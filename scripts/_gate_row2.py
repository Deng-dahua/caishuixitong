# -*- coding: utf-8 -*-
"""给第二行（D8 汇总行 / ㊷ 触发信号）配行为级闸门，并做反向验证。

闸门插在 `check_report_consistency` 里线索链断言的紧后面（同一处代码族）。
反向验证：分别破坏"剔除汇总行"与"对题优先"，闸门必须变红。
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NL = chr(10)
CRLF = chr(13) + chr(10)
AUDIT = os.path.join(ROOT, "tools", "audit_consistency.py")
CLUE = os.path.join(ROOT, "engine", "clue_chain.py")
ER = os.path.join(ROOT, "engine", "enterprise_report.py")

GATE_ANCHOR = (
    '        _n_e = (build_clue_chain(_f_e, _rl_e, {}, provided_materials=["银行流水"]).get("nodes") or [{}])[0]' + NL +
    '        if _n_e.get("has_data"):' + NL +
    '            issues.append(("ERROR", "engine/clue_chain.py",' + NL +
    '                           "对题阈值失效：不相干的要件命中证据被当成该环节读数"))'
)
GATE_ADD = GATE_ANCHOR + NL + (
    NL +
    '        # ② 触发信号（㊷，2026-10-04）：**不得"最长者优先"**——否则总落在最长的免责长句上，' + NL +
    '        #   把差异/口径说明挤掉（实测 80/80 条勾稽发现都不带差异说明）。' + NL +
    '        _sig = _terminal_signal_   # noqa: F821  (下方 try 内注入)' + NL +
    '        _dl = ("该结果只说明两个数据口径需要逐月对账。累计方向性差额1,170,164.14元，"' + NL +
    '               "银行贷方收款与销项发票价税合计的差异同时超过25%和10万元。")' + NL +
    '        _got = _sig(_dl, [], {"type": "银行收款大于申报收入"})' + NL +
    '        if "差额" not in _got or "差异" not in _got:' + NL +
    '            issues.append(("ERROR", "engine/clue_chain.py",' + NL +
    '                           "触发信号未选中含差异量的句子（疑似仍在按长度选）——"' + NL +
    '                           "㊷ 差异/口径说明被挤掉"))' + NL +
    '        if _got == "该结果只说明两个数据口径需要逐月对账。":' + NL +
    '            issues.append(("ERROR", "engine/clue_chain.py",' + NL +
    '                           "触发信号选到了不含数字的免责句 —— 触发信号必须带可量化差异"))' + NL +
    NL +
    '        # ③ 汇总行（疑点2 D8，2026-10-04）：汇总行**不是一笔明细**，不得计入笔数与金额。' + NL +
    '        _rows_d8 = [{"序号": 1, "对方单位": "甲", "金额（元）": "275000.00"},' + NL +
    '                    {"序号": 2, "对方单位": "乙", "金额（元）": "137000.00"},' + NL +
    '                    {"序号": 3, "对方单位": "汇总：其他个人／个体往来（未达门槛",' + NL +
    '                     "金额（元）": "170233.01"}]' + NL +
    '        _txt_d8 = _evsum_([{"title": "逐笔明细", "rows": _rows_d8}])   # noqa: F821' + NL +
    '        if "170,233.01" in _txt_d8:' + NL +
    '            issues.append(("ERROR", "engine/enterprise_report.py",' + NL +
    '                           "汇总行的金额被计入触发金额（把汇总当一笔明细）"))' + NL +
    '        if "412,000.00" not in _txt_d8:' + NL +
    '            issues.append(("ERROR", "engine/enterprise_report.py",' + NL +
    '                           "剔除汇总行后的金额合计应为本表各笔之和 412,000.00，实测不符"))' + NL +
    '        if "汇总" not in _txt_d8:' + NL +
    '            issues.append(("ERROR", "engine/enterprise_report.py",' + NL +
    '                           "剔除了汇总行却未如实披露（不得静默少算）"))'
)

# 在 try 块内注入两个被测函数名，避免在模块顶部新增导入
INJECT_OLD = ('        from engine.clue_chain import build_clue_chain' + NL +
              '        import re as _re_clue')
INJECT_NEW = (
    '        from engine.clue_chain import build_clue_chain' + NL +
    '        import re as _re_clue' + NL +
    '        from engine.clue_chain import _terminal_signal as _terminal_signal_' + NL +
    '        from engine.enterprise_report import _evidence_summary as _evsum_'
)

s = io.open(AUDIT, "r", encoding="utf-8", newline="").read()
has_crlf = CRLF in s
t = s.replace(CRLF, NL)
for nm, old, new in (("闸门锚点", GATE_ANCHOR, GATE_ADD), ("导入注入", INJECT_OLD, INJECT_NEW)):
    if t.count(old) != 1:
        print("!! %s 命中 %d 次" % (nm, t.count(old)))
        sys.exit(2)
    t = t.replace(old, new, 1)
io.open(AUDIT, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if has_crlf else t)
print("OK 闸门已加 ②③（触发信号 + 汇总行）")

RUN = (
    "import sys; sys.path.insert(0, %r);"
    "from tools.audit_consistency import check_report_consistency as f;"
    "iss=[i for i in f() if i[0]=='ERROR']; print(len(iss));"
    "[print(chr(32)*4, i[1], i[2][:95]) for i in iss]"
) % ROOT


def run():
    r = subprocess.run([sys.executable, "-c", RUN], capture_output=True, text=True,
                       cwd=ROOT, encoding="utf-8", errors="replace")
    return ((r.stdout or "") + (r.stderr or "")).strip()


print("\n=== 基线 ===")
print(run())

MUTS = [
    ("M1 复现 ㊷：触发信号退回「最长者优先」", CLUE,
     '        best = max(cands, key=_score)',
     '        best = max(cands, key=len)  # MUTATED'),
    ("M2 复现 D8：不再剔除汇总行", ER,
     '            if _is_sum:' + NL + '                _summary_rows += 1' + NL + '                continue',
     '            if False:' + NL + '                _summary_rows += 1' + NL + '                continue'),
]

for name, path, old, new in MUTS:
    base = io.open(path, "r", encoding="utf-8", newline="").read()
    crlf = CRLF in base
    t2 = base.replace(CRLF, NL)
    if t2.count(old) != 1:
        print("\n!! %s anchor 命中 %d 次（变异无效，不算通过）" % (name, t2.count(old)))
        continue
    t2 = t2.replace(old, new, 1)
    io.open(path, "w", encoding="utf-8", newline="").write(t2.replace(NL, CRLF) if crlf else t2)
    print("\n=== %s ⇒ ===" % name)
    print(run())
    io.open(path, "w", encoding="utf-8", newline="").write(base)

print("\n=== 全部还原后 ===")
print(run())
