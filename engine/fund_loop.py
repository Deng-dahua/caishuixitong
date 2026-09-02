"""跨企业资金回流闭环 增强引擎 —— 第四阶 P1 能力（资金流闭环增强）。

这是 bank_flow 已预留 cross_enterprise 钩子的"闭环增强"实现：
bank_flow 仅做"同名对手方既收又付"的简单闭环，本模块在跨企业图谱基础上补做
**多主体（三角）资金回流**识别——企业付款给关联组某一成员、又从同组另一成员收款，
构成经由关联方的资金空转闭环（A→B→C→A 的单方视角近似：企业付出至关联组、又收到关联组回款）。

判定逻辑（单方银行流水视角，闭环金额取"付给关联组"与"关联组回款"之较小者）：
  1) 直接闭环：对手方既收又付 → 闭环=min(收,付)；
  2) 三角/关联闭环：把 cross_enterprise 关系网中的关联主体归为一组，企业对该组"净付出"
     与"净收回"同时存在 → 闭环=min(组内收回, 组内付出)（扣除已计入的直接闭环）。

输出 comprehensive["fund_loop"]，与 bank_flow / two_tax_income 同构。
"""

import time
from collections import defaultdict

_LINK_KW = (
    "公司", "有限公司", "有限责任公司", "厂", "店", "商行", "集团", "贸易", "实业",
    "供应链", "科技", "技术", "建材", "股份", "合伙", "中心", "物流", "超市",
)


def _safe(v):
    try:
        return float(v or 0)
    except Exception:
        return 0.0


def _is_corp(name):
    if not name:
        return False
    return any(k in name for k in _LINK_KW)


def _related_groups(cross_enterprise):
    """从 cross_enterprise 关系图谱构建"关联组"：每条关系把 company_a/company_b 归为同组。
    返回 list of set(名称)。"""
    ce = cross_enterprise or {}
    rels = ce.get("relationships") or []
    if not rels:
        return []
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    names = set()
    for rel in rels:
        a = str(rel.get("company_a", "") or "").strip()
        b = str(rel.get("company_b", "") or "").strip()
        if a and b:
            union(a, b)
            names.add(a)
            names.add(b)
    groups = defaultdict(set)
    for n in names:
        groups[find(n)].add(n)
    return [g for g in groups.values() if len(g) >= 1]


def run_fund_loop_check(bank_txs, cross_enterprise=None, company_name=""):
    """识别跨企业资金回流闭环（直接 + 三角/关联）。返回对齐 dict。"""
    if not bank_txs:
        return {
            "available": False,
            "ok": True,
            "title": "跨企业资金回流闭环",
            "summary": "本轮未提供银行流水。",
            "body": "资金回流闭环（货款回流至开票方/关联方）是虚开与账外经营的关键证据，"
                    "需银行流水结合跨企业图谱才能识别。未提供银行流水则无法做闭环检测。",
            "metrics": {},
            "signals": [],
            "verdict": "未提供银行流水",
            "recommendation": "上传企业银行流水（含交易日期、对方户名、借贷金额、摘要），"
                              "并提供关联企业清单以做跨企业闭环识别。",
            "note": "资金回流闭环识别属「待证线索」：需结合货物流转与合同核实业务真实性，不作为定性依据。",
        }

    # 逐对手方收/付
    recv = defaultdict(float)
    paid = defaultdict(float)
    for tx in bank_txs:
        cp = str(tx.get("counterparty", "") or "").strip()
        if not cp:
            continue
        c = _safe(tx.get("credit"))
        d = _safe(tx.get("debit"))
        if c > 0:
            recv[cp] += c
        if d > 0:
            paid[cp] += d

    # ── 1) 直接闭环 ──
    direct_amount = 0.0
    direct_detail = []
    direct_parties = set()
    for cp, r in recv.items():
        p = paid.get(cp, 0.0)
        if r > 0 and p > 0:
            loop = min(r, p)
            direct_amount += loop
            direct_parties.add(cp)
            if len(direct_detail) < 10:
                direct_detail.append(f"{cp}：收{r:,.2f}/付{p:,.2f}（闭环{loop:,.2f}）")

    # ── 2) 三角/关联闭环（基于跨企业图谱）──
    groups = _related_groups(cross_enterprise)
    indirect_amount = 0.0
    indirect_detail = []
    for g in groups:
        # 组内（排除已计入直接闭环的成员，避免重复）
        grp_recv = sum(recv.get(m, 0.0) for m in g if m not in direct_parties)
        grp_paid = sum(paid.get(m, 0.0) for m in g if m not in direct_parties)
        if grp_recv > 0 and grp_paid > 0:
            loop = min(grp_recv, grp_paid)
            indirect_amount += loop
            members = "、".join(sorted(g)[:4])
            if len(indirect_detail) < 10:
                indirect_detail.append(f"关联组[{members}]：企业收{grp_recv:,.2f}/付{grp_paid:,.2f}（闭环{loop:,.2f}）")

    circular_amount = direct_amount + indirect_amount

    # ── 信号与结论 ──
    signals = []
    sev_high = False
    sev_mid = False

    if direct_amount > 0:
        sev_high = True
        signals.append({
            "signal": f"直接资金回流闭环约{direct_amount:,.2f}元（{len(direct_parties)}个对手方既收又付）",
            "hint": "企业与同一对手方互有收付款，货款疑似回流；结合合同与货物流转核实业务真实性。"
                    + ("样例：" + "；".join(direct_detail[:3]) if direct_detail else ""),
        })

    if indirect_amount > 0:
        sev_high = True
        signals.append({
            "signal": f"经关联企业的三角资金回流闭环约{indirect_amount:,.2f}元",
            "hint": "企业通过关联组不同成员完成「付出—收回」，构成经由关联方的资金空转；"
                    "结合跨企业图谱核实同一控制人与业务闭环。" + ("样例：" + "；".join(indirect_detail[:3]) if indirect_detail else ""),
        })
    elif groups and direct_amount == 0:
        sev_mid = True
        signals.append({
            "signal": f"存在{len(groups)}个跨企业关联组，但本轮流水未直接触发闭环",
            "hint": "已构建关联网络，需补充完整流水（含关联企业账户）以检测跨账户回流；当前仅作结构提示。",
        })

    if sev_high:
        verdict = "存在跨企业资金回流闭环，须核实业务真实性"
    elif sev_mid:
        verdict = "存在关联关系，待补充流水做闭环核实"
    else:
        verdict = "未触发资金回流闭环（仅代表本轮数据范围）"

    metrics = {
        "direct_loop_amount": round(direct_amount, 2),
        "indirect_loop_amount": round(indirect_amount, 2),
        "circular_amount": round(circular_amount, 2),
        "direct_loop_parties": len(direct_parties),
        "related_groups": len(groups),
    }

    lines = []
    lines.append(f"资金回流闭环合计：{circular_amount:,.2f}元")
    if direct_amount > 0:
        lines.append(f"直接闭环：{direct_amount:,.2f}元（{len(direct_parties)}个对手方）")
        for d in direct_detail[:6]:
            lines.append(f"  - {d}")
    if indirect_amount > 0:
        lines.append(f"三角/关联闭环：{indirect_amount:,.2f}元（{len(groups)}个关联组）")
        for d in indirect_detail[:6]:
            lines.append(f"  - {d}")
    if not direct_detail and not indirect_detail:
        lines.append("本轮流水未触发明显的收付款闭环；如有关联企业账户流水未纳入，闭环可能被低估。")
    body = "\n".join(lines)

    recommendation = ("系统已识别资金回流结构。下一步：①逐笔核实闭环对手方真实交易与货物流；"
                      "②穿透关联企业同一控制人；③补充关联企业账户流水做完整闭环检测。定性权在风险检查员。")

    return {
        "available": True,
        "ok": True,
        "title": "跨企业资金回流闭环",
        "company": company_name,
        "verified_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": f"资金回流闭环合计{circular_amount:,.2f}元（直接{direct_amount:,.2f}元"
                   + (f"、关联三角{indirect_amount:,.2f}元" if indirect_amount > 0 else "") + "）。",
        "body": body,
        "metrics": metrics,
        "signals": signals,
        "verdict": verdict,
        "recommendation": recommendation,
        "note": "本识别基于银行流水与跨企业图谱，属「待证线索」：资金回流需结合货物流转与合同核实，"
                "不作为定性依据。",
    }
