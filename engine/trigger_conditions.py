# -*- coding: utf-8 -*-
"""触发条件与认定要件**分离**（Skill 1 唯一权威）。

## 为什么要分开
用户复核（2026-10-07，疑点1）：
  报告同时写着「经核对，本企业**未涉及任何一条构成要件**」与「共13张发票涉及红冲/作废：
  其中红字发票（红冲）13张、作废0张」；而第1条要件原文是
  「存在红字发票或作废发票（红冲行为）——本项为现象/前提条，存在即成立」。
  **已检出 13 张红字发票 ⇒ 第1条已满足**，却写「未涉及任何一条构成要件」。
根因（架构级）：**"触发条件"与"认定要件"在实现里是同一个东西** ——
  要件核对器找不到"针对该要件的核对证据"就判 `not_concluded`（未形成核对结论），
  而**现象/前提条的"证据"就是触发信号本身**（存在即成立），根本不需要另找核对证据。

## 三条概念（本模块是它们的唯一解析点）
1. **触发条件**：出现什么信号就把本项**列为疑点**（不设阈值；如"存在红冲/作废发票"）。
2. **认定要件**：满足什么条件才**认定风险成立**（逐条核对，可能有数值门槛）。
3. **结论分层**：
   · 触发条件命中 ⇒ **疑点成立**（这是"列入检查"的依据，不是"违法"的认定）。
   · 认定要件全部满足 ⇒ 风险成立；否则 ⇒ **风险是否成立待定**。

## 口径
- **前提条（现象/存在性要件）**：声明里含「现象/前提条」「存在即成立」之一即认定；
  其满足判据 = **本疑点因检出该现象而列示**（触发条件已命中），
  故结论必须写「**符合情形**」，**不得**写「未形成核对结论」。
- 判定依据是**文本声明**（红线条目里写明），本模块只按词表识别，**不针对任何一条具体红线**；
  新增同类要件只需在红线文案里写明"现象/前提条"，无需改代码。

## 与既有权威的关系（不重复实现）
- 要件**逐条结论**：`engine.constituent_checkpoint`（本模块只提供"是否前提条"的判定与措辞）。
- 要件**数值门槛**：`engine.constituent_threshold`。
- 红线**声明**：`engine.tax_redlines`。
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

VERSION = "1.1.0"

_ROOT = Path(__file__).resolve().parent.parent

#: 「现象/前提条」的识别词表（**数据驱动**：新增同类只加一行，不改逻辑）
PREMISE_MARKERS: tuple = (
    "现象/前提条",
    "前提条",
    "存在即成立",
    "存在即纳入",
    "属于现象条",
)

#: 结论分层的标准措辞（报告只引用这里，禁止各处自写）
CONCLUSION_PREMISE_OK = "符合情形"
SAY_TRIGGER = "本项因触发条件「%s」而列为疑点。"
SAY_ROLLUP = "认定要件共 %d 条：已满足 %d 条、待核实 %d 条。"
SAY_SUSPICION_OK = "**疑点成立**（触发条件已命中；这是「列入检查」的依据，不等于违法认定）。"
SAY_RISK_PENDING = "**风险是否成立待定**：须待上述待核实要件核对完毕后方可认定。"
SAY_RISK_OK = "**风险成立**：认定要件已全部满足。"


def is_premise_constituent(text: Any) -> bool:
    """该要件是否为**现象/前提条**（存在即成立）—— **仅按文本词表**（兜底用）。

    判据：声明文本里出现 `PREMISE_MARKERS` 任一词。
    ⚠ 优先使用**结构化判定** `is_precondition(risk_code, index, text)`：
      实测 疑点3/4/12 的第1条要件（"…存在差异"/"…不闭合"）**文本里没有"现象/前提条"字样**，
      仅靠本词表会漏判 ⇒ 结构化 `is_precondition` 才是权威，本函数只做兜底。
    """
    s = str(text or "")
    return any(m in s for m in PREMISE_MARKERS)


# ══════════════ 结构化判定（权威）：config/risk_conditions.json ══════════════
_COND_CACHE: Optional[Dict[str, Any]] = None
_COND_PATH = _ROOT / "config" / "risk_conditions.json"


def load_risk_conditions() -> Dict[str, Any]:
    """风险指标配置（触发条件 + 认定要件 + `is_precondition`）。唯一权威文件。"""
    global _COND_CACHE
    if _COND_CACHE is None:
        try:
            raw = json.loads(_COND_PATH.read_text(encoding="utf-8"))
            _COND_CACHE = raw if isinstance(raw, dict) else {}
        except Exception:            # 留痕：配置缺失 ⇒ 空表（下游按词表兜底，不静默改判）
            _COND_CACHE = {}
    return _COND_CACHE


def risk_entry(risk_code: Any) -> Optional[Dict[str, Any]]:
    """按 `risk_code`（本项目即红线编号 RL-*）取配置条目。"""
    rc = str(risk_code or "").strip()
    if not rc:
        return None
    for r in (load_risk_conditions().get("risks") or []):
        if not isinstance(r, dict):
            continue
        if str(r.get("risk_code")) == rc:
            return r
        # ★ 2026-10-07：**别名匹配** —— 有些发现是"VR 规则/综合画像"键控，红线与 rule_id 都为空，
        #   报告层只能拿到**发现标记名**。把这些发现按 `aliases` 登记进配置表（数据驱动），
        #   即可让它们获得**已登记的触发条件与认定要件**（而非仅靠内联兜底）。
        for a in (r.get("aliases") or []):
            if str(a).strip() == rc:
                return r
    return None


def trigger_conditions_of(risk_code: Any) -> List[Dict[str, Any]]:
    e = risk_entry(risk_code) or {}
    return [t for t in (e.get("trigger_conditions") or []) if isinstance(t, dict)]


def determination_criteria_of(risk_code: Any) -> List[Dict[str, Any]]:
    e = risk_entry(risk_code) or {}
    return [c for c in (e.get("determination_criteria") or []) if isinstance(c, dict)]


def is_precondition(risk_code: Any, index: int, text: Any = "") -> bool:
    """**唯一权威**：该认定要件是否为前提条（现象条）。

    判定顺序：
      ① 结构化配置命中（`config/risk_conditions.json` 的 `is_precondition`）⇒ 用它；
      ② 配置里查不到该条 ⇒ 退回文本词表 `is_premise_constituent(text)`。
    """
    try:
        i = int(index)
    except Exception:
        i = 0
    for c in determination_criteria_of(risk_code):
        if str(c.get("id")) == "C%d" % i:
            return bool(c.get("is_precondition"))
    return is_premise_constituent(text)


def premise_indices_of(risk_code: Any, constituents: Sequence[Any] = ()) -> List[int]:
    """前提条序号（1 基）：优先结构化配置，配置缺失时按词表扫文本。"""
    cps = determination_criteria_of(risk_code)
    if cps:
        return [i for i, c in enumerate(cps, start=1) if c.get("is_precondition")]
    return premise_indices(constituents)


def trigger_status(risk_code: Any, hit_evidence: Any = None,
                   listed: bool = True, *, fallback_desc: str = "") -> Dict[str, Any]:
    """触发条件命中状态。

    `hit_evidence`：本次触发该疑点的**读数**（如"共13张红发发票"/"工资6人、社保5人"）。
    口径：**疑点一旦被列示（listed=True），即说明触发条件已命中**——
    这正是"出现什么信号就列为疑点"的定义；读数用于**留痕**，不作为再判门槛。
    """
    tcs = trigger_conditions_of(risk_code)
    # ★ 2026-10-07：**兜底触发条件** —— 有疑点但不是"红线编号"键控的（如 VR 规则发现：
    #   `rule_id=VR012` 而 `redline_id` 为空）⇒ 配置里查不到条目。
    #   此时**必须以该发现自身的触发信号**作为触发条件，否则会违反用户验收
    #   「不得出现"已列为疑点"但"未触发任何触发条件"」——实测 3 个疑点即此情形。
    #   口径：`fallback_desc` = 触发该发现的规则/信号描述（调用方传入），命中状态同 `listed`。
    if not tcs and str(fallback_desc or "").strip():
        tcs = [{"id": "T1", "desc": str(fallback_desc).strip()[:80], "auto": True}]
    ev = str(hit_evidence or "").strip()
    out: List[Dict[str, Any]] = []
    for t in tcs:
        out.append({"id": str(t.get("id") or ""), "desc": str(t.get("desc") or ""),
                    "auto": bool(t.get("auto", True)),
                    "hit": bool(listed), "evidence": ev})
    return {"risk_code": str(risk_code or ""), "conditions": out,
            "hit_count": sum(1 for x in out if x["hit"]), "listed": bool(listed)}



def premise_indices(constituents: Sequence[Any]) -> List[int]:
    """要件列表里**前提条**的序号（**1 基**，与项目要件序号口径一致）。"""
    return [i for i, c in enumerate(constituents or [], start=1) if is_premise_constituent(c)]


def trigger_text(constituents: Sequence[Any], redline_name: str = "",
                 reading: str = "", risk_code: Any = "") -> str:
    """触发条件文本（报告首句用）。

    取**第一条前提条**的要件原文作为触发条件描述（它本身就是"出现什么信号"的声明）；
    红线未声明前提条时，退回红线名称 + 本轮读数。
    """
    # ★ 结构化触发条件优先（config/risk_conditions.json 的 trigger_conditions[0].desc）
    tcs = trigger_conditions_of(risk_code)
    if tcs and str(tcs[0].get("desc") or "").strip():
        return SAY_TRIGGER % str(tcs[0]["desc"]).strip()
    cps = list(constituents or ())
    for i in premise_indices(cps):
        base = str(cps[i - 1])
        base = base.split("——")[0].strip(" ；;。")
        return SAY_TRIGGER % base
    nm = str(redline_name or "").strip() or "本项风险指标"
    tail = ("（本轮读数：%s）" % reading) if str(reading or "").strip() else ""
    return SAY_TRIGGER % (nm + tail)


def rollup(checkpoints: Iterable[Dict[str, Any]],
           constituents: Sequence[Any] = (),
           risk_code: Any = "") -> Dict[str, Any]:
    """认定要件口径汇总。

    返回 `{total, satisfied, pending, not_applicable, premise_total,
            premise_satisfied, suspicion_ok, risk_ok}`。
    - `satisfied`：结论为「符合情形」的要件数（含已满足的前提条）。
    - `pending`：**待核实** = 未形成核对结论 / 未单独核对 / 有信号但未达门槛。
      （"已核对且未发现符合"**不属于**待核实 —— 那是已闭合的结论。）
    - `risk_ok`：要件全部满足或全部闭合且无待核实。
    前提条序号优先取**结构化配置**（`risk_code`），配置缺失时退回文本词表。
    """
    cps = [c for c in (checkpoints or []) if isinstance(c, dict)]
    total = len(cps)
    satisfied = sum(1 for c in cps if c.get("_conclusion") == "checked_hit")
    closed_miss = sum(1 for c in cps if c.get("_conclusion") == "checked_miss")
    na = sum(1 for c in cps if c.get("_conclusion") == "not_applicable")
    pending = sum(1 for c in cps
                  if c.get("_conclusion") in ("not_concluded", "not_checked", "threshold_unmet"))
    idx = premise_indices_of(risk_code, constituents) if risk_code \
        else premise_indices(constituents)
    premise_total = sum(1 for c in cps if int(c.get("index") or 0) in idx)
    premise_satisfied = sum(1 for c in cps
                            if int(c.get("index") or 0) in idx
                            and c.get("_conclusion") == "checked_hit")
    return {
        "total": total,
        "satisfied": satisfied,
        "closed_miss": closed_miss,
        "pending": pending,
        "not_applicable": na,
        "premise_total": premise_total,
        "premise_satisfied": premise_satisfied,
        "suspicion_ok": bool(premise_total and premise_satisfied == premise_total)
                        or bool(total and satisfied),
        "risk_ok": bool(total and pending == 0 and satisfied > 0),
        "premise_indices": idx,
    }


def verdict_sentence(checkpoints: Iterable[Dict[str, Any]],
                     constituents: Sequence[Any] = (),
                     redline_name: str = "", reading: str = "",
                     risk_code: Any = "") -> str:
    """报告标准结论句（触发条件 → 要件汇总 → 疑点/风险分层）。

    统一由本函数产出，**禁止各处自写同类句子**（防措辞漂移与"未涉及任何一条"病句复发）。
    措辞按用户规格（2026-10-07）：三项顺序为
      ① 本项因触发条件 X 而列为疑点；② 认定要件共 N 条，已满足 M 条，待核实 K 条；
      ③ 疑点成立 / 风险是否成立待定。
    """
    r = rollup(checkpoints, constituents, risk_code)
    if not r["total"]:
        return ""
    parts = [trigger_text(constituents, redline_name, reading, risk_code),
             SAY_ROLLUP % (r["total"], r["satisfied"], r["pending"])]
    if r["not_applicable"]:
        parts.append("另有 %d 条本业态不适用（不计入待核实）。" % r["not_applicable"])
    parts.append(SAY_RISK_OK if r["risk_ok"] else SAY_SUSPICION_OK)
    if not r["risk_ok"]:
        parts.append(SAY_RISK_PENDING)
    return "".join(parts).replace('"', "「").replace('"', "」")


def classify(risk_code: Any, checkpoints: Iterable[Dict[str, Any]],
             constituents: Sequence[Any] = (), *, reading: str = "",
             listed: bool = True, fallback_desc: str = "") -> Dict[str, Any]:
    """**用户规格要求的输出字段**（一次产出，供报告与门禁共用）。

    返回：
      `risk_code`              风险编码（本项目即红线编号）
      `trigger_conditions`     触发条件清单（含 auto 标记）
      `trigger_status`         每条触发条件的命中状态（含读数）
      `determination_criteria` 认定要件清单（含 `is_precondition`）
      `criterion_status`       每条认定要件的核对状态（含结论枚举与展示结论）
      `suspicion_established`  疑点是否成立（bool）
      `risk_established`       风险是否成立（bool）
      `conclusion`             结论表述（标准句）
    """
    cps = [c for c in (checkpoints or []) if isinstance(c, dict)]
    r = rollup(cps, constituents, risk_code)
    ts = trigger_status(risk_code, reading, listed=listed, fallback_desc=fallback_desc)
    crits: List[Dict[str, Any]] = []
    for c in cps:
        i = int(c.get("index") or 0)
        crits.append({
            "id": "C%d" % i,
            "desc": str(c.get("要件") or "")[:200],
            "is_precondition": is_precondition(risk_code, i, c.get("要件")),
            "status": str(c.get("_conclusion") or ""),
            "status_text": str(c.get("核对结论") or ""),
            "independent_source": str(c.get("独立数据源") or ""),
        })
    # ★★ 2026-10-07（用户验收「补做3」的**根因修复**）：**无核对记录时退回配置里的认定要件**。
    #   事故：疑点2/10/11 这 3 个"无红线绑定的综合/规则发现"**没有构成要件** ⇒ 没有核对记录
    #   ⇒ 结构化块里 `determination_criteria = []`（实测 0 条），而**配置里其实各有 1 条 C1 前提条**
    #   ⇒ "配置有、产物没有"，读者与门禁都看不出该疑点该核哪条。
    #   口径（与用户规格第 6 条一致）：
    #     · 前提条（is_precondition）且**触发已命中**（现象已检出）⇒ `checked_hit` + 「符合情形」；
    #     · 其余要件 ⇒ `not_checked`，如实写明"本项未绑定构成要件，本轮未作逐条核对"（不判"未发现符合"）。
    #   这样 `determination_criteria` 与配置**同源**，门禁 TDS-⑦（要件↔状态一一对应）
    #   与 TDS-⑧（前提条必须写符合情形）对这 3 个疑点同样生效。
    if not crits:
        _hit_any = int(ts.get("hit_count") or 0) > 0
        for _c in determination_criteria_of(risk_code):
            _is_pre = bool(_c.get("is_precondition"))
            _ok = _is_pre and _hit_any
            crits.append({
                "id": str(_c.get("id") or ("C%d" % (len(crits) + 1))),
                "desc": str(_c.get("desc") or "")[:200],
                "is_precondition": _is_pre,
                "status": "checked_hit" if _ok else "not_checked",
                "status_text": ("符合情形（这项属于现象/前提条，存在即成立）" if _ok else
                                "未单独核对（本项为综合/规则发现、未绑定构成要件，"
                                "本轮未作逐条核对）"),
                "independent_source": "",
            })
    return {
        "risk_code": str(risk_code or ""),
        "trigger_conditions": ts["conditions"],
        "trigger_status": {"hit_count": ts["hit_count"], "listed": ts["listed"],
                           "conditions": ts["conditions"]},
        "determination_criteria": crits,
        "criterion_status": {c["id"]: {"status": c["status"], "text": c["status_text"],
                                       "is_precondition": c["is_precondition"]} for c in crits},
        # ★ 用户规格：触发条件命中 ⇒ 疑点成立；**风险成立**须认定要件全部闭合且无待核实
        "suspicion_established": bool(ts["hit_count"] > 0) and listed,
        "risk_established": bool(r["risk_ok"]),
        "rollup": {k: v for k, v in r.items() if k != "premise_indices"},
        "conclusion": verdict_sentence(cps, constituents, reading=reading, risk_code=risk_code),
    }



__all__ = ["VERSION", "PREMISE_MARKERS", "is_premise_constituent", "premise_indices",
           "is_precondition", "premise_indices_of", "load_risk_conditions", "risk_entry",
           "trigger_conditions_of", "determination_criteria_of", "trigger_status", "classify",
           "trigger_text", "rollup", "verdict_sentence",
           "CONCLUSION_PREMISE_OK", "SAY_TRIGGER", "SAY_ROLLUP",
           "SAY_SUSPICION_OK", "SAY_RISK_PENDING", "SAY_RISK_OK"]
