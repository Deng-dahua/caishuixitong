# -*- coding: utf-8 -*-
"""业务操作留痕（`engine/audit_trail.py`）的回归测试。

背景（实测缺口，非设想）：`audit_logs` 表与 `/api/audit-logs` 早就在，但**全仓无写入**
（`SELECT COUNT(*)` = 0）⇒ 上传/分析/复核/导出/下载/删除六类动作一条都没留痕。
本组锁住三件事：**唯一的写入权威**、**失败不阻断也不静默**、**表结构只增不改**。

★ 隔离原则：所有用例都把 `database.engine` 换成本用例的临时 SQLite 文件
  （`audit_trail` 在被调用时才 `from database import engine`，故 monkeypatch 生效），
  **绝不写真实 `data/accounting.db`**。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

import database
from engine import audit_trail as AT

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def iso(tmp_path, monkeypatch):
    """把 `database.engine` 换成临时库（用例结束自动还原）。"""
    eng = create_engine("sqlite:///" + (tmp_path / "audit_iso.db").as_posix(),
                        connect_args={"check_same_thread": False})
    monkeypatch.setattr(database, "engine", eng)
    AT.ensure_schema()
    return eng


# ── 正例 ─────────────────────────────────────────────────────────────────────

@pytest.mark.plain
def test_record_writes_and_returns_id(iso):
    n0 = AT.count()
    rid = AT.record("doc.upload", target="某资料.csv", company_id=7,
                    detail="成功 1 个", user_name="tester")
    assert isinstance(rid, int) and rid > 0
    assert AT.count() == n0 + 1
    row = AT.list_records(limit=1)[0]
    assert (row["action"], row["target"], row["company_id"], row["user_name"]) == \
        ("doc.upload", "某资料.csv", 7, "tester")
    assert row["action_cn"] == "资料上传"          # 动作必须能出中文名
    assert AT.last_error() is None


@pytest.mark.plain
def test_unregistered_action_is_recorded_verbatim():
    """未登记动作**照记原值**（不许静默丢弃、也不许改名冒充已知）。"""
    assert len(AT.ACTIONS) == len(AT.ACTION_CN), "ACTIONS 与 ACTION_CN 必须一一对应"
    assert AT.action_cn("brand.new.thing") == "brand.new.thing"
    assert AT.action_cn("doc.upload") == "资料上传"


@pytest.mark.plain
def test_missing_company_is_null_not_zero(iso):
    """无归属的留痕必须存 NULL —— **不得用 0 冒充**（0 是"账套 0"，语义完全不同）。"""
    rid = AT.record("report.delete", target="x")
    row = [r for r in AT.list_records() if r["id"] == rid][0]
    assert row["company_id"] is None


@pytest.mark.plain
def test_filters_and_order(iso):
    for cid, act in ((1, "doc.upload"), (1, "report.export"), (2, "doc.upload")):
        AT.record(act, target="t", company_id=cid)
    assert len(AT.list_records(company_id=1)) == 2
    assert len(AT.list_records(company_id=2)) == 1
    assert [r["action"] for r in AT.list_records(action="doc.upload")] == \
        ["doc.upload", "doc.upload"]                      # 过滤生效且顺序稳定
    got = AT.list_records(limit=1, offset=0)
    assert len(got) == 1
    assert AT.count(company_id=1) == 2


# ── 反向验证 ─────────────────────────────────────────────────────────────────

@pytest.mark.reverse
def test_write_failure_does_not_raise_but_is_never_silent(monkeypatch):
    """留痕失败 ⇒ **不阻断主链**（不抛）且**绝不静默**（`last_error()` 非空）。"""
    monkeypatch.setattr(AT, "ensure_schema",
                        lambda: (_ for _ in ()).throw(RuntimeError("probe-boom")))
    assert AT.record("doc.upload", target="x", company_id=1) is None
    assert AT.last_error(), "写失败被静默了（last_error 为空）"
    # 反向面：闸门/测试模式下必须**抛**（证明"失败"这件事本身可被观测）
    monkeypatch.setattr(AT, "RAISE_ON_WRITE_ERROR", True)
    with pytest.raises(RuntimeError):
        AT.record("doc.upload", target="x", company_id=1)


@pytest.mark.reverse
def test_gate_catches_a_second_writer(iso):
    """**闸门必须自证非假**：别处再写一份 `INSERT INTO audit_logs` ⇒ 必须报 ERROR。"""
    import tools.audit_consistency as AC
    assert AC.check_audit_trail_single_writer() == [], "基线必须干净"
    probe = ROOT / "engine" / "_zz_probe_audit_second_writer.py"
    # 字面量在**运行期拼**，避免把本测试文件自己变成"第二写入点"（闸门会扫 tests/）
    needle = "INSERT " + "INTO " + "audit_logs"
    probe.write_text(
        "# -*- coding: utf-8 -*-\n"
        "def bad(conn):\n"
        "    conn.execute(\"%s (company_id, action) VALUES (1, 'x')\")\n" % needle,
        encoding="utf-8")
    try:
        issues = AC.check_audit_trail_single_writer()
        assert any(i[0] == "ERROR" and "_zz_probe_audit_second_writer" in i[1]
                   for i in issues), issues
    finally:
        if probe.exists():
            probe.unlink()
    assert AC.check_audit_trail_single_writer() == [], "还原后必须回到干净"


# ── 口径锁 ───────────────────────────────────────────────────────────────────

@pytest.mark.lock
def test_schema_only_appends_columns(iso):
    """表结构**只增不改**：原 7 列名与顺序不变，新列只能追加在末尾。

    为什么锁死顺序：读接口按位置取值（历史实现 `r[0]..r[6]`），
    顺序一变，历史数据与既有消费方同时出问题。
    """
    cols = [c["name"] for c in inspect(iso).get_columns("audit_logs")]
    assert cols[:7] == ["id", "company_id", "user_name", "action", "target",
                        "detail", "created_at"], cols
    assert cols[7:] == ["user_id"], cols


@pytest.mark.lock
def test_ensure_schema_is_idempotent(iso):
    before = [c["name"] for c in inspect(iso).get_columns("audit_logs")]
    AT.ensure_schema()
    AT.ensure_schema()
    after = [c["name"] for c in inspect(iso).get_columns("audit_logs")]
    assert before == after


@pytest.mark.lock
def test_index_exists(iso):
    """`(company_id, created_at)` 索引必须存在（否则报告页按账套查留痕会全表扫）。"""
    names = {i["name"] for i in inspect(iso).get_indexes("audit_logs")}
    assert "ix_audit_logs_company_created" in names, names


@pytest.mark.lock
def test_gate_registered_and_green():
    """闸门必须**注册进总链**且当前为绿（否则它只是装饰）。

    ★ 本组**故意不另写一份"全仓只有一处写入"的静态判据**：那属于同一概念两处实现，
      两处迟早分叉（本测试第一版就是这么写的，结果因为"注释里提到写法"而假红）。
      该判据的唯一权威 = 闸门 `check_audit_trail_single_writer()`，此处只断言它存在且为绿。
    """
    src = (ROOT / "tools" / "audit_consistency.py").read_text(encoding="utf-8")
    assert re.search(r"^\s*\+\s*check_audit_trail_single_writer\(\)", src, re.M), \
        "check_audit_trail_single_writer 未注册进 run_checks()"
    import tools.audit_consistency as AC
    assert AC.check_audit_trail_single_writer() == []
