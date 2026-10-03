"""发票 / 流水 / 工资社保记录的**字段读取与语义判定**唯一权威（2026-09-25）

═══════════════════════════════════════════════════════════════════════════════
为什么必须收敛（根因）
═══════════════════════════════════════════════════════════════════════════════
同一件事（"取购方名称" / "判断是否作废红冲" / "取所属月份"）曾在多个模块各写一份，
且**实现并不一致**，导致同一张发票在不同检测器里得到不同结论：

  `_buyer`     3 份：其中 external_check_reminder 版**少认 `购买方名称` 别名**
  `_seller`    3 份：同理少认 `销售方名称`
  `_goods`     2 份：input_voucher 版**少认 `商品名称`**
  `_is_void_or_red` 2 份：invoice_pattern_detector 只看类型字样；
                        verified_rule_engine 还看状态/`is_void`/`is_red`/**负数金额**
                        → 同一张作废或红冲发票，一个模块判是、另一个判否
  `_row_period`     2 份：语义相同（重复实现）
  `_is_noise_name`  2 份：实现逐字相同，连 `_NOISE_PERSON_NAMES` 常量也重复定义两份

**后果**：作废/红冲率、客户集中度、人员统计等结论在不同章节可能互相矛盾 ——
与行业无关，对**所有企业**都成立。

═══════════════════════════════════════════════════════════════════════════════
设计原则
═══════════════════════════════════════════════════════════════════════════════
F1 **字段别名集中维护**：新增导出模板的列名，只在本文件加一行，不改各检测器。
F2 **判定取超集**：作废/红冲这类"命中即异常"的判定，合并时必须取**并集**
   （任一线索成立即为真）—— 漏判会放过风险，误判只多一次人工复核。
F3 **语义不同就改名，不要硬合并**：同名但参数/返回不同的函数（如
   `_wage_total(vouchers)->float` 与 `_wage_total(data)->(float,来源)`），
   合并会产生隐蔽 bug，应**改名区分**并在文档里写明用途。
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple

# ── F1：字段别名表（唯一维护处；新增导出模板列名只需在此加一项）────────────────
BUYER_KEYS: Tuple[str, ...] = (
    "buyer", "buyer_name", "购方名称", "购买方名称", "购买方", "购方",
)
SELLER_KEYS: Tuple[str, ...] = (
    "seller", "seller_name", "销方名称", "销售方名称", "销售方", "销方", "供应商名称",
)
GOODS_KEYS: Tuple[str, ...] = (
    "goods", "goods_name", "货物或应税劳务名称", "商品名称", "开票项目",
    "服务名称", "货物名称", "品名",
)
INV_TYPE_KEYS: Tuple[str, ...] = ("inv_type", "invoice_type", "发票类型", "票种")
STATUS_KEYS: Tuple[str, ...] = ("status", "发票状态", "票据状态", "状态")
PERIOD_KEYS: Tuple[str, ...] = (
    "period_start", "period_end", "所属期", "费款所属期", "期间", "月份", "month",
    "所属月份", "账期", "缴费所属期", "税款所属期", "所属期间", "记账月份", "凭证日期",
)
ACCOUNT_KEYS: Tuple[str, ...] = (
    "account", "科目", "科目名称", "会计科目", "acct", "account_name",
)

# ── F1b 凭证「科目编码」与「科目名称」是两个字段，不可混用（2026-10-03）───────────
# ★ 真实缺陷（用户 2026-10-03 复核疑点11 时暴露）：
#   真实凭证行的结构是 `{account: "600102", account_name: "主营业务收入/服务收入", ...}`
#   —— `account` 是**科目编码**，`account_name` 是**科目名称**。
#   而 `sum(... for v in vouchers if "主营业务收入" in str(v.get("account")))` 这类判据
#   读的是**编码**，永远匹配不到汉字科目名 ⇒ `凭证主营业务收入` 恒为 0.00。
#   实测后果（公司1 真账套）：「收入三源对比」写成
#   「凭证主营业务收入0.00元（开票0.00+未开票0.00） vs 销项发票7,035,008.58元」，
#   而账面真实主营业务收入是 **6,636,800.57 元**（不含税），×1.06 恰好等于
#   销项开票 7,035,008.58 元 —— 三源其实完全吻合，报告却呈现成"账上一分钱收入都没有"。
#   故此处把两类字段分开登记：**要名称就用 `ACCOUNT_NAME_KEYS`，要编码就用 `ACCOUNT_CODE_KEYS`**，
#   任何模块不得再写 `v.get("account")` 去比汉字科目名。
ACCOUNT_NAME_KEYS: Tuple[str, ...] = (
    "account_name", "科目名称", "会计科目", "科目全称", "科目", "acct_name", "subject_name",
)
ACCOUNT_CODE_KEYS: Tuple[str, ...] = (
    "account_code", "科目编码", "科目代码", "account", "acct", "科目号", "account_no",
)

# ── F2：发票「结构性证据」字段（2026-10-02 补充：成本/费用归属的第一刀）──────────
# ★ 真实缺陷（本轮根因之一）：`main._parse_invoice_sheet` 早已把表头「税收编码」映射成
#   `tax_code`、「计量单位」→`unit`、「业务类型」→`biz_type`；但全库 5 处读的是中文键
#   「**税收分类编码**」——真实列名是「**税收编码**」，故这些 `tc.startswith("3")` 判据
#   **永远取不到值**（实测 3620 行进项里 tax_code 非空 3354 行、而中文键恒空）⇒
#   服务类发票的判定全部静默失效。故此类字段的别名表与读取**唯一收敛到此处**，
#   任何模块只许 `fieldkit.tax_code_of(row)` 取，不得再写第二份字面量。
TAX_CODE_KEYS: Tuple[str, ...] = (
    "tax_code", "税收编码", "税收分类编码", "商品和服务税收分类编码",
    "商品编码", "货物税收编码",
)
UNIT_KEYS: Tuple[str, ...] = ("unit", "计量单位", "uom")
BIZ_TYPE_KEYS: Tuple[str, ...] = ("biz_type", "业务类型", "业务类别")

# ── 备注 / 项目标识（2026-10-02 新增：成本与费用区分的「直接相关性」判据要用）──
#  背景（用户给出的判定原则）：区分主营业务成本与期间费用的**核心判据不是发票品名，
#  而是"这笔支出是否直接服务于某个项目/客户、与该项目收入形成直接配比"。
#  同一张「技术服务费」：为客户定制项目支付 ⇒ 主营业务成本；内部 IT 维护 ⇒ 管理费用。
#  这条判据要有证据才成立，票面上可承载它的就是**备注栏**与**项目编号/合同号**字段
#  （发票备注常写"XX项目""合同号 XX"）。此处与其它字段一样收敛为唯一别名表，
#  各模块只许 `fieldkit.project_of(row)` / `remark_of(row)` 取，不得自写键名。
REMARK_KEYS: Tuple[str, ...] = (
    "remark", "备注", "备注栏", "发票备注", "remarks", "note", "摘要",
)
PROJECT_KEYS: Tuple[str, ...] = (
    "project", "project_name", "项目名称", "项目", "项目编号", "project_no",
    "合同号", "contract_no", "合同编号",
)

# ── 工资/社保人员行字段（2026-10-01 补充：原 detector 与「证据行」各写一份键表）──
# 事故：pipeline._enrich_evidence_rows._salary_row 读 姓名/部门/实发金额/period，
# 而工资表实际行结构是 {name, salary, net, gross, period_start, period_end, ...}
# （实测 12 张工资表 55 行：旧键表**一行都读不到金额**，证据行金额恒 0.00 元、
# 部门与日期恒空 —— 读者看到"这几个人 0 元"，是**假证据**，不是真没发工资）。
PERSON_NAME_KEYS: Tuple[str, ...] = (
    "name", "employee_name", "姓名", "员工姓名", "职工姓名", "人员姓名",
)
# 顺序＝取值优先级；0 元就是 0 元，不得因"0 是假值"继续往后取（旧实现用 `or` 链会跳过 0）
SALARY_PAY_KEYS: Tuple[str, ...] = (
    "salary", "wage", "应发", "gross", "net", "实发", "实发金额", "实发工资", "amount",
)
SALARY_DEPT_KEYS: Tuple[str, ...] = ("部门", "dept", "department", "所属部门")

# 表头/合计行等非人员文本（唯一维护处）
NOISE_PERSON_NAMES = {
    "合计", "小计", "总计", "姓名", "人员", "职工姓名", "员工姓名", "序号", "本月合计",
    "本年累计", "平均", "人数", "单位", "部门", "备注", "说明", "员工", "职工",
    "合计金额", "本页合计", "累计", "总人数", "应发合计", "实发合计", "个人合计",
    "单位合计", "缴费基数合计", "小写", "大写", "社保", "公积金",
}


def _txt(row: Any, keys: Sequence[str]) -> str:
    """按别名顺序取第一个非空值并转成去空白字符串。"""
    if not isinstance(row, dict):
        return ""
    for k in keys:
        v = row.get(k)
        if v in (None, ""):
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


# ── 字段读取 ────────────────────────────────────────────────────────────────
def buyer_name(inv: Any) -> str:
    """购方名称（兼容各导出模板别名）。"""
    return _txt(inv, BUYER_KEYS)


def seller_name(inv: Any) -> str:
    """销方名称（兼容各导出模板别名）。"""
    return _txt(inv, SELLER_KEYS)


def goods_name(inv: Any) -> str:
    """货物/应税劳务名称（兼容各导出模板别名）。"""
    return _txt(inv, GOODS_KEYS)


def invoice_type(inv: Any) -> str:
    """发票类型（如"电子发票(普通发票)"/"增值税专用发票"）。"""
    return _txt(inv, INV_TYPE_KEYS)


def tax_code_of(inv: Any) -> str:
    """商品和服务税收分类编码（简称"税收编码"）。

    ★ 唯一权威：真实数据里这个键叫 **tax_code**（`main._parse_invoice_sheet` 的映射产物），
      中文别名一并兼容；历史代码里写成「税收分类编码」的写法**取不到值**（死判据）。
    """
    return _txt(inv, TAX_CODE_KEYS)


def unit_of(inv: Any) -> str:
    """计量单位（货物/服务的硬证据：件吨千克台… ⇒ 货物；次月小时项… ⇒ 服务）。"""
    return _txt(inv, UNIT_KEYS)


def remark_of(inv: Any) -> str:
    """发票备注栏原文。**

    ★ 2026-10-02：备注是「直接相关性」判据的**证据来源**之一（常写"XX项目""合同号 XX"），
      此前全库没有统一入口 ⇒ 各模块即使想用也无从取值。
    """
    return _txt(inv, REMARK_KEYS)


def project_of(inv: Any) -> str:
    """项目/合同标识（项目名称、项目编号、合同号）。**

    取不到就返回空串 —— **空表示"没有项目归属证据"，不得用空值去推断归属**；
    有值时说明这张票能直接对应到某个项目/合同，是「与收入直接配比」的硬证据。
    """
    return _txt(inv, PROJECT_KEYS)


def biz_type_of(inv: Any) -> str:
    """业务类型（开票软件导出的业务口径，如「库存商品_饲料」/「销售费用_运杂费」）。"""
    return _txt(inv, BIZ_TYPE_KEYS)


def invoice_status(inv: Any) -> str:
    """发票状态（如"正常"/"作废"/"红冲"）。"""
    return _txt(inv, STATUS_KEYS)


def account_name(voucher: Any) -> str:
    """记账凭证的**科目名称**（如「主营业务收入/服务收入」）。

    ★ 2026-10-03：改为只认**名称类**字段（`ACCOUNT_NAME_KEYS`），不再回退到 `account`
    —— 真实凭证里 `account` 是科目编码（"600102"），回退会让所有"科目名含某关键词"
    的判据恒不成立（实测把 6,636,800.57 元主营业务收入读成 0.00）。
    需要编码请用 `account_code()`。
    """
    return _txt(voucher, ACCOUNT_NAME_KEYS)


def account_code(voucher: Any) -> str:
    """记账凭证的**科目编码**（如「600102」）。"""
    return _txt(voucher, ACCOUNT_CODE_KEYS)


def account_text(voucher: Any) -> str:
    """科目**名称+编码**的合并文本（做"是否属于某类科目"的模糊判定时用）。

    取并集而非二选一：名称给出语义、编码兜住只导了编码的模板。
    ⚠ 刻意**不含摘要** —— 摘要常写"结转主营业务收入"这类字眼，掺进来会让
    "该行科目是不是主营业务收入"的判定串到结转行/本年利润行上。
    """
    seen, out = set(), []
    for p in (account_name(voucher), account_code(voucher)):
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return " ".join(out)


def account_label(voucher: Any) -> str:
    """科目**人读标签**：优先名称，无名称时用编码（报告展示/关键词判定统一用它）。"""
    return account_name(voucher) or account_code(voucher)


# ── 银行流水行文本（唯一维护处；2026-10-03 新增）────────────────────────────
# 事故：这条"把一条流水的可读文本拼起来"的逻辑曾在 `bank_nature._tx_text` 与
# `payment_channel._tx_text` 各写一份（字段清单还不一样）——同一笔流水的"文本"
# 在一个模块里有"备注"、在另一个模块里没有，收款性质判定与结算渠道判定就会分叉。
# 现收敛到此，两个模块只做薄转发。
BANK_TX_TEXT_KEYS: Tuple[str, ...] = (
    "counterparty", "counterparty_name", "对手方", "对方户名", "付款方", "收款方",
    "summary", "摘要", "用途", "purpose", "remark", "备注", "notes", "memo",
    "交易附言", "goods", "货物或应税劳务名称",
)


def bank_tx_text(row: Any) -> str:
    """一条银行流水的可读文本（对手方 + 摘要 + 用途 + 备注 + 附言）。"""
    if not isinstance(row, dict):
        return ""
    return " ".join(str(row.get(k)) for k in BANK_TX_TEXT_KEYS if row.get(k) not in (None, ""))


def person_name(row: Any) -> str:
    """人员姓名（工资名册/社保清单/人员档案统一）。"""
    return _txt(row, PERSON_NAME_KEYS)


def salary_pay(row: Any) -> float:
    """工资金额（应发/实发都要能取到）；取不到返回 0。

    ★ 2026-10-01：旧实现用 `row.get("salary") or row.get("wage") or ...` 串，
      `0` 会被当成假值继续往后取 —— 0 元工资会被读成下一个别名的金额，
      属于"静默漂移"。现改为按别名顺序取第一个**键存在**的值（0 就返回 0）。
    """
    if not isinstance(row, dict):
        return 0.0
    for k in SALARY_PAY_KEYS:
        if k not in row:
            continue
        try:
            return float(_num(row, (k,)))
        except Exception:  # noqa: BLE001  # 值非数值时继续下一个别名
            continue
    return 0.0


def salary_dept(row: Any) -> str:
    """工资/人员记录所属部门。"""
    return _txt(row, SALARY_DEPT_KEYS)


def tax_category(goods: Any) -> str:
    """取金税发票品名里的税收分类（`*类别*` 内文字）。

    `*广告服务*广告发布费` → `广告服务`；无 `*类别*` 标记时返回空串。
    """
    m = re.search(r"\*([^*]+)\*", str(goods or ""))
    return m.group(1).strip() if m else ""


# ── 语义判定 ────────────────────────────────────────────────────────────────
_TRUEISH = {"1", "true", "y", "yes", "是", "作废", "红冲", "红字", "负数"}
_VOID_RED_WORDS = ("作废", "红冲", "红字", "负数")


def is_void_or_red(inv: Any) -> bool:
    """判断发票是否为**作废/红冲**（F2：取并集，任一线索成立即为真）。

    合并前两套判据的不一致正是这里要消除的：
      · 只看发票类型字样（漏判 status/is_void/is_red/负数金额）
      · 只看 status/标志/金额（漏判类型字段里写"红冲"的情形）
    并集后可覆盖：类型字样、状态字段、`is_void`/`is_red` 标志、以及**金额为负**。
    """
    if not isinstance(inv, dict):
        return False
    # ① 发票类型 / 状态字段里的字样
    for field in (invoice_type(inv), invoice_status(inv)):
        if any(w in field for w in _VOID_RED_WORDS):
            return True
    # ② 显式布尔标志
    for k in ("is_void", "is_red", "is_negative", "作废", "红冲"):
        v = str(inv.get(k) if inv.get(k) is not None else "").strip().lower()
        if v in _TRUEISH:
            return True
    # ③ 金额为负（红冲发票常以负数体现）
    from engine.numparse import to_number
    for k in ("amount", "金额", "total", "价税合计", "total_amount"):
        if inv.get(k) not in (None, "") and to_number(inv.get(k)) < 0:
            return True
    return False


def row_period(row: Any) -> str:
    """从工资/社保记录提取所属月份，返回 `YYYY-MM`；取不到返回空串。

    工资表/社保表每行自带费款所属期 —— 这是「按月份分析」的唯一可靠依据。
    **逐行聚合而忽略月份，会把「同一人 12 个月的记录」误算成「12 名员工」**
    （实测把 6 名员工报成「51 名员工工资高度均一」）。凡涉及工资/社保的人员统计与
    均额判定，必须先按 (姓名, 月份) 归位。

    ★ 2026-09-25 收敛：`YYYY-MM` 解析唯一权威是 `findingkit.normalize_month`
    （本函数只负责"按别名表找第一个能解析出月份的字段"）。
    """
    from engine.findingkit import normalize_month
    if not isinstance(row, dict):
        return ""
    for k in PERIOD_KEYS:
        v = str(row.get(k) or "").strip()
        if not v:
            continue
        m = normalize_month(v)
        if m:
            return m
    return ""


def is_noise_name(name: Any) -> bool:
    """判断名称是否为表头/合计行等非人员文本（非真实员工姓名）。"""
    n = str(name or "").strip()
    if not n:
        return True
    n_compact = n.replace(" ", "").replace("\u3000", "")
    if n in NOISE_PERSON_NAMES:
        return True
    if n_compact in {x.replace(" ", "") for x in NOISE_PERSON_NAMES}:
        return True
    # 纯数字（序号行）视为噪声
    return bool(n_compact) and n_compact.isdigit()


# ── 发票金额 / 税额 / 价税合计 / 票号（F1：别名集中在此，禁止各检测器自写）──
_AMOUNT_KEYS = ("amount", "金额", "je", "amount_excl_tax", "不含税金额", "金额(元)")
_TAX_KEYS = ("tax", "税额", "se", "tax_amount")
_TOTAL_KEYS = ("total", "价税合计", "jshj", "amount_with_tax", "价税合计金额", "金额合计")
_INV_NO_KEYS = ("invoice_no", "发票号码", "inv_no", "发票号", "number", "invoice_number")


def _num(row: Any, keys: Sequence[str]) -> float:
    """按别名顺序取第一个非空值并转数值（统一数值解析）。缺字段返回 0.0。"""
    from engine.numparse import to_number
    if not isinstance(row, dict):
        return 0.0
    for k in keys:
        v = row.get(k)
        if v in (None, ""):
            continue
        return to_number(v)
    return 0.0


def amount(inv: Any) -> float:
    """发票「金额」（不含税）。"""
    return _num(inv, _AMOUNT_KEYS)


def tax(inv: Any) -> float:
    """发票「税额」。"""
    return _num(inv, _TAX_KEYS)


def total(inv: Any) -> float:
    """发票「价税合计」。"""
    return _num(inv, _TOTAL_KEYS)


def invoice_no(inv: Any) -> str:
    """发票号码。"""
    return _txt(inv, _INV_NO_KEYS)


# ── 对手方「是否自然人」（2026-10-02：私户/个人账户类主题的证据行过滤要用）────────
# 背景（用户质疑）：疑点「公私混同发薪/私户支付薪酬」的明细表里混进了**公司主体**的记录
#   （上海蕴世广告传媒有限公司 1,611,200.00 服务费收入、沙暴文化传播 419,154.26 收入…）——
#   那是"客户付给公司"的对公流水，与"私户发薪"毫无关系。
#   根因：抓行只按"文本含银行/流水"就取**金额最大**的几笔，从不看这一笔到底相不相关。
#   修法：当本项主题是"个人账户/私户/六员/公私混同"时，只取**对手方为自然人**的行。
_ORG_SUFFIXES = (
    "公司", "集团", "厂", "厂区", "店", "门市部", "中心", "事务所", "工作室", "协会",
    "商会", "基金会", "医院", "学校", "大学", "学院", "研究院", "研究所", "银行",
    "合作社", "农场", "基地", "企业", "商行", "商贸", "超市", "商场", "酒店", "宾馆",
    "餐厅", "饭店", "酒楼", "物流", "运输", "快递", "分公司", "办事处", "管委会",
    "政府", "局", "站", "馆", "社", "行", "部", "所",
)


def looks_like_person(name: Any) -> bool:
    """对手方名称是否像**自然人**（用于"个人账户/私户"主题的证据行过滤）。**

    判据（宁缺勿错，避免误伤机构）：先排除机构后缀（命中即非自然人）；再看长度 ——
    中文姓名一般 2~4 字（复姓+名至多 5）。取不到名称/无法判断时返回 False
    （**不臆测**：判不出就不当作个人，宁可少列也不把机构当个人）。
    """
    t = str(name or "").strip()
    if not t:
        return False
    for s in _ORG_SUFFIXES:
        if s and t.endswith(s):
            return False
    # 括号/空格等噪声先去掉再判长度
    import re as _re_p
    core = _re_p.sub(r"[（(][^）)]*[）)]|[\s·、,，.。\-_—]", "", t)
    if not core:
        return False
    if len(core) <= 5 and _re_p.fullmatch(r"[\u4e00-\u9fa5]{2,5}", core):
        return True
    return False


#: 企业法人组织形式后缀（用户质疑的"公司主体"就是这些）
_ENTERPRISE_SUFFIXES = (
    "有限公司", "有限责任公司", "股份有限公司", "股份公司", "公司", "集团",
    "总公司", "分公司", "子公司", "合伙企业", "有限合伙", "外资企业",
)
#: 银行流水"对手方"字段里的**非名称脏值**（摘要/业务术语误入，不是交易对手）
_NON_NAME_TOKENS = (
    "汇出", "汇入", "汇款", "结算", "批量", "转账", "转出", "转入", "代发", "代付",
    "扣款", "划转", "退款", "退汇", "手续费", "利息", "结息", "工资", "报销",
    "备用金", "往来", "清算", "轧差", "银行", "银联", "支付", "收款", "付款",
)


def looks_like_enterprise(name: Any) -> bool:
    """是否**企业法人**（含"公司/集团/合伙企业"等组织形式后缀）。

    与 `looks_like_person` 的分工：本判据用于"个人账户/私户"类主题的证据行过滤 ——
    要剔除的是用户点名的那类**公司主体**（上海蕴世广告传媒有限公司…），
    而**工作室/协会/个体户**是该类检测的真实对象（经营者个人账户），不在剔除之列。
    """
    t = str(name or "").strip()
    if not t:
        return False
    return any(t.endswith(s) for s in _ENTERPRISE_SUFFIXES)


def is_noise_counterparty(name: Any) -> bool:
    """对手方字段是否是**脏值**（银行摘要/业务术语误入，不是真正的交易对手名）。

    实测：`支付结算批量汇出汇款` 被当成交易对手名列出 —— 读者会以为那是一家单位。
    """
    t = str(name or "").strip()
    if not t:
        return False
    _kw = sum(1 for k in _NON_NAME_TOKENS if k in t)
    if _kw >= 2:
        return True
    return any(t.endswith(k) for k in ("汇出汇款", "批量汇出", "结算款项"))
