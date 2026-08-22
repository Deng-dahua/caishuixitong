"""企业易读版「涉税稽查工作报告」九章数据生成。

从一键分析结果（all_findings / file_results / target_entity 等）组装
`enterprise_readable_report` 字段，供前端 _buildEnterpriseReadableBody 渲染
九章稽查文书式报告。

字段结构对齐前端 static/js/tax-doc-analysis.js 的读取逻辑。
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from collections import Counter, OrderedDict


# ── 14 类税务合规必查资料（与 domain_analysis.py 保持一致）──
_REQUIRED_DOC_CATEGORIES = [
    "银行流水", "销项发票", "进项发票", "记账凭证", "工资表", "社保明细",
    "进销存台账", "合同文件", "科目余额表", "资产负债表", "利润表",
    "增值税申报表", "企业所得税申报表", "个税申报表", "其他税种申报表",
]

# 资料 type → 中文类别名
_DOC_TYPE_NAME = {
    "bank": "银行流水明细", "bank_statement": "银行流水明细",
    "bank_transaction": "银行流水明细",
    "sales_invoice": "销项发票明细",
    "purchase_invoice": "进项发票明细",
    "salary": "工资薪金明细", "payroll": "工资薪金明细",
    "social_security": "社会保险明细",
    "housing_fund": "住房公积金明细",
    "voucher": "记账凭证", "journal": "记账凭证",
    "trial_balance": "科目余额表", "ledger": "科目余额表",
    "contract": "合同文件", "order": "合同文件",
    "inventory": "进销存台账",
    "vat": "增值税申报表", "tax_return": "纳税申报表",
    "fixed_asset": "固定资产资料", "assets": "固定资产资料",
    "related_party": "关联方资料",
    "customs": "海关报关资料", "export": "出口退税资料",
    "financial": "财务报表", "financial_statement": "财务报表",
}

# type → 已覆盖的"必查资料类别"
_DOC_TYPE_TO_CATEGORY = {
    "bank": "银行流水", "bank_statement": "银行流水", "bank_transaction": "银行流水",
    "sales_invoice": "销项发票", "purchase_invoice": "进项发票",
    "salary": "工资表", "payroll": "工资表",
    "social_security": "社保明细", "housing_fund": "社保明细",
    "voucher": "记账凭证", "journal": "记账凭证",
    "trial_balance": "科目余额表", "ledger": "科目余额表",
    "contract": "合同文件", "order": "合同文件",
    "inventory": "进销存台账",
    "vat": "增值税申报表",
    "financial": "财务报表", "financial_statement": "财务报表",
}


def _cn_num(n):
    nums = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
    n = int(n or 0)
    if 0 <= n <= 10:
        return nums[n]
    if 10 < n < 20:
        return "十" + nums[n - 10]
    if 20 <= n < 100:
        return nums[n // 10] + "十" + (nums[n % 10] if n % 10 else "")
    return str(n)


def _seq(items, empty="能够证明相关业务事实的原始资料。"):
    """把 list 转成『第一，…；第二，…。』序列"""
    if not items:
        return empty
    items = [str(x).rstrip("。；") for x in items if str(x).strip()]
    if not items:
        return empty
    nums = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
            "十一", "十二", "十三", "十四", "十五", "十六"]
    parts = []
    for i, x in enumerate(items):
        parts.append("第" + (nums[i] if i < len(nums) else str(i + 1)) + "，" + x)
    return "；".join(parts) + "。"


def _build_identity(report_data):
    te = report_data.get("target_entity", {}) or {}
    snap = report_data.get("_case_snapshot", {}) or {}
    return {
        "subject_name": te.get("name") or "未填写企业名称",
        "taxpayer_id": te.get("uscc") or te.get("taxpayer_id") or te.get("credit_code") or "",
        "period": te.get("period") or "以本轮资料记载期间为准",
        "analysis_round": report_data.get("analysis_round") or snap.get("analysis_round") or 1,
    }


def _build_inspector_perspective():
    return {
        "opening": "根据本轮税务稽查工作安排，现对被检查企业提交并成功读取的财税资料实施检查，并将检查范围、实施程序、查明事实、税务影响、处理意见及后续复查要求报告如下。",
        "work_principle": "以企业上传的原始资料为起点，先确认数据事实，再核对交易、会计处理和纳税申报；正常解释、反向证据和资料缺口分别记录。",
        "conclusion_rule": "只有能够回查到本轮资料的具体事实才写入问题部分；行业指标、风险评分和资料缺失不能单独作为问题认定。",
        "administrative_boundary": "本报告由企业使用的财税风险防控系统依据已提交资料生成，用于模拟税务稽查程序并开展合规整改，不具有税务机关行政执法文书效力；税务机关实际检查结论应以依法送达的正式文书为准。",
    }


def _build_procedures(report_data):
    """七项稽查程序（固定描述 + 本轮实际数字）"""
    file_results = report_data.get("file_results", []) or []
    files_count = report_data.get("files_count", len(file_results)) or len(file_results)
    full_read = sum(1 for fr in file_results if isinstance(fr, dict) and "完整" in str(fr.get("actions", [])))
    partial = sum(1 for fr in file_results if isinstance(fr, dict) and "部分" in str(fr.get("actions", [])))
    blocked = sum(1 for fr in file_results if isinstance(fr, dict) and ("失败" in str(fr.get("actions", [])) or "阻断" in str(fr.get("actions", []))))
    findings = report_data.get("all_findings", []) or []
    confirmed = [f for f in findings if isinstance(f, dict) and f.get("level") not in ("待核验",)]

    procedures = [
        ("确认被检查企业、期间和资料批次",
         f"确认被检查企业为{report_data.get('target_entity', {}).get('name', '被检查企业')}，检查期间以本轮资料记载期间为准；登记并冻结{files_count}份资料。本轮程序结果为：企业主体、检查轮次和资料范围已经记录；无法由本轮资料覆盖的期间和业务不作外推。"),
        ("逐份读取资料并检查数据质量",
         f"逐份检查资料能否读取、字段是否可定位、金额是否能够重新计算。可完整用于本轮核对{full_read}份，部分读取{partial}份，读取阻断{blocked}份。本轮程序结果为：每份资料均形成明确使用范围；部分读取和阻断内容已经转入补件，不用空结果代替检查。"),
        ("执行单份资料内部复算",
         f"分别检查银行余额连续性、发票号码及金额税额、工资人员和月份、社会保险与住房公积金、账簿借贷及其他已具备字段的内部关系。本轮程序结果为：现有资料能够直接证明的具体问题{len(confirmed)}项；已执行且本轮未发现达到检查条件异常的项目见第五章。"),
        ("执行账、票、表、税、款、货、合同和人员交叉核对",
         "按照实际可用资料，把交易主体、业务期间、合同履约、发票、资金、会计处理和纳税申报连接起来；资料链条缺少节点时停止该项外推。本轮程序结果为：完整具备资料节点的交叉核对链条以实际可用资料为准；仍有资料需要补充识别或修复。"),
        ("检查正常解释、反向证据和税务影响",
         "对每项差异分别检查正常业务原因、反向证据、企业说明、政策适用期间和金额计算条件，避免把异常信号直接写成违法结论。本轮程序结果为：问题部分只保留能够回查到本轮资料的具体事实；税务性质或金额尚不能确定的内容已经明确说明限制。"),
        ("检查应有但未提供的资料及其连带影响",
         "根据企业行业、经营活动和税种，反向检查本轮未取得的申报、账簿、合同、履约、资金、人员、资产和优惠资料。本轮程序结果为：形成受阻检查及补件要求；缺少资料只表示相应检查未完成，不直接认定企业存在违法。"),
        ("形成处理意见、验收标准和下一轮复查计划",
         "对已确认问题逐项提出处理步骤、责任安排、完成标准和应回传资料；对资料缺口明确补齐后必须重跑的检查。本轮程序结果为：本轮保持涉税稽查工作报告草稿状态。"),
    ]
    return [{"seq": i + 1, "name": name, "narrative": narrative}
            for i, (name, narrative) in enumerate(procedures)]


def _build_materials(report_data):
    """按资料类别归并 file_results，生成资料清单"""
    file_results = report_data.get("file_results", []) or []
    groups = OrderedDict()
    for fr in file_results:
        if not isinstance(fr, dict):
            continue
        ftype = fr.get("type", "unknown")
        groups.setdefault(ftype, []).append(fr)

    materials = []
    seq = 1
    for ftype, items in groups.items():
        display = _DOC_TYPE_NAME.get(ftype, "财税资料")
        total_rows = 0
        for fr in items:
            for a in (fr.get("actions") or []):
                import re as _re
                m = _re.search(r"(\d+)条", str(a))
                if m:
                    total_rows += int(m.group(1))
        materials.append({
            "seq": seq,
            "document_type": display,
            "display_name": display,
            "read_method": "电子表格读取",
            "read_result": f"{len(items)}份读取完整",
            "use_boundary": "全部可进入本轮自动核对",
            "narrative": f"本轮共收到{len(items)}份{display}，共读取{total_rows}条记录。系统通过电子表格读取进行处理，读取结果为{len(items)}份读取完整。本轮使用范围为：全部可进入本轮自动核对。具体文件名称、文件指纹、解析回执和逐行定位保留在内部资料底稿中。",
        })
        seq += 1
    return materials


def _problem_paragraphs(f):
    """从 finding 生成六段式问题说明"""
    detail = str(f.get("detail") or f.get("description") or "")
    how = str(f.get("how_found") or "")
    reasons = f.get("reasonable_explanations") or f.get("alternative_explanations") or []
    suggestion = str(f.get("suggestion") or "")
    steps = f.get("investigation_steps") or []
    src_files = f.get("source_files") or []
    scope = "、".join(sorted({str(s.get("type") or s.get("file") or "") for s in src_files if isinstance(s, dict)})) or "本轮已上传并成功读取的相关资料"
    tax_impact = str(f.get("tax_impact") or "")
    if not tax_impact or "尚未形成" in tax_impact:
        tax_impact = "本项只确认资料中存在需要核清的具体差异，不把差异直接当作应补税额。税额影响以完成资料更正、账税核对和重新计算后的结果为准。"

    paragraphs = [
        {"heading": "查明的主要事实",
         "text": "经查，" + detail + "上述数字来自本轮已读取资料的全量筛查，不是抽样估计。"},
        {"heading": "结论状态",
         "text": _conclusion_statement(f)},
        {"heading": "检查范围、方法和资料依据",
         "text": "本项使用的资料范围为" + scope + "。稽查人员直接读取企业上传的资料，按照同一口径逐项重新计算，并将计算结果与资料中的记录进行比较。原始文件指纹、读取回执、复算指标、代表性明细和可用的原文件行号已保存在内部稽查底稿中；专业人员可在工作底稿中回查。"},
        {"heading": "这件事对企业意味着什么",
         "text": "本轮确认资料中存在能够重复计算的数据差异。企业应先修复资料完整性和计算口径，再开展账、票、表、税和资金用途核对。仅凭这一数据差异，不能认定企业少缴税款或违反税收规定。" + tax_impact},
        {"heading": "应当同时核对的正常业务原因",
         "text": "出现上述情况不当然等于发生税务违法。企业应按同一证据标准核对：" + _seq(reasons, "正常业务原因和对企业有利的原始资料。")},
        {"heading": "企业应当怎样处理",
         "text": "企业应当依据真实业务办理，不得为了消除系统提示而倒签、补造或者无事实依据调整。具体处理顺序为：" + _seq(steps or [suggestion], "按真实业务和原始资料查明原因并作真实处理。")},
        {"heading": "怎样才算处理完成",
         "text": "本项只有达到下列条件后才可申请关闭：" + _seq(["本次发现的每一组差异都有原始资料、差异原因和处理结果可以回查",
                                                          "更正后的数据能够与会计记录和相关纳税申报资料核对一致，或对仍有差异的事项单独说明",
                                                          "补充资料后重新检查，系统能够分别列示合理事项、仍需处理事项和证据不足事项"],
                                                         "问题能够定位、处理过程能够回查，重新检查不再出现同一差异。")},
    ]
    return paragraphs


def _conclusion_statement(f):
    """两级结论文本：可核定→最终答案；待核→建议与补证要求"""
    grade = str(f.get("conclusion_grade") or "")
    if grade == "已核定":
        answer = str(f.get("final_answer") or "").strip()
        scope_note = str(f.get("conclusion_scope_note") or "").strip()
        return (
            (answer or "本项结论已由本轮所报资料直接计算核定。")
            + (" " + scope_note if scope_note else "")
            + " 本项无须补充核实即可作为定案事实引用；行政处理决定仍由稽查人员依程序作出。"
        )
    suggestion = str(f.get("suggestion") or "").strip()
    return (
        "本项为待核事项：现有资料只能确认疑点信号，尚不足以作出最终认定。"
        "须补充外部证据（合同、物流单据、盘点表、权属证明等）后方可定性。"
        + (f"本轮建议：{suggestion}" if suggestion else "请按报告『企业应当怎样处理』一节逐项补证。")
    )


def _build_confirmed_problems(report_data):
    """从 findings 组装『确认的具体问题』（level 非待核验/信息的）"""
    findings = report_data.get("all_findings", []) or []
    problems = []
    seq = 1
    for f in findings:
        if not isinstance(f, dict):
            continue
        if f.get("level") in ("待核验", "信息", "低风险"):
            continue
        ev = f.get("_evidence_ref", {}) or {}
        problems.append({
            "seq": seq,
            "title": (f.get("type") or "具体资料问题").replace("待核事实：", "").replace("待核事实:", ""),
            "conclusion_grade": f.get("conclusion_grade") or "待核",
            "final_answer": str(f.get("final_answer") or ""),
            "narrative_paragraphs": _problem_paragraphs(f),
            "trace_id": ev.get("trace_id", ""),
        })
        seq += 1
    return problems


def _build_completed_checks(report_data):
    """已执行且本轮未发现达到条件异常的检查（level 待核验的）"""
    findings = report_data.get("all_findings", []) or []
    completed = []
    seq = 1
    for f in findings:
        if not isinstance(f, dict):
            continue
        if f.get("level") != "待核验":
            continue
        completed.append({
            "seq": seq,
            "title": (f.get("type") or "检查").replace("待核事实：", "").replace("待核事实:", ""),
            "narrative": "稽查人员对本项执行了本轮规定的检查程序，按照该检查项目规定的字段、口径和计算条件完成筛查，并记录本轮唯一执行状态。检查结果为：本轮已经取得该项检查所需资料并执行规则，未发现达到该规则检查条件的异常。",
        })
        seq += 1
    return completed


def _build_action_plan(problems):
    """处理意见（从确认问题派生）"""
    plans = []
    for i, p in enumerate(problems):
        plans.append({
            "seq": _cn_num(i + 1),
            "problem": p.get("title", ""),
            "narrative": "企业应先依据真实业务和原始资料办理，不得倒签、补造或者作无事实依据的调整。本项由企业指定熟悉该项业务和资料的负责人办理，并由另一名人员复核。整改不能仅以口头说明作为完成依据，验收时应确认处理过程能够回查、更正后的数据能够与会计和申报资料核对一致。",
        })
    return plans


def _build_further_checks(report_data):
    """受阻检查：14 类必查资料中未提交的类别"""
    file_results = report_data.get("file_results", []) or []
    covered = set()
    for fr in file_results:
        if not isinstance(fr, dict):
            continue
        cat = _DOC_TYPE_TO_CATEGORY.get(fr.get("type", ""))
        if cat:
            covered.add(cat)
    # 从 target_entity / material_intel 补充已识别类别
    mi = report_data.get("comprehensive", {}).get("material_intel", {}) if isinstance(report_data.get("comprehensive"), dict) else {}
    if isinstance(mi, dict):
        for k in mi.keys():
            covered.add(str(k))

    missing = [c for c in _REQUIRED_DOC_CATEGORIES if c not in covered]

    further = []
    for i, cat in enumerate(missing):
        further.append({
            "seq": i + 1,
            "title": f"未收到“{cat}”导致相关检查未完成",
            "narrative_paragraphs": [
                {"heading": "本轮检查结论",
                 "text": f"经检查，本轮未收到该项资料，无法取得完成相关检查所需的完整事实。资料缺失只表示检查范围受限，不表示企业已经存在违法或少缴税问题。本轮相关检查未完成，所列风险方向目前无法排除，但不作违法、少缴税款或处罚认定。"},
                {"heading": "被阻断的检查和风险影响",
                 "text": f"由于资料条件不具备，本轮无法完成与“{cat}”相关的账、票、表、税、款交叉核对。目前仍无法排除相应的风险方向。涉及{cat}的检查结论不得显示为无异常或已经合规。"},
                {"heading": "补充资料要求",
                 "text": f"企业应补充{cat}。如原资料客观上无法取得，可以提供能够证明同一事实的替代资料。"},
                {"heading": "下一轮复查程序",
                 "text": f"资料补齐后，稽查人员将重新执行受影响的全部检查程序。本项完成标准为：资料能够覆盖本轮检查期间，来源、形成时间、原始版本和具体业务可以回查；补齐后重新运行受影响的全部检查程序。"},
            ],
        })
    return further


def _build_summary(report_data, problems, completed, further):
    findings = report_data.get("all_findings", []) or []
    file_results = report_data.get("file_results", []) or []
    files_count = report_data.get("files_count", len(file_results)) or len(file_results)
    types = {fr.get("type") for fr in file_results if isinstance(fr, dict)}
    te = report_data.get("target_entity", {}) or {}

    key_points = []
    for p in problems[:3]:
        first = p.get("narrative_paragraphs", [{}])[0].get("text", "") if p.get("narrative_paragraphs") else ""
        key_points.append(f"重点{p['seq']}：{p.get('title', '')}。{first[:120]}")
    if further:
        key_points.append(f"还有{len(further)}项检查尚未完成，优先补齐资料。这些事项表示检查范围受限，不表示已经发生相应违法。")

    verified_cnt = sum(1 for p in problems if p.get("conclusion_grade") == "已核定")
    pending_cnt = len(problems) - verified_cnt
    grade_phrase = ""
    if problems:
        if verified_cnt and pending_cnt:
            grade_phrase = (f"其中{verified_cnt}项为账面勾稽已核定事项，已直接给出最终结论；"
                            f"{pending_cnt}项为待核事项，须补充外部证据后定性，本轮已随附检查建议。")
        elif verified_cnt:
            grade_phrase = f"全部{verified_cnt}项为账面勾稽已核定事项，已直接给出最终结论。"
        else:
            grade_phrase = f"全部{pending_cnt}项为待核事项，须补充外部证据后定性，本轮已随附检查建议。"

    headline = (f"本次税务稽查共接收{files_count}个文件，归并为{len(types)}类资料。稽查人员经逐项读取、复算和交叉核对，"
                f"确认{len(problems)}项已有资料能够证明的具体问题。{grade_phrase}"
                f"另有{len(completed)}项检查已执行且本轮未发现达到条件的异常；"
                f"{len(further)}项因资料不足或影响范围尚未查清，本轮不作问题认定，补充资料后再检查。")

    owner_message = (f"请企业负责人先组织处理本报告列明的具体问题，并按要求补齐资料。"
                     f"完成真实更正和资料补充后，应发起新一轮全量复查，由稽查人员继续核对原问题是否处理完成，以及补充资料是否带出新的关联问题。")

    return {
        "headline": headline,
        "owner_message": owner_message,
        "key_points": key_points,
        "received_material_count": files_count,
        "material_category_count": len(types),
        "confirmed_problem_count": len(problems),
        "verified_problem_count": verified_cnt,
        "pending_problem_count": pending_cnt,
        "completed_check_count": len(completed),
        "further_check_count": len(further),
    }


def build_enterprise_readable_report(report_data):
    """主入口：从分析结果组装 enterprise_readable_report"""
    if not isinstance(report_data, dict):
        return {}

    problems = _build_confirmed_problems(report_data)
    completed = _build_completed_checks(report_data)
    materials = _build_materials(report_data)
    procedures = _build_procedures(report_data)
    further = _build_further_checks(report_data)
    summary = _build_summary(report_data, problems, completed, further)
    plans = _build_action_plan(problems)

    return {
        "compilation_style": "税务稽查文书式报告",
        "generated_date": datetime.now().strftime("%Y年%m月%d日 %H时%M分"),
        "identity": _build_identity(report_data),
        "inspector_perspective": _build_inspector_perspective(),
        "summary": summary,
        "inspection_procedures": procedures,
        "materials": materials,
        "confirmed_problems": problems,
        "completed_checks": completed,
        "action_plan": plans,
        "further_checks": further,
        "recheck": {
            "trigger": "企业完成真实整改或补充资料后，重新点击一键分析。",
            "work": "下一轮将重新读取全部资料，复查本轮问题，检查补充资料带出的关联事项，并比较前后两轮变化。",
            "convergence": "问题逐项处理、资料逐步完整、账务与申报能够相互核对，才表示企业正在趋于合规；不能以问题数量为零或分数下降单独判断。",
        },
        "report_statement": [
            "本报告只对本轮已上传且能够读取的资料负责，未上传资料不在本轮具体问题认定范围内。",
            "本报告所列“具体问题”均有本轮资料中的直接数据或可回查证据支持；资料不足的事项已单独列入补充资料后再检查清单。",
            "本报告采用税务稽查文书式结构和稽查人员陈述口径编制，所列检查事实、处理意见和复查要求用于企业合规整改。",
            "企业应依据真实业务和原始资料办理整改，不得倒签、补造、篡改、删除或隐匿资料。",
        ],
    }
