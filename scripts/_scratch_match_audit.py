# -*- coding: utf-8 -*-
"""只读诊断 + 修后复核：疑点「二、发现的依据」挂到的明细表。"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.enterprise_report import _build_redline_problems

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                     "data", "cache", "last_analysis_cache.json")


def main():
    d = json.load(open(CACHE, encoding="utf-8"))
    rep = d["1"]["report"]["report"]
    fs = rep["all_findings"]
    sus = rep["comprehensive"]["redline_detection"]["suspicions"]
    # pipeline 实际调用点过滤掉弱结论疑点（与 _build_redline_problems 内同口径）
    probs = _build_redline_problems(sus, fs)
    for i, p in enumerate(probs, 1):
        paras = p.get("narrative_paragraphs") or []
        if len(paras) < 2:
            continue
        titles = [t.get("title") for t in (paras[1].get("detail_tables") or [])]
        if titles:
            print("疑点%-2d %-22s 二、发现的依据 → %s"
                  % (i, (p.get("title") or "")[:22], titles))


if __name__ == "__main__":
    main()
