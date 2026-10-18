# -*- coding: utf-8 -*-
"""GAP-21 反向验证：把"空章节处理"改坏，测试必须变红。

四个注入点：
  ① 回到"只丢空块不丢空章"（章节壳）
  ② 剔除但不登记 `skipped_sections`（静默丢）
  ③ HTML 渲染器不写"未列示"说明（读者以为漏印）
  ④ 把空章节塞进 `omitted`（混淆"视图裁剪"与"本轮无内容"）

用法：python scripts/_reverse_verify_empty_section.py
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
RENDER = os.path.join(ROOT, "engine", "report_render.py")
TEST = "tests/test_empty_section_handling.py"


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


def inj_keep_empty_section() -> None:
    """恢复"章节壳"：空块也照样 append。"""
    old = ('        if not blocks:\n'
           '            skipped.append({"key": key, "title": VIEWS.SECTION_CN[key],\n'
           '                            "reason": _EMPTY_SECTION_REASON})\n'
           '            continue')
    new = ('        if not blocks:\n'
           '            pass')
    _patch(RSVC, old, new)


def inj_silent_drop() -> None:
    """剔除但不登记（静默丢）。"""
    old = ('            skipped.append({"key": key, "title": VIEWS.SECTION_CN[key],\n'
           '                            "reason": _EMPTY_SECTION_REASON})')
    new = ('            pass')
    _patch(RSVC, old, new)


def inj_no_html_note() -> None:
    """HTML 渲染器不写"未列示"说明。"""
    old = '    if sk:\n        T.append("<h2>本报告未列示的章节</h2>'
    new = '    if False:\n        T.append("<h2>本报告未列示的章节</h2>'
    _patch(RENDER, old, new)


def inj_merge_into_omitted() -> None:
    """把空章节塞进 `omitted`（混淆两种语义）。"""
    old = '        "skipped_sections": skipped,'
    new = '        "skipped_sections": [],\n        "omitted": [{"key": x["key"], "title": x["title"]} for x in skipped],'
    _patch(RSVC, old, new)


CASES = [
    ("① 恢复章节壳", inj_keep_empty_section, RSVC),
    ("② 剔除但不登记", inj_silent_drop, RSVC),
    ("③ HTML 不写「未列示」", inj_no_html_note, RENDER),
    ("④ 混进 omitted", inj_merge_into_omitted, RSVC),
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
