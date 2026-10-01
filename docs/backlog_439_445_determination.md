# 存量 backlog #439–#445 逐条判定报告

> 生成时间：2026-10-01（窗口末）
> 判定原则：**先核实状态/代码是否真的落地，不无脑重做**；「代码已落地待闸门/状态收敛」与「真缺口」必须区分开。
> 所有判定均附可复现证据（命令 + 实测输出）。

---

## 一、总览

| 编号 | 标题 | 判定 | 依据 |
|---|---|---|---|
| #439 | COUNT 陈旧数改为权威值 | **已落地**（状态收敛） | 提交 `0ab1bf30`；全库扫描生产文件无残留 |
| #440 | COUNT 阈值/采样/局部层 + 历史日志登记豁免 | **已落地**（状态收敛） | `COUNT_SKIP_FILES` + `COUNT_EXEMPT_CONTEXTS` 已含对应条目 |
| #441 | doc_type_to_category 漏补充识别 doc_type | **已落地**（状态收敛） | `check_doc_type_category_map()` 实测 `issues: 0` |
| #442 | 跨模块同名私有函数登记豁免 | **已落地**（状态收敛） | `KNOWN_VALID_DOCS` 同名豁免已登记 |
| #443 | 红线引用带「中华人民共和国」全称法规补登 | **已落地**（状态收敛） | `KNOWN_VALID_DOCS` 已补登全称法规 |
| #444 | 40 条盲区红线登记豁免 | **已落地**（状态收敛） | 盲区豁免已登记 |
| #445 | 重跑三闸 + 反向验证 + 生成逐条判定报告 + 提交 | **本轮完成** | 见第三节 |

> **关键结论**：#439–#444 六条在提交 `0ab1bf30`「fix(audit): 收敛审计闸门 27 项 WARN」中已全部实现，
> 本轮做的是**状态收敛 + 反向验证复核**，不是重做。

---

## 二、逐条判定（#439–#444）

### #439 COUNT 陈旧数改为权威值 —— 已落地

- **scope**：items 1, 3, 4, 7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 20
- **现状核查**：全库搜索历史值 `分析链19` / `线索链40` / `证据链20` / `红线68` / `规则20` / `68 条红线` 等字符串。
  生产文件（`engine/coordinator.py`、`engine/enterprise_report.py`、`memory.py`、`redline_benchmark.py`、
  `static/methodology_canonical_catalog.json`、`system_directory.json`、`tests/test_redline_methodology.py`、`
  executive_brief.py`）**已无残留**。
- **命中但不在扫描口径**（不属缺陷）：旧记忆文件、一次性诊断脚本、`tax_agi_override.json` 中的历史值。
- **判定**：改为 completed。

### #440 COUNT 豁免登记 —— 已落地

- **scope**：items 2, 5, 6, 15
- **实现位置**：`tools/audit_consistency.py`
  - `COUNT_SKIP_FILES`（line 117–122）已含 `static/js/rewrite_steps.py`、**`static/module_auto_update_log.json`**（item 15 的历史日志豁免）；
  - `COUNT_EXEMPT_CONTEXTS`（line 128–132）已含三个正则：阈值（`≥N 条规则`）、采样（`采样前 N 条规则`）、局部层（`原来 N 条规则外`），对应 items 2/5/6。
- **判定**：改为 completed。

### #441 doc_type_to_category 漏补充识别 doc_type —— 已落地

- **scope**：item 21
- **实现位置**：`check_doc_type_category_map`（`tools/audit_consistency.py` line 394）
  - line 443–447 已把 `material_recognition._SUPPLEMENTARY_RECOGNITION` 的 `doc_type` 并入合法键集；
  - line 448 的 `suspicious = sorted(mapped - real_types - _DOC_TYPE_ALIAS_KEYS - _sup_doc_types)` 已完成漂移扣除。
- **实测**：
  ```
  tools.audit_consistency.check_doc_type_category_map()  ->  issues: 0
  ```
- **判定**：改为 completed。

### #442 跨模块同名私有函数登记豁免 —— 已落地

- **scope**：item 22
- `KNOWN_VALID_DOCS` 中已登记同名私有函数豁免（`grep` 命中 5 处相关登记）。
- **判定**：改为 completed。

### #443 红线引用带「中华人民共和国」全称法规补登 —— 已落地

- **scope**：items 23–26
- `KNOWN_VALID_DOCS` 已补登带全称的法条（「中华人民共和国」关键字命中 23 处）。
- **判定**：改为 completed。

### #444 40 条盲区红线登记豁免 —— 已落地

- **scope**：item 27
- 盲区红线豁免已登记（`盲区` 关键字在 `audit_consistency.py` 命中 20 处）。
- **判定**：改为 completed。

---

## 三、#445 收口证据（本轮实测）

### 3.1 反向验证：豁免登记必须「精准」而非「放宽」

脚本 `scripts/_rev_validate_exemptions.py` 的四项验证（故意破坏 → 必须仍报错 / 不破坏 → 必须不报错）：

```
[PASS] A-COUNT豁免精准（阈值/采样/局部层表述不算陈旧数）
[PASS] B-doc_type修复精准（真实类型与补充识别 doc_type 均合法，拼错键仍报错）
[PASS] C-盲区红线豁免精准（新盲区红线仍报错）
[PASS] D-分歧豁免精准（新同名分歧仍报错）
ALL PASS = True
```

> 这条反向验证的意义：证明 #440/#442/#444 的豁免登记**不是靠放宽阈值把 WARN 抹平**，而是精准命中既有合法表述，
> 换个写法/新增同类问题仍会被闸门抓出来。

### 3.2 三闸 + 发布闸门

| 闸门 | 结果 | 证据 |
|---|---|---|
| `tools/verify_release.py` | **All release checks passed**（rc=0，37 项 PASS） | 含 `count constants and law references are consistent (0 error(s))` |
| `tools/audit_consistency.py` | **ERROR 0 项 \| WARN 0 项** | 权威值：rules 89 / clue_paths 38 / evidence_plans 25 / analysis_plans 25 / modules 25 / redlines 91 / verified_rules 73 |
| `pytest tests/` | **804 passed / 166 subtests passed**（46.60s） | 基线 798 + 本轮 6 条新测试 |
| `scripts/_audit_redline_coverage.py` | 红线 **91** / 有真实检测器 **81** / 仅兜底 10 / 盲区 **0** | 检测器仅存于 `scripts/` 的剩 2 条 |

> 注：审计「文本维度」另打印 18 条信息性 `⚠`（10 个历史 `text_sync` 块 + 8 条「关联模块文件不存在」），
> 属历史共享内容未迁移，不计入 WARN/ERROR，也不阻断发布（发布闸门 `verify_release` 已含该项且通过）。

### 3.3 红线覆盖度（①能力核心指标）

- 红线总数 **91**，其中带真实生产检测器 **81**（本轮 80→81，新增 RL-SPT-012 专用探测器），仅兜底 **10**，盲区 **0**。
- 检测器仅落在 `scripts/`（一次性诊断脚本，不算生产检测器来源）的红线：`RL-SPT-013`、`RL-VAT-012`。

---

## 四、本轮一并完成的收尾：RL-SPT-012（ prior 窗口发现，本轮落地）

| 项 | 内容 |
|---|---|
| 问题 | 11 条「有信号未触发」里，仅 **RL-SPT-012（股权转让未申报个税）** 是真缺口 |
| 落地 | `engine/special_redline_detectors.py` 新增 `_EXTRA_DETECTORS` 专用探测器通道；`redline_id = "RL-SPT-012"` 先赋值再传参（使覆盖审计 `_scan_ids` 能认领） |
| 口径 | 完税凭证反证：判定 `tax_declarations` 拼进 `pay_text`；**只报记录条数、不报金额、不做税额试算**（缺资料 ≠ 已认定未申报） |
| 验收 | 单元 11 passed；反向验证 **5/5 破坏即红**（C1 探测器未接 / C2 完税凭证未抑制 / C3 redline_id 缺失 / C4 信号未命中 / C5 把手续费当金额报出） |

---

## 五、遗留与下一步

### 5.1 未解决（非本轮缺陷）

- `tools/audit_consistency.py` 文本维度 WARN 存量（历史 `text_sync` 块 + 「关联模块文件不存在」），非数字维度，不阻断发布。
- `data/uploads/9999/` 临时账套被 safe-delete 守护按轮累计拦下，需手工删除（勿删 1/2/3/9992~9998）。

### 5.2 后续 backlog（按价值排序）

1. **#341–#345**「有什么查什么」宗旨 + 工资社保单向可查（`engine/audit_doctrine.py` 与 `_domain_salary_ss_hf_compare` 三分支均已落地，待补闸门/收口）
2. **#461** 扫新税种 / 风险域
3. **#395–#397** 章首主线研判 / 解除去模板化 / 验证
4. **#406–#409** plain_language 转换层接线
5. **#243–#251** 旧 methodology/scenario 文件删除状态收敛
6. 状态混乱项收敛（本轮已处理 10 个 cancelled 却仍标 in_progress 的任务）
