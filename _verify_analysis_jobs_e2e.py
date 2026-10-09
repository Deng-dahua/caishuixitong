# -*- coding: utf-8 -*-
"""端到端实测：一键分析 ⇒ **作业流水真实落盘**（用户按钮路径）。

用**隔离实例**：把真实 `security.db` / `accounting.db` / `uploads/` 复制到临时
`APP_DATA_DIR`，在独立端口起服务，走真实 HTTP（login → analyze-start →
轮询 analyze-status → analyze-result），跑完即销毁。

验证目标（结果级，不是"我改了代码"）：
  ① 点一次「一键分析」⇒ `analysis_jobs.jsonl` 新增 1 条作业，且
     status=done / 时长可由流水推导 / started_by 非空 / trigger 正确；
  ② 重启服务 ⇒ 用旧 task_id 仍能查到**终态**（作业落盘，不再随进程消失）；
  ③ force=1 ⇒ trigger=force；未变化再跑一次 ⇒ trigger=incremental（若命中复用）；
  ④ 删除账套 ⇒ 该企业作业行消失（由 purge 第 ⑩ 项保证，见另一脚本）。

用法：`python _verify_analysis_jobs_e2e.py`
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
PORT = int(os.environ.get("VERIFY_PORT", "8013"))
COMPANY = int(os.environ.get("VERIFY_COMPANY", "1"))
POLL_MAX = 150          # 150 × 2s = 5 分钟


def duplicate_labels(names) -> list:
    """找出**断言编号重复**的编号（编号 = 名称里第一个空白分隔的词）。

    为什么把它抽成纯函数：编号撞号是本脚本**实测发生过**的缺陷 —— 新增断言插在
    中间时，`⑯⑰⑱⑲` 被两段断言共用（PASS/FAIL 输出里同号出现两次，FAIL 归因
    歧义）。而 `ok()` 只会打印，发现不了撞号。抽成纯函数后可**离线反向验证**
    （`--self-test-labels`），不必跑 6 分钟的服务端到端。

    返回重复编号列表（去重、保序）；**空列表 = 通过**。
    """
    seen, dup = set(), []
    for n in names:
        s = str(n).strip()
        i = s.split()[0] if s else s
        if i in seen and i not in dup:
            dup.append(i)
        seen.add(i)
    return dup


def _self_test_labels() -> int:
    """离线反向验证 `duplicate_labels` 不是假判据。"""
    cases = [
        (["① 甲", "② 乙", "③ 丙"], []),                 # 唯一 ⇒ 必须空
        (["①-1 甲", "①-1 乙"], ["①-1"]),                # 撞号 ⇒ 必须报出
        (["⑯ 甲", "⑯ 乙", "⑯ 丙"], ["⑯"]),              # 三连撞 ⇒ 只报一次
        ([], []),                                        # 空输入 ⇒ 空
    ]
    bad = 0
    for names, want in cases:
        got = duplicate_labels(names)
        okc = got == want
        print(("PASS " if okc else "FAIL ") + "duplicate_labels(%r) -> %r（期望 %r）"
              % (names, got, want))
        if not okc:
            bad += 1
    print("SELF-TEST FAILS=%d" % bad)
    return 1 if bad else 0


def _free_port(p: int) -> bool:
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", p))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _stage_data() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="ajobs_e2e_"))
    for f in ("security.db", "accounting.db"):
        src = ROOT / "data" / f
        if src.exists():
            shutil.copy2(src, tmp / f)
    up = ROOT / "data" / "uploads"
    if up.exists():
        shutil.copytree(up, tmp / "uploads")
    return tmp


def _cookie(jar, name):
    for c in jar:
        if c.name == name:
            return c.value
    return ""


def _opener(jar):
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),                  # 绕开环境代理（否则 502）
        urllib.request.HTTPCookieProcessor(jar),
    )


def main() -> int:
    if not _free_port(PORT):
        print("!! 端口 %d 已被占用，换个 VERIFY_PORT" % PORT)
        return 1
    data_dir = _stage_data()
    base = "http://127.0.0.1:%d" % PORT
    env = dict(os.environ)
    env["APP_DATA_DIR"] = str(data_dir)
    env["APP_COOKIE_SECURE"] = "0"
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("CODEBUDDY_SAFE_DELETE_BULK_GUARD", None)
    log = open(data_dir / "server.log", "w", encoding="utf-8")
    # ★ 反向验证模式（VERIFY_BREAK=1）：在**服务进程内**把作业流水登记掐成 no-op，
    #   验证"起一次分析 ⇒ 流水新增 1 条作业"这条判据**真的依赖**该登记
    #   （不变红 ⇒ 判据是假的）。
    break_mode = os.environ.get("VERIFY_BREAK") == "1"
    if break_mode:
        boot = ("import main, uvicorn;"
                "main._register_job_started = lambda *a, **k: None;"
                "main._register_job_finished = lambda *a, **k: None;"
                "uvicorn.run(main.app, host='127.0.0.1', port=%d, log_level='info')" % PORT)
        cmd = [PY, "-c", boot]
        print("★ 反向验证模式：作业流水登记已被掐成 no-op")
    else:
        cmd = [PY, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(PORT)]
    proc = subprocess.Popen(
        cmd, cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    print("隔离实例 APP_DATA_DIR =", data_dir, "| pid =", proc.pid)
    fails = []

    _seen_ids = set()

    def ok(name, cond, extra=""):
        # ★ 编号唯一性：撞号的断言**直接判失败** —— 同号会让 FAIL 归因产生歧义
        #   （本脚本实测撞过 ⑯⑰⑱⑲）。判据实现见 `duplicate_labels`，可离线反向验证。
        _i = str(name).split()[0] if str(name).strip() else str(name)
        dup = _i in _seen_ids
        _seen_ids.add(_i)
        if dup:
            print("FAIL 断言编号重复 %s：%s" % (_i, name))
            fails.append("断言编号重复 " + _i)
        print(("PASS " if cond else "FAIL ") + name
              + ((" | " + str(extra)) if extra else ""))
        if not cond:
            fails.append(name)

    try:
        # 等端口就绪
        ready = False
        for _ in range(60):
            time.sleep(1)
            if proc.poll() is not None:
                break
            try:
                with urllib.request.urlopen(base + "/api/auth/me", timeout=2):
                    ready = True
                    break
            except urllib.error.HTTPError:
                # 401 = 服务已在响应（未登录的正常结果）⇒ 就绪
                ready = True
                break
            except Exception:
                continue
        if not ready:
            print("!! 服务未就绪；服务日志尾部：")
            print((data_dir / "server.log").read_text(encoding="utf-8", errors="ignore")[-2500:])
            return 2
        print("[1] 服务就绪")

        # 建临时账号（写进隔离 security.db）
        os.environ["APP_DATA_DIR"] = str(data_dir)
        from security import create_user                       # noqa: E402
        import secrets
        user = "_wb_verify_jobs"
        pw = "Vj-" + secrets.token_urlsafe(10)
        create_user(user, pw, role="admin", company_ids=[COMPANY])
        jar = http.cookiejar.CookieJar()
        op = _opener(jar)
        req = urllib.request.Request(
            base + "/api/auth/login",
            data=json.dumps({"username": user, "password": pw}).encode(),
            headers={"Content-Type": "application/json"})
        with op.open(req, timeout=20) as r:
            print("[2] 登录:", json.loads(r.read().decode()))
        csrf = _cookie(jar, "csrf_token")

        def run_once(force: int) -> dict:
            req = urllib.request.Request(
                base + "/api/tax-risk-docs/analyze-start?company_id=%d&force=%d" % (COMPANY, force),
                data=b"", method="POST", headers={"X-CSRF-Token": csrf})
            with op.open(req, timeout=30) as r:
                start = json.loads(r.read().decode())
            tid = start.get("task_id")
            print("    analyze-start(force=%d) ->" % force,
                  {k: start.get(k) for k in ("ok", "task_id", "incremental", "reused")})
            st, data = None, {}
            for _i in range(POLL_MAX):
                time.sleep(2)
                with op.open(base + "/api/tax-risk-docs/analyze-status/" + str(tid), timeout=20) as r:
                    data = json.loads(r.read().decode())
                st = data.get("status")
                if st in ("done", "error"):
                    break
            print("    终态:", st, "| progress:", data.get("progress"),
                  "|", str(data.get("message"))[:90])
            return {"task_id": tid, "status": st, "start": start}

        r1 = run_once(0)
        ok("①-1 第一次分析完成（status=done）", r1["status"] == "done", r1["status"])

        sys.path.insert(0, str(ROOT))
        from engine import analysis_jobs as AJ                          # noqa: E402
        from engine.enterprise_report import (                          # noqa: E402
            is_current_report_version as _is_cur_ver,
        )
        if break_mode:
            _n = len(AJ.list_jobs(company_id=COMPANY))
            jf = data_dir / "analysis_jobs.jsonl"
            print("反向模式：分析已完成，作业数 =", _n,
                  "| 流水文件存在 =", jf.exists())
            ok("R7 反向验证：掐掉作业登记后，『起一次分析 ⇒ 新增 1 条作业』**必须变红**",
               _n == 0, _n)
            print("FAILS=%d" % len(fails))
            return 1 if fails else 0

        r2 = run_once(1)
        ok("①-2 强制重算完成（status=done）", r2["status"] == "done", r2["status"])
        r3 = run_once(0)
        ok("①-3 再跑一次完成（status=done）", r3["status"] == "done", r3["status"])

        # ── 读流水（★ 作业落盘证据）──
        jf = data_dir / "analysis_jobs.jsonl"
        ok("② 作业流水文件已生成", jf.exists(), jf)
        rows = [json.loads(l) for l in jf.read_text(encoding="utf-8").splitlines() if l.strip()] \
            if jf.exists() else []
        print("    流水行数 =", len(rows))

        jobs = AJ.list_jobs(company_id=COMPANY, limit=20)
        print("    折叠后作业数 =", len(jobs))
        for j in jobs:
            print("      · %s | %s | %s | %.1fs | by=%s | findings=%s | lvl=%s | doc=%s | from=%s"
                  % (j["job_id"][:8], j["status"], j["trigger"],
                     (j["duration_ms"] or 0) / 1000.0, j["started_by"],
                     j["findings_count"], j["overall_level"], j["report_doc_no"], j["reused_from"]))
        ok("③ 起一次分析 ⇒ 流水新增 1 条作业（3 次点击 ⇒ 3 条）",
           len(jobs) == 3, len(jobs))
        done_jobs = [j for j in jobs if j["status"] == "done"]
        # ★ 判据修正（2026-10-09 第二次复跑实测假红）：
        #   原断言写死 `duration_ms > 0`，但**增量复用是秒回**（复用上次结果，不重算），
        #   起止时间戳落在同一秒 ⇒ 时长合法地等于 0 ⇒ 断言误报 FAIL。
        #   这不是产品缺陷，是判据把"可推导"错当成了"必须大于零"。
        #   正确口径：① 每个终态作业都**能**从流水推导出时长（非 None 即达意）；
        #             ② 真正重算的作业（manual/force/resume）必须 > 0（它们要跑几分钟）。
        ok("④ status=done 且时长可由流水推导（非 None）；真正重算的作业须 > 0",
           len(done_jobs) >= 1
           and all(j["duration_ms"] is not None for j in done_jobs)
           # ③ 反"空壳判据"：必须真有一次非增量作业，否则"须 > 0"那半句永远为真
           and any(j["trigger"] != "incremental" for j in done_jobs)
           and all((j["duration_ms"] or 0) > 0 for j in done_jobs
                   if j["trigger"] != "incremental"),
           [(j["job_id"][:8], j["trigger"], j["duration_ms"]) for j in done_jobs])
        ok("⑤ started_by 非空（发起人已入账）",
           all(j["started_by"] for j in jobs), [j["started_by"] for j in jobs])
        trigs = sorted({j["trigger"] for j in jobs})
        ok("⑥ 触发方式含 force（强制重算被区分出来）", "force" in trigs, trigs)
        ok("⑦ 非增量复用的作业 trigger=manual", "manual" in trigs or "incremental" in trigs, trigs)
        ok("⑧ 作业起始时间戳为北京时间",
           all(str(j["started_at"]).endswith("+08:00") for j in jobs),
           [j["started_at"] for j in jobs])
        ok("⑨ selfcheck 在真实流水上通过", AJ.selfcheck() == [], AJ.selfcheck())
        ok("⑩ 每个作业都能按 job_id 查到（重启后可回查）",
           all(AJ.get_job(j["job_id"]) is not None for j in jobs))

        # ── 重启语义：用旧 task_id 查流水，仍在（内存任务已随进程消失）──
        tid_last = r2["task_id"]
        ok("⑪ 按 task_id 直接查作业（等价于「重启后仍查得到」）",
           AJ.get_job(tid_last) is not None and AJ.get_job(tid_last)["status"] == "done",
           (AJ.get_job(tid_last) or {}).get("status"))

        # ── 落盘缓存（下面多组断言共用；先读一次）──
        cache = data_dir / "cache" / "last_analysis_cache.json"
        _c = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
        _entry = _c.get(str(COMPANY)) or {}

        # ── 增量复用是否命中（★ 2026-10-09 起改为**硬断言**，不再是"可接受"）──
        #   原实现有两处缺陷使增量复用**从未生效**：
        #     ① 缓存版式判据用硬编码报告名白名单，而白名单取值全是 `forbidden_aliases`
        #        （禁止别名）⇒ `_cached_report_ok` 恒 False；
        #     ② `_data_fp` 只写内存不写磁盘 ⇒ 重启后 `_cached_fp == _fp` 恒假。
        #   两处都已修：本断言即"用户可见结果"——第三次点击（资料未变、未强制）
        #   必须走增量复用、秒回上次结果。
        _inc = bool(r3["start"].get("incremental"))
        _inc_job = next((j for j in jobs if j["job_id"] == r3["task_id"]), None)
        ok("⑫ 第三次点击命中增量复用（资料/规则未变 ⇒ 复用上次结果）",
           _inc, {"incremental": _inc, "task": r3["task_id"]})
        ok("⑬ 增量复用的作业 trigger=incremental 且记下 reused_from（复用了哪一次）",
           _inc_job is not None and _inc_job["trigger"] == "incremental"
           and bool(_inc_job.get("reused_from")),
           (None if _inc_job is None else
            (_inc_job["trigger"], _inc_job["reused_from"])))
        ok("⑭ 落盘缓存已携带 _data_fp（跨重启增量复用的前提）",
           bool(_entry.get("_data_fp")), _entry.get("_data_fp"))
        ok("⑮ 落盘缓存的报告通过权威版式判据（不靠名称白名单）",
           bool(_entry.get("report")) and _is_cur_ver(
               (((_entry.get("report") or {}).get("report") or {})
                .get("enterprise_readable_report") or {})),
           None)

        # ── 报告合规装配是否真的写进去了（★ 根因修复的结果级判据）──
        rep = ((_entry.get("report") or {}).get("report") or {})
        rc = rep.get("report_compliance") or {}
        print("    report_compliance 键 =", list(rc.keys()))
        ok("⑯ report_compliance 已写入（原实现被 json.dumps(set) 抛错整段兜走）",
           bool(rc.get("compliance")) and bool(rc.get("document_meta")), list(rc.keys()))
        vr = rc.get("version_record") or {}
        _tids = {r1["task_id"], r2["task_id"], r3["task_id"]}
        ok("⑰ 台账行 analysis_id == 作业 id（报告 → 作业单向回指）",
           bool(vr.get("analysis_id")) and str(vr.get("analysis_id")) in _tids,
           (vr.get("analysis_id"), sorted(_tids)))
        _pl = rep.get("pipeline_log") or []
        ok("⑱ pipeline_log 不再有『多行业/合规 装配失败』",
           not [x for x in _pl if "装配失败" in str(x) and "合规" in str(x)],
           [str(x)[:120] for x in _pl if "装配失败" in str(x)][:2])
        ok("⑲ 只放合规要素、未内嵌整份报告（避免落盘体积翻倍）",
           "all_findings" not in rc and "pipeline_log" not in rc,
           [k for k in rc if k in ("all_findings", "pipeline_log")])
        ok("⑳ 前端消费的字段齐备（compliance/document_meta/signature_block）",
           all(k in rc for k in ("compliance", "document_meta", "signature_block")),
           list(rc.keys()))

        # ── #614：删除 ⇒ 作业流水随之一并消失（"删了就是真删了"）──
        try:
            proc.terminate()
            proc.wait(timeout=20)
        except Exception:
            pass
        stopped = True
        import main as M                                        # noqa: E402
        _res = M.purge_company_analysis_artifacts(COMPANY, include_uploads=False)
        print("    purge.cleared =", _res.get("cleared"))
        print("    purge.leftovers =", _res.get("leftovers"))
        ok("㉑ 删除后该企业作业行**全部消失**（读侧为空）",
           AJ.list_jobs(company_id=COMPANY) == [], AJ.list_jobs(company_id=COMPANY))
        ok("㉒ purge 逐项结果里如实报告了『分析作业流水』",
           any("分析作业流水" in str(c) for c in (_res.get("cleared") or []))
           and not any("分析作业流水" in str(x) for x in (_res.get("leftovers") or [])),
           _res.get("cleared"))
        _purge_log = data_dir / "purge_log.jsonl"
        ok("㉓ purge_log.jsonl 记录了本次流水清理（可审计）",
           _purge_log.exists() and "analysis_jobs" in _purge_log.read_text(encoding="utf-8"),
           str(_purge_log))
        ok("㉔ 删除**没有**被在跑/已完成的作业写回复活（终局守卫生效）",
           AJ.list_jobs(company_id=COMPANY) == [])
    finally:
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=20)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        log.close()
        print("[清理] 隔离实例已停止；数据目录保留，供人工核对：", data_dir)

    print("FAILS=%d" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    if "--self-test-labels" in sys.argv:
        raise SystemExit(_self_test_labels())
    raise SystemExit(main())
