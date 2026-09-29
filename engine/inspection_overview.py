# -*- coding: utf-8 -*-
"""税务稽查专家工作底稿版 —— 检查情况总述（2026-09-26）

回答四件事（用户要求）：
  ① 本次检查的基本情况（查了什么、怎么查）；
  ② 风险类型分布；
  ③ 风险程度评定（含依据）；
  ④ 对企业怎么看（总体判断）+ 监管态度（分级处理建议）。
  并在风险程度评定之后新增「五、企业整体风险综合评价」定调段：把整体等级、主要风险领域、
  纳税遵从评价三句合成一段结论性表述，作为整个检查情况总述的"定调句"。

写作红线（与"总体结论"编辑标准同源，工作底稿版同样适用）：
  · 发现 ≠ 确认：线索只能说"存在指向…的差异/异常"，不得说"存在偷税/虚开事实"；
  · 主观故意不作认定：是否属故意偷逃税，须经补证与核实，本轮不下结论；
  · 等级与状态分离：高/中/低是等级，"待核验"是证据状态，不参与排序；
  · 行业认定待核实：销项品名只作"初步测算口径"，须并列登记口径；
  · 边界声明归属：文书性质说明统一在第六章「报告性质和使用说明」给出，本章不再重复（2026-09-27）。
  · 本章只写**检查分析的事实与由此提出的观点**：不写"待核实"式免责语，不写"见某章/本章不展开"式引导。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine.overall_conclusion import _group_by_theme


def _lvl_counts(tiers: List[Dict[str, Any]]) -> Dict[str, int]:
    return {t["level"]: int(t.get("count") or 0) for t in (tiers or [])}


def build_inspection_overview(report_data: Any,
                              problems: Optional[List[dict]] = None,
                              further: Optional[List[dict]] = None,
                              overall_conclusion: Optional[Dict[str, Any]] = None,
                              cost_recon_detail: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
        # ★ 2026-09-27 用户口径：只给事实与观点，不写"待核实"、不写引导说明。
        _ind_seg = ("行业口径：本轮按销项发票品名指向的「%s」口径测算（来源：%s）"
                    % (ind_name, ind_src or "未标注"))
        if ind_reg and ind_reg != ind_name:
            _ind_seg += "；登记经营范围为「%s」，与销项发票品名口径不一致。" % ind_reg
    P.append(
        "二、企业与经营特征：%s经营规模：%s。%s"
        % (_ind_seg, ("；".join(_scale) if _scale else "本轮未取得完整财务快照"),
           "其中收入口径取自销项发票不含税金额，成本与费用须区分主营成本与期间费用后分别判断。")
    )

    # ── 三、风险类型分布（执行摘要：只给计数，主题明细见总体结论，避免与下文重复）──
    P.append("三、发现问题的类型分布：本轮共识别并列示 %d 项涉嫌风险事项，"
             "按风险性质归纳的主题分布（各主题项数及代表事项）详见下文「本轮检查总体结论」。"
             % len(problems))

    # ── 四、风险程度评定（执行摘要：只给整体等级与依据，各等级项数与待核验清单见总体结论，避免与下文重复）──
    _grade = "低"
    if n_high >= 3:
        _grade = "高"
    elif n_high >= 1 or n_mid >= 5:
        _grade = "较高"
    elif n_mid >= 1 or len(problems) > 0:
        _grade = "中等"
    P.append(
        "四、风险程度评定：本轮整体风险程度评定为「%s」。评定依据为：潜在税额影响、涉及金额、证据缺口、"
        "是否涉及虚开或偷税、补证紧迫性五项综合排序，仅供参考；各风险等级（高/中/低）项数、"
        "待核验事项清单，详见下文「本轮检查总体结论」；主营业务成本两口径勾稽见第三章台账后的专项明细。"
        % _grade
    )

    # ── 五、企业整体风险综合评价（定调句：等级 + 主要风险领域 + 遵从评价）──
    _top = sorted(themes, key=lambda g: -int(g.get("count") or 0))[:2]
    _total_p = len(problems)
    _sum_top = sum(int(g.get("count") or 0) for g in _top)
    _share = (_sum_top / _total_p * 100) if _total_p else 0.0
    if len(_top) >= 2:
        _top_clause = "风险高度集中于「%s」与「%s」两个领域，二者合计 %d 项、占全部 %d 项涉嫌风险事项的 %.0f%%" % (
            _top[0].get("theme"), _top[1].get("theme"), _sum_top, _total_p, _share)
    elif _top:
        g0 = _top[0]
        _top_clause = "主要风险领域为%s（%d 项，占全部 %d 项涉嫌风险事项的 %.0f%%）" % (
            g0.get("theme"), g0.get("count"), _total_p,
            (g0.get("count") / _total_p * 100 if _total_p else 0.0))
    else:
        _top_clause = "本轮暂无可归纳的主要风险领域"
    _synth = (
        "五、企业整体风险综合评价：综合本轮风险程度评定（整体「%s」）与问题类型分布，"
        "该企业整体税务风险等级为「%s」；%s。"
        "结合资料与核算管理尚不完备、多项异常线索指向具体涉嫌方向的实际情况，"
        "本轮对该企业纳税遵从的总体评价为：在已提交资料范围内呈现较高风险敞口，"
        "但主观故意性质尚不能认定，须以补证与核实为前提，再行判断其纳税义务履行的真实状况。"
        % (_grade, _grade, _top_clause)
    )
    P.append(_synth)

    # ── 六、对企业纳税遵从情况的看法（分层表述，关键：不得定性）──
    _view = []
    if further:
        _view.append("资料与核算管理方面：本轮有 %d 项检查因资料缺失、不完整或影响范围未查清而未能实施，"
                     "反映企业资料归集与凭证管理尚不完备" % len(further))
    _view.append("数据异常方面：本轮发现 %d 项指向具体涉嫌方向（如隐匿收入、虚开发票、虚列成本、"
                 "资金空转、转移利润、少代扣代缴税款等）的差异或异常线索，均需补充外部证据后方能定性"
                 % len(problems))
    _view.append("主观故意方面：本轮不作认定——现有资料不足以判断上述差异系管理疏漏、核算差错，"
                 "还是存在主观故意；须经补证与核实后另行判断")
    P.append("六、对企业纳税遵从情况的总体看法：" + "；".join(_view) + "。")

    # ── 七、监管态度与后续处理建议（分级）──
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
    P.append("七、监管态度与后续处理建议（分级分类）：" + "；".join(_pos) + "。")
    P.append("需要说明：本部分为工作建议，不构成税务处理、行政处罚或移送决定；"
             "是否达到移送标准，应在证据补齐并依法核实后另行判断。")

    # ── 八、关键口径对照（2026-09-29 点评整改 P0-7）──
    # 目的：全文同一指标可能出现多个口径（如"收入"有申报/开票/资金流三口径），本节把
    # 各口径**编号列示**（定义+数值+来源），供全文数字回指；取不到的口径如实写"未取得"，
    # 绝不用默认值顶替（缺失≠0）。数值只从既有计算块**转引**，不重算（防口径分叉）。
    comp = rd.get("comprehensive") or {}
    _bf = ((comp.get("bank_flow") or {}).get("metrics") or {})
    _tt = ((comp.get("two_tax_income") or {}).get("metrics") or {})
    _ra = ((comp.get("revenue_authenticity") or {}).get("metrics") or {})
    _crd = cost_recon_detail if isinstance(cost_recon_detail, dict) else {}

    def _fmt_amt(v) -> str:
        if v is None:
            return "未取得（缺失不按 0 参与比对）"
        from engine.numparse import to_number_checked as _tc
        val, ok = _tc(v)
        if not ok:
            return "未取得（缺失不按 0 参与比对）"
        return "%.2f 元" % float(val)

    _rows = [
        ("增值税申报销售额（申报口径）", _fmt_amt(_tt.get("vat_sales")), "增值税申报表；两税差异章"),
        ("企业所得税申报营业收入（申报口径）", _fmt_amt(_tt.get("cit_income")), "企业所得税申报表；两税差异章"),
        ("销项开票不含税合计（发票口径）",
         _fmt_amt(_bf.get("invoice_total") or _ra.get("invoiced_total")), "销项发票；资金流比对章"),
        ("银行经营性入账合计（资金流口径）", _fmt_amt(_bf.get("flow_receipt") or _ra.get("bank_in_total")),
         "银行流水；资金流比对章"),
        ("其中：对公收款", _fmt_amt(_bf.get("corporate_receipt")), "银行流水；资金流比对章"),
        ("其中：私户/个人收款", _fmt_amt(_bf.get("personal_receipt")), "银行流水；资金流比对章"),
        ("收款−申报差额（未开票敞口·毛口径）", _fmt_amt(_bf.get("uninvoiced_gap")),
         "银行收款−申报收入；资金流比对章"),
        ("剔除明显非销售流入后敞口", _fmt_amt(_bf.get("uninvoiced_gap_after_nonsales")),
         "毛口径−非销售收款；资金流比对章"),
        ("主营业务成本·发票类目口径", _fmt_amt(_crd.get("invoice_total")), "进项发票按行业类目归集；第三章专项明细"),
        ("主营业务成本·账面口径（序时账 6401 借方）", _fmt_amt(_crd.get("book_total")), "序时账；第三章专项明细"),
        ("两口径差异", _fmt_amt(_crd.get("diff")), "发票口径−账面口径；第三章专项明细"),
    ]
    _cal = ["八、关键口径对照：本报告同一指标可能存在多个口径（申报/开票/资金流/账面），"
            "各章数字以本对照为准回指；口径间差异本身即检查线索，详见对应章节。"]
    for _i, (_nm, _val, _src) in enumerate(_rows, 1):
        _cal.append("口径%d %s＝%s（来源：%s）" % (_i, _nm, _val, _src))
    P.append(" ".join(_cal))

    # ── 九、时效与滞纳金提示（2026-09-29 点评整改 P1-12）──
    # 企业所得税年度汇算清缴截止次年 5 月 31 日；更正申报的滞纳金自期满次日起按日万分之五。
    # 只写通用法定口径，不虚构检查期间的具体日期（期间以报告抬头为准）。
    P.append(
        "九、时效与滞纳金提示：企业所得税年度汇算清缴截止于年度终了之日起五个月内（次年 5 月 31 日）；"
        "检查期间属年度汇算范围且汇算期已届满的，更正申报与补缴将依法自汇算期结束次日起按日加收"
        "万分之五滞纳金。建议先逐项核实差异、确定应补口径后，再行更正申报，并在补缴资金安排中计入"
        "滞纳金成本；印花税、附加税费等小税种的补缴同样自法定缴纳期限届满起计算滞纳金。"
    )

    # ★ 2026-09-27 用户口径：删去本章末「边界声明」——第六章「报告性质和使用说明」已由
    #   `inspector_perspective.administrative_boundary`（文书性质说明）承载，避免两处重复。

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
