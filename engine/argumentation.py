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

from typing import Any, Dict, List, Optional

# 四个裁决层级：「触红」与「定性」是两个层次，不可混为一谈
#   —— 符合红线的构成要件即已触红（客观判断，与行业无关）；
#   —— 证据链是否闭合只决定能否「定性」，不决定「是否触红」。
_VERDICT_CONFIRMED = "红线成立（证据闭合，可定性）"      # 触红 + 证据闭合 → 可定性
_VERDICT_HIT_PENDING = "红线成立（待补证后定性）"        # 触红 + 证据未闭合 → 置疑清单
_VERDICT_EXCLUDED = "红线不成立（有合理解释）"           # 反证成立 → 排除
_VERDICT_WEAK = "线索不足，未形成税务疑点"               # 无线索支撑 → 仅作观察

# 报告用的结论分级
GRADE_CONFIRMED = "已核定"
GRADE_PENDING = "待核"
GRADE_EXCLUDED = "已排除"


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
    claim = (f"本企业触碰红线 {redline.get('id','')}「{redline.get('name','')}」，{_suspect_txt}")
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

    # 置信度模型（不靠拍脑袋，逐项可解释）
    confidence = 0.50
    confidence += 0.25 * closure
    confidence += 0.10 * data_completeness
    if "高风险" in level:
        confidence += 0.08
    elif "低风险" in level:
        confidence -= 0.05
    confidence -= 0.20 * rebuttal_ratio
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

    # 反证成立条件检验
    rebuttal_tests = []
    for r in rebuttals[:5]:
        rebuttal_tests.append({
            "rebuttal": r,
            "needs": "须提供与该理由对应的书面协议、原始单据与履行记录",
            "verifiable_now": "本轮资料能够验证" if rebuttal_supported else "本轮资料无法验证，须补充资料",
        })

    reasoning = _compose_reasoning(redline, claim, clue, evidence, rebuttals, verdict, confidence)

    next_actions: List[str] = []
    for m in (evidence.get("missing_materials") or [])[:5]:
        next_actions.append(f"补充提供「{m}」")
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

    # 触红后置信度下限 0.60：既然符合构成要件，就不能因证据未齐而说成「没把握」
    if redline_hit:
        confidence = round(max(0.60, min(0.95, confidence)), 2)

    return {
        "claim": claim,
        "redline_id": redline.get("id", ""),
        "redline_name": redline.get("name", ""),
        "suspect": redline.get("suspect", ""),
        "legal_basis": list(redline.get("legal_basis") or []),
        "constituents": list(redline.get("constituents") or []),
        "grounds": grounds,
        "rebuttals": rebuttals,
        "rebuttal_tests": rebuttal_tests,
        "verdict": verdict,
        "conclusion_grade": grade,
        "redline_hit": redline_hit,
        "confidence": confidence,
        "closure": closure,
        "reasoning": reasoning,
        "next_actions": next_actions[:8],
        "remedy": evidence.get("remedy", ""),
    }


def _compose_reasoning(redline: Dict, claim: str, clue: Dict, evidence: Dict,
                       rebuttals: List[str], verdict: str, confidence: float) -> str:
    """把论证过程写成一段大白话（稽查员口吻）"""
    parts = []
    parts.append(f"【主张】{claim}。")
    parts.append(
        f"【依据】本条红线的构成要件是：{_join(redline.get('constituents') or [], '；')}。"
    )
    if clue.get("terminal_signal"):
        parts.append(f"【线索】{clue.get('terminal_signal')}。")
    chain_desc = "→".join(
        f"{n.get('source','?').split('、')[0]}" for n in (clue.get("nodes") or [])
    )
    if chain_desc:
        parts.append(f"【线索链】{chain_desc}。")
    parts.append(
        f"【证据】{evidence.get('verdict','')}，闭合度{int(float(evidence.get('closure',0))*100)}%"
        f"（已有{evidence.get('available_count',0)}项、缺失{evidence.get('missing_count',0)}项）；"
        f"{evidence.get('rebuttal_status','')}。"
    )
    if rebuttals:
        parts.append(
            f"【反证】企业可能主张：{_join(rebuttals[:3], '；')}。"
            "上述理由成立与否，须以书面协议与原始单据为准，不以口头说明认定。"
        )
    if verdict == _VERDICT_CONFIRMED:
        tail = "证据链已闭合，本疑点可直接定性；若企业有异议，须更正所报资料本身或提出相反证据。"
    elif verdict == _VERDICT_HIT_PENDING:
        tail = ("已触碰税务红线，但证据链尚未闭合，暂不定性——转置疑清单，"
                "由企业补充上述证据后重新检查；在补证前既不认定违法，也不予排除。")
    elif verdict == _VERDICT_EXCLUDED:
        tail = "已有合理解释并有证据支撑，本条红线予以排除。"
    else:
        tail = "现有资料不足以形成税务疑点，仅作观察记录，待资料补充后重新判定。"
    parts.append(f"【裁决】{verdict}，置信度{int(confidence * 100)}%。{tail}")
    return "".join(parts)


def _join(items: List[Any], sep: str) -> str:
    return sep.join(str(i).strip() for i in items if str(i).strip())
