# Skill 化补充 · 5 个文档一致性 Skill —— 设计文档

> 日期：2026-10-07 ｜ 批次：**第01批（Skill-1 触发条件与认定要件分离）· Skill 化补充**
> 依据：用户《第1批 Skill 化补充指令》—— 把"如何避免同类问题再次发生"抽象成 5 个 Skill
> 一句话结论：**5 个 Skill 已全部写入系统（配置 + 门禁 + 测试 + 自动应用），失败样例来自本次 11 处问题的实测。**

---

## 0. 架构：**一个核心 + 五个薄转发**（不重复实现）

5 个 Skill 要做的事只有三件：**(a) 取权威值**、**(b) 抽文档里写的值**、**(c) 比对并出清单**。
若各写一遍 ⇒ 就是本项目最忌的"同一概念 5 处实现、5 种判法"。故：

| 层 | 文件 | 职责 |
|---|---|---|
| **唯一核心** | `engine/doc_consistency_core.py` | 取权威值（9 种 kind）/ 抽文档值（正则声明）/ 同义展开 / 解析 U 表 / 遍历引用图；**5 个 Skill 的逻辑都在这里** |
| Skill D1 | `engine/doc_number_authority.py` | 薄转发 `check_numbers()` + 数据表键 `numbers` |
| Skill D2 | `engine/rule_reference_sync.py` | 薄转发 `check_rules()` + 数据表键 `rules` |
| Skill D3 | `engine/doc_residue_scan.py` | 薄转发 `check_residue()` + `expand_grep()`（展开同义写法）|
| Skill D4 | `engine/todo_status_sync.py` | 薄转发 `check_todo_status()` + `sync_status()` |
| Skill D5 | `engine/doc_ref_graph.py` | 薄转发 `check_ref_graph()` + `affected_downstream()` |
| 数据 | `config/doc_consistency.json` | 数字权威映射 / 规则清单 / 引用关系图 / 状态词表 |
| 数据 | `config/doc_synonyms.json` | 同义写法词典 + 扫描范围与对照文件排除 |

> 新增【一个数字 / 一条规则 / 一条引用边 / 一种旧值写法】= **加一行数据**，不改逻辑分支。

---

## 1. Skill D1 · 文档数字一致性

| 项 | 内容 |
|---|---|
| **职责** | ① 文档中每个数字必须有唯一权威来源；② 权威值必须**现算**（脚本/配置实测），不得手抄；③ 报告生成前校验「文档数字 == 权威值」；④ 不一致时**阻断生成** |
| **唯一权威映射**（数据表 `numbers[].authority.kind`） | `config_count` → `config/*.json` 实测 ｜ `pytest_collect` → `pytest --collect-only` ｜ `file_count` → `ls docs/第0X批/` ｜ `product_count` → 全量产物 ｜ `catalog_count` → 规则清单 |
| **输入** | 文档路径 + 数字位置（`claims[].file/regex`）+ 权威源（`authority`） |
| **输出** | 逐个数字的一致性结果 + 不一致清单（`[{level, where, detail}]`，`where` = `文件:行`） |
| **入口** | `engine.doc_number_authority.audit()` ｜ 门禁 `check_doc_number_authority()` |
| **本次失败样例** | `02:140`「质量门禁 **8** 条规则」vs 权威 **9**；`01` §6 合计「**25 passed**」vs **28**；`06`「TDS-①~⑧」vs 清单 **9** 条；`数字统一修订记录`「445 条」vs **456**（该文件为对照文件，已登记 `quote_files`） |
| **实测状态** | 修复后 **ERROR 0 / WARN 0**；反向验证：把「前提条数 69」改成 68 ⇒ 立刻报红 |

**已登记的数字权威（7 个）**：`rule_count`（门禁规则条数 9）｜`test_case_count`（28）｜`risk_count`（94）｜
`criterion_count`（456）｜`precondition_count`（69）｜`batch_doc_count`（交付物份数）｜`problem_count`（16）。

## 2. Skill D2 · 规则引用一致性

| 项 | 内容 |
|---|---|
| **职责** | ① 新增/修改一条门禁规则时，**自动扫描**所有引用该规则的文件；② 引用清单 = 规则清单 / 自证段 / 失败样例 / 通过样例 / 回归报告 / 最小检查集 / 修订记录；③ 任一引用处未同步 ⇒ **阻断生成** |
| **机制** | 每条规则有唯一编号（`TDS-①`…`TDS-⑨`，见 `rule_catalog`）；判据两条：**(a) 引用有效性**（文档里出现的编号必须已登记；**逐字符校验**，支持「TDS-⑤⑥⑦⑧」集合引用）**(b) 覆盖完整性**（`rule_catalog_files` 里的文件必须完整列出全部规则） |
| **输入** | 规则编号 + 规则变更内容（数据表 `rule_catalog` / `rule_catalog_files`） |
| **输出** | 引用清单（文件:行）+ 同步状态 |
| **入口** | `engine.rule_reference_sync.audit()` ｜ 门禁 `check_rule_reference_sync()` |
| **本次失败样例** | 新增 `TDS-⑨` 后 `02 §3 规则清单` 只到 TDS-⑧（**缺 ⑨**）⇒ 报 ERROR；`02:140`「8 条规则」 |
| **实测状态** | 修复后 **0 ERROR**；反向验证：① 往 `rule_catalog` 加 `TDS-⑩` 而不更新 02 ⇒ 报红；② 文档写「TDS-⑩」而清单里没有 ⇒ 报红 |

## 3. Skill D3 · 全文残留校验

| 项 | 内容 |
|---|---|
| **职责** | ① grep 关键词必须覆盖**所有可能写法**；② 建立**同义写法词典**；③ 检索时自动展开为全部变体；④ 词典未收录的写法 ⇒ 视为校验漏洞（WARN，要求补词典） |
| **词典示例（本批实登）** | 「25 例 / 25例 / 25 passed / 25passed / 25 tests / 25tests / 25 用例 / 25用例」｜「8 条规则 / 8条规则 / 8 条门禁 / 门禁 8 条」｜「55.94s / 55.94 秒 / 55.94」｜「445 条 / 445条」｜「TDS-①~⑧ / TDS-①～⑧」 |
| **输入** | 待校验旧值（`stale_values[].old`）+ 词典（`variants[]`）+ 扫描范围（`scan_scope`） |
| **输出** | **展开后的 grep 命令**（`expand_grep()`）+ 残留清单 |
| **入口** | `engine.doc_residue_scan.audit()` / `.expand_grep()` ｜ 门禁 `check_doc_residue_scan()` |
| **本次失败样例** | 旧 grep 只搜「25 例」⇒ **漏掉**「25 passed」（`01` §6 合计行正是此写法，我人工修订时也漏了，正是本 Skill 抓出来的） |
| **实测状态** | 修复后 **0 ERROR**；反向验证：在文档里写「1421 通过」⇒ 报红；**区间形态**（「55.94–214.90s」）**不算残留**（收窄后消除假红） |

## 4. Skill D4 · 未完成事项状态同步

| 项 | 内容 |
|---|---|
| **职责** | ① 未完成清单每项必须有**状态字段**；② 状态 ∈ `未开始/进行中/已修复/待决策/不阻断`；③ 补做完成后状态**自动同步**；④ 状态未同步 ⇒ **阻断生成** |
| **机制** | 每项唯一 ID（U1…Un）；「补做记录」写「U1 已修复」时，未完成清单里 U1 状态必须已是「已修复」（**双向一致**） |
| **输入** | 未完成清单（`08_未完成事项清单.md` 的 U 表）+ 补做记录 |
| **输出** | 状态同步结果 + 不一致清单；`sync_status(completed_ids)` 返回应改项 |
| **入口** | `engine.todo_status_sync.audit()` / `.sync_status()` ｜ 门禁 `check_todo_status_sync()` |
| **本次失败样例** | 补做3 已定性「系统 bug 并已修」，而 U1 仍挂「未完成」；且 U 表**根本没有状态列** |
| **实测状态** | 修复后 **0 ERROR**：U 表加「状态」列（U1=**已修复**、新增 U8=待决策）；反向验证：把 U1 改回「不阻断」而补做记录写「已修复」⇒ 报红 |

## 5. Skill D5 · 跨文件引用一致性

| 项 | 内容 |
|---|---|
| **职责** | ① 下游文件引用上游数据时必须**标注来源**；② 上游变更时自动列出**受影响的下游文件**；③ 下游未同步更新 ⇒ **阻断生成** |
| **机制** | `ref_graph` = `[{up, down[], numbers[]}]`；判据：该数字的 `claims` 必须覆盖每个 `down` 且**实际命中**（未写 = 未标注来源 = ERROR） |
| **输入** | 上游变更记录 + 文件引用关系图 |
| **输出** | 受影响下游清单（`affected_downstream(上游)`）+ 同步状态 |
| **入口** | `engine.doc_ref_graph.audit()` / `.affected_downstream()` ｜ 门禁 `check_doc_ref_graph()` |
| **本次失败样例** | `最小检查集` 说「28 例」而 `01 §6` 写「25」（两文件不同步） |
| **实测状态** | 修复后 **0 ERROR**；实测 `affected_downstream("01_Skill设计文档.md")` → `['最小检查集.md', '05_回归测试报告.md']`；反向验证：改坏下游数字 ⇒ 报红 |

---

## 6. 依赖与版本

| 项 | 值 |
|---|---|
| 5 个 Skill 版本 | 均 **1.0.0** |
| 共享核心 | `engine/doc_consistency_core.py` v**1.0.2**（**唯一实现**；不作为独立 Skill 登记。1.0.1 新增 `_guard()` 健康闸门 + 异常留痕；**1.0.2 新增 `check_consistency()` 同文件自洽、`check_tables()` 表格列数、`pytest_receipt`/`json_len` 两种权威 kind、`claims[].enforce` 逐条强制**） |
| 数据表 | `config/doc_consistency.json` v1.0.0 ｜ `config/doc_synonyms.json` v1.0.0 |
| 门禁 | `tools/audit_consistency.py` 新增 **5 个** `check_doc_*` 函数，全部并入总链 |
| 测试 | `tests/test_doc_consistency_skills.py`（**59 例**：22 例基础 + D0 健康闸门 4 例 + 判据扩充 6 例 + 最终修正轮 10 例 + **终极修正轮 10 例**）；另 `tests/conftest.py` 写全量运行回执 |
| 登记 | `config/skill_specs.json`：Skill 总数 **56 → 61**；`skill_registry.validate()` = **`[]`** |

---

**本项是否满足验收标准**：**满足**。① 5 个 Skill 均写入系统配置（§6 有 id/impl/entry_points）；
② 均增加门禁（§1~§5 各列门禁函数，且已并链）；③ 失败样例全部取自本次 11 处问题（逐 Skill 列明）；
④ 通过样例为修复后实测 0 ERROR；⑤ 回归与自动应用见《5 个 Skill 回归测试报告》《5 个 Skill 自动应用验证结果》。
