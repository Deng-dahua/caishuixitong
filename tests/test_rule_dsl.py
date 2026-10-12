# -*- coding: utf-8 -*-
"""规则条件 DSL（`engine/rule_dsl.py`）回归锁 —— T-6「规则外置」（2026-10-13）。

**为什么要有这组测试**：
T-6 裁定「三层渐进」（阈值类已外置 / 条件类可外置 / 要件化类留 Python）。本轮新建
条件 DSL 解释器后，实测瓶颈**不在 DSL 而在字段取数口径**（538 个字段无口径）。
本组锁住解释器本身的正确性 —— 尤其**三值逻辑**，因为它是本项目「缺失≠0」铁律的落点：
若字段缺失默认 False，等于把「没查」说成「没问题」。

本组七类：
  ① 解析：实测语法面（比较/算术/函数/and-or-not/布尔字面量/`params.X`）
  ② **三值逻辑**：缺字段 / 参数待核 / 除零 ⇒ UNKNOWN，**绝不是 False**
  ③ Kleene 语义与短路
  ④ 白名单：未登记函数、未登记否定形容词 ⇒ 报错（不猜语义）
  ⑤ 有意不支持：集合语义 / 时间窗 ⇒ `UnsupportedSyntax`（留 Python）
  ⑥ 可外置判定 `externalizable()`
  ⑦ 反向验证：破坏三值逻辑 ⇒ 断言必红

★ 隔离原则：纯函数 + 合成绑定，不落盘、不碰真实库。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

from engine.rule_dsl import (ALLOWED_FUNCS, NEG_ADJ, DslError,  # noqa: E402
                            UnsupportedSyntax, compile_expr, evaluate,
                            externalizable)

_CAND = ("config/rulelist_v1.json", "config/rulelist_v11.json",
         "config/rulelist_v12.json")


def ev(logic, variables=None, params=None):
    return evaluate(compile_expr(logic), variables or {}, params or {})


def ev_reasons(logic, variables=None, params=None):
    sink = []
    evaluate(compile_expr(logic), variables or {}, params or {}, sink)
    return sink


class TestParsing:
    """① 实测语法面。"""

    def test_simple_comparison(self):
        assert ev("a > 1", {"a": 2}) is True
        assert ev("a > 1", {"a": 0}) is False

    def test_single_equals_means_double_equals(self):
        """候选库把 `=` 写作 `==`（实测 140 处）。"""
        assert ev("a = 0", {"a": 0}) is True
        assert ev("a == 0", {"a": 0}) is True

    def test_arithmetic_precedence(self):
        assert ev("1 + 2 * 3 = 7", {}) is True

    def test_abs_and_min(self):
        assert ev("abs(a - b) / b > params.v", {"a": 11, "b": 10}, {"v": 0.05}) is True
        assert ev("min(a, b) > 0", {"a": 3, "b": 5}) is True

    def test_boolean_literals(self):
        """`true`/`false` 是字面量，**不是变量**（实测 45+18 处；当变量会被误判缺字段）。"""
        assert ev("flag = false", {"flag": False}) is True
        assert ev("flag = true", {"flag": True}) is True
        assert ev("flag = false", {}) is None, "true/false 不该被当成必然缺字段"

    def test_identifier_may_contain_ampersand(self):
        """`R&D_expense` 是合法标识符（候选库实测 5 处）。"""
        r = compile_expr("R&D_expense > 0")
        assert "R&D_expense" in r.identifiers
        assert ev("R&D_expense > 0", {"R&D_expense": 1}) is True

    def test_params_reference_becomes_param_node(self):
        """`params.X` 必须解析为参数引用（曾因未改写 AST 而被误判"字段缺失"）。"""
        r = compile_expr("a > params.t")
        assert r.params_used == {"t"}
        assert r.identifiers == {"a"}

    def test_and_or_not(self):
        assert ev("a > 0 and b > 0", {"a": 1, "b": 1}) is True
        assert ev("a > 0 or b > 0", {"a": 0, "b": 1}) is True
        assert ev("not (a > 0)", {"a": 0}) is True


class TestTriValueLogic:
    """② 三值逻辑 —— 本模块最关键的语义（缺失≠0）。"""

    def test_missing_field_is_unknown_not_false(self):
        assert ev("a > 1", {}) is None, "缺字段必须 UNKNOWN，绝不当 False"

    def test_null_field_is_unknown(self):
        assert ev("a > 1", {"a": None}) is None

    def test_unknown_reason_is_reported(self):
        rs = ev_reasons("a > 1", {})
        assert any("字段未取到值" in x for x in rs), rs

    def test_param_not_registered_is_unknown(self):
        assert ev("a > params.t", {"a": 5}, {}) is None
        assert any("参数未登记" in x for x in ev_reasons("a > params.t", {"a": 5}, {}))

    def test_param_null_pending_is_unknown(self):
        """★ 参数登记为 null（如地区参数待属地确认）⇒ UNKNOWN，**绝不当 0**。"""
        assert ev("a > params.t", {"a": 5}, {"t": None}) is None
        assert any("待核" in x for x in ev_reasons("a > params.t", {"a": 5}, {"t": None}))

    def test_division_by_zero_is_unknown(self):
        """★ 除零 ⇒ UNKNOWN（不返回 0、不抛异常）。"""
        assert ev("a / b > 1", {"a": 5, "b": 0}) is None
        assert any("除数为零" in x for x in ev_reasons("a / b > 1", {"a": 5, "b": 0}))

    def test_not_unknown_is_unknown(self):
        assert ev("not (a > 1)", {}) is None

    def test_unknown_propagates_through_arithmetic_and_functions(self):
        assert ev("abs(a - b) > 1", {"a": 5}) is None
        assert ev("min(a, b) > 1", {"b": 2}) is None


class TestKleeneAndShortCircuit:
    """③ Kleene 语义与短路。"""

    def test_false_and_unknown_is_false(self):
        """一侧为假即可判假（短路），无须知道另一侧。"""
        assert ev("a > 0 and b > 0", {"a": 0}) is False

    def test_true_or_unknown_is_true(self):
        assert ev("a > 0 or b > 0", {"a": 1}) is True

    def test_false_or_unknown_is_unknown(self):
        assert ev("a > 0 or b > 0", {"a": 0}) is None

    def test_true_and_unknown_is_unknown(self):
        assert ev("a > 0 and b > 0", {"a": 1}) is None


class TestWhitelist:
    """④ 白名单：未登记者报错，不猜语义。"""

    def test_unknown_function_rejected(self):
        with pytest.raises(DslError) as e:
            compile_expr("sqrt(a) > 1")
        assert "未登记的函数" in str(e.value)

    def test_unknown_negation_adjective_rejected(self):
        """`X not <形容词>`：仅 `NEG_ADJ` 白名单内支持；其余报错（不猜）。"""
        with pytest.raises(DslError):
            compile_expr("method not wonderful")

    def test_declared_negation_adjectives_supported(self):
        for adj in NEG_ADJ:
            assert ev("cond not %s" % adj, {"cond": False}) is True

    def test_whitelist_nonempty(self):
        assert ALLOWED_FUNCS and NEG_ADJ


class TestIntentionallyUnsupported:
    """⑤ 有意不支持（留 Python，属要件化类）。"""

    def test_set_membership_not_in(self):
        with pytest.raises(UnsupportedSyntax):
            compile_expr("a not in b")

    def test_time_window_for_loop(self):
        with pytest.raises(UnsupportedSyntax):
            compile_expr("a > 0 for n months")

    def test_while_loop(self):
        with pytest.raises(UnsupportedSyntax):
            compile_expr("while a > 0")

    def test_unsupported_is_subclass_of_dsl_error(self):
        assert issubclass(UnsupportedSyntax, DslError)


class TestExternalizable:
    """⑥ 可外置判定（T-6 验收口径）。"""

    def test_ok_when_vars_and_params_known(self):
        ok, why = externalizable("a - b > params.t", {"a", "b"}, {"t"})
        assert ok, why

    def test_blocked_by_unknown_var(self):
        ok, why = externalizable("a - b > 0", {"a"}, set())
        assert not ok and "字段无取数口径" in why

    def test_blocked_by_unknown_param(self):
        ok, why = externalizable("a > params.t", {"a"}, set())
        assert not ok and "参数未登记" in why

    def test_blocked_when_unsupported_syntax(self):
        ok, why = externalizable("a not in b", {"a", "b"}, set())
        assert not ok and "超表达力" in why


class TestRealCandidateLibrary:
    """⑦ 真实候选库：解析率与边界登记必须对得上（防悄悄漂移）。"""

    def _rules(self):
        out = []
        for rel in _CAND:
            out += json.loads((ROOT / rel).read_text(encoding="utf-8"))["rules"]
        return out

    def test_all_rules_parse_or_are_declared_unsupported(self):
        """★ 每条候选：要么可解析，要么**明确**属"有意不支持" —— 不得有语法错。"""
        bad = []
        for r in self._rules():
            try:
                compile_expr(str(r.get("logic") or ""))
            except UnsupportedSyntax:
                continue
            except DslError as exc:
                bad.append((r["src"], str(exc)[:40]))
        assert not bad, "存在未归类的不规范表达式：\n" + "\n".join(map(str, bad))

    def test_scope_register_matches_actual(self):
        scope = json.loads((ROOT / "config" / "rule_dsl_scope.json").read_text(encoding="utf-8"))
        unsup = sorted(x["src"] for x in scope["unsupported_rules"])
        assert len(unsup) == scope["counts"]["unsupported"]
        assert scope["counts"]["malformed"] == 0, "本轮已把不规范表达式全部规范化"

    def test_func_whitelist_covers_actual_usage(self):
        used = set()
        for r in self._rules():
            try:
                used |= set(compile_expr(str(r.get("logic") or "")).funcs_used)
            except DslError:
                continue
        assert used <= set(ALLOWED_FUNCS), used - set(ALLOWED_FUNCS)

    def test_gap_fields_registered(self):
        """字段缺口清单必须覆盖实际缺口（缺口=候选引用但 var_map 未登记）。"""
        vm = set()
        for rel in _CAND:
            d = json.loads((ROOT / rel).read_text(encoding="utf-8"))
            vm |= set(k for k in (d.get("var_map") or d.get("var_map_addendum") or {})
                      if not k.startswith("_"))
        actual = set()
        for r in self._rules():
            try:
                actual |= compile_expr(str(r.get("logic") or "")).identifiers
            except DslError:
                continue
        gap = actual - vm
        scope = json.loads((ROOT / "config" / "rule_dsl_scope.json").read_text(encoding="utf-8"))
        reg = set(scope["gap_fields"]["flag_like"]) | set(scope["gap_fields"]["numeric_like"])
        assert gap == reg, "缺口清单与实际不一致（多出 %s；登记多出 %s）" % (
            sorted(gap - reg)[:5], sorted(reg - gap)[:5])


class TestGateReverse:
    """⑧ 反向验证：破坏 ⇒ 闸门必须报红（证明判据非假）。"""

    def _gate(self):
        spec = importlib.util.spec_from_file_location(
            "_t_dsl_gate", ROOT / "tools" / "audit_consistency.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_gate_green_now(self):
        assert [i for i in self._gate().check_rule_dsl_and_externalizable()
                if i[0] == "ERROR"] == []

    def test_reverse_scope_drift_is_flagged(self, monkeypatch):
        """登记表与实际边界不一致 ⇒ 必须报红。"""
        import tempfile
        g = self._gate()
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            (tdp / "config").mkdir()
            scope = json.loads((ROOT / "config" / "rule_dsl_scope.json").read_text(encoding="utf-8"))
            scope["unsupported_rules"] = scope["unsupported_rules"][:-1]   # 少登一条
            (tdp / "config" / "rule_dsl_scope.json").write_text(
                json.dumps(scope, ensure_ascii=False), encoding="utf-8")
            for rel in _CAND:
                (tdp / "config" / Path(rel).name).write_text(
                    (ROOT / rel).read_text(encoding="utf-8"), encoding="utf-8")
            monkeypatch.setattr(g, "ROOT", tdp, raising=True)
            errs = [i for i in g.check_rule_dsl_and_externalizable() if i[0] == "ERROR"]
        assert any("不一致" in i[2] for i in errs), errs

    def test_reverse_gap_growth_is_flagged(self, monkeypatch):
        """字段缺口扩大（登记值调小）⇒ 必须报红。"""
        import tempfile
        g = self._gate()
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            (tdp / "config").mkdir()
            scope = json.loads((ROOT / "config" / "rule_dsl_scope.json").read_text(encoding="utf-8"))
            scope["counts"]["gap_fields"] = 1                 # 谎报很小的缺口
            (tdp / "config" / "rule_dsl_scope.json").write_text(
                json.dumps(scope, ensure_ascii=False), encoding="utf-8")
            for rel in _CAND:
                (tdp / "config" / Path(rel).name).write_text(
                    (ROOT / rel).read_text(encoding="utf-8"), encoding="utf-8")
            monkeypatch.setattr(g, "ROOT", tdp, raising=True)
            errs = [i for i in g.check_rule_dsl_and_externalizable() if i[0] == "ERROR"]
        assert any("缺口" in i[2] and "扩大" in i[2] for i in errs), errs

    def test_reverse_default_zero_is_caught(self, monkeypatch):
        """★ 反向验证三值逻辑（**最贴铁律的破坏**）：把「缺字段」改成默认 `0` ⇒ 断言必红。

        为什么用 `0` 而不是 `False`：本模块 `_is_num` **刻意排除 `bool`**，所以
        「缺字段→False」还会被**类型检查**再拦一次（返回 `bad-cmp`）。
        而「缺字段→0」会一路算成 `0 > 1 = False` —— 即把「没查到」说成「没问题」，
        正是项目铁律「缺失≠0」要防的**最危险形态**。
        """
        import engine.rule_dsl as dsl
        _orig = dsl._eval

        def _broken(node, v, p, reasons):
            if node[0] == "var":
                return v.get(node[1], 0)          # ★ 破坏：缺失默认 0
            return _orig(node, v, p, reasons)

        monkeypatch.setattr(dsl, "_eval", _broken, raising=True)
        assert dsl.evaluate(dsl.compile_expr("a > 1"), {}, {}) is False, \
            "破坏后应变成 False（证明该缺陷形态确实存在、判据能捕捉）"
        monkeypatch.undo()
        assert dsl.evaluate(dsl.compile_expr("a > 1"), {}, {}) is None, "还原后必须回到 UNKNOWN"

    def test_bool_operand_in_numeric_comparison_is_unknown(self):
        """附加防线：布尔值参与**数值**比较 ⇒ UNKNOWN（类型错误不得静默算出结论）。"""
        assert ev("flag > 1", {"flag": False}) is None
        assert any("不是数值" in x for x in ev_reasons("flag > 1", {"flag": False}))
