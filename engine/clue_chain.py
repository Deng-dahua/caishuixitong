# -*- coding: utf-8 -*-
"""
线索链引擎 —— 回答「这个税务疑点是怎么被发现的」
==================================================

线索链的定义
--------------------------------------------------
线索链是「原始资料 → 税务疑点」之间可回溯、可复核的推导路径。它回答稽查员
最关心的问题：**这条疑点是拍脑袋想出来的，还是从资料里一步步算出来的？**

每一环必须回答三件事：
    ① 用了什么资料（source）
    ② 做了什么计算或比对（action）
    ③ 实际看到了什么数字（observed）——没有数字就说明这一环没数据

设计原则
--------------------------------------------------
1. 每一环都必须落到具体数字。写不出数字的环节标注「本轮未取得该项数据」，
   绝不用「经分析发现异常」这类空话充数。
2. 线索链可回溯：每环给出 trace_ref（回查位置），专业人员能按图索骥复核。
3. 无资料支撑的环节不隐藏——它本身就是「风险盲区」，要暴露给报告。
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from engine.sentencekit import (  # ★ 报告文本唯一实现
    split_sentences, strip_meta_prefix, pick_best,
    render_value, translate_key, clamp_text,
)

# 金额/占比/数量/人次的数字提取（保留原始写法，不改写、不换算）
_NUM_PATTERNS = [
    r"[-+]?\d[\d,]*(?:\.\d+)?\s*万元",
    r"[-+]?\d[\d,]*(?:\.\d+)?\s*元",
    r"[-+]?\d[\d,]*(?:\.\d+)?\s*%",
    r"[-+]?\d[\d,]*(?:\.\d+)?\s*笔",
    r"[-+]?\d[\d,]*(?:\.\d+)?\s*张",
    r"[-+]?\d[\d,]*(?:\.\d+)?\s*人",
    r"[-+]?\d[\d,]*(?:\.\d+)?\s*组",
    r"[-+]?\d[\d,]*(?:\.\d+)?\s*个月",
    r"[-+]?\d[\d,]*(?:\.\d+)?\s*家",
    r"[-+]?\d[\d,]*(?:\.\d+)?\s*次",
]


# 报告增强时拼入的方法论后缀标记（税务合规方法/影响/建议/法规依据）。
# 这些不是「核对到的事实」，其中的阈值文字（如「>=3张触发」）若被抽进 numbers 会污染线索链。
_METHODOLOGY_MARKERS = ("税务合规方法", "税务影响", "处理建议", "法规依据")


def _strip_methodology(detail: str) -> str:
    """剥掉报告增强（_enrich_short_findings）拼入的方法论后缀。

    ★ 2026-09-26 修复：短 finding 的 how_found（含「>=3张触发」阈值文字）会被拼进 detail，
       `extract_numbers(detail + " " + how)` 据此抽出了伪数字「3张」，导致线索链
       numbers 出现「-1,285,450.57元、13张、3张」三值，其中「3张」纯属方法论阈值而非事实。
       现只从**事实原文**抽数，方法论后缀一律丢弃。
    """
    s = str(detail or "")
    for mk in _METHODOLOGY_MARKERS:
        idx = s.find(mk)
        # 仅当标记出现在字段**中部**（idx>0）才剥——开头出现的视为事实原文，保留
        if idx > 0:
            s = s[:idx].rstrip("。；; ").rstrip()
    return s


def extract_numbers(text: str, limit: int = 8) -> List[str]:
    """从叙述文本中提取带单位的确定性数字串（原样保留，不做格式化）"""
    if not text:
        return []
    out, seen = [], set()
    for pat in _NUM_PATTERNS:
        for m in re.findall(pat, str(text)):
            s = m.strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
    # 补充无单位但显著的数字（如发票号、税率、笔数）
    if len(out) < 3:
        for m in re.findall(r"\d[\d,]*\.?\d*", str(text)):
            s = m.strip()
            if s and s not in seen and len(s) >= 2:
                seen.add(s)
                out.append(s)
            if len(out) >= limit:
                break
    return out[:limit]


def _metric_rows(metrics: Any) -> List[Tuple[str, str]]:
    """把 observed_metrics 摊平成 (指标名, 值)

    ★ 2026-09-25 根因修复：值一律经 `sentencekit.render_value` 渲染（**禁止 Python repr**）。
      旧实现对"值为 list[dict]"的指标用 `str(x)[:16]`，把内部结构截断后写进企业报告：

          「…—counterparty_count=2；examples=[{'counterparty':，{'counterparty'」

      企业内部数据结构泄漏给企业，且 `[`/`{` 被截断成**括号不闭合**的残句。
      现由 render_value 统一渲染：键名汉化、用中文分隔符、超出写「等N项」，绝不出现 { [ ' 等 repr 记号。
    """
    rows: List[Tuple[str, str]] = []
    if isinstance(metrics, dict):
        for k, v in metrics.items():
            vs = render_value(v, max_len=90)
            if vs:
                rows.append((translate_key(k), vs))
    elif isinstance(metrics, list):
        for i, v in enumerate(metrics[:8]):
            if isinstance(v, dict):
                k = v.get("name") or v.get("metric") or v.get("key") or f"指标{i+1}"
                rows.append((translate_key(k),
                             render_value(v.get("value") if "value" in v else v, max_len=80)))
            else:
                rows.append((f"指标{i+1}", render_value(v, max_len=80)))
    return rows


def _sources_of(finding: Dict) -> List[str]:
    """取发现所依据的资料来源"""
    srcs: List[str] = []
    for s in (finding.get("independent_sources") or []):
        if s and s not in srcs:
            srcs.append(str(s))
    for s in (finding.get("source_files") or []):
        if isinstance(s, dict):
            name = str(s.get("type") or s.get("file") or "")
        else:
            name = str(s)
        if name and name not in srcs:
            srcs.append(name)
    for key in ("data_sources", "evidence_sources"):
        for s in (finding.get(key) or []):
            if s and str(s) not in srcs:
                srcs.append(str(s))
    return srcs


def _sample_rows(finding: Dict, limit: int = 5) -> List[str]:
    """取代表性明细样本（逐笔/逐人）

    ★ 2026-09-25：改用 `sentencekit.render_value`（键名汉化、中文分隔符、禁止 repr）。
      旧实现 `"、".join(f"{k}={v}")` 对嵌套值会 `str(dict)` → 报告里出现
      `examples={'counterparty': '…'}` 这类内部结构。
    """
    rows = finding.get("evidence_rows") or finding.get("detail_rows") or []
    out: List[str] = []
    for r in rows[:limit]:
        s = render_value(r, max_len=120)
        if s:
            out.append(s)
    return out


def build_clue_chain(finding: Dict, redline: Dict, engine_data: Optional[Dict] = None) -> Dict:
    """
    构建单条发现的线索链。

    返回结构：
        {
          "redline_id", "redline_name",
          "sources_used": [...],                 # 本条线索实际使用的资料
          "nodes": [ {step, source, action, observed, trace_ref, has_data} ],
          "terminal_signal": "...",              # 终端信号（触红的具体数值）
          "numbers": [...],                      # 链路上出现的确定性数字
          "samples": [...],                      # 代表性明细
          "data_gaps": [...]                     # 本条线索想查但没资料的环节
        }
    """
    engine_data = engine_data or {}
    detail = str(finding.get("detail") or finding.get("description") or "")
    how = str(finding.get("how_found") or "")
    metrics = finding.get("observed_metrics")
    sources = _sources_of(finding)
    # ★ 2026-09-26：只从事实原文抽数，剥掉方法论后缀（避免「>=3张触发」等阈值被当事实数字）
    numbers = extract_numbers(_strip_methodology(detail))
    samples = _sample_rows(finding)

    nodes: List[Dict] = []
    template = list(redline.get("clue_chain") or [])

    if template:
        # 有红线模板：按模板骨架逐环落地，并把实际观察值填进去
        total = len(template)
        for i, tpl in enumerate(template):
            step_no = i + 1
            observed = ""
            has_data = True
            if step_no == 1:
                # 首环：资料来源与实际读取到的规模
                if sources:
                    observed = "已读取资料：" + "、".join(sources[:6])
                    if len(sources) > 6:
                        observed += f" 等{len(sources)}类"
                else:
                    observed = "本轮未取得该项资料"
                    has_data = False
            elif step_no == total:
                # 末环：终端信号（触红值）
                terminal = _terminal_signal(detail, numbers, finding)
                observed = terminal or "本轮未取得可量化的终端数据"
                has_data = bool(terminal)
            else:
                # 中间环：优先用指标，其次用叙述中的数字
                mrows = _metric_rows(metrics)
                if mrows:
                    observed = "；".join(f"{k}={v}" for k, v in mrows[:3])
                elif numbers:
                    observed = "计算得到：" + "、".join(numbers[:3])
                else:
                    observed = "本轮未取得该环节可量化数据"
                    has_data = False
            nodes.append({
                "step": step_no,
                "source": tpl.get("source", ""),
                "action": tpl.get("action", ""),
                "output": tpl.get("output", ""),
                "observed": observed,
                "trace_ref": f"底稿编号 {finding.get('scene_fact_id') or finding.get('fact_id') or '—'} "
                             f"第{step_no}环",
                "has_data": has_data,
            })
    else:
        # 无模板：退化为「资料 → 计算 → 结果」三环，仍要求每环有数字
        nodes = [
            {"step": 1, "source": "、".join(sources) or "本轮已上传并成功读取的资料",
             "action": "读取并归集与本项相关的记录",
             "output": "可复核的数据集",
             "observed": f"已读取{len(sources)}类资料" if sources else "本轮未取得该项资料",
             "trace_ref": f"底稿编号 {finding.get('scene_fact_id') or '—'} 第1环",
             "has_data": bool(sources)},
            {"step": 2, "source": detail[:60] or "—",
             "action": how or "按同一口径重新计算并比对",
             "output": "差异或异常指标",
             "observed": ("；".join(f"{k}={v}" for k, v in _metric_rows(metrics)[:3])
                          or ("计算得到：" + "、".join(numbers[:3]) if numbers else "本轮未取得可量化数据")),
             "trace_ref": f"底稿编号 {finding.get('scene_fact_id') or '—'} 第2环",
             "has_data": bool(metrics or numbers)},
            {"step": 3, "source": "上述比对结果",
             "action": "判断是否触碰红线构成要件",
             "output": redline.get("name", ""),
             "observed": _terminal_signal(detail, numbers, finding) or "本轮未取得终端数据",
             "trace_ref": f"底稿编号 {finding.get('scene_fact_id') or '—'} 第3环",
             "has_data": bool(_terminal_signal(detail, numbers, finding))},
        ]

    data_gaps = [
        {"step": n["step"], "gap": n["source"] or n["output"]}
        for n in nodes if not n.get("has_data")
    ]

    return {
        "redline_id": redline.get("id", ""),
        "redline_name": redline.get("name", ""),
        "sources_used": sources,
        "nodes": nodes,
        "terminal_signal": _terminal_signal(detail, numbers, finding),
        "numbers": numbers,
        "samples": samples,
        "data_gaps": data_gaps,
    }


def _terminal_signal(detail: str, numbers: List[str], finding: Dict) -> str:
    """
    终端信号：把「触红的具体数值」说清楚。
    优先取叙述中第一段带数字的句子（通常是结论句）。

    ★ 2026-09-25 修复：切句改用 `sentencekit.split_sentences`（**括号感知**）。
      旧实现 `re.split(r"[。；\n]", detail)` 会把括号内的分号当句末切点，
      切出「…（取销项发票不含税金额」这种**括号不闭合**的残句，
      而该残句会原样进企业报告（实测），一句话读不通即损害报告可信度。
      同时剥离源文本自带的前置语（"已经核实的事实是："），避免与报告引导语叠加。
    """
    if not detail:
        return ""
    sentences = split_sentences(str(detail))
    best = pick_best(sentences[:4]) or ""
    if best:
        return clamp_text(strip_meta_prefix(best), 180)
    if numbers:
        return "涉及金额与占比：" + "、".join(numbers[:4])
    return ""


def chain_text(chain: Dict) -> str:
    """把线索链压成一段可直读的话（报告用，大白话）"""
    nodes = chain.get("nodes") or []
    if not nodes:
        return ""
    parts = []
    for n in nodes:
        seg = f"第{n['step']}步，从「{n.get('source') or '—'}」{n.get('action') or ''}"
        if n.get("observed"):
            seg += f"，实际看到：{n['observed']}"
        parts.append(seg)
    return "；".join(parts) + "。"
