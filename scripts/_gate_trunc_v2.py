# -*- coding: utf-8 -*-
"""给"截断必须声明总数"加产物级闸门（这次链路里没有 shell —— 本文件由 Write 工具直接落盘）。

★ 前 5 次失败的真根因：`python -c "…"` 传入的中文/全角标点被 shell 编码层改写
  ⇒ 正则与字符串"看起来一样却不匹配"。本脚本全程在**文件内**操作中文，不经 shell。
★ 正则只用 `[0-9]`，全文零反斜杠。

流程：插入 → 写盘 → **在进程内 reload 自测**（3 例）→ 不通过自动回退 → 通过则打印结果。
"""
import importlib
import io
import os
import shutil
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
P = os.path.join(ROOT, "tools", "audit_consistency.py")
BAK = os.path.join(ROOT, "scripts", "_bk_audit_gate_trunc.py")

HELPER_LINES = [
    "def _trunc_violations(_text):",
    "    \"\"\"返回「声明项数 > 可见名数 且 未声明总数」的违规列表。",
    "",
    "    ★ 2026-10-04（疑点4 D8 收尾）：原先三处一律只列前 6 个材料名且**静默**",
    "      （实测 seq=9 声明 8 项、只列 6 名）⇒ 读者以为只有 6 项。",
    "      产品侧已用 `_brief_atoms()` 加「等（共N项）」；本函数是它的**自动守护**。",
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

CALL_LINES = [
    "                    # ★ 2026-10-04（疑点4 D8 收尾）：**截断必须声明总数**（自动守护）。",
    "                    for _d9, _v9 in _trunc_violations(_T8):",
    "                        issues.append(('ERROR', 'enterprise_readable_report',",
    "                                       '声明%d项但只列%d个名且未声明总数 seq=%s（静默截断）'",
    "                                       % (_d9, _v9, _p8.get('seq'))))",
]

ANCHOR = "            except Exception as _e8:"

shutil.copy2(P, BAK)
try:
    raw = io.open(P, "r", encoding="utf-8", newline="").read()
    had = CRLF in raw
    t = raw.replace(CRLF, NL)
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
        lines[fn_start:fn_start] = HELPER_LINES
        t = NL.join(lines)
        if t.count(ANCHOR) != 1:
            print("!! 调用锚点命中 %d ⇒ 回退" % t.count(ANCHOR))
            shutil.copy2(BAK, P)
            sys.exit(2)
        t = t.replace(ANCHOR, NL.join(CALL_LINES + [ANCHOR]), 1)
        io.open(P, "w", encoding="utf-8", newline="").write(
            t.replace(NL, CRLF) if had else t)
        print("OK 闸门已插入")

    # ── 进程内自测（reload 取新函数）──
    sys.path.insert(0, ROOT)
    if "tools.audit_consistency" in sys.modules:
        del sys.modules["tools.audit_consistency"]
    import tools.audit_consistency as A
    importlib.reload(A)
    f = A._trunc_violations
    T1 = f("共需8项（c、d、e、f、g、h）")                      # 静默截断 ⇒ [(8,6)]
    T2 = f("其中8项已提供（c、d、e、f、g、h等（共8项））")      # 已声明 ⇒ []
    T3 = f("其中2项已提供（c、d）")                            # 未截断 ⇒ []
    T4 = f("确未提供的有3项（退货单、折让协议、拒收证明）")        # 刚好 ⇒ []
    print("=== 自测 ===")
    print("  T1 静默截断 =", T1, "(期望 [(8, 6)])")
    print("  T2 已声明总数 =", T2, "(期望 [])")
    print("  T3 未截断 =", T3, "(期望 [])")
    print("  T4 刚好 =", T4, "(期望 [])")
    ok = (T1 == [(8, 6)]) and (T2 == []) and (T3 == []) and (T4 == [])
    print("自测", "通过" if ok else "未通过")
    if not ok:
        shutil.copy2(BAK, P)
        print("已回退闸门文件")
        sys.exit(3)
except Exception as exc:
    shutil.copy2(BAK, P)
    print("!! 异常并已回退：", exc)
    raise
finally:
    if os.path.exists(BAK):
        try:
            os.remove(BAK)
        except Exception:
            pass
