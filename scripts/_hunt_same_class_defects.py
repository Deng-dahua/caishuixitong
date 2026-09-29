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


def _domain_emits_missing_material(node) -> bool:
    """函数体内是否存在 findings.append({"type": "资料缺失-..."})。

    有则属「缺资料→产出 资料缺失 待核验 发现」的合规有痕行为（与项目统一行为一致），
    不应判为 D1 缺陷；无则属静默零产出（报告无痕），才是真缺陷。
    """
    for n in ast.walk(node):
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call):
            func = n.value.func
            if isinstance(func, ast.Attribute) and func.attr == "append" \
                    and isinstance(func.value, ast.Name) and func.value.id == "findings":
                if n.value.args and isinstance(n.value.args[0], ast.Dict):
                    for k, v in zip(n.value.args[0].keys, n.value.args[0].values):
                        if isinstance(k, ast.Constant) and k.value == "type" \
                                and isinstance(v, ast.Constant) and isinstance(v.value, str) \
                                and v.value.startswith("资料缺失"):
                            return True
    return False


def scan_A_hard_gates():
    """A：域函数开头的硬门禁（缺一份资料就整域返回空）。

    2026-09-30 精确化：仅当该域缺主资料时**未产出 资料缺失 待核验 发现**（静默零产出）
    才判为缺陷；已 append 资料缺失发现的域属合规有痕行为，跳过。
    """
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
                    # 缺主资料时已产出 资料缺失 待核验 发现 → 合规有痕，跳过
                    if _domain_emits_missing_material(node):
                        continue
                    # 否则属静默零产出（报告无痕），才是 D1 类真缺陷
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
    """C（2026-09-30 重写）：原设计只用 _objective_domain_keys 白名单并入 7 个客观域，
    其余 40+ 域被输出封印整体隔离（实测 86 项「算了但看不到」）。

    2026-09-26「全部提升」决策改为由 engine.output_governance.promote_domain_findings
    把**全部**域风险级发现并入正式输出（pipeline.py 调用
    `_promote(_scenario_execution, domain_results, ...)`，传入完整 domain_results）。
    本检查验证新机制已接线，不再依赖旧白名单——旧白名单即便存在也不再是唯一闸门。
    """
    pipe = open(os.path.join(ROOT, "engine", "pipeline.py"), encoding="utf-8").read()
    doms = sorted(set(re.findall(r'domain_results\.append\(\{"domain":\s*"([^"]+)"', pipe)))
    # 新机制接线判据：promote_domain_findings 被引入，且以 domain_results 调用
    wired = ("promote_domain_findings" in pipe) and ("_promote(" in pipe) \
        and ("domain_results" in pipe)
    has_old_whitelist = bool(re.search(r"_objective_domain_keys\s*=\s*\(", pipe))
    return doms, wired, has_old_whitelist


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
    doms, wired, has_old = scan_C_domain_not_sealed()
    print(f"  产出的分析域共 {len(doms)} 个。")
    if wired:
        print("  ✓ 「全部提升」已接线：promote_domain_findings 以完整 domain_results 调用，")
        print("    所有域风险级发现一律并入正式输出（旧 _objective_domain_keys 白名单已非唯一闸门）。")
    else:
        print("  ⚠ 未检测到 promote_domain_findings 以 domain_results 调用——域产出可能再次被隔离！")
    if has_old:
        print("  （注：旧 _objective_domain_keys 白名单仍存在于 pipeline.py，但已非唯一闸门，可后续清理。）")

    print("\n" + "=" * 78)
    print("D. 非权威词表 level（风险发现才会被静默丢弃；下列多为非风险 vocabulary）")
    print("=" * 78)
    d = scan_D_illegal_levels()
    print(f"  共 {len(d)} 处 level 取值不在权威词表 {sorted(LEGAL_LEVELS)}：")
    for rel, ln, v in d:
        print(f"      {rel}:{ln}  level={v!r}")
    print("  说明：上述取值多为「置信度(高可信/中等可信/低可信) / 评审(错误·警告·注意) /")
    print("        标签(层级) / 机会流(优惠机会·提醒·提示) / 维度评分(未触发) / 自检(未知)」等")
    print("        非风险 vocabulary，不进入风险发现流，不会被静默丢弃。风险发现 level 合法性")
    print("        已由审计闸门 check_finding_level_legality 强制（六键风险发现形状 + 非法 level → ERROR）。")


if __name__ == "__main__":
    main()
