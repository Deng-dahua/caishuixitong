# -*- coding: utf-8 -*-
"""解析与标准化**增强**（P1-1）—— 解析器**性能**与**行数上限**的唯一权威。

## 解决什么（全部源自《P0 验收报告》§5，均为实测取证）

| 编号 | 问题 | 实证 |
|---|---|---|
| §5-② | 行读取复杂度 **O(n²)** | 200 行 0.57s → 1,000 行 11.56s → 3,000 行 100.0s → **5,000 行 277.6s**；`耗时/n²` 恒定 11~14 µs |
| §5-③ | 行数上限**静默截断** | `main.py` 30+ 处 `min(nrows, N)`，超出部分**无任何回执**（用户以为全读了） |
| §5-④ | `nrows is None` 未防御 | 缺 worksheet dimension 的 xlsx 以 `read_only` 打开时 `max_row is None` ⇒ `min(nrows, N)` 抛 `TypeError`，被上层 `except` 吞掉 ⇒ 对外只表现为"无法识别" |

根因（§5-②）：`main._get_row_values` 在 openpyxl `read_only` 模式下**逐行**调用
`iter_rows(min_row=…, max_row=…)`，而 read_only 的区间读**每次都要从文件头流式跳过前 N 行**
（无随机访问索引）⇒ 总代价 `ΣO(r) = O(n²)`。

## 修法（都不改语义，只改复杂度与补回执）

1. **顺序游标 + 增量消费**（`iter_rows_range`）：同一 sheet 上维持**一个**流式迭代器，
   顺序前进时只消费增量 ⇒ 顺序访问总代价 **O(n)**；仅在"跳转/回退"时退回区间读
   （与原实现逐元素等价，正确性优先）。
2. **安全行数**（`safe_nrows`）：`nrows` 为空/非法 ⇒ 回退 `sheet.max_row`，再不行返回 0
   （**不猜**，不伪造一个数字）。
3. **上限登记 + 截断回执**（`ROW_CAPS` / `truncation_note`）：上限值集中登记；
   `main.py` 的既有字面量**不动**（"不修改已有功能"），由闸门
   `check_row_cap_manifest` 断言「源码实测集合 == 登记集合」，漂移即 ERROR。

## 铁律

- **不改解析结果**：同一表同数据 ⇒ 行数与内容**逐字节一致**（`tests/test_parse_enhance.py`
  用"优化前后比对"断言这一点）。
- **缺失 ≠ 0**：取不到行数返回 0 并**如实标注**，不静默顶替。
- **单一权威**：性能优化与上限登记只此一处；`main.py` 只做同行内薄转发。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

__all__ = [
    "ROW_CAPS", "CAP_KINDS", "MAX_ROW_CAP",
    "safe_nrows", "iter_rows_range", "drop_cursor", "reset_cursors",
    "row_cap", "source_literals", "manifest", "truncation_note",
    "truncated", "row_cap_note",
]

# ══════════════════════════════════════════════════════════════════════════
# ① 行数上限登记表（★ 唯一权威：新增/修改上限只加这里一行）
# ══════════════════════════════════════════════════════════════════════════
#: 值 → 语义。`main.py` 的 `min(nrows, N)` 里出现的**每个 N 都必须登记在此**
#: （闸门 `check_row_cap_manifest` 断言源码集合 ⊆ 本表键集合，反之亦然）。
ROW_CAPS: Dict[int, str] = {
    5000: "核心明细表（序时账 / 银行流水 / 发票 / 存货 / 科目余额）",
    3000: "中等明细表（工资 / 成本费用 / 申报明细）",
    2000: "申报类 / 合同类 / 表头探测扫描",
    1000: "科目余额类（辅助账）",
    500: "抽样（宽表）",
    200: "抽样（中等）",
    120: "抽样（窄表）",
    50: "样例（宽表）",
    30: "样例（中等）",
    15: "样例（窄表）",
    12: "样例（极窄）",
    4: "键值对探测（表头附近）",
}

#: 上限的"种类"（供接口与前端分组呈现；**不是**第二个上限表）
CAP_KINDS: Dict[str, str] = {
    "明细数据": "决定**真正进入分析**的行数上限（超限即截断）",
    "抽样样例": "仅用于表头/字段推断的少量抽样，不限制数据读入",
    "探测": "结构探测用（键值对 / 表头定位）",
}

MAX_ROW_CAP: int = max(ROW_CAPS) if ROW_CAPS else 0


def row_cap(kind: Any) -> Optional[int]:
    """按值取登记说明对应的上限；未登记返回 `None`（**不猜**）。"""
    try:
        v = int(kind)
    except (TypeError, ValueError):
        return None
    return v if v in ROW_CAPS else None


def cap_note(cap: Any) -> str:
    """上限的中文说明；未登记时**如实说未登记**（不冒用相近值）。"""
    try:
        v = int(cap)
    except (TypeError, ValueError):
        return "上限值无效"
    if v in ROW_CAPS:
        return str(ROW_CAPS[v])
    return "未登记的上限值 %d（请在 engine/parse_enhance.ROW_CAPS 补登记）" % v


# ══════════════════════════════════════════════════════════════════════════
# ② 安全行数（修 §5-④）
# ══════════════════════════════════════════════════════════════════════════
def safe_nrows(sheet: Any, nrows: Any = None) -> int:
    """安全行数：`nrows` 为空/非法 ⇒ 回退 `sheet.max_row` ⇒ 再不行返回 0。

    ★ 为什么需要：openpyxl `read_only=True` 打开**缺 worksheet dimension** 的 xlsx
      （如 `write_only=True` 生成、或部分第三方导出）时 `worksheet.max_row is None`
      ⇒ 原 `min(max_scan + 1, nrows)` 抛
      `TypeError: '<' not supported between instances of 'NoneType' and 'int'`，
      被 `_parse_excel_structured` 的 `except` 吞掉 ⇒ 对外**只表现为"无法识别"**
      （实测：造数 10 万行、引擎实读 0 行、分析 3 秒即 error，排查两轮才定位）。
    """
    n = 0
    try:
        n = int(nrows) if nrows is not None else 0
    except (TypeError, ValueError):
        n = 0
    if n > 0:
        return n
    m = 0
    try:
        raw = getattr(sheet, "max_row", None)
        m = int(raw) if raw is not None else 0
    except (TypeError, ValueError):
        m = 0
    return max(0, m)


# ══════════════════════════════════════════════════════════════════════════
# ③ 顺序游标行读取（修 §5-②）
# ══════════════════════════════════════════════════════════════════════════
_CURSOR_ATTR = "_pe_row_cursor"


def _norm_row(row: Any) -> List[str]:
    """行归一（与 `main._get_row_values` **逐元素同口径**：None ⇒ 空串）。"""
    if not row:
        return []
    return [str(c) if c is not None else "" for c in row]


def _cursor(sheet: Any) -> Optional[Dict[str, Any]]:
    """取（或建）该 sheet 的**顺序游标**；不支持则返回 `None`（走区间读）。"""
    st = getattr(sheet, _CURSOR_ATTR, None)
    if isinstance(st, dict) and st.get("sheet") is sheet:
        return st
    if not hasattr(sheet, "iter_rows"):
        return None
    try:
        it = sheet.iter_rows(values_only=True)          # 从第 1 行起的**流式**迭代器
    except Exception:                                   # noqa: BLE001
        return None
    st = {"sheet": sheet, "it": it, "pos": 0}
    try:
        setattr(sheet, _CURSOR_ATTR, st)
    except Exception:                                   # noqa: BLE001
        return None
    return st


def drop_cursor(sheet: Any) -> None:
    """丢弃该 sheet 的游标。

    ★ 必须的：openpyxl `read_only` 下**两个活跃 reader 会互相干扰**
      （同一底层解析器），故走区间读之前先放掉游标。
    """
    try:
        if isinstance(getattr(sheet, _CURSOR_ATTR, None), dict):
            object.__setattr__(sheet, _CURSOR_ATTR, None)
    except Exception:                                   # noqa: BLE001
        pass


def reset_cursors() -> None:
    """全局重置（测试与长驻进程用；不持有全局表，靠属性名约定）。"""
    return None


def _range_read(sheet: Any, start: int, end: int) -> List[List[str]]:
    """区间读（1-based `[start, end]`）—— 与既有实现**逐元素等价**的回退路径。"""
    drop_cursor(sheet)                                  # 先放掉游标，避免双 reader
    try:
        rows = list(sheet.iter_rows(min_row=start, max_row=end, values_only=True))
    except Exception:                                   # noqa: BLE001
        return []
    return [_norm_row(r) for r in rows]


def iter_rows_range(sheet: Any, start: int, end: int) -> List[List[str]]:
    """读 1-based 区间 `[start, end]` 的**归一化行**（与 openpyxl 返回逐元素等价）。

    ★ 性能语义：
      · **顺序前进**（`start` 不小于游标下一行）⇒ 用单次流式游标**只消费增量**
        ⇒ 顺序访问总代价 **O(n)**（这就是 §5-② O(n²) 的修法）；
      · **跳转/回退**（或 sheet 不支持迭代）⇒ 退回 `_range_read`（区间读）。

    ★ 正确性语义：两条路径返回**同一形状**（`list[list[str]]`，行序与
      `iter_rows(min_row=start, max_row=end, values_only=True)` 一致），
      故调用方（`main._get_row_values`）**无需任何改动**。
    """
    try:
        s, e = int(start), int(end)
    except (TypeError, ValueError):
        return []
    if s < 1 or e < s:
        return []
    st = _cursor(sheet)
    if st is None or st.get("pos", 0) + 1 < s:          # 不支持迭代 或 需要回退
        return _range_read(sheet, s, e)
    out: List[List[str]] = []
    while st["pos"] < e:
        try:
            row = next(st["it"])
        except StopIteration:
            break
        except Exception:                               # noqa: BLE001
            # 游标坏了 ⇒ 退回区间读（正确性优先；退回后会重建游标）
            drop_cursor(sheet)
            return _range_read(sheet, s, e)
        st["pos"] += 1
        if st["pos"] >= s:
            out.append(_norm_row(row))
    return out


# ══════════════════════════════════════════════════════════════════════════
# ④ 源码上限扫描与清单（供闸门与接口）
# ══════════════════════════════════════════════════════════════════════════
_CAP_RE = re.compile(r"min\(\s*nrows\s*,\s*(\d+)\s*\)")


def source_literals(main_py: Optional[str] = None) -> Set[int]:
    """静态扫描 `main.py` 里 `min(nrows, N)` 的 N 集合（闸门与文档的**共建依据**）。

    ★ 只认**行数上限**写法 `min(nrows, N)`；`content[:2000]` 之类的**文本截断
      不是行数上限**，故意不纳入（否则登记表会被无关数字污染）。
    """
    if main_py is None:
        main_py = str(Path(__file__).resolve().parent.parent / "main.py")
    try:
        src = Path(main_py).read_text(encoding="utf-8", errors="replace")
    except Exception:                                   # noqa: BLE001
        return set()
    return {int(x) for x in _CAP_RE.findall(src)}


def manifest(main_py: Optional[str] = None) -> Dict[str, Any]:
    """上限清单（供接口/前端/闸门；**登记表即权威**）。"""
    found = source_literals(main_py)
    registered = set(ROW_CAPS.keys())
    return {
        "row_caps": [{"cap": k, "note": ROW_CAPS[k]} for k in sorted(ROW_CAPS, reverse=True)],
        "max_cap": MAX_ROW_CAP,
        "kinds": dict(CAP_KINDS),
        "source_values": sorted(found, reverse=True),
        "registered_values": sorted(registered, reverse=True),
        "unregistered": sorted(found - registered),
        "stale": sorted(registered - found),
        "consistent": found == registered,
        "cursor_attr": _CURSOR_ATTR,
    }


# ══════════════════════════════════════════════════════════════════════════
# ⑤ 截断回执（修 §5-③：静默截断 ⇒ 显式回执）
# ══════════════════════════════════════════════════════════════════════════
def truncated(total: Any, cap: Any) -> bool:
    """是否发生截断（`total` 与 `cap` 都必须是**已知正整数**才判；否则 `False`）。"""
    try:
        t, c = int(total), int(cap)
    except (TypeError, ValueError):
        return False
    return t > 0 and c > 0 and t > c


def truncation_note(total: Any, cap: Any, label: str = "") -> str:
    """截断回执（自然句）；未截断返回空串。

    ★ 口径：`total` 未知（`None`/0/非数）⇒ **不产出回执**（缺失≠0，
      不能把"不知道多少行"写成"没有超出"）。
    """
    if not truncated(total, cap):
        return ""
    t, c = int(total), int(cap)
    return ("「%s」共 %d 行，本次读入前 %d 行（达解析上限 %d），超出部分**未参与分析**；"
            "如需全量请按此上限拆分为多个文件后重新上传。"
            % (label or "该表", t, c, c))


def row_cap_note(total: Any, cap: Any, label: str = "") -> Dict[str, Any]:
    """结构化回执（供接口/前端渲染，避免前端各自拼句）。"""
    t = int(total) if isinstance(total, (int, float)) and not isinstance(total, bool) else None
    c = int(cap) if isinstance(cap, (int, float)) and not isinstance(cap, bool) else None
    return {
        "total_rows": t,
        "cap": c,
        "cap_note": cap_note(c) if c is not None else "",
        "truncated": truncated(t, c),
        "note": truncation_note(t, c, label),
    }


# ══════════════════════════════════════════════════════════════════════════
# ⑥ 标准化增强：可识别字段的"覆盖度体检"（只读，不改字段表）
# ══════════════════════════════════════════════════════════════════════════
def field_coverage(rows: Iterable[Dict[str, Any]], names: Iterable[str]) -> Dict[str, Any]:
    """统计一组行在给定标准字段上的**取数覆盖度**（供前端提示"哪列没认出来"）。

    返回 `{field: {"cn":…, "hits":n, "rows":n, "ratio":r}}` 与整体摘要。
    ★ 只读统计，**不改任何数据**、不下结论（是否算"缺失"由 `extract_validate` 判）。
    """
    from engine.standard_fields import aliases_of, field as _f    # noqa: PLC0415
    row_list = [r for r in rows if isinstance(r, dict)]
    total = len(row_list)
    detail: Dict[str, Any] = {}
    for n in names:
        nm = str(n)
        al = aliases_of(nm)
        hits = 0
        for r in row_list:
            for a in al:
                v = r.get(a)
                if v not in (None, "") and not (isinstance(v, str) and not v.strip()):
                    hits += 1
                    break
        detail[nm] = {
            "cn": str((_f(nm) or {}).get("cn") or nm),
            "hits": hits,
            "rows": total,
            "ratio": (0.0 if total == 0 else round(hits / total, 4)),
            "aliases": len(al),
            "recognized": hits > 0,
        }
    recognized = [k for k, v in detail.items() if v["recognized"]]
    return {
        "rows": total,
        "fields": detail,
        "recognized_fields": sorted(recognized),
        "unrecognized_fields": sorted(set(str(x) for x in names) - set(recognized)),
        "recognized_ratio": (0.0 if not names else round(len(recognized) / len(list(names)), 4)),
    }
