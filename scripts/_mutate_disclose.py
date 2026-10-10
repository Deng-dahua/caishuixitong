# -*- coding: utf-8 -*-
"""选项 1（披露式）：判「已有」不变，但**范围差异必须具体披露且可机器校验**。

背景
----
疑点2 D9：`完整资金链条流水` 在已提供 `银行流水` 时判「已有」。清别名会破不变量
（要件数据源失效 + 既有闸门明确要求此类细名判已有），故**判定口径不动**。

现状问题（读码实测）
----
类别层命中时写得是**对所有命中一律套用**的样板话：
  "…该类别已具备——其中具体材料的范围与口径（如是否覆盖全部账户、是否含本项所指协议）须人工确认。"
① 不具体：无论本项名里到底有没有范围限定，都挂同一句；
② 不可校验：没有结构化字段，闸门无从断言"该披露时必须披露"；
③ 有噪声：**没有**范围限定的普通命中也被迫挂一句"须人工确认"。

修法
----
① 新增唯一权威 `_scope_gap(evidence_name, matched)`：只有本项名在**已命中材料名之外**
   确实带「范围/完整性」限定语时才返回该限定语，否则返回 ""。
   该表**只用于披露**，不改变「已有／待核」判定。
② 判「已有」时附结构化字段 `scope_unverified`（=限定语，无则 None），
   basis 分两路：有范围差异 ⇒ 写明**具体是哪个限定语**+未核实什么；
   无范围差异 ⇒ 明确"本项名中无额外范围限定，视为已具备"，**不挂免责样板**。
③ 闸门（行为级，另附反向验证）：有范围限定且判已有 ⇒ 必须带 `scope_unverified` 且 basis 含"范围"；
   无范围限定且判已有 ⇒ `scope_unverified` 必须为空。
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NL = chr(10)
CRLF = chr(13) + chr(10)


def swap(path, pairs):
    p = os.path.join(ROOT, path)
    raw = io.open(p, "r", encoding="utf-8", newline="").read()
    has_crlf = CRLF in raw
    s = raw.replace(CRLF, NL)
    for old, new in pairs:
        if s.count(old) != 1:
            print("!! %s: anchor命中 %d次(应为1): %r" % (path, s.count(old), old[:80]))
            sys.exit(2)
        s = s.replace(old, new, 1)
    io.open(p, "w", encoding="utf-8", newline="").write(s.replace(NL, CRLF) if has_crlf else s)
    print("OK %s (%d处)" % (path, len(pairs)))


# ── ① 披露用的范围限定语表 + 唯一权威判据 ──────────────────────────────
swap("engine/evidence_chain.py", [(
    '''def _related_categories(evidence_name: str, purpose: str,''',
    '''# ★★ 2026-10-04（疑点2 D9，选项 1「披露式」）：**范围/完整性**限定语 —— 只用于**披露**。
#   ⚠ 本表**不参与**「已有／待核」判定（判定口径见 `_match_material` 的类别层；
#     曾尝试用它使"更具体的名字"不构成覆盖 ⇒ 破了两条硬约束：
#     要件数据源失效恒 not_checked、既有闸门要求此类细名判已有。见 2026-10-04 记忆。）
#   它的职责只有一件：当本项名在**已命中材料名之外**还带着这些限定语时，
#   说明"有这类资料"≠"覆盖了这个范围"，必须在依据里**具体披露**并标记 `scope_unverified`。
_SCOPE_QUALIFIERS: tuple = (
    "完整", "全量", "全部", "逐笔", "全套", "链条", "账户", "已销户", "明细",
)


def _scope_gap(evidence_name: str, matched: List[str]) -> str:
    """本项名在已命中材料名之外是否带**范围/完整性**限定语；有则返回该限定语，否则 ""。

    唯一权威：`_SCOPE_QUALIFIERS`。判据只看"多出来的部分"，因此对任意
    「限定语＋类别名」写法都成立，新增一类限定语只需往表里加一行。
    **只用于披露，不改变判定**。
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


def _recommended_match_material'''
)])

# ── ② 类别层：具体披露 + 结构化字段 ─────────────────────────────────────
swap("engine/evidence_chain.py", [(
    '''                _cat_txt = "、".join(_needed)
                _basis = ("本项要求「%s」（资料类别：%s）；企业已提供同类资料「%s」，"
                          "该类别已具备——其中具体材料的范围与口径（如是否覆盖全部账户、"
                          "是否含本项所指协议）须人工确认。" %
                          (evidence_name, _cat_txt, "、".join(_have[:4])))
                return {"status": "已有", "matched": _have,
                        "matched_detail": [{"material": a, "need": evidence_name,
                                            "form": a, "exact": False} for a in _have[:4]],
                        "unmet": [], "related": [], "basis": _basis,
                        "by_category": _needed}''',
    '''                _cat_txt = "、".join(_needed)
                # ★★ 2026-10-04（疑点2 D9，选 1）：**把范围披露做具体、做成可校验的**。
                #   旧写法对**所有**类别层命中一律套"…范围与口径须人工确认"，既不具体
                #   （本项名里到底有没有范围限定都一样），也无法机器校验，还让没有范围
                #   限定的普通命中无端挂一句免责。现分两路，并把限定语落成结构化字段。
                _gap = _scope_gap(evidence_name, _needed)
                _basis = ("本项要求「%s」（资料类别：%s）；企业已提供同类资料「%s」，"
                          "该类别已具备。" % (evidence_name, _cat_txt, "、".join(_have[:4])))
                if _gap:
                    _basis += ("但本项名另含**范围/完整性**限定「%s」，属**同类不同范围**——"
                               "已提供资料是否覆盖该范围（如是否含全部账户、是否逐笔到明细）"
                               "**须人工确认**，确认前不得视为已满足本项范围要求。" % _gap)
                else:
                    _basis += "本项名中无额外范围限定，视为已具备。"
                return {"status": "已有", "matched": _have,
                        "matched_detail": [{"material": a, "need": evidence_name,
                                            "form": a, "exact": False} for a in _have[:4]],
                        "unmet": [], "related": [], "basis": _basis,
                        "scope_unverified": _gap or None,
                        "by_category": _needed}'''
)])

# ── ③ 严格逐字分支：同样披露（非逐字命中时） ────────────────────────────
swap("engine/evidence_chain.py", [(
    '''        return {
            "status": "已有",
            "matched": matched,
            "matched_detail": matched_detail,
            "unmet": [],
            "related": [],
            "basis": "本轮已提供%s，可作为本项证据" % "、".join(_parts),
        }''',
    '''        _gap2 = _scope_gap(evidence_name, matched)
        _basis2 = "本轮已提供%s，可作为本项证据" % "、".join(_parts)
        if _gap2:
            _basis2 += ("；但本项名另含**范围/完整性**限定「%s」，属**同类不同范围**——"
                        "已提供资料是否覆盖该范围须人工确认。" % _gap2)
        return {
            "status": "已有",
            "matched": matched,
            "matched_detail": matched_detail,
            "unmet": [],
            "related": [],
            "basis": _basis2,
            "scope_unverified": _gap2 or None,
        }'''
)])
