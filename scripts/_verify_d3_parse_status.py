# -*- coding: utf-8 -*-
"""MQ2-D3 端到端验收：**空内容不得判为 success**（三态验证）。

判据（结果级）：
  ① 非财税资料（`.txt`）解析 ⇒ `documents.parse_status = failed`
  ② 内容损坏的 `.xlsx`（0 行）解析 ⇒ `failed`
  ③ 正常财税资料（有数据行）解析 ⇒ `success`（**不得误伤**）

★ 证据同时取两处：`documents.parse_status` 与 `extracted_tables.parse_status`
  （二者脱节过就是历史缺陷，故都看）。

用法：python scripts/_verify_d3_parse_status.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

SIM = Path(r"C:\Users\Administrator\WorkBuddy\2026-08-04-21-37-33\_scenario_sim\data")
DB = SIM / "accounting.db"
BASE = "http://127.0.0.1:8023"


def _client():
    jar = {}

    def call(method, path, body=None, timeout=180):
        headers = {}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if jar:
            headers["Cookie"] = "; ".join("%s=%s" % kv for kv in jar.items())
        if jar.get("csrf_token"):
            headers["X-CSRF-Token"] = jar["csrf_token"]
        req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with op.open(req, timeout=timeout) as r:
                raw = r.read().decode("utf-8", "replace")
                for c in (r.headers.get_all("Set-Cookie") or []):
                    kv = c.split(";")[0]
                    k, v = kv.split("=", 1)
                    jar[k.strip()] = v.strip()
                return r.status, raw
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")

    return call


def _find_docs() -> dict:
    """挑样本：★ 必须**物理文件存在**且**当前用户可见**（属 pid=10），否则解析会 404，
    导致"没真跑解析"的弱证据（第一版就这么栽过，已修正）。"""
    c = sqlite3.connect(str(DB))
    out = {}
    picks = {
        "txt": "select id, original_name, parse_status from documents "
               "where project_id=10 and original_name like '%.txt%' order by id limit 1",
        "broken": "select id, original_name, parse_status from documents "
                  "where project_id=10 and original_name like '%伪装%' order by id limit 1",
        "ok": "select id, original_name, parse_status from documents "
              "where project_id=10 and original_name like '%科目余额表%' "
              "and parse_status='success' order by id limit 1",
    }
    for tag, q in picks.items():
        row = c.execute(q).fetchone()
        if row:
            out[tag] = {"id": row[0], "name": row[1], "status_before": row[2]}
    c.close()
    return out


def _status(doc_id: int) -> dict:
    c = sqlite3.connect(str(DB))
    d = c.execute("select parse_status from documents where id=?", (doc_id,)).fetchone()
    t = c.execute("select parse_status, count(*), ifnull(sum(row_count),0) from extracted_tables "
                  "where document_id=? group by parse_status", (doc_id,)).fetchall()
    c.close()
    return {"documents": d[0] if d else None, "tables": [list(x) for x in t]}


def main() -> int:
    call = _client()
    st, raw = call("POST", "/api/auth/login",
                   {"username": "sim_finance", "password": "MetaQ2-Sim-2026!"})
    assert st == 200, (st, raw[:200])

    docs = _find_docs()
    print("待验资料：", json.dumps(docs, ensure_ascii=False, indent=1))
    expect = {"txt": "failed", "broken": "failed", "ok": "success"}
    results = []

    for tag, d in docs.items():
        did = d["id"]
        before = _status(did)
        st, raw = call("POST", f"/api/v1/documents/{did}/extract", {})
        after = _status(did)
        body = {}
        try:
            body = json.loads(raw)
        except Exception:                                        # noqa: BLE001
            pass
        got = after["documents"]
        ok = (got == expect[tag])
        results.append((tag, d["name"], before["documents"], got, expect[tag], ok,
                        body.get("parse_error") or ""))
        print("\n[%s] id=%s %s" % (tag, did, d["name"]))
        print("     解析 HTTP=%s；状态 %s → %s（期望 %s）%s"
              % (st, before["documents"], got, expect[tag], "✅" if ok else "❌"))
        print("     extracted_tables 状态分布=%s" % after["tables"])
        if body.get("parse_error"):
            print("     解析说明=%s" % str(body["parse_error"])[:140])

    good = all(r[5] for r in results)
    print("\n" + ("✅ MQ2-D3 验收通过：空内容=failed、损坏=failed、正常=success"
                  if good else "❌ MQ2-D3 验收未通过"))
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main())
