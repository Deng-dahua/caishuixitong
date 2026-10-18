# -*- coding: utf-8 -*-
"""GAP-16 反向验证：把上传报表勾稽的接入改坏，测试必须变红。

四个注入点（都是当初真实发生过的错法）：
  ① 等级写成"涉嫌风险"（展示名）⇒ 词表外，会被封印静默丢弃
  ② 读取时不判表是否存在 ⇒ 表未建抛 `no such table` 被吞，看起来像"没有异常"
  ③ 库不可用也返回 readable=True ⇒ "读不到"伪装成"没有异常"
  ④ 接入点从 pipeline 里摘掉（回到"算了但不读"）

用法：python scripts/_reverse_verify_statement_feed.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
FEED = os.path.join(ROOT, "engine", "statement_check_feed.py")
PIPE = os.path.join(ROOT, "engine", "pipeline.py")
TEST = "tests/test_statement_check_feed.py"


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


def inj_display_level() -> None:
    _patch(FEED, 'LEVEL = "高风险"', 'LEVEL = "涉嫌风险"')


def inj_no_table_guard() -> None:
    _patch(FEED,
           "            has = conn.execute(_text(\n"
           "                \"SELECT 1 FROM sqlite_master WHERE type='table' AND name='extract_issues'\"\n"
           "            )).first()\n"
           "            if not has:\n"
           "                return [], True",
           "            has = True\n"
           "            if not has:\n"
           "                return [], True")


def inj_failure_looks_ok() -> None:
    _patch(FEED, "    except Exception:                                    # noqa: BLE001\n"
                 "        return [], False\n"
                 "    out: List[Dict[str, Any]] = []",
           "    except Exception:                                    # noqa: BLE001\n"
           "        return [], True\n"
           "    out: List[Dict[str, Any]] = []")


def inj_unwire() -> None:
    _patch(PIPE, "            from engine.statement_check_feed import collect_findings as _xcheck_collect\n"
                 "            _x_findings, _x_receipt = _xcheck_collect(company_id)",
           "            _x_findings, _x_receipt = [], {'readable': True, 'count': 0, 'note': 'x'}")


CASES = [
    ("① 等级写成展示名「涉嫌风险」", inj_display_level, FEED),
    ("② 不判 extract_issues 是否存在", inj_no_table_guard, FEED),
    ("③ 库不可用也报 readable=True", inj_failure_looks_ok, FEED),
    ("④ 摘掉 pipeline 接入点", inj_unwire, PIPE),
]


def main() -> int:
    base_rc, base_out = _run()
    print("基线：rc=%d %s" % (base_rc, base_out.strip().splitlines()[-1] if base_out.strip() else ""))
    if base_rc != 0:
        print("✗ 基线未绿：\n%s" % base_out[-2000:])
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
