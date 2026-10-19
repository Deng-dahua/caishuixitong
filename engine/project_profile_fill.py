# -*- coding: utf-8 -*-
"""项目画像字段的**自动填列**（唯一权威，2026-10-19 立）。

## 为什么需要这个模块（用户三问定位到的真缺口）

用户的三问其实是同一个根因的三个侧面：

  > 「为什么海更公司分析报告都能显示行业等信息了，在稽查项目管理列表中就是不显示这些信息呢？」
  > 「报告生成与导出模块的分析报告的运行是不是单独和财税稽查系统脱离的？怎么信息就不共用呢？」

实测事实（2026-10-19）：

  · **不脱离**：分析确实读了 `projects` / `companies` / `sys_company_info`；
  · **缺的是回写**：分析把行业解析出来只写进 `companies.industry_resolved`
    （`main._write_resolved_industry`，供"选择账套"页显示），
    **从来没写回 `projects.industry`**；而稽查项目管理列表读的正是 `projects.industry`
    ⇒ 报告里有、列表里是「—」。
  · 实测数据：`projects.id=42` 的 `industry/region/period_*/profile_*` 全空，
    而同一次分析的 `target_entity` 里 `industry="广告传媒"`、`legal_representative="张晓冬"`、
    `period="2025-01 至 2025-12"`、`business_scope=…` 全都有。

本模块负责**从已有数据推导字段值**（推导不出来就如实说"不可得+原因"，绝不编造）；
真正写库的仍由 `engine/project_service.sync_profile_from_analysis` 执行
—— **`projects` 表的写入权威只有 `project_service` 一个**，本模块不写库。

## 推导来源与优先级（每条都写明来源，供前端展示与留痕）

| 字段 | 来源（按优先级） | 推导不出来时 |
|---|---|---|
| 行业 | ① 分析结果的 `_industry_resolved`（多来源加权）② `industry_resolver.resolve_industry`（名称/经营范围/品名）③ 工商登记行业 | 留空 + 原因 |
| 地区 | 注册地址（`sys_company_info` / 分析 `target_entity.address`）解析「省+市」 | 留空 + 原因 |
| 稽查期间 | 分析结果的报告期间（`identity.period` / `target_entity.period`） | 留空 + 原因 |
| 税种范围 | 分析结果里的申报表税种（`tax_declarations._declaration_type`） | 留空 + 原因 |
| 工商 7 项 | `sys_company_info`（缓存/档案，唯一权威）→ 分析 `target_entity` | 留空 + 原因 |

## 铁律

- **不编造**：推导不出来就 `value=""` + `reason`，绝不用默认值顶替（缺失≠0）；
- **不覆盖人工判断**：调用方（`sync_profile_from_analysis`）只写"当前为空"或"与推导值不同"
  的字段，且**空推导值永远不覆盖已有值**；
- **不另写推断逻辑**：行业必须走 `industry_resolver`（那才是唯一权威），
  本模块只做"取哪个来源、怎么解析、怎么标注"的装配。
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "PROVINCES",
    "region_from_address",
    "industry_from_scope",
    "period_from_analysis",
    "period_parts",
    "tax_scopes_from_analysis",
    "analysis_values",
    "suggest_for_project",
    "SYNC_FIELDS",
]

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: 项目表里"可由系统自动填列"的字段（顺序即写入顺序；与 `project_service` 的列名一致）
SYNC_FIELDS: Tuple[str, ...] = (
    "taxpayer_id", "industry", "region", "period_start", "period_end", "tax_scopes",
    "legal_representative", "registered_capital", "established_date",
    "registration_status", "registered_address", "business_scope", "company_type",
)

#: 工商 7 项（与 project_service.PROFILE_FIELDS 同口径，这里只列 key）
PROFILE_KEYS: Tuple[str, ...] = (
    "legal_representative", "registered_capital", "established_date",
    "registration_status", "registered_address", "business_scope", "company_type",
)


def _profile_dicts() -> Dict[str, Any]:
    """读画像字典（数据文件是唯一权威；`project_service` 已有同源读取，此处只读 regions）。"""
    path = os.path.join(_ROOT, "config", "project_profile_dicts.json")
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:                                          # noqa: BLE001
        return {}


def _provinces() -> List[str]:
    """省级全称清单（来自 `config/project_profile_dicts.json::regions`，单一权威）。"""
    return [str(x) for x in (_profile_dicts().get("regions") or []) if str(x).strip()]


PROVINCES = _provinces()

#: 统一社会信用代码第 3–8 位 = 登记管理机关行政区划码（GB/T 2260）；
#: 这里只登记**省级两位码**（34 条，标准码表）—— 市级码表体量大且易过期，
#: 不在此硬编码；需要市时由「注册地址」或「企业名称中的行政区划」提供。
USCC_PROVINCE = {
    "11": "北京市", "12": "天津市", "13": "河北省", "14": "山西省", "15": "内蒙古自治区",
    "21": "辽宁省", "22": "吉林省", "23": "黑龙江省", "31": "上海市", "32": "江苏省",
    "33": "浙江省", "34": "安徽省", "35": "福建省", "36": "江西省", "37": "山东省",
    "41": "河南省", "42": "湖北省", "43": "湖南省", "44": "广东省", "45": "广西壮族自治区",
    "46": "海南省", "50": "重庆市", "51": "四川省", "52": "贵州省", "53": "云南省",
    "54": "西藏自治区", "61": "陕西省", "62": "甘肃省", "63": "青海省", "64": "宁夏回族自治区",
    "65": "新疆维吾尔自治区", "71": "台湾省", "81": "香港特别行政区", "82": "澳门特别行政区",
}

#: 省级简称 → 全称（"广东" → "广东省"；直辖市的简称即全称前缀）
_PROV_SHORT = {
    "北京": "北京市", "天津": "天津市", "上海": "上海市", "重庆": "重庆市",
    "河北": "河北省", "山西": "山西省", "辽宁": "辽宁省", "吉林": "吉林省",
    "黑龙江": "黑龙江省", "江苏": "江苏省", "浙江": "浙江省", "安徽": "安徽省",
    "福建": "福建省", "江西": "江西省", "山东": "山东省", "河南": "河南省",
    "湖北": "湖北省", "湖南": "湖南省", "广东": "广东省", "海南": "海南省",
    "四川": "四川省", "贵州": "贵州省", "云南": "云南省", "陕西": "陕西省",
    "甘肃": "甘肃省", "青海": "青海省", "台湾": "台湾省",
    "内蒙古": "内蒙古自治区", "广西": "广西壮族自治区", "西藏": "西藏自治区",
    "宁夏": "宁夏回族自治区", "新疆": "新疆维吾尔自治区",
    "香港": "香港特别行政区", "澳门": "澳门特别行政区",
}

#: 地级市/直辖市区县后缀识别（只取到市级，不细化到区县）
_CITY_RE = re.compile(r"([\u4e00-\u9fa5]{2,8}?(?:市|自治州|地区|盟))")


def region_from_address(address: Any) -> Dict[str, Any]:
    """从**注册地址**解析「省+市」（如「广东省深圳市」）。解析不出 ⇒ `value=""` + 原因。

    ★ 只做**确定性的地理前缀解析**，不做任何猜测：
      · 地址必须有省级线索（全称或常见简称）才认，否则视为不可得；
      · 城市取地址中"省级之后、第一个 `市/自治州/地区/盟` 结尾"的片段；
        直辖市（北京/上海/天津/重庆）的城市部分即该市本身；
      · 解析结果只用于**填列**，来源标注为「注册地址解析」——不是工商登记的地区字段
        （工商登记信息本身不含"地区"字段，地区只能由住址推导，必须如实标注来源）。
    """
    text = str(address or "").strip()
    if not text:
        return {"value": "", "source": "", "reason": "未取得注册地址，无法解析地区"}

    prov = ""
    idx = -1
    # ① 优先匹配省级全称（长的先匹配：内蒙古自治区 / 广西壮族自治区 …）
    for p in sorted(PROVINCES, key=len, reverse=True):
        if p and p in text:
            prov, idx = p, text.index(p) + len(p)
            break
    # ② 退回省级简称（"广东深圳…"）
    if not prov:
        for short, full in sorted(_PROV_SHORT.items(), key=lambda kv: len(kv[0]), reverse=True):
            if text.startswith(short) or (short + "省") in text or (short + "市") in text:
                prov = full
                j = text.find(short)
                idx = j + len(short)
                break
    if not prov:
        return {"value": "", "source": "注册地址",
                "reason": "注册地址里未识别到省级行政区，无法确定地区"}

    # ③ 直辖市：城市即该市
    if prov in ("北京市", "上海市", "天津市", "重庆市"):
        return {"value": prov, "source": "注册地址解析",
                "reason": "直辖市，地区即市本身"}

    rest = text[idx:]
    m = _CITY_RE.search(rest)
    if m:
        city = m.group(1)
        # 去掉可能的"省/自治区"残留前缀，只保留城市名
        return {"value": prov + city, "source": "注册地址解析", "reason": ""}
    # 只有省、没有市：如实只给省（不补"市"字，不猜）
    return {"value": prov, "source": "注册地址解析",
            "reason": "地址中未识别到市级行政区，地区只精确到省"}


def _city_in_name(company_name: str) -> str:
    """企业名称里的**市级行政区划**（如「深圳海更…」⇒「深圳市」）。

    口径：企业名称必须含行政区划（《企业名称登记管理规定》），因此名称开头的城市名
    是**登记信息**而非猜测。只认 `shared_state._CHINA_CITIES_UNIFIED`（全代码唯一城市清单），
    命中多个取最长（避免「台山」被「山」类短词误命中）。取不到返回 ""。
    """
    name = str(company_name or "").strip()
    if not name:
        return ""
    try:
        from shared_state import _CHINA_CITIES_UNIFIED as CITIES   # noqa: PLC0415
    except Exception:                                            # noqa: BLE001
        return ""
    # 只看名称前 12 字（行政区划在名称最前部，避免把商号里的城市名当地域）
    head = name[:12]
    hits = [c for c in CITIES if c and c in head]
    if not hits:
        return ""
    city = max(hits, key=len)
    return city if city.endswith("市") else city + "市"


def region_of(address: Any = "", company_name: Any = "", uscc: Any = "") -> Dict[str, Any]:
    """确定性地推导「地区」（省+市），三级来源，取到即止，并**标注来源**。

    ① **注册地址**：省+市（最准，来源「注册地址解析」）；
    ② **企业名称中的行政区划**（登记信息，来源「企业名称行政区划」）—— 需要省时
       再由 ①/③ 提供，缺省则只给市（不猜省）；
    ③ **统一社会信用代码的登记机关行政区划码**（GB/T 2260 省级两位码，来源
       「登记机关行政区划码」）—— 只到省，**不冒充市**。

    全部落空 ⇒ `value=""` + 明确原因（**不猜**）。
    """
    addr_res = region_from_address(address)
    if addr_res["value"]:
        return addr_res

    city = _city_in_name(str(company_name or ""))
    prov = ""
    src_city = ""
    if city:
        src_city = "企业名称行政区划"
    if not prov:
        code = str(uscc or "").strip().upper()
        if len(code) >= 8 and code[2:4] in USCC_PROVINCE:
            prov = USCC_PROVINCE[code[2:4]]
    if city and prov:
        return {"value": prov + city, "source": "%s + 登记机关行政区划码" % src_city,
                "reason": ""}
    if city:
        return {"value": city, "source": src_city,
                "reason": "只从企业名称识别到市，未取得省（地址与信用代码均未给出）"}
    if prov:
        return {"value": prov, "source": "登记机关行政区划码",
                "reason": "只到省级：注册地址未取得、企业名称未含市级行政区划"}
    return {"value": "", "source": "",
            "reason": "注册地址、企业名称与统一社会信用代码都未能确定地区，需人工填写"}


def industry_from_scope(company_name: str = "", business_scope: str = "",
                        registered_industry: str = "",
                        sales_goods: Optional[List[str]] = None,
                        resolved: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """推导行业口径（**唯一实现走 `industry_resolver`**，本函数只做装配与标注）。

    优先级：
      ① 分析已经算好的 `_industry_resolved`（多来源加权，最权威）；
      ② 现算 `resolve_industry(名称, 登记行业, 经营范围, 销项品名)`；
      ③ 都拿不到 ⇒ 留空 + 原因。
    返回 `{value, source, confidence, reason, note}`；`note` 用于说明"登记口径与采用口径不一致"等。
    """
    if isinstance(resolved, dict) and str(resolved.get("industry") or "").strip():
        return {
            "value": str(resolved.get("industry") or "").strip(),
            "source": "分析结果（%s）" % (resolved.get("source") or "来源未标注"),
            "confidence": str(resolved.get("confidence") or ""),
            "reason": "",
            "note": str(resolved.get("scope_note") or ""),
        }
    try:
        from engine.industry_resolver import resolve_industry       # noqa: PLC0415
    except Exception as exc:                                        # noqa: BLE001
        return {"value": "", "source": "", "confidence": "",
                "reason": "行业解析器不可用：%s" % exc, "note": ""}

    log: List[str] = []
    try:
        res = resolve_industry(company_name=str(company_name or ""),
                               registered_industry=str(registered_industry or ""),
                               sales_goods=list(sales_goods or []),
                               business_scope=str(business_scope or ""),
                               pipeline_log=log)
    except Exception as exc:                                        # noqa: BLE001
        return {"value": "", "source": "", "confidence": "",
                "reason": "行业解析失败：%s" % exc, "note": ""}

    ind = str(res.get("industry") or "").strip()
    if not ind:
        return {"value": "", "source": "", "confidence": "无",
                "reason": "名称、经营范围与发票品名都未能识别出行业，需人工填写",
                "note": ""}
    return {
        "value": ind,
        "source": "系统解析（%s）" % (res.get("source") or "来源未标注"),
        "confidence": str(res.get("confidence") or ""),
        "reason": "",
        "note": str(res.get("scope_note") or ""),
    }


def period_parts(period: Any) -> Tuple[str, str]:
    """把「2025-01 至 2025-12」/「2025-01~2025-12」/「2025年度」解析成 `(起, 止)` 日期。

    解析不出返回 `("", "")`（**不猜**）；只给年份时按整年（YYYY-01-01 ~ YYYY-12-31）。
    """
    text = str(period or "").strip()
    if not text:
        return "", ""
    text = text.replace("～", "~").replace("－", "-").replace("—", "-").replace("–", "-")
    # 「YYYY-MM 至 YYYY-MM」/「YYYY-MM ~ YYYY-MM」
    m = re.search(r"(\d{4})\s*[-年/.]\s*(\d{1,2}).{0,6}?(\d{4})\s*[-年/.]\s*(\d{1,2})", text)
    if m:
        y1, m1, y2, m2 = (int(x) for x in m.groups())
        if 1 <= m1 <= 12 and 1 <= m2 <= 12:
            return _month_end(y1, m1, start=True), _month_end(y2, m2, start=False)
    # 「YYYY年度」/ 只有一年
    y = re.search(r"(\d{4})\s*年?", text)
    if y:
        yy = int(y.group(1))
        if 1990 <= yy <= 2100:
            return "%04d-01-01" % yy, "%04d-12-31" % yy
    return "", ""


def _month_end(year: int, month: int, *, start: bool) -> str:
    if start:
        return "%04d-%02d-01" % (year, month)
    # 月末：下月 1 号减一天
    if month == 12:
        return "%04d-12-31" % year
    import calendar                                                # noqa: PLC0415
    last = calendar.monthrange(year, month)[1]
    return "%04d-%02d-%02d" % (year, month, last)


def period_from_analysis(report: Dict[str, Any]) -> Dict[str, Any]:
    """从分析结果取**稽查期间**（报告期间 ⇒ 起止日期）。"""
    report = report or {}
    er = report.get("enterprise_readable_report") or {}
    ident = er.get("identity") if isinstance(er.get("identity"), dict) else {}
    te = report.get("target_entity") or {}
    raw = str(ident.get("period") or te.get("period") or "").strip()
    if not raw:
        return {"value": "", "raw": "", "source": "",
                "reason": "分析结果未给出报告期间，无法推导稽查期间"}
    ps, pe = period_parts(raw)
    if not (ps and pe):
        return {"value": "", "raw": raw, "source": "",
                "reason": "分析结果的报告期间「%s」无法解析成起止日期" % raw}
    return {"value": (ps, pe), "raw": raw, "source": "分析结果（报告期间）", "reason": ""}


def tax_scopes_from_analysis(report: Dict[str, Any]) -> Dict[str, Any]:
    """从分析结果的申报表数据推导**税种范围**（只认已上传申报表覆盖的税种）。"""
    report = report or {}
    decls = report.get("tax_declarations")
    if not isinstance(decls, list) or not decls:
        return {"value": [], "source": "",
                "reason": "分析结果未包含申报表数据（未上传申报表），无法推导税种范围"}
    #: 申报表类型 → 税种名（与 `project_service` 的税种选项同字面量，取值见 levy_nature）
    KIND_CN = {
        "vat": "增值税", "cit": "企业所得税", "iit": "个人所得税",
        "stamp": "印花税", "urban": "城市维护建设税", "edu": "教育费附加",
        "local_edu": "地方教育附加", "property": "房产税", "land": "城镇土地使用税",
    }
    got: List[str] = []
    for d in decls:
        if not isinstance(d, dict):
            continue
        k = str(d.get("_declaration_type") or "").strip().lower()
        cn = KIND_CN.get(k)
        if cn and cn not in got:
            got.append(cn)
    if not got:
        return {"value": [], "source": "",
                "reason": "申报表数据里未识别到可用的税种类型"}
    return {"value": got, "source": "分析结果（已上传申报表）", "reason": ""}


def _txt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v == 0:
        return ""
    return str(v).strip()


def analysis_values(report: Dict[str, Any],
                    company_row: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
    """把一次分析的结果整理成 `{字段: {value, source, reason}}`（**不写库**）。

    `company_row` = `sys_company_info` 行（工商档案/缓存，唯一权威）。
    工商类字段优先取该行，缺项再退回分析 `target_entity`；两者都没有 ⇒ 空 + 原因。
    """
    report = report or {}
    te = report.get("target_entity") or {}
    er = report.get("enterprise_readable_report") or {}
    ident = er.get("identity") if isinstance(er.get("identity"), dict) else {}
    row = company_row or {}
    out: Dict[str, Dict[str, Any]] = {}

    def pick(*vals: Any) -> str:
        for v in vals:
            s = _txt(v)
            if s:
                return s
        return ""

    # ── 身份 ──
    uscc = pick(row.get("tax_id"), te.get("uscc"), ident.get("taxpayer_id"))
    out["taxpayer_id"] = {"value": uscc,
                          "source": "工商档案" if _txt(row.get("tax_id")) else "分析结果",
                          "reason": "" if uscc else "工商信息与资料中均未取得统一社会信用代码"}

    # ── 工商 7 项 ──
    for key, label in (("legal_representative", "法定代表人"),
                       ("registered_capital", "注册资本"),
                       ("established_date", "成立日期"),
                       ("registration_status", "登记状态"),
                       ("registered_address", "注册地址"),
                       ("business_scope", "经营范围"),
                       ("company_type", "公司类型")):
        alt = {"legal_representative": te.get("legal_representative") or te.get("legal_person"),
               "registered_capital": te.get("registered_capital"),
               "established_date": te.get("established_date"),
               "registered_address": te.get("address"),
               "business_scope": te.get("business_scope"),
               "company_type": te.get("company_type"),
               "registration_status": None}.get(key)
        v = pick(row.get(key), alt)
        out[key] = {"value": v,
                    "source": "工商档案" if _txt(row.get(key)) else ("分析结果" if v else ""),
                    "reason": "" if v else "工商信息与资料中均未取得%s" % label}

    # ── 行业（权威：分析已算出的 _industry_resolved）──
    ind_suggest = industry_from_scope(
        company_name=pick(te.get("name"), ident.get("subject_name"), row.get("name")),
        business_scope=pick(out["business_scope"]["value"]),
        registered_industry=pick(te.get("industry_registered")),
        sales_goods=list(te.get("_industry_goods") or []),
        resolved=te.get("_industry_resolved") if isinstance(te.get("_industry_resolved"), dict) else None,
    )
    out["industry"] = {"value": ind_suggest["value"], "source": ind_suggest["source"],
                       "reason": ind_suggest["reason"], "confidence": ind_suggest["confidence"],
                       "note": ind_suggest.get("note") or ""}

    # ── 地区（注册地址解析，确定性）──
    reg = region_of(out["registered_address"]["value"],
                    company_name=pick(te.get("name"), ident.get("subject_name"), row.get("name")),
                    uscc=uscc)
    out["region"] = {"value": reg["value"],
                     "source": reg["source"] if reg["value"] else "",
                     "reason": reg["reason"]}

    # ── 稽查期间 ──
    per = period_from_analysis(report)
    out["period_start"] = {"value": per["value"][0] if per["value"] else "",
                           "source": per["source"], "reason": per["reason"]}
    out["period_end"] = {"value": per["value"][1] if per["value"] else "",
                         "source": per["source"], "reason": per["reason"]}

    # ── 税种范围 ──
    sc = tax_scopes_from_analysis(report)
    out["tax_scopes"] = {"value": sc["value"], "source": sc["source"], "reason": sc["reason"]}
    return out


def suggest_for_project(project: Dict[str, Any],
                        report: Optional[Dict[str, Any]] = None,
                        company_row: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """给「编辑项目」表单用的逐字段建议（**只建议、不写库**）。

    返回 `{"fields": {key: {value, suggested, current, source, reason, why_kept}}, ...}`
      · `suggested` = 建议值（已按"只填空/有出入才建议"过滤后的**最终建议**）；
      · `why_kept` = 该字段保留现有值的原因（有值且与建议一致 / 用户已填且分析未给出）；
      · 前端据此填列，并在提示区显示来源与不可得原因（**不得静默**）。
    """
    project = project or {}
    vals = analysis_values(report or {}, company_row)
    fields: Dict[str, Dict[str, Any]] = {}
    for key in SYNC_FIELDS:
        cur = project.get(key)
        sug = vals.get(key) or {"value": "", "source": "", "reason": "无推导来源"}
        cur_s = _norm(cur)
        sug_s = _norm(sug.get("value"))
        if not sug_s:
            # 推导不出 ⇒ 保留现值，如实说明为什么没填
            fields[key] = {
                "value": cur_s, "suggested": "", "current": cur_s,
                "source": "", "reason": sug.get("reason") or "无推导来源",
                "why_kept": "系统未推导出该字段（%s），保留现有值"
                            % (sug.get("reason") or "无推导来源"),
                "confidence": str(sug.get("confidence") or ""), "note": sug.get("note") or "",
            }
        elif sug_s == cur_s:
            fields[key] = {"value": cur_s, "suggested": "", "current": cur_s,
                           "source": sug.get("source") or "", "reason": "",
                           "why_kept": "现有值已与系统推导一致",
                           "confidence": str(sug.get("confidence") or ""), "note": sug.get("note") or ""}
        else:
            # 有出入 ⇒ 建议更新（这就是"工商信息有出入就自动更新"的前端呈现）
            fields[key] = {"value": cur_s or sug_s, "suggested": sug_s, "current": cur_s,
                           "source": sug.get("source") or "", "reason": "",
                           "why_kept": "",
                           "confidence": str(sug.get("confidence") or ""), "note": sug.get("note") or ""}
    return {"fields": fields,
            "sources": sorted({str(f.get("source")) for f in fields.values() if f.get("source")}),
            "missing": {k: f["reason"] for k, f in fields.items() if f.get("reason")}}


def _norm(v: Any) -> str:
    """归一化用于**比较**（不是用于写入）：None/空 ⇒ ""；列表 ⇒ 逗号串；数值去尾零。

    ★ 数值必须按"数值相等"比较：`1000` 与 `1000.0`、`"1000"` 与 `"1000.0"` 都是同一个值。
      首版只做了 `str()`，导致回写后再次读出来变成"有出入"（DB 存 int 1000、
      推导值是字符串 "1000.0"）⇒ 每次打开编辑页都提示"注册资本有出入"（假差异）。
    """
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return ",".join(str(x).strip() for x in v if str(x).strip())
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        f = float(v)
        return ("%d" % f) if f == int(f) else str(f)
    s = str(v).strip()
    if s in ("None", "null", "undefined"):
        return ""
    # 形如数字的字符串 ⇒ 归一为数值文本（"1000.00" → "1000"、"1000.5" → "1000.5"）
    try:
        if s and all(c in "0123456789.-+" for c in s):
            f = float(s)
            return ("%d" % f) if f == int(f) else str(f)
    except (TypeError, ValueError):
        pass
    return s
