# -*- coding: utf-8 -*-
"""「一、本轮检查总体结论」生成器 —— 唯一权威（2026-09-26）

用户要求（2026-09-26）：该章必须**从 findings 实测派生**，不得手写模板。
凡数字（收到资料数、风险项数、各等级计数）、点名清单、涉及税种、行业口径，
一律取实测；新增或减少一条发现时**无需改本模块**（只认数据，不认特例）。

编辑标准（用户 2026-09-26 复核后定稿，**务必遵守**）：
  ① 行业认定**不得写得太确定**：销项发票品名只作「**初步测算口径**」，须并列登记口径，
     并声明"行业认定应以登记经营范围、实际主营业务收入构成、合同和发票品名为准，尚需核实"。
     禁用"变名开票"等重定性词，改中性表述（"开票品名与实际经营是否一致，需核实…"）。
  ② 事项措辞用「**涉嫌风险事项**」——"涉嫌"本身即含尚需核实之意（**不再叠加"尚需核实"**，用户 2026-09-27），
     名词核心是"风险事项"；紧跟"尚不构成违法定性"。禁用"已确认 N 项风险事项"式强断言。
  ③ **等级与状态分离**：风险等级只有 高/中/低；「待核验」是**证据状态**，
     必须单列并声明"不参与风险等级排序"，不得与"低风险"并列（分类不统一）。
  ④ 须写明**分级依据**（潜在税额 / 涉及金额 / 证据缺口 / 是否涉及虚开或偷税 / 补证紧迫性）。
  ⑤ 税种统计须注明是「**事项—税种关联次数**，非事项数」（一项可涉多个税种）。
  ⑥ 涉嫌方向写「**可能**涉及的涉嫌方向」（"涉嫌"已含尚需核实，**不再写"（尚需核实）"**，用户 2026-09-27），
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

# ★ 等级展示标签唯一权威（`counts.by_level` 保权威键，展示另走 by_level_display）
from engine.risk_levels import display_label as _display_label

# 分层顺序：按风险程度由重到轻（与 findings.risk_level 词表一致）
_TIER_ORDER = ["高风险", "中风险", "待核验", "低风险", "信息"]
# ★ 2026-10-06：展示标签转发唯一权威 `risk_levels.display_label`（原先此处硬编码一份）
_TIER_LABEL: Dict[str, str] = {_lv: _display_label(_lv) for _lv in _TIER_ORDER}

# 涉嫌方向词表（**数据驱动**：只在真实 suspect 文本中出现时才列出，命不中不写）
_DIRECTION_VOCAB = [
    "隐匿收入", "隐瞒收入", "不入账的收入", "虚开发票", "接受虚开发票", "为他人代开",
    "虚列成本", "虚增成本", "虚列费用", "虚增税前扣除", "虚列人员", "虚增人员",
    "资金回流", "资金空转", "转移利润", "变相分配", "公私混同",
    "少缴税款", "少代扣代缴", "未代扣代缴", "拆分收入", "虚抵",
]


def _short_title(t: Any) -> str:
    """标题去掉「：后缀说明」，只留主事件名（点名/列举用）。

    ★★ 2026-10-03（用户复核第一章：列举里出现「企业所得税贡献率偏低（对应风险指标」这种
      括号未闭合的残句）：**只在括号外的冒号处切分**。
      旧实现 `s.split("：")[0]` 会切在**括注内部**的冒号上——标题裁剪后形如
      「X（对应风险指标：Y；本项仅涉及…）」，第一个冒号在括号里，切完就留下半截括号。
      现按括号深度扫描，只在深度 0 处切；并在收尾做一次**括号配平**（多余左括号补右括号），
      保证任何截断都留下结构完整的句子。
    """
    s = str(t or "").strip()
    depth = 0
    cut = -1
    for i, ch in enumerate(s):
        if ch in "（(":
            depth += 1
        elif ch in "）)":
            depth = max(0, depth - 1)
        elif ch in "：:" and depth == 0:
            cut = i
            break
    if cut > 0:
        s = s[:cut]
    # 括号配平：左括号多于右括号时补齐（截断可见、结构完整）
    for _o, _c in (("（", "）"), ("(", ")")):
        _d = s.count(_o) - s.count(_c)
        if _d > 0:
            s += _c * _d
    return s.strip()


def _industry_scope_covers(te: Any) -> Optional[bool]:
    """读解析器给出的「本轮行业是否被经营范围涵盖」三态结论（True/False/None）。

    ★ 权威来源是 `industry_resolver.resolve_industry` 本轮产出的 `_industry_resolved`，
      **不在本文件重算** —— 下游一重算就会出现"解析器说涵盖、文案说冲突"的口径打架。
      解析器未给出（老产物/其他入口）时回退 None（无从判定 → 不认定冲突）。
    """
    if not isinstance(te, dict):
        return None
    res = te.get("_industry_resolved")
    if isinstance(res, dict) and "scope_covers" in res:
        return res.get("scope_covers")
    return None


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
                    "银行收款大于", "私户", "个人账户收取", "未纳入",
                    # 2026-10-03 补词（判据只看标题后，按标题实名补）
                    "未开票收入", "收入完整", "个人账户收取经营"]),
    ("发票与交易真实性", ["虚开发票", "接受虚开", "为他人代开", "红字冲销", "作废发票",
                          "有进无销", "有销无进", "开票额", "票面", "品名",
                          "数字特征", "金额分布", "整十整百", "金额异常"]),
    ("成本费用真实性", ["虚列成本", "虚增成本", "虚列费用", "白条", "成本列支", "期间费用",
                        "无真实业务", "虚增税前扣除", "成本费用", "列支费用", "调节"]),
    ("资金流向", ["资金回流", "资金空转", "公转私", "公私混同", "回流", "循环",
                  # 2026-10-03 补词：银行流水/余额滚动类属"资金流"性质
                  "银行流水", "余额滚动", "流水勾稽", "资金流水"]),
    ("工资社保与个税", ["工资", "社保", "个税", "劳务报酬", "代扣代缴", "虚列人员", "用工",
                        # 2026-10-03 补词：住房公积金属"工资社保（用工附加）"性质
                        "住房公积金", "公积金"]),
    ("税费申报", ["申报", "印花税", "附加", "计税依据", "税负", "少缴",
                  # ★ 2026-10-03：主题判定改为只看标题后补入的两类**同一性质**事项
                  #   （所得税贡献率/亏损仍经营属"税费申报与税负"性质，不是"收入完整性"）。
                  "贡献率", "长期亏损",
                  # 2026-10-03 补词（标题实名）：扣除限额/纳税调整/表间勾稽同属"税费申报"性质
                  "扣除限额", "纳税调整", "勾稽", "表间"]),
    ("关联交易", ["关联", "六员", "转移利润", "利益输送"]),
    ("经营合理性", ["持续经营", "毛利率", "商业合理性", "集中度", "地域分布"]),
]


# ★ 主题归类的**前置定向规则**（标题命中即优先归类，早于通用关键词匹配）。
#   用途：纠正"标题能定性、但通用关键词被 `suspect` 的泛化方向带偏"的事项。
#   新增同类只加一行；命中后**不再**走关键词匹配。
_THEME_OVERRIDE: List[tuple] = [
    # 所得税贡献/长期亏损属"税费申报与税负"性质，不是"收入完整性"
    #（其 risk_level_basis 亦为"长期亏损仍持续经营：收入或成本不实"，落点是所得税）
    ("税费申报", ("贡献率", "长期亏损")),
]


def _group_by_theme(problems: List[dict]) -> List[Dict[str, Any]]:
    """按**风险性质**归纳（每条归入首个命中主题；未命中归"其他"）。"""
    buckets: Dict[str, list] = {}
    order = [t[0] for t in _RISK_THEMES] + ["其他"]
    for name in order:
        buckets[name] = []
    for p in problems:
        # ★★ 2026-10-03（用户复核第一章：「企业所得税贡献率偏低」被错归入「收入完整性」）：
        #   根因是**判据文本混了 `suspect`** —— 它是红线包（要件包）的**泛化涉嫌方向**，
        #   对同一红线的所有情形通用（该案的 suspect 含"少列收入"），于是把一件"所得税贡献/税负"
        #   事项归进了"收入完整性"，首段据此写出的"风险集中于收入完整性与税费申报"归因随之失真。
        #   ⚠ 试过"只看标题"，结果 6 项掉进「其他」（标题过短/不含关键词）——
        #   说明这张关键词表的真问题是**缺词**，不是"看了 suspect"。故保留原文本口径，
        #   改用**标题级前置规则**做定向纠正（新增同类只加一行）。
        # ★★ 2026-10-03（用户："一并调"）：**判据文本只看标题**。
        #   `suspect` 是红线包（要件包）的**泛化涉嫌方向**（"虚开发票""隐匿收入""账外"），
        #   对同一红线的所有情形通用 ⇒ 会**抢先命中**排在前面的主题，把事项拉错类。
        #   实测 7 项被带偏：「数字特征异常」被"账外"拉进收入完整性、「成本列支的资金与负债」
        #   与「关联交易异常」被"虚开发票"拉进发票与交易真实性、「银行流水余额滚动」被"隐瞒收入"
        #   拉进收入完整性、「税前扣除限额超限」被"列支费用"拉进成本费用真实性、
        #   「表间勾稽四方比对」被"隐匿收入"拉进收入完整性、「供应商集中度」被"接受虚开"拉进发票类。
        #   ⚠ 上一轮试过"只看标题"失败（6 项落「其他」），真因是**关键词表缺词** —— 故本轮同时补词。
        text = str(p.get("title") or "")
        hit = "其他"
        _t = str(p.get("title") or "")
        for _th, _kws in _THEME_OVERRIDE:
            if any(_kw in _t for _kw in _kws):
                hit = _th
                break
        else:
            _t = ""    # 未命中前置规则 → 走下面的通用关键词匹配
        if _t:
            buckets[hit].append(_short_title(p.get("title")))
            continue
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


def compilation_declaration(report_data: Any) -> str:
    """编制声明 —— **唯一权威**（按轮次条件化）。

    ★ 2026-09-29（点评整改 P2-3）：外部点评实测「第1轮」的报告里写
      「本轮结论独立于此前任何一轮报告」——第 1 轮**不存在**"此前轮"，
      句子自相矛盾。同一句在 `overall_conclusion` / `inspection_overview` /
      `narrative_fresh` 三处各写一份，故收敛到本函数（单一权威）。
    """
    rd = report_data if isinstance(report_data, dict) else {}
    _cr = rd.get("compliance_round") or {}
    n = rd.get("analysis_round") or ( _cr.get("round_no") if isinstance(_cr, dict) else None) or 1
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 1
    tail = ""  # 2026-10-01 按用户定调：删除"首次检查/独立于前序轮次"等轮次元信息
    return (
        "编制声明：本轮已重新读取全部资料并重新计算，按“资料合规性核验 → 多源交叉比对 → "
        "资金流向穿透 → 行业基准对标 → 规则与红线扫描 → 证据链闭合度评估”六步程序实施检查，"
        "以下为本轮复算结论。" + tail
    )


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
    reg = str(cand.get("工商登记") or cand.get("经营范围推断") or ind["registered"] or "").strip()
    inv = str(cand.get("销项发票品名推断") or "").strip()
    _covers = _industry_scope_covers(te)

    # ★ 2026-10-02 重构（用户口径事故修复，行业无关、全行业通用）：
    #   旧实现只要「登记 ≠ 销项推断」就写「指向超范围经营或开票品名不实」——
    #   但经营范围是**宽口径许可清单**，正常公司必然同时挂多类业务
    #   （工商登记为商贸 ≠ 不能做广告传媒）。该行业若已被经营范围涵盖 ⇒ 根本不冲突，
    #   旧表述是**假冲突误报**。
    #   ⚠ 术语铁律：「商贸」是**工商登记行业**（Company.industry_code），不是"经营范围"；
    #     经营范围是另一份文本（business_scope）。此前三处文案把它写成"登记经营范围为「X」"，
    #     属概念混用，读者会以为"商贸"是从经营范围里读出来的。
    #   三态：True 已涵盖（不表述/中性说明）；False 未见及（中性提核查）；
    #        None 无从判定（只说本轮口径；若因**经营范围文本残缺**，须如实说明原因）。
    conflict = ""
    if reg and inv and reg != inv and _covers is False:
        # ★ 2026-09-26 用户口径：「变名开票」是重定性词，改为中性表述（只提出问题，不定性）。
        # ★ 2026-09-27 用户口径：这是**事实 + 观点**，不写"需核实"式免责语（观点用"指向…的可能"）。
        conflict = (f"工商登记行业为「{reg}」，销项发票品名指向「{inv}」，两者不一致；"
                    f"且「{inv}」在经营范围文本中未见行业级关键词，"
                    f"开票品名与实际经营是否一致，需核实。")
    elif reg and inv and reg != inv and _covers is True:
        conflict = (f"工商登记行业为「{reg}」，本轮销项开票品名指向「{inv}」；"
                    f"该行业已为经营范围所涵盖，不构成超范围经营，"
                    f"本轮按销项口径以「{inv}」作为行业基准。")
    elif reg and inv and reg != inv:
        # ★ 2026-10-02：无法判定时**必须说明原因**（文本残缺 vs 未提供），
        #   否则读者会把"我们拿到的资料不完整"误读成"经营范围里确实没有"。
        _scope_txt = str((te or {}).get("business_scope") or "")
        try:
            from engine.industry_resolver import scope_text_issue as _sti
            _issue = _sti(_scope_txt) or "经营范围文本无法用于判定"
        except Exception:
            _issue = "未取得可用的经营范围文本"
        conflict = (f"工商登记行业为「{reg}」，本轮销项开票品名指向「{inv}」；"
                    f"因{_issue}，无法核对该行业是否在许可范围内，"
                    f"本轮按销项口径以「{inv}」作为行业基准。")

    # ── 已核定 / 待定性 ──
    verified = sum(1 for p in problems if str(p.get("conclusion_grade") or "") == "已核定")
    pending = len(problems) - verified

    # ══════════ 组装段落（四段式执行摘要，用户 2026-10-08 定稿）══════════
    # ★★ 2026-10-08（用户：「请只重构报告第一章，不改其他章节。把第一章从'压缩版全文'
    #   改为真正的'执行摘要'，采用'总结—概括—抽象'三层结构」）：
    #   结构 =（一）检查性质与资料条件（总结）→（二）整体结论（概括）
    #         →（三）主线抽象（抽象）→（四）下一步动作（建议）。
    #   **删除四类"与后章重复"的内容**（用户点名）：
    #     ① 逐项/分级点名清单 → 改为"编号 R1~RN + 指向第二部分台账"；
    #     ② 事项—税种关联次数明细；③ 按风险性质归纳明细；④ 监管态度与后续处理建议详细分类。
    #   **保留**（不属重复、且是本章实质）：编制声明（六步程序）、资料条件、整体等级与分级依据、
    #     等级与证据状态分列、行业口径、涉嫌方向、检查受限记录、下一步动作。
    #   ⚠ 前端（`static/js/tax-doc-analysis.js`）**只渲染 `overall_conclusion.paragraphs`**
    #     （实测：`var oc = report.overall_conclusion; var ocParas = oc.paragraphs`）⇒
    #     本函数是第一章的**唯一改造点**，改这里即全站生效，**前端无需改**。
    #   ⚠ 数据不变量：`tiers` / `tax_types` / `directions` / `industry` / `conflict` /
    #     `risk_themes` / `cost_reconciliation` / `counts` 等**返回字段一律保持原样**
    #     （前端台账与多处闸门/用例据此取值），本次只改"给人看的段落"。
    #   ⚠ 已实测：同数据两轮产物第一章 diff = 0 段（确定性输出），故改这里必然改变前端第一章。
    P: List[str] = []

    # ── 派生量必须先于段落生成（结论段引用它们；踩坑：插在派生之前会 UnboundLocalError）──
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
    _total_p = len(problems)

    # 主要风险领域（取前二）：用于"风险集中于何处"的一句概括
    _top2 = sorted(_themes, key=lambda g: -int(g.get("count") or 0))[:2]
    _sum_top = sum(int(g.get("count") or 0) for g in _top2)
    _share = (_sum_top / _total_p * 100) if _total_p else 0.0
    if len(_top2) >= 2:
        _top_clause = ("风险高度集中于「%s」与「%s」两个领域，二者合计 %d 项、"
                       "占全部 %d 项涉嫌风险事项的 %.0f%%"
                       % (_top2[0].get("theme"), _top2[1].get("theme"), _sum_top, _total_p, _share))
    elif _top2:
        g0 = _top2[0]
        _top_clause = "主要风险领域为%s（%d 项，占全部 %d 项涉嫌风险事项的 %.0f%%）" % (
            g0.get("theme"), g0.get("count"), _total_p,
            (g0.get("count") / _total_p * 100 if _total_p else 0.0))
    else:
        _top_clause = "本轮暂无可归纳的主要风险领域"

    # ── 结论效力范围（资料受限 ⇒ 先限定结论效力范围，再给等级）──
    #   唯一权威：`enterprise_report.required_doc_coverage`（与本章「必查资料齐备性」、
    #   后面的检查受限记录**同源**，保证"章首说缺几类"与"后面列几项"一致）。
    #   取不到覆盖面信息时**不臆断**：不写限制语，也不谎称完整。
    _cov = None
    try:
        from engine.enterprise_report import required_doc_coverage as _rdc
        _cov = _rdc(report_data)
    except Exception:  # noqa: BLE001 —— 取不到就如实不限定，绝不臆造数字
        _cov = None
    _scope_clause = ""
    _cov_txt = ""
    if isinstance(_cov, dict):
        _cov_txt = ("%d 类（实际提供 %d 类、缺失 %d 类）"
                    % (_cov.get("total") or 0, _cov.get("complete") or 0,
                       _cov.get("missing_count") or 0))
        if _cov.get("limited"):
            _scope_clause = (
                "本轮结论受资料条件限制：必查资料共 %d 类，实际提供 %d 类、缺失 %d 类"
                "（缺失清单与各自影响见本章「本轮检查必查资料齐备性」及后面的检查受限记录），"
                "部分检查程序因此未能完成。故以下结论是「现有资料条件下的风险画像」，"
                "不等于对企业涉税情况的完整结论，补齐资料后须重新判断。"
                % (_cov.get("total") or 0, _cov.get("complete") or 0,
                   _cov.get("missing_count") or 0)
            )
    _level_lead = ("在资料受限的前提下，该企业的整体税务风险等级为「%s」"
                   if _scope_clause else "该企业整体税务风险等级为「%s」") % _grade

    # ══════（一）检查性质与资料条件（总结）══════
    #   ① 本轮**是什么检查**（性质）+ 资料条件（依据几类几份；必查几类、实际几类、缺几类）
    #      ——**只给计数与出处**，不逐名罗列（清单由紧随其后的「本轮检查必查资料齐备性」表承担，
    #      避免章内重复）；
    #   ② 本轮按什么程序做的（编制声明，唯一权威 `compilation_declaration`，按轮次条件化）。
    _p1 = ("（一）检查性质与资料条件：本轮为税务风险扫描工作底稿，依据已上传的 %d 类资料"
           "（%d 份）实施检查" % (cats, files_count))
    if _cov_txt:
        _p1 += "；按本轮检查必查资料口径共 %s" % _cov_txt
    _p1 += "。" + compilation_declaration(report_data)
    P.append(_p1)

    # 检查受限记录（属"资料条件"的补充；**不是风险疑点**，口径不同、不相互计入）
    #   ★ 保留本项目既有口径：① 说明两者关系与各自口径；② 逐项点名缺的是哪份资料；
    #     ③ 重申"检查受限 ≠ 已发生违法"。补齐后受影响程序将重新执行。
    if further:
        _blocked = []
        for _f in further:
            _t = str((_f or {}).get("title") or "")
            # 标题形如「未收到“合同文件”导致相关检查未完成」——用字符串截取取资料名，
            # 不引入 re（本模块未导入 re；曾因此差点整段抛错）。
            _name = ""
            for _o, _c in (("“", "”"), ('"', '"')):
                _a, _b = _t.find(_o), _t.find(_c, _t.find(_o) + 1)
                if _a >= 0 and _b > _a:
                    _name = _t[_a + 1:_b].strip()
                    break
            if _name and _name not in _blocked:
                _blocked.append(_name)
        _blocked_txt = ("，分别是：" + "、".join(_blocked)) if _blocked else ""
        P.append(
            f"另有 {len(further)} 项不属于风险疑点，而是因未收到相应资料、导致相关检查无法完成的"
            f"检查受限记录{_blocked_txt}；原因是检查所需资料未提供，不是已查出问题。"
            f"它与上面列示的 %d 项风险事项口径不同、不相互计入（本报告的风险事项合计 %d 项，"
            f"不因本段而增减）。补齐上述资料后，受影响的检查程序将重新执行；"
            f"本段只表示本轮检查范围受限，不表示已经发生相应违法。" % (len(problems), len(problems))
        )

    # ══════（二）整体结论（概括）══════
    #   ① 整体等级（资料受限时先限定效力范围）+ 主要风险领域 + 纳税遵从总体评价；
    #   ② 事项总数（**只在此处出现一次**）+ 分级依据 + 各等级计数 + 证据状态分列；
    #   ③ 行业口径 + 涉嫌方向（事实 + 观点）。
    #   ★ 等级与证据状态**必须分列**：等级只有 高/中/低；「证据不足」是证据状态，
    #     不参与风险等级排序（分类不统一会把状态混进等级）。
    if problems:
        P.append(
            "（二）整体结论：企业整体风险综合评价：" + _scope_clause
            + "%s；%s。结合资料与核算管理尚不完备、多项异常线索指向具体涉嫌方向的实际情况，"
            "本轮对该企业纳税遵从的总体评价为：在已提交资料范围内呈现较高风险敞口，"
            "但主观故意性质尚不能认定，须以补充资料与核实为前提，再行判断其纳税义务履行的真实状况。"
            % (_level_lead, _top_clause)
        )
        P.append(
            "本轮共识别并列示 %d 项涉嫌风险事项（编号 R1~R%d），逐项的依据、需补资料与复核情况"
            "见本报告第二部分风险事项台账；风险等级按潜在税额、涉及金额、证据缺口、"
            "是否涉及虚开或偷税、补充资料紧迫性五项综合评定：高风险 %d 项、中风险 %d 项、"
            "低风险 %d 项；另有「%s」%d 项属证据状态（证据不足），不参与风险等级排序，"
            "本报告不对任何一项作出违法认定。"
            % (len(problems), len(problems), _high, _mid, _low,
               _display_label("待核验"), _pend)
        )
    else:
        P.append(
            "（二）整体结论：企业整体风险综合评价：本轮未识别到涉嫌风险事项，"
            "整体税务风险等级为「%s」，报告不对企业作出任何违法认定。" % _grade
        )

    # 行业口径（原样引用解析器结论，含来源；冲突表述由三态 `scope_covers` 决定）
    #   ★ 行业认定**不得写得太确定**：销项发票品名只作"初步测算口径"，
    #     登记口径并列，是否一致需核实（中性表述，不用"变名开票"等重定性词）。
    if ind["name"]:
        seg = (f"行业口径：本轮按销项发票品名指向的「{ind['name']}」口径测算"
               f"（来源：{ind['source'] or '未标注'}）。")
        if conflict:
            seg += conflict
        P.append(seg)

    # 涉嫌方向（**数据驱动**：只在真实 suspect 文本中出现时才列，命不中不写）
    if directions:
        P.append("可能涉及的涉嫌方向包括：" + "、".join(directions) + "等。")

    # ══════（三）主线抽象（抽象）══════
    #   把逐条事项**抽象**为少数几条贯穿性主线（主题 + 项数 + 代表事项），
    #   而不是把 16 项/按等级平铺一遍。明细一律指向第二部分台账（不重复）。
    if _themes:
        _tops3 = sorted(_themes, key=lambda g: -int(g.get("count") or 0))[:3]
        _parts = []
        for _i, _g in enumerate(_tops3):
            _rep = "、".join(_g["items"][:3])
            _suf = "等" if len(_g["items"]) > 3 else ""
            _parts.append("%s「%s」%d 项，代表：%s%s"
                          % ("①②③"[_i], _g.get("theme"), _g.get("count"), _rep, _suf))
        P.append("（三）主线抽象：%d 条贯穿全部事项的主线（对应事项见第二部分风险事项台账）：%s。"
                 % (len(_tops3), "；".join(_parts)))

    # ══════（四）下一步动作（建议）══════
    P.append(
        "（四）下一步动作：请企业负责人先按上述风险程度与优先顺序组织处理，并按要求补齐资料；"
        "完成真实更正和资料补充后，发起新一轮全量复查，继续核对原问题是否处理完成，"
        "以及补充资料是否带出新的关联问题。"
    )
    P.append(
        "操作顺序建议：① 优先补齐影响面最广的缺失资料（清单见本章「本轮检查必查资料齐备性」）；"
        "② 按上文（三）的主线顺序组织核实；③ 按各事项「需补资料」逐项补齐（见第二部分台账）；"
        "④ 资料补齐后重新执行受影响的检查程序（见第四部分整改验收与下一轮复查标准，"
        "其中含按风险由重到轻的分级分类处理要求）。"
        "本段为工作建议，不构成处理结论；其效力范围与使用限制见第五部分「报告性质和使用说明」。"
    )

    # ══════ 主营业务成本三方勾稽（不在总述展开；仍计算以供返回字段与台账消费）══════
    #   ★ 用户 2026-09-27：细节分析归「主营业务成本两口径勾稽明细」与风险事项台账
    #     （VR060 / 行业对标），本章只作概论，故不再输出段落。
    cost_recon = _cost_reconciliation(rd)

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
            # ★★ 2026-10-06（真实缺陷，自检抓到）：`by_level` 的**键**曾被改写成展示词
            #   「已列明」，于是「等级「已列明」报告 2 项、实际 0 项」——
            #   键与实际 `risk_level` 对不上，且把「待核验」与「尚需核实」两种来源
            #   **合并覆盖**（字典推导后写者覆盖前写者，丢计数）。
            #   违反项目铁律「**结构性枚举字段不得被当展示文本替换**」。
            #   现行口径：① `by_level` 用**权威等级名**（机器可核对、无丢失）；
            #             ② 展示写法另给 `by_level_display`（走权威 `risk_levels.display_label`）；
            #             ③ 正文措辞仍由各段自行决定（实测正文里「待核验/待核实」0 命中，口径已达成）。
            "by_level": {t["level"]: t["count"] for t in tiers},
            "by_level_display": {_display_label(t["level"]): t["count"] for t in tiers},
        },
    }
