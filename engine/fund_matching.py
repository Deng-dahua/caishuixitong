# -*- coding: utf-8 -*-
"""发票 ↔ 银行流水匹配引擎（2026-09-05 研发）。

税务稽查员的证据链思维：主营业务成本必须有真实的资金支付印证。
    - 对公支付流水匹配   → 交易真实性强 ✓
    - 个人垫付后报销     → 发票流与资金流分离，三流不一致，需核验（大额即风险）
    - 没有任何支付记录   → 挂账未付 / 虚开发票 / 发票未入账，分级核验

收入侧同理：主营业务收入必须对应银行或第三方平台收款。
    - 有收款流水 → 收入真实性强 ✓
    - 无收款流水 → 应收账款挂账或虚构收入风险

匹配策略（现实考虑）：
    1. 名称精确匹配：规范化后完全一致；
    2. 核心名包含匹配：流水对方名包含发票对方核心名（或反之），
       覆盖"XX有限公司" vs "XX公司"、"XX（总部）"等现实差异；
    3. 金额窗口匹配：同名交易对手的流水合计与发票金额偏差 ≤15%；
    4. 第三方平台归集（财付通/支付宝/微信支付）视为有效收款通道。
"""

from __future__ import annotations

from collections import defaultdict

# ── 名称规范化 ───────────────────────────────────────────────
_PROVINCES = [
    "北京", "天津", "上海", "重庆", "河北", "山西", "辽宁", "吉林", "黑龙江",
    "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南",
    "广东", "海南", "四川", "贵州", "云南", "陕西", "甘肃", "青海", "台湾",
    "内蒙古", "广西", "西藏", "宁夏", "新疆", "香港", "澳门",
]

_COMPANY_SUFFIXES = [
    "股份有限公司", "有限责任公司", "集团有限公司", "有限公司", "集团",
    "总公司", "分公司", "公司", "厂", "商行", "经营部", "经销部",
    "商店", "店铺", "个体工商户", "工作室", "事务所", "中心", "服务部",
]

_PLATFORM_KEYWORDS = ["财付通", "支付宝", "微信支付", "银联", "易宝", "汇付天下",
                      "通联支付", "拉卡拉", "快钱", "网银在线", "京东支付", "美团",
                      "翼支付", "和包", "云闪付", "第三方支付", "聚合支付", "收单"]

_INDIVIDUAL_MARKERS = ["先生", "女士", "小姐", "师傅", "老板"]

# 机构类名称（无公司后缀但绝非个人）：防止把酒店/学校等误判为自然人
_ORGANIZATION_MARKERS = [
    "酒店", "饭店", "宾馆", "旅馆", "酒店管理", "餐饮", "餐厅", "食堂",
    "学校", "学院", "大学", "幼儿园", "医院", "诊所", "药店", "卫生",
    "银行", "信用社", "支行", "分理处", "保险", "证券", "基金",
    "超市", "商场", "百货", "市场", "商城", "广场",
    "政府", "局", "委", "中心", "服务中心", "办事处", "村委会", "居委会",
    "税务", "财政", "国库", "公积金", "社保", "彩票", "邮政", "电信", "移动",
    "供电", "供水", "燃气", "水务", "加油站", "物业", "会所", "旅行社",
]


def normalize_entity_name(name: str) -> str:
    """规范化企业/个人名称：去省份前缀、公司后缀、空白与标点。"""
    if not name:
        return ""
    text = str(name).strip()
    # 全角转半角、去空白
    text = "".join(ch for ch in text if ch not in " \t\n\r\u3000")
    # 去省份前缀（带"省/市/自治区"长形式优先）
    for p in sorted(_PROVINCES, key=len, reverse=True):
        if text.startswith(p):
            text = text[len(p):]
            break
    if text.startswith("省") or text.startswith("市"):
        text = text[1:]
    # 去公司后缀
    changed = True
    while changed:
        changed = False
        for s in _COMPANY_SUFFIXES:
            if text.endswith(s):
                text = text[: -len(s)]
                changed = True
                break
    # 去括号及内容（"XX（总部）"→"XX"）
    import re
    text = re.sub(r"[（(【\[].*?[)）】\]]", "", text)
    return text.strip()


def _core_of(name: str) -> str:
    core = normalize_entity_name(name)
    return core if core else str(name or "").strip()


def is_platform_counterparty(name: str) -> bool:
    """是否第三方支付平台/聚合收单机构（其收款属于有效资金通道）。"""
    n = str(name or "")
    return any(k in n for k in _PLATFORM_KEYWORDS)


def is_individual_name(name: str) -> bool:
    """判断流水对方名称是否为自然人（无公司后缀且含人称标记或纯姓名特征）。"""
    n = str(name or "").strip()
    if not n:
        return False
    if any(k in n for k in _INDIVIDUAL_MARKERS):
        return True
    # 机构类名称（酒店/学校/银行等）绝非个人
    if any(k in n for k in _ORGANIZATION_MARKERS):
        return False
    core = normalize_entity_name(n)
    # 规范化后与原名一致（没有任何公司后缀被剥掉）且非平台 → 大概率是个人
    return bool(core) and core == n and not is_platform_counterparty(n)


def _amount_of(row) -> float:
    try:
        return float(row.get("amount") or row.get("total") or 0)
    except (TypeError, ValueError):
        return 0.0


def match_invoices_to_flows(inv_rows, bank_txs, side="purchase", name_field=None):
    """把发票与银行流水做方向性匹配（客户级聚合策略，2026-09-05）。

    side="purchase"：发票 seller（销方）↔ 流水 debit（支出）counterparty
    side="sale"：    发票 buyer（购方）↔ 流水 credit（收入）counterparty

    匹配策略（现实考虑）：同一客户常有多张发票、多笔流水（分批付款），
    单张发票与单笔流水直接比对必然失配。因此按「交易对手核心名」聚合：
      1. 名称匹配（核心名精确或包含）；
      2. 客户级金额比对：|同名流水合计 - 同名发票合计| / 发票合计 ≤ 25%
         （窗口放宽到 25%，覆盖分批付款、跨期回款、部分赊销等现实情形）；
      3. 匹配成功 → 该客户全部发票均视为有资金印证；
      4. 第三方平台归集（财付通/支付宝等）作为独立有效收款通道。

    返回:
        {
          "per_inv": [ {"row": inv, "matched": bool, "flow_rows": [...], "pay_mode": ...} ],
          "matched_amount": float, "unmatched_amount": float, "match_ratio": float,
        }
    """
    inv_rows = inv_rows or []
    bank_txs = bank_txs or []

    # 建流水索引：核心名 → 流水列表（支出或收入方向）
    flow_index = defaultdict(list)
    for tx in bank_txs:
        cp = str(tx.get("counterparty") or "").strip()
        if not cp:
            continue
        if side == "purchase":
            if _number_of(tx.get("debit")) <= 0:
                continue  # 采购付款只看支出流水
        else:
            if _number_of(tx.get("credit")) <= 0:
                continue  # 销售收款只看收入流水
        flow_index[_core_of(cp)].append(tx)

    # ── 客户级聚合：核心名 → (发票列表, 发票合计, 流水列表, 流水合计) ──
    inv_groups = defaultdict(lambda: {"invs": [], "total": 0.0})
    for inv in inv_rows:
        if not isinstance(inv, dict):
            continue
        name = str(inv.get(name_field) or inv.get("seller") or inv.get("buyer") or "").strip()
        key = _core_of(name) if name else ""
        inv_groups[key]["invs"].append(inv)
        inv_groups[key]["total"] += _amount_of(inv)

    flow_groups = defaultdict(lambda: {"flows": [], "total": 0.0})
    for key, flows in flow_index.items():
        flow_groups[key]["flows"] = flows
        flow_groups[key]["total"] = sum(
            _number_of(tx.get("debit") if side == "purchase" else tx.get("credit")) for tx in flows
        )

    # ── 客户级匹配判定 ──
    matched_keys = set()
    for key, ig in inv_groups.items():
        if not key:
            continue  # 无对手方名称的发票无法匹配
        # 1. 名称匹配：精确或核心名互含
        candidate_keys = []
        if key in flow_groups:
            candidate_keys.append(key)
        else:
            for fk in flow_groups:
                if fk and (key in fk or fk in key):
                    candidate_keys.append(fk)
        if not candidate_keys:
            continue
        # 2. 客户级金额比对
        fg_total = sum(flow_groups[fk]["total"] for fk in candidate_keys)
        inv_total = ig["total"]
        if inv_total <= 0:
            matched_keys.add(key)  # 发票无金额：同名流水即算有支付痕迹
            continue
        if abs(fg_total - inv_total) / inv_total <= 0.25:
            matched_keys.add(key)

    per_inv = []
    matched_amount = 0.0
    unmatched_amount = 0.0
    for inv in inv_rows:
        if not isinstance(inv, dict):
            continue
        amount = _amount_of(inv)
        name = str(inv.get(name_field) or inv.get("seller") or inv.get("buyer") or "").strip()
        key = _core_of(name) if name else ""
        matched = key in matched_keys
        if not name:
            per_inv.append({"row": inv, "matched": False, "flow_rows": [], "pay_mode": "no_counterparty"})
            unmatched_amount += amount
            continue
        if matched:
            flows = []
            for fk in flow_groups:
                if fk == key or (key and fk and (key in fk or fk in key)):
                    flows.extend(flow_groups[fk]["flows"])
            if any(is_platform_counterparty(tx.get("counterparty")) for tx in flows):
                pay_mode = "platform"
            elif any(is_individual_name(tx.get("counterparty")) for tx in flows):
                pay_mode = "person_paid"
            else:
                pay_mode = "company_paid"
            matched_amount += amount
        else:
            # 有同名流水但金额对不上 → 金额不符；无同名流水 → 无支付记录
            has_same_name = any(
                key and fk and (key in fk or fk in key) for fk in flow_groups
            ) or key in flow_groups
            pay_mode = "amount_mismatch" if has_same_name else "no_flow"
            unmatched_amount += amount
        per_inv.append({"row": inv, "matched": matched, "flow_rows": flows if matched else [], "pay_mode": pay_mode})

    total = matched_amount + unmatched_amount
    return {
        "per_inv": per_inv,
        "matched_amount": round(matched_amount, 2),
        "unmatched_amount": round(unmatched_amount, 2),
        "match_ratio": round(matched_amount / total, 4) if total > 0 else 0.0,
    }


def classify_core_cost_payment(core_invs, bank_txs):
    """主营成本发票的付款方式分类（证据链核心）。

    返回:
        {
          "company_paid": [...],  # 对公流水匹配（含平台代付视为有效）
          "person_paid": [...],   # 个人垫付（流水对方为自然人）
          "unpaid": [...],        # 无支付记录（挂账/虚开/未入账风险）
          "amount_mismatch": [...],  # 有同名流水但金额对不上
          "totals": {...},
          "evidence_ratio": float,  # 有资金印证的占比（对公+平台+个人都算有资金痕迹）
        }
    """
    result = match_invoices_to_flows(core_invs, bank_txs, side="purchase", name_field="seller")
    company_paid, person_paid, unpaid, mismatch = [], [], [], []
    for entry in result["per_inv"]:
        mode = entry.get("pay_mode")
        if mode == "company_paid" or mode == "platform":
            company_paid.append(entry)
        elif mode == "person_paid":
            person_paid.append(entry)
        elif mode == "no_flow" or mode == "no_counterparty":
            unpaid.append(entry)
        else:
            mismatch.append(entry)

    def _sum(entries):
        return round(sum(_amount_of(e["row"]) for e in entries), 2)

    total = _sum(company_paid) + _sum(person_paid) + _sum(unpaid) + _sum(mismatch)
    evidenced = _sum(company_paid) + _sum(person_paid)
    return {
        "company_paid": company_paid,
        "person_paid": person_paid,
        "unpaid": unpaid,
        "amount_mismatch": mismatch,
        "totals": {
            "company_paid": _sum(company_paid),
            "person_paid": _sum(person_paid),
            "unpaid": _sum(unpaid),
            "amount_mismatch": _sum(mismatch),
            "total": total,
        },
        "evidence_ratio": round(evidenced / total, 4) if total > 0 else 0.0,
    }


def classify_revenue_receipt(sal_invs, bank_txs):
    """销项发票的收款印证分类（收入侧证据链）。

    返回: {"matched": [...], "unmatched": [...], "totals": {...}, "receipt_ratio": float}
    """
    result = match_invoices_to_flows(sal_invs, bank_txs, side="sale", name_field="buyer")
    matched, unmatched = [], []
    for entry in result["per_inv"]:
        if entry.get("matched"):
            matched.append(entry)
        else:
            unmatched.append(entry)

    def _sum(entries):
        return round(sum(_amount_of(e["row"]) for e in entries), 2)

    total = _sum(matched) + _sum(unmatched)
    return {
        "matched": matched,
        "unmatched": unmatched,
        "totals": {"matched": _sum(matched), "unmatched": _sum(unmatched), "total": total},
        "receipt_ratio": round(_sum(matched) / total, 4) if total > 0 else 0.0,
    }


def _number_of(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
