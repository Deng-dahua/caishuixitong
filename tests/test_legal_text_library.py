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
        """基线必须与现算一致 —— 否则闸门的"防退化"是空的。"""
        mod = _load_audit()
        c = _cov()
        assert len(_lib()) == int(c.get("library_size") or -1), \
            "库条数 %d ≠ 基线 %d（请重跑 scripts/_load_legal_texts.py）" % (
                len(_lib()), int(c.get("library_size") or -1))
        # 现算覆盖率（与闸门同口径）
        import re
        import sys
        sys.path.insert(0, str(ROOT))
        from engine.legal_citation import split_citation
        from engine.legal_version import canonical_law
        from engine.tax_redlines import REDLINES

        def _an(a):
            return re.sub(r"\s+", "", str(a or ""))

        idx = {}
        for x in _lib():
            idx.setdefault(canonical_law(x["law"]), set()).add(_an(x["article"]))
        tot = hit = 0
        for r in REDLINES:
            lb = (r or {}).get("legal_basis")
            if isinstance(lb, str):
                lb = [lb]
            for it in (lb or []):
                if not isinstance(it, str) or not it.strip():
                    continue
                law, art, _, _ = split_citation(it)
                tot += 1
                arts = idx.get(canonical_law(law))
                if arts and (not art or any(a.startswith(_an(art)) or _an(art).startswith(a)
                                            for a in arts if a)):
                    hit += 1
        assert abs((hit / tot) - float(c["coverage"])) < 0.002, \
            "现算覆盖率 %.4f ≠ 基线 %.4f" % (hit / tot, float(c["coverage"]))
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
        """把基线抬高（= 红线引用了正文库没有的条文）⇒ 闸门 A 段必报 ERROR。"""
        def mutate(_lib, cov):
            cov["coverage"] = 1.0                  # 现实是 0.9951 ⇒ 必然退化
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

    def test_currency_gate_ignores_bracketed_history_note(self):
        """留痕用「」标注的历史引用**不得**被判为引用（否则会误报）。

        ⚠ 判据必须**归一后精确比对**，不得用子串 —— 实测裸子串「增值税暂行条例」会
        误命中《中华人民共和国**土地**增值税暂行条例》（**现行有效的另一部法**）。
        """
        import re
        import sys
        sys.path.insert(0, str(ROOT))
        from engine.legal_version import canonical_law

        src = (ROOT / "engine" / "tax_redlines.py").read_text(encoding="utf-8")
        expired = {"现金管理暂行条例", "进出口关税条例", "增值税暂行条例",
                   "增值税暂行条例实施细则"}
        hits = [m.group(1) for m in re.finditer(r"《([^》]+)》", src)
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
