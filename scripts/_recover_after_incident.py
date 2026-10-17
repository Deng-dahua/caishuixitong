# -*- coding: utf-8 -*-
"""2026-10-17 数据事故的恢复脚本（一次性工具）。

事故经过
--------
`engine/backup.restore_backup` 首版用模块级常量 `SECURITY_DB.parent` 拼恢复目标，
而该常量在 import 时就固化为**真实 data/**。测试里 monkeypatch 了 `DATA_DIR` 却
不影响它 ⇒ 跑一次测试就把生产 `data/accounting.db`（6.3 MB）与 `data/security.db`
覆盖成了 12 KB 的测试库。事后把规则改成「目标一律由 DATA_DIR 派生 + `_assert_inside`
硬护栏」（见 engine/backup.py）。

本脚本做**尽量完整**的抢救（按可靠性从高到低）
  ① 现场留证：把损坏文件**字节级复制**到 `data/_incident_20261017/`（不删、不改）；
  ② 隔离区取回：`_scenario_sim/data/accounting.db` 里保存着**公司 1 的真实主数据**
     （深圳海更数字传媒有限公司 / 91440300MA5H824G7M / 378 个科目 / 50 个部门 /
     5 个期间 / 3 条行业基准），用 `VACUUM INTO` 生成干净快照作为新库；
  ③ 清理测试残留：删掉公司 2（元质量模拟测试有限公司）与两个模拟项目；
  ④ 重登记原件：`data/uploads/1` 下 **102 个原件完好**，按文件名重新登记为
     company 1 的 documents（doc_type 留 `other`、`parse_status=pending`，
     **不猜分类** —— 让用户用界面的「重新分类/重新解析」跑一遍）；
  ⑤ 重建安全库：`init_security_db()` + 用环境变量口令引导一个管理员。

**不可恢复**（如实记录）
  · 原 `audit_logs`（1913 条运行日志）—— 审计留痕丢失；
  · 原 `documents` 行及其 `extracted_tables/fields`（只有隔离区那 22 份的抽取结果）；
  · 原 `reports` 版本记录（隔离区保留 5 条，其余丢失）。

用法
    python scripts/_recover_after_incident.py            # 演练，只打印计划
    python scripts/_recover_after_incident.py --apply    # 真正执行
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from runtime_storage import (ACCOUNTING_DB, DATA_DIR, SECURITY_DB,
                             now_cst, purge_file)

SIM_DB = ROOT.parent / "_scenario_sim" / "data" / "accounting.db"
EVIDENCE = DATA_DIR / "_incident_20261017"
UPLOADS_1 = DATA_DIR / "uploads" / "1"

#: 事故中受影响的文件（含 SQLite 边车）
AFFECTED = ("accounting.db", "accounting.db-wal", "accounting.db-shm", "security.db")

#: 隔离区里属于「模拟测试」的实体（按 USCC / 名称识别，不按 id 猜）
TEST_COMPANY_USCC = "91440300MA5SIMQ2X1"
TEST_PROJECT_CODES = ("PJ-20261016-0001", "PJ-20261017-0001")


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _md5(p: Path) -> str:
    h = hashlib.md5()                       # noqa: S324 - 与既有 documents.md5 口径一致
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def step1_evidence(apply: bool) -> list:
    done = []
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    for name in AFFECTED:
        src = DATA_DIR / name
        if not src.exists():
            continue
        dst = EVIDENCE / name
        if apply:
            shutil.copy2(src, dst)
        done.append("%s (%d bytes) → %s" % (name, src.stat().st_size, dst.name))
    return done


def step2_restore_from_sim(apply: bool) -> str:
    if not SIM_DB.is_file():
        raise SystemExit("隔离区库不存在：%s" % SIM_DB)
    for name in AFFECTED:
        p = DATA_DIR / name
        if p.exists() and apply:
            ok, why = purge_file(p)          # 损坏文件进回收站（可恢复），不物理删
            if not ok:
                raise SystemExit("无法移走损坏文件 %s：%s" % (p, why))
    if apply:
        con = sqlite3.connect(str(SIM_DB), timeout=30)
        try:
            con.execute("VACUUM INTO ?", (str(ACCOUNTING_DB),))
        finally:
            con.close()
    return "从隔离区快照恢复 → %s" % ACCOUNTING_DB


def step3_clean_test_data(apply: bool) -> list:
    # 演练模式下生产库还是**损坏的**（第②步没执行）⇒ 改为读隔离区库来出计划
    con = sqlite3.connect(str(ACCOUNTING_DB if apply else SIM_DB), timeout=30)
    log = []
    try:
        tabs = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        cur = con.execute("SELECT id,name,uscc FROM companies WHERE uscc=?", (TEST_COMPANY_USCC,))
        bad = cur.fetchall()
        for cid, name, uscc in bad:
            log.append("删除测试公司 %s(%s) %s" % (cid, uscc, name))
            if not apply:
                continue
            doc_ids = [r[0] for r in con.execute(
                "SELECT id FROM documents WHERE company_id=?", (cid,))]
            for t in ("extracted_tables", "extracted_fields", "document_pages", "extract_issues"):
                if t in tabs and doc_ids:
                    con.execute("DELETE FROM %s WHERE document_id IN (%s)"
                                % (t, ",".join("?" * len(doc_ids))), doc_ids)
            for t in ("documents", "reports", "project_members"):
                if t in tabs:
                    con.execute("DELETE FROM %s WHERE %s" % (
                        t, "company_id=?" if t != "project_members" else "project_id IN "
                        "(SELECT id FROM projects WHERE taxpayer_id=?)"), (cid if t != "project_members" else uscc,))
            con.execute("DELETE FROM companies WHERE id=?", (cid,))

        for code in TEST_PROJECT_CODES:
            row = con.execute("SELECT id,name FROM projects WHERE code=?", (code,)).fetchone()
            if not row:
                continue
            pid, pname = row
            log.append("删除模拟项目 %s(%s) %s" % (pid, code, pname))
            if not apply:
                continue
            doc_ids = [r[0] for r in con.execute(
                "SELECT id FROM documents WHERE project_id=?", (pid,))]
            for t in ("extracted_tables", "extracted_fields", "document_pages", "extract_issues"):
                if t in tabs and doc_ids:
                    con.execute("DELETE FROM %s WHERE document_id IN (%s)"
                                % (t, ",".join("?" * len(doc_ids))), doc_ids)
            for t in ("documents", "project_members"):
                if t in tabs:
                    con.execute("DELETE FROM %s WHERE project_id=?" % t, (pid,))
            con.execute("DELETE FROM projects WHERE id=?", (pid,))
        if apply:
            con.commit()
    finally:
        con.close()
    return log


def step4_reregister_uploads(apply: bool) -> dict:
    """把 uploads/1 下**尚未登记**的原件补登记为 documents（不猜分类、不解析）。"""
    con = sqlite3.connect(str(ACCOUNTING_DB if apply else SIM_DB), timeout=30)
    con.row_factory = sqlite3.Row
    added, skipped = [], 0
    try:
        tabs = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "documents" not in tabs:
            raise SystemExit("恢复后的库没有 documents 表")
        known = {str(r[0]) for r in con.execute("SELECT filename FROM documents")}
        max_doc = con.execute("SELECT COALESCE(MAX(doc_id),0) FROM documents").fetchone()[0]
        company_id = con.execute("SELECT id FROM companies ORDER BY id LIMIT 1").fetchone()
        if not company_id:
            raise SystemExit("恢复后的库没有任何公司，无法登记原件")
        company_id = int(company_id[0])
        files = sorted(p for p in UPLOADS_1.iterdir() if p.is_file())
        for i, f in enumerate(files, 1):
            if f.name in known:
                skipped += 1
                continue
            max_doc += 1
            added.append(f.name)
            if not apply:
                continue
            con.execute(
                "INSERT INTO documents (project_id, company_id, doc_id, filename, original_name,"
                " ext, size, md5, sha256, doc_type, category, classify_by, parse_status,"
                " page_count, storage_path, uploaded_by, uploaded_at, updated_at, note)"
                " VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (company_id, max_doc, f.name, f.name, f.suffix.lower(), f.stat().st_size,
                 _md5(f), _sha256(f), "other", "other", "recovery-unclassified", "pending",
                 0, str(f), "incident-recovery", now_cst(), now_cst(),
                 "2026-10-17 事故恢复：仅登记文件（未分类、未解析），请在界面重新分类/重新解析"))
        if apply:
            con.commit()
    finally:
        con.close()
    return {"added": added, "skipped": skipped}


def step5_rebuild_security(apply: bool) -> str:
    if not apply:
        return "重建安全库（init_security_db + 引导管理员 %s）" % os.environ.get(
            "APP_ADMIN_USERNAME", "(未设置)")
    import security                       # noqa: PLC0415

    security.init_security_db()
    security._bootstrap_admin_from_environment()
    con = sqlite3.connect(str(SECURITY_DB))
    try:
        n = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        con.close()
    return "安全库已重建，用户数 %d" % n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真正执行（默认只演练）")
    args = ap.parse_args()
    apply = bool(args.apply)

    print("=" * 72)
    print("2026-10-17 数据事故恢复  模式=%s" % ("执行" if apply else "演练"))
    print("DATA_DIR =", DATA_DIR)
    print("=" * 72)

    print("\n① 现场留证")
    for line in step1_evidence(apply):
        print("   ", line)

    print("\n② 从隔离区快照恢复业务库")
    print("   ", step2_restore_from_sim(apply))

    print("\n③ 清理模拟测试残留")
    for line in step3_clean_test_data(apply):
        print("   ", line)

    print("\n④ 重新登记 uploads/1 原件")
    r = step4_reregister_uploads(apply)
    print("    待登记 %d 个，已存在跳过 %d 个" % (len(r["added"]), r["skipped"]))
    for name in r["added"][:5]:
        print("      +", name)
    if len(r["added"]) > 5:
        print("      … 其余 %d 个" % (len(r["added"]) - 5))

    print("\n⑤ 重建安全库")
    print("   ", step5_rebuild_security(apply))

    if apply:
        con = sqlite3.connect(str(ACCOUNTING_DB))
        try:
            for t in ("companies", "documents", "projects", "accounts", "departments", "reports"):
                try:
                    n = con.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
                    print("    %-14s %d" % (t, n))
                except sqlite3.Error:
                    pass
        finally:
            con.close()
    print("\n完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
