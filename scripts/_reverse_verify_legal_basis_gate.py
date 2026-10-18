# -*- coding: utf-8 -*-
"""GAP-19 反向验证：把"无依据降级为线索"改坏，测试必须变红。

四个注入点：
  ① 不降风险等级（无依据仍维持"已认定有风险"的档位）
  ② 不降结论等级（仍是 L3「风险事项成立」）
  ③ 取不到依据也降级（把"读不到"当成"没有依据"）
  ④ 详情接口不标注（只剩列表页有标注 ⇒ 两把尺）

用法：python scripts/_reverse_verify_legal_basis_gate.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
G = os.path.join(ROOT, "engine", "legal_basis_gate.py")
RS = os.path.join(ROOT, "engine", "risk_service.py")
TEST = "tests/test_legal_basis_gate.py"


def _run() -> tuple:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    p = subprocess.run([PY, "-m", "pytest", TEST, "-q", "--no-header",
                        "-p", "no:cacheprovider"],
                       cwd=ROOT, capture_output=True, text=True, env=env, timeout=600)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _bump(path: str) -> None:
    st = os.stat(path)
    os.utime(path, (st.st_atime + 120, st.st_mtime + 120))


def _patch(path: str, old: str, new: str) -> None:
    txt = open(path, encoding="utf-8").read()
    assert old in txt, "注入锚点不存在：%r" % old[:70]
    open(path, "w", encoding="utf-8", newline="").write(txt.replace(old, new, 1))
    _bump(path)


def inj_no_level_downgrade() -> None:
    _patch(G,
           'ASSERTED_LEVELS: tuple = ("极高风险", "高风险", "中风险")',
           'ASSERTED_LEVELS: tuple = ()')


def inj_no_grade_downgrade() -> None:
    _patch(G, 'GRADE_CLUE = "L2"', 'GRADE_CLUE = "L3"')


def inj_unavailable_also_downgrades() -> None:
    """把"读不到"当成"没有依据"（缺失如实被破坏）。

    ★ 注入必须**真的改变行为**：只在 `provisions_n = 0` 后面赋值没用 ——
      原代码随后仍走 `unavailable` 分支并提前 return，等级一字不改（实测 12 passed，
      是**假注入**）。正确注入 = 让 `None` 不提前返回，落进 `n == 0` 的降级分支。
    """
    old = ('    if provisions_n is None:\n'
           '        finding["legal_basis_status"] = "unavailable"\n'
           '        finding["legal_basis_note"] = NOTE_UNAVAILABLE\n'
           '        return finding')
    new = ('    if provisions_n is None:\n'
           '        finding["legal_basis_status"] = "unavailable"\n'
           '        finding["legal_basis_note"] = NOTE_UNAVAILABLE\n'
           '        provisions_n = 0')
    _patch(G, old, new)


def inj_unwire_detail() -> None:
    """详情接口不再标注（列表页还有 ⇒ 两把尺）。"""
    _patch(RS,
           '        _basis_annotate(f, len(_lbf.get("provisions") or []))',
           '        pass')


CASES = [
    ("① 不降风险等级", inj_no_level_downgrade, G),
    ("② 不降结论等级", inj_no_grade_downgrade, G),
    ("③ 取不到依据也降级", inj_unavailable_also_downgrades, G),
    ("④ 详情接口不标注", inj_unwire_detail, RS),
]


def main() -> int:
    base_rc, base_out = _run()
    print("基线：rc=%d %s" % (base_rc, base_out.strip().splitlines()[-1] if base_out.strip() else ""))
    if base_rc != 0:
        print("✗ 基线未绿，反向验证无意义：\n%s" % base_out[-2000:])
        return 2
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
                    detail = line.strip()
                    break
            results.append({"case": name, "turned_red": rc != 0, "detail": detail})
            print("%s %s → %s" % ("✓" if rc != 0 else "✗", name, detail))
        finally:
            shutil.move(bak, target)
            _bump(target)
    after_rc, after_out = _run()
    print("还原后：rc=%d %s" % (after_rc,
                              after_out.strip().splitlines()[-1] if after_out.strip() else ""))
    ok = all(r["turned_red"] for r in results) and after_rc == 0
    print("\n===== 结论 =====")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print("反向验证 %d/%d 触发红灯；还原后 %s"
          % (sum(1 for r in results if r["turned_red"]), len(results),
             "绿" if after_rc == 0 else "仍红（异常）"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
