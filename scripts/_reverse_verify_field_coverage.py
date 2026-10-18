# -*- coding: utf-8 -*-
"""GAP-14 反向验证：把覆盖率接口改回旧口径，测试必须变红。

四个注入点（对应原事故的三处根因 + 一个"假体检"）：
  ① `include_rows=False`（回到只给预览）⇒ 行数 0
  ② 域改回 `t.get("domain")`（表里没这个键）⇒ 域空、字段清单空
  ③ 字段清单去掉"该表已登记字段" ⇒ 未识别字段永远为空（体检自证循环）
  ④ 硬编码 `row_count=0`（伪装成"接口在跑但没数据"）

用法：python scripts/_reverse_verify_field_coverage.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
API = os.path.join(ROOT, "parse_api.py")
TEST = "tests/test_field_coverage_api.py"


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


def _patch(old: str, new: str) -> None:
    txt = open(API, encoding="utf-8").read()
    assert old in txt, "注入锚点不存在：%r" % old[:60]
    open(API, "w", encoding="utf-8", newline="").write(txt.replace(old, new, 1))
    _bump(API)


def inj_preview_only() -> None:
    _patch('got = SVC.get_extracted(document_id, session, include_rows=True)',
           'got = SVC.get_extracted(document_id, session, include_rows=False)')


def inj_domain_key() -> None:
    _patch('dom = SVC._domain_of(doc_type)              # noqa: SLF001 —— 域推导唯一权威',
           'dom = str(t.get("domain") or "")')


def inj_no_registered() -> None:
    _patch("    for n in registered or []:", "    for n in []:")


def inj_row_count_zero() -> None:
    _patch('"row_count": len(rows),', '"row_count": 0,')


CASES = [
    ("① 只给预览（退回 rows=[]）", inj_preview_only),
    ("② 域改回 t['domain']（键不存在）", inj_domain_key),
    ("③ 去掉已登记字段（体检自证）", inj_no_registered),
    ("④ 行数硬编码 0", inj_row_count_zero),
]


def main() -> int:
    base_rc, base_out = _run()
    print("基线：rc=%d %s" % (base_rc, base_out.strip().splitlines()[-1] if base_out.strip() else ""))
    if base_rc != 0:
        print("✗ 基线未绿，反向验证无意义：\n%s" % base_out[-2000:])
        return 2
    bak = API + ".bak"
    results = []
    for name, fn in CASES:
        shutil.copy2(API, bak)
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
            shutil.move(bak, API)
            _bump(API)
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
