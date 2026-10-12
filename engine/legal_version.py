# -*- coding: utf-8 -*-
"""法条版本化**单一权威**（用户第 3 批 任务4「法律适用匹配 —— 法条版本化」）。

## 为什么要这一层

外部点评 #5「法律依据引用不够严谨」，本系统实测暴露三类**可机检**缺陷：

  ① **同一部法两套法名**：红线库同时出现「发票管理办法」与「发票管理办法（2023修订）」
     ⇒ 同一部法被当成两部（"一个概念多处维护"的典型；改名时必漏一处）。
  ② **引用不标版本**：正文只写「《发票管理办法》第二十七条」，读者无法判断是不是现行有效；
     而该办法 2023 年已由国务院令第 764 号修订（2023-07-20 施行）。
  ③ **"引用较早"只能靠人工记得**：如《增值税专用发票使用规定》（国税发〔2006〕156 号），
     红字发票流程已改按数电票红字确认单规则执行。

## 口径（与项目铁律一致，禁默认值顶替）

- 版本信息**只有一处权威**：`config/legal_versions.json`（人工维护、可复核、可版本化回滚）。
- **未登记 ≠ 现行有效**：未登记的引用一律标注「版本未登记，须核对现行有效文本」，
  绝不静默按"现行有效"处理；闸门统计未登记法名数量（可见、可收敛）。
- `status` 只取 `STATUSES`；`superseded`/`expired` 的条目**一经引用即由闸门拦下**。
- `effective_from` 取不到就写 `null`（**不臆造日期**）。
- 法名归一 `canonical_law()`：去掉法名里的**版本括注**（「（2023修订）」「（2019年修正）」），
  **保留**文号括注（「（国家税务总局公告2018年第28号）」是法名的一部分，不是版本）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent
_REG_PATH = _ROOT / "config" / "legal_versions.json"

#: 版本状态枚举（★ 唯一权威；新增状态只改这一行 + `STATUS_CN`）
STATUSES: Tuple[str, ...] = ("current", "amended", "superseded", "expired", "unknown")

STATUS_CN: Dict[str, str] = {
    "current": "现行有效",
    "amended": "已修订（引用条文须核对是否落在现行版本内）",
    "superseded": "已被新法取代",
    "expired": "已失效",
    "unknown": "版本未登记",
}

#: 引用**现行版本已失效/被取代**的法条时，闸门直接拦下的状态
BLOCKING_STATUSES: Tuple[str, ...] = ("superseded", "expired")

#: 本系统最常引用、且点评点名的核心法（**必须**登记版本；未登记 ⇒ 闸门 ERROR）
CORE_LAWS: Tuple[str, ...] = (
    "税收征收管理法",
    "企业所得税法",
    "企业所得税法实施条例",
    "个人所得税法",
    "发票管理办法",
    "社会保险法",
    "住房公积金管理条例",
    "印花税法",
    "增值税暂行条例",
    "会计法",
)

#: 法名里的**版本括注**（只认"修订/修正/年版/版"语义；**不认**文号括注）
_VERSION_NOTE_RE = re.compile(
    r"[（(][^（）()]{0,16}?(?:修订|修正|年版|第[一二三四五六七八九十\d]+版)[^（）()]{0,16}?[）)]"
)
#: 纯"（试行）"类**属于法名本身**，不得剥除（如《股权转让所得个人所得税管理办法（试行）》）
_KEEP_TITLE_NOTE = ("试行", "暂行", "草案")

# ★★ 2026-10-13（T-5 第二阶段实测根因）：**同一部法两套法名**必须归一。
#   `_VERSION_NOTE_RE` 明确"不认文号括注"（见其上注释），但这导致：
#     · 引用写「企业所得税核定征收办法（国税发〔2008〕30号）」，登记表存「企业所得税核定征收办法」
#       ⇒ 归一结果不同 ⇒ 被当成**另一部法** ⇒ 法条版本闸门报"未登记"（**假缺口**）。
#     · 引用只写文号（「财税〔2003〕158号」），登记表存全称 ⇒ 同样失配。
#   实测：39 个"未登记法名"中 **18 个**属此类（占 46%）。
#   ⇒ 修法：从登记表自身的 `source` 字段**派生**「文号 → 登记法名」别名表
#     （单一权威：别名不另存一份，随登记表自动同步，**不可能漂移**）。
_WENHAO_RE = re.compile(
    r"(财税\s*〔\d{4}〕\s*\d+\s*号"
    r"|国税发\s*〔\d{4}〕\s*\d+\s*号"
    r"|财综\s*〔\d{4}〕\s*\d+\s*号"
    r"|国家税务总局公告\s*\d{4}\s*年第\s*\d+\s*号"
    r"|财政部\s*税务总局公告\s*\d{4}\s*年第\s*\d+\s*号"
    r"|财政部\s*国家税务总局公告\s*\d{4}\s*年第\s*\d+\s*号"
    r"|国务院令第\s*\d+\s*号"
    r"|国令第\s*\d+\s*号)"
)
#: **尾部说明型/文号型括注**（≥6 字，且**不**含"试行/暂行/草案"）⇒ 归一法名时剥除。
#: 例：「（国家税务总局公告2014年第67号）」「（引用较早，具体适用须按…复核）」。
_TRAIL_NOTE_RE = re.compile(r"[（(][^（）()]{6,}[）)]\s*$")

_REG_KEYS_CACHE: Optional[frozenset] = None
_ALIAS_CACHE: Optional[Dict[str, str]] = None


def _norm_wh(s: str) -> str:
    """文号归一（去空白），使「财税〔2008〕121 号」与「财税〔2008〕121号」等价。"""
    return re.sub(r"\s+", "", str(s or ""))


def _base_key(law: str) -> str:
    """登记名的基础归一（**不含**别名解析，避免自引用）。"""
    return _norm_law(_VERSION_NOTE_RE.sub("", str(law or "")))


def _registered_keys() -> frozenset:
    global _REG_KEYS_CACHE
    if _REG_KEYS_CACHE is None:
        _REG_KEYS_CACHE = frozenset(_base_key(e.get("law") or "") for e in registry_entries())
    return _REG_KEYS_CACHE


def _wenhao_alias_index() -> Dict[str, str]:
    """**文号 → 登记法名**（从登记表 `source` 字段派生；不含独立数据文件 ⇒ 不会漂移）。"""
    global _ALIAS_CACHE
    if _ALIAS_CACHE is None:
        idx: Dict[str, str] = {}
        for e in registry_entries():
            base = _base_key(e.get("law") or "")
            for wh in _WENHAO_RE.findall(str(e.get("source") or "")):
                idx.setdefault(_norm_wh(wh), base)
        _ALIAS_CACHE = idx
    return _ALIAS_CACHE


def _resolve_alias(s: str) -> Optional[str]:
    for wh in _WENHAO_RE.findall(s):
        hit = _wenhao_alias_index().get(_norm_wh(wh))
        if hit:
            return hit
    return None


def reset_caches() -> None:
    """清空登记表与别名缓存（测试/登记表变更后调用）。"""
    global _REG_CACHE, _ISSUES_CACHE, _REG_KEYS_CACHE, _ALIAS_CACHE
    _REG_CACHE = None
    _ISSUES_CACHE = None
    _REG_KEYS_CACHE = None
    _ALIAS_CACHE = None


_REG_CACHE: Optional[Dict[str, Any]] = None
_ISSUES_CACHE: Optional[List[Tuple[str, str, str]]] = None


def _norm_law(s: str) -> str:
    return re.sub(r"\s+", "", str(s or "").replace("《", "").replace("》", "")
                  .replace("中华人民共和国", ""))


def canonical_law(law: str) -> str:
    """法名归一（★ 唯一权威）：去《》、去"中华人民共和国"、去版本括注、**文号↔全称归一**、去空白。

    ★ 保留"（试行）/（暂行）"类括注 —— 那是法名的组成部分，去掉会与正式法混淆。

    ★★ 2026-10-13（T-5 第二阶段）：新增**文号归一**，解决"同一部法两套法名"：
      ① 已是登记名 ⇒ 原样返回（避免把文号型登记名改写成别的法）；
      ② 串内出现**已登记文号** ⇒ 返回该文号对应的登记法名（如「财税〔2003〕158号」→ 全称）；
      ③ 否则剥**尾部说明型/文号型括注**后重试（如「…办法（国税发〔2008〕30号）」→「…办法」）。
    实测效果：39 个"未登记法名"中 18 个为假缺口，据此消解。
    """
    s = _base_key(law)
    if not s:
        return s
    reg = _registered_keys()
    # ① 已是登记名（含"国家税务总局公告2014年第39号"这类以文号为名的登记项）
    if s in reg:
        return s
    # ② 串内含已登记文号 ⇒ 归一为全称法名
    hit = _resolve_alias(s)
    if hit:
        return hit
    # ③ 剥尾部说明型/文号型括注后重试
    s2 = _TRAIL_NOTE_RE.sub("", s).strip()
    if s2 and s2 != s:
        if s2 in reg:
            return s2
        hit2 = _resolve_alias(s2)
        if hit2:
            return hit2
        return s2
    return s


def has_version_in_name(law: str) -> bool:
    """法名里是否**写了版本**（写了 ⇒ 版本信息被塞进法名，属"多头维护"缺陷）。"""
    return bool(_VERSION_NOTE_RE.search(str(law or "")))


def _load_registry() -> Dict[str, Any]:
    global _REG_CACHE
    if _REG_CACHE is not None:
        return _REG_CACHE
    try:
        _REG_CACHE = json.loads(_REG_PATH.read_text(encoding="utf-8"))
    except Exception:
        _REG_CACHE = {"schema": 0, "laws": []}
    if not isinstance(_REG_CACHE, dict):
        _REG_CACHE = {"schema": 0, "laws": []}
    return _REG_CACHE


def registry_entries() -> List[Dict[str, Any]]:
    return [e for e in (_load_registry().get("laws") or []) if isinstance(e, dict)]


def _law_index() -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for e in registry_entries():
        k = canonical_law(e.get("law") or "")
        if k:
            out.setdefault(k, e)
    return out


def entry_of(law: str) -> Optional[Dict[str, Any]]:
    """取某法名的登记项（找不到 ⇒ None ⇒ 视为"版本未登记"）。"""
    return _law_index().get(canonical_law(law))


def status_of(law: str) -> str:
    e = entry_of(law)
    st = str((e or {}).get("status") or "unknown").strip()
    return st if st in STATUSES else "unknown"


def is_current(law: str) -> bool:
    return status_of(law) == "current"


def version_note(law: str) -> str:
    """给出**可直接放进报告的版本括注**（未登记 ⇒ 如实说明，不默认现行有效）。"""
    e = entry_of(law)
    if not e:
        return "（版本未登记，须核对现行有效文本）"
    st = status_of(law)
    ver = str(e.get("current_version") or "").strip()
    src = str(e.get("source") or "").strip()
    parts = [p for p in (ver, src) if p]
    head = "；".join(parts) if parts else "未登记版本信息"
    tail = STATUS_CN.get(st, st)
    extra = str(e.get("note") or "").strip()
    return "（%s，%s%s）" % (head, tail, ("；" + extra) if extra else "")


def registered_laws() -> List[str]:
    return sorted(_law_index().keys())


def unregistered_core_laws() -> List[str]:
    idx = _law_index()
    return [l for l in CORE_LAWS if canonical_law(l) not in idx]


def is_blocking(law: str) -> bool:
    """该法名的版本状态是否**禁止引用**（已被取代/失效）。"""
    return status_of(law) in BLOCKING_STATUSES


def audit_registry() -> List[str]:
    """登记表自身的完整性检查，返回问题描述列表（空 = 合规）。

    判据：① schema 齐备；② 每条必须有 `law`/`current_version`/`source`/`status`；
    ③ `status` ∈ STATUSES；④ `effective_from` 非空时必须是 ISO `YYYY-MM-DD` 且已生效；
    ⑤ 归一后的法名**不得重复**（重复 ⇒ 同一部法两处登记，必然漂移）；
    ⑥ 核心法（`CORE_LAWS`）必须登记。
    """
    probs: List[str] = []
    reg = _load_registry()
    if int(reg.get("schema") or 0) < 1:
        probs.append("登记表 schema 缺失或版本过低")
    seen: Dict[str, int] = {}
    import datetime as _dt
    today = _dt.date.today().isoformat()
    for i, e in enumerate(registry_entries()):
        law = str(e.get("law") or "").strip()
        if not law:
            probs.append("第 %d 条缺 law" % (i + 1))
            continue
        if has_version_in_name(law):
            probs.append("法名「%s」把版本写进了法名（版本只应登记在本表）" % law)
        for f in ("current_version", "source", "status"):
            if not str(e.get(f) or "").strip():
                probs.append("「%s」缺字段 %s" % (law, f))
        st = str(e.get("status") or "").strip()
        if st and st not in STATUSES:
            probs.append("「%s」status=%s 不在枚举内" % (law, st))
        ef = e.get("effective_from")
        if ef is not None:
            s = str(ef).strip()
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
                probs.append("「%s」effective_from=%s 非 ISO 日期" % (law, s))
            elif s > today:
                probs.append("「%s」effective_from=%s 晚于今日" % (law, s))
        k = canonical_law(law)
        if k in seen:
            probs.append("法名「%s」与第 %d 条归一后重复（同一部法两处登记）" % (law, seen[k] + 1))
        else:
            seen[k] = i
    for l in unregistered_core_laws():
        probs.append("核心法「%s」未登记版本" % l)
    return probs


def audit_citations(citations) -> List[str]:
    """检查一批引用（法名 / 「《法名》第X条」字符串）的版本合规性。

    返回问题描述（空 = 合规）。判据：
      · 引用现行版本**已被取代/失效**的法 ⇒ 阻断；
      · 法名里写了版本 ⇒ 阻断（同一部法两套法名）。
    """
    from engine.legal_citation import split_citation  # 薄转发，不另写解析
    probs: List[str] = []
    if isinstance(citations, str):
        citations = [citations]
    for c in (citations or []):
        if not isinstance(c, str):
            continue
        law, _art, _note, _content = split_citation(c)
        law = law or c
        if has_version_in_name(law):
            probs.append("法名「%s」把版本写进了法名（应统一法名 + 版本登记）" % law)
        if is_blocking(law):
            probs.append("引用了%s的法条：%s" % (STATUS_CN.get(status_of(law), ""), c[:60]))
    return probs


__all__ = [
    "STATUSES", "STATUS_CN", "BLOCKING_STATUSES", "CORE_LAWS",
    "canonical_law", "has_version_in_name", "registry_entries", "entry_of",
    "status_of", "is_current", "version_note", "registered_laws",
    "unregistered_core_laws", "is_blocking", "audit_registry", "audit_citations",
]


# ═══════════════════════════════════════════════════════════════════════════
# 报告级薄转发（阶段9 第3项「法规版本管理器」的报告装配接口）
# ★ 本段**不实现**任何版本判定逻辑，全部转发到上面的唯一权威函数，
#   避免"版本口径两处实现必然漂移"。
# ═══════════════════════════════════════════════════════════════════════════
_LAW_NAME_RE = re.compile(r"《([^》]{2,60})》")
_LAW_HINT_RE = re.compile(r"法$|条例|办法|规定|通知|决定|公告|细则|解释|批复|暂行|法实施")


def extract_law_names(texts) -> List[str]:
    """从文本中抽法规名（过滤表单名/刊物名等非法规）。"""
    seen: List[str] = []
    for t in texts:
        for m in _LAW_NAME_RE.finditer(str(t or "")):
            nm = m.group(1)
            if _LAW_HINT_RE.search(nm) and nm not in seen:
                seen.append(nm)
    return seen


def annotate_report(report_data) -> Dict[str, Any]:
    """给报告引用的每条法规打上 版本/生效日期/现行有效性；返回待核与拦截清单。

    版本信息**一律取自登记表**（`config/legal_versions.json`）；
    未登记 ⇒ 标『版本待核』，绝不当成现行有效；superseded/expired ⇒ 拦截。
    """
    texts: List[str] = []
    if isinstance(report_data, dict):
        for k, v in report_data.items():
            if isinstance(v, str):
                texts.append(v)
        # ★ 2026-10-08：改用**报告层统一取数**（原先直取顶层 confirmed_problems ⇒ 实测恒为空，
        #   导致"法规引用 0 条"）。薄转发 report_items，不重复实现口径。
        try:
            from engine.report_pipeline import report_items as _ri
            _items_lv = _ri(report_data)[:50]
        except Exception:
            _items_lv = (report_data.get("confirmed_problems") or [])[:50]
        for it in _items_lv:
            if isinstance(it, dict):
                texts.extend(str(it.get(kk) or "") for kk in ("law_basis", "conclusion", "reason",
                                                               "verdict", "risk_level_basis", "suspect"))
                # ★ 法规引用实际落在叙述段与明细表里（不是单一 law_basis 字段）⇒ 必须一并扫描，
                #   否则"法规引用 0 条"（实测踩过）。
                for _x in (it.get("narrative_paragraphs") or []):
                    if isinstance(_x, dict) and _x.get("text"):
                        texts.append(str(_x["text"]))
                    elif isinstance(_x, str):
                        texts.append(_x)
                for _x in (it.get("missing_materials") or []) + (it.get("missing_material_names") or []):
                    if isinstance(_x, str):
                        texts.append(_x)
                _dt = it.get("detail_table")
                if isinstance(_dt, dict):
                    for _v in _dt.values():
                        if isinstance(_v, list):
                            for _r in _v[:20]:
                                if isinstance(_r, dict):
                                    texts.extend(str(x) for x in _r.values() if isinstance(x, str))

    anns: List[Dict[str, Any]] = []
    for nm in extract_law_names(texts):
        canon = canonical_law(nm)
        ent = entry_of(nm) or {}
        st = status_of(nm)
        anns.append({
            "law": canon or nm,
            "as_cited": nm,
            "status": st,
            "version_note": version_note(nm),
            "current_version": ent.get("current_version"),
            "effective_from": ent.get("effective_from"),   # 取不到为 None，不臆造
            "source": ent.get("source"),
            "registered": bool(ent),
            "blocking": bool(is_blocking(nm)),
        })
    pending = [a for a in anns if (not a["registered"]) or a["status"] == "unknown"]
    blocking = [a for a in anns if a["blocking"]]
    return {
        "annotations": anns,
        "pending": pending,
        "blocking": blocking,
        "summary": (f"法规引用 {len(anns)} 条；版本待核 {len(pending)} 条；"
                    f"已失效/被替代（拦截）{len(blocking)} 条"),
        "principle": "未登记一律标『版本待核』，不作现行有效；superseded/expired 引用即拦下",
    }


def pending_list() -> List[Dict[str, Any]]:
    """未登记的核心法规（供报告 CH6 与待核清单直接引用）。"""
    return [{"law": nm, "status": "unknown", "status_cn": "版本待核"} for nm in unregistered_core_laws()]
