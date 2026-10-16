# -*- coding: utf-8 -*-
"""旧路由写端点权限补齐 —— **真 HTTP** 结果级验收（MQ2-D1 扩展，2026-10-17）。

判定纪律（与 `scripts/metaq2_sim/perm_matrix.js` 同一口径）：
  · 声明**有**权限 ⇒ 期望**非 403**（403 即"误拒"；400/404/422 说明已进业务层 ⇒ 通过）；
  · 声明**无**权限 ⇒ 期望 **403**（其余状态 = "请求已进业务层" ⇒ 未强制）；
  · 仅管理员端点 ⇒ 只有 system_admin 期望非 403。

★ 探测参数一律用**不存在的资源 id**（999999）与**空 body**：
   · 无权限角色会被拦在业务层之前 ⇒ 零副作用；
   · 有权限角色最多得到一个业务层错误（404/400），不会真改数据。
"""
from __future__ import annotations

import http.cookiejar
import json
import pathlib
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8023"
ROOT = pathlib.Path(__file__).resolve().parent.parent
PW = "MetaQ2-Sim-2026!"
ROLES = {
    "system_admin": "sim_admin",
    "enterprise_finance": "sim_finance",
    "tax_advisor": "sim_advisor",
    "review_expert": "sim_expert",
    "auditor": "sim_auditor",
}
ADMIN = "\x00admin"
ADMIN_USER = "sim_admin"

# (key, 方法, 路径, 所需权限 或 ADMIN, 说明)
PROBES = [
    ("doc.batch_delete", "POST", "/api/tax-risk-docs/batch-delete", "document.write", "批量删除资料"),
    ("doc.purge_pending", "POST", "/api/tax-risk-docs/purge-pending?company_id=999999", "document.write", "清理删除残留"),
    ("doc.delete", "DELETE", "/api/tax-risk-docs/999999?company_id=999999", "document.write", "删除单条资料"),
    ("ana.analyze_start", "POST", "/api/tax-risk-docs/analyze-start?company_id=999999&force=0", "analysis.run", "发起异步分析"),
    ("ana.policy_check", "POST", "/api/policy/check?company_id=999999", "analysis.run", "政策影响检查"),
    ("rev.review", "POST", "/api/tax-risk-docs/review?company_id=999999", "risk.review", "报告复核"),
    ("rev.edit_preview", "POST", "/api/tax-risk-docs/edit-preview?company_id=999999", "risk.review", "编辑效果预览"),
    ("rem.create", "POST", "/api/remediation/create?company_id=999999&finding_type=probe&risk_level=%E4%B8%AD", "risk.review", "创建整改"),
    ("view.ask", "POST", "/api/tax-risk-docs/ask?company_id=999999", "risk.view", "引擎问答"),
    ("rep.workpaper", "POST", "/api/workpaper/generate?company_id=999999", "report.generate", "生成工作底稿"),
    ("rep.deliver", "POST", "/api/compliance/rounds/probe-x/deliver?company_id=999999", "report.generate", "交付报告"),
    ("prj.delete_company", "DELETE", "/api/companies/999999", "project.write", "删除账套"),
    ("prj.industry", "PUT", "/api/companies/999999/industry?industry=probe", "project.write", "改行业分类"),
    ("rule.check_relevance", "POST", "/api/tax-risk-rules/check-relevance", "ruleversion.manage", "规则相关性检查"),
    ("rule.feedback_update", "PUT", "/api/feedback/update", "ruleversion.manage", "改纠正规则库"),
    ("adm.agi_query", "POST", "/api/agi/query?company_id=999999&query=probe", ADMIN, "AGI 问答（遗留）"),
    ("adm.pipeline_history", "DELETE", "/api/pipeline/history?company_id=999999&index=0", ADMIN, "删历史条目"),
    ("adm.create_company", "POST", "/api/companies", ADMIN, "新建账套"),
]

JSON_BODY = {"POST": "{}", "PUT": "{}"}


def _opener() -> tuple:
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),           # ★ trust_env=False 等价：绕开本机 http_proxy
        urllib.request.HTTPCookieProcessor(jar),
    )
    return op, jar


def _call(op, jar, method, path, body=None):
    headers = {}
    data = None
    if body is not None:
        data = body.encode("utf-8")
        headers["Content-Type"] = "application/json"
    if method.upper() not in ("GET", "HEAD"):
        headers["X-CSRF-Token"] = next((c.value for c in jar if c.name == "csrf_token"), "")
    req = urllib.request.Request(BASE + path, data=data, method=method.upper(), headers=headers)
    try:
        with op.open(req, timeout=60) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:                        # noqa: BLE001
        return 0, repr(exc)


def main() -> int:
    role_perms = json.loads(
        (ROOT / "config" / "rbac.json").read_text(encoding="utf-8")
    )["role_permissions"]

    sessions: dict = {}
    for role, user in ROLES.items():
        op, jar = _opener()
        st, txt = _call(op, jar, "POST", "/api/auth/login",
                        json.dumps({"username": user, "password": PW}))
        if st != 200:
            print(f"!! 登录失败 {user}: HTTP {st} {txt[:120]}")
            return 2
        sessions[role] = (op, jar)

    rows = []
    for key, method, path, need, desc in PROBES:
        real_path = path
        for role, (op, jar) in sessions.items():
            declared = (role == "system_admin") if need == ADMIN else (
                role == "system_admin" or need in (role_perms.get(role) or [])
            )
            body = JSON_BODY.get(method)
            st, txt = _call(op, jar, method, real_path, body)
            got403 = st == 403
            if declared and got403:
                verdict = "❌ 误拒"
            elif (not declared) and (not got403):
                verdict = "⚠ 未强制"
            else:
                verdict = "✅ 一致"
            rows.append({"key": key, "desc": desc, "role": role, "need": need,
                         "declared": declared, "status": st, "verdict": verdict,
                         "detail": txt.replace("\n", " ")[:150]})
        print(f"  {key:24s} {need:20s} " + " ".join(
            f"{r['role'][:6]}={r['status']}" for r in rows[-5:]))

    bad = [r for r in rows if not r["verdict"].startswith("✅")]
    print()
    print("=== 汇总 ===")
    print(f"探测项 {len(PROBES)} × 角色 {len(ROLES)} = {len(rows)}")
    print(f"一致 {len(rows)-len(bad)} / 异常 {len(bad)}")
    for r in bad:
        print(f"  {r['verdict']} {r['role']:18s} {r['key']:22s} need={r['need']:20s} "
              f"declared={r['declared']} HTTP={r['status']} | {r['detail'][:110]}")

    out = ROOT / "docs" / "元质量_20261016" / "_scenarios" / "LEGACY_PERM_MATRIX.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"probes": [{"key": k, "desc": d, "need": n} for k, _, _, n, d in PROBES],
                               "rows": rows,
                               "summary": {"total": len(rows), "ok": len(rows) - len(bad),
                                           "bad": len(bad)}},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n台账已写入 {out}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
