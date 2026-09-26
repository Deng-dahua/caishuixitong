# -*- coding: utf-8 -*-
"""收敛字段读取/语义判定到 engine/fieldkit.py + 对语义不同的同名函数改名区分。

分两类处理：
  A. 语义相同 → 实现改为转发 fieldkit（保留原名与签名）
  B. 语义不同但同名 → **改名**并在文档里写明用途（硬合并会产生隐蔽 bug）
"""
import ast
import io
import os
import re

REPO = r"c:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong"
os.chdir(REPO)

# ── A. 转发映射：(文件, 函数名) → (fieldkit 函数, 第一参数是否保留原名) ──
FORWARD = {
    ("engine/external_check_reminder.py", "_buyer"): "buyer_name",
    ("engine/external_check_reminder.py", "_seller"): "seller_name",
    ("engine/false_invoice.py", "_buyer"): "buyer_name",
    ("engine/false_invoice.py", "_seller"): "seller_name",
    ("engine/invoice_pattern_detector.py", "_buyer"): "buyer_name",
    ("engine/invoice_pattern_detector.py", "_seller"): "seller_name",
    ("engine/invoice_pattern_detector.py", "_inv_type"): "invoice_type",
    ("engine/invoice_pattern_detector.py", "_is_void_or_red"): "is_void_or_red",
    ("engine/verified_rule_engine.py", "_is_void_or_red"): "is_void_or_red",
    ("engine/input_voucher.py", "_goods"): "goods_name",
    ("engine/structure_mismatch_detector.py", "_goods"): "goods_name",
    ("engine/domain_analysis.py", "_row_period"): "row_period",
    ("engine/verified_rule_engine.py", "_row_period"): "row_period",
    ("engine/domain_analysis.py", "_is_noise_name"): "is_noise_name",
    ("engine/verified_rule_engine.py", "_is_noise_name"): "is_noise_name",
}

# ── B. 改名（语义不同，不得硬合并）──
RENAMES = {
    "engine/verified_rule_engine.py": [
        # 返回 (值, 来源)，与 deduction_limit_detector 的 (vouchers)->float 语义不同
        ("_wage_total", "_wage_total_with_source"),
        # 参数是"整行"且走关键词映射；domain_analysis 的是"取税收分类"，语义不同
        ("_goods_category", "_goods_category_by_keyword"),
    ],
    "engine/monthly_reconcile.py": [
        # 返回原值；ap_aging/ar_aging 的是"返回 str"，语义不同
        ("_first", "_first_raw"),
    ],
}


def replace_func(path: str, name: str, new_src: str):
    src = io.open(path, encoding="utf-8").read()
    lines = src.split("\n")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            lines[node.lineno - 1: node.end_lineno] = new_src.split("\n")
            io.open(path, "w", encoding="utf-8").write("\n".join(lines))
            return True
    return False


# A. 转发
batch = {}
for (path, name), target in FORWARD.items():
    batch.setdefault(path, []).append((name, target))

for path, items in batch.items():
    src = io.open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            for name, target in items:
                if node.name != name:
                    continue
                params = [a.arg for a in node.args.posonlyargs + node.args.args]
                first = params[0] if params else "row"
                indent = " " * node.col_offset
                raw = "\n".join(src.split("\n")[node.lineno - 1: node.body[0].lineno - 1])
                i, j = raw.index("("), raw.rindex(")")
                sig = raw[i + 1:j].strip()
                anno = " -> bool" if node.name in ("_is_void_or_red", "_is_noise_name") else (
                    " -> str" if node.name in ("_buyer", "_seller", "_goods", "_row_period", "_inv_type") else "")
                new = (f"{indent}def {node.name}({sig}){anno}:\n"
                       f'{indent}    """字段读取/语义判定（统一实现）。\n\n'
                       f"{indent}    ★ 2026-09-25 收敛：实现已统一到 engine/fieldkit.py（唯一权威）。\n"
                       f"{indent}      原多份私有实现互相不一致，导致同一张发票在不同检测器里结论不同。\n"
                       f'{indent}    """\n'
                       f"{indent}    from engine.fieldkit import {target} as _fk\n"
                       f"{indent}    return _fk({first})")
                replace_func(path, node.name, new)
                print("  ✓ 转发 %s::%s → fieldkit.%s" % (path, name, target))

# B. 改名（词边界替换该文件内的引用）
for path, pairs in RENAMES.items():
    src = io.open(path, encoding="utf-8").read()
    for old, new in pairs:
        n = len(re.findall(r"\b%s\b" % re.escape(old), src))
        src = re.sub(r"\b%s\b" % re.escape(old), new, src)
        print("  ✓ 改名 %s: %s → %s（%d 处）" % (path, old, new, n))
    io.open(path, "w", encoding="utf-8").write(src)

# C. 重复常量 _NOISE_PERSON_NAMES → 引用 fieldkit
for path in ("engine/domain_analysis.py", "engine/verified_rule_engine.py"):
    src = io.open(path, encoding="utf-8").read()
    src = re.sub(r"_NOISE_PERSON_NAMES = \{[^}]*\}",
                 "from engine.fieldkit import NOISE_PERSON_NAMES as _NOISE_PERSON_NAMES  "
                 "# ★ 2026-09-25 唯一来源（原先两处重复定义）",
                 src, count=1)
    io.open(path, "w", encoding="utf-8").write(src)
    print("  ✓ 常量收敛 %s: _NOISE_PERSON_NAMES → fieldkit" % path)
