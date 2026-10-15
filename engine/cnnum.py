# -*- coding: utf-8 -*-
"""中文数字 ↔ 阿拉伯数字，**唯一权威实现**（用于法条条号等中文编号）。

## 为什么单独一个模块（实测，2026-10-15）
同一件事此前有 **5 处私有实现**，且**行为不一致**：

| 位置 | 方向 / 范围 | 后果 |
|---|---|---|
| `scripts/_gen_legal_index.py::cn2num` | 中文→int，个位/十/几十 | **「第一百零三条」解析不出** ⇒ `provision_id` 为 null |
| `scripts/_gen_legal_mappings.py::cn2num` | 中文→int，同上 | 同上（可确证的条款映射被误判为不可确证） |
| `scripts/_load_legal_texts_full.py::_cn_to_int` | 中文→int，含百/千 | 另：**排序键**在无「之N」时不乘 100 ⇒ 见下 |
| `engine/quality_gates.py::_cn_num` | 中文→int，一~二十 | **待收敛**（历史实现，属质量闸门域，本轮未动） |
| `engine/enterprise_report.py::_cn_num` | **int→中文**（反向） | 与前者**方向相反**，不算同类，仅同名 |

上一轮实测后果（**两处真事故**）：
1. 整部法全文入库后，条款索引 **1806 条拿不到 `provision_id`**（全是「第一百条」以上）
   —— 不是数据缺失，而是**解析器能力不足**被当成"解析不出"如实暴露；
2. **排序键错乱**：旧实现的排序键在**无「之N」时不乘 100**（`第十五条`→15、`第十五条之一`→1501）
   ⇒「第十六条」(16) 竟小于「第十五条之一」(1501)，被切分器判为"续行"而**吞掉条号**。
   修复后正文库再增 **440 条**（实测 6569 → 7009）。
⇒ 五份实现必然分叉，收敛为一份（闸门 `check_cnnum_single_source` 锁死）。

## 边界（本模块只做数字转换）
不判断"这是不是条文"（那是各切分器 / `legal_citation` 的职责）。相邻三层**不得互相替代**：
- `engine/numparse.py` —— 数值**文本**解析（`"12,000.00"` → `12000.0`，含 `￥`/千分位）
- `engine/findingkit.py` —— **月份**键（`YYYYMM`）
- `engine/cnnum.py`（本模块）—— **中文数字**（`"一百零三"` → `103`）
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9}
_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}
_CN_ALL = "".join(_DIGITS) + "".join(_UNITS)

#: 条号：`第一百零三条` / `第十五条` / `第十条`（可带「之一/之二…」）
_ARTICLE_RE = re.compile(rf"^第([{_CN_ALL}]+)条(?:之([{_CN_ALL}]+))?$")


def cn_to_int(s: str) -> Optional[int]:
    """中文数字 → int。解析不出 ⇒ `None`（**不猜、不兜底为 0**）。

    >>> cn_to_int("十五"), cn_to_int("一百零三"), cn_to_int("二千零一十五")
    (15, 103, 2015)
    """
    t = str(s or "").strip()
    if not t:
        return None
    if t.isdigit():                                   # 已经就是阿拉伯数字
        return int(t)
    total = 0        # 已结算部分
    section = 0      # 当前千位以内
    number = 0       # 待用数字
    seen = False
    for ch in t:
        if ch in _DIGITS:
            number = _DIGITS[ch]
            seen = True
        elif ch in _UNITS:
            unit = _UNITS[ch]
            if unit == 10000:
                section = (section + (number or 1)) * unit
                total += section
                section = 0
            else:
                section += (number or 1) * unit
            number = 0
            seen = True
        else:
            return None
    if not seen:
        return None
    val = total + section + number
    return val if val > 0 else None


def parse_article(article: str) -> Tuple[Optional[int], Optional[int]]:
    """解析条号 → `(条号数字, 之N 序号)`。

    >>> parse_article("第一百零三条")
    (103, None)
    >>> parse_article("第十五条之一")
    (15, 1)
    >>> parse_article("附录一")
    (None, None)
    """
    m = _ARTICLE_RE.match(str(article or "").strip())
    if not m:
        return None, None
    return cn_to_int(m.group(1)), (cn_to_int(m.group(2)) if m.group(2) else None)


def article_sort_key(article: str) -> int:
    """条号 → **排序键**（同法内排序用）。带「之一」排在本条与下一条之间。

    解析不出 ⇒ 一个很大的数（排在最后，不干扰正常排序）。
    """
    num, sub = parse_article(article)
    if num is None:
        return 10 ** 9
    return num * 100 + (sub or 0)
