# -*- coding: utf-8 -*-
"""疑点1 D7 的另一半（宽泛等价）根因收口：`_covered_by` 不得**反向覆盖**。

病根：覆盖规则写成"**双向**包含"（`form in token or token in form`），
      于证据要求「退款银行流水」被已提供资料「银行流水」覆盖 ⇒ 判「已有」——
      可"有银行流水"≠"有退款记录"。多出来的限定语（退款/收款/付款/向供应商付款/
      转让价款/向个人或灵活用工平台…）恰恰是**实质性要求**。
      而本函数 docstring 自己写的是「**逐字**材料名覆盖」——又是"注释说 A、代码做 B"。

修法（不对称，只删反向）：
  · `form == token`      → 逐字命中（exact）
  · `token in form`      → 已提供资料**更具体**（要求"银行流水"、提供"银行流水（全部账户）"）⇒ 仍算覆盖
  · `form in token`      → 证据要求**更具体**（限定语）⇒ **不再算覆盖**，由调用方判「待核」，
                            并在说明里点明"已提供【银行流水】，本项要求【退款银行流水】，须核对是否含退款记录"

已量化影响面：91 条红线的证据项里，17 条命中反向包含（涉 15 条红线），
其中"退款银行流水/收款银行流水/向供应商付款的银行流水/转让价款的银行流水"等
正是被误判「已有」的那一类。
"""
import io
import os
import sys

NL = chr(10)
P = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "engine", "evidence_chain.py")

OLD = '''            if form == token or form in token or token in form:
                return {"need": token, "material": str(a), "form": form,
                        "exact": form == token}'''
NEW = '''            # ★★ 2026-10-04（疑点1 四维自检 D7）：**不得反向覆盖**——只保留
            #   `form == token`（逐字命中）与 `token in form`（已提供资料更具体）。
            #   旧实现的 `form in token`（证据要求更具体）会把「退款银行流水」判成
            #   「银行流水」已覆盖 ⇒ 无据断言「已有」；而"退款"这类限定语是实质要求。
            #   本函数 docstring 写的本来就是"逐字材料名覆盖"，此处是让代码回到注释口径。
            if form == token or token in form:
                return {"need": token, "material": str(a), "form": form,
                        "exact": form == token}'''

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
print("OK _covered_by 反向覆盖已收敛（逐字/更具体才算覆盖）")
