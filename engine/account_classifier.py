# -*- coding: utf-8 -*-
"""会计归属判定 —— **主营业务成本 vs 期间费用**的唯一权威（2026-10-02）

═════════════════════════════════════════════════════════════════════════════
存在理由（真实缺陷，非空谈）
═════════════════════════════════════════════════════════════════════════════
「这张进项发票算主营业务成本，还是期间费用」这一判定，此前**散落在 4 处各自实现**，
且四张表的归属互相打架（实测比对）：

  · engine/memory.py:1293             BIZ_EXPENSE_KEYWORDS ─ 8 类经营要素（水电/物业/通信/安保…）
  · engine/domain_analysis.py:7072    _MAJOR_EXPENSE_KWS   ─ 含 咨询/广告/装修/招聘…
  · engine/main_biz_cost.py:92        _MAJOR_EXPENSE_KWS   ─ 同上名，**多**了 运费/装卸/承运/运送
  · engine/pipeline.py:4006           _EXPENSE_KWS         ─ 含 住宿/餐饮/差旅/汽油/停车…

后果（同品名两套结论）：一张「住宿费」发票 —— pipeline 判**费用**（不参与生产物资分析），
`main_biz_cost` 却因为没在它的重大费用表里 → 落到「待核/默认成本」，**虚增成本、压低毛利**。

═════════════════════════════════════════════════════════════════════════════
判定铁律（写死在本模块，全系统不得在别处重写）
═════════════════════════════════════════════════════════════════════════════
L1 **票面没有会计科目字段**。成本/费用是**推断**出来的，不是从票面"读"出来的。
   因此任何判定都必须带 **evidence**（命中了哪一层、哪个词）与 **confidence**。
L2 **第一刀切「是否构成存货/是否资本化」，不切品名**。水电、运输、包装、维修、租赁
   同一个品名，可能落成本也可能落三费，唯一区别是**用途·部门·承担主体**；而用途只有
   回账（合同/项目/验收单）才知道。故本模块对这类词一律 `needs_context=True`。
L3 **三态裁决，禁二态硬判**： 主营业务成本 / 期间费用 / **待核**。
   ★ 判不出来必须落「待核」，**绝不允许默认判成本**（默认判成本=虚增成本、掩盖问题）。
L4 **行业层优先于通用层**（沿用 `audit_consistency.check_cost_industry_basis` 的顺序铁律：
   行业核心投入判定必须排在通用费用关键词之前，否则广告公司的核心成本「广告发布」
   会被通用「广告/推广/发布」费用表截走成期间费用 —— 已发生过的真事故）。
L5 **金额一律取不含税**，进项税额单列（由 `fieldkit` 负责取数，本模块只收已取好的值）。

═════════════════════════════════════════════════════════════════════════════
分层设计（新增同类对象只需在**数据表**加一行，不改这里的逻辑）
═════════════════════════════════════════════════════════════════════════════
  ① 资本/预付/个人硬排除层  → CAPITAL / PREPAID / 不得抵扣
  ② 行业核心投入层（数据驱动，`industry_resolver.core_inputs_for`）  → COST
  ③ 通用成本层（不依赖行业也成立）                                  → COST
  ④ 需上下文层（用途决定归属，无项目上下文即落待核）                → 待核
  ⑤ 通用费用层（明确当期损益）                                      → EXPENSE
  ⑥ 未命中                                                          → 待核
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# ── 三态 + 特殊态（对外 vocab，其他模块只引用这里，不得另立） ────────────────
CLASS_COST = "主营业务成本"
CLASS_EXPENSE = "期间费用"
CLASS_CAPITAL = "资本性支出"
CLASS_UNDETERMINED = "待核"

# 期间费用的明细归属（会计报表口径）
EXPENSE_SUB_SELLING = "销售费用"
EXPENSE_SUB_ADMIN = "管理费用"
EXPENSE_SUB_FINANCE = "财务费用"
EXPENSE_SUB_RD = "研发费用"

# 置信度（低置信 ⇔ 落在待核）
CONF_HIGH = "高"
CONF_MEDIUM = "中"
CONF_LOW = "低"

#: 允许输出的 account_class 全集（闸门 `check_cost_expense_triad` 据它校验）
ALLOWED_CLASSES = (CLASS_COST, CLASS_EXPENSE, CLASS_CAPITAL, CLASS_UNDETERMINED)

#: ★ 2026-10-02 拆分：「需上下文层」原先是**一整张词表 ⇒ 命中即一律落待核**
#   （实测 ④ 层两个分支 `return` 的都是 CLASS_UNDETERMINED，`require_context` 参数形同虚设）
#   ⇒ 本最该被分辨的「运输/装卸/包装/搬运」反倒全都退成「分不出来」。
#   现按**会计事实**拆成两张表，新增同类只需在对应表里加一行、不改分类逻辑：
#     · INVENTORY_SUPPORT_KWS —— 构成**存货采购成本**（企业会计准则第1号——存货 第六条：
#       存货采购成本含购买价款、运输费、装卸费、包装费、挑选整理费…）⇒ 命中即**自动裁决为成本**；
#     · AMBIGUOUS_KWS —— 用途决定归属（生产耗用 vs 办公耗用 / 项目用 vs 管理用），
#       票面 + 结构性证据都判不出 ⇒ **仍落待核**（铁律：判不出不默认成本）。
INVENTORY_SUPPORT_KWS = (
    # 物流类（★ 准则明文：采购成本含运输费、装卸费、包装费…）
    "运输", "运费", "物流", "货运", "配送", "装卸", "搬运", "承运", "运送",
    "仓租", "仓储", "挑选整理",
    # 包装与辅耗（构成存货的直接组成部分）
    # ⚠ 只认「包装材料/包装物/包装袋/包装箱/包装费」等**采购口径**写法：裸词「包装」会命中
    #   「软包装罐头」这类**商品属性**（真实验收：宠物罐头整块被挪去待核）
    "包装材料", "包装物", "包装袋", "包装箱", "包装费", "辅料", "耗材", "试剂",
)

AMBIGUOUS_KWS = (
    # 能源（生产耗用→成本；办公耗用→管理费用；单看品名无法确定）
    "水电", "电费", "水费", "蒸汽", "燃气", "煤炭", "燃油", "汽油", "柴油", "加油",
    # 维护类（车间设备 vs 办公设备）
    "维修", "维护", "保养", "修理", "修缮",
    # 场地（厂房用→成本/制造费用；办公用→管理费用）
    "租赁", "租金", "场地",
    # 服务外购（用途决定：项目外包→成本；管理咨询→管理费用）
    # ⚠ 只留「劳务外包」：裸词「劳务/劳务费」过泛，会把 `*劳务*加工费` 截成费用、
    #   连带让 3 处既有回归测试失败（委托加工费对制造业就是主营业务成本）
    "检测", "化验", "实验", "会议", "会务", "安保", "劳务外包", "分包",
)

#: 兼容旧派生出口（major_expense_keywords 等引用）+ 旧派生出口语义不变量：两张表的并集
NEEDS_CONTEXT_KWS = tuple(INVENTORY_SUPPORT_KWS) + tuple(AMBIGUOUS_KWS)

#: 通用成本层（与行业无关也成立：直接构成存货/服务产出）
GENERAL_COST_KWS = (
    "原材料", "原料", "材料", "五金", "元器件", "零配件", "零部件", "配件",
    "半成品", "产成品", "库存商品", "委托加工费", "加工费", "外协加工",
    "商品", "货物",
)

#: 通用费用层（明确当期损益，无需项目上下文即可判定）
GENERAL_EXPENSE_KWS = (
    # 招待 / 职工福利（业务招待费、职工福利费）
    "住宿", "餐饮", "餐费", "饭费", "招待", "业务招待", "团建", "员工福利", "福利",
    # 办公 / 行政
    "办公用品", "文具", "打印", "复印", "硒鼓", "墨盒", "纸张", "邮递", "快递",
    "通信", "电话", "话费", "短信", "保洁", "清洁", "垃圾",
    # 专业服务（当期损益，除非本行业 core_inputs 覆盖）
    "咨询", "顾问", "律师", "法律", "审计", "评估", "认证", "代理记账", "招聘",
    "猎头", "人力资源", "培训", "广告",
    # 场地与保险（一般企业为管理费用；厂房/设备情形由需上下文层与行业层先判）
    "物业", "物业管理", "物业费", "保险", "社保",
    # 差旅 / 交通（个人报销口径，非存货）
    "差旅", "房费", "过路费", "通行费", "停车", "停车费", "加油卡", "旅游",
    # 财务费用
    "利息", "手续费", "银行手续费",
)

#: ★ 差旅出行层（2026-10-02 新增，**优先于行业核心投入层**）
#  会计事实：员工因公出行的票务与住宿属**期间费用**（管理费用—差旅费），与行业无关 ——
#  广告公司的机票、制造企业的机票，同样都是差旅，**不是**主营业务成本。
#  为什么必须单独成层、且排在行业核心投入之前（实测两处误判就出在这里）：
#    ① 撞词：金税分类「*经纪代理服务*机票款」里含"代理"，而广告传媒的行业核心投入里
#       登记过"代理服务"⇒ 105,883.20 元机票款被判成**主营业务成本**；
#    ② 落地无门：`*运输服务*客运服务费 / 票价 / 国内机票款` 含"运输"，但服务轨道不吃
#       存货采购成本层 ⇒ 72,135.26 元退成"待核"，而同一实物的「住宿服务住宿费」却在费用桶
#       —— 同一类支出两种归属，读者一眼就看出不一致。
#  ⚠ 口径说明（如实、不猜死）：默认按**员工差旅**归期间费用；若实为**为客户/项目代订**
#    （应向客户另行收费），须凭项目合同调整 —— 故本层结论附带 `needs_context=True` 与
#    需补资料说明，绝不把"代订"这一少数情形当成不存在。
TRAVEL_KWS = (
    # 票务与客运（含"代订"这种票务平台口径写法）
    "机票", "车票", "火车票", "动车", "高铁", "客运", "旅客运输", "交通费",
    "退票费", "改签费", "行李费", "燃油附加费", "机场建设费", "行程单",
    "订票费", "代订机票", "代订住宿", "代订房", "代订票",
    # 住宿与旅游（出差住宿、会务之外的旅游服务）
    "住宿", "房费", "旅游服务", "旅行社",
    # 明确的差旅口径用词
    "差旅费", "差旅",
)

#: 资本化层（形成资产，不得一次性计入成本/费用；税务上另按折旧/摊销处理）
CAPITAL_KWS = (
    "固定资产", "设备", "机器", "机械", "车辆", "汽车", "货车", "工程机械",
    "房屋", "建筑物", "厂房", "办公楼", "土地使用权", "无形资产", "专利",
    "商标", "著作权", "软件著作权", "在建工程", "安装费", "工程材料",
    # 房屋装修改造：资本化或长期待摊，不得一次性进当期损益
    "装修", "装潢", "装修工程",
)

#: 预付卡层（购入时不征税、进项不得抵扣、税前不得扣除 → 必须看到实际消费去向）
PREPAID_KWS = (
    "预付卡", "单用途卡", "购物卡", "礼品卡", "储值卡", "加油卡", "提货券",
    "预付", "预付账款", "京东e卡", "京东卡", "e卡",
)

#: 个人消费 / 不得税前扣除（不得计入企业成本费用）
PERSONAL_KWS = (
    "个人消费", "个人", "员工个人", "家属", "私用",
)

# ── 供其他模块「引用」而不是「重抄」的派生词表 ───────────────────────────────
# ★ 单源铁律：这四张表是本模块派生出来的**唯一出口**。
#   其余模块（memory / domain_analysis / main_biz_cost / pipeline）只许 import 后
#   直接使用，**不得**再写一份字面量表（闸门 `check_account_classifier_single_source` 拦）。

#: 「重大费用关键词（需对公付款但非主营成本）」—— 原 domain_analysis 与
#: main_biz_cost 各写一份（后者多 运费/装卸/承运/运送 ⇒ 同一张住宿费发票两套结论）
def major_expense_keywords() -> List[str]:
    """通用费用 + 需上下文词 的并集（口径唯一，两处同名实现由此收敛为一份）。"""
    out: List[str] = []
    for kw in tuple(GENERAL_EXPENSE_KWS) + tuple(NEEDS_CONTEXT_KWS):
        if kw not in out:
            out.append(kw)
    return out


#: 「经营费用关键词（排除出生产物资分析）」—— 原 pipeline 私有表
def operating_expense_keywords() -> List[str]:
    return list(GENERAL_EXPENSE_KWS)


#: 全部权威关键词（单源闸门用它反扫私有重抄）
def all_authoritative_keywords() -> List[str]:
    out: List[str] = []
    for tup in (GENERAL_COST_KWS, GENERAL_EXPENSE_KWS, NEEDS_CONTEXT_KWS,
                CAPITAL_KWS, PREPAID_KWS, PERSONAL_KWS):
        for kw in tup:
            if kw not in out:
                out.append(kw)
    return out


def expense_element_keywords(exclusive: Optional[Dict[str, Sequence[str]]] = None) -> Dict[str, List[str]]:
    """经营要素完备性检测词表（供 `memory.BIZ_EXPENSE_KEYWORDS` **引用**而非重抄）。

    ⚠ 这不是「成本/费用会计归属」词表，是另一个概念：用于判断企业是否具备
      **真实经营要素**（缺场地/能耗/物流/办公 ⇒ 空壳、账外经营线索）。
      故此处**不追求与权威层的词完全一致**，而是「权威层命中词 ∪ 该模块自有词」，
      由调用方把自己的独有词传入 `exclusive`，保证零功能回归且不重抄权威词。

    新增同类要素：在本函数的层选择里加一条映射即可，不改分类逻辑。
    """
    nc, ge = NEEDS_CONTEXT_KWS, GENERAL_EXPENSE_KWS

    def _pick(pool: Sequence[str], words: Sequence[str]) -> List[str]:
        out = [k for k in pool if any(w in k for w in words)]
        return [k for k in dict.fromkeys(out)]

    derived: Dict[str, List[str]] = {
        "租赁": _pick(nc, ("租赁", "租金", "场地", "仓租")),
        "水电": _pick(nc, ("水电", "电费", "水费", "蒸汽", "燃气", "煤炭", "燃油")),
        "物业": _pick(tuple(ge) + nc, ("物业", "物管", "管理费")),
        "通信": _pick(ge, ("通信", "电话", "话费", "短信")),
        "物流": _pick(nc, ("运输", "运费", "物流", "货运", "配送", "装卸", "搬运")),
        "办公": _pick(ge, ("办公", "文具", "打印", "复印", "纸张", "硒鼓", "墨盒", "快递", "邮递")),
        "维修": _pick(nc, ("维修", "维护", "保养", "修理", "修缮")),
        "安保": _pick(tuple(nc) + tuple(ge), ("安保", "保安", "监控", "消防")),
    }
    for cat, kws in dict(exclusive or {}).items():
        bucket = derived.setdefault(str(cat), [])
        for k in (kws or ()):
            if k and k not in bucket:
                bucket.append(k)
    return derived


def _industry_core(industry: Sequence[str]) -> List[str]:
    """行业核心投入（数据驱动）。取不到行业口径时返回空 → 上游必须落「待核」。"""
    out: List[str] = []
    try:
        from engine.industry_resolver import core_inputs_for_many
        for kw in core_inputs_for_many(list(industry or [])):
            if kw and str(kw) not in out:
                out.append(str(kw))
    except Exception:
        return []
    return out


def _parts_text(*parts: Any) -> str:
    return " ".join(str(p or "") for p in parts).strip()


def _longest_keyword_hit(text: str, table: Iterable[str]) -> Optional[str]:
    """最长命中优先，避免「材料」吞掉「原材料」、「礼品」吞掉「礼盒」前的判定错位。"""
    best: Optional[str] = None
    best_len = 0
    for kw in table:
        if kw and kw in text and len(kw) > best_len:
            best, best_len = kw, len(kw)
    return best


#: 计价尾缀：金税品名常把同一实物写成「代言费 / 代言服务费 / 代言服务」三种形式。
#  词表里写的是一个写法，票面是另一个写法 ⇒ 按**词根**比对，否则该进成本的反落"待核"
#  （实测：行业核心投入登记了「代言费」，票面是「*现代服务*代言服务费」→ 匹配不上
#   → 641,509.43 元被扔进"待核"，而它本是该行业的核心投入）。
_KW_TRAIL_SUFFIXES = ("服务费", "服务", "费用", "费", "款项", "款", "金额")
#: 词根化**禁用**结果：这些词本身没有任何行业信息，词根化后会命中一切含"服务/费"的品名
#  （实测隐患：`core_inputs['咨询服务']` 里登记过裸「服务费」，词根化后成「服务」
#   ⇒ 该行业所有 `*服务费` 都被判成主营业务成本）。
_KW_ROOT_BLOCK = frozenset({"服务", "费用", "费", "款", "款项", "金额", "服务费"})


def _kw_root(kw: Any) -> str:
    """取关键词词根（去计价尾缀）；词根至少留 2 个字，且不得退化成无行业信息的泛词。"""
    k = str(kw or "")
    for s in _KW_TRAIL_SUFFIXES:
        if k.endswith(s) and len(k) - len(s) >= 2:
            root = k[: -len(s)]
            return k if root in _KW_ROOT_BLOCK else root
    return k


def _longest_core_hit(text: str, core: Sequence[str]) -> Optional[str]:
    """行业核心投入匹配：**原词 与 词根 二者取最长命中**。

    ⚠ 只用于「行业核心投入层」：该层的词表由数据文件（`industry_data.json::core_inputs`）
      维护、按行业登记，词根化不会把别的行业/别的层带偏；通用费用层等仍用逐字匹配
      （那里词多且杂，词根化容易过宽）。
    """
    best: Optional[str] = None
    best_len = 0
    for kw in (core or ()):
        for cand in (str(kw or ""), _kw_root(kw)):
            if cand and len(cand) > best_len and cand in text:
                best, best_len = cand, len(cand)
    return best


# ═══ 结构性证据层（2026-10-02 新增：成本/费用归属的**第一刀**）════════════════════════
# 发票票面**没有会计科目字段**，但有三样**行业无关、资料无关**的硬证据可以先把
# 「这张进项有没有实物存货」切开 —— 这正是「一键分析能否分辨主营业务成本 vs 期间费用」的
# 分水岭（此前只能靠关键词猜 + 业态兜底 ⇒ 服务类外购被兜底成成本、货物类又无处落地）。
#
#   ① 业务类型（开票软件口径，如「库存商品_饲料」/「销售费用_运杂费」）
#   ② 税收分类编码（权威，字段 `tax_code`；真实列名是**「税收编码」**不是「税收分类编码」）
#   ③ 计量单位（`unit`：件/吨/千克/台… ⇒ 货物；次/月/小时/项… ⇒ 服务）
#   ④ 开票项目 `*大类*` 的大类名（含「服务」二字 ⇒ 服务）
#
# ★ 纪律：只登记**已实证**的前缀；未实证的一律不登记 ⇒ 回退关键词层/业态兜底（宁缺勿错）。

#: 结构性定性结果（小写常量，供 evidence 文案与分支判据引用）
KIND_GOODS = "goods"            #: 货物（构成存货）
KIND_SERVICE = "service"        #: 服务/劳务/无形资产（无实物，不构成存货）
KIND_PREPAID = "prepaid"        #: 预付卡销售
KIND_AGENCY = "agency"          #: 代收代付（不计本企业成本费用）
KIND_UNKNOWN = ""

#: 税收分类编码「两位前缀」→ (结构性定性, 人可读名)。
#: 证据：本仓库真实进项 **3620 行**只读统计（scripts/_probe_structural_fields.py），
#:      每条前缀均附开票项目佐证；新增同类只在本表加一行，不改分类逻辑。
#:   10 货物   `*纺织产品*被子` `*饲料*宠物食品` `*纸制品*纸箱`（1924 行，52%）
#:   11 货物   `*供电*电费`（电力/热力属 VAT 货物税目）
#:   20 劳务   `*劳务*维修费`
#:   30 服务   `*设计服务*设计服务费` `*广告服务*广告发布费` `*运输服务*客运服务费`
#:             `*信息技术服务*信息服务费` `*物流辅助服务*搬运服务`（1320 行，36%）
#:   40 无形资产 `*无形资产*会员权益-餐饮权益`
#:   60 预付卡   `*预付卡销售*京东E卡`（与 PREPAID_KWS 同口径）
#:   61 代收代付 `*代收民航发展基金*代收民航发展基金`（代收代付不计本企业成本费用）
TAX_CODE_CLASSES: Dict[str, Tuple[str, str]] = {
    "10": (KIND_GOODS, "货物"),
    "11": (KIND_GOODS, "电力/热力/燃气等货物"),
    "20": (KIND_SERVICE, "劳务"),
    "30": (KIND_SERVICE, "服务"),
    "40": (KIND_SERVICE, "无形资产"),
    "60": (KIND_PREPAID, "预付卡销售"),
    "61": (KIND_AGENCY, "代收代付"),
}

#: 业务类型前缀 → (结构性定性, 人可读名, 期间费用子目)（实证：公司3 发票列表「库存商品_饲料」等）
_BIZ_TYPE_INVENTORY = ("库存商品", "原材料", "半成品", "产成品", "周转材料", "委托加工物资")
_BIZ_TYPE_EXPENSE = ("销售费用", "管理费用", "财务费用", "研发费用", "制造费用", "营业费用")

#: 服务类大类名（开票项目 `*...*` 里的「大类」文本命中即服务）
_SERVICE_CATEGORY_HINTS = (
    "交通运输服务", "物流辅助服务", "信息技术服务", "设计服务", "广告服务",
    "鉴证咨询服务", "专业技术服务", "文化创意服务", "商务辅助服务", "货物运输服务",
    "建筑服务", "金融服务", "生活服务", "旅游服务", "鉴证服务", "认证服务",
)
#: 货物类大类名（开票项目 `*...*` 的大类明确是货物品名）
_GOODS_CATEGORY_HINTS = (
    "饲料", "纺织产品", "纸制品", "塑料制品", "金属材料", "化工原料", "五金",
    "电子产品", "食品", "饮料", "服装", "木材", "建材", "机械设备", "仪器仪表",
)

#: 服务单位（计量单位层面即说明这是服务，无实物）
_SERVICE_UNITS = ("月", "季", "年", "小时", "人次", "人天", "吨公里", "公里", "千米", "项", "次", "批", "天", "日")
#: 货物单位（有实物，构成存货）
_GOODS_UNITS = ("吨", "千克", "公斤", "克", "件", "个", "台", "套", "只", "张", "本", "根", "条",
                "瓶", "包", "箱", "盒", "袋", "卷", "米", "升", "块", "双", "付", "组", "罐")


def structural_kind(tax_code: Any = "", unit: Any = "", biz_type: Any = "",
                    text: Any = "") -> Tuple[str, str]:
    """结构性定性：这张进项**有没有实物存货** ⇒ 成本/费用第一刀（行业无关、资料无关）。

    返回 ``(kind, evidence)``；取不到返回 ``("", 原因)``。优先级 ①业务类型 ②税收编码
    ③计量单位 ④开票项目大类 ⑤品名含「服务」。
    ★ 只做「定性」，**不做最终裁决** —— 最终三态仍由各关键词层/业态兜底给出，
      结构性证据用来①堵住「服务类被业态兜底成成本」②给未命中项一个可自证的成本兜底。
    """
    biz_s = str(biz_type or "").strip()
    if biz_s:
        for pre in _BIZ_TYPE_INVENTORY:
            if biz_s.startswith(pre):
                return KIND_GOODS, "业务类型「%s」" % biz_s
        for pre in _BIZ_TYPE_EXPENSE:
            if biz_s.startswith(pre):
                return KIND_SERVICE, "业务类型「%s」属当期损益口径" % biz_s
    tc_s = str(tax_code or "").strip()
    if len(tc_s) >= 2:
        hit = TAX_CODE_CLASSES.get(tc_s[:2])
        if hit:
            return hit[0], "税收分类编码 %s（%s）" % (tc_s[:19], hit[1])
    u_s = str(unit or "").strip()
    if u_s:
        if u_s in _SERVICE_UNITS:
            return KIND_SERVICE, "计量单位「%s」" % u_s
        if u_s in _GOODS_UNITS:
            return KIND_GOODS, "计量单位「%s」" % u_s
    body = str(text or "")
    for hint in _SERVICE_CATEGORY_HINTS:
        if hint in body:
            return KIND_SERVICE, "开票项目含服务大类「%s」" % hint
    for hint in _GOODS_CATEGORY_HINTS:
        if hint in body:
            return KIND_GOODS, "开票项目含货物大类「%s」" % hint
    if "服务" in body:
        return KIND_SERVICE, "品名含「服务」"
    return KIND_UNKNOWN, "业务类型/税收编码/计量单位/开票项目均未给出定性"


def _inventory_support_decision(text: str, kind_why: str,
                                ind_list: Sequence[str]) -> Optional[Dict[str, Any]]:
    """命中「存货采购支持词」（运输/装卸/搬运/包装/仓租/挑选整理/辅料耗材试剂）时的裁决。

    ★ 业态闸门（2026-10-02）：「运输/装卸/搬运/包装 ⇒ 存货成本」是**企业会计准则第1号——存货
      第六条**的明文结论，但**只在有存货的业态成立**（贸易型/生产型）。服务型（广告/咨询/信息技术
      …）**根本无存货**，其运输费、搬运费一律是当期损益 ⇒ 此处**不得**裁决为成本，返回 None
      由调用方继续往下落到通用费用层/业态兜底（服务型⇒待核）。
      真实验收漏网点：广告传媒的 `*物流辅助服务*运输费` 曾被判成主营业务成本。
    """
    kw = _longest_keyword_hit(text, INVENTORY_SUPPORT_KWS)
    if not kw or _business_category(ind_list) not in ("贸易型", "生产型"):
        return None
    return {
        "account_class": CLASS_COST,
        "expense_sub": "",
        "confidence": CONF_MEDIUM,
        "evidence": "存货采购成本层｜%s｜命中「%s」" % (kind_why or "票面品名", kw),
        "matched_kw": kw,
        "matched_layer": "存货采购成本",
        # ★ 仍 needs_context=True：准则推论 ≠ 个案事实，若为**销售环节**运费（→销售费用）或
        #   管理用途，仍须凭项目/合同上下文复核，不得把结论说死。
        "needs_context": True,
        "missing_material": "项目合同、验收(入库)单与付款凭证",
        "reason": "属存货采购成本构成项（运输费/装卸费/包装费/挑选整理费），计入存货、结转主营业务成本；"
                  "若为销售环节运费则应改计销售费用，须凭项目/合同上下文复核",
    }


#: 「自用」指示词（2026-10-02，用户判定原则的第二个例子）：
#   同一张「技术服务费」，代客户项目开发 ⇒ 成本；**公司内部 IT 系统维护 ⇒ 管理费用**。
#   依据是"是否为维持公司整体运营而发生的间接支出"——自用即间接，与收入无直接配比。
#   ⚠ 词表刻意用**自用语义**而非裸词：「行政」「管理」这类裸词会误伤项目类备注
#     （如"为XX项目提供行政管理服务"），且本层排在「项目直接配比」之后，
#     项目证据一旦存在就先按成本定案。
SELF_USE_KWS = (
    "内部使用", "内部系统", "内部管理", "内部维护", "公司内部", "自用",
    "办公用", "办公室用", "行政使用", "管理部门", "员工使用", "内部办公",
)

#: 备注栏里出现这些词，才认为它**在说项目/合同归属**。
#  为什么不加这一层不行：备注栏绝大多数内容是"见附件""款已付""对账无误"这类**与项目无关**
#  的文字；若"有备注就算项目证据"，等于把几乎所有发票都判成主营业务成本（严重误判）。
_PROJECT_INDICATORS = ("项目", "工程", "合同", "订单", "方案", "标的")
#: 从备注里**提取**项目名（取到"…项目/工程/合同/订单"为止的片段），避免把整段备注当项目名
_PROJECT_NAME_RE = None  # 延迟编译（见 _project_evidence）


def _project_evidence(inv_or_goods: Any, project: str = "", remark: str = "") -> str:
    """取「项目/合同归属」证据（适用于 dict 行或纯文本两种调用形式）。

    这是「直接相关性」判据的**唯一证据入口**：取不到就返回空串
    （**空＝没有证据，不得据此推断归属**）。

    证据来源与严格性：
      ① 项目名 / 项目编号 / 合同号字段 —— 本身就是项目专用字段，非空即证据；
      ② 备注栏 —— **必须出现项目指示词**（项目/工程/合同/订单/方案/标的）才算证据，
         并从中**提取**项目名片段（`…项目` / `…合同`），不能把整段备注当项目名。
    """
    pj_raw = str(project or "").strip()
    rk_raw = str(remark or "").strip()
    if isinstance(inv_or_goods, dict):
        try:
            from engine.fieldkit import project_of as _pj, remark_of as _rk  # 单一权威
            pj_raw = pj_raw or _pj(inv_or_goods)
            rk_raw = rk_raw or _rk(inv_or_goods)
        except Exception:
            pass
    if pj_raw:
        return pj_raw[:40]
    if rk_raw and any(k in rk_raw for k in _PROJECT_INDICATORS):
        global _PROJECT_NAME_RE
        if _PROJECT_NAME_RE is None:
            import re as _re_pj
            _PROJECT_NAME_RE = _re_pj.compile(
                r"([\u4e00-\u9fa5A-Za-z0-9（）()·\-]{2,30}?(?:项目|工程|合同|订单))")
        m = _PROJECT_NAME_RE.search(rk_raw)
        return (m.group(1) if m else rk_raw[:30]).strip()
    return ""


def _project_linked_decision(evidence: str, kind_reason: str,
                             travel_kw: str = "") -> Optional[Dict[str, Any]]:
    """「与收入直接配比」⇒ 主营业务成本（用户给出的**核心判据**）。

    用户原话（判定原则）：区分成本与费用的核心不是发票品名，而是**该支出是否直接服务于
    某个已承接或将要承接的项目、并与该项目收入形成直接配比** ——
    同一张「技术服务费」：为客户定制项目支付 ⇒ 成本；内部 IT 维护 ⇒ 管理费用。

    落地口径（宁缺勿错）：
      · 只有**取得项目/合同证据**（项目名、项目编号、合同号，或备注栏写明项目）时命中；
      · 证据取不到 ⇒ 返回 None，由后续按品名 + 行业口径判定，**绝不臆测项目归属**；
      · 差旅票务若对应到项目（如为客户项目出差），按用户原则可入成本 ⇒ 本层**先于**
        差旅出行层判定（`travel_kw` 仅用于把理由写清楚）。
    """
    if not evidence:
        return None
    why = ("该支出直接对应到项目/合同「%s」，与该项目收入形成直接配比"
           % evidence[:40])
    if travel_kw:
        why = ("%s；差旅票务本属期间费用，但对应到具体项目时按项目直接配比计入成本"
               % why)
    return {
        "account_class": CLASS_COST,
        "expense_sub": "",
        "confidence": CONF_HIGH,
        "evidence": "项目直接配比层｜%s｜命中项目/合同「%s」" % (kind_reason or "票面", evidence[:40]),
        "matched_kw": evidence[:40],
        "matched_layer": "项目直接配比",
        "needs_context": False,
        "missing_material": "",
        "reason": why + "；须留存该项目合同与验收/结算单据备查",
    }


def filter_cost_invoices(invoices: Any, industry: Any = "") -> List[Dict[str, Any]]:
    """只保留**归属为主营业务成本**的发票（三态口径复核）。唯一实现，多处引用。

    为什么需要它（2026-10-02，用户复核「按供应商」表）：
      「主营成本按供应商」「核心成本逐张清单」这类明细的**标签就是"主营业务成本"**，
      因此必须按「成本/费用/待核」三态过滤，不能用"发票类目口径"的全量。
      实测公司1：发票类目口径核心成本 59 家供应商里，**47.5% 的金额实际被判为
      期间费用或待核**（机票、住宿、咨询、体育文化…），挂在"主营业务成本"名下
      → 读者看到"表名说成本、内容混着差旅和咨询"，且与三态表自相矛盾。

    ⚠ 只用于**明细展示**；金额统计口径（如"发票类目口径合计"）不得用它替换 ——
      那个合计是与账面口径做勾稽的基准，必须保持全量。
    """
    out: List[Dict[str, Any]] = []
    for inv in (invoices or []):
        if not isinstance(inv, dict):
            continue
        g = str(inv.get("goods") or inv.get("货物或应税劳务名称") or "")
        try:
            cls = classify_line(
                g, industry=industry,
                tax_code=inv.get("tax_code") or inv.get("税收编码") or "",
                unit=inv.get("unit") or inv.get("单位") or "",
                biz_type=inv.get("biz_type") or inv.get("业务类型") or "",
                project=inv.get("project") or inv.get("项目名称") or inv.get("合同号") or "",
                remark=inv.get("remark") or inv.get("备注") or "",
            ).get("account_class")
        except Exception:
            cls = ""
        if cls == CLASS_COST:
            out.append(inv)
    return out


def _travel_decision(kind_reason: str, text: str) -> Optional[Dict[str, Any]]:
    """差旅出行层裁决：命中票务/客运/住宿/旅游 ⇒ **期间费用（差旅费）**。

    设计要点见 `TRAVEL_KWS` 注释：本层必须排在**行业核心投入层之前**，否则
    「*经纪代理服务*机票款」会被行业核心投入里的"代理服务"截走判成主营业务成本。
    """
    kw = _longest_keyword_hit(text, TRAVEL_KWS)
    if not kw:
        return None
    return {
        "account_class": CLASS_EXPENSE,
        "expense_sub": "差旅费",
        "confidence": CONF_HIGH,
        "evidence": "差旅出行层｜%s｜命中「%s」" % (kind_reason or "票面品名", kw),
        "matched_kw": kw,
        "matched_layer": "差旅出行",
        # 员工差旅是常态；"为客户/项目代订"是少数情形 ⇒ 提示复核，不把话说死
        "needs_context": True,
        "missing_material": "出差审批单/行程单（如属为客户代订等非员工差旅，另需项目合同）",
        "reason": "员工出行票务与住宿属期间费用（管理费用—差旅费）；"
                  "如实属为客户/项目代订并另行收费，须凭项目合同改计成本",
    }


def _resolve_service(kind_reason: str, text: str, goods_s: str,
                     core: Sequence[str],
                     ind_list: Sequence[str]) -> Optional[Dict[str, Any]]:
    """服务/劳务/无形资产轨道裁决（结构性定性为「无实物」 ⇒ **不进存货成本推定**）。

    顺序：**差旅出行层 → 行业核心投入** → 通用成本 → 存货采购支持费 → 通用费用；
    全部未命中 ⇒ 待核（★ 服务无存货可比照，**绝不**业态兜底成成本）。
    ★ 差旅层必须最先判：员工出行票务与行业无关，抢在"行业核心投入"之前才能避免
      「*经纪代理服务*机票款」被行业词表里的"代理"截走（实测 105,883.20 元误判为成本）。
    """
    _tr = _travel_decision(kind_reason, text)
    if _tr:
        return _tr
    kw = _longest_core_hit(goods_s, core) or _longest_core_hit(text, core)
    if kw:
        return {
            "account_class": CLASS_COST, "expense_sub": "", "confidence": CONF_HIGH,
            "evidence": "行业核心投入层｜%s｜命中「%s」" % (kind_reason, kw),
            "matched_kw": kw, "matched_layer": "行业核心投入（服务轨道）",
            "needs_context": False, "missing_material": "",
            "reason": "属该行业核心投入（服务/劳务形态），构成服务产出成本",
        }
    kw = _longest_keyword_hit(text, GENERAL_COST_KWS)
    if kw:
        return {
            "account_class": CLASS_COST, "expense_sub": "", "confidence": CONF_MEDIUM,
            "evidence": "通用成本层｜%s｜命中「%s」" % (kind_reason, kw),
            "matched_kw": kw, "matched_layer": "通用成本（服务轨道）",
            "needs_context": False, "missing_material": "",
            "reason": "构成服务产出的直接投入（委外加工等），计入主营业务成本",
        }
    svc_inv = _inventory_support_decision(text, kind_reason, ind_list)
    if svc_inv:
        svc_inv["matched_layer"] = "存货采购成本（服务轨道·%s）" % kind_reason
        return svc_inv
    kw = _longest_keyword_hit(text, GENERAL_EXPENSE_KWS)
    if kw:
        sub, why = _expense_sub_of(text, kw)
        return {
            "account_class": CLASS_EXPENSE, "expense_sub": sub, "confidence": CONF_MEDIUM,
            "evidence": "通用费用层｜%s｜命中「%s」" % (kind_reason, kw),
            "matched_kw": kw, "matched_layer": "通用费用（服务轨道）",
            "needs_context": False, "missing_material": "",
            "reason": why,
        }
    return {
        "account_class": CLASS_UNDETERMINED, "expense_sub": "", "confidence": CONF_LOW,
        "evidence": "服务轨道｜%s｜未落入行业核心投入/通用成本/存货采购支持/通用费用" % kind_reason,
        "matched_kw": "", "matched_layer": "服务轨道（无存货可比照）",
        "needs_context": True, "missing_material": "项目合同、验收(入库)单与付款凭证",
        "reason": "服务类采购无存货可比照，既不能推定成本也不宜直接计入费用，须凭项目/合同上下文定性",
    }


def classify_line(
    goods: Any,
    *,
    industry: Any = "",
    seller: Any = "",
    note: Any = "",
    require_context: bool = True,
    tax_code: Any = "",
    unit: Any = "",
    biz_type: Any = "",
    project: Any = "",
    remark: Any = "",
) -> Dict[str, Any]:
    """对**一张进项发票/一行明细**做成本/费用归属判定（三态）。

    返回（字段只读，禁调用方写私有字段）::
        {
          "account_class":  三态之一（CLASS_*），
          "expense_sub":    期间费用时的明细归属（销售/管理/财务/研发），否则 "",
          "confidence":     高/中/低,
          "evidence":       人可读的判定依据（命中层+词+行业口径），
          "matched_kw":     命中的关键词（未命中为 ""），
          "matched_layer":  命中的分层名（行业核心投入/通用成本/需上下文/通用费用/资本/预付/个人/未命中）,
          "needs_context":  该品名是否**必须**依赖项目/合同上下文才能定性，
          "missing_material": 定性所缺的具体资料名（取自 material_recognition 已登记名；此处只给线索名）
          "reason":         一句话说明为什么（供报告直接引用，不拼接新文案）
        }

    铁律：**不得**因为品名命中就判 confirmed。判不出来一律 CLASS_UNDETERMINED。
    """
    text = _parts_text(goods, note)
    goods_s = str(goods or "")
    ind_list = [i for i in (industry if isinstance(industry, (list, tuple, set))
                            else [industry]) if i]
    ind_desc = "、".join(str(i) for i in ind_list) or "（无行业口径）"

    # ★ ② 结构性定性（第一刀：有没有实物存货）—— 行业无关、资料无关、关键词无关。
    #   服务/预付卡/代收代付 ⇒ **不进存货成本推定**，直接走服务轨道裁决（服务无存货可比照）。
    _kind, _kind_why = structural_kind(tax_code, unit, biz_type,
                                       "%s %s" % (goods_s, text))
    _core = _industry_core(ind_list)

    def _undetermined(layer: str, kw: str, why: str) -> Dict[str, Any]:
        return {
            "account_class": CLASS_UNDETERMINED,
            "expense_sub": "",
            "confidence": CONF_LOW,
            "evidence": "%s｜未就用途取得项目/合同上下文，%s" % (layer, why),
            "matched_kw": kw,
            "matched_layer": layer,
            "needs_context": True,
            "missing_material": "项目合同、验收(入库)单与付款凭证",
            "reason": why,
        }

    # ── ① 硬排除层：资本性支出 / 预付卡 / 个人消费 ──────────────────────────
    kw = _longest_keyword_hit(text, PERSONAL_KWS)
    if kw:
        return {
            "account_class": CLASS_UNDETERMINED,
            "expense_sub": "",
            "confidence": CONF_MEDIUM,
            "evidence": "个人消费层｜命中「%s」" % kw,
            "matched_kw": kw,
            "matched_layer": "个人消费",
            "needs_context": False,
            "missing_material": "个人消费明细与支付主体证明",
            "reason": "以个人名义/个人消费名义取得，不得计入企业成本费用，也不得税前扣除",
        }
    kw = _longest_keyword_hit(text, CAPITAL_KWS)
    if kw:
        return {
            "account_class": CLASS_CAPITAL,
            "expense_sub": "",
            "confidence": CONF_MEDIUM,
            "evidence": "资本化层｜命中「%s」" % kw,
            "matched_kw": kw,
            "matched_layer": "资本化",
            "needs_context": False,
            "missing_material": "资产验收单与折旧年限资料",
            "reason": "形成长期资产，须资本化后按折旧/摊销分期扣除，不得一次性计入当期成本费用",
        }
    kw = _longest_keyword_hit(text, PREPAID_KWS)
    if kw:
        return {
            "account_class": CLASS_UNDETERMINED,
            "expense_sub": "",
            "confidence": CONF_MEDIUM,
            "evidence": "预付卡层｜命中「%s」" % kw,
            "matched_kw": kw,
            "matched_layer": "预付卡",
            "needs_context": True,
            "missing_material": "预付卡实际消费明细与对应项目归属",
            "reason": "预付卡购入环节不征税、进项不得抵扣、税前不得扣除，须见到实际消费去向才能定性",
        }

    # ── ②★★ 项目直接配比层（用户判定原则的核心：与收入直接配比 ⇒ 主营业务成本）──────
    #   依据（用户给出）：区分成本与费用的核心不是发票品名，而是该支出**是否直接服务于
    #   某个已承接/将要承接的项目、与该项目收入形成直接配比**——同一张「技术服务费」，
    #   为客户定制项目支付＝成本，内部 IT 维护＝费用。
    #   落地口径：**只有取得项目/合同证据才命中**（项目名/项目编号/合同号，或备注栏写明项目）；
    #   取不到证据一律返回 None，交后续按品名+行业口径判定 —— 绝不臆测项目归属。
    #   位置：在「硬排除」之后（个人消费/资本化/预付卡即便挂了项目也不得计入成本费用），
    #   但在差旅出行层与行业核心投入层**之前**（差旅若对应到项目，按用户原则可入成本）。
    _pj_ev = _project_evidence(None, project=str(project or ""), remark=_parts_text(remark, note))
    if _pj_ev:
        _tk_hit = _longest_keyword_hit(text, TRAVEL_KWS)
        _pj_dec = _project_linked_decision(_pj_ev, "", travel_kw=_tk_hit or "")
        if _pj_dec:
            return _pj_dec

    # ── ②★★b 自用层（用户判定原则的第二个例子：间接相关 ⇒ 期间费用）────────────
    #   「同一张技术服务费：为客户定制项目 ⇒ 成本；公司内部 IT 系统维护 ⇒ 管理费用」。
    #   判据＝**备注/摘要说明该支出是自用**（为维持公司整体运营），与收入无直接配比。
    #   位置在项目层之后：项目证据一旦存在，先按"直接配比"定案为成本。
    _su_kw = _longest_keyword_hit(_parts_text(remark, note), SELF_USE_KWS)
    if _su_kw:
        return {
            "account_class": CLASS_EXPENSE,
            "expense_sub": "管理费用",
            "confidence": CONF_MEDIUM,
            "evidence": "自用层｜票面说明为自用｜命中「%s」" % _su_kw,
            "matched_kw": _su_kw,
            "matched_layer": "自用（无项目配比）",
            "needs_context": False,
            "missing_material": "",
            "reason": "该支出为维持公司整体运营而发生（自用），与主营业务收入无直接配比，"
                      "计入期间费用；若实为某项目投入，须提供该项目合同后调整",
        }

    # ── ②★ 结构性定性为「无实物」⇒ 服务轨道（行业无关第一刀；防服务类外购被业态兜底成成本）
    if _kind in (KIND_SERVICE, KIND_PREPAID, KIND_AGENCY):
        return _resolve_service(_kind_why, text, goods_s, _core, ind_list)

    # ── ②★b 差旅出行层（优先于行业核心投入，见 TRAVEL_KWS 注释）─────────────
    _tr = _travel_decision(_kind_why, text)
    if _tr:
        return _tr

    # ── ③ 行业核心投入层（优先于通用费用层，防广告公司核心成本被截走） ────────
    core = _core
    kw = _longest_core_hit(goods_s, core) or _longest_core_hit(text, core)
    if kw:
        return {
            "account_class": CLASS_COST,
            "expense_sub": "",
            "confidence": CONF_HIGH,
            "evidence": "行业核心投入层｜行业口径「%s」命中「%s」" % (ind_desc, kw),
            "matched_kw": kw,
            "matched_layer": "行业核心投入",
            "needs_context": False,
            "missing_material": "",
            "reason": "属于该行业的核心投入，构成存货/服务产出成本",
        }

    # ── ③ 通用成本层 ────────────────────────────────────────────────────────
    kw = _longest_keyword_hit(text, GENERAL_COST_KWS)
    if kw:
        return {
            "account_class": CLASS_COST,
            "expense_sub": "",
            "confidence": CONF_MEDIUM,
            "evidence": "通用成本层｜命中「%s」" % kw,
            "matched_kw": kw,
            "matched_layer": "通用成本",
            "needs_context": False,
            "missing_material": "",
            "reason": "直接构成存货/服务产出，计入主营业务成本",
        }

    # ── ④ 需上下文层（★ 2026-10-02「命中层自动裁决」：一张表拆成两张） ─────────
    # ★ 旧缺陷 : 整张 NEEDS_CONTEXT_KWS 命中 ⇒ 两个分支 `return` 的都是 CLASS_UNDETERMINED
    #            （`require_context` 形同虚设）⇒ 本最该被分辨的 运输/装卸/包装/搬运
    #            反倒全退成"分不出来"。现按会计事实分道走：
    #   · 存货采购支持费 INVENTORY_SUPPORT_KWS —— 企业会计准则第1号——存货 第六条明文的
    #     存货采购成本构成（运输费/装卸费/包装费/挑选整理费…）⇒ **命中即自动裁决为成本**
    #     （业态闸门在 `_inventory_support_decision` 内：服务型无存货不吃这条）；
    #   · 用途模糊项 AMBIGUOUS_KWS（水电/维修/租赁/检测…，生产耗用 vs 办公耗用、项目用 vs
    #     管理用票面判不出）⇒ **仍落待核**（铁律：判不出不默认成本），
    #     除非 caller 显式声明已取得项目上下文（require_context=False）。
    _inv_dec = _inventory_support_decision(text, _kind_why, ind_list)
    if _inv_dec:
        return _inv_dec
    kw = _longest_keyword_hit(text, AMBIGUOUS_KWS)
    if kw and require_context:
        return _undetermined(
            "需上下文", kw,
            "同一品名可能计入成本也可能计入期间费用（生产耗用 vs 办公耗用、项目用 vs 管理用），"
            "须凭项目/合同上下文定性")
    # ── ⑤ 通用费用层（明确当期损益） ────────────────────────────────────────
    # ⚠ 食品/水果/茶叶/酒水/香烟/礼品/礼盒**不在此层**：这些"招待载体"词单独出现既不能证
    #   成费用（商贸进货的罐头含"食品"）、也不能证成存货，谁都判不了 ⇒ 交给 ⑥ 业态兜底或待核。
    #   业务招待一旦有语境，是由「招待/餐费/团建/福利」这些**用途词**判定，不靠载体词。
    kw = _longest_keyword_hit(text, GENERAL_EXPENSE_KWS)
    if kw:
        sub, why = _expense_sub_of(text, kw)
        return {
            "account_class": CLASS_EXPENSE,
            "expense_sub": sub,
            "confidence": CONF_MEDIUM,
            "evidence": "通用费用层｜命中「%s」" % kw,
            "matched_kw": kw,
            "matched_layer": "通用费用",
            "needs_context": False,
            "missing_material": "",
            "reason": why,
        }

    # ── ⑥ 未命中 → 按**业态**兜底（不是"一律待核"，也不是"一律成本"）──────────
    # ★ 真实验收暴露（2026-10-02，公司3 猩织光宠物食品商贸，940 个进项 SKU）：
    #   关键词表**在原理上不可能**穷举一个商贸企业的所有 SKU（猫粮/罐头/用品…上千种），
    #   若未命中即落待核，等于把这个行业最常见的主营业务成本全部丢掉。
    #   会计事实：生产型/贸易型企业的存货**就是**所采购的商品材料——除已判为期间费用、
    #   资本性支出、个人消费、预付卡之外的进项，基本构成存货、销售时结转为主营业务成本。
    #   服务型无存货，未命中口径的外购服务既可能是项目外包成本也可能是管理费用 ⇒ 必须待核。
    #   故用小口径的**业态**兜底（一次规则覆盖全行业全 SKU），而不是给某行业加白名单。
    category = _business_category(ind_list)
    if category in ("贸易型", "生产型"):
        return {
            "account_class": CLASS_COST,
            "expense_sub": "",
            "confidence": CONF_MEDIUM,
            "evidence": "业态兜底层｜%s｜行业口径「%s」属%s，未列入费用/资本口径的进项通常构成存货"
                        % (_kind_why or ("行业口径「%s」未定性" % ind_desc), ind_desc, category),
            "matched_kw": "",
            "matched_layer": "业态兜底（%s）" % category,
            "needs_context": False,
            "missing_material": "",
            "reason": "购销/生产业态下该笔进项未落入费用或资本化口径，按会计事实计入存货、结转主营业务成本",
        }
    return {
        "account_class": CLASS_UNDETERMINED,
        "expense_sub": "",
        "confidence": CONF_LOW,
        "evidence": "未命中任何权威层（行业核心投入/通用成本/需上下文/通用费用）＋业态「%s」无存货可比照"
                    % (category or "未取得"),
        "matched_kw": "",
        "matched_layer": "未命中（业态不支持推定）",
        "needs_context": True,
        "missing_material": "项目合同、验收(入库)单与付款凭证",
        "reason": "该业态无存货可比照，未命中口径的外购支出须凭项目/合同上下文定性",
    }


def _business_category(ind_list: Sequence[str]) -> str:
    """业态（贸易型 / 生产型 / 服务型 / 空）。取不到就返回空串 ⇒ 调用方落待核。"""
    try:
        from engine.industry_resolver import business_category
        for ind in (ind_list or []):
            try:
                cat = (business_category(str(ind)) or {}).get("category") or ""
            except Exception:
                cat = ""
            if cat:
                return str(cat)
    except Exception:
        return ""
    # ★ 2026-10-02 清理：原先 `return ""` 之后还有一整段 `return {...}`（**不可达死代码**，
    #   是 `_business_category` 早期形态的残留）—— 它永不会执行，却会让误读者以为
    #   「未命中 → 待核」在本函数内生成。此处只保留真正的业态口径（空串 ⇒ 调用方落待核）。
    return ""


def _expense_sub_of(text: str, kw: str) -> Tuple[str, str]:
    """期间费用的明细归属：招待/福利→管理；差旅→管理；利息/手续费→财务；其余→管理。"""
    if any(k in text for k in ("利息", "手续费", "银行")):
        return EXPENSE_SUB_FINANCE, "计入财务费用"
    if any(k in text for k in ("咨询", "顾问", "律师", "法律", "审计", "评估",
                               "认证", "培训", "招聘", "猎头", "会务", "会议")):
        return EXPENSE_SUB_ADMIN, "计入管理费用"
    if any(k in text for k in ("住宿", "差旅", "餐饮", "餐费", "招待", "团建",
                               "交通", "停车", "过路")):
        return EXPENSE_SUB_ADMIN, "计入管理费用（业务招待/职工福利口径）"
    if any(k in text for k in ("广告", "推广", "宣传", "展览", "参展", "媒体")):
        return EXPENSE_SUB_SELLING, "计入销售费用"
    return EXPENSE_SUB_ADMIN, "计入期间费用"


def classify_lines(
    lines: Sequence[Dict[str, Any]],
    *,
    industry: Any = "",
    require_context: bool = True,
    amount_of: Optional[Any] = None,
) -> Dict[str, Any]:
    """把一批进项明细（每行至少含 goods/品名文本）汇总成**三层结论**（供报告渲染）。

    返回::
        {
          "industry": 实际使用的行业口径,
          "total_amount": 不含税金额合计,
          "by_class": {account_class: {"amount": float, "count": int, "lines": [...]}},
          "cost_lines": [...], "expense_lines": [...], "pending_lines": [...],
          "missing_materials": 去重后的补证资料清单,
          "industry_covered": 是否启用了行业口径
        }
    """
    ind_list = [i for i in (industry if isinstance(industry, (list, tuple, set))
                            else [industry]) if i]
    core = _industry_core(ind_list)
    total = 0.0
    cost_lines: List[Dict[str, Any]] = []
    expense_lines: List[Dict[str, Any]] = []
    pending_lines: List[Dict[str, Any]] = []
    missing: List[str] = []

    for ln in (lines or []):
        if not isinstance(ln, dict):
            continue
        goods = ln.get("goods") or ln.get("goods_name") or ln.get("品名") or ""
        note = ln.get("note") or ln.get("备注") or ""
        # ★ 2026-10-02：把发票的**结构性证据**（税收编码/计量单位/业务类型）一并交给权威层，
        #   否则「第一刀」（有无实物存货）拿不到数据，只能退回关键词猜（本轮根因之一）。
        res = classify_line(
            goods, industry=ind_list, seller=ln.get("seller") or ln.get("对方单位") or "",
            note=note, require_context=require_context,
            tax_code=ln.get("tax_code") or ln.get("税收编码") or ln.get("税收分类编码") or "",
            unit=ln.get("unit") or ln.get("计量单位") or "",
            biz_type=ln.get("biz_type") or ln.get("业务类型") or "")
        amt_val = _safe_amount(ln, amount_of)
        total += amt_val
        item = {
            "goods": str(goods),
            "amount": round(amt_val, 2),
            "account_class": res["account_class"],
            "expense_sub": res["expense_sub"],
            "confidence": res["confidence"],
            "evidence": res["evidence"],
            "matched_kw": res["matched_kw"],
            "matched_layer": res["matched_layer"],
            "reason": res["reason"],
        }
        if res["missing_material"] and res["missing_material"] not in missing:
            missing.append(res["missing_material"])
        if res["account_class"] == CLASS_COST:
            cost_lines.append(item)
        elif res["account_class"] == CLASS_EXPENSE:
            expense_lines.append(item)
        else:
            pending_lines.append(item)

    by_class: Dict[str, Dict[str, Any]] = {}
    for bucket, cls in ((cost_lines, CLASS_COST), (expense_lines, CLASS_EXPENSE),
                        (pending_lines, CLASS_UNDETERMINED)):
        by_class[cls] = {
            "amount": round(sum(x["amount"] for x in bucket), 2),
            "count": len(bucket),
            "lines": bucket,
        }

    return {
        "industry": "、".join(str(i) for i in ind_list),
        "industry_covered": bool(core),
        "total_amount": round(total, 2),
        "by_class": by_class,
        "cost_lines": cost_lines,
        "expense_lines": expense_lines,
        "pending_lines": pending_lines,
        "missing_materials": missing,
    }


def _safe_amount(ln: Dict[str, Any], amount_of: Optional[Any]) -> float:
    """不含税金额；取不到记 0（区分缺失 vs 0 由调用方负责，此处不臆造）。"""
    if callable(amount_of):
        try:
            v = amount_of(ln)
            return float(v or 0.0)
        except Exception:
            return 0.0
    for k in ("amount", "金额", "不含税金额", "amount_excl_tax", "je"):
        v = ln.get(k)
        if v not in (None, ""):
            try:
                return abs(float(v))
            except (TypeError, ValueError):
                continue
    return 0.0
