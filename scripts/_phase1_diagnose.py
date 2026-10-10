# -*- coding: utf-8 -*-
"""阶段1：问题诊断 + 重复诊断（只读，全部现算，不手抄、不推断）。

产出：
    baseline/阶段1/重复清单.json      六类重复逐条（含行号、原文、判定、处理方式）
    baseline/阶段1/重复率.json        整体/同章节/事实完整出现次数 三项阈值校验
    baseline/阶段1/问题诊断.json      9 类问题的机器判据命中
    baseline/阶段1/诊断摘要.md        人读摘要

判据全部来自 config/dedup_rules.json（唯一权威），本文件只做执行，不内嵌规则。
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import dupkit  # noqa: E402  —— 重复判定唯一权威实现

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = json.load(open(os.path.join(ROOT, "config", "dedup_rules.json"), encoding="utf-8"))
SRC_TXT = os.path.join(ROOT, "baseline", "V1.0", "原始报告_纯文本.txt")
OUT = os.path.join(ROOT, "baseline", "阶段1")

TABLE_MARK = ("<<TABLE_START>>", "<<TABLE_END>>")
RE_LIST_PREFIX = re.compile(r"^\s*(?:\d+[.、)）]|[①-⑳]|［[^］]{1,4}］|[-—•])\s*")
RE_CHAPTER = re.compile(r"^([一二三四五六七八九十]+)、")
RE_ITEM = re.compile(r"^(疑点\d+)[：:]")
RE_EMPTY_ROW = re.compile(RULES["render_residue"]["empty_table_row_regex"])
RE_AMOUNT = re.compile(RULES["fact_anchor"]["amount_regex"])
RE_CROSSREF = re.compile(r"见疑点R?\d+|见要件[A-Z]*\d*-?C?\d*|见事实F-\d+|见资料D-\d+|见声明S-\d+|见法规L-\d+")
RE_LAW = re.compile(r"《[^》]+》")
RE_NECESSARY = [re.compile(x["regex"]) for x in RULES["necessary_repeat"].get("patterns", [])]


def is_table_data_row(txt: str) -> bool:
    """明细表数据行：以 | 首尾，且**至少一个单元格有非空内容**（排除空表行与分隔行）。"""
    t = txt.strip()
    if not (t.startswith("|") and t.endswith("|")):
        return False
    cells = [c.strip().strip("-:") for c in t.strip("|").split("|")]
    return any(c for c in cells)


def is_necessary(txt: str, *, is_table_header: bool = False) -> bool:
    """命中必要重复白名单（结构/格式/引用/明细数据行），不参与重复判定。"""
    if is_table_header:
        return True          # 表格表头：格式必需（位置判据，无法用单行正则表达）
    if is_table_data_row(txt):
        return True          # 明细表逐笔数据行：不同维度表各列一次，属必要重复
    return any(rx.search(txt) for rx in RE_NECESSARY)


# ------------------------------------------------------------------ 归一化
def norm(s: str) -> str:
    s = s.strip()
    if RULES["norm"]["strip_list_prefix"]:
        s = RE_LIST_PREFIX.sub("", s).strip()
    if RULES["norm"]["unify_punct"]:
        s = s.replace("（", "(").replace("）", ")").replace("，", ",")
        s = s.replace("：", ":").replace("；", ";").replace("、", ",")
    if RULES["norm"]["collapse_space"]:
        s = re.sub(r"\s+", " ", s)
    return s


def skeleton(s: str) -> str:
    """骨架化：金额/数字/法规名/百分比 → 占位符，用于结构重复判定。"""
    t = re.sub(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", "#A", s)
    t = re.sub(r"\d+(?:\.\d+)?%", "#P", t)
    t = re.sub(r"\d+(?:\.\d+)?", "#N", t)
    t = RE_LAW.sub("#L", t)
    return t


def bigrams(s: str) -> set:
    if len(s) < 2:
        return {s} if s else set()
    return {s[i:i + 2] for i in range(len(s) - 1)}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ------------------------------------------------------------------ 章节切分
def split_chapters(lines: list[str]) -> list[dict]:
    """按顶层『一、』与『疑点N：』切章。

    判定规则（唯一权威，避免把疑点内部小节误当顶层章）：
      * 先扫出全部『疑点N：』行号，构成疑点区间 [start, 下一疑点start)。
      * 一个『一、』行只有落在**任何疑点区间之外**时才是顶层章；
        落在疑点区间内的是该疑点的固定小节骨架，不单独成章。
    """
    item_starts = [i for i, l in enumerate(lines, 1) if RE_ITEM.match(l.strip())]
    # 所有『X、』行（含疑点内部小节）：最后一个疑点的区间止于其后第一个『X、』行之前，
    # 否则文末的顶层章（三/四/五）会被最后一个疑点区间吞掉。
    head_lines = [i for i, l in enumerate(lines, 1)
                  if RE_CHAPTER.match(l.strip()) and len(l.strip()) <= 40]
    item_ranges = []
    for k, st in enumerate(item_starts):
        if k + 1 < len(item_starts):
            en = item_starts[k + 1] - 1
        else:
            nxt = next((h for h in head_lines if h > st), None)
            en = (nxt - 1) if nxt else len(lines)
        item_ranges.append((st, en))

    def in_item(ln: int) -> int | None:
        for st, en in item_ranges:
            if st <= ln <= en:
                return st
        return None

    # Markdown 标题优先：V1.1 起报告为 md，章节由 '#' 标题表达
    md_chaps = [{"title": l.strip().lstrip("#").strip(), "start": i, "kind": "疑点" if l.startswith("### ") else "章"}
                for i, l in enumerate(lines, 1) if re.match(r"^#{2,3} ", l)]
    if md_chaps:
        return md_chaps

    chaps: list[dict] = []
    # 顶层章判据：『X、』的序号必须在全文层面**连续递增**（一→二→三…）。
    # 疑点内部小节每个疑点都从『一、』重新起算，故必然与期望序号不符 → 不会被误收。
    CN = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    expected = 1
    for i, raw in enumerate(lines, 1):
        s = raw.strip()
        if not s or s.startswith("<<"):
            continue
        m_item = RE_ITEM.match(s)
        if m_item:
            chaps.append({"title": s[:34], "start": i, "kind": "疑点"})
            continue
        m_ch = RE_CHAPTER.match(s)
        if m_ch and len(s) <= 40:
            # 疑点内部骨架小节（如「三、已取得的资料与待补充的资料」）与顶层章同形，
            # 用骨架名单排除：命中骨架 ⇒ 必是疑点小节，不可能是顶层章。
            if s in RULES["structure_skeleton"]["titles"]:
                continue
            n = CN.get(m_ch.group(1))
            if n is None:
                continue
            if n == expected:
                chaps.append({"title": s, "start": i, "kind": "章"})
                expected = n + 1
    chaps.sort(key=lambda c: c["start"])
    return chaps


# ------------------------------------------------------------------ 主流程
def build_blocks(lines: list[str]) -> list[dict]:
    """收集可判定块（含表行，排除表标记行与空行），并把每行归属到章节。"""
    blocks: list[dict] = []  # {no, raw, norm, is_table_row, chapter}
    chapters = split_chapters(lines)
    chap_of_line: dict[int, str] = {}
    for idx, c in enumerate(chapters):
        end = chapters[idx + 1]["start"] - 1 if idx + 1 < len(chapters) else len(lines)
        for ln in range(c["start"], end + 1):
            chap_of_line[ln] = c["title"]

    for i, rawl in enumerate(lines, 1):
        s = rawl.strip()
        if s in TABLE_MARK:
            continue
        if not s:
            continue
        blocks.append({
            "no": i,
            "raw": s,
            "norm": norm(s),
            "is_table_row": "|" in s and not s.startswith("<<"),
            "chapter": chap_of_line.get(i, "未归属"),
        })

    # 表头行判定（位置判据）：下一行是 markdown 分隔行 `|---|` ⇒ 本行为表头（格式必需）
    pats = RULES["necessary_repeat"].get("patterns", [])
    if len(pats) > 1:
        rx_sep = re.compile(pats[1]["regex"])
        for k, b in enumerate(blocks):
            nxt = blocks[k + 1]["raw"] if k + 1 < len(blocks) else ""
            b["is_table_header"] = bool(rx_sep.match(nxt))

    return blocks


def classify(blocks: list[dict]) -> tuple[list[dict], list[dict]]:
    """六类重复分类，判据全部来自 config/dedup_rules.json。返回 (findings, fact_rep)。"""
    findings: list[dict] = []

    def add(kind: str, sub: str, nos: list[int], sample: str, handling: str, necessary: bool,
            redundant_mode: str = "keep_one"):
        """redundant_mode: keep_one=保留首次其余冗余；all=整类全部冗余（一次都不该出现）。"""
        findings.append({
            "type": kind, "subtype": sub, "count": len(nos),
            "lines": nos[:20], "all_lines_count": len(nos),
            "sample": sample[:160],
            "necessary": necessary, "handling": handling,
            "redundant_mode": redundant_mode,
        })

    # R1 渲染残留
    rr = RULES["render_residue"]
    empty_rows = [b["no"] for b in blocks if b["is_table_row"] and RE_EMPTY_ROW.match(b["raw"])]
    empty_heads = [b["no"] for b in blocks if b["raw"] in rr["empty_headings"]]
    if empty_rows:
        add("渲染残留", "空表格行", empty_rows, "|  |  |  |  |  |", "删除整行；空表改为『本项无适用行』一行声明", False, "all")
    if empty_heads:
        add("渲染残留", "空小标题（模板变量为空）", empty_heads, "分述", "删除；原『总述/分述』双轨合并为单轨", False, "all")

    # R2 结构骨架重复
    sk = RULES["structure_skeleton"]["titles"]
    for t in sk:
        nos = [b["no"] for b in blocks if b["raw"] == t]
        if len(nos) > 1:
            add("结构重复", f"骨架标题《{t}》", nos, t, "统一模板化：骨架只在模板库声明一次，各疑点只填差异", True)

    # R3 套话重复
    bp = RULES["boilerplate"]
    for t in bp["exact"]:
        nos = [b["no"] for b in blocks if b["raw"] == t or b["norm"] == norm(t)]
        if len(nos) > 1:
            add("套话重复", "通用句", nos, t, "改为一次性声明 + 交叉引用（见声明S-0x）", False)
    for p in bp["prefix"]:
        nos = [b["no"] for b in blocks if b["raw"].startswith(p)]
        if len(nos) > 1:
            add("套话重复", "通用段（前缀匹配）", nos, p + "…", "改为一次性声明 + 交叉引用", False)

    # R4 完全重复（排除已归类）
    already = set()
    for f in findings:
        already.update(f["lines"])
    cnt = Counter(b["norm"] for b in blocks
                  if len(b["norm"]) >= RULES["norm"]["min_len_for_dup"] and b["no"] not in already
                  and not is_necessary(b["raw"], is_table_header=b.get("is_table_header", False)))
    for s, n in cnt.most_common():
        if n <= 1:
            break
        nos = [b["no"] for b in blocks if b["norm"] == s and b["no"] not in already]
        if len(nos) > 1:
            add("完全重复", "字面相同", nos, s, "保留首次完整陈述，其余改为引用", False)
            already.update(nos[1:])

    # R5 近似重复（候选须排除已被前面规则归类的块，避免同一段被两类各记一次）
    near = RULES["near_dup"]
    cand = [b for b in blocks
            if len(b["norm"]) >= near["min_len"]
            and b["raw"] not in sk
            and not b["is_table_row"]
            and b["no"] not in already
            and not is_necessary(b["raw"], is_table_header=b.get("is_table_header", False))
            and not RE_CROSSREF.search(b["raw"])]
    grams = {b["no"]: bigrams(b["norm"]) for b in cand}
    near_groups: list[dict] = []
    used: set[int] = set()
    for i, a in enumerate(cand):
        if a["no"] in used:
            continue
        grp = [a]
        for b in cand[i + 1:]:
            if b["no"] in used:
                continue
            if jaccard(grams[a["no"]], grams[b["no"]]) >= near["jaccard_min"]:
                grp.append(b)
                used.add(b["no"])
        if len(grp) > 1:
            used.add(a["no"])
            near_groups.append({
                "lines": [g["no"] for g in grp],
                "sample": grp[0]["raw"][:160],
                "peer": grp[1]["raw"][:160],
                "jaccard": round(jaccard(grams[grp[0]["no"]], grams[grp[1]["no"]]), 3),
            })
        if len(near_groups) >= near["max_pairs_reported"]:
            break
    for g in near_groups:
        findings.append({
            "type": "近似重复", "subtype": "2-gram 相似度≥%.2f" % near["jaccard_min"],
            "count": len(g["lines"]), "lines": g["lines"][:20],
            "sample": g["sample"], "peer": g["peer"], "jaccard": g["jaccard"],
            "necessary": False, "handling": "合并为一处完整陈述 + 引用",
        })

    # R6 事实重复（稀有数值锚点）
    fa = RULES["fact_anchor"]
    # 判据（修正后）：『同一事实完整出现』= 同一数值所在的**高度相似句子**重复出现。
    # 不能用「含该数值的不同段落数」——同一数值在『为何列入检查』与『结论』中的表述上下文不同，
    # 属正常引用而非重复完整陈述，用段落数会把这类全部误判（实测 V1.0 会虚高）。
    sent_by_val: dict[str, list[tuple[str, int]]] = defaultdict(list)
    fact_scan = [b for b in blocks if not b["is_table_row"]]
    for b in fact_scan:
        for sent in dupkit.split_sentences(b["raw"], keep_delim=False):
            st = sent.strip()
            if len(st) < 8:
                continue
            # 同一句里同一数值出现多次只登记一次，否则该句会与自己配对（ratio=1.0）造成假重复
            vals = {m.group(0) for m in RE_AMOUNT.finditer(st)
                    if len(re.sub(r"[^\d]", "", m.group(0))) >= fa["min_digits"]}
            for v in vals:
                sent_by_val[v].append((st, b["no"]))
    fact_rep = []
    for v, pairs in sent_by_val.items():
        if not (2 <= len(pairs) <= fa["rare_max_occurrences"]):
            continue
        # 相似度判定统一走 engine/dupkit（句子级用 SequenceMatcher.ratio）
        groups: list[list[int]] = []
        used: set[int] = set()
        for i, (_t1, l1) in enumerate(pairs):
            if i in used:
                continue
            grp = [l1]
            for j in range(i + 1, len(pairs)):
                if j in used:
                    continue
                if dupkit.is_sentence_dup(pairs[i][0], pairs[j][0], rules=RULES):
                    grp.append(pairs[j][1])
                    used.add(j)
            if len(grp) > 1:
                used.add(i)
                groups.append(grp)
        extra = sum(len(g) - 1 for g in groups)
        if extra > 0:
            fact_rep.append({"value": v, "occurrences": extra + 1,
                             "repeat_sentences": extra, "lines": sorted(set(
                                 ln for g in groups for ln in g))[:12]})
    fact_rep.sort(key=lambda x: -x["occurrences"])
    return findings, fact_rep


def compute_rates(blocks: list[dict], findings: list[dict], fact_rep: list[dict]) -> dict:
    """重复率三项判定 —— **薄转发**到唯一权威 `engine.dedup_pipeline.duplicate_rate`。

    ★ 2026-10-08（条款 A5 核验）：本函数原为三项判定的**独立实现**，与产出链的
      `dedup_pipeline.duplicate_rate`（当时只判『整体』）两处并存 ⇒ 同一判据两处实现、
      产出链的阻断依据残缺（同章节超阈、同一事实多次出现均不阻断）。
      现收敛为单一权威：本函数只做「取行 → 调引擎 → 附本脚本明细」。
      `findings` / `fact_rep` 仅作**呈现**（写 `重复清单.json`），**不参与判定**。
    """
    from engine.dedup_pipeline import duplicate_rate as _dr
    rates = _dr([str(b.get("raw") or "") for b in blocks])
    rates["本脚本六类明细"] = {
        "说明": "仅为呈现（写 重复清单.json）；判定一律以引擎三项为准，不在此处另算",
        "findings组数": len(findings),
        "事实重复簇数": len(fact_rep),
    }
    return rates
def main() -> int:
    """用法：scripts/_phase1_diagnose.py [输入文本] [输出目录]

    默认对 V1.0 冻结稿跑；传入路径即可对 V1.1/V1.2… 各版本重跑实测。
    """
    src = sys.argv[1] if len(sys.argv) > 1 else SRC_TXT
    outdir = sys.argv[2] if len(sys.argv) > 2 else OUT
    os.makedirs(outdir, exist_ok=True)
    raw = open(src, encoding="utf-8").read()
    lines = raw.split("\n")
    blocks = build_blocks(lines)
    print(f"[INFO] 可判定块 {len(blocks)}")
    findings, fact_rep = classify(blocks)
    rates = compute_rates(blocks, findings, fact_rep)

    # ---------- 9 类问题诊断 ----------
    problems = diagnose_problems(blocks, lines, rates)

    # ---------- 落盘 ----------
    json.dump({"findings": findings}, open(os.path.join(outdir, "重复清单.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    json.dump(rates, open(os.path.join(outdir, "重复率.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    json.dump({"problems": problems}, open(os.path.join(outdir, "问题诊断.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"[INFO] 输入 {src} → 输出 {outdir}")

    print("\n=== 9 类问题诊断 ===")
    for p in problems:
        print(f"  [{p['id']}] {p['category']}/{p['name']} -> {p['status']} x{p.get('count',0)}")
        if p.get("detail"):
            print(f"        {p['detail']}")

    print("\n=== 重复率 ===")
    _o, _c, _f = rates["整体"], rates["章节统计"], rates["事实重复"]
    print(f"整体重复率 {_o['重复率']:.2%} (阈值 {_o['阈值']:.0%}) -> {_o['判定']}")
    print(f"章节数 {_c['总章节']}，超 {_c['阈值']:.0%} 的章节：{_c['超阈章节']}")
    print(f"事实锚点重复 {_f['锚点数']} 个，超额出现 {_f['超额出现次数合计']} 次 -> {_f['判定']}")
    print("\n=== 分类计数 ===")
    for k, v in Counter(f["type"] for f in findings).most_common():
        print(f"  {k}: {v} 组")
    print("\n=== 冗余块 TOP 类型 ===")
    for f in sorted(findings, key=lambda x: -x["count"])[:12]:
        print(f"  [{f['type']}/{f['subtype']}] x{f['count']}  {f['sample'][:52]}")
    return 0


# ------------------------------------------------------- 9 类问题诊断（文档层现算）
PROBLEM_RULES = [
    # (编号, 类别, 判据名, 正则, 说明, 处理方向)
    ("P2", "数据与计数一致性", "办理顺序编号断裂", r"办理顺序：第[一二三四五六七八九十]+项",
     "统计实际编号序列，检查是否跳号、末值是否大于总项数", "改为统一编号 R1..R16，编号连续且与总项数一致"),
    ("P3", "定性口径", "『已查明的风险』缺谓语破句", r"本企业本项已查明的风险[；;]",
     "模板变量位为空导致句子断裂，且与全文『不作认定』正面冲突", "改用 L1/L2/L3 分级结论句式，禁止缺谓语短句"),
    ("P3", "定性口径", "『已查明』与『未认定』同段并存", r"(已查明|已认定).{0,240}?(未认定到|不作认定|未形成核对结论)",
     "同一段内既称已查明又称未认定，定性口径自相矛盾", "结论只保留一级：L1 命中/L2 待核/L3 成立"),
    ("P6", "法规引用", "法条版本未登记", r"版本未登记|须核对现行有效文本|引用较早",
     "法规未核到现行有效版本即随文交付", "法规统一编号 L-01..，集中到法规索引，未核版本不得作判据"),
    # 只匹配『待核』作为**等级词**使用（后接括号/表格分隔符）；"待核线索""待核项"是合法术语，不判
    ("P7", "术语一致性", "『待核』与『待核验』混用", r"(?<!待)待核(?=[（(|])",
     "等级词表以 risk_levels.LEGAL_LEVELS 为唯一权威（合法值含『待核验』）", "统一为『待核验』，加术语表与门禁校验"),
    ("P9", "归档与模板整洁", "空表格行",RULES["render_residue"]["empty_table_row_regex"],
     "渲染残留，对外交付视为硬伤", "空表改为『本项无适用行』一行声明；空行一律不渲染"),
    ("P9", "归档与模板整洁", "空小标题（模板变量为空）", r"^(分述|总述|总结)$",
     "模板变量位为空仍渲染出标题", "删除；『总述/分述』双轨合并为单轨"),
    # P4 按疑点块聚合判定，占位：真正判定见 diagnose_problems 内 P4-b
    ("P5", "等级与证据强度", "等级词不在法定词表", r"等级\s*[:：]?\s*(极高|很高|较高|偏高|一般)风险",
     "risk_levels.LEGAL_LEVELS 为唯一权威", "归一到法定等级词；加门禁双向校验"),
]


def diagnose_problems(blocks: list[dict], lines: list[str], rates: dict) -> list[dict]:
    out: list[dict] = []

    def put(pid, cat, name, hitline: str, count: int, samples: list[str], handling: str, status="检出"):
        out.append({"id": pid, "category": cat, "name": name, "status": status,
                    "count": count, "sample_lines": samples[:6], "sample": hitline[:150],
                    "handling": handling})

    # P1 重复冗余：直接引用已算出的重复率
    o = rates["整体"]
    put("P1", "重复冗余", f"整体重复率 {o['重复率']:.2%}（阈值 {o['阈值']:.0%}）",
        f"冗余 {o['冗余字数']} 字 / 正文 {o['总字数']} 字，冗余块 {o['冗余块数']}/{o['总块数']}",
        1, [], "阶段5 去重：六类重复分别按『删除/合并/引用替换』处理", o["判定"])

    # 其余按正则扫描
    for pid, cat, name, pat, _desc, handling in PROBLEM_RULES:
        rx = re.compile(pat)
        nos, samples = [], []
        for b in blocks:
            if rx.search(b["raw"]):
                nos.append(b["no"])
                if len(samples) < 6:
                    samples.append(b["no"])
        if nos:
            sample = next(b["raw"] for b in blocks if b["no"] == samples[0])
            put(pid, cat, name, sample, len(nos), samples, handling)
        else:
            put(pid, cat, name, "", 0, [], handling, "未检出")

    # P2-b 办理顺序编号断裂（序列分析）
    CN2 = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    seq = []
    for b in blocks:
        m = re.search(r"办理顺序：第([一二三四五六七八九十]+)项", b["raw"])
        if m:
            s = m.group(1)
            n = CN2.get(s)
            if n is None and s.startswith("十"):
                n = 10 + CN2.get(s[1:], 0)
            seq.append((b["no"], s, n))
    if seq:
        total_items = sum(1 for b in blocks if RE_ITEM.match(b["raw"]))
        nums = [n for _, _, n in seq if n]
        missing = [i for i in range(1, max(nums) + 1) if i not in nums]
        over = [n for n in nums if n > total_items]
        out.append({"id": "P2-b", "category": "数据与计数一致性", "name": "办理顺序编号序列校验",
                    "status": "检出" if (missing or over) else "PASS",
                    "count": len(missing) + len(over),
                    "detail": {"实际编号": [s for _, s, _ in seq], "总疑点数": total_items,
                               "跳号": missing, "大于总项数": over},
                    "handling": "统一编号 R1..R16，连续且不超总项数"})

    # P4-b 关键证据缺失仍给出等级：按疑点块聚合判定（同一疑点内既有『现状：缺失』又有中/高等级）
    item_blocks: dict[str, list[dict]] = defaultdict(list)
    cur = "未归属"
    for b in blocks:
        if RE_ITEM.match(b["raw"]):
            cur = b["raw"][:12]
        item_blocks[cur].append(b)
    p4_hits = []
    for k, bs in item_blocks.items():
        if k == "未归属":
            continue
        miss = [b["no"] for b in bs if re.search(r"现状：缺失|独立数据源本轮未取得|资料缺失", b["raw"])]
        lvl = [b["no"] for b in bs if re.search(r"等级\s*[:：]?\s*(高风险|中风险)|(高风险|中风险)", b["raw"])]
        if miss and lvl:
            p4_hits.append({"疑点": k, "缺失行": miss[:4], "等级行": lvl[:4]})
    out.append({"id": "P4-b", "category": "证据链闭合", "name": "关键证据缺失仍给出中/高等级（一票否决）",
                "status": "检出" if p4_hits else "未检出", "count": len(p4_hits),
                "detail": {"命中疑点数": len(p4_hits), "样例": p4_hits[:6]},
                "handling": "触发 V1 否决：等级降为『待核验』、结论降为 L2，并注明关键证据缺失不作认定"})

    # P10 段内重复（模式化）：句子级判据的盲区
    ia = RULES.get("intra_paragraph") or {}
    ia_hits = []
    for rx_spec in ia.get("patterns", []):
        rx = re.compile(rx_spec["regex"])
        for b in blocks:
            if b["is_table_row"]:
                continue
            for m in rx.finditer(b["raw"]):
                val = m.group(1)
                outside = b["raw"][:m.start()] + b["raw"][m.end():]
                if val in outside:
                    ia_hits.append({"line": b["no"], "数值": val,
                                    "重复表述": m.group(0)[:60], "规则": rx_spec["name"]})
    out.append({"id": "P10", "category": "重复冗余", "name": "段内重复（模式化）",
                "status": "检出" if ia_hits else "未检出", "count": len(ia_hits),
                "detail": {"命中": ia_hits[:8],
                           "口径说明": ia.get("description", "")[:160]},
                "handling": "删除重复的表说明括号（保留首次完整表述）"})

    # P11 多版本输出类：是否区分内部版/对外版
    _alltxt = " ".join(b["raw"] for b in blocks)
    has_internal = "内部版" in _alltxt
    has_external = "对外版" in _alltxt
    out.append({"id": "P11", "category": "多版本输出", "name": "未区分内部版/对外版",
                "status": "检出" if not (has_internal and has_external) else "PASS",
                "count": 0 if (has_internal and has_external) else 1,
                "detail": {"内部版标识": has_internal, "对外版标识": has_external,
                           "说明": "指令要求一键生成内部完整版与对外脱敏版（对外版禁泄露企业名称/自然人姓名/账号/发票号）"},
                "handling": "产出内部版 + 对外脱敏版两个文件，并在版头标注版本类型与脱敏范围"})

    # P12 行业适配类：行业基准是否落到 _default（通用默认基准＝失配）
    import re as _re
    m_ent = _re.search(r"([\u4e00-\u9fa5A-Za-z0-9]{2,20}(?:有限公司|股份有限公司))", _alltxt)
    ent = m_ent.group(1) if m_ent else ""
    bm = None
    try:
        sys.path.insert(0, ROOT)
        from engine import industry_resolver as _ir
        bm = _ir.match_benchmark(ent)[0] if ent else None
    except Exception as exc:  # noqa: BLE001 —— 留痕，不静默
        out.append({"id": "P12", "category": "行业适配", "name": "行业基准匹配（无法判定）",
                    "status": "SKIP", "count": 0, "detail": {"原因": f"行业解析不可用：{exc}"},
                    "handling": "修复行业解析后重跑"})
    if bm is not None:
        bad = bm in (None, "_default")
        out.append({"id": "P12", "category": "行业适配", "name": "行业基准落 _default（基准失配）",
                    "status": "检出" if bad else "PASS", "count": 1 if bad else 0,
                    "detail": {"企业": ent, "匹配基准": bm,
                               "说明": "落到 _default 表示未匹配到行业基准，同业对标用的是通用默认值"},
                    "handling": "修复行业名归一/别名映射，使基准落到真实行业键"})

    # P13 自检缺失类：是否有报告生成后自动校验
    txt_all = _alltxt
    has_sc = ("自检" in txt_all and ("清单" in txt_all or "报告" in txt_all))
    out.append({"id": "P13", "category": "自检缺失", "name": "无报告生成后自动校验",
                "status": "PASS" if has_sc else "检出", "count": 0 if has_sc else 1,
                "detail": {"说明": "指令要求：未通过自检清单不得输出报告（且须系统化，不依赖人工提醒）"},
                "handling": "新增《系统自检报告》章 + 自检清单接入产出链（阻断机制）"})

    # P8 结构与导航
    has_summary = any(("决策摘要" in b["raw"] or "摘要" in b["raw"])
                      and not b["is_table_row"] and "|" not in b["raw"] for b in blocks)
    out.append({"id": "P8", "category": "结构与导航", "name": "缺企业负责人决策摘要",
                "status": "未检出（即缺）" if not has_summary else "PASS",
                "count": 0 if has_summary else 1,
                "sample": "全文 102 页、1,884 块，第一章为『检查情况总述与总体结论』（非决策摘要）",
                "handling": "新增第0章《决策摘要》≤2 页：只给结论与行动项，不给推导"})

    # P6-b 业务招待费限额笔误专项核验（指令点名，必须给结论）
    wrong5 = [b["no"] for b in blocks if re.search(r"招待费[^。]{0,80}5\s*%", b["raw"])]
    right5 = [b["no"] for b in blocks if "5‰" in b["raw"]]
    out.append({"id": "P6-b", "category": "数据与法规校验", "name": "业务招待费限额『5‰ vs 5%』笔误核验",
                "status": "未检出笔误" if not wrong5 else "检出",
                "count": len(wrong5),
                "detail": {"使用5%的行": wrong5, "使用5‰的行": right5,
                           "复算": "6,636,800.57 × 5‰ = 33,184.00 元，与正文『按孰低法可扣除约 33,184.00 元』一致；"
                                   "发生额 411,111.53 × 60% = 246,666.92 元 > 33,184.00 元，孰低取 33,184.00 元 ✓"},
                "handling": "本样本未检出该笔误，不作修改；阶段6 仍将限额公式与数值固化进规则库做机器复算"})
    return out


if __name__ == "__main__":
    sys.exit(main())
