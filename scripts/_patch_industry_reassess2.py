# -*- coding: utf-8 -*-
"""给 reassess_industry 补「并列第一 = 无共识（不得据此变更）」守卫。"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "engine", "industry_resolver.py")

SRC = io.open(TARGET, "r", encoding="utf-8", newline="").read()


def _crlf(s):
    return s.replace("\r\n", "\n").replace("\n", "\r\n")


OLD = _crlf(u'''    # ★ 只认「≥2 路证据同时指向同一行业」；单路证据不足以推翻高权威口径
    top_ind, top_routes = None, 0
    for ind in sorted(merged.keys()):
        n = merged[ind]
        if top_ind is None or n > top_routes or (n == top_routes and len(ind) > len(top_ind)):
            top_ind, top_routes = ind, n
''')

NEW = _crlf(u'''    # ★ 只认「≥2 路证据同时指向同一行业」；单路证据不足以推翻高权威口径。
    #   ★ 并列第一（多个行业同票）＝**没有共识**，一律不得据此变更——宁可 keep，
    #     也不让弱证据在平局时任意挑一个（选谁都不本正，等于现场猜）。
    order = sorted(merged.keys(), key=lambda k: (-merged[k], -len(k), k))
    top_ind = order[0] if order else ""
    top_routes = merged.get(top_ind, 0)
    tied = [k for k in order if merged.get(k, 0) == top_routes]
    if len(tied) > 1:
        _industry_reassess_log(
            pipeline_log,
            "[行业再判读] 新证据在 %s 之间并票（各 %d 路），无共识，"
            "不据此变更原口径 '%s'" % ("、".join(tied), top_routes, cur))
        return {"industry": cur, "decision": "keep", "evidence": evidence,
                "from_fallback": cur in _TRADE_FALLBACK_INDUSTRIES,
                "reason": "新证据多行业并票，无共识"}
''')

assert OLD in SRC, "anchor not found"
SRC = SRC.replace(OLD, NEW, 1)
io.open(TARGET, "w", encoding="utf-8", newline="").write(SRC)
print("OK: ambiguity guard injected")
