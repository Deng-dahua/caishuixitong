# Skill 化补充 · 5 个 Skill 回归测试报告

> 命令与结果均为**实测**

## 1. 全量回归

```bash
./.venv/Scripts/python.exe -m pytest tests/ -q
# 实测：1914 passed, 4 skipped, 166 subtests passed（耗时随机器负载浮动，不单列；以「与本次 passed 同次运行」为准）
```
（本批主体 28 例 + 文档一致性 59 例已包含在内）

## 2. 5 个门禁（对**真实交付物**）

| 门禁 | ERROR | WARN |
|---|---|---|
| `check_doc_number_authority()` | **0** | 0 |
| `check_rule_reference_sync()` | **0** | 0 |
| `check_doc_residue_scan()` | **0** | 0 |
| `check_todo_status_sync()` | **0** | 0 |
| `check_doc_ref_graph()` | **0** | 0 |

## 3. Skill 注册表

```bash
./.venv/Scripts/python.exe -c "import sys,json; sys.path.insert(0,'.'); from engine import skill_registry as SR; print(SR.validate())"
# 实测：[]（合规）｜ Skill 总数 61
```

## 4. 用例分类（`@pytest.mark` **现算**）：反向验证（`test_reverse_*`）**19 例** + 破坏性用例（`test_break_*`）**7 例** + 口径锁（`test_lock_*`）**8 例** = 验证类 **34 例**

| # | Skill | 构造 | 期望 | 实际 |
|---|---|---|---|---|
| 1 | D1 | 「前提条数 69」→ 68 | ERROR | ✅ |
| 2 | D2 | `rule_catalog` 加 `TDS-⑩`、不更新 02 | ERROR | ✅ |
| 3 | D2 | 文档写不存在的「TDS-⑩」 | ERROR | ✅ |
| 4 | D3 | 文档写入「1421 通过」 | ERROR | ✅ |
| 5 | D4 | U1 改回「不阻断」+ 补做记录写「已修复」 | ERROR | ✅ |
| 6 | D5 | 改坏下游数字（28→25） | ERROR | ✅ |
| 7 | **D0** | `config/doc_consistency.json` **JSON 非法** | D1/D2/D4/D5 四条 ERROR | ✅ 全红 |
| 8 | **D0** | 表合法但**缺必需键**（空表） | 四条 ERROR | ✅ 全红 |
| 9 | **D0** | `config/doc_synonyms.json` 缺 `stale_values` | D3 ERROR | ✅ |
| 10 | **D1** | `01` §6 分项加总改成 31（合计 28） | ERROR（分项加总 ≠ 合计） | ✅ |
| 11 | **D1** | `02` 门禁调用行号改回 11123 | ERROR（行号 ≠ grep 实测） | ✅ |
| 12 | **D4** | 删掉「状态同步声明」标记行 | ERROR（判据无法执行） | ✅ |
| 13 | **D4** | 在 08 里加解释性散文（含旧状态字样） | **不得报错**（散文≠声明） | ✅ |
| 14 | **D3** | **围栏外**写旧值 `1421 passed` | ERROR | ✅ |
| 15 | **D3** | **围栏内**（引用区）写旧值 | **不得报错** | ✅ |

> 第 7~9 例来源：本批收口时**真发生**过一次假绿 —— `config/doc_consistency.json` 因一处半角引号导致
> JSON 非法，5 个门禁**全部报 0 项问题**。故新增 D0 健康闸门（详见 `5个Skill门禁规则.md` §2.1），
> 并对**真文件**做了端到端反向验证（改真文件 → 跑 → 还原，见 `R1_修正记录.md` 附条 12）。

## 5. 失败项

**全量 0 失败**（`1914 passed`）。
过程中**被这 5 个 Skill 自己抓出并修掉**的问题（诚实记录）：

| # | 被抓出的问题 | 抓它的 Skill | 修法 |
|---|---|---|---|
| 1 | `02:140`「8 条规则」 | D1 + D3 | 改 9 条 |
| 2 | `01` §6 合计「25 passed」 | D3（人工 grep「25 例」**漏了**这个写法） | 改 28 passed |
| 3 | `06` 规则清单「TDS-①~⑧」 | D2 + D1 | 改 ①~⑨（共 9 条） |
| 4 | `02 §3` 规则表缺 `TDS-⑨` | D2 | 补一行 |
| 5 | `08` U 表无状态列；U1 挂「未完成」 | D4 | 加状态列、U1=已修复、新增 U8=待决策 |
| 6 | `05:23`「55.94s」被写成单值 | D3（区间判据收窄后） | 改为"与本次 passed 同次运行" + 区间写法 |
| 7 | 新增的这 7 份 Skill 化文档引用旧值触发 D3 假红 | D3 自测 | 登记 `quote_files` / `exclude_files`（**证明"先量化再收窄"**） |

---

**本项是否满足验收标准**：**满足**。① 全量回归命令与结果；② 5 个门禁逐项 ERROR/WARN；
③ 注册表校验；④ 用例分类（现算）：反向验证 **19 例** + 破坏性用例（`test_break_*`）**7 例** + 口径锁（`test_lock_*`）**8 例** = 验证类 **34 例**；正例/自证 **25 例**；全量用例 **59 例**
## 6. 全量闸门与新增 WARN（**如实记录**）

```bash
./.venv/Scripts/python.exe tools/audit_consistency.py
# 实测：ERROR 0 项 | WARN 3 项（Skill 化之前为 WARN 1 项）
```

新增的 2 条 WARN **全部指向本批新增的 5 个模块**，属**既有闸门对新代码的例行提示**：

| WARN | 来源闸门 | 内容 | 处置 |
|---|---|---|---|
| 1 | `check_no_vague_wording` 类（词频） | `engine/doc_residue_scan.py` / `tests/test_doc_consistency_skills.py`：「规则」文中 8 ≠ 权威 89 | **接受**：这两份文件里"规则"是**文档一致性规则**（D1-R1…），与红线规则数（89）无关，属同词不同义 |
| 2 | `check_duplicate_definitions` | `engine/` 仍有 12 组跨模块同名：`audit / load_config / entry_of / canonical_name / reload_config / affected_downstream / _index / _grams / audit_product / problem_key` | **接受**：`audit()` 是 5 个 Skill 的**统一入口名**（设计如此）；其余多为**既有同名**（非本批引入）；共享核心 `doc_consistency_core` 已收敛取数与比对逻辑 |

> 口径：这 2 条是 **WARN 不是 ERROR**（不阻断），且**不是缺陷**（同词不同义 / 统一入口名）。
> 若你要求 WARN 归零，可选：(a) 把 5 个 `audit()` 改名为各自专属名（如 `audit_d1()`）；(b) 给词频闸门加白名单。
> **本批不做**（属既有闸门的口径微调），已列入 `08_未完成事项清单.md` 的 U9。
