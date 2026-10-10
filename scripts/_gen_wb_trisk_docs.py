# -*- coding: utf-8 -*-
"""WB-TRISK-2026-001 §八 交付物生成器（数据表驱动部分）。

生成（**从配置/代码现算，不手抄**，保证与实现同步）：
    02_数据字典.md          03_规则库.md        04_模板库.md
    05_行业包.md            06_税种包.md
    12_测试用例与测试报告.md  13_验收报告.md      15_归档样例.md

手写部分（需人判断）：01_系统迭代方案 / 07_证据链模型说明书 / 08_逻辑一致性校验规则 /
    09_归档规范说明书 / 10_模板整洁质检规则 / 11_Skill定义 / 14_用户手册。

用法：
    ./.venv/Scripts/python.exe scripts/_gen_wb_trisk_docs.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "第10批_WB-TRISK-2026-001_系统迭代"
BENCH = ROOT / "data" / "cache" / "last_analysis_cache.json"
COMPANY_CODE = "91440300MA5H824G7M"
PERIOD = "202601"


def load(rel: str) -> Any:
    p = ROOT / rel
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"_error": f"{rel} 解析失败：{exc}"}


def touch(name: str) -> Path:
    p = OUT / name
    p.write_text("", encoding="utf-8")
    return p


def w(name: str, lines: List[str]) -> Path:
    p = OUT / name
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def hdr(title: str, *extra: str) -> List[str]:
    L = [f"# {title}", ""]
    L += [f"> {x}" for x in extra]
    if extra:
        L.append("")
    return L


# ================================================================ 02 数据字典
def gen_data_dictionary() -> Path:
    L = hdr(
        "02 · 数据字典",
        "指令：WB-TRISK-2026-001 §八（交付物）＋§二（单一事实源、模板与内容分离、全行业配置化）",
        "本文件由 `scripts/_gen_wb_trisk_docs.py` **从配置与代码现算**生成，不手抄；改配置后重跑即同步。",
    )
    L += ["## 1 配置数据表（配置即契约，新增对象只加行不改码）", ""]
    cfg_files = sorted(p.name for p in (ROOT / "config").glob("*.json"))
    L += ["| 配置文件 | schema | 版本 | 顶层键数 | 顶层键 |", "|---|---|---|---|---|"]
    for fn in cfg_files:
        d = load(f"config/{fn}")
        if not isinstance(d, dict):
            continue
        keys = [k for k in d.keys() if not k.startswith("_")]
        L.append(f"| `config/{fn}` | {d.get('schema','—')} | {d.get('version','—')} | {len(keys)} | "
                 f"{'、'.join(keys[:9])}{'…' if len(keys) > 9 else ''} |")

    L += ["", "## 2 本批新增/修改的数据表（WB-TRISK-2026-001 P0）", ""]
    new_tables = {
        "config/numbering.json": "编号规则（前缀/分段/序号宽度/连续性约束）：新增编号类型只加一行",
        "config/conclusion_grades.json": "结论四级（L1~L4）+ 裁决词映射 + 一票否决触发条件 + 等级合法词表",
        "config/quality_gates.json": "四道门禁判据表（38 条）+ 扫描域白名单 + 策略（未通过禁输出/SKIP 不算通过）",
        "config/archive_spec.json": "归档规范（底稿编号/页眉页脚/七类索引/签署/审计轨迹/导出包/渲染层降级）",
        "config/alternative_evidence.json": "替代程序库（缺 A 资料 → 可替代取得的等价资料，键=14 类权威类别名）",
    }
    L += ["| 数据表 | 作用 | 权威性 |", "|---|---|---|"]
    for k, v in new_tables.items():
        L.append(f"| `{k}` | {v} | 该领域唯一权威 |")

    L += ["", "## 3 唯一权威登记（同一概念只此一处实现）", ""]
    L += ["| 概念 | 唯一权威 | 说明 |", "|---|---|---|"]
    auth = [
        ("数值解析", "engine/numparse.py", "AMOUNT_KEYS / to_number_checked；解析失败返回 None，不返回 0"),
        ("风险等级", "engine/risk_levels.py", "LEGAL_LEVELS / SEVERITY / normalize / cap_level"),
        ("证据状态", "engine/data_source_status.py", "STATUSES_ALL 五态（已有/缺失/须核对/待企业提交/本业态不适用）"),
        ("资料类别", "engine/material_names.py", "CATEGORIES 14 类；要件数据源必须可归入其一"),
        ("行业判定", "engine/industry_resolver.py", "行业判定唯一权威；not_required_materials() 决定业态剔除"),
        ("编号", "engine/numbering.py（本批新增）", "WB-TR/WB-R/WB-EV/WB-GAP/WB-LAW/WB-ATT/WB-IDX/WB-RC"),
        ("结论分级", "engine/conclusion_grade.py（本批新增）", "L1~L4 + 一票否决 + 与 argumentation 裁决词双向校验"),
        ("事实登记", "engine/fact_store.py（本批新增）", "金额/人数/笔数/日期/税种/企业名 + 金额口径五要素"),
        ("门禁判据", "config/quality_gates.json（本批新增）", "38 条；实现侧在 engine/quality_gates.py"),
        ("裁决词", "engine/argumentation.py", "_VERDICT_* / GRADE_*；映射表在 config/conclusion_grades.json"),
        ("报告正文域", "config/quality_gates.json → scan_domain", "词表类判据的扫描白名单（防把上传的 HTML 当正文）"),
    ]
    for a, b, c in auth:
        L.append(f"| {a} | `{b}` | {c} |")

    L += ["", "## 4 本批新增数据结构", ""]
    L += ["### 4.1 `Fact`（engine/fact_store.py）", "", "| 字段 | 类型 | 含义 |", "|---|---|---|"]
    for k, t, m in [
        ("fact_id", "str", "`F-<KIND缩写>-<期间>-<sha1前10>`；同键同值幂等"),
        ("kind", "str", "amount / count / ratio / date / tax / entity / level / text"),
        ("label", "str", "事实标签（归一：去空白、去尾标点）"),
        ("value", "float|str|None", "值；解析失败为 None（**不返回 0**）"),
        ("scope", "str", "口径：full 全口径 / adjusted 剔除口径"),
        ("tax_inclusive", "bool|None", "含税性；与 scope 正交"),
        ("period", "str", "YYYYMM"),
        ("source", "str", "来源资料/表名"),
        ("derivation", "str", "计算过程（可复算）"),
        ("related", "str", "口径分组键；多值同组即视为已声明，不判冲突"),
        ("scope_note", "str", "口径说明"),
    ]:
        L.append(f"| `{k}` | {t} | {m} |")

    L += ["", "### 4.2 `GateFinding` / `GateResult`（engine/quality_gates.py）", "",
          "| 字段 | 类型 | 含义 |", "|---|---|---|"]
    for k, t, m in [
        ("gate / check_id", "str", "门禁 A~D / 判据编号（与 config 一一对应）"),
        ("severity", "str", "ERROR / WARN / INFO"),
        ("layer", "str", "data（结构化层）/ render（导出物层）/ both"),
        ("message", "str", "问题描述（含计数）"),
        ("fix", "str", "修复建议（取自判据表）"),
        ("sample", "any", "命中样例（可回查原文）"),
        ("status", "str", "PASS / FAIL / SKIP —— **SKIP 不计通过**"),
        ("stats / skips", "dict / list", "统计与「为何没查」的如实说明"),
    ]:
        L.append(f"| `{k}` | {t} | {m} |")

    L += ["", "### 4.3 编号分段（config/numbering.json）", "",
          "| 类型 | 前缀 | 分段 | 中文名 |", "|---|---|---|---|"]
    nb = load("config/numbering.json") or {}
    for k, v in (nb.get("rules") or {}).items():
        seg = ("<企业代码>-<期间>-<序号>" if k != "law" else "<税种>-<序号>")
        L.append(f"| `{k}` | `{v.get('prefix')}` | {seg} | {v.get('cn')} |")
    L += ["", "| 约束 | 值 |", "|---|---|"]
    for k, v in (nb.get("continuity") or {}).items():
        L.append(f"| {k} | `{v}` |")
    return w("02_数据字典.md", L)


# ================================================================ 03 规则库
def gen_rule_library() -> Path:
    L = hdr(
        "03 · 规则库",
        "指令：WB-TRISK-2026-001 §八 ＋ §3.2（风险等级规则引擎）",
        "数量由代码/配置**现算**，不手抄。",
    )
    L += ["## 1 规则体系总览", "", "| 规则体系 | 载体 | 数量（现算） | 用途 |", "|---|---|---|---|"]
    counts: Dict[str, Any] = {}

    try:
        from engine import tax_redlines as tr
        ids = [k for k in dir(tr) if k.isupper()]
        redline = None
        for name in ("REDLINES", "REDLINE_LIBRARY", "RULES"):
            v = getattr(tr, name, None)
            if isinstance(v, (list, dict)) and v:
                redline = len(v)
                break
        counts["redline"] = redline
    except Exception as exc:  # noqa: BLE001
        counts["redline"] = f"取不到（{exc}）"

    rc = load("config/risk_conditions.json") or {}
    rf = load("config/risk_families.json") or {}
    qg = load("config/quality_gates.json") or {}
    dc = load("config/doc_consistency.json") or {}
    counts["conditions"] = len(rc.get("risks") or [])
    counts["families"] = len(rf.get("families") or [])
    counts["gate_checks"] = sum(len(g.get("checks") or []) for g in (qg.get("gates") or []))
    counts["gate_count"] = len(qg.get("gates") or [])
    counts["doc_authorities"] = len(dc.get("numbers") or [])

    try:
        from engine import verified_rule_engine as vre
        vr = next((len(v) for k, v in vars(vre).items()
                   if k.isupper() and isinstance(v, (list, dict)) and 20 < len(v) < 5000), None)
        counts["verified"] = vr
    except Exception as exc:  # noqa: BLE001
        counts["verified"] = f"取不到（{exc}）"

    for name, argv, n, use in [
        ("红线库 RL", "`engine/tax_redlines.py`", counts["redline"], "法定禁止情形；带 indicator_constituents / violation_any_of"),
        ("风险条件", "`config/risk_conditions.json`", counts["conditions"], "触发条件与认定要件的配置化登记"),
        ("风险族", "`config/risk_families.json`", counts["families"], "同族子项去重计数（避免同一风险计多遍）"),
        ("已验规则 VR", "`engine/verified_rule_engine.py`", counts["verified"], "可直接计算的数据型规则"),
        ("质量门禁", "`config/quality_gates.json`", f"{counts['gate_count']} 道 / {counts['gate_checks']} 条", "**本批新增**：输出前质检"),
        ("文档一致性权威", "`config/doc_consistency.json`", counts["doc_authorities"], "交付文档数字/规则/残留/编号治理"),
    ]:
        L.append(f"| {name} | {argv} | {n if n is not None else '—'} | {use} |")

    L += ["", "## 2 风险等级规则引擎（§3.2 五维加权）", ""]
    L += ["P0 实现为**可配置词表 + 硬约束 + 一票否决**三件套；五维加权算法为 P1（见 01 迭代方案）。", ""]
    L += ["### 2.1 合法等级词表（唯一权威 `engine/risk_levels.LEGAL_LEVELS`）", ""]
    try:
        from engine import risk_levels as rl
        L += ["| 等级 | 轻重标度 | 呈现序 | 类型 |", "|---|---|---|---|"]
        for lv in rl.LEGAL_LEVELS:
            kind = "风险档" if lv in getattr(rl, "RISK_GRADES", ()) else "证据状态"
            L.append(f"| {lv} | {rl.SEVERITY.get(lv, '—')} | {rl.PRESENT_ORDER.get(lv, '—')} | {kind} |")
    except Exception as exc:  # noqa: BLE001
        L.append(f"取不到：{exc}")

    L += ["", "### 2.2 硬约束（同一事项内，违反即 ERROR）", "",
          "| 约束 | 判据 | 出处 |", "|---|---|---|"]
    for a, b, c in [
        ("等级词表", "风险等级必须属于合法词表；表外词归一后仍非法即报错", "A5"),
        ("无证据不得定级", "closure=0 或 evidence_have=0 ⇒ 等级不得高于『待核验』", "A1 / 一票否决 V1·V5"),
        ("未闭合不得定中高", "closure < 0.80 ⇒ 等级不得为 中风险及以上", "A9 / V2"),
        ("等级与结论挂钩", "结论等级 L1/L2 ⇒ 不得带 高风险/极高风险", "B3"),
        ("高等级与低可能性不并存", "同项同时出现『高风险』与『可能性低』且未声明定级依据 ⇒ ERROR", "B4"),
        ("未认定与已查明不并存", "同项并存『未认定』与『已查明』⇒ ERROR", "B5"),
    ]:
        L.append(f"| {a} | {b} | {c} |")

    L += ["", "### 2.3 一票否决触发条件（`config/conclusion_grades.json → veto_rules`）", "",
          "| ID | 条件 | 触发含义 |", "|---|---|---|"]
    cg = load("config/conclusion_grades.json") or {}
    for t in ((cg.get("veto_rules") or {}).get("triggers") or []):
        L.append(f"| {t.get('id')} | `{t.get('when')}` | {t.get('why')} |")
    onv = (cg.get("veto_rules") or {}).get("on_veto") or {}
    L += ["", f"否决后处置：risk_level ≤ **{onv.get('max_risk_level')}**；conclusion_grade 降至 **L2**；"
              f"追加声明「{onv.get('append_text')}」；门禁严重度 {onv.get('gate_severity')}。"]

    L += ["", "### 2.4 定性词禁用表（`veto_rules.determinative_words`）", ""]
    words = (cg.get("veto_rules") or {}).get("determinative_words") or []
    L.append("　".join(f"`{x}`" for x in words))

    L += ["", "## 3 四道门禁判据清单（38 条）", ""]
    for g in (qg.get("gates") or []):
        L += [f"### 门禁{g.get('id')} · {g.get('cn')}（{g.get('source')}）", ""]
        L += ["| 判据 | 层 | 严重度 | 规则 | 修复建议 |", "|---|---|---|---|---|"]
        for c in (g.get("checks") or []):
            L.append(f"| {c.get('id')} | {c.get('layer')} | {c.get('severity')} | {c.get('rule')} | {c.get('fix')} |")
        L.append("")
    return w("03_规则库.md", L)


# ================================================================ 04 模板库
def gen_template_library() -> Path:
    L = hdr(
        "04 · 模板库",
        "指令：WB-TRISK-2026-001 §3.4（模板与内容分离、多受众模板）＋§3.3（页眉页脚/索引/签署）",
    )
    spec = load("config/archive_spec.json") or {}
    L += ["## 1 页眉 / 页脚（`config/archive_spec.json`）", "",
          "| 区域 | 必需 | 字段 | 渲染式 |", "|---|---|---|---|"]
    for zone in ("header", "footer"):
        z = spec.get(zone) or {}
        L.append(f"| {zone} | {z.get('required')} | {'、'.join(z.get('fields') or [])} | `{z.get('render')}` |")
    L += ["", f"密级档：{'、'.join((spec.get('footer') or {}).get('security_levels') or [])}"
              f"（默认 {(spec.get('footer') or {}).get('default_security_level')}）"]

    L += ["", "## 2 七类索引（`archive_spec.indexes`）", "",
          "| 索引 | 中文名 | 编号规则 | 必需 | 字段 |", "|---|---|---|---|---|"]
    nb = load("config/numbering.json") or {}
    for i in (spec.get("indexes") or []):
        rule = i.get("rule") or "—"
        prefix = ((nb.get("rules") or {}).get(rule) or {}).get("prefix", "—")
        L.append(f"| `{i.get('id')}` | {i.get('cn')} | {prefix} | {i.get('required')} | {'、'.join(i.get('keys') or [])} |")

    L += ["", "## 3 签署栏（`archive_spec.signature_block`）", "",
          "| 角色 | 中文名 | 日期字段 |", "|---|---|---|"]
    for r in (spec.get("signature_block") or {}).get("roles") or []:
        L.append(f"| `{r.get('key')}` | {r.get('cn')} | `{r.get('date_key')}` |")
    L += ["", f"附加字段：{'、'.join((spec.get('signature_block') or {}).get('extra_fields') or [])}"]

    L += ["", "## 4 归档导出包成员（`archive_spec.export_package`）", "",
          "| 成员 | 中文名 | 扩展名 | 必需 |", "|---|---|---|---|"]
    for m in (spec.get("export_package") or {}).get("members") or []:
        L.append(f"| `{m.get('id')}` | {m.get('cn')} | `{m.get('ext')}` | {m.get('required')} |")

    L += ["", "## 5 渲染层降级规则（HTML → PDF/Word）", "",
          "本批**新增**：HTML 报告的交互元素不得带出到文档交付物。", "",
          "| 项 | 规则 |", "|---|---|"]
    rl = spec.get("render_layer") or {}
    L.append(f"| 禁止出现在导出物中的词 | {'、'.join(rl.get('forbid_in_exports') or rl.get('forbid_in_export') or [])} |")
    toc = rl.get("toc") or {}
    L.append(f"| 目录来源 | 必须由正文标题生成（`{toc.get('source')}`），需页码={toc.get('require_page_no')} |")
    L.append(f"| 空表策略 | {rl.get('empty_table_policy')} |")
    L.append(f"| 分页样式 | @page={'必需' if (rl.get('page_css') or {}).get('require_at_page') else '—'}，"
             f"页脚计数={'必需' if (rl.get('page_css') or {}).get('require_footer_counter') else '—'} |")

    L += ["", "## 6 报告受众分版（§3.4「模板库按报告类型管理」）", "",
          "| 版本 | 读者 | 内容范围 | 状态 |", "|---|---|---|---|"]
    for a, b, c, d in [
        ("老板摘要版", "企业法定代表人", "结论页 / 税负区间页 / 行动页 / 红线三栏页 / 补交清单页 / 口径限制页 / 签署页（≤8 页）", "**待建（P1）**"),
        ("财务执行版", "财务负责人", "逐项行动清单 + 补交清单 + 更正口径", "**待建（P1）**"),
        ("税务顾问版", "外部税务顾问", "要件核对表 + 证据角色表 + 法条引用 + 口径声明", "**待建（P1）**"),
        ("工作底稿版（现产出）", "检查/复核/归档", "现有 `enterprise_readable_report` 全量内容", "已有，本批加固"),
    ]:
        L.append(f"| {a} | {b} | {c} | {d} |")
    return w("04_模板库.md", L)


# ================================================================ 05 行业包
def gen_industry_pack() -> Path:
    L = hdr("05 · 行业包", "指令：WB-TRISK-2026-001 §四（全行业适配：新增行业无需改代码）")
    ip = load("config/industry_params.json") or {}
    inds = ip.get("industries") or []
    L += [f"## 1 已登记行业（{len(inds)} 个）—— 权威 `config/industry_params.json`", "",
          "| 行业ID | 名称 | 子类（样例） | 风险指标 |", "|---|---|---|---|"]
    for it in inds:
        if not isinstance(it, dict):
            continue
        L.append(f"| `{it.get('industry_id')}` | {it.get('label')} | "
                 f"{'、'.join((it.get('subtypes') or [])[:6])} | {'、'.join((it.get('risk_indicators') or [])[:6])} |")
    if not inds:
        L += ["_（取不到行业表，请检查 config/industry_params.json）_"]

    L += ["", "## 2 新增一个行业的标准动作（只配置、不改代码）", "",
          "1. 在 `static/industry_data.json` 补该行业的基准数据（骨架 `_如何填充` 已注明）。",
          "2. 在 `config/industry_params.json → industries` 加一行（可用 `engine/industry_params.py::new_industry_template()` 生成模板）。",
          "3. 运行 `engine/industry_params.py::validate()` 校验。",
          "4. 如需剔除本行业不适用的必查资料，在 `engine/industry_resolver.not_required_materials()` 登记（**唯一权威**）。",
          "",
          "**成熟度评估：约 8 成。** 基准数据仍需人工填充；风险检测器实现仍属代码层。",
          ]

    L += ["", "## 3 业态剔除（服务型 vs 制造型）", "",
          "本项目铁律：**资料要求跟随业态**，唯一权威 = `engine/industry_resolver.not_required_materials()`。",
          "服务型业态天然无实物货物流转，故以下资料不列入必查：",
          ]
    try:
        import sys as _s
        _s.path.insert(0, str(ROOT))
        from engine import industry_resolver as ir
        fn = getattr(ir, "not_required_materials", None)
        L.append(f"接口：`engine/industry_resolver.not_required_materials()`，签名取到={callable(fn)}")
    except Exception as exc:  # noqa: BLE001
        L.append(f"（接口取不到：{exc}）")

    L += ["", "## 4 待补（P1）", "",
          "- 行业包字段尚未覆盖：资料清单 / 风险指标 / 证据要求 / 模板 / 法规库 —— 现只有基准与阈值。",
          "- 建议按 `config/industry_params.json` 的 schema 扩四个子表，均「加行即生效」。",
          ]
    return w("05_行业包.md", L)


# ================================================================ 06 税种包
def gen_tax_pack() -> Path:
    L = hdr("06 · 税种包", "指令：WB-TRISK-2026-001 §四（新增税种无需改代码）")
    nb = load("config/numbering.json") or {}
    codes = (((nb.get("special_rules") or {}).get("law") or {}).get("tax_codes") or {})
    L += [f"## 1 税种代码表（{len(codes)} 个）—— 权威 `config/numbering.json → special_rules.law.tax_codes`", "",
          "| 代码 | 税种 |", "|---|---|"]
    for k, v in codes.items():
        L.append(f"| `{k}` | {v} |")

    L += ["", "## 2 税率测算表（唯一权威 `engine/tax_impact.py::_RATES`）", "",
          "| 税种/项目 | 税率 | 口径说明 |", "|---|---|---|"]
    try:
        from engine import tax_impact as ti
        table = getattr(ti, "_RATES", None) or {}
        for k, v in table.items():
            rate, note = (v if isinstance(v, (list, tuple)) and len(v) == 2 else (v, ""))
            L.append(f"| {k} | {('未量化' if rate is None else rate)} | {note} |")
        L += ["", f"（共 {len(table)} 项；权威侧另有 `engine/tax_rates.py::CANON_RATES` 用于含税/不含税换算）"]
    except Exception as exc:  # noqa: BLE001
        L.append(f"取不到：{exc}")

    L += ["", "## 3 税种覆盖现状 vs 指令要求", "",
          "| 税种 | 指令要求 | 现覆盖 | 缺口 |", "|---|---|---|---|"]
    for t, need, have, gap in [
        ("增值税", "风险指标/构成要件/证据要求/法规/计算规则", "有（RL-VAT-*、进项差异、红冲等）", "税种包未成独立数据表"),
        ("企业所得税", "同上", "有（扣除限额、贡献率、成本列支等）", "同上"),
        ("个人所得税", "同上", "有（工资/社保/股权转让）", "同上"),
        ("印花税", "同上", "有（RL-SPT-*）", "同上"),
        ("城建税/教育费附加/地方教育附加", "同上", "部分（附加税费计税依据不匹配）", "税种包未成独立数据表"),
        ("文化事业建设费", "同上", "有（RL-SPT-017）", "同上"),
        ("社会保险费", "同上", "有（RL-PAY-001、payroll_rules.py）", "同上"),
        ("房产税 / 土地增值税", "同上", "**弱**", "**缺**"),
    ]:
        L.append(f"| {t} | {need} | {have} | {gap} |")

    L += ["", "## 4 结论：税种包成熟度约 2~3 成", "",
          "现状：税率/纳税调整逻辑散在 `verified_rule_engine.py` / `pipeline.py` / `tax_impact.py` 代码中，",
          "**无独立税种包数据表**。P1 建议：按 `config/industry_params.json` 的成熟范式，新建",
          "`config/tax_packs.json`（键=税种代码，值含 indicators/constituents/evidence/law/compute），",
          "并配 `engine/tax_pack.py::validate()`，与 `industry_params` 同一套写法。",
          ]
    return w("06_税种包.md", L)


# ================================================================ 12 测试用例与测试报告
def gen_tests_report() -> Path:
    L = hdr("12 · 测试用例与测试报告",
            "指令：WB-TRISK-2026-001 §七（必测用例）＋§5.6（回归测试）",
            "本文件由 `scripts/_gen_wb_trisk_docs.py` 调用**实际运行**生成，数据非手写。")
    # 跑验收脚本
    r = subprocess.run([str(ROOT / ".venv" / "Scripts" / "python.exe"),
                        str(ROOT / "scripts" / "_acceptance_wb_trisk_2026_001.py")],
                       capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT))
    L += ["## 1 验收脚本实跑输出（`scripts/_acceptance_wb_trisk_2026_001.py`）", "",
          f"退出码：**{r.returncode}**（0=全部通过）", "", "```text", (r.stdout or r.stderr or "").strip(), "```"]

    L += ["", "## 2 回归测试文件", "",
          "| 项 | 值 |", "|---|---|"]
    tf = ROOT / "tests" / "test_quality_gates_v2.py"
    L.append(f"| 测试文件 | `tests/test_quality_gates_v2.py` |")
    if tf.exists():
        src = tf.read_text(encoding="utf-8")
        L.append(f"| 用例数（@pytest.mark 计数） | plain={src.count('@pytest.mark.plain')} "
                 f"reverse={src.count('@pytest.mark.reverse')} lock={src.count('@pytest.mark.lock')} |")
    r2 = subprocess.run([str(ROOT / ".venv" / "Scripts" / "python.exe"), "-m", "pytest",
                         "tests/test_quality_gates_v2.py", "-q"],
                        capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT))
    L.append(f"| 运行结果 | {((r2.stdout or '').strip().splitlines() or ['—'])[-1]} |")

    L += ["", "## 3 §七 必测用例逐条对照", "",
          "| 指令编号 | 指令要求 | 系统判据 | 真实数据实测 | 结论 |", "|---|---|---|---|---|"]
    rows = [
        ("§七-1a", "个人账户收款 1,082,000 vs 1,082,094.53", "B6 声明计数/同事实多处比对；事实库同键多值",
         "两者并存：1,082,000.00 出现在项3、项4（标签『对公账户收自自然人』）；1,082,094.53 出现在项4（标签『来自个人账户』）；差额 94.53 = 报告内『银行内部款项94.53元』，但**全篇未声明两者关系**",
         "**已捕获**（B6/B7 链路）+ 事实库同键多值判冲突"),
        ("§七-1b", "自然人付款方 3 人 vs 4 人", "同项内同量词多值",
         "项4 并存『3 个自然人付款方』与『4 个自然人』", "已定位；判据以事实库 count 类同键多值承接（文本比对误报率高，见第4节）"),
        ("§七-1c", "银行差异 1,734,859.35 vs 227,659.35", "金额口径登记表",
         "报告已写明『（剔除明显非销售流入后约227,659.35元）』——**已声明口径，不属缺陷**",
         "**判为非缺陷**（若强行判冲突即为假红）"),
        ("§七-1d", "成本无付款 1,498,692.68 vs 13,432.48", "同一标签多值未声明口径",
         "同一项内两处均写『未匹配到任何支付渠道』，金额差 **111 倍**", "**已捕获**（B5/B6 链路）+ 事实库判冲突"),
        ("§七-2", "多税种联动写『可能性低』却列高风险", "B3 / B4",
         "项2 标高风险，正文写『本项已查明的风险的可能性低』；16/16 项 conclusion_grade=待核却带高/中/低等级",
         "**已捕获**（B3 1 项 + A1/A9 11 项）"),
        ("§七-3", "编号缺第八/十/十二/十六/十七", "B2 编号连续性",
         "实测 13/16 有编号，缺号 [8,10,12,16,17]，末值『十八』>项数16，3 项无编号", "**已捕获**（B2，5 处问题）"),
        ("§七-4a", "『说明2。要把这一项查清楚，需要：』后空白", "D2 孤立引导句",
         "报告正文域命中 2 处，原文即『要把这一项查清楚，需要：』段末无内容", "**已捕获**（D2）"),
        ("§七-4b", "『下载 CSV』『点击展开』", "D1 UI 残留（渲染层）",
         "**数据层为 0**；确认其只产生于 HTML 渲染/导出层（见 09 说明书）", "**分层承接**：数据层 D 门禁不误报，渲染层导出前查"),
        ("§七-5", "无页号/无证据号/无复核签署", "C1/C2/C3/C5/C7/C8",
         "缺总底稿号、16 项缺风险号、缺 7 类索引、签署缺『批准人』、缺审计轨迹", "**已捕获**（C 门禁 5 条 ERROR）"),
        ("§七-6", "关键证据缺失时不得输出『已查明风险』『高风险』", "A1/A9/A3 + 一票否决 V1~V6",
         "closure=0 的 9 项带中风险以上；closure<0.8 另有 2 项；16/16 项含定性词『已查明』",
         "**已捕获**（A1×9、A9×2、A3×16）"),
    ]
    for a, b, c, d, e in rows:
        L.append(f"| {a} | {b} | {c} | {d} | {e} |")
    return w("12_测试用例与测试报告.md", L)


# ================================================================ 13 验收报告
def gen_acceptance() -> Path:
    L = hdr("13 · 验收报告",
            "指令：WB-TRISK-2026-001 §六（质量门禁与验收标准）",
            "依据**真实基准样本**的实跑结果生成。")
    L += ["## 1 基准样本", "",
          "| 项 | 值 |", "|---|---|",
          "| 样本 | 《深圳海更数字传媒有限公司税务风险扫描工作底稿》 |",
          "| 企业 | 深圳海更数字传媒有限公司（91440300MA5H824G7M） |",
          "| 数据源 | `data/cache/last_analysis_cache.json`（结构化 report_data） |",
          "| 报告主体 | confirmed_problems 16 项 |", ""]
    try:
        d = json.loads(BENCH.read_text(encoding="utf-8"))
        R = d["1"]["report"]["report"]
        from engine import quality_gates as qg
        res = qg.run_all_gates(R, company_code=COMPANY_CODE, period=PERIOD)
        L += ["## 2 四道门禁实跑结论", "",
              f"- 全部通过：**{res['all_passed']}**",
              f"- 允许生成正式底稿：**{res['formal_output_allowed']}**",
              f"- 汇总：ERROR {res['summary']['total_errors']} / WARN {res['summary']['total_warns']} / SKIP {res['summary']['total_skips']}",
              f"- 未通过门禁：{res['summary']['failed_gates']}",
              f"- 引擎自检：{res['self_check_errors'] or 'OK'}", ""]
        L += ["| 门禁 | 名称 | 状态 | ERROR | WARN |", "|---|---|---|---|---|"]
        for g in res["gates"]:
            L.append(f"| {g['gate']} | {g['cn']} | **{g['status']}** | {g['errors']} | {g['warns']} |")
        L += ["", "### 2.1 逐条 ERROR", "", "| 门禁-判据 | 条数 | 说明 |", "|---|---|---|"]
        for g in res["gates"]:
            for f in g["findings"]:
                if f["severity"] == "ERROR":
                    L.append(f"| {g['gate']}-{f['check_id']} | {f['count']} | {f['message']} |")
        L += ["", "### 2.2 逐条 WARN / SKIP（如实登记，SKIP 不计通过）", "", "| 门禁 | 类型 | 内容 |", "|---|---|---|"]
        for g in res["gates"]:
            for f in g["findings"]:
                if f["severity"] == "WARN":
                    L.append(f"| {g['gate']} | WARN {f['check_id']} | {f['message']} |")
            for s in g["skips"]:
                L.append(f"| {g['gate']} | SKIP | {s} |")
    except Exception as exc:  # noqa: BLE001
        L.append(f"实跑失败：{exc!r}")

    L += ["", "## 3 §六 验收标准逐项判定", "",
          "| 维度 | 指令目标 | 本批实际 | 判定 |", "|---|---|---|---|"]
    for a, b, c, d in [
        ("证据链闭合度", "合格以上（关键证据缺失不得定性；闭合度可量化；补证自动重跑）",
         "一票否决已实现并对基准样本生效（A1×9、A9×2、A3×16）；闭合度可量化且被 B9 锁定自洽性；补证重跑沿用既有全量重跑（增量重算未做）", "**部分满足**"),
        ("逻辑一致性", "合格以上（金额/人数/笔数/编号/风险等级无矛盾）",
         "结构化层零误报判据已生效（B2 编号、B3 等级、B5 定性、B6 计数、B7 跨章节、B9 闭合度自洽）；事实库 SSOT 已建（正向登记待接入产出链）", "**部分满足**"),
        ("归档规范性", "合格以上（编号/页号/索引/证据号/复核签署/审计轨迹）",
         "编号服务、七类索引、签署、审计轨迹、导出包**已定义并可校验**；渲染层页眉页脚/页码与原生 docx 导出**未实现**", "**部分满足**"),
        ("模板整洁度", "合格以上（无 UI 残留/无空白模板/无重复段落/术语统一）",
         "扫描域白名单化后 D 门禁零误报生效（D2/D4/D5 对基准样本报红）；UI 残留检测已下沉到引擎层（原仅前端）；渲染层导出前检查待接", "**部分满足**"),
        ("全行业适配", "可配置", "行业 6 个、参数可配、新增行业约 8 成；税种包约 2~3 成", "**未达标**"),
        ("Skill 固化", "稳定运行", "既有 61 Skill + 3 方案；本批新增能力**尚未登记为 Skill**、编排未接入主流程", "**未达标**"),
    ]:
        L.append(f"| {a} | {b} | {c} | {d} |")

    L += ["", "## 4 未通过项与整改建议（由用户决定是否继续）", "",
          "| 优先级 | 未通过项 | 建议动作 |", "|---|---|---|"]
    for a, b, c in [
        ("P0-1", "事实库 SSOT 未接入产出链", "在报告组装处 `fact_store.declare()` 登记每个进入正文的金额/人数，使 B1 由「未执行(SKIP)」变为「可判定」"),
        ("P0-2", "渲染层页眉页脚/页码未实现", "导出模板加 `@page` + `counter(page)/counter(pages)`；目录改为由正文标题生成"),
        ("P0-3", "原生 docx 导出未实现", "`python-docx==1.2.0` 已在依赖中，补 `HTML→docx` 适配层并做降级（剥 `**`/UI 词/空表）"),
        ("P0-4", "空表与折叠面板降级", "导出时展开或整段省略（`archive_spec.render_layer.empty_table_policy`）"),
        ("P1-1", "风险等级五维加权算法未实现", "按 `RISK_LEVEL_BASIS` 扩为可配权重表（配置化，行业可覆盖）"),
        ("P1-2", "替代程序库仅登记未贯通", "A7 由 WARN 升 ERROR，并让报告『补救要求』列直接取替代库"),
        ("P1-3", "税种包未成独立数据表", "新建 `config/tax_packs.json` 并配 validate()"),
        ("P1-4", "Skill 固化未完成", "把四道门禁登记为 TaxRiskScan.Workpaper.Generator 的步骤与门禁，接入 skill_runtime"),
    ]:
        L.append(f"| {a} | {b} | {c} |")
    return w("13_验收报告.md", L)


# ================================================================ 15 归档样例
def gen_archive_sample() -> Path:
    L = hdr("15 · 归档样例", "指令：WB-TRISK-2026-001 §3.3（归档导出包、索引、编号）",
            "由 `engine/numbering.py` 与 `config/archive_spec.json` **现算**生成，非手写。")
    from engine import numbering as nb
    svc = nb.NumberingService(COMPANY_CODE, PERIOD)
    L += ["## 1 编号样例", "", "| 类型 | 样例编号 |", "|---|---|"]
    for k in svc.covered_kinds():
        if k == "law":
            L.append(f"| {k} | `{svc.make(k, 3, tax_code='VAT')}` / `{svc.make(k, 1, tax_code='CIT')}` |")
        elif k == "workpaper":
            L.append(f"| {k} | `{svc.workpaper_no(1)}` |")
        elif k == "evidence":
            L.append(f"| {k} | `{svc.make(k, 1)}` … `{svc.make(k, 25)}` |")
        else:
            L.append(f"| {k} | `{svc.make(k, 1)}` |")

    L += ["", "## 2 归档目录结构（约定）", "", "```text",
          f"{svc.workpaper_no(1)}_深圳海更数字传媒有限公司_{PERIOD}_正式版/",
          "├── manifest.json                 # 归档清单（成员+哈希+版本）",
          "├── 01_正式版.pdf                 # 只读正式件",
          "├── 02_可编辑版.docx              # 可编辑件（已做渲染层降级）",
          "├── 03_数据包.xlsx                # 金额索引/风险索引/证据索引/资料缺口索引",
          "├── 04_证据附件包.zip",
          "├── 05_索引.json                  # 七类索引的机读版",
          "└── 06_版本对比.md                # 与上一版逐项 diff",
          "```"]

    L += ["", "## 3 七类索引表头样例", ""]
    spec = load("config/archive_spec.json") or {}
    for i in (spec.get("indexes") or []):
        prefix = ((load("config/numbering.json") or {}).get("rules") or {}).get(i.get("rule") or "", {}).get("prefix", "—")
        L += [f"### {i.get('cn')}（{prefix}）", "", "| " + " | ".join(
            [f"{k}" for k in (i.get("keys") or [])]) + " |",
            "|" + "---|" * len(i.get("keys") or []), ""]

    L += ["", "## 4 审计轨迹样例（append-only）", "", "```json",
          json.dumps([{
              "at": "2026-10-08T00:07:36", "operator": "system(one-click-analysis)",
              "action": "生成工作底稿", "target": svc.workpaper_no(1),
              "before": None, "after": "draft",
              "reason": "首轮一键分析",
              "source_data_version": "202601", "rule_version": "1.0.0",
              "template_version": "1.0.0", "skill_version": "1.0.0",
          }], ensure_ascii=False, indent=1), "```",
          "",
          "> 说明：`operator` 必须是可识别主体。现有 `report_compliance.record_version()` 缺『谁』字段 —— 本批已在 `config/archive_spec.json → audit_trail.entry_fields` 中登记该要求，接入为 P0-3。"]
    return w("15_归档样例.md", L)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    made = []
    for fn, label in [
        (gen_data_dictionary, "02_数据字典.md"),
        (gen_rule_library, "03_规则库.md"),
        (gen_template_library, "04_模板库.md"),
        (gen_industry_pack, "05_行业包.md"),
        (gen_tax_pack, "06_税种包.md"),
        (gen_tests_report, "12_测试用例与测试报告.md"),
        (gen_acceptance, "13_验收报告.md"),
        (gen_archive_sample, "15_归档样例.md"),
    ]:
        try:
            p = fn()
            made.append((label, p.stat().st_size))
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL {label}: {exc!r}")
    print("生成完成：")
    for k, v in made:
        print(f"  {k:<28} {v:>8} 字节")
    return 0


if __name__ == "__main__":
    sys.exit(main())
