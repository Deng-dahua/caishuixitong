# -*- coding: utf-8 -*-
"""META-SYSTEM-COMPLETENESS-AUDIT 的 P0 修复回归（2026-10-18）。

每条用例都对应一个**实测过**的缺陷，且尽量做成"可反向验证"的形式：
把修复撤掉，用例必须变红（否则判据是假的）。

覆盖：
  GAP-01 条号漂移 / 无条号
  GAP-02 法规时效判定（现行法不得判死、长名不被拆、不造虚构法名、幂等）
  GAP-03 出罪型规则（善意取得）与反证需真材料
  GAP-04 读取失败文件不算"已提供"
  GAP-05 合同金额参与勾稽
  GAP-06 顶额取不含税 / 备注按业务类型 / 错用税率
  GAP-07 DOCX 合同要素
  GAP-09 OCR 单 bytes / XML 发票
  GAP-10 失败原因可回执（状态机允许 failed→success）
"""
from __future__ import annotations

import io

import pytest


# ───────────────────────── GAP-02 法规时效 ─────────────────────────
class TestLawValidity:
    def test_current_law_is_not_dead(self):
        """现行《增值税法》不得被判废止 —— 旧实现返回 valid=False/ERROR。"""
        from engine.law_validity_checker import check_law_validity, is_deprecated
        t = "《中华人民共和国增值税法》第二十一条"
        r = check_law_validity(t)
        assert r["action"] == "noop", r
        assert r["alert"] == "OK", r
        assert is_deprecated(t) is False

    def test_long_name_not_split(self):
        """「土地增值税暂行条例」不得被「增值税暂行条例」吃掉（实测生成合成词）。"""
        from engine.law_validity_checker import apply_replacements
        t = "《中华人民共和国土地增值税暂行条例》第七条"
        out, applied = apply_replacements(t)
        assert out == t, out
        assert not applied

    def test_no_fictional_law(self):
        """「房产税暂行条例」是 current，不得被改名为并不存在的《房产税法》。"""
        from engine.law_validity_checker import apply_replacements
        t = "《房产税暂行条例》第二条"
        out, _ = apply_replacements(t)
        assert out == t, out
        assert "房产税法" not in out

    def test_replace_and_idempotent(self):
        from engine.law_validity_checker import apply_replacements
        out, applied = apply_replacements("《增值税暂行条例》第十九条")
        assert out == "《中华人民共和国增值税法》第十九条"
        assert applied
        out2, applied2 = apply_replacements(out)
        assert out2 == out and not applied2, "必须幂等"

    def test_no_double_prefix(self):
        """已带全称前缀时不得再叠一层「中华人民共和国中华人民共和国」。"""
        from engine.law_validity_checker import apply_replacements
        out, _ = apply_replacements("《中华人民共和国增值税法实施条例》第五条")
        assert "中华人民共和国中华人民共和国" not in out


# ───────────────────────── GAP-01 条号 ─────────────────────────
class TestLegalBasisArticles:
    def test_invoice_law_article_is_21(self):
        """虚开禁止是《发票管理办法》第二十一条；第二十二条是"税控装置"条款。"""
        from engine.tax_redlines import REDLINES
        bad = [r["id"] for r in REDLINES
               if "发票管理办法》第二十二条" in str(r.get("legal_basis"))]
        assert bad == [], "仍有规则把税控装置条款当虚开依据：%s" % bad

    def test_all_redlines_have_article_or_declared_normative(self):
        """每条红线的法定依据要么有条号，要么显式声明"规范性文件无条号结构"。"""
        from engine.legal_citation import split_citations
        from engine.tax_redlines import REDLINES
        missing = []
        for r in REDLINES:
            lb = r.get("legal_basis")
            items = [lb] if isinstance(lb, str) else list(lb or [])
            items = [x for x in items if isinstance(x, str) and x.strip()]
            cites = [c for it in items for c in split_citations(it)]
            if not cites:
                missing.append((r["id"], "无法解析引用"))
                continue
            if all(not c[1].strip() for c in cites):
                if not any(("无条文序号结构" in it or "按全文适用" in it) for it in items):
                    missing.append((r["id"], "; ".join(i[:40] for i in items)))
        assert missing == [], "无条号且未声明的规则：%s" % missing

    def test_legal_basis_never_nested_list(self):
        """补丁不得把 legal_basis 写成嵌套列表（首版踩过，会让解析整段失效）。"""
        from engine.tax_redlines import REDLINES
        bad = [r["id"] for r in REDLINES
               if isinstance(r.get("legal_basis"), list)
               and any(isinstance(x, list) for x in r["legal_basis"])]
        assert bad == [], bad


# ───────────────────────── GAP-03 出罪与反证 ─────────────────────────
class TestExculpatory:
    def test_good_faith_not_a_violation(self):
        """善意取得被命中 ⇒ 属"正当情形"，不得渲染成"疑似触碰红线"。"""
        from engine.argumentation import build_argumentation
        from engine.clue_chain import build_clue_chain
        from engine.evidence_chain import build_evidence_chain
        from engine.tax_redlines import get_redline
        rl = get_redline("RL-PTY-008")
        f = {"type": rl["name"], "level": "低风险", "score": 1,
             "detail": "供应商走逃，但交易真实、款项已付、货物已入库、不知情"}
        clue = build_clue_chain(f, rl, {})
        ev = build_evidence_chain(f, rl, ["进项发票", "采购合同", "入库单", "银行流水"], {})
        arg = build_argumentation(f, rl, clue, ev, {})
        assert "触碰" not in arg["verdict"], arg["verdict"]
        assert arg["conclusion_grade"] == "已排除", arg

    def test_exculpatory_rule_has_no_violation_constituents(self):
        from engine.tax_redlines import get_redline
        rl = get_redline("RL-PTY-008")
        assert rl.get("exculpatory") is True
        assert rl.get("violation_any_of") == []
        assert rl.get("indicator_constituents") == []

    def test_rebuttal_requires_real_material(self):
        """只在文本里写材料名 ⇒ 不算"反证已提交"（旧实现会因此错误出罪）。"""
        from engine.evidence_chain import build_evidence_chain
        from engine.tax_redlines import get_redline
        rl = get_redline("RL-VAT-001")
        base = {"type": "有销无进", "level": "待核验", "score": 0, "detail": "无对应进项"}
        f = dict(base, opposing_evidence="委托加工协议及委托方发料单、上期存货明细账")
        ev = build_evidence_chain(f, rl, ["销项发票", "进项发票"], {})
        reb = [e for e in ev["elements"] if e["role"] == "反证"]
        assert reb and all(e["status"] != "已提交" for e in reb), reb

    def test_all_redlines_have_evidence_chain(self):
        from engine.tax_redlines import REDLINES
        missing = [r["id"] for r in REDLINES if not r.get("evidence_chain")]
        assert missing == [], "无证据链（反证机制不可达）：%s" % missing


# ───────────────────────── GAP-04 证据可用性 ─────────────────────────
class TestEvidenceAvailability:
    def test_read_failure_not_counted_as_provided(self):
        """"文件在盘里"不等于"证据已具备"：解析失败的资料不计入已提供。"""
        from engine.enterprise_report import _doc_covered_categories
        data = {
            "file_results": [{"file": "合同.docx", "type": "contract", "_rows": []}],
            "read_failures": ["合同.docx"],
        }
        cov = _doc_covered_categories(data)
        assert "合同文件" not in cov, cov

    def test_parsed_contract_counted(self):
        from engine.enterprise_report import _doc_covered_categories
        data = {
            "file_results": [{"file": "合同.docx", "type": "contract",
                              "_rows": [{"amount": 1}]}],
            "read_failures": [],
        }
        assert "合同文件" in _doc_covered_categories(data)

    def test_evidence_row_located(self):
        """证据行必须能回链到"文件 + 表内行号"。"""
        from engine.pipeline import _locate_evidence_rows
        rows = [{"source": "可疑发票", "ref_id": "INV-1", "amount": 100}]
        frs = [{"file": "取票.xlsx", "_header_row": 1,
                "_rows": [{"inv_no": "INV-1", "amount": 100}]}]
        out = _locate_evidence_rows(rows, frs)
        assert out[0]["locate_status"] == "located"
        assert out[0]["source_file"] == "取票.xlsx"
        assert out[0]["row_index"] == 2

    def test_evidence_row_not_found_is_reported(self):
        """定位不到必须显式标 not_found（不静默留空）。"""
        from engine.pipeline import _locate_evidence_rows
        out = _locate_evidence_rows([{"source": "x", "ref_id": "NOPE"}],
                                    [{"file": "a.xlsx", "_rows": [{"inv_no": "B"}]}])
        assert out[0]["locate_status"] == "not_found"


# ───────────────────────── GAP-05/06/07 单证与比对 ─────────────────────────
class TestInvoiceAndContract:
    def test_limit_uses_amount_without_tax(self):
        """顶额判定取**不含税**金额（旧实现取价税合计 ⇒ 该抓的档位反而不命中）。"""
        from engine.invoice_limit_detector import detect_invoice_limit_top
        inv = [{"invoice_no": "A", "buyer": "X", "amount": 9999.99,
                "total": 11299.98, "goods": "棉布"},
               {"invoice_no": "B", "buyer": "X", "amount": 9999999.99,
                "total": 11299999.98, "goods": "棉布"}]
        assert detect_invoice_limit_top(inv, {}), "不含税顶额必须命中"

    def test_limit_ignores_non_top_amount(self):
        from engine.invoice_limit_detector import detect_invoice_limit_top
        inv = [{"invoice_no": "C", "buyer": "Y", "amount": 8849.55, "total": 9999.99}]
        assert detect_invoice_limit_top(inv, {}) == []

    def test_misused_rate_detected(self):
        from engine.invoice_rate_detector import detect_misused_rate
        invs = [{"invoice_no": "A1", "goods": "钢材", "tax_rate": "6%", "amount": 1000},
                {"invoice_no": "A2", "goods": "建筑服务", "tax_rate": "10%", "amount": 2000},
                {"invoice_no": "A3", "goods": "棉布", "tax_rate": "13%", "amount": 3000}]
        r = detect_misused_rate(invs, {})
        assert r and r[0]["observed_metrics"]["mismatch_count"] == 2, r
        assert "A1" in [s["inv_no"] for s in r[0]["observed_metrics"]["samples"]]

    def test_unknown_goods_not_judged(self):
        """品名未纳入映射表 ⇒ 不判（宁可漏判不可误伤），且必须计数说明。"""
        from engine.invoice_rate_detector import detect_misused_rate
        invs = [{"invoice_no": "Z", "goods": "未知品名XYZ", "tax_rate": "9%", "amount": 1}]
        assert detect_misused_rate(invs, {}) == []

    def test_remark_only_for_statutory_types(self):
        """备注栏只对法定必须备注的业务类型判（货物销售不纳入分母）。"""
        from engine.domain_analysis import _domain_advanced_rules
        invs = [{"invoice_no": "A1", "goods": "建筑服务", "remark": "", "amount": 1},
                {"invoice_no": "A2", "goods": "钢材", "remark": "", "amount": 1}]
        r = _domain_advanced_rules([], invs, [], [], [], [], [])
        hit = [x for x in r if "备注" in x["type"]]
        assert hit, r
        m = hit[0]["observed_metrics"]
        assert m["required_total"] == 1, m          # 只有建筑服务进分母
        assert m["missing_invoice_nos"] == ["A1"]

    def test_docx_contract_elements(self):
        from engine.contract_parser import parse_contract_text
        r = parse_contract_text([
            "建设工程施工合同",
            "甲方（发包方）：甲公司",
            "乙方（承包方）：乙公司",
            "第二条 合同价款：人民币伍佰万元整（￥5,000,000.00）。",
            "签订日期：2026年1月10日",
        ], "c.docx")
        row = r["rows"][0]
        assert row["amount"] == 5000000.0
        assert row["party_a"] == "甲公司" and row["party_b"] == "乙公司"
        assert row["sign_date"] == "2026-01-10"

    def test_contract_summary_missing_is_none(self):
        """缺失≠0：没有合同 ⇒ total_amount 为 None。"""
        from engine.pipeline import _contract_summary
        assert _contract_summary([])["total_amount"] is None
        assert _contract_summary([{"amount": 100}])["total_amount"] == 100


# ───────────────────────── GAP-09 OCR / XML ─────────────────────────
class TestOcrXml:
    def test_ocr_accepts_single_bytes(self):
        """`_ocr_png_bytes` 必须接受**单个 bytes**（旧实现按 list 遍历 ⇒ 遍历每个 int ⇒ TypeError）。"""
        import inspect
        import main
        src = inspect.getsource(main._ocr_png_bytes)
        assert "isinstance(images, (bytes, bytearray, memoryview))" in src

    def test_xml_invoice_parsed(self, tmp_path):
        from engine.pipeline import _parse_xml_invoice
        p = tmp_path / "a.xml"
        p.write_text(
            '<?xml version="1.0"?><Invoice><Header><InvoiceNo>NO1</InvoiceNo>'
            "<InvoiceDate>2026-04-01</InvoiceDate></Header>"
            "<Seller><Name>甲</Name></Seller><Buyer><Name>乙</Name></Buyer>"
            "<Items><Item><Name>棉布</Name><Amount>100</Amount><Rate>13%</Rate></Item></Items>"
            "<Total><AmountWithTax>113</AmountWithTax></Total></Invoice>", encoding="utf-8")
        r = _parse_xml_invoice(str(p), "a.xml")
        row = r["rows"][0]
        assert row["invoice_no"] == "NO1" and row["amount"] == 100.0
        assert row["seller"] == "甲" and row["buyer"] == "乙" and row["goods"] == "棉布"


# ───────────────────────── GAP-10 状态机 ─────────────────────────
class TestParseStatusFlow:
    def test_failed_can_become_success(self):
        """重解析成功必须能置 success（旧表不允许 ⇒ 真实失败原因被状态机错误覆盖）。"""
        from engine.document_types import PARSE_STATUS_FLOW
        assert "success" in PARSE_STATUS_FLOW["failed"]

    def test_transition_allows_reparse(self):
        from engine.document_types import can_parse_transition
        assert can_parse_transition("failed", "success") is True
        assert can_parse_transition("pending", "success") is False


# ───────────────────────── GAP-11 跨表勾稽 ─────────────────────────
class TestCrossStatement:
    def _run(self, income, decls):
        from engine.cross_statement_check import run_cross_statement_check
        return run_cross_statement_check(income_stmt=income, tax_declarations=decls)

    def test_difference_flagged(self):
        r = self._run({"profit_total": 450000},
                      [{"profit_total": 150000, "_declaration_type": "cit"}])
        assert r["status"] == "compared" and r["findings"]
        assert abs(r["diff"]) == 300000.0

    def test_consistent_not_flagged(self):
        r = self._run({"profit_total": 450000},
                      [{"profit_total": 452000, "_declaration_type": "cit"}])
        assert r["status"] == "compared" and not r["findings"]

    def test_one_sided_not_concluded(self):
        r = self._run({"profit_total": 450000}, [])
        assert r["status"] == "one_sided" and not r["findings"]

    def test_unavailable(self):
        r = self._run({}, [])
        assert r["status"] == "unavailable" and r["book_profit_total"] is None
