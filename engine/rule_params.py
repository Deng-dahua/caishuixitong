# -*- coding: utf-8 -*-
"""规则判定阈值读取器 —— **唯一读取权威**（数据表 `config/rule_params.json`）。

## 为什么单独一个模块
阈值此前**硬编码在各检测器的算式里**（`engine/verified_rule_engine.py` 的 VR038/039/040、
`engine/deduction_limit_detector.py` 的四个 `_*_RATE`）⇒ 改一处漏一处 = 同一条规则两个答案。
本模块把**读取路径收敛为一个入口**，检测器只写 `rule_params.value("<参数名>")`。

## 三条纪律（违反即事故）
1. **取不到不兜底**：参数未登记 ⇒ 返回 `None`（**绝不返回 0**）。调用方拿到 `None`
   必须**跳过该项判定并留痕**（项目铁律：缺失≠0；用 0 当阈值会让"无上限"变成"任何金额都超限"）。
2. **不在本模块写任何阈值字面量**：唯一权威永远是数据表；本模块只做读取。
3. **不猜参数名**：`value()` 只接受表内登记的名字；未登记时可选 `strict=True` 直接抛错，
   用于"该参数必须有"的场景（如检测器启动自检），避免静默全表默认。

## 与相邻模块的分工
- `engine/numparse.py`     —— 数值**文本**解析（"12,000.00" → 12000.0）
- `engine/rule_params.py`  —— 阈值**配置**读取（本模块）
- 二者不同层，**不得互相替代**。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parents[1]
_CFG = _ROOT / "config" / "rule_params.json"

_CACHE: Optional[Dict[str, Any]] = None
#: 已报告过的缺失参数名（去重，避免同一缺失在循环里刷屏）
_MISSING_SEEN: set = set()


def _load() -> Dict[str, Any]:
    """读表（惰性 + 缓存）。读不出来 ⇒ 空表并留痕，**不抛**（避免整轮分析崩）。"""
    global _CACHE
    if _CACHE is None:
        try:
            _CACHE = json.loads(_CFG.read_text(encoding="utf-8")).get("params") or {}
        except Exception as exc:                                  # noqa: BLE001
            print(f"[rule_params] ⚠ 阈值表读取失败（{type(exc).__name__}: {exc}）"
                  f"⇒ 本轮所有阈值判定将跳过（不用默认值顶替）")
            _CACHE = {}
    return _CACHE


def reset_cache() -> None:
    """清缓存（改了数据表后调用；与 `legal_version.reset_caches` 同模式）。"""
    global _CACHE
    _CACHE = None
    _MISSING_SEEN.clear()


def entry(name: str) -> Dict[str, Any]:
    """取某参数的**完整登记条目**（含 cn/value/legal_basis/engine_wired）。未登记 ⇒ 空 dict。"""
    v = _load().get(name)
    return v if isinstance(v, dict) else {}


def value(name: str, strict: bool = False) -> Any:
    """取参数值。

    - 未登记 / 值为 null ⇒ `None`（**不兜底**），并留痕一次；
    - `strict=True` ⇒ 直接抛 `KeyError`（用于"该参数必须有"的启动自检）。
    """
    e = entry(name)
    if "value" not in e or e.get("value") is None:
        if strict:
            raise KeyError(f"阈值参数 `{name}` 未登记（唯一权威 config/rule_params.json）"
                           f"⇒ 该检测器不得启动")
        if name not in _MISSING_SEEN:
            _MISSING_SEEN.add(name)
            print(f"[rule_params] ⚠ 阈值参数 `{name}` 未登记 ⇒ 相关判定**跳过**"
                  f"（不用默认值顶替；请补 config/rule_params.json 一行）")
        return None
    return e.get("value")


def ratio(name: str, strict: bool = False) -> Optional[float]:
    """取**比例/倍数**型阈值（int/float 归一为 float）。取不到 ⇒ `None`。"""
    v = value(name, strict=strict)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):                               # noqa: BLE001
        print(f"[rule_params] ⚠ 阈值参数 `{name}` 的值 {v!r} 不是数值 ⇒ 判定跳过")
        return None


def used_by(name: str) -> List[str]:
    """该参数被哪些规则/检测器引用（用于报告溯源与改动影响面评估）。"""
    u = entry(name).get("used_by")
    return list(u) if isinstance(u, list) else []


def params_of(rule_id: str) -> List[str]:
    """反查：某规则引用了哪些阈值参数名（新增规则时用）。"""
    return [k for k, v in _load().items()
            if isinstance(v, dict) and rule_id in (v.get("used_by") or [])]


def engine_wired(name: str) -> bool:
    """该参数**是否真被引擎检测器按此阈值判定**（false ⇒ 仅登记，**不得宣称已接入**）。"""
    return bool(entry(name).get("engine_wired"))


def audit_snapshot() -> Dict[str, Any]:
    """现算快照（供闸门/报告使用，**不写盘、不臆造**）。"""
    t = _load()
    wired = [k for k, v in t.items() if isinstance(v, dict) and v.get("engine_wired")]
    notw = [k for k, v in t.items() if isinstance(v, dict) and not v.get("engine_wired")]
    return {"total": len([k for k in t if not k.startswith("_")]),
            "engine_wired": len(wired), "not_wired": len(notw),
            "not_wired_names": sorted(notw),
            "names": sorted(k for k in t if not k.startswith("_"))}
