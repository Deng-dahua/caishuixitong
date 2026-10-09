# -*- coding: utf-8 -*-
"""去重流水线（唯一权威实现）——把「报告去重」从脚本固化为可被产出链调用的引擎能力。

**为什么需要本模块**：去重逻辑原只存在于 `scripts/_phase5_dedup.py`（一次性脚本），
产出链无法调用 ⇒ 每次仍要人工跑脚本（违反指令「不再依赖人工提醒」）。
本模块提供稳定 API，`scripts/_phase5_dedup.py` 与产出链都调用它，避免两处实现漂移。

四类处置（判据全部来自 `config/dedup_rules.json`）：
  1. 套话/前缀套话 → 替换为「（见声明S-xx）」引用
  2. 完全重复（归一化后字面相同）→ 保留首次，其余删除
  3. 近似重复（段落级相似度 ≥ 阈值）→ 保留首次，其余删除
  4. 事实重复（同一数值所在的**高度相似句子**）→ 保留首次完整陈述，其余改为「（见事实Rn-Fxx）」
  5. 段内重复（模式化，如「（本表 N 行，金额合计 X 元）」）→ 删除重复括号

相似度判定一律走 `engine/dupkit.py`（唯一实现），本模块不自行实现相似度。

★ **与 `engine/report_dedup.py` 的分工**（两者不可互相替代，也不重复实现）：
  · `report_dedup`（skill `report_dedup` v1.1.0）：**报告文体特有**的元话语删除、
    共性段上提（`_HOISTABLE_HEADS`）、表注去重 —— 面向「报告怎么排版才不啰嗦」。
  · `dedup_pipeline`（本模块）：**通用六类重复**（套话/完全/近似/事实/段内）+ **重复率阻断** ——
    面向「同一事实是否在多处完整陈述」与「超阈不得输出」。
  · 两者共用 `engine/dupkit.py` 的相似度判定，**不各自实现相似度**。
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from engine import dupkit

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CFG = os.path.join(_ROOT, "config", "dedup_rules.json")
_CACHE: Optional[Dict[str, Any]] = None

RE_AMOUNT = re.compile(r"(?<!\d)\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<!\d)\d{5,}(?:\.\d+)?")


def load_rules() -> Dict[str, Any]:
    """读判据配置（与 dupkit 同源同一份文件，不另存副本）。"""
    global _CACHE
    if _CACHE is None:
        try:
            with open(_CFG, "r", encoding="utf-8") as fh:
                _CACHE = json.load(fh)
        except Exception:  # noqa: BLE001 —— 交给调用方判断空配置
            _CACHE = {}
    return _CACHE


def _necessary_res() -> List[re.Pattern]:
    pats = (load_rules().get("necessary_repeat") or {}).get("patterns") or []
    return [re.compile(p["regex"]) for p in pats]


def is_table_data_row(txt: str) -> bool:
    """明细表数据行：以 | 首尾且至少一个单元格有非空内容（排除空表行与分隔行）。"""
    t = str(txt or "").strip()
    if not (t.startswith("|") and t.endswith("|")):
        return False
    cells = [c.strip().strip("-:") for c in t.strip("|").split("|")]
    return any(cells)


#: 引用语（含去重替换语、交叉引用串）——用于判定"近纯引用块"。
#  ★★ 2026-10-08（P0-2 根因治理）：**薄转发唯一权威** `engine.reference.REF_TOKEN_RE`。
#    本项目实测同一"引用串形态"曾在 6 处各写一遍；本处原先自持一条
#    `[〔(（]见[^〕)）]{1,24}[〕)）]`（*只认带括号的*）—— 与生成侧/识别侧口径不同源，
#    裸串「见疑点R4」在本处**不被剥除** ⇒ "近纯引用块"判定失效（假冗余）。
#    现改为懒加载唯一权威（避免 reference↔dedup_pipeline 模块级循环导入），并保留
#    原正则作**兜底**（取不到权威时不至于把引用块当冗余算）。
_RE_REF_ANY: Optional[re.Pattern] = None
_RE_REF_FALLBACK = re.compile(r"[〔(（]见[^〕)）]{1,24}[〕)）]")


def _ref_any_re() -> "re.Pattern":
    global _RE_REF_ANY
    if _RE_REF_ANY is None:
        try:
            from engine.reference import REF_TOKEN_RE as _rt
            _RE_REF_ANY = _rt
        except Exception:  # noqa: BLE001
            _RE_REF_ANY = _RE_REF_FALLBACK
    return _RE_REF_ANY


#: 各类「必要重复」的判据来源（★ 单一入口登记，闸门据此断言"没有第二套豁免"）。
#: 顺序即短路顺序；每一元 = (来源说明, 判定函数)。
def _necessary_sources():
    """**必要重复**各来源的判定函数（懒加载，避免模块级循环导入）。

    ★★ 2026-10-09（P1-3 判据同口径根因治理）：同一概念「这段文字属必要重复、不计冗余」
      此前有**三处各写一套**：
        ① `dedup_pipeline.is_necessary` + `config/dedup_rules.json::necessary_repeat`
           —— 只服务 `duplicate_rate` 的四项判据；
        ② `common_clauses` 登记表（`is_registered_clause` / `is_necessary_template`）
           —— 只服务『跨章节模板句』一项；
        ③ `report_pipeline.non_dedupable_values`（逐项结论/口径字段）
           —— 只服务模板整洁门禁 D5。
      ⇒ 实测后果：同一个「逐项结论句」「报告级通用口径」在 A 判据被豁免、在 B 判据被计为
        冗余，闸门之间互相假红；且『跨章节模板句』把**逐项结论句**（各事项主体不同）判为模板。
      现收敛为**单一入口本函数**：调用方一律只问 `is_necessary()`，
      由它依次询问各**登记表**（登记表仍是各自数据的唯一权威，本函数只做汇聚）。
    """
    out = []
    try:
        from engine.common_clauses import is_registered_clause, is_necessary_template
        out.append(("common_clauses 登记表（报告级通用口径 + 必要模板）",
                    lambda s: is_registered_clause(s) or is_necessary_template(s)))
    except Exception:  # noqa: BLE001 —— 取不到登记表不得静默：留痕由调用方 stats 承载
        pass
    return out


def is_necessary(txt: str) -> bool:
    """必要重复白名单（结构/格式/引用/明细数据行/**已登记口径**）——不参与去重、不计冗余。

    ★ 调用方（`duplicate_rate` 四项判据、模板整洁门禁）**只经本函数**判定"是否豁免"，
      不得再各自维护第二套豁免（详见 `_necessary_sources` 的根因说明）。

    ★★ 2026-10-09（防"过宽豁免"）：登记表判据（`common_clauses` 的 `^…` 前缀式）对
      **多句段落**若整块套用，会把"仅以登记口径开头、其余是本项特有内容"的长段整体豁免
      ⇒ 真冗余被藏住。故多句段落要求**逐句**都能命中登记口径才豁免；单句文本照旧。
    """
    if is_table_data_row(txt):
        return True
    s = str(txt or "")
    # ★ 2026-10-08（条款 A5）：**近纯引用块**视为必要重复。
    #   句子级去重会把"同一事实的重复句"替换为引用语（「见疑点Rn」）；若某块只剩引用语，
    #   块与块之间必然字面相同 —— 那是**引用格式**（指令要求），不是冗余陈述。
    #   （配置里的『交叉引用串/去重引用语』regex 要求**整行**是引用，覆盖不到
    #     "引用语夹在段中/多段引用组合"的情形，故此处按"去掉引用后是否还有实质内容"判定。）
    if len(_ref_any_re().sub("", s).strip()) < 6:
        return True
    if any(rx.search(s) for rx in _necessary_res()):
        return True
    srcs = _necessary_sources()
    if not srcs:
        return False
    try:
        from engine.dupkit import split_sentences as _ss
        sents = [str(x) for x in _ss(s, keep_delim=False) if str(x).strip()]
    except Exception:  # noqa: BLE001 —— 切句不可用 ⇒ 不臆断，退回整块判定
        sents = []
    if len(sents) <= 1:
        return any(fn(s) for _desc, fn in srcs)
    return all(any(fn(x) for _desc, fn in srcs) for x in sents)


def boilerplate_index() -> Tuple[Dict[str, str], List[Tuple[str, str]]]:
    """套话 → 声明编号 的映射（供替换为引用）。"""
    bp = load_rules().get("boilerplate") or {}
    exact = {str(t): f"S-{i + 1:02d}" for i, t in enumerate(bp.get("exact") or [])}
    pref = [(str(p), f"S-{len(exact) + i + 1:02d}") for i, p in enumerate(bp.get("prefix") or [])]
    return exact, pref


# ---------------------------------------------------------------- 逐段去重
def dedup_paragraph(text: str, seen_norm: Dict[str, str], seen_paras: List[Tuple[str, str]],
                    *,
                    where: str = "", rules: Optional[Dict[str, Any]] = None) -> Tuple[Optional[str], List[dict]]:
    """对**单个段落**做去重。返回 (输出文本或 None=丢弃, 处理记录)。"""
    R = rules or load_rules()
    log: List[dict] = []
    t = str(text or "").strip()
    if not t or is_necessary(t):
        return (t or None), log

    exact, pref = boilerplate_index()
    for b, sno in exact.items():
        if t == b or dupkit.norm(t) == dupkit.norm(b):
            log.append({"type": "套话重复", "where": where, "原": t[:80],
                        "处置": f"替换为引用（见声明{sno}）", "依据": "dedup_rules.boilerplate.exact"})
            return f"（见声明{sno}）", log
    for p, sno in pref:
        if t.startswith(p):
            log.append({"type": "套话重复", "where": where, "原": t[:80],
                        "处置": f"替换为引用（见声明{sno}）", "依据": "dedup_rules.boilerplate.prefix"})
            return f"（见声明{sno}）", log

    nt = dupkit.norm(t)
    if len(nt) >= int(R["norm"]["min_len_for_dup"]):
        if nt in seen_norm:
            log.append({"type": "完全重复", "where": where, "原": t[:80],
                        "处置": f"删除（首次见 {seen_norm[nt]}）", "依据": "字面相同，删除不丢信息"})
            return None, log
        seen_norm[nt] = where
    if len(nt) >= int(R["near_dup"]["min_len"]):
        for og, ow in seen_paras:
            if dupkit.is_paragraph_dup(nt, og, rules=R):
                log.append({"type": "近似重复", "where": where, "原": t[:80],
                            "处置": f"删除（近似，首次见 {ow}）", "依据": "段落级相似度≥阈值"})
                return None, log
        seen_paras.append((nt, where))
    return t, log


# ---------------------------------------------------------------- 句子级去重
def dedup_sentences(text: str, seen_sents: List[Tuple[str, str]], fact_ref: Dict[str, str],
                    *, where: str = "", rules: Optional[Dict[str, Any]] = None) -> Tuple[str, List[dict]]:
    """句子级去重：同一数值所在的**高度相似句子**只保留首次完整陈述，其余改引用。"""
    R = rules or load_rules()
    log: List[dict] = []
    kept: List[str] = []
    for sn in dupkit.split_sentences(str(text or "")):
        st = sn.strip()
        if len(st) < 12 or is_necessary(st):
            if st:
                kept.append(st)
            continue
        hit = next((w for og, w in seen_sents if dupkit.is_sentence_dup(st, og, rules=R)), None)
        if hit:
            ref = next((fact_ref[m.group(0).strip()] for m in RE_AMOUNT.finditer(st)
                        if m.group(0).strip() in fact_ref), None)
            log.append({"type": "事实重复", "where": where, "原": st[:80],
                        "处置": (f"替换为引用（见事实{ref}）" if ref else f"删除（相似句首次见 {hit}）"),
                        "依据": "同一事实完整陈述全局仅保留一次"})
            if ref:
                kept.append(f"（见事实{ref}）")
            continue
        seen_sents.append((st, where))
        kept.append(st)
    return "".join(kept).strip(), log


# ---------------------------------------------------------------- 段内去重
def dedup_within_paragraph(text: str, *, where: str = "",
                           rules: Optional[Dict[str, Any]] = None) -> Tuple[str, List[dict]]:
    """段内重复（模式化）：如「（本表 N 行，金额合计 X 元）」在同段已陈述该数值时删除。"""
    R = rules or load_rules()
    log: List[dict] = []
    out = str(text or "")
    for spec in (R.get("intra_paragraph") or {}).get("patterns") or []:
        rx = re.compile(spec["regex"])
        for m in reversed(list(rx.finditer(out))):
            val = m.group(1)
            outside = out[:m.start()] + out[m.end():]
            if val in outside:
                log.append({"type": "段内重复", "where": where, "原": m.group(0)[:80],
                            "处置": "删除（同段已完整陈述该数值）",
                            "依据": f"dedup_rules.intra_paragraph/{spec['name']}"})
                out = out[:m.start()] + out[m.end():]
    return out.strip(), log


# ---------------------------------------------------------------- 重复率
_RE_SECTION = re.compile(r"^<<S:(.+?)>>$")


def split_sections(lines: List[str]) -> Tuple[List[str], List[str]]:
    """把行切分为 `(内容行, 该行所属章节)`（两者等长）——**章节归属的唯一实现**。

    识别优先级：
      ① 显式分节标记 `<<S:名称>>`（`output_variants.report_text_from` 输出，产出链用）；
      ② md 标题（`#` 起）或 `疑点N：` / `R1：`（离线 md 稿用）；
      ③ 否则沿用上一章节（开头为「全文」）。
    标记行本身**不计入内容块**（不参与字数与重复率统计）。
    """
    blocks: List[str] = []
    sections: List[str] = []
    cur = "全文"
    for raw in lines:
        s = str(raw or "").strip()
        if not s:
            continue
        m = _RE_SECTION.match(s)
        if m:
            cur = m.group(1).strip()[:40] or "全文"
            continue
        if s.startswith("<<"):
            continue
        if re.match(r"^#{1,6}\s+", s) or re.match(r"^(疑点\s*\d+|R\d+)\s*[:：]", s):
            cur = s.lstrip("#").strip()[:40] or cur
        blocks.append(s)
        sections.append(cur)
    return blocks, sections


def fact_repeat_stats(blocks: List[str], *,
                      rules: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """「同一事实完整出现次数」唯一判定：同一**数值锚点**所在的**高度相似句子**聚簇，
    簇内超出阈值（默认 1）的次数即超额。

    判据**逐字对齐** `config/dedup_rules.json::fact_anchor`（原 `_phase1_diagnose` R6 口径）：
      · 句子长度 ≥ 8；数值须 ≥ `min_digits` 位数字（否则把税率/页码当事实）；
      · 锚点出现次数须 ≤ `rare_max_occurrences`（超出视为公共常量，不作事实锚）；
      · 相似度走 `engine/dupkit.is_sentence_dup`（唯一实现，本函数不自实现）；
      · 明细表数据行（`is_necessary`）不构成"完整陈述"，不计入（逐笔数据非同一事实）。
    """
    R = rules or load_rules()
    maxocc = int(R["thresholds"].get("fact_full_occurrences_max") or 1)
    fa = R.get("fact_anchor") or {}
    min_digits = int(fa.get("min_digits") or 5)
    rare_max = int(fa.get("rare_max_occurrences") or 30)
    sent_by_val: Dict[str, List[str]] = {}
    for b in blocks:
        if is_necessary(b):
            continue
        for sn in dupkit.split_sentences(b, keep_delim=False):
            st = str(sn).strip()
            if len(st) < 8:
                continue
            # 同句同值只登记一次，否则该句会与自己配对（ratio=1.0）造成假重复
            vals = {m.group(0) for m in RE_AMOUNT.finditer(st)
                    if len(re.sub(r"[^\d]", "", m.group(0))) >= min_digits}
            for v in vals:
                sent_by_val.setdefault(v, []).append(st)
    reps: List[Dict[str, Any]] = []
    excess = 0
    for v, sents in sent_by_val.items():
        if not (2 <= len(sents) <= rare_max):
            continue
        clusters: List[List[str]] = []
        used = set()
        for i, s in enumerate(sents):
            if i in used:
                continue
            grp = [s]
            for j in range(i + 1, len(sents)):
                if j in used:
                    continue
                if dupkit.is_sentence_dup(s, sents[j], rules=R):
                    grp.append(sents[j])
                    used.add(j)
            if len(grp) > 1:
                used.add(i)
                clusters.append(grp)
        for g in clusters:
            if len(g) > maxocc:
                reps.append({"锚点": v, "完整陈述次数": len(g), "样例": g[0][:80]})
                excess += len(g) - maxocc
    reps.sort(key=lambda x: -x["完整陈述次数"])
    return {"口径补充": "只统计非明细表数据行的正文陈述；同一数值锚点下高度相似的句子视为『同一事实』",
            "锚点数": len(sent_by_val), "超额出现次数合计": excess,
            "阈值_同一事实完整出现": maxocc, "TOP20": reps[:20],
            "判定": "PASS" if excess == 0 else "FAIL"}


def cross_chapter_template_stats(blocks: List[str], sections: List[str], *,
                                 rules: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """「跨章节模板句」判据（**第四项**）——补上"跨章节 + 非数值 + 句子级"这一格。

    ★ 2026-10-09（P0-7）：原有三项判据都抓不到它 ——
      · 整体 / 同章节只看**段落级**相似，而模板句藏在段内，段与段并不相似；
      · 同一事实只认**含 ≥5 位数值锚点**的句子（模板句无金额）。
      实测（2026-10-08 产物）：33 种非数值模板句跨章节重复，最长 13 次。

    判据（与上提**同口径**，否则"判据一套、动作另一套"）：
      句子须同时满足 —— 长度 ≥ `cross_chapter_min_len`、非明细表数据行、非近纯引用块、
      非结构性引导句（`report_dedup.is_structural_lead`，即 `content_placeholder_guard.is_orphan_lead`）、
      未登记在 `config/common_clauses.json`（`hoist` 与 `necessary` 两个清单均算已登记）；
      然后统计其出现的**不同章节数**，> `cross_chapter_max_chapters` 即超额。

    ⚠ 键必须用 `report_dedup.cmp_key`（去空白 + 去句末分隔符 + 去强调符）：
      否则"xxx。"与"xxx"会被当成两句，判据与上提动作对不上（经典漏配）。
    """
    R = rules or load_rules()
    th = R["thresholds"]
    min_len = int(th.get("cross_chapter_min_len") or 12)
    max_ch = int(th.get("cross_chapter_max_chapters") or 1)
    from engine.common_clauses import is_necessary_template, is_registered_clause
    from engine.report_dedup import cmp_key, is_structural_lead
    occ: Dict[str, set] = {}
    sample: Dict[str, str] = {}
    for b, sec in zip(blocks, sections):
        if is_necessary(b):
            continue
        for sn in dupkit.split_sentences(b, keep_delim=False):
            s = str(sn).strip()
            k = cmp_key(s)
            if len(k) < min_len:
                continue
            if is_structural_lead(s) or is_registered_clause(s) or is_necessary_template(s):
                continue
            occ.setdefault(k, set()).add(str(sec))
            sample.setdefault(k, s)
    over = sorted(((k, v) for k, v in occ.items() if len(v) > max_ch),
                  key=lambda kv: -len(kv[1]))
    return {
        "口径补充": "统计非明细表数据行、非近纯引用块、非结构性引导句、且未登记在 "
                    "config/common_clauses.json 的句子，其出现的**不同章节数**",
        "阈值_跨章节数": max_ch, "最小长度": min_len,
        "跨章节句种类数": len(occ), "超额种类数": len(over),
        "TOP20": [{"跨章节数": len(v), "样例": sample[k][:100]} for k, v in over[:20]],
        "判定": "PASS" if not over else "FAIL",
    }


def duplicate_rate(lines: List[str], *, rules: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """重复率**四项**判定（唯一权威）：整体 ≤10% / 同章节 ≤5% / 同一事实完整出现 ≤1 次 /
    跨章节模板句 ≤1 个章节。

    ★ 2026-10-08（条款 A5 核验发现）：升级前本函数**只判『整体』**，而
      `scripts/_phase1_diagnose.py` 另有一份**三项完整**实现 ⇒ 同一判据两处实现、
      且产出链的阻断依据残缺（同章节超阈、同一事实多次出现**均不阻断**）。
      现合并为唯一权威：产出链与离线稿都调本函数（离线侧已改薄转发）。
    ★ 2026-10-09（P0-7）：新增第四项「跨章节模板句」—— 前三项**结构上**覆盖不到
      "跨章节 + 非数值 + 句子级"（模板句藏在段内，段与段并不相似；且无金额锚点）。
    阻断判据 = 四项**任一项**超阈。同章节采用**双判据**（比例超阈 **且** 冗余字数≥下限），
    避免短章节的小绝对量被百分比放大成假红。
    """
    R = rules or load_rules()
    th = R["thresholds"]
    blocks, sections = split_sections(lines)
    seen_norm: Dict[str, str] = {}
    seen_paras: List[Tuple[str, str]] = []
    redundant: Set[int] = set()
    for i, b in enumerate(blocks):
        if is_necessary(b):
            continue
        nt = dupkit.norm(b)
        if len(nt) >= int(R["norm"]["min_len_for_dup"]) and nt in seen_norm:
            redundant.add(i)
            continue
        seen_norm.setdefault(nt, str(i))
        if any(dupkit.is_paragraph_dup(nt, g, rules=R) for g, _ in seen_paras):
            redundant.add(i)
            continue
        seen_paras.append((nt, str(i)))

    total_chars = sum(len(b) for b in blocks) or 1
    red_chars = sum(len(blocks[i]) for i in redundant)
    rate = red_chars / total_chars
    overall_ok = rate <= th["overall_max"]

    # ── 同章节 ──
    min_ch = int(th.get("per_chapter_min_chars") or 0)
    min_red = int(th.get("per_chapter_min_redundant_chars") or 0)
    by_ch: Dict[str, List[int]] = {}
    for i, sec in enumerate(sections):
        by_ch.setdefault(sec, []).append(i)
    per_ch: Dict[str, Dict[str, Any]] = {}
    for ch, idxs in by_ch.items():
        tc = sum(len(blocks[i]) for i in idxs)
        rc = sum(len(blocks[i]) for i in idxs if i in redundant)
        per_ch[ch] = {
            "chars": tc, "redundant_chars": rc,
            "rate": round(rc / tc, 4) if tc else 0.0,
            "blocks": len(idxs), "redundant_blocks": sum(1 for i in idxs if i in redundant),
            "判定依据": ("样本过小（%d 字 < %d），不单独判定" % (tc, min_ch)) if tc < min_ch else "正常判定",
        }
    judged = {k: v for k, v in per_ch.items() if v["chars"] >= min_ch}
    for v in judged.values():
        v["判定"] = ("FAIL" if (v["rate"] > th["per_chapter_max"] and v["redundant_chars"] >= min_red)
                    else "PASS")
    ch_fail = [k for k, v in judged.items() if v.get("判定") == "FAIL"]
    worst = sorted(judged.items(), key=lambda kv: -kv[1]["rate"])[:15]

    fs = fact_repeat_stats(blocks, rules=R)
    xs = cross_chapter_template_stats(blocks, sections, rules=R)
    blocking = ((not overall_ok) or bool(ch_fail) or fs["判定"] == "FAIL"
                or xs["判定"] == "FAIL")
    return {
        "整体": {"重复率": round(rate, 4), "冗余字数": red_chars, "总字数": total_chars,
                 "阈值": th["overall_max"], "判定": "PASS" if overall_ok else "FAIL"},
        "章节统计": {"总章节": len(per_ch), "参与判定章节": len(judged),
                     "样本过小未判定": len(per_ch) - len(judged),
                     "超阈章节": len(ch_fail), "阈值": th["per_chapter_max"],
                     "最小样本量": min_ch, "超阈章节名": ch_fail[:10]},
        "同章节最差15": [{"章节": k, **v, "阈值": th["per_chapter_max"],
                          "冗余字数下限": min_red} for k, v in worst],
        "事实重复": fs,
        "跨章节模板句": xs,
        "阻断": blocking,
        "说明": "四项任一超阈 ⇒ 报告不得输出（指令禁止事项第 10 条）",
    }
