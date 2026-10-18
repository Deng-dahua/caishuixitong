# -*- coding: utf-8 -*-
"""GAP-20 反向验证：把"服务端导出"改坏，测试必须变红。

四个注入点：
  ① 前端恢复 `window.print()`（回到浏览器打印 ⇒ 无防伪、无元数据）
  ② 端点不写审计留痕（报告流出去无记录）
  ③ 端点去掉权限点校验（任何登录用户都能导出）
  ④ 端点不返回回执头（无法自证走了服务端）

用法：python scripts/_reverse_verify_export_server_side.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
JS = os.path.join(ROOT, "static", "js", "tax-doc-analysis.js")
MAIN = os.path.join(ROOT, "main.py")
TESTS = ["tests/test_export_server_side.py", "tests/test_export_endpoint_live.py"]


def _run() -> tuple:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    p = subprocess.run([PY, "-m", "pytest"] + TESTS + ["-q", "--no-header",
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


def inj_browser_print() -> None:
    """把导出函数改回浏览器打印。"""
    old = "async function exportTaxDocReportPdf() {"
    new = ("async function exportTaxDocReportPdf() {\n"
           "  window.print();\n"
           "  return;")
    _patch(JS, old, new)


def inj_no_audit() -> None:
    """把留痕动作改成"查看"（导出不再被记录为"报告流出去了"）。"""
    _patch(MAIN, '_EXPORT_AUDIT_ACTION = "report.export"',
           '_EXPORT_AUDIT_ACTION = "report.view"')


def inj_no_perm() -> None:
    _patch(MAIN, '    auth = _request_perm(request, "report.generate")',
           '    from engine.api_common import session_of as _so\n    auth = _so(request)')


def inj_no_receipt_headers() -> None:
    _patch(MAIN, '            "X-Report-Render": "server",', '            "X-Report-Gone": "",')


CASES = [
    ("① 前端恢复浏览器打印", inj_browser_print, JS),
    ("② 端点不写审计留痕", inj_no_audit, MAIN),
    ("③ 端点去掉权限校验", inj_no_perm, MAIN),
    ("④ 端点不返回回执头", inj_no_receipt_headers, MAIN),
]


def main() -> int:
    base_rc, base_out = _run()
    print("基线：rc=%d %s" % (base_rc, base_out.strip().splitlines()[-1] if base_out.strip() else ""))
    if base_rc != 0:
        print("✗ 基线未绿，反向验证无意义：\n%s" % base_out[-3000:])
        return 2
    results = []
    for name, fn, target in CASES:
        bak = target + ".bak"
        shutil.copy2(target, bak)
        try:
            fn()
            # JS 改动后需同步版本号（否则"版本不同步"会先报红，掩盖真正的注入点）
            if target == JS:
                env = dict(os.environ)
                env["PYTHONDONTWRITEBYTECODE"] = "1"
                subprocess.run([PY, "tools/sync_asset_versions.py"], cwd=ROOT,
                               env=env, capture_output=True, text=True, timeout=120)
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
            if target == JS:
                subprocess.run([PY, "tools/sync_asset_versions.py"], cwd=ROOT,
                               capture_output=True, text=True, timeout=120)
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
