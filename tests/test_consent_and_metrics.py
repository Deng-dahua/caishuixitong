# -*- coding: utf-8 -*-
"""知情同意（E-01/E-04）与运行指标（O-02）守护测试。

判据要压住三件事：
  ① 同意**按版本**生效：条款改版后必须重新确认，旧记录不能冒充新同意；
  ② 未确认 ≠ 默认同意（读不到就是未确认，不默认放行）；
  ③ 指标采集**绝不因异常而失败**，且**不记录查询参数**（防敏感信息进指标）。
"""
from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import consent as CS   # noqa: E402
from engine import metrics as M    # noqa: E402


# ── E-01 知情同意 ───────────────────────────────────────────────────────────
def test_consent_payload_has_required_topics() -> None:
    """条款必须覆盖：数据范围/目的/留存/权利/免责 —— 缺一项即是"告知不完整"。"""
    p = CS.payload()
    assert p["version"] == CS.CONSENT_VERSION
    assert p["title"] and p["items"], "条款为空"
    text = "".join(i["title"] + i["body"] for i in p["items"])
    for kw in ("处理哪些数据", "目的", "留存", "权利", "免责", "安全"):
        assert kw in text, "条款缺少「%s」" % kw
    assert "不构成税务鉴证意见" in text, "缺少免责核心表述"


def test_unaccepted_user_is_not_treated_as_consented(tmp_path, monkeypatch) -> None:
    """未确认就是未确认（不许默认同意）。"""
    assert CS.is_accepted("no-such-user-%s" % tmp_path.name) is False


def test_record_then_accepted_is_idempotent(tmp_path, monkeypatch) -> None:
    """确认后状态变为已确认；重复提交幂等（不产生多条记录）。"""
    import security

    db = tmp_path / "security.db"
    monkeypatch.setattr(security, "SECURITY_DB", str(db))
    security.init_security_db()
    user = "consent_probe"
    assert CS.is_accepted(user) is False
    r1 = CS.record(user, client_ip="127.0.0.1", user_agent="pytest")
    assert r1["ok"] is True and r1["already"] is False
    assert CS.is_accepted(user) is True
    r2 = CS.record(user, client_ip="127.0.0.1", user_agent="pytest")
    assert r2["already"] is True, "重复确认不应再插一条"
    # 只应有 1 条
    with security._connect() as conn:
        n = conn.execute("SELECT COUNT(*) FROM user_consents WHERE username=?", (user,)).fetchone()[0]
    assert n == 1, "重复确认写入了 %d 条" % n


def test_version_bump_requires_reconsent(tmp_path, monkeypatch) -> None:
    """★ 条款改版 ⇒ 旧版本记录不能冒充新版本同意。"""
    import security

    db = tmp_path / "security.db"
    monkeypatch.setattr(security, "SECURITY_DB", str(db))
    security.init_security_db()
    user = "consent_ver"
    CS.record(user, version="2020-01-v0")
    assert CS.is_accepted(user, version="2020-01-v0") is True
    assert CS.is_accepted(user, version="2099-12-v9") is False, (
        "旧版本同意被当成了新版本同意 ⇒ 改版后不会重新告知")


# ── O-02 指标 ───────────────────────────────────────────────────────────────
def test_metrics_counts_and_percentiles() -> None:
    M.reset()
    for i in range(100):
        M.record_request("/api/v1/demo/%d" % i, "GET", 200, 0.01 * (i % 10 + 1))
    M.record_request("/api/v1/demo/1", "POST", 500, 2.0)

    s = M.snapshot()
    assert s["requests"]["total"] == 101
    assert s["requests"]["server_errors_5xx"] == 1
    assert s["latency_ms"]["p50"] > 0
    assert s["latency_ms"]["p99"] >= s["latency_ms"]["p50"]
    # 路径归一化：/demo/{n} 只应有一行，而不是 100 行
    paths = [p["path"] for p in s["top_paths"]]
    assert paths.count("/api/v1/demo/{n}") == 1, "路径未归一化（高基数风险）：%s" % paths[:5]
    assert s["slowest"], "慢请求清单为空"


def test_metrics_never_records_query_string() -> None:
    """★ 隐私判据：指标里**不得**出现查询参数（那里可能有搜索词/身份证号）。"""
    M.reset()
    M.record_request("/api/v1/search?q=%E8%BA%AB%E4%BB%BD%E8%AF%81", "GET", 200, 0.02)
    s = M.snapshot()
    blob = str(s)
    assert "q=" not in blob, "指标里出现了查询参数"
    assert "%E8" not in blob, "指标里出现了 URL 编码后的查询参数"


def test_metrics_record_never_raises() -> None:
    """采集不能影响业务：传垃圾参数也不许抛异常。"""
    M.reset()
    M.record_request(None, None, None, None)          # type: ignore[arg-type]
    M.record_request("", "", 200, "not-a-number")     # type: ignore[arg-type]
    assert M.snapshot()["requests"]["total"] >= 0


def test_prometheus_text_has_stable_fields() -> None:
    M.reset()
    M.record_request("/api/v1/x", "GET", 200, 0.03)
    txt = M.prometheus_text()
    for name in ("app_requests_total", "app_errors_5xx_total",
                 "app_uptime_seconds", "app_latency_p50_ms", "app_latency_p95_ms"):
        assert name in txt, "Prometheus 文本缺字段 %s" % name


def test_normalize_path_collapses_ids() -> None:
    assert M.normalize_path("/api/v1/projects/123/risks") == "/api/v1/projects/{n}/risks"
    assert M.normalize_path("/api/v1/x/0b6f3a4e-1111-2222-3333-444455556666") == "/api/v1/x/{uuid}"
