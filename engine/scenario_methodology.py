# -*- coding: utf-8 -*-
"""真实业务场景驱动的方法论计划器。

该模块只生成核验任务、资料缺口和候选信号，不生成违法定性、税额、
处罚或立案意见。场景合同的完整正文由受保护的只读接口提供。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ASSETS = {
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
    "K": {
        "asset": "real_estate_scenario_contracts",
        "path": _PROJECT_ROOT / "static" / "real_estate_scenario_contracts.json",
        "terms": ("房地产", "房产开发", "地产开发", "商品房开发"),
    },
}


FILE_TYPE_SOURCE_FAMILIES = {
    "inventory": {"生产存货", "仓储物流", "工程材料"},
    "sales_invoice": {"发票申报", "销售履约"},
    "purchase_invoice": {"发票申报", "采购成本", "工程材料"},
    "invoice": {"发票申报"},
    "invoice_universal": {"发票申报"},
    "input_vat_deduction": {"发票申报"},
    "tax_return": {"税费申报"},
    "tax_declaration": {"税费申报"},
    "bank": {"资金结算"},
    "bank_statement": {"资金结算"},
    "bank_transaction": {"资金结算"},
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
}


SCENE_SIGNAL_TERMS = {
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
}


@lru_cache(maxsize=len(CONTRACT_ASSETS))
def load_scenario_contracts(industry_code="C"):
    spec = CONTRACT_ASSETS[str(industry_code or "").upper()]
    return json.loads(spec["path"].read_text(encoding="utf-8-sig"))


def _resolve_industry_code(industry):
    text = str(industry or "").strip().lower()
    for code, spec in CONTRACT_ASSETS.items():
        if text == code.lower() or text.startswith(f"{code.lower()} "):
            return code
        if any(term.lower() in text for term in spec["terms"]):
            return code
    return ""


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
        if any(term in name_text for term in ("土地", "立项", "规划", "预售许可", "竣工", "清算", "项目分期")):
            families.add("房地产项目")
        if any(term in name_text for term in ("房源", "楼盘", "网签", "认购", "交付", "办证", "车位", "储藏室")):
            families.add("房源交易")
        if any(term in name_text for term in ("开发成本", "成本对象", "工程结算", "公共配套", "造价", "分摊")):
            families.add("开发成本")
    return sorted(families), sorted(file_types)


def _candidate_signal_count(scene_id, findings):
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
            "boundary": "当前仅对已完成五链重写的行业生成场景计划。",
        }

    spec = CONTRACT_ASSETS[industry_code]
    payload = load_scenario_contracts(industry_code)
    available_families, file_types = _available_source_families(file_results)
    available_set = set(available_families)
    plans = []
    for scene in payload.get("scenarios", []):
        scene_id = scene.get("id")
        gates = SCENE_SOURCE_GATES.get(scene_id, [])
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
        if satisfied == 0:
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
            "candidate_signal_count": _candidate_signal_count(scene_id, findings),
            "candidate_signal_boundary": "候选信号只用于确定核验顺序，不是证据或结论。",
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
