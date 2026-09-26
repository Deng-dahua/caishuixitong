# -*- coding: utf-8 -*-
"""税务稽查专家工作底稿版 —— 检查情况总述（2026-09-26）

回答四件事（用户要求）：
  ① 本次检查的基本情况（查了什么、怎么查）；
  ② 风险类型分布；
  ③ 风险程度评定（含依据）；
  ④ 对企业怎么看（总体判断）+ 监管态度（分级处理建议）。

写作红线（与"总体结论"编辑标准同源，工作底稿版同样适用）：
  · 发现 ≠ 确认：线索只能说"存在指向…的差异/异常"，不得说"存在偷税/虚开事实"；
  · 主观故意不作认定：是否属故意偷逃税，须经补证与核实，本轮不下结论；
  · 等级与状态分离：高/中/低是等级，"待核验"是证据状态，不参与排序；
  · 行业认定待核实：销项品名只作"初步测算口径"，须并列登记口径；
  · 边界声明：本底稿为企业内部风险检查形成，不具税务机关文书效力。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine.overall_conclusion import (
    _cost_reconciliation, _group_by_theme, _short_title,
)


def _lvl_counts(tiers: List[Dict[str, Any]]) -> Dict[str, int]:
    return {t["level"]: int(t.get("count") or 0) for t in (tiers or [])}


def build_inspection_overview(report_data: Any,
                              problems: Optional[List[dict]] = None,
                              further: Optional[List[dict]] = None,
                              overall_conclusion: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """生成「检查情况总述」。返回 {"paragraphs":[...], "grading":..., "posture":...}。"""
    rd = report_data if isinstance(report_data, dict) else {}
    err = rd.get("enterprise_readable_report") or {}
    if problems is None:
        problems = err.get("confirmed_problems") or []
    if further is None:
        further = err.get("further_checks") or []
    problems = [p for p in (problems or []) if isinstance(p, dict)]
    further = [f for f in (further or []) if isinstance(f, dict)]

    oc = overall_conclusion or {}
    tiers = oc.get("tiers") or []
    themes = oc.get("risk_themes") or _group_by_theme(problems)
    lv = _lvl_counts(tiers)
    n_high, n_mid, n_low = lv.get("高风险", 0), lv.get("中风险", 0), lv.get("低风险", 0)
    n_pend = lv.get("待核验", 0)

    file_results = rd.get("file_results") or []
    files_count = rd.get("files_count") or len(file_results)
    types = {fr.get("type") for fr in file_results if isinstance(fr, dict)}
    cats = len([t for t in types if t])

    te = rd.get("target_entity") or {}
    ind_name = str(te.get("industry") or "")
    ind_src = str(te.get("_industry_source") or "")
    ind_reg = str(te.get("industry_registered") or "")
    fs = ((rd.get("engine_status") or {}).get("financial_snapshot")) or {}
    cost_recon = oc.get("cost_reconciliation") or _cost_reconciliation(rd)

    P: List[str] = []

    # ── 一、检查基本情况 ──
    P.append(
        "一、检查基本情况：本轮对被检查企业提交并成功读取的 %d 类资料（%d 份）实施检查，"
        "按“资料合规性核验 → 多源交叉比对 → 资金流向穿透 → 行业基准对标 → 规则与红线扫描 → "
        "证据链闭合度评估”的程序重新读取、重新计算，形成本轮复算结论；"
        "本轮结论独立于此前任何一轮报告。"
        % (cats, files_count)
    )

    # ── 二、企业与经营特征 ──
    _scale = []
    if fs.get("total_sales"):
        _scale.append("销项开票（不含税）%.2f 元" % float(fs.get("total_sales") or 0))
    if fs.get("total_purchases"):
        _scale.append("进项采购 %.2f 元" % float(fs.get("total_purchases") or 0))
    if fs.get("gross_margin_pct") is not None:
        _scale.append("毛利率 %.2f%%" % float(fs.get("gross_margin_pct") or 0))
    if fs.get("sale_count"):
        _scale.append("销项 %d 张" % int(fs.get("sale_count") or 0))
    if fs.get("pur_count"):
        _scale.append("进项 %d 张" % int(fs.get("pur_count") or 0))
    _ind_seg = ""
    if ind_name:
        _ind_seg = ("行业口径：本轮初步按销项发票品名指向的「%s」口径测算（来源：%s）"
                    % (ind_name, ind_src or "未标注"))
        if ind_reg and ind_reg != ind_name:
            _ind_seg += "，同时列示登记口径「%s」" % ind_reg
        _ind_seg += "；行业认定应以登记经营范围、实际主营业务收入构成、合同和发票品名为准，待核实。"
    P.append(
        "二、企业与经营特征：%s经营规模：%s。%s"
        % (_ind_seg, ("；".join(_scale) if _scale else "本轮未取得完整财务快照"),
           "其中收入口径取自销项发票不含税金额，成本与费用须区分主营成本与期间费用后分别判断。")
    )

    # ── 三、风险类型分布 ──
    if themes:
        _parts = []
        for g in themes:
            _rep = "、".join((g.get("items") or [])[:3])
            _suffix = "等" if len(g.get("items") or []) > 3 else ""
            _parts.append("%s %d 项（%s%s）" % (g.get("theme"), g.get("count"), _rep, _suffix))
        P.append("三、发现问题的类型分布：本轮共识别并列示 %d 项待核实风险事项，按风险性质归纳为——%s。"
                 % (len(problems), "；".join(_parts)))
    else:
        P.append("三、发现问题的类型分布：本轮识别并列示 %d 项待核实风险事项，暂无可归纳的风险主题。"
                 % len(problems))

    # ── 四、风险程度评定 ──
    _grade = "低"
    if n_high >= 3:
        _grade = "高"
    elif n_high >= 1 or n_mid >= 5:
        _grade = "较高"
    elif n_mid >= 1 or len(problems) > 0:
        _grade = "中等"
    _grade_txt = (
        "四、风险程度评定：本轮风险程度评定为「%s」。其中风险等级为高风险 %d 项、中风险 %d 项、"
        "低风险 %d 项；另有 %d 项因证据不足暂列为待核验事项（属证据状态，不参与风险等级排序）。"
        "评定依据为：潜在税额影响、涉及金额、证据缺口、是否涉及虚开或偷税、补证紧迫性五项综合排序，仅供参考。"
        % (_grade, n_high, n_mid, n_low, n_pend)
    )
    if cost_recon.get("status") == "差异超阈值（待核）":
        _grade_txt += ("另，主营业务成本两口径差异已超阈值（发票类目口径与账面口径相差 %.2f 元），"
                       "成本真实性本身即构成本轮重点核实事项。" % float(cost_recon.get("diff") or 0))
    P.append(_grade_txt)

    # ── 五、对企业纳税遵从情况的看法（分层表述，关键：不得定性）──
    _view = []
    if further:
        _view.append("资料与核算管理方面：本轮有 %d 项检查因资料缺失、不完整或影响范围未查清而未能实施，"
                     "反映企业资料归集与凭证管理尚不完备" % len(further))
    _view.append("数据异常方面：本轮发现 %d 项指向具体涉嫌方向（如隐匿收入、虚开发票、虚列成本、"
                 "资金空转、转移利润、少代扣代缴税款等）的差异或异常线索，均需补充外部证据后方能定性"
                 % len(problems))
    _view.append("主观故意方面：本轮不作认定——现有资料不足以判断上述差异系管理疏漏、核算差错，"
                 "还是存在主观故意；须经补证与核实后另行判断")
    P.append("五、对企业纳税遵从情况的总体看法：" + "；".join(_view) + "。")

    # ── 六、监管态度与后续处理建议（分级）──
    _pos = []
    if n_low:
        _pos.append("提示提醒：对 %d 项低风险事项，建议以提示提醒方式要求企业自行规范与整改" % n_low)
    if n_mid:
        _pos.append("补证核实：对 %d 项中风险事项，建议限期要求企业补充合同、物流、资金、入库等外部证据，"
                    "逐项排除疑点" % n_mid)
    if n_high:
        _pos.append("重点关注：对 %d 项高风险事项（证据相对集中、涉及隐匿收入或虚开发票方向），"
                    "建议列为后续优先检查事项" % n_high)
    if n_pend:
        _pos.append("待核验事项：对 %d 项证据不足事项，建议先行补证，不宜在证据补齐前作出处理结论" % n_pend)
    if further:
        _pos.append("限期补正资料：对 %d 项因资料缺失未能实施的检查，建议限期要求企业补齐后再行检查" % len(further))
    _pos.append("复查要求：企业完成真实更正与资料补充后，应发起新一轮全量复查，核对原问题是否处理完成、"
                "以及补充资料是否带出新的关联问题")
    P.append("六、监管态度与后续处理建议（分级分类）：" + "；".join(_pos) + "。")
    P.append("需要说明：本部分为工作建议，不构成税务处理、行政处罚或移送决定；"
             "是否达到移送标准，应在证据补齐并依法核实后另行判断。")

    # ── 七、边界声明 ──
    P.append("七、边界声明：本工作底稿由企业使用的财税风险防控系统依据已提交资料生成，"
             "用于模拟税务风险检查程序并开展合规整改，不具有税务机关行政执法文书效力；"
             "所列事项均为待核实事项，不代表已经认定违法；税务机关实际检查结论应以依法送达的正式文书为准。")

    return {
        "paragraphs": P,
        "grading": {
            "overall": _grade,
            "high": n_high, "mid": n_mid, "low": n_low, "pending_verify": n_pend,
            "total": len(problems), "further": len(further),
            "basis": "潜在税额影响 / 涉及金额 / 证据缺口 / 是否涉及虚开或偷税 / 补证紧迫性",
        },
        "posture": _pos,
        "themes": themes,
    }
