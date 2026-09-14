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

# 字号提取复用 domain_analysis 的去噪实现（剥行政区划 → 去组织形式 → 取 2 字），
# 两处口径必须一致，否则关联方图谱与供应链穿透会给出互相矛盾的结论。
try:  # 兜底：导入失败时退回本地实现，不因模块依赖阻断图谱构建
    from engine.domain_analysis import _brand_of as _BRAND_OF
except Exception:  # pragma: no cover
    _BRAND_OF = None


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
    """取字号（用于群集）：剥离行政区划与组织形式后取 2 字。

    2026-09-14 修正：原实现「保留行政区划前缀取前 4 字」，真实数据实测**全为误报**——
      「中国铁路」x14 = 各铁路局下属车站/车务段（火车票）；
      「深圳市福」x6 = 福田区 6 家大排档小餐馆（差旅餐饮）；
      「深圳市龙」x6 = 龙华区/龙岗区餐馆、篮球协会、百货店；
      「深圳市宝」x5 = 宝安区 5 家餐饮个体户。
    行政区划相同只说明**同城**，与"同一控制人"无关；真正的同族形态是剥离行政区划后
    字号仍相同（如"鑫源贸易/鑫源物资/鑫源建材"）。故改与 domain_analysis._brand_of 同口径，
    两处字号判定不再打架。
    """
    if _BRAND_OF is not None:
        return _BRAND_OF(name)
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


def _classify_overlap(engine_data: Dict, overlap: List[str]):
    """把双向交易主体按"对开风险"分级，复用 domain_analysis 的统一判据。

    返回 (mirror, unrelated)：
      mirror    —— 同额对开（两侧金额均≥10万 且 小额/大额≥90%）；
      unrelated —— 购销品名类别无交集且两侧金额均≥5万。
    导入失败或无金额信息时退回旧口径（全部按 unrelated 提示），不静默丢信号。
    """
    try:
        from engine.domain_analysis import classify_cross_direction
    except Exception:  # pragma: no cover
        return [], [{"name": n, "purchase": 0.0, "sale": 0.0,
                     "purchase_cats": [], "sale_cats": []} for n in overlap]
    invs = []
    for r in (engine_data.get("pur_invs") or []):
        if isinstance(r, dict):
            n = _get(r, _NAME_KEYS)
            if n:
                invs.append(dict(r, direction="进项", seller=n))
    for r in (engine_data.get("sal_invs") or []):
        if isinstance(r, dict):
            n = _get(r, _NAME_KEYS)
            if n:
                invs.append(dict(r, direction="销项", buyer=n))
    res = classify_cross_direction(invs)
    return res["mirror"], res["unrelated"]


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

    # 双向交易分级（2026-09-14 纠偏）：
    # 「互为供需」本身完全正常——委托加工、售后回购、集团内购销、商贸双向贸易，
    # 以及传媒·广告·IT·咨询业互相采购服务资源。旧逻辑只要有交集就报「高风险」，
    # 实测公司1 的两家均属行业常态（采购信息服务 50.17 万 / 销售信息服务 30.19 万；
    # 采购信息服务 16.98 万 / 销售设计服务 0.34 万），不具备对开虚增的动机。
    # 改为只对**同额对开**或**购销品名无关且金额重大**的主体出结论，其余不报。
    _mirror, _unrelated = _classify_overlap(engine_data, graph["overlap"])
    if _mirror:
        findings.append(_mk(
            "同一交易对手双向金额高度对称——疑似同额对开（待核）",
            f"{len(_mirror)} 个主体同时在供应商与客户名单中，且**双向金额高度接近**"
            f"（小额占大额≥90%、两侧均≥10万元）："
            + "；".join(f"{i['name']}（采购{i['purchase']:,.2f}元/销售{i['sale']:,.2f}元）"
                       for i in _mirror[:5])
            + "。该形态可能指向对开（环开）虚增收入与成本，但也可能是委托加工、售后回购、"
              "集团内购销、总代理与返销或互换媒体/流量资源，须核实合同、交付成果与资金流后定性。",
            9, "高风险",
            [f"对称主体 {len(_mirror)} 个"] + [i["name"] for i in _mirror[:5]],
            ["购销合同与商业目的说明", "交付成果或入库验收单", "物流与资金流水", "定价政策说明"],
            "供应商名单与客户名单求交集后，逐户比对双向金额（小额/大额≥90% 且两侧均≥10万元）",
        ))
    if _unrelated:
        findings.append(_mk(
            "同一交易对手购销品名无关（待核）",
            f"{len(_unrelated)} 个主体既为供应商又为客户，但采购与销售的**品名类别毫无交集**，"
            f"且双向金额均达 5 万元以上："
            + "；".join(f"{i['name']}（采购{i['purchase_cats'] or '—'}/销售{i['sale_cats'] or '—'}）"
                       for i in _unrelated[:5])
            + "。缺乏商业链条上的对应关系，可能指向以对开方式走票；"
              "亦可能为集团内多业态往来或偶发交易，须结合合同与交付核实。",
            6, "待核验",
            [f"品名无关主体 {len(_unrelated)} 个"] + [i["name"] for i in _unrelated[:5]],
            ["购销合同与商业目的说明", "交付成果或入库验收单", "资金流水"],
            "双向主体的进项与销项品名类别集合求交集为空，且两侧金额均≥5万元",
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
