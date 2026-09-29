# -*- coding: utf-8 -*-
"""个人信息（PIPL）脱敏 —— **企业版报告对外输出的唯一收敛点**。

## 为什么要有这个模块（根因）

原报告链路里**根本没有个人信息脱敏层**：凡是流到报告的个体级数据一律原样输出。外部点评实测：
「杨莹 670,000、初永伟 275,000、李昭阳 137,000；私户付款 10 笔逐笔列示」——
员工**真实姓名**与**个人银行账户收付金额明细**逐笔进了给企业看（且可能外传）的报告正文。

《个人信息保护法》第六条（最小必要 + 目的限定）与第五十一条（分级分类、加密/去标识化）要求：
对外文书不应暴露自然人身份与账户级金额；但**税务风险检查本身需要知道"有这些人、这些金额"**
才能让企业去核实——所以正确的做法**不是删掉事实，而是去掉身份**：
「员工 A（姓*）」「个人账户 1（尾号 ****1234）」+ 明确标注本报告**属内部资料**。

## 与内部底稿的分工（刻意不同，勿统一）

| 文书 | 是否脱敏 | 理由 |
|---|---|---|
| 企业版报告 `enterprise_readable_report` | **脱敏**（本模块） | 对外交付/可能外传 |
| 内部工作底稿 `comprehensive` / `all_findings` | **不脱敏** | 检查员必须能对上具体人、具体账号去取证 |

## 通用规则（数据表驱动，新增同类字段只加一行）

- 键名命中 → 按该类的脱敏算法处理（姓名 / 证件号 / 手机号 / 银行账号）；
- 正文中的姓名：先在**人名键**上收集姓名集合，再在全文做字面替换；
- **绝不误伤企业名**：凡该姓名是任何"单位/企业名"的子串（如"海更"之于"深圳海更数字传媒"），
  或该姓名本身像机构（含"公司/企业/中心/厂/店/所/行/院/部/社/台/站/集团/事务所"），一律不改。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set, Tuple

# ── ① 键名分类表（唯一权威；新增字段名只加一行）────────────────────────────────
_NAME_KEYS: Set[str] = {
    "姓名", "员工姓名", "员工", "人员", "人名", "客户姓名", "客户名", "供应商联系人",
    "收款人", "付款人", "收款方联系人", "经办人", "联系人", "负责人", "股东", "法定代表人",
    "法人", "实际控制人", "财务负责人", "办税人", "开票人", "复核人", "领用姓名",
    "person", "person_name", "employee", "employee_name", "payee", "payer", "contact",
}
_ID_KEYS: Set[str] = {
    "身份证", "身份证号", "身份证号码", "证件号", "证件号码", "统一社会信用代码个人",
    "id_card", "id_no", "identity_no",
}
_PHONE_KEYS: Set[str] = {
    "手机号", "手机号码", "手机", "电话", "联系电话", "联系方式", "phone", "mobile", "tel",
}
_ACCT_KEYS: Set[str] = {
    "账号", "账户", "银行账号", "银行账户", "卡号", "银行卡号", "收款账号", "付款账号",
    "对方账号", "本方账号", "account", "account_no", "bank_account", "card_no",
}

# 机构性字样的姓名候选：命中即认为不是自然人，不脱敏
_ORG_WORDS = ("公司", "企业", "中心", "工厂", "厂", "店", "事务所", "银行", "集团", "超市",
              "商场", "营业部", "分公司", "有限公司", "合作社", "工作室", "研究院", "医院",
              "学校", "政府", "街道", "税务", "平台", "网络", "科技", "商贸", "实业")

# 收集企业/单位名的键名（用于保护"姓名是企业名子串"的情形）
_ORG_NAME_KEYS: Set[str] = {
    "名称", "公司名称", "企业名称", "单位名称", "对方单位", "对方名称", "客户名称",
    "供应商名称", "销售方", "购买方", "销方", "购方", "seller", "buyer", "company",
    "company_name", "counterparty", "vendor", "customer", "name",
}

# ★ 2026-09-29：**交易对手类键**——既可能是单位也可能是自然人。税务检查里
#   自然人对手方（私户收款人/付款人）是核心线索，其姓名常只出现在**正文句子**里
#   （如「收款人 杨莹 收到 670,000 元」），而不在任何"姓名"字段中。
#   故必须从**源数据**按此表预收集人名集合，再到报告全文做字面替换——
#   只在已渲染文本里找名是无解的（没有 NER，无法从自由文本识别姓名）。
#   方向偏"宁可多脱敏"（脱敏过度只影响可读性；脱敏不足是合规事故）。
_COUNTERPARTY_KEYS: Set[str] = {
    "交易对手", "交易对手方", "对方户名", "对方账户名", "对手方", "对方", "收付方",
    "counterparty", "opponent", "trade_party", "payee_name", "payer_name",
}
# 地名/机构性后缀：命中即不视为自然人姓名
_NON_PERSON_SUFFIX = ("省", "市", "区", "县", "镇", "乡", "村", "路", "街", "道", "州",
                      "局", "署", "校", "站", "台", "社", "部", "所", "行", "院", "厂", "店")

_CJK_RE = re.compile(r"[\u4e00-\u9fa5]")
_NOTICE = ("个人信息保护说明：本报告涉及的自然人姓名、身份证件号码、手机号、银行账号等信息，"
           "已按《中华人民共和国个人信息保护法》最小必要与去标识化要求脱敏处理；"
           "本报告属内部资料，不得对外提供或公开传播。如需核对具体个人身份，"
           "请在本机构内部工作底稿中查阅。")

# 脱敏后的占位序号（保证同一姓名在同一份报告里映射到同一个占位符）
_PERSON_PLACEHOLDER = "自然人"


def mask_person_name(name: str) -> str:
    """姓名脱敏：保留首字（姓），其余以 `*` 等长替换。如 杨莹 → 杨*，初永伟 → 初**。"""
    s = str(name or "").strip()
    if len(s) < 2 or not _CJK_RE.search(s):
        return s
    return s[0] + "*" * (len(s) - 1)


def mask_id_no(v: str) -> str:
    """证件号脱敏：保留首尾各 1 位，中间以 `*` 覆盖（长度不保留，避免可推算）。"""
    s = str(v or "").strip()
    if len(s) < 4:
        return "*" * len(s)
    return s[0] + "*" * 6 + s[-1]


def mask_phone(v: str) -> str:
    """手机号脱敏：保留前 3 位与后 4 位（138****1234）。"""
    s = str(v or "").strip()
    if len(s) < 7:
        return "*" * len(s)
    return s[:3] + "*" * 4 + s[-4:]


def mask_account(v: str) -> str:
    """银行账号脱敏：保留前 4 位与后 4 位。"""
    s = str(v or "").strip()
    if len(s) < 9:
        return "*" * len(s)
    return s[:4] + "*" * 6 + s[-4:]


def _is_orgish(text: str) -> bool:
    s = str(text or "")
    return any(w in s for w in _ORG_WORDS)


def _looks_like_person(text: str) -> bool:
    """自然人姓名启发式（仅用于**源数据**中的对手方字段，宁可多脱敏）。

    条件：2~4 个纯中文、不含机构字样、不以地名单字结尾、不含数字/字母。
    """
    s = str(text or "").strip()
    if not (2 <= len(s) <= 4):
        return False
    if not all(_CJK_RE.match(ch) for ch in s):
        return False
    if _is_orgish(s):
        return False
    if s[-1] in _NON_PERSON_SUFFIX:
        return False
    return True


def _collect(obj: Any,
             person_names: Set[str],
             org_names: Set[str],
             stats: Dict[str, int],
             _seen: Set[int] = None,
             _depth: int = 0) -> None:
    """第一遍：收集人名（键名驱动 + 源数据对手方启发式）与单位名（用于保护同名子串）。

    ★ 2026-09-29 实测坑：真实 `report_data` 含**循环引用**，无保护地递归会 RecursionError
      → 被上层 `except` 吞掉 → 脱敏静默失效（dump 里连 `_pii_notice` 都没有）。
      故按 `id()` 去重 + 深度上限。
    """
    if _depth > 24:
        return
    if _seen is None:
        _seen = set()
    if isinstance(obj, (dict, list, tuple)):
        if id(obj) in _seen:
            return
        _seen.add(id(obj))
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = str(k)
            if isinstance(v, str):
                val = v.strip()
                if not val:
                    continue
                if key in _NAME_KEYS and 2 <= len(val) <= 6 and _CJK_RE.search(val) \
                        and not _is_orgish(val):
                    person_names.add(val)
                    stats["person_names_found"] = stats.get("person_names_found", 0) + 1
                elif key in _ORG_NAME_KEYS:
                    org_names.add(val)
                    stats["org_names_found"] = stats.get("org_names_found", 0) + 1
                    # 对手方字段同时进自然人候选（后续按机构判定与子串规则互斥过滤）
                    if key in _COUNTERPARTY_KEYS and _looks_like_person(val):
                        person_names.add(val)
                        stats["person_candidates"] = stats.get("person_candidates", 0) + 1
                elif key in _COUNTERPARTY_KEYS and _looks_like_person(val):
                    person_names.add(val)
                    stats["person_candidates"] = stats.get("person_candidates", 0) + 1
            else:
                _collect(v, person_names, org_names, stats, _seen, _depth + 1)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect(v, person_names, org_names, stats, _seen, _depth + 1)


def _redact(obj: Any, mapping: Dict[str, str], stats: Dict[str, int],
            _seen: Set[int] = None, _depth: int = 0) -> Any:
    """第二遍：键名驱动脱敏 + 正文姓名替换（不改动屏幕/内部底稿）。"""
    if _depth > 24:
        return obj
    if _seen is None:
        _seen = set()
    if isinstance(obj, (dict, list, tuple)):
        if id(obj) in _seen:
            return obj          # 循环引用：原样返回，避免死循环
        _seen.add(id(obj))
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            key = str(k)
            if isinstance(v, str):
                val = v
                if key in _NAME_KEYS and val.strip() in mapping:
                    out[k] = mapping[val.strip()]
                    stats["names_masked"] = stats.get("names_masked", 0) + 1
                    continue
                if key in _ID_KEYS or key in _PHONE_KEYS or key in _ACCT_KEYS:
                    masked = (mask_id_no(val) if key in _ID_KEYS
                              else mask_phone(val) if key in _PHONE_KEYS
                              else mask_account(val))
                    if masked != val:
                        stats["sensitive_masked"] = stats.get("sensitive_masked", 0) + 1
                    out[k] = masked
                    continue
                out[k] = _replace_names(val, mapping, stats)
            else:
                out[k] = _redact(v, mapping, stats, _seen, _depth + 1)
        return out
    if isinstance(obj, (list, tuple)):
        return [_redact(v, mapping, stats, _seen, _depth + 1) for v in obj]
    return obj


def _replace_names(text: str, mapping: Dict[str, str], stats: Dict[str, int]) -> str:
    if not text or not mapping:
        return text
    s = text
    for name, masked in mapping.items():
        if name and name in s:
            n = s.count(name)
            s = s.replace(name, masked)
            stats["names_masked"] = stats.get("names_masked", 0) + n
    return s


def redact_enterprise_report(report: Any, source: Any = None) -> Any:
    """企业版报告个人信息脱敏（**唯一入口**）。

    `source` = 本次分析的**源数据**（`report_data`）。人名清单**必须同时从源数据收集**：
    姓名常只出现在正文句子里（「收款人 杨莹 收到 670,000 元」），而自由文本里没有
    字段可依；只在已渲染文本里找名是无解的。从源数据按人名/对手方字段预收集姓名集合，
    再回报告全文做字面替换 —— 这是唯一可行的通用做法。

    幂等：已脱敏文本不含真实姓名，重复调用不再变化。
    返回新结构并写入 `_pii_notice`（供渲染层显示"内部资料"标识）。
    """
    if not isinstance(report, dict):
        return report
    stats: Dict[str, int] = {}
    person_names: Set[str] = set()
    org_names: Set[str] = set()
    # 目标企业名本身也算"单位名"，防止把企业名的一部分当人名改掉
    _idn = report.get("identity") if isinstance(report.get("identity"), dict) else {}
    _oc = (_idn or {}).get("organization") or {}
    for v in ((_oc or {}).values() if isinstance(_oc, dict) else []):
        if isinstance(v, str) and v.strip():
            org_names.add(v.strip())
    _collect(report, person_names, org_names, stats)
    if source is not None and source is not report:
        _collect(source, person_names, org_names, stats)

    # 排除：① 是企业名的子串；② 自身带机构字样；③ 不是纯中文
    mapping: Dict[str, str] = {}
    for name in sorted(person_names, key=len, reverse=True):
        if _is_orgish(name):
            continue
        if any(name in o for o in org_names if o and o != name):
            continue
        if not _CJK_RE.search(name):
            continue
        mapping[name] = mask_person_name(name)

    if not mapping:
        out = dict(report)
        out["_pii_notice"] = _NOTICE
        out["_pii_stats"] = {"person_names_found": stats.get("person_names_found", 0),
                             "names_masked": 0, "sensitive_masked": 0,
                             "note": "未发现需脱敏的自然人姓名/证件号/账号。"}
        return out

    out = _redact(report, mapping, stats)
    if isinstance(out, dict):
        out["_pii_notice"] = _NOTICE
        out["_pii_stats"] = {
            "person_names_found": len(mapping),
            "names_masked": stats.get("names_masked", 0),
            "sensitive_masked": stats.get("sensitive_masked", 0),
            "org_names_protected": len(org_names),
        }
    return out
