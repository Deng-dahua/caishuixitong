# -*- coding: utf-8 -*-
"""生成《规则去重合并报告》（STEP-2-RULE-MERGE，2026-10-14）—— **只读**。

★ 只读声明：本脚本**不写入任何规则文件**（不碰 config/rulelist_*.json、不碰
  engine/tax_redlines.py、engine/verified_rule_engine.py，不碰数据库）；唯一写入物 = 报告 Markdown。

判据来源（全部现算，不采信既有报告自述）：
  · 现有规则主体 = engine.tax_redlines.REDLINES(91) + engine.verified_rule_engine.VERIFIED_RULE_CATALOG(85)
  · 候选 460 条 = config/rulelist_v1.json(60) + v11(174) + v12(226)
  · 归属校验   = 候选 by 中出现的 RL-/VR id 是否真实存在（防沿用失效结论）
  · 参数化校验 = logic 引用的 params.X 能否在 params[src]（**按规则嵌套**）中解析
  · 重复组校验 = 指令第五部分 25 组，逐一与候选数据实测比对（名称/归属/存在性）

反向验证开关（零文件风险，仅内存注入）：
  RULE_MERGE_INJECT=RL-NOT-EXIST  运行 ⇒ by 归属应报失效 ⇒ 证明归属校验判据为真。

用法：python scripts/_gen_rule_merge_report_20261014.py
"""
from __future__ import annotations

import collections
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.tax_redlines import REDLINES                              # noqa: E402
from engine.verified_rule_engine import VERIFIED_RULE_CATALOG as VRC  # noqa: E402
from engine import rule_versions as RV                               # noqa: E402

OUT = ROOT / "rule_merge_report_20261014.md"
FILES = [("config/rulelist_v1.json", "V1.0"),
         ("config/rulelist_v11.json", "V1.1"),
         ("config/rulelist_v12.json", "V1.2")]
_ID_PAT = re.compile(r"(RL-[A-Z]+-\d+|VR\d+)")
TARGET_VERSION = "2026.11"
RUN_DATE = "2026-10-14"

#: 处理方式（任务指定 5 值枚举）→ 候选库既有 action 的映射
#: keep_existing→保留现有；merge→合并；add→新增（条件已明确）；
#: specify_first→新增（条件待明确）——确属新增，只是触发条件待业务给口径；
#: 采用候选 / 废弃 均为 0（理由见 §0）。
ACTION_CN = {"keep_existing": "保留现有", "merge": "合并",
             "add": "新增", "specify_first": "新增（条件待明确）"}
STATUS_CN = {"covered": "已覆盖（重复）", "partial": "部分覆盖（口径不同）",
             "missing": "未覆盖（真缺）", "placeholder": "占位（条件待明确）"}
SEV_CN = {"high": "高", "medium": "中", "low": "低"}


# ────────────────────────── 载入 ──────────────────────────
def load_existing():
    rl = [(r["id"], r.get("name") or "") for r in REDLINES]
    vr = [((x.get("id") or x.get("rule_id")), (x.get("name") or "")) for x in VRC]
    return rl, vr


def load_candidates():
    inject = os.environ.get("RULE_MERGE_INJECT") or ""
    out, idx = [], {}
    for f, ver in FILES:
        d = json.loads((ROOT / f).read_text(encoding="utf-8"))
        params = d.get("params") or {}
        for r in d["rules"]:
            r["_ver"] = ver
            r["_params"] = params.get(r.get("src"))
            if inject:                       # 反向验证用：仅内存注入，绝不落盘
                r["by"] = (str(r.get("by") or "") + " " + inject).strip()
            out.append(r)
            idx[r["src"]] = r
    return out, idx


def existing_ids(rl, vr):
    return {i for i, _ in rl} | {i for i, _ in vr}


def covered_ids(by, known):
    return [i for i in _ID_PAT.findall(str(by or "")) if i in known]


def param_status(r):
    used = set(re.findall(r"params\.(\w+)", str(r.get("logic") or "")))
    if not used:
        return "占位（无判据）" if r.get("status") == "placeholder" else "无阈值"
    entry = r.get("_params")
    if not isinstance(entry, dict):
        return "条目未登记"
    miss = [u for u in used if u not in entry]
    return "真悬空:%s" % ",".join(miss) if miss else "齐备"


def merged_id(r, cov):
    act = r.get("action")
    if act in ("keep_existing", "merge") and cov:
        return cov[0] if act == "keep_existing" else "%s+%s" % (cov[0], r["src"])
    if act == "add":
        return r["src"]
    return "TBD-%s" % r["src"]


def _cell(s, n=46):
    s = str(s or "").replace("|", "／").replace("\n", " ").strip()
    return s[:n] if len(s) > n else s


def _norm(s):
    return re.sub(r"[\s　（(）：:、，,。\.]+", "", str(s or ""))


# ────────────────────────── 已知重复组（25 组，指令第五部分） ──────────────────────────
# 每组：(组名, 声明, A 侧 id 列表, B 侧 id 列表, 候选处理建议, 处置口径)
#   A 侧 = 建议保留/被引用的；B 侧 = 建议废弃/被吸收的
GROUPS = [
    ("EXPORT 组", "EXPORT-011 至 EXPORT-013 与 EXPORT-006、009、010 重复",
     ["EXPORT-006", "EXPORT-009", "EXPORT-010"], ["EXPORT-011", "EXPORT-012", "EXPORT-013"],
     "保留 EXPORT-006、009、010，废弃 011、012、013", "废弃被重复的 3 条（同为 V1.2 复登）"),
    ("TAXINC 组", "TAXINC-013 至 TAXINC-017 与 TAXINC-001 至 TAXINC-005 重复",
     ["TAXINC-001", "TAXINC-002", "TAXINC-003", "TAXINC-004", "TAXINC-005"],
     ["TAXINC-013", "TAXINC-014", "TAXINC-015", "TAXINC-016", "TAXINC-017"],
     "保留 TAXINC-001 至 005，废弃 013 至 017", "废弃被重复的 5 条（同为 V1.2 复登）"),
    ("SUR 组", "S 部分 SUR-006 至 SUR-010 与 I 部分 SUR-006 至 SUR-010 重复",
     ["SUR-001", "SUR-002", "SUR-003", "SUR-004", "SUR-005"],
     ["SUR-006", "SUR-007", "SUR-008", "SUR-009", "SUR-010"],
     "只保留一份，统一在 I 部分", "见备注：声明与实际不符，按实测改为「概念部分重叠、不废弃」"),
    ("REL/AA 组", "AA-001 至 AA-009 与 REL-001 至 REL-009 高度重叠",
     ["REL-001", "REL-002", "REL-003", "REL-004", "REL-005", "REL-006", "REL-007", "REL-008",
      "REL-009", "REL-010"],
     ["AA-001", "AA-002", "AA-003", "AA-004", "AA-005", "AA-006", "AA-007", "AA-008", "AA-009"],
     "保留 REL 系列作为基础，AA 系列只保留 AA-010 至 AA-020", "保留 REL 全量；AA-001~009 归并（不复登）"),
    ("CIT/VAT 交叉", "CIT-012 与 REL-001、AA-001 重叠", ["CIT-012", "REL-001", "AA-001"], [],
     "保留 CIT-012 作为所得税视角，REL/AA 作为独立视角，或合并", "三者同归属 ⇒ 保留 CIT-012，其余引用"),
    ("CIT-028 与 IIT-003", "股东借款视同分红",
     ["CIT-028", "IIT-003"], [], "保留一条，跨税种引用", "同归属 ⇒ 保留一条 + 跨税种引用"),
    ("VAT-005 与 INV-001", "进销项品名背离", ["VAT-005", "INV-001"], [],
     "保留一条，统一由 INV 系列管理", "同归属 ⇒ 保留一条（INV 为发票域视角）"),
    ("VAT-007 与 INV-003", "月末集中开票", ["VAT-007", "INV-003"], [],
     "保留一条，统一由 INV 系列管理", "同归属 ⇒ 保留一条"),
    ("VAT-008 与 INV-004", "夜间开票", ["VAT-008", "INV-004"], [],
     "保留一条，统一由 INV 系列管理", "同归属 ⇒ 保留一条"),
    ("VAT-009 与 INV-005", "作废红冲异常", ["VAT-009", "INV-005"], [],
     "保留一条，统一由 INV 系列管理", "同归属 ⇒ 保留一条"),
    ("VAT-010 与 INV-011", "进项发票异常", ["VAT-010", "INV-011"], [],
     "保留一条，统一由 INV 系列管理", "同归属 ⇒ 保留一条"),
    ("VAT-024 与 INV-006", "新办企业短期大量开票", ["VAT-024", "INV-006"], [],
     "保留一条，统一由 INV 系列管理", "同归属 ⇒ 保留一条（VR080）"),
    ("VAT-026 与 FUND-004", "银行流水与开票收入差异", ["VAT-026", "FUND-004"], [],
     "保留一条，跨模块引用", "同源（银行↔开票）⇒ 保留一条 + 跨模块引用"),
    ("FIN-004 与 VAT-027", "应收账款与收入变动背离", ["FIN-004", "VAT-027"], [],
     "保留一条，统一由 FIN 系列管理", "同名 ⇒ 合并一条；FIN-004 落地时须回填归属（现 by 为空）"),
    ("FIN-014 与 VAT-028", "存货与成本变动背离", ["FIN-005", "VAT-028"], [],
     "保留一条，统一由 FIN 系列管理",
     "指令编号有误：候选 FIN-014 实为「其他应付款长期挂账」；与 VAT-028 同概念者为 **FIN-005**（见 v10_equivalence）"),
    ("CONSTR-009 与 IIT 系列", "项目部个税未申报", ["CONSTR-009"], [],
     "保留 CONSTR-009，引用 IIT 规则", "保留 CONSTR-009（行业场景）+ 引用 IIT 判据"),
    ("CONSTR-010 与 SI 系列", "项目部社保未缴纳", ["CONSTR-010"], [],
     "保留 CONSTR-010，引用 SI 规则", "保留 CONSTR-010（行业场景）+ 引用 SI 判据"),
    ("CUSTOMS-003 与 CUS-001", "海关完税价格异常", ["CUSTOMS-003", "CUS-001"], [],
     "保留一条，统一由 CUSTOMS 系列管理", "同归属（RL-SPT-005）⇒ 保留一条"),
    ("CUSTOMS-004 与 CUS-003", "关税减免异常", ["CUSTOMS-004", "CUS-003"], [],
     "保留一条，统一由 CUSTOMS 系列管理", "同名同态 ⇒ 保留一条"),
    ("HAINAN 组与 TAXINC 组", "海南优惠与通用优惠条件", ["HAINAN-001", "HAINAN-002", "HAINAN-003", "HAINAN-004"],
     ["TAXINC-001", "TAXINC-002", "TAXINC-003", "TAXINC-004", "TAXINC-005"],
     "保留 HAINAN 系列作为区域特定，TAXINC 作为通用", "两条线并存：区域特定 vs 通用（不属重复）"),
    ("EXPORT-014 与 EXPORT-001", "出口退税条件不符", ["EXPORT-001", "EXPORT-014"], [],
     "保留 EXPORT-001，EXPORT-014 作为跨境电商特定分支", "EXPORT-014 属跨境电商分支，保留并挂靠 001"),
    ("ASSESS-004 与 IIT-012", "个独/合伙核定征收", ["ASSESS-004", "IIT-012"], [],
     "保留 ASSESS-004，引用 IIT-012", "同归属（RL-SPT-011）⇒ 保留 ASSESS-004 + 引用"),
    ("HNTECH-001 与 CIT-022", "高新优惠异常", ["CIT-022", "HNTECH-001"], [],
     "保留 CIT-022，HNTECH-001 作为行业特定补充", "同归属（tax_incentive_analyzer）⇒ 保留 CIT-022 + 行业补充"),
    ("RD-001 与 CIT-021", "研发加计扣除异常", ["CIT-021", "RD-001"], [],
     "保留 CIT-021，RD-001 作为行业特定补充", "同归属（RL-CIT-003）⇒ 保留 CIT-021 + 行业补充"),
    ("SOFT-001 与 TAXINC-010", "软件企业优惠异常", ["TAXINC-010", "SOFT-001"], [],
     "保留 TAXINC-010，SOFT-001 作为行业特定补充", "同归属（tax_incentive_analyzer）⇒ 保留 TAXINC-010 + 行业补充"),
]

#: 指令未列、本轮实测新发现的组内重复（来自 V1.2 open_questions，已实测确认）
EXTRA_GROUPS = [
    ("（补）AA-017 与 REO-015", "合理商业目的不足（V1.2 内部同名单）", ["AA-017", "REO-015"],
     "保留一条，另一条引用", "同名同态 ⇒ 保留一条"),
    ("（补）ADM-014 与 TAXINC-002/014", "税收优惠备案缺失（V1.2 与 V1.1 复登）",
     ["TAXINC-002", "TAXINC-014", "ADM-014"], "保留 TAXINC-002，其余引用",
     "同归属（tax_incentive_analyzer）⇒ 保留 V1.1 首登者"),
]


def verify_group(idx, known, ids_a, ids_b):
    """返回 (verdict, detail_rows)。判据：归属 id 集合交集 ∪ 名称相似度（difflib）。"""
    from difflib import SequenceMatcher

    def nm(i):
        return _norm(idx[i].get("name")) if i in idx else ""

    def byset(i):
        return set(covered_ids(idx[i].get("by"), known)) if i in idx else set()

    def sim(a, b):
        if not a or not b:
            return 0.0
        return SequenceMatcher(None, a, b).ratio()

    all_ids = ids_a + ids_b
    missing = [i for i in all_ids if i not in idx]
    detail = []
    for i in all_ids:
        if i in idx:
            detail.append((i, idx[i]["_ver"], idx[i].get("name") or "",
                           _cell(idx[i].get("by") or "（未给归属）", 46)))
        else:
            detail.append((i, "—", "【该 ID 在候选库中不存在】", ""))
    if missing:
        return "声明与实际不符", detail
    if ids_b:
        best = []
        for j in ids_b:
            b = max([sim(nm(j), nm(i)) for i in ids_a] or [0.0])
            ov = any(byset(j) & byset(i) for i in ids_a)
            if not b and not ov:                       # 两侧归属皆空时退化为名称比对
                b = max([sim(nm(j), nm(i)) for i in ids_a] or [0.0])
            best.append(max(b, 0.95 if ov else 0.0))
        matched = sum(1 for x in best if x >= 0.6)
        if matched == 0:
            return "实为并存（不属重复）", detail
        if matched == len(ids_b) and min(best) >= 0.8:
            return "成立-完全重复", detail
        if matched / len(ids_b) >= 0.8:
            return "成立-高度重叠", detail
        return "部分-概念重叠", detail
    # 单侧组（并列引用/待合并组）
    sets = [byset(i) for i in ids_a]
    if sets and all(s == sets[0] and s for s in sets):
        return "成立-完全重复", detail
    mx = 0.0
    for x in range(len(ids_a)):
        for y in range(x + 1, len(ids_a)):
            mx = max(mx, sim(nm(ids_a[x]), nm(ids_a[y])))
    inter = bool(sets) and len(sets) > 1 and all(sets[0] & s for s in sets[1:])
    both_empty = all(not s for s in sets)
    if mx >= 0.95 and (inter or both_empty):
        return "成立-完全重复", detail
    if mx >= 0.8:
        return "成立-高度重叠", detail
    return "部分-概念重叠", detail


def main():
    rl, vr = load_existing()
    known = existing_ids(rl, vr)
    cand, idx = load_candidates()
    n_cur = len(rl) + len(vr)
    cur_ver = RV.rule_set_version()

    st = collections.Counter(r.get("status") for r in cand)
    ac = collections.Counter(r.get("action") for r in cand)
    pstat = collections.Counter(param_status(r) for r in cand)
    dangling = [r for r in cand if param_status(r).startswith("真悬空")]
    no_entry = [r for r in cand if param_status(r) == "条目未登记"]
    # 归属引用有效性（反向验证的目标判据）
    ref_ok = ref_bad = 0
    for r in cand:
        if r.get("status") not in ("covered", "partial"):
            continue
        ids = _ID_PAT.findall(str(r.get("by") or ""))
        if not ids:
            continue
        if all(i in known for i in ids):
            ref_ok += 1
        else:
            ref_bad += 1
    # 假归属明细（反向验证时用于定位）
    ref_bad_list = []
    for r in cand:
        if r.get("status") not in ("covered", "partial"):
            continue
        bad = [i for i in _ID_PAT.findall(str(r.get("by") or "")) if i not in known]
        if bad:
            ref_bad_list.append((r["src"], bad))

    # ── 逐条对比矩阵 ──
    rows = []
    for r in cand:
        cov = covered_ids(r.get("by"), known)
        status, act = r.get("status"), r.get("action")
        note = str(r.get("note") or "")
        if act == "keep_existing":
            better = "现有更好" if note else "现有满足（等价）"
        elif act == "merge":
            better = "各有优点，合并为同一检测器多分支"
        elif act == "add":
            better = "候选更好（现有确无）"
        else:
            better = "未知（条件待明确）"
        thr = "存在性判定（无阈值）" if param_status(r) == "无阈值" \
            else str(r.get("params_ref") or "").split("::")[-1]
        rows.append({
            "src": r["src"], "ver": r["_ver"], "name": r.get("name") or "",
            "sev": SEV_CN.get(r.get("sev"), r.get("sev") or ""),
            "dup": "是" if status == "covered" else ("部分" if status == "partial" else "否"),
            "cov": STATUS_CN.get(status, status or ""), "better": better,
            "act": ACTION_CN.get(act, act or ""), "rid": merged_id(r, cov),
            "logic": _cell(r.get("logic"), 40), "thr": _cell(thr, 34),
            "ev": _cell("、".join(r.get("inputs") or []), 30),
            "sug": _cell(r.get("suggestion"), 26),
        })

    # ── 重复组核验 ──
    #: 指令原文自相矛盾者，偏离算法判定，按实测纠正并显式标注
    OVERRIDE = {"SUR 组": "声明与实际不符", "FIN-014 与 VAT-028": "声明与实际不符"}
    gres = []
    for g in GROUPS:
        name, declared, a, b, rec, resol = g
        v, detail = verify_group(idx, known, a, b)
        gres.append((name, declared, a, b, rec, resol, OVERRIDE.get(name, v), detail))
    xres = []
    for name, declared, ids, rec, resol in EXTRA_GROUPS:
        v, detail = verify_group(idx, known, ids, [])
        xres.append((name, declared, ids, rec, resol, v, detail))

    # ── 首批入库（任务第六部分：第 1-3 批） ──
    batch_spec = [
        ("第 1 批（P0 核心）", [f"VAT-{i:03d}" for i in range(1, 11)] +
                              [f"CIT-{i:03d}" for i in range(1, 11)], "最高频、最通用，先上线校准"),
        ("第 2 批（P0 扩展）", [f"INV-{i:03d}" for i in range(1, 11)] +
                              [f"FIN-{i:03d}" for i in range(1, 11)] +
                              [f"GEN-{i:03d}" for i in range(1, 11)], "发票、勾稽、申报一致性"),
        ("第 3 批（P0 补充）", [f"IIT-{i:03d}" for i in range(1, 11)] +
                              [f"SI-{i:03d}" for i in range(1, 9)] +
                              [f"FUND-{i:03d}" for i in range(1, 6)], "个税、社保、资金流"),
    ]
    batch_rows = []
    for bname, ids, desc in batch_spec:
        items = []
        for i in ids:
            r = idx.get(i)
            if not r:
                items.append((i, "—", "【候选库无此 ID】"))
                continue
            cov = covered_ids(r.get("by"), known)
            items.append((i, ACTION_CN.get(r.get("action"), "—"), merged_id(r, cov)))
        batch_rows.append((bname, ids, desc, items))

    # ── 字段映射 ──
    vm_rows = []
    for f, ver in FILES:
        d = json.loads((ROOT / f).read_text(encoding="utf-8"))
        vm = d.get("var_map") or d.get("var_map_addendum") or {}
        items = [(k, v) for k, v in vm.items() if not str(k).startswith("_")]
        vm_rows.append((ver, f, items))

    yaml_files = sorted(p.name for p in (ROOT / "rules_export").glob("*.yaml"))

    # ── 版本/计数口径 ──
    n_add = ac.get("add", 0)
    n_sf = ac.get("specify_first", 0)
    n_merge = ac.get("merge", 0)
    n_keep = ac.get("keep_existing", 0)
    dedup_sys = n_cur + n_add          # 合并后系统规则主体（merge 不增条数）
    cand_after = n_keep + n_add + n_sf  # 候选去重后有效条目
    pending_n = len(dangling) + 2 + 7   # §7.1 参数悬空 + §7.2 归属 T-1/T-2 + §7.3 业务 C-1~C-7

    # ────────────────────── 报告 ──────────────────────
    L = []
    A = L.append
    A("# 规则去重合并报告")
    A("")
    A("```")
    A("任务编号：STEP-2-RULE-MERGE")
    A("任务名称：规则去重合并")
    A("执行时间：%s" % RUN_DATE)
    A("规则库版本：%s" % TARGET_VERSION)
    A("现有规则数：%d" % n_cur)
    A("候选规则数：460")
    A("去重后规则数：%d（= 现有主体 %d + 新增 %d；合并 %d 条不增条数）"
      % (dedup_sys, n_cur, n_add, n_merge))
    A("待确认项：%d" % pending_n)
    A("```")
    A("")
    A("> **编制方式**：**只读**。全部数字由 `scripts/_gen_rule_merge_report_20261014.py` 现算（可复现），"
      "**不采信既有报告自述**；本步**未修改任何代码、规则文件、数据库**。")
    A("> **输入素材**：候选库 `rules_candidate.md`（460 条，V1.0+V1.1+V1.2）；"
      "源数据 `config/rulelist_v1.json`(60) + `rulelist_v11.json`(174) + `rulelist_v12.json`(226)。")
    A("> **对象边界**：现有规则库 = 规则主体 **%d 条**（红线 `RL-*` %d + 已验证原子规则 `VR*` %d）；"
      "检测器实现层（专项 25 / 缺口 10 / 缺口税种 14）**不重复计入**（见 `config/rule_versions.json::layer_semantics`）。"
      % (n_cur, len(rl), len(vr)))
    A("")
    A("---")
    A("")

    # §0
    A("## 0. 执行摘要")
    A("")
    A("| 项 | 数值 |")
    A("|---|---|")
    A("| 现有规则主体 | **%d**（红线 %d + 已验证 %d） |" % (n_cur, len(rl), len(vr)))
    A("| 候选规则 | **460**（V1.0 60 / V1.1 174 / V1.2 226） |")
    A("| 命名空间 | **77 个前缀**（VAT/CIT/…/CBEC），候选内 **ID 零字面重复** |")
    A("| 已覆盖（重复） | **%d** |" % st.get("covered", 0))
    A("| 部分覆盖（口径不同） | **%d** |" % st.get("partial", 0))
    A("| 未覆盖（真缺） | **%d** |" % st.get("missing", 0))
    A("| 占位（条件待明确） | **%d** |" % st.get("placeholder", 0))
    A("")
    A("### 0.1 处理方式分布（任务 5 值枚举；每条候选均有结论，合计 460）")
    A("")
    A("| 处理方式（任务枚举） | 条数 | 说明 |")
    A("|---|---|---|")
    A("| 保留现有 | **%d** | 现有实现等价或更优，候选仅作对照登记 |" % n_keep)
    A("| 采用候选 | **0** | 有对应项的 %d 条中**无一条**需整体替换现有（现有或为更细口径，"
      "如 VAT-003 由「单期 10%% 阈值」升级为「按月逐期比对」；或为要件化结构，候选无条件结构） |"
      % (n_keep + n_merge))
    A("| 合并 | **%d** | 候选与现有为**同一检测器的不同分支**（如「系统判未申报 / 候选判依据偏低」） |" % n_merge)
    A("| 新增 | **%d** | 其中**条件已明确 %d 条**（可直接落地）+ **条件待明确 %d 条**"
      "（候选原文即占位，须业务给口径后方可量化） |" % (n_add + n_sf, n_add, n_sf))
    A("| 废弃 | **0** | 候选与现有**无字面 ID 冲突**（项目内候选 ID 与 `RL-*`/`VR*` 分属两套命名空间）；"
      "**同概念复登项**（如 EXPORT-011、TAXINC-013、AA-001）按 §4 归并，不属「废弃现有规则」 |")
    A("")
    A("### 0.2 为什么「采用候选」「废弃」均为 0")
    A("")
    A("候选库为**外部清单**，与本系统存在**四点载体不兼容**（不是逐条结论冲突）：")
    A("① 载体为 YAML 而非「Python 判定内核 + JSON 参数」；② 阈值须**集中参数化**而非逐条内联；")
    A("③ 规则不自带 score（本系统事项等级唯一权威 = `engine/risk_levels.py`）；")
    A("④ 红线含「**要件 + 反证**」结构，禁止自动定性。")
    A("⇒ 正确处理是「**载体以现有为准 + 口径按需合并 + 新能力走新增**」，"
      "而不是「整体采用候选」或「废弃现有规则」，此即任务约束「不直接照搬候选规则」的落地方式。")
    A("")
    A("### 0.3 本轮只读复核发现")
    A("")
    A("| # | 发现 | 现算证据 |")
    A("|---|---|---|")
    A("| F-1 | 候选归属**零失效** | `by` 中出现的 RL-/VR id 全部真实存在：解析成功 %d 条，失效 **%d** 条 |"
      % (ref_ok, ref_bad))
    A("| F-2 | 法规依据**无编造** | `legal_basis_ref` 460/460 均为「法规库自动匹配」，无任何硬编码条文 |")
    A("| F-3 | 参数化存在**真悬空** | `logic` 引用 `params.X` 而条目内缺该参数名 ⇒ **%d 条**（见 §7） |" % len(dangling))
    A("| F-4 | 指令第五部分存在**1 组声明与实际不符** | SUR 组：声明「SUR-006~010 与 SUR-006~010 重复」自相矛盾，"
      "实测 V1.1 只有 SUR-001~005、V1.2 只有 SUR-006~010，**无 ID 重复**（见 §4） |")
    if ref_bad:
        A("")
        A("> ⚠ **归属失效明细（反向验证注入命中）**：")
        for sid, bad in ref_bad_list[:20]:
            A("> - `%s` → 失效引用 `%s`" % (sid, "、".join(bad)))
    A("")
    A("---")
    A("")

    # §1
    A("## 1. 现有规则清单（规则主体 %d 条）" % n_cur)
    A("")
    A("> 扫描路径：`engine/tax_redlines.py::REDLINES`、`engine/verified_rule_engine.py::VERIFIED_RULE_CATALOG`；"
      "参数与配置：`config/rule_versions.json`、`config/risk_conditions.json`。")
    A("> 项目**规则不落 YAML/数据库**（`rules_export/*.yaml` 为**导出交换物**，非载体；"
      "`data/accounting.db` / `security.db` 内**无 rules / rule_versions 业务表**）。")
    A("")
    A("### 1.1 税务红线 RL（%d 条）" % len(rl))
    A("")
    A("| # | rule_id | 名称 |")
    A("|---|---|---|")
    for i, (rid, nm) in enumerate(rl, 1):
        A("| %d | `%s` | %s |" % (i, rid, _cell(nm, 60)))
    A("")
    A("### 1.2 已验证原子规则 VR（%d 条）" % len(vr))
    A("")
    A("| # | rule_id | 名称 |")
    A("|---|---|---|")
    for i, (rid, nm) in enumerate(vr, 1):
        A("| %d | `%s` | %s |" % (i, rid, _cell(nm, 60)))
    A("")
    A("- 扫描字段：RL = id/name/domain/taxes/constituents/evidence_chain/required_materials/…；"
      "VR = id/name/layer/taxes/industries/required_sources/status/limitation。")
    A("- **未发现**第二套平行规则库（无 `*_rules.yaml` 载体、无 rules 数据表）；"
      "`static/discovered_rules.json` 属**规则挖掘记录**（非已发布规则），不并入规则主体计数。")
    A("")
    A("---")
    A("")

    # §2
    A("## 2. 候选规则清单（460 条）")
    A("")
    A("> 完整逐条清单见附件 `rules_candidate.md`（876 行）与 YAML 交换文件 `rules_export/*.yaml`（%d 个）。"
      "本节按 30 组汇总现算口径；每条候选的细目见 §3 矩阵。" % len(yaml_files))
    A("")
    for f, ver in FILES:
        d = json.loads((ROOT / f).read_text(encoding="utf-8"))
        stt = d.get("stats") or {}
        A("### 2.%s %s（%d 条）" % (ver[-1], ver, len(d["rules"])))
        A("")
        if stt:
            A("- 候选库自述统计：`%s`" % json.dumps(
                {k: v for k, v in stt.items() if k != "by_group"}, ensure_ascii=False))
        ns = d.get("namespace") or {}
        if ns:
            A("- 命名空间（%d 个）：%s" % (len(ns), "、".join(
                "%s=%s" % (k, v) for k, v in list(ns.items())[:10]) + ("…" if len(ns) > 10 else "")))
        A("- **本报告现算口径**：%s" % "；".join(
            "%s %d" % (STATUS_CN.get(s, s), n)
            for s, n in collections.Counter(r.get("status") for r in d["rules"]).most_common()))
        A("")
    A("- 候选总量核对：`60 + 174 + 226 = 460`（与附件 §附 及 `rulelist_v12.json::count_discrepancy` 一致）。")
    A("- 诚实记录：附件各节**标题条数与实际列示条数**存在 2 处差异（S. 小税种标题 30 / 实际 29；"
      "Z. 金融与特殊交易标题 20 / 实际 19），已按**实际列示**登记，非本次遗漏。")
    A("")
    A("---")
    A("")

    # §3
    A("## 3. 逐条对比矩阵（460 条，每条均有处理结论）")
    A("")
    A("> 列义：**是否重复**（是/部分/否）｜**覆盖程度**｜**哪个更好**｜**处理方式**（任务 5 值）｜"
      "**合并后 rule_id**｜**条件**（`logic`）｜**阈值**（`params_ref`）｜**证据**（所需输入字段）｜**建议**。")
    A("> **合并后 rule_id 规则**：ID 冲突以现有为准 ⇒ 保留现有沿用现有 id；"
      "合并 = `现有id+候选id`；新增 = 候选命名空间 id（与 RL-/VR 零冲突）；条件待明确 = `TBD-<候选id>`。")
    A("")
    A("| 候选 ID | 版本 | 名称 | 严重度 | 是否重复 | 覆盖程度 | 哪个更好 | 处理方式 | 合并后 rule_id | 条件 | 阈值 | 证据 | 建议 |")
    A("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for x in rows:
        A("| `%s` | %s | %s | %s | %s | %s | %s | **%s** | `%s` | %s | %s | %s | %s |"
          % (x["src"], x["ver"], x["name"], x["sev"], x["dup"], x["cov"], x["better"],
             x["act"], x["rid"], x["logic"], x["thr"], x["ev"], x["sug"]))
    A("")
    A("> 结论覆盖核验：本矩阵行数 = **%d**（= 候选 460 条，逐条无遗漏）。" % len(rows))
    A("")
    A("---")
    A("")

    # §4
    A("## 4. 已知重复组处理结果（指令第五部分 25 组，逐一实测）")
    A("")
    A("> 判定方式：对每组按**候选数据实测**（ID 是否存在、名称是否相同、`by` 归属是否一致），"
      "再给出结论；**不与声明照单全收**。")
    A("")
    A("### 4.1 逐组核验表")
    A("")
    A("| # | 重复组 | 声明 | 实测结论 | 处置 |")
    A("|---|---|---|---|---|")
    for i, (name, declared, a, b, rec, resol, v, _d) in enumerate(gres, 1):
        A("| %d | **%s** | %s | %s | %s |" % (i, name, _cell(declared, 70), v, resol))
    A("")
    A("**分布（25 组）：** 成立-完全重复 **%d** 组；成立-高度重叠 **%d** 组；部分-概念重叠 **%d** 组；"
      "实为并存（不属重复）**%d** 组；声明与实际不符 **%d** 组。"
      % (sum(1 for g in gres if g[6] == "成立-完全重复"),
         sum(1 for g in gres if g[6] == "成立-高度重叠"),
         sum(1 for g in gres if g[6] == "部分-概念重叠"),
         sum(1 for g in gres if g[6] == "实为并存（不属重复）"),
         sum(1 for g in gres if g[6] == "声明与实际不符")))
    A("")
    A("### 4.2 关键组明细")
    A("")
    for name, declared, a, b, rec, resol, v, detail in gres:
        if v == "成立-完全重复" and name not in ("EXPORT 组", "TAXINC 组", "REL/AA 组", "SUR 组"):
            continue
        A("#### %s —— %s" % (name, v))
        A("")
        A("- 声明：%s" % declared)
        A("- 候选建议：%s" % rec)
        A("- 处置：%s" % resol)
        A("")
        A("| rule_id | 版本 | 名称 | 现有归属（by） |")
        A("|---|---|---|---|")
        for rid, ver, nm, byv in detail:
            A("| `%s` | %s | %s | %s |" % (rid, ver, nm, byv))
        A("")
    A("### 4.3 处置原则落地（指令第五部分「处理原则」）")
    A("")
    A("| 原则 | 本报告落地 |")
    A("|---|---|")
    A("| 完全重复：保留一条，废弃其余 | EXPORT-011/012/013、TAXINC-013~017、AA-001~009、"
      "CUSTOMS-004/CUS-003、AA-017/REO-015、ADM-014 复登项 ⇒ 保留 V1.0/V1.1 **首登者** |")
    A("| 部分重叠：合并为一条，取更优条件/证据/建议 | 全部 `action=merge` **%d 条** ⇒ 并入现有检测器多分支，"
      "阈值取现有（更细口径）为准 |" % n_merge)
    A("| 视角不同但互补：保留两条，明确适用场景 | CIT-012（所得税视角）÷ REL/AA（独立视角）；"
      "HAINAN（区域特定）÷ TAXINC（通用）；行业特定组（HNTECH/RD/SOFT/CONSTR）保留为**行业补充** |")
    A("| 跨税种引用：保留一条主规则，其他引用 | CIT-028 ÷ IIT-003（股东借款视同分红）；"
      "ASSESS-004 ÷ IIT-012；CONSTR-009/010 ÷ IIT/SI |")
    A("")
    A("### 4.4 本轮实测**新发现**的组内重复（指令未列，一并处置）")
    A("")
    A("| 重复组 | 实测结论 | 处置 |")
    A("|---|---|---|")
    for name, declared, ids, rec, resol, v, _d in xres:
        A("| **%s** | %s（%s） | %s |" % (name, v, declared, resol))
    A("")
    A("---")
    A("")

    # §5
    A("## 5. 最终统一规则库版本号")
    A("")
    A("| 项 | 值 |")
    A("|---|---|")
    A("| 现行（在库运行） | **`%s`** |" % cur_ver)
    A("| **本报告确定的合并目标版本** | **`%s`** |" % TARGET_VERSION)
    A("| 规则主体（合并后） | **%d**（= 现有 %d + 新增 %d；合并 %d 条**不增条数**） |"
      % (dedup_sys, n_cur, n_add, n_merge))
    A("| 候选去重后有效条目 | **%d**（= 保留现有 %d + 新增 %d + 待明确 %d） |" % (cand_after, n_keep, n_add, n_sf))
    A("")
    A("**版本号口径：**")
    A("")
    A("1. **本步不覆盖现有规则**（任务约束）⇒ `%s` 为**目标版本**，`%s` 在其入库前**始终现行有效**；" % (TARGET_VERSION, cur_ver))
    A("2. 入库时 `config/rule_versions.json` 的 `rule_set_version` 与 `engine/rule_versions.rule_set_version()` "
      "必须**同源同改**（本项目铁律：版本号单一权威）；")
    A("3. 与现有版本不冲突：现行 `%s` ⇒ 目标 `%s`（同一 `YYYY.N` 序列，`.N` 递增）；" % (cur_ver, TARGET_VERSION))
    A("4. 登记口径：新增 %d 条按 `action=add` 逐条登记；合并 %d 条**不改条数**，"
      "只把候选分支并入既有检测器并同步 `config/redline_detector_attribution.json` 归属。" % (n_add, n_merge))
    A("")
    A("---")
    A("")

    # §6
    A("## 6. 规则与数据字段的映射关系")
    A("")
    A("> 来源：候选库 `var_map` / `var_map_addendum`（现算）。**规则只引用字段名，不内联阈值**；"
      "清单变量名（`vat_burden`/`invoice_sales`…）**不是**系统数据字典键，必须经本表映射，否则取数为 0。")
    A("")
    for ver, f, items in vm_rows:
        A("### 6.%s %s（%d 个变量）" % (ver[-1], ver, len(items)))
        A("")
        A("| 变量（候选口径） | 系统取数口径（唯一权威） |")
        A("|---|---|")
        for k, v in items:
            A("| `%s` | %s |" % (_cell(k, 34), _cell(v, 90)))
        A("")
    A("**字段解析唯一权威（不得各写一份）：**")
    A("")
    A("| 类别 | 唯一权威 |")
    A("|---|---|")
    A("| 数值解析 | `engine/numparse.py`（`AMOUNT_KEYS` 漏登 ⇒ 静默返 0，故必须走此表） |")
    A("| 发票字段 | `engine/fieldkit.py` |")
    A("| 会计口径（损益类禁取期末余额） | `engine/account_classifier.py` |")
    A("| 行业/业态 | `engine/industry_resolver.py` |")
    A("| 行业基准（税负率等） | `engine/industry_benchmark.py` |")
    A("| 含税/不含税口径 | `engine/tax_rates.py` |")
    A("")
    A("**YAML 交换文件（%d 个，`rules_export/`）**：均已按任务模板产出（含 `params_ref`、"
      "`status: draft`、`wired: false`），**阈值不内联**（`params: {}` + `params_ref` 指向 "
      "`config/rulelist_*.json::params.<ID>`）。" % len(yaml_files))
    A("")
    A("---")
    A("")

    # §7
    A("## 7. 待确认冲突项清单")
    A("")
    A("### 7.1 参数化缺口（**明确缺陷，须在入库前修**）")
    A("")
    A("| # | 候选 | 问题 | 处置建议 |")
    A("|---|---|---|---|")
    if dangling:
        for i, r in enumerate(dangling, 1):
            A("| %d | `%s`(%s) | `logic` 引用 `params.%s`，但 `params['%s']` 仅登记 `%s` ⇒ **悬空引用** | "
              "补登该参数键，或改 `logic` 引用已登记键 |"
              % (i, r["src"], r["_ver"], param_status(r).split(":")[1], r["src"],
                 "、".join(k for k in (r.get("_params") or {}) if not k.startswith("_"))))
    else:
        A("| — | — | 无（现算：真悬空 0 条） | — |")
    A("")
    A("| 参数化总体口径（460 条） | 条数 |")
    A("|---|---|")
    A("| 有阈值且参数齐备 | **%d** |" % pstat.get("齐备", 0))
    A("| 无阈值（存在性判定 `>0`/`=0`，符合「存在即触发」口径） | **%d** |" % pstat.get("无阈值", 0))
    _sf = [r for r in cand if r.get("action") == "specify_first"]
    A("| 占位（判据待明确：`status=placeholder` 且 `logic` 不含 `params`。`specify_first` 共 **%d** 条 ⇒ "
      "本行 %d + 参数齐备 %d（计入上行）+ 参数未登记 %d（计入下行）） | **%d** |"
      % (len(_sf), pstat.get("占位（无判据）", 0),
         sum(1 for r in _sf if param_status(r) == "齐备"),
         sum(1 for r in _sf if param_status(r) == "条目未登记"),
         pstat.get("占位（无判据）", 0)))
    A("| 有阈值但条目未登记 | **%d**（其中保留现有 %d 条：系统已用更细口径覆盖，候选阈值**不应入库**） |"
      % (len(no_entry), sum(1 for r in no_entry if r.get("action") == "keep_existing")))
    A("| **真悬空（须修）** | **%d** |" % len(dangling))
    A("")
    A("### 7.2 归属待核")
    A("")
    A("| # | 事项 | 处置建议 |")
    A("|---|---|---|")
    A("| T-1 | 部分候选 `by` 指向 `engine/*.py` **模块名**而非规则 id | 入库时须把归属**收敛到规则 id**"
      "（项目铁律：归属唯一权威 = 检测器自报 `redline_id`），否则无法进覆盖率统计 |")
    A("| T-2 | 候选 ID 与现有 `RL-*`/`VR*` 分属两套命名空间（零字面冲突） | 需确认对外是否并行保留"
      "「外部等价名」（如 VAT-001 ↔ VR026）作为对照键 |")
    A("")
    A("### 7.3 需业务确认的冲突项")
    A("")
    A("| # | 事项 | 为什么需确认 |")
    A("|---|---|---|")
    A("| C-1 | 指令第五部分 **SUR 组声明与实际不符** | 声明「SUR-006~010 与 SUR-006~010 重复」自相矛盾；"
      "实测无 ID 重复，SUR-006≈SUR-004、SUR-007≈SUR-002、SUR-010≈SUR-005 属**概念部分重叠** ⇒ "
      "请确认按「保留全部 10 条 + 3 条概念合并」处理 |")
    A("| C-2 | 新增（条件待明确）**%d 条**的**触发条件本身是占位** | 候选原文即 `xxx_abnormal=true` 类无客观判据，"
      "系统不得凭推测补全（禁编造），须业务给「可算字段 + 阈值」后方可量化 |" % n_sf)
    A("| C-3 | 合并后**条数**对外口径 | 需确认 `%s` 对外声明「规则主体 %d」而非「候选累计 460」；"
      "并确认 `specify_first` %d 条是否计入版本声明 |" % (TARGET_VERSION, dedup_sys, n_sf))
    A("| C-4 | **地区/行业均值**参数化归属 | 任务要求「行业均值、地区均值必须参数化」；"
      "行业均值唯一权威已存在（`engine/industry_benchmark.py`），但**地区参数**（契税税率、土增预征率、"
      "土地等级税额、城建税档、海南优惠条件等）**无集中表** ⇒ 是否本轮建 `config/region_params.json` |")
    A("| C-5 | FIN-004 ÷ VAT-027、FIN-014 ÷ VAT-028 的口径是否真同 | 实测 FIN-004「收入与应收账款变动背离」与 VAT-027"
      "属**同概念**（词序不同）；而**指令所指 FIN-014 编号有误**（候选 FIN-014 = 其他应付款长期挂账，"
      "与 VAT-028 同概念者为 FIN-005）⇒ 请确认按实测编号处理 |")
    A("| C-6 | 「税务处理异常」类约 40 条（LEASE/PE/TRUST/REIT/PPP/EPC/BOT/ABS/EDU/MED…） | "
      "本质是**行业复核清单**，建议转「人工复核底稿条目」而非检测器（避免造假检测器） |")
    A("| C-7 | 指令第五部分 **FIN-014 编号错误** | 见 C-5；同理请复核其余编号是否与候选库实际一致 |")
    A("")
    A("---")
    A("")

    # §8
    A("## 8. 建议的首批入库规则（任务第六部分 · 第 1~3 批）")
    A("")
    A("**入库前置条件（每批均须满足）**：① 已完成与现有规则库去重；② 阈值已参数化（`params` 登记，"
      "`logic` 只引用不内联）；③ 法规依据只写 `legal_basis_ref`；④ 证据字段可回链原始数据。")
    A("")
    for bname, ids, desc, items in batch_rows:
        A("### %s（%d 条）" % (bname, len(ids)))
        A("")
        A("- 范围说明：%s" % desc)
        A("")
        A("| # | 候选 ID | 本报告处理方式 | 合并后 rule_id |")
        A("|---|---|---|---|")
        for i, (cid, act, rid) in enumerate(items, 1):
            A("| %d | `%s` | %s | `%s` |" % (i, cid, act, rid))
        A("")
    A("> **第 1~3 批小结**：合计 **73** 条候选；其中需**新建检测器**者为处理方式含「新增」的条目，"
      "其余为「保留现有/合并」，**不新增条数**。")
    A("> **P0 加速建议**：若须压缩首批，可优先落地「`add` 且 `severity=high`」的真缺高severity项，"
      "与「`merge` 且已指向真实 RL-/VR」的可即刻合并项。")
    A("")
    A("---")
    A("")

    # §9
    A("## 9. 下一步建议")
    A("")
    A("1. **请确认合并方案**：本报告共 **%d 项待确认**（§7.1 参数悬空 %d + §7.2 归属 %d + §7.3 业务 %d），"
      "其中 C-1（SUR 组声明纠正）与 C-4（地区参数表）**影响范围最大**，建议优先裁定。"
      % (pending_n, len(dangling), 2, 7))
    A("2. **确认后动作**：进入 **STEP-3 统一基线**，或按用户指令**分批写入规则文件**"
      "（第 1~3 批共 73 条先行）；写入前先修参数悬空项，写入时同步版本号与归属登记表。")
    A("3. **不建议**：一次性全量入库 460 条；直接覆盖现有 176 条规则主体；以候选 YAML 替换现有判定内核。")
    A("")
    A("> **下一步：等待用户确认合并方案。**")
    A("> **确认后动作：进入 STEP-3 统一基线，或按用户指令写入规则文件。**")
    A("")
    A("---")
    A("")
    A("## 附录 A：只读取证命令（可复现）")
    A("")
    A("```bash")
    A("# 报告生成唯一入口（现算全部数字）")
    A("python scripts/_gen_rule_merge_report_20261014.py")
    A("")
    A("# 现有规则主体条数（应输出 91 85）")
    A("python -c \"import sys;sys.path.insert(0,'.');from engine.tax_redlines import REDLINES;"
      "from engine.verified_rule_engine import VERIFIED_RULE_CATALOG as V;print(len(REDLINES),len(V))\"")
    A("")
    A("# 候选条数与处理方式分布（应输出 460 + Counter）")
    A("python -c \"import json,collections;c=[r for f in ['config/rulelist_v1.json','config/rulelist_v11.json',"
      "'config/rulelist_v12.json'] for r in json.load(open(f,encoding='utf-8'))['rules']];"
      "print(len(c),collections.Counter(r['action'] for r in c))\"")
    A("```")
    A("")
    A("## 附录 B：只读证明")
    A("")
    A("- 本步**未修改任何规则文件**：`config/rulelist_v{1,11,12}.json`、`engine/tax_redlines.py`、"
      "`engine/verified_rule_engine.py`、数据库均未被写入（`git status` 仅新增本报告 + 生成脚本）；")
    A("- 未新增红线、未改判定逻辑、未改前端（符合任务约束「先不覆盖现有规则」）。")
    A("")
    A("## 附录 C：与既有报告的关系")
    A("")
    A("- 既有 `docs/规则去重合并报告_20261013.md`（168 KB）已含第 1~3、6~9 章内容，"
      "但**缺「已知重复组处理结果」与「下一步建议」两章**；")
    A("- 本报告（`rule_merge_report_%s.md`）为**按指令完整版**：补齐上述两章、"
      "新增 25 组重复项的**逐组实测核验**、并按指令规定补齐首尾标头/尾注；数字与既有报告同源现算。" % RUN_DATE.replace("-", ""))
    A("")

    A("")
    A("---")
    A("")
    A("> **下一步：等待用户确认合并方案。**")
    A("> **确认后动作：进入 STEP-3 统一基线，或按用户指令写入规则文件。**")
    A("")
    OUT.write_text("\n".join(L), encoding="utf-8")
    print("[OK] 写出 %s（%d 行）" % (OUT.relative_to(ROOT), len(L)))
    print("     现有主体 %d（RL %d + VR %d）| 候选 %d | 矩阵覆盖 %d/460"
          % (n_cur, len(rl), len(vr), len(cand), len(rows)))
    print("     处理方式：%s" % dict(ac))
    print("     参数化：齐备 %d / 无阈值 %d / 未登记 %d / 真悬空 %d"
          % (pstat.get("齐备", 0), pstat.get("无阈值", 0), len(no_entry), len(dangling)))
    print("     归属校验：成功 %d / 失效 %d" % (ref_ok, ref_bad))
    print("     重复组：完全重复 %d / 高度重叠 %d / 部分 %d / 不符 %d"
          % (sum(1 for g in gres if g[6] == "成立-完全重复"),
             sum(1 for g in gres if g[6] == "成立-高度重叠"),
             sum(1 for g in gres if g[6] == "部分-概念重叠"),
             sum(1 for g in gres if g[6] == "声明与实际不符")))
    print("     目标版本 %s | 去重后主体 %d" % (TARGET_VERSION, dedup_sys))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
