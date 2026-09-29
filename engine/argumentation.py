# -*- coding: utf-8 -*-
"""
论证链引擎 —— 分析论证贯穿整个风险检查过程
==================================================

稽查不是「发现异常→下结论」，而是**论证**：
    主张（触了哪条红线）
      → 论据（线索链+证据链支撑到什么程度）
        → 反证（企业可能的正当理由）
          → 反驳/检验（反证需什么证据才能成立，现有资料能否支撑）
            → 裁决（成立 / 不成立 / 证据不足待证）

三种裁决（不可逾越的边界）
--------------------------------------------------
    红线成立（confirmed）   证据链闭合且无有效反证 —— 可以作出确定性判断
    红线不成立（excluded）  反证成立并足以解释全部异常 —— 予以排除
    红线待证（unconfirmed） 证据不足或正反双方势均力敌 —— 转入置疑清单，
                            由企业提供资料自证，**系统既不认定也不否认**

铁律
--------------------------------------------------
1. 发现 ≠ 确认。触红只表示「有法定情形需要核实」。
2. 缺失型信号（该有的没有）一律作为待证信号抓取，禁止通过提高阈值放过。
3. 证据不足一律转置疑清单，系统绝不自动定罪，也绝不自动免责。
"""

import re
from typing import Any, Dict, List, Optional

# 四个裁决层级：「触红」与「定性」是两个层次，不可混为一谈
#   —— 符合红线的构成要件即已触红（客观判断，与行业无关）；
#   —— 证据链是否闭合只决定能否「定性」，不决定「是否触红」。
# ★ 2026-09-27（用户要求通俗化）：把"红线成立"等内部裁定词改为老板也能看懂的说法。
#   语义不变：仍严格区分「触红（出现法定禁止情形）」与「定性（证据链是否闭合）」，
#   且绝不写"已认定违法"——系统只作初步判断，以税务机关最终认定为准。
_VERDICT_CONFIRMED = "已触碰税务违规红线（资料齐全，可作初步判断）"   # 触红 + 材料齐全 → 可初步判断
_VERDICT_HIT_PENDING = "已触碰税务违规红线（资料不足，待补证后判断）" # 触红 + 材料未齐 → 置疑清单
_VERDICT_EXCLUDED = "经核查未触碰违规红线（已有合理解释）"       # 反证成立 → 排除
_VERDICT_WEAK = "现有资料不足以形成税务疑点"                   # 无线索支撑 → 仅作观察

# 报告用的结论分级
GRADE_CONFIRMED = "已核定"
GRADE_PENDING = "待核"
GRADE_EXCLUDED = "已排除"


# ── 置信度模型权重（2026-09-29 外置可配）──────────────────────────────────────
# 原硬编码于 build_argumentation 内（0.50/0.25/0.10/±0.08/±0.05/−0.20），现统一收敛为
# 单一权威配置，便于回测调参、避免散落多处导致同一模型两套权重。
# 语义（逐项可解释，不靠拍脑袋）：
#   base                —— 触红即有的基础置信（有法定情形需核实）；
#   closure             —— 证据链闭合度每提升 1.0 的加权（材料越齐越可信）；
#   data_completeness   —— 线索链数据完整度每提升 1.0 的加权；
#   high_risk / low_risk—— 风险等级对置信的微调（高则+ / 低则−）；
#   rebuttal_ratio      —— 反证提交比例每提升 1.0 的加权（**为负**：企业提交正当理由
#                          证据越充分，疑点置信越应下调，防误判偏高风险）。
# 设计约束：base + closure(=1) + data(=1) ≈ 1.0（证据与数据全齐时接近满置信），
#          高风险的 +0.08 不应突破 0.95 上界（下方 clamp）。
CONFIDENCE_WEIGHTS: Dict[str, float] = {
    "base": 0.50,
    "closure": 0.25,
    "data_completeness": 0.10,
    "high_risk": 0.08,
    "low_risk": -0.05,
    "rebuttal_ratio": -0.20,
}

# 数据源标识 → 中文名（论证叙述「线索链」用，避免 salaries 等英文标识进入报告正文）
# 与 enterprise_report._SOURCE_LABELS 保持一致；长键在前，避免 inventory 抢先命中 inventory_ledger。
_SOURCE_ZH = [
    ("tax_declarations", "纳税申报表"), ("social_security", "社保明细"),
    ("transport_contracts", "运输合同"), ("inventory_ledger", "进销存台账"),
    ("company_profile", "企业基础信息"), ("target_entity", "目标企业信息"),
    ("fixed_assets", "固定资产台账"), ("trial_balance", "科目余额表"),
    ("declaration", "纳税申报表"), ("salaries", "工资表"),
    ("bank_txs", "银行流水"), ("sal_invs", "销项发票"),
    ("pur_invs", "进项发票"), ("vouchers", "记账凭证"),
    ("inventory", "进销存台账"), ("contracts", "合同台账"),
    ("bom", "物料清单"),
]


def _zh_source(src: Any) -> str:
    """把数据源标识（salaries 或「salaries、social_security」复合串）转为中文。"""
    s = str(src or "")
    if not s:
        return ""
    for en, zh in sorted(_SOURCE_ZH, key=lambda x: -len(x[0])):
        s = s.replace(en, zh)
    return s


def _justifications(finding: Dict, redline: Dict) -> List[str]:
    """汇总正当理由（反证）：红线库定义 + 发现自带的合理解释"""
    outs: List[str] = []
    for j in (redline.get("justifications") or []):
        s = str(j).strip()
        if s and s not in outs:
            outs.append(s)
    for key in ("reasonable_explanations", "alternative_explanations", "opposing_evidence"):
        vals = finding.get(key) or []
        if isinstance(vals, dict):
            vals = list(vals.values())
        for v in vals:
            if isinstance(v, dict):
                s = str(v.get("text") or v.get("explanation") or v.get("name") or "").strip()
            else:
                s = str(v).strip()
            if s and s not in outs:
                outs.append(s)
    return outs


def _grounds(finding: Dict, clue: Dict, evidence: Dict) -> List[str]:
    """论据：支撑主张的具体事实"""
    grounds: List[str] = []
    if clue.get("terminal_signal"):
        grounds.append(f"线索链终端信号：{clue['terminal_signal']}")
    for n in (clue.get("nodes") or []):
        if n.get("has_data") and n.get("observed") and n.get("step", 0) >= 2:
            g = f"第{n['step']}环：{n.get('action','')}——{n.get('observed','')}"
            if g not in grounds:
                grounds.append(g)
    for e in (evidence.get("elements") or []):
        if e.get("status") == "已有":
            grounds.append(f"{e['role']}「{e['name']}」已在案（{e['purpose']}）")
    return grounds[:6]


def build_argumentation(finding: Dict, redline: Dict, clue: Dict,
                        evidence: Dict, engine_data: Optional[Dict] = None) -> Dict:
    """
    构建单条疑点的论证链。

    返回：
        {
          "claim": "主张：...",
          "legal_basis": [...],
          "grounds": [...],           # 论据
          "rebuttals": [...],         # 反证（正当理由）
          "rebuttal_tests": [...],    # 每项反证成立所需的证据与当前能否验证
          "verdict": "红线成立（证据闭合）/...",
          "confidence": 0~1,
          "reasoning": "论证过程叙述（大白话）",
          "next_actions": [...]       # 下一步要做什么
        }
    """
    engine_data = engine_data or {}
    _suspect = str(redline.get('suspect') or '税务风险')
    # suspect 已含「涉嫌」字样，不得重复叠加
    _suspect_txt = _suspect if _suspect.startswith("涉嫌") else f"涉嫌{_suspect}"
    # ★ 2026-09-25：claim 文本**不带红线编号** —— 编号是内部追溯标识，已在条目
    #   `redline_id` 字段中透传；写进面向读者的表述里，一旦某条渲染路径没过净化闸门
    #   就会泄漏给企业（实测内部树里 16 处 claim 仍带 RL-XXX）。
    claim = (f"本企业触碰红线「{redline.get('name','')}」，{_suspect_txt}")
    grounds = _grounds(finding, clue, evidence)
    rebuttals = _justifications(finding, redline)

    closure = float(evidence.get("closure") or 0.0)
    nodes = clue.get("nodes") or []
    data_completeness = (
        sum(1 for n in nodes if n.get("has_data")) / len(nodes) if nodes else 0.0
    )
    level = str(finding.get("level") or "")

    # 反证可验证性：反证所需证据是否已提供
    rebuttal_elements = [e for e in (evidence.get("elements") or []) if e.get("role") == "反证"]
    rebuttal_supported = sum(1 for e in rebuttal_elements if e.get("status") == "已提交")
    rebuttal_ratio = (rebuttal_supported / len(rebuttal_elements)) if rebuttal_elements else 0.0

    # 置信度模型（不靠拍脑袋，逐项可解释；权重外置，见 CONFIDENCE_WEIGHTS 可配）
    w = CONFIDENCE_WEIGHTS
    confidence = w["base"]
    _conf_parts: List[Dict[str, Any]] = [{"项": "基准分", "权重": w["base"], "取值": 1.0,
                                          "贡献": round(w["base"], 4)}]
    confidence += w["closure"] * closure
    _conf_parts.append({"项": "证据链闭合度", "权重": w["closure"], "取值": round(closure, 4),
                        "贡献": round(w["closure"] * closure, 4)})
    confidence += w["data_completeness"] * data_completeness
    _conf_parts.append({"项": "环节数据完整度", "权重": w["data_completeness"],
                        "取值": round(data_completeness, 4),
                        "贡献": round(w["data_completeness"] * data_completeness, 4)})
    if "高风险" in level:
        confidence += w["high_risk"]
        _conf_parts.append({"项": "风险等级为高", "权重": w["high_risk"], "取值": 1.0,
                            "贡献": round(w["high_risk"], 4)})
    elif "低风险" in level:
        confidence += w["low_risk"]
        _conf_parts.append({"项": "风险等级为低", "权重": w["low_risk"], "取值": 1.0,
                            "贡献": round(w["low_risk"], 4)})
    confidence += w["rebuttal_ratio"] * rebuttal_ratio
    _conf_parts.append({"项": "反证已提交比例（反向计分）", "权重": w["rebuttal_ratio"],
                        "取值": round(rebuttal_ratio, 4),
                        "贡献": round(w["rebuttal_ratio"] * rebuttal_ratio, 4)})
    confidence = round(max(0.05, min(0.95, confidence)), 2)

    # ── 第一层：是否触红（客观判断） ──
    # 方法论铁律：一旦符合某项风险情形即触碰税务红线，触红与否**只取决于
    # 线索链是否给出可量化的触红事实**，与证据链闭合度无关——闭合度决定
    # 的是「能否定性」，不是「是否触红」。用闭合度卡触红会让真实疑点被吞掉。
    has_signal = bool(clue.get("terminal_signal"))
    redline_hit = has_signal

    # ── 第二层：能否定性（取决于证据链闭合度与反证） ──
    if redline_hit and rebuttal_ratio >= 0.5 and closure < 0.60:
        verdict, grade = _VERDICT_EXCLUDED, GRADE_EXCLUDED
    elif redline_hit and closure >= 0.80 and not evidence.get("direct_missing"):
        verdict, grade = _VERDICT_CONFIRMED, GRADE_CONFIRMED
    elif redline_hit:
        verdict, grade = _VERDICT_HIT_PENDING, GRADE_PENDING
    else:
        verdict, grade = _VERDICT_WEAK, GRADE_PENDING

    # 勾稽异常类红线（借贷不平 / 余额滚动关系断裂等）：仅揭示数据勾稽断裂，
    # 本身不足以证明隐瞒收入或账外资金循环，须有正面隐瞒 / 账外证据方可定性。
    # 证据链齐全只说明异常「可读出」，不说明「已定性」；故即使闭合度达标也不自动确认
    # （遵守铁律：发现不等于确认，证据不足一律转置疑清单）。
    if redline.get("disposition") == "reconciliation_anomaly" and verdict == _VERDICT_CONFIRMED:
        verdict, grade = _VERDICT_HIT_PENDING, GRADE_PENDING

    # 反证成立条件检验
    rebuttal_tests = []
    for r in rebuttals[:5]:
        rebuttal_tests.append({
            "rebuttal": r,
            "needs": "须提供与该理由对应的书面协议、原始单据与履行记录",
            "verifiable_now": "本轮资料能够验证" if rebuttal_supported else "本轮资料无法验证，须补充资料",
        })

    reasoning = _compose_reasoning(redline, claim, clue, evidence, rebuttals, verdict, confidence)

    # ★ 2026-09-27（P3）：优先补"本项文本真正提到的资料"（红线库 required_sources 偏宽，
    #   会出现"同一凭证借贷不平"却先要"合同文件"）。做法=把文本命中的资料**前置**，不删任何需求。
    _ftext = " ".join(str(finding.get(k) or "") for k in ("type", "detail", "description", "title"))
    _mat_hits: List[str] = []
    for _kw, _mat in (("记账凭证", "记账凭证"), ("凭证", "记账凭证"), ("序时账", "序时账"),
                      ("科目余额表", "科目余额表"), ("银行流水", "银行流水"),
                      ("销项发票", "销项发票"), ("进项发票", "进项发票"),
                      ("工资表", "工资表"), ("社保", "社保明细"), ("劳动合同", "劳动合同"),
                      ("进销存", "进销存台账"), ("运输合同", "运输合同"), ("合同", "合同文件"),
                      ("固定资产", "固定资产清单"), ("申报表", "纳税申报表")):
        if _kw in _ftext and _mat not in _mat_hits:
            _mat_hits.append(_mat)
    next_actions: List[str] = []
    for m in (evidence.get("missing_materials") or [])[:5]:
        next_actions.append(f"补充提供「{m}」")
    # ★ 2026-09-25：「待核」项不是"缺材料"，而是"已有相关资料但未必含本项所需"，
    #   动作应为"确认"而非"补充提供" —— 否则报告会让企业去补一份其实已经交了的资料。
    for m in (evidence.get("verify_materials") or [])[:5]:
        next_actions.append(f"确认已提供的「{m}」中是否包含本项所需内容")
    for e in (evidence.get("direct_missing") or [])[:3]:
        next_actions.append(f"取得直接证据：{e}")
    if rebuttals:
        next_actions.append("由企业对上述正当理由逐项提交书面证明与原始单据")
    steps = finding.get("investigation_steps") or []
    for s in steps[:3]:
        if isinstance(s, dict):
            s = str(s.get("step") or s.get("action") or s)
        s = str(s).strip()
        if s and s not in next_actions:
            next_actions.append(s)

    # 触红后置信度下限 0.60：既然符合构成要件，就不能因证据未齐而说成「没把握」。
    # ★ 但被有效反证排除（rebuttal_ratio≥0.5 且闭合度不足 → 已判 EXCLUDED）的红线，
    #   其低置信是"正当理由成立"的真实反映，不得被地板顶回 0.60，否则反证机制被掩盖。
    if redline_hit and verdict != _VERDICT_EXCLUDED:
        confidence = round(max(0.60, min(0.95, confidence)), 2)

    # 把"本项文本命中的资料"前置（去重，不删既有需求）
    _pre = [f"补充提供「{_m}」" for _m in _mat_hits]
    next_actions = _pre + [a for a in next_actions if a not in _pre]

    # ★ 2026-09-27（P3）：next_actions 相关性排序键（资料名出现在本项文本里 → 0，排前）
    def _na_rel_rank(a):
        t = str(a)
        for _p in ("补充提供「", "确认已提供的「", "取得直接证据："):
            t = t.replace(_p, "")
        t = t.split("」")[0].split("：")[-1].strip()
        return 0 if (t and t in _ftext) else 1

    return {
        "claim": claim,
        "redline_id": redline.get("id", ""),
        "redline_name": redline.get("name", ""),
        "suspect": redline.get("suspect", ""),
        "legal_basis": list(redline.get("legal_basis") or []),
        "constituents": list(redline.get("constituents") or []),
        # ★ 2026-09-27：本企业**实际涉及**的构成要件（由域逐条判定后带出；只列命中的）。
        #   企业报告「一、涉及的风险事项」优先采用它（不再罗列通用要件清单）。
        "constituent_hits": list(finding.get("constituent_hits") or []),
        "grounds": grounds,
        "rebuttals": rebuttals,
        "rebuttal_tests": rebuttal_tests,
        "verdict": verdict,
        "conclusion_grade": grade,
        "redline_hit": redline_hit,
        "confidence": confidence,
        # ★ 2026-09-29（点评整改 P1-9）：可信度的**分项计算依据**（可逐项复算）。
        #   外部点评指出「判断可信度约75%（较高）」类表述无任何计算公式披露，
        #   读者无法判断这个数是怎么来的 → 现随结论一并输出各分项权重与取值。
        "confidence_breakdown": _conf_parts,
        "confidence_formula": ("可信度 = 基准分 0.50 + 0.25×证据链闭合度 + 0.10×环节数据完整度 "
                              "+ 0.08×（高风险）/ −0.05×（低风险）− 0.20×反证已提交比例，"
                              "结果截断在 5%~95% 之间；各分项为加权和，权重固定、可复算。"),
        "closure": closure,
        "reasoning": reasoning,
        "next_actions": sorted(next_actions, key=_na_rel_rank)[:8],
        "remedy": evidence.get("remedy", ""),
    }


def _compose_reasoning(redline: Dict, claim: str, clue: Dict, evidence: Dict,
                       rebuttals: List[str], verdict: str, confidence: float) -> str:
    """把论证过程写成一段自然叙述（检查人员口吻，不出现字段标记与编号）。

    报告是给人看的文书，不保留【主张】【依据】这类内部字段标记，
    也不出现 RL-XXX 这样的红线编号（编号只在系统内部用于追溯）。
    叙述按「查到了什么 → 凭什么这样判断 → 现在能定到什么程度 → 企业可以怎么解释」
    的自然逻辑展开。
    """
    parts = []
    # 去掉 claim 里的红线编号（「本企业触碰红线 RL-PAY-001「名称」，涉嫌…」→ 自然表述）
    claim_text = re.sub(r"红线\s*RL-[A-Z]+-\d+\s*", "红线", claim or "")
    claim_text = re.sub(r"RL-[A-Z]+-\d+\s*", "", claim_text).strip()
    parts.append(f"{claim_text}。")
    # ★ 2026-09-25：构成要件是**待核对的判断标准**，不是已成立的事实。
    #   旧文案写"这样判断的依据是：…"，读起来像这些要件已经成立 ——
    #   用户无法分辨哪些是"标准"、哪些是"本轮核对到的事实"。
    constituents = redline.get("constituents") or []
    if constituents:
        parts.append(f"判断本项是否成立，要看这几项标准是否同时满足：{_join(constituents, '；')}。")
    if clue.get("terminal_signal"):
        parts.append(f"本轮从所报资料中直接核对到的事实是：{clue.get('terminal_signal')}。")

    # ★ 2026-09-25 根因修复：资料归属必须按**实际取得情况**陈述。
    #   旧文案把红线模板声明的"应查资料路径"当成"已核对路径"，写出
    #   "这些事实是从固定资产明细账、试生产记录、折旧计算表、设备产能这几类资料里
    #     逐层核对出来的" —— 而该企业这几类资料**一份都没提交**（证据表里全是缺失）。
    #   现改为：只说本轮**实际读取到**的资料（可核验），并把未取得数据的环节显式点出。
    real_sources = [_zh_source(s) for s in (clue.get("sources_used") or []) if s]
    if real_sources:
        parts.append("本轮实际读取到的资料是：" + "、".join(real_sources[:6]) + "。")
    nodes = clue.get("nodes") or []
    gap_nodes = [n for n in nodes if not n.get("has_data")]
    if gap_nodes:
        parts.append(
            "本项核查共%d环，其中" % len(nodes)
            + "、".join("第%s环" % n.get("step") for n in gap_nodes)
            + "因本轮未取得该环节所需资料，未取得数据（各环实际读到的数据见上一段明细表）。"
        )
    elif nodes:
        # ★ 不写"全部取得数据"：各环有数据只代表该环节取得了可量化数据，
        #   不代表"该环对应资料已提供/已读取"（环的对应资料是检查路径上的应查项）。
        #   可证的表述是"各环数据见明细表"，读什么、读到什么由表逐环列示。
        parts.append("本项核查共%d环，各环实际读到的数据见上一段明细表。" % len(nodes))
    _v = evidence.get('verdict', '')
    # ★ 2026-09-27（用户要求通俗化）：材料齐全程度用项数，并补列「还缺的具体材料名」，
    #   让非财税背景的负责人知道缺的是哪几样（仅列前 6 样，避免过长）。
    _av = int(evidence.get('available_count', 0) or 0)
    _mc = int(evidence.get('missing_count', 0) or 0)
    _mm = evidence.get('missing_materials') or []
    _mat_txt = f"就资料来说，{_v}（已提供{_av}项"
    if _mm:
        _mat_txt += "；尚缺：" + "、".join(str(m) for m in _mm[:6])
    elif _mc:
        _mat_txt += f"；还缺{_mc}项"
    else:
        _mat_txt += "，所需资料已齐备"
    _mat_txt += f"{'；' + evidence.get('rebuttal_status', '') if evidence.get('rebuttal_status') else ''}。"
    parts.append(_mat_txt)
    if rebuttals:
        parts.append(
            f"企业如果认为这不成立，通常可以说明：{_join(rebuttals[:3], '；')}。"
            "但这些说明能不能采信，要看有没有书面协议和原始单据，口头解释不能作为认定依据。"
        )
    if verdict == _VERDICT_CONFIRMED:
        tail = "支撑材料已经齐全，这一项可以直接认定；企业如有异议，需要更正所报资料本身或者提出相反证据。"
    elif verdict == _VERDICT_HIT_PENDING:
        if redline.get("disposition") == "reconciliation_anomaly":
            tail = ("该项属于数据勾稽异常（借贷不平或余额滚动关系断裂），本身不足以认定违法；"
                    "需企业说明原因（如红字冲销、补记凭证、在途未达账项等），"
                    "无法合理解释且存在账外资金或隐瞒收入线索的，转进一步核查。")
        else:
            tail = ("已经触碰税务红线，但材料还不够齐全，本轮暂不下结论，"
                    "转由企业补充上述材料后重新检查；补证之前既不认定违法，也不予排除。")
    elif verdict == _VERDICT_EXCLUDED:
        tail = "企业给出的解释合理且有证据支撑，这一项予以排除。"
    else:
        tail = "现有资料还不足以形成税务疑点，本轮只作观察记录，等资料补充后再判断。"
    # ★ 2026-09-27（用户要求通俗化）："把握程度"改为"判断可信度"并附通俗档位
    #   （很高/较高/中等/偏低/低），让老板一眼知道我们分析有多有把握。
    _band = _conf_band(confidence)
    _conf_txt = f"判断可信度约{int(confidence * 100)}%（{_band}）" if _band else f"判断可信度约{int(confidence * 100)}%"
    parts.append(f"综合以上，本项结论是{verdict}，{_conf_txt}。{tail}")
    return "".join(parts)


def _join(items: List[Any], sep: str) -> str:
    return sep.join(str(i).strip() for i in items if str(i).strip())


def _conf_band(confidence: Any) -> str:
    """把 0~1 的可信度映射为通俗档位（供报告正文展示，便于非财税背景负责人理解）。"""
    try:
        c = float(confidence)
    except (TypeError, ValueError):
        return ""
    if c >= 0.85:
        return "很高"
    if c >= 0.70:
        return "较高"
    if c >= 0.55:
        return "中等"
    if c >= 0.40:
        return "偏低"
    return "低"
