# -*- coding: utf-8 -*-
"""真实业务场景驱动的方法论计划器。

该模块只生成核验任务、资料缺口和观察信号，不生成违法定性、税额、
处罚或立案意见。场景合同的完整正文由受保护的只读接口提供。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ASSETS = {
    "A": {
        "asset": "agriculture_scenario_contracts",
        "path": _PROJECT_ROOT / "static" / "agriculture_scenario_contracts.json",
        "terms": ("农、林、牧、渔业", "农林牧渔", "农业", "种植", "养殖", "林业", "渔业", "农民专业合作社"),
    },
    "B": {
        "asset": "mining_scenario_contracts",
        "path": _PROJECT_ROOT / "static" / "mining_scenario_contracts.json",
        "terms": ("采矿业", "矿业", "矿山", "煤矿", "金属矿", "非金属矿", "油气开采", "矿产资源开采"),
    },
    "C": {
        "asset": "manufacturing_scenario_contracts",
        "path": _PROJECT_ROOT / "static" / "manufacturing_scenario_contracts.json",
        "terms": ("制造", "生产企业", "加工企业", "工厂"),
    },
    "E": {
        "asset": "construction_scenario_contracts",
        "path": _PROJECT_ROOT / "static" / "construction_scenario_contracts.json",
        "terms": ("建筑", "施工", "工程承包", "建设工程"),
    },
    "F": {
        "asset": "wholesale_retail_scenario_contracts",
        "path": _PROJECT_ROOT / "static" / "wholesale_retail_scenario_contracts.json",
        "terms": ("批发", "零售", "商贸", "贸易", "商超", "电商零售"),
    },
    "OVERLAY-PLATFORM": {
        "asset": "platform_scenario_contracts",
        "path": _PROJECT_ROOT / "static" / "platform_scenario_contracts.json",
        "terms": ("互联网平台", "网络平台", "平台经济", "网络直播", "灵活用工平台", "网络货运平台", "内容平台", "数字平台"),
    },
    "K": {
        "asset": "real_estate_scenario_contracts",
        "path": _PROJECT_ROOT / "static" / "real_estate_scenario_contracts.json",
        "terms": ("房地产", "房产开发", "地产开发", "商品房开发"),
    },
}


FILE_TYPE_SOURCE_FAMILIES = {
    "inventory": {"生产存货", "仓储物流", "工程材料", "商品库存"},
    "sales_invoice": {"发票申报", "销售履约", "渠道订单"},
    "purchase_invoice": {"发票申报", "采购成本", "工程材料", "商品库存"},
    "invoice": {"发票申报"},
    "invoice_universal": {"发票申报"},
    "input_vat_deduction": {"发票申报"},
    "tax_return": {"税费申报"},
    "tax_declaration": {"税费申报"},
    "bank": {"资金结算", "支付结算"},
    "bank_statement": {"资金结算", "支付结算"},
    "bank_transaction": {"资金结算", "支付结算"},
    "voucher": {"会计核算"},
    "trial_balance": {"会计核算"},
    "financial": {"会计核算"},
    "contract": {"合同权利义务"},
    "related_party": {"关联关系"},
    "customs": {"海关出口"},
    "export": {"海关出口"},
    "salary": {"人员薪酬"},
    "payroll": {"人员薪酬"},
    "social_security": {"人员薪酬"},
    "generic_data": {"其他业务资料"},
}


SCENE_SOURCE_GATES = {
    "MIN-01": [
        {"name": "矿业权许可与空间", "any": ["矿业权许可"]},
        {"name": "储量采区与实际开采", "any": ["采矿生产"]},
        {"name": "计量库存与申报", "any": ["矿产品计量", "税费申报", "会计核算"]},
    ],
    "MIN-02": [
        {"name": "采出原矿与堆场", "any": ["采矿生产", "矿产品计量"]},
        {"name": "选矿化验与精尾矿", "any": ["选矿加工"]},
        {"name": "库存去向与税会", "any": ["矿产品计量", "会计核算", "税费申报"]},
    ],
    "MIN-03": [
        {"name": "矿种产品和来源", "any": ["矿业权许可", "采矿生产", "选矿加工"]},
        {"name": "销售自用和扣减", "any": ["矿产品计量", "销售履约", "合同权利义务"]},
        {"name": "资源税申报", "any": ["资源税申报", "税费申报"]},
    ],
    "MIN-04": [
        {"name": "外包合同与承载", "any": ["矿山外包", "合同权利义务"]},
        {"name": "作业工程量与验收", "any": ["采矿生产", "矿山外包"]},
        {"name": "结算票款与成本", "any": ["资金结算", "发票申报", "会计核算"]},
    ],
    "MIN-05": [
        {"name": "质量化验", "any": ["选矿加工", "矿产品计量"]},
        {"name": "合同公式和关联关系", "any": ["合同权利义务", "关联关系"]},
        {"name": "结算资金与申报", "any": ["资金结算", "发票申报", "资源税申报"]},
    ],
    "MIN-06": [
        {"name": "权利事件与出让合同", "any": ["矿业权许可", "合同权利义务"]},
        {"name": "费源和缴费", "any": ["资源税申报", "税费申报", "资金结算"]},
        {"name": "勘查开发与资产", "any": ["采矿生产", "会计核算"]},
    ],
    "MIN-07": [
        {"name": "安全修复义务", "any": ["矿山安全环保", "矿业权许可"]},
        {"name": "工程实施和验收", "any": ["矿山安全环保", "矿山外包"]},
        {"name": "专项资金和账务", "any": ["资金结算", "发票申报", "会计核算"]},
    ],
    "MIN-08": [
        {"name": "过磅装运和轨迹", "any": ["矿产品计量", "仓储物流"]},
        {"name": "港口海关和签收", "any": ["仓储物流", "海关出口", "销售履约"]},
        {"name": "结算票款和税期", "any": ["资金结算", "发票申报", "资源税申报"]},
    ],
    "AGR-01": [
        {"name": "经营单元与权利", "any": ["农业经营权", "农业生产"]},
        {"name": "投入生长与收获", "any": ["农业生产", "生物资产"]},
        {"name": "销售税会", "any": ["仓储物流", "资金结算", "发票申报", "会计核算"]},
    ],
    "AGR-02": [
        {"name": "自产与成员来源", "any": ["农业生产", "合作社成员"]},
        {"name": "外购与加工库存", "any": ["农产品收购", "农产品加工", "商品库存"]},
        {"name": "优惠和分别核算", "any": ["税费申报", "会计核算", "发票申报"]},
    ],
    "AGR-03": [
        {"name": "生产者和收购", "any": ["农产品收购", "合作社成员"]},
        {"name": "交付付款与使用", "any": ["仓储物流", "资金结算", "农产品加工"]},
        {"name": "凭证与抵扣", "any": ["发票申报", "税费申报"]},
    ],
    "AGR-04": [
        {"name": "合作社成员治理", "any": ["合作社成员"]},
        {"name": "订单交付结算", "any": ["农业生产", "农产品收购", "资金结算"]},
        {"name": "成员账户和税会", "any": ["合作社成员", "会计核算", "税费申报"]},
    ],
    "AGR-05": [
        {"name": "经营权和用途", "any": ["农业经营权"]},
        {"name": "农业设施和生产", "any": ["农业生产", "合同权利义务"]},
        {"name": "租金投入和税会", "any": ["资金结算", "会计核算", "税费申报"]},
    ],
    "AGR-06": [
        {"name": "资金文件和项目", "any": ["农业补助保险", "合同权利义务"]},
        {"name": "收储交付或损失", "any": ["农业生产", "仓储物流", "生物资产"]},
        {"name": "资金用途和税会", "any": ["资金结算", "会计核算", "税费申报"]},
    ],
    "AGR-07": [
        {"name": "生物资产群组", "any": ["生物资产"]},
        {"name": "生长死亡和处置", "any": ["农业生产", "生物资产"]},
        {"name": "销售赔款和税会", "any": ["农业补助保险", "资金结算", "会计核算"]},
    ],
    "AGR-08": [
        {"name": "原料来源和加工", "any": ["农产品收购", "农产品加工"]},
        {"name": "质检冷链和去向", "any": ["农产品加工", "仓储物流", "商品库存"]},
        {"name": "优惠进项和申报", "any": ["发票申报", "税费申报", "会计核算"]},
    ],
    "MFG-01": [
        {"name": "生产与库存", "any": ["生产存货"]},
        {"name": "销售履约", "any": ["销售履约", "合同权利义务"]},
        {"name": "发票或资金", "any": ["发票申报", "资金结算"]},
        {"name": "会计核算", "any": ["会计核算"]},
    ],
    "MFG-02": [
        {"name": "委外合同", "any": ["合同权利义务"]},
        {"name": "委外收发与成果", "any": ["生产存货", "仓储物流"]},
        {"name": "加工结算", "any": ["发票申报", "资金结算"]},
    ],
    "MFG-03": [
        {"name": "生产工艺与物料", "any": ["生产存货"]},
        {"name": "称重仓储与处置", "any": ["仓储物流", "其他业务资料"]},
        {"name": "处置价款", "any": ["发票申报", "资金结算"]},
    ],
    "MFG-04": [
        {"name": "双端收发存", "any": ["生产存货", "仓储物流"]},
        {"name": "货权或运输", "any": ["合同权利义务", "其他业务资料"]},
        {"name": "期末会计", "any": ["会计核算"]},
    ],
    "MFG-05": [
        {"name": "研发项目与活动", "any": ["合同权利义务", "其他业务资料"]},
        {"name": "人员或直接投入", "any": ["人员薪酬", "生产存货"]},
        {"name": "辅助账与申报", "any": ["会计核算", "发票申报"]},
    ],
    "MFG-06": [
        {"name": "设备取得", "any": ["合同权利义务", "采购成本", "发票申报"]},
        {"name": "投用与生产", "any": ["生产存货", "其他业务资料"]},
        {"name": "资产会计税务", "any": ["会计核算"]},
    ],
    "MFG-07": [
        {"name": "关联关系和交易", "any": ["关联关系", "合同权利义务"]},
        {"name": "实际功能资产风险", "any": ["生产存货", "人员薪酬", "其他业务资料"]},
        {"name": "分部财务和定价", "any": ["会计核算", "发票申报"]},
    ],
    "MFG-08": [
        {"name": "出口订单与货物", "any": ["合同权利义务", "生产存货"]},
        {"name": "报关物流", "any": ["海关出口", "其他业务资料"]},
        {"name": "收汇和申报", "any": ["资金结算", "发票申报"]},
    ],
    "CON-01": [
        {"name": "项目与工程地点", "any": ["工程项目", "合同权利义务"]},
        {"name": "预缴与申报", "any": ["税费申报", "发票申报"]},
        {"name": "项目会计", "any": ["会计核算"]},
    ],
    "CON-02": [
        {"name": "合同与进度结算", "any": ["合同权利义务", "工程项目"]},
        {"name": "开票与收款", "any": ["发票申报", "资金结算"]},
        {"name": "收入核算", "any": ["会计核算"]},
    ],
    "CON-03": [
        {"name": "分包合同与工程量", "any": ["合同权利义务", "工程项目"]},
        {"name": "分包票款", "any": ["发票申报", "资金结算"]},
        {"name": "成本核算", "any": ["会计核算", "采购成本"]},
    ],
    "CON-04": [
        {"name": "项目与计税选择", "any": ["工程项目", "合同权利义务"]},
        {"name": "申报与预缴", "any": ["税费申报", "发票申报"]},
        {"name": "进项与会计划分", "any": ["采购成本", "会计核算"]},
    ],
    "CON-05": [
        {"name": "材料收发存", "any": ["工程材料", "生产存货", "仓储物流"]},
        {"name": "工程量与施工部位", "any": ["工程项目"]},
        {"name": "材料计价核算", "any": ["会计核算", "发票申报"]},
    ],
    "CON-06": [
        {"name": "实名与考勤", "any": ["人员薪酬", "工程项目"]},
        {"name": "工资与资金", "any": ["人员薪酬", "资金结算"]},
        {"name": "扣缴与社保", "any": ["税费申报", "人员薪酬"]},
    ],
    "CON-07": [
        {"name": "项目成本与分配", "any": ["会计核算", "工程项目"]},
        {"name": "合同采购与分包", "any": ["合同权利义务", "采购成本"]},
        {"name": "暂估与票款", "any": ["发票申报", "资金结算"]},
    ],
    "CON-08": [
        {"name": "变更索赔与确认", "any": ["合同权利义务", "工程项目"]},
        {"name": "开票与资金", "any": ["发票申报", "资金结算"]},
        {"name": "收入成本与申报", "any": ["会计核算", "税费申报"]},
    ],
    "REA-01": [
        {"name": "土地项目与许可", "any": ["房地产项目", "合同权利义务"]},
        {"name": "房源规划与清算", "any": ["房源交易", "税费申报"]},
        {"name": "成本会计", "any": ["会计核算", "开发成本"]},
    ],
    "REA-02": [
        {"name": "房源认购与合同", "any": ["房源交易", "合同权利义务"]},
        {"name": "收退款与按揭", "any": ["资金结算"]},
        {"name": "预缴预征申报", "any": ["税费申报", "发票申报"]},
    ],
    "REA-03": [
        {"name": "完工与交付", "any": ["房地产项目", "房源交易"]},
        {"name": "开票与申报", "any": ["发票申报", "税费申报"]},
        {"name": "收入成本核算", "any": ["会计核算", "开发成本"]},
    ],
    "REA-04": [
        {"name": "土地价款与支付", "any": ["房地产项目", "资金结算"]},
        {"name": "规划可售面积", "any": ["房源交易"]},
        {"name": "扣除与申报", "any": ["税费申报", "会计核算"]},
    ],
    "REA-05": [
        {"name": "清算房源与产权", "any": ["房源交易", "房地产项目"]},
        {"name": "收入收款与发票", "any": ["资金结算", "发票申报"]},
        {"name": "清算和尾盘申报", "any": ["税费申报"]},
    ],
    "REA-06": [
        {"name": "成本对象与工程", "any": ["开发成本", "房地产项目"]},
        {"name": "合同票款与履约", "any": ["合同权利义务", "发票申报", "资金结算"]},
        {"name": "分配与税会", "any": ["会计核算", "税费申报"]},
    ],
    "REA-07": [
        {"name": "附属资产权属", "any": ["房源交易", "房地产项目"]},
        {"name": "合同与收款主体", "any": ["合同权利义务", "资金结算"]},
        {"name": "税会处理", "any": ["会计核算", "税费申报", "发票申报"]},
    ],
    "REA-08": [
        {"name": "客户关联关系", "any": ["关联关系", "房源交易"]},
        {"name": "价格合同与审批", "any": ["合同权利义务", "房源交易"]},
        {"name": "完整对价与税会", "any": ["资金结算", "会计核算", "税费申报"]},
    ],
    "RET-01": [
        {"name": "商品采购与库存", "any": ["商品库存", "采购成本", "仓储物流"]},
        {"name": "订单出库与退货", "any": ["渠道订单", "销售履约", "售后退款"]},
        {"name": "会计发票申报", "any": ["会计核算", "发票申报", "税费申报"]},
    ],
    "RET-02": [
        {"name": "全渠道订单", "any": ["渠道订单"]},
        {"name": "支付履约与结算", "any": ["支付结算", "销售履约", "平台结算"]},
        {"name": "开票税会", "any": ["发票申报", "会计核算", "税费申报"]},
    ],
    "RET-03": [
        {"name": "原订单与售后", "any": ["渠道订单", "售后退款"]},
        {"name": "退货退款", "any": ["销售履约", "支付结算", "商品库存"]},
        {"name": "蓝红票和税会", "any": ["发票申报", "会计核算", "税费申报"]},
    ],
    "RET-04": [
        {"name": "商业协议和条件", "any": ["商业政策", "合同权利义务"]},
        {"name": "履约及结算", "any": ["渠道订单", "平台结算", "支付结算"]},
        {"name": "票据和税会", "any": ["发票申报", "会计核算", "税费申报"]},
    ],
    "RET-05": [
        {"name": "代销联营合同", "any": ["代销联营", "合同权利义务"]},
        {"name": "货权订单和结算", "any": ["商品库存", "渠道订单", "平台结算"]},
        {"name": "角色和税会", "any": ["会计核算", "发票申报", "税费申报"]},
    ],
    "RET-06": [
        {"name": "会员钱包和卡券", "any": ["会员权益"]},
        {"name": "充值核销退款", "any": ["支付结算", "渠道订单", "售后退款"]},
        {"name": "余额和税会", "any": ["会计核算", "发票申报", "税费申报"]},
    ],
    "RET-07": [
        {"name": "门店订单和班次", "any": ["渠道订单", "销售履约"]},
        {"name": "支付商户和账户", "any": ["支付结算", "平台结算"]},
        {"name": "收入发票申报", "any": ["会计核算", "发票申报", "税费申报"]},
    ],
    "PLT-01": [
        {"name": "平台入口与运营", "any": ["平台基础信息", "合同权利义务"]},
        {"name": "系统权限与结算", "any": ["平台系统日志", "支付结算"]},
        {"name": "涉税信息报送", "any": ["平台涉税报送", "税费申报"]},
    ],
    "PLT-02": [
        {"name": "账户与实名历史", "any": ["平台账户身份"]},
        {"name": "合同运营与收款", "any": ["合同权利义务", "支付结算"]},
        {"name": "身份报送与安全", "any": ["平台涉税报送", "平台系统日志"]},
    ],
    "PLT-03": [
        {"name": "平台订单售后", "any": ["平台订单", "售后退款"]},
        {"name": "分账结算", "any": ["平台结算", "支付结算"]},
        {"name": "收入报送税会", "any": ["平台涉税报送", "会计核算", "税费申报"]},
    ],
    "PLT-04": [
        {"name": "业务线和协议", "any": ["平台基础信息", "合同权利义务"]},
        {"name": "履约售后分账", "any": ["平台订单", "售后退款", "平台结算"]},
        {"name": "角色税会", "any": ["会计核算", "发票申报", "税费申报"]},
    ],
    "PLT-05": [
        {"name": "直播内容钱包", "any": ["直播内容", "虚拟权益"]},
        {"name": "退款和多方分成", "any": ["售后退款", "平台结算", "支付结算"]},
        {"name": "直播报送扣缴", "any": ["平台涉税报送", "税费申报", "人员薪酬"]},
    ],
    "PLT-06": [
        {"name": "任务人员成果", "any": ["灵活用工任务", "人员薪酬"]},
        {"name": "验收和票款", "any": ["合同权利义务", "支付结算", "发票申报"]},
        {"name": "扣缴代办报送", "any": ["平台涉税报送", "税费申报"]},
    ],
    "PLT-07": [
        {"name": "托运承运订单", "any": ["网络货运", "合同权利义务"]},
        {"name": "车辆司机轨迹", "any": ["网络货运轨迹", "人员薪酬"]},
        {"name": "结算票税报送", "any": ["平台结算", "发票申报", "平台涉税报送"]},
    ],
    "PLT-08": [
        {"name": "境内外主体交易", "any": ["跨境平台", "合同权利义务"]},
        {"name": "地点币种结算", "any": ["跨境履约", "资金结算"]},
        {"name": "跨境报送申报", "any": ["平台涉税报送", "税费申报"]},
    ],
}


SCENE_SIGNAL_TERMS = {
    "MIN-01": ("矿业权", "采矿许可证", "矿区", "储量", "核定产能", "采区"),
    "MIN-02": ("原矿", "精矿", "选矿", "尾矿", "品位", "回收率", "金属量"),
    "MIN-03": ("资源税", "应税矿产品", "原矿选矿", "外购扣减", "运杂费", "衰竭期"),
    "MIN-04": ("采掘外包", "剥离", "井巷", "矿内运输", "台班", "工程量"),
    "MIN-05": ("品位", "化验", "计价公式", "关联销售", "煤炭单价", "精矿结算"),
    "MIN-06": ("矿业权出让收益", "探矿权", "采矿权", "费源", "勘查开发"),
    "MIN-07": ("安全生产费用", "生态修复", "闭坑", "尾矿库", "专项台账", "修复验收"),
    "MIN-08": ("地磅", "过磅", "装运", "车辆轨迹", "港口", "签收", "矿产品吨位"),
    "AGR-01": ("地块", "水域", "种苗", "饲料", "亩产", "投入产出", "收获", "出栏"),
    "AGR-02": ("自产农产品", "成员产品", "外购农产品", "免税销售", "农林牧渔优惠", "分别核算"),
    "AGR-03": ("农产品收购", "收购发票", "农户", "过磅", "核定扣除", "农产品进项"),
    "AGR-04": ("合作社", "成员账户", "订单农业", "经纪人", "盈余返还", "成员交易"),
    "AGR-05": ("土地经营权", "土地流转", "承包地", "农业设施", "大棚", "池塘"),
    "AGR-06": ("财政补贴", "政府收储", "专项资金", "农业保险", "保险赔款", "灾害补助"),
    "AGR-07": ("生物资产", "存栏", "繁育", "转群", "死亡", "扑杀", "采伐"),
    "AGR-08": ("初加工", "深加工", "冷链", "含水率", "自然失重", "边副产品"),
    "MFG-01": ("投入产出", "BOM", "有进无销", "有销无进", "库存", "完工", "发货"),
    "MFG-02": ("委托加工", "委外", "加工费", "来料加工", "受托加工"),
    "MFG-03": ("废料", "副产品", "边角料", "危废", "其他业务收入"),
    "MFG-04": ("调拨", "在途", "负库存", "盘点", "期末截止"),
    "MFG-05": ("研发", "加计扣除", "辅助账", "研发人员", "研发材料"),
    "MFG-06": ("固定资产", "设备", "转固", "折旧", "试生产", "政府补助"),
    "MFG-07": ("关联交易", "转让定价", "委托生产", "功能风险", "同期资料"),
    "MFG-08": ("出口", "报关", "收汇", "退税", "免抵退"),
    "CON-01": ("异地项目", "跨地区", "预缴", "项目台账", "工程地点", "抵减"),
    "CON-02": ("预收", "进度款", "结算", "产值", "收入确认", "质保金"),
    "CON-03": ("分包", "工程量", "扣除", "劳务班组", "分包款", "合法凭证"),
    "CON-04": ("简易计税", "一般计税", "甲供", "老项目", "进项划分", "计税方法"),
    "CON-05": ("甲供材", "领料", "退料", "调拨", "材料损耗", "工程物资"),
    "CON-06": ("实名制", "考勤", "工资专户", "班组", "代扣代缴", "农民工"),
    "CON-07": ("暂估", "冲回", "跨项目", "成本分配", "机械费", "项目成本"),
    "CON-08": ("合同变更", "签证", "索赔", "奖励", "停工补偿", "质保金"),
    "REA-01": ("房地产项目", "分期", "楼栋", "业态", "清算单位", "成本对象"),
    "REA-02": ("认购", "预售", "首付", "按揭", "监管账户", "预缴", "预征"),
    "REA-03": ("竣工", "交付", "办证", "完工产品", "投入使用", "收入确认"),
    "REA-04": ("土地价款", "土地出让金", "可售面积", "销售面积", "销售额扣除"),
    "REA-05": ("土地增值税清算", "清算收入", "尾盘", "视同销售", "抵债", "安置房"),
    "REA-06": ("开发成本", "成本对象", "公共配套", "分摊", "暂估", "造价"),
    "REA-07": ("车位", "储藏室", "配套", "代收费用", "人防", "物业收款"),
    "REA-08": ("关联销售", "内部认购", "员工购房", "特殊价格", "返佣", "低价售房"),
    "RET-01": ("进销存", "SKU", "采购入库", "仓店", "调拨", "盘点", "负库存"),
    "RET-02": ("订单", "支付", "签收", "平台结算", "商户号", "渠道"),
    "RET-03": ("退货", "退款", "红冲", "红字发票", "重新开票", "销售折让"),
    "RET-04": ("返利", "商业折扣", "促销", "补贴", "陈列费", "渠道服务"),
    "RET-05": ("代销", "联营", "主要责任人", "代理人", "净额", "佣金"),
    "RET-06": ("会员", "储值", "预付卡", "礼券", "积分", "核销"),
    "RET-07": ("现金", "聚合支付", "个人账户", "收款码", "POS", "班次"),
    "PLT-01": ("平台域名", "运营主体", "报送主体", "基本信息报送", "平台备案"),
    "PLT-02": ("平台账户", "实名认证", "经营者身份", "从业人员身份", "收款主体"),
    "PLT-03": ("平台订单", "季度报送", "报送收入", "分账", "平台佣金", "平台服务费"),
    "PLT-04": ("平台自营", "撮合", "主要责任人", "代理人", "总额净额", "平台角色"),
    "PLT-05": ("直播", "主播", "虚拟币", "虚拟礼物", "打赏", "MCN", "创作者"),
    "PLT-06": ("灵活用工", "任务订单", "劳务报酬", "代办申报", "众包", "自由职业者"),
    "PLT-07": ("网络货运", "货运平台", "实际承运人", "司机", "车辆轨迹", "运单"),
    "PLT-08": ("境外平台", "跨境平台", "数字服务", "境外经营者", "外币", "境外收入"),
}


@lru_cache(maxsize=32)
def load_scenario_contracts(industry_code="C"):
    from engine.methodology_catalog import load_reviewed_scenario_contracts

    return load_reviewed_scenario_contracts(str(industry_code or "").upper())


def _resolve_industry_code(industry):
    from engine.methodology_portfolio import resolve_industry_code

    return resolve_industry_code(industry)


def _available_source_families(file_results):
    families = set()
    file_types = set()
    for item in file_results or []:
        if not isinstance(item, dict) or item.get("error"):
            continue
        file_type = str(item.get("type", "unknown") or "unknown").strip().lower()
        file_types.add(file_type)
        families.update(FILE_TYPE_SOURCE_FAMILIES.get(file_type, set()))
        name_text = " ".join(
            str(item.get(key, "") or "") for key in ("file", "original_name", "_header_row")
        )
        if any(term in name_text for term in ("BOM", "工单", "领料", "完工", "生产", "进销存")):
            families.add("生产存货")
        if any(term in name_text for term in ("物流", "运单", "签收", "调拨", "盘点", "称重")):
            families.add("仓储物流")
        if any(term in name_text for term in ("报关", "提运单", "出口退税", "收汇")):
            families.add("海关出口")
        if any(term in name_text for term in ("研发", "立项", "辅助账", "试验")):
            families.add("其他业务资料")
        if any(term in name_text for term in ("项目", "施工", "工程量", "监理", "进度", "结算", "签证", "索赔")):
            families.add("工程项目")
        if any(term in name_text for term in ("材料", "甲供", "领退料", "工程物资")):
            families.add("工程材料")
        if any(term in name_text for term in ("预缴", "申报", "完税", "计税方法", "扣缴")):
            families.add("税费申报")
        if any(term in name_text for term in ("实名", "考勤", "工资", "班组", "社保", "人员")):
            families.add("人员薪酬")
        if any(term in name_text for term in ("合同", "分包", "承包协议", "补充协议")):
            families.add("合同权利义务")
        if any(term in name_text for term in ("采矿许可证", "探矿权", "采矿权", "矿业权", "矿区坐标", "储量报告", "核定产能")):
            families.add("矿业权许可")
        if any(term in name_text for term in ("采区", "采掘", "爆破", "铲装", "原矿", "生产班报", "储量动用")):
            families.add("采矿生产")
        if any(term in name_text for term in ("地磅", "过磅", "称重", "堆场", "装车", "装船", "矿产品签收")):
            families.add("矿产品计量")
        if any(term in name_text for term in ("选矿", "精矿", "尾矿", "品位", "水分", "化验", "回收率", "金属量")):
            families.add("选矿加工")
        if any(term in name_text for term in ("资源税", "应税矿产品", "原矿选矿", "外购扣减", "矿业权出让收益")):
            families.add("资源税申报")
        if any(term in name_text for term in ("外包采掘", "采掘承包", "剥离工程", "井巷工程", "矿内运输", "台班验收")):
            families.add("矿山外包")
        if any(term in name_text for term in ("安全生产费用", "安全费用", "生态修复", "修复方案", "闭坑", "尾矿库", "修复验收")):
            families.add("矿山安全环保")
        if any(term in name_text for term in ("承包地", "土地经营权", "土地流转", "地块", "水域", "林班", "养殖单元", "图斑")):
            families.add("农业经营权")
        if any(term in name_text for term in ("种植", "养殖", "播种", "投苗", "农资", "饲料", "收获", "出栏", "捕捞", "生产日志")):
            families.add("农业生产")
        if any(term in name_text for term in ("农产品收购", "收购发票", "农户交付", "过磅", "收购台账", "农户付款")):
            families.add("农产品收购")
        if any(term in name_text for term in ("合作社", "成员名册", "成员账户", "成员交易", "订单农业", "盈余分配")):
            families.add("合作社成员")
        if any(term in name_text for term in ("农业补贴", "财政资金", "政府收储", "农业保险", "保险赔款", "查勘定损")):
            families.add("农业补助保险")
        if any(term in name_text for term in ("生物资产", "存栏", "繁育", "转群", "死亡淘汰", "无害化", "林木蓄积")):
            families.add("生物资产")
        if any(term in name_text for term in ("初加工", "深加工", "冷库", "冷链", "分选", "屠宰", "含水率", "自然失重")):
            families.add("农产品加工")
        if any(term in name_text for term in ("土地", "立项", "规划", "预售许可", "竣工", "清算", "项目分期")):
            families.add("房地产项目")
        if any(term in name_text for term in ("房源", "楼盘", "网签", "认购", "交付", "办证", "车位", "储藏室")):
            families.add("房源交易")
        if any(term in name_text for term in ("开发成本", "成本对象", "工程结算", "公共配套", "造价", "分摊")):
            families.add("开发成本")
        if any(term in name_text for term in ("SKU", "商品", "进销存", "采购入库", "门店库存", "仓店", "盘点", "调拨")):
            families.add("商品库存")
        if any(term in name_text for term in ("订单", "POS", "收银", "渠道销售", "店铺交易", "发货", "签收")):
            families.add("渠道订单")
        if any(term in name_text for term in ("支付", "商户号", "收款码", "聚合支付", "微信", "支付宝", "现金日结")):
            families.add("支付结算")
        if any(term in name_text for term in ("平台账单", "平台结算", "分账", "佣金", "冻结款")):
            families.add("平台结算")
        if any(term in name_text for term in ("退货", "退款", "红冲", "红字", "售后", "换货")):
            families.add("售后退款")
        if any(term in name_text for term in ("返利", "折扣", "促销", "补贴", "陈列", "渠道服务")):
            families.add("商业政策")
        if any(term in name_text for term in ("代销", "联营", "寄售", "总额净额")):
            families.add("代销联营")
        if any(term in name_text for term in ("会员", "储值", "预付卡", "礼券", "积分", "卡券")):
            families.add("会员权益")
        if any(term in name_text for term in ("平台基本信息", "域名", "应用清单", "许可证", "业务线", "平台运营")):
            families.add("平台基础信息")
        if any(term in name_text for term in ("平台账户", "实名认证", "经营者身份", "从业人员身份", "账号变更")):
            families.add("平台账户身份")
        if any(term in name_text for term in ("平台订单", "交易流水", "订单事件", "平台交易")):
            families.add("平台订单")
        if any(term in name_text for term in ("报送表", "涉税信息报送", "季度报送", "报送回执", "代办申报")):
            families.add("平台涉税报送")
        if any(term in name_text for term in ("系统日志", "接口日志", "权限记录", "数据谱系")):
            families.add("平台系统日志")
        if any(term in name_text for term in ("直播", "直播间", "主播", "MCN", "创作者", "内容事件")):
            families.add("直播内容")
        if any(term in name_text for term in ("虚拟币", "虚拟礼物", "打赏", "虚拟钱包")):
            families.add("虚拟权益")
        if any(term in name_text for term in ("灵活用工", "任务订单", "自由职业", "众包", "服务成果")):
            families.add("灵活用工任务")
        if any(term in name_text for term in ("网络货运", "货主订单", "实际承运", "运单")):
            families.add("网络货运")
        if any(term in name_text for term in ("车辆轨迹", "装卸地点", "签收轨迹", "司机车辆")):
            families.add("网络货运轨迹")
        if any(term in name_text for term in ("境外平台", "跨境平台", "境外经营者")):
            families.add("跨境平台")
        if any(term in name_text for term in ("客户地点", "履约地点", "数字服务", "境外服务")):
            families.add("跨境履约")
    return sorted(families), sorted(file_types)


def _observed_signal_count(scene_id, findings):
    terms = SCENE_SIGNAL_TERMS.get(scene_id, ())
    count = 0
    for finding in findings or []:
        if not isinstance(finding, dict):
            continue
        text = " ".join(
            str(finding.get(key, "") or "")
            for key in ("type", "detail", "domain", "category", "suggestion")
        )
        if any(term in text for term in terms):
            count += 1
    return count


def build_scenario_review_plan(industry, file_results=None, findings=None):
    """生成只读的场景核验计划，不改变或新增 finding。"""
    industry_code = _resolve_industry_code(industry)
    if not industry_code:
        return {
            "version": None,
            "industry": str(industry or ""),
            "industry_code": "",
            "applicable": False,
            "status": "不适用",
            "maturity": None,
            "scenes": [],
            "boundary": "未能依据实际经营活动确定适用行业；仅运行跨行业共同事实合同，并要求人工确认业务模式。",
        }

    spec = CONTRACT_ASSETS.get(industry_code, {"asset": "methodology_portfolio"})
    payload = load_scenario_contracts(industry_code)
    available_families, file_types = _available_source_families(file_results)
    available_set = set(available_families)
    plans = []
    for scene in payload.get("scenarios", []):
        scene_id = scene.get("id")
        gates = scene.get("source_gates") or SCENE_SOURCE_GATES.get(scene_id, [])
        gate_results = []
        for gate in gates:
            observed = sorted(available_set.intersection(gate.get("any", [])))
            gate_results.append({
                "name": gate.get("name"),
                "satisfied": bool(observed),
                "observed": observed,
                "accepted_families": list(gate.get("any", [])),
            })
        satisfied = sum(1 for gate in gate_results if gate["satisfied"])
        total = len(gate_results)
        if total == 0:
            status = "待补资料_可初筛" if available_set else "资料不足_未启动"
        elif satisfied == 0:
            status = "资料不足_未启动"
        elif satisfied < total:
            status = "待补资料_可初筛"
        else:
            status = "资料就绪_待人工核验"
        plans.append({
            "scene_id": scene_id,
            "name": scene.get("name"),
            "maturity": scene.get("maturity"),
            "status": status,
            "source_gate_satisfied": satisfied,
            "source_gate_total": total,
            "source_gate_results": gate_results,
            "observed_signal_count": _observed_signal_count(scene_id, findings),
            "observed_signal_boundary": "观察信号只用于确定核验顺序，不是证据或结论。",
            "target_fact": (scene.get("doubt") or {}).get("target_fact", ""),
            "lead_domain": (scene.get("domain_collaboration") or {}).get("lead", ""),
            "contract_asset": spec["asset"],
        })

    return {
        "version": payload.get("version"),
        "industry": str(industry or ""),
        "industry_code": industry_code,
        "industry_name": payload.get("name", ""),
        "contract_asset": spec["asset"],
        "applicable": True,
        "status": "核验计划已生成",
        "maturity": payload.get("maturity"),
        "available_source_families": available_families,
        "observed_file_types": file_types,
        "scene_count": len(plans),
        "ready_for_human_review": sum(
            item["status"] == "资料就绪_待人工核验" for item in plans
        ),
        "pending_more_sources": sum(
            item["status"] in ("资料不足_未启动", "待补资料_可初筛") for item in plans
        ),
        "scenes": plans,
        "boundary": payload.get("positioning"),
        "forbidden_outputs": (payload.get("common_contract") or {}).get("forbidden_outputs", []),
    }
