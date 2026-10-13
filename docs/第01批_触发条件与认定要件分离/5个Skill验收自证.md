# Skill 化补充 · 5 个 Skill 是否满足验收标准

> 用户验收 6 项 ｜ 日期：2026-10-07 ｜ 全部附**实际文件路径 / 命令 / 结果**

| # | 落地验收要求 | 证据（实际） | 判定 |
|---|---|---|---|
| 1 | 每个 Skill 必须**写入系统配置**，不得只输出文档 | `config/skill_specs.json` 新增 5 条（`doc_number_authority` / `rule_reference_sync` / `doc_residue_scan` / `todo_status_sync` / `doc_ref_graph`，各 version 1.0.0 + impl + entry_points）；数据表 `config/doc_consistency.json` + `config/doc_synonyms.json`；`engine.skill_registry.validate()` = **`[]`** | ✅ |
| 2 | 每个 Skill 必须**增加质量门禁**校验规则 | `tools/audit_consistency.py` 新增 **5 个** `check_doc_*` 函数（**25 条判据**），**全部并入总链 `run_checks()`**；对真实交付物实测 **ERROR 0 / WARN 0** | ✅ |
| 3 | 每个 Skill 必须用本次 **11 处问题**做失败样例 | 逐 Skill 对应（见 §失败样例映射）：D1←5 处数字 + 2 处 bug 的"配置有产物无"；D2←TDS-⑨ 未同步；D3←旧 grep 漏「25 passed」；D4←U1 状态未同步；D5←跨文件 28 vs 25 | ✅ |
| 4 | 每个 Skill 必须用**修复后**做通过样例 | 5 个门禁对真实文档 **0 ERROR**（`5个Skill门禁规则.md` §1 表）；`pytest tests/test_doc_consistency_skills.py -q` → **42 passed** | ✅ |
| 5 | 每个 Skill 必须**跑回归测试** | `pytest tests/ -q` → **1944 passed / 4 skipped / 166 subtests**（耗时随机器负载浮动，不单列；以「与本次 passed 同次运行」为准）；5 个门禁 0 ERROR；反向验证 **19 例**；破坏性用例 **7 例**；口径锁 **8 例**（验证类 **34 例**）成立 | ✅ |
| 6 | 每个 Skill 必须**支持下次分析自动应用** | ① 并入闸门总链（一键分析收尾即执行）；② **造新文档实测**：新落盘一篇含 `TDS-⑩` 的文档 ⇒ D2 立即报红，无需改代码；③ 换批次只需改 `doc_root` 一行 | ✅ |

## 失败样例映射（本次 11 处问题 → 5 个 Skill）

| 本次问题 | 归属 Skill |
|---|---|
| ① 测试用例数 25 vs 28 ｜ ② passed 1421 vs 1424 ｜ ③ 耗时 55.94 vs 62.04 ｜ ④ 认定要件 445 vs 456 ｜ ⑤ 前提条数遗漏 | **D1**（并由 **D3** 抓残留） |
| ⑥ 规则清单未含 `TDS-⑨` + 「8 条规则」 | **D2**（+ D1 抓条数） |
| ⑦ 旧 grep 只搜「25 例」漏「25 passed」 | **D3** |
| ⑧ U1 状态未同步 | **D4** |
| ⑨ 最小检查集 28 例 vs 01 写 25 | **D5** |
| ⑩ 综合疑点要件数=0（计算逻辑 bug） ｜ ⑪ 门禁缺"配置有产物必须有"判据 | Skill-1 主体（`trigger_conditions.classify()` + TDS-⑨），见 `R1_诊断报告.md`；**D1 的 `must_state_in` 与 D5 的引用图已把这类"配置有产物无"纳入可检** |

## 实测命令（可复现）

```bash
./.venv/Scripts/python.exe -m pytest tests/test_doc_consistency_skills.py -q   # 42 passed
./.venv/Scripts/python.exe -m pytest tests/ -q                                  # 1944 passed / 4 skipped
./.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'.'); from engine import skill_registry as SR; print(SR.validate())"   # []
```

---

**本项是否满足验收标准**：**满足**（6/6）。每项均附文件路径 / 命令 / 实测结果；
"11 处问题"逐处映射到具体 Skill；反向验证与自动应用均有实测。
