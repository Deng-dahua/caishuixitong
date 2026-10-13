# -*- coding: utf-8 -*-
"""资料（P0-2）**Service 层**：上传 / 查重 / 分类 / 列表 / 详情 / 删除 / 分类修正 / 断点续传 / 审计。

三处唯一权威（均为薄转发，勿另立第二套）：
  · 存储路径  → `runtime_storage.company_upload_dir()`（`data/uploads/<cid>/`）
  · 删除      → `runtime_storage.move_to_trash()`（**移入回收站，不物理删除**）
  · 时间      → `runtime_storage.now_cst()`
  · 审计      → `engine.audit_trail.record()`
  · 类型/分类 → `engine.document_types`（读 `filename_type_map.json` + `document_categories.json`）
  · 项目可见性 → `engine.project_service._fetch_visible`（**租户隔离复用 P0-1，不重复实现**）

★ 查重口径（须明确，否则会误解）
  去重范围 = **同一项目（project）**。理由：同一份资料在**不同项目**里是**合法且必要**的
  （两个项目可能是同一企业的不同期间/不同口径复核），按公司去重会导致"B 项目传不进去"。
  同时仍会检测「**同一公司内其他项目已有同内容文件**」并在响应里提示（`same_content_elsewhere`），
  既做到查重、又不阻断合法场景。

★ 大文件
  单请求上限沿用既有 **10MB**（不改口径）；**分片上传**（断点续传）单文件上限
  `document_types.RESUMABLE_MAX_SIZE`（200MB），且该放宽**只作用于分片路径**。
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple

from engine.document_store import ensure_schema
from engine.document_types import (
    CHUNK_SIZE, EXT_CN, MAX_UPLOAD_SIZE, OTHER_CATEGORY, PARSE_STATUS_CN,
    PARSE_STATUSES, PARSE_STATUS_FLOW, RESUMABLE_MAX_SIZE, category_cn,
    ext_of, guess_category, mask_sensitive, validate_category, validate_content,
    validate_parse_status,
)


class DocumentError(Exception):
    """业务异常：携带 HTTP 状态码，由 API 层**原样转发**。"""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = int(status)


# --------------------------------------------------------------------------
# 基础设施薄转发
# --------------------------------------------------------------------------
def _engine_or_default(engine):
    if engine is not None:
        return engine
    from database import engine as _engine            # noqa: PLC0415
    return _engine


def _now() -> str:
    from runtime_storage import now_cst               # noqa: PLC0415
    return now_cst()


def _upload_dir(company_id: Any) -> str:
    from runtime_storage import company_upload_dir as _cud    # noqa: PLC0415
    return str(_cud(int(company_id)))


def _safe_filename(name: str, fallback: str = "upload") -> str:
    from runtime_storage import safe_filename as _sf  # noqa: PLC0415
    return _sf(name, fallback)


def _to_trash(path: str) -> bool:
    from runtime_storage import move_to_trash as _mt  # noqa: PLC0415
    return bool(_mt(path))


def _audit(action: str, *, target: Any, company_id: Any, detail: Any,
           request: Any = None) -> None:
    from engine.audit_trail import record as _record   # noqa: PLC0415
    _record(action, target=target, company_id=company_id, detail=detail, request=request)


def _legacy_bridge(entry: Dict[str, Any]) -> None:
    """把新接口上传的资料**登记进既有资料清单**（`shared_state._tax_risk_docs`）。

    ★ 为什么必须做：既有清单是**一键分析的输入源**。若不登记，用户在新页面传了资料、
      分析却看不到 ⇒ 功能缺口。
    ★ 为什么安全：同一目录、同一编号空间、同一字段形状 ⇒ 不产生"两份资料"；
      既有清单的写入逻辑（`main.py` 的上传处理器）**一字未改**。
    """
    try:
        import shared_state as _ss                    # noqa: PLC0415
        _ss._tax_risk_docs.append(entry)              # noqa: SLF001
    except Exception:                                 # noqa: BLE001
        # 桥接失败不得影响上传本身；但**必须留痕**（不静默）
        from engine.audit_trail import record as _rec  # noqa: PLC0415
        _rec("doc.upload", target=str(entry.get("original_name") or ""),
             company_id=entry.get("company_id"),
             detail="⚠ 已落盘但未能登记进既有资料清单（一键分析可能看不到本文件）")


def _next_legacy_id() -> int:
    """取既有编号空间的下一个 id（**单一编号空间**，避免两套 id 冲突）。"""
    try:
        import main as _main                          # noqa: PLC0415
        _main._tax_doc_counter[0] += 1                # noqa: SLF001
        return int(_main._tax_doc_counter[0])
    except Exception:                                 # noqa: BLE001
        return int(uuid.uuid4().int % 2_000_000_000)


# --------------------------------------------------------------------------
# 项目可见性（★ 租户隔离复用 P0-1）
# --------------------------------------------------------------------------
def _project_row(conn, session: Any, project_id: Any) -> Dict[str, Any]:
    """取项目行（复用 P0-1 的可见性判定）。

    ★ 事故修正：`project_service._fetch_visible` 抛的是 `ProjectError`，
      而本模块 API 层只捕 `DocumentError` ⇒ 跨租户会变成 **HTTP 500**
      （把"无权访问"误报成"服务端故障"）。**必须在此边界转换异常类型**，
      且**保持原状态码**（404 ⇒ 404，不降级为 400）。
    """
    from engine.project_service import ProjectError, _fetch_visible   # noqa: PLC0415
    try:
        return _fetch_visible(conn, session, project_id)
    except ProjectError as exc:
        raise DocumentError(str(exc.message), int(exc.status)) from exc


def _document_row(conn, session: Any, document_id: Any) -> Dict[str, Any]:
    """取一条**当前用户可见**的资料（经其所属项目的租户隔离判定）。

    不可见 ⇒ 404（**不泄露存在性**），与 P0-1 口径一致。
    """
    from sqlalchemy import text as _text              # noqa: PLC0415
    try:
        did = int(document_id)
    except Exception:                                 # noqa: BLE001
        raise DocumentError("资料 ID 非法", 400)
    row = conn.execute(_text("SELECT * FROM documents WHERE id=:d"), {"d": did}).first()
    if row is None:
        raise DocumentError("资料不存在或无权访问", 404)
    rec = dict(row._mapping)
    pid = rec.get("project_id")
    if pid in (None, ""):
        raise DocumentError("资料未归属任何项目，无法判定权限", 409)
    _project_row(conn, session, pid)                  # 权限前置（跨租户 ⇒ 404）
    return rec


def _row_to_doc(rec: Dict[str, Any], *, with_masked: bool = True) -> Dict[str, Any]:
    out = dict(rec)
    out["ext_cn"] = EXT_CN.get(str(out.get("ext") or ""), str(out.get("ext") or ""))
    out["category_cn"] = category_cn(str(out.get("category") or OTHER_CATEGORY))
    out["parse_status_cn"] = PARSE_STATUS_CN.get(
        str(out.get("parse_status") or ""), str(out.get("parse_status") or ""))
    if with_masked:
        # ★ 脱敏**只作用于展示字段**；`original_name` 原样保留（可追溯性铁律）
        out["original_name_masked"] = mask_sensitive(str(out.get("original_name") or ""))
    return out


def _validate_status_transition(old: str, new: str) -> None:
    if old == new:
        return
    if new not in PARSE_STATUS_FLOW.get(str(old), ()):
        raise DocumentError(
            "解析状态非法迁移：%s → %s（允许：%s）"
            % (PARSE_STATUS_CN.get(old, old), PARSE_STATUS_CN.get(new, new),
               "、".join(PARSE_STATUS_CN.get(s, s)
                         for s in PARSE_STATUS_FLOW.get(old, ())) or "无"),
            400)


def _v400(fn, *args, **kwargs):
    """把 `document_types` 的 `ValueError`（参数非法）**统一转成 400**。

    ★ 事故：`validate_category` 抛的是 `ValueError`，而 API 层只捕 `DocumentError`
      ⇒ 非法分类会变成 **HTTP 500**（把"用户传错了参数"误报成"服务端故障"）。
      在 Service 边界统一转换，是唯一正确的位置（API 层不必逐个知道哪个校验器抛什么）。
    """
    try:
        return fn(*args, **kwargs)
    except ValueError as exc:
        if isinstance(exc, DocumentError):            # 已经是业务异常 ⇒ 原样
            raise
        raise DocumentError(str(exc), 400) from exc


# --------------------------------------------------------------------------
# 上传
# --------------------------------------------------------------------------
def upload_documents(project_id: Any, files: Iterable[Tuple[str, bytes]], session: Any, *,
                     engine=None, request: Any = None,
                     max_size: int = MAX_UPLOAD_SIZE) -> Dict[str, Any]:
    """批量上传（`files` = [(原始文件名, 字节), …]）。

    `max_size`：单文件上限。**默认 = 既有单请求口径**（10MB，不改既有策略）；
    分片上传合并后由 `chunk_complete` 传入 `RESUMABLE_MAX_SIZE`（**该放宽只作用于分片路径**）。

    返回 `{uploaded: [...], duplicated: [...], rejected: [...], stats: {...}}`。
    **失败与跳过都如实回执**（不粉饰、不静默）。
    """
    eng = _engine_or_default(engine)
    ensure_schema(eng)
    from sqlalchemy import text as _text              # noqa: PLC0415

    with eng.connect() as conn:
        prow = _project_row(conn, session, project_id)
    pid = int(prow["id"])
    cid = prow.get("company_id")
    if cid in (None, ""):
        raise DocumentError("项目未关联账套，无法存放资料", 409)
    cid = int(cid)

    udir = _upload_dir(cid)
    os.makedirs(udir, exist_ok=True)
    uname = str(getattr(session, "username", "") or "")
    ts = _now()

    uploaded: List[Dict[str, Any]] = []
    duplicated: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []

    for raw_name, content in files:
        name = str(raw_name or "").strip() or "upload"
        ext = ext_of(name)
        try:
            validate_content(name, content, max_size=max_size)
        except ValueError as exc:
            rejected.append({"filename": name, "reason": str(exc)})
            continue

        md5 = hashlib.md5(content).hexdigest()
        sha256 = hashlib.sha256(content).hexdigest()

        with eng.connect() as conn:
            # ① 同项目内查重
            dup = conn.execute(_text(
                "SELECT id, original_name FROM documents "
                "WHERE project_id=:p AND (md5=:m OR sha256=:s) LIMIT 1"
            ), {"p": pid, "m": md5, "s": sha256}).first()
            if dup:
                duplicated.append({
                    "filename": name, "md5": md5,
                    "duplicate_of": int(dup[0]),
                    "duplicate_of_name": str(dup[1]),
                    "scope": "project",
                    "reason": "同一项目内已存在相同内容（MD5/SHA256 一致）",
                })
                continue
            # ② 公司内其他项目的同内容文件 ⇒ **提示但不跳过**
            elsewhere = conn.execute(_text(
                "SELECT id, project_id FROM documents "
                "WHERE company_id=:c AND md5=:m AND project_id<>:p LIMIT 1"
            ), {"c": cid, "m": md5, "p": pid}).first()
        other_hit = ({"id": int(elsewhere[0]), "project_id": int(elsewhere[1])}
                     if elsewhere else None)

        doc_id = _next_legacy_id()
        fname = "%s_%s_%s" % (cid, doc_id, _safe_filename(name))
        fpath = os.path.join(udir, fname)
        saved = False
        try:
            with open(fpath, "wb") as fh:
                fh.write(content)
            saved = True
        except PermissionError:
            saved = False                             # 沙箱/权限不足：仍登记，如实标注

        category, doc_type = guess_category(name)
        with eng.begin() as conn:
            row = conn.execute(_text(
                "INSERT INTO documents (project_id, company_id, doc_id, filename, original_name, "
                " ext, size, md5, sha256, doc_type, category, classify_by, parse_status, "
                " page_count, storage_path, uploaded_by, uploaded_at, updated_at) "
                "VALUES (:pid,:cid,:did,:fn,:on,:ext,:sz,:m,:s,:dt,:cat,'auto','pending',0,"
                " :sp,:ub,:ts,:ts) RETURNING id"
            ), {
                "pid": pid, "cid": cid, "did": doc_id, "fn": fname, "on": name,
                "ext": ext, "sz": len(content), "m": md5, "s": sha256,
                "dt": doc_type or "", "cat": category, "sp": fpath,
                "ub": uname, "ts": ts,
            }).first()
            new_id = int(row[0])

        _legacy_bridge({
            "id": doc_id, "filename": fname, "original_name": name,
            "path": fpath, "size": len(content), "md5": md5, "sha256": sha256,
            "uploaded_at": ts, "company_id": cid, "file_saved": saved,
        })

        item = {"id": new_id, "doc_id": doc_id, "original_name": name,
                "original_name_masked": mask_sensitive(name),
                "category": category, "category_cn": category_cn(category),
                "doc_type": doc_type, "size": len(content), "md5": md5,
                "sha256": sha256, "file_saved": saved}
        if other_hit:
            item["same_content_elsewhere"] = other_hit
        uploaded.append(item)

    if uploaded:
        _audit("doc.upload",
               target="、".join(str(u["original_name"]) for u in uploaded)[:400],
               company_id=cid,
               detail="项目 %s：成功 %d 个%s%s"
                      % (prow.get("code") or pid, len(uploaded),
                         ("；跳过重复 %d 个" % len(duplicated)) if duplicated else "",
                         ("；拒绝 %d 个" % len(rejected)) if rejected else ""),
               request=request)

    return {"uploaded": uploaded, "duplicated": duplicated, "rejected": rejected,
            "stats": {"uploaded": len(uploaded), "duplicated": len(duplicated),
                      "rejected": len(rejected),
                      "max_size": MAX_UPLOAD_SIZE, "chunk_size": CHUNK_SIZE},
            "message": "成功 %d 个%s%s"
                       % (len(uploaded),
                          ("，跳过重复 %d 个" % len(duplicated)) if duplicated else "",
                          ("，拒绝 %d 个" % len(rejected)) if rejected else "")}


# --------------------------------------------------------------------------
# 查询
# --------------------------------------------------------------------------
def list_documents(project_id: Any, session: Any, *, engine=None, q: Any = None,
                   category: Any = None, parse_status: Any = None,
                   page: Any = 1, page_size: Any = 20,
                   sort: Any = "uploaded_at", order: Any = "desc") -> Dict[str, Any]:
    eng = _engine_or_default(engine)
    ensure_schema(eng)
    from sqlalchemy import text as _text              # noqa: PLC0415

    with eng.connect() as conn:
        prow = _project_row(conn, session, project_id)
    pid = int(prow["id"])

    where, params = ["d.project_id = :pid"], {"pid": pid}
    kw = str(q or "").strip()
    if kw:
        where.append("(d.original_name LIKE :kw OR d.filename LIKE :kw)")
        params["kw"] = "%" + kw + "%"
    cat = str(category or "").strip()
    if cat:
        where.append("d.category = :cat")
        params["cat"] = _v400(validate_category, cat)
    st = str(parse_status or "").strip()
    if st:
        where.append("d.parse_status = :st")
        params["st"] = _v400(validate_parse_status, st)

    cols = {"uploaded_at": "d.uploaded_at", "size": "d.size",
            "original_name": "d.original_name"}
    order_by = cols.get(str(sort or "").strip(), "d.uploaded_at")
    direction = "ASC" if str(order or "").lower() == "asc" else "DESC"
    try:
        page_i = max(1, int(page))
    except Exception:                                 # noqa: BLE001
        page_i = 1
    try:
        size_i = max(1, min(int(page_size), 200))
    except Exception:                                 # noqa: BLE001
        size_i = 20
    params["_limit"], params["_offset"] = size_i, (page_i - 1) * size_i

    clause = " AND ".join(where)
    with eng.connect() as conn:
        total = int(conn.execute(_text(
            "SELECT COUNT(*) FROM documents d WHERE " + clause), params).first()[0] or 0)
        rows = conn.execute(_text(
            "SELECT * FROM documents d WHERE " + clause +
            " ORDER BY %s %s, d.id DESC LIMIT :_limit OFFSET :_offset"
            % (order_by, direction)), params).all()
        by_cat = {str(r[0]): int(r[1]) for r in conn.execute(_text(
            "SELECT category, COUNT(*) FROM documents WHERE project_id=:pid GROUP BY category"
        ), {"pid": pid}).all()}
    return {"items": [_row_to_doc(dict(r._mapping)) for r in rows],
            "total": total, "page": page_i, "page_size": size_i,
            "pages": (total + size_i - 1) // size_i if total else 0,
            "category_counts": {k: v for k, v in by_cat.items()},
            "category_counts_cn": {category_cn(k): v for k, v in by_cat.items()}}


def get_document(document_id: Any, session: Any, *, engine=None,
                 with_pages: bool = True) -> Dict[str, Any]:
    eng = _engine_or_default(engine)
    ensure_schema(eng)
    from sqlalchemy import text as _text              # noqa: PLC0415
    with eng.connect() as conn:
        rec = _document_row(conn, session, document_id)
        out = _row_to_doc(rec)
        if with_pages:
            out["pages"] = [dict(r._mapping) for r in conn.execute(_text(
                "SELECT page_no, char_count, status FROM document_pages "
                "WHERE document_id=:d ORDER BY page_no"), {"d": rec["id"]}).all()]
        out["watermark_on_download"] = True
    return out


def save_pages(document_id: Any, pages: Iterable[Dict[str, Any]], session: Any, *,
               engine=None) -> Dict[str, Any]:
    """落盘分页解析结果（供解析器调用）。`pages` = [{page_no, char_count, excerpt, status}]。"""
    eng = _engine_or_default(engine)
    ensure_schema(eng)
    from sqlalchemy import text as _text              # noqa: PLC0415
    ts = _now()
    n = 0
    with eng.begin() as conn:
        rec = _document_row(conn, session, document_id)
        conn.execute(_text("DELETE FROM document_pages WHERE document_id=:d"),
                     {"d": rec["id"]})
        for p in pages:
            conn.execute(_text(
                "INSERT INTO document_pages (document_id, page_no, char_count, excerpt, "
                " status, created_at) VALUES (:d,:n,:c,:e,:s,:ts)"
            ), {"d": rec["id"], "n": int(p.get("page_no") or 0),
                "c": int(p.get("char_count") or 0),
                "e": str(p.get("excerpt") or "")[:2000],
                "s": _v400(validate_parse_status, p.get("status") or "success"), "ts": ts})
            n += 1
        conn.execute(_text("UPDATE documents SET page_count=:n, updated_at=:ts WHERE id=:d"),
                     {"n": n, "ts": ts, "d": rec["id"]})
    return {"ok": True, "document_id": int(rec["id"]), "page_count": n}


def set_parse_status(document_id: Any, status: Any, session: Any, *, engine=None,
                     note: Any = None) -> Dict[str, Any]:
    eng = _engine_or_default(engine)
    ensure_schema(eng)
    from sqlalchemy import text as _text              # noqa: PLC0415
    new = _v400(validate_parse_status, status)
    with eng.begin() as conn:
        rec = _document_row(conn, session, document_id)
        _validate_status_transition(str(rec.get("parse_status") or "pending"), new)
        conn.execute(_text(
            "UPDATE documents SET parse_status=:s, note=COALESCE(:nt, note), updated_at=:ts "
            "WHERE id=:d"), {"s": new, "nt": (str(note) if note is not None else None),
                             "ts": _now(), "d": rec["id"]})
    return {"ok": True, "id": int(rec["id"]), "parse_status": new,
            "parse_status_cn": PARSE_STATUS_CN[new]}


def classify_document(document_id: Any, category: Any, session: Any, *, engine=None,
                      request: Any = None, note: Any = None) -> Dict[str, Any]:
    """**人工修正分类**（`classify_by` 置 `manual`，防自动识别回改）。"""
    eng = _engine_or_default(engine)
    ensure_schema(eng)
    from sqlalchemy import text as _text              # noqa: PLC0415
    cat = _v400(validate_category, category)
    with eng.begin() as conn:
        rec = _document_row(conn, session, document_id)
        old = str(rec.get("category") or OTHER_CATEGORY)
        conn.execute(_text(
            "UPDATE documents SET category=:c, classify_by='manual', "
            " note=COALESCE(:nt, note), updated_at=:ts WHERE id=:d"
        ), {"c": cat, "nt": (str(note) if note is not None else None),
            "ts": _now(), "d": rec["id"]})
    _audit("doc.classify", target=str(rec.get("original_name") or ""),
           company_id=rec.get("company_id"),
           detail="分类 %s → %s（人工修正）" % (category_cn(old), category_cn(cat)),
           request=request)
    return {"ok": True, "id": int(rec["id"]), "category": cat,
            "category_cn": category_cn(cat), "classify_by": "manual",
            "previous_category": old, "previous_category_cn": category_cn(old)}


# --------------------------------------------------------------------------
# 删除
# --------------------------------------------------------------------------
def delete_document(document_id: Any, session: Any, *, engine=None,
                    request: Any = None) -> Dict[str, Any]:
    """删除资料：文件**移入回收站**（可追溯）+ 删登记行 + 从既有清单移除 + 留痕。"""
    eng = _engine_or_default(engine)
    ensure_schema(eng)
    from sqlalchemy import text as _text              # noqa: PLC0415
    with eng.begin() as conn:
        rec = _document_row(conn, session, document_id)
        path = str(rec.get("storage_path") or "")
        moved = _to_trash(path) if path and os.path.exists(path) else False
        conn.execute(_text("DELETE FROM document_pages WHERE document_id=:d"),
                     {"d": rec["id"]})
        conn.execute(_text("DELETE FROM documents WHERE id=:d"), {"d": rec["id"]})

    # 同步从既有资料清单移除（否则一键分析仍会读到已删资料）
    try:
        import shared_state as _ss                    # noqa: PLC0415
        _ss._tax_risk_docs[:] = [              # noqa: SLF001
            d for d in _ss._tax_risk_docs if int(d.get("id") or -1) != int(rec.get("doc_id") or -2)
        ]
    except Exception:                                 # noqa: BLE001
        pass

    _audit("doc.delete", target=str(rec.get("original_name") or ""),
           company_id=rec.get("company_id"),
           detail="删除资料（文件%s）" % ("已移入回收站" if moved else "未找到物理文件"),
           request=request)
    return {"ok": True, "id": int(rec["id"]),
            "moved_to_trash": moved,
            "message": "资料已删除" + ("（文件已移入回收站，可追溯）" if moved
                                       else "（未找到物理文件，仅删登记）")}


# --------------------------------------------------------------------------
# 断点续传
# --------------------------------------------------------------------------
def _sessions_root() -> str:
    from runtime_storage import DATA_DIR              # noqa: PLC0415
    root = os.path.join(str(DATA_DIR), "upload_sessions")
    os.makedirs(root, exist_ok=True)
    return root


def _session_path(upload_id: str) -> str:
    return os.path.join(_sessions_root(), "%s.json" % upload_id)


def _load_session(upload_id: str) -> Dict[str, Any]:
    p = _session_path(upload_id)
    if not os.path.exists(p):
        raise DocumentError("上传会话不存在或已过期", 404)
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:                                 # noqa: BLE001
        raise DocumentError("上传会话已损坏，请重新发起", 409)


def _save_session(sess: Dict[str, Any]) -> None:
    from runtime_storage import atomic_write_json as _awj   # noqa: PLC0415
    _awj(_session_path(str(sess["upload_id"])), sess)


def chunk_init(project_id: Any, filename: Any, size: Any, session: Any, *,
               engine=None, md5: Any = None) -> Dict[str, Any]:
    """发起分片上传会话（断点续传的起点）。"""
    eng = _engine_or_default(engine)
    ensure_schema(eng)
    name = str(filename or "").strip()
    ext = ext_of(name)
    from engine.document_types import ALLOWED_EXTENSIONS   # noqa: PLC0415
    if ext not in ALLOWED_EXTENSIONS:
        raise DocumentError("不支持的文件类型：%s" % (ext or "(无扩展名)"), 400)
    try:
        total_size = int(size)
    except Exception:                                 # noqa: BLE001
        raise DocumentError("文件大小非法", 400)
    if total_size <= 0:
        raise DocumentError("文件大小必须为正", 400)
    if total_size > RESUMABLE_MAX_SIZE:
        raise DocumentError("文件超过分片上传上限 %.0fMB"
                            % (RESUMABLE_MAX_SIZE / 1024 / 1024), 400)

    with eng.connect() as conn:
        prow = _project_row(conn, session, project_id)
    cid = prow.get("company_id")
    if cid in (None, ""):
        raise DocumentError("项目未关联账套，无法存放资料", 409)

    upload_id = uuid.uuid4().hex
    chunks_total = (total_size + CHUNK_SIZE - 1) // CHUNK_SIZE
    os.makedirs(os.path.join(_sessions_root(), upload_id), exist_ok=True)
    sess = {"upload_id": upload_id, "project_id": int(prow["id"]),
            "company_id": int(cid), "filename": name, "size": total_size,
            "md5": str(md5 or ""), "chunk_size": CHUNK_SIZE,
            "chunks_total": chunks_total, "received": [],
            "uploaded_by": str(getattr(session, "username", "") or ""),
            "created_at": _now()}
    _save_session(sess)
    return {"upload_id": upload_id, "chunk_size": CHUNK_SIZE,
            "chunks_total": chunks_total, "size": total_size,
            "resumable_max_size": RESUMABLE_MAX_SIZE,
            "message": "请按 chunk_index（0 起）上传 %d 个分片" % chunks_total}


def chunk_put(upload_id: str, chunk_index: Any, content: bytes, session: Any, *,
              engine=None) -> Dict[str, Any]:
    """上传一个分片；重复上传同一分片**幂等**（覆盖）。"""
    eng = _engine_or_default(engine)
    ensure_schema(eng)
    sess = _load_session(upload_id)
    with eng.connect() as conn:
        _project_row(conn, session, sess["project_id"])   # 权限前置
    try:
        idx = int(chunk_index)
    except Exception:                                 # noqa: BLE001
        raise DocumentError("分片序号非法", 400)
    if not (0 <= idx < int(sess["chunks_total"])):
        raise DocumentError("分片序号越界（应在 0~%d）" % (int(sess["chunks_total"]) - 1), 400)
    if len(content) > CHUNK_SIZE:
        raise DocumentError("分片超过 %dMB" % (CHUNK_SIZE // 1024 // 1024), 400)
    cdir = os.path.join(_sessions_root(), str(upload_id))
    os.makedirs(cdir, exist_ok=True)
    with open(os.path.join(cdir, "%06d.part" % idx), "wb") as fh:
        fh.write(content)
    got = set(int(x) for x in sess.get("received") or [])
    got.add(idx)
    sess["received"] = sorted(got)
    _save_session(sess)
    missing = [i for i in range(int(sess["chunks_total"])) if i not in got]
    return {"ok": True, "upload_id": upload_id, "received": len(got),
            "chunks_total": int(sess["chunks_total"]),
            "missing": missing[:100], "complete": not missing}


def chunk_status(upload_id: str, session: Any, *, engine=None) -> Dict[str, Any]:
    """查询已收/缺失分片 ⇒ **断点续传的依据**。"""
    eng = _engine_or_default(engine)
    ensure_schema(eng)
    sess = _load_session(upload_id)
    with eng.connect() as conn:
        _project_row(conn, session, sess["project_id"])
    got = set(int(x) for x in sess.get("received") or [])
    missing = [i for i in range(int(sess["chunks_total"])) if i not in got]
    return {"upload_id": upload_id, "filename": sess["filename"],
            "received": sorted(got), "missing": missing,
            "chunks_total": int(sess["chunks_total"]),
            "complete": not missing, "created_at": sess.get("created_at")}


def chunk_complete(upload_id: str, session: Any, *, engine=None,
                   request: Any = None) -> Dict[str, Any]:
    """合并分片 ⇒ 走**同一套**入库链路（校验/查重/分类/桥接/留痕）。"""
    eng = _engine_or_default(engine)
    ensure_schema(eng)
    sess = _load_session(upload_id)
    cdir = os.path.join(_sessions_root(), str(upload_id))
    total = int(sess["chunks_total"])
    parts = [os.path.join(cdir, "%06d.part" % i) for i in range(total)]
    missing = [i for i, p in enumerate(parts) if not os.path.exists(p)]
    if missing:
        raise DocumentError("分片缺失，无法合并：%s" % missing[:20], 400)
    buf = bytearray()
    for p in parts:
        with open(p, "rb") as fh:
            buf.extend(fh.read())
    if len(buf) != int(sess["size"]):
        raise DocumentError("合并后大小不符（期望 %d，实际 %d）"
                            % (int(sess["size"]), len(buf)), 400)
    if sess.get("md5"):
        got = hashlib.md5(bytes(buf)).hexdigest()
        if got != sess["md5"]:
            raise DocumentError("MD5 校验失败（期望 %s，实际 %s）" % (sess["md5"], got), 400)

    res = upload_documents(sess["project_id"], [(sess["filename"], bytes(buf))],
                           session, engine=eng, request=request,
                           max_size=RESUMABLE_MAX_SIZE)   # ★ 分片路径用分片上限（非 10MB）
    # 清理会话（成功或查重都清；**失败保留**以便重试）
    _cleanup_upload_session(upload_id)
    res["upload_id"] = upload_id
    res["resumed"] = True
    return res


def _cleanup_upload_session(upload_id: str) -> tuple:
    """清理**上传会话**（分片目录 + 会话 JSON）。

    ★ 这是**声明的删除出口**（已登记 `check_delete_exits::_EXITS`）：
      语义范围 = **上传会话临时态**（`data/upload_sessions/<id>/` 与 `<id>.json`），
      **不含**任何用户资料 / 报告交付物（那些各有专属业务出口）。
      实现走唯一权威 `runtime_storage` 的目录级原语 `purge_tree`（**移入回收站，不物理删除**）
      —— 本函数**不自行** `rmtree`/`os.remove`（那会绕过删除出口铁律）。
    返回 `(ok, reason)`；调用方须依据返回值判断，失败时**如实留痕**（不谎报）。
    """
    from runtime_storage import purge_tree as _purge_tree     # noqa: PLC0415
    cdir = os.path.join(_sessions_root(), str(upload_id))
    sentinel = os.path.join(_sessions_root(), "%s.json" % upload_id)
    results = []
    if os.path.isdir(cdir):
        results.append(_purge_tree(cdir))
    if os.path.exists(sentinel):
        results.append(_purge_tree(sentinel))
    ok = all(bool(r[0]) for r in results) if results else True
    reason = "；".join(str(r[1]) for r in results) if results else "无需清理"
    if not ok:
        # ★ 不静默：清理失败必须可见（残留分片会占磁盘）
        try:
            from engine.audit_trail import record as _rec   # noqa: PLC0415
            _rec("doc.upload", target=str(upload_id),
                 detail="⚠ 上传会话清理未完全成功：%s（可能有分片残留）" % reason)
        except Exception:                                   # noqa: BLE001
            pass
    return ok, reason


# --------------------------------------------------------------------------
# 元数据（字典唯一来源）
# --------------------------------------------------------------------------
def metadata() -> Dict[str, Any]:
    from engine.document_types import (ALLOWED_EXTENSIONS, CATEGORY_CN,   # noqa: PLC0415
                                      CLASSIFY_SOURCE_CN, EXT_CN)
    from engine.document_watermark import EMBEDDABLE          # noqa: PLC0415
    return {
        "extensions": [{"value": e, "label": EXT_CN.get(e, e)}
                       for e in sorted(ALLOWED_EXTENSIONS)],
        "categories": [{"value": k, "label": v} for k, v in CATEGORY_CN.items()],
        "parse_statuses": [{"value": s, "label": PARSE_STATUS_CN[s]}
                           for s in PARSE_STATUSES],
        "classify_sources": [{"value": k, "label": v} for k, v in CLASSIFY_SOURCE_CN.items()],
        "limits": {"max_size": MAX_UPLOAD_SIZE, "chunk_size": CHUNK_SIZE,
                   "resumable_max_size": RESUMABLE_MAX_SIZE},
        "storage": "本地文件系统（本项目无对象存储；路径权威 runtime_storage.company_upload_dir）",
        "watermark": {
            "embeddable": sorted(EMBEDDABLE),
            "sidecar_note": "非 PDF/图片格式无法嵌入可视水印，将随附水印信息且如实标注",
        },
    }


__all__ = [
    "DocumentError", "upload_documents", "list_documents", "get_document",
    "save_pages", "set_parse_status", "classify_document", "delete_document",
    "chunk_init", "chunk_put", "chunk_status", "chunk_complete", "metadata",
]
