# -*- coding: utf-8 -*-
"""把行内的 `float(<expr> or 0)` 统一替换为 `to_number(<expr>)`（唯一权威）。

用括号配对扫描定位 `float(...)` 的完整范围，避免正则无法处理嵌套（如
`float(i.get("total", i.get("amount", 0)) or 0)`）。
"""
import io
import os
import re

REPO = r"c:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong"
os.chdir(REPO)

FILES = [
    "main.py", "engine/domain_analysis.py", "engine/pipeline.py", "engine/payment_channel.py",
    "engine/fund_matching.py", "engine/financial_analyzer.py", "engine/business_model.py",
    "engine/verified_rule_engine.py", "engine/enterprise_report.py", "engine/industry_benchmark.py",
]


def rewrite(text: str):
    """返回 (新文本, 替换次数)。只处理 `float( ... or 0 )` 形态。"""
    out = []
    i = 0
    n = 0
    while True:
        j = text.find("float(", i)
        if j < 0:
            out.append(text[i:])
            break
        # 不是标识符的一部分（如 my_float( ）
        if j > 0 and (text[j - 1].isalnum() or text[j - 1] == "_"):
            out.append(text[i:j + 6])
            i = j + 6
            continue
        # 括号配对
        k = j + 6
        depth = 1
        in_str = None
        while k < len(text) and depth:
            ch = text[k]
            if in_str:
                if ch == "\\":
                    k += 2
                    continue
                if ch == in_str:
                    in_str = None
            elif ch in "\"'":
                in_str = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        if k >= len(text):
            out.append(text[i:])
            break
        inner = text[j + 6:k]
        m = re.fullmatch(r"(?s)\s*(.*?)\s+or\s+0\s*", inner)
        if m:
            expr = m.group(1)
            out.append(text[i:j] + "to_number(%s)" % expr)
            n += 1
        else:
            out.append(text[i:k + 1])
        i = k + 1
    return "".join(out), n


total = 0
for path in FILES:
    if not os.path.exists(path):
        continue
    src = io.open(path, encoding="utf-8").read()
    new, n = rewrite(src)
    if not n:
        continue
    # 确保已导入 to_number
    if "from engine.numparse import to_number" not in new and "from engine import numparse" not in new:
        m = re.search(r"^(from |import )", new, re.M)
        anchor = "from engine.numparse import to_number  # ★ 2026-09-25 统一数值解析\n"
        if path == "main.py":
            new = anchor + new
        else:
            # 在首个 import 段结束后插入
            lines = new.split("\n")
            idx = max((i for i, l in enumerate(lines) if l.startswith(("import ", "from "))), default=-1)
            lines.insert(idx + 1 if idx >= 0 else 0, anchor.rstrip("\n"))
            new = "\n".join(lines)
    io.open(path, "w", encoding="utf-8").write(new)
    total += n
    print("  ✓ %-34s 替换 %d 处" % (path, n))

print("\n共替换 %d 处行内私有兜底" % total)
