"""规则版本留痕引擎（P0-A）—— 唯一权威：`config/rule_versions.json`。

**解决的缺口**（实测取证，非设想）：
现有 finding 已带 `trace_id` / Provenance / 法规版本（`config/legal_versions.json`）/
报告版本（`engine/report_compliance`），**但没有"这条结论当时按哪版规则算出来的"**。
规则一旦修改，历史结论无法自证——违反报告可追溯要求。

**三条设计铁律**：
1. **未登记 ⇒ 显式标「未登记」**，绝不用默认版本静默顶替（否则等于伪造版本溯源）。
2. **单一权威**：版本号只在 `config/rule_versions.json` 登记；本模块只读、不做二次维护。
   新增同类对象 = 加一行数据，不改逻辑分支。
3. **不打乱既有契约**：只在 finding 上**新增字段**，不改既有字段名与语义（向后兼容）。

公开入口：
    rule_set_version()        —— 规则集版本（整批）
    version_of(rule_id)       —— 单条规则版本；未登记返回 None
    stamp(finding)            —— 就地补齐 rule_version / rule_set_version 并返回
    snapshot()                —— 本次分析所用版本集（供报告与审计留痕）
    coverage(rules=None)      —— 版本登记覆盖率（供门禁，不猜）
    load_versions()           —— 读取登记表（★ 不叫 load：与 risk_families.load 撞名会被
                                  「跨模块同名函数」闸门判为真实分歧）
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent
_VERSIONS = _ROOT / "config" / "rule_versions.json"
_CACHE: Optional[Dict[str, Any]] = None


def load_versions() -> Dict[str, Any]:
    """规则版本登记表（**唯一读取入口**）。读不到时返回空表并由调用方显式处理。

    ★ 命名说明：**既不叫 `load()`**（与 `risk_families.load` 撞名）、**也不叫
      `load_registry()`**（与 `common_clauses.load_registry` 撞名）—— 两者都会触发
      「跨模块同名函数」闸门的人工裁定负担。取 `load_versions` 表意明确且不撞。
    """
    global _CACHE
    if _CACHE is None:
        try:
            _CACHE = json.loads(_VERSIONS.read_text(encoding="utf-8"))
        except Exception:
            _CACHE = {}
    return _CACHE or {}


def reload() -> Dict[str, Any]:
    """强制重读（测试与迁移用）。"""
    global _CACHE
    _CACHE = None
    return load_versions()


def rule_set_version() -> str:
    """整批规则集版本。未登记返回空串（调用方须显式处理，不得填默认值）。"""
    return str(load_versions().get("rule_set_version") or "")


def _rules() -> Dict[str, Any]:
    r = load_versions().get("rules")
    return r if isinstance(r, dict) else {}


def version_of(rule_id: Any) -> Optional[str]:
    """单条规则版本；**未登记返回 None**（不猜、不默认）。"""
    rid = str(rule_id or "").strip()
    if not rid:
        return None
    item = _rules().get(rid)
    if isinstance(item, dict):
        v = item.get("version")
        return str(v) if v else None
    if isinstance(item, str) and item:
        return item
    return None


def stamp(finding: Dict[str, Any]) -> Dict[str, Any]:
    """就地补齐版本字段并返回（幂等）。

    - 有 `rule_id` 且已登记 ⇒ `rule_version` = 登记版本；
    - 有 `rule_id` 但未登记 ⇒ `rule_version` = **"未登记"**（并置 `rule_version_status`），
      **绝不写默认版本**；
    - 无 `rule_id`（域分析等非规则型发现）⇒ 只给规则集版本，不给单条版本，
      `rule_version_status` = `not_applicable`（不制造假归属）。
    """
    if not isinstance(finding, dict):
        return finding
    rsv = rule_set_version()
    if rsv:
        finding["rule_set_version"] = rsv
    rid = finding.get("rule_id") or finding.get("redline_id")
    if not rid:
        finding["rule_version_status"] = "not_applicable"
        return finding
    v = version_of(rid)
    if v:
        finding["rule_version"] = v
        finding["rule_version_status"] = "registered"
    else:
        finding["rule_version"] = "未登记"
        finding["rule_version_status"] = "unregistered"
    return finding


def stamp_all(findings: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """批量打戳（迭代遍历，兼容任意 list）。"""
    out: List[Dict[str, Any]] = []
    for f in findings or []:
        if isinstance(f, dict):
            stamp(f)
        out.append(f)
    return out


def snapshot(findings: Optional[Iterable[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """本次分析所用版本集：规则集版本 + 命中规则及其版本 + 未登记清单。"""
    rsv = rule_set_version()
    hit: Dict[str, str] = {}
    unregistered: List[str] = []
    for f in findings or []:
        if not isinstance(f, dict):
            continue
        rid = f.get("rule_id") or f.get("redline_id")
        if not rid:
            continue
        v = version_of(rid)
        if v:
            hit[str(rid)] = v
        elif str(rid) not in unregistered:
            unregistered.append(str(rid))
    return {
        "rule_set_version": rsv or "未登记",
        "hit_rule_count": len(hit),
        "hit_rule_versions": dict(sorted(hit.items())),
        "unregistered_rule_ids": sorted(unregistered),
    }


def registered_ids() -> List[str]:
    return sorted(_rules().keys())


def coverage(rules: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """版本登记覆盖率。`rules` 传入时应覆盖**全部已发布规则 id**（由门禁负责取全）。"""
    if rules is None:
        return {"total": len(_rules()), "registered": len(_rules()),
                "missing": [], "ratio": 1.0 if _rules() else 0.0}
    ids = [str(r).strip() for r in rules if str(r or "").strip()]
    registered = set(_rules().keys())
    missing = [r for r in ids if r not in registered]
    total = len(ids)
    return {
        "total": total,
        "registered": total - len(missing),
        "missing": missing,
        "ratio": (1.0 if total == 0 else round((total - len(missing)) / total, 4)),
    }


def declared_rules() -> List[Tuple[str, str]]:
    """(rule_id, version) 列表，供审计与报告展示。"""
    return [(k, str(v.get("version") if isinstance(v, dict) else v or ""))
            for k, v in sorted(_rules().items())]
