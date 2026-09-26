# -*- coding: utf-8 -*-
"""一次性迁移：把 engine/industry_benchmark.py 里硬编码的 INDUSTRY_BENCHMARKS / _GENERIC
并入唯一数据源 static/industry_data.json，统一指标命名与结构。

合并前（三套，数字各不相同）：
  ① industry_data.json → benchmarks（66 细分行业，[下,上,中]，小数；指标名中文）
  ② industry_benchmark.py → INDUSTRY_BENCHMARKS（23 键， (下,上)，百分比；指标名英文）
  ③ benchmarks_coarse（10 门类，gross_margin/vat_burden 单值，百分比）—— 与 ① 同文件却不同schema
合并后：
  · 唯一数字来源 = industry_data.json
  · benchmarks / benchmarks_coarse **同一套指标名 + 同一套结构**（[下限,上限,中位]，小数比例）
  · 指标全量：毛利率 / 净利率 / 税负率 / 进销比 / 期间费用率 / 人均营收(万)
  · 门类层保留 gross_margin / vat_burden 兼容镜像（值＝中位×100），不破坏既有读取方
"""
import json
import os
import shutil
import datetime

REPO = r"c:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong"
os.chdir(REPO)
P = "static/industry_data.json"

data = json.load(open(P, encoding="utf-8"))
bm = data["benchmarks"]

# 合并前先把②③的原始数字固化下来（③的粗粒度真值取自②，①的粗粒度单值作为中位校验）
M = {  # 门类键 → ②中的键
    "制造业": "制造业", "建筑业": "建筑业", "批发零售": "批发和零售业",
    "交通运输": "交通运输仓储和邮政业", "住宿餐饮": "住宿和餐饮业",
    "信息技术": "软件和信息技术服务业", "租赁商务": "租赁和商务服务业",
    "房地产业": "房地产业", "农林牧渔": "农、林、牧、渔业",
    "电力热力燃气水": "电力热力燃气及水生产供应业",
}
SRC2 = {  # ②的原始数据（本次迁移的输入，迁移后源码中将不再出现硬编码）
    "制造业": {"vat_burden": (1.5, 3.5), "gross_margin": (8.0, 40.0), "expense_ratio": (0.0, 15.0), "purchase_sales": (0.4, 0.95)},
    "批发和零售业": {"vat_burden": (0.5, 1.5), "gross_margin": (5.0, 20.0), "expense_ratio": (0.0, 12.0), "purchase_sales": (0.6, 0.98)},
    "建筑业": {"vat_burden": (2.0, 3.5), "gross_margin": (8.0, 20.0), "expense_ratio": (0.0, 10.0), "purchase_sales": (0.5, 0.95)},
    "软件和信息技术服务业": {"vat_burden": (1.0, 3.0), "gross_margin": (25.0, 60.0), "expense_ratio": (0.0, 35.0), "purchase_sales": (0.1, 0.6)},
    "住宿和餐饮业": {"vat_burden": (1.0, 3.0), "gross_margin": (40.0, 65.0), "expense_ratio": (0.0, 45.0), "purchase_sales": (0.2, 0.7)},
    "交通运输仓储和邮政业": {"vat_burden": (2.0, 3.5), "gross_margin": (12.0, 28.0), "expense_ratio": (0.0, 15.0), "purchase_sales": (0.3, 0.85)},
    "房地产业": {"vat_burden": (2.5, 5.0), "gross_margin": (20.0, 40.0), "expense_ratio": (0.0, 15.0), "purchase_sales": (0.3, 0.9)},
    "租赁和商务服务业": {"vat_burden": (1.5, 4.0), "gross_margin": (20.0, 50.0), "expense_ratio": (0.0, 30.0), "purchase_sales": (0.15, 0.7)},
    "农、林、牧、渔业": {"vat_burden": (0.5, 2.0), "gross_margin": (10.0, 30.0), "expense_ratio": (0.0, 20.0), "purchase_sales": (0.3, 0.9)},
    "电力热力燃气及水生产供应业": {"vat_burden": (1.5, 3.0), "gross_margin": (10.0, 25.0), "expense_ratio": (0.0, 12.0), "purchase_sales": (0.4, 0.9)},
    # 以下为②中的细分口径，并入 benchmarks 细分层（仅补 期间费用率；其余指标以①为准）
    "广告传媒": {"vat_burden": (1.0, 3.5), "gross_margin": (30.0, 65.0), "expense_ratio": (0.0, 40.0), "purchase_sales": (0.15, 0.75)},
    "信息技术": {"vat_burden": (1.0, 3.0), "gross_margin": (30.0, 90.0), "expense_ratio": (0.0, 40.0), "purchase_sales": (0.1, 0.6)},
    "咨询服务": {"vat_burden": (1.5, 4.0), "gross_margin": (20.0, 75.0), "expense_ratio": (0.0, 45.0), "purchase_sales": (0.1, 0.6)},
    "建筑工程": {"vat_burden": (2.0, 3.5), "gross_margin": (5.0, 35.0), "expense_ratio": (0.0, 12.0), "purchase_sales": (0.5, 0.95)},
    "纺织制造": {"vat_burden": (1.5, 3.5), "gross_margin": (8.0, 40.0), "expense_ratio": (0.0, 15.0), "purchase_sales": (0.4, 0.95)},
    "餐饮服务": {"vat_burden": (1.0, 3.0), "gross_margin": (40.0, 65.0), "expense_ratio": (0.0, 45.0), "purchase_sales": (0.2, 0.7)},
    "物流运输": {"vat_burden": (2.0, 3.5), "gross_margin": (5.0, 40.0), "expense_ratio": (0.0, 15.0), "purchase_sales": (0.3, 0.85)},
    "医药健康": {"vat_burden": (1.5, 4.0), "gross_margin": (20.0, 60.0), "expense_ratio": (0.0, 35.0), "purchase_sales": (0.2, 0.8)},
    "商贸": {"vat_burden": (0.5, 1.5), "gross_margin": (3.0, 30.0), "expense_ratio": (0.0, 12.0), "purchase_sales": (0.6, 0.98)},
}
GENERIC_SRC = {"vat_burden": (0.3, 6.0), "gross_margin": (2.0, 70.0), "expense_ratio": (0.0, 50.0), "purchase_sales": (0.05, 1.2)}

report = []


def _tri(lo_pct, hi_pct, mid_pct=None):
    """百分比区间 → [下限, 上限, 中位] 小数；中位缺省取区间中点。"""
    lo, hi = lo_pct / 100.0, hi_pct / 100.0
    mid = (mid_pct / 100.0) if mid_pct is not None else round((lo + hi) / 2, 4)
    return [round(lo, 4), round(hi, 4), round(mid, 4)]


# ── ① 重建 benchmarks_coarse（统一 schema）──
old_coarse = data.get("benchmarks_coarse") or {}
new_coarse = {}
for ck, src_key in M.items():
    s = SRC2[src_key]
    old = old_coarse.get(ck) or {}
    gm_mid = old.get("gross_margin")            # ①原粗粒度单值（百分比）优先作为中位
    vat_mid = old.get("vat_burden")
    new_coarse[ck] = {
        "毛利率": _tri(s["gross_margin"][0], s["gross_margin"][1], gm_mid),
        "税负率": _tri(s["vat_burden"][0], s["vat_burden"][1], vat_mid),
        "进销比": _tri(s["purchase_sales"][0] * 100, s["purchase_sales"][1] * 100),
        "期间费用率": _tri(s["expense_ratio"][0], s["expense_ratio"][1]),
        # 兼容镜像：保留旧字段名（百分比单值），值＝中位×100，不破坏既有读取方
        "gross_margin": gm_mid if gm_mid is not None else round((s["gross_margin"][0] + s["gross_margin"][1]) / 2, 2),
        "vat_burden": vat_mid if vat_mid is not None else round((s["vat_burden"][0] + s["vat_burden"][1]) / 2, 2),
    }
    report.append("coarse {:<18} 毛利率{}~{}%  税负率{}~{}%".format(
        ck, s["gross_margin"][0], s["gross_margin"][1], s["vat_burden"][0], s["vat_burden"][1]))

# ①原粗粒度里未被②覆盖的门类（居民服务/文化体育）保留，只需补统一指标名
for ck, old in old_coarse.items():
    if ck in new_coarse:
        continue
    gm = float(old.get("gross_margin") or 0)
    vat = float(old.get("vat_burden") or 0)
    new_coarse[ck] = {
        "毛利率": _tri(max(gm - 10, 0), gm + 10, gm),
        "税负率": _tri(max(vat - 1.5, 0), vat + 1.5, vat),
        "进销比": [0.2, 0.95, 0.6],
        "期间费用率": [0.0, 30.0, 15.0],
        "gross_margin": gm, "vat_burden": vat,
    }
    report.append("coarse %-18s 由原单值推导（±10%%/±1.5%%）" % ck)
data["benchmarks_coarse"] = new_coarse

# ── ② 细分层补 期间费用率（来自②；其余指标一律以①为准）──
added = 0
for k, s in SRC2.items():
    if k not in bm:
        continue
    if "期间费用率" not in bm[k]:
        bm[k]["期间费用率"] = _tri(s["expense_ratio"][0], s["expense_ratio"][1])
        added += 1
report.append("细分层补 期间费用率 ×%d 个行业" % added)

# ── ③ _default 并入 _GENERIC（取更宽的兜底区间，保留"宽松"语义）──
dflt = bm.get("_default") or {}
widen = {
    "毛利率": _tri(GENERIC_SRC["gross_margin"][0], GENERIC_SRC["gross_margin"][1]),
    "税负率": _tri(GENERIC_SRC["vat_burden"][0], GENERIC_SRC["vat_burden"][1]),
    "进销比": _tri(GENERIC_SRC["purchase_sales"][0] * 100, GENERIC_SRC["purchase_sales"][1] * 100),
    "期间费用率": _tri(GENERIC_SRC["expense_ratio"][0], GENERIC_SRC["expense_ratio"][1]),
}
for mk, tri in widen.items():
    cur = dflt.get(mk)
    if not cur:
        dflt[mk] = tri
    else:
        dflt[mk] = [min(cur[0], tri[0]), max(cur[1], tri[1]), cur[2]]
dflt.setdefault("净利率", [0.01, 0.3, 0.08])
dflt.setdefault("人均营收(万)", [15, 200, 50])
bm["_default"] = dflt
report.append("_default 并入宽松兜底：%s" % json.dumps(dflt, ensure_ascii=False))

data["_merge_note"] = (
    "2026-09-25 合并：本文件为全系统**唯一**的行业数值来源。"
    "benchmarks（细分行业层）与 benchmarks_coarse（门类层）使用同一套指标名"
    "（毛利率/净利率/税负率/进销比/期间费用率/人均营收(万)）与同一结构 [下限,上限,中位]（小数比例）。"
    "engine/industry_benchmark.py 的区间改为从本文件派生，不再硬编码，避免'两套数字'。"
)

# ── 备份并写回 ──
bak = P + ".bak-" + datetime.datetime.now().strftime("%Y%m%d%H%M%S")
shutil.copy2(P, bak)
json.dump(data, open(P, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("备份 →", bak)
print("已写回", P, os.path.getsize(P), "bytes")
print()
for line in report:
    print("  ", line)
print()
print("校验：coarse 键 =", list(new_coarse.keys()))
print("细分行业数 =", len([k for k in bm if k != "_default"]))
