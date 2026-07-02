---
name: tax-risk-report
description: >
  财税系统税务风险分析报告生成技能。当需要生成税务风险分析报告、资料风险分析报告、
  涉税风险综合报告时使用。涵盖29域分析+312规则双引擎、文件解析分类修复、
  报告同类风险合并、综合报告增强（资金流向图/往来方TOP20/P0-P2建议）。
  Triggers: "出分析报告", "资料风险分析", "一键分析", "税险报告", "综合风险报告",
  "generate tax risk report".
agent_created: true
---

# 税务风险分析报告生成技能

## 核心架构

报告生成基于 FastAPI 后端 `main.py` 中的 `_run_analyze(company_id, db)` 函数，运行在 `http://localhost:8001` 的服务上。

### 三引擎分析架构

| 引擎 | 位置 | 说明 |
|------|------|------|
| 29域分析 | main.py `_domain_*` 函数 | 资金追踪/进销审查/供应商穿透/经营实质等29个域 |
| 312规则引擎 | tax_risk.py `get_tax_risk_report()` | 211条核心规则 + 101条扩展规则 |
| 跨域关联推理 | main.py `_domain_cross_domain_reasoning` | 多域证据链合成，虚开/隐匿收入等证据链 |

## 报告生成工作流

### Step 1: 确保数据就绪

```bash
# 检查上传文件
curl -s http://localhost:8001/api/tax-risk-docs/list?company_id=1

# 文件应位于
ls static/uploads/tax-risk-docs/
```

### Step 2: 触发分析（同步，约2-5分钟）

分析通过 `POST /api/tax-risk-docs/analyze?company_id=1` 触发，返回值含 `report` 对象。

```python
# 核心调用链
_run_analyze(company_id, db)
  ├── 扫描 UPLOAD_DIR 恢复文件列表
  ├── 逐文件解析 (_parse_excel_structured / _parse_pdf_bank_statement)
  │   ├── 关键词指纹 (_parse_by_content)
  │   ├── 结构分析 (_parse_by_structure_only)
  │   └── 交叉验证裁决
  ├── 分类汇总: bank_txs / invoices / salaries / vouchers / ...
  ├── 29域逐域分析 (_domain_*)
  ├── 312规则引擎 (get_tax_risk_report)
  ├── 依赖域 (规则覆盖验证 + 跨域关联推理)
  ├── 同类风险合并 (_merge_similar_findings)
  └── 返回报告JSON
```

### Step 3: 前端渲染

前端 `tax-doc-analysis.js` 的 `renderTaxDocReport(r)` 将 JSON 渲染为 HTML。

## 常见问题与修复

### 文件分类错误

**问题**: 销项发票被误判为进项发票
**原因**: `invoice_universal` 指纹得分（4+）覆盖了 `sales_invoice` 指纹得分（2），universal 默认解析为进项
**修复**: 在 `_parse_by_content()` 中添加优先级逻辑：当 `invoice_universal` 胜出且 `sales_invoice`/`purchase_invoice` 也达标时，优先具体类型

**问题**: 凭证被结构分析误判为银行流水
**原因**: 凭证和银行流水共享"借方金额""贷方金额""摘要"等列，结构分析 99% 置信度覆盖了关键词
**修复**: 在 `STRUCT_AMBIGUOUS_PAIRS` 中添加 `("voucher", "bank_statement")` 对

**问题**: 工资表被误判为公积金
**原因**: 简化工资表（5列）和公积金表结构完全相同
**修复**: 在 `STRUCT_AMBIGUOUS_PAIRS` 中添加 `("salary", "housing_fund")` 等对

### 同类风险合并

`_merge_similar_findings()` 函数按 `type` 分组，对同类型、同级、同分的发现合并。
当前支持"同城供应商群集"模式（正则: `.{2,4}地区集中\d+家`）。
新增合并模式时扩写 `_is_mergeable_city_group()` 和对应的合并函数。

### 数据充分性守卫

`total_parsed < 10` 时设置 `low_data_warning = True`，前端显示数据不足警告横幅。
`total_parsed == 0` 时直接返回 `ok: false`，拒绝生成报告。

## 关键文件索引

| 文件 | 功能 |
|------|------|
| `main.py` `_run_analyze` (~13637行) | 报告生成主函数 |
| `main.py` `_FILE_FINGERPRINTS` (~9901行) | 31类关键词指纹定义 |
| `main.py` `_merge_similar_findings` | 同类风险合并 |
| `main.py` `STRUCT_AMBIGUOUS_PAIRS` (~10462行) | 结构同形冲突对 |
| `main.py` `_parse_excel_structured` | 文件解析入口 |
| `tax_risk.py` `get_tax_risk_report()` | 312规则引擎 |
| `static/js/tax-doc-analysis.js` | 前端报告渲染 |
| `static/index.html` | 页面入口，含JS版本号 |

## 项目基础信息

- 仓库: `github.com/Deng-dahua/caishuixitong`
- 启动: `python -m uvicorn main:app --port 8001`
- 数据库: SQLite `accounting.db`
- 技术栈: Python 3.13 + FastAPI + SQLAlchemy + HTML/CSS/JS

## 交付检查清单

报告生成完成后，按以下顺序检查：
1. 重启服务器确认代码生效
2. 运行 `python audit.py 1` 确认 7/7 通过
3. 触发分析 API 确认 stats 各项非零
4. 检查 pipeline_log 标签与 stats 一致
5. 检查同类风险是否已合并
6. `git commit` + `git push`
