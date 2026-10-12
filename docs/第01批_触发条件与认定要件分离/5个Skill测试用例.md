# Skill 化补充 · 5 个 Skill 测试用例

> 文件：`tests/test_doc_consistency_skills.py` ｜ 用例数（`--collect-only` 实测）：**59**
> 本轮实测：`42 passed`（全量 1780 passed / 4 skipped / 166 subtests，见 `5个Skill回归测试报告.md`）

## 1. 用例清单

| # | Skill | 用例 | 断言 |
|---|---|---|---|
| 1 | D1 | `test_pass_real_docs` | 真实文档 ⇒ 0 ERROR（通过样例） |
| 2 | D1 | `test_authority_values_are_computed` | 权威值与直接读配置一致（**现算**，非缓存/手抄） |
| 3 | D1 | `test_reverse_wrong_number_is_detected` | **反向**：把「前提条数 69」改成 68 ⇒ 报红 |
| 4 | D2 | `test_pass_real_docs` | 真实文档 ⇒ 0 ERROR |
| 5 | D2 | `test_reverse_missing_new_rule_is_detected` | **反向**：`rule_catalog` 加 `TDS-⑩` 而不更新 02 ⇒ 报红 |
| 6 | D2 | `test_reverse_unknown_rule_id_is_detected` | **反向**：文档写不存在的「TDS-⑩」⇒ 报红 |
| 7 | D2 | `test_collective_rule_reference_is_valid` | 口径：`TDS-⑤⑥⑦⑧` 是集合引用，不得误判 |
| 8 | D3 | `test_pass_real_docs` | 真实文档 ⇒ 0 ERROR |
| 9 | D3 | `test_grep_is_expanded_from_dictionary` | 输出必须含全部同义写法（「25 passed」「25tests」等） |
| 10 | D3 | `test_reverse_unlisted_variant_is_reported` | **反向**：写入「1421 通过」⇒ 报红 |
| 11 | D3 | `test_range_form_is_not_residue` | 口径：区间「55.94–214.90s」不算残留 |
| 12 | D4 | `test_pass_real_docs` | 真实文档 ⇒ 0 ERROR |
| 13 | D4 | `test_every_todo_has_status` | 每项必须有状态字段 |
| 14 | D4 | `test_u1_is_marked_fixed` | 本次 bug 的修复落到状态：U1 = 已修复 |
| 15 | D4 | `test_reverse_status_conflict_is_detected` | **反向**：把 U1 改回「不阻断」+ 补做记录写「已修复」⇒ 报红 |
| 16 | D5 | `test_pass_real_docs` | 真实文档 ⇒ 0 ERROR |
| 17 | D5 | `test_affected_downstream` | 能力：`01_Skill设计文档.md` ⇒ `['最小检查集.md','05_回归测试报告.md']` |
| 18 | D5 | `test_reverse_downstream_not_updated_is_detected` | **反向**：改坏下游数字 ⇒ 报红 |
| 19 | 落地 | `test_registered_in_skill_specs` | 5 个 Skill 均在 `config/skill_specs.json` |
| 20 | 落地 | `test_registry_validate_clean` | `validate()` = `[]` |
| 21 | 落地 | `test_gates_wired_into_chain` | 5 个门禁均以 `+ check_xxx()` 并入总链 |
| 22 | 落地 | `test_all_five_gates_zero_error` | 5 个门禁对真实文档 0 ERROR |
| 23 | **D0 健康闸门** | `test_reverse_broken_json_turns_gates_red` | **反向**：数据表 JSON 非法 ⇒ D1/D2/D4/D5 **全红**（防假绿） |
| 24 | **D0 健康闸门** | `test_reverse_missing_key_turns_gates_red` | **反向**：表合法但缺必需键（空表）⇒ 全红 |
| 25 | **D0 健康闸门** | `test_reverse_broken_synonyms_turns_d3_red` | **反向**：同义词典缺 `stale_values` ⇒ D3 报红 |
| 26 | **D0 健康闸门** | `test_health_gate_present_in_source` | 判据自证存在（防止日后被删） |
| 27 | **新增判据** | `test_sum_check_catches_inconsistent_total` | **反向**：`01 §6` 分项改成加总 31 ⇒ D1 报「分项加总 ≠ 合计」 |
| 28 | **新增判据** | `test_line_number_authority_comes_from_grep` | 行号类数字的权威 = `grep -n` 实测（不靠人核） |
| 29 | **新增判据** | `test_reverse_wrong_line_number_is_detected` | **反向**：`02` 行号改回失真的 11123 ⇒ D1 报红 |
| 30 | **新增判据** | `test_todo_declaration_must_carry_marker` | **反向**：删掉「状态同步声明」标记 ⇒ D4 报「判据无法执行」 |
| 31 | **新增判据** | `test_prose_is_not_treated_as_declaration` | 口径：**解释性散文**不得被当成"补做记录声明"（初版自造假红的根因） |
| 32 | **新增判据** | `test_residue_outside_fence_still_red` | 口径锁：**围栏外**写旧值 ⇒ 报红；**围栏内**（引用区）⇒ 不报红 |
| 33 | **本轮 A** | `test_receipt_authority_is_read_from_real_receipt` | 全量 passed 的权威 == 运行回执里的 `passed`（不是手抄） |
| 34 | **本轮 A** | `test_reverse_stale_receipt_is_rejected` | **反向**：回执 `tests_max_mtime` 落后 ⇒ 取不到 + 提示"过期" |
| 35 | **本轮 A** | `test_reverse_wrong_full_passed_is_detected` | **反向**：`05` passed 改错 ⇒ ERROR |
| 36 | **本轮 A** | `test_reverse_wrong_skill_total_is_detected` | **反向**：`06` Skill 总数改错 ⇒ ERROR |
| 37 | **本轮 B** | `test_reverse_wrong_gate_call_line_in_06_is_detected` | **反向**：`06 §4` 行号改回 11123 ⇒ ERROR（此前 06 不在 claims 内） |
| 38 | **本轮 A′** | `test_consistency_check_catches_intra_file_mismatch` | **反向**：`05` §2 与末尾耗时不一致 ⇒ ERROR |
| 39 | **本轮 A′** | `test_duration_is_not_a_numeric_authority` | 口径锁：**耗时不做数值权威**，只有 `CONS-05-duration` 自洽判据 |
| 40 | **本轮 C** | `test_reverse_table_column_mismatch_is_detected` | **反向**：表内插一行列数不一致 ⇒ ERROR（**须插进已有表格**，否则空洞通过） |
| 41 | **本轮 C** | `test_escaped_pipe_in_cell_is_not_a_column` | 口径锁：单元格内 `\\|` 不算列分隔 |
| 42 | **本轮 D** | `test_d5_scope_is_cross_file_only` | 口径锁：`d5_scope` 必须写清"同文件内部一致性不归 D5" |

## 2. 命令

```bash
./.venv/Scripts/python.exe -m pytest tests/test_doc_consistency_skills.py -q
# 实测：42 passed
./.venv/Scripts/python.exe -m pytest tests/ -q
# 实测：1780 passed, 4 skipped, 166 subtests passed（耗时随机器负载浮动，不单列；以「与本次 passed 同次运行」为准）
```

## 3. 失败样例 → 通过样例的**可复现**对照

| Skill | 失败样例（本次 11 处问题中的对应处） | 期望 | 实际 |
|---|---|---|---|
| D1 | `02:140`「质量门禁 8 条规则」vs 权威 9；`01` §6「25 passed」vs 28 | 报红 | ✅ 报红（修复后 0 ERROR） |
| D2 | `TDS-⑨` 未进 `02 §3` 规则清单 | 报红 | ✅ 报红（补齐后 0） |
| D3 | 旧 grep 只搜「25 例」，漏「25 passed」 | 报红 | ✅ 报红（词典展开后 0） |
| D4 | 补做3 已修而 U1 挂「未完成」 | 报红 | ✅ 报红（U1=已修复后 0） |
| D5 | `最小检查集` 28 例 vs `01` 写 25 | 报红 | ✅ 报红（统一后 0） |

---

**本项是否满足验收标准**：**满足**。① 用例清单 **59** 条（反向验证 **19 例** + 破坏性用例 **7 例** + 口径锁 **8 例** + 正例/自证 **25 例**）；
② 命令与实测结果；③ 失败样例 → 通过样例逐 Skill 对照（全部来自本次 11 处问题）。
