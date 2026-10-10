# -*- coding: utf-8 -*-
"""给「实质限定语」权威表配**自动校验**（否则表被清空/D7 复发会静默）。

插在 `check_evidence_claim_grounded` 的 ②（反向保护：付款银行流水必须「已有」）之后，
与新断言成对存在、互为反向：
  · ② 方向/用途限定（付款）⇒ **必须**判「已有」（防"一刀切判缺失"）
  · ②b 实质要求限定（退款/退货）⇒ **必须**判「非已有」（防"有银行流水=有退款记录"）
两条同时成立，才说明这张表真的在按"限定语性质"分流，而不是靠一边倒。
"""
import io
import os
import sys

NL = chr(10)
P = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "tools", "audit_consistency.py")

OLD = '''        elif not (st.get("matched_detail") or []):
            issues.append(("ERROR", "engine/evidence_chain.py",
                           f"判「已有」但未给出逐字依据：「{item}」"))
'''
NEW = '''        elif not (st.get("matched_detail") or []):
            issues.append(("ERROR", "engine/evidence_chain.py",
                           f"判「已有」但未给出逐字依据：「{item}」"))

    # ②b 实质限定语（2026-10-04 疑点1 D7 另一半）：证据要求比已提供资料**更具体**、
    #     且多出的限定语属**实质要求**（退款/退货…）⇒ **不得**判「已有」。
    #     与 ② 互为反向：② 管"方向/用途类限定不得一刀切判缺失"，②b 管"实质要求类不得放水"。
    #     两条同时成立，才证明 `_SUBSTANTIVE_QUALIFIERS` 真的在按**限定语性质**分流。
    for mats, item, why in ((["银行流水"], "退款银行流水", "有银行流水 ≠ 有退款记录"),
                            (["银行流水"], "退款明细", "有银行流水 ≠ 有退款明细"),
                            (["销项发票"], "退货凭据", "有销项发票 ≠ 有退货凭据")):
        st = _status(item, mats)
        if st["status"] == "已有":
            issues.append(("ERROR", "engine/evidence_chain.py",
                           f"实质限定语被放水：「{item}」在只提供 {mats} 时被判「已有」"
                           f"（{why}）；现状={st['status']} 依据={st.get('basis')}"))
'''
s = io.open(P, "r", encoding="utf-8", newline="").read()
crlf = "\r\n" in s
s = s.replace("\r\n", NL)
if s.count(OLD) != 1:
    print("!! anchor 命中 %d 次" % s.count(OLD))
    sys.exit(2)
s = s.replace(OLD, NEW, 1)
if crlf:
    s = s.replace(NL, "\r\n")
io.open(P, "w", encoding="utf-8", newline="").write(s)
print("OK 已加 ②b 实质限定语断言（与 ② 成对反向）")
