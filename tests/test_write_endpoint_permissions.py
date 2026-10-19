# -*- coding: utf-8 -*-
"""写类端点的**功能权限点**校验（MQ2-D1）—— 防回退静态闸门 + 配置一致性。

背景（阶段 2 MQ2-D1，合规型 P0）：权限矩阵 60 项实测 **一致 50 / 放行 10 / 误拒 0** ——
写/动作类端点在**声明无权限**的角色下仍返回 200/201 且**实际产生数据**。
修复：为 22 个 v1 写端点 + 1 个旧路由（删除报告）补 `require_permission` 校验。

本文件守两件事（**防复发**，不依赖真实 HTTP，可常驻 CI）：
  ① `WRITE_GUARD_REQUIRED` 里列的每个写端点，其**端点区间内**必须出现权限校验调用；
  ② 校验用的权限码必须是 `config/rbac.json::permissions` 里**已登记**的码（防拼错码名 ⇒ 恒 403 或恒放行）。

★ 为什么用"端点区间"而不是"整个文件 grep"：整个文件有校验不代表**该端点**有校验
  （同文件其他端点的校验会造成假通过）。
"""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: 写端点 → 期望的权限码（★ 与实现同源；新增写端点必须在此登记，否则测试不覆盖它）
WRITE_GUARD_REQUIRED = {
    ("reports_api.py", "post", "/projects/{project_id}/reports"): "report.generate",
    # ★ 2026-10-19（用户要求：报告列表加「删除选中」）：批量删报告 = 与「生成报告」同一
    #   功能域（能生成才谈得上清理自己生成的交付物）。端点用 POST + `confirm` 显式确认。
    ("reports_api.py", "post", "/reports/delete"): "report.generate",
    ("risks_api.py", "post", "/risks/bulk-review"): "risk.review",
    ("risks_api.py", "post", "/risks/{risk_id}/review"): "risk.review",
    ("risks_api.py", "post", "/risks/{risk_id}/comment"): "risk.review",
    ("analysis_api.py", "post", "/projects/{project_id}/analysis-jobs"): "analysis.run",
    ("analysis_api.py", "post", "/analysis-jobs/{job_id}/cancel"): "analysis.run",
    ("analysis_api.py", "post", "/analysis-jobs/{job_id}/retry"): "analysis.run",
    ("analysis_api.py", "delete", "/analysis-jobs/{job_id}"): "analysis.run",
    ("documents_api.py", "post", "/documents/chunk/init"): "document.write",
    ("documents_api.py", "put", "/documents/chunk/{upload_id}/{chunk_index}"): "document.write",
    ("documents_api.py", "post", "/documents/chunk/{upload_id}/complete"): "document.write",
    ("documents_api.py", "post", "/projects/{project_id}/documents"): "document.write",
    ("documents_api.py", "delete", "/documents/{document_id}"): "document.write",
    ("documents_api.py", "post", "/documents/{document_id}/classify"): "document.write",
    ("documents_api.py", "put", "/documents/{document_id}/parse-status"): "document.write",
    ("projects_api.py", "post", ""): "project.write",
    ("projects_api.py", "put", "/{project_id}"): "project.write",
    ("projects_api.py", "delete", "/{project_id}"): "project.write",
    ("projects_api.py", "post", "/{project_id}/members"): "project.write",
    ("extract_api.py", "post", "/documents/{document_id}/extract"): "document.write",
    ("extract_api.py", "put", "/extracted/{field_id}"): "document.write",
    ("extract_api.py", "post", "/extract/issues/{issue_id}/resolve"): "document.write",
    # 既有合规（另一批已实现，一并纳入守护）
    ("rule_versions_api.py", "post", "/rule-versions/publish"): "ruleversion.manage",
    ("rule_versions_api.py", "post", "/rule-versions/rollback"): "ruleversion.manage",
    ("templates_api.py", "post", "/report-templates/{template_id}"): "template.manage",
    ("templates_api.py", "post", "/report-templates/{template_id}/disable"): "template.manage",
}

#: **Service 层**校验的端点（★ 项目有两种合法模式：API 层 `_require_perm` /
#:  Service 层 `access_service._require`。后者更严格——不经 HTTP 的调用也被覆盖，
#:  故**不**强行统一为 API 层，而是分别守护。）
SERVICE_LAYER_GUARDED = {
    ("rbac_api.py", "post", "/users"): ("engine/access_service.py", "create_user", "user.manage"),
    ("rbac_api.py", "put", "/users/{user_id}"): ("engine/access_service.py", "update_user", "user.manage"),
    ("rbac_api.py", "post", "/roles"): ("engine/access_service.py", "create_custom_role", "role.manage"),
}

#: 校验调用形态（任一命中即视为"已校验"）
_GUARD_PAT = re.compile(r"_require_perm\(|_perm\(request|_request_perm\(request|_require\(session|rbac_allows\(")


def _endpoint_segment(src: str, meth: str, path: str) -> str:
    """取该端点从装饰器到**下一个装饰器**之间的源码片段（避免同文件其他端点造成假通过）。"""
    m = re.search(r'@(?:app|router)\.%s\(\s*"%s"' % (meth, re.escape(path)), src)
    if not m:
        return ""
    nxt = [x for x in (src.find("@router.", m.end()), src.find("@app.", m.end())) if x != -1]
    end = min(nxt) if nxt else len(src)
    return src[m.start():end]


@pytest.mark.parametrize("spec,perm", sorted(WRITE_GUARD_REQUIRED.items()))
def test_write_endpoint_has_permission_guard(spec, perm) -> None:
    """① 每个登记在册的写端点，其**自身区间内**必须有权限校验（且用的是期望的权限码）。"""
    fname, meth, path = spec
    f = ROOT / fname
    assert f.exists(), "文件不存在：%s" % fname
    src = f.read_text(encoding="utf-8")
    seg = _endpoint_segment(src, meth, path)
    assert seg, "未找到端点 %s %s（%s）—— 是否改路径而未同步本表？" % (meth.upper(), path or "(root)", fname)
    assert _GUARD_PAT.search(seg), (
        "写端点缺权限校验：%s %s %s\n（修复：在 `session = _session(request)` 之后加 "
        "`_require_perm(session, \"%s\")`）" % (fname, meth.upper(), path or "(root)", perm))
    assert '"%s"' % perm in seg or "'%s'" % perm in seg, (
        "写端点 %s %s 的校验**不是**期望权限码 %s（实际片段=%s）"
        % (meth.upper(), path or "(root)", perm, seg[:200]))


@pytest.mark.parametrize("spec,perm", sorted(WRITE_GUARD_REQUIRED.items()))
def test_permission_code_is_registered(spec, perm) -> None:
    """② 权限码必须在 `config/rbac.json::permissions` 登记（防拼错码名 ⇒ 恒 403）。"""
    cfg = json.loads((ROOT / "config" / "rbac.json").read_text(encoding="utf-8"))
    codes = {p["code"] for p in (cfg.get("permissions") or [])}
    assert perm in codes, "权限码 `%s` 未在 config/rbac.json 登记（已登记 %d 个）" % (perm, len(codes))


def test_helper_present_in_patched_files() -> None:
    """③ 补过校验的文件必须**能用** `_require_perm`（单一转换点，不自判角色）。

    ★ 2026-10-18（R-02）：收敛前每个文件各自 `def _require_perm(...)` 复制一份
    （`_session` 10 份、`_require_perm` 6 份）——"改一处忘一处"正是权限口径漂移的机制。
    收敛后统一为**别名引用** `engine/api_common`。故判据放宽到"两种形态都算数"，
    但**强度不降**：仍要求最终实现走 `require_permission` 权威，且不得自判角色。
    """
    import engine.api_common as AC

    for fname in ("reports_api.py", "risks_api.py", "analysis_api.py",
                  "documents_api.py", "projects_api.py", "extract_api.py"):
        src = (ROOT / fname).read_text(encoding="utf-8")
        has_def = "def _require_perm(" in src
        has_alias = "_require_perm = require_perm" in src
        assert has_def or has_alias, (
            "%s 既没有定义 `_require_perm`，也没有引用唯一权威的别名" % fname)
        if has_def:
            seg = src[src.index("def _require_perm("):]
            seg = seg[: seg.find("\ndef ", 5)]
            assert "require_permission(" in seg, "%s 的 _require_perm 未走 require_permission 权威" % fname
            assert "session.role" not in seg and "is_admin" not in seg, (
                "%s 的 _require_perm 出现自判角色痕迹（应为唯一权威转发）" % fname)
        else:
            # 别名形态：权威实现必须在 api_common，且它自身仍须满足同样两条要求
            impl_src = (ROOT / "engine" / "api_common.py").read_text(encoding="utf-8")
            seg = impl_src[impl_src.index("def require_perm("):]
            seg = seg[: seg.find("\ndef ", 5)]
            assert "require_permission(" in seg, "api_common.require_perm 未走 require_permission 权威"
            assert "session.role" not in seg and "is_admin" not in seg, (
                "api_common.require_perm 出现自判角色痕迹")
            assert AC.require_perm is not None


def test_main_old_route_report_delete_guarded() -> None:
    """④ 旧路由「删除报告」（破坏性）必须校验 —— MQ2-D1 补的 main.py 端点。"""
    src = (ROOT / "main.py").read_text(encoding="utf-8")
    seg = _endpoint_segment(src, "delete", "/api/tax-risk-docs/report")
    assert seg, "未找到 DELETE /api/tax-risk-docs/report"
    assert "_require_perm(request," in seg, "旧路由「删除报告」缺权限校验"
    assert '"report.generate"' in seg, "旧路由「删除报告」的权限码不是 report.generate"


@pytest.mark.parametrize("spec,svc", sorted(SERVICE_LAYER_GUARDED.items()))
def test_service_layer_guarded_endpoints(spec, svc) -> None:
    """①b **Service 层**校验模式：端点经 `_call(SVC.xxx)` 转发，权限在 Service 内强制。

    ★ 与 API 层模式等价（权限矩阵实测 5/5 一致），但覆盖面更广（不经 HTTP 的调用也被拦）。
    """
    fname, meth, path = spec
    svc_file, svc_fn, perm = svc
    api_src = (ROOT / fname).read_text(encoding="utf-8")
    seg = _endpoint_segment(api_src, meth, path)
    assert seg, "未找到端点 %s %s（%s）" % (meth.upper(), path, fname)
    assert svc_fn in seg, (
        "端点 %s %s 未转发到 Service `%s`（本表假设其校验在 Service 层）"
        % (meth.upper(), path, svc_fn))

    src = (ROOT / svc_file).read_text(encoding="utf-8")
    m = re.search(r"\ndef %s\(" % re.escape(svc_fn), src)
    assert m, "Service 函数 `%s` 不在 %s" % (svc_fn, svc_file)
    nxt = re.search(r"\ndef [a-z_]+\(", src[m.end():])
    body = src[m.start(): m.end() + (nxt.start() if nxt else len(src))]
    assert '_require(session, "%s")' % perm in body, (
        "Service `%s` 未强制权限点 %s（%s）" % (svc_fn, perm, svc_file))
