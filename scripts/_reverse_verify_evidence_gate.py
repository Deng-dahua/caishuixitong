# -*- coding: utf-8 -*-
"""`check_evidence_rows_semantic_match` 闸门的**干净反向验证**（故意破坏 → 闸门必须变红）。

每次破坏都要满足两条，缺一即闸门是假的：
  1. 红色必须来自**判据**（含"闸门 check_evidence_rows_semantic_match"字样）；
  2. 不得是 `SyntaxError/解析失败/产物解析失败` 这类白捡的红色。

场景设计（对**新代码**做破坏，证明闸门守的是本次修的两条根因）：
  0 基线：新代码跑出的发现（detector 交有自有 evidence_rows）→ 闸门应**全绿**；
  A detector 回归（删掉自有 evidence_rows 后重跑通用兜底）→ 闸门必须报「无关记账凭证」；
  B 工资键表回归（证据行仍按旧键表取，金额恒 0）→ 闸门必须报「工资金额全 0 的假证据」；
  C 无关改动（只改个字段值）→ 闸门应**保持全绿**。
"""
import glob
import json
import os
import shutil
import sys
import tempfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import main  # noqa: E402
from engine.numparse import to_number  # noqa: E402
from engine.pipeline import _enrich_evidence_rows  # noqa: E402
from engine.verified_rule_engine import _scan_payroll_social  # noqa: E402
from tools.audit_consistency import check_evidence_rows_semantic_match  # noqa: E402

U = os.path.join("data", "uploads", "1")
_PICK = ("工资", "社保", "序时账")


def _collect():
    data = {"salaries": [], "social_security": [], "vouchers": []}
    for fp in sorted(glob.glob(os.path.join(U, "*"))):
        if not fp.lower().endswith((".xls", ".xlsx")):
            continue
        if not any(k in os.path.basename(fp) for k in _PICK):
            continue
        try:
            p = main._parse_excel_structured(fp, os.path.splitext(fp)[1].lower()) or {}
        except Exception:  # noqa: BLE001
            continue
        t, rows = p.get("type", ""), p.get("rows") or []
        if t == "salary":
            data["salaries"].extend(rows)
        elif t == "social_security":
            data["social_security"].extend(rows)
        elif t == "voucher":
            data["vouchers"].extend(rows)
    return data


SPEC = {"id": "VR-PAY-001", "name": "工资名册与社会保险人员范围差异",
        "type": "工资名册与社会保险人员范围差异",
        "required_sources": ["工资表", "社保明细"]}


def _dump(findings, path):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"all_findings": findings}, fh, ensure_ascii=False)
    return path


def _gate(path):
    return check_evidence_rows_semantic_match(path)


def _summary(issues):
    errs = [i for i in issues if i[0] == "ERROR"]
    warns = [i for i in issues if i[0] == "WARN"]
    return len(errs), len(warns), errs, warns


def main3():
    data = _collect()
    print("工资行 %d / 社保行 %d / 凭证行 %d"
          % (len(data["salaries"]), len(data["social_security"]), len(data["vouchers"])))
    findings = _scan_payroll_social(data, SPEC)
    if not findings:
        print("!! 扫描器未产出发现，反向验证无法进行")
        return 1
    base_f = dict(findings[0])
    print("基线发现: %s（自有 evidence_rows %d 行）"
          % (base_f.get("type"), len(base_f.get("evidence_rows") or [])))

    tmpdir = tempfile.mkdtemp(prefix="gate_")
    results = {}

    # 0 基线
    p0 = _dump([dict(base_f)], os.path.join(tmpdir, "s0.json"))
    e0, w0, _, _ = _summary(_gate(p0))
    results["0 基线"] = (e0, w0)
    print("  0 基线                 : ERROR %d / WARN %d" % (e0, w0))

    # A detector 回归：回放**用户复核实测的那张表**的原 8 行证据
    #   （4 张无关的记账凭证 + 4 行金额恒 0 的工资表人员行 —— 疑点是「工资名册与社保
    #     人员范围差异」，表里却挂着应收 161 万收款凭证和 0 元工资行）。
    #   这里写死而不从产物里读：产物每次跑都会覆盖，硬编码才能稳定复现用户看到的现象。
    _accident = [
        {"source": "记账凭证", "ref_id": "记-2", "ref_label": "收到款项",
         "amount": 1611200.0, "counterparty": "应收账款/上海蕴世广告传媒有限公司", "date": "", "note": ""},
        {"source": "记账凭证", "ref_id": "记-20", "ref_label": "结转期间损益",
         "amount": 1524325.98, "counterparty": "主营业务成本", "date": "", "note": ""},
        {"source": "记账凭证", "ref_id": "记-1", "ref_label": "销售服务",
         "amount": 1494054.59, "counterparty": "主营业务收入/服务收入", "date": "", "note": ""},
        {"source": "记账凭证", "ref_id": "记-19", "ref_label": "结转期间损益",
         "amount": 1494054.59, "counterparty": "本年利润", "date": "", "note": ""},
        {"source": "工资表", "ref_id": "杨莹", "ref_label": "", "amount": 0.0,
         "counterparty": "", "date": "", "note": ""},
        {"source": "工资表", "ref_id": "徐瑶", "ref_label": "", "amount": 0.0,
         "counterparty": "", "date": "", "note": ""},
        {"source": "工资表", "ref_id": "黄奕珊", "ref_label": "", "amount": 0.0,
         "counterparty": "", "date": "", "note": ""},
        {"source": "工资表", "ref_id": "李昭阳", "ref_label": "", "amount": 0.0,
         "counterparty": "", "date": "", "note": ""},
    ]
    fa = dict(base_f)
    fa["evidence_rows"] = _accident
    va = [r for r in _accident if r.get("source") == "记账凭证"]
    pa = _dump([fa], os.path.join(tmpdir, "sA.json"))
    eA, wA, errA, _ = _summary(_gate(pa))
    results["A detector 回归"] = (eA, wA)
    print("  A 事故态证据行回放      : ERROR %d / WARN %d（回放无关凭证 %d 行）"
          % (eA, wA, len(va)))
    for i in errA[:2]:
        print("      └ %s" % i[2][:150])

    # B 工资键表回归：证据行走旧键表（模拟 2026-10-01 事故态的 0 元假证据）
    def _old_salary_row(s):
        return {"source": "工资表",
                "ref_id": str(s.get("姓名") or s.get("name") or "")[:15] or "-",
                "ref_label": str(s.get("部门") or s.get("dept") or "")[:20],
                "amount": to_number(s.get("实发金额", s.get("实发", s.get("amount", 0)))),
                "counterparty": "", "date": str(s.get("period") or "")[:10], "note": ""}

    # 取 4 个**不同人月**的工资行（按 (姓名, 期间) 去重），避免同一人重复 4 行
    _seen, top_sal = set(), []
    for _s in sorted(data["salaries"],
                     key=lambda x: to_number(x.get("salary")), reverse=True):
        _k = (str(_s.get("name") or _s.get("employee_name") or ""),
              str(_s.get("period_start") or _s.get("period_end") or ""))
        if _k in _seen:
            continue
        _seen.add(_k)
        top_sal.append(_s)
        if len(top_sal) == 4:
            break
    fb = dict(base_f)
    fb["evidence_rows"] = [_old_salary_row(s) for s in top_sal]
    pb = _dump([fb], os.path.join(tmpdir, "sB.json"))
    eB, wB, errB, _ = _summary(_gate(pb))
    results["B 工资键表回归"] = (eB, wB)
    print("  B 工资键表回归          : ERROR %d / WARN %d（金额为 0 的行 %d 行）"
          % (eB, wB, sum(1 for r in fb["evidence_rows"] if to_number(r.get("amount")) == 0)))
    for i in errB[:2]:
        print("      └ %s" % i[2][:150])

    # C 无关改动
    fc = dict(base_f)
    fc["suggestion"] = "无关改动：仅改建议字段"
    pc = _dump([fc], os.path.join(tmpdir, "sC.json"))
    eC, wC, _, _ = _summary(_gate(pc))
    results["C 无关改动"] = (eC, wC)
    print("  C 无关改动              : ERROR %d / WARN %d" % (eC, wC))

    # 判定：红色必须来自判据（不是解析失败）
    def _has_judgement(errs):
        return any("check_evidence_rows_semantic_match" in e[2] for e in errs)
    ok = True
    # (名称, 期望是红色还是绿色, 取值函数)
    checks = [("0 基线", "绿", lambda: results["0 基线"]),
              ("A 事故态证据行回放", "红", lambda: results["A detector 回归"]),
              ("B 工资键表回归", "红", lambda: results["B 工资键表回归"]),
              ("C 无关改动", "绿", lambda: results["C 无关改动"])]
    print("\n── 反向验证判定 ──")
    for name, want, getv in checks:
        n_err = getv()[0]
        good = (n_err == 0) if want == "绿" else (n_err > 0)
        ok = ok and good
        print("  %-18s 期望%s → ERROR %d → %s"
              % (name, want, n_err, "通过" if good else "失败"))
    ok = ok and _has_judgement(errA) and _has_judgement(errB)
    print("  红色来自判据（非解析失败）: %s" % ("通过" if (ok and _has_judgement(errA)
                                                     and _has_judgement(errB)) else "失败"))
    shutil.rmtree(tmpdir, ignore_errors=True)
    print("\n结论: %s" % ("闸门反向验证通过（4/4：基线绿、事故态与工资键表两处回归红、无关改动绿）"
                         if ok else "闸门不达标，需修闸门"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main3())
