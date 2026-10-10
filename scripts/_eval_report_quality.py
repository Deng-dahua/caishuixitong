# -*- coding: utf-8 -*-
"""只读评估脚本：对实渲染报告做「去重 / 逻辑 / 证据」量化体检。
用法: ./.venv/Scripts/python.exe scripts/_eval_report_quality.py
不修改任何文件；全部结论打印为可复核数字。
"""
import io
import json
import os
import re
import sys
from difflib import SequenceMatcher

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")

REPORT = os.path.join(ROOT, "scripts", "four_reports", "company_1_full.json")
TXT = os.path.join(ROOT, "output", "评估用_报告文本_20261008.txt")

d = json.load(io.open(REPORT, encoding="utf-8"))
er = d.get("enterprise_readable_report") or d
probs = [p for p in (er.get("confirmed_problems") or []) if isinstance(p, dict)]

print("=" * 78)
print("A. 疑点级去重（finding 之间是否重复）")
print("=" * 78)


def _find_text(p):
    parts = [str(p.get("title") or "")]
    for para in (p.get("narrative_paragraphs") or []):
        parts.append(str((para or {}).get("heading") or ""))
        parts.append(str((para or {}).get("text") or ""))
    return "\n".join(parts)


texts = [_find_text(p) for p in probs]
titles = [str(p.get("title") or "")[:34] for p in probs]

# A1 标题是否唯一
norm_t = [re.sub(r"\s+", "", t) for t in titles]
dup_t = [t for t in set(norm_t) if norm_t.count(t) > 1]
print("A1 标题唯一性: %d 个疑点 / 重复标题 %d 组 %s" % (
    len(probs), len(dup_t), dup_t or "无"))

# A2 全文两两相似度（>0.6 视为高重合）
print("\nA2 两两全文相似度 >=0.60 的疑点对：")
pairs = []
for i in range(len(texts)):
    for j in range(i + 1, len(texts)):
        r = SequenceMatcher(None, texts[i], texts[j]).ratio()
        if r >= 0.60:
            pairs.append((r, i + 1, j + 1))
for r, i, j in sorted(pairs, reverse=True):
    print("   %.3f  疑点%d <-> 疑点%d" % (r, i, j))
print("   合计 %d 对" % len(pairs))


def sents(t):
    return [s.strip() for s in re.split(r"[。！？；\n]+", t) if len(s.strip()) >= 14]


# A3 跨疑点逐字重复句
print("\nA3 跨疑点『逐字重复』的长句（>=14字，出现在 >=3 个疑点）：")
sent_map = {}
for idx, t in enumerate(texts, 1):
    for s in set(sents(t)):
        sent_map.setdefault(s, set()).add(idx)
cross = [(s, ids) for s, ids in sent_map.items() if len(ids) >= 3]
cross.sort(key=lambda x: -len(x[1]))
for s, ids in cross[:15]:
    print("   x%-2d %s" % (len(ids), s[:62]))
print("   合计 %d 句" % len(cross))

print("\n" + "=" * 78)
print("B. 疑点『内部』内容去重（同一疑点里是否自我重复）")
print("=" * 78)
in_dup_total = 0
for idx, t in enumerate(texts, 1):
    ss = sents(t)
    seen = {}
    for s in ss:
        seen[s] = seen.get(s, 0) + 1
    rep = {s: n for s, n in seen.items() if n > 1}
    if rep:
        in_dup_total += sum(n - 1 for n in rep.values())
        print("   疑点%2d: %d 句重复（去重后多余 %d 句）" % (
            idx, len(rep), sum(n - 1 for n in rep.values())))
        for s, n in list(rep.items())[:3]:
            print("        x%d  %s" % (n, s[:56]))
print("   合计：%d 个疑点存在自我重复，冗余句 %d 处" % (
    sum(1 for t in texts if any(v > 1 for v in
        {s: sents(t).count(s) for s in set(sents(t))}.values())), in_dup_total))

print("\n" + "=" * 78)
print("C. 引用主导段（同一个人看得到『〔见疑点Rn〕』代替正文）")
print("=" * 78)
ref_re = re.compile(r"〔见[^〕]*〕")
bad_items = 0
bad_paras = 0
for idx, p in enumerate(probs, 1):
    n = 0
    for para in (p.get("narrative_paragraphs") or []):
        t = str((para or {}).get("text") or "")
        if not t:
            continue
        refs = ref_re.findall(t)
        if refs and len("".join(refs)) >= max(12, len(t) * 0.6):
            n += 1
    if n:
        bad_items += 1
        bad_paras += n
        print("   疑点%2d『%s』引用主导段 %d/%d" % (
            idx, titles[idx - 1], n, len(p.get("narrative_paragraphs") or [])))
print("   受影响疑点 %d/%d，引用主导段合计 %d" % (bad_items, len(probs), bad_paras))

print("\n" + "=" * 78)
print("D. 逻辑一致性（等级 / 结论 / 金额 是否自相矛盾）")
print("=" * 78)
from collections import Counter
lv = Counter(str(p.get("risk_level") or p.get("level") or "?") for p in probs)
print("D1 风险等级分布:", dict(lv))
for idx, p in enumerate(probs, 1):
    blob = texts[idx - 1]
    lvl = str(p.get("risk_level") or p.get("level") or "")
    # 结论里说"可能性低/中等" 却又评"高风险"
    m = re.search(r"可能性(高|中等|低)", blob)
    if m and lvl:
        hi = ("高" in lvl)
        low = (m.group(1) == "低")
        if hi and low:
            print("   ⚠ 疑点%2d 评为『%s』但正文写『可能性低』" % (idx, lvl))
    # 未认定要件 + 判"已查明的风险"
    if "未认定到任何一条构成要件" in blob and "已查明的风险" in blob:
        print("   ⚠ 疑点%2d 同时出现『未认定到任何一条构成要件』与『已查明的风险』" % idx)

print("\nD2 同一金额在多少个疑点里被当作本项金额：")
amt_map = {}
for idx, p in enumerate(probs, 1):
    for m in re.findall(r"([0-9][0-9,]{6,}\.\d{2})", texts[idx - 1]):
        amt_map.setdefault(m, set()).add(idx)
shared = sorted(((a, ids) for a, ids in amt_map.items() if len(ids) >= 3),
                key=lambda x: -len(x[1]))
for a, ids in shared[:10]:
    print("   %-16s 出现在疑点 %s" % (a, sorted(ids)))
print("   合计 %d 个金额跨 >=3 个疑点重复出现" % len(shared))

print("\n" + "=" * 78)
print("E. 体量与信息密度")
print("=" * 78)
print("E1 报告纯文本字符: %d" % len(io.open(TXT, encoding="utf-8").read()))
tot = sum(len(t) for t in texts)
print("E2 16 个疑点正文合计字符: %d（均 %.0f/疑点）" % (tot, tot / max(1, len(texts))))
# 套话密度
boiler = ["本项之所以列入检查", "不作定性", "不构成违法认定", "须由税务机关依法认定",
          "不足以排除", "既不认定违法，也不予排除", "补充资料", "证据不足"]
for b in boiler:
    c = sum(texts[i].count(b) for i in range(len(texts)))
    print("   『%s』x%d" % (b, c))
