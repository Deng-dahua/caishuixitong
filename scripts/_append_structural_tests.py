# -*- coding: utf-8 -*-
"""把「结构性证据层 / 命中层自动裁决」的新回归测试追加到 tests/test_account_classifier.py。

★ 行尾纪律：追加前先把待追加块整体转成 CRLF 再写盘（该文件全文件 CRLF，混入 bare-LF 会被
  `audit_consistency` 的行尾规则判为缺陷）。
"""
import io
import os

TARGET = os.path.join("tests", "test_account_classifier.py")
SENTINEL = "# ── 9. 结构性证据层 / 命中层自动裁决（2026-10-02） ─────────────────────────"

BLOCK = '''
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
'''

with io.open(TARGET, "r", encoding="utf-8", newline="") as fh:
    body = fh.read()
if SENTINEL.strip() in body:
    raise SystemExit("测试块已存在，拒绝重复追加：%s" % SENTINEL)
if not body.endswith("\n"):
    body += "\r\n"
block = BLOCK.replace("\n", "\r\n")
with io.open(TARGET, "wb") as fh:
    fh.write((body + block).encode("utf-8"))
raw = open(TARGET, "rb").read()
print("written: CRLF=%d bare-LF=%d" % (raw.count(b"\r\n"),
                                       raw.count(b"\n") - raw.count(b"\r\n")))
