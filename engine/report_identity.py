# -*- coding: utf-8 -*-
"""报告性质一致性（Skill 5 唯一权威）：标题 / 文末声明 / 报告定位必须同一口径。

## 为什么要它
用户复核（2026-10-07）：报告**标题**是「税务风险扫描工作底稿」，文末/定位又出现另一种说法，
读者无法判断"这份东西到底是什么"。要求统一为「**内部辅助分析工作底稿**」。

## 唯一权威
名称与"允许/禁止"词表全部取自 `config/report_identity.json`（**新增同类只加一行数据**）；
本模块只做解析、校验与统一替换，**不写死任何名称字面量**。

## 口径
- `canonical_name()`：报告**唯一**名称（标题、文末声明、报告性质三处必须一致）。
- `scan_names(texts)`：文本中出现的**禁止别名**（如"内部辅助分析草稿""检查报告"）⇒ 问题清单。
- `unify(text)`：把禁止别名替换为唯一名称（用于生成期收口）。
- 与 `engine.report_compliance` 的关系：本模块是**报告名称的一致性守卫**，
  名称的**出处**仍是 `report_compliance.document_meta`（本模块从同一配置读取，避免第二权威）。
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

VERSION = "1.0.0"

_ROOT = Path(__file__).resolve().parent.parent
_CFG_PATH = _ROOT / "config" / "report_identity.json"
_CACHE: Optional[Dict[str, Any]] = None

#: 配置缺失时的**唯一兜底**（与 config/report_identity.json 同值；任何改动以配置为准）
_FALLBACK = {
    "canonical": "内部辅助分析工作底稿",
    "forbidden_aliases": ["内部辅助分析草稿", "风险扫描工作底稿", "税务风险扫描工作底稿",
                          "涉税风险检查工作报告", "检查报告", "分析报告"],
}


def load_config() -> Dict[str, Any]:
    global _CACHE
    if _CACHE is None:
        try:
            raw = json.loads(_CFG_PATH.read_text(encoding="utf-8"))
            _CACHE = raw if isinstance(raw, dict) else dict(_FALLBACK)
        except Exception:
            _CACHE = dict(_FALLBACK)
    return _CACHE or dict(_FALLBACK)


def canonical_name() -> str:
    """报告唯一名称。"""
    return str(load_config().get("canonical") or _FALLBACK["canonical"]).strip()


def forbidden_aliases() -> List[str]:
    """禁止使用的别名（**按长度降序**，替换时先长后短，避免"部分替换"造出新病句）。"""
    al = load_config().get("forbidden_aliases") or []
    return sorted({str(x).strip() for x in al if str(x).strip()},
                  key=len, reverse=True)


def unify(text: Any) -> str:
    """把禁止别名替换为唯一名称（幂等）。"""
    s = str(text or "")
    if not s:
        return s
    cn = canonical_name()
    for a in forbidden_aliases():
        if a == cn or a in cn:
            continue                      # 别名是唯一名称的子串时跳过（否则会自我替换）
        s = s.replace(a, cn)
    return s


def scan_names(texts: Iterable[Any], *, where: str = "") -> List[Dict[str, Any]]:
    """文本里出现的禁止别名 ⇒ 问题清单。"""
    out: List[Dict[str, Any]] = []
    cn = canonical_name()
    for i, t in enumerate(texts or []):
        s = str(t or "")
        for a in forbidden_aliases():
            if a == cn or a in cn:
                continue
            if a in s:
                out.append({"kind": "alias_used", "level": "ERROR",
                            "where": where or ("第%d项" % (i + 1)),
                            "detail": "出现了非唯一名称「%s」，应统一为「%s」。" % (a, cn),
                            "text": s[:140]})
    return out


def identity_line() -> str:
    """报告性质标准句（标题/文末声明/报告定位三处引用同一句）。"""
    cn = canonical_name()
    return ("本报告为%s，依据企业提供的资料编制，仅供内部风险复核与整改使用；"
            "不具有税务机关行政执法文书的效力。" % cn)


def consistency_report(title: Any, tail_statement: Any, purpose: Any) -> List[Dict[str, Any]]:
    """三处（标题/文末声明/报告定位）一致性核对。"""
    cn = canonical_name()
    probs: List[Dict[str, Any]] = []
    for label, val in (("标题", title), ("文末声明", tail_statement), ("报告定位", purpose)):
        s = str(val or "").strip()
        if not s:
            probs.append({"kind": "identity_missing", "level": "ERROR",
                          "detail": "%s为空（报告性质三处必须都写明）。" % label, "text": ""})
            continue
        if cn not in s:
            probs.append({"kind": "identity_mismatch", "level": "ERROR",
                          "detail": "%s未采用唯一名称「%s」。" % (label, cn), "text": s[:140]})
    probs.extend(scan_names([title, tail_statement, purpose], where="报告性质"))
    return probs


__all__ = ["VERSION", "load_config", "canonical_name", "forbidden_aliases", "unify",
           "scan_names", "identity_line", "consistency_report"]
