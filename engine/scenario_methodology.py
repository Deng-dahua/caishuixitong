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
_CONTRACT_PATH = _PROJECT_ROOT / "static" / "manufacturing_scenario_contracts.json"


FILE_TYPE_SOURCE_FAMILIES = {
    "inventory": {"生产存货", "仓储物流"},
    "sales_invoice": {"发票申报", "销售履约"},
    "purchase_invoice": {"发票申报", "采购成本"},
    "invoice": {"发票申报"},
    "invoice_universal": {"发票申报"},
    "input_vat_deduction": {"发票申报"},
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
}


@lru_cache(maxsize=1)
def load_scenario_contracts():
    return json.loads(_CONTRACT_PATH.read_text(encoding="utf-8-sig"))


def _is_manufacturing(industry):
    text = str(industry or "").strip().lower()
    return text == "c" or any(term in text for term in ("制造", "生产企业", "加工企业", "工厂"))


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
    payload = load_scenario_contracts()
    if not _is_manufacturing(industry):
        return {
            "version": payload.get("version"),
            "industry": str(industry or ""),
            "applicable": False,
            "status": "不适用",
            "maturity": payload.get("maturity"),
            "scenes": [],
            "boundary": payload.get("positioning"),
        }

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
            "contract_asset": "manufacturing_scenario_contracts",
        })

    return {
        "version": payload.get("version"),
        "industry": str(industry or ""),
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
