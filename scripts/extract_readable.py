# -*- coding: utf-8 -*-
"""从 run_four_companies 产出的 full.json 中抽取 enterprise_readable_report 的正文，
生成可读 markdown，供人工评估"稽查员分身"达成度。不重复跑分析。
"""
import sys, os, json

ROOT = r"c:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong"
OUT = os.path.join(ROOT, "scripts", "four_reports")
SYS = os.path.join(OUT, "readable")

# 只保留四类内容：确认问题 / 已执行无异常 / 处理意见+验收 / 资料缺失未完成
CHAPTER_ORDER = [
    "identity", "summary",
    "confirmed_problems", "completed_checks",
    "action_plan", "recheck",
    "further_checks", "capability_boundary", "inspection_questions_report",
    "report_statement",
]

TITLE_MAP = {
    "identity": "一、企业信息",
    "summary": "二、本轮检查总体结论",
    "confirmed_problems": "三、本轮稽查确认的具体问题",
    "completed_checks": "四、已经执行且本轮未发现达到条件异常的检查",
    "action_plan": "五、稽查处理意见和整改验收标准",
    "recheck": "五（续）、下一轮复查安排",
    "further_checks": "六、因资料缺失或不完整而无法完成的检查",
    "capability_boundary": "六（续）、系统能力边界",
    "inspection_questions_report": "六（续）、待企业澄清事项（稽查询问清单）",
    "report_statement": "七、报告性质和使用说明",
}

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
    s = er.get("summary") or {}
    if s:
        lines.append(f"- 接收文件 {s.get('received_material_count', '—')} 个，归并 {s.get('material_category_count', '—')} 类资料")
        lines.append(f"- 确认具体问题 {s.get('confirmed_problem_count', '—')} 项；已执行无异常检查 {s.get('completed_check_count', '—')} 项；资料缺失需补件 {s.get('further_check_count', '—')} 项")
    lines.append("")

    total = sum(len(x) for x in lines)
    for key in CHAPTER_ORDER:
        if key not in er:
            continue
        v = er[key]
        title = TITLE_MAP.get(key) or (v.get("title") or v.get("heading") or key if isinstance(v, dict) else key)
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
