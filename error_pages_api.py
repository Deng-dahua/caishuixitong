# -*- coding: utf-8 -*-
"""页面级错误兜底（**唯一权威**）：把「页面路径」的错误渲染成人话 HTML。

★ 为什么需要它（2026-10-14 实测）
  访问 `/risks` 时浏览器把 `{"detail":"Not Found"}` 直接摊在空白页上（用户截图即此）；
  500/503 同样把 JSON 摊出来。页面路径出错应当给**人话 + 处置动作**。

★ 与 API 的边界（不可越界）
  `/api/**`、`/static/**`、`/docs`、`/openapi.json` 一律**保持 JSON/原样语义不变** ——
  接口调用方靠状态码 + JSON 结构判定，不能被 HTML 污染。

★ 与「服务版本可见化」（`engine/runtime_version.py`）联动
  错误页会带上**当前服务启动时间**；若检测到"进程载入的代码已被磁盘更新"，则红字直说
  「请重启」——这正是 `/risks` 404 那类事故的**根治提示**（不是改代码，而是重启）。
"""
from __future__ import annotations

import html as _html
from typing import Any, Optional, Tuple

from fastapi.responses import HTMLResponse, JSONResponse

from database import is_db_busy_error, is_db_readonly_error

# 这些前缀下的错误**不得**被 HTML 化（保持原语义）
_JSON_PREFIXES = ("/api/", "/static/", "/docs", "/redoc", "/openapi.json")

_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>%(title)s - 财税风险防控系统</title>
<style>
  body{margin:0;background:#f8fafc;color:#0f172a;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif}
  .wrap{max-width:760px;margin:8vh auto;padding:0 20px}
  .card{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:28px 30px;box-shadow:0 1px 3px rgba(15,23,42,.06)}
  .code{font-size:44px;font-weight:800;color:%(accent)s;line-height:1}
  h1{font-size:19px;margin:10px 0 6px}
  .path{font-family:ui-monospace,Consolas,monospace;background:#f1f5f9;border-radius:5px;padding:2px 7px;font-size:12.5px;color:#334155}
  .msg{margin:14px 0 4px;font-size:14px;color:#334155;line-height:1.8}
  ul{margin:10px 0 0;padding-left:20px;font-size:13.5px;color:#475569;line-height:2}
  .stale{margin:16px 0 0;padding:12px 14px;background:#fef2f2;border:1px solid #fecaca;border-radius:8px;color:#b91c1c;font-size:13.5px;line-height:1.9}
  .foot{margin-top:18px;padding-top:14px;border-top:1px dashed #e2e8f0;font-size:12.5px;color:#64748b;line-height:1.9}
  a{color:#2563eb;text-decoration:none}
  a:hover{text-decoration:underline}
</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <div class="code">%(status)s</div>
    <h1>%(title)s</h1>
    <div class="msg"><span class="path">%(path)s</span></div>
    <div class="msg">%(detail)s</div>
    %(actions)s
    %(stale)s
    <div class="foot">%(foot)s</div>
  </div>
</div>
</body>
</html>
"""


def wants_json(path: str) -> bool:
    """该路径的错误是否应保持 JSON/原样语义。"""
    p = path or "/"
    return any(p.startswith(x) for x in _JSON_PREFIXES)


def _stale_block() -> str:
    try:
        from engine import runtime_version as _RV                           # noqa: PLC0415
        hint = _RV.stale_hint()
    except Exception:                                                       # noqa: BLE001
        return ""
    if not hint:
        return ""
    return '<div class="stale">⚠️ %s</div>' % _html.escape(hint).replace("**", "")


def _foot_block() -> str:
    try:
        from engine import runtime_version as _RV                           # noqa: PLC0415
        booted = _RV.boot_snapshot()
        return ("当前服务启动于 %s（PID %s）。&nbsp;·&nbsp;"
                "<a href=\"/\">返回首页</a>&nbsp;·&nbsp;"
                "<a href=\"/healthz\">服务状态（JSON）</a>"
                % (_html.escape(str(booted.get("booted_at"))), booted.get("pid")))
    except Exception:                                                       # noqa: BLE001
        return "<a href=\"/\">返回首页</a>&nbsp;·&nbsp;<a href=\"/healthz\">服务状态（JSON）</a>"


def render_page_error(status: int, title: str, detail: str, path: str,
                      actions: Optional[list] = None) -> str:
    """渲染页面级错误 HTML（唯一实现，404/500/503 共用）。"""
    accent = {404: "#64748b", 500: "#dc2626", 503: "#d97706"}.get(int(status), "#dc2626")
    items = actions or []
    act_html = ("<ul>" + "".join("<li>%s</li>" % _html.escape(str(x)) for x in items) + "</ul>") \
        if items else ""
    return _PAGE_TEMPLATE % {
        "status": int(status), "title": _html.escape(str(title)),
        "detail": _html.escape(str(detail)), "path": _html.escape(str(path)),
        "accent": accent, "actions": act_html, "stale": _stale_block(), "foot": _foot_block(),
    }


def _is_page(path: str) -> bool:
    """页面级错误（应当返回 HTML）的**处置建议**（按状态码分类）。"""
    return not wants_json(path)


_RESTART_HINT = ("若这是刚更新的功能/页面：当前服务可能仍在运行**旧代码**（Python 代码是进程启动时的快照）"
                 "⇒ 请关闭服务后重新运行 start8001.bat，再刷新本页。")


def error_route(request: Any, exc: BaseException) -> Tuple[int, str, Optional[HTMLResponse]]:
    """全局异常分流**唯一权威**：返回 `(status_code, message, html_or_None)`。

    · 数据库「只读/权限」⇒ **500**（多半**不可**靠重试解决 ⇒ 不提示"请重试"）；
    · 数据库「忙/锁」  ⇒ **503**（可重试）；
    · 其它            ⇒ **500**。
    `html_or_None`：页面路径给出 HTML 兜底页；`/api/**` 等返回 `None`（由调用方回 JSON）。
    """
    _ro = is_db_readonly_error(exc)
    _busy = is_db_busy_error(exc)
    if _ro:
        status, msg = 500, "数据库当前不可写（只读或权限不足）：请检查数据文件的写权限/占用（`data/` 目录），此错误**重试无效**。"
    elif _busy:
        status, msg = 503, "服务繁忙，请重试（数据库并发写入冲突）。"
    else:
        status, msg = 500, "服务器内部错误。"
    path = str(getattr(getattr(request, "url", None), "path", "") or "")
    if not _is_page(path):
        return status, msg, None
    title = {500: "服务器内部错误", 503: "服务繁忙"}.get(status, "服务器内部错误")
    actions = ["查看服务窗口（start8001.bat）的控制台日志，里面有完整堆栈。", _RESTART_HINT]
    if status == 503:
        actions.insert(0, "稍等数秒后重试；若持续出现，说明有并发写入争用，可稍后重试。")
    html = render_page_error(status, title, msg, path, actions)
    return status, msg, HTMLResponse(html, status_code=status)


def page_404_handler(request: Any, exc: BaseException) -> Any:
    """404 兜底（注册到 `app.add_exception_handler(404, ...)`）。

    · `/api/**`、`/static/**` ⇒ 与 FastAPI 默认一致：`{"detail": "Not Found"}`；
    · 页面路径 ⇒ HTML，且**明确给出"是否只是没重启"的判据**（本类事故的根治提示）。
    """
    detail = str(getattr(exc, "detail", None) or "Not Found")
    path = str(getattr(getattr(request, "url", None), "path", "") or "")
    if not _is_page(path):
        return JSONResponse({"detail": detail}, status_code=404)
    actions = [
        "确认地址是否拼写正确（侧边栏里的入口都是有效页面）。",
        "若该页面确实应存在（例如 `/risks`、`/projects`）：当前服务很可能仍在运行**旧代码**——"
        "Python 代码在进程启动时就固定了，而前端菜单是**每次请求从磁盘读**的。"
        "⇒ 关闭服务后重新运行 start8001.bat，再刷新本页。",
        "自检：打开 `/healthz`，若 `stale.stale` 为 true，即证明服务需要重启。",
    ]
    html = render_page_error(404, "页面不存在", detail, path, actions)
    return HTMLResponse(html, status_code=404)


__all__ = ["wants_json", "render_page_error", "error_route", "page_404_handler"]
