# -*- coding: utf-8 -*-
"""Reverse verification: prove the new behaviour assertion on the
"missing-material-driven downgrade" backstop point is REAL, not cosmetic.

Sabotage variants (each must turn the gate RED), then restore and confirm GREEN.

Discipline honoured here:
  * sabotage is byte-level and ASCII-safe (no Chinese inside b'' literals);
  * backup lives under scripts/_bak/ only (never engine/, or audit would report
    a second in-repo implementation);
  * after every write we push mtime into the future and run with
    PYTHONDONTWRITEBYTECODE=1 so no stale .pyc masks the change;
  * restore is byte-exact and asserted.
"""
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DOCTRINE = os.path.join(ROOT, "engine", "audit_doctrine.py")
BAK = os.path.join(ROOT, "scripts", "_bak", "audit_doctrine.rev_validate.bak")
GATE = os.path.join(ROOT, "tools", "audit_consistency.py")
PY = sys.executable

ENV = dict(os.environ)
ENV["PYTHONDONTWRITEBYTECODE"] = "1"

results = []


def mark(name, ok, detail=""):
    results.append((name, ok))
    print("[%s] %s %s" % ("PASS" if ok else "FAIL", name, detail))


def fresh(path):
    """Force a re-compile: mtime in the future + no bytecode cache."""
    t = time.time() + 120.0
    os.utime(path, (t, t))


def gate_issues():
    code = (
        "import sys; sys.path.insert(0, r'%s');\n"
        "import tools.audit_consistency as ac;\n"
        "iss = ac.check_audit_doctrine();\n"
        "print('__ISSUES__' + repr(iss));\n"
    ) % ROOT
    p = subprocess.run([PY, "-c", code], capture_output=True, env=ENV, cwd=ROOT)
    out = p.stdout.decode("utf-8", "replace")
    tail = p.stderr.decode("utf-8", "replace")[-400:]
    if "__ISSUES__" not in out:
        print("  !! gate could not be evaluated, stderr tail:", tail)
        return None
    return eval(out.split("__ISSUES__", 1)[1].strip())


def main():
    shutil.copy2(DOCTRINE, BAK)
    with open(BAK, "rb") as fh:
        original = fh.read()
    try:
        # ── baseline must be clean ──────────────────────────────────────────
        base = gate_issues()
        if base is None:
            mark("0-baseline gate evaluable", False)
            return
        e0 = [i for i in base if i[0] == "ERROR"]
        mark("0-baseline clean (no ERROR)", not e0, "errors=%d" % len(e0))

        with open(DOCTRINE, "rb") as fh:
            cur = fh.read()

        # ── S1: reverse the semantics (missing_driven=True -> False) ────────
        a1 = b"                missing_driven=True,\n"
        if a1 not in cur:
            mark("S1-anchor found", False)
            return
        with open(DOCTRINE, "wb") as fh:
            fh.write(cur.replace(a1, b"                missing_driven=False,\n"))
        fresh(DOCTRINE)
        iss = gate_issues()
        hit = [i for i in (iss or []) if i[0] == "ERROR" and "兜底降级点" in i[2]]
        mark("S1-semantics-reversed -> gate RED", bool(hit),
             "hits=%d" % len(hit))
        for i in hit:
            print("      -", i[2][:150])

        # ── restore + S2: make the backstop a silent no-op ─────────────────
        with open(DOCTRINE, "wb") as fh:
            fh.write(original)
        fresh(DOCTRINE)
        cur = original
        a2 = (
            b'        if not looks_missing_driven(f):\n'
            b'            continue\n'
        )
        if a2 not in cur:
            mark("S2-anchor found", False)
            return
        with open(DOCTRINE, "wb") as fh:
            fh.write(cur.replace(a2, b'        if True:\n            continue\n'))
        fresh(DOCTRINE)
        iss = gate_issues()
        hit = [i for i in (iss or []) if i[0] == "ERROR" and "兜底降级点" in i[2]]
        mark("S2-backstop-noop -> gate RED", bool(hit), "hits=%d" % len(hit))
        for i in hit:
            print("      -", i[2][:150])

        # ── S3: score cap removed (probe expects 极高风险 9 -> 待核验) ─────
        a3 = b"            if float(finding.get(\"score\") or 0) > _MISSING_DRIVEN_SCORE_CAP:"
        if a3 not in cur:
            mark("S3-anchor found", False)
            return
        with open(DOCTRINE, "wb") as fh:
            fh.write(cur.replace(a3, b"            if False:"))
        fresh(DOCTRINE)
        iss = gate_issues()
        hit = [i for i in (iss or []) if i[0] == "ERROR" and "score" in i[2]]
        mark("S3-score-cap-removed -> gate RED", bool(hit), "hits=%d" % len(hit))
        for i in hit:
            print("      -", i[2][:150])
    finally:
        with open(DOCTRINE, "wb") as fh:
            fh.write(original)
        fresh(DOCTRINE)
        with open(DOCTRINE, "rb") as fh:
            same = fh.read() == original
        mark("restore byte-exact", same)

    ok = all(ok for _, ok in results)
    print()
    print("ALL PASS = %s" % ok)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
