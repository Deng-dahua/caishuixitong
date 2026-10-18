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

严禁：以「证据链未闭合」为由不记录疑点；也严禁以「已触碰红线线」为由跳过证据链。
"""

from typing import Any, Dict, List, Optional, Tuple
import re

# 证据名称关键词 → 资料类别（**仅用于判断"类别相关"**，不再用于判定"已有"！
# —— 2026-09-25 根因修复：旧版用它把"劳动合同与用工名册"归到「工资表」、
#    把"考勤记录与门禁记录"归到「工资表」，于是只要企业交了工资表，
#    劳动合同、劳务派遣协议、考勤记录统统被判「已有」——全是无据断言。
#    「已有」的判据已改为 `_material_requirements` 的**逐字材料名覆盖**。）
# ⚠ 关键词须**只放该类别独有**的词："名册""人员""用工""考勤""记录"这些词
#   横跨多个类别（用工名册/成员名册/资产名册、考勤记录/门禁记录），
#   放进来会造成类别串味，进而把不相干的证据说成"类别相关"。
# ★★ 2026-10-03（用户："彻底解决多种叫法的问题"）：类别表与别名表**不再在本模块维护**，
#   统一由 `engine/material_names.py` 提供（唯一权威）。本模块只做引用/转发。
#   背景：此前"资料名"散落在 8 处（required_materials / evidence_chain.name /
#   constituent_sources / _SUPP_ENTRIES / _MATERIAL_KEYWORDS / _MATERIAL_SYNONYMS /
#   _EQUIVALENT_CATEGORIES / _MATERIAL_SUPERCLASS），同一份材料两套名字两套判定 ⇒
#   要件表说"银行流水｜已有"、证据表说"完整资金链条流水｜待核实"，同页自相矛盾。
from engine.material_names import (
    CATEGORY_KEYWORDS as _MATERIAL_KEYWORDS,
    CATEGORY_ALIASES as _MATERIAL_SYNONYMS,
    category_strict as _category_strict,
    canonical as _canonical_material,
    strict_categories_of as _strict_categories_of,
    strict_categories_all as _strict_categories_all,
    strict_category_groups as _strict_category_groups,
)

_GENERIC_MATERIAL_TOKENS = {
    # 单独出现时无法确认"这份具体材料已提交"（"发票"分不清进/销项，"合同"分不清采购/销售/劳务）
    "发票", "凭证", "合同", "协议", "记录", "单据", "明细", "清单", "流水",
    "报表", "台账", "资料", "文件", "证明", "账簿", "往来", "相关", "有关",
    "记账凭证", "原始凭证", "相关资料", "相应资料", "书面证明", "文本",
    # 无法区分具体税种/具体品种，不能作为"某份具体材料已提交"的判据
    "纳税申报表", "其他税种申报表", "申报表", "财务报表",
}

# ★ 2026-10-03：原此处自建的 `_MATERIAL_SYNONYMS` 字面量表已删除 ——
#   它与 `material_names.CATEGORY_ALIASES` 是同一概念的两份实现（多头维护），
#   且局部定义会**覆盖**上方 import 的转发，导致新登记的别名在旧匹配路径里失效。
#   现全系统只保留唯一权威 `engine/material_names.CATEGORY_ALIASES`。

# ★★ 2026-10-06：此处原有的 `_AND_SPLIT` / `_OR_SPLIT` 两张正则表**已删除** ——
#   ① 它们是**死代码**（全文件无任何引用，实际切分由下方括号感知的
#      `_AND_DELIMS` / `_AND_WORDS` 承担）；
#   ② 作为"第二份并列分隔符表"存在本身就是隐患：它与
#      `industry_resolver.MATERIAL_SEG_SEP`、`material_names._AND_SPLIT`
#      内容还**各不相同**，后人误引即复活多头维护
#      （曾因此出现"同一份要件 3 种判法"，见 `industry_resolver` 顶部 ★★ 说明）。
#   唯一权威：`engine.industry_resolver.MATERIAL_SEG_SEP`（含「或」用 `MATERIAL_ALT_SEP`）。

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


# ★★ 2026-10-04（疑点1 四维自检 D7 另一半）：**实质限定语**权威表。
#   证据项名形如「限定语 + 资料类别名」时，限定语分两类：
#     · 方向/用途类（付款/收款/收付/销项/进项/开出/取得…）——任何该类资料都具备，
#       不构成额外内容要求 ⇒ 已提供「银行流水」即满足「付款银行流水」（旧行为正确，保留）。
#     · 实质要求类（下表）——要求资料中含**特定性质的记录**：
#       有「银行流水」≠有「退款记录」⇒ **不得**判「已有」，须判「待核」。
_SUBSTANTIVE_QUALIFIERS: tuple = (
    "退款", "退货", "退运", "退回", "折让", "拒收", "抵销", "抵账", "核销",
    "赔款", "赔偿", "违约金", "罚没", "滞纳", "冲减", "冲回",
)


def _substantive_qualifier(token: str, form: str) -> str:
    """`token` 比 `form` 多出的限定部分里，是否含**实质要求**类限定语；返回命中的那个。"""
    if not token or not form or form == token or form not in token:
        return ""
    _extra = str(token).replace(str(form), "")
    for _q in _SUBSTANTIVE_QUALIFIERS:
        if _q in _extra:
            return _q
    return ""


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
            # ★★ 2026-10-04（疑点1 D7 另一半）：`form in token`（证据项比已提供资料**更具体**）
            #   不再一律算覆盖 —— 先看多出来的限定语是方向/用途还是实质要求。
            # ★ 2026-10-04（选项 B）：**同族不同物不构成覆盖** ——
            #   社保与公积金同族（归类相同、便于剔除与计数），但不是同一份材料，
            #   不得判「已有」。唯一权威 `material_names.sibling_conflict`。
            try:
                from engine.material_names import sibling_conflict as _sib
                if _sib(token, form):
                    continue
            except Exception:  # noqa: BLE001
                pass
            if form == token or token in form:
                return {"need": token, "material": str(a), "form": form,
                        "exact": form == token}
            if form in token and not _substantive_qualifier(token, form):
                return {"need": token, "material": str(a), "form": form,
                        "exact": False}
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


# ★★ 2026-10-04（疑点2 D9，选项 1 披露式）：**范围/完整性**限定语 —— 只用于**披露**，
#   **不参与**「已有／待核」判定（清别名会破不变量：要件数据源恒 not_checked、既有闸门
#   要求此类细名判已有）。职责只有一件：本项名在**已命中材料名之外**还带这些限定语时，
#   说明有这类资料 ≠ 覆盖了这个范围，必须在依据里**具体披露**并标记 scope_unverified。
_SCOPE_QUALIFIERS: tuple = (
    "完整", "全量", "全部", "逐笔", "全套", "链条", "账户", "已销户", "明细",
)


def _scope_gap(evidence_name: str, matched: List[str]) -> str:
    """本项名在已命中材料名之外是否带**范围/完整性**限定语；有则返回该限定语，否则空串。

    唯一权威：`_SCOPE_QUALIFIERS`。**只用于披露，不改变判定**。
    """
    _name = str(evidence_name or "")
    _rest = _name
    for _m in (matched or []):
        _m = str(_m or "")
        if _m and _m in _rest:
            _rest = _rest.replace(_m, "")
    for _q in _SCOPE_QUALIFIERS:
        if _q in _rest:
            return _q
    return ""


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
                    available: List[str], role: str = "") -> Dict:
    """判定证据项现状 → `{status, basis, matched, related}`（**全系统唯一实现**）。

    三态（判据见 `_material_requirements` 注释）：
      · `已有`  —— 每一组具体材料名都被已提供资料**逐字覆盖**；`matched` 给出命中的资料名
      · `待核`  —— 未逐字覆盖，但清单里有**类别相关**资料；须人工确认该资料是否含本项材料
      · `缺失`  —— 无任何相关命中

    **禁止**把「待核」当作「已有」使用（闭合度、可定性判断一律按未取得处理）。
    """
    # ★★ 2026-10-03：**两级判定** —— 先按"资料**类别**"判有没有，再谈具体材料与范围。
    #   为什么要这一步：系统只有 14 个"材料类别"（与"企业已提供清单"同源），
    #   而红线要求常是更细的名字（"完整资金链条流水"）。两个层级混在一起做**逐字比较**，
    #   细名永远匹配不上类别名 ⇒ 系统性判「待核/缺失」，并派生出"要件表说已有、
    #   证据表说待核实"的同页矛盾（用户反复报的就是这个）。
    #   口径：类别命中 ⇒ 「已有」（"这类资料已提供"是可证事实），并把**范围差异**写进说明；
    #        判不出类别（反证材料、非同类实物）⇒ 保持下方严格逐字逻辑，**不兜底**。
    if role != "反证":
        # ★ 必须"全部段落都能归类"才允许走类别层（未登记的段落会让判定失效，不得静默丢弃）
        #   ★★ 2026-10-03：改走 `strict_category_groups` —— 支持「或」语义
        #   （要件①「工资表**或**个税申报表」＝ 其一即可；旧实现按「且」判，
        #     只上传工资表的企业该要件永远"未单独核对"）。与 `_material_requirements`
        #     的契约（"A或B → 两者之一即可"）对齐。
        _groups = _strict_category_groups(evidence_name)
        if _groups:
            # ★ 两处收紧（由既有严格性测试逼出，测试是对的）：
            #   ① 已提供侧**只用严格口径**：`category_strict`（登记别名/类别名），
            #      **不得**用关键词兜底 —— 否则「渠道订单」会因为名字里含"订单"
            #      被当成「合同文件」类别，从而给"采购合同"发一张假的"已有"
            #      （实测 test_no_fuzzy_match 正是锁这条）。
            #   ② **必须完全覆盖**：每个「且」组内**任一「或」候选**的全部类别都在
            #      已提供类别中，才算该组满足；未覆盖 ⇒ 不得整项判已有
            #      （实测 test_partial_match_is_pending_not_available 锁这条）。
            _have_cats = set()
            _have = []
            for _a in available:
                _c = _category_strict(_a)
                if _c:
                    _have_cats.add(_c)
                    _have.append(_a)
            # ★ 2026-10-04（选项 B）：类别命中但**同族不同物** ⇒ 不得判「已有」。
            _sib_hit = False
            try:
                from engine.material_names import sibling_conflict as _sib2
                for _a2 in _have:
                    if _sib2(evidence_name, _a2):
                        _sib_hit = True
                        break
            except Exception:  # noqa: BLE001
                _sib_hit = False
            if _sib_hit:
                try:
                    from engine.material_names import sibling_note as _sibn
                    _sib_txt = _sibn(evidence_name, "、".join(_have[:2])) or "同族但不是同一份材料"
                except Exception:  # noqa: BLE001
                    _sib_txt = "同族但不是同一份材料"
                return {"status": "待核", "matched": _have, "matched_detail": [],
                        "unmet": [evidence_name], "related": [],
                        "basis": ("本项要求「%s」；本轮已提供的是「%s」，二者%s，"
                                  "须补充该项本身的具体材料后方可核对。"
                                  % (evidence_name, "、".join(_have[:3]), _sib_txt)),
                        "sibling_conflict": True}
            if all(any(set(_alt) <= _have_cats for _alt in _grp) for _grp in _groups):
                _needed = sorted({c for _grp in _groups for _alt in _grp for c in _alt})
                _have = [a for a in _have if _category_strict(a) in set(_needed)]
                _cat_txt = "、".join(_needed)
                # ★ 2026-10-04（疑点2 D9，选项 1 披露式）：范围差异必须具体披露且可校验。
                _gap = _scope_gap(evidence_name, _needed)
                _basis = ("本项要求「%s」（资料类别：%s）；企业已提供同类资料「%s」，"
                          "该类别已具备。" % (evidence_name, _cat_txt, "、".join(_have[:4])))
                if _gap:
                    # ⚠ 本段会渲染进报告「依据」列 ⇒ 不得带 markdown
                    _basis += ("但本项名另含「范围/完整性」限定「%s」，属同类不同范围——"
                               "已提供资料是否覆盖该范围（如是否含全部账户、是否逐笔到明细）"
                               "须人工确认，确认前不得视为已满足本项范围要求。" % _gap)
                else:
                    _basis += "本项名中无额外范围限定，视为已具备。"
                return {"status": "已有", "matched": _have,
                        "matched_detail": [{"material": a, "need": evidence_name,
                                            "form": a, "exact": False} for a in _have[:4]],
                        "unmet": [], "related": [], "basis": _basis,
                        "scope_unverified": _gap or None,
                        "by_category": _needed}
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
        _gap2 = _scope_gap(evidence_name, matched)
        _basis2 = "本轮已提供%s，可作为本项证据" % "、".join(_parts)
        if _gap2:
            # ⚠ 同上：进报告「依据」列，禁 markdown
            _basis2 += ("；但本项名另含「范围/完整性」限定「%s」，属同类不同范围——"
                        "已提供资料是否覆盖该范围须人工确认。" % _gap2)
        return {
            "status": "已有",
            "matched": matched,
            "matched_detail": matched_detail,
            "unmet": [],
            "related": [],
            "basis": _basis2,
            "scope_unverified": _gap2 or None,
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


def _atoms_count(elements, not_required_docs=None):
    """把一组证据元素按**材料名原子**计数（拆复合名 + 去重），并先过业态剔除。

    ★ 与 §三（`enterprise_report`）**同一算法、同一业态剔除权威** —— 两边必须同源，
      否则同一页会给出两个数（疑点5 D11 事故）。
    """
    _na = not_required_docs
    if _na is None:
        _na = set()
    _seps = ("、", "，", ",", "；", ";", "／", "/", "以及", "或者", "与", "和", "及", "或")
    _out = []
    for _e in (elements or []):
        _n = _e.get("name") if isinstance(_e, dict) else _e
        _n = str(_n or "").strip()
        if not _n:
            continue
        if _na:
            _drop = False
            for _m in _na:
                if _m and _m in _n:
                    _drop = True
                    break
            if _drop:
                continue
        for _s in _seps:
            _n = _n.replace(_s, "\x00")
        for _y in _n.split("\x00"):
            _y = _y.strip()
            if _y and _y not in _out:
                _out.append(_y)
    return _out


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

    # ★★ 2026-10-06：**业态不适用资料在此处（算 status 之前）就剔除**。
    #   唯一权威 `industry_resolver.exclude_not_required_material`（段级；"" = 整项不适用）。
    #
    #   病根（已复现，非特例）：旧实现在**函数末尾**用**字符级 `str.replace`** 剔除，
    #   把不适用资料名当**子串删掉** ⇒ ① 切出悬空连词残词
    #   （"采购合同与入库验收单"→"采购合同**与**"、"物流单据与承运记录"→"**与**承运记录" 或 ""，
    #    **取决于 set 迭代序 ⇒ 同一输入两次运行产出不同**）；② 它发生在
    #   `status`/`basis`/`direct_missing` **算完之后** ⇒ 只有名字被改，
    #   **依据、直接证据清单、补救要求仍是原始要求** —— 服务型企业照样被要求补物流单据。
    #   ⇒ 现在：先剔名 → 用剔后的名去判 status / 算 basis / 组 direct_missing，
    #     整项都不适用 ⇒ **该证据项不进 elements**（不可能要求的材料不该出现在证据角色表），
    #     并记入 `industry_excluded` 供报告如实披露（**不静默丢弃**）。
    _na_docs: set = set()
    try:
        from engine.industry_resolver import not_required_materials as _nrm
        _na_docs = set(_nrm((engine_data or {}).get("industry"))[0] or ())
    except Exception:  # noqa: BLE001
        _na_docs = set()
    _excluded: List[Dict] = []
    try:
        from engine.industry_resolver import exclude_not_required_material as _xna
    except Exception:  # noqa: BLE001
        _xna = None

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
        if role != "反证" and _xna is not None:
            # ★ 反证不剔：它是正当理由（不是企业要交的材料），剔空会把反证整条吃掉。
            _nm_eff = _xna(name, _na_docs)
            if not _nm_eff:
                _excluded.append({"role": role, "name": name,
                                  "reason": "本业态天然不适用（不构成资料缺失，也不作为证据要求）"})
                continue
            name = _nm_eff
        if role == "反证":
            # ★★ 2026-10-18 重写（META-SYSTEM-COMPLETENESS-AUDIT / GAP-03+GAP-04）
            #
            # 旧判据：把 finding 自带 `opposing_evidence / supporting_evidence /
            # reasonable_explanations` 的**文本**与材料名做包含匹配 ⇒ 只要企业在
            # 描述里**写下材料名**就算"反证已提交"。实测后果：
            #   ① 同一 finding 只改这段文本（材料名有/无），verdict 就从
            #      「疑似触碰红线 conf=0.6」翻成「未触碰违规红线 conf=0.3」
            #      —— **不核验协议内容、不核验是否真发生**；
            #   ② 于是"善意取得"这类主观状态，企业写上名字即可出罪（漏报），
            #      也可能被无关文本误触发（误报）。
            #
            # 新判据：反证与直接证据**同一口径** —— 必须在**本轮已取得材料清单**
            # （`available`，唯一权威 = material_readiness）里能定位到该材料；
            # 只有"真拿到了、能指到"才算已提交。finding 里的文本降级为
            # **企业声明线索**（写进 basis 供复核，不参与判定）。
            m = _match_material(name, purpose, available, role="反证")
            submitted = (m["status"] == "已有")
            # 企业是否在发现里**声明**了这个反证（仅作提示，不作判定）
            _declared = next((h for h in (_covered_by(t, _submitted)
                                          for t in (t for alts in _material_requirements(name) for t in alts))
                              if h), None)
            if submitted:
                _hit = _declared or {"form": (m.get("matched") or ["已提供资料"])[0],
                                     "material": name}
                basis = "本轮已提供与本项对应的材料「%s」，可作为反证核验" % _hit["form"]
            elif _declared:
                basis = ("企业已声明持有「%s」，但**本轮资料清单中未定位到该材料**；"
                         "声明不等于已提交，须补充上传后核对" % _declared["form"])
            else:
                basis = "本轮未取得该正当理由对应的材料"
            elements.append({
                "role": role, "name": name, "purpose": purpose,
                "status": "已提交" if submitted else "待企业提交",
                "basis": basis,
                "matched": list(m.get("matched") or []) if submitted else [],
                "matched_detail": list(m.get("matched_detail") or []) if submitted else [],
                "declared_by_enterprise": bool(_declared),
                "related": [],
                "weight": _ROLE_WEIGHT.get(role, 1),
            })
            continue
        m = _match_material(name, purpose, available, role=role)
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
            # ★ 2026-10-03：判「已有」的**依据**必须随元素带出去（报告与不变式都要能自证）：
            #   逐字依据看 matched_detail.form；类别依据看 by_category（严格口径的类别名）。
            "by_category": m.get("by_category") or [],
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
    # ★★ 2026-10-04（疑点2 D12，双字段）：**具体材料名**清单（面向企业"要补哪几样"）。
    #   `missing_materials` 保持**类别级**不动 —— 它是业态剔除与计数的口径，
    #   换成具体名会让下游建议文案把本业态不适用的具体名写进去（实测 3 项 ERROR）
    #   并打破 `test_verify_and_missing_separated` 的粒度锁定。
    #   两个字段并存：**口径用类别、表达用具体名**，互不干扰。
    missing_material_names: List[str] = []
    verify_material_names: List[str] = []
    # ★ 2026-10-02（用户质疑「服务业是否还欠缺进销存台账」）：**资料要求必须跟随业态**。
    #   判据取唯一权威 `industry_resolver.not_required_materials`（业态 skip_domains 驱动）——
    #   服务型业态天然无实物货物流转 ⇒ 进销存台账/BOM 不计缺失、不进待补清单。
    #   ⚠ 必须在这里（引擎算缺失时）剔，而不是报告层过滤：报告文案（"尚缺：X"）
    #     与计数都基于此处的结论，报告层过滤会出现"还缺1项却没有名字"的自相矛盾。
    # ★★ 2026-10-06：`_na_docs` 已于函数开头取好（**同一派生、不重复计算**）；
    #   到这里 `e["name"]` **已经过段级剔除**（见开头 ★★），故下面的名称级判据
    #   只是纵深防御；`category in _na_docs`（**类别级**，另一粒度）仍不可省 ——
    #   段级名剔除管不到"类别名本身不适用"（如服务型的"进销存台账"类）。
    for e in elements:
        if e["role"] == "反证" or e["status"] == "已有":
            continue
        bucket = verify_materials if e["status"] == "待核" else missing_materials
        names_bucket = (verify_material_names if e["status"] == "待核"
                        else missing_material_names)
        text = e["name"]
        if _na_docs and any(_m and _m in text for _m in _na_docs):
            text = ""  # ★疑点6 D10：本业态天然不适用 ⇒ 不进名称级待补清单（否则正文会要企业交它）
        _cls = False
        for category, keywords in _MATERIAL_KEYWORDS:
            if not any(kw in text for kw in keywords):
                continue
            _cls = True
            forms = [category] + list(_EQUIVALENT_CATEGORIES.get(category, []))
            if any(f in available for f in forms):
                continue  # 该类别本轮已提供 → 不是缺失
            if category in _na_docs:
                continue  # ★ 该业态天然不适用（如服务型企业的进销存台账）→ 不计缺失
            if category not in bucket:
                bucket.append(category)
            if text and text not in names_bucket:
                names_bucket.append(text)
        # ★★ 2026-10-04（疑点3 D13）：**归不了类的缺失证据也要登记具体名**。
        #   旧实现只登记能归入 `_MATERIAL_KEYWORDS` 已知类别的材料名；疑点3 的
        #   「销售台账、发货记录」「客户对账单与询证函回函」归不了任何类别 ⇒ 两个字段都空，
        #   而 §三 文案列的是全部缺失元素 ⇒ 字段与文案口径分裂。
        #   这里**不做类别归一**（`missing_materials` 仍只收已归类项，语义不变），
        #   只把**具体名**补进 `missing_material_names`；业态剔除照常按名判。
        if (not _cls) and text and text not in names_bucket:
            names_bucket.append(text)

    # 反证状态
    rebuttals = [e for e in elements if e["role"] == "反证"]
    if not rebuttals:
        rebuttal_status = "本条红线无适用反证"
    elif any(e["status"] == "已提交" for e in rebuttals):
        rebuttal_status = "企业已提交部分正当理由，须逐项核验后认定"
    else:
        # ★ 2026-10-01（用户批注「排除依据」是排除了什么，看不懂）：旧文案
        #   "现有资料不构成排除依据" 没有宾语、也没点明排除的是本项涉嫌风险，读者无从判断。
        #   改为直述「不足以排除本项涉嫌风险」——排除对象、排除了多少，一次说清。
        rebuttal_status = "企业尚未提交正当理由的书面证明，现有资料不足以排除本项涉嫌风险"

    # ★★ 2026-10-06：旧的**字符级业态剔除块已删除**（原来在这里用 `str.replace` 删子串）。
    #   它有两个已复现的缺陷：① 切出悬空连词残词（"采购合同与"/"与承运记录"）、
    #   且结果**依赖 set 迭代序 ⇒ 同一输入两次运行产出不同**；
    #   ② 时序在 status/basis/direct_missing **之后** ⇒ 名字改了，依据与待补清单没改，
    #      服务型企业照样被要求补物流单据。
    #   ⇒ 现改为**函数开头、算 status 之前**由唯一权威
    #     `industry_resolver.exclude_not_required_material` 段级剔除，
    #     整项不适用则不进 elements（见上方说明与 `industry_excluded`）。

    # ★★ 2026-10-06：红线自带的「补救要求」是**成句文案**，同样含本业态不适用资料
    #   （实测「提供付款对应的采购合同、入库验收单、物流单据，并对资金回流路径…」）
    #   ⇒ 与证据项名走**同一权威**的文本级剔除（`exclude_not_required_in_text`）。
    #   在引擎层就剔：`remedy` 有 3 个消费点（report §五、argumentation.remedy、suspicion 顶层），
    #   只在报告层剔会让另外两处仍要求企业提交不存在的东西。
    _remedy_eff = redline.get("remedy", "")
    if _remedy_eff and _na_docs:
        try:
            from engine.industry_resolver import exclude_not_required_in_text as _xtna
            _remedy_eff = _xtna(_remedy_eff, _na_docs)
        except Exception:  # noqa: BLE001
            pass

    return {
        "elements": elements,
        "available_count": sum(1 for e in elements if e["status"] == "已有"),
        "verify_count": sum(1 for e in elements if e["status"] == "待核"),
        "missing_count": sum(1 for e in elements if e["status"] != "已有"),
        # ★★ 2026-10-05（疑点5 D11）：**原子数**权威字段（与 §三 同算法、同业态剔除）。
        #   事故：上面三个是**元素数**，而 §三 用**材料名原子数**（拆复合名、去重）
        #   ⇒ 同一页 §三「同类 3 项」/§四「同类 1 项」。
        #   本组字段是**唯一权威**：§三 与 §四 都读它 ⇒ 构造上不可能不一致。
        #   ⚠ 仅**新增**，不改上面三个字段、不改任何判定（逐步切换，便于回退）。
        "available_atom_count": len(_atoms_count([e for e in elements if e["status"] == "已有"])),
        "verify_atom_count": len(_atoms_count([e for e in elements if e["status"] == "待核"])),
        # ★ 只算"缺失"（与 §三「确未提供」同口径）—— 旧写法 `!= "已有"` 会把
        #   「待核」「待企业提交」也算进去 ⇒ §三「需要N项」被算大（实测 5→9）。
        "missing_atom_count": len(_atoms_count([e for e in elements if e["status"] == "缺失"])),
        "closure": closure,
        # ★★ 2026-10-09（P0-6 闭合度单一权威）：把闭合度的**分子/分母（权数口径）**一并带出。
        #   事故：`closure` 有两个算法 —— 这里按**权数**（直接证据权数3）算，
        #   而报告 `evidence_have/evidence_need` 按**元素项数**算，门禁 B9 用后者复算前者 ⇒
        #   必然不自洽（实测 0.38 vs 1/4=0.25）。现把分子分母透出，使
        #   `closure == round(closure_num / closure_den, 2)` 可由任一下游**单向复核**。
        "closure_num": got,
        "closure_den": need,
        "verdict": verdict,
        "direct_missing": direct_missing,
        "missing_materials": missing_materials,
        "missing_material_names": missing_material_names,
        "verify_material_names": verify_material_names,
        "verify_materials": verify_materials,
        "remedy": _remedy_eff,
        "rebuttal_status": rebuttal_status,
        "required_materials": list(redline.get("required_materials") or []),
        # ★ 2026-09-29（#448）：本轮**实际取得**的材料名（与需求侧 required/missing 互补）。
        #   用途：逐要件独立核对（constituent_checkpoint）据此解析「该要件的独立数据源是否已取得」。
        #   不改任何闭合度/结论逻辑，仅作为"已取得"的权威清单向下游透出。
        "available_materials": list(available),
        # ★★ 2026-10-06：本项**因业态天然不适用而被剔除**的证据要求（如实披露，**不静默丢**）。
        #   报告据此可写"本项另有 N 项证据要求不属于本业态必查项"。
        "industry_excluded": _excluded,
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
    # ★ 2026-09-27（用户要求）：不以比例表述材料齐全程度，改为项数（已有几项/还缺几项）。
    _have_n = int(chain.get("available_count", 0) or 0)
    _miss_n = int(chain.get("missing_count", 0) or 0)   # missing_count = 待核 + 缺失
    seg.append(f"共需{_have_n + _miss_n}项材料，已有{_have_n}项、还缺{_miss_n}项，{chain.get('verdict', '')}")
    return "；".join(seg) + "。"


# ---------------------------------------------------------------- 闭合度唯一权威（P0-6）
def closure_basis(chain: Any) -> Dict[str, Any]:
    """闭合度的**分子/分母**（权数口径）——唯一计算处。

    ★★ 2026-10-09（P0-6）：闭合度此前有**两个算法**：本模块按证据角色**权数**
    （直接证据 3 / 资金 2 / 间接 2）算，报告 `evidence_have/evidence_need` 按**项数**算，
    门禁 B9 用后者复算前者 ⇒ 必然不自洽。现把分子分母收敛到本函数**一处**：
      · `num` = 已取得（status=="已有"）且非反证 的权数合计
      · `den` = 全部非反证证据 的权数合计
      · `closure = round(min(1.0, num/den), 2)`，den==0 时 closure=0.0
    传入的可以是 evidence_chain 字典，也可以是裸 elements 列表。
    """
    if isinstance(chain, dict):
        els = [e for e in (chain.get("elements") or []) if isinstance(e, dict)]
    elif isinstance(chain, (list, tuple)):
        els = [e for e in chain if isinstance(e, dict)]
    else:
        els = []
    den = sum(int(e.get("weight") or 1) for e in els if e.get("role") != "反证")
    num = sum(int(e.get("weight") or 1) for e in els
              if e.get("role") != "反证" and e.get("status") == "已有")
    closure = round(min(1.0, num / den), 2) if den else 0.0
    return {"num": num, "den": den, "closure": closure, "elements": len(els)}


def closure_of(chain: Any) -> Optional[float]:
    """闭合度唯一权威 —— 由 `elements` **单向重算**（不读缓存值），供报告/门禁共用。

    返回 None 表示**结构缺失**（拿不到 elements），调用方应如实登记"未评估"，
    绝不用 0.0 冒充（缺失≠0）。
    """
    if isinstance(chain, dict) and not (chain.get("elements") or []):
        return None
    if not isinstance(chain, dict) and not isinstance(chain, (list, tuple)):
        return None
    return closure_basis(chain)["closure"]


# ── 门禁可见投影（P0-6）────────────────────────────────────────────────
#: `elements[]` 中**门禁可见**的窄字段（A6 用 status；C3 用 evidence_no；口径用 role/weight）。
SURFACE_ELEMENT_KEYS: Tuple[str, ...] = (
    "name", "role", "status", "weight", "basis", "evidence_no",
)
#: 链级**门禁可见**字段（计数 / 闭合度分子分母 / 待补材料名）。
SURFACE_CHAIN_KEYS: Tuple[str, ...] = (
    "available_count", "verify_count", "missing_count",
    "closure", "closure_num", "closure_den",
    "direct_missing", "missing_materials", "missing_material_names",
)


def surface_chain(chain: Any) -> Optional[Dict[str, Any]]:
    """把证据链裁成**门禁可见投影**（唯一权威）—— 挂到 `confirmed_problems[].evidence_chain`。

    ★★ 2026-10-09（P0-6）：此前该字段恒为 None ⇒ 门禁 A6/C3 **判据空转（SKIP）**。
      但**不能整链挂载**：链里的 `verdict`/`remedy`/`rebuttal_status` 是**成句长文案**，
      而它们**已经在报告正文**（§三 / §五）出现过 —— 整链挂载会让同一段话二次进入
      A3 定性词扫描与去重统计，制造**假红**。
      ⇒ 只保留"门禁真正要用的窄字段"：① elements 的 role/status/weight/basis/编号
        ② 计数 ③ 闭合度分子分母 ④ 待补材料名。

    拿不到 elements ⇒ 返回 None（缺失≠0，不臆造空链）。
    """
    if not isinstance(chain, dict) or not (chain.get("elements") or []):
        return None
    els: List[Dict[str, Any]] = []
    for e in (chain.get("elements") or []):
        if not isinstance(e, dict):
            continue
        els.append({k: e.get(k) for k in SURFACE_ELEMENT_KEYS if e.get(k) not in (None, "")})
    out: Dict[str, Any] = {k: chain.get(k) for k in SURFACE_CHAIN_KEYS if chain.get(k) is not None}
    out["elements"] = els
    return out
