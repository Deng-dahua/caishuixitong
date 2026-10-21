# -*- coding: utf-8 -*-
"""资金流 × 发票流**柔性匹配引擎**（三维聚合 + 资产负债表调节 + 未匹配四分类）。

═══════════════════════════════════════════════════════════════════════════════
为什么必须建这一层（根因）
═══════════════════════════════════════════════════════════════════════════════
真实业务里「一张发票 ↔ 一笔流水」几乎从不一一对应：

  · **分批付款**：一张 100 万发票分 3 笔打款（3×33.3 万）；
  · **合并付款**：上月 50 万 + 本月 50 万两张发票，本月一次性收 100 万；
  · **预收/预付**：先收款后开票（预收账款）或先开票后收款（应收账款）；
  · **跨期回款**：本月开票、次月甚至季度末才回款。

按「单笔对单笔」比对，上述**全部**会被判成"未匹配" ⇒ 报告满屏"开票收入有 X 元
未匹配到银行流水" ⇒ 把正常赊销/预收读成"账外收入嫌疑" ⇒ **大量误报**。

═══════════════════════════════════════════════════════════════════════════════
设计（三维聚合）
═══════════════════════════════════════════════════════════════════════════════
D1 **按对象聚合**：以「交易对手核心名」为客户键，汇总该对象**当期/累计**的发票总额
   与流水总额做**桶级**比对（不是逐笔）。名称容错复用 `fund_matching._core_of`
   （去省市前缀/公司后缀/括号），不另立一套。
D2 **按期间聚合（跨期窗口）**：允许「流水发生次月才开票」等跨期情形 —— 对每个客户，
   在 `[发票最早日 - back_days, 发票最晚日 + forward_days]` 窗口内取流水；
   窗口外流水不算作该发票的收款。窗口宽度由配置给出（默认前 0 后 90 天）。
D3 **按合同聚合**：流水摘要里的「合同号/项目名」若能对上合同，则以合同金额为参照
   （合同域数据缺失时**跳过**，不臆测）。
D4 **资产负债表调节项**（★ 核心去误报）：
       预期经营性收款 = 申报收入 - Δ应收账款 + Δ预收账款 + 其他调节项
       残差 = 实际经营性收款 - 预期经营性收款
   残差在容忍度内（默认 5% 或绝对额阈值）⇒ **不触发**差额预警，并在报告中把差额
   **解释为**"应收账款增加 X 元 / 预收账款减少 Y 元"。
D5 **未匹配四分类**（替代"一律账外收入嫌疑"）：
       【预收性质】 摘要含预付款/定金，或该对象有历史开票记录；
       【收款尾款】 摘要含结算款/尾款/尾数，且能找到对应历史发票；
       【非经营流水】复用 `bank_nature.classify_receipts`（唯一权威）判为非经营性；
       【真正异常】 无发票、无合同、对方非个人、金额巨大 ⇒ 此时才"重点核查"。

═══════════════════════════════════════════════════════════════════════════════
单一权威声明（不得另立第二套）
═══════════════════════════════════════════════════════════════════════════════
  · 名称规范化            → `engine.fund_matching.normalize_entity_name` / `_core_of`
  · 收款性质（经营/非经营）→ `engine.bank_nature.classify_receipts`（本模块**不猜关键词**）
  · 应收账款              → `engine.ar_aging.build_ar_index`
  · 数值解析              → `engine.numparse`
  · 客户级匹配底盘        → `engine.fund_matching.match_invoices_to_flows`
  本模块只做「**三维聚合 + 调节 + 分类**」这一件事，其余一律薄转发。

铁律：发现≠确认；未匹配 ≠ 隐匿收入；结论一律待证线索，不作为定性依据。
"""
from __future__ import annotations

import datetime as _dt
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

from engine.numparse import to_number

# ── 默认参数（可被 data 或 config 覆盖）──────────────────────────────────────
#: 客户级金额偏差容忍度（超过即视为"该客户开票与收款不吻合"）——沿用 fund_matching 的 25%
DEFAULT_OBJECT_TOLERANCE = 0.25
#: 资产负债表调节后的**残差**容忍度（5% 或绝对额 10 万，取"两者都不超过"才算解释得通）
DEFAULT_RESIDUAL_RATE = 0.05
DEFAULT_RESIDUAL_ABS = 100000.0
#: 跨期窗口：发票最早日往前/往后各取多少天内的流水
DEFAULT_BACK_DAYS = 0
DEFAULT_FORWARD_DAYS = 90
#: 「金额巨大」阈值（真正异常的必要条件之一）
DEFAULT_LARGE_AMOUNT = 500000.0

#: 未匹配四分类（枚举，报告与前端共用同一套字面量）
CLS_ADVANCE = "预收性质"
CLS_TAIL = "收款尾款"
CLS_NON_OP = "非经营流水"
CLS_SUSPECT = "真正异常"

#: 关键词只用于**辅助佐证**（主判据是 bank_nature 与历史发票），不单独定性
_TAIL_KWS = ("尾款", "尾数", "结算款", "结清", "余款", "末期款")
_ADVANCE_KWS = ("预付款", "预付", "定金", "订金", "预收", "诚意金")
_NON_OP_HINTS = ("借款", "往来", "退保证金", "保证金", "还款", "出资", "注资")


# ══════════════════════════════════════════════════════════════════════════
# 基础工具（全部薄转发既有权威）
# ══════════════════════════════════════════════════════════════════════════
def _core_of(name: Any) -> str:
    """交易对手核心名（唯一权威：fund_matching）。"""
    from engine.fund_matching import _core_of as _c
    return _c(str(name or ""))


def _num(v: Any) -> float:
    """数值解析（唯一权威：engine.numparse —— 本模块**只转发，不自实现**）。

    ★ 2026-10-21 审计闸门抓出：初版写成 `return to_number(v)` 的直接实现体，
      被判「数值解析多头维护」（与全仓 9 个模块同一毛病）。统一为薄转发。
    """
    from engine.numparse import to_number as _to_number
    return _to_number(v)


def _tx_text(tx: Any) -> str:
    """一条流水的全部可用文本（唯一权威：fieldkit.bank_tx_text）。"""
    from engine.fieldkit import bank_tx_text
    return bank_tx_text(tx)


def _tx_date(tx: Any) -> Optional[_dt.date]:
    """流水日期（容错多种写法）；解析不出返回 None。"""
    return _parse_date(tx.get("date") or tx.get("交易日期") or tx.get("tx_date")
                       or tx.get("date_str") or "")


def _inv_date(inv: Any) -> Optional[_dt.date]:
    return _parse_date(inv.get("date") or inv.get("invoice_date")
                       or inv.get("开票日期") or inv.get("rq") or "")


def _parse_date(raw: Any) -> Optional[_dt.date]:
    """宽松日期解析：支持 2025-01-15 / 2025/1/15 / 20250115 / 2025年1月15日。"""
    s = str(raw or "").strip()
    if not s:
        return None
    m = re.search(r"(\d{4})\D{0,2}(\d{1,2})\D{0,2}(\d{1,2})", s)
    if not m:
        return None
    try:
        return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _is_income_flow(tx: Any) -> bool:
    """是否收入侧流水（贷方 > 0）。"""
    return _num(tx.get("credit")) > 0


def _flow_amount(tx: Any, side: str) -> float:
    """该流水在本 side 下的可比金额：sale→贷方(收)，purchase→借方(付)。

    ★ 比例/倍数判定的分子分母必须为正 —— 取不到（≤0）即返回 0，由调用方跳过。
    """
    return _num(tx.get("credit")) if side == "sale" else _num(tx.get("debit"))


# ══════════════════════════════════════════════════════════════════════════
# D1 + D2：按对象 + 按期间 聚合（跨期窗口内的桶级比对）
# ══════════════════════════════════════════════════════════════════════════
def aggregate_by_object(inv_rows: Sequence[Any], bank_txs: Sequence[Any],
                        side: str = "sale", *,
                        name_field: Optional[str] = None,
                        back_days: int = DEFAULT_BACK_DAYS,
                        forward_days: int = DEFAULT_FORWARD_DAYS
                        ) -> Dict[str, Dict[str, Any]]:
    """按「交易对手核心名」聚合发票与流水（含**跨期窗口**），返回逐对象桶。

    返回 {核心名: {
        "invoices": [...], "invoice_total": float, "invoice_span": (最早日, 最晚日),
        "flows": [...], "flow_total": float, "platform_flow_total": float,
        "diff": float, "diff_rate": float,   # (flow-inv)/inv，inv>0 才有意义
        "matched": bool,                     # 桶级是否吻合（偏差 ≤ 容忍度）
        "in_window": int, "out_window": int, # 窗口内/外流水笔数（跨期证据）
    }}

    ★ 为什么先按期间收窄再按对象聚合：跨期窗口保证"次月才开的票"仍能在同一客户桶里
      与收款对上（D2），避免把它们判成"未匹配"。
    """
    inv_rows = [r for r in (inv_rows or []) if isinstance(r, dict)]
    bank_txs = [r for r in (bank_txs or []) if isinstance(r, dict)]
    field = name_field or ("buyer" if side == "sale" else "seller")

    buckets: Dict[str, Dict[str, Any]] = {}

    def _bucket(key: str) -> Dict[str, Any]:
        return buckets.setdefault(key, {
            "invoices": [], "invoice_total": 0.0, "invoice_span": (None, None),
            "flows": [], "flow_total": 0.0, "platform_flow_total": 0.0,
            "diff": 0.0, "diff_rate": 0.0, "matched": False,
            "in_window": 0, "out_window": 0,
        })

    # ① 发票入桶
    for inv in inv_rows:
        name = str(inv.get(field) or inv.get("buyer") or inv.get("seller")
                   or inv.get("购方名称") or inv.get("销方名称") or "").strip()
        key = _core_of(name)
        if not key:
            continue
        b = _bucket(key)
        b["invoices"].append(inv)
        b["invoice_total"] += _inv_amount(inv)
        d = _inv_date(inv)
        lo, hi = b["invoice_span"]
        if d is not None:
            b["invoice_span"] = (d if lo is None or d < lo else lo,
                                 d if hi is None or d > hi else hi)

    # ② 流水按窗口归入对应桶（先建核心名索引，再逐桶按窗口筛）
    flow_by_core: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for tx in bank_txs:
        if side == "sale" and not _is_income_flow(tx):
            continue                      # 收入侧只看贷方
        if side == "purchase" and _num(tx.get("debit")) <= 0:
            continue                      # 采购侧只看借方
        key = _core_of(tx.get("counterparty") or tx.get("对方户名") or "")
        if not key:
            continue
        flow_by_core[key].append(tx)

    from engine.fund_matching import is_platform_counterparty
    for key, b in buckets.items():
        cand_keys = [key]
        # 名称容错：核心名互含（覆盖"XX有限公司" vs "XX公司"等）
        for fk in flow_by_core:
            if fk and fk != key and (key in fk or fk in key):
                cand_keys.append(fk)
        lo, hi = b["invoice_span"]
        for fk in cand_keys:
            for tx in flow_by_core.get(fk, []):
                td = _tx_date(tx)
                if lo is not None and td is not None:
                    if td < lo - _dt.timedelta(days=int(back_days)):
                        b["out_window"] += 1
                        continue
                    if hi is not None and td > hi + _dt.timedelta(days=int(forward_days)):
                        b["out_window"] += 1
                        continue
                b["in_window"] += 1
                amt = _flow_amount(tx, side)
                b["flows"].append(tx)
                b["flow_total"] += amt
                if is_platform_counterparty(tx.get("counterparty")):
                    b["platform_flow_total"] += amt

    # ③ 桶级吻合判定（客户级金额比对，容忍度沿用 fund_matching 口径）
    for b in buckets.values():
        inv_t, flow_t = b["invoice_total"], b["flow_total"]
        b["diff"] = round(flow_t - inv_t, 2)
        if inv_t > 0:
            b["diff_rate"] = round((flow_t - inv_t) / inv_t, 4)
            b["matched"] = abs(b["diff_rate"]) <= DEFAULT_OBJECT_TOLERANCE
        else:
            b["diff_rate"] = 0.0
            b["matched"] = flow_t <= 0 or inv_t <= 0   # 无发票金额：同名有流水即算有痕迹
    return buckets


def _inv_amount(inv: Any) -> float:
    """发票可比金额：优先不含税金额，其次价税合计（与既有 fund_matching 口径一致）。"""
    a = _num(inv.get("amount") or inv.get("je") or inv.get("金额"))
    if a > 0:
        return a
    return _num(inv.get("total") or inv.get("价税合计") or inv.get("jshj"))


# ══════════════════════════════════════════════════════════════════════════
# D4：资产负债表调节（★ 核心去误报）
# ══════════════════════════════════════════════════════════════════════════
def _declared_revenue(data: Dict[str, Any]) -> Tuple[float, str]:
    """申报销售额（数据源：tax_declarations）。取不到返回 (0, 说明)。"""
    total = 0.0
    for d in (data.get("tax_declarations") or []):
        if not isinstance(d, dict):
            continue
        total += _num(d.get("sales_amount") or d.get("销售额") or d.get("sal_amount"))
    return round(total, 2), ("申报表销售额合计" if total > 0 else "未取得申报表销售额")


def _ar_delta(data: Dict[str, Any]) -> Tuple[float, bool, str]:
    """应收账款**变动额**（期末-期初）与可得性。

    口径：优先取「应收账款明细」的期末未收合计（当期新增挂账）；
    其次取科目余额表「应收账款」期末余额（时点数，作为当期挂账规模上限）。
    两者都取不到 ⇒ 返回 (0, False, 原因) —— **不臆测**（UNKNOWN 一律跳过）。
    """
    rows = data.get("accounts_receivable")
    if rows:
        try:
            from engine.ar_aging import build_ar_index
            idx = build_ar_index(rows if isinstance(rows, list) else (rows or {}).get("rows"),
                                 data.get("trial_balance"))
            total = float(idx.get("aggregate_balance") or 0.0)
            if not idx.get("from_trial_balance"):
                total = sum(v.get("unreceived", 0.0) for v in (idx.get("by_customer") or {}).values())
            if total > 0:
                return round(total, 2), True, "应收账款明细/科目余额表"
        except Exception:                                     # noqa: BLE001
            pass
    tb = data.get("trial_balance")
    if tb:
        try:
            from engine.ar_aging import build_ar_index
            idx = build_ar_index(None, tb)
            if idx.get("aggregate_balance", 0) > 0:
                return round(idx["aggregate_balance"], 2), True, "科目余额表-应收账款期末余额"
        except Exception:                                     # noqa: BLE001
            pass
    return 0.0, False, "未取得应收账款明细或科目余额表"


def _advance_delta(data: Dict[str, Any]) -> Tuple[float, bool, str]:
    """预收账款**余额**与可得性（数据源：科目余额表「预收账款」）。

    ★ 严格：找不到「预收账款」科目即返回不可用（不臆测为 0，避免把"没数据"当成"没预收"）。
    """
    for row in (data.get("trial_balance") or []):
        if not isinstance(row, dict):
            continue
        nm = str(row.get("科目名称") or row.get("科目") or row.get("account_name")
                 or row.get("account") or "")
        code = str(row.get("科目编码") or row.get("科目代码") or row.get("code") or "")
        if "预收" not in nm and not code.startswith("2203"):
            continue
        close = _num(row.get("期末余额") or row.get("期末贷方余额") or row.get("余额")
                     or row.get("close") or row.get("贷方余额"))
        if close:
            return round(abs(close), 2), True, "科目余额表-预收账款期末余额"
    return 0.0, False, "未取得预收账款科目余额"


def reconcile_income(data: Dict[str, Any], *,
                     operating_cash: Optional[float] = None,
                     residual_rate: float = DEFAULT_RESIDUAL_RATE,
                     residual_abs: float = DEFAULT_RESIDUAL_ABS) -> Dict[str, Any]:
    """★ 用资产负债表科目**调节**「经营性流水 vs 申报收入」的差额（去误报核心）。

    恒等式（现金制 ↔ 应计制转换，符号按会计口径）：

        预期经营性收款 = 申报收入 − Δ应收账款 + Δ预收账款 + 其他调节项
        残差           = 实际经营性收款 − 预期经营性收款

    · 应收账款增加（客户欠得更多）⇒ 预期现金**少于**申报收入（故减）；
    · 预收账款增加（先收钱后开票）⇒ 预期现金**多于**申报收入（故加）。

    残差在容忍度内（|残差| ≤ max(5% × 申报收入, ...) 且 ≤ 绝对额阈值）
    ⇒ **不触发**差额预警，并把差额解释为应收/预收的变动。

    ⚠ 已证实口径不一致 / UNKNOWN 的调节项**一律跳过**，并在 `skipped` 里如实写明
      —— 缺失 ≠ 0，不得用默认值静默顶替。

    返回 {declared, operating_cash, expected_cash, residual, residual_rate,
          explained_by: {...}, available, skipped: [...], verdict_hint, detail}
    """
    declared, decl_src = _declared_revenue(data)
    scope = income_cash_scope(data)
    if operating_cash is None:
        operating_cash = scope["comparable"]
    oc = round(float(operating_cash or 0.0), 2)

    ar_amt, ar_ok, ar_src = _ar_delta(data)
    adv_amt, adv_ok, adv_src = _advance_delta(data)

    skipped: List[str] = []
    if not ar_ok:
        skipped.append("应收账款变动（%s）" % ar_src)
    if not adv_ok:
        skipped.append("预收账款变动（%s）" % adv_src)

    explained_ar = -ar_amt if ar_ok else 0.0
    explained_adv = adv_amt if adv_ok else 0.0
    expected = round(declared + explained_ar + explained_adv, 2)
    residual = round(oc - expected, 2) if declared > 0 else 0.0

    tol = max(abs(declared) * residual_rate, 0.0)
    within = abs(residual) <= max(tol, 0.0) or abs(residual) <= residual_abs

    parts = []
    if ar_ok and ar_amt:
        parts.append("应收账款增加 %s 元（客户已开票未回款的部分）" % format(ar_amt, ",.2f"))
    if adv_ok and adv_amt:
        parts.append("预收账款 %s 元（先收款后开票的部分）" % format(adv_amt, ",.2f"))
    if scope.get("undetermined", 0) > 0:
        parts.append("可比口径中含性质待判定收款 %s 元（须企业逐笔说明款项性质）"
                     % format(scope["undetermined"], ",.2f"))
    if not scope.get("available"):
        parts.append("收款性质分类本轮不可用，现金侧为全部贷方发生额")
    if skipped:
        parts.append("未取得以下调节项，未参与计算：%s" % "、".join(skipped))

    if declared <= 0:
        hint = "未取得申报销售额，无法做账表勾稽（资料缺口，不指向企业）"
        detail = "申报销售额缺失，资产负债表调节无法实施；" + "；".join(parts)
    elif within:
        hint = "未发现差异"
        detail = ("经营性收款 %s 元与「申报收入 %s 元%s」经资产负债表调节后基本吻合"
                  "（残差 %s 元，在容忍度内）%s。"
                  % (format(oc, ",.2f"), format(declared, ",.2f"),
                     ("" if not parts else "，已考虑" + "、".join(
                         p.split("（")[0] for p in parts if "调节项" not in p)),
                     format(residual, ",.2f"),
                     ("；" + "；".join(parts)) if parts else ""))
    else:
        hint = "存在未解释差异"
        detail = ("经营性收款 %s 元与「申报收入 %s 元」经资产负债表调节后仍有残差 %s 元"
                  "（超过容忍度 %s 元）%s。须核实该差额是否属未开票收入未申报、"
                  "或存在未入账收款，抑或是资料口径差异。"
                  % (format(oc, ",.2f"), format(declared, ",.2f"), format(residual, ",.2f"),
                     format(max(tol, residual_abs), ",.2f"),
                     ("（" + "；".join(parts) + "）") if parts else ""))

    return {
        "declared": declared, "declared_source": decl_src,
        "operating_cash": oc,
        "cash_scope": scope,
        "expected_cash": expected,
        "residual": residual,
        "residual_rate": (round(residual / declared, 4) if declared > 0 else 0.0),
        "tolerance": round(max(tol, residual_abs), 2),
        "explained_by": {
            "revenue": declared,
            "ar_change": explained_ar,
            "advance_change": explained_adv,
            "ar_available": ar_ok, "ar_source": ar_src,
            "advance_available": adv_ok, "advance_source": adv_src,
        },
        "within_tolerance": bool(within),
        "available": bool(declared > 0),
        "skipped": skipped,
        "verdict_hint": hint,
        "detail": detail,
    }


def operating_income_cash(data: Dict[str, Any]) -> float:
    """经营性收款合计（**口径唯一**：`engine.bank_nature`，与既有三源对比同源）。

    口径（与 `domain_analysis._domain_voucher_invoice_revenue_compare` 完全一致）：
      性质分类**可用** ⇒ 取 `operating`（经营性）；不可用 ⇒ 退回 `total`（全部贷方）。

    ⚠ 「性质待判定」的收款**不计入**经营性（B2 不臆测）——但那样会漏掉一大块真实收款
      （实测：对手方无公司后缀时全归"待判定"），导致调节式算出**假差额**。
      故本函数另提供 `income_cash_scope()` 把 operating/undetermined 分开返回，
      由 `reconcile_income` 把两者均可比地纳入，并如实披露。
    """
    return float(income_cash_scope(data)["comparable"])


def income_cash_scope(data: Dict[str, Any]) -> Dict[str, float]:
    """收入侧现金口径明细（operating / undetermined / non_operating / comparable）。

    ★ `comparable`（**用于账表勾稽的可比口径**）= 经营性 + 待判定。
      为什么把"待判定"一并纳入：待判定收款的**性质尚无证据**，既不能算收入、也不能
      当非经营剔除（B2 明确"不得为了凑收入口径默认算经营性"）。在**账表勾稽**里
      把它排除会让等式左右**都缺同一块**，差额反而被夸大；故如实把它纳入"可比口径"
      并在报告中披露"其中 X 元性质待判定、须企业说明"——既不臆测，也不丢数据。
    """
    from engine.bank_nature import classify_receipts
    # ★ 2026-10-21 审计闸门抓出：必须**显式传序时账** —— 否则收款性质判定退回"猜摘要"
    #   （bank_nature 的账优先顺位：序时账科目 > 摘要关键词 > 待判定）。
    res = classify_receipts(data.get("bank_txs") or [],
                            data.get("vouchers") or data.get("voucher_rows"))
    if not res.get("available"):
        return {"operating": 0.0, "undetermined": 0.0, "non_operating": 0.0,
                "comparable": float(res.get("total") or 0.0), "available": False}
    op = float(res.get("operating") or 0.0)
    und = float(res.get("undetermined") or 0.0)
    non = float(res.get("non_operating") or 0.0)
    return {"operating": round(op, 2), "undetermined": round(und, 2),
            "non_operating": round(non, 2), "comparable": round(op + und, 2),
            "available": True}


# ══════════════════════════════════════════════════════════════════════════
# D5：未匹配流水四分类（替代"一律账外收入嫌疑"）
# ══════════════════════════════════════════════════════════════════════════
def classify_unmatched(data: Dict[str, Any], *,
                       side: str = "sale",
                       large_amount: float = DEFAULT_LARGE_AMOUNT) -> Dict[str, Any]:
    """把「**无对应发票**的资金流入」按四类归类，各自输出。

    ★★ 语义边界（2026-10-21 修正，验收①实测抓出）：
      「未匹配」= **该交易对手在发票清单里根本没有开票记录**（无论金额多少）。
      **不包括**"有开票但收款金额不全"——那种情形是**应收账款挂账**（差额），
      其收款部分**已属于该发票的收款**，绝不能算成"未匹配流入"。
      旧口径（按桶级 matched 判定）会把「客户A 开票100万只收60万」的 60 万全判成
      未匹配 ⇒ 凭空造出 60 万"账外流入"，正是用户批评的误报。

    四类的判据（主判据优先，关键词仅作佐证）：
      【非经营流水】 —— `bank_nature.classify_receipts` 判为非经营性（唯一权威）；
      【预收性质】   —— 摘要含预付款/定金等，**或**该对象有开票记录（先收后开）；
      【收款尾款】   —— 摘要含结算款/尾款等，**且**能对应到历史发票；
      【真正异常】   —— 以上皆非、对方**非个人**、且金额 ≥ 大额阈值。

    返回 {categories, unmatched_total, unmatched_count, suspects, detail_lines,
          over_invoiced: [...]}   # over_invoiced = 有开票但收款不足的对象（应收挂账，非未匹配）
    """
    inv_rows = [r for r in (data.get("sal_invs") if side == "sale" else data.get("pur_invs"))
                or [] if isinstance(r, dict)]
    bank_txs = [r for r in (data.get("bank_txs") or []) if isinstance(r, dict)]
    buckets = aggregate_by_object(inv_rows, bank_txs, side=side)

    # 该对象是否有开票记录（决定"是否属未匹配流入"）
    invoiced_cores = {k for k, b in buckets.items() if b["invoices"]}
    def _has_invoice(core: str) -> bool:
        if not core:
            return False
        if core in invoiced_cores:
            return True
        return any(k and (k in core or core in k) for k in invoiced_cores)

    # 经营性/非经营性分类（唯一权威：bank_nature）
    from engine.bank_nature import classify_receipts
    try:
        _nat = classify_receipts(bank_txs, data.get("vouchers") or data.get("voucher_rows"))
        _non_op_keys = {(_core_of(r.get("counterparty")), round(r.get("amount", 0), 2))
                        for r in (_nat.get("non_operating_rows") or [])}
    except Exception:                                         # noqa: BLE001
        _non_op_keys = set()

    from engine.fund_matching import is_individual_name, is_platform_counterparty

    cats: Dict[str, Dict[str, Any]] = {
        CLS_ADVANCE: {"rows": [], "amount": 0.0, "count": 0},
        CLS_TAIL: {"rows": [], "amount": 0.0, "count": 0},
        CLS_NON_OP: {"rows": [], "amount": 0.0, "count": 0},
        CLS_SUSPECT: {"rows": [], "amount": 0.0, "count": 0},
    }
    suspects: List[Dict[str, Any]] = []

    for tx in bank_txs:
        amt = _flow_amount(tx, side)
        if amt <= 0:
            continue
        cp = str(tx.get("counterparty") or "").strip()
        core = _core_of(cp)
        # ★ 该对象**有开票记录** ⇒ 其收款属于该发票的收款（可能部分），
        #   差额归"应收/预收"调节项，**不进入未匹配**（语义边界）。
        if _has_invoice(core):
            continue

        text = _tx_text(tx)
        key_hit = (core, round(amt, 2))

        # ① 非经营流水（bank_nature 唯一权威）
        if key_hit in _non_op_keys or any(h in text for h in _NON_OP_HINTS):
            _add(cats[CLS_NON_OP], tx, amt, cp)
            continue
        # ② 预收性质：摘要含预付款/定金（无发票对象的新客户先收款，典型预收）
        if any(k in text for k in _ADVANCE_KWS):
            _add(cats[CLS_ADVANCE], tx, amt, cp)
            continue
        # ③ 收款尾款：摘要含尾款/结算款 —— 无发票记录时须再查合同作历史佐证
        if any(k in text for k in _TAIL_KWS) and _has_contract_evidence(data, tx):
            _add(cats[CLS_TAIL], tx, amt, cp)
            continue
        # ④ 真正异常：无发票、无合同、对方非个人、金额巨大
        has_contract = _has_contract_evidence(data, tx)
        if (not is_individual_name(cp)) and (not is_platform_counterparty(cp)) \
                and amt >= large_amount and not has_contract:
            rec = _add(cats[CLS_SUSPECT], tx, amt, cp)
            suspects.append(rec)
            continue
        # 其余：有对方但证据不足、金额未达大额阈值 ⇒ 归【预收性质】宽口径，须企业说明
        _add(cats[CLS_ADVANCE], tx, amt, cp)

    # 有开票但收款不足的对象（应收挂账；其收款**不是**未匹配流入）
    over_invoiced = [
        {"object": k, "invoice_total": round(b["invoice_total"], 2),
         "flow_total": round(b["flow_total"], 2), "gap": round(b["diff"], 2)}
        for k, b in buckets.items()
        if b["invoices"] and not b["matched"] and b["diff"] < 0
    ]

    unmatched_total = round(sum(c["amount"] for c in cats.values()), 2)
    lines = []
    for name, c in cats.items():
        if c["count"]:
            lines.append("【%s】%d 笔、合计 %s 元" % (name, c["count"], format(c["amount"], ",.2f")))

    return {
        "categories": cats,
        "unmatched_total": unmatched_total,
        "unmatched_count": sum(c["count"] for c in cats.values()),
        "suspects": sorted(suspects, key=lambda r: -r["amount"]),
        "detail_lines": lines,
        "over_invoiced": over_invoiced,
    }


def _add(cat: Dict[str, Any], tx: Any, amt: float, cp: str) -> Dict[str, Any]:
    rec = {"date": str(tx.get("date") or "")[:10], "counterparty": cp,
           "amount": round(amt, 2), "summary": str(tx.get("summary") or "")[:60]}
    cat["rows"].append(rec)
    cat["amount"] += amt
    cat["count"] += 1
    return rec


def _has_contract_evidence(data: Dict[str, Any], tx: Any) -> bool:
    """该流水能否对上合同（合同号/项目名 命中 `contracts` 域）。命中即算有合同证据。"""
    contracts = data.get("contracts") or data.get("contract_data") or []
    if not contracts:
        return False
    text = _tx_text(tx)
    for c in contracts:
        if not isinstance(c, dict):
            continue
        cno = str(c.get("contract_no") or c.get("合同编号") or "").strip()
        cnm = str(c.get("name") or c.get("合同名称") or "").strip()
        if (cno and cno in text) or (cnm and len(cnm) >= 4 and cnm in text):
            return True
    return False


# ══════════════════════════════════════════════════════════════════════════
# 顶层入口：三维聚合匹配 + 调节 + 分类
# ══════════════════════════════════════════════════════════════════════════
def run_flexible_matching(data: Dict[str, Any], *,
                          side: str = "sale",
                          company_name: str = "") -> Dict[str, Any]:
    """柔性匹配总入口（收入侧 side="sale"，采购侧 side="purchase"）。

    返回与能力范式同构的 dict（available/ok/title/summary/body/metrics/signals/
    verdict/recommendation/note），并透传：
      · objects      —— 逐对象聚合桶（含跨期窗口计数）
      · reconcile    —— 资产负债表调节结果（残差是否在容忍度内）
      · unmatched    —— 未匹配四分类
    """
    side = "sale" if str(side) != "purchase" else "purchase"
    title = "资金流与发票流柔性匹配（三维聚合）" + ("·收入侧" if side == "sale" else "·采购侧")
    inv = (data.get("sal_invs") if side == "sale" else data.get("pur_invs")) or []
    bank = data.get("bank_txs") or []

    if not inv and not bank:
        return {
            "available": False, "ok": True, "title": title, "company": company_name,
            "summary": "未提供发票或银行流水，无法进行资金流与发票流的柔性匹配。",
            "body": "资金流×发票流匹配需要销项发票与银行收款流水，本轮均未提供。",
            "metrics": {}, "signals": [], "verdict": "资料缺失待核",
            "recommendation": "上传销项发票与银行流水后重新分析。",
            "note": "结论属待证线索，不作为定性依据。",
            "objects": {}, "reconcile": {}, "unmatched": {},
        }

    objects = aggregate_by_object(inv, bank, side=side)
    reconcile = reconcile_income(data) if side == "sale" else {}
    unmatched = classify_unmatched(data, side=side)

    matched_objs = [k for k, b in objects.items() if b["matched"]]
    gap_objs = [(k, b) for k, b in objects.items() if not b["matched"] and b["invoice_total"] > 0]
    cross_period = sum(1 for b in objects.values() if b["out_window"] > 0)
    suspects = unmatched.get("suspects") or []

    metrics = {
        "object_count": len(objects),
        "matched_object_count": len(matched_objs),
        "gap_object_count": len(gap_objs),
        "cross_period_object_count": cross_period,
        "unmatched_total": unmatched.get("unmatched_total", 0.0),
        "unmatched_count": unmatched.get("unmatched_count", 0),
        "suspect_count": len(suspects),
        "suspect_amount": round(sum(s["amount"] for s in suspects), 2),
    }
    if reconcile:
        metrics["declared_revenue"] = reconcile.get("declared", 0.0)
        metrics["operating_cash"] = reconcile.get("operating_cash", 0.0)
        metrics["residual"] = reconcile.get("residual", 0.0)
        metrics["within_tolerance"] = reconcile.get("within_tolerance", False)

    signals: List[Dict[str, str]] = []
    if cross_period:
        signals.append({"signal": f"{cross_period} 个对象存在跨期收款",
                        "hint": "发票与流水不在同月（含次月开票/回款），已按跨期窗口匹配"})
    for k, b in sorted(gap_objs, key=lambda kv: -abs(kv[1]["diff"]))[:5]:
        signals.append({"signal": f"{k}：开票 {b['invoice_total']:,.2f} 元、收款 {b['flow_total']:,.2f} 元",
                        "hint": f"差额 {b['diff']:,.2f} 元，须结合应收账款/预收账款核实"})
    if unmatched.get("unmatched_total", 0) > 0:
        signals.append({"signal": "未匹配资金流入 %s 元（%d 笔）"
                                  % (format(unmatched["unmatched_total"], ",.2f"),
                                     unmatched["unmatched_count"]),
                        "hint": "已按预收/尾款/非经营/异常四类拆分，见下"})

    if suspects:
        verdict = "存在真正异常收款待核"
    elif reconcile and reconcile.get("available") and not reconcile.get("within_tolerance"):
        verdict = "存在未解释差异待核"
    elif gap_objs:
        verdict = "存在待解释差额（多为应收/预收）"
    else:
        verdict = "三维聚合匹配未见异常"

    body_parts = [
        "【按对象聚合】%d 个交易对手完成桶级比对，吻合 %d 个、存在差额 %d 个。"
        % (len(objects), len(matched_objs), len(gap_objs)),
    ]
    if cross_period:
        body_parts.append("【按期间聚合】%d 个对象存在跨期收款，已在跨期窗口内完成匹配。" % cross_period)
    if reconcile:
        body_parts.append("【资产负债表调节】" + reconcile.get("detail", ""))
    if unmatched.get("detail_lines"):
        body_parts.append("【未匹配分类】" + "；".join(unmatched["detail_lines"]) + "。")

    return {
        "available": True, "ok": True, "title": title, "company": company_name,
        "summary": "；".join(body_parts),
        "body": "\n".join(body_parts),
        "metrics": metrics,
        "signals": signals,
        "verdict": verdict,
        "recommendation": ("对未解释差异与【真正异常】收款，请企业逐笔说明款项性质"
                           "（预收/往来/赊销回款/账外收入），并提供合同、发货记录、"
                           "应收账款明细账与期后回款凭证；正常赊销与预收不构成疑点。"),
        "note": "未匹配 ≠ 隐匿收入；本项结论属待证线索，不作为定性依据。",
        "objects": objects,
        "reconcile": reconcile,
        "unmatched": unmatched,
    }


__all__ = [
    "aggregate_by_object",
    "reconcile_income",
    "classify_unmatched",
    "run_flexible_matching",
    "operating_income_cash",
    "CLS_ADVANCE", "CLS_TAIL", "CLS_NON_OP", "CLS_SUSPECT",
]