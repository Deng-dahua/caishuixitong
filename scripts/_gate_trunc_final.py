# -*- coding: utf-8 -*-
"""给"截断必须声明总数"加一道**能自测通过**的产物级闸门（写入 audit_consistency ⑧）。

★ 上一轮 4 次失败都栽在**转义**（`\d` 经 bash heredoc → Python 字符串 → 文件 三层被吃掉）。
本脚本用 **Write 工具直接写最终文本**，且正则里**只用 `[0-9]`、不用 `\d`**，并对分隔符用字符类
`[、，,；;／/]` —— **全文零反斜杠**。

判据：正文里「有 N 项（…名…）」若 **N > 实际列出的名数**，且**没有**写「共 N 项」
⇒ 静默截断 ⇒ ERROR。
"""
import io
import os
import subprocess
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
P = os.path.join(ROOT, "tools", "audit_consistency.py")

HELPER = [
    "def _trunc_violations(_text):",
    "    \"\"\"返回「声明项数 > 可见名数 且 未声明总数」的违规列表（截断必须显式声明总数）。",
    "",
    "    ★ 2026-10-04（疑点4 D8 收尾）：原先三处一律只列前 6 个材料名且**静默**",
    "      （实测 seq=9 声明 8 项只列 6 名）⇒ 读者以为只有 6 项。",
    "      现产品侧已用 `_brief_atoms()` 加「等（共N项）」；本函数是它的**自动守护**。",
    "      ⚠ 正则只用 `[0-9]`（不用反斜杠）—— 反斜杠经多层写入会被吃掉。",
    "    \"\"\"",
    "    import re as _rt",
    "    _pat = _rt.compile(\"有([0-9]+)项（([^）]*)）\")",
    "    _sep = _rt.compile(\"[、，,；;／/]|与|和|及|或者\")",
    "    _txt = _text or \"\"",
    "    _out = []",
    "    for _m in _pat.finditer(_txt):",
    "        _dec = int(_m.group(1))",
    "        if (\"共%d项\" % _dec) in _txt:",
    "            continue",
    "        _body = _m.group(2).replace(\"等（共%d项）\" % _dec, \"\").strip()",
    "        _vis = [x.strip() for x in _sep.split(_body) if x.strip()]",
    "        if _dec > len(_vis):",
    "            _out.append((_dec, len(_vis)))",
    "    return _out",
    "",
    "",
]

CALL = [
    "                    # ★ 2026-10-04（疑点4 D8 收尾）：**截断必须声明总数**（自动守护）。",
    "                    for _d9, _v9 in _trunc_violations(_T8):",
    "                        issues.append(('ERROR', 'enterprise_readable_report',",
    "                                       '声明%d项但只列%d个名且未声明总数 seq=%s（静默截断）'",
    "                                       % (_d9, _v9, _p8.get('seq'))))",
]


def rd(p):
    raw = io.open(p, "r", encoding="utf-8", newline="").read()
    return raw.replace(CRLF, NL), (CRLF in raw)


def wr(p, t, h):
    io.open(p, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if h else t)


t, h = rd(P)
if "_trunc_violations" in t:
    print("SKIP 已在（幂等）")
else:
    lines = t.split(NL)
    idx = None
    for i, ln in enumerate(lines):
        if "⑧ 缺料三态" in ln:
            idx = i
            break
    if idx is None:
        print("!! 找不到 ⑧ 闸门行")
        sys.exit(2)
    fn_start = None
    for j in range(idx, -1, -1):
        if lines[j].startswith("def "):
            fn_start = j
            break
    if fn_start is None:
        print("!! 找不到所属 def")
        sys.exit(2)
    lines[fn_start:fn_start] = HELPER
    t = NL.join(lines)
    A = "            except Exception as _e8:"
    if t.count(A) != 1:
        print("!! 调用锚点命中 %d ⇒ 不写盘" % t.count(A))
        sys.exit(2)
    t = t.replace(A, NL.join(CALL + [A]), 1)
    wr(P, t, h)
    print("OK 闸门已插入")

# ══ 自测（写盘后立即验证，不通过就回退）══
BACK = os.path.join(ROOT, "scripts", "_bk_audit_tv2.py")
shutil_ok = True
try:
    import shutil
    shutil.copy2(P, BACK)
except Exception:
    shutil_ok = False

r = subprocess.run([sys.executable, "-c",
                    "import sys; sys.path.insert(0, %r);"
                    "from tools.audit_consistency import _trunc_violations as f;"
                    "print('T1', f('共需8项（c、d、e、f、g、h）'));"
                    "print('T2', f('其中8项已提供（c、d、e、f、g、h等（共8项））'));"
                    "print('T3', f('其中2项已提供（c、d）'))" % ROOT],
                   capture_output=True, text=True, cwd=ROOT,
                   encoding="utf-8", errors="replace")
out = ((r.stdout or "") + (r.stderr or "")).strip()
print("=== 自测 ===")
print(out)
ok = ("T1 [(8, 6)]" in out) and ("T2 []" in out) and ("T3 []" in out)
print("自测通过" if ok else "!! 自测未通过")
if not ok and shutil_ok:
    import shutil
    shutil.copy2(BACK, P)
    print("已回退闸门文件")
    sys.exit(3)
