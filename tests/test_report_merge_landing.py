# -*- coding: utf-8 -*-
"""「资料风险分析报告」并入「报告生成与导出」—— 防回退守护（2026-10-19）。

## 用户需求
「把资料风险分析报告模块融入报告生成与导出模块，然后删除资料风险分析报告模块。」

## 改造要点（本文件锁住的就是这些）

  ① 原 SPA 内页 `data-page="tax-doc-analysis"` **已删除**：侧边栏入口、白名单条目、
     标题映射、switch 分派、`taxDocPageActive` 的跨文件改写，全部清掉；
  ② 报告阅读能力**并入** `/reports`，作为**第一个（默认）页签**「分析报告」；
  ③ 渲染**复用** `tax-doc-analysis.js::renderTaxDocReport`（报告级渲染的唯一实现）
     —— 不另写一份，否则两条链会各出各的报告；
  ④ 因 `reports.html` **刻意不引 `core.js`**（它是 SPA 主控制器，加载即自启），
     其依赖的 `escHtml`/`escapeHtml`/`toast` 抽成 `static/js/dom-utils.js`（唯一权威），
     两页共同加载 —— 否则审计闸门 `check_js_undefined_calls` 会报「查无此名」；
  ⑤ `_tdaCid()` 读全局 `currentCompanyId` ⇒ `reports.js` 必须把它设好，
     否则「导出PDF / 缓存 / 删除报告」会报「未选择账套」；
  ⑥ 数据是**双层嵌套**：正文在 `last-analysis` 返回的 `.report` 里（不是顶层）；
  ⑦ 深链兼容：`navigateTo('tax-doc-analysis')` 必须重定向到 `/reports`
     （引擎仪表盘等处仍有此深链），且该重定向**必须在白名单校验之前**
     —— 否则会被 `_FALLBACK_PAGE` 静默改成首页。

末尾有**逐项反向验证**：破坏一处 ⇒ 对应判据必须报错（不变红说明判据是假的）。
"""
from __future__ import annotations

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, "static", "js", "core.js")
INDEX = os.path.join(ROOT, "static", "index.html")
REPORTS_HTML = os.path.join(ROOT, "static", "reports.html")
REPORTS_JS = os.path.join(ROOT, "static", "js", "reports.js")
TDA_JS = os.path.join(ROOT, "static", "js", "tax-doc-analysis.js")
DOMUTILS = os.path.join(ROOT, "static", "js", "dom-utils.js")


def _s(path: str) -> str:
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def _code(path: str) -> str:
    """剥注释 + 行尾归一化后的源码（存在性/否定性断言的唯一取材口径）。

    ★ 必须剥注释：否则注释里提一句被禁的名字就会让判据**误报**；反过来，
      判据若在注释里也能匹配到目标串（如 `d.report`），注入式反向验证就会
      "注入后仍然通过" ⇒ 判据是假的（本轮实际踩到 R5/R7 两项）。
    ★ 必须归一化行尾：本仓 HTML/JS 为 CRLF，锚点写 `\\n` 会永远命中不了。
    ★ HTML 块注释 `<!-- ... -->` **可以跨行**，必须用 DOTALL 剥（本轮踩到）。
    """
    src = _s(path).replace("\r\n", "\n").replace("\r", "\n")
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"<!--.*?-->", "", src, flags=re.S)          # HTML 块注释（跨行）
    src = re.sub(r"(?m)^\s*//.*$", "", src)
    return src


# ══════════ ① 内页已删除 ══════════
def test_sidebar_entry_removed() -> None:
    """侧边栏不得再有 `data-page="tax-doc-analysis"` 入口。"""
    html = _code(INDEX)
    assert 'data-page="tax-doc-analysis"' not in html, (
        "index.html 仍有 `data-page=\"tax-doc-analysis\"` 侧边栏入口 —— 该内页应已删除")


def test_whitelist_entry_removed() -> None:
    """SPA 白名单不得再含 `tax-doc-analysis`。"""
    m = re.search(r"(?m)^var _allowedPages = \[([^\]]*)\]", _code(CORE))
    assert m, "core.js 未找到 `_allowedPages` 白名单"
    pages = [x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip()]
    assert "tax-doc-analysis" not in pages, (
        "白名单仍含 `tax-doc-analysis`（该内页已删除）：%s" % pages)


def test_fallback_page_is_not_dead_page() -> None:
    """非法页键的兜底页不得是已删除的内页（否则建空容器 + 「模块加载超时」）。"""
    m = re.search(r"(?m)^var _FALLBACK_PAGE = '([^']+)'", _code(CORE))
    assert m, "core.js 未定义 `_FALLBACK_PAGE`（兜底页必须显式声明，不能硬编码死页）"
    assert m.group(1) != "tax-doc-analysis", (
        "兜底页指向已删除的内页 `tax-doc-analysis`")
    # 兜底页必须本身在白名单内（否则 navigateTo 会陷入"改完仍非法"）
    m2 = re.search(r"(?m)^var _allowedPages = \[([^\]]*)\]", _code(CORE))
    pages = [x.strip().strip("'\"") for x in m2.group(1).split(",") if x.strip()]
    assert m.group(1) in pages, (
        "兜底页 `%s` 不在白名单 %s 内 ⇒ navigateTo 会改到一个仍非法的页" % (m.group(1), pages))


def test_no_render_dispatch_for_removed_page() -> None:
    """不得再有 `_sR(container, 'renderTaxDocAnalysis')` 的分派（内页已删）。"""
    assert "_sR(container, 'renderTaxDocAnalysis')" not in _code(CORE), (
        "core.js 仍把 `tax-doc-analysis` 分派给 `renderTaxDocAnalysis` —— 内页应已删除")


def test_deep_link_redirect_exists_before_whitelist() -> None:
    """深链 `navigateTo('tax-doc-analysis')` 必须重定向到 `/reports`，且在白名单校验之前。

    否则会先被 `_FALLBACK_PAGE` 静默改成首页 —— 用户点「资料风险分析报告」却到了首页，
    而且看不到任何解释（引擎仪表盘 / 过滤记录页仍保留该深链）。
    """
    code = _code(CORE)
    assert "if (page === 'tax-doc-analysis') { window.location.href = '/reports'; return; }" in code, (
        "缺 `tax-doc-analysis` → `/reports` 的重定向（深链兼容）")
    i_redir = code.index("if (page === 'tax-doc-analysis')")
    i_wl = code.index("if (_allowedPages.indexOf(page) === -1)")
    assert i_redir < i_wl, (
        "重定向必须在白名单校验**之前** —— 否则会先被 `_FALLBACK_PAGE` 静默改成首页")


# ══════════ ② 并入 /reports ══════════
def test_reports_has_analysis_tab_first() -> None:
    """`/reports` 必须有「分析报告」页签，且是**第一个（默认）**页签。"""
    html = _s(REPORTS_HTML)
    assert 'id="tab-analysis"' in html, "reports.html 缺「分析报告」页签 #tab-analysis"
    assert 'id="pane-analysis"' in html, "reports.html 缺分析报告面板 #pane-analysis"
    # 必须是第一个页签（否则用户打开 /reports 看到的还是「生成报告」）
    i_first = html.index('class="tabs"')
    i_analysis = html.index('id="tab-analysis"')
    i_gen = html.index('id="tab-gen"')
    assert i_analysis < i_gen, "「分析报告」必须排在「生成报告」之前"
    assert i_analysis > i_first, "页签结构异常"
    # 该页签必须带 active（默认选中）+ 面板默认可见
    seg = html[i_first:i_analysis + 200]
    assert 'class="tab active"' in seg, "「分析报告」页签必须是默认选中（active）"


def test_report_body_container_exists() -> None:
    """`/reports` 必须提供 `#tda-report-area` 容器（`renderTaxDocReport` 硬编码取它）。"""
    assert 'id="tda-report-area"' in _s(REPORTS_HTML), (
        "reports.html 缺 `#tda-report-area` —— `renderTaxDocReport` 找不到容器会直接 return（空白）")


def test_reports_loads_render_dependencies_in_order() -> None:
    """`/reports` 必须按序加载渲染依赖：dom-utils → constants → tax-doc-analysis。"""
    html = _s(REPORTS_HTML)
    for need in ("/static/js/dom-utils.js", "/static/js/constants.js",
                 "/static/js/tax-doc-analysis.js"):
        assert need in html, "reports.html 未加载 %s（报告渲染依赖）" % need
    i_dom = html.index("/static/js/dom-utils.js")
    i_const = html.index("/static/js/constants.js")
    i_tda = html.index("/static/js/tax-doc-analysis.js")
    assert i_dom < i_const < i_tda, (
        "依赖加载顺序错误（须 dom-utils → constants → tax-doc-analysis）：%d/%d/%d"
        % (i_dom, i_const, i_tda))


def test_reports_does_not_load_core_js() -> None:
    """`/reports` **不得**引入 `core.js`（SPA 主控制器，加载即自启 `_startApp`）。"""
    assert "/static/js/core.js" not in _s(REPORTS_HTML), (
        "reports.html 引入了 core.js ⇒ 会在此独立页触发 SPA 初始化（拉账套、切页、"
        "在不相干的容器上渲染），属明显副作用")


def test_render_reuses_single_implementation() -> None:
    """渲染必须**复用** `renderTaxDocReport`，不得在本页另写一套报告渲染。"""
    js = _code(REPORTS_JS)
    assert "renderTaxDocReport(d.report)" in js, (
        "reports.js 未复用 `renderTaxDocReport`（报告级渲染的唯一实现）")
    # 不得出现"自己拼报告章节"的迹象（例如自建完整封面/章节 HTML）
    for bad in ("_buildEnterpriseReadableBody", "renderTaxDocAnalysis"):
        assert bad not in js, (
            "reports.js 出现 `%s` ⇒ 疑似在本页另写报告渲染（多头维护）" % bad)


def test_data_nesting_uses_report_key() -> None:
    """数据是双层嵌套：必须取 `.report`（不是接口返回的顶层对象）。

    ★ 判据作用于**剥注释后的代码** —— 否则注释里解释契约时写一句 `d.report`，
      就能让"真正取数那行被改成 `d`"照样通过（R5 反向验证抓出来的假绿）。
    """
    js = _code(REPORTS_JS)
    assert re.search(r"renderTaxDocReport\(\s*d\.report\s*\)", js), (
        "reports.js 未以 `renderTaxDocReport(d.report)` 调用 —— `last-analysis` 返回"
        "**外层**对象，报告正文在 `.report` 里（传顶层对象则渲染不出任何内容）")


def test_company_id_is_wired_for_export() -> None:
    """`currentCompanyId` 必须被**赋为当前账套**，否则导出/缓存/删除报告会报「未选择账套」。

    ★ 判据必须精确到「把 CID 赋进去」这一形态，不能只查"出现过 `window.currentCompanyId =`"：
      `reports.js` 里另有一处 `= 0`（切项目时清空），只查"有赋值"会让
      「真正把 CID 赋进去那行被删掉」照样通过（R7 反向验证抓出来的假绿）。
    """
    js = _code(REPORTS_JS)
    assert re.search(r"window\.currentCompanyId\s*=\s*Number\(\s*CID\s*\)", js), (
        "reports.js 未把当前账套赋给 `window.currentCompanyId` ⇒ "
        "`tax-doc-analysis.js::_tdaCid()` 取到 0 ⇒ 导出PDF/缓存/删除报告全部失败"
        "（且这三个按钮就在本页签上）")


def test_analysis_loader_reports_failure_visibly() -> None:
    """取不到报告时必须在页面上**如实说明原因**（不得静默空白）。"""
    js = _s(REPORTS_JS)
    assert "尚无分析报告" in js, "reports.js 未在无报告时给出可见说明"
    assert "报告渲染器未加载" in js, (
        "reports.js 未在渲染器缺失时给出可见提示（否则只是一个空白页）")


# ══════════ ③ 共享工具模块（唯一权威） ══════════
def test_dom_utils_defines_shared_helpers() -> None:
    """`dom-utils.js` 必须是这几个共享工具的唯一实现。"""
    src = _code(DOMUTILS)
    for fn in ("function normalizeDisplayValue", "function escapeHtml",
               "var esc = escapeHtml", "var escHtml = escapeHtml", "function toast"):
        assert fn in src, "dom-utils.js 缺 `%s`" % fn


def test_core_js_no_longer_defines_them() -> None:
    """`core.js` 不得再定义它们（重复定义 = 多头维护，转义实现分叉）。"""
    code = _code(CORE)
    for fn in ("function normalizeDisplayValue", "function escapeHtml", "function toast"):
        assert fn not in code, (
            "core.js 仍定义 `%s` ⇒ 与 dom-utils.js 多头维护（转义分叉=显示错乱或 XSS）" % fn)


def test_both_pages_load_dom_utils_before_users() -> None:
    """两页都必须加载 `dom-utils.js`，且在其使用者之前。"""
    idx = _s(INDEX)
    rep = _s(REPORTS_HTML)
    for name, html in (("index.html", idx), ("reports.html", rep)):
        assert "/static/js/dom-utils.js" in html, "%s 未加载 dom-utils.js" % name
    # index.html：必须在 core.js 与 tax-doc-analysis.js 之前
    i_dom = idx.index("/static/js/dom-utils.js")
    assert i_dom < idx.index("/static/js/core.js"), (
        "index.html 里 dom-utils.js 必须早于 core.js（后者顶层即引用 esc/escHtml）")
    assert i_dom < idx.index("/static/js/tax-doc-analysis.js"), (
        "index.html 里 dom-utils.js 必须早于 tax-doc-analysis.js")


# ══════════ ④ 反向验证 ══════════
def _with_broken(path_attr, old, new, fn):
    """把 `path_attr` 指向的文件做一次替换后执行 `fn`，断言其必须失败。"""
    import pytest

    raw = _s(globals()[path_attr]).replace("\r\n", "\n").replace("\r", "\n")
    assert old in raw, (
        "反向验证锚点未命中（%s 中找不到 %r）—— 说明注入无法触发判据，本项是空转的"
        % (path_attr, old[:70]))
    broken = raw.replace(old, new, 1)
    assert broken != raw, "替换未生效"
    ext = os.path.splitext(globals()[path_attr])[1]
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_broken_tmp" + ext)
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(broken)
    original = globals()[path_attr]
    globals()[path_attr] = tmp
    try:
        with pytest.raises(AssertionError):
            fn()
    finally:
        globals()[path_attr] = original
        try:
            os.remove(tmp)
        except OSError:
            pass


def test_reverse_r1_sidebar_entry_restored() -> None:
    """注入：把侧边栏入口加回来 ⇒ 内页已删判据必须报错。"""
    _with_broken("INDEX",
                 '<div class="nav-group-title">二、系统</div>',
                 '<div class="nav-group-title">二、风险分析</div>\n'
                 '    <div class="nav-item" data-page="tax-doc-analysis">资料风险分析报告</div>\n'
                 '    <div class="nav-group-title">二、系统</div>',
                 test_sidebar_entry_removed)


def test_reverse_r2_whitelist_entry_restored() -> None:
    """注入：把 `tax-doc-analysis` 加回白名单 ⇒ 白名单判据必须报错。"""
    _with_broken("CORE", "var _allowedPages = ['home', 'methodology'];",
                 "var _allowedPages = ['home', 'methodology', 'tax-doc-analysis'];",
                 test_whitelist_entry_removed)


def test_reverse_r3_redirect_moved_after_whitelist() -> None:
    """注入：把深链重定向挪到白名单校验之后 ⇒ 顺序判据必须报错。"""
    src = _s(CORE).replace("\r\n", "\n").replace("\r", "\n")   # ★ 归一化行尾再做锚点
    redir = "  if (page === 'tax-doc-analysis') { window.location.href = '/reports'; return; }\n"
    assert redir in src, "反向验证锚点未命中（重定向语句被改写了？）"
    broken = src.replace(redir, "", 1)
    wl = "  if (_allowedPages.indexOf(page) === -1) { page = _FALLBACK_PAGE; }\n"
    assert wl in broken, "反向验证锚点 2 未命中"
    broken = broken.replace(wl, wl + redir, 1)
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_broken_redir.js")
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(broken)
    original = globals()["CORE"]
    globals()["CORE"] = tmp
    try:
        import pytest
        with pytest.raises(AssertionError):
            test_deep_link_redirect_exists_before_whitelist()
    finally:
        globals()["CORE"] = original
        os.remove(tmp)


def test_reverse_r4_core_js_defines_duplicate_helper() -> None:
    """注入：`core.js` 又定义一份 `escapeHtml` ⇒ 多头维护判据必须报错。"""
    _with_broken("CORE", "// ==================== 分页工具 ====================",
                 "function escapeHtml(s) { return String(s); }\n"
                 "// ==================== 分页工具 ====================",
                 test_core_js_no_longer_defines_them)


def test_reverse_r5_reports_drops_report_key() -> None:
    """注入：把 `d.report` 改成 `d`（误用顶层对象）⇒ 嵌套判据必须报错。"""
    _with_broken("REPORTS_JS", "renderTaxDocReport(d.report);",
                 "renderTaxDocReport(d);", test_data_nesting_uses_report_key)


def test_reverse_r6_reports_loads_core_js() -> None:
    """注入：给 `reports.html` 加上 core.js ⇒ 不得引入判据必须报错。"""
    _with_broken("REPORTS_HTML",
                 '<script src="/static/js/rbac-nav.js?v=ac23045192" defer></script>',
                 '<script src="/static/js/rbac-nav.js?v=ac23045192" defer></script>\n'
                 '  <script src="/static/js/core.js?v=0000000000"></script>',
                 test_reports_does_not_load_core_js)


def test_reverse_r7_company_id_not_wired() -> None:
    """注入：去掉 `window.currentCompanyId` 赋值 ⇒ 导出接线判据必须报错。"""
    _with_broken("REPORTS_JS", "window.currentCompanyId = Number(CID);",
                 "/* removed */", test_company_id_is_wired_for_export)


def test_reverse_r8_analysis_not_first_tab() -> None:
    """注入：把「分析报告」页签挪到「生成报告」之后 ⇒ 顺序判据必须报错。"""
    html = _s(REPORTS_HTML).replace("\r\n", "\n").replace("\r", "\n")   # ★ 归一化行尾
    a = '      <div class="tab active" data-tab="analysis" id="tab-analysis">分析报告</div>\n'
    assert a in html, "反向验证锚点未命中（页签结构变了？）"
    broken = html.replace(a, "", 1)
    b = '      <div class="tab" data-tab="gen" id="tab-gen" data-perm="report.generate">生成报告</div>\n'
    assert b in broken, "反向验证锚点 2 未命中"
    broken = broken.replace(b, b + a, 1)
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_broken_tab.html")
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(broken)
    original = globals()["REPORTS_HTML"]
    globals()["REPORTS_HTML"] = tmp
    try:
        import pytest
        with pytest.raises(AssertionError):
            test_reports_has_analysis_tab_first()
    finally:
        globals()["REPORTS_HTML"] = original
        os.remove(tmp)


if __name__ == "__main__":       # pragma: no cover
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))