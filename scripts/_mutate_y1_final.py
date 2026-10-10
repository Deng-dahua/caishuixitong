# -*- coding: utf-8 -*-
"""疑点1 最后两项：① D3 类型名改名（名/判据对齐）② D7 另一半（宽泛等价）根因收口。

② 的根因与修法
--------------
证据项名 =「限定语 + 资料类别名」时，限定语分两类：
  · **方向/用途**类（付款/收款/收付/销项/进项/开出/取得…）——任何该类资料都具备，
    不构成额外内容要求 ⇒ 提供「银行流水」即满足「付款银行流水」（旧行为正确，保留）；
  · **实质要求**类（退款/退货/折让/拒收/抵销/赔款/违约金/完整…）——要求资料中含
    **特定性质的记录**，有「银行流水」≠有「退款记录」⇒ **不得**判「已有」，须判「待核」。
旧实现按"双向包含"一刀切 ⇒ 把「退款银行流水」判成「银行流水」已覆盖（无据断言），
而函数自己的 docstring 写的是"逐字材料名覆盖" ⇒ 又一次"注释说 A、代码做 B"。

修法：新增**唯一权威** `_SUBSTANTIVE_QUALIFIERS`（人工审过的实质限定语表），
`_covered_by` 对 `form in token`（证据项更具体）先查该表：
  含实质限定语 ⇒ 不构成覆盖（判待核）；否则维持覆盖。
这样既修掉 D7，又保住闸门②的反向保护（「付款银行流水或第三方支付凭证」+银行流水 仍判「已有」）。
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NL = chr(10)


def swap(path, pairs):
    p = os.path.join(ROOT, path)
    raw = io.open(p, "r", encoding="utf-8", newline="").read()
    crlf = "\r\n" in raw
    s = raw.replace("\r\n", NL)
    for old, new in pairs:
        if s.count(old) != 1:
            print("!! %s: anchor命中 %d次(应为1): %r" % (path, s.count(old), old[:80]))
            sys.exit(2)
        s = s.replace(old, new, 1)
    if crlf:
        s = s.replace(NL, "\r\n")
    io.open(p, "w", encoding="utf-8", newline="").write(s)
    print("OK %s (%d处)" % (path, len(pairs)))


# ── ① D3：类型名去掉"数量异常"的阈值暗示 ──────────────────────────────
swap("engine/domain_analysis.py", [(
    '''            "type": "红冲/作废发票数量异常",''',
    '''            # ★ 2026-10-04（疑点1 D3 收尾）：类型名**去掉"数量异常"**——
            #   本项判据是"存在即成立、不设比例/张数阈值"（见上方详情首句），
            #   而"数量异常"暗示存在一个阈值型判据，名与实不符。
            #   改名后 名（现象情形）/判据（存在即成立）/读数（对题要件证据）三者口径一致。
            "type": "红冲/作废发票情形",'''
)])

swap("main.py", [(
    '''        ("红冲", "红冲/作废发票数量异常"),''',
    '''        ("红冲", "红冲/作废发票情形"),'''
)])

# ── ② D7 另一半：实质限定语权威表 + _covered_by 收窄 ────────────────────
swap("engine/evidence_chain.py", [
    ('''def _covered_by(token: str, available: List[str]) -> Optional[Dict]:''',
     '''# ★★ 2026-10-04（疑点1 四维自检 D7 另一半）：**实质限定语**权威表。
#   证据项名形如「限定语 + 资料类别名」时，限定语分两类：
#     · **方向/用途**类（付款/收款/收付/销项/进项/开出/取得/借/贷/转…）——
#       任何该类资料都具备该属性，不构成额外内容要求 ⇒ 已提供「银行流水」即满足
#       「付款银行流水」（旧行为**正确**，必须保留，否则闸门②的反向保护会报"一刀切判缺失"）。
#     · **实质要求**类（下表）——要求资料中含**特定性质的记录**：
#       有「银行流水」≠有「退款记录」，有「发票」≠有「退货凭据」⇒ **不得**判「已有」，
#       须判「待核」，由报告说明"本项要求【X】，已提供【Y】，须核对其中是否含…"。
#   ⚠ 本表是**唯一权威**，人工审过；新增一类限定语只需加一行，不改逻辑分支。
#     判据只看"多出来的限定部分"，不认整名，因此对任何「限定语+类别名」的写法都成立。
_SUBSTANTIVE_QUALIFIERS: Tuple[str, ...] = (
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


def _covered_by(token: str, available: List[str]) -> Optional[Dict]:'''),
    ('''            # ⚠ 2026-10-04（疑点1 D7 另一半）：曾尝试收窄为 "只认逐字/更具体覆盖"
            #   （删掉 `form in token`），但撞上闸门 ② 的**反向保护**——
            #   「付款银行流水或第三方支付凭证」+ 已提供「银行流水」必须仍判「已有」
            #   （防止用"一刀切判缺失"糊弄检查）。两者冲突的根源是：
            #   限定语到底属**实质要求**（退款=须有退款记录）还是**普通用途**（付款=任何流水都有付款），
            #   **无法靠字符串包含关系区分**，需要一张人工审过的"实质限定语"权威表。
            #   故**暂回退**，待该权威表建立后再收窄（影响面：17 个证据项，分属多条红线）。
            if form == token or form in token or token in form:
                return {"need": token, "material": str(a), "form": form,
                        "exact": form == token}''',
     '''            # ★★ 2026-10-04（疑点1 D7 另一半）：`form in token`（证据项比已提供资料**更具体**）
            #   不再一律算覆盖 —— 先看多出来的限定语是"方向/用途"还是"实质要求"。
            #   实质要求未被满足 ⇒ **不构成覆盖**（由调用方判「待核」）。
            #   （此处正是"有银行流水 ≠ 有退款记录"的落点；而"付款银行流水 ← 银行流水"
            #     因"付款"属方向/用途类，仍算覆盖，闸门②的反向保护不受影响。）
            if form == token or token in form:
                return {"need": token, "material": str(a), "form": form,
                        "exact": form == token}
            if form in token and not _substantive_qualifier(token, form):
                return {"need": token, "material": str(a), "form": form,
                        "exact": False}'''),
])
