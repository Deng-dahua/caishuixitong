# -*- coding: utf-8 -*-
"""规则版本**管理**（P1-6）—— 发布 / 回滚 / 版本差异。

## 扫描现状（改动前）

| 既有 | 位置 | 说明 |
|---|---|---|
| 版本登记（176 条） | `config/rule_versions.json::rules` | 每条规则的 `version/effective_from/changed_note/layer` |
| 出厂历史 | 同上 `rule_set_history` | **只有 1 条**（`2026.10` 初始登记）—— 之后所有变更都无处记录 |
| 判读 | `engine/rule_versions.py` | `rule_set_version()` / `version_of()` / `stamp()`（给 finding 打版本戳） |

**缺口**：版本**只能读不能管** —— 无法发布新版本、无法回滚、无法看"两版之间差了什么"，
且**变更无留痕**（改了 `rule_versions.json` 无从追溯是谁改的）。

## 本模块做什么

1. **发布**（`publish`）：把"当前生效版本"推进到新版本号，并把**当时的逐条规则版本快照**
   落盘（供后续 diff）；写 append-only 台账 `data/rule_version_events.jsonl`。
2. **回滚**（`rollback`）：把生效版本退回一个**历史版本**（必须在历史里，否则 400）。
3. **差异**（`diff`）：比较两个版本的**快照**，给出新增/删除/版本变更三类差异。
4. **变更留痕**：每次发布/回滚写审计动作 `rule_version.publish` / `rule_version.rollback`。

## 铁律

- **单一权威**：「当前生效版本」的唯一判读点是 `rule_versions.rule_set_version()`
  （它优先取台账、回落 config）。本模块**不另存一份当前版本**。
- **未发布时与基线完全一致**：台账为空 ⇒ `rule_set_version()` 等于 config 值
  （闸门断言；这也保证既有报告溯源不受影响）。
- **不猜**：版本号格式非法 / 重复 / 非单调 / 回滚目标不在历史 ⇒ 400 并说明原因。
- **快照可缺**：旧版本没有快照 ⇒ `diff` 如实说明"该版本无快照，无法比对"，
  **不返回空差异**（空差异会被误读成"两版完全相同"）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "RuleVersionError", "VERSION_RE", "current_version", "list_versions",
    "publish", "rollback_version", "diff", "snapshot_of", "versions_dir",
    "last_errors", "metadata",
]

#: 版本号形态：`YYYY.NN`（与既有 `2026.10` 同族）
VERSION_RE = re.compile(r"^\d{4}\.(0[1-9]|1[0-2])$")

_LAST_ERROR = ""


class RuleVersionError(Exception):
    """版本管理层错误（`status` 为 HTTP 语义码，由 API 层转 `HTTPException`）。"""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = int(status)


def last_errors() -> str:
    return _LAST_ERROR


def _log(msg: str) -> None:
    global _LAST_ERROR
    _LAST_ERROR = str(msg)
    try:
        import sys as _sys                                    # noqa: PLC0415
        print("[rule-version] %s" % msg, file=_sys.stderr, flush=True)
    except Exception:                                         # noqa: BLE001
        pass


# ══════════════════════════════════════════════════════════════════════════
# 读取（一律转发 `rule_versions`，**不另立第二份**）
# ══════════════════════════════════════════════════════════════════════════
def current_version() -> str:
    """**当前生效**版本（唯一判读点：`rule_versions.rule_set_version()`）。"""
    from engine import rule_versions as RV                    # noqa: PLC0415
    return RV.rule_set_version()


def versions_dir() -> Path:
    """快照目录（**调用时**解析 `runtime_storage` ⇒ 隔离实例不越界）。"""
    from runtime_storage import DATA_DIR                      # noqa: PLC0415
    return Path(DATA_DIR) / "rule_version_snapshots"


def _snapshot_path(version: str) -> Path:
    return versions_dir() / ("%s.json" % str(version))


def snapshot_of(version: str) -> Optional[Dict[str, Any]]:
    """某版本的逐条规则版本快照；**没有快照 ⇒ `None`**（不返回空字典）。"""
    p = _snapshot_path(version)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:                                  # noqa: BLE001
        _log("快照 %s 解析失败：%s" % (version, exc))
        return None


def _write_snapshot(version: str, data: Dict[str, Any]) -> None:
    from runtime_storage import atomic_write_json             # noqa: PLC0415
    versions_dir().mkdir(parents=True, exist_ok=True)
    atomic_write_json(_snapshot_path(version), data, indent=1)


def _current_rules_map() -> Dict[str, str]:
    """当前 config 里每条规则的版本（`{rule_id: version}`）。"""
    from engine import rule_versions as RV                    # noqa: PLC0415
    return {rid: (ver or "") for rid, ver in RV.declared_rules()}


def list_versions() -> List[Dict[str, Any]]:
    """版本清单（出厂历史 + 台账事件；**同一版本台账胜出**），按版本倒序。"""
    from engine import rule_versions as RV                    # noqa: PLC0415
    cur = current_version()
    rows = RV.rule_set_history()
    for r in rows:
        r["is_current"] = (str(r.get("version") or "") == cur)
        r["has_snapshot"] = _snapshot_path(str(r.get("version") or "")).exists()
    rows.sort(key=lambda x: str(x.get("version") or ""), reverse=True)
    return rows


# ══════════════════════════════════════════════════════════════════════════
# 写入
# ══════════════════════════════════════════════════════════════════════════
def _validate_version(version: Any) -> str:
    v = str(version or "").strip()
    if not VERSION_RE.match(v):
        raise RuleVersionError(
            "版本号必须形如 `YYYY.NN`（年份.两位月份），当前为 %r" % v, 400)
    return v


def publish(version: Any, session: Any, *, note: str = "",
            request: Any = None) -> Dict[str, Any]:
    """发布新版本：写台账 + 落**逐条规则版本快照**（供 diff）。

    ★ 版本号必须与当前生效版本**不同**（重复发布 ⇒ 400：那不是"发布"，是误操作）。
    """
    v = _validate_version(version)
    cur = current_version()
    if v == cur:
        raise RuleVersionError("版本 %s 已是当前生效版本，无需发布" % v, 400)
    from engine import rule_versions as RV                    # noqa: PLC0415
    if v in {str(x.get("version") or "") for x in RV.rule_set_history()}:
        raise RuleVersionError(
            "版本 %s 已在历史中；要改回该版本请用**回滚**（发布需用新版本号）" % v, 400)
    rules_map = _current_rules_map()
    from runtime_storage import now_cst                       # noqa: PLC0415
    actor = str(getattr(session, "username", "") or "")
    aid = getattr(session, "user_id", None)
    _write_snapshot(v, {"version": v, "at": now_cst(), "rules": rules_map})
    RV.append_event({"at": now_cst(), "action": "publish", "from_version": cur,
                     "to_version": v, "note": str(note or ""),
                     "rule_count": len(rules_map), "actor": actor,
                     "actor_id": (int(aid) if aid not in (None, "") else None)})
    _audit("rule_version.publish", v,
           "发布规则集版本 %s（自 %s，共 %d 条规则）%s"
           % (v, cur or "未登记", len(rules_map),
              ("；说明：%s" % note[:200]) if note else ""), request, session)
    return {"from_version": cur, "to_version": v, "rule_count": len(rules_map),
            "snapshot": str(_snapshot_path(v)),
            "message": "已发布规则集版本 %s（自 %s）；逐条规则版本快照已落盘，可做版本差异比对。"
                       % (v, cur or "未登记")}


def rollback_version(version: Any, session: Any, *, note: str = "",
             request: Any = None) -> Dict[str, Any]:
    """回滚到**历史中已存在**的版本（目标不在历史 ⇒ 400，不静默接受）。"""
    v = _validate_version(version)
    cur = current_version()
    from engine import rule_versions as RV                    # noqa: PLC0415
    known = {str(x.get("version") or "") for x in RV.rule_set_history()}
    if v not in known:
        raise RuleVersionError(
            "版本 %s 不在历史中，无法回滚（历史版本：%s）"
            % (v, "、".join(sorted(known)) or "无"), 400)
    if v == cur:
        raise RuleVersionError("版本 %s 已是当前生效版本，无需回滚" % v, 400)
    from runtime_storage import now_cst                       # noqa: PLC0415
    actor = str(getattr(session, "username", "") or "")
    aid = getattr(session, "user_id", None)
    RV.append_event({"at": now_cst(), "action": "rollback", "from_version": cur,
                     "to_version": v, "note": str(note or ""), "actor": actor,
                     "actor_id": (int(aid) if aid not in (None, "") else None)})
    _audit("rule_version.rollback", v,
           "回滚规则集版本 %s → %s%s"
           % (cur or "未登记", v, ("；说明：%s" % note[:200]) if note else ""),
           request, session)
    return {"from_version": cur, "to_version": v,
            "has_snapshot": _snapshot_path(v).exists(),
            "message": "已回滚到 %s（自 %s）。" % (v, cur or "未登记")}


def diff(from_version: Any, to_version: Any) -> Dict[str, Any]:
    """两版本差异（基于**快照**）：新增规则 / 移除规则 / 版本变更。

    ★ 任一侧无快照 ⇒ 返回 `comparable=False` + 明确原因，**不返回空差异**
      （空差异会被误读为"两版完全相同"）。
    """
    a = _validate_version(from_version)
    b = _validate_version(to_version)
    sa, sb = snapshot_of(a), snapshot_of(b)
    missing = [x for x, s in ((a, sa), (b, sb)) if s is None]
    if missing:
        return {"from_version": a, "to_version": b, "comparable": False,
                "reason": ("版本 %s 没有快照，无法比对差异（快照在**发布时**落盘，"
                           "历史出厂版本与回滚目标可能没有快照）。" % "、".join(missing)),
                "added": [], "removed": [], "changed": [],
                "note": "无快照 ≠ 两版相同。"}
    ra = (sa.get("rules") or {})
    rb = (sb.get("rules") or {})
    added = sorted(set(rb) - set(ra))
    removed = sorted(set(ra) - set(rb))
    changed = sorted([{"rule_id": k, "from": str(ra[k]), "to": str(rb[k])}
                      for k in (set(ra) & set(rb)) if str(ra[k]) != str(rb[k])],
                     key=lambda x: x["rule_id"])
    return {"from_version": a, "to_version": b, "comparable": True,
            "counts": {"from": len(ra), "to": len(rb),
                       "added": len(added), "removed": len(removed),
                       "changed": len(changed)},
            "added": added[:200], "removed": removed[:200], "changed": changed[:200],
            "truncated": (len(added) > 200 or len(removed) > 200 or len(changed) > 200),
            "note": "差异基于发布时落盘的**逐条规则版本快照**；截断时 `truncated=true`。"}


def _audit(action: str, target: str, detail: str, request: Any, session: Any) -> None:
    from engine.audit_trail import record as _rec              # noqa: PLC0415
    uid = getattr(session, "user_id", None) if session is not None else None
    uname = str(getattr(session, "username", "") or "") if session is not None else ""
    _rec(action, target=target, detail=detail, request=request,
         user_id=(int(uid) if uid not in (None, "") else None),
         user_name=(uname or None))


def metadata() -> Dict[str, Any]:
    """字典（供接口/前端）。"""
    from engine import rule_versions as RV                     # noqa: PLC0415
    return {
        "current_version": current_version(),
        "config_version": str(RV.load_versions().get("rule_set_version") or ""),
        "registered_rule_count": len(RV.registered_ids()),
        "version_pattern": VERSION_RE.pattern,
        "storage": "data/rule_version_events.jsonl（append-only）+ data/rule_version_snapshots/*.json",
        "note": ("「当前生效版本」唯一判读点 = `rule_versions.rule_set_version()`；"
                 "**未发布时与配置基线完全一致**。版本差异基于发布时快照；"
                 "无快照时如实说明，不返回空差异。"),
    }
