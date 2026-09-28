# -*- coding: utf-8 -*-
"""统一口径脚本：为**缺少显式「不属于下列正当情形」豁免构成要件**的红线，
按其自带的 justifications 补一条显式豁免要件，追加到 constituents 末尾。

★ 与 2026-09-27 的 _add_constituent_exemptions.py 区别：
  旧脚本用宽泛关键词（解释/合理/无法/不属于…）判定"已有豁免"，导致 31 条红线
  仅靠正向下要件里嵌入的"可解释来源/无法…解释"过关，未形成显式豁免 bullet，
  与另外 37 条「不属于下列正当情形」格式不统一。本脚本以"缺『不属于』"为唯一判定，
  把全部 68 条统一为显式豁免格式。

★ 安全性：追加到 constituents **末尾**，不重排；既有的 constituent_hits.index（1..N）
  仍指向原要件，豁免要件恒为末位、永不被 hit 命中，索引零移位。
★ 格式：不属于下列正当情形：<理由1>；<理由2>…
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TARGET = os.path.join(ROOT, "engine", "tax_redlines.py")


def main():
    from engine.tax_redlines import REDLINES

    # 判定：constituents 中没有任何一条含「不属于」→ 需要补显式豁免要件
    need = [r for r in REDLINES
            if not any("不属于" in str(c) for c in (r.get("constituents") or []))]
    with io.open(TARGET, encoding="utf-8") as f:
        src = f.read()

    done, skipped = 0, []
    for r in need:
        rid = r.get("id")
        js = [str(x).strip() for x in (r.get("justifications") or []) if str(x).strip()]
        if not js:
            skipped.append((rid, "无 justifications"))
            continue
        text = "不属于下列正当情形：" + "；".join(js)
        i = src.find('"id": "%s"' % rid)
        j = src.find('"constituents": [', i) if i >= 0 else -1
        if j < 0:
            skipped.append((rid, "未定位到 constituents"))
            continue
        m = re.search(r"\n[ \t]*\]", src[j:])
        if not m:
            skipped.append((rid, "未定位到 constituents 结尾"))
            continue
        k = j + m.start()
        inner = src[j + len('"constituents": ['):k].rstrip()
        if not inner.endswith(","):
            inner = inner + ","
        new_inner = inner + '\n            "%s"' % text
        src = src[:j + len('"constituents": [')] + new_inner + src[k:]
        done += 1

    with io.open(TARGET, "w", encoding="utf-8") as f:
        f.write(src)
    print("已补显式豁免要件:", done, "/", len(need))
    if skipped:
        print("跳过:")
        for s in skipped:
            print("   -", s)
    return 0 if not skipped else 1


if __name__ == "__main__":
    sys.exit(main())
