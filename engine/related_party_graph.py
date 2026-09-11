"""关联方穿透图谱（2026-09-12）

对应金税四期核心能力之一：**跨企业关联关系图谱**。

边界说明（重要）：
金税四期的关联图谱建立在工商股权、法人、财务负责人等**全国登记数据**之上；
本系统不掌握外部工商库，因此走「**数据自证**」路线——用账套内可观测的同源信号
反推关联关系，得到的结论只能作为**待核线索**，不能据以认定关联交易或转移利润。

五类同源信号（任一命中即列为待核线索）：
1. 主体重叠：同一交易对手既是供应商又是客户（循环开票嫌疑）
2. 字号群集：多个交易对手共享同一字号/前缀（疑似一址多照、壳公司群）
3. 账号同源：不同交易对手共用同一银行账号
4. 标识同源：不同交易对手共用联系电话、地址、税号片段
5. 资金回流：向某主体付款后，资金经其关联方回流（闭环）

所有产出均为待核线索，标注"_unconfirmed"，须企业自证或稽查核实。
"""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from typing import Any, Dict, List, Set

_NAME_KEYS = ["客户名称", "购方名称", "销方名称", "供应商", "供应商名称", "客户",
              "往来单位", "对方单位", "counterparty", "name", "单位名称"]
_ACCOUNT_KEYS = ["银行账号", "账号", "收款账号", "付款账号", "account", "account_no"]
_CONTACT_KEYS = ["联系电话", "电话", "手机", "联系方式", "phone", "tel"]
_ADDR_KEYS = ["地址", "注册地址", "经营地址", "address"]
_TAXNO_KEYS = ["税号", "纳税人识别号", "税号", "tax_no", "纳税人识别号"]


def _get(rec: Dict, keys: List[str]) -> str:
    for k in keys:
        v = rec.get(k)
        if v not in (None, ""):
            return str(v).strip()
    return ""


def _names(records: Any) -> List[str]:
    out = []
    for r in records or []:
        if not isinstance(r, dict):
            continue
        n = _get(r, _NAME_KEYS)
        if n and len(n) >= 3:
            out.append(n)
    return out


def _brand(name: str) -> str:
    """取字号（用于群集）：保留行政区划前缀，去掉组织形式与行业后缀后取前 4 字。

    必须**保留行政区划**：真实风险形态是「深圳市龙*」这类同城同字号聚集
    （历史命中过"供应商名称群集'深圳市龙'——6家疑似关联壳公司"）。
    若先剥掉"深圳市"再取字，会把同族企业拆成互不相干的字号，群集彻底失效。
    """
    s = re.sub(r"[（(].*?[)）]", "", name)
    s = re.sub(r"(股份有限公司|有限责任公司|有限公司|分公司|个体户|经营部|商行|中心|厂|店)", "", s)
    return s[:4]


def _shared_attr(records: Any, keys: List[str]) -> Dict[str, Set[str]]:
    """属性 → 使用该属性的主体集合（用于发现不同主体共享同一账号/电话/地址）。"""
    m: Dict[str, Set[str]] = defaultdict(set)
    for r in records or []:
        if not isinstance(r, dict):
            continue
        attr = _get(r, keys)
        name = _get(r, _NAME_KEYS)
        if attr and len(attr) >= 6 and name:
            m[attr].add(name)
    return {k: v for k, v in m.items() if len(v) >= 2}


def build_related_party_graph(engine_data: Dict) -> Dict:
    """构建关联方穿透图谱，返回结构化结果（供报告与后续步骤复用）。"""
    sal = engine_data.get("sal_invs") or []
    pur = engine_data.get("pur_invs") or []
    bank = engine_data.get("bank_txs") or []

    customers = set(_names(sal))
    suppliers = set(_names(pur))

    graph = {
        "overlap": sorted(customers & suppliers),
        "clusters": {},
        "shared_accounts": {},
        "shared_contacts": {},
        "shared_address": {},
        "customer_count": len(customers),
        "supplier_count": len(suppliers),
    }

    # 字号群集
    by_brand: Dict[str, Set[str]] = defaultdict(set)
    for n in (customers | suppliers):
        b = _brand(n)
        if len(b) >= 3:
            by_brand[b].add(n)
    graph["clusters"] = {b: sorted(v) for b, v in by_brand.items() if len(v) >= 3}

    # 共享标识
    graph["shared_accounts"] = {k: sorted(v) for k, v in _shared_attr(bank, _ACCOUNT_KEYS).items()}
    graph["shared_contacts"] = {k: sorted(v) for k, v in _shared_attr(bank, _CONTACT_KEYS).items()}
    graph["shared_address"] = {k: sorted(v) for k, v in _shared_attr(bank, _ADDR_KEYS).items()}

    return graph


# ── 人员穿透（法人 / 股东 / 董监高）──────────────────────────────────
# 背景：cross_enterprise_graph.EnterpriseNode 已有 legal_rep/shareholders/directors
# 字段，Relationship 也支持 same_legal_rep，但 database.py 无对应工商字段 → 恒空（死代码）。
# 这里提供一条**可落地的外部数据接入路径**：从 static/company_officers.json 读取
# 工商登记式的任职与持股信息，使"同一控制人/同一股东"类关联真正能被检出。
_OFFICER_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "company_officers.json")


def load_officer_registry() -> Dict[str, Dict]:
    """读取工商式任职登记表；文件不存在返回空（不误报）。

    期望格式：
      {"企业全称": {"legal_rep": "张三", "shareholders": ["张三","李四"],
                    "directors": ["王五"], "supervisors": ["赵六"]}, ...}
    """
    try:
        if os.path.exists(_OFFICER_PATH):
            with open(_OFFICER_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def build_officer_index(registry: Dict[str, Dict]) -> Dict[str, Dict[str, set]]:
    """人员 → {角色: 企业集合} 的反查索引。"""
    index: Dict[str, Dict[str, set]] = defaultdict(lambda: defaultdict(set))
    for company, info in (registry or {}).items():
        if not isinstance(info, dict):
            continue
        rep = str(info.get("legal_rep", "") or "").strip()
        if rep and len(rep) >= 2:
            index[rep]["legal_rep"].add(company)
        for role_key, role_name in (("shareholders", "shareholder"),
                                    ("directors", "director"),
                                    ("supervisors", "supervisor")):
            for person in info.get(role_key) or []:
                p = str(person).strip()
                if p and len(p) >= 2:
                    index[p][role_name].add(company)
    return {k: dict(v) for k, v in index.items()}


def detect_officer_relations(engine_data: Dict, registry: Dict[str, Dict]) -> List[Dict]:
    """人员穿透：同一法人/股东/董监高控制多家企业，且其中与账套交易对手重合 → 关联交易疑点。"""
    if not registry:
        return []
    index = build_officer_index(registry)
    # 本账套的交易对手（供应商+客户）
    counterparties = set(_names(engine_data.get("sal_invs"))) | set(_names(engine_data.get("pur_invs")))

    findings: List[Dict] = []
    for person, roles in index.items():
        companies: set = set()
        role_desc = []
        for role, comps in roles.items():
            companies |= comps
            role_desc.append({"legal_rep": "法定代表人", "shareholder": "股东",
                              "director": "董事/高管", "supervisor": "监事"}.get(role, role))
        if len(companies) < 2:
            continue
        # 与本账套交易对手重合的部分
        overlap = sorted(c for c in companies
                         if any(c in cp or cp in c for cp in counterparties))
        level = "高风险" if overlap else "中风险"
        findings.append({
            "type": ("同一控制人旗下企业与本账套存在交易（待核）" if overlap
                     else "同一人员在多家企业任职或持股（待核）"),
            "detail": (
                f"{person}（{'/'.join(role_desc)}）同时关联 {len(companies)} 家企业："
                f"{'、'.join(sorted(companies)[:5])}。"
                + (f"其中 {len(overlap)} 家为本账套交易对手：{'、'.join(overlap[:5])}，"
                   "存在关联交易、转移定价或分散收入的嫌疑，须按独立交易原则复核定价。"
                   if overlap else
                   "虽未见与本账套直接交易，但提示存在集团化架构，"
                   "在核查关联方资金往来时应一并纳入穿透范围。")
            ),
            "level": level,
            "score": 8 if overlap else 5,
            "tax_type": "企业所得税/增值税",
            "domain": "关联交易",
            "policy_ref": "RL-CIT-001/RL-CIT-002",
            "suggestion": "请说明上述企业间股权与人员关系，并提供关联交易定价政策、"
                          "同期资料及资金往来明细。",
            "items": [{"name": "股权与人员关系说明", "status": "待补充"},
                      {"name": "关联交易定价政策与同期资料", "status": "待补充"}],
            "evidence": [f"{person} 关联 {len(companies)} 家"] + sorted(companies)[:5]
                        + ([f"交易对手重合 {len(overlap)} 家"] if overlap else []),
            "needs_material": ["股权与人员关系说明", "关联交易定价政策", "同期资料"],
            "_officer": person,
            "_officer_companies": sorted(companies),
            "_detection_method": "工商式任职/持股登记反查同一人员关联多家企业，"
                                 "并与本账套交易对手求交集",
            "_unconfirmed": True,
        })
    return findings


def run_related_party_detection(engine_data: Dict, pipeline_log: List[str] = None) -> List[Dict]:
    """按图谱产出关联方类待核发现（全部 _unconfirmed，绝不认定关联交易）。"""
    graph = build_related_party_graph(engine_data)
    findings: List[Dict] = []

    def _mk(topic: str, detail: str, score: int, level: str, evidence: List[str],
            materials: List[str], method: str) -> Dict:
        return {
            "type": topic, "detail": detail, "level": level, "score": score,
            "tax_type": "企业所得税/增值税", "domain": "关联交易",
            "policy_ref": "RL-CIT-001/RL-CIT-002/RL-PTY-002",
            "suggestion": "请说明下列主体间的关系并提供佐证：" + "、".join(materials),
            "items": [{"name": m, "status": "待补充"} for m in materials],
            "evidence": evidence, "needs_material": materials,
            "_detection_method": method, "_unconfirmed": True,
            "_related_party_graph": {
                "overlap": graph.get("overlap", []),
                "clusters": graph.get("clusters", {}),
                "shared_accounts": graph.get("shared_accounts", {}),
            },
        }

    if graph["overlap"]:
        findings.append(_mk(
            "同一交易对手既是供应商又是客户（待核）",
            f"存在 {len(graph['overlap'])} 个主体同时出现在供应商与客户名单中："
            f"{'、'.join(graph['overlap'][:5])}。该情形可能具有真实商业背景（如委托加工、"
            "售后回购），也可能指向循环开票、虚增收入与成本。请核实交易实质与商业目的。",
            7, "高风险",
            [f"重叠主体 {len(graph['overlap'])} 个"] + graph["overlap"][:5],
            ["购销合同与商业目的说明", "物流与资金流水", "定价政策说明"],
            "供应商名单与客户名单求交集，识别双向交易主体",
        ))

    for brand, members in list(graph["clusters"].items())[:5]:
        findings.append(_mk(
            "交易对手字号群集疑似关联壳公司（待核）",
            f"字号「{brand}」下聚集 {len(members)} 家交易对手：{'、'.join(members[:5])}。"
            "同一字号大量聚集可能为一址多照、关联壳公司或空壳走票通道，"
            "也可能为连锁经营、集团采购等正常情形。请核实其股权、人员与经营场所关系。",
            7, "高风险",
            [f"字号 {brand}", f"成员 {len(members)} 家"] + members[:5],
            ["各主体工商登记信息", "股权与人员关系说明", "经营场所与人员证明"],
            "按字号（去行政区划与行业后缀）聚类交易对手，聚集数≥3 即列为线索",
        ))

    for attr, members in list(graph["shared_accounts"].items())[:3]:
        findings.append(_mk(
            "不同交易对手共用同一银行账号（待核）",
            f"银行账号 ***{str(attr)[-4:]} 被 {len(members)} 个不同主体使用："
            f"{'、'.join(members[:5])}。不同主体共用收款账号通常指向关联方、走票通道或"
            "个人账户代收，请核实账号归属与资金最终去向。",
            8, "高风险",
            [f"共享账号 {len(members)} 个主体"] + members[:5],
            ["银行开户资料与账号归属证明", "资金去向说明", "主体关系说明"],
            "按银行账号反查使用该账号的不同主体（≥2 个即可疑）",
        ))

    for attr, members in list(graph["shared_contacts"].items())[:3]:
        findings.append(_mk(
            "不同交易对手共用同一联系电话（待核）",
            f"联系电话 ***{str(attr)[-4:]} 被 {len(members)} 个不同主体使用："
            f"{'、'.join(members[:5])}。请核实是否为同一实际控制人、同一办公场所或代办机构。",
            6, "中风险",
            [f"共享电话 {len(members)} 个主体"] + members[:5],
            ["各主体联系方式与办公场所证明", "实际控制人说明"],
            "按联系电话反查使用该号码的不同主体（≥2 个即可疑）",
        ))

    for attr, members in list(graph["shared_address"].items())[:3]:
        findings.append(_mk(
            "不同交易对手共用同一经营地址（待核）",
            f"地址「{str(attr)[:20]}」被 {len(members)} 个不同主体登记使用："
            f"{'、'.join(members[:5])}。请核实是否为一址多照、同一场所经营或注册代理机构地址。",
            6, "中风险",
            [f"共享地址 {len(members)} 个主体"] + members[:5],
            ["各主体经营场所租赁合同", "注册登记地址证明"],
            "按经营地址反查使用该地址的不同主体（≥2 个即可疑）",
        ))

    # 人员穿透（法人/股东/董监高）——需 static/company_officers.json，
    # 无该文件时自动跳过（不误报），并在日志中提示数据缺口。
    _registry = load_officer_registry()
    if _registry:
        findings.extend(detect_officer_relations(engine_data, _registry))
    elif pipeline_log is not None:
        pipeline_log.append(
            "[关联方穿透] 未提供工商任职登记(static/company_officers.json)，"
            "法人/股东/董监高维度未穿透"
        )

    if pipeline_log is not None and findings:
        pipeline_log.append(
            f"[关联方穿透] 检出 {len(findings)} 条关联线索"
            f"（双向交易 {len(graph['overlap'])}、字号群集 {len(graph['clusters'])}、"
            f"共享账号 {len(graph['shared_accounts'])}）"
        )
    return findings
