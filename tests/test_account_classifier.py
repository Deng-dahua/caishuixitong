# -*- coding: utf-8 -*-
"""成本/费用归属唯一权威 `engine/account_classifier.py` 回归测试。

锁死的东西（都是本轮真实验收踩出来的坑，不是纸面约束）：
  1. 三态：主营业务成本 / 期间费用 / 待核，判不出来**必须**待核，绝不默认成本；
  2. 业态兜底：贸易型/生产型未命中 → 存货成本（商贸 940 个 SKU 若全落待核就是事故）；
             服务型未命中 → 待核（服务无存货可比照，不许推定）；
  3. 行业层优先于通用费用层（防广告公司的核心成本「广告发布」被通用「广告」费用表截走）；
  4. 需上下文词无项目上下文必须待核（运输/水电/维修/租赁/会议/检测…）；
  5. 硬排除：资本化 / 预付卡 / 个人消费不得当成成本或费用；
  6. 输出必须可自证：confidence 与 evidence 非空；
  7. 词表单一源：两处同名 `_MAJOR_EXPENSE_KWS` 必须完全相等（同名字表漂移曾致错判）。
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import account_classifier as ac  # noqa: E402


def _cls(goods, **kw):
    return ac.classify_line(goods, **kw)


# ── 1. 三态：判不出来必须待核 ────────────────────────────────────────────────
def test_unknown_goods_is_undetermined_not_cost():
    r = _cls("全新未登记品名zzq999", industry="广告传媒")
    assert r["account_class"] == ac.CLASS_UNDETERMINED
    assert r["account_class"] != ac.CLASS_COST, "未命中却判成本 = 虚增成本（真实事故）"


def test_no_industry_basis_still_undetermined():
    r = _cls("某完全陌生品名", industry="")
    assert r["account_class"] == ac.CLASS_UNDETERMINED


# ── 2. 业态兜底 ──────────────────────────────────────────────────────────────
def test_trade_industry_fallback_makes_inventory_cost():
    """公司3 猩织光宠物食品商贸：940 个 SKU 不可能被关键词表穷举，必须业态兜底成成本。"""
    r = _cls("*饲料*鸡肉苹果饭罐头", industry="批发零售")
    assert r["account_class"] == ac.CLASS_COST
    assert r["matched_layer"].startswith("业态兜底")
    assert r["confidence"] == ac.CONF_MEDIUM


def test_service_industry_fallback_stays_undetermined():
    """服务型无存货可比照，未命中必须待核，不许推定成本。"""
    r = _cls("某未登记外购服务", industry="广告传媒")
    assert r["account_class"] == ac.CLASS_UNDETERMINED


# ── 3. 行业层优先于通用费用层 ────────────────────────────────────────────────
def test_ad_industry_core_cost_not_caught_by_generic_expense():
    r = _cls("*广告服务*广告发布费", industry="广告传媒")
    assert r["account_class"] == ac.CLASS_COST, "行业核心成本被通用费用表截走（已发生过的真事故）"
    # ★ 2026-10-02：服务形态的核心投入改走「服务轨道」，层名带后缀（服务轨道）；
    #   这里锁的是**层名前缀**而非整串 —— 防它哪天被通用费用表截走时换个陌生层名混过去。
    assert r["matched_layer"].startswith("行业核心投入")
    assert r["confidence"] == ac.CONF_HIGH


def test_某企业型广告业成本费用分离():
    lines = [{"goods": g} for g in (
        "*广告服务*广告发布费", "*现代服务*策划服务费", "*信息技术服务*信息服务费",
        "*现代服务*会展服务", "*生活服务*餐饮", "住宿费", "办公用品", "*物流辅助服务*运输费")]
    s = ac.classify_lines(lines, industry="广告传媒")
    cost = {i["goods"] for i in (s["cost_lines"] or [])}
    exp = {i["goods"] for i in (s["expense_lines"] or [])}
    pend = {i["goods"] for i in (s["pending_lines"] or [])}
    assert "*广告服务*广告发布费" in cost
    assert "*现代服务*策划服务费" in cost
    assert "*信息技术服务*信息服务费" in cost
    assert "*现代服务*会展服务" in cost
    assert {"*生活服务*餐饮", "住宿费", "办公用品"} <= exp
    assert "*物流辅助服务*运输费" in pend, "运输费无项目上下文必须待核"


# ── 4. 需上下文层 ────────────────────────────────────────────────────────────
def test_needs_context_words_are_undetermined_without_project():
    for probe in ("运输费", "水电费", "维修费", "租赁费", "会议费", "检测费", "装卸费"):
        r = _cls(probe, industry="广告传媒")
        assert r["account_class"] == ac.CLASS_UNDETERMINED, "%s 应落待核" % probe
        assert r["needs_context"] is True
        assert r["missing_material"]


def test_needs_context_goods_attribute_not_misread():
    """「软包装罐头」里的「包装」是商品属性不是采购口径 —— 真实验收踩到的坑。"""
    r = _cls("*饲料*珍致吞拿鱼肉泥（添加鸡肉）软包装罐头", industry="批发零售")
    assert r["matched_layer"] != "需上下文", "裸词「包装」误命中商品属性"


# ── 5. 硬排除 ────────────────────────────────────────────────────────────────
def test_capital_exclusion():
    r = _cls("服务器 设备 机器", industry="批发零售")
    assert r["account_class"] == ac.CLASS_CAPITAL


def test_prepaid_card_is_undetermined():
    r = _cls("京东e卡 预付卡", industry="批发零售")
    assert r["account_class"] == ac.CLASS_UNDETERMINED
    assert r["matched_layer"] == "预付卡"
    assert r["needs_context"] is True


def test_entertainment_terms_alone_are_not_expense():
    """「食品/酒水/礼品」单独出现既不能证成费用也不能证成成本（商贸进货含食品是常态）。"""
    for g in ("礼品 礼盒 酒水", "茶叶 食品", "香烟 食品"):
        r = _cls(g, industry="咨询服务")
        assert r["account_class"] == ac.CLASS_UNDETERMINED, "%s 不应直接判费用" % g


def test_entertainment_with_context_is_expense():
    r = _cls("业务招待 食品 茶叶", industry="批发零售")
    assert r["account_class"] == ac.CLASS_EXPENSE
    assert r["expense_sub"] == ac.EXPENSE_SUB_ADMIN


# ── 6. 可自证 ────────────────────────────────────────────────────────────────
def test_every_result_carries_confidence_and_evidence():
    for goods, kw in (("*广告服务*广告发布费", {"industry": "广告传媒"}),
                      ("办公用品", {"industry": "广告传媒"}),
                      ("运输费", {"industry": "广告传媒"}),
                      ("无头无尾", {"industry": "广告传媒"}),
                      ("随便什么", {})):
        r = _cls(goods, **kw)
        assert str(r.get("confidence") or "").strip(), goods
        assert str(r.get("evidence") or "").strip(), goods
        assert r["account_class"] in ac.ALLOWED_CLASSES


def test_classify_lines_sums_three_layers():
    lines = [{"goods": "*广告服务*广告发布费", "amount": 100},
             {"goods": "住宿费", "amount": 30},
             {"goods": "*物流辅助服务*运输费", "amount": 10}]
    s = ac.classify_lines(lines, industry="广告传媒")
    assert s["cost_lines"][0]["amount"] == 100
    assert s["expense_lines"][0]["amount"] == 30
    assert s["pending_lines"][0]["amount"] == 10
    assert abs(s["total_amount"] - 140.0) < 0.01
    assert s["missing_materials"]


# ── 7. 词表单一源（同名字表漂移曾致错判） ────────────────────────────────────
def test_named_tables_are_identical_across_modules():
    from engine import domain_analysis
    from engine import main_biz_cost
    a = list(main_biz_cost._MAJOR_EXPENSE_KWS)
    b = list(domain_analysis._MAJOR_EXPENSE_KWS)
    assert a == b, "两处同名 _MAJOR_EXPENSE_KWS 不一致 = 同一张发票两套结论（本轮修复的缺陷）"
    assert "住宿" in a and "运输" in a, "收敛后两表必须同时覆盖住宿与运输"


def test_authoritative_keywords_are_single_source():
    kws = ac.all_authoritative_keywords()
    assert len(kws) > 40
    assert len(set(kws)) == len(kws), "权威词表内部不得重复"


# ── 8. 管道侧唯一权威必须真的导入进来（曾因漏别名让整条分析崩在半路） ───────────
def test_pipeline_alias_is_imported():
    import engine.pipeline as pl
    assert hasattr(pl, '_account_classifier'), (
        'pipeline 引用了 _account_classifier 却没导入（真实验收踩到：一键分析整条链路 NameError）')
    assert pl._account_classifier is ac

# ── 9. 结构性证据层 / 命中层自动裁决（2026-10-02） ─────────────────────────
# 背景（本轮根因）：发票票面**没有会计科目字段**，此前只能靠关键词猜 + 业态兜底 ⇒
#   · 服务类外购（*信息技术服务*信息服务费）被「贸易型→存货」的业态兜底推成**主营业务成本**（错）；
#   · 运输/装卸/包装/搬运这些本该自动分辨的进项，因「需上下文层」整张表命中即待核
#     （两个分支 return 的都是 CLASS_UNDETERMINED，require_context 形同虚设）⇒ 全部"分不出来"。
# 新法：先按**结构性证据**（业务类型 / 税收分类编码 / 计量单位 / 开票项目大类）切「有无实物存货」，
#       再把「需上下文层」按会计事实拆成 存货采购支持费（准则明文 ⇒ 自动裁决）与 用途模糊项（⇒ 仍待核）。

#: 真账套实证（scripts/_probe_structural_fields.py，3620 行进项只读统计）
TC_FEED = "1030104010000000000"        # *饲料*宠物食品      → 货物
TC_ELEC = "1100101020200000000"        # *供电*电费          → 货物（电力属 VAT 货物税目）
TC_ADSL = "3040303010600000000"        # *广告服务*广告发布费 → 服务
TC_TRANSPORT = "3040409020000000000"   # *物流辅助服务*搬运服务 → 服务
TC_JDE = "6010000000000000000"         # *预付卡销售*京东E卡  → 预付卡


def test_structural_tax_code_goods_is_cost():
    """★ 第一刀生效：税收分类编码 <10/11> = 货物 ⇒ 构成存货 ⇒ 主营业务成本。"""
    r = _cls("*饲料*宠物食品", industry="批发零售", tax_code=TC_FEED, unit="件")
    assert r["account_class"] == ac.CLASS_COST
    assert "税收分类编码" in r["evidence"], "结论必须有可自证的结构性证据"
    assert r["matched_layer"] == "业态兜底（贸易型）" or r["matched_layer"].startswith("存货采购成本")


def test_structural_tax_code_service_is_cost_in_service_track():
    """服务类（编码 30）**不进**业态兜底的存货推定；行业核心投入命中仍可判成本（L4 铁律）。"""
    r = _cls("*广告服务*广告发布费", industry="广告传媒", tax_code=TC_ADSL)
    assert r["account_class"] == ac.CLASS_COST, "行业核心成本不得被服务轨道拒之门外（L4）"
    assert r["matched_layer"].startswith("行业核心投入")


def test_service_purchase_never_cost_by_business_type_fallback():
    """★ 回归锁：服务型外购（编码 30，无关键词命中）**绝不能**被业态兜底推成主营业务成本。

    旧缺陷：公司3 商贸业态下 `*信息技术服务*信息服务费` 未命中任何费用词，
    却因「贸易型 ⇒ 未列入费用口径的进项通常构成存货」被判成成本（虚增成本、压低毛利）。
    """
    r = _cls("*信息技术服务*信息服务费", industry="批发零售", tax_code="3040201990000000000")
    assert r["account_class"] != ac.CLASS_COST, (
        "服务类采购无存货可比照，不得由业态兜底推定为主营业务成本（本轮真缺陷）")
    assert r["account_class"] == ac.CLASS_UNDETERMINED


def test_inventory_support_is_cost_in_trade_industry():
    """★ 命中层自动裁决：准则明文的存货采购成本构成项（运输/装卸/搬运/包装）⇒ 判成本。"""
    r = _cls("*物流辅助服务*搬运服务", industry="商贸批发",
             tax_code=TC_TRANSPORT, unit="月")
    assert r["account_class"] == ac.CLASS_COST
    assert r["matched_layer"].startswith("存货采购成本")
    assert r["needs_context"] is True, "须带可复核 marks：销售环节运费应改计销售费用"


def test_inventory_support_not_cost_in_service_industry():
    """★ 业态闸门：服务型（广告/咨询/信息技术）**根本无存货**，运输费、搬运费一律是当期损益。"""
    r = _cls("*物流辅助服务*运输费", industry="广告传媒", tax_code=TC_TRANSPORT)
    assert r["account_class"] != ac.CLASS_COST, (
        "服务型业态无存货，运输/搬运费不得按存货采购成本判成主营业务成本（本轮真缺陷）")


def test_ambiguous_words_stay_undetermined():
    """保守不动：用途决定归属的词（水电/维修/租赁/检测/会议…）仍落待核，不许默认判成本。"""
    for probe in ("水电费", "维修费", "租赁费", "会议费", "检测费"):
        r = _cls(probe, industry="商贸批发", tax_code=TC_ELEC)
        assert r["account_class"] == ac.CLASS_UNDETERMINED, "%s 应落待核" % probe
        assert r["needs_context"] is True


def test_structural_kind_priority_and_table():
    """结构性定性：业务类型 > 税收编码 > 计量单位，且实证映射表合法。"""
    assert ac.structural_kind(TC_FEED, "件", "", "*饲料*宠物食品")[0] == ac.KIND_GOODS
    assert ac.structural_kind(TC_TRANSPORT, "月", "", "*物流辅助服务*搬运服务")[0] == ac.KIND_SERVICE
    assert ac.structural_kind("", "月", "", "")[0] == ac.KIND_SERVICE
    assert ac.structural_kind("", "", "", "完全无特征品名")[0] == ac.KIND_UNKNOWN
    # ★ 映射表只许登记「已实证」的前缀，且定性值必须落在允许集合内（防手滑加错）。
    allowed = {ac.KIND_GOODS, ac.KIND_SERVICE, ac.KIND_PREPAID, ac.KIND_AGENCY}
    assert ac.TAX_CODE_CLASSES, "实证映射表不得为空"
    for pre, (kind, label) in ac.TAX_CODE_CLASSES.items():
        assert kind in allowed, "前缀 %s 定性 %r 不在允许集合" % (pre, kind)
        assert label and label != pre


def test_fieldkit_tax_code_of_reads_the_real_column():
    """★ 死判据回归锁：真实列名是「税收**编码**」，不是「税收分类编码」。

    旧缺陷：全库 5 处（`_invoice_is_service_fee` / `_goods_is_service` / 等）读的是中文键
    「税收分类编码」⇒ 解析器从没写过这个键 ⇒ `tc.startswith("3")` 永远取假值，
    服务类发票判据静默失效（风险漏检）。
    """
    from engine import fieldkit
    assert fieldkit.tax_code_of({"税收编码": TC_FEED}) == TC_FEED, "必须能读真实列名「税收编码」"
    assert fieldkit.tax_code_of({"tax_code": TC_FEED}) == TC_FEED
    assert fieldkit.tax_code_of({"税收分类编码": TC_FEED}) == TC_FEED, "中文别名仍须兼容"
    assert fieldkit.unit_of({"计量单位": "罐"}) == "罐"
    assert fieldkit.biz_type_of({"biz_type": "库存商品_饲料"}) == "库存商品_饲料"


def test_classify_lines_forwards_structural_fields():
    """结构性证据必须由 classify_lines 从明细行带进权威层（否则第一刀无数据可用）。"""
    s = ac.classify_lines(
        [{"goods": "*物流辅助服务*搬运服务", "amount": 10, "tax_code": TC_TRANSPORT, "unit": "月"}],
        industry="商贸批发")
    cost = s["cost_lines"] or []
    assert len(cost) == 1 and cost[0]["account_class"] == ac.CLASS_COST
    assert "税收分类编码" in cost[0]["evidence"] or "计量单位" in cost[0]["evidence"], (
        "结论证据里看不到结构性证据 ⇒ 管道没把字段带下来（第一刀失效）")


def test_pipeline_agg_keeps_structural_fields():
    """管道品名小计必须保住结构性证据，否则报告层交给权威层时证据已断。"""
    import engine.pipeline as pl
    src = open(os.path.join("engine", "pipeline.py"), encoding="utf-8").read()
    assert 'for _sk, _getter in (("tax_code", _tc_of), ("unit", _u_of), ("biz_type", _bt_of))' in src, (
        "_agg_invs 未保住 tax_code/unit/biz_type（结构性证据到权威层的链路断了）")
    assert hasattr(pl, "_account_classifier")


# ══════════════════════════════════════════════════════════════════════════════
# 差旅出行层 + 行业核心投入词根匹配（2026-10-02，用户复核「按供应商」表暴露）
# ══════════════════════════════════════════════════════════════════════════════
class TestTravelExpenseLayer:
    """员工差旅出行票务属**期间费用**，与行业无关；不得被"行业核心投入"截走。

    实测两类误判（都出现在用户贴出的「主营成本·按供应商」表里）：
      · `*经纪代理服务*机票款` 105,883.20 元 → 撞上行业核心投入里过泛的「代理服务」
        被判成**主营业务成本**（那是"媒介代理"的意思，机票根本不是）；
      · `*运输服务*客运服务费/票价/国内机票款` 72,135.26 元 → 无层可落退成"待核"，
        而同一实物的「住宿服务住宿费」却在费用桶 —— 同一类支出两种归属。
    """

    CASES = ("经纪代理服务机票款", "经纪代理服务代订住宿费", "经纪代理服务代订房费",
             "经纪代理服务退票费", "运输服务客运服务费",
             "运输服务国内机票款；运输服务燃油附加费", "住宿服务住宿费", "旅游服务综合服务费")

    def test_travel_goods_are_expense(self):
        for g in self.CASES:
            r = ac.classify_line(g, industry="广告传媒")
            assert r["account_class"] == ac.CLASS_EXPENSE, f"{g} 未判为期间费用：{r}"
            assert r["matched_layer"] == "差旅出行", f"{g} 未走差旅出行层：{r['matched_layer']}"
            assert r["expense_sub"] == "差旅费", f"{g} 费用明细未落到差旅费：{r.get('expense_sub')}"

    def test_same_thing_same_bucket(self):
        """同一实物的"自营写法"与"代订写法"必须落同一个桶（不得一个成本一个待核）。"""
        pairs = [("住宿服务住宿费", "经纪代理服务代订住宿费"),
                 ("住宿服务房费", "经纪代理服务代订房费")]
        for a, b in pairs:
            ca = ac.classify_line(a, industry="广告传媒")["account_class"]
            cb = ac.classify_line(b, industry="广告传媒")["account_class"]
            assert ca == cb == ac.CLASS_EXPENSE, f"{a}/{b} 归属不一致：{ca} vs {cb}"

    def test_capital_and_prepaid_still_win(self):
        """差旅层不得抢在资本化/预付卡之前（加油卡仍须走预付卡、设备仍须资本化）。"""
        assert ac.classify_line("加油卡", industry="广告传媒")["account_class"] != ac.CLASS_EXPENSE
        assert ac.classify_line("移动通信设备三星 S25", industry="广告传媒")["account_class"] == ac.CLASS_CAPITAL

    def test_core_input_not_hurt_by_travel_layer(self):
        """反向锁：广告传媒的核心投入仍须判成本（差旅层不得误伤）。"""
        for g in ("广告服务广告发布费", "设计服务专业设计服务", "信息系统服务信息服务费"):
            assert ac.classify_line(g, industry="广告传媒")["account_class"] == ac.CLASS_COST, g

    def test_travel_kws_not_empty(self):
        assert ac.TRAVEL_KWS, "差旅出行词表为空（该层形同不存在）"


class TestCoreKeywordRootMatch:
    """行业核心投入按**词根**匹配：'代言费' 要能命中票面的「代言服务费」。

    实测：`core_inputs['广告传媒']` 登记的是「代言费」，票面是
    `*现代服务*代言服务费` → 逐字匹配不上 → 641,509.43 元的行业核心投入
    被扔进"待核"（该进成本的没进）。
    """

    def test_suffix_variant_matches(self):
        r = ac.classify_line("现代服务代言服务费", industry="广告传媒")
        assert r["account_class"] == ac.CLASS_COST, r
        assert r["matched_layer"] == "行业核心投入（服务轨道）"

    def test_root_helper_basics(self):
        assert ac._kw_root("代言费") == "代言"
        assert ac._kw_root("制作费") == "制作"
        # 泛词不得被词根化（否则"服务费"→"服务"会命中一切含"服务"的品名）
        assert ac._kw_root("服务费") == "服务费"
        assert ac._kw_root("费用") == "费用"
        assert ac._kw_root("咨询") == "咨询"


class TestCostInvoiceFilter:
    """`filter_cost_invoices` —— 成本明细只留归属为主营业务成本的发票（用户拍板）。"""

    def test_filters_out_travel_and_services(self):
        invs = [
            {"goods": "广告服务广告发布费", "amount": 1000, "seller": "A"},
            {"goods": "经纪代理服务机票款", "amount": 2000, "seller": "B"},
            {"goods": "现代服务咨询服务费", "amount": 3000, "seller": "C"},
            {"goods": "现代服务代言服务费", "amount": 4000, "seller": "D"},
        ]
        kept = ac.filter_cost_invoices(invs, industry="广告传媒")
        got = sorted(x["seller"] for x in kept)
        assert got == ["A", "D"], f"应只保留成本类（A/D），实际 {got}"

    def test_tolerates_bad_rows(self):
        assert ac.filter_cost_invoices(None, industry="广告传媒") == []
        assert ac.filter_cost_invoices([None, "x", {}, {"goods": ""}], industry="广告传媒") == []


# ══════════════════════════════════════════════════════════════════════════════
# 「直接相关性」判据（2026-10-02，用户给出的判定原则）
#   核心：区分成本与费用的**不是发票品名**，而是该支出是否直接服务于某个项目、
#   与该项目收入形成直接配比。同一张技术服务费：为客户项目 ⇒ 成本；内部 IT 维护 ⇒ 费用。
# ══════════════════════════════════════════════════════════════════════════════
class TestProjectDirectMatching:
    """项目/合同证据 ⇒ 主营业务成本（与收入直接配比）。"""

    def test_project_field_wins(self):
        r = ac.classify_line("现代服务技术服务费", industry="广告传媒",
                             project="某客户年度传播项目")
        assert r["account_class"] == ac.CLASS_COST
        assert r["matched_layer"] == "项目直接配比"

    def test_remark_with_project_indicator(self):
        r = ac.classify_line("信息系统服务服务费", industry="广告传媒",
                             remark="华美博扬项目 结项结算")
        assert r["account_class"] == ac.CLASS_COST, r
        assert "项目" in r["matched_kw"]

    def test_travel_linked_to_project_is_cost(self):
        """用户原则明说：项目相关的差旅费可计入主营业务成本。"""
        r = ac.classify_line("经纪代理服务机票款", industry="广告传媒",
                             remark="出差-某客户项目 行程单")
        assert r["account_class"] == ac.CLASS_COST, r

    def test_plain_remark_is_not_evidence(self):
        """反向红线：'见附件''款已付'这类普通备注**不是**项目证据。

        否则"有备注就算项目证据"会把几乎所有发票判成主营业务成本（严重误判）。
        """
        for nm in ("见附件", "款已付，对账无误", "对账无误", ""):
            assert ac._project_evidence(None, project="", remark=nm) == "", nm
        # 行为层面：无项目证据的机票仍按差旅归费用
        assert ac.classify_line("经纪代理服务机票款", industry="广告传媒",
                                remark="见附件")["account_class"] == ac.CLASS_EXPENSE

    def test_hard_exclusions_beat_project(self):
        """挂项目也不能把个人消费/预付卡/资本性算进成本。"""
        for g in ("预付卡购物卡", "职工个人消费支出", "房屋建筑物"):
            r = ac.classify_line(g, industry="广告传媒", project="某项目")
            assert r["account_class"] != ac.CLASS_COST, f"{g} 越过了硬排除层：{r}"


class TestSelfUseExpense:
    """自用 ⇒ 期间费用（用户举的第二个例子）。"""

    def test_internal_it_maintenance_is_expense(self):
        r = ac.classify_line("现代服务技术服务费", industry="广告传媒",
                             remark="系公司内部IT系统维护")
        assert r["account_class"] == ac.CLASS_EXPENSE, r
        assert r["matched_layer"] == "自用（无项目配比）"
        assert r["expense_sub"] == "管理费用"

    def test_project_evidence_beats_self_use(self):
        """项目证据与自用词同时出现时，按"直接配比"优先判成本。"""
        r = ac.classify_line("现代服务技术服务费", industry="广告传媒",
                             remark="华美博扬项目 内部结算")
        assert r["account_class"] == ac.CLASS_COST, r

    def test_no_remark_keeps_original_behaviour(self):
        """无备注时行为不变（不得因新增层改变原有判定）。"""
        assert ac.classify_line("广告服务广告发布费", industry="广告传媒")["account_class"] == ac.CLASS_COST
        assert ac.classify_line("经纪代理服务机票款", industry="广告传媒")["account_class"] == ac.CLASS_EXPENSE
        assert ac.classify_line("现代服务服务费", industry="广告传媒")["account_class"] == ac.CLASS_UNDETERMINED
