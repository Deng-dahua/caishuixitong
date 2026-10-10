# -*- coding: utf-8 -*-
"""只读实验（不改产品代码）：用红线 match_hints 作准绳，看 2-gram 兜底匹配还剩哪些。"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.enterprise_report import (_MATCH_STOP, _cjk_bigrams,  # noqa: E402
                                      _finding_detail_tables,
                                      _match_suspicion_detail)
from engine.tax_redlines import all_redlines  # noqa: E402

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                     "data", "cache", "last_analysis_cache.json")


def main():
    d = json.load(open(CACHE, encoding="utf-8"))
    rep = d["1"]["report"]["report"]
    fs = rep["all_findings"]
    sus = rep["comprehensive"]["redline_detection"]["suspicions"]
    hints = {r.get("id"): (r.get("match_hints") or []) for r in all_redlines()}

    dt_by_type = {}
    for f in fs:
        if not isinstance(f, dict):
            continue
        t = _finding_detail_tables(f)
        if t and f.get("type"):
            dt_by_type.setdefault(f["type"], t)

    print("=== match_hints 准绳：命中表 vs 该红线 match_hints 是否真相关 ===")
    kept = dropped = 0
    for i, s in enumerate(sus, 1):
        t = _match_suspicion_detail(s, dt_by_type)
        if not t:
            continue
        rid = s.get("redline_id") or ""
        hs = set()
        for h in hints.get(rid, []):
            hs |= set(_cjk_bigrams(str(h)))
        title = (t[0].get("title") or "")
        hit = bool(hs)
        # 表标题（含 type）与 hints 的重叠
        ov = hs & set(_cjk_bigrams(title))
        mark = "保留" if hit else "**丢弃**"
        if hit:
            kept += 1
        else:
            dropped += 1
        print("%s 疑点%-2d %-20s rid=%-13s 表=%-30s 重叠bigram=%d %s"
              % (mark, i, (s.get("redline_name") or "")[:20], rid, title[:30], len(ov), sorted(ov)[:6]))
    print("=== 保留 %d / 丢弃 %d ===" % (kept, dropped))


if __name__ == "__main__":
    main()
