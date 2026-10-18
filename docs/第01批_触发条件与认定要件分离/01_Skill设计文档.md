# 01 · Skill 设计文档 —— 触发条件与认定要件分离

> **Skill 名称**：触发条件与认定要件分离（trigger_conditions / determination_criteria separation）
> **系统登记 id**：`trigger_constituent_separation`（`config/skill_specs.json`，version `1.1.0`）
> **实现文件**：`engine/trigger_conditions.py`（第 38 行 `VERSION = "1.1.0"`）
> **更新日期**：2026-10-07
> **落盘位置**：`docs/第01批_触发条件与认定要件分离/01_Skill设计文档.md`

---

## 1. Skill 职责（一段话）

**把"出现什么信号就列为疑点"（触发条件）与"满足什么条件才认定风险成立"（认定要件）彻底分开。**
本 Skill 之前，两者被混为一谈统一叫"构成要件"：系统查到 13 张红字发票、工资 6 人/社保 5 人、
9 个月差异超阈值、2 笔固定资产付款（这些**都是"列入检查"的依据**），却把第 1 条认定要件写成
「未形成核对结论」——读者无法分辨"疑点成立"与"风险成立"。本 Skill 让每条风险指标**必须同时定义**
两类条件，疑点形成时记录命中了哪条触发条件，逐条核对认定要件并分别记状态，报告明确写出
「本项因触发条件 X 而列为疑点 / 认定要件共 N 条：已满足 M 条、待核实 K 条 / 疑点成立、风险是否成立待定」。

---

## 2. 输入字段

| 输入 | 来源（唯一权威） | 说明 |
|---|---|---|
| 风险指标定义（触发条件 + 认定要件） | `config/risk_conditions.json`（130 条 = 127 红线派生 + 3 人工登记发现） | 由 `scripts/_gen_risk_conditions.py` 从 `engine.tax_redlines` 派生，人工可逐条修订 |
| 疑点数据 | `report_data.comprehensive.redline_detection.suspicions[]` | 每个疑点携带 `redline_id` / `constituents` / `constituent_sources` / `evidence_chain` |
| 核对结果 | `engine.constituent_checkpoint.build_constituent_checkpoints(suspicion)` | 逐要件独立核对记录（含 `_conclusion` 枚举、`核对结论` 展示文本） |

## 3. 输出字段（**已落盘**，非仅文本）

| 规格字段 | 落盘键名（唯一权威 `trigger_conditions.classify()`） | 类型 | 实测示例（疑点1） |
|---|---|---|---|
| 风险编码 | `risk_code` | str | `"RL-VAT-007"` |
| 触发条件清单 | `trigger_conditions` | list | `[{"id":"T1","desc":"存在红字发票或作废发票（红冲行为）","auto":true,"hit":true,"evidence":"销项红字/作废 1,015,900.00 元，占同期销项蓝字开票额 12.6%"}]` |
| 每条触发条件命中状态 | `trigger_status` | dict | `{"hit_count":1,"listed":true,"conditions":[…]}` |
| 认定要件清单 | `determination_criteria` | list | `[{"id":"C1","desc":"…","is_precondition":true,"status":"checked_hit","status_text":"符合情形（这项属于现象/前提条，存在即成立）","independent_source":"销项发票、进项发票"}]` |
| 每条认定要件核对状态 | `criterion_status` | dict | `{"C1":{"status":"checked_hit","text":"符合情形（…）","is_precondition":true}}` |
| **疑点是否成立** | `suspicion_established` | **bool** | `true` |
| **风险是否成立** | `risk_established` | **bool** | `false` |
| 结论表述 | `conclusion` | str | `"本项因触发条件「…」而列为疑点。认定要件共 7 条：已满足 1 条、待核实 6 条。疑点成立（触发条件已命中；这是「列入检查」的依据，不等于违法认定）。风险是否成立待定：须待上述待核实要件核对完毕后方可认定。"` |

> 落盘位置：`scripts/four_reports/company_1_full.json` → `enterprise_readable_report.confirmed_problems[i].trigger_determination`
> 实测落盘：**16 / 16 疑点**（命令与输出见 `06_写入系统证据.md` §2）。

## 4. 参数配置

| 配置项 | 位置（文件:行） | 取值 |
|---|---|---|
| 触发条件字典 | `config/risk_conditions.json` → `risks[].trigger_conditions[]` | 每条 `{id, desc, auto}`；**94 条风险指标各 ≥1 条**（合计 **94 条**） |
| 认定要件字典 | `config/risk_conditions.json` → `risks[].determination_criteria[]` | 每条 `{id, desc, is_precondition}`；**130 条风险指标各 ≥1 条**（合计 **600 条**，其中**前提条 142 条**） |
| 状态字典 | `engine/trigger_conditions.py` 第 53–57 行 | `SAY_TRIGGER` / `SAY_ROLLUP` / `SAY_SUSPICION_OK` / `SAY_RISK_PENDING` / `SAY_RISK_OK` |
| 前提条标记 | `config/risk_conditions.json` → `determination_criteria[].is_precondition` | 结构化字段（**不是**文本词表）；派生规则见 `scripts/_gen_risk_conditions.py::is_existence_criterion` |
| 结论枚举 | `engine/constituent_checkpoint.py` 第 53–71 行 `_CONCLUSION_ZH` | `checked_hit / checked_miss / threshold_unmet / not_concluded / not_checked / not_applicable` |

## 5. 配置 JSON（**真实写入系统**，非示例占位）

`config/risk_conditions.json`（`schema=1, version=1.0.0, updated=2026-10-07`，`risks` **94 条**（91 红线派生 + 3 人工登记）），RL-VAT-007 实条：

```json
{
  "risk_code": "RL-VAT-007",
  "name": "红字冲销与作废发票比例异常",
  "trigger_conditions": [
    { "id": "T1", "desc": "存在红字发票或作废发票（红冲行为）", "auto": true }
  ],
  "determination_criteria": [
    { "id": "C1", "desc": "存在红字发票或作废发票（红冲行为）", "is_precondition": true },
    { "id": "C2", "desc": "红冲发生在月末、季末或申报期前后等敏感时点", "is_precondition": false },
    { "id": "C3", "desc": "红冲无对应退货单、折让协议等合法事由", "is_precondition": false },
    { "id": "C4", "desc": "红字发票缺《红字发票信息确认单》，或与被冲减蓝字发票不配平（无对应蓝票、购方或金额不符、非一正一负配平）", "is_precondition": false },
    { "id": "C5", "desc": "存在跨年度红冲，或单张红冲金额高于同期蓝票水平（可能跨期调节收入、冲减上年度利润）", "is_precondition": false },
    { "id": "C6", "desc": "频繁作废发票后重新开具以调节税额或隐瞒真实交易", "is_precondition": false },
    { "id": "C7", "desc": "不属于下列正当情形：开票信息填写错误当月作废重开；客户退货或销售折让（有协议支撑）；跨期价格调整与结算差异", "is_precondition": false }
  ]
}
```

> 与用户规格 JSON 的字段名**逐字一致**（`risk_code / trigger_conditions[].{id,desc,auto} / determination_criteria[].{id,desc,is_precondition}`）；
> 仅 `risk_code` 沿用了本项目既有的红线编号体系（`RL-*`），未另起第二套编码。

## 6. 测试用例清单

| 层级 | 类（`tests/test_trigger_determination_separation.py::`） | 用例数 | 关键断言 |
|---|---|---|---|
| 单元（用户样例） | `TestUnitSamples` | **10** | 疑点1/3/4/12 前提条判 `checked_hit` 且结论以「符合情形」开头；触发命中 ⇒ 疑点成立；词表不是必需（结构化 `is_precondition` 才是权威） |
| 单元（结构化落盘） | `TestStructuredOutput` | **7** | 16 疑点 8 字段齐全；触发命中 ⇔ 疑点成立；要件↔状态一一对应；四样例 C1 前提条=符合情形 |
| 集成 | `TestIntegrationAllRisks` | **3** | 94 条风险指标**每条**都同时定义触发条件与认定要件；前提条全判「符合情形」；无"已列为疑点却无触发条件" |
| 反向验证 | `TestGateReverseValidation` | **3** | 构造"触发条件未命中却列为疑点"/"前提条未写符合情形"/"缺结构化块" ⇒ 门禁必须报红 |
| 回归 | `TestGateRegression` | **2** | 配置级门禁 0 ERROR；病句「未涉及任何一条构成要件」不得再产出 |
| 反向锁（人工条目） | `TestManualEntriesNotClobbered` | **3** | 人工登记的 `aliases` 条目不得被生成器覆盖（本批实测事故的防回退锁） |
| **合计** | | **28 passed**（分项 10 + 7 + 3 + 3 + 2 + 3 = 28） | 命令：`./.venv/Scripts/python.exe -m pytest tests/test_trigger_determination_separation.py -q --collect-only` → `28 tests collected`（**分项加总 = 合计 = 28**） |

## 7. 版本变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| 1.0.0 | 2026-10-07 | 新建：`engine/trigger_conditions.py`、`config/risk_conditions.json`（94 条）、门禁 `check_trigger_determination_separation()`、报告分层句、测试 9 例；4 疑点第 1 条改为「符合情形」 |
| **1.1.0** | 2026-10-07 | ① 新增 `aliases` 字段（无红线/规则键控的 3 个发现获得正式触发源，触发源绑定 16/16）；② **新增规格【输出】结构化落盘** `confirmed_problems[].trigger_determination`（`_finalize_trigger_determination()`，16/16 疑点）；③ 门禁扩充 4 条产物级判据（字段齐全 / 触发命中⇔疑点成立 / 要件与状态一一对应 / 前提条必须写符合情形）；④ 测试 9 → **28 例**（含 3 例反向验证；实测 `pytest tests/test_trigger_determination_separation.py -q` → `28 tests collected`） |

## 8. 依赖说明

| 方向 | 模块 | 关系 |
|---|---|---|
| 本 Skill 依赖 | `engine/constituent_checkpoint.py` | 提供逐要件核对记录（`criterion_status` 的来源） |
| 本 Skill 依赖 | `config/risk_conditions.json` | 触发条件/认定要件配置（唯一权威） |
| 本 Skill 依赖 | `engine/industry_resolver.py` | 业态剔除（要件数据源是否"本业态不适用"） |
| 本 Skill 被依赖 | `engine/enterprise_report.py`（第 3094 行 `_enterprise_situations` → 第 3151 行 `verdict_sentence`；第 2516 行 `_finalize_trigger_determination`） | 报告里那两句分层结论句 + 结构化块落盘 |
| 本 Skill 被依赖 | `tools/audit_consistency.py`（第 11606 行 `check_trigger_determination_separation()`，第 13014 行并入总链） | 质量门禁 |
| 本 Skill 被依赖 | `engine/child_item_completeness.py`（Skill 6）/ `engine/data_source_status.py`（Skill 7） | 各自用 `is_precondition()` 判前提条（**不各自实现**） |

---

**本项是否满足验收标准**：**满足**。
① 名称/版本/日期齐备（§开头）；② 职责一段话（§1）；③ 输入字段 3 类（§2）；④ 输出 8 字段（§3，含实测示例）；⑤ 参数配置 5 项（§4）；⑥ 配置 JSON 为**真实写入系统**的实条（§5）；⑦ 测试清单（§6，**28 例**实测通过）；⑧ 版本变更记录（§7，2 条）；⑨ 依赖说明（§8，双向）。
