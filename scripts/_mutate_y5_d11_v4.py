# -*- coding: utf-8 -*-
"""疑点5 · D11 第一步（单点、低风险）：在**引擎层**产出三态的**原子数**权威字段。

★ 唯一计数权威就在这里（`evidence_chain.py:601-603`）：
      "available_count": sum(1 for e in elements if e["status"] == "已有")
      "verify_count":    sum(1 for e in elements if e["status"] == "待核")
      "missing_count":   sum(1 for e in elements if e["status"] != "已有")
  —— 全是**元素数**；而 §三 用**材料名原子数**（拆复合名、去重）⇒ 同一页两个数。

本步只**新增**三个字段（**不改**现有字段、不改任何判定）：
      available_atom_count / verify_atom_count / missing_atom_count
  算法与 §三 一致：拆复合名（分隔符含 、，,；;／/ 与 以及/与/和/及/或）+ 去重，
  且**先过业态剔除**（唯一权威 `industry_resolver.not_required_materials`，与 §三 同源）。
第二步再让 §三/§四 读这三个字段（构造上不可能不一致）。
"""
import io
import os
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
P = os.path.join(ROOT, "engine", "evidence_chain.py")

OLD = (
    '        "available_count": sum(1 for e in elements if e["status"] == "已有"),' + NL +
    '        "verify_count": sum(1 for e in elements if e["status"] == "待核"),' + NL +
    '        "missing_count": sum(1 for e in elements if e["status"] != "已有"),'
)
NEW = (
    '        "available_count": sum(1 for e in elements if e["status"] == "已有"),' + NL +
    '        "verify_count": sum(1 for e in elements if e["status"] == "待核"),' + NL +
    '        "missing_count": sum(1 for e in elements if e["status"] != "已有"),' + NL +
    '        # ★★ 2026-10-05（疑点5 D11）：**原子数**权威字段（与 §三 同算法、同业态剔除）。' + NL +
    '        #   事故：上面三个是**元素数**，而 §三 用**材料名原子数**（拆复合名、去重）' + NL +
    '        #   ⇒ 同一页 §三「同类 3 项」/§四「同类 1 项」。' + NL +
    '        #   本组字段是**唯一权威**：§三 与 §四 都读它 ⇒ 构造上不可能不一致。' + NL +
    '        #   ⚠ 仅**新增**，不改上面三个字段、不改任何判定（逐步切换，便于回退）。' + NL +
    '        "available_atom_count": len(_atoms_count([e for e in elements if e["status"] == "已有"])),' + NL +
    '        "verify_atom_count": len(_atoms_count([e for e in elements if e["status"] == "待核"])),' + NL +
    '        "missing_atom_count": len(_atoms_count([e for e in elements if e["status"] != "已有"])),'
)

HELPER = '''def _atoms_count(elements, not_required_docs=None):
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
            _n = _n.replace(_s, "\\x00")
        for _y in _n.split("\\x00"):
            _y = _y.strip()
            if _y and _y not in _out:
                _out.append(_y)
    return _out


'''

raw = io.open(P, "r", encoding="utf-8", newline="").read()
crlf = CRLF in raw
t = raw.replace(CRLF, NL)

if "_atoms_count" in t:
    print("SKIP 已在（幂等）")
    sys.exit(0)

# 插 helper 到 build_evidence_chain 之前
A = "def build_evidence_chain("
c = t.count(A)
print("build_evidence_chain 命中 =", c)
if c != 1:
    print("!! 锚点异常 ⇒ 不写盘")
    sys.exit(2)
t = t.replace(A, HELPER + A, 1)

c2 = t.count(OLD)
print("三态计数字段命中 =", c2)
if c2 != 1:
    print("!! 字段锚点异常 ⇒ 不写盘")
    sys.exit(2)
t = t.replace(OLD, NEW, 1)
io.open(P, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
print("[DONE] 引擎层已加原子数权威字段（仅新增，行为不变）")
