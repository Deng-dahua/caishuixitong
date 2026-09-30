"""特定/专项风险红线探测器（2026-09-30）

为覆盖度审计中"盲区"（既无检测器也不在 _DEFAULT_HIT_INDEX 兜底）的特定/专项红线
补上**可执行的识别路径**，使这些红线在运行期由 `_map_finding` 走 `mode="declared"`
必然归位，而非仅靠 `match_redline_grounded` 文本模糊匹配碰运气。

覆盖红线：
    RL-INC-004 其他应付款大额长期挂账        RL-COST-001 暂估成本长期挂账
    RL-FUND-003 股东借款年末未还              RL-FUND-004 大额现金收付
    RL-INV-001 账实不符                       RL-INV-002 存货长期不动销
    RL-INV-003 投入产出不匹配                 RL-PAY-004 劳务报酬与工资薪金混淆
    RL-CIT-002 关联方无偿/低价资金往来        RL-CIT-003 研发费用加计扣除归集异常
    RL-AST-002 政府补助与收益确认异常         RL-OTH-002 持有房产土地未申报
    RL-SPT-001 土地增值税未清算               RL-SPT-002 应税消费品未申报消费税
    RL-SPT-003 资源税                          RL-SPT-004 环境保护税
    RL-SPT-005 进口完税价格申报不实           RL-SPT-006 向非居民支付未源泉扣缴
    RL-SPT-007 承受土地房屋权属未申报契税     RL-SPT-009 股权转让价格明显偏低
    RL-SPT-010 住房公积金未全员缴存           RL-VAT-009 价外费用未并入销售额

核心原则（严守系统铁律，绝不越权定性）：
1. 发现≠确认：只产出「待核疑点 / 置疑清单」，绝不下定性结论。
2. 有数据 → 命中即产出待核线索；无对应税种申报记录才升级为置疑。
3. 每个红线的识别方法固化在 SPECS.methods，报告/审计可追溯"凭什么识别"。
4. 表驱动：新增同类红线只需在 SPECS 加一行数据（含 redline_id 字面量），不改引擎分支。

数据契约（engine_data，键均可缺省）：
    balances 科目余额表 | vouchers 序时账/凭证 | sal_invs/pur_invs 销项/进项发票
    bank_txs 银行流水 | salaries 工资表 | inventory 库存台账 | tax_declarations 申报表
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from engine.gap_risk_detectors import _finding, _dump

# ── 表驱动规格（每条＝一行数据；redline_id 为字面量，供覆盖审计识别 + 运行期 declared 归位）──
SPECS: List[Dict[str, Any]] = [
    {
        "redline_id": "RL-INC-004", "topic": "其他应付款大额长期挂账（待核）", "tax_type": "企业所得税",
        "signals": ["其他应付款"],
        "decl_keywords": [],
        "needs": ["科目余额表-其他应付款明细", "银行流水", "借款合同或往来协议"],
        "method": "检索科目余额表其他应付款余额及明细 → 对象为无关联自然人或经营范围不符企业、长期无还款无利息 → 命中即置疑要求补合同与流水",
        "policy_ref": "《企业所得税法》第六条、《税收征收管理法》第三十五条",
        "level": "低风险", "score": 3,
    },
    {
        "redline_id": "RL-COST-001", "topic": "暂估成本长期挂账未取得发票冲回（待核）", "tax_type": "企业所得税",
        "signals": ["暂估"],
        "decl_keywords": [],
        "needs": ["科目余额表-暂估科目", "进项发票", "采购合同", "入库单", "企业所得税申报表"],
        "method": "检索科目余额表/序时账暂估入库科目 → 跨年度未取得发票冲回、汇算清缴前未调增 → 命中即置疑",
        "policy_ref": "国家税务总局公告2018年第28号",
        "level": "低风险", "score": 3,
    },
    {
        "redline_id": "RL-FUND-003", "topic": "股东借款年末未归还且未用于经营（待核）", "tax_type": "个人所得税",
        "require": ["股东"],  # 须见"股东"上下文，其他应收款本身 != 股东借款
        "signals": ["其他应收款"],
        "decl_keywords": [],
        "needs": ["其他应收款明细", "银行流水", "个税申报表", "借款合同"],
        "method": "检索其他应收款明细中股东（含家庭成员）往来 → 跨纳税年度未归还、未用于经营 → 命中即置疑视同分红",
        "policy_ref": "财税〔2003〕158号第二条",
        "level": "低风险", "score": 3,
    },
    {
        "redline_id": "RL-FUND-004", "topic": "大额现金收付：交易真实性无法验证（待核）", "tax_type": "增值税",
        "signals": ["坐支", "大额现金", "现金交易", "现金收付", "白条抵库"],
        "decl_keywords": [],
        "needs": ["现金日记账", "记账凭证", "银行流水", "出库单"],
        "method": "检索库存现金科目与现金日记账大额收付 → 超结算起点1000元且无法由银行流水印证 → 命中即置疑",
        "policy_ref": "《现金管理暂行条例》第五条、第六条",
        "level": "低风险", "score": 3,
    },
    {
        "redline_id": "RL-INV-001", "topic": "账实不符：存货账面与实际库存不符（待核）", "tax_type": "增值税",
        "signals": ["盘亏", "盘盈", "待处理财产损溢", "账实不符", "存货差异"],
        "decl_keywords": [],
        "needs": ["进销存台账", "盘点表", "出入库单", "仓储合同"],
        "method": "检索存货盘盈亏/待处理财产损溢 → 无合理损耗报废处理、未转出进项 → 命中即置疑",
        "policy_ref": "《增值税暂行条例》第十条、财税〔2016〕36号附件1第二十七条",
        "level": "低风险", "score": 3,
    },
    {
        "redline_id": "RL-INV-002", "topic": "存货长期不动销：滞销挂账或虚假存货（待核）", "tax_type": "企业所得税",
        "signals": ["呆滞", "滞销", "库存积压", "不动销"],
        "decl_keywords": [],
        "needs": ["进销存台账", "盘点表", "采购合同", "入库单"],
        "method": "检索长期无出库记录的存货品种 → 未计提跌价准备或报废 → 命中即置疑",
        "policy_ref": "《企业所得税法》第八条、第十条",
        "level": "低风险", "score": 3,
    },
    {
        "redline_id": "RL-INV-003", "topic": "投入产出不匹配：耗用与产量背离（待核）", "tax_type": "增值税",
        "signals": ["BOM", "单耗", "投入产出比", "单位产品材料耗用"],
        "decl_keywords": [],
        "needs": ["BOM物料清单", "领料单", "完工入库单", "能耗单据"],
        "method": "比对单位产品材料耗用与BOM/行业经验值 → 投入与产出无合理配比、无工艺变更解释 → 命中即置疑",
        "policy_ref": "《增值税暂行条例》第一条、财税〔2016〕36号",
        "level": "低风险", "score": 3,
    },
    {
        "redline_id": "RL-PAY-004", "topic": "劳务报酬与工资薪金混淆：用工身份与扣缴不实（待核）", "tax_type": "个人所得税",
        "signals": ["劳务费", "劳务报酬"],
        "decl_keywords": [],
        "needs": ["工资表", "劳务合同", "费用明细账", "进项发票", "个税申报表"],
        "method": "比对工资名单与劳务费支付名单 → 长期固定/按月计酬人员按劳务报酬处理 → 命中即置疑扣缴范围",
        "policy_ref": "《个人所得税法》第二条、国税发〔1994〕89号",
        "level": "低风险", "score": 3,
    },
    {
        "redline_id": "RL-CIT-002", "topic": "关联方无偿或低价资金往来：未按独立交易原则计息（待核）", "tax_type": "企业所得税",
        "signals": ["资金拆借", "统借统还", "资金占用", "关联方资金", "关联方往来"],
        "decl_keywords": [],
        "needs": ["银行流水", "往来明细", "资金拆借协议"],
        "method": "检索关联方资金拆借 → 未收付利息或利率偏离同期金融机构贷款利率、未作特别纳税调整 → 命中即置疑",
        "policy_ref": "《企业所得税法》第四十一条、《特别纳税调整实施办法》",
        "level": "低风险", "score": 3,
    },
    {
        "redline_id": "RL-CIT-003", "topic": "研发费用加计扣除归集异常（待核）", "tax_type": "企业所得税",
        "signals": ["研发支出", "研发费用", "加计扣除"],
        "decl_keywords": [],
        "needs": ["研发费用辅助账", "立项文件", "工时记录", "领料单"],
        "method": "检索研发费用归集 → 无立项/工时记录、与生产费用未分别核算 → 命中即置疑加计扣除合规性",
        "policy_ref": "财税〔2015〕119号、国家税务总局公告2015年第97号",
        "level": "低风险", "score": 3,
    },
    {
        "redline_id": "RL-AST-002", "topic": "政府补助与收益确认纳税调整异常（待核）", "tax_type": "企业所得税",
        "signals": ["递延收益", "政府补助", "专项应付款", "财政拨款", "补助收入"],
        "decl_keywords": [],
        "needs": ["科目余额表", "政府补助文件", "企业所得税申报表"],
        "method": "检索递延收益/其他收益/专项应付款 → 未计入应税收入或不符合不征税收入三条件 → 命中即置疑",
        "policy_ref": "财税〔2011〕70号第一条、第二条",
        "level": "低风险", "score": 3,
    },
    {
        "redline_id": "RL-OTH-002", "topic": "持有房产土地未申报房产税、土地使用税（待核）", "tax_type": "房产税",
        "signals": ["房屋建筑物", "房产原值", "土地使用权"],
        "decl_keywords": ["房产税", "城镇土地使用税"],
        "needs": ["资产负债表", "固定资产明细", "房产税申报表"],
        "method": "检索固定资产房屋建筑物/土地使用权 → 无对应房产税、土地使用税申报 → 命中即置疑计税依据",
        "policy_ref": "《房产税暂行条例》第二条、第三条",
        "level": "低风险", "score": 3,
    },
    {
        "redline_id": "RL-SPT-001", "topic": "土地增值税未清算或扣除项目不实（待核）", "tax_type": "土地增值税",
        "source": "sales",
        "signals": ["不动产销售", "土地出让", "转让不动产", "土地增值税清算", "开发产品转让"],
        "decl_keywords": ["土地增值税"],
        "needs": ["土地出让合同", "开发成本明细账", "建安发票", "竣工验收备案表", "销售明细表", "土地增值税申报表"],
        "method": "检索不动产/土地使用权转让收入与开发成本 → 达清算条件未清算或扣除项目无合法凭证 → 命中即置疑",
        "policy_ref": "《土地增值税暂行条例》、国税发〔2009〕91号",
        "level": "低风险", "score": 3,
    },
    {
        "redline_id": "RL-SPT-002", "topic": "应税消费品未申报消费税或计税价格偏低（待核）", "tax_type": "消费税",
        "source": "sales",  # 消费税风险只看"销售/生产"侧；采购化妆品 != 生产销售应税消费品
        "signals": ["消费税", "应税消费品", "成品油", "化妆品", "贵重首饰", "高尔夫", "游艇"],
        "decl_keywords": ["消费税"],
        "needs": ["产成品明细账", "销售发票与台账", "委托加工合同", "消费税申报表"],
        "method": "检索经营范围/发票品名涉应税消费品 → 无对应消费税申报或关联售价明显偏低 → 命中即置疑",
        "policy_ref": "《消费税暂行条例》第一条、第三条、《消费税暂行条例实施细则》",
        "level": "低风险", "score": 3,
    },
    {
        "redline_id": "RL-SPT-003", "topic": "开采应税资源未申报资源税或销售量与产量不符（待核）", "tax_type": "资源税",
        "source": "sales",
        "signals": ["资源税", "原矿", "选矿", "采矿"],
        "decl_keywords": ["资源税"],
        "needs": ["采矿许可证", "产量台账", "过磅单", "存货明细账", "资源税申报表"],
        "method": "检索采矿/选矿经营 → 申报销售数量与产量台账/过磅记录存在差异 → 命中即置疑",
        "policy_ref": "《资源税法》第一条、第三条",
        "level": "低风险", "score": 3,
    },
    {
        "redline_id": "RL-SPT-004", "topic": "直接排放应税污染物未申报环境保护税（待核）", "tax_type": "环境保护税",
        "signals": ["环境保护税", "环保税", "排污", "排污许可证", "污染物排放"],
        "decl_keywords": ["环境保护税", "环保税"],
        "needs": ["排污许可证", "环评批复", "自动监测数据或检测报告", "环境保护税申报表"],
        "method": "检索工业排污线索 → 无对应环境保护税申报或申报排放量低于监测数据 → 命中即置疑",
        "policy_ref": "《环境保护税法》第二条、第五条",
        "level": "低风险", "score": 3,
    },
    {
        "redline_id": "RL-SPT-005", "topic": "进口货物完税价格申报不实（待核）", "tax_type": "关税",
        "source": "purchase", "require": ["报关"],  # 只有自身"进口报关"才是关税义务人
        "signals": ["进口", "报关", "海关", "完税价格"],
        "decl_keywords": ["关税"],
        "needs": ["进口报关单", "海关专用缴款书", "进口合同", "对外付汇凭证", "运输与保险单据"],
        "method": "检索进口/报关/付汇记录 → 申报成交价格与对外付汇金额不符、未含运费保险费特许权使用费 → 命中即置疑",
        "policy_ref": "《海关法》第五十五条、《进出口关税条例》第十八条",
        "level": "低风险", "score": 3,
    },
    {
        "redline_id": "RL-SPT-006", "topic": "向非居民支付境内所得未履行源泉扣缴（待核）", "tax_type": "企业所得税",
        "signals": ["非居民", "源泉扣缴", "预提所得税", "特许权使用费", "技术服务费"],
        "decl_keywords": ["扣缴企业所得税", "预提所得税", "源泉扣缴"],
        "needs": ["境外付款台账", "对外付汇凭证", "合同或协议", "扣缴企业所得税报告表", "完税凭证"],
        "method": "检索向境外（含中国港澳台地区）付款记录 → 无对应扣缴企业所得税申报与完税凭证 → 命中即置疑",
        "policy_ref": "《企业所得税法》第三十七条、第三十八条",
        "level": "低风险", "score": 3,
    },
    {
        "redline_id": "RL-SPT-007", "topic": "承受土地房屋权属未申报契税（待核）", "tax_type": "契税",
        "signals": ["契税", "受让", "不动产权", "房屋买卖", "土地使用权出让"],
        "decl_keywords": ["契税"],
        "needs": ["权属转移合同", "不动产权证或登记查询结果", "契税申报表", "完税凭证", "评估报告"],
        "method": "检索受让土地使用权/房屋权属转移 → 无权属变更后契税申报与完税凭证 → 命中即置疑",
        "policy_ref": "《契税法》第一条、第二条",
        "level": "低风险", "score": 3,
    },
    {
        "redline_id": "RL-SPT-009", "topic": "股权转让价格明显偏低且无正当理由（待核）", "tax_type": "个人所得税",
        "signals": ["股权转让", "股东变更", "股权变动", "转让股权"],
        "decl_keywords": [],
        "needs": ["股权转让协议及补充协议", "股东决议", "工商变更登记", "银行流水与付款凭证", "转让时点财务报表或评估报告", "完税凭证"],
        "method": "检索股权转让/长期股权投资变动 → 申报价格低于净资产份额/初始成本、协议价与实付不符 → 命中即置疑",
        "policy_ref": "国家税务总局公告2014年第67号第十二条、第十四条",
        "level": "低风险", "score": 3,
    },
    {
        "redline_id": "RL-SPT-010", "topic": "住房公积金未开户、未全员缴存或基数不实（待核）", "tax_type": "住房公积金",
        "mode": "absence",  # 风险＝"未"缴存：须见用工存在，且公积金资料缺失
        "presence_signals": ["工资", "薪金", "社保", "职工", "人员"],
        "absence_data_key": "housing_fund",
        "absence_signals": ["缴存登记", "缴存基数"],
        "signals": ["工资", "薪金", "社保", "职工"],
        "decl_keywords": [],
        "needs": ["工资表", "个税申报明细", "社保参保明细", "住房公积金缴存明细", "劳动合同"],
        "method": "比对工资表人数/社保参保人数与公积金缴存人数 → 未开户、人数或基数低于实际 → 命中即置疑",
        "policy_ref": "《住房公积金管理条例》第十五条、第十六条、第二十条",
        "level": "低风险", "score": 3,
    },
    {
        "redline_id": "RL-VAT-009", "topic": "价外费用未并入销售额申报（待核）", "tax_type": "增值税",
        "source": "sales",
        # ★ 2026-09-30：原 signals 只留「违约金/赔偿金/价外费用」，却剔除「包装费/滞纳金」，
        #   理由写的是"常见于采购"——但本 spec 已是 `source="sales"`（只看销项发票+合同），
        #   采购侧噪声**已被 source 排除**，剔除反而使**采集信号与红线要件1/method 文案不符**
        #   （要件1 明列：违约金、赔偿金、滞纳金、包装费、代收款项）。
        #   现按《增值税暂行条例实施细则》第十二条「价外费用」名目补齐，与要件对齐；
        #   仍只查向购买方**收取**侧，故不会把采购取得的包装费/滞纳金误报为价外费用。
        "signals": ["违约金", "赔偿金", "滞纳金", "包装费", "包装物租金",
                    "延期付款利息", "代收款项", "代垫款项", "优质费"],
        "decl_keywords": [],
        "needs": ["收款凭证与银行流水", "合同价外费用条款", "代收代付或返还证明"],
        "method": "检索向购买方收取的违约金/赔偿金/滞纳金/包装费等 → 未开票未并入销售额、混入往来科目 → 命中即置疑",
        "policy_ref": "《增值税暂行条例》第六条、《增值税暂行条例实施细则》第十二条",
        "level": "低风险", "score": 3,
    },
    {
        "redline_id": "RL-CIT-010", "topic": "资本弱化：关联债资比超 2:1 利息扣除受限（待核）", "tax_type": "企业所得税",
        "signals": ["关联方借款", "关联借款", "统借统还", "关联方资金拆借", "资本弱化"],
        "decl_keywords": [],
        "needs": ["借款合同", "科目余额表", "利息支出明细账", "企业所得税申报表", "同期资料"],
        "method": "检索关联方借款/资金拆借 → 计算关联债资比是否超过 2:1（金融企业5:1，权益性投资含实收资本+资本公积+盈余公积），超标准部分利息不得税前扣除、须作纳税调增 → 命中即置疑",
        "policy_ref": "《企业所得税法》第四十六条、财税〔2008〕121号",
        "level": "低风险", "score": 3,
    },
]

# 供覆盖审计识别的字面量已在 SPECS 的 "redline_id" 键中（见上）。


# ── 要件级证据：只认领扫描器**真算过**的要件（记录数/金额），宁缺勿错 ──────────
_AMOUNT_KEYS = ("金额", "本期发生额", "期末余额", "期末贷方", "期末借方", "余额",
                "close_credit", "close_debit", "current_debit", "current_credit",
                "amount", "借方", "贷方", "debit", "credit", "价税合计")


def _to_amt(v: Any) -> float:
    try:
        s = str(v).replace(",", "").replace("￥", "").replace("¥", "").replace("元", "").strip()
        return abs(float(s)) if s else 0.0
    except Exception:
        return 0.0


def _match_stats(rows: List[Any], signals: Sequence[str]):
    """统计命中信号的记录数及涉及金额（扫描器实际算出的量）。"""
    n = 0
    amt = 0.0
    for row in rows:
        if any(s in _dump(row) for s in signals):
            n += 1
            if isinstance(row, dict):
                for k in _AMOUNT_KEYS:
                    if k in row:
                        amt += _to_amt(row.get(k))
    return n, amt


def run_special_redline_detection(engine_data: Dict, pipeline_log: List[str] = None) -> List[Dict]:
    """执行全部特定/专项风险探测器。

    返回待核发现列表（只含疑点或置疑请求，绝不含定性结论）。
    每条发现带 redline_id（运行期 declared 归位）+ constituent_hits（要件级观察事实）。
    任何单条异常都不影响其余执行。
    """
    data = engine_data if isinstance(engine_data, dict) else {}
    src_rows: List[Any] = []
    for _k in ("vouchers", "balances", "bank_txs", "sal_invs", "pur_invs", "salaries",
               "inventory", "tax_declarations", "fixed_assets", "contracts",
               "social_security", "housing_fund"):
        _v = data.get(_k)
        if isinstance(_v, list):
            src_rows.extend(_v)
    vch = _dump(data.get("vouchers"))
    bal = _dump(data.get("balances"))          # 科目余额表
    bank = _dump(data.get("bank_txs"))
    invs = _dump(data.get("sal_invs")) + "\n" + _dump(data.get("pur_invs"))
    sal = _dump(data.get("salaries"))
    inv = _dump(data.get("inventory"))
    decl = _dump(data.get("tax_declarations"))
    fa = _dump(data.get("fixed_assets"))       # 固定资产明细
    ct = _dump(data.get("contracts"))          # 合同
    ss = _dump(data.get("social_security"))    # 社保明细
    hf = _dump(data.get("housing_fund"))       # 公积金明细
    text = "\n".join([vch, bal, bank, invs, sal, inv, decl, fa, ct, ss, hf])

    # 精度关键：按"风险发生侧"分文本——销售/提供侧只看销项发票+合同，
    # 避免把"采购/持有"信号误当成"销售/申报"风险（如传媒买化妆品 != 生产销售应税消费品）。
    _NL = chr(10)
    _sale = _dump(data.get("sal_invs"))
    _pur = _dump(data.get("pur_invs"))
    texts = {
        "all": _NL.join([vch, bal, bank, _sale, _pur, sal, inv, decl, fa, ct, ss, hf]),
        "sales": _NL.join([_sale, ct]),
        "purchase": _NL.join([_pur, vch, bal, fa, ct]),
    }

    results: List[Dict] = []
    for spec in SPECS:
        try:
            t = texts.get(spec.get("source", "all"), texts["all"])
            if spec.get("mode") == "absence":
                # 缺席型：须见"用工存在"信号；且对应数据缺失 或 未见"已缴存"信号
                pres = [k for k in spec.get("presence_signals", []) if k in t]
                if not pres:
                    continue
                akey = spec.get("absence_data_key")
                if akey and data.get(akey):
                    continue  # 对应资料已提供 → 视为已缴存，不置疑
                if any(k in t for k in spec.get("absence_signals", [])):
                    continue
                hits = pres
            else:
                hits = [k for k in spec.get("signals", []) if k and k in t]
                if not hits:
                    continue
                req = spec.get("require") or []
                if req and not all(k in t for k in req):
                    continue  # 必需上下文未同时出现 → 不足以置疑（防误报）
            dl = spec.get("decl_keywords") or []
            if dl and any(k in decl for k in dl):
                continue  # 已见对应税种申报/缴款记录 → 不置疑
            detail = (
                f"在账簿/申报资料中检测到涉及「{spec['topic'].rstrip('（待核）')}」的相关线索"
                f"（命中：{'、'.join(hits[:4])}）。本项为待核疑点：请补充下列资料后复核，"
                "以确认是否属于法定正当情形。"
            )
            f = _finding(
                spec["redline_id"], spec["topic"], spec["tax_type"], detail,
                spec["level"], spec["score"], needs_material=spec["needs"],
                unconfirmed=True, policy_ref=spec.get("policy_ref", ""), evidence=hits[:4],
            )
            n, amt = _match_stats(src_rows, hits)
            _ev = (f"命中「{'、'.join(hits[:3])}」相关记录 {n} 条"
                   + (f"，涉及金额 {amt:,.2f} 元" if amt else "")
                   + "（要件观察事实；是否构成该要件之情形须人工复核）")
            f["constituent_hits"] = [{"index": int(spec.get("hit_index", 1)), "evidence": _ev}]
            f["_detection_method"] = spec.get("method", "")
            results.append(f)
        except Exception as exc:  # 单条异常不阻断整体
            if pipeline_log is not None:
                pipeline_log.append(f"[专项探测器] {spec.get('redline_id')} 执行异常: {exc}")

    if pipeline_log is not None and results:
        pipeline_log.append(
            f"[专项探测器] 特定/专项风险域检出 {len(results)} 条待核事项"
        )
    return results
