# -*- coding: utf-8 -*-
"""只读实验（不改产品代码）：兜底匹配改用「红线名 ↔ 发现类型」比对（剔除 suspect 泛描述词），
看 21 条挂载里会丢/留哪些，判断新口径是否更准。"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.enterprise_report import (_MATCH_STOP, _cjk_bigrams,  # noqa: E402
                                      _finding_detail_tables)

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                     "data", "cache", "last_analysis_cache.json")


def main():
    d = json.load(open(CACHE, encoding="utf-8"))
    rep = d["1"]["report"]["report"]
    fs = rep["all_findings"]
    sus = rep["comprehensive"]["redline_detection"]["suspicions"]

    dt_by_type = {}
    for f in fs:
        if not isinstance(f, dict):
            continue
        if str(f.get("type") or "").endswith("缺失") or str(f.get("type") or "").startswith("资料缺失"):
            continue
        t = _finding_detail_tables(f)
        if t and f.get("type"):
            dt_by_type.setdefault(f["type"], t)

    keep = drop = 0
    print("=== A) 现行口径（红线名+suspect+rid 全比） vs B) 新口径（只比红线名） ===")
    for i, s in enumerate(sus, 1):
        rid = s.get("redline_id") or ""
        rname = str(s.get("redline_name") or "")
        old = " ".join([rname, str(s.get("suspect") or ""), rid])
        sbg_old = set(_cjk_bigrams(old)) - set(_MATCH_STOP)
        sbg_new = set(_cjk_bigrams(rname)) - set(_MATCH_STOP)
        bo, bn = 0, 0
        best_o = best_n = ""
        for tkey, tables in dt_by_type.items():
            tb = set(_cjk_bigrams(tkey)) - set(_MATCH_STOP)
            if not tb:
                continue
            so, sn = len(sbg_old & tb), len(sbg_new & tb)
            if so > bo:
                bo, best_o = so, tables[0].get("title")
            if sn > bn:
                bn, best_n = sn, tables[0].get("title")
        ho, hn = bo >= 3, bn >= 3
        if ho:
            keep += 1
        else:
            drop += 1
        mark = "  " if ho == hn else "★ "
        print("%s疑点%-2d %-18s A(旧)=%d %-28s B(新)=%d %-28s" %
              (mark, i, rname[:18], bo, str(best_o)[:28], bn, str(best_n)[:28]))
    print("=== 会挂载的疑点数：旧 %d / 新 %d ===" % (keep, drop))


if __name__ == "__main__":
    main()
