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
    assert r["matched_layer"] == "行业核心投入"
    assert r["confidence"] == ac.CONF_HIGH


def test_海更型广告业成本费用分离():
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
