# -*- coding: utf-8 -*-
"""**风险族**配置的唯一权威（2026-10-07，用户第 3 批 任务2）。

## 口径（用户原话）
> 「同一事实只能有一个父风险，子项作为差异点，**不单独计入报告总事项数**；
>   报告总事项数 = 父风险数。」

## 为什么要有配置文件（而不是把规则写在代码里）
用户要求风险族可**按行业启用**、可灰度、可回滚 —— 这些都必须以**数据**表达，
否则每加一族/换行业都要改逻辑分支（本项目最高频的复发根因）。

## 结构（字段语义见 `config/risk_families.json` 的 `_schema`）
```
risk_family_id, risk_family_name,
parent_risk_code, parent_risk_name,
children[] = {child_risk_code, child_risk_name},
count_policy, display_policy, level_policy, enabled_industries
```

## 与 `finding_families.FAMILIES` 的关系（单一权威，不双维护）
`FAMILIES` 是**运行时关键词表**（族 → 关键词元组），本模块是**配置视图**（族 → 策略）。
两者由 `validate_against_runtime()` 断言一致（族名与关键词必须逐条对应），
**不一致即报错**——避免"配置改了、运行时没改"的静默漂移。
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "config", "risk_families.json")

_CACHE: Optional[Dict[str, Any]] = None

#: 合法计数口径（新增口径必须同时改 `count_policy_means` 与闸门）
COUNT_POLICIES = ("once_per_family", "sub_items_not_counted")
#: 合法呈现口径
DISPLAY_POLICIES = ("parent_plus_diffs", "sub_items_as_bullets")
#: 合法等级口径（★ `parent_fixed` 必须由红线库声明独立依据，否则不得使用）
LEVEL_POLICIES = ("max_of_children", "parent_fixed")


def load(force: bool = False) -> Dict[str, Any]:
    """读取配置（带缓存）；文件缺失/损坏 ⇒ 抛错，**不静默用空配置兜底**。"""
    global _CACHE
    if _CACHE is not None and not force:
        return _CACHE
    with open(_PATH, "r", encoding="utf-8") as f:
        _CACHE = json.load(f)
    return _CACHE


def families(industry: Optional[str] = None) -> List[Dict[str, Any]]:
    """按**行业**取启用的风险族（`enabled_industries` 为空 ⇒ 全行业启用）。"""
    ind = str(industry or "").strip()
    out = []
    for fam in (load().get("families") or []):
        _en = [str(x) for x in (fam.get("enabled_industries") or [])]
        if not _en or (ind and ind in _en):
            out.append(fam)
    return out


def family_of(child_risk_name: str, industry: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """按**子项名称关键词**归族（命中即返回该族配置；不命中返回 None）。"""
    b = str(child_risk_name or "")
    for fam in families(industry):
        for ch in (fam.get("children") or []):
            _k = str(ch.get("child_risk_name") or "")
            if _k and _k in b:
                return fam
    return None


def count_policy_means(policy: str) -> str:
    """计数口径 → 可读含义（唯一解释处；报告口径说明直接引用它）。"""
    return {
        "once_per_family": "同一族内多个子项只计 **1 项**（父项），子项不单独计入总事项数",
        "sub_items_not_counted": "子项只作差异点呈现，**不计入**报告总事项数",
    }.get(str(policy or ""), "未登记口径（不得用于报告）")


def validate_against_runtime() -> List[str]:
    """**配置 ↔ 运行时**一致性校验：返回问题列表（空 = 一致）。

    判据（双向）：
      · 运行时有、配置没有 ⇒ 该族"无策略"，报告口径无从声明；
      · 配置有、运行时没有 ⇒ 该族**永远匹配不到**（死配置）。
    关键词来源＝`finding_families.FAMILIES`（运行时唯一权威）。
    """
    from engine.finding_families import FAMILIES
    issues: List[str] = []
    _rt = {str(f): set(kws) for f, _lb, kws in FAMILIES}
    _cfg = {str(f.get("risk_family_name")): {
        str(c.get("child_risk_name")) for c in (f.get("children") or [])} for f in (load().get("families") or [])}
    for _name in _rt:
        if _name not in _cfg:
            issues.append("运行时有风险族「%s」，但配置表未登记（报告无法声明计数口径）" % _name)
    for _name in _cfg:
        if _name not in _rt:
            issues.append("配置表登记了风险族「%s」，但运行时无此族（死配置，永远匹配不到）" % _name)
            continue
        _miss = _rt[_name] - _cfg[_name]
        if _miss:
            issues.append("风险族「%s」的关键词未在配置表中登记：%s" % (_name, sorted(_miss)[:6]))
    for fam in (load().get("families") or []):
        for _f, _allow in (("count_policy", COUNT_POLICIES),
                           ("display_policy", DISPLAY_POLICIES),
                           ("level_policy", LEVEL_POLICIES)):
            _v = str(fam.get(_f) or "")
            if _v not in _allow:
                issues.append("族「%s」的 %s=「%s」未登记（合法值：%s）"
                              % (fam.get("risk_family_name"), _f, _v, "、".join(_allow)))
        if not (fam.get("parent_risk_code") and fam.get("parent_risk_name")):
            issues.append("族「%s」缺父风险编号/名称（总事项数按父项计，父项不可缺）"
                          % fam.get("risk_family_name"))
    return issues


def summary_line(industry: Optional[str] = None) -> str:
    """一行口径声明（供报告「按风险性质归纳」处引用，避免各处自写）。"""
    fams = families(industry)
    return ("本轮启用 %d 个风险族；**同族内多个子项只计 1 项**（父项），"
            "报告总事项数＝父项数之和。" % len(fams))
