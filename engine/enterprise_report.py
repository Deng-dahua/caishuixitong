"""企业易读版「涉税稽查工作报告」九章数据生成。

从一键分析结果（all_findings / file_results / target_entity 等）组装
`enterprise_readable_report` 字段，供前端 _buildEnterpriseReadableBody 渲染
九章稽查文书式报告。

字段结构对齐前端 static/js/tax-doc-analysis.js 的读取逻辑。
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from collections import Counter, OrderedDict


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


def _brief(text, limit=180):
    """按句子边界截断摘要文本，避免半句话被切断。"""
    t = _norm_text(text)
    if len(t) <= limit:
        return t
    cut = t[:limit]
    for stop in ("。", "；", "！", "？"):
        idx = cut.rfind(stop)
        if idx >= 40:
            return cut[:idx + 1]
    return cut.rstrip("，、；, ") + "。"


def _fmt_metric_val(v):
    """明细表单元格格式化：浮点千分位、列表转中文顿号、其余转字符串。"""
    if isinstance(v, float):
        return f"{v:,.2f}" if abs(v) < 1e9 else f"{v:,.0f}"
    if isinstance(v, list):
        return "、".join(str(x) for x in v)
    if isinstance(v, dict):
        return "、".join(f"{kk}={vv}" for kk, vv in v.items())
    return str(v)


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
        _scalar_cn = {
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
        }
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
                            row[_scalar_cn.get(ik, str(ik))] = _fmt_metric_val(inner.get(ik))
                        rows.append(row)
                    columns = [label] + [_scalar_cn.get(ik, str(ik)) for ik in inner_keys]
                    break
        # 2.6) 列表嵌套字典（list-of-dicts）：如 anomaly_months[{month,left,right,gap,...}]——逐行表格
        if not rows:
            for k, v in metrics.items():
                if k in skip or not isinstance(v, list) or not v or not isinstance(v[0], dict):
                    continue
                inner_keys = list(v[0].keys())
                # 列名：把已知 key 汉化
                columns = [_scalar_cn.get(ik, str(ik)) for ik in inner_keys]
                rows = [{_scalar_cn.get(ik, str(ik)): _fmt_metric_val(item.get(ik)) for ik in inner_keys}
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
            scalar_rows.append({"指标": _scalar_cn.get(k, str(k)), "数值": val})
        if scalar_rows and not rows:
            rows = scalar_rows
            columns = ["指标", "数值"]
    if not rows:
        return [], []
    # 列名汉化
    _col_cn = {
        "invoice_number": "发票号码", "invoice_code": "发票代码", "rows": "出现行号",
        "count": "出现次数", "account": "账户尾号", "date": "日期",
        "expected_balance": "应滚余额", "reported_balance": "账面余额", "difference": "差额",
        "row": "行号", "amount": "金额", "tax": "税额", "total": "价税合计",
        "counterparty": "资金对手方", "receipts": "累计收款", "payments": "累计付款",
        "transaction_count": "笔数", "name": "对手方", "month": "月份", "voucher_no": "凭证号",
        "supplier": "加工方", "goods": "货物", "cross_region": "是否跨地区",
        "rows": "出现行号", "invoice_code": "发票代码",
        "debit": "借方", "credit": "贷方", "code": "存货编码", "end_qty": "期末数量",
        "name": "品项", "begin": "期初", "in_qty": "入库", "out_qty": "出库",
        "expected_end_qty": "应滚期末", "reported_end_qty": "账面期末",
    }
    columns = [_col_cn.get(c, str(c)) for c in columns]
    return rows, columns


# ── 14 类税务合规必查资料（与 domain_analysis.py 保持一致）──
_REQUIRED_DOC_CATEGORIES = [
    "银行流水", "销项发票", "进项发票", "记账凭证", "工资表", "社保明细",
    "进销存台账", "合同文件", "科目余额表", "资产负债表", "利润表",
    "增值税申报表", "企业所得税申报表", "个税申报表", "其他税种申报表",
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
_DOC_TYPE_TO_CATEGORY = {
    "bank": "银行流水", "bank_statement": "银行流水", "bank_transaction": "银行流水",
    "sales_invoice": "销项发票", "purchase_invoice": "进项发票",
    "salary": "工资表", "payroll": "工资表",
    "social_security": "社保明细", "housing_fund": "社保明细",
    "voucher": "记账凭证", "journal": "记账凭证",
    "trial_balance": "科目余额表", "ledger": "科目余额表",
    "contract": "合同文件", "order": "合同文件",
    "inventory": "进销存台账",
    "vat": "增值税申报表",
    "financial": "财务报表", "financial_statement": "财务报表",
}


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


def _build_identity(report_data):
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
        "opening": "根据本轮税务稽查工作安排，现对被检查企业提交并成功读取的财税资料实施检查，并将检查范围、实施程序、查明事实、税务影响、处理意见及后续复查要求报告如下。",
        "work_principle": "以企业上传的原始资料为起点，先确认数据事实，再核对交易、会计处理和纳税申报；正常解释、反向证据和资料缺口分别记录。",
        "conclusion_rule": "只有能够回查到本轮资料的具体事实才写入问题部分；行业指标、风险评分和资料缺失不能单独作为问题认定。",
        "administrative_boundary": "本报告由企业使用的财税风险防控系统依据已提交资料生成，用于模拟税务稽查程序并开展合规整改，不具有税务机关行政执法文书效力；税务机关实际检查结论应以依法送达的正式文书为准。",
    }


def _build_procedures(report_data):
    """七项稽查程序（固定描述 + 本轮实际数字）"""
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
         f"分别检查银行余额连续性、发票号码及金额税额、工资人员和月份、社会保险与住房公积金、账簿借贷及其他已具备字段的内部关系。本轮程序结果为：现有资料能够直接证明的具体问题{len(confirmed)}项；已执行且本轮未发现达到检查条件异常的项目见第五章。"),
        ("执行账、票、表、税、款、货、合同和人员交叉核对",
         "按照实际可用资料，把交易主体、业务期间、合同履约、发票、资金、会计处理和纳税申报连接起来；资料链条缺少节点时停止该项外推。本轮程序结果为：完整具备资料节点的交叉核对链条以实际可用资料为准；仍有资料需要补充识别或修复。"),
        ("检查正常解释、反向证据和税务影响",
         "对每项差异分别检查正常业务原因、反向证据、企业说明、政策适用期间和金额计算条件，避免把异常信号直接写成违法结论。本轮程序结果为：问题部分只保留能够回查到本轮资料的具体事实；税务性质或金额尚不能确定的内容已经明确说明限制。"),
        ("检查应有但未提供的资料及其连带影响",
         "根据企业行业、经营活动和税种，反向检查本轮未取得的申报、账簿、合同、履约、资金、人员、资产和优惠资料。本轮程序结果为：形成受阻检查及补件要求；缺少资料只表示相应检查未完成，不直接认定企业存在违法。"),
        ("形成处理意见、验收标准和下一轮复查计划",
         "对已确认问题逐项提出处理步骤、责任安排、完成标准和应回传资料；对资料缺口明确补齐后必须重跑的检查。本轮程序结果为：本轮保持涉税稽查工作报告草稿状态。"),
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
    """从 finding 生成六段式问题说明"""
    detail = _norm_text(str(f.get("detail") or f.get("description") or ""))
    how = _norm_text(str(f.get("how_found") or ""))
    reasons = f.get("reasonable_explanations") or f.get("alternative_explanations") or []
    suggestion = _norm_text(str(f.get("suggestion") or ""))
    steps = f.get("investigation_steps") or []
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
        tax_impact = "本项只确认资料中存在需要核清的具体差异，不把差异直接当作应补税额。税额影响以完成资料更正、账税核对和重新计算后的结果为准。"

    # 代表性明细：把后台已算出的逐笔差异落到正文，是报告『详尽』的关键
    detail_rows, detail_cols = _build_detail_table(f)
    paragraphs = [
        {"heading": "查明的主要事实",
         "text": "经查，" + detail + "上述数字来自本轮已读取资料的全量筛查，不是抽样估计。"},
        {"heading": "结论状态",
         "text": _conclusion_statement(f)},
        {"heading": "代表性明细（可回查）",
         "text": ("以下为本项涉及的逐笔/代表明细（已脱敏行号与金额，原始数据见工作底稿）：" if detail_rows
                  else "本项明细已留存于内部稽查底稿，可按上述资料范围逐笔回查。")},
        {"heading": "检查范围、方法和资料依据",
         "text": "本项使用的资料范围为" + scope + "。稽查人员直接读取企业上传的资料，按照同一口径逐项重新计算，并将计算结果与资料中的记录进行比较。原始文件指纹、读取回执、复算指标、代表性明细和可用的原文件行号已保存在内部稽查底稿中；专业人员可在工作底稿中回查。"},
        {"heading": "这件事对企业意味着什么",
         "text": "本轮确认资料中存在能够重复计算的数据差异。企业应先修复资料完整性和计算口径，再开展账、票、表、税和资金用途核对。仅凭这一数据差异，不能认定企业少缴税款或违反税收规定。" + tax_impact},
        {"heading": "应当同时核对的正常业务原因",
         "text": "出现上述情况不当然等于发生税务违法。企业应按同一证据标准核对：" + _seq(reasons, "正常业务原因和对企业有利的原始资料。")},
        {"heading": "企业应当怎样处理",
         "text": "企业应当依据真实业务办理，不得为了消除系统提示而倒签、补造或者无事实依据调整。具体处理顺序为：" + _seq(steps or [suggestion], "按真实业务和原始资料查明原因并作真实处理。")},
        {"heading": "怎样才算处理完成",
         "text": "本项只有达到下列条件后才可申请关闭：" + _seq(["本次发现的每一组差异都有原始资料、差异原因和处理结果可以回查",
                                                          "更正后的数据能够与会计记录和相关纳税申报资料核对一致，或对仍有差异的事项单独说明",
                                                          "补充资料后重新检查，系统能够分别列示合理事项、仍需处理事项和证据不足事项"],
                                                         "问题能够定位、处理过程能够回查，重新检查不再出现同一差异。")},
    ]
    if detail_rows:
        # 把明细表挂在第一段对象上，供前端渲染；同时保留文本回退
        paragraphs[0]["detail_table"] = {"columns": detail_cols, "rows": detail_rows}
    return paragraphs


def _conclusion_statement(f):
    """两级结论文本：可核定→最终答案；待核→建议与补证要求"""
    grade = str(f.get("conclusion_grade") or "")
    if grade == "已核定":
        answer = _norm_text(str(f.get("final_answer") or "").strip())
        scope_note = _norm_text(str(f.get("conclusion_scope_note") or "").strip())
        return (
            (answer or "本项结论已由本轮所报资料直接计算核定。")
            + (" " + scope_note if scope_note else "")
            + " 本项无须补充核实即可作为定案事实引用；行政处理决定仍由稽查人员依程序作出。"
        )
    suggestion = _norm_text(str(f.get("suggestion") or "").strip())
    return (
        "本项为待核事项：现有资料只能确认疑点信号，尚不足以作出最终认定。"
        "须补充外部证据（合同、物流单据、盘点表、权属证明等）后方可定性。"
        + (f"本轮建议：{suggestion}" if suggestion else "请按报告『企业应当怎样处理』一节逐项补证。")
    )


def _build_confirmed_problems(report_data):
    """从 findings 组装『确认的具体问题』（level 非待核验/信息的）"""
    findings = report_data.get("all_findings", []) or []
    problems = []
    seq = 1
    for f in findings:
        if not isinstance(f, dict):
            continue
        if f.get("level") in ("待核验", "信息", "低风险"):
            continue
        ev = f.get("_evidence_ref", {}) or {}
        problems.append({
            "seq": seq,
            "title": (f.get("type") or "具体资料问题").replace("待核事实：", "").replace("待核事实:", ""),
            "conclusion_grade": f.get("conclusion_grade") or "待核",
            "final_answer": str(f.get("final_answer") or ""),
            "observed_metrics": f.get("observed_metrics") or {},
            "narrative_paragraphs": _problem_paragraphs(f),
            "trace_id": ev.get("trace_id", ""),
        })
        seq += 1
    return problems


def _build_completed_checks(report_data):
    """已执行且本轮未发现达到条件异常的检查（level 待核验的）"""
    findings = report_data.get("all_findings", []) or []
    completed = []
    seq = 1
    for f in findings:
        if not isinstance(f, dict):
            continue
        if f.get("level") != "待核验":
            continue
        completed.append({
            "seq": seq,
            "title": (f.get("type") or "检查").replace("待核事实：", "").replace("待核事实:", ""),
            "narrative": "稽查人员对本项执行了本轮规定的检查程序，按照该检查项目规定的字段、口径和计算条件完成筛查，并记录本轮唯一执行状态。检查结果为：本轮已经取得该项检查所需资料并执行规则，未发现达到该规则检查条件的异常。",
        })
        seq += 1
    return completed


def _build_action_plan(problems):
    """处理意见（从确认问题派生）"""
    plans = []
    for i, p in enumerate(problems):
        plans.append({
            "seq": _cn_num(i + 1),
            "problem": p.get("title", ""),
            "narrative": "企业应先依据真实业务和原始资料办理，不得倒签、补造或者作无事实依据的调整。本项由企业指定熟悉该项业务和资料的负责人办理，并由另一名人员复核。整改不能仅以口头说明作为完成依据，验收时应确认处理过程能够回查、更正后的数据能够与会计和申报资料核对一致。",
        })
    return plans


def _build_further_checks(report_data):
    """受阻检查：14 类必查资料中未提交的类别"""
    file_results = report_data.get("file_results", []) or []
    covered = set()
    for fr in file_results:
        if not isinstance(fr, dict):
            continue
        cat = _DOC_TYPE_TO_CATEGORY.get(fr.get("type", ""))
        if cat:
            covered.add(cat)
    # 从 target_entity / material_intel 补充已识别类别
    mi = report_data.get("comprehensive", {}).get("material_intel", {}) if isinstance(report_data.get("comprehensive"), dict) else {}
    if isinstance(mi, dict):
        for k in mi.keys():
            covered.add(str(k))

    missing = [c for c in _REQUIRED_DOC_CATEGORIES if c not in covered]

    further = []
    for i, cat in enumerate(missing):
        further.append({
            "seq": i + 1,
            "title": f"未收到“{cat}”导致相关检查未完成",
            "narrative_paragraphs": [
                {"heading": "本轮检查结论",
                 "text": f"经检查，本轮未收到该项资料，无法取得完成相关检查所需的完整事实。资料缺失只表示检查范围受限，不表示企业已经存在违法或少缴税问题。本轮相关检查未完成，所列风险方向目前无法排除，但不作违法、少缴税款或处罚认定。"},
                {"heading": "被阻断的检查和风险影响",
                 "text": f"由于资料条件不具备，本轮无法完成与“{cat}”相关的账、票、表、税、款交叉核对。目前仍无法排除相应的风险方向。涉及{cat}的检查结论不得显示为无异常或已经合规。"},
                {"heading": "补充资料要求",
                 "text": f"企业应补充{cat}。如原资料客观上无法取得，可以提供能够证明同一事实的替代资料。"},
                {"heading": "下一轮复查程序",
                 "text": f"资料补齐后，稽查人员将重新执行受影响的全部检查程序。本项完成标准为：资料能够覆盖本轮检查期间，来源、形成时间、原始版本和具体业务可以回查；补齐后重新运行受影响的全部检查程序。"},
            ],
        })
    return further


def _build_summary(report_data, problems, completed, further):
    findings = report_data.get("all_findings", []) or []
    file_results = report_data.get("file_results", []) or []
    files_count = report_data.get("files_count", len(file_results)) or len(file_results)
    types = {fr.get("type") for fr in file_results if isinstance(fr, dict)}
    te = report_data.get("target_entity", {}) or {}

    key_points = []
    for p in problems[:5]:
        first = p.get("narrative_paragraphs", [{}])[0].get("text", "") if p.get("narrative_paragraphs") else ""
        grade = p.get("conclusion_grade") or "待核"
        grade_tag = "（已核定）" if grade == "已核定" else "（待核）"
        key_points.append(f"重点{p['seq']}{grade_tag}：{p.get('title', '')}。{_brief(first, limit=110)}")
    if len(problems) > 5:
        key_points.append(f"另有{len(problems) - 5}项具体问题见第四章及本章『本轮全部发现一览』。")
    if further:
        key_points.append(f"还有{len(further)}项检查尚未完成，优先补齐资料。这些事项表示检查范围受限，不表示已经发生相应违法。")

    verified_cnt = sum(1 for p in problems if p.get("conclusion_grade") == "已核定")
    pending_cnt = len(problems) - verified_cnt
    grade_phrase = ""
    if problems:
        if verified_cnt and pending_cnt:
            grade_phrase = (f"其中{verified_cnt}项为账面勾稽已核定事项，已直接给出最终结论；"
                            f"{pending_cnt}项为待核事项，须补充外部证据后定性，本轮已随附检查建议。")
        elif verified_cnt:
            grade_phrase = f"全部{verified_cnt}项为账面勾稽已核定事项，已直接给出最终结论。"
        else:
            grade_phrase = f"全部{pending_cnt}项为待核事项，须补充外部证据后定性，本轮已随附检查建议。"

    headline = (f"本次税务稽查共接收{files_count}个文件，归并为{len(types)}类资料。稽查人员经逐项读取、复算和交叉核对，"
                f"确认{len(problems)}项已有资料能够证明的具体问题。{grade_phrase}"
                f"另有{len(completed)}项检查已执行且本轮未发现达到条件的异常；"
                f"{len(further)}项因资料不足或影响范围尚未查清，本轮不作问题认定，补充资料后再检查。")

    owner_message = (f"请企业负责人先组织处理本报告列明的具体问题，并按要求补齐资料。"
                     f"完成真实更正和资料补充后，应发起新一轮全量复查，由稽查人员继续核对原问题是否处理完成，以及补充资料是否带出新的关联问题。")

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
        one_line = _brief(first_para.get("text", ""), limit=70)
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


def build_enterprise_readable_report(report_data):
    """主入口：从分析结果组装 enterprise_readable_report"""
    if not isinstance(report_data, dict):
        return {}

    problems = _build_confirmed_problems(report_data)
    completed = _build_completed_checks(report_data)
    materials = _build_materials(report_data)
    procedures = _build_procedures(report_data)
    further = _build_further_checks(report_data)
    summary = _build_summary(report_data, problems, completed, further)
    plans = _build_action_plan(problems)
    discovery_overview = _build_discovery_overview(report_data, problems, completed, further)

    return {
        "compilation_style": "税务稽查文书式报告",
        "generated_date": datetime.now().strftime("%Y年%m月%d日 %H时%M分"),
        "identity": _build_identity(report_data),
        "inspector_perspective": _build_inspector_perspective(),
        "summary": summary,
        "discovery_overview": discovery_overview,
        "inspection_procedures": procedures,
        "materials": materials,
        "confirmed_problems": problems,
        "completed_checks": completed,
        "action_plan": plans,
        "further_checks": further,
        "recheck": {
            "trigger": "企业完成真实整改或补充资料后，重新点击一键分析。",
            "work": "下一轮将重新读取全部资料，复查本轮问题，检查补充资料带出的关联事项，并比较前后两轮变化。",
            "convergence": "问题逐项处理、资料逐步完整、账务与申报能够相互核对，才表示企业正在趋于合规；不能以问题数量为零或分数下降单独判断。",
        },
        "report_statement": [
            "本报告只对本轮已上传且能够读取的资料负责，未上传资料不在本轮具体问题认定范围内。",
            "本报告所列“具体问题”均有本轮资料中的直接数据或可回查证据支持；资料不足的事项已单独列入补充资料后再检查清单。",
            "本报告采用税务稽查文书式结构和稽查人员陈述口径编制，所列检查事实、处理意见和复查要求用于企业合规整改。",
            "企业应依据真实业务和原始资料办理整改，不得倒签、补造、篡改、删除或隐匿资料。",
        ],
    }
