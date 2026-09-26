# -*- coding: utf-8 -*-
"""一次性迁移：把全项目 25 处私有数值解析统一委托到 engine/numparse.py（唯一权威）。

替换策略：
  · 纯解析器（21 处）→ `return to_number(<第一参数>[, <第二参数>])`
  · 记录取金额（4 处 `_amt`/`_amount_of`）→ `return first_amount(row, absolute=True)`
各模块保留原函数名与**原始签名**（含默认值），仅实现改为委托。
"""
import ast
import io
import os

REPO = r"c:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong"
os.chdir(REPO)

TARGETS = {
    "engine/ap_aging.py": ["_to_float"],
    "engine/ar_aging.py": ["_to_float"],
    "engine/bank_flow.py": ["_safe"],
    "engine/business_model.py": ["_number"],
    "engine/chain_executor.py": ["_safe_float"],
    "engine/deduction_limit_detector.py": ["_safe"],
    "engine/domain_analysis.py": ["_number", "_amount_of"],
    "engine/export_rebate_crosscheck.py": ["_num"],
    "engine/external_check_reminder.py": ["_safe"],
    "engine/false_invoice.py": ["_safe"],
    "engine/fund_loop.py": ["_safe"],
    "engine/fund_matching.py": ["_amount_of"],
    "engine/industry_benchmark.py": ["_num"],
    "engine/input_voucher.py": ["_safe"],
    "engine/invoice_pattern_detector.py": ["_safe", "_amt"],
    "engine/monthly_reconcile.py": ["_num"],
    "engine/red_team.py": ["_num"],
    "engine/revenue_authenticity.py": ["_number"],
    "engine/structure_mismatch_detector.py": ["_safe", "_amt"],
    "engine/threshold_scanner.py": ["_safe_float"],
    "engine/two_tax_income.py": ["_safe"],
    "engine/verified_rule_engine.py": ["_number"],
}
EXTRACT_NAMES = {"_amt", "_amount_of"}

NOTE = ("    ★ 2026-09-25 收敛：实现已统一到 engine/numparse.py（唯一权威）。\n"
        "      原私有实现遇 \"12,000.00\" / \"￥1,234.56\" 等会静默返回 0，\n"
        "      导致同一金额在不同模块被算成不同值（报告自相矛盾 / 规则漏触发）。\n")

total = 0
for path, names in TARGETS.items():
    src = io.open(path, encoding="utf-8").read()
    lines = src.split("\n")
    tree = ast.parse(src)
    edits = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name not in names:
            continue
        params = [a.arg for a in node.args.posonlyargs + node.args.args]
        if not params:
            print("  [跳过] %s::%s 无参数" % (path, node.name))
            continue
        first = params[0]
        # 从源码取原始签名文本（保留默认值原样）
        raw = "\n".join(lines[node.lineno - 1: node.body[0].lineno - 1])
        i, j = raw.index("("), raw.rindex(")")
        params_text = raw[i + 1:j].strip()
        indent = " " * node.col_offset
        anno = " -> float" if node.returns is not None else ""
        if node.name in EXTRACT_NAMES:
            body = (f"{indent}    from engine.numparse import first_amount as _first_amount\n"
                    f"{indent}    return _first_amount({first}, absolute=True)")
        else:
            # 第二参数若存在（如 default=0.0）原样透传
            args = [a.arg for a in node.args.posonlyargs + node.args.args]
            arg2 = ""
            if len(args) >= 2 and node.args.defaults:
                arg2 = ", " + args[1]
            body = (f"{indent}    from engine.numparse import to_number as _to_number\n"
                    f"{indent}    return _to_number({first}{arg2})")
        new = (f"{indent}def {node.name}({params_text}){anno}:\n"
               f'{indent}    """数值解析（统一实现）。\n\n' + NOTE + f'{indent}    """\n' + body)
        edits.append((node.lineno - 1, node.end_lineno, new, node.name))
    for start, end, new, nm in sorted(edits, reverse=True):
        lines[start:end] = new.split("\n")
        total += 1
        print("  ✓ %s::%s" % (path, nm))
    io.open(path, "w", encoding="utf-8").write("\n".join(lines))

print("\n共统一 %d 处" % total)
