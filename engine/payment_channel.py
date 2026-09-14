# -*- coding: utf-8 -*-
"""支付渠道识别与跨期匹配窗口（2026-09-14 新增）。

背景
----
`fund_matching.match_invoices_to_flows` 只认**对公转账**（按对手核心名）与**平台代付**，
个人垫付仅认"流水对方为自然人"。但成本的合法付款渠道远不止这些：

    对公转账 / **银行承兑·商业承兑汇票** / 平台代付 / **个人垫付后报销** /
    **现金** / **债务抵销·以货抵款** / 股东代付 / 应付账款挂账

尤其**票据**（出票、背书、贴现都不体现在对公转账里）与**跨期付款**（年末开票、次年付款）
会造成大量"假未匹配"。

本模块职责
--------
对已被判为"无流水"的发票做**二次取证**：
1. 在 `[发票日 − 前置天数, 发票日 + 账期天数]` 的**跨期窗口**内找付款/结算痕迹；
2. 识别票据、抵销、现金、报销等**非对公转账**渠道；
3. 返回命中渠道与原始证据行，供规则层分层定性（**不直接下结论**）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from engine.fund_matching import _core_of
except Exception:  # pragma: no cover
    import re as _re

    def _core_of(name: str) -> str:
        return _re.sub(r"[（(].*?[)）]", "", str(name or "")).strip()[:12]

# 发票日之前允许的提前付款天数（预付/半月结）
PRE_DAYS = 30
# 发票日之后允许的账期天数（赊购常态上限）
DEFAULT_WINDOW_DAYS = 180

CHANNEL_KEYWORDS = {
    "票据结算": ("承兑", "汇票", "票据", "贴现", "背书", "银承", "商承", "银行承兑"),
    "债务抵销": ("抵销", "抵账", "以货抵", "抹账", "冲抵", "债务重组", "款项互抵"),
    "个人垫付": ("报销", "垫付", "备用金", "代垫"),
    "现金": ("现金", "取现", "库存现金", "现钞"),
    "平台代付": ("财付通", "支付宝", "抖音", "微信支付", "平台结算", "代付"),
}


def _norm_date(text: Any) -> Optional[str]:
    """"YYYY-MM-DD / YYYYMMDD / YYYY年M月D日" → "YYYYMMDD"；失败返回 None。"""
    s = "".join(ch for ch in str(text or "") if ch.isdigit())
    return s[:8] if len(s) >= 8 else None


def _day_diff(a: str, b: str) -> Optional[int]:
    import datetime as _dt
    if not a or not b:
        return None
    try:
        d1 = _dt.date(int(a[:4]), int(a[4:6]), int(a[6:8]))
        d2 = _dt.date(int(b[:4]), int(b[4:6]), int(b[6:8]))
    except ValueError:
        return None
    return (d2 - d1).days


def _tx_text(row: Dict) -> str:
    if not isinstance(row, dict):
        return ""
    return " ".join(str(row.get(k) or "") for k in
                    ("counterparty", "对手方", "对方户名", "summary", "摘要", "用途",
                     "remark", "备注", "goods", "货物或应税劳务名称"))


def detect_channels(text: str) -> List[str]:
    """从文本识别非对公转账的结算渠道。"""
    t = str(text or "")
    return [name for name, kws in CHANNEL_KEYWORDS.items() if any(k in t for k in kws)]


def window_exceeds_data(invoice_date: str, base_date: str,
                        window_days: int = DEFAULT_WINDOW_DAYS) -> bool:
    """发票日 + 账期是否**超出数据期末**。

    超出 → 该笔付款完全可能发生在企业未提供的后续期间（年末开票、次年付款是常态），
    此时"未匹配到付款"是**资料未覆盖**，不是未付款；须补后续期间流水后再判断。
    """
    if not invoice_date or not base_date:
        return False
    off = _day_diff(_norm_date(invoice_date), _norm_date(base_date))
    return off is not None and off < window_days


def find_payment_evidence(supplier: str, invoice_date: str,
                          bank_txs: Optional[List[Dict]] = None,
                          vouchers: Optional[List[Dict]] = None,
                          window_days: int = DEFAULT_WINDOW_DAYS,
                          pre_days: int = PRE_DAYS,
                          invoice_amount: Optional[float] = None) -> Dict[str, Any]:
    """对一笔发票做跨期 + 多渠道二次取证。

    归因纪律（避免张冠李戴）：
      · 银行流水：**必须**「对手名命中供应商核心名」才计入；无名称命中时，
        仅在「金额吻合（±2%）且属票据/抵销/现金/平台等非对公渠道」时才计入；
      · 序时账：**必须**凭证文本中出现供应商核心名。
      （否则一条含"代付/现金"字样的流水会被错误地算作所有未匹配发票的覆盖证据。）

    返回::

        {
          "window_days": int, "channels": {渠道名: 命中笔数},
          "hits": [ {来源, 渠道, 日期, 金额, 摘要} ... 最多 8 条 ],
          "same_name_out_of_window": int,   # 同名付款但落在窗口外（跨期/超账期信号）
        }
    """
    inv_d = _norm_date(invoice_date)
    core = _core_of(supplier)
    amt_inv = abs(float(invoice_amount or 0))
    result = {"window_days": window_days, "channels": {}, "hits": [],
              "same_name_out_of_window": 0}
    if not core:
        return result

    def _bump(ch):
        result["channels"][ch] = result["channels"].get(ch, 0) + 1

    # ① 银行流水（支出方向）：窗口内 + 名称命中（或 金额吻合的渠道命中）
    for tx in bank_txs or []:
        if not isinstance(tx, dict):
            continue
        try:
            amt = float(str(tx.get("debit") or 0).replace(",", "") or 0)
        except (TypeError, ValueError):
            amt = 0.0
        if amt <= 0:
            continue
        text = _tx_text(tx)
        cp = str(tx.get("counterparty") or "")
        name_hit = bool(core and (core in cp or core in text))
        chs = detect_channels(text)
        off = _day_diff(inv_d, _norm_date(tx.get("date") or tx.get("交易日期")))
        if off is None:
            continue
        in_window = (-pre_days) <= off <= window_days
        if name_hit:
            if not in_window:
                result["same_name_out_of_window"] += 1
                continue
            ch = chs[0] if chs else "对公转账"
        else:
            # 无名称命中：仅当"金额吻合 + 属非对公渠道"才认，避免误归因
            amount_close = amt_inv > 0 and abs(amt - amt_inv) <= max(1.0, amt_inv * 0.02)
            if not (chs and amount_close and in_window):
                continue
            ch = chs[0]
        _bump(ch)
        if len(result["hits"]) < 8:
            result["hits"].append({"来源": "银行流水", "渠道": ch,
                                   "日期": str(tx.get("date") or "")[:10],
                                   "金额": round(amt, 2), "摘要": text[:60]})

    # ② 序时账（凭证）：必须出现供应商核心名，再看是否为票据/抵销/现金等渠道
    for v in vouchers or []:
        if not isinstance(v, dict):
            continue
        text = _tx_text(v)
        if not text or not (core and core in text):
            continue
        off = _day_diff(inv_d, _norm_date(v.get("date") or v.get("日期") or v.get("记账日期")))
        if off is None or not ((-pre_days) <= off <= window_days):
            continue
        chs = detect_channels(text)
        if not chs:
            continue          # 未写明结算渠道的凭证不作为"已结算"证据
        _bump(chs[0])
        if len(result["hits"]) < 8:
            result["hits"].append({"来源": "序时账", "渠道": chs[0],
                                   "日期": str(v.get("date") or v.get("日期") or "")[:10],
                                   "金额": None, "摘要": text[:60]})
    return result
