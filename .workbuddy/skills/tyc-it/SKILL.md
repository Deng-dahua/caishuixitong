---
name: tyc-it
description: 天眼查 MCP"天眼一下"（TYC It）商业查询入口。用于任何需要使用天眼查企业数据支撑的商业查询、企业信息查询、商业尽调、主体核验、合作方/客户/供应商评估、股权实控与关联关系、司法和行政风险、经营真实性、知识产权、人员背景、历史沿革、行业/园区/榜单发现、上市财务等问题；包括但不限于查公司、判断能否合作、识别关联关系、排查风险、发现行业企业、核验品牌/专利/投标机会等场景。
---

# 天眼一下

英文名：TYC It
建议唤起命令：`/tyc-it`

## MCP Server 调用契约（当前架构）

当前 MCP Server 的 `tools/list` 默认只公开小工具面；162 个 T1.1 业务语义聚合工具仍在服务端注册，深层维度通过能力目录和代理工具进入。执行本 skill 时遵循以下契约：

- 实体锚定优先调用公开工具 `search_companies`，参数使用 `query`。从候选表同时保留 `name` 作为后续 `company_name`、`id` 作为 `company_id`、`creditCode` 作为最终主体标识。
- 基础信息优先直接调用公开画像工具：`get_company_basic_profile`、`get_group_info`、`get_company_group_profile`、`get_company_people`、`get_person_profile`、`get_person_risk_profile`。
- 除公开画像和通用搜索工具外，调用公司维度明细前先调用 `get_company_capabilities(company_id, company_name)`，只使用返回表格中真实存在的 `tool_name`。
- 调用内部工具时使用 `call_tool`；`tool_name` 必须逐字复制能力表中的真实名称，不要翻译、改写或猜测。顶层主体参数优先传 `company_name`，只有没有精确名称时才用 `company_id`。
- 仅当同一企业下多个事实补齐互不依赖时使用 `call_tools_batch`，每批最多 3 个。关系路径、主体搜索、详情下钻、人员画像、能力发现、会决定下一步的问题不要放入 batch。
- 如果问题涉及集团、关联方、子公司、投资方、控股股东、担保链或人物版图，把每个相关主体加入查询队列，并分别做实体锚定和能力发现。

## 触发条件

当用户提出宽泛或探索式商查问题，而不是已经指名某个专用 skill 时使用本 skill。

典型问题：

- "帮我查一下这家公司靠不靠谱"
- "这家公司能不能作为客户/供应商/合作方"
- "A 和 B 有没有关联关系"
- "某公司背后是谁控制的"
- "最近有没有诉讼、被执行、处罚或经营异常"
- "这家公司有没有真实经营、招投标、资质、招聘、客户供应商"
- "某品牌有没有商标风险，某技术方向有哪些专利公司"
- "找一下某行业/某地区/某标签下的企业名单"
- "给我做一个商查摘要，不要太长"

## 输入要求

| 输入形式 | 示例 | 处理方式 |
|---|---|---|
| 完整企业名 | `北京字节跳动科技有限公司` | 可跳过候选确认，仍建议用 `search_companies` 或基础画像核验主体 |
| USCC | `91110108551385082Q` | 直接作为精确主体，必要时反查企业名称 |
| 简称/品牌/曾用名/模糊名 | `字节`、`抖音`、`天眼查` | 必须用 `search_companies(query)` 消歧 |
| 两个以上主体 | `联洋国融和启赢互联` | 分别锚定，每个主体保留独立 `company_name` 和 `company_id` |
| 行业/地区/标签/榜单 | `上海 AI 公司`、`专精特新企业` | 使用搜索类入口形成候选名单，再对重点公司下钻 |

实体锚定规则：

1. 若输入匹配 USCC 正则 `^[0-9A-Z]{18}$`，直接使用。
2. 若输入含 `有限公司`、`股份有限公司`、`集团`、`合伙企业`、`个体工商户`、`事务所`、`中心`、`分公司` 等组织形式且长度足够，优先按完整企业名处理。
3. 其他情况调用 `search_companies(query: userInput)`。过滤 `regStatus` 为 `存续`、`在业`、`在营`、`开业` 的候选，按相关性、注册资本、成立时间和用户语境排序，最多展示 5 个。
4. 候选为 1 个时可自动锚定；候选大于等于 2 个时暂停并请用户确认；候选为 0 时请用户提供更完整名称、USCC 或其他线索。

## 意图分流

| 意图 | 优先工具链 |
|---|---|
| 主体画像 | `search_companies` -> `get_company_basic_profile`；必要时 `get_company_capabilities` -> `get_company_registration_info`、`get_company_profile`、`get_company_tags` |
| 合作准入/风险初筛 | `get_company_basic_profile` -> `get_company_capabilities` -> `get_risk_overview`、`get_business_exception`、`get_administrative_penalty`、`get_serious_violation`、`get_judgment_debtor_info`、`get_dishonest_info` |
| 股权实控/UBO | `get_group_info` 或 `get_company_group_profile` -> `get_company_capabilities` -> `get_shareholder_info`、`get_actual_controller`、`get_beneficial_owners`、`get_equity_tree`、`get_equity_ratio` |
| 关联关系 | 分别 `search_companies` -> `get_relation_path`；再按需 `get_relation_graph`、`get_company_group_profile`、`get_key_personnel` |
| 司法诉讼/执行 | `get_company_capabilities` -> `get_risk_overview`、`get_judicial_case`、`get_judicial_documents`、`get_case_filing_info`、`get_judgment_debtor_info`、`get_dishonest_info`、`get_high_consumption_restriction` |
| 行政/税务/ESG 合规 | `get_company_capabilities` -> `get_administrative_penalty`、`get_environmental_penalty`、`get_tax_violation`、`get_tax_arrears_notice`、`get_serious_violation` |
| 经营真实性 | `get_company_basic_profile` -> `get_company_capabilities` -> `get_company_scale`、`get_qualifications`、`get_bidding_info`、`get_suppliers_and_customers`、`get_recruitment_info`、`get_products_info`、`get_administrative_license` |
| 知产/品牌/技术 | `get_company_capabilities` -> `get_ipr_score`、`get_patent_info`、`get_trademark_info`、`get_software_copyright_info`；关键词搜索用 `search_trademarks`、`search_patents` |
| 人员背景 | `get_company_people` -> `get_person_profile` 或 `get_person_risk_profile`；必要时 `get_personnel_positions`、`get_personnel_related_companies`、`get_person_risk_overview` |
| 历史沿革 | `get_company_capabilities` -> `get_historical_overview`、`get_historical_registration`、`get_historical_shareholders`、`get_historical_investments`、`get_change_records`、`get_history_names` |
| 行业/名单发现 | `search_companies_by_industry_region`、`search_companies_by_tag`、`search_companies_by_ranking`、`search_park_companies`；对候选 Top N 再画像 |
| 上市/财务 | `get_company_capabilities` -> `get_financial_summary`、`get_financial_data`、`get_listing_info`、`get_income_statement`、`get_balance_sheet`、`get_cash_flow_statement`、`get_stock_shareholders` |

## 执行流程

### Step 1: 明确问题边界
从用户原话提取：`subject[]`、`intent[]`、`depth`、`decision_context`。

### Step 2: 锚定主体
对每个企业线索执行锚定规则。完成锚定后记录 `company_name`、`company_id`、`creditCode`。

### Step 3: 调用高密度公开入口
按问题选择公开入口：单主体→`get_company_basic_profile`；集团/股权→`get_group_info`；人员→`get_company_people`。

### Step 4: 能力发现与下钻
调用 `get_company_capabilities(company_id, company_name)`。从返回表格复制 `tool_name`，按意图分流表调用必要工具。

### Step 5: 交叉验证和判断
把结论建立在至少两个维度的互证上。明确区分"已查无记录""工具未返回""未覆盖该维度"。

### Step 6: 输出
默认结论先行，再给证据和建议。快速摘要模板和标准商查报告模板见上方完整版。

## CLI 调用方式

本 Skill 通过 `tyc` CLI 命令调用天眼查数据。常用命令：

```bash
# 搜索企业
tyc search "企业名称" --md

# 企业基本信息
tyc company registration-info "企业名称" --md

# 企业风险概览
tyc company risk-overview "企业名称" --md

# 查看可用工具
tyc layers --md
```
