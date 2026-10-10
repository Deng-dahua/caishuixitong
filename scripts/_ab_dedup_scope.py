# -*- coding: utf-8 -*-
"""只读 A/B：在**同一份去重前快照**上对比不同去重范围的效果（P0-2 决策依据）。

快照 `scripts/four_reports/_pre_dedup_snapshot.json` 取自
`report_dedup.dedup_report`（第 1 轮）**之后**、`report_pipeline.dedup_report_data`（第 2 轮）**之前**。

产出：整体重复率 + 段落塌陷数 + 自引用数 + 指向不符数，供"范围统一"前后对比。
"""
import sys, os, json, io, re, copy, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from engine import output_variants as ov
from engine.dedup_pipeline import duplicate_rate
from engine import report_pipeline as rp

SNAP = "scripts/four_reports/_pre_dedup_snapshot.json"
REF = re.compile(r"〔见[^〕]*〕")


def rate_of(data):
    t = ov.report_text_from(data)
    if not t.strip():
        return None, None
    r = duplicate_rate(t.split("\n"))
    return r["整体"]["重复率"], r


def ref_stats(data):
    """塌陷段数 / 自引用数（引用编号 == 所属疑点编号）。"""
    er = data.get("enterprise_readable_report") or {}
    probs = [p for p in (er.get("confirmed_problems") or []) if isinstance(p, dict)]
    collapsed = []
    selfref = 0
    total_ref = 0
    for p in probs:
        seq = p.get("seq")
        for para in (p.get("narrative_paragraphs") or []):
            if not isinstance(para, dict):
                continue
            t = str(para.get("text") or "")
            refs = REF.findall(t)
            total_ref += len(refs)
            if refs and not REF.sub("", t).strip():
                collapsed.append((seq, str(para.get("heading"))[:20]))
            selfref += sum(1 for r in refs if ("R%s〕" % seq) in r)
    return collapsed, selfref, total_ref


pre = json.load(io.open(SNAP, encoding="utf-8"))
r0, _ = rate_of(pre)
print("【快照本体】= 第 1 轮（report_dedup）之后、第 2 轮之前")
print("   整体重复率 = %s" % ("%.2f%%" % (r0 * 100) if r0 else "NA"))
c, s, tr = ref_stats(pre)
print("   塌陷段 %d ｜ 自引用 %d ｜ 引用串 %d" % (len(c), s, tr))

after = copy.deepcopy(pre)
_, log = rp.dedup_report_data(after)
r1, _ = rate_of(after)
c2, s2, tr2 = ref_stats(after)
print("\n【当前第 2 轮（现状）】")
print("   整体重复率 = %.2f%%   塌陷段 %d ｜ 自引用 %d ｜ 引用串 %d ｜ 处理 %d 条"
      % (r1 * 100, len(c2), s2, tr2, len(log)))
print("   塌陷明细：%s" % sorted(c2)[:30])
