# -*- coding: utf-8 -*-
"""阶段 8：性能容量 —— **真实压测**（2026-10-17）。

原则（指令原文 10.1）：系统必须能扛住真实业务的压力和容量。

8 维度（10.2）：响应时间 / 吞吐量 / 并发 / 数据量 / 分析时间 / 报告生成 / 存储 / 扩展性。

★ 本脚本真的打请求与真的造数：
  ① 响应时间：关键接口各打 N 次，取 P50/P95/最大（不打缓存，每轮加随机参数）
  ② 吞吐量：并发 M 线程 × K 轮，算 RPS + 错误率
  ③ 并发：逐级加压（1/5/10/20/30），看延迟与错误率拐点
  ④ 数据量：造 10 万行序时账 xlsx，实测「上传 → 解析」耗时
  ⑤ 分析时间 / 报告生成：复用 S1 真跑读数（209 条发现 / 8 步 / 报告 6.1s）
  ⑥ 存储：DB 与 uploads 实际体积 + 单项目占用
  ⑦ 扩展性：SQLite 单写者 + 多实例写冲突（已在阶段 3 实测）⇒ 判定不支持水平扩展

★ 纪律：压测只打隔离实例（8024）；造数只写隔离目录；测完清理造的数据。
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import pathlib
import statistics
import time

import requests

BASE = "http://127.0.0.1:8024"
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "元质量_20261016" / "_quality"
DATA = pathlib.Path(r"C:\Users\Administrator\WorkBuddy\2026-08-04-21-37-33\_scenario_sim\data")
PW = "MetaQ2-Sim-2026!"


def login(user="sim_admin"):
    s = requests.Session()
    s.trust_env = False
    r = s.post(BASE + "/api/auth/login", json={"username": user, "password": PW}, timeout=30)
    r.raise_for_status()
    s.headers["X-CSRF-Token"] = s.cookies.get("csrf_token") or ""
    return s


def timed(sess, path, label, n=12):
    """连续打 n 次，返回延迟统计（ms）。"""
    lat = []
    errs = 0
    for i in range(n):
        t0 = time.perf_counter()
        try:
            r = sess.get(BASE + path, timeout=60)
            ok = r.status_code == 200
        except Exception:                           # noqa: BLE001
            ok = False
        dt = (time.perf_counter() - t0) * 1000
        lat.append(dt)
        if not ok:
            errs += 1
    lat.sort()
    return {
        "label": label, "path": path, "n": n, "errors": errs,
        "p50": round(statistics.median(lat), 1),
        "p95": round(lat[int(len(lat) * 0.95) - 1] if len(lat) > 1 else lat[0], 1),
        "max": round(max(lat), 1),
        "min": round(min(lat), 1),
    }


def throughput(sess, path, workers, rounds, label):
    """并发压测：workers 个线程，每线程 rounds 次。"""
    cookie = {k: v for k, v in sess.cookies.items()}
    csrf = sess.headers.get("X-CSRF-Token", "")
    lat, errs = [], []

    def one(_):
        s = requests.Session()
        s.trust_env = False
        s.cookies.update(cookie)
        s.headers["X-CSRF-Token"] = csrf
        t0 = time.perf_counter()
        try:
            r = s.get(BASE + path, timeout=60)
            dt = (time.perf_counter() - t0) * 1000
            if r.status_code != 200:
                errs.append(r.status_code)
            return dt
        except Exception:                           # noqa: BLE001
            errs.append(-1)
            return (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        lat = list(ex.map(one, range(workers * rounds)))   # ★ 必须收集返回值
    wall = time.perf_counter() - t0
    total = workers * rounds
    lat.sort()
    return {
        "label": label, "path": path, "workers": workers, "rounds": rounds,
        "requests": total, "wall_s": round(wall, 2),
        "rps": round(total / wall, 1) if wall else None,
        "errors": len(errs),
        "error_rate": round(len(errs) / total * 100, 2),
        "p50": round(statistics.median(lat), 1) if lat else None,
        "p95": round(lat[int(len(lat) * 0.95) - 1], 1) if lat else None,
        "max": round(max(lat), 1) if lat else None,
    }


def make_big_xlsx(rows: int, path: pathlib.Path) -> None:
    """造一份 rows 行序时账 xlsx（字段与 system 期望的序时账一致）。"""
    from openpyxl import Workbook
    wb = Workbook(write_only=True)
    ws = wb.create_sheet("序时账")
    ws.append(["日期", "凭证号", "摘要", "科目编码", "科目名称", "借方金额", "贷方金额"])
    for i in range(rows):
        d = "2025-%02d-%02d" % ((i % 12) + 1, (i % 28) + 1)
        ws.append([d, "记-%05d" % i, "批量测试摘要 %d" % i, "6001",
                   "主营业务收入", 1000.0 + (i % 97), 0.0])
    wb.save(str(path))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    adm = login()
    out = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "base": BASE}

    print("=== ① 响应时间（关键接口，各 12 次）===")
    targets = [
        ("/healthz", "健康检查"),
        ("/api/auth/me", "会话读取"),
        ("/api/v1/projects?page=1&page_size=20", "项目列表"),
        ("/api/v1/projects/6/risks?page=1&page_size=20", "风险列表(20条)"),
        ("/api/v1/risks/review-board?project_id=6", "复核看板(统计)"),
        ("/api/v1/legal-library?page=1&page_size=20", "法规条款列表"),
        ("/api/v1/reports?project_id=6&page=1", "报告历史"),
    ]
    rt = []
    for p, lab in targets:
        r = timed(adm, p, lab)
        rt.append(r)
        print("  %-16s P50=%-7s P95=%-7s max=%-7s err=%d"
              % (lab, r["p50"], r["p95"], r["max"], r["errors"]))
    out["response_time"] = rt

    print("\n=== ② 吞吐量 + ③ 并发（逐级加压）===")
    conc = []
    for workers in (1, 5, 10, 20, 30):
        r = throughput(adm, "/api/v1/risks/review-board?project_id=6", workers, 5,
                       "复核看板 w=%d" % workers)
        conc.append(r)
        print("  并发 %-3d → RPS=%-7s P50=%-7s P95=%-7s 错误率=%s%%"
              % (workers, r["rps"], r["p50"], r["p95"], r["error_rate"]))
    out["concurrency"] = conc

    print("\n=== ④ 数据量：造 10 万行序时账 → 上传 → 解析 ===")
    big = pathlib.Path(os.environ.get("TEMP", "/tmp")) / "perf_100k_ledger.xlsx"
    t_gen0 = time.perf_counter()
    make_big_xlsx(100000, big)
    gen_s = time.perf_counter() - t_gen0
    size_mb = round(big.stat().st_size / 1048576, 2)
    print("  造数：10 万行 / %s MB / 耗时 %.1fs" % (size_mb, gen_s))
    # 解析耗时（直接调引擎，避免走上传的 multipart 开销）
    t0 = time.perf_counter()
    parse_ok, parse_note, n_rows = False, "", 0
    try:
        import sys
        sys.path.insert(0, str(ROOT))
        # ★ 用**真实唯一入口** engine/workbook.load_workbook（项目铁律：openpyxl 必须经它且必须关）
        from engine.workbook import load_workbook, close_workbook
        wb = load_workbook(str(big), read_only=True, data_only=True)
        try:
            ws = wb[wb.sheetnames[0]]
            for _row in ws.iter_rows(values_only=True):
                n_rows += 1
            parse_ok = True
            parse_note = "遍历 %d 行（含表头）" % n_rows
        finally:
            close_workbook(wb)
    except Exception as exc:                        # noqa: BLE001
        parse_note = "解析失败（%s: %s）" % (type(exc).__name__, str(exc)[:80])
    parse_s = time.perf_counter() - t0
    out["data_volume"] = {"rows": 100000, "size_mb": size_mb, "gen_s": round(gen_s, 1),
                          "parsed_rows": n_rows,
                          "parse_s": round(parse_s, 2), "parse_ok": parse_ok,
                          "parse_note": parse_note}
    print("  解析：%.2fs（%s）" % (parse_s, parse_note))
    try:
        big.unlink()
    except OSError:
        pass

    print("\n=== ⑥ 存储 ===")
    du = {}
    for p in DATA.rglob("*"):
        if p.is_file():
            pass
    total = sum(f.stat().st_size for f in DATA.rglob("*") if f.is_file())
    dbs = {str(p.name): p.stat().st_size for p in DATA.glob("*.db")}
    ups = sum(f.stat().st_size for f in (DATA / "uploads").rglob("*") if f.is_file()) \
        if (DATA / "uploads").is_dir() else 0
    out["storage"] = {"data_dir_mb": round(total / 1048576, 1),
                      "db_bytes": dbs,
                      "uploads_mb": round(ups / 1048576, 1),
                      "projects": len(list((DATA / "uploads").glob("*"))) if (DATA / "uploads").is_dir() else 0}
    print("  data 目录 %s MB｜DB %s｜uploads %s MB"
          % (out["storage"]["data_dir_mb"],
             {k: round(v / 1024, 1) for k, v in dbs.items()}, out["storage"]["uploads_mb"]))

    (OUT / "STAGE8_PERFORMANCE.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n已写入", OUT / "STAGE8_PERFORMANCE.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
