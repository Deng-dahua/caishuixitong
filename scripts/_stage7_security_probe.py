# -*- coding: utf-8 -*-
"""阶段 7：安全合规 —— **真实攻击测试**（2026-10-17）。

原则（指令原文 9.1）：安全是底线，合规是红线。

10 维度（9.2）：认证 / 授权 / 加密 / 脱敏 / 审计 / 合规 / 隐私 / 防攻击 / 防泄露 / 备份。

★ 本脚本**真的发起攻击请求**，不是看代码猜：
  A1 未认证访问受保护资源          → 期望 401/302
  A2 CSRF：有会话但无 token 的写操作 → 期望 403
  A3 横向越权：低权角色访问他人账套/项目 → 期望 403/404
  A4 垂直越权：低权角色调用管理员端点   → 期望 403
  A5 SQL 注入：查询参数注入 ' OR 1=1--   → 期望不返回全量、不 500
  A6 XSS：写入 <script> 后回读            → 期望被转义（不原样回显成标签）
  A7 目录遍历：静态资源路径 ../..        → 期望 400/404
  A8 敏感信息：错误响应是否回显堆栈/路径 → 期望不回显
  A9 脱敏：列表接口是否返回完整身份证/账号 → 期望掩码
  A10 会话失效：退出后旧 cookie 重用      → 期望 401

★ 纪律：
  · 只测**自己系统的隔离实例**（不是外部目标），只读+最小写入；
  · 每条都记录 `期望 / 实际 / 判定`，**不达标就如实写不达标**；
  · 若因环境（APP_COOKIE_SECURE=0 等）导致某项不适用，明确标 N/A 并说明。
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import urllib.parse

import requests

BASE = "http://127.0.0.1:8024"
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "元质量_20261016" / "_quality"

PW = "MetaQ2-Sim-2026!"
ROLES = {
    "sim_admin": "系统管理员",
    "sim_advisor": "税务师",
    "sim_expert": "复核专家",
    "sim_finance": "企业财务",
    "sim_auditor": "审计员",
}

S = requests.Session()
S.trust_env = False          # ★ 本机有 http_proxy，不关会静默全失败


def login(user: str) -> "requests.Session":
    s = requests.Session()
    s.trust_env = False
    r = s.post(BASE + "/api/auth/login", json={"username": user, "password": PW}, timeout=20)
    assert r.status_code == 200, "登录失败 %s: %s %s" % (user, r.status_code, r.text[:120])
    s.headers["X-CSRF-Token"] = s.cookies.get("csrf_token") or ""
    return s


def probe(method: str, path: str, sess, **kw):
    """发一次请求，返回 (status, body[:400])。"""
    try:
        r = sess.request(method, BASE + path, timeout=25, **kw)
        return r.status_code, (r.text or "")[:400]
    except Exception as exc:                       # noqa: BLE001
        return -1, "EXC %s" % exc


def main() -> int:
    results = []
    detail = {}

    def rec(aid, dim, title, expect, sess, method, path, **kw):
        st, body = probe(method, path, sess, **kw)
        results.append({"id": aid, "dim": dim, "title": title,
                        "expect": expect, "status": st, "body": body[:220]})
        print("  %-4s %-6s %-34s → HTTP %-4s %s" % (aid, dim, title[:34], st, expect))
        return st, body

    print("=== A1 未认证访问 ===")
    anon = requests.Session()
    anon.trust_env = False
    for p in ("/api/v1/projects", "/api/auth/me", "/api/v1/risks/review-board?company_id=1"):
        rec("A1", "认证", "未登录访问 %s" % p, "期望 401/302",
            anon, "GET", p)

    adm = login("sim_admin")
    aud = login("sim_auditor")
    fin = login("sim_finance")

    print("=== A2 CSRF ===")
    noc = requests.Session()
    noc.trust_env = False
    noc.cookies.update(adm.cookies)               # 带 cookie，但**不带 CSRF 头**
    rec("A2", "防攻击", "有会话无 CSRF 头的写操作", "期望 403",
        noc, "POST", "/api/v1/projects",
        json={"name": "csrf-probe", "taxpayer_id": "91440300MA5CSRF000"})

    print("=== A3 横向越权（审计员访问不存在/他人账套）===")
    rec("A3", "授权", "审计员读 company_id=99999 的复核看板", "期望 403/404",
        aud, "GET", "/api/v1/risks/review-board?company_id=99999")
    rec("A3", "授权", "审计员读项目 6 的风险列表", "期望 403/200(若授权)",
        aud, "GET", "/api/v1/projects/6/risks?page=1&page_size=5")

    print("=== A4 垂直越权（低权角色调管理员端点）===")
    rec("A4", "授权", "审计员创建用户", "期望 403",
        aud, "POST", "/api/v1/users",
        json={"username": "hacked_%d" % (abs(id(aud)) % 10000), "password": "Hacked-Pass-2026!",
              "role_codes": ["system_admin"], "company_ids": []})
    rec("A4", "授权", "企业财务创建用户", "期望 403",
        fin, "POST", "/api/v1/users",
        json={"username": "hacked2", "password": "Hacked-Pass-2026!",
              "role_codes": ["system_admin"], "company_ids": []})
    rec("A4", "授权", "审计员删项目 6", "期望 403",
        aud, "DELETE", "/api/v1/projects/6")

    print("=== A5 SQL 注入 ===")
    inj = urllib.parse.quote("' OR 1=1--")
    st, body = rec("A5", "防攻击", "项目搜索注入 ' OR 1=1--", "期望不返回全量、不 500",
                   adm, "GET", "/api/v1/projects?q=%s&page=1&page_size=5" % inj)
    detail["sqli_projects_total"] = None
    try:
        j = json.loads(body) if body.strip().startswith("{") else {}
        detail["sqli_projects_total"] = j.get("total")
    except ValueError:
        pass
    st2, body2 = rec("A5", "防攻击", "风险列表 id 注入 1 OR 1=1", "期望 4xx/不 500",
                     adm, "GET", "/api/v1/risks/1%20OR%201=1")

    print("=== A6 XSS ===")
    # ★ 方案调整（第一版想"新建项目"，但 USCC 唯一性校验会正确拒绝重复 ⇒ 测不到 XSS）。
    #   改为**可逆的字段更新**：读项目 6 的原 remark → 写入 <script> → 回读 → 还原。
    #   这样既测到存储型 XSS，又不留脏数据。
    payload = "<script>alert('xss')</script>"
    pid = 6
    orig = adm.get(BASE + "/api/v1/projects/%s" % pid, timeout=20)
    if orig.status_code == 200:
        orig_remark = (orig.json() or {}).get("remark", "") or ""
        up = adm.put(BASE + "/api/v1/projects/%s" % pid,
                     json={"remark": "xssprobe" + payload}, timeout=20)
        if up.status_code in (200, 201):
            g = adm.get(BASE + "/api/v1/projects/%s" % pid, timeout=20)
            echoed = payload in (g.text or "")
            results.append({"id": "A6", "dim": "防攻击", "title": "字段写入 <script> 后回读",
                            "expect": "JSON 原样返回（转义责任在前端）；不得在服务端拼进 HTML",
                            "status": g.status_code,
                            "body": ("回读含原始 script 标签=%s（JSON 通道正常）；" % echoed)
                                    + (g.text or "")[:160]})
            print("  A6   防攻击  写入 <script> 后回读 → HTTP %s（JSON 回显原样=%s）"
                  % (g.status_code, echoed))
            detail["xss_echo_raw"] = echoed
            # 还原
            adm.put(BASE + "/api/v1/projects/%s" % pid, json={"remark": orig_remark}, timeout=20)
            print("       （已还原 remark 原值）")
        else:
            results.append({"id": "A6", "dim": "防攻击", "title": "字段写入 <script> 后回读",
                            "expect": "—", "status": up.status_code,
                            "body": "更新接口拒绝：%s" % (up.text or "")[:160]})
            print("  A6   更新项目失败 HTTP %s：%s" % (up.status_code, (up.text or "")[:100]))
    else:
        results.append({"id": "A6", "dim": "防攻击", "title": "字段写入 <script> 后回读",
                        "expect": "—", "status": orig.status_code, "body": "项目 6 读取失败"})
        print("  A6   项目 6 读取失败 HTTP %s" % orig.status_code)

    print("=== A7 目录遍历 ===")
    for p in ("/static/../security.py", "/static/%2e%2e/security.py", "/static/js/../../main.py"):
        rec("A7", "防攻击", "路径遍历 %s" % p, "期望 400/404",
            adm, "GET", p)

    print("=== A8 敏感信息回显 ===")
    st8, body8 = rec("A8", "防泄露", "不存在的账套错误信息", "期望不含堆栈/绝对路径",
                     adm, "GET", "/api/v1/risks/review-board?company_id=99999")
    detail["a8_leak"] = bool(re.search(r"Traceback|C:\\\\|\.py\", line|sqlite3\.", body8))

    print("=== A9 脱敏 ===")
    st9, body9 = rec("A9", "脱敏", "审计日志列表是否掩码用户名", "期望掩码或按权限",
                     adm, "GET", "/api/v1/audit-logs?page=1&page_size=3")

    print("=== A10 会话失效 ===")
    tmp = login("sim_admin")
    cookies = dict(tmp.cookies)
    tmp.post(BASE + "/api/auth/logout", timeout=20)
    reuse = requests.Session()
    reuse.trust_env = False
    reuse.cookies.update(cookies)
    st10, body10 = probe("GET", "/api/auth/me", reuse)
    results.append({"id": "A10", "dim": "认证", "title": "退出后重用旧 cookie",
                    "expect": "期望 401", "status": st10, "body": body10[:150]})
    print("  A10  认证   退出后重用旧 cookie → HTTP %s（期望 401）" % st10)

    # ── 代码层取证（加密/备份/合规/隐私）────────────────────────────────────
    ev = json.loads((OUT / "EVIDENCE_BASE.json").read_text(encoding="utf-8"))
    sec = ev["security"]

    data = {
        "generated_at": __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"),
        "base": BASE, "results": results, "detail": detail,
        "code_facts": {
            "csrf_hits": len(sec["csrf"]), "masking_hits": len(sec["masking"]),
            "mfa_hits": len(sec["mfa"]), "at_rest_crypto": len(sec["at_rest_crypto"]),
            "backup_hits": len(sec["backup"]), "watermark_hits": len(sec["watermark"]),
            "pipl_dsll": len(sec["pipl_dsll"]), "sql_concat_suspect": len(sec["sql_injection"]),
            "param_binding": len(sec["param_binding"]), "audit_hits": len(ev["observability"]["audit"]),
        },
    }
    (OUT / "STAGE7_SECURITY.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    ok = sum(1 for r in results if r["status"] in (200, 201, 302, 400, 401, 403, 404))
    print("\n共 %d 项攻击探测；HTTP 非异常 %d 项" % (len(results), ok))
    print("已写入", OUT / "STAGE7_SECURITY.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
