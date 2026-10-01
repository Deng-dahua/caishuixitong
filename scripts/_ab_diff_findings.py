# -*- coding: utf-8 -*-
"""A/B 比对：定位「报告瘦身第二批」删除文案后 `all_findings` 少掉的条目。

用法：python scripts/_ab_diff_findings.py
读取 scripts/_ab_before_report.json（改前）与 scripts/_ab_after_report.json（改后），
按 (type, detail) 生成指纹求差，输出「改前有、改后无」与「改后有、改前无」。
"""
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)


def load_findings(path):
    d = json.load(io.open(path, encoding="utf-8"))
    rep = d.get("comprehensive", {}).get("report", d) if isinstance(d.get("comprehensive"), dict) else d
    # 兼容：顶层即有 all_findings
    f = d.get("all_findings")
    if not f and isinstance(rep, dict):
        f = rep.get("all_findings")
    return f or []


def key(x):
    return (str(x.get("type") or ""), str(x.get("detail") or "")[:120], str(x.get("level") or ""))


def main():
    b = load_findings("scripts/_ab_before_report.json")
    a = load_findings("scripts/_ab_after_report.json")
    print("改前 all_findings:", len(b), "| 改后 all_findings:", len(a))
    kb, ka = {}, {}
    for x in b:
        kb.setdefault(key(x), []).append(x)
    for x in a:
        ka.setdefault(key(x), []).append(x)
    only_before = {k: v for k, v in kb.items() if k not in ka}
    only_after = {k: v for k, v in ka.items() if k not in kb}
    print("\n=== 只在「改前」出现（= 本次少掉的条目）:", sum(len(v) for v in only_before.values()), "===")
    for k, v in only_before.items():
        print("  [%s] %s" % (v[0].get("level"), k[0]))
        print("      detail:", k[1][:160])
        extra = {kk: vv for kk, vv in v[0].items()
                 if kk in ("redline_id", "evidence_tier", "how_found", "category", "_scenario_governed")}
        if extra:
            print("      其他字段:", json.dumps(extra, ensure_ascii=False)[:200])
    print("\n=== 只在「改后」出现（新增）:", sum(len(v) for v in only_after.values()), "===")
    for k, v in only_after.items():
        print("  [%s] %s | %s" % (v[0].get("level"), k[0], k[1][:110]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
