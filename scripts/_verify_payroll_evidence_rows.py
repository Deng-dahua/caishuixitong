# -*- coding: utf-8 -*-
"""验证「工资名册与社会保险人员范围差异」疑点的明细表已与疑点语义匹配。

验证链：
  1. 用真实上传资料（工资表 / 社保清单）跑 `_scan_payroll_social`;
  2. 确认该发现**自带** evidence_rows（逐人逐月：姓名/月份/工资/社保基数/匹配状态）;
  3. 再跑一遍 `pipeline._enrich_evidence_rows` 通用兜底采样，确认它**不再覆盖/混入**
     无关记账凭证（此前实测混入应收 161 万、结转损益 152 万的凭证 4 张）;
  4. 用报告渲染 `_finding_detail_tables` 看最终出到读者面前的表是什么样。
"""
import glob
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import main  # noqa: E402
from engine.enterprise_report import _finding_detail_tables  # noqa: E402
from engine.pipeline import _enrich_evidence_rows  # noqa: E402
from engine.verified_rule_engine import _scan_payroll_social  # noqa: E402

U = os.path.join("data", "uploads", "1")


def _parse(fp):
    ext = os.path.splitext(fp)[1].lower()
    return main._parse_excel_structured(fp, ext) or {}


# 只解析本验证需要的三类资料（142 个上传文件全解析太慢且触发环境守护）
_KEEP = ("工资", "社保")


def _collect():
    data = {"salaries": [], "social_security": [], "vouchers": []}
    for fp in sorted(glob.glob(os.path.join(U, "*"))):
        if not fp.lower().endswith((".xls", ".xlsx")):
            continue
        if not any(k in os.path.basename(fp) for k in _KEEP):
            continue
        p = _parse(fp)
        t, rows = p.get("type", ""), p.get("rows") or []
        if t == "salary":
            data["salaries"].extend(rows)
        elif t == "social_security":
            data["social_security"].extend(rows)
        elif t == "voucher":
            data["vouchers"].extend(rows)
    return data


def main2():
    data = _collect()
    print("工资行 %d / 社保行 %d / 凭证行 %d"
          % (len(data["salaries"]), len(data["social_security"]), len(data["vouchers"])))
    spec = {"id": "VR-PAY-001", "name": "工资名册与社会保险人员范围差异",
            "type": "工资名册与社会保险人员范围差异",
            "required_sources": ["工资表", "社保明细"]}
    fs = _scan_payroll_social(data, spec)
    if not fs:
        print("!! 扫描器未产出发现")
        return 1
    f = dict(fs[0])
    print("发现类型: %s" % f.get("type"))
    ev = f.get("evidence_rows") or []
    print("① 自有 evidence_rows: %d 行" % len(ev))
    for r in ev[:6]:
        print("     %s | %s | 工资=%s | 社保基数=%s | %s"
              % (r.get("姓名"), r.get("月份"), r.get("工资"), r.get("社保基数"), r.get("匹配状态")))
    if len(ev) > 6:
        print("     …（共 %d 行）" % len(ev))

    # ③ 通用兜底不得再混入
    _enrich_evidence_rows([f], [], [], data["salaries"], data["vouchers"], "测试")
    ev2 = f.get("evidence_rows") or []
    voucher_rows = [r for r in ev2 if r.get("source") == "记账凭证"]
    print("③ 经通用兜底后：证据行 %d 行，其中记账凭证行 %d 行（须为 0）"
          % (len(ev2), len(voucher_rows)))
    for r in voucher_rows[:5]:
        print("     !! 混入无关凭证: %s %s %s" % (r.get("ref_id"), r.get("ref_label"), r.get("amount")))

    # ④ 报告渲染
    tables = _finding_detail_tables(f)
    print("④ 报告渲染明细表 %d 张" % len(tables))
    for t in tables:
        print("    title=%s  行数=%d" % (t.get("title"), len(t.get("rows") or [])))
        print("    columns=%s" % t.get("columns"))
        for row in (t.get("rows") or [])[:3]:
            print("      ", row)

    bad = len(voucher_rows)
    print("\n结论: %s" % ("通过——明细表与疑点语义匹配" if bad == 0 and ev else "未通过"))
    return 0 if (bad == 0 and ev) else 1


if __name__ == "__main__":
    sys.exit(main2())
