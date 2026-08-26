# -*- coding: utf-8 -*-
"""两税收入差异比对单元测试：直接构造 tax_declarations，验证抽取与判定逻辑。"""
import os, sys
BASE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(BASE)
sys.path.insert(0, PROJECT)

from engine.two_tax_income import run_two_tax_compare, _cit_income_from_row

# 构造与 pipeline 一致的两税申报表：VAT 用 declaration 字典(带 sales_amount)，CIT 用通用行(带 _declaration_type)
TAX_DECLS = [
    {"sales_amount": 600000.0, "sales_tax": 78000.0, "input_tax": 40000.0,
     "payable_tax": 38000.0, "period": "2026-01"},
    {"项目": "营业收入", "金额": 250000.0, "栏次": 1, "_declaration_type": "cit_declaration"},
    {"项目": "营业成本", "金额": 150000.0, "栏次": 2, "_declaration_type": "cit_declaration"},
]


def test_extract_cit_row():
    row = {"项目": "营业收入", "金额": 250000.0, "栏次": 1}
    assert _cit_income_from_row(row) == 250000.0
    row2 = {"项目": "营业收入", "本年金额": 520000.0, "上年金额": 400000.0}
    assert _cit_income_from_row(row2) == 520000.0
    row3 = {"项目": "营业成本", "金额": 999.0}
    assert _cit_income_from_row(row3) == 0.0  # 非收入标签 → 0


def test_vat_over_cit_high():
    r = run_two_tax_compare(tax_declarations=TAX_DECLS)
    assert r["available"], r
    m = r["metrics"]
    print("vat_sales=", m["vat_sales"], "cit_income=", m["cit_income"], "diff=", m["diff"], "diff_pct=", m["diff_pct"])
    assert m["vat_sales"] == 600000.0, m
    assert m["cit_income"] == 250000.0, m
    assert m["diff"] == 350000.0, m
    assert m["diff_pct"] == 140.0, m  # (600000-250000)/250000
    assert "显著高于" in r["verdict"], r["verdict"]
    assert any("高于" in s["signal"] for s in r["signals"]), r["signals"]


def test_consistent():
    decls = [
        {"sales_amount": 400000.0, "period": "2026-01"},
        {"项目": "营业收入", "金额": 400000.0, "_declaration_type": "cit_declaration"},
    ]
    r = run_two_tax_compare(tax_declarations=decls)
    assert r["available"]
    assert "基本一致" in r["verdict"], r["verdict"]
    assert m_diff(r) == 0.0


def test_only_one_side():
    decls = [{"sales_amount": 500000.0, "period": "2026-01"}]
    r = run_two_tax_compare(tax_declarations=decls)
    assert r["available"]
    assert r["metrics"]["only_one_side"] is True
    assert "仅取得增值税" in r["signals"][0]["signal"], r["signals"]


def test_no_data():
    r = run_two_tax_compare(tax_declarations=[])
    assert not r["available"]
    assert r["verdict"] == "未提供两税申报表"


def m_diff(r):
    return r["metrics"]["diff"]


if __name__ == "__main__":
    test_extract_cit_row()
    test_vat_over_cit_high()
    test_consistent()
    test_only_one_side()
    test_no_data()
    print("[OK] 两税收入差异比对 全部断言通过")
