# -*- coding: utf-8 -*-
"""项目画像自动填列与分析回写 —— 防回退守护（2026-10-19 第四批）。

## 用户四问对应的四件事

  ① 「分析报告所使用的模板是不是和报告模板模块的？」→ **本文件锁住答案**（见
     `test_report_templates_are_two_models`）：同一页 `/reports` 的两个页签走**两套文档模型**：
       · 「分析报告」页签 = 一键分析链 ⇒ 用**报告模板**（`config/report_compliance.json::templates`
         + `engine/industry_params.json` 的行业→模板映射；实测海更为「服务型行业模板（轻资产）」）；
       · 「生成报告」页签 = 导出链（`report_service.build_document`）⇒ **12 节通用结构**，
         且 `_industry_template_meta.applied` 恒为 `False`（**如实声明**不套用）。
  ② 「进入分析报告页面设置为显示页面顶端」→ `test_embed_report_no_autoscroll` +
     `test_embed_report_scrolls_to_top`。
  ③ 「为什么报告能显示行业、项目列表不显示」→ **根因是回写链断了**（不是模块脱离）：
     `test_sync_writes_back_to_projects` + `test_sync_empty_never_overwrites`。
  ④ 「编辑项目页所有信息自动获取自动填列，不要任何自动按钮；工商信息有出入按分析所得更新」
     → `test_no_auto_button_left` / `test_edit_form_calls_suggestions` /
     `test_sync_analysis_value_wins_over_stale`。

末尾是**逐项反向验证**：把每处的关键片段破坏一次，对应判据必须报错
（不变红 ⇒ 判据是假的，属"工具坏了比没验证更危险"那一类）。
"""
from __future__ import annotations

import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

FILL_PY = os.path.join(ROOT, "engine", "project_profile_fill.py")
SVC_PY = os.path.join(ROOT, "engine", "project_service.py")
API_PY = os.path.join(ROOT, "projects_api.py")
AUDIT_PY = os.path.join(ROOT, "engine", "audit_trail.py")
PROJECTS_JS = os.path.join(ROOT, "static", "js", "projects.js")
PROJECTS_HTML = os.path.join(ROOT, "static", "projects.html")
REPORTS_JS = os.path.join(ROOT, "static", "js", "reports.js")
REPORTS_HTML = os.path.join(ROOT, "static", "reports.html")
TDA_JS = os.path.join(ROOT, "static", "js", "tax-doc-analysis.js")
MAIN_PY = os.path.join(ROOT, "main.py")


def _s(path: str) -> str:
    """读文件并**归一化行尾**（本仓 HTML/JS 是 CRLF，锚点写 `\\n` 会永远命中不了）。"""
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read().replace("\r\n", "\n").replace("\r", "\n")


def _code(path: str) -> str:
    """剥注释后的源码（存在性/否定性断言的唯一取材口径）。"""
    src = _s(path)
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"(?m)^\s*//.*$", "", src)
    src = re.sub(r"(?m)^\s*<!--.*?-->\s*$", "", src)
    return src


# ══════════════════════════════════════════════════════════════════════════
# ① 两套文档模型（回答"模板是不是同一个"）
# ══════════════════════════════════════════════════════════════════════════
def test_report_templates_are_two_models() -> None:
    """`/reports` 的两个页签走**两套文档模型**，不得被后来者误改成一套。"""
    from engine.report_service import _industry_template_meta
    meta, decl = _industry_template_meta("广告传媒")
    assert meta["applied"] is False, (
        "导出链（生成报告）必须如实声明 `applied=False`：它走 12 节通用结构，"
        "不套用行业模板的章节重排")
    assert meta["matched"] is True, "「广告传媒」应能匹配到行业模板（匹配信息要照实列出）"
    assert "12 节" in meta["reason"], "必须写明为什么没套用（两套文档模型），不能含混"
    assert decl, "必须给读者一句可见的口径说明（不能只写进 meta）"

    # 分析链（一键分析）确实套用了模板：`apply_template` 写 `report_template_meta`
    from engine.report_template import apply_template
    out, tmeta = apply_template({"x": 1}, "广告传媒")
    assert out["report_template_meta"]["matched"] is True
    assert tmeta["sections"], "分析链必须给出模板章节顺序（实测为 6 章）"
    assert tmeta["template_id"], "必须给出模板 id（行业→模板映射唯一权威在 industry_params）"


def test_analysis_report_declares_its_template() -> None:
    """分析报告正文顶部必须**显示**自己用的模板与章节顺序（而不是只存在后端）。"""
    js = _code(TDA_JS)
    assert "_renderScopeAdoptedBlock" in js
    assert "report_template_meta" in js, "报告未读取模板元信息 ⇒ 用户无从判断模板是否生效"
    assert "章节顺序" in js, "必须显示章节顺序（否则'用了模板'只是空口声明）"


# ══════════════════════════════════════════════════════════════════════════
# ② 进入分析报告 = 页面顶端
# ══════════════════════════════════════════════════════════════════════════
def test_embed_report_no_autoscroll() -> None:
    """`renderTaxDocReport` 在**内嵌页**不得自己滚动（否则一进页面就被滚走）。"""
    code = _code(TDA_JS)
    assert "function renderTaxDocReport(" in code, "未找到 `renderTaxDocReport`"
    # ★ 按"下一个顶层函数"切片，不假设函数长度
    #   （首版写 `[\s\S]{0,200}?\n}` 要求 200 字内遇到收尾花括号 —— 这个函数几百行，
    #    正则永远匹配不到 ⇒ 判据自身失效）
    start = code.index("function renderTaxDocReport(")
    rest = code[start + 10:]
    nxt = re.search(r"(?m)^function ", rest)
    seg = code[start:(start + 10 + nxt.start())] if nxt else code[start:]
    assert len(seg) > 500, "函数切片异常（取不到函数体 ⇒ 后续判据无意义）"
    assert "scrollIntoView" in seg, "该函数内的滚动语句不见了（判据要跟着走）"
    assert "embed-report" in seg, (
        "未按 `body.embed-report` 判定是否内嵌 ⇒ 内嵌时仍会自动滚动到报告区")
    # 必须是"条件滚动"（有 if 包住），不能无条件执行
    assert re.search(r"if\s*\(!?_tdaEmbedded", seg), (
        "滚动语句未被内嵌判定包住（条件被删 ⇒ 行为回到改前）")


def test_embed_report_scrolls_to_top() -> None:
    """`reports.js` 必须主动把视口归位顶部（进页面 / 切页签 / 重渲染三种进入方式）。"""
    js = _code(REPORTS_JS)
    assert "function _scrollPageTop" in js, "缺 `_scrollPageTop()`"
    m = re.search(r"function _scrollPageTop\(\)\s*\{([\s\S]*?)\n\}", js)
    assert m and "scrollTo" in m.group(1), "`_scrollPageTop` 未真正滚动"
    sw = re.search(r"function switchTab\(name\)\s*\{([\s\S]*?)\n\}", js)
    assert sw, "未找到 `switchTab`"
    assert "_scrollPageTop();" in sw.group(1), (
        "switchTab 体内必须归位顶部（否则切到「分析报告」会停在上一页签的滚动位置）。"
        "★ 判据必须限定在函数体内 —— 只查全文的话，别处有调用也会让它通过")
    # 渲染完也要归位
    assert js.count("_scrollPageTop();") >= 2, (
        "渲染完成处也必须归位（否则首屏进来 scrollY 仍非 0）")


def test_reports_html_declares_embed() -> None:
    """`<body class="embed-report">` 是**声明式**标记（不依赖脚本加载顺序）。"""
    html = _s(REPORTS_HTML)
    assert re.search(r"<body[^>]*class=\"[^\"]*embed-report", html), (
        "reports.html 的 body 必须带 `embed-report` 类 —— 这是 `tax-doc-analysis.js` "
        "判断'不要自动滚动'的唯一信号")


# ══════════════════════════════════════════════════════════════════════════
# ③④ 字段派生（不编造）+ 分析回写（补上断掉的链）
# ══════════════════════════════════════════════════════════════════════════
def test_region_from_address_is_deterministic() -> None:
    from engine.project_profile_fill import region_from_address
    assert region_from_address("广东省深圳市南山区某路1号")["value"] == "广东省深圳市"
    assert region_from_address("北京市朝阳区某路")["value"] == "北京市"
    assert region_from_address("内蒙古自治区呼和浩特市某路")["value"] == "内蒙古自治区呼和浩特市"
    # 解析不出来必须**留空 + 原因**，绝不猜
    r = region_from_address("某未知地址")
    assert r["value"] == "" and r["reason"], "解析不出地区时必须留空并说明原因（缺失≠编造）"


def test_region_three_tier_sources() -> None:
    """地区三级推导：地址 → 企业名称行政区划 → 信用代码登记机关码；每级都标来源。"""
    from engine.project_profile_fill import region_of
    a = region_of(address="", company_name="深圳海更数字传媒有限公司",
                  uscc="91440300MA5H824G7M")
    assert a["value"] == "广东省深圳市", "企业名称里的行政区划是登记信息，应能推导出省市"
    assert "企业名称" in a["source"] and "行政区划码" in a["source"], (
        "必须如实标注两段来源（市来自名称、省来自信用代码）")
    b = region_of(address="", company_name="", uscc="91440300MA5H824G7M")
    assert b["value"] == "广东省", "只有信用代码时只能到省"
    assert b["reason"], "只到省必须说明为什么没有市（不能悄悄降级）"
    c = region_of()
    assert c["value"] == "" and c["reason"], "三者全无 ⇒ 留空 + 原因"


def test_period_parse_never_invents() -> None:
    from engine.project_profile_fill import period_parts
    assert period_parts("2025-01 至 2025-12") == ("2025-01-01", "2025-12-31")
    assert period_parts("2025年度") == ("2025-01-01", "2025-12-31")
    assert period_parts("2024-07~2025-06") == ("2024-07-01", "2025-06-30")
    assert period_parts("乱码") == ("", ""), "解析不出必须返回空（不猜一个期间出来）"


def test_analysis_values_marks_source_per_field() -> None:
    """每个字段都必须带来源；取不到必须带原因（用户才能判断"为什么没填"）。"""
    from engine.project_profile_fill import analysis_values
    report = {"target_entity": {"name": "深圳海更数字传媒有限公司",
                                "industry": "广告传媒",
                                "uscc": "91440300MA5H824G7M",
                                "_industry_resolved": {"industry": "广告传媒",
                                                       "source": "销项发票品名推断",
                                                       "confidence": "中高"}},
              "enterprise_readable_report": {"identity": {"period": "2025-01 至 2025-12",
                                                          "taxpayer_id": "91440300MA5H824G7M"}},
              "tax_declarations": [{"_declaration_type": "vat", "period": "2025-01"}]}
    vals = analysis_values(report, None)
    assert vals["industry"]["value"] == "广告传媒"
    assert "销项发票品名推断" in vals["industry"]["source"]
    assert vals["period_start"]["value"] == "2025-01-01"
    assert vals["tax_scopes"]["value"] == ["增值税"]
    # 工商档案没有 ⇒ 每个工商字段都要有 reason
    for k in ("legal_representative", "registered_capital", "registration_status"):
        assert vals[k]["value"] == "" and vals[k]["reason"], (
            "字段 %s 取不到时必须留空 + 原因" % k)


def test_sync_writes_back_to_projects() -> None:
    """★ 核心：分析取得的信息必须写回 **projects**（不是只写 companies）。

    这正是「报告里有行业、项目列表没有」的根因 —— 回写链此前**根本不存在**。
    """
    src = _code_(SVC_PY)
    assert "def sync_profile_from_analysis" in src, "缺回写函数（分析结果无法进项目表）"
    seg = src[src.index("def sync_profile_from_analysis"):]
    assert '"UPDATE projects SET' in seg.replace("'", '"'), (
        "回写必须更新 **projects** 表（写 companies 不会让项目列表显示出来）")
    # 必须在分析完成链路上被调用（只写函数不接线 = 永远不会发生）
    main = _s(MAIN_PY)
    i = main.index("def _persist_one_click_result")
    seg_main = main[i:i + 30000]
    assert "sync_profile_from_analysis" in seg_main, (
        "`_persist_one_click_result` 未调用回写 ⇒ 跑完分析项目表仍为空")
    assert "analysis_values" in seg_main, "回写前必须先按权威派生字段（不能各自算一遍）"


def _code_(path: str) -> str:
    return _code(path)


def test_sync_empty_never_overwrites() -> None:
    """空推导值**永不覆盖**已有值（缺失≠0；也不能把用户填的清掉）。"""
    src = _code_(SVC_PY)
    seg = src[src.index("def sync_profile_from_analysis"):]
    assert "空值不覆盖" in seg or "空值永不覆盖" in seg, "口径注释缺失（后人会改错）"
    assert "if not sv:" in seg and "continue" in seg, (
        "必须有 '取不到值就 continue' 的分支（否则空串会把现值清空）")


def test_sync_period_is_scope_not_overwritten() -> None:
    """稽查期间是**人定的工作边界**：只在项目未设期间时补，绝不覆盖用户设定。"""
    src = _code_(SVC_PY)
    seg = src[src.index("def sync_profile_from_analysis"):]
    assert "只在项目未设期间时补" in seg, "口径注释缺失"
    assert re.search(r"if not \(_clean_str\(r\.get\(\"period_start\"\)\)", seg), (
        "缺'仅当期间为空才写'的判据 ⇒ 会把用户设定的稽查范围改掉")


def test_sync_is_idempotent_and_audited() -> None:
    """重复回写不得反复产生变更；每次回写必须留痕（动作已登记进 `ACTIONS`）。"""
    from engine.audit_trail import ACTIONS, ACTION_CN
    assert "project.profile_sync" in ACTIONS, "回写动作未登记 ⇒ 审计日志会打「未登记的动作」"
    assert ACTION_CN.get("project.profile_sync"), "动作缺中文名（界面/导出不得出现英文码）"
    src = _code_(SVC_PY)
    seg = src[src.index("def sync_profile_from_analysis"):]
    assert '_n(r.get(key)) == _n(sv)' in seg, (
        "必须按归一化值比较（1000 与 1000.0 是同一个值），否则每次打开都报'有出入'")
    assert "_audit(" in seg, "回写必须留痕"


# ══════════════════════════════════════════════════════════════════════════
# ④ 编辑页全自动：没有任何"自动按钮"
# ══════════════════════════════════════════════════════════════════════════
def test_no_auto_button_left() -> None:
    """用户明确要求"不要甚至一个自动按钮" ⇒ 该元素必须彻底不存在。"""
    html = _code(PROJECTS_HTML)
    assert 'id="btn-fetch-bizinfo"' not in html, (
        "`#btn-fetch-bizinfo` 仍在（用户 2026-10-19：不要任何自动按钮/徽标）")
    import json
    perms = json.load(open(os.path.join(ROOT, "config", "frontend_perms.json"),
                           encoding="utf-8"))
    ids = {x.get("id") for x in (perms["pages"].get("projects.html") or [])}
    assert "btn-fetch-bizinfo" not in ids, "元素已删但权限表仍登记 ⇒ 闸门会报「元素不存在」"


def test_auto_trigger_and_rbac() -> None:
    """自动触发：input 防抖 + blur 兜底；权限问 RBAC（且用**就绪标志 loaded**）。"""
    js = _code(PROJECTS_JS)
    assert 'nameInput.addEventListener("input"' in js
    assert 'nameInput.addEventListener("blur"' in js
    assert "window.RBAC" in js and "'project.write'" in js, "权限判断必须问 RBAC"
    m = re.search(r"function bizAllowed\(\)\s*\{([\s\S]*?)\n  \}", js)
    assert m, "未找到 `bizAllowed`"
    body = m.group(1)
    assert "state.loaded" in body or "st.loaded" in body, (
        "必须用 `RBAC.state.loaded` 判就绪（`state.ready` 是**不存在的字段**，"
        "恒为 undefined ⇒ 自动查填永不触发 —— 真机验收抓出来的）")
    assert "RBAC.ready(" in body, (
        "未就绪时要注册回调补查一次，否则页面刚打开就输入会永久得不到自动填列")


def test_derived_fields_are_used() -> None:
    """行业/地区由**后端派生**（`d.derived`），前端不得自建第二套推断。"""
    js = _code(PROJECTS_JS)
    assert "d.derived" in js, "未使用后端派生的行业/地区"
    assert '["industry", "行业"]' in js and '["region", "地区"]' in js, (
        "派生字段未真正填入行业/地区输入框")
    # 后端单一权威：派生只在 service 的模块级入口挂载一次
    svc = _s(os.path.join(ROOT, "engine", "business_info", "service.py"))
    assert "def _with_derived" in svc
    assert "return _with_derived(res)" in svc, "派生必须在模块级入口统一挂载（所有调用方一次到位）"


def test_edit_form_calls_suggestions() -> None:
    """打开编辑页必须自动补全（调 suggestions 接口），并显示来源/原因。"""
    js = _code(PROJECTS_JS)
    assert "profile-suggestions" in js, "编辑页未调用自动补全接口"
    assert "autoCompleteForm" in js, "缺自动补全实现"
    assert "form-autofill" in js, "缺提示区（来源/不可得原因必须可见）"
    html = _code(PROJECTS_HTML)
    assert 'id="form-autofill"' in html, "HTML 缺提示区容器"
    api = _s(API_PY)
    assert "/{project_id}/profile-suggestions" in api, "缺建议接口"
    assert "load_payload" in api, "报告来源必须走唯一权威 `risk_service.load_payload`"
    assert '"project" in detail' in api, (
        "取项目对象要兼容两种返回形状 —— 首版写成 `detail.get('project')` ⇒ "
        "`get_project` 返回的**就是项目本身** ⇒ 拿到 None ⇒ 所有字段「推导不出」")


def test_analysis_value_wins_over_stale() -> None:
    """用户要求：工商信息与分析结果有出入时，**以分析所得为准**（回写覆盖）。"""
    from engine.project_profile_fill import _norm
    # 归一化让 1000 / 1000.0 视为同一值（否则会报假差异）
    assert _norm(1000) == _norm("1000.0") == "1000"
    assert _norm(1000.5) == _norm("1000.50") == "1000.5"
    src = _code_(SVC_PY)
    seg = src[src.index("def sync_profile_from_analysis"):]
    # 有出入时：以传入的（分析）值为准写入
    assert 'sets.append("%s=:_v_%s"' in seg, '未实现「有出入则写入」的语句'


# ══════════════════════════════════════════════════════════════════════════
# 反向验证 —— 判据必须**真能变红**
# ══════════════════════════════════════════════════════════════════════════
def _with_broken(path_attr: str, old: str, new: str, fn) -> None:
    raw = _s(globals()[path_attr])
    assert old in raw, (
        "反向验证锚点未命中（%s 中找不到 %r）—— 注入无法触发判据，本项是空转的"
        % (path_attr, old[:70]))
    broken = raw.replace(old, new, 1)
    assert broken != raw, "替换未生效"
    tmp = os.path.join(ROOT, "tests", "_broken_tmp" + os.path.splitext(globals()[path_attr])[1])
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


def _with_broken_in_func(path_attr: str, func_head: str, old: str, new: str, fn) -> None:
    """在**指定函数体之后**做一次替换（避免改到同文件里别的同名片段）。"""
    raw = _s(globals()[path_attr])
    assert func_head in raw, "函数头未命中：%s" % func_head
    head_at = raw.index(func_head)
    tail = raw[head_at:]
    assert old in tail, (
        "反向验证锚点未命中（%s 的 %s 之后找不到 %r）—— 注入无法触发判据，本项是空转的"
        % (path_attr, func_head, old[:60]))
    broken = raw[:head_at] + tail.replace(old, new, 1)
    tmp = os.path.join(ROOT, "tests", "_broken_tmp" + os.path.splitext(globals()[path_attr])[1])
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


def test_reverse_r1_autoscroll_restored() -> None:
    """注入：去掉内嵌判定（恢复无条件滚动）⇒ ② 判据必须报错。"""
    _with_broken("TDA_JS",
                 "if (!_tdaEmbedded) {",
                 "if (true) {",
                 test_embed_report_no_autoscroll)


def test_reverse_r2_scroll_to_top_removed() -> None:
    """注入：删掉切页签时的归位 ⇒ ② 判据必须报错。"""
    # ★ 注入的必须是**真实调用语句**，不能只改注释
    #   （首版把注释删掉就以为"注入成功" ⇒ 函数体里那行调用还在 ⇒ 判据仍通过）
    _with_broken("REPORTS_JS",
                 "  _scrollPageTop();\n  if (name === 'analysis')",
                 "  if (name === 'analysis')",
                 test_embed_report_scrolls_to_top)


def test_reverse_r3_auto_button_restored() -> None:
    """注入：把"自动"徽标加回表单 ⇒ ④「不要任何自动按钮」判据必须报错。

    ★ 2026-10-19（用户改需求）锚点随表单调整：原锚点是
      `<label>统一社会信用代码 *<input ...>`（带必填星号），而本轮用户要求
      「新建项目只需填企业名称」⇒ 税号不再是必填，`*` 已移除 ⇒ 旧锚点必然失效
      （表现为"反向验证锚点未命中，本项是空转的"）。
      现改用**唯一不变**的锚点：`id="pf-tid"` 的完整标签开头。
      判据本身（`#btn-fetch-bizinfo` 不得出现在 HTML 里）不变，注入点仍然有效。
    """
    _with_broken("PROJECTS_HTML",
                 '<label>统一社会信用代码<input type="text" id="pf-tid"',
                 '<span id="btn-fetch-bizinfo" role="status">自动</span>\n'
                 '          <label>统一社会信用代码<input type="text" id="pf-tid"',
                 test_no_auto_button_left)


def test_reverse_r4_rbac_ready_flag_broken() -> None:
    """注入：把就绪标志改回不存在的 `state.ready` ⇒ ④ 判据必须报错（这正是真踩到的坑）。"""
    _with_broken("PROJECTS_JS",
                 "if (!st.loaded) {",
                 "if (!st.ready) {",
                 test_auto_trigger_and_rbac)


def test_reverse_r5_sync_write_back_removed() -> None:
    """注入：把**回写函数内**的 UPDATE 目标改成 companies ⇒ ③ 判据必须报错。

    ★ 必须限定在 `sync_profile_from_analysis` 函数体内做替换：
      `"UPDATE projects SET` 在 `update_project` 里也有一处，全文替换只会改到那一处
      ⇒ 回写函数丝毫无损 ⇒ 判据仍通过（首版就是这样"注入后仍绿"，属假反向验证）。
    """
    _with_broken_in_func("SVC_PY", "def sync_profile_from_analysis",
                         '"UPDATE projects SET', '"UPDATE companies SET',
                         test_sync_writes_back_to_projects)


def test_reverse_r6_period_overwrite_allowed() -> None:
    """注入：去掉"仅当期间为空才写"的判断 ⇒ ③ 判据必须报错。"""
    _with_broken("SVC_PY",
                 'if not (_clean_str(r.get("period_start")) or _clean_str(r.get("period_end"))):',
                 'if True:',
                 test_sync_period_is_scope_not_overwritten)


def test_reverse_r7_empty_overwrite_allowed() -> None:
    """注入：去掉空值跳过 ⇒ ③ 判据必须报错。"""
    _with_broken("SVC_PY",
                 '                if not sv:\n                    continue',
                 '                if False:\n                    continue',
                 test_sync_empty_never_overwrites)


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
