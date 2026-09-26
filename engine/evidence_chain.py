# -*- coding: utf-8 -*-
"""
证据链引擎 —— 回答「要坐实或排除这条红线，需要组织哪些证据」
==============================================================

证据链的定义
--------------------------------------------------
证据链是围绕一条红线组织起来的**证明要素清单**。它回答两个问题：
    ① 要认定（或排除）这条红线，法定上需要哪些证据？
    ② 本轮手上有什么、还缺什么？缺的那一项会导致这条红线查不清吗？

证据角色（税务稽查通行分类）
--------------------------------------------------
    直接证据   能直接证明待证事实（合同、入库单、发票原件）——权数 3
    资金证据   能印证款项真实流转（银行流水、支付凭证）——权数 2
    间接证据   需结合其他证据推认（物流、能耗、考勤）——权数 2
    反证       证明红线不成立的正当理由证据——单独评估，不计入闭合度

闭合度与结论
--------------------------------------------------
    闭合度 = 已取得的（直接+资金+间接）证据权数 / 必需的权数合计
    ≥0.80  证据链基本闭合 → 可作出确定性判断
    0.50~0.80 部分闭合   → 需补证后才能定性
    <0.50  未闭合         → 属检查范围受限，禁止推定，转入置疑清单

严禁：以「证据链未闭合」为由不记录疑点；也严禁以「已触红线」为由跳过证据链。
"""

from typing import Dict, List, Optional
import re

# 证据名称关键词 → 资料类别（**仅用于判断"类别相关"**，不再用于判定"已有"！
# —— 2026-09-25 根因修复：旧版用它把"劳动合同与用工名册"归到「工资表」、
#    把"考勤记录与门禁记录"归到「工资表」，于是只要企业交了工资表，
#    劳动合同、劳务派遣协议、考勤记录统统被判「已有」——全是无据断言。
#    「已有」的判据已改为 `_material_requirements` 的**逐字材料名覆盖**。）
# ⚠ 关键词须**只放该类别独有**的词："名册""人员""用工""考勤""记录"这些词
#   横跨多个类别（用工名册/成员名册/资产名册、考勤记录/门禁记录），
#   放进来会造成类别串味，进而把不相干的证据说成"类别相关"。
_MATERIAL_KEYWORDS: List[List[str]] = [
    ["银行流水", ["流水", "付款", "收款", "资金", "转账", "代付", "支付", "回单"]],
    ["销项发票", ["销项", "开票", "销售发票"]],
    ["进项发票", ["进项", "采购发票"]],
    ["记账凭证", ["凭证", "记账", "会计分录", "账簿"]],
    ["工资表", ["工资", "薪酬"]],
    ["社保明细", ["社保", "参保", "缴费基数"]],
    ["进销存台账", ["入库", "出库", "库存", "盘点", "台账", "存货", "领料", "完工", "发货"]],
    ["合同文件", ["合同", "协议", "订单"]],
    ["科目余额表", ["科目", "余额", "明细账", "往来", "挂账", "辅助账"]],
    ["增值税申报表", ["增值税", "纳税申报"]],
    ["企业所得税申报表", ["所得税", "汇算"]],
    ["个税申报表", ["个税", "扣缴"]],
    ["资产负债表", ["资产", "负债", "报表"]],
    ["利润表", ["利润", "毛利", "费用", "成本", "报表"]],
]

# ── 「已有」的判据：逐字材料名覆盖（2026-09-25 根因修复）────────────────────
# 铁律：**「已有」是对"某个具体材料已提交"的事实断言，不是对"相关类别存在"的推断。**
# 只有证据项名里要求的**每一组具体材料名**都被某份已提供资料的**名称**逐字覆盖，
# 才可判「已有」；仅类别相关 → 「待核」（须人工确认是否含该材料）；无相关 → 「缺失」。
# 反例（修复前）：企业只交了「工资表」，报告却写
#   直接证据「劳动合同与用工名册」现状=已有，basis=本轮已提供「工资表」，可作为本项证据
# ——用工资表去证明劳动合同，且该企业连「合同文件」都列在缺失清单里。
_GENERIC_MATERIAL_TOKENS = {
    # 单独出现时无法确认"这份具体材料已提交"（"发票"分不清进/销项，"合同"分不清采购/销售/劳务）
    "发票", "凭证", "合同", "协议", "记录", "单据", "明细", "清单", "流水",
    "报表", "台账", "资料", "文件", "证明", "账簿", "往来", "相关", "有关",
    "记账凭证", "原始凭证", "相关资料", "相应资料", "书面证明", "文本",
    # 无法区分具体税种/具体品种，不能作为"某份具体材料已提交"的判据
    "纳税申报表", "其他税种申报表", "申报表", "财务报表",
}

# 同一份材料的规范名与别名（**仅限确属同一实物**；不得放宽到"相关/相近"）
_MATERIAL_SYNONYMS = {
    "银行流水": ["银行对账单", "银行明细", "资金流水", "流水单"],
    "工资表": ["工资名册", "工资清单", "工资花名册", "薪酬表"],
    "社保明细": ["社保参保明细", "参保缴费明细", "参保缴费记录", "社保清单", "社保缴费明细"],
    "记账凭证": ["会计凭证"],
    "科目余额表": ["余额表"],
    "增值税申报表": ["增值税纳税申报表"],
}

_AND_SPLIT = re.compile(r"[、，,；;／/\s]+|与|和|及|以及")
_OR_SPLIT = re.compile(r"或|或者")

# ⚠ 切分必须**括号感知**：证据项名里常带括号，如
#   「与待证事实相关且依法获准核验的特定账户、期间和交易资料（含已销户账户）」
#   若在括号内的 `、` 上也切，会切出「期间和交易资料（含已销户账户」这种
#   **括号不闭合**的残片，再拼进 basis 就成了一句话读不通的报告（实测）。
_AND_DELIMS = "、，,；;/"
_AND_WORDS = ("以及", "与", "和", "及")

# 「且」关系：证据项名里同时列出多份材料时，必须**全部**取得才算已有
# （「劳动合同与用工名册」= 两样都要）。「或」关系：任一候选取得即可。


def _split_outside_brackets(text: str, delims: str, words: tuple) -> List[str]:
    """在**括号之外**按分隔符/连接词切分（括号内一律不切）。"""
    from engine.sentencekit import split_sentences
    out: List[str] = []
    for seg in split_sentences(str(text or ""), delims=delims):
        # 再按连接词切（同样只在括号外）
        pieces = [seg]
        for w in words:
            nxt: List[str] = []
            for p in pieces:
                nxt.extend(split_sentences(p, delims=w) if w in p else [p])
            pieces = nxt
        out.extend(pieces)
    return out


def _material_forms(name: str) -> List[str]:
    """一份资料的规范名与其全部别名（含由别名反查规范名、含已声明的等价类别）。

    ⚠ 与旧版的区别：旧版是"证据项名里**出现某个关键词**就归到某类别"（名册→工资表），
      本函数只做**名称级**的等价展开，等价关系来自人工审过的
      `_MATERIAL_SYNONYMS` 与 `_EQUIVALENT_CATEGORIES` 两张表，不放任关键词碰撞。
    """
    forms = [name]
    forms.extend(_MATERIAL_SYNONYMS.get(name, []))
    for canon, alts in _MATERIAL_SYNONYMS.items():
        if name in alts:
            forms.append(canon)
    forms.extend(_EQUIVALENT_CATEGORIES.get(name, []))
    for canon, alts in _EQUIVALENT_CATEGORIES.items():
        if name in alts:
            forms.append(canon)
    # 去重保序
    out: List[str] = []
    for f in forms:
        if f and f not in out:
            out.append(f)
    return out


def _covered_by(token: str, available: List[str]) -> Optional[Dict]:
    """`token` 是否被某项已提供资料**逐字覆盖**；是则返回命中详情，否则 None。

    返回 `{"need", "material", "form", "exact"}`：
      · `need`     —— 证据项里要求的具体材料名（token）
      · `material` —— 命中的**已提供资料名**
      · `form`     —— 实际逐字命中的那个称谓（可能是资料名，也可能是它已声明的别名/等价名）
      · `exact`    —— 该称谓与 `need` 是否**逐字一致**（否则属"同一材料的不同叫法"）

    ⚠ 记录 `form` 是为了让"已有"这个断言可追溯：报告只允许说"已提供「X」，
      你的证据项写的是「Y」，二者逐字一致 / 属同一材料的不同叫法" ——
      每一句都能回指到一个具体的字词，而不是一个模糊的"类别相关"。
    覆盖 = 双向包含（`form` 含 `token`，或 `token` 含 `form`），且两侧都必须是
    **具体材料名**（长度≥3 且非通用词）——避免「发票」命中「进项发票」这种串味。
    """
    if len(token) < 3 or token in _GENERIC_MATERIAL_TOKENS:
        return None
    for a in available:
        for form in _material_forms(str(a or "")):
            if len(form) < 3 or form in _GENERIC_MATERIAL_TOKENS:
                continue
            if form == token or form in token or token in form:
                return {"need": token, "material": str(a), "form": form,
                        "exact": form == token}
    return None


def _material_requirements(evidence_name: str) -> List[List[str]]:
    """把证据项名解析为「且」组，每组内是「或」候选的具体材料名。

    `劳动合同与用工名册` → [['劳动合同'], ['用工名册']]  （两样都要）
    `付款银行流水或第三方支付凭证` → [['付款银行流水', '第三方支付凭证']]  （两者之一即可）

    ⚠ 切分**只在括号之外**进行（见 `_split_outside_brackets` 的说明）。
    """
    groups: List[List[str]] = []
    for seg in _split_outside_brackets(evidence_name, _AND_DELIMS, _AND_WORDS):
        alts: List[str] = []
        for alt in _split_outside_brackets(seg, "", ("或", "或者")):
            # ⚠ 只剥空白与冒号，**不得剥括号**：`strip("（）()")` 会把
            #   「交易资料（含已销户账户）」尾部的 `）` 剥掉 → 括号不闭合（实测踩过）
            alt = alt.strip(" \t　：:")
            if len(alt) >= 3 and alt not in _GENERIC_MATERIAL_TOKENS:
                alts.append(alt)
        if alts:
            groups.append(alts)
    return groups


def _related_categories(evidence_name: str, purpose: str,
                        available: List[str]) -> List[str]:
    """与本证据项**类别相关**的已提供资料（只用于「待核」说明，不作"已有"依据）。

    ★ 只看**证据项名称**，不看证明目的 —— 目的文字里的"参保""用工"等词会把
      类别带偏（实测：「劳务派遣协议及派遣单位资质」的目的一句话含"参保"，
      就被说成"已提供社保明细"，属实无必要且易误导）。
    """
    text = str(evidence_name or "")
    hits: List[str] = []
    for category, keywords in _MATERIAL_KEYWORDS:
        if not any(kw in text for kw in keywords):
            continue
        for cand in [category] + list(_EQUIVALENT_CATEGORIES.get(category, [])):
            if cand in available and cand not in hits:
                hits.append(cand)
    return hits


def _match_material(evidence_name: str, purpose: str,
                    available: List[str]) -> Dict:
    """判定证据项现状 → `{status, basis, matched, related}`（**全系统唯一实现**）。

    三态（判据见 `_material_requirements` 注释）：
      · `已有`  —— 每一组具体材料名都被已提供资料**逐字覆盖**；`matched` 给出命中的资料名
      · `待核`  —— 未逐字覆盖，但清单里有**类别相关**资料；须人工确认该资料是否含本项材料
      · `缺失`  —— 无任何相关命中

    **禁止**把「待核」当作「已有」使用（闭合度、可定性判断一律按未取得处理）。
    """
    groups = _material_requirements(evidence_name)
    matched: List[str] = []
    matched_detail: List[Dict] = []
    unmet: List[str] = []
    for alts in groups:
        hit = next((h for h in (_covered_by(t, available) for t in alts) if h), None)
        if hit:
            if hit["material"] not in matched:
                matched.append(hit["material"])
            matched_detail.append(hit)
        else:
            unmet.append(alts[0])
    if groups and not unmet and matched:
        _parts = []
        for h in matched_detail:
            if h["exact"]:
                # 命中的称谓与本项要求逐字一致；若该称谓就是资料名，说法更简
                if h["form"] == h["material"]:
                    _parts.append("「%s」（与本项要求逐字一致）" % h["material"])
                else:
                    _parts.append("「%s」（其称谓「%s」与本项要求逐字一致）"
                                  % (h["material"], h["form"]))
            else:
                _parts.append("「%s」（本项写作「%s」，属同一材料的不同叫法）"
                              % (h["material"], h["need"]))
        return {
            "status": "已有",
            "matched": matched,
            "matched_detail": matched_detail,
            "unmet": [],
            "related": [],
            "basis": "本轮已提供%s，可作为本项证据" % "、".join(_parts),
        }

    related = _related_categories(evidence_name, purpose, available)
    # ⚠ 用「、」而非「」「」连接：报告输出前的净化层会剥掉「」，若靠它分隔多个材料名，
    #   剥掉后会连读成"应付账款明细账账龄分析"这类歧义串（实测）。故依据文字必须在
    #   **没有「」的情况下也读得通**。
    _unmet_disp = "、".join(unmet)
    _need = _unmet_disp or evidence_name or "该项"
    if related:
        if matched:
            basis = ("本项要求%s；其中%s本轮已提供，但%s未在已提供资料中逐字见到，"
                     "须人工确认已提供资料中是否包含该内容" % (
                         "、".join(g[0] for g in groups), "、".join(matched), _unmet_disp))
        else:
            basis = ("本项要求%s，未在已提供资料中逐字见到；清单中有类别相关的%s，"
                     "但二者不是同一份材料，须人工确认已提供资料中是否包含本项所需内容"
                     % (_need, "、".join(related)))
        return {"status": "待核", "matched": matched, "matched_detail": matched_detail,
                "unmet": unmet, "related": related, "basis": basis}
    return {
        "status": "缺失",
        "matched": matched,
        "matched_detail": matched_detail,
        "unmet": unmet,
        "related": [],
        "basis": "本轮未提供本项所需材料（%s），无法组织本项证据"
                 % ("、".join(unmet) or evidence_name or "该项"),
    }

# 等价资料类别：不同模块对同一批资料的叫法不同，须视为同一类，
# 否则「财务报表」已提供却被判「资产负债表缺失」，虚增证据缺口。
_EQUIVALENT_CATEGORIES = {
    "财务报表": ["资产负债表", "利润表"],
    "资产负债表": ["财务报表"],
    "利润表": ["财务报表"],
    "增值税申报表": ["纳税申报表", "其他税种申报表"],
    "企业所得税申报表": ["纳税申报表", "其他税种申报表"],
    "个税申报表": ["纳税申报表", "其他税种申报表"],
    "记账凭证": ["序时账", "明细账"],
    "科目余额表": ["序时账", "明细账"],
}

_ROLE_WEIGHT = {"直接证据": 3, "资金证据": 2, "间接证据": 2, "反证": 1}

# 判定「证据已有」的最低门槛：直接证据必须全部取得，间接/资金证据按比例
_DIRECT_ROLES = {"直接证据"}

# 旧版 `_match_material`（"关键词 → 15 类资料 → 类别在清单里就算已有"）已于
# 2026-09-25 删除：它用「工资表」证明「劳动合同」、用「销项发票」证明「设备采购合同」，
# 属无据断言。现由上方 `_match_material`（逐字材料名覆盖）唯一承担。


def build_evidence_chain(finding: Dict, redline: Dict,
                         available_materials: Optional[List[str]] = None,
                         engine_data: Optional[Dict] = None) -> Dict:
    """
    构建单条疑点的证据链。

    返回：
        {
          "elements": [ {role, name, purpose, status, basis, matched, related, weight} ],
          "available_count",   # 状态=已有（逐字命中具体材料）
          "verify_count",      # 状态=待核（类别相关，须人工确认）
          "missing_count",     # 状态!=已有（含待核与缺失）
          "closure": 0~1,
          "verdict": "支撑材料已基本齐全/尚不齐全/严重不足",
          "missing_materials": [...],   # 确未提供的资料类别
          "verify_materials": [...],    # 须人工确认是否已含的资料类别
          "remedy": "...",
          "rebuttal_status": "..."
        }

    status 三态语义（2026-09-25 起，报告每个字都须有据）：
        `已有` —— 已提供资料的**名称**逐字覆盖本项要求的具体材料名（唯一可计为"已取得"）
        `待核` —— 未逐字覆盖，但清单里有类别相关资料 → 须人工确认，**不得计为已取得**
        `缺失` —— 无任何相关
    """
    available = [str(a) for a in (available_materials or []) if a]
    engine_data = engine_data or {}
    template = list(redline.get("evidence_chain") or [])
    elements: List[Dict] = []

    # 企业已提交的反证线索（用于判断正当理由是否有资料支撑）
    _submitted = []
    for key in ("opposing_evidence", "supporting_evidence", "reasonable_explanations"):
        for v in (finding.get(key) or []):
            _submitted.append(str(v if not isinstance(v, dict)
                                  else (v.get("text") or v.get("name") or v)))

    for item in template:
        role = str(item.get("role") or "间接证据")
        name = str(item.get("name") or "")
        purpose = str(item.get("purpose") or "")
        if role == "反证":
            # 反证（正当理由）是否成立，只认企业是否实际提交，
            # 严禁按资料类别关键词猜测——否则「银行承兑汇票」里的「转账」
            # 二字会被当成反证已提供，把真实疑点错误排除。
            # 2026-09-25：判据由 `name[:6]` 固定长度前缀改为**具体材料名命中**
            # （原写法对「退休返聘协议、实习协议、非全日制用工协议」只取前 6 字，
            #  且会把任意含该 6 字的文本当作已提交）。
            _tokens = [t for alts in _material_requirements(name) for t in alts]
            _hit = next((h for h in (_covered_by(t, _submitted) for t in _tokens) if h), None)
            submitted = bool(_hit)
            elements.append({
                "role": role, "name": name, "purpose": purpose,
                "status": "已提交" if submitted else "待企业提交",
                "basis": (("企业已提交与本项对应的书面材料「%s」，须纳入论证核验" % _hit["form"])
                          if submitted else "企业尚未提交该正当理由的书面证明"),
                "matched": [_hit["material"]] if submitted else [],
                "matched_detail": [_hit] if submitted else [],
                "related": [],
                "weight": _ROLE_WEIGHT.get(role, 1),
            })
            continue
        m = _match_material(name, purpose, available)
        status, basis = m["status"], m["basis"]
        if status == "缺失" and (finding.get("supporting_evidence") or []):
            # 发现自身带支持性证据记录 → 至多为"待核"，**绝不可**升为"已有"
            # （发现声明的是线索，不是已提交的材料）
            supporting = finding.get("supporting_evidence") or []
            if any(name and (name[:4] in str(s) or role in str(s)) for s in supporting):
                status = "待核"
                basis = "本轮资料中含与本项相关的线索，但未取得该证据材料本身，须补充"
        elements.append({
            "role": role, "name": name, "purpose": purpose,
            "status": status, "basis": basis,
            "matched": m["matched"], "matched_detail": m.get("matched_detail") or [],
            "related": m["related"],
            "weight": _ROLE_WEIGHT.get(role, 1),
        })

    # 闭合度：只算直接/资金/间接证据（反证单独评估）
    # ★ 2026-09-25：只有「已有」（逐字命中具体材料）才计入已取得。
    #   「待核」按 0 计 —— 否则会出现"材料其实没拿到、闭合度却达标、疑点被错误定性为已确认"。
    need = sum(e["weight"] for e in elements if e["role"] != "反证")
    got = sum(e["weight"] for e in elements
              if e["role"] != "反证" and e["status"] == "已有")
    closure = round(min(1.0, got / need), 2) if need else 0.0

    # 直接证据未逐字取得（含待核）→ 不得作出确定性判断
    direct_missing = [e["name"] for e in elements
                      if e["role"] == "直接证据" and e["status"] != "已有"]

    # 2026-09-13：verdict 文案不得出现「证据链」等内部术语，改为资料完备程度的
    # 自然表述（本字段直接进入报告正文，见 enterprise_report._build_redline_problems 的 p3 与 p4）。
    if closure >= 0.80 and not direct_missing:
        verdict = "支撑材料已基本齐全，可以作出确定性判断"
    elif closure >= 0.50:
        verdict = "支撑材料尚不齐全，需补充材料后才能定性"
    else:
        verdict = "支撑材料严重不足，核心材料缺失"

    # 待核项不并入"缺失"：报告须分别说清"确未提供"与"须确认是否已含"。
    # ★ 两条硬约束：①只看**证据项名称**（证明目的里的字会串味）；
    #   ②**已提供的类别绝不进 missing**（否则会出现"社保明细缺失"而清单里明明有社保明细）。
    missing_materials: List[str] = []
    verify_materials: List[str] = []
    for e in elements:
        if e["role"] == "反证" or e["status"] == "已有":
            continue
        bucket = verify_materials if e["status"] == "待核" else missing_materials
        text = e["name"]
        for category, keywords in _MATERIAL_KEYWORDS:
            if not any(kw in text for kw in keywords):
                continue
            forms = [category] + list(_EQUIVALENT_CATEGORIES.get(category, []))
            if any(f in available for f in forms):
                continue  # 该类别本轮已提供 → 不是缺失
            if category not in bucket:
                bucket.append(category)
            break

    # 反证状态
    rebuttals = [e for e in elements if e["role"] == "反证"]
    if not rebuttals:
        rebuttal_status = "本条红线无适用反证"
    elif any(e["status"] == "已提交" for e in rebuttals):
        rebuttal_status = "企业已提交部分正当理由，须逐项核验后认定"
    else:
        rebuttal_status = "企业尚未提交正当理由的书面证明，现有资料不构成排除依据"

    return {
        "elements": elements,
        "available_count": sum(1 for e in elements if e["status"] == "已有"),
        "verify_count": sum(1 for e in elements if e["status"] == "待核"),
        "missing_count": sum(1 for e in elements if e["status"] != "已有"),
        "closure": closure,
        "verdict": verdict,
        "direct_missing": direct_missing,
        "missing_materials": missing_materials,
        "verify_materials": verify_materials,
        "remedy": redline.get("remedy", ""),
        "rebuttal_status": rebuttal_status,
        "required_materials": list(redline.get("required_materials") or []),
    }


def evidence_text(chain: Dict) -> str:
    """把材料清单压成一段可直读的话。

    ★ 2026-09-25：「已有」与「待核」必须分开说 —— 旧版把两者混为
      「现已有证据」，于是"只有工资表"被写成"劳动合同等已在案"。
    """
    els = chain.get("elements") or []
    if not els:
        return ""
    have = [f"{e['name']}" for e in els if e["status"] == "已有"]
    verify = [f"{e['name']}" for e in els if e["status"] == "待核"]
    lack = [f"{e['name']}" for e in els if e["status"] == "缺失"]
    seg = []
    if have:
        seg.append("已在案证据（名称逐字对应）：" + "、".join(have[:6]))
    if verify:
        seg.append("须确认是否已含：" + "、".join(verify[:6]))
    if lack:
        seg.append("确未提供：" + "、".join(lack[:6]))
    seg.append(f"资料齐全程度{int(chain.get('closure', 0) * 100)}%，{chain.get('verdict', '')}")
    return "；".join(seg) + "。"
