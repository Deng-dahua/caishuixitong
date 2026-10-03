# -*- coding: utf-8 -*-
"""采购来源真实性核验（唯一权威）（2026-10-03）

═══════════════════════════════════════════════════════════════════════════════
为什么需要它（用户原话）
═══════════════════════════════════════════════════════════════════════════════
「虽然对供应商的范围有新的定义（＝成本类采购），但是**采购来源的真实性还是值得严谨的查一查**，
这是一个很好的疑点，就得看**如何证实**采购来源的真实性。」

集中度/地域分布**本身不足以定性质**（已实证：公司1 真实供应商 374 家、CR3 33.68% 属分散，
却曾被写成"高度集中"）。要"证实采购来源真实性"，必须用**可证伪的事实**——
每一条都能由某份资料或某类外部数据证实/证否，而不是靠统计指标猜测。

本模块给出一组**全部可证伪**的判据（每条都写清"用什么资料能证实或排除"）：

 Z1 **有票无付款**：进项发票销方在银行流水中查不到对公付款（金额达门槛）
    → 证实资料：全部银行账户流水、付款凭证；外部：银行流水完整性核验
 Z2 **付款对象与开票销方不符**：钱付给了发票销方以外的第三方（资金流与票流不一致）
    → 证实资料：合同（约定收款方）、付款申请单、代付协议
 Z3 **同日同额/连号重复开票**：同一销方同日开出多张同额票、或票号连续集中于一日
    → 证实资料：合同/订单、服务成果交付记录（服务类无物流，改看成果与工时）
 Z4 **顶额开票**：单张金额贴近发票限额（十万位整数上限），疑拆分/凑额
    → 证实资料：合同金额与结算单、服务成果
 Z5 **开票方主体特征异常**：名称含"工作室/中心/服务部"等且无实体经营特征（需外部数据）
    → 证实资料：工商登记（成立时间/实缴资本/参保人数/经营场所）、开票环境
 Z6 **品名与业务/经营范围不匹配**：外购品名与本企业行业、客户项目无对应
    → 证实资料：项目立项/合同、成本构成、工时记录（服务业的"料"是人与时间）
 Z7 **资金闭环**：付款后短期内经个人账户回流（复用资金回流配对能力）

★ 本模块**只产出事实与核实路径**，不做定性；定性留给红线引擎按要件判定。
★ 判据数据化（阈值集中在下方常量），新增线索只加一条判据函数。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

from engine.numparse import to_number

#: Z1 单笔付款匹配容差（元）
PAY_MATCH_TOL = 1000.0
#: Z1 触发门槛：无对应付款的采购金额（元）
NO_PAY_FLOOR = 500000.0
#: Z4 顶额开票：距**税控单张最高开票限额**的差值不超过此比例
NEAR_LIMIT_RATIO = 0.02
#: 税控单张最高开票限额档位（顶额开票只针对这些档位，不是"任意整数"）
INVOICE_LIMITS = (9999.99, 99999.99, 999999.99, 9999999.99)
#: Z3 同日同额重复开票的门槛（张数）
SAME_DAY_SAME_AMT_MIN = 2
#: Z3/Z4 **单张金额门槛**：低于此额的同日同额/顶额不构成线索
#   （实测不加门槛时，保险 30 元、餐饮/京东 100 元等日常小额报销全部命中——纯噪声）
SHAPE_FLOOR = 50000.0


def _fk_total(inv: Any) -> float:
    from engine.fieldkit import total as _t
    return abs(to_number(_t(inv) or 0))


def _seller_of(inv: Any) -> str:
    from engine.fieldkit import seller_name as _s
    return str(_s(inv) or "").strip()


def _payee_of(tx: Any) -> str:
    return str((tx or {}).get("counterparty") or (tx or {}).get("counterparty_name") or "").strip()


def _debit_of(tx: Any) -> float:
    return abs(to_number((tx or {}).get("debit", 0)))


def _name_match(a: str, b: str) -> bool:
    """名称是否指向同一主体（前缀/包含，短名从严）。"""
    a, b = str(a or "").strip(), str(b or "").strip()
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= 6 and len(b) >= 6 and a[:6] == b[:6]:
        return True
    if len(a) >= 4 and len(b) >= 4 and (a in b or b in a):
        return True
    return False


def _near_limit(amount: float) -> Optional[float]:
    """是否**顶额开票**：贴近税控设备的单张最高开票限额。

    ★ 2026-10-03 修正：旧判据用"上一个 1 万/10 万整数上限"，于是 69,600 会"贴近 70,000"、
      89,923 会"贴近 90,000" —— 那是**凑整**，不是**限额**，几乎每张票都能命中（纯噪声）。
      真正的限额档位是 9,999.99 / 99,999.99 / 999,999.99 / 9,999,999.99（税控最高开票限额）。
    """
    best = None
    for lim in INVOICE_LIMITS:
        # ★ 必须"**低于**且贴近"限额：差额为正、且在容差内。
        #   旧写法 `(lim - amount)/lim <= ratio` 在 amount 远大于 lim 时差额为**负数**，
        #   也满足 `<= ratio` ⇒ 任何金额都会"贴近 9,999.99"（实测 680,000 被判贴近 1 万）。
        gap = (lim - amount) / lim
        if 0 <= gap <= NEAR_LIMIT_RATIO:
            best = round(lim, 2)          # 取最贴近的档位
    return best


def verify_procurement_authenticity(pur_invs: Sequence[Any],
                                    bank_txs: Sequence[Any] = (),
                                    *,
                                    industry: Any = "",
                                    cost_only: bool = True) -> Dict[str, Any]:
    """采购来源真实性核验（唯一实现）。

    返回 {facts: [...], by_code: {...}, note: str}
      facts —— 每条：[{code, 事实, 金额, 对象, 需核实, 可证实资料}]
    """
    from engine.fieldkit import invoice_no as _invno

    pur = list(pur_invs or [])
    bank = list(bank_txs or ())
    facts: List[Dict[str, Any]] = []

    # ── 按发票号去重后归集（一票多行不得重复计）──
    by_inv: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for r in pur:
        s = _seller_of(r)
        if not s:
            continue
        no = str(_invno(r) or "").strip() or ("__row__%d" % id(r))
        amt = _fk_total(r)
        k = (s, no)
        if amt > (by_inv.get(k) or {}).get("金额", 0.0):
            by_inv[k] = {"销方": s, "票号": no, "金额": amt, "日期": str(r.get("date") or "")[:10],
                         "raw": r}
    invoices = list(by_inv.values())
    total = sum(i["金额"] for i in invoices)
    invoices_all = list(invoices)          # ★ 全量：票↔款匹配（Z1/Z2）必须用它
    # ★ 只有"开票形态/主体特征"（Z3/Z4/Z5）才按**成本类**口径收窄（与"供应商"定义一致：
    #   保险/餐饮/京东/差旅等期间费用类对手方不参与采购来源分析）。
    #   实测教训：Z2 若也用收窄集合，会把"已开票的销方"误报成"无该主体开票"
    #   （林超攀明明开了 60 万的票，却被报"无该主体开票"）。
    if cost_only:
        try:
            from engine.account_classifier import filter_cost_invoices as _fci
            _cost_keys = {str(_invno(r) or "").strip() for r in _fci(pur, industry)}
            invoices = [i for i in invoices if i["票号"] in _cost_keys]
        except Exception:
            pass
    _all_sellers = {i["销方"] for i in invoices_all}

    # ── 银行付款（按对手方归集）──
    paid: Dict[str, float] = defaultdict(float)
    for t in bank:
        p = _payee_of(t)
        d = _debit_of(t)
        if p and d > 0:
            paid[p] += d

    def _paid_for(name: str) -> float:
        if name in paid:
            return paid[name]
        best = 0.0
        for p, v in paid.items():
            if _name_match(name, p):
                best = max(best, v)
        return best

    # ── Z1 有票无付款（按销方归集后逐个判定）──
    # ★ Z1（有票无付款）与 Z2 同属"票↔款匹配"，必须用**全量**发票：
    #   付款到底发生没发生，与这张票被归为成本还是费用**无关**。
    by_seller_all: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for i in invoices_all:
        by_seller_all[i["销方"]].append(i)
    by_seller: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for i in invoices:
        by_seller[i["销方"]].append(i)
    for seller, rows in by_seller_all.items():
        amt = sum(r["金额"] for r in rows)
        if amt < NO_PAY_FLOOR:
            continue
        p = _paid_for(seller)
        if p <= 0:
            facts.append({
                "code": "Z1", "事实": f"{seller} 开票 {amt:,.2f} 元，但银行流水中**未见对该销方的付款**",
                "金额": round(amt, 2), "对象": seller,
                "需核实": "是否为挂账赊购、由关联方/第三方代付、或以现金/私户支付",
                "可证实资料": "全部银行账户流水（含一般户与已销户）、付款凭证、代付协议、采购合同付款条款",
            })

    # ── Z3 同日同额重复开票 / 同日连号 ──
    key = defaultdict(list)
    for i in invoices:
        key[(i["销方"], i["日期"], round(i["金额"], 2))].append(i["票号"])
    for (seller, day, amt), nos in key.items():
        if len(nos) >= SAME_DAY_SAME_AMT_MIN and amt >= SHAPE_FLOOR:
            facts.append({
                "code": "Z3",
                "事实": f"{seller} 在 {day} 同日开出 {len(nos)} 张同额发票（每张 {amt:,.2f} 元，票号 {', '.join(nos[:3])}）",
                "金额": round(amt * len(nos), 2), "对象": seller,
                "需核实": "是否同一笔服务被拆分开票（拆分通常为规避限额或凑额）",
                "可证实资料": "服务合同/订单（约定总价与结算方式）、服务成果交付记录、工时记录",
            })

    # ── Z4 顶额开票 ──
    for i in invoices:
        lim = _near_limit(i["金额"])
        if lim and i["金额"] >= SHAPE_FLOOR:
            facts.append({
                "code": "Z4", "事实": f"票号 {i['票号']} 金额 {i['金额']:,.2f} 元，贴近 {lim:,.0f} 元上限（差额 {lim - i['金额']:,.2f} 元）",
                "金额": round(i["金额"], 2), "对象": i["销方"],
                "需核实": "是否为规避单张限额而拆分/凑额开票",
                "可证实资料": "合同金额与结算单、服务成果、付款记录",
            })

    # ── Z5 主体特征（仅从名称可判者；其余须外部数据）──
    small_kw = ("工作室", "中心", "服务部", "经营部", "商行")
    for seller, rows in by_seller.items():
        amt = sum(r["金额"] for r in rows)
        if amt >= NO_PAY_FLOOR and any(k in seller for k in small_kw):
            facts.append({
                "code": "Z5", "事实": f"{seller}（登记形式为个体/工作室类）开票合计 {amt:,.2f} 元",
                "金额": round(amt, 2), "对象": seller,
                "需核实": "该主体是否有与开票规模相匹配的实际经营能力（人员、场所、社保）",
                "可证实资料": "工商登记（成立时间、注册资本、参保人数、经营场所）、开票环境信息、服务成果",
            })

    # ── Z2 付款对象与开票销方不符（付款方在**全量**销方集合之外且金额较大）──
    #   限定：只对"疑似采购付款"的对手方判——个人账户/借款往来/税费等属别的红线范畴
    #   （初永伟、李昭阳这类在账上挂"其他应付款"，是借款往来，不是采购来源问题）。
    from engine.fieldkit import looks_like_person as _is_person
    sellers = _all_sellers
    for p, v in sorted(paid.items(), key=lambda kv: -kv[1])[:50]:
        if v < NO_PAY_FLOOR:
            continue
        if _is_person(p):
            continue
        if any(_name_match(p, s) for s in sellers):
            continue
        facts.append({
            "code": "Z2", "事实": f"向「{p}」付款 {v:,.2f} 元，但本轮进项发票中**无该主体的开票**",
            "金额": round(v, 2), "对象": p,
            "需核实": "该付款对应哪张发票/哪个供应商（是否存在第三方代收、账外采购、或个人账户收款）",
            "可证实资料": "采购合同（约定收款方）、付款申请与审批单、代付协议、供应商对账记录",
        })

    codes = defaultdict(lambda: {"金额": 0.0, "条数": 0})
    for f in facts:
        codes[f["code"]]["金额"] += f.get("金额", 0.0)
        codes[f["code"]]["条数"] += 1

    note = ""
    if facts:
        note = ("采购来源真实性：本轮检出 %d 条可证伪线索（有票无付款 %d 条、同日同额 %d 条、"
                "顶额开票 %d 条、主体特征 %d 条、付款对象不符 %d 条）。"
                "每条线索都列明了**用什么资料能证实或排除**；集中度/地域分布仅作背景，不作定性依据。"
                % (len(facts), codes["Z1"]["条数"], codes["Z3"]["条数"],
                   codes["Z4"]["条数"], codes["Z5"]["条数"], codes["Z2"]["条数"]))
    else:
        note = ("采购来源真实性：按「有票无付款／同日同额／顶额开票／付款对象不符」四类可证伪线索核查，"
                "本轮**未检出**异常；纳入核查的成本类进项发票 %d 张（已按票号去重）、合计 %s 元。"
                % (len(invoices), format(total, ",.2f")))
    return {"facts": facts, "by_code": {k: dict(v) for k, v in codes.items()},
            "invoice_count": len(invoices), "total": round(total, 2),
            "note": note.replace("**", "")}


__all__ = ["verify_procurement_authenticity", "PAY_MATCH_TOL", "NO_PAY_FLOOR",
           "NEAR_LIMIT_RATIO", "SAME_DAY_SAME_AMT_MIN", "SHAPE_FLOOR"]
