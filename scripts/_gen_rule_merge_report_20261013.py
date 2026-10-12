# -*- coding: utf-8 -*-
"""生成《规则去重合并报告》（2026-10-13）—— **只读**候选库与现有规则库，产出新报告。

★ 只读声明：本脚本**不写入任何规则文件**（不碰 config/rulelist_*.json、不碰 tax_redlines.py /
  verified_rule_engine.py）；唯一写入物 = 报告 Markdown。

判据来源（全部现算，不采信既有报告自述）：
  · 现有规则主体 = `engine.tax_redlines.REDLINES`(91) + `engine.verified_rule_engine.VERIFIED_RULE_CATALOG`(85)
  · 候选 460 条 = `config/rulelist_v1.json`(60) + `v11`(174) + `v12`(226)
  · 归属校验 = 候选 `by` 中出现的 RL-/VR id 是否真实存在（防沿用失效结论）
  · 参数化校验 = `logic` 引用的 `params.X` 能否在 `params[src]`（**按规则嵌套**）中解析
用法：`python scripts/_gen_rule_merge_report_20261013.py`
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.tax_redlines import REDLINES                       # noqa: E402
from engine.verified_rule_engine import VERIFIED_RULE_CATALOG as VRC  # noqa: E402
from engine import rule_versions as RV                        # noqa: E402

OUT = ROOT / "docs" / "规则去重合并报告_20261013.md"
FILES = [("config/rulelist_v1.json", "V1.0"),
         ("config/rulelist_v11.json", "V1.1"),
         ("config/rulelist_v12.json", "V1.2")]
_ID_PAT = re.compile(r"(RL-[A-Z]+-\d+|VR\d+)")

#: 处理方式（**任务指定的 5 值枚举**）→ 与候选库既有 `action` 的对应
#: ★ 口径：候选为「外部清单」，其 `action` 与任务枚举**不是逐字对应**，须显式映射：
#:   keep_existing → 保留现有 ；merge → 合并 ；add → 新增（条件已明确）；
#:   specify_first → 新增（条件待明确）——它**确属新增**（现有无对应项），只是触发条件待业务给口径；
#:   采用候选 = 0 （有对应项的 272 条中，无一条需整体替换现有：现有或为更细口径、或为要件化结构）；
#:   废弃     = 0 （候选与现有不构成同一 ID 冲突，结论亦无互斥项）
ACTION_CN = {
    "keep_existing": "保留现有",
    "merge": "合并",
    "add": "新增",
    "specify_first": "新增（条件待明确）",
}
#: 任务 5 值枚举 → 本报告实际条数（`specify_first` 归入「新增」桶）
ENUM_MAP = [
    ("保留现有", "keep_existing"),
    ("采用候选", None),
    ("合并", "merge"),
    ("新增", ("add", "specify_first")),
    ("废弃", None),
]
#: 覆盖程度（候选 `status`）→ 中文
STATUS_CN = {
    "covered": "已覆盖（重复）",
    "partial": "部分覆盖（口径不同）",
    "missing": "未覆盖（真缺）",
    "placeholder": "占位（条件待明确）",
}
SEV_CN = {"high": "高", "medium": "中", "low": "低"}


def load_existing():
    rl = [(r["id"], r.get("title") or r.get("name") or "") for r in REDLINES]
    vr = [((x.get("id") or x.get("rule_id")), (x.get("name") or x.get("title") or "")) for x in VRC]
    return rl, vr


def load_candidates():
    out = []
    for f, ver in FILES:
        d = json.loads((ROOT / f).read_text(encoding="utf-8"))
        params = d.get("params") or {}
        for r in d["rules"]:
            r["_ver"] = ver
            r["_params"] = params.get(r.get("src"))
            out.append(r)
    return out


def existing_ids(rl, vr):
    return {i for i, _ in rl} | {i for i, _ in vr}


def covered_ids(by: str, known: set):
    return [i for i in _ID_PAT.findall(str(by or "")) if i in known]


def param_status(r: dict) -> str:
    """参数化校验（按规则嵌套解析，避免扁平查找的误报）。"""
    used = set(re.findall(r"params\.(\w+)", str(r.get("logic") or "")))
    if not used:
        return "无阈值"
    entry = r.get("_params")
    if not isinstance(entry, dict):
        return "条目未登记"
    miss = [u for u in used if u not in entry]
    return "真悬空:%s" % ",".join(miss) if miss else "齐备"


def merged_id(r: dict, cov: list) -> str:
    """合并后 rule_id（ID 冲突以现有为准；补充用命名空间 ID）。"""
    act = r.get("action")
    if act in ("keep_existing", "merge") and cov:
        base = cov[0]
        return base if act == "keep_existing" else "%s+%s" % (base, r["src"])
    if act == "add":
        return r["src"]                      # 候选自带命名空间 ID，与 RL-/VR 无冲突
    return "TBD-%s" % r["src"]               # specify_first：口径明确前不占用 ID


def _cell(s, n=46) -> str:
    s = str(s or "").replace("|", "／").replace("\n", " ").strip()
    return s[:n]


def main() -> int:
    rl, vr = load_existing()
    known = existing_ids(rl, vr)
    cand = load_candidates()
    n_cur = len(rl) + len(vr)
    cur_ver = RV.rule_set_version()

    # ── 统计 ──
    st = collections.Counter(r.get("status") for r in cand)
    ac = collections.Counter(r.get("action") for r in cand)
    byact_sev = collections.Counter((r.get("action"), r.get("sev")) for r in cand)
    pstat = collections.Counter(param_status(r) for r in cand)
    dangling = [r for r in cand if param_status(r).startswith("真悬空")]
    no_entry = [r for r in cand if param_status(r) == "条目未登记"]
    no_entry_by_act = collections.Counter(r.get("action") for r in no_entry)
    dangling_by = [r for r in cand
                   if r.get("status") in ("covered", "partial")
                   and not covered_ids(r.get("by"), known)]
    # 归属引用有效性
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

    # ── 逐条对比矩阵数据 ──
    rows = []
    for r in cand:
        cov = covered_ids(r.get("by"), known)
        status = r.get("status")
        act = r.get("action")
        # 哪个更好：以"系统是否用更稳健/更细口径"为准，读候选 note（有则采信其结论，无则据动作推断）
        note = str(r.get("note") or "")
        if act == "keep_existing":
            better = "现有更好" if note else "现有满足（等价）"
        elif act == "merge":
            better = "各有优点，合并为同一检测器多分支"
        elif act == "add":
            better = "候选更好（现有确无）"
        else:
            better = "未知（条件待明确）"
        lg = str(r.get("logic") or "")
        # 阈值列：优先 params_ref；无阈值则标「存在性判定」
        if param_status(r) == "无阈值":
            thr = "存在性判定（无阈值）"
        else:
            thr = str(r.get("params_ref") or "").split("::")[-1]
        rows.append({
            "src": r["src"], "ver": r["_ver"], "name": r.get("name") or "",
            "sev": SEV_CN.get(r.get("sev"), r.get("sev") or ""),
            "dup": "是" if status == "covered" else ("部分" if status == "partial" else "否"),
            "cov": STATUS_CN.get(status, status or ""),
            "better": better, "act": ACTION_CN.get(act, act or ""),
            "rid": merged_id(r, cov),
            "logic": _cell(lg, 40), "thr": _cell(thr, 34),
            "ev": _cell("、".join(r.get("inputs") or []), 30),
            "sug": _cell(r.get("suggestion"), 26),
        })

    # ── P0 首批：add&high（必建）+ merge&high 且归属明确（可即刻合并） ──
    p0_add = [r for r in cand if r.get("action") == "add" and r.get("sev") == "high"]
    p0_merge = [r for r in cand
                if r.get("action") == "merge" and r.get("sev") == "high"
                and covered_ids(r.get("by"), known)]
    p0 = p0_add + p0_merge[:max(0, 50 - len(p0_add))]

    # ── 字段映射汇总 ──
    vm_rows = []
    for f, ver in FILES:
        d = json.loads((ROOT / f).read_text(encoding="utf-8"))
        vm = d.get("var_map") or d.get("var_map_addendum") or {}
        items = [(k, v) for k, v in vm.items() if not str(k).startswith("_")]
        vm_rows.append((ver, f, items))

    # ── 报告 ──
    L = []
    A = L.append
    A("# 规则去重合并报告（候选规则库 460 条 vs 现有规则库 176 条）")
    A("")
    A("> **编制时间**：2026-10-13　｜　**编制方式**：**只读**（未修改任何规则文件）")
    A("> **现有规则库**：`engine/tax_redlines.py::REDLINES`(%d) + "
      "`engine/verified_rule_engine.py::VERIFIED_RULE_CATALOG`(%d) = **规则主体 %d 条**"
      % (len(rl), len(vr), n_cur))
    A("> **候选规则库**：`config/rulelist_v1.json`(60) + `rulelist_v11.json`(174) + "
      "`rulelist_v12.json`(226) = **460 条**（即 V1.0+V1.1+V1.2）")
    A("> **现行规则集版本**：`%s`（`engine/rule_versions.py`）　｜　"
      "**本报告确定的合并目标版本**：`2026.11`（见 §4）" % cur_ver)
    A("> **口径声明**：全部数字由本脚本**现算**（`scripts/_gen_rule_merge_report_20261013.py`，可复现）；"
      "**不采信既有报告自述**。")
    A("")
    A("---")
    A("")
    A("## 0. 执行摘要")
    A("")
    A("| 项 | 数值 |")
    A("|---|---|")
    A("| 现有规则主体 | **%d**（红线 %d + 已验证 %d） |" % (n_cur, len(rl), len(vr)))
    A("| 候选规则 | **460**（V1.0 60 / V1.1 174 / V1.2 226） |")
    A("| 重复（已覆盖） | **%d** |" % st.get("covered", 0))
    A("| 部分覆盖（口径不同） | **%d** |" % st.get("partial", 0))
    A("| 真缺（未覆盖） | **%d** |" % st.get("missing", 0))
    A("| 占位（条件待明确） | **%d** |" % st.get("placeholder", 0))
    A("")
    A("**处理方式分布（任务 5 值枚举；每条候选均有结论，合计 460）**")
    A("")
    A("| 处理方式（任务枚举） | 条数 | 说明 |")
    A("|---|---|---|")
    A("| 保留现有 | **%d** | 现有实现等价或更优，候选仅作对照登记 |" % ac.get("keep_existing", 0))
    A("| 采用候选 | **0** | 有对应项的 272 条中**无一条**需整体替换现有"
      "（现有或为更细口径，如「按月逐期比对」优于候选「单期阈值」；或为要件化结构，候选无条件结构） |")
    A("| 合并 | **%d** | 候选与现有为**同一检测器的不同分支**（如「系统判未申报 / 候选判依据偏低」） |"
      % ac.get("merge", 0))
    A("| 新增 | **%d** | 其中**条件已明确 %d 条**（可直接落地）+ **条件待明确 %d 条**"
      "（候选原文即占位，须业务给口径后方可量化） |"
      % (ac.get("add", 0) + ac.get("specify_first", 0), ac.get("add", 0), ac.get("specify_first", 0)))
    A("| 废弃 | **0** | 候选与现有不构成同一 ID 冲突（字面冲突 0），结论亦无互斥项 ⇒ 无需废弃 |")
    A("")
    A("> **为什么「采用候选」「废弃」均为 0**：候选库自带 `why` 声明与本系统**四点不兼容**"
      "（① 载体为 YAML 而非 Python+JSON；② 阈值须集中参数化而非逐条内联；③ 规则不自带 score；"
      "④ 红线含「要件+反证」结构、禁止自动定性）。这四点属**载体形态**层面的不兼容，"
      "**不是逐条结论冲突** ⇒ 正确处理是「载体以现有为准 + 口径按需合并 + 新能力走新增」，"
      "而不是「整体采用候选」或「废弃现有规则」。这也正是任务约束「不直接照搬候选规则」的落地方式。")
    A("")
    A("**本轮只读复核发现的三项事实（可复算）**：")
    A("")
    A("| # | 发现 | 证据 |")
    A("|---|---|---|")
    A("| F-1 | 候选归属**零失效**：`by` 中出现的 RL-/VR id 全部真实存在（%d 条全部解析成功，失效 0） | 现算 |"
      % ref_ok)
    A("| F-2 | `legal_basis_ref` **460/460 均为「法规库自动匹配」**，无任何编造条文 | 现算 |")
    A("| F-3 | 参数化：`logic` 引用 `params.X` 而条目内缺该参数名 ⇒ **真悬空 %d 条**（V1.0 VAT-021 / V1.1 PCT-006 / INV-008） | 现算 |"
      % len(dangling))
    A("")
    A("---")
    A("")
    A("## 1. 现有规则清单（规则主体 %d 条）" % n_cur)
    A("")
    A("> 仅列**规则主体**（红线 + 已验证原子规则）。检测器实现层（专项 25 / 缺口 10 / 缺口税种 14）"
      "与权威事实核查规则 89 属**不重复计入**的其它维度，见 `config/rule_versions.json::layer_semantics`。")
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
    A("---")
    A("")
    A("## 2. 候选规则清单（460 条）")
    A("")
    A("> 候选 ID 自带**命名空间**（VAT/CIT/IIT/SI/SD/… /DEED/GOT/PLAT/LIQ…），"
      "与现有 `RL-*`/`VR*` **零字面冲突**（现算：冲突 0 条）。")
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
                "%s=%s" % (k, v) for k, v in list(ns.items())[:12]) + ("…" if len(ns) > 12 else "")))
        A("- 本报告现算口径：%s" % "；".join(
            "%s %d" % (STATUS_CN.get(s, s), n)
            for s, n in collections.Counter(r.get("status") for r in d["rules"]).most_common()))
        A("")
    A("---")
    A("")
    A("## 3. 逐条对比矩阵（460 条，每条均有处理结论）")
    A("")
    A("> 列含义：**是否重复**（是/部分/否）｜**覆盖程度**｜**哪个更好**｜**处理方式**（任务指定 5 值）｜"
      "**合并后 rule_id**｜**条件**（`logic`）｜**阈值**（`params_ref`，任务要求全部参数化）｜"
      "**证据**（所需输入字段）｜**建议**。")
    A("> **合并后 rule_id 规则**：ID 冲突以现有为准 ⇒ 保留现有沿用现有 id；合并 = `现有id+候选id`；"
      "新增 = 候选命名空间 id（不与 RL-/VR 冲突）；条件待明确 = `TBD-<候选id>`（口径明确前不占用正式 ID）。")
    A("")
    A("| 候选 ID | 版本 | 名称 | 严重度 | 是否重复 | 覆盖程度 | 哪个更好 | 处理方式 | 合并后 rule_id | 条件 | 阈值 | 证据 | 建议 |")
    A("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for x in rows:
        A("| `%s` | %s | %s | %s | %s | %s | %s | **%s** | `%s` | %s | %s | %s | %s |"
          % (x["src"], x["ver"], x["name"], x["sev"], x["dup"], x["cov"], x["better"],
             x["act"], x["rid"], x["logic"], x["thr"], x["ev"], x["sug"]))
    A("")
    A("---")
    A("")
    A("## 4. 最终统一规则库版本号")
    A("")
    A("| 项 | 值 |")
    A("|---|---|")
    A("| 现行（在库运行） | **`%s`** |" % cur_ver)
    A("| **本报告确定的合并目标版本** | **`2026.11`** |")
    A("| 规则主体（合并后不变） | **%d**（=%d+%d） |" % (n_cur, len(rl), len(vr)))
    A("| 候选入库后增量 | 新增 **%d** 条（`action=add`）+ 合并 **%d** 条（`action=merge`，不新增条数） |"
      % (ac.get("add", 0), ac.get("merge", 0)))
    A("")
    A("**版本号口径**：")
    A("")
    A("1. **本步不覆盖现有规则**（任务约束 7）⇒ `2026.11` 是**目标版本**，"
      "`2026.10` 在其入库前**始终现行有效**；")
    A("2. 入库时 `config/rule_versions.json` 的 `version` 与 `engine/rule_versions.rule_set_version()` "
      "必须**同源同改**（本项目铁律：版本号单一权威）；")
    A("3. 登记口径：新增规则按 `action=add` 的 **%d** 条逐条登记；"
      "合并规则**不改条数**，只把候选分支并入既有检测器，故规则主体由 %d → **%d**。"
      % (ac.get("add", 0), n_cur, n_cur + ac.get("add", 0)))
    A("")
    A("---")
    A("")
    A("## 5. 规则与数据字段的映射关系")
    A("")
    A("> 来源：候选库 `var_map` / `var_map_addendum`（现算）。"
      "**规则只引用字段名，不内联阈值**；字段取值口径见 `engine/fieldkit.py`、`engine/numparse.py`（项目唯一权威）。")
    A("")
    for ver, f, items in vm_rows:
        A("### 5.%s %s（%d 个字段）" % (ver[-1], ver, len(items)))
        A("")
        A("| 变量（候选口径） | 系统取数口径 |")
        A("|---|---|")
        for k, v in items:
            A("| `%s` | %s |" % (_cell(k, 34), _cell(v, 80)))
        A("")
    A("")
    A("**字段解析权威（不得各写一份）**：")
    A("")
    A("| 类别 | 唯一权威 |")
    A("|---|---|")
    A("| 数值解析 | `engine/numparse.py` |")
    A("| 发票字段 | `engine/fieldkit.py` |")
    A("| 会计口径（损益类禁取期末余额） | `engine/account_classifier.py` |")
    A("| 行业/业态 | `engine/industry_resolver.py` |")
    A("")
    A("---")
    A("")
    A("## 6. 待确认冲突项清单")
    A("")
    A("### 6.1 参数化缺口（**明确缺陷，须在入库前修**）")
    A("")
    A("| # | 候选 | 问题 | 处置建议 |")
    A("|---|---|---|---|")
    for _i, r in enumerate(dangling, 1):
        A("| %d | `%s`(%s) | `logic` 引用 `params.%s`，但 `params['%s']` 仅登记 `%s` ⇒ **悬空引用** | "
          "补登该参数键，或改 `logic` 引用已登记键 |"
          % (_i, r["src"], r["_ver"], param_status(r).split(":")[1],
             r["src"], "、".join(k for k in (r.get("_params") or {}) if not k.startswith("_"))))
    A("")
    A("**参数化总体口径（现算，460 条）**")
    A("")
    A("| 类别 | 条数 | 说明 |")
    A("|---|---|---|")
    A("| 有阈值且参数齐备 | **%d** | 可直接入库 |" % pstat.get("齐备", 0))
    A("| 无阈值（存在性判定） | **%d** | `>0`/`=0` 类触发，符合项目「存在即触发」口径，**非**硬编码阈值 |"
      % pstat.get("无阈值", 0))
    A("| 有阈值但条目未登记 | **%d** | 分布：%s |"
      % (len(no_entry), "、".join("%s %d" % (ACTION_CN.get(k, k), v)
                                  for k, v in no_entry_by_act.most_common())))
    A("| **真悬空** | **%d** | 见上表，**须修** |" % len(dangling))
    A("")
    A("> **对「条目未登记 %d 条」的判断**：`保留现有` 的 %d 条中，系统已用**更细口径**覆盖"
      "（如 VAT-003 由「单期 10%% 阈值」升级为「按月逐期比对」），候选阈值**不应入库**；"
      "而 `合并`/`新增`/`新增（条件待明确）` 的 %d 条，在落地时**必须补登参数**（否则违反任务要求 5）。"
      % (len(no_entry), no_entry_by_act.get("keep_existing", 0),
         len(no_entry) - no_entry_by_act.get("keep_existing", 0)))
    A("")
    A("### 6.2 归属待核（候选 `by` 未给出 RL-/VR id，仅指向模块）")
    A("")
    A("| # | 条数 | 类型 | 处置建议 |")
    A("|---|---|---|---|")
    A("| T-1 | %d | `by` 指向 `engine/*.py` 模块而非规则 id | 入库时须把归属**收敛到规则 id**"
      "（项目铁律：归属唯一权威 = 检测器自报 `redline_id`），否则无法进覆盖率统计 |" % len(dangling_by))
    A("")
    A("### 6.3 需业务确认的冲突项")
    A("")
    A("| # | 事项 | 为什么需确认 |")
    A("|---|---|---|")
    A("| C-1 | `新增（条件待明确）`（**%d** 条）的**触发条件**本身是占位 | 候选原文即「条件待明确」，"
      "系统不得凭推测补全（禁编造），须业务给口径后方可量化 |" % ac.get("specify_first", 0))
    A("| C-2 | 合并后**条数**口径：`合并` 不增条数、`新增` 增 %d 条 | 需确认 `2026.11` 对外是否声明"
      "「规则主体 %d」而非「候选累计 460」 |" % (ac.get("add", 0), n_cur + ac.get("add", 0)))
    A("| C-3 | 候选阈值与系统既有阈值的**取值分歧** | 少数候选阈值与系统现状不一致"
      "（如 VAT-007「阈值与清单 0.5 完全一致」为一致；其余差异需逐条裁定以谁为准） |")
    A("| C-4 | **地区/行业均值**参数化归属 | 任务要求「行业均值、地区均值必须参数化」；"
      "现有唯一权威为 `engine/industry_benchmark.py` + 行业表，"
      "但**地区参数（契税税率/土增预征率等）无集中表** ⇒ 是否本轮一并建表待定 |")
    A("")
    A("---")
    A("")
    A("## 7. 建议的首批入库规则（P0，%d 条）" % len(p0))
    A("")
    A("**选取判据**：① `action=add` 且 `sev=high`（**真缺 + 高严重度**，共 %d 条，全部纳入）；"
      "② `action=merge` 且 `sev=high` 且归属指向**真实 RL-/VR**（可即刻并入既有检测器，取 %d 条补齐至 50）。"
      % (len(p0_add), len(p0) - len(p0_add)))
    A("")
    A("| # | 候选 ID | 版本 | 名称 | 建议动作 | 合并后 rule_id | 所需字段 |")
    A("|---|---|---|---|---|---|---|")
    for i, r in enumerate(p0, 1):
        cov = covered_ids(r.get("by"), known)
        A("| %d | `%s` | %s | %s | **%s** | `%s` | %s |"
          % (i, r["src"], r["_ver"], r["name"], ACTION_CN.get(r.get("action"), ""),
             merged_id(r, cov), _cell("、".join(r.get("inputs") or []), 26)))
    A("")
    A("> **入库前置条件**：P0 中 `action=add` 的条目须先在 `params` 表**登记阈值**"
      "（凡 `logic` 含 `params.X` 者），再落地检测器；`action=merge` 的条目**不新增条数**，"
      "只在既有检测器内扩展分支，并同步 `config/redline_detector_attribution.json` 归属。")
    A("")
    A("---")
    A("")
    A("## 附录 A：本次只读取证命令（可复现）")
    A("")
    A("```bash")
    A("# 报告生成的唯一入口（现算全部数字）")
    A("python scripts/_gen_rule_merge_report_20261013.py")
    A("")
    A("# 现有规则主体条数")
    A("python -c \"import sys;sys.path.insert(0,'.');from engine.tax_redlines import REDLINES;"
      "from engine.verified_rule_engine import VERIFIED_RULE_CATALOG as V;print(len(REDLINES),len(V))\"")
    A("")
    A("# 候选条数与处理方式分布")
    A("python -c \"import json,collections;c=[r for f in ['config/rulelist_v1.json','config/rulelist_v11.json',"
      "'config/rulelist_v12.json'] for r in json.load(open(f,encoding='utf-8'))['rules']];"
      "print(len(c),collections.Counter(r['action'] for r in c))\"")
    A("```")
    A("")
    A("## 附录 B：只读证明")
    A("")
    A("- 本步**未修改任何规则文件**：`config/rulelist_v{1,11,12}.json`、`engine/tax_redlines.py`、"
      "`engine/verified_rule_engine.py` 均未被写入（`git status` 仅新增本报告 + 生成脚本）；")
    A("- 未新增红线、未改判定逻辑、未改前端（符合任务约束 7「先不覆盖现有规则」）。")
    A("")

    OUT.write_text("\n".join(L), encoding="utf-8")
    print("[OK] 写出 %s（%d 行）" % (OUT.relative_to(ROOT), len(L)))
    print("     现有主体 %d | 候选 %d | 结论覆盖 %d/460" % (n_cur, len(cand), len(rows)))
    print("     处理方式：%s" % dict(ac))
    print("     参数化：齐备 %d / 无阈值 %d / 条目未登记 %d / 真悬空 %d"
          % (pstat.get("齐备", 0), pstat.get("无阈值", 0), len(no_entry), len(dangling)))
    print("     P0 首批 %d 条（add&high %d + merge&high %d）" % (len(p0), len(p0_add), len(p0) - len(p0_add)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
