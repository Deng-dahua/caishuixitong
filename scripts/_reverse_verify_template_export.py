# -*- coding: utf-8 -*-
"""GAP-22 反向验证：把"行业模板口径声明"改坏，测试必须变红。

四个注入点：
  ① 不写 `template_meta`（回到"导出件里看不出行业适配生没生效"）
  ② `applied` 谎报为 True（假装导出件也按行业模板重排了）
  ③ 声明不挂进免责声明章（导出件里看不到）
  ④ 行业未匹配时冒用"已适配"措辞

用法：python scripts/_reverse_verify_template_export.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
RSVC = os.path.join(ROOT, "engine", "report_service.py")
TEST = "tests/test_report_template_export_consistency.py"


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


def _patch(old: str, new: str) -> None:
    txt = open(RSVC, encoding="utf-8").read()
    assert old in txt, "注入锚点不存在：%r" % old[:70]
    open(RSVC, "w", encoding="utf-8", newline="").write(txt.replace(old, new, 1))
    _bump(RSVC)


def inj_no_meta() -> None:
    _patch('        "template_meta": _tpl_meta,', '        "template_meta": {},')


def inj_claim_applied() -> None:
    _patch('    meta: Dict[str, Any] = {"industry": str(industry or ""), "applied": False,',
           '    meta: Dict[str, Any] = {"industry": str(industry or ""), "applied": True,')


def inj_not_rendered() -> None:
    _patch('    decl = str(ctx.get("template_declaration") or "").strip()\n'
           '    if decl:\n'
           '        blocks.append(_block_note(decl))',
           '    decl = str(ctx.get("template_declaration") or "").strip()\n'
           '    if False:\n'
           '        blocks.append(_block_note(decl))')


def inj_borrow_on_unmatched() -> None:
    _patch('        if tpl:\n', '        if True:\n')


CASES = [
    ("① 不写 template_meta", inj_no_meta),
    ("② 谎报 applied=True", inj_claim_applied),
    ("③ 声明不进正文", inj_not_rendered),
    ("④ 未匹配也冒用适配措辞", inj_borrow_on_unmatched),
]


def main() -> int:
    base_rc, base_out = _run()
    print("基线：rc=%d %s" % (base_rc, base_out.strip().splitlines()[-1] if base_out.strip() else ""))
    if base_rc != 0:
        print("✗ 基线未绿，反向验证无意义：\n%s" % base_out[-2000:])
        return 2
    bak = RSVC + ".bak"
    results = []
    for name, fn in CASES:
        shutil.copy2(RSVC, bak)
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
            shutil.move(bak, RSVC)
            _bump(RSVC)
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
