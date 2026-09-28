# -*- coding: utf-8 -*-
"""「一、本轮检查总体结论」生成器 —— 唯一权威（2026-09-26）

用户要求（2026-09-26）：该章必须**从 findings 实测派生**，不得手写模板。
凡数字（收到资料数、风险项数、各等级计数）、点名清单、涉及税种、行业口径，
一律取实测；新增或减少一条发现时**无需改本模块**（只认数据，不认特例）。

编辑标准（用户 2026-09-26 复核后定稿，**务必遵守**）：
  ① 行业认定**不得写得太确定**：销项发票品名只作「**初步测算口径**」，须并列登记口径，
     并声明"行业认定应以登记经营范围、实际主营业务收入构成、合同和发票品名为准，待核实"。
     禁用"变名开票"等重定性词，改中性表述（"开票品名与实际经营是否一致，需核实…"）。
  ② 事项措辞用「**涉嫌风险事项**」——"涉嫌"本身即含待核实之意（**不再叠加"待核实"**，用户 2026-09-27），
     名词核心是"风险事项"；紧跟"尚不构成违法定性"。禁用"已确认 N 项风险事项"式强断言。
  ③ **等级与状态分离**：风险等级只有 高/中/低；「待核验」是**证据状态**，
     必须单列并声明"不参与风险等级排序"，不得与"低风险"并列（分类不统一）。
  ④ 须写明**分级依据**（潜在税额 / 涉及金额 / 证据缺口 / 是否涉及虚开或偷税 / 补证紧迫性）。
  ⑤ 税种统计须注明是「**事项—税种关联次数**，非事项数」（一项可涉多个税种）。
  ⑥ 涉嫌方向写「**可能**涉及的涉嫌方向」（"涉嫌"已含待核实，**不再写"（待核实）"**，用户 2026-09-27），
     不得写"已指向"。
  ⑧ 本章是**总述与总体结论**，只作概论：行业对标偏离、成本两口径勾稽等**细节分析归专项章节/风险事项台账**，
     本章不展开（用户 2026-09-27）。
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
        # ★ 2026-09-27 用户口径：这是**事实 + 观点**，不写"需核实"式免责语（观点用"指向…的可能"）。
        conflict = (f"登记经营范围为「{reg}」，销项发票品名指向「{inv}」，两者不一致；"
                    f"开票品名与实际经营是否一致，指向超范围经营或开票品名不实的可能。")

    # ── 已核定 / 待定性 ──
    verified = sum(1 for p in problems if str(p.get("conclusion_grade") or "") == "已核定")
    pending = len(problems) - verified

    # ══════════ 组装段落 ══════════
    P: List[str] = []

    P.append(
        "编制声明：本轮已重新读取全部资料并重新计算，按“资料合规性核验 → 多源交叉比对 → "
        "资金流向穿透 → 行业基准对标 → 规则与红线扫描 → 证据链闭合度评估”六步程序实施检查，"
        "以下为本轮复算结论，独立于此前任何一轮报告。"
    )

    # ★ 开篇总括（用户要求：先给整体情况与重点结果，再展开细节）
    _lv = {t["level"]: t["count"] for t in tiers}
    _high = int(_lv.get("高风险", 0) or 0)
    _mid = int(_lv.get("中风险", 0) or 0)
    _low = int(_lv.get("低风险", 0) or 0)
    _pend = int(_lv.get("待核验", 0) or 0)
    _grade = "低"
    if _high >= 3:
        _grade = "高"
    elif _high >= 1 or _mid >= 5:
        _grade = "较高"
    elif _mid >= 1 or len(problems) > 0:
        _grade = "中等"
    _themes = _group_by_theme(problems)
    tax_txt = ""
    if tax_types:
        tax_txt = ("涉及税种：" + "、".join(f"{t['name']}{t['count']}项" for t in tax_types[:6])
                   + "（上述为「事项—税种关联次数」，一项可涉及多个税种，非事项数）。")
    dir_txt = ""
    if directions:
        dir_txt = "可能涉及的涉嫌方向包括：" + "、".join(directions) + "等。"
    if problems:
        P.append(
            "检查范围与结果概览：本轮依据已上传的 %d 类资料（%d 份）实施检查，共识别并列示 %d 项涉嫌风险事项，"
            "均存在资料层面的差异或异常线索，尚不构成违法定性。%s%s"
            % (cats, files_count, len(problems), tax_txt, dir_txt)
        )
    else:
        P.append(
            "检查范围与结果概览：本轮依据已上传的 %d 类资料（%d 份）实施检查，未识别到涉嫌风险事项。"
            % (cats, files_count)
        )

    # ★ 2026-09-29（C3 风险组合画像）：跨业务轴组合信号 → 总述显式提示多税种联动稽查。
    _cp_src = ((rd.get("comprehensive", {}) or {})
               .get("redline_detection", {}) or {}).get("summary", {}) or {}
    for _cp in (_cp_src.get("combo_profiles") or []):
        if not isinstance(_cp, dict):
            continue
        _labels = "、".join(_cp.get("axis_labels") or [])
        P.append(
            "【多税种联动稽查信号】本企业在「%s」等多个业务环节同时触发税务风险指标"
            "（共 %d 个环节），呈现业务全链条勾稽断裂的系统性异常，而非孤立单点问题。"
            "建议启动多税种联动稽查：上述疑点指向收入—成本—资金—票据全链条勾稽断裂，"
            "单一税种核查难以还原事实，应统筹增值税、企业所得税、个人所得税及印花税等"
            "跨税种联动核查，并重点追查「票流—资金流—货物流—账簿」四流是否一致。"
            % (_labels, int(_cp.get("axis_count") or 0))
        )

    # 行业与对标
    # ★ 2026-09-26 用户口径：**行业认定不能写得太确定**。区分两件事——
    #   ①「测算口径」可以用销项发票品名（用户认可其贴近实际经营），但必须写明是"初步按…口径测算"；
    #   ②「行业认定」应以登记经营范围、实际收入构成、合同与发票品名为准，**待核实**。
    #   同时并列登记口径，不把推断包装成已认定。
    if ind["name"]:
        # ★ 2026-09-27 用户口径：总述**只给检查分析的事实与由此提出的观点**——
        #   不写"待核实"式免责语，也不写"见某章/本章不展开"式引导说明。
        seg = (f"行业口径：本轮按销项发票品名指向的「{ind['name']}」口径测算"
               f"（来源：{ind['source'] or '未标注'}）。")
        if conflict:
            seg += conflict
        P.append(seg)

    # 风险总量与税种、涉嫌方向已并入上文「检查范围与结果概览」，不再单列（避免同一件事说两遍）。

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
        P.append(
            "风险等级评定：本轮整体风险程度评定为「%s」。风险等级按潜在税额、涉及金额、证据缺口、"
            "是否涉及虚开或偷税、补证紧迫性综合排序，仅供参考；各风险等级事项列示如下。"
            % _grade
        )
        for t in lv_tiers:
            P.append(f"{t['label']} {t['count']} 项：" + "；".join(t["items"]) + "。")
    for t in st_tiers:
        if t["level"] == "待核验":
            P.append(f"待核验（证据不足，不参与风险等级排序）{t['count']} 项："
                     + "；".join(t["items"]) + "。")
        else:
            P.append(f"{t['label']}（非风险等级，供参考）{t['count']} 项："
                     + "；".join(t["items"]) + "。")

    # ★ 企业整体风险综合评价（定调句：整体等级 + 主要风险领域 + 遵从评价，合成一段结论）
    _top = sorted(_themes, key=lambda g: -int(g.get("count") or 0))[:2]
    _total_p = len(problems)
    _sum_top = sum(int(g.get("count") or 0) for g in _top)
    _share = (_sum_top / _total_p * 100) if _total_p else 0.0
    if len(_top) >= 2:
        _top_clause = "风险高度集中于「%s」与「%s」两个领域，二者合计 %d 项、占全部涉嫌风险事项的 %.0f%%" % (
            _top[0].get("theme"), _top[1].get("theme"), _sum_top, _share)
    elif _top:
        g0 = _top[0]
        _top_clause = "主要风险领域为%s（%d 项，占全部涉嫌风险事项的 %.0f%%）" % (
            g0.get("theme"), g0.get("count"),
            (g0.get("count") / _total_p * 100 if _total_p else 0.0))
    else:
        _top_clause = "本轮暂无可归纳的主要风险领域"
    P.append(
        "企业整体风险综合评价：综合风险程度评定与问题类型分布，该企业整体税务风险等级为「%s」；%s。"
        "结合资料与核算管理尚不完备、多项异常线索指向具体涉嫌方向的实际情况，"
        "本轮对该企业纳税遵从的总体评价为：在已提交资料范围内呈现较高风险敞口，"
        "但主观故意性质尚不能认定，须以补证与核实为前提，再行判断其纳税义务履行的真实状况。"
        % (_grade, _top_clause)
    )

    # ★ 2026-09-27（用户要求）：主营业务成本三方勾稽**不在总述展开**——它是细节分析，
    #   归「主营业务成本两口径勾稽明细」（第三章台账后）与风险事项台账（VR060 / 行业对标）。
    #   此处仍计算 cost_recon，供返回字段（cost_reconciliation）与台账消费，只是不再输出段落。
    cost_recon = _cost_reconciliation(rd)

    # 对企业纳税遵从情况的总体看法（分层：合规定性 / 主观故意；不得定性）
    if problems:
        if verified > 0:
            grade_txt = f"其中账面对账可即时核定的 {verified} 项已直接给出结论，其余 {pending} 项需补充外部证据后方可定性；"
        else:
            grade_txt = "本轮各项均需补充外部证据后方可定性；"
        P.append(
            "对企业纳税遵从情况的总体看法：本轮已逐项列明检查依据、可能涉及的涉嫌方向与需补资料；"
            + grade_txt
            + "风险等级与优先顺序仅表示补证紧迫性与潜在税务影响，不表示已经认定违法。"
            + "主观故意方面：本轮不作认定——现有资料不足以判断上述差异系管理疏漏、核算差错，"
            "还是存在主观故意；须经补证与核实后另行判断。"
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

    # ★ 监管态度与后续处理建议（分级分类；各类项数已在上文列明，此处不再重复数字）
    _pos = []
    if _low:
        _pos.append("提示提醒：对低风险事项，建议以提示提醒方式要求企业自行规范与整改")
    if _mid:
        _pos.append("补证核实：对中风险事项，建议限期要求企业补充合同、物流、资金、入库等外部证据，逐项排除疑点")
    if _high:
        _pos.append("重点关注：对高风险事项（证据相对集中、涉及隐匿收入或虚开发票方向），建议列为后续优先检查事项")
    if _pend:
        _pos.append("待核验事项：对证据不足事项，建议先行补证，不宜在证据补齐前作出处理结论")
    if further:
        _pos.append("限期补正资料：对因资料缺失未能实施的检查，建议限期要求企业补齐后再行检查")
    P.append("监管态度与后续处理建议（分级分类）：" + "；".join(_pos) + "。")
    P.append("需要说明：本部分为工作建议，不构成税务处理、行政处罚或移送决定；"
             "是否达到移送标准，应在证据补齐并依法核实后另行判断。")
    # ★ 2026-09-27 用户口径：**删去本章末的「边界声明」**——该声明是"说明"性质，
    #   第六章「报告性质和使用说明」已由 `inspector_perspective.administrative_boundary`
    #   （文书性质说明）承载，两处重复；本章只留事实与观点。

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
