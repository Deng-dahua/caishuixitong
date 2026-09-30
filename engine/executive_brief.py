# -*- coding: utf-8 -*-
"""决策层摘要版（3 分钟版）——**企业负责人看的 3~5 页摘要在本模块唯一生成**。

## 为什么要有（外部点评 P2-1 / P2-6）

- **P2-1**：报告 11.3 万字、模板重复约四成，**缺 3~5 页决策层摘要版**。
  企业负责人要的是"哪几件事最要紧、要花多少钱、下一步谁做什么"，
  而不是逐条红线论证。故在全文之前提供一版**结论先行、只讲重点**的摘要。
- **P2-6**：报告里同时出现**四套计数**（如"89 条规则 / 89 条红线 / 90 项台账 / 25 项具体问题"），
  彼此无映射，读者以为互相矛盾。故本模块给出**计数映射表**：
  每个数字"是什么口径、从哪来、彼此什么关系"，只在摘要里说一次。

## 设计约束（沿用项目铁律）

- **不改写任何结论**：摘要只做"选择 + 重排 + 转引"，数值一律从既定计算块转引，不重算；
- **不新增风险事项**：摘要列出的事项必须是正文里已有的事项（按 `seq` 引用）；
- **缺失如实**：取不到的数值写"未取得"，不用 0 顶替；
- **待核实口径**：全篇保持"涉嫌/待核实"，禁止定性（由 `text_guardrails` 兜底）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# 摘要里"最要紧"的事项数（决策层一次能处理的数量级；非阈值判定，只影响呈现）
TOP_N = 5

_LEVEL_RANK = {"极高风险": 5, "高风险": 4, "中风险": 3, "待核验": 2, "低风险": 1, "信息": 0}


def _fmt_amt(v: Any) -> str:
    from engine.numparse import to_number_checked
    val, ok = to_number_checked(v)
    if not ok:
        return "未取得"
    try:
        return "{:,.2f} 元".format(float(val))
    except (TypeError, ValueError):
        return "未取得"


def build_counts_map(report: Dict[str, Any]) -> List[Dict[str, str]]:
    """计数映射表（P2-6）：每个数字的口径 + 来源 + 彼此关系。**唯一权威**。

    库规模从代码里的目录**运行时读取**（不是硬编码），避免"20/74/156"这类陈旧数字。
    """
    rep = report if isinstance(report, dict) else {}
    er = rep.get("enterprise_readable_report") or {}
    rows: List[Dict[str, str]] = []

    # ① 库规模（工具本身有多大）
    n_redline = n_rule = n_domain = None
    try:
        from engine.tax_redlines import all_redlines
        n_redline = len(all_redlines())
    except Exception:
        pass
    try:
        # ★ 业务域数取**域分析目录**（DOMAIN_DATA_MAP，35 个）。
        #   注意：`tax_redlines.DOMAIN_ORDER` 是**红线分类**（12 类），
        #   不是业务域数 —— 混用会让"域"这个数字自相矛盾（点评 P2-6 的成因之一）。
        from engine.domain_analysis import DOMAIN_DATA_MAP as _DDM
        n_domain = len(_DDM)
    except Exception:
        pass
    try:
        from engine.verified_rule_engine import VERIFIED_RULE_CATALOG
        n_rule = len(VERIFIED_RULE_CATALOG)
    except Exception:
        pass
    rows.append({
        "口径": "已验证原子规则库",
        "数值": ("%d 条" % n_rule) if n_rule else "未取得",
        "来源": "系统规则目录（本轮全库规模，非本企业命中数）",
        "关系": "工具能力上限；本企业命中几条见下行「已验证规则命中」",
    })
    rows.append({
        "口径": "税务风险红线库",
        "数值": ("%d 条" % n_redline) if n_redline else "未取得",
        "来源": "红线目录（本轮全库规模）",
        "关系": "每条红线含多项构成要件；本企业命中数见「触碰红线疑点」",
    })
    rows.append({
        "口径": "业务域",
        "数值": ("%d 个" % n_domain) if n_domain else "未取得",
        "来源": "域分析目录 DOMAIN_DATA_MAP（本轮全库规模）",
        "关系": "注意区分：本行是「业务域」（35 个）；红线分类（税种/业务轴）是另一套口径，"
                "不可混用 —— 点评 P2-6 的混乱就来自把两套数字并排却不说口径",
    })

    # ② 本轮命中（本企业的情况）
    rd_sum = (er.get("redline_summary") or {})
    led = (er.get("resolution_ledger") or {})
    probs = er.get("confirmed_problems") or []
    scope = rep.get("output_scope") or {}
    rows.append({
        "口径": "触碰红线疑点",
        "数值": ("%d 项" % int(rd_sum.get("suspicion_total") or len(probs))),
        "来源": "红线检测（红线库 → 本企业命中）",
        "关系": "报告「具体问题」章逐项展开的就是这些疑点",
    })
    rows.append({
        "口径": "域分析结论",
        "数值": ("%d 项" % int(((scope.get("evidence_tiers") or {}).get(
            "域分析结论（基于上传资料计算）") or 0))),
        "来源": "业务域分析（域目录 → 本企业产出）",
        "关系": "已全部并入台账；可信度标注为「基于上传资料计算」",
    })
    rows.append({
        "口径": "风险事项台账",
        "数值": ("%d 项" % int(led.get("total") or len(led.get("rows") or []))),
        "来源": "台账（把「已验证规则命中 + 域分析结论」逐条归并去重后的可执行清单）",
        "关系": "同一事项可能同时来自规则与域，故台账数不等于两者相加；"
                "类型级聚合后见「聚合项数」列",
    })
    rows.append({
        "口径": "已验证规则命中",
        "数值": ("%d 项" % int(((scope.get("evidence_tiers") or {}).get(
            "已验原子规则（可信观察）") or 0))),
        "来源": "已验证原子规则引擎",
        "关系": "可信度最高的一类；其余为域分析结论",
    })
    ti = er.get("tax_impact_summary") or {}
    rows.append({
        "口径": "潜在税额敞口",
        "数值": _fmt_amt(ti.get("total")),
        "来源": "逐项按适用税率粗略测算后汇总",
        "关系": "各事项金额可能重叠，合计为最坏情形上界，不可逐项相加；"
                "已量化 %s/%s 项" % (ti.get("quantified"), ti.get("total_items")),
    })
    return rows


def build_executive_brief(report: Dict[str, Any]) -> Dict[str, Any]:
    """生成决策层摘要版（3~5 页）。返回结构与段落文本，供 Web / 离线共用。"""
    rep = report if isinstance(report, dict) else {}
    er = rep.get("enterprise_readable_report") or {}
    ident = er.get("identity") or {}
    summary = er.get("summary") or {}
    oc = er.get("overall_conclusion") or {}
    ti = er.get("tax_impact_summary") or {}
    led = er.get("resolution_ledger") or {}
    probs = [p for p in (er.get("confirmed_problems") or []) if isinstance(p, dict)]
    rd_sum = er.get("redline_summary") or {}

    # ── 一、一句话结论 ──
    headline = str(summary.get("headline") or "").strip()
    overall = str(rep.get("overall_level") or "").strip() or "未形成风险事项"
    one_line = (f"本轮对{ident.get('subject_name') or '被检查企业'}"
                f"{ident.get('period') or '（期间以资料记载为准）'}的经营资料实施检查，"
                f"总体情况：{overall}。")
    # `summary.headline` 可能是整段编制叙述 → 只取首句且限长，避免摘要首段变成"编制声明"
    if headline and not headline.startswith("编制声明"):
        # ★ 用唯一权威切句（`str.split("。")` 会在括号内切错，切出读不通的残句）
        try:
            from engine.sentencekit import split_sentences as _ss
            _sents = _ss(headline)
        except Exception:
            _sents = [headline]
        _first = str((_sents or [headline])[0]).strip().rstrip("。")
        if _first and _first not in one_line:
            one_line += (_first[:110] + "。")

    # ── 二、关键数字面板 ──
    metrics = [
        {"名称": "受检期间", "数值": str(ident.get("period") or "以资料记载为准")},
        {"名称": "已读取资料", "数值": "%s 份" % (summary.get("received_material_count") or rep.get("files_count") or 0)},
        {"名称": "触碰红线疑点", "数值": "%d 项" % int(rd_sum.get("suspicion_total") or len(probs))},
        {"名称": "台账风险事项", "数值": "%d 项" % int(led.get("total") or len(led.get("rows") or []))},
        {"名称": "潜在税额敞口（最坏情形上界）", "数值": _fmt_amt(ti.get("total"))},
        {"名称": "已量化事项", "数值": "%s/%s 项" % (ti.get("quantified"), ti.get("total_items"))},
    ]
    by_tax = [t for t in (ti.get("by_tax") or []) if isinstance(t, dict)]
    if by_tax:
        metrics.append({"名称": "敞口构成（按税种）",
                        "数值": "；".join("%s %s" % (t.get("tax"), _fmt_amt(t.get("amount")))
                                        for t in by_tax)})

    # ── 三、最要紧的 N 项（按 等级 → 敞口 排序；只从正文已有事项里挑，不新增） ──
    def _rank(p: Dict[str, Any]) -> Tuple[int, float]:
        lv = _LEVEL_RANK.get(str(p.get("risk_level") or p.get("level") or ""), 0)
        try:
            amt = float(((p.get("tax_impact") or {}).get("total")) or 0.0)
        except (TypeError, ValueError):
            amt = 0.0
        return (-lv, -amt)
    top = sorted(probs, key=_rank)[:TOP_N]
    top_items = []
    for p in top:
        _hi = p.get("tax_impact") or {}
        _need = str(p.get("missing_materials") or "")
        if isinstance(p.get("missing_materials"), list):
            _need = "、".join(str(x) for x in p["missing_materials"][:4])
        top_items.append({
            "seq": p.get("seq"),
            "标题": str(p.get("title") or ""),
            "等级": str(p.get("risk_level") or p.get("level") or ""),
            "敞口": _fmt_amt(_hi.get("total")) if _hi.get("available") else "未量化（需补资料后测算）",
            "企业要做的事": str((p.get("suggestion") or "")).strip() or
                            ("补充：%s" % _need if _need else "见正文该项「需企业提供的资料与说明」"),
        })

    # ── 四、下一步动作清单（时限 + 成本维度，复用既有口径，不新增承诺） ──
    actions = [
        "① 先处理上表所列事项：按各项「需企业提供的资料与说明」补资料或作书面说明；"
        "资料补齐后由系统重跑，核定该项是「可自证清白」还是「证据闭合」。",
        "② 若涉及以前年度已申报数据的更正，须在次年 5 月 31 日汇算清缴截止前完成；"
        "逾期更正申报的，滞纳金自期满次日起按日加收万分之五（年化约 18.25%）。",
        "③ 涉及自然人信息的事项（工资、个人账户收付等），请按《个人信息保护法》"
        "最小必要原则在本企业内部处理，不得随本报告外传。",
    ]

    # ── 五、边界声明 ──
    boundary = [
        "本文书由企业税务风险检查系统自动生成，是检查工作底稿与风险提示，"
        "不是税务机关出具的税务文书，不具备税务处理、行政处罚或强制执行效力。",
        "本摘要所列事项均为待核实事实，不构成违法定性；是否成立须由有权人员依法核实后判断。",
        "摘要中数值一律转引自正文各章，口径以「关键口径对照」为准；"
        "取不到的数值如实写「未取得」，不按 0 参与比较。",
    ]

    paragraphs: List[str] = []
    paragraphs.append("一、一句话结论：" + one_line)
    paragraphs.append("二、关键数字：" + "；".join(
        "%s＝%s" % (m["名称"], m["数值"]) for m in metrics) + "。")
    if top_items:
        paragraphs.append("三、最需要先处理的事项（按等级与敞口排序，共 %d 项，详见正文「具体问题」章）："
                          % len(top_items))
    for it in top_items:
        paragraphs.append("第%s项 %s（%s，潜在敞口 %s）。下一步：%s"
                          % (it["seq"], it["标题"], it["等级"], it["敞口"], it["企业要做的事"]))
    paragraphs.append("四、下一步动作：" + "".join(actions))
    paragraphs.append("五、边界声明：" + " ".join(boundary))

    return {
        "available": bool(one_line),
        "title": "决策层摘要（3 分钟版）",
        "one_line": one_line,
        "metrics": metrics,
        "counts_map": build_counts_map(rep),
        "top_items": top_items,
        "actions": actions,
        "boundary": boundary,
        "paragraphs": paragraphs,
        "note": ("本摘要只做「选重点 + 重排 + 转引」，不新增任何风险事项，"
                 "也未改变任何结论、金额与等级；完整论证见后文各章。"),
    }
