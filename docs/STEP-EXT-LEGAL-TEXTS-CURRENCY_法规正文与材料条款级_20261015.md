# 法规正文与材料条款级落地（2026-10-15 后续轮）

承接 `STEP-EXT-LEGAL-FULL-MATCH` 的四项遗留。**四项全部落地**，并额外修掉两处由此暴露的
**既有实现缺陷**（中文数字解析多头维护、条号排序键错乱）。

---

## 一、四项遗留的落地结果

| # | 遗留项 | 落地结果 | 可核验产物 |
|---|---|---|---|
| ① | 法律/行政法规正文多数未入正文库，须逐部核实时效 | ✅ **正文库 131 → 7009 条**；140 部采集，**101 部「全文有效」入库**，29 部**不入库并逐部写明原因** | `static/legal_library.json`、`config/legal_texts_currency.json` |
| ② | 材料与条款只关联到法规级 | ✅ **条款级已打通**（粒度**三态** `provision`/`law`/`none`） | `config/legal_materials.json`（`provision_ids`/`matched_provisions`）、`engine/legal_extras.py` |
| ③ | 规则 `params` 阈值参数化接引擎判定 | ✅ **阈值唯一权威表** + 收敛 **8 处硬编码**，反向验证证明"真读表" | `config/rule_params.json`、`engine/rule_params.py` |
| ④ | 案例/解读/问答只有元数据+摘要 | ✅ **2055 条正文已采**（案例 966 / 解读 646 / 问答 443） | `data/legal_crawl/material_texts/`（2055 个 JSON） |

---

## 二、① 逐部核实时效：三道闸 + 台账

### 正文来源（实测修正）
列表 `url` 给的是 `www.chinatax.gov.cn/zcfgk/...` —— **实测 404**；
换成 `fgk.chinatax.gov.cn` 同路径 ⇒ **200，且含整部法全文**（`div.arc_cont`）。
页面自带**效力标识** `span.xg`（`全文有效`/`全文废止`/`已修改`/`全文失效`）+ 成文日期。

> ★ 只认 `span.xg`：正文里出现「尚未生效」等词**不是**效力标识（实测《行政复议法实施条例》
> 第五十七条正文含该词）——全文关键词判效力会误判。

### 三道闸（任一不过 ⇒ **整体不入库**，并写入台账）
| 闸 | 判据 | 不过的处置 |
|---|---|---|
| A | 页面效力标识 == `全文有效` | `全文废止`/`全文失效`/`已修改`/缺失 ⇒ **不入库**（不拿旧版文本顶替现行文本） |
| B | 与 `config/legal_versions.json` 交叉核实（`status ∈ {expired, superseded}` ⇒ 不入库） | 两者不一致 ⇒ 记 `version_conflicts` 待人工裁定（本轮 **0** 条） |
| C | 能切出「第X条」条文 | 公布令/决定类（无条文）⇒ 记 `no_article`，如实列出 |

### 实测结果
```
扫描 140 部｜入库 101 部（新增条文 6878）｜未入库 29 部｜切不出条文 10 部
页面效力标识分布：全文有效 111 / 全文废止 24 / 已修改 3 / 全文失效 1
```
**24 部「全文废止」被拦下**，含《增值税暂行条例》《印花税暂行条例》《进出口关税条例》
《企业所得税暂行条例》《车辆购置税暂行条例》《耕地占用税暂行条例》等 ——
这些正是**最容易被误引**的旧文本（项目铁律：引用已废止条文比缺条文更危险）。

### 切分纪律（两条实测教训）
1. **条号前置断言**：`第X条` 前面必须不是汉字 ⇒ 否则《增值税法实施条例》第二条里的
   「**增值税法第三条**所称货物…」会被当成条文起点，把上一条切碎。
2. **严格递增才拆行内**：紧凑排版（整部法挤在一行）需要行内切分，但必须要求
   "首个条号 = 上一条 + 1 且递增"，否则「第十一条　依照本法第二条规定…」会被误拆。

---

## 三、② 材料条款级：只认「法名紧邻条号」+ ID 必已登记

### 为什么此前只能到法规级
摘要（`snippet`）通常不写条号 ⇒ 原 `granularity_note` 的原话：
「是否指向具体条款，摘要未写明 ⇒ 条款级留空待人工，不猜」。补采正文后才有依据。

### 判定纪律（与法规级同样严）
- **只认「法名 + 紧跟条号」的相邻共现**（中间仅允许空白与书名号收尾符 `》` 等）；
- **不做**"全文任意条号就近配对"——材料常在同一段并列引多部法，就近配对必然错配；
- 产出的条款 ID 必须**在 `config/legal_provisions.json` 中真实存在**
  （不在库中时保留关联但标 `in_library=false`，如实暴露"有引用无正文"）。

### 实测结果
```
材料 2055 条｜关联到法规 994 条｜关联到**条款** 193 条（正文已采 748 条时点）
粒度三态：provision 193 / law 801 / none 1061
```
例：`TAX-ADMIN-LAW-063`（《税收征管法》第六十三条·偷税）被 **112 条官方案例**条款级引用
（`for_provision` 直出，不再退回法规级）。

### 读层升级（两级优先，不再一律说"只到法规级"）
- `for_provision(条款ID)`：① 先取条款级命中（`granularity=provision`）；
  ② 无命中 ⇒ **如实退回**法规级并标 `granularity=law`；
- `engine/risk_service._related_materials`（风险详情"相关官方材料"）**同步升级**为两级优先；
- `list_materials` 新增 `granularity` / `provision_id` 筛选；
- `material_detail` 新增**正文**（从 `data/legal_crawl/material_texts/` 读，不塞进 `config/`）。

---

## 四、③ 阈值参数化：一处登记，多处消费

### 为什么必须做（实测多头维护）
同一批**法定扣除限额**此前**两处各写一份**：
- `engine/verified_rule_engine.py`：VR038 `min(occ*0.6, rev*0.005)`、VR039 `rev*0.15`、VR040 `wage*0.14`；
- `engine/deduction_limit_detector.py`：`_UNION_RATE=0.02`、`_EDU_RATE=0.08`、
  `_DONATION_RATE=0.12`、`_DEBT_EQUITY_RATIO=2.0`。

⇒ 法定比例一旦调整，必须记得改齐所有副本，漏一处即"同一条规则两个答案"。

### 收敛方案
- 表：`config/rule_params.json`（**11 个参数**，按**参数名**登记，不按规则 ID
  ⇒ 同一阈值被多条规则共用时只登记一次，如债资比 2:1 服务 `RL-CIT-009/010/014`）；
- 读层：`engine/rule_params.py`（唯一读取入口；**取不到 ⇒ `None`，绝不兜底为 0**）；
- 三个**法定比例也进入规格描述**（`VR038/039/040.limitation`）⇒ 改表值文案同步变，
  避免"判定读表、文案仍写死"的分叉。

### 如实标注未接入的 3 条
`engine_wired=false` + `not_wired_reason`：亏损结转 5 年（`loss_carryforward_years`）、
分红个税 20%（`dividend_iit_rate`）、委托研发 80%（`entrusted_rd_deduction_ratio`）
—— 引擎暂无对应可复算数据源（需连续年度申报表 / 个税代扣台账 / 委托研发专项归集），
**不虚构检测器**。

---

## 五、★ 意外发现并修掉的既有缺陷（本轮最大收获）

### 缺陷 1：中文数字解析有 **5 处私有实现**，能力还不一致
| 位置 | 范围 | 后果 |
|---|---|---|
| `_gen_legal_index.py::cn2num` | 个位/十/几十 | **「第一百零三条」解析不出** |
| `_gen_legal_mappings.py::cn2num` | 同上 | 可确证的条款映射被误判为不可确证 |
| `_load_legal_texts_full.py::_cn_to_int` | 含百/千 | （本轮新增，行为正确） |
| `engine/quality_gates.py::_cn_num` | 一~二十 | 待收敛（质量闸门域，本轮未动） |
| `engine/enterprise_report.py::_cn_num` | **int→中文**（反向） | 方向相反，仅同名 |

**实测后果**：整部法全文入库后，条款索引 **1806 条拿不到 `provision_id`**
（全是第一百条以上，如《企业所得税法实施条例》第一百条~第一百三十条）
—— 不是数据缺失，而是**解析器能力不足**被当成"解析不出"如实暴露。

**收敛**：新建 `engine/cnnum.py`（唯一权威），三处脚本改为引用。
**结果：1806 → 1**（剩 1 条是既有特例「公告2014年第39号 正文」）。

### 缺陷 2：条号排序键错乱（收敛过程中暴露）
旧排序键在**无「之N」时不乘 100**：`第十五条`→15、`第十五条之一`→1501
⇒「**第十六条**」(16) 竟**小于** 1501，被切分器判为"续行"而**吞掉条号**。

**修复后正文库再增 440 条**（6569 → 7009）。

### 缺陷 3：覆盖率闸门的**浮点精度口径不对齐**（假 ERROR）
登记值由录入器 `round(_, 4)` 写入，闸门现算却是未截断的原始浮点
⇒ 同一份数据也判"退化"（241/242：登记 `0.9959` vs 现算 `0.99586776…`）。
已改为**现算同精度取整后比较**，并反向验证"真退化仍必须变红"。

---

## 六、闸门与反向验证（本轮新增 3 道）

| 闸门 | 判据 | 反向验证 |
|---|---|---|
| `check_rule_params_single_source` | A 表结构完备 / B 不得与地区参数表重名 / C 未接入须写理由 / D 声称已接入必须真引用（文件里能找到参数名） | `_verify_rule_params_gate_reverse.py`：缺字段 / 跨表重名 / 假接入 ⇒ 三段全变红 |
| `check_cnnum_single_source` | A 全仓不得再出现中文数字对照表（白名单 2 处）/ B 行为级断言 + **条号排序键严格递增** | `_verify_cnnum_gate_reverse.py`：新增私有实现 / 破坏「百」位 / 排序键退回旧写法 ⇒ 三段全变红 |
| `check_material_granularity_truthful` | A 三态自洽 / B ID 形状合法且法短码已登记 / C **依据可复核**（正文真含「法名紧邻该条号」，抽样 60）/ D 三态必填 | `_verify_material_granularity_gate_reverse.py`：假条款级 / 非法 ID / 依据不成立 / 两表脱同步 ⇒ 四段全变红 |

> ★ 反向验证**必须子进程逐轮**：闸门读的是运行期已导入的模块，同进程内改文件会命中
> Python 模块缓存（首版测试方法错，误判"闸门失效"）。另有 1 处**判据自身的名字错误**
> （模块级函数里误用局部别名 `_re` ⇒ `NameError` 被 `except` 吞成 `False`，误报 60 条假 ERROR）
> —— 判据自己的 bug 比数据错误更难发现。

---

## 七、验收（可复现命令）

```bash
# 采集与入库
./.venv/Scripts/python.exe scripts/_crawl_legal_texts.py          # 法律/行政法规全文（140 部）
./.venv/Scripts/python.exe scripts/_crawl_material_texts.py       # 材料正文（2055 条）
./.venv/Scripts/python.exe scripts/_extend_law_codes.py           # 补 70 部法短码
./.venv/Scripts/python.exe scripts/_load_legal_texts_full.py      # 切分入库（含时效核实）
./.venv/Scripts/python.exe scripts/_gen_legal_index.py            # 条款索引
./.venv/Scripts/python.exe scripts/_gen_legal_mappings.py         # 规则⇄条款映射
./.venv/Scripts/python.exe scripts/_gen_legal_materials.py        # 材料关联（含条款级）
./.venv/Scripts/python.exe scripts/_load_legal_texts.py           # 覆盖率登记（现算）

# 反向验证（必须全 PASS）
./.venv/Scripts/python.exe scripts/_verify_rule_params_reverse.py
./.venv/Scripts/python.exe scripts/_verify_rule_params_gate_reverse.py
./.venv/Scripts/python.exe scripts/_verify_cnnum_gate_reverse.py
./.venv/Scripts/python.exe scripts/_verify_material_granularity_gate_reverse.py

# 闸门与测试
./.venv/Scripts/python.exe tools/audit_consistency.py
./.venv/Scripts/python.exe -m pytest tests/test_legal_mapping.py tests/test_legal_topics.py -q
```

---

## 八、残留（如实）

1. **条文本体仍非 100%**：正文库覆盖 101 部法；目录 7121 条中其余为**规范性文件/公告**，
   未逐条入正文（体量与核实成本）。这是"候选 ≠ 已核实"的正常状态，**不编造**。
2. **19 处「正文冲突」**：采集版与既有**人工录入版**实质不同（多为人工版省略了列举项编号），
   **保留人工版**并记入 `content_conflicts` 待人工核对，不自动覆盖。
3. **1 处 `in_library=false`**：材料条款级引用（`CIT-VOUCHER-MEASURE-012`）对应条文未入正文库
   —— 关联保留、正文缺失，**如实标注**。
4. **3 个阈值参数未接引擎**（亏损 5 年 / 分红个税 20% / 委托研发 80%）—— 缺数据源，如实标注。
5. **既有审计 ERROR 3 项**（`seq17` 已有/要补自相矛盾、跨章节重复模板句、`/extract` 孤岛页）
   **非本轮引入**，未处理。
6. `engine/quality_gates.py::_cn_num` 与 `engine/enterprise_report.py::_cn_num`
   属既有实现（前者待收敛，后者方向相反），本轮**未动**以免波及闸门行为，已在闸门白名单登记。
