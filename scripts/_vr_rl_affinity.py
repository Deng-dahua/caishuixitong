# -*- coding: utf-8 -*-
"""VR(73 已验证原子规则) ↔ RL(68 红线) 语义归属核查。

背景（2026-09-29）：RL-FUND-005「银行流水余额滚动不一致」被静态覆盖脚本判为"盲区"，
实际 VR009 就是它的检测器 —— 只是 VR 的 finding 没声明 `redline_id`。
⇒ "无数据路径 35 条"这个数字**被系统性虚高**：把"已实现但未声明归属"算成了"根本没实现"。

本脚本按名称 2-gram 重叠 + 关键词，给出 VR→RL 候选，供人工确认哪些是"漏声明归属"。
静态口径仅供参考；运行态权威见 `_gap_constituent_hits.py`（match_mode + 逐要件 checkpoint）。
"""
import importlib.util, os, re, json, sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(ROOT, "engine")
sys.path.insert(0, ROOT)

from engine import tax_redlines as tr          # noqa: E402
from engine import verified_rule_engine as vre  # noqa: E402

REDLINES = tr.REDLINES
VRS = vre.CATALOG if hasattr(vre, "CATALOG") else None
if VRS is None:
    # 回退：找模块内的规则清单变量
    for k, v in vars(vre).items():
        if isinstance(v, (list, tuple)) and v and isinstance(v[0], dict) and "id" in v[0] and str(v[0]["id"]).startswith("VR"):
            VRS = v
            break

print("VR 规则数:", len(VRS), "| RL 红线数:", len(REDLINES))


def grams(s, n=2):
    s = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", s or "")
    return set(s[i:i + n] for i in range(max(len(s) - n + 1, 1))) if s else set()


# 1) 已声明 redline_id 的 VR（扫源码）
declared = {}
ROOT_FILES = [os.path.join(ENGINE, f) for f in os.listdir(ENGINE) if f.endswith(".py")]
ROOT_FILES.append(os.path.join(ROOT, "main.py"))
pat = re.compile(r'redline_id[^\n]{0,8}?(RL-[A-Z0-9-]+)')
for fp in ROOT_FILES:
    try:
        txt = open(fp, encoding="utf-8").read()
    except Exception:
        continue
    for m in pat.finditer(txt):
        declared.setdefault(m.group(1), set()).add(os.path.basename(fp))

# 2) 每条 VR 的候选 RL（按名称重叠）
rows = []
for v in VRS:
    vid, vname = v.get("id"), v.get("name", "")
    vg = grams(vname)
    cands = []
    for r in REDLINES:
        rid, rname = r["id"], r.get("name", "")
        rg = grams(rname.split("：")[0])
        if not vg or not rg:
            continue
        inter = len(vg & rg)
        jac = inter / max(len(vg | rg), 1)
        if inter >= 3 and jac >= 0.30:
            cands.append((round(jac, 3), rid, rname))
    cands.sort(reverse=True)
    rows.append({"vr": vid, "vr_name": vname, "declared_rl": sorted(x for x, fs in declared.items() if False) or None,
                 "cands": cands[:3]})

# 哪些 RL 已被任何 VR/检测器声明
all_ids = [r["id"] for r in REDLINES]
cov = json.load(open(os.path.join(ROOT, "scripts", "_redline_coverage.json"), encoding="utf-8"))
blind = set(cov["blind"])
has_det = set(cov["has_detector"])

print("\n== 名称高相似(≥3 gram 且 Jaccard≥0.30)的 VR↔RL 候选（尤其落在盲区/仅兜底的要重点看）==")
need_review = []
for row in rows:
    if not row["cands"]:
        continue
    for jac, rid, rname in row["cands"]:
        if rid in blind:
            need_review.append((row["vr"], row["vr_name"], jac, rid, rname))
            print(f"  [盲区] {row['vr']:<7} {row['vr_name'][:28]:<30} ≈ {rid:<14} {rname[:30]:<32} J={jac}")
            break

print("\n== 盲区红线(%d 条) 中，有 VR 名称候选的 %d 条 ==" % (len(blind), len(need_review)))
print("== 盲区红线全量 ==")
for r in sorted(blind):
    print("   ", r)

out = {"vr_rl_candidates": rows, "blind": sorted(blind), "review": need_review}
json.dump(out, open(os.path.join(ROOT, "scripts", "_vr_rl_affinity.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("\n[OK] scripts/_vr_rl_affinity.json")
