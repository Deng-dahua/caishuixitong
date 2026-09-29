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

from engine.numparse import to_number  # ★ 2026-09-25 统一数值解析（唯一实现）
import time
from collections import defaultdict

_LINK_KW = (
    "公司", "有限公司", "有限责任公司", "厂", "店", "商行", "集团", "贸易", "实业",
    "供应链", "科技", "技术", "建材", "股份", "合伙", "中心", "物流", "超市",
)

# ★ 2026-09-29（点评整改 P1-2）：**"闭环"必须按特征分级，不能"互有收付即闭环"**。
#   外部点评实测：`min(收,付)>0` 即判闭环，于是
#     ·「河南林超攀 付600,000 / 收0」这类**单侧往来**被并进"回流要件"（实际不构成闭环）；
#     · 等额双向（科沃斯 2 万/2 万、时趣 5.5 万/5.5 万）与悬殊双向（107 万/27.5 万）**同列**，
#       读者无法区分"过账走账"与"正常业务往来"。
#   分级口径（对称度 = |收−付| ÷ max(收,付)，**通用、与行业无关**）：
#     · ≤5%   → 等额双向：典型"过账/代收代付"，最高关注；
#     · ≤30%  → 近似双向：可能含部分回流，须核；
#     · >30%  → **不对称·单侧往来：不构成回流闭环**，单独列示为普通资金往来。
#   只有前两类计入"闭环金额"。
_LOOP_SYMMETRY_TIGHT = 0.05
_LOOP_SYMMETRY_LOOSE = 0.30


def _loop_tier(recv: float, paid: float):
    """按对称度给"互有收付"分级。返回 (是否构成闭环, 档位名, 对称度)。"""
    hi = max(float(recv or 0.0), float(paid or 0.0))
    if hi <= 0:
        return False, "", 0.0
    asym = abs(float(recv or 0.0) - float(paid or 0.0)) / hi
    if asym <= _LOOP_SYMMETRY_TIGHT:
        return True, "等额双向（疑似过账/代收代付）", asym
    if asym <= _LOOP_SYMMETRY_LOOSE:
        return True, "近似双向（可能含部分回流，须核）", asym
    return False, "不对称·单侧往来（不构成回流闭环）", asym


def _safe(v):
    """数值解析（统一实现）。

    ★ 2026-09-25 收敛：实现已统一到 engine/numparse.py（唯一权威）。
      原私有实现遇 "12,000.00" / "￥1,234.56" 等会静默返回 0，
      导致同一金额在不同模块被算成不同值（报告自相矛盾 / 规则漏触发）。
    """
    from engine.numparse import to_number as _to_number
    return _to_number(v)


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

    # ── 1) 直接闭环（★ P1-2：按对称度分级，只有等额/近似双向才计闭环）──
    direct_amount = 0.0
    direct_detail = []
    direct_parties = set()
    asym_parties = []            # 不对称·单侧往来（不计入闭环，单列说明）
    tight_n = loose_n = 0
    for cp, r in recv.items():
        p = paid.get(cp, 0.0)
        if r > 0 and p > 0:
            _ok, _tier, _asym = _loop_tier(r, p)
            if not _ok:
                if len(asym_parties) < 10:
                    asym_parties.append(f"{cp}：收{r:,.2f}/付{p:,.2f}（对称度{_asym:.0%}，{_tier}）")
                continue
            loop = min(r, p)
            direct_amount += loop
            direct_parties.add(cp)
            if _asym <= _LOOP_SYMMETRY_TIGHT:
                tight_n += 1
            else:
                loose_n += 1
            if len(direct_detail) < 10:
                direct_detail.append(f"{cp}：收{r:,.2f}/付{p:,.2f}（闭环{loop:,.2f}，{_tier}）")

    # ── 2) 三角/关联闭环（基于跨企业图谱）──
    groups = _related_groups(cross_enterprise)
    indirect_amount = 0.0
    indirect_detail = []
    for g in groups:
        # 组内（排除已计入直接闭环的成员，避免重复）
        grp_recv = sum(recv.get(m, 0.0) for m in g if m not in direct_parties)
        grp_paid = sum(paid.get(m, 0.0) for m in g if m not in direct_parties)
        if grp_recv > 0 and grp_paid > 0:
            _gok, _gtier, _gasym = _loop_tier(grp_recv, grp_paid)
            if not _gok:
                members_a = "、".join(sorted(g)[:4])
                if len(asym_parties) < 10:
                    asym_parties.append(f"关联组[{members_a}]：收{grp_recv:,.2f}/付{grp_paid:,.2f}"
                                        f"（对称度{_gasym:.0%}，{_gtier}）")
                continue
            loop = min(grp_recv, grp_paid)
            indirect_amount += loop
            members = "、".join(sorted(g)[:4])
            if len(indirect_detail) < 10:
                indirect_detail.append(f"关联组[{members}]：企业收{grp_recv:,.2f}/付{grp_paid:,.2f}"
                                       f"（闭环{loop:,.2f}，{_gtier}）")

    circular_amount = direct_amount + indirect_amount

    # ── 信号与结论 ──
    signals = []
    sev_high = False
    sev_mid = False

    if direct_amount > 0:
        sev_high = True
        signals.append({
            "signal": f"直接资金回流闭环约{direct_amount:,.2f}元（{len(direct_parties)}个对手方互有收付）",
            "hint": ("其中等额双向（疑似过账/代收代付）%d 个、近似双向（可能含部分回流）%d 个；"
                     "结合合同与货物流转核实业务真实性。" % (tight_n, loose_n))
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

    # ★ P1-2：不对称·单侧往来**单列**为观察项（不计入闭环金额，避免"单侧往来被写成回流闭环"）
    if asym_parties:
        signals.append({
            "signal": "另见 %d 个对手方互有收付但**金额悬殊**，不构成回流闭环（按普通资金往来列示）"
                      % len(asym_parties),
            "hint": "单侧收付远大于另一侧时，属正常业务往来特征，不宜按回流认定；"
                    "如另有合同缺失、货物流无对应等情形，另行判断。样例："
                    + "；".join(asym_parties[:3]),
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
        "even_two_way_parties": tight_n,          # 等额双向（疑似过账）
        "near_two_way_parties": loose_n,          # 近似双向
        "asymmetric_parties": len(asym_parties),  # 不对称·单侧往来（不计入闭环）
        "related_groups": len(groups),
    }

    lines = []
    lines.append(f"资金回流闭环合计：{circular_amount:,.2f}元"
                 f"（口径：仅计入收付金额相近的等额/近似双向；金额悬殊的单侧往来不计入）")
    if direct_amount > 0:
        lines.append(f"直接闭环：{direct_amount:,.2f}元（{len(direct_parties)}个对手方；"
                     f"等额双向{tight_n}个、近似双向{loose_n}个）")
        for d in direct_detail[:6]:
            lines.append(f"  - {d}")
    if indirect_amount > 0:
        lines.append(f"三角/关联闭环：{indirect_amount:,.2f}元（{len(groups)}个关联组）")
        for d in indirect_detail[:6]:
            lines.append(f"  - {d}")
    if asym_parties:
        lines.append(f"不计入闭环的单侧往来：{len(asym_parties)}个对手方（互有收付但金额悬殊）")
        for d in asym_parties[:6]:
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
