# -*- coding: utf-8 -*-
"""法定增值税征收率/税率表与「含税—不含税」口径换算（唯一权威）

═══════════════════════════════════════════════════════════════════════════════
为什么需要这一层
═══════════════════════════════════════════════════════════════════════════════
同一个金额在不同资料里是**两种口径**：序时账/凭证记的是**不含税**收入与成本，
而发票（价税合计）是**含税**金额。把两者直接相减，差额会被读成"少计收入/少计成本"，
实际只是口径不同。实测（公司1 真账套）：

    账载主营业务收入（不含税） 6,636,800.57 元
    ×1.06（6% 税率）        = 7,035,008.60 元
    销项发票价税合计          = 7,035,008.58 元   → 差异 0.02 元（口径吻合）

若不换算，就会得出"账上 663.7 万、开票 703.5 万，差 39.8 万"的假差额。

原实现把这套税率表写在 `engine/monthly_reconcile.py`（`_CANON_RATES`）里，
只管"税价配比"一条勾稽链；现抽为唯一权威，`monthly_reconcile` 反过来引用本表
（薄转发，行为不变），其它需要口径换算的模块一律用本模块的 `match_tax_inclusive`。
"""

from __future__ import annotations

from typing import Dict, Optional, Sequence, Tuple

#: 常见增值税征收率/税率（不含税口径）
CANON_RATES: Tuple[float, ...] = (0.01, 0.03, 0.05, 0.06, 0.09, 0.13)
#: 其含税等价率（税额÷含税金额 = c/(1+c)），用于"按含税金额入账"的判据
CANON_RATES_INCL: Tuple[float, ...] = tuple(round(c / (1 + c), 4) for c in CANON_RATES)
#: 判定容差（1.5 个百分点）
RATE_TOL: float = 0.015


def to_inclusive(amount: float, rate: float) -> float:
    """不含税金额 → 含税金额。"""
    return float(amount) * (1.0 + float(rate))


def to_exclusive(amount: float, rate: float) -> float:
    """含税金额 → 不含税金额。"""
    return float(amount) / (1.0 + float(rate))


def implied_rate(base: float, target: float) -> Optional[float]:
    """隐含率 = target/base - 1（base 为不含税口径时即税额占不含税额之比）。"""
    b = float(base or 0.0)
    if b <= 0:
        return None
    return float(target or 0.0) / b - 1.0


def match_tax_inclusive(base: float, target: float, tol: float = RATE_TOL) -> Dict[str, object]:
    """判断两个金额是否只是「含税/不含税」口径不同（同一经济事项）。

    返回 dict：
      matched    —— 是否命中法定税率之一（含 0，即两方同为一种口径）
      rate       —— 命中的税率（0 表示口径相同）
      converted  —— 把 base 按其不含税口径换算成含税后的金额
      diff       —— converted - target（元）
      note       —— 人读说明（可直接进报告）
    """
    b, t = float(base or 0.0), float(target or 0.0)
    out: Dict[str, object] = {
        "matched": False, "rate": None, "converted": b, "diff": None, "note": ""
    }
    if b <= 0 or t <= 0:
        return out
    r = implied_rate(b, t)
    if r is None:
        return out
    # 容差按"隐含率"给：取**最接近**的法定率（不能取"第一个落入容差"的 ——
    # 实测 6% 会被相邻的 5% 抢先命中：|0.06-0.05| = 0.01 ≤ 0.015）
    cands: Sequence[float] = (0.0,) + tuple(CANON_RATES)
    best = min(cands, key=lambda c: abs(r - c))
    if abs(r - best) > tol:
        out["note"] = "隐含率 %.2f%% 与法定征收率/税率均不相符，不能按口径差解释。" % (r * 100)
        return out
    conv = to_inclusive(b, best)
    if best == 0:
        note = "两者口径相同（均不含税）：%s 元 与 %s 元一致。" % (
            format(b, ",.2f"), format(t, ",.2f"))
    else:
        note = (
            "两者仅口径不同（不含税 × (1+%g%%)）：%s 元换算为含税 %s 元，"
            "与 %s 元相差 %s 元。" % (
                best * 100, format(b, ",.2f"), format(conv, ",.2f"),
                format(t, ",.2f"), format(conv - t, ",.2f"))
        )
    out.update(
        matched=True,
        rate=best,
        converted=round(conv, 2),
        diff=round(conv - t, 2),
        note=note,
    )
    return out


__all__ = [
    "CANON_RATES",
    "CANON_RATES_INCL",
    "RATE_TOL",
    "to_inclusive",
    "to_exclusive",
    "implied_rate",
    "match_tax_inclusive",
]
