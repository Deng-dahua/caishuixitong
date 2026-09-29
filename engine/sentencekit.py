# -*- coding: utf-8 -*-
"""文本切句与前置语剥离的**唯一权威**（2026-09-25）

═══════════════════════════════════════════════════════════════════════════════
为什么需要它（根因）
═══════════════════════════════════════════════════════════════════════════════
句读切分在全项目写过 **5 遍**：`clue_chain._terminal_signal`、
`enterprise_report._extract_core_sentence`、`agents/coordinator`、`pipeline`、
`text_guardrails`，写法都是朴素的：

    re.split(r"[。；\\n]", text)

朴素切分对**括号内的分号**会切错。真实事故（企业报告正文）：

    原始 detail：…已经核实的事实是：凭证费用合计 44,394,561.24元，收入口径
    6,636,800.57元（取销项发票不含税金额；若以申报收入 0.00元计则更高），费用率 668.9%…

朴素切分把「（取销项发票不含税金额；若以申报收入 0.00元计则更高）」从中间切开，
报告里就出现一句 **括号不闭合、读不通** 的"事实"：

    「本轮从所报资料中直接核对到的事实是：…收入口径 6,636,800.57元（取销项发票不含税金额」

审计报告是要给企业看的对外文书，一句话读不通即损害可信度。故句读切分必须**括号感知**：
（）、()、「」、《》、【】、“”、[]、{}  内部一律不切。

另附 `strip_meta_prefix`：拼接事实句时先剥掉源文本自带的"已经核实的事实是："这类前置语，
否则会与我方引导语叠加成「本轮…核对到的事实是：已经核实的事实是：…」。
"""

from __future__ import annotations

import re
from typing import Any, Iterable, List, Optional

# 中文/英文括号对（开 → 闭）
_BRACKET_PAIRS = {
    "（": "）", "(": ")",
    "「": "」", "『": "』",
    "《": "》", "〈": "〉",
    "【": "】", "[": "]",
    "“": "”", "‘": "’",
    "{": "}", "〔": "〕", "［": "］",
}
_OPENERS = set(_BRACKET_PAIRS.keys())
_CLOSERS = set(_BRACKET_PAIRS.values())

# 句末标点（默认切点）
DEFAULT_DELIMS = "。；\n!?！？"


def split_sentences(text: str, delims: str = DEFAULT_DELIMS,
                    keep_delims: bool = False) -> List[str]:
    """括号感知的句子切分。

    只在一层括号**之外**遇到 `delims` 时才切；括号内的句读一律保留。
    `keep_delims=True` 时把分隔符保留在前一片段末尾（用于原样回拼）。
    """
    s = str(text or "")
    if not s:
        return []
    out: List[str] = []
    buf: List[str] = []
    depth = 0
    for ch in s:
        if ch in _OPENERS:
            depth += 1
        elif ch in _CLOSERS and depth > 0:
            depth -= 1
        if ch in delims and depth == 0:
            if keep_delims:
                buf.append(ch)
                out.append("".join(buf))
            elif "".join(buf).strip():
                out.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    if "".join(buf).strip():
        out.append("".join(buf))
    return out


def is_balanced(text: str) -> bool:
    """括号是否闭合（成对）。用于拦截"切出来就残缺"的片段。"""
    s = str(text or "")
    stack: List[str] = []
    for ch in s:
        if ch in _OPENERS:
            stack.append(_BRACKET_PAIRS[ch])
        elif ch in _CLOSERS:
            if not stack or stack[-1] != ch:
                return False
            stack.pop()
    return not stack


def first_sentence(text: str, delims: str = DEFAULT_DELIMS) -> str:
    """取第一句（括号感知）；空串返回空串。"""
    parts = split_sentences(text, delims=delims)
    return parts[0].strip() if parts else ""


# 源文本自带的前置语（拼接事实句前须剥掉，避免与我方引导语叠加）
_META_PREFIXES = (
    "已经核实的事实是：", "已核实的事实是：", "核实的事实是：",
    "已经核实的事实：", "已核实的事实：",
    "已核实：", "经核实：", "核实：", "经核对：", "核对结果：",
    "已经查明：", "已查明：", "经查：", "经查发现：",
    "事实是：", "事实：", "结论是：", "分析结果：", "计算结果：",
)
# 去掉行首的项目符号/编号（如「· xxx」「① xxx」）
# ★ 2026-09-26 修复：字符类**不再含裸数字 \d**。
#   旧实现 `^[\s·•\-\*\u2460-\u2473\d\.、\)）]{1,6}` 把「13张」「6名」等量词前的计数
#   当成列表编号前缀剥掉，导致报告出现「张发票被红冲…」（13 丢失）、「名员工…」（6 丢失）。
_LEAD_MARK = re.compile(r"^[\s·•\-\*\u2460-\u2473\.、\)）]{1,6}")
# 仅当数字后**紧跟编号分隔符**（. 、 ) ））才视为列表编号（如「1. xxx」「2) xxx」「3、xxx」）。
# 注意：裸数字 + 中文量词（「13张」「6名」）不匹配，从而被保留。
_LEAD_NUM = re.compile(r"^\d{1,3}[\.、\)）]")


def strip_meta_prefix(text: str, strip_marks: bool = True) -> str:
    """剥掉源文本自带的前置语与行首编号，便于安全地拼接引导语。"""
    s = str(text or "").strip()
    changed = True
    while changed and s:
        changed = False
        for p in sorted(_META_PREFIXES, key=len, reverse=True):
            if s.startswith(p):
                s = s[len(p):].lstrip()
                changed = True
        if strip_marks:
            m = _LEAD_MARK.match(s)
            # 仅当剥掉后仍非空时才剥（避免把「· 」这类空标记残留）
            if m and len(s) > m.end():
                s = s[m.end():].lstrip()
                changed = True
            # 列表编号（数字 + 分隔符），如「1. 」「2) 」
            m = _LEAD_NUM.match(s)
            if m and len(s) > m.end():
                s = s[m.end():].lstrip()
                changed = True
    return s


def join_cn(items: Iterable, sep: str = "；") -> str:
    """把若干片段用中文分隔符连成一句（去空、去重保序）。"""
    out: List[str] = []
    for x in items or []:
        s = str(x or "").strip()
        if s and s not in out:
            out.append(s)
    return sep.join(out)


def pick_best(sentences: Iterable[str], require_digit: bool = True,
              require_balanced: bool = True) -> Optional[str]:
    """从候选句中挑最"有信息量"的一句：含数字、括号闭合、最长者优先。"""
    best: Optional[str] = None
    for s in sentences or []:
        t = str(s or "").strip()
        if not t:
            continue
        if require_digit and not re.search(r"\d", t):
            continue
        if require_balanced and not is_balanced(t):
            continue
        if best is None or len(t) > len(best):
            best = t
    return best


# ═══════════════════════════════════════════════════════════════════════════════
# 内部值 → 报告可读文本
# ═══════════════════════════════════════════════════════════════════════════════
# 为什么需要（真实事故）：`clue_chain._metric_rows` 对"值为 list[dict]"的指标
# 用 `str(x)[:16]` 渲染，直接把 **Python repr** 截断后写进企业报告：
#
#     第2环：按收款人归集金额与频次，剔除已申报工资与报销——counterparty_count=2；
#           examples=[{'counterparty':，{'counterparty'
#
# 结果：企业内部数据结构泄漏给企业，且 `[` `{` 被截断成**括号不闭合**的残句。
# 铁律：**报告文本永远不得出现 Python repr**（`{...}` `[...]` `'key':`）。
# 渲染一律用中文分隔符（、；）与「键=值」，并给出"等N项"而不是截断括号。

_MAX_DEPTH = 3


def _join_parts(parts: List[str], max_len: int, sep: str = "、", overflow: str = "") -> str:
    """按 `max_len` 拼装「键=值 / 元素」列表——**整项取舍，绝不把某一项从中间切开**。

    ★ 2026-09-29（点评整改 P0-9c）真实事故：嵌套字典按 `max_len=min(90,30)` 拼装时
      朴素切片产生「…进数量=1,680.00、差异=-2,3…」——**金额被切半截**，
      读起来像真数字（外部点评实测 "=260,5" "=275,00"）。
      规则：逐项累加，放不下即停；被省略的项用 `overflow` 如实标注（如「等5项」）。
      这样"截断"丢的是**完整的一项**，保留下来的每一项都是完整键值对。
    """
    kept: List[str] = []
    total = len(parts)
    for p in parts:
        if kept and len(sep.join(kept + [p])) > max_len:
            break
        kept.append(p)
    s = sep.join(kept)
    if len(kept) < total:
        s = (s + (overflow or ("等%d项" % total))) if s else ("共%d项" % total)
    return s


def render_value(v: Any, max_len: int = 90, _depth: int = 0) -> str:
    """把内部值渲染成**可读中文串**：不出 repr、不出方括号/花括号、长度受限。

    · `None` → 空串；布尔 → 是/否；浮点 → 千分位两位小数
    · `dict` → `键=值` 用「、」连接（键名可先经 `translate_key` 汉化）
    · `list` → 元素用「、」连接，超出 3 项写「等N项」
    · 字符串 → 去空白并按 `max_len` 截断（截断处加「…」）
    """
    if v is None:
        return ""
    if isinstance(v, bool):
        return "是" if v else "否"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return f"{v:,.2f}" if abs(v) < 1e12 else f"{v:,.0f}"
    if isinstance(v, str):
        # 安全截断：不把括号切断（否则报告里出现悬空左括号）
        return clamp_text(v, max_len)
    if _depth >= _MAX_DEPTH:
        return "…" if v else ""
    if isinstance(v, dict):
        parts: List[str] = []
        for k, vv in list(v.items())[:6]:
            sv = render_value(vv, max_len=min(max_len, 30), _depth=_depth + 1)
            if not sv:
                continue
            parts.append(f"{translate_key(k)}={sv}")
        return _join_parts(parts, max_len)
    if isinstance(v, (list, tuple, set)):
        seq = list(v)
        # 同构 dict 列表（如 [{'name':'甲'},{'name':'乙'}]）→ 只取值并列，
        # 否则会渲染成「人员=甲、人员=乙」这种重复啰嗦的串（实测）。
        if seq and all(isinstance(x, dict) for x in seq):
            keys = {tuple(x.keys()) for x in seq}
            if len(keys) == 1:
                shared = list(keys)[0]
                if len(shared) == 1:
                    only = shared[0]
                    parts = [render_value(x.get(only), max_len=min(max_len, 40),
                                          _depth=_depth + 1) for x in seq[:3]]
                    parts = [p for p in parts if p]
                    return _join_parts(parts, max_len,
                                       overflow=("等%d项" % len(seq)) if len(seq) > 3 else "")
        parts = [render_value(x, max_len=min(max_len, 40), _depth=_depth + 1) for x in seq[:3]]
        parts = [p for p in parts if p]
        return _join_parts(parts, max_len,
                           overflow=("等%d项" % len(seq)) if len(seq) > 3 else "")
    # ★ 2026-09-29：标量兜底同样不得朴素切片（数字被切半截 → 报告出现 "260,5"）。
    return clamp_text(str(v), max_len)


def clamp_text(text: Any, max_len: int = 200, ellipsis: str = "…") -> str:
    """**安全截断**：不把括号切断，超出长度时优先在句读处收尾。

    真实事故：`inspector_reasoning` 用 `(f["detail"] or "")[:200]` 朴素截断，
    把「…现实中存在三种可能：①客户赊账未付（应收账」切成悬空左括号，
    该残句原样进企业报告（`inspector_reasoning.key_clues[].detail`）。

    策略：① 长度内 → 原样；
          ② `max_len` 之前最后一个句读处收尾（且收尾后括号须闭合）；
          ③ 都不行 → 在 `max_len` 处切，并**补上未闭合的右括号**。

    ★ 2026-09-29（点评整改 P0-9c）：句读集合**加入顿号「、」与竖线「｜」**。
      真实事故：键值对串「货物=饲料、销数量=65.00、进数量=1,680.00、差异=-1,680.00」
      按 max_len=30 截断时，若不认顿号为句读，就会硬切在千分位之间 →
      「…进数量=1,680.00、差异=-1,6」，报告里出现看似真数字的**残句**。
      顿号/竖线是列表分隔符，在它们处收尾是自然且无损的（丢的是完整一项）。
    """
    s = str(text or "").strip()
    if not s or len(s) <= max_len:
        return s
    window = s[:max_len + 1]
    for m in reversed(list(re.finditer(r"[。；!?！？\n、｜]", window))):
        cand = s[:m.start()]
        if cand.strip() and is_balanced(cand):
            return cand.strip() + ellipsis
    return close_brackets(s[:max_len]) + ellipsis


def close_brackets(text: Any) -> str:
    """补上未闭合的右括号（仅供"截断后收尾"使用，不改动已有内容）。"""
    s = str(text or "")
    stack: List[str] = []
    for ch in s:
        if ch in _OPENERS:
            stack.append(_BRACKET_PAIRS[ch])
        elif ch in _CLOSERS and stack and stack[-1] == ch:
            stack.pop()
    return s + "".join(reversed(stack))


_KEY_CN_CACHE: Optional[dict] = None

# ── Python repr → 可读中文（诊断日志出口的统一净化）──────────────────────────────
# 真实事故：`pipeline_log` 里出现
#     「11层连续未触发已标记待验证: ['任务与权限', '资料接收保全', …]」
#     「加工信号评分: 0.00, signals=['进销品名差异(纯服务业-不构成加工信号)', …], applicable=False」
#     「通道=['国家企业信用信息公示系统', '搜索引擎综合核实', …]」
# 这些是 Python 列表/字典的 repr，直接进了报告数据（前端日志面板会展示）。
# 与其逐个调用点改（会漏、会复发），在**日志出口**统一净化一次。
# ⚠ 只处理**带引号的** repr 结构，不会误伤 `[PROFILE]`、`[修正验证]` 这类中文方括号前缀。
_REPR_STR = r"(?:'[^']*'|\"[^\"]*\")"
_REPR_LIST_RE = re.compile(r"\[\s*" + _REPR_STR + r"(?:\s*,\s*" + _REPR_STR + r")*\s*\]")
_REPR_DICT_RE = re.compile(r"\{\s*" + _REPR_STR + r"\s*:\s*[^{}]*?"
                           r"(?:\s*,\s*" + _REPR_STR + r"\s*:\s*[^{}]*?)*\s*\}")
_QUOTE_STRIP = re.compile(r"^['\"]|['\"]$")


def _split_repr_items(body: str) -> List[str]:
    """按顶层逗号切分（引号内的逗号不算）。"""
    items, buf, quote = [], [], ""
    for ch in body:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = ""
            continue
        if ch in "'\"":
            quote = ch
            buf.append(ch)
        elif ch == ",":
            items.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        items.append("".join(buf))
    return items


def humanise_repr(text: Any) -> str:
    """把字符串里的 Python repr（列表/字典）转成可读中文；其余内容原样保留。

    `['甲', '乙']` → `甲、乙`；`{'k': 'v', 'n': 1}` → `k=v、n=1`。
    嵌套结构反复处理至稳定（最多 3 轮）。
    """
    s = str(text or "")
    for _ in range(3):
        prev = s

        def _list_cn(m):
            body = m.group(0)[1:-1]
            vals = [_QUOTE_STRIP.sub("", x.strip()) for x in _split_repr_items(body)]
            return "、".join(v for v in vals if v)

        def _dict_cn(m):
            body = m.group(0)[1:-1]
            parts = []
            for x in _split_repr_items(body):
                k, sep, v = x.partition(":")
                if not sep:
                    continue
                kk = _QUOTE_STRIP.sub("", k.strip())
                vv = _QUOTE_STRIP.sub("", v.strip())
                if kk:
                    parts.append(f"{kk}={vv}" if vv else kk)
            return "、".join(parts)

        s = _REPR_DICT_RE.sub(_dict_cn, s)
        s = _REPR_LIST_RE.sub(_list_cn, s)
        if s == prev:
            break
    return s


# 中文语境下的半角标点 → 全角（左侧是中文即视为中文语境；左侧是 ASCII 一律不动）
_CJK_PUNCT_RULES = (
    # 左侧是中文即视为中文语境（右侧可为中文或数字，覆盖「完成: 0个集群」）；
    # 左侧是 ASCII（如 `16/21`、`SKU:ABC`）一律不动。
    (re.compile(r"(?<=[\u4e00-\u9fa5])\s*,\s*(?=[\u4e00-\u9fa5\d])"), "，"),
    (re.compile(r"(?<=[\u4e00-\u9fa5])\s*;\s*(?=[\u4e00-\u9fa5\d])"), "；"),
    (re.compile(r"(?<=[\u4e00-\u9fa5])\s*:\s*(?=[\u4e00-\u9fa5\d])"), "："),
    # 句末句点：中文后紧跟半角 . 且其后**非数字/字母**（保护小数 `0.00` 与
    # 文件扩展名 `序时账.xlsx`，二者都不是句末标点）→ 。
    (re.compile(r"(?<=[\u4e00-\u9fa5])\.(?![0-9A-Za-z])"), "。"),
    # 叹号 / 问号：中文后 → 全角
    (re.compile(r"(?<=[\u4e00-\u9fa5])!"), "！"),
    (re.compile(r"(?<=[\u4e00-\u9fa5])\?"), "？"),
    # 悬空顿号（顿号紧邻其他句读）→ 去掉顿号，避免「、；」「、，」这类双标点
    (re.compile(r"、\s*(?=[，。；：、！？,;:!?])"), ""),
    # 重复句读折叠为一个（`。。`→`。`、`；；`→`；`）
    (re.compile(r"([，。；：、！？])\1+"), r"\1"),
)

# 半角圆括号 → 全角：**整对**替换以保证左右成对（绝不产生 `(…）` 半对）。
# 命中两种中文语境：① 括号**紧跟在中文之后**（`张(41.70%)`）；② 括号**内含中文**（`(收款方, 付款方)`）。
_PAREN_AFTER_CJK_RE = re.compile(r"(?<=[\u4e00-\u9fa5])\s*\(([^()]{1,80})\)")
_PLAIN_PAREN_RE = re.compile(r"\(([^()]{1,80})\)")
# 兜底：残留的、位于中文后的半角右括号 → 全角（此规则在成对替换之后执行）
_STRAY_CLOSER_RE = re.compile(r"(?<=[\u4e00-\u9fa5])\s*\)")


def _cn_paren(m: "re.Match") -> str:
    return f"（{m.group(1)}）"


def _cn_paren_if_cjk(m: "re.Match") -> str:
    return f"（{m.group(1)}）" if re.search(r"[\u4e00-\u9fa5]", m.group(1)) else m.group(0)


def normalize_cjk_punct(text: Any) -> str:
    """把中文语境下的半角标点改成全角（`模块, 跳过` → `模块，跳过`）。

    真实事故：`[ORCHESTRATOR] 激活16/21个模块, 跳过5个. 分布: 分析:7` 这类日志
    与部分明细用半角逗号，混在中文里（`(收款方, 付款方)`）读起来是"没写好的中文"；
    报告正文还实测有 **1315 处** `有限公司(396,887元)` 这类半角括号 ——
    自 2026-09-27 起本函数接入报告净化收敛点 `enterprise_report._zh_normalize_obj`。

    ⚠ 只在**中文语境**（括号紧跟在中文后，或括号内含中文）时替换；
      `分析:7`、`16/21`、`SKU:ABC`、`0.00`、`ABC(1)` 等一律不动。
    """
    s = str(text or "")
    for pat, repl in _CJK_PUNCT_RULES:
        s = pat.sub(repl, s)
    # 圆括号**整对**转换，避免半对；随后再把中文后的残留右括号兜底为全角
    s = _PAREN_AFTER_CJK_RE.sub(_cn_paren, s)      # 中文后紧跟的括号（内容不限）
    s = _PLAIN_PAREN_RE.sub(_cn_paren_if_cjk, s)   # 其余：仅当括号内含中文
    s = _STRAY_CLOSER_RE.sub("）", s)
    return s


def humanise_log_lines(log: Any) -> List[str]:
    """诊断日志列表的统一净化（出口调用一次，覆盖全部现有与未来日志行）。

    ① `humanise_repr`：清掉 Python repr；
    ② `neutralise_output_text`：日志同样会展示在前端日志面板，内部术语（线索链/证据链/
       裁决/竞争假设…）一并通过**文字护栏**换成业务语言（唯一出处，不在本模块另写一份）。
    """
    if not isinstance(log, list):
        return log
    try:
        from engine.text_guardrails import neutralise_output_text as _nt
    except Exception:  # noqa: BLE001
        _nt = None
    out: List[str] = []
    for x in log:
        if not isinstance(x, str):
            out.append(x)
            continue
        s = normalize_cjk_punct(humanise_repr(x))
        if _nt is not None:
            try:
                s = _nt(s)
            except Exception:  # noqa: BLE001
                pass
        out.append(s)
    return out


def translate_key(key: Any) -> str:
    """把英文指标/字段键汉化成中文标签（复用 `enterprise_report` 的词表，唯一来源）。

    **延迟导入**：`enterprise_report` 不依赖本模块，故此处导入安全；
    延迟到调用时是为了避免模块导入期互相牵连。
    """
    global _KEY_CN_CACHE
    k = str(key or "").strip()
    if not k:
        return ""
    if _KEY_CN_CACHE is None:
        try:
            from engine.enterprise_report import _translate_key as _tk
            _KEY_CN_CACHE = {"_fn": _tk}
        except Exception:  # noqa: BLE001
            _KEY_CN_CACHE = {"_fn": None}
    fn = _KEY_CN_CACHE.get("_fn")
    if fn is not None:
        try:
            out = fn(k)
            return str(out or k)
        except Exception:  # noqa: BLE001
            return k
    return k


def render_kv_rows(mapping: Any, limit: int = 6) -> List[str]:
    """把 dict 渲染成若干 `键=值` 行（键汉化、值可读、无 repr）。"""
    rows: List[str] = []
    if not isinstance(mapping, dict):
        return rows
    for k, v in list(mapping.items())[:limit]:
        sv = render_value(v)
        if not sv:
            continue
        rows.append(f"{translate_key(k)}={sv}")
    return rows
