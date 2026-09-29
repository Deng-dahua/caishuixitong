# -*- coding: utf-8 -*-
"""章节内**模板句去重** —— 「通用口径只说一次」的落实点（外部点评 P1-8 / P2-7）。

## 问题

多条同类条目各自带**同一段通用说明**，逐条重复。实测第二章「资料接收与保全」的每条
narrative 都以同一句结尾（9 条 = 9 次）：

> 以上资料经逐份读取解析，N 份读取完整。本轮使用范围为：全部可进入本轮自动核对。
> 文件指纹、解析回执、复算指标和逐行定位保留在内部资料底稿中，可按文件名回查。

点评原话：「篇幅 11.3 万字、**模板重复约四成**」。这类重复不改变任何结论，
纯粹降低可读性，且让读者以为每条都有独立信息。

## 做法（与报告风格 S6 一致）

在**同一章的一组条目**里，检测被 ≥N 条**共同拥有**的结尾模板（长度 ≥L），
把它**抽到章首说一次**（`chapter_note`），条目内只保留差异部分。
判据：归一化后（去空白/数字差异）的**公共后缀**，不是"相同即删"——
因为模板里常带"2 份/3 份"这类随条目变化的数字。

阈值外置（`_MIN_REPEAT` / `_MIN_TAIL_LEN`），新增章节只需在调用处加一个键名。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

_MIN_REPEAT = 3      # 至少这么多条共有才算"模板"
_MIN_TAIL_LEN = 20   # 模板最短长度
_MAX_STEPS = 6       # 逐步加长公共后缀的最大轮次（防 O(n²) 过大）
# ★ 折叠保护：**不得把条目剥空**。若各条只差数字（归一化后完全相同），
#   "最长公共后缀"就是整条 → 会把条目剥空。判据不看"折叠比例"（真模板往往与条目共用句式，
#   比例可以很大），而看**剥完还剩不剩差异**：
#     · 每条剩余 ≥ _MIN_REMAIN 字；
#     · 剩余部分归一化后**至少 2 种**（否则各条本无差异，折叠无意义且会剥空）。
_MIN_REMAIN = 8

_DIGIT = re.compile(r"\d+(?:\.\d+)?")


def _norm(s: str) -> str:
    """**长度保持**的归一化：数字→`#`、空白→`_`，其余原样。

    ★ 必须长度保持，否则"公共后缀有多长"无法从归一化串长度反推回原文长度。
      （第一版把标点也去掉 → 长度缩水 → 长度守卫恒不成立，模板永远抽不出来。）
    """
    return re.sub(r"\d", "#", re.sub(r"\s", "_", str(s or "")))


def _longest_common_suffix(texts: List[str]) -> int:
    """所有文本的**最长公共后缀**长度（逐字符从尾部比较，归一化后比较）。

    ★ 固定窗口比较找不出"变长公共后缀"：各条的文件名长度不同，
      窗口一大就不匹配、一小就切在文件名中间（实测第一版只折叠了 1 条）。
    """
    if not texts:
        return 0
    norms = [_norm(t) for t in texts]
    m = min(len(t) for t in norms)
    k = 0
    while k < m:
        ch = norms[0][-1 - k]
        if any(nm[-1 - k] != ch for nm in norms):
            break
        k += 1
    return k


def _candidate_tail_len(items: List[Dict[str, Any]], text_key: str) -> int:
    texts = [str(it.get(text_key) or "") for it in items if isinstance(it, dict)]
    texts = [t for t in texts if t]
    if len(texts) < _MIN_REPEAT:
        return 0
    return _longest_common_suffix(texts)


def collapse_common_tail(items: Any, text_key: str = "narrative") -> Tuple[Any, str]:
    """把一组条目里**共有的结尾模板**抽出来。

    返回 `(新条目列表, chapter_note)`：
      · 条目内该模板被剥掉（保留各自的差异部分）；
      · `chapter_note` 为"抽出来的那段通用说明"（章首渲染一次；抽不出则为空串）。
    """
    if not isinstance(items, list) or len(items) < _MIN_REPEAT:
        return items, ""
    try:
        n = _candidate_tail_len(items, text_key)
    except Exception:
        return items, ""
    if n < _MIN_TAIL_LEN:
        return items, ""
    texts = [str(it.get(text_key) or "") if isinstance(it, dict) else "" for it in items]
    _cands = [t[-n:] for t in texts if len(t) >= n]
    if not _cands:
        return items, ""
    # ★ 剥完必须还剩**有差异**的内容（否则"折叠"等于把条目全删）
    _remains = [t[: len(t) - n].strip() for t in texts if len(t) >= n]
    if not _remains:
        return items, ""
    if len({_norm(r) for r in _remains}) < 2:
        return items, ""
    _too_short = [r for r in _remains if len(r) < _MIN_REMAIN]
    if len(_too_short) > max(0, len(texts) - _MIN_REPEAT):
        return items, ""
    # 取**最短的那版**作为章首说明：最短者不含各条特有的前后缀，最接近"通用说明"本意
    _raw_tail = min(_cands, key=len).strip()
    note = _raw_tail
    # 公共后缀的起点可能落在某个词/文件名中间（实测开头是".Excel。"）→ 从第一个句读处起读，
    # 使章首说明是一句完整的话（被剥掉的多余片段本就是各条的特有噪声）。
    # ⚠ 剥离时仍须用**未修剪的 `_raw_tail`** 比对（用修剪后的 note 比对会恒不匹配，
    #   实测第一版因此"说明抽出来了、条目却没剥掉"）。
    _cut = -1
    for _i, _ch in enumerate(note[:30]):
        if _ch in "。；！？":
            _cut = _i
            break
    if _cut >= 0:
        note = note[_cut + 1:].strip()
    if len(note) < _MIN_TAIL_LEN:
        return items, ""
    out: List[Any] = []
    for it in items:
        if not isinstance(it, dict):
            out.append(it)
            continue
        t = str(it.get(text_key) or "")
        if len(t) >= n and _norm(t[-n:]) == _norm(_raw_tail):
            it2 = dict(it)
            it2[text_key] = t[: len(t) - n].strip()
            it2["_template_collapsed"] = True
            out.append(it2)
        else:
            out.append(it)
    return out, ("本章各条目共用的通用说明（为避免逐条重复，在此统一说明一次）：" + note)
