# -*- coding: utf-8 -*-
"""全量扫描：把 5 类缺陷在**当前 26 个疑点**里的实际分布打出来（只读）。

扫的是产物 + 引擎行为两层：
  · 产物层：缺料清单项数自洽、声明项数=列出名数、§五要补项∈要件数据源、证据明细表缺失、
    环节读数重复、"声称未提供某资料"与实际数据矛盾。
  · 引擎层：对 RL-INC-002（疑点4）单跑 `build_evidence_chain`，看幽灵资料名是否仍会产生。
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, os.getcwd())
ROOT = os.getcwd()
D = json.load(io.open(os.path.join(ROOT, "scripts", "four_reports",
                                  "company_1_full.json"), "r", encoding="utf-8"))
ER = D.get("enterprise_readable_report") or {}
CP = ER.get("confirmed_problems") or []
rd = ((D.get("comprehensive") or {}).get("redline_detection") or {})

print("疑点总数 =", len(CP))
print("")

res = {}


def add(k, n, detail=""):
    res.setdefault(k, [0, []])
    res[k][0] += 1
    if detail:
        res[k][1].append(detail)


for p in CP:
    seq = p.get("seq")
    T = json.dumps(p, ensure_ascii=False)
    # ── D8-① 项数自洽：同类 + 另有 + 确未提供 == 总数 ──
    m_need = re.search(r"需要\s*(\d+)\s*项", T)
    parts = [int(m.group(1)) for m in (re.search(r"(\d+)\s*项已提供同类", T),
                                       re.search(r"另有\s*(\d+)\s*项", T),
                                       re.search(r"确未提供的有\s*(\d+)\s*项", T)) if m]
    if m_need and parts:
        tot = int(m_need.group(1))
        if sum(parts) != tot:
            add("D8-① 项数不自洽", 1, "seq=%s 需要%s 但 %s=%d" % (
                seq, tot, "+".join(str(x) for x in parts), sum(parts)))
    # ── D8-② 声明项数 = 列出名数 ──
    for m in re.finditer(r"确未提供的有\s*(\d+)\s*项（([^）]*)）", T):
        nm = [x for x in re.split(r"[、，,；;／/]|与|和|及|或者", m.group(2)) if x.strip()]
        if len(nm) != int(m.group(1)):
            add("D8-② 声明≠名数", 1, "seq=%s 声明%s 实际%d" % (seq, m.group(1), len(nm)))
    # ── D10 幽灵资料名 ──
    srcs = []
    for np_ in (p.get("narrative_paragraphs") or []):
        for tb in (np_.get("detail_tables") or []):
            if "独立核对表" in str((tb or {}).get("title") or ""):
                for r in ((tb or {}).get("rows") or []):
                    srcs.append(str(r.get("独立数据源") or ""))
    for x in (p.get("missing_materials") or []):
        if srcs and not any(str(x) in s or s in str(x) for s in srcs):
            add("D10 幽灵资料名", 1, "seq=%s %s" % (seq, x))
    # ── D11 §五要补项 ∈ 要件数据源 ──
    sug = str(p.get("suggestion") or "")
    for a in re.findall(r"补充提供\s*([^；。、，]{2,20})", sug):
        if srcs and not any(a in s or s in a for s in srcs):
            add("D11 要补项不在要件数据源", 1, "seq=%s %s" % (seq, a))
    # ── D5 证据明细表缺失 ──
    tabs = []
    if (p.get("detail_table") or {}).get("rows"):
        tabs.append(str((p.get("detail_table") or {}).get("title") or ""))
    for np_ in (p.get("narrative_paragraphs") or []):
        for tb in (np_.get("detail_tables") or []):
            tabs.append(str((tb or {}).get("title") or ""))
        dt = np_.get("detail_table") or {}
        if dt.get("rows"):
            tabs.append(str(dt.get("title") or ""))
    if tabs and not [x for x in tabs if "证据" in x and "核对" not in x]:
        add("D5 无证据明细表", 1, "seq=%s 仅有：%s" % (seq, "、".join(tabs)[:40]))

# ── D6/D3 在 redline_detection 层（环节链）──
seen_rid = set()
for k in ("suspicions", "unconfirmed"):
    for it in (rd.get(k) or []):
        rid = it.get("redline_id")
        if rid in seen_rid:
            continue
        seen_rid.add(rid)
        nodes = (it.get("clue_chain") or {}).get("nodes") or []
        obs = [str(n.get("observed") or "").strip() for n in nodes]
        obs = [o for o in obs if o]
        if len(obs) != len(set(obs)):
            dup = [o for o in set(obs) if obs.count(o) > 1]
            add("D6 环节读数重复", 1, "%s 重复：%s" % (rid, str(dup)[:46]))
        for o in obs:
            if ("未提供" in o or "未取得" in o) and ("流水" in o or "明细" in o):
                add("D3 声称缺资料（需核对是否与实际矛盾）", 1, "%s %s" % (rid, o[:40]))

print("=== 各类缺陷当前分布 ===")
if not res:
    print("  全部 5 类均未发现")
for k in sorted(res):
    n, det = res[k]
    print("  %-28s %3d 处" % (k, n))
    for d2 in det[:3]:
        print("        %s" % d2)

# ── 引擎层：RL-INC-002 单跑，看幽灵名是否仍会产生 ──
print("")
print("=== 引擎层验证（RL-INC-002 / 疑点4）===")
try:
    from engine.tax_redlines import get_redline
    from engine.evidence_chain import build_evidence_chain
    rl = get_redline("RL-INC-002") or {}
    syn = {"type": "公私混同", "detail": "个人账户收取经营性款项", "supporting_evidence": [],
           "opposing_evidence": [], "reasonable_explanations": []}
    ev = build_evidence_chain(syn, rl, ["银行流水", "记账凭证"], {"industry": "广告传媒"})
    print("  证据项：", [e.get("name") for e in (ev.get("elements") or [])][:4])
    print("  missing_materials      =", json.dumps(ev.get("missing_materials"), ensure_ascii=False)[:60])
    print("  missing_material_names =", json.dumps(ev.get("missing_material_names"), ensure_ascii=False)[:70])
    srcs = [str(c.get("name") or "") for c in (rl.get("constituent_sources") or [])]
    print("  红线声明的要件数据源 =", json.dumps(srcs, ensure_ascii=False)[:90])
    ghost = [x for x in (ev.get("missing_materials") or [])
             if not any(str(x) in s for s in srcs)]
    print("  幽灵资料名 =", ghost or "无")
except Exception as exc:
    print("  引擎层验证异常：", exc)
