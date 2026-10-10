# -*- coding: utf-8 -*-
"""报告 JSON 载荷的**形状唯一性**与四个渲染出口的可用性（T-P0-8 回归）。

背景（实测，非设想）：`tax_risk.py::get_tax_risk_report()` 曾有两个 `return`
各自手写载荷字面量 —— 「无业务数据」分支 `summary` 是 **str**、中风险键名
`medium_risk_count`；「正常」分支 `summary` 是 **dict**、中风险键名 `mid_risk_count`。
四个渲染出口一律 `s.get(...)` ⇒ 本系统**唯一那个真实账套**（七张业务表全 0 行）
导出报告时 `AttributeError: 'str' object has no attribute 'get'` ⇒ **HTTP 500**
（`/api/tax-risk/report/download?format=pdf|docx|pptx` 全部不可用）。

本组锁住四件事：
  ① 两个分支的载荷**键集逐项相同**，`summary` 两处都是 dict 且键名唯一；
  ② 四个渲染出口对**无数据载荷**也能产出非空字节（"不再 500"的单元级证明）；
  ③ 无数据时不得把"缺失"渲染成 `0.00` / `None`（缺失≠0）；
  ④ PPTX 详情页不得**静默丢项**（每页第 7 项曾被 `continue` 吃掉）。

★ 隔离原则：不碰真实库/真实产物 —— `_report_payload` 是纯函数；
  渲染出口只在内存里生成字节并断言，不落盘。
"""
from __future__ import annotations

import ast
import io
import zipfile
from pathlib import Path

import pytest

import tax_risk as T

ROOT = Path(__file__).resolve().parents[1]

RENDERERS = ("_generate_report_html", "_download_pdf", "_download_docx", "_download_pptx")


def _bytes_of(out) -> bytes:
    """四个出口的返回类型并不统一：`_generate_report_html` 返回 **str**，其余返回 `Response`。

    ⚠ 这正是 T-P0-8 同类坑的一种（同一接口多种形状）——测试里显式归一化，
      不许用 `out.body` 一把梭猜。
    """
    if isinstance(out, bytes):
        return out
    if isinstance(out, str):
        return out.encode("utf-8")
    body = getattr(out, "body", None)
    if body is None:
        body = getattr(out, "content", b"")
    return body or b""


def _mk(results, available=True):
    """按唯一权威构造一份载荷（无数据 / 有 findings 两种）。"""
    return T._report_payload(
        company_id=1, period_start="2025-01", period_end="2025-06",
        industry="综合", industry_benchmark=T._industry_benchmark_block(None),
        summary=T._report_summary(results, 0, analysis_available=available),
        metrics=({"revenue": 1000.0, "cost": 600.0, "gross_margin_pct": 40.0,
                  "vat_payable": 30.0} if available else
                 {"revenue": None, "cost": None, "gross_margin_pct": None,
                  "vat_payable": None}),
        results=results, notice="" if available else T._NO_DATA_NOTICE,
        analysis_available=available,
    )


def _findings(n=2):
    return [{"item": "事项%02d" % i, "category": "经营实质", "risk_level": "中风险",
             "risk_score": 5, "detail": "d", "suggestion": "s"} for i in range(1, n + 1)]


class TestShapeSingleAuthority:
    def test_payload_keys_identical_across_branches(self):
        """两个分支的顶层键集必须逐项相同。"""
        assert set(_mk([], False)) == set(_mk(_findings(), True))

    def test_payload_keys_equal_declared_keys(self):
        assert set(_mk([], False)) == set(T._REPORT_PAYLOAD_KEYS)

    def test_summary_is_dict_and_keys_declared(self):
        for payload in (_mk([], False), _mk(_findings(), True)):
            assert isinstance(payload["summary"], dict)
            assert set(payload["summary"]) == set(T._SUMMARY_KEYS)

    def test_mid_risk_key_name_is_single(self):
        """中风险键名唯一：`mid_risk_count` 在、`medium_risk_count` 不在。"""
        s = _mk(_findings(), True)["summary"]
        assert "mid_risk_count" in s and "medium_risk_count" not in s

    def test_no_data_level_is_not_good(self):
        """没有数据 ≠ 良好：无数据时等级必须是 None（缺失≠0），不得默认成"良好"。"""
        assert _mk([], False)["summary"]["overall_risk_level"] is None
        assert _mk([], False)["analysis_available"] is False

    def test_get_tax_risk_report_returns_only_via_builder(self):
        """静态锁：`get_tax_risk_report()` 的每个 return 都必须调 `_report_payload()`。"""
        tree = ast.parse((ROOT / "tax_risk.py").read_text(encoding="utf-8"))
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "get_tax_risk_report")
        returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
        assert returns, "get_tax_risk_report 竟然没有 return"
        for r in returns:
            assert isinstance(r.value, ast.Call), "return 了手写字面量，形状会漂移"
            assert getattr(r.value.func, "id", "") == "_report_payload"


class TestRenderersNeverBreak:
    @pytest.mark.parametrize("fn_name", RENDERERS)
    def test_no_data_payload_renders(self, fn_name):
        """无数据载荷：四个出口都必须产出非空字节（改造前这里是 AttributeError）。"""
        body = _bytes_of(getattr(T, fn_name)(_mk([], False)))
        assert body, "%s 对无数据载荷产出为空" % fn_name

    @pytest.mark.parametrize("fn_name", RENDERERS)
    def test_full_payload_renders(self, fn_name):
        assert _bytes_of(getattr(T, fn_name)(_mk(_findings(), True)))

    def test_missing_not_rendered_as_zero_or_none(self):
        """无数据时：不得渲染成 `0.00` 或字符串 `None`，应为「—」。"""
        html = _bytes_of(T._generate_report_html(_mk([], False))).decode("utf-8", "replace")
        assert "None" not in html and "nan" not in html
        assert "0.00" not in html, "缺失被渲染成 0.00（缺失≠0）"
        assert "—" in html

    def test_no_data_reason_is_visible(self):
        """交付物必须写明"为何无法分析"，不得给用户一份无解释的空白报告。"""
        html = _bytes_of(T._generate_report_html(_mk([], False))).decode("utf-8", "replace")
        assert "暂无业务数据" in html


class TestPptxNoSilentDrop:
    def test_all_findings_present(self):
        """PPTX 详情页每页第 7 项曾被 `continue` 静默丢掉 ⇒ 逐项断言必须都在。"""
        n = 13
        many = [{"item": "唯一标记项%02d" % i, "category": "经营实质",
                 "risk_level": "中风险", "risk_score": 5,
                 "detail": "d", "suggestion": "s"} for i in range(1, n + 1)]
        body = _bytes_of(T._download_pptx(_mk(many, True)))
        zf = zipfile.ZipFile(io.BytesIO(body))
        xml = b"".join(zf.read(nm) for nm in sorted(zf.namelist())
                       if nm.startswith("ppt/slides/") and nm.endswith(".xml"))
        missing = [i for i in range(1, n + 1) if ("唯一标记项%02d" % i).encode() not in xml]
        assert not missing, "PPTX 丢了编号 %s" % missing


class TestHelpers:
    def test_money_and_pct_text(self):
        assert T._money_text(None) == "—"
        assert T._money_text("") == "—"
        assert T._money_text(1234.5) == "1,234.50"
        assert T._money_text("abc") == "—"
        assert T._pct_text(None) == "—"
        assert T._pct_text(40.0) == "40.0%"

    def test_level_text(self):
        assert T._level_text({"overall_risk_level": "高风险"}) == "高风险"
        assert T._level_text({"overall_risk_level": None}) == "无法评估"
        assert T._level_text({}) == "无法评估"

    def test_has_any_business_data_precedence(self):
        """`scalar() or 0 > 0` 会被解析成 `scalar() or (0>0)` —— 必须显式括号。"""
        src = (ROOT / "tax_risk.py").read_text(encoding="utf-8")
        assert "scalar() or 0) > 0" in src
