# -*- coding: utf-8 -*-
"""第 6 批验收测试：Skill 编排引擎（任务1）。

用户要求逐条：按方案选择 Skill / 顺序+并行+条件+重试 / 输入输出可追溯 /
行业·企业·税种·检查重点组合 / 局部重跑（该 Skill 及下游）/ 输出执行日志 /
人工暂停复核后继续 / 灰度发布与版本回滚。
"""
from __future__ import annotations


class TestPlanStore:
    def test_plans_are_valid(self):
        from engine.skill_runtime import validate_plans
        assert validate_plans() == [], validate_plans()

    def test_unknown_plan_raises(self):
        from engine.skill_runtime import resolve_plan
        try:
            resolve_plan(plan_id="不存在的方案")
        except ValueError:
            return
        raise AssertionError("未登记的方案必须报错，不得静默换方案")

    def test_resolve_by_industry_focus_default(self):
        from engine.skill_runtime import resolve_plan
        a = resolve_plan(industry="制造业")
        assert a["plan_id"] == "industry_focus" and a["matched_by"] == "industry", a
        b = resolve_plan(focus=["对外交付"])
        assert b["plan_id"] == "compliance_review", b
        c = resolve_plan()
        assert c["matched_by"] == "default" and c["plan_id"] == "standard", c


class TestRun:
    def _plan(self):
        return {"plan_id": "T", "plan_name": "测试方案", "steps": [
            {"step_id": "s1", "skill_id": "numparse", "entry": "x", "params": {"a": 1}},
            {"step_id": "s2", "skill_id": "numparse", "entry": "y", "params": {},
             "parallel_group": "P1"},
            {"step_id": "s3", "skill_id": "numparse", "entry": "z", "params": {},
             "parallel_group": "P1"},
            {"step_id": "s4", "skill_id": "numparse", "entry": "w", "params": {},
             "when": {"industry_matched": True}},
        ]}

    def test_sequential_parallel_conditional_and_log_fields(self):
        from engine.skill_runtime import LOG_FIELDS, run
        calls = []

        def h(ctx, params):
            calls.append(params)
            return {"seen": len(calls)}

        got = run(self._plan(), ctx={"industry_params": {"matched": False}},
                  handlers={"numparse": h}, company_id=7)
        assert got["status"] == "ok"
        assert len(got["log"]) == 4
        # 条件不成立 ⇒ skipped 且留痕（不是静默跳过）
        s4 = [r for r in got["log"] if r["step_id"] == "s4"][0]
        assert s4["status"] == "skipped" and "条件不成立" in s4["error"], s4
        # 输入输出可追溯：每条日志字段齐备
        for r in got["log"]:
            for f in LOG_FIELDS:
                assert f in r, "日志缺字段 %s" % f
        assert all(isinstance(r["ms"], int) for r in got["log"])

    def test_retry_and_final_failure(self):
        from engine.skill_runtime import run
        state = {"n": 0}

        def flaky(ctx, params):
            state["n"] += 1
            if state["n"] < 2:
                raise RuntimeError("第一次失败")
            return "ok"

        plan = {"plan_id": "R", "plan_name": "重试", "steps": [
            {"step_id": "s1", "skill_id": "numparse", "entry": "x", "params": {}, "retries": 1}]}
        got = run(plan, handlers={"numparse": flaky})
        assert got["log"][0]["status"] == "ok" and got["log"][0]["attempt"] == 2, got["log"][0]

        def always_fail(ctx, params):
            raise RuntimeError("一直失败")
        got2 = run(plan, handlers={"numparse": always_fail})
        assert got2["status"] == "failed"
        assert got2["log"][0]["status"] == "failed" and "一直失败" in got2["log"][0]["error"]

    def test_pause_and_resume_keeps_progress(self):
        from engine.skill_runtime import run
        plan = {"plan_id": "P", "plan_name": "暂停", "steps": [
            {"step_id": "s1", "skill_id": "numparse", "entry": "x", "params": {}},
            {"step_id": "s2", "skill_id": "numparse", "entry": "y", "params": {},
             "pause_after": True, "pause_reason": "须人工复核"},
            {"step_id": "s3", "skill_id": "numparse", "entry": "z", "params": {}}]}
        got = run(plan, handlers={"numparse": lambda c, p: "ok"})
        assert got["status"] == "paused", got
        assert got["pause"]["after_step"] == "s2" and "人工复核" in got["pause"]["reason"]
        assert [r["step_id"] for r in got["log"]] == ["s1", "s2"], "暂停后不得继续执行下游"
        # 恢复：从暂停点的下一步继续（不重跑已成功的步骤）
        from engine.skill_runtime import rerun
        done = rerun(plan, "s3", handlers={"numparse": lambda c, p: "ok"})
        assert [r["step_id"] for r in done["log"]] == ["s3"]

    def test_local_rerun_covers_downstream_only(self):
        from engine.skill_runtime import rerun
        plan = {"plan_id": "D", "plan_name": "下游", "steps": [
            {"step_id": "s1", "skill_id": "numparse", "entry": "x", "params": {}},
            {"step_id": "s2", "skill_id": "numparse", "entry": "y", "params": {}},
            {"step_id": "s3", "skill_id": "numparse", "entry": "z", "params": {}}]}
        got = rerun(plan, "s2", handlers={"numparse": lambda c, p: "ok"})
        assert got["rerun_scope"] == ["s2", "s3"], got
        assert got["upstream_skipped"] == ["s1"], got
        try:
            rerun(plan, "不存在")
        except ValueError:
            pass
        else:
            raise AssertionError("未登记步骤必须报错")


class TestGrayAndRollback:
    def test_effective_version_and_rollback(self):
        from engine.skill_runtime import effective_version, rollback
        v0 = effective_version("redaction", company_id="no-such-company")
        assert v0, v0
        r = rollback("redaction", "0.9.0")
        try:
            assert effective_version("redaction", company_id="no-such-company") == "0.9.0"
        finally:
            rollback("redaction", v0)          # 还原，避免污染方案库
        assert r["skill_id"] == "redaction"

    def test_log_md_contains_required_columns(self):
        from engine.skill_runtime import render_log_md, run
        got = run({"plan_id": "L", "plan_name": "日志", "steps": [
            {"step_id": "s1", "skill_id": "numparse", "entry": "x", "params": {"k": "v"}}]},
            handlers={"numparse": lambda c, p: {"n": 1}})
        md = render_log_md(got)
        for col in ("步骤", "Skill", "版本", "入口", "状态", "尝试", "耗时(ms)", "入参", "结果", "异常"):
            assert col in md, col
        assert "# 本次分析 Skill 执行日志" in md
