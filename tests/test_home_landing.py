# -*- coding: utf-8 -*-
"""登录/返回/刷新三种进入方式落点 —— 防回退守护（2026-10-18）。

## 用户需求（三条必须同时成立）

  ① **登录后**直接显示「首页总览」（不看上次停在哪）；
  ② 任何内页点「返回主界面」也显示「首页总览」；
  ③ **刷新页面**仍显示当前所在页。

## 为什么这三条会互相打架（本轮根因）

① 与 ③ 都要经 `GET /` 落地，差别只在「这次进入是**主动导航**还是**刷新**」。
改之前 `GET /` 一律读 `localStorage.lastPage` ⇒ 登录后永远回到上次停留的内页，
**需求①根本不生效**；同时 8 个页面的「返回主界面」指向 `/index`，而系统
**没有 `/index` 路由** ⇒ 点了就是 404（坏链接）。

解法是引入**一次性主动导航信号** `?page=<内页键>`：登录与返回按钮都带它，
`core.js::_resolveLandingPage()` 优先认它、落地即用 `history.replaceState` 抹掉
⇒ F5 时 URL 已干净、走 `lastPage` ⇒ ③ 不受影响。

## 本文件锁住什么

  · 落点解析函数存在且**优先级正确**（信号 > lastPage > 默认 home）；
  · 白名单是**模块级唯一权威**（不得在 `navigateTo` 内另写一份）；
  · 默认页 = home；
  · 登录页**不再按角色**分流、带 `?page=home`；
  · 全部「返回主界面/返回首页」链接指向 `/?page=home`，无 `/index` 残留；
  · `main.py` 有 `/index` 兼容路由（防漏改处 404）；
  · `navigateTo` 仍写 `lastPage`（③ 的存储前提）。

末尾有**逐项反向验证**：把每处的关键片段破坏一次，对应判据必须报错
（不变红 ⇒ 判据是假的，属于"工具坏了比没验证更危险"那一类）。
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, "static", "js", "core.js")
LOGIN = os.path.join(ROOT, "static", "login.html")
INDEX = os.path.join(ROOT, "static", "index.html")
MAIN = os.path.join(ROOT, "main.py")
STATIC = os.path.join(ROOT, "static")

HOME_HREF = "/?page=home"
BACK_TEXTS = ("返回主界面", "返回首页")


def _s(path: str) -> str:
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def _code(path: str) -> str:
    """读取并**剥掉注释**后的源码（存在性/否定性断言的唯一取材口径）。

    ★ 必须剥注释（本仓明载的事故形态）：否则在注释里提一句
      `localStorage.getItem('lastPage')`，判据"不得直接读 lastPage"就误报；
      反过来"注释里还留着字段名"也会让存在性断言假绿。两边都是假结论。
    """
    src = _s(path)
    src = src.replace("\r\n", "\n").replace("\r", "\n")
    # 块注释
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    # 行注释（JS `//` 与 Python `#`）；只剥"行首到行尾"的整段注释，避免误伤字符串
    src = re.sub(r"(?m)^\s*//.*$", "", src)
    src = re.sub(r"(?m)^\s*#.*$", "", src)
    return src


def _fn_body(path: str, header_re: str) -> str:
    """取某函数的函数体（**剥注释**后；行尾归一化为 `\\n`）。

    ★ 行尾必须归一化：本仓 HTML/JS 为 CRLF，而判据锚点写的是 `\\n` ——
      不归一化时 `"  navigateTo(...);\\n"` 这类锚点永远匹配不上，
      反向验证会变成"锚点未命中"的空转（本轮实际踩到）。
    """
    m = re.search(header_re, _code(path), re.S)
    assert m, "未找到函数体：%s（判据锚点失效？）" % header_re
    return m.group(1)


def _pages() -> list:
    return sorted(
        os.path.join(STATIC, n) for n in os.listdir(STATIC) if n.endswith(".html")
    )


# ══════════ ① 落点解析（唯一权威） ══════════
def test_landing_resolver_exists() -> None:
    """`_resolveLandingPage()` 必须存在（落点解析的唯一权威）。"""
    src = _s(CORE)
    assert "function _resolveLandingPage()" in src, (
        "core.js 缺 `_resolveLandingPage()` —— 落点解析没有唯一权威，"
        "登录/返回/刷新三种进入方式会各判一套")


def test_landing_priority_signal_first() -> None:
    """优先级必须是：显式信号 > lastPage > 默认页。"""
    body = _fn_body(CORE, r"function _resolveLandingPage\(\)\s*\{(.*?)\n\}")
    i_sig = body.find("_readLandingParam()")
    i_saved = body.find("lastPage")
    i_def = body.find("_DEFAULT_PAGE")
    assert i_sig != -1, "落点解析未读取一次性信号（`?page=`）⇒ 登录/返回到不了首页总览"
    assert i_saved != -1, "落点解析未读 lastPage ⇒ 刷新无法停在当前页"
    assert i_def != -1, "落点解析未用 `_DEFAULT_PAGE` 兜底"
    assert i_sig < i_saved < i_def, (
        "落点优先级错误（须为 信号 < lastPage < 默认页 的先后顺序）："
        "sig=%d saved=%d def=%d" % (i_sig, i_saved, i_def))


def test_landing_signal_is_one_shot() -> None:
    """信号必须**一次性**：落地后抹掉 URL 参数，否则 F5 会被永久钉在该页。"""
    assert "function _consumeLandingParam()" in _s(CORE), (
        "缺 `_consumeLandingParam()`（一次性信号未实现）")
    body = _fn_body(CORE, r"function _consumeLandingParam\(\)\s*\{(.*?)\n\}")
    assert "replaceState" in body, (
        "未用 `history.replaceState` 抹除参数 ⇒ 会留下历史记录，"
        "用户按浏览器「后退」会回到带参数的 URL，行为不一致")
    # 且必须在解析时被调用
    r = _fn_body(CORE, r"function _resolveLandingPage\(\)\s*\{(.*?)\n\}")
    assert "_consumeLandingParam()" in r, (
        "`_resolveLandingPage` 未消费一次性信号 ⇒ 刷新仍被强制落到该页（需求(3)失效）")


def test_landing_param_validated_against_whitelist() -> None:
    """`?page=xxx` 非法值必须**视为没给**，绝不静默改成别的页。"""
    body = _fn_body(CORE, r"function _readLandingParam\(\)\s*\{(.*?)\n\}")
    assert "_allowedPages.indexOf" in body, (
        "信号未按白名单校验 ⇒ 传入非法 page 会被 `navigateTo` 静默改成 "
        "tax-doc-analysis（猜错用户意图比不管更糟）")
    assert "return null" in body, "非法信号未返回 null（会被当成有效信号）"


def test_whitelist_is_module_level_single_source() -> None:
    """白名单必须是**模块级唯一权威**，`navigateTo` 内不得再写一份。"""
    code = _code(CORE)
    hits = re.findall(r"(?m)^var _allowedPages = \[", code)
    assert len(hits) == 1, (
        "`var _allowedPages = [` 模块级声明出现 %d 次（应恰好 1 次）——"
        "多头维护会导致落点解析与切页校验各判一套" % len(hits))
    # navigateTo 内不得重新声明（★ 剥注释后判据，否则注释里提一句就误报）
    body = _fn_body(CORE, r"function navigateTo\(page\)\s*\{(.*?)\n\}")
    assert "var _allowedPages" not in body, (
        "`navigateTo` 内又声明了一份白名单 ⇒ 两个权威，会各自漂移")


def test_default_page_is_home() -> None:
    """默认落点（首次访问）必须是首页总览。"""
    m = re.search(r"(?m)^var _DEFAULT_PAGE = '([^']+)'", _code(CORE))
    assert m, "core.js 未定义 `_DEFAULT_PAGE`"
    assert m.group(1) == "home", (
        "默认落点应为 'home'，实际 '%s'（新用户会直接跳进内页，看不到总览）" % m.group(1))


def test_enter_app_uses_resolver() -> None:
    """`enterApp` 必须走落点解析（不得再直接读 lastPage）。"""
    body = _fn_body(CORE, r"async function enterApp\(companyId, companyName\)\s*\{(.*?)\n\}")
    assert "navigateTo(_resolveLandingPage())" in body, (
        "`enterApp` 未使用 `_resolveLandingPage()` ⇒ 登录后仍回上次内页（需求(1)失效）")
    assert "localStorage.getItem('lastPage')" not in body, (
        "`enterApp` 仍直接读 lastPage ⇒ 绕过了唯一权威（需求(1)失效）")


def test_navigate_writes_last_page() -> None:
    """`navigateTo` 必须写 `lastPage`（需求(3)「刷新停在当前页」的存储前提）。"""
    body = _fn_body(CORE, r"function navigateTo\(page\)\s*\{(.*?)\n\}")
    assert "localStorage.setItem('lastPage', page)" in body, (
        "`navigateTo` 未写 lastPage ⇒ 刷新无法恢复当前页（需求(3)失效）")


# ══════════ ② 登录后进首页总览 ══════════
def test_login_goes_home_not_roles() -> None:
    """登录成功必须进首页总览，不得再按角色分流到 `/roles`。"""
    src = _s(LOGIN)
    assert "location.assign(" in src, "login.html 未找到跳转语句"
    assert '"/?page=home"' in src, (
        "登录后未带 `?page=home` 一次性信号 ⇒ 会落到 lastPage（需求①失效）")
    assert 'data.role === "admin" ? "/roles"' not in src, (
        "登录仍按角色分流到 /roles ⇒ 管理员登录后看不到首页总览（需求①失效）")


def test_login_keeps_forced_password_change() -> None:
    """强制改密必须优先于首页总览（否则等于静默废除安全策略）。"""
    src = _s(LOGIN)
    assert "must_change_password" in src, (
        "登录跳转未处理 `must_change_password` ⇒ 未改初始密码也能进系统")
    assert "/change-password" in src, "缺强制改密目标页"


# ══════════ ③ 返回主界面 → 首页总览 ══════════
def test_no_index_deadlink_remains() -> None:
    """不得再有 `href=\"/index\"`（该路由历史上不存在，点了就是 404）。"""
    bad = []
    for p in _pages():
        src = _s(p)
        for m in re.finditer(r"<a\b[^>]*>.*?</a>", src, re.S | re.I):
            tag = m.group(0)
            if any(t in tag for t in BACK_TEXTS) and re.search(
                    r"""href\s*=\s*['"]/(?:index|index\.html)['"]""", tag):
                bad.append(os.path.basename(p))
    assert not bad, "以下页面的「返回主界面」仍是 /index 死链：%s" % bad


def test_all_back_links_point_to_home() -> None:
    """所有「返回主界面/返回首页」链接必须指向 `/?page=home`。"""
    bad = []
    total = 0
    for p in _pages():
        src = _s(p)
        for m in re.finditer(r"<a\b[^>]*>.*?</a>", src, re.S | re.I):
            tag = m.group(0)
            if not any(t in tag for t in BACK_TEXTS):
                continue
            total += 1
            hm = re.search(r"""href\s*=\s*(['"])([^'"]*)\1""", tag)
            href = hm.group(2) if hm else ""
            if href != HOME_HREF:
                bad.append("%s → %s" % (os.path.basename(p), href or "(无 href)"))
    assert total > 0, "未找到任何「返回主界面/返回首页」链接（判据锚点失效？）"
    assert not bad, (
        "以下「返回主界面」未指向 %s（点了看不到首页总览）：%s" % (HOME_HREF, bad))


def test_wire_tool_is_idempotent() -> None:
    """注入器 `--check` 必须返回 0（幂等；不幂等会让每次运行都产生 diff）。"""
    import subprocess
    exe = sys.executable
    r = subprocess.run(
        [exe, os.path.join(ROOT, "scripts", "_wire_home_links.py"), "--check"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=ROOT,
    )
    assert r.returncode == 0, (
        "`_wire_home_links.py --check` 返回 %d（说明有页面未同步）：\n%s%s"
        % (r.returncode, r.stdout, r.stderr))


# ══════════ ④ `/index` 兼容路由 ══════════
def test_index_compat_route_exists() -> None:
    """`main.py` 必须有 `/index` 兼容路由（防漏改处与遗留书签 404）。"""
    code = _code(MAIN)
    assert re.search(r'@app\.get\("/index"\)', code), (
        "main.py 缺 `@app.get(\"/index\")` 兼容路由 ⇒ 遗留书签仍 404")
    # 取路由定义处**之后的整段**（到本体函数结束），因为 `/index` 与 `/index.html`
    # 是连续两个装饰器共用一个函数；判据要看到函数体里的重定向目标。
    i = code.index('@app.get("/index")')
    seg = code[i:i + 1200]
    assert "RedirectResponse" in seg, "`/index` 路由未做重定向"
    assert "?page=home" in seg, (
        "`/index` 重定向目标不是首页总览 ⇒ 语义与「返回主界面」按钮不一致")


# ==============================================================================
# (5) 反向验证 —— 判据必须真能变红（"工具坏了比没验证更危险"）
#
#   做法：把被测文件内容做**一处**替换后写到临时副本，再把上面**已经写好的
#   判据函数**（不是复制一份新判据）指向该副本执行，断言它必须抛 AssertionError。
#     · 复用同一函数 ⇒ 不存在"判据有两份、只有一份是真的"；
#     · 破坏在真实文件内容上做 ⇒ 注入方式真能触发判据（不是空转）。
# ==============================================================================

def _with_broken(path_attr, old, new, fn):
    """把 `path_attr` 指向的文件做一次替换后执行 `fn`，断言其必须失败。

    ★ **取材口径**：读原始文件、`\\r\\n` 归一化为 `\\n`（与 `_code()` 的判据口径
      一致），再做替换。不归一化时锚点写 `\\n` 而文件是 CRLF ⇒ 永远命中不了
      （反向验证退化为"空转"，本轮实际踩到）。
    ★ 写回的副本同样用 `\\n`；判据只做源码扫描、不做行尾敏感匹配，故安全。
    """
    import pytest

    raw = _s(globals()[path_attr]).replace("\r\n", "\n").replace("\r", "\n")
    assert old in raw, (
        "反向验证锚点未命中（%s 中找不到 %r）—— 说明注入方式无法触发判据，"
        "本项反向验证是空转的" % (path_attr, old[:60]))
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


def test_reverse_r1_signal_priority_broken() -> None:
    """注入：落点改为「先 lastPage、后信号」⇒ 优先级判据必须报错。"""
    import pytest

    src = _s(CORE).replace("\r\n", "\n").replace("\r", "\n")
    m = re.search(r"function _resolveLandingPage\(\)\s*\{(.*?)\n\}", src, re.S)
    assert m, "未找到落点解析函数"
    body = m.group(1)
    broken_body = body.replace(
        "var explicit = _readLandingParam();", "var explicit = null;", 1)
    broken_body = broken_body.replace(
        "if (saved && _allowedPages.indexOf(saved) !== -1) { return saved; }",
        "if (saved && _allowedPages.indexOf(saved) !== -1) { return saved; }\n"
        "  var _late = _readLandingParam(); if (_late) { return _late; }", 1)
    assert broken_body != body, "反向验证：优先级注入未生效"
    broken = src[:m.start(1)] + broken_body + src[m.end(1):]
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_broken_prio.js")
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(broken)
    original = globals()["CORE"]
    globals()["CORE"] = tmp
    try:
        with pytest.raises(AssertionError):
            test_landing_priority_signal_first()
    finally:
        globals()["CORE"] = original
        os.remove(tmp)


def test_reverse_r2_one_shot_broken() -> None:
    """注入：不再消费一次性信号 ⇒ 刷新会被永久钉在该页，判据必须报错。"""
    _with_broken("CORE", "  _consumeLandingParam();\n", "",
                 test_landing_signal_is_one_shot)


def test_reverse_r3_dual_whitelist_broken() -> None:
    """注入：`navigateTo` 内重新声明白名单 ⇒ 唯一权威判据必须报错。"""
    _with_broken(
        "CORE",
        "if (_allowedPages.indexOf(page) === -1) { page = 'tax-doc-analysis'; }",
        "var _allowedPages = ['home', 'tax-doc-analysis'];\n"
        "  if (_allowedPages.indexOf(page) === -1) { page = 'tax-doc-analysis'; }",
        test_whitelist_is_module_level_single_source)


def test_reverse_r4_default_page_broken() -> None:
    """注入：默认落点改回 tax-doc-analysis ⇒ 默认页判据必须报错。"""
    _with_broken("CORE", "var _DEFAULT_PAGE = 'home';",
                 "var _DEFAULT_PAGE = 'tax-doc-analysis';", test_default_page_is_home)


def test_reverse_r5_enter_app_broken() -> None:
    """注入：`enterApp` 绕过唯一权威直接读 lastPage ⇒ 需求(1) 判据必须报错。"""
    _with_broken("CORE", "navigateTo(_resolveLandingPage());",
                 "navigateTo(localStorage.getItem('lastPage') || 'home');",
                 test_enter_app_uses_resolver)


def test_reverse_r6_login_role_split_broken() -> None:
    """注入：登录跳转改回按角色分流 ⇒ 登录判据必须报错。"""
    src = _s(LOGIN).replace("\r\n", "\n").replace("\r", "\n")
    old = ('location.assign(\n'
           '          data.must_change_password ? "/change-password" : "/?page=home"\n'
           '        );')
    assert old in src, "反向验证锚点未命中（login.html 跳转语句结构变了？）"
    _with_broken("LOGIN", old,
                 'location.assign(data.role === "admin" ? "/roles" : "/");',
                 test_login_goes_home_not_roles)


def test_reverse_r7_backlink_deadlink_broken() -> None:
    """注入：某页返回链接退回 `/index` ⇒ 死链与指向判据都必须报错。

    让 `_pages()` 只返回一个临时副本页面（**不碰真实文件**）。
    """
    import pytest

    tmp = os.path.join(STATIC, "_broken_backlink.html")
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write('<!doctype html><html><body>\n'
                 '  <a href="/index">返回主界面</a>\n'
                 '</body></html>\n')
    original = _pages
    globals()["_pages"] = lambda: [tmp]
    try:
        with pytest.raises(AssertionError):
            test_no_index_deadlink_remains()
        with pytest.raises(AssertionError):
            test_all_back_links_point_to_home()
    finally:
        globals()["_pages"] = original
        os.remove(tmp)


def test_reverse_r8_param_unvalidated_broken() -> None:
    """注入：信号不校验白名单（直接当页键用）⇒ 判据必须报错。"""
    _with_broken("CORE",
                 "if (v && _allowedPages.indexOf(v) !== -1) { return v; }",
                 "if (v) { return v; }",
                 test_landing_param_validated_against_whitelist)


def test_reverse_r9_enter_app_missing_resolver_broken() -> None:
    """注入：把 `enterApp` 的落点解析整句删掉 ⇒ 判据必须报错（防判据正则过宽）。"""
    _with_broken("CORE", "  navigateTo(_resolveLandingPage());\n", "",
                 test_enter_app_uses_resolver)


if __name__ == "__main__":       # pragma: no cover
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
