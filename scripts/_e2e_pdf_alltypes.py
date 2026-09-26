# -*- coding: utf-8 -*-
"""端到端全类型 PDF 验收：一次上传 8 种不同内容的 PDF，验证「不管什么内容都能识别并归入对应集合」。"""
import os, sys, json, sqlite3, glob
os.environ["APP_COOKIE_SECURE"] = "0"
os.environ["APP_ALLOWED_ORIGINS"] = "http://127.0.0.1:8001"
BASE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(BASE)
sys.path.insert(0, PROJECT); sys.path.insert(0, BASE)

TEST_CID = 9996
CO_NAME = "测试全类型PDF识别企业"
PD = os.path.join(PROJECT, "data/_pdftest")


def setup_company():
    c = sqlite3.connect(os.path.join(PROJECT, "data", "accounting.db"))
    c.execute("DELETE FROM companies WHERE id=?", (TEST_CID,))
    c.execute(
        "INSERT INTO companies(id,name,uscc,registered_capital,established_date,"
        "legal_representative,legal_representative_id,address,business_scope,"
        "company_type,industry_code,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (TEST_CID, CO_NAME, "91440300MA5H824G7M", "5000000", "2018-03-15",
         "张晓冬", "440300199001010011", "深圳市龙岗区坂田街道", "其他综合零售",
         "有限责任公司", "52", "2026-01-01"))
    c.commit(); c.close()


def main():
    setup_company()
    # 收集测试用 PDF
    picks = []
    for pat, label in (
        ("*进项发票列表.pdf", "进项发票"),
        ("*销项发票列表.pdf", "销项发票"),
        ("*工资表.pdf", "工资表"),
        ("*社保明细*.pdf", "社保明细"),
        ("*凭证.pdf", "凭证"),
        ("*科目余额.pdf", "科目余额"),
        ("*会议纪要.pdf", "无关内容"),
    ):
        got = glob.glob(os.path.join(PD, pat))
        if got:
            picks.append((label, got[0]))
    # 增值税申报表 PDF（真实，2025-01 / 2025-09）
    for t in ("1_295_", "1_303_"):
        g = glob.glob(os.path.join(PROJECT, "data/trash/%s*.pdf" % t))
        if g:
            picks.append(("增值税申报表", g[0]))
    # 银行对账单 PDF（真实，招行）
    g = glob.glob(os.path.join(PROJECT, "data/uploads/1/1_488_*.pdf"))
    if g:
        picks.append(("银行对账单", g[0]))

    print("准备上传 %d 个 PDF：" % len(picks))
    for lb, p in picks:
        print("   [%s] %s" % (lb, os.path.basename(p)))

    from fastapi.testclient import TestClient
    import main as appmod
    client = TestClient(appmod.app)
    lr = client.post("/api/auth/login", json={"username": "admin", "password": "Admin@2024caishui"})
    if not lr.json().get("ok"):
        print("登录失败"); return
    hdr = {"X-CSRF-Token": client.cookies.get("csrf_token", "")}

    files = []
    for lb, p in picks:
        files.append(("files", (os.path.basename(p), open(p, "rb").read(), "application/pdf")))
    r = client.post(f"/api/tax-risk-docs/upload?company_id={TEST_CID}", files=files, headers=hdr)
    up = r.json()
    print("\n[upload]", r.status_code, "上传", len(up.get("uploaded", [])), "跳过", up.get("skipped"), "拒绝", up.get("rejected"))

    r = client.post(f"/api/tax-risk-docs/analyze?company_id={TEST_CID}", headers=hdr)
    body = r.json()
    print("[analyze]", r.status_code, "ok =", body.get("ok"))
    if not body.get("ok"):
        print("  失败:", str(body.get("message"))[:300])
        print("  明细:", str(body.get("detail"))[:400])
        for x in body.get("file_results") or []:
            print("   ", x.get("file"), "->", x.get("type"), (x.get("actions") or [])[:1])
        return

    rep = body["report"]
    print("\n========== 每个 PDF 的识别结果 ==========")
    for x in rep.get("file_results") or []:
        print("  %-52s type=%-18s %s" % (
            str(x.get("file"))[:52], x.get("type"),
            " / ".join(str(a) for a in (x.get("actions") or [])[:1])[:60]))

    print("\n========== 数据集合是否收到数据 ==========")
    st = rep.get("stats") or {}
    print("  stats =", json.dumps(st, ensure_ascii=False)[:400])

    print("\n========== 判定 ==========")
    fr = rep.get("file_results") or []
    from collections import Counter
    dist = Counter((x.get("type") or "?") for x in fr)
    print("  类型分布 =", dict(dist))
    unknown = dist.get("unknown", 0)
    print("  未识别(unknown) 文件数 =", unknown)
    print("  >>", "✓ 全部 PDF 均被识别（无 unknown）" if unknown == 0 else "✗ 仍有 %d 个未识别" % unknown)


if __name__ == "__main__":
    main()
