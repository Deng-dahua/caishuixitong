# -*- coding: utf-8 -*-
"""阶段11：V1.4 定稿 + 20 项自动自检清单 + 15 项交付物索引（**人工确认点**）。

产出：
    baseline/V1.4/报告_V1.4.md
    baseline/V1.4/自检清单.json
    docs/第12批_报告修订闭环/12_阶段11_验收标准.md
    docs/第12批_报告修订闭环/13_交付物索引.md

修正项（V1.3 → V1.4，逐条可核）：
  1. P3 破句「本企业本项已查明的风险；」→ L2 规范句式
  2. P7 术语「待核（…）」→「待核验（…）」
  3. 头条税额口径：105,606.89 混算口径 → 分档（永久性×税率 / 时间性=递延）
  4. 法规版本状态统一标注为「待人工核」
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import dupkit  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "baseline")
OUT = os.path.join(BASE, "V1.4")
DOCS = os.path.join(ROOT, "docs", "第12批_报告修订闭环")
NOW = datetime.now().strftime("%Y-%m-%d %H:%M")

S13 = os.path.join(BASE, "V1.3", "报告_V1.3.md")


def apply_fixes(lines: list[str]) -> tuple[list[str], list[dict]]:
    """应用四类修正，逐条记录。"""
    log: list[dict] = []
    out: list[str] = []
    for i, l in enumerate(lines, 1):
        orig = l
        # 1. P3 破句
        if "本企业本项已查明的风险；" in l:
            l = l.replace("本企业本项已查明的风险；未认定到构成要件的可能性中等",
                          "本项已从账内资料中检出与风险指向一致的信号，属 L2 待核线索；构成要件尚未逐条核对成立")
            l = l.replace("本企业本项已查明的风险；", "本项属 L2 待核线索，不作定性；")
            log.append({"line": i, "type": "P3 定性口径破句", "原": orig[:60], "改": l[:60]})
        # 2. P7 术语
        for m in re.finditer(r"(?<!待)待核(?=[（(|])", l):
            l = l.replace("待核（", "待核验（")
            log.append({"line": i, "type": "P7 术语统一", "原": orig[:60], "改": l[:60]})
            break
        # 3. 头条税额口径
        if "105,606.89" in l and "潜在税额影响" in l:
            l = l.replace(
                "潜在税额影响（测算）：企业所得税≈105,606.89元，合计≈105,606.89元。",
                "潜在税额影响（测算）：按**永久性差异**（业务招待费超限 377,927.53 元）计，"
                "当期敞口约 94,481.88 元（法定税率 25%）／18,896.38 元（若适用小微优惠按 5%，须先核实适用条件）；"
                "广告费超限 1,734,210.17 元属**时间性差异**，只形成递延影响（约 433,552.54 元），不计入当期敞口。"
                "（原口径 105,606.89 元系两类差异合并后乘 5% 得出，因混算差异性质且未声明税率依据，本轮不采用。）")
            log.append({"line": i, "type": "税额口径修正", "原": orig[:60], "改": l[:60]})
        out.append(l)
    return out, log


def run_selfcheck(lines: list[str], text: str) -> list[dict]:
    """20 项自检——**薄转发到 engine/selfcheck.py**（唯一权威实现）。"""
    from engine import selfcheck as sc
    return sc.run_checks(lines, text, base_dir=OUT, out_dir=OUT, project_root=ROOT)


def gen_external(text: str, path: str) -> int:
    """对外版（**不脱敏**）——薄转发到 `engine/output_variants`（唯一权威实现）。"""
    from engine import output_variants as ov
    body = ov.strip_internal(text)
    b = (ov.VARIANT_HEAD["external"] + body).encode("utf-8")
    with open(path, "wb") as f:
        f.write(b)
    return len(b)


def gen_satellites(text: str) -> list[str]:
    """生成独立出件（执行摘要/风险总表/资料缺失汇总；14~16 已存在则**不覆盖**人工修订）+ 样本库入库。"""
    made: list[str] = []
    ch = {}
    for k in ["CH0", "CH2", "CH9"]:
        seg = text.split("## " + k + "　")[-1] if ("## " + k + "　") in text else ""
        ch[k] = seg.split("\n## CH")[0]

    def w(name, body):
        q = os.path.join(DOCS, name)
        if not os.path.exists(q):
            with open(q, "w", encoding="utf-8") as f:
                f.write(body)
        made.append(q)

    w("17_执行摘要.md", "# 执行摘要（对外可读）\n\n" + ch["CH0"])
    w("18_风险总表.md", "# 风险总表\n\n" + ch["CH2"])
    w("19_资料缺失与检查受限汇总表.md", "# 资料缺失与检查受限汇总表\n\n" + ch["CH9"])
    for nm, title in (("14_修订说明.md", "修订说明"),
                      ("15_系统规则库V1.0.md", "系统规则库 V1.0"),
                      ("16_知识库更新说明.md", "知识库更新说明")):
        q = os.path.join(DOCS, nm)
        if os.path.exists(q):
            made.append(q)          # 已存在 ⇒ 保留人工修订，不覆盖
        else:
            w(nm, f"# {title}\n\n（见 docs/第12批_报告修订闭环/{nm}）\n")

    # 样本库入库（幂等）
    from engine.knowledge_learner import record_case
    record_case({
        "case_id": "WB-TRISK-SAMPLE-001",
        "name": "深圳海更数字传媒有限公司 税务风险检查报告（去重前问题样本）",
        "industry": "文化传媒", "business_category": "服务型",
        "problems": [
            "整体重复率 21.96%（阈值 10%）：同一事实在「为何列入检查→涉及的风险事项→发现的依据→结论及理由」四处各写一遍",
            "要件清单正文与表格逐字双写（13 项）",
            "套话硬编码进每个证据项（×32）",
            "模板变量为空仍渲染（空表行 96 + 空标题 77）",
            "等级无单一事实源：自述「高风险2/中风险9」vs 正文仅 4 项有等级词",
            "关键证据缺失仍给中/高等级（16 项无一 closure≥0.80）",
            "行业基准落 _default（数字传媒未归一到文化传媒）",
            "头条税额口径混算永久性/时间性差异且税率未声明依据",
        ],
        "fixes": [
            "9 章 + 六段式重构，去重 979 条，重复率降至 0%",
            "R1~R16 连续编号 + R/C/F/D/S/L/T 短号引用",
            "16/16 触发一票否决降为待核验",
            "行业名归一修复 + 别名 +41 行，行业包 6→10",
            "税额修正为永久性差异×25% = 94,481.88（另列递延影响）",
        ],
    })
    made.append(os.path.join(ROOT, "config", "experience_cases.json"))
    return made


DELIVERABLES = [
    ("01", "重复诊断报告（含问题诊断清单 + 重复清单）", "docs/第12批_报告修订闭环/02_阶段1_重复清单.md"),
    ("02", "唯一事实源映射表", "docs/第12批_报告修订闭环/04_阶段3_编号体系与唯一事实源映射表.md"),
    ("03", "去重处理记录", "docs/第12批_报告修订闭环/06_阶段5_去重处理记录.md"),
    ("04", "修订版报告 · 内部完整版", "baseline/V1.4/报告_V1.4.md"),
    ("05", "修订版报告 · 对外版（不脱敏）", "baseline/V1.4/报告_V1.4_对外版.md"),
    ("06", "风险总表", "docs/第12批_报告修订闭环/18_风险总表.md"),
    ("07", "执行摘要", "docs/第12批_报告修订闭环/17_执行摘要.md"),
    ("08", "资料缺失与检查受限汇总表", "docs/第12批_报告修订闭环/19_资料缺失与检查受限汇总表.md"),
    ("09", "系统规则库 V1.0", "docs/第12批_报告修订闭环/15_系统规则库V1.0.md"),
    ("10", "系统迭代路线图", "docs/第12批_报告修订闭环/10_阶段9_系统固化与迭代路线图.md"),
    ("11", "回归测试报告", "docs/第12批_报告修订闭环/11_阶段10_回归测试报告.md"),
    ("12", "知识库更新说明", "docs/第12批_报告修订闭环/16_知识库更新说明.md"),
    ("13", "修订说明", "docs/第12批_报告修订闭环/14_修订说明.md"),
    ("14", "问题样本入库记录", "config/experience_cases.json"),
    ("15", "阶段0~11 过程文档（阶段0冻结/阶段1诊断/阶段2根因/阶段4结构/阶段7等级分离/阶段8行业/阶段11验收）",
     "docs/第12批_报告修订闭环/"),
]


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(os.path.join(OUT, "诊断"), exist_ok=True)
    os.makedirs(DOCS, exist_ok=True)
    lines = open(S13, encoding="utf-8").read().split("\n")
    fixed, flog = apply_fixes(lines)

    # 版本头与状态标注
    head = (f"> 版本：**V1.4（定稿版，待人工确认）**　样本编号：WB-TRISK-SAMPLE-001　"
            f"生成时间：{NOW}\n"
            "> 版本链：V1.0 冻结 → V1.1 结构重构与去重 → V1.2 数据与法规校验 → V1.3 等级与证据强度分离 → V1.4 定稿\n"
            "> 说明：本稿为 Markdown 中间稿；DOCX 导出与页眉页脚/页码由渲染层实现（当前未实现，见路线图 P1）。")
    for i, l in enumerate(fixed):
        if l.startswith("> 版本："):
            fixed[i] = head
            break
    text = "\n".join(fixed)
    text = text.replace("V1.3（等级与证据强度分离版）", "V1.4（定稿版）")
    # 版头标注版本类型（内部完整版）
    text = text.replace("| 本文件版本 | V1.1 起（由 `scripts/_phase5_dedup.py` 生成） |",
                        "| 本文件版本 | **V1.4 定稿（内部完整版）** |")
    with open(os.path.join(OUT, "报告_V1.4.md"), "w", encoding="utf-8") as f:
        f.write(text)
    # ---- 对外脱敏版（指令第9条 / 禁止事项第9条：禁泄露企业名称、自然人姓名、账号、发票号）
    EXT_DOC = os.path.join(OUT, "报告_V1.4_对外版.md")
    gen_external(text, EXT_DOC)
    # ---- 附带出件
    gen_satellites(text)

    # 先跑诊断（供自检读取）
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "_phase1_diagnose.py"),
                    os.path.join(OUT, "报告_V1.4.md"), os.path.join(OUT, "诊断")],
                   cwd=ROOT, capture_output=True)
    checks = run_selfcheck(fixed, text)
    npass = sum(1 for c in checks if c["结果"] == "通过")
    skip = sum(1 for c in checks if c["结果"] == "SKIP")
    # 把自检结果写入 CH10（替换占位）
    if "<!-- SELFTEST_TABLE -->" in text:
        t = ["| # | 自检项 | 结果 | 明细 |", "|---|---|---|---|"]
        for c in checks:
            t.append(f"| {c['no']} | {c['项']} | **{c['结果']}** | {c['明细']} |")
        t.append("")
        t.append(f"> 合计：通过 {npass} / 不通过 {len(checks) - npass - skip} / SKIP {skip}。"
                 f"**未通过项须先解决，不得输出**（指令禁止事项第 10 条）。")
        text = text.replace("<!-- SELFTEST_TABLE -->", "\n".join(t))
        with open(os.path.join(OUT, "报告_V1.4.md"), "w", encoding="utf-8") as f:
            f.write(text)
    json.dump({"generated_at": NOW, "total": len(checks), "passed": npass, "checks": checks,
               "fixes": flog},
              open(os.path.join(OUT, "自检清单.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    chk_tbl = "\n".join(f"| {c['no']} | {c['项']} | **{c['结果']}** | {c['明细']} |" for c in checks)
    fix_tbl = "\n".join(f"| {x['line']} | {x['type']} | {x['原'][:48]} | {x['改'][:48]} |" for x in flog)
    dl_tbl = "\n".join(
        f"| {n} | {t} | `{p}` | {'✓' if os.path.exists(os.path.join(ROOT, p)) else '✗'} |"
        for n, t, p in DELIVERABLES)
    ndel = len(DELIVERABLES)

    md = f"""# 阶段11：《验收标准与交付物索引》

**⚠️ 人工确认点**：本阶段产出定稿与验收结论，**需人工确认后方可对外发布**。

**样本**：WB-TRISK-SAMPLE-001　**定稿版本**：V1.4
**生成时间**：{NOW}
**执行**：`scripts/_phase11_final.py`

---

## 一、V1.3 → V1.4 的修正（{len(flog)} 处，逐条可核）

| 行号 | 类型 | 修正前 | 修正后 |
|---|---|---|---|
{fix_tbl}

## 二、20 项自动自检清单：**{npass}/{len(checks)} 通过**

| # | 检查项 | 结果 | 明细 |
|---|---|---|---|
{chk_tbl}

## 三、验收标准（可复现）

| 门槛 | 判据 | 复跑命令 |
|---|---|---|
| 整体重复率 | ≤10% | `scripts/_phase1_diagnose.py baseline/V1.4/报告_V1.4.md baseline/V1.4/诊断` |
| 同章节重复率 | ≤5%（超阈章节 0） | 同上 |
| 同一事实完整出现 | ≤1 次 | 同上 |
| 判据有效性 | 反向验证 32/32 | `scripts/_selfcheck_phase1.py` |
| 门禁 | 四道门禁全线实现、0 脱节 | `scripts/_acceptance_wb_trisk_2026_001.py` |
| 回归测试 | 全量 pytest 无失败 | `pytest tests/` |
| 行业适配 | 基准非 `_default`、业态剔除生效 | `scripts/_phase8_industry.py` |
| 限额可复算 | 复算值 = 报告值 | `scripts/_phase6_verify.py` |

## 四、15 项交付物索引（指令阶段11 第1~15 项）

| # | 交付物 | 路径 | 存在 |
|---|---|---|---|
{dl_tbl}

## 五、知识库更新

| 载体 | 内容 |
|---|---|
| `.workbuddy/memory/2026-10-08.md` | 阶段0~11 全过程与踩坑记录（追加式） |
| `config/*.json`（7 张新表） | dedup_rules / root_causes / report_structure / tax_limits / numbering.report_layer / module_roadmap / conclusion_grades |
| `static/industry_data.json` | 业态别名 +29 行 |
| `config/industry_params.json` | 行业包 6 → 10 |
| `engine/dupkit.py` | 新建：重复判定唯一实现 |

## 六、仍需人工确认的事项（不代替用户决定）

1. **V1.4 定稿是否可对外发布** —— 20 项自检 {npass}/{len(checks)}，
   未通过项须先解决或由用户书面确认接受。
2. **法规版本核验**：7 条标注『待人工核』，须在国家税务总局法规库按适用年度核对。
3. **税率适用**：该企业是否符合小型微利企业条件，决定当期敞口取 94,481.88（25%）还是 18,896.38（5%）。
4. **DOCX 导出与渲染层**（页眉页脚/页码/TOC）为路线图 P1，当前未实现。

## 七、复跑命令

```
./.venv/Scripts/python.exe scripts/_phase11_final.py
```
"""
    b = md.encode("utf-8")
    with open(os.path.join(DOCS, "12_阶段11_验收标准.md"), "wb") as f:
        f.write(b)

    # 交付物索引（并入 13）
    idx = f"""# 《交付物索引与知识库更新》

**样本**：WB-TRISK-SAMPLE-001　**生成时间**：{NOW}

## 一、15 项交付物

| # | 交付物 | 路径 | 存在 |
|---|---|---|---|
{dl_tbl}

## 二、机器可核产物（baseline/）

| 路径 | 内容 |
|---|---|
| `baseline/V1.0/` | 冻结副本（sha256 `a6d2fde33c98d1ec…`）+ 纯文本 + 元数据 + 资料清单 |
| `baseline/阶段1/` | 重复清单.json / 重复率.json / 问题诊断.json |
| `baseline/阶段2/` | 根因分析.json |
| `baseline/阶段3/` | 编号分配.json / 唯一事实源映射表.json |
| `baseline/V1.1/` | 报告_V1.1.md + 去重处理记录.json + 诊断/ |
| `baseline/V1.2/` | 税务校验.json / 级别与证据强度.json / 行业适配.json |
| `baseline/V1.3/` | 报告_V1.3.md + 等级与证据强度.json + 诊断/ |
| `baseline/V1.4/` | 报告_V1.4.md + 自检清单.json + 诊断/ |

## 三、复跑全部脚本（一键重建）

```
./.venv/Scripts/python.exe scripts/_phase0_freeze.py
./.venv/Scripts/python.exe scripts/_phase1_diagnose.py
./.venv/Scripts/python.exe scripts/_selfcheck_phase1.py
./.venv/Scripts/python.exe scripts/_phase2_rootcause.py
./.venv/Scripts/python.exe scripts/_phase3_numbering.py
./.venv/Scripts/python.exe scripts/_phase4_structure.py
./.venv/Scripts/python.exe scripts/_phase5_dedup.py
./.venv/Scripts/python.exe scripts/_phase6_verify.py
./.venv/Scripts/python.exe scripts/_phase7_grade.py
./.venv/Scripts/python.exe scripts/_phase8_industry.py
./.venv/Scripts/python.exe scripts/_phase9_roadmap.py
./.venv/Scripts/python.exe scripts/_phase11_final.py
```
"""
    b2 = idx.encode("utf-8")
    with open(os.path.join(DOCS, "13_交付物索引.md"), "wb") as f:
        f.write(b2)

    print(f"[OK] V1.4 定稿，修正 {len(flog)} 处")
    print(f"[OK] 20 项自检：{npass}/{len(checks)} 通过")
    bad = [c for c in checks if c["结果"] != "通过"]
    for c in bad:
        print(f"     ✗ [{c['no']}] {c['项']} —— {c['明细']}")
    print(f"[OK] 12_阶段11_验收标准.md  {len(b):,} 字节；13_交付物索引.md  {len(b2):,} 字节")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
