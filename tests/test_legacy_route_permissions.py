# -*- coding: utf-8 -*-
"""旧路由写端点权限表 —— 防回退守护（MQ2-D1 扩展，2026-10-17）。

守护三件事，任一件被破坏都应让测试变红：

1. **表 ↔ 代码不脱节**：表里每条 (方法, 路径) 必须真实存在于 `main.py`；
   表中权限点必须都在 `config/rbac.json::permissions` 内（不新增权限点、不扩模型）。
2. **不漏配**：`main.py` 的**每个写端点**要么已登记，要么在下面的
   `INTENTIONALLY_UNREGISTERED` 白名单里。**新增写端点若忘了登记 ⇒ 本测试失败**。
3. **接线有效**：`enforce_request_security` 源码里必须真的调用 `_required_legacy_perm`，
   否则"表建了但没人用" = 假绿。

另一条独立守护见 `test_legacy_route_permissions_live` 家族的真 HTTP 实测
（`scripts/_verify_legacy_perms.py`，18 端点 × 5 角色 = 90 项）。
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _main_write_endpoints() -> set:
    """`main.py` 里注册的全部写端点 (方法, 路径)。"""
    src = (ROOT / "main.py").read_text(encoding="utf-8")
    out = set()
    for line in src.split("\n"):
        m = re.match(r'\s*@app\.(get|post|put|delete|patch)\(\s*["\']([^"\']*)["\']', line)
        if not m:
            continue
        method, path = m.group(1).upper(), m.group(2)
        if method in ("POST", "PUT", "DELETE", "PATCH"):
            out.add((method, path))
    return out


def _security_web_source() -> str:
    return (ROOT / "security_web.py").read_text(encoding="utf-8")


def _legacy_tables() -> tuple:
    """从 `security_web.py` 源码里取两张表（不 import，避免副作用）。

    直接 import 会加载 `security.py`（含库连接逻辑）——这里只做**静态**判定，
    与守护目标一致（守护的是源码内容，不是运行期对象）。
    """
    src = _security_web_source()
    perms, admin = [], []
    for block, bucket in (("_LEGACY_WRITE_PERMS", perms), ("_LEGACY_ADMIN_ONLY", admin)):
        seg = src.split(block + ": tuple = (", 1)[1].split("\n)", 1)[0]
        for m in re.finditer(r'\(\s*"([A-Z]+)"\s*,\s*"([^"]+)"\s*(?:,\s*"([^"]+)")?\s*\)', seg):
            bucket.append((m.group(1), m.group(2), m.group(3)))
    return perms, admin


#: **有意放行**的写端点（不在权限表内，各有明确理由）。
#: ⚠ 这是一份**显式白名单**：任何新增写端点若既不登记、又不在此处 ⇒ 测试失败。
INTENTIONALLY_UNREGISTERED = {
    # ① 公共路径（`security.is_public_path` 白名单，必须免登录）
    ("POST", "/api/auth/login"): "登录（公开路径）",
    ("POST", "/api/auth/register"): "免登录账号设置（公开路径）",
    # ② 自我服务（已按 `auth.user_id` 做所有权隔离，不属功能权限点管辖）
    ("POST", "/api/auth/logout"): "登出自己",
    ("POST", "/api/auth/select-company"): "选择自己可见的账套",
    ("POST", "/api/auth/change-password"): "改自己密码",
    ("POST", "/api/v1/auth/change-password"): "改自己密码（v1 别名）",
    ("POST", "/api/me/llm-credentials"): "管理自己的模型密钥",
    ("PUT", "/api/me/llm-credentials/{credential_id}"): "轮换自己的模型密钥",
    ("POST", "/api/me/llm-credentials/{credential_id}/default"): "设自己的默认密钥",
    ("POST", "/api/me/llm-credentials/{credential_id}/test"): "测试自己的模型密钥",
    ("DELETE", "/api/me/llm-credentials/{credential_id}"): "删自己的模型密钥",
    # ③ 405 墓桩（恒返回"请使用管理我的模型"，不产生副作用）
    ("POST", "/api/apikey"): "405 墓桩",
    ("DELETE", "/api/apikey"): "405 墓桩",
    # ④ 已由既有 `_ADMIN_PATHS` 覆盖（前缀级 admin 检查，与本源表并列的既有机制）
    ("POST", "/api/system-logs/clear"): "既有 _ADMIN_PATHS 覆盖",
    # ⑤ 纯提交反馈（不限功能权限点；改结论/改规则库的反馈端点**已**登记）
    ("POST", "/api/feedback/error"): "提交错误反馈",
    ("POST", "/api/agi/content-feedback"): "提交内容反馈",
    ("POST", "/api/agi/engine-feedback"): "提交引擎级反馈",
}

#: 仅管理员集合应当**恰好**是这些（多一个少一个都应被察觉 —— 防误加/误删）。
EXPECTED_ADMIN_ONLY = {
    ("POST", "/api/companies"),                       # 与既有特例一致
    ("POST", "/api/industries/refresh-benchmarks"),
    ("DELETE", "/api/pipeline/history"),
    ("POST", "/api/patrol/config"),
    ("POST", "/api/patrol/run"),
    ("POST", "/api/notifications/config"),
    ("POST", "/api/agi/query"),
    ("POST", "/api/agi/self-check/{company_id}"),
    ("POST", "/api/agi/parallel/toggle"),
    ("POST", "/api/agi/sample"),
    ("POST", "/api/agi/predict"),
    ("POST", "/api/agi/rectify"),
    ("POST", "/api/agi/rectify/update"),
    ("POST", "/api/agi/propagate-to-chains"),
}


def test_every_table_entry_exists_in_main() -> None:
    """① 表中每条 (方法, 路径) 必须真实存在于 `main.py`（防手抄错路径）。"""
    perms, admin = _legacy_tables()
    code = _main_write_endpoints()
    table = {(m, p) for m, p, _ in perms} | {(m, p) for m, p, _ in admin}
    ghost = sorted(table - code)
    assert not ghost, "表中存在 main.py 没有的端点（路径写错？）: %s" % ghost


def test_permission_codes_are_registered() -> None:
    """② 表中权限点必须都在 `config/rbac.json::permissions`（不新增权限点）。"""
    perms, _ = _legacy_tables()
    codes = {
        p["code"]
        for p in json.loads((ROOT / "config" / "rbac.json").read_text(encoding="utf-8"))["permissions"]
    }
    used = {c for _, _, c in perms if c}
    unknown = sorted(used - codes)
    assert not unknown, "表中出现 rbac.json 之外的权限点: %s" % unknown


def test_no_duplicate_registration() -> None:
    """③ 同一端点不得同时登记在两张表里。"""
    perms, admin = _legacy_tables()
    dup = sorted({(m, p) for m, p, _ in perms} & {(m, p) for m, p, _ in admin})
    assert not dup, "端点同时登记为『权限点』与『仅管理员』: %s" % dup


def test_admin_only_set_is_exactly_expected() -> None:
    """④ 仅管理员集合应当恰好等于预期（防悄悄把业务端点挪进 admin）。"""
    _, admin = _legacy_tables()
    got = {(m, p) for m, p, _ in admin}
    assert got == EXPECTED_ADMIN_ONLY, (
        "仅管理员集合与预期不符；多出=%s 缺少=%s"
        % (sorted(got - EXPECTED_ADMIN_ONLY), sorted(EXPECTED_ADMIN_ONLY - got))
    )


def test_no_write_endpoint_left_unregistered() -> None:
    """⑤ **漏配闸门**：新增写端点若不登记、又不在白名单 ⇒ 失败。

    这是本守护的核心价值 —— 表是"唯一权威"，就必须保证**没有端点游离在表外**。
    """
    perms, admin = _legacy_tables()
    registered = {(m, p) for m, p, _ in perms} | {(m, p) for m, p, _ in admin}
    code = _main_write_endpoints()
    unregistered = sorted(code - registered)
    unexpected = [x for x in unregistered if x not in INTENTIONALLY_UNREGISTERED]
    assert not unexpected, (
        "以下写端点既未登记权限、也不在有意放行白名单中（新增端点请补登记）：%s"
        % unexpected
    )


def test_unregistered_whitelist_has_no_stale_entries() -> None:
    """⑥ 白名单不得残留已不存在的端点（防白名单腐化）。"""
    code = _main_write_endpoints()
    stale = sorted(k for k in INTENTIONALLY_UNREGISTERED if k not in code)
    assert not stale, "白名单里的端点在 main.py 已不存在: %s" % stale


def test_enforcement_is_wired() -> None:
    """⑦ **接线自检**：`enforce_request_security` 里必须真的调用查表函数。

    若只建表不接线 ⇒ 权限根本没生效，但表看起来"很完整"（假绿）。
    """
    src = _security_web_source()
    assert "def _required_legacy_perm(" in src, "查表函数未定义"
    m = re.search(r"\nasync def enforce_request_security\(", src)
    assert m, "未找到 enforce_request_security"
    # 取到下一个顶层 async def / def 之前
    nxt = re.search(r"\n(?:async )?def ", src[m.end():])
    body = src[m.start(): m.end() + (nxt.start() if nxt else len(src))]
    assert "_required_legacy_perm(" in body, "enforce_request_security 未调用 _required_legacy_perm ⇒ 权限表没接线"
    assert "require_permission(session" in body, "未调用 engine.rbac.require_permission ⇒ 未复用既有权威"


def test_reverse_removing_an_entry_is_detected(tmp_path, monkeypatch) -> None:
    """⑧ **反向验证**：把表里一条改成不存在的路径 ⇒ ① 必须报出来。

    证明 ① 不是同义反复（真的在比对，而不是"总能通过"）。
    """
    src = _security_web_source()
    broken = src.replace(
        '("POST", "/api/tax-risk-docs/upload", "document.write"),',
        '("POST", "/api/tax-risk-docs/upload-TYPO-FOR-REVERSE-TEST", "document.write"),',
        1,
    )
    assert broken != src, "反向验证锚点未命中（表内容变了？请更新本测试的锚点）"

    perms, admin = [], []
    for block, bucket in (("_LEGACY_WRITE_PERMS", perms), ("_LEGACY_ADMIN_ONLY", admin)):
        seg = broken.split(block + ": tuple = (", 1)[1].split("\n)", 1)[0]
        for mm in re.finditer(r'\(\s*"([A-Z]+)"\s*,\s*"([^"]+)"\s*(?:,\s*"([^"]+)")?\s*\)', seg):
            bucket.append((mm.group(1), mm.group(2), mm.group(3)))
    table = {(m, p) for m, p, _ in perms} | {(m, p) for m, p, _ in admin}
    ghost = sorted(table - _main_write_endpoints())
    assert "POST /api/tax-risk-docs/upload-TYPO-FOR-REVERSE-TEST" in " ".join(
        "%s %s" % g for g in ghost
    ), "反向验证失败：把路径改错后 ① 的判据没有发现 ⇒ 判据可能是同义反复"


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
