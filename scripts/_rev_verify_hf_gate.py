# -*- coding: utf-8 -*-
"""反向验证：故意破坏公积金闸门的每条契约 → 必须报 ERROR；随后原样恢复。"""
import io, hashlib, subprocess, sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ["engine/domain_analysis.py", "engine/subject_consistency.py",
         "engine/monthly_reconcile.py", "engine/pipeline.py",
         "engine/material_names.py", "engine/evidence_chain.py"]
backup = {}
for f in FILES:
    p = os.path.join(ROOT, f)
    b = io.open(p, "rb").read()
    backup[f] = b

def run_gate():
    r = subprocess.run([sys.executable, "tools/audit_consistency.py"],
                       cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    # 断言口径：**任何新增 ERROR 都算报警**（不能只看含"公积金"的行 ——     # 否则「或」语义这类不带该词的闸门会假绿）
    lines = [L for L in out.split("\n") if L.strip().startswith("ERROR")]
    return lines

def patch(rel, old, new):
    p = os.path.join(ROOT, rel)
    s = io.open(p, encoding="utf-8").read()
    assert old in s, "锚点未找到: %s @ %s" % (old[:40], rel)
    io.open(p, "w", encoding="utf-8", newline="\n").write(s.replace(old, new, 1))

def restore():
    for f, b in backup.items():
        io.open(os.path.join(ROOT, f), "wb").write(b)

cases = [
    ("移除签名中的 housing_fund", "engine/domain_analysis.py",
     "def _domain_salary_ss_hf_compare(salaries, social_security, housing_fund=None):",
     "def _domain_salary_ss_hf_compare(salaries, social_security):"),
    ("把公积金金额勾稽轴重新挂回 RL-SPT-010", "engine/subject_consistency.py",
     '"公积金缴存对等":          ("", "公积金缴存对等逐月不匹配"),',
     '"公积金缴存对等":          ("RL-SPT-010", "公积金缴存对等逐月不匹配"),'),
    ("取消公积金比对调用", "engine/domain_analysis.py",
     "findings.extend(_housing_fund_findings(sal_rows, sal_pm, sal_amt, sal_names, housing_fund))",
     "pass  # findings.extend(_housing_fund_findings(...))"),
    ("monthly_reconcile 自建公积金月份别名", "engine/monthly_reconcile.py",
     "from engine.payroll_rules import hf_month, hf_amount",
     'from engine.payroll_rules import hf_month, hf_amount\n    _ = ("counterparty",)'),
    ("去掉「或」语义（类别层不再调 strict_category_groups）", "engine/evidence_chain.py",
     "_groups = _strict_category_groups(evidence_name)",
     "_groups = None  # 故意破坏：回退按「且」判"),
]
ok = True
for name, rel, old, new in cases:
    restore()
    patch(rel, old, new)
    hits = run_gate()
    red = bool(hits)
    print(("[RED ✓] " if red else "[GREEN ✗ 未报警] ") + name + ("  | " + hits[0].strip()[:110] if hits else ""))
    ok = ok and red
restore()
# 恢复自检
for f, b in backup.items():
    a = hashlib.md5(io.open(os.path.join(ROOT, f), "rb").read()).hexdigest()
    c = hashlib.md5(b).hexdigest()
    assert a == c, "恢复失败: %s" % f
print("\n全部反向验证通过" if ok else "\n存在未报警的契约（闸门有假绿）")
