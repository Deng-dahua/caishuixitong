# -*- coding: utf-8 -*-
"""阶段3：编号体系落地 + 唯一事实源映射表。

产出：
    baseline/阶段3/编号分配.json           本样本七类短号的实际分配（现算）
    baseline/阶段3/唯一事实源映射表.json    概念 → 唯一权威（含模块存在性校验）
    docs/第12批_报告修订闭环/04_阶段3_编号体系与唯一事实源映射表.md

原则：
  * 编号一律由 engine/numbering.py::ReportNumbering 生成，本脚本不拼接任何编号字符串。
  * 唯一事实源映射表的每条都做**模块存在性校验**：不存在的标『未落地』，不假称已实现。
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.numbering import ReportNumbering  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "baseline")
OUT = os.path.join(BASE, "阶段3")
DOCS = os.path.join(ROOT, "docs", "第12批_报告修订闭环")
NOW = datetime.now().strftime("%Y-%m-%d %H:%M")

SRC_TXT = os.path.join(BASE, "V1.0", "原始报告_纯文本.txt")
RE_ITEM = re.compile(r"^(疑点\d+)[：:]")
RE_LAW_NAME = re.compile(r"《([^》]{2,60})》")
# 法规名判据：含下列词之一才视为法规，否则是表单名/刊物名（如《红字发票信息确认单》《中国国家地理》）
LAW_HINT = re.compile(r"法$|条例|办法|规定|通知|决定|公告|细则|解释|批复|暂行")
RE_MATERIAL_ITEM = re.compile(r"^\d+\.\s*(\S.{0,38})$")
RE_TABLE_START = "<<TABLE_START>>"

# 唯一事实源映射表（唯一权威清单；新增概念只加一行）
SSOT = [
    ("数值解析（金额/比例/人数）", "engine/numparse.py", "AMOUNT_KEYS 漏登＝静默返 0；新增字段只加此处"),
    ("金额口径（含税/不含税/剔除口径）", "engine/fact_store.py", "Fact 五要素：scope/tax_inclusive/period/source/derivation"),
    ("风险等级词表", "engine/risk_levels.py", "LEGAL_LEVELS 为唯一合法词表，其余模块薄转发"),
    ("结论分级（L1~L4）", "engine/conclusion_grade.py + config/conclusion_grades.json", "关键证据缺失触发一票否决，降为 L2/待核验"),
    ("行业判定与业态资料剔除", "engine/industry_resolver.py", "resolve_into_profile() 为唯一写回点"),
    ("资料类别（14 类）", "engine/material_names.py", "CATEGORIES；类别名≠资料名"),
    ("资料识别", "engine/material_recognition.py", "_SUPP_ENTRIES"),
    ("资料是否已提供（严格口径）", "engine/redline_engine.py::_available_materials", "必须严格 15 类，放宽会错升 confirmed"),
    ("发票字段", "engine/fieldkit.py", "发票类字段唯一解析入口"),
    ("月份键 / 发现身份", "engine/findingkit.py", "finding_identity 用于豁免记账"),
    ("成本与费用判定", "engine/account_classifier.py", "判不出必须待核，严禁默认判成本"),
    ("用工与社保缴费参数", "engine/payroll_rules.py", "法定参数/口径/字段名唯一权威"),
    ("法条引用", "engine/legal_citation.py", "文号与版本状态；未核版本不得作判据"),
    ("编号（底稿 WB-* + 报告短号 R/C/F/D/S/L/T）", "engine/numbering.py", "NumberingService / ReportNumbering，禁止自行拼接"),
    ("事实登记（唯一事实源）", "engine/fact_store.py", "FactStore.declare；同键不同值保留 revisions 不静默覆盖"),
    ("重复判定（六类）", "config/dedup_rules.json", "新增一类只加行"),
    ("根因定义", "config/root_causes.json", "根因→症状→修复落点唯一权威"),
    ("质量门禁（四道 38 条）", "engine/quality_gates.py + config/quality_gates.json", "attach_to_report 为唯一接线点"),
    ("归档规范", "config/archive_spec.json", "底稿号/页眉页脚/索引/导出包"),
    ("替代程序库", "config/alternative_evidence.json", "键＝material_names 的 14 类，禁自造"),
    ("证据现状与缺口", "engine/evidence_chain.py", "missing 须过业态剔除"),
    ("报告文本生成", "engine/sentencekit.py", "报告句唯一生成点"),
    ("文案护栏", "engine/text_guardrails.py", "禁用含糊词与越界定性"),
    ("说人话表达", "engine/plain_language.py", "面向企业负责人的表述"),
    ("线索链资料/读数同源", "engine/clue_chain.py", "materials_available + _on_topic_reading"),
    ("工作底稿编排（Skill 层）", "engine/workpaper_generator.py", "十五步编排，尚未登记 skill_specs.json"),
]


def check_path(p: str) -> tuple[bool, str]:
    """模块存在性校验：既查包路径也查文件路径。

    形如 `engine/x.py::_fn` 的写法只校验 `::` 之前的文件（函数是文件内的成员，不是独立文件）。
    """
    rel = p.split(" ")[0].split("+")[0].strip()
    rel = rel.split("::")[0].strip()
    fs = rel.replace(".", os.sep)
    for cand in (os.path.join(ROOT, fs + ".py"), os.path.join(ROOT, fs), os.path.join(ROOT, rel)):
        if os.path.exists(cand):
            return True, rel
    return False, rel


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(DOCS, exist_ok=True)
    lines = open(SRC_TXT, encoding="utf-8").read().split("\n")
    rn = ReportNumbering()

    # ---------------- 风险事项 R（16 项，按文档出现顺序）
    risks = []
    for i, l in enumerate(lines, 1):
        s = l.strip()
        m = RE_ITEM.match(s)
        if m:
            title = s.split("：", 1)[1] if "：" in s else s
            title = re.sub(r"办理顺序：第[一二三四五六七八九十]+项$", "", title).strip("（）")
            risks.append({"seq": len(risks) + 1, "no": rn.next("risk"), "line": i,
                          "old": m.group(1), "title": title[:60]})
    assert len(risks) == 16, f"疑点数应为 16，实得 {len(risks)}"

    # ---------------- 构成要件 C（每个疑点下的要件表行数）
    constituents: list[dict] = []
    cur_rseq = 0
    in_tbl = False
    for i, l in enumerate(lines, 1):
        s = l.strip()
        m = RE_ITEM.match(s)
        if m:
            cur_rseq = next((r["seq"] for r in risks if r["line"] == i), 0)
            continue
        if s == RE_TABLE_START:
            in_tbl = True
            continue
        if s == "<<TABLE_END>>":
            in_tbl = False
            continue
        if in_tbl and cur_rseq and re.match(r"^第\d+条\s*\|", s):
            constituents.append({"no": rn.next("constituent", rseq=cur_rseq),
                                 "risk": f"R{cur_rseq}", "line": i,
                                 "text": s.split("|", 1)[1][:50] if "|" in s else s[:50]})

    # ---------------- 法规 L（去重，按首次出现排序）
    seen: dict[str, dict] = {}
    for i, l in enumerate(lines, 1):
        for m in RE_LAW_NAME.finditer(l):
            name = m.group(1)
            if not LAW_HINT.search(name):
                continue  # 表单名/刊物名，不是法规
            if name not in seen:
                seen[name] = {"no": rn.next("law"), "name": name, "first_line": i, "count": 1}
            else:
                seen[name]["count"] += 1
    laws = sorted(seen.values(), key=lambda x: x["first_line"])

    # ---------------- 资料 D（『N. 资料名』条目，去重）
    seen_d: dict[str, dict] = {}
    for i, l in enumerate(lines, 1):
        s = l.strip()
        m = RE_MATERIAL_ITEM.match(s)
        if not m or "|" in s:
            continue
        name = m.group(1).strip()
        if len(name) < 4 or "本项若按红线口径核对" in name:
            continue  # 套话项，不是资料
        if name not in seen_d:
            seen_d[name] = {"no": rn.next("material"), "name": name, "first_line": i, "count": 1}
        else:
            seen_d[name]["count"] += 1
    materials = sorted(seen_d.values(), key=lambda x: x["first_line"])

    # ---------------- 声明 S（套话 → 一次性声明）
    rules = json.load(open(os.path.join(ROOT, "config", "dedup_rules.json"), encoding="utf-8"))
    statements = []
    for t in rules["boilerplate"]["exact"]:
        statements.append({"no": rn.next("statement"), "text": t[:80]})
    for p in rules["boilerplate"]["prefix"]:
        statements.append({"no": rn.next("statement"), "text": p[:80] + "…"})

    # ---------------- 事实 F（阶段1 的稀有数值锚点，排除明细表行）
    rate = json.load(open(os.path.join(BASE, "阶段1", "重复率.json"), encoding="utf-8"))
    facts = []
    for x in rate["事实重复"]["TOP20"]:
        facts.append({"no": rn.next("fact"), "value": x["value"],
                      "occurrences": x["occurrences"], "lines": x["lines"]})

    # ---------------- 表 T（正式表，按出现顺序）
    tables = []
    for i, l in enumerate(lines, 1):
        if l.strip() == RE_TABLE_START:
            tables.append({"no": rn.next("table"), "line": i + 1})

    assign = {
        "sample": "WB-TRISK-SAMPLE-001",
        "generated_at": NOW,
        "generated_by": "engine/numbering.py::ReportNumbering（唯一权威，本脚本不拼接编号）",
        "continuity_note": "R 从 1 连续到 16，无跳号无重号，max(seq)=总数（修正原文『第十八项』＞总数 16 的缺陷）",
        "counts": {k: len(v) for k, v in
                   [("R", risks), ("C", constituents), ("L", laws), ("D", materials),
                    ("S", statements), ("F", facts), ("T", tables)]},
        "risk": risks, "constituent_sample": constituents[:20], "constituent_total": len(constituents),
        "law": laws, "material_sample": materials[:30], "material_total": len(materials),
        "statement": statements, "fact": facts,
        "table_sample": tables[:10], "table_total": len(tables),
    }
    json.dump(assign, open(os.path.join(OUT, "编号分配.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # ---------------- 唯一事实源映射表（指令要求字段：编号/类型/内容摘要/唯一完整位置/其他引用位置/原始出处/是否必要重复）
    ssot_rows = []
    missing = []
    all_txt = {}
    for root_, _dirs, files_ in os.walk(ROOT):
        if any(x in root_ for x in ("__pycache__", ".git", "node_modules", "baseline", "docs")):
            continue
        for fn in files_:
            if fn.endswith((".py", ".json")):
                fp = os.path.join(root_, fn)
                try:
                    all_txt[fp] = open(fp, encoding="utf-8", errors="replace").read()
                except Exception:
                    pass
    for idx, (concept, authority, note) in enumerate(SSOT, 1):
        ok, rel = check_path(authority)
        leaf = rel.split("/")[-1].split(".")[0]
        # 其他引用位置：引用该权威文件名（或模块名）的其它文件
        refs = []
        for fp, txt in all_txt.items():
            if leaf and leaf in txt and os.path.basename(fp) != rel.split("/")[-1]:
                refs.append(os.path.relpath(fp, ROOT).replace(os.sep, "/"))
        refs = sorted(set(refs))[:8]
        kind = ("engine 模块" if rel.startswith("engine/") else
                "config 数据表" if rel.startswith("config/") else
                "static 数据表" if rel.startswith("static/") else "其他")
        ssot_rows.append({
            "编号": f"SSOT-{idx:02d}",
            "类型": kind,
            "内容摘要": concept,
            "唯一完整位置": rel,
            "其他引用位置": refs,
            "原始出处": refs[0] if refs else rel,
            "是否必要重复": "是（唯一权威本身只此一处；下游一律薄转发）",
            "authority": authority, "note": note,
            "landed": ok, "status": "已落地" if ok else "未落地",
        })
        if not ok:
            missing.append(authority)
    ssot = {"generated_at": NOW, "method": "模块存在性校验（os.path.exists），不假称已实现",
            "total": len(ssot_rows), "landed": sum(1 for r in ssot_rows if r["landed"]),
            "rows": ssot_rows}
    json.dump(ssot, open(os.path.join(OUT, "唯一事实源映射表.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # ---------------- Markdown
    r_tbl = "\n".join(f"| {r['no']} | {r['old']} | {r['line']} | {r['title'][:46]} |" for r in risks)
    c_tbl = "\n".join(f"| {c['no']} | {c['line']} | {c['text'][:52]} |" for c in constituents[:14])
    l_tbl = "\n".join(f"| {x['no']} | {x['name'][:52]} | {x['count']} | {x['first_line']} |" for x in laws)
    d_tbl = "\n".join(f"| {x['no']} | {x['name'][:48]} | {x['count']} |" for x in materials[:20])
    s_tbl = "\n".join(f"| {x['no']} | {x['text'][:60]} |" for x in statements)
    f_tbl = "\n".join(f"| {x['no']} | {x['value']} | {x['occurrences']} | {', '.join(str(i) for i in x['lines'][:6])} |"
                      for x in facts[:14])
    ssot_tbl = "\n".join(
        f"| {r['编号']} | {r['类型']} | {r['内容摘要']} | `{r['唯一完整位置']}` | "
        f"{len(r['其他引用位置'])} 处 | {r['是否必要重复']} | {r['status']} |" for r in ssot_rows)
    cnt = assign["counts"]
    md = f"""# 阶段3：编号体系与《唯一事实源映射表》

**样本**：WB-TRISK-SAMPLE-001（V1.0 冻结版）
**生成时间**：{NOW}
**编号唯一权威**：`engine/numbering.py`（`NumberingService` 底稿层 + `ReportNumbering` 报告层）
**配置**：`config/numbering.json` 的 `report_layer` 段（新增类型只加一行）
**执行**：`scripts/_phase3_numbering.py`（现算）

---

## 一、编号体系（七类短号）

| 类别 | 格式 | 引用格式 | 本样本分配数 |
|---|---|---|---|
| R 风险事项 | R1 | 见疑点R1 | {cnt['R']} |
| C 构成要件 | R1-C2 | 见要件R1-C2 | {cnt['C']} |
| F 事实 | F-001 | 见事实F-001 | {cnt['F']} |
| D 资料 | D-001 | 见资料D-001 | {cnt['D']} |
| S 声明 | S-01 | 见声明S-01 | {cnt['S']} |
| L 法规 | L-01 | 见法规L-01 | {cnt['L']} |
| T 表 | T-01 | 见表T-01 | {cnt['T']} |

> **连续性修正**：原文「办理顺序」编号为 一/二/三/四/五/六/七/**九**/十一/十三/十四/十五/**十八**，
> 跳号 8/10/12/16/17 且末值 18 ＞ 总项数 16。本方案统一为 **R1~R16，连续、无跳号、max(seq)=总数**。

## 二、R1~R16 分配表（对应原「疑点1~疑点16」）

| 新编号 | 原编号 | 行号 | 风险事项 |
|---|---|---|---|
{r_tbl}

## 三、构成要件 C（节选 14 条，共 {cnt['C']} 条）

| 编号 | 行号 | 要件（截断） |
|---|---|---|
{c_tbl}

## 四、法规 L（共 {cnt['L']} 条，已过滤非法规名）

| 编号 | 法规名称 | 引用次数 | 首次行 |
|---|---|---|---|
{l_tbl}

> 过滤说明：`《红字发票信息确认单》`（表单名）、`《中国国家地理》`（刊物名）不含法规特征词，已排除，不占用 L 号。

## 五、资料 D（节选 20 类，共 {cnt['D']} 类）

| 编号 | 资料名 | 出现次数 |
|---|---|---|
{d_tbl}

## 六、声明 S（套话抽为一次性声明，共 {cnt['S']} 条）

| 编号 | 声明内容 |
|---|---|
{s_tbl}

## 七、事实 F（节选 14 条）

| 编号 | 数值锚点 | 原出现段数 | 原行号 |
|---|---|---|---|
{f_tbl}

> 去重后：每个事实只在**事实段**完整陈述一次（≤1 次），其余位置一律用「见事实F-0xx」引用。

## 八、《唯一事实源映射表》

本表回答「这个概念由谁说了算」。**已落地 {ssot['landed']}/{ssot['total']}**，未落地的如实标注。

| 编号 | 类型 | 内容摘要 | 唯一完整位置 | 其他引用位置 | 是否必要重复 | 状态 |
|---|---|---|---|---|---|---|
{ssot_tbl}

{f"> **未落地的权威点**：{('、'.join(missing))}——需在阶段9 系统固化时补齐，不得用临时实现顶替。" if missing else ""}

## 九、引用替换规则（阶段5 执行依据）

| 原写法 | 替换为 |
|---|---|
| 整段复述另一疑点的内容 | 见疑点Rn |
| 整段复述某条要件 | 见要件Rn-Cm |
| 再次陈述同一金额/人数/比例 | 见事实F-0xx |
| 再次列出同一份资料 | 见资料D-0xx |
| 再次写出同一句通用声明 | 见声明S-0x |
| 再次写出同一法条全文 | 见法规L-0x |
| 再次铺陈同一张表 | 见表T-0x |

## 十、复跑命令

```
./.venv/Scripts/python.exe scripts/_phase3_numbering.py
```
"""
    b = md.encode("utf-8")
    with open(os.path.join(DOCS, "04_阶段3_编号体系与唯一事实源映射表.md"), "wb") as f:
        f.write(b)
    print(f"[OK] 编号分配 R{cnt['R']} C{cnt['C']} F{cnt['F']} D{cnt['D']} S{cnt['S']} L{cnt['L']} T{cnt['T']}")
    print(f"[OK] 唯一事实源 {ssot['landed']}/{ssot['total']} 已落地，未落地：{missing}")
    print(f"[OK] 04_阶段3_编号体系与唯一事实源映射表.md  {len(b):,} 字节")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
