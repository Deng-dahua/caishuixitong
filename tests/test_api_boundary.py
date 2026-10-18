# -*- coding: utf-8 -*-
"""API 公共边界（R-02）守护测试。

背景：`_session` 曾在 10 个 API 文件各复制一份、`_call` 8 份、`_require_perm`/
`_request_perm` 各 6 份。收敛到 `engine/api_common.py` 后，本文件锁住三件事：

  ① **行为不变**：401/403 的语义与错误文案与收敛前一致（前端/测试依赖它）；
  ② **不许误吞**：`call_boundary` 只捕获**显式声明**的业务异常，
     未被声明的异常（代码缺陷）必须原样抛出 —— 否则真正的 500 会被伪装成 4xx；
  ③ **不许回退**：任何 `*api*.py` 不得再定义那几个边界函数（闸门另有覆盖）。
"""
from __future__ import annotations

import pathlib
import sys

import pytest
from fastapi import HTTPException

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import api_common as AC   # noqa: E402


class _Sess:
    def __init__(self, is_admin=False, perms=("project.view",)):
        self.is_admin = is_admin
        self.username = "probe"
        self._perms = set(perms)

    def can_access_company(self, cid):        # noqa: ANN001
        return True


class _Req:
    def __init__(self, auth=None):
        self.state = type("St", (), {"auth": auth})()


class _BizError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


# ── ① session_of / admin_of ─────────────────────────────────────────────────
def test_session_of_401_when_absent() -> None:
    with pytest.raises(HTTPException) as ei:
        AC.session_of(_Req(None))
    assert ei.value.status_code == 401
    assert ei.value.detail == "未登录"


def test_session_of_returns_session() -> None:
    s = _Sess()
    assert AC.session_of(_Req(s)) is s


def test_admin_of_rejects_non_admin_with_403() -> None:
    with pytest.raises(HTTPException) as ei:
        AC.admin_of(_Req(_Sess(is_admin=False)))
    assert ei.value.status_code == 403, "非管理员必须 403（不能放行）"


def test_admin_of_allows_admin() -> None:
    s = _Sess(is_admin=True)
    assert AC.admin_of(_Req(s)) is s


def test_admin_of_checks_401_before_403() -> None:
    """未登录时先 401（不泄露"该资源存在但你没权限"）。"""
    with pytest.raises(HTTPException) as ei:
        AC.admin_of(_Req(None))
    assert ei.value.status_code == 401


# ── ② require_perm / request_perm ───────────────────────────────────────────
def test_require_perm_forbidden_when_missing() -> None:
    # ★ 用 `role.manage`：无角色属性的假会话会回落到 `enterprise_finance`（既有口径），
    #   而该角色**确实没有** role.manage ⇒ 才能测到"缺权限就 403"这条判据。
    #   （第一版用了 project.write，那恰好是该角色有的权限，导致判据空转 —— 已修正。）
    with pytest.raises(HTTPException) as ei:
        AC.require_perm(_Sess(perms=()), "role.manage")
    assert ei.value.status_code == 403
    assert "无权执行该操作" in ei.value.detail, "错误文案应来自 engine.rbac（唯一权威）"


def test_request_perm_keeps_legacy_message() -> None:
    """`request_perm` 保留既有文案「缺少权限：%s」—— 前端/测试依赖它，不许改。"""
    with pytest.raises(HTTPException) as ei:
        AC.request_perm(_Req(_Sess(perms=())), "risk.review")
    assert ei.value.status_code == 403
    assert ei.value.detail == "缺少权限：risk.review"


def test_request_perm_401_before_403() -> None:
    with pytest.raises(HTTPException) as ei:
        AC.request_perm(_Req(None), "risk.review")
    assert ei.value.status_code == 401


# ── ③ call_boundary ─────────────────────────────────────────────────────────
def test_call_boundary_maps_declared_error() -> None:
    def boom():
        raise _BizError("项目不存在或无权访问", 404)

    with pytest.raises(HTTPException) as ei:
        AC.call_boundary(boom, exc_types=(_BizError,))
    assert ei.value.status_code == 404
    assert ei.value.detail == "项目不存在或无权访问"


def test_call_boundary_defaults_to_400_when_no_status() -> None:
    class _Bare(Exception):
        pass

    def boom():
        raise _Bare("没有 status 属性")

    with pytest.raises(HTTPException) as ei:
        AC.call_boundary(boom, exc_types=(_Bare,))
    assert ei.value.status_code == 400


def test_call_boundary_does_NOT_swallow_undeclared_errors() -> None:
    """★ 核心判据：未声明的异常必须原样抛出（否则 500 被伪装成 4xx，掩盖故障）。"""
    def boom():
        raise ValueError("代码缺陷，不是业务错误")

    with pytest.raises(ValueError):
        AC.call_boundary(boom, exc_types=(_BizError,))


def test_call_boundary_passes_through_result_and_kwargs() -> None:
    def fn(a, b=0, **kw):
        return (a, b, kw)

    got = AC.call_boundary(fn, 1, b=2, exc_types=(_BizError,), extra="x")
    assert got == (1, 2, {"extra": "x"})


# ── ④ 不许回退：源码层判据（闸门之外的即时反馈） ────────────────────────────
def test_no_api_file_redefines_boundary_helpers() -> None:
    forbidden = ("def _session(", "def _require_perm(", "def _request_perm(",
                 "def _perm(", "def _admin(")
    bad = []
    for p in sorted(ROOT.glob("*api*.py")):
        if p.name.startswith("_bk"):
            continue
        src = p.read_text(encoding="utf-8", errors="replace")
        bad.extend("%s:%s" % (p.name, f.strip()) for f in forbidden if f in src)
    assert not bad, "以下文件重新定义了边界函数（应改为别名引用 engine.api_common）：%s" % bad


def test_every_call_wrapper_uses_call_boundary() -> None:
    """`_call` 允许存在，但必须转发到 `call_boundary`（禁止各写一套转换逻辑）。"""
    import ast

    bad = []
    for p in sorted(ROOT.glob("*api*.py")):
        if p.name.startswith("_bk"):
            continue
        src = p.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "_call":
                body = ast.get_source_segment(src, node) or ""
                if "call_boundary" not in body:
                    bad.append("%s:%d" % (p.name, node.lineno))
    assert not bad, "以下 _call 未转发到 call_boundary：%s" % bad
