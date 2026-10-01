# -*- coding: utf-8 -*-
"""把 _patch_industry_reassess 注入时 shell 转义写坏的字面 '/r/n' 修成真 CRLF。

（注入脚本里 u'...\\r\\n...' 经 bash 传递被写成字面 /r/n；这里按字节精确复位。）
幂等：没有 '/r/n' 时直接退出。
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "engine", "industry_resolver.py")

CR, LF = b"\x0d", b"\x0a"

PAIRS = [
    (b"    if pipeline_log is not None:/r/n        try:/r/n            pipeline_log.append(msg)",
     b"    if pipeline_log is not None:" + CR + LF + b"        try:" + CR + LF + b"            pipeline_log.append(msg)"),
    (b"        except Exception:/r/n            pass",
     b"        except Exception:" + CR + LF + b"            pass"),
]


def main():
    raw = io.open(TARGET, "rb").read()
    if b"/r/n" not in raw:
        print("SKIP: no literal /r/n found")
        return 0
    for old, new in PAIRS:
        n = raw.count(old)
        if n:
            raw = raw.replace(old, new)
            print("fixed %d occurrence(s): %s" % (n, old[:40]))
    if b"/r/n" in raw:
        print("WARN: leftover /r/n remains", file=sys.stderr)
        return 1
    io.open(TARGET, "wb").write(raw)
    print("CRLF=%d bareLF=%d" % (
        raw.count(CR + LF), raw.replace(CR + LF, b"").count(LF)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
