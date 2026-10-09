# -*- coding: utf-8 -*-
"""词表交叉冲突的**唯一权威** —— 禁用词表 × 授权词表 的登记、计算与查询。

## 为什么要有这个模块（P1-4 根因）

本项目头号病根「同一概念两处维护」在**词表层**的具体形态是：

> **清洗层要删的词，恰是术语层要留的词。**

实测（2026-10-09）：`report_wording.FORBIDDEN_VAGUE_TERMS` 含裸词「待核」，
而 `conclusion_grades.term_authority.terms` 含授权术语「待核事项」——
子串关系。若不登记豁免，两个模块的判据必然互相打架：

* 清洗层要删「待核」⇒ 授权术语「待核事项」被误伤（实测审计侧 25 处误报）；
* 术语层要留「待核事项」⇒ 真模糊词「待核」漏网。

此前靠代码里的**隐式占位豁免**（`vague_hits` 先保护术语再扫）勉强共存。
隐式豁免的问题：**无出处、无理由、无人复核** ⇒ 下次改词表必然复发
（同一病根在本项目已出血 3 次，见 `check_vague_wording_single_source`）。

## 本模块的职责（唯一权威 + 薄转发）

1. `tables()`：枚举全仓的**禁用词表**与**授权词表**（唯一入口，新增词表只在此加一项）；
2. `conflicts()`：计算两表**子串级**交集（`equal` / `substring`）；
3. `exemptions()`：读 `config/vocab_exemptions.json`（唯一登记表）；
4. `unregistered_conflicts()`：交集里**没有登记**的 ⇒ 供闸门报 ERROR。

⚠ 本模块**只登记与计算**，不裁决业务对错 —— 裁决理由写在 config 的 `reason` 里，
由人复核；闸门只保证「凡交集必有登记且理由非空」。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

__all__ = [
    "load_spec", "load_errors", "exemptions", "tables", "conflicts",
    "find_exemption", "unregistered_conflicts", "VERSION",
]

VERSION = "1.0.0"

_ROOT = Path(__file__).resolve().parent.parent
_CFG = _ROOT / "config" / "vocab_exemptions.json"
_CACHE: Dict[str, Any] | None = None
_LOAD_ERRORS: List[str] = []


def load_spec() -> Dict[str, Any]:
    """读登记表（唯一配置入口）。读不出 ⇒ 留痕后返回空表（不静默）。"""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    try:
        data = json.loads(_CFG.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            _LOAD_ERRORS.append(f"{_CFG} 不是 JSON 对象")
            data = {}
    except Exception as exc:  # noqa: BLE001
        _LOAD_ERRORS.append(f"读 {_CFG} 失败：{exc}")
        data = {}
    _CACHE = data
    return _CACHE


def load_errors() -> List[str]:
    load_spec()
    return list(_LOAD_ERRORS)


def exemptions() -> List[Dict[str, Any]]:
    """已登记豁免清单。"""
    ex = load_spec().get("exemptions")
    return [e for e in ex if isinstance(e, dict)] if isinstance(ex, list) else []


def tables() -> List[Tuple[str, str, Tuple[str, ...]]]:
    """枚举全部词表：`[(表标识, 角色, 词元组)]`；角色 ∈ {"forbidden","authorized"}。

    ★ 新增一张词表 ⇒ **只在本函数加一行**（闸门判据自动覆盖），不改任何逻辑分支。
    ★ 表标识形如 `模块.属性`，供登记表 `*_table` 字段逐字引用。
    """
    out: List[Tuple[str, str, Tuple[str, ...]]] = []
    try:
        from engine import report_wording as _rw
        out.append(("report_wording.FORBIDDEN_VAGUE_TERMS", "forbidden",
                    tuple(_rw.FORBIDDEN_VAGUE_TERMS or ())))
    except Exception as exc:  # noqa: BLE001
        _LOAD_ERRORS.append(f"无法导入 report_wording：{exc}")
    try:
        from engine import risk_levels as _rl
        out.append(("risk_levels.LEGAL_LEVELS", "authorized",
                    tuple(_rl.LEGAL_LEVELS or ())))
    except Exception as exc:  # noqa: BLE001
        _LOAD_ERRORS.append(f"无法导入 risk_levels：{exc}")
    try:
        from engine.conclusion_grade import (  # noqa: PLC0415
            term_authority as _ta, determinative_words as _dw, conclusion_terms as _ct,
        )
        out.append(("conclusion_grades.term_authority.forbidden_determinative", "forbidden",
                    tuple((_ta().get("forbidden_determinative") or ()))))
        out.append(("conclusion_grades.veto_rules.determinative_words", "forbidden",
                    tuple(_dw() or ())))
        out.append(("conclusion_grades.term_authority.terms", "authorized",
                    tuple(_ct() or ())))
    except Exception as exc:  # noqa: BLE001
        _LOAD_ERRORS.append(f"无法导入 conclusion_grade：{exc}")
    return out


def conflicts() -> List[Dict[str, str]]:
    """禁用词 × 授权词 的**子串级**交集（任一为另一子串即算冲突）。

    :return: `[{forbidden, forbidden_table, authorized, authorized_table, relation}]`
    """
    tabs = tables()
    forb = [(t, str(w)) for (t, role, ws) in tabs if role == "forbidden" for w in ws if str(w)]
    auth = [(t, str(w)) for (t, role, ws) in tabs if role == "authorized" for w in ws if str(w)]
    out: List[Dict[str, str]] = []
    for ft, f in forb:
        for at, a in auth:
            if f in a or a in f:
                out.append({
                    "forbidden": f, "forbidden_table": ft,
                    "authorized": a, "authorized_table": at,
                    "relation": "equal" if f == a else "substring",
                })
    return out


def find_exemption(forbidden: Any, authorized: Any) -> Dict[str, Any]:
    """按 (禁用词, 授权词) 二元组查登记项（逐字匹配）。"""
    f, a = str(forbidden or ""), str(authorized or "")
    for e in exemptions():
        if str(e.get("forbidden") or "") == f and str(e.get("authorized") or "") == a:
            return e
    return {}


def unregistered_conflicts() -> List[Dict[str, Any]]:
    """交集里**未登记**或**登记不合格**（无 reason / 无 handler）的项。

    每项附加 `_why` 说明不合格原因，供闸门直接输出。
    """
    out: List[Dict[str, Any]] = []
    for c in conflicts():
        e = find_exemption(c["forbidden"], c["authorized"])
        if not e:
            c = dict(c)
            c["_why"] = "未在 config/vocab_exemptions.json 登记（禁用词与授权词共存必须有出处与理由）"
            out.append(c)
            continue
        _miss = [k for k in ("reason", "handler", "id") if not str(e.get(k) or "").strip()]
        if _miss:
            c = dict(c)
            c["_why"] = "登记项缺字段：%s（登记必须可复核）" % "、".join(_miss)
            out.append(c)
    return out
