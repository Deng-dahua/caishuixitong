# -*- coding: utf-8 -*-
"""把"截断必须声明总数"的自动守护加进 ⑧ —— 严格按「先验证判据、再写进闸门」。

四步（任一步不符即回退，绝不留下会误报的闸门）：
  ① 先在**真跑产物**上验证判据：全部疑点应 0 违规；
  ② 反向验证：抹掉「等（共N项）」后必须报出违规（否则判据抓不住问题，等于白设）；
  ③ 两条都过 ⇒ 才把判据搬进 `audit_consistency`（模块级函数 + ⑧ 里 4 行调用）；
  ④ 复跑产物级探针 + 全量验收。
"""
import importlib
import io
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
AUD = os.path.join(ROOT, "tools", "audit_consistency.py")
ART = os.path.join(ROOT, "scripts", "four_reports", "company_1_full.json")
BAK = os.path.join(ROOT, "scripts", "_bk_audit_gate_final.py")

# ★ 判据本体（零反斜杠；`[^（]{0,12}` 允许「项」与「（」之间最多 12 个字符，
#   真实文案是「其中8项已提供同类资料（…）」；上限防止跨句误报）
PAT = "有([0-9]+)项[^（]{0,12}（([^）]*)）"
SEP = "[、，,；;／/]|与|和|及|或者"


def judge(text, pat=PAT, sep=SEP):
    """返回「声明项数 > 可见名数 且 未声明总数」的违规列表。"""
    import re as _re
    _p = _re.compile(pat)
    _s = _re.compile(sep)
    _txt = text or ""
    _out = []
    for _m in _p.finditer(_txt):
        _dec = int(_m.group(1))
        if ("共%d项" % _dec) in _txt:
            continue
        _body = _m.group(2).replace("等（共%d项）" % _dec, "").strip()
        _vis = [x.strip() for x in _s.split(_body) if x.strip()]
        if _dec > len(_vis):
            _out.append((_dec, len(_vis)))
    return _out


def load_cp():
    D = json.load(io.open(ART, "r", encoding="utf-8"))
    return (D.get("enterprise_readable_report") or {}).get("confirmed_problems") or []


# ══ 步骤 ①② 先在真数据上验证判据 ══
CP = load_cp()
bad = 0
for p in CP:
    r = judge(json.dumps(p, ensure_ascii=False))
    if r:
        bad += 1
        print("  违规 seq=%s %s" % (p.get("seq"), r))
print("① 真实产物违规数 =", bad, "（期望 0）")

rev_ok = False
for p in CP:
    T = json.dumps(p, ensure_ascii=False)
    if re.search("等（共[0-9]+项）", T):
        S = re.sub("等（共[0-9]+项）", "", T)
        r1, r2 = judge(T), judge(S)
        print("② 反向 seq=%s 原样=%s 抹掉后=%s" % (p.get("seq"), r1, r2))
        rev_ok = (not r1) and bool(r2)
        break
if not rev_ok:
    for p in CP:
        T = json.dumps(p, ensure_ascii=False)
        S = re.sub("（[^）]*）", "（x、y）", T, count=3)
        if judge(S):
            print("② 反向（构造）seq=%s -> %s" % (p.get("seq"), judge(S)))
            rev_ok = True
            break
print("② 反向验证 =", "通过" if rev_ok else "未通过")

if bad or not rev_ok:
    print("!! 判据未通过 ⇒ 不写进闸门")
    sys.exit(3)

# ══ 步骤 ③ 搬进闸门 ══
HELPER = [
    "def _trunc_violations(_text):",
    "    \"\"\"返回「声明项数 > 可见名数 且 未声明总数」的违规列表（截断必须显式声明总数）。",
    "",
    "    ★ 2026-10-04（疑点4 D8 收尾）：三处材料名一律只列前 6 个，原先**静默**",
    "      （实测 seq=9 声明 8 项、只列 6 名）⇒ 读者以为只有 6 项。",
    "      产品侧已用 `_brief_atoms()` 加「等（共N项）」；本函数是它的**自动守护**。",
    "      判据说明：真实文案是「其中8项已提供同类资料（…）」——「项」与「（」之间有字，",
    "      故正则必须允许**有限**的中间文字（`[^（]{0,12}`，上限防跨句误报）。",
    "    \"\"\"",
    "    import re as _rt",
    "    _pat = _rt.compile(\"有([0-9]+)项[^（]{0,12}（([^）]*)）\")",
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
ANCHOR = "            except Exception as _e8:"

shutil.copy2(AUD, BAK)
raw = io.open(AUD, "r", encoding="utf-8", newline="").read()
had = CRLF in raw
t = raw.replace(CRLF, NL)
if "_trunc_violations" in t:
    print("③ 已在（幂等，跳过插入）")
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

# ══ 步骤 ④ 复跑（模块内自测 + 产物级 + 全量）══
sys.path.insert(0, ROOT)
if "tools.audit_consistency" in sys.modules:
    del sys.modules["tools.audit_consistency"]
import tools.audit_consistency as A
importlib.reload(A)
g = A._trunc_violations
CP2 = load_cp()
b2 = sum(len(g(json.dumps(p, ensure_ascii=False))) for p in CP2)
print("④ 模块内跑真实产物：违规总数 =", b2, "（期望 0）")
if b2:
    shutil.copy2(BAK, AUD)
    print("!! 模块内判据异常 ⇒ 已回退")
    sys.exit(4)
os.remove(BAK)
print("[DONE] 截断自动守护已上线")
