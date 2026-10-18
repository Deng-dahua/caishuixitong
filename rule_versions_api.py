# -*- coding: utf-8 -*-
"""规则版本管理 HTTP 接口（P1-6）。

路径前缀 `/api/v1`（**新增**端点专用；既有规则/报告链路一字未改）。

★ 端点
    GET  /api/v1/rule-versions                    版本清单（出厂历史 + 台账事件）
    GET  /api/v1/rule-versions/meta               字典（当前版本 / 配置版本 / 版本号规则）
    GET  /api/v1/rule-versions/diff               两版本差异（`?from=&to=`）
    GET  /api/v1/rule-versions/{version}          单版本详情（含是否有快照）
    POST /api/v1/rule-versions/publish            发布新版本
    POST /api/v1/rule-versions/rollback           回滚到历史版本

★ 路由顺序：`meta` / `diff` / `publish` / `rollback` 必须注册在 `{version}` **之前**。
★ 权限：读 `report.view`；写 `ruleversion.manage`。
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from engine import rule_version_admin as ADMIN

from engine.api_common import (admin_of, call_boundary, request_perm,
                             require_perm, session_of)

# ★ R-02（2026-10-17）：以下名字是**别名**，逻辑唯一在 engine/api_common。
#   禁止在本文件重新定义（闸门 `check_api_boundary_single_source` 会报错）。
_perm = request_perm

router = APIRouter(prefix="/api/v1", tags=["规则版本管理（P1-6）"])
page_router = APIRouter(tags=["规则版本管理（页面）"])

_ROOT = os.path.dirname(os.path.abspath(__file__))


def _call(fn, *args, **kwargs):
    """业务异常 → HTTP 的**唯一转换点**在 `engine/api_common.call_boundary`；
    本函数只声明「本域该捕获哪一类业务异常」（ADMIN.RuleVersionError）。"""
    return call_boundary(fn, *args, exc_types=(ADMIN.RuleVersionError,), **kwargs)


@router.get("/rule-versions/meta", summary="规则版本字典（当前/配置版本、版本号规则）")
def rule_versions_meta(request: Request) -> Dict[str, Any]:
    _perm(request, "report.view")
    return ADMIN.metadata()


@router.get("/rule-versions/diff", summary="两版本差异（基于发布时快照）")
def rule_versions_diff(request: Request,
                       from_: str = Query(..., alias="from"),
                       to: str = Query(...)) -> Dict[str, Any]:
    _perm(request, "report.view")
    return _call(ADMIN.diff, from_, to)


@router.get("/rule-versions", summary="规则版本清单")
def list_rule_versions(request: Request) -> Dict[str, Any]:
    _perm(request, "report.view")
    rows: List[Dict[str, Any]] = ADMIN.list_versions()
    return {"current": ADMIN.current_version(), "total": len(rows), "items": rows,
            "note": ("清单 = 出厂历史（config/rule_versions.json）+ 运行期发布/回滚事件；"
                     "同一版本以事件为准（`source=ledger`）。")}


@router.get("/rule-versions/{version}", summary="单版本详情（含是否有快照）")
def get_rule_version(version: str, request: Request) -> Dict[str, Any]:
    _perm(request, "report.view")
    hit = [x for x in ADMIN.list_versions() if str(x.get("version")) == str(version)]
    if not hit:
        raise HTTPException(status_code=404, detail="版本不存在：%s" % version)
    out = dict(hit[0])
    snap = ADMIN.snapshot_of(version)
    out["snapshot_rule_count"] = (len((snap or {}).get("rules") or {}) if snap else 0)
    out["snapshot_note"] = ("" if snap else
                            "该版本没有快照（快照在**发布时**落盘；出厂历史版本无快照）——"
                            "无快照不表示该版本不存在。")
    return out


@router.post("/rule-versions/publish", summary="发布规则集版本")
def publish_rule_version(request: Request,
                         payload: Dict[str, Any] = Body(default_factory=dict)):
    """请求体：`{version: "YYYY.NN", note?}`。"""
    session = _perm(request, "ruleversion.manage")
    body = payload if isinstance(payload, dict) else {}
    return _call(ADMIN.publish, body.get("version"), session,
                 note=str(body.get("note") or ""), request=request)


@router.post("/rule-versions/rollback", summary="回滚到历史版本")
def rollback_rule_version(request: Request,
                          payload: Dict[str, Any] = Body(default_factory=dict)):
    """请求体：`{version: "YYYY.NN", note?}`；目标必须在历史中，否则 400。"""
    session = _perm(request, "ruleversion.manage")
    body = payload if isinstance(payload, dict) else {}
    return _call(ADMIN.rollback_version, body.get("version"), session,
                 note=str(body.get("note") or ""), request=request)


@page_router.get("/rule-versions", response_class=HTMLResponse, include_in_schema=False)
def rule_versions_page():
    """规则版本管理页（静态 HTML，无服务端模板）。"""
    path = os.path.join(_ROOT, "static", "rule_versions.html")
    for enc in ("utf-8-sig", "gbk", "gb18030", "utf-8"):
        try:
            with open(path, "r", encoding=enc) as fh:
                return fh.read()
        except (UnicodeDecodeError, LookupError):
            continue
    return "<h1>Encoding error</h1>"


__all__ = ["router", "page_router"]
