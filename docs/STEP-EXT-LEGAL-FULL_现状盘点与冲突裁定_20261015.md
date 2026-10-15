# STEP-EXT-LEGAL-FULL 现状盘点与冲突裁定（2026-10-15）

> 本文件是执行《法规库与规则引擎深度关联及全量专题整合》指令的**第 0-1 步产出**。
> 按指令第十二条「遇到 DECIDE，暂停并请求裁定」，本文列出**必须先裁定的 4 项结构性冲突**。
> 全部结论**可自证来源**（附实测命令与输出）。

---

## 一、现状盘点（实测，非推测）

### 1.1 法规库相关既有资产

| 资产 | 规模（实测） | 角色 | 唯一权威？ |
|---|---|---|---|
| `static/legal_library.json` | **131 条 / 66 部法**（字段 `law/article/content/source`） | 法条**正文库** | ✅ 条文唯一来源 |
| `static/legal_refs.json` | 12 条（`law/content/scenario`） | 历史要点库 | 并入正文库读层 |
| `config/legal_versions.json` | **73 部法**（current 63 / expired 6 / amended 3 / superseded 1） | 版本状态登记 | ✅ 版本唯一权威 |
| `config/legal_text_coverage.json` | 1 份：`206 引用 / 205 命中 / 99.51%` | 覆盖率登记（现算） | ✅ 覆盖率唯一口径 |
| `engine/legal_citation.py` | 282 行 | 引用解析/补全 | ✅ 引用唯一权威 |
| `engine/legal_version.py` | 440 行 | 版本状态判定 | ✅ 版本唯一权威 |
| `engine/legal_library.py` | P2-1 新增 | 法规库**读层**（不出现数据文件字面量） | — |
| `engine/legal_reasoner.py` / `legal_updater.py` / `law_validity_checker.py` | 既有 | 推理 / 更新 / 有效性检查 | — |
| `legal_api.py` | **5 个端点** `/api/v1/legal-library/*` + 1 页面路由 | 浏览/检索层 | — |
| `static/legal_library.html` + `static/js/legal_library.js` | 124 行 + 页面逻辑 | 法规库浏览页（原生 JS） | — |
| `scripts/_load_legal_texts.py` | 幂等录入器 | 正文库**唯一录入权威** | ✅ |
| 闸门 | `check_legal_library_wiring` / `check_legal_text_coverage` / `check_legal_versioning` / `check_redline_legal_basis_currency` | 绑定上述权威与路径 | — |

**P2-1 交付时已自述**：*「条文与版本数据俱全，缺的是「浏览 / 检索」这一层」*（见 `docs/P2-1_法规库_交付报告_20261014.md`）。该层已于 2026-10-14 交付。

### 1.2 规则侧既有资产

| 资产 | 规模（实测） | 关键事实 |
|---|---|---|
| `engine/tax_redlines.py` | **91 条红线**，ID 体系 `RL-<税种>-<NNN>` | 含 `legal_basis`（"《法》第X条"**自由文本**），字段：`constituents`/`clue_chain`/`evidence_chain`/`required_materials`/`remedy`/`violation_any_of` 等 18 项 |
| 发票类红线 | `RL-INV-001` ~ `RL-INV-004`（4 条） | 编号为 `RL-INV-###`，**非**指令的 `INV-###` |
| 候选规则库 | **460 条**（`rulelist_v1/v11/v12.json`，60/174/226） | ★★ **`legal_basis_ref` 占位率 100%**（460/460）——实测每条都是 `{"law":"","article":"","raw":"法规库自动匹配","placeholder":true}` |
| `engine/rule_loader.py` | 5 类载体（Python 执行 / JSON 候选 / YAML 导出 / DSL 边界 / 治理） | 规则加载唯一入口 |
| `config/redline_detector_attribution.json` | 归属登记表 | 红线归属唯一权威 |
| `engine/rule_versions.py` | 规则版本 | 规则分层计数权威 |

### 1.3 数据源可达性（实测 2026-10-15 15:40）

| 数据源 | 结果 |
|---|---|
| `https://www.chinatax.gov.cn/` | **HTTP 200**（0.80s） |
| `https://fgk.chinatax.gov.cn/` | **HTTP 200**（0.19s） |
| `https://12366.chinatax.gov.cn/` | **HTTP 200**（0.63s） |

⇒ 三源**全部可达**，抓取技术可行。遵守 robots.txt 与"不高频请求"约束是工程节奏问题，不是可行性问题。

### 1.4 法规库对首个专题「虚开发票」的覆盖（实测）

正文库 131 条中，含虚开/发票/抵扣凭证/走逃/失联/善意/代开关键词的仅 **14 条**：

| 法名 | 条数 |
|---|---|
| 发票管理办法 | 6 |
| 国家税务总局公告2019年第38号 | 2 |
| 增值税专用发票使用规定 / 企业所得税税前扣除凭证管理办法（018年28号、正文） | 各 1 |
| 增值税法 / 2014年第39号公告 / 文化事业建设费通知 | 各 1 |

**缺口（指令第八部分点名要求、现库缺失）**：`刑法第205条/205条之一/212条`、`发票管理办法第21条/第35条/第37条`、`发票管理办法实施细则`、`两高解释（2024）`、`立案追诉标准`、`纳税人合规开具发票正负面清单`、`全国税务行政处罚裁量基准`、`重大税收违法失信主体信息公布管理办法`、`联合惩戒措施清单`、`走逃失联企业公告`、`异常增值税扣税凭证管理公告`、`国税发〔2000〕187号（善意取得）`、`国税函〔2007〕1240号（不加收滞纳金）` 等。

---

## 二、差距分析：指令要的 vs 项目已有

| 指令要求 | 项目现状 | 判定 |
|---|---|---|
| 三数据源抓取 | 三源可达，**未抓取**（现有 131 条来自人工核实录入） | **真缺口** |
| 14 类文件类型归集 | 现库有法律/行政法规/规范性文件/公告，缺**批复/函/解读/问答/指引/司法解释/地方性文件** | **真缺口** |
| 效力状态过滤 | ✅ 已有 `legal_versions.json`（6 档状态）+ `legal_version` 判定 + 闸门 | 已有，可复用 |
| 法规库结构化（条款级） | ✅ 已有 131 条条款级（`law+article+content+source`） | **已有，但无稳定条款 ID** |
| 法规库标签化/索引化 | ⚠️ 仅按 `law` 分组；**无话题标签** | **真缺口** |
| 法规关系（引用/修订/废止） | ❌ 无 | **真缺口** |
| 法规-规则双向关联 | ❌ 无映射表；红线只有 `legal_basis` 自由文本；**460 候选 100% 占位** | **真缺口（核心）** |
| 专题（TOPIC）维度 | ❌ 全仓无"专题"概念 | **真缺口** |
| 前端专题列表/详情/知识图谱 | ❌ 只有按法名的浏览页 | **真缺口** |
| 规则提取/去重/参数化/分批入库 | 部分已有（去重合并有 `dupkit`；参数化有 `params_ref`；版本有 `rule_versions`） | 可复用 + 需扩展 |
| 不编造条文 / 不硬编码法规条款 | ✅ 已有硬判据（`check_legal_text_coverage` + P2-1「逐字反查」反向验证） | 已有，须延续 |

---

## 三、硬冲突（必须先裁定，否则违反项目铁律）

### 冲突 A：指令要建 5 张 DB 表 vs 项目「单一权威」

| | 指令方案 | 项目现状 |
|---|---|---|
| 数据落地 | 新建 `legal_documents` / `legal_provisions` / `legal_topics` / `legal_relations` / `legal_mappings` 五张**数据库表** | 已有 `legal_library.json` + `legal_versions.json` **两个 JSON 权威**，且**四道闸门绑定其路径与形态** |
| 条款标识 | `provision_id`（新造） | `{law, article}` 复合键（现用） |
| 页面写入 | 未禁止 | P2-1 明确「**法规库只读**，写入仍走 `_load_legal_texts.py`，人工核实后录入——**有意如此**」 |

**风险**：建 DB 五表 = **同一概念（法条正文）出现第二个权威**。这是本项目最高频、代价最大的事故类型（记忆铁律：「单一权威（多头维护=事故）」「★同一概念必查「另一条链路在哪判」」）。若不撤旧权威，`check_legal_text_coverage` / `check_legal_library_wiring` 会与新的 DB 表口径打架；若撤旧权威，则要同步改 4 道闸门 + P2-1 读层 + 5 个端点 + 页面 —— 属「迁移级」改动。

**可选路径**：
- **A1（建议）**：**扩展现有 JSON 权威**——`legal_library.json` 每条**加字段**（`provision_id` / `topic_tags` / `kind`），新增 `config/legal_topics.json`（专题表）与 `config/legal_relations.json`（关系表），**加数据不改逻辑分支**（符合项目「新增对象只加一行数据」）。DB 表**不建**。
- **A2**：按指令建五表，并把 JSON 权威**迁移**为 DB 表（新权威），同步撤换 4 道闸门与读层。工期显著更长，但更接近指令原文。

### 冲突 B：规则编号与字段体系冲突

指令给的 31 条规则（`INV-021`~`INV-051`）存在两处**不能照搬**的问题：

1. **编号体系冲突**：项目现用 `RL-<税种>-<NNN>`（如 `RL-INV-001`）；指令用 `INV-###`。两套并存 = 同一"发票类规则"两个编号空间。
2. **条件表达式引用了项目中不存在的字段**：`shell_company_indicators` / `circular_invoice_detected` / `false_trade_chain_detected` / `invoice_goods_name != actual_goods_name` 等——项目规则的 `condition` 约束于真实可得的输入字段（见 `rulelist_v1/v11/v12.json` 的 `inputs` 与 `engine/numparse` / `fieldkit`）。**照搬这些表达式会同时违反两条红线**（①不照搬候选规则；②不硬编码法规条款），且规则**跑不通**（无输入字段 ⇒ 静默不命中或报错）。

**可选路径**：
- **B1（建议）**：坚持**只新增/增强，编号沿用 `RL-INV-###`**（下一个可用号，如 `RL-INV-005…`），`condition` 一律改写为项目**真实字段**，`legal_basis_ref` 指向**法规库实际条款 ID**。
- **B2**：按指令原样采用 `INV-###` 编号与英文字段占位，后续再映射。

### 冲突 C：范围与工期

指令要求 **20 个专题**（P0 六个）× 3 源 × 14 文件类型 × 2~3 层关联追踪，且**「不跳步、不并行、不合并」**。
- 现实：一次完整爬取（含慢速、断点续爬、去重、条款拆解、人工核实录入）是**跨多轮**的工程量。
- 若追求单轮"全量做完"，只能靠**编造条文**填充 —— 直接触碰红线⑤（不编造法规条文）。

**可选路径**：
- **C1（建议）**：本轮只做 **TOPIC-001「虚开发票」端到端闭环**（专题注册 → 补法规缺口（真抓取+人工核实）→ 条款拆解打标 → 法规-规则关联 → 前端专题页），作为**可复制的模板**，后续专题按同一模板逐轮推进。
- **C2**：本轮只做**底座**（专题注册 + 条款 ID + 关系表 + 关联表 + 前端骨架），不抓取、不扩规则。
- **C3**：六个 P0 专题全量（工期最长，多轮）。

### 冲突 D：460 条候选规则的占位如何落地

460 条候选的 `legal_basis_ref` **100% 占位**，且字段值就是"法规库自动匹配"。指令第 6.3 节要求「自动关联 + 人工复核才生效」。

项目铁律：「**不确定就不报**」「取不到数据时明确说明未确定，绝不用默认值静默顶替」。因此：
- 自动相似度匹配只能产出**候选建议**，不得直接置为 `verified=true`；
- 本轮可确证的（法规库中**确有条文**支撑的规则）→ 填真实条款 ID；
- 无法确证的 → **保持占位并如实标注**（不改写成看似已关联）。

---

## 四、建议执行路径（待裁定后细化）

以 **A1 + B1 + C1 + D（如实标注）** 为推荐组合：

| 阶段 | 内容 | 产出 |
|---|---|---|
| S1 | 专题注册 `config/legal_topics.json`（TOPIC-001~020 元数据，数据驱动） | 专题表 |
| S2 | 给正文库加 **稳定条款 ID + 话题标签 + 文件类型**（`legal_library.json` 加字段；`_load_legal_texts.py` 同步） | 条款 ID / 标签 |
| S3 | **补齐 TOPIC-001 法规缺口**（三源真抓取 → 人工核实 → 录入；不改写、不编造） | 专题法规全量清单 + 效力统计 |
| S4 | 法规关系表 `config/legal_relations.json`（引用/修订/废止，≥2 层） | 关系表 |
| S5 | 关联表 `config/legal_mappings.json`（规则 ↔ 条款，含 `verified` 与来源） | 双向关联 |
| S6 | 规则丰富（TOPIC-001 相关，**沿用 `RL-INV-###`**，真实字段条件表达式） | 新增规则 + 去重/参数化清单 |
| S7 | 前端：专题列表 / 专题详情 / 条款检索 / 规则-法规关联 | 页面 + 端点 |
| S8 | 报告：《专题法规全量清单》《效力状态统计》《规则库丰富报告》 | 报告 |

---

## 五、待裁定项（4 项）

1. **底座形态**：A1 扩展现有 JSON 权威（建议）/ A2 新建 DB 五表并迁移。
2. **规则编号与字段**：B1 沿用 `RL-INV-###` + 真实字段（建议）/ B2 按指令 `INV-###` 原样。
3. **本轮范围**：C1 仅 TOPIC-001 端到端（建议）/ C2 仅底座 / C3 六个 P0 专题。
4. **占位规则处理**：D1 只填可确证者、其余如实标注（建议）/ D2 自动匹配后全量写入。

---

## 附：本文实测命令

```bash
# 三源可达性
for u in https://www.chinatax.gov.cn/ https://fgk.chinatax.gov.cn/ https://12366.chinatax.gov.cn/; do
  curl -s -o /dev/null -w "%{http_code}\n" --max-time 12 -A Mozilla/5.0 "$u"; done

# 候选规则占位率（460/460 占位）
python -c "import sys;sys.path.insert(0,'.');from engine import rule_loader as RL;
c=RL.load_json_candidates();
print(len(c), sum(1 for r in c if any(x.get('placeholder') for x in (r.get('legal_basis_ref') or []))))"

# 正文库规模 / 虚开发票覆盖
python -c "import json;d=json.load(open('static/legal_library.json',encoding='utf-8'));
kw=['虚开','发票','抵扣凭证','走逃','失联','善意','代开'];
print(len(d), len([e for e in d if any(k in e['law']+e['content'] for k in kw)]))"
```
