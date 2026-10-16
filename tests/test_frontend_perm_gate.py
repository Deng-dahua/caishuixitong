# -*- coding: utf-8 -*-
"""前端权限门控 —— 防回退守护（裁定 MQ2-O4 / 发现 MQ2-O7，2026-10-17）。

背景：`reports.html` 曾**完全未接入**既有的前端门控，导致无 `report.generate` 的角色
（复核专家/审计员）能看到并填写「生成报告」表单，点击后才被服务端 403。

★ 口径：前端门控的**唯一机制**是 `static/js/rbac-nav.js`（消费服务端下发的
`permissions`，不推断角色）。本守护只断言「**该页已接入且关键入口挂了正确权限点**」，
不重复实现权限判定本身。

守护三件事：
  ① 该页引入了 `rbac-nav.js`；
  ② 「生成报告」页签与表单挂了 `data-perm="report.generate"`；
  ③ `reports.js` 在无该权限时把默认页签切到「报告列表」（否则停在隐藏的空白页签）。

另：`scripts/_verify_reports_perm_gate.js` 是**真浏览器实测**（4 角色 × 显隐 + 直打接口 403），
与本静态守护互为补充。
"""
from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORTS_HTML = ROOT / "static" / "reports.html"
REPORTS_JS = ROOT / "static" / "js" / "reports.js"
RBAC_NAV = ROOT / "static" / "js" / "rbac-nav.js"

#: 页面里必须挂权限点的「生成报告」入口（元素 id → 权限点）。
REQUIRED_GATED_IDS = {
    "tab-gen": "report.generate",
    "pane-gen": "report.generate",
}


def _html() -> str:
    return REPORTS_HTML.read_text(encoding="utf-8")


def test_rbac_nav_is_included() -> None:
    """① 报告页必须引入前端门控脚本（唯一机制）。"""
    html = _html()
    assert "rbac-nav.js" in html, (
        "static/reports.html 未引入 rbac-nav.js ⇒ 该页不参与任何前端权限门控"
    )
    # 机制本体必须存在（避免"引了个空文件"）
    assert RBAC_NAV.exists(), "static/js/rbac-nav.js 不存在"
    nav = RBAC_NAV.read_text(encoding="utf-8")
    assert "data-perm" in nav and "permissions" in nav, "rbac-nav.js 未消费 data-perm/permissions"


@pytest.mark.parametrize("element_id,perm", sorted(REQUIRED_GATED_IDS.items()))
def test_generate_entry_is_gated(element_id: str, perm: str) -> None:
    """② 「生成报告」入口必须挂 `data-perm`（无权限 ⇒ 隐藏）。"""
    html = _html()
    m = re.search(r"<[^>]*\bid=\"%s\"[^>]*>" % re.escape(element_id), html)
    assert m, "static/reports.html 中未找到 id=%s 的元素" % element_id
    tag = m.group(0)
    assert 'data-perm="%s"' % perm in tag, (
        "id=%s 未挂 data-perm=\"%s\"（当前标签：%s）⇒ 无权限角色仍会看到该入口"
        % (element_id, perm, tag[:160])
    )


def test_default_tab_falls_back_without_permission() -> None:
    """③ 无 report.generate 时须切换到「报告列表」，否则停在隐藏的空白页签。"""
    src = REPORTS_JS.read_text(encoding="utf-8")
    assert "RBAC" in src and "report.generate" in src, (
        "reports.js 未按 report.generate 做默认页签回退"
    )
    assert re.search(r"""switchTab\(\s*['"]history['"]\s*\)""", src), (
        "reports.js 未在无权限时调用 switchTab('history')"
    )


def test_other_gated_pages_are_not_regressed() -> None:
    """④ 既有已接门控的页面不得被回退（防止"修一处、坏一处"）。"""
    expect = {
        "index.html": 1,
        "users.html": 1,
        "roles.html": 1,
        "audit_logs.html": 1,
        "reports.html": 1,
    }
    for name, at_least in expect.items():
        p = ROOT / "static" / name
        if not p.exists():
            continue
        assert (p.read_text(encoding="utf-8").count("rbac-nav.js") >= at_least), (
            "%s 丢失了对 rbac-nav.js 的引用" % name
        )


def test_reverse_removing_gate_is_detected() -> None:
    """⑤ **反向验证**：把 `data-perm` 从生成入口摘掉 ⇒ ② 必须报错。

    证明 ② 不是同义反复（真的在比对属性，而非"总能通过"）。
    """
    html = _html()
    broken = html.replace(
        '<div id="pane-gen" data-perm="report.generate">',
        '<div id="pane-gen">',
        1,
    )
    assert broken != html, "反向验证锚点未命中（页面结构变了？请更新锚点）"
    m = re.search(r"<[^>]*\bid=\"pane-gen\"[^>]*>", broken)
    assert m and 'data-perm="report.generate"' not in m.group(0), (
        "反向验证失败：摘掉 data-perm 后判据仍认为已挂载 ⇒ 判据是同义反复"
    )


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
