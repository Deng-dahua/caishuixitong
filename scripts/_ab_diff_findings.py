# -*- coding: utf-8 -*-
"""A/B 比对：定位两份报告 JSON 之间 `all_findings` 的差集。

用法：
  python scripts/_ab_diff_findings.py                       # 默认 v1=改前 v2=改后（本目录固定文件名）
  python scripts/_ab_diff_findings.py <a.json> <b.json>      # 任意两份（a=基准，b=对照）

输出「只在 a 出现」「只在 b 出现」两组，按 (type, detail, level) 指纹比对。
"""
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

DEFAULT_A = "scripts/_ab_before_report.json"
DEFAULT_B = "scripts/_ab_after_report.json"


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
    pa = sys.argv[1] if len(sys.argv) > 2 else DEFAULT_A
    pb = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_B
    a = load_findings(pa)
    b = load_findings(pb)
    print("A(%s) all_findings: %d | B(%s) all_findings: %d" % (pa, len(a), pb, len(b)))
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
