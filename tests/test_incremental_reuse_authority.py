# -*- coding: utf-8 -*-
"""增量复用「缓存版式判据」唯一权威的回归测试（2026-10-09）。

## 为什么要有这组测试

用户可见症状：**「资料没变，再点一次分析，还是要等很久重算」** ——
「增量复用」（资料+规则指纹未变 ⇒ 直接复用上次结果）**从未生效**。

根因（对真实产物实测，非推测）有两处，且都是"同一概念、两条链路各判一次"：

1. `main.py::analyze_tax_risk_docs_start` 用**硬编码报告名白名单**判定缓存可否复用，
   而那 4 个取值**全部出自 `config/report_identity.json` 的 `forbidden_aliases`
   （禁止别名表）** —— 判据只在"报告顶着禁止名称"时才可能成立。
   真实产出值是权威派生的「内部辅助分析工作底稿（风险检查文书式）」
   （`data/cache/last_analysis_cache.json` 与 `scripts/four_reports/company_1_full.json`
   实测一致）⇒ `_cached_report_ok` **恒为 False**。
   前端同一概念早已修好（`tax-doc-analysis.js::_isEnterpriseEdition`「★ 删除名称白名单」），
   后端当时没有收敛。

2. `_data_fp` **只写内存、不写磁盘**（`disk_cache` 构造时漏了它），而启动时
   `lifespan` 用磁盘缓存回填 `_last_analysis_cache` ⇒ 重启后 `_cached.get("_data_fp","")`
   恒为 `""` ⇒ `_cached_fp == _fp` 恒假 ⇒ **跨重启的增量复用从未生效**。

## 判据（与生产同口径，不另立标准）

- 权威函数 `enterprise_report.is_current_report_version()` 的行为：
  放行「按权威构造的真实结构」，拒绝带任一禁止别名 / 缺 `document_meta` /
  非法 `report_edition` / 空报告；
- **权威不得含报告名字面量**（改名要自动跟随）；
- `main.py` 主流程不得自行解释 `compilation_style`、必须调用权威；
- `audit_doctrine` 不得留报告名副本（第二出处）；
- 落盘缓存**必须**携带 `_data_fp`（否则跨重启复用再次失效）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _main_code(strip_comments: bool = True) -> str:
    """`main.py` 的**代码视图**（可选剔除行注释，镜像生产闸门口径）。"""
    out = []
    for ln in (ROOT / "main.py").read_text(encoding="utf-8").split("\n"):
        if strip_comments:
            if ln.strip().startswith("#"):
                continue
            out.append(re.sub(r"#.*$", "", ln))
        else:
            out.append(ln)
    return "\n".join(out)


class TestReuseAuthorityBehaviour:
    """权威函数的行为：放行正确结构、拒绝一切脏缓存。"""

    def _good(self) -> dict:
        from engine.audit_doctrine import DEFAULT_REPORT_EDITION
        from engine.enterprise_report import _doc_display_name
        from engine.report_identity import canonical_name
        return {
            "compilation_style": _doc_display_name(),
            "report_edition": DEFAULT_REPORT_EDITION,
            "document_meta": {"name": canonical_name()},
        }

    def test_accepts_real_structure(self):
        """★ 真实产出结构必须被放行 —— 否则增量复用再次恒不命中（本轮根因）。"""
        from engine.enterprise_report import is_current_report_version
        assert is_current_report_version(self._good()) is True

    def test_accepts_real_cached_product(self):
        """★ 直接拿**真实缓存产物**验判据（对真实产物取证，不构造样例）。"""
        import json
        p = ROOT / "data" / "cache" / "last_analysis_cache.json"
        if not p.exists():
            pytest.skip("本机无缓存产物，跳过真实产物断言")
        disk = json.loads(p.read_text(encoding="utf-8"))
        checked = 0
        for _cid, v in disk.items():
            rpt = (v.get("report") or {}).get("report") or {}
            cer = rpt.get("enterprise_readable_report") or {}
            if not cer:
                continue
            from engine.enterprise_report import is_current_report_version
            assert is_current_report_version(cer) is True, "cid=%s 被误判为脏缓存" % _cid
            checked += 1
        assert checked >= 1, "缓存里没有可校验的企业易读版报告"

    def test_rejects_every_forbidden_alias(self):
        """带**任一禁止别名**的报告不得被放行（历史白名单正是这些别名 ⇒ 恒假）。"""
        from engine.enterprise_report import _doc_display_name, is_current_report_version
        from engine.report_identity import forbidden_aliases
        cur = _doc_display_name()
        bad = [a for a in forbidden_aliases() if a != cur]
        assert bad, "禁止别名表为空，判据无从校验"
        for a in bad:
            assert is_current_report_version(dict(self._good(), compilation_style=a)) is False, \
                "禁止别名「%s」被放行" % a

    def test_rejects_missing_document_meta(self):
        from engine.enterprise_report import is_current_report_version
        g = {k: v for k, v in self._good().items() if k != "document_meta"}
        assert is_current_report_version(g) is False

    def test_rejects_invalid_edition(self):
        from engine.enterprise_report import is_current_report_version
        assert is_current_report_version(
            dict(self._good(), report_edition="税务风险检查文书式报告")) is False

    def test_rejects_empty_and_non_dict(self):
        from engine.enterprise_report import is_current_report_version
        assert is_current_report_version({}) is False
        assert is_current_report_version(None) is False
        assert is_current_report_version([]) is False

    def test_does_not_require_pyramid_edition(self):
        """`pyramid_edition` 是只读派生视图，真实产物里为 False ⇒ **不得**作为判据。"""
        from engine.enterprise_report import is_current_report_version
        assert is_current_report_version(dict(self._good(), pyramid_edition=False)) is True


class TestReuseAuthoritySingleSource:
    """「报告名」只能有一个出处；主流程不得自行解释版式字段。"""

    def test_authority_has_no_report_name_literal(self):
        """权威内部不得出现任何报告名字面量（含历史名与禁止别名）。

        ⚠ 必须**剔除 docstring**：权威函数的文档串里会引用"从前那段白名单长什么样"
          （举证需要），那是说明文字、不是判据。判据只审**代码**
          —— 这与生产闸门 `check_delete_exits` 本轮修掉的是同一个坑（把散文当代码审）。
        """
        from engine.report_identity import forbidden_aliases
        src = (ROOT / "engine" / "enterprise_report.py").read_text(encoding="utf-8")
        i = src.find("def is_current_report_version(")
        assert i > 0, "权威函数不存在"
        body = src[i:i + 4000]
        j = body.find("\ndef ", 10)          # 只取到下一个顶层函数为止
        if j > 0:
            body = body[:j]

        def _blank(m):
            return re.sub(r"[^\n]", " ", m.group(0))

        code = re.sub(r'"""(?:.|\n)*?"""', _blank, body)     # 去 docstring
        code = re.sub(r"'''(?:.|\n)*?'''", _blank, code)
        code = re.sub(r"#[^\n]*", _blank, code)              # 去行注释
        for a in forbidden_aliases():
            assert a not in code, "权威函数内硬编码了报告名「%s」" % a

    def test_main_delegates_and_does_not_interpret_style(self):
        code = _main_code()
        assert "is_current_report_version" in code, "main.py 未接权威（版式判据各写一份）"
        assert "compilation_style" not in code, \
            "main.py 主流程自行解释 compilation_style（历史缺陷即此处）"

    def test_audit_doctrine_has_no_style_copy(self):
        from engine.audit_doctrine import REPORT_EDITING_STANDARDS
        for name, meta in REPORT_EDITING_STANDARDS.items():
            assert "compilation_style" not in meta, \
                "`REPORT_EDITING_STANDARDS[%s]` 留有报告名副本（第二出处）" % name

    def test_doc_display_name_fallback_is_not_forbidden_alias(self):
        """`_doc_display_name()` 的取值不得是禁止别名（兜底曾用禁止名）。"""
        from engine.enterprise_report import _doc_display_name
        from engine.report_identity import forbidden_aliases
        assert _doc_display_name() not in forbidden_aliases()


class TestIncrementalShortcutWiring:
    """增量短路两个前提必须都在，缺一即"永远命中不了"。"""

    def test_disk_cache_persists_data_fingerprint(self):
        """落盘缓存必须携带 `_data_fp` —— 否则重启后 `_cached_fp == _fp` 恒假。"""
        code = _main_code()
        i = code.find("disk_cache = {")
        assert i > 0, "找不到 disk_cache 构造"
        blk = code[i:i + 900]
        assert '"_data_fp"' in blk, \
            "disk_cache 未落盘 `_data_fp` ⇒ 跨重启增量复用再次失效"

    def test_saved_payload_carries_both_keys(self):
        """内存缓存与磁盘缓存写的是同一份 payload（键必须成对出现）。"""
        code = _main_code()
        assert '_last_analysis_cache[company_id] = {' in code
        i = code.find("_last_analysis_cache[company_id] = {")
        blk = code[i:i + 400]
        assert '"_data_fp": _fp_now' in blk, "内存缓存未写 `_data_fp`"

    def test_shortcut_requires_all_three_conditions(self):
        """短路条件必须是 fp 相同 + 未过期 + 版式当前（三者与门）。"""
        code = _main_code()
        assert "if _cached_fp == _fp and _fresh and _cached_report_ok:" in code, \
            "增量短路条件被改动 —— 三个前提必须同时成立"


class TestProductionGatesPresent:
    """生产闸门必须在总控里注册（否则"改了没人管"）。"""

    def test_gate_registered(self):
        src = (ROOT / "tools" / "audit_consistency.py").read_text(encoding="utf-8")
        assert "check_report_version_reuse_authority" in src
        assert re.search(r"\+\s*check_report_version_reuse_authority\(\)", src), \
            "闸门未接入总控列表"

    def test_gate_green_on_current_tree(self):
        """当前工作树必须是绿的（红就该在提交前修，而不是把测试放宽）。"""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_ac_test", ROOT / "tools" / "audit_consistency.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.check_report_version_reuse_authority() == []
