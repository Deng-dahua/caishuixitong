# -*- coding: utf-8 -*-
"""法规**正文库**（``static/legal_library.json``）契约测试。

★★ 本文件守护的是一个**易被混淆**的区分：

   · ``config/legal_versions.json`` ＝ **版本登记**（「这部法现行有没有效」）
   · ``static/legal_library.json``  ＝ **正文内容**（「这条条文原文写了什么」）

  两者是**两件事**。混谈会造成「登记了版本 ⇒ 以为有正文」的**假绿** ——
  报告引用的法条在正文库里查不到，却因为"版本已登记"而无人发现。
  本测试 + 闸门 ``check_legal_text_coverage`` 锁定该区分。

判据（对应闸门 A~C）：
  A 覆盖率不得低于登记基线（改了引用却忘了补条文 ⇒ 退化）；
  B 每条正文含非空 law/article/content/source，且 (law, article) 不重复；
  C 库条数不得低于登记基线。

★ 反向验证**必须真调闸门**（同义反复的"断言自己构造的坏数据是坏的"不算验证）。
"""
from __future__ import annotations

import importlib.util
import json
import sys

import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "static" / "legal_library.json"
COV = ROOT / "config" / "legal_text_coverage.json"


def _load_audit():
    spec = importlib.util.spec_from_file_location(
        "_ac_legal_text", ROOT / "tools" / "audit_consistency.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)                              # noqa: SLF001
    return mod


def _lib() -> list:
    return json.loads(LIB.read_text(encoding="utf-8"))


def _cov() -> Dict[str, Any]:
    return json.loads(COV.read_text(encoding="utf-8"))


class TestLibraryContract:
    """真实正文库自身的契约（读盘断言）。"""

    def test_library_exists_and_nonempty(self):
        items = _lib()
        assert isinstance(items, list) and items, "法规正文库为空或格式错"

    def test_every_entry_has_four_fields(self):
        """每条正文必须含非空 law/article/content/source —— 缺一则无法溯源。"""
        bad = []
        for i, x in enumerate(_lib(), 1):
            for f in ("law", "article", "content", "source"):
                if not str(x.get(f) or "").strip():
                    bad.append((i, x.get("law"), f))
        assert not bad, "正文条目缺字段（序号, 法名, 缺失字段）：%s" % bad[:6]

    def test_no_duplicate_law_article(self):
        """同一 (law, article) 不得登记两次 —— 同一口径两处维护 = 事故。"""
        seen, dup = {}, []
        for i, x in enumerate(_lib(), 1):
            k = (str(x.get("law") or ""), str(x.get("article") or ""))
            if k in seen:
                dup.append((k, seen[k], i))
            else:
                seen[k] = i
        assert not dup, "正文库重复条目：%s" % dup[:5]

    def test_baseline_present(self):
        c = _cov()
        assert int(c.get("total_refs") or 0) > 0
        assert float(c.get("coverage") or 0) > 0.9, "覆盖率基线异常偏低：%s" % c

    def test_registered_baseline_matches_reality(self):
        """基线必须与现算一致 —— 否则闸门的"防退化"是空的。

        ★ 2026-10-16：改为调用**唯一实现** `engine.legal_coverage.compute`
          （原来自带第三份现算代码，与录入脚本/闸门各写一套 ⇒ 三处必然分叉）。
        """
        mod = _load_audit()
        c = _cov()
        assert len(_lib()) == int(c.get("library_size") or -1), \
            "库条数 %d ≠ 基线 %d（请重跑 scripts/_load_legal_texts.py）" % (
                len(_lib()), int(c.get("library_size") or -1))
        from engine.legal_coverage import compute
        now = compute(_lib())
        assert now["total_refs"] == int(c.get("total_refs") or -1), \
            "现算引用数 %d ≠ 基线 %d" % (now["total_refs"], int(c.get("total_refs") or -1))
        assert abs(float(now["coverage"]) - float(c["coverage"] or 0)) < 1e-6, \
            "现算覆盖率 %.4f ≠ 基线 %.4f" % (now["coverage"], float(c["coverage"] or 0))
        assert mod is not None


class TestGateClean:
    """闸门在**真实**工作区必须 0 命中。"""

    def test_text_coverage_gate_clean(self):
        mod = _load_audit()
        errs = [i for i in mod.check_legal_text_coverage() if i[0] == "ERROR"]
        assert not errs, "法规正文库闸门报错：%s" % errs[:4]

    def test_legal_basis_currency_gate_clean(self):
        mod = _load_audit()
        errs = [i for i in mod.check_redline_legal_basis_currency() if i[0] == "ERROR"]
        assert not errs, "红线法规时效闸门报错（引用了已废止法规）：%s" % errs[:4]


class TestGateReverse:
    """★ 反向验证：真调闸门，构造已知缺陷 ⇒ 必须报 ERROR。"""

    def _sandbox(self, monkeypatch, tmp: Path, mutate) -> Any:
        """把真实库复制进临时目录并施加 `mutate`，再让闸门在该 ROOT 上运行。"""
        (tmp / "static").mkdir(parents=True, exist_ok=True)
        (tmp / "config").mkdir(parents=True, exist_ok=True)
        lib = _lib()
        cov = _cov()
        mutate(lib, cov)
        (tmp / "static" / "legal_library.json").write_text(
            json.dumps(lib, ensure_ascii=False), encoding="utf-8")
        (tmp / "config" / "legal_text_coverage.json").write_text(
            json.dumps(cov, ensure_ascii=False), encoding="utf-8")
        mod = _load_audit()
        monkeypatch.setattr(mod, "ROOT", tmp, raising=True)
        return mod

    def test_gate_detects_missing_field(self, monkeypatch):
        """把某条 article 清空 ⇒ 闸门 B 段必报 ERROR。"""
        def mutate(lib, _cov):
            lib[3]["article"] = ""
        with tempfile.TemporaryDirectory() as td:
            mod = self._sandbox(monkeypatch, Path(td), mutate)
            errs = [i for i in mod.check_legal_text_coverage() if i[0] == "ERROR"]
            assert errs, "判据失真：清空 article 后闸门竟未报 ERROR"
            assert any("缺字段" in i[2] and "article" in i[2] for i in errs), errs[:3]
        monkeypatch.undo()
        assert not [i for i in _load_audit().check_legal_text_coverage() if i[0] == "ERROR"]

    def test_gate_detects_duplicate_entry(self, monkeypatch):
        """复制一条造成 (law, article) 重复 ⇒ 闸门 B 段必报 ERROR。"""
        def mutate(lib, _cov):
            lib.append(json.loads(json.dumps(lib[3])))
        with tempfile.TemporaryDirectory() as td:
            mod = self._sandbox(monkeypatch, Path(td), mutate)
            errs = [i for i in mod.check_legal_text_coverage() if i[0] == "ERROR"]
            assert any("重复登记" in i[2] for i in errs), errs[:3]
        monkeypatch.undo()

    def test_gate_detects_coverage_regression(self, monkeypatch):
        """**削弱数据**（把被引用那部法的条文改到不存在的法名下）⇒ 闸门 A 段必报 ERROR。

        ★★ 2026-10-16 修：原注入是「把基线抬到 1.0」—— 覆盖率现已达 **100%**，
          任何 ≤1 的基线都不可能被"低于" ⇒ **注入失效、测试空转**（这是我第一次写这道
          反向验证时踩到的坑：注入方式必须真能触发判据）。改为削弱数据。
        """
        from engine.legal_citation import split_citations
        from engine.tax_redlines import REDLINES
        first = ""
        for r in REDLINES:
            lb = (r or {}).get("legal_basis")
            lb = [lb] if isinstance(lb, str) else (lb or [])
            for it in lb:
                if isinstance(it, str) and it.strip():
                    got = split_citations(it)
                    if got:
                        first = got[0][0]
                    break
            if first:
                break
        assert first, "取不到被引用的法名 ⇒ 注入无从谈起"

        def mutate(lib, _cov):
            n = 0
            for x in lib:
                if first in str(x.get("law") or ""):
                    x["law"] = "（反向验证注入）不存在的法名"
                    n += 1
            assert n, "正文库里没有 %r 的条文 ⇒ 注入无效" % first

        with tempfile.TemporaryDirectory() as td:
            mod = self._sandbox(monkeypatch, Path(td), mutate)
            errs = [i for i in mod.check_legal_text_coverage() if i[0] == "ERROR"]
            assert any("退化" in i[2] for i in errs), errs[:3]
        monkeypatch.undo()

    def test_gate_detects_shrunk_library(self, monkeypatch):
        """库条目被误删（低于基线）⇒ 闸门 C 段必报 ERROR。"""
        def mutate(lib, _cov):
            lib.pop()
        with tempfile.TemporaryDirectory() as td:
            mod = self._sandbox(monkeypatch, Path(td), mutate)
            errs = [i for i in mod.check_legal_text_coverage() if i[0] == "ERROR"]
            assert any("疑误删" in i[2] for i in errs), errs[:3]
        monkeypatch.undo()

    def test_currency_gate_detects_expired_citation(self, monkeypatch):
        """★ 注入一条引用**已废止**法规的红线 ⇒ 时效闸门必报 ERROR。

        选《中华人民共和国进出口关税条例》（status=expired，2024-12-01 随《关税法》废止）。
        """
        import engine.tax_redlines as tr
        fake = [{"id": "RL-ZZ-999", "name": "测试用：引用已废止法规",
                 "legal_basis": ["《中华人民共和国进出口关税条例》第十八条"]}]
        monkeypatch.setattr(tr, "REDLINES", fake, raising=True)
        mod = _load_audit()
        errs = [i for i in mod.check_redline_legal_basis_currency() if i[0] == "ERROR"]
        assert errs, "判据失真：引用已废止法规竟未报 ERROR"
        assert any("已废止" in i[2] or "expired" in i[2] for i in errs), errs[:3]
        monkeypatch.undo()

    def test_currency_gate_scan_scope_covers_detectors(self):
        """闸门默认扫描范围必须含**检测器实现层**（防有人收窄范围 ⇒ 盲区复发）。"""
        mod = _load_audit()
        need = {"engine/tax_redlines.py", "engine/special_redline_detectors.py"}
        assert need <= set(mod._CURRENCY_SCAN_FILES), mod._CURRENCY_SCAN_FILES

    def test_currency_gate_scans_detector_policy_ref(self, tmp_path, monkeypatch):
        """★ 检测器实现层的 ``policy_ref`` 也必须被时效闸门覆盖（原盲区）。

        事故背景：闸门原只查 ``tax_redlines.legal_basis``，而
        ``special_redline_detectors.SPECS.policy_ref`` 是**另一份**政策引用 ⇒
        RL-FUND-004 / RL-SPT-005 / RL-INV-001 / RL-INV-003 / RL-VAT-009 曾长期引用失效法规。

        反向验证：把扫描文件列表指向一个**临时文件**（内含引用已废止法规），
        真调闸门 ⇒ **必须**报 ERROR。全程不触碰任何真实文件。
        """
        p = tmp_path / "fake_detector.py"
        p.write_text('X = {"policy_ref": "《现金管理暂行条例》第五条"}\n',
                     encoding="utf-8")
        mod = _load_audit()
        monkeypatch.setattr(mod, "_CURRENCY_SCAN_FILES", (str(p),), raising=True)
        errs = [i for i in mod.check_redline_legal_basis_currency() if i[0] == "ERROR"]
        assert any("现金管理暂行条例" in i[2] for i in errs), \
            "判据失真：检测器 policy_ref 引用已废止法规竟未报 ERROR"
        monkeypatch.undo()

    def test_currency_gate_ignores_bracketed_history_note(self):
        """留痕用「」标注的历史引用**不得**被判为引用（否则会误报）。

        ⚠ 判据必须**归一后精确比对**，不得用子串 —— 实测裸子串「增值税暂行条例」会
        误命中《中华人民共和国**土地**增值税暂行条例》（**现行有效的另一部法**）。
        扫描范围＝闸门实际扫描的全部政策引用文件（含检测器实现层）。
        """
        import re
        import sys
        sys.path.insert(0, str(ROOT))
        from engine.legal_version import canonical_law

        mod = _load_audit()
        expired = {"现金管理暂行条例", "进出口关税条例", "增值税暂行条例",
                   "增值税暂行条例实施细则"}
        hits = []
        for rel in mod._CURRENCY_SCAN_FILES:
            fp = Path(rel) if Path(rel).is_absolute() else (ROOT / rel)
            if not fp.exists():
                continue
            src = fp.read_text(encoding="utf-8")
            hits += [m.group(1) for m in re.finditer(r"《([^》]+)》", src)
                     if canonical_law(m.group(1)) in expired]
        assert not hits, "已废止法规出现在书名号内（会被判为正式引用）：%s" % hits[:3]

    def test_script_loads_and_is_idempotent(self):
        """录入脚本必须**幂等**：连续两次运行不得改变库内容。"""
        import subprocess
        import sys

        before = LIB.read_text(encoding="utf-8")
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "_load_legal_texts.py")],
                           capture_output=True, text=True, cwd=str(ROOT))
        assert r.returncode == 0, r.stderr[-400:]
        assert LIB.read_text(encoding="utf-8") == before, "录入脚本非幂等：重跑改变了库内容"
        assert "已存在" in r.stdout or "无新增" in r.stdout


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
