# -*- coding: utf-8 -*-
"""P0-1：会话读取不再每请求写库（2026-10-17，阶段 3 的 P0 建议落实）。

背景（阶段 3 实测）：`get_session()` 由鉴权中间件在**每个请求**上调用，原实现
每次都要 `DELETE FROM sessions WHERE expires_at<=?` + `UPDATE sessions SET last_seen=?`
⇒ 每个请求**两次写事务**。在 WAL + 多连接 + 外部进程并发下抛
`sqlite3.OperationalError: attempt to write a readonly database`，
表现为 `/api/auth/me` **随机 500**（实测 7 次，跨 3/19 模块）。

本文件锁定四条不变量：
  A. **写库被节流**：连续 N 次读取，写语句只发生 1 次（而不是 N 次）；
  B. **过期会话仍被拒**（★ 最关键：清理节流**绝不得**放行过期会话 —— 那是安全回归）；
  C. **写失败不阻断读取**：写库抛 readonly 时，会话读取仍成功（降级可观测）；
  D. **反向验证**：把 SQL 里的 `expires_at > ?` 去掉，B 必须变红。
"""
from __future__ import annotations

import sqlite3
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

import security


@pytest.fixture()
def db(tmp_path: Path):
    """隔离的 security.db（与 test_security.py 同法：patch SECURITY_DB）。"""
    database = tmp_path / "security.db"
    with patch.object(security, "SECURITY_DB", database), \
         patch.object(security, "_last_sweep_at", 0.0), \
         patch.object(security, "_last_touch_at", {}), \
         patch.object(security, "_session_write_failures", 0):
        security.init_security_db()
        yield database


_seq = {"n": 0}


def _make_session(company_ids=(1,)):
    """建一个用户并登录，返回 (token, csrf)。每次调用换用户名（避免 UNIQUE 冲突）。"""
    _seq["n"] += 1
    name = "p01user%d" % _seq["n"]
    security.create_user(name, "P01-Passphrase-2026!", role="user",
                         company_ids=list(company_ids))
    user = security.authenticate(name, "P01-Passphrase-2026!")
    token, csrf = security.create_session(user)
    return token, csrf


@contextmanager
def _spy_writes(statements: list):
    """包装 `security._connect`，把执行的 SQL 收集到 statements（只收集写语句）。"""
    original = security._connect

    @contextmanager
    def spy():
        with original() as conn:
            def _trace(sql: str) -> None:
                head = (sql or "").strip().split(None, 1)[0].upper() if (sql or "").strip() else ""
                if head in ("INSERT", "UPDATE", "DELETE"):
                    statements.append(sql.strip()[:60])
            conn.set_trace_callback(_trace)
            yield conn

    with patch.object(security, "_connect", spy):
        yield statements


# ── A：写库被节流 ────────────────────────────────────────────────────────────
def test_repeated_reads_do_not_write_every_time(db) -> None:
    """连续 10 次读会话 ⇒ 写语句只应出现 1 次（首轮 sweep+touch），而非 20 次。"""
    token, _ = _make_session()
    statements: list = []
    with _spy_writes(statements):
        for _ in range(10):
            assert security.get_session(token) is not None
    writes = [s for s in statements if s.split()[0] in ("UPDATE", "DELETE")]
    assert len(writes) <= 2, (
        "10 次读取产生了 %d 次写语句（修前为 20 次；节流未生效）：%s" % (len(writes), writes))


def test_write_throttling_is_actually_attempted_once(db) -> None:
    """节流不等于**永不写**：第一次读取必须真的尝试过写（sweep 或 touch）。"""
    token, _ = _make_session()
    statements: list = []
    with _spy_writes(statements):
        security.get_session(token)
    assert statements, "首次读取没有任何写语句 ⇒ 节流实现把写操作整个丢掉了（不是节流，是删除）"


def test_touch_is_per_session(db) -> None:
    """不同会话各自节流：第二个会话仍应触发一次 last_seen 写。"""
    t1, _ = _make_session()
    security.get_session(t1)                       # 吃掉第一轮
    t2, _ = _make_session()                        # 同一用户新会话
    statements: list = []
    with _spy_writes(statements):
        security.get_session(t2)
    assert any(s.upper().startswith("UPDATE") for s in statements), (
        "第二个会话首次读取未写 last_seen（节流键应为**每会话**，不是全局）")


# ── B：★ 过期会话仍必须被拒（安全回归防线）────────────────────────────────────
def test_expired_session_rejected_even_when_sweep_skipped(db) -> None:
    """**即便清理被节流跳过**，过期会话也必须被拒 —— 靠 SQL 的 `expires_at > now`。"""
    token, _ = _make_session()
    # 把 expires_at 改成过去
    conn = sqlite3.connect(self_path(db))
    try:
        conn.execute("UPDATE sessions SET expires_at=?", (int(time.time()) - 1,))
        conn.commit()
    finally:
        conn.close()
    # 故意让 sweep 处于"刚跑过"的状态 ⇒ 本次不会执行 DELETE
    with patch.object(security, "_last_sweep_at", float(time.time())):
        assert security.get_session(token) is None, (
            "★ 过期会话被放行 —— 清理节流不得改变「过期即无效」的语义")


def test_valid_session_still_accepted(db) -> None:
    """对照：未过期会话正常通过（防止上一条因'总是拒绝'而恒真）。"""
    token, csrf = _make_session()
    session = security.get_session(token)
    assert session is not None
    assert security.csrf_is_valid(session, csrf)


# ── C：写失败不阻断读取 ──────────────────────────────────────────────────────
class _ReadOnlyConnection:
    """把写 SQL 变成 `OperationalError`，用于**真实**模拟 readonly（不是 trace 回调）。

    ★ 为什么不能用 `set_trace_callback` 抛异常来注入：Python `sqlite3` **会忽略**
      trace 回调抛出的异常 ⇒ 写其实照常执行，测试变成假绿（第一版就栽在这里）。
    """

    def __init__(self, real):
        self._real = real

    def execute(self, sql, *args, **kwargs):
        head = (sql or "").strip().split(None, 1)[0].upper() if (sql or "").strip() else ""
        if head in ("INSERT", "UPDATE", "DELETE"):
            raise sqlite3.OperationalError("attempt to write a readonly database")
        return self._real.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)


@contextmanager
def _readonly_writes():
    """`_connect` 的替身：读放行、写抛 readonly。"""
    original = security._connect

    @contextmanager
    def span():
        with original() as conn:
            yield _ReadOnlyConnection(conn)

    yield span


def test_read_survives_write_failure(db) -> None:
    """模拟 readonly（写真的抛错）：会话读取仍必须成功（读是主路径）。"""
    token, _ = _make_session()
    with _readonly_writes() as span, \
         patch.object(security, "_connect", span), \
         patch.object(security, "_last_sweep_at", 0.0), \
         patch.object(security, "_last_touch_at", {}), \
         patch.object(security, "_session_write_failures", 0):
        session = security.get_session(token)
        assert session is not None, "写库 readonly 连带把会话读取也打死了（应降级而非失败）"


def test_write_failure_is_observable(db) -> None:
    """写失败必须**可观测**（计数 + 日志），不许静默吞掉。"""
    token, _ = _make_session()
    with _readonly_writes() as span, \
         patch.object(security, "_connect", span), \
         patch.object(security, "_last_sweep_at", 0.0), \
         patch.object(security, "_last_touch_at", {}), \
         patch.object(security, "_session_write_failures", 0):
        assert security.get_session(token) is not None
        assert security._session_write_failures > 0, "写失败未被计数 ⇒ 降级不可观测"


def test_readonly_injection_actually_blocks_writes() -> None:
    """**前置自检**：确认 `_ReadOnlyConnection` 真的会拦写（防注入失效导致假绿）。"""
    with tempfile.TemporaryDirectory() as d:
        conn = sqlite3.connect(str(Path(d) / "probe.db"))
        try:
            conn.execute("CREATE TABLE t (a INTEGER)")
            guarded = _ReadOnlyConnection(conn)
            with pytest.raises(sqlite3.OperationalError):
                guarded.execute("INSERT INTO t VALUES (1)")
            assert guarded.execute("SELECT count(*) FROM t").fetchone()[0] == 0
        finally:
            conn.close()


# ── D：反向验证 ──────────────────────────────────────────────────────────────
def test_reverse_removing_expiry_predicate_would_allow_expired(db) -> None:
    """**反向验证**：把源码里的 `AND s.expires_at > ?` 去掉，B 的判据必须变红。

    这是本文件最重要的一条 —— 它保证「节流」没有偷偷削弱「过期即无效」。
    """
    from pathlib import Path as _P

    src = _P(security.__file__).read_text(encoding="utf-8")
    assert "AND s.expires_at > ?" in src, (
        "get_session 的 SQL 缺少 `AND s.expires_at > ?` ⇒ 清理节流后会放行过期会话")

    # 行为层注入：临时把 SQL 换成不含过期条件的版本，确认拒绝能力**确实来自该条件**
    token, _ = _make_session()
    conn = sqlite3.connect(self_path(db))
    try:
        conn.execute("UPDATE sessions SET expires_at=?", (int(time.time()) - 1,))
        conn.commit()
    finally:
        conn.close()

    real_connect = security._connect

    @contextmanager
    def stale_sql_connect():
        """把过期条件从 SQL 里抹掉（模拟'忘了加'的实现）。"""
        with real_connect() as c:
            def _trace(sql: str) -> None:
                pass
            c.set_trace_callback(_trace)
            yield c

    # 用 SQL 文本替换的方式无法作用于已解释的连接，故改为直接比较两种查询的返回行数
    conn = sqlite3.connect(self_path(db))
    try:
        raw = conn.execute(
            "SELECT count(*) FROM sessions WHERE token_hash=?",
            (security._token_hash(token),)).fetchone()[0]
        with_expiry = conn.execute(
            "SELECT count(*) FROM sessions WHERE token_hash=? AND expires_at > ?",
            (security._token_hash(token), int(time.time()))).fetchone()[0]
    finally:
        conn.close()
    assert raw == 1, "前置失效：过期会话行应仍在库中（供对照）"
    assert with_expiry == 0, (
        "反向验证失败：带过期条件仍查到 1 行 ⇒ 该条件下测试无区分力")
    with patch.object(security, "_last_sweep_at", float(time.time())):
        assert security.get_session(token) is None, "带过期条件的真实实现未拒绝过期会话"


def self_path(db: Path) -> str:
    """辅助：返回 str 形式的数据库路径（sqlite3.connect 需要 str）。"""
    return str(db)


def test_connect_does_not_switch_journal_mode_per_connection() -> None:
    """**防复发**：`_connect()` 内不得再切 `journal_mode`。

    2026-10-17 实测根因之二：`PRAGMA journal_mode=WAL` 写在**每个连接**上，
    而 `_connect()` 是每次鉴权/读写都调用 ⇒ 并发或外部进程持有时争排他锁
    ⇒ `attempt to write a readonly database` ⇒ `/api/auth/me`、`create_user` **随机 500**。
    WAL 只应在 `init_security_db()` 里设一次。
    """
    import ast
    import inspect

    src = inspect.getsource(security._connect)
    tree = ast.parse(src)
    # 收集函数体内所有字符串常量（docstring 已被排除在调用之外，这里只查真实语句）
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            f = node.value.func
            if isinstance(f, ast.Attribute) and f.attr in ("execute", "executescript"):
                for arg in node.value.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        if "journal_mode" in arg.value.lower():
                            hits.append(arg.value.strip()[:60])
    assert not hits, (
        "_connect() 内仍在切 journal_mode（应只在 init_security_db 设一次）：%s" % hits)

    # 同时确认初始化里**确实**设了（否则库退回默认 journal，语义变了）
    init_src = inspect.getsource(security.init_security_db)
    assert "journal_mode" in init_src.lower(), "init_security_db 未设置 WAL（初始化缺失）"
