# -*- coding: utf-8 -*-
"""五项界面需求的防回退守护（2026-10-19 第二批）。

## 用户需求
  ① 风险结果与复核（`/risks`）的【刷新】按钮删除；
  ② 报告生成与导出（`/reports`）的【刷新】按钮删除；
  ③ 「为什么切换模块的时候还会显示资料风险分析报告的页面？」；
  ④ `/reports` 报告列表/历史版本：列表设置选择框 + 【删除选中】按钮；
  ⑤ 「修改密码模块设置到登录页面去」。

## ③ 的真实根因（本文件要锁住的）
报告正文**自带整页封面**（`tax-doc-analysis.js` 注入
`<div class="cover"><h1>{报告名}</h1>…</div>`，报告名如「内部辅助分析工作底稿」
由 `config/report_identity.json` 唯一权威下发）。内嵌到 `/reports` 后与本页主标题
**并存两个 H1** ⇒ 用户看到报告封面标题，以为"资料风险分析报告"模块没被删掉。
修法是**降级封面而非删除**（封面里的报告编号/被审企业/日期/资料数量是必要信息）。

## ④ 的关键设计
本系统原本**没有"删除报告"能力**（`reports_api.py` 无删除端点）。故本轮**新建**：
  · 服务端 `engine/report_service.delete_reports`（登记行 + 落盘文件移入回收站；
    版本台账 append-only **保留**）；
  · 端点 `POST /api/v1/reports/delete`（权限 `report.generate` + 必须显式 `confirm`）；
  · 审计闸门 `_EXITS` 登记新删除出口。

## ⑤ 的安全约束（必须锁死，否则是真漏洞）
登录页自助改密 = **未登录可用** ⇒ 若无防护，它会成为**绕过登录限流的密码爆破入口**。
故必须：复用登录限流、失败不泄露账号是否存在、改密后撤销全部会话。
另发现并修复既有隐患：`page-memory.js` 的 `change` 监听**不看 `type`**，
只靠 id 关键字跳过 ⇒ 新增的 `pw-old`/`pw-new` 会把**明文密码写进 localStorage**。

末尾有逐项反向验证（注入缺陷 ⇒ 判据必须报错）。
"""
from __future__ import annotations

import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RISKS_HTML = os.path.join(ROOT, "static", "risks.html")
RISKS_JS = os.path.join(ROOT, "static", "js", "risks.js")
REPORTS_HTML = os.path.join(ROOT, "static", "reports.html")
REPORTS_JS = os.path.join(ROOT, "static", "js", "reports.js")
LOGIN_HTML = os.path.join(ROOT, "static", "login.html")
INDEX_HTML = os.path.join(ROOT, "static", "index.html")
MAIN = os.path.join(ROOT, "main.py")
SECURITY = os.path.join(ROOT, "security.py")
REPORTS_API = os.path.join(ROOT, "reports_api.py")
REPORT_SERVICE = os.path.join(ROOT, "engine", "report_service.py")
PAGE_MEMORY = os.path.join(ROOT, "static", "js", "page-memory.js")
AUDIT = os.path.join(ROOT, "tools", "audit_consistency.py")
PROJECTS_HTML = os.path.join(ROOT, "static", "projects.html")


def _s(path: str) -> str:
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def _code(path: str) -> str:
    """剥注释 + 行尾归一化（存在性/否定性断言的唯一取材口径）。

    ★ 本仓 HTML/JS 为 CRLF、且注释里常引用被禁字符串 ⇒ 不归一化/不剥注释必出假判据。
    """
    src = _s(path).replace("\r\n", "\n").replace("\r", "\n")
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"<!--.*?-->", "", src, flags=re.S)
    src = re.sub(r"(?m)^\s*//.*$", "", src)
    src = re.sub(r"(?m)^\s*#.*$", "", src)
    return src


# ══════════ ①② 刷新按钮删除 ══════════
def test_risks_refresh_button_removed() -> None:
    """`/risks` 顶栏不得再有【刷新】按钮（HTML 与 JS 绑定都要清）。"""
    assert 'id="btn-refresh"' not in _code(RISKS_HTML), "risks.html 仍有 #btn-refresh（刷新按钮）"
    assert "el('btn-refresh')" not in _code(RISKS_JS), (
        "risks.js 仍绑定 #btn-refresh ⇒ 元素已删，绑定会抛 null 错误")


def test_reports_refresh_button_removed() -> None:
    """`/reports` 顶栏与报告列表内均不得再有【刷新】按钮。"""
    code = _code(REPORTS_HTML)
    assert 'id="btn-refresh"' not in code, "reports.html 仍有 #btn-refresh（顶栏刷新）"
    assert 'id="btn-list-refresh"' not in code, "reports.html 仍有 #btn-list-refresh（列表刷新）"
    js = _code(REPORTS_JS)
    assert "el('btn-refresh')" not in js and "el('btn-list-refresh')" not in js, (
        "reports.js 仍绑定已删除的刷新按钮")


def test_refresh_capability_not_lost() -> None:
    """★ 删按钮 ≠ 删能力：换项目仍必须触发重取（否则用户只能按 F5）。"""
    rj = _code(RISKS_JS)
    m = re.search(r"el\('project'\)\.onchange\s*=\s*function[\s\S]{0,400}?refreshAll\(\)", rj)
    assert m, "risks.js 的「换项目 ⇒ refreshAll()」被一起删掉了（刷新能力丢失）"
    j = _code(REPORTS_JS)
    m2 = re.search(r"el\('project'\)\.onchange[\s\S]{0,400}?refreshAll\(\)", j)
    assert m2, "reports.js 的「换项目 ⇒ refreshAll()」被一起删掉了（刷新能力丢失）"


# ══════════ ③ 报告封面标题降级 ══════════
def test_cover_demotion_exists() -> None:
    """`/reports` 必须在渲染后**降级**报告封面标题（不是删除封面）。"""
    js = _code(REPORTS_JS)
    assert "_demoteReportCover" in js, "reports.js 缺封面降级函数"
    assert re.search(r"renderTaxDocReport\([^)]*\)\s*;\s*\n\s*_demoteReportCover\(\)", js), (
        "`renderTaxDocReport` 之后**必须**调 `_demoteReportCover()`（否则封面大标题又冒出来）")


def test_cover_demotion_uses_vendor_class_not_deletion() -> None:
    """降级必须是"加类 + 覆盖样式"，**不得**删掉封面节点（那是必要信息）。"""
    js = _code(REPORTS_JS)
    assert ".cover" in js, "未定位报告封面 `.cover`"
    # 不得出现移除封面/清空封面的写法
    for bad in ("cover.remove(", "cover.remove()", "cover.innerHTML = ''",
                "cover.parentNode.removeChild"):
        assert bad not in js, "封面被**删除**（应是降级）——封面含报告编号/被审企业等必要信息"
    html = _s(REPORTS_HTML)
    assert "rpt-cover-card" in html and "rpt-cover-demoted" in html, (
        "reports.html 缺封面降级样式（rpt-cover-card / rpt-cover-demoted）")


def test_report_render_no_longer_polls_dead_file_list() -> None:
    """`renderTaxDocReport` 不得再调 `refreshTaxDocList()`（资料清单已并入 /documents）。

    该调用会白跑一次 `/api/tax-risk-docs/list` 请求并触发误导性 console 报错
    （`#tda-file-list` 在**任何页面**都已不存在）。
    """
    js = _code(os.path.join(ROOT, "static", "js", "tax-doc-analysis.js"))
    m = re.search(r"function renderTaxDocReport\(r\)\s*\{(.*?)\n\}", js, re.S)
    assert m, "未找到 `renderTaxDocReport` 函数体"
    body = m.group(1)
    assert "refreshTaxDocList()" not in body, (
        "renderTaxDocReport 仍在调 refreshTaxDocList()（死路径：元素已不存在，白跑接口 + 误导报错）")


# ══════════ ④ 报告列表勾选 + 删除选中 ══════════
def test_report_list_has_selection_ui() -> None:
    """报告列表必须有：全选框 + 删除选中按钮（且未勾选时不显示）。"""
    html = _s(REPORTS_HTML)
    assert 'id="rep-sel-all"' in html, "reports.html 缺表头全选框 #rep-sel-all"
    assert 'id="btn-del-reports"' in html, "reports.html 缺【删除选中】按钮 #btn-del-reports"
    # ★ 未勾选时不显示：按钮必须带 `hidden` 初始态
    m = re.search(r'<button[^>]*id="btn-del-reports"[^>]*>', html)
    assert m, "未找到 #btn-del-reports 标签"
    assert "hidden" in m.group(0), (
        "【删除选中】按钮初始必须 `hidden`（未勾选时不该出现，否则易误点）")
    assert 'data-perm="report.generate"' in m.group(0), (
        "【删除选中】按钮必须受权限门控（与服务端同一权限点）")


def test_report_list_rows_have_checkbox() -> None:
    """每行必须有勾选框（动态渲染，故在 JS 里断言）。"""
    js = _code(REPORTS_JS)
    assert 'class="rep-sel"' in js, "reports.js 未渲染每行勾选框 .rep-sel"
    assert "REP_PICKED" in js, "reports.js 缺勾选状态容器（口径应与 /projects 一致）"


def test_selection_cleared_on_reload() -> None:
    """重新加载列表必须**清空勾选** —— 绝不删"用户当前看不到的行"。"""
    js = _code(REPORTS_JS)
    m = re.search(r"async function loadList\(\)\s*\{(.*?)\n\}", js, re.S)
    assert m, "未找到 loadList 函数体"
    assert "REP_PICKED = {}" in m.group(1), (
        "loadList 未清空勾选 ⇒ 翻页/换项目后可能删掉看不见的报告（与 /projects 口径不一致）")


def test_delete_requires_explicit_confirm_and_permission() -> None:
    """删除端点必须：显式 `confirm` + 权限门控（否则误点即删）。"""
    src = _code(REPORTS_API)
    assert re.search(r'@router\.post\(\s*"/reports/delete"', src), (
        "reports_api.py 缺 `POST /reports/delete` 端点")
    i = src.index('@router.post(\n    "/reports/delete"') if '@router.post(\n    "/reports/delete"' in src \
        else src.index('/reports/delete')
    seg = src[i:i + 1600]
    assert "_require_perm(session, \"report.generate\")" in seg.replace("'", '"'), (
        "删除端点缺权限门控（应有 `_require_perm(session, \"report.generate\")`）")
    assert "confirm" in seg, "删除端点未要求显式 confirm ⇒ 误点即删"


def test_delete_service_keeps_ledger_and_uses_trash() -> None:
    """服务端删除必须：文件走回收站（可恢复）、台账 append-only 保留。"""
    src = _code(REPORT_SERVICE)
    assert re.search(r"^def delete_reports\(", src, re.M), "report_service 缺 delete_reports"
    m = re.search(r"^def delete_reports\(.*?(?=\n@_boundary|\n^def )", src, re.S | re.M)
    assert m, "未找到 delete_reports 函数体"
    body = m.group(0)
    assert "move_to_trash" in body, "未用 move_to_trash（铁律：删物理文件一律可恢复，禁 os.remove）"
    assert "os.remove(" not in body and "os.unlink(" not in body, (
        "delete_reports 出现 os.remove/os.unlink ⇒ 违反「删除一律可恢复」铁律")
    assert "report_versions" in body or "append-only" in body, (
        "delete_reports 未处理/声明版本台账（append-only 保留，不得删台账行）")


def test_delete_exit_registered_in_audit() -> None:
    """新删除出口必须登记到审计闸门 `_EXITS`（否则闸门报 ERROR）。"""
    src = _s(AUDIT)
    assert '"delete_reports"' in src, (
        "审计闸门 `_EXITS` 未登记 `delete_reports` ⇒ 新增删除路径未申报清理范围")


# ══════════ ⑤ 修改密码移到登录页 ══════════
def test_login_page_has_change_password_panel() -> None:
    """登录页必须有「修改密码」入口与表单（含账号/原密码/新密码/确认）。"""
    html = _s(LOGIN_HTML)
    assert 'id="toggle-change-pw"' in html, "login.html 缺「修改密码」入口"
    for i in ("pw-username", "pw-old", "pw-new", "pw-confirm", "pw-submit"):
        assert 'id="%s"' % i in html, "login.html 缺改密表单元素 #%s" % i


def test_sidebar_change_password_entry_removed() -> None:
    """侧边栏不得再有「修改密码」入口（已统一到登录页）。"""
    assert "/change-password'" not in _code(INDEX_HTML), (
        "index.html 仍有指向 /change-password 的侧边栏入口")

def test_public_change_password_is_whitelisted() -> None:
    """未登录改密端点必须登记免登录白名单（否则被拦成 401，入口在最需要时不可用）。"""
    assert "/api/auth/change-password-public" in _code(SECURITY), (
        "`security.is_public_path` 未登记 `/api/auth/change-password-public`")


def test_public_change_password_reuses_login_throttle() -> None:
    """★ 安全要害：未登录改密**必须复用登录限流**。

    否则它会成为**绕过登录限流的密码爆破入口**（攻击者拿它反复试原密码，
    而登录端点那边风平浪静 —— 限流形同虚设）。
    """
    src = _code(MAIN)
    i = src.index("async def api_auth_change_password_public")
    # 取到下一个装饰器/函数定义为止
    nxt = [x for x in (src.find("\n@app.", i), src.find("\n@app.", i + 1)) if x != -1]
    seg = src[i:(min(nxt) if nxt else len(src))]
    # ★ 断言**真实调用形态**（`_lia(username, client_ip)`），而不是"名字出现在片段里"：
    #   名字可以只出现在 import 行（`login_is_allowed as _lia,`）而调用已被删 ——
    #   首版判据就是这样被 R4 反向验证抓出"太松"的。
    assert re.search(r"_lia\(\s*username\s*,\s*client_ip\s*\)", seg), (
        "未调用 `login_is_allowed`（`_lia(username, client_ip)`）"
        "⇒ 无登录限流，成为绕过限流的密码爆破入口")
    assert re.search(r"_rlr\(\s*username\s*,\s*client_ip\s*,", seg), (
        "未调用 `record_login_result`（`_rlr(username, client_ip, ...)`）"
        "⇒ 失败次数不计入限流（限流永不触发）")
    assert "if not allowed" in seg, "取到限流结论却未据此拒绝 ⇒ 限流形同虚设"


def test_public_change_password_does_not_leak_account_existence() -> None:
    """失败必须统一措辞，不得区分"账号不存在"与"原密码错误"（防账号枚举）。"""
    src = _code(MAIN)
    i = src.index("async def api_auth_change_password_public")
    seg = src[i:i + 4200]
    assert "账号或原密码不正确" in seg, (
        "未把「账号不存在」与「原密码错误」统一为同一措辞 ⇒ 可枚举账号")
    assert "not found" in seg, "未处理 `change_password_with_old` 的 user-not-found 分支"


def test_page_memory_never_stores_passwords() -> None:
    """★ 安全要害：`page-memory.js` 必须按 `type` 排除密码框（不能只靠 id 关键字）。

    既有隐患：`change` 监听不看 `type`，只靠 id 命中 `password|pwd` 跳过 ——
    只要 id 不叫 "password"（如登录页新增的 `pw-old`/`pw-new`），
    **明文密码就被写进 localStorage**。
    """
    src = _code(PAGE_MEMORY)
    assert "isSensitive" in src, (
        "page-memory.js 缺 `isSensitive()` 类型级判据 ⇒ 只靠 id 关键字，密码可能被持久化")
    m = re.search(r"function isSensitive\(el\)\s*\{(.*?)\n  \}", src, re.S)
    assert m, "未找到 isSensitive 函数体"
    body = m.group(1)
    assert "'password'" in body or '"password"' in body, (
        "isSensitive 未按 `type === 'password'` 排除")
    # ★ 三处都必须有守卫，缺一即失效（本判据由 R5 反向验证校准过：
    #   只查 bind 里的 2 处是不够的 —— `remember()` 是唯一的写入点，
    #   它自己没有守卫时，"删掉写入点守卫"这种注入仍会让判据通过）。
    rem = re.search(r"function remember\(el\)\s*\{(.*?)\n  \}", src, re.S)
    assert rem, "未找到 remember 函数体"
    assert "isSensitive(el)" in rem.group(1), (
        "`remember()`（唯一写入点）没有 isSensitive 守卫 ⇒ 只要有一个调用方忘了判，"
        "密码就会被写进 localStorage")
    b = re.search(r"function bind\(\)\s*\{(.*?)\n  \}", src, re.S)
    assert b, "未找到 bind 函数体"
    bind_body = b.group(1)
    assert bind_body.count("isSensitive") >= 2, (
        "`change` 与 `blur` 两条路径都必须过 isSensitive（只改一条等于没修）")


def test_page_memory_skips_login_pw_fields() -> None:
    """登录页的 pw-* 输入框必须被记忆机制排除（它们全是凭据类）。"""
    html = _s(LOGIN_HTML)
    # 三个密码框必须是 type=password（这样 isSensitive 的 type 判据才能生效）
    for i in ("pw-old", "pw-new", "pw-confirm"):
        m = re.search(r'<input[^>]*id="%s"[^>]*>' % i, html)
        assert m, "未找到 #%s" % i
        assert 'type="password"' in m.group(0), (
            "#%s 必须是 type=password（否则会被 page-memory 当普通输入框持久化）" % i)


def test_public_change_password_audited() -> None:
    """未登录改密必须留痕（成功与失败都要）。"""
    src = _code(MAIN)
    i = src.index("async def api_auth_change_password_public")
    seg = src[i:i + 4200]
    assert seg.count("auth.change_password") >= 2, (
        "未登录改密的成功/失败都要写审计（`auth.change_password`），当前不足 2 处")


# ══════════ 反向验证 ══════════
def _with_broken(path_attr, old, new, fn):
    """把 `path_attr` 指向的文件做一次替换后执行 `fn`，断言其必须失败。"""
    import pytest

    raw = _s(globals()[path_attr]).replace("\r\n", "\n").replace("\r", "\n")
    assert old in raw, (
        "反向验证锚点未命中（%s 中找不到 %r）—— 注入无法触发判据，本项是空转的"
        % (path_attr, old[:70]))
    broken = raw.replace(old, new, 1)
    assert broken != raw, "替换未生效"
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "_broken_tmp" + os.path.splitext(globals()[path_attr])[1])
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


def test_reverse_r1_risks_refresh_restored() -> None:
    """注入：把 risks 的刷新按钮加回来 ⇒ 判据必须报错。"""
    _with_broken("RISKS_HTML", '<a href="/?page=home">返回主界面</a>',
                 '<button id="btn-refresh">刷新</button>\n'
                 '    <a href="/?page=home">返回主界面</a>',
                 test_risks_refresh_button_removed)


def test_reverse_r2_cover_demotion_call_removed() -> None:
    """注入：去掉 `_demoteReportCover()` 调用 ⇒ 判据必须报错。"""
    _with_broken("REPORTS_JS", "    _demoteReportCover();\n", "",
                 test_cover_demotion_exists)


def test_reverse_r3_selection_not_cleared() -> None:
    """注入：`loadList` 不再清空勾选 ⇒ 判据必须报错。"""
    _with_broken("REPORTS_JS", "  REP_PICKED = {};                       // ★ 重新加载 ⇒ 清空勾选（不删看不见的行）",
                 "  /* 不清空 */", test_selection_cleared_on_reload)


def test_reverse_r4_throttle_removed() -> None:
    """注入：未登录改密**删掉限流调用** ⇒ 安全判据必须报错。

    ★ 注入必须**删掉调用**而不是改写逻辑 —— 首版我写的是
      `allowed, retry_after = _lia(...)` → `= True, 0`，结果判据仍通过：
      因为 `_lia`（`login_is_allowed` 的别名）以及 import 语句里的名字
      **仍在文件里**，字符串扫描自然还能查到。这是"注入方式无效"，不是判据假。
    """
    src = _s(MAIN).replace("\r\n", "\n").replace("\r", "\n")
    old = ("    allowed, retry_after = _lia(username, client_ip)\n"
           "    if not allowed:")
    assert old in src, "反向验证锚点未命中"
    # 整段替换为"直接放行"，并把 _lia 的具体调用点去掉（import 别名仍在，故
    # 判据需同时看"调用形态"——见下）
    broken = src.replace(old, "    allowed, retry_after = True, 0\n    if not allowed:", 1)
    # 为了让"删掉限流"真能被检出，把别名调用一并去掉（模拟整段被移除）
    broken = broken.replace("login_is_allowed as _lia,", "", 1)
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_broken_main.py")
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(broken)
    original = globals()["MAIN"]
    globals()["MAIN"] = tmp
    try:
        import pytest
        with pytest.raises(AssertionError):
            test_public_change_password_reuses_login_throttle()
    finally:
        globals()["MAIN"] = original
        os.remove(tmp)


def test_reverse_r5_page_memory_type_guard_removed() -> None:
    """注入：`page-memory` 去掉类型守卫（回到只靠 id 关键字）⇒ 判据必须报错。"""
    _with_broken("PAGE_MEMORY",
                 "    if (isSensitive(el)) { return; }\n",
                 "",
                 test_page_memory_never_stores_passwords)


def test_reverse_r6_delete_exit_unregistered() -> None:
    """注入：从审计 `_EXITS` 摘掉 `delete_reports` ⇒ 判据必须报错。"""
    _with_broken("AUDIT", '"delete_reports": "报告交付物级',
                 '"delete_reportsX": "报告交付物级',
                 test_delete_exit_registered_in_audit)


def test_reverse_r7_public_whitelist_removed() -> None:
    """注入：从免登录白名单摘掉未登录改密路径 ⇒ 判据必须报错。"""
    _with_broken("SECURITY", ', "/api/auth/change-password-public"}', '}',
                 test_public_change_password_is_whitelisted)


if __name__ == "__main__":       # pragma: no cover
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))


# ══════════════════════════════════════════════════════════════════════════════
# 第三批（2026-10-19 当晚）：删「分析报告」页签工具条 + 修 markdown 记号泄漏
# ══════════════════════════════════════════════════════════════════════════════

def test_analysis_pane_toolbar_removed() -> None:
    """`/reports`「分析报告」页签里那块工具条（导出PDF/缓存/删除报告 + 说明文案）已删除。

    ★ 但**只删界面入口，不删实现**：三个函数本体必须仍在 `tax-doc-analysis.js` ——
      审计闸门 `check_report_consistency` 的行为级判据依赖 `exportTaxDocReportPdf`
      的函数体（须走 `/api/tax-risk-docs/export`、禁 `window.print`、须读
      `X-Report-Watermark` 回执）。
    """
    code = _code(REPORTS_HTML)
    for bid in ("tda-export-pdf-btn", "tda-cache-btn", "tda-delete-btn"):
        assert 'id="%s"' % bid not in code, (
            "reports.html 仍存在 #%s（该工具条应已删除）" % bid)
    # 报告正文容器必须保留（renderTaxDocReport 硬编码取它）
    assert 'id="tda-report-area"' in _s(REPORTS_HTML), "报告正文容器被误删"
    # 函数实现必须保留（删了会让审计判据报「未找到导出报告函数」）
    tda = _code(os.path.join(ROOT, "static", "js", "tax-doc-analysis.js"))
    for fn in ("async function exportTaxDocReportPdf", "function deleteTaxDocReport",
               "async function showCacheInfo"):
        assert fn in tda, "`%s` 被误删 —— 只应删界面入口，实现须保留" % fn


def test_no_markdown_bold_leak_in_any_page() -> None:
    """★ 任何静态页面的**可见文案**都不得出现成对的 `**`（浏览器会原样显示星号）。

    实证：用户贴回的页面文字里写着「本页签展示**最近一次**…」—— 星号真的显示出来了。
    HTML 不解析 markdown ⇒ 在 `.html` 里 `**` 就是两个星号。
    """
    import re as _re

    bad = []
    for f in sorted(glob.glob(os.path.join(ROOT, "static", "*.html"))):
        raw = _s(f)
        t = _re.sub(r"<!--.*?-->", "", raw, flags=_re.S)          # HTML 注释
        t = _re.sub(r"/\*.*?\*/", "", t, flags=_re.S)             # CSS 注释
        t = _re.sub(r"<style.*?</style>", "", t, flags=_re.S | _re.I)
        t = _re.sub(r"<script.*?</script>", "", t, flags=_re.S | _re.I)
        text = _re.sub(r"<[^>]+>", "", t)                          # 去标签 ⇒ 纯可见文本
        hits = _re.findall(r"\*\*[^*\n]{1,40}\*\*", text)
        if hits:
            bad.append("%s → %s" % (os.path.basename(f), hits[:3]))
    assert not bad, "以下页面的可见文案含 markdown 记号（会原样显示星号）：%s" % bad


def test_markdown_leak_gate_is_wired() -> None:
    """新闸门 `check_no_markdown_leak_in_html` 必须**注册进 `run_checks`**（否则形同虚设）。"""
    src = _s(AUDIT)
    assert "def check_no_markdown_leak_in_html" in src, "审计缺该闸门"
    # 项目铁律：run_checks 源码里必须出现每个 check_* 函数名
    m = re.search(r"def run_checks\(.*?\n(?=def |\Z)", src, re.S)
    assert m, "未找到 run_checks 函数体"
    assert "check_no_markdown_leak_in_html()" in m.group(0), (
        "闸门未注册进 run_checks ⇒ 不会被执行（接线自检会 FATAL，此处提前拦下）")


def test_reverse_r8_analysis_toolbar_restored() -> None:
    """注入：把「导出PDF」按钮加回分析报告页签 ⇒ 判据必须报错。"""
    _with_broken("REPORTS_HTML",
                 '<div id="tda-report-area">',
                 '<button id="tda-export-pdf-btn">导出PDF</button>\n      '
                 '<div id="tda-report-area">',
                 test_analysis_pane_toolbar_removed)


def test_reverse_r9_markdown_leak_injected() -> None:
    """注入：往某页可见文案里塞一对星号 ⇒ markdown 泄漏判据必须报错。

    ★ 注入文件必须落在 `static/` 目录内 —— 该判据是 **glob 遍历 `static/*.html`**
      （它要覆盖全部页面），若把破坏样本写到 `tests/` 下（`_with_broken` 的默认位置），
      判据根本扫不到 ⇒ 反向验证会"注入后仍绿"（首版就是这样假绿的）。
    """
    import pytest

    tmp = os.path.join(ROOT, "static", "_broken_md_leak.html")
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write('<!doctype html><html><body>\n'
                 '  <p>本页签展示**最近一次**完整报告</p>\n'
                 '</body></html>\n')
    try:
        with pytest.raises(AssertionError):
            test_no_markdown_bold_leak_in_any_page()
    finally:
        os.remove(tmp)


def test_reverse_r10_gate_unwired() -> None:
    """注入：把闸门从 `run_checks` 里摘掉 ⇒ 接线判据必须报错。"""
    _with_broken("AUDIT",
                 "+ check_no_markdown_leak_in_html()",
                 "+ None  # 被摘掉",
                 test_markdown_leak_gate_is_wired)
