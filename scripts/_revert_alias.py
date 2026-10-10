# -*- coding: utf-8 -*-
"""回退"别名表清理 + 范围类限定语"，并补回崩溃时丢失的闸门补丁。

为什么回退（实测 7 ERROR + 1 test FAILED）：
  · RL-PTY-001 第3/第5条要件的**数据源**「应付账款明细」移出别名表后 ⇒ 该要件**恒 not_checked**
    （踩了 `material_names` 的不变量：每个要件数据源都必须能归入某类）
  · 既有闸门明确断言：**细名（完整资金链条流水）在已提供银行流水时"应判已有"**
    —— 这是 10-03 那批的**设计决定**（避免"细名永远匹配不上 ⇒ 系统性判缺失"）
  · tests/test_audit_doctrine.py::TestConstituentSourceObtainability 同步失败

⇒ 结论：疑点2 D9 **不能靠删别名修**，它撞的是**上层的取舍**。
   正确修法要在更上层：判「已有」的同时**在依据里显式披露范围差异**，
   或增设"同族不同物"的第三关系类型 / 新增第 16 类。
   本轮先把这条链路的**不变量与冲突留档**，不硬破。

同时补回 `_fix_gate_nonTax.py`（崩溃恢复时未重放 ⇒ 旧字符串闸门复活并误报）。
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NL = chr(10)
CRLF = chr(13) + chr(10)

# ── ① 回退 material_names（从改前副本整文件还原） ──────────────────────
_src = os.path.join(ROOT, "scripts", "_bk_matnames.py")
_dst = os.path.join(ROOT, "engine", "material_names.py")
io.open(_dst, "w", encoding="utf-8", newline="").write(
    io.open(_src, "r", encoding="utf-8", newline="").read())
print("OK 已整文件还原 engine/material_names.py")

# ── ② 移除 evidence_chain 的 _SCOPE_QUALIFIERS（保留 _SUBSTANTIVE_QUALIFIERS） ──
P = os.path.join(ROOT, "engine", "evidence_chain.py")
s = io.open(P, "r", encoding="utf-8", newline="").read()
has_crlf = CRLF in s
t = s.replace(CRLF, NL)

T1 = (
    NL +
    '# ★★ 2026-10-04（疑点2 D9）：**范围/完整性**类限定语——要求"这份资料是完整的/含全量的/' + NL +
    '#   "逐笔到明细的"，同样**不是**"同一实物的另一种叫法"。「全部银行账户流水」不是' + NL +
    '#   「银行流水」的同义词：企业提供的流水可能只覆盖一个账户。二者并列构成"更强要求"的两类。' + NL +
    '_SCOPE_QUALIFIERS: tuple = (' + NL +
    '    "完整", "全量", "全部", "逐笔", "明细", "全套", "账户", "链条",' + NL +
    ')' + NL
)
T2 = (
    '    for _q in _SCOPE_QUALIFIERS:' + NL +
    '        if _q in _extra:' + NL +
    '            return _q' + NL
)
for _name, _frag in (("_SCOPE_QUALIFIERS 表", T1), ("_SCOPE_QUALIFIERS 循环", T2)):
    if t.count(_frag) != 1:
        print("!! %s anchor 命中 %d 次" % (_name, t.count(_frag)))
        sys.exit(2)
    t = t.replace(_frag, "", 1)
io.open(P, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if has_crlf else t)
print("OK 已移除 _SCOPE_QUALIFIERS（保留 _SUBSTANTIVE_QUALIFIERS：疑点1 D7 仍修好）")
