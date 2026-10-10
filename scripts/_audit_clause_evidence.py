# -*- coding: utf-8 -*-
"""条款核验的证据复核（只读）—— 打印命中词的真实上下文，判定真假红。

用途：`_audit_clause_compliance.py` 给出初判后，**必须**复核命中语境，
否则会把「本报告不构成行政处罚」这类**合规否定式**误判为违规定性（项目铁律：
断言"没有 X"前必须全文本反查；判据先量化再收窄）。
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT = os.path.join(ROOT, "data", "cache", "last_analysis_cache.json")


def load_report(path: str) -> dict:
    raw = json.loads(open(path, encoding="utf-8", errors="ignore").read())
    if "enterprise_readable_report" in raw:
        return raw
    for v in raw.values():
        if isinstance(v, dict):
            rep = v.get("report")
            if isinstance(rep, dict) and isinstance(rep.get("report"), dict):
                return rep["report"]
            if isinstance(rep, dict) and "enterprise_readable_report" in rep:
                return rep
    return {}


def all_text(node, limit: int = 400000) -> str:
    out, seen, stack = [], set(), [node]
    while stack and sum(len(x) for x in out) < limit:
        cur = stack.pop()
        if isinstance(cur, str):
            out.append(cur)
            continue
        if isinstance(cur, (dict, list)):
            if id(cur) in seen:
                continue
            seen.add(id(cur))
            stack.extend(cur.values() if isinstance(cur, dict) else cur)
    return "\n".join(out)


def ctx(text: str, kw: str, span: int = 46, maxn: int = 4):
    hits, i = [], 0
    while len(hits) < maxn:
        j = text.find(kw, i)
        if j < 0:
            break
        hits.append(text[max(0, j - span): j + len(kw) + span].replace("\n", " "))
        i = j + len(kw)
    return hits


def main(path: str) -> int:
    rep = load_report(path)
    err = rep.get("enterprise_readable_report") or {}
    T = all_text(err)
    print("报告层文本量：%d 字\n" % len(T))

    print("═══ A6 语境复核：越权表述候选 ═══")
    for kw in ("已查明的风险", "违法认定", "定性为", "构成偷税", "属于偷税", "应认定为"):
        cs = ctx(T, kw)
        print("\n【%s】命中 %d 处" % (kw, T.count(kw)))
        for c in cs:
            print("   …%s…" % c)

    print("\n═══ B1 语境复核：禁区词 ═══")
    for kw in ("税务处理决定", "行政处罚", "移送决定", "法律意见", "财务顾问"):
        cs = ctx(T, kw)
        print("\n【%s】命中 %d 处" % (kw, T.count(kw)))
        for c in cs:
            print("   …%s…" % c)

    print("\n═══ B2 五要素的实质承载（宽松搜索）═══")
    for kw in ("风险信号", "风险识别", "证据核对", "资料缺口", "缺失资料", "待核", "复查标准", "复查"):
        print("   %-8s 命中 %d" % (kw, T.count(kw)))

    print("\n═══ B4 报告实际使用的『事项/结论』术语频次 ═══")
    for kw in ("风险信号", "待核事项", "已认定事实", "违法认定",
               "涉嫌风险事项", "风险事项", "已列明", "待核实事项", "疑点", "风险点"):
        print("   %-10s %d" % (kw, T.count(kw)))

    print("\n═══ B5 免责/边界声明全文 ═══")
    for kw in ("不替代", "不构成", "法定程序", "另行判断", "另行认定", "有权机关"):
        cs = ctx(T, kw, span=60, maxn=3)
        print("\n【%s】命中 %d 处" % (kw, T.count(kw)))
        for c in cs:
            print("   …%s…" % c)

    print("\n═══ A3 资料不足提示的措辞实况 ═══")
    gap = rep.get("_material_gap") or {}
    print("  _material_gap.summary =", (gap.get("summary") or "")[:200])
    for kw in ("补齐", "补充资料", "重新分析", "重新执行", "发起新一轮"):
        print("   %-8s 全文命中 %d" % (kw, T.count(kw)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT))
