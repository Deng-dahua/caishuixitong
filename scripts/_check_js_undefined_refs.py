# -*- coding: utf-8 -*-
"""前端 JS「被调用但未定义」静态扫描（2026-10-01 新增）。

背景（真实事故，本次由它抓到）：
  删除 JS 函数 `_freshnessStrip` 时，只删了函数定义与**报告主体**处的调用，
  漏掉 `renderAnalyzeHeader()` 内的第二处调用 → 运行到该渲染分支时抛
  `ReferenceError: _freshnessStrip is not defined`（页面局部白屏，且**语法检查查不出来**：
  语法合法，只是运行时找不到符号）。

判据：把 JS 里出现的 `_xxx(` 调用集合 与 `function _xxx(` 定义集合求差，
      并排除 `window._xxx =` 动态挂载与 `this._xxx(` 成员调用。
局限：纯文本扫描，不解析作用域；同名局部变量/对象方法可能误报或漏报，
      故输出仅作**提示**，发现即人工确认。

用法：python scripts/_check_js_undefined_refs.py
退出码：存在未定义引用 → 1；否则 0。
"""
import io
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JS_FILES = [
    "static/js/tax-doc-analysis.js",
]

# 允许存在的"动态挂载"写法（在别处赋值）
_DYNAMIC_MARKERS = ("window.", "globalThis.")


def _node():
    for cand in (
        r"C:\Users\Administrator\.workbuddy\binaries\node\versions\22.22.2-3\node.exe",
        "node",
    ):
        try:
            subprocess.run([cand, "-v"], capture_output=True, check=True)
            return cand
        except Exception:
            continue
    return None


def check(path):
    src = io.open(path, encoding="utf-8", errors="ignore").read()
    called = set(m.group(1) for m in re.finditer(r"(?<![\w.])_(\w+)\s*\(", src))
    defined = set(m.group(1) for m in re.finditer(r"function\s+_(\w+)\s*\(", src))
    missing = []
    for name in sorted(called - defined):
        # 动态挂载判定：源码里存在 `window._<name> = ...`（如 window._makeEditIcon = function…）
        if any((mark + "_" + name) in src for mark in _DYNAMIC_MARKERS):
            continue
        missing.append("_" + name)
    return missing


def main():
    node = _node()
    bad_total = 0
    for rel in JS_FILES:
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            print("[SKIP] 不存在:", rel)
            continue
        missing = check(p)
        print("%s | 被调用但未定义的内部函数: %d" % (rel, len(missing)))
        for m in missing:
            print("   ✗", m)
        bad_total += len(missing)
        # 顺带做一次语法检查（语法错误与未定义引用是两类问题）
        if node:
            r = subprocess.run(
                [node, "-e",
                 "const fs=require('fs');const s=fs.readFileSync(process.argv[1],'utf8');"
                 "try{new Function(s);console.log('SYNTAX_OK');}"
                 "catch(e){console.log('SYNTAX_ERR:'+e.message);process.exit(2);}", p],
                capture_output=True, text=True)
            out = (r.stdout or "").strip()
            if "SYNTAX_OK" in out:
                print("   [OK] 语法检查通过")
            else:
                print("   [FAIL] 语法:", out or r.stderr.strip())
                bad_total += 1
    if bad_total:
        print("\n[FAIL] 存在 %d 个问题（未定义引用或语法错误）——删 JS 函数后务必复扫。" % bad_total)
        return 1
    print("\n[OK] 无未定义引用、语法通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
