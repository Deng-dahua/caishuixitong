# -*- coding: utf-8 -*-
"""用工缴费（社保 / 住房公积金）**法定参数**唯一权威（2026-10-03）

═══════════════════════════════════════════════════════════════════════════════
为什么需要这一层
═══════════════════════════════════════════════════════════════════════════════
"缴存基数是否低于实际工资"这类判断需要**法定下限**做基准。此前这些数字（如社保低基数的
0.6）散在 `domain_analysis` 的判据里就地硬编码，新增一类（公积金）时只能再抄一份 ——
正是"同一概念、多条链路各判一次"的复发土壤。

本模块只做一件事：把**引用法定口径**的参数集中登记。判据代码里只许引用这里的名字，
不得再出现裸数字；新增一个缴费项目（如工会经费）只需在本表加一行。

═══════════════════════════════════════════════════════════════════════════════
口径说明（写进报告时必须保留）
═══════════════════════════════════════════════════════════════════════════════
· `HF_MIN_RATIO` —— 《住房公积金管理条例》第十八条：职工和单位住房公积金的缴存比例
  **均不得低于职工上一年度月平均工资的 5%**。据此可做**单向反推**：
      个人月缴存额 ＝ 缴存基数 × 个人缴存比例 ，且 个人缴存比例 ≥ 5%
   ⇒ 缴存基数 ＝ 个人月缴存额 ÷ 个人缴存比例 ≤ 个人月缴存额 ÷ 5%
   ⇒ 若「个人月缴存额 < 实际工资 × 5%」，则**缴存基数必然低于实际工资**（可证伪的硬结论）。
  反向不成立：缴存额占工资 ≥5% 时不能据此排除低基数（比例可能是 12%，基数仍可能偏低），
  故对照 <5% 之外的记录**不产出**结论（宁缺勿错）。
· `SS_BASE_LOW_RATIO` —— 社保缴费基数低于实际工资 60% 视为低基数参保（沿用既有判据，
  60% 为多数地区社保缴费基数下限与社会平均工资的关系口径）。
· `HF_UNIT_PERSONAL_EQUAL` —— 单位与个人缴存比例通常相同（1:1），但**并非法定必然**，
  故仅用于"口径提示"，**不得**用它把个人缴存额乘 2 当作账载应记金额（那会造出差额）。
"""

from __future__ import annotations

#: 住房公积金缴存比例法定下限（《住房公积金管理条例》第十八条）
HF_MIN_RATIO: float = 0.05
#: 社保缴费基数低于实际工资的判定比例（低于 60% 视为低基数参保）
SS_BASE_LOW_RATIO: float = 0.60
#: 单位与个人公积金缴存比例通常相同（仅作口径提示，不作换算依据）
HF_UNIT_PERSONAL_EQUAL: bool = True

#: 引用依据（报告/法条文字统一取自此处，避免各处自写导致口径不一）
HF_MIN_RATIO_BASIS: str = ("《住房公积金管理条例》第十八条：职工和单位住房公积金的"
                           "缴存比例均不得低于职工上一年度月平均工资的 5%")
SS_BASE_LOW_RATIO_BASIS: str = ("《社会保险法》第十二条、第三十五条：用人单位以本单位职工"
                                "工资总额、职工以本人上年度月平均工资为缴费基数")


# ── 口径判定（唯一权威）：明细列的是"个人缴存部分"还是"单位+个人合计" ───────────
HF_SCOPE_PERSONAL = "personal"      #: 明细只列个人缴存部分
HF_SCOPE_UNIT_TOTAL = "unit_total"  #: 明细列的是单位+个人合计（或单位部分）
HF_SCOPE_UNKNOWN = "unknown"        #: 无从判定（不得臆测）

_HF_SCOPE_ZH = {
    HF_SCOPE_PERSONAL: "个人缴存部分",
    HF_SCOPE_UNIT_TOTAL: "单位与个人合计（或单位部分）",
    HF_SCOPE_UNKNOWN: "无从判定（明细未标明单位/个人口径）",
}


def hf_detail_scope(detail_total: float, salary_hf_deduct_total: float,
                    *, tol: float = 0.02) -> str:
    """判定公积金明细表的金额口径。

    **唯一权威判据**：与工资表的「公积金个人扣缴额」比对 —— 两者都是**个人实际扣缴数**。
      相等 ⇒ 明细列的是个人缴存部分（`personal`）；
      不等 ⇒ 明细列的不是个人部分（`unit_total`）；
      任一为 0/缺 ⇒ `unknown`（**不臆测**）。

    ★ 为什么要它：账簿"住房公积金"科目记的是**单位+个人**（个人部分属代扣，通常另走
      应付职工薪酬）。若拿只含**个人**部分的明细去和科目总额对等，会凭空得到
      「差一个单位部分」的假差额（实测 1,200 vs 2,400），进而被读成"少缴/未全员缴存"。
    """
    try:
        d = float(detail_total or 0.0)
        s = float(salary_hf_deduct_total or 0.0)
    except (TypeError, ValueError):
        return HF_SCOPE_UNKNOWN
    if d <= 0 or s <= 0:
        return HF_SCOPE_UNKNOWN
    return HF_SCOPE_PERSONAL if abs(d - s) <= max(1.0, tol * s) else HF_SCOPE_UNIT_TOTAL


def hf_scope_zh(scope: str) -> str:
    """口径常量 → 报告用语。"""
    return _HF_SCOPE_ZH.get(str(scope or ""), _HF_SCOPE_ZH[HF_SCOPE_UNKNOWN])


def hf_detail_scope_pairs(pairs, *, tol: float = 0.02, majority: float = 0.8) -> str:
    """按 **(人, 月) 配对**判定口径（比总额比对可靠）。

    参数：`pairs` = [(公积金明细额, 工资表公积金个人扣缴额), ...]，只放两边都有的配对。

    ★ 为什么不能只比总额（实测教训）：公司1 的公积金明细覆盖 11 个月、工资表只有 5 个月，
      总额 17,700 vs 15,900（比值 1.11）落在"既不等于个人、也不等于 2 倍"的灰区，
      总额法判成"非个人口径"⇒ 金额勾稽照样执行 ⇒ 又产出 9 条口径差疑点。
      按配对比对则清楚：两边的每一个人月都是 300 vs 300 ⇒ 明细列的确实是**个人部分**。
    """
    same = doubled = other = 0
    for d, s in (pairs or []):
        try:
            d = float(d or 0.0)
            s = float(s or 0.0)
        except (TypeError, ValueError):
            continue
        if d <= 0 or s <= 0:
            continue
        if abs(d - s) <= max(1.0, tol * s):
            same += 1
        elif abs(d - 2.0 * s) <= max(1.0, tol * 2.0 * s):
            doubled += 1
        else:
            other += 1
    tot = same + doubled + other
    if tot == 0:
        return HF_SCOPE_UNKNOWN
    if same / tot >= majority:
        return HF_SCOPE_PERSONAL
    if doubled / tot >= majority:
        return HF_SCOPE_UNIT_TOTAL
    return HF_SCOPE_UNKNOWN


# ── 公积金明细的**字段名**（唯一权威）─────────────────────────────────────────
# ★ 2026-10-03 根因：公积金明细经通用表格解析后，月份落在 `counterparty` 这个**合成列名**上
#   （形如 `{"person_name":"徐瑶","id_number":"...","counterparty":"2025-01","amount_col":"300"}`）。
#   `fieldkit.row_period` 的别名表里没有 `counterparty`（它通常是**对手方名称**，不能全局登记），
#   于是公积金行全部落到"未标注月份"，与工资表的 `2025-01` 对不上 ⇒ 差集把**全员全额**
#   报成「有工资无公积金」（实测 6 人 55 组，实际只有 1 人 2 组）。
#   而 `monthly_reconcile._fund_series` 自己另写了一份 `("counterparty", "缴存月份", ...)` ——
#   同一份材料的字段名，两条链路各读一次、且只有一条读对。现收敛到本表。
HF_MONTH_KEYS: tuple = ("counterparty", "缴存月份", "所属期", "所属月份", "月份", "month",
                        "period", "period_start", "账期", "记账月份")
HF_PERSON_KEYS: tuple = ("person_name", "name", "职工姓名", "姓名", "员工姓名")
HF_AMOUNT_KEYS: tuple = ("amount_col", "个人缴存额", "personal_amount", "缴存额",
                         "单位缴存额", "total", "amount", "金额")


def _pick(row: dict, keys) -> object:
    for k in keys:
        if k in row and row.get(k) not in (None, ""):
            return row.get(k)
    return None


def hf_month(row: object) -> str:
    """公积金明细行 → `YYYY-MM`（唯一权威；取不到返回空串）。"""
    from engine.findingkit import normalize_month
    if not isinstance(row, dict):
        return ""
    for k in HF_MONTH_KEYS:
        v = str(row.get(k) or "").strip()
        if not v:
            continue
        m = normalize_month(v)
        if m:
            return m
    return ""


def hf_person(row: object) -> str:
    """公积金明细行 → 人员姓名（唯一权威）。"""
    return str(_pick(row, HF_PERSON_KEYS) or "").strip()


def hf_amount(row: object) -> float:
    """公积金明细行 → 缴存额（唯一权威；口径由 `hf_detail_scope` 判定）。"""
    from engine.numparse import to_number
    return to_number(_pick(row, HF_AMOUNT_KEYS))


