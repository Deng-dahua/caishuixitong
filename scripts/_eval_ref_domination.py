# -*- coding: utf-8 -*-
"""只读：精确统计「正文被引用语吃掉」的段落（不设下限，逐段分类）。
用法: ./.venv/Scripts/python.exe scripts/_eval_ref_domination.py
"""
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")

REF = re.compile(r"〔见[^〕]*〕")
d = json.load(io.open("scripts/four_reports/company_1_full.json", encoding="utf-8"))
er = d.get("enterprise_readable_report") or d
probs = [p for p in (er.get("confirmed_problems") or []) if isinstance(p, dict)]

pure, dom, ok = [], [], []
for p in probs:
    seq = p.get("seq")
    title = str(p.get("title") or "")[:26]
    for para in (p.get("narrative_paragraphs") or []):
        if not isinstance(para, dict):
            continue
        head = str(para.get("heading") or "").strip()
        t = str(para.get("text") or "")
        stripped = REF.sub("", t).strip()
        refs = REF.findall(t)
        nref = len(refs)
        ref_chars = sum(len(x) for x in refs)
        if not t.strip():
            continue
        if nref and not stripped:
            pure.append((seq, title, head, nref, t[:60]))
        elif nref and len(t) >= 30 and ref_chars >= len(t) * 0.40:
            dom.append((seq, title, head, nref, len(t), ref_chars, t[:70]))
        else:
            ok.append(1)

print("总段落 %d ｜ 正常 %d ｜ 纯引用(整段只剩引用) %d ｜ 引用主导(>=40%%) %d"
      % (len(pure) + len(dom) + len(ok), len(ok), len(pure), len(dom)))

print("\n=== ① 整段只剩引用（该小节内容=0，读者看不到任何信息）===")
by_item = {}
for seq, title, head, nref, snip in pure:
    by_item.setdefault(seq, []).append((head, nref))
for seq in sorted(by_item, key=lambda x: (x is None, x)):
    t = next((x[1] for x in pure if x[0] == seq), "")
    print("  疑点R%s『%s』" % (seq, t))
    for head, nref in by_item[seq]:
        print("      - %-22s 全文=%s" % (head, "〔见疑点Rn〕×%d" % nref))
print("  → 受影响疑点 %d 个，空白小节 %d 处" % (len(by_item), len(pure)))

print("\n=== ② 引用主导段（>=40% 字符是引用，正文被压缩）===")
for seq, title, head, nref, ln, rc, snip in dom:
    print("  疑点R%s『%s』/ %s：引用%d处 占 %d/%d 字符" % (seq, title, head, nref, rc, ln))
print("  → %d 处" % len(dom))

# 关键小节（结论/依据/风险事项）是否受损
KEY = ("结论", "依据", "风险事项", "需企业提供", "资料")
hit_key = [(s, t, h) for s, t, h, *_ in pure + dom if any(k in h for k in KEY)]
print("\n=== ③ 受损小节里，属『关键小节』的（结论/依据/风险事项/资料）===")
for s, t, h in hit_key:
    print("  疑点R%s『%s』→ %s" % (s, t, h))
print("  → %d 处关键小节被引用吃掉" % len(hit_key))
