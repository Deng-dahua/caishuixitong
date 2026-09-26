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
    "所属月份", "账期", "缴费所属期", "税款所属期", "所属期间",
)
ACCOUNT_KEYS: Tuple[str, ...] = (
    "account", "科目", "科目名称", "会计科目", "acct", "account_name",
)

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


def invoice_status(inv: Any) -> str:
    """发票状态（如"正常"/"作废"/"红冲"）。"""
    return _txt(inv, STATUS_KEYS)


def account_name(voucher: Any) -> str:
    """记账凭证的科目名称。"""
    return _txt(voucher, ACCOUNT_KEYS)


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
