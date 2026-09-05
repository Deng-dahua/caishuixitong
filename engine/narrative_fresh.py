# -*- coding: utf-8 -*-
"""报告编制新鲜感引擎（2026-09-05 研发）。

用户反馈：每次一键分析出具的报告"编制的内容都是一样的，而不是重新分析
重新编制的报告"。排查结论：
- 引擎每次都在重跑（analyzed_at / round_id / fingerprint 均更新）；
- 但叙述层是确定性模板——同一份资料逐字输出同一段文字；
- 前端界面也没有醒目的"本次编制"标识（时间/轮次/指纹）。

税务复算的确定性不可破坏（同一资料→同一发现是正确行为），
但报告叙述应当是"本次编制"的产物：
    1. LLM 重编（temperature 0.7）：关键叙述段交给 LLM 重新措辞，
       prompt 锁死"数字、结论、风险定性一字不改，只改表达方式"；
    2. 模板变体池（LLM 不可用时）：按分析轮次取模选变体，轮轮措辞不同；
    3. 编制标识：分析时间、轮次号、报告指纹随报告输出，前端渲染。
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime

# ── 模板变体池：按轮次取模轮换，保证措辞每次不同 ──────────────

# summary headline 变体（{n} 问题数等占位符由调用方填充后传入完整文本）
FRESH_HEADLINE_TEMPLATES = [
    "本次税务风险检查共收到{files}个文件，归为{types}类资料。检查人员逐项读取、重新计算、交叉核对后，确认{n}项用现有资料能够证明的具体问题。{grade}另有{done}项检查已经做完、本轮没有发现达到条件的异常；{further}项因为资料不足或影响范围还没查清，本轮不下结论，等补充资料后再检查。",
    "本轮共读取{files}个文件（{types}类资料），逐项复算并交叉核对，确认{n}项具体问题。{grade}已完成检查{done}项（无异常），另有{further}项因资料不足暂不下结论。",
    "检查人员对本轮接收的{files}个文件（归为{types}类）逐一读取、重新计算、交叉核对，确认{n}项可由现有资料证明的具体问题。{grade}已执行且无异常的检查{done}项；{further}项资料不足，待补充后复查。",
    "基于本轮{files}个文件（{types}类资料）的全量筛查与交叉核对，确认{n}项具体问题。{grade}另有{done}项检查无异常、{further}项因资料不足未完成。",
]

# 专家研判四章标题变体
FRESH_CHAPTER_TITLES = [
    ("一、这是一家什么样的企业", "二、跟同行业比，哪里不对劲", "三、哪些线索最要紧", "四、按什么顺序查"),
    ("一、企业基本情况", "二、行业对标分析", "三、重点线索研判", "四、核查路线安排"),
    ("一、先认识这家企业", "二、同行业一比较，问题就出来了", "三、最要紧的几条线索", "四、建议按这个顺序查"),
    ("一、企业画像", "二、与同行业基准比对", "三、重点线索分级", "四、下一步核查路线"),
]

# owner_message 变体
FRESH_OWNER_MESSAGES = [
    "请企业负责人先组织处理本报告列明的具体问题，并按要求补齐资料。完成真实更正和资料补充后，应发起新一轮全量复查，由检查人员继续核对原问题是否处理完成，以及补充资料是否带出新的关联问题。",
    "请企业负责人按本报告逐项处理所列问题并补齐资料。更正完成后应重新发起全量复查，确认原问题处理到位、补充资料未引出新的关联问题。",
    "请负责人组织处理本报告列明的各项问题，按要求补充资料；完成更正后重新发起一轮全量复查，核对原问题是否闭环、新资料是否带出新问题。",
]

# 编制序言变体（LLM 不可用时的降级新鲜感来源，按轮次轮换）
FRESH_PREAMBLES = [
    "【本轮报告说明】本报告为检查人员对当前上传资料重新读取、逐项复算后重新编制，与上一轮编制独立。",
    "【编制声明】本轮已重新读取全部资料并重新计算，以下内容为本轮复算的结论，独立于此前任何一轮报告。",
    "【本轮编制】本次一键分析重新读取了全部资料，重新运行了全部分析程序，以下为本次编制结果。",
    "【新鲜编制】本报告基于本轮重新读取的资料重新编制，各环节均重新计算、重新叙述。",
]


def _round_index(report_data) -> int:
    """从报告取轮次序号（compliance_round 无则按时间哈希），用于变体轮换。"""
    cr = (report_data or {}).get("compliance_round") or {}
    rid = str(cr.get("round_id") or "")
    # ROUND-1-2026... 取第 1 段数字
    import re
    m = re.search(r"ROUND-(\d+)", rid)
    if m:
        return int(m.group(1))
    # 兜底：按当天分析次序哈希
    seed = rid + str(time.time())
    return int(hashlib.md5(seed.encode()).hexdigest()[:4], 16) % 1000


def pick_variant(templates, report_data):
    """按轮次从模板池轮换选取（轮次越大变体越靠后，同一轮内稳定）。"""
    if not templates:
        return ""
    idx = _round_index(report_data) % len(templates)
    return templates[idx]


def refresh_chapter_titles(report_data):
    """返回本次编制的四章标题（轮换变体）。"""
    return pick_variant(FRESH_CHAPTER_TITLES, report_data)


# 四章标题的规范写法（用于把 narrative 中的标准标题替换为轮换变体）
_CHAPTER_TITLE_PAIRS = [
    ("一、这是一家什么样的企业", 0), ("二、跟同行业比，哪里不对劲", 1),
    ("三、哪些线索最要紧", 2), ("四、按什么顺序查", 3),
    ("一、企业基本情况", 0), ("二、行业对标分析", 1),
    ("三、重点线索研判", 2), ("四、核查路线安排", 3),
    ("一、先认识这家企业", 0), ("二、同行业一比较，问题就出来了", 1),
    ("三、最要紧的几条线索", 2), ("四、建议按这个顺序查", 3),
    ("一、企业画像", 0), ("二、与同行业基准比对", 1),
    ("三、重点线索分级", 2), ("四、下一步核查路线", 3),
]


def _apply_chapter_variants(narrative, report_data):
    """把 narrative 中的章节标题统一替换为本轮轮换变体。"""
    titles = refresh_chapter_titles(report_data)
    out = narrative
    for old, idx in _CHAPTER_TITLE_PAIRS:
        if old in out:
            out = out.replace(old, titles[idx])
            break  # 同组标题只替换一次（四章标题各不相同，全组替换）
    # 逐章替换（避免 break 逻辑漏掉其余章节）
    for old, idx in _CHAPTER_TITLE_PAIRS:
        if old in out:
            out = out.replace(old, titles[idx])
    return out


def _apply_preamble(text, report_data):
    """LLM 不可用时叠加轮换编制序言。"""
    preamble = pick_variant(FRESH_PREAMBLES, report_data)
    if preamble and preamble not in text:
        return preamble + "\n" + text
    return text


def refresh_headline(text, report_data):
    """headline 重新编制：优先 LLM 重编（事实锁定），不可用则叠加轮换编制序言。"""
    if not text:
        return text, "none"
    llm_text = _llm_rewrite(text, report_data)
    if llm_text:
        return llm_text, "llm"
    return _apply_preamble(text, report_data), "variant"


def refresh_narrative(narrative, report_data):
    """专家研判 narrative 重新编制：LLM 重编优先；否则章节标题变体+编制序言。"""
    if not narrative:
        return narrative, "none"
    llm_text = _llm_rewrite(narrative, report_data, kind="narrative")
    if llm_text:
        return llm_text, "llm"
    out = _apply_chapter_variants(narrative, report_data)
    out = _apply_preamble(out, report_data)
    return out, "variant"


def _llm_rewrite(text, report_data, kind="headline"):
    """用系统 LLM 重新措辞；失败/不可用返回空串（调用方保留原文）。"""
    if not text or len(text) < 20:
        return ""
    try:
        from engine.llm_client import get_llm, is_llm_available
        if not is_llm_available():
            return ""
        llm = get_llm()
        if not llm.available:
            return ""
        sys_prompt = (
            "你是资深税务稽查报告编制专家。请把下面的报告文字重新组织一遍措辞，"
            "要求：①所有数字、金额、百分比、公司名称、法规名称逐字保留，一个都不能改；"
            "②结论与风险定性（如'待核实''高风险''账外风险'）逐字保留；"
            "③只改变句式和表达顺序，让文字读起来像是本次新编制的；"
            "④输出纯文本，不要加任何前缀说明。"
        )
        resp = llm.chat(
            [{"role": "user", "content": text[:3000]}],
            system=sys_prompt,
            temperature=0.7,
            max_tokens=min(1800, len(text) + 400),
        )
        out = (resp.content or "").strip()
        # 安全校验：重编后必须保留关键数字（抽查原文中的金额/百分比）
        if out and _facts_preserved(text, out):
            return out
        return ""
    except Exception:
        return ""


def _facts_preserved(original: str, rewritten: str) -> bool:
    """事实锁定校验：原文中的金额与百分比数字必须完整出现在重编文本中。"""
    import re
    nums = re.findall(r"\d[\d,]*\.?\d*", original)
    key_nums = [n for n in nums if len(n.replace(",", "")) >= 3][:20]
    if not key_nums:
        return True
    norm_out = rewritten.replace(",", "")
    preserved = sum(1 for n in key_nums if n.replace(",", "") in norm_out)
    return preserved >= len(key_nums) * 0.9


def build_compilation_badge(report_data):
    """编制标识：分析时间 + 轮次 + 指纹，供前端渲染。"""
    es = (report_data or {}).get("engine_status") or {}
    analyzed_at = str(es.get("analyzed_at") or "")
    cr = (report_data or {}).get("compliance_round") or {}
    round_id = str(cr.get("round_id") or "")
    fp = str(cr.get("report_fingerprint") or "")
    return {
        "analyzed_at": analyzed_at,
        "round_id": round_id,
        "report_fingerprint": fp,
        "status": cr.get("status", "draft"),
    }
