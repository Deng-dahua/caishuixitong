#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""C4 检测器覆盖率测试（2026-09-29）。

验证目标：40 条「盲区红线」（无源码检测器、未登记 _DEFAULT_HIT_INDEX 兜底，
只能依赖 match_redline_grounded 软匹配）**确实可达**——即：当一条发现携带该红线的
信号（名称主词）且本轮提供了其 required_materials 时，match_redline_grounded 能命中它。

若某条盲区红线不可达 → 它永远是「死红线」（永远命不中），必须要么补检测器、
要么登记兜底、要么补 match_hints，否则从库中剔除。

运行：PYTHONPATH=. python scripts/_verify_blind_redline_coverage.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.tax_redlines import REDLINES, match_redline_grounded
from engine.redline_engine import _DEFAULT_HIT_INDEX
from tools.audit_consistency import _scan_declared_detectors


def _blind_redlines():
    det = _scan_declared_detectors()
    out = []
    for r in REDLINES:
        rid = r["id"]
        if rid in det or rid in _DEFAULT_HIT_INDEX:
            continue  # 有检测器或兜底 → 非盲区
        out.append(r)
    return out


def main():
    print("=== C4 盲区红线软匹配可达性测试 ===")
    blind = _blind_redlines()
    print(f"盲区红线总数：{len(blind)}")

    unreachable = []
    no_hints = []
    short_hint_only = []
    for r in blind:
        rid = r["id"]
        hints = r.get("match_hints") or []
        if not hints:
            no_hints.append(rid)
        # 名称主词作为发现标题/正文信号 → 强信号 name@title
        title = r.get("name", "")
        text = title + " " + " ".join(str(h) for h in hints)
        avail = list(r.get("required_materials") or [])
        got, info = match_redline_grounded(title, text, avail, domain=r.get("domain"))
        if got is None or got.get("id") != rid:
            unreachable.append((rid, got.get("id") if got else None, info.get("note", "")))
        # 备注：仅依赖 name@title、无 ≥4 字 hint 可命中全文的（hint@textL）也视为可达，
        # 但记录为「弱提示」（靠名称而非提示词命中）。
        if not any(len(str(h)) >= 4 for h in hints) and title:
            short_hint_only.append(rid)

    if no_hints:
        print(f"  [ERROR] 以下盲区红线无 match_hints（死红线）：{no_hints}")
    if unreachable:
        print(f"  [ERROR] 以下盲区红线软匹配不可达：")
        for rid, got_id, note in unreachable:
            print(f"     {rid} → 命中了 {got_id}（{note}）")
    if short_hint_only:
        print(f"  [提示] 仅依赖名称命中、无 ≥4 字提示词的盲区红线 {len(short_hint_only)} 条："
              f"{', '.join(short_hint_only)}")

    assert not no_hints, "存在无 match_hints 的死红线"
    assert not unreachable, f"{len(unreachable)} 条盲区红线软匹配不可达"

    print(f"\n[OK] C4：{len(blind)} 条盲区红线全部可被 match_redline_grounded 软匹配命中（可达性 100%）")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f"\n[FAIL] {exc}")
        sys.exit(1)
