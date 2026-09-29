# -*- coding: utf-8 -*-
"""明细表治理 —— **企业版报告里所有明细表的唯一规范化点**。

## 为什么需要（根因，2026-09-29 点评整改 P1-14）

外部点评：「明细与合计对不上 / 归集失败」。实测发现的是一个**静默数据丢失**机制：

1. **列名与行键对不上**：报告输出闸门 `_zh_normalize_obj` 会把**值**做中文标点规范化
   （半角括号 → 全角），但**不会动字典的键**。于是同一个标签被写成两种形态：
   `columns = ['金额（元）', …]`（被规范化过）而 `rows[*] = {'金额(元)': …}`（没被动过）
   → 渲染层按 `columns` 取值取不到 → **整列渲染为空**，读者看到"有列无数据"。
2. **内部标识列外泄**：`ref_id` / `_key` 这类内部追溯键被当成正式列渲染。
3. **截断不注明**：生产者对明细做 `[:30]` 之类限行后未标注"仅列示前 N 笔"，
   读者会把"列示的行"当成"全部的行"，从而与合计对不上。

本模块在**报告输出前的同一道闸门**上跑一遍，统一修好这三类问题。
判据方向：**能对齐就对齐（保信息），对不齐就删列（不留空列）**，
截断一律注明。

## 通用规则（数据表驱动，新增同类只加一行）
- `_PUNCT_STRIP`：用于「标点不敏感」比对（去括号/空白/间隔符）；
- `_INTERNAL_COL_PREFIXES` / `_INTERNAL_COL_KEYS`：内部列名单。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# 标点不敏感比对：去掉的字符
_PUNCT_CHARS = "（）()【】[]、，,；;：: \u3000·．.－-_/｜|"

# 内部追溯列：不得作为正式列渲染（仍保留在内部底稿）
# ⚠ `ref_id` **不在**此列：实测它承载的是**凭证号**（如「记-2」）本身有价值，
#   且已被 `_EV_COLUMN_CN` 汉化为「凭证号」。此处只收"纯内部标识"。
_INTERNAL_COL_KEYS = {"_id", "_key", "seq_id", "source_key", "trace_id",
                      "snapshot_id", "fact_id", "scene_fact_id"}
_INTERNAL_COL_PREFIXES = ("_",)


def _canon_label(s: Any) -> str:
    """标签归一（仅用于**比对**，不改变输出）：去标点/空白/大小写。"""
    t = str(s or "").strip().lower()
    for ch in _PUNCT_CHARS:
        t = t.replace(ch, "")
    return t


def is_internal_col(name: Any) -> bool:
    s = str(name or "").strip()
    if not s:
        return True
    if s in _INTERNAL_COL_KEYS:
        return True
    return any(s.startswith(p) for p in _INTERNAL_COL_PREFIXES)


def align_table(table: Any) -> Dict[str, Any]:
    """把一张明细表规范化为「columns 与每行键一致」的自洽结构。

    步骤：① 剔除内部列；② 逐列做**标点不敏感**匹配，把行键改写成列名；
          ③ 仍匹配不到的列 → 丢弃（否则渲染为空列）；④ 行内多余键 → 保留为附加列
          （不丢信息），并把它们追加进 columns；⑤ 截断注明。
    """
    if not isinstance(table, dict):
        return {}
    rows = [r for r in (table.get("rows") or []) if isinstance(r, dict)]
    cols = [str(c) for c in (table.get("columns") or [])]
    out = {k: v for k, v in table.items() if k not in ("rows", "columns")}

    if not rows:
        out["columns"] = [c for c in cols if not is_internal_col(c)]
        out["rows"] = []
        return out

    # ① 剔除内部列
    cols = [c for c in cols if not is_internal_col(c)]

    # 收集**行键**（只用行键！把列名也算进来会让"列名在行里"永远为真 → 重命名永不执行，
    # 实测第一版就踩了这个坑：行键仍是 金额(元)、列名是 金额（元），对齐静默失效）
    key_order: List[str] = []
    for r in rows:
        for k in r.keys():
            k = str(k)
            if k not in key_order and not is_internal_col(k):
                key_order.append(k)

    # ② 标点不敏感匹配：列名 ←→ 行键
    canon_to_keys: Dict[str, List[str]] = {}
    for k in key_order:
        canon_to_keys.setdefault(_canon_label(k), []).append(k)

    final_cols: List[str] = []
    rename: Dict[str, str] = {}          # 原行键 → 目标列名
    for c in cols:
        if c in key_order:
            target = c
        else:
            cands = canon_to_keys.get(_canon_label(c)) or []
            if not cands:
                continue                   # 行里没有这一列 → 丢弃，不留空列
            target = c                     # 以列名为准（渲染层按 columns 取值）
            for k in cands:
                if k != c:
                    rename[k] = c
        if target not in final_cols:
            final_cols.append(target)
    # ④ 行里还有、列里没有的键 → 追加为附加列（不丢信息）
    for k in key_order:
        tgt = rename.get(k, k)
        if tgt not in final_cols:
            final_cols.append(tgt)

    new_rows: List[Dict[str, Any]] = []
    for r in rows:
        nr: Dict[str, Any] = {}
        for k, v in r.items():
            k = str(k)
            if is_internal_col(k):
                continue
            nr[rename.get(k, k)] = v
        new_rows.append(nr)

    # ★ 末道：仍带 ASCII 字母的列名（如 `ref_id`）必须汉化，否则"英文列名入文"。
    #   走键汉化唯一权威 `sentencekit.translate_key`（延迟导入，避免模块环依赖）。
    try:
        from engine.sentencekit import translate_key as _tk
        final_cols = [_tk(c) for c in final_cols]
        new_rows = [{_tk(k): v for k, v in r.items()} for r in new_rows]
    except Exception:
        pass

    out["columns"] = final_cols
    out["rows"] = new_rows

    # ⑤ 截断注明：生产者若记录了总数，且实际列示少于总数 → 明确写出"仅列示前 N 笔"
    total = table.get("rows_total")
    try:
        total_n = int(total) if total is not None else 0
    except (TypeError, ValueError):
        total_n = 0
    if total_n and total_n > len(new_rows):
        out["truncation_note"] = ("本表明细共 %d 笔，此处仅列示前 %d 笔；"
                                  "完整清单见内部工作底稿。" % (total_n, len(new_rows)))
    return out


def govern_all_tables(obj: Any, _depth: int = 0, _seen: set = None) -> Any:
    """递归遍历报告结构，对所有明细表执行 `align_table`（原地不可变：返回新结构）。

    识别口径：同时含 `columns` 与 `rows`（list）的 dict 即视为明细表。
    ★ 必须带环保护：真实 report_data 含循环引用（见 `pii_guard` 同款教训）。
    """
    if _depth > 30:
        return obj
    if _seen is None:
        _seen = set()
    if isinstance(obj, (dict, list, tuple)):
        if id(obj) in _seen:
            return obj
        _seen.add(id(obj))
    if isinstance(obj, dict):
        if isinstance(obj.get("columns"), list) and isinstance(obj.get("rows"), list):
            return align_table(obj)
        return {k: govern_all_tables(v, _depth + 1, _seen) for k, v in obj.items()}
    if isinstance(obj, list):
        return [govern_all_tables(v, _depth + 1, _seen) for v in obj]
    return obj


def collect_table_violations(obj: Any, _depth: int = 0, _seen: set = None) -> List[str]:
    """校验明细表自洽性。返回违规描述列表（**零误报**口径）。

    只报两类**真缺陷**：
      ① 出现内部列（会渲染成 `ref_id` 这种内部标识）；
      ② 某列名与行键**只差标点**（半/全角括号等）→ 渲染层按列名取值取不到、
         整列空白（这是实测的静默数据丢失，非"稀疏表"）。
    ⚠ 刻意**不**报"某行缺某列"：稀疏明细表（不同行字段不同）是正常的，
    渲染层会补 `—`，报它就是误报 —— 闸门误报会被绕过。
    """
    bad: List[str] = []
    if _depth > 30:
        return bad
    if _seen is None:
        _seen = set()
    if isinstance(obj, (dict, list, tuple)):
        if id(obj) in _seen:
            return bad
        _seen.add(id(obj))
    if isinstance(obj, dict):
        if isinstance(obj.get("columns"), list) and isinstance(obj.get("rows"), list):
            title = str(obj.get("title") or "")[:24]
            cols = [str(c) for c in obj["columns"]]
            internal = [c for c in cols if is_internal_col(c)]
            if internal:
                bad.append("表「%s」含内部列 %s" % (title, "、".join(internal[:3])))
            row_keys = set()
            for r in obj["rows"][:200]:
                if isinstance(r, dict):
                    row_keys |= {str(k) for k in r.keys()}
            canon = {_canon_label(k) for k in row_keys}
            for c in cols:
                if c in row_keys:
                    continue
                if _canon_label(c) in canon:
                    bad.append("表「%s」列名与行键仅标点不同（整列会渲染为空）：%s" % (title, c))
            return bad
        for v in obj.values():
            bad += collect_table_violations(v, _depth + 1, _seen)
    elif isinstance(obj, list):
        for v in obj:
            bad += collect_table_violations(v, _depth + 1, _seen)
    return bad
