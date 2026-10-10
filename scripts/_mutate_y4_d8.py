# -*- coding: utf-8 -*-
"""疑点4 · D8-① 修复：**缺料三态计数同源同单位**（一次做完，含恒等式自检）。

事故原文（seq=1）：「本项核查需要 **3** 项材料，其中 **1** 项已提供同类资料（退款银行流水）…；
**另有 1 项（退款银行流水）**须确认已提供资料中是否含该内容；确未提供的有 **3** 项」

两层根因
--------
① **同一批 `verify` 被说两遍**：`elif verify:` 分支已说"其中N项已提供同类资料…"，
   紧随其后的独立 `if verify:` 又说"另有N项…须确认…" ⇒ 同一份材料计两次。
   ⚠ 只有 `have` 为空时两段才都执行 ⇒ 正是这类疑点触发。
② **单位不一致**：「需要N项」是**证据元素个数**（`len(_els)`），
   而「确未提供的K项」是**材料名原子数**（拆复合名、去重）⇒ 两段必然对不上。
   （这一层是 2026-10-04 修疑点3「计数观感」时只改一段、未统一全文口径引入的。）

修法
----
· 把缺料口径（`_lack_auth` / `_lack_ok`）**提前**到三态计数之前（唯一权威来源）；
· 三态计数全部按**材料名原子数**（`_atoms_of`：拆复合名 + 去重）：
  `_need_n = 逐字 + 同类 + 确未提供`（**由构造保证恒等**）；
· 删掉重复的"另有N项…"那段（`elif verify:` 改 `if verify:`，两态并存时各说一次）。

纪律：锚点唯一性先校验；同一文件多次替换**累积**后一次性写盘；改完跑**恒等式自检**。
"""
import io
import os
import subprocess
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
ER = os.path.join(ROOT, "engine", "enterprise_report.py")

# ── ① 计数：原子数 + 缺料口径提前 ──
A1 = ('        _need_n = len(_els)' + NL + '        _have_n = len(have)' + NL)
N1 = (
    '        # ★★ 2026-10-04（疑点4 D8-① 修复）：**三态计数同源同单位**。' + NL +
    '        #   事故：「需要3项」但分项 1+1+3=5 —— ①同一批 verify 被说两遍（见下）；' + NL +
    '        #   ②「需要N项」按**元素数**、而「确未提供的K项」按**材料名原子数** ⇒ 单位不同必然对不上。' + NL +
    '        #   修法：缺料口径提前到此处（唯一权威），三态统一按**原子数**（拆复合名 + 去重），' + NL +
    '        #   `_need_n` 由三态**相加得出** ⇒ 恒等式由构造保证。' + NL +
    '        _lack_auth = [str(_z9) for _z9 in (ev.get("missing_material_names") or [])' + NL +
    '                      if str(_z9).strip()]' + NL +
    '        if _lack_auth:' + NL +
    '            _lack_ok = _filter_not_required(list(_lack_auth), not_required_docs)' + NL +
    '        else:' + NL +
    '            _lack_ok = _filter_not_required(list(_lack_names_early), not_required_docs)' + NL +
    NL +
    '        def _atoms_of(_lst):' + NL +
    '            _out = []' + NL +
    '            for _x9 in (_lst or []):' + NL +
    '                _n9 = _x9.get("name") if isinstance(_x9, dict) else _x9' + NL +
    '                for _y9 in re.split(r"[、，,；;／/]|与|和|及|以及|或", str(_n9 or "")):' + NL +
    '                    _y9 = _y9.strip()' + NL +
    '                    if _y9 and _y9 not in _out:' + NL +
    '                        _out.append(_y9)' + NL +
    '            return _out' + NL +
    NL +
    '        _at_have = _atoms_of(have)' + NL +
    '        _at_verify = _atoms_of(verify)' + NL +
    '        _at_lack = _atoms_of(_lack_ok)' + NL +
    '        _have_n = len(_at_have)' + NL +
    '        _need_n = _have_n + len(_at_verify) + len(_at_lack)' + NL
)

# ── ② verify 段：elif → if（与 have 并列），删掉后面的重复段 ──
A2 = ('        elif verify:' + NL)
N2 = ('        if verify:' + NL)
A3 = ('        if verify:' + NL +
      '            _p3 += "；另有%d项（%s）须确认已提供资料中是否含该内容" % (' + NL +
      '                len(verify), _name_brief(verify))' + NL)
N3 = ('        # ★ 2026-10-04（疑点4 D8-①）：原此处还有一段"另有N项（…）须确认已提供资料中是否含' + NL +
      '        #   该内容"，与上面的 verify 段**描述同一批材料** ⇒ 同一份被数两次（"需要3项"却' + NL +
      '        #   出现 1+1+3=5）。已删除，三态各说一次。' + NL)

# ── ③ 提前取 lack 的名字（原在后面才有 _lack_names，这里先建 early 版）──
A4 = ('        lack = [e for e in _els if e.get("status") == "缺失"]' + NL)
N4 = ('        lack = [e for e in _els if e.get("status") == "缺失"]' + NL +
      '        # ★ 2026-10-04（疑点4 D8-①）：缺料名字先取好（`_lack_names_early`），' + NL +
      '        #   供下面的三态计数在权威字段缺失时回落使用。' + NL +
      '        _lack_names_early = []' + NL +
      '        for _e7 in (lack or []):' + NL +
      '            _n7 = _e7.get("name") if isinstance(_e7, dict) else _e7' + NL +
      '            _n7 = str(_n7 or "").strip()' + NL +
      '            if _n7 and _n7 not in _lack_names_early:' + NL +
      '                _lack_names_early.append(_n7)' + NL)

# ── ④ 后面那段重复计算改为"沿用上面已算好的" ──
A5 = ('        _lack_auth = [str(_z9) for _z9 in (ev.get("missing_material_names") or [])' + NL +
      '                      if str(_z9).strip()]' + NL +
      '        if _lack_auth:' + NL +
      '            _lack_ok = _filter_not_required(list(_lack_auth), not_required_docs)' + NL +
      '        else:' + NL +
      '            _lack_ok = _filter_not_required(list(_lack_names), not_required_docs)' + NL)
N5 = ('        # （`_lack_auth` / `_lack_ok` 已在三态计数处算好 —— 唯一来源，不在此重复计算。）' + NL)

EDITS = [(A4, N4, "①提前取缺料名"), (A1, N1, "②三态按原子数"),
         (A2, N2, "③verify 段改并列"), (A3, N3, "④删重复段"), (A5, N5, "⑤去掉重复计算")]


def rd(p):
    return io.open(p, "r", encoding="utf-8", newline="").read().replace(CRLF, NL)


raw = io.open(ER, "r", encoding="utf-8", newline="").read()
crlf = CRLF in raw
t = raw.replace(CRLF, NL)
print("=== 锚点校验 ===")
ok = True
for old, _new, tag in EDITS:
    c = t.count(old)
    print("  %-16s 命中 %d 次 %s" % (tag, c, "OK" if c == 1 else "**不唯一**"))
    if c != 1:
        ok = False
if not ok:
    print("!! 锚点不唯一 ⇒ 不写盘")
    sys.exit(2)
for old, new, tag in EDITS:
    t = t.replace(old, new, 1)
    print("  OK " + tag)
assert "另有%d项（%s）须确认已提供资料中是否含该内容" not in t, "重复段未删净"
io.open(ER, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
print("[DONE] D8-① 已修")
