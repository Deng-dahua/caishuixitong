# -*- coding: utf-8 -*-
"""反向验证：让 `_scope_gap` 恒返回空（范围披露失效）⇒ 闸门 ②c 必须变红。"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, "engine", "evidence_chain.py")
NL = chr(10)
CRLF = chr(13) + chr(10)

RUN = (
    "import sys; sys.path.insert(0, %r);"
    "from tools.audit_consistency import check_evidence_claim_grounded as f;"
    "iss=[i for i in f() if i[0]=='ERROR']; print(len(iss));"
    "[print(chr(32)*4, i[2][:105]) for i in iss]"
) % ROOT


def run():
    r = subprocess.run([sys.executable, "-c", RUN], capture_output=True, text=True,
                       cwd=ROOT, encoding="utf-8", errors="replace")
    return ((r.stdout or "") + (r.stderr or "")).strip()


base = io.open(P, "r", encoding="utf-8", newline="").read()
has_crlf = CRLF in base
t = base.replace(CRLF, NL)

OLD = '    _name = str(evidence_name or "")\n    _rest = _name'
NEW = '    return ""  # MUTATED: 范围披露失效\n    _name = str(evidence_name or "")\n    _rest = _name'

print("=== 基线 ===")
print(run())
if t.count(OLD) != 1:
    print("!! anchor 命中 %d 次" % t.count(OLD))
    sys.exit(2)
mut = t.replace(OLD, NEW, 1)
io.open(P, "w", encoding="utf-8", newline="").write(mut.replace(NL, CRLF) if has_crlf else mut)
print("\n=== 范围披露失效（D9 复发）===")
print(run())
io.open(P, "w", encoding="utf-8", newline="").write(base)
print("\n=== 还原后 ===")
print(run())
print("逐字节一致:", io.open(P, "r", encoding="utf-8", newline="").read() == base)
