# -*- coding: utf-8 -*-
"""税务稽查专家研判内核——让系统像人类税务稽查专家一样开口思考。

人类税务稽查专家拿到一家企业的材料后，心智过程是有固定顺序的，这个顺序本身就是
"专业性"的来源。本模块把这段心智过程显式化、可执行化：

    第 1 步【先懂企业】画像——这家企业是谁、干什么、什么模式、多大体量。
        专家不会一上来就找风险，而是先给企业"定性"，否则任何风险判断都是空中楼阁。

    第 2 步【对标行业】基准——毛利率/净利率/税负率/人均产值 vs 行业基准，
        哪里偏离、偏离多少、可能意味着什么。这是"相对判断"，是规则引擎（只看绝对值）
        永远做不出来的那一层。

    第 3 步【抓重点】线索分级——把散落的发现按「风险性质 × 证据硬度 × 行业敏感性」
        重新排序。同一线索（如供应商地域分散）对制造业是强信号、对服务业可能是正常
        经营特征，专家会自动加权，规则不会。

    第 4 步【给路线】核查路线——先查什么、后查什么、为什么这个顺序。
        证据最硬、定性最直接的优先，资料缺失的殿后。

设计原则：
- 纯函数、可单测，输入 report_data（含 target_entity / engine_status / all_findings / stats）。
- 输出结构化 dict + 一段连贯文本（专家口吻），供报告渲染与 summary 引用。
- 绝不凭空编造数字：所有指标要么来自 financial_snapshot，要么来自行业基准库。
"""

import json
import os

# 行业基准库路径（相对本文件定位到 static/industry_data.json）
_IND_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "static", "industry_data.json")


def _load_industry_data():
    try:
        with open(_IND_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ── 业务模式 → 粗粒度行业（用于行业基准兜底）──
_BIZ_TO_COARSE = {
    "制造业": "制造业",
    "贸易业": "批发零售",
    "服务业": "居民服务",
}

# 服务业细分行业名 → 粗粒度基准（更贴切的兜底）
_SERVICE_FINE_TO_COARSE = {
    "餐饮": "住宿餐饮", "酒店": "住宿餐饮", "住宿": "住宿餐饮",
    "广告": "租赁商务", "传媒": "租赁商务", "咨询": "租赁商务", "设计": "租赁商务",
    "信息": "信息技术", "软件": "信息技术", "互联网": "信息技术", "网络": "信息技术",
    "文化": "文化体育", "影视": "文化体育", "娱乐": "文化体育",
}


def _match_benchmark(industry, biz_model, entity_name="", business_scope=""):
    """按企业画像匹配行业基准，返回 (基准名, 基准dict)。匹配不到返回 (None, None)。"""
    data = _load_industry_data()
    benchmarks = data.get("benchmarks", {}) or {}
    coarse = data.get("benchmarks_coarse", {}) or {}

    ind = str(industry or "").strip()
    # 1. 精确匹配细分行业
    if ind and ind in benchmarks:
        return ind, benchmarks[ind]
    # 2. 细分行业名互含匹配（"文化传媒" vs "广告传媒"）
    if ind:
        for k in benchmarks:
            if k == "_default":
                continue
            if k in ind or ind in k:
                return k, benchmarks[k]
    # 3. 从企业名称/经营范围推断细分行业
    scope_name = str(business_scope or "") + str(entity_name or "")
    if scope_name:
        for k in benchmarks:
            if k == "_default":
                continue
            if k in scope_name:
                return k, benchmarks[k]
    # 4. 服务业细分 → 粗粒度
    if biz_model == "服务业" and scope_name:
        for kw, coarse_key in _SERVICE_FINE_TO_COARSE.items():
            if kw in scope_name:
                return coarse_key, coarse.get(coarse_key)
    # 5. 业务模式 → 粗粒度
    bm = str(biz_model or "").strip()
    coarse_key = _BIZ_TO_COARSE.get(bm)
    if coarse_key and coarse.get(coarse_key):
        return coarse_key, coarse.get(coarse_key)
    # 6. 兜底
    if benchmarks.get("_default"):
        return "_default", benchmarks["_default"]
    return None, None


def _build_entity_profile(target_entity, fin_snap, stats, core_biz=None):
    """第 1 步：企业画像。core_biz: 主营业务识别结果（2026-09-05）。"""
    te = target_entity or {}
    name = te.get("name") or "被检查企业"
    industry = te.get("industry") or ""
    biz_model = te.get("biz_model") or "未确定经营模式"
    business_scope = te.get("business_scope") or ""
    registered_capital = te.get("registered_capital") or ""
    established = str(te.get("established_date") or "")[:10]

    # 行业未标注时，从名称/经营范围推断一个行业词，避免画像留白
    if not industry:
        _INDUSTRY_HINTS = ("餐饮", "酒店", "广告", "传媒", "咨询", "设计", "软件", "互联网",
                           "信息技术", "纺织", "服装", "食品", "机械", "电子", "化工", "建材",
                           "贸易", "商贸", "物流", "运输", "教育", "培训", "医疗", "建筑", "装饰")
        _scope = str(name or "") + str(business_scope or "")
        for _kw in _INDUSTRY_HINTS:
            if _kw in _scope:
                industry = _kw + "行业"
                break
        if not industry:
            industry = "未标注行业"

    fs = fin_snap or {}
    sales = fs.get("total_sales") or 0
    purchases = fs.get("total_purchases") or 0
    salary = fs.get("total_salary") or 0
    sale_count = fs.get("sale_count") or 0
    pur_count = fs.get("pur_count") or 0

    # 规模判断（销售额口径）
    if sales >= 100_000_000:
        scale = "大型"
    elif sales >= 10_000_000:
        scale = "中型"
    elif sales >= 1_000_000:
        scale = "小型"
    else:
        scale = "微型"

    # 一句话定性
    if biz_model == "服务业":
        nature = "以提供服务为主业的轻资产企业，不涉及货物生产"
    elif biz_model == "制造业":
        nature = "以生产制造为主业的实体企业，存在「采购原材料→加工→销售成品」的物耗链条"
    elif biz_model == "贸易业":
        nature = "以购销贸易为主业的流通企业，存在「采购→销售」的实物货物流转"
    else:
        nature = "经营模式尚未明确，须结合经营范围与进销结构进一步确认"

    profile = {
        "name": name, "industry": industry, "biz_model": biz_model,
        "scale": scale, "registered_capital": str(registered_capital),
        "established": established,
        "sales": round(sales, 2), "purchases": round(purchases, 2),
        "salary": round(salary, 2),
        "sale_count": sale_count, "pur_count": pur_count,
        "nature": nature,
    }
    text = (
        f"{name}是一家{industry}企业（经营模式：{biz_model}），{nature}。"
        f"按本轮资料，开出去的发票收入{sales:,.0f}元、进货发票{purchases:,.0f}元，"
        f"开票{sale_count}张、收进进货发票{pur_count}张，属{scale}企业。"
    )
    if registered_capital:
        text += f"注册资本{registered_capital}。"
    # 主营业务识别（2026-09-05）：像税务稽查员一样先圈定"这家企业靠什么赚钱"
    if core_biz and core_biz.get("core_revenue_amount") is not None:
        _cr = core_biz.get("core_revenue_amount") or 0
        _cc = core_biz.get("core_cost_amount") or 0
        _ratio = (core_biz.get("core_revenue_ratio") or 0) * 100
        _gm = ((_cr - _cc) / _cr * 100) if _cr > 0 else None
        text += (
            f"经识别，该企业的主营业务收入约{_cr:,.0f}元（占开票收入{_ratio:.0f}%）、"
            f"对应主营业务成本约{_cc:,.0f}元"
        )
        if _gm is not None:
            text += f"，主营业务毛利率约{_gm:.1f}%"
        text += "。后续行业对标与重点线索均以主营业务口径为主。"
    return profile, text


def _build_industry_benchmark(industry, biz_model, fin_snap, entity_name="", business_scope="", core_biz=None):
    """第 2 步：行业对标——毛利率/人均产值 vs 行业基准，给出专家式相对判断。
    优先用主营业务毛利率对标（2026-09-05：稽查员只对标主营业务的赚钱能力）。"""
    bench_name, bench = _match_benchmark(industry, biz_model, entity_name, business_scope)
    if not bench:
        return None, ""

    fs = fin_snap or {}
    sales = fs.get("total_sales") or 0
    purchases = fs.get("total_purchases") or 0

    # 实际毛利率：优先主营业务口径，缺省用财务快照（gross_margin_pct 是百分比）
    gm_pct = None
    gm_scope_note = ""
    if core_biz and core_biz.get("core_revenue_amount"):
        _cr = core_biz.get("core_revenue_amount") or 0
        _cc = core_biz.get("core_cost_amount") or 0
        if _cr > 0:
            gm_pct = (_cr - _cc) / _cr * 100
            gm_scope_note = "（主营业务口径）"
    if gm_pct is None:
        gm_pct = fs.get("gross_margin_pct")
        if gm_pct is None and sales > 0:
            gm_pct = (sales - purchases) / sales * 100

    observations = []

    # 毛利率对标（优先主营业务口径，2026-09-05）
    gm_range = bench.get("毛利率")  # [下限, 上限, 中位]（小数）
    if gm_range and gm_pct is not None:
        lo, hi, mid = gm_range[0] * 100, gm_range[1] * 100, gm_range[2] * 100
        gm = float(gm_pct)
        _m = f"毛利率{gm_scope_note}" if gm_scope_note else "毛利率"
        if gm < 0:
            # 销项 < 进项成本 → 购销倒挂，不是普通"毛利率偏低"
            observations.append({
                "metric": "进销结构",
                "actual": round(gm, 1),
                "benchmark": f"{lo:.0f}%~{hi:.0f}%（中位{mid:.0f}%）",
                "direction": "购销倒挂",
                "why": ("开出去的发票金额比进货成本还少，收入盖不住成本，属于购销倒挂。正常做生意不会长期这样，"
                        "需要核实三件事：①开出去的发票是不是全都上传了（少报收入会人为放大倒挂）；"
                        "②有没有隐瞒不报的收入；③进货发票里是不是虚列了成本、虚抵了税。"
                        "先把资料缺漏排除掉，再判断是不是真的倒挂。"),
            })
        elif gm < lo:
            observations.append({
                "metric": _m,
                "actual": round(gm, 1),
                "benchmark": f"{lo:.0f}%~{hi:.0f}%（中位{mid:.0f}%）",
                "direction": "明显偏低",
                "why": ("毛利率明显低于同行业的下限，通常指向三种可能：①销售收入没报足（有隐瞒不报的收入）；"
                        "②成本或进货发票虚高（虚列成本、多抵税）；③进货里混进了大量跟主业无关的服务或费用，"
                        "把真实毛利率拉低了。需要把无关进项剥出来，重新算一遍真实毛利率，再逐项排除。"),
            })
        elif gm > hi:
            observations.append({
                "metric": _m,
                "actual": round(gm, 1),
                "benchmark": f"{lo:.0f}%~{hi:.0f}%（中位{mid:.0f}%）",
                "direction": "明显偏高",
                "why": ("毛利率明显高于同行业的上限，可能指向：①成本或进货发票被压低了（少记成本、进货发票缺失）；"
                        "②高附加值业务集中（需要核实是不是真的）；③记账口径差异。需要核实成本是不是记全了。"),
            })
        else:
            observations.append({
                "metric": _m,
                "actual": round(gm, 1),
                "benchmark": f"{lo:.0f}%~{hi:.0f}%（中位{mid:.0f}%）",
                "direction": "处于合理区间",
                "why": "毛利率落在行业正常区间里，收入和成本基本配比正常。",
            })

    # 人均产值对标（销售额 / 用工人数）
    # 用工人数从 stats 工资/社保记录推断，取工资记录条数去重不易，此处用 bench 的人均营收区间做粗判
    # （若财务快照无 headcount，跳过，避免编造）
    headcount = fs.get("headcount")
    per_capita_bench = bench.get("人均营收(万)")
    if headcount and headcount > 0 and per_capita_bench and sales > 0:
        per_capita = sales / headcount / 10000  # 万元
        lo, hi, mid = per_capita_bench
        if per_capita < lo:
            observations.append({
                "metric": "人均产值", "actual": round(per_capita, 1),
                "benchmark": f"{lo}~{hi}万（中位{mid}万）", "direction": "偏低",
                "why": "平均每人创造的收入偏低，说明用工人数和收入规模对不上，需要核实用工是不是真的、收入是不是记全了。",
            })

    result = {"benchmark_name": bench_name, "observations": observations}
    if not observations:
        return result, ""
    lines = [f"对照『{bench_name}』行业基准："]
    for o in observations:
        lines.append(f"· {o['metric']}{o['actual']}%，行业{o['benchmark']}，{o['direction']}。{o['why']}")
    return result, "\n".join(lines)


def _clue_severity(finding, biz_model):
    """判断一条线索的专家权重（结合行业敏感性）。

    返回 (优先级档位: 'A'|'B'|'C', 权重分:int)。
    A 档：证据硬、定性直接，资金流/发票/账面勾稽，须最优先；
    B 档：需外部证据的实质线索；
    C 档：数据质量/资料缺失类，殿后。
    """
    t = str(finding.get("type") or "") + str(finding.get("category") or "") + str(finding.get("domain") or "")
    level = str(finding.get("level") or "")
    score = finding.get("score") or 0
    try:
        score = int(score)
    except Exception:
        score = 0

    # 资金流 / 公私混同 / 现金 / 平台归集 / 回流 —— 证据最硬
    hard_money = ("资金", "公私", "个人账户", "现金", "聚合支付", "回流", "六员", "收款", "往来")
    # 发票穿透 / 虚开 / 进销背离 —— 定性直接
    hard_invoice = ("虚开", "发票", "进项", "销项", "有进无销", "有销无进", "进销", "品名", "开票")
    # 数据质量 / 资料缺失 —— 殿后
    data_quality = ("借贷差额", "发票号", "品名为空", "重复", "完整性与借贷", "余额未", "未标注")

    tier = "B"
    weight = 5
    if any(k in t for k in data_quality):
        tier, weight = "C", 2
    elif any(k in t for k in hard_money):
        tier, weight = "A", 9
    elif any(k in t for k in hard_invoice):
        tier, weight = "A", 8
    elif "关联" in t or "转让定价" in t:
        tier, weight = "B", 5

    # 行业敏感性：制造业专属线索对服务业降权；服务业线索对制造业降权
    mfg_only = ("运输费", "货值", "能源", "BOM", "产能", "委外", "进销存", "原材料", "存货", "加价倍数")
    if biz_model == "服务业" and any(k in t for k in mfg_only):
        weight = max(1, weight - 4)
        tier = "C" if tier == "B" else tier
    if biz_model == "制造业" and "平台" in t:
        weight = max(1, weight - 2)

    # 风险等级加权
    if level == "高风险":
        weight += 3
    elif level in ("中风险",):
        weight += 2
    elif level in ("低风险", "待核验", "信息"):
        weight += 0
    return tier, weight


def _build_key_clues(all_findings, biz_model):
    """第 3 步：重点线索分级排序。"""
    ranked = []
    for f in all_findings:
        if not isinstance(f, dict):
            continue
        tier, weight = _clue_severity(f, biz_model)
        ftype = (f.get("type") or "未命名线索").replace("待核事实：", "").replace("待核事实:", "")
        opposing = list(f.get("reasonable_explanations") or f.get("alternative_explanations") or [])[:4]
        # 行业敏感性：供应商地域分散对服务业是"服务采购天然分散"，而非制造业的"原料产地集中"
        if "供应商地域" in ftype or "购销集中度" in ftype:
            if biz_model == "服务业":
                opposing = ["广告投放/媒体采购天然分散", "服务商按项目跨省采购", "线上服务无地域约束"]
            elif biz_model == "贸易业":
                opposing = ["代理多品牌跨区采购", "电商一件代发分散采购"]
        ranked.append({
            "type": ftype,
            "level": f.get("level") or "",
            "score": f.get("score") or 0,
            "detail": (f.get("detail") or "")[:200],
            "opposing": opposing,
            "steps": (f.get("investigation_steps") or [])[:4],
            "tier": tier,
            "weight": weight,
        })
    ranked.sort(key=lambda x: (-x["weight"], x["tier"]))
    return ranked


def _build_investigation_route(key_clues, biz_model):
    """第 4 步：核查路线。"""
    a = [c for c in key_clues if c["tier"] == "A"]
    b = [c for c in key_clues if c["tier"] == "B"]
    c = [c for c in key_clues if c["tier"] == "C"]
    route = []
    if a:
        route.append(f"第一步·资金和发票硬线索（{len(a)}项）：先查证据最硬、最容易定性的——"
                     + "、".join(c["type"] for c in a[:3]) + "等，这类线索能直接锁定资金回流、虚开发票或账实不符。")
    if b:
        route.append(f"第二步·实质交易线索（{len(b)}项）：核实供应商/客户资质、关联关系和用工身份这些"
                     "需要外部证据的事项——" + "、".join(c["type"] for c in b[:3]) + "等。")
    if c:
        route.append(f"第三步·数据质量和资料缺口（{len(c)}项）：补齐品名、发票号、借贷平衡等资料质量问题后重新跑一遍——"
                     + "、".join(c["type"] for c in c[:3]) + "等。")
    if not route:
        route.append("本轮资料有限，还没有形成可以排序的重点线索，补充核心资料后再研判。")
    return route


def _build_core_biz(report_data):
    """主营业务识别（2026-09-05）：销项按主营成本品名重合 + 80/20 主业法则识别主营收入，
    进项用报告里已分类的主营成本（invoice_tables.core_cost / engine_status.biz_cost_classification）。"""
    it = report_data.get("invoice_tables") or {}
    sales = it.get("sales") or []
    core_cost_rows = it.get("core_cost") or []
    bcc = (report_data.get("engine_status") or {}).get("biz_cost_classification") or {}
    core_cost_amount = bcc.get("core_cost_amount")
    if core_cost_amount is None:
        core_cost_amount = sum(float(r.get("amount") or r.get("total") or 0) for r in core_cost_rows)
    core_goods = set()
    for r in core_cost_rows:
        g = str(r.get("goods") or "").strip()
        if g:
            core_goods.add(g)
    core_goods |= set(bcc.get("core_goods") or [])
    try:
        from engine.main_biz_cost import identify_core_revenue
        rev = identify_core_revenue(sales, core_goods)
    except Exception:
        rev = {}
    return {
        "core_revenue_amount": rev.get("core_revenue_amount"),
        "core_revenue_ratio": rev.get("core_revenue_ratio"),
        "core_cost_amount": round(core_cost_amount, 2) if core_cost_amount is not None else None,
        "core_goods_sale": rev.get("core_goods_sale") or set(),
        "core_cost_count": bcc.get("core_cost_count") or len(core_cost_rows),
    }


def build_inspector_reasoning(report_data):
    """主入口：生成税务稽查专家研判。"""
    if not isinstance(report_data, dict):
        return {}
    te = report_data.get("target_entity") or {}
    es = report_data.get("engine_status") or {}
    fin_snap = es.get("financial_snapshot") or {}
    stats = report_data.get("stats") or {}
    all_findings = report_data.get("all_findings") or []

    biz_model = te.get("biz_model") or ""
    industry = te.get("industry") or ""
    name = te.get("name") or ""
    scope = te.get("business_scope") or ""

    core_biz = _build_core_biz(report_data)
    profile, profile_text = _build_entity_profile(te, fin_snap, stats, core_biz)
    bench_result, bench_text = _build_industry_benchmark(
        industry, biz_model, fin_snap, name, scope, core_biz)
    key_clues = _build_key_clues(all_findings, biz_model)
    route = _build_investigation_route(key_clues, biz_model)

    # 组装连贯文本（专家口吻·大白话）
    parts = ["一、这是一家什么样的企业", profile_text]
    if bench_text:
        parts.append("二、跟同行业比，哪里不对劲")
        parts.append(bench_text)
    parts.append("三、哪些线索最要紧")
    if key_clues:
        for i, c in enumerate(key_clues[:8], 1):
            seg = f"{i}. {c['type']}（{c['level'] or '待核实'}）"
            if c["opposing"]:
                seg += f"——可能的正常解释：{'、'.join(c['opposing'][:3])}"
            parts.append(seg)
    else:
        parts.append("本轮没有形成重点线索。")
    parts.append("四、按什么顺序查")
    parts.extend(route)

    # 统一过一遍大白话翻译层（幂等：已白话的文本不受影响）
    from engine.plain_language import to_plain
    narrative = to_plain("\n\n".join(parts))

    return {
        "entity_profile": profile,
        "industry_benchmark": bench_result,
        "key_clues": key_clues,
        "investigation_route": route,
        "core_business": core_biz,
        "narrative": narrative,
    }
