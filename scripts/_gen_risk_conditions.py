# -*- coding: utf-8 -*-
"""风险指标配置生成器：为每条红线生成 `trigger_conditions` + `determination_criteria(is_precondition)`。

## 为什么要生成（而不是手抄 91 条）
用户规格（2026-10-07）要求"认定要件表增加 `is_precondition` 字段（标记前提条）"，
且"新增风险指标时必须同时定义触发条件和认定要件"。
手抄 91 条红线既易漏又易漂移；此处从**唯一权威 `engine.tax_redlines`** 派生，
**派生规则是显式、可审计的**（见下），产出 `config/risk_conditions.json` 作为**可手改的数据表**。

## `is_precondition` 的派生规则（唯一权威，写在这里也写进产物的 note）
前提条（现象条）= "该现象出现即列为疑点、不需要再满足附加条件"的那一条认定要件。
  ① **显式声明优先**：要件文本含 `trigger_conditions.PREMISE_MARKERS`（现象/前提条/存在即成立…）⇒ true。
  ② **存在性判据**：该要件是认定要件的**第 1 条**，且文本是**存在性判据**——
     含存在性语（存在/发生/出现/差异/不符/不一致/不闭合/不匹配/未…）且**不含数值门槛语**
     （超过/低于/高于/不少于/比例达到/金额达到/倍/百分比…）⇒ true。
     依据：认定要件序列里，"现象"必然排在最前（它是触发条件在要件侧的镜像）；
     带数值门槛的那条是**第二层认定**，不是前提。
  ③ 其余 ⇒ false。
  ⚠ 规则只用于**生成初值**；`config/risk_conditions.json` 一旦生成即为**数据权威**，
    人工可逐条修订（如某红线确不适合，改该行 `is_precondition`），**不必改代码**。

## 触发条件（trigger_conditions）的派生
每条红线的触发条件 = **该疑点为何被列为疑点**的声明。系统在疑点详情里已统一写为
「凡出现上述情形即纳入检查范围」，故触发条件取**第 1 条认定要件的现象描述**（同一现象的两侧表述），
并标 `auto: true`（表示由系统自动判定命中，无需人工勾选）。
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.trigger_conditions import PREMISE_MARKERS  # noqa: E402

#: 存在性语（现象条的典型措辞）
EXISTENCE_WORDS = ("存在", "发生", "出现", "差异", "不符", "不一致", "不闭合", "不匹配",
                   "未", "缺", "无", "短", "漏", "少", "异常", "偏离", "背离", "矛盾",
                   "不实", "未取得", "未履行", "列支", "列示",
                   # ★ 2026-10-07 扩充：这些也是"现象/存在性"表述（实测漏判 RL-SPT-017
                   #   「企业提供广告服务…取得收入」——它显然是被列示的现象，却因词表未覆盖而漏判）
                   "提供", "取得", "收付", "收取", "支付", "发生额", "形成", "签署",
                   "变动", "结转", "计入", "挂账", "开票", "申报", "缴纳", "缴存")
#: 数值门槛语（有它 ⇒ 该条属"第二层认定"，不是前提条）
THRESHOLD_WORDS = ("超过", "低于", "高于", "不少于", "不超过", "达到", "比例", "百分比",
                   "倍", "金额≥", "金额>", "≥", "≤", "阈值", "占比", "率超", "万元以上",
                   "元以上", "下限", "上限", "不得低于")


def is_existence_criterion(text: Any) -> bool:
    """该要件是否为**存在性判据**（现象条候选）。"""
    s = str(text or "")
    if not s:
        return False
    if any(w in s for w in THRESHOLD_WORDS):
        return False
    return any(w in s for w in EXISTENCE_WORDS)


def _marker_premise(text: Any) -> bool:
    return any(m in str(text or "") for m in PREMISE_MARKERS)


def _clean(desc: Any) -> str:
    """要件描述归一：去掉"——本项为现象/前提条…"这类注解尾巴，保留判据本体。"""
    s = str(desc or "").strip()
    s = re.split(r"——", s)[0].strip()
    return s


def build_entry(redline: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """单条红线 → 配置条目；无认定要件则返回 None。"""
    rid = str(redline.get("id") or "").strip()
    if not rid:
        return None
    cons = redline.get("constituents") or redline.get("indicator_constituents") or []
    if not isinstance(cons, list) or not cons:
        return None
    tcs: List[Dict[str, Any]] = []
    cps: List[Dict[str, Any]] = []
    for i, c in enumerate(cons, start=1):
        desc = _clean(c)
        pre = _marker_premise(c) or (i == 1 and is_existence_criterion(c))
        cps.append({"id": "C%d" % i, "desc": desc, "is_precondition": bool(pre)})
        if i == 1:
            tcs.append({"id": "T1", "desc": desc, "auto": True})
    if not cps:
        return None
    return {
        "risk_code": rid,
        "name": str(redline.get("name") or redline.get("title") or "")[:60],
        "trigger_conditions": tcs,
        "determination_criteria": cps,
    }


def _existing_manual_entries(derived_codes: set) -> Dict[str, Any]:
    """读旧配置里**非派生**的人工条目与人工字段（**必须原样保留**）。

    ★ 实测事故（2026-10-07，本批收口时发现）：本脚本是"纯覆盖"，而
      「无红线/规则键控的发现」是按 `aliases` **人工登记**进 `config/risk_conditions.json` 的
      （`VR012` / `VR019` / `SYN-MULTI-TAX-PROFILE`）。跑一次生成器 ⇒ 这 3 条**被静默删掉**
      （94 → 91），随之"触发源绑定 16/16"退化回 13/16（那 3 个疑点又走内联兜底 WARN）。
      与 `scripts/_gen_data_sources.py` 的"人工撰写字段原样保留"同一纪律 —— 两个生成器必须同款。
    """
    kept: Dict[str, Any] = {"manual": [], "aliases": {}}
    try:
        old = json.loads((ROOT / "config" / "risk_conditions.json").read_text(encoding="utf-8"))
    except Exception:                         # 首跑无旧文件，属正常路径
        return kept
    for r in (old.get("risks") or []):
        if not isinstance(r, dict):
            continue
        rc = str(r.get("risk_code") or "")
        if not rc:
            continue
        al = r.get("aliases")
        if al:
            kept["aliases"][rc] = al
        if rc not in derived_codes:           # 人工条目（无红线/规则键控的发现）
            kept["manual"].append(r)
    return kept


def main() -> int:
    import engine.tax_redlines as tr
    # 收集全部红线（兼容多种容器形态）
    redlines: List[Dict[str, Any]] = []
    seen: set = set()
    for nm in dir(tr):
        v = getattr(tr, nm)
        seq = v if isinstance(v, list) else (list(v.values()) if isinstance(v, dict) else None)
        if not seq:
            continue
        for r in seq:
            if isinstance(r, dict) and r.get("id") and "constituents" in r:
                rid = str(r["id"])
                if rid not in seen:
                    seen.add(rid)
                    redlines.append(r)
    redlines.sort(key=lambda r: str(r.get("id")))
    entries = [e for e in (build_entry(r) for r in redlines) if e]
    # ★ 人工撰写层：保留 aliases 字段 + 非派生的人工条目（见 `_existing_manual_entries`）
    kept = _existing_manual_entries({str(e.get("risk_code")) for e in entries})
    for e in entries:
        al = kept["aliases"].get(str(e.get("risk_code")))
        if al:
            e["aliases"] = al
    entries.extend(kept["manual"])
    out = {
        "schema": 1,
        "version": "1.0.0",
        "updated": "2026-10-07",
        "note": ("风险指标配置（触发条件与认定要件分离）。唯一权威=本文件；由 "
                 "`scripts/_gen_risk_conditions.py` 从 `engine.tax_redlines` 派生。"
                 "is_precondition 派生规则：①要件文本含 PREMISE_MARKERS；"
                 "②或为认定要件第1条且属存在性判据（含存在性语、不含数值门槛语）。"
                 "人工可逐条修订本文件，无需改代码。"
                 "★ 2026-10-07：新增 `aliases` 字段——无红线/规则键控的发现（VR 规则、综合画像）"
                 "按发现标记名登记，使其同样获得已登记的触发条件与认定要件；"
                 "**该字段与本类条目由生成器原样保留（不会被重生成覆盖）**。"),
        "fields": ["risk_code", "name", "aliases", "trigger_conditions", "determination_criteria"],
        "criterion_fields": ["id", "desc", "is_precondition"],
        "trigger_fields": ["id", "desc", "auto"],
        "risks": entries,
    }
    p = ROOT / "config" / "risk_conditions.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    n_pre = sum(1 for e in entries for c in e["determination_criteria"] if c["is_precondition"])
    n_al = sum(1 for e in entries if e.get("aliases"))
    print("已生成 %s：%d 条风险指标（红线派生 %d + 人工登记 %d）；标记前提条 %d 条；含 aliases %d 条"
          % (p.name, len(entries), len(entries) - len(kept["manual"]), len(kept["manual"]),
             n_pre, n_al))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
