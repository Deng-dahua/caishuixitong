# -*- coding: utf-8 -*-
"""OCR 引擎治理 HTTP 接口（P1-2）。

路径前缀 `/api/v1`（**新增**端点专用；既有 OCR 调用链一字未改）。

★ 本模块提供的端点
    GET /api/v1/ocr/meta    引擎状态（有哪些引擎、可用性、首选、置信度阈值、最近一次运行）
    GET /api/v1/ocr/runs    最近若干次 OCR 运行留痕（引擎 / 段数 / 耗时 / 低置信度计数）

★ 认证：`security_web.enforce_request_security`（中间件）；权限：`document.view`
  （唯一权威 `engine.rbac.rbac_allows`），不满足 ⇒ 403 且说明缺哪一项。
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/v1", tags=["OCR 引擎治理（P1-2）"])


def _require(request: Request, perm: str):
    auth = getattr(request.state, "auth", None)
    if auth is None:
        raise HTTPException(status_code=401, detail="未登录")
    from engine.rbac import rbac_allows          # noqa: PLC0415
    if not rbac_allows(auth, perm):
        raise HTTPException(status_code=403, detail="缺少权限：%s" % perm)
    return auth


@router.get("/ocr/meta", summary="OCR 引擎状态（可用性 / 首选 / 阈值 / 最近一次运行）")
def ocr_meta(request: Request) -> Dict[str, Any]:
    _require(request, "document.view")
    from engine import ocr_engine as OC          # noqa: PLC0415
    return OC.engine_metadata()


@router.get("/ocr/runs", summary="最近 OCR 运行留痕")
def ocr_runs(request: Request, limit: int = 20) -> Dict[str, Any]:
    _require(request, "document.view")
    from engine import ocr_engine as OC          # noqa: PLC0415
    rows: List[Dict[str, Any]] = list(OC._RUNS)  # noqa: SLF001  — 只读快照
    n = max(0, min(int(limit or 20), 50))
    return {"total": len(rows), "items": rows[-n:] if n else [],
            "note": "留痕仅保存在进程内（重启即清空）；缺失 ≠ 0，列表为空表示本进程尚未执行过 OCR。"}


__all__ = ["router"]
