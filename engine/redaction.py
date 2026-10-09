# -*- coding: utf-8 -*-
"""数据脱敏（用户第 5 批 任务2「按角色脱敏姓名、账号、身份证、金额」）。

## 口径

- **角色 → 脱敏项**由 `config/report_compliance.json` 的 `redaction_roles` 决定（**唯一权威**），
  本模块只实现"怎么脱"，不决定"要不要脱"。
- 遍历一律走**唯一权威** `engine.plain_language.walk_strings_inplace`
  （迭代 + `id()` 去环，禁递归）——项目已因递归爆栈导致整份报告的文本加工**从未生效**过一次。
- **脱敏必须在"对外版本"上做**：内部底稿保留原文。两者是**两个对象**，不是同一对象被改两次。
- 脱敏后必须留下痕：`redaction_report(obj, role)` 返回**命中项与条数**（改了要看得见）。

## 脱敏规则（★ 唯一权威表 `_RULES`，新增一类只加一行）

| 项 | 处理 | 例 |
|---|---|---|
| 姓名 | 保留姓氏 + 「某」（已是"某"形式则不动） | 张伟 → 张某 |
| 账号 | 首 4 位 + `****` + 末 2 位 | 6222020200112233 → 6222****33 |
| 身份证 | 首 3 位 + `***********` + 末 4 位 | 110101199001011234 → 110***********1234 |
| 金额 | 量级化（保留数量级，不保留精确数） | 1,234,567.89 元 → 约 123 万元 |
| 联系方式 | 手机/邮箱部分遮盖 | 13812345678 → 138****5678 |

⚠ **金额量级化会改变数字**，故只在**对外版**上做；内部底稿与四类不变性指纹一律用原文。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

#: 脱敏项（★ 唯一权威：与 config 的 redaction_roles 字段一一对应）
REDACTION_ITEMS: Tuple[str, ...] = ("name", "account", "id_card", "amount", "contact")


def _cfg() -> Dict[str, Any]:
    """报告合规配置（★ 唯一权威：engine/report_compliance.load_config）。

    ★ 2026-10-08 收敛：本模块曾自持 `_COMPLIANCE` 路径 + 解析逻辑，读取**同一份**
      `config/report_compliance.json`（与 report_compliance 两份实现并存，改路径/改
      解析口径即漂移）。现只**薄转发**，不自持字面量。
    """
    from engine.report_compliance import load_config
    return load_config()


def role_policy(role: str) -> Dict[str, Any]:
    """角色 → 脱敏策略；**未知角色按最严处理**（全部脱敏），绝不默认不脱敏。"""
    roles = _cfg().get("redaction_roles") or {}
    pol = roles.get(str(role or ""))
    if not isinstance(pol, dict):
        return {"label": "未登记角色（按最严脱敏）", "role": str(role or ""),
                **{k: True for k in REDACTION_ITEMS}}
    out = dict(pol)
    out["role"] = str(role)
    for k in REDACTION_ITEMS:
        out[k] = bool(pol.get(k, True))
    return out


def roles() -> List[str]:
    return sorted((_cfg().get("redaction_roles") or {}).keys())


# ── 单项脱敏 ─────────────────────────────────────────────────────────────────

# ── 姓名：**按姓氏表判定**，而不是按位置取字符 ──────────────────────────────
# ★ 事故（本轮实测两例）：初版 `([\u4e00-\u9fa5])([\u4e00-\u9fa5]{1,3})(?=先生|女士…)`
#   ① 从左到右扫描 "张某先生向李小明女士" 命中「向+李小明」⇒ 输出「向某」（**吃掉姓氏**）；
#   ② 「法定代表人王建国签字」把「王建国签」整体当人名 ⇒ 输出「王某字」（**吃掉正文**）。
#   根因：汉字没有词边界，按"称谓前固定 2-4 字"取必然错位。
# ★ 修法：以**称谓/身份词**为锚点，用**姓氏表 + 复姓表 + 尾部停用字**确定人名跨度。
_CALLS = ("先生", "女士", "经理", "法人", "股东", "负责人", "老板")
_SURNAMES = set(
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛"
    "奚范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍"
    "余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席"
    "季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯昝管卢莫欧"
    # ★ 补漏（实测：初版漏了「刘」这类超常见姓 ⇒ 「监事刘建国」整句没被脱敏）
    "刘曾叶丁崔谭陆石廖付白闫段侯龙黎龚覃武向章岳邢屠蒙池乔郁党翟申冉桂牛边燕尚温庄晏柴阎连茹艾容古易慎戈满弘匡国文寇广禄师巩聂勾冷辛简饶沙养巢关查荆红游权盖益桓公"
)
#: 复姓（**只保留前两字 + 某**）
_COMPOUND = ("欧阳", "司马", "上官", "诸葛", "东方", "皇甫", "尉迟", "公孙", "慕容",
             "司徒", "令狐", "宇文", "长孙", "独孤", "南宫", "西门", "夏侯", "端木")
#: 尾部停用字：人名后面紧接的动词/助词/标点被误吞时的"回退"判据（**数据驱动**）
#: ⚠ **不得**把「年/月/日/号/市/省/县/区/镇/街/路」放进来 —— 它们是**合法的名字末字**
#:   （实测：把「月」放进来后「欧阳明月」被截成「欧阳明」⇒ 输出「欧阳某月」，
#    多留一个字、少脱一个字，且看不出报错）。
_NAME_TAIL_STOP = set("签说称为是的等及和与报提交称，。、；：（）()")

#: 「身份词 + 人名」（人名在**后**）——无称谓的人名靠它兜住
_CTX_BEFORE = ("法定代表人", "法人代表", "实际控制人", "财务负责人", "法人", "股东",
               "收款人", "付款人", "客户", "供应商", "员工", "联系人", "负责人",
               "办税人", "监事", "董事", "经办人", "签收人", "代理人")

_NAME_BEFORE = re.compile(r"([\u4e00-\u9fa5]{2,4})(?=(?:%s))" % "|".join(_CALLS))
_NAME_AFTER = re.compile(r"(?:%s)\s*[:：为是]?\s*([\u4e00-\u9fa5]{2,4})"
                         % "|".join(sorted(_CTX_BEFORE, key=len, reverse=True)))


def _ok_head(seg: str) -> bool:
    return len(seg) >= 2 and (seg[:2] in _COMPOUND or seg[:1] in _SURNAMES) and "某" not in seg


def _span_right(cand: str) -> str:
    """人名紧接**称谓之前** ⇒ 从右往左取。

    ★ 判据不是"最长匹配"（那样会把**上文里的姓氏**一起吃进来：
      "…向李小明女士" 会取「向李小」⇒ 输出「向某」，实测踩过）。
      规则：① 复姓+双名（4 字）优先；② 否则取**最短的有效跨度**（2 字优先于 3 字，
      仅当 3 字跨度的首字是姓氏而 2 字的首字**不是**时才取 3 字）。
    """
    s = str(cand or "")
    if len(s) >= 4:
        seg = s[-4:]
        if seg[-1] not in _NAME_TAIL_STOP and seg[:2] in _COMPOUND and _ok_head(seg):
            return seg
    if len(s) >= 3:
        seg3 = s[-3:]
        if seg3[-1] not in _NAME_TAIL_STOP and seg3[:2] in _COMPOUND:
            return seg3
        if seg3[-1] not in _NAME_TAIL_STOP and seg3[0] in _SURNAMES:
            seg2 = s[-2:]
            if seg2[:1] not in _SURNAMES and seg2[:2] not in _COMPOUND:
                return seg3
    if len(s) >= 2:
        seg2 = s[-2:]
        if (seg2[:1] in _SURNAMES or seg2[:2] in _COMPOUND) and "某" not in seg2:
            return seg2
    return ""


def _span_left(cand: str) -> str:
    """人名紧接**身份词之后** ⇒ 从左往右取；末尾落在停用字上就回退一位。

    复姓优先（「欧阳明月」→ 欧阳某 而不是 欧某）。
    """
    s = str(cand or "")
    for L in (4, 3, 2):
        if len(s) >= L:
            seg = s[:L]
            if seg and seg[-1] in _NAME_TAIL_STOP:
                seg = seg[:-1]
            if _ok_head(seg):
                return seg
    return ""


def _mask(span: str) -> str:
    return (span[:2] + "某") if span[:2] in _COMPOUND else (span[:1] + "某")


def redact_names(text: str) -> Tuple[str, int]:
    """按姓氏表脱敏人名，返回 (新文本, 命中数)。两轮：称谓锚点 + 身份词锚点。"""
    cnt = 0
    out = str(text or "")
    for m in reversed(list(_NAME_BEFORE.finditer(out))):
        span = _span_right(m.group(1))
        if not span:
            continue
        start = m.start(1) + len(m.group(1)) - len(span)
        out = out[:start] + _mask(span) + out[start + len(span):]
        cnt += 1
    spans = []
    for m in _NAME_AFTER.finditer(out):
        span = _span_left(m.group(1))
        if span:
            spans.append((m.start(1), len(span), _mask(span)))
    for start, ln, rep in reversed(spans):
        out = out[:start] + rep + out[start + ln:]
        cnt += 1
    return out, cnt


# 账号/身份证/手机：★ **不能用 `\b`** —— 汉字与数字之间不存在词边界，
#   实测导致「账号6222020200112233」**完全没被脱敏**（不报错，只是"没生效"）。
_ID_CARD_RE = re.compile(r"(?<!\d)(\d{3})\d{11}(\d{4})(?!\d)|(?<!\d)(\d{3})\d{8}(\d{4})(?!\d)")
_ACCOUNT_RE = re.compile(r"(?<!\d)(\d{4})\d{6,}(\d{2})(?!\d)")
_PHONE_RE = re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)")
_EMAIL_RE = re.compile(r"\b([\w.\-]{1,2})[\w.\-]*@([\w\-]+(?:\.[\w\-]+)+)\b")
_AMOUNT_RE = re.compile(r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*元")


def _mask_account(m: "re.Match") -> str:
    return m.group(1) + "****" + m.group(2)


def _mask_id_card(m: "re.Match") -> str:
    if m.group(1):
        return m.group(1) + "***********" + m.group(2)
    return m.group(3) + "********" + m.group(4)


def _mask_phone(m: "re.Match") -> str:
    return m.group(1) + "****" + m.group(2)


def _mask_email(m: "re.Match") -> str:
    return m.group(1) + "***@" + m.group(2)


def _magnitude(n: float) -> str:
    """金额量级化（只保留数量级，不保留精确数）。"""
    if n >= 1e8:
        return "约 %.2f 亿元" % (n / 1e8)
    if n >= 1e4:
        return "约 %.0f 万元" % (n / 1e4)
    if n >= 1e3:
        return "约 %.1f 千元" % (n / 1e3)
    return "不足千元"


def _mask_amount(m: "re.Match") -> str:
    try:
        v = float(str(m.group(1)).replace(",", ""))
    except Exception:
        return m.group(0)
    return _magnitude(v)


#: 项 → (正则, 替换函数)（★ 唯一权威表；`name` 走 `redact_names`，见 `redact_text`）
_RULES: Tuple[Tuple[str, Any, Any], ...] = (
    ("id_card", _ID_CARD_RE, _mask_id_card),
    ("account", _ACCOUNT_RE, _mask_account),
    ("contact", _PHONE_RE, _mask_phone),
    ("contact", _EMAIL_RE, _mask_email),
    ("amount", _AMOUNT_RE, _mask_amount),
)


def redact_text(text: str, policy: Dict[str, Any],
                counter: Optional[Dict[str, int]] = None) -> str:
    """按策略脱敏一段文本；`counter` 用于累计命中项（留痕）。"""
    s = str(text or "")
    if not s:
        return s
    for item, rx, fn in _RULES:
        if not policy.get(item):
            continue
        new, n = rx.subn(fn, s)
        if n:
            s = new
            if counter is not None:
                counter[item] = counter.get(item, 0) + n
    if policy.get("name"):
        s, n = redact_names(s)
        if n and counter is not None:
            counter["name"] = counter.get("name", 0) + n
    return s


def redact_obj(obj: Any, role: str = "external",
               counter: Optional[Dict[str, int]] = None) -> Any:
    """**原地**按角色脱敏整份对象（迭代 + 去环；返回同一对象）。"""
    pol = role_policy(role)
    cnt: Dict[str, int] = counter if counter is not None else {}
    if pol.get("amount"):
        _redact_amount_values(obj, cnt)
    try:
        from engine.plain_language import walk_strings_inplace
        return walk_strings_inplace(obj, lambda v, _k: redact_text(v, pol, cnt))
    except Exception:
        # 兜底：仍要遍历（不能因为工具不可用就"声称脱敏了却没做"）
        def _walk(o: Any, seen: set) -> None:
            if isinstance(o, dict):
                if id(o) in seen:
                    return
                seen.add(id(o))
                for k in list(o.keys()):
                    if isinstance(o[k], str):
                        o[k] = redact_text(o[k], pol, cnt)
                    else:
                        _walk(o[k], seen)
            elif isinstance(o, list):
                if id(o) in seen:
                    return
                seen.add(id(o))
                for i, v in enumerate(o):
                    if isinstance(v, str):
                        o[i] = redact_text(v, pol, cnt)
                    else:
                        _walk(v, seen)
        _walk(obj, set())
        return obj


def redaction_report(role: str, counter: Dict[str, int]) -> str:
    """脱敏留痕说明（自然句）。"""
    pol = role_policy(role)
    if not counter:
        return "本次对外版本未命中需脱敏的内容（按角色「%s」的规则扫描）。" % pol.get("label", role)
    parts = ["%s %d 处" % ({"name": "姓名", "account": "账号", "id_card": "身份证件号",
                            "amount": "金额（文本）", "amount_field": "金额（数值字段）",
                            "contact": "联系方式"}.get(k, k), v)
             for k, v in sorted(counter.items())]
    return "本次对外版本按角色「%s」完成脱敏：%s。" % (pol.get("label", role), "、".join(parts))


#: **数值型**金额字段的键名（★ 唯一权威：新增一类只加一行）。
#:   ⚠ 只脱敏**文本**是不够的：实测报告的 `tax_impact.basis/total` 是**数字**，
#:     正则扫不到 ⇒ 对外版仍会泄漏精确金额（"看起来脱敏了，其实最大的那个数没动"）。
_AMOUNT_VALUE_KEYS = (
    "basis", "total", "amount", "tax_amount", "tax_due", "payable", "receivable",
    "expense", "cost", "revenue", "sales", "income", "profit", "balance",
    "价税合计", "金额", "税额", "余额", "发生额", "收入", "成本", "费用",
)
#: 明确**不脱敏**的数值键（比例/税率/计数：脱敏会破坏语义）。
#: ⚠ 必须分两级：**精确**匹配（`n`/`rate` 这类短词）与**子串**匹配（长词）。
#:   初版把 `"n"` 也当子串比 ⇒ `"amount"` 里含 n ⇒ **嵌套金额字段被整体跳过**（实测）。
_SKIP_EXACT = {"n", "rate", "ratio", "pct", "percent", "count", "seq", "index",
               "i", "k", "v", "len"}
_SKIP_SUB = ("evidence_have", "evidence_need", "finding_count", "files_count",
             "risk_score", "confidence")


def _round_amount(v: Any) -> Any:
    """数值型金额 ⇒ **按万元四舍五入**（保留量级、不保留精确数）。"""
    try:
        f = float(v)
    except Exception:
        return v
    if f == 0:
        return v
    return float(round(f / 10000.0) * 10000)


def _redact_amount_values(obj: Any, counter: Dict[str, int]) -> Any:
    """对**数值型**金额字段做量级化（迭代 + 去环，禁递归）。"""
    seen: set = set()
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if id(cur) in seen:
                continue
            seen.add(id(cur))
            for k in list(cur.keys()):
                v = cur[k]
                kl = str(k).lower()
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    if kl in _SKIP_EXACT or any(x in kl for x in _SKIP_SUB):
                        continue
                    if any(str(x).lower() in kl for x in _AMOUNT_VALUE_KEYS):
                        nv = _round_amount(v)
                        if nv != v:
                            cur[k] = nv
                            counter["amount_field"] = counter.get("amount_field", 0) + 1
                    continue
                stack.append(v)
        elif isinstance(cur, list):
            if id(cur) in seen:
                continue
            seen.add(id(cur))
            for v in cur:
                if isinstance(v, (dict, list)):
                    stack.append(v)
    return obj


def copy_for_role(obj: Any, role: str) -> Tuple[Any, Dict[str, int], str]:
    """生成**该角色的副本**并脱敏（深拷贝，绝不改动内部底稿）。"""
    import copy as _copy
    clone = _copy.deepcopy(obj)
    counter: Dict[str, int] = {}
    redact_obj(clone, role, counter)
    return clone, counter, redaction_report(role, counter)


__all__ = ["REDACTION_ITEMS", "role_policy", "roles", "redact_text", "redact_names", "redact_obj",
           "redaction_report", "copy_for_role"]
