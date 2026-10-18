# -*- coding: utf-8 -*-
"""GAP-23 反向验证：把大账套读取/识别改坏，测试必须变红。

四个注入点（前两个是实测抓到的**真事故**）：
  ① `safe_nrows` 退回"dimension 缺失 ⇒ 0 行"（整份账套静默丢光）
  ② 去掉 `bank_statement.require_any`（序时账又被判成银行流水）
  ③ `require_any` 里混进账簿通用词（形同虚设）
  ④ 截断回执在 total 未知时也产出（把"不知道"写成"没超出"）

用法：python scripts/_reverse_verify_large_ledger.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
PE = os.path.join(ROOT, "engine", "parse_enhance.py")
MAIN = os.path.join(ROOT, "main.py")
TEST = "tests/test_large_ledger_row_cap.py"


def _run() -> tuple:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    p = subprocess.run([PY, "-m", "pytest", TEST, "-q", "--no-header",
                        "-p", "no:cacheprovider"],
                       cwd=ROOT, capture_output=True, text=True, env=env, timeout=900)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _bump(path: str) -> None:
    st = os.stat(path)
    os.utime(path, (st.st_atime + 120, st.st_mtime + 120))


def _patch(path: str, old: str, new: str) -> None:
    txt = open(path, encoding="utf-8").read()
    assert old in txt, "注入锚点不存在：%r" % old[:70]
    open(path, "w", encoding="utf-8", newline="").write(txt.replace(old, new, 1))
    _bump(path)


def inj_zero_nrows() -> None:
    """dimension 缺失 ⇒ 直接返回 0（回到"整份账套丢光"）。"""
    _patch(PE, "    if m > 0:\n        return m\n    # ── 兜底：dimension 缺失 ⇒ 有界实测扫描 ──",
           "    if m >= 0:\n        return m\n    # ── 兜底：dimension 缺失 ⇒ 有界实测扫描 ──")


def inj_no_require_any() -> None:
    _patch(MAIN, '        "require_any": ["对方户名", "对方账号", "对方行名", "对方开户行", "交易余额",',
           '        "require_any_off": ["x"],\n        "_unused": ["对方户名", "对方账号", "对方行名", "对方开户行", "交易余额",')


def inj_weak_require_any() -> None:
    _patch(MAIN, '"require_any": ["对方户名", "对方账号", "对方行名", "对方开户行", "交易余额",',
           '"require_any": ["记账日期", "凭证号", "对方账号", "对方行名", "对方开户行", "交易余额",')


def inj_note_when_unknown() -> None:
    _patch(PE, "    if not truncated(total, cap):\n        return \"\"",
           "    if False:\n        return \"\"")


def inj_trial_balance_small_cap() -> None:
    """科目余额表套 3000 上限（实测缺陷：5000 行只读 2999 行）。"""
    _patch(MAIN, "    for r in range(start, min(nrows, 5000)):",
           "    for r in range(start, min(nrows, 3000)):")


CASES = [
    ("① dimension 缺失返回 0 行", inj_zero_nrows, PE),
    ("⑤ 科目余额表套 3000 上限", inj_trial_balance_small_cap, MAIN),
    ("② 去掉 require_any", inj_no_require_any, MAIN),
    ("③ require_any 混入通用词", inj_weak_require_any, MAIN),
    ("④ 行数未知也出截断回执", inj_note_when_unknown, PE),
]


def main() -> int:
    base_rc, base_out = _run()
    print("基线：rc=%d %s" % (base_rc, base_out.strip().splitlines()[-1] if base_out.strip() else ""))
    if base_rc != 0:
        print("✗ 基线未绿，反向验证无意义：\n%s" % base_out[-2500:])
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
                if "failed" in line or "passed" in line or "error" in line.lower():
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
