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

# ★★ 税费性质权威（2026-10-06，用户评语 #4「税费法律适用混同」）：
#   社保费/住房公积金/文化事业建设费 **不是税** —— 各自的法律依据与追责主体不同，
#   不能一律套用《税收征收管理法》第六十三条偷税条款。唯一权威 `engine.levy_nature`。
#   在模块顶部导入（而非使用点内联 try/except），避免 except 分支把权威置 None 后被调用。
from engine.levy_nature import natures_of as _levy_natures_of
from engine.levy_nature import consequence_text as _levy_consequence
from engine.levy_nature import item_consequence_text as _levy_item_consequence
from engine.levy_nature import consequence_declarations as _levy_declarations
from engine.levy_nature import CONSEQUENCE_DECL_NAME as _LEVY_DECL_NAME

# ★★ 结论用语唯一权威（2026-10-08，P0-2 用语权威收口）：
#   报告结论只能使用 `config/conclusion_grades.json::term_authority` 的四个术语
#   （风险信号 / 待核事项 / 已认定事实 / 违法认定）。历史上本模块有 3 处**硬编码**
#   「本项已查明的风险…」—— 含定性词"已查明"，而 L2 禁止定性词、且缺 L2 必需文本，
#   导致质量门禁 A3/B5 同一病根各报一次。现统一由 `pending_clue_phrase` 生成。
from engine.conclusion_grade import pending_clue_phrase as _pending_clue_phrase

# ★★ 结论等级 → 风险等级上限的唯一权威（2026-10-09，P0-5）：
#   L1/L2 是"线索级"结论，`allow_risk_level` 只允许 信息/待核验/低风险 ——
#   报告层不得再各自判"是否超限"。收敛为 `cap_level_for_grade` / `effective_grade_id`。
from engine.conclusion_grade import cap_level_for_grade as _cg_cap_level
from engine.conclusion_grade import effective_grade_id as _cg_grade_id
from engine.conclusion_grade import map_verdict as _cg_map_verdict

# ★★ 报告级通用口径句唯一权威（2026-10-08，P0-7 同源）：
#   「证据边界声明」此前在**两个分支各写一套**（专项比对项 / 另行检出的域分析项），
#   属"同一概念两处维护"。它本就是报告级口径 ⇒ 只在 `report_wording` 定义一次，
#   本模块四处（含 `_TEMPLATE_PREFIXES` 差异化锚点）一律转手本别名，禁再手写字面量。
from engine.report_wording import EVIDENCE_BOUNDARY_CLAUSE as _EVIDENCE_BOUNDARY

# ★★ 风险等级唯一权威（2026-10-06，用户评语 #1「风险等级前后矛盾」）：
#   等级词表 / 轻重标度 / 呈现顺序 / 上限压制 全部转发 `engine.risk_levels`，
#   本模块不再自建第二张等级表（多头维护＝同一事项在不同章节等级不一致）。
from engine.risk_levels import cap_level as _cap_level
from engine.risk_levels import normalize as _normalize_level
from engine.risk_levels import present_order as _level_present_order
from engine.risk_levels import severity as _level_severity
from engine.risk_levels import LEGAL_LEVELS as _LEGAL_RISK_LEVELS_AUTH
from engine.risk_levels import PRESENT_ORDER as _RISK_PRESENT_ORDER_AUTH
from engine.risk_levels import display_label as _display_label

# ★ 2026-10-07：行业基准口径声明与指标汉化一律引用唯一权威（本处只做薄转发，不自带字面声明）。
#   事故：本文件曾引用未定义的 `_BENCH_CAUTION`（NameError ⇒ 行业对标章节整段不产出），
#   且 `_build_industry_benchmark_report` 自带一份指标中文名手工表，与 industry_benchmark 两处维护。
from engine.industry_benchmark import BENCHMARK_CAUTION as _BENCH_CAUTION
from engine.industry_benchmark import indicator_label as _bench_indicator_label


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
    (r"(?<![A-Za-z_])detect(?![A-Za-z_])", "检测"),
    (r"(?<![A-Za-z_])verify(?![A-Za-z_])", "核验"),
    (r"(?<![A-Za-z_])diagnose(?![A-Za-z_])", "诊断"),
    (r"(?<![A-Za-z_])rectify(?![A-Za-z_])", "整改"),
    (r"(?<![A-Za-z_])report(?![A-Za-z_])", "报告"),
    (r"(?<![A-Za-z_])[Vv][Ss](?![A-Za-z_])", "与"),   # vs / VS（中文或空格环绕均适用）
    (r"(?<![A-Za-z_])BOM(?![A-Za-z_])", "物料清单"),
    (r"(?<![A-Za-z_])ETS(?![A-Za-z_])", "电子税务局"),
    # 文件扩展名（文件类型描述里出现的 .xlsx/.xls/.pdf 等）
    (r"(?<![A-Za-z_])xlsx(?![A-Za-z_])", "Excel"),
    (r"(?<![A-Za-z_])xls(?![A-Za-z_])", "Excel"),
    (r"(?<![A-Za-z_])pdf(?![A-Za-z_])", "PDF"),
    (r"(?<![A-Za-z_])docx(?![A-Za-z_])", "Word"),
    (r"(?<![A-Za-z_])doc(?![A-Za-z_])", "Word"),
    (r"(?<![A-Za-z_])csv(?![A-Za-z_])", "CSV"),
    (r"(?<![A-Za-z_])txt(?![A-Za-z_])", "文本"),
    # 布尔值字符串化残留
    (r"(?<![A-Za-z_])False(?![A-Za-z_])", "否"),
    (r"(?<![A-Za-z_])True(?![A-Za-z_])", "是"),
    # 常见计量单位
    (r"(?<![A-Za-z_])kg(?![A-Za-z_])", "千克"),
    (r"(?<![A-Za-z_])mm(?![A-Za-z_])", "毫米"),
    (r"(?<![A-Za-z_])cm(?![A-Za-z_])", "厘米"),
    # 技术/法律术语残留
    (r"arm's length", "独立交易原则"),
    (r"(?<![A-Za-z_])token(?![A-Za-z_])", "令牌"),
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


# ★ 2026-09-29（点评整改 P0-9d）：**计数器/状态类内部键**的保留后缀。
#   引擎为让计数键落入 `_BOSS_KEY_EXCLUDE_TOKEN`（不被当作金额）而用 `_笔数`/`_张数`
#   后缀，但这类键是**纯中文+下划线**，`_translate_key` 原样返回 → 报告出现
#   「红字发票_笔数=13」这种变量名。通用规则：保留后缀前的中文按下划线连接的部分
#   一律去分隔符（新增同类计数器键**无需改代码**，只需沿用后缀）。
_COUNTER_SUFFIXES = ("_笔数", "_张数", "_项数", "_人次", "_人月", "_笔", "_项")

# ★ 2026-09-29：状态/等级类内部码（值即枚举名）也要写成中文可读形式。
_ENUM_CODE_CN = {
    "已核定_限于所报资料勾稽": "已核定（限于所报资料勾稽）",
    "草稿_待人工复核": "草稿（待人工复核）",
    # ★ 2026-10-06：**枚举值**同样不得以英文码入文。
    #   实测 `经营模式=b2b_or_unknown` 直接出现在报告「二、发现的依据」里
    #   （键已汉化、值漏了）—— 键与值都必须过汉化权威。
    "b2b_or_unknown": "面向企业为主或未标注",
    "b2b": "面向企业",
    "b2c": "面向个人消费者",
    "mixed": "兼有企业与个人客户",
    "unknown": "未标注",
}


_METRIC_CN = {
    # ★★ 2026-10-06（用户第 2 批 AC7）：**引擎数据源键名不得进正文**。
    #   实测报告正文出现「本项依据的独立数据源：sal_invs、pur_invs」「结论适用范围：
    #   screening_and_review_only」——这些是 pipeline/analysis_coverage 的**内部键与枚举**
    #   （`analysis_coverage` 里已有中文映射，但报告侧这份表没登记 ⇒ 词元分译也拼不出来）。
    #   判据：凡可能进正文的引擎键/枚举值，**必须在本表登记**（一处维护）。
    "sal_invs": "销项发票", "pur_invs": "进项发票", "tax_declarations": "纳税申报表",
    "screening_and_review_only": "仅用于筛查与复核（不作定性）",
    "material": "原料", "issue": "问题", "theoretical": "理论耗用", "actual": "实际耗用",
    "deviation_ratio": "偏差率", "finished_products": "对应成品",
    "processing_count": "加工费笔数", "total_amount": "加工费合计", "cross_region_count": "跨地区笔数",
    "contract_area": "合同面积(㎡)", "required_area": "库存所需面积(㎡)",
    "end_inventory_value": "期末存货货值", "end_inventory_qty": "期末存货数量",
    "goods_value": "购销货值", "actual_transport": "账面运输费", "contract_freight": "合同运费",
    "cities": "涉及城市", "freight_bearer": "运费承担方",
    "duplicate_invoice_count": "重复发票号数", "salary_only_count": "仅工资册人数",
    # ★ 2026-10-04（用户复核疑点6 D7 病句）：此前只登记了 `*_only_count`，而
    #   `salary_person_count`/`social_person_count` 未登记 ⇒ 落到单词分译（salary 工资 +
    #   person 个人 + count 数）⇒ 报告出现 **「工资个人数=6；社保个人数=5」** 病句。
    #   通用规则：**凡进入正文的计数键必须在本表登记**（否则词元拼接会造词）。
    "salary_person_count": "工资表人数", "social_person_count": "社保参保人数",
    "uninsured_person_count": "未参保人数", "hf_person_count": "公积金缴存人数",
    "unfunded_person_count": "未缴存公积金人数", "person_month_count": "人月配对数",
    "low_base_person_count": "低基数参保人数", "mismatch_person_count": "双向未匹配人数",
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
    # VR036 通道3：货物用于对外投资/分配给股东（RL-VAT-012 净增量）
    "invest_distribute_count": "对外投资/分配笔数",
    "invest_distribute_total": "对外投资/分配存货成本合计",
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
    # VR059 现金交易监管盲区（★ 2026-10-08 冗余收敛后暴露：VR059 在暖态运行下稳定触发，
    #   此前这 4 个键未登记 ⇒ 词元分译会拼出「现金 凭证 行数」病句。凡进正文的键必须登记。）
    "cash_voucher_rows": "现金收款笔数", "cash_voucher_amount": "现金收款金额",
    "cash_ledger_provided": "是否已提供现金日记账", "cash_intensive_blindspot": "是否现金密集型盲区",
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
    # ★ 2026-09-29（点评整改 P0-9d）：实测漏进企业报告的英文键（键=值 形态）逐条汉化。
    #   这些键来自 clue_chain 的 observed/samples 渲染，此前 `_METRIC_CN` 与 `_WORD_CN`
    #   都查不到，`_translate_key` 按设计"宁可露英文也不假汉化"返回原键 → 报告出现
    #   「core_cost_total=1,882,804.87；company_paid_amount=53,859.91」。
    "core_cost_total": "主营业务成本类发票合计",
    "company_paid_amount": "公户已付款金额",
    "person_paid_amount": "个人账户已付款金额",
    "book_payroll_total": "账面应付职工薪酬合计",
    "public_account_payroll": "公户代发工资金额",
    "private_paid_records": "个人账户付款记录",
    "avg_amount_per_individual_customer": "个人客户人均开票金额",
    "uninsured_person_count": "未参保人数",
    "uninsured_person_month_count": "未参保人月数",
    "company_id": "企业编号",
    # ★ 2026-10-06（闸门 ERROR：报告正文出现 `declared_input_tax_total=192463.32`）：
    #   这两键此前**未登记** ⇒ `_translate_key` 译不出 ⇒ 原样漏进报告正文。
    #   按"同类对象只需加一行数据、不改逻辑分支"的口径补登记。
    "avg_amount_per_individual_supplier": "个人或个体户供应商户均金额",
    "business_model": "经营模式",
    # ★ 2026-10-06（同批普查：**22 个键/枚举在真实产物里译不出**，逐个补登记 —— 只加数据行）：
    #   判定见 `tools/audit_consistency.py::check_metric_key_localized` 与
    #   `scripts/_audit_unlocalized_metrics.py`（对全量产物普查，非针对某一家企业）。
    "purchase_total": "采购合计",
    "bank_in_total": "银行进账合计",
    "book_cost_total": "账面主营业务成本合计",
    "book_cost_source": "账面成本取数口径",
    "amount_mismatch_amount": "金额不一致合计",
    "analysis_base_date": "分析基准日",
    "ap_detail_provided": "已提供应付账款明细",
    "ap_from_trial_balance": "应付账款取自余额表",
    "ap_summary_balance": "应付账款汇总余额",
    "beyond_data_amount": "超出资料范围金额",
    "beyond_data_examples": "超出资料范围举例",
    "beyond_data_rows": "超出资料范围笔数",
    "cost_basis_gap": "成本支撑缺口",
    "cost_basis_gap_ratio": "成本支撑缺口占比",
    "covered_by_other_channel_amount": "已由其他渠道覆盖金额",
    "evidence_ratio": "证据覆盖比例",
    "individual_supplier_share": "个人或个体户供应商占比",
    "out_of_window_amount": "超属期金额",
    "person_paid_examples": "涉个人付款举例",
    "person_paid_ratio": "涉个人付款占比",
    "uncovered_amount": "未覆盖金额",
    "unexplained_gap": "未解释差额",
    "unfunded_person_month_count": "未缴存人月数",
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

    ★ 2026-09-29（点评整改 P0-9d，多头维护收敛）：本函数是**键汉化的唯一权威**，
      查表顺序 = `_ENUM_CODE_CN`（状态码，值即枚举名）→ `_METRIC_CN`（指标）
      → `_EV_COLUMN_CN`（逐笔证据列名）→ `_WORD_CN`（单词分译）。
      此前 `_EV_COLUMN_CN` 是**只在 evidence 明细表内部生效的独立孤岛**，
      同一键（如 `ref_label`）在明细表里译得出、在 clue_chain 的
      observed/samples 里却原样漏英文（实测 `ref_label=发票号…`）——
      正是本项目"一个概念多份实现"的老病。现二者共用同一查表链。
      另：**纯中文+保留后缀**的内部计数键（`红字发票_笔数`）与状态码，
      在此统一去分隔符/加括号，避免变量名入文。
    """
    s = str(key)
    if not s:
        return s
    if s in _ENUM_CODE_CN:
        return _ENUM_CODE_CN[s]
    if s in _METRIC_CN:
        return _METRIC_CN[s]
    # 纯中文（无 ASCII 字母）→ 处理内部保留后缀 / 下划线连写，再原样返回
    if not re.search(r"[A-Za-z]", s):
        for suf in _COUNTER_SUFFIXES:
            if s.endswith(suf) and len(s) > len(suf):
                return s[:-len(suf)].replace("_", "") + suf.lstrip("_")
        return s
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
            result = re.sub(r"(?<![A-Za-z_])%s(?![A-Za-z_])" % re.escape(en), zh, result)
    # 三次兜底：中英连写键（如 direct回流金额）——已知词元紧邻中文时也替换。
    if re.search(r"[A-Za-z]{3,}", result):
        for en, zh in sorted(_WORD_CN.items(), key=lambda x: -len(x[0])):
            if len(en) >= 3:
                result = result.replace(en, zh)
    # 终检：仍有**任何**未知英文 → 返回**原键**（不静默剔除，避免语义反转）
    # ⚠ 用 `[A-Za-z]` 而非 `{3,}`：1~2 字母的残留（如 `ar_un已接收_合计_x` 里的 `un`）
    #   同样是"半翻译"，同样可能已丢词元。
    if re.search(r"[A-Za-z]", result):
        # ★ 2026-09-29：词表全无解 → 退到「逐笔证据列名表」（`ref_label` 等），
        #   它此前只在 evidence 明细表内部生效，是同一概念的第二份实现。
        if s in _EV_COLUMN_CN:
            return _EV_COLUMN_CN[s]
        return s
    return result


def _metric_kv_text(met, limit: int = 8) -> str:
    """把 `observed_metrics` 压成一句可直读的「汉化键=值；…」（**唯一实现**）。

    ★★ 2026-10-06（闸门 ERROR：报告正文出现 `declared_input_tax_total=192463.32`）：
      此前**两处**各自 `"%s=%s" % (k, v)` 直接拼**引擎原始键名**
      （`_promote_standalone_reports` 一处、`_merge_ledger_into_problems` 一处）——
      同一缺陷两份实现（本项目"一个概念多份实现"的老病），现收敛为这一个函数。
    三条硬判据：
      ① 只取**标量**（int/float/str/bool）—— list/dict 的 repr 会把 `{'k': v}` 拼进正文；
      ② **键与值都要过汉化唯一权威** `_translate_key`：
         · 键汉化后仍含 ASCII ⇒ 整对不写；
         · 值若是**枚举码**（纯小写/下划线）⇒ 必须译出；译不出 ⇒ 整对不写；
         · 布尔值写成「是/否」（`True/False` 也是英文）；
      ③ 取不到中文名就**不展示**（**绝不用英文顶替**；数字在正文大白话里已写明，不丢信息）。
    """
    if not isinstance(met, dict) or not met:
        return ""
    parts = []
    for k, v in list(met.items())[:limit]:
        if not isinstance(v, (int, float, str, bool)):
            continue
        zh = _translate_key(k)
        if not zh or re.search(r"[A-Za-z]", str(zh)):
            continue                      # 键未汉化 ⇒ 宁可不写，也不让英文变量名入文
        if isinstance(v, bool):
            val = "是" if v else "否"
        elif isinstance(v, str) and re.match(r"^[a-z][a-z0-9_]*$", v):
            # ★ 枚举码（b2b_or_unknown…）同样是英文 ⇒ 必须译出，译不出就不写这一对
            _vz = _translate_key(v)
            if re.search(r"[A-Za-z]", str(_vz)):
                continue
            val = _vz
        else:
            val = v
        parts.append("%s=%s" % (zh, val))
    return "；".join(parts)


def _build_detail_table(f):
    """从 finding 的 observed_metrics / examples / 明细 生成可回查的代表性明细表。

    返回 (rows, columns)：rows 为 dict 列表，columns 为列中文名列表；无可用明细时返回 ([], [])。
    明细是让报告『详尽』的关键：把后台已经算出的逐笔差异落到正文，而不是只在 Detail 里写汇总数。
    """
    metrics = f.get("observed_metrics") or {}
    # ★ 2026-09-29（点评整改 P1-14）：源明细**总数**。凡列示行数少于总数，
    #   报告必须注明"仅列示前 N 笔"——否则读者会把列示的行当成全部的行，
    #   从而与合计对不上（外部点评：「7 笔合计 1,320,000 只列 5 笔 800,000 未注明」）。
    _rows_total = 0
    if not isinstance(metrics, dict):
        metrics = {}
    # 兼容直接挂在 finding 上的 examples 列表
    examples = f.get("examples") or metrics.get("examples") or []
    rows, columns = [], []
    # 1) 通用 examples 列表（每项是一行 dict）
    if isinstance(examples, list) and examples and isinstance(examples[0], dict):
        columns = list(examples[0].keys())
        rows = [dict(x) for x in examples[:30]]
        if len(examples) > 30:
            _rows_total = len(examples)
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
            if len(metrics[key]) > 30:
                _rows_total = len(metrics[key])
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
                    if len(v) > 30:
                        _rows_total = len(v)
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
                if len(v) > 30:
                    _rows_total = len(v)
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
                        if len(v) > 30:
                            _rows_total = len(v)
                        return rows, [col], _rows_total
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
            return tbl["rows"], tbl["columns"], len(ev)
    if not rows:
        return [], [], 0
    # 统一汉化列名与行键：保证 columns 与 rows 键一致（前端按 columns 取值）。
    # 精确映射优先，词表兜底，杜绝英文键名漏网。
    columns = [_translate_key(c) for c in columns]
    rows = [{_translate_key(k): v for k, v in row.items()} for row in rows]
    # ★ 2026-09-29（P1-14）：把源明细总数透传给渲染层（>列示行数时须注明"仅列示前 N 笔"）
    return rows, columns, _rows_total


# ── evidence_rows → 明细表（2026-09-26 根因修复）────────────────────────
# 根因：引擎产出的「逐笔证据」统一挂在 finding.evidence_rows（本轮 167 条发现中 138 条带此字段），
# 但企业报告此前只渲染 finding.detail_tables（按 redline_id 关联），而 detail_tables 全库仅 1 条发现带。
# 结果：138 条发现的逐笔明细被静默吞掉（如红冲/作废发票 13 张逐笔清单不显示）。
# 此处把 evidence_rows 也当作明细表来源：凡带 evidence_rows 的发现（能关联到红线疑点）都会在企业报告
# 「发现的依据」段列出逐笔明细。这是通用规则，新增任何带 evidence_rows 的发现都无需改报告渲染代码。
_EV_COLUMN_CN = {
    # ★ 2026-09-29（P1-14）：`ref_label` 实测承载的是**单据标签/摘要**（如"收到款项"），
    #   旧标签「发票/凭证号」会把它当成凭证号 → 读者看到"凭证号"栏里是摘要，与合计对不上。
    #   改名为「凭证/单据标识」；真正的凭证号来自 `ref_id`（见下）。
    "ref_label": "凭证/单据标识", "ref_id": "凭证号",
    "invoice_no": "发票号", "inv_no": "发票号",
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
    """中文相邻 2-gram —— 唯一权威 `engine/findingkit.py:cjk_bigrams`（本名转调）。

    ★ 2026-10-01 收敛：此前本模块与 `pipeline` 各写一份字面实现，`audit_consistency`
      的跨模块分歧检查立刻报「真实分歧（非转发桩）」。现统一落 findingkit。
    """
    from engine.findingkit import cjk_bigrams as _fk
    return _fk(text)


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


# ── 分项扣除限额测算表（2026-10-01 事故修复）────────────────────────────
# 事故：RL-CIT-007 静态 clue_chain 只填了业务招待费（超限 377,927.53），而广告费和业务
#   宣传费（超限 1,734,210.17，是前者的 4.6 倍）已由 VR039 算出却没进该疑点**任何表**。
#   根因：扣除限额是多分项红线，报告只渲染"算出数的那一项"的片段。
# 口径（通用规则，新增同类只在本表加一行，不改逻辑分支）：
#   · 红线要出本表，须在此登记它含哪些分项及各自指标键；未登记的红线**不出表**（不给所有红线硬套）；
#   · 本轮没算出数的分项**整行不出**——缺失 ≠ 0，不得用默认值顶替；
#   · 每分项的三个数必须取自**本分项自己的** observed_metrics（串项回归已锁，见测试）。
_LIMIT_ITEMS: Dict[str, List[Dict[str, str]]] = {
    "RL-CIT-007": [
        # ★★ 2026-10-04（用户复核疑点5）：
        #   ① 补齐要件① 声称的**全部 6 类**分项（原先只登记 3 类 ⇒ 要件说 6 类、表只出 2 行，
        #      覆盖率 1/3 且读者无从知道"其余 4 类是没超限、还是没数据"）；
        #   ② 每项补 **适用规则**（法定公式，D4：读者要能复核限额数字怎么来的）与
        #      **差异性质**（D13：区分永久性/时间性差异 —— 混为一谈会让企业把可结转部分当永久不可扣而**多缴税**）。
        #   ⇒ 纯数据表扩充，新增同类只加一行。
        {"费用项目": "业务招待费", "账面发生额": "entertainment_total",
         "扣除限额": "deduct_cap", "超限金额": "over_limit",
         "适用规则": "发生额×60% 与 当年销售（营业）收入×5‰ **孰低**（《企业所得税法实施条例》第43条）",
         "差异性质": "**永久性差异**（不得结转以后年度扣除）"},
        {"费用项目": "广告费和业务宣传费", "账面发生额": "ad_promo_total",
         "扣除限额": "deduct_cap", "超限金额": "over_limit",
         "适用规则": "不超过当年销售（营业）收入15%（《企业所得税法实施条例》第44条）",
         "差异性质": "**时间性差异：超过部分准予结转以后纳税年度扣除**（第44条）"},
        {"费用项目": "职工福利费", "账面发生额": "welfare_total",
         "扣除限额": "deduct_cap", "超限金额": "over_limit",
         "适用规则": "不超过工资薪金总额14%（《企业所得税法实施条例》第40条）",
         "差异性质": "**永久性差异**（不得结转以后年度扣除）"},
        {"费用项目": "工会经费", "账面发生额": "union_total",
         "扣除限额": "deduct_cap", "超限金额": "over_limit",
         "适用规则": "不超过工资薪金总额2%（《企业所得税法实施条例》第41条）",
         "差异性质": "**永久性差异**（不得结转以后年度扣除）"},
        {"费用项目": "职工教育经费", "账面发生额": "edu_total",
         "扣除限额": "deduct_cap", "超限金额": "over_limit",
         "适用规则": "不超过工资薪金总额8%（《企业所得税法实施条例》第42条）",
         "差异性质": "**时间性差异：超过部分准予结转以后纳税年度扣除**（第42条）"},
        {"费用项目": "公益性捐赠", "账面发生额": "donation_total",
         "扣除限额": "deduct_cap", "超限金额": "over_limit",
         "适用规则": "不超过年度利润总额12%（《企业所得税法》第9条、实施条例第53条）",
         "差异性质": "**时间性差异：准予结转以后三年内在计算应纳税所得额时扣除**"},
    ],
}
_LIMIT_COLUMNS = ["序号", "费用项目", "账面发生额（元）", "扣除限额（元）", "超限金额（元）",
                  "差异性质", "适用规则"]

# ★★★ 2026-10-04（用户复核疑点5 D2）：**红线要件里混进的"另一类风险"要件** —— 数据表（新增同类只加一行）。
#   事故：RL-CIT-007 的第③条要件是「**关联方债权性投资与权益性投资比例超过2:1**且超标准利息未调整」，
#   这是**资本弱化**（财税〔2008〕121号）问题，与本项"费用扣除限额超限"**主题不同**；
#   报告却把它平铺在要件表里，读者会以为本企业同时存在"关联方债资比超标"问题。
#   处置：报告在该要件后**显式声明"与本项主题不同、不在本项核查范围"**（不隐藏、不改事实）。
_REDLINE_OFFTOPIC_CONSTITUENTS: Dict[str, Dict[int, str]] = {
    "RL-CIT-007": {
        3: "属【资本弱化】风险（关联方债资比超标，财税〔2008〕121号），与本项「费用扣除限额」主题不同，"
           "不在本项核查范围",
    },
}


def _limit_items_table(rid, findings):
    """分项扣除限额测算表：把红线登记的各分项目（发生额/扣除限额/超限）一次摆全。

    返回 {columns, rows} 或 None（红线未登记 / 本轮一个分项都没算出数）。
    """
    _rid = str(rid or "").strip()
    items = _LIMIT_ITEMS.get(_rid)
    if not items:
        return None

    # 收集该红线下所有带 observed_metrics 的发现（**每项各由一条发现算出**，
    # 如 RL-CIT-007 下招待费来自 VR038、广宣费来自 VR039、福利费来自 VR040）。
    _mts = []
    for _f in (findings or []):
        if isinstance(_f, dict) and str(_f.get("redline_id") or "").strip() == _rid:
            _m = _f.get("observed_metrics")
            if isinstance(_m, dict) and _m:
                _mts.append(_m)
    if not _mts:
        return None

    rows = []
    for _i, _it in enumerate(items, 1):
        _cells = {"序号": _i, "费用项目": _it["费用项目"]}
        # ★ **本分项自己的三个键必须齐全**才出这一行。三者共用 `deduct_cap` 键名
        #   （限额公式同类），早期实现"凑齐一个就出"会把业务招待费的 33,184.00
        #   配给广宣费（串项回归，测试已锁）。
        # 本分项的三个键必须在**同一条发现**里取齐（先按"本分项独有的发生额键"定位该分项的那条发现）
        _src = next((m for m in _mts if m.get(_it["账面发生额"]) not in (None, "")), None)
        _complete = True
        for _col, _key in (("账面发生额（元）", _it["账面发生额"]),
                           ("扣除限额（元）", _it["扣除限额"]),
                           ("超限金额（元）", _it["超限金额"])):
            _v = (_src or {}).get(_key)
            if _v is None or _v == "":
                _complete = False      # 缺失≠0：整行不出，绝不用 0 或别的分项的数顶替
                break
            try:
                _cells[_col] = format(float(_v), ",.2f")
            except (TypeError, ValueError):
                _cells[_col] = str(_v)
        if _complete:
            # ★ 2026-10-04（D4/D13）：把**法定公式**与**差异性质**一并写出（数据取自本项登记，不另写逻辑）
            _cells["差异性质"] = str(_it.get("差异性质") or "")
            _cells["适用规则"] = str(_it.get("适用规则") or "")
            rows.append(_cells)
    if not rows:
        return None
    # ★★ 2026-10-04（用户复核疑点5 D5）：**覆盖范围必须自证** ——
    #   要件① 声称"业务招待费、广宣费、职工福利费、工会经费、职工教育经费、公益性捐赠等"（6 类），
    #   而表里只出了 2 行（其余 4 类**未取得工资薪金总额/利润总额等计算底稿，未测算**）。
    #   旧实现对此**一字不提** ⇒ 读者会以为"只有这两项超限"。
    #   判据（数据驱动）：登记项 − 实际出行项 = 未测算项，逐名点出（**缺失≠0**：不填零、不顶替）。
    _done = {str(r.get("费用项目") or "") for r in rows}
    _todo = [str(_it.get("费用项目") or "") for _it in items if str(_it.get("费用项目") or "") not in _done]
    _scope = ("口径说明：本项共登记 %d 类分项扣除限额，本轮**算出 %d 类**" % (len(items), len(rows)))
    if _todo:
        _scope += ("；其余 %d 类（%s）**因未取得工资薪金总额／年度利润总额等计算底稿，本轮未测算**"
                   "——按「缺失≠0」不填零、不顶替，须补资料后再核。" % (len(_todo), "、".join(_todo)))
    _scope += "。超限金额的**差异性质**分两类：永久性差异（当期调增后不得结转）与时间性差异（当期调增、准予结转以后年度扣除），两者当期都须调增，但后者以后年度可调减。"
    return {"title": "分项扣除限额测算", "columns": list(_LIMIT_COLUMNS), "rows": rows,
            "scope_note": _scope}


def risk_item_lead(redline_name, suspect_txt, participating, signal=""):
    """「一、涉及的风险事项」段首句（2026-10-02 抽出为可测函数，供闸门与回归测试直调）。

    铁律：**一条构成要件都没认下时，不得用触碰红线口径开场。**

    事故：旧版无条件写「经检查，本企业触发税务风险指标，即<红线名>，<suspect>；
    凡符合下列构成要件即属涉嫌疑点。」，而同一疑点下一段（构成要件独立核对表）却写
    「经核对，本企业涉及上述第 无 条构成要件」—— 同一疑点内部正面矛盾（用户复核实测）。

    根因：触碰红线判据（线索链有没有信号）与「涉及第 N 条要件」判据（constituent_checkpoint
    逐条独立核对有没有认定）是两套互不相认的口径，报告却默认它们永远一致。
    `participating` 为假（无序号被认定）时，只报"账内信号 + 标准清单"，不报触碰红线、不报罪名。
    """
    if participating:
        return (f"经检查，本企业触发税务风险指标，即{redline_name}，{suspect_txt}。"
                f"该风险指标不因行业而变，凡符合下列构成要件即属涉嫌疑点：")
    _sig = ("账内检出需进一步核验的信号——%s。" % str(signal).rstrip("。；").strip()) if signal else ""
    return (f"经检查，本企业未就「{redline_name}」认定到任何一条构成要件：{_sig}"
            f"下列要件清单是本项对应的判断标准，逐条核对结果见下：")


def sanitize_conclusion_assertion(text, redline_name, participating):
    """「四、本项结论及理由」的**触碰红线断言**必须与「是否认定到构成要件」口径一致。

    ★ 2026-10-02（用户复核疑点5）：首句（一、）已按 `participating` 分支成文，
      结论段（四、）却**无条件沿用**发现级的触碰红线 claim —— 于是同一疑点里
      首段说「未认定到任何一条构成要件」，结论段却写「本企业触碰红线……涉嫌虚开发票」。
      本次事故里 p1 改对了、p4 漏改，可见「两处口径」必须落到**同一个函数**上，
      靠渲染顺序天然一致是守不住的。

    ★ 本函数现**只做转调**：净化实现收归
      `argumentation.neutralize_assertion_when_no_constituent`（文本产出方同一份代码）。
      原因：报告侧读到的文本可能已被上游 `plain_language.to_plain` 改写
      （「补证」→「补充资料」），逐字锚点在报告侧会**静默失效**；
      真正的修法是在**案件卷宗刚落成、尚未被改写时**就地中性化（`redline_engine` 收尾），
      本函数留作输出侧的最后一道**幂等**保险（已中性化的文本不再匹配，原样返回）。
    """
    if participating:
        return str(text or "").strip()
    try:
        from engine.argumentation import neutralize_assertion_when_no_constituent as _n
    except Exception:
        return str(text or "").strip()
    return _n(text, redline_name)


def _with_scope_note(tables, sampled_scope=None):
    """给「具体问题」所附明细表加**统一口径说明**（★ 2026-09-29 点评整改 P1-1）。

    外部点评实测：附表标题「有工资无社保（共5笔）」，行里却是工资表**全员名单**，
    而正文与构成要件都说「仅 1 人（杨莹）」——读者无法判断到底几个人、是谁。

    根因：附在具体问题下的表是**该发现所依据的基础逐笔明细（全量）**，
    而正文/要件里的人数笔数是**按构成要件筛选后**的结果 —— 两者本就不同口径，
    但报告从未说明，于是看起来像自相矛盾。

    这里不改任何数字、不重算，只**把口径说清**（每表一次，措辞统一）。
    """
    out = []
    for t in (tables or []):
        if not isinstance(t, dict):
            continue
        t = dict(t)
        if len(t.get("rows") or []) >= 2 and not t.get("scope_note"):
            if sampled_scope:
                # ★ 2026-10-02（用户复核疑点5）：**抽样就说抽样**，不得自称"全量"。
                #   实测「需外部数据核验：关联交易的同期资料与关联申报（共8笔）」下的口径说明
                #   写的是"基础逐笔明细（全量）"，而这 8 行其实是采样上限截断的结果。
                #   `sampled_scope` 由采样方（pipeline）自带，不在报告层另写一份上限数字。
                t["scope_note"] = (
                    "口径说明：本表列出的是该风险事项所依据的基础逐笔明细的抽样"
                    "（%s，不是全量清单）；正文与构成要件中写明的人数/笔数是按构成要件筛选后的"
                    "结果，两者口径不同，判断具体涉及范围时以正文数字为准。" % sampled_scope)
            else:
                t["scope_note"] = (
                    "口径说明：本表列出的是该风险事项所依据的基础逐笔明细（全量）；"
                    "正文与构成要件中写明的人数/笔数是按构成要件筛选后的结果，"
                    "两者口径不同，判断具体涉及范围时以正文数字为准。")
        out.append(t)
    return out


def _finding_detail_tables(f):
    """取发现的可渲染明细表：优先用显式 detail_tables，否则把 evidence_rows 转成明细表。
    返回 list[dict]（每个 {title, columns, rows}）。"""
    if not isinstance(f, dict):
        return []
    dts = f.get("detail_tables") or []
    out = [t for t in dts if isinstance(t, dict) and t.get("rows")]
    if out:
        # ★ P1-1：附在具体问题下的表是"基础全量明细"，与正文按要件筛选后的人数/笔数
        #   口径不同 —— 统一加口径说明（每表一次），避免"表题与内容矛盾"的观感。
        return _with_scope_note(out)
    ev = f.get("evidence_rows") or []
    title = str(f.get("type") or "逐笔明细")
    if ev:
        # ★ 2026-10-02（用户复核疑点5）：**抽样不得自称"共N笔"** ——
        #   "共N笔"读起来是"这件事一共发生了 N 笔"，而 N 其实是采样上限截断后的行数。
        if f.get("evidence_rows_scope"):
            title = f"{title}（抽样{len(ev)}笔）"
        else:
            title = f"{title}（共{len(ev)}笔）"
    tbl = _evidence_rows_to_detail_table(ev, title=title)
    if tbl:
        return _with_scope_note([tbl], sampled_scope=f.get("evidence_rows_scope") or "")
    return []


# ── 明细行与本项口径的方向对准（唯一权威，报告层统一执行）─────────────────────
# ★★ 2026-10-03（用户："证据的收集特别不准，而且很垃圾，整一堆没用的证据和信息"）：
#   实测三类"垃圾证据"，全部是**行与本项口径不符**：
#     ① 「主营业务收入收款印证核实」表里混入**支出**行（明星费用 680,000、房租水电、
#        批量扣收手续费）—— 收款表列支出，读者无法判断本项结论；
#     ② 同一批银行流水行（上海蕴世 1,611,200 等）同时出现在疑点 3「银行收款大于申报收入」
#        与疑点 17「公转私大额频繁支出」（共 185 行跨疑点重复）—— 因为两侧都按"金额最大"
#        抓行，从不看方向：**按方向收敛后重复自然消失**（收款项只留收款行、支出项只留支出行）；
#     ③ 明细表与正文声明相矛盾（正文写"已剔除借款、往来款"，表里却有「借款」「往来款」）。
#   判据（与 `pipeline` 的"风险发生侧"同一口径，此处补到**报告层**以覆盖所有生产方）：
#     主题偏收入侧 ⇒ 只留收款行；偏支出侧 ⇒ 只留支出行；两侧都有（如"资金回流"既看收也看付）
#     ⇒ **不过滤**，避免丢证据。方向判不出来（金额为负的红冲行、无方向字段）⇒ **保留**（宁缺勿错）。
_INCOME_SIDE_KWS = ("收款", "收取", "收入", "账外", "隐匿", "少计", "未开票", "销项",
                    # 「回流」同时放进两侧：资金回流既看付出去、也看收回来的那一笔，
                    # 任一侧过滤都会丢证据 ⇒ 两侧都有线索 = 不过滤。
                    "回流")
_EXPENSE_SIDE_KWS = ("付款", "支付", "支出", "成本", "费用", "公转私", "发薪", "对私",
                     "进项", "采购", "回流")
# 非经营性收款：收入完整性主题下，这些是"差异的说明项"，不是经营性收款的证据
_NON_OPERATING_KWS = ("借款", "往来款", "还款", "退款", "贷款", "利息", "保证金", "押金",
                      "投资款", "备用金", "代收代付")


def _row_side(row) -> str:
    """单行的资金方向：`income` / `expense` / `unknown`。

    ★ 只认**结构化字段**（说明列的「收入/支出」、贷方/借方），不靠单位名称猜。
      红冲行（金额为负）与无方向字段的行一律 `unknown`（保留）。
    """
    note = str((row or {}).get("说明") or (row or {}).get("note") or "")
    # ★★ 2026-10-03（自检脚本抓出）：**同一行里同时含"转出/转入"的往来行，方向不明，不得过滤**。
    #   事故：疑点4「个人账户收取经营性款项」的附表行说明是"个人账户往来（转出600,000元/转入0元）"，
    #   `_row_side` 误判为支出侧 ⇒ 100 行被剔空，而**表题仍写"（共100笔）"**，形成
    #   "表题 100 笔、内容 0 行"的严重自相矛盾（自检脚本的第一条命中）。
    if ("转出" in note and "转入" in note) or ("借" in note and "贷" in note):
        return "unknown"
    if "支出" in note or "付款" in note:
        return "expense"
    if "收入" in note or "收款" in note:
        return "income"
    for _k, _side in (("贷方", "income"), ("收款", "income"),
                      ("借方", "expense"), ("付款", "expense")):
        if _k in note:
            return _side
    return "unknown"


def _filter_rows_by_subject_side(tables, subject_text):
    """按本项主题的资金方向过滤明细行；返回 `(过滤后的表, 被剔除行数)`。

    · 主题同时含收/支两侧线索 ⇒ 不过滤（避免丢证据）；
    · 方向判不出的行 ⇒ 保留；
    · 被剔除的行数如实回传，由报告写进表下口径说明（**不静默丢数据**）。
    """
    subj = str(subject_text or "")
    _inc = any(k in subj for k in _INCOME_SIDE_KWS)
    _exp = any(k in subj for k in _EXPENSE_SIDE_KWS)
    if _inc == _exp:
        return tables, 0
    want = "income" if _inc else "expense"
    out, dropped = [], 0
    for tb in (tables or []):
        rows = (tb or {}).get("rows") or []
        kept = []
        _d = 0
        _non_oper = 0
        for r in rows:
            _s = _row_side(r)
            if _s != "unknown" and _s != want:
                _d += 1
                continue
            # ★ 收入完整性主题：把**非经营性收款**（借款、往来款、还款、退款、贷款、利息、
            #   保证金…）从"经营性收款"明细里剔出去 —— 这些正是本项差异的**说明项**，
            #   不是本项的证据；而且正文已声明"已剔除…往来款等非收入项目"，
            #   表里再列出来就是**正文与表自相矛盾**（实测 12 行）。
            if want == "income":
                _lab = str((r or {}).get("凭证/单据标识") or (r or {}).get("ref_label") or "")
                if any(k in _lab for k in _NON_OPERATING_KWS):
                    _non_oper += 1
                    continue
            kept.append(r)
        dropped += _d + _non_oper
        if not (_d or _non_oper):
            out.append(tb)
            continue
        nt = dict(tb)
        nt["rows"] = kept
        # ★★ 2026-10-03（自检脚本抓出）：**过滤后必须同步表题里的"（共N笔）"**，
        #   否则出现"表题共100笔、实际0行"。空表一律不挂（避免空表占位）。
        if kept:
            _ttl = str(nt.get("title") or "")
            if re.search(r"（共\s*\d+\s*笔）", _ttl):
                nt["title"] = re.sub(r"（共\s*\d+\s*笔）", "（共%d笔）" % len(kept), _ttl)
            elif re.search(r"共\s*\d+\s*笔", _ttl):
                nt["title"] = re.sub(r"共\s*\d+\s*笔", "共%d笔" % len(kept), _ttl)
        _bits = []
        if _d:
            _bits.append("剔除 %d 行方向相反的资金记录（%s）"
                         % (_d, "本项只看收款" if want == "income" else "本项只看支出"))
        if _non_oper:
            _bits.append("剔除 %d 行非经营性收款（借款、往来款、还款、退款、贷款、利息、保证金等）"
                         "——这些是本项差异的**说明项**而非本项证据，须逐笔说明其性质，"
                         "故不列作经营性收款明细" % _non_oper)
        _note = ("口径说明：本表已按本项口径过滤，" + "；".join(_bits)
                 + "。被剔除的记录仍在其自身所属事项中列示，此处不重复。")
        nt["scope_note"] = (str(tb.get("scope_note") or "").strip() + " " + _note).strip()
        if kept:
            out.append(nt)
    return out, dropped


# ── 附表明细的**论点匹配**过滤（2026-10-06，用户复核疑点2）──────────────
# 用户原话（疑点2「工资表人数与社保参保人数不符」下面挂了 30 行"工资名册与社保清单"）：
#   「明确回答你：在当前"疑点2"这个主题下，你列出的这些信息**完全不需要展示**……
#     你给出的数据（初永伟、吴德昌、徐瑶的逐月工资与社保基数，且状态均为"工资社保均有"），
#     不仅不能证明"人数不符"，反而恰恰说明这些人在社保名单里是存在的。
#     把它们放在"人数不符"的疑点下，属于**证据与论点不匹配**，同时造成了严重的篇幅冗余。」
#
# **通用判据（不认表名、不认企业）**：表内若有**状态/结论列**，其值为"本行无差异"标记的行，
#   在**差异/异常类主题**下**不得作为本项证据列示** —— 它们不支撑本项论点，
#   还会把真正的差异行淹没（实测 30 行里 28 行是"均有"，真差异只有 2 行）。
#   ⚠ 标记词必须**窄**：只认明确的"本行无差异"（均有/无差异/无异常/匹配成功…）。
#     不得用"未发现/一致/相符/正常"等宽词 —— 实测宽词会命中「构成要件独立核对表」的
#     "未单独核对/未发现符合"行（那不是"无差异"），造成误删。
#   ⚠ 剔除必须**如实披露**（表下口径说明写明剔了几行、什么性质），不静默丢数据。
_STATE_COL_KEYS = ("匹配状态", "状态", "核对结论", "结论", "差异性质", "结果", "是否异常")
_NORMAL_STATE_MARKS = ("均有", "无差异", "不存在差异", "未发现差异",
                       "无异常", "不存在异常", "匹配成功")
#: 差异/异常类主题的关键词（命中即认为"本项要找的是差异"，无差异行不算证据）
_DIFF_SUBJECT_KWS = ("不符", "差异", "不一致", "不匹配", "偏低", "偏小", "偏高", "偏大",
                     "超限", "超过", "超出", "异常", "缺失", "为零", "偏离", "不实")
#: 实体列（用于判断"两张表是不是同一批对象"）
_ENTITY_KEYS = ("姓名", "人员", "人员姓名", "对方单位", "counterparty", "供应商", "客户")


def _row_state(row):
    """取行内**状态/结论列**的值（唯一判据入口；取不到给空串）。"""
    if not isinstance(row, dict):
        return ""
    for _k in _STATE_COL_KEYS:
        if _k in row:
            return str(row.get(_k) or "").strip()
    return ""


def _is_normal_row(row) -> bool:
    """该行是否是"本行无差异"（不构成差异证据）——**窄词**判据。"""
    _st = _row_state(row)
    return bool(_st) and any(_m in _st for _m in _NORMAL_STATE_MARKS)


def _row_entities(table):
    """取本表的**对象集合**（用于判"是否同一批对象"）；取不到返回 None。"""
    _rows = [r for r in ((table or {}).get("rows") or []) if isinstance(r, dict)]
    if not _rows:
        return None
    for _k in _ENTITY_KEYS:
        _vs = {str(r.get(_k) or "").strip() for r in _rows if str(r.get(_k) or "").strip()}
        if _vs:
            return frozenset(_vs)
    return None


def _filter_rows_off_topic(tables, subject_text):
    """按**本项论点**过滤附表：剔除"无差异"行 + 同批对象只留最聚合的一张表。

    返回 `(过滤后的表, 剔除行数, 说明片段列表)`。两项通用规则：

      R-a **差异主题下剔除"无差异"行**：主题含差异/异常类词，且表内状态列标记"本行无差异"
          ⇒ 该行不是本项证据（它证明的是"这项正常"），剔除；剔空则整表不挂。
      R-b **同批对象只留最聚合的一张表**：多张表的**对象集合相同**时，只保留**行数最少**
          （即已按对象聚合）的那张，其余不挂 —— 同一批数据在一项里呈现多遍是纯冗余
          （实测疑点2 挂了 3 张都讲"杨莹 1–2 月"的表）。

    ⚠ 关于"逐月明细不逐行铺开"：**本函数不额外做聚合**，因为实测本系统产出的
      社保低基数/公积金类表**已是按人聚合**（1 行/人，月份写在"涉及月份"列），
      唯一的"人×月"级表是工资-社保**配对状态表**，而它经 R-a/R-b 后留下的正是
      已聚合的那张（1 行/人）。故不为此再写一套聚合逻辑（避免"注释说 A、代码做 B"）。
    """
    subj = str(subject_text or "")
    if not any(k in subj for k in _DIFF_SUBJECT_KWS):
        return tables, 0, []          # 非差异主题 ⇒ 一行不动（保守）
    notes: List[str] = []
    off = 0
    stage: List[dict] = []
    for tb in (tables or []):
        rows = [r for r in ((tb or {}).get("rows") or []) if isinstance(r, dict)]
        kept = [r for r in rows if not _is_normal_row(r)]
        _n = len(rows) - len(kept)
        if not kept:
            off += _n
            notes.append("本表 %d 行全部为「无差异」记录（不构成本项差异证据），故不列示"
                         % len(rows))
            continue
        off += _n
        nt = dict(tb)
        nt["rows"] = kept
        if _n:
            _ttl = str(nt.get("title") or "")
            nt["title"] = re.sub(r"（共\s*\d+\s*笔）", "（共%d笔）" % len(kept), _ttl) \
                if re.search(r"（共\s*\d+\s*笔）", _ttl) else _ttl
        stage.append(nt)
    # R-b：同批对象只留最聚合的一张（行数最少；同则列数最多者）
    by_ent: Dict[Any, List[int]] = {}
    for i, tb in enumerate(stage):
        _e = _row_entities(tb)
        if _e:
            by_ent.setdefault(_e, []).append(i)
    drop_idx: set = set()
    for _e, idxs in by_ent.items():
        if len(idxs) < 2:
            continue
        _best = max(idxs, key=lambda i: (-len(stage[i].get("rows") or []),
                                        len(stage[i].get("columns") or [])))
        for i in idxs:
            if i != _best:
                drop_idx.add(i)
                off += len(stage[i].get("rows") or [])
        notes.append("同一批对象（%s）另有 %d 张表重复呈现，本处只保留已聚合的那张"
                     % ("、".join(sorted(_e))[:20], len(idxs) - 1))
    out = [tb for i, tb in enumerate(stage) if i not in drop_idx]
    # ★★ 2026-10-06：R-b 删掉同批对象的重复表后，**幸存表里指向它的"上表/下表"引用会悬空**
    #   （实测幸存表题写着"（同一批差异：与上表「有工资无社保」是同一批对象…）"，
    #     而那张表已被 R-b 删除 ⇒ 读者找不到"上表"。）
    #   ⇒ 删表必须同时清掉对它的**悬空引用**（只清"指代别的表"的括注，不动本项事实）。
    if drop_idx:
        _ref = re.compile(r"[（(][^（）()]*[上|下]表[^（）()]*[）)]")
        for tb in out:
            for _f in ("title", "scope_note"):
                _v = str(tb.get(_f) or "")
                if _v and ("上表" in _v or "下表" in _v):
                    _nv = _ref.sub("", _v).strip()
                    _nv = re.sub(r"[（(]\s*[）)]", "", _nv).strip()
                    tb[_f] = _nv
    if off or notes:
        _n2 = ("口径说明：本表只列示与本项论点相关的差异记录"
               + ("（共剔除 %d 行无差异或重复记录：%s）" % (off, "；".join(notes[:3])) if notes else "")
               + "；被剔除的记录不是本项证据，逐笔台账仍在本报告工作底稿中可查。")
        for tb in out:
            tb["scope_note"] = (str(tb.get("scope_note") or "").strip() + " " + _n2).strip()
    return out, off, notes


def _evidence_summary(tables) -> str:
    """把本项附表的证据**汇总成一句概述**（口径／笔数／对象数／合计金额／最大一笔）。

    ★★ 2026-10-03（用户：「本项之所以列入检查，是因为出现了以下情况：<某一个例子>…
      这段话能否概述情况，而不是列举情况；**各疑点的这段内容也是概述情况，而不是列举情况**」）：
      旧版取"某一条发现的 detail 原句"，而 detail 常是**举例**（"河南林超攀：转出600,000元…"），
      于是"为何列入检查"变成"举一个例子"，甚至可能举到与本项主体**相反**的例子。
      现改为**从本项证据本身归纳**：命中多少笔、涉及多少对象、合计多少钱、最大一笔是谁——
      这才是稽查底稿说明"为什么把它列入检查"的口径（可复算、可回指明细表）。
      返回 "" 表示无法汇总（调用方退回原取值链，不编造）。
    """
    rows = [r for tb in (tables or []) for r in ((tb or {}).get("rows") or [])]
    if not rows:
        return ""
    # ★★ 2026-10-03（用户质询疑点23「触发依据不能自证」）：**逐表概述，不跨表合并行数**。
    #   事故：同一疑点挂了三张表（要件核对表 5 行 + 有工资无公积金 2 行 + 缴存基数 53 行），
    #   旧实现把三张表的行数/金额**加总**成"共55笔记录…金额合计928,000.00元" ——
    #   55 与 928,000 在语义上既不是人数差异、也不是基数差额，读者无法据此判断"为什么列入检查"。
    #   现按表逐条概述：表题（自带口径与人数对比）+ 本表行数 + 对象数 + 金额合计。
    _NAME_KEYS = ("对方单位", "counterparty", "人员", "人员姓名", "姓名")
    _AMT_KEYS = ("金额（元）", "金额(元)", "金额", "amount", "应发工资（元）", "工资")
    segs: List[str] = []
    for tb in (tables or []):
        _rows = [r for r in ((tb or {}).get("rows") or []) if isinstance(r, dict)]
        if not _rows:
            continue
        ttl = str((tb or {}).get("title") or "逐笔明细").strip()
        # ★★ 2026-10-04（用户复核疑点6「触发依据金额夸大 32.3 倍」）：
        #   事故：表「工资名册与社会保险人员范围差异（共30笔）」的 30 行里 **28 行是"工资社保均有"
        #   （无差异的正常行）**，而本函数把**全部 30 行的工资**加总成"金额合计 549,000.00 元"——
        #   真实差异只有 **17,000**（杨莹 2 个月）⇒ **夸大 32.29 倍**，且表题与内容矛盾。
        #   根因：**把"配对状态表"当"命中明细表"**——范围/配对类表的每一行并不都是本项发现。
        #   通用判据（数据驱动、不认表名）：表内若有**状态/结论类列**，其值为"无差异"类标记的行
        #   **不计入**金额与对象数，并把未计入的行数**如实披露**（不得把非差异当差异）。
        #   ★ 判据只认**明确的"本行无差异"标记**（均有 / 无差异 / 不存在差异 / 未发现差异 /
        #     无异常 / 不存在异常 / 匹配成功）——**不得**用"未发现""一致""相符""正常"等宽词：
        #     实测宽词会命中 9 张「构成要件独立核对表」的"未单独核对/未发现符合"行（那不是"无差异"）。
        #   ★★ 并**不把"差异"二字注入文案**：`差异` 是涉案金额的语义锚点，注入它会改变
        #     `tax_impact.extract_amount` 的锚定结果（实测一改措辞就有 12 个疑点的 tax_impact 变值）。
        #     本项只做两件事：**金额只算非无差异行** + **如实披露无差异行数**；措辞保持原样。
        _STATE_KEYS = ("匹配状态", "状态", "核对结论", "结论", "差异性质", "结果", "是否异常")
        _NORMAL_MARKS = ("均有", "无差异", "不存在差异", "未发现差异", "无异常", "不存在异常", "匹配成功")
        # ★★ 2026-10-04（疑点2 D8）：**汇总行不是一笔明细**。
        #   事故：`verified_rule_engine` 产出的「【汇总】其他个人／个体往来（未达本要件50万元门槛，
        #   共8个对象）」被当普通明细行，计入"共N笔"与"金额合计"（实测疑点2 的共3笔／2,246,055.57）；
        #   渲染时还被截断成"汇总：其他个人／个体往来（未达本要件50万元门槛"（括号不闭合）。
        #   `pipeline.py` 本有"跳过银行流水汇总行"的机制，但检测器自拼的行没走那道闸——
        #   故在**消费端**加通用数据判据（不认表名）：实体列取值以「汇总／合计／小计／总计」
        #   开头或含「【汇总】／汇总：」⇒ 汇总行，不计入笔数与金额，并如实披露行数。
        _SUMMARY_MARKS = ("汇总", "合计", "小计", "总计")
        _kept, _normal = [], 0
        _summary_rows = 0
        for r in _rows:
            _st = ""
            for _k in _STATE_KEYS:
                if _k in r:
                    _st = str(r.get(_k) or "")
                    break
            if _st and any(_m in _st for _m in _NORMAL_MARKS):
                _normal += 1
                continue
            # 汇总行：实体列（对方单位/人员/姓名/凭证号…）以「汇总/合计/小计/总计」开头
            _is_sum = False
            for _k in _NAME_KEYS + ("凭证号", "凭证/单据标识"):
                _v = str(r.get(_k) or "").strip()
                if _v and any(_v.startswith(_m) or ("【汇总】" in _v) or ("汇总：" in _v)
                              for _m in _SUMMARY_MARKS):
                    _is_sum = True
                    break
            if _is_sum:
                _summary_rows += 1
                continue
            _kept.append(r)
        if not _kept:
            # 全部行都经核对无差异 ⇒ 本表不构成"触发依据"，如实说明（不虚报金额）
            segs.append("%s（本表 %d 行经逐项核对无差异，不计入触发金额）" % (ttl, len(_rows)))
            if len(segs) >= 3:
                break
            continue
        names, amts = [], []
        for r in _kept:
            who = ""
            for _k in _NAME_KEYS:
                who = str(r.get(_k) or "").strip()
                if who:
                    break
            if who and who not in names:
                names.append(who)
            for k in _AMT_KEYS:
                if k in r:
                    try:
                        amts.append(abs(float(str(r[k]).replace(",", "").rstrip("%"))))
                    except (TypeError, ValueError):
                        pass
                    break
        # ★★ 2026-10-04（疑点1 四维自检 D2）：**表内混方向时不得跨方向加总**。
        #   事故：本项明细表 13 行含销项（本企业开出）4 行 + 取得（进项）9 行，概述写成
        #   "金额合计 1,285,450.57 元"（= 1,015,900.00 + 269,550.57）——而同一疑点正文已写明
        #   "影响销项税额的只有销项侧" ⇒ 触发依据与正文两个口径，合成数还被当成本项涉案金额。
        #   通用判据（**纯结构、不认表名**）：表内若有方向/侧别类列且**取值多于一种**，
        #   行数与金额按方向分列、不跨类加总；只有一类或无该类列 ⇒ 行为完全不变。
        #   （与相邻的"配对状态表不得当命中明细表"判据同一风格。）
        #   ⚠ 第一版按**列名**找"方向/开票方向…"——**实测没生效**：本项侧别信息编码在
        #     「来源」列里（取值 = "销项发票"/"进项发票"），列名不含"方向"。
        #     故改按**列的取值**判：取值集合全部落在方向词表内、且多于一种 ⇒ 该列是方向列。
        #     仍是数据驱动（新增侧别叫法只往 `_SIDE_VALUES` 加一项），不认表名。
        _SIDE_VALUES = (
            "销项", "进项", "销项发票", "进项发票", "开出", "取得",
            "收入", "支出", "收款", "付款", "转出", "转入",
            "借", "贷", "借方", "贷方", "销项税额", "进项税额",
        )
        _by_dir = {}
        for _k in ((_kept[0] or {}).keys()):
            _vals = {str((_r0 or {}).get(_k) or "").strip() for _r0 in _kept}
            _vals.discard("")
            if len(_vals) < 2:
                continue
            if not all(_v in _SIDE_VALUES for _v in _vals):
                continue
            for _r0 in _kept:
                _by_dir.setdefault(str((_r0 or {}).get(_k) or "").strip() or "未标注",
                                   []).append(_r0)
            break
        if len(_by_dir) < 2:
            _by_dir = {}
        seg = "%s（本表 %d 行" % (ttl, len(_rows))
        if _normal:
            seg += "，其中 **%d 行经逐项核对无差异**（不计入金额与对象数）" % _normal
        if _summary_rows:
            # 如实披露被排除的汇总行（不得静默少算，也不得把汇总当明细）
            seg += "，另有 %d 行为汇总结算行（不计入笔数与金额）" % _summary_rows
        if names:
            seg += "，涉及 %d 个对象" % len(names)
        if _by_dir:
            _parts = []
            for _dv, _rs in _by_dir.items():
                _a = 0.0
                for _r0 in _rs:
                    for _k in _AMT_KEYS:
                        if _k in _r0:
                            try:
                                _a += abs(float(str(_r0[_k]).replace(",", "").rstrip("%")))
                            except (TypeError, ValueError):
                                pass
                            break
                _parts.append("%s %d 行、金额合计 %s 元"
                              % (_dv, len(_rs), format(_a, ",.2f")))
            seg += "，按方向分列（不跨方向加总）：" + "；".join(_parts)
        elif amts:
            seg += "，金额合计 %s 元" % format(sum(amts), ",.2f")
        segs.append(seg + "）")
        if len(segs) >= 3:
            break
    return "；".join(segs) + "。"


# 表内"实体"列（用来判断两张表讲的是不是同一批对象）与"金额"列
_TBL_ENTITY_KEYS = ("姓名", "人员", "人员姓名", "对方单位", "counterparty", "工号", "身份证号")
_TBL_AMT_KEYS = ("金额（元）", "金额(元)", "金额", "amount", "应发工资（元）",
                 "工资", "工资表内工资合计（元）", "账面发生额（元）", "超限金额（元）")


def _tbl_entities(tb) -> set:
    """取一张表的实体值集（非空才返回；用于判断两表是否讲同一批对象）。"""
    out = set()
    for r in ((tb or {}).get("rows") or []):
        if not isinstance(r, dict):
            continue
        for _k in _TBL_ENTITY_KEYS:
            _v = str(r.get(_k) or "").strip()
            if _v:
                out.add(_v)
                break
    return out


def _tbl_has_amount(tb) -> bool:
    _cols = [str(c) for c in ((tb or {}).get("columns") or [])]
    _cols += [k for r in ((tb or {}).get("rows") or []) if isinstance(r, dict) for k in r.keys()]
    return any(any(_a == _c or _a in _c for _a in _TBL_AMT_KEYS) for _c in _cols)


def _annotate_overlapping_tables(tables) -> list:
    """同一疑点内多张表讲**同一批差异**时，给较小（按实体归并）的那张标注口径关系。

    ★★ 2026-10-04（用户复核疑点6 D8「表2 与表4 完全重复」）：
      事故——同一疑点下同时出现
        ·「工资名册与社会保险人员范围差异（30 行，人月级）」⊇
        ·「有工资无社保（2 行，人月级）」＝
        ·「工资名册有、社保参保无（1 行，人员级）」
      三张表讲的是**同一批差异**（最后一张是前者的**按人员归并**），却都没有说明口径关系；
      读者会以为是三批不同的差异。（且最后一张是**另一域新增时**造成的重复 —— 多头建表。）

    判据（数据驱动、不认表名）：两表**实体值集非空且相等** + **都有金额列** + **行数不同**
      ⇒ 行数少的即"按实体归并"的口径 ⇒ 在其**标题后追加关系声明**。
    ★ **保留原表、不删数据、不改数字**（口径关系必须自证，不得静默合并）。

    返回**新列表**（表 dict 复制后改写标题，避免污染其他疑点共用的同一份表对象）。
    """
    tabs = [t for t in (tables or []) if isinstance(t, dict)]
    if len(tabs) < 2:
        return list(tables or [])
    out = [dict(t) for t in tabs]
    _ents = [_tbl_entities(t) for t in out]
    _amts = [_tbl_has_amount(t) for t in out]
    _rows = [len(t.get("rows") or []) for t in out]
    for i in range(len(out)):
        for j in range(len(out)):
            if i == j or not _ents[i] or _ents[i] != _ents[j]:
                continue
            # i 为"较小（归并）"表：行数更少，且两张都有金额列
            if not (_rows[i] < _rows[j] and _amts[i] and _amts[j]):
                continue
            _ti = str(out[i].get("title") or "")
            _tj = str(out[j].get("title") or "")
            if "同一批差异" in _ti:
                continue
            # ★ 引用另一张表的标题时**只取主名**（去掉其自带括号），并在截断处给出可见「…」
            #   —— 项目铁律：**截断必须可见**，且正文/表题禁 markdown（`**` 会被渲染层剥掉）。
            _ref = _tj.split("（")[0].strip()
            if len(_ref) > 18:
                _ref = _ref[:18] + "…"
            out[i]["title"] = (
                _ti + "（同一批差异：与上表「%s」是同一批对象，按人员归并呈现，"
                      "不另行计数、不另计金额）" % _ref)
            out[i]["scope_note"] = (
                str(out[i].get("scope_note") or "").strip()
                + " 口径说明：本表是同一批差异的归并视图（与「%s」同源），"
                  "只换个粒度呈现，不另行计数。" % _ref).strip()
            break
    return out


def _select_detail_tables(rid, rname, sup_subjects, src_tables, dt_by_rid, dt_by_type, s):
    """按**来源归属**选本疑点的逐笔明细表（唯一判据在 `subject_consistency`）。

    返回 `(tables 或 None, 附在正文里的如实说明或 "")`。

    选取顺序：
      ① 本疑点**自己声明的支撑发现**出的表（权威口径，零猜测）；
      ② 支撑发现为空（应为个例）→ 按红线编号精确关联；
      ③ 再退一步：以**同一主体判据**（`subject_consistency.same_subject`）在
         「发现类型 ↔ 本疑点主体」之间找表 —— ★ 不再用汉字 2-gram 重叠：
         实测 2-gram 会把「增值税进项税额对等」挂到「附加税费计税依据与增值税不匹配」名下，
         而同一主体判据（泛词已剔除）能同时做到"该挂的挂上、不该挂的不挂"。
      ④ 都没有 → 不附明细；若系统里**确实存在**与该红线编号相关的明细、只是主体不符，
         则如实写明"为什么没附"（读者需要知道是"没有相关的"，不是"系统没查"）。
    """
    try:
        from engine.subject_consistency import norm_subject_key as _nsk
        from engine.subject_consistency import same_subject as _ssame
    except Exception:
        _nsk = None
        _ssame = None
    sup_keys = []
    for x in (sup_subjects or []):
        k = _nsk(x) if _nsk else str(x or "")
        if k and k not in sup_keys:
            sup_keys.append(k)
    picked, seen = [], set()
    for k in sup_keys:
        hit = (src_tables or {}).get(k)
        if not hit:
            continue
        for t in (hit.get("tables") or []):
            ttl = str((t or {}).get("title") or "")
            if ttl in seen:
                continue
            seen.add(ttl)
            picked.append(t)
    # ★★ 2026-10-03（自检脚本抓出的**回归**）：本函数的第二返回值语义是"**如实说明文本**"，
    #   而 `_filter_rows_by_subject_side` 的第二返回值是"剔除行数(int)" —— 直接透传会让
    #   `_pp["text"] + _tbl_note` 抛 `TypeError: can only concatenate str (not "int") to str`，
    #   导致**企业版报告整段生成失败**（main 里被 except 吞掉、只留一行日志、报告静默降级）。
    #   现统一由 `_apply_dir_filter` 适配：返回 (tables 或 None, 说明文本)。
    def _apply_dir_filter(_tabs):
        _t2, _dropped = _filter_rows_by_subject_side(_tabs, rname)
        # ★★ 2026-10-06（用户复核疑点2）：**再按本项论点过滤** ——
        #   剔除"本行无差异"的行（它们不构成本项差异证据）、同批对象只留最聚合的一张表。
        #   必须在**方向过滤之后**、**挂载之前**（唯一收口点），否则又会出现
        #   "某处过滤了、另一处照旧挂"的多头情形。
        _t2, _offtopic, _ot_notes = _filter_rows_off_topic(_t2, rname)
        if _t2:
            return _t2, ""
        if _dropped or _offtopic:
            _why = []
            if _dropped:
                _why.append("方向相反的资金记录 %d 行" % _dropped)
            if _offtopic:
                _why.append("与本项论点无关的无差异/重复记录 %d 行" % _offtopic)
            return None, ("\n\n说明：本项口径下可逐笔列示的记录全部为%s（已剔除），"
                          "故本项不附明细表；这些记录归属其自身所属事项，"
                          "逐笔台账仍在本报告工作底稿中可查。" % "、".join(_why))
        return None, ""

    if picked:
        # ★ 2026-10-03：按本项主题的资金方向对准（收款类只列收款、支出类只列支出）
        return _apply_dir_filter(picked)
    if not sup_keys:
        cand = (dt_by_rid or {}).get(rid) if rid else None
        if cand:
            return _apply_dir_filter(list(cand))
        # 同一主体兜底（无红线编号 / 无支撑发现时的最后一道）
        if _ssame and rname:
            for _tk, _tabs in (dt_by_type or {}).items():
                if _ssame(_tk, rname):
                    return _apply_dir_filter(list(_tabs))
        return None, ""
    # 有明细被拒（主体不符）→ 必须说明，不能默默少一张表
    rej = (dt_by_rid or {}).get(rid) if rid else None
    if rej:
        ttl = str((rej[0] or {}).get("title") or "")[:30]
        return None, (
            "\n\n说明：系统内另有一套与本项红线编号关联的逐笔明细（「%s」），"
            "经主体一致性核对，其反映的是**另一件事**，与本项主体不符，故不附于本项；"
            "该明细已归入其自身所属事项。本项不附逐笔明细，不代表本项未作核对——"
            "本项实际读到的事实与数字见上一节各环。" % ttl)
    return None, ""


def _build_subject_audit(problems, sink):
    """把"哪个环节记了什么"汇总成一份可复核的自检结果（唯一出口，供报告与流水共用）。

    `sink` 是 `_build_redline_problems` 逐项累计的原始记录；本函数只做统计与
    逐项对应（把 `seq` 补齐），不改判定结论。
    """
    issues = list((sink or {}).get("issues") or [])
    # 逐项回填 seq/title（报告层按 `redline_id` + 标题前缀对齐）
    _by_rid = {}
    for p in (problems or []):
        _by_rid.setdefault(str(p.get("redline_id") or ""), []).append(p)
    for it in issues:
        if it.get("seq"):
            continue
        cands = _by_rid.get(str(it.get("redline_id") or "")) or []
        for p in cands:
            if str(it.get("title") or "")[:24] and str(it.get("title") or "")[:24] in str(p.get("title") or ""):
                it["seq"] = p.get("seq")
                it["title"] = str(p.get("title") or "")[:60]
                break
        else:
            if cands:
                it["seq"] = cands[0].get("seq")
                it["title"] = str(cands[0].get("title") or "")[:60]
    by_code = {}
    for it in issues:
        by_code[it.get("code") or "—"] = by_code.get(it.get("code") or "—", 0) + 1
    _checked = len(problems or [])
    _bad_seqs = {it.get("seq") for it in issues if it.get("seq")}
    out = {
        "checked": _checked,
        "issue_count": len(issues),
        "ok_count": max(0, _checked - len(_bad_seqs)) if _bad_seqs else _checked,
        "issues": issues,
        "by_code": by_code,
        "rule": ("疑点主体自检：① 每条疑点的**主体（风险指标名）**与其**支撑发现**必须"
                 "是同一件事（主体词有交集，或红线库声明过该类主体归本红线）；"
                 "② 每条拟挂附表必须来自**本疑点自己声明的支撑发现**；"
                 "③ 判据不成立时：不挂该附表、标题声明认定范围、结论保持待核，并记入本自检。"),
    }
    try:
        from engine.subject_consistency import format_audit_line
        out["summary_line"] = format_audit_line(out)
    except Exception:
        out["summary_line"] = "主体一致性自检：检查 %d 项，%d 项不一致" % (
            out["checked"], out["issue_count"])
    return out


def _match_suspicion_detail(s, dt_by_type):
    """按「发现类型 ↔ 疑点红线名」关键词重叠，把未打 redline_id 的域发现兜底关联到疑点。
    返回匹配到的明细表 list 或 None；重叠 2-gram 数 >=3 才命中，避免误挂。

    ★ 2026-10-01（用户复核疑点2 实测）：**只比对红线名，不得掺 `suspect`**。
      原实现把 `suspect`（如「涉嫌少缴企业所得税」）也算进比对文本，而 suspect 是
      **泛税种词**（所得/得税/企业…），几乎与任何发现都能凑到 3 个 2-gram →
      实测把「表1 主营成本总额·按供应商分布」挂到了「营业账簿印花税未申报」名下（张冠李戴）。
      红线名是本条疑点的**唯一身份标识**，比对只用红线名。
    """
    if not isinstance(s, dict) or not dt_by_type:
        return None
    name = str(s.get("redline_name") or "")
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

# ★★ 2026-10-02（用户质疑：行业为服务业，是否还欠缺进销存台账？）：**资料要求必须跟随业态**。
#   业态配置 `industry_resolver.business_category()` 里每个业态已声明 `skip_domains`
#   （服务型的 skip_domains 明确含「进销存分析/存货周转/BOM映射/水电能耗分析」），
#   域分析据此跳过；但**必查资料清单没有跟着走** ⇒ 同一份报告自相矛盾：
#     一处写「进销存跳过-服务行业：不适用进销存比值分析」，
#     另一处把「进销存台账」列为缺失并要求企业补交（实测企业版报告 94 处提及）。
#   对服务企业要求存货台账是**无效要求**：既增加企业负担，又让"资料齐全"永远达不到
#   （参考：某服务型企业 15 类必查里缺 7 类，其中 1 类根本不该要）。
#   本映射：**业态跳过的域 → 该域所需的资料名**。新增同类只加一行（资料名取自已登记名）。
def _not_required_docs(industry):
    """按**业态**给出「不该列为必查」的资料名与原因（薄转发，唯一实现在 industry_resolver）。

    ★ 判据为业态 `skip_domains`（服务型含"进销存分析/存货周转/BOM映射"）；
      `evidence_chain` 算缺失时也调同一实现，保证"报告说缺什么"与"这里列必查"一致。
    """
    from engine.industry_resolver import not_required_materials as _nrm
    return _nrm(industry)


#: 材料名内的**并列分隔符**（"采购合同与入库验收单" ⇒ 两段）
# ★★ 2026-10-06：**分隔符表与判定算法已收敛到唯一权威**
#   `industry_resolver.MATERIAL_SEG_SEP` / `exclude_not_required_material`。
#   本模块不再自持一份（曾出现 4 份实现、4 种判法：字符级 replace / 段级 /
#   不含「与」的段级 + 双向包含 / 整句文本级 ⇒ 同一要件在一份报告里 4 种结论）。


def _strip_not_required(name, not_required):
    """**薄转发** → `industry_resolver.exclude_not_required_material`（唯一权威）。

    段级剔除本业态不适用的资料段；返回 "" 表示整项都不适用（调用方应剔除该项）。
    ⇒ "采购合同与入库验收单" → "采购合同"（保留适用部分，不整项误删）。
    """
    from engine.industry_resolver import exclude_not_required_material as _authority
    return _authority(name, not_required)


def _trim_text_materials(text, not_required):
    """**薄转发** → `industry_resolver.exclude_not_required_in_text`（唯一权威）。

    例：`补救要求：提供付款对应的采购合同、入库验收单、物流单据，并对…`
      → `补救要求：提供付款对应的采购合同，并对…`
    """
    from engine.industry_resolver import exclude_not_required_in_text as _authority
    return _authority(text, not_required)


def _filter_not_required(items, not_required):
    """对一串材料名过业态剔除（返回新列表，保持原序；整项不适用的丢掉）。"""
    out = []
    for x in (items or []):
        _t = _strip_not_required(x, not_required)
        if _t and _t not in out:
            out.append(_t)
    return out


def _trim_action_material(action, not_required):
    """把「补充提供「X」」/「取得直接证据：X」/「确认已提供的「X」…」里的材料名过业态剔除。

    材料名被剔空 ⇒ 返回 ""（调用方丢掉整个动作）。
    """
    _a = str(action or "").strip()
    if not _a or not not_required:
        return _a
    for _pre, _suf, _q in (("补充提供「", "」", True),
                           ("确认已提供的「", "」", True),
                           ("取得直接证据：", "", False)):
        if _a.startswith(_pre):
            _body = _a[len(_pre):]
            _tail = ""
            if _q:
                _i = _body.find(_suf)
                if _i < 0:
                    return _a
                _tail = _body[_i:]
                _body = _body[:_i]
            _new = _strip_not_required(_body, not_required)
            if not _new:
                return ""
            return _pre + _new + _tail
    return _a


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


def _note(out_obj, msg) -> None:
    """报告级留痕（唯一实现）：追加到 `pipeline_log`。

    说明：`main._append_one_click_log` 是同语义实现，但 `engine` 层 import `main` 会成环，
    故在此本地实现**同一语义**（不静默丢弃、不改动报告事实）。
    """
    if isinstance(out_obj, dict):
        lg = out_obj.setdefault("pipeline_log", [])
        if isinstance(lg, list):
            lg.append(str(msg))

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
    '经检查，本企业触发税务风险指标（尚需核实），即<指标名>，' 的全局框架前缀。

    该框架（"尚需核实 / 触发指标"）在 headline 已统一陈述一次；若逐条重复，
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


def _report_level_notes_statement(problems: Any) -> List[str]:
    """报告级**通用口径**声明（风险等级依据 / 可信度公式）—— 上提一次。

    ★ 与 `engine/report_pipeline.merge_report_level_notes` **同口径**（共用同一常量表
      `REPORT_LEVEL_TEXT_KEYS` / `REPORT_LEVEL_MIN_OCCUR`），避免"两处各写一套"。
      上提后逐项位置写的是 `REPORT_LEVEL_REF`（「见报告性质和使用说明」）——
      所以**这里必须真的把它写出来**，否则引用悬空。
    """
    try:
        from engine.report_pipeline import (
            REPORT_LEVEL_TEXT_KEYS, REPORT_LEVEL_MIN_OCCUR, REPORT_LEVEL_REF,
        )
    except Exception:  # noqa: BLE001 —— 取不到就不加（不臆造）
        return []
    from collections import Counter
    out: List[str] = []
    for k in REPORT_LEVEL_TEXT_KEYS:
        cnt: Counter = Counter()
        for it in (problems or []):
            if isinstance(it, dict):
                v = it.get(k)
                # ⚠ 必须**排除已上提的引用语**：否则重复调用时取到的是
                #   「（见报告性质和使用说明）」本身 ⇒ 生成自引用声明（实测踩过）。
                if isinstance(v, str) and v.strip() and v.strip() != REPORT_LEVEL_REF:
                    cnt[v.strip()] += 1
        if not cnt:
            continue
        mode, n = cnt.most_common(1)[0]
        if n < REPORT_LEVEL_MIN_OCCUR:
            continue
        label = {"risk_level_basis": "风险等级依据", "confidence_formula": "可信度（置信度）公式"}.get(k, k)
        out.append("%s：%s" % (label, mode))
    return out


def _report_levy_declarations(problems: Any) -> List[str]:
    """报告级「税费性质与法定后果」声明 —— **唯一入口**（2026-10-08，P0-2 去重收口）。

    逐项「若不补证的后果」只留本项情形 + 引用（`levy_nature.item_consequence_text`），
    法条原文**按性质在报告级声明一次**：既满足"同一法条不得逐项重复"（产出链的
    重复率阻断），又满足"法条不得因去重被删"（合规底线）。

    数据驱动：只为**本报告实际涉及**的性质声明；新增一种税费只在 `levy_nature.LEVIES`
    加一行，本处与逐项引用自动跟随（不改任何逻辑分支）。
    """
    _nats: List[str] = []
    for _p in (problems or []):
        if not isinstance(_p, dict):
            continue
        for _n in _levy_natures_of(_p):
            if _n not in _nats:
                _nats.append(_n)
    return _levy_declarations(_nats)


def _administrative_boundary_statement() -> List[str]:
    """报告**效力边界**声明（《专注税务风险检查条款》第5条）—— **唯一权威**。

    "本报告不替代税务机关法定程序认定"是条款要求的**强制声明**；
    收敛为函数而非散落字面量，使闸门可**运行时断言**（改别处无法绕过）。
    """
    return ["本报告不替代税务机关依法定程序作出的认定；是否达到相应标准，"
            "须由有权人员依法核实后另行判断。"]


def _conclusion_terms_statement() -> List[str]:
    """报告**结论用语**声明（条款 B4）。

    ★ 术语**唯一权威**是 `config/conclusion_grades.json::term_authority`，
      经 `engine.conclusion_grade.conclusion_terms()` 薄转发读取 ——
      本函数不硬编码四词，避免"两处各写一套"（用户条款要求结论只用四个术语）。
    """
    try:
        from engine.conclusion_grade import conclusion_terms
        ts = list(conclusion_terms())
    except Exception:  # noqa: BLE001 —— 取不到就不加该声明（不臆造）
        return []
    if not ts:
        return []
    return ["结论用语：本报告结论只用四个术语——%s；其中「%s」只能由有权机关依法作出，本报告不作出。"
            % ("、".join(ts), ts[-1])]


def _build_inspector_perspective():
    return {
        "opening": "根据本轮税务风险检查工作安排，现对被检查企业提交并成功读取的财税资料实施检查，并将检查范围、实施程序、查明事实、税务影响、处理意见及后续复查要求报告如下。",
        "work_principle": "以企业上传的原始资料为起点，先确认数据事实，再核对交易、会计处理和纳税申报；正常解释、反向证据和资料缺口分别记录。",
        "conclusion_rule": "只有能够回查到本轮资料的具体事实才写入问题部分；行业指标、风险评分和资料缺失不能单独作为问题认定。",
        # ★ 2026-10-06（用户：「五、报告性质和使用说明……重写，有废话」）：
        #   删掉「由企业使用的财税风险防控系统依据已提交资料生成，用于模拟税务风险检查程序
        #   并开展合规整改」—— **系统自述**（我们是谁、用来干什么），企业不需要知道；
        #   「依据已提交资料生成」也与第三章「覆盖范围声明」重复。只留**效力边界**一句。
        #   ⚠ 这是**唯一权威**（前端只在它为空时的兜底文案里也有同一句，两处必须一致）。
        "administrative_boundary": "本报告不具有税务机关行政执法文书的效力，不替代税务机关依法定程序作出的认定；税务机关的实际检查结论以依法送达的正式文书为准。",
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
        detail_rows, detail_cols, detail_total = _build_detail_table(f)
        if detail_rows:
            # 把明细表挂在第一段对象上，供前端渲染；同时保留文本回退
            # ★ 2026-09-29（P1-14）：带上源明细总数，供渲染层注明"仅列示前 N 笔"
            paragraphs[0]["detail_table"] = {"columns": detail_cols, "rows": detail_rows,
                                             "rows_total": detail_total}
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


# 结构/枚举字段：**不得**被模糊词替换（闸门与前端枚举值依赖它们）
_ENUM_KEYS_PROTECTED = frozenset({
    "risk_level",          # 值「待核验/待核」= 降级疑点标识（闸门依赖）
    "risk_level_capped_from",
    # ★ 2026-10-06（实测事故）：`level` 是**结构化枚举字段**（`risk_levels.LEGAL_LEVELS`
    #   的成员），原先**不在**保护集里 ⇒ 被本清洗改写成「已提供同类资料」
    #   （实测 `tiers[].level` 变成非等级词，`counts.by_level` 的键也随之对不上实际值，
    #     自检报「等级「已列明」报告 2 项、实际 0 项」）。
    #   违反铁律「结构性枚举字段不得被当展示文本替换」—— 展示写法在渲染层翻译。
    "level",
    "conclusion_grade",
    "code", "key", "id", "trace_id", "redline_id", "seq", "级别", "等级",
    # ★★ 2026-10-15（同一事故第三次出血，用户裁定后浮现）：等级呈现新增的两个**结构化**
    #   字段未登记保护集 ⇒ 其值「待核验」被 `_scrub_out_vague` 改写成展述词
    #   「已提供同类资料」⇒ 导出报告「风险总览」的等级表把 2 项印成「已提供同类资料」
    #   （既不是等级、也不是展示词），且 `risk_service.stats` 按它统计必然错档。
    #   铁律：**结构性枚举字段不得被当展示文本替换**，展示写法一律在渲染层翻译。
    "detected_risk_level", "risk_level_capped_by_grade_from",
})


def _drop_empty_tables(obj):
    """剔除**空白表格**（就地 + 返回新结构）：无表头 / 无数据 / 行全空 的表一律不挂。

    ★★ 2026-10-06（用户第 1 批 4.1.4：「页面中出现的所有异常空白表格……应该删除或修复」）：
      实测文档里存在 **69×6 与 27×4 两张只有边框、单元格全空** 的表（表头也是空的），
      读者看到的是两张"空框"，既占页又让人以为内容丢失。
    判据（只看数据、不认表名 —— 通用）：
      · `rows` 为空；或
      · `columns` 全为空/空白（无表头）；或
      · 所有行的**所有单元格**都为空（含只含空白 / `—` / `-` 的占位）。
    剔除必须**留痕**（返回剔除张数，由调用方打印），不静默吞。
    """
    if isinstance(obj, str):
        return obj
    if isinstance(obj, list):
        return [_drop_empty_tables(v) for v in obj]
    if not isinstance(obj, dict):
        return obj
    _rows = obj.get("rows")
    _is_table = isinstance(obj.get("columns"), list) and isinstance(_rows, list)
    if _is_table:
        _cols = [str(c) for c in (obj.get("columns") or [])]
        if not _rows or not any(c.strip() for c in _cols):
            obj["_drop_empty_table"] = True
            return obj
        _blank = True
        for _r in _rows:
            if not isinstance(_r, dict):
                continue
            for _v in _r.values():
                _s = str(_v if _v is not None else "").strip().strip("—－-– ")
                if _s:
                    _blank = False
                    break
            if not _blank:
                break
        if _blank:
            obj["_drop_empty_table"] = True
            return obj
        # ★★ 2026-10-06（用户第 2 批 AC7「**无合计0表**」）：
        #   **金额列全为 0/空 ⇒ 该表零信息量**，渲染出来只有"金额 0.00"。
        #   实测：「同一供应商同品名单价不一致（共5笔）」5 行金额合计 0.00 —— 既无信息量，
        #   又与所属疑点（文化事业建设费）无关（用户已指出应删）。
        #   判据：表内**含金额/合计字样的列**，其全部取值都是 0 / 空 / `—` ⇒ 整表不挂。
        #   ⚠ 只在"有金额列"时判（纯文本表不受影响），且**留痕**（由调用方打印张数）。
        _money_cols = [c for c in _cols
                       if ("金额" in c or "合计" in c or "税额" in c or "价税" in c)]
        if _money_cols:
            _nonzero = False
            for _r in _rows:
                if not isinstance(_r, dict):
                    continue
                for _c in _money_cols:
                    _s = str(_r.get(_c) if _r.get(_c) is not None else "").strip().strip("—－-– ¥￥,元 ")
                    if _s and _s not in ("0", "0.0", "0.00", "0.000"):
                        try:
                            if abs(float(_s.replace(",", ""))) > 0:
                                _nonzero = True
                                break
                        except ValueError:
                            _nonzero = True      # 非数字但有内容 ⇒ 不算"零值表"
                            break
                if _nonzero:
                    break
            if not _nonzero:
                obj["_drop_empty_table"] = True
                return obj
    for _k in list(obj.keys()):
        obj[_k] = _drop_empty_tables(obj[_k])
    return obj


def _purge_flagged_tables(obj, _counter=None):
    """把 `_drop_empty_tables` 打过标的表从列表里真正删掉（并计数）。"""
    if _counter is None:
        _counter = [0]
    if isinstance(obj, str):
        return obj
    if isinstance(obj, list):
        _kept = []
        for _v in obj:
            if isinstance(_v, dict) and _v.get("_drop_empty_table"):
                _counter[0] += 1
                continue
            _kept.append(_purge_flagged_tables(_v, _counter))
        return _kept
    if isinstance(obj, dict):
        for _k in list(obj.keys()):
            obj[_k] = _purge_flagged_tables(obj[_k], _counter)
        return obj
    return obj


# ══════════════════════════════════════════════════════════════════════════════
# ★ 2026-10-07（第 6 批 全量回归 第 3/7/8/10 项）：**统一收口后处理**
#   三件事都在"报告已组装、计数定稿之前"一次做完（唯一收口点，避免多处各改一遍）：
#   ① 明细表**主题不符** ⇒ 移出本项（用户第 6 批 第3项：本项主题是"人数不符"，
#      不应夹带"社保低基数"的逐人明细 —— 那是另一风险维度）；
#   ② **组合项**（由同族合并而来、带 family_members）若定为高风险，
#      必须写明**独立依据**（用户第 6 批 第8项：组合项不再单独定高风险）；
#   ③ **模板句去重**：要件核对结论句与结论句在不同事项间会**逐字相同**
#      ⇒ 各自带上本项主题/名称后再渲染（既消除逐字重复，也提高信息量）。
# ══════════════════════════════════════════════════════════════════════════════

#: 明细表**子主题**判据（★ 唯一权威：新增一类只加一行）。
#:   (表标题关键词, 该表所属子主题) —— 表主题 ≠ 本项主题时，该表移出本项。
_TABLE_SUBTOPIC = (
    ("低基数", "社保低基数"),
    ("基数占工资", "社保低基数"),
    ("名册有", "人数不符"),
    ("参保无", "人数不符"),
    ("人数", "人数不符"),
)

#: 本项**主题**判据（事项标题关键词 → 主题）
_PROBLEM_TOPIC = (
    ("人数与社保参保人数不符", "人数不符"),
    ("人数不符", "人数不符"),
)

#: 模板句前缀（★ 唯一权威：新增一句只加一行）；命中即插入本项标识以消除逐字重复
_TEMPLATE_PREFIXES = (
    # ★ 2026-10-07：「经核对，本企业**未涉及任何一条构成要件**」已下线（触发条件与认定要件分离后
    #   该句不再产出）——按"旧实现删净"纪律一并移除，避免它继续参与模板句去重匹配。
    "认定要件共",
    "本项因触发条件",
    # ★★ 2026-10-08（P0-2 第 4 处收口）：旧字面量「本项属**已查明的风险**」已**下线**
    #   （含定性词"已查明"，改由 `conclusion_grade.pending_clue_phrase` 生成结论用语）
    #   ⇒ 按"旧实现删净"纪律移除本行，改登记**证据边界声明**——它是新的
    #   "通用口径逐项复述"载体（`report_wording.EVIDENCE_BOUNDARY_CLAUSE`，唯一权威）。
    _EVIDENCE_BOUNDARY,
    # ★★ 2026-10-08（P0-3 根因治理）：下列两条是**通用补件流程句**，逐项复述逐字相同
    #   （实测：R8「附加税费」项与 R5「税前扣除限额」项补件步骤 jaccard=0.649≥0.62 被判冗余；
    #   `_p3` 补料句 jaccard=0.625≥0.62）。二者均**无项内实体含义**（材料名才是差异），
    #   属"通用口径逐项复述"⇒ 按本表机制差异化（命中处插入本项标识）。
    "第一，确认已提供的",
    "本项要定性为成立还是不成立，须先把材料补齐",
)
#: 容忍空白/换行的模板句正则（★ 实测：模板句在原文里含换行，`str.find` 匹配不到，
#:   而"重复段"判定是**去空白后**比较的 ⇒ 只有容忍空白才与判定同源）
#: ⚠ 源串里写的是 `**加粗**`，而**渲染前强调标记已被剥掉** ⇒ 构正则前先去掉 `*`，
#:   否则字面量永远匹配不上（实测：3 句改了、10 处没改，重复段仍在）。
_TEMPLATE_RES = tuple(
    re.compile(r"\s*".join(re.escape(ch) for ch in _p.replace("*", "")))
    for _p in _TEMPLATE_PREFIXES
)


def _table_subtopic(title) -> str:
    t = str(title or "")
    for kw, topic in _TABLE_SUBTOPIC:
        if kw in t:
            return topic
    return ""


def _problem_topic(title) -> str:
    t = str(title or "")
    for kw, topic in _PROBLEM_TOPIC:
        if kw in t:
            return topic
    return ""


def _finalize_topics_basis_uniqueness(out: dict, problems: List[dict]) -> dict:
    """统一收口：主题不符的表移出 / 组合项补独立依据 / 模板句差异化。返回统计。"""
    stat = {"tables_moved": 0, "basis_added": 0, "sentences_diff": 0, "moved_notes": []}
    for p in problems:
        title = str(p.get("title") or "")
        topic = _problem_topic(title)
        # ① 主题不符的表移出（留痕，不静默丢）
        if topic:
            for np in (p.get("narrative_paragraphs") or []):
                if not isinstance(np, dict):
                    continue
                tbs = np.get("detail_tables")
                if not isinstance(tbs, list):
                    continue
                keep = []
                for tb in tbs:
                    if isinstance(tb, dict):
                        st = _table_subtopic(tb.get("title"))
                        if st and st != topic:
                            stat["tables_moved"] += 1
                            stat["moved_notes"].append(
                                (p.get("seq"), st, str(tb.get("title"))[:40]))
                            continue
                    keep.append(tb)
                np["detail_tables"] = keep
        # ② 组合项高风险：必须写明独立依据；没有就降级为「按子项最高等级」
        if p.get("family_members") and str(p.get("risk_level")) == "高风险":
            basis = str(p.get("risk_level_basis") or "")
            if ("独立" not in basis) and ("组合" not in basis) and ("联动" not in basis):
                p["risk_level_basis"] = (
                    "本项为**组合项**（由同族/联动子项合并而来），其等级**不直接继承子项**；"
                    "本项定为高风险，依据是**多条独立线索同时指向同一结论**"
                    "（收入、票账差异、资金三线互相印证），且各线均有独立数据源支撑。"
                    "如其中任一线索被企业举证排除，本项等级应相应下调。")
                stat["basis_added"] += 1
        # ③ 模板句差异化
        short = title[:18] or "本项"

        def _de_set(s_: str) -> str:
            return s_.replace("*", "")

        def _de_index(s_: str, i_de: int) -> int:
            """把"去强调串"里的位置映射回原串位置（`*` 只被删除，不改变其余字符顺序）。"""
            n = 0
            for pos, ch in enumerate(s_):
                if ch == "*":
                    continue
                if n == i_de:
                    return pos
                n += 1
            return len(s_)

        def _diff(v):
            """命中模板句 ⇒ 在**该句出现处**插入本项标识。

            ★ 两个实测坑（都在这里踩过）：
              ① 只判 `startswith` 会漏"前面还有引导语"的串 ⇒ 改为**包含即命中**；
              ② 模板句的 `**` 强调符**有的被渲染剥掉、有的保留** ⇒ 两边都**去强调**后匹配，
                 再把位置映射回原文插入（否则字面量永远匹配不上，重复段留在报告里）。
            """
            if not isinstance(v, str) or "本项（" in v[:12]:
                return v, 0
            v_de = _de_set(v)
            for rx in _TEMPLATE_RES:
                m = rx.search(v_de)
                if m:
                    i = _de_index(v, m.start())
                    return v[:i] + "本项（%s）：" % short + v[i:], 1
            return v, 0

        for np in (p.get("narrative_paragraphs") or []):
            if not isinstance(np, dict):
                continue
            for k in ("text", "tail"):
                nv, n = _diff(np.get(k))
                if n:
                    np[k] = nv
                    stat["sentences_diff"] += n
            bl = np.get("bullets")
            if isinstance(bl, list):
                for i, b in enumerate(bl):
                    nv, n = _diff(b)
                    if n:
                        bl[i] = nv
                        stat["sentences_diff"] += n
        # ★★ 2026-10-08（P0-3 根因治理）：`suggestion`（处理建议＝通用补件步骤）与
        #   `narrative_paragraphs` 同属"模板句逐项复述"的载体；实测跨项 jaccard=0.649≥0.62、
        #   被 `dedup_pipeline.duplicate_rate` 判为冗余 ⇒ 一并纳入差异化（复用同一 `_diff`，不另立实现）。
        #   ⚠ `verdict` / `tax_impact.note` 属**标准化用语**（非通用流程句），不在此列——它们
        #     逐项各陈述一次本项结论/量化状态属语义必需，已登记入
        #     `config/dedup_rules.json::necessary_repeat.patterns`。
        nv, n = _diff(p.get("suggestion"))
        if n:
            p["suggestion"] = nv
            stat["sentences_diff"] += n
    return stat


def _finalize_trigger_determination(out: dict, problems: List[dict], report_data: dict) -> dict:
    """定稿收口：为每个疑点产出**触发条件/认定要件分离**的结构化块（唯一调用点）。

    ★ 用户规格【输出】字段（**已由唯一权威 `trigger_conditions.classify()` 一次产出**）：
      `risk_code / trigger_conditions / trigger_status / determination_criteria /
       criterion_status / suspicion_established（疑点是否成立）/ risk_established（风险是否成立）/
       conclusion（结论表述）`。
    ⚠ 之前这些只**渲染成报告里的一段话**，产物里没有结构化数据 ⇒ 前端/门禁/下游无法按字段消费、
      也无法机检"疑点成立 ⇔ 触发条件命中"（本项目 Skill 6/7 都踩过同一坑）。
    """
    stat = {"built": 0, "skipped": 0, "no_trigger": 0}
    try:
        from engine.trigger_conditions import classify as _classify
        from engine.constituent_checkpoint import build_constituent_checkpoints as _bcc
    except Exception as exc:                    # noqa: BLE001 - 留痕，不静默
        return {"built": 0, "skipped": 0, "no_trigger": 0,
                "error": "无法导入触发条件权威：%s" % str(exc)[:120]}
    # 疑点对象索引（与 Skill 7 同口径；唯一位置见 `_finalize_data_source_status`）
    _sus = (((report_data.get("comprehensive") or {}).get("redline_detection") or {})
            .get("suspicions")) or report_data.get("suspicions") or []
    idx: Dict[str, dict] = {}
    for s in (_sus or []):
        if not isinstance(s, dict):
            continue
        for k in (str(s.get("redline_id") or ""), str(s.get("rule_id") or ""),
                  str(s.get("title") or "")):
            if k and k not in idx:
                idx[k] = s
    try:
        from engine.enterprise_report import _not_required_docs as _nrd  # noqa: PLC0415
    except Exception:                           # noqa: BLE001
        _nrd = None
    for p in problems:
        if not isinstance(p, dict):
            continue
        key = ""
        for k in (str(p.get("redline_id") or ""), str(p.get("rule_id") or ""),
                  str(p.get("title") or "")):
            if k and k in idx:
                key = k
                break
        # 触发**读数**（留痕用）：取本项首条「核对证据：…」（即触发该疑点的现象读数）
        _reading = ""
        for np_ in (p.get("narrative_paragraphs") or []):
            for b in (np_.get("bullets") or []):
                _s = str(b or "")
                _i = _s.find("核对证据：")
                if _i >= 0:
                    _reading = _s[_i + len("核对证据："):].split("）")[0][:120]
                    break
            if _reading:
                break
        s = idx.get(key)
        if s is None:
            # ★ 无绑定疑点对象（综合画像 / 独立发现，实测 3 个）⇒ **仍按规格落块**：
            #   触发条件用本项标题兜底（与门禁"不得已列为疑点却无触发源"同口径），
            #   认定要件为空（它们不是按红线要件判定的）⇒ `risk_established=False`。
            try:
                _blk2 = _classify(key or str(p.get("title") or ""), [], [], reading=_reading,
                                  listed=True, fallback_desc=str(p.get("title") or ""))
                # 规范键回填：靠 `aliases` 命中的登记条目 ⇒ `risk_code` 用登记键
                # （VR012 / VR019 / SYN-MULTI-TAX-PROFILE），而不是标题
                try:
                    from engine.trigger_conditions import risk_entry as _re2
                    _e2 = _re2(key or str(p.get("title") or "")) or {}
                    if _e2.get("risk_code"):
                        _blk2["risk_code"] = str(_e2["risk_code"])
                except Exception:           # noqa: BLE001 - 取不到就保留原标题（如实）
                    pass
                p["trigger_determination"] = _blk2
                stat["built"] += 1
                stat["unbound"] = int(stat.get("unbound") or 0) + 1
            except Exception as exc:            # noqa: BLE001 - 留痕，不静默
                stat["skipped"] += 1
                try:
                    _note(out, "[触发条件] 兜底块生成失败(%s)：%s" % (key[:24], str(exc)[:100]))
                except Exception:
                    pass
            continue
        _na = None
        if _nrd is not None:
            try:
                _na = _nrd(((report_data.get("target_entity") or {}).get("industry")))[0]
            except Exception:                   # noqa: BLE001
                _na = None
        try:
            cps = _bcc(s, not_required=_na)
        except Exception as exc:                # noqa: BLE001 - 留痕，不静默
            stat["skipped"] += 1
            try:
                _note(out, "[触发条件] 要件核对重建失败(%s)：%s" % (key[:24], str(exc)[:100]))
            except Exception:
                pass
            continue
        try:
            blk = _classify(key, cps, s.get("constituents") or [], reading=_reading,
                            listed=True, fallback_desc=str(p.get("title") or ""))
        except Exception as exc:                # noqa: BLE001 - 留痕，不静默
            stat["skipped"] += 1
            try:
                _note(out, "[触发条件] 结构化块生成失败(%s)：%s" % (key[:24], str(exc)[:100]))
            except Exception:
                pass
            continue
        p["trigger_determination"] = blk
        # ★ 2026-10-07：`risk_code` 必须是**登记表里的规范键**。
        #   有 3 个疑点既无红线编号也无规则编号（实测 seq=2/10/11），报告层的绑定键只能取
        #   **完整标题**（靠配置 `aliases` 命中登记条目）⇒ 若直接回写标题，
        #   `risk_code` 就不像"风险编码"了。此处回填登记表里的规范键（VR012 / VR019 /
        #   SYN-MULTI-TAX-PROFILE），与门禁/报告口径一致。
        try:
            from engine.trigger_conditions import risk_entry as _re
            _ent = _re(key) or {}
            if _ent.get("risk_code"):
                blk["risk_code"] = str(_ent["risk_code"])
        except Exception:                   # noqa: BLE001 - 取不到就保留原标题（如实）
            pass
        stat["built"] += 1
        if not int((blk.get("trigger_status") or {}).get("hit_count") or 0):
            stat["no_trigger"] += 1
    return stat


def _finalize_data_source_status(out: dict, problems: List[dict], report_data: dict) -> dict:
    """定稿收口：为每个疑点产出**数据源状态表**（规格【输出】字段；唯一调用点）。

    ★ 目标（Skill 7）：消灭"数据已取得却写未取得"的同页矛盾。
      判据源与要件核对表**同一入口** `data_source_status.source_status_map(suspicion)`
      ⇒ 核对表的「数据源状态」与状态表的 `status_in_checklist` **按构造一致**；
      `status_in_detail` 则取**渲染后的明细表**（"明细表里出现了什么"是事实）。

    取不到对应疑点对象时**如实留痕并跳过**（不臆造状态）。
    """
    stat = {"built": 0, "skipped": 0, "conflicts": 0}
    try:
        from engine import data_source_status as _ds
    except Exception as exc:                    # noqa: BLE001 - 留痕，不静默
        return {"built": 0, "skipped": 0, "conflicts": 0,
                "error": "无法导入数据源状态权威：%s" % str(exc)[:120]}
    # 疑点对象索引（按红线编号 / 规则编号 / 完整标题，与其它绑定键同口径）
    #   ⚠ 疑点列表的**唯一位置**是 `report_data.comprehensive.redline_detection.suspicions`
    #     （`_build_confirmed_problems` 就用它；首版写了 `report_data["suspicions"]`，
    #      结果 16/16 全部取不到、静默跳过 —— 故此处同时兜底旧位置）。
    _sus = (((report_data.get("comprehensive") or {}).get("redline_detection") or {})
            .get("suspicions"))
    if not _sus:
        _sus = report_data.get("suspicions") or []
    idx: Dict[str, dict] = {}
    for s in (_sus or []):
        if not isinstance(s, dict):
            continue
        for k in (str(s.get("redline_id") or ""), str(s.get("rule_id") or ""),
                  str(s.get("title") or "")):
            if k and k not in idx:
                idx[k] = s
    # 工况剔除（唯一权威）
    _nr = None
    try:
        from engine.industry_resolver import not_required_materials as _nrm
        _ind = str(((out.get("identity") or {}).get("industry")) or
                   (((report_data.get("target_entity") or {}).get("industry")) or ""))
        _nr = _nrm(_ind) if _ind else None
    except Exception:                           # noqa: BLE001 - 取不到 ⇒ 不剔除（宁可多列）
        _nr = None
    for p in problems:
        if not isinstance(p, dict):
            continue
        key = ""
        for k in (str(p.get("redline_id") or ""), str(p.get("rule_id") or ""),
                  str(p.get("title") or "")):
            if k and k in idx:
                key = k
                break
        s = idx.get(key)
        if s is None:
            stat["skipped"] += 1
            continue
        try:
            tbl = _ds.table_from(p, s, not_required=_nr)
        except Exception as exc:                # noqa: BLE001 - 留痕，不静默
            stat["skipped"] += 1
            try:
                _note(out, "[数据源状态] 生成失败(%s)：%s" % (key[:24], str(exc)[:100]))
            except Exception:
                pass
            continue
        if not tbl:
            stat["skipped"] += 1
            continue
        p["data_source_status"] = tbl
        stat["built"] += 1
        stat["conflicts"] += sum(1 for r in tbl if r.get("consistency") is False)
    return stat


def _child_checklist_para(problem: dict):
    """子项清单挂到**承载构成要件/要件核对表**的那一段（唯一判据）。

    与旧实现的位置保持一致（报告第 2 段「一、涉及的风险事项」的条目列表）；
    取不到要件表时退到"首个有条目的段"，再退到首段 —— 逐级兜底、不静默丢。
    """
    paras = [x for x in (problem.get("narrative_paragraphs") or []) if isinstance(x, dict)]
    for np_ in paras:
        for t in (np_.get("detail_tables") or []):
            if isinstance(t, dict) and "构成要件" in str(t.get("title") or ""):
                return np_
    for np_ in paras:
        if isinstance(np_.get("bullets"), list) and np_["bullets"]:
            return np_
    return paras[0] if paras else None


def _finalize_child_checklist(out: dict, problems: List[dict]) -> dict:
    """定稿收口：为每个疑点产出「子项与关联项逐项核对清单」+ **结构化审计块**（唯一调用点）。

    ★ 为什么必须在**定稿之后**、且判据源必须是 `problem_texts(problem)`：
      ① 旧实现在 `_enterprise_situations()` 里生成，判据输入只有"要件 bullet"，
         而配置初值在生成器里用**整篇正文**算 ⇒ 同一子项"配置写已核对、报告写未核对"；
      ② 旧实现的 gap 里带出「配置声明为已核对」「判别性词根未命中」等**内部术语**
         （报告是给企业看的，不能出现系统内部说法）；
      ③ 必须晚于 `_remove_empty_tables()` —— 否则清单可能列举一张已被剔除的空表。
    清单文本由唯一权威 `child_item_completeness.render_child_list` 产出（单行、中文标点，
    不得含换行 —— 报告把换行渲染成「 ， 」，实测出现过像乱码的段落）。

    ★ 2026-10-07（对齐用户规格【输出】字段）：同时把**结构化审计块**写进本项
      （`child_item_audit`）：`parent_risk_code / child_items / child_status /
      child_conclusion / child_gap / related_items / related_analysis`。
      **文本与结构由 `audit_for_problem()` 一次算出** —— 结构上不可能出现"清单写未核对、
      结构写已核对"的两张皮（门禁另有断言）。
    """
    stat = {"listed": 0, "failed": 0, "audited": 0}
    try:
        from engine.child_item_completeness import audit_for_problem as _audit_p
    except Exception as exc:                      # noqa: BLE001 - 留痕，不静默
        return {"listed": 0, "failed": 1, "audited": 0,
                "error": "无法导入子项权威模块：%s" % str(exc)[:120]}
    for p in problems:
        if not isinstance(p, dict):
            continue
        try:
            audit_blk, txt = _audit_p(p)
        except Exception as exc:                   # noqa: BLE001 - 留痕，不静默
            stat["failed"] += 1
            try:
                _note(out, "[子项清单] 生成失败(%s)：%s"
                          % (p.get("redline_id") or p.get("title"), str(exc)[:100]))
            except Exception:
                pass
            continue
        if not audit_blk:
            continue
        # ① 结构化审计块（规格字段；取不到子项也照写，便于门禁判断"本项无子项"）
        p["child_item_audit"] = audit_blk
        stat["audited"] += 1
        # ② 报告文本清单
        if not txt:
            continue
        para = _child_checklist_para(p)
        if para is None:
            stat["failed"] += 1
            continue
        bl = para.get("bullets")
        if not isinstance(bl, list):
            bl = []
            para["bullets"] = bl
        bl.append(_naturalize_report_text(txt))
        stat["listed"] += 1
    return stat


def _doc_display_name() -> str:
    """报告名称（★ 唯一权威 `report_compliance.document_meta`）；取不到退回原名并可见。

    ★ 2026-10-09：兜底值从前是**字面量**「涉税风险检查工作报告（风险检查文书式）」——
      而该串正是 `config/report_identity.json` 里的 **`forbidden_aliases`（禁止别名）**。
      即：一旦合规配置取不到，报告会顶着一个**系统明令禁止的名称**出厂。
      现改为向唯一权威 `report_identity.canonical_name()` 取（该函数自带兜底、不抛异常），
      **本函数内不再有任何报告名字面量**。
    """
    nm = ""
    try:
        from engine.report_compliance import document_meta
        nm = str((document_meta("internal_working_paper") or {}).get("name") or "").strip()
    except Exception:
        nm = ""
    if not nm:
        try:
            from engine.report_identity import canonical_name
            nm = str(canonical_name() or "").strip()
        except Exception:                                # noqa: BLE001
            nm = ""
    return nm + "（风险检查文书式）"


def is_current_report_version(readable_report: Any) -> bool:
    """增量复用放行判据：这份「企业易读版报告」是否为**当前**版式（唯一权威）。

    ★ 为什么需要它（2026-10-09 对真实产物实测 + 闸门抓到，非推测）：
      原实现写在 `main.py::analyze_tax_risk_docs_start` 内，用**硬编码报告名白名单**
      判定缓存可否复用::

          _cer.get("compilation_style") in ("涉税风险检查工作报告（风险检查文书式）",
                                          "税务风险检查文书式报告",
                                          "内部税务风险检查员报告",
                                          "企业易读检查结果")

      而报告名是**可配置的**：唯一权威 `report_compliance.document_meta.name`
      =「内部辅助分析工作底稿」，经 `_doc_display_name()` 加后缀
      ⇒ 真实产出值「**内部辅助分析工作底稿（风险检查文书式）**」
      （对 `data/cache/last_analysis_cache.json` 与
      `scripts/four_reports/company_1_full.json` 实测一致）。
      更糟的是：那 4 个白名单取值**全部出自 `config/report_identity.json` 的
      `forbidden_aliases`（禁止别名表）** —— 判据只在"报告顶着禁止名称"时才可能成立。
      ⇒ `_cached_report_ok` **恒为 False** ⇒ **增量复用从未生效**，
      连同 `trigger="incremental"` 的作业流水行一起成为死路径。
      前端早已踩过同一个坑并修好（`static/js/tax-doc-analysis.js::_isEnterpriseEdition`
      「★ 删除名称白名单」）—— 后端当时**没有收敛**（同一概念、两条链路各判一次）。

    ★ 判据（**不含任何报告名字面量**，全部跟随唯一权威）：
      ① `compilation_style` 必须等于**当前**产出值 `_doc_display_name()`（改名自动跟随）；
      ② `document_meta` 必须存在（后端声明的文档定位，与前端 `_isEnterpriseEdition` 同一判据）；
      ③ `report_edition` 必须是 `audit_doctrine` 声明的**合法编辑版**。
      任一不满足 ⇒ 视为脏缓存 ⇒ 强制全量重算（**宁可多算一次，不可复用错版**）。

    ⚠ **不得**额外要求 `pyramid_edition`：它是只读派生视图，真实产物里为 `False`
      （实测）—— 要求它会让判据再次恒假，正是本函数要消灭的那个病。
    """
    if not isinstance(readable_report, dict):
        return False
    try:
        from engine.audit_doctrine import is_valid_edition
        style_ok = str(readable_report.get("compilation_style") or "") == _doc_display_name()
    except Exception:                                    # noqa: BLE001
        return False
    dm = readable_report.get("document_meta")
    has_dm = isinstance(dm, dict) and bool(dm.get("name") or dm.get("edition_kind"))
    return bool(style_ok and has_dm and is_valid_edition(readable_report.get("report_edition")))


def _attach_compliance_to_readable(out: dict, report_data: dict) -> None:
    """把合规要素**挂到报告成品对象**上（docx 导出消费的就是它）。

    第 5 批的合规能力此前只到 `report_data`，导出链路读 `enterprise_readable_report`
    ⇒ 名称/签名栏/保密/授权/系统标识/申辩**在 docx 中全部不可见**（质检实测各 0 次）。
    """
    try:
        from engine.report_compliance import compliance_block, compliance_text
        signers = dict((report_data or {}).get("report_signers") or {})
        reviewed = (report_data or {}).get("report_reviewed")
        blk = compliance_block("internal_working_paper", signers, reviewed)
        out["compliance"] = blk
        out["compliance_text"] = compliance_text(blk)
        out["document_meta"] = blk.get("document") or {}
        out["signature_block"] = blk.get("signatures") or {}
        out["security"] = blk.get("security") or {}
        out["authorization"] = blk.get("authorization") or {}
        out["system_block"] = blk.get("system") or {}
        out["feedback"] = blk.get("feedback") or {}
    except Exception as _c_exc:  # noqa: BLE001
        out["compliance_unavailable"] = str(_c_exc)[:160]


def _sync_item_counts(out: dict, problems: list) -> dict:
    """★ 2026-10-07（质检 P0-1）：把**全文的事项数声明**统一到定稿列表。

    事故：报告第 1 页写 16 项，而正文仍有「确认26项…」「全部26项…」「检查 26 项」
    （`len(problems)` 取的是**同族合并/编号定稿之前**的列表；`narrative_fresh` 的模板句
    已把旧数字烤进文本）⇒ 同一报告两套计数口径。

    ★ 为什么只改这三处而不是全文正文字符串替换：全文替换会误伤"含 12 项（明细见下表）"
      这类**聚合行数**（那是另一回事）。所以只同步**报告级计数声明**。
    """
    import re as _re
    n = len(problems or [])
    stat = {"fixed": 0}
    _pats = (
        _re.compile(r"确认\s*\d+\s*项"),
        _re.compile(r"全部\s*\d+\s*项"),
        _re.compile(r"检查\s*\d+\s*项"),
    )

    def _fix(txt):
        t = str(txt or "")
        for rx in _pats:
            m = rx.search(t)
            if not m:
                continue
            key = rx.pattern[0:2]
            word = "确认" if "确认" in m.group(0) else ("全部" if "全部" in m.group(0) else "检查")
            new = "%s %d 项" % (word, n) if word == "检查" else "%s%d项" % (word, n)
            if m.group(0) != new:
                t = t[:m.start()] + new + t[m.end():]
                stat["fixed"] += 1
        return t

    for key in ("discovery_overview", "inspection_overview", "summary", "overall_conclusion"):
        v = out.get(key)
        if isinstance(v, dict):
            for k2 in list(v.keys()):
                if isinstance(v[k2], str):
                    v[k2] = _fix(v[k2])
        elif isinstance(v, str):
            out[key] = _fix(v)
    sc = out.get("subject_consistency_audit")
    if isinstance(sc, dict) and isinstance(sc.get("summary_line"), str):
        sc["summary_line"] = _fix(sc["summary_line"])
    # 报告级共性声明
    if isinstance(out.get("common_statements"), list):
        out["common_statements"] = [_fix(x) for x in out["common_statements"]]
    return stat



def _remove_empty_tables(root):
    """一步到位：标记 + 真删，返回 (新结构, 删除张数)。"""
    _marked = _drop_empty_tables(root)
    _cnt = [0]
    _out = _purge_flagged_tables(_marked, _cnt)
    return _out, _cnt[0]


def _scrub_out_vague(obj):
    """**就地**替换掉禁用模糊词（唯一权威 `engine.report_wording.scrub_vague`）。

    ★ 2026-10-05（用户：「报告永远不能出现尚需核实」）：词表在 `report_wording`，
      本函数只负责"遍历到每一处文本"。
    ★★ 2026-10-06（**"注释说 A、代码做 B"**，实测事故）：本函数原先是**递归**实现，
      且带 `if _depth > 12: return` 的**深度上限**——注释写的是"必须**深递归**：
      藏在任意深度，只处理顶层必然漏"，代码却在第 12 层**静默停止**
      ⇒ `resolution_ledger` / `working_paper_report` 等深层块**从未被清洗**
      （实测产物里「两者均为尚需核实事实」整块幸存，共 225 处）。
      ⇒ 改为**迭代 + `id()` 去环**（复用既有权威 `plain_language.walk_strings_inplace`），
         **无深度上限**；这同时符合项目铁律"遍历 report_data 必须迭代+去环，禁递归"。
      结构性枚举字段（`_ENUM_KEYS_PROTECTED`）仍原样保留（渲染层翻译，数据层不动）。
    """
    if not isinstance(obj, (dict, list)):
        return obj
    try:
        from engine.report_wording import scrub_vague as _scrub
        from engine.plain_language import walk_strings_inplace as _walk
    except Exception:  # noqa: BLE001 —— 词表不可用时保持原样，不因措辞丢报告
        return obj

    def _fn(v, key_ctx=None):
        # 机器标识字段：原样保留（闸门与前端枚举依赖它）
        if isinstance(key_ctx, str) and key_ctx in _ENUM_KEYS_PROTECTED:
            return v
        _nv = _scrub(v)
        if _nv != v:
            _scrub_out_vague.scrubbed += 1        # 留痕：改了但看不出生效＝事故
        return _nv

    return _walk(obj, _fn)


#: 清洗计数（供报告构建末尾打印留痕：**"清洗跑没跑、改了几处"必须可见**）
_scrub_out_vague.scrubbed = 0


def _strip_markup_out(obj):
    """终局收口：**整份报告**的文本一律不得含 markdown 标记（唯一调用点）。

    ★ 为什么必须全局（2026-10-07 实测事故）：
      `_naturalize_report_text` 里**有**去星号规则，但它只在**疑点段落构造路径**上被调用；
      `tax_impact_summary.note`（18 处）、`risk_level_basis`、`related_analyses[].data`、
      要件/触发情况文本**没走到它** ⇒ 星号直通前端：产物 `**` **120 处**、
      **渲染到网页上 73 处**，企业会看到「② 增值税部分**未考虑**进项留抵…故为**上界**。」
      项目里早有这条规则，只是**局部**（`test_bank_nature` / `test_overall_conclusion` /
      `test_self_doubt` 各自断言自己那块），漏掉的容器没人管 ⇒ 收口到一处、全局跑一遍。

    机器标识字段（`_ENUM_KEYS_PROTECTED`）原样保留（前端枚举依赖它）；
    规则本体 = 唯一权威 `engine.text_guardrails.strip_markup`（幂等，可重复执行）。
    """
    if not isinstance(obj, (dict, list)):
        return obj
    try:
        from engine.text_guardrails import strip_markup as _strip_md
        from engine.plain_language import walk_strings_inplace as _walk
    except Exception:                     # noqa: BLE001 - 护栏不可用时保持原样，不因标记丢报告
        return obj
    counter = {"n": 0}

    def _fn(v, key_ctx=None):
        if isinstance(key_ctx, str) and key_ctx in _ENUM_KEYS_PROTECTED:
            return v
        nv = _strip_md(v)
        if nv != v:
            counter["n"] += 1
        return nv

    out = _walk(obj, _fn)
    _strip_markup_out.stripped = counter["n"]
    return out


#: 去标记计数（留痕用）
_strip_markup_out.stripped = 0


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
    #    ⚠ 实测事故（2026-10-07）：旧判据 `\[(?:系统|已核)[^\]]{0,200}?\]` 会把子项清单的
    #      **状态标记「[已核对]」整块吃掉**（"已核"+"对"+"］"），报告里只剩一个空格
    #      ⇒ 子项清单「[已核对] 分项扣除限额测算」渲染成「 分项扣除限额测算」。
    #      收紧为「系统…」或「已核+实/查/比」，"[已核对]" 不再命中。
    s = _re.sub(r"\[(?:系统|已核[实查比])[^\]]{0,200}?\]", "", s)
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
    # ★★ 2026-10-07（实测事故：报告里出现「： ， 毛利率…」这种像乱码的片段）：
    #   旧实现是 `s.replace("·", "，")` —— **不吃两侧空白**。而 `· ` 前的换行已被
    #   `plain_language.to_plain` 折成空格（`re.sub(r"\s+", " ", …)`），于是
    #   「…基准（行业口径：…）：\n· 毛利率…」变成「…）： ， 毛利率…」（空+逗号+空）。
    #   修法两步：① 连两侧空白一起吃；② 若圆点紧跟在**句读/冒号**之后（本项目 100% 是
    #   「标题：」+ 列表项），逗号是多余的，直接去掉圆点 —— 得到「…）：毛利率…」。
    s = _re.sub(r"\s*·\s*(?=[：:。；，、\n])", "", s)
    s = _re.sub(r"([：:。；，、])\s*·\s*", r"\1", s)
    s = _re.sub(r"\s*·\s*", "，", s)
    # 11.5 箭头：查证路径与流程本是并列关系，改成顿号
    s = s.replace("→", "、")
    s = s.replace("<-", "来自")
    # 11.6 markdown 强调与标题井号：正文里一律去掉。
    #   ★ 规则本体已收敛到**唯一权威** `engine.text_guardrails.strip_markup`
    #     （2026-10-07：该规则原本只在本函数里生效，导致只走本函数的串被清理、
    #      `tax_impact_summary.note` 等**没走本函数**的串带着 `**` 直通前端 ⇒
    #      产物 120 处、页面 73 处。现由终局收口 `_strip_markup_out()` 对整份报告统一执行。）
    try:
        from engine.text_guardrails import strip_markup as _strip_md
        s = _strip_md(s)
    except Exception:                     # noqa: BLE001 - 留痕：护栏不可用时保留原串，不丢内容
        s = _re.sub(r"\*{2,3}([^*\n]{1,40})\*{2,3}", r"\1", s)
        s = _re.sub(r"\*{2,}", "", s)
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


def _enterprise_situations(arg, clue, cap=8, constituents=None, checkpoints=None,
                           redline_id=None):
    """section 一「涉及的风险事项」bullets 的**单一权威**产出函数。

    返回 (条目列表, 来源, 要件核对表)：  # ★ 2026-10-03：契约统一为 3 元组（旧文档写 2、实际多分支返回 3）
      - 有抽象构成要件（_cons 非空）：
          · 有逐条命中（constituent_hits）→ 返回**合并清单**：先一行"本企业涉及上述第 X 条
            构成要件，已核对到的情况见各条括号内标注"，再逐条列出全部抽象要件，命中的在
            括号内标注"本企业：证据"（来源 'constituents'）；
          · 无命中（未取得逐条判定数据）→ 列出全部抽象要件 + 一句说明（来源 'constituents_no_hit'）。
      - 无抽象构成要件（不应发生，91 条红线均≥3 条）→ 回退到本企业**已核对到的具体事实**
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
    # ★ 2026-09-29（点评整改 P0-5 深层）：**要件级独立核对**优先。
    #   点评验收标准：「每要件独立 checkpoint（独立数据源 + 独立结论）；无独立证据显示
    #   '未单独核对'且**不计入**「涉及第X条要件」」。核对记录由 `constituent_checkpoint`
    #   按**红线自身定义**逐要件生成（数据源按语义匹配、匹配不上则如实写"未定义"），
    #   只有结论为 `checked_hit` 的要件才计入「涉及」—— 这是"不计入"的硬保证。
    _cps = [c for c in (checkpoints or []) if isinstance(c, dict)]
    if _cps:
        try:
            from engine.constituent_checkpoint import (
                checkpoint_table as _ctbl, participating_indices as _pind,
                summarize as _csum,
            )
            # ★ 2026-10-03：传入红线编号 —— 参与认定须过「要件组合逻辑」
            #   （只有指标现象成立时不得计入"涉及要件"，详见 constituent_checkpoint.redline_verdict_rule）
            _part = _pind(_cps, redline_id)
            _marks = "".join(_circled[i - 1] for i in _part if 1 <= i <= len(_circled))
            # ★★ 2026-10-03（用户复核疑点2）：空集合**不得渲染成「第 无 条」**（病句）。
            #   实测原文「经核对，本企业涉及上述第 无 条构成要件」——读者一眼看出是病句。
            # ★★ 2026-10-07（触发条件与认定要件分离）—— 取代"涉及/未涉及构成要件"的二分。
            #   病句：前提条已判「符合情形」、其余要件待核实时，此处仍输出
            #   「经核对，本企业**未涉及任何一条构成要件**」—— 与同段"符合情形 1 条"**自相矛盾**
            #   （用户 4 条验收：疑点1/3/4/12 第1条必须写"符合情形"，且全文不得出现该病句）。
            #   现统一由唯一权威 `trigger_conditions.verdict_sentence` 产出：
            #     本项因触发条件X而列为疑点 → 认定要件共N条已满足M条待核实K条 → 疑点成立/风险待定。
            _head = ""
            try:
                from engine.trigger_conditions import verdict_sentence as _vs
                _head = _vs(_cps, risk_code=redline_id) or ""
            except Exception as _vse:          # noqa: BLE001 - 留痕，不静默
                _note(out if isinstance(out, dict) else {}, "[结论句] verdict_sentence 失败: %s" % _vse)
            if not _head:
                # 兜底（唯一权威取不到时）：保留可读句，但**不得**再输出"未涉及任何一条构成要件"
                _head = ("经核对，本项认定要件共 %d 条：已单独核对且符合情形 %d 条，"
                         "其余待核实（详见下列逐条核对）。"
                         % (len(_cps), sum(1 for _c in _cps if _c.get("_conclusion") == "checked_hit")))
            _head += _csum(_cps)
            out = [_naturalize_report_text(_head)]

            # ★★ 2026-10-07（子项与关联项完整性 · 第 2 版）：**子项清单已迁到"定稿收口"阶段**。
            #   为什么必须迁（实测事故）：清单在这里生成时，判据输入只有"要件 bullet"，
            #   而配置初值是在生成器里用**整篇正文**算的 ⇒ 同一子项"配置写已核对、
            #   报告写未核对"，gap 文案里还带出"配置声明/判别性词根"这类企业看不懂的内部术语。
            #   现由 `_finalize_child_checklist()` 在**列表定稿之后**统一产出，
            #   判据源唯一权威 `child_item_completeness.problem_texts(problem)`
            #   —— 与生成器初值**同一份输入**（见该模块头部 ④）。
            for cp in _cps:
                _mk = _circled[cp["index"] - 1] if 1 <= cp["index"] <= len(_circled) else "第%d条" % cp["index"]
                _tail = ("（%s；独立数据源：%s｜%s）"
                         % (cp.get("核对结论"), cp.get("独立数据源"), cp.get("数据源状态")))
                # ★★ 2026-10-04（用户复核疑点5 D2）：**要件里混进的"另一类风险"必须当场声明**。
                #   事故：RL-CIT-007 第③条要件是「关联方债资比 2:1」（资本弱化），与本项
                #   "费用扣除限额"主题不同，却平铺在要件表里 ⇒ 读者以为本企业同时存在该问题。
                #   数据表 `_REDLINE_OFFTOPIC_CONSTITUENTS` 驱动（新增同类只加一行）；不隐藏、不改事实。
                _ot = ((_REDLINE_OFFTOPIC_CONSTITUENTS.get(str(redline_id or "")) or {})
                       .get(int(cp.get("index") or 0)))
                if _ot:
                    _tail = _tail[:-1] + "；【与本项主题不同】%s）" % _ot
                if cp.get("证据") and cp.get("_conclusion") == "checked_hit":
                    # ★★ 2026-10-03（用户复核：证据被截成"…相差 ）"，括号不闭合）：
                    #   旧实现 `str(...)[:120]` 是**硬切片** —— 没有省略号、还会把括号切掉，
                    #   读者看到的是断句 + 孤立括号（实测"与 7,035,008.58 元相差 ）"）。
                    #   铁律：截断必须可见（省略号是唯一信号），且括号必须配平。
                    _ev = _clamp_balanced(str(cp.get("证据")), 150)
                    _tail = _tail[:-1] + "；核对证据：%s）" % _ev
                out.append(_naturalize_report_text(("%s %s" % (_mk, cp.get("要件"))).rstrip("。；") + _tail))
            _tb = _ctbl(_cps)
            return out, "constituents_checkpointed", _tb
        except Exception:
            pass
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
            # ★ 2026-09-29（点评整改 P1-5）：**要件命中必须过阈值校验**。
            #   外部点评实测：某要件写「未付款占比超过50%」，而本企业实际 32.5%，报告仍标
            #   「涉及要件②」——要件清单（什么情形算涉嫌）与企业命中（踩了哪条）之间没有算术闭环，
            #   读者一算就发现"没到门槛也算命中"。校验逻辑收敛在
            #   `engine/constituent_threshold.py`（通用：只比同量纲；取不到实际值则放行不误杀）。
            try:
                from engine.constituent_threshold import check_constituent_hit as _cth
            except Exception:
                _cth = None
            _unmet_notes = []
            if _cth:
                for _i in list(_hit_map.keys()):
                    if not (1 <= _i <= len(_cons)):
                        continue
                    _verdict, _note = _cth(_cons[_i - 1], _hit_map[_i])
                    if _verdict == "unmet":
                        _unmet_notes.append("第%d条要件%s" % (_i, _note))
                        _hit_map.pop(_i, None)
            if _unmet_notes:
                _hit_map["_unmet_note"] = "；".join(_unmet_notes)
            if not any(isinstance(k, int) for k in _hit_map):
                # 全部命中项都未达门槛 → 不得声称"涉及"，如实写"未达门槛"
                # ★ 2026-10-03：本函数其余分支都返回 **3 元组**（条目, 来源, 要件表），
                #   这一支只返回 2 个值 ⇒ 调用方 `_sits, _sit_src, _cp_tbl = ...` 抛
                #   "not enough values to unpack" —— 任何红线走到"命中项全未达门槛"都会让
                #   报告装配整段失败（被 pytest 抓出）。补齐第 3 个返回值（无要件表 → None）。
                # ★ 2026-10-03：本函数其余分支都返回 **3 元组**（条目, 来源, 要件表），
                #   这一支只返回 2 个值 ⇒ 调用方 `_sits, _sit_src, _cp_tbl = ...` 抛
                #   "not enough values to unpack" —— 任何红线走到"命中项全未达门槛"都会让
                #   报告装配整段失败（被 pytest 抓出）。补齐第 3 个返回值（无要件表 → None）。
                return [_naturalize_report_text(
                    "经核对，本企业本轮未达到上述构成要件的数值门槛，暂不计为涉及该项："
                    + "；".join(_unmet_notes) + "。上述要件清单供对照，具体是否涉及须补资料后重新判断。"
                )], "constituents_threshold_unmet", None
            # 既有抽象要件、又有本企业命中 → 每条要件均列出，命中的在括号内标注本企业证据
            _hit_marks = "".join(_circled[i - 1] for i in sorted(k for k in _hit_map if isinstance(k, int))
                                 if 1 <= i <= len(_circled))
            # ★ 2026-09-29（点评整改 P0-5）：头句显式声明"未括注=未单独核对"，
            #   防止读者把"列出全部要件"误读为"逐条都核对过"（发现级证据只落首个命中位）。
            out = [_naturalize_report_text(
                f"经核对，本企业涉及上述第 {_hit_marks or '相关'} 条构成要件，"
                f"已核对到的情况见各条括号内标注；未括注的要件为本轮未单独核对到的构成要件，"
                f"不作为认定依据：")]
            for i, c in enumerate(_cons, 1):
                mark = _circled[i - 1] if i <= len(_circled) else f"第{i}条"
                if i in _hit_map and _hit_map[i]:
                    out.append(_naturalize_report_text(
                        f"{mark} {c}（本企业：{_hit_map[i]}）".rstrip("。；")))
                else:
                    out.append(_naturalize_report_text(f"{mark} {c}".rstrip("。；")))
            # ★ 2026-09-29（P1-5）：把"信号命中但未达数值门槛"的要件如实列出，
            #   否则读者会看到"要件列了却没标命中"而不知原因（也不让门槛校验静默生效）。
            if _hit_map.get("_unmet_note"):
                out.append(_naturalize_report_text(
                    "另有要件有信号但未达数值门槛，本轮不计为涉及：" + str(_hit_map["_unmet_note"])))
            return out, "constituents", None
        # 有抽象清单但本轮未取得逐条判定数据 → 仍列抽象清单，并说明
        return ([_naturalize_report_text(c.rstrip("。；")) for c in _cons]
                + [_naturalize_report_text(
                    "（本轮已对该红线逐条核对，尚未取得足以判定各要件的完整数据；"
                    "上列为本红线涉嫌构成要件）")]), "constituents_no_hit", None
    # —— 无抽象清单（不应发生，91 条红线均≥3 条）：回退到本企业实际核对到的事实 ——
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
    return [_naturalize_report_text(raw_items[i]) for i in keep[:cap]], "facts", None


def _clamp_balanced(text, limit):
    """截断文本但**保留可见省略号**并**配平括号**（报告正文铁律：截断必须可见）。

    ★ 2026-10-03 新增：旧代码直接用 `[:N]` 硬切片，实测把要件证据切成
    "…与 7,035,008.58 元相差 ）" —— 断句 + 孤立右括号，读者读不通。
    本函数：① 只在句子边界或空格处切；② 追加"…"；③ 补足被切掉的右括号。
    """
    s = str(text or "")
    if len(s) <= limit:
        return s
    cut = s[:limit]
    for _sep in ("。", "；", "，", "、", " "):
        _k = cut.rfind(_sep)
        if _k >= limit // 2:
            cut = cut[:_k + (1 if _sep != " " else 0)]
            break
    cut = cut.rstrip("，、；： ")
    for _pair in (("（", "）"), ("(", ")"), ("「", "」"), ("《", "》")):
        if cut.count(_pair[0]) > cut.count(_pair[1]):
            cut += _pair[1] * (cut.count(_pair[0]) - cut.count(_pair[1]))
    return cut + "…"


def _audit_note(audit_sink, code, detail, title="", redline_id=""):
    """往"疑点主体自检台账"记一条**如实说明**（唯一权威出口）。

    ★★ 2026-10-08（P0 根因治理）：**`audit_sink` 在生产路径是 dict，不是 list。**
      `build_enterprise_readable_report` 传进来的是 `{"issues": [], "by_code": {}}`，
      而本模块历史上多处写成 `audit_sink.append("...")` —— dict 没有 `append`：
        · 落在 `except` 里的 ⇒ 把**真错误**替换成 `AttributeError`，原错误信息被吞（静默降级）；
        · 落在无 try 的路径上 ⇒ **本项整段生成失败**（正属于"报告产量归零"那类事故）。
      现统一走本函数：dict 追加一条结构化 issue（与主体错配留痕同构，可被
      `_build_subject_audit` 汇总、可被闸门断言）；list 才 append 字符串。
    ⚠ 只"如实说明"，不改判定、不改事实（与 `_build_subject_audit` 的既有约定一致）。
    """
    if audit_sink is None:
        return
    _code = str(code or "报告自检")
    _detail = str(detail or "")
    if isinstance(audit_sink, dict):
        audit_sink.setdefault("issues", []).append({
            "seq": None, "title": str(title or "")[:60], "code": _code,
            "detail": _detail, "redline_id": str(redline_id or ""),
        })
        return
    try:
        audit_sink.append("[%s] %s" % (_code, _detail))
    except Exception:
        pass


def _build_redline_problems(suspicions=None, findings=None, rate_ctx=None,
                            not_required_docs=None, audit_sink=None):
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
    # ★★ 2026-10-02（用户：疑点内容与疑点主体错配，彻底修复）：
    #   **附表挂载改为"来源归属"口径**（唯一权威 `subject_consistency`）。
    #   旧版先按红线编号精确关联、未命中就用「红线名 ↔ 发现类型」的 2-gram 重叠兜底
    #   ⇒ 实测把别的发现的表挂了过来（「附加税费计税依据与增值税不匹配」拿到
    #      「增值税进项税额对等逐月不匹配」的表）。
    #   现按「这张表来自哪条发现 → 该发现是不是**本疑点自己声明的支撑发现**」判定：
    #   归属不符的表一律不挂，宁可不附明细，也不附错明细。
    # ★ 2026-10-03：按发现**类型**建索引 —— 「点→面推演」要与本疑点建入口的那条发现对齐
    #   （推演是基于"这一条读数"展开的，取错发现就会推出另一件事的解释）。
    _lateral_by_type = {}
    for _fl in (findings or []):
        if isinstance(_fl, dict) and _fl.get("lateral_reasoning"):
            _lateral_by_type[str(_fl.get("type") or "")] = _fl["lateral_reasoning"]
    _src_tables = {}          # 发现主体规范键 -> {"rid": rid, "tables": [...]}
    _owner = {}               # id(表) -> 发现主体规范键（供自检回溯来源）
    # ★★ 2026-10-08（P0-4 根因治理）：**"这张表来自哪条发现（原名）"** 也必须留索引。
    #   只留规范键不够用：判定"这张表能不能当本项的事实引子"要用
    #   `subject_consistency.same_subject(来源发现类型, 本项红线名)`，它吃的是**类型原名**。
    _owner_type = {}          # id(表) -> 来源发现的 type（原名）
    for _f in (findings or []):
        if not isinstance(_f, dict):
            continue
        # ★ 2026-10-01（用户复核疑点2 实测）：**资料缺失类发现不得进下钻表索引**。
        #   这类发现的 evidence_rows 是随手样本行（如「企业所得税申报表缺失」挂 2 张
        #   与所得税无关的记账凭证），靠泛词就能挂到任意疑点名下，属张冠李戴。
        if str(_f.get("type") or "").strip().startswith("资料缺失"):
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
        # ★ 来源归属索引：以「发现主体规范键」（去期间/批次括注）为键，
        #   与疑点声明的支撑发现主体按同一函数归一，两端必然可比。
        from engine.subject_consistency import norm_subject_key as _nsk
        _skey = _nsk(_f.get("type") or "")
        if _skey and _skey not in _src_tables:
            _src_tables[_skey] = {"rid": str(_rid or ""), "tables": _tables}
        for _t in _tables:
            _owner[id(_t)] = _skey
            _owner_type[id(_t)] = str(_f.get("type") or "").strip()
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
        # ★★ 2026-10-02：本疑点声明的支撑发现主体（正文裁剪、附表归属、主体自检三处共用，
        #   只算一次，避免三处各判一次又各不相同——这正是"错配"反复出现的根因）。
        _sup_subjects = []
        for _sf in (s.get("supporting_findings") or []):
            if isinstance(_sf, dict) and str(_sf.get("type") or "").strip():
                _sup_subjects.append(str(_sf["type"]).strip())
        if str(s.get("finding_type") or "").strip():
            _sup_subjects.insert(0, str(s["finding_type"]).strip())
        rname = s.get("redline_name", "")
        grade = s.get("conclusion_grade") or arg.get("conclusion_grade") or "待核"

        # ★ 2026-09-29（点评整改 P0-6）：**标题按实际证据裁剪**。
        #   红线名是"要件包"的概括名（如 RL-CIT-004「长期亏损仍持续经营」以"亏损"
        #   为命名前提）；若本轮只证明了该红线的其它要件（如"税负贡献与规模不匹配"）
        #   却沿用全名，报告就写出与企业自身数据相矛盾的前提（实测：标题称长期亏损、
        #   同项正文净利润为正）。裁剪逻辑收敛在 `tax_redlines.trim_redline_title`
        #   （数据表驱动，新增红线只加一行）。
        #   ⚠ 必须在此处先算：p1（首段）与 p4（结论段）都要用 `_premise_note`。
        _title_raw, _premise_note = (rname.strip() or rid), ""
        try:
            from engine.tax_redlines import trim_redline_title as _trim_title
            # 发现自有名称：优先疑点自带的 finding_type，其次支撑发现的第一条 type
            # （报告标题须是"企业自有的发现名"，不是红线包名）
            _own_type = s.get("finding_type") or ""
            if not _own_type:
                for _sf in (s.get("supporting_findings") or []):
                    if isinstance(_sf, dict) and str(_sf.get("type") or "").strip():
                        _own_type = str(_sf["type"]).strip()
                        break
            _title_raw, _premise_note = _trim_title(
                rid, _own_type, arg.get("constituent_hits"), rname)
        except Exception:
            _title_raw, _premise_note = (rname.strip() or rid), ""

        # ★★ 2026-10-03（用户复核疑点2）：**上游已显式降级的发现，疑点不得再以红线名立标题**。
        #   事故：检测器已判「仅单向大额转出，不构成资金回流，不挂红线」（redline_id 已清空、
        #   降级为低风险），疑点层却仍以红线名「资金回流：付款后经个人账户回流」做标题。
        #   企业读到的是"高风险的资金回流疑点"，而引擎的结论恰恰是"不构成回流"。
        #   判据（通用）：`s["downgraded"]`（来自 `redline_engine` 落盘的 `_downgrade_reason`）
        #   ⇒ 标题改用**发现自有类型**、认定范围声明"未认定到任何一条构成要件"。
        if s.get("downgraded"):
            _own = str(s.get("finding_type") or "").strip() or "账内待核线索"
            _title_raw = "待核线索：%s" % _own
            _premise_note = ("本项未认定到任何一条构成要件，仅作尚需核实线索登记，"
                             "不按该风险指标定性；%s" % (str(s.get("downgrade_reason") or "")[:100] or ""))

        # ★★ 2026-10-02（用户：疑点内容与疑点主体错配，彻底修复）：
        #   **主体自检写进一键分析** —— 报告对自己"要写的内容"先自问一句：
        #   "本项的主体（风险指标名）与本项实际依据的发现（支撑发现）是不是同一件事？"
        #   不是 → 标题必须声明认定范围，**不得**让读者以为标题所述情形已被认定。
        #   判据唯一权威 `subject_consistency.suspicion_subject_ok`（词表+红线声明两级）。
        #   ★ 此处只"如实说明 + 记账"，不隐藏、不改事实：判定结果进 `audit_sink`，
        #     由 `build_enterprise_readable_report` 汇总进报告与流水（可复核、可回归）。
        _ok_sub = True
        # ★★ 2026-10-02（用户：疑点内容与疑点主体错配，彻底修复）：
        #   自检的**主判据是本疑点"建入口那条发现"（`finding_type`）**，而不是"支撑发现里
        #   随便有一条对得上就算过"。事故：疑点 RL-SPT-017「广告/娱乐服务未申报文化事业建设费」
        #   的 entry 是软匹配来的「同一供应商同品名单价不一致」（完全另一件事），
        #   而它名下确实还挂着一条正当的「文化事业建设费未申报（待核）」支撑发现 ——
        #   旧判据因后者命中而"通过"，标题与正文（entry 的线索链/证据链）却仍然错配。
        #   entry 决定标题之外的线索链与证据链，因此 entry 一致才算本项主体一致。
        _entry_subject = str(s.get("finding_type") or "").strip()
        _check_subjects = [_entry_subject] if _entry_subject else list(_sup_subjects)
        try:
            from engine.subject_consistency import suspicion_subject_ok as _sso
            _ok_sub, _why_sub = _sso(rname, _check_subjects, rid)
            if not _ok_sub and _entry_subject:
                # entry 与红线名不符，但**名下**确有同一主体的支撑发现 → 仍按不符处理，
                # 但说明里点明这条支撑发现，便于复核时定位。
                _ok2, _why2 = _sso(rname, _sup_subjects, rid)
                if _ok2:
                    _why_sub = ("本项建入口的发现（%s）与风险指标名不符；"
                                "名下另有相同主体的支撑发现，但正文线索/证据取自建入口那条"
                                % _entry_subject[:26])
        except Exception:
            _ok_sub, _why_sub = True, ""
        if not _check_subjects:
            # 本疑点连"依据了哪条发现"都没取到 → **无从判定**，不得当成错配报出去
            # （实测此处曾把 12 条单发现疑点全部误判为错配）。
            _ok_sub = True
        if not _ok_sub:
            # ★ 但若 `trim_redline_title` 已经声明过本项认定范围（`_premise_note` 非空），
            #   就不再叠加第二段同义声明 —— 同一件事说两遍会让报告像在自我辩解。
            #   自检留痕照记（审计不受影响），只是不再往标题里重复加括注。
            if not _premise_note:
                _clarify2 = ("本项风险指标名称与本项已读到的证据所指情形不完全对应，"
                             "本项未就该指标名称所述情形作出认定")
                _title_raw = ("%s（%s）" % (_title_raw, _clarify2))
                _premise_note = ("需要说明：本项疑点名称取自风险指标库的指标名；"
                                 "本项实际读到的证据指向的情形与该指标名所述情形不完全对应。"
                                 "本项只按实际证据范围内的事实登记和说明，"
                                 "未就该指标名称所述情形本身作出认定。")
            if isinstance(audit_sink, dict):
                audit_sink.setdefault("issues", []).append({
                    "seq": None, "title": str(_title_raw)[:60],
                    "code": "疑点主体与其证据不是同一件事", "detail": _why_sub,
                    "redline_id": rid,
                })
                audit_sink.setdefault("by_code", {})
                _k = "疑点主体与其证据不是同一件事"
                audit_sink["by_code"][_k] = audit_sink["by_code"].get(_k, 0) + 1

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
        # ★ 2026-09-26 三层术语重标：执行版不写"触碰税务红线/触碰红线成立"（易读成已定性违法），
        #   改为"触发税务风险指标（待核实）"，与决策版口径一致。
        _cons_all = [str(c).strip() for c in (s.get("constituents") or []) if str(c).strip()]
        # _enterprise_situations 是 section 一 bullets 的**单一权威**：有抽象要件时返回
        # 「抽象要件全列 + 命中项括号内标注证据」的合并清单；无抽象要件（不应发生）回退事实。
        # ★ 2026-09-29（P0-5 深层）：逐要件独立核对——每要件一条（独立数据源+独立结论）。
        #   放在标题裁剪之后、段落拼装之前：首段与"发现依据"段都要用它。
        _cps_all = []
        try:
            from engine.constituent_checkpoint import build_constituent_checkpoints as _bcc
            # ★ 2026-10-03：传入**业态不适用资料集合** —— 要件级同样剔除
            #   （服务型企业的"物流单据/入库验收单"不适用；不剔除会让要件——
            #    尤其"不属于正当情形"这类出罪要件——永远核对不了，企业无法自证清白）。
            _cps_all = _bcc(s, not_required=(not_required_docs or set()))
        except Exception:
            _cps_all = []
        _sits, _sit_src, _cp_tbl = _enterprise_situations(
            arg, clue, constituents=_cons_all, checkpoints=_cps_all, redline_id=rid)
        # ★ 2026-10-02：先无条件预置为空，供下面 p4 复用（避免在 `if _cons_all:` 里赋值、
        #   却在分支外读取的 UnboundLocalError —— 曾多次栽在"变量只在分支内赋值"上）。
        _participating: set = set()
        if _cons_all:
            # ★ 2026-10-02（用户复核疑点5：涉及第 无 条 vs 触碰红线 正面冲突）
            #   **「触发税务风险指标…涉嫌X」的触碰红线开场句，必须以「至少一条要件被认定」为前提。**
            #   旧版无条件套用，于是出现：首句「本企业触发税务风险指标……涉嫌通过关联企业转移利润、
            #   虚开发票」，下一条 bullet 却是「涉及上述第 无 条构成要件」——同一疑点内部自相矛盾。
            #   根因：触碰红线判据与要件认定是两套互不相认的口径，报告却默认它们一致。
            _participating: set = set()
            if _cps_all:
                try:
                    from engine.constituent_checkpoint import participating_indices as _pind
                    _participating = set(_pind(_cps_all, rid))
                except Exception:
                    _participating = set()
            _sig_lead = str(clue.get("terminal_signal") or "").strip()
            if not _sig_lead:
                for _sf in (s.get("supporting_findings") or []):
                    if isinstance(_sf, dict) and str(_sf.get("terminal_signal") or "").strip():
                        _sig_lead = str(_sf["terminal_signal"]).strip()
                        break
            p1 = risk_item_lead(rname, _suspect_txt, _participating, _sig_lead)
            bullets1 = _sits
        else:
            # 防御：红线未定义构成要件（不应发生，68 条均≥3 条），退回旧版单句口径
            p1 = (
                f"经检查，本企业触发税务风险指标，即{rname}，{_suspect_txt}。"
                "经核对，本企业已符合构成此项风险的涉嫌要件。"
            )
            bullets1 = _sits or None
        # ★ 2026-09-27（用户口径）：法定依据须写到**具体哪一条、什么内容**（唯一权威 legal_citation）。
        # ★ 2026-10-07（用户第 3 批 任务4「法条版本化」）：同时标注该法**现行版本**
        #   （唯一权威 engine.legal_version）：已登记 ⇒「（2023年修订；国务院令第764号，现行有效）」，
        #   未登记 ⇒「（版本未登记，须核对现行有效文本）」——**不默认按现行有效呈现**。
        try:
            from engine.legal_citation import format_legal_basis as _flb
            _legal_txt = _flb(legal, with_version=True)
        except TypeError:
            from engine.legal_citation import format_legal_basis as _flb
            _legal_txt = _flb(legal)
        except Exception:
            _legal_txt = "；".join(str(x) for x in legal)
        tail1 = _naturalize_report_text(f"法定依据：{_legal_txt}。") if _legal_txt else ""

        # ② 发现过程
        # ★★ 2026-10-05（疑点5 D6）：分项扣除限额的数字**回填**到对题环节的 observed。
        #   事故：三环都写「本环节未产出对题读数」，而同疑点的分项测算表里确实有金额
        #   （业务招待费账面 411,111.53／超限 377,927.53；广宣费 2,729,730.26／1,734,210.17）
        #   ⇒ 数据在同疑点内可回指，写「未产出」等于否定已算出的数。
        #   ⚠ 必须在此处（`_clue_narrative` 之前）：那里会把环节文本固化，之后改 nodes 无效。
        #   ⚠ 只回填**动作对题**的环节（环3「核对是否作纳税调增」其读数确实缺汇算清缴明细）。
        _lit = None
        try:
            _lit = _limit_items_table(rid, findings)
        except Exception as _e1:  # noqa: BLE001
            if isinstance(audit_sink, dict):
                audit_sink.setdefault("issues", []).append({
                    "seq": None, "title": str(_title_raw)[:60],
                    "code": "分项限额取数失败", "detail": str(_e1)[:120], "redline_id": rid,
                })
        if _lit:
            try:
                _lim_txt = "；".join(
                    "%s 账面 %s、超限 %s" % (r.get("费用项目"), r.get("账面发生额（元）"), r.get("超限金额（元）"))
                    for r in ((_lit.get("rows") or [])[:3]))
                for _nd in (clue.get("nodes") or []):
                    if not isinstance(_nd, dict):
                        continue
                    _obs5 = str(_nd.get("observed") or "")
                    if "未产出对题读数" not in _obs5:
                        continue
                    _act5 = str(_nd.get("action") or "") + str(_nd.get("output") or "")
                    if not any(_k in _act5 for _k in ("限额", "归集", "扣除", "计算", "发生额")):
                        continue
                    _nd["observed"] = "本环节读数（来自本项分项扣除限额测算）：" + _lim_txt
                    _nd["has_data"] = True
            except Exception as _e2:  # noqa: BLE001
                if isinstance(audit_sink, dict):
                    audit_sink.setdefault("issues", []).append({
                        "seq": None, "title": str(_title_raw)[:60],
                        "code": "分项限额回填失败", "detail": str(_e2)[:120], "redline_id": rid,
                    })
        chain_desc = _clue_narrative(clue, not_required=not_required_docs)
        p2 = (
            "这个疑点不是估计出来的，是从资料里一步步算出来的："
            + (chain_desc or "本轮资料不足以还原完整的发现过程。")
        )
        if clue.get("data_gaps"):
            # ★ 2026-09-29（点评整改 P0-1②）：按三态分别表述——资料缺失才"计入检查受限"；
            #   所需资料已提供但环节未产出数据的，如实写"检查程序待完善项，不计入资料缺失"，
            #   不得与第一章"已提供资料"清单自相矛盾。
            _gaps = clue.get("data_gaps", [])
            # ★ 2026-10-05（疑点2 D11 复诊）：**业态不适用单列一档**。
            #   旧口径只有"缺资料 / 非缺资料"两档 ⇒ 业态不适用被并进"程序待完善"，
            #   汇总句写"所需资料已在本轮提供"，而节点正文写"属本业态不适用"，同页矛盾。
            _na = [g for g in _gaps if g.get("reason") == "not_applicable_industry"]
            _mg = [g for g in _gaps if g.get("reason") == "material_missing"]
            _eg = [g for g in _gaps
                   if g.get("reason") not in ("material_missing", "not_applicable_industry")]
            _parts = []
            if _mg:
                _parts.append("其中" + "、".join(
                    f"第{g['step']}环" for g in _mg
                ) + "因缺少资料未取得数据，已计入检查受限范围")
            if _eg:
                # ★ 2026-10-05（疑点7 D6 收口）**"非 material_missing"不等于"资料已提供"**。
                #   事故：环节2 声明「销项发票、人员、产能数据」，只提供了销项发票，
                #   「人员/产能数据」本系统归不了类 ⇒ 旧实现把整段写成
                #   "第2环、第3环所需资料已在本轮提供、但该环节未产出可展示数据"，
                #   与同段第2环正文"尚缺…人员、产能数据"**自相矛盾**。
                #   现按 `data_gaps` 里各环节的缺口明细分口径：
                #     · 无缺口明细 ⇒ 该环节资料确已提供（可写"已提供"）
                #     · 有缺口明细   ⇒ 只说"未取到该环节所需的部分资料"（不写"已提供"）
                _eg_txt = []
                for _g in _eg:
                    _gm = [x for x in (_g.get("_gap_missing") or []) if x]
                    if _gm:
                        _eg_txt.append(
                            f"第{_g['step']}环未取到该环节所需的 " + "、".join(
                                m.split("：", 1)[-1] if str(m).startswith("无法归类") else str(m)
                                for m in _gm[:3])
                            + "，未产出可展示数据")
                    else:
                        _eg_txt.append(
                            f"第{_g['step']}环所需资料已在本轮提供、但该环节未产出可展示数据")
                _parts.append("、".join(_eg_txt)
                              + "（属检查程序待完善项，不计入资料缺失，不影响资料齐备性判断）")
            if _na:
                _parts.append("、".join(
                    f"第{g['step']}环" for g in _na
                ) + "所需资料属本业态天然不适用（企业本就不会有），不计入资料缺失，也不影响资料齐备性判断")
            if _parts:
                p2 += "；".join(_parts) + "。"

        # ③ 已有材料与待补材料
        # ★ 2026-09-25：三态须分开说。「已有」= 名称逐字对应的材料已提交；
        #   「待核」= 清单里有相关类别但未必含本项所需（不得混入"已拿到"）；
        #   「缺失」= 确未提供。旧版把"待核"也写成"已在案"，导致
        #   "企业只交了工资表"被报告写成"劳动合同等材料已在案"。
        _els = ev.get("elements") or []
        # ★★ 2026-10-03（用户复核疑点2）：三态清单**先过业态剔除**（唯一权威
        #   `industry_resolver.not_required_materials`，与 material_readiness 同一实现）。
        #   事故：服务型广告企业被列为"确未提供：物流单据与承运记录"、并被要求
        #   "取得直接证据：采购合同与入库验收单" —— 这两样它天然不会有 ⇒ 永远无法"资料齐全"。
        #   "采购合同与入库验收单" 按段剔除后保留 "采购合同"（不整项误删）。
        def _nr_el(_e):
            _n = _strip_not_required((_e or {}).get("name"), not_required_docs)
            if not _n:
                return None
            if _n == str((_e or {}).get("name") or "").strip():
                return _e
            # ★ 2026-10-05（疑点5 D11）：**写回原 element**，不再用副本 ——
            #   旧实现只在副本上重写 name，§四 读 `ev["elements"]` 仍是原名
            #   ⇒ §三/§四 元素名不同 ⇒ 同源计算也算出不同项数（D11）。
            try:
                _e["name"] = _n
            except Exception:  # noqa: BLE001
                pass
            return _e

        _els = [x for x in (_nr_el(_e) for _e in _els) if x]
        have = [e for e in _els if e.get("status") == "已有"]
        verify = [e for e in _els if e.get("status") == "待核"]
        lack = [e for e in _els if e.get("status") == "缺失"]
        # ★ 2026-10-04（疑点4 D8-①）：缺料名字先取好（`_lack_names_early`），
        #   供下面的三态计数在权威字段缺失时回落使用。
        _lack_names_early = []
        for _e7 in (lack or []):
            _n7 = _e7.get("name") if isinstance(_e7, dict) else _e7
            _n7 = str(_n7 or "").strip()
            if _n7 and _n7 not in _lack_names_early:
                _lack_names_early.append(_n7)
        # ★ 2026-09-27（用户要求）：材料齐全程度**不得用比例/百分比**表述，
        #   只表述"已有几项、还缺几项"（项数）。closure 仍内部计算（决定能否定性），
        #   但不再进入正文 —— 杜绝"材料齐全程度40%"这类比例表述。
        # ★ 2026-10-01（用户批注「定什么下来/排除什么」）：p3 重写，三条硬要求——
        #   ① 先说清**定性对象**（本项要定性为成立还是不成立）与**补料原因**（须先把材料补齐）；
        #   ② 凡报「缺 N 项」必须点出**具体资料名**（`_name_brief`），不能只有五个数字；
        #   ③ 判据说「可以作出确定性判断」时**不再追加**「暂不作定性/现有资料不足」类表述
        #      ——旧逻辑会在已能定性时仍写"暂不作定性"，自相矛盾。
        # ★★ 2026-10-04（疑点4 D8-① 修复）：**三态计数同源同单位**。
        #   事故：「需要3项」但分项 1+1+3=5 —— ①同一批 verify 被说两遍（见下）；
        #   ②「需要N项」按**元素数**、而「确未提供的K项」按**材料名原子数** ⇒ 单位不同必然对不上。
        #   修法：缺料口径提前到此处（唯一权威），三态统一按**原子数**（拆复合名 + 去重），
        #   `_need_n` 由三态**相加得出** ⇒ 恒等式由构造保证。
        _lack_auth = [str(_z9) for _z9 in (ev.get("missing_material_names") or [])
                      if str(_z9).strip()]
        if _lack_auth:
            _lack_ok = _filter_not_required(list(_lack_auth), not_required_docs)
        else:
            _lack_ok = _filter_not_required(list(_lack_names_early), not_required_docs)

        def _atoms_of(_lst):
            _out = []
            for _x9 in (_lst or []):
                _n9 = _x9.get("name") if isinstance(_x9, dict) else _x9
                for _y9 in re.split(r"[、，,；;／/]|与|和|及|以及|或", str(_n9 or "")):
                    _y9 = _y9.strip()
                    if _y9 and _y9 not in _out:
                        _out.append(_y9)
            return _out

        def _brief_atoms(_lst, _cap=6):
            """列前 _cap 个材料名；**被截断时必须显式声明总数**。
            ★ 2026-10-04（疑点4 D8 收尾）：原先一律截前 6 个且**静默**,
            读者会以为只有 6 项（实测 seq=9 声明 8 项只列 6 名）。
            ⇒ 截断即须声明「…等（共 N 项）」。
            """
            _out = "、".join(_lst[:_cap])
            if len(_lst) > _cap:
                _out += "等（共%d项）" % len(_lst)
            return _out

        _at_have = _atoms_of(have)
        _at_verify = _atoms_of(verify)
        _at_lack = _atoms_of(_lack_ok)
        _have_n = len(_at_have)
        _need_n = _have_n + len(_at_verify) + len(_at_lack)
        _p3 = "本项要定性为成立还是不成立，须先把材料补齐：本项核查需要%d项材料" % _need_n
        if have:
            _p3 += "，其中名称逐字对应、已确在手上的有%d项（%s）" % (len(_at_have), _brief_atoms(_at_have))
        if verify:
            # ★★ 2026-10-03（用户复核疑点11："本项检查需要4项材料，目前还没有一项材料与要求
            #   逐字对应"——而同一页正文正在引用序时账/销项发票/银行流水的数字）：
            #   旧文案在 have 为空时一律写"还没有一项材料与要求逐字对应"，读者会理解成
            #   "企业什么都没交"，与证据表里的"待核实（有同类资料）/缺2项"自相矛盾。
            #   事实是：**本项要求的材料名比已提供清单的类别名更细**（如要求"全部银行账户
            #   及个人账户流水"、已提供类别为"银行流水"）——属"同类资料、范围须确认"，
            #   不是"未提供"。三态各说各话，不得用一句话把"待核"吞成"没有"。
            _p3 += "，其中%d项已提供同类资料（%s）、但与本项要求的范围未逐字对应，须确认是否覆盖" % (
                len(_at_verify), _brief_atoms(_at_verify))
        else:
            _p3 += "，目前没有一项材料与本项要求对应"
        # ★ 2026-10-04（疑点4 D8-①）：原此处还有一段"另有N项（…）须确认已提供资料中是否含
        #   该内容"，与上面的 verify 段**描述同一批材料** ⇒ 同一份被数两次（"需要3项"却
        #   出现 1+1+3=5）。已删除，三态各说一次。
        # ★★ 2026-10-04（疑点3 D13 + 计数观感）：缺料文案与**结构化字段同一口径**。
        #   `lack` 是**证据元素字典列表**（元素含 name/status/role），先取名再谈其它。
        #   ① 业态剔除贯穿：`missing_materials` 已被剔除清空（服务型天然无销售台账/发货记录），
        #      文案若仍写「确未提供」⇒ 字段说没有、文案说缺 N 项，同一页自相矛盾。
        #   ② 计数观感：复合名（含两项）按 `len(lack)` 只算 1 项 ⇒ 声明数与列出的名不一致。
        _lack_names = []
        for _e8 in (lack or []):
            _n8 = _e8.get("name") if isinstance(_e8, dict) else _e8
            _n8 = str(_n8 or "").strip()
            if _n8 and _n8 not in _lack_names:
                _lack_names.append(_n8)
        # ★ 2026-10-04（疑点3 D13 收口）：缺料来源改为**唯一权威**。
        #   `evidence_chain` 已完成「业态剔除 + 未归类材料登记」，直接读它 ⇒
        #   字段 / §三 / §四 三处构造上一致，不会再漂移。
        #   ⚠ 保留 `_lack_names`（下一行仍引用它）；权威字段缺失时**回落**到原计算。
        # （`_lack_auth` / `_lack_ok` 已在三态计数处算好 —— 唯一来源，不在此重复计算。）
        if _lack_names and not _lack_ok:
            _p3 += "；本项所列资料属本业态天然不适用，不计入确未提供"
        elif _lack_ok:
            _atoms = []
            for _x8 in _lack_ok:
                for _y8 in re.split(r"[、，,；;／/]|与|和|及|以及|或", _x8):
                    _y8 = _y8.strip()
                    if _y8 and _y8 not in _atoms:
                        _atoms.append(_y8)
            _p3 += "；确未提供的有%d项（%s）" % (len(_at_lack), _brief_atoms(_at_lack))
        _verdict3 = str(ev.get("verdict") or "").strip()
        _p3 += "。" + _verdict3
        if _verdict3 and "可以作出确定性判断" not in _verdict3:
            _rs3 = str(ev.get("rebuttal_status") or "").strip()
            if _rs3:
                _p3 += "，" + _rs3.rstrip("。") + "。"
        p3 = _p3

        # ④ 论证与理由（上游可能带出内部标记或编号，此处做正文净化兜底）
        p4 = _naturalize_report_text(arg.get("reasoning") or "")
        # ★ 2026-10-02（用户复核疑点5）：**结论段的触碰红线断言必须跟着要件认定走** ——
        #   一条要件都没认下时不得再断言「本企业触碰红线」（与同项「涉及第 无 条构成要件」冲突）。
        p4 = sanitize_conclusion_assertion(p4, rname, _participating)
        # ★ 2026-09-29（B2 闭环）：对"以行业基准为判定口径"的红线，论证段补出
        #   按实际行业解析出的基准区间与口径声明（来源 industry_benchmark / industry_data.json，
        #   非税务机关官方口径），使"对照行业基准区间上沿"这类硬化要件真正可核验、不自说自话。
        _bm = arg.get("benchmark_ref") or {}
        _bm_txt = _bm.get("text") if isinstance(_bm, dict) else ""
        if _bm_txt:
            p4 = ((p4 + " " if p4 else "") + _naturalize_report_text(_bm_txt))
        # ★ 2026-09-29（B1 闭环）：把「本企业实际值 vs 行业区间」的真实比对结论并入论证段。
        #   此前只有静态区间文本，读者无法判断本企业是否越界 → 要件说"对照"却没对照（名实不符）。
        #   取不到实际值时 compare 返回 resolved=False，此处不追加任何文字（不编造比对结论）。
        _cmp = arg.get("benchmark_compare") or {}
        _cmp_txt = _cmp.get("text") if isinstance(_cmp, dict) else ""
        if _cmp_txt:
            p4 = ((p4 + " " if p4 else "") + _naturalize_report_text(_cmp_txt))
        # ★ 2026-09-29（P0-6）：命名要件未成立时，在结论段明示认定范围，
        #   避免"标题断言亏损、正文说盈利"式的自相矛盾。
        if _premise_note:
            p4 = ((p4 + " " if p4 else "") + _naturalize_report_text(_premise_note))

        # ⑤ 需企业补充的资料与说明
        # 2026-09-13 用户要求：涉及明细的一律走列表，正文只留引导句，
        # 不再把「第一，…；第二，…」塞进段落里。明细通过 bullets 字段传出。
        actions = [a for a in (arg.get("next_actions") or []) if a]
        # ★★ 2026-10-03（用户复核疑点2）：**"五、需企业提供的资料"同样要过业态剔除**。
        #   事故：服务型广告企业被要求"补充提供……物流单据"、"取得直接证据：采购合同与入库验收单"
        #   —— 这两样它天然不会有 ⇒ "自证清白"的路被堵死。
        #   （材料名段级剔除；整名都不适用 ⇒ 丢掉该动作。）
        if not_required_docs:
            actions = [a for a in (_trim_action_material(x, not_required_docs) for x in actions) if a]
        p5_lead = "要把这一项查清楚，需要：" if actions else "需要由企业就该项提交书面说明。"
        bullets5 = [_naturalize_report_text(str(a).rstrip("。；"))
                    for a in actions if str(a).strip()]
        # ★★ 2026-10-03（用户复核疑点2）：**红线自带的"补救要求"文案同样要过业态剔除** ——
        #   实测「补救要求：提供付款对应的采购合同、**入库验收单、物流单据**，并对资金回流路径…」，
        #   而服务型广告企业天然没有这两样 ⇒ 要求它补 = 要求它永远达不到"资料齐全"。
        _remedy_raw = str(ev.get("remedy") or "").strip()
        if _remedy_raw and not_required_docs:
            _remedy_raw = _trim_text_materials(_remedy_raw, not_required_docs)
        tail5 = _naturalize_report_text(f"补救要求：{_remedy_raw}") if _remedy_raw else ""

        # ══════════════════════════════════════════════════════════════════
        # ★★ 2026-10-02（用户要求新增两项内容，由我决定后落地）：
        #   ① **「为何列入检查」**：让企业一眼看懂"正是因为出现了什么情况才有这个疑点"。
        #      数据来源＝本项终局触发信号（`clue_chain.terminal_signal`，即检测器判定触发的
        #      那一句事实），**可自证**、不另行编造；取不到则不写（不臆测）。
        #   ② **「若不补证的后果」**：按目前分析结论，若企业无法补证或解释，**可能**被如何
        #      定性、承担什么后果。口径三条硬约束（不得越界）：
        #        · 只说"存在被认定为…的风险"，不说"就是/将被认定"（本报告不作定性）；
        #        · 引用的法条只用条款号（第三十二条滞纳金、第六十三条偷税），不逐字引原文
        #          （法条文本以 `legal_citation` 唯一权威为准，避免两处表述漂移）；
        #        · 必须保留"须由税务机关依法调查认定 + 补证前既不认定违法也不予排除"。
        #      仅在**尚未定性**的档位出现（已核定的项已定性，不再讲"若不补证"）。
        # ══════════════════════════════════════════════════════════════════
        # ⚠ `terminal_signal` **不总是"触发原因"**：它有时是排查后的**结论句**
        #   （实测「个人账户收取经营性款项」的 terminal_signal 是"对公账户工资类支出
        #    1,743,847.92 元已覆盖并超过账面应发工资 928,000.00 元，公户代发充分"——
        #    那是"未发现异常"的意思，拿它当触发原因会**语义相反**）。
        #   故先排除"未发现/已覆盖/充分/正常"这类否定性信号，改用线索链首环的事实。
        _NEG_SIGNAL_KWS = ("未发现", "未见", "不存在", "未出现", "已覆盖", "充分", "正常",
                           "无异常", "未超过", "未达", "未涉及", "已排除")
        # ⚠ 一个疑点常聚合**多条发现**，而主线索链未必是主题对应的那条 ——
        #   实测「个人账户收取经营性款项」的主信号取到了同疑点下"成本付款核验"的信号
        #   （"444 张发票的供应商在银行流水付款记录中找不到对应付款"），与"个人账户收款"无关。
        #   故按**与疑点标题的字面相关度**（汉字 2-gram 重叠）挑最相关的那条发现，
        #   主线索链仅作兜底。
        def _bg2(_x):
            _tt = "".join(_c for _c in str(_x or "") if "\u4e00" <= _c <= "\u9fff")
            return {_tt[i:i + 2] for i in range(max(0, len(_tt) - 1))}

        # 取值优先级（先主题相关、再字面相关、最后通用句）：
        #   ① 主线索链的终局信号（非否定句）——它就是本项检测的触发事实；
        #   ② 主线索链首环"账内实际读到的数据"；
        #   ③ 同疑点下其它发现里与标题字面最相关者的信号；
        #   ④ 通用句（不编造具体原因，但保证该段存在）。
        _rb2 = _bg2(rname)
        # ★★ 2026-10-03：附表选择提前到这里 —— 「为何列入检查」要以**本项证据的汇总**概述，
        #   而不是引用某条发现的 detail 原句（那常是"举一个例子"）。
        _rid = s.get("redline_id", "")
        _table_subjects = list(_sup_subjects)
        if (not _ok_sub) and _entry_subject:
            try:
                from engine.subject_consistency import norm_subject_key as _nsk2
                _ek = _nsk2(_entry_subject)
                _table_subjects = [x for x in _table_subjects if _nsk2(x) != _ek]
            except Exception:
                pass
        _tables, _tbl_note = _select_detail_tables(
            _rid, rname, _table_subjects, _src_tables, _dt_by_rid, _dt_by_type, s)
        # ★ 2026-10-04（疑点6 D8）：同疑点内讲**同一批差异**的多张表必须标注口径关系
        #   （否则读者以为是多批差异；实测 3 张表讲同一批、其中 1 张是另一域新增造成的重复）。
        try:
            _tables = _annotate_overlapping_tables(_tables)
        except Exception as _aoe:
            # ★ 2026-10-08：改走 `_audit_note`（audit_sink 是 dict，不能直接 .append）。
            _audit_note(audit_sink, "同疑点表口径关系标注失败", _aoe,
                        title=rname, redline_id=rid)
        _ev_sum = _evidence_summary(_tables)
        # ★★ 2026-10-08（P0-4 根因治理，公司1 真实产物取证 R14/RL-SPT-017）：
        #   事故：「广告/娱乐服务未申报文化事业建设费」这一项的"为何列入检查"被写成
        #     「同一供应商同品名单价不一致（共5笔）（本表 5 行，涉及 5 个对象，金额合计 0.00 元）」
        #     —— 读者看到的是**另一件事**的事实，本项报告的可信度直接受损。
        #   真凶不是 `supporting_findings` 打分（那是另一条只在此处**不执行**的兜底路径），
        #     而是本行：`_evidence_summary(_tables)` 概述的是**附表**，而该附表来自建入口那条
        #     **软匹配**发现（主体自检已判 `_ok_sub=False`）⇒ 用它当引子必然张冠李戴。
        #   判据（通用、数据驱动、不认表名）：**引子来源必须与本项红线名是同一件事** ——
        #     用 `subject_consistency.same_subject(来源发现类型, 红线名)` 逐张核。
        #     · 全部来源都判不出（无索引）⇒ 不阻断（保守，宁可用真事实也不用空话）；
        #     · 有来源且**无一**通过 ⇒ 置空，退回线索链终局信号（它本就是"本项为何触发"的口径）。
        #   ⚠ 只动引子、不动附表：附表是本项**实际读到的证据**，另有既有测试明确要求保留
        #     （`test_foreign_table_is_not_attached`：本项自己的明细必须还在）；
        #     且实测该附表并不进正文表格区，仅在引子处泄漏。
        if _ev_sum and _tables:
            _origins = {str(_owner_type.get(id(_t)) or "").strip() for _t in _tables}
            _origins.discard("")
            if _origins:
                try:
                    from engine.subject_consistency import same_subject as _ssame2
                    _on_topic = any(_ssame2(_o, rname) for _o in _origins)
                except Exception:
                    _on_topic = True
                if not _on_topic:
                    _audit_note(
                        audit_sink, "事实引子与主体不符",
                        "本项附表的来源（%s）与本项风险指标「%s」不是同一件事，"
                        "该汇总不得作为本项'为何列入检查'的依据，已改用本项自身的触发信号"
                        % ("；".join(sorted(_origins))[:60], str(rname)[:40]),
                        title=rname, redline_id=rid)
                    _ev_sum = ""
        _main_sig = str(clue.get("terminal_signal") or "").strip()
        if _main_sig and any(k in _main_sig for k in _NEG_SIGNAL_KWS):
            _main_sig = ""
        # 取值优先级（2026-10-03 起）：① 本项证据**汇总概述**（可复算、可回指明细表）；
        #   ② 主线索链终局信号；③ 主线索链首环读数；④ 同疑点下最相关发现的信号；⑤ 通用句。
        _why_txt = _ev_sum or _main_sig
        if not _why_txt:
            for _n0 in (clue.get("nodes") or []):
                _obs0 = str((_n0 or {}).get("observed") or "").strip() if isinstance(_n0, dict) else ""
                # 跳过"已读取资料：…"这类**只说明读了什么**的环（不是触发原因），
                # 且必须走中文化（否则会带 `matches=` 这类引擎内部键名进正文）。
                if not _obs0 or "已读取资料" in _obs0:
                    continue
                _obs0 = _humanize_observed(_obs0) or _obs0
                _why_txt = "在%s环节读到：%s%s" % (
                    _label_source(str(_n0.get("source") or "")) or "相关资料",
                    _obs0[:80], "…" if len(_obs0) > 80 else "")
                break
        if not _why_txt:
            # ★★ 2026-10-08（P0-4 根因治理，公司1 真实产物取证）：
            #   病根：`_best_sc` 从 **-1** 起、判据为 `_sc2 > _best_sc` ⇒ **零重叠（0）也中选**，
            #   于是任何弱相关/无关的同疑点发现都能当上"事实引子"。
            #   实测（R14）标题「广告/娱乐服务未申报文化事业建设费」，事实引子却被写成
            #   「同一供应商同品名单价不一致（共5笔）（本表 5 行…金额合计 0.00 元）」
            #   —— 读者看到的是**张冠李戴的事实**，报告可信度直接受损。
            #   修法：设**主体重叠相对下限**（≥ 标题汉字 2-gram 数的 15%，且至少 1 个）。
            #     低于下限 ⇒ **不用该路径**（宁可退回中性口径，也不塞一条无关事实）。
            #     标题无可用中文（`_rb2` 为空）⇒ 无法判相关度 ⇒ 同样不用该路径，
            #     并按本项目铁律**留痕**（不静默）。
            _sc_floor = max(1, int(len(_rb2) * 0.15))
            _best_sc = -1
            for _f0 in (s.get("supporting_findings") or []):
                if not isinstance(_f0, dict):
                    continue
                _sig2 = str(_f0.get("terminal_signal") or "").strip()
                if not _sig2 or any(k in _sig2 for k in _NEG_SIGNAL_KWS):
                    continue
                _sc2 = len(_rb2 & _bg2(str(_f0.get("type") or "")))
                if _sc2 >= _sc_floor and _sc2 > _best_sc:
                    _why_txt, _best_sc = _sig2, _sc2
            if not _why_txt and (s.get("supporting_findings") or []):
                _audit_note(
                    audit_sink, "事实引子缺主体依据",
                    "同疑点下无发现的标题相关度达到下限（需≥%d，标题可用中文 2-gram %d 个）"
                    "⇒ 改用中性口径，不引用可能张冠李戴的事实" % (_sc_floor, len(_rb2)),
                    title=rname, redline_id=rid)
        if not _why_txt:
            # 回退：线索链首环"账内实际读到的数据"（同样是可自证事实，不臆测原因）
            # ⚠ 截断必须**可见**（省略号），不得留半截数字（本项目铁律）
            for _n in (clue.get("nodes") or []):
                if isinstance(_n, dict) and str(_n.get("observed") or "").strip():
                    _obs = str(_n["observed"]).strip()
                    _why_txt = "在%s环节读到：%s%s" % (
                        str(_n.get("source") or "相关资料"),
                        _obs[:80], "…" if len(_obs) > 80 else "")
                    break
        _pre_paras = [{
            "heading": "为何列入检查",
            "text": _naturalize_report_text(
                ("本项之所以列入检查，是因为出现了以下情况：%s。"
                 "本项对应的风险指标是「%s」——凡出现上述情形即纳入检查范围；"
                 "是否成立，另按本项构成要件逐条核对（见下）。"
                 % (_why_txt.rstrip("。；; "), rname)) if _why_txt else
                ("本项因风险指标「%s」与本企业账内数据的比对结果列入检查："
                 "比对中发现与该指标对应的异常线索（详见下一节各环实际读到的数据）；"
                 "是否成立，另按本项构成要件逐条核对。" % rname)),
        }]
        _post_paras = []
        if grade != "已核定":
            _taxes_txt = "、".join(str(x) for x in (s.get("taxes") or []) if str(x).strip())
            # ★★ 2026-10-03（用户：疑点是否要加"会被如何定性、承担什么后果"）：
            #   「存在被认定为**涉嫌**X的风险」是病句 —— "被认定"是确定语义、
            #   "涉嫌"是待核语义，挤在一起既不通顺也不严谨。此处剥掉「涉嫌」前缀，
            #   并加「」把被认定的情形括起来（实测 24 条疑点全部带这个病句）。
            _suspect_plain = _suspect_txt
            for _p0 in ("涉嫌",):
                if _suspect_plain.startswith(_p0):
                    _suspect_plain = _suspect_plain[len(_p0):]
            _suspect_plain = _suspect_plain.strip() or "账簿少列收入、少缴应纳税款"

            _post_paras.append({
                "heading": "若不补证的后果",
                # ★★ 2026-10-06（用户评语 #4「税费法律适用混同」）：
                #   旧实现**对所有事项一律**套用《税收征收管理法》第三十二条 + 第六十三条（偷税），
                #   对社保费/住房公积金/文化事业建设费属**法律适用错误** ——
                #   社保费依《社会保险法》第八十六条；公积金依《住房公积金管理条例》
                #   且追责主体是**住房公积金管理中心**；文建费是**政府性基金**。
                #   ⇒ 按本项**性质**选用对应依据（唯一权威 `engine.levy_nature`）。
                # ★★ 2026-10-08（P0-2 去重收口）：**法条上提报告级一次、逐项用引用**。
                #   实测：同一性质的法条在 13 个事项里逐字相同 ⇒ 整体重复率 11.11% 超阈
                #   （>10%）⇒ `duplicate_rate` 判「阻断」⇒ 报告不得输出；
                #   而这些法条句属 `report_dedup._is_nature_specific`（故意不让跨性质上提，
                #   防税款条款被套到公积金上）⇒ 句级上提永远打不中，只能原地重复。
                #   ⇒ 逐项只留**本项自己的情形** + 指向报告级「税费性质与法定后果」的引用；
                #     法条原文按性质在报告级声明一次（`_report_levy_declarations`）。
                "text": _naturalize_report_text(
                    _levy_item_consequence(_levy_natures_of(s),
                                      suspect=_suspect_plain,
                                      taxes_txt=_taxes_txt,
                                      grade_txt={"已核定": "已可作出判断",
                                                 "已排除": "已排除"}.get(str(grade),
                                                                     "尚待补证与核实"))),
            })

        paragraphs = _pre_paras + [
            {"heading": "一、涉及的风险事项", "text": _naturalize_report_text(p1),
             "bullets": bullets1 or None, "tail": tail1,
             # ★ 2026-09-29（P0-5 深层）：要件级独立核对表（每要件一行：独立数据源 +
             #   数据源状态 + 独立结论），使"哪条核过、哪条没核"可直接核验。
             "detail_tables": ([_cp_tbl] if _cp_tbl else None)},
            {"heading": "二、发现的依据", "text": _naturalize_report_text(p2),
             "detail_table": _clue_table(clue, not_required=not_required_docs)},
            # 本段明细由 detail_table 承载，不再另出 bullets，避免同一信息重复两遍
            {"heading": "三、已取得的资料与待补充的资料", "text": _naturalize_report_text(p3),
             "detail_table": _evidence_table(ev)},
            {"heading": "四、本项结论及理由", "text": p4},
        ] + _post_paras + [
            {"heading": "五、需企业提供的资料与说明", "text": _naturalize_report_text(p5_lead),
             "bullets": bullets5 or None, "tail": tail5,
             # ★ 2026-10-04（疑点2 收口）：补资料清单（具体材料名 + 关联未核对要件 + 依赖度）
             "detail_table": _supplement_table(
                 _cp_tbl, s.get("missing_material_names") or [], not_required_docs)},
        ]

        # ★★ 2026-10-03（用户：「这种对每一项问题从点到面的推断思考与分析，是应该接入
        #   一键分析按钮，并让它每次生成报告时都要触发的功能」）：
        #   为**每一条疑点**生成「推断与联想」段——把本项读数在正常经营下的可能原因、
        #   若为违规会是什么样、哪份资料能区分、以及该载体在逻辑上能否成立，逐条摊开。
        #   ★ 位置：插在「二、发现的依据」之后（先给依据，再展开推断），
        #     且**按小标题定位**插入，不得按索引写死（历史上按索引插段曾把附表挂错小节）。
        try:
            from engine.inference_ladder import ladder_for_suspicion as _ladder
            _lat = _lateral_by_type.get(str(s.get("finding_type") or ""))
            _sec = _ladder(s, _lat)
            if _sec and _sec.get("bullets"):
                _sec["text"] = _naturalize_report_text(_sec["text"])
                _sec["bullets"] = [_naturalize_report_text(b) for b in _sec["bullets"]]
                # 位置＝**末尾**：段名是「六、」，接在「五、需企业提供的资料与说明」之后，
                # 编号与位置一致（曾插在「二、」之后，出现"二、→六、→三、"的乱序）。
                paragraphs.append(_sec)
        except Exception as _le:
            # 铁律：不静默吞（except 留痕）——推演段失败必须可见，否则等于没有这层能力
            _audit_note(audit_sink, "推演段生成失败", _le, title=rname, redline_id=rid)

        # 逐笔明细表 挂到「发现的依据」段 —— **按来源归属**（唯一权威 subject_consistency）：
        #   ① 只用「本疑点自己声明的支撑发现」出的表（`supporting_findings` 是引擎给出的
        #      "本疑点由哪些发现构成"，是唯一权威）；
        #   ② 支撑发现为空时，才退回按红线编号精确关联；
        #   ③ 都没有 → 不附明细；有明细但主体不符时**如实写明为什么没附**
        #      （绝不附一张主体不符的表 —— 那正是用户反复报的"内容与主体错配"）。
        # （附表已在前面选好：`_tables` / `_tbl_note`；此处只做挂载）
        if _tables:
            # ★★ 2026-10-02：**按小标题定位**，不得按位置写死。
            #   事故：原为 `paragraphs[1]["detail_tables"] = _tables`，
            #   本轮新增「为何列入检查」段（插在第 0 位）后，索引 1 变成
            #   「一、涉及的风险事项」——逐笔证据表被挂到了**错误的小节**下
            #   （读者的"发现的依据"里看不到明细，反而在"涉及的风险事项"里出现）。
            #   是反向闸门 `test_legit_same_topic_table_still_attached` 把它抓出来的。
            for _pp in paragraphs:
                if str(_pp.get("heading") or "").startswith("二、"):
                    _pp["detail_tables"] = _tables
                    break
            else:
                paragraphs[-1]["detail_tables"] = _tables
        elif _tbl_note:
            # 有候选明细但主体不符（或压根没有与本项相关的明细）：如实写出来，
            # 让读者知道"这里没有逐笔明细"的原因是**没有相关的**，而不是"系统没查"。
            for _pp in paragraphs:
                if str(_pp.get("heading") or "").startswith("二、"):
                    _pp["text"] = (_pp.get("text") or "") + _tbl_note
                    break
            if isinstance(audit_sink, dict):
                audit_sink.setdefault("issues", []).append({
                    "seq": None, "title": _title_raw[:60],
                    "code": "附表来源与本项主体不符",
                    "detail": _tbl_note.strip()[:120], "redline_id": rid,
                })
                audit_sink.setdefault("by_code", {})
                _k2 = "附表来源与本项主体不符"
                audit_sink["by_code"][_k2] = audit_sink["by_code"].get(_k2, 0) + 1

        # ★ 2026-10-01：**分项扣除限额测算表**挂到「四、本项结论及理由」——
        #   多分项红线（如 RL-CIT-007 招待费/广宣费/福利费）此前只渲染算出数的那一项，
        #   其余分项的超限金额进了系统却进不了报告。
        try:
            _lit = _lit if _lit is not None else _limit_items_table(rid, findings)
        except Exception:
            _lit = None
        if _lit:
            paragraphs[3]["detail_tables"] = [_lit]
            # ★★ 2026-10-05（疑点5 D6）：分项数字**回填**到对题环节的 observed。
            #   事故：三环都写「本环节未产出对题读数」，而同疑点的分项测算表里
            #   确实有金额（业务招待费 411,111.53／广宣费 2,729,730.26）
            #   ⇒ 数据在同疑点内可回指，写「未产出」等于否定已算出的数。
            #   只回填**动作对题**的环节（环3「核对是否作纳税调增」不得被填）；数字逐字取自本表。
            try:
                _lim_txt = "；".join(
                    "%s 账面 %s、超限 %s" % (r.get("费用项目"),
                                            r.get("账面发生额（元）"), r.get("超限金额（元）"))
                    for r in ((_lit.get("rows") or [])[:3]))
                for _nd in (clue.get("nodes") or []):
                    if not isinstance(_nd, dict):
                        continue
                    _obs5 = str(_nd.get("observed") or "")
                    if "未产出对题读数" not in _obs5:
                        continue
                    _act5 = str(_nd.get("action") or "") + str(_nd.get("output") or "")
                    if not any(_k in _act5 for _k in ("限额", "归集", "扣除", "计算", "发生额")):
                        continue
                    _nd["observed"] = "本环节读数（来自本项分项扣除限额测算）：" + _lim_txt
                    _nd["has_data"] = True
            except Exception:
                pass

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
        # ★★ 2026-10-09（P0-6 闭合度单一权威）：闭合度**只有一个算法** ——
        #   `engine.evidence_chain.closure_basis()`（按证据角色权数：直接=3 / 资金=2 / 间接=2）。
        #   事故：本处原取 `s["closure"]`/`ev["closure"]`（不回算），而门禁 B9 用
        #   `evidence_have/need`（**材料项数**）复算 ⇒ 同一指标**两个口径**，必然不自洽
        #   （实测 seq4 closure=0.38 而 1/4=0.25）。
        #   现一律**由 elements 单向重算**；拿不到 elements ⇒ None（缺失≠0），
        #   绝不用 0 冒充"未评估"，也绝不用旧缓存值顶替。
        _clo_pack = None
        _eb = ev if (isinstance(ev, dict) and ev.get("elements")) else None
        _eb_surface = None
        if _eb is not None:
            try:
                from engine.evidence_chain import closure_basis as _clo_basis
                from engine.evidence_chain import surface_chain as _sc
                _clo_pack = _clo_basis(_eb)
                _eb_surface = _sc(_eb)
            except Exception as _ce:  # noqa: BLE001 —— 不静默：闭合度算不出必须留痕
                _audit_note(audit_sink, "闭合度重算失败", _ce, title=rname, redline_id=rid)
                _clo_pack = None
                _eb_surface = None
        _clo = _clo_pack["closure"] if _clo_pack else None
        # ★ 2026-09-29（点评整改 P0-6）：**标题按实际证据裁剪**（计算见本循环前部
        #   `_title_raw` / `_premise_note`，此处不再重复）。
        # 前提未成立时，首段的"本企业触发…即<红线名>"同样须收窄，否则标题与正文不一致
        if _premise_note:
            p1 = (
                f"经检查，本企业触发税务风险指标（对应：{rname}），{_suspect_txt}。"
                f"本项认定范围见标题括注。该风险指标不因行业而变，凡符合下列构成要件即属涉嫌疑点："
            )
        # ★★ 2026-10-03（用户复核疑点3）**通用化**：**疑点等级不得超过其"建入口那条发现"的等级**。
        #   事故（实测 3 例）：发现级「中风险」被红线等级表升为「高风险」（RL-INC-001 / RL-INC-002）、
        #   「低风险」被升为「中风险」（RL-VAT-006）——发现层自己写着"该结果只说明两个数据口径
        #   需要逐月对账"，疑点层却成了"高风险账外收入"。
        #   判据（数据驱动）：`risk_level = min(红线等级表中的等级, entry 发现自身 level)`；
        #   等级序：信息 < 低风险 < 中风险 < 高风险 < 极高风险；被压时另记 `risk_level_capped_from`。
        #   （`downgraded` 的线索仍最强：一律「待核验」。）
        _lv = ("待核验" if s.get("downgraded")
               else ((_lb or {}).get("level") or s.get("level", "")))
        _cap = str(s.get("level") or "").strip()
        # ★★ 2026-10-06：**等级标度唯一权威 `engine.risk_levels`**（原先此处内联一张
        #   `{"信息":-1,"低风险":0,...}` 表，与 pipeline/finding_families 各自一张表**互相矛盾**，
        #   同一事项在不同章节被判成不同等级）。`cap_level` 同时还保证
        #   「待核验」这类**证据状态不参与压制**（降级线索不得被"信息"压掉）。
        _lv, _capped_from = _cap_level(_lv, _cap) if not s.get("downgraded") else (_lv, "")
        problems.append({
            "seq": i,
            # 报告标题只写红线名（用户要求：正文不出现 RL-XXX 编号）；
            # 编号仍通过 redline_id 字段透传，供系统内部追溯与前端可选展示。
            "title": _naturalize_report_text(_title_raw),
            "premise_note": _naturalize_report_text(_premise_note) if _premise_note else "",
            "redline_id": rid,
            # ★★ 2026-10-07（触发条件与认定要件分离）——**把 rule_id 一并透传**。
            #   部分发现是"VR 规则"键控（`rule_id=VRxxx`）而非红线键控（`redline_id` 为空），
            #   报告层若只带 redline_id，则这些疑点**拿不到任何触发源** ⇒ 直接违反验收
            #   「不得出现"已列为疑点"但"未触发任何触发条件"」。实测 3 个疑点即此情形
            #   （多税种联动稽查风险画像 / 同一交易对手同时出现在客户与供应商清单(VR012) /
            #     增值税申报进项税额与进项发票税额月度差异(VR019)）。
            #   口径：触发源 = redline_id（红线绑定）> rule_id（规则绑定）> 本项触发信号（兜底）。
            "rule_id": str(s.get("rule_id") or s.get("_rule_id") or ""),
            "conclusion_grade": grade,
            # ★ 2026-10-02（用户复核疑点5）：**结论徽标也必须与要件认定同口径**。
            #   引擎的 verdict 表示"红线终局信号已触发"，与"是否认定到构成要件"是两件事；
            #   一条要件都没认定时，报告里若仍挂着「已触碰税务违规红线」，
            #   读者看到的仍是"本项说触碰红线了，可是构成要件一条都没认定"。
            #   故报告层的结论文案跟随唯一权威 `_participating`（同 p1/p4 用的那个集合）。
            #   引擎裁决本身不改（计数、排序仍按原裁决），只改**读者看到的措辞**
            #   ——与「执行版不写触碰税务红线、改说触发税务风险指标（待核实）」同一宗旨。
            # ★★★ 2026-10-05（用户明确口径：「报告永远不能出现待核实。
            #   从既有资料检查分析，**能确定的风险就是风险**」）
            #   旧措辞「账内检出信号待核实（未认定到构成要件，不作定性）」有三处错：
            #     ① 「待核实」——把已从账内读出的确定事实说成不确定，企业无法据此整改；
            #     ② 「未认定到构成要件」——把判定过程写给企业看（属内部口径）；
            #     ③ 「不作定性」——读起来像"这件事不算问题"，反而弱化了真风险。
            #   现口径：**能确定的说清楚是什么风险，不能确定的明确说是资料不足**，
            #   两者都不写"待核实"。
            # ⚠ 措辞须同时满足两条（缺一闸门即 ERROR）：
            #   ① 用户口径「能确定的风险就是风险」⇒ 不写"待核实"、正面说清楚是什么风险；
            #   ② 闸门 `check_downgraded_problem_wording`：**降级疑点**（标题「待核线索…」）
            #      的结论必须含「未认定」，否则企业会以为它已被认定。
            # ★★ 2026-10-08（P0-2 用语权威收口）：**不得再写字面量**。
            #   旧字面量「本项已查明的风险；未认定到构成要件（认定范围见本项说明）」含**定性词**
            #   "已查明"，而 L2 的 `allow_determinative_words=false`，且缺 L2 的
            #   `required_text`（「待核」「不作定性」）⇒ 质量门禁 A3 / B5 同一事项各报一次。
            #   现句式由 `conclusion_grade.pending_clue_phrase` 生成（唯一权威，术语驱动）。
            "verdict": (s.get("verdict", "") if _participating
                        else _pending_clue_phrase(with_scope_note=True)),
            "confidence": s.get("confidence", 0.0),
            # ★ 2026-09-29（点评整改 P1-9）：可信度的**分项计算依据**与公式（可逐项复算）。
            #   外部点评：全文 25 处「判断可信度约 N%」无任何口径披露，读者无法核验。
            "confidence_breakdown": arg.get("confidence_breakdown") or [],
            "confidence_formula": arg.get("confidence_formula") or "",
            "closure": _clo,
            # ★ 2026-09-27（用户要求）：前端也以项数（已有/还缺）呈现材料齐全程度，
            #   不再显示百分比。closure 仅内部使用（决定能否定性）。
            #   ★★ 2026-10-09（P0-6）：`evidence_have/need` 是**材料项数**（前端"已有X项/还缺Y项"
            #     + "补全N项资料"），与闭合度的**权数口径**是两回事 —— 故另立
            #     `closure_num/closure_den`（权数）承载闭合度的分子/分母，使
            #     `closure == round(closure_num/closure_den, 2)` 可由任一下游**同口径**复核
            #     （门禁 B9 已改用它，不再拿项数复算权数）。
            "evidence_have": int(ev.get("available_count", 0) or 0),
            "evidence_need": int(ev.get("available_count", 0) or 0)
                             + int(ev.get("missing_count", 0) or 0),
            "closure_num": (_clo_pack or {}).get("num"),
            "closure_den": (_clo_pack or {}).get("den"),
            # ★★ 2026-10-09（P0-6）：**挂载证据链本体**（含 elements[].role/status/weight）。
            #   事故：`confirmed_problems[].evidence_chain` 恒为 None ⇒ 门禁 A6（证据状态五态词表）
            #   与 C3（证据缺编号）**直接 SKIP ⇒ 判据空转**（"三不"里的"判据空转"）。
            #   只挂**栅栏化投影**（`evidence_chain.surface_chain`），不带 verdict/remedy 等
            #   已在正文出现的长文案 —— 避免同一内容二次进入词表扫描与去重统计。
            "evidence_chain": _eb_surface,
            "direct_missing": str(ev.get("direct_missing") or ""),
            # ★★ 2026-10-03（用户复核疑点3）：**降级的发现不得沿用红线的高风险等级**。
            #   事故：引擎已把该发现降为「低风险」，报告却因红线等级表把它标成「高风险」。
            #   判据：`s["downgraded"]` ⇒ 等级强制「待核验」（与"只作待核线索登记"一致）。
            # ★★ 2026-10-03（用户复核疑点3）**通用化**：**疑点等级不得超过其"建入口那条发现"的等级**。
            #   事故（实测 3 例）：发现级「中风险」被红线等级表升为「高风险」（RL-INC-001 / RL-INC-002）、
            #   「低风险」被升为「中风险」（RL-VAT-006）——发现层自己写着"该结果只说明两个数据口径
            #   需要逐月对账"，疑点层却成了"高风险账外收入"。
            #   判据（数据驱动）：`risk_level = min(红线等级表中的等级, entry 发现自身 level)`；
            #   等级序：信息 < 低风险 < 中风险 < 高风险 < 极高风险。降级时另记 `risk_level_capped`。
            "risk_level": _lv,
            "risk_level_capped_from": _capped_from,
            "risk_level_basis": _lb_basis,
            "suspect": s.get("suspect", ""),
            "taxes": s.get("taxes", []),
            "final_answer": (arg.get("claim", "") if grade == "已核定" else ""),
            "suggestion": _seq(actions, ""),
            "narrative_paragraphs": paragraphs,
            "detail_table": _evidence_table(ev),
            "finding_count": s.get("finding_count", 1),
            # ★ 按业态剔除「不适用资料」：对服务型企业要求进销存台账 = 无效要求
            #   （实测 8/29 个疑点的待补清单里出现它，有的**只有**这一项）。
            #   与 material_readiness 同源（同一 `not_required_docs`），不另立口径。
            # ★★ 2026-10-03（用户复核疑点2）：由**等值**匹配升级为**按段**剔除 ——
            #   旧实现只处理"整项恰好等于不适用名"，而实测清单里是**组合名**
            #   「采购合同与入库验收单」「物流单据与承运记录」，于是漏网。
            #   现统一走 `_strip_not_required`（同一权威，段级判定；"采购合同"被保留）。
            "missing_materials": _filter_not_required(s.get("missing_materials"), not_required_docs),
            # ★ 2026-10-04（疑点2 D12）：**具体材料名**（面向企业要补哪几样）。
            #   业态剔除与计数仍用上面的类别级字段，此字段只负责表达，故同样过一遍剔除。
            "missing_material_names": _filter_not_required(
                s.get("missing_material_names") or [], not_required_docs),
            "verify_materials": _filter_not_required(s.get("verify_materials"), not_required_docs),
            "trace_id": (clue.get("nodes") or [{}])[0].get("trace_ref", ""),
        })
    # ★ 2026-09-27（P1）：逐项测算**潜在税额影响**。只认关键词锚定的明确金额，
    #   取不到 → 未量化（绝不猜）。
    # ★ 2026-09-29（点评整改 P0-4）：税率走 rate_ctx（pipeline 从销项有效税率/净利润
    #   推断的语境），未提供时才落到 tax_impact._RATES 兜底口径。
    # ★★ 2026-10-03（用户复核疑点1：税额虚高 8.4 倍）：**两道口径关**——
    #   ① 锚定改"语义锚定"（`tax_impact.extract_amount`）：排除"占比分母/剔除…后/合计"类
    #      **参照量**，优先"分子/差额/少缴/红冲"类**涉案量**。事故：占比分母 8,050,908.58
    #      比涉案金额 1,015,900.00 大 ⇒ 旧规则"取最大"把分母当涉案金额。
    #   ② **含税→不含税**（`tax_impact.normalize_basis`，唯一权威 `engine.tax_rates.to_exclusive`）：
    #      锚定到"价税合计"时先价税分离，再进 estimate_tax；取不到税率则**不换算**并如实标注。
    try:
        from engine.tax_impact import (extract_amount_from_problem, estimate_tax,
                                       normalize_basis)
        for _p in problems:
            _am = extract_amount_from_problem(_p)
            _norm = normalize_basis(_am, rate_ctx)
            # ★ 2026-10-04（疑点4 D12）：传入**基数性质**，让 tax_impact 能判断
            #   这个税种的基数是不是本项事实的金额（判不出则传空，行为不变）。
            # ★ 2026-10-06（用户评语 #3-③）：同时传"锚定金额**是否本身就是税额**"——
            #   进项/销项税额类差额若再乘税率是**逻辑错误**（实测 4,501.34→270.08）。
            from engine.tax_impact import (infer_amount_nature as _ian,
                                           infer_amount_is_tax as _iati)
            _p["tax_impact"] = estimate_tax(_norm.get("amount"), _p.get("taxes"),
                                            rate_ctx=rate_ctx,
                                            amount_nature=_ian(_p),
                                            amount_is_tax=_iati(_p))
            if _am:
                _scope = str(_norm.get("scope_note") or "")
                _p["tax_impact"]["amount_context"] = (
                    (_scope + "；锚定语境：" + str(_am.get("context") or ""))
                    if _scope else str(_am.get("context") or ""))
            # ★★ 2026-10-06（用户第 2 批 疑点1 ①②）：**红冲/作废类：金额只是"异常线索"**。
            #   红冲可能是法定更正（开票有误/退货/折让），**不等于已确认少缴税款**
            #   ⇒ 潜在税额一律**未量化**，并写明"若需上界估算，仅按红冲金额价税分离后乘适用税率"。
            #   判据取自本项自身的**主题字段**（`redline_name`/`title`），数据驱动、非公司特例。
            _blob = str(_p.get("title") or "") + str(_p.get("redline_id") or "")
            _is_clue_only = any(k in _blob for k in ("红冲", "红字", "作废"))
            if _is_clue_only:
                _ti = _p.get("tax_impact") or {}
                if not _ti.get("available"):
                    _ti["note"] = (
                        "未量化：本项金额为**红冲/作废金额线索**，红冲可能是依法更正"
                        "（开票有误、销货退回、销售折让），**不等于已确认少缴税款**，"
                        "故不给出潜在税额。若需上界参考：**仅按红冲金额**（销项侧冲减价税合计）"
                        "价税分离后乘适用税率估算，并须以逐张核实红冲事由、还原被冲销蓝票"
                        "业务真实性后的结论为准。")
                    _p["tax_impact"] = _ti
    except Exception:
        pass

    # ★★ 2026-10-02（用户质疑：为什么二、具体问题不是从高风险开始排）：
    #   **排序必须在这个主路径上执行**。事故：`_build_confirmed_problems` 在有红线疑点时
    #   直接 `return _build_redline_problems(...)`，而 `_RISK_PRESENT_ORDER` 的排序写在
    #   **旧路径**（无 suspicions 时）后面 —— 主路径**从不执行那段排序**，它是死代码；
    #   实际顺序＝suspicions 的置信度顺序，与风险等级无关（实测"高风险"夹在第 7、14、15 位）。
    #   既有闸门只查"源码里有没有引用顺序表"，查不到"这段从没被走到"，故漏网。
    #   判据：等级规范化 → 按呈现顺序升序（越重越靠前）→ 同级按潜在税额降序 → 重排 seq。
    for _p in problems:
        _p["risk_level"] = _normalize_risk_level(_p.get("risk_level"))
    problems.sort(key=lambda _p: (
        _RISK_PRESENT_ORDER.get(str(_p.get("risk_level") or "").strip(), 99),
        -float(((_p.get("tax_impact") or {}).get("amount") or 0) or 0),
    ))
    for _i, _p in enumerate(problems, start=1):
        _p["seq"] = _i
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
    # ★ 2026-09-29（点评整改 P0-9c）：**不要抹掉省略号**。
    #   省略号是"此处已被截断"的**唯一信号**。旧实现 `s.replace("…", "")` 把
    #   「差异=-1,6…」变成「差异=-1,6」——一个看起来像真数字的残句，读者无从分辨。
    #   外部点评实测的 "=260,5" "=275,00" "（偏离 —）" "单笔）" 全部由此产生：
    #   截断本身未必错，**把截断痕迹擦掉**才把"截断"伪装成了"数据"。
    #   现保留省略号，仅去掉尾随分隔符；配合 clamp_text 的顿号边界
    #   （切点落在「、」处），键值对不再被从中间切开。
    s = s.strip("，；。 ")
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


# ★★ 2026-10-03（用户："报告编制特别不精准、很儿戏、整一堆没用的证据和信息"）：
#   **"实际看到的数据"里的三类无价值内容，一律不得充当证据。**
#   逐条实测（公司1 成品报告）：
#     ① 元信息当证据：「已读取资料：银行流水」「本轮未取得该项资料」——
#        这是**取数过程的元信息**，不是账内事实；它被写进"看到…"后，
#        该环等于没有证据，却占了整整一步（疑点1/5/7/9/12/15/16/18/19/20/21 均有）。
#     ② 空话占步：「数据与上一环一致」——零数字、零信息（15 条疑点都有）。
#     ③ 指标倾倒：`匹配明细=人员=初永伟、转出个人金额=1,071,343.80等5项…等10项`
#        —— 把 `observed_metrics` 的原始结构直接倒进正文，读者拿不到"本项到底凭什么"。
_OBS_META_READ_PREFIX = ("已读取资料", "已读取", "读取并归集", "本轮已上传并成功读取")
_OBS_META_GAP_PREFIX = ("本轮未取得", "该环节未取得", "该环节未产出", "未取得该环节")
_OBS_PILE_RE = re.compile(r"等\s*\d+\s*项")


def _obs_kind(value) -> str:
    """观测值的证据价值分类：`fact`(有账内读数) / `meta_read` / `meta_gap` / `none` / `pile`。"""
    s = str(value or "").strip()
    if not s or s == "同上":
        return "none"
    for p in _OBS_META_READ_PREFIX:
        if s.startswith(p):
            return "meta_read"
    for p in _OBS_META_GAP_PREFIX:
        if s.startswith(p):
            return "meta_gap"
    if _OBS_PILE_RE.search(s) and len(s) >= 26:
        return "pile"
    return "fact"


def _obs_lead_fact(value, limit: int = 46) -> str:
    """指标倾倒时只保留**第一个可直接引用的读数**（其余指向明细表）。"""
    s = str(value or "").strip()
    for seg in re.split(r"[，；、]", s):
        seg = seg.strip()
        if seg and re.search(r"\d", seg):
            return seg[:limit]
    return s[:limit]


def _clue_narrative(clue, not_required=None):
    """把发现过程讲成大白话，每环只在**真有账内读数**时才写「看到…」。

    ★★ 2026-10-03 重写（用户："整一堆没用的证据和信息"）：
      旧版对每一环一律写"看到{observed}"，于是元信息（"已读取资料：银行流水"）、
      空话（"数据与上一环一致"，来自 dedup 的"同上"）、指标倾倒三种东西都冒充了证据。
      现按证据价值分流：
        · `fact`      → 原样写"看到…"（这是本项结论的真正依据）；
        · `pile`      → 只写第一个可引用读数 + "（完整读数见本项明细表）"；
        · `meta_read` → 该环只交代"做了什么"（读了什么资料已在第三节列明，不重复播报）；
        · `meta_gap`  → 不写"看到"，把缺口**在句尾集中交代一次**并点明缺的是哪份资料
                        （既不拿元信息冒充证据，也不静默吞掉"这一步没读到）"）。
      另外：`dedup` 产生的"同上"不再写成"数据与上一环一致"（零信息），直接并入上一环的读数。
    """
    nodes = clue.get("nodes") or []
    if not nodes:
        return ""
    observed_list = _dedup_observed([n.get("observed") for n in nodes])
    parts = []
    gaps = []
    for i, n in enumerate(nodes):
        _src_txt = _label_source(n.get("source")) or "相关资料"
        if not_required:
            _src_txt = _strip_not_required(_src_txt, not_required) or _src_txt
        seg = f"第{n.get('step')}步从{_src_txt}中{n.get('action') or ''}"
        obs = observed_list[i] if i < len(observed_list) else ""
        kind = _obs_kind(obs)
        if kind == "fact":
            # 观测值内部的「；」改为「，」，避免与步骤之间的分隔符混淆
            seg += f"，看到{str(obs).replace('；', '，')}"
        elif kind == "pile":
            seg += f"，看到{_obs_lead_fact(obs)}（完整读数见本项明细表）"
        elif kind == "meta_gap":
            _src = _label_source(n.get("source")) or "相关资料"
            gaps.append(_src)
        # meta_read / none：不写"看到"，避免拿取数过程冒充账内事实
        parts.append(seg)
    txt = "；".join(parts) + "。"
    _gaps = list(dict.fromkeys(gaps))
    if _gaps:
        txt += ("其中%d个环节因所需资料（%s）本轮未提供而未取得读数，已计入检查受限范围。"
                % (len(_gaps), "、".join(_gaps)))
    return txt


def _clue_table(clue, not_required=None):
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
    # ★ 2026-09-29（点评整改 P2-2）：**表格里不得出现「同上」**。
    #   `_dedup_observed` 的"同上"是为**句子**服务的（避免连续两句重复）；放进表格后，
    #   单看该行的读者不知道"上"指哪一行 —— 外部点评实测"多处环节表第３环同上，孤立阅读无意义"。
    #   表格每行都自带「环节」列，故重复值**原样回填**（可独立阅读），不写"同上"。
    def _cell(i: int, node: dict) -> str:
        v = observed_list[i] if i < len(observed_list) else ""
        if v == "同上":
            # ★ 2026-10-02：此处**必须仍走中文化**，不可回填原始 observed。
            #   实测漏网：疑点「对私转账」第 3 环与本环观测值同文本 → 命中"同上"分支，
            #   旧实现把 `matches=人员=初永伟…` / `receipts=275,000.00…` 这类
            #   引擎内部键名**原样回填**进表格，读者看到的是英文变量名而不是数据。
            #   「同上」只是"不再重复播报"的信号，不是"放弃清洗"的信号。
            cur = str(node.get("observed") or "").strip()
            if cur:
                v = _humanize_observed(cur)
            if v:
                return v
            for j in range(i - 1, -1, -1):
                prev = _humanize_observed(str((nodes[j] or {}).get("observed") or "").strip())
                if prev:
                    return prev
            return "与上一环节相同"
        # ★★ 2026-10-03：表格里同样不得拿元信息/倾倒充当"实际看到的数据"（与正文同口径）。
        _k = _obs_kind(v)
        if _k == "meta_read":
            return "—（本环为读取与归集，无独立读数）"
        if _k == "meta_gap":
            return "未取得读数（本轮未提供该资料）"
        if _k == "pile":
            return _obs_lead_fact(v) + "…"
        return v
    return {
        "columns": ["环节", "对应资料", "做了什么", "实际看到的数据"],
        "rows": [
            {"环节": f"第{n.get('step')}环",
             # ★★ 2026-10-03（用户复核疑点2）：**「对应资料」列同样过业态剔除** ——
             #   服务型企业的第4环原写"合同与物流单据"，等于要求它提供天然没有的资料；
             #   段级剔除后保留适用的"合同"（见 `_strip_not_required`）。
             "对应资料": (_strip_not_required(_label_source(n.get("source", "")), not_required)
                          or _label_source(n.get("source", ""))),
             "做了什么": n.get("action", ""),
             "实际看到的数据": _cell(i, n)}
            for i, n in enumerate(nodes)
        ],
    }


def _name_brief(els, limit: int = 3) -> str:
    """把材料清单压成一句**具体资料名**短列（禁模糊套话）。

    ★ 2026-10-01（用户批注「定什么下来/排除什么」）：报告凡报「缺 N 项」，必须点出
      具体资料名——只写「还缺 3 项」读者无从补件，只写「这一项」更无宾语无前指。
      ≤ limit 个：顿号连写（「原始单据、合同与发票」）；
      超过：报「N 项（详见下表）」并指向「三、已取得的资料与待补充的资料」的证据明细表。
    """
    names = [str((e or {}).get("name") or "").strip()
             for e in (els or []) if isinstance(e, dict)]
    names = [n for n in names if n]
    if not names:
        return ""
    if len(names) <= limit:
        return "、".join(names)
    return "%d 项（详见下表）" % len(names)


def _supplement_table(cp_tbl: Optional[Dict], names: List[str],
                      not_required: Optional[List[str]] = None) -> Optional[Dict]:
    """补资料清单表：按**具体材料名**聚合，标出关联的未核对要件与补齐后可核什么。

    ★ 2026-10-04（疑点2 收口）：把 91 条「如实缺料」变成可执行清单。
      之前只说"缺料"，企业不知道**先补哪一份、补完能核出什么**。
      本表回答三问：缺哪几份（具体名）／卡住哪些要件／补完能核什么。

    `cp_tbl` ＝ 构成要件独立核对表（`constituent_checkpoint.checkpoint_table`）。
    `names`   ＝ 该疑点的**具体材料名**（`missing_material_names`）。
    依赖度 = 卡在该资料上的未核对要件条数（= 补它的收益），按此降序 ⇒ 天然优先级。
    """
    _nr = [str(x) for x in (not_required or []) if str(x).strip()]
    _names = []
    for n in (names or []):
        n = str(n or "").strip()
        if not n or n in _names:
            continue
        # 业态不适用：宁可不出（企业天然不会有，要了也白要）
        if _nr and any((n == _m) or (_m in n) for _m in _nr):
            continue
        _names.append(n)
    if not _names:
        return None
    _rows_cp = ((cp_tbl or {}).get("rows") or []) if isinstance(cp_tbl, dict) else []
    out_rows = []
    for _n in _names:
        _hit = []
        for _r in _rows_cp:
            if not isinstance(_r, dict):
                continue
            _src = str(_r.get("独立数据源") or "")
            _st = str(_r.get("数据源状态") or "")
            _cc = str(_r.get("核对结论") or "")
            # ★ 2026-10-04：状态过滤放宽为「凡非已有」——实测许多行的状态是「缺失」，
            #   原过滤只认 未取得/待核 ⇒ 依赖度被算成 0 ⇒ 12 个疑点挂不出清单。
            if _st == "已有" and "未单独核对" not in _cc:
                continue
            if not _src:
                continue
            if _n == _src or _n in _src or _src in _n:
                _hit.append(_r)
        _seqs = "、".join(str(_r.get("要件序号") or "") for _r in _hit[:4]) or "—"
        _what = "；".join(str(_r.get("构成要件") or "") for _r in _hit[:2])
        if len(_what) > 56:
            _what = _what[:56] + "…"
        out_rows.append({
            "待补资料（具体名称）": _n,
            "关联未核对要件": _seqs,
            "补齐后可核什么": _what or "—",
            "依赖度（条）": len(_hit),
        })
    # ★ 2026-10-04：**依赖度 0 的行不单列**——它们没挂到任何具体要件，
    #   “补了能核什么”是—”，属空话占步（项目报告可信度铁律）。
    #   依赖度 = 0 的行数写进 scope_note，不占表行。
    _rows_unchecked = [r for r in _rows_cp
                      if isinstance(r, dict)
                      and "未单独核对" in str(r.get("核对结论") or "")]
    if not _rows_unchecked:
        return None
    _zero = [r for r in out_rows if int(r["依赖度（条）"]) == 0]
    for _z in _zero:
        _z["关联未核对要件"] = "未挂到具体要件"
        _z["补齐后可核什么"] = "该资料是证据链要求，未被任何单条要件单独依赖"
    out_rows.sort(key=lambda r: -int(r["依赖度（条）"]))
    return {
        "title": "补资料清单（按具体材料名，先补依赖度多的）",
        "columns": ["待补资料（具体名称）", "关联未核对要件", "补齐后可核什么", "依赖度（条）"],
        "rows": out_rows,
        "scope_note": ("本清单只列**具体材料名**；已剔除本业态天然不适用的资料；"
                       "依赖度＝卡在该资料上的未核对要件条数，越多越应先补。"
                       + ("另有 %d 项待补资料未挂到具体要件，未单列。" % len(_zero) if _zero else "")),
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


def _build_confirmed_problems(report_data, audit_sink=None):
    """从 findings 组装『确认的具体问题』（level 非待核验/信息的）"""
    # ═══ 新方法论：以「税务红线疑点」为主干（2026-09-06）═══
    _rd = (report_data.get("comprehensive", {}) or {}).get("redline_detection") or {}
    if _rd.get("suspicions"):
        _findings = ((report_data.get("scenario_execution", {}) or {}).get("findings")
                     or report_data.get("all_findings", []) or [])
        # ★ 2026-10-02：按业态把「不适用资料」传进去（如服务型企业的进销存台账），
        #   与 material_readiness 用**同一权威**（业态 skip_domains），避免同一报告两套口径。
        _na_docs2 = _not_required_docs(
            (report_data.get("target_entity") or {}).get("industry"))[0]
        return _build_redline_problems(_rd["suspicions"], _findings,
                                       rate_ctx=(report_data.get("comprehensive", {}) or {}).get("tax_rate_context"),
                                       not_required_docs=_na_docs2,
                                       audit_sink=audit_sink)
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
    # ★★ 2026-10-02（用户定调：一定是先说重要的信息）：顺序显式＝
    #   极高→高→中→低→待核验（`_RISK_PRESENT_ORDER`），同级按潜在敞口金额降序。
    #   正值升序（越大越靠前）+ 金额取负 = 金额大的在前；表外等级一律沉到最末（99），
    #   不再混进高/中之间。
    problems.sort(key=lambda fp: (_RISK_PRESENT_ORDER.get(
                                      str(fp[0].get("level") or "").strip(), 99),
                                  -(_extract_finding_exposure(fp[0])["amount"] or 0)))
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
        # ★ 2026-10-06（用户：「这个要重写，有废话」）：
        #   原文含「须指定熟悉该项业务和资料的负责人，并由另一名人员复核」——
        #   那是**企业内部管理要求**，不是税务风险检查的结论或要求，属废话/越界；
        #   保留其中**真正可验收**的那一半（过程可回查、更正后数据与账务申报一致）。
        #   共用尾句会被 `chapter_dedup` 抽成第四章的「通用要求：…」，故此处不加标签。
        gov = "处理过程能够回查，更正后的数据能与账务、申报资料相互核对一致。"
        plans.append({
            "seq": _cn_num(i + 1),
            "problem": title,
            "narrative": core + gov,
        })
    # ★★ 2026-10-09（P0-5）：**办理顺序的赋值已移出本函数**。
    #   事故：此处早于 `_promote_standalone_to_problems`（域分析项并入）与 `merge_families`
    #   （同族合并删项）执行 ⇒ 之后新增/删除的项**拿不到编号**，而被删项留下的空号
    #   让编号变成 1,2,…,9,11,13,…（门禁 B2 实测「缺号 [8,10,12,16,17]、最大 18 ≠ 项数 16」）。
    #   现收敛到**唯一编号时刻**（报告定稿：重排→重编号→赋办理顺序】，见
    #   `build_enterprise_readable_report` 的「编号定稿」块。
    return plans


def required_doc_coverage(report_data):
    """**必查资料齐备性**的唯一权威（供受阻检查 / 资料齐备性总览 / 总体结论共用）。

    ★★ 2026-10-06（用户评语 #5「检查程序未完成却给总体结论偏强」）：
      原先 `_build_further_checks` 与 `_build_material_readiness` **各算一遍**
      「必查清单 − 已提供 − 本业态不适用」，两处口径一旦漂移，就会出现
      「章首说缺 6 类、章末列 7 项」的自相矛盾；而**总体结论**根本不知道资料受限，
      照样给一个不带上限的整体等级 —— 用户看到的正是"程序没做完，结论却很硬"。

    返回（键名即口径，取不到就如实为空，不臆造）：
      {
        "required": [...本业态适用必查类...],   # 已剔"本业态不适用"
        "na": [...不适用...], "na_reason": {...},
        "provided": [...已提供...], "missing": [...缺失...],
        "total": int, "complete": int, "missing_count": int,
        "limited": bool,        # 检查范围是否受限（= 有缺失）
      }
    """
    covered = _doc_covered_categories(report_data)
    try:
        _na_raw = _not_required_docs(
            (report_data.get("target_entity") or {}).get("industry"))
        # 权威实现返回 `(资料名集合, 说明文本)` —— 说明是**文本**不是字典，原样透传。
        _na_docs, _na_reason = (_na_raw[0] or set()), str(_na_raw[1] or "")
    except Exception:  # noqa: BLE001 —— 业态判定失败不臆断，按"全部适用"处理（偏严）
        _na_docs, _na_reason = set(), ""
    _na_docs = set(_na_docs)
    _required = [c for c in _REQUIRED_DOC_CATEGORIES if c not in _na_docs]
    _provided = [c for c in _required if c in covered]
    _missing = [c for c in _required if c not in covered]
    return {
        "required": _required,
        "na": sorted(_na_docs),
        "na_reason": _na_reason,
        "provided": _provided,
        "missing": _missing,
        "total": len(_required),
        "complete": len(_provided),
        "missing_count": len(_missing),
        "limited": bool(_missing),
    }


def _build_further_checks(report_data):
    """受阻检查：必查资料中**未提交且本业态适用**的类别。

    ★★ 2026-10-03（用户复核第一章："另有 7 项…"与"必查 14 类、进销存台账不适用"自相矛盾）：
      本函数原先只做 `必查清单 − 已提供`，**没有剔除"本业态不适用"的资料** ——
      于是「进销存台账」同时出现在两处：
        · 章首：「本企业业态为服务型…进销存台账不属于必查项，不因未提供而计入缺失」；
        · 章尾：把它列为"未收到导致相关检查未完成"的受限项。
      现与 `material_readiness` **共用同一权威 `required_doc_coverage`**，
      保证"报告说缺什么"与"这里列什么受限"口径一致（不再各算一遍）。
    """
    missing = list(required_doc_coverage(report_data)["missing"])

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
    # ★★ 2026-10-06：齐备性口径**统一走唯一权威** `required_doc_coverage`
    #   （原先此处再算一遍"必查 − 已提供 − 业态不适用"，与 `_build_further_checks`
    #    各算一遍 ⇒ 两处漂移就会出现"章首说缺 6 类、章末列 7 项"）。
    _cov = required_doc_coverage(report_data)
    _required_eff = list(_cov["required"])
    provided = list(_cov["provided"])
    _missing_cats = list(_cov["missing"])
    # 本业态**不适用**资料与原因（唯一权威返回，供下面的 `not_applicable`/`summary_text` 引用）
    _na_docs = set(_cov["na"])
    _na_reason = _cov["na_reason"]

    missing = []
    for cat in _missing_cats:
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
    total = _cov["total"]
    complete = _cov["complete"]
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
        # 按业态**不适用**的资料（如服务型企业的进销存台账）：不计缺失，但必须说明原因，
        # 否则读者会以为"漏要了一份资料"。
        "not_applicable": ({
            "docs": sorted(_na_docs),
            "reason": _na_reason,
        } if _na_docs else None),
        "summary_text": (
            f"本轮检查必查资料共 {total} 类，本轮已提供 {complete} 类、缺失 {len(missing)} 类。"
            + ("资料齐全，全部检查程序可执行。" if not missing
               else "资料不齐全：以下缺失将影响相应风险方向的检查（详见缺失清单）。")
            + (_na_reason if _na_docs else "")
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


def _build_resolution_ledger(report_data, problems=None):
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
    # ★ 2026-09-29（点评整改 P1-13）：**域间联动** —— 把互相印证的发现连起来。
    #   外部点评：所得税贡献率与"小微优惠（应享）"互不引用、私户收款与公户超额代发
    #   未做配对，读者看到两条对立/相关结论却不知须合并判断。判据是**两两结构关系**
    #   （同主体反向资金 / 同税种结论相向 / 同指标不同口径），收敛在 `domain_linkage`。
    _links: Dict[int, list] = {}
    try:
        from engine.domain_linkage import link_findings as _lf, linkage_text as _lt
        _links = _lf(findings)
        _link_txt = {i: _lt(v) for i, v in _links.items()}
    except Exception:
        _link_txt = {}
    by_state = {TERMINAL_IRONCLAD: [], TERMINAL_SELF_PROOF: [], TERMINAL_PENDING: []}
    rows = []
    tier_stat = {}
    for _fi, f in enumerate(findings):
        state = normalize_terminal_state(f.get("terminal_state"))
        if state in by_state:
            by_state[state].append(f)
        tier = str(f.get("evidence_tier") or "")
        if tier:
            tier_stat[tier] = tier_stat.get(tier, 0) + 1
        resolve = f.get("resolve_steps") or []
        proof = f.get("self_proof_materials") or []
        # ★★★ 2026-10-05（用户明确口径：「报告永远不能出现待核实。
        #   从既有资料检查分析，**能确定的风险就是风险**」）
        #   病根：发现层 `level` 有 137/156 条是「**待核验**」—— 那是**证据成熟度**，
        #   不是风险等级；被直接塞进「等级」栏后显示成「待核实」，读起来像"不确定"，
        #   等于把**已从账内算出的确定事实**降格成"还要再看"。
        #   现口径：
        #     · 「等级」栏**只放风险等级**（高/中/低风险）；
        #     · 「待核验」这类**证据成熟度**归「证据地位」栏（那里已有
        #       已验原子规则/域分析结论两档），不混进等级；
        #     · 两者都没有 ⇒ 等级栏写「已列明」（有具体事实，只是未做风险分级），
        #       **不写"待核实"**。
        # ⚠ 「等级」栏只放**风险等级**；发现层无等级或写「待核验」（那是**证据成熟度**，
        #   不是风险大小）时**留空** —— 空值由渲染层整列隐藏，
        #   绝不能拿"已列明/待核实"这类**非等级词**去填等级栏（外行读着别扭，
        #   且会让"等级"列同时表达两种语义）。证据成熟度在「证据地位」栏。
        _lv = str(f.get("level") or "").strip()
        _risk_lv = "" if _lv in ("待核验", "待核实", "待核", "") else _lv
        _tier_full = tier or "未标注"
        if _lv in ("待核验", "待核实", "待核") and tier:
            _tier_full = "%s（证据已固化程度：%s）" % (tier, _lv)
        rows.append({
            "风险事项": str(f.get("type") or ""),
            # ★ 2026-10-05：台账行带 rid（**内部字段**，不进 `_LEDGER_COLUMNS`、不展示），
            #   供 `_merge_ledger_into_problems` 按红线把本行并入对应疑点 ——
            #   用户要求"围绕每一个疑点编排"，同一红线下的多条风险本就是同一件事。
            #   落盘产物里疑点的 `redline_id` 为空，**只能用行上的 rid**，
            #   否则渲染前挂不上、事后也无法复核。
            "_redline_id": str(f.get("redline_id") or "").strip(),
            "等级": _risk_lv,
            "证据地位": _tier_full,
            "终局方向": state or str(f.get("terminal_state") or "待核"),
            "解除方式": "；".join(str(x) for x in resolve[:6]) or "（待补充资料后由系统给出）",
            "需补自证资料": "；".join(
                "{0}——{1}".format(p.get("material", ""), p.get("proves", ""))
                for p in proof[:6] if isinstance(p, dict)
            ) or "（本项尚需的资料见「分析覆盖」章节）",
            # ★ 2026-09-29（P1-13）：域间联动（与哪些发现须合并/配对核实）
            "联动事项": (_link_txt.get(_fi) or ""),
        })
    # ★ 2026-09-29（点评整改 P1-7 / P1-16）：**台账治理** —— 准入过滤（剔除系统自查/
    #   资料请求单等内部工具条目）+ 类型级聚合（"XX逐月不匹配（2025-01）…（2025-12）"
    #   归并为一行、期间落到明细）+ 统一发现 ID（可由规范键复算）+ 与「具体问题」章
    #   的疑点映射。收敛在 `engine/ledger_governance.py`（唯一权威，数据表驱动）。
    _excluded_internal: List[dict] = []
    try:
        from engine.ledger_governance import govern_ledger_rows as _gov
        _g = _gov(rows, findings, problems=problems)
        rows = _g["rows"]
        _excluded_internal = _g["excluded"]
    except Exception as _ge:  # noqa: BLE001
        _excluded_internal = [{"风险事项": "〈台账治理未生效〉", "剔除原因": str(_ge)[:120]}]
    # 台账专列（原 6 列 + 治理新增 3 列）；渲染层会自动隐藏整列为空的列
    _LEDGER_COLUMNS = ["风险事项", "等级", "证据地位", "终局方向", "解除方式", "需补自证资料",
                       "联动事项", "发现ID", "聚合项数", "关联疑点"]
    # ★★ 2026-10-05（用户意见：报告是企业视角，不是覆盖率自证；重复呈现要消除）：
    #   给每行打一个**内部**标记 `_已在问题章详证` —— 该项是否已在第二章「具体问题」
    #   逐条详证（含事实、解除方式、需补自证资料、处理顺序）。
    #   · 有标记 ⇒ 第三章不再重复列行，只做**索引**（避免同一件事说两遍）；
    #   · 无标记 ⇒ 第三章必须完整列示（这是第二章没覆盖的真实风险，一项都不丢）。
    #   ⚠ 该字段以下划线开头 = 内部字段，**不进列**（渲染层不展示），
    #     仅供前端分流；台账总行数与覆盖率口径**不向企业展示**（那是按钮的内部职责）。
    for _r in rows:
        if not isinstance(_r, dict):
            continue
        _r["_已在问题章详证"] = bool(str(_r.get("关联疑点") or "").strip()
                                  and str(_r.get("关联疑点") or "").strip() != "—")
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
        _cp_name = "多税种联动稽查风险画像（%s）" % _labels
        try:
            from engine.ledger_governance import make_finding_id as _mk_id
            _cp_id = _mk_id(_cp_name)
        except Exception:
            _cp_id = ""
        rows.append({
            "风险事项": _cp_name,
            "等级": str(_cp.get("level") or "中风险"),
            "证据地位": "组合风险信号（跨%d个业务环节）" % int(_cp.get("axis_count") or 0),
            "终局方向": "待联动核查（多税种）",
            "解除方式": str(_cp.get("recommendation") or "（待联动核查后由系统给出）"),
            "需补自证资料": "；".join("跨税种联动核查：%s" % t
                                  for t in (_cp.get("combined_taxes") or []))
                              or "（本项详见总体结论章及各项贡献红线台账行）",
            # ★ 2026-09-29（P1-7）：合成行同样要有统一发现 ID（台账内不得有"无名行"）
            "发现ID": _cp_id,
            "聚合项数": "",
            "关联疑点": "",
        })    # ★ 2026-09-25：这两项必须由**最终报告里的发现**现算。
    #   audit_doctrine 汇总是在管道中段生成的（封印/补齐出口之前），
    #   拿它的计数会低估（实测报告 22 条全有出口，汇总里却只写 8 条）。
    # ★ 2026-10-08（P0-1）：计数算法收敛到唯一权威 `report_metrics.ledger_counts`
    #   （此前此处自带一套 for 循环，门禁另算一套 ⇒ 台账写数与验数各写一遍）。
    #   同时**声明本台账的覆盖范围**：它覆盖的是引擎检出明细（all_findings），
    #   与报告正文条目集合（confirmed_problems）**不是一个集合** ——
    #   不声明范围，任何判据都只能拿它跟正文项数比，必然假红。
    from engine import report_metrics as _rm
    _lc = _rm.ledger_counts(findings)
    return {
        "scope": _rm.LEDGER_SCOPE,
        "scope_total": len(findings),
        "total": len(rows),
        "ironclad": _lc["ironclad"],
        "self_provable": _lc["self_provable"],
        "pending": _lc["pending"],
        "with_resolve": _lc["with_resolve"],
        "with_self_proof": _lc["with_self_proof"],
        # ★ 证据地位分布：报告中所有风险已全部呈现，此处标注各结论的取得方式
        "evidence_tiers": tier_stat,
        "evidence_tier_note": (scope.get("note") or ""),
        "statement": str(summary.get("statement") or ""),
        "columns": _LEDGER_COLUMNS,
        # ★ 2026-09-29（P1-16）：被剔除的内部工具条目（不进企业台账，供内部改进清单）
        # ★ 2026-10-05（用户意见：覆盖率/内部动作是企业不需要看到的，属按钮内部职责）：
        #   `excluded_internal` 仍保留在产物里供内部改进清单使用，但**对外一律不展示** ——
        #   展示"剔除了 N 项、转入内部改进清单"等于把内部自查动作写给企业看，
        #   只会让企业去揣测"你到底查了多少、藏了什么"。企业视图只保留风险事项本身。
        "excluded_internal": _excluded_internal,
        "excluded_internal_note": "",
        "rows": rows,
        # ★★★ 2026-10-05（用户：「第二、三、四章应该**融合**，不是物理叠加」）：
        #   把台账里的**真风险**并进第二章对应疑点条目下（`related_risks`），
        #   使报告只呈现**一份清单**：每件事在一处讲完（事实/证据/等级/解除方式/
        #   需补资料/办理顺序/验收标准），不再第二章说一遍、第三章再说一遍。
        #   挂载规则（唯一权威）：`关联疑点` 指向第 N 项 ⇒ 并入该项；
        #   指向为空 ⇒ 独立成条（`standalone_risks`，它们本就是不同的事，
        #   如"关联交易价格偏离""多税种联动画像"，硬挂到别的主题上会张冠李戴）。
        "merged_into_problems": _merge_ledger_into_problems(rows, problems),
        "standalone_risks": [r for r in rows
                            if not r.get("关联疑点")
                            and str(r.get("等级") or "") in ("高风险", "中风险", "低风险")],
    }


def _promote_standalone_reports(out: dict, problems: List[dict]) -> int:
    """把**本身是真风险**的独立底稿立为风险事项（与其它风险同等呈现）。

    ★★★ 2026-10-05（用户：「这真让人想死…你是怎么认为这些内容的？」）：
      `input_voucher_report`（应转出未转出 **3,996.91 元**）因**没有对应红线疑点**，
      被我判"保持独立"，结果降格成一节技术比对，与"系统能力边界/外部数据源核验"
      （都是系统自述、日志）挤在一起。**"没有对应疑点" ≠ "它不是风险"**。
      现在：清单（`report_layout.STANDALONE_RISK_REPORTS`）中的底稿**立为风险事项**，
      用**与红线疑点逐段相同的 7 段结构**呈现。
    """
    from engine.report_layout import STANDALONE_RISK_REPORTS as _S
    if not problems:
        return 0
    _seq = 0
    for _p in problems:
        try:
            _seq = max(_seq, int(_p.get("seq") or 0))
        except Exception:  # noqa: BLE001
            pass
    added = 0
    for _key, _title in _S.items():
        rep = out.get(_key)
        if not isinstance(rep, dict) or not rep:
            continue
        if str(rep.get("verdict") or "") == "未发现异常":
            continue
        _seq += 1
        _sum = str(rep.get("summary") or "").strip()
        _ver = str(rep.get("verdict") or "").strip()
        _met = rep.get("metrics") or {}
        _rec = str(rep.get("recommendation") or "").strip()
        _sigs = []
        for _sg in (rep.get("signals") or []):
            if isinstance(_sg, dict):
                _s = str(_sg.get("signal") or "").strip()
                _h = str(_sg.get("hint") or "").strip()
                if _s:
                    _sigs.append(_s + ("（" + _h + "）" if _h else ""))
            elif _sg:
                _sigs.append(str(_sg))
        # ★★ 2026-10-05（闸门抓到格式泄漏）：`observed_metrics` 里含**嵌套结构**
        #   （如 `examples` = `[{'counterparty': '初永伟', 'receipts': 275000.0, …}]`），
        #   直接 `"%s=%s"` 会把**list/dict 的 repr** 拼进正文 ⇒ 报告出现 `{'k': v}`。
        # ★★ 2026-10-06：拼接统一走**唯一实现** `_metric_kv_text`
        #   （除嵌套结构外，它还把**英文键名**汉化；此前此处拼的是引擎原始英文键）。
        _met_txt = _metric_kv_text(_met)
        problems.append({
            "seq": _seq,
            "title": _title,
            "verdict": _ver or _pending_clue_phrase(),
            "risk_level": "中风险",
            "redline_id": "",
            "source": "专项比对（无对应红线，独立风险事项）",
            "evidence_tier": "专项比对结论（基于上传资料计算）",
            # ★★ 2026-10-08（与组合分支**同一病根**）：同一段 `_sum` 此前被拼进
            #   「为何列入检查」「一、涉及的风险事项」「四、本项结论及理由」**三处**
            #   ⇒ 同一事项内同一段文字出现 3 次（重复率自检的直接来源）。
            #   现每处只保留**各自职责**的内容：触发事实归「为何列入检查」，
            #   结论归「四、本项结论及理由」，互不复述。
            "narrative_paragraphs": [
                {"heading": "为何列入检查",
                 "text": "本项之所以列入检查，是因为在已上传资料中出现了以下情况：" + (_sum or _title)},
                {"heading": "一、涉及的风险事项",
                 "text": "经检查，本项涉及的风险事项为「%s」。被识别的风险信号与量化结果见"
                         "「二、发现的依据」。" % _title},
                {"heading": "二、发现的依据",
                 "text": "".join(_sigs) + ("量化结果：" + _met_txt if _met_txt else "")},
                {"heading": "三、已取得的资料与待补充的资料",
                 "text": "本项依据的独立数据源：进项发票（已上传）。"
                         "尚需结合用途明细账、领用记录与已转出凭证核对是否已作转出。"},
                {"heading": "四、本项结论及理由",
                 # ★★ 2026-10-08（P0-7 同源）：该句是**报告级口径**，唯一权威
                 #   `report_wording.EVIDENCE_BOUNDARY_CLAUSE`（两分支共用一处，禁再手写）。
                 "text": _EVIDENCE_BOUNDARY},
                {"heading": "若不补充资料的后果",
                 "text": "如企业未补充上述资料、也未对相关情况作出合理解释，本项风险方向无法排除，"
                         "可能影响相应期间的申报处理口径；具体后果须依据适用期间、完整事实、证据"
                         "和法定程序，由有权人员复核后认定。"},
                {"heading": "五、需企业提供的资料与说明",
                 "text": "要把这一项查清楚，需要：" + (_rec or "进项用途明细与领用记录、不得抵扣用途的进项税分摊表、已转出凭证。")},
            ],
        })
        added += 1
    return added


def _promote_standalone_to_problems(out: dict, problems: List[dict], report_data: dict = None,
                                    audit_sink=None) -> int:
    """把「另行检出的税务风险事项」**并入第二章**，并用**与疑点相同的段落结构**呈现。

    ★★★ 2026-10-05（用户问：「三、本轮另行检出的税务风险事项为什么不放在第二章？
      为什么不以第二章的表述方式呈现？」）
      **用户是对的**：同一份报告里不该有两种"待遇" ——
      26 个红线疑点有完整论证（为何列入/风险事项/发现依据/资料/结论/怎么改），
      而另有 9 条只给一张表格（等级/解除方式/需补资料）。读者看到的是"二等公民"，
      而且表格里的"解除方式"千篇一律（同一句话套 N 遍），信息量远低于段落式。
      **现在**：这 9 条**并入第二章同一列表**，逐条生成同构段落；
      第三章随之整章下线 —— 报告只有**一份风险清单**。

    ## 数据来源（必须归一化后匹配）
      · 8 条来自 `all_findings`，但**名字已被 `plain_language.TERM_MAP` 改过**
        （finding 原名「…交易核**验**」「…不可见**盲区**」→ 台账名「核**实**」「死角」）
        ⇒ 必须用 `to_plain()` **归一化后再比名**，否则匹配不上（实测漏 2 条）。
      · 1 条（多税种联动画像）来自 `redline_detection.summary.combo_profiles`（组合信号）。
    """
    from engine.plain_language import to_plain as _tp
    rows = list((out.get("resolution_ledger") or {}).get("standalone_risks") or [])
    if not rows or not problems:
        return 0
    # ★★★ 2026-10-05（**真 bug 修复**，用户复核第五章时顺带查出）：
    #   `out` 是**企业报告字典**，它**不含** `all_findings`（那是内部发现，155 条在 report_data 里）
    #   ⇒ 原先 `out.get("all_findings")` 恒为 None ⇒ `_findings` 空 ⇒
    #     `_basis` 空 ⇒ 9 条疑点（序27-35）的「二、发现的依据」**全是兜底空话**
    #     （"（本项依据见「专项能力比对」相应章节）"，而该章已不存在）。
    #   修法：从**源头 `report_data`** 取（`out` 仅用于 resolution_ledger 等报告字段）。
    def _clean_detail(_t: str) -> str:
        """清掉 `detail` 里**嵌的字典字面量**（格式泄漏）。

        ★ 2026-10-05（闸门抓到）：上游 `detail` 里含 Python dict 的 repr
          （如 `{'counterparty': '初永伟', 'receipts': 275000.0, …}`），
          直接拼进正文会**格式泄漏**（报告正文出现 `{'k': v}`）。
          这些 dict 的字段与紧邻的文字**信息重复**（文字已写明对方名称与金额），
          故**整段删除**不丢信息；并规整多余空白与半角标点。
        """
        import re as _re3
        _t = _re3.sub(r"\{[^{}]{0,400}\}", "", str(_t or ""))
        _t = _re3.sub(r"[ \t]{2,}", " ", _t)
        _t = _re3.sub(r"\s+([，。；、）])", r"\1", _t)
        return _t.strip()

    _src = report_data if isinstance(report_data, dict) else out
    _findings = {_tp(str(f.get("type") or "")): f
                 for f in (_src.get("all_findings") or []) if isinstance(f, dict)}
    _combos = {}
    # ⚠ 必须从 `_src`（= `report_data`）取 `comprehensive`，**不能取 `out`** ——
    #   `out` 是**企业报告字典**（`enterprise_readable_report`），它**不含** `comprehensive`
    #   ⇒ 取错源时 `_combos` 恒空 ⇒ 组合画像命不中，其「发现的依据」永远落成
    #     "（本项依据见本报告相应条目内的测算说明）"这种**指针式空话**。
    #   ★ 这与本函数上方已记录的 `out.get("all_findings")` 是**同一个 bug 的第二次出现**
    #     （同一个"外层信封 vs 报告体"混淆）—— 教训：**认准一处取数源后，全函数统一**。
    for _c in (((_src.get("comprehensive") or {}).get("redline_detection") or {})
               .get("summary") or {}).get("combo_profiles") or []:
        if isinstance(_c, dict):
            _nm = "多税种联动稽查风险画像（%s）" % "、".join(_c.get("axis_labels") or [])
            _combos[_nm] = _c
    # ★ 2026-10-06：组合画像的「发现的依据」要**逐环节引用本环节已写明的资料事实**，
    #   故此处按 redline_id 建索引（此时各红线疑点已全部构造完毕）。
    _by_rl = {str(_p.get("redline_id")): _p for _p in (problems or [])
              if str(_p.get("redline_id") or "").strip()}
    _seq0 = 0
    for _p in problems:
        try:
            _seq0 = max(_seq0, int(_p.get("seq") or 0))
        except Exception:  # noqa: BLE001
            pass
    added = 0
    for _r in rows:
        if not isinstance(_r, dict):
            continue
        _name = str(_r.get("风险事项") or "")
        _f = _findings.get(_tp(_name))
        _c = _combos.get(_name)
        _seq0 += 1
        _lv = str(_r.get("等级") or "")
        _basis, _res = [], []
        #: 组合项专用的「为何列入检查」正文（**只讲理由与去向，不复述清单**）。
        _c_why = ""
        #: 组合项专用的「一、涉及的风险事项」正文（= 各环节信号的**紧凑清单**，全事项只此一次）。
        _c_item = ""
        if _f:
            _det = _clean_detail(str(_f.get("detail") or ""))
            _met = _f.get("observed_metrics") or {}
            _srcs = [str(x) for x in (_f.get("independent_sources") or [])]
            if _det:
                _basis.append(_det)
            if _met:
                # ★★ 2026-10-05（闸门抓到格式泄漏；**同一缺陷的第二处**）：
                #   `observed_metrics` 含嵌套结构（`examples` = list of dict），
                #   `"%s=%s"` 会把 list/dict 的 repr 拼进正文 ⇒ 报告出现 `{'k': v}`。
                #   ⚠ 我第一次只改了 `_promote_standalone_reports` 里的同名拼接，
                #     **漏了这一处**（生成序27-35 的就是这里）—— 又一次"同一概念多处实现"。
                # ★★ 2026-10-06：**第三次**同一处又出问题（英文键名入文）。
                #   ⇒ 彻底收敛：两处都改为调**唯一实现** `_metric_kv_text`
                #     （标量过滤 + 键汉化 + 未汉化不写，三件事一处管）。
                _kv = _metric_kv_text(_met)
                if _kv:
                    _basis.append("量化结果：" + _kv)
            if _srcs:
                # ★★ 2026-10-06（用户第 2 批 AC7）：**引擎键名不得进正文** ——
                #   原先直接 join 原始键 ⇒ 报告出现「独立数据源：sal_invs、pur_invs」。
                #   键汉化唯一权威＝`_translate_key`（`_METRIC_CN` 精确映射 + 词表分译）。
                _res.append("本项依据的独立数据源："
                            + "、".join(_translate_key(x) for x in _srcs) + "。")
            if _f.get("conclusion_scope"):
                # 同理：`screening_and_review_only` 这类**枚举值**也要汉化
                _res.append("结论适用范围：%s。"
                            % _translate_key(_f.get("conclusion_scope")))
        elif _c:
            # ★★ 2026-10-06（用户：「来自原子规则/域分析/组合画像/专项比对，你也要有资料站住脚啊！
            #   是资料的哪些情况得清晰梳理吧」）：
            #   组合画像原先的「二、发现的依据」只有两句**程式化空话**
            #   （"本项由跨业务轴组合信号触发：收入、票账差异、资金。组合涉及税种：…"）
            #   —— 没有任何资料事实，条目正文因此落成"（本项依据见本报告相应条目内的测算说明）"
            #   这种**指针式空话**（报告里出现"见别处"= 本项没有自己的依据）。
            #   组合信号本身**不是独立事实**，它的事实就是"构成它的各环节信号同时出现" ——
            #   故此处**逐环节点出该环节的具体资料事实**（取该红线疑点本条已写明的事实句），
            #   让读者一眼看到"是资料的哪些情况"支撑了这一条。
            _by_axis_lbl: dict = {}
            for _cr in (_c.get("contributing_redlines") or []):
                _rid = str(_cr.get("redline_id") or "")
                _p = _by_rl.get(_rid)
                _fact = ""
                for _seg in ((_p or {}).get("narrative_paragraphs") or []):
                    if str(_seg.get("heading") or "").startswith("为何列入检查"):
                        _fact = str(_seg.get("text") or "")
                        break
                # ⚠ 各条模板写法不统一（"是因为在已上传资料中出现了以下情况：" /
                #   "是因为出现了以下情况："），故用**容错剥离**，不能写死一种。
                import re as _re_f
                _fact = _re_f.sub(
                    r"^本项之所以列入检查，是因为(?:在已上传资料中)?出现了以下情况：", "", _fact)
                # ⚠ 正文**禁 markdown**（护栏会再洗一遍，但不能靠它兜底）
                _fact = _fact.replace("**", "")
                # ⚠ 切句必须用唯一权威 `sentencekit.split_sentences`（括号感知）——
                #   朴素 `split("。")` 会在**括号内**切错，切出"金额合计 6,203,1"这种残句
                #   （由闸门 `check_sentence_splitting` 当场拦下，实测正是这么被抓的）。
                try:
                    from engine.sentencekit import split_sentences as _sents
                    _cand = _sents(_fact)
                    _fact = (_cand[0] if _cand else _fact)
                except Exception:                      # noqa: BLE001
                    _fact = _fact
                if len(_fact) > 110:
                    # 只在**不在括号内**的位置截断，避免切出残缺括号
                    _fact = _fact[:110].rstrip("，、；：（(")
                    _fact += "…"
                _by_axis_lbl.setdefault(str(_cr.get("axis_label") or "环节"), []).append(
                    (str(_cr.get("redline_name") or _rid),
                     # ★ 2026-10-15：叙述里的等级词走展示权威（裸「待核验」不得进正文）
                     _display_label(str((_p or {}).get("risk_level") or "待核验")),
                     _fact))
            # ★★ 2026-10-08（重复率自检阻断的**最大单项**）：同一份「各环节信号清单」
            #   此前被拼进**三处**（「为何列入检查」「一、涉及的风险事项」「二、发现的依据」）
            #   ⇒ 同一事项内同一清单出现 3 次（实测该事项冗余 1,780 字、单章重复率 60%，
            #   整体重复率被它一项顶过 10% 阈值）。
            #   现按**用途**分两级、每级只出现一次（数据驱动，新增环节无需改分支）：
            #     · 环节清单（子项名+等级，紧凑）→「为何列入检查」：回答"凭什么列入"；
            #     · 逐环节资料事实（子项名+等级+该环节已写明的事实）→「二、发现的依据」：
            #       回答"是资料的哪些情况"。
            _cmp_items, _det_items = [], []
            for _ax, _items in _by_axis_lbl.items():
                _cmp_items.append("· %s环节——%s" % (_ax, "；".join(
                    "%s（%s）" % (_n, _l) for _n, _l, _ in _items)))
                _det_items.append("· %s环节——%s" % (_ax, "；".join(
                    ("%s（%s）%s" % (_n, _l, ("：" + _fx) if _fx else ""))
                    for _n, _l, _fx in _items)))
            _c_why = ("本项为组合项——%s各业务环节的信号**同时出现**后才合成联动信号"
                      "（任一环节单独出现只作提示；多环节同时异常才提示多税种联动稽查）；"
                      "构成明细见本项「一、涉及的风险事项」，逐环节的资料事实见「二、发现的依据」。"
                      % ("、".join(str(_x) for _x in _by_axis_lbl.keys()) or "多个"))
            _c_item = ("本项由下列各业务环节的信号同时出现后合成："
                       + "".join(_cmp_items)) if _cmp_items else ""
            _basis.append(
                "本项不是独立事实，而是下列各业务环节的信号**同时出现**后合成的联动信号"
                "（任一环节单独出现只作提示；多环节同时异常才提示多税种联动稽查）："
                + "".join(_det_items))
            _basis.append("组合涉及税种：%s。" % "、".join(_c.get("combined_taxes") or []))
            if _c.get("recommendation"):
                _res.append(str(_c.get("recommendation")))
        _need = str(_r.get("需补自证资料") or "").strip()
        # ★★ 2026-10-09（P0-5 七环 schema 收敛 —— 消灭"第二套段落 schema"）：
        #   域分析发现此前**自行拼** 7 段，环名与红线分支不同、且缺「推导链／要件清单／
        #   结论句／后果段」，又不写 `conclusion_grade`、不进办理顺序 ⇒ 门禁 A4/B2 实测报错。
        #   现环名与环序由**唯一权威** `engine/report_ring_schema.RINGS` 决定：
        #   本分支只提供「环的内容素材」，环叫什么、排第几、是否必填全由 schema 决定。
        _trigger_txt = "本项之所以列入检查，是因为在已上传资料中出现了以下情况：" + (
            _c_why or (_basis[0] if _basis else _name))
        # 推导链：域分析项的"从资料一步步读出来"＝其**域信号合成过程**（如实陈述，不臆造步骤）
        _derive_txt = ("本项不是凭印象得出的，是从已上传资料里按业务环节信号逐步读出来的："
                       "「%s」对应的各业务环节信号在同一轮分析中同时出现，才合成为本项"
                       "（任一环节单独出现只作提示）。逐环节读到的资料事实见本段。%s"
                       % (_name, ("".join(_basis) if _basis else "")))
        # 要件清单（判定要点）：域分析项**不是**红线构成要件，故**明确标注来源差异**，
        #   只列"判定要点"，避免读者误以为它也有法定构成要件。
        _crit_txt = ("本项属域分析结论，其判定要点如下（**非**红线法定构成要件清单）："
                     "①该业务环节信号是否确实来自本企业已上传资料；"
                     "②各环节信号之间能否相互印证（而非孤立出现）；"
                     "③是否存在可复核的相反证据足以排除本项。")
        # 结论句：域分析项的合规裁决语（只到"账内已读到信号"这一层，不越界定性）。
        _concl_txt = ("综合以上，本项结论是：账内已读到与「%s」指向一致的信号，"
                      "但尚未认定到构成要件成立、材料也不够齐全 ⇒ 只作须核对疑点登记，"
                      "待企业补充材料后重新核对。本项等级为%s。%s"
                      % (_name, _lv, _EVIDENCE_BOUNDARY))
        try:
            from engine.report_ring_schema import build_rings as _build_rings
            _rings = _build_rings({
                "trigger": {"heading": "为何列入检查", "text": _trigger_txt},
                "risk_item": {"heading": "一、涉及的风险事项",
                              "text": "经检查，本项涉及的风险事项为「%s」，风险等级 %s。%s"
                                      % (_name, _lv, _c_item or "")},
                "basis": {"heading": "二、发现的依据", "text": _derive_txt},
                "materials": {"heading": "三、已取得的资料与待补充的资料",
                              "text": ("".join(_res) or "本项资料齐备度见报告「资料完备度」说明。")
                                      + ("尚缺：%s。" % _need if _need else "")},
                "conclusion": {"heading": "四、本项结论及理由",
                               "text": _crit_txt + _concl_txt},
                "request": {"heading": "五、需企业提供的资料与说明",
                            "text": ("要把这一项查清楚，需要：" + _need) if _need
                                    else "本项结论可通过现有资料复核；如企业有相反证据，请提供并说明。"},
            }, ctx={"need": _need, "risk_level": _lv,
                    "taxes_txt": "、".join(str(x) for x in (_r.get("涉及税种") or []) if str(x).strip())})
        except Exception as _rs_err:  # noqa: BLE001 —— 不静默：结构收敛失败必须可见
            _audit_note(audit_sink, "域分析七环收敛失败", _rs_err, title=_name)
            _rings = [
                {"heading": "为何列入检查", "text": _trigger_txt},
                {"heading": "一、涉及的风险事项",
                 "text": "经检查，本项涉及的风险事项为「%s」，风险等级 %s。%s"
                         % (_name, _lv, _c_item or (_basis[0] if _basis else ""))},
                {"heading": "二、发现的依据", "text": _derive_txt},
                {"heading": "三、已取得的资料与待补充的资料",
                 "text": ("".join(_res) or "本项资料齐备度见报告「资料完备度」说明。")
                         + ("尚缺：%s。" % _need if _need else "")},
                {"heading": "四、本项结论及理由", "text": _crit_txt + _concl_txt},
                {"heading": "若不补充资料的后果",
                 "text": "如企业未补充上述资料、也未对相关情况作出合理解释，本项风险方向无法排除，"
                         "可能影响相应期间的申报处理口径；具体后果须依据适用期间、完整事实、证据"
                         "和法定程序，由有权人员复核后认定。"},
                {"heading": "五、需企业提供的资料与说明",
                 "text": ("要把这一项查清楚，需要：" + _need) if _need
                         else "本项结论可通过现有资料复核；如企业有相反证据，请提供并说明。"},
            ]
        problems.append({
            "seq": _seq0,
            "title": _name,
            # ★ 2026-10-08：补「未认定」声明 —— 该句式会被 `text_guardrails.audit_wording` 的
            #   W2 判据命中（称"已查明的风险"却未声明未认定，读者会误以为已定性）。
            # ★★ 2026-10-08（P0-2 用语权威收口）：改由 `conclusion_grade.pending_clue_phrase`
            #   生成（去掉定性词"已查明"、自动带 L2 必需的「待核」「不作定性」）。
            "verdict": _pending_clue_phrase(source_note="另行检出的域分析结论"),
            # ★★ 2026-10-09（P0-5）：域分析项同样登记**结论等级**（门禁 A4 要求），
            #   口径与红线疑点一致 —— 由用语映射唯一权威 `conclusion_grade.map_verdict` 得出，
            #   不自行硬编码 "L2"。
            #   ⚠ 旧实现引用了**未定义**的 `_grade_from_verdict`（NameError，本轮真跑会崩）——
            #     这正是本项目"未定义名"病根的又一次出现，闸门 `check_undefined_names` 已上锁。
            "conclusion_grade": _cg_map_verdict(_pending_clue_phrase())[0],
            "risk_level": _lv,
            "redline_id": "",
            "source": "域分析发现",          # 与红线疑点区分来源（不改变呈现方式）
            "evidence_tier": str(_r.get("证据地位") or ""),
            "narrative_paragraphs": _rings,
        })
        added += 1
    return added


def _merge_ledger_into_problems(rows: List[dict], problems: List[dict]) -> int:
    """把台账行**并进对应疑点**的 `related_risks`，返回并入条数。

    ★ 2026-10-05（用户要求：**围绕每一个疑点编排**，一节讲完一件事）。
    挂载判据（唯一权威，两级，**不靠关键词猜测**）：
      ① **`redline_id` 相同** —— 最精确：同一红线下的多条风险本就是同一件事，
         例：疑点「资金回流与公私混同检测」(RL-FUND-002) 与台账项
         「资金回流与公私混同检测」「公私混同发薪/私户支付薪酬」同属该红线。
      ② `关联疑点` 文本里的序号（「具体问题第3项」）—— rid 缺失时的兜底。
    ⚠ 实测教训：落盘产物里疑点的 `redline_id` 为空（渲染层不带出），
      但**本函数运行在渲染之前**，`problems` 此刻**是带 rid 的** ⇒ 必须在这里用 rid，
      事后从产物反查是查不到的。
    """
    import re as _re
    if not rows or not problems:
        return 0
    by_seq = {}
    by_rid = {}
    for p in problems:
        if not isinstance(p, dict):
            continue
        sq = str(p.get("seq") or "").strip()
        if sq:
            by_seq[sq] = p
        rid = str(p.get("redline_id") or "").strip()
        if rid and rid not in by_rid:
            by_rid[rid] = p
    n = 0
    for r in rows:
        if not isinstance(r, dict):
            continue
        tgt = by_rid.get(str(r.get("redline_id") or "").strip())
        if not tgt:
            m = _re.search(r"第\s*(\d+)\s*项", str(r.get("关联疑点") or ""))
            if m:
                tgt = by_seq.get(m.group(1))
        if not tgt:
            continue
        # ★★ 2026-10-06（用户：「疑点1的『本项还包含以下风险信号』，这部分内容不是已经在一至五里
        #   说了吗？」）：**是重复** —— 被并进来的那一行**就是本项自己的来源行**。
        #   实测：疑点1「红字冲销与作废发票比例异常」下面又列出一条"相关风险信号"
        #   「红冲/作废发票情形」——而本项「为何列入检查」段开头写的正是
        #   "红冲/作废发票情形（共13笔）…"，同一个东西说两遍。
        #   根因：归属判据只问"这行属于哪个疑点"（`redline_id` / `关联疑点` 序号），
        #   **没有问"这行是不是本项自己的来源"** —— 而来源行必然也指向本项
        #   ⇒ 必然被并回来一次（实测 11 个疑点、14 行）。
        #   判据（数据驱动，不靠关键词猜）：行的「风险事项」归一化后**出现在本项标题、
        #   或本项「为何列入检查」段的前 60 字内** ⇒ 它就是这个疑点的来源事项，不再作为
        #   "额外风险信号"重复列出。（段0 开头就是来源表题或来源事实。）
        #   ⚠ 判据必须与闸门 `check_related_risks_not_self` **逐字一致**（同一口径两处实现=事故）。
        _nm = _re.sub(r"[\s（）()【】\[\]·，,、]", "", str(r.get("风险事项") or ""))
        if _nm:
            _seg0 = ""
            for _sg in (tgt.get("narrative_paragraphs") or []):
                if str(_sg.get("heading") or "").startswith("为何列入检查"):
                    _seg0 = str(_sg.get("text") or "")
                    break
            _ctx = (_re.sub(r"[\s（）()【】\[\]·，,、]", "", str(tgt.get("title") or ""))
                    + "|" + _re.sub(r"[\s（）()【】\[\]·，,、]", "", _seg0[:60]))
            if _nm in _ctx:
                continue                      # 本项自己的来源行 ⇒ 不重复列出
        tgt.setdefault("related_risks", []).append({
            "风险事项": r.get("风险事项", ""),
            "等级": r.get("等级", ""),
            "终局方向": r.get("终局方向", ""),
            "解除方式": r.get("解除方式", ""),
            "需补自证资料": r.get("需补自证资料", ""),
        })
        n += 1
    return n


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


def _resync_summary_counts(out) -> dict:
    """把 `summary` 里**由事项列表派生**的计数，统一按**定稿列表**重算 —— **唯一权威**。

    ★★ 2026-10-08 根因修复（用户：「summary.pending_problem_count=26 与
      confirmed_problem_count=16 口径不符，属数据侧老缺陷」）：
      `_build_summary()` 在**列表定稿之前**执行（拿的是当时那份列表），
      而定稿发生在 `_promote_standalone_to_problems` / 同族合并 / 主题收口之后；
      原实现在两处补丁里**各自只同步了 `confirmed_problem_count`**，
      它**同源的兄弟字段** `pending_problem_count` 被漏掉
      ⇒ 报告出现「已确认 16 项 / 待核 26 项」自相矛盾（26 也不是任何真实列表的长度）。

    为什么必须收敛成一个函数：**只要"同一个列表派生多个计数"，逐个补字段必然漏**
    （本项目同一坑已复发多次）。此后**新增任何列表派生计数，只加在这里**，
    调用方一律只调本函数，不得再手改 `summary[...]`。

    ⚠ 计数只允许有**一个定稿时刻**：列表定稿之后（调用点见
      `_promote_standalone_to_problems` 之后 与 「计数定稿」块）。

    返回重算后的计数（供日志自证）。
    """
    sm = out.get("summary")
    if not isinstance(sm, dict):
        return {}
    problems = [p for p in (out.get("confirmed_problems") or []) if isinstance(p, dict)]
    further = [f for f in (out.get("further_checks") or []) if isinstance(f, dict)]
    completed = out.get("completed_checks")
    verified = sum(1 for p in problems
                   if str(p.get("conclusion_grade") or "") == "已核定")
    sm["confirmed_problem_count"] = len(problems)
    sm["verified_problem_count"] = verified
    # 「待核」= 已确认 − 已核定（**不另起一套口径**，否则又是两个来源）
    sm["pending_problem_count"] = len(problems) - verified
    sm["further_check_count"] = len(further)
    if isinstance(completed, list):
        sm["completed_check_count"] = len(completed)
    return {
        "confirmed": sm["confirmed_problem_count"],
        "verified": sm["verified_problem_count"],
        "pending": sm["pending_problem_count"],
        "further": sm["further_check_count"],
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
            "body": "本轮跨企业关系检测已完成：系统内企业之间的供应商、客户、法定代表人及关键人员均未形成需进一步追查的重合。此结论仅基于本轮可读取的企业主体与发票往来数据；如存在未纳入系统的关联企业，须通过外部工商股权穿透补充核查（该方向不在本报告覆盖范围内，须由风险检查员结合外部数据与下户取证另行核实）。",
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
            # ★ 2026-09-29（点评整改）：原始 HTTP 错误码不出正式文书，转业务语言
            _err = str(res.get("error", ""))
            if "403" in _err or "Forbidden" in _err:
                _err = "访问被拒绝"
            elif "timed out" in _err.lower() or "timeout" in _err.lower():
                _err = "连接超时"
            else:
                _err = (_err[:24] or "未知原因")
            chan_summary.append(f"{ch}：未响应（{_err}）")
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
    # ★ 2026-10-06：原此处另有一张 `_rank = {...}`（与本模块其它等级表**并列第三张**），
    #   实为**死代码**（定义后无任何引用），已删除 —— 等级标度只留唯一权威 `risk_levels`。
    #   主线研判的排序另见下方 `_high_by_theme`（只判"是否高风险"，不比较高低）。

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
    # ★ 2026-10-06：等级名一律走**展示权威** `risk_levels.display_label`
    #   （待核验 → 「已列明」）。正文里若出现权威名「待核验」，会被下游
    #   `plain_language` 通俗化成「尚需核实」——那同样是用户明令禁止的词。
    _lv_txt = "、".join("%s %d 项" % (_display_label(k), v)
                        for k, v in lv_counts.items() if v)
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
        # ★ 指标汉化唯一权威 `industry_benchmark.indicator_label`（2026-10-07 收敛，原为本地第二份手工表）
        label = _bench_indicator_label(key) or key
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
        "note": f"预警区间为{_BENCH_CAUTION}；"
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

# ★★ 2026-10-06：以下三张表**全部转为薄转发**（唯一权威 `engine.risk_levels`）。
#   历史事故：本模块 `_LEVEL_RANK` / `_RISK_PRESENT_ORDER` / 内联 `_rank`，与
#   `pipeline::_sev` / `finding_families::_LV_RANK` **各自维护**且**对「信息 vs 低风险」
#   给出相反答案** ⇒ 同一事项在不同章节被判成不同等级（用户评语 #1）。
#   保留旧名字是为了不破坏既有闸门对 `_RISK_PRESENT_ORDER` 的"唯一权威"断言，
#   但值一律来自权威表，本模块**不再自建任何等级标度**。
#   ★ 注意：`_LEVEL_RANK` 在本项目**已无调用点**（`_level_rank` 亦无调用），故不再保留。

#: 疑点**呈现顺序**（越小越靠前）：风险由重到轻，「待核验/信息」为证据状态放最末。
_RISK_PRESENT_ORDER = _RISK_PRESENT_ORDER_AUTH

#: 风险等级的**合法集合**（权威词表；与 `audit_consistency.check_finding_level_legality` 同源）。
_LEGAL_RISK_LEVELS = _LEGAL_RISK_LEVELS_AUTH


def _normalize_risk_level(level: Any) -> str:
    """把疑点等级规范到权威词表；**词表外一律归「信息」**（薄转发 `risk_levels.normalize`）。

    为什么必须规范（2026-10-02 用户问"为什么不是从高风险开始"时牵出）：
      税收优惠分析器产出的发现 `level="优惠机会"`（机会流 vocabulary），被红线引擎归到
      "未按规定安排残疾人就业且未申报缴纳残保金"后进了**风险疑点**章节，
      报告于是出现 `风险等级=优惠机会` —— 它不是风险等级，读者无从理解；
      而且它不在呈现顺序表里（会取 99 沉到最末），与其它等级混排时顺序更乱。
    口径：词表外 ≠ 丢弃该疑点，而是**归入「信息」档**（呈现顺序最末），如实保留事项。
    """
    return _normalize_level(level)


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

    # ★★ 2026-10-02（用户：给一键分析写入一套"自我审查"思考体系）：
    #   报告在编制**具体问题**章时，同步对自己"要写进去的内容"做主体一致性自检
    #   （疑点主体 ↔ 自己的支撑发现 ↔ 拟挂附表），判定结果累计到 `_sc_audit`，
    #   由本函数末尾写入报告（`subject_consistency_audit`）与一键分析流水。
    #   自检**不改事实、不隐藏**：不匹配时报告如实声明认定范围，并记明原因供复核。
    _sc_audit = {"issues": [], "by_code": {}}
    problems = _build_confirmed_problems(report_data, audit_sink=_sc_audit)
    completed = _build_completed_checks(report_data)
    materials = _build_materials(report_data)
    procedures = _build_procedures(report_data)
    further = _build_further_checks(report_data)
    summary = _build_summary(report_data, problems, completed, further)
    plans = _build_action_plan(problems)
    # ★ 2026-09-29（点评整改 P1-8 / P2-7）：**章节内模板句去重**（S6「通用口径只说一次」）。
    #   实测「资料接收与保全」章 9 条 narrative、**「风险检查处理意见」章 25 条 narrative**
    #   每条都以同一段通用说明结尾（后者 89 字 × 25 次）—— 即点评所说"模板重复约四成"。
    #   现把各章共有的**结尾模板**抽到**章首说明一次**，条目内只留差异部分（不改任何事实）。
    #   收敛在 `chapter_dedup.collapse_common_tail`（阈值外置；新增章节只加一个键名）。
    _chapter_notes = {"materials_note": "", "action_plan_note": ""}
    try:
        from engine.chapter_dedup import collapse_common_tail as _cct
        materials, _n1 = _cct(materials, "narrative")
        _chapter_notes["materials_note"] = _n1
        plans, _n2 = _cct(plans, "narrative")
        _chapter_notes["action_plan_note"] = _n2
    except Exception:
        pass
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
    resolution_ledger = _build_resolution_ledger(report_data, problems=problems)
    # ★ 2026-09-26 三版重构：底稿版（检查组工作底稿）
    working_paper_report = _build_working_paper_report(report_data)
    # ★ 2026-09-26 用户要求：「一、本轮检查总体结论」必须从 findings 实测派生（不得手写模板）。
    #   数字/点名清单/涉及税种/行业口径全部取实测，新增或减少发现无需改代码。
    from engine.overall_conclusion import build_overall_conclusion
    overall_conclusion = build_overall_conclusion(
        report_data, problems, further, inspector_reasoning)
    # ★ 2026-09-29（点评整改 P0-7）：成本两口径明细**先于**总述构建，
    #   供「关键口径对照」直接引用同一数值（单一来源，不重算）。
    from engine.cost_recon_detail import build_cost_recon_detail
    cost_recon_detail = build_cost_recon_detail(report_data)
    # ★★★ 2026-10-05（用户：「这些内容……就不能融入相关的板块中去？」）
    #   把**专项比对**挂进**它讲的那个疑点** —— 读者在一个地方看到"结论 + 全部论证"，
    #   不必在末尾"专项能力比对"一节里自己对应"哪段是给哪个疑点的"。
    #   映射唯一权威：`engine/report_layout.SPECIAL_TO_PROBLEM`（数据驱动，新增只加一行）。
    #   挂载失败的（外部核实通道 / 能力边界）**保持独立**，它们讲的不是某一个疑点。
    _spec_kinds = {
        "bank_flow_report": bank_flow_report,
        "revenue_authenticity_report": revenue_authenticity_report,
        "two_tax_report": two_tax_report,
        "fund_loop_report": fund_loop_report,
        "cross_enterprise_report": cross_enterprise_report,
        "false_invoice_report": false_invoice_report,
        "cost_recon_detail": cost_recon_detail,
    }
    _spec_attach_errors: List[str] = []
    try:
        from engine.report_layout import (
            match_problem as _mp, report_title as _rt, has_content as _hc,
        )
        for _p in problems:
            if not isinstance(_p, dict):
                continue
            for _k, _rep in _spec_kinds.items():
                # ⚠ 判据是"有内容"，不是 `available`（实测 cross_enterprise_report
                #   无 available 键 ⇒ 该项被漏挂）
                if not _hc(_rep):
                    continue
                if not _mp(_p.get("title"), _k):
                    continue
                _p.setdefault("related_analyses", []).append({
                    "key": _k,
                    "title": _rt(_k, _rep),
                    "data": _rep,
                })
                # ★ 2026-10-05（用户：「已并入疑点15，还有单独呈现的必要吗？」）：
                #   标记该底稿**已被某条疑点承载** ⇒ 前端不再单设同名章节
                #   （"一件事只讲一次"）；无任何疑点承载时仍保留单独章节作兜底。
                if isinstance(_rep, dict):
                    _rep["_carried_by_problem"] = True
    except Exception as _se:  # noqa: BLE001
        # 项目惯例：异常**写进产物**（让失效可见、可复核），不只打日志
        _spec_attach_errors.append(str(_se)[:160])
        print("[专项比对挂载] 失败：%s" % _se)

    # ★★★ 2026-10-05（用户追问「这些内容就不能融入到第二章吗？」——**问了三次**，
    #   说明我前两轮只加"指针"没做到"并入"）：
    #   现在把**资料缺口的完整说明**（本轮检查结论／被阻断的检查和风险影响／
    #   补充资料要求／下一轮复查程序 四段）**整段挂到它影响的疑点**，
    #   并在第二章之后**整章下线**「因资料缺失而无法完成的检查」章 ——
    #   报告自此只有一份叙事：每件事在它所属的疑点里讲完。
    #   判据唯一：疑点自己声明的**「独立数据源」**（`report_layout.extract_sources`）。
    #   ⚠ **不能**用资料类别全文搜：疑点2 正文含"劳动**合同**"，会被"合同文件"误挂；
    #     而它的数据源是"工资表、社保明细"，本不依赖购销合同。
    try:
        from engine.report_layout import extract_sources as _ex_src, gap_category_hit as _gap_hit
        import re as _re2
        _gap_cats: List[str] = []
        _fc_by_cat: Dict[str, dict] = {}
        for _f in (further or []):
            _m = _re2.search(r'[“"]([^”"]+)[”"]', str(_f.get("title") or ""))
            if _m and _m.group(1) not in _fc_by_cat:
                _gap_cats.append(_m.group(1))
                _fc_by_cat[_m.group(1)] = _f
        if _gap_cats:
            for _p in problems:
                if not isinstance(_p, dict):
                    continue
                _srcs = _ex_src(_p)
                _hit = [c for c in _gap_cats if _gap_hit(_srcs, c)]
                if _hit:
                    # 类别名（简短提示用）+ 完整说明（提供四段原文，供前端整段呈现）
                    _p["material_gaps"] = _hit
                    _p["material_gap_notes"] = [
                        {
                            "类别": c,
                            "段落": list((_fc_by_cat.get(c) or {}).get("narrative_paragraphs") or []),
                        }
                        for c in _hit
                    ]
    except Exception as _ge:  # noqa: BLE001
        print("[资料缺口挂载] 失败：%s" % str(_ge)[:160])

    # ★★★ 2026-10-05（同上一并处理：用户追问「这些内容就不能融入到第二章吗？」）：
    #   询问清单里**指向具体疑点**的主题，整条挂到该疑点（`questions`）；
    #   报告末尾只保留**无对应疑点的主题**。
    #   归属表唯一权威：`report_layout.QUESTION_THEME_TO_PROBLEM`；
    #   挂载逻辑唯一实现：`report_layout.attach_question_themes`。
    #   ⚠ **挂载必须放在「并入独立风险事项」之后**（见函数末尾）——
    #     事故（2026-10-06）：本段原在此处（早于 `_promote_standalone_reports`），
    #     而「进项异常凭证」正是**由那次并入才产生**的风险事项
    #     ⇒ 挂载时它还不存在 ⇒ 「进项，应转出未转出」找不到归属 ⇒ 被丢进报告末尾残余章。
    #     即"顺序错了 ⇒ 归属表写对了也不生效"。

    # ★ 2026-09-26 工作底稿版「检查情况总述」：基本情况 / 风险类型 / 风险程度 /
    #   对企业总体看法 / 监管态度（分级建议）/ 边界声明
    from engine.inspection_overview import build_inspection_overview
    inspection_overview = build_inspection_overview(
        report_data, problems, further, overall_conclusion,
        cost_recon_detail=cost_recon_detail)
    # ★ 2026-09-27：主营业务成本「两口径勾稽明细」（发票类目构成 / 账面构成 / 差异归因），
    #   无论是否超阈值都产出（合规留痕）。发票构成取自 pipeline 已算好的 core_cost 拆分（单一权威），
    #   本模块不重跑 classify，避免口径分叉。
    # ★ 2026-09-27（P1）：本轮潜在税额敞口汇总（分税种 + 已量化/未量化覆盖度）
    try:
        from engine.tax_impact import build_tax_impact_summary as _btis
        _tax_impact_summary = _btis(
            problems, ctx=(report_data.get("comprehensive", {}) or {}).get("tax_rate_context"))
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
    #   ★ 2026-09-29（P1-11）：派生必须以**同一份已轴归一化 + 表治理的 `out`** 为源，
    #     不能拿未经处理的 `report_data` 另开一路（旧顺序下派生视图会绕过输出闸门，
    #     实测确认过「工作底稿版已脱敏、派生版仍带真实姓名」）。故此处只留 `_identity`，
    #     派生动作移到底部、以 `out` 的归一化内容为源。
    _identity = _identity_from_report_data(report_data)

    # ★ 2026-10-02（用户定调）：**企业版报告不做个人信息脱敏，且禁止任何隐藏/遮盖**。
    #   原收敛点 `engine/pii_guard.py`（杨莹→杨*、初永伟→初**）已整体删除：本报告的
    #   读者是**被查企业本身**，员工姓名、私户收付金额正是企业需要逐人核对的内容；
    #   把姓名打成 `杨*` 只会让「逐人说明」这条核查要求无法落地（用户实测反馈：
    #   疑点3 显示「需逐人说明：杨*」）。内部工作底稿（comprehensive / all_findings）
    #   **本就不脱敏**，对外交付版同口径。
    #   ⚠ 防复发闸门：`tools/audit_consistency.py` 的禁止脱敏检查
    #   （模块缺失 + 全库 AST 禁引用脱敏符号 + 报告实测无「首字+等长星号」脱敏形态）。
    def _norm_and_redact(_o):
        try:
            _o = _zh_normalize_obj(_o)
            # ★ 2026-09-29（点评整改 P1-14）：**明细表治理**（唯一规范化点）。
            #   必须放在 `_zh_normalize_obj` **之后**：正因为它会把值里的半角括号
            #   规范成全角、而**不动字典键**，才造成 columns='金额（元）' 与
            #   行键 '金额(元)' 不一致、整列渲染为空（实测的静默数据丢失）。
            #   此处统一对齐列名/行键、剔除内部列、注明截断。
            try:
                from engine.table_governance import govern_all_tables as _gt
                _o = _gt(_o)
            except Exception:
                pass
            return _o
        except Exception:
            return _zh_normalize_obj(_o)


    out = _norm_and_redact({
        # ★★ 2026-10-07（质检 P0-2）：报告名称必须来自**合规唯一权威**
        #   `engine.report_compliance.document_meta()`，而不是硬编码"涉税风险检查工作报告"。
        #   事故：第 5 批已把名称/签名栏/保密/授权/系统标识/申辩做成配置，
        #   但**只挂在 `report_data`，没有进 `enterprise_readable_report`**
        #   ⇒ 导出 docx 时全部丢失（用户在 docx 里数到「税务风险扫描工作底稿」「编制人」「保密等级」各 0 次）。
        #   口径：取不到就**保留原名称**（不阻断），并在 `compliance_unavailable` 留痕。
        "compilation_style": _doc_display_name(),
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
        # 专项比对挂载失败信息（空=全部挂载成功；非空=有专项没进对应疑点，须复核）
        "special_attach_errors": _spec_attach_errors,
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
        # ★ 2026-09-29（P1-8/P2-7）：被抽出的章节通用说明（章首渲染一次）
        "materials_note": _chapter_notes.get("materials_note") or "",
        # ★ 2026-09-29（P1-8/P2-7）：整改处理意见章被抽出的通用说明（章首一次）
        "action_plan_note": _chapter_notes.get("action_plan_note") or "",
        "confirmed_problems": problems,
        # ★ 2026-10-02：主体一致性自检结果（疑点主体 ↔ 所写内容）。内部核对用；
        #   同时写入一键分析流水，使"自检真的跑过、跑出什么"可被复核与回归。
        "subject_consistency_audit": _build_subject_audit(problems, _sc_audit),
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
        # ★ 2026-10-06（用户：「这个要重写，有废话」）：
        #   ① trigger 原写「**重新点击一键分析**」= 系统操作说明（按钮怎么点是企业不需要知道的）；
        #   ② work 原写「**下一轮将重新读取全部资料**」= 系统动作描述（"我怎么做的"），
        #      与企业该做什么无关；保留的是"复查什么、看什么变化"。
        #   ③ convergence 原句尾「才表示企业正在趋于合规」与标题重复 ⇒ 精简。
        "recheck": {
            "trigger": "完成真实整改或补充资料后，即重新检查。",
            "work": "复查本轮问题是否处理完成，检查补充资料是否带出新的关联事项，"
                    "并对照前后两轮的变化。",
            "convergence": "问题逐项处理、资料逐步完整、账务与申报能够相互核对；"
                           "不能以问题数量归零或分数下降单独判断。",
        },
        # ★★★ 2026-10-05（用户复核第五章：「是不是有内容在报告中是重复的？」）
        #   **核实后确认 4 处重复，删除 3 条**：
        #   · 原说明1「只对本轮已上传资料负责，未上传不在认定范围」
        #     ⇒ 与**第三章（覆盖范围声明）**"本报告的结论仅基于企业本轮已上传的资料"**重复**
        #   · 原说明5「账外经营、私户收款…须依赖外部数据源，详见「能力边界与彻底风险检查路线」章节」
        #     ⇒ 与**第三章**（同样点名"账外经营、私户收款…不在覆盖范围"）**重复**，
        #        且**引用了一个已被删除的章节**（该章本轮改为「覆盖范围声明」）—— 指向失效
        #   · 原说明3「采用…文书式结构编制…用于企业合规整改」
        #     ⇒ 与**"文书性质说明"**（"用于模拟税务风险检查程序并开展合规整改"）**同义**
        #   保留 2 条**独特**信息（别处都没有）：
        #   · 所列问题**有直接数据/可回查证据支持**（其余资料不足的已列补充清单）
        #   · **不得倒签、补造、篡改、删除或隐匿资料**（第四章只说"建立在真实业务和原始资料基础上"，
        #     未含这层禁止性要求）
        # ★ 2026-10-06（用户：「五、报告性质和使用说明……**重写，有废话**」）：
        #   ① 原说明1「所列具体问题均有直接数据/可回查证据支持；资料不足的已列入补充清单」
        #      = **系统自我证明**（"我做得对"）+ **指向别处**（那份清单已并入疑点与资料齐备性章）
        #      ⇒ 整条删除：企业不需要看我们如何自证，它只需要知道自己该做什么。
        #   ② 原说明2 的「依据真实业务和原始资料办理整改」与**第四章「办理要求」重复**
        #      ⇒ 只留第四章没有的**禁止性要求**（不得动资料）：第四章管"不得无据调账申报"，
        #      本条管"不得倒签/补造/篡改/删除/隐匿资料"，两条不重叠。
        "report_statement": [
            "整改过程中不得倒签、补造、篡改、删除或隐匿资料。",
        ] + _administrative_boundary_statement() + _conclusion_terms_statement()
          + _report_level_notes_statement(problems),
    })
    # ★★★ 2026-10-05（用户明确口径：「报告永远不能出现待核实。
    #   从既有资料检查分析，**能确定的风险就是风险**」）
    #   **单一出口统一过词表**（唯一权威 `engine.report_wording`）——
    #   不在各模块各改一遍（那样必然漏，且会出现两套口径）。
    #   只做逐词替换，**不重写任何句子**，事实表述零改动。
    # ★★★ 2026-10-05（用户：「三、本轮另行检出的税务风险事项为什么不放在第二章？
    #   为什么不以第二章的表述方式呈现？」）：
    #   把这 9 条**并入第二章同一列表**并生成同构段落，第三章随之整章下线。
    try:
        _promoted = _promote_standalone_to_problems(out, problems, report_data,
                                                    audit_sink=_sc_audit)
        _promoted += _promote_standalone_reports(out, problems)
        if _promoted:
            out["confirmed_problems"] = problems
            out["_promoted_standalone_count"] = _promoted
            # ⚠ 第一章统计在并入**之前**算的（`_build_summary` 先执行）⇒ 必须同步。
            #   ★ 2026-10-08 根因修复：原实现**只同步 `confirmed_problem_count`**，
            #     漏掉同源兄弟字段 `pending_problem_count` ⇒ 实测「已确认 16 / 待核 26」自相矛盾。
            #     ⇒ 一律走唯一权威 `_resync_summary_counts`（按定稿列表重算**全部**派生计数）。
            _rc = _resync_summary_counts(out)
            if _rc:
                print("[计数定稿·并入后] 已按定稿列表重算：已确认 %d / 已核定 %d / 待核 %d / 受阻 %d"
                      % (_rc["confirmed"], _rc["verified"], _rc["pending"], _rc["further"]))
    except Exception as _pe:  # noqa: BLE001
        print("[并入库并入] 失败：%s" % str(_pe)[:160])

    # ★★ 2026-10-06（用户：「疑点1的本项还包含以下风险信号，这部分内容不是已经在一至五里说了吗？」）：
    #   **本项自己的来源行不得作为"额外风险信号"重复列出**。
    #   ⚠ 过滤放在**这里**（而非 `_merge_ledger_into_problems` 内）：实测疑点9 的标题
    #     「企业所得税贡献率偏低（对应风险指标：…；本项未认定到该指标的任何一条构成要件…）」
    #     是在**并入之后**才被追加注解的 ⇒ 在并入那一刻用它判"是不是本项自己"会判不出来。
    #     ⇒ 判据必须在**标题与段落都定稿之后**执行，否则又是"顺序错了、判据白写"。
    try:
        import re as _re_sr
        # ★★ 口径对齐（**同一坑第二次**）：此刻行名仍带 `待核事实：` 前缀、且写"核**验**"，
        #   而报告定稿前 `report_wording` 会剥前缀、把"核验"改"核实" ⇒
        #   **同一事物此刻与定稿后长得不一样**，按字面比必然判不出来
        #   （实测 seq=9 行名"待核事实：企业所得税贡献率偏低" vs 标题"企业所得税贡献率偏低（…）"）。
        #   ⇒ 两侧都过**同一权威**再比：`plain_language.to_plain`（核验→核实…）+ 
        #      `report_wording.scrub_vague`（剥「待核事实：」前缀…），
        #      使"此刻的名字"与"定稿的名字"落在同一词汇表里。
        try:
            from engine.plain_language import to_plain as _tp_sr
        except Exception:                                        # noqa: BLE001
            _tp_sr = None
        try:
            from engine.report_wording import scrub_vague as _sv
        except Exception:                                        # noqa: BLE001
            _sv = None

        def _nz(_s):
            _t = str(_s or "")
            # ⚠ 顺序：先 `scrub_vague`（剥「待核事实：」前缀），后 `to_plain`（换词）。
            #   反了的话 to_plain 会先把前缀改成「尚需核实事实：」，前缀剥离就失效了。
            for _fn in (_sv, _tp_sr):
                if _fn is None:
                    continue
                try:
                    _t = _fn(_t)
                except Exception:                                # noqa: BLE001
                    pass
            return _re_sr.sub(r"[\s（）()【】\[\]·，,、：:]", "", _t)

        _dropped = 0
        for _p in problems:
            if not isinstance(_p, dict) or not _p.get("related_risks"):
                continue
            _seg0 = ""
            for _sg in (_p.get("narrative_paragraphs") or []):
                if str(_sg.get("heading") or "").startswith("为何列入检查"):
                    _seg0 = str(_sg.get("text") or "")
                    break
            _ctx = _nz(_p.get("title")) + "|" + _nz(_seg0[:60])
            _keep = []
            for _r in _p["related_risks"]:
                _nm = _nz((_r or {}).get("风险事项"))
                if _nm and _nm in _ctx:
                    _dropped += 1          # 就是本项自己的来源事项 ⇒ 不重复列出
                    continue
                _keep.append(_r)
            if _keep:
                _p["related_risks"] = _keep
            else:
                _p.pop("related_risks", None)
        if _dropped:
            print("[相关风险信号] 剔除 %d 个「本项自己」的重复条目" % _dropped)
    except Exception as _sr_err:  # noqa: BLE001
        print("[相关风险信号] 自我去重失败：%s" % str(_sr_err)[:160])

    # ★★ 2026-10-06（用户评语：事项数量虚高 —— 同一事实被拆成多个疑点、疑点27–34 重复前文）：
    #   **同族事项合并**（唯一权威 `engine.finding_families`）：同族只留一个**主事项**
    #   （等级最高→税额最大→原顺序靠前），其余降为**子项**并**不再单独计数**；
    #   子项信息挂到主事项的 `family_members` 且**写进正文**（不静默丢）。
    #   ⚠ 必须放在**计数定稿之前** —— 否则计数又按合并前的列表算（本报告的老病）。
    try:
        from engine.finding_families import merge_families as _mf
        _mfst = _mf(problems)
        if _mfst.get("removed_items"):
            print("[同族合并] %d 个族合并掉 %d 个子项：%s"
                  % (_mfst["merged_families"], _mfst["removed_items"],
                     "；".join("%s(留:%s)" % (d["family"], d["lead"])
                               for d in _mfst["detail"][:3])))
    except Exception as _mf_err:  # noqa: BLE001
        print("[同族合并] 失败（事项数会虚高，属缺陷）：%s" % str(_mf_err)[:160])

    # ★★ 2026-10-06（用户评语 #7「『检查程序待完善项』与『资料缺失』混用／结论先行」）：
    #   当**所需资料本轮已提供、但检查程序未产出可展示数据**（`clue_chain.data_gaps`
    #   全部为 `reason == "engine_gap"`）且本项**没有任何实测数字/终端信号**时，
    #   报告不得同时给出"风险等级 + 潜在税额"——那正是用户说的"程序没跑通却结论先行"。
    #   ⇒ 本项统一降级为：**不作定量**（不评风险等级、不给潜在税额）并写明原因。
    #   判据是**结构字段**（data_gaps.reason），不是文本匹配；且有"存在实测数字则不降级"
    #   的反向保护，避免误伤有真凭据的项。
    # ⚠ 不写 `List[str]` 注解：本模块未绑定 `List`（局部注解运行时不求值才没炸，
    #   一旦上移到模块级/签名即 NameError —— 不给自己埋雷）。
    _gap_downgraded = []
    for _p in problems:
        if not isinstance(_p, dict):
            continue
        _cl = _p.get("clue_chain") or {}
        _gaps = [g for g in (_cl.get("data_gaps") or []) if isinstance(g, dict)]
        if not _gaps:
            continue
        if any(str(g.get("reason") or "") != "engine_gap" for g in _gaps):
            continue                      # 存在"缺资料"缺口 ⇒ 属另一类问题，不在此降级
        if _cl.get("numbers") or str(_cl.get("terminal_signal") or "").strip():
            continue                      # 有实测数字/终端信号 ⇒ 不降级（不误伤）
        _p["risk_level"] = "待核验"
        _p.pop("tax_impact", None)
        _p["no_quantification_note"] = (
            "本项所需资料本轮已提供，但检查程序未产出可展示数据（属检查程序待完善项）。"
            "为避免「结论先行」，本项**不作定量**：不评定风险等级、不给出潜在税额，"
            "待检查程序完善或企业补充说明后重新检查。")
        _gap_downgraded.append(str(_p.get("title") or "")[:18])
    if _gap_downgraded:
        print("[不作定量] %d 项因「检查程序未产出数据」降级为待核验、不作定量：%s"
              % (len(_gap_downgraded), "、".join(_gap_downgraded[:5])))

    # ★★ 2026-10-06（用户评语 #1「总数、编号与风险等级严重不一致」）：
    #   **凡是"计数/等级/主题分布"，一律在列表定稿之后重算** —— 此前只有 `summary`
    #   一处做了同步（见上方 `_promoted` 分支的注释），而另两处仍在"并入独立风险事项
    #   之前"的旧列表上算，于是同一份报告出现两套口径：
    #     · `overall_conclusion`（等级判据「高风险 N 项、中风险 M 项」）
    #     · `inspection_overview`（第一章「本轮共识别并列示 N 项涉嫌风险事项」）
    #   实测症状：总述写 26 项、第二章列到 34 项；总述说高风险 1 项，而第二章里
    #   另有高等级条目 ⇒ 读者看到的是"报告自己和自己打架"。
    #   ⇒ 此处（＝最后一道去重之后、`build_self_doubt` 之前）**一并重算并覆盖**，
    #     下游（自我怀疑层、询问挂载、前端渲染）看到的即同一份定稿计数。
    try:
        from engine.overall_conclusion import build_overall_conclusion as _boc_rc
        from engine.inspection_overview import build_inspection_overview as _bio_rc

        # ★★★ 2026-10-06（用户第 1 批 ②）：**疑点编号必须连续**（1..N），不得缺号。
        #   事故：`_build_redline_problems` 早先把 seq 编成 1..N，但**之后**的
        #   `merge_families`（同族合并）会**删除**子项、`_promote_standalone_to_problems`
        #   会**追加**新项 ⇒ 最终列表 seq 变成 1,2,3,4,5,6,7,9,11,13,14,15,18,27,29,34
        #   （用户实测：编号缺号）。顺序/编号**只能有一个定稿时刻**＝此处。
        #   判据：按**呈现顺序**（等级由重到轻、同级按潜在税额降序）重排后连续编号。
        # ★★ 2026-10-09（P0-5 一级收口）：**等级上限**（结论等级 → 允许的风险等级）与
        #   **七环完整性**都必须在这唯一时刻收口，之后才排序 —— 否则排序依据的是**未压制**的等级。
        _cap_n = 0
        _ring_gap = 0
        try:
            from engine import report_ring_schema as _rrs
        except Exception:  # noqa: BLE001
            _rrs = None
        for _p in problems:
            if not isinstance(_p, dict):
                continue
            # ① 结论等级 → 风险等级上限（唯一权威 `conclusion_grade.cap_level_for_grade`）
            _gid, _greg = _cg_grade_id(_p)
            if _greg:
                _capped, _from = _cg_cap_level(_p.get("risk_level"), _gid)
                if _from:
                    _p["risk_level"] = _capped
                    _p["risk_level_capped_by_grade_from"] = _from
                    _cap_n += 1
            # ★ 2026-10-15（用户裁定「虽没定性也是隐患，明确涉嫌风险的呈现」）：
            #   结论未定性 ⇒ risk_level 保持受控（防「结论待核、等级高风险」自相矛盾，
            #   门禁 B3 语义不变），但**检出等级**必须原生携带并呈现 —— 企业有权
            #   知道这个隐患按检出证据达到了什么强度。
            _p["detected_risk_level"] = (_p.get("risk_level_capped_by_grade_from")
                                         or _p.get("risk_level") or "")
            _p["risk_level"] = _normalize_risk_level(_p.get("risk_level"))
            # ② 七环结构收敛（红线项与域分析项同构；环名由 schema 决定）
            if _rrs is not None:
                try:
                    #   ctx（含"已定性不适用后果环"等跳过规则）由**唯一权威**
                    #   `report_ring_schema.ctx_for_problem` 推导 —— 生产与常驻闸门同源，
                    #   否则会出现"生产按规则跳过、闸门仍按七环判缺"的假红。
                    _miss = _rrs.normalize_problem_rings(
                        _p, ctx=_rrs.ctx_for_problem(_p))
                    if _miss:
                        _ring_gap += 1
                except Exception as _re2:  # noqa: BLE001 —— 不静默
                    print("[七环收敛] seq=%s 失败：%s" % (_p.get("seq"), str(_re2)[:120]))
        if _cap_n:
            print("[等级上限] 按结论等级压制风险等级 %d 项" % _cap_n)
        if _ring_gap:
            print("[七环收敛] %d 项仍有必填环缺口" % _ring_gap)
        problems.sort(key=lambda _p: (
            _RISK_PRESENT_ORDER.get(str(_p.get("risk_level") or "").strip(), 99),
            -float((((_p.get("tax_impact") or {}).get("amount")) or 0) or 0),
        ))
        _seq_remap = {}
        for _i, _p in enumerate(problems, start=1):
            _old = _p.get("seq")
            if _old is not None and str(_old) != str(_i):
                _seq_remap[str(_old)] = _i
            _p["seq"] = _i
            # ★★ 2026-10-09（P0-5）：**办理顺序**与 seq 同源、同刻、连续 1..N
            #   （此前在 `_build_action_plan` 里算，早于并入/合并 ⇒ 缺号，门禁 B2 报红）。
            try:
                _p["办理顺序"] = _cn_num(_i)
            except Exception:  # noqa: BLE001
                pass
        if _seq_remap:
            print("[编号定稿] 疑点编号已连续重排：%s" % _seq_remap)

        # ★★ T-2（2026-10-12）：**风险分值必须在此刻派生**（等级已定稿之后）。
        #   为什么必须在这里、而不是更早：上方「结论等级→风险等级上限」压制会**改写**
        #   `risk_level`（实测 `红字冲销…` 由「高风险」压到「低风险」，而分值若早算则为 80
        #   ⇒ **分值陈旧、与等级矛盾**）。分值口径只由等级派生（唯一权威 `engine/risk_levels.py`），
        #   故必须在等级终局后派生；且排序（上方 sort）依据的是等级，不受分值影响。
        #   待核验（证据状态）/正向发现/词表外 ⇒ `None` + `risk_score_status`，**绝不用 0 顶替**。
        from engine.risk_levels import stamp_risk_score_all as _stamp_scores
        _stamp_scores(problems)

        out["overall_conclusion"] = _boc_rc(
            report_data, problems, further, inspector_reasoning)
        out["inspection_overview"] = _bio_rc(
            report_data, problems, further, out["overall_conclusion"],
            cost_recon_detail=cost_recon_detail)
        # ★ 2026-10-07（第 6 批 全量回归 第 3/7/8/10 项）：**统一收口后处理**（唯一调用点）
        try:
            _fstat = _finalize_topics_basis_uniqueness(out, problems)
            if _fstat["tables_moved"]:
                print("[主题收口] 移出主题不符明细表 %d 张（如社保低基数表不夹带在人数不符项下）"
                      % _fstat["tables_moved"])
            if _fstat["basis_added"]:
                print("[等级依据] 为 %d 个组合项补写独立依据（组合项不单独定高风险）"
                      % _fstat["basis_added"])
            if _fstat["sentences_diff"]:
                print("[模板句去重] %d 句模板句已按本项主题差异化" % _fstat["sentences_diff"])
        except Exception as _fin_exc:  # noqa: BLE001
            print("[主题收口] 执行失败（不阻断）：%s" % str(_fin_exc)[:160])

        # ★ 2026-10-07（质检 P0-1/P0-2）：**计数与合规都必须在定稿后再收口一次**
        try:
            _cnt = _sync_item_counts(out, problems)
            if _cnt.get("fixed"):
                print("[计数收口] 全文事项数声明已同步为 %d 项（%d 处）"
                      % (len(problems), _cnt["fixed"]))
        except Exception as _c1:  # noqa: BLE001
            print("[计数收口] 执行失败（不阻断）：%s" % str(_c1)[:160])
        try:
            _attach_compliance_to_readable(out, report_data)
        except Exception as _c2:  # noqa: BLE001
            print("[合规收口] 执行失败（不阻断）：%s" % str(_c2)[:160])

        # ★★ 2026-10-06（用户第 1 批 ①）：**税额敞口的"已量化 X / 总数 Y"必须按定稿列表算**。
        #   事故：`build_tax_impact_summary` 在本段之前用**旧列表（26 项）**算过一次，
        #   于是报告第 4 页写「已量化 7 / 26 项」，而第 1 页写「16 项」——同一份报告两套口径
        #   （用户实测）。⇒ 与其余计数一并**在定稿后重算**（分母＝定稿事项数）。
        try:
            from engine.tax_impact import build_tax_impact_summary as _btis_rc
            out["tax_impact_summary"] = _btis_rc(
                problems,
                ctx=(report_data.get("comprehensive", {}) or {}).get("tax_rate_context"))
        except Exception as _tis_err:  # noqa: BLE001
            print("[计数定稿] 税额敞口汇总重算失败：%s" % str(_tis_err)[:120])
        # 主体一致性自检里引用的 seq 必须同步（否则指向不存在的编号）
        _sca_rc = out.get("subject_consistency_audit")
        if isinstance(_sca_rc, dict):
            for _iss in (_sca_rc.get("issues") or []):
                if isinstance(_iss, dict) and str(_iss.get("seq")) in _seq_remap:
                    _iss["seq"] = _seq_remap[str(_iss.get("seq"))]
        # ★★ 2026-10-06（用户第 1 批 4.1.4「异常空白表格」）：
        #   **空表/全空单元格的表一律不挂**（表头为空、行全空、或列全空都会渲染成
        #   "一张只有边框的空白表格"）。判据只看数据，不看表名（通用）。
        try:
            out, _dropped_empty = _remove_empty_tables(out)
            if _dropped_empty:
                print("[表格治理] 剔除空白表格 %d 张（无表头/无数据，渲染出来只是空框）"
                      % _dropped_empty)
        except Exception as _ete:  # noqa: BLE001
            print("[表格治理] 空白表格剔除失败：%s" % str(_ete)[:120])

        # ★★ 2026-10-06（C 类普查：**第 3 处计数**）：具体问题章首的「主线研判」——
        #   「主线研判：本轮共 N 项风险事项（高N 中N 低N 尚需核实N）」同样在
        #   `_promote_standalone_to_problems` **之前**算 ⇒ 用户实测第 4 页仍写 26 项。
        #   ⇒ 与另两处一并重算（计数只允许有一个时刻：**列表定稿之后**）。
        try:
            _bm2 = _build_main_assessment(problems)
            if _bm2:
                out["main_assessment"] = _bm2
        except Exception as _bm_exc:  # noqa: BLE001
            print("[计数定稿] 主线研判重算失败：%s" % str(_bm_exc)[:120])
        _sm2 = out.get("summary")
        if isinstance(_sm2, dict):
            # ★ 2026-10-08：走唯一权威（含 pending/verified/further 一并重算），
            #   不再只补 `confirmed_problem_count` 一个字段。
            _rc2 = _resync_summary_counts(out)
            print("[计数定稿] summary 重算：已确认 %d / 已核定 %d / 待核 %d / 受阻 %d"
                  % (_rc2.get("confirmed", 0), _rc2.get("verified", 0),
                     _rc2.get("pending", 0), _rc2.get("further", 0)))
        print("[计数定稿] 总述/等级判据/主线研判已按定稿列表重算：共 %d 项" % len(problems))
    except Exception as _rc_err:  # noqa: BLE001
        print("[计数定稿] 重算失败（报告仍按旧计数输出，属缺陷）：%s" % str(_rc_err)[:160])

    # ★★ 2026-10-06（用户要求）：给每条风险事项加**自我怀疑**层 ——
    #   「以终为始拆解疑点的关键信息 → 自我反驳 → 再索取资料进行自我验证」。
    #   唯一权威：`engine/self_doubt.py`（只读既有字段，不重算任何判定）。
    #   ⚠ 必须放在**所有**问题都构造完（含并入的独立风险事项）之后，否则新并入的项没有本段。
    try:
        from engine.self_doubt import build_self_doubt as _bsd
        # 「已提供资料」取自**唯一权威** `material_readiness.provided`（不另立名单），
        # 用于避免把企业已交的资料再列进"验证清单"。
        _prov_mat = list(((out.get("material_readiness") or {}).get("provided")) or [])
        _sd_n = _bsd(problems, provided_materials=_prov_mat)
        if _sd_n:
            out["confirmed_problems"] = problems
            print("[自我怀疑] 已为 %d 条风险事项生成「可能错在哪里 + 验证清单」" % _sd_n)
    except Exception as _sd_err:  # noqa: BLE001
        print("[自我怀疑] 生成失败：%s" % str(_sd_err)[:160])

    # ★★ 2026-10-08（P0-2 去重收口）：报告级「税费性质与法定后果」声明。
    #   逐项「若不补证的后果」只留本项情形 + **引用**（`levy_nature.item_consequence_text`），
    #   法条原文在此**按性质声明一次** —— 否则同一法条在 13 个事项里逐字重复，
    #   整体重复率超阈（>10%）⇒ 产出链判「阻断」⇒ 报告不得输出；
    #   而法条又不得因去重被删（合规底线，删了就是法律适用错误）。
    #   ⚠ 必须放在**列表定稿之后**（并入的独立风险事项可能引入新性质），
    #     否则会出现"逐项引用了报告级声明里没有的性质" ⇒ 引用悬空。
    try:
        _levy_decls = _report_levy_declarations(problems)
        if _levy_decls:
            _rs0 = out.get("report_statement")
            _rs0 = list(_rs0) if isinstance(_rs0, list) else []
            for _t in _levy_decls:
                if _t not in _rs0:
                    _rs0.append(_t)
            out["report_statement"] = _rs0
            # 同时登记为**报告级共性声明**（机器消费口径：闸门用 `common_statements`
            # 判定"本项有效文本"含报告级声明；见 `tools/audit_consistency.py` ③i）。
            _cs0 = list(out.get("common_statements") or [])
            for _t in _levy_decls:
                if all(_t != str((_c or {}).get("text") or "") for _c in _cs0):
                    _cs0.append({"heading": _LEVY_DECL_NAME, "text": _t,
                                 "scope": "declaration"})
            out["common_statements"] = _cs0
            print("[税费性质] 报告级「%s」声明 %d 条（逐项后果段改为引用）"
                  % (_LEVY_DECL_NAME, len(_levy_decls)))
    except Exception as _ld_err:  # noqa: BLE001 —— 不静默：引用悬空属缺陷，必须留痕
        print("[税费性质] 报告级声明生成失败（逐项引用将悬空，属缺陷）：%s" % str(_ld_err)[:160])

    # ★★ 2026-10-06（用户评语：重复冗余占全文三分之一以上、同一资料被要求三次）：
    #   **去重唯一权威** `engine.report_dedup`，在此一次性收口（所有段落都已定稿）：
    #     R1 删元话语（"本段是系统对自己结论的复核"等系统自述）；
    #     R2 逐字重复的**共性段**从所有疑点删除，由报告级 `common_statements` 前置一次；
    #     R3 同一表注只保留首次。
    try:
        from engine.report_dedup import dedup_report as _dd
        _ddst = _dd(out)
        if _ddst.get("common_statements"):
            # ★★ 2026-10-08（P0-2 去重收口）：**合并而非覆盖** —— 报告级「税费性质与
            #   法定后果」声明（上面已登记）若被这里覆盖掉，逐项后果段的引用就**悬空**
            #   （企业按引用查不到法条 = 等于把法条删了）。
            _cs_all = list(out.get("common_statements") or [])
            for _c in _ddst["common_statements"]:
                if _c not in _cs_all:
                    _cs_all.append(_c)
            out["common_statements"] = _cs_all
            # ★★ **前置渲染**：收上来的共性声明必须在报告级**出现一次**，
            #   否则"去重"就等于"删内容"（企业无处对照）。挂进第五章的同一声明列表
            #   （`report_statement` 由前端渲染为「报告性质与使用说明」的条目）。
            try:
                # ★★ 2026-10-07（Skill 4「占位符与空内容检测」）：**孤立引导句不得进报告**。
                #   事故（用户复核文末「说明2」）：去重把"共性句"上提到报告级声明时，
                #   把**引导句**也当成了共性句 —— 实测 `report_statement` 里出现
                #   「要把这一项查清楚，需要：」，而它的正文在别处，渲染出来是"有标题没有内容"。
                #   引导句（以「：」承诺后文）**脱离正文即无信息量** ⇒ 一律剔除；
                #   判据唯一权威 `engine.content_placeholder_guard.is_orphan_lead`（形态+词表）。
                from engine.content_placeholder_guard import is_orphan_lead as _orphan_lead
                _extra = []
                for _c in _ddst["common_statements"]:
                    _txt = str(_c.get("text") or "").strip()
                    if not _txt or _txt in _extra:
                        continue
                    if _orphan_lead(_txt):
                        try:
                            _note(out, "[空内容拦截] 剔除孤立引导句：%s" % _txt[:40])
                        except Exception:      # noqa: BLE001 - 留痕失败不得影响出报告
                            pass
                        continue
                    _extra.append(_txt)
                if _extra:
                    _rs = out.get("report_statement")
                    out["report_statement"] = (list(_rs) if isinstance(_rs, list) else []) + _extra
            except Exception:  # noqa: BLE001
                pass

        # ★★ 2026-10-07（Skill 3「字段截断检测」）：**字段完整性体检**。
        #   风险面：报告出现「涉及月份 2025-01、…、2025-10」这类**被静默截断**的列举
        #   （缺 11/12 月且无省略号），读者会误以为已列全、低估涉及期间。
        #   判据唯一权威 `engine.field_completeness`（覆盖性 + 截断可见性，数据驱动）。
        #   此处只**体检并留痕**（不静默、不改写数据），命中写入一键分析日志供复核。
        try:
            from engine.field_completeness import scan as _fc_scan
            _fc_period = str(((out.get("identity") or {}).get("period")) or "")
            for _fi in _fc_scan(out, _fc_period)[:5]:
                _note(out, "[字段截断] %s：%s"
                                      % (_fi.get("kind"), str(_fi.get("detail"))[:120]))
        except Exception as _fc_err:      # noqa: BLE001 - 留痕，不静默
            _note(out, f"[字段完整性] 体检未执行: {_fc_err}")
        print("[去重] 元话语删 %d 句｜共性段上提 %d 处／共性句上提 %d 处（合并为 %d 条报告级声明）｜表注去重 %d 处"
              % (_ddst.get("meta_removed", 0), _ddst.get("hoisted", 0),
                 _ddst.get("sentences_hoisted", 0),
                 len(_ddst.get("common_statements") or []),
                 _ddst.get("table_notes_removed", 0)))
    except Exception as _dd_err:  # noqa: BLE001
        print("[去重] 失败（报告将保留重复内容，属缺陷）：%s" % str(_dd_err)[:160])

    # ★★ 2026-10-07（Skill 6 第 2 版）：**子项与关联项逐项核对清单**在定稿处统一产出。
    #   用户复核：疑点1 进项侧 9 笔红冲、疑点3 风险族 5 个子项、疑点4 要件④、疑点15 个人垫付
    #   —— 都是"列了子项却不分析"。此处为**唯一调用点**（见 `_finalize_child_checklist` docstring）。
    try:
        _cc_stat = _finalize_child_checklist(out, problems)
        if _cc_stat.get("listed"):
            print("[子项清单] 已为 %d 个疑点生成「子项与关联项逐项核对」清单"
                  "（结构化审计块 %d 个）" % (_cc_stat["listed"], _cc_stat.get("audited", 0)))
        if _cc_stat.get("failed"):
            print("[子项清单] 有 %d 个疑点未产出清单（须查）" % _cc_stat["failed"])
    except Exception as _cc_err:  # noqa: BLE001
        print("[子项清单] 收口失败（报告将缺少子项清单，属缺陷）：%s" % str(_cc_err)[:160])

    # ★★ 2026-10-07（Skill 1【输出】字段）：**触发条件/认定要件分离**的结构化块也在定稿处收口。
    #   口径由唯一权威 `trigger_conditions.classify()` 一次产出（报告里的那两句话就是它的文本形态）；
    #   此前只有文本、没有结构化数据 ⇒ 无法机检"疑点成立 ⇔ 触发条件命中"。
    try:
        _td_stat = _finalize_trigger_determination(out, problems, report_data)
        if _td_stat.get("built"):
            print("[触发条件] 已为 %d 个疑点落盘触发条件/认定要件结构化块（无触发命中 %d 个）"
                  % (_td_stat["built"], _td_stat.get("no_trigger", 0)))
        if _td_stat.get("skipped"):
            print("[触发条件] 有 %d 个疑点未取到对应疑点对象，已跳过（须查）" % _td_stat["skipped"])
    except Exception as _td_err:  # noqa: BLE001
        print("[触发条件] 收口失败（报告将缺少结构化块，属缺陷）：%s" % str(_td_err)[:160])

    # ★★ 2026-10-07（Skill 7「数据源状态一致性」）：**数据源状态表**同样在定稿处收口。
    #   事故：要件核对表写「独立数据源本轮未取得」，而同页明细表正列着确认单编号、
    #   正文正用着销项发票金额 ⇒ "数据已取得却写未取得"（实测 65 条要件行中 26 条）。
    #   本表把「明细表侧 / 核对表侧」两个状态并排落盘，并标 `consistency`
    #   —— 门禁据此阻断（明细表已有却判未取得 ⇒ ERROR）。
    try:
        _ds_stat = _finalize_data_source_status(out, problems, report_data)
        if _ds_stat.get("built"):
            print("[数据源状态] 已为 %d 个疑点落盘数据源状态表（冲突 %d 处）"
                  % (_ds_stat["built"], _ds_stat.get("conflicts", 0)))
        if _ds_stat.get("skipped"):
            print("[数据源状态] 有 %d 个疑点未取到对应疑点对象，已跳过（须查）" % _ds_stat["skipped"])
    except Exception as _ds_err:  # noqa: BLE001
        print("[数据源状态] 收口失败（报告将缺少数据源状态表，属缺陷）：%s" % str(_ds_err)[:160])

    # ★★★ 2026-10-06：**询问主题挂载必须在"并入独立风险事项"之后执行**。
    #   事故：本段原先放在上方（早于 `_promote_standalone_*`），而
    #   「进项异常凭证：不得抵扣用途未作进项转出」正是**由并入才产生**的风险事项
    #   ⇒ 挂载那一刻它还不存在 ⇒ 「进项，应转出未转出」找不到归属
    #   ⇒ 被丢进报告末尾的「待企业澄清事项（其余事项）」，与风险事项**重复呈现**。
    #   即：**归属表写对也可能不生效 —— 顺序错了就静默落回残余章**。
    #   闸门 `check_question_theme_attachment()` 断言"残余章必须为空"，正是为防这类漂移。
    try:
        from engine.report_layout import attach_question_themes as _aqt
        _attached_n, _unattached = _aqt(
            (inspection_questions_report or {}).get("themes") or [], problems)
        if isinstance(inspection_questions_report, dict):
            inspection_questions_report["unattached_themes"] = _unattached
            inspection_questions_report["attached_theme_count"] = _attached_n
            out["inspection_questions_report"] = inspection_questions_report
    except Exception as _qe:  # noqa: BLE001
        print("[询问挂载] 失败：%s" % str(_qe)[:160])

    _scrub_out_vague.scrubbed = 0
    _scrub_out_vague(out)
    _n_scrub_first = _scrub_out_vague.scrubbed

    # ★★★ 2026-10-06（顺序缺陷，"判据白写"同族）：**表格治理必须在报告定稿处再收口一次**。
    #   事故：`govern_all_tables` 原先只在 6108 行 `_norm_and_redact(...)` 那一刻执行，
    #   而「并入独立风险事项」（6212 行）、「询问主题挂载」（6426 行）都在其**之后**追加内容
    #   ⇒ 这些后追加的表**从未过治理**：列名与行键不对齐（整列渲染为空）、内部列
    #   （`_id`/`trace_id`）外泄成正式列、截断不注明 —— 正是 `table_governance` 立项要修的三类
    #   缺陷，在**后追加的**内容上全部复发。
    #   修法：与 `seal_governed_findings` 同款"终局唯一收口"——内容定稿后整份再跑一遍
    #   （`align_table` 幂等，重复执行不改变已治理过的表）。
    try:
        from engine.table_governance import govern_all_tables as _gt_final
        out = _gt_final(out)
    except Exception as _tg_err:  # noqa: BLE001
        print("[表格治理] 终局收口失败（后追加的表将未治理，属缺陷）：%s" % str(_tg_err)[:160])

    # ★★★ 2026-10-06（**顺序缺陷第 3 例**）：措辞清洗也必须**终局收口**。
    #   实测事故：清洗原在 6429 行（询问挂载之后、表格治理之前）执行，报了"替换 208 处"，
    #   但产物里的 `inspection_overview` / `resolution_ledger` 等仍带 210 处「尚需核实」——
    #   即**清洗跑过了、这些串却不在它当时的可达图里**（同一函数内后挂的块 / 派生副本）。
    #   ⇒ 与 `govern_all_tables` 同款：**定稿后再跑一遍**（`scrub_vague` 幂等）。
    #   ⚠ 并留痕计数：**"清洗跑没跑、改了几处"必须可见**（本项目铁律：改了看不出生效＝事故）。
    _scrub_out_vague.scrubbed = 0
    out = _scrub_out_vague(out)
    print("[措辞清洗] 替换 %d 处（首次 %d 处）｜禁用模糊词唯一权威 report_wording.scrub_vague"
          % (_scrub_out_vague.scrubbed, _n_scrub_first))

    # ★★★ 2026-10-07（实测事故：企业会看到「**未考虑**进项留抵」这种带星号的句子）：
    #   **去 markdown 标记**也必须**终局收口**（与 `govern_all_tables` / `_scrub_out_vague`
    #   同款"顺序缺陷"）：规则原在 `_naturalize_report_text` 里，只覆盖疑点段落构造路径，
    #   而 `tax_impact_summary.note` 等后拼/旁路的串没走到它 ⇒ 产物 120 处、页面 73 处。
    #   ⚠ 必须放在**所有内容定稿之后**（后面再拼串就又漏了）；幂等，可重复执行。
    out = _strip_markup_out(out)
    print("[去标记] 清除 markdown 标记 %d 处｜唯一权威 text_guardrails.strip_markup"
          % _strip_markup_out.stripped)
    return out
