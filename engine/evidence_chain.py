# -*- coding: utf-8 -*-
"""
证据链引擎 —— 回答「要坐实或排除这条红线，需要组织哪些证据」
==============================================================

证据链的定义
--------------------------------------------------
证据链是围绕一条红线组织起来的**证明要素清单**。它回答两个问题：
    ① 要认定（或排除）这条红线，法定上需要哪些证据？
    ② 本轮手上有什么、还缺什么？缺的那一项会导致这条红线查不清吗？

证据角色（税务稽查通行分类）
--------------------------------------------------
    直接证据   能直接证明待证事实（合同、入库单、发票原件）——权数 3
    资金证据   能印证款项真实流转（银行流水、支付凭证）——权数 2
    间接证据   需结合其他证据推认（物流、能耗、考勤）——权数 2
    反证       证明红线不成立的正当理由证据——单独评估，不计入闭合度

闭合度与结论
--------------------------------------------------
    闭合度 = 已取得的（直接+资金+间接）证据权数 / 必需的权数合计
    ≥0.80  证据链基本闭合 → 可作出确定性判断
    0.50~0.80 部分闭合   → 需补证后才能定性
    <0.50  未闭合         → 属检查范围受限，禁止推定，转入置疑清单

严禁：以「证据链未闭合」为由不记录疑点；也严禁以「已触红线」为由跳过证据链。
"""

from typing import Dict, List, Optional

# 证据名称关键词 → 资料类别（用于判定本轮是否已提供）
_MATERIAL_KEYWORDS: List[List[str]] = [
    ["银行流水", ["流水", "付款", "收款", "资金", "转账", "代付", "支付", "回单"]],
    ["销项发票", ["销项", "开票", "销售发票", "发票"]],
    ["进项发票", ["进项", "采购发票", "发票"]],
    ["记账凭证", ["凭证", "记账", "会计分录", "账簿"]],
    ["工资表", ["工资", "名册", "考勤", "人员", "用工", "薪酬"]],
    ["社保明细", ["社保", "参保", "缴费基数"]],
    ["进销存台账", ["入库", "出库", "库存", "盘点", "台账", "存货", "领料", "完工", "发货"]],
    ["合同文件", ["合同", "协议", "订单"]],
    ["科目余额表", ["科目", "余额", "明细账", "往来", "挂账", "辅助账"]],
    ["增值税申报表", ["申报", "纳税申报"]],
    ["企业所得税申报表", ["申报", "纳税申报", "汇算"]],
    ["个税申报表", ["个税", "扣缴", "申报"]],
    ["资产负债表", ["资产", "负债", "报表"]],
    ["利润表", ["利润", "收入", "成本", "报表"]],
]

# 等价资料类别：不同模块对同一批资料的叫法不同，须视为同一类，
# 否则「财务报表」已提供却被判「资产负债表缺失」，虚增证据缺口。
_EQUIVALENT_CATEGORIES = {
    "财务报表": ["资产负债表", "利润表"],
    "资产负债表": ["财务报表"],
    "利润表": ["财务报表"],
    "增值税申报表": ["纳税申报表", "其他税种申报表"],
    "企业所得税申报表": ["纳税申报表", "其他税种申报表"],
    "个税申报表": ["纳税申报表", "其他税种申报表"],
    "记账凭证": ["序时账", "明细账"],
    "科目余额表": ["序时账", "明细账"],
}

_ROLE_WEIGHT = {"直接证据": 3, "资金证据": 2, "间接证据": 2, "反证": 1}

# 判定「证据已有」的最低门槛：直接证据必须全部取得，间接/资金证据按比例
_DIRECT_ROLES = {"直接证据"}


def _match_material(evidence_name: str, purpose: str, available: List[str]) -> Optional[str]:
    """
    判断某项证据对应的资料本轮是否已提供，返回命中的资料类别。

    严格规则：先把证据名归到 15 类稽查资料中的某一类，再检查该类别是否
    在已提供清单里。**禁止模糊命中**——否则「采购合同」会被误判为已有
    （因为清单里有「渠道订单」这类含「合同/订单」字样但性质不同的资料），
    直接导致证据链闭合度虚高、错误定性。
    """
    text = f"{evidence_name} {purpose}"
    for category, keywords in _MATERIAL_KEYWORDS:
        if any(kw in text for kw in keywords):
            if category in available:
                return category
            # 等价类别（同一批资料的不同叫法）视为已提供
            for eq in _EQUIVALENT_CATEGORIES.get(category, []):
                if eq in available:
                    return f"{category}（{eq}）"
            return None  # 命中类别但未实际提供 → 缺失，不做模糊替代
    return None


def build_evidence_chain(finding: Dict, redline: Dict,
                         available_materials: Optional[List[str]] = None,
                         engine_data: Optional[Dict] = None) -> Dict:
    """
    构建单条疑点的证据链。

    返回：
        {
          "elements": [ {role, name, purpose, status, basis, weight} ],
          "available_count", "missing_count",
          "closure": 0~1,
          "verdict": "证据链基本闭合/部分闭合/未闭合",
          "missing_materials": [...],
          "remedy": "...",
          "rebuttal_status": "反证未提交/反证已有/反证待核"
        }
    """
    available = [str(a) for a in (available_materials or []) if a]
    engine_data = engine_data or {}
    template = list(redline.get("evidence_chain") or [])
    elements: List[Dict] = []

    # 企业已提交的反证线索（用于判断正当理由是否有资料支撑）
    _submitted = []
    for key in ("opposing_evidence", "supporting_evidence", "reasonable_explanations"):
        for v in (finding.get(key) or []):
            _submitted.append(str(v if not isinstance(v, dict)
                                  else (v.get("text") or v.get("name") or v)))

    for item in template:
        role = str(item.get("role") or "间接证据")
        name = str(item.get("name") or "")
        purpose = str(item.get("purpose") or "")
        if role == "反证":
            # 反证（正当理由）是否成立，只认企业是否实际提交，
            # 严禁按资料类别关键词猜测——否则「银行承兑汇票」里的「转账」
            # 二字会被当成反证已提供，把真实疑点错误排除。
            _nm = name[:6]
            submitted = any(_nm and _nm in t for t in _submitted)
            elements.append({
                "role": role, "name": name, "purpose": purpose,
                "status": "已提交" if submitted else "待企业提交",
                "basis": ("企业已提交相关说明或资料，须纳入论证核验"
                          if submitted else "企业尚未提交该正当理由的书面证明"),
                "weight": _ROLE_WEIGHT.get(role, 1),
            })
            continue
        hit = _match_material(name, purpose, available)
        if hit:
            status, basis = "已有", f"本轮已提供「{hit}」，可作为本项证据"
        else:
            # 若发现本身带有支持性证据记录，视为部分取得
            supporting = finding.get("supporting_evidence") or []
            partial = any(
                any(kw in str(s) for kw in (name[:4], role))
                for s in supporting
            ) if supporting else False
            if partial:
                status, basis = "部分", "本轮资料中含相关线索但未取得完整证据材料"
            else:
                status, basis = "缺失", "本轮未提供该资料，无法组织本项证据"
        elements.append({
            "role": role,
            "name": name,
            "purpose": purpose,
            "status": status,
            "basis": basis,
            "weight": _ROLE_WEIGHT.get(role, 1),
        })

    # 闭合度：只算直接/资金/间接证据（反证单独评估）
    need = sum(e["weight"] for e in elements if e["role"] != "反证")
    got = sum(e["weight"] for e in elements
              if e["role"] != "反证" and e["status"] == "已有")
    got += sum(e["weight"] * 0.5 for e in elements
               if e["role"] != "反证" and e["status"] == "部分")
    closure = round(min(1.0, got / need), 2) if need else 0.0

    direct_missing = [e["name"] for e in elements
                      if e["role"] == "直接证据" and e["status"] != "已有"]

    if closure >= 0.80 and not direct_missing:
        verdict = "证据链基本闭合"
    elif closure >= 0.50:
        verdict = "证据链部分闭合，需补充证据后定性"
    else:
        verdict = "证据链未闭合，核心证据缺失"

    missing_materials = []
    for e in elements:
        if e["status"] != "已有" and e["role"] != "反证":
            for category, keywords in _MATERIAL_KEYWORDS:
                text = f"{e['name']} {e['purpose']}"
                if any(kw in text for kw in keywords) and category not in missing_materials:
                    missing_materials.append(category)
                    break

    # 反证状态
    rebuttals = [e for e in elements if e["role"] == "反证"]
    if not rebuttals:
        rebuttal_status = "本条红线无适用反证"
    elif any(e["status"] == "已提交" for e in rebuttals):
        rebuttal_status = "企业已提交部分正当理由，须逐项核验后认定"
    else:
        rebuttal_status = "企业尚未提交正当理由的书面证明，现有资料不构成排除依据"

    return {
        "elements": elements,
        "available_count": sum(1 for e in elements if e["status"] == "已有"),
        "missing_count": sum(1 for e in elements if e["status"] != "已有"),
        "closure": closure,
        "verdict": verdict,
        "direct_missing": direct_missing,
        "missing_materials": missing_materials,
        "remedy": redline.get("remedy", ""),
        "rebuttal_status": rebuttal_status,
        "required_materials": list(redline.get("required_materials") or []),
    }


def evidence_text(chain: Dict) -> str:
    """把证据链压成一段可直读的话"""
    els = chain.get("elements") or []
    if not els:
        return ""
    have = [f"{e['name']}" for e in els if e["status"] == "已有"]
    lack = [f"{e['name']}" for e in els if e["status"] != "已有"]
    seg = []
    if have:
        seg.append("现已有证据：" + "、".join(have[:6]))
    if lack:
        seg.append("尚缺证据：" + "、".join(lack[:6]))
    seg.append(f"闭合度{int(chain.get('closure', 0) * 100)}%，{chain.get('verdict', '')}")
    return "；".join(seg) + "。"
