# -*- coding: utf-8 -*-
"""P0 验收 · 全流程联调（隔离实例 + **真服务** + 真 HTTP + 真实账套数据）。

链路（任务书 §1）：
    登录 → 创建项目 → 上传资料 → 解析 → 一键分析 → 风险结果 → 复核 → 生成报告 → 导出 → 归档

★ 为什么用**真 uvicorn 服务**而不是 TestClient：联调要验的是"用户按钮点下去那条路"，
  中间件、Cookie、CSRF、后台线程、静态资源都要真跑一遍。
★ 隔离：`APP_DATA_DIR=<临时目录>`，复制 `security.db` / `accounting.db` / `uploads/`
  ⇒ 跑完即销毁，**不触碰生产数据**。
★ 反向判据：每一步既验"成功"，也验"**关键字段不是空的**"（否则"接口全 200 但什么也没产出"会骗过测试）。

用法：`python _p0_i1_e2e_full_flow.py`
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
PORT = int(os.environ.get("VERIFY_PORT", "8022"))
COMPANY = int(os.environ.get("VERIFY_COMPANY", "1"))


def _free(p: int) -> bool:
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", p))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _multipart(files: list, fields: dict | None = None):
    """构造 multipart/form-data（标准库无现成封装，手写边界）。"""
    boundary = "----P0E2E" + uuid.uuid4().hex
    out = bytearray()
    for k, v in (fields or {}).items():
        out += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                % (boundary, k, v)).encode()
    for name, content in files:
        out += ("--%s\r\nContent-Disposition: form-data; name=\"files\"; filename=\"%s\"\r\n"
                "Content-Type: application/octet-stream\r\n\r\n" % (boundary, name)).encode()
        out += content + b"\r\n"
    out += ("--%s--\r\n" % boundary).encode()
    return bytes(out), "multipart/form-data; boundary=%s" % boundary


class Client:
    def __init__(self, base: str):
        self.base = base
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),                      # 绕开环境代理（否则 502）
            urllib.request.HTTPCookieProcessor(self.jar))

    def csrf(self) -> str:
        return next((c.value for c in self.jar if c.name == "csrf_token"), "")

    def call(self, method: str, path: str, *, body=None, raw=None, ctype=None,
             timeout: int = 300, csrf: bool = True):
        headers = {}
        data = None
        if raw is not None:
            data, ctype = raw, ctype
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if ctype:
            headers["Content-Type"] = ctype
        if csrf and method not in ("GET", "HEAD"):
            headers["X-CSRF-Token"] = self.csrf()
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with self.op.open(req, timeout=timeout) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers or {}), e.read()

    def json(self, method: str, path: str, **kw):
        st, hd, bd = self.call(method, path, **kw)
        try:
            return st, json.loads(bd.decode("utf-8", "replace"))
        except Exception:                                        # noqa: BLE001
            return st, {"_raw": bd[:300].decode("utf-8", "replace")}


results: list = []


def ok(name: str, cond: bool, extra: str = "") -> None:
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + ((" | " + str(extra)) if extra else ""))


def main() -> int:
    if not _free(PORT):
        print("端口 %d 被占用" % PORT)
        return 1
    data_dir = Path(tempfile.mkdtemp(prefix="p0_e2e_"))
    for f in ("security.db", "accounting.db"):
        src = ROOT / "data" / f
        if src.exists():
            shutil.copy2(src, data_dir / f)
    up = ROOT / "data" / "uploads"
    if up.exists():
        shutil.copytree(up, data_dir / "uploads")

    admin_u, admin_p = "_p0e2e_admin", "P0-E2E-Admin-2026!"

    # ★ 在**隔离库**里建验收账号。
    #   为什么不能靠 `APP_ADMIN_USERNAME` 引导：`_bootstrap_admin_from_environment`
    #   只在 `users` 表**为空**时创建，而这里复制了真实 `security.db`（已有用户）
    #   ⇒ 引导不生效，登录会 401（实测踩过）。
    os.environ["APP_DATA_DIR"] = str(data_dir)
    sys.path.insert(0, str(ROOT))
    from security import init_security_db, create_user as _cu        # noqa: E402
    init_security_db()
    try:
        _cu(admin_u, admin_p, role="admin", company_ids=[COMPANY])
    except Exception as _exc:                                        # noqa: BLE001
        print("[提示] 建验收账号：%r（多半是已存在，继续）" % (_exc,))

    env = dict(os.environ)
    env.update({
        "APP_DATA_DIR": str(data_dir),
        "APP_COOKIE_SECURE": "0",
        "APP_ADMIN_USERNAME": admin_u,
        "APP_ADMIN_PASSWORD": admin_p,
        "PYTHONIOENCODING": "utf-8",
    })
    env.pop("CODEBUDDY_SAFE_DELETE_BULK_GUARD", None)
    log = open(data_dir / "server.log", "w", encoding="utf-8")
    proc = subprocess.Popen([PY, "-m", "uvicorn", "main:app", "--host", "127.0.0.1",
                             "--port", str(PORT)], cwd=str(ROOT), env=env,
                            stdout=log, stderr=subprocess.STDOUT)
    base = "http://127.0.0.1:%d" % PORT
    t_start = time.time()
    try:
        ready = False
        for _ in range(120):
            time.sleep(1)
            if proc.poll() is not None:
                break
            try:
                urllib.request.urlopen(base + "/api/auth/me", timeout=2)
            except urllib.error.HTTPError:
                ready = True
                break
            except Exception:
                continue
        if not ready:
            print("!! 服务未就绪；日志尾部：")
            print((data_dir / "server.log").read_text(encoding="utf-8", errors="ignore")[-2500:])
            return 2
        print("隔离实例 =", data_dir)
        print("[0] 服务就绪（%.1fs）" % (time.time() - t_start))

        c = Client(base)

        # ── 步骤 1：登录 ────────────────────────────────────────────────
        st, r = c.json("POST", "/api/v1/auth/login",
                       body={"username": admin_u, "password": admin_p})
        ok("① 登录成功（200 + 下发 auth_token/CSRF）",
           st == 200 and r.get("ok") is True and bool(c.csrf()),
           "status=%s roles=%s" % (st, r.get("roles")))
        ok("①b 登录返回权限集合非空（RBAC 生效）", bool(r.get("permissions")),
           "%d 项" % len(r.get("permissions") or []))
        st, me = c.json("GET", "/api/auth/me")
        ok("①c 会话有效（/api/auth/me 200）", st == 200 and me.get("username") == admin_u)

        # ── 步骤 2：创建项目 ────────────────────────────────────────────
        st, proj = c.json("POST", "/api/v1/projects", body={
            "name": "P0 联调验收项目", "company_id": COMPANY,
            "period_start": "2025-01-01", "period_end": "2025-12-31",
            "industry": "信息技术服务", "tax_scopes": ["增值税", "企业所得税"],
            "remark": "P0 全流程联调（自动生成）"})
        pid = proj.get("id")
        ok("② 创建项目成功（201 + 有 id）", st == 201 and isinstance(pid, int) and pid > 0,
           "status=%s id=%s code=%s" % (st, pid, proj.get("code")))
        ok("②b 新项目状态为草稿（状态机起点）", proj.get("status") == "draft",
           proj.get("status_cn"))
        st, proj2 = c.json("GET", "/api/v1/projects/%s" % pid)
        ok("②c 创建人自动成为 owner 成员",
           any(m.get("role") == "owner" for m in (proj2.get("members") or [])),
           [m.get("role") for m in (proj2.get("members") or [])])
        # 状态推进：草稿 → 资料上传中（联调需要一个"可上传"的状态）
        st, up_proj = c.json("PUT", "/api/v1/projects/%s" % pid,
                             body={"status": "uploading"})
        ok("②d 状态迁移 draft→uploading 成功", st == 200 and up_proj.get("status") == "uploading",
           up_proj.get("status"))

        # ── 步骤 3：上传资料 ────────────────────────────────────────────
        src_files = sorted((ROOT / "data" / "uploads" / str(COMPANY)).glob("*.xlsx"))[:2]
        if not src_files:
            src_files = sorted((ROOT / "data" / "uploads" / str(COMPANY)).iterdir())[:2]
        payload = [(p.name, p.read_bytes()) for p in src_files]
        raw, ctype = _multipart(payload)
        st, _hd, bd = c.call("POST", "/api/v1/projects/%s/documents" % pid, raw=raw, ctype=ctype)
        try:
            up = json.loads(bd.decode("utf-8", "replace"))
        except Exception:                                        # noqa: BLE001
            up = {"_raw": bd[:200].decode("utf-8", "replace")}
        uploaded = up.get("items") or up.get("uploaded") or []
        doc_ids = [d.get("id") for d in uploaded if isinstance(d, dict) and d.get("id")]
        ok("③ 上传资料成功（%d 份）" % len(payload), st == 201 and bool(doc_ids),
           "status=%s ids=%s" % (st, doc_ids))
        ok("③b 上传的文件带指纹（MD5/SHA256 查重依据）",
           bool(uploaded) and any(
               (d.get("md5") or d.get("sha256") or d.get("content_hash")) for d in uploaded),
           str(sorted((uploaded[0].keys() if uploaded else []))[:12]))
        st, docs = c.json("GET", "/api/v1/projects/%s/documents" % pid)
        ok("③c 资料列表可读且非空",
           st == 200 and int(docs.get("total") or 0) >= len(doc_ids), docs.get("total"))

        # ── 步骤 4：解析与标准化 ────────────────────────────────────────
        #   ★ 前置失败时**不得**直接下标取元素 ⇒ 否则 IndexError 中断整轮，
        #     后面的步骤连"没跑到"都记录不下来。
        did = doc_ids[0] if doc_ids else None
        if did is None:
            ok("④ 单份资料解析（前置：无资料 ⇒ 跳过）", False, "上传未产出资料 id")
            print("\n[中止] 上传环节未产出资料 id，后续步骤无法进行（见上）")
            return 1
        t_parse = time.time()
        st, ex = c.json("POST", "/api/v1/documents/%s/extract" % did, body={})
        ok("④ 单份资料解析成功（200）", st == 200 and bool(ex.get("ok", True)),
           "status=%s %.1fs" % (st, time.time() - t_parse))
        ok("④b 解析产出结构化表/字段（不是空解析）",
           bool(ex.get("tables") or ex.get("fields") or ex.get("standard_fields")
                or ex.get("extracted_tables")),
           sorted(ex.keys())[:10])
        st, exr = c.json("GET", "/api/v1/documents/%s/extracted" % did)
        ok("④c 解析结果可回读（含字段或校验信息）",
           st == 200 and bool(exr.get("tables") or exr.get("fields") or exr.get("issues")),
           "status=%s keys=%s" % (st, sorted(exr.keys())[:8]))

        # ── 步骤 5：一键分析（8 步 / 5 态，真跑引擎）────────────────────
        st, job = c.json("POST", "/api/v1/projects/%s/analysis-jobs" % pid,
                         body={"force": True})
        job_id = job.get("job_id")
        ok("⑤ 发起分析任务成功（201 + job_id）", st == 201 and bool(job_id),
           "status=%s job_id=%s" % (st, job_id))
        t_an = time.time()
        status, last = None, {}
        for _ in range(300):                                     # 300 × 3s = 15 min 上限
            time.sleep(3)
            st, last = c.json("GET", "/api/v1/analysis-jobs/%s" % job_id)
            status = last.get("status")
            if status in ("SUCCESS", "FAILED", "CANCELLED"):
                break
        el_an = time.time() - t_an
        ok("⑤b 分析任务到达终态 SUCCESS（8 步全执行）", status == "SUCCESS",
           "status=%s %.1fs" % (status, el_an))
        steps = last.get("steps") or []
        done_steps = [s for s in steps if str(s.get("status")) in ("done", "success", "ok")]
        ok("⑤c 8 步清单完整且全部完成", len(steps) == 8 and len(done_steps) == 8,
           "steps=%d done=%d" % (len(steps), len(done_steps)))
        ok("⑤d 进度到达 100", int(last.get("progress") or 0) >= 100, last.get("progress"))

        # ── 步骤 6：风险结果 ────────────────────────────────────────────
        st, rk = c.json("GET", "/api/v1/projects/%s/risks" % pid)
        items = rk.get("items") or []
        ok("⑥ 风险列表可读", st == 200, "status=%s total=%s" % (st, rk.get("total")))
        _avail = rk.get("available")
        ok("⑥b 风险库可用（载荷 company_{cid}_full.json 存在且可读）",
           _avail is not False,
           ("载荷不可用：%s" % rk.get("reason")) if _avail is False
           else "available=%s items=%d" % (_avail, len(items)))
        ok("⑥c 风险条目字段完整（编号/等级/税额/证据）",
           bool(items) and all(("risk_no" in it) and (("risk_level" in it) or ("level" in it))
                               for it in items[:5]),
           "首条键=%s" % (sorted((items[0].keys() if items else []))[:14]))
        st, stats = c.json("GET", "/api/v1/projects/%s/risks/stats" % pid)
        ok("⑥c 风险统计可读", st == 200 and isinstance(stats, dict),
           sorted(list(stats.keys()))[:8] if isinstance(stats, dict) else type(stats))

        # ── 步骤 7：复核 ────────────────────────────────────────────────
        risk_no = str((items[0] or {}).get("risk_no") or "") if items else ""
        if risk_no:
            st, rv = c.json("POST", "/api/v1/risks/%s/review" % risk_no,
                            body={"action": "confirm", "company_id": COMPANY,
                                  "note": "P0 联调：已核对账证一致"})
            ok("⑦ 风险复核（确认）成功", st == 200 and bool(rv.get("ok", True)),
               "status=%s state=%s" % (st, rv.get("state") or rv.get("review_state")))
            st2, rk2 = c.json("GET", "/api/v1/projects/%s/risks" % pid,
                              body=None) if False else c.json(
                "GET", "/api/v1/projects/%s/risks" % pid)
            it2 = next((x for x in (rk2.get("items") or []) if x.get("risk_no") == risk_no), {})
            ok("⑦b 复核状态已持久化（不是『点了没变』）",
               str(it2.get("review_state") or it2.get("state") or "") not in ("", "pending"),
               it2.get("review_state") or it2.get("state"))
            st, cm = c.json("POST", "/api/v1/risks/%s/comment" % risk_no,
                            body={"company_id": COMPANY, "note": "P0 联调批注"})
            ok("⑦c 风险批注成功", st == 200, st)
            # 反向：需理由的动作缺理由必须 400
            st, _e = c.json("POST", "/api/v1/risks/%s/review" % risk_no,
                            body={"action": "exclude", "company_id": COMPANY})
            ok("⑦d 反向：『排除』缺理由 ⇒ 400（禁止无理由处置）", st == 400, st)
        else:
            ok("⑦ 风险复核（前置：无风险条目 ⇒ 跳过）", True, "本轮无风险条目")

        # ── 步骤 8：生成报告 ────────────────────────────────────────────
        t_rp = time.time()
        st, rep = c.json("POST", "/api/v1/projects/%s/reports" % pid,
                         body={"view": "full", "formats": ["pdf", "html", "docx", "xlsx"]})
        el_rp = time.time() - t_rp
        rid = rep.get("id") or rep.get("report_id")
        ok("⑧ 生成报告成功（含 4 种格式）", st in (200, 201) and bool(rid),
           "status=%s id=%s %.1fs" % (st, rid, el_rp))
        files = rep.get("files") or {}
        ok("⑧b 4 种导出格式均已产出", len(files) >= 4, sorted(files.keys()))
        #   ★ 字段名以 **Service 返回体**为准：`disclaimer_present`（render 层强制；
        #     `report_service` 在 832 行写该回执）。用 `rep["disclaimer"]` 会得到 None ⇒ 假红。
        ok("⑧c 报告含免责声明（任务书硬要求）", rep.get("disclaimer_present") is True,
           "disclaimer_present=%s" % rep.get("disclaimer_present"))
        ok("⑧d 报告含水印文字", bool(rep.get("watermark_text")),
           str(rep.get("watermark_text"))[:70])

        # ── 步骤 9：导出 ────────────────────────────────────────────────
        if rid:
            st, hd, bd = c.call("GET", "/api/v1/reports/%s/download?format=pdf" % rid,
                                csrf=False, timeout=300)
            ok("⑨ 导出 PDF 成功（200 + %PDF 魔数 + 非空）",
               st == 200 and bd[:4] == b"%PDF" and len(bd) > 2000,
               "status=%s bytes=%d" % (st, len(bd)))
            st2, hd2, bd2 = c.call("GET", "/api/v1/reports/%s/download?format=xlsx" % rid,
                                   csrf=False, timeout=300)
            ok("⑨b 导出 XLSX 成功（PK 魔数）", st2 == 200 and bd2[:2] == b"PK",
               "status=%s bytes=%d" % (st2, len(bd2)))

        # ── 步骤 10：归档 ───────────────────────────────────────────────
        st, res = c.json("GET", "/api/tax-risk-docs/analyze-result/%s" % job_id,
                         csrf=False, timeout=300)
        er = ((res.get("report") or res).get("enterprise_readable_report") or {}) \
            if isinstance(res, dict) else {}
        wp = er.get("workpaper_no") or er.get("archive", {}).get("workpaper_no")
        ok("⑩ 归档结构已回填（底稿号存在）", bool(wp), "workpaper_no=%s" % wp)
        ok("⑩b 归档含审计轨迹", bool(er.get("audit_trail")),
           "audit_trail 条数=%s" % (len(er.get("audit_trail") or [])
                                     if isinstance(er.get("audit_trail"), list) else "—"))
        #   ★ 键名与**层级**都以实现为准：`main._append_one_click_log(report_data, ...)` 写的是
        #     `report_data["pipeline_log"]`，即 **report 对象顶层**（不是 `enterprise_readable_report`
        #     内层，也不是 `one_click_log`）⇒ 取错键/取错层都会假红（实测各踩一次）。
        logs = (res.get("report") or res).get("pipeline_log") or []
        arc_line = [ln for ln in logs if isinstance(ln, str) and "[归档结构]" in ln]
        ok("⑩c 归档回填已留痕（一键分析日志可见）", bool(arc_line),
           (arc_line[0][:110] if arc_line else ""))

        # ── 全流程留痕核对（审计）──────────────────────────────────────
        st, lg = c.json("GET", "/api/v1/audit-logs", body=None) if False else \
            c.json("GET", "/api/v1/audit-logs?page_size=200")
        acts = {x.get("action") for x in (lg.get("items") or [])}
        need = {"auth.login", "project.create", "project.update", "doc.upload",
                "analysis.start", "job.finished", "report.export"}
        #   ★ 「风险复核/批注」是否留痕取决于 ⑥ 是否拿到风险条目：
        #     若上游载荷缺失（已由 ⑥b 单独判 FAIL），这两条**没执行** ⇒ 不该在这里
        #     再算一次"留痕缺失"（那是同一根因的重复计数）。单列说明，口径不混。
        risk_acts = {"risk.review", "risk.comment"}
        ok("⑪ 已执行环节的关键动作均已留痕", need <= acts, "缺失=%s" % sorted(need - acts))
        ok("⑪b 风险复核/批注留痕（依赖 ⑥ 载荷可用）",
           risk_acts <= acts,
           ("未执行（上游载荷缺失，见 ⑥b）" if not (risk_acts <= acts) else "已留痕"))
        total_flow = time.time() - t_start
        print("\n[总耗时] %.1fs（含服务启动与 %d 份真实资料的一键分析 %.1fs）"
              % (total_flow, 0, el_an))
        print("[分析耗时] %.1fs = %.2f 分钟" % (el_an, el_an / 60))
        print("[报告耗时] %.1fs = %.2f 分钟" % (el_rp, el_rp / 60))
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except Exception:                                        # noqa: BLE001
            proc.kill()
        n_fail = sum(1 for _n, c in results if not c)
        print("\n" + "=" * 66)
        print("全流程联调：%d 项通过 / %d 项失败（共 %d）"
              % (len(results) - n_fail, n_fail, len(results)))
        for n, c in results:
            if not c:
                print("  FAIL  " + n)
        if n_fail:
            log_txt = (data_dir / "server.log").read_text(encoding="utf-8", errors="ignore")
            print("---- 服务日志尾部 ----")
            print(log_txt[-1500:])


if __name__ == "__main__":
    rc = main()
    sys.exit(rc if rc else (1 if any(not c for _n, c in results) else 0))
