# -*- coding: utf-8 -*-
"""从 run_four_companies 产出的 full.json 中抽取 enterprise_readable_report 的正文，
生成可读 markdown，供人工评估"稽查员分身"达成度。不重复跑分析。
"""
import sys, os, json

ROOT = r"c:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong"
OUT = os.path.join(ROOT, "scripts", "four_reports")
SYS = os.path.join(OUT, "readable")

# 想看的章节（叙事 + 各能力章）；按顺序排版
CHAPTER_ORDER = [
    "identity", "inspector_perspective", "summary", "discovery_overview",
    "inspection_procedures", "materials", "confirmed_problems", "completed_checks",
    "cross_enterprise_report", "external_verify_report",
    "bank_flow_report", "two_tax_report", "input_voucher_report",
    "false_invoice_report", "fund_loop_report",
    "inspection_questions_report",
    "capability_boundary", "action_plan", "further_checks", "recheck", "report_statement",
]

PER_CHAPTER_CAP = 5000
TOTAL_CAP = 90000


def dump_val(v, cap=PER_CHAPTER_CAP):
    if isinstance(v, str):
        s = v
    else:
        try:
            s = json.dumps(v, ensure_ascii=False, indent=1, default=str)
        except Exception:
            s = str(v)
    if len(s) > cap:
        s = s[:cap] + f"\n…[截断，原长 {len(s)} 字符]"
    return s


def extract(cid):
    path = os.path.join(OUT, f"company_{cid}_full.json")
    with open(path, "r", encoding="utf-8") as f:
        report = json.load(f)
    er = report.get("enterprise_readable_report") or {}
    name = report.get("company_name") or er.get("identity") or f"company_{cid}"
    if isinstance(name, dict):
        name = name.get("name") or str(name)

    lines = [f"# 企业 {cid} 涉税稽查工作报告（可读提取）\n"]
    # 顶部：6 大能力 verdict
    comp = report.get("comprehensive") or {}
    caps = ["two_tax_income", "bank_flow", "input_voucher", "false_invoice", "fund_loop", "cross_enterprise"]
    lines.append("## 一、六大能力结论速览")
    for k in caps:
        sec = comp.get(k)
        if isinstance(sec, dict):
            lines.append(f"- **{k}**: available={sec.get('available')} | verdict={sec.get('verdict') or sec.get('risk_level') or '—'}")
    lines.append("")

    total = sum(len(x) for x in lines)
    for key in CHAPTER_ORDER:
        if key not in er:
            continue
        v = er[key]
        title = ""
        if isinstance(v, dict):
            title = v.get("title") or v.get("heading") or key
        else:
            title = key
        body = dump_val(v)
        sec = f"\n## {title}\n\n{body}\n"
        if total + len(sec) > TOTAL_CAP:
            lines.append(f"\n…[已达总字数上限 {TOTAL_CAP}，其余章节略]")
            break
        lines.append(sec)
        total += len(sec)

    txt = "\n".join(lines)
    os.makedirs(SYS, exist_ok=True)
    outp = os.path.join(SYS, f"company_{cid}_readable.md")
    with open(outp, "w", encoding="utf-8") as f:
        f.write(txt)
    print(f"[OK] company {cid} -> {outp} ({len(txt)} chars)", flush=True)


if __name__ == "__main__":
    for cid in [1, 2, 3, 4]:
        extract(cid)
    print("ALL DONE", flush=True)
