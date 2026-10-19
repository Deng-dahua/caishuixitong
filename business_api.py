# -*- coding: utf-8 -*-
"""工商信息查询 HTTP 接口（2026-10-18 新增）。

路径前缀 `/api/v1/business`（**新增**端点专用；现有 167 个端点一字未改）。

★ 认证与权限
  认证唯一权威 = `security_web.enforce_request_security`（中间件层已写入
  `request.state.auth`），本模块只读、**不重复实现**。
  功能权限：`project.write`（用户要求「必须登录，且具备创建项目的权限」）
  —— 与 `projects_api` 的建项目同权，因为该接口的用途就是**填项目表单**。

★ 为什么是 GET 而不是 POST（与 `/api/tax-risk-docs/export` 的处理不同）
  导出接口写的是**审计留痕**（"报告流出去了"是不可逆的业务事件），必须 POST + CSRF；
  本接口写的是**缓存填充**（同参数多次调用结果一致、可覆盖、7 天后自动过期），
  语义上是"查询并顺带缓存"，属幂等读。故按用户给定的 `GET ...?name=` 实现。
  ★ 若将来在此接口追加任何**业务写**（如改账套主体），必须改 POST。

★ 失败语义
  查询失败**不是** HTTP 错误：返回 200 + `ok=false` + 可读 `message`
  （用户要求"查询超时，请手动填写"且"不能阻断项目创建"）。
  只有"参数非法"（名称过短）才是 400，"项目不存在/越权"是 404。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response

from engine import business_info as BI
from engine import project_service as PSVC

from engine.api_common import require_perm, session_of

# ★ 以下是**别名**，逻辑唯一在 engine/api_common（禁止本文件重新定义）
_require_perm = require_perm
_session = session_of

router = APIRouter(prefix="/api/v1/business", tags=["工商信息查询"])


def _check_project(project_id: Optional[int], session: Any) -> None:
    """`project_id` 若给了就必须真实存在且在当前用户范围内（否则 404，不静默忽略）。"""
    if project_id is None:
        return
    try:
        PSVC.get_project(int(project_id), session)
    except Exception as exc:                                     # noqa: BLE001
        status = int(getattr(exc, "status", 404) or 404)
        detail = str(getattr(exc, "message", None) or exc)
        raise HTTPException(status_code=status, detail=detail) from exc


@router.get("/query", summary="按企业名称查询工商信息（项目表单『自动查填』）")
def query_business_info(
    request: Request,
    response: Response,
    name: str = Query(..., min_length=2, max_length=100, description="企业全称"),
    project_id: Optional[int] = Query(None, description="关联的稽查项目（可选）"),
    refresh: bool = Query(False, description="忽略缓存，强制重新取数"),
) -> Dict[str, Any]:
    session = _session(request)
    _require_perm(session, "project.write")
    # 查询结果含企业工商信息（可能含法定代表人姓名）⇒ 不进任何中间缓存
    response.headers["Cache-Control"] = "no-store"
    _check_project(project_id, session)
    try:
        return BI.query_company(name, project_id=project_id, refresh=bool(refresh))
    except Exception as exc:                                     # noqa: BLE001
        # ★ 兜底：服务层理论上不抛（失败都走 ok=false），真抛了也不能 500 打断前端
        return {"ok": False, "name": str(name), "profile": None, "cache_hit": False,
                "stale": False, "source": "", "source_detail": "", "fetched_at": None,
                "age_hours": None, "elapsed_ms": 0, "attempts": [],
                "code": "internal_error",
                "message": "查询超时，请手动填写",
                "detail": "服务内部异常（%s）：请手工填写后继续，不影响项目创建"
                          % type(exc).__name__,
                "risk_status_warning": None,
                "data_quality": {"missing": [], "notes": []}}


@router.get("/channels", summary="各工商通道的**如实状态**（A/C 是否已配置、哪条现在真能用）")
def business_channels(request: Request, response: Response) -> Dict[str, Any]:
    """返回通道事实（**不是能力声称**）：每条通道的已配置/可用状态与说明。

    ★ 2026-10-19 立：界面与文档长期只写"4 通道工商数据验证"这类**能力声称**，
      读者看不出"哪条现在真能取到数"。本接口把事实集中到唯一来源
      （配置 + 环境变量），供界面如实展示。
    ★ 只读、不触发任何外网请求；密钥类环境变量**只报"是否已配置"，不回显值**。
    """
    session = _session(request)
    _require_perm(session, "project.write")
    response.headers["Cache-Control"] = "no-store"
    return BI.channels()


@router.get("/cached", summary="只看本地已落库的工商档案（不触发外网请求）")
def cached_business_info(
    request: Request,
    response: Response,
    name: str = Query(..., min_length=2, max_length=100),
) -> Dict[str, Any]:
    session = _session(request)
    _require_perm(session, "project.write")
    response.headers["Cache-Control"] = "no-store"
    prof = BI.BusinessInfoService().cached(name)
    if not prof:
        return {"ok": False, "found": False, "name": name, "profile": None,
                "message": "本地未落库该企业"}
    return {"ok": True, "found": True, "name": prof.get("name"), "profile": prof,
            "age_hours": prof.get("age_hours"),
            "message": "命中本地档案（%s）" % (prof.get("source_detail") or prof.get("source") or ""),
            "stale": (prof.get("age_hours") or 0) > float(
                (BI.config().get("cache") or {}).get("ttl_hours") or 168)}


__all__ = ["router"]
