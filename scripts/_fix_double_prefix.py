# -*- coding: utf-8 -*-
"""修掉上一道 byte 替换把 `_industry_reassess_log` 前缀叠成双份的问题。"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "engine", "industry_resolver.py")

BAD = b"_industry_reassess_industry_reassess_log"
GOOD = b"_industry_reassess_log"


def main():
    raw = io.open(TARGET, "rb").read()
    n = raw.count(BAD)
    if not n:
        print("SKIP: clean")
        return 0
    raw = raw.replace(BAD, GOOD)
    io.open(TARGET, "wb").write(raw)
    print("fixed %d line(s)" % n)
    print("CRLF=%d bareLF=%d" % (
        raw.count(b"\r\n"), raw.replace(b"\r\n", b"").count(b"\n")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
