# -*- coding: utf-8 -*-
"""标准字段（P0-3）**唯一权威**：读 `config/standard_fields.json` + 值归一。

★ 三处薄转发（勿另立第二套）
  · 字段别名 → `engine/fieldkit.py` 的别名常量（`aliases_from` **引用常量名**，不抄表）
  · 金额解析 → `engine/numparse.to_number_checked`（能区分"真 0"与"解析失败"）
  · 期间归一 → 本模块 `to_standard_period`（只做格式归一，**不改语义**）

★ 新增一个可识别字段 = **在 JSON 加一行**（不改代码分支）。
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from engine import fieldkit as _FK
from engine.numparse import to_number_checked

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FIELDS_PATH = os.path.join(_PROJECT_ROOT, "config", "standard_fields.json")

TYPES: Tuple[str, ...] = ("amount", "text", "date", "period")

_CACHE: Dict[str, Any] = {}


def reset_cache() -> None:
    _CACHE.clear()


def _load() -> Dict[str, Any]:
    if "cfg" not in _CACHE:
        try:
            with open(_FIELDS_PATH, "r", encoding="utf-8") as fh:
                _CACHE["cfg"] = json.load(fh)
        except Exception:                             # noqa: BLE001
            _CACHE["cfg"] = {"fields": []}
    return _CACHE["cfg"]


def fields() -> List[Dict[str, Any]]:
    """标准字段清单（按声明顺序）。"""
    return list((_load().get("fields") or []))


def field_names() -> List[str]:
    return [str(f.get("name")) for f in fields() if f.get("name")]


def field(name: str) -> Optional[Dict[str, Any]]:
    n = str(name or "")
    for f in fields():
        if str(f.get("name")) == n:
            return f
    return None


def domain_cn(domain: str) -> str:
    d = ((_load().get("_domains") or {})).get(str(domain))
    if d:
        return str(d).split("（")[0].strip()
    return str(domain or "")


def required_names(domain: Optional[str] = None) -> List[str]:
    out = []
    for f in fields():
        if not f.get("required"):
            continue
        if domain and str(f.get("domain")) != str(domain):
            continue
        out.append(str(f.get("name")))
    return out


def aliases_of(name: str) -> List[str]:
    """该标准字段的全部别名（`aliases_from` 常量展开在前，内联 `aliases` 追加在后）。

    ★ 顺序即优先级：常量里的别名先匹配（它们与既有解析口径同源）。
    """
    f = field(name) or {}
    out: List[str] = []
    src = str(f.get("aliases_from") or "").strip()
    if src:
        const = getattr(_FK, src, None)
        if const:
            try:
                out.extend([str(x) for x in const])
            except TypeError:
                pass
    for a in (f.get("aliases") or []):
        s = str(a)
        if s and s not in out:
            out.append(s)
    seen: set = set()
    uniq: List[str] = []
    for a in out:
        if a and a not in seen:
            seen.add(a)
            uniq.append(a)
    return uniq


def fields_of_domain(domain: str) -> List[Dict[str, Any]]:
    return [f for f in fields() if str(f.get("domain")) == str(domain)]


# --------------------------------------------------------------------------
# 归一
# --------------------------------------------------------------------------
#: 全角→半角（与 numparse 同口径，仅用于期间文本）；**源与目标必须等长**（13 = 10 数字 + 3 符号）
_FULL2HALF = str.maketrans("０１２３４５６７８９／．－", "0123456789/.-")

_PERIOD_PATTERNS: Tuple[Tuple[re.Pattern, str], ...] = (
    # 2024-01 / 2024/01 / 2024.01
    (re.compile(r"^(\d{4})[-/.](\d{1,2})$"), r"\1-\2"),
    # 202401
    (re.compile(r"^(\d{4})(\d{2})$"), r"\1-\2"),
    # 20240105（★ 实测：既有解析器把日期列归一为 `20240105` 这种 8 位无分隔格式，
    #   `bank_statement` 与 `sales_invoice` 都如此 ⇒ 不支持它会让日期字段全部取不到）
    (re.compile(r"^(\d{4})(\d{2})(\d{2})$"), r"\1-\2-\3"),
    # 2024-01-01（保留日）
    (re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$"), r"\1-\2-\3"),
    # 2024年1月
    (re.compile(r"^(\d{4})\s*年\s*(\d{1,2})\s*月?$"), r"\1-\2"),
    # 2024年
    (re.compile(r"^(\d{4})\s*年$"), r"\1"),
    # 2024（**纯 4 位年份 = 年度期间，合法**；放在 6 位/年月规则之后，不冲突）
    (re.compile(r"^((?:19|20)\d{2})$"), r"\1"),
    # 2024年第1季度
    (re.compile(r"^(\d{4})\s*年?\s*第\s*([1-4])\s*季度$"), r"\1-Q\2"),
)


def to_standard_period(value: Any) -> Tuple[str, bool]:
    """期间文本 → **标准可读期间**（`YYYY-MM` / `YYYY-MM-DD` / `YYYY` / `YYYY-Qn`）。

    ★ 与 `engine/findingkit` 的 `month_key`（月键）**职责不同，故不转发**（已在审计
      `_DIVERGENCE_OK` 与本 docstring 双处说明）：
        · 本函数 = **文书格式归一**（把各种写法统一成可读期间串），**产出给人看**；
        · `month_key` = **分组键构造**（保证同一月只有一个桶），**产出给聚合用**。
      本函数**不构造月键**、不做分组，故不属"期间键归一的多头实现"。
    只做**格式**归一，**不推断语义**；无法识别 ⇒ 原样返回、`ok=False`（**不猜**）。
    """
    s = str(value if value is not None else "").strip().translate(_FULL2HALF)
    if not s:
        return "", False
    s = re.sub(r"\s+", "", s)
    for pat, rep in _PERIOD_PATTERNS:
        m = pat.match(s)
        if m:
            if "Q" in rep:
                return rep.replace(r"\1", m.group(1)).replace(r"\2", m.group(2)), True
            out = m.expand(rep)
            # 月份补零
            mm = re.match(r"^(\d{4})-(\d{1,2})(-\d{1,2})?$", out)
            if mm:
                out = "%s-%02d%s" % (mm.group(1), int(mm.group(2)), mm.group(3) or "")
            return out, True
    return s, False


def normalize_value(name: str, value: Any) -> Tuple[Any, bool, str]:
    """按标准字段的 `type` 归一。返回 `(归一值, 是否成功, 说明)`。

    · `amount` ⇒ `numparse.to_number_checked`；失败 ⇒ `(原值, False, "金额格式错误: <原值>")`
    · `period` ⇒ `to_standard_period`；失败 ⇒ `(原值, False, "期间格式未识别: <原值>")`
    · `date`   ⇒ 复用期间归一（同格式族）；失败同上
    · `text`   ⇒ 去空白即成功（空 ⇒ 失败）
    """
    f = field(name) or {}
    t = str(f.get("type") or "text")
    if t == "amount":
        num, ok = to_number_checked(value, default=0.0)
        if not ok:
            return value, False, "金额格式错误: %s" % str(value)[:60]
        return num, True, ""
    if t in ("period", "date"):
        out, ok = to_standard_period(value)
        if not ok:
            return value, False, ("期间格式未识别: %s" % str(value)[:60] if t == "period"
                                  else "日期格式未识别: %s" % str(value)[:60])
        return out, True, ""
    s = str(value if value is not None else "").strip()
    if not s:
        return "", False, "文本为空"
    return s, True, ""


# --------------------------------------------------------------------------
# 取行内字段值（按标准字段别名）
# --------------------------------------------------------------------------
def value_from_row(name: str, row: Dict[str, Any]) -> Any:
    """按该标准字段的别名顺序，从原始行取第一个非空值（**只读，不改原行**）。"""
    if not isinstance(row, dict):
        return None
    for a in aliases_of(name):
        v = row.get(a)
        if v in (None, ""):
            continue
        if isinstance(v, str) and not v.strip():
            continue
        return v
    return None


def metadata() -> Dict[str, Any]:
    """字典（供前端；**唯一权威**来自本模块）。"""
    return {
        "fields": [{"name": str(f.get("name")), "cn": str(f.get("cn")),
                    "domain": str(f.get("domain")), "domain_cn": domain_cn(str(f.get("domain"))),
                    "type": str(f.get("type")), "required": bool(f.get("required"))}
                   for f in fields()],
        "domains": [{"value": k, "label": str(v).split("（")[0].strip()}
                    for k, v in (_load().get("_domains") or {}).items()],
        "types": list(TYPES),
        "validation_rules": list((_load().get("_validation") or {}).keys()),
    }


__all__ = ["fields", "field", "field_names", "fields_of_domain", "aliases_of",
           "to_standard_period", "normalize_value", "value_from_row",
           "required_names", "domain_cn", "metadata", "reset_cache", "TYPES"]
