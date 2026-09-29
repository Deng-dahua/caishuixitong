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
