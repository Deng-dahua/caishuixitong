# -*- coding: utf-8 -*-
"""一次性脚本：为缺少"豁免/正当理由"类要件的红线，**按该红线自带的 justifications 补一条豁免要件**。

★ 为什么这么做（2026-09-27 用户要求）：
  - 要件表若只有"出现即有问题"的要件，缺少"但存在正当情形"的出口，容易误判；
  - 豁免要件**不能套模板**（"无合理解释"这种空话没有判断价值），
    所以直接采用红线库里**已由业务定义的 `justifications`**（正当理由清单）来生成，每条都是具体的。

生成格式：`不属于下列正当情形：<理由1>；<理由2>…`
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TARGET = os.path.join(ROOT, "engine", "tax_redlines.py")

EXEMPT = ("解释", "豁免", "合理", "正当", "无合理", "无法", "不属于", "非个人", "合法")


def main():
    from engine.tax_redlines import REDLINES

    need = [r for r in REDLINES
            if not any(any(k in str(c) for k in EXEMPT) for c in (r.get("constituents") or []))]
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
    print("已补豁免要件:", done, "/", len(need))
    if skipped:
        print("跳过:")
        for s in skipped:
            print("   -", s)
    return 0 if not skipped else 1


if __name__ == "__main__":
    sys.exit(main())
