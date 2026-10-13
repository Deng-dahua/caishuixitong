# -*- coding: utf-8 -*-
"""资料上传与管理 HTTP 接口（P0-2）。

路径前缀 `/api/v1`（**新增**端点专用；现有 `/api/tax-risk-docs/*` 27 个端点**一字未改**）。

★ 任务书要求的 5 个接口
    POST   /api/v1/projects/{projectId}/documents          （multipart，批量）
    GET    /api/v1/projects/{projectId}/documents
    GET    /api/v1/documents/{documentId}
    DELETE /api/v1/documents/{documentId}
    POST   /api/v1/documents/{documentId}/classify
  另补（任务书"执行内容 8 断点续传"所必需，且下载/字典）：
    GET    /api/v1/documents/meta
    GET    /api/v1/documents/{documentId}/download          （**加水印**）
    POST   /api/v1/documents/chunk/init
    PUT    /api/v1/documents/chunk/{uploadId}/{chunkIndex}
    GET    /api/v1/documents/chunk/{uploadId}
    POST   /api/v1/documents/chunk/{uploadId}/complete

★ 认证：唯一权威 = `security_web.enforce_request_security`（中间件已做），本模块只读
  `request.state.auth`，**不重复实现鉴权**。
★ 错误语义：400 参数/状态非法 ｜ 401 未登录 ｜ 403 无权限 ｜ 404 不存在**或跨租户**
  ｜ 409 状态冲突（如资料未归属项目、会话损坏）。
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from fastapi import (APIRouter, File, Form, HTTPException, Request, UploadFile)
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from engine import document_service as SVC

router = APIRouter(prefix="/api/v1", tags=["资料上传与管理（P0-2）"])

#: 页面路由（**无前缀**）。独立 router ⇒ `main.py` 只需**同一行内**追加一个
#: `include_router` ⇒ 文件行数不变 ⇒ 既有文档的 `main.py:行号` 引用零漂移。
page_router = APIRouter(tags=["资料上传（页面）"])

_ROOT = os.path.dirname(os.path.abspath(__file__))


# --------------------------------------------------------------------------
# 请求体
# --------------------------------------------------------------------------
class ClassifyIn(BaseModel):
    category: str = Field(..., description="目标分类码（见 /meta 的 categories）")
    note: Optional[str] = Field(None, description="修正说明（可选）")


class ParseStatusIn(BaseModel):
    parse_status: str = Field(..., description="解析状态码（见 /meta 的 parse_statuses）")
    note: Optional[str] = None


class ChunkInitIn(BaseModel):
    project_id: int = Field(..., description="所属项目 ID")
    filename: str = Field(..., description="原始文件名（含扩展名）")
    size: int = Field(..., description="文件总字节数")
    md5: Optional[str] = Field(None, description="全文件 MD5（可选；提供则合并后校验）")


# --------------------------------------------------------------------------
# 内部
# --------------------------------------------------------------------------
def _session(request: Request):
    auth = getattr(request.state, "auth", None)
    if auth is None:
        raise HTTPException(status_code=401, detail="未登录")
    return auth


def _call(fn, *args, **kwargs):
    """统一把 Service 业务异常转 HTTP（**唯一转换点**）。"""
    try:
        return fn(*args, **kwargs)
    except SVC.DocumentError as exc:
        raise HTTPException(status_code=int(exc.status), detail=str(exc.message)) from exc


def _watermark_text(session: Any, doc: Dict[str, Any]) -> str:
    from runtime_storage import now_cst              # noqa: PLC0415
    who = str(getattr(session, "username", "") or "未知用户")
    return "内部使用 · %s · %s · 仅供本次核查（%s）" % (
        who, str(now_cst())[:16], str(doc.get("original_name") or "")[:60])


# --------------------------------------------------------------------------
# 元数据（★ 必须注册在 `/{document_id}` 之前）
# --------------------------------------------------------------------------
@router.get("/documents/meta", summary="资料字典（类型/分类/解析状态/上限）")
def documents_meta(request: Request):
    _session(request)
    return SVC.metadata()


# --------------------------------------------------------------------------
# 断点续传（★ 必须先于 `/{document_id}` 注册，否则 `chunk` 会被当成 id）
# --------------------------------------------------------------------------
@router.post("/documents/chunk/init", summary="发起分片上传（断点续传起点）")
def chunk_init(payload: ChunkInitIn, request: Request):
    session = _session(request)
    return _call(SVC.chunk_init, payload.project_id, payload.filename, payload.size,
                 session, md5=payload.md5)


@router.put("/documents/chunk/{upload_id}/{chunk_index}", summary="上传一个分片（幂等）")
async def chunk_put(upload_id: str, chunk_index: int, request: Request):
    session = _session(request)
    content = await request.body()
    return _call(SVC.chunk_put, upload_id, chunk_index, content, session)


@router.get("/documents/chunk/{upload_id}", summary="查询已收/缺失分片（续传依据）")
def chunk_status(upload_id: str, request: Request):
    session = _session(request)
    return _call(SVC.chunk_status, upload_id, session)


@router.post("/documents/chunk/{upload_id}/complete", summary="合并分片并入库")
def chunk_complete(upload_id: str, request: Request):
    session = _session(request)
    return _call(SVC.chunk_complete, upload_id, session, request=request)


# --------------------------------------------------------------------------
# 上传 / 列表（项目维度）
# --------------------------------------------------------------------------
@router.post("/projects/{project_id}/documents", summary="上传资料（multipart，支持批量）",
             status_code=201)
async def upload_documents(
    project_id: int,
    request: Request,
    files: List[UploadFile] = File(..., description="一个或多个文件"),
):
    session = _session(request)
    payload = []
    for f in files:
        payload.append((f.filename or "upload", await f.read()))
    return _call(SVC.upload_documents, project_id, payload, session, request=request)


@router.get("/projects/{project_id}/documents", summary="资料列表（搜索/分类/状态/分页）")
def list_documents(
    project_id: int,
    request: Request,
    q: Optional[str] = None,
    category: Optional[str] = None,
    parse_status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    sort: str = "uploaded_at",
    order: str = "desc",
):
    session = _session(request)
    return _call(SVC.list_documents, project_id, session, q=q, category=category,
                 parse_status=parse_status, page=page, page_size=page_size,
                 sort=sort, order=order)


# --------------------------------------------------------------------------
# 单条：详情 / 下载（水印）/ 删除 / 分类修正 / 解析状态
# --------------------------------------------------------------------------
@router.get("/documents/{document_id}", summary="资料详情（含分页记录）")
def get_document(document_id: int, request: Request):
    session = _session(request)
    return _call(SVC.get_document, document_id, session)


@router.get("/documents/{document_id}/download", summary="下载资料（**加水印**）")
def download_document(document_id: int, request: Request):
    """下载**副本**并加水印；原件**绝不改动**。

    响应头如实报告水印形态（**不静默**）：
      · `X-Watermark-Mode: embedded` ⇒ 已嵌入文件内容；
      · `X-Watermark-Mode: sidecar`  ⇒ 该格式无法嵌入，随附水印信息（`X-Watermark-Text`）。
    """
    from engine.document_watermark import apply_watermark   # noqa: PLC0415
    session = _session(request)
    doc = _call(SVC.get_document, document_id, session, with_pages=False)

    path = str(doc.get("storage_path") or "")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="物理文件不存在（登记存在但文件缺失）")
    with open(path, "rb") as fh:
        content = fh.read()

    text = _watermark_text(session, doc)
    out, mode, message = apply_watermark(str(doc.get("original_name") or ""), content, text)

    # 留痕（任务书要求：上传、删除、**下载**）
    from engine.audit_trail import record as _record        # noqa: PLC0415
    _record("doc.download", target=str(doc.get("original_name") or ""),
            company_id=doc.get("company_id"),
            detail="下载资料（水印：%s）" % ("已嵌入" if mode == "embedded" else "随附说明"),
            request=request)

    fname = str(doc.get("original_name") or "download")
    # ★ HTTP 头只能是 ASCII ⇒ 中文水印文字/说明一律 **URL 编码**后放入（前端 decodeURIComponent 还原）。
    #   （事故：直接放原始中文 ⇒ httpx/Starlette 抛 UnicodeEncodeError 'ascii' codec。）
    headers = {
        "X-Watermark-Mode": mode,
        "X-Watermark-Text": quote(text, safe=""),
        "X-Watermark-Message": quote(message, safe=""),
        "X-Watermark-Text-Encoding": "percent-utf8",
        "Content-Disposition": "attachment; filename*=UTF-8''%s" % quote(fname),
    }
    return Response(content=out, media_type="application/octet-stream", headers=headers)


@router.delete("/documents/{document_id}", summary="删除资料（文件移入回收站）")
def delete_document(document_id: int, request: Request):
    session = _session(request)
    return _call(SVC.delete_document, document_id, session, request=request)


@router.post("/documents/{document_id}/classify", summary="人工修正资料分类")
def classify_document(document_id: int, payload: ClassifyIn, request: Request):
    session = _session(request)
    return _call(SVC.classify_document, document_id, payload.category, session,
                 request=request, note=payload.note)


@router.put("/documents/{document_id}/parse-status", summary="更新解析状态（供解析器调用）")
def set_parse_status(document_id: int, payload: ParseStatusIn, request: Request):
    session = _session(request)
    return _call(SVC.set_parse_status, document_id, payload.parse_status, session,
                 note=payload.note)


# --------------------------------------------------------------------------
# 页面
# --------------------------------------------------------------------------
@page_router.get("/documents", response_class=HTMLResponse, include_in_schema=False)
def documents_page():
    """资料上传与管理页（静态 HTML，无服务端模板）。"""
    path = os.path.join(_ROOT, "static", "documents.html")
    for enc in ("utf-8-sig", "gbk", "gb18030", "utf-8"):
        try:
            with open(path, "r", encoding=enc) as fh:
                return fh.read()
        except (UnicodeDecodeError, LookupError):
            continue
    return "<h1>Encoding error</h1>"
