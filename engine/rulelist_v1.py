# -*- coding: utf-8 -*-
"""外部规则清单 V1.0 的落地检测器（本系统真缺的 12 条）—— **查实层**，不新增红线。

## 为什么单独一个模块
外部清单（VAT 30 + CIT 30）里有 48 条本系统已有对应检测器（对照见
`config/rulelist_v1.json`），只有 12 条真缺。这 12 条都是"可从账内数据真算"的
**可复算事实**，故按系统已验证原子规则（VR）的范式落地，**不新增红线**
（红线条数被 91 处文档/闸门绑定；VR 只做查实层，归属另议）。

## 三条纪律（违反即事故）
1. **阈值不写进代码**：全部取自 `config/rulelist_v1.json → params`（唯一权威）。
   新增同类对象 = 在数据表加一行。
2. **数值/期间解析走唯一权威**：`engine/numparse.py`（数值）、`engine/findingkit.py`（月份）。
   严禁私有实现（历史上用「按位或+零」的兜底写法，遇 "12,000.00" 会静默返 0）。
3. **缺资料 ≠ 违规**：拉不起完整判据时只出「数据质量提示」（`data_quality_limitation`），
   绝不按"疑似"下风险等级；**且不重复报告**——若本账套连该类数据都没有，
   覆盖度/资料缺口模块已负责列明，此处**静默**。

## 与外部清单的差异（已在 `config/rulelist_v1.json` 显式登记）
- 清单用 `condition` 单条布尔式、规则自带 `score`；本系统等级由 `engine/risk_levels.py`
  裁定、规则不自带分数 ⇒ 本模块只产出**事实 + 待核口径**。
- 清单的 `tax_exempt_sales`/`prepaid_vat`/`taxable_income` 等变量需申报表附列资料，
  本系统只在**该类申报表已上传**时才计算，否则不产出（见 12 条各自的 `_basis`）。
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

_CFG = Path(__file__).resolve().parents[1] / "config" / "rulelist_v1.json"
_PARAMS: Optional[Dict[str, Any]] = None

#: 夜间开票的小时集合缺省（可被数据表覆盖）
_DEFAULT_NIGHT_HOURS = (22, 23, 0, 1, 2, 3, 4, 5)
_DEFAULT_SOURCES = ["序时账/记账凭证", "发票（销项/进项）", "纳税申报表", "银行流水", "企业档案"]


def _params(rule_id: str) -> Dict[str, Any]:
    """取该外部规则的阈值（唯一权威 `config/rulelist_v1.json → params`）。"""
    global _PARAMS
    if _PARAMS is None:
        try:
            _PARAMS = json.loads(_CFG.read_text(encoding="utf-8")).get("params") or {}
        except Exception:                      # noqa: BLE001 —— 配置缺失 ⇒ 空表（不静默给错阈值）
            _PARAMS = {}
    return _PARAMS.get(rule_id) or {}


def _num(value) -> float:
    """数值解析（唯一权威 engine/numparse.py）。"""
    from engine.numparse import to_number
    return to_number(value)


def _month(value) -> str:
    """月份键 `YYYYMM`（唯一权威 engine/findingkit.month_key）。"""
    from engine.findingkit import month_key
    return month_key(value)


def _dict_rows(data: Dict, key: str) -> List[Dict]:
    v = (data or {}).get(key)
    return [r for r in v if isinstance(r, dict)] if isinstance(v, list) else []


def _mk(spec: Dict, detail: str, metrics: Dict, sources: List[str] = None,
        status: str = "clue_pending_investigation", priority: str = "中"):
    """构造 finding（复用系统统一底盘，强制携带三件套与待核口径）。"""
    from engine.verified_rule_engine import _rule_finding
    return _rule_finding(spec, detail, metrics,
                         sources or spec.get("required_sources") or _DEFAULT_SOURCES,
                         status=status, priority=priority)


def _field(row: Dict, names) -> Any:
    """按候选键名取值（容错不同来源的表头）。"""
    for k in names:
        v = (row or {}).get(k)
        if v not in (None, ""):
            return v
    return None


def _need(spec: Dict, what: str, why: str, evidence: List[str]):
    """缺资料时的统一产出：**数据质量提示**（不是风险结论）。"""
    return _mk(spec,
               f"本项需企业补充资料后方可完成核验：{what}。{why}",
               {"_data_gap": what}, status="data_quality_limitation")


# ══════════════════════════════════════════════════════════════════
# 增值税侧
# ══════════════════════════════════════════════════════════════════

def scan_vat_004(data: Dict, spec: Dict) -> List[Dict]:
    """VAT-004 进销项税额增速背离：销项税增速 − 进项税增速 > 阈值 且 销项增速 > 下限。"""
    p = _params("VAT-004")
    out, inp = defaultdict(float), defaultdict(float)
    for r in _dict_rows(data, "sal_invs"):
        m = _month(_field(r, ["date", "开票日期"]))
        if m:
            out[m] += _num(_field(r, ["tax", "税额"]))
    for r in _dict_rows(data, "pur_invs"):
        m = _month(_field(r, ["date", "开票日期"]))
        if m:
            inp[m] += _num(_field(r, ["tax", "税额"]))
    months = sorted(set(out) | set(inp))
    if len(months) < 2:
        return []

    def _grow(series) -> Optional[float]:
        first, last = months[0], months[-1]
        base, cur = series.get(first, 0.0), series.get(last, 0.0)
        return (cur - base) / base if base > 0 else None

    g_out, g_in = _grow(out), _grow(inp)
    if g_out is None or g_in is None:
        return []                              # 首月为零 ⇒ 增速无意义，不硬算
    gap, floor = float(p.get("growth_gap", 0.3)), float(p.get("output_growth_floor", 0.2))
    if g_out - g_in > gap and g_out > floor:
        return [_mk(spec,
                    f"销项税额从 {months[0]} 的 {out.get(months[0], 0):,.2f} 元增至 "
                    f"{months[-1]} 的 {out.get(months[-1], 0):,.2f} 元（增速 {g_out*100:.1f}%），"
                    f"同期进项税额增速仅 {g_in*100:.1f}%（差 {abs(g_out-g_in)*100:.1f} 个百分点，"
                    f"阈值 {gap*100:.0f} 个百分点）。销售增长未带动相应采购，"
                    "请核实进项是否取得充分、销项是否真实，以及是否存在少抵或多开情形。",
                    {"vat004_output_growth": round(g_out, 4), "vat004_input_growth": round(g_in, 4),
                     "vat004_gap": round(g_out - g_in, 4)},
                    priority="中")]
    return []


def scan_vat_008(data: Dict, spec: Dict) -> List[Dict]:
    """VAT-008 夜间开票异常：夜间（22:00–次日 06:00）开票占比超阈值。"""
    p = _params("VAT-008")
    hours = set(p.get("night_hours") or _DEFAULT_NIGHT_HOURS)
    total = night = 0
    night_amt = 0.0
    amt = 0.0
    for r in _dict_rows(data, "sal_invs"):
        d = str(_field(r, ["date", "开票日期"]) or "")
        m = re.search(r"[T ](\d{1,2}):(\d{2})", d)
        if not m:
            continue
        total += 1
        a = _num(_field(r, ["amount", "金额"]))
        amt += a
        if int(m.group(1)) in hours:
            night += 1
            night_amt += a
    if total < int(p.get("min_invoices", 10)):
        return []                              # 样本不足，不出结论
    ratio = night / total
    if ratio > float(p.get("night_ratio", 0.2)):
        return [_mk(spec,
                    f"销项发票 {total} 张中 {night} 张（{ratio*100:.1f}%，阈值 "
                    f"{float(p.get('night_ratio', 0.2))*100:.0f}%）开具于夜间 22:00–次日 06:00，"
                    f"涉及金额 {night_amt:,.2f} 元。请核实是否存在非正常工作时间的集中开票，"
                    "以及该时点开票对应的真实业务发生时间。",
                    {"vat008_night_count": night, "vat008_total_count": total,
                     "vat008_night_ratio": round(ratio, 4), "vat008_night_amount": round(night_amt, 2)},
                    priority="中")]
    return []


def scan_vat_014(data: Dict, spec: Dict) -> List[Dict]:
    """VAT-014 简易计税与一般计税进项混用：**需申报表附列资料**方可完整判定。

    账内可先做线索检索（科目/摘要含「简易计税」）；拉不起
    「简易计税销售额 > 0 且 一般计税进项已抵扣 > 0」的完整判据时只出资料提示。
    """
    clue = []
    for r in _dict_rows(data, "vouchers"):
        blob = str(_field(r, ["account_name", "科目名称", "account"]) or "") + \
               str(_field(r, ["summary", "摘要"]) or "")
        if "简易计税" in blob:
            clue.append(blob[:40])
    if not clue:
        return []
    return [_need(spec, "增值税申报表附列资料（一）（三）（四）与简易计税备案资料",
                  "账内存在「简易计税」线索，但仅凭账载无法判断简易计税销售额与一般计税进项"
                  "是否混用；需比对申报表附列资料中简易计税栏与一般计税进项抵扣栏。",
                  [f"账内命中「简易计税」线索 {len(clue)} 处"])]


def scan_vat_015(data: Dict, spec: Dict) -> List[Dict]:
    """VAT-015 预缴增值税与申报税额差异：**需《增值税预缴税款表》**。"""
    has_cross_region = False
    for r in _dict_rows(data, "sal_invs"):
        g = str(_field(r, ["goods", "货物名称"]) or "")
        if any(k in g for k in ("建筑服务", "不动产", "租赁服务", "工程施工")):
            has_cross_region = True
            break
    if not has_cross_region:
        return []
    return [_need(spec, "《增值税预缴税款表》与异地预缴完税凭证",
                  "销项侧存在建筑服务/不动产租赁等可能需异地预缴的应税行为，"
                  "但账内无预缴税款记录，无法比对预缴与申报的一致性。",
                  ["销项品名命中建筑服务/不动产类关键词"])]


def scan_vat_021(data: Dict, spec: Dict) -> List[Dict]:
    """VAT-021 差额征税项目异常：**需申报表附列资料（差额征税栏）**。"""
    kw = ("旅游服务", "劳务派遣", "经纪代理", "融资租赁", "客运场站", "代收转付", "人力资源服务")
    hit = []
    for r in _dict_rows(data, "sal_invs"):
        g = str(_field(r, ["goods", "货物名称"]) or "")
        if any(k in g for k in kw):
            hit.append(g[:30])
    if not hit:
        return []
    return [_need(spec, "增值税申报表附列资料（三）差额征税项目明细",
                  "销项品名命中差额征税常见税目，但账内无扣除项目明细，"
                  "无法核验销售额与扣除额是否匹配。",
                  [f"命中差额征税税目 {len(hit)} 张发票"])]


def scan_vat_024(data: Dict, spec: Dict) -> List[Dict]:
    """VAT-024 新办企业短期大量开票：成立后 N 个月内开票金额与张数超阈值。"""
    p = _params("VAT-024")
    te = data.get("target_entity") if isinstance(data.get("target_entity"), dict) else {}
    est = str(_field(te, ["established_date", "成立日期", "成立时间"]) or "")
    est_m = _month(est)
    if not est_m:
        return []                              # 无成立日期 ⇒ 不判（不猜）
    months_n = int(p.get("months", 3))
    sal = _dict_rows(data, "sal_invs")
    cnt, amt = 0, 0.0
    for r in sal:
        m = _month(_field(r, ["date", "开票日期"]))
        if not m:
            continue
        try:
            span = (int(m[:4]) - int(est_m[:4])) * 12 + (int(m[4:6]) - int(est_m[4:6]))
        except Exception:                      # noqa: BLE001
            continue
        if 0 <= span < months_n:
            cnt += 1
            amt += _num(_field(r, ["amount", "金额"]))
    if cnt < int(p.get("min_invoices", 20)) or amt <= float(p.get("amount_threshold", 1000000.0)):
        return []
    return [_mk(spec,
                f"企业成立于 {est[:10]}，成立后 {months_n} 个月内已开具销项发票 {cnt} 张、"
                f"金额 {amt:,.2f} 元（金额阈值 {float(p.get('amount_threshold', 1000000.0)):,.2f} 元、"
                f"张数阈值 {int(p.get('min_invoices', 20))} 张）。请核实新办期业务能力与开票规模是否匹配。",
                {"vat024_invoice_count": cnt, "vat024_amount": round(amt, 2),
                 "vat024_established": est[:10]},
                priority="中")]
    return []


# ══════════════════════════════════════════════════════════════════
# 企业所得税侧
# ══════════════════════════════════════════════════════════════════

def _cit_decls(data: Dict) -> List[Dict]:
    """企业所得税申报表行（按 `_declaration_type` 过滤）。"""
    out = []
    for r in _dict_rows(data, "tax_declarations"):
        t = str(r.get("_declaration_type") or "").lower()
        if t in ("cit", "cit_declaration", "企业所得税"):
            out.append(r)
    return out


def scan_cit_002(data: Dict, spec: Dict) -> List[Dict]:
    """CIT-002 企业所得税税负率期间波动：需**两期**企业所得税申报表。"""
    p = _params("CIT-002")
    decls = _cit_decls(data)
    if len(decls) < 2:
        if decls:
            return [_need(spec, "上期企业所得税申报表",
                          "仅有当期企业所得税申报数据，无法计算税负率的期间波动。",
                          [f"企业所得税申报行 {len(decls)} 期"])]
        return []                              # 连该类申报表都没有 ⇒ 覆盖度模块已负责
    series = []
    for r in decls:
        rev = _num(_field(r, ["revenue", "营业收入", "sales_amount", "销售额"]))
        cit = _num(_field(r, ["cit_payable", "应纳所得税额", "payable_tax", "应纳税额"]))
        if rev > 0:
            series.append((str(_field(r, ["period", "所属期"]) or ""), cit / rev))
    if len(series) < 2:
        return []
    series.sort()
    prev, cur = series[-2][1], series[-1][1]
    if prev <= 0:
        return []
    vol = abs(cur - prev) / prev
    if vol > float(p.get("volatility", 0.5)):
        return [_mk(spec,
                    f"企业所得税税负率由 {series[-2][0]} 的 {prev*100:.3f}% 变为 "
                    f"{series[-1][0]} 的 {cur*100:.3f}%，波动 {vol*100:.1f}%（阈值 "
                    f"{float(p.get('volatility', 0.5))*100:.0f}%）。请分析税负突变原因。",
                    {"cit002_prev_rate": round(prev, 6), "cit002_cur_rate": round(cur, 6),
                     "cit002_volatility": round(vol, 4)}, priority="中")]
    return []


def scan_cit_003(data: Dict, spec: Dict) -> List[Dict]:
    """CIT-003 利润总额与应纳税所得额差异异常（> 阈值）。"""
    p = _params("CIT-003")
    decls = _cit_decls(data)
    if not decls:
        return []                              # 无企业所得税申报表 ⇒ 覆盖度模块已列明需补
    hits = []
    for r in decls:
        profit = _num(_field(r, ["profit_total", "利润总额"]))
        taxable = _num(_field(r, ["taxable_income", "应纳税所得额"]))
        if profit <= 0 or taxable == 0:
            continue
        diff = abs(taxable - profit) / profit
        if diff > float(p.get("diff_ratio", 0.3)):
            hits.append((str(_field(r, ["period", "所属期"]) or ""), profit, taxable, diff))
    if not hits:
        return []
    per, profit, taxable, diff = hits[-1]
    return [_mk(spec,
                f"{per} 利润总额 {profit:,.2f} 元与应纳税所得额 {taxable:,.2f} 元相差 "
                f"{diff*100:.1f}%（阈值 {float(p.get('diff_ratio', 0.3))*100:.0f}%）。"
                "请核实纳税调整项目是否完整（A105000 明细）。",
                {"cit003_profit": round(profit, 2), "cit003_taxable": round(taxable, 2),
                 "cit003_diff_ratio": round(diff, 4)}, priority="中")]


def scan_cit_007(data: Dict, spec: Dict) -> List[Dict]:
    """CIT-007 预缴与汇算差异大：需同一纳税年度的预缴与汇算数据。"""
    p = _params("CIT-007")
    decls = _cit_decls(data)
    if not decls:
        return []
    hits = []
    for r in decls:
        pre = _num(_field(r, ["prepaid_cit", "预缴税额", "已预缴税额"]))
        ann = _num(_field(r, ["annual_cit", "实际应纳所得税额", "汇算应纳所得税额"]))
        if ann <= 0:
            continue
        diff = abs(pre - ann) / ann
        if pre > 0 and diff > float(p.get("diff_ratio", 0.3)):
            hits.append((str(_field(r, ["period", "所属期"]) or ""), pre, ann, diff))
    if not hits:
        return []
    per, pre, ann, diff = hits[-1]
    return [_mk(spec,
                f"{per} 预缴企业所得税 {pre:,.2f} 元与汇算应纳 {ann:,.2f} 元相差 {diff*100:.1f}%"
                f"（阈值 {float(p.get('diff_ratio', 0.3))*100:.0f}%）。请核实预缴准确性与汇算调整。",
                {"cit007_prepaid": round(pre, 2), "cit007_annual": round(ann, 2),
                 "cit007_diff_ratio": round(diff, 4)}, priority="中")]


def _non_taxable_clues(data: Dict):
    """账内不征税/免税收入线索（科目或摘要命中）。"""
    nt, ex = [], []
    for r in _dict_rows(data, "vouchers"):
        blob = str(_field(r, ["account_name", "科目名称", "account"]) or "") + \
               str(_field(r, ["summary", "摘要"]) or "")
        amt = _num(_field(r, ["credit", "贷方"]))
        if any(k in blob for k in ("不征税收入", "专项应付款", "财政拨款")):
            nt.append((blob[:36], amt))
        if any(k in blob for k in ("免税收入", "免税项目", "免征")):
            ex.append((blob[:36], amt))
    for b in _dict_rows(data, "balances"):
        nm = str(_field(b, ["name", "科目名称"]) or "")
        if "不征税" in nm:
            nt.append((nm[:36], _num(_field(b, ["close_credit", "期末贷方"]))))
        if "免税" in nm:
            ex.append((nm[:36], _num(_field(b, ["close_credit", "期末贷方"]))))
    return nt, ex


def scan_cit_019(data: Dict, spec: Dict) -> List[Dict]:
    """CIT-019 不征税收入对应支出已扣除线索（需专项资料核实对应关系）。"""
    nt, _ = _non_taxable_clues(data)
    if not nt:
        return []
    amt = sum(a for _, a in nt)
    return [_need(spec, "不征税收入专项资料与 A105040 明细",
                  f"账内存在不征税收入线索（{len(nt)} 处，贷方合计 {amt:,.2f} 元）。"
                  "不征税收入用于支出所形成的费用/资产折旧摊销不得税前扣除，"
                  "需以专项资料核实对应支出是否已扣除。",
                  [f"不征税收入线索 {len(nt)} 处"])]


def scan_cit_020(data: Dict, spec: Dict) -> List[Dict]:
    """CIT-020 免税收入对应成本已扣除线索（需免税项目核算资料）。"""
    _, ex = _non_taxable_clues(data)
    if not ex:
        return []
    amt = sum(a for _, a in ex)
    return [_need(spec, "免税项目与其对应成本的分别核算资料",
                  f"账内存在免税收入/免税项目线索（{len(ex)} 处，贷方合计 {amt:,.2f} 元）。"
                  "免税收入对应的成本不得税前扣除，需核对是否已分别核算。",
                  [f"免税收入线索 {len(ex)} 处"])]


def scan_cit_030(data: Dict, spec: Dict) -> List[Dict]:
    """CIT-030 税会差异调整不完整线索（需 A105000 纳税调整明细表）。"""
    decls = _cit_decls(data)
    if not decls:
        return []
    gap = False
    for r in decls:
        profit = _num(_field(r, ["profit_total", "利润总额"]))
        taxable = _num(_field(r, ["taxable_income", "应纳税所得额"]))
        adj = _num(_field(r, ["adjust_amount", "纳税调整增加额", "调整额"]))
        if profit != 0 and taxable != 0 and adj == 0 and abs(taxable - profit) > 0:
            gap = True
    if not gap:
        return []
    return [_need(spec, "A105000 纳税调整项目明细表",
                  "申报数据中利润总额与应纳税所得额存在差异，但未见纳税调整额，"
                  "无法判断调整是否完整。",
                  ["利润总额与应纳税所得额存在差异而调整额为 0"])]


# ══════════════════════════════════════════════════════════════════
# 分发（供 verified_rule_engine._SCANNERS 薄转发）
# ══════════════════════════════════════════════════════════════════

DETECTORS = {
    "VAT-004": scan_vat_004,
    "VAT-008": scan_vat_008,
    "VAT-014": scan_vat_014,
    "VAT-015": scan_vat_015,
    "VAT-021": scan_vat_021,
    "VAT-024": scan_vat_024,
    "CIT-002": scan_cit_002,
    "CIT-003": scan_cit_003,
    "CIT-007": scan_cit_007,
    "CIT-019": scan_cit_019,
    "CIT-020": scan_cit_020,
    "CIT-030": scan_cit_030,
}


def scan(data: Dict, spec: Dict, src_id: str) -> List[Dict]:
    """按外部规则号分派（`verified_rule_engine._SCANNERS` 的薄转发目标）。"""
    fn = DETECTORS.get(src_id)
    if fn is None:
        return []
    try:
        return fn(data, spec) or []
    except Exception as exc:                    # noqa: BLE001 —— 单条异常不阻断整轮
        import sys
        print(f"[规则清单V1] {src_id} 执行异常: {exc}", file=sys.stderr)
        return []
