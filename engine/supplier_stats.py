# -*- coding: utf-8 -*-
"""供应商集中度与地域分布的**唯一权威**（2026-10-03）

═══════════════════════════════════════════════════════════════════════════════
为什么必须收敛（真实事故：一个量纲错误让"任何企业"都触发"供应商高度集中"）
═══════════════════════════════════════════════════════════════════════════════
用户质询：「疑点24 供应商集中度与地域分布缺乏商业合理性……你也必须充分证据证明
到底是怎么缺乏商业合理性！！！！」

实测公司1（真账套）：进项 1014 张票 / **374 家供应商** / CR1=11.67% / CR3=33.45% /
本省广东 143 家 —— 这是**极其分散**。可报告却写「供应商**高度集中**」。

根因有两条，都在"同一概念三处各算一份"上：
  A. **量纲不一致**：`phase1_triage` 写入 `ctx.supplier_concentration = top3_pct`（**百分数**，33.45），
     而 `external_check_reminder` 用 `conc >= 0.6`（**小数阈值**）比较 ⇒ `33.45 >= 0.6` **恒真**
     ⇒ **任何企业都会命中"供应商高度集中"**（与阈值高低无关，是量纲错）。
  B. **三套口径**：`phase1_triage`（按行累加、不去重、无平台剔除）、
     `external_check_reminder`（按行累加、只取 seller）、
     `domain_analysis`（有 `[:3]` 切片 + 剔除平台/全国性服务商 + 家数下限 8）。
     一票多行时按行加总会**放大"行数多的供应商"**的占比；不剔平台会让"京东/电信"顶到前几名。

本模块给出**一套**口径，`ctx.supplier_concentration` 只作为它的缓存载体（单位＝百分数）。

★★ 2026-10-03（用户质询："什么是供应商？取得的发票中，哪些才是供应商？与主营业务成本
  相关的是供应商，还是期间费用相关的也是供应商？"）
  **答：票流上的"销方"≠"供应商"。** 取得发票的对方都是上游单位，但"供应商"在**采购来源
  真实性分析**里的含义是"提供生产经营投入的交易对手"，按 `account_classifier` 三态分：
    · 外购商品/原材料/委托加工/与项目收入直接配比的外购服务 ⇒ **是供应商**（集中度、地域、
      货物流佐证才有商业含义）；
    · 差旅/住宿/办公/水电/租金/电信/审计/法律/京东淘宝等**期间费用类对手方** ⇒ **不是供应商**
      （"机票都从同一家航司买"不构成异常；RL-PTY-002 要件⑥自己也写明"电商平台或全国性服务商
      …不代表采购产地异常（已剔除）"）；
    · 判不出性质的（待核）⇒ **不得当作供应商用于指控**。
  ⇒ **集中度的分母只能是"成本类采购"，不是"全部进项"**（实测公司1 的进项 100% 是服务费类）。

口径（对任何行业、任何企业一致）：
  1. **按发票号去重**（进项发票是"一票多行"，按行加总等于把同一张票重复计入）；
  2. **剔除平台/全国性服务商**（京东/淘宝/电信/电网等，其占比高低与采购来源真实性无关）；
  3. **家数下限**：真实供应商 < `MIN_SUPPLIERS` 时**不给集中度结论**
     （仅 3~5 家时前三大天然接近 100%，不当然构成集中）；
  4. 输出 CR1/CR3/CR5、供应商家数、**异省占比**（以本省为基准）与地域分布。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

from engine.numparse import to_number

#: 真实供应商家数下限（低于此值不给集中度结论——家数太少时 CR3 天然接近 100%）
MIN_SUPPLIERS = 8
#: 集中度预警阈值（**百分数**，与 phase1_triage 的行业自适应阈值同量纲）
DEFAULT_WARN_PCT = 80.0
#: 成本类采购占全部进项的最低比例：低于此值视为"本企业无实质性供应商采购"（服务业常见）
COST_MATERIALITY_PCT = 20.0


def _seller(inv: Any) -> str:
    from engine.fieldkit import seller_name
    return str(seller_name(inv) or "").strip()


def _is_platform(name: str) -> bool:
    try:
        from engine.verified_rule_engine import _is_platform_operator
        return bool(_is_platform_operator(name))
    except Exception:
        kws = ("京东", "淘宝", "天猫", "拼多多", "电信", "移动", "联通", "电网", "支付宝", "腾讯")
        return any(k in str(name or "") for k in kws)


def _province(name: str) -> Optional[str]:
    try:
        from engine.geo_infer import infer_province
        return infer_province(name)
    except Exception:
        return None


def supplier_amounts(pur_invs: Sequence[Any], *, dedup: bool = True) -> Dict[str, float]:
    """按供应商归集采购额（**唯一口径**：按发票号去重，避免一票多行重复计入）。

    ★ 金额一律取**字段权威** `fieldkit.total`（不再自建 `_amount/_inv_amount` 包装：
      跨模块重名会被闸门判"同一概念两份实现"，且包装层容易与权威漂移）。
    """
    from engine.fieldkit import total as _fk_total
    if not dedup:
        out: Dict[str, float] = defaultdict(float)
        for i in (pur_invs or []):
            s = _seller(i)
            if s:
                out[s] += abs(to_number(_fk_total(i) or 0))
        return dict(out)

    from engine.fieldkit import invoice_no as _invno
    by_inv: Dict[Tuple[str, str], float] = {}
    for i in (pur_invs or []):
        s = _seller(i)
        if not s:
            continue
        no = str(_invno(i) or "").strip() or ("__row__%d" % id(i))
        amt = abs(to_number(_fk_total(i) or 0))
        k = (s, no)
        if amt > by_inv.get(k, 0.0):
            by_inv[k] = amt
    out2: Dict[str, float] = defaultdict(float)
    for (s, _no), v in by_inv.items():
        out2[s] += v
    return dict(out2)


def supplier_concentration(pur_invs: Sequence[Any], *,
                           home_province: Optional[str] = None,
                           exclude_platform: bool = True,
                           industry: Any = "",
                           cost_only: bool = True) -> Dict[str, Any]:
    """供应商集中度与地域分布统计（唯一实现）。

    返回：
      total         —— 采购总额（去重后）
      supplier_count—— 供应商家数（含平台）
      real_count    —— 真实供应商家数（剔除平台后，用于家数下限判断）
      cr1/cr3/cr5   —— 前三/前五集中度（**百分数**）
      top_names     —— 前三大供应商名
      foreign_pct   —— 异省采购占比（百分数，需 home_province）
      province      —— 地域分布 [{省, 金额, 占比, 家数}]
      verdict       —— "集中" / "分散" / "家数不足无法判断"
      note          —— 人读说明（可直接进报告，数值与措辞一致）
      warn_pct      —— 本次采用的预警阈值（百分数）
    """
    # ★ 只统计**成本类**采购（期间费用类对手方不是"供应商"，见模块头注释）
    _all_rows = list(pur_invs or [])
    _cost_rows = _all_rows
    _cost_pct: Optional[float] = None
    if cost_only:
        try:
            from engine.account_classifier import filter_cost_invoices as _fci
            _cost_rows = list(_fci(_all_rows, industry))
        except Exception:
            _cost_rows = _all_rows
        _all_amt = sum(supplier_amounts(_all_rows).values())
        _cost_amt = sum(supplier_amounts(_cost_rows).values())
        _cost_pct = round(_cost_amt / _all_amt * 100.0, 2) if _all_amt > 0 else 0.0
        if _cost_pct < COST_MATERIALITY_PCT:
            # 本企业几乎没有"外购成本类"采购（典型：服务业/纯费用结构）⇒ 不做集中度结论
            return {
                "total": round(sum(supplier_amounts(_all_rows).values()), 2),
                "cost_total": round(_cost_amt, 2), "cost_pct": _cost_pct,
                "supplier_count": len(supplier_amounts(_all_rows)),
                "real_count": 0, "cr1": 0.0, "cr3": 0.0, "cr5": 0.0,
                "top_names": [], "foreign_pct": None, "province": [],
                "verdict": "不适用",
                "warn_pct": DEFAULT_WARN_PCT,
                "note": ("本企业进项中外购成本类采购仅占 %.2f%%（低于 %.0f%% 的口径下限）："
                         "取得的发票主要是期间费用类（服务费/差旅/租金等）对手方，"
                         "不属于「供应商」分析的范畴，本项不作集中度与地域分布结论。"
                         "（集中度只在成本类采购上有商业含义；费用类对手方集中与否不构成异常。）"
                         % (_cost_pct, COST_MATERIALITY_PCT)).replace('**', ''),
            }
    sellers = supplier_amounts(_cost_rows)
    real = {n: v for n, v in sellers.items() if not (exclude_platform and _is_platform(n))} \
        if exclude_platform else dict(sellers)
    total = sum(sellers.values())
    real_total = sum(real.values())
    srt = sorted(real.items(), key=lambda kv: -kv[1])
    cr = lambda k: (sum(v for _, v in srt[:k]) / real_total * 100.0) if real_total > 0 else 0.0

    # 地域分布（以真实供应商为准）
    prov: Dict[str, Dict[str, Any]] = {}
    for n, v in real.items():
        p = _province(n) or "未知"
        d = prov.setdefault(p, {"省": p, "金额": 0.0, "家数": 0})
        d["金额"] += v
        d["家数"] += 1
    prov_list = sorted(prov.values(), key=lambda d: -d["金额"])
    for d in prov_list:
        d["占比"] = round(d["金额"] / real_total * 100.0, 2) if real_total > 0 else 0.0

    foreign_pct: Optional[float] = None
    if home_province and real_total > 0:
        # 本省判定：名称含本省名，或反推省份等于本省
        home_amt = 0.0
        for n, v in real.items():
            p = _province(n)
            if (p and p == home_province) or (home_province in str(n)):
                home_amt += v
        foreign_pct = round((real_total - home_amt) / real_total * 100.0, 2)

    verdict, note = "家数不足无法判断", ""
    if len(real) >= MIN_SUPPLIERS:
        if cr(3) >= DEFAULT_WARN_PCT:
            verdict = "集中"
            note = (f"前三大供应商占真实采购额 {cr(3):.2f}%（≥预警 {DEFAULT_WARN_PCT:.0f}%）："
                    f"采购来源集中，须结合是否独家代理/长协/集团统采判断商业合理性。")
        else:
            verdict = "分散"
            _home_n = 0
            if home_province:
                _home_n = sum(int(d["家数"]) for d in prov_list
                              if d["省"] == home_province or home_province in str(d["省"]))
            note = (f"真实供应商 {len(real)} 家，前三大合计仅占 {cr(3):.2f}%"
                    f"（最大一家 {cr(1):.2f}%），未显示集中")
            if foreign_pct is not None:
                note += (f"；地域分布覆盖 {len(prov_list)} 个省份，异省采购占 {foreign_pct:.2f}%"
                         + (f"，本省（{home_province}）供应商 {_home_n} 家" if _home_n else ""))
            note += "。集中度与地域分布不构成异常线索。"
    else:
        note = (f"真实供应商仅 {len(real)} 家（低于判断下限 {MIN_SUPPLIERS} 家）："
                f"家数过少时前三大占比天然接近 100%，**不当然构成集中**，本轮不作集中度结论。")

    return {
        "total": round(total, 2),
        "cost_total": round(real_total, 2),
        "cost_pct": _cost_pct,
        "supplier_count": len(sellers),
        "real_count": len(real),
        "cr1": round(cr(1), 2), "cr3": round(cr(3), 2), "cr5": round(cr(5), 2),
        "top_names": [n for n, _ in srt[:3]],
        "foreign_pct": foreign_pct,
        "province": prov_list,
        "verdict": verdict,
        "warn_pct": DEFAULT_WARN_PCT,
        "note": note.replace("**", ""),
    }


__all__ = [
    "MIN_SUPPLIERS",
    "COST_MATERIALITY_PCT",
    "DEFAULT_WARN_PCT",
    "supplier_amounts",
    "supplier_concentration",
]
