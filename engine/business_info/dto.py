# -*- coding: utf-8 -*-
"""工商信息 DTO 与**清洗**（唯一实现）。

职责边界
--------
· 本模块只做「杂乱输入 → 标准 DTO」，**不发起任何网络请求、不落库**；
· 字段名与中文标签的唯一权威是 `engine.project_service.PROFILE_FIELDS`
  （项目表单/详情/账套同步都用它）——本模块**只引用、不重定义**；
· 下拉可选项的唯一权威是 `config/project_profile_dicts.json`
  （登记状态 / 公司类型 / 资本单位）；
· 数值解析的唯一权威是 `engine.numparse`（项目铁律：金额绝不自写正则）；
· **缺失如实**：取不到就是 `None` 并记 `notes`，绝不填默认值/"其他"顶替。
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ── 输入别名（各数据源字段名不一；仅作读取归一，不产生新字段） ──
_ALIASES: Dict[str, Tuple[str, ...]] = {
    "name": ("name", "company_name", "企业名称", "公司名称", "名称", "entname"),
    "tax_id": ("tax_id", "uscc", "credit_code", "unified_code", "税号",
               "统一社会信用代码", "纳税人识别号", "注册号"),
    "legal_representative": ("legal_representative", "legal_person", "法定代表人",
                             "法人代表", "负责人", "oper_name"),
    "registered_capital": ("registered_capital", "reg_capital", "注册资本",
                           "注册资金", "regcap"),
    "established_date": ("established_date", "establish_date", "成立日期",
                         "注册日期", "成立时间", "esdate"),
    "registration_status": ("registration_status", "status", "登记状态",
                            "经营状态", "企业状态", "reg_status"),
    "registered_address": ("registered_address", "address", "注册地址",
                           "住所", "企业地址", "dom"),
    "company_type": ("company_type", "companyType", "公司类型", "企业类型",
                     "主体类型", "enttype"),
    "business_scope": ("business_scope", "scope", "经营范围", "经营业务范围", "opscope"),
}

_USCC_RE = re.compile(r"^[0-9A-Z]{18}$")
_DATE_RE = re.compile(r"(\d{4})\s*[-/年.]?\s*(\d{1,2})\s*[-/月.]?\s*(\d{1,2})")
_DATE8_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})$")

_FULLWIDTH_MAP = {0x3000: 0x20, 0xFF08: 0x28, 0xFF09: 0x29,
                  0xFF0C: 0x2C, 0xFF1B: 0x3B, 0xFF1A: 0x3A}


@dataclass
class CompanyProfile:
    """标准工商画像 DTO（字段名与 `PROFILE_FIELDS` 对齐）。"""

    name: str = ""
    tax_id: Optional[str] = None
    legal_representative: Optional[str] = None
    registered_capital: Optional[float] = None      # 单位见 capital_unit（默认万元）
    capital_unit: str = "万元"
    established_date: Optional[str] = None           # YYYY-MM-DD
    registration_status: Optional[str] = None
    registered_address: Optional[str] = None
    company_type: Optional[str] = None
    business_scope: Optional[str] = None
    source: str = ""
    source_detail: str = ""
    confidence: float = 0.0
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["missing"] = [k for k in ("tax_id", "legal_representative", "registered_capital",
                                    "established_date", "registration_status",
                                    "registered_address", "company_type", "business_scope")
                        if d.get(k) in (None, "")]
        return d


def _s(v: Any) -> str:
    if v is None:
        return ""
    return unicodedata.normalize("NFKC", str(v)).translate(_FULLWIDTH_MAP).strip()


def clean_text(v: Any, maxlen: int) -> Optional[str]:
    s = re.sub(r"\s+", " ", _s(v))
    if not s:
        return None
    return s[:maxlen]


def clean_uscc(v: Any) -> Optional[str]:
    """统一社会信用代码：去空格/连字符、转大写；不合 18 位格式 ⇒ None（**不猜**）。"""
    s = re.sub(r"[\s\-_]", "", _s(v)).upper()
    if not s:
        return None
    return s if _USCC_RE.match(s) else None


def clean_capital(v: Any, units: Dict[str, float]) -> Tuple[Optional[float], Optional[str]]:
    """注册资本 → `(万元数值, 单位说明)`；无法解析 ⇒ `(None, None)`。

    ★ 数值部分用 `engine.numparse.to_number_checked`（唯一数字口径）；
      单位换算表来自 `config/business_info.json::capital_units`（数据，不写死在代码）。
    """
    s = _s(v)
    if not s:
        return None, None
    try:
        from engine.numparse import to_number_checked      # noqa: PLC0415
    except Exception:                                      # noqa: BLE001
        return None, None
    unit = ""
    factor = 1.0
    for u in sorted(units, key=len, reverse=True):
        if u in s:
            unit, factor = u, float(units[u])
            break
    m = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", s)
    if not m:
        return None, None
    num, ok = to_number_checked(m.group(0), default=0.0)
    if not ok:
        return None, None
    val = round(float(num) * factor, 4)
    if val < 0:
        return None, None
    return val, (unit or "万元")


def clean_date(v: Any) -> Optional[str]:
    """成立日期归一 `YYYY-MM-DD`；非法/缺失 ⇒ None。"""
    s = _s(v)
    if not s:
        return None
    m8 = _DATE8_RE.match(s)
    if m8:
        y, mo, d = m8.groups()
        return "%s-%s-%s" % (y, mo, d)
    m = _DATE_RE.search(s)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1900 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return "%04d-%02d-%02d" % (y, mo, d)


def clean_status(v: Any, status_map: Dict[str, str], allowed: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """登记状态归一：返回 `(标准值|None, notes文字|None)`。

    ★ 只映射到 `config/project_profile_dicts.json::registration_statuses` 里的值；
      取不到映射时**返回 None 并带原始值**（不硬塞"其他"，那会掩盖真实状态）。
    """
    s = _s(v)
    if not s:
        return None, None
    if s in allowed:
        return s, None
    # ★ 按「在原文中出现的**位置**」定优先级：`吊销，未注销` 必须归「吊销」，
    #   不能因为「注销」也是 2 字就撞上（实测踩过：按长度排序会误判主体资格）。
    cands = []
    for key in status_map:
        if not key:
            continue
        pos = s.find(key)
        if pos >= 0:
            cands.append((pos, -len(key), key))
    if cands:
        key = sorted(cands)[0][2]
        val = status_map[key]
        if val in allowed or not allowed:
            return val, None
        return None, "登记状态「%s」映射到未登记值「%s」" % (s, val)
    return None, "登记状态无法归一（原始值：%s）" % s[:30]


def clean_company_type(v: Any, allowed: List[str]) -> Optional[str]:
    """公司类型归一：完全匹配优先，其次"包含最长关键词"；认不出 ⇒ None。"""
    s = _s(v)
    if not s:
        return None
    if s in allowed:
        return s
    for cand in sorted(allowed, key=len, reverse=True):
        if cand and cand in s:
            return cand
    # 反向：输入是标准值的子串（如"有限责任公司(自然人独资)"→"有限责任公司"）
    for cand in sorted(allowed, key=len, reverse=True):
        if s in cand:
            return cand
    return None


_SCOPE_NOISE = re.compile(r"[\r\n\t]+")


def clean_scope(v: Any, maxlen: int, stop_words: List[str]) -> Optional[str]:
    """经营范围归一：去换行/多空格、剔除登记机关套话；截断到字段上限。"""
    s = _SCOPE_NOISE.sub("", _s(v))
    for w in stop_words:
        if w and w in s:
            s = s.replace(w, "")
    s = re.sub(r"[；;]{2,}", "；", s).strip("；;、，, ")
    if not s:
        return None
    return s[:maxlen]


def to_float(v: Any, default: float = 0.0) -> float:
    """任意输入 → float（走 `engine.numparse` 的唯一数字口径）。"""
    try:
        from engine.numparse import to_number_checked        # noqa: PLC0415
        n, ok = to_number_checked(v, default=default)
        return float(n) if ok else float(default)
    except Exception:                                        # noqa: BLE001
        return float(default)


def _pick(raw: Dict[str, Any], key: str) -> Any:
    for alias in _ALIASES.get(key, (key,)):
        if alias in raw and raw[alias] not in (None, ""):
            return raw[alias]
    return None


def build_profile(raw: Dict[str, Any], *, cfg: Dict[str, Any],
                  source: str = "", source_detail: str = "",
                  confidence: float = 0.0) -> CompanyProfile:
    """把**任意来源**的原始字典清洗成 DTO。清洗过程逐项留痕到 `notes`。"""
    from engine.project_service import PROFILE_FIELDS        # noqa: PLC0415
    maxlen = {name: mx for name, _cn, mx, _kind in PROFILE_FIELDS
              if isinstance(mx, int) and mx > 0}
    try:
        from engine.project_service import _profile_dicts     # noqa: PLC0415
        dicts = _profile_dicts() or {}
    except Exception:                                         # noqa: BLE001
        dicts = {}
    statuses = list(dicts.get("registration_statuses") or [])
    types = list(dicts.get("company_types") or [])
    status_map = dict(cfg.get("status_map") or {})
    units = dict(cfg.get("capital_units") or {})
    stop = list((cfg.get("scope_rule") or {}).get("scope_stop_words") or [])

    # ★ 数字转换唯一权威 `engine.numparse`（行内兜底写法遇"1,000"会静默变 0）
    p = CompanyProfile(source=source, source_detail=source_detail,
                       confidence=to_float(confidence))
    p.name = clean_text(_pick(raw, "name"), maxlen.get("name", 100)) or ""

    uscc_raw = _pick(raw, "tax_id")
    p.tax_id = clean_uscc(uscc_raw)
    if uscc_raw not in (None, "") and not p.tax_id:
        p.notes.append("统一社会信用代码格式不合 18 位（原始值：%s）" % _s(uscc_raw)[:24])

    p.legal_representative = clean_text(_pick(raw, "legal_representative"),
                                        maxlen.get("legal_representative", 50))
    cap, unit = clean_capital(_pick(raw, "registered_capital"), units)
    p.registered_capital, p.capital_unit = cap, (unit or "万元")

    est_raw = _pick(raw, "established_date")
    p.established_date = clean_date(est_raw)
    if est_raw not in (None, "") and not p.established_date:
        p.notes.append("成立日期无法解析（原始值：%s）" % _s(est_raw)[:24])

    st, st_note = clean_status(_pick(raw, "registration_status"), status_map, statuses)
    p.registration_status = st
    if st_note:
        p.notes.append(st_note)

    p.registered_address = clean_text(_pick(raw, "registered_address"),
                                      maxlen.get("registered_address", 200))
    ct_raw = _pick(raw, "company_type")
    p.company_type = clean_company_type(ct_raw, types)
    if ct_raw not in (None, "") and not p.company_type:
        p.notes.append("公司类型不在登记字典内（原始值：%s）" % _s(ct_raw)[:30])

    p.business_scope = clean_scope(_pick(raw, "business_scope"),
                                   maxlen.get("business_scope", 1000), stop)
    return p


def is_risky_status(status: Any, risky: List[str]) -> bool:
    s = _s(status)
    return bool(s) and any(r and r in s for r in risky)


__all__ = ["CompanyProfile", "build_profile", "clean_text", "clean_uscc",
           "clean_capital", "clean_date", "clean_status", "clean_company_type",
           "clean_scope", "is_risky_status", "to_float"]
