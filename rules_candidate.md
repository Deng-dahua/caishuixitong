# rules_candidate.md（候选规则库：V1.0 + V1.1 + V1.2）

> 本文档是财税稽查分析系统的候选规则库，包含 **V1.0 + V1.1 + V1.2 全部候选规则**。
> 作为《WorkBuddy 开发指令书》**第 2 步「规则去重合并」**的附件使用。
>
> - 所有规则均为**候选规则**，必须与现有规则库逐条对比、去重、合并后再入库。
> - **规则 ID 冲突时，以现有已上线规则为准。**
> - 所有阈值、行业均值、地区均值**必须参数化**。
> - 法规依据只写 `legal_basis_ref`，由法规库自动匹配。
> - **不直接照搬，不直接覆盖现有规则。**

---

## 目录

1. [一、使用说明](#一使用说明)
2. [二、单条规则 YAML 模板](#二单条规则-yaml-模板)
3. [三、规则 ID 命名空间](#三规则-id-命名空间)
4. [四、候选规则清单](#四候选规则清单)
5. [五、已知重复项与去重说明](#五已知重复项与去重说明)
6. [六、分批入库建议](#六分批入库建议)
7. [七、给 WorkBuddy 的附件使用说明](#七给-workbuddy-的附件使用说明)

---

## 一、使用说明

1. 本文档所有规则均为**候选规则，不是最终规则**。
2. 必须与现有规则库**逐条对比、去重、合并**后再入库。
3. **规则 ID 冲突时，以现有已上线规则为准。**
4. 所有阈值、行业均值、地区均值、比例、金额阈值**必须参数化**。
5. 法规依据**只写 `legal_basis_ref`**，由法规库自动匹配。
6. **不编造法规条文，不硬编码法规条款。**
7. **不直接覆盖现有规则**，先生成对比报告和合并方案。
8. **不全量一次性入库**，按第六部分建议分批入库。
9. 每条规则上线前**必须由税务专家校准阈值**。
10. 系统输出的是**风险线索和分析建议**，不构成税务处理、处罚或法律意见，**必须经专业人员复核**。

---

## 二、单条规则 YAML 模板

```yaml
- rule_id: VAT-003
  name: 开票收入与申报收入差异
  tax_type: VAT
  version: 1.0.0
  severity: high          # high / medium / low
  enabled: true
  scope:
    period: current_year
    industry: auto
  inputs:
    - invoice_sales
    - declared_sales
  params:
    diff_ratio: 0.1
  condition: "abs(invoice_sales - declared_sales) / declared_sales > params.diff_ratio"
  risk:
    score: 85
    message: "开票收入与申报收入差异超过阈值"
    evidence:
      - "开票收入: ${invoice_sales}"
      - "申报收入: ${declared_sales}"
      - "差异率: ${diff_ratio_actual}"
    suggestion: "核查未开票收入、申报完整性、收入确认时点"
    legal_basis_ref: "法规库自动匹配"
```

---

## 三、规则 ID 命名空间

| 前缀 | 税种/领域 | 前缀 | 税种/领域 |
|---|---|---|---|
| VAT | 增值税 | CIT | 企业所得税 |
| IIT | 个人所得税 | SI | 社保与非税 |
| SD | 印花税 | PCT | 房产税 |
| LUT | 城镇土地使用税 | LAT | 土地增值税 |
| SUR | 附加税费 | INV | 发票合规 |
| FIN | 财务报表勾稽 | REL | 关联交易 |
| FUND | 资金流 | EXPORT | 出口退税 |
| CONS | 消费税 | RES | 资源税 |
| ENV | 环保税 | TAXINC | 税收优惠 |
| GEN | 通用申报 | DEED | 契税 |
| GOT | 耕地占用税 | VET | 车船税 |
| VPT | 车辆购置税 | CUS | 关税 |
| TON | 船舶吨税 | TOB | 烟叶税 |
| CUL | 文化事业建设费 | WAT | 水利建设基金 |
| ADM | 税收征管 | AA | 反避税 |
| INT | 国际税收 | REO | 企业重组 |
| EST | 房地产 | CONSTR | 建筑 |
| PLAT | 平台经济 | FLEX | 灵活用工 |
| HNW | 高净值个人 | FINA | 金融 |
| LEASE | 融资租赁 | FACT | 保理 |
| MICRO | 小贷 | GUAR | 担保 |
| PAWN | 典当 | PE | 私募 |
| FUNDM | 公募基金 | TRUST | 信托 |
| REIT | REITs | PPP | PPP |
| EPC | EPC | BOT | BOT |
| ABS | 资产证券化 | CUSTOMS | 海关 |
| BOND | 保税 | FTZ | 自贸区 |
| HAINAN | 海南自贸港 | ASSESS | 核定征收 |
| LIQ | 注销清算 | BANKR | 破产重整 |
| EINV | 电子发票 | RRT | 留抵退税 |
| HNTECH | 高新 | RD | 研发 |
| SOFT | 软件 | IC | 集成电路 |
| ANIME | 动漫 | CULT | 文化 |
| EDU | 教育 | MED | 医疗 |
| ELDER | 养老 | CHILD | 托育 |
| HOUSE | 家政 | SPORT | 体育 |
| TOUR | 旅游 | HOTEL | 住宿 |
| CATER | 餐饮 | ENT | 娱乐 |
| CBEC | 跨境电商 | | |

---

## 四、候选规则清单

### A. 增值税 VAT（30）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| VAT-001 | 增值税税负率偏低 | 高 | vat_burden < industry_avg_vat_burden * 0.7 | vat_payable, sales_revenue, industry_avg_vat_burden | 核查收入确认、进项抵扣、发票合规 |
| VAT-002 | 增值税税负率异常波动 | 中 | abs(vat_burden - vat_burden_last_year) / vat_burden_last_year > 0.5 | vat_burden, vat_burden_last_year | 分析税负突变原因 |
| VAT-003 | 开票收入与申报收入差异 | 高 | abs(invoice_sales - declared_sales) / declared_sales > 0.1 | invoice_sales, declared_sales | 核查未开票收入、申报完整性 |
| VAT-004 | 进销项变动背离 | 中 | output_tax_growth - input_tax_growth > 0.3 and output_tax_growth > 0.2 | output_tax, input_tax | 核查进项抵扣与销售匹配 |
| VAT-005 | 进销项品名背离 | 高 | top_input_goods not in top_output_goods and amount_ratio > 0.3 | 进销项品名、金额 | 核查虚开、变名开票 |
| VAT-006 | 进销项数量背离 | 中 | abs(input_qty - output_qty) / output_qty > 0.3 | 进销项数量 | 核查存货、生产消耗 |
| VAT-007 | 月末集中开票 | 中 | month_end_invoice_ratio > 0.5 | month_end_invoice_amount, total_invoice_amount | 核查收入确认时点 |
| VAT-008 | 夜间开票异常 | 中 | night_invoice_ratio > 0.2 | night_invoice_count, total_invoice_count | 核查开票真实性 |
| VAT-009 | 红冲作废率异常 | 中 | void_ratio > 0.1 | void_invoice_amount, total_invoice_amount | 核查作废红冲原因 |
| VAT-010 | 进项发票异常 | 高 | abnormal_invoice_count > 0 | abnormal_invoice_count, input_invoice_total | 核查异常凭证、进项转出 |
| VAT-011 | 有进项无销项 | 高 | input_tax > 0 and output_tax = 0 for n months | 月度进销项 | 核查隐匿收入、停工待产 |
| VAT-012 | 有销项无进项 | 中 | output_tax > 0 and input_tax = 0 for n months | 月度进销项 | 核查虚开、成本缺失 |
| VAT-013 | 免税收入与进项抵扣不匹配 | 高 | tax_exempt_sales > 0 and input_tax_for_exempt_deducted > 0 | 免税销售额、已抵扣进项 | 核查进项转出 |
| VAT-014 | 简易计税与一般计税混用异常 | 中 | simplified_tax_sales > 0 and general_tax_input_deducted > 0 | 简易计税销售额、一般计税进项 | 核查计税方法适用 |
| VAT-015 | 预缴增值税与申报差异 | 中 | abs(prepaid_vat - declared_vat) / declared_vat > 0.1 | 预缴税额、申报税额 | 核查预缴与申报一致性 |
| VAT-016 | 未开票收入占比异常 | 中 | un_invoiced_revenue_ratio > 0.3 | 未开票收入、总收入 | 核查未开票收入真实性 |
| VAT-017 | 销售退回异常 | 中 | sales_return_ratio > 0.1 | 销售退回金额、销售收入 | 核查退回真实性 |
| VAT-018 | 价外费用未计税 | 中 | extra_price_income > taxed_extra_price_income | 价外费用、已计税价外费用 | 核查价外费用计税 |
| VAT-019 | 视同销售未处理 | 高 | deemed_sales_amount > declared_deemed_sales | 视同销售金额、已申报视同销售 | 核查视同销售 |
| VAT-020 | 进项税额转出异常 | 中 | should_transfer_out > actual_transfer_out | 应转出进项、实际转出 | 核查进项转出 |
| VAT-021 | 差额征税项目异常 | 中 | difference_tax_sales - difference_tax_cost > threshold | 差额征税销售额、扣除额 | 核查差额征税 |
| VAT-022 | 发票作废后重开异常 | 中 | void_reissue_count > threshold | void_reissue_count | 核查作废重开 |
| VAT-023 | 同一客户频繁顶额开票 | 中 | same_customer_max_invoice_count > threshold | same_customer_invoice_count | 核查拆分开票 |
| VAT-024 | 新办企业短期大量开票 | 高 | new_company_invoice_amount_3m > threshold | 新办企业开票金额 | 核查虚开 |
| VAT-025 | 购销合同与开票金额差异 | 中 | abs(contract_amount - invoice_amount) / contract_amount > 0.2 | 合同金额、开票金额 | 核查合同与发票一致性 |
| VAT-026 | 银行流水收入与开票收入差异 | 高 | abs(bank_receipts - invoice_sales) / invoice_sales > 0.2 | 银行收款、开票收入 | 核查账外收入 |
| VAT-027 | 应收账款与收入变动背离 | 中 | AR_growth - revenue_growth > 0.3 | 应收账款、收入 | 核查收入确认 |
| VAT-028 | 存货变动与销售成本背离 | 中 | inventory_change - cost_of_sales_change > 0.3 | 存货、销售成本 | 核查成本结转 |
| VAT-029 | 增值税税率适用错误 | 高 | applied_vat_rate != correct_vat_rate | 适用税率、正确税率 | 核查税率适用 |
| VAT-030 | 即征即退/先征后退异常 | 中 | refund_amount > threshold and refund_condition not met | 退税金额、退税条件 | 核查退税合规 |

### B. 企业所得税 CIT（30）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| CIT-001 | 所得税贡献率偏低 | 高 | cit_contribution < industry_avg_cit_contribution * 0.7 | cit_payable, revenue, industry_avg | 核查利润、纳税调整 |
| CIT-002 | 所得税税负率异常波动 | 中 | abs(cit_burden - cit_burden_last_year) / cit_burden_last_year > 0.5 | cit_payable, profit | 分析税负突变 |
| CIT-003 | 利润总额与应纳税所得额差异异常 | 中 | abs(taxable_income - profit_total) / profit_total > 0.3 | profit_total, taxable_income | 核查税会差异调整 |
| CIT-004 | 成本费用率异常 | 高 | cost_ratio > industry_avg_cost_ratio * 1.3 | cost, revenue, industry_avg | 核查成本费用真实性 |
| CIT-005 | 收入与成本变动背离 | 中 | revenue_growth - cost_growth < -0.3 and revenue_growth < 0 | revenue, cost | 核查收入成本匹配 |
| CIT-006 | 毛利率异常低于行业 | 中 | gross_margin < industry_avg_gross_margin * 0.7 | gross_margin, industry_avg | 核查定价、成本 |
| CIT-007 | 预缴与汇算差异大 | 中 | abs(prepaid_cit - annual_cit) / annual_cit > 0.3 | prepaid_cit, annual_cit | 核查预缴准确性 |
| CIT-008 | 期间费用占比异常 | 中 | expense_ratio > industry_avg_expense_ratio * 1.3 | expense, revenue | 核查费用真实性 |
| CIT-009 | 业务招待费超标 | 中 | entertainment_expense > min(revenue*0.005, actual*0.6) | entertainment_expense, revenue | 核查纳税调整 |
| CIT-010 | 广告宣传费超标 | 中 | advertising_expense > revenue*0.15 | advertising_expense, revenue | 核查纳税调整 |
| CIT-011 | 利息支出超标/资本弱化 | 高 | interest_expense > equity*2*market_rate | interest_expense, equity, market_rate | 核查关联方利息扣除 |
| CIT-012 | 关联交易定价异常 | 高 | abs(related_transaction_price - market_price)/market_price> 0.2 | related_transaction_price, market_price | 核查转让定价 |
| CIT-013 | 关联方借款长期未还 | 中 | related_party_receivable_age > 365 | related_party_receivable_balance, age | 核查视同分红/利息 |
| CIT-014 | 存货与成本不匹配 | 中 | inventory_change - cost_of_sales_change > 0.3 | inventory, cost_of_sales | 核查成本结转 |
| CIT-015 | 固定资产折旧异常 | 中 | depreciation_amount != depreciation_policy_amount | depreciation_amount, policy | 核查折旧政策 |
| CIT-016 | 无形资产摊销异常 | 中 | amortization_amount != amortization_policy_amount | amortization_amount, policy | 核查摊销政策 |
| CIT-017 | 资产损失税前扣除异常 | 高 | asset_loss_amount > threshold and evidence_completeness < 1 | asset_loss_amount, evidence | 核查损失证据 |
| CIT-018 | 政府补助税务处理异常 | 中 | government_grant > 0 and taxable_grant != government_grant | government_grant, taxable_grant | 核查不征税收入 |
| CIT-019 | 不征税收入对应支出扣除 | 高 | non_taxable_income > 0 and corresponding_expense_deducted > 0 | non_taxable_income, expense | 核查支出不得扣除 |
| CIT-020 | 免税收入对应成本扣除 | 高 | tax_exempt_income > 0 and corresponding_cost_deducted > 0 | tax_exempt_income, cost | 核查成本不得扣除 |
| CIT-021 | 研发费用加计扣除异常 | 中 | R&D_expense > 0 and R&D_conditions not met | R&D_expense, conditions | 核查加计扣除条件 |
| CIT-022 | 高新技术企业优惠异常 | 中 | high_tech_conditions not met and high_tech_deduction > 0 | conditions, deduction | 核查高新优惠 |
| CIT-023 | 小型微利企业优惠异常 | 中 | small_micro_conditions not met and small_micro_deduction > 0 | conditions, deduction | 核查小微优惠 |
| CIT-024 | 西部大开发等区域优惠异常 | 中 | regional_incentive_conditions not met and regional_deduction > 0 | conditions, deduction | 核查区域优惠 |
| CIT-025 | 弥补亏损异常 | 中 | loss_carryforward > 5 years or loss_amount > threshold | loss_carryforward, period | 核查亏损弥补 |
| CIT-026 | 预提费用/预计负债异常 | 中 | accrued_expense > actual_payment | accrued_expense, actual_payment | 核查预提费用 |
| CIT-027 | 工资薪金与个税社保不匹配 | 高 | salary_total - iit_total - social_security_total > threshold | salary_total, iit_total, social_security_total | 核查工资个税社保 |
| CIT-028 | 股东借款视同分红风险 | 高 | shareholder_loan_balance > 0 and loan_days > 365 | shareholder_loan_balance, loan_days | 核查视同分红 |
| CIT-029 | 对外捐赠扣除异常 | 中 | donation_amount > deduction_limit | donation_amount, deduction_limit | 核查捐赠扣除 |
| CIT-030 | 税会差异调整不完整 | 中 | tax_accounting_diff > adjusted_diff | tax_accounting_diff, adjusted_diff | 核查调整完整性 |

### C. 个人所得税 IIT（20）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| IIT-001 | 个税申报人数与社保人数差异 | 高 | abs(iit_headcount - social_headcount) / social_headcount > 0.2 | 个税人数、社保人数 | 核查漏报、少报 |
| IIT-002 | 个税工资总额与企业所得税工资总额差异 | 高 | abs(iit_salary_total - cit_salary_total) / cit_salary_total > 0.1 | 个税工资、所得税工资 | 核查工资口径 |
| IIT-003 | 股东借款长期未还 | 高 | shareholder_loan_balance > 0 and loan_days > 365 | 股东借款、天数 | 核查视同分红 |
| IIT-004 | 股东分红未代扣代缴 | 高 | dividend_paid > 0 and iit_withheld = 0 | 分红金额、已扣个税 | 核查代扣代缴 |
| IIT-005 | 劳务报酬未代扣代缴 | 高 | labor_remuneration > 0 and iit_withheld = 0 | 劳务报酬、已扣个税 | 核查代扣代缴 |
| IIT-006 | 多处任职未合并申报 | 中 | person_multi_employer = true and merged_declaration = false | 任职信息、申报记录 | 核查合并申报 |
| IIT-007 | 年终奖计税方式异常 | 中 | annual_bonus_tax_method not optimal | 年终奖、计税方式 | 核查计税方式 |
| IIT-008 | 高收入人员税负偏低 | 中 | high_income_person_tax_burden < threshold | 高收入人员、税负 | 核查申报完整性 |
| IIT-009 | 外籍个人免税补贴异常 | 中 | foreign_tax_exempt_subsidy > threshold | 外籍补贴、免税条件 | 核查免税条件 |
| IIT-010 | 股权转让个税申报异常 | 高 | equity_transfer_income > 0 and iit_declared < threshold | 股权转让收入、个税 | 核查股权转让 |
| IIT-011 | 合伙企业个人合伙人经营所得异常 | 中 | partnership_income_allocated > 0 and iit_declared = 0 | 合伙分配、个税 | 核查经营所得 |
| IIT-012 | 个体工商户核定征收异常 | 中 | fixed_rate_collection and actual_income > threshold | 核定征收、实际收入 | 核查核定适用 |
| IIT-013 | 个人独资企业投资人个税异常 | 中 | sole_proprietorship_income > 0 and iit_declared = 0 | 独资企业利润、个税 | 核查经营所得 |
| IIT-014 | 工资薪金长期低于起征点 | 中 | salary_below_threshold_months > 6 | 工资、月份 | 核查工资真实性 |
| IIT-015 | 现金发放工资未申报 | 高 | cash_salary > 0 and iit_declared = 0 | 现金工资、个税 | 核查漏报 |
| IIT-016 | 离职补偿金个税异常 | 中 | severance_pay > threshold and iit_withheld = 0 | 离职补偿、个税 | 核查免税额度 |
| IIT-017 | 股权激励个税递延异常 | 中 | equity_incentive and deferred_tax_condition not met | 股权激励、递延条件 | 核查递延备案 |
| IIT-018 | 利息股息红利所得未代扣 | 高 | interest_dividend_income > 0 and iit_withheld = 0 | 利息股息、已扣个税 | 核查代扣代缴 |
| IIT-019 | 财产租赁所得未代扣 | 中 | property_rental_income > 0 and iit_withheld = 0 | 租赁所得、已扣个税 | 核查代扣代缴 |
| IIT-020 | 偶然所得未代扣 | 中 | accidental_income > 0 and iit_withheld = 0 | 偶然所得、已扣个税 | 核查代扣代缴 |

### D. 社保与非税 SI（8）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| SI-001 | 社保人数与个税人数差异 | 高 | abs(social_headcount - iit_headcount) / iit_headcount > 0.2 | 社保人数、个税人数 | 核查漏缴社保 |
| SI-002 | 社保基数与工资总额差异 | 高 | abs(social_base_total - salary_total) / salary_total > 0.2 | 社保基数、工资总额 | 核查基数 |
| SI-003 | 试用期未缴社保 | 中 | probation_employee_count > 0 and social_insured = false | 试用期人数、参保状态 | 核查试用期社保 |
| SI-004 | 按最低基数缴纳 | 中 | social_base = min_base for ratio > 0.8 | 社保基数、最低基数 | 核查基数合规 |
| SI-005 | 劳务派遣社保异常 | 中 | dispatch_worker_count > 0 and social_insured = false | 派遣人数、参保状态 | 核查派遣社保 |
| SI-006 | 公积金基数异常 | 中 | abs(housing_fund_base - salary_total) / salary_total > 0.2 | 公积金基数、工资 | 核查公积金 |
| SI-007 | 残保金申报异常 | 中 | disabled_employment_ratio < required_ratio and fund_declared = 0 | 残疾人比例、残保金 | 核查残保金 |
| SI-008 | 工会经费申报异常 | 低 | union_fund_declared < salary_total * 0.02 | 工会经费、工资总额 | 核查工会经费 |

### E. 印花税 SD（10）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| SD-001 | 合同金额与印花税计税依据差异 | 高 | abs(contract_amount - stamp_tax_base) / contract_amount > 0.1 | 合同金额、印花税基数 | 核查计税依据 |
| SD-002 | 资金账簿印花税异常 | 中 | capital_increase > 0 and stamp_tax_paid = 0 | 实收资本、资本公积 | 核查资金账簿 |
| SD-003 | 产权转移书据未申报 | 高 | property_transfer_amount > 0 and stamp_tax_paid = 0 | 产权转移金额、印花税 | 核查产权转移 |
| SD-004 | 借款合同未申报 | 中 | loan_contract_amount > 0 and stamp_tax_paid = 0 | 借款合同、印花税 | 核查借款合同 |
| SD-005 | 租赁合同未申报 | 中 | lease_contract_amount > 0 and stamp_tax_paid = 0 | 租赁合同、印花税 | 核查租赁合同 |
| SD-006 | 购销合同未申报 | 中 | purchase_sales_contract_amount > 0 and stamp_tax_paid = 0 | 购销合同、印花税 | 核查购销合同 |
| SD-007 | 运输合同未申报 | 中 | transport_contract_amount > 0 and stamp_tax_paid = 0 | 运输合同、印花税 | 核查运输合同 |
| SD-008 | 技术合同未申报 | 中 | technology_contract_amount > 0 and stamp_tax_paid = 0 | 技术合同、印花税 | 核查技术合同 |
| SD-009 | 营业账簿印花税异常 | 中 | business_ledger_count > 0 and stamp_tax_paid = 0 | 营业账簿、印花税 | 核查营业账簿 |
| SD-010 | 印花税税目适用错误 | 中 | applied_stamp_tax_item != correct_item | 适用税目、正确税目 | 核查税目 |

### F. 房产税 PCT（8）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| PCT-001 | 房产原值未申报 | 高 | building_original_value > 0 and property_tax_paid = 0 | 房产原值、房产税 | 核查从价计征 |
| PCT-002 | 租金收入未申报房产税 | 高 | rental_income > 0 and property_tax_paid = 0 | 租金收入、房产税 | 核查从租计征 |
| PCT-003 | 免租期房产税异常 | 中 | rent_free_period > 0 and property_tax_paid = 0 | 免租期、房产税 | 核查免租期 |
| PCT-004 | 地下建筑物未申报 | 中 | underground_building_value > 0 and property_tax_paid = 0 | 地下建筑物、房产税 | 核查地下建筑 |
| PCT-005 | 在建工程转固未申报 | 中 | construction_in_progress_transferred > 0 and property_tax_paid = 0 | 在建工程转固、房产税 | 核查转固 |
| PCT-006 | 房产税计税依据异常 | 中 | abs(property_tax_base - building_original_value * (1 - deduction)) > threshold | 计税依据、原值、扣除 | 核查计税依据 |
| PCT-007 | 房产税税率适用错误 | 中 | applied_property_tax_rate != correct_rate | 适用税率、正确税率 | 核查税率 |
| PCT-008 | 房产税与土地使用税不匹配 | 低 | property_tax_paid > 0 and land_use_tax_paid = 0 | 房产税、土地使用税 | 核查匹配 |

### G. 城镇土地使用税 LUT（6）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| LUT-001 | 土地面积未申报 | 高 | land_area > 0 and land_use_tax_paid = 0 | 土地面积、土地使用税 | 核查申报 |
| LUT-002 | 土地等级适用错误 | 中 | applied_land_level != correct_land_level | 适用等级、正确等级 | 核查等级 |
| LUT-003 | 免税土地未备案 | 中 | tax_exempt_land > 0 and filing_missing = true | 免税土地、备案 | 核查备案 |
| LUT-004 | 土地使用税与房产税不匹配 | 低 | land_use_tax_paid > 0 and property_tax_paid = 0 | 土地使用税、房产税 | 核查匹配 |
| LUT-005 | 土地出让合同与申报差异 | 中 | abs(land_transfer_area - declared_land_area) / land_transfer_area > 0.1 | 出让面积、申报面积 | 核查面积 |
| LUT-006 | 土地闲置未申报 | 中 | idle_land_area > 0 and land_use_tax_paid = 0 | 闲置土地、土地使用税 | 核查闲置土地 |

### H. 土地增值税 LAT（10）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| LAT-001 | 预缴土地增值税异常 | 高 | prepaid_lat < pre_sale_revenue * prepay_rate | 预收收入、预缴土地增值税 | 核查预缴 |
| LAT-002 | 清算条件已满足未清算 | 高 | liquidation_condition_met = true and liquidation_done = false | 清算条件、清算状态 | 核查清算 |
| LAT-003 | 扣除项目金额异常 | 高 | deduction_amount > threshold | 扣除项目金额 | 核查扣除 |
| LAT-004 | 销售收入与申报差异 | 高 | abs(sales_revenue - declared_lat_sales) / sales_revenue > 0.1 | 销售收入、申报收入 | 核查收入 |
| LAT-005 | 普通住宅与非普通住宅划分错误 | 中 | residential_type_misclassified = true | 住宅类型、划分标准 | 核查划分 |
| LAT-006 | 开发成本分摊异常 | 中 | cost_allocation_ratio != reasonable_ratio | 成本分摊、合理比例 | 核查分摊 |
| LAT-007 | 利息支出扣除异常 | 中 | interest_deduction > threshold | 利息支出、扣除限额 | 核查利息 |
| LAT-008 | 拆迁补偿费异常 | 中 | relocation_compensation > threshold | 拆迁补偿、凭证 | 核查补偿 |
| LAT-009 | 土地增值税税负率异常 | 中 | lat_burden < industry_avg_lat_burden * 0.7 | 土地增值税税负、行业均值 | 核查税负 |
| LAT-010 | 清算后再转让未申报 | 中 | post_liquidation_transfer > 0 and lat_declared = 0 | 清算后转让、土地增值税 | 核查再转让 |

### I. 附加税费 SUR（10）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| SUR-001 | 附加税费计税依据与增值税差异 | 中 | abs(surtax_base - vat_payable) / vat_payable > 0.05 | 附加税费基数、增值税 | 核查计税依据 |
| SUR-002 | 附加税费减免适用错误 | 中 | surtax_reduction_applied and condition not met | 减免、条件 | 核查减免 |
| SUR-003 | 城建税税率适用错误 | 中 | applied_urban_rate != correct_rate | 适用税率、正确税率 | 核查税率 |
| SUR-004 | 教育费附加/地方教育附加未申报 | 中 | vat_payable > 0 and education_surcharge_paid = 0 | 增值税、教育费附加 | 核查申报 |
| SUR-005 | 附加税费与增值税申报不匹配 | 中 | abs(surtax_paid - vat_payable * surtax_rate) > threshold | 附加税费、增值税、税率 | 核查匹配 |
| SUR-006 | 地方教育附加未申报 | 中 | vat_payable > 0 and local_edu_surcharge_paid = 0 | 增值税、地方教育附加 | 核查申报 |
| SUR-007 | 教育费附加减免异常 | 中 | edu_surcharge_reduction and condition not met | 减免、条件 | 核查减免 |
| SUR-008 | 附加税费退库异常 | 中 | surtax_refund > 0 and vat_refund = 0 | 附加税费退库、增值税退税 | 核查退库 |
| SUR-009 | 附加税费跨期异常 | 中 | surtax_period != vat_period | 附加税费期间、增值税期间 | 核查期间 |
| SUR-010 | 附加税费申报表间差异 | 中 | abs(surtax_return_a - surtax_return_b) > threshold | 申报表A、申报表B | 核查申报 |

### J. 发票合规 INV（20）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| INV-001 | 进销项品名背离 | 高 | top_input_goods not in top_output_goods and amount_ratio > 0.3 | 进销项品名、金额 | 核查虚开 |
| INV-002 | 顶额开票 | 中 | invoice_amount = max_limit for count > threshold | 发票金额、限额 | 核查拆分 |
| INV-003 | 月末集中开票 | 中 | month_end_invoice_ratio > 0.5 | 月末开票、总开票 | 核查收入确认 |
| INV-004 | 夜间开票 | 中 | night_invoice_ratio > 0.2 | 夜间开票、总开票 | 核查真实性 |
| INV-005 | 作废红冲异常 | 中 | void_ratio > 0.1 | 作废金额、总金额 | 核查作废 |
| INV-006 | 新办企业短期大量开票 | 高 | new_company_invoice_amount_3m > threshold | 新办企业开票 | 核查虚开 |
| INV-007 | 同一IP/设备开票异常 | 中 | same_ip_invoice_count > threshold | 开票IP、设备 | 核查关联 |
| INV-008 | 同一客户频繁开票 | 中 | same_customer_invoice_count > threshold | 客户开票次数 | 核查拆分 |
| INV-009 | 发票流与资金流不一致 | 高 | invoice_payer != fund_payer | 发票、资金流 | 核查三流一致 |
| INV-010 | 发票流与合同流不一致 | 高 | invoice_party != contract_party | 发票、合同 | 核查三流一致 |
| INV-011 | 进项发票异常 | 高 | abnormal_invoice_count > 0 | 异常发票、进项 | 核查进项转出 |
| INV-012 | 销项发票异常 | 高 | abnormal_output_invoice_count > 0 | 异常销项 | 核查销项 |
| INV-013 | 农产品收购发票异常 | 高 | agricultural_purchase_invoice > threshold | 农产品发票 | 核查收购 |
| INV-014 | 差旅费发票异常 | 中 | travel_expense_invoice > threshold | 差旅发票 | 核查真实性 |
| INV-015 | 咨询费发票异常 | 高 | consulting_invoice > threshold | 咨询发票 | 核查虚开 |
| INV-016 | 会议费发票异常 | 中 | conference_invoice > threshold | 会议发票 | 核查真实性 |
| INV-017 | 广告费发票异常 | 中 | advertising_invoice > threshold | 广告发票 | 核查真实性 |
| INV-018 | 运输费发票异常 | 中 | transport_invoice > threshold | 运输发票 | 核查真实性 |
| INV-019 | 电子发票重复报销 | 中 | duplicate_e_invoice = true | 电子发票、报销记录 | 核查重复 |
| INV-020 | 发票备注栏缺失 | 低 | required_remark_missing = true | 发票备注、要求 | 核查备注 |

### K. 财务报表勾稽 FIN（18）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| FIN-001 | 资产负债表不平衡 | 高 | assets != liabilities + equity | 资产、负债、权益 | 核查报表 |
| FIN-002 | 利润表与资产负债表未分配利润勾稽异常 | 高 | abs(net_profit - retained_earnings_change) > threshold | 净利润、未分配利润 | 核查勾稽 |
| FIN-003 | 现金流量表与货币资金勾稽异常 | 高 | abs(cash_flow_net - cash_change) > threshold | 现金流、货币资金 | 核查勾稽 |
| FIN-004 | 收入与应收账款变动背离 | 中 | AR_growth - revenue_growth > 0.3 | 应收账款、收入 | 核查收入 |
| FIN-005 | 收入与存货变动背离 | 中 | inventory_growth - revenue_growth > 0.3 | 存货、收入 | 核查收入 |
| FIN-006 | 成本与应付账款变动背离 | 中 | AP_growth - cost_growth > 0.3 | 应付账款、成本 | 核查成本 |
| FIN-007 | 费用与应付职工薪酬变动背离 | 中 | payable_salary_growth - expense_growth > 0.3 | 应付薪酬、费用 | 核查费用 |
| FIN-008 | 固定资产与折旧变动背离 | 中 | fixed_asset_growth - depreciation_growth > 0.3 | 固定资产、折旧 | 核查折旧 |
| FIN-009 | 无形资产与摊销变动背离 | 中 | intangible_asset_growth - amortization_growth > 0.3 | 无形资产、摊销 | 核查摊销 |
| FIN-010 | 长期股权投资与投资收益背离 | 中 | long_term_equity_investment_growth - investment_income_growth > 0.3 | 长期股权投资、投资收益 | 核查收益 |
| FIN-011 | 借款与财务费用背离 | 中 | loan_growth - finance_expense_growth > 0.3 | 借款、财务费用 | 核查利息 |
| FIN-012 | 货币资金与利息收入背离 | 中 | cash_growth - interest_income_growth > 0.3 | 货币资金、利息收入 | 核查利息 |
| FIN-013 | 其他应收款长期挂账 | 中 | other_receivable_age > 365 | 其他应收款、账龄 | 核查挂账 |
| FIN-014 | 其他应付款长期挂账 | 中 | other_payable_age > 365 | 其他应付款、账龄 | 核查挂账 |
| FIN-015 | 预收账款与收入确认背离 | 中 | advance_receipt_growth - revenue_growth > 0.3 | 预收账款、收入 | 核查收入 |
| FIN-016 | 存货周转率异常 | 中 | inventory_turnover < industry_avg * 0.7 | 存货周转率、行业均值 | 核查存货 |
| FIN-017 | 应收账款周转率异常 | 中 | AR_turnover < industry_avg * 0.7 | 应收账款周转率、行业均值 | 核查应收 |
| FIN-018 | 毛利率异常波动 | 中 | abs(gross_margin - gross_margin_last_year) > 0.2 | 毛利率、上年毛利率 | 核查波动 |

### L. 关联交易 REL（10）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| REL-001 | 关联交易定价异常 | 高 | abs(related_price - market_price)/market_price> 0.2 | 关联价格、市场价格 | 核查转让定价 |
| REL-002 | 关联交易占比过高 | 中 | related_transaction_ratio > 0.5 | 关联交易、总收入 | 核查关联 |
| REL-003 | 关联方资金占用 | 高 | related_party_receivable > threshold | 关联方应收 | 核查资金占用 |
| REL-004 | 关联方借款利率异常 | 高 | related_loan_rate > market_rate * 1.5 | 关联借款利率、市场利率 | 核查利息 |
| REL-005 | 关联方购销价格异常 | 高 | related_purchase_sales_price != market_price | 关联购销、市场价格 | 核查定价 |
| REL-006 | 关联方劳务费用异常 | 中 | related_service_fee > threshold | 关联劳务费 | 核查劳务 |
| REL-007 | 关联方资产转让异常 | 高 | related_asset_transfer_price != fair_value | 关联资产转让、公允价值 | 核查转让 |
| REL-008 | 关联方股权转让异常 | 高 | related_equity_transfer_price != fair_value | 关联股权转让、公允价值 | 核查转让 |
| REL-009 | 关联方债务豁免 | 中 | related_party_debt_forgiveness > 0 | 债务豁免 | 核查税务处理 |
| REL-010 | 关联方承担费用 | 中 | related_party_expense_bearing > 0 | 关联方费用承担 | 核查费用 |

### M. 资金流 FUND（11）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| FUND-001 | 公转私大额频繁 | 高 | public_to_private_count > threshold and amount > threshold | 公转私记录 | 核查资金 |
| FUND-002 | 私转公大额频繁 | 高 | private_to_public_count > threshold and amount > threshold | 私转公记录 | 核查资金 |
| FUND-003 | 资金回流 | 高 | fund_return_detected = true | 资金流水 | 核查回流 |
| FUND-004 | 银行流水与收入不匹配 | 高 | abs(bank_receipts - revenue) / revenue > 0.2 | 银行收款、收入 | 核查收入 |
| FUND-005 | 银行流水与成本不匹配 | 中 | abs(bank_payments - cost) / cost > 0.2 | 银行付款、成本 | 核查成本 |
| FUND-006 | 现金交易异常 | 中 | cash_transaction_ratio > 0.3 | 现金交易、总交易 | 核查现金 |
| FUND-007 | 个人卡收付款 | 高 | personal_card_transaction > threshold | 个人卡交易 | 核查资金 |
| FUND-008 | 第三方支付异常 | 中 | third_party_payment > threshold | 第三方支付 | 核查资金 |
| FUND-009 | 资金池异常 | 中 | fund_pool_balance > threshold | 资金池 | 核查资金 |
| FUND-010 | 大额预付款长期未冲销 | 中 | prepayment_age > 365 | 预付款、账龄 | 核查预付款 |
| FUND-011 | 资金池税务处理异常 | 中 | cash_pool and tax_treatment_abnormal | 资金池、税务处理 | 核查处理 |

### N. 出口退税 EXPORT（14）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| EXPORT-001 | 出口退税申报异常 | 高 | export_refund > threshold and condition not met | 出口退税、条件 | 核查退税 |
| EXPORT-002 | 免抵退税额异常 | 高 | export_tax_refund != calculated_refund | 免抵退税额、计算值 | 核查计算 |
| EXPORT-003 | 出口收入与报关单差异 | 高 | abs(export_revenue - customs_declaration) / export_revenue > 0.1 | 出口收入、报关单 | 核查收入 |
| EXPORT-004 | 进料加工核销异常 | 中 | processing_trade_verification_missing = true | 进料加工、核销 | 核查核销 |
| EXPORT-005 | 出口发票异常 | 中 | export_invoice_abnormal = true | 出口发票 | 核查发票 |
| EXPORT-006 | 退税函调异常 | 高 | tax_refund_investigation_abnormal = true | 函调结果 | 核查函调 |
| EXPORT-007 | 出口商品编码适用错误 | 中 | applied_export_code != correct_code | 商品编码、正确编码 | 核查编码 |
| EXPORT-008 | 出口退税率适用错误 | 中 | applied_refund_rate != correct_rate | 退税率、正确税率 | 核查税率 |
| EXPORT-009 | 出口收汇异常 | 中 | export_receipt_missing = true | 出口收汇 | 核查收汇 |
| EXPORT-010 | 出口转内销未申报 | 中 | export_to_domestic > 0 and tax_declared = 0 | 出口转内销、申报 | 核查申报 |
| EXPORT-011 | 出口退税函调异常 | 高 | tax_refund_investigation_abnormal = true | 函调结果 | 核查函调 |
| EXPORT-012 | 出口收汇异常 | 中 | export_receipt_missing = true | 出口收汇 | 核查收汇 |
| EXPORT-013 | 出口转内销未申报 | 中 | export_to_domestic > 0 and tax_declared = 0 | 出口转内销、申报 | 核查申报 |
| EXPORT-014 | 跨境电商无票免税异常 | 中 | cross_border_ecommerce_tax_free and conditions_not_met | 无票免税、条件 | 核查条件 |

> **注**：EXPORT-011 至 EXPORT-013 与 EXPORT-006、009、010 重复，见第五部分去重说明。

### O. 消费税 CONS（8）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| CONS-001 | 消费税税目适用错误 | 中 | applied_consumption_item != correct_item | 适用税目、正确税目 | 核查税目 |
| CONS-002 | 消费税计税依据异常 | 中 | abs(consumption_tax_base - sales_amount) > threshold | 计税依据、销售额 | 核查依据 |
| CONS-003 | 自产自用未申报 | 高 | self_produced_used > 0 and consumption_tax_paid = 0 | 自产自用、消费税 | 核查自用 |
| CONS-004 | 委托加工未代扣代缴 | 高 | entrusted_processing > 0 and consumption_tax_withheld = 0 | 委托加工、已扣税 | 核查代扣 |
| CONS-005 | 进口消费税未申报 | 高 | import_consumption_goods > 0 and consumption_tax_paid = 0 | 进口应税消费品、消费税 | 核查进口 |
| CONS-006 | 消费税与增值税收入差异 | 中 | abs(consumption_tax_sales - vat_sales) / vat_sales > 0.1 | 消费税收入、增值税收入 | 核查收入 |
| CONS-007 | 成品油消费税异常 | 中 | oil_consumption_tax != calculated | 成品油、消费税 | 核查成品油 |
| CONS-008 | 白酒消费税异常 | 中 | baijiu_consumption_tax != calculated | 白酒、消费税 | 核查白酒 |

### P. 资源税/环保税 RES/ENV（5）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| RES-001 | 资源税计税依据异常 | 中 | abs(resource_tax_base - sales_quantity) > threshold | 资源税基数、销售量 | 核查依据 |
| RES-002 | 资源税税目适用错误 | 中 | applied_resource_item != correct_item | 适用税目、正确税目 | 核查税目 |
| ENV-001 | 环保税排放量申报异常 | 中 | emission_declared != emission_actual | 申报排放量、实际排放量 | 核查排放 |
| ENV-002 | 环保税减免适用错误 | 中 | env_tax_reduction and condition not met | 减免、条件 | 核查减免 |
| ENV-003 | 环保税与排污许可差异 | 中 | abs(env_tax_emission - permit_emission) > threshold | 环保税排放、排污许可 | 核查差异 |

### Q. 税收优惠 TAXINC（17）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| TAXINC-001 | 优惠条件不满足但享受优惠 | 高 | incentive_condition_met = false and incentive_claimed = true | 优惠条件、享受优惠 | 核查条件 |
| TAXINC-002 | 优惠备案缺失 | 中 | incentive_claimed = true and filing_missing = true | 优惠、备案 | 核查备案 |
| TAXINC-003 | 优惠金额计算错误 | 中 | incentive_amount != calculated_incentive | 优惠金额、计算值 | 核查计算 |
| TAXINC-004 | 叠加享受优惠 | 中 | overlapping_incentives = true | 叠加优惠 | 核查叠加 |
| TAXINC-005 | 优惠期间错误 | 中 | incentive_period != correct_period | 优惠期间、正确期间 | 核查期间 |
| TAXINC-006 | 高新优惠异常 | 中 | high_tech_condition_met = false and high_tech_deduction > 0 | 高新条件、优惠 | 核查高新 |
| TAXINC-007 | 小微优惠异常 | 中 | small_micro_condition_met = false and small_micro_deduction > 0 | 小微条件、优惠 | 核查小微 |
| TAXINC-008 | 研发加计扣除异常 | 中 | R&D_condition_met = false and R&D_deduction > 0 | 研发条件、加计扣除 | 核查研发 |
| TAXINC-009 | 西部大开发优惠异常 | 中 | western_condition_met = false and western_deduction > 0 | 西部条件、优惠 | 核查西部 |
| TAXINC-010 | 软件企业优惠异常 | 中 | software_condition_met = false and software_deduction > 0 | 软件条件、优惠 | 核查软件 |
| TAXINC-011 | 资源综合利用优惠异常 | 中 | resource_condition_met = false and resource_deduction > 0 | 资源条件、优惠 | 核查资源 |
| TAXINC-012 | 残疾人就业优惠异常 | 中 | disabled_condition_met = false and disabled_deduction > 0 | 残疾人条件、优惠 | 核查残疾人 |
| TAXINC-013 | 优惠条件不满足但享受 | 高 | incentive_condition_met = false and incentive_claimed = true | 优惠条件、享受优惠 | 核查条件 |
| TAXINC-014 | 优惠备案缺失 | 中 | incentive_claimed and filing_missing | 优惠、备案 | 核查备案 |
| TAXINC-015 | 优惠金额计算错误 | 中 | incentive_amount != calculated_incentive | 优惠金额、计算值 | 核查计算 |
| TAXINC-016 | 叠加享受优惠 | 中 | overlapping_incentives = true | 叠加优惠 | 核查叠加 |
| TAXINC-017 | 优惠期间错误 | 中 | incentive_period != correct_period | 优惠期间、正确期间 | 核查期间 |

> **注**：TAXINC-013 至 TAXINC-017 与 TAXINC-001 至 TAXINC-005 重复，见第五部分去重说明。

### R. 通用申报 GEN（14）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| GEN-001 | 申报表间数据不一致 | 高 | abs(return_a - return_b) / return_b > 0.1 | 申报表A、申报表B | 核查申报 |
| GEN-002 | 申报数据与财务报表不一致 | 高 | abs(tax_return - financial_statement) / financial_statement > 0.1 | 申报数据、财务报表 | 核查差异 |
| GEN-003 | 申报数据与发票数据不一致 | 高 | abs(tax_return - invoice_data) / invoice_data > 0.1 | 申报数据、发票数据 | 核查差异 |
| GEN-004 | 申报数据与银行流水不一致 | 高 | abs(tax_return - bank_flow) / bank_flow > 0.2 | 申报数据、银行流水 | 核查差异 |
| GEN-005 | 申报数据与社保数据不一致 | 中 | abs(tax_return - social_security) / social_security > 0.2 | 申报数据、社保数据 | 核查差异 |
| GEN-006 | 申报数据与工商年报不一致 | 中 | abs(tax_return - annual_report) / annual_report > 0.2 | 申报数据、工商年报 | 核查差异 |
| GEN-007 | 申报逾期 | 中 | declaration_date > due_date | 申报日期、截止日期 | 核查逾期 |
| GEN-008 | 零申报异常 | 中 | zero_declaration_months > 6 and business_active = true | 零申报月份、经营状态 | 核查零申报 |
| GEN-009 | 负申报异常 | 中 | negative_declaration_months > 3 | 负申报月份 | 核查负申报 |
| GEN-010 | 申报税种缺失 | 高 | required_tax_types not in declared_tax_types | 应报税种、已报税种 | 核查缺失 |
| GEN-011 | 申报期间缺失 | 中 | missing_periods > 0 | 申报期间 | 核查缺失 |
| GEN-012 | 申报金额突变 | 中 | abs(current_amount - last_amount) / last_amount > 0.5 | 本期金额、上期金额 | 核查突变 |
| GEN-013 | 申报频率异常 | 低 | declaration_frequency > threshold | 申报频率 | 核查频率 |
| GEN-014 | 同一法人多企业关联申报异常 | 中 | same_legal_person_companies > threshold and abnormal_related_declaration = true | 同一法人企业、申报 | 核查关联 |

### S. 小税种补充（30）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| DEED-001 | 契税计税依据偏低 | 高 | deed_tax_base < contract_amount * 0.9 | 契税基数、合同金额 | 核查计税依据 |
| DEED-002 | 土地使用权出让契税未申报 | 高 | land_transfer_amount > 0 and deed_tax_paid = 0 | 土地出让金额、契税 | 核查申报 |
| DEED-003 | 房屋买卖契税未申报 | 高 | house_transfer_amount > 0 and deed_tax_paid = 0 | 房屋转让金额、契税 | 核查申报 |
| DEED-004 | 契税税率适用错误 | 中 | applied_deed_rate != correct_rate | 适用税率、正确税率 | 核查税率 |
| DEED-005 | 契税减免条件不符 | 中 | deed_tax_reduction and condition not met | 减免、条件 | 核查减免 |
| GOT-001 | 耕地占用税未申报 | 高 | occupied_farmland_area > 0 and farmland_tax_paid = 0 | 占用耕地面积、耕地占用税 | 核查申报 |
| GOT-002 | 耕地占用税计税面积异常 | 中 | abs(tax_area - actual_area) / actual_area > 0.1 | 计税面积、实际面积 | 核查面积 |
| GOT-003 | 耕地占用税减免异常 | 中 | farmland_tax_reduction and condition not met | 减免、条件 | 核查减免 |
| VET-001 | 车船税未申报 | 中 | vehicle_count > 0 and vehicle_tax_paid = 0 | 车辆数量、车船税 | 核查申报 |
| VET-002 | 车船税计税依据异常 | 中 | vehicle_tax_base != correct_base | 计税依据、正确依据 | 核查依据 |
| VET-003 | 车船税减免异常 | 中 | vehicle_tax_reduction and condition not met | 减免、条件 | 核查减免 |
| VPT-001 | 车辆购置税未申报 | 高 | vehicle_purchase_amount > 0 and vpt_paid = 0 | 购车金额、车辆购置税 | 核查申报 |
| VPT-002 | 车辆购置税计税价格偏低 | 中 | vpt_base < market_price * 0.9 | 计税价格、市场价 | 核查价格 |
| VPT-003 | 车辆购置税减免异常 | 中 | vpt_reduction and condition not met | 减免、条件 | 核查减免 |
| CUS-001 | 关税完税价格异常 | 高 | customs_value < invoice_value * 0.9 | 完税价格、发票金额 | 核查完税价格 |
| CUS-002 | 关税税率适用错误 | 中 | applied_customs_rate != correct_rate | 适用税率、正确税率 | 核查税率 |
| CUS-003 | 关税减免异常 | 中 | customs_reduction and condition not met | 减免、条件 | 核查减免 |
| TON-001 | 船舶吨税未申报 | 中 | ship_tonnage > 0 and tonnage_tax_paid = 0 | 船舶吨位、吨税 | 核查申报 |
| TOB-001 | 烟叶税未申报 | 中 | tobacco_purchase_amount > 0 and tobacco_tax_paid = 0 | 烟叶收购金额、烟叶税 | 核查申报 |
| TOB-002 | 烟叶税计税依据异常 | 中 | tobacco_tax_base != purchase_amount | 计税依据、收购金额 | 核查依据 |
| CUL-001 | 文化事业建设费未申报 | 中 | advertising_revenue > 0 and cultural_fee_paid = 0 | 广告收入、文化事业建设费 | 核查申报 |
| CUL-002 | 文化事业建设费计税依据异常 | 中 | abs(cultural_fee_base - advertising_revenue) / advertising_revenue > 0.1 | 计费基数、广告收入 | 核查依据 |
| WAT-001 | 水利建设基金未申报 | 中 | sales_revenue > 0 and water_fund_paid = 0 | 销售收入、水利基金 | 核查申报 |
| WAT-002 | 水利建设基金计税依据异常 | 中 | abs(water_fund_base - sales_revenue) / sales_revenue > 0.1 | 计费基数、收入 | 核查依据 |
| SUR-006 | 地方教育附加未申报 | 中 | vat_payable > 0 and local_edu_surcharge_paid = 0 | 增值税、地方教育附加 | 核查申报 |
| SUR-007 | 教育费附加减免异常 | 中 | edu_surcharge_reduction and condition not met | 减免、条件 | 核查减免 |
| SUR-008 | 附加税费退库异常 | 中 | surtax_refund > 0 and vat_refund = 0 | 附加税费退库、增值税退税 | 核查退库 |
| SUR-009 | 附加税费跨期异常 | 中 | surtax_period != vat_period | 附加税费期间、增值税期间 | 核查期间 |
| SUR-010 | 附加税费申报表间差异 | 中 | abs(surtax_return_a - surtax_return_b) > threshold | 申报表A、申报表B | 核查申报 |

> **注**：SUR-006 至 SUR-010 与 I 部分重复，见第五部分去重说明。
> **计数据实说明**：本节标题为「30 条」，**实际列示 29 条**（DEED 5 + GOT 3 + VET 3 + VPT 3 + CUS 3 + TON 1 + TOB 2 + CUL 2 + WAT 2 + SUR 5）。
> 与 `config/rulelist_v12.json::count_discrepancy` 记录一致（「组一实际 29 条」），**按实际列示登记，不按标题**。

### T. 税收征管与申报补充 ADM（20）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| ADM-001 | 税务登记信息与工商信息不一致 | 中 | tax_registration != business_registration | 税务登记、工商登记 | 核查登记 |
| ADM-002 | 财务负责人/办税人异常 | 中 | same_person_multi_companies > threshold | 人员、企业数 | 核查关联 |
| ADM-003 | 注册地址异常 | 中 | registered_address_virtual = true | 注册地址、虚拟地址标识 | 核查地址 |
| ADM-004 | 发票领用异常 | 中 | invoice_quota_increase_abnormal = true | 发票领用、调整 | 核查领用 |
| ADM-005 | 税控设备异常 | 中 | tax_device_abnormal = true | 税控设备 | 核查设备 |
| ADM-006 | 申报表逻辑校验异常 | 高 | return_logic_check_failed = true | 申报表逻辑 | 核查申报 |
| ADM-007 | 申报数据篡改痕迹 | 高 | return_amended_count > threshold | 更正次数 | 核查更正 |
| ADM-008 | 多次更正申报 | 中 | amended_count > 3 | 更正次数 | 核查原因 |
| ADM-009 | 申报与缴款不一致 | 高 | abs(declared_tax - paid_tax) > threshold | 申报税额、缴款税额 | 核查缴款 |
| ADM-010 | 欠税未清缴 | 高 | tax_arrears > 0 | 欠税金额 | 核查欠税 |
| ADM-011 | 滞纳金异常 | 中 | late_fee > threshold | 滞纳金 | 核查滞纳 |
| ADM-012 | 延期申报异常 | 中 | extension_declaration_count > threshold | 延期申报次数 | 核查延期 |
| ADM-013 | 延期缴税异常 | 中 | extension_payment_count > threshold | 延期缴税次数 | 核查延期 |
| ADM-014 | 税收优惠备案缺失 | 中 | incentive_claimed and filing_missing | 优惠、备案 | 核查备案 |
| ADM-015 | 跨区域涉税事项未报验 | 中 | cross_region_project and report_missing | 跨区域项目、报验 | 核查报验 |
| ADM-016 | 外管证未核销 | 中 | external_management_certificate_not_cancelled | 外管证 | 核查核销 |
| ADM-017 | 总分机构汇总纳税异常 | 高 | headquarters_branch_allocation_abnormal | 总分机构、分配 | 核查汇总 |
| ADM-018 | 合并纳税异常 | 中 | consolidated_tax_filing_abnormal | 合并纳税 | 核查合并 |
| ADM-019 | 税收洼地注册异常 | 中 | tax_haven_registration = true | 注册地、税收洼地 | 核查实质 |
| ADM-020 | 财政返还与税收挂钩 | 高 | fiscal_refund_linked_to_tax = true | 财政返还、税收 | 核查返还 |

### U. 反避税与转让定价 AA（20）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| AA-001 | 关联交易定价偏离市场 | 高 | abs(related_price - market_price)/market_price> 0.2 | 关联价、市场价 | 核查转让定价 |
| AA-002 | 关联交易占比过高 | 中 | related_transaction_ratio > 0.5 | 关联交易、总收入 | 核查关联 |
| AA-003 | 关联方资金占用 | 高 | related_party_receivable > threshold | 关联方应收 | 核查资金占用 |
| AA-004 | 关联方借款利率异常 | 高 | related_loan_rate > market_rate * 1.5 | 关联利率、市场利率 | 核查利息 |
| AA-005 | 关联方劳务费用异常 | 中 | related_service_fee > threshold | 关联劳务费 | 核查劳务 |
| AA-006 | 关联方资产转让异常 | 高 | related_asset_transfer_price != fair_value | 关联资产转让、公允价值 | 核查转让 |
| AA-007 | 关联方股权转让异常 | 高 | related_equity_transfer_price != fair_value | 关联股权转让、公允价值 | 核查转让 |
| AA-008 | 关联方债务豁免 | 中 | related_party_debt_forgiveness > 0 | 债务豁免 | 核查税务处理 |
| AA-009 | 关联方承担费用 | 中 | related_party_expense_bearing > 0 | 关联方费用承担 | 核查费用 |
| AA-010 | 成本分摊协议异常 | 中 | cost_sharing_agreement_abnormal = true | 成本分摊协议 | 核查分摊 |
| AA-011 | 预约定价安排未执行 | 中 | APA_exists and actual_transaction != APA_terms | APA、实际交易 | 核查执行 |
| AA-012 | 同期资料缺失 | 中 | related_transaction_threshold_met and contemporaneous_docs_missing | 关联交易、同期资料 | 核查资料 |
| AA-013 | 国别报告缺失 | 中 | CbCR_required and CbCR_missing | 国别报告要求、提交 | 核查报告 |
| AA-014 | 主体文档缺失 | 中 | master_file_required and master_file_missing | 主体文档 | 核查文档 |
| AA-015 | 本地文档缺失 | 中 | local_file_required and local_file_missing | 本地文档 | 核查文档 |
| AA-016 | 特殊事项文档缺失 | 中 | special_file_required and special_file_missing | 特殊事项文档 | 核查文档 |
| AA-017 | 合理商业目的不足 | 高 | reasonable_business_purpose_score < threshold | 商业目的评分 | 核查目的 |
| AA-018 | 导管公司特征 | 高 | conduit_company_indicators > threshold | 导管公司指标 | 核查实质 |
| AA-019 | 择协避税特征 | 高 | treaty_shopping_indicators > threshold | 择协避税指标 | 核查受益所有人 |
| AA-020 | 主要目的测试未通过 | 高 | principal_purpose_test_failed = true | 主要目的测试 | 核查协定优惠 |

> **注**：AA-001 至 AA-009 与 L 部分 REL-001 至 REL-009 高度重叠，见第五部分去重说明。

### V. 国际税收与非居民 INT（20）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| INT-001 | 非居民预提所得税未代扣 | 高 | non_resident_income > 0 and withholding_tax = 0 | 非居民所得、预提税 | 核查代扣 |
| INT-002 | 非居民股息预提税异常 | 高 | dividend_to_non_resident > 0 and withholding_tax < correct_tax | 股息、预提税 | 核查代扣 |
| INT-003 | 非居民利息预提税异常 | 高 | interest_to_non_resident > 0 and withholding_tax < correct_tax | 利息、预提税 | 核查代扣 |
| INT-004 | 非居民特许权使用费预提税异常 | 高 | royalty_to_non_resident > 0 and withholding_tax < correct_tax | 特许权使用费、预提税 | 核查代扣 |
| INT-005 | 非居民财产转让预提税异常 | 高 | property_transfer_to_non_resident > 0 and withholding_tax = 0 | 财产转让、预提税 | 核查代扣 |
| INT-006 | 常设机构判定异常 | 高 | permanent_establishment_indicators > threshold | 常设机构指标 | 核查常设机构 |
| INT-007 | 国际运输税收异常 | 中 | international_transport_income > 0 and tax_treatment_abnormal | 国际运输收入、税务处理 | 核查处理 |
| INT-008 | 税收协定优惠适用异常 | 高 | treaty_benefit_claimed and beneficial_owner_test_failed | 协定优惠、受益所有人 | 核查受益所有人 |
| INT-009 | 受益所有人认定异常 | 高 | beneficial_owner_indicators < threshold | 受益所有人指标 | 核查认定 |
| INT-010 | 境外所得未申报 | 高 | overseas_income > 0 and declared_overseas_income = 0 | 境外所得、申报 | 核查申报 |
| INT-011 | 境外所得抵免异常 | 高 | foreign_tax_credit > correct_credit | 境外抵免、正确抵免 | 核查抵免 |
| INT-012 | 直接抵免异常 | 中 | direct_credit_abnormal = true | 直接抵免 | 核查抵免 |
| INT-013 | 间接抵免异常 | 中 | indirect_credit_abnormal = true | 间接抵免 | 核查抵免 |
| INT-014 | 分国不分项抵免异常 | 中 | country_by_country_credit_abnormal = true | 分国抵免 | 核查计算 |
| INT-015 | 综合抵免异常 | 中 | comprehensive_credit_abnormal = true | 综合抵免 | 核查计算 |
| INT-016 | 饶让抵免异常 | 中 | tax_sparing_credit_abnormal = true | 饶让抵免 | 核查计算 |
| INT-017 | CRS信息申报异常 | 中 | CRS_reporting_missing = true | CRS申报 | 核查申报 |
| INT-018 | 对外支付备案缺失 | 中 | outbound_payment > threshold and filing_missing = true | 对外支付、备案 | 核查备案 |
| INT-019 | 服务贸易对外支付税务备案异常 | 中 | service_trade_payment > threshold and tax_filing_missing | 服务贸易支付、备案 | 核查备案 |
| INT-020 | 非居民享受协定待遇后续管理异常 | 中 | treaty_benefit_followup_missing = true | 协定待遇、后续管理 | 核查管理 |

### W. 企业重组与资本交易 REO（15）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| REO-001 | 股权收购特殊性税务处理异常 | 高 | special_tax_treatment and conditions_not_met | 特殊性税务处理、条件 | 核查条件 |
| REO-002 | 资产收购特殊性税务处理异常 | 高 | special_tax_treatment and conditions_not_met | 特殊性税务处理、条件 | 核查条件 |
| REO-003 | 企业合并特殊性税务处理异常 | 高 | special_tax_treatment and conditions_not_met | 特殊性税务处理、条件 | 核查条件 |
| REO-004 | 企业分立特殊性税务处理异常 | 高 | special_tax_treatment and conditions_not_met | 特殊性税务处理、条件 | 核查条件 |
| REO-005 | 债务重组特殊性税务处理异常 | 高 | special_tax_treatment and conditions_not_met | 特殊性税务处理、条件 | 核查条件 |
| REO-006 | 股权转让所得未申报 | 高 | equity_transfer_income > 0 and tax_declared = 0 | 股权转让所得、申报 | 核查申报 |
| REO-007 | 股权转让价格偏低 | 高 | transfer_price < fair_value * 0.7 | 转让价格、公允价值 | 核查价格 |
| REO-008 | 非货币性资产投资税务处理异常 | 高 | non_monetary_asset_investment and tax_treatment_abnormal | 非货币资产投资、税务处理 | 核查处理 |
| REO-009 | 技术入股递延纳税异常 | 中 | technology_equity_investment and deferred_tax_conditions_not_met | 技术入股、递延条件 | 核查递延 |
| REO-010 | 股权激励递延纳税异常 | 中 | equity_incentive and deferred_tax_conditions_not_met | 股权激励、递延条件 | 核查递延 |
| REO-011 | 转增股本个税异常 | 中 | capital_reserve_to_equity > 0 and IIT_withheld = 0 | 转增股本、个税 | 核查个税 |
| REO-012 | 未分配利润转增个税异常 | 中 | retained_earnings_to_equity > 0 and IIT_withheld = 0 | 未分配利润转增、个税 | 核查个税 |
| REO-013 | 资本公积转增个税异常 | 中 | capital_reserve_to_equity > 0 and IIT_withheld = 0 | 资本公积转增、个税 | 核查个税 |
| REO-014 | 间接转让中国应税财产未申报 | 高 | indirect_transfer_china_taxable_property and tax_declared = 0 | 间接转让、申报 | 核查申报 |
| REO-015 | 合理商业目的不足 | 高 | reasonable_business_purpose_score < threshold | 商业目的评分 | 核查目的 |

### X. 房地产与建筑 EST/CONSTR（20）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| EST-001 | 预收房款未预缴增值税 | 高 | pre_sale_revenue > 0 and vat_prepaid = 0 | 预收房款、预缴增值税 | 核查预缴 |
| EST-002 | 预收房款未预缴土地增值税 | 高 | pre_sale_revenue > 0 and lat_prepaid = 0 | 预收房款、预缴土地增值税 | 核查预缴 |
| EST-003 | 预收房款未预计毛利 | 高 | pre_sale_revenue > 0 and estimated_gross_profit = 0 | 预收房款、预计毛利 | 核查所得税 |
| EST-004 | 开发产品完工未结转 | 高 | project_completed and revenue_not_recognized | 完工项目、收入确认 | 核查结转 |
| EST-005 | 开发成本分摊异常 | 中 | cost_allocation_ratio != reasonable_ratio | 成本分摊、合理比例 | 核查分摊 |
| EST-006 | 土地成本扣除异常 | 中 | land_cost_deduction > threshold | 土地成本、扣除 | 核查扣除 |
| EST-007 | 拆迁补偿费异常 | 中 | relocation_compensation > threshold | 拆迁补偿、凭证 | 核查补偿 |
| EST-008 | 公共配套费异常 | 中 | public_facilities_cost > threshold | 公共配套费 | 核查成本 |
| EST-009 | 开发间接费异常 | 中 | development_indirect_cost > threshold | 开发间接费 | 核查费用 |
| EST-010 | 利息支出扣除异常 | 中 | interest_deduction > threshold | 利息支出、扣除限额 | 核查利息 |
| CONSTR-001 | 建筑服务预缴增值税异常 | 高 | construction_service_revenue > 0 and vat_prepaid = 0 | 建筑服务收入、预缴增值税 | 核查预缴 |
| CONSTR-002 | 异地施工未预缴 | 高 | cross_region_construction and vat_prepaid = 0 | 异地施工、预缴 | 核查预缴 |
| CONSTR-003 | 简易计税适用异常 | 中 | simplified_tax_method and conditions_not_met | 简易计税、条件 | 核查适用 |
| CONSTR-004 | 甲供材税务处理异常 | 中 | owner_supplied_materials and tax_treatment_abnormal | 甲供材、税务处理 | 核查处理 |
| CONSTR-005 | 清包工税务处理异常 | 中 | labor_only_contract and tax_treatment_abnormal | 清包工、税务处理 | 核查处理 |
| CONSTR-006 | 分包款扣除异常 | 中 | subcontract_deduction > threshold | 分包款、扣除 | 核查扣除 |
| CONSTR-007 | 挂靠经营税务风险 | 高 | affiliation_business = true | 挂靠经营 | 核查主体 |
| CONSTR-008 | 转包税务风险 | 高 | subcontracting = true | 转包 | 核查转包 |
| CONSTR-009 | 项目部个税未申报 | 中 | project_department_salary > 0 and IIT_declared = 0 | 项目部工资、个税 | 核查个税 |
| CONSTR-010 | 项目部社保未缴纳 | 中 | project_department_salary > 0 and social_insured = false | 项目部工资、社保 | 核查社保 |

### Y. 平台经济、灵活用工、高净值个人 PLAT/FLEX/HNW（20）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| PLAT-001 | 平台佣金收入未申报 | 高 | platform_commission_income > 0 and tax_declared = 0 | 平台佣金、申报 | 核查申报 |
| PLAT-002 | 平台打赏收入未申报 | 高 | live_reward_income > 0 and tax_declared = 0 | 打赏收入、申报 | 核查申报 |
| PLAT-003 | 主播个税未代扣 | 高 | anchor_income > 0 and IIT_withheld = 0 | 主播收入、个税 | 核查代扣 |
| PLAT-004 | MCN机构税务处理异常 | 中 | MCN_income_allocation_abnormal | MCN收入、分配 | 核查处理 |
| PLAT-005 | 平台灵活用工结算异常 | 高 | flexible_employment_settlement > threshold and invoice_abnormal | 灵活用工结算、发票 | 核查结算 |
| PLAT-006 | 委托代征异常 | 高 | entrusted_collection and conditions_not_met | 委托代征、条件 | 核查代征 |
| PLAT-007 | 汇总代开发票异常 | 中 | aggregated_invoice_abnormal = true | 汇总代开 | 核查代开 |
| PLAT-008 | 自然人代开异常 | 中 | natural_person_invoice > threshold | 自然人代开 | 核查代开 |
| PLAT-009 | 临时税务登记异常 | 中 | temporary_tax_registration > threshold | 临时税务登记 | 核查登记 |
| PLAT-010 | 集群注册异常 | 中 | cluster_registration > threshold | 集群注册 | 核查注册 |
| FLEX-001 | 劳务外包变相用工 | 高 | labor_outsourcing_ratio > 0.5 and actual_employment = true | 劳务外包、实际用工 | 核查实质 |
| FLEX-002 | 劳务派遣比例超标 | 中 | dispatch_worker_ratio > 0.1 | 派遣比例 | 核查比例 |
| FLEX-003 | 社保代缴异常 | 高 | social_security_agency > 0 and actual_employer != agency | 社保代缴、实际雇主 | 核查代缴 |
| FLEX-004 | 个税代征异常 | 高 | IIT_collection_agency and conditions_not_met | 个税代征、条件 | 核查代征 |
| FLEX-005 | 薪酬代发异常 | 中 | salary_payment_agency > threshold | 薪酬代发 | 核查代发 |
| HNW-001 | 高净值个人税负偏低 | 高 | high_net_worth_tax_burden < threshold | 高净值个人、税负 | 核查申报 |
| HNW-002 | 境外资产未申报 | 高 | overseas_asset > 0 and declared = 0 | 境外资产、申报 | 核查申报 |
| HNW-003 | 境外收入未申报 | 高 | overseas_income > 0 and declared = 0 | 境外收入、申报 | 核查申报 |
| HNW-004 | 家族信托税务处理异常 | 中 | family_trust_tax_treatment_abnormal | 家族信托、税务处理 | 核查处理 |
| HNW-005 | 大额保单税务处理异常 | 中 | large_insurance_policy > threshold | 大额保单 | 核查处理 |

### Z. 金融与特殊交易（20）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| FINA-001 | 贷款利息收入未申报 | 高 | loan_interest_income > 0 and tax_declared = 0 | 利息收入、申报 | 核查申报 |
| FINA-002 | 金融商品转让税务处理异常 | 中 | financial_asset_transfer and tax_treatment_abnormal | 金融商品转让、税务处理 | 核查处理 |
| FINA-003 | 贷款损失准备金扣除异常 | 中 | loan_loss_provision > threshold | 贷款损失准备金 | 核查扣除 |
| LEASE-001 | 融资租赁税务处理异常 | 高 | finance_lease and tax_treatment_abnormal | 融资租赁、税务处理 | 核查处理 |
| LEASE-002 | 融资性售后回租异常 | 高 | sale_leaseback and tax_treatment_abnormal | 售后回租、税务处理 | 核查处理 |
| LEASE-003 | 经营租赁税务处理异常 | 中 | operating_lease and tax_treatment_abnormal | 经营租赁、税务处理 | 核查处理 |
| FACT-001 | 保理利息税务处理异常 | 中 | factoring_interest and tax_treatment_abnormal | 保理利息、税务处理 | 核查处理 |
| MICRO-001 | 小贷公司利息收入未申报 | 高 | micro_loan_interest > 0 and tax_declared = 0 | 小贷利息、申报 | 核查申报 |
| GUAR-001 | 担保费收入未申报 | 中 | guarantee_fee_income > 0 and tax_declared = 0 | 担保费、申报 | 核查申报 |
| PAWN-001 | 典当利息税务处理异常 | 中 | pawn_interest and tax_treatment_abnormal | 典当利息、税务处理 | 核查处理 |
| PE-001 | 私募基金税务处理异常 | 中 | private_equity_fund and tax_treatment_abnormal | 私募基金、税务处理 | 核查处理 |
| FUNDM-001 | 公募基金税务处理异常 | 中 | public_fund and tax_treatment_abnormal | 公募基金、税务处理 | 核查处理 |
| TRUST-001 | 信托收益税务处理异常 | 中 | trust_income and tax_treatment_abnormal | 信托收益、税务处理 | 核查处理 |
| REIT-001 | REITs税务处理异常 | 中 | REITs and tax_treatment_abnormal | REITs、税务处理 | 核查处理 |
| REIT-002 | REITs分红税务处理异常 | 中 | REITs_dividend and tax_treatment_abnormal | REITs分红、税务处理 | 核查处理 |
| PPP-001 | PPP项目税务处理异常 | 中 | PPP_project and tax_treatment_abnormal | PPP项目、税务处理 | 核查处理 |
| EPC-001 | EPC合同税务处理异常 | 中 | EPC_contract and tax_treatment_abnormal | EPC合同、税务处理 | 核查处理 |
| BOT-001 | BOT项目税务处理异常 | 中 | BOT_project and tax_treatment_abnormal | BOT项目、税务处理 | 核查处理 |
| ABS-001 | 资产证券化税务处理异常 | 中 | ABS_transaction and tax_treatment_abnormal | ABS交易、税务处理 | 核查处理 |

> **计数据实说明**：本节标题为「20 条」，**实际列示 19 条**（FINA 3 + LEASE 3 + FACT 1 + MICRO 1 + GUAR 1 + PAWN 1 + PE 1 + FUNDM 1 + TRUST 1 + REIT 2 + PPP 1 + EPC 1 + BOT 1 + ABS 1）。**按实际列示登记，不按标题。**

### AA. 海关、保税、自贸区、海南自贸港（15）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| CUSTOMS-001 | 保税料件内销未补税 | 高 | bonded_material_domestic_sale > 0 and tax_paid = 0 | 保税料件内销、补税 | 核查补税 |
| CUSTOMS-002 | 加工贸易核销异常 | 中 | processing_trade_verification_abnormal | 加工贸易核销 | 核查核销 |
| CUSTOMS-003 | 海关完税价格异常 | 高 | customs_value < invoice_value * 0.9 | 完税价格、发票金额 | 核查价格 |
| CUSTOMS-004 | 关税减免异常 | 中 | customs_reduction and condition not met | 减免、条件 | 核查减免 |
| BOND-001 | 保税区税务处理异常 | 中 | bonded_zone and tax_treatment_abnormal | 保税区、税务处理 | 核查处理 |
| BOND-002 | 综合保税区税务处理异常 | 中 | comprehensive_bonded_zone and tax_treatment_abnormal | 综保区、税务处理 | 核查处理 |
| FTZ-001 | 自贸区税务处理异常 | 中 | free_trade_zone and tax_treatment_abnormal | 自贸区、税务处理 | 核查处理 |
| HAINAN-001 | 海南自贸港15%所得税异常 | 高 | hainan_15_percent and conditions_not_met | 海南优惠、条件 | 核查条件 |
| HAINAN-002 | 海南自贸港个税优惠异常 | 高 | hainan_IIT_incentive and conditions_not_met | 海南个税优惠、条件 | 核查条件 |
| HAINAN-003 | 离岛免税异常 | 中 | duty_free_island and conditions_not_met | 离岛免税、条件 | 核查条件 |
| HAINAN-004 | 跨境电商保税进口异常 | 中 | cross_border_bonded_import and tax_treatment_abnormal | 跨境电商保税进口 | 核查处理 |
| EXPORT-011 | 出口退税函调异常 | 高 | tax_refund_investigation_abnormal = true | 函调结果 | 核查函调 |
| EXPORT-012 | 出口收汇异常 | 中 | export_receipt_missing = true | 出口收汇 | 核查收汇 |
| EXPORT-013 | 出口转内销未申报 | 中 | export_to_domestic > 0 and tax_declared = 0 | 出口转内销、申报 | 核查申报 |
| EXPORT-014 | 跨境电商无票免税异常 | 中 | cross_border_ecommerce_tax_free and conditions_not_met | 无票免税、条件 | 核查条件 |

### AB. 核定征收、注销清算、破产重整（12）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| ASSESS-001 | 核定征收条件不符 | 高 | assessed_collection and conditions_not_met | 核定征收、条件 | 核查条件 |
| ASSESS-002 | 核定征收率异常 | 中 | assessed_rate < industry_avg_rate * 0.7 | 核定率、行业均值 | 核查核定 |
| ASSESS-003 | 核定征收企业收入异常 | 中 | assessed_income < actual_income * 0.7 | 核定收入、实际收入 | 核查收入 |
| ASSESS-004 | 个人独资/合伙核定异常 | 高 | sole_proprietorship_or_partnership and assessed_collection and conditions_not_met | 个独/合伙、核定、条件 | 核查条件 |
| LIQ-001 | 注销清算未申报 | 高 | liquidation and tax_declared = 0 | 清算、申报 | 核查申报 |
| LIQ-002 | 清算所得计算异常 | 高 | liquidation_income != calculated_income | 清算所得、计算值 | 核查计算 |
| LIQ-003 | 股东分得剩余资产税务处理异常 | 高 | residual_asset_distribution and tax_treatment_abnormal | 剩余资产分配、税务处理 | 核查处理 |
| LIQ-004 | 清算期间经营所得未申报 | 高 | liquidation_period_income > 0 and tax_declared = 0 | 清算期间所得、申报 | 核查申报 |
| BANKR-001 | 破产重整税务处理异常 | 中 | bankruptcy_reorganization and tax_treatment_abnormal | 破产重整、税务处理 | 核查处理 |
| BANKR-002 | 债务重组所得未申报 | 高 | debt_restructuring_income > 0 and tax_declared = 0 | 债务重组所得、申报 | 核查申报 |
| BANKR-003 | 资产处置损失异常 | 中 | asset_disposal_loss > threshold | 资产处置损失 | 核查损失 |
| BANKR-004 | 破产财产分配税务处理异常 | 中 | bankruptcy_asset_distribution and tax_treatment_abnormal | 破产财产分配、税务处理 | 核查处理 |

### AC. 电子发票、留抵退税（10）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| EINV-001 | 电子发票重复报销 | 中 | duplicate_e_invoice = true | 电子发票、报销记录 | 核查重复 |
| EINV-002 | 全电发票红冲异常 | 中 | full_e_invoice_void_abnormal = true | 全电发票、红冲 | 核查红冲 |
| EINV-003 | 数电票开具异常 | 中 | digital_invoice_abnormal = true | 数电票 | 核查开具 |
| EINV-004 | 发票查验异常 | 中 | invoice_verification_failed = true | 发票查验 | 核查查验 |
| EINV-005 | 发票勾选异常 | 中 | invoice_selection_abnormal = true | 发票勾选 | 核查勾选 |
| RRT-001 | 留抵退税条件不符 | 高 | retained_tax_refund and conditions_not_met | 留抵退税、条件 | 核查条件 |
| RRT-002 | 增量留抵异常 | 高 | incremental_retained_tax_refund_abnormal | 增量留抵 | 核查计算 |
| RRT-003 | 存量留抵异常 | 高 | stock_retained_tax_refund_abnormal | 存量留抵 | 核查计算 |
| RRT-004 | 留抵抵欠异常 | 中 | retained_tax_offset_arrears_abnormal | 留抵抵欠 | 核查处理 |
| RRT-005 | 留抵退税后进项转出异常 | 中 | input_tax_transfer_out_after_refund_abnormal | 进项转出 | 核查转出 |

### AD. 行业特定补充（20）

| 规则ID | 规则名称 | 等级 | 触发逻辑 | 核心输入 | 建议 |
|---|---|---|---|---|---|
| HNTECH-001 | 高新条件不满足但享受优惠 | 高 | high_tech_condition_met = false and high_tech_deduction > 0 | 高新条件、优惠 | 核查高新 |
| HNTECH-002 | 高新研发费用占比异常 | 中 | R&D_ratio < required_ratio | 研发费用占比、要求 | 核查占比 |
| HNTECH-003 | 高新科技人员占比异常 | 中 | tech_personnel_ratio < required_ratio | 科技人员占比、要求 | 核查占比 |
| RD-001 | 研发费用加计扣除异常 | 中 | R&D_deduction and conditions_not_met | 研发加计、条件 | 核查条件 |
| RD-002 | 研发费用归集异常 | 中 | R&D_expense_allocation_abnormal | 研发费用归集 | 核查归集 |
| SOFT-001 | 软件企业优惠异常 | 中 | software_condition_met = false and software_deduction > 0 | 软件条件、优惠 | 核查软件 |
| IC-001 | 集成电路企业优惠异常 | 中 | IC_condition_met = false and IC_deduction > 0 | 集成电路条件、优惠 | 核查集成电路 |
| ANIME-001 | 动漫企业优惠异常 | 中 | anime_condition_met = false and anime_deduction > 0 | 动漫条件、优惠 | 核查动漫 |
| CULT-001 | 文化企业优惠异常 | 中 | culture_condition_met = false and culture_deduction > 0 | 文化条件、优惠 | 核查文化 |
| EDU-001 | 教育服务税务处理异常 | 中 | education_service and tax_treatment_abnormal | 教育服务、税务处理 | 核查处理 |
| MED-001 | 医疗服务税务处理异常 | 中 | medical_service and tax_treatment_abnormal | 医疗服务、税务处理 | 核查处理 |
| ELDER-001 | 养老服务税务处理异常 | 中 | elderly_care_service and tax_treatment_abnormal | 养老服务、税务处理 | 核查处理 |
| CHILD-001 | 托育服务税务处理异常 | 中 | childcare_service and tax_treatment_abnormal | 托育服务、税务处理 | 核查处理 |
| HOUSE-001 | 家政服务税务处理异常 | 中 | domestic_service and tax_treatment_abnormal | 家政服务、税务处理 | 核查处理 |
| SPORT-001 | 体育服务税务处理异常 | 中 | sports_service and tax_treatment_abnormal | 体育服务、税务处理 | 核查处理 |
| TOUR-001 | 旅游服务税务处理异常 | 中 | tourism_service and tax_treatment_abnormal | 旅游服务、税务处理 | 核查处理 |
| HOTEL-001 | 住宿服务税务处理异常 | 中 | hotel_service and tax_treatment_abnormal | 住宿服务、税务处理 | 核查处理 |
| CATER-001 | 餐饮服务税务处理异常 | 中 | catering_service and tax_treatment_abnormal | 餐饮服务、税务处理 | 核查处理 |
| ENT-001 | 娱乐服务税务处理异常 | 中 | entertainment_service and tax_treatment_abnormal | 娱乐服务、税务处理 | 核查处理 |
| CBEC-001 | 跨境电商税务处理异常 | 中 | cross_border_ecommerce and tax_treatment_abnormal | 跨境电商、税务处理 | 核查处理 |

---

## 五、已知重复项与去重说明

以下重复项**必须在第 2 步「规则去重合并」中处理，不能直接入库**。

| 重复组 | 重复规则 | 处理建议 |
|---|---|---|
| EXPORT 组 | EXPORT-011 至 EXPORT-013 与 EXPORT-006、009、010 重复 | 保留 EXPORT-006、009、010，废弃 011、012、013 |
| TAXINC 组 | TAXINC-013 至 TAXINC-017 与 TAXINC-001 至 TAXINC-005 重复 | 保留 TAXINC-001 至 005，废弃 013 至 017 |
| SUR 组 | S 部分 SUR-006 至 SUR-010 与 I 部分 SUR-006 至 SUR-010 重复 | 只保留一份，统一在 I 部分 |
| REL/AA 组 | AA-001 至 AA-009 与 REL-001 至 REL-009 高度重叠 | 保留 REL 系列作为基础关联交易规则，AA 系列只保留 AA-010 至 AA-020，或合并为统一关联交易规则集 |
| CIT/VAT 交叉 | CIT-012 与 REL-001、AA-001 重叠 | 保留 CIT-012 作为所得税视角，REL/AA 作为独立视角，或合并为统一规则 |
| CIT-028 与 IIT-003 | 股东借款视同分红，两处重复 | 保留一条，跨税种引用 |
| VAT-005 与 INV-001 | 进销项品名背离 | 保留一条，统一由 INV 系列管理 |
| VAT-007 与 INV-003 | 月末集中开票 | 保留一条，统一由 INV 系列管理 |
| VAT-008 与 INV-004 | 夜间开票 | 保留一条，统一由 INV 系列管理 |
| VAT-009 与 INV-005 | 作废红冲异常 | 保留一条，统一由 INV 系列管理 |
| VAT-010 与 INV-011 | 进项发票异常 | 保留一条，统一由 INV 系列管理 |
| VAT-024 与 INV-006 | 新办企业短期大量开票 | 保留一条，统一由 INV 系列管理 |
| VAT-026 与 FUND-004 | 银行流水与开票收入差异 | 保留一条，跨模块引用 |
| FIN-004 与 VAT-027 | 应收账款与收入变动背离 | 保留一条，统一由 FIN 系列管理 |
| FIN-014 与 VAT-028 | 存货与成本变动背离 | 保留一条，统一由 FIN 系列管理 |
| CONSTR-009 与 IIT 系列 | 项目部个税未申报 | 保留 CONSTR-009，引用 IIT 规则 |
| CONSTR-010 与 SI 系列 | 项目部社保未缴纳 | 保留 CONSTR-010，引用 SI 规则 |
| CUSTOMS-003 与 CUS-001 | 海关完税价格异常 | 保留一条，统一由 CUSTOMS 系列管理 |
| CUSTOMS-004 与 CUS-003 | 关税减免异常 | 保留一条，统一由 CUSTOMS 系列管理 |
| HAINAN 组与 TAXINC 组 | 海南优惠与通用优惠条件 | 保留 HAINAN 系列作为区域特定，TAXINC 作为通用 |
| EXPORT-014 与 EXPORT-001 | 出口退税条件不符 | 保留 EXPORT-001，EXPORT-014 作为跨境电商特定分支 |
| ASSESS-004 与 IIT-012 | 个独/合伙核定征收 | 保留 ASSESS-004，引用 IIT-012 |
| HNTECH-001 与 CIT-022 | 高新优惠异常 | 保留 CIT-022，HNTECH-001 作为行业特定补充 |
| RD-001 与 CIT-021 | 研发加计扣除异常 | 保留 CIT-021，RD-001 作为行业特定补充 |
| SOFT-001 与 TAXINC-010 | 软件企业优惠异常 | 保留 TAXINC-010，SOFT-001 作为行业特定补充 |

---

## 六、分批入库建议

**不要一次性把所有规则都入库。** 建议按以下批次逐步上线，每批校准后再扩展。

| 批次 | 范围 | 数量 | 说明 |
|---|---|---|---|
| 第 1 批（P0 核心） | VAT-001 至 VAT-010、CIT-001 至 CIT-010 | 20 | 最高频、最通用，先上线校准 |
| 第 2 批（P0 扩展） | INV-001 至 INV-010、FIN-001 至 FIN-010、GEN-001 至 GEN-010 | 30 | 发票、勾稽、申报一致性 |
| 第 3 批（P0 补充） | IIT-001 至 IIT-010、SI-001 至 SI-008、FUND-001 至 FUND-005 | 23 | 个税、社保、资金流 |
| 第 4 批（P1） | VAT-011 至 VAT-030、CIT-011 至 CIT-030 | 40 | 补齐增值税、所得税 |
| 第 5 批（P1） | REL、AA、INT、REO | 65 | 关联交易、反避税、国际税收、重组 |
| 第 6 批（P1） | SD、PCT、LUT、LAT、SUR、CONS、RES、ENV | 65 | 小税种 |
| 第 7 批（P1） | EST、CONSTR、PLAT、FLEX、HNW | 40 | 房地产、建筑、平台经济、高净值 |
| 第 8 批（P2） | FINA、LEASE、FACT、MICRO、GUAR、PAWN、PE、FUNDM、TRUST、REIT、PPP、EPC、BOT、ABS | 20 | 金融与特殊交易 |
| 第 9 批（P2） | CUSTOMS、BOND、FTZ、HAINAN、EXPORT | 29 | 海关、保税、自贸区、出口 |
| 第 10 批（P2） | ASSESS、LIQ、BANKR、EINV、RRT | 22 | 核定、注销、破产、电子发票、留抵 |
| 第 11 批（P2） | HNTECH、RD、SOFT、IC、ANIME、CULT、EDU、MED、ELDER、CHILD、HOUSE、SPORT、TOUR、HOTEL、CATER、ENT、CBEC | 20 | 行业特定补充 |

---

## 七、给 WorkBuddy 的附件使用说明

> **附件：rules_candidate.md 使用说明**
>
> 本文档是《财税稽查分析系统 · WorkBuddy 开发指令书 V1.0》**第 2 步「规则去重合并」**的附件。

### 你必须做的事

1. 扫描现有规则库，列出所有已有规则。
2. 将本文档中所有候选规则作为对比对象。
3. **逐条对比**：
   - 是否重复
   - 覆盖程度
   - 哪个更好
   - 处理方式：保留现有 / 采用候选 / 合并 / 新增 / 废弃
   - 合并后的 rule_id、名称、条件、阈值、证据、建议
4. **规则 ID 冲突时，以现有已上线规则为准**；补充规则使用命名空间 ID。
5. 所有阈值、行业均值、地区均值**必须参数化**。
6. 法规依据**只写 `legal_basis_ref`**，由法规库自动匹配。
7. **先不覆盖现有规则**，先生成对比报告和合并方案。

### 你必须输出的报告

**《规则去重合并报告》**，包含：

1. 现有规则清单
2. 候选规则清单
3. 逐条对比矩阵
4. 最终统一规则库版本号（例如 2025.3）
5. 规则与数据字段的映射关系
6. 待确认冲突项清单
7. 建议的首批入库规则（按第六部分分批建议）

### 约束

- **不直接照搬**候选规则。
- **不直接覆盖**现有规则。
- **不编造**法规条文。
- **不全量**一次性入库。
- 输出用 **Markdown**。

### 验收标准

- 每条候选规则都有**处理结论**。
- 有**统一版本号**。
- 有**首批入库建议**。
- 有**待确认清单**。
- **重复项已按第五部分处理**。

---

## 附：与源数据核对（计数据实说明）

> 本节为**附件整理时增加的核对记录**，用于可溯源自证；不改变上述任何候选规则内容。

| 数据源 | 实际条数 |
|---|---|
| `config/rulelist_v1.json`（V1.0） | **60** |
| `config/rulelist_v11.json`（V1.1） | **174** |
| `config/rulelist_v12.json`（V1.2） | **226** |
| 合计 | **460** |

- 本文档各节标题条数与**实际列示条数**存在两处差异，已按**实际列示**登记并就地注明：
  - **S. 小税种补充**：标题「30 条」，实际 **29 条**；
  - **Z. 金融与特殊交易**：标题「20 条」，实际 **19 条**。
- 上述差异与 `config/rulelist_v12.json::count_discrepancy` 的记录一致
  （其中载明「组一实际 29 条（DEED 5 + GOT 3 + VET 3 + VPT 3 + CUS 3 + TON 1 + TOB 2 + CUL 2 + WAT 2 + SUR 5）」）。
- 各节条数按 **按实际列示** 汇总，含已知重复项；去重后约 **420 条**（详见第五部分）。

