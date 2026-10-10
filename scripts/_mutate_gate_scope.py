# -*- coding: utf-8 -*-
"""闸门补 4 组断言：范围要求 / 不同实物 也不得判「已有」（疑点2 D9 配套）。"""
import io
import os
import sys

NL = chr(10)
CRLF = chr(13) + chr(10)
P = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "tools", "audit_consistency.py")

OLD = (
    '    for mats, item, why in ((["银行流水"], "退款银行流水", "有银行流水 ≠ 有退款记录"),' + NL +
    '                            (["银行流水"], "退款明细", "有银行流水 ≠ 有退款明细"),' + NL +
    '                            (["销项发票"], "退货凭据", "有销项发票 ≠ 有退货凭据")):'
)
NEW = (
    '    for mats, item, why in ((["银行流水"], "退款银行流水", "有银行流水 ≠ 有退款记录"),' + NL +
    '                            (["银行流水"], "退款明细", "有银行流水 ≠ 有退款明细"),' + NL +
    '                            (["销项发票"], "退货凭据", "有销项发票 ≠ 有退货凭据"),' + NL +
    '                            # ★★ 2026-10-04（疑点2 D9）：**范围要求也不是同义词** ——' + NL +
    '                            #   原先别名表把「完整资金链条流水」「全部银行账户及个人账户流水」' + NL +
    '                            #   登记成「银行流水」的别名 ⇒ `form == token` ⇒ 判「逐字命中」' + NL +
    '                            #   ⇒ 提供「银行流水」就冒充"已有完整资金链条流水"。' + NL +
    '                            (["银行流水"], "完整资金链条流水", "范围要求：要能串起完整链条"),' + NL +
    '                            (["银行流水"], "全部银行账户流水", "范围要求：要覆盖全部账户"),' + NL +
    '                            (["进销存台账"], "退货单", "退货单是退货凭据，不是库存台账"),' + NL +
    '                            (["科目余额表"], "应付账款明细", "科目余额表不提供供应商级明细")):'
)

s = io.open(P, "r", encoding="utf-8", newline="").read()
has_crlf = CRLF in s
t = s.replace(CRLF, NL)
if t.count(OLD) != 1:
    print("!! anchor 命中 %d 次" % t.count(OLD))
    sys.exit(2)
t = t.replace(OLD, NEW, 1)
io.open(P, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if has_crlf else t)
print("OK 闸门已补 4 组断言")
