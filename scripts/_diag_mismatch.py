# -*- coding: utf-8 -*-
"""逐条体检：疑点主体 ↔（① 附表 ② 明细行 ③ 自身支撑发现）是否同一件事。

★ 口径说明（本脚本改版的原因）：
  初版用「汉字 2-gram 相关性」当判据，结果**两种错误同时发生**：
    · 真配对被误判为错配（如 RL-PTY-001「成本列支的资金与负债证据不足」＋
      「表1 主营成本总额·按供应商分布 / 表2 已付金额 / 表4 应付账款核对」，
      语义完全对口、字面重叠 0.00~0.05）；
    · 用词相近的错配反而"看起来相关"。
  根因：文字相似度 ≠ 主体同一。现改用**来源归属**（附表来自哪条发现，该发现是不是
  本疑点声明的支撑发现）为主判据 —— 这在源码里本就是权威（`supporting_findings`），
  只是报告挂表时没走它。

判定口径与报告一致：唯一权威 `engine/subject_consistency`。
输出三堆：
  A. 附表来源不在本疑点支撑发现内        → 真错配（挂错表）
  B. 明细行与本项主体无共同主题词        → 需人工确认（可能错配）
  C. 疑点主体与支撑发现不是同一件事      → 归属层错配（根因在红线归属）
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from engine.subject_consistency import (  # noqa: E402
    norm_subject_key, same_subject, table_source_ok, suspicion_subject_ok,
)

PATH = sys.argv[1] if len(sys.argv) > 1 else 'scripts/four_reports/_fresh_result.json'
d = json.load(open(PATH, encoding='utf-8'))
rep = d.get('report', d)
cps = ((rep.get('enterprise_readable_report') or {}).get('confirmed_problems')) or []
findings = ((rep.get('scenario_execution') or {}).get('findings')
            or rep.get('all_findings') or [])
suspicions = ((rep.get('comprehensive') or {}).get('redline_detection') or {}).get('suspicions') or []

# 发现 → 明细表（按主体规范键索引；同一键取首条，与报告同口径）
# 另建「表题 → 来源主体键」：显式下钻表（表1/表2…）的标题不等于发现类型，
# 必须回溯到"这张表由哪条发现产出"，否则会把自己的表误判成外来表。
SRC = {}
TITLE_OWNER = {}
for f in findings:
    if not isinstance(f, dict):
        continue
    if str(f.get('type') or '').strip().startswith('资料缺失'):
        continue
    k = norm_subject_key(f.get('type'))
    if not k:
        continue
    tabs = [t for t in (f.get('detail_tables') or []) if isinstance(t, dict) and t.get('rows')]
    if not tabs and f.get('evidence_rows'):
        tabs = [{'title': str(f.get('type') or ''), 'rows': f.get('evidence_rows')}]
    if tabs and k not in SRC:
        SRC[k] = tabs
    for t in tabs:
        # 报告出口会把值里的半角标点规范成全角（`·`→`，`），故按"只留中文/字母数字"
        # 的规范键建立映射，避免同一张表因标点差异被判成"外来表"。
        TITLE_OWNER.setdefault(norm_subject_key((t or {}).get('title')), k)

SUS = {}
for s in suspicions:
    SUS[str(s.get('redline_id') or '')] = s

print("=" * 112)
print("逐条体检（判据：来源归属＝附表所属发现 是否为本疑点声明的支撑发现；主体词＝去泛化主题词）")
print("=" * 112)
cnt = {'A': 0, 'B': 0, 'C': 0}
for i, c in enumerate(cps):
    title = str(c.get('title') or '')
    sus = None
    _tkey = norm_subject_key(title)
    for r, s in SUS.items():
        _nkey = norm_subject_key(s.get('redline_name'))
        if _nkey and (_nkey in _tkey or _tkey.startswith(_nkey)):
            sus = s
            break
    sup = []
    if sus:
        if str(sus.get('finding_type') or '').strip():
            sup.append(str(sus['finding_type']).strip())
        for f in (sus.get('supporting_findings') or []):
            if isinstance(f, dict) and str(f.get('type') or '').strip():
                sup.append(str(f['type']).strip())
    sup_keys = {norm_subject_key(x) for x in sup}
    sup_keys.discard('')
    probs = []
    if not sup:
        probs.append(('C?', '本疑点取不到支撑发现（无从判定）'))
    else:
        ok, why = suspicion_subject_ok(
            str(sus.get('redline_name') or ''), sup, sus.get('redline_id'))
        if not ok:
            probs.append(('C', '%s｜支撑：%s' % (why[:70], '、'.join(sorted(sup))[:60])))
    for p in (c.get('narrative_paragraphs') or []):
        for dt in (p.get('detail_tables') or []):
            ttl = str(dt.get('title') or '')
            # 系统自产表（要件独立核对表）不属于任何发现，不参与来源归属判定
            if ttl.startswith('构成要件独立核对表'):
                continue
            src_key = TITLE_OWNER.get(norm_subject_key(ttl)) or norm_subject_key(ttl)
            if not sup_keys:
                continue
            ok, why = table_source_ok(sup_keys, src_key or ttl)
            if not ok:
                probs.append(('A', '%s｜%s' % (ttl[:34], why[:60])))
            cells = []
            for x in (dt.get('rows') or [])[:12]:
                for kk in ('对方单位', '凭证/单据标识', '品名', '证据名称', '构成要件', '风险事项'):
                    v = str((x or {}).get(kk) or '').strip()
                    if v:
                        cells.append(v)
            if cells and not any(same_subject(v, title) for v in cells[:24]):
                probs.append(('B', '明细行与本项主体无共同主题词（样本：%s）'
                              % '、'.join(cells[:3])[:46]))
    if probs:
        print(f"\n[{i}] {title[:56]}")
        for tag, msg in probs:
            cnt[tag[0]] += 1
            print(f"   [{tag}] {msg}")
print("\n统计：附表挂错(A)=%d  行存疑(B)=%d  主体错配(C)=%d" % (cnt['A'], cnt['B'], cnt['C']))
