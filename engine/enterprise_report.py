"""企业易读版「涉税风险检查工作报告」九章数据生成。

从一键分析结果（all_findings / file_results / target_entity 等）组装
`enterprise_readable_report` 字段，供前端 _buildEnterpriseReadableBody 渲染
九章风险检查文书式报告。

字段结构对齐前端 static/js/tax-doc-analysis.js 的读取逻辑。
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from collections import Counter, OrderedDict

from engine.inspector_reasoning import build_inspector_reasoning
from engine.pyramid_edition import build_pyramid_edition


def _norm_text(text):
    """中文标点规范化：消除拼接残留的 "。。""。；"".、" 等异常序列。"""
    t = str(text or "")
    if not t:
        return t
    t = re.sub(r"[。．]\s*[。．]+\s*", "。", t)
    t = re.sub(r"\.{2,}", "。", t)
    t = re.sub(r"。+\s*[；;]", "；", t)
    t = re.sub(r"[；;]\s*。+", "；", t)
    t = re.sub(r"[；;]{2,}", "；", t)
    t = re.sub(r"、\s*、+", "、", t)
    t = re.sub(r"[.．]\s*[、]", "。", t)
    t = re.sub(r"。+\s*[、]", "。", t)
    t = re.sub(r"[，,]\s*。+", "。", t)
    t = re.sub(r"[，,]\s*[；;]", "；", t)
    return t.strip()


# ── 报告输出中文化归一：消除规则引擎/流水线遗留的英文缩写与术语 ──
# 这些英文是上游 finding 文本/方法论描述里写死的缩写，enterprise_report 原样拼入报告；
# 在此统一归一为中文，保证「报告内容不固定为英文、随数据动态呈现中文」。
_ZH_REPLACEMENTS = [
    (r"detect→verify→diagnose→report", "检测→核验→诊断→报告"),
    (r"detect→verify→diagnose", "检测→核验→诊断"),
    (r"(?<![A-Za-z])detect(?![A-Za-z])", "检测"),
    (r"(?<![A-Za-z])verify(?![A-Za-z])", "核验"),
    (r"(?<![A-Za-z])diagnose(?![A-Za-z])", "诊断"),
    (r"(?<![A-Za-z])rectify(?![A-Za-z])", "整改"),
    (r"(?<![A-Za-z])report(?![A-Za-z])", "报告"),
    (r"(?<![A-Za-z])[Vv][Ss](?![A-Za-z])", "与"),   # vs / VS（中文或空格环绕均适用）
    (r"(?<![A-Za-z])BOM(?![A-Za-z])", "物料清单"),
    (r"(?<![A-Za-z])ETS(?![A-Za-z])", "电子税务局"),
    # 文件扩展名（文件类型描述里出现的 .xlsx/.xls/.pdf 等）
    (r"(?<![A-Za-z])xlsx(?![A-Za-z])", "Excel"),
    (r"(?<![A-Za-z])xls(?![A-Za-z])", "Excel"),
    (r"(?<![A-Za-z])pdf(?![A-Za-z])", "PDF"),
    (r"(?<![A-Za-z])docx(?![A-Za-z])", "Word"),
    (r"(?<![A-Za-z])doc(?![A-Za-z])", "Word"),
    (r"(?<![A-Za-z])csv(?![A-Za-z])", "CSV"),
    (r"(?<![A-Za-z])txt(?![A-Za-z])", "文本"),
    # 布尔值字符串化残留
    (r"(?<![A-Za-z])False(?![A-Za-z])", "否"),
    (r"(?<![A-Za-z])True(?![A-Za-z])", "是"),
    # 常见计量单位
    (r"(?<![A-Za-z])kg(?![A-Za-z])", "千克"),
    (r"(?<![A-Za-z])mm(?![A-Za-z])", "毫米"),
    (r"(?<![A-Za-z])cm(?![A-Za-z])", "厘米"),
    # 技术/法律术语残留
    (r"arm's length", "独立交易原则"),
    (r"(?<![A-Za-z])token(?![A-Za-z])", "令牌"),
]


def _zh_normalize(text):
    """把报告正文里的英文缩写/术语归一为中文，避免报告出现英文。"""
    if not isinstance(text, str):
        return text
    s = text
    for pat, rep in _ZH_REPLACEMENTS:
        s = re.sub(pat, rep, s, flags=re.IGNORECASE)
    return s


def _zh_normalize_obj(o):
    """递归对报告字典的全部字符串值做中文化归一 + 正文自然化 + **定性边界净化**。

    这是企业易读报告输出前的**全量净化闸门**：
      ① 中文化：英文键名/标识转中文（_zh_normalize）
      ② 自然化：剥除【主张】【线索】【依据】等内部字段标记与 RL-XXX 红线编号
         （用户要求：给企业看的报告一律自然表述，不出现内部标记）
      ③ **定性边界净化**（2026-09-25 补）：调用 `text_guardrails` 的规则式护栏，
         把"把线索直接断言为已成立的违法事实"降为待核表述。

    ★ 为什么③必须加在这里（根因）：项目原有**两条净化路径** ——
      `text_guardrails.review_report_methodology` 只净化
      `all_findings/domain_results/comprehensive/...` 等键，且**在报告生成之前**执行；
      而本函数是报告输出前的最后一道闸门。晚生成的文本（如红线论证链 `argumentation.reasoning`
      是在 `redline_engine` 里、在护栏之后才拼出来的）此前**绕过了定性护栏**，
      于是「部分收入经个人账户归集，**是账外收款的直接证据**」这类越界断言能直接进报告。
      两条路径不共享同一套护栏 = 有缝的闸门；现由本函数统一补上，使"最后一道闸门"名副其实。
    """
    if isinstance(o, str):
        from engine.text_guardrails import neutralise_output_text
        from engine.sentencekit import normalize_cjk_punct as _np
        # ★ 2026-09-27（用户要求「标点符号技能要加强」）：报告正文标点规范化
        #   （中文语境半角→全角）接入本收敛点。此前本函数只做中文化/自然化/定性净化，
        #   **未做标点规范化** → 报告正文残留 1315 处中文语境半角括号、11 处半角冒号等。
        return neutralise_output_text(_np(_naturalize_report_text(_zh_normalize(o))))
    if isinstance(o, list):
        return [_zh_normalize_obj(x) for x in o]
    if isinstance(o, dict):
        return {k: _zh_normalize_obj(v) for k, v in o.items()}
    return o


def _fmt_metric_val(v):
    """明细表单元格格式化：布尔转是/否、浮点千分位、列表转中文顿号、其余转字符串。"""
    if isinstance(v, bool):
        return "是" if v else "否"
    if isinstance(v, float):
        return f"{v:,.2f}" if abs(v) < 1e9 else f"{v:,.0f}"
    if isinstance(v, list):
        return "、".join(str(x) for x in v)
    if isinstance(v, dict):
        return "、".join(f"{kk}={vv}" for kk, vv in v.items())
    return str(v)


_METRIC_CN = {
    "material": "原料", "issue": "问题", "theoretical": "理论耗用", "actual": "实际耗用",
    "deviation_ratio": "偏差率", "finished_products": "对应成品",
    "processing_count": "加工费笔数", "total_amount": "加工费合计", "cross_region_count": "跨地区笔数",
    "contract_area": "合同面积(㎡)", "required_area": "库存所需面积(㎡)",
    "end_inventory_value": "期末存货货值", "end_inventory_qty": "期末存货数量",
    "goods_value": "购销货值", "actual_transport": "账面运输费", "contract_freight": "合同运费",
    "cities": "涉及城市", "freight_bearer": "运费承担方",
    "duplicate_invoice_count": "重复发票号数", "salary_only_count": "仅工资册人数",
    "social_only_count": "仅社保册人数", "supplier": "加工方", "goods": "货物",
    "amount": "金额", "cross_region": "是否跨地区",
    "only_buy_count": "仅采购商品类数", "only_buy_amount": "涉及金额", "core_cost_pct": "占核心成本%",
    "has_processing": "是否存在加工费", "only_buy_goods": "仅采购商品",
    "only_sell_count": "仅销售商品类数", "only_sell_amount": "涉及金额", "only_sell_goods": "仅销售商品",
    "count": "家数", "amount": "金额", "credit": "收款", "debit": "付款",
    "month": "月份", "left": "收款(银行)", "right": "开票(销项)", "gap": "差额",
    "gap_ratio": "差额率", "province": "省份", "supplier_count": "供应商家数",
    "province_count": "涉及省份", "supplier_top3_ratio": "前3大供应商占比",
    "customer_top3_ratio": "前3大客户占比", "individual_supplier_count": "个体户供应商数",
    "raw_material_amount": "原材料采购金额", "production_energy_amount": "生产能源金额",
    "production_energy_invoice_count": "生产能源发票数", "personnel_match_count": "命中六员数",
    "total_amount": "往来总额", "person_account_count": "涉及个人账号数",
    "anomaly_months": "异常月份", "supplier_amount": "个体户供应商金额",
    "goods": "货物", "sale_qty": "销数量", "purchase_qty": "进数量", "diff": "差额",
    # VR026 税负率
    "paid_vat": "实缴增值税", "revenue_base": "应税销售收入", "burden_rate_pct": "税负率(%)",
    "industry_ref_low": "行业参考下限(%)", "industry_ref_high": "行业参考上限(%)", "extreme_low": "极低税负",
    # VR027 作废红冲
    "void_red_count": "作废红冲张数", "total_count": "发票总数", "void_red_ratio": "作废红冲占比",
    "near_period_end_count": "月末季末作废数", "top_amount": "最大单张金额",
    # VR028 未开票收入
    "bank_credit_total": "银行收款合计", "invoice_total": "销项开票合计",
    "declared_sales": "申报销售额", "declared_uninvoiced": "已申报未开票收入", "basis": "比对口径",
    # VR029 零申报
    "declaration_count": "申报期数", "zero_count": "零申报期数", "periods": "申报期间",
    # VR030 股东借款
    "person_out_total": "转个人合计", "other_receivable_to_person": "其他应收款挂股东",
    "person_out_detail": "转个人明细", "receivable_examples": "挂账示例",
    # VR031 印花税
    "purchase_amount": "采购金额", "sales_amount": "销售金额", "contract_base": "购销合计",
    "declared_stamp_base": "申报印花计税依据",
    # VR032 进项转出
    "hit_count": "命中张数", "reversal_tax_total": "应转出税额", "examples": "疑点示例",
    "suspicion": "嫌疑用途", "seller": "销方", "invoice_no": "发票号",
    # VR033 变名
    "purchase_categories": "购进大类", "sales_categories": "销售大类", "divergence": "背离项",
    # VR034 费用虚列
    "suspicious_count": "可疑笔数", "suspicious_total": "可疑金额合计", "cash_total": "现金支出合计",
    "expense_total": "费用合计", "revenue_total": "收入合计", "expense_rate": "费用率",
    "summary": "摘要",
    # VR035 印花其他税目
    "loan_base": "借款计税依据", "lease_base": "租赁计税依据", "other_base": "其他税目合计",
    # VR036 视同销售
    "gift_count": "赠送笔数", "gift_total": "赠送金额合计", "self_use_count": "自用处数",
    "self_use_total": "自用金额合计", "channel": "线索来源",
    # VR037 关联交易转让定价
    "deviation_count": "单价偏离笔数", "threshold": "偏离阈值", "median_price": "中位单价",
    "deviation": "偏离幅度", "direction": "方向", "counterparty": "交易对手方",
    "related_party_data": "股权穿透数据", "note": "说明",
    # VR038 业务招待费
    "entertainment_total": "业务招待费发生额", "deduct_cap": "扣除限额", "over_limit": "超限金额",
    # VR039 广告费
    "ad_promo_total": "广告费发生额",
    # VR040 福利费
    "welfare_total": "福利费发生额", "wage_total": "工资总额", "wage_source": "工资数据来源",
    # VR041 折旧摊销
    "dep_amort_total": "折旧摊销合计", "fixed_assets_total": "固定资产原值", "notes": "异常说明",
    # VR042 房产税
    "building_value": "房屋原值", "from_price_tax": "从价房产税", "rent_total": "租金收入",
    "from_rent_tax": "从租房产税", "est_property_tax": "测算房产税", "declared_property_tax": "已申报房产税",
    "rent_contracts": "租赁合同",
    # VR043 城建附加
    "paid_vat": "实缴增值税", "est_city_tax": "测算城建税", "est_edu": "测算教育费附加",
    "est_local_edu": "测算地方教育附加", "est_total": "测算附加税合计", "declared_supplementary": "已申报附加税",
    # VR044 库存收入背离
    "closing_inventory_amount": "期末库存金额", "annual_revenue": "年营业收入", "inv_rev_ratio": "库存收入比",
    # VR045 运输背离
    "out_qty": "出库量", "contract_weight": "合同运输重量", "freight_voucher_amount": "运费凭证金额",
    # VR046 呆滞
    "stagnant_count": "呆滞存货项数", "zero_outbound_periods": "零出库期数",
    # VR047 滚动矛盾
    "mismatch_count": "滚动矛盾处数", "expected_closing": "应有期末", "reported_closing": "账面期末", "diff": "差异",
    # VR048 规格不一致
    "conflict_count": "规格冲突项数", "input_specs": "进项规格", "output_specs": "销项规格",
    # VR049 物流/损耗
    "big_deal_count": "大额交易笔数", "missing_logistics": "物流资料缺失", "loss_anomaly_count": "损耗异常项数",
    "actual_loss_rate": "实际损耗率", "bom_loss_rate": "BOM定额损耗率",
    # VR050 跨境
    "foreign_deal_count": "跨境交易笔数", "customs_data_provided": "报关资料已提供",
    # VR051 责令单
    "demand_item_count": "责令补资项数", "triggered_finding_count": "触发发现数", "demand_order": "责令单明细",
    "demand_docs": "需补充资料",
    # VR052 委托加工业务真实性
    "registered_province": "企业注册省", "registered_city": "企业注册市",
    "processing_inv_count": "加工费进项笔数", "processing_inv_total": "加工费进项合计",
    "cross_province_processing_count": "跨省加工费笔数", "cross_province_processing_amount": "跨省加工费金额",
    "cross_province_suppliers": "跨省供应商省份", "transport_invoice_count": "运输费发票笔数",
    "has_transport_contract": "是否有运输合同", "has_processing_contract": "是否有委托加工合同",
    "missing_dims": "缺失维度", "auto_exonerate_path": "自证清白路径",
    # VR053 作废发票资金回流勾稽
    "void_invoice_count": "作废发票张数", "void_invoice_amount": "作废发票金额",
    "matched_count": "资金吻合张数", "matched_amount": "资金吻合金额",
    "matched_buyer_count": "资金吻合受票方户数", "match_ratio": "资金吻合占比",
    "total_receipt": "对公收款总额", "reported_income": "申报收入",
    "income_gap": "资金流与申报缺口", "matched_examples": "吻合示例",
    # VR054 作废发票未重开未申报勾稽
    "void_buyer_count": "涉及作废受票方户数", "total_void_amount": "作废金额合计",
    "no_reissue_buyer_count": "只作废不重开户数", "no_reissue_void_amount": "只作废不重开金额",
    "anomaly_ratio": "异常户金额占比", "declare_gap": "申报收入背离",
    "no_reissue_examples": "只作废不重开示例",
    "verified_facts": "已核实事实", "to_prove": "需企业举证",
    # ── 补充：基础扫描/缺失型/勾稽/资金往来规则指标键（补齐中文，杜绝英文漏网）──
    # 进项品名为空
    "missing_count": "品名为空张数", "missing_amount": "品名为空金额",
    # 公私账户资金混同（matches 列表内键）
    "name": "人员", "out_to_person": "转出个人金额", "in_from_person": "个人转入金额",
    "big_out_count": "大额转出笔数", "big_in_count": "大额转入笔数",
    # 申报 vs 开票/发票勾稽（gaps 列表内键 + 汇总）
    "declared_sales": "申报销售额", "invoice_sales": "开票销售额",
    "declared_input_tax": "申报进项税额", "invoice_input_tax": "发票进项税额",
    "declared_sales_total": "申报销售额合计", "invoice_sales_total": "开票销售额合计",
    "declared_input_tax_total": "申报进项税额合计", "invoice_input_tax_total": "发票进项税额合计",
    "directional_total_gap": "累计方向性差额", "gap_months": "差异月份数", "gaps": "逐月差异明细",
    # 客户集中度
    "customer_count": "客户户数", "customer_amount": "客户金额合计",
    "individual_customer_count": "个体户客户数",
    # 名称近似/重叠
    "similar_pair_count": "近似名称对数", "overlap_count": "重叠户数",
    "counterparty_count": "对手方户数", "comparable_count": "可比对数",
    # 用工/人均产值
    "headcount": "估算用工人数", "per_capita_output": "人均产值", "revenue": "销项收入",
    "salary_headcount": "工资人数", "social_headcount": "社保人数",
    "salary_only_examples": "仅工资示例", "social_only_examples": "仅社保示例",
    # 加价/产出
    "markup_ratio": "加价倍数", "output_amount": "销项成品金额",
    # 费用虚列
    "suspicious_ratio_of_expense": "可疑费用占比", "warn_line": "预警线",
    "conclusion_type": "结论类型",
    # 负库存/账实不符
    "negative_count": "负数笔数", "unbalanced_count": "不平衡笔数", "imbalance_count": "不平衡笔数",
    # 经营实质（缺失型）
    "industry": "行业", "expected": "应备要素", "missing": "缺失要素",
    "missing_common": "缺失常见要素", "detected_elements": "已识别要素",
    "has_premises": "是否有场地", "has_equipment": "是否有设备",
    "has_energy": "是否有能耗", "has_own_capacity": "是否有自有产能",
    "pur_count": "进项发票笔数", "sal_count": "销项发票笔数",
    "out_province_processing_amount": "外省加工费金额", "out_province_provinces": "外省省份",
    "expected_freight_high": "运费区间上限", "expected_freight_low": "运费区间下限",
    # 供应链/数量勾稽
    "big_diff_count": "大额差异笔数", "quantity_diffs": "数量差异明细",
    # 责令单
    "triggered_findings": "触发发现明细",
    # ★ 2026-09-25 补齐：这些键按词表逐词翻译会产出**语义错误或残破**的中文标签
    #   （实测 `ar_unreceived_total` → "已接收合计"，意思正好相反；
    #    `ar_max_aging_days` → "___日"）。逐词兜底对领域缩写无能为力，必须显式映射。
    #   应收账款账龄（revenue_authenticity 三维度之 ar_aging）
    "ar_customers": "应收账款客户数",
    "ar_unreceived_total": "应收账款未收合计",
    "ar_long_aging_count": "长账龄笔数",
    "ar_max_aging_days": "最长账龄天数",
    "ar_from_trial_balance": "账龄取自科目余额表",
    # 循环对开（false_invoice / input_voucher）
    "circular_mirror_count": "同额对开笔数",
    "circular_unrelated_count": "品名无关且金额重大笔数",
    # 两税差异（two_tax_income）
    "vat_over_cit": "增值税收入减企业所得税收入",
    "cit_income": "企业所得税口径收入",
    "only_one_side": "仅单边存在",
    # 收入真实性 / 其它
    "invoiced_total": "已开票合计",
    "person_inflow_amount": "个人账户流入金额",
    "start_signal": "起点信号成立",
    "base_date": "基准日",
    "themes": "主题",
}

# ★ 2026-09-25：引擎实际产出的 metrics 键**唯一清单**（前端 `_renderCapMetrics`
#   是直接打印键名的）。闸门与测试均引用本清单；新增指标键时必须同步补
#   `_METRIC_CN`/`_WORD_CN`，否则会报 ERROR —— 这是故意的。
KNOWN_ENGINE_METRIC_KEYS = (
    "abnormal_deduction_tax", "abnormal_supplier_count", "ar_customers",
    "ar_from_trial_balance", "ar_long_aging_count", "ar_max_aging_days", "ar_unreceived_total",
    "bank_in_total", "base_date", "circular_amount", "circular_mirror_count",
    "circular_supplier_count", "circular_unrelated_count", "cit_income", "concentration_ratio",
    "concentration_supplier", "corporate_receipt", "declared_side", "declared_total",
    "declared_value", "diff", "diff_pct", "direct_loop_amount", "direct_loop_parties",
    "flow_pay", "flow_receipt", "fund_loop_amount", "high_risk_relationships", "in_out_ratio",
    "indirect_loop_amount", "input_amount_total", "input_invoice_count", "input_tax_total",
    "invoice_total", "invoiced_total", "nonsales_receipt", "only_one_side",
    "person_inflow_amount", "personal_receipt", "purchase_total", "related_groups",
    "reported_income", "sales_total", "same_amount_groups", "should_transfer_out_tax",
    "start_signal", "themes", "third_party_receipt", "top1_customer_share",
    "top3_customer_share", "total_questions", "uninvoiced_gap", "uninvoiced_gap_after_nonsales",
    "unmatched_amount", "unmatched_corporate_receipt", "vat_over_cit", "vat_sales"
)


def _translate_all_metric_dicts(obj):
    """递归把**任意层级**下名为 `metrics` 的字典的键汉化（原地修改）。

    ★ 2026-09-25：只汉化顶层 `metrics` 会漏掉嵌套的（如
      `revenue_authenticity_report.dimensions.ar_aging.metrics`）。
      前端 `_renderCapMetrics` 是**直接打印键名**的（`esc(k)`），
      所以任何一处 `metrics` 的英文键都可能被用户看到。

    ⚠ 只改名为 `metrics` 的字典的**键**，不动其他键名 —— 其余键名（summary/body/verdict…）
      是前端渲染契约的一部分，翻译它们会破坏接口。
    """
    if isinstance(obj, dict):
        if isinstance(obj.get("metrics"), dict):
            obj["metrics"] = _translate_metric_keys(obj["metrics"])
        for v in obj.values():
            _translate_all_metric_dicts(v)
    elif isinstance(obj, list):
        for v in obj:
            _translate_all_metric_dicts(v)
    return obj


def _translate_metric_keys(o):
    """递归把字典（含嵌套列表/字典）的英文键汉化为中文标签（供报告透传字段使用）。

    值侧同时做空值净化：None/null 不保留占位（前端若渲染会显示字符串 "null"）。
    """
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            v = _translate_metric_keys(v)
            # 键值同为空的指标无信息量，剔除；避免前端渲染出「申报收入: null」
            if v is None or v == "":
                continue
            out[_translate_key(k)] = v
        return out
    if isinstance(o, list):
        return [_translate_metric_keys(x) for x in o]
    return o


# ── 通用英文单词 → 中文词表（兜底翻译任何未显式映射的 snake_case 键）──
# 报告表格/章节里出现的英文键名，精确映射(_METRIC_CN)未命中时，按此词表逐词翻译。
# 这样新增规则/章节产生的英文键也能自动中文化，不再需要手工逐个补映射。
_WORD_CN = {
    "count": "数", "amount": "金额", "total": "合计", "qty": "数量", "value": "值",
    "number": "号码", "no": "号", "code": "代码", "num": "数", "id": "编号",
    "name": "名称", "type": "类型", "category": "类别", "kind": "种类",
    "goods": "货物", "unit": "单位", "price": "单价", "supplier": "供应商",
    "customer": "客户", "counterparty": "对手方", "seller": "销方", "buyer": "购方",
    "person": "个人", "account": "账户",
    "direction": "方向", "deviation": "偏离", "median": "中位", "diff": "差额",
    "gap": "缺口", "difference": "差额", "ratio": "率", "share": "占比", "top": "前",
    "rate": "率", "pct": "%",
    "purchase": "进", "sale": "销", "input": "进项", "output": "销项", "in": "进",
    "out": "出", "invoice": "发票", "tax": "税额", "vat": "增值税",
    "deduction": "抵扣", "reversal": "转出",
    "month": "月份", "date": "日期", "period": "期间", "year": "年", "day": "日",
    "status": "状态", "level": "层级", "grade": "等级", "verdict": "结论",
    "recommendation": "建议", "result": "结果", "available": "可用性", "boundary": "边界",
    "scope": "范围", "note": "说明", "summary": "摘要", "desc": "说明",
    "voucher": "凭证", "debit": "借方", "credit": "贷方", "balance": "余额",
    "expected": "应有", "reported": "账面", "begin": "期初", "end": "期末",
    "document": "资料", "file": "文件", "material": "资料", "doc": "资料",
    "read": "读取", "method": "方式", "display": "展示", "use": "使用", "row": "行",
    "rows": "行", "source": "来源", "receipt": "收款", "payment": "付款",
    "transaction": "交易", "headcount": "人数", "salary": "工资", "social": "社保",
    "example": "示例", "examples": "示例", "detail": "明细", "list": "清单",
    "items": "项目", "province": "省份", "city": "城市", "region": "地区",
    "industry": "行业", "theme": "主题", "severity": "严重度", "question": "问题",
    "questions": "问题", "basis": "依据", "signal": "信号", "signals": "信号",
    "hint": "提示", "need": "需求", "why": "原因", "trigger": "触发", "work": "工作",
    "convergence": "收敛", "problem": "问题", "opening": "导语", "bottom": "底线",
    "line": "线", "roadmap": "路线图", "responsibility": "责任", "principle": "原则",
    "conclusion": "结论", "rule": "规则", "administrative": "行政", "perspective": "视角",
    "plan": "计划", "action": "行动", "procedure": "程序", "inspection": "检查",
    "coverage": "覆盖", "identity": "身份", "subject": "主体", "taxpayer": "纳税人",
    "analysis": "分析", "round": "轮次", "generated": "生成", "headline": "标题",
    "owner": "负责人", "message": "说明", "compilation": "编制",
    "style": "风格", "checked": "已核", "pending": "待办", "further": "进一步",
    "check": "核验", "risk": "风险", "link": "关联", "cross": "跨", "enterprise": "企业",
    "derivation": "派生", "tree": "树", "recheck": "复查", "must": "必须",
    "rely": "依赖", "external": "外部", "system": "系统", "verified": "已核",
    "confirmed": "确认", "completed": "完成", "overview": "总览", "discovery": "发现",
    "key": "关键", "point": "要点", "paragraph": "段落", "paragraphs": "段落",
    "table": "表", "metric": "指标", "metrics": "指标", "identity": "身份",
    "entity": "主体", "fund": "资金", "loop": "回流", "flow": "流", "bank": "银行",
    "report": "报告", "cross_enterprise": "跨企业", "financial": "财务",
    "statement": "报表", "request": "请求", "required": "必需", "optional": "可选",
    "missing": "缺失", "present": "已提交", "received": "已接收", "counted": "计数",
    "abnormal": "异常", "concentration": "集中", "high": "高", "relationships": "关联",
    "should": "应", "transfer": "转", "same": "同", "groups": "组", "sales": "销",
    "breakdown": "分布", "links": "关联", "top1": "第一大", "top3": "前三大",
    "completed": "完成", "confirmed": "确认", "circular": "环开", "relationship": "关联",
    # 2026-09-12 补：专项能力章节 metrics 实测暴露的未覆盖词元
    # （此前产生「流pay」「corporate收款」「declared值」这类半中半英键名）
    # 注意：不得重复定义本表已存在的键（sale/sales/invoice/flow/statement 等），
    # 否则后值静默覆盖前值、语义随 dict 顺序漂移。
    "pay": "付款", "corporate": "对公", "thirdparty": "第三方",
    "third": "第三", "party": "方",
    "nonsales": "非销售", "declared": "已申报", "uninvoiced": "未开票",
    "unmatched": "未匹配", "matched": "已匹配",
    "direct": "直接", "indirect": "间接", "parties": "对方",
    "related": "关联",
    # 2026-09-12 二批：实测仍漏译的词元（个人收款/申报收入/申报口径/非销售后）
    "personal": "个人", "income": "收入", "side": "口径", "after": "后",
}


def _translate_key(key):
    """把英文键名翻译为中文：精确映射(_METRIC_CN)优先，否则按单词词表逐词翻译。

    纯中文或无英文的键原样返回（幂等）；无法翻译的词保留原样，避免破坏数据。

    2026-09-12 补：引擎里存在「中英连写」键（corporate收款、declared值、
    uninvoiced缺口afternonsales）——按下划线分词后整段是混合词，词表查不到，
    导致报告出现半中半英。此处增加英文片段兜底替换（长词优先）。
    """
    s = str(key)
    if not s or not re.search(r"[A-Za-z]", s):
        return s
    if s in _METRIC_CN:
        return _METRIC_CN[s]
    words = re.split(r"[_\-]", s)
    out, hit, miss = [], False, False
    for w in words:
        low = w.lower()
        if low in _WORD_CN:
            out.append(_WORD_CN[low])
            hit = True
        else:
            out.append(w)
            miss = True
    # ★ 2026-09-25 加固：**不得再做"半翻译"** —— 只要还存在译不出的片段，
    #   最终就**返回原键**，绝不用"把残留英文整段剔除"来凑出中文。
    #   理由：整段剔除会**静默丢失词元、甚至语义反转** ——
    #   实测 `ar_unreceived_total`（应收账款**未**收合计）被剔成「已接收合计」
    #   （`un` 未知被丢、`received`→已接收），成了给企业报告里的一句**假话**。
    #   宁可露出英文键（一眼看出未汉化、可补映射，且闸门会逼出该补的映射），
    #   也不产出**看起来像中文的错误标签**。
    #   注：`miss` 不再提前返回 —— 仍要让下面两层的**已知词元**替换生效
    #   （中英连写键如 `direct回流金额` 必须能译成「直接回流金额」）。
    result = "".join(out) if (hit and not miss) else s
    # 二次兜底：对仍含英文的片段做子串替换（长词优先）。
    # 约束：① 只替换长度 ≥3 的英文词，避免 in/out/al/s/e 等短词元污染中文
    #       （曾把 personal 打成「个人al」、declared_side 打成「已申报s编号e」）；
    #       ② 仅在词边界替换，不切断更长的英文单词。
    if re.search(r"[A-Za-z]{3,}", result):
        for en, zh in sorted(_WORD_CN.items(), key=lambda x: -len(x[0])):
            if len(en) < 3 or en not in result:
                continue
            result = re.sub(r"(?<![A-Za-z])%s(?![A-Za-z])" % re.escape(en), zh, result)
    # 三次兜底：中英连写键（如 direct回流金额）——已知词元紧邻中文时也替换。
    if re.search(r"[A-Za-z]{3,}", result):
        for en, zh in sorted(_WORD_CN.items(), key=lambda x: -len(x[0])):
            if len(en) >= 3:
                result = result.replace(en, zh)
    # 终检：仍有**任何**未知英文 → 返回**原键**（不静默剔除，避免语义反转）
    # ⚠ 用 `[A-Za-z]` 而非 `{3,}`：1~2 字母的残留（如 `ar_un已接收_合计_x` 里的 `un`）
    #   同样是"半翻译"，同样可能已丢词元。
    if re.search(r"[A-Za-z]", result):
        return s
    return result


def _build_detail_table(f):
    """从 finding 的 observed_metrics / examples / 明细 生成可回查的代表性明细表。

    返回 (rows, columns)：rows 为 dict 列表，columns 为列中文名列表；无可用明细时返回 ([], [])。
    明细是让报告『详尽』的关键：把后台已经算出的逐笔差异落到正文，而不是只在 Detail 里写汇总数。
    """
    metrics = f.get("observed_metrics") or {}
    if not isinstance(metrics, dict):
        metrics = {}
    # 兼容直接挂在 finding 上的 examples 列表
    examples = f.get("examples") or metrics.get("examples") or []
    rows, columns = [], []
    # 1) 通用 examples 列表（每项是一行 dict）
    if isinstance(examples, list) and examples and isinstance(examples[0], dict):
        columns = list(examples[0].keys())
        rows = [dict(x) for x in examples[:30]]
    # 2) 各类命名明细字段
    named = {
        "duplicate_invoice_examples": ["invoice_number", "invoice_code", "rows", "count"],
        "balance_mismatch_examples": ["account", "date", "expected_balance", "reported_balance", "difference"],
        "invoice_mismatch_examples": ["invoice_number", "row", "amount", "tax", "total", "difference"],
        "counterparty_examples": ["counterparty", "receipts", "payments", "transaction_count"],
        "overlap_examples": ["name"],
        "voucher_examples": ["month", "voucher_no", "debit", "credit", "difference"],
        "negative_items": ["code", "name", "end_qty", "row"],
        "inventory_mismatch_examples": ["name", "begin", "in_qty", "out_qty", "expected_end_qty", "reported_end_qty", "difference"],
    }
    for key, cols in named.items():
        if key in metrics and isinstance(metrics[key], list) and metrics[key]:
            rows = [dict(x) for x in metrics[key][:30]]
            columns = cols
            break
    # 3) 兜底：标量 observed_metrics（无逐笔列表时）按『指标/数值』两列渲染，
    #    让 BOM 投入产出、合同面积、到货价等所有带指标的发现都能落到明细表。
    if not rows:
        skip = {"examples"}
        # 2.5) 嵌套字典（dict-of-dicts）：如 province_breakdown{省份:{count,amount}}、
        #      matches{姓名:{credit,debit,count}}——渲染成多行多列表格
        if not rows:
            for k, v in metrics.items():
                if k in skip or not isinstance(v, dict) or not v:
                    continue
                if all(isinstance(inner, dict) and inner for inner in v.values()):
                    inner_keys = list(next(iter(v.values())).keys())
                    label = {"province_breakdown": "省份", "matches": "人员",
                             "supplier_breakdown": "供应商", "customer_breakdown": "客户"}.get(k, "项目")
                    rows = []
                    for key, inner in list(v.items())[:30]:
                        row = {label: str(key)}
                        for ik in inner_keys:
                            row[_METRIC_CN.get(ik, str(ik))] = _fmt_metric_val(inner.get(ik))
                        rows.append(row)
                    columns = [label] + [_METRIC_CN.get(ik, str(ik)) for ik in inner_keys]
                    break
        # 2.6) 列表嵌套字典（list-of-dicts）：如 anomaly_months[{month,left,right,gap,...}]——逐行表格
        if not rows:
            for k, v in metrics.items():
                if k in skip or not isinstance(v, list) or not v or not isinstance(v[0], dict):
                    continue
                inner_keys = list(v[0].keys())
                # 列名：把已知 key 汉化
                columns = [_METRIC_CN.get(ik, str(ik)) for ik in inner_keys]
                rows = [{_METRIC_CN.get(ik, str(ik)): _fmt_metric_val(item.get(ik)) for ik in inner_keys}
                        for item in v[:30]]
                break
        scalar_rows = []
        for k, v in metrics.items():
            if k in skip or isinstance(v, dict):
                continue
            if isinstance(v, list):
                if v and isinstance(v[0], dict):
                    continue  # 已由命名明细或通用 examples 处理
                if v:
                    # 字符串/标量列表：单列渲染（用中文标签）
                    col = {"only_buy_goods": "仅采购商品", "only_sell_goods": "仅销售商品",
                           "finished_products": "对应成品"}.get(k, "明细")
                    rows = [{col: str(x)} for x in v[:30]]
                    if rows:
                        return rows, [col]
                continue
            if v in (None, ""):
                continue
            val = v
            if isinstance(v, float):
                val = f"{v:,.2f}" if abs(v) < 1e9 else f"{v:,.0f}"
            scalar_rows.append({"指标": _METRIC_CN.get(k, str(k)), "数值": val})
        if scalar_rows and not rows:
            rows = scalar_rows
            columns = ["指标", "数值"]
    # ★ 2026-09-26：兜底——发现自带的逐笔证据 evidence_rows 也作为明细表来源
    if not rows:
        ev = (f.get("evidence_rows") if isinstance(f, dict) else None) or []
        tbl = _evidence_rows_to_detail_table(ev)
        if tbl:
            return tbl["rows"], tbl["columns"]
    if not rows:
        return [], []
    # 统一汉化列名与行键：保证 columns 与 rows 键一致（前端按 columns 取值）。
    # 精确映射优先，词表兜底，杜绝英文键名漏网。
    columns = [_translate_key(c) for c in columns]
    rows = [{_translate_key(k): v for k, v in row.items()} for row in rows]
    return rows, columns


# ── evidence_rows → 明细表（2026-09-26 根因修复）────────────────────────
# 根因：引擎产出的「逐笔证据」统一挂在 finding.evidence_rows（本轮 167 条发现中 138 条带此字段），
# 但企业报告此前只渲染 finding.detail_tables（按 redline_id 关联），而 detail_tables 全库仅 1 条发现带。
# 结果：138 条发现的逐笔明细被静默吞掉（如红冲/作废发票 13 张逐笔清单不显示）。
# 此处把 evidence_rows 也当作明细表来源：凡带 evidence_rows 的发现（能关联到红线疑点）都会在企业报告
# 「发现的依据」段列出逐笔明细。这是通用规则，新增任何带 evidence_rows 的发现都无需改报告渲染代码。
_EV_COLUMN_CN = {
    "ref_label": "发票/凭证号", "invoice_no": "发票号", "inv_no": "发票号",
    "counterparty": "对方单位", "party": "对方单位",
    "amount": "金额(元)", "total": "金额(元)", "money": "金额(元)",
    "date": "日期", "bill_date": "开票日期",
    "source": "来源资料", "file": "来源资料",
    "note": "说明", "remark": "说明", "kind": "类型", "type": "类型",
}
_EV_COLUMN_ORDER = ["ref_label", "counterparty", "amount", "date", "source", "note"]
# 红线/疑点名里高频但无区分度的词，按类型兜底关联时降权，避免误挂
_MATCH_STOP = {"异常", "发票", "数量", "风险", "比例", "事项", "检查", "核查", "疑点"}


def _cjk_bigrams(text):
    """取中文字符的相邻 2-gram 集合，用于「发现类型 ↔ 疑点名称」关键词重叠匹配。"""
    text = "".join(re.findall(r"[一-鿿]", str(text or "")))
    return set(text[i:i + 2] for i in range(len(text) - 1))


def _norm_type_key(type_str):
    """发现类型去标点规整键（用于按类型兜底关联疑点）。"""
    return "".join(re.findall(r"[一-鿿A-Za-z0-9]", str(type_str or "")))


def _evidence_rows_to_detail_table(ev_rows, title="逐笔明细"):
    """把 finding.evidence_rows（list[dict]）转成前端可渲染的明细表。

    自动识别常见字段并汉化列名（发票号/对方单位/金额/日期/来源/说明），
    识别不了的字段也透传，保证不丢信息。返回 {title, columns, rows} 或 None。
    """
    if not isinstance(ev_rows, list) or not ev_rows:
        return None
    rows = []
    for idx, r in enumerate(ev_rows, 1):
        if not isinstance(r, dict):
            rows.append({"序号": idx, "说明": str(r)})
            continue
        row = {"序号": idx}
        used = set()
        for key in _EV_COLUMN_ORDER:
            if key in r:
                cn = _EV_COLUMN_CN.get(key, key)
                v = r.get(key)
                if key in ("amount", "total", "money") and isinstance(v, (int, float)):
                    v = f"{v:,.2f}"
                row[cn] = v
                used.add(key)
        # 其余未识别字段也带上（避免丢信息，如来源文件、备注原文）
        for k, v in r.items():
            if k in used or k in _EV_COLUMN_ORDER:
                continue
            row[_EV_COLUMN_CN.get(k, str(k))] = v
        rows.append(row)
    if not rows:
        return None
    return {"title": title, "columns": list(rows[0].keys()), "rows": rows}


def _finding_detail_tables(f):
    """取发现的可渲染明细表：优先用显式 detail_tables，否则把 evidence_rows 转成明细表。
    返回 list[dict]（每个 {title, columns, rows}）。"""
    if not isinstance(f, dict):
        return []
    dts = f.get("detail_tables") or []
    out = [t for t in dts if isinstance(t, dict) and t.get("rows")]
    if out:
        return out
    ev = f.get("evidence_rows") or []
    title = str(f.get("type") or "逐笔明细")
    if ev:
        title = f"{title}（共{len(ev)}笔）"
    tbl = _evidence_rows_to_detail_table(ev, title=title)
    if tbl:
        return [tbl]
    return []


def _match_suspicion_detail(s, dt_by_type):
    """按「发现类型 ↔ 疑点名称/涉嫌」关键词重叠，把未打 redline_id 的域发现兜底关联到疑点。
    返回匹配到的明细表 list 或 None；重叠 2-gram 数 >=3 才命中，避免误挂。"""
    if not isinstance(s, dict) or not dt_by_type:
        return None
    name = " ".join([
        str(s.get("redline_name") or ""),
        str(s.get("suspect") or ""),
        str(s.get("redline_id") or ""),
    ])
    s_bigrams = _cjk_bigrams(name)
    if not s_bigrams:
        return None
    best, best_score = None, 0
    for tkey, tables in dt_by_type.items():
        overlap = s_bigrams & _cjk_bigrams(tkey)
        # 去掉高频无区分度词，按有效重叠计数
        effective = overlap - _MATCH_STOP
        score = len(effective)
        if score > best_score:
            best, best_score = tables, score
    return best if best_score >= 3 else None


# ── 14 类税务合规必查资料（与 domain_analysis.py 保持一致）──
_REQUIRED_DOC_CATEGORIES = [
    "银行流水", "销项发票", "进项发票", "记账凭证", "工资表", "社保明细",
    "进销存台账", "合同文件", "科目余额表", "资产负债表", "利润表",
    "增值税申报表", "企业所得税申报表", "个税申报表", "其他税种申报表",
]

# 2026-09-05 新增：缺失资料 → 无法检查的风险方面映射表。
# 用户要求：告知"缺失某项资料而无法检查哪一方面的风险"。
# 每项：缺什么资料 → 查不了哪些风险（大白话）→ 补什么能查清。
_MISSING_DOC_RISK_MAP = [
    ("银行流水", ["资金回流与公私混同", "账外收入", "收入收款印证", "主营成本资金印证", "暂估成本公转私闭环", "利息与补贴收入完整性"],
     "提供全部银行账户流水（含个人账户与第三方平台账单），否则资金侧风险完全不可见。"),
    ("销项发票", ["收入完整性（申报-开票勾稽）", "作废红冲异常", "折扣折让计税", "客户集中度", "主营收入识别"],
     "提供销项发票明细（含作废与红字发票），否则收入侧风险无法定量。"),
    ("进项发票", ["成本真实性", "虚开发票与上游异常", "进项转出", "供应商集中度与地域分布", "主营成本识别"],
     "提供进项发票明细（含税码与品名），否则成本侧风险无法定量。"),
    ("记账凭证", ["账票税勾稽", "暂估成本与挂账", "成本费用归集准确性", "其他应付款异常"],
     "提供序时账（记账凭证），否则账面数据无法与发票、申报核对。"),
    ("工资表", ["用工真实性", "个税全员全额扣缴", "工资拆分规避", "人均产值合理性"],
     "提供工资薪金明细（含工号与证件号），否则薪酬与个税风险无法检查。"),
    ("社保明细", ["用工一致性（工资vs参保）", "未参保与基数不符", "挂靠用工线索"],
     "提供社会保险明细（分月分人），否则参保真实性无法核对。"),
    ("进销存台账", ["账外经营线索", "进销数量勾稽", "存货真实性", "呆滞库存"],
     "提供进销存台账（收发存逐笔），否则货物流动侧风险无法检查。"),
    ("合同文件", ["业务真实性", "五流一致", "关联交易与定价", "履约与结算匹配"],
     "提供购销与服务合同，否则交易实质无法核验。"),
    ("科目余额表", ["暂估成本", "预收账款长期挂账", "其他应付款异常", "科目结构勾稽"],
     "提供科目余额表（至末级科目），否则账面科目风险无法检查。"),
    ("资产负债表", ["资产负债结构异常", "长期挂账往来款", "净资产与申报勾稽"],
     "提供资产负债表，否则资产端与权益端风险无法检查。"),
    ("利润表", ["成本费用结构", "毛利率异常", "期间费用合理性", "两税收入差异"],
     "提供利润表，否则利润构成与收入成本配比无法检查。"),
    ("增值税申报表", ["收入完整性（申报-开票差额）", "税负率偏离", "留抵异常", "未开票收入敞口"],
     "提供增值税纳税申报表（分月），否则申报侧风险无法定量。"),
    ("企业所得税申报表", ["扣除限额与纳税调整", "亏损弥补合规", "暂估成本税前扣除", "两税收入差异"],
     "提供企业所得税申报表，否则所得税侧风险无法检查。"),
    ("个税申报表", ["个税扣缴合规", "劳务报酬代扣", "工资拆分线索"],
     "提供个人所得税扣缴申报表，否则扣缴义务履行情况无法检查。"),
    ("其他税种申报表", ["印花税漏报", "房产税漏报", "城建税及附加附征", "其他财产行为税"],
     "提供印花税、房产税等申报表，否则财产行为税风险无法检查。"),
]

# 资料 type → 中文类别名
_DOC_TYPE_NAME = {
    "bank": "银行流水明细", "bank_statement": "银行流水明细",
    "bank_transaction": "银行流水明细",
    "sales_invoice": "销项发票明细",
    "purchase_invoice": "进项发票明细",
    "salary": "工资薪金明细", "payroll": "工资薪金明细",
    "social_security": "社会保险明细",
    "housing_fund": "住房公积金明细",
    "voucher": "记账凭证", "journal": "记账凭证",
    "trial_balance": "科目余额表", "ledger": "科目余额表",
    "contract": "合同文件", "order": "合同文件",
    "inventory": "进销存台账",
    "vat": "增值税申报表", "tax_return": "纳税申报表",
    "fixed_asset": "固定资产资料", "assets": "固定资产资料",
    "related_party": "关联方资料",
    "customs": "海关报关资料", "export": "出口退税资料",
    "financial": "财务报表", "financial_statement": "财务报表",
    "bom": "BOM物料清单",
    "warehouse_lease": "仓库租赁合同",
    "transport_contract": "运输合同",
    "generic_data": "其他财税资料",
    "unknown": "其他财税资料",
}

# type → 已覆盖的"必查资料类别"
# ⚠ 2026-09-25 重写（P0，"已上传申报表却报缺增值税申报表"的根因）：
#   原映射表的键是**凭想象写的**，与解析器实际产出的类型名大量不符：
#     · 9 个死键（`bank`/`vat`/`journal`/`ledger`/`order`/`payroll`/`financial`/
#       `financial_statement`/`bank_transaction`）—— `_FILE_FINGERPRINTS` 从不产出这些；
#     · 35 个实际类型未覆盖（含 `vat_declaration`、`cit_declaration`、`individual_tax`、
#       `stamp_duty`、`tax_payment`、`contract_list`、`input_vat_deduction`、
#       `financial_statements`(复数) 等）；
#     · 值里的"财务报表"不在 `_REQUIRED_DOC_CATEGORIES` 中，导致"资产负债表""利润表"
#       **永远被判缺失**（必查 15 类中有 5 类永远无法覆盖）。
#   后果：即使 12 份增值税申报表已成功解析，报告首章"发现一览"仍写
#   「缺资料：“增值税申报表”」，前端报告区直接显示"缺少增值税申报表"。
#   → 键必须严格对齐 `main._FILE_FINGERPRINTS` 的实际类型；一份资料可覆盖多个必查类别，
#     故值统一改为 **tuple**。
_DOC_TYPE_TO_CATEGORY = {
    # 资金流
    "bank_statement": ("银行流水",), "bank": ("银行流水",), "bank_transaction": ("银行流水",),
    # 发票流
    "sales_invoice": ("销项发票",), "purchase_invoice": ("进项发票",),
    "input_vat_deduction": ("进项发票",),
    "invoice_universal": ("销项发票", "进项发票"), "invoice": ("销项发票", "进项发票"),
    # 人员流
    "salary": ("工资表",), "employee_list": ("工资表",), "attendance": ("工资表",),
    "social_security": ("社保明细",), "housing_fund": ("社保明细",),
    "salary_tax": ("个税申报表",),
    # 账务
    "voucher": ("记账凭证",),
    "trial_balance": ("科目余额表",),
    "accounts_receivable": ("科目余额表",), "accounts_payable": ("科目余额表",),
    "prepaid_advance": ("科目余额表",), "other_receivables": ("科目余额表",),
    "fixed_assets": ("科目余额表",), "intangible_assets": ("科目余额表",),
    "asset_impairment": ("科目余额表",), "expense_detail": ("记账凭证",),
    "rd_expense": ("记账凭证",), "rd_aux_ledger": ("记账凭证",),
    "expense_report": ("记账凭证",),
    "equity_transaction": ("科目余额表",),
    # 货物流 / 合同流
    "inventory": ("进销存台账",), "bom": ("进销存台账",),
    "contract": ("合同文件",), "contract_list": ("合同文件",), "order": ("合同文件",),
    "warehouse_lease": ("合同文件",), "transport_contract": ("合同文件",),
    "loan_borrowing": ("合同文件",), "related_party": ("合同文件",),
    # 税流 —— ★ 关键修正：解析器产出的是 vat_declaration，不是 vat
    "vat_declaration": ("增值税申报表",), "vat": ("增值税申报表",),
    "cit_declaration": ("企业所得税申报表",),
    "individual_tax": ("个税申报表",),
    "stamp_duty": ("其他税种申报表",), "tax_payment": ("其他税种申报表",),
    # 通用申报表：内容无法细分时，按"至少已提供申报表"计入全部税种申报类别
    "tax_declaration": ("增值税申报表", "企业所得税申报表", "个税申报表", "其他税种申报表"),
    # 财务报表：一份报表通常同时含资产负债表与利润表 → 同时覆盖两个必查类别
    "financial_statements": ("资产负债表", "利润表"),
    "financial_statement": ("资产负债表", "利润表"),
    "financial": ("资产负债表", "利润表"),
    # 进出口 / 其他
    "customs_declaration": ("合同文件",), "export_invoice": ("销项发票",),
    "forex_collection": ("银行流水",), "import_export": ("合同文件",),
    "audit_notice": ("合同文件",), "contact_list": (),
    "generic_data": (),
}

# ── P3.5 补充自证资料类别映射（单一权威来源：engine/material_recognition）──
# 红线库 required_materials 中既非 15 类必查、也非超类表变体的资料名（审计漂移 WARN），
# 在此登记为独立补充类别：上传→识别 doc_type→映射到与红线需求名完全一致的类别名→
# 证据链逐字命中判定"已有"，翻转"需补充提供"为"已提供"（绝不冒充某 15 类）。
try:
    from engine.material_recognition import _SUPPLEMENTARY_RECOGNITION as _SUPP_REC
    for _n, _info in _SUPP_REC.items():
        _DOC_TYPE_TO_CATEGORY[_info["doc_type"]] = (_n,) + tuple(_info.get("extra_cats") or ())
    # "发票"由发票类 doc_type 双映射提供（避免 early-return 误吞正常发票，同时让
    # 红线需求名"发票"在上传任意发票时即逐字命中"已有"）。
    for _dt in ("sales_invoice", "purchase_invoice", "invoice_universal", "input_vat_deduction"):
        _cur = _DOC_TYPE_TO_CATEGORY.get(_dt) or ()
        if "发票" not in _cur:
            _DOC_TYPE_TO_CATEGORY[_dt] = tuple(_cur) + ("发票",)
except Exception as _e:  # pragma: no cover - 依赖缺失不静默放行
    import sys
    print("WARN engine.material_recognition 加载失败，补充自证资料识别不可用:", _e, file=sys.stderr)


def _doc_covered_categories(report_data):
    """已提供的必查资料类别集合（唯一实现，供 further_checks / material_readiness 共用）。

    判据 = ① `file_results` 里每个文件的 `type` 经 `_DOC_TYPE_TO_CATEGORY` 映射；
           ② `comprehensive.material_intel` 里出现的键（可能是类别名本身）。
    """
    covered = set()
    for fr in (report_data.get("file_results") or []):
        if not isinstance(fr, dict):
            continue
        # 双重利用：type 是内容真实类别；补充自证资料的 sup_* 挂在 supplementary_category 上
        cats = _DOC_TYPE_TO_CATEGORY.get(str(fr.get("type") or "").strip())
        _sup_cat = _DOC_TYPE_TO_CATEGORY.get(str(fr.get("supplementary_category") or "").strip())
        # 主体不符被排除的文件不算"已提供"（其数据未参与分析）
        if fr.get("subject_mismatch") or fr.get("type") == "subject_mismatch":
            continue
        if not cats and not _sup_cat:
            continue
        if isinstance(cats, str):
            cats = (cats,)
        if isinstance(_sup_cat, str):
            _sup_cat = (_sup_cat,)
        covered.update(cats or ())
        covered.update(_sup_cat or ())
    _comp = report_data.get("comprehensive")
    mi = (_comp.get("material_intel") if isinstance(_comp, dict) else None) or {}
    if isinstance(mi, dict):
        for k in mi.keys():
            if k in _REQUIRED_DOC_CATEGORIES:
                covered.add(str(k))
    return covered



def _cn_num(n):
    nums = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
    n = int(n or 0)
    if 0 <= n <= 10:
        return nums[n]
    if 10 < n < 20:
        return "十" + nums[n - 10]
    if 20 <= n < 100:
        return nums[n // 10] + "十" + (nums[n % 10] if n % 10 else "")
    return str(n)


def _core_sentence(text, max_len=90):
    """从一段事实叙述里提取「核心一句」——第一个含数字的分句（摘要用）。

    稽查专家写摘要的原则：标题 + 一个带数字的结论句，而不是整段复述。
    取第一个句号/分号前的分句；若其不含数字则向后找第一个含数字的分句；
    超过 max_len 截断并补省略号。
    """
    text = _norm_text(str(text or "")).replace("经查，", "").replace("经查,", "").strip()
    if not text:
        return ""
    # 按句号/分号切分句 —— 用 sentencekit（**括号感知**，不在（）「」《》内部切）
    from engine.sentencekit import split_sentences
    clauses = [c.strip() for c in split_sentences(text) if c.strip()]
    if not clauses:
        return text[:max_len] + ("…" if len(text) > max_len else "")
    # 优先：含数字的分句（数字=事实的锚点）；截断用 clamp_text（不切括号内）
    from engine.sentencekit import clamp_text
    for c in clauses:
        if re.search(r"[0-9]", c):
            return clamp_text(c, max_len)
    # 兜底：第一句
    return clamp_text(clauses[0], max_len)


def _strip_redline_prefix(text):
    """key_points 每条只索引「标题 + 实质一句」，剥掉红线正文首句里
    '经检查，本企业触发税务风险指标（待核实），即<指标名>，' 的全局框架前缀。

    该框架（"待核实 / 触发指标"）在 headline 已统一陈述一次；若逐条重复，
    26 条重点会变成同一句机械模板（与"解除方式套话"同类雷同病）。剥掉后
    指标名只在标题出现一次，key_points 每条只留"涉嫌…"实质一句，信息密度更高。
    """
    return re.sub(r"^经检查，本企业触发税务风险指标，即[^，]+，", "", str(text or "")).strip()


def _seq(items, empty="能够证明相关业务事实的原始资料。"):
    """把 list 转成『第一，…；第二，…。』序列"""
    if not items:
        return empty
    items = [str(x).rstrip("。；") for x in items if str(x).strip()]
    if not items:
        return empty
    nums = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
            "十一", "十二", "十三", "十四", "十五", "十六"]
    parts = []
    for i, x in enumerate(items):
        parts.append("第" + (nums[i] if i < len(nums) else str(i + 1)) + "，" + x)
    return "；".join(parts) + "。"


def _identity_from_report_data(report_data):
    te = report_data.get("target_entity", {}) or {}
    snap = report_data.get("_case_snapshot", {}) or {}
    return {
        "subject_name": te.get("name") or "未填写企业名称",
        "taxpayer_id": te.get("uscc") or te.get("taxpayer_id") or te.get("credit_code") or "",
        "period": te.get("period") or "以本轮资料记载期间为准",
        "analysis_round": report_data.get("analysis_round") or snap.get("analysis_round") or 1,
    }


def _build_inspector_perspective():
    return {
        "opening": "根据本轮税务风险检查工作安排，现对被检查企业提交并成功读取的财税资料实施检查，并将检查范围、实施程序、查明事实、税务影响、处理意见及后续复查要求报告如下。",
        "work_principle": "以企业上传的原始资料为起点，先确认数据事实，再核对交易、会计处理和纳税申报；正常解释、反向证据和资料缺口分别记录。",
        "conclusion_rule": "只有能够回查到本轮资料的具体事实才写入问题部分；行业指标、风险评分和资料缺失不能单独作为问题认定。",
        "administrative_boundary": "本报告由企业使用的财税风险防控系统依据已提交资料生成，用于模拟税务风险检查程序并开展合规整改，不具有税务机关行政执法文书效力；税务机关实际检查结论应以依法送达的正式文书为准。",
    }


def _build_procedures(report_data):
    """七项风险检查程序（固定描述 + 本轮实际数字）"""
    file_results = report_data.get("file_results", []) or []
    files_count = report_data.get("files_count", len(file_results)) or len(file_results)
    full_read = sum(1 for fr in file_results if isinstance(fr, dict) and "完整" in str(fr.get("actions", [])))
    partial = sum(1 for fr in file_results if isinstance(fr, dict) and "部分" in str(fr.get("actions", [])))
    blocked = sum(1 for fr in file_results if isinstance(fr, dict) and ("失败" in str(fr.get("actions", [])) or "阻断" in str(fr.get("actions", []))))
    findings = report_data.get("all_findings", []) or []
    confirmed = [f for f in findings if isinstance(f, dict) and f.get("level") not in ("待核验",)]

    procedures = [
        ("确认被检查企业、期间和资料批次",
         f"确认被检查企业为{report_data.get('target_entity', {}).get('name', '被检查企业')}，检查期间以本轮资料记载期间为准；登记并冻结{files_count}份资料。本轮程序结果为：企业主体、检查轮次和资料范围已经记录；无法由本轮资料覆盖的期间和业务不作外推。"),
        ("逐份读取资料并检查数据质量",
         f"逐份检查资料能否读取、字段是否可定位、金额是否能够重新计算。可完整用于本轮核对{full_read}份，部分读取{partial}份，读取阻断{blocked}份。本轮程序结果为：每份资料均形成明确使用范围；部分读取和阻断内容已经转入补件，不用空结果代替检查。"),
        ("执行单份资料内部复算",
         f"分别检查银行余额连续性、发票号码及金额税额、工资人员和月份、社会保险与住房公积金、账簿借贷及其他已具备字段的内部关系。本轮程序结果为：现有资料能够直接证明的具体问题{len(confirmed)}项，具体见第二部分。"),
        ("执行账、票、表、税、款、货、合同和人员交叉核对",
         "按照实际可用资料，把交易主体、业务期间、合同履约、发票、资金、会计处理和纳税申报连接起来；资料链条缺少节点时停止该项外推。本轮程序结果为：完整具备资料节点的交叉核对链条以实际可用资料为准；仍有资料需要补充识别或修复。"),
        ("检查正常解释、反向证据和税务影响",
         "对每项差异分别检查正常业务原因、反向证据、企业说明、政策适用期间和金额计算条件，避免把异常信号直接写成违法结论。本轮程序结果为：问题部分只保留能够回查到本轮资料的具体事实；税务性质或金额尚不能确定的内容已经明确说明限制。"),
        ("检查应有但未提供的资料及其连带影响",
         "根据企业行业、经营活动和税种，反向检查本轮未取得的申报、账簿、合同、履约、资金、人员、资产和优惠资料。本轮程序结果为：形成受阻检查及补件要求；缺少资料只表示相应检查未完成，不直接认定企业存在违法。"),
        ("形成处理意见、验收标准和下一轮复查计划",
         "对已确认问题逐项提出处理步骤、责任安排、完成标准和应回传资料；对资料缺口明确补齐后必须重跑的检查。本轮程序结果为：本轮保持涉税风险检查工作报告草稿状态。"),
    ]
    return [{"seq": i + 1, "name": name, "narrative": narrative}
            for i, (name, narrative) in enumerate(procedures)]


def _extract_rows_from_actions(fr):
    """从 file_result 的 actions 文本中累加已提取行数（如『提取N条…』『N条流水』）。"""
    total = 0
    for a in (fr.get("actions") or []):
        a = str(a)
        # 优先匹配『提取N条』『N条流水』『N行』『N条…』
        for pat in (r"提取(\d+)[条行]", r"(\d+)条流水", r"(\d+)行", r"(\d+)条"):
            m = re.search(pat, a)
            if m:
                total += int(m.group(1))
                break
    return total


def _build_materials(report_data):
    """按资料类别归并 file_results，生成资料清单（含具体文件名与行数，便于回查与佐证）。"""
    file_results = report_data.get("file_results", []) or []
    groups = OrderedDict()
    for fr in file_results:
        if not isinstance(fr, dict):
            continue
        ftype = fr.get("type", "unknown")
        groups.setdefault(ftype, []).append(fr)

    materials = []
    seq = 1
    for ftype, items in groups.items():
        display = _DOC_TYPE_NAME.get(ftype, "财税资料")
        total_rows = 0
        file_names = []
        for fr in items:
            total_rows += _extract_rows_from_actions(fr)
            fname = fr.get("file") or fr.get("original_name") or fr.get("name")
            if fname:
                # 仅保留文件名，去掉路径，避免泄露目录结构
                base = str(fname).replace("\\", "/").split("/")[-1]
                if base not in file_names:
                    file_names.append(base)
        files_text = "、".join(file_names) if file_names else "（文件名见内部资料底稿）"
        materials.append({
            "seq": seq,
            "document_type": display,
            "display_name": display,
            "read_method": "电子表格/结构化读取",
            "read_result": f"{len(items)}份读取完整，共{total_rows}条记录",
            "use_boundary": "全部可进入本轮自动核对",
            "file_names": file_names,
            "row_count": total_rows,
            "narrative": (
                f"本轮共收到{len(items)}份{display}，读取并进入核对{total_rows}条记录。"
                f"涉及文件为：{files_text}。"
                f"系统通过结构化读取逐份解析，读取结果为{len(items)}份读取完整。"
                f"本轮使用范围为：全部可进入本轮自动核对。文件指纹、解析回执、复算指标和逐行定位保留在内部资料底稿中，可按文件名回查。"
            ),
        })
        seq += 1
    return materials


def _problem_paragraphs(f):
    """从 finding 生成问题说明（2026-09-05 重构：稽查专家写法，四段式）。

    用户批评原八段式「啰嗦、该讲的不讲、废话一堆」。重构原则：
    1. 发现了什么——数字与事实优先，是核心段；
    2. 为什么值得查——风险与正常解释对抗呈现（稽查员的双向思维）；
    3. 怎么查——下一步动作（合并原「企业应当怎样处理」与「本轮建议」，去重）；
    4. 什么时候算完——一句完成标准。
    删除每条约185字的「检查范围方法」重复段（资料范围已在明细与底稿中可回查，
    全报告只在第一章总述一次）与无明细时的「代表性明细」空话段。
    """
    from engine.plain_language import to_plain, to_plain_list
    detail = to_plain(_norm_text(str(f.get("detail") or f.get("description") or "")))
    how = to_plain(_norm_text(str(f.get("how_found") or "")))
    reasons = to_plain_list(f.get("reasonable_explanations") or f.get("alternative_explanations") or [])
    suggestion = to_plain(_norm_text(str(f.get("suggestion") or "")))
    steps = to_plain_list(f.get("resolve_steps") or f.get("investigation_steps") or [])
    src_files = f.get("source_files") or []
    scope_names = set()
    for s in src_files:
        if not isinstance(s, dict):
            continue
        ftype = str(s.get("type") or "")
        if ftype:
            scope_names.add(_DOC_TYPE_NAME.get(ftype, ftype))
        elif s.get("file"):
            scope_names.add(str(s.get("file")))
    scope = "、".join(sorted(scope_names)) or "本轮已上传并成功读取的相关资料"
    tax_impact = _norm_text(str(f.get("tax_impact") or ""))
    if not tax_impact or "尚未形成" in tax_impact:
        tax_impact = "税额影响以完成资料更正、账税核对和重新计算后的结果为准，本项不直接给出应补税额。"

    # 代表性明细：规则显式给的多表优先（detail_tables），否则自动推断单表
    _detail_tables = f.get("detail_tables") or []

    # ── 段1：发现了什么（核心段，数字与事实）──
    fact_text = "经查，" + detail
    fact_text += "（依据资料：" + scope + "，全量筛查，非抽样。）" if scope else ""

    # ── 段2：为什么值得查（风险 + 正常解释对抗呈现）──
    grade = str(f.get("conclusion_grade") or "")
    if grade == "已核定":
        why_text = _conclusion_statement(f)
    else:
        risk_part = "现有资料只能确认可疑信号，还不足以最终定性；需要补充外部证据后才能下结论。"
        why_text = risk_part + tax_impact
        if reasons:
            why_text += "正常业务也可能出现这种情况：" + _seq(reasons, "企业可先按正常原因逐项排除。")

    # ── 段3：怎么查（下一步动作，去重合并）──
    action_items = steps or ([suggestion] if suggestion else [])
    how_text = "下一步查法：" + _seq(action_items, "按真实业务和原始资料查明原因。")

    # ── 段4：什么时候算完 ──
    done_text = "完成标准：每一组差异都有原始资料、原因和处理结果可回查；更正后的数据能与账表核对一致；补充资料重新检查后不再出现同一差异。"

    paragraphs = [
        {"heading": "发现了什么", "text": fact_text},
        {"heading": "为什么值得查", "text": why_text},
        {"heading": "怎么查", "text": how_text},
        {"heading": "什么时候算完", "text": done_text},
    ]
    if _detail_tables:
        # 规则显式给出的多张下钻表（如 VR060 的成本/付款/应付逐笔溯源）
        paragraphs[0]["detail_tables"] = _detail_tables
    else:
        detail_rows, detail_cols = _build_detail_table(f)
        if detail_rows:
            # 把明细表挂在第一段对象上，供前端渲染；同时保留文本回退
            paragraphs[0]["detail_table"] = {"columns": detail_cols, "rows": detail_rows}
    return paragraphs


def _conclusion_statement(f):
    """两级结论文本：可核定→最终答案；待核→建议与补证要求（大白话，2026-09-05）"""
    from engine.plain_language import to_plain
    grade = str(f.get("conclusion_grade") or "")
    if grade == "已核定":
        answer = _norm_text(str(f.get("final_answer") or "").strip())
        scope_note = _norm_text(str(f.get("conclusion_scope_note") or "").strip())
        return to_plain(
            (answer or "本项结论已由本轮所报资料直接计算核定。")
            + (" " + scope_note if scope_note else "")
            + " 本项不需要再补充核实就可以作为定案事实引用；行政处理决定仍由检查人员依程序作出。"
        )
    suggestion = _norm_text(str(f.get("suggestion") or "").strip())
    return to_plain(
        "本项为涉嫌事项：现有资料只能确认可疑信号，还不足以作出最终认定。"
        "需要补充外部证据（合同、物流单据、盘点表、权属证明等）后才能定性。"
        + (f"本轮建议：{suggestion}" if suggestion else "请按本报告关于企业应当怎样处理的说明逐项补证。")
    )


def _naturalize_report_text(text):
    """报告正文自然化：去掉内部字段标记与红线编号，改为自然表述。

    用户要求：给企业看的报告里不要出现「【主张】【线索】【依据】」「RL-PAY-001」
    这类内部标记，一律改为自然语言。此函数是报告输出前的最后一道兜底，
    即使上游（引擎/历史缓存/其他生成路径）带出这些标记，也不会流到企业手上。

    注意：红线编号本身仍保留在 title 之外的 redline_id 字段，供系统内部追溯。
    """
    if not text:
        return text
    import re as _re
    s = str(text)
    # 1) 方头括号字段标记 → 自然表述（长标记优先，避免短标记吃掉长标记前缀）
    for tag, plain in _TAG_PLAIN:
        if tag in s:
            s = s.replace(tag, plain)
    # 2) 残留的其他方头括号标记：直接去掉括号保留内容
    s = _re.sub(r"【([^】]{1,20})】", r"\1：", s)
    # 3) 剥除红线编号（如「触碰税务红线 RL-PTY-001「名称」」→「触碰税务红线「名称」」）
    s = _re.sub(r"红线\s*RL-[A-Z]+-\d+\s*", "红线", s)
    # 4) 其余位置的裸编号一律剥除（如 "RL-PTY-001 采购成本…" → "采购成本…"）
    s = _re.sub(r"RL-[A-Z]+-\d+\s*", "", s)
    # 5) 清理因剥除产生的空括号、重复词与多余空格
    s = _re.sub(r"「\s*」", "", s)
    s = _re.sub(r"税务红线红线", "税务红线", s)   # 防上游已含「税务红线」时叠加
    s = _re.sub(r"([\u4e00-\u9fa5]{2,4})\1", r"\1", s)  # 相邻重复词（如「税务税务」）
    # 6) 去掉系统内部动作 / 推理过程的自述（2026-09-13 用户要求）：报告是给企业的
    #    对外文书，只写「需企业说明什么」，不写「系统做了什么、怎么排除的」。
    #    注意括号内可能再嵌括号（如「（…未达法定退休年龄下限（女50/男60），…）」），
    #    故用「最多一层嵌套」的贪婪式匹配，而非简单的 [^）]* 。
    _nest = r"(?:[^（）]|（[^（）]*）)*"
    s = _re.sub(
        r"（\s*(?:已核|已核实|已比对|已排除|经核|经比对)" + _nest + r"?"
        r"(?:剔除|不成立|已排除|已核|已比对)" + _nest + r"?）", "", s)
    s = _re.sub(
        r"[（(\[【]?\s*系统(?:已|未|将|会|自动)" + _nest + r"?"
        r"(?:剔除|排除|标注|识别|检测|命中|校验|触发)" + _nest + r"?[）)\]】]?", "", s)
    # 7) 内嵌在行内的方括号说明块（如「[系统已自动做伪误判排查: …]」）
    s = _re.sub(r"\[(?:系统|已核)[^\]]{0,200}?\]", "", s)
    # 8) 客观化主语：把「我」开头的自述改为陈述句
    s = _re.sub(r"(?<=[。；\n])我(?:将|已|先|把|对|做|逐|按)", "报告", s)
    s = _re.sub(r"^我(?:将|已|先|把|对|做|逐|按)", "本报告", s)
    s = _re.sub(r"系统(?:已|未|自动)", "", s)
    # 9) 内部术语 → 业务语言的映射**已收敛到 `text_guardrails._DIRECT_REPLACEMENTS`**
    #    （唯一出处；报告闸门 `_zh_normalize_obj` 已接入护栏，故此处不再重复一份）。
    #    收敛原因：原先只在本函数做，而 findings 走的是 `review_finding` 那条路径
    #    → `all_findings[].type` 带着「证据链」进了前端（实测）。
    # ★ 2026-09-25：`裁决` 的映射**已收敛到 `text_guardrails._DIRECT_REPLACEMENTS`**
    #   （唯一出处，改「认定」）。此处原来另有一份 `裁决→结论`，属同一概念两处实现、
    #   且两处口径不同（结论 vs 认定）→ 同一句话在不同渲染路径下说法不一致。
    #   报告净化闸门 `_zh_normalize_obj` 已接入文字护栏，故删掉本地这份。
    # 11) 无异常检查的套话整段删除（2026-09-13 用户要求）：十几项检查原样
    #     复制同一段「检查人员对本项执行了…没有发现…不正常情况」，属无效篇幅。
    #     本节改为只列检查项名称，说明统一在章节导言出现一次。
    if "检查人员对本项执行了本轮规定的检查程序" in s:
        # 非贪婪匹配到本段结束，避免把后文一起吃掉
        s = _re.sub(
            r"检查人员对本项执行了.*?没有发现达到该规则检查条件的不正常情况。", "", s)
    # 12) 符号自然化（2026-09-13 用户要求）：报告读起来是正常句子，
    #     不用直角引号、段落符号与箭头。明细一律走列表，不在正文里堆符号。
    s = _strip_symbol_noise(s)
    s = _re.sub(r"[，。；：]{2,}", lambda m: m.group(0)[0], s)
    s = _re.sub(r"  +", " ", s)
    return s


def _strip_symbol_noise(s):
    """把「」『』·●→ 与 markdown 星号等符号改成正常句子里的标点。

    用户要求「就正常的句子」：资料名、清单名不该带直角引号；查证路径里的
    箭头应写成并列；段落里的中点、圆点是列表符号，应换成句读。
    """
    import re as _re
    # 11.1 红线名：去引号后会与「红线」二字粘连，用「，即」衔接保持通顺
    s = _re.sub(r"红线[「『]([^」』]{1,60})[」』]", r"红线，即\1", s)
    # 11.2 章节/表名引用（『…』）：改成书名号外的自然衔接，直接去引号
    s = s.replace("『", "").replace("』", "")
    # 11.3 其余直角引号：一律去引号保内容（资料名/清单名/字段名）
    s = s.replace("「", "").replace("」", "")
    # 11.4 列表圆点/中点/实心点 → 句读（明细由前端渲染成列表，正文不留符号）
    s = _re.sub(r"\s*[●•‣▪■□○]\s*", "；", s)
    s = s.replace("·", "，")
    # 11.5 箭头：查证路径与流程本是并列关系，改成顿号
    s = s.replace("→", "、")
    s = s.replace("<-", "来自")
    # 11.6 markdown 强调（*纺织产品*）与标题井号：正文里一律去掉
    s = _re.sub(r"\*([^*\n]{1,40})\*", r"\1", s)
    s = _re.sub(r"^\s*#{1,6}\s*", "", s, flags=_re.M)
    # 11.7 清理因替换产生的重复/多余顿号逗号与空括号
    s = _re.sub(r"[、，]{2,}", "、", s)
    s = _re.sub(r"[；；]{2,}", "；", s)
    s = s.strip()
    return s


# 方头括号内部标记 → 自然表述（长标记在前，避免前缀误替换）
_TAG_PLAIN = [
    ("【为何值得查·具体理由】", "之所以值得查，"),
    ("【需企业举证排除的事项】", "需要企业举证说明："),
    ("【需企业补充/系统待接入】", "还需企业补充或系统后续接入的资料："),
    ("【已核实事实·地理背离】", "已经核实："),
    ("【已核实事实·物流缺位】", "已经核实："),
    ("【已核实事实·合同缺位】", "已经核实："),
    ("【已核实事实】", "已经核实的事实是："),
    ("【综合税务合规结论】", "综合各方面情况，税务合规状况如下："),
    ("【经营模式诊断】", "经营模式方面，"),
    ("【核心风险画像】", "主要风险集中在："),
    ("【交叉验证洞察】", "交叉验证后发现，"),
    ("【核查优先级】", "核查的先后顺序建议为："),
    ("【资料质量声明】", "关于资料完整性，需要说明："),
    ("【线索定性】", "本项目前的性质是："),
    ("【企业权利告知】", "需要告知企业的是："),
    ("【主张】", "本项主张是："),
    ("【线索】", "线索方面，"),
    ("【线索链】", "发现过程是，"),
    ("【依据】", "判断依据是："),
    ("【证据】", "证据方面，"),
    ("【反证】", "企业可以申辩的是："),
    ("【裁决】", "本项结论是："),
    ("【编制声明】", "编制说明："),
    ("【本轮报告说明】", "本报告说明："),
    ("【行业对标】", "行业基准方面，"),
    ("【说明】", "说明："),
    ("【短板】", "不足之处是："),
    ("【底线】", "不得突破的底线是："),
]


_SIT_PREFIX_RES = (
    re.compile(r"^资料中直接读到的事实[：:]\s*"),
    re.compile(r"^本轮从所报资料中直接核对到的事实是[：:]\s*"),
    re.compile(r"^第\d+环[：:]\s*"),
)


def _enterprise_situations(arg, clue, cap=8, constituents=None):
    """section 一「涉及的风险事项」bullets 的**单一权威**产出函数。

    返回 (条目列表, 来源)：
      - 有抽象构成要件（_cons 非空）：
          · 有逐条命中（constituent_hits）→ 返回**合并清单**：先一行"本企业涉及上述第 X 条
            构成要件，已核对到的情况见各条括号内标注"，再逐条列出全部抽象要件，命中的在
            括号内标注"本企业：证据"（来源 'constituents'）；
          · 无命中（未取得逐条判定数据）→ 列出全部抽象要件 + 一句说明（来源 'constituents_no_hit'）。
      - 无抽象构成要件（不应发生，68 条红线均≥3 条）→ 回退到本企业**已核对到的具体事实**
        （来源 'facts'）。

    ★ 2026-09-28（用户反转 09-27）：抽象构成要件清单（"凡符合下列构成要件即属涉嫌疑点"）
      与本企业逐条命中**合并进同一清单**，既不互相取代、也不重复罗列——命中的要件直接在其
      括号内标注证据，未命中的照列。这样企业既能看到"什么情形算涉嫌"，又能看到"本企业踩了哪条"。
    facts 的来源优先级：论证 ground（系统实际读到/算出的事实）→ 线索链**已取得数据**的环节 →
    线索链终局信号；做轻量清洗、归一化去重（含"被更长条目包含"的近似重复）、限量。

    cap 必须 ≥ 单条红线可能命中的最大要件数（现行最多 5 条）——过小会**静默截掉**后面的命中要件。
    """
    # ★ 2026-09-28（用户反转 09-27）：优先采用**域逐条判定命中的构成要件**，
    #   按**条款序号**呈现："① 要件原文（本企业：证据）"——要件原文取自红线库（唯一权威），
    #   证据取自域判定。结果作为抽象构成要件清单之后的"本企业实际命中情况"呈现，
    #   不再取代抽象清单。无命中判定时，回退到"本企业实际核对到的事实"（grounds）。
    _hits = arg.get("constituent_hits") or []
    # ★ 要件文本来自**红线定义**（suspicion.constituents），不在 argumentation 里；
    #   调用方必须透传 constituents，否则命中 bullet 会退化成只剩"（本企业：…）"、丢失「① 要件原文」。
    _cons = [str(c).strip() for c in (constituents or arg.get("constituents") or []) if str(c).strip()]
    _circled = "①②③④⑤⑥⑦⑧⑨⑩"
    # ── (A)+(B) 合并为 section 一 的单一 bullet 清单（单一权威产出，消除"抽象清单 vs 本企业命中"重复）──
    if _cons:
        _hit_map = {}
        for h in _hits:
            if isinstance(h, dict) and h.get("index"):
                try:
                    _hit_map[int(h["index"])] = str(h.get("evidence") or "").strip()
                except (TypeError, ValueError):
                    pass
        if _hit_map:
            # 既有抽象要件、又有本企业命中 → 每条要件均列出，命中的在括号内标注本企业证据
            _hit_marks = "".join(_circled[i - 1] for i in sorted(_hit_map)
                                 if 1 <= i <= len(_circled))
            out = [_naturalize_report_text(
                f"经核对，本企业涉及上述第 {_hit_marks or '相关'} 条构成要件，"
                f"已核对到的情况见各条括号内标注：")]
            for i, c in enumerate(_cons, 1):
                mark = _circled[i - 1] if i <= len(_circled) else f"第{i}条"
                if i in _hit_map and _hit_map[i]:
                    out.append(_naturalize_report_text(
                        f"{mark} {c}（本企业：{_hit_map[i]}）".rstrip("。；")))
                else:
                    out.append(_naturalize_report_text(f"{mark} {c}".rstrip("。；")))
            return out, "constituents"
        # 有抽象清单但本轮未取得逐条判定数据 → 仍列抽象清单，并说明
        return ([_naturalize_report_text(c.rstrip("。；")) for c in _cons]
                + [_naturalize_report_text(
                    "（本轮已对该红线逐条核对，尚未取得足以判定各要件的完整数据；"
                    "上列为本红线涉嫌构成要件）")]), "constituents_no_hit"
    # —— 无抽象清单（不应发生，68 条红线均≥3 条）：回退到本企业实际核对到的事实 ——
    raw_items = []

    def _clean(raw):
        s = str(raw or "").strip()
        if not s:
            return ""
        for rx in _SIT_PREFIX_RES:
            s = rx.sub("", s)
        s = s.replace("——", "：").replace("_", "").replace("=", "为").strip()
        return s

    def _key(s):
        return re.sub(r"[\s0-9,.\-—（）()\[\]【】：:；;、，。/％%_=]", "", s)

    for g in (arg.get("grounds") or []):
        c = _clean(g)
        if c:
            raw_items.append(c)
    if not raw_items:
        for n in (clue.get("nodes") or []):
            if n.get("has_data") and n.get("observed"):
                c = _clean(f"{n.get('source') or ''}：{n.get('observed')}")
                if c:
                    raw_items.append(c)
    if not raw_items:
        c = _clean(clue.get("terminal_signal"))
        if c:
            raw_items.append(c)
    keys = [_key(x) for x in raw_items]
    keep, kept_keys = [], []
    for i, x in enumerate(raw_items):
        k = keys[i]
        if not k:
            continue
        if any(i != j and k != keys[j] and keys[j] in k for j in range(len(keys))):
            continue                       # 包含更短条目（是"更啰嗦的同一事实"）→ 丢弃，留干净的短句
        if k in kept_keys:
            continue                       # 完全重复
        keep.append(i)
        kept_keys.append(k)
    return [_naturalize_report_text(raw_items[i]) for i in keep[:cap]], "facts"


def _build_redline_problems(suspicions, findings=None):
    """
    按「税务红线疑点」组装报告主体（2026-09-06 新方法论）

    每条疑点回答五个问题：
      ① 触碰了哪条红线、涉嫌什么、法定依据是什么
      ② 这个疑点是怎么从资料里发现的（每环落到具体数字）
      ③ 现在手上已经有哪些材料、还缺哪些材料、齐全到什么程度
      ④ 本项结论及其理由
      ⑤ 需要补充什么资料或解释才能定性
    """
    problems = []
    # 从原始发现里取规则显式给出的多表下钻，或把逐笔证据 evidence_rows 转成明细表，
    # 挂到「发现的依据」段，让企业看到聚合数背后的明细。
    # ★ 2026-09-26 根因修复：此前只认 detail_tables（全库仅 1 条发现带），
    #   导致 138 条带 evidence_rows 的发现的逐笔明细被静默吞掉；
    #   现统一把 evidence_rows 也视为明细表来源，并支持按 redline_id / 发现类型 关联到疑点。
    _dt_by_rid = {}
    _dt_by_type = {}
    for _f in (findings or []):
        if not isinstance(_f, dict):
            continue
        _tables = _finding_detail_tables(_f)
        if not _tables:
            continue
        _rid = _f.get("redline_id")
        if _rid:
            _dt_by_rid.setdefault(_rid, _tables)
        _tkey = _norm_type_key(_f.get("type") or "")
        if _tkey:
            _dt_by_type.setdefault(_tkey, _tables)
    # ★ 2026-09-27（用户要求）：无线索支撑 / 已排除的结论**不得进「具体问题」**——
    #   否则出现"线索不足，未形成税务疑点"却列为问题的自相矛盾。此处统一滤除，
    #   并使 seq 保持连续（不跳号）。弱结论集来自 argumentation（单一出处）。
    try:
        from engine.argumentation import _VERDICT_WEAK as _VW, _VERDICT_EXCLUDED as _VE
        _weak_verdicts = {str(_VW), str(_VE)}
    except Exception:
        _weak_verdicts = {"线索不足，未形成税务疑点"}
    suspicions = [s for s in suspicions
                  if str((s or {}).get("verdict") or "") not in _weak_verdicts]
    for i, s in enumerate(suspicions, 1):
        arg = s.get("argumentation") or {}
        clue = s.get("clue_chain") or {}
        ev = s.get("evidence_chain") or {}
        rid = s.get("redline_id", "")
        rname = s.get("redline_name", "")
        grade = s.get("conclusion_grade") or arg.get("conclusion_grade") or "待核"

        # ① 红线与法条
        legal = [l for l in (s.get("legal_basis") or []) if l]
        _suspect = str(s.get("suspect") or "税务风险")
        _suspect_txt = _suspect if _suspect.startswith("涉嫌") else f"涉嫌{_suspect}"
        # ★ 2026-09-28（用户反转 09-27 决策）：报告必须**同时**呈现两类信息，二者不可互相替代：
        #   (A) 本红线的**抽象构成要件清单**（「凡符合下列构成要件即属涉嫌疑点」，
        #       红线定义、与具体企业无关）——让企业知道"什么情形算涉嫌"；
        #   (B) 本企业**实际命中哪几条**的逐条判定（_enterprise_situations 取域判定证据）——
        #       让企业知道"本企业踩了哪几条、证据是什么"。
        #   09-27 那版把(A)整个禁掉、只输出(B)，被用户判定为理解错误，现恢复(A)，
        #   且把(B)合并进(A)的同一清单（命中要件在括号内标注证据），不再新增段落、不重复罗列。
        # ★ 2026-09-26 三层术语重标：执行版不写"触碰税务红线/触红成立"（易读成已定性违法），
        #   改为"触发税务风险指标（待核实）"，与决策版口径一致。
        _cons_all = [str(c).strip() for c in (s.get("constituents") or []) if str(c).strip()]
        # _enterprise_situations 是 section 一 bullets 的**单一权威**：有抽象要件时返回
        # 「抽象要件全列 + 命中项括号内标注证据」的合并清单；无抽象要件（不应发生）回退事实。
        _sits, _sit_src = _enterprise_situations(arg, clue, constituents=_cons_all)
        if _cons_all:
            p1 = (
                f"经检查，本企业触发税务风险指标，即{rname}，{_suspect_txt}。"
                f"该风险指标不因行业而变，凡符合下列构成要件即属涉嫌疑点："
            )
            bullets1 = _sits
        else:
            # 防御：红线未定义构成要件（不应发生，68 条均≥3 条），退回旧版单句口径
            p1 = (
                f"经检查，本企业触发税务风险指标，即{rname}，{_suspect_txt}。"
                "经核对，本企业已符合构成此项风险的涉嫌要件。"
            )
            bullets1 = _sits or None
        # ★ 2026-09-27（用户口径）：法定依据须写到**具体哪一条、什么内容**（唯一权威 legal_citation）。
        try:
            from engine.legal_citation import format_legal_basis as _flb
            _legal_txt = _flb(legal)
        except Exception:
            _legal_txt = "；".join(str(x) for x in legal)
        tail1 = _naturalize_report_text(f"法定依据：{_legal_txt}。") if _legal_txt else ""

        # ② 发现过程
        chain_desc = _clue_narrative(clue)
        p2 = (
            "这个疑点不是估计出来的，是从资料里一步步算出来的："
            + (chain_desc or "本轮资料不足以还原完整的发现过程。")
        )
        if clue.get("data_gaps"):
            p2 += "其中" + "、".join(
                f"第{g['step']}环" for g in clue.get("data_gaps", [])
            ) + "因缺少资料未取得数据，已计入检查受限范围。"

        # ③ 已有材料与待补材料
        # ★ 2026-09-25：三态须分开说。「已有」= 名称逐字对应的材料已提交；
        #   「待核」= 清单里有相关类别但未必含本项所需（不得混入"已拿到"）；
        #   「缺失」= 确未提供。旧版把"待核"也写成"已在案"，导致
        #   "企业只交了工资表"被报告写成"劳动合同等材料已在案"。
        _els = ev.get("elements") or []
        have = [e for e in _els if e.get("status") == "已有"]
        verify = [e for e in _els if e.get("status") == "待核"]
        lack = [e for e in _els if e.get("status") == "缺失"]
        # ★ 2026-09-27（用户要求）：材料齐全程度**不得用比例/百分比**表述，
        #   只表述"已有几项、还缺几项"（项数）。closure 仍内部计算（决定能否定性），
        #   但不再进入正文 —— 杜绝"材料齐全程度40%"这类比例表述。
        _need_n = len(_els)
        _have_n = len(have)
        _lack_n = _need_n - _have_n   # 还缺 = 待核 + 缺失（凡未逐字取得的都算还缺）
        p3 = (
            f"要把这一项定下来，需要{_need_n}项材料。"
            + (f"名称逐字对应、已确在手上的有{_have_n}项。" if have
               else "目前还没有一项材料与要求逐字对应。")
            + (f"另有{len(verify)}项须确认已提供资料中是否含该内容。" if verify else "")
            + (f"确未提供的有{len(lack)}项。" if lack else "")
            + f"合计已有{_have_n}项、还缺{_lack_n}项，{ev.get('verdict', '')}。"
            + (f"{ev.get('rebuttal_status', '')}。" if ev.get("rebuttal_status") else "")
        )

        # ④ 论证与理由（上游可能带出内部标记或编号，此处做正文净化兜底）
        p4 = _naturalize_report_text(arg.get("reasoning") or "")
        # ★ 2026-09-29（B2 闭环）：对"以行业基准为判定口径"的红线，论证段补出
        #   按实际行业解析出的基准区间与口径声明（来源 industry_benchmark / industry_data.json，
        #   非税务机关官方口径），使"对照行业基准区间上沿"这类硬化要件真正可核验、不自说自话。
        _bm = arg.get("benchmark_ref") or {}
        _bm_txt = _bm.get("text") if isinstance(_bm, dict) else ""
        if _bm_txt:
            p4 = ((p4 + " " if p4 else "") + _naturalize_report_text(_bm_txt))

        # ⑤ 需企业补充的资料与说明
        # 2026-09-13 用户要求：涉及明细的一律走列表，正文只留引导句，
        # 不再把「第一，…；第二，…」塞进段落里。明细通过 bullets 字段传出。
        actions = [a for a in (arg.get("next_actions") or []) if a]
        p5_lead = "要把这一项查清楚，需要：" if actions else "需要由企业就该项提交书面说明。"
        bullets5 = [_naturalize_report_text(str(a).rstrip("。；"))
                    for a in actions if str(a).strip()]
        tail5 = _naturalize_report_text(f"补救要求：{ev['remedy']}") if ev.get("remedy") else ""

        paragraphs = [
            {"heading": "一、涉及的风险事项", "text": _naturalize_report_text(p1),
             "bullets": bullets1 or None, "tail": tail1},
            {"heading": "二、发现的依据", "text": _naturalize_report_text(p2),
             "detail_table": _clue_table(clue)},
            # 本段明细由 detail_table 承载，不再另出 bullets，避免同一信息重复两遍
            {"heading": "三、已取得的资料与待补充的资料", "text": _naturalize_report_text(p3),
             "detail_table": _evidence_table(ev)},
            {"heading": "四、本项结论及理由", "text": p4},
            {"heading": "五、需企业提供的资料与说明", "text": _naturalize_report_text(p5_lead),
             "bullets": bullets5 or None, "tail": tail5},
        ]

        # 规则显式下钻表 / 逐笔证据表 挂到「发现的依据」段：
        # 先按红线编号精确关联，未命中再按「发现类型 ↔ 疑点名称」关键词重叠兜底关联
        # （覆盖带 evidence_rows 但未打 redline_id 的域发现，如红冲/作废发票）。
        _rid = s.get("redline_id", "")
        _tables = _dt_by_rid.get(_rid) if _rid else None
        if not _tables:
            _tables = _match_suspicion_detail(s, _dt_by_type)
        if _tables:
            paragraphs[1]["detail_tables"] = _tables

        # ★ 2026-09-26：按**证据强度**重排等级（仅覆盖已逐项论证的红线，见 tax_redlines.RISK_LEVEL_BASIS）
        _lb = None
        try:
            from engine.tax_redlines import risk_level_basis as _rlb
            _lb = _rlb(rid)
        except Exception:
            _lb = None
        # ★ 2026-09-27（用户要求）：**分级依据不得缺失**（原仅 4/26 有专属依据）。
        #   无专属依据时给统一口径兜底，并说明该等级是五项综合排序得出。
        _lb_basis = str((_lb or {}).get("basis") or "").strip()
        if not _lb_basis:
            # ★ 2026-09-27（用户要求通俗化）：把"等级依据"兜底文案写成老板能看懂的 5 点大白话。
            _lb_basis = ("风险等级按以下5项综合评定：①可能少缴的税款多少 ②涉及金额大小 "
                         "③还缺哪些证据 ④是否涉嫌虚开发票或偷税 ⑤需要补资料的紧急程度。"
                         "本项没有单独的分级标准，采用全库统一口径。")
        # ★ 2026-09-27（用户要求）：**证据齐全程度不得留空成"0%"**（原 21/26 为空）。
        #   优先取本项证据链的闭合度；确实取不到 → 置 None，由前端**整段省略**该指标，
        #   绝不用 0% 冒充"未评估"。
        _clo = s.get("closure")
        if _clo in (None, ""):
            _clo = ev.get("closure")
        try:
            _clo = round(float(_clo), 4) if _clo not in (None, "") else None
        except (TypeError, ValueError):
            _clo = None
        problems.append({
            "seq": i,
            # 报告标题只写红线名（用户要求：正文不出现 RL-XXX 编号）；
            # 编号仍通过 redline_id 字段透传，供系统内部追溯与前端可选展示。
            "title": _naturalize_report_text(rname.strip() or rid),
            "redline_id": rid,
            "conclusion_grade": grade,
            "verdict": s.get("verdict", ""),
            "confidence": s.get("confidence", 0.0),
            "closure": _clo,
            # ★ 2026-09-27（用户要求）：前端也以项数（已有/还缺）呈现材料齐全程度，
            #   不再显示百分比。closure 仅内部使用（决定能否定性）。
            "evidence_have": int(ev.get("available_count", 0) or 0),
            "evidence_need": int(ev.get("available_count", 0) or 0)
                             + int(ev.get("missing_count", 0) or 0),
            "risk_level": ((_lb or {}).get("level") or s.get("level", "")),
            "risk_level_basis": _lb_basis,
            "suspect": s.get("suspect", ""),
            "taxes": s.get("taxes", []),
            "final_answer": (arg.get("claim", "") if grade == "已核定" else ""),
            "suggestion": _seq(actions, ""),
            "narrative_paragraphs": paragraphs,
            "detail_table": _evidence_table(ev),
            "finding_count": s.get("finding_count", 1),
            "missing_materials": s.get("missing_materials", []),
            "verify_materials": s.get("verify_materials", []),
            "trace_id": (clue.get("nodes") or [{}])[0].get("trace_ref", ""),
        })
    # ★ 2026-09-27（P1）：逐项测算**潜在税额影响**。只认关键词锚定的明确金额，
    #   取不到 → 未量化（绝不猜）；税率与假设见 engine/tax_impact.py。
    try:
        from engine.tax_impact import extract_amount_from_problem, estimate_tax
        for _p in problems:
            _am = extract_amount_from_problem(_p)
            _p["tax_impact"] = estimate_tax((_am or {}).get("amount"), _p.get("taxes"))
            if _am:
                _p["tax_impact"]["amount_context"] = _am.get("context", "")
    except Exception:
        pass
    return problems


# ── 发现过程「实际看到的数据」中文化与降噪（2026-09-12）──────────────────
# 背景：引擎输出的 observed 常带英文字段名与残缺 JSON 碎片
# （如 salary_person_count=6、province_breakdown={广东:{'count': 29, 'amou…），
# 直接进报告既不专业，也把关键数字淹没在噪音里。此处统一转为中文可读表述。
_SOURCE_LABELS = [
    ("social_security", "社保明细"), ("salaries", "工资表"),
    ("tax_declarations", "纳税申报表"), ("declarations", "报关单"),
    ("bank_txs", "银行流水"), ("sal_invs", "销项发票"),
    ("pur_invs", "进项发票"), ("vouchers", "记账凭证"),
    ("inventory", "进销存台账"), ("invoices", "发票"),
    # 2026-09-12 补齐：发现过程 source 全集对齐（required_sources 实测 17 种标识）
    ("inventory_ledger", "进销存台账"), ("company_profile", "企业基础信息"),
    ("contracts", "合同台账"), ("transport_contracts", "运输合同"),
    ("trial_balance", "科目余额表"), ("fixed_assets", "固定资产台账"),
    ("bom", "物料清单"), ("declaration", "纳税申报表"),
    ("target_entity", "目标企业信息"),
    # 2026-09-12 补齐：引擎在「已读取资料」类观测值中输出的单数/别名形式，
    # 缺失会在报告中留下「、、、、、」空顿号（英文标识被清洗后只剩分隔符）。
    ("purchase_invoice", "进项发票"), ("purchase_invoices", "进项发票"),
    ("sales_invoice", "销项发票"), ("sales_invoices", "销项发票"),
    ("salary", "工资表"), ("voucher", "记账凭证"), ("bank_tx", "银行流水"),
    ("sal_inv", "销项发票"), ("pur_inv", "进项发票"), ("contract", "合同台账"),
]
# ── 通用词元翻译（兜底）：映射表之外的 snake_case 指标键按词元拆开翻译 ──
# 整键每个词元都可译才翻译；遇到未知词元则连「键=」一起剔除、只保留数值。
_TOKEN_ZH = {
    "invoice": "发票", "count": "数量", "amount": "金额", "total": "合计",
    "ratio": "占比", "pct": "比例", "rate": "比率", "salary": "工资",
    "social": "社保", "bank": "银行", "cash": "现金", "purchase": "采购",
    "sales": "销售", "sale": "销售", "revenue": "收入", "cost": "成本",
    "supplier": "供应商", "customer": "客户", "person": "人员",
    "month": "月份", "months": "月份", "void": "作废", "red": "红字",
    "matched": "匹配", "unmatched": "未匹配", "input": "进项",
    "output": "销项", "tax": "税款", "declared": "申报", "voucher": "凭证",
    "inventory": "存货", "freight": "运费", "rent": "租金", "welfare": "福利",
    "travel": "差旅", "entertainment": "业务招待", "energy": "能耗",
    "personal": "个人", "collection": "收款", "payment": "付款",
    "paid": "已付", "unpaid": "未付", "examples": "示例",
    "breakdown": "分布", "gap": "差异", "detail": "明细", "names": "名单",
    "list": "清单", "pur": "采购", "sal": "销售", "inv": "发票",
    "num": "数量", "rows": "笔数", "buy": "买入", "sell": "卖出",
    "in": "流入", "out": "流出", "big": "大额", "zero": "零",
    "top": "前列", "avg": "平均", "max": "最大", "min": "最小",
    "receipt": "收款", "wage": "工资", "staff": "员工", "employee": "员工",
    "insured": "参保", "uninsured": "未参保", "cross": "跨",
    "province": "省份", "region": "地区", "processing": "加工",
    "production": "生产", "material": "材料", "raw": "原材料",
    "goods": "品名", "fixed": "固定", "asset": "资产", "dep": "折旧摊销",
    "cit": "企业所得税", "vat": "增值税", "base": "基数",
    "only": "仅在", "duplicate": "重复", "mismatch": "不一致",
    "match": "匹配", "flow": "流水", "tx": "交易", "transfer": "转账",
    "gift": "礼品", "balance": "余额", "profit": "利润", "loss": "亏损",
    "gross": "毛利", "margin": "利润率", "net": "净", "income": "所得",
    "expense": "费用", "subsidy": "补贴", "bonus": "奖金",
    "labor": "劳务", "contract": "合同", "platform": "平台",
    "counterparty": "交易对手", "third": "第三方", "party": "方",
    "near": "临近", "period": "期末", "end": "期末", "abnormal": "异常",
    "anomaly": "异常", "missing": "缺失", "required": "必备",
    "used": "已使用", "usage": "使用", "book": "账面", "actual": "实际",
    "estimated": "估算", "est": "估算", "history": "历史",
    "transport": "运输", "transportation": "运输", "circular": "循环",
    "fund": "资金", "loop": "回流", "top3": "前三",
    "declaration": "申报", "reimbursement": "报销", "rebate": "退税",
    "export": "出口", "import": "进口", "customs": "报关",
    "foreign": "跨境", "exchange": "外汇", "related": "关联",
    # 2026-09-12 二批：findings 观测指标常见词元
    "ad": "广告", "promo": "推广", "added": "新增", "affected": "受影响",
    "after": "之后", "before": "之前", "applied": "已应用", "available": "可用",
    "credit": "贷方", "deal": "交易", "diff": "差异", "violations": "违规",
    "payroll": "工资", "burden": "税负", "change": "变动", "closing": "期末",
    "occurrence": "发生", "company": "公司", "comparable": "可比",
    "completion": "完成", "concentration": "集中度", "confirmed": "已确认",
    "conflict": "冲突", "consumer": "消费", "core": "主营", "correction": "更正",
    "coverage": "覆盖", "critical": "严重", "date": "日期", "declare": "申报",
    "deductible": "可抵扣", "demand": "需求", "item": "项目", "amort": "摊销",
    "deviation": "偏离", "dimension": "维度", "direct": "直接",
    "directional": "方向", "divergence": "背离", "domain": "域",
    "dual": "双重", "role": "角色", "empty": "空值", "evidence": "证据",
    "exact": "精确", "expected": "预期", "file": "文件", "files": "文件",
    "filtered": "过滤后", "finding": "发现", "findings": "发现",
    "four": "四", "star": "星", "further": "进一步", "check": "核查",
    "generic": "通用", "hallucination": "幻觉", "has": "有无",
    "healing": "自愈", "rules": "规则", "rule": "规则", "high": "高",
    "quality": "质量", "risk": "风险", "hit": "命中", "hypothesis": "假设",
    "imbalance": "失衡", "independent": "独立", "source": "来源",
    "indirect": "间接", "industry": "行业", "scene": "场景",
    "insufficient": "不足", "rev": "收入", "issue": "问题", "issues": "问题",
    "major": "主要", "minor": "次要", "markup": "加价", "buyer": "购买方",
    "signals": "信号", "signal": "信号", "category": "类别",
    "memories": "记忆", "meta": "元", "misfire": "误触发", "module": "模块",
    "negative": "负数", "new": "新增", "old": "旧", "no": "无",
    "reissue": "换开", "noise": "噪声", "non": "非", "numeric": "数值",
    "opposing": "对立", "other": "其他", "overlap": "重叠",
    "patterns": "模式", "pending": "待定", "problem": "问题",
    "personnel": "人员", "policies": "政策", "portfolio": "组合",
    "post": "后验", "pre": "先验", "product": "产品", "provided": "已提供",
    "without": "无", "received": "已收到", "reversal": "冲销", "root": "根因",
    "row": "行", "sample": "抽样", "self": "自", "use": "用途",
    "severe": "严重", "shared": "共用", "similar": "相似", "pair": "对",
    "stagnant": "呆滞", "step": "步骤", "submit": "提交", "success": "成功",
    "supporting": "佐证", "suspicion": "疑点", "suspicious": "可疑",
    "system": "系统", "text": "文本", "their": "对方", "three": "三",
    "trace": "追踪", "trigger": "触发", "triggered": "已触发",
    "trusted": "可信", "observation": "观测", "typical": "典型",
    "unbalanced": "失衡", "unbilled": "未开票", "unexplained": "未解释",
    "uniform": "统一", "uninvoiced": "未开票", "unique": "唯一",
    "vals": "取值", "unreported": "未申报", "valid": "有效",
    "verification": "核验", "verified": "已核实", "verify": "核验",
    "warning": "预警", "liability": "负债", "assets": "资产",
    "unexplained_gap": "未解释差异", "co": "共同", "lessons": "教训",
}


def _generic_key_zh(key):
    """把 snake_case 指标键按词元翻译为中文；任一词元未知则返回 None（整键剔除）。"""
    out = []
    for t in key.split("_"):
        if not t:
            continue
        zh = _TOKEN_ZH.get(t)
        if zh:
            out.append(zh)
        elif t.isdigit():
            out.append(t)
        else:
            return None
    return "".join(out) if out else None

_OBSERVED_KEY_LABELS = [
    ("salary_person_count", "工资表人数"),
    ("social_person_count", "社保参保人数"),
    ("salary_only_count", "有工资无社保人数"),
    ("social_only_count", "有社保无工资人数"),
    ("person_account_count", "涉及个人账户数"),
    ("core_cost_total", "主营成本总额"),
    ("ap_summary_balance", "应付账款汇总余额"),
    ("uncovered_amount", "既无付款亦无挂账金额"),
    ("ap_from_trial_balance", "应付来源是否科目余额表"),
    ("core_cost_supplier_breakdown", "主营成本按供应商"),
    ("company_paid_supplier_breakdown", "已付金额按供应商"),
    ("source_documents", "资料来源映射"),
    ("unpaid_amount", "未匹配付款金额"),
    ("unpaid_ratio", "未付款占比"),
    ("supplier_count", "供应商家数"),
    ("province_count", "涉及省份数"),
    ("province_breakdown", "地区分布"),
    ("discount_amount", "折扣折让金额"),
    ("discount_rows", "折扣折让笔数"),
    ("individual_supplier_count", "个人/个体户供应商家数"),
    ("avg_amount_per_individual_supplier", "户均金额"),
    ("supplier_amount", "涉及金额"),
    ("related_party_data", "关联方数据"),
    ("matches", "匹配明细"), ("examples", "示例"),
    ("goods", "品名"), ("count", "家数"), ("amount", "金额"),
    ("name", "姓名"), ("note", "说明"),
    # 高频财务指标整键（避免词元拼接出「毛利利润率比例」这类拗口表述）
    ("gross_margin_pct", "毛利率"), ("purchase_sales_ratio", "购销比"),
    ("customer_top3_ratio", "前三大客户占比"), ("supplier_top3_ratio", "前三大供应商占比"),
    ("bank_in_ratio", "银行流入占收款比"), ("bank_out_ratio", "银行流出占付款比"),
]


def _humanize_observed(text):
    """把引擎原始观测值转为用户可读的中文表述，并剔除 JSON 碎片。"""
    if not text:
        return ""
    s = str(text)
    # ① 先做「键=」整键翻译（必须最先做：后续按子串替换短词会把长键拦腰截断）
    #    精确映射优先，映射表之外的 snake_case 键按词元翻译；
    #    含未知词元的键连「键=」一并剔除、只保留数值，避免英文残留。
    _key_map = dict(_OBSERVED_KEY_LABELS)
    def _gk(m):
        k = m.group(1)
        if k in _key_map:
            return _key_map[k] + "="
        zh = _generic_key_zh(k)
        return zh + "=" if zh else ""
    s = re.sub(r"\b([A-Za-z_][A-Za-z0-9_]*)=", _gk, s)
    # ② 数据源标识（如「已读取资料：salaries」）转中文
    for en, zh in sorted(_SOURCE_LABELS, key=lambda x: -len(x[0])):
        s = s.replace(en, zh)
    # ③ 值域里的短标识（JSON 内部 name:/count:/goods: 等）转中文，长键优先
    for en, zh in sorted(_OBSERVED_KEY_LABELS, key=lambda x: -len(x[0])):
        s = s.replace(en, zh)
    # 去掉 JSON 结构符与引号
    s = re.sub(r"[{}[\]]", "", s)
    s = s.replace("'", "").replace('"', "")
    # 清理残缺标点与空白
    s = re.sub(r"[,，]{2,}", "，", s)
    s = re.sub(r"[:：]\s*(?=[，。；]|$)", "", s)
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[，；。]{2,}", "，", s)
    # 去掉孤立英文单词（长度>=3 的纯字母片段，多为残留标识）
    s = re.sub(r"\b[A-Za-z_]{3,}\b", "", s)
    # 去掉末尾被截断的碎片（无数字且过短的尾段，如 "金额…"）
    segs = [x for x in re.split(r"[，；]", s) if x]
    while segs and not re.search(r"\d", segs[-1]) and len(segs[-1]) <= 4:
        segs.pop()
    # 逐段规整：去掉段尾残留逗号，段内半角逗号统一为顿号
    # （注意：数字千分位逗号「7,747,329.31」必须保留，否则金额被读错）
    def _comma_to_dun(x):
        x = re.sub(r"[,，;；]+$", "", x)
        return re.sub(r"(?<=\D),(?=\D)", "、", x)
    segs = [_comma_to_dun(x) for x in segs]
    # 剔除被清洗后只剩分隔符的空段与空顿号（如「人员薪酬、、、、、社保明细」）
    segs = [re.sub(r"[、，；]{2,}", "、", x).strip("、，；") for x in segs]
    s = "；".join([x for x in segs if x and re.search(r"[\u4e00-\u9fa5\d]", x)])
    s = s.replace("…", "").strip("，；。 ")
    # 观测值里可能夹带上游 finding 的方头括号标记（如「【主营业务成本识别后】…」），
    # 用户要求正文不出现这类内部标记，统一自然化。
    s = _naturalize_report_text(s)
    return s


def _label_source(src):
    """把发现过程的数据源标识（salaries 等）转为中文名称，未知原样返回。"""
    if not src:
        return ""
    s = str(src)
    for en, zh in sorted(_SOURCE_LABELS, key=lambda x: -len(x[0])):
        if s == en:
            return zh
        s = s.replace(en, zh)
    return s


def _dedup_observed(values):
    """相邻环节观测值完全相同时只保留首次，后续标注「同上」，突出差异而非重复。"""
    out = []
    prev = None
    for v in values:
        cur = _humanize_observed(v)
        if cur and prev is not None and cur == prev:
            out.append("同上")
        else:
            out.append(cur)
        if cur:
            prev = cur
    return out


def _clue_narrative(clue):
    """把发现过程讲成大白话，每环带实际数字（中文表述、剔除英文与 JSON 碎片）"""
    nodes = clue.get("nodes") or []
    if not nodes:
        return ""
    observed_list = _dedup_observed([n.get("observed") for n in nodes])
    parts = []
    for i, n in enumerate(nodes):
        seg = f"第{n.get('step')}步从{_label_source(n.get('source')) or '相关资料'}中{n.get('action') or ''}"
        obs = observed_list[i] if i < len(observed_list) else ""
        if obs:
            # 观测值内部的「；」改为「，」，避免与步骤之间的分隔符混淆
            seg += f"，看到{obs.replace('；', '，')}" if obs != "同上" else "，数据与上一环一致"
        parts.append(seg)
    return "；".join(parts) + "。"


def _clue_table(clue):
    """发现过程明细表：环/资料/动作/实际看到（中文表述、相邻重复标注同上）

    ★ 2026-09-25：列名由「使用资料」改为「**对应资料**」。
      该列填的是红线模板声明的**应查资料**（检查路径上"这一环要看什么"），
      不是"本轮实际读了什么" —— 旧列名会让读者误以为这些资料都已读取。
      本轮**实际读取**的资料另在正文中列明，未取得数据的环在「实际看到的数据」列
      会明确写"本轮未取得该环节可量化数据"。
    """
    nodes = clue.get("nodes") or []
    if not nodes:
        return None
    observed_list = _dedup_observed([n.get("observed") for n in nodes])
    return {
        "columns": ["环节", "对应资料", "做了什么", "实际看到的数据"],
        "rows": [
            {"环节": f"第{n.get('step')}环", "对应资料": _label_source(n.get("source", "")),
             "做了什么": n.get("action", ""),
             "实际看到的数据": (observed_list[i] if i < len(observed_list) else "")}
            for i, n in enumerate(nodes)
        ],
    }


def _evidence_table(ev):
    """材料清单：角色/材料名称/证明目的/现状/依据。

    ★ 2026-09-25：新增「依据」列。用户要求「报告每一个字都要能确定可以这么写」——
      只写「已有/缺失/待核」而不写依据，读者无法核验该断言是否成立；
      加上依据后，每个现状都能回指到"哪份已提供材料的哪个称谓"或"哪份材料确未提供"。
      现状三态语义见 engine/evidence_chain.build_evidence_chain 的 docstring：
        已有 = 名称逐字对应；待核 = 有相关类别但须人工确认；缺失 = 确未提供。
    """
    els = ev.get("elements") or []
    if not els:
        return None
    return {
        "columns": ["证据角色", "证据名称", "证明目的", "现状", "依据"],
        "rows": [
            {"证据角色": e.get("role", ""), "证据名称": e.get("name", ""),
             "证明目的": e.get("purpose", ""), "现状": e.get("status", ""),
             "依据": _naturalize_report_text(e.get("basis", ""))}
            for e in els
        ],
    }


def _build_confirmed_problems(report_data):
    """从 findings 组装『确认的具体问题』（level 非待核验/信息的）"""
    # ═══ 新方法论：以「税务红线疑点」为主干（2026-09-06）═══
    _rd = (report_data.get("comprehensive", {}) or {}).get("redline_detection") or {}
    if _rd.get("suspicions"):
        _findings = ((report_data.get("scenario_execution", {}) or {}).get("findings")
                     or report_data.get("all_findings", []) or [])
        return _build_redline_problems(_rd["suspicions"], _findings)
    findings = report_data.get("all_findings", []) or []
    # 缺失型（该有的没有）经竞争假设裁决后仍为"证据不足"的，转「待企业澄清事项」抛企业自证，
    # 不列为已确认问题（避免同一发现既"已核定"又"待证"的矛盾）。
    # 以 hypothesis_verification.details 为权威来源（all_findings 未必回写该标记）。
    _hv = (report_data.get("comprehensive", {}) or {}).get("hypothesis_verification", {}) or {}
    _unconfirmed_types = {d.get("finding_type") for d in (_hv.get("details") or []) if d.get("unconfirmed")}
    problems = []
    for f in findings:
        if not isinstance(f, dict):
            continue
        if f.get("level") in ("待核验", "信息", "低风险"):
            continue
        if f.get("_hypothesis_unconfirmed") is True or (f.get("type") in _unconfirmed_types):
            continue
        ev = f.get("_evidence_ref", {}) or {}
        problems.append((f, {
            "title": (f.get("type") or "具体资料问题").replace("待核事实：", "").replace("待核事实:", ""),
            "conclusion_grade": f.get("conclusion_grade") or "待核",
            "final_answer": str(f.get("final_answer") or ""),
            "suggestion": str(f.get("suggestion") or ""),
            "observed_metrics": _translate_metric_keys(f.get("observed_metrics") or {}),
            "narrative_paragraphs": _problem_paragraphs(f),
            "trace_id": ev.get("trace_id", ""),
        }))
    # ★ 2026-09-26 三版重构：执行版确认问题按「等级 × 金额」排序（重大优先），
    #   TOP5 先呈现，其余保持逐项底稿（前端可折叠）。
    problems.sort(key=lambda fp: (_level_rank(fp[0].get("level")),
                                  (_extract_finding_exposure(fp[0])["amount"] or 0)),
                  reverse=True)
    out = []
    for seq, (f, p) in enumerate(problems, start=1):
        p = dict(p)
        p["seq"] = seq
        out.append(p)
    return out


def _build_completed_checks(report_data):
    """（本章已下线）2026-09-13 用户要求：整节不再列示。

    原「三、已经执行且本轮未发现达到条件异常的检查」：先是把同一段 104 字套话
    复制给每一条检查，改成只列名称清单后，用户仍认为这一节整体不需要——
    没有异常本来就没有可说的内容。故整节下线，报告不再出现。

    保留本函数仅为兼容既有调用方（enterprise_report 组装与 scripts/ 导出脚本），
    恒返回空列表；前端亦不再渲染该章节。
    """
    return []


def _build_action_plan(problems):
    """处理意见（从确认问题派生）：每条按问题类型给出具体整改要点，避免逐条复制同一段套话。"""
    plans = []
    for i, p in enumerate(problems):
        title = p.get("title", "") or "具体资料问题"
        suggestion = _norm_text(str(p.get("suggestion") or "").strip())
        final_answer = _norm_text(str(p.get("final_answer") or "").strip())
        # 具体整改要点：优先用该项已给出的处理建议或已核定结论，回指真实业务
        if suggestion and "尚未形成" not in suggestion:
            core = "本项已给出处理建议：" + suggestion
        elif final_answer and "尚未形成" not in final_answer:
            core = "本项已确认事实为：" + final_answer + "。企业应据此先修复资料与计算口径，再开展账、票、表、税和资金用途核对。"
        else:
            core = f"本项（{title}）须按报告『企业应当怎样处理』一节逐项补证，以原始业务资料查明原因并作真实处理；不得仅以口头说明作为完成依据。"
        gov = "办理须指定熟悉该项业务和资料的负责人，并由另一名人员复核；验收时确认处理过程能够回查、更正后的数据能够与会计和申报资料核对一致。"
        plans.append({
            "seq": _cn_num(i + 1),
            "problem": title,
            "narrative": core + gov,
        })
    return plans


def _build_further_checks(report_data):
    """受阻检查：14 类必查资料中未提交的类别"""
    covered = _doc_covered_categories(report_data)

    missing = [c for c in _REQUIRED_DOC_CATEGORIES if c not in covered]

    further = []
    for i, cat in enumerate(missing):
        further.append({
            "seq": i + 1,
            "title": f"未收到“{cat}”导致相关检查未完成",
            "narrative_paragraphs": [
                {"heading": "本轮检查结论",
                 "text": f"经检查，本轮没有收到这项资料，没法取得完成相关检查所需的完整事实。资料缺失只表示检查范围受限，不表示企业已经存在违法或少缴税的问题。本轮相关检查没有做完，所列风险方向目前没法排除，但不作违法、少缴税款或处罚认定。"},
                {"heading": "被阻断的检查和风险影响",
                 "text": f"由于资料条件不具备，本轮没法完成与“{cat}”相关的账、票、表、税、款交叉核对。目前仍无法排除相应的风险方向。涉及{cat}的检查结论不得显示为无异常或已经合规。"},
                {"heading": "补充资料要求",
                 "text": f"企业应补充{cat}。如原资料客观上无法取得，可以提供能够证明同一事实的替代资料。"},
                {"heading": "下一轮复查程序",
                 "text": f"资料补齐后，检查人员将重新执行受影响的全部检查程序。本项完成标准为：资料能够覆盖本轮检查期间，来源、形成时间、原始版本和具体业务可以回查；补齐后重新运行受影响的全部检查程序。"},
            ],
        })
    return further


def _build_material_readiness(report_data):
    """资料齐备性总览（2026-09-05，用户要求）。

    本轮检查必查资料是否齐全：每类资料给出「已提供/缺失」状态；
    缺失项逐一说明「缺这份资料 → 无法检查哪几方面风险 → 补什么能查清」，
    资料不齐全时显式提醒，让检查范围受限的原因透明可查。
    """
    file_results = report_data.get("file_results", []) or []
    covered = _doc_covered_categories(report_data)

    provided = []
    missing = []
    for cat in _REQUIRED_DOC_CATEGORIES:
        if cat in covered:
            provided.append(cat)
        else:
            entry = next((e for e in _MISSING_DOC_RISK_MAP if e[0] == cat), None)
            if entry:
                missing.append({
                    "doc": entry[0],
                    "uncheckable_risks": entry[1],
                    "remedy": entry[2],
                })
            else:
                missing.append({
                    "doc": cat,
                    "uncheckable_risks": ["相关风险方向"],
                    "remedy": f"提供{cat}，否则相关检查无法完成。",
                })
    total = len(_REQUIRED_DOC_CATEGORIES)
    complete = total - len(missing)
    # ★ 2026-09-25：**文件级**读取失败也要交代 —— 与"整类资料缺失"不同，
    #   这指"文件在清单里、但内容一行都没读到"（路径失效/格式不支持）。
    #   实测事故：24 个文件（12 银行 + 12 社保）内容读不到 → 发现数从 13 静默降到 7，
    #   而报告只说"已提供 8 类"，使用者会把少报当成企业没问题。静默少报比误报更危险。
    read_failures = list(report_data.get("read_failures") or [])
    _rf_note = ""
    if read_failures:
        _rf_note = (
            f"另有 {len(read_failures)} 个文件**未读取到任何数据**（"
            + "、".join(read_failures[:5]) + ("等" if len(read_failures) > 5 else "")
            + "），相关风险方向本轮无法检查，本次结论基于**不完整资料**。"
        )
    return {
        "required_total": total,
        "provided_count": complete,
        "missing_count": len(missing),
        "complete": len(missing) == 0,
        "provided": provided,
        "missing": missing,
        "read_failures": read_failures,
        "partial_data": bool(read_failures),
        "summary_text": (
            f"本轮检查必查资料共 {total} 类，本轮已提供 {complete} 类、缺失 {len(missing)} 类。"
            + ("资料齐全，全部检查程序可执行。" if not missing
               else "资料不齐全：以下缺失将影响相应风险方向的检查（详见缺失清单）。")
            + _rf_note
        ),
    }


def _build_analysis_coverage(report_data):
    """本轮**分析覆盖清单**（现有资料能查多少 / 需补什么才能判定，逐项列明）。

    ★ 2026-09-25 新增：一键分析要当"稽查替身"，就必须能回答"该查的都查了吗、
      没查的为什么"。此前答不出来，出现三类静默：登记了但从不执行（14 项指标中 7 项）、
      整域静态跳过（利润表全 0）、少报被当成没问题。本段把覆盖情况作为一等输出。

    ★ 同日语义纠正（用户宗旨）：本段**不是**"因为缺资料所以没查"的清单，
      而是"现有资料已查尽 + 其余需补充资料方可判定"的**待补自证事项**清单。
      措辞与字段名都按此调整，避免读者误以为系统在等资料齐全才排查。
    """
    cov = report_data.get("analysis_coverage") or {}
    if not isinstance(cov, dict) or not cov.get("total"):
        return {}
    blocked = cov.get("blocked_items") or []
    rows = [{
        "类别": str(it.get("kind") or ""),
        "检查项": str(it.get("name") or ""),
        "需补充的资料": "、".join(it.get("missing") or []),
        "补充后方可判定": str(it.get("effect") or "")[:120],
    } for it in blocked[:200]]
    return {
        "total": cov.get("total", 0),
        "executed": cov.get("executed", 0),
        "awaiting_self_proof": cov.get("awaiting_self_proof", cov.get("blocked", 0)),
        "executed_ratio": cov.get("executed_ratio", 0),
        "summary": str(cov.get("summary_text") or ""),
        "missing_sources": cov.get("missing_sources") or {},
        "columns": ["类别", "检查项", "需补充的资料", "补充后方可判定"],
        "rows": rows,
    }


def _build_one_sided_digest(report_data):
    """「我给了这些资料，你到底都查了哪些」——按已上传资料列出的可独立执行检查。

    ★ 2026-09-25 新增（用户宗旨 D1）：一键分析必须"上传了什么资料就查什么资料"。
      本段逐份资料列出其**单独存在时**即可完成的检查项，让使用者能直接核对
      "我上传的每一份资料是否都被用尽"，而不是只能看到"缺什么"。
    """
    items = report_data.get("one_sided_checks") or []
    if not items:
        return {}
    rows = []
    for it in items:
        for c in (it.get("checks") or []):
            rows.append({
                "已上传资料": str(it.get("source") or ""),
                "可独立完成的检查": str(c.get("name") or ""),
                "查法": str(c.get("how") or "")[:140],
            })
    return {
        "source_count": len(items),
        "check_count": len(rows),
        "columns": ["已上传资料", "可独立完成的检查", "查法"],
        "rows": rows,
    }


def _build_resolution_ledger(report_data):
    """逐项风险的**解除路径与自证清单**（宗旨 D3 + D4）。

    ★ 2026-09-25 新增。用户宗旨原话：
      「反映已查出的税务风险，也反映就已查出的税务风险需要怎样解除风险，
        是否有自证的资料需要补充，最终就是铁证如山或是自证清白。」
    所以每条风险必须同时带出三样东西，缺一不可：
      ① 怎么解除（resolve_steps）；② 需要补什么自证资料（self_proof_materials）；
      ③ 终局方向（terminal_state：铁证如山 / 可自证清白 / 待补自证）。
    没有出口的风险清单对使用者毫无用处 —— 他不知道下一步该做什么。
    """
    findings = [f for f in (report_data.get("all_findings") or []) if isinstance(f, dict)]
    if not findings:
        return {}
    from engine.audit_doctrine import (
        TERMINAL_IRONCLAD, TERMINAL_PENDING, TERMINAL_SELF_PROOF,
        normalize_terminal_state,
    )
    by_state = {TERMINAL_IRONCLAD: [], TERMINAL_SELF_PROOF: [], TERMINAL_PENDING: []}
    rows = []
    tier_stat = {}
    for f in findings:
        state = normalize_terminal_state(f.get("terminal_state"))
        if state in by_state:
            by_state[state].append(f)
        tier = str(f.get("evidence_tier") or "")
        if tier:
            tier_stat[tier] = tier_stat.get(tier, 0) + 1
        resolve = f.get("resolve_steps") or []
        proof = f.get("self_proof_materials") or []
        rows.append({
            "风险事项": str(f.get("type") or ""),
            "等级": str(f.get("level") or ""),
            "证据地位": tier or "未标注",
            "终局方向": state or str(f.get("terminal_state") or "待核"),
            "解除方式": "；".join(str(x) for x in resolve[:6]) or "（待补充资料后由系统给出）",
            "需补自证资料": "；".join(
                "{0}——{1}".format(p.get("material", ""), p.get("proves", ""))
                for p in proof[:6] if isinstance(p, dict)
            ) or "（本项尚需的资料见「分析覆盖」章节）",
        })
    summary = report_data.get("audit_doctrine") or {}
    scope = report_data.get("output_scope") or {}
    # ★ 2026-09-29（C3 风险组合画像）：把跨业务轴组合信号作为一条合成风险事项追加进台账，
    #   使其不被静默丢弃（"查得出来"）；它来自 redline_detection.summary.combo_profiles，
    #   不来自封印后的 all_findings，故不影响封印治理。
    _cp_src = ((report_data.get("comprehensive", {}) or {})
               .get("redline_detection", {}) or {}).get("summary", {}) or {}
    for _cp in (_cp_src.get("combo_profiles") or []):
        if not isinstance(_cp, dict):
            continue
        _labels = "、".join(_cp.get("axis_labels") or [])
        rows.append({
            "风险事项": "多税种联动稽查风险画像（%s）" % _labels,
            "等级": str(_cp.get("level") or "中风险"),
            "证据地位": "组合风险信号（跨%d个业务环节）" % int(_cp.get("axis_count") or 0),
            "终局方向": "待联动核查（多税种）",
            "解除方式": str(_cp.get("recommendation") or "（待联动核查后由系统给出）"),
            "需补自证资料": "；".join("跨税种联动核查：%s" % t
                                  for t in (_cp.get("combined_taxes") or []))
                              or "（本项详见总体结论章及各项贡献红线台账行）",
        })    # ★ 2026-09-25：这两项必须由**最终报告里的发现**现算。
    #   audit_doctrine 汇总是在管道中段生成的（封印/补齐出口之前），
    #   拿它的计数会低估（实测报告 22 条全有出口，汇总里却只写 8 条）。
    with_resolve = sum(1 for f in findings if f.get("resolve_steps"))
    with_proof = sum(1 for f in findings if f.get("self_proof_materials"))
    return {
        "total": len(rows),
        "ironclad": len(by_state[TERMINAL_IRONCLAD]),
        "self_provable": len(by_state[TERMINAL_SELF_PROOF]),
        "pending": len(by_state[TERMINAL_PENDING]),
        "with_resolve": with_resolve,
        "with_self_proof": with_proof,
        # ★ 证据地位分布：报告中所有风险已全部呈现，此处标注各结论的取得方式
        "evidence_tiers": tier_stat,
        "evidence_tier_note": (scope.get("note") or ""),
        "statement": str(summary.get("statement") or ""),
        "columns": ["风险事项", "等级", "证据地位", "终局方向", "解除方式", "需补自证资料"],
        "rows": rows,
    }


def _build_summary(report_data, problems, completed, further):
    from engine.plain_language import to_plain
    findings = report_data.get("all_findings", []) or []
    file_results = report_data.get("file_results", []) or []
    files_count = report_data.get("files_count", len(file_results)) or len(file_results)
    types = {fr.get("type") for fr in file_results if isinstance(fr, dict)}
    te = report_data.get("target_entity", {}) or {}

    key_points = []

    # 专家研判·行业对标置顶：把"毛利率/进销结构 vs 行业基准"的相对判断放在最前，
    # 让报告开篇像人类稽查专家一样先给出"这家企业哪里不对劲"的整体判断，而非平铺规则命中。
    try:
        _reasoning = build_inspector_reasoning(report_data)
        _bench = (_reasoning.get("industry_benchmark") or {}).get("observations") or []
        # "未参与对标"（无收入数据时）不得作为开篇的重点异常，它只是数据缺口说明
        _striking = [o for o in _bench
                     if o.get("direction") not in ("处于合理区间", "未参与对标")]
        if _striking:
            _o = _striking[0]
            _ib = _reasoning.get("industry_benchmark") or {}
            # ★ 2026-09-25：标注行业口径。此前只写"对照XX基准"，读者无法判断这个 XX
            #   是工商登记行业、还是从销项发票品名推断的，出现过"商贸企业被拿橡胶制品
            #   基准判毛利率偏低"这类无法自证来源的表述。
            _src = str(_ib.get("industry_source") or "").strip()
            _src_txt = f"（行业口径：{_src}）" if _src else ""
            key_points.append(
                to_plain(
                    f"【行业对标】对照{_ib.get('benchmark_name', '行业')}基准{_src_txt}，"
                    f"本企业{_o['metric']}{_o['actual']}%（行业{_o['benchmark']}），{_o['direction']}。"
                    f"{_o['why']}"
                )
            )
    except Exception:
        pass

    # ★ 2026-09-26：结论部分不限制字数（用户要求）。逐条列出全部已确认问题，
    #   每条仍保持「标题 + 核心一句（大白话）」的讲重点风格，但不强行截断为前 5 条、
    #   也不再折叠成"另有 N 项"——覆盖完整、可读、通顺。
    #   ★ 2026-09-26 表达升级：红线正文首句的"经检查，本企业触发税务风险指标（待核实），
    #     即<指标名>，"是全局框架（headline 已统一陈述），逐条重复即雷同套话；此处剥掉，
    #     每条只留"涉嫌…"实质一句。另用一句导语一次性说明"待核实 + 详见台账"，不重复 26 次。
    if problems:
        key_points.append(
            "以下疑点均须补充外部证据后方可定性；每一项的事实、涉嫌方向与需补资料，"
            "见本报告『红线疑点』各章与『全部风险事项台账』，本节省复。"
        )
    for p in problems:
        first = p.get("narrative_paragraphs", [{}])[0].get("text", "") if p.get("narrative_paragraphs") else ""
        grade = p.get("conclusion_grade") or "待核"
        # ★ 2026-09-27：待核项不再挂"（待核）"——经大白话层会被改写成"（待核实）"，
        #   与"涉嫌"口径重复；仅保留"（已核定）"以区分已给结论的项，全部待核的口径由导语统一说明。
        grade_tag = "（已核定）" if grade == "已核定" else ""
        # 摘要只写「标题 + 核心一句」（第一个含数字的分句），不把整段 detail 抄进摘要。
        core_line = _strip_redline_prefix(_core_sentence(first))
        key_points.append(to_plain(f"重点{p['seq']}{grade_tag}：{p.get('title', '')}。{core_line}"))
    if further:
        key_points.append(f"还有{len(further)}项检查尚未完成，优先补齐资料。这些事项表示检查范围受限，不表示已经发生相应违法。")

    verified_cnt = sum(1 for p in problems if p.get("conclusion_grade") == "已核定")
    pending_cnt = len(problems) - verified_cnt
    grade_phrase = ""
    if problems:
        if verified_cnt and pending_cnt:
            grade_phrase = (f"其中{verified_cnt}项是账面对账已核定事项，已直接给出最终结论；"
                            f"{pending_cnt}项是涉嫌风险事项，需要补充外部证据后定性，本轮已附上检查建议。")
        elif verified_cnt:
            grade_phrase = f"全部{verified_cnt}项是账面对账已核定事项，已直接给出最终结论。"
        else:
            grade_phrase = f"全部{pending_cnt}项是涉嫌风险事项，需要补充外部证据后定性，本轮已附上检查建议。"

    headline = (f"本次税务风险检查共收到{files_count}个文件，归为{len(types)}类资料。检查人员逐项读取、重新计算、交叉核对后，"
                f"确认{len(problems)}项用现有资料能够证明的具体问题。{grade_phrase}"
                f"{len(further)}项因为资料不足或影响范围还没查清，本轮不下结论，等补充资料后再检查。")

    owner_message = (f"请企业负责人先组织处理本报告列明的具体问题，并按要求补齐资料。"
                     f"完成真实更正和资料补充后，应发起新一轮全量复查，由检查人员继续核对原问题是否处理完成，以及补充资料是否带出新的关联问题。")

    return {
        "headline": headline,
        "owner_message": owner_message,
        "key_points": key_points,
        "received_material_count": files_count,
        "material_category_count": len(types),
        "confirmed_problem_count": len(problems),
        "verified_problem_count": verified_cnt,
        "pending_problem_count": pending_cnt,
        "completed_check_count": len(completed),
        "further_check_count": len(further),
    }


def _build_discovery_overview(report_data, problems, completed, further):
    """本轮全部发现一览：把确认问题、已执行检查、受阻检查合并成一张总表，
    让企业负责人不展开各章就能看到全貌（类型 + 等级 + 一句话结论）。

    用于增厚报告：原来负责人只能逐章钻取，现在第一章即给全景。
    """
    rows = []
    for p in problems:
        first_para = (p.get("narrative_paragraphs") or [{}])[0] or {}
        one_line = _core_sentence(first_para.get("text", ""))
        rows.append({
            "no": p.get("seq"),
            "category": "确认问题",
            "type": p.get("title", ""),
            "grade": p.get("conclusion_grade") or "待核",
            "summary": one_line,
        })
    for c in completed:
        rows.append({
            "no": c.get("seq"),
            "category": "已执行检查",
            "type": c.get("title", ""),
            "grade": "无异常",
            "summary": "本轮资料满足条件且规则已执行，未发现达到检查条件的异常。",
        })
    for f in further:
        rows.append({
            "no": f.get("seq"),
            "category": "受阻检查",
            "type": f.get("title", "").replace("未收到", "缺资料：").replace("导致相关检查未完成", ""),
            "grade": "待补资料",
            "summary": "本轮未收到相应资料，相关检查未能完成；资料补齐后重新检查。",
        })
    return rows


def _build_derivation_tree_report(report_data):
    """疑点派生树（风险检查思维导图 / 洋葱式逐层展开章节）。

    把引擎生成的 derivation_tree 渲染成「剥洋葱」式的可读结构：
    每一层疑点都给出——分析口径 / 佐证动作 / 需补资料 / 派生的连带疑点，
    并标注每个节点永远存在的两种终态：铁证如山 或 待证可自证清白。
    """
    dt = report_data.get("derivation_tree") or {}
    tree = dt.get("tree") or []
    if not tree:
        return None
    note = dt.get("note", "")

    def render_node(n, depth):
        pad = "    " * depth
        lines = []
        rid = n.get("rule_id", "")
        name = n.get("name", rid)
        state = n.get("terminal_state", "")
        if n.get("cycle_ref"):
            lines.append(f"{pad}↺ {name}——（已在上方展开，详见前序节点；防止循环展开）")
            return lines
        lines.append(f"{pad}● {name}")
        lines.append(f"{pad}  终态：{state}")
        if n.get("layer"):
            lines.append(f"{pad}  所属层：{n.get('layer')}")
        link = n.get("link")
        if link:
            lines.append(f"{pad}  派生关系：{link}")
        analyze = n.get("analyze")
        if analyze:
            lines.append(f"{pad}  怎么分析：{analyze}")
        evidence = n.get("evidence")
        if evidence:
            lines.append(f"{pad}  怎么佐证：{evidence}")
        materials = n.get("materials")
        if materials:
            lines.append(f"{pad}  补什么资料：{materials}")
        children = n.get("children") or []
        if children:
            lines.append(f"{pad}  牵连出的疑点（剥下一层）：")
            for c in children:
                lines.extend(render_node(c, depth + 1))
        return lines

    blocks = []
    for root in tree:
        blocks.append("\n".join(render_node(root, 0)))
    body = "\n\n".join(blocks)
    return {
        "title": "疑点派生树（风险检查思维导图 · 洋葱式逐层展开）",
        "summary": f"本轮识别入口疑点 {dt.get('root_count', 0)} 个，经勾稽共派生疑点节点 {dt.get('total_nodes', 0)} 个，"
                   f"最大展开层深 {dt.get('max_depth', 0)} 层。每个疑点被铁证闭合或企业自证清白前，永远存在两种可能。",
        "principle": note,
        "body": body,
    }


def _build_capability_boundary(report_data):
    """能力边界与彻底风险检查路线章节。

    把系统从「接近彻底」再往上推的关键抓手写进报告：明确本系统在数据可触达范围内
    已能近乎彻底覆盖的违法形态、必须依赖外部数据源与人工下户才能查实的形态、以及
    法律责任边界。让每份报告都自带「证据来源局限声明」，既回应「彻底风险检查」诉求，
    又不越界替风险检查员做终裁。
    """
    findings = report_data.get("all_findings", []) or []
    triggered = {f.get("rule_id") for f in findings if isinstance(f, dict) and f.get("rule_id")}

    covered = [
        "申报数据内部矛盾（增值税/企业所得税表间钩稽、税负率异常、未开票收入隐匿）",
        "发票流异常（频繁作废后资金回流、作废未重开未申报、进销严重背离、接受异常凭证）",
        "票账税表款钩稽断裂（有票无货、有货无票、账表不符、申报数与账簿不符）",
        "成本费用真实性缺口（无合同/无运输/无资金流对应的异常进项、委托加工三流缺失）",
        "关联交易与资金回流线索（同一主体兼具供应商与客户、资金闭环、突击注销前转移）",
    ]
    need_external = [
        {"gap": "账外经营 / 私户收款 / 两套账",
         "why": "企业不将上述行为纳入系统可读取资料，纯靠自报数据无法发现",
         "need": "银行对公与对私流水交叉、物流/库存实地盘点、上下游企业开票受票反向比对、第三方支付与现金证据"},
        {"gap": "主观故意定性（偷税 vs 少缴）",
         "why": "系统能证明数据矛盾，但证明不了主观故意",
         "need": "风险检查员结合询问笔录、经营情境、补证反应综合判断，并依法定程序认定"},
        {"gap": "未申报的隐性收入与体外循环",
         "why": "收入未进入任何申报与账簿系统，无内部数据可钩稽",
         "need": "外部涉税数据（金税四期比对、工商股权穿透、社保与人员规模反推产能）"},
    ]
    # 本轮实际触发的规则数，作为「已覆盖维度」的量化注脚
    coverage_note = (
        f"本轮已触发 {len(triggered)} 条可复算规则形成勾稽网络；上述「已覆盖」项均能在"
        f"企业已上传且可读取资料范围内被自动复算与回查。"
    )
    roadmap = [
        "第一阶（本轮已具备）：企业自报资料的票账税表款货合同人员七维闭合勾稽 + 疑点派生树逐层深挖。",
        "第二阶（待接通外部源）：接入财税/开票类与工商风险类数据源，使企业自报数据获得外部独立视角，识别账外与隐性收入。",
        "第三阶（引擎深挖）：打通跨企业关联交易闭环识别，把单户疑点扩展为供应链网状违法图谱。",
    ]
    return {
        "title": "能力边界与彻底风险检查路线",
        "opening": "本节说明本系统在「彻底风险检查企业税收违法行为」这一目标上的实际能力边界，以及继续向上推进的路线。系统已能在数据可触达范围内近乎彻底地发现违法线索，但「彻底」的最后一环依赖外部数据源与人工执法，不在算法能力内。",
        "covered_in_scope": covered,
        "coverage_note": coverage_note,
        "must_rely_on_external": need_external,
        "responsibility_boundary": [
            "系统产出为「待证线索」与「已验证事实」，定性权、执法权与法律责任始终在风险检查员、法制审核与税务机关。",
            "系统结论用于模拟风险检查程序与合规整改，不替代依法送达的税务处理/处罚决定书。",
            "证据不足的事项只列入待补证清单，不以风险评分或模型推测单独认定违法。",
        ],
        "roadmap": roadmap,
        "bottom_line": "系统是企业税收违法风险检查的锋利显微镜与推演器；要逼近「彻底」，必须由系统（数据勾稽）+ 外部源（独立视角）+ 风险检查员（取证与定性）三者合体。单靠系统无法、也不应变身终裁者。",
    }


def _build_cross_enterprise_report(report_data):
    """跨企业关联交易闭环章节（第三阶：单户疑点 → 供应链网状违法图谱）。

    读取引擎已在主链路算好的 comprehensive.cross_enterprise，把「同一实际控制人控制的
    关联企业 / 共享供应商 / 共享客户 / 共享人员」渲染成风险检查文书式可读结构。
    这是把系统从「查一户」推向「查一张网」的关键一档——虚开、洗票、利润转移类违法
    在网状视角下暴露率显著提升。
    """
    comprehensive = report_data.get("comprehensive") or {}
    ce = comprehensive.get("cross_enterprise") or {}
    if not ce:
        return None
    rels = ce.get("relationships") or []
    if not rels:
        return {
            "title": "跨企业关联交易闭环（供应链网状违法图谱）",
            "summary": ce.get("summary", "系统内企业未发现明显跨企业关联关系。"),
            "body": "本轮跨企业关系检测已完成：系统内企业之间的供应商、客户、法定代表人及关键人员均未形成需进一步追查的重合。此结论仅基于本轮可读取的企业主体与发票往来数据；如存在未纳入系统的关联企业，须通过外部工商股权穿透补充核查（见「能力边界与彻底风险检查路线」）。",
            "risk_links": [],
        }

    TYPE_CN = {
        "shared_supplier": "共享供应商",
        "shared_customer": "共享客户",
        "shared_personnel": "共享人员（法人/股东/董事/监事）",
        "same_legal_rep": "同一法定代表人",
    }
    REL_RISK_HINT = {
        "shared_supplier": "可能为同一实际控制人通过多家企业操纵供应链、拆分业务或虚增成本",
        "shared_customer": "需排查是否通过多主体分散收入、转移利润或循环开票",
        "shared_personnel": "人员重合指向同一实际控制人控制的关联企业群",
        "same_legal_rep": "同一法定代表人直接构成关联企业，资金与业务往来须逐笔核实独立性",
    }
    lines = []
    risk_links = []
    for r in rels:
        t = r.get("type", "")
        tcn = TYPE_CN.get(t, t)
        a, b = r.get("company_a", ""), r.get("company_b", "")
        ents = r.get("shared_entities") or []
        lvl = r.get("risk_level", "")
        lines.append(f"● [{a}] ↔ [{b}]　关系：{tcn}（{lvl}风险）")
        if ents:
            lines.append(f"  重合实体：{'、'.join(ents[:8])}{'…' if len(ents) > 8 else ''}")
        lines.append(f"  风险检查指向：{REL_RISK_HINT.get(t, r.get('description', ''))}")
        risk_links.append({
            "pair": f"{a} ↔ {b}",
            "type": tcn,
            "risk_level": lvl,
            "shared": ents,
            "hint": REL_RISK_HINT.get(t, r.get("description", "")),
        })
    body = "\n".join(lines)
    high = sum(1 for r in rels if r.get("risk_level") == "high")
    return {
        "title": "跨企业关联交易闭环（供应链网状违法图谱）",
        "summary": ce.get("summary", ""),
        "body": body,
        "risk_links": risk_links,
        "high_risk_count": high,
        "note": (
            f"本轮识别跨企业关联关系 {len(rels)} 条（高风险 {high} 条）。上述关系为企业主体与发票往来数据"
            f"自动勾稽所得，属「待证线索」：是否构成关联交易违法，须风险检查员结合资金流水、合同实质与询问"
            f"笔录进一步核实，并依法定程序认定。"
        ),
    }


def _build_external_verify_report(report_data):
    """第二阶：外部工商/风险核验章节——企业自报数据之外的独立视角。

    数据来自 report_data["comprehensive"]["external_verify"]
    （engine/external_verifier 的 ExternalVerificationEngine.verify 输出）。
    免费通道（国家企业信用公示系统+搜索引擎）已实装；天眼查/企查查需 token。
    """
    ce = (report_data.get("comprehensive") or {}).get("external_verify") or {}
    if not ce:
        return {
            "title": "外部工商与风险核验（企业自报数据之外的独立视角）",
            "available": False,
            "summary": "本轮未获取外部核验数据（企业名称缺失或核验通道未响应）。",
            "body": "未纳入外部工商/风险核验。属系统能力边界内的待补强项："
                    "当企业账外经营、私户收款或借壳控制时，仅看企业自报数据不足以发现，"
                    "须通过外部工商、股权穿透、行政处罚与涉诉记录交叉验证。",
            "channels": [],
            "signals": [],
            "verdict": "无法核验",
            "recommendation": "建议接通天眼查/企查查或国家企业信用公示系统后重新核验。",
            "note": "外部核验结论属「待证线索」，仅供风险检查员延伸调查参考，不作为定性依据。",
        }

    channels = ce.get("channels_used") or []
    results = ce.get("results") or {}
    assessment = ce.get("assessment") or {}
    verdict = assessment.get("verdict", "无法核验")
    rec = assessment.get("recommendation", "")
    risk_signals = assessment.get("risk_signals") or []

    # 整理各通道关键信息
    chan_summary = []
    for ch, res in results.items():
        if not isinstance(res, dict):
            continue
        if res.get("status") == "跳过(免费模式)":
            chan_summary.append(f"{ch}：付费通道（本次未启用）")
            continue
        if not res.get("ok"):
            chan_summary.append(f"{ch}：未响应（{str(res.get('error',''))[:40]}）")
            continue
        if ch == "国家企业信用信息公示系统":
            st = res.get("status", "未知")
            chan_summary.append(f"{ch}：工商状态={st}，存续={res.get('is_active')}，异常={res.get('is_abnormal')}")
        elif ch == "搜索引擎综合核实":
            chk = res.get("checks") or {}
            det = "、".join([f"{k}={'有' if v else '无'}" for k, v in chk.items()])
            chan_summary.append(f"{ch}：{det}；综合={res.get('assessment','')}")
        else:
            chan_summary.append(f"{ch}：{res.get('source','')} 已响应")

    # 风险信号 → 风险检查指向
    REL_HINT = {
        "企业状态异常": "关注是否借注销/吊销前转移收入、逃避税款；核查注销前突击开票与资金流向。",
        "高风险": "外部多源提示高风险，结合自报数据核查是否存在账外经营或隐瞒收入。",
        "经营异常": "列入经营异常名录，核查实际经营地址与申报一致性、是否空壳。",
        "处罚记录": "存在行政处罚记录，核查历史违法类型是否涉及虚开发票/偷税，警惕重复违法。",
        "涉诉记录": "存在涉诉/裁判记录，核查是否涉及合同诈骗、虚开增值税专用发票等。",
    }
    signals = []
    for s in risk_signals:
        hint = ""
        for k, v in REL_HINT.items():
            if k in s:
                hint = v
                break
        signals.append({"signal": s, "hint": hint or "建议风险检查员延伸核实。"})

    lines = [f"外部核验通道：{('、'.join(channels)) if channels else '无'}"]
    for cs in chan_summary:
        lines.append(f"● {cs}")
    if signals:
        lines.append("风险信号与风险检查指向：")
        for s in signals:
            lines.append(f"  - {s['signal']} → {s['hint']}")
    body = "\n".join(lines)

    return {
        "title": "外部工商与风险核验（企业自报数据之外的独立视角）",
        "available": True,
        "summary": f"本轮通过{len([c for c in channels if c not in ('天眼查','企查查')])}个免费通道对企业工商与风险状况作独立核验，"
                   f"综合结论：{verdict}。",
        "body": body,
        "channels": chan_summary,
        "signals": signals,
        "verdict": verdict,
        "recommendation": rec,
        "note": "外部核验结论属「待证线索」，由企业自报数据之外的公开/第三方视角所得，仅供风险检查员延伸调查参考，"
                "不作为定性依据；付费深度通道（天眼查/企查查）配置 token 后可自动启用，进一步穿透股权与关联企业。",
    }


def _build_bank_flow_report(report_data):
    """第四阶 P0：银行流水（资金流）比对章节。

    数据来自 report_data["comprehensive"]["bank_flow"]
    （engine/bank_flow.run_bank_flow_compare 输出）。
    """
    bf = (report_data.get("comprehensive") or {}).get("bank_flow") or {}
    if not bf:
        return {
            "title": "银行流水（资金流）比对",
            "available": False,
            "summary": "本轮未提供银行流水，未做资金流比对。",
            "body": "银行流水是数电票时代暴露账外经营、私户收款、未开票收入的核心依据，也是风险检查必收资料。"
                    "未提供则无法量化资金流与申报收入的偏离。",
            "signals": [],
            "verdict": "未提供银行流水",
            "recommendation": "上传企业银行流水（含交易日期、对方户名、借贷金额、摘要）。",
            "note": "银行流水比对结论属「待证线索」，需逐笔核实，不作为定性依据。",
        }

    metrics = bf.get("metrics") or {}
    signals = bf.get("signals") or []
    verdict = bf.get("verdict", "")
    body = bf.get("body", "") or ""

    return {
        "title": "银行流水（资金流）比对",
        "available": True,
        "summary": bf.get("summary", ""),
        "body": body,
        "metrics": metrics,
        "signals": signals,
        "verdict": verdict,
        "recommendation": bf.get("recommendation", ""),
        "note": bf.get("note", "银行流水比对结论属「待证线索」，需逐笔核实，不作为定性依据。"),
    }


def _build_two_tax_report(report_data):
    """第四阶 P0：增值税收入 vs 企业所得税收入差异比对章节。

    数据来自 report_data["comprehensive"]["two_tax_income"]
    （engine/two_tax_income.run_two_tax_compare 输出）。
    """
    tt = (report_data.get("comprehensive") or {}).get("two_tax_income") or {}
    if not tt:
        return {
            "title": "增值税收入 vs 企业所得税收入差异比对",
            "available": False,
            "summary": "本轮未提供增值税申报表与企业所得税申报表，未做两税收入勾稽。",
            "body": "增值税申报销售额与企业所得税申报营业收入的勾稽，是数电票时代暴露所得税少计收入、"
                    "隐匿利润的第二条主线证据（第一主线为银行资金流）。两税分属不同申报表、自动预填互不校验，"
                    "税局不会自动拦截其背离。未提供两税申报表则无法量化该差异。",
            "signals": [],
            "verdict": "未提供两税申报表",
            "recommendation": "上传增值税纳税申报表与企业所得税纳税申报表（年度汇算清缴/季度预缴均可）。",
            "note": "两税收入差异比对结论属「待证线索」，需结合收入确认政策与纳税调整底稿核实，不作为定性依据。",
        }

    metrics = tt.get("metrics") or {}
    signals = tt.get("signals") or []
    verdict = tt.get("verdict", "")
    body = tt.get("body", "") or ""

    return {
        "title": "增值税收入 vs 企业所得税收入差异比对",
        "available": True,
        "summary": tt.get("summary", ""),
        "body": body,
        "metrics": metrics,
        "signals": signals,
        "verdict": verdict,
        "recommendation": tt.get("recommendation", ""),
        "note": tt.get("note", "两税收入差异比对结论属「待证线索」，需结合收入确认政策与纳税调整底稿核实，不作为定性依据。"),
    }


def _build_revenue_authenticity_report(report_data):
    """收入真实性（账外收入嫌疑）三维度三角验证章节（2026-09-14 新增）。

    数据来自 report_data["comprehensive"]["revenue_authenticity"]
    （engine/revenue_authenticity.run_revenue_authenticity_check 输出）。
    把"银行收款>申报收入→账外收入"拆为 维度1发票↔申报 / 维度2发票↔银行 /
    维度3应收账龄 三路并行验证，综合裁定三态。
    """
    ra = (report_data.get("comprehensive") or {}).get("revenue_authenticity") or {}
    if not ra:
        return {
            "title": "收入真实性（账外收入嫌疑）",
            "available": False,
            "summary": "本轮未提供销项发票、银行流水或申报表，未做收入真实性三维度验证。",
            "body": "收入真实性（账外收入嫌疑）以「银行收款>申报收入」为起点信号，经发票↔申报、发票↔银行、"
                    "应收账龄三维度交叉验证后出综合裁定。缺少任一基础数据均无法量化，须补证后复核。",
            "signals": [],
            "verdict": "未提供基础数据",
            "recommendation": "上传销项发票、银行收款流水与增值税申报表，并尽量提供应收账款明细表（含账龄）。",
            "note": "结论属待证线索，不作为定性依据；银行收款大于申报收入本身不构成确认。",
        }

    metrics = ra.get("metrics") or {}
    signals = ra.get("signals") or []
    verdict = ra.get("verdict", "")
    body = ra.get("body", "") or ""
    dims = ra.get("dimensions") or {}

    return {
        "title": "收入真实性（账外收入嫌疑）",
        "available": True,
        "summary": ra.get("summary", ""),
        "body": body,
        "metrics": metrics,
        "signals": signals,
        "verdict": verdict,
        "recommendation": ra.get("recommendation", ""),
        "note": ra.get("note", "结论属待证线索，不作为定性依据；银行收款大于申报收入本身不构成确认，须三维交叉验证后出嫌疑结论。"),
        "dimensions": dims,
    }


def _build_input_voucher_report(report_data):
    """第四阶 P1：进项异常凭证 / 应转出未转出比对章节。"""
    iv = (report_data.get("comprehensive") or {}).get("input_voucher") or {}
    if not iv:
        return {
            "title": "进项异常凭证 / 应转出未转出比对",
            "available": False,
            "summary": "本轮未提供进项发票数据。",
            "body": "进项异常凭证（上游走逃失联、非正常户开具）与应进项转出未转出（购进用于免税、"
                    "集体福利、个人消费、非正常损失等）是数电票下票表比对仍会自动放行的风险点。未提供进项发票则无法量化。",
            "signals": [],
            "verdict": "未提供进项发票",
            "recommendation": "上传进项发票/进项抵扣勾选明细，并粘贴上游异常凭证清单。",
            "note": "进项异常凭证比对结论属「待证线索」，不作为定性依据。",
        }
    return {
        "title": "进项异常凭证 / 应转出未转出比对",
        "available": True,
        "summary": iv.get("summary", ""),
        "body": iv.get("body", "") or "",
        "metrics": iv.get("metrics") or {},
        "signals": iv.get("signals") or [],
        "verdict": iv.get("verdict", ""),
        "recommendation": iv.get("recommendation", ""),
        "note": iv.get("note", "进项异常凭证比对结论属「待证线索」，不作为定性依据。"),
    }


def _build_false_invoice_report(report_data):
    """第四阶 P1：虚开风险网络比对章节。"""
    fi = (report_data.get("comprehensive") or {}).get("false_invoice") or {}
    if not fi:
        return {
            "title": "虚开风险网络比对",
            "available": False,
            "summary": "本轮未提供进/销项发票数据。",
            "body": "虚开（票真业务假）是数电票下票表比对自动放行的盲区，需结合进销项背离、集中顶额开票、"
                    "资金回流闭环与跨企业图谱才能暴露。未提供发票则无法量化。",
            "signals": [],
            "verdict": "未提供发票数据",
            "recommendation": "上传销/进项发票、银行流水与关联企业清单。",
            "note": "虚开风险比对结论属「待证线索」，系统不替代主管机关认定。",
        }
    return {
        "title": "虚开风险网络比对",
        "available": True,
        "summary": fi.get("summary", ""),
        "body": fi.get("body", "") or "",
        "metrics": fi.get("metrics") or {},
        "signals": fi.get("signals") or [],
        "verdict": fi.get("verdict", ""),
        "recommendation": fi.get("recommendation", ""),
        "note": fi.get("note", "虚开风险比对结论属「待证线索」，系统不替代主管机关认定。"),
    }


def _build_fund_loop_report(report_data):
    """第四阶 P1：跨企业资金回流闭环比对章节。"""
    fl = (report_data.get("comprehensive") or {}).get("fund_loop") or {}
    if not fl:
        return {
            "title": "跨企业资金回流闭环",
            "available": False,
            "summary": "本轮未提供银行流水。",
            "body": "资金回流闭环（货款回流至开票方/关联方）是虚开与账外经营的关键证据，"
                    "需银行流水结合跨企业图谱才能识别。未提供银行流水则无法做闭环检测。",
            "signals": [],
            "verdict": "未提供银行流水",
            "recommendation": "上传企业银行流水并提供关联企业清单。",
            "note": "资金回流闭环识别属「待证线索」，不作为定性依据。",
        }
    return {
        "title": "跨企业资金回流闭环",
        "available": True,
        "summary": fl.get("summary", ""),
        "body": fl.get("body", "") or "",
        "metrics": fl.get("metrics") or {},
        "signals": fl.get("signals") or [],
        "verdict": fl.get("verdict", ""),
        "recommendation": fl.get("recommendation", ""),
        "note": fl.get("note", "资金回流闭环识别属「待证线索」，不作为定性依据。"),
    }


def _build_inspection_questions_report(report_data):
    """十八、风险检查询问清单与待澄清事项：把系统识别的待证线索转化为企业可答复、可举证的具体问题。
    补偿系统做不了的下户盘货/查金税四期/穿透资金最终去向——以提问引导企业自证自改。"""
    comp = report_data.get("comprehensive", {}) or {}
    iq = comp.get("inspection_questions") or {}
    if not isinstance(iq, dict) or not iq.get("available"):
        return {
            "title": "十八、风险检查询问清单与待澄清事项",
            "available": False,
            "summary": "本轮未生成风险检查询问事项（未发现需置疑的线索或资料不足未触发）。",
            "themes": [],
            "note": "系统不能下户盘货、不能查金税四期、不能穿透资金最终去向；如后续补充资料或发现新线索，将重新生成询问清单。",
        }
    themes = iq.get("themes") or []
    return {
        "title": "十八、风险检查询问清单与待澄清事项",
        "available": True,
        "summary": iq.get("summary", ""),
        "verdict": iq.get("verdict", ""),
        "recommendation": iq.get("recommendation", ""),
        "note": iq.get("note", ""),
        "themes": [
            {
                "theme": t.get("theme", ""),
                "severity": t.get("severity", ""),
                "questions": [
                    {
                        "question": q.get("question", ""),
                        "basis": q.get("basis", ""),
                        "materials": q.get("materials", []),
                        "resolves": q.get("resolves", ""),
                        "system_gap": q.get("system_gap", ""),
                    }
                    for q in t.get("questions", [])
                ],
            }
            for t in themes
        ],
    }


def _build_main_assessment(problems):
    """★ 2026-09-27（P2）：具体问题章首的**主线研判**——最可能的 2–3 个问题方向及依据。

    数据驱动：复用 `overall_conclusion._group_by_theme`（按风险性质归纳，单一出处）
    与 `_collect_directions`（真实 suspect 扫描），再按"项数 × 等级权重"排序取前三。
    不引入任何新素材，只把已有事项**收敛成一句判断**，避免平铺 26 条。
    """
    problems = [p for p in (problems or []) if isinstance(p, dict)]
    if not problems:
        return {}
    try:
        from engine.overall_conclusion import _group_by_theme, _collect_directions
        themes = _group_by_theme(problems)
        dirs = _collect_directions(problems)
    except Exception:
        themes, dirs = [], []
    _rank = {"极高风险": 5, "高风险": 4, "中风险": 3, "待核验": 2, "低风险": 0, "信息": 0}

    def _lv(p):
        return str(p.get("risk_level") or p.get("level") or "")
    lv_counts = {}
    for p in problems:
        lv_counts[_lv(p)] = lv_counts.get(_lv(p), 0) + 1
    # 主题 → 高风险项数（用于排序）
    _high_by_theme = {}
    for p in problems:
        if _lv(p) != "高风险":
            continue
        for g in themes:
            if p.get("title") in (g.get("items") or []):
                _high_by_theme[g["theme"]] = _high_by_theme.get(g["theme"], 0) + 1
                break
    top = sorted(themes, key=lambda g: (-(int(g.get("count") or 0) * 2 + _high_by_theme.get(g["theme"], 0))))[:3]
    if not top:
        return {}
    _parts = []
    nums = ["①", "②", "③"]
    for i, g in enumerate(top):
        _reps = "、".join((g.get("items") or [])[:1])
        _hi = _high_by_theme.get(g["theme"], 0)
        _parts.append("%s「%s」%d 项%s%s" % (
            nums[i] if i < len(nums) else "·", g.get("theme"), g.get("count"),
            ("（含高风险 %d 项）" % _hi) if _hi else "",
            ("，代表事项：%s" % _reps) if _reps else ""))
    _lv_txt = "、".join("%s %d 项" % (k, v) for k, v in lv_counts.items() if v)
    seg = ("主线研判：本轮共 %d 项风险事项（%s）。按事项数量、风险等级、证据地位与潜在税额影响"
           "综合排序，本轮最可能的问题方向为：%s。" % (len(problems), _lv_txt, "；".join(_parts)))
    if dirs:
        seg += "可能涉及的涉嫌方向包括：" + "、".join(dirs) + "等。"
    seg += "据此，建议按上述顺序优先组织核实与整改。"
    return {
        "available": True,
        "directions": [{"theme": g["theme"], "count": g.get("count"),
                        "high": _high_by_theme.get(g["theme"], 0)} for g in top],
        "paragraph": seg,
    }


def _build_industry_benchmark_report(report_data):
    """行业指标对标章节：本企业指标 vs 同行业预警区间。

    数据来源为 industry_benchmark 探测器产出的待核线索（带 _indicator 标记）。
    区间来源会明确标注是"实测校准"还是"通用参考"，避免把经验值当作官方口径。
    """
    findings = [f for f in (report_data.get("all_findings") or [])
                if isinstance(f, dict) and f.get("_indicator")]
    if not findings:
        return {
            "available": False,
            "title": "行业指标对标",
            "summary": "本次未触发行业指标偏离线索。",
            "body": "", "metrics": {}, "signals": [], "verdict": "未发现异常",
            "recommendation": "", "note": "",
        }
    # ★ 2026-09-27（用户要求）：必须写清**对标的行业口径**与**区间来源**，
    #   否则读者无法判断这个区间是哪个行业的、是否可靠。
    _te = report_data.get("target_entity") or {}
    _ind_name = str(_te.get("industry") or "").strip()
    _ind_src = str(_te.get("_industry_source") or "").strip()
    _scope = ""
    if _ind_name:
        _scope = ("本企业对标的行业口径为「%s」%s。"
                  % (_ind_name, ("（来源：%s）" % _ind_src) if _ind_src else ""))
    lines = [_scope + "本企业实际指标与同行业预警区间比对如下（偏离项列为待核线索）：", ""]
    metrics = {}
    for f in findings:
        key = f.get("_indicator", "")
        actual = f.get("_actual")
        rng = f.get("_range") or []
        src = f.get("_benchmark_source", "通用参考")
        label = {"vat_burden": "增值税税负率", "gross_margin": "毛利率",
                 "expense_ratio": "期间费用率", "purchase_sales": "进销比"}.get(key, key)
        unit = "" if key == "purchase_sales" else "%"
        lines.append(
            f"· {label}：实际 {actual}{unit}，行业区间 {rng[0] if rng else '-'}~{rng[1] if len(rng)>1 else '-'}{unit}"
            f"（区间来源：{src}）"
        )
        metrics[label] = f"{actual}{unit}"
    body = "\n".join(lines)
    return {
        "available": True,
        "title": "行业指标对标",
        "summary": f"共 {len(findings)} 项指标偏离同行业预警区间，须结合经营模式核实是否存在合理原因。",
        "body": body,
        "metrics": metrics,
        "signals": [{"signal": f.get("type", ""), "hint": f.get("suggestion", "")} for f in findings],
        "verdict": "待证线索",
        "recommendation": "请就偏离项说明原因，并提供行业可比资料与适用税收优惠备案资料。",
        "note": "预警区间为通用参考值或本地实测校准值，非税务机关官方口径；"
                "偏离区间仅构成待证线索，不作为定性依据。",
    }


def _build_related_party_report(report_data):
    """关联方穿透章节：同源信号 + 人员穿透（法人/股东/董监高）。"""
    findings = [f for f in (report_data.get("all_findings") or [])
                if isinstance(f, dict) and (f.get("_related_party_graph") or f.get("_officer"))]
    if not findings:
        return {
            "available": False,
            "title": "关联方穿透分析",
            "summary": "本次未发现关联方同源信号。",
            "body": "", "metrics": {}, "signals": [], "verdict": "未发现异常",
            "recommendation": "", "note": "",
        }
    lines = ["从交易数据与任职持股登记中识别到以下关联方线索：", ""]
    for f in findings:
        lines.append(f"· {f.get('type','')}（{f.get('level','')}）")
        lines.append(f"  {f.get('detail','')}")
        lines.append("")
    return {
        "available": True,
        "title": "关联方穿透分析",
        "summary": f"识别到 {len(findings)} 条关联方线索，须核实是否存在关联交易与转移定价。",
        "body": "\n".join(lines),
        "metrics": {"关联方线索数": len(findings)},
        "signals": [{"signal": f.get("type", ""), "hint": f.get("suggestion", "")} for f in findings],
        "verdict": "待证线索",
        "recommendation": "请说明相关主体股权与人员关系，并提供关联交易定价政策与同期资料。",
        "note": "本系统无外部工商数据库，关联关系依据账套内同源信号与任职登记推定，"
                "仅作待证线索，不构成关联交易或转移利润的认定。",
    }


# ════════════════════════════════════════════════════════════════════════════
# 风险敞口（潜在最大损失）抽取工具 —— 供企业报告通用复用
# 取数铁律：取不到金额时返回 {amount:None, confidence:"未量化"}，绝不编造数字；
# 金额只给“潜在最大敞口”，最佳/最小估计需概率输入（未提供时不臆造）。
# ════════════════════════════════════════════════════════════════════════════

# 暴露金额（敞口）相关键提示（中英双语，匹配 observed_metrics 顶层键）。
# 用“具体前缀”避免 over→cover、red→declared 的贪婪误命中；计数/上下文先排除再判敞口。
_BOSS_EXPO_PREFIX = ("gap", "mismatch", "unmatched", "short", "deficit", "excess",
                     "violation", "false", "refund", "late", "exposure", "risk",
                     "penalty", "diff", "void", "over_limit", "over_amount",
                     "over_declared", "under_paid", "under_declared", "under_amount",
                     "redline", "uncovered")
_BOSS_EXPO_CN = ("差额", "差异", "缺口", "未匹配", "少缴", "应补", "补缴", "违规",
                 "虚列", "多列", "超限额", "未计提", "未转出", "未申报", "退税",
                 "滞纳", "敞口", "风险金额", "潜在", "红冲", "作废")
# 列表型字段名若出现这些 token，则其内部 amount 可汇总为敞口（如 private_paid_records）
_BOSS_LIST_EXPO_TOKEN = ("paid", "private", "void", "red", "unmatched", "mismatch",
                         "penalty", "refund", "late", "false", "over_limit", "short",
                         "deficit", "uncovered", "underpaid", "under_declared")
# 顶层键后缀黑名单（计数/率/示例类，绝不是金额）
_BOSS_KEY_EXCLUDE_SUFFIX = ("_months", "_days", "_count", "_ratio", "_rate", "_pct",
                            "_num", "_examples", "_detail", "_list", "_name",
                            "_status", "_type", "_note", "_ids")
# 顶层键黑名单（明显是背景总量/收款/已付/计数，不是敞口）
_BOSS_KEY_EXCLUDE_TOKEN = ("total", "合计", "总额", "收入", "成本", "revenue", "cost",
                           "payroll", "工资", "人数", "笔数", "次数", "ratio", "率",
                           "month", "day", "name", "examples", "状态", "类别",
                           "比例", "total_", "summary", "收款", "收金额",
                           "count", "_num", "月数", "月份")


def _is_expo_key(k):
    """是否为“敞口型金额”键。先排除计数/上下文，再判敞口前缀（避免贪婪误命中）。"""
    kl = k.lower()
    if any(kl.endswith(s) for s in _BOSS_KEY_EXCLUDE_SUFFIX):
        return False
    if any(t in kl for t in _BOSS_KEY_EXCLUDE_TOKEN):
        return False
    if any(h in kl for h in _BOSS_EXPO_PREFIX):
        return True
    if any(h in k for h in _BOSS_EXPO_CN):
        return True
    return False


def _is_context_key(k):
    """是否为明显背景量（总额/收入/成本/人数/计数），不作为敞口。"""
    kl = k.lower()
    # “matched”是已匹配背景量（unmatched 才是敞口，须排除前排除 matched 但保留 unmatched）
    if "matched" in kl and "unmatched" not in kl:
        return True
    if any(kl.endswith(s) for s in _BOSS_KEY_EXCLUDE_SUFFIX):
        return True
    if any(t in kl for t in _BOSS_KEY_EXCLUDE_TOKEN):
        return True
    return False

_LEVEL_RANK = {"极高风险": 5, "高风险": 4, "中风险": 3, "低风险": 0,
               "待核验": 1, "待核": 1, "信息": 1}


def _coerce_amount(v):
    """尽量把任意值转成 float 金额；失败返回 None。"""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.replace(",", "").replace("元", "").replace("￥", "").replace("¥", "").strip()
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _extract_finding_exposure(f):
    """尽力从 finding 提取一条“代表敞口金额”。

    数据现实：finding 没有标准化“补税额/敞口”字段，金额散落在 observed_metrics
    （顶层数值键）、evidence_rows、detail 文本。本函数按可信度降序取：
      ① observed_metrics 顶层“敞口型”键的最大值（_is_expo_key 判定）；
      ② 退而求其次取 observed_metrics 顶层非上下文数值键；
      ③ detail 文本里“差额/缺口/…”后的首个金额；
      ④ 都取不到 → 返回 None（前端标“未量化（待财务测算）”），绝不编造。
    """
    om = f.get("observed_metrics") or {}
    cands = []
    if isinstance(om, dict):
        for k, v in om.items():
            n = _coerce_amount(v)
            if n is not None and abs(n) > 0:
                cands.append((str(k), n))
    # ① 敞口型键优先
    expo = None
    for k, v in cands:
        if _is_expo_key(k):
            if expo is None or abs(v) > abs(expo[1]):
                expo = (k, v)
    if expo is not None:
        return {"amount": expo[1], "source": "observed_metrics", "key": expo[0],
                "confidence": "系统量化"}
    # ①b 列表型字段：字段名含暴露 token 且其元素为带 amount 的 dict → 汇总（如私户支付记录）
    om = f.get("observed_metrics") or {}
    if isinstance(om, dict):
        for lk, lv in om.items():
            if not isinstance(lv, list) or not any(t in lk.lower() for t in _BOSS_LIST_EXPO_TOKEN):
                continue
            s = 0.0
            for it in lv:
                if isinstance(it, dict):
                    a = _coerce_amount(it.get("amount"))
                    if a is not None and abs(a) > 0:
                        s += abs(a)
            if s > 0:
                return {"amount": s, "source": "observed_metrics(列表汇总)",
                        "key": lk, "confidence": "系统量化"}
    # ② 非上下文数值键（兜底，标“需财务确认”）
    fb = None
    for k, v in cands:
        if _is_context_key(k):
            continue
        if fb is None or abs(v) > abs(fb[1]):
            fb = (k, v)
    if fb is not None:
        return {"amount": fb[1], "source": "observed_metrics(上下文指标)", "key": fb[0],
                "confidence": "需财务确认"}
    # ③ detail 文本
    det = f.get("detail") or ""
    m = re.search(r"(差额|缺口|差异|未匹配|少缴|应补|补缴|风险金额|违规金额|未印证|未收|未付|敞口)"
                  r"[^0-9]{0,12}([0-9][0-9,]{2,}(?:\.[0-9]+)?)\s*元?", det)
    if m:
        n = _coerce_amount(m.group(2))
        if n is not None:
            return {"amount": n, "source": "detail文本", "key": m.group(1),
                    "confidence": "需财务确认"}
    return {"amount": None, "source": "未提取", "key": "", "confidence": "未量化"}


def _maturity_assessment(maturity):
    """把 evidence_maturity 映射为“概率评估”定性标签（不编造数值概率）。"""
    m = maturity or ""
    if "multi_source" in m:
        return "需评估（多源线索·待人工复核）"
    if "single_source" in m:
        return "需评估（单源·可初步确认）"
    if "unverified" in m:
        return "需评估（来源链路待验证·待核）"
    return "需评估（证据成熟度未标注）"


def _level_rank(level):
    return _LEVEL_RANK.get(level, 1)


def _raw_confirmed_findings(report_data):
    """与 _build_confirmed_problems 同口径取出“已查明风险事项”的原始 finding。"""
    _hv = (report_data.get("comprehensive", {}) or {}).get("hypothesis_verification", {}) or {}
    _unconfirmed_types = {d.get("finding_type") for d in (_hv.get("details") or [])
                          if d.get("unconfirmed")}
    out = []
    for f in (report_data.get("all_findings", []) or []):
        if not isinstance(f, dict):
            continue
        if f.get("level") in ("待核验", "信息", "低风险"):
            continue
        if f.get("_hypothesis_unconfirmed") is True or (f.get("type") in _unconfirmed_types):
            continue
        out.append(f)
    return out


def _problem_narrative_text(p):
    """拼接 problem 的全部叙述文本，用于金额抽取。"""
    parts = []
    for para in (p.get("narrative_paragraphs") or []):
        if isinstance(para, dict):
            parts.append(str(para.get("text") or ""))
            if para.get("bullets"):
                parts.append(" ".join(str(b) for b in para["bullets"]))
            if para.get("tail"):
                parts.append(str(para.get("tail") or ""))
    return "\n".join(parts)


def _extract_amount_from_text(text):
    """从叙述文本抽代表金额：仅在‘敞口型词’附近出现金额时才取（避免把收入/工资等背景总量当敞口）。

    防误绑：若金额前后 24 字内出现背景总量词（合同/收入/开票/申报/工资/成本/销售额），
    视为“基数”而非“敞口”，跳过（如“差额…看到发票总额11,747,476元”应驳回）。
    取不到 → 返回 None（上层标‘未量化（待财务测算）’），绝不把背景数字当敞口。
    """
    if not text:
        return None
    _BASE_TOTAL = ("合同", "收入", "开票", "发票", "申报", "工资", "成本", "销售额",
                   "营收", "采购", "结算金额")
    _pat = re.compile(r"(差额|缺口|差异|未匹配|少缴|应补|补缴|风险金额|违规金额|未印证|未收|未付|敞口|"
                      r"比例异常|超限额|超限|未申报|未计提|未转出|价税合计|合计金额|红冲|作废|冲销|"
                      r"回流|缺口金额|少缴税款|应补缴)"
                      r"[^0-9\-]{0,16}[-−]?([0-9][0-9,]{2,}(?:\.[0-9]+)?)\s*元?")
    for m in _pat.finditer(text):
        num = _coerce_amount(m.group(2))
        if num is None or num == 0:
            continue
        start = max(0, m.start(2) - 24)
        ctx = text[start:m.start(2)]
        if any(b in ctx for b in _BASE_TOTAL):
            continue
        return num
    return None




def _working_paper_item(f):
    """底稿版单条：保留全部原始证据、法规、计算过程与抽样说明。"""
    laws = f.get("_methodology_laws") or f.get("provenance") or []
    if isinstance(laws, dict):
        laws = list(laws.values())
    return {
        "type": f.get("type"),
        "category": f.get("category"),
        "level": f.get("level"),
        "conclusion_grade": f.get("conclusion_grade"),
        "terminal_state": f.get("terminal_state"),
        "evidence_tier": f.get("evidence_tier"),
        "evidence_maturity": f.get("evidence_maturity") or f.get("_evidence_maturity"),
        "redline_id": f.get("redline_id"),
        "detail": f.get("detail"),
        "observed_metrics": f.get("observed_metrics"),
        "evidence_rows": f.get("evidence_rows"),
        "self_proof_materials": f.get("self_proof_materials"),
        "resolve_steps": f.get("resolve_steps"),
        "laws": laws,
        "how_found": f.get("how_found"),
        "trace_id": (f.get("_evidence_ref") or {}).get("trace_id"),
    }


def _build_working_paper_report(report_data):
    """底稿版（检查组工作底稿）：全部 159 项发现的原始证据、法规、计算过程、抽样说明。

    与决策版（结论先行）、执行版（整改清单）分离，供检查组与企业财务逐笔核对，
    不与管理结论混排；不另行生成“定性结论”，只陈列可追溯的事实与依据。
    """
    findings = [f for f in (report_data.get("all_findings") or []) if isinstance(f, dict)]
    by_cat = {}
    for f in findings:
        cat = f.get("category") or "未分类"
        by_cat.setdefault(cat, []).append(f)
    cats = []
    for cat, items in by_cat.items():
        cats.append({
            "category": cat,
            "count": len(items),
            "items": [_working_paper_item(f) for f in items],
        })
    return {
        "variant": "底稿版（检查组工作底稿）",
        "note": ("本版含全部发现的原始证据、法规、计算过程与抽样说明，供检查组与企业财务逐笔核对；"
                 "不与决策版/执行版混排，不另行生成管理结论。"),
        "all_findings_count": len(findings),
        "by_category": cats,
        "inspection_questions_ref": "专项询问清单见执行版「风险检查询问清单」章节",
        "reconciliation_ref": "勾稽矩阵见执行版「勾稽矩阵」章节",
    }


def build_enterprise_readable_report(report_data, edition=None):
    """主入口：从分析结果组装 enterprise_readable_report。

    `edition`：报告编辑版（"税务稽查专家工作底稿版" 基线 / "金字塔原理编辑版" 派生）。
    两版**共享同一份内容基线**——本函数始终构建工作底稿版全部章节（内容逐字不变），
    并额外派生 `pyramid_edition`（只读结构化重组）附加于顶层；`report_edition`
    记录当前所选编辑版。无论选哪种 edition，工作底稿版内容均不被改写。
    """
    if not isinstance(report_data, dict):
        return {}
    if edition is None:
        from engine.audit_doctrine import DEFAULT_REPORT_EDITION
        edition = DEFAULT_REPORT_EDITION

    problems = _build_confirmed_problems(report_data)
    completed = _build_completed_checks(report_data)
    materials = _build_materials(report_data)
    procedures = _build_procedures(report_data)
    further = _build_further_checks(report_data)
    summary = _build_summary(report_data, problems, completed, further)
    plans = _build_action_plan(problems)
    discovery_overview = _build_discovery_overview(report_data, problems, completed, further)
    derivation_tree_report = _build_derivation_tree_report(report_data)
    analysis_coverage = _build_analysis_coverage(report_data)
    capability_boundary = _build_capability_boundary(report_data)
    cross_enterprise_report = _build_cross_enterprise_report(report_data)
    industry_benchmark_report = _build_industry_benchmark_report(report_data)
    related_party_report = _build_related_party_report(report_data)
    external_verify_report = _build_external_verify_report(report_data)
    bank_flow_report = _build_bank_flow_report(report_data)
    two_tax_report = _build_two_tax_report(report_data)
    revenue_authenticity_report = _build_revenue_authenticity_report(report_data)
    input_voucher_report = _build_input_voucher_report(report_data)
    false_invoice_report = _build_false_invoice_report(report_data)
    fund_loop_report = _build_fund_loop_report(report_data)
    inspection_questions_report = _build_inspection_questions_report(report_data)
    inspector_reasoning = build_inspector_reasoning(report_data)
    material_readiness = _build_material_readiness(report_data)
    # ★ 2026-09-25 宗旨三件套：已上传资料查了什么 / 每项风险怎么解除与自证 / 终局两态
    one_sided_digest = _build_one_sided_digest(report_data)
    resolution_ledger = _build_resolution_ledger(report_data)
    # ★ 2026-09-26 三版重构：底稿版（检查组工作底稿）
    working_paper_report = _build_working_paper_report(report_data)
    # ★ 2026-09-26 用户要求：「一、本轮检查总体结论」必须从 findings 实测派生（不得手写模板）。
    #   数字/点名清单/涉及税种/行业口径全部取实测，新增或减少发现无需改代码。
    from engine.overall_conclusion import build_overall_conclusion
    overall_conclusion = build_overall_conclusion(
        report_data, problems, further, inspector_reasoning)
    # ★ 2026-09-26 工作底稿版「检查情况总述」：基本情况 / 风险类型 / 风险程度 /
    #   对企业总体看法 / 监管态度（分级建议）/ 边界声明
    from engine.inspection_overview import build_inspection_overview
    inspection_overview = build_inspection_overview(
        report_data, problems, further, overall_conclusion)
    # ★ 2026-09-27：主营业务成本「两口径勾稽明细」（发票类目构成 / 账面构成 / 差异归因），
    #   无论是否超阈值都产出（合规留痕）。发票构成取自 pipeline 已算好的 core_cost 拆分（单一权威），
    #   本模块不重跑 classify，避免口径分叉。
    from engine.cost_recon_detail import build_cost_recon_detail
    cost_recon_detail = build_cost_recon_detail(report_data)
    # ★ 2026-09-27（P1）：本轮潜在税额敞口汇总（分税种 + 已量化/未量化覆盖度）
    try:
        from engine.tax_impact import build_tax_impact_summary as _btis
        _tax_impact_summary = _btis(problems)
    except Exception:
        _tax_impact_summary = {}
    # ★ 2026-09-27（P2）：具体问题章首的**主线研判**（最可能的 2–3 个方向）
    main_assessment = _build_main_assessment(problems)

    # 专项报告的 metrics 指标键统一中文化（独立于 observed_metrics 的另一处英文键来源）
    # ★ 2026-09-25：**递归**汉化所有 `metrics` 字典的键 —— 旧写法只处理**顶层** `metrics`，
    #   于是 `revenue_authenticity_report.dimensions.ar_aging.metrics` 里的
    #   `ar_customers / ar_unreceived_total / ar_long_aging_count / ar_max_aging_days /
    #   ar_from_trial_balance` 等 5 个英文键原样留在企业报告里（实测）。
    #   前端 `_renderCapMetrics` 会**直接把键名打印**给用户，一旦某条渲染/导出路径触到
    #   这些嵌套 metrics，用户就会看到英文键名。
    for _sec in (two_tax_report, input_voucher_report, false_invoice_report,
                 fund_loop_report, external_verify_report, bank_flow_report,
                 cross_enterprise_report, derivation_tree_report, revenue_authenticity_report,
                 industry_benchmark_report, related_party_report, inspection_questions_report):
        _translate_all_metric_dicts(_sec)

    # ★ 2026-09-26 金字塔原理编辑版：对工作底稿版的只读结构化重组（不改写任何内容）。
    #   始终派生并附加，使前端可在两种编辑版间纯客户端切换，无需重算。
    _identity = _identity_from_report_data(report_data)
    pyramid_edition = build_pyramid_edition({
        "confirmed_problems": problems,
        "summary": summary,
        "identity": _identity,
        "resolution_ledger": resolution_ledger,
    })

    out = _zh_normalize_obj({
        "compilation_style": "涉税风险检查工作报告（风险检查文书式）",
        "generated_date": datetime.now().strftime("%Y年%m月%d日 %H时%M分"),
        # ★ 2026-09-26 报告编辑版：基线=税务稽查专家工作底稿版；派生=金字塔原理编辑版。
        #   二者共用下方同一内容基线；pyramid_edition 为只读派生视图。
        "report_edition": edition,
        "identity": _identity_from_report_data(report_data),
        "inspector_perspective": _build_inspector_perspective(),
        "inspector_reasoning": inspector_reasoning,
        "material_readiness": material_readiness,
        # ★ 已上传资料各自"单独可查"的项目：直接回答"我给了这些，你查了哪些"（宗旨 D1）
        "one_sided_digest": one_sided_digest,
        # ★ 逐项风险的解除方式与自证清单 + 终局两态（宗旨 D3/D4）
        "resolution_ledger": resolution_ledger,
        # 红线判定汇总：本轮触碰多少条税务红线、各结论层级数量（报告抬头展示）
        "redline_summary": ((report_data.get("comprehensive", {}) or {}).get("redline_detection") or {}).get("summary", {}),
        "summary": summary,
        # ★ 2026-09-26：第一章「本轮检查总体结论」——从 findings 实测派生（唯一权威）
        "overall_conclusion": overall_conclusion,
        # ★ 2026-09-26：工作底稿版「检查情况总述」（风险类型 / 风险程度 / 总体看法 / 监管态度）
        "inspection_overview": inspection_overview,
        # ★ 2026-09-27：主营业务成本「两口径勾稽明细」（阈值内也照出，合规留痕）
        "cost_recon_detail": cost_recon_detail,
        # ★ 2026-09-27（P1）：本轮潜在税额敞口汇总（分税种 + 已量化/未量化覆盖度）
        "tax_impact_summary": _tax_impact_summary,
        # ★ 2026-09-27（P2）：具体问题章首主线研判
        "main_assessment": main_assessment,
        "discovery_overview": discovery_overview,
        "inspection_procedures": procedures,
        "materials": materials,
        "confirmed_problems": problems,
        "completed_checks": completed,
        "derivation_tree_report": derivation_tree_report,
        "analysis_coverage": analysis_coverage,
        "cross_enterprise_report": cross_enterprise_report,
        "industry_benchmark_report": industry_benchmark_report,
        "related_party_report": related_party_report,
        "external_verify_report": external_verify_report,
        "bank_flow_report": bank_flow_report,
        "two_tax_report": two_tax_report,
        "revenue_authenticity_report": revenue_authenticity_report,
        "input_voucher_report": input_voucher_report,
        "false_invoice_report": false_invoice_report,
        "fund_loop_report": fund_loop_report,
        "inspection_questions_report": inspection_questions_report,
        "capability_boundary": capability_boundary,
        "action_plan": plans,
        "further_checks": further,
        # ★ 2026-09-26 三版重构：底稿版（检查组工作底稿，全部原始证据）
        "working_paper_report": working_paper_report,
        "recheck": {
            "trigger": "企业完成真实整改或补充资料后，重新点击一键分析。",
            "work": "下一轮将重新读取全部资料，复查本轮问题，检查补充资料带出的关联事项，并比较前后两轮变化。",
            "convergence": "问题逐项处理、资料逐步完整、账务与申报能够相互核对，才表示企业正在趋于合规；不能以问题数量为零或分数下降单独判断。",
        },
        "report_statement": [
            "本报告只对本轮已上传且能够读取的资料负责，未上传资料不在本轮具体问题认定范围内。",
            "本报告所列“具体问题”均有本轮资料中的直接数据或可回查证据支持；资料不足的事项已单独列入补充资料后再检查清单。",
            "本报告采用税务风险检查文书式结构和风险检查人员陈述口径编制，所列检查事实、处理意见和复查要求用于企业合规整改。",
            "企业应依据真实业务和原始资料办理整改，不得倒签、补造、篡改、删除或隐匿资料。",
            "系统能力存在边界：账外经营、私户收款、主观故意定性等须依赖外部数据源与人工下户取证，详见「能力边界与彻底风险检查路线」章节。",
        ],
    })
    # ★ 2026-09-26 金字塔原理编辑版 = 纯派生结构性视图，**刻意不经过** _zh_normalize_obj：
    #   否则 _naturalize_report_text 会把行动标题的「【等级】」标记改写为「等级：」，
    #   既破坏前端可读性，又使 pyramid_preserves_content 闸门（按【等级】格式自校验）失效、
    #   并损害「工作底稿版 + pyramid_edition 可无损还原」的可逆性。
    out["pyramid_edition"] = pyramid_edition
    return out
