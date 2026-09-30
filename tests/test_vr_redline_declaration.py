# -*- coding: utf-8 -*-
"""回归闸门：VR(已验证原子规则) → RL(红线) 的**显式归属声明**必须有效、且真实可触发。

背景（2026-09-29 #448 检出能力，根因修复）：
    RL-FUND-005「银行流水余额滚动关系不一致」被静态覆盖脚本判为"盲区（无任何数据路径）"，
    实际 VR009 就是它的检测器 —— 只是 finding 未声明 `redline_id`。
    ⇒「盲区条数」被系统性虚高：把"已实现但未声明归属"算成了"根本没实现"；
       运行期也只能靠 match_hints 模糊匹配碰运气（可能挂错或不挂）。
    同源缺陷经排查共 8 处（见本文件 DECLARED 表；其中三条扣除限额规则同属一条）。

本测试锁定三件事（缺一不可）：
    ① 认领的红线 id 必须真实存在（防拼错 id）；
    ② constituent_hits 的要件序号必须落在该红线 constituions 序号范围内（防填超范围序号）；
    ③ 触发时必须归位：`redline_engine._map_finding` 走 mode="declared"（而非模糊匹配）。
"""
import inspect
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import redline_engine          # noqa: E402
from engine import tax_redlines as tr      # noqa: E402
from engine import verified_rule_engine as vre  # noqa: E402

_RL_BY_ID = {r["id"]: r for r in tr.REDLINES}
_SPEC_BY_ID = {s["id"]: s for s in vre.VERIFIED_RULE_CATALOG}

# (VR id, 认领的红线 id) —— 2026-09-29 显式认领清单（同源缺陷修复）
DECLARED = [
    ("VR009", "RL-FUND-005"),   # 银行流水余额滚动关系不一致
    ("VR029", "RL-VAT-010"),    # 长期零申报或申报数据异常
    ("VR032", "RL-VAT-011"),    # 进项税额应转出未转出
    ("VR033", "RL-VAT-003"),    # 进销品名背离
    ("VR036", "RL-VAT-008"),    # 视同销售未计提销项税额
    ("VR038", "RL-CIT-007"),    # 业务招待费扣除超限
    ("VR039", "RL-CIT-007"),    # 广告费和业务宣传费扣除超限
    ("VR040", "RL-CIT-007"),    # 职工福利费扣除超限
    ("VR063", "RL-INC-003"),    # 预收账款、合同负债长期挂账
    ("VR067", "RL-OTH-006"),    # 销售折扣折让异常
    # ── 第二批（2026-09-29 #448 运行期软匹配→声明确认）：先查"是否已有 VR 仅缺归属" ──
    ("VR024", "RL-FUND-001"),   # 个人/个体户供应商客户交易核验
    ("VR025", "RL-FUND-002"),   # 资金回流与公私混同检测
    ("VR043", "RL-OTH-003"),    # 城建税及附加随增值税附征勾稽
    ("VR005", "RL-PAY-001"),    # 工资名册与社会保险人员范围差异
    ("VR037", "RL-CIT-001"),    # 关联交易价格偏离（转让定价探针）
    ("VR056", "RL-INC-002"),    # 公私混同发薪/私户支付薪酬
]


def _run(vid, data):
    return vre._SCANNERS[vid](data, _SPEC_BY_ID[vid])


# ───────────────────────── ① 静态：声明合法 ─────────────────────────
@pytest.mark.parametrize("vid,rid", DECLARED)
def test_declared_redline_exists(vid, rid):
    assert rid in _RL_BY_ID, f"{vid} 认领了不存在的红线 {rid}"


@pytest.mark.parametrize("vid,rid", DECLARED)
def test_declaration_present_and_index_in_range(vid, rid):
    """scanner 源码必须含 redline_id 声明 + constituent_hits，且要件序号在红线范围内。"""
    src = inspect.getsource(vre._SCANNERS[vid])
    assert f'"redline_id"] = "{rid}"' in src, f"{vid} 未声明 redline_id={rid}"
    idxs = [int(x) for x in re.findall(r'"index":\s*(\d+)', src)]
    assert idxs, f"{vid} 未附 constituent_hits（逐要件证据）"
    n = len(_RL_BY_ID[rid]["constituents"])
    for i in idxs:
        assert 1 <= i <= n, f"{vid} 要件序号 {i} 超出 {rid} 的要件数 {n}"


# ───────────────────────── ② 行为：真实触发并归位 ─────────────────────────
def _assert_declared(finding, rid):
    """触发结果必须带声明，且红线引擎必须走 declared 路径（不是模糊匹配）。"""
    assert finding.get("redline_id") == rid, f"发现未认领 {rid}：{finding.get('redline_id')}"
    hits = finding.get("constituent_hits") or []
    assert hits, "逐要件证据缺失"
    rl, info = redline_engine._map_finding(finding, available_materials=["银行流水", "记账凭证"])
    assert info.get("mode") == "declared", f"未走 declared 路径：{info}"
    assert rl and rl["id"] == rid


def test_vr009_bank_balance_rollforward():
    """银行流水余额滚动断裂（孤立断裂簇 + 两侧正确滚动）→ RL-FUND-005。"""
    rows = [
        {"statement_id": "S1", "date": "20250101", "balance": 1000, "credit": 0, "debit": 0, "tx_no": "1"},
        {"statement_id": "S1", "date": "20250102", "balance": 1100, "credit": 100, "debit": 0, "tx_no": "2"},
        {"statement_id": "S1", "date": "20250103", "balance": 1200, "credit": 100, "debit": 0, "tx_no": "3"},
        {"statement_id": "S1", "date": "20250104", "balance": 9999, "credit": 100, "debit": 0, "tx_no": "4"},  # 断裂①
        {"statement_id": "S1", "date": "20250105", "balance": 8888, "credit": 100, "debit": 0, "tx_no": "5"},  # 断裂②
        {"statement_id": "S1", "date": "20250106", "balance": 8988, "credit": 100, "debit": 0, "tx_no": "6"},
        {"statement_id": "S1", "date": "20250107", "balance": 9088, "credit": 100, "debit": 0, "tx_no": "7"},
    ]
    fs = _run("VR009", {"bank_txs": rows})
    assert fs, "应检出余额滚动断裂"
    _assert_declared(fs[0], "RL-FUND-005")
    assert fs[0]["constituent_hits"][0]["index"] == 1
    # 反例：余额完全正确 → 不得触发（零误报口径）
    ok = [dict(r, balance=1000 + i * 100) for i, r in enumerate(rows)]
    assert _run("VR009", {"bank_txs": ok}) == []


def test_vr029_long_zero_filing():
    decls = [{"period": f"2025{m:02d}", "sales_amount": 0, "payable_tax": 0} for m in range(1, 7)]
    fs = _run("VR029", {"tax_declarations": decls})
    assert fs, "6 期全零申报应触发"
    _assert_declared(fs[0], "RL-VAT-010")


def test_vr063_prepaid_aging():
    tb = [{"code": "2203", "name": "预收账款", "credit": 200000, "debit": 0}]
    fs = _run("VR063", {"trial_balance": tb, "vouchers": []})
    assert fs, "预收账款 20 万长期挂账应触发"
    _assert_declared(fs[0], "RL-INC-003")


def test_vr067_discount_anomaly():
    sal = [{"goods": "商品A", "amount": -60000, "buyer": "甲公司", "invoice_no": "X1",
            "summary": "销售折让"}]
    fs = _run("VR067", {"sal_invs": sal})
    assert fs, "折扣/折让 6 万（无红冲标识、无配平）应触发"
    _assert_declared(fs[0], "RL-OTH-006")


# ───────────────────────── 第二批行为测试 ─────────────────────────
def test_vr025_fund_recirculation():
    """企业↔个人大额整数转存转取 → RL-FUND-002。"""
    bank = [{"date": "20250101", "counterparty": "张三", "credit": 0, "debit": 600000,
             "summary": "转存"}]
    fs = _run("VR025", {"bank_txs": bank, "target_entity": {}})
    assert fs, "企业向个人大额整数转出应触发"
    _assert_declared(fs[0], "RL-FUND-002")
    assert fs[0]["constituent_hits"][0]["index"] == 1


def test_vr043_city_constr_tax():
    """实缴增值税存在、附加税申报字段缺失 → RL-OTH-003 要件①。"""
    decls = [{"period": "202501", "payable_tax": 100000}]
    fs = _run("VR043", {"declaration": decls})
    assert fs, "实缴增值税应随征附加税，差异无法核实应触发"
    _assert_declared(fs[0], "RL-OTH-003")
    assert fs[0]["constituent_hits"][0]["index"] == 1


def test_vr005_payroll_social():
    """工资名册与社保参保人数不符 → RL-PAY-001 要件①。"""
    salaries = [{"name": f"A{i}", "salary": 10000} for i in range(1, 7)]
    social = [{"name": f"B{i}", "base": 5000} for i in range(1, 6)]
    fs = _run("VR005", {"salaries": salaries, "social_security": social})
    assert fs, "工资名册 6 人、社保 5 人（无重叠）应触发"
    _assert_declared(fs[0], "RL-PAY-001")
    assert fs[0]["constituent_hits"][0]["index"] == 1


def test_vr037_related_party_pricing():
    """同品名同单位交易单价偏离 ≥40% → RL-CIT-001 要件③。"""
    sal = [
        {"goods": "A", "unit": "件", "price": 100, "buyer": "甲公司", "invoice_no": "I1"},
        {"goods": "A", "unit": "件", "price": 200, "buyer": "甲公司", "invoice_no": "I2"},
        {"goods": "A", "unit": "件", "price": 300, "buyer": "甲公司", "invoice_no": "I3"},
    ]
    fs = _run("VR037", {"sal_invs": sal, "pur_invs": [], "related_parties": [{"name": "甲公司"}]})
    assert fs, "3 笔同品名同单位单价离散应触发"
    _assert_declared(fs[0], "RL-CIT-001")
    assert fs[0]["constituent_hits"][0]["index"] == 3


def test_vr056_mixed_payroll():
    """员工个人账户直接支付薪酬 → RL-INC-002 要件①。"""
    salaries = [{"name": f"C{i}", "salary": 10000} for i in range(1, 7)]
    bank = [{"date": "20250101", "counterparty": "C1", "credit": 0, "debit": 5000,
             "summary": "工资"}]
    fs = _run("VR056", {"salaries": salaries, "bank_txs": bank})
    assert fs, "私户直接支付薪酬应触发"
    _assert_declared(fs[0], "RL-INC-002")
    assert fs[0]["constituent_hits"][0]["index"] == 1


def test_vr024_individual_counterparty():
    """个人客户累计金额异常巨大（非消费级）→ RL-FUND-001 要件①。"""
    sal = [{"goods": "设备", "amount": 5000000, "buyer": "张三", "invoice_no": "X1"}]
    fs = _run("VR024", {"sal_invs": sal, "pur_invs": []})
    assert fs, "个人客户累计 500 万应触发"
    declared = [f for f in fs if f.get("redline_id") == "RL-FUND-001"]
    assert declared, "风险发现应认领 RL-FUND-001"
    _assert_declared(declared[0], "RL-FUND-001")
    assert declared[0]["constituent_hits"][0]["index"] == 1


def test_run_redline_detection_declared_upgrades_matched():
    """回归闸门（2026-09-29 #448 接线升级）：红线配对 first-finder-wins，
    若模糊匹配（mode=matched）先到、声明型发现（mode=declared）后到同一红线，
    match_mode 必须升为 declared，并以声明型发现的逐要件命中覆盖 _DEFAULT_HIT_INDEX 兜底。

    若此断言被改回"matched"，则已声明归属的真实检测器虽接好，运行期仍被标成模糊匹配，
    ① 检出能力被静默低估 —— 这正是本轮要修的根因。
    """
    mats = ["银行流水（含个人账户）"]
    # 模糊匹配发现：无 redline_id，靠 match_hints（"公私混同"）命中 RL-INC-002 → mode=matched
    fuzzy = {
        "type": "个人账户收款核查",
        "domain": "收入",
        "level": "高风险",
        "detail": "个人账户收取经营性款项，公私混同，款项未入公司账未申报纳税",
        "description": "检出法定代表人个人账户收取经营性款项，公私混同",
    }
    # 声明型发现：VR56 已显式认领 RL-INC-002 → mode=declared（后到）
    declared = {
        "type": "公私混同发薪",
        "domain": "收入",
        "level": "高风险",
        "detail": "银行流水显示以员工个人账户直接支付的工资款项",
        "redline_id": "RL-INC-002",
        "constituent_hits": [{
            "index": 1,
            "evidence": "以员工个人账户直接支付的工资款项合计X元（六员个人账户存在经营性收款）",
        }],
    }
    out = redline_engine.run_redline_detection(
        [fuzzy, declared],
        engine_data=None,
        material_readiness={"provided": mats},
        pipeline_log=None,
    )
    susps = out.get("suspicions") or []
    inc002 = [s for s in susps if s.get("redline_id") == "RL-INC-002"]
    assert inc002, "RL-INC-002 应被触发"
    s = inc002[0]
    assert s["match_mode"] == "declared", (
        f"声明型发现后到应升为 declared，实际={s['match_mode']}")
    # 声明型发现的逐要件命中（index=1）应保留，而非仅兜底首序号
    hits = [c.get("index") for c in (s.get("argumentation") or {}).get("constituent_hits") or []]
    assert 1 in hits, f"声明型发现的逐要件命中应保留：{hits}"
