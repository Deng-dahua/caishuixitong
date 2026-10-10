# -*- coding: utf-8 -*-
"""A/B 取证（只读快照 + 就地重放，不碰正式产物）：
在同一份「去重前」输入上重放 report_pipeline.dedup_report_data，
逐疑点/逐小节对比 **旧算法** 的效果，量化：
  ① 哪些小节被整段替换成引用（内容归零）；
  ② 引用指向哪一项（是否与本项主题相关 / 是否自引用）；
  ③ 计数器 `report_dedup.find_leftover_duplicates` 是否认为这些段"该上提"。
"""
import sys, os, json, io, copy, re
ROOT = r"c:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong"
os.chdir(ROOT); sys.path.insert(0, ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from engine.report_pipeline import dedup_report_data
from engine.report_dedup import is_hoistable_head, find_leftover_duplicates

REF = re.compile(r"〔见疑点R(\d+)〕")

snap = json.load(open('scripts/four_reports/_pre_dedup_snapshot.json', encoding='utf-8'))
pre = copy.deepcopy(snap)
WORK = copy.deepcopy(snap)
_, log = dedup_report_data(WORK)

er_pre = pre.get('enterprise_readable_report') or {}
er_new = WORK.get('enterprise_readable_report') or {}
P0 = [p for p in (er_pre.get('confirmed_problems') or []) if isinstance(p, dict)]
P1 = [p for p in (er_new.get('confirmed_problems') or []) if isinstance(p, dict)]

def paras(p):
    return {str((np or {}).get('heading')): str((np or {}).get('text') or '')
            for np in (p.get('narrative_paragraphs') or []) if isinstance(np, dict)}

pure = []
for a, b in zip(P0, P1):
    seq = a.get('seq')
    da, db = paras(a), paras(b)
    for h, t0 in da.items():
        t1 = db.get(h, '')
        stripped = REF.sub('', t1).strip()
        if REF.search(t1) and not stripped and t0.strip():
            pure.append((seq, h, t0, REF.findall(t1)))

print("=== ① 被整段替换为引用的小节（内容归零）===")
print("共 %d 处，涉及疑点 %d 个" % (len(pure), len({x[0] for x in pure})))
for seq, h, t0, refs in pure:
    tgt = sorted({int(x) for x in refs})
    self_ref = '★自引用' if seq in tgt else ''
    flags = []
    for x in tgt:
        flags.append("R%d%s" % (x, "(本项)" if x == seq else ""))
    print("  R%-3s %-22s → %s %s" % (seq, h[:20], ",".join(flags), self_ref))

print("\n=== ② 计数器 vs 替换器：被替换的小节里，多少是『计数器认为该上提』的？===")
hoistable = 0
for seq, h, t0, refs in pure:
    if is_hoistable_head(h):
        hoistable += 1
print("被整段清空的小节 %d 处；其中标题属『可上提共性段』的 %d 处，"
      "**不属共性段（本项特有）却被清空**的 %d 处"
      % (len(pure), hoistable, len(pure) - hoistable))
for seq, h, t0, refs in pure:
    if not is_hoistable_head(h):
        print("   ✗ 本项特有却清空：R%-3s %s" % (seq, h))

print("\n=== ③ 被清空的『本项特有』小节的原文（去重前）——证明信息确实丢失 ===")
shown = 0
for seq, h, t0, refs in pure:
    if not is_hoistable_head(h) and shown < 6:
        print("  R%s /%s/：%s" % (seq, h, t0[:150].replace(chr(10), ' ')))
        shown += 1

print("\n=== ④ 引用是否指向不相干疑点（专家评估指出的 R4 误指）===")
# 看 material_gap_notes 的替换
for a, b in zip(P0, P1):
    mb = b.get('material_gap_notes') or []
    for g in mb:
        if not isinstance(g, dict):
            continue
        for seg in (g.get('段落') or []):
            if isinstance(seg, dict) and REF.search(str(seg.get('text') or '')):
                print("  R%s 类别=%s /%s/ → %s" % (
                    a.get('seq'), g.get('类别'), str(seg.get('heading'))[:12],
                    str(seg.get('text'))[:40]))
