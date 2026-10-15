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
        "method": "检索库存现金科目与现金日记账的现金收付（坐支、白条抵库等不规范形态）→ 无法由银行流水印证、收入未申报或成本无合规凭证 → 命中即置疑",
        "policy_ref": "《税收征收管理法》第六十三条、《人民币银行结算账户管理办法》第八条",
        "level": "低风险", "score": 3,
    },
    {
        "redline_id": "RL-INV-001", "topic": "账实不符：存货账面与实际库存不符（待核）", "tax_type": "增值税",
        "signals": ["盘亏", "盘盈", "待处理财产损溢", "账实不符", "存货差异"],
        "decl_keywords": [],
        "needs": ["进销存台账", "盘点表", "出入库单", "仓储合同"],
        "method": "检索存货盘盈亏/待处理财产损溢 → 无合理损耗报废处理、未转出进项 → 命中即置疑",
        "policy_ref": "《中华人民共和国增值税法》第二十二条（非正常损失等不得抵扣情形）",
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
        "policy_ref": "《税收征收管理法》第三十五条、《中华人民共和国增值税法》",
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
        "policy_ref": "《中华人民共和国海关法》第五十三条、《中华人民共和国关税法》第二十四条、第二十五条",
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
        #   现按现行增值税法关于销售额（价外费用并入）的口径补齐，与要件对齐；
        #   仍只查向购买方**收取**侧，故不会把采购取得的包装费/滞纳金误报为价外费用。
        "signals": ["违约金", "赔偿金", "滞纳金", "包装费", "包装物租金",
                    "延期付款利息", "代收款项", "代垫款项", "优质费"],
        "decl_keywords": [],
        "needs": ["收款凭证与银行流水", "合同价外费用条款", "代收代付或返还证明"],
        "method": "检索向购买方收取的违约金/赔偿金/滞纳金/包装费等 → 未开票未并入销售额、混入往来科目 → 命中即置疑",
        "policy_ref": "《中华人民共和国增值税法》第十七条（销售额）、《中华人民共和国增值税法实施条例》第十五条",
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
    {
        "redline_id": "RL-VAT-014", "topic": "异地建筑服务/不动产租赁销售未在项目所在地预缴增值税（待核）",
        "tax_type": "增值税",
        # 只看提供方/销售侧：企业采购建筑服务（进项）不构成其预缴义务，source=sales 天然排除。
        "source": "sales",
        "signals": ["建筑服务", "工程施工", "建筑安装", "安装服务", "装饰服务", "修缮服务",
                    "不动产经营租赁", "不动产租赁", "销售不动产"],
        "decl_keywords": ["预缴税款表", "预缴增值税", "预缴税款"],
        "needs": ["建筑服务合同", "增值税预缴税款表", "缴款凭证", "增值税申报表"],
        "method": "在销项侧（销项发票品名＋合同）检索提供建筑服务、出租或销售不动产的应税行为 → 未见《增值税预缴税款表》或异地预缴完税凭证 → 命中即置疑（项目与机构在同一县市区依法无需预缴者除外）",
        "policy_ref": "国家税务总局公告2016年第17号（跨县市区建筑服务）、第16号（不动产经营租赁）、第14号（转让不动产）",
        "level": "待核验", "score": 4,
    },
    {
        "redline_id": "RL-VAT-015", "topic": "农产品收购发票进项真实性存疑（待核）",
        "tax_type": "增值税",
        # 农产品收购发票由购买方自开并作进项抵扣，故在进项侧（进项发票＋凭证＋账簿）检索。
        "source": "purchase",
        "signals": ["农产品收购发票", "收购发票", "农产品收购", "免税农产品"],
        "decl_keywords": [],
        "needs": ["农产品收购发票", "收购台账", "过磅单与入库验收单", "银行付款记录"],
        "method": "在进项侧（进项发票＋凭证＋账簿）检索农产品收购发票/收购凭证 → 要求以收购台账、过磅单、入库验收单、农户身份信息与付款记录佐证 → 无佐证即置疑（属农产品核定扣除试点并已按核定方法计算进项税额者除外）",
        "policy_ref": "财税〔2017〕37号（农产品进项税额抵扣）、财税〔2012〕38号（农产品增值税进项税额核定扣除试点实施办法）",
        "level": "待核验", "score": 4,
    },]

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



# ══════════ RL-SPT-012 股权转让未申报个人所得税（专用探测器）═════════════════════
# 该红线此前只有 `_DEFAULT_HIT_INDEX` 兜底（软匹配），覆盖度审计把它记为「仅兜底」：
# 生产链路里没有任何真检测器去认领它。补上专用探测器后，运行期走 `_map_finding` 的
# `mode="declared"` 必然归位，而不是靠文本模糊匹配碰运气。
#
# 口径（严守"发现≠确认 / 缺数不得编"两条铁律）：
#   1. 只认**实质线索**：合同、序时账、银行流水、科目余额里出现股权转让/股权变动态；
#      不把任意含"股权"两字的记录都当证据（"股权投资""实收资本"是另一回事）。
#   2. 「是否已申报缴纳股权转让个税」无法从现有资料直接读出 ⇒ 用**反证缺席**规避：
#      资料里同一处同时出现股权转让与完税/完税凭证字样 → 视为可能已申报，不置疑。
#   3. 要件1 的前置「转让方为自然人」本轮资料无法确认 ⇒ 结论只能是**待核验**，
#      且**不试算税额**（缺转让协议与价款支付流水，缺数不得编）。
#   4. 命中记录数可以报（扫描器真算过），但**不报"涉及金额"**：
#      银行流水里 matched 行的金额多为变更登记服务费/手续费，报成"股权转让涉及金额"会误导。
_EQUITY_SIGNALS = (
    "股权转让", "股权变更", "转让股权", "受让股权", "股权变动", "股权转让协议",
)
# 反证：股权转让与完税凭证同时出现 → 可能已申报缴纳，不置置疑
_EQUITY_PAY_EVIDENCE = ("完税", "完税凭证", "税收缴款书", "缴税凭证")
_EQUITY_SOURCE_KEYS = ("contracts", "vouchers", "bank_txs", "balances")

_EXTRA_DETECTORS = ()


def _detect_equity_transfer_iit(data, texts=None, pipeline_log=None):
    """RL-SPT-012 专用检测器：检出自然人股权转让线索 + 无完税凭证 → 待核置疑。"""
    src_text = chr(10).join([_dump(data.get(k)) for k in _EQUITY_SOURCE_KEYS])
    if not src_text:
        return []
    hits = [k for k in _EQUITY_SIGNALS if k in src_text]
    if not hits:
        return []
    # 反证缺席：同一处既有股权转让、又有完税凭证 → 可能已申报，不置疑
    # ★ 反证要连 tax_declarations 一起看（完税凭证/缴款记录多落在申报资料里）；
    #   但信号本身仍只认合同/序时账/银行流水/科目余额，免得“证书里有转让字样”就当线索。
    pay_text = src_text + chr(10) + _dump(data.get("tax_declarations"))
    if any(k in pay_text for k in _EQUITY_PAY_EVIDENCE):
        return []
    # 计记录数（扫描器真算过的量）
    n = 0
    for k in _EQUITY_SOURCE_KEYS:
        v = data.get(k)
        if isinstance(v, list):
            for row in v:
                if any(s in _dump(row) for s in hits):
                    n += 1
    redline_id = "RL-SPT-012"
    topic = "股权转让未申报个人所得税（待核）"
    detail = (
        "本轮资料中检出涉及股权转让/股权变更的线索"
        "（命中：{hits}；来源：合同、序时账、银行流水、科目余额中相关记录 {n} 条）。"
        "股权转让所得个人所得税的纳税义务人为**转让方自然人**，受让方支付方负代扣代缴义务；"
        "本轮资料中未见股权转让个人所得税的完税凭证或缴款记录。需要说明两点："
        "①转让方是否为自然人（要件前提）须凭股权转让协议与工商变更登记核实；"
        "②因缺转让协议与转让价款支付流水，本项**不作税额试算**，缺数不编。"
        "请补充下列资料后复核。"
    ).format(hits="、".join(hits[:4]), n=n)
    f = _finding(
        redline_id, topic, "个人所得税", detail,
        "待核验", 4,
        needs_material=[
            "股权转让协议", "工商变更登记", "转让价款支付流水",
            "转让方身份证明或变更登记申请表", "完税凭证", "被投资企业资产负债表（净资产）",
        ],
        unconfirmed=True,
        policy_ref="国家税务总局公告2014年第67号《股权转让所得个人所得税管理办法（试行）》",
        evidence=hits[:4],
    )
    f["constituent_hits"] = [
        {"index": 4, "evidence": "本轮资料未见股权转让个人所得税完税凭证或缴款记录"
                                 "（缺资料 ≠ 已认定未申报，须企业举证）"},
        {"index": 1, "evidence": "检出股权转让/股权变更相关记录 %d 条，转让方是否为自然人仍尚需核实" % n},
    ]
    f["_detection_method"] = (
        "检索合同、序时账、银行流水、科目余额中的股权转让/股权变动态；"
        "如同时出现完税凭证字样则视为可能已申报而不置疑；不试算税额（缺转让价款与协议）。"
    )
    return [f]


_EXTRA_DETECTORS = (_detect_equity_transfer_iit,)

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

    # ── 专用探测器：表驱动 SPECS 之外个别红线的专属识别路径（每行为一个 _EXTRA_DETECTORS 元素）──
    for _extra in _EXTRA_DETECTORS:
        try:
            results.extend(_extra(data, texts, pipeline_log))
        except Exception as _exc:  # 单条异常不阻断整体
            if pipeline_log is not None:
                pipeline_log.append("[专项探测器] %s 执行异常: %s" % (_extra.__name__, _exc))
    if pipeline_log is not None and results:
        pipeline_log.append(
            f"[专项探测器] 特定/专项风险域检出 {len(results)} 条待核事项"
        )
    return results

# ═══ BEGIN BATCH_SPECS_LOADER (auto-generated by scripts/_apply_rule_batch.py) ═══
# ★ 批次检测规格**字面量**（数据源 `config/rule_batches/batch_*.json`）
#   并入后新规则立即获得**可执行检测路径**（signals 命中即置疑）。
_BATCH_SPECS: List[Dict] = (
[
    {
        "redline_id": "RL-VAT-016",
        "topic": "对开环开发票：交易闭环（待核）",
        "tax_type": "增值税",
        "signals": [
            "对开",
            "环开",
            "互开",
            "循环开票",
            "闭环开票",
            "对开发票"
        ],
        "decl_keywords": [],
        "needs": [
            "进销项发票明细",
            "购销合同",
            "出入库单",
            "银行流水",
            "开票对象清单"
        ],
        "method": "检索进销项发票与合同中出现对开/环开/互开/闭环情形 → 交易对手互为购销双方、无对应货物流 → 命中即置疑核查商业实质",
        "policy_ref": "《中华人民共和国发票管理办法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-001"
    },
    {
        "redline_id": "RL-VAT-017",
        "topic": "富余票：票货分离（待核）",
        "tax_type": "增值税",
        "signals": [
            "富余票",
            "票货分离",
            "有票无货",
            "多余票",
            "票货不符"
        ],
        "decl_keywords": [],
        "needs": [
            "进销项发票明细",
            "出入库单",
            "购销合同",
            "资金流水"
        ],
        "method": "检索出现「富余票/票货分离/有票无货」等情形 → 开票金额超出实际货物交易、票面品名与库存/物流无对应 → 命中即置疑",
        "policy_ref": "《中华人民共和国发票管理办法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-001"
    },
    {
        "redline_id": "RL-VAT-018",
        "topic": "开票方走逃（失联）：发票来源异常（待核）",
        "tax_type": "增值税",
        "signals": [
            "走逃",
            "失联",
            "非正常户",
            "失控发票",
            "走逃失联"
        ],
        "decl_keywords": [],
        "needs": [
            "进项发票明细",
            "供应商档案",
            "采购合同",
            "银行流水"
        ],
        "method": "检索发票来源方出现「走逃/失联/非正常户」标识或相关描述 → 核实该发票是否属异常凭证、进项是否按规定处理 → 命中即置疑",
        "policy_ref": "《中华人民共和国发票管理办法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-001"
    },
    {
        "redline_id": "RL-VAT-019",
        "topic": "涉税中介协助开票（待核）",
        "tax_type": "增值税",
        "signals": [
            "涉税中介",
            "税务代理",
            "代理开票",
            "中介协助",
            "代账公司"
        ],
        "decl_keywords": [],
        "needs": [
            "代理服务合同",
            "发票明细",
            "服务成果交付记录",
            "资金流水"
        ],
        "method": "检索与涉税中介/代理记账机构的服务关系 → 代理开票量与实际业务规模不匹配、无服务成果交付 → 命中即置疑核查中介责任",
        "policy_ref": "《中华人民共和国税收征收管理法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-001"
    },
    {
        "redline_id": "RL-VAT-020",
        "topic": "拆分交易化整为零：规避限额（待核）",
        "tax_type": "增值税",
        "signals": [
            "拆分合同",
            "化整为零",
            "分拆开票",
            "拆分开票",
            "分割合同"
        ],
        "decl_keywords": [],
        "needs": [
            "合同清单",
            "发票明细",
            "交易实质说明",
            "资金流水"
        ],
        "method": "检索同一交易被拆分为多份合同或多张发票 → 拆分后单笔均低于某临界值、且时间与标的连续 → 命中即置疑核查拆分目的",
        "policy_ref": "《中华人民共和国发票管理办法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-001"
    },
    {
        "redline_id": "RL-VAT-021",
        "topic": "阴阳合同：合同与发票金额背离（待核）",
        "tax_type": "增值税",
        "signals": [
            "阴阳合同",
            "合同金额与发票",
            "备案合同",
            "实际合同",
            "两份合同"
        ],
        "decl_keywords": [],
        "needs": [
            "合同原件",
            "发票明细",
            "补充协议",
            "资金流水",
            "业务实质说明"
        ],
        "method": "检索存在两份金额不一致的合同、或合同金额与开票金额明显背离 → 实际收付与备案/开票口径不符 → 命中即置疑核查合同真实性",
        "policy_ref": "《中华人民共和国税收征收管理法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-001"
    },
    {
        "redline_id": "RL-VAT-022",
        "topic": "三流不一致：票/货/款背离（待核）",
        "tax_type": "增值税",
        "signals": [
            "三流不一致",
            "票货款不一致",
            "货物流与资金流",
            "开票对象与付款方不符",
            "收取货款方不一致"
        ],
        "decl_keywords": [],
        "needs": [
            "进销项发票明细",
            "出入库单/物流单据",
            "银行流水",
            "购销合同"
        ],
        "method": "比对发票流（开受票方）、货物流（出入库/物流）、资金流（收付款方）三者 → 出现主体或金额不一致 → 命中即置疑核查交易真实性",
        "policy_ref": "《中华人民共和国发票管理办法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-001"
    },
    {
        "redline_id": "RL-PTY-006",
        "topic": "空壳企业特征：无实质经营（待核）",
        "tax_type": "增值税",
        "signals": [
            "空壳",
            "无实际经营",
            "无经营场所",
            "无人员",
            "注册地异常",
            "一址多户"
        ],
        "decl_keywords": [],
        "needs": [
            "工商登记信息",
            "人员社保记录",
            "经营场所证明",
            "发票明细",
            "银行流水"
        ],
        "method": "检索企业呈「无实际经营/无人员/无场所/一址多户」等特征 → 同时存在大额开票 → 命中即置疑核查经营实质与开票能力",
        "policy_ref": "《中华人民共和国发票管理办法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-001"
    },
    {
        "redline_id": "RL-PTY-007",
        "topic": "开票时间异常：集中/非营业时段（待核）",
        "tax_type": "增值税",
        "signals": [
            "集中开票",
            "开票时间异常",
            "月末集中",
            "跨月开票",
            "顶额开票时间"
        ],
        "decl_keywords": [],
        "needs": [
            "发票明细（含开票时间）",
            "业务发生时间凭证",
            "出入库单",
            "资金流水"
        ],
        "method": "分析开票时间的分布 → 集中于月末/季末、或与业务发生时点明显脱节、或集中在非营业时段 → 命中即置疑核查开票时限合理性",
        "policy_ref": "《中华人民共和国发票管理办法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-001"
    },
    {
        "redline_id": "RL-PTY-008",
        "topic": "善意取得情形识别（处理区分用）",
        "tax_type": "增值税",
        "signals": [
            "善意取得",
            "不知情",
            "真实交易存在",
            "善意"
        ],
        "decl_keywords": [],
        "needs": [
            "购销合同",
            "付款凭证",
            "货物交付凭证",
            "发票原件",
            "受票方主观状态说明"
        ],
        "method": "识别是否具备「真实交易 + 受票方不知情」的善意取得情形 → 命中则**按善意取得口径处理**（进项转出、不加收滞纳金、不予行政处罚），本项**不作风险定性**",
        "policy_ref": "《中华人民共和国发票管理办法》",
        "level": "低风险",
        "score": 1,
        "_batch_id": "BATCH-001"
    },
    {
        "redline_id": "RL-VAT-023",
        "topic": "纳税义务发生时间与开票时点脱节（待核）",
        "tax_type": "增值税",
        "signals": [
            "纳税义务发生时间",
            "先开票未申报",
            "开票时点与纳税义务",
            "延迟确认销项",
            "滞后申报"
        ],
        "decl_keywords": [],
        "needs": [
            "销项发票明细（含开票日期）",
            "销售合同（含收款条款）",
            "银行流水",
            "增值税申报表"
        ],
        "method": "比对纳税义务发生时间（收款/开票/发货）与销项申报期间 → 存在先开具发票或先收款而未在当期申报、或义务时点早于申报期 → 命中即置疑核查确认时点",
        "policy_ref": "《中华人民共和国增值税法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-002"
    },
    {
        "redline_id": "RL-VAT-024",
        "topic": "进销项期间错配：跨期调节（待核）",
        "tax_type": "增值税",
        "signals": [
            "进项跨期",
            "销项跨期",
            "期间错配",
            "跨期调节",
            "进项留抵异常波动"
        ],
        "decl_keywords": [],
        "needs": [
            "各期增值税申报表",
            "进销项发票明细",
            "序时账",
            "银行流水"
        ],
        "method": "比对同笔业务的进项抵扣期间与销项申报期间 → 二者明显错位（如进项提前抵扣、销项滞后申报）或留抵额异常波动 → 命中即置疑核查期间归属",
        "policy_ref": "《中华人民共和国增值税法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-002"
    },
    {
        "redline_id": "RL-VAT-025",
        "topic": "计税方法适用错误：简易与一般混用（待核）",
        "tax_type": "增值税",
        "signals": [
            "简易计税",
            "一般计税",
            "计税方法选错",
            "征收率与税率",
            "计税方式混用"
        ],
        "decl_keywords": [],
        "needs": [
            "增值税申报表",
            "发票明细",
            "业务类型清单",
            "计税方法备案资料"
        ],
        "method": "核对业务类型与所选计税方法 → 适用一般计税的业务按简易计税申报（或反之）、征收率与税率混用 → 命中即置疑核查方法适用",
        "policy_ref": "《中华人民共和国增值税法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-002"
    },
    {
        "redline_id": "RL-VAT-026",
        "topic": "折扣折让退回处理不合规（待核）",
        "tax_type": "增值税",
        "signals": [
            "销售折扣",
            "销售折让",
            "销货退回",
            "折扣额未开在同一张发票",
            "红字冲减"
        ],
        "decl_keywords": [],
        "needs": [
            "发票明细（含红字）",
            "销售合同",
            "退货单/折让协议",
            "增值税申报表"
        ],
        "method": "检索发生折扣、折让或退货的业务 → 折扣额未在同一张发票金额栏注明、或以折扣后金额开票未按规定处理 → 命中即置疑核查销售额计算",
        "policy_ref": "《中华人民共和国增值税法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-002"
    },
    {
        "redline_id": "RL-VAT-027",
        "topic": "预收款与预缴税款处理异常（待核）",
        "tax_type": "增值税",
        "signals": [
            "预收款",
            "预缴增值税",
            "预收账款长期挂账",
            "预售",
            "预缴与申报不符"
        ],
        "decl_keywords": [],
        "needs": [
            "预收账款明细",
            "增值税预缴申报表",
            "销售合同",
            "银行流水",
            "发票明细"
        ],
        "method": "检索预收款科目与预缴申报记录 → 预收款长期挂账未按规定确认纳税义务、或预缴金额与计税依据不符 → 命中即置疑",
        "policy_ref": "《中华人民共和国增值税法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-002"
    },
    {
        "redline_id": "RL-VAT-028",
        "topic": "零税率/免税适用合规性存疑（待核）",
        "tax_type": "增值税",
        "signals": [
            "零税率",
            "免税申报",
            "跨境应税行为",
            "出口免税",
            "优惠备案缺失"
        ],
        "decl_keywords": [],
        "needs": [
            "增值税申报表（免税/零税率栏）",
            "业务合同",
            "跨境业务凭证",
            "优惠备案资料"
        ],
        "method": "核对享受零税率或免税的业务 → 业务实质是否落入法定范围、是否已按规定备案与留存备查 → 命中即置疑核查适用条件",
        "policy_ref": "《中华人民共和国增值税法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-002"
    },
    {
        "redline_id": "RL-CIT-011",
        "topic": "收入确认时点与权责发生制不符（待核）",
        "tax_type": "企业所得税",
        "signals": [
            "收入确认时点",
            "权责发生制",
            "跨年确认收入",
            "预收长期挂账",
            "延迟确认收入"
        ],
        "decl_keywords": [],
        "needs": [
            "利润表",
            "主营业务收入明细账",
            "销售合同",
            "发货单",
            "企业所得税申报表"
        ],
        "method": "比对收入确认时点与权责发生制要求 → 已满足确认条件仍挂预收/应付，或跨年调节收入 → 命中即置疑核查确认期间",
        "policy_ref": "《中华人民共和国企业所得税法实施条例》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-003"
    },
    {
        "redline_id": "RL-CIT-012",
        "topic": "成本费用跨期列支（待核）",
        "tax_type": "企业所得税",
        "signals": [
            "跨期列支",
            "费用跨年",
            "以前年度费用",
            "预提费用",
            "期间费用归属错误"
        ],
        "decl_keywords": [],
        "needs": [
            "费用明细账",
            "记账凭证",
            "发票取得时间",
            "企业所得税申报表"
        ],
        "method": "核对费用发生期间与列支期间 → 将属于以前或以后年度的费用在本期扣除（或反之）、大额预提无实际发生 → 命中即置疑",
        "policy_ref": "《中华人民共和国企业所得税法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-003"
    },
    {
        "redline_id": "RL-CIT-013",
        "topic": "资产损失未按规定申报即扣除（待核）",
        "tax_type": "企业所得税",
        "signals": [
            "资产损失",
            "坏账损失",
            "存货报废",
            "盘亏损失",
            "清单申报",
            "专项申报"
        ],
        "decl_keywords": [],
        "needs": [
            "资产损失清单",
            "专项申报资料",
            "报废/毁损证明",
            "责任认定与赔偿说明",
            "企业所得税申报表"
        ],
        "method": "检索资产损失扣除项 → 未按规定区分清单申报与专项申报、或缺少损失确认的法定证据（技术鉴定、责任认定、法律文书）→ 命中即置疑",
        "policy_ref": "《中华人民共和国企业所得税法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-003"
    },
    {
        "redline_id": "RL-CIT-014",
        "topic": "关联方利息支出超债资比未调整（待核）",
        "tax_type": "企业所得税",
        "signals": [
            "关联方利息",
            "债资比",
            "关联借款",
            "利息扣除限额",
            "资本弱化"
        ],
        "decl_keywords": [],
        "needs": [
            "关联方借款合同",
            "财务费用明细账",
            "权益性投资金额",
            "企业所得税申报表",
            "关联业务往来报告表"
        ],
        "method": "计算关联方债权性投资与权益性投资比例 → 超过法定比例部分的利息支出是否作纳税调整 → 命中即置疑核查调整情况",
        "policy_ref": "《中华人民共和国企业所得税法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-003"
    },
    {
        "redline_id": "RL-CIT-015",
        "topic": "不征税收入对应支出重复扣除（待核）",
        "tax_type": "企业所得税",
        "signals": [
            "不征税收入",
            "财政性资金",
            "专项用途",
            "对应支出",
            "重复扣除"
        ],
        "decl_keywords": [],
        "needs": [
            "财政拨款文件",
            "资金使用台账",
            "费用明细账",
            "企业所得税申报表"
        ],
        "method": "核对作为不征税收入处理的财政性资金 → 其用于支出所形成的费用或资产折旧是否又作了税前扣除 → 命中即置疑（不征税收入对应支出不得扣除）",
        "policy_ref": "《中华人民共和国企业所得税法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-003"
    },
    {
        "redline_id": "RL-CIT-016",
        "topic": "亏损弥补期限或结转异常（待核）",
        "tax_type": "企业所得税",
        "signals": [
            "弥补亏损",
            "亏损结转",
            "以前年度亏损",
            "亏损弥补超期",
            "亏损额异常"
        ],
        "decl_keywords": [],
        "needs": [
            "历年企业所得税申报表",
            "亏损弥补明细表",
            "审计报告",
            "账簿凭证"
        ],
        "method": "核对历年亏损额与本年弥补额 → 超过法定弥补期限仍弥补、或弥补额大于实际可弥补亏损、或亏损额与账簿记录不符 → 命中即置疑",
        "policy_ref": "《中华人民共和国企业所得税法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-003"
    },
    {
        "redline_id": "RL-PAY-007",
        "topic": "全年一次性奖金计税方式适用错误（待核）",
        "tax_type": "个人所得税",
        "signals": [
            "全年一次性奖金",
            "年终奖",
            "单独计税",
            "合并计税",
            "奖金计税方式"
        ],
        "decl_keywords": [],
        "needs": [
            "工资表（含奖金）",
            "个税申报表",
            "奖金发放凭证",
            "任职受雇资料"
        ],
        "method": "核对全年一次性奖金的计税方式选择与适用条件 → 同一纳税年度内多次使用单独计税、或不符合适用条件仍按优惠政策计算 → 命中即置疑核查计税方式",
        "policy_ref": "《中华人民共和国个人所得税法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-004"
    },
    {
        "redline_id": "RL-PAY-008",
        "topic": "劳务报酬预扣预缴计算错误（待核）",
        "tax_type": "个人所得税",
        "signals": [
            "劳务报酬",
            "预扣预缴",
            "减除费用",
            "预扣率",
            "劳务费个税"
        ],
        "decl_keywords": [],
        "needs": [
            "劳务费支付明细",
            "个税申报表",
            "劳务合同",
            "付款凭证"
        ],
        "method": "核对劳务报酬所得的费用减除额与预扣率适用 → 未按次减除费用、预扣率适用错误（三档超额累进）、或与工资薪金混算 → 命中即置疑",
        "policy_ref": "《中华人民共和国个人所得税法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-004"
    },
    {
        "redline_id": "RL-PAY-009",
        "topic": "股东分红未按规定扣缴个税（待核）",
        "tax_type": "个人所得税",
        "signals": [
            "股东分红",
            "利润分配",
            "股息红利",
            "应付股利",
            "分利"
        ],
        "decl_keywords": [],
        "needs": [
            "利润分配决议",
            "应付股利明细账",
            "个税申报表",
            "银行流水",
            "股东名册"
        ],
        "method": "检索利润分配/应付股利发生额 → 是否按「利息、股息、红利所得」20% 代扣代缴个税 → 命中即置疑核查扣缴义务履行",
        "policy_ref": "《中华人民共和国个人所得税法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-004"
    },
    {
        "redline_id": "RL-PAY-010",
        "topic": "非居民个人所得扣缴异常（待核）",
        "tax_type": "个人所得税",
        "signals": [
            "非居民个人",
            "外籍人员",
            "非居民扣缴",
            "税收协定待遇",
            "无住所个人"
        ],
        "decl_keywords": [],
        "needs": [
            "外籍/非居民人员名册",
            "个税申报表",
            "任职受雇资料",
            "在华停留天数记录",
            "协定待遇备案"
        ],
        "method": "核对非居民个人所得的计税方式与协定待遇适用 → 居民/非居民身份判定、停留天数计算、协定待遇享受是否合规 → 命中即置疑",
        "policy_ref": "《中华人民共和国个人所得税法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-004"
    },
    {
        "redline_id": "RL-PAY-011",
        "topic": "专项附加扣除与资料一致性存疑（待核）",
        "tax_type": "个人所得税",
        "signals": [
            "专项附加扣除",
            "子女教育",
            "住房贷款利息",
            "赡养老人",
            "继续教育",
            "大病医疗"
        ],
        "decl_keywords": [],
        "needs": [
            "专项附加扣除申报明细",
            "相关证明材料",
            "工资表",
            "个税申报表"
        ],
        "method": "核对专项附加扣除申报项与留存备查资料 → 扣除标准或享受条件与申报不符、多个单位重复扣除、或缺少佐证材料 → 命中即置疑",
        "policy_ref": "《中华人民共和国个人所得税法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-004"
    },
    {
        "redline_id": "RL-OTH-012",
        "topic": "逾期申报或漏报税种（待核）",
        "tax_type": "其他税费",
        "signals": [
            "逾期申报",
            "漏申报",
            "未申报",
            "申报期限",
            "申报表缺失",
            "零申报异常"
        ],
        "decl_keywords": [],
        "needs": [
            "各税种申报表台账",
            "纳税申报记录",
            "业务类型清单",
            "发票明细"
        ],
        "method": "比对账簿反映的应税业务与已申报税种 → 存在应申报未申报、逾期申报或长期零申报而业务量不符 → 命中即置疑",
        "policy_ref": "《中华人民共和国税收征收管理法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-005"
    },
    {
        "redline_id": "RL-OTH-013",
        "topic": "缴纳与申报金额不一致（待核）",
        "tax_type": "其他税费",
        "signals": [
            "缴款与申报不符",
            "欠缴税款",
            "税款未缴",
            "缴款书金额",
            "申报未缴"
        ],
        "decl_keywords": [],
        "needs": [
            "各期申报表",
            "完税凭证/缴款书",
            "银行流水",
            "税款缴纳台账"
        ],
        "method": "比对申报应纳税额与实际缴纳入库金额 → 存在差额且无合理原因（欠缴、少缴、缓缴未批） → 命中即置疑",
        "policy_ref": "《中华人民共和国税收征收管理法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-005"
    },
    {
        "redline_id": "RL-OTH-014",
        "topic": "税务与工商登记信息不一致（待核）",
        "tax_type": "其他税费",
        "signals": [
            "登记信息不一致",
            "变更未备案",
            "经营范围变更",
            "注册地址变更",
            "法定代表人变更"
        ],
        "decl_keywords": [],
        "needs": [
            "工商登记信息",
            "税务登记信息",
            "变更记录",
            "营业执照"
        ],
        "method": "比对税务登记信息与工商登记信息 → 名称、地址、法定代表人、经营范围等发生变更未同步 → 命中即置疑核查登记一致性",
        "policy_ref": "《中华人民共和国税收征收管理法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-005"
    },
    {
        "redline_id": "RL-OTH-015",
        "topic": "账簿凭证设置与保管不合规（待核）",
        "tax_type": "其他税费",
        "signals": [
            "账簿不全",
            "凭证缺失",
            "未设账簿",
            "原始凭证不合规",
            "账簿保管期限"
        ],
        "decl_keywords": [],
        "needs": [
            "账簿清单",
            "记账凭证",
            "原始凭证",
            "会计制度或核算办法"
        ],
        "method": "核查账簿设置与凭证完整性 → 未按规定设置账簿、记账凭证缺少原始凭证支撑、或保管期限不足 → 命中即置疑",
        "policy_ref": "《中华人民共和国税收征收管理法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-005"
    },
    {
        "redline_id": "RL-OTH-016",
        "topic": "发票领用存与经营规模不匹配（待核）",
        "tax_type": "其他税费",
        "signals": [
            "发票领用存",
            "发票结存",
            "大量领用",
            "发票流失",
            "发票存量异常"
        ],
        "decl_keywords": [],
        "needs": [
            "发票领用存台账",
            "开票明细",
            "纳税信用等级",
            "营业收入"
        ],
        "method": "核对发票领用、开具与结存记录 → 领用量或结存量与经营规模、纳税信用等级明显不匹配，或存在未开具发票流失风险 → 命中即置疑",
        "policy_ref": "《中华人民共和国发票管理办法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-005"
    },
    {
        "redline_id": "RL-SPT-022",
        "topic": "研发费用归集范围错误（待核）",
        "tax_type": "企业所得税",
        "signals": [
            "研发费用",
            "加计扣除",
            "归集范围",
            "研发支出",
            "研发项目"
        ],
        "decl_keywords": [],
        "needs": [
            "研发项目立项决议",
            "研发费用辅助账",
            "研发人员名单",
            "费用明细账",
            "企业所得税申报表"
        ],
        "method": "核对归集入研发费用的支出 → 是否属于允许加计扣除的范围（如行政办公、常规升级、市场调研等不应计入） → 命中即置疑核查归集口径",
        "policy_ref": "《中华人民共和国企业所得税法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-006"
    },
    {
        "redline_id": "RL-SPT-023",
        "topic": "研发费用辅助账未按规定设置（待核）",
        "tax_type": "企业所得税",
        "signals": [
            "辅助账",
            "研发费用辅助账",
            "研发支出辅助账",
            "未设辅助账",
            "辅助账与总账不符"
        ],
        "decl_keywords": [],
        "needs": [
            "研发费用辅助账",
            "总账与明细账",
            "研发项目清单",
            "工时分配记录"
        ],
        "method": "核查是否按研发项目设置辅助账并正确归集 → 未设辅助账、辅助账与总账不符、或多项目费用未合理分摊 → 命中即置疑",
        "policy_ref": "《中华人民共和国企业所得税法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-006"
    },
    {
        "redline_id": "RL-SPT-024",
        "topic": "委托研发加计扣除基数或比例错误（待核）",
        "tax_type": "企业所得税",
        "signals": [
            "委托研发",
            "委托开发",
            "合作研发",
            "委托境外研发",
            "委托研发扣除比例"
        ],
        "decl_keywords": [],
        "needs": [
            "委托研发合同",
            "技术合同登记证明",
            "付款凭证",
            "受托方费用明细",
            "企业所得税申报表"
        ],
        "method": "核对委托研发的加计扣除基数 → 委托境内研发按实际发生额 80% 计入、委托境外研发另有上限；基数或比例适用错误 → 命中即置疑",
        "policy_ref": "《中华人民共和国企业所得税法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-006"
    },
    {
        "redline_id": "RL-SPT-025",
        "topic": "不适行业/活动未剔除（待核）",
        "tax_type": "企业所得税",
        "signals": [
            "不适用行业",
            "负面清单",
            "禁止加计",
            "烟草制造",
            "娱乐业",
            "批发零售"
        ],
        "decl_keywords": [],
        "needs": [
            "营业执照与经营范围",
            "主营业务收入构成",
            "研发项目清单",
            "企业所得税申报表"
        ],
        "method": "核对所属行业是否属不适用加计扣除的负面清单（烟草制造、住宿餐饮、批发零售、房地产、租赁商务服务、娱乐业等）→ 属则整体不得加计 → 命中即置疑",
        "policy_ref": "《中华人民共和国企业所得税法》",
        "level": "低风险",
        "score": 3,
        "_batch_id": "BATCH-006"
    }
]
)
SPECS.extend(_BATCH_SPECS)
# ═══ END BATCH_SPECS_LOADER ═══

