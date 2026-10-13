# -*- coding: utf-8 -*-
"""基线数字自检（**只读**）：把《统一开发基线》声明的数字与仓库实测逐项比对。

★ 为什么必须有这个脚本：
  基线文档一旦与仓库实际脱节（改了代码没改文档 / 抄错数字），后续所有开发计划都建立在
  错误地基上。本脚本是"基线可信"的**结果级判据**——任一数字不符即退出码 1。

判据（21 项，全部为「实测值」而非文档转录）：
  端点 149/9/2/7 ｜ engine 190 ｜ tests 98 ｜ config 38 ｜ tools 12 ｜ yaml 18
  accounting.db 39 表 ｜ security.db 6 表
  规则主体 176（红线 91 + 已验证 85 + 检测器实现层 25/10/14）
  候选 460（add 97 / merge 141）｜ 176+97=273

用法：
  .venv/Scripts/python.exe scripts/_verify_baseline_numbers.py
"""
from __future__ import annotations

import glob
import json
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)          # 项目铁律：只读核验脚本必须显式 insert ROOT


def _count(fname: str, pat: str) -> int:
    with open(os.path.join(ROOT, fname), encoding="utf-8") as fh:
        return len(re.findall(pat, fh.read()))


def _tables(db: str) -> int:
    conn = sqlite3.connect(os.path.join(ROOT, db))
    try:
        return len(list(conn.execute(
            "select name from sqlite_master where type='table'")))
    finally:
        conn.close()


def main() -> int:
    ok, bad = [], []

    def chk(name, claimed, actual):
        (ok if claimed == actual else bad).append((name, claimed, actual))

    # ── 端点（合计应为 167 = 149+9+2+7）──
    chk("main.py 路由", 149, _count("main.py", r"@app\.(get|post|put|delete|patch)\("))
    chk("tax_risk.py 路由", 9, _count("tax_risk.py", r"@router\.(get|post|put|delete|patch)\("))
    chk("tax_rules_api.py 路由", 2, _count("tax_rules_api.py", r"@router\.(get|post|put|delete|patch)\("))
    chk("file_parser.py 路由", 7, _count("file_parser.py", r"@router\.(get|post|put|delete|patch)\("))

    # ── 规模 ──
    chk("engine/*.py", 190, len(glob.glob(os.path.join(ROOT, "engine/*.py"))))
    chk("tests/*.py", 98, len(glob.glob(os.path.join(ROOT, "tests/*.py"))))
    chk("config/*.json", 38, len(glob.glob(os.path.join(ROOT, "config/*.json"))))
    chk("tools/*.py", 12, len(glob.glob(os.path.join(ROOT, "tools/*.py"))))
    chk("rules_export/*.yaml", 18, len(glob.glob(os.path.join(ROOT, "rules_export/*.yaml"))))

    # ── 数据库 ──
    chk("accounting.db 表数", 39, _tables("data/accounting.db"))
    chk("security.db 表数", 6, _tables("data/security.db"))

    # ── 规则分层（唯一权威 layer_semantics）──
    with open(os.path.join(ROOT, "config/rule_versions.json"), encoding="utf-8") as fh:
        layers = json.load(fh)["layer_semantics"]["layers"]
    chk("规则主体", 176, sum(v["count"] for v in layers.values()
                             if v.get("counts_toward_rule_total")))
    chk("红线 REDLINES", 91, layers["tax_redlines"]["count"])
    chk("已验证规则", 85, layers["verified_rule_engine"]["count"])
    chk("专项探测(检测器层)", 25, layers["special_redline_detectors"]["count"])
    chk("缺口探测(检测器层)", 10, layers["gap_risk_detectors"]["count"])
    chk("缺口税种探测(检测器层)", 14, layers["gap_tax_obligations"]["count"])

    # ── 候选库 ──
    tot = adds = merges = 0
    for f in ("config/rulelist_v1.json", "config/rulelist_v11.json", "config/rulelist_v12.json"):
        with open(os.path.join(ROOT, f), encoding="utf-8") as fh:
            rules = json.load(fh)["rules"]
        tot += len(rules)
        adds += sum(1 for r in rules if r.get("action") == "add")
        merges += sum(1 for r in rules if r.get("action") == "merge")
    chk("候选规则总数", 460, tot)
    chk("候选 add（真缺）", 97, adds)
    chk("候选 merge（口径不同）", 141, merges)
    chk("全部 add 入库后规则主体", 273, 176 + adds)

    print("=== ✅ 通过 %d 项 ===" % len(ok))
    for name, _, actual in ok:
        print("  %-26s %s" % (name, actual))
    if bad:
        print("=== ❌ 不符 %d 项 ===" % len(bad))
        for name, claimed, actual in bad:
            print("  %-26s 基线声明=%s 实测=%s" % (name, claimed, actual))
        return 1
    print("\n基线文档数字与仓库实测 100% 一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
