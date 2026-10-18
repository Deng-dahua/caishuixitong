# -*- coding: utf-8 -*-
"""P0-2：首页总览 —— 防回退守护（2026-10-17）。

阶段 3 用户视角评估把「首页/总览」评为**全站最低（3.38）**：正文仅 0.4KB、
说明性文案 0 字、无反馈区，登录后只有一个侧栏。修完必须**锁住三件事**，
否则下一次改动很容易把它悄悄退回原状（本轮就踩过两次）：

  ① 容器 id 必须是 `page-home` —— `core.js` 切内页时只隐藏
     `#content-area > [id^="page-"]`，用别的 id 会与内页**同时显示**；
  ② `navigateTo` 的**内页白名单必须含 `home`** —— 否则 `navigateTo('home')`
     会被**静默改成** `tax-doc-analysis`，首页永远出不来（本轮实测踩过）；
  ③ 首次访问默认落到首页（老用户仍回上次页面）。

真浏览器验收见 `scripts/_verify_home_overview.js`。
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
INDEX = ROOT / "static" / "index.html"
CORE = ROOT / "static" / "js" / "core.js"
HOME_JS = ROOT / "static" / "js" / "home-overview.js"

#: 首页四块 KPI 的容器 id（与 home-overview.js 对应）
KPI_IDS = ["home-kpi-pending", "home-kpi-overdue", "home-kpi-docs", "home-kpi-job"]


def _s(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8")


# ── ① 容器与脚本 ─────────────────────────────────────────────────────────────
def test_home_container_is_page_home() -> None:
    """容器 id 必须是 `page-home`（否则与内页同时显示）。"""
    html = _s(INDEX)
    assert 'id="page-home"' in html, (
        "index.html 缺少 `id=\"page-home\"` 容器 —— core.js 切页时不会隐藏它，"
        "会与「资料风险分析报告」同时显示")
    # 且必须在 content-area 之内（不能放到 sidebar 里）
    i_area = html.index('id="content-area"')
    i_home = html.index('id="page-home"')
    assert i_home > i_area, "`#page-home` 不在 `#content-area` 之后（层级放错了）"


def test_home_script_is_loaded_with_version() -> None:
    """首页脚本必须被引用且带内容哈希（`?v=`），否则改了等于没改。"""
    html = _s(INDEX)
    assert re.search(r"/static/js/home-overview\.js\?v=[0-9a-f]{10}", html), (
        "index.html 未引用 home-overview.js（或未带 ?v= 内容哈希）")


def test_home_has_four_kpi_and_explanation() -> None:
    """四块 KPI + 口径说明必须存在（这是"可理解性/可反馈性"从 2 分提到 4+ 的实体）。"""
    html = _s(INDEX)
    for i in KPI_IDS:
        assert 'id="%s"' % i in html, "首页缺 KPI 容器 #%s" % i
    assert "口径说明" in html, "首页缺「口径说明」（必须写明指标取自哪个项目、缺失≠0）"
    assert "最近更新的项目" in html, "首页缺「最近更新的项目」列表区"


# ── ② 白名单（本轮踩过的坑，必须锁死）────────────────────────────────────────
def test_navigate_allowed_pages_contains_home() -> None:
    """`navigateTo` 的内页白名单必须含 `home`。

    这是本轮最隐蔽的一处：改了默认落点、容器 id 也对，但白名单会把
    `home` **静默矫正**成 `tax-doc-analysis` ⇒ 首页永远显示不出来。
    """
    src = _s(CORE)
    m = re.search(r"var _allowedPages = \[([^\]]*)\]", src)
    assert m, "core.js 未找到 `_allowedPages` 白名单（结构变了？）"
    pages = [x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip()]
    assert "home" in pages, (
        "内页白名单缺 `home` ⇒ navigateTo('home') 会被静默改成 tax-doc-analysis"
        "（当前白名单：%s）" % pages)


def test_default_page_is_home() -> None:
    """首次访问（无任何信号、无 lastPage）必须落首页。

    ★ 2026-10-18 修正（判据曾变成**假绿**）：原判据直接对源码正则
      `localStorage.getItem('lastPage') \\|\\| 'home'`。本轮把该表达式从代码里
      移除、改为经 `_resolveLandingPage()` 解析（其中含说明性注释引用了这句旧写法），
      于是**判据匹配到了注释文本 ⇒ 一直绿**，而真实代码早已不含该表达式。
      "把渲染代码删掉、注释里还留着字段名照样通过" —— 本仓明载的假判据形态。

      现口径：**剥注释后**断言唯一权威 `_DEFAULT_PAGE` 为 `'home'`。
      更完整的落点解析判据（含反向验证）在 `tests/test_home_landing.py`。
    """
    import re as _re

    src = _s(CORE)
    src = src.replace("\r\n", "\n").replace("\r", "\n")
    src = _re.sub(r"/\*.*?\*/", "", src, flags=_re.S)          # 块注释
    src = _re.sub(r"(?m)^\s*//.*$", "", src)                   # 行注释
    m = _re.search(r"(?m)^var _DEFAULT_PAGE = '([^']+)'", src)
    assert m, (
        "core.js 未找到默认落点权威 `_DEFAULT_PAGE`（剥注释后仍无 ⇒ 落点解析被拆了？）")
    assert m.group(1) == "home", (
        "默认落点应为 'home'，实际 '%s'（新用户会直接跳进资料分析页，看不到总览）" % m.group(1))
    # 且必须经唯一权威函数落地，不得在别处另写一份兜底
    assert "_resolveLandingPage()" in src, (
        "落点未经 `_resolveLandingPage()` 解析 ⇒ 登录/返回/刷新会各判一套")


def test_page_title_registered() -> None:
    """标题映射必须有 `home`（否则页头显示英文 'home'）。"""
    src = _s(CORE)
    assert re.search(r"['\"]home['\"]\s*:\s*['\"][^'\"]+['\"]", src), (
        "core.js 的 pages 标题映射缺 `home`")


# ── ③ 渲染纪律：缺失≠0、失败不空白 ──────────────────────────────────────────
def test_home_js_never_uses_zero_as_fallback() -> None:
    """取不到时必须写"—"，不得用 0 顶替（缺失 ≠ 0）。"""
    src = _s(HOME_JS)
    assert "缺失 ≠ 0" in src, "home-overview.js 缺「缺失 ≠ 0」的口径说明"
    # num() 的兜底必须是 —，不能是 0
    m = re.search(r"function num\(v\)\s*\{(.*?)\n  \}", src, re.S)
    assert m, "未找到 num() 函数"
    body = m.group(1)
    assert "'—'" in body or '"—"' in body, "num() 未以「—」作为取不到时的展示值"
    assert "return '0'" not in body and 'return "0"' not in body, "num() 用 0 顶替缺失值"


def test_home_js_reports_failures_on_page() -> None:
    """接口失败必须在页面上显示原因（不能只 console，也绝不能空白）。"""
    src = _s(HOME_JS)
    assert "取不到" in src, "home-overview.js 未把失败原因写到页面上"
    assert "msg err" in src, "home-overview.js 未使用既有 `.msg.err` 提示样式"


def test_home_js_job_contract_uses_jobs_key() -> None:
    """`analysis-jobs` 的返回键是 `jobs`（不是 `items`），且参数是 `limit`。

    本轮实测踩过：按 `items` + `page_size` 写 ⇒ 永远取空 ⇒ 首页错误显示"未分析"，
    而项目其实已分析成功（SUCCESS）。这类"看着正常其实是假数据"必须锁住。
    """
    src = _s(HOME_JS)
    assert "/analysis-jobs?limit=" in src, "analysis-jobs 未用 `limit` 参数"
    assert "d.jobs" in src, "analysis-jobs 未按 `jobs` 键取数据"
    assert "/analysis-jobs?" not in src.replace("/analysis-jobs?limit=", ""), (
        "仍存在未带 limit 的 analysis-jobs 调用")


def test_home_uses_existing_css_classes() -> None:
    """复用既有样式类（kpi-grid/kpi-card/section-card/quick-actions），不新造一套。"""
    html = _s(INDEX)
    for cls in ("kpi-grid", "kpi-card", "section-card", "quick-actions", "kpi-sub"):
        assert cls in html, "首页未复用既有样式类 .%s" % cls
    # 表格类名必须与其它页一致（table.grid），不能自造 .table
    home_js = _s(HOME_JS)
    assert '<table class="grid">' in home_js, "首页表格未用与其它页一致的 `table.grid`"


# ── ④ 反向验证 ───────────────────────────────────────────────────────────────
def test_reverse_removing_home_from_whitelist_would_break() -> None:
    """注入：把 `home` 从白名单摘掉 ⇒ ② 的判据必须报错（证明判据非空转）。"""
    src = _s(CORE)
    m = re.search(r"var _allowedPages = \[([^\]]*)\]", src)
    assert m, "白名单未找到"
    inner = m.group(1)
    broken_inner = inner.replace("'home',", "").replace("'home'", "")
    broken = src[:m.start(1)] + broken_inner + src[m.end(1):]
    assert broken != src, "反向验证锚点未命中"
    m2 = re.search(r"var _allowedPages = \[([^\]]*)\]", broken)
    pages2 = [x.strip().strip("'\"") for x in m2.group(1).split(",") if x.strip()]
    assert "home" not in pages2, "反向验证失败：摘掉后仍认为白名单含 home ⇒ 判据是假的"


if __name__ == "__main__":       # pragma: no cover
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
