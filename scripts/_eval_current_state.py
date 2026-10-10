# -*- coding: utf-8 -*-
"""对**当前冻结产物**做一次全面体检（只读），覆盖用户问到的每个维度。

输出：
  A 结构/计数
  B 去重三层（疑点间 / 疑点内 / 跨疑点引用）
  C 金额与税额口径
  D 逻辑自洽（矛盾句 / 残句 / 占位符 / 粘连）
  E 企业补救（自证清白）覆盖
"""
import sys, os, json, io, re
from collections import Counter
ROOT = r"c:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong"
os.chdir(ROOT); sys.path.insert(0, ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ART = 'scripts/four_reports/_eval_frozen_2245.json'
d = json.load(open(ART, encoding='utf-8'))
er = d.get('enterprise_readable_report') or {}
probs = [p for p in (er.get('confirmed_problems') or []) if isinstance(p, dict)]
TXT = open('output/评估用_报告文本_当前.txt', encoding='utf-8').read()

REF = re.compile(r"〔见疑点R(\d+)〕")

print("=" * 78)
print("A 结构 / 计数")
print("=" * 78)
print("风险事项数 =", len(probs))
lv = Counter(str(p.get('risk_level') or '') for p in probs)
print("等级分布 =", dict(lv))
titles = [str(p.get('title') or '') for p in probs]
print("标题唯一性：%d 个 / 重复 %d 组" % (len(titles), len(titles) - len(set(titles))))
narr = sum(len(p.get('narrative_paragraphs') or []) for p in probs)
print("叙述小节总数 =", narr)

print()
print("=" * 78)
print("B 去重（三层）")
print("=" * 78)
# B1 疑点间标题唯一
print("B1 疑点间（标题）：唯一 %d / %d" % (len(set(titles)), len(titles)))
# B2 疑点内自我重复（连续两次相同引用）
selfdup = re.findall(r"(〔见疑点R\d+〕)\1", TXT)
print("B2 疑点内：连续重复引用 %d 处" % len(selfdup))
# B3 跨疑点引用：整段只剩引用 = 空白小节
pure = []
dom = []
for p in probs:
    seq = p.get('seq')
    for np in (p.get('narrative_paragraphs') or []):
        if not isinstance(np, dict):
            continue
        t = str(np.get('text') or '')
        if not t.strip():
            continue
        refs = REF.findall(t)
        stripped = REF.sub('', t).strip()
        if refs and not stripped:
            pure.append((seq, str(np.get('heading')), t))
        elif refs and len(t) >= 30 and sum(len(x) for x in REF.findall(t)) >= len(t) * 0.4:
            dom.append((seq, str(np.get('heading')), t))
print("B3 跨疑点：整段只剩引用（内容归零） %d 处；引用主导(>=40%%) %d 处" % (len(pure), len(dom)))
for seq, h, t in pure:
    print("    空白小节：R%s /%s/" % (seq, h))
# B3b 引用指向是否相关/自引用
selfref = 0
misdir = []
for p in probs:
    seq = p.get('seq')
    blob = json.dumps(p, ensure_ascii=False)
    for m in set(REF.findall(blob)):
        if int(m) == seq and ('自引用' if False else True):
            selfref += 1
print("B3b 引用总数 = %d；自引用(见疑点Rn 出现在 Rn 自己里) = %d" % (TXT.count('〔见疑点'), selfref))
# 报告级重复率
print("报告自报重复率：去重前 %s → 去重后 %s（阈值 整体≤10%%）"
      % (d.get('_dedup_rate_before'), d.get('_dedup_rate_after')))
print("主话语元（系统自述）残留 =", len(re.findall(r"本段是系统|系统不对企业的解释作预判", TXT)))

print()
print("=" * 78)
print("C 金额 / 税额口径")
print("=" * 78)
tot = re.search(r"本轮潜在税额敞口（测算）：合计约 ([\d,\.]+) 元", TXT)
print("敞口合计 =", tot.group(1) if tot else "(未找到)")
for p in probs:
    ti = p.get('tax_impact') or {}
    if not ti.get('available'):
        continue
    items = [(i.get('tax'), i.get('amount'), i.get('rate')) for i in (ti.get('items') or [])]
    ttl = ti.get('total')
    if ttl and ttl > 100000:
        print("  R%-3s basis=%-14s total=%-14s items=%s" % (p.get('seq'), ti.get('basis'), ttl, items))
print("含『≈—元』破折号占位的小节 =", len(re.findall(r"≈—元", TXT)))
print("含『合计≈0.00元』但单项缺失 =", len(re.findall(r"合计≈0\.00元", TXT)))

print()
print("=" * 78)
print("D 逻辑自洽 / 表述")
print("=" * 78)
print("残句『本企业本项已查明的风险；』 =", TXT.count('本企业本项已查明的风险'))
print("『可能性低』与『高风险』同项并存候选：")
for p in probs:
    blob = json.dumps(p, ensure_ascii=False)
    if '可能性低' in blob and str(p.get('risk_level')) == '高风险':
        print("    R%s 等级=高风险，正文含『可能性低』" % p.get('seq'))
print("『办理顺序：第』粘连 =", TXT.count('办理顺序：第'))
lowsim = [t for t in titles if len(t) > 40]
print("超长标题(内嵌推理) =", len(lowsim))
for t in lowsim[:5]:
    print("    %s" % t[:90])

print()
print("=" * 78)
print("E 企业补救（自证清白）")
print("=" * 78)
sd = sum(1 for p in probs if p.get('self_doubt'))
print("有『可能错在哪里/验证清单』的疑点 = %d / %d" % (sd, len(probs)))
print("『可自证清白』出现 =", TXT.count('可自证清白'))
print("『推翻条件』出现 =", TXT.count('推翻条件'))
qs = er.get('inspection_questions_report') or {}
print("询问清单 available =", qs.get('available'), "；条数 =", len(qs.get('questions') or qs.get('items') or []) if isinstance(qs, dict) else '')
print("询问清单是否单独成章（含『需企业澄清的问题』标题）= %d" % TXT.count('需企业澄清的问题'))
