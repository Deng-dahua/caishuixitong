# -*- coding: utf-8 -*-
"""**阈值参数化检测器**——把 `config/rule_params.json` 里"仅登记、未接引擎"的阈值真正接上判定。

## 为什么单独一个模块
遗留项③的收口：`config/rule_params.json` 建成后，有 **3 个法定阈值只登记了值、没有检测器**
（`engine_wired=false`）：

| 参数 | 归属红线 | 原先缺什么 |
|---|---|---|
| `loss_carryforward_years`（亏损结转年限） | `RL-CIT-016` | 历年亏损台账 + 本年弥补额 |
| `dividend_iit_rate`（利息股息红利 20%） | `RL-PAY-009` | 利润分配额 × 个税代扣配比 |
| `entrusted_rd_deduction_ratio`（委托研发 80%） | `RL-SPT-024` | 委托研发实际发生额 × 申报加计基数 |

本模块给这三者各建一个**真检测器**（可从账内/申报数据复算），阈值一律走
`engine/rule_params`（**不得写死**；取不到 ⇒ **跳过判定**，绝不兜底为 0）。

## 数据前提**如实**（铁律：缺资料 ≠ 违规）
三个检测器都要求「两侧数据」齐备才判定；**只有一侧 ⇒ 静默返回**（另一侧属资料缺口，
覆盖度模块已负责列明，此处**不重复报告**、也**不按"疑似"下风险等级**）。

## 与既有模块的边界
- `engine/verified_rule_engine.py`（VR）：原子规则（阈值本轮已收敛到 `rule_params`）；
- `engine/deduction_limit_detector.py`：**税前扣除限额**家族（工会/教育/捐赠/债资比）；
- **本模块**：**非扣除限额**类的参数化判定（亏损结转 / 分红代扣 / 委托研发加计）。
三者互不重叠；新增一类阈值判定只需在 `_DETECTORS` 加一行（**不改调度逻辑**）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

#: 检测器登记表：`(函数, 归属红线)`。新增同类检测器＝在此加一行。
_DETECTORS: List[tuple] = []


def _register(redline_id: str):
    def _wrap(fn):
        _DETECTORS.append((fn, redline_id))
        return fn
    return _wrap


def _num(v) -> float:
    """数值解析（唯一权威 `engine.numparse`）。"""
    from engine.numparse import to_number
    return to_number(v)


def _rows(data: Dict[str, Any], *keys: str) -> List[Dict[str, Any]]:
    for k in keys:
        v = (data or {}).get(k)
        if isinstance(v, list):
            return [r for r in v if isinstance(r, dict)]
    return []


def _acct(row: Dict[str, Any]) -> str:
    return str(row.get("account_name") or row.get("科目") or row.get("account") or "")


def _credit(row: Dict[str, Any]) -> float:
    v = row.get("credit")
    return _num(v if v is not None else (row.get("贷方") or row.get("amount")))


def _debit(row: Dict[str, Any]) -> float:
    v = row.get("debit")
    return _num(v if v is not None else (row.get("借方") or row.get("amount")))


def _emit(redline_id: str, name: str, taxes: List[str], domain: str, detail: str,
          metrics: Dict[str, Any], sources: List[str], policy_ref: str = "",
          suggestion: str = "", constituent_hits: Optional[List[Dict[str, Any]]] = None,
          level: str = "中风险", score: int = 6) -> Dict[str, Any]:
    """构造 finding —— 走 `verified_rule_engine._rule_finding`（全系统统一底盘）。

    ★ 与批次规则（`special_redline_detectors`）用**同一底盘**：强制携带三件套
      （处置定性 / 已核实事实与待举证 / 企业权利告知），避免"贴标签"式结论。
    """
    from engine.verified_rule_engine import _rule_finding
    spec = {"id": redline_id, "name": name, "layer": "阈值参数化判定",
            "industries": ["ALL"], "taxes": taxes, "domain": domain,
            "required_sources": sources, "status": "verified_executable_screening"}
    f = _rule_finding(spec, detail, metrics, sources,
                      priority="调查优先级", level=level, score=score)
    f["redline_id"] = redline_id
    if policy_ref:
        f["policy_ref"] = policy_ref
    if suggestion:
        f["suggestion"] = suggestion
    if constituent_hits:
        f["constituent_hits"] = constituent_hits
    f["_detection_method"] = ("阈值取自 `config/rule_params.json`，经 `engine/rule_params` 读取"
                              "（**不写死**；取不到则跳过判定）")
    return f


# ══════════════════════════ RL-CIT-016 亏损弥补年限 ══════════════════════════

@_register("RL-CIT-016")
def detect_loss_carryforward(data: Dict[str, Any], ctx: Any = None) -> List[Dict[str, Any]]:
    """亏损结转年限超期仍弥补（阈值 `loss_carryforward_years`）。

    **数据前提**：需**连续年度的亏损与弥补台账**（`tax_declarations` 里企业所得税年度
    申报表的 `prior_year_losses=[{year, loss, used}]`）+ 本年度（`tax_year`）。
    ★ 台账或本年度取不到 ⇒ **静默**（不按疑似下等级）。
    """
    from engine import rule_params as RP
    years = RP.ratio("loss_carryforward_years")
    if years is None:
        return []
    limit_years = int(years)

    hist: List[Dict[str, Any]] = []
    cur_year: Optional[int] = None
    for d in _rows(data, "tax_declarations", "declaration", "declarations"):
        for x in (d.get("prior_year_losses") or []):
            if isinstance(x, dict) and x.get("year"):
                hist.append(x)
        if cur_year is None:
            for k in ("tax_year", "year", "所属年度", "申报年度"):
                if d.get(k):
                    try:
                        cur_year = int(str(d[k])[:4])
                    except (TypeError, ValueError):
                        cur_year = None
                    if cur_year:
                        break
    if not hist or not cur_year:
        return []

    expired: List[Dict[str, Any]] = []
    used_in_time = 0.0
    for x in hist:
        try:
            y = int(str(x.get("year"))[:4])
        except (TypeError, ValueError):
            continue
        used, loss = _num(x.get("used")), _num(x.get("loss"))
        if used <= 0 or loss <= 0:
            continue
        if (cur_year - y) > limit_years:
            expired.append({"loss_year": y, "amount": round(loss, 2), "used": round(used, 2),
                            "elapsed_years": cur_year - y})
        else:
            used_in_time += used
    if not expired:
        return []
    tot = sum(e["used"] for e in expired)
    det = "；".join("第%d 年亏损 %s 元于第%d 年弥补（已逾 %d 年 > 法定 %d 年）"
                   % (e["loss_year"], f"{e['amount']:,.2f}", cur_year,
                      e["elapsed_years"], limit_years) for e in expired[:5])
    return [_emit(
        "RL-CIT-016", "亏损弥补超期仍结转扣除", ["企业所得税"], "企业所得税",
        "核实到 %d 笔**超期弥补**：%s，合计弥补 %s 元。亏损结转年限不得超过 %d 年"
        "（高新技术企业与科技型中小企业另有 10 年规定，须先确认适用资格）。"
        % (len(expired), det, f"{tot:,.2f}", limit_years),
        {"carryforward_limit_years": limit_years,
         "expired_items": expired, "expired_used_total": round(tot, 2),
         "current_year": cur_year, "ledger_entries": len(hist)},
        ["tax_declarations", "vouchers"],
        policy_ref="《中华人民共和国企业所得税法》第十八条",
        suggestion="核对历年亏损台账与各年度弥补申报，超期弥补部分应作纳税调增；"
                   "若主张适用 10 年期限，须提供高新技术企业或科技型中小企业资格证明。",
        constituent_hits=[
            {"index": 1, "evidence": "归集到历年亏损台账 %d 笔、本年弥补合计 %s 元。"
                                     % (len(hist), f"{tot + used_in_time:,.2f}")},
            {"index": 2, "evidence": "其中 %d 笔的亏损年度距本年度**超过 %d 年**"
                                     "（明细见 observed_metrics.expired_items）。"
                                     % (len(expired), limit_years)},
        ])]


# ══════════════════════════ RL-PAY-009 分红代扣个税 ══════════════════════════

@_register("RL-PAY-009")
def detect_dividend_iit(data: Dict[str, Any], ctx: Any = None) -> List[Dict[str, Any]]:
    """股东分红未按规定代扣代缴个税（阈值 `dividend_iit_rate` = 20%）。

    **数据前提**：需「利润分配/应付股利**发生额**」与「**代扣个税**」**两侧**。
    ★ 只有一侧 ⇒ **静默**（另一侧属资料缺口，不重复报、不按疑似定性）。
    """
    from engine import rule_params as RP
    rate = RP.ratio("dividend_iit_rate")
    if rate is None:
        return []
    div = withheld = 0.0
    seen_div = seen_wht = False
    for v in _rows(data, "vouchers"):
        a = _acct(v)
        if any(k in a for k in ("应付股利", "应付利润", "利润分配")):
            seen_div = True
            div += _credit(v)
        if "个人所得税" in a:
            seen_wht = True
            withheld += _credit(v)
    if not (seen_div and seen_wht) or div <= 0:
        return []
    due = div * rate
    gap = due - withheld
    if gap <= max(due * 0.01, 1.0):
        return []
    return [_emit(
        "RL-PAY-009", "股东分红未按规定代扣代缴个人所得税", ["个人所得税"], "个人所得税",
        "检测到「应付股利/利润分配」贷方发生额 %s 元，按「利息、股息、红利所得」**%d%%** "
        "税率应代扣个税 %s 元，实际归集「应交个人所得税」贷方 %s 元，**差额 %s 元**"
        "未代扣（或未足额）。"
        % (f"{div:,.2f}", int(rate * 100), f"{due:,.2f}", f"{withheld:,.2f}", f"{gap:,.2f}"),
        {"dividend_iit_rate": rate,
         "dividend_payable": round(div, 2), "iit_withheld": round(withheld, 2),
         "iit_should_withhold": round(due, 2), "shortfall": round(gap, 2)},
        ["vouchers", "tax_declarations"],
        policy_ref="《中华人民共和国个人所得税法》第三条（利息、股息、红利所得适用 20% 比例税率）",
        suggestion="核实股东会分红决议、支付对象（自然人股东）与金额，补办代扣代缴申报并缴纳"
                   "滞纳金；对已支付未扣缴的，依《税收征收管理法》第六十九条处理。",
        constituent_hits=[
            {"index": 1, "evidence": "归集到「应付股利/利润分配」贷方发生额 %s 元。" % f"{div:,.2f}"},
            {"index": 2, "evidence": "「应交个人所得税」贷方 %s 元，低于应代扣额 %s 元的 99%% "
                                     "⇒ 代扣义务未履行或未足额。"
                                     % (f"{withheld:,.2f}", f"{due:,.2f}")},
        ])]


# ══════════════════════════ RL-SPT-024 委托研发加计基数 ══════════════════════════

@_register("RL-SPT-024")
def detect_entrusted_rd_base(data: Dict[str, Any], ctx: Any = None) -> List[Dict[str, Any]]:
    """委托研发加计扣除基数或比例错误（阈值 `entrusted_rd_deduction_ratio` = 80%）。

    **数据前提**：需「委托研发实际发生额」（凭证）与「申报加计基数」（申报表）**两侧**。
    ★ 单侧缺失 ⇒ **静默**。
    """
    from engine import rule_params as RP
    ratio = RP.ratio("entrusted_rd_deduction_ratio")
    if ratio is None:
        return []
    actual = 0.0
    seen = False
    for v in _rows(data, "vouchers"):
        a = _acct(v)
        if ("委托研发" in a) or ("委托外部" in a and "研发" in a):
            seen = True
            actual += _debit(v)
    declared: Optional[float] = None
    for d in _rows(data, "tax_declarations", "declaration", "declarations"):
        for k in ("entrusted_rd_base", "委托研发基数", "委托境外研发基数"):
            if d.get(k) is not None:
                declared = _num(d.get(k))
                break
        if declared is not None:
            break
    if not seen or actual <= 0 or declared is None:
        return []
    cap = actual * ratio
    if declared <= cap + max(cap * 0.005, 1.0):
        return []
    return [_emit(
        "RL-SPT-024", "委托研发加计扣除基数或比例错误", ["企业所得税"], "企业所得税",
        "委托研发实际发生额 %s 元，按**%d%%** 计入委托方研发费用的上限为 %s 元，"
        "而申报的加计扣除基数为 %s 元，**超出 %s 元**（委托境内研发按实际发生额的 80%% 计入；"
        "委托境外研发另有不超过境内符合条件研发费用三分之二的上限）。"
        % (f"{actual:,.2f}", int(ratio * 100), f"{cap:,.2f}", f"{declared:,.2f}",
           f"{declared - cap:,.2f}"),
        {"entrusted_rd_deduction_ratio": ratio,
         "entrusted_rd_actual": round(actual, 2), "eligible_base_cap": round(cap, 2),
         "declared_base": round(declared, 2), "excess": round(declared - cap, 2)},
        ["vouchers", "tax_declarations"],
        policy_ref="《财政部 国家税务总局 科学技术部关于完善研究开发费用税前加计扣除政策的通知》"
                   "（财税〔2015〕119号）",
        suggestion="核对委托研发合同与技术合同登记证明，按实际发生额的 80% 重新计算基数；"
                   "受托方已就该项目加计的，不得重复加计。",
        constituent_hits=[
            {"index": 1, "evidence": "归集到委托研发实际发生额 %s 元，并取得申报加计基数 %s 元。"
                                     % (f"{actual:,.2f}", f"{declared:,.2f}")},
            {"index": 2, "evidence": "申报基数超出「实际发生额 × %d%%」上限 %s 元 ⇒ 比例适用错误。"
                                     % (int(ratio * 100), f"{declared - cap:,.2f}")},
        ])]


# ══════════════════════════ 统一入口 ══════════════════════════

def detect_params_wired(data: Dict[str, Any], ctx: Any = None) -> List[Dict[str, Any]]:
    """主入口：跑全部"阈值参数化"检测器。

    ★ **逐检测器隔离**：任一检测器抛异常**不影响其余**，且异常**必须留痕**
      （项目铁律：域分析必须有容错护栏；异常绝不静默）。
    """
    out: List[Dict[str, Any]] = []
    errors: List[str] = []
    for fn, rid in _DETECTORS:
        try:
            got = fn(data or {}, ctx) or []
            for f in got:
                if isinstance(f, dict):
                    f.setdefault("redline_id", rid)
            out.extend([f for f in got if isinstance(f, dict)])
        except Exception as exc:                              # noqa: BLE001
            errors.append("%s(%s): %s: %s" % (getattr(fn, "__name__", "?"), rid,
                                              type(exc).__name__, str(exc)[:120]))
    if errors:
        print("[params_wired] ⚠ 检测器异常（已隔离，不影响其余）：" + "；".join(errors))
    return out


def wired_params() -> List[str]:
    """本模块**实际接线**的阈值参数名（供闸门核对 `engine_wired` 声明与实现一致）。"""
    from engine import rule_params as RP
    return [n for n in ("loss_carryforward_years", "dividend_iit_rate",
                        "entrusted_rd_deduction_ratio") if RP.entry(n)]


__all__ = ["detect_params_wired", "detect_loss_carryforward", "detect_dividend_iit",
           "detect_entrusted_rd_base", "wired_params"]
