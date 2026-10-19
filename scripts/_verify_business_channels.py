# -*- coding: utf-8 -*-
"""结果级验收：工商通道 **A + C**（2026-10-19）。

## 判据不是"我改了哪个文件"，而是"**这条通道现在到底能不能取到数**"

正向（必须通过）
  ① `local_db` 真账套命中（真实数据，不 mock）；
  ② **A 通道真能取数**：起本地 mock 页面 + 注入 cookie ⇒ 解析出登记字段，
     且来源标注含「A 通道」；
  ③ **C 通道真能取数**：起本地 mock JSON + 注入 token/地址 ⇒ 取到字段并
     经 `engine.business_info.dto` 清洗（含中文别名、金额单位、状态映射）；
  ④ 未配置时**如实失败**：原因里必须出现**可执行配置路径**（变量名），
     而不是"未知错误"这种让人无从下手的措辞。

反向（注入已知缺陷 ⇒ 必须变红）
  ⑤ A 通道：把 `cookie_required` 关掉、让 mock 返回 521 ⇒ 必须失败且原因指明
     Cookie 失效与重配变量（证明 521 分支真的在判，不是摆设）；
  ⑥ C 通道：清空 token ⇒ 必须失败且原因含变量名（证明"未配置"分支真的在判）；
  ⑦ `source_confidence` 表缺失 ⇒ 回落到 `default`，**不得抛异常**（配置容错）。

用法：
    .venv/Scripts/python.exe scripts/_verify_business_channels.py
"""
from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FAILS: list[str] = []
PASSES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASSES if ok else FAILS).append(name)
    print(("  ✅ " if ok else "  ❌ ") + name + (("  —— " + detail) if detail else ""))


# ─────────────────────────── mock 外网 ───────────────────────────
_GSXT_HTML = """<html><body>
<div>深圳测试科技有限公司</div>
<table>
<tr><td>统一社会信用代码</td><td>91440300MA5XXXXX1X</td></tr>
<tr><td>法定代表人</td><td>张三</td></tr>
<tr><td>注册资本</td><td>1000万元</td></tr>
<tr><td>成立日期</td><td>2018-03-15</td></tr>
<tr><td>登记状态</td><td>存续</td></tr>
<tr><td>住所</td><td>深圳市南山区科技园XX路1号</td></tr>
<tr><td>企业类型</td><td>有限责任公司</td></tr>
<tr><td>经营范围</td><td>技术开发；技术服务；软件开发</td></tr>
</table></body></html>"""

_PAID_JSON = {
    "data": {
        "entname": "深圳测试科技有限公司",
        "credit_code": "91440300MA5XXXXX1X",
        "oper_name": "张三",
        "regcap": "1000万元",
        "esdate": "2018-03-15",
        "reg_status": "存续",
        "dom": "深圳市南山区科技园XX路1号",
        "enttype": "有限责任公司",
        "opscope": "技术开发；技术服务；软件开发",
    }
}


class _Handler(BaseHTTPRequestHandler):
    mode = "ok"          # ok | 521
    kind = "html"        # html | json

    def log_message(self, *a):        # 静默
        pass

    def do_GET(self):                 # noqa: N802
        if self.mode == "521":
            self.send_response(521)
            self.end_headers()
            self.wfile.write(b"<html><body>521</body></html>")
            return
        body = (_GSXT_HTML if self.kind == "html"
                else json.dumps(_PAID_JSON, ensure_ascii=False)).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8" if self.kind == "html"
                         else "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve(mode="ok", kind="html"):
    _Handler.mode, _Handler.kind = mode, kind
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, "http://127.0.0.1:%d/?x=1" % httpd.server_address[1]


def main() -> int:
    from engine.business_info import providers as PR
    from engine.business_info import service as SVC
    from engine.business_info import store as ST
    from engine.business_info import dto as DTO

    base_cfg = json.loads((ROOT / "config" / "business_info.json").read_text(encoding="utf-8"))
    # 测试用配置：关掉随机延迟（否则每次等 0.8~2.2s）
    base_cfg = dict(base_cfg)
    base_cfg["request"] = dict(base_cfg.get("request") or {})
    base_cfg["request"]["delay_ms_range"] = [0, 0]

    print("\n【正向】① local_db 真账套命中（真实数据）")
    hit = ST.get("深圳海更数字传媒有限公司")
    check("local_db 能命中真实账套", bool(hit), "账套：%s" % (hit or {}).get("name", ""))

    deadline = __import__("time").time() + 20

    print("\n【正向】② A 通道（人工 cookie）真能取到登记字段")
    httpd_a, url_a = serve("ok", "html")
    cfg_a = dict(base_cfg)
    cfg_a["manual_cookie"] = dict(base_cfg["manual_cookie"])
    cfg_a["manual_cookie"]["search_url"] = url_a
    cfg_a["manual_cookie"]["require_exact_name"] = True
    os.environ["GSXT_COOKIE"] = "TESTCOOKIE=abcdef123456"
    res_a = PR.ManualCookieProvider().query("深圳测试科技有限公司", cfg_a, deadline)
    check("A 通道 ok=True", bool(res_a.ok), res_a.reason or "")
    raw_a = res_a.raw or {}
    check("A 通道解析出社会信用代码", raw_a.get("tax_id") == "91440300MA5XXXXX1X",
          str(raw_a.get("tax_id")))
    check("A 通道解析出法定代表人", raw_a.get("legal_representative") == "张三",
          str(raw_a.get("legal_representative")))
    check("A 通道来源标注为 A 通道", "A 通道" in (res_a.source_detail or ""),
          res_a.source_detail or "")
    prof_a = DTO.build_profile(raw_a, cfg=base_cfg, source="manual_cookie",
                               source_detail=res_a.source_detail, confidence=0.85)
    check("A 通道数据能清洗成 DTO（金额/日期/状态）",
          prof_a.registered_capital == 1000.0 and prof_a.established_date == "2018-03-15"
          and bool(prof_a.registration_status),
          "cap=%s date=%s status=%s" % (prof_a.registered_capital,
                                        prof_a.established_date, prof_a.registration_status))
    httpd_a.shutdown()

    print("\n【正向】③ C 通道（付费 token）真能取到并清洗")
    httpd_c, url_c = serve("ok", "json")
    cfg_c = dict(base_cfg)
    os.environ["BUSINESS_API_TOKEN"] = "tok_test_123"
    os.environ["BUSINESS_API_BASE_URL"] = url_c
    os.environ["BUSINESS_API_PROVIDER"] = "tianyancha"
    res_c = PR.PaidApiProvider().query("深圳测试科技有限公司", cfg_c, deadline)
    check("C 通道 ok=True", bool(res_c.ok), res_c.reason or "")
    raw_c = res_c.raw or {}
    check("C 通道按中文别名取到字段（entname/oper_name）",
          raw_c.get("entname") == "深圳测试科技有限公司" and raw_c.get("oper_name") == "张三",
          json.dumps(raw_c, ensure_ascii=False)[:120])
    prof_c = DTO.build_profile(raw_c, cfg=base_cfg, source="paid_api",
                               source_detail=res_c.source_detail, confidence=0.9)
    check("C 通道数据能清洗成 DTO（别名→标准字段 + 单位换算）",
          prof_c.name == "深圳测试科技有限公司" and prof_c.legal_representative == "张三"
          and prof_c.registered_capital == 1000.0 and prof_c.tax_id == "91440300MA5XXXXX1X",
          "name=%s cap=%s uscc=%s" % (prof_c.name, prof_c.registered_capital, prof_c.tax_id))
    check("C 通道来源标注为 C 通道", "C 通道" in (res_c.source_detail or ""),
          res_c.source_detail or "")
    httpd_c.shutdown()

    print("\n【正向】④ 未配置时如实失败，且给出可执行配置路径")
    for k in ("GSXT_COOKIE", "BUSINESS_API_TOKEN", "BUSINESS_API_BASE_URL", "BUSINESS_API_PROVIDER"):
        os.environ.pop(k, None)
    res_a2 = PR.ManualCookieProvider().query("深圳测试科技有限公司", base_cfg, deadline)
    check("A 未配置 cookie ⇒ 失败", not res_a2.ok)
    check("A 失败原因含变量名与操作步骤",
          "GSXT_COOKIE" in res_a2.reason and "人工通过验证码" in res_a2.reason,
          res_a2.reason[:110])
    res_c2 = PR.PaidApiProvider().query("深圳测试科技有限公司", base_cfg, deadline)
    check("C 未配置 token ⇒ 失败", not res_c2.ok)
    check("C 失败原因含变量名", "BUSINESS_API_TOKEN" in res_c2.reason, res_c2.reason[:110])
    check("失败原因不含'未知原因'这类含糊措辞",
          "未知" not in res_a2.reason and "未知" not in res_c2.reason)

    print("\n【反向】⑤ A 通道 521 分支真的在判（关掉 cookie_required 强行走请求）")
    httpd_r, url_r = serve("521", "html")
    cfg_r = dict(base_cfg)
    cfg_r["manual_cookie"] = dict(base_cfg["manual_cookie"])
    cfg_r["manual_cookie"]["search_url"] = url_r
    cfg_r["manual_cookie"]["cookie_required"] = False
    os.environ["GSXT_COOKIE"] = "STALE=expired000000"
    res_r = PR.ManualCookieProvider().query("深圳测试科技有限公司", cfg_r, deadline)
    check("521 必须失败（不能当成功）", not res_r.ok)
    check("521 原因指明 Cookie 失效与重配变量",
          "521" in res_r.reason and "GSXT_COOKIE" in res_r.reason, res_r.reason[:130])
    httpd_r.shutdown()
    os.environ.pop("GSXT_COOKIE", None)

    print("\n【反向】⑥ C 通道 token 清空必须失败（不能沿用上次环境）")
    os.environ["BUSINESS_API_BASE_URL"] = url_c or "http://127.0.0.1:1/x"
    os.environ.pop("BUSINESS_API_TOKEN", None)
    res_c3 = PR.PaidApiProvider().query("深圳测试科技有限公司", base_cfg, deadline)
    check("token 清空 ⇒ 失败", not res_c3.ok)
    check("失败原因含 BUSINESS_API_TOKEN", "BUSINESS_API_TOKEN" in res_c3.reason,
          res_c3.reason[:110])

    print("\n【反向】⑦ 置信度配置缺失时回落 default，不抛异常")
    try:
        v = SVC.confidence_of("brand_new_channel", {"source_confidence": {"default": 0.66}})
        check("未知通道回落到 default=0.66", v == 0.66, str(v))
        v2 = SVC.confidence_of("paid_api", {"source_confidence": {"paid_api": 0.9, "default": 0.1}})
        check("已登记通道取自身值", v2 == 0.9, str(v2))
        v3 = SVC.confidence_of("x", {})
        check("无配置表也不抛异常（回落 0.7）", v3 == 0.7, str(v3))
    except Exception as exc:                                      # noqa: BLE001
        check("置信度缺失容错", False, "抛异常：%s" % exc)

    print("\n【正向】⑧ 通道状态接口如实反映配置（不回显密钥值）")
    from engine import business_info as BI
    BI.reset_cache()
    ch = BI.channels()
    items = {x["provider"]: x for x in ch["items"]}
    check("通道清单含 local_db/manual_cookie/paid_api",
          set(items) == {"local_db", "manual_cookie", "paid_api"}, str(sorted(items)))
    check("未配置的 A 标 available=False", items["manual_cookie"]["available"] is False)
    check("状态不含任何密钥值",
          all("tok_test_123" not in json.dumps(x, ensure_ascii=False) for x in ch["items"]))
    check("A+C 路线登记在 channel_plan.routes",
          ch["plan"]["routes"] == {"A": "manual_cookie", "C": "paid_api"},
          json.dumps(ch["plan"]["routes"], ensure_ascii=False))

    print("\n" + "=" * 66)
    print("通过 %d 项 | 失败 %d 项" % (len(PASSES), len(FAILS)))
    if FAILS:
        print("失败项：")
        for f in FAILS:
            print("  - " + f)
        return 1
    print("全部通过：工商 A+C 通道**真能取数**，且未配置时如实失败并给出可执行配置路径。")
    return 0


if __name__ == "__main__":
    sys.exit(main())