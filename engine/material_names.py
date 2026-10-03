# -*- coding: utf-8 -*-
"""资料名称的**唯一权威**（两级命名 + 别名归一）（2026-10-03）

═══════════════════════════════════════════════════════════════════════════════
为什么必须建立这一层（根因："同一份材料，多种叫法"）
═══════════════════════════════════════════════════════════════════════════════
系统里"资料名"曾散落在 **8 处**各自维护：
  `required_materials`（红线）｜`evidence_chain[].name`（证据角色）｜`constituent_sources`（要件数据源）
  ｜`material_recognition._SUPP_ENTRIES`（115 条识别登记）｜`evidence_chain._MATERIAL_KEYWORDS`
  ｜`evidence_chain._MATERIAL_SYNONYMS`｜`evidence_chain._EQUIVALENT_CATEGORIES`
  ｜`analysis_coverage._MATERIAL_SUPERCLASS`（15 类超类表）

后果（实测，用户反复报）：
  · 要件表说「独立数据源：银行流水｜**已有**」，同一页证据表说「完整资金链条流水｜**待核实**」
    —— 同一份材料，两处名字不同、两套判定 → **同页自相矛盾**；
  · 「本项检查需要4项材料，目前还没有一项材料与要求逐字对应」，而正文正在引用这些材料的数字。

**真正的结构性原因**：系统只有 **14 个"材料类别"**（与"企业已提供清单"同源：银行流水/进项发票/…），
而红线要求的常是**更细的具体材料**（"完整资金链条流水"、"采购合同与入库验收单"）。两个层级
被混在一起做**逐字字符串比较**，细名永远匹配不上类别名 ⇒ 系统性判「缺失」。

═══════════════════════════════════════════════════════════════════════════════
本模块的契约
═══════════════════════════════════════════════════════════════════════════════
N1 **两级命名**：
   · **类别层 `CATEGORY_KEYWORDS`**（14 类）——与"企业已提供资料清单"同一套名字；
     用于回答「这类资料**有没有**」。
   · **具体材料层**（红线 `evidence_chain[].name`）——回答「本项要求**哪份**证据」；
     每份具体材料都必须能**归到某个类别**（`categories_of`），否则视为登记缺口。
N2 **判定只认类别**：齐备性（已有/待核/缺失）按**类别**判定；具体材料名不再参与字符串比较
   —— 从根上消除"同一份材料两套判定"。范围差异（如"须覆盖全部银行账户及个人账户"）
   写进说明，不改变"该类别已提供"这一事实。
N3 **别名只收"同一实物"**：`CATEGORY_ALIASES` 仅登记同一份材料的另一种叫法，
   **不得**放宽到"相关/相近"（"拒收证明"这类不同实物刻意不登记）。
N4 **单一来源**：本表是唯一维护处；`evidence_chain` 等模块只许引用，不得再抄一份。
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence

# ── N1 类别层：类别 → 识别关键词（与"已提供资料清单"同源）─────────────────────
CATEGORY_KEYWORDS: List[List[str]] = [
    ["银行流水", ["流水", "付款", "收款", "资金", "转账", "代付", "支付", "回单"]],
    ["销项发票", ["销项", "开票", "销售发票"]],
    ["进项发票", ["进项", "采购发票"]],
    ["记账凭证", ["凭证", "记账", "会计分录", "账簿"]],
    ["工资表", ["工资", "薪酬"]],
    # ★ 2026-10-03：住房公积金缴存明细与社保明细同属"用工缴费凭证"一个类别
    #   （`enterprise_report` 早已把 housing_fund 归到"社保明细"类）。
    #   此前关键词里没有"公积金"，导致红线的"住房公积金缴存明细"**判不出类别**，
    #   要件②在报告里永远显示"未单独核对（独立数据源本轮未取得）"——不是没资料，是归不了类。
    ["社保明细", ["社保", "参保", "缴费基数", "公积金"]],
    ["进销存台账", ["入库", "出库", "库存", "盘点", "台账", "存货", "领料", "完工", "发货"]],
    ["合同文件", ["合同", "协议", "订单"]],
    ["科目余额表", ["科目", "余额", "明细账", "往来", "挂账", "辅助账"]],
    ["增值税申报表", ["增值税", "纳税申报"]],
    ["企业所得税申报表", ["所得税", "汇算"]],
    ["个税申报表", ["个税", "扣缴"]],
    ["资产负债表", ["资产", "负债", "报表"]],
    ["利润表", ["利润", "毛利", "费用", "成本", "报表"]],
]

# ── N3 别名层：同一份材料的另一种叫法（仅限**同一实物**）──────────────────────
CATEGORY_ALIASES: Dict[str, List[str]] = {
    "银行流水": ["银行对账单", "银行明细", "资金流水", "流水单",
                 "收汇水单", "收银或平台结算单",
                 # ★ 2026-10-03：红线的"证据角色名"常把**范围**写进名字里，
                 #   如"完整资金链条流水"＝银行流水（要求覆盖全部账户），本质是同一份材料；
                 #   范围差异由 `scope` 说明承载，不再靠"名字不一样"表达（那会被判缺失）。
                 "完整资金链条流水", "银行账户流水", "全部银行账户及个人账户流水"],
    "工资表": ["工资名册", "工资清单", "工资花名册", "薪酬表"],
    "社保明细": ["社保参保明细", "参保缴费明细", "参保缴费记录", "社保清单", "社保缴费明细",
                 # ★ 2026-10-03：公积金"缴存明细"与社保"缴费明细"是同一实物（逐人逐月的缴费记录），
                 #   故登记为同一类别；**「缴存登记回执」刻意不登记**——那是"已办理登记"的证明，
                 #   与"缴费明细"不是同一实物，混登记会让"提供了社保明细"冒充"已提交登记回执"。
                 "住房公积金缴存明细", "住房公积金明细", "公积金缴存明细", "公积金明细",
                 "公积金汇缴书", "住房公积金汇缴书"],
    "科目余额表": ["余额表", "应付账款明细"],
    "增值税申报表": ["增值税纳税申报表"],
    "销项发票": ["建安发票", "出口发票"],
    "进项发票": ["采购发票明细"],
    # ★ 2026-10-03：合同类细名归位。**只登记"确属同一实物"的名字**——
    #   复合要求（"采购合同与入库验收单"）不整串登记，靠 `categories_of` 拆词归位；
    #   反证材料（"退款协议""客户书面说明"）**不登记**：那是企业须主动提交的特定说明，
    #   "已提供合同文件类别"不等于"已提交该说明"（否则反证被当成已获取，直接错排风险）。
    "合同文件": ["采购合同", "销售合同", "劳务合同", "借款合同",
                 "合同台账与全部应税凭证", "采购合同与验收单"],
    "进销存台账": ["投料单", "在建工程领用或研发领用记录", "退货单",
                   "入库验收单", "入库单", "出库单", "出库单与发货记录", "验收单",
                   "存货明细账与期末盘点表", "存货盘点表", "出入库台账"],
    "企业所得税申报表": ["A106000弥补亏损明细表"],
    "个税申报表": ["个税申报记录（工资薪金或股息红利）"],
    # 账内凭证类（报销单据/辅助凭证属记账凭证）
    "记账凭证": ["会计凭证", "费用报销单据与业务凭证"],
    # ⚠ 刻意**不登记**（不同实物，硬映射＝冒充实得）：
    #   「物流单据」「承运记录」——是发货/承运证据，不是库存台账；
    #   「个人卡资金用途凭证」——是资金用途证明，与账内凭证不同实物；
    #   「完税凭证」「纳税凭证」——是缴税证明，与申报表不同实物；
    #   「拒收证明」——折让/退货的事由说明，与任何既存类别都不是同一实物。
}

#: 类别规范名（供外部判断"这个名字是不是类别名"）
CATEGORIES: List[str] = [c for c, _ in CATEGORY_KEYWORDS]

_SPLIT = re.compile(r"[、，,；;／/\s]+|与|和|及|以及|或")


def _alias_index() -> Dict[str, str]:
    """别名 → 类别（含类别名自映射）。同一别名指向多个类别时**以先声明者为准**，
    并由闸门 `check_material_alias_single_source` 报错（不允许一物多类别）。"""
    idx: Dict[str, str] = {}
    for cat in CATEGORIES:
        idx.setdefault(cat, cat)
    for cat, alts in CATEGORY_ALIASES.items():
        if cat not in CATEGORIES:
            continue
        for a in alts:
            idx.setdefault(str(a), cat)
    return idx


def canonical(name: Any) -> Optional[str]:
    """任意叫法 → **类别规范名**。判不出返回 None（**不臆测**）。"""
    t = str(name or "").strip()
    if not t:
        return None
    idx = _alias_index()
    if t in idx:
        return idx[t]
    # 去掉常见尾缀再做一次（"…明细/…清单/…记录/…台账/…资料"）
    for suf in ("明细表", "明细", "清单", "记录", "资料", "文件", "证明", "台账", "表"):
        if t.endswith(suf) and len(t) > len(suf):
            core = t[: -len(suf)]
            if core in idx:
                return idx[core]
            for k, v in idx.items():
                if len(k) >= 2 and k in core:
                    return v
    # 最后按类别关键词做**最长命中**（与资料识别口径一致）
    best: Optional[str] = None
    best_len = 0
    for cat, kws in CATEGORY_KEYWORDS:
        for kw in kws:
            if kw in t and len(kw) > best_len:
                best, best_len = cat, len(kw)
    return best


def category_strict(name: Any) -> Optional[str]:
    """**严格口径**：只认"确属同一实物"的登记（别名表 / 类别名本身），判不出返回 None。

    与 `canonical()` 的分工（★ 2026-10-03）：
      · `canonical()`  —— **展示/归类**用，允许按关键词兜底（"采购合同"→合同文件）；
      · `category_strict()` —— **齐备性判定**用，**绝不兜底**：反证材料
        （"退款协议""客户全部为需票企业的书面说明与合同"）刻意未登记别名，就必须判不出，
        否则"已提供合同文件类别"会被当成"已提交该反证说明"，直接错排风险。
    """
    t = str(name or "").strip()
    if not t:
        return None
    return _alias_index().get(t)


def strict_categories_of(text: Any) -> List[str]:
    """严格口径的拆分归类（只认登记别名；未登记的段不兜底）。"""
    t = str(text or "").strip()
    if not t:
        return []
    out: List[str] = []
    one = category_strict(t)
    if one:
        out.append(one)
    for part in _SPLIT.split(t):
        p = part.strip()
        if len(p) < 2:
            continue
        c = category_strict(p)
        if c and c not in out:
            out.append(c)
    return out


#: 「且」分隔（要件数据源里 A、B ＝ 两样都要）
_AND_SPLIT = re.compile(r"[、，,；;／/\s]+|与|和|及|以及")
#: 「或」分隔（A或B ＝ 其一即可，与 `evidence_chain._material_requirements` 同一契约）
_ALT_SPLIT = re.compile(r"或(?:者)?")


def strict_category_groups(text: Any) -> Optional[List[List[List[str]]]]:
    """把要件数据源解析为「且」组，每组内是「或」候选的类别集合。

    例：`住房公积金缴存明细、工资表、社保参保明细` → [[['社保明细']], [['工资表']], [['社保明细']]]
        `工资表或个税申报表`                     → [[['工资表'], ['个税申报表']]]
        `缴存登记回执、劳动合同、住房公积金缴存明细` → None（有段落判不出类别）

    返回 None 表示**有任一段落无法归类** ⇒ 调用方必须退回逐字判定，不得静默丢弃。

    ★★ 2026-10-03（用户质询疑点23「要件①为何永远『未单独核对』」）：
      要件① 写的是「存在劳动用工关系（工资表**或**个税申报有人员）」，
      而数据源声明「劳动合同、工资表」用的是「、」。旧实现把「或」也当作「且」切分
      （`_SPLIT` 里含「或」）⇒ 要求**两样同时具备**才认「已有」，
      于是只上传工资表的企业，要件① 永远停在「独立数据源本轮未取得」。
      这与 `evidence_chain._material_requirements` 自己写明的契约（「A或B → 两者之一即可」）
      直接冲突 —— 同一份要件，两条链路各判一次，且判法相反。
    """
    t = str(text or "").strip()
    if not t:
        return None
    groups: List[List[List[str]]] = []
    for seg in _AND_SPLIT.split(t):
        seg = str(seg or "").strip()
        if len(seg) < 2:
            continue
        alts: List[List[str]] = []
        for alt in _ALT_SPLIT.split(seg):
            alt = str(alt or "").strip()
            if len(alt) < 2:
                continue
            cats = strict_categories_of(alt)
            if not cats:
                return None          # 有段落判不出 ⇒ 整体失效（不得静默丢弃）
            alts.append(cats)
        if alts:
            groups.append(alts)
    return groups or None


def strict_categories_all(text: Any) -> Optional[List[str]]:
    """严格归类，并要求**全部段落都能归位**。

    返回：所有段落对应的类别（去重保序）；
          **只要有任一段落判不出类别 → 返回 None**（表示"不能靠类别判定"，调用方须回退严格逐字逻辑）。

    ★ 为什么必须这样（实测事故）：`"进项发票与采购台账"` 去掉未登记的"采购台账"后
      只剩下 `["进项发票"]`，若据此判"类别已覆盖"就会把整项判成「已有」——
      而企业只提供了进项发票、采购台账并未提供。**未登记的段落必须让判定失效，不得静默丢弃。**
    """
    t = str(text or "").strip()
    if not t:
        return None
    parts = [p.strip() for p in _SPLIT.split(t) if len(p.strip()) >= 2]
    if not parts:
        one = category_strict(t)
        return [one] if one else None
    out: List[str] = []
    for p in parts:
        c = category_strict(p)
        if not c:
            # 整串或整串里的类别名兜一次（"采购合同与入库验收单"这类已登记整串别名）
            c = category_strict(p) or None
        if not c:
            whole = category_strict(t)
            if whole and len(parts) == 1:
                c = whole
        if not c:
            return None          # 有段落判不出 ⇒ 类别判定失效
        if c not in out:
            out.append(c)
    return out or None


def is_category(name: Any) -> bool:
    """这个名字本身是不是类别规范名。"""
    return str(name or "").strip() in CATEGORIES


def categories_of(text: Any) -> List[str]:
    """一段文字里提到了**哪些资料类别**（去重、保序）。

    例：`"采购合同与入库验收单"` → `["合同文件", "进销存台账"]`
        `"完整资金链条流水"` → `["银行流水"]`
    判不出 → 空列表（调用方须按"未登记"处理，不得默认归到任意类别）。
    """
    t = str(text or "").strip()
    if not t:
        return []
    out: List[str] = []
    # ① 整串先归一（能直接命中的优先）
    whole = canonical(t)
    if whole:
        out.append(whole)
    # ② 再按分隔符切开，逐段归一
    for part in _SPLIT.split(t):
        p = part.strip()
        if len(p) < 2:
            continue
        c = canonical(p)
        if c and c not in out:
            out.append(c)
        elif not c:
            # 段落内可能含类别关键词（如"采购合同"含"合同"）
            for cat, kws in CATEGORY_KEYWORDS:
                if any(kw in p for kw in kws) and cat not in out:
                    out.append(cat)
                    break
    return out


def same_material(a: Any, b: Any) -> bool:
    """两个名字是否**同一份材料**（归一到同一类别即视为同一；都判不出则字符串相等）。"""
    ca, cb = canonical(a), canonical(b)
    if ca and cb:
        return ca == cb
    if ca or cb:
        return False
    return str(a or "").strip() == str(b or "").strip()


def missing_from(required: Sequence[str], available: Sequence[str]) -> List[str]:
    """按**类别**求差集：`required` 中哪些类别在 `available` 里没有。

    返回缺失的**类别名**（不是原始写法），保证报告里的"缺失清单"与"已提供清单"同源。
    """
    have = set()
    for a in (available or []):
        c = category_strict(a) or canonical(a)   # 已提供清单本身是类别名，严格口径即可
        if c:
            have.add(c)
    lack: List[str] = []
    for r in (required or []):
        cats = strict_categories_of(r)          # ★ 判定用严格口径（不兜底）
        if not cats:
            one = category_strict(r)
            cats = [one] if one else []
        for c in cats:
            if c and c not in have and c not in lack:
                lack.append(c)
    return lack


__all__ = [
    "CATEGORY_KEYWORDS",
    "category_strict",
    "strict_categories_of",
    "strict_categories_all",
    "CATEGORY_ALIASES",
    "CATEGORIES",
    "canonical",
    "is_category",
    "categories_of",
    "same_material",
    "missing_from",
]
