# -*- coding: utf-8 -*-
"""一次性补齐：按**最近一次分析结果**回填稽查项目画像（2026-10-19）。

## 背景

`project_service.sync_profile_from_analysis` 已接到分析完成链路上
（`main._persist_one_click_result`），但**改造之前跑过的分析**没有回写过
⇒ 历史项目的 `industry/region/period_*/profile_*` 仍是空，列表显示「—」。
本脚本按同一套权威（`project_profile_fill.analysis_values` +
`project_service.sync_profile_from_analysis`）补一次，**不另写任何逻辑**。

## 用法

    python scripts/_backfill_project_profile.py            # 只预览（默认，不写库）
    python scripts/_backfill_project_profile.py --apply     # 实际写入
    python scripts/_backfill_project_profile.py --apply --company 1

## 铁律

- 默认 **dry-run**：不写库也能看到"会改哪些字段、从什么改成什么、依据哪个来源"；
- 幂等：已一致（或用户已填且分析未给出）的字段不会被改；重复跑第二次应显示 **0 项**；
- 数据源只读既有产物：报告载荷（`engine.report_payload`）+ 工商档案
  （`engine.business_info.store`）；不重跑分析、不伪造值。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _payload(cid: int):
    from engine.report_payload import payload_path                 # noqa: PLC0415
    path = payload_path(cid)
    if not os.path.exists(path):
        return None, "载荷不存在：%s" % os.path.basename(path)
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh), ""
    except Exception as exc:                                       # noqa: BLE001
        return None, "载荷读取失败：%s" % exc


def _company_row(project_name: str, tax_id: str):
    from engine.business_info import store as BIZ                  # noqa: PLC0415
    try:
        row = BIZ.get_by_tax_id(tax_id) if tax_id else None
        if row is None and project_name:
            row = BIZ.get(project_name)
        return row
    except Exception:                                              # noqa: BLE001
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="按最近一次分析结果补齐项目画像")
    ap.add_argument("--apply", action="store_true", help="实际写库（缺省只预览）")
    ap.add_argument("--company", type=int, default=None, help="只处理指定账套 id")
    args = ap.parse_args()

    from sqlalchemy import text as _text                           # noqa: PLC0415
    from database import engine as eng                             # noqa: PLC0415
    from engine.project_profile_fill import analysis_values         # noqa: PLC0415
    from engine.project_service import sync_profile_from_analysis  # noqa: PLC0415

    with eng.connect() as conn:
        rows = conn.execute(_text(
            "SELECT id, company_id, code, name, taxpayer_id, industry, region, "
            "period_start, period_end, tax_scopes FROM projects ORDER BY id")).fetchall()
    projects = [dict(r._mapping) for r in rows]
    if args.company is not None:
        projects = [p for p in projects if p.get("company_id") == args.company]

    if not projects:
        print("没有可处理的项目（%s）"
              % ("company=%s" % args.company if args.company else "全部"))
        return 0

    print("模式：%s" % ("APPLY（写库）" if args.apply else "DRY-RUN（只预览，不写库）"))
    total = 0
    for p in projects:
        cid = p.get("company_id")
        print("\n项目 %s（%s）｜账套 %s" % (p.get("id"), p.get("code"), cid))
        if not cid:
            print("  ⚠ 未关联账套，跳过（回写依赖账套的分析结果）")
            continue
        report, err = _payload(int(cid))
        if report is None:
            print("  ⚠ 跳过：%s" % err)
            continue
        row = _company_row(str(p.get("name") or ""), str(p.get("taxpayer_id") or ""))
        vals = analysis_values(report, row)
        res = sync_profile_from_analysis(int(cid), vals, dry_run=not args.apply)
        chs = [c for c in (res.get("changes") or []) if c.get("project_id") == int(p["id"])]
        if not chs:
            print("  ✓ 无需改动（已一致，或分析未给出可填值）")
            continue
        total += len(chs)
        for c in chs:
            print("  · %-22s %-22r → %r   [%s]"
                  % (c["field"], str(c["from"])[:22], str(c["to"])[:34], c.get("source") or "—"))
        if not args.apply:
            print("  （预览：未写库，加 --apply 执行）")
    print("\n合计待改字段：%d 个%s" % (total, "" if args.apply else "（预览）"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
