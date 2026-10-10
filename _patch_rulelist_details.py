# -*- coding: utf-8 -*-
"""把候选清单原文的「触发逻辑 / 核心输入 / 建议」转录进数据表（单一权威）。

为什么：YAML 导出需要 condition/inputs/suggestion。若把这些写进导出器，导出器就成了第二份数据
（多头维护）。故一律落到 config/rulelist_v1.json（V1.0 60 条）与 config/rulelist_v11.json（V1.1 174 条），
导出器只做格式转换。

数据格式：id|触发逻辑|核心输入|建议（外部清单原文转录，逐条对应）。
阈值一律不在 condition 内联数值字面量，统一引用 params（见各表 params 段）。
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
V1 = ROOT / "config" / "rulelist_v1.json"
V11 = ROOT / "config" / "rulelist_v11.json"

# ── V1.0（VAT 30 + CIT 30）─────────────────────────────────────────────────
V10_DETAIL = """
VAT-001|vat_burden < industry_avg_vat_burden * params.ratio|vat_payable,sales_revenue,industry_avg_vat_burden|核查收入确认、进项抵扣、发票合规
VAT-002|abs(vat_burden - vat_burden_last_year) / vat_burden_last_year > params.volatility|vat_burden,vat_burden_last_year|分析税负突变原因
VAT-003|abs(invoice_sales - declared_sales) / declared_sales > params.diff_ratio|invoice_sales,declared_sales|核查未开票收入、申报完整性
VAT-004|output_tax_growth - input_tax_growth > params.growth_gap and output_tax_growth > params.output_growth_floor|output_tax,input_tax|核查进项抵扣与销售匹配
VAT-005|top_input_goods not in top_output_goods and amount_ratio > params.amount_ratio|进销项品名,金额|核查虚开、变名开票
VAT-006|abs(input_qty - output_qty) / output_qty > params.qty_ratio|进销项数量|核查存货、生产消耗
VAT-007|month_end_invoice_ratio > params.month_end_share|month_end_invoice_amount,total_invoice_amount|核查收入确认时点
VAT-008|night_invoice_ratio > params.night_ratio|night_invoice_count,total_invoice_count|核查开票真实性
VAT-009|void_ratio > params.void_ratio|void_invoice_amount,total_invoice_amount|核查作废红冲原因
VAT-010|abnormal_invoice_count > 0|abnormal_invoice_count,input_invoice_total|核查异常凭证、进项转出
VAT-011|input_tax > 0 and output_tax = 0 for n months|月度进销项|核查隐匿收入、停工待产
VAT-012|output_tax > 0 and input_tax = 0 for n months|月度进销项|核查虚开、成本缺失
VAT-013|tax_exempt_sales > 0 and input_tax_for_exempt_deducted > 0|免税销售额,已抵扣进项|核查进项转出
VAT-014|simplified_tax_sales > 0 and general_tax_input_deducted > 0|简易计税销售额,一般计税进项|核查计税方法适用
VAT-015|abs(prepaid_vat - declared_vat) / declared_vat > params.diff_ratio|预缴税额,申报税额|核查预缴与申报一致性
VAT-016|un_invoiced_revenue_ratio > params.unbilled_ratio|未开票收入,总收入|核查未开票收入真实性
VAT-017|sales_return_ratio > params.return_ratio|销售退回金额,销售收入|核查退回真实性
VAT-018|extra_price_income > taxed_extra_price_income|价外费用,已计税价外费用|核查价外费用计税
VAT-019|deemed_sales_amount > declared_deemed_sales|视同销售金额,已申报视同销售|核查视同销售
VAT-020|should_transfer_out > actual_transfer_out|应转出进项,实际转出|核查进项转出
VAT-021|difference_tax_sales - difference_tax_cost > params.gap_threshold|差额征税销售额,扣除额|核查差额征税
VAT-022|void_reissue_count > params.count_threshold|void_reissue_count|核查作废重开
VAT-023|same_customer_max_invoice_count > params.count_threshold|same_customer_invoice_count|核查拆分开票
VAT-024|new_company_invoice_amount_3m > params.amount_threshold|新办企业开票金额|核查虚开
VAT-025|abs(contract_amount - invoice_amount) / contract_amount > params.diff_ratio|合同金额,开票金额|核查合同与发票一致性
VAT-026|abs(bank_receipts - invoice_sales) / invoice_sales > params.revenue_diff_ratio|银行收款,开票收入|核查账外收入
VAT-027|AR_growth - revenue_growth > params.growth_gap|应收账款,收入|核查收入确认
VAT-028|inventory_change - cost_of_sales_change > params.growth_gap|存货,销售成本|核查成本结转
VAT-029|applied_vat_rate != correct_vat_rate|适用税率,正确税率|核查税率适用
VAT-030|refund_amount > params.amount_threshold and refund_condition not met|退税金额,退税条件|核查退税合规
CIT-001|cit_contribution < industry_avg_cit_contribution * params.ratio|cit_payable,revenue,industry_avg|核查利润、纳税调整
CIT-002|abs(cit_burden - cit_burden_last_year) / cit_burden_last_year > params.volatility|cit_payable,profit|分析税负突变
CIT-003|abs(taxable_income - profit_total) / profit_total > params.diff_ratio|profit_total,taxable_income|核查税会差异调整
CIT-004|cost_ratio > industry_avg_cost_ratio * params.upper_ratio|cost,revenue,industry_avg|核查成本费用真实性
CIT-005|revenue_growth - cost_growth < -params.growth_gap and revenue_growth < 0|revenue,cost|核查收入成本匹配
CIT-006|gross_margin < industry_avg_gross_margin * params.ratio|gross_margin,industry_avg|核查定价、成本
CIT-007|abs(prepaid_cit - annual_cit) / annual_cit > params.diff_ratio|prepaid_cit,annual_cit|核查预缴准确性
CIT-008|expense_ratio > industry_avg_expense_ratio * params.upper_ratio|expense,revenue|核查费用真实性
CIT-009|entertainment_expense > min(revenue * params.revenue_rate, actual * params.actual_rate)|entertainment_expense,revenue|核查纳税调整
CIT-010|advertising_expense > revenue * params.revenue_rate|advertising_expense,revenue|核查纳税调整
CIT-011|interest_expense > equity * params.debt_equity_ratio * market_rate|interest_expense,equity,market_rate|核查关联方利息扣除
CIT-012|abs(related_transaction_price - market_price) / market_price > params.price_deviation|related_transaction_price,market_price|核查转让定价
CIT-013|related_party_receivable_age > params.age_days|related_party_receivable_balance,age|核查视同分红/利息
CIT-014|inventory_change - cost_of_sales_change > params.growth_gap|inventory,cost_of_sales|核查成本结转
CIT-015|depreciation_amount != depreciation_policy_amount|depreciation_amount,policy|核查折旧政策
CIT-016|amortization_amount != amortization_policy_amount|amortization_amount,policy|核查摊销政策
CIT-017|asset_loss_amount > params.amount_threshold and evidence_completeness < 1|asset_loss_amount,evidence|核查损失证据
CIT-018|government_grant > 0 and taxable_grant != government_grant|government_grant,taxable_grant|核查不征税收入
CIT-019|non_taxable_income > 0 and corresponding_expense_deducted > 0|non_taxable_income,expense|核查支出不得扣除
CIT-020|tax_exempt_income > 0 and corresponding_cost_deducted > 0|tax_exempt_income,cost|核查成本不得扣除
CIT-021|R&D_expense > 0 and R&D_conditions not met|R&D_expense,conditions|核查加计扣除条件
CIT-022|high_tech_conditions not met and high_tech_deduction > 0|conditions,deduction|核查高新优惠
CIT-023|small_micro_conditions not met and small_micro_deduction > 0|conditions,deduction|核查小微优惠
CIT-024|regional_incentive_conditions not met and regional_deduction > 0|conditions,deduction|核查区域优惠
CIT-025|loss_carryforward > params.years or loss_amount > params.amount_threshold|loss_carryforward,period|核查亏损弥补
CIT-026|accrued_expense > actual_payment|accrued_expense,actual_payment|核查预提费用
CIT-027|salary_total - iit_total - social_security_total > params.amount_threshold|salary_total,iit_total,social_security_total|核查工资个税社保
CIT-028|shareholder_loan_balance > 0 and loan_days > params.loan_days|shareholder_loan_balance,loan_days|核查视同分红
CIT-029|donation_amount > deduction_limit|donation_amount,deduction_limit|核查捐赠扣除
CIT-030|tax_accounting_diff > adjusted_diff|tax_accounting_diff,adjusted_diff|核查调整完整性
"""

# ── V1.1（IIT 20 / SI 8 / SD 10 / PCT 8 / LUT 6 / LAT 10 / SUR 5 / INV 20 /
#          FIN 18 / REL 10 / FUND 10 / EXPORT 10 / CONS 8 / RES-ENV 5 /
#          TAXINC 12 / GEN 14）─────────────────────────────────────────────
V11_DETAIL = """
IIT-001|abs(iit_headcount - social_headcount) / social_headcount > params.headcount_diff_ratio|个税人数,社保人数|核查漏报、少报
IIT-002|abs(iit_salary_total - cit_salary_total) / cit_salary_total > params.salary_total_diff_ratio|个税工资,所得税工资|核查工资口径
IIT-003|shareholder_loan_balance > 0 and loan_days > params.loan_days|股东借款,天数|核查视同分红
IIT-004|dividend_paid > 0 and iit_withheld = 0|分红金额,已扣个税|核查代扣代缴
IIT-005|labor_remuneration > 0 and iit_withheld = 0|劳务报酬,已扣个税|核查代扣代缴
IIT-006|person_multi_employer = true and merged_declaration = false|任职信息,申报记录|核查合并申报
IIT-007|annual_bonus_tax_method not optimal|年终奖,计税方式|核查计税方式
IIT-008|high_income_person_tax_burden < params.burden_threshold|高收入人员,税负|核查申报完整性
IIT-009|foreign_tax_exempt_subsidy > params.amount_threshold|外籍补贴,免税条件|核查免税条件
IIT-010|equity_transfer_income > 0 and iit_declared < params.amount_threshold|股权转让收入,个税|核查股权转让
IIT-011|partnership_income_allocated > 0 and iit_declared = 0|合伙分配,个税|核查经营所得
IIT-012|fixed_rate_collection and actual_income > params.amount_threshold|核定征收,实际收入|核查核定适用
IIT-013|sole_proprietorship_income > 0 and iit_declared = 0|独资企业利润,个税|核查经营所得
IIT-014|salary_below_threshold_months > params.salary_below_threshold_months|工资,月份|核查工资真实性
IIT-015|cash_salary > 0 and iit_declared = 0|现金工资,个税|核查漏报
IIT-016|severance_pay > params.severance_threshold and iit_withheld = 0|离职补偿,个税|核查免税额度
IIT-017|equity_incentive and deferred_tax_condition not met|股权激励,递延条件|核查递延备案
IIT-018|interest_dividend_income > 0 and iit_withheld = 0|利息股息,已扣个税|核查代扣代缴
IIT-019|property_rental_income > 0 and iit_withheld = 0|租赁所得,已扣个税|核查代扣代缴
IIT-020|accidental_income > 0 and iit_withheld = 0|偶然所得,已扣个税|核查代扣代缴
SI-001|abs(social_headcount - iit_headcount) / iit_headcount > params.headcount_diff_ratio|社保人数,个税人数|核查漏缴社保
SI-002|abs(social_base_total - salary_total) / salary_total > params.base_diff_ratio|社保基数,工资总额|核查基数
SI-003|probation_employee_count > 0 and social_insured = false|试用期人数,参保状态|核查试用期社保
SI-004|social_base = min_base for ratio > params.min_base_share|社保基数,最低基数|核查基数合规
SI-005|dispatch_worker_count > 0 and social_insured = false|派遣人数,参保状态|核查派遣社保
SI-006|abs(housing_fund_base - salary_total) / salary_total > params.fund_base_diff_ratio|公积金基数,工资|核查公积金
SI-007|disabled_employment_ratio < required_ratio and fund_declared = 0|残疾人比例,残保金|核查残保金
SI-008|union_fund_declared < salary_total * params.union_fund_rate|工会经费,工资总额|核查工会经费
SD-001|abs(contract_amount - stamp_tax_base) / contract_amount > params.base_diff_ratio|合同金额,印花税基数|核查计税依据
SD-002|capital_increase > 0 and stamp_tax_paid = 0|实收资本,资本公积|核查资金账簿
SD-003|property_transfer_amount > 0 and stamp_tax_paid = 0|产权转移金额,印花税|核查产权转移
SD-004|loan_contract_amount > 0 and stamp_tax_paid = 0|借款合同,印花税|核查借款合同
SD-005|lease_contract_amount > 0 and stamp_tax_paid = 0|租赁合同,印花税|核查租赁合同
SD-006|purchase_sales_contract_amount > 0 and stamp_tax_paid = 0|购销合同,印花税|核查购销合同
SD-007|transport_contract_amount > 0 and stamp_tax_paid = 0|运输合同,印花税|核查运输合同
SD-008|technology_contract_amount > 0 and stamp_tax_paid = 0|技术合同,印花税|核查技术合同
SD-009|business_ledger_count > 0 and stamp_tax_paid = 0|营业账簿,印花税|核查营业账簿
SD-010|applied_stamp_tax_item != correct_item|适用税目,正确税目|核查税目
PCT-001|building_original_value > 0 and property_tax_paid = 0|房产原值,房产税|核查从价计征
PCT-002|rental_income > 0 and property_tax_paid = 0|租金收入,房产税|核查从租计征
PCT-003|rent_free_period > 0 and property_tax_paid = 0|免租期,房产税|核查免租期
PCT-004|underground_building_value > 0 and property_tax_paid = 0|地下建筑物,房产税|核查地下建筑
PCT-005|construction_in_progress_transferred > 0 and property_tax_paid = 0|在建工程转固,房产税|核查转固
PCT-006|abs(property_tax_base - building_original_value * (1 - params.deduction_ratio)) > params.base_diff_tolerance|计税依据,原值,扣除|核查计税依据
PCT-007|applied_property_tax_rate != correct_rate|适用税率,正确税率|核查税率
PCT-008|property_tax_paid > 0 and land_use_tax_paid = 0|房产税,土地使用税|核查匹配
LUT-001|land_area > 0 and land_use_tax_paid = 0|土地面积,土地使用税|核查申报
LUT-002|applied_land_level != correct_land_level|适用等级,正确等级|核查等级
LUT-003|tax_exempt_land > 0 and filing_missing = true|免税土地,备案|核查备案
LUT-004|land_use_tax_paid > 0 and property_tax_paid = 0|土地使用税,房产税|核查匹配
LUT-005|abs(land_transfer_area - declared_land_area) / land_transfer_area > params.area_diff_ratio|出让面积,申报面积|核查面积
LUT-006|idle_land_area > 0 and land_use_tax_paid = 0|闲置土地,土地使用税|核查闲置土地
LAT-001|prepaid_lat < pre_sale_revenue * params.prepay_rate|预收收入,预缴土地增值税|核查预缴
LAT-002|liquidation_condition_met = true and liquidation_done = false|清算条件,清算状态|核查清算
LAT-003|deduction_amount > params.amount_threshold|扣除项目金额|核查扣除
LAT-004|abs(sales_revenue - declared_lat_sales) / sales_revenue > params.diff_ratio|销售收入,申报收入|核查收入
LAT-005|residential_type_misclassified = true|住宅类型,划分标准|核查划分
LAT-006|cost_allocation_ratio != reasonable_ratio|成本分摊,合理比例|核查分摊
LAT-007|interest_deduction > params.amount_threshold|利息支出,扣除限额|核查利息
LAT-008|relocation_compensation > params.amount_threshold|拆迁补偿,凭证|核查补偿
LAT-009|lat_burden < industry_avg_lat_burden * params.burden_ratio|土地增值税税负,行业均值|核查税负
LAT-010|post_liquidation_transfer > 0 and lat_declared = 0|清算后转让,土地增值税|核查再转让
SUR-001|abs(surtax_base - vat_payable) / vat_payable > params.base_diff_ratio|附加税费基数,增值税|核查计税依据
SUR-002|surtax_reduction_applied and condition not met|减免,条件|核查减免
SUR-003|applied_urban_rate != correct_rate|适用税率,正确税率|核查税率
SUR-004|vat_payable > 0 and education_surcharge_paid = 0|增值税,教育费附加|核查申报
SUR-005|abs(surtax_paid - vat_payable * surtax_rate) > params.tolerance|附加税费,增值税,税率|核查匹配
INV-001|top_input_goods not in top_output_goods and amount_ratio > params.amount_ratio|进销项品名,金额|核查虚开
INV-002|invoice_amount = max_limit for count > params.count_threshold|发票金额,限额|核查拆分
INV-003|month_end_invoice_ratio > params.month_end_share|月末开票,总开票|核查收入确认
INV-004|night_invoice_ratio > params.night_ratio|夜间开票,总开票|核查真实性
INV-005|void_ratio > params.void_ratio|作废金额,总金额|核查作废
INV-006|new_company_invoice_amount_3m > params.amount_threshold|新办企业开票|核查虚开
INV-007|same_ip_invoice_count > params.count_threshold|开票IP,设备|核查关联
INV-008|same_customer_invoice_count > params.count_threshold|客户开票次数|核查拆分
INV-009|invoice_payer != fund_payer|发票,资金流|核查三流一致
INV-010|invoice_party != contract_party|发票,合同|核查三流一致
INV-011|abnormal_invoice_count > 0|异常发票,进项|核查进项转出
INV-012|abnormal_output_invoice_count > 0|异常销项|核查销项
INV-013|agricultural_purchase_invoice > params.amount_threshold|农产品发票|核查收购
INV-014|travel_expense_invoice > params.amount_threshold|差旅发票|核查真实性
INV-015|consulting_invoice > params.amount_threshold|咨询发票|核查虚开
INV-016|conference_invoice > params.amount_threshold|会议发票|核查真实性
INV-017|advertising_invoice > params.amount_threshold|广告发票|核查真实性
INV-018|transport_invoice > params.amount_threshold|运输发票|核查真实性
INV-019|duplicate_e_invoice = true|电子发票,报销记录|核查重复
INV-020|required_remark_missing = true|发票备注,要求|核查备注
FIN-001|assets != liabilities + equity|资产,负债,权益|核查报表
FIN-002|abs(net_profit - retained_earnings_change) > params.tolerance|净利润,未分配利润|核查勾稽
FIN-003|abs(cash_flow_net - cash_change) > params.tolerance|现金流,货币资金|核查勾稽
FIN-004|AR_growth - revenue_growth > params.growth_gap|应收账款,收入|核查收入
FIN-005|inventory_growth - revenue_growth > params.growth_gap|存货,收入|核查收入
FIN-006|AP_growth - cost_growth > params.growth_gap|应付账款,成本|核查成本
FIN-007|payable_salary_growth - expense_growth > params.growth_gap|应付薪酬,费用|核查费用
FIN-008|fixed_asset_growth - depreciation_growth > params.growth_gap|固定资产,折旧|核查折旧
FIN-009|intangible_asset_growth - amortization_growth > params.growth_gap|无形资产,摊销|核查摊销
FIN-010|long_term_equity_investment_growth - investment_income_growth > params.growth_gap|长期股权投资,投资收益|核查收益
FIN-011|loan_growth - finance_expense_growth > params.growth_gap|借款,财务费用|核查利息
FIN-012|cash_growth - interest_income_growth > params.growth_gap|货币资金,利息收入|核查利息
FIN-013|other_receivable_age > params.age_days|其他应收款,账龄|核查挂账
FIN-014|other_payable_age > params.age_days|其他应付款,账龄|核查挂账
FIN-015|advance_receipt_growth - revenue_growth > params.growth_gap|预收账款,收入|核查收入
FIN-016|inventory_turnover < industry_avg * params.turnover_ratio|存货周转率,行业均值|核查存货
FIN-017|AR_turnover < industry_avg * params.turnover_ratio|应收账款周转率,行业均值|核查应收
FIN-018|abs(gross_margin - gross_margin_last_year) > params.gross_margin_delta|毛利率,上年毛利率|核查波动
REL-001|abs(related_price - market_price) / market_price > params.price_deviation|关联价格,市场价格|核查转让定价
REL-002|related_transaction_ratio > params.related_ratio|关联交易,总收入|核查关联
REL-003|related_party_receivable > params.amount_threshold|关联方应收|核查资金占用
REL-004|related_loan_rate > market_rate * params.market_rate_multiple|关联借款利率,市场利率|核查利息
REL-005|related_purchase_sales_price != market_price|关联购销,市场价格|核查定价
REL-006|related_service_fee > params.amount_threshold|关联劳务费|核查劳务
REL-007|related_asset_transfer_price != fair_value|关联资产转让,公允价值|核查转让
REL-008|related_equity_transfer_price != fair_value|关联股权转让,公允价值|核查转让
REL-009|related_party_debt_forgiveness > 0|债务豁免|核查税务处理
REL-010|related_party_expense_bearing > 0|关联方费用承担|核查费用
FUND-001|public_to_private_count > params.count_threshold and amount > params.amount_threshold|公转私记录|核查资金
FUND-002|private_to_public_count > params.count_threshold and amount > params.amount_threshold|私转公记录|核查资金
FUND-003|fund_return_detected = true|资金流水|核查回流
FUND-004|abs(bank_receipts - revenue) / revenue > params.revenue_diff_ratio|银行收款,收入|核查收入
FUND-005|abs(bank_payments - cost) / cost > params.cost_diff_ratio|银行付款,成本|核查成本
FUND-006|cash_transaction_ratio > params.cash_ratio|现金交易,总交易|核查现金
FUND-007|personal_card_transaction > params.amount_threshold|个人卡交易|核查资金
FUND-008|third_party_payment > params.amount_threshold|第三方支付|核查资金
FUND-009|fund_pool_balance > params.amount_threshold|资金池|核查资金
FUND-010|prepayment_age > params.prepay_age_days|预付款,账龄|核查预付款
EXPORT-001|export_refund > params.amount_threshold and condition not met|出口退税,条件|核查退税
EXPORT-002|export_tax_refund != calculated_refund|免抵退税额,计算值|核查计算
EXPORT-003|abs(export_revenue - customs_declaration) / export_revenue > params.export_revenue_diff_ratio|出口收入,报关单|核查收入
EXPORT-004|processing_trade_verification_missing = true|进料加工,核销|核查核销
EXPORT-005|export_invoice_abnormal = true|出口发票|核查发票
EXPORT-006|tax_refund_investigation_abnormal = true|函调结果|核查函调
EXPORT-007|applied_export_code != correct_code|商品编码,正确编码|核查编码
EXPORT-008|applied_refund_rate != correct_rate|退税率,正确税率|核查税率
EXPORT-009|export_receipt_missing = true|出口收汇|核查收汇
EXPORT-010|export_to_domestic > 0 and tax_declared = 0|出口转内销,申报|核查申报
CONS-001|applied_consumption_item != correct_item|适用税目,正确税目|核查税目
CONS-002|abs(consumption_tax_base - sales_amount) > params.base_diff_tolerance|计税依据,销售额|核查依据
CONS-003|self_produced_used > 0 and consumption_tax_paid = 0|自产自用,消费税|核查自用
CONS-004|entrusted_processing > 0 and consumption_tax_withheld = 0|委托加工,已扣税|核查代扣
CONS-005|import_consumption_goods > 0 and consumption_tax_paid = 0|进口应税消费品,消费税|核查进口
CONS-006|abs(consumption_tax_sales - vat_sales) / vat_sales > params.diff_ratio|消费税收入,增值税收入|核查收入
CONS-007|oil_consumption_tax != calculated|成品油,消费税|核查成品油
CONS-008|baijiu_consumption_tax != calculated|白酒,消费税|核查白酒
RES-001|abs(resource_tax_base - sales_quantity) > params.base_diff_tolerance|资源税基数,销售量|核查依据
RES-002|applied_resource_item != correct_item|适用税目,正确税目|核查税目
ENV-001|emission_declared != emission_actual|申报排放量,实际排放量|核查排放
ENV-002|env_tax_reduction and condition not met|减免,条件|核查减免
ENV-003|abs(env_tax_emission - permit_emission) > params.emission_tolerance|环保税排放,排污许可|核查差异
TAXINC-001|incentive_condition_met = false and incentive_claimed = true|优惠条件,享受优惠|核查条件
TAXINC-002|incentive_claimed = true and filing_missing = true|优惠,备案|核查备案
TAXINC-003|incentive_amount != calculated_incentive|优惠金额,计算值|核查计算
TAXINC-004|overlapping_incentives = true|叠加优惠|核查叠加
TAXINC-005|incentive_period != correct_period|优惠期间,正确期间|核查期间
TAXINC-006|high_tech_condition_met = false and high_tech_deduction > 0|高新条件,优惠|核查高新
TAXINC-007|small_micro_condition_met = false and small_micro_deduction > 0|小微条件,优惠|核查小微
TAXINC-008|R&D_condition_met = false and R&D_deduction > 0|研发条件,加计扣除|核查研发
TAXINC-009|western_condition_met = false and western_deduction > 0|西部条件,优惠|核查西部
TAXINC-010|software_condition_met = false and software_deduction > 0|软件条件,优惠|核查软件
TAXINC-011|resource_condition_met = false and resource_deduction > 0|资源条件,优惠|核查资源
TAXINC-012|disabled_condition_met = false and disabled_deduction > 0|残疾人条件,优惠|核查残疾人
GEN-001|abs(return_a - return_b) / return_b > params.return_diff_ratio|申报表A,申报表B|核查申报
GEN-002|abs(tax_return - financial_statement) / financial_statement > params.statement_diff_ratio|申报数据,财务报表|核查差异
GEN-003|abs(tax_return - invoice_data) / invoice_data > params.invoice_diff_ratio|申报数据,发票数据|核查差异
GEN-004|abs(tax_return - bank_flow) / bank_flow > params.bank_diff_ratio|申报数据,银行流水|核查差异
GEN-005|abs(tax_return - social_security) / social_security > params.social_diff_ratio|申报数据,社保数据|核查差异
GEN-006|abs(tax_return - annual_report) / annual_report > params.annual_report_diff_ratio|申报数据,工商年报|核查差异
GEN-007|declaration_date > due_date|申报日期,截止日期|核查逾期
GEN-008|zero_declaration_months > params.zero_declaration_months and business_active = true|零申报月份,经营状态|核查零申报
GEN-009|negative_declaration_months > params.negative_declaration_months|负申报月份|核查负申报
GEN-010|required_tax_types not in declared_tax_types|应报税种,已报税种|核查缺失
GEN-011|missing_periods > 0|申报期间|核查缺失
GEN-012|abs(current_amount - last_amount) / last_amount > params.amount_change_ratio|本期金额,上期金额|核查突变
GEN-013|declaration_frequency > params.count_threshold|申报频率|核查频率
GEN-014|same_legal_person_companies > params.company_count_threshold and abnormal_related_declaration = true|同一法人企业,申报|核查关联
"""


def _parse(block: str):
    out = {}
    for line in block.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        assert len(parts) == 4, "行格式错: %s" % line
        rid, logic, inputs, sugg = parts
        out[rid] = {"logic": logic,
                    "inputs": [x.strip() for x in inputs.split(",") if x.strip()],
                    "suggestion": sugg}
    return out


def _patch(path: Path, details: dict) -> None:
    d = json.loads(path.read_text(encoding="utf-8"))
    miss, hit = [], 0
    for r in d["rules"]:
        det = details.get(r["src"])
        if not det:
            miss.append(r["src"])
            continue
        r["logic"] = det["logic"]
        r["inputs"] = det["inputs"]
        r["suggestion"] = det["suggestion"]
        r["legal_basis_ref"] = "法规库自动匹配"
        hit += 1
    assert not miss, "以下规则缺原文转录: %s" % miss
    assert hit == len(d["rules"]), "命中数 %d ≠ 规则数 %d" % (hit, len(d["rules"]))
    path.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[%s] 补 logic/inputs/suggestion %d 条 ✓" % (path.name, hit))
    # 自检：condition 里不得出现直接数值阈值（应引用 params.*）
    import re
    bad = [r["src"] for r in d["rules"]
           if re.search(r"[<>=]\s*0\.\d", r["logic"]) and "params." not in r["logic"]]
    print("  阈值疑似内联: %s" % (bad or "无 ✓"))


if __name__ == "__main__":
    _patch(V1, _parse(V10_DETAIL))
    _patch(V11, _parse(V11_DETAIL))
