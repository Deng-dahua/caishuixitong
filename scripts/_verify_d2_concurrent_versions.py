# -*- coding: utf-8 -*-
"""MQ2-D2 端到端验收：**10 路并发生成报告** ⇒ 版本号必须无重复。

★ 判据（结果级，不看"代码改了没"，看"台账里新增了什么"）：
  ① 记录生成前台账行数与已用 (company_id, version) 集合；
  ② 10 路**真 HTTP 并发**打 `POST /api/v1/projects/{pid}/reports`；
  ③ 回读台账**新增行**，断言新增的 version 两两不同；
  ④ 同时给出"修复前基线"对照（历史重复行仍在，append-only 不追溯改）。

用法：python scripts/_verify_d2_concurrent_versions.py
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIM = Path(r"C:\Users\Administrator\WorkBuddy\2026-08-04-21-37-33\_scenario_sim\data")
LEDGER = SIM / "report_versions.jsonl"
BASE = "http://127.0.0.1:8023"
PID = 10
CID = "1"


def _login() -> tuple:
    jar_cookie = {}

    def call(method, path, body=None, cookie=None, csrf=None, timeout=300):
        headers = {}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if cookie:
            headers["Cookie"] = cookie
        if csrf:
            headers["X-CSRF-Token"] = csrf
        req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with op.open(req, timeout=timeout) as r:
                raw = r.read().decode("utf-8", "replace")
                sc = r.headers.get_all("Set-Cookie") or []
                return r.status, raw, sc
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace"), []

    st, raw, sc = call("POST", "/api/auth/login",
                       {"username": "sim_advisor", "password": "MetaQ2-Sim-2026!"})
    assert st == 200, (st, raw[:200])
    pairs = []
    for c in sc:
        kv = c.split(";")[0]
        pairs.append(kv.strip())
    cookie = "; ".join(pairs)
    csrf = next((p.split("=", 1)[1] for p in pairs if p.startswith("csrf_token=")), "")
    return cookie, csrf, call


def main() -> int:
    cookie, csrf, call = _login()
    before = LEDGER.read_text(encoding="utf-8").splitlines() if LEDGER.exists() else []
    n0 = len(before)
    used_before = set()
    for ln in before:
        try:
            o = json.loads(ln)
        except Exception:                                        # noqa: BLE001
            continue
        if o.get("company_id") == CID:
            used_before.add(o.get("version"))

    N = 10
    print("生成前：台账 %d 行；company_id=%s 已用版本号 %d 个（样例 %s）"
          % (n0, CID, len(used_before), sorted(used_before)[:3]))

    def one(i):
        return call("POST", f"/api/v1/projects/{PID}/reports",
                    {"view": "self_check", "formats": ["html"],
                     "change_note": "MQ2-D2 并发验收 #%d" % i},
                    cookie=cookie, csrf=csrf)

    with ThreadPoolExecutor(max_workers=N) as ex:
        res = list(ex.map(one, range(N)))

    ok = sum(1 for st, _, _ in res if st in (200, 201))
    print("并发 %d 路：HTTP 200/201 %d 个；状态=%s" % (N, ok, [st for st, _, _ in res]))
    if ok < N:
        for st, raw, _ in res:
            if st not in (200, 201):
                print("   失败样本 HTTP %s：%s" % (st, raw[:160]))

    after = LEDGER.read_text(encoding="utf-8").splitlines()
    added = []
    for ln in after[n0:]:
        try:
            o = json.loads(ln)
        except Exception:                                        # noqa: BLE001
            continue
        if o.get("company_id") == CID and str(o.get("change_note", "")).startswith("MQ2-D2 并发验收"):
            added.append(o)

    vers = [o.get("version") for o in added]
    dup = sorted({v for v in vers if vers.count(v) > 1})
    print("\n新增台账行：%d（应为 %d）" % (len(added), N))
    print("新增版本号：%s" % vers)
    print("新增版本号唯一性：%s" % ("✅ 无重复" if not dup else "❌ 重复 %s" % dup))
    if added:
        print("样例记录：doc_no=%s version=%s" % (added[0].get("doc_no"), added[0].get("version")))

    hist = [(o.get("doc_no"), o.get("version")) for o in
            (json.loads(x) for x in before if x.strip()) if o.get("company_id") == CID]
    from collections import Counter
    c = Counter(hist)
    hist_dup = {k: v for k, v in c.items() if v > 1}
    print("\n【修复前基线（历史，append-only 不追溯修改）】同(doc_no,version)重复 %d 组：%s"
          % (len(hist_dup), list(hist_dup.items())[:4]))

    good = (ok == N) and (len(added) == N) and (not dup)
    print("\n" + ("✅ MQ2-D2 验收通过：10 并发生成报告，新增版本号全部唯一"
                  if good else "❌ MQ2-D2 验收未通过"))
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
