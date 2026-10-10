# -*- coding: utf-8 -*-
"""① 去掉披露文本里的 markdown（项目铁律：报告正文禁 markdown）
   ② 给"范围披露"配行为级闸门（含反向保护：无范围限定的命中不得挂披露话术）"""
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
            print("!! %s: anchor命中 %d次(应为1): %r" % (path, s.count(old), old[:70]))
            sys.exit(2)
        s = s.replace(old, new, 1)
    io.open(p, "w", encoding="utf-8", newline="").write(s.replace(NL, CRLF) if has_crlf else s)
    print("OK %s (%d处)" % (path, len(pairs)))


# ── ① 去 markdown（依据会渲染进报告"依据"列） ──────────────────────────
swap("engine/evidence_chain.py", [(
    '''                if _gap:
                    _basis += ("但本项名另含**范围/完整性**限定「%s」，属**同类不同范围**——"
                               "已提供资料是否覆盖该范围（如是否含全部账户、是否逐笔到明细）"
                               "**须人工确认**，确认前不得视为已满足本项范围要求。" % _gap)''',
    '''                if _gap:
                    # ⚠ 本段会渲染进报告的「依据」列 ⇒ **不得带 markdown**（项目铁律：正文禁 markdown）
                    _basis += ("但本项名另含「范围/完整性」限定「%s」，属同类不同范围——"
                               "已提供资料是否覆盖该范围（如是否含全部账户、是否逐笔到明细）"
                               "须人工确认，确认前不得视为已满足本项范围要求。" % _gap)'''
), (
    '''        if _gap2:
            _basis2 += ("；但本项名另含**范围/完整性**限定「%s」，属**同类不同范围**——"
                        "已提供资料是否覆盖该范围须人工确认。" % _gap2)''',
    '''        if _gap2:
            # ⚠ 同上：进报告「依据」列，禁 markdown
            _basis2 += ("；但本项名另含「范围/完整性」限定「%s」，属同类不同范围——"
                        "已提供资料是否覆盖该范围须人工确认。" % _gap2)'''
)])

# ── ② 闸门：范围披露成对断言 ────────────────────────────────────────────
swap("tools/audit_consistency.py", [(
    '''    # ③ 全量不变式：全量红线 × 全部证据项，凡判「已有」必有**可自证**的依据。''',
    '''    # ②c 范围披露（2026-10-04 疑点2 D9，选项 1「披露式」）：
    #     **判「已有」不变**（清别名会破不变量），但"同类不同范围"必须**具体披露且可校验**。
    #     成对反向：带范围限定 ⇒ 必须披露；不带范围限定 ⇒ 不得挂披露话术（防无谓免责）。
    try:
        from engine.evidence_chain import _match_material as _mm       # noqa: PLC0415
        from engine.evidence_chain import _scope_gap as _sg            # noqa: PLC0415
        _st_a = _mm("完整资金链条流水", "", ["银行流水"])
        if _st_a.get("status") != "已有":
            issues.append(("ERROR", "engine/evidence_chain.py",
                           "范围限定项（完整资金链条流水）已不再判「已有」——判定口径被误改"
                           "（清别名会破不变量：要件数据源恒 not_checked）"))
        if not _st_a.get("scope_unverified") or "范围" not in str(_st_a.get("basis", "")):
            issues.append(("ERROR", "engine/evidence_chain.py",
                           "带范围限定却未披露范围差异 ⇒ 「已有」变成无据断言"
                           "（需 scope_unverified 字段 + 依据含范围说明）"))
        _st_b = _mm("银行流水", "", ["银行流水"])
        if _st_b.get("scope_unverified"):
            issues.append(("ERROR", "engine/evidence_chain.py",
                           "无范围限定的命中被判出范围差异 ⇒ 给所有命中挂无谓免责"))
        if _sg("付款银行流水", ["银行流水"]):
            issues.append(("ERROR", "engine/evidence_chain.py",
                           "「付款」属方向/用途类（任何该类资料都具备），不应触发范围披露"))
    except Exception as _e:  # noqa: BLE001
        issues.append(("ERROR", "engine/evidence_chain.py", f"范围披露断言执行失败：{_e}"))

    # ③ 全量不变式：全量红线 × 全部证据项，凡判「已有」必有**可自证**的依据。'''
)])
