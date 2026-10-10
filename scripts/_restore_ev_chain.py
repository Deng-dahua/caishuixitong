# -*- coding: utf-8 -*-
"""恢复 evidence_chain 的两处已验收修复（回退时误用了 11:1x 的旧备份把它们抹掉了）。

按依赖顺序重放：
  ① 实质限定语权威表 `_SUBSTANTIVE_QUALIFIERS` + `_substantive_qualifier`
     （疑点1 D7：退款银行流水 → 待核；付款/收款银行流水 → 仍已有）
  ② 范围披露 `_SCOPE_QUALIFIERS` + `_scope_gap`（疑点2 D9：判已有但必须披露范围差异）

只改 evidence_chain.py；audit_consistency 的闸门未受影响。
★ 文案不含 ASCII 引号。
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NL = chr(10)
CRLF = chr(13) + chr(10)
P = os.path.join(ROOT, "engine", "evidence_chain.py")


def swap(path, old, new, tag):
    raw = io.open(path, "r", encoding="utf-8", newline="").read()
    crlf = CRLF in raw
    t = raw.replace(CRLF, NL)
    c = t.count(old)
    if c != 1:
        print("!! %s 命中 %d 次（应为 1）" % (tag, c))
        sys.exit(2)
    t = t.replace(old, new, 1)
    io.open(path, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
    print("OK %s" % tag)


# ── ① 实质限定语（疑点1 D7）────────────────────────────────────────────
OLD1 = "def _covered_by(token: str, available: List[str]) -> Optional[Dict]:"
NEW1 = (
    "# ★★ 2026-10-04（疑点1 四维自检 D7 另一半）：**实质限定语**权威表。" + NL +
    "#   证据项名形如「限定语 + 资料类别名」时，限定语分两类：" + NL +
    "#     · 方向/用途类（付款/收款/收付/销项/进项/开出/取得…）——任何该类资料都具备，" + NL +
    "#       不构成额外内容要求 ⇒ 已提供「银行流水」即满足「付款银行流水」（旧行为正确，保留）。" + NL +
    "#     · 实质要求类（下表）——要求资料中含**特定性质的记录**：" + NL +
    "#       有「银行流水」≠有「退款记录」⇒ **不得**判「已有」，须判「待核」。" + NL +
    "_SUBSTANTIVE_QUALIFIERS: tuple = (" + NL +
    "    \"退款\", \"退货\", \"退运\", \"退回\", \"折让\", \"拒收\", \"抵销\", \"抵账\", \"核销\"," + NL +
    "    \"赔款\", \"赔偿\", \"违约金\", \"罚没\", \"滞纳\", \"冲减\", \"冲回\"," + NL +
    ")" + NL + NL + NL +
    "def _substantive_qualifier(token: str, form: str) -> str:" + NL +
    "    \"\"\"`token` 比 `form` 多出的限定部分里，是否含**实质要求**类限定语；返回命中的那个。\"\"\"" + NL +
    "    if not token or not form or form == token or form not in token:" + NL +
    "        return \"\"" + NL +
    "    _extra = str(token).replace(str(form), \"\")" + NL +
    "    for _q in _SUBSTANTIVE_QUALIFIERS:" + NL +
    "        if _q in _extra:" + NL +
    "            return _q" + NL +
    "    return \"\"" + NL + NL + NL +
    OLD1
)
swap(P, OLD1, NEW1, "① 实质限定语表")

OLD2 = (
    "            if form == token or form in token or token in form:" + NL +
    "                return {\"need\": token, \"material\": str(a), \"form\": form," + NL +
    "                        \"exact\": form == token}"
)
NEW2 = (
    "            # ★★ 2026-10-04（疑点1 D7 另一半）：`form in token`（证据项比已提供资料**更具体**）" + NL +
    "            #   不再一律算覆盖 —— 先看多出来的限定语是方向/用途还是实质要求。" + NL +
    "            if form == token or token in form:" + NL +
    "                return {\"need\": token, \"material\": str(a), \"form\": form," + NL +
    "                        \"exact\": form == token}" + NL +
    "            if form in token and not _substantive_qualifier(token, form):" + NL +
    "                return {\"need\": token, \"material\": str(a), \"form\": form," + NL +
    "                        \"exact\": False}"
)
swap(P, OLD2, NEW2, "① _covered_by 收窄")

# ── ② 范围披露（疑点2 D9）──────────────────────────────────────────────
OLD3 = "def _related_categories(evidence_name: str, purpose: str,"
NEW3 = (
    "# ★★ 2026-10-04（疑点2 D9，选项 1 披露式）：**范围/完整性**限定语 —— 只用于**披露**，" + NL +
    "#   **不参与**「已有／待核」判定（清别名会破不变量：要件数据源恒 not_checked、既有闸门" + NL +
    "#   要求此类细名判已有）。职责只有一件：本项名在**已命中材料名之外**还带这些限定语时，" + NL +
    "#   说明有这类资料 ≠ 覆盖了这个范围，必须在依据里**具体披露**并标记 scope_unverified。" + NL +
    "_SCOPE_QUALIFIERS: tuple = (" + NL +
    "    \"完整\", \"全量\", \"全部\", \"逐笔\", \"全套\", \"链条\", \"账户\", \"已销户\", \"明细\"," + NL +
    ")" + NL + NL + NL +
    "def _scope_gap(evidence_name: str, matched: List[str]) -> str:" + NL +
    "    \"\"\"本项名在已命中材料名之外是否带**范围/完整性**限定语；有则返回该限定语，否则空串。" + NL + NL +
    "    唯一权威：`_SCOPE_QUALIFIERS`。**只用于披露，不改变判定**。" + NL +
    "    \"\"\"" + NL +
    "    _name = str(evidence_name or \"\")" + NL +
    "    _rest = _name" + NL +
    "    for _m in (matched or []):" + NL +
    "        _m = str(_m or \"\")" + NL +
    "        if _m and _m in _rest:" + NL +
    "            _rest = _rest.replace(_m, \"\")" + NL +
    "    for _q in _SCOPE_QUALIFIERS:" + NL +
    "        if _q in _rest:" + NL +
    "            return _q" + NL +
    "    return \"\"" + NL + NL + NL +
    OLD3
)
swap(P, OLD3, NEW3, "② 范围披露表")

raw = io.open(P, "r", encoding="utf-8", newline="").read()
assert raw.count("_SUBSTANTIVE_QUALIFIERS") == 2, raw.count("_SUBSTANTIVE_QUALIFIERS")
assert raw.count("_SCOPE_QUALIFIERS") == 2, raw.count("_SCOPE_QUALIFIERS")
print("[OK] 两处修复已恢复")
