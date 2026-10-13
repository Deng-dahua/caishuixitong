# -*- coding: utf-8 -*-
"""报告模板**管理**（P1-5）—— 模板清单与变更台账的**唯一权威**。

## 扫描现状（改动前）

| 既有 | 位置 | 说明 |
|---|---|---|
| 模板数据（4 个） | `config/report_compliance.json::templates` | **只读配置**：`service_light` / `manufacturing` / `retail` / `project_based` |
| 模板装配（运行时） | `engine/report_template.py` | `section_order()` / `apply_template()` / `validate_templates()`；章节白名单 `BASE_SECTIONS` |
| 行业→模板映射 | `engine/industry_params.json` → `report_template(template_id)` | 行业决定用哪个模板 |

**缺口**：模板只存在于**配置文件**里 —— 没有接口可列举 / 查看 / 新增 / 修改 / 停用，
变更也**无留痕**（改了 `report_compliance.json` 无从追溯"谁在什么时候改了什么"）。

## 本模块做什么（**不改既有装配行为**）

1. **有效模板 = 内置（config）⊕ 自定义覆盖（台账）**：内置模板仍来自 `report_compliance`，
   本模块**不复制**它；自定义/覆盖版本落 append-only 台账 `data/report_templates.jsonl`。
2. **模板即"章节顺序 + 侧重"**：章节仍必须落在 `report_template.BASE_SECTIONS` 白名单内
   （否则 400）—— 这条**不放松**，否则"新增一个章节"会悄悄发生而不显式登记。
3. **版本化**：每次变更追加一行（含 `version` 递增、`action`、`actor`、`at`），
   当前态由**折叠**得到（沿用 `analysis_jobs`/`risk_review` 同一惯用法）。
4. **不改既有函数语义**：`report_template.section_order()` 等保持现状；
   本模块提供 `effective_templates()` 供**新增的接口**与后续装配升级使用。

## 铁律

- **单一权威**：模板清单只在本模块收口；`config/report_compliance.json` 仍是**内置**来源，
  本模块只**读**它。
- **缺失 ≠ 0**：查不到模板 ⇒ `None` + 明确原因，**不返回空模板**（空模板会产出"没章节的报告"）。
- **不改事实**：模板只决定**呈现**（章节顺序/侧重），不增删风险事项（`report_template` 既有铁律）。
"""
from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "TemplateError", "templates_path", "builtin_templates", "effective_templates",
    "list_templates", "get_template", "template_versions", "upsert_template",
    "disable_template", "reset_cache", "last_errors", "metadata",
]

SCOPE_BUILTIN = "builtin"
SCOPE_CUSTOM = "custom"

#: 模板 ID 合法形态（小写字母开头，可含数字/下划线；**防注入与路径穿越**）
_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,48}$")

_LOCK = threading.RLock()
_CACHE: Dict[str, Any] = {}
_LAST_ERROR = ""


class TemplateError(Exception):
    """模板层错误（`status` 为 HTTP 语义码，由 API 层转 `HTTPException`）。"""

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
        print("[report-template] %s" % msg, file=_sys.stderr, flush=True)
    except Exception:                                         # noqa: BLE001
        pass


def reset_cache() -> None:
    with _LOCK:
        _CACHE.clear()


def templates_path() -> Path:
    """变更台账路径。

    ★ **调用时**解析 `runtime_storage`（不在 import 期固化）—— 否则隔离实例
      （`APP_DATA_DIR`）会越界写生产数据（P0-7 的 `_LEDGER` 教训）。
    """
    from runtime_storage import DATA_DIR                     # noqa: PLC0415
    return Path(DATA_DIR) / "report_templates.jsonl"


# ══════════════════════════════════════════════════════════════════════════
# ① 内置模板（唯一来源 = report_compliance；本模块**只读**）
# ══════════════════════════════════════════════════════════════════════════
def builtin_templates() -> Dict[str, Dict[str, Any]]:
    """内置模板（来自 `config/report_compliance.json::templates`）。

    ★ **读不到 ⇒ 返回空字典**（由调用方如实呈现"内置模板不可用"），不伪造。
    """
    try:
        from engine.report_compliance import load_config     # noqa: PLC0415
        tpl = (load_config().get("templates") or {})
    except Exception as exc:                                  # noqa: BLE001
        _log("内置模板不可用：%s" % exc)
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for tid, t in tpl.items():
        out[str(tid)] = {
            "template_id": str(tid),
            "label": str((t or {}).get("label") or tid),
            "sections": [str(x) for x in ((t or {}).get("sections") or [])],
            "emphasis": str((t or {}).get("emphasis") or ""),
            "scope": SCOPE_BUILTIN,
            "version": 0,
        }
    return out


# ══════════════════════════════════════════════════════════════════════════
# ② 台账（append-only + 折叠）
# ══════════════════════════════════════════════════════════════════════════
def _load_template_events() -> List[Dict[str, Any]]:
    try:
        from runtime_storage import read_jsonl               # noqa: PLC0415
        rows, bad = read_jsonl(templates_path())
        if bad:
            _log("模板台账有 %d 行无法解析（已如实计数，未静默丢弃）" % bad)
        return [r for r in rows if isinstance(r, dict)]
    except Exception as exc:                                  # noqa: BLE001
        _log("模板台账不可读：%s" % exc)
        return []


def _append_event(row: Dict[str, Any]) -> None:
    from runtime_storage import append_jsonl                 # noqa: PLC0415
    append_jsonl(templates_path(), row)


def _custom_templates() -> Dict[str, Dict[str, Any]]:
    """由台账折叠出的**自定义/覆盖**模板（同一 id 最后一次胜出；`disabled` 的标记为停用）。"""
    out: Dict[str, Dict[str, Any]] = {}
    for r in _load_template_events():
        tid = str(r.get("template_id") or "").strip()
        if not tid:
            continue
        if str(r.get("action") or "") == "disable":
            rec = out.setdefault(tid, {})
            rec["disabled"] = True
            rec["disabled_at"] = str(r.get("at") or "")
            rec["disabled_by"] = str(r.get("actor") or "")
            rec["version"] = int(r.get("version") or rec.get("version") or 0)
            continue
        out[tid] = {
            "template_id": tid,
            "label": str(r.get("label") or tid),
            "sections": [str(x) for x in (r.get("sections") or [])],
            "emphasis": str(r.get("emphasis") or ""),
            "scope": SCOPE_CUSTOM,
            "version": int(r.get("version") or 0),
            "created_at": str(r.get("at") or ""),
            "created_by": str(r.get("actor") or ""),
            "note": str(r.get("note") or ""),
            "disabled": bool(out.get(tid, {}).get("disabled")),
        }
    return out


# ══════════════════════════════════════════════════════════════════════════
# ③ 有效模板 = 内置 ⊕ 覆盖
# ══════════════════════════════════════════════════════════════════════════
def effective_templates() -> Dict[str, Dict[str, Any]]:
    """当前**有效**模板集合（自定义覆盖内置；停用项的处置见下）。

    ★ 停用语义分两种（**不能一律删除** —— 那会让"停用覆盖"变成"模板消失"）：
      · 停用**覆盖内置**的模板 ⇒ **回到内置出厂值**（内置仍在有效集合里）；
      · 停用**纯自定义**模板   ⇒ 从有效集合移除。
    """
    with _LOCK:
        if "eff" not in _CACHE:
            builtin = builtin_templates()
            merged: Dict[str, Dict[str, Any]] = dict(builtin)
            for tid, c in _custom_templates().items():
                if c.get("disabled"):
                    if tid in builtin:
                        # 覆盖被停用 ⇒ 恢复内置出厂值（**保留**，不是删除）
                        merged[tid] = dict(builtin[tid])
                    else:
                        merged.pop(tid, None)
                    continue
                merged[tid] = dict(c)
            _CACHE["eff"] = merged
        return dict(_CACHE["eff"])


def list_templates(*, include_disabled: bool = False) -> List[Dict[str, Any]]:
    """模板清单（默认不含停用项；`include_disabled=True` 时带 `disabled` 标记一起返回）。"""
    builtin = builtin_templates()
    custom = _custom_templates()
    rows: List[Dict[str, Any]] = []
    for tid, t in effective_templates().items():
        item = dict(t)
        item["overridden"] = tid in custom
        item["was_builtin"] = tid in builtin
        rows.append(item)
    if include_disabled:
        for tid, c in custom.items():
            if c.get("disabled") and tid not in effective_templates():
                item = dict(c)
                item["overridden"] = True
                item["was_builtin"] = tid in builtin
                rows.append(item)
    rows.sort(key=lambda x: (str(x.get("scope")), str(x.get("template_id"))))
    return rows


def get_template(template_id: Any) -> Optional[Dict[str, Any]]:
    """取单个模板；不存在 ⇒ `None`（**不返回空模板**）。"""
    tid = str(template_id or "").strip()
    if not tid:
        return None
    eff = effective_templates()
    if tid in eff:
        item = dict(eff[tid])
        item["overridden"] = tid in _custom_templates()
        item["was_builtin"] = tid in builtin_templates()
        return item
    return None


def template_versions(template_id: Any) -> List[Dict[str, Any]]:
    """该模板的**变更历史**（时间正序；含 disable 事件）。"""
    tid = str(template_id or "").strip()
    out = []
    for r in _load_template_events():
        if str(r.get("template_id") or "") != tid:
            continue
        out.append({
            "version": int(r.get("version") or 0),
            "action": str(r.get("action") or ""),
            "at": str(r.get("at") or ""),
            "actor": str(r.get("actor") or ""),
            "label": str(r.get("label") or ""),
            "sections": [str(x) for x in (r.get("sections") or [])],
            "emphasis": str(r.get("emphasis") or ""),
            "note": str(r.get("note") or ""),
        })
    return out


# ══════════════════════════════════════════════════════════════════════════
# ④ 写入
# ══════════════════════════════════════════════════════════════════════════
def _validate_sections(sections: Any) -> List[str]:
    """章节必须落在 `report_template.BASE_SECTIONS` 白名单内（**不放松**）。"""
    try:
        from engine.report_template import BASE_SECTIONS     # noqa: PLC0415
    except Exception as exc:                                  # noqa: BLE001
        raise TemplateError("章节白名单不可取（report_template 不可用）：%s" % exc, 500) from exc
    secs = [str(x).strip() for x in (sections or []) if str(x or "").strip()]
    if not secs:
        raise TemplateError("sections 不能为空（空模板会产出『没有章节的报告』）", 400)
    bad = [s for s in secs if s not in BASE_SECTIONS]
    if bad:
        raise TemplateError(
            "章节不在白名单内：%s（合法值为：%s）"
            % ("、".join(bad), "、".join(BASE_SECTIONS)), 400)
    # 去重但保序
    seen: set = set()
    uniq: List[str] = []
    for s in secs:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


def upsert_template(template_id: Any, payload: Dict[str, Any], session: Any, *,
                    request: Any = None) -> Dict[str, Any]:
    """新建 / 覆盖一个模板（写台账，**版本号自增**）。

    ★ 覆盖**内置**模板是允许的（`overridden=True`），但**不修改** `report_compliance.json`
      —— 内置仍是"出厂值"，随时可停用覆盖回到出厂。
    """
    tid = str(template_id or "").strip()
    if not _ID_RE.match(tid):
        raise TemplateError(
            "模板编码必须为 2~49 位小写字母/数字/下划线，且以字母开头：%r" % tid, 400)
    body = payload if isinstance(payload, dict) else {}
    label = str(body.get("label") or "").strip()
    if not label:
        raise TemplateError("label（模板名称）不能为空", 400)
    secs = _validate_sections(body.get("sections"))
    emphasis = str(body.get("emphasis") or "").strip()
    note = str(body.get("note") or "").strip()

    hist = template_versions(tid)
    next_ver = (max([int(x.get("version") or 0) for x in hist] or [0])) + 1
    actor = str(getattr(session, "username", "") or "")
    aid = getattr(session, "user_id", None)

    from runtime_storage import now_cst                      # noqa: PLC0415
    row = {"at": now_cst(), "event": "template", "action": "upsert",
           "template_id": tid, "version": next_ver,
           "label": label, "sections": secs, "emphasis": emphasis,
           "note": note, "actor": actor,
           "actor_id": (int(aid) if aid not in (None, "") else None)}
    with _LOCK:
        _append_event(row)
        _CACHE.pop("eff", None)

    _audit("report_template.upsert", tid,
           "报告模板「%s」v%d：章节 %s"
           % (label, next_ver, "、".join(secs)), request, session)
    out = get_template(tid) or {}
    out["version"] = next_ver
    out["message"] = "模板「%s」已保存为 v%d（内置覆盖：%s）" % (
        label, next_ver, "是" if tid in builtin_templates() else "否")
    return out


def disable_template(template_id: Any, session: Any, *, request: Any = None,
                     note: str = "") -> Dict[str, Any]:
    """停用一个**自定义/覆盖**模板（回到内置出厂值，或从有效集合中移除）。

    ★ **不允许停用"未被覆盖的内置模板"** —— 那会把出厂模板从有效集合里抹掉，
      而用户其实无从"恢复"（没有删除内置的入口）。要停用内置，须先覆盖再停用。
    """
    tid = str(template_id or "").strip()
    if not tid:
        raise TemplateError("模板编码不能为空", 400)
    custom = _custom_templates()
    if tid not in custom:
        raise TemplateError(
            "「%s」不是自定义/覆盖模板，不能停用（内置模板请先覆盖再停用）" % tid, 400)
    if custom[tid].get("disabled"):
        out = {"template_id": tid, "disabled": True, "noop": True,
               "message": "该模板已处于停用状态，本次未产生变更"}
        return out
    hist = template_versions(tid)
    next_ver = (max([int(x.get("version") or 0) for x in hist] or [0])) + 1
    actor = str(getattr(session, "username", "") or "")
    aid = getattr(session, "user_id", None)
    from runtime_storage import now_cst                      # noqa: PLC0415
    with _LOCK:
        _append_event({"at": now_cst(), "event": "template", "action": "disable",
                       "template_id": tid, "version": next_ver,
                       "note": str(note or ""), "actor": actor,
                       "actor_id": (int(aid) if aid not in (None, "") else None)})
        _CACHE.pop("eff", None)
    _audit("report_template.disable", tid, "停用报告模板「%s」v%d" % (tid, next_ver),
           request, session)
    return {"template_id": tid, "disabled": True, "noop": False, "version": next_ver,
            "message": "模板「%s」已停用（若它曾覆盖内置模板，则已回到出厂值）" % tid}


def _audit(action: str, target: str, detail: str, request: Any, session: Any) -> None:
    """薄转发 `audit_trail.record`（**不放进 try/except:pass** —— 留痕失败必须可见）。"""
    from engine.audit_trail import record as _rec            # noqa: PLC0415
    uid = getattr(session, "user_id", None) if session is not None else None
    uname = str(getattr(session, "username", "") or "") if session is not None else ""
    _rec(action, target=target, detail=detail, request=request,
         user_id=(int(uid) if uid not in (None, "") else None),
         user_name=(uname or None))


def metadata() -> Dict[str, Any]:
    """字典（供接口/前端；章节白名单与内置模板一并下发）。"""
    try:
        from engine.report_template import BASE_SECTIONS, REQUIRED_SECTIONS   # noqa: PLC0415
        base = list(BASE_SECTIONS)
        required = list(REQUIRED_SECTIONS)
    except Exception:                                         # noqa: BLE001
        base, required = [], []
    return {
        "base_sections": base,
        "required_sections": required,
        "builtin_ids": sorted(builtin_templates().keys()),
        "scopes": [SCOPE_BUILTIN, SCOPE_CUSTOM],
        "id_pattern": _ID_RE.pattern,
        "storage": "data/report_templates.jsonl（append-only，当前态由折叠得到）",
        "note": ("模板只决定**呈现**（章节顺序与侧重），**不增删风险事项**；"
                 "章节必须落在 base_sections 白名单内。"),
    }
