# -*- coding: utf-8 -*-
"""业务操作留痕（Audit Trail）—— 「谁、什么时候、对哪个对象、做了什么」的**唯一权威**。

## 为什么要有它（实测缺口，不是设想）

`audit_logs` 表**早就在**（`database.py` 的 `init_db` 里 `CREATE TABLE IF NOT EXISTS`），
读接口 `/api/audit-logs` **也早就在**（`main.py` 的 `get_audit_logs`）—— 但**全仓没有任何一处写入**：

    SELECT COUNT(*) FROM audit_logs;            -- 0
    grep -rn "audit_logs" --include=*.py .       -- 只有 CREATE TABLE 与 SELECT

也就是说，**最需要追责的六类动作此前一条都没留痕**：
资料上传、分析发起、结论复核、报告导出、报告下载、资料/账套删除。
旁边的 `data/logs/access.jsonl` 只记 URL + 方法，回答不了
"**是谁把哪条结论改了**"这类问题（它连公司/对象都没有）。

## 铁律

- **写入只有一处**：本模块的 `record()`。闸门 `check_audit_trail_single_writer`
  逐行扫描（排除注释/文档串），别处出现 `INSERT INTO audit_logs` ⇒ ERROR。
- **绝不阻断主流程**：留痕失败只写 stderr（`[audit-trail] ...`）并返回 `None`。
  审计是**旁路证据**、不是主链 —— 但**绝不静默**（任何失败都必须能被看见）。
- **动作词表唯一权威**：新增一类动作只加 `ACTIONS` 一处；**未知动作照记原值 + 留痕**，
  不许静默丢弃（与 `engine/analysis_jobs.py::JOB_TRIGGERS` 同口径）。
- **表结构只增不改**：新列一律 `ALTER TABLE ... ADD COLUMN`，且由 `inspector` 守卫（幂等）。
  已存在的 7 列（`id/company_id/user_name/action/target/detail/created_at`）
  **列名与顺序不得变动** —— 读接口与历史数据都依赖它。
  这就是本项目的 **migration 底座**（不引入 alembic：§6 要求"变更走 migration"，
  而换栈式引入 alembic 与"不擅自更换技术栈"冲突，故用"幂等建表 + 幂等加列"实现同一目的）。
- **时间唯一** `runtime_storage.now_cst()`（北京时间）。
- **`company_id` 允许为空**：账套级删除（如 `/api/companies/{id}`）发生时该账套可能
  已经不在库里，此时**照记原 id**（`audit_logs.company_id` 无外键约束，正是为此）。
"""
from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Tuple

#: 业务动作词表（★ 唯一权威：新增一类动作只加这里一处）
ACTIONS: Tuple[str, ...] = (
    "doc.upload",       # 资料上传（成功落盘的每一份）
    "doc.delete",       # 资料删除
    "analysis.start",   # 发起一键分析（含强制重算/断点续跑/上传后自动重跑）
    "finding.review",   # 结论复核
    "report.export",    # 报告导出（生成交付件/工作底稿）
    "report.download",  # 报告下载（取回已生成的报告文件）
    "report.delete",    # 报告删除
    "company.purge",    # 账套删除（含其全部派生物）
    # ── 2026-10-13 新增（P0-1 项目管理）：**只在末尾追加**，既有动作顺序不得变动 ──
    "project.create",        # 稽查项目创建
    "project.update",        # 稽查项目修改（含状态迁移）
    "project.delete",        # 稽查项目删除
    "project.member_change",  # 稽查项目成员变更（新增/角色调整）
    # ── 2026-10-13 新增（P0-2 资料上传）：**只在末尾追加**，既有动作顺序不得变动 ──
    "doc.download",      # 资料下载（含水印生成）
    "doc.classify",      # 资料分类修正（人工）
    # ── 2026-10-13 新增（P0-3 解析与标准化）──
    "extract.run",       # 发起资料解析（解析 + 标准化 + 校验）
    "extract.correct",   # 解析结果人工校正
)

#: 动作的中文名（★ 与 `ACTIONS` 一一对应；面向界面/导出，不得出现英文码）
ACTION_CN: Dict[str, str] = {
    "doc.upload": "资料上传",
    "doc.delete": "资料删除",
    "analysis.start": "发起分析",
    "finding.review": "结论复核",
    "report.export": "报告导出",
    "report.download": "报告下载",
    "report.delete": "报告删除",
    "company.purge": "账套删除",
    "project.create": "项目创建",
    "project.update": "项目修改",
    "project.delete": "项目删除",
    "project.member_change": "项目成员变更",
    "doc.download": "资料下载",
    "doc.classify": "资料分类修正",
    "extract.run": "资料解析",
    "extract.correct": "解析结果校正",
}

#: 最近一次留痕错误（供诊断/闸门读取；正常为 None）
_LAST_ERROR: Optional[str] = None

#: 仅供闸门/测试：置 True 时写入失败直接抛异常（用于反向验证"写失败不静默"）
RAISE_ON_WRITE_ERROR = False

#: 表结构是否已就绪（**按 engine 身份**缓存：进程内同一 engine 只做一次）。
#: ★ 为什么必须缓存：`record()` 是**每一次业务动作**都要走的热路径，
#:   若每次都跑一遍 `CREATE TABLE/INDEX IF NOT EXISTS`，等于每次留痕都去抢一次
#:   SQLite 的**写锁 + 建索引检查** —— 在分析线程写库时会明显互相等待。
#: ★ 为什么按 `id(engine)` 而不是一个布尔：测试/闸门会把 `database.engine` 换成临时库，
#:   换库后必须重新建表，否则会"在新库上不建表"而静默失败。
_SCHEMA_READY_ENGINE: Optional[int] = None
_SCHEMA_LOCK = threading.RLock()


def _log(msg: str) -> None:
    """留痕（绝不静默）。"""
    try:
        import sys as _sys
        print("[audit-trail] %s" % msg, file=_sys.stderr, flush=True)
    except Exception:                            # noqa: BLE001
        pass


def last_error() -> Optional[str]:
    """最近一次留痕错误（正常为 None）。"""
    return _LAST_ERROR


def action_cn(action: Any) -> str:
    """动作码 → 中文名；未登记的**原样返回**（不静默丢弃、也不冒充已知）。"""
    a = str(action or "")
    return ACTION_CN.get(a, a)


# ── 表结构（幂等 = migration 底座）────────────────────────────────────────────

def ensure_schema() -> None:
    """幂等建表 + 幂等加列 + 索引。**可在任何时候重复调用**。

    - 表不存在 ⇒ 按**原 7 列**建（与历史 schema 逐字一致，历史数据可直接共存）；
    - 新列缺失 ⇒ `ALTER TABLE ADD COLUMN`（SQLite 安全、向后兼容）；
    - 索引缺失 ⇒ 建 `(company_id, created_at)`。

    为什么"只增不改"：`/api/audit-logs` 的历史实现按**位置**取值（`r[0]..r[6]`），
    在末尾追加列不会影响它；一旦改动既有列的顺序，读接口与历史数据同时出问题。
    """
    global _SCHEMA_READY_ENGINE
    from database import engine as _engine          # noqa: PLC0415
    if _SCHEMA_READY_ENGINE == id(_engine):
        return
    with _SCHEMA_LOCK:
        if _SCHEMA_READY_ENGINE == id(_engine):
            return
        from sqlalchemy import inspect as _inspect, text as _text   # noqa: PLC0415

        with _engine.begin() as conn:
            conn.execute(_text("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER,
                    user_name TEXT,
                    action TEXT NOT NULL,
                    target TEXT,
                    detail TEXT,
                    created_at TEXT
                )
            """))
            cols = {c["name"] for c in _inspect(conn).get_columns("audit_logs")}
            # ★ 只在此处增列：`user_id` 让"同名用户改名/重名"也能追溯
            if "user_id" not in cols:
                conn.execute(_text("ALTER TABLE audit_logs ADD COLUMN user_id INTEGER"))
            conn.execute(_text(
                "CREATE INDEX IF NOT EXISTS ix_audit_logs_company_created "
                "ON audit_logs (company_id, created_at)"
            ))
        _SCHEMA_READY_ENGINE = id(_engine)


# ── 写侧（唯一入口）──────────────────────────────────────────────────────────

def _resolve_actor(request: Any = None,
                   user_id: Any = None,
                   user_name: Any = None) -> Tuple[Optional[int], str]:
    """解析"是谁"。

    优先级：显式参数 > `request.state.auth`（HTTP 处理器）> `request_context` 的
    上下文变量（分析线程等**非请求**场景，只拿得到 id ⇒ 用户名留空，**不编造**）。
    """
    uid: Optional[int] = None
    uname: str = ""
    if request is not None:
        auth = getattr(getattr(request, "state", None), "auth", None)
        if auth is not None:
            try:
                uid = int(getattr(auth, "user_id"))
            except Exception:                    # noqa: BLE001
                uid = None
            uname = str(getattr(auth, "username", "") or "")
    if user_id is not None:
        try:
            uid = int(user_id)
        except Exception:                        # noqa: BLE001
            pass
    if user_name:
        uname = str(user_name)
    if uid is None:
        try:
            from request_context import get_current_user_id   # noqa: PLC0415
            _ctx = get_current_user_id()
            uid = int(_ctx) if _ctx is not None else None
        except Exception:                        # noqa: BLE001
            uid = None
    if uid is not None and not uname:
        # 非请求场景（分析线程/后台清理）只拿得到 id ⇒ 向**既有权威** `security.list_users()`
        # 反查用户名；查不到就留空，**绝不编造**（"admin"之类不得猜）。
        try:
            from security import list_users as _lu        # noqa: PLC0415
            for u in _lu():
                if int(u.get("id") or -1) == uid:
                    uname = str(u.get("username") or "")
                    break
        except Exception:                        # noqa: BLE001
            uname = uname
    return uid, uname


def record(action: str, *, target: Any = "", company_id: Any = None,
           detail: Any = "", request: Any = None,
           user_id: Any = None, user_name: Any = None) -> Optional[int]:
    """登记一条业务操作留痕。返回新行 id；失败返回 `None`（并已留痕）。

    参数：
      - `action`：见 `ACTIONS`（未知值**照记 + 留痕**，不静默丢弃）；
      - `target`：被操作对象的**可读标识**（资料文件名 / 作业 id / 报告编号 / 账套名）；
      - `company_id`：所属账套（无归属传 None，**不要用 0 冒充**）；
      - `detail`：补充说明（如"命中 2 条、跳过 1 条重复"）。

    ★ 调用点**不得**把本函数放进 `try` 里再 `pass`：本函数自身已保证"不抛、不静默"，
      外层再吞一次就等于把留痕失败藏起来（那正是本次要根治的毛病）。
    """
    global _LAST_ERROR
    try:
        a = str(action or "").strip()
        if not a:
            raise ValueError("action 不能为空")
        if a not in ACTIONS:
            _log("未登记的动作 %r（合法值 %s），按原值记录" % (a, list(ACTIONS)))
        uid, uname = _resolve_actor(request=request, user_id=user_id, user_name=user_name)
        cid: Optional[int] = None
        if company_id is not None:
            try:
                cid = int(company_id)
            except Exception:                    # noqa: BLE001
                cid = None
        from runtime_storage import now_cst      # noqa: PLC0415
        from database import engine as _engine    # noqa: PLC0415
        from sqlalchemy import text as _text      # noqa: PLC0415
        ensure_schema()
        with _engine.begin() as conn:
            row = conn.execute(_text(
                "INSERT INTO audit_logs "
                "(company_id, user_name, action, target, detail, created_at, user_id) "
                "VALUES (:cid, :un, :ac, :tg, :dt, :ts, :uid)"
            ), {
                "cid": cid,
                "un": uname,
                "ac": a,
                "tg": str(target or "")[:500],
                "dt": str(detail or "")[:2000],
                "ts": now_cst(),
                "uid": uid,
            })
            new_id = getattr(row, "lastrowid", None)
        _LAST_ERROR = None
        return int(new_id) if new_id is not None else None
    except Exception as exc:                     # noqa: BLE001
        _LAST_ERROR = "留痕失败(%s)：%s" % (action, exc)
        _log(_LAST_ERROR)
        if RAISE_ON_WRITE_ERROR:
            raise
        return None


# ── 读侧 ─────────────────────────────────────────────────────────────────────

def list_records(company_id: Any = None, action: Any = None,
                 limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    """按条件读留痕（`created_at` **倒序**，最新在前）。

    ★ 与 `/api/audit-logs` 的历史行为同口径：不传 `company_id` ⇒ 全量。
      这里**不做权限判断**（权限网关在路由层），只负责取数。
    """
    from database import engine as _engine        # noqa: PLC0415
    from sqlalchemy import text as _text          # noqa: PLC0415
    where: List[str] = []
    params: Dict[str, Any] = {"lim": max(0, int(limit)), "off": max(0, int(offset))}
    if company_id is not None:
        where.append("company_id = :cid")
        params["cid"] = int(company_id)
    if action:
        where.append("action = :ac")
        params["ac"] = str(action)
    sql = "SELECT id, company_id, user_name, action, target, detail, created_at, user_id " \
          "FROM audit_logs"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC, id DESC LIMIT :lim OFFSET :off"
    ensure_schema()
    with _engine.begin() as conn:
        rows = conn.execute(_text(sql), params).fetchall()
    out: List[Dict[str, Any]] = []
    for r in rows:
        item = {
            "id": r[0], "company_id": r[1], "user_name": r[2], "action": r[3],
            "target": r[4], "detail": r[5], "created_at": r[6],
            "user_id": (r[7] if len(r) > 7 else None),
        }
        item["action_cn"] = action_cn(item["action"])
        out.append(item)
    return out


def count(company_id: Any = None, action: Any = None) -> int:
    """计数（供验收/自证；不与 `list_records` 各写一套过滤口径）。"""
    from database import engine as _engine        # noqa: PLC0415
    from sqlalchemy import text as _text          # noqa: PLC0415
    where: List[str] = []
    params: Dict[str, Any] = {}
    if company_id is not None:
        where.append("company_id = :cid")
        params["cid"] = int(company_id)
    if action:
        where.append("action = :ac")
        params["ac"] = str(action)
    sql = "SELECT COUNT(*) FROM audit_logs"
    if where:
        sql += " WHERE " + " AND ".join(where)
    ensure_schema()
    with _engine.begin() as conn:
        return int(conn.execute(_text(sql), params).scalar() or 0)


__all__ = [
    "ACTIONS", "ACTION_CN", "RAISE_ON_WRITE_ERROR",
    "ensure_schema", "record", "list_records", "count",
    "action_cn", "last_error",
]
