"""P0-5 风险**综合排序分**（多因子加权 0-100）—— **只排序，不定性**。

★★ 与 `engine/risk_levels.py` 的关系（**不得混淆，也不得相互替代**）::

    risk_levels.risk_score_of(等级)  →  等级 ⇒ 分值（**单向派生**，用于**定性**；5 档）
    本模块 score(finding)            →  severity×confidence×金额×频次 加权 ⇒ 综合分
                                        （**只用于排序/展示优先级**；不改等级）

★ 铁律（沿用本项目 `config/risk_scores.json` 既有纪律）：
  **禁止用本分反推定性** —— 综合分**不得写回** `risk_level` / `conclusion_grade` / `verdict`。
  本模块**不修改**传入的 finding（纯函数，返回新字典）。

★ 任务书口径的三档（80-100 高 / 50-79 中 / 0-49 低）登记在
  `config/risk_scoring.json::grade_view`，作为综合分的**分档视图** `priority_grade`。
  **不替换**既有 5 档等级：既有词表有「极高风险」一档，三档视图会把极高降级为高，
  若用它替代等级会**改变结论严重度**（实测确认）。

★ 缺失值处理（缺失≠0）：
  取不到的因子**整项剔除并重算权重**（不是给 0 分），并在结果里如实标
  `factors[].state = missing` 与 `missing_weight`。
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "config", "risk_scoring.json")
_CACHE: Dict[str, Any] = {}


def config() -> Dict[str, Any]:
    """读取评分配置（进程内缓存）。"""
    if "cfg" not in _CACHE:
        with open(_CONFIG_PATH, encoding="utf-8") as fh:
            _CACHE["cfg"] = json.load(fh) or {}
    return _CACHE["cfg"]


def reset_cache() -> None:
    _CACHE.clear()


# ══════════════════════════════════════════════════════════════════════════
# 各因子
# ══════════════════════════════════════════════════════════════════════════
def severity_norm(level: Any, finding: Any = None) -> Optional[float]:
    """基础严重度（0~1）。★ 取既有唯一权威 `risk_levels.risk_score_of`（不另立表）。

    取不到（等级为空 / 证据状态"待核验" / 非风险正向发现）⇒ `None`（**不返回 0**）。
    """
    from engine import risk_levels as RL                      # noqa: PLC0415
    v = RL.risk_score_of(level, finding)
    if v is None:
        return None
    return max(0.0, min(float(v) / 100.0, 1.0))


def _band_value(kind: str, value: Any) -> Optional[float]:
    """按配置分段取系数。分段表**一行一档**（新增档 = 加一行）。"""
    bands = ((config().get("bands") or {}).get(kind) or [])
    try:
        v = float(value)
    except Exception:                                         # noqa: BLE001
        return None
    for b in bands:
        mx = b.get("max")
        if mx is None or v <= float(mx):
            return float(b.get("value"))
    return None


def amount_of(finding: Dict[str, Any]) -> Optional[float]:
    """从 `tax_impact` 取涉税金额合计。`available=false` ⇒ `None`（**不得当 0 元**）。"""
    ti = finding.get("tax_impact")
    if not isinstance(ti, dict) or ti.get("available") is False:
        return None
    items = ti.get("items")
    if isinstance(items, list) and items:
        tot = 0.0
        got = False
        for it in items:
            if not isinstance(it, dict):
                continue
            try:
                tot += float(it.get("amount"))
                got = True
            except Exception:                                 # noqa: BLE001
                continue
        if got:
            return tot
    for key in ("basis", "amount", "total"):
        try:
            return float(ti.get(key))
        except Exception:                                     # noqa: BLE001
            continue
    return None


def frequency_of(finding: Dict[str, Any]) -> Optional[int]:
    """命中频次（同规则命中条目数）。取不到 ⇒ `None`（调用方按下界 1 处理）。"""
    for key in ("finding_count", "hit_count"):
        try:
            return int(finding.get(key))
        except Exception:                                     # noqa: BLE001
            continue
    return None


# ══════════════════════════════════════════════════════════════════════════
# 综合分
# ══════════════════════════════════════════════════════════════════════════
def score(finding: Dict[str, Any]) -> Dict[str, Any]:
    """计算综合排序分。**纯函数**（不改传入的 finding）。

    返回::

        {
          "priority_score": int|None,      # 0-100；全部因子缺失 ⇒ None（缺失≠0）
          "priority_grade": str,           # 任务书三档视图（高/中/低）；无分 ⇒ ""
          "factors": [{name, 中文, value, state, source}...],
          "missing_weight": float,         # 被剔除因子的权重之和
          "score_basis": float,            # 实际参与计算的权重和
          "weights": {…},                  # 参与计算的归一化权重
          "note": str
        }
    """
    cfg = config()
    w = dict(cfg.get("weights") or {})
    fcfg = cfg.get("factors") or {}
    lvl = finding.get("risk_level") or finding.get("level") or ""
    conf = finding.get("confidence")

    # ① 基础严重度
    sv = severity_norm(lvl, finding)
    # ② 置信度
    cv: Optional[float] = None
    try:
        cv = max(0.0, min(float(conf), 1.0))
    except Exception:                                         # noqa: BLE001
        cv = None
    # ③ 金额影响
    amt = amount_of(finding)
    av = _band_value("amount", amt) if amt is not None else None
    # ④ 频次（缺失按下界 1 ⇒ 0.3）
    freq = frequency_of(finding)
    freq_state = "ok"
    if freq is None:
        freq = 1
        freq_state = "default_one"
    fv = _band_value("frequency", freq)

    factors: List[Dict[str, Any]] = []
    used: Dict[str, float] = {}
    missing_w = 0.0
    _spec = [(("severity", sv, "ok"), "基础严重度", "事项等级 → 分值（risk_levels，单向）"),
             (("confidence", cv, "ok"), "置信度", "finding.confidence（0~1）"),
             (("amount", av, "ok"), "金额影响系数", "tax_impact 涉税金额分段"),
             (("frequency", fv, freq_state), "频次系数", "finding_count 分段")]
    for (key, val, state), cn, src in _spec:
        miss = val is None
        factors.append({"name": key, "name_cn": cn,
                        "value": (None if miss else round(float(val), 4)),
                        "state": ("missing" if miss else state),
                        "source": src,
                        "weight": float(w.get(key) or 0.0)})
        if miss:
            missing_w += float(w.get(key) or 0.0)
        else:
            used[key] = float(val)
    basis = 1.0 - missing_w
    if not used or basis <= 0:
        return {"priority_score": None, "priority_grade": "", "factors": factors,
                "missing_weight": round(missing_w, 4), "score_basis": 0.0,
                "weights": {}, "note": "全部因子取不到 ⇒ 不给综合分（缺失≠0）"}
    # ★★ 信息不足 ⇒ **不给分**（实测缺陷，2026-10-13）：
    #   归一化会把"唯一参与因子"放大到 100% 权重 —— 实测「其余因子全缺、仅频次缺省值 0.3」
    #   被算成 **30 分**（呈现为"低"档），是**误导**（那 0.3 还是缺省下界、不是实测值）。
    #   故参与权重和不足 `min_basis` ⇒ 返回 None 并如实标 `insufficient`。
    _min_basis = float((config().get("min_basis") or 0.5))
    if basis < _min_basis:
        return {"priority_score": None, "priority_grade": "", "factors": factors,
                "missing_weight": round(missing_w, 4), "score_basis": round(basis, 4),
                "weights": {}, "status": "insufficient",
                "note": ("参与计算的权重和 %.2f 低于下限 %.2f ⇒ 信息不足，不给综合分"
                         "（避免用缺省值放大成分数）。%s"
                         % (basis, _min_basis, "缺失因子以 0 分顶替属禁止行为。"))}
    # 重算归一化权重
    norm = {k: (float(w.get(k) or 0.0) / basis) for k in used}
    raw = sum(norm[k] * v for k, v in used.items())
    score_v = int(round(max(0.0, min(raw, 1.0)) * 100))
    return {
        "priority_score": score_v,
        "priority_grade": grade_view_of(score_v),
        "factors": factors,
        "missing_weight": round(missing_w, 4),
        "score_basis": round(basis, 4),
        "weights": {k: round(v, 4) for k, v in norm.items()},
        "status": "ok",
        "note": ("综合排序分：只作排序/展示优先级，**不得反推定性**"
                 "（等级唯一权威 engine/risk_levels.py）。"),
    }


def grade_view_of(priority: Any) -> str:
    """综合分 → 任务书**三档视图**（高/中/低）。取不到 ⇒ 空串（缺失≠默认档）。"""
    try:
        p = float(priority)
    except Exception:                                         # noqa: BLE001
        return ""
    for b in ((config().get("grade_view") or {}).get("bands") or []):
        lo, hi = float(b.get("min")), float(b.get("max"))
        if lo <= p <= hi:
            return str(b.get("grade") or "")
    return ""


def grade_view_bands() -> List[Dict[str, Any]]:
    """三档视图的定义（供前端，不在前端硬编码阈值）。"""
    return list(((config().get("grade_view") or {}).get("bands") or []))


def stamp(finding: Dict[str, Any]) -> Dict[str, Any]:
    """给 finding **追加**排序分字段（返回新字典；**不覆盖任何既有字段**）。"""
    out = dict(finding)
    r = score(finding)
    out["priority_score"] = r["priority_score"]
    out["priority_grade"] = r["priority_grade"]
    out["priority_factors"] = r["factors"]
    out["priority_note"] = r["note"]
    return out


def stamp_all(findings: Any) -> List[Dict[str, Any]]:
    return [stamp(f) for f in (findings or []) if isinstance(f, dict)]


def metadata() -> Dict[str, Any]:
    """评分配置字典（前端中文名唯一来源）。"""
    cfg = config()
    return {
        "weights": cfg.get("weights") or {},
        "weights_cn": cfg.get("weights_cn") or {},
        "factors": cfg.get("factors") or {},
        "bands": cfg.get("bands") or {},
        "grade_view": cfg.get("grade_view") or {},
        "excluded_note": cfg.get("excluded_note") or "",
        "note": cfg.get("note") or "",
        "order": ["severity", "confidence", "amount", "frequency"],
    }


__all__ = ["config", "reset_cache", "severity_norm", "amount_of", "frequency_of",
           "score", "grade_view_of", "grade_view_bands", "stamp", "stamp_all", "metadata"]
