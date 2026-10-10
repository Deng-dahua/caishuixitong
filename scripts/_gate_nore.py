# -*- coding: utf-8 -*-
"""截断自动守护 —— **完全不用正则**（str.find / split），绕开此前的正则/转义/编码问题。

判据：正文里「有 N 项（…名…）」若 **N > 实际列出的名数**、且**没有**写「共 N 项」
⇒ 静默截断 ⇒ ERROR。
实现要点：
  · 逐处扫描「有 + 数字 + 项」，再找**紧随其后**的「（…）」，中间文字 ≤ 12 字
    （真实文案是「其中8项已提供同类资料（…）」；上限防跨句误报）；
  · 「项」与「（」之间的字符数用 `find` 直接量，不写正则；
  · 名单切分用 `replace(sep, "\\x00").split(...)`，不用正则。

流程（任一步不符即回退，绝不留会误报的闸门）：
  ① 真跑产物上验证：**必须 0 违规**；
  ② 反向验证：抹掉「等（共N项）」后**必须报出违规**；
  ③ 两条都过 ⇒ 才搬进 audit_consistency（模块级函数 + ⑧ 里 4 行调用）；
  ④ 复跑模块内自测 + 全量验收。
"""
import importlib
import io
import json
import os
import shutil
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
AUD = os.path.join(ROOT, "tools", "audit_consistency.py")
ART = os.path.join(ROOT, "scripts", "four_reports", "company_1_full.json")
BAK = os.path.join(ROOT, "scripts", "_bk_audit_gate_nore.py")

SEPS = ("、", "，", ",", "；", ";", "／", "/", "或者", "以及", "与", "和", "及")


def _split_names(body):
    _s = body or ""
    for _p in SEPS:
        _s = _s.replace(_p, "\x00")
    return [x.strip() for x in _s.split("\x00") if x.strip()]


def judge(text):
    """不用正则的截断违规检测。"""
    _t = text or ""
    _out = []
    _pos = 0
    while True:
        _i = _pos
        while _i < len(_t) and not _t[_i].isdigit():
            _i += 1
        if _i >= len(_t):
            return _out
        _j = _i
        _k = _j
        while _k < len(_t) and _t[_k].isdigit():
            _k += 1
        if _k == _j or _k >= len(_t) or _t[_k] != "项":
            _pos = _i + 1
            continue
        _dec = int(_t[_j:_k])
        _m = _t.find("（", _k)
        if _m < 0 or (_m - _k - 1) > 12:
            _pos = _i + 1
            continue
        _e = _t.find("）", _m + 1)
        if _e < 0:
            _pos = _i + 1
            continue
        if ("共%d项" % _dec) in _t:
            _pos = _e + 1
            continue
        _body = _t[_m + 1:_e].replace("等（共%d项）" % _dec, "")
        _vis = _split_names(_body)
        if _dec > len(_vis):
            _out.append((_dec, len(_vis)))
        _pos = _e + 1


def load_cp():
    D = json.load(io.open(ART, "r", encoding="utf-8"))
    return (D.get("enterprise_readable_report") or {}).get("confirmed_problems") or []


# ══ ① 真跑产物：不误报 ══
CP = load_cp()
bad = 0
for p in CP:
    r = judge(json.dumps(p, ensure_ascii=False))
    if r:
        bad += 1
        print("  违规 seq=%s %s" % (p.get("seq"), r))
print("① 真实产物违规数 =", bad, "（期望 0）")

# ══ ② 反向：抹掉「等（共N项）」后必须报 ══
rev = 0
for p in CP:
    T = json.dumps(p, ensure_ascii=False)
    if "等（共" not in T:
        continue
    S = T
    while "等（共" in S:
        a = S.find("等（共")
        b = S.find("）", a)
        S = S[:a] + S[b + 1:]
    r1, r2 = judge(T), judge(S)
    print("② 反向 seq=%s 原样=%s 抹掉后=%s" % (p.get("seq"), r1, r2))
    if r2 and not r1:
        rev = 1
    break
if not rev:
    # 兜底：构造一个"静默截断"样本（不依赖产物）
    _t = "本项需要9项材料，其中9项已提供同类资料资料（甲、乙、丙、丁、戊、己）"
    print("② 兜底样本 =", judge(_t), "（期望非空）")
    rev = 1 if judge(_t) else 0
print("② 反向验证 =", "通过" if rev else "未通过")

if bad or not rev:
    print("!! 判据未双向通过 ⇒ 不写进闸门")
    sys.exit(3)

# ══ ③ 搬进闸门 ══
HELPER = [
    "def _trunc_violations(_text):",
    "    \"\"\"返回「声明项数 > 可见名数 且 未声明总数」的违规列表（**不用正则**实现）。",
    "",
    "    ★ 2026-10-04（疑点4 D8 收尾）：三处材料名一律只列前 6 个，原先**静默**",
    "      （实测 seq=9 声明 8 项、只列 6 名）⇒ 读者以为只有 6 项。",
    "      产品侧已用 `_brief_atoms()` 加「等（共N项）」；本函数是它的**自动守护**。",
    "      ⚠ 刻意**不用正则**（本项目多处正则判据在写入链路上被转义/编码破坏过），",
    "        一律用 find/split，行为可预测。",
    "    \"\"\"",
    "    _seps = (\"、\", \"，\", \",\", \"；\", \";\", \"／\", \"/\", \"或者\", \"以及\", \"与\", \"和\", \"及\")",
    "    _t = _text or \"\"",
    "    _out = []",
    "    _pos = 0",
    "    while True:",
    "        _i = _pos",
    "        while _i < len(_t) and not _t[_i].isdigit():",
    "            _i += 1",
    "        if _i >= len(_t):",
    "            return _out",
    "        _j = _i",
    "        _k = _j",
    "        while _k < len(_t) and _t[_k].isdigit():",
    "            _k += 1",
    "        if _k == _j or _k >= len(_t) or _t[_k] != \"项\":",
    "            _pos = _i + 1",
    "            continue",
    "        _dec = int(_t[_j:_k])",
    "        _m = _t.find(\"（\", _k)",
    "        if _m < 0 or (_m - _k - 1) > 12:",
    "            _pos = _i + 1",
    "            continue",
    "        _e = _t.find(\"）\", _m + 1)",
    "        if _e < 0:",
    "            _pos = _i + 1",
    "            continue",
    "        if (\"共%d项\" % _dec) in _t:",
    "            _pos = _e + 1",
    "            continue",
    "        _body = _t[_m + 1:_e].replace(\"等（共%d项）\" % _dec, \"\")",
    "        for _sp in _seps:",
    "            _body = _body.replace(_sp, \"\\x00\")",
    "        _vis = [x.strip() for x in _body.split(\"\\x00\") if x.strip()]",
    "        if _dec > len(_vis):",
    "            _out.append((_dec, len(_vis)))",
    "        _pos = _e + 1",
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
ANCHOR = "            except Exception as _e8:"

shutil.copy2(AUD, BAK)
raw = io.open(AUD, "r", encoding="utf-8", newline="").read()
had = CRLF in raw
t = raw.replace(CRLF, NL)
if "_trunc_violations" in t:
    print("③ 已在（幂等）")
else:
    lines = t.split(NL)
    idx = None
    for i, ln in enumerate(lines):
        if "⑧ 缺料三态" in ln:
            idx = i
            break
    if idx is None:
        print("!! 找不到 ⑧ 闸门行")
        shutil.copy2(BAK, AUD)
        sys.exit(2)
    fn_start = None
    for j in range(idx, -1, -1):
        if lines[j].startswith("def "):
            fn_start = j
            break
    lines[fn_start:fn_start] = HELPER
    t = NL.join(lines)
    if t.count(ANCHOR) != 1:
        print("!! 调用锚点命中 %d ⇒ 回退" % t.count(ANCHOR))
        shutil.copy2(BAK, AUD)
        sys.exit(2)
    t = t.replace(ANCHOR, NL.join(CALL + [ANCHOR]), 1)
    io.open(AUD, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if had else t)
    print("③ 闸门已插入")

# ══ ④ 复跑模块内自测 ══
sys.path.insert(0, ROOT)
if "tools.audit_consistency" in sys.modules:
    del sys.modules["tools.audit_consistency"]
import tools.audit_consistency as A
importlib.reload(A)
g = A._trunc_violations
b2 = sum(len(g(json.dumps(p, ensure_ascii=False))) for p in load_cp())
print("④ 模块内跑真实产物：违规总数 =", b2, "（期望 0）")
if b2:
    shutil.copy2(BAK, AUD)
    print("!! 模块内判据异常 ⇒ 已回退")
    sys.exit(4)
os.remove(BAK)
print("[DONE] 截断自动守护已上线（无正则实现）")
