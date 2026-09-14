# -*- coding: utf-8 -*-
"""误报模式静态体检（2026-09-15 新增，可复用）。

扫描 engine/ 与主程序里几类"必然误报"代码模式：
  ① 前 N 名未切片：sorted(...) 赋给变量后 sum 该变量却无 [:] 切片 → 占比恒为 100%
  ② 状态/枚举用精确相等白名单：真实值带后缀（如「存续（在营、开业、在册）」）即被判异常
  ③ 分母兜底导致恒真：x / max(total, 1) > 0 之类
  ④ 过松门槛：len(...) >= 1 / > 0 即出风险结论
仅输出可疑行，需人工判读。
"""
import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = (".git", "node_modules", "data", ".venv", "__pycache__", "four_reports", "reports")


def py_files():
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for fn in files:
            if fn.endswith(".py"):
                yield os.path.join(root, fn)


def scan_slice():
    """① 前 N 名切片缺失"""
    ps = re.compile(r"(\w+)\s*=\s*sorted\(([^)]{0,140})\)")
    psum = re.compile(r"sum\([^)]{0,80}\bin\s+(\w+)\b")
    out = []
    for p in py_files():
        lines = open(p, encoding="utf-8", errors="ignore").read().splitlines()
        svars = {}
        for i, l in enumerate(lines, 1):
            m = ps.search(l)
            if m:
                svars.setdefault(m.group(1), []).append(i)
        for i, l in enumerate(lines, 1):
            m = psum.search(l)
            if m and m.group(1) in svars and "[:3]" not in l and "[:" not in l:
                out.append((p, i, m.group(1), svars[m.group(1)], l.strip()[:120]))
    return out


def scan_whitelist():
    """② 状态/枚举精确相等白名单"""
    key = re.compile(r"(存续|在业|开业|正常|正常户|一般纳税人|小规模|已申报|A级|B级|M级|C级|D级)")
    inc = re.compile(r"\bin\s+\(\s*[\"'][^\"']+[\"']")
    out = []
    for p in py_files():
        for i, l in enumerate(open(p, encoding="utf-8", errors="ignore").read().splitlines(), 1):
            if "not in" in l or " not " in l:
                continue
            if inc.search(l) and key.search(l):
                out.append((p, i, l.strip()[:130]))
    return out


def scan_always_true():
    """③ 分母兜底恒真 / ④ 过松门槛"""
    out = []
    pats = [
        (re.compile(r"/\s*max\([^)]+\)\s*>\s*0\b"), "分母兜底后 >0（恒真风险）"),
        (re.compile(r"/\s*max\([^)]+\)\s*>\s*0\.0\b"), "分母兜底后 >0.0（恒真风险）"),
        (re.compile(r"len\([^)]+\)\s*>=\s*1\b"), "len>=1 即出结论（过松）"),
        (re.compile(r"len\([^)]+\)\s*>\s*0\b"), "len>0 即出结论（过松）"),
    ]
    for p in py_files():
        for i, l in enumerate(open(p, encoding="utf-8", errors="ignore").read().splitlines(), 1):
            s = l.strip()
            if s.startswith("#"):
                continue
            for pat, why in pats:
                if pat.search(l):
                    out.append((p, i, why, s[:120]))
                    break
    return out


for title, rows, fmt in (
    ("① 前N名切片缺失（占比恒100%）", scan_slice(), "L{1} var={2} decl@{3} | {4}"),
    ("② 状态/枚举精确相等白名单", scan_whitelist(), "L{1} | {2}"),
    ("③④ 恒真/过松门槛", scan_always_true(), "L{1} [{2}] {3}"),
):
    print("=" * 78)
    print(title, "命中", len(rows))
    for r in rows[:25]:
        print(" ", os.path.relpath(r[0], REPO), fmt.format(*r))
