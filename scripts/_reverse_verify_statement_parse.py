# -*- coding: utf-8 -*-
"""GAP-15 反向验证：把报表/申报表结构化改坏，测试必须变红。

五个注入点：
  ① 去掉报表透视分支（回到通用解析）⇒ 报表取不到字段
  ② 金额列择优恒取第一个数值列 ⇒ 纵向表把「行次」当金额
  ③ 申报表不按行次而"见到数值就收"（模拟按项目名猜）
  ④ 主表页过滤失效 ⇒ 附列资料页行次撞号误抓
  ⑤ 报表模式不支持「一、营业收入」这类前缀 ⇒ 利润表取不到

用法：python scripts/_reverse_verify_statement_parse.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
ES = os.path.join(ROOT, "engine", "extract_service.py")
TEST = "tests/test_statement_declaration_parse.py"


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
    txt = open(ES, encoding="utf-8").read()
    assert old in txt, "注入锚点不存在：%r" % old[:70]
    open(ES, "w", encoding="utf-8", newline="").write(txt.replace(old, new, 1))
    _bump(ES)


def inj_no_pivot() -> None:
    _patch('            if _dt in STATEMENT_TYPES:', '            if False:')


def inj_first_amount_col() -> None:
    # 让「择优」整体失效：函数第一行直接返回第一个数值列（= 行次列）
    _patch("            def _pick_amount_col(cols: List[int]) -> int:\n"
           "                cands = [c for c in cols if not _is_ordinal_col(c)] or list(cols)",
           "            def _pick_amount_col(cols: List[int]) -> int:\n"
           "                return cols[0]\n"
           "                cands = [c for c in cols if not _is_ordinal_col(c)] or list(cols)")


def inj_guess_any_number() -> None:
    _patch("        spec_f = lines_map.get(code)\n        if not spec_f:\n            continue",
           "        spec_f = lines_map.get(code) or {'field': 'tax_payable'}\n"
           "        if not spec_f:\n            continue")


def inj_no_main_page_filter() -> None:
    _patch('    main_pages = [t for t in pages if "附列资料" not in t]',
           '    main_pages = list(pages)')


def inj_no_prefix_strip() -> None:
    _patch("                    bare = _strip_statement_prefix(k)",
           "                    bare = k")


CASES = [
    ("① 去掉报表透视", inj_no_pivot),
    ("② 金额列不排除行次", inj_first_amount_col),
    ("③ 行次未命中就猜字段", inj_guess_any_number),
    ("④ 主表页过滤失效", inj_no_main_page_filter),
    ("⑤ 不剥「一、」前缀", inj_no_prefix_strip),
]


def main() -> int:
    base_rc, base_out = _run()
    print("基线：rc=%d %s" % (base_rc, base_out.strip().splitlines()[-1] if base_out.strip() else ""))
    if base_rc != 0:
        print("✗ 基线未绿：\n%s" % base_out[-2000:])
        return 2
    bak = ES + ".bak"
    results = []
    for name, fn in CASES:
        shutil.copy2(ES, bak)
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
            shutil.move(bak, ES)
            _bump(ES)
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
