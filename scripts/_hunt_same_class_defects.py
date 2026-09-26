# -*- coding: utf-8 -*-
"""同源缺陷扫描器：找出与「工资社保」同一性质的其它路径。

工资社保事件由 4 类缺陷叠加而成，本脚本对每一类做全项目扫描并给出证据：

  A 硬门禁跳过   —— 域函数开头 `if not <某资料>: return findings`
                    → 该资料缺失时**整域零产出**（D1 违反：有什么资料就查什么资料）
  B 缺资料反读成违规 —— 用「另一份资料的名单」做差集/比率，名单为空时分母/被减集退化
                    → 把"资料没交"算成"全员违规"（D2 违反）
  C 产出进不了报告 —— 域产出未并入 `_scenario_execution`（报告最终由
                    `seal_governed_findings` 覆盖 all_findings，只留 `_scenario_governed`）
  D 非法等级被丢弃 —— level 不在权威词表 `{极高风险,高风险,中风险,待核验,信息,低风险}`
                    （词表外的等级会被后续环节静默丢弃）

用法：python scripts/_hunt_same_class_defects.py
"""
import ast
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

LEGAL_LEVELS = {"极高风险", "高风险", "中风险", "待核验", "信息", "低风险"}
# 资料类形参名（域函数的入参通常就是这些）
MATERIAL_PARAMS = {
    "salaries", "social_security", "bank_txs", "invoices", "sal_invs", "pur_invs",
    "vouchers", "inventory", "bom_data", "trial_balance_data", "contract_data",
    "tax_declarations", "docs", "fixed_assets", "accounts_payable",
}


def _mask_comments(text: str) -> str:
    """只去注释（保留字符串字面量）：取值校验类检查必须用原文。"""
    out = re.sub(r'"""(?:.|\n)*?"""', lambda m: "" if False else m.group(0), text)
    lines = []
    for ln in text.splitlines():
        s = ln.split("#", 1)[0] if "#" in ln else ln
        lines.append(s)
    return "\n".join(lines)


def scan_A_hard_gates():
    """A：域函数开头的硬门禁（缺一份资料就整域返回空）。"""
    hits = []
    for f in sorted(glob.glob(os.path.join(ROOT, "engine", "*.py"))):
        rel = os.path.relpath(f, ROOT).replace("\\", "/")
        try:
            tree = ast.parse(open(f, encoding="utf-8", errors="replace").read())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("_domain_"):
                continue
            args = {a.arg for a in node.args.args}
            mats = args & MATERIAL_PARAMS
            if len(mats) < 1:
                continue
            # 检查函数体前 3 条语句里是否有 `if not <mat>: return`
            for st in node.body[:3]:
                if not isinstance(st, ast.If):
                    continue
                txt = ast.unparse(st.test)
                if not txt.startswith("not "):
                    continue
                var = txt[4:].strip()
                if var in mats and "return" in ast.unparse(st.body):
                    # 该域是否只依赖这一份资料？若形参里有 ≥2 份资料，则缺一份跳过属 D1 违反
                    hits.append((rel, node.name, node.lineno, var, sorted(mats)))
    return hits


def scan_B_missing_reads_as_violation():
    """B：用另一份资料的名单做差集/比率，名单为空时会把"缺资料"算成"全量违规"。

    启发式判据：函数内出现 `set(...) - set(...)` 或 `for x in A if x not in B` 形态，
    且 A/B 来自不同资料形参，且**函数未对 B 为空做提前返回或标记**。
    """
    hits = []
    for f in sorted(glob.glob(os.path.join(ROOT, "engine", "*.py"))):
        rel = os.path.relpath(f, ROOT).replace("\\", "/")
        try:
            src = open(f, encoding="utf-8", errors="replace").read()
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body_txt = ast.unparse(node)
            args = {a.arg for a in node.args.args}
            mats = args & MATERIAL_PARAMS
            if len(mats) < 2:
                continue
            # 差集/成员判定形态
            diff_pat = re.search(r"for\s+\w+(?:\s*,\s*\w+)?\s+in\s+(\w+)_?\w*\s+if\s+[^\n]*not in\s+(\w+)", body_txt)
            has_empty_guard = re.search(r"if not (\w+)[^\n]*:\s*\n\s*return", body_txt) is not None
            if diff_pat and not has_empty_guard:
                a, b = diff_pat.group(1), diff_pat.group(2)
                hits.append((rel, node.name, node.args.args[0].lineno if node.args.args else node.lineno,
                             f"差集 {a} - {b}，未对 {b} 为空做保护"))
    return hits


def scan_C_domain_not_sealed():
    """C：产出域 vs 可并入报告的域白名单（其余域的产出进不了报告）。"""
    pipe = open(os.path.join(ROOT, "engine", "pipeline.py"), encoding="utf-8").read()
    doms = sorted(set(re.findall(r'domain_results\.append\(\{"domain":\s*"([^"]+)"', pipe)))
    m = re.search(r"_objective_domain_keys = \(([^)]*)\)", pipe, re.S)
    keys = re.findall(r'"([^"]+)"', m.group(1)) if m else []
    unmatched_keys = [k for k in keys if not any(k in d for d in doms)]
    not_sealed = [d for d in doms if not any(k in d for k in keys)]
    return doms, keys, not_sealed, unmatched_keys


def scan_D_illegal_levels():
    """D：level 取值不在权威词表内（会被静默丢弃）。"""
    hits = []
    pat = re.compile(r'["\']level["\']\s*:\s*["\']([^"\']{1,14})["\']')
    files = ["main.py"] + sorted(glob.glob(os.path.join(ROOT, "engine", "**", "*.py"), recursive=True))
    for f in files:
        rel = os.path.relpath(f, ROOT).replace("\\", "/")
        if "__pycache__" in rel:
            continue
        try:
            src = open(f, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        code = _mask_comments(src)
        for m in pat.finditer(code):
            v = m.group(1)
            if not re.search(r"[\u4e00-\u9fff]", v):
                continue          # 变量插值/英文键，跳过
            if v in LEGAL_LEVELS:
                continue
            hits.append((rel, code[:m.start()].count("\n") + 1, v))
    return hits


def main():
    print("=" * 78)
    print("A. 硬门禁跳过（缺一份资料 → 整域零产出）")
    print("=" * 78)
    a = scan_A_hard_gates()
    if not a:
        print("  ✓ 未发现『多资料域因单份缺失而整域返回』")
    for rel, fn, ln, var, mats in a:
        print(f"  ⚠ {rel}:{ln} {fn}() —— `if not {var}: return`，而该域形参含 {mats}")

    print("\n" + "=" * 78)
    print("B. 缺资料反读成违规（差集基准为空 → 全量判违规）")
    print("=" * 78)
    b = scan_B_missing_reads_as_violation()
    if not b:
        print("  ✓ 未发现未加保护的跨资料差集")
    for rel, fn, ln, why in b:
        print(f"  ⚠ {rel}:{ln} {fn}() —— {why}")

    print("\n" + "=" * 78)
    print("C. 产出进不了报告（未并入场景执行 → 被输出封印吞掉）")
    print("=" * 78)
    doms, keys, not_sealed, unmatched = scan_C_domain_not_sealed()
    print(f"  产出的分析域共 {len(doms)} 个；可并入报告的域键 {len(keys)} 个：{keys}")
    if unmatched:
        print(f"  ⚠ 白名单里匹配不到任何域的键（永远不生效）：{unmatched}")
    print(f"  未在白名单内的域 {len(not_sealed)} 个：")
    for d in not_sealed:
        print(f"      · {d}")

    print("\n" + "=" * 78)
    print("D. 非法等级（会被后续环节静默丢弃）")
    print("=" * 78)
    d = scan_D_illegal_levels()
    print(f"  共 {len(d)} 处 level 取值不在权威词表 {sorted(LEGAL_LEVELS)}：")
    for rel, ln, v in d:
        print(f"      {rel}:{ln}  level={v!r}")


if __name__ == "__main__":
    main()
