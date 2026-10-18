# -*- coding: utf-8 -*-
"""GAP-18 反向验证：把法规分层改坏，测试必须变红。"""
from __future__ import annotations
import json, os, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
TIER = os.path.join(ROOT, "engine", "legal_tier.py")
CFG = os.path.join(ROOT, "config", "legal_law_tiers.json")
LIB = os.path.join(ROOT, "engine", "legal_library.py")
TEST = "tests/test_legal_tier.py"


def _run():
    env = dict(os.environ); env["PYTHONDONTWRITEBYTECODE"] = "1"
    p = subprocess.run([PY, "-m", "pytest", TEST, "-q", "--no-header",
                        "-p", "no:cacheprovider"], cwd=ROOT, capture_output=True,
                       text=True, env=env, timeout=600)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _bump(p):
    st = os.stat(p); os.utime(p, (st.st_atime + 120, st.st_mtime + 120))


def _patch(path, old, new):
    txt = open(path, encoding="utf-8").read()
    assert old in txt, "锚点不存在：%r" % old[:60]
    open(path, "w", encoding="utf-8", newline="").write(txt.replace(old, new, 1))
    _bump(path)


def inj_default_tax() -> None:
    """未知一律算税务（夸大税务口径 = 反向的美化）。"""
    _patch(TIER, '    return "background"\n\n\ndef tier_cn', '    return "tax"\n\n\ndef tier_cn')


def inj_hardcode_law() -> None:
    """源码里硬编码法名清单（回到"法名散落在代码里"的老路）。"""
    _patch(TIER, 'TIERS: tuple = ("tax", "related", "background")',
           'TIERS: tuple = ("tax", "related", "background")\n'
           '_HARDCODED = ("中华人民共和国企业所得税法", "中华人民共和国增值税法")')


def inj_library_no_tier() -> None:
    """库统计接口不分档（回到只报总数）。"""
    _patch(LIB, '        "by_tier": _tier_stats(rows),', '        "by_tier": {},')


def inj_config_bad_value() -> None:
    """配置里写了非法分层值。"""
    p = CFG
    d = json.loads(open(p, encoding="utf-8").read())
    d["laws"]["中华人民共和国企业所得税法"] = "main"
    open(p, "w", encoding="utf-8", newline="").write(json.dumps(d, ensure_ascii=False, indent=2) + "\n")


CASES = [
    ("① 未知一律算税务", inj_default_tax, TIER),
    ("② 源码硬编码法名", inj_hardcode_law, TIER),
    ("③ 库统计不分档", inj_library_no_tier, LIB),
    ("④ 配置非法分层值", inj_config_bad_value, CFG),
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
