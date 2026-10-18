# -*- coding: utf-8 -*-
"""GAP-17 反向验证：把两列指标改坏，测试必须变红。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
COV = os.path.join(ROOT, "engine", "legal_coverage.py")
GATE = os.path.join(ROOT, "tools", "audit_consistency.py")
TEST = "tests/test_legal_coverage_two_columns.py"


def _run():
    env = dict(os.environ); env["PYTHONDONTWRITEBYTECODE"] = "1"
    p = subprocess.run([PY, "-m", "pytest", TEST, "-q", "--no-header",
                        "-p", "no:cacheprovider"], cwd=ROOT,
                       capture_output=True, text=True, env=env, timeout=600)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _bump(p):
    st = os.stat(p); os.utime(p, (st.st_atime + 120, st.st_mtime + 120))


def _patch(path, old, new):
    txt = open(path, encoding="utf-8").read()
    assert old in txt, "注入锚点不存在：%r" % old[:60]
    open(path, "w", encoding="utf-8", newline="").write(txt.replace(old, new, 1))
    _bump(path)


def inj_law_only_means_article() -> None:
    """只写到法名也算"条号级可核对"（即两列合并）。"""
    _patch(COV, '        "article_total_refs": art_total,',
           '        "article_total_refs": tot,\n        "_x": art_total,')


def inj_no_article_refs() -> None:
    """不披露"只到法名"的段数（恒 0）。"""
    _patch(COV, '        "no_article_refs": no_art,', '        "no_article_refs": 0,')


def inj_registry_drop_column() -> None:
    """登记文件丢掉 article_coverage（回到单列口径）。"""
    p = os.path.join(ROOT, "config", "legal_text_coverage.json")
    d = json.loads(open(p, encoding="utf-8").read())
    d.pop("article_coverage", None)
    open(p, "w", encoding="utf-8", newline="").write(json.dumps(d, ensure_ascii=False, indent=2) + "\n")


def restore_registry() -> None:
    sys.path.insert(0, ROOT)
    from engine.legal_coverage import write_registry
    write_registry()


def inj_gate_no_two_columns() -> None:
    """闸门不再比两列。"""
    _patch(GATE, '        for _key, _label in (("law_coverage", "引用可定位率"),',
           '        for _key, _label in ():')


CASES = [
    ("① 两列合并（法名当条号级）", inj_law_only_means_article, COV),
    ("② 不披露仅到法名段数", inj_no_article_refs, COV),
    ("③ 登记文件丢条号级列", inj_registry_drop_column, os.path.join(ROOT, "config", "legal_text_coverage.json")),
    ("④ 闸门不再比两列", inj_gate_no_two_columns, GATE),
]


def main() -> int:
    base_rc, base_out = _run()
    print("基线：rc=%d %s" % (base_rc, base_out.strip().splitlines()[-1] if base_out.strip() else ""))
    if base_rc != 0:
        print("✗ 基线未绿：\n%s" % base_out[-1500:]); return 2
    results = []
    for name, fn, target in CASES:
        bak = target + ".bak"
        shutil.copy2(target, bak)
        try:
            fn()
            rc, out = _run()
            detail = ""
            for line in reversed(out.strip().splitlines()):
                if "failed" in line or "passed" in line:
                    detail = line.strip(); break
            results.append({"case": name, "turned_red": rc != 0, "detail": detail})
            print("%s %s → %s" % ("✓" if rc != 0 else "✗", name, detail))
        finally:
            shutil.move(bak, target); _bump(target)
    after_rc, after_out = _run()
    print("还原后：rc=%d %s" % (after_rc, after_out.strip().splitlines()[-1] if after_out.strip() else ""))
    ok = all(r["turned_red"] for r in results) and after_rc == 0
    print("\n===== 结论 =====")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print("反向验证 %d/%d 触发红灯；还原后 %s" % (sum(1 for r in results if r["turned_red"]),
          len(results), "绿" if after_rc == 0 else "仍红（异常）"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
