# -*- coding: utf-8 -*-
"""规则库的**中文标签 + 候选清单处置台账**（2026-10-18）。

解决三件事（用户实测反馈）
--------------------------
1. **下拉英文**：`layer` 的值是 Python 模块名 / 候选清单文件名（`rulelist_v12.json`），
   前端直接显示 ⇒ 下拉里全是英文。唯一权威 `config/rule_layer_labels.json`。
2. **严重度/版本/法规依据三列看不出结论**：
   · 严重度原样是 `high/medium/low`；
   · 版本只有真规则才有（候选 460 条全「未登记」）；
   · 法规依据 460 条**全部**写着占位「法规库自动匹配」。
3. **候选清单（未入库）无处处置**：460 条候选只是躺在 JSON 里，谁该入库、谁被覆盖、
   谁卡在数据源，没有任何一处给出结论。

处置口径（**只做可推导的事，推不出就如实说推不出**）
----------------------------------------------------
· **版本**：已登记规则 → 取 `config/rule_versions.json`；候选若映射到某已登记规则
  → `沿用 <规则号> v<x>`；其余 → 候选清单自身版次（`V1.0 / V1.1 / V1.2`）+「未发布」。
· **法规依据**：候选的 `by` 字段指向系统内规则（`RL-*` / `VR*`）时，**转查**
  `config/legal_mappings.json`（唯一已确证关联表）取真实条款 ID；查不到 ⇒
  `undetermined` + 写明原因（**绝不**用规则名去猜法条）。
· **数据源缺口**：用 `config/rule_dsl_scope.json` 的 `var_map` 实测该候选的 `inputs`
  有几个没有取数口径 ⇒ 决定它能不能真执行（这是"入库"与否的硬约束）。
· **严重度**：`high/medium/low` → 系统权威等级词，取值表在 `config/rule_layer_labels.json`。

★ 本模块**不执行规则、不改规则本体**，只做「读 + 标注 + 汇总」。
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CFG_P = os.path.join(_ROOT, "config", "rule_layer_labels.json")
_CACHE: Dict[str, Any] = {}

#: 候选清单文件名 → 自身版次（用于「版本」列可读化；新增清单只加一行）
_LIST_VER: Dict[str, str] = {
    "rulelist_v1.json": "V1.0",
    "rulelist_v11.json": "V1.1",
    "rulelist_v12.json": "V1.2",
}

#: 从 `by` 文本里抓系统规则号（RL-XXX-000 / VR000 / 其它 PREFIX-000）
_RID_RE = re.compile(r"\b(RL-[A-Z]{2,4}-\d{3}|VR\d{3,4}|[A-Z]{2,6}-[A-Z]{2,4}-\d{3})\b")


def labels(refresh: bool = False) -> Dict[str, Any]:
    """读标签权威表（进程内缓存）。"""
    if not refresh and _CACHE.get("labels"):
        return _CACHE["labels"]
    try:
        with open(_CFG_P, encoding="utf-8") as fh:
            d = json.load(fh)
    except Exception:                                          # noqa: BLE001
        d = {}
    _CACHE["labels"] = d
    return d


def reset_cache() -> None:
    _CACHE.clear()


def _pick(section: str, value: Any, default_cn: str = "") -> str:
    m = (labels().get(section) or {})
    if not isinstance(m, dict):
        return default_cn
    v = m.get(str(value or ""))
    if isinstance(v, dict):
        return str(v.get("cn") or default_cn)
    return str(v or default_cn)


def layer_cn(layer: Any) -> str:
    """层的中文名。未登记 ⇒ 原样返回（由闸门报 ERROR，不静默）。"""
    return _pick("labels", layer, str(layer or ""))


def severity_cn(sev: Any) -> str:
    return _pick("severity_labels", sev, str(sev or ""))


def candidate_status_cn(status: Any) -> str:
    return _pick("candidate_status_labels", status, str(status or ""))


def candidate_action_cn(action: Any) -> str:
    return _pick("candidate_action_labels", action, str(action or ""))


def layer_options(present: Optional[List[str]] = None) -> List[Dict[str, str]]:
    """下拉选项：值 = 真实 layer，标签 = 中文名（附说明）。"""
    reg = (labels().get("labels") or {})
    out: List[Dict[str, str]] = []
    seen = set()
    for k, v in reg.items():
        if not isinstance(v, dict):
            continue
        out.append({"value": k, "label": str(v.get("cn") or k),
                    "note": str(v.get("note") or "")})
        seen.add(k)
    # 实际出现但未登记的层：**照样列出**（否则前端看不到、也无从发现漏登记）
    for k in (present or []):
        if k and k not in seen:
            out.append({"value": k, "label": k, "note": "未登记中文名（见闸门 check_rule_layer_labels）"})
            seen.add(k)
    return out


# ────────────────────────── 候选台账 ──────────────────────────

def system_rule_ids() -> set:
    """系统**真实存在**的规则号（红线 + 已验证原子规则）。

    ★ 用途：候选清单的 `status` 是**写下那一刻**的判断，此后系统新增检测器时
      清单不会自动更新（实测：VAT-004…CIT-030 共 12 条仍标 `missing`，
      但系统已由 VR075~VR086 真实实现，`by` 里甚至写着「本批落地」）。
      不核对就会出现"清单说没入库、系统其实早就有"的自相矛盾台账。
    """
    if _CACHE.get("sys_ids") is not None:
        return _CACHE["sys_ids"]
    ids: set = set()
    try:
        from engine.tax_redlines import REDLINES              # noqa: PLC0415
        ids |= {str(r.get("id") or "") for r in REDLINES if r.get("id")}
    except Exception:                                          # noqa: BLE001
        pass
    try:
        import re as _re                                      # noqa: PLC0415
        src = open(os.path.join(_ROOT, "engine", "verified_rule_engine.py"),
                   encoding="utf-8").read()
        ids |= set(_re.findall(r'"id":\s*"(VR\d{3,4})"', src))
    except Exception:                                          # noqa: BLE001
        pass
    ids.discard("")
    _CACHE["sys_ids"] = ids
    return ids


def _versions_index() -> Dict[str, Dict[str, Any]]:
    p = os.path.join(_ROOT, "config", "rule_versions.json")
    try:
        with open(p, encoding="utf-8") as fh:
            return dict((json.load(fh).get("rules") or {}))
    except Exception:                                          # noqa: BLE001
        return {}


def _var_map() -> set:
    """候选里已登记「取数口径」的字段集合（唯一权威 `config/rule_dsl_scope.json` 现算）。"""
    if _CACHE.get("var_map") is not None:
        return _CACHE["var_map"]
    vm: set = set()
    for name in _LIST_VER:
        try:
            with open(os.path.join(_ROOT, "config", name), encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception:                                      # noqa: BLE001
            continue
        for key in ("var_map", "var_map_addendum"):
            vm |= set(k for k in (d.get(key) or {}) if not str(k).startswith("_"))
    _CACHE["var_map"] = vm
    return vm


def _legal_of_rules(rule_ids: List[str]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """规则号 → 已确证条款（唯一权威 `config/legal_mappings.json`）。"""
    try:
        from engine import legal_mapping as LM                    # noqa: PLC0415
    except Exception:                                          # noqa: BLE001
        return [], []
    provs: List[Dict[str, Any]] = []
    seen = set()
    for rid in rule_ids:
        try:
            for p in LM.provisions_of(rid):
                pid = str(p.get("provision_id") or "")
                if pid and pid in seen:
                    continue
                if pid:
                    seen.add(pid)
                provs.append({"provision_id": pid,
                              "law": str(p.get("law") or ""),
                              "article": str(p.get("article") or ""),
                              "via_rule": rid})
        except Exception:                                      # noqa: BLE001
            continue
    return provs, sorted({p["via_rule"] for p in provs})


def resolve(row: Dict[str, Any], *, list_name: str = "",
            vers: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """单条候选的**处置结论**（版本 / 法规依据 / 数据源缺口 / 入库去向）。"""
    vers = _versions_index() if vers is None else vers
    src = str(row.get("src") or "")
    status = str(row.get("status") or "")
    action = str(row.get("action") or "")
    by = str(row.get("by") or "")
    rule_ids = _RID_RE.findall(by)

    # ① 版本
    reg = vers.get(src) or {}
    if reg.get("version"):
        version, ver_source = str(reg["version"]), "已登记（config/rule_versions.json）"
    else:
        via = next((r for r in rule_ids if (vers.get(r) or {}).get("version")), "")
        if via:
            version = "沿用 %s v%s" % (via, vers[via]["version"])
            ver_source = "跟随所映射的系统规则"
        else:
            version = "%s（未发布）" % (_LIST_VER.get(list_name, "候选"))
            ver_source = "候选清单自身版次"

    # ② 法规依据（只认已确证映射；不按名字猜）
    provs, via_rules = _legal_of_rules(rule_ids)
    if provs:
        basis_status = "determined"
        basis_note = "引自系统内 %s 的已确证条款映射" % "、".join(via_rules)
    elif rule_ids:
        basis_status = "no_mapping"
        basis_note = ("映射到 %s，但该规则在条款关联表里无可确证条款"
                      "（须补 `scripts/_gen_legal_mappings.py` 后再确认）" % "、".join(rule_ids))
    else:
        basis_status = "no_rule"
        basis_note = "系统内无对应规则（`by` 未指向规则号）⇒ 未建立条款映射，须人工核定"

    # ③ 数据源缺口（能不能真执行）
    inputs = [str(x) for x in (row.get("inputs") or [])]
    vm = _var_map()
    missing = [i for i in inputs if i and i not in vm]
    executable = bool(inputs) and not missing

    # ④ 清单状态**过期核对**：`by` 指向的规则号若系统真实存在，则实际已覆盖
    sys_ids = system_rule_ids()
    existing = [r for r in rule_ids if r in sys_ids]
    stale = bool(existing) and status in ("missing", "placeholder")

    # ⑤ 入库去向
    if status == "covered":
        disp, disp_cn = "kept", "已覆盖：沿用现有规则"
    elif status == "partial":
        disp, disp_cn = "merged", "部分覆盖：并入现有规则"
    elif status == "missing":
        disp, disp_cn = ("ready", "可入库：新建检测器") if executable else \
                        ("blocked", "暂不能入库：缺数据源取数口径")
    elif status == "placeholder":
        disp, disp_cn = "pending", "待明确口径后入库"
    else:
        disp, disp_cn = "unknown", "状态未登记（见闸门）"
    if stale:
        disp = "stale_status"
    # ★ 2026-10-20：并入专家裁定（pending/blocked 必有——生成器内做覆盖核对）
    expert = None
    if disp in ("pending", "blocked"):
        v = (adjudications().get("verdicts") or {}).get(src)
        if v:
            expert = {"verdict": v.get("verdict"), "legal": v.get("legal"),
                      "data": v.get("data"), "note": v.get("note")}
        disp_cn = ("清单状态过期：系统已由 %s 实现（清单仍标「%s」，须订正清单）"
                   % ("、".join(existing), candidate_status_cn(status)))

    return {
        "src": src + ("@%s" % _LIST_VER.get(list_name, "") if list_name else ""),
        "rule_id": src,
        "name": str(row.get("name") or ""),
        "list": list_name,
        "list_version": _LIST_VER.get(list_name, ""),
        "severity": str(row.get("sev") or ""),
        "severity_cn": severity_cn(row.get("sev")),
        "status": status,
        "status_cn": candidate_status_cn(status),
        "action": action,
        "action_cn": candidate_action_cn(action),
        "version": version,
        "version_source": ver_source,
        "legal_status": basis_status,
        "legal_provisions": provs,
        "legal_note": basis_note,
        "mapped_rules": rule_ids,
        "inputs": inputs,
        "missing_inputs": missing,
        "executable": executable,
        "expert": expert,
        "disposition": disp,
        "disposition_cn": disp_cn,
        "existing_rules": existing,
        "stale_status": stale,
        "suggestion": str(row.get("suggestion") or ""),
    }


def ledger() -> Dict[str, Any]:
    """全部候选的处置台账（现算；供 API / 生成器 / 闸门共用）。"""
    if _CACHE.get("ledger"):
        return _CACHE["ledger"]
    vers = _versions_index()
    rows: List[Dict[str, Any]] = []
    for name in _LIST_VER:
        p = os.path.join(_ROOT, "config", name)
        if not os.path.exists(p):
            continue
        try:
            with open(p, encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception:                                      # noqa: BLE001
            continue
        for r in (d.get("rules") or []):
            rows.append(resolve(r, list_name=name, vers=vers))
    from collections import Counter
    out = {
        "total": len(rows),
        "by_disposition": dict(Counter(r["disposition"] for r in rows)),
        "by_status": dict(Counter(r["status"] for r in rows)),
        "by_severity": dict(Counter(r["severity"] for r in rows)),
        "by_legal": dict(Counter(r["legal_status"] for r in rows)),
        "executable_n": sum(1 for r in rows if r["executable"]),
        "items": rows,
        "expert_adjudication": _adjudication_summary(),
    }
    _CACHE["ledger"] = out
    return out


def adjudications() -> Dict[str, Any]:
    """专家裁定（唯一权威 `config/rule_adjudications.json`，读盘带缓存）。

    ★ 2026-10-20（用户质问「能接受待建/无法规依据/暂不能入库吗」）：
      机械处置只回答"清单状态"；本裁定是**人工专业核定层**，逐条给出
      「应建 / 线索级 / 需外部数据（缺什么）/ 业务插件 / 重复 / 需表栏次」。
      由 `scripts/_gen_rule_adjudications.py` 生成（176/176 覆盖核对在脚本内）。
    """
    if "adjud" in _CACHE:
        return _CACHE["adjud"]
    path = os.path.join(_ROOT, "config", "rule_adjudications.json")
    d: Dict[str, Any] = {}
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh) or {}
    except Exception as exc:                                   # noqa: BLE001
        d = {"_error": str(exc), "verdicts": {}}
    _CACHE["adjud"] = d
    return d


def _adjudication_summary() -> Dict[str, Any]:
    adj = adjudications()
    verd = adj.get("verdicts") or {}
    from collections import Counter
    return {
        "total": len(verd),
        "by_verdict": dict(Counter(str(x.get("verdict")) for x in verd.values())),
        "by_verdict_cn": dict(Counter(str(adj.get("_verdict_cn", {}).get(
            x.get("verdict"), x.get("verdict"))) for x in verd.values())),
    }


def summary() -> Dict[str, Any]:
    """台账**汇总**（不含逐条，给页面 KPI 用）。"""
    d = ledger()
    return {k: d[k] for k in ("total", "by_disposition", "by_status", "by_severity",
                              "by_legal", "executable_n")}


def enrich(rec: Dict[str, Any]) -> Dict[str, Any]:
    """把中文标签与候选处置结论并入一条规则记录（就地；**候选与真规则都适用**）。"""
    rec["layer_cn"] = layer_cn(rec.get("layer"))
    if rec.get("severity"):
        rec["severity_cn"] = severity_cn(rec.get("severity"))
    if rec.get("source_kind") == "json":
        # 候选：附处置结论（版本/法规依据/数据源缺口/入库去向）
        one = next((x for x in ledger()["items"]
                    if x["rule_id"] == rec.get("rule_id")
                    and x["list"] == str(rec.get("layer") or "")), None)
        # ★ 2026-10-20：附**专家裁定**（待建/暂不能入库的候选必须有专业结论）
        if one and one.get("disposition") in ("pending", "blocked"):
            v = (adjudications().get("verdicts") or {}).get(str(rec.get("rule_id")))
            if v:
                cn = (adjudications().get("_verdict_cn") or {})
                rec["expert"] = {
                    "verdict": v.get("verdict"),
                    "verdict_cn": cn.get(v.get("verdict"), v.get("verdict")),
                    "legal": v.get("legal"),
                    "data": v.get("data"),
                    "note": v.get("note"),
                }
        if one:
            rec["candidate"] = {k: one[k] for k in (
                "status_cn", "action_cn", "severity_cn", "version", "version_source",
                "legal_status", "legal_note", "mapped_rules", "missing_inputs",
                "executable", "disposition", "disposition_cn", "list_version")}
            rec["candidate"]["legal_provisions"] = [
                {"provision_id": p.get("provision_id"), "law": p.get("law"),
                 "article": p.get("article"), "via_rule": p.get("via_rule")}
                for p in (one.get("legal_provisions") or [])]
            # 版本列直接给**已确定**的值（原来恒为「未登记」）
            if not rec.get("version_registered"):
                rec["version"] = one["version"]
                rec["version_source"] = one["version_source"]
            # 法规依据：把占位替换为**已确证条款**（无则如实标注原因）
            if rec.get("legal_basis_placeholder"):
                rec["legal_basis_status"] = one["legal_status"]
                rec["legal_basis_note"] = one["legal_note"]
                if one["legal_provisions"]:
                    rec["legal_basis_determined"] = [
                        {"provision_id": p["provision_id"], "law": p["law"],
                         "article": p["article"], "via_rule": p["via_rule"]}
                        for p in one["legal_provisions"]]
    return rec


__all__ = ["labels", "reset_cache", "layer_cn", "severity_cn", "candidate_status_cn",
           "candidate_action_cn", "layer_options", "resolve", "ledger", "summary",
           "enrich", "_LIST_VER"]
