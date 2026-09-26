# -*- coding: utf-8 -*-
"""「一、本轮检查总体结论」生成器 —— 唯一权威（2026-09-26）

用户要求（2026-09-26）：该章必须**从 findings 实测派生**，不得手写模板。
凡数字（收到资料数、风险项数、各等级计数）、点名清单、涉及税种、行业口径，
一律取实测；新增或减少一条发现时**无需改本模块**（只认数据，不认特例）。

编辑标准（用户 2026-09-26 复核后定稿，**务必遵守**）：
  ① 行业认定**不得写得太确定**：销项发票品名只作「**初步测算口径**」，须并列登记口径，
     并声明"行业认定应以登记经营范围、实际主营业务收入构成、合同和发票品名为准，待核实"。
     禁用"变名开票"等重定性词，改中性表述（"开票品名与实际经营是否一致，需核实…"）。
  ② 事项措辞用「**待核实风险事项**」——名词核心是"风险事项"（肯定它是风险），
     "待核实"只作定语；紧跟"尚不构成违法定性"。禁用"已确认 N 项风险事项"式强断言。
  ③ **等级与状态分离**：风险等级只有 高/中/低；「待核验」是**证据状态**，
     必须单列并声明"不参与风险等级排序"，不得与"低风险"并列（分类不统一）。
  ④ 须写明**分级依据**（潜在税额 / 涉及金额 / 证据缺口 / 是否涉及虚开或偷税 / 补证紧迫性）。
  ⑤ 税种统计须注明是「**事项—税种关联次数**，非事项数」（一项可涉多个税种）。
  ⑥ 涉嫌方向须写「**可能**涉及的涉嫌方向（**待核实**）」，不得写"已指向"。
  ⑦ 资料缺口措辞用"**将影响**……的检查"，不用"无法检查"；
     "稽查必查资料"改为"本轮检查必查资料"（系统报告非税务机关稽查文书）。

设计红线：
  · 本模块只**读** findings 与 target_entity / inspector_reasoning，不修改任何结论；
  · 涉嫌方向用**词表扫描真实 suspect 字段**得出，命不中就不写（不凭空罗列）；
  · 行业口径原样引用（含来源与冲突），不自造"某行业基准"表述。
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

# 分层顺序：按风险程度由重到轻（与 findings.risk_level 词表一致）
_TIER_ORDER = ["高风险", "中风险", "待核验", "低风险", "信息"]
_TIER_LABEL = {"信息": "提示性事项"}

# 涉嫌方向词表（**数据驱动**：只在真实 suspect 文本中出现时才列出，命不中不写）
_DIRECTION_VOCAB = [
    "隐匿收入", "隐瞒收入", "不入账的收入", "虚开发票", "接受虚开发票", "为他人代开",
    "虚列成本", "虚增成本", "虚列费用", "虚增税前扣除", "虚列人员", "虚增人员",
    "资金回流", "资金空转", "转移利润", "变相分配", "公私混同",
    "少缴税款", "少代扣代缴", "未代扣代缴", "拆分收入", "虚抵",
]


def _short_title(t: Any) -> str:
    """标题去掉「：后缀说明」，只留主事件名（点名用）。"""
    s = str(t or "").strip()
    for sep in ("：", ":"):
        if sep in s:
            s = s.split(sep)[0]
    return s.strip()


def _collect_directions(problems: List[dict], limit: int = 6) -> List[str]:
    """从真实 suspect 文本扫描出**实际出现**的涉嫌方向（命中即列，未命中不列）。"""
    c: Counter = Counter()
    for p in problems:
        s = str((p or {}).get("suspect") or "")
        if not s:
            continue
        for d in _DIRECTION_VOCAB:
            if d in s:
                c[d] += 1
    return [d for d, _ in c.most_common(limit)]


# ═══════════════════════════════════════════════════════════════════════════
# 风险主题归纳表（数据驱动：新增主题只需加一行，不改逻辑）
# ═══════════════════════════════════════════════════════════════════════════
# 用途：把逐条发现**归纳**为稽查主题，回答"风险集中在哪些方面"，
#       而不是只按等级平铺列举（用户要求：突出重点结果、总结归纳风险情况）。
_RISK_THEMES = [
    # ⚠ 顺序即优先级：越**具体/定性越重**的主题排越前。
    #   反例（已修）：原「成本费用真实性」排在「发票与交易真实性」之前，
    #   导致"有进无销"（涉嫌虚开+虚增成本）被成本主题先截走——虚开是更具体的定性，应优先。
    ("收入完整性", ["隐匿收入", "隐瞒收入", "不入账", "未开票", "账外", "少计收入",
                    "银行收款大于", "私户", "个人账户收取", "未纳入"]),
    ("发票与交易真实性", ["虚开发票", "接受虚开", "为他人代开", "红字冲销", "作废发票",
                          "有进无销", "有销无进", "开票额", "票面", "品名"]),
    ("成本费用真实性", ["虚列成本", "虚增成本", "虚列费用", "白条", "成本列支", "期间费用",
                        "无真实业务", "虚增税前扣除", "成本费用", "列支费用", "调节"]),
    ("资金流向", ["资金回流", "资金空转", "公转私", "公私混同", "回流", "循环"]),
    ("工资社保与个税", ["工资", "社保", "个税", "劳务报酬", "代扣代缴", "虚列人员", "用工"]),
    ("税费申报", ["申报", "印花税", "附加", "计税依据", "税负", "少缴"]),
    ("关联交易", ["关联", "六员", "转移利润", "利益输送"]),
    ("经营合理性", ["长期亏损", "数字特征", "持续经营", "毛利率", "异常"]),
]


def _group_by_theme(problems: List[dict]) -> List[Dict[str, Any]]:
    """按**风险性质**归纳（每条归入首个命中主题；未命中归"其他"）。"""
    buckets: Dict[str, list] = {}
    order = [t[0] for t in _RISK_THEMES] + ["其他"]
    for name in order:
        buckets[name] = []
    for p in problems:
        text = " ".join(str(p.get(k) or "") for k in ("title", "suspect"))
        hit = "其他"
        for name, kws in _RISK_THEMES:
            if any(kw in text for kw in kws):
                hit = name
                break
        buckets[hit].append(_short_title(p.get("title")))
    out = []
    for name in order:
        items = buckets.get(name) or []
        if items:
            out.append({"theme": name, "count": len(items), "items": items})
    return out


def _cost_reconciliation(rd: Dict[str, Any]) -> Dict[str, Any]:
    """★ 2026-09-26 三方闭环：发票类目口径 / 账面口径 / 差异待核。

    为什么需要（用户指令）："取得发票中哪些属于主营业务成本"只解决了**分子挑得准**，
    但发票口径天然偏小（人工成本、制造费用不在进项发票里）→ 若只用它当主营成本会
    得出毛利率虚高，反而**掩盖风险**。故必须与账面口径勾稽，差额如实列"待核"。

    铁律：账面口径只认**发生额**（序时账借方发生额 / 科目余额表本期发生额）。
    **损益类科目期末余额恒为 0，绝不可用**；检测到"期末余额"来源一律拒收。
    取不到就明说"未取得"，不得用默认值静默顶替。
    """
    out: Dict[str, Any] = {
        "invoice_cost": None, "invoice_cost_count": 0,
        "book_cost": None, "book_cost_source": "",
        "diff": None, "diff_pct": None, "status": "未取得", "note": "",
    }
    # ── ① 发票类目口径（成本类进项合计）──
    try:
        bcc = ((rd.get("engine_status") or {}).get("biz_cost_classification")) or {}
        # 注意：落盘的 engine_status 里只存**汇总值**（core_cost_amount / core_cost_count），
        # 不发票明细列表（core_cost_invs 未序列化）。故优先取汇总值，明细仅在存在时兜底累加。
        from engine.numparse import to_number as _ton
        _amt = _ton(bcc.get("core_cost_amount"))
        if _amt is not None:
            out["invoice_cost"] = round(float(_amt), 2)
            _n = _ton(bcc.get("core_cost_count"))
            out["invoice_cost_count"] = int(_n) if _n is not None else 0
        else:
            core = bcc.get("core_cost_invs") or []
            if core:
                _s = 0.0
                for inv in core:
                    _v = _ton((inv or {}).get("amount", (inv or {}).get("total")))
                    if _v:
                        _s += float(_v)
                out["invoice_cost"] = round(_s, 2)
                out["invoice_cost_count"] = len(core)
    except Exception:
        pass

    # ── ② 账面口径（只认发生额）──
    try:
        from engine.numparse import to_number as _ton
        for f in (rd.get("all_findings") or []):
            om = (f or {}).get("observed_metrics") or {}
            if not isinstance(om, dict) or om.get("book_cost_total") is None:
                continue
            src = str(om.get("book_cost_source") or "")
            if "期末余额" in src:        # 损益类科目期末为 0，拒收
                continue
            _v = _ton(om.get("book_cost_total"))
            if _v is None:
                continue
            out["book_cost"] = round(float(_v), 2)
            out["book_cost_source"] = src or "未标注来源"
            break
    except Exception:
        pass

    inv, book = out["invoice_cost"], out["book_cost"]
    if inv is not None and book is not None:
        d = round(float(inv) - float(book), 2)
        out["diff"] = d
        out["diff_pct"] = (round(d / float(book) * 100, 2) if book else None)
        # 阈值：相对 >10% 且绝对 >1 万（与 VR060 双口径同一阈值口径）
        if book and abs(d) > 10000 and abs(d / float(book)) > 0.10:
            out["status"] = "差异超阈值（待核）"
            out["note"] = ("两口径差异已超阈值（相对>10% 且绝对>1万元）。可能成因：未开票采购、"
                           "暂估入账、人工与制造费用不在进项发票、票货不符、虚列成本；"
                           "须逐项核对后方可定性。")
        else:
            out["status"] = "两口径基本吻合"
            out["note"] = "两口径差异在阈值内（相对≤10% 或绝对≤1万元），属正常暂估或不开票采购范围。"
    elif inv is not None:
        out["status"] = "账面口径未取得"
        out["note"] = "本轮未取得可确认的账面主营业务成本（需序时账借方发生额或科目余额表本期发生额），无法完成勾稽。"
    elif book is not None:
        out["status"] = "发票口径未取得"
        out["note"] = "本轮未取得成本类进项发票口径，无法完成勾稽。"
    else:
        out["status"] = "两口径均未取得"
        out["note"] = "本轮未取得发票类目口径与账面口径，主营成本勾稽未参与。"
    return out


def build_overall_conclusion(report_data: Any,
                             problems: Optional[List[dict]] = None,
                             further: Optional[List[dict]] = None,
                             inspector_reasoning: Optional[dict] = None) -> Dict[str, Any]:
    """生成「本轮检查总体结论」。

    返回：
      {
        "paragraphs": [段落文本...],       # 直接可按顺序渲染的纯文本段落
        "tiers": [{"level","label","count","items":[...]}, ...],
        "tax_types": [{"name","count"}, ...],
        "industry": {"name","source","confidence","registered","benchmark_name",
                     "observations","candidates","benchmark_source"},
        "conflict": "登记口径≠实际口径"的说明（无则空串）,
        "counts": {...},
      }
    """
    rd = report_data if isinstance(report_data, dict) else {}
    err = rd.get("enterprise_readable_report") or {}
    if problems is None:
        problems = err.get("confirmed_problems") or []
    if further is None:
        further = err.get("further_checks") or []
    problems = [p for p in (problems or []) if isinstance(p, dict)]
    further = [f for f in (further or []) if isinstance(f, dict)]

    file_results = rd.get("file_results") or []
    files_count = rd.get("files_count") or len(file_results)
    types = {fr.get("type") for fr in file_results if isinstance(fr, dict)}
    cats = len([t for t in types if t])

    te = rd.get("target_entity") or {}

    # ── 分层（完全取实测 risk_level）──
    tiers: List[Dict[str, Any]] = []
    for lv in _TIER_ORDER:
        items = [p for p in problems if str(p.get("risk_level") or "") == lv]
        if items:
            tiers.append({
                "level": lv,
                "label": _TIER_LABEL.get(lv, lv),
                "count": len(items),
                "items": [_short_title(p.get("title")) for p in items],
            })

    # ── 涉及税种（取实测 taxes）──
    tc: Counter = Counter()
    for p in problems:
        for t in (p.get("taxes") or []):
            if t:
                tc[str(t)] += 1
    tax_types = [{"name": k, "count": v} for k, v in tc.most_common()]

    # ── 涉嫌方向（数据驱动）──
    directions = _collect_directions(problems)

    # ── 行业口径（原样引用，含来源与冲突）──
    ib: Dict[str, Any] = {}
    if isinstance(inspector_reasoning, dict):
        ib = inspector_reasoning.get("industry_benchmark") or {}
    try:
        cand = te.get("_industry_candidates") or {}
        if not isinstance(cand, dict):
            cand = {}
    except Exception:
        cand = {}
    ind = {
        "name": str(te.get("industry") or "").strip(),
        "source": str(te.get("_industry_source") or "").strip(),
        "confidence": str(te.get("_industry_confidence") or "").strip(),
        "registered": str(te.get("industry_registered") or "").strip(),
        "benchmark_name": str(ib.get("benchmark_name") or ""),
        "benchmark_source": str(ib.get("industry_source") or ""),
        "observations": ib.get("observations") or [],
        "candidates": cand,
    }
    reg = str(cand.get("工商登记") or ind["registered"] or "").strip()
    inv = str(cand.get("销项发票品名推断") or "").strip()
    conflict = ""
    if reg and inv and reg != inv:
        # ★ 2026-09-26 用户口径：「变名开票」是重定性词，改为中性表述（只提出问题，不定性）。
        conflict = (f"登记口径为「{reg}」，而销项发票品名指向「{inv}」，两者不一致；"
                    f"开票品名与实际经营是否一致，需核实是否存在超范围经营、开票品名不实等情形。")

    # ── 已核定 / 待定性 ──
    verified = sum(1 for p in problems if str(p.get("conclusion_grade") or "") == "已核定")
    pending = len(problems) - verified

    # ══════════ 组装段落 ══════════
    P: List[str] = []

    P.append(
        f"编制声明：本轮已重新读取全部资料（{files_count} 份，归为 {cats} 类）并重新计算，"
        f"以下为本轮复算结论，独立于此前任何一轮报告。"
    )

    # ★ 开篇总括（用户要求：先给整体情况与重点结果，再展开细节）
    _lv = {t["level"]: t["count"] for t in tiers}
    _pv = int(_lv.get("待核验", 0) or 0)
    _themes = _group_by_theme(problems)
    _top = "、".join("%s（%d 项）" % (g["theme"], g["count"]) for g in _themes[:3])
    _lv_txt = ""
    if any(_lv.get(k) for k in ("高风险", "中风险", "低风险")):
        _lv_txt = ("，其中高风险 %d 项、中风险 %d 项、低风险 %d 项"
                   % (int(_lv.get("高风险", 0)), int(_lv.get("中风险", 0)), int(_lv.get("低风险", 0))))
    P.append(
        "检查范围与结果概览：本轮依据已上传的 %d 类资料（%d 份）实施检查，共识别并列示 %d 项待核实风险事项%s%s。"
        "风险主要集中在：%s。"
        % (cats, files_count, len(problems), _lv_txt,
           ("，另有 %d 项因证据不足暂列待核验" % _pv) if _pv else "",
           _top or "（本轮未形成可归纳的风险主题）")
    )

    # 行业与对标
    # ★ 2026-09-26 用户口径：**行业认定不能写得太确定**。区分两件事——
    #   ①「测算口径」可以用销项发票品名（用户认可其贴近实际经营），但必须写明是"初步按…口径测算"；
    #   ②「行业认定」应以登记经营范围、实际收入构成、合同与发票品名为准，**待核实**。
    #   同时并列登记口径，不把推断包装成已认定。
    if ind["name"]:
        seg = (f"行业口径：本轮初步按销项发票品名指向的「{ind['name']}」口径测算"
               f"（来源：{ind['source'] or '未标注'}）。")
        if ind["registered"] and ind["registered"] != ind["name"]:
            seg += f"同时列示登记口径「{ind['registered']}」。"
        seg += "行业认定应以登记经营范围、实际主营业务收入构成、合同和发票品名为准，待核实。"
        obs = ind["observations"]
        if obs:
            o = obs[0] or {}
            seg += (f"据该测算口径对照行业基准，本企业{o.get('metric', '')}{o.get('actual', '')}%"
                    f"（行业{o.get('benchmark', '')}），{o.get('direction', '')}。{o.get('why', '')}")
        if conflict:
            seg += conflict
        P.append(seg)

    # 风险总量与税种分布
    # ★ 2026-09-26 用户口径："确认 N 项风险事项"措辞太强且与后文"均需补证后定性"互相矛盾；
    #   统一为「识别并列示 N 项**待核实风险事项**」+「尚不构成违法定性」——
    #   名词核心仍是"风险事项"（肯定它是风险），"待核实"只作定语。
    if problems:
        tax_txt = ""
        if tax_types:
            tax_txt = ("涉及税种：" + "、".join(f"{t['name']}{t['count']}项" for t in tax_types[:6])
                       + "（上述为「事项—税种关联次数」，一项可涉及多个税种，非事项数）。")
        dir_txt = ""
        if directions:
            dir_txt = "可能涉及的涉嫌方向（待核实）包括：" + "、".join(directions) + "等。"
        P.append(
            f"本轮识别并列示 {len(problems)} 项待核实风险事项，均存在资料层面的差异或异常线索，"
            f"尚不构成违法定性。{tax_txt}{dir_txt}"
        )

    # ★ 按**风险性质**归纳（用户要求：总结归纳风险情况，而非只按等级平铺列举）
    if _themes:
        _parts = []
        for g in _themes:
            _rep = "、".join(g["items"][:3])
            _suffix = "等" if len(g["items"]) > 3 else ""
            _parts.append("%s %d 项（%s%s）" % (g["theme"], g["count"], _rep, _suffix))
        P.append("按风险性质归纳：" + "；".join(_parts) + "。")

    # 分层点名
    # ★ 2026-09-26 用户口径：**"待核验"不是风险等级**。等级只有 高/中/低，
    #   "待核验/信息"是**证据状态**，不能与等级并列（否则"待核验5项"与"低风险5项"分类不统一）。
    _LEVELS = ("高风险", "中风险", "低风险")
    lv_tiers = [t for t in tiers if t["level"] in _LEVELS]
    st_tiers = [t for t in tiers if t["level"] not in _LEVELS]
    if lv_tiers:
        P.append("风险等级暂分为" + "、".join(f"{t['label']}{t['count']}项" for t in lv_tiers) + "。")
        P.append("风险等级按潜在税额、涉及金额、证据缺口、是否涉及虚开或偷税、补证紧迫性综合排序，仅供参考。")
        for t in lv_tiers:
            P.append(f"{t['label']}{t['count']}项：" + "；".join(t["items"]) + "。")
    for t in st_tiers:
        if t["level"] == "待核验":
            P.append(f"另有 {t['count']} 项因证据不足，暂列为待核验事项，不参与风险等级排序："
                     + "；".join(t["items"]) + "。")
        else:
            P.append(f"另有 {t['count']} 项为{t['label']}（非风险等级），供参考："
                     + "；".join(t["items"]) + "。")

    # ★ 三方闭环：发票类目口径 / 账面口径 / 差异待核
    cost_recon = _cost_reconciliation(rd)
    _cr_txt = ""
    if cost_recon["invoice_cost"] is not None or cost_recon["book_cost"] is not None:
        _inv_txt = (f"{cost_recon['invoice_cost']:,.2f} 元（{cost_recon['invoice_cost_count']} 张）"
                    if cost_recon["invoice_cost"] is not None else "未取得")
        _bk_txt = (f"{cost_recon['book_cost']:,.2f} 元（来源：{cost_recon['book_cost_source']}）"
                   if cost_recon["book_cost"] is not None else "未取得")
        _cr_txt = f"主营业务成本三方勾稽：发票类目口径 {_inv_txt}；账面口径 {_bk_txt}。"
        if cost_recon["diff"] is not None:
            _cr_txt += f"差异 {cost_recon['diff']:,.2f} 元（{cost_recon['diff_pct']}%），{cost_recon['status']}。"
        else:
            _cr_txt += f"{cost_recon['status']}。"
        _cr_txt += cost_recon["note"]
        P.append(_cr_txt)

    # 法律边界（与上文的"待核实风险事项"同一口径，不再重复"已确认"式强断言）
    if problems:
        if verified > 0:
            grade_txt = f"其中账面对账可即时核定的 {verified} 项已直接给出结论，其余 {pending} 项需补充外部证据后方可定性。"
        else:
            grade_txt = "本轮各项均需补充外部证据后方可定性。"
        P.append(
            f"本轮已逐项列明检查依据、可能涉及的涉嫌方向与需补资料；{grade_txt}"
            f"风险等级与优先顺序仅表示补证紧迫性与潜在税务影响，不表示已经认定违法。"
        )

    # 未完成
    if further:
        P.append(
            f"另有 {len(further)} 项因资料缺失、资料不完整或影响范围尚未查清，本轮暂不下结论；"
            f"这部分表示检查范围受限，不表示已经发生相应违法。"
        )

    # 下一步
    P.append(
        "请企业负责人先按上述风险程度与优先顺序组织处理，并按要求补齐资料；"
        "完成真实更正和资料补充后，发起新一轮全量复查，继续核对原问题是否处理完成，"
        "以及补充资料是否带出新的关联问题。"
    )

    return {
        "paragraphs": P,
        "tiers": tiers,
        "tax_types": tax_types,
        "directions": directions,
        "industry": ind,
        "conflict": conflict,
        # ★ 按风险性质归纳（供第一章台账/前端按主题展示）
        "risk_themes": _themes,
        # ★ 三方闭环：发票类目口径 / 账面口径 / 差异待核（供第一章台账渲染三列）
        "cost_reconciliation": cost_recon,
        "counts": {
            "files": files_count,
            "categories": cats,
            "total": len(problems),
            "verified": verified,
            "pending": pending,
            "further": len(further),
            "by_level": {t["level"]: t["count"] for t in tiers},
        },
    }
