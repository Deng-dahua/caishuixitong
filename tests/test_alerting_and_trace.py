# -*- coding: utf-8 -*-
"""阈值告警（O-03）与请求关联 id（O-04）守护测试。

背景
----
· O-03：此前"告警"只有**分析完成通知** —— 没阈值、没触发条件、没冷却、没分级。
  这不是告警，是通知。真正的告警必须能回答"什么条件下报、报几次、报给谁"。
· O-04：`trace_id` 此前是**业务字段**（报告/证据链编号），不是"这一次 HTTP 请求"的
  关联 id ⇒ 多个模块的日志无法串起来。

判据重点：
  ① 告警**必须有冷却**（否则持续故障刷屏，等于没有告警）；
  ② 取不到数据时**不能当作正常**（那是最危险的假绿灯）；
  ③ 关联 id 要**跨 async 并发不串味**（contextvars，不是 thread-local）；
  ④ 日志里必须真的出现 rid（不是"装了 filter 但没生效"）。
"""
from __future__ import annotations

import asyncio
import logging
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import alerting as AL          # noqa: E402
from engine import request_context as RC   # noqa: E402


@pytest.fixture(autouse=True)
def _clean():
    AL.reset()
    yield
    AL.reset()


# ── O-03 告警 ───────────────────────────────────────────────────────────────
def _snap(total=1000, errors=0, p95=100, samples=1000):
    return {
        "requests": {"total": total, "server_errors_5xx": errors,
                     "error_rate": (errors / total) if total else 0.0},
        "latency_ms": {"p50": 50, "p95": p95, "p99": p95 + 10, "samples": samples},
    }


def test_error_rate_rule_fires(monkeypatch) -> None:
    monkeypatch.setattr(AL, "_metrics", lambda: _snap(errors=50))
    monkeypatch.setattr(AL, "_backup_age_hours", lambda: 1.0)
    monkeypatch.setattr(AL, "_disk_free_ratio", lambda: 0.9)
    monkeypatch.setattr(AL, "_failed_jobs_ratio", lambda: 0.0)
    fired = AL.evaluate(now=1000.0)
    codes = {x["code"] for x in fired}
    assert "ERR_RATE_HIGH" in codes, fired
    item = [x for x in fired if x["code"] == "ERR_RATE_HIGH"][0]
    assert item["value"] == "5.00%"
    assert item["level"] == "critical"


def test_cooldown_prevents_repeat(monkeypatch) -> None:
    """★ 核心判据：同一规则在冷却窗口内只报一次（否则持续故障会刷屏）。"""
    monkeypatch.setattr(AL, "_metrics", lambda: _snap(errors=50))
    monkeypatch.setattr(AL, "_backup_age_hours", lambda: 1.0)
    monkeypatch.setattr(AL, "_disk_free_ratio", lambda: 0.9)
    monkeypatch.setattr(AL, "_failed_jobs_ratio", lambda: 0.0)
    first = AL.evaluate(now=1000.0)
    assert first, "首次应当告警"
    second = AL.evaluate(now=1000.0 + 60)          # 1 分钟后再评估
    assert not second, "冷却窗口内重复告警 ⇒ 告警会被无视"
    # 冷却过去后应再次告警
    window = max(int(r.get("cooldown_minutes", 30)) for r in AL.RULES) * 60 + 60
    third = AL.evaluate(now=1000.0 + window)
    assert third, "冷却结束后未重新告警"


def test_force_bypasses_cooldown(monkeypatch) -> None:
    monkeypatch.setattr(AL, "_metrics", lambda: _snap(errors=50))
    monkeypatch.setattr(AL, "_backup_age_hours", lambda: 1.0)
    monkeypatch.setattr(AL, "_disk_free_ratio", lambda: 0.9)
    monkeypatch.setattr(AL, "_failed_jobs_ratio", lambda: 0.0)
    AL.evaluate(now=1000.0)
    again = AL.evaluate(now=1000.0, respect_cooldown=False)
    assert again, "force 应绕过冷却"


def test_no_alert_when_healthy(monkeypatch) -> None:
    monkeypatch.setattr(AL, "_metrics", lambda: _snap(errors=0, p95=100))
    monkeypatch.setattr(AL, "_backup_age_hours", lambda: 1.0)
    monkeypatch.setattr(AL, "_disk_free_ratio", lambda: 0.9)
    monkeypatch.setattr(AL, "_failed_jobs_ratio", lambda: 0.0)
    assert AL.evaluate(now=1000.0) == []


def test_missing_data_is_not_treated_as_healthy(monkeypatch) -> None:
    """★ 取不到数据**不能当作正常** —— 那是最危险的假绿灯。"""
    monkeypatch.setattr(AL, "_metrics", lambda: _snap())
    monkeypatch.setattr(AL, "_backup_age_hours", lambda: None)   # 从未备份
    monkeypatch.setattr(AL, "_disk_free_ratio", lambda: None)    # 取不到
    monkeypatch.setattr(AL, "_failed_jobs_ratio", lambda: None)
    fired = AL.evaluate(now=1000.0)
    codes = {x["code"] for x in fired}
    assert "BACKUP_STALE" in codes, "从未备份却没告警"
    item = [x for x in fired if x["code"] == "BACKUP_STALE"][0]
    assert item["value"] == "从未备份"


def test_backup_stale_threshold(monkeypatch) -> None:
    monkeypatch.setattr(AL, "_metrics", lambda: _snap())
    monkeypatch.setattr(AL, "_disk_free_ratio", lambda: 0.9)
    monkeypatch.setattr(AL, "_failed_jobs_ratio", lambda: 0.0)
    monkeypatch.setattr(AL, "_backup_age_hours", lambda: 10.0)
    assert not [x for x in AL.evaluate(now=1000.0) if x["code"] == "BACKUP_STALE"]
    AL.reset()
    monkeypatch.setattr(AL, "_backup_age_hours", lambda: 72.0)
    assert [x for x in AL.evaluate(now=2000.0) if x["code"] == "BACKUP_STALE"]


def test_eval_failure_is_reported_not_swallowed(monkeypatch) -> None:
    """指标本身取不到时，要报"评估失败"，不能静默返回空列表。"""
    def boom():
        raise RuntimeError("metrics 不可用")

    monkeypatch.setattr(AL, "_metrics", boom)
    fired = AL.evaluate(now=1000.0)
    assert fired and fired[0]["code"] == "EVAL_FAILED", "评估失败被静默吞掉了"


def test_status_explains_why_not_firing(monkeypatch) -> None:
    """`status()` 必须能回答「为什么没报」（当前值 vs 阈值）。"""
    monkeypatch.setattr(AL, "_metrics", lambda: _snap())
    monkeypatch.setattr(AL, "_backup_age_hours", lambda: 1.0)
    monkeypatch.setattr(AL, "_disk_free_ratio", lambda: 0.5)
    monkeypatch.setattr(AL, "_failed_jobs_ratio", lambda: 0.0)
    st = AL.status()
    assert len(st["rules"]) == len(AL.RULES)
    for row in st["rules"]:
        assert row["threshold"] and row["current"] is not None
        assert "firing" in row


# ── O-04 关联 id ────────────────────────────────────────────────────────────
def test_trace_id_generated_and_propagated() -> None:
    tid = RC.set_trace_id(None)
    assert len(tid) == 8 and RC.current_trace_id() == tid
    given = RC.set_trace_id("caller-abc")
    assert given == "caller-abc" and RC.current_trace_id() == "caller-abc"


def test_trace_id_isolated_between_async_tasks() -> None:
    """★ async 并发下不许串味（用 thread-local 必然串）。"""
    seen = {}

    async def worker(name):
        RC.set_trace_id("rid-" + name)
        await asyncio.sleep(0.01)          # 期间另一个任务会改 id
        seen[name] = RC.current_trace_id()

    async def main():
        await asyncio.gather(worker("a"), worker("b"))

    asyncio.run(main())
    assert seen["a"] == "rid-a" and seen["b"] == "rid-b", seen


def test_log_records_carry_trace_id() -> None:
    """日志里必须真的出现 rid（不是"装了 filter 但没生效"）。"""
    records = []

    class _H(logging.Handler):
        def emit(self, record):
            records.append(record)

    root = logging.getLogger()
    handler = _H()
    handler.addFilter(RC.TraceFilter())
    handler.setFormatter(logging.Formatter("[rid=%(trace_id)s] %(message)s"))
    root.addHandler(handler)
    try:
        RC.set_trace_id("deadbeef")
        logging.getLogger("probe.rid").warning("hello")
        RC.set_trace_id(None)
        RC._trace_id.set("")               # 模拟无请求上下文
        logging.getLogger("probe.rid").warning("no-context")
    finally:
        root.removeHandler(handler)
    assert any("rid=deadbeef" in handler.format(r) for r in records if r.getMessage() == "hello")
    assert any("rid=-" in handler.format(r) for r in records
               if r.getMessage() == "no-context"), "无上下文时应显示 `-` 而不是空串"


def test_api_endpoints_registered() -> None:
    src = (ROOT / "backup_api.py").read_text(encoding="utf-8")
    assert "/alerts" in src and "alerts/evaluate" in src
    assert src.count("_admin(request)") >= 3, "告警接口必须仅管理员"
