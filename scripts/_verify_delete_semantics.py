# -*- coding: utf-8 -*-
"""删除语义端到端验证（非破坏版）：真实调用 8001 接口。

安全约定：**绝不删除用户的真实资料**。删除类验证只用本脚本自造的合成文件
（doc_id ≥ 900000），真实文件（doc_id < 900000）只读不删。

验证项：
  C. 强制重算 —— force=1 绕过增量复用；报告带 _freshness（计算时间/指纹/依据资料）
  B. 真实删除 —— 合成文件是否真从磁盘消失、列表是否清空、返回是否如实
  D. 删除报告 —— 六处副本是否都清、是否回读校验、是否返回残留清单

用法：
    python scripts/_verify_delete_semantics.py            # 默认只跑 C（安全）
    python scripts/_verify_delete_semantics.py --full     # 追加 B/D（会造合成文件）
"""
import json, os, sys, time, urllib.request, urllib.error, http.cookiejar

B = "http://127.0.0.1:8001"
CJ = http.cookiejar.CookieJar()
OP = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CJ))
CS = ""
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CID = 1
SYNTH_FLOOR = 900000     # 合成文件 doc_id 下界：>= 该值才允许删除


def req(m, p, b=None, t=900):
    r = urllib.request.Request(B + p, data=json.dumps(b).encode() if b is not None else None, method=m)
    r.add_header("Content-Type", "application/json")
    r.add_header("User-Agent", "wb/1.0")
    if CS:
        r.add_header("X-CSRF-Token", CS)
    try:
        with OP.open(r, timeout=t) as x:
            return x.status, json.loads(x.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:500]


def disk_files(cid):
    d = os.path.join(ROOT, "data", "uploads", str(cid))
    return sorted(os.listdir(d)) if os.path.isdir(d) else []


st, js = req("POST", "/api/auth/login", {"username": "admin", "password": "Admin@2024caishui"})
CS = next((c.value for c in CJ if c.name == "csrf_token"), "")
print("① 登录:", js.get("ok"))


def step_c():
    print("\n" + "=" * 72)
    print("C. 强制重算：force=1 必须真跑，且报告携带新鲜度标识")
    print("=" * 72)
    st, a = req("POST", f"/api/tax-risk-docs/analyze-start?company_id={CID}", {})
    print("  第1次(不带force) :", json.dumps(a, ensure_ascii=False)[:200])
    tid = a.get("task_id")
    for _ in range(300):
        st, stt = req("GET", "/api/tax-risk-docs/analyze-status/" + str(tid))
        if stt.get("status") in ("done", "error"):
            break
        time.sleep(2)
    print("  第1次结束:", stt.get("status"))
    if stt.get("status") == "error":
        st, er = req("GET", "/api/tax-risk-docs/analyze-result/" + str(tid))
        print("  失败原因:", json.dumps(er, ensure_ascii=False)[:300])
        return

    st, b = req("POST", f"/api/tax-risk-docs/analyze-start?company_id={CID}", {})
    print("  第2次(不带force) :", json.dumps(b, ensure_ascii=False)[:240])
    print("     → 增量复用命中:" , bool(b.get("incremental")),
          "| 说明:", b.get("message"))
    if b.get("result_computed_at"):
        print("     → 明确告知复用的是:", str(b["result_computed_at"])[:19], "的结果")

    st, c = req("POST", f"/api/tax-risk-docs/analyze-start?company_id={CID}&force=1", {})
    print("  第3次(force=1)   :", json.dumps(c, ensure_ascii=False)[:240])
    print("     → force 绕过增量复用:", not bool(c.get("incremental")))
    tid2 = c.get("task_id")
    for _ in range(400):
        st, stt2 = req("GET", "/api/tax-risk-docs/analyze-status/" + str(tid2))
        if stt2.get("status") in ("done", "error"):
            break
        time.sleep(2)
    print("  第3次结束:", stt2.get("status"), stt2.get("progress"))
    st, raw = req("GET", "/api/tax-risk-docs/analyze-result/" + str(tid2))
    rep = (raw or {}).get("report") or {}
    fr = rep.get("_freshness") or {}
    print("  ✓ report._freshness =", json.dumps(fr, ensure_ascii=False)[:420])
    print("  ✓ overall_level =", rep.get("overall_level"),
          "| files_count =", rep.get("files_count"),
          "| findings =", len(rep.get("all_findings") or []))


def step_bd():
    print("\n" + "=" * 72)
    print("B. 真实删除（仅限本脚本自造的合成文件 doc_id ≥ %d）" % SYNTH_FLOOR)
    print("=" * 72)
    tdir = os.path.join(ROOT, "data", "uploads", str(CID))
    os.makedirs(tdir, exist_ok=True)
    # ★ 合成文件必须**在服务启动前**由外部创建（扫描只在进程启动时执行一次）。
    #   本函数绝不自己造文件——否则会出现"造了文件却不在列表里"的假失败。
    made = [f for f in sorted(os.listdir(tdir)) if f"{CID}_9" in f]
    print("  预期合成文件（须由外部在启动服务前创建）:", made)
    if not made:
        print("  未发现合成文件。正确用法：")
        print("    ① 在 data/uploads/1/ 造 1_900001_*.xlsx / 1_900002_*.xlsx")
        print("    ② 重启服务  ③ 再跑本脚本 --full")
        return

    st, lst = req("GET", f"/api/tax-risk-docs/list?company_id={CID}")
    lst = lst if isinstance(lst, list) else []
    real = [d for d in lst if int(d.get("id") or 0) < SYNTH_FLOOR]
    synth = [d for d in lst if int(d.get("id") or 0) >= SYNTH_FLOOR]
    print("  列表: 真实 %d 条 / 合成 %d 条" % (len(real), len(synth)))
    print("  ⚠ 真实资料受保护，不参与删除:", [d.get("original_name") for d in real])

    if not synth:
        print("  合成文件未进列表（服务未在文件创建后重启，或被墓碑挡住），跳过 B")
        _cleanup_synth(made)
        return
    ids = [d["id"] for d in synth]
    before = disk_files(CID)
    st, res = req("POST", "/api/tax-risk-docs/batch-delete", {"company_id": CID, "doc_ids": ids})
    print("  HTTP", st, "→", json.dumps(res, ensure_ascii=False)[:500])
    after = disk_files(CID)
    print("  磁盘真实消失:", len([f for f in before if f not in after]), "/", len(made))
    st, lst2 = req("GET", f"/api/tax-risk-docs/list?company_id={CID}")
    print("  删除后列表:", len(lst2) if isinstance(lst2, list) else lst2,
          "（应等于真实资料数", len(real), "）")
    _cleanup_synth(made)

    print("\n" + "=" * 72)
    print("D. 删除报告：六处副本是否全清")
    print("=" * 72)
    st, dr = req("DELETE", f"/api/tax-risk-docs/report?company_id={CID}")
    print("  HTTP", st, "→", json.dumps(dr, ensure_ascii=False)[:700])
    st, la = req("GET", f"/api/tax-risk-docs/last-analysis?company_id={CID}")
    print("  last-analysis（应为暂无）:", json.dumps(la, ensure_ascii=False)[:120])
    st, h = req("GET", f"/api/pipeline/history?company_id={CID}")
    print("  分析历史条数:", h.get("count") if isinstance(h, dict) else h)
    cp = os.path.join(ROOT, "data", "uploads", "checkpoints", f"{CID}.json")
    print("  检查点文件存在:", os.path.exists(cp))
    tr = os.path.join(ROOT, "data", "uploads", "transfer")
    print("  中转站该公司明细:",
          len([f for f in os.listdir(tr) if f.startswith(f"{CID}_")]) if os.path.isdir(tr) else 0)
    try:
        with open(os.path.join(ROOT, "data", "cache", "last_analysis_cache.json"),
                  "r", encoding="utf-8") as f:
            dc = json.load(f)
        print("  磁盘缓存仍含该公司:", str(CID) in dc)
    except Exception as e:
        print("  磁盘缓存读取异常:", e)
    tb = os.path.join(ROOT, "data", "deleted_docs.json")
    print("  已登记墓碑:",
          len(json.load(open(tb, encoding="utf-8"))) if os.path.exists(tb) else 0)


def _cleanup_synth(made):
    """清掉本脚本自造的合成文件与其墓碑，绝不留残留（也不碰真实资料）。

    注意：必须自己保证 ROOT 在 sys.path 上——本脚本可能以任意 cwd 执行，
    否则 `import runtime_storage` 会 ImportError，墓碑清不掉，下次再跑
    脚本时自造的文件会被墓碑挡住而"看不到"，误判为产品缺陷。
    """
    try:
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)
        from runtime_storage import clear_doc_tombstone
        tdir = os.path.join(ROOT, "data", "uploads", str(CID))
        trash = os.path.join(ROOT, "data", "trash")
        dids = [n.split("_")[1] for n in made if len(n.split("_")) > 1]
        for name in made:
            clear_doc_tombstone(CID, name)
            for base in (tdir, trash):
                p = os.path.join(base, name)
                if os.path.isfile(p):
                    os.remove(p)
        # 回收站里可能因改名产生 名字.1.xlsx / 名字.1.1.xlsx 等副本
        for f in (os.listdir(trash) if os.path.isdir(trash) else []):
            if any(d in f for d in dids):
                try:
                    os.remove(os.path.join(trash, f))
                except OSError:
                    pass
        # 清理后复核，避免"以为清了其实没清"
        left_tomb = [k for k in _load_tomb_keys() if any(d in k for d in dids)]
        left_file = [f for f in (os.listdir(tdir) if os.path.isdir(tdir) else [])
                     if any(d in f for d in dids)]
        print("  [清理] 合成文件/墓碑残留:",
              "无" if not left_tomb and not left_file else (left_tomb, left_file))
    except Exception as exc:
        print("  [清理] 合成残留清理异常:", exc)


def _load_tomb_keys():
    try:
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)
        from runtime_storage import load_doc_tombstones
        return list(load_doc_tombstones().keys())
    except Exception:
        return []


if __name__ == "__main__":
    step_c()
    if "--full" in sys.argv:
        step_bd()
    print("\n完成。")
