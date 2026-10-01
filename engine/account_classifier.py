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

#: 计成本的 exception：即使命中需上下文层，只要 caller 显式给了项目上下文，仍可判成本
NEEDS_CONTEXT_KWS = (
    # 物流类（采购端运费→存货成本；销售端运费→销售费用；单看品名无法确定）
    "运输", "运费", "物流", "货运", "配送", "装卸", "搬运", "承运", "运送",
    # 能源（生产耗用→成本；办公耗用→管理费用）
    "水电", "电费", "水费", "蒸汽", "燃气", "煤炭", "燃油", "汽油", "柴油", "加油",
    # 生产辅耗
    # ⚠ 只认「包装材料/包装物/包装费」等**采购口径**写法：裸词「包装」会命中
    #   「软包装罐头」这类**商品属性**（真实验收：宠物罐头整块被挪去待核）
    "包装材料", "包装物", "包装袋", "包装箱", "包装费", "辅料", "耗材", "试剂",
    # 维护类
    "维修", "维护", "保养", "修理", "修缮",
    # 场地
    "租赁", "租金", "场地", "仓租",
    # 服务外购（用途决定：项目外包→成本；管理咨询→管理费用）
    # ⚠ 只留「劳务外包」：裸词「劳务/劳务费」过泛，会把 `*劳务*加工费` 截成费用、
    #   连带让 3 处既有回归测试失败（委托加工费对制造业就是主营业务成本）
    "检测", "化验", "实验", "会议", "会务", "安保", "劳务外包", "分包",
)

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


def classify_line(
    goods: Any,
    *,
    industry: Any = "",
    seller: Any = "",
    note: Any = "",
    require_context: bool = True,
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

    # ── ② 行业核心投入层（优先于通用费用层，防广告公司核心成本被截走） ────────
    core = _industry_core(ind_list)
    kw = _longest_keyword_hit(goods_s, core) or _longest_keyword_hit(text, core)
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

    # ── ④ 需上下文层（用途决定归属；无项目上下文即落待核） ───────────────────
    kw = _longest_keyword_hit(text, NEEDS_CONTEXT_KWS)
    if kw:
        if not require_context:
            return {
                "account_class": CLASS_UNDETERMINED,
                "expense_sub": "",
                "confidence": CONF_LOW,
                "evidence": "需上下文层｜命中「%s」但未提供项目上下文" % kw,
                "matched_kw": kw,
                "matched_layer": "需上下文",
                "needs_context": True,
                "missing_material": "项目合同、验收(入库)单与付款凭证",
                "reason": "同一品名可能计入成本也可能计入期间费用，须凭项目/合同上下文定性",
            }
        return _undetermined(
            "需上下文", kw,
            "同一品名可能计入成本也可能计入期间费用，须凭项目/合同上下文定性")
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
            "evidence": "业态兜底层｜行业口径「%s」属%s，未列入费用/资本口径的进项通常构成存货"
                        % (ind_desc, category),
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
    return ""
    return {
        "account_class": CLASS_UNDETERMINED,
        "expense_sub": "",
        "confidence": CONF_LOW,
        "evidence": "未命中任何权威层（行业核心投入/通用成本/需上下文/通用费用）",
        "matched_kw": "",
        "matched_layer": "未命中",
        "needs_context": True,
        "missing_material": "项目合同、验收(入库)单与付款凭证",
        "reason": "票面品名未落在任何已登记的成本/费用口径内，不得凭空定性",
    }


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
        res = classify_line(
            goods, industry=ind_list, seller=ln.get("seller") or ln.get("对方单位") or "",
            note=note, require_context=require_context)
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
