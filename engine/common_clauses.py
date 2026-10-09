# -*- coding: utf-8 -*-
"""报告级**通用口径**上提（P0-7 唯一权威）。

## 要解决的问题（用户复核 2026-10-08）
正文里有 33 种**非数值模板句**跨章节重复，最长重复 13 次
（如「补充资料之前既不认定违法，也不予排除」×11、「是否成立，另按本项构成要件逐条核对」×13）。
原有的三项重复率判据**都抓不到**：
  · 整体 / 同章节 —— 只看**段落级**相似，而模板句藏在段内，段与段并不相似；
  · 同一事实 —— 只认**含 ≥5 位数值锚点**的句子。
⇒ 「跨章节 + 非数值 + 句子级」这一格无人守。

这些句子绝大多数是**报告级通用口径**：对每个事项一字不差成立，本不该逐条复述。
故**止血办法＝上提**：按 `config/common_clauses.json` 从各事项正文移除，在报告级只说一次。

## 与其它模块的分工（不得互相替代，也不得重复实现）
  · `engine/report_dedup`  —— **报告文体**特有的元话语删除 / 共性段与共性句上提（逐字重复驱动，自动发现）。
  · `engine/common_clauses`（本模块） —— **登记表驱动**的报告级通用口径上提（口径已知，按表移除）。
  · `engine/dedup_pipeline` —— 通用六类重复 + **重复率四项判据**（含『跨章节模板句』，以本表为白名单）。
  · `config/dedup_rules.json::necessary_repeat` —— 必要重复（结构/格式/引用/明细行）。

## 可见性铁律
`common_clauses` 是**机器口径登记表**（闸门读取），`report_statement` 才是**渲染器唯一消费点**
（前端 `static/js/tax-doc-analysis.js` 渲染为「五、报告性质和使用说明」）。
⇒ 上提时**同时**写入 `report_statement`，否则"去重"就等于"把话删掉了"。
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CFG = os.path.join(_ROOT, "config", "common_clauses.json")
_CACHE: Optional[Dict[str, Any]] = None

VERSION = "1.0.0"


def load_registry(force: bool = False) -> Dict[str, Any]:
    """读登记表（缺文件/坏文件返回空表，调用方据此退化为"不上提"，绝不臆造口径）。"""
    global _CACHE
    if _CACHE is None or force:
        try:
            with open(_CFG, "r", encoding="utf-8") as fh:
                _CACHE = json.load(fh)
        except Exception:  # noqa: BLE001
            _CACHE = {}
    return _CACHE


def _compiled(key: str) -> List[Tuple[str, "re.Pattern"]]:
    """`(clause_id, 编译后的正则)` 列表 —— 登记表 → 判据的唯一转换点。"""
    out: List[Tuple[str, "re.Pattern"]] = []
    for c in (load_registry().get(key) or []):
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id") or "")
        for pat in (c.get("match") or []):
            try:
                out.append((cid, re.compile(pat)))
            except re.error:                      # 坏正则不得静默吞掉整条登记项
                print("[通用口径] 登记项 %s 的正则非法，已跳过：%r" % (cid, pat))
    return out


def hoist_rules() -> List[Tuple[str, "re.Pattern"]]:
    """**报告级通用口径**判据（应上提）。"""
    return _compiled("hoist")


def necessary_rules() -> List[Tuple[str, "re.Pattern"]]:
    """**形似但指代各事项自身**的句子判据（保留在原地，登记理由备查）。"""
    return _compiled("necessary")


def clause_text(clause_id: str) -> str:
    """登记项的报告级表述文本（用于写入 `report_statement`）。"""
    for c in (load_registry().get("hoist") or []):
        if isinstance(c, dict) and str(c.get("id")) == clause_id:
            return str(c.get("text") or "")
    return ""


def section_title() -> str:
    return str((load_registry().get("section") or {}).get("title") or "报告性质和使用说明")


def _key(text: Any) -> str:
    """判据比对键 —— **薄转发唯一权威** `engine.report_dedup.cmp_key`（去强调符/空白/句末符）。

    为什么必须转发而不是自写：同一条判据（"这句是不是登记在册的通用口径"）的两侧文本
    来自不同来源（登记表写的正则 vs 报告正文的句子），字面比对必然因空白/标点差异漏配。
    """
    try:
        from engine.report_dedup import cmp_key as _ck
        return _ck(text)
    except Exception:                             # noqa: BLE001
        return re.sub(r"[\s\u3000]+", "", str(text or "")).strip()


def _match_clause(sent_key: str, rules: List[Tuple[str, "re.Pattern"]]) -> Optional[str]:
    for cid, rx in rules:
        if rx.search(sent_key):
            return cid
    return None


def is_registered_clause(sent: Any) -> bool:
    """该句是否为**已登记的报告级通用口径**（应上提）——闸门白名单判据。"""
    k = _key(sent)
    return bool(k) and _match_clause(k, hoist_rules()) is not None


def is_necessary_template(sent: Any) -> bool:
    """该句是否为**已登记的必要模板**（形似但指代各事项自身）——闸门白名单判据。"""
    k = _key(sent)
    return bool(k) and _match_clause(k, necessary_rules()) is not None


def _split_keep(text: Any) -> List[str]:
    """切句且保留句末分隔符（薄转发 `engine.report_dedup._split_keep`，可原样回拼）。"""
    try:
        from engine.report_dedup import _split_keep as _sk
        return list(_sk(text) or [])
    except Exception:                             # noqa: BLE001
        return []


def _has_payload(para: Any) -> bool:
    """段落是否带用户可见载荷（薄转发 `engine.report_dedup.has_visible_payload`）。"""
    try:
        from engine.report_dedup import has_visible_payload as _hp
        return bool(_hp(para))
    except Exception:                             # noqa: BLE001
        return False


def _strip_clauses(text: str, rules: List[Tuple[str, "re.Pattern"]],
                   hit_ids: List[str]) -> Tuple[str, int]:
    """从一段正文中移除命中登记项句子（保留其余原文与标点）。返回 (新文本, 移除句数)。"""
    pieces = _split_keep(text)
    if not pieces:
        return text, 0
    keep: List[str] = []
    removed = 0
    for p in pieces:
        cid = _match_clause(_key(p), rules)
        if cid:
            hit_ids.append(cid)
            removed += 1
            continue
        keep.append(p)
    return "".join(keep).strip(), removed


def hoist_common_clauses(report_data: Any) -> Dict[str, Any]:
    """按登记表把**报告级通用口径**从各事项正文移除，并在报告级只留一份。

    返回 `{"hoisted": 移除句数, "clauses": [命中的 clause_id...], "paragraphs_dropped": n}`。
    幂等：第二次调用不会重复移除，也不会重复登记（按 id 去重）。

    边界（必须守住）：
      · **只移除登记在册的句子**，不改写任何本项特有的事实、金额、资料名、结论；
      · 段落正文被移除后若变空、但带用户可见载荷（bullets/明细表/尾注）⇒ **保留该段**
        （载荷是本项专属内容，删掉即"用户可见内容真丢"）；
      · 正文与载荷全空 ⇒ 才丢弃该段（不留空标题）；
      · 上提的文本**同时**写入 `report_statement`（渲染器唯一消费点），确保企业看得见。
    """
    stat: Dict[str, Any] = {"hoisted": 0, "clauses": [], "paragraphs_dropped": 0}
    if not isinstance(report_data, dict):
        return stat
    hoist = hoist_rules()
    if not hoist:
        return stat
    # ★★ 2026-10-09 实测事故（本模块第一版）：取数与落点都取错层 ——
    #   读的是 `report_data["confirmed_problems"]`（**顶层**，实测不存在），
    #   写的是 `report_data["report_statement"]`（**顶层**）。
    #   而正文条目在 `enterprise_readable_report.confirmed_problems`，
    #   前端读的是 `r.enterprise_readable_report.report_statement`
    #   （`static/js/tax-doc-analysis.js:5678`）⇒ **上提恒为 0 句、写了也没人看得见**
    #   （pipeline_log 实测留痕：「上提 0 句（登记项 0 个）」，闸门同时读不到 ⇒ 双盲）。
    #   现：容器与条目一律走**唯一权威** `engine/report_metrics`。
    from engine.report_metrics import report_surface_container, report_surface_items
    container = report_surface_container(report_data)
    problems = report_surface_items(report_data)
    if not isinstance(problems, list) or not problems:
        return stat

    hit_ids: List[str] = []
    for pr in problems:
        if not isinstance(pr, dict):
            continue
        kept: List[dict] = []
        for para in (pr.get("narrative_paragraphs") or []):
            if not isinstance(para, dict):
                kept.append(para)
                continue
            before = str(para.get("text") or "")
            after, n_rm = _strip_clauses(before, hoist, hit_ids)
            para["text"] = after
            stat["hoisted"] += n_rm
            # 载荷里的条目同样可能是通用口径（如补件清单里的通用要求），一并收敛。
            bl = para.get("bullets")
            if isinstance(bl, list) and bl:
                nb: List[Any] = []
                n_bullet_rm = 0
                for b in bl:
                    bid = _match_clause(_key(b), hoist)
                    if bid:
                        hit_ids.append(bid)
                        n_bullet_rm += 1
                        continue
                    nb.append(b)
                if n_bullet_rm:
                    stat["hoisted"] += n_bullet_rm
                    para["bullets"] = (nb or None)
            if after or _has_payload(para):
                kept.append(para)
            else:
                stat["paragraphs_dropped"] += 1
        pr["narrative_paragraphs"] = kept

    # 登记（按 id 去重、与既有合并 ⇒ 幂等）：只在**确有命中**时登记，报告不出现空登记。
    order: List[str] = []
    for cid in hit_ids:
        if cid and cid not in order:
            order.append(cid)
    existing = container.get("common_clauses")
    merged: List[dict] = [c for c in (existing or []) if isinstance(c, dict)]
    seen = {str(c.get("id")) for c in merged}
    for cid in order:
        if cid in seen:
            continue
        txt = clause_text(cid)
        if not txt:
            continue
        merged.append({"id": cid, "text": txt, "section": section_title()})
        seen.add(cid)
    container["common_clauses"] = merged
    stat["clauses"] = order

    # ★★ 可见性：渲染器只消费 `report_statement`（前端渲染为「五、报告性质和使用说明」），
    #   且**读的是承载条目那一层的** `report_statement`
    #   （`static/js/tax-doc-analysis.js:5678`：`r.enterprise_readable_report.report_statement`）
    #   ⇒ 必须写进同一个容器，否则上提等于删内容（企业无处对照）。
    #   ⚠ 第一版把 `report_statement` 写到顶层 `report_data` ⇒ 前端取不到（写了个寂寞）。
    rs = container.get("report_statement")
    rs = list(rs) if isinstance(rs, list) else []
    for c in merged:
        t = str(c.get("text") or "").strip()
        if t and t not in rs:
            rs.append(t)
    container["report_statement"] = rs
    return stat
