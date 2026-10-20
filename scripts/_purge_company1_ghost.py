# -*- coding: utf-8 -*-
"""清理 company 1「幽灵账套」+ 同类孤儿主数据（2026-10-20，用户拍板）。

## 背景（事实，非推测）
company 1（深圳海更数字传媒有限公司，USCC 91440300MA5H824G7M）是 2026-10-17
数据事故**恢复时的宿主**，与 company 3（深圳市海更数字传媒有限公司，项目 44）
是**同一家企业**（同一 USCC —— 用户 10-19 重新建项目时重录，故 id 不同）。

它**仍在 `companies` 表**（所以官方「删除账套」端点可用），但：
  · **没有任何项目**（projects 表只剩 43/44，company 1 的 41/42/1 已不存在）；
  · 挂着 **8 份报告**，全部 `project_id` 指向**已不存在的项目**（41/42/1）；
  · 90 科目 / 10 部门 / 1 期间 / 1 董事 —— 与 company 3/4/5 **内容完全相同**
    （逐行签名一致 ⇒ 非独有事实，清了不丢内容）；
  · 939 条 audit_logs（该账套的历史运行留痕）；
  · `output/reports/1/` 下 **38 个报告交付物文件**；
  · `data/uploads/checkpoints/1.json`、`data/cache/last_analysis_cache['1']`。

另实测发现 **company 4 / 5 也是孤儿主数据**（各 90 科目 / 10 部门 / 1 期间，
无 `companies` 行）—— 与 company 1 同一类病（库重置时企业行消失、主数据残留）。

## 本次清理范围（用户指令：「这些未清，请一并清理」）
  A. **company 1 全链清理**：走官方唯一权威路径 ——
     `delete_company_cascade(1)` + `purge_company_analysis_artifacts(1,
     include_uploads=True, confirmed_deleted=True)`（⑬ 报告交付物目录已于本轮补入）.
     ★ 走官方路径而非自写 SQL：ORM `cascade="all, delete-orphan"` 会自动清
       accounts/departments/periods 等主数据；purge 清缓存/报告文件/原件/DB 行。
  B. **company 4 / 5 孤儿主数据清理**：仅清「主数据 + audit_logs」——
     它们是**纯残留**（无 companies 行 ⇒ 与 A 的"仍在库"不同），
     同样用 purge（`include_uploads=True, confirmed_deleted=True`）：
     因其不在库，在库护栏会放行；中心清理点覆盖 ⑬⑭。

## 明确**不碰**
  · company 2（中山市达冠纺织，项目 43）与 company 3（深圳市海更数字传媒，项目 44）
    —— 用户的**现存业务账套**，一字不动。
  · `report_versions.jsonl`（append-only 台账，铁律保留）。
  · company_id 为 0 / None / 99999 / 999999 的审计行 —— 它们不是"孤儿账套"，
    是**无归属留痕**（0=上传时未定项目、99999/999999=历史测试值），
    归 audit_trail 口径管，不在本次范围。

## 安全护栏
  G1 仅允许 id ∈ {1,4,5}（本次明确定义的清理目标），其余一律拒绝；
  G2 company 1 必须**无任何项目**（有项目 ⇒ 拒绝，防止误清活跃账套）；
  G3 company 1 的主数据必须**在别处有同签名副本**（清了不丢独有事实）；
  G4 目标必须在 `companies` 表之外（4/5）或在库且无项目（1）。
  G5 默认演练，`--apply` 才执行。

用法：
    ./.venv/Scripts/python.exe scripts/_purge_company1_ghost.py           # 演练
    ./.venv/Scripts/python.exe scripts/_purge_company1_ghost.py --apply   # 执行
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from runtime_storage import ACCOUNTING_DB, DATA_DIR              # noqa: E402

#: 本次清理目标（用户明确定义的"幽灵账套"）
TARGETS = (1, 4, 5)


def _sig(conn, cid):
    """科目签名（code+name）—— 用于判断主数据是否"别处已有"。"""
    conn.row_factory = sqlite3.Row
    return sorted((str(r["code"] or ""), str(r["name"] or ""))
                  for r in conn.execute(
                      "SELECT code, name FROM accounts WHERE company_id=?", (cid,)))


def _scan(conn):
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    alive = {int(r[0]) for r in cur.execute("SELECT id FROM companies").fetchall()}
    out = {}
    for cid in TARGETS:
        row = cur.execute("SELECT id,name,uscc FROM companies WHERE id=?", (cid,)).fetchone()
        in_db = row is not None
        projs = [dict(r) for r in cur.execute(
            "SELECT id,code,name FROM projects WHERE company_id=?", (cid,)).fetchall()]
        # 该 id 在各带 company_id 表里的行数
        tabs = [r[0] for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        rows_by_tab = {}
        for t in tabs:
            try:
                cols = [c[1] for c in cur.execute('PRAGMA table_info("%s")' % t).fetchall()]
                if "company_id" not in cols:
                    continue
                n = cur.execute('SELECT COUNT(*) FROM "%s" WHERE company_id=?' % t,
                                (cid,)).fetchone()[0]
                if n:
                    rows_by_tab[t] = int(n)
            except Exception:                                    # noqa: BLE001
                continue
        # 主数据"别处有副本"证据（以 accounts 签名比对）
        sig_here = _sig(conn, cid)
        sig_elsewhere = []
        for other in sorted(alive | {4, 5}):
            if other == cid:
                continue
            if _sig(conn, other) == sig_here and sig_here:
                sig_elsewhere.append(other)
        # 报告交付物目录文件数
        rep_dir = Path(DATA_DIR).parent / "output" / "reports" / str(cid)
        rep_files = (len([f for f in rep_dir.iterdir() if f.is_file()])
                     if rep_dir.is_dir() else 0)
        out[cid] = {
            "in_db": in_db, "name": (dict(row).get("name") if row else None),
            "uscc": (dict(row).get("uscc") if row else None),
            "projects": projs, "rows_by_tab": rows_by_tab,
            "accounts": len(sig_here), "sig_elsewhere": sig_elsewhere,
            "report_files": rep_files,
            "uploads_dir": (Path(DATA_DIR) / "uploads" / str(cid)).is_dir(),
            "checkpoint": (Path(DATA_DIR) / "uploads" / "checkpoints" / ("%d.json" % cid)).is_file(),
            "cache_key": str(cid),
        }
    return out, alive


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真正执行（默认只演练）")
    args = ap.parse_args()
    apply = bool(args.apply)

    print("=" * 74)
    print("清理 company 1 幽灵账套 + 孤儿主数据  模式=%s" % ("执行" if apply else "演练"))
    print("DATA_DIR =", DATA_DIR)
    print("=" * 74)

    conn = sqlite3.connect("file:%s?mode=ro" % Path(ACCOUNTING_DB).as_posix(), uri=True)
    try:
        info, alive = _scan(conn)
    finally:
        conn.close()

    print("\n【只读扫描】companies 在库: %r" % sorted(alive))
    for cid in TARGETS:
        d = info[cid]
        print("\n  ── company %d ──" % cid)
        print("     在 companies 表: %s   名称: %s" % (d["in_db"], d["name"]))
        print("     项目: %r" % d["projects"])
        print("     各表行数: %r" % d["rows_by_tab"])
        print("     科目签名 %d 行；别处同签名副本: %r" % (d["accounts"], d["sig_elsewhere"]))
        print("     output/reports/%d/ 文件: %d" % (cid, d["report_files"]))
        print("     uploads/%d/ 目录存在: %s；checkpoint: %s" % (cid, d["uploads_dir"], d["checkpoint"]))

    # ── 护栏 ─────────────────────────────────────────────────────────────
    print("\n【护栏核验】")
    bad = []
    for cid in TARGETS:
        d = info[cid]
        if d["in_db"] and d["projects"]:
            bad.append("G2 company %d 仍在库且有项目 ⇒ 疑似活跃账套，拒绝" % cid)
        if cid == 1 and not d["sig_elsewhere"]:
            bad.append("G3 company 1 主数据在别处无同签名副本 ⇒ 可能丢独有事实")
    print("   G1 目标集合={1,4,5} ................ ✓（脚本硬编码）")
    print("   G2 在库者必须无项目 ................ %s" % ("✓" if not any(
        "G2" in b for b in bad) else "✘"))
    print("   G3 company 1 主数据别处有副本 ...... %s" % ("✓" if not any(
        "G3" in b for b in bad) else "✘"))
    if bad:
        print("\n✘ 护栏未通过，拒绝执行：")
        for b in bad:
            print("   -", b)
        return 2

    if not apply:
        print("\n【将执行的动作（演练，未落地）】")
        print("   A. company 1：delete_company_cascade(1) + purge(...include_uploads=True)")
        print("      → 报告交付物 %d 个 / 主数据 %d 行 / 939 审计行 / 缓存 / checkpoint"
              % (info[1]["report_files"], sum(info[1]["rows_by_tab"].values())))
        for cid in (4, 5):
            print("   B. company %d：purge(...include_uploads=True)（不在库，纯残留 %d 行）"
                  % (cid, sum(info[cid]["rows_by_tab"].values())))
        print("\n（演练结束，未改动任何数据。加 --apply 执行）")
        return 0

    # ── 执行 ─────────────────────────────────────────────────────────────
    import main as M                                                # noqa: PLC0415
    from database import Company, SessionLocal                      # noqa: PLC0415
    from security import delete_company_cascade                     # noqa: PLC0415

    results = {}
    # A. company 1：仍在库 ⇒ 走官方端点同款路径（删 Company 行 → 级联 → purge）
    cid = 1
    db = SessionLocal()
    try:
        co = db.query(Company).filter(Company.id == cid).first()
        cname = co.name if co else ""
        if co is not None:
            db.delete(co)
            db.commit()
    finally:
        db.close()
    affected = delete_company_cascade(cid)
    out1 = M.purge_company_analysis_artifacts(cid, include_uploads=True,
                                              confirmed_deleted=True,
                                              company_name=cname)
    results[cid] = {"cascade_users": affected, "cleared": out1["cleared"],
                    "leftovers": out1["leftovers"]}

    # B. company 4/5：不在库 ⇒ 直接 purge（在库护栏放行）
    for cid in (4, 5):
        out = M.purge_company_analysis_artifacts(cid, include_uploads=True,
                                                 confirmed_deleted=True,
                                                 company_name="")
        results[cid] = {"cleared": out["cleared"], "leftovers": out["leftovers"]}

    print("\n【执行结果】")
    for cid in TARGETS:
        r = results[cid]
        print("   company %d: 清理 %d 项%s" % (cid, len(r["cleared"]), r["cleared"]))
        if r.get("leftovers"):
            print("      ✘ 残留: %r" % r["leftovers"])

    # 复扫自证
    conn2 = sqlite3.connect("file:%s?mode=ro" % Path(ACCOUNTING_DB).as_posix(), uri=True)
    try:
        info2, alive2 = _scan(conn2)
    finally:
        conn2.close()
    print("\n【复扫】companies 在库: %r" % sorted(alive2))
    for cid in TARGETS:
        d = info2[cid]
        print("   company %d: 在库=%s 项目=%d 各表行数=%r 报告文件=%d"
              % (cid, d["in_db"], len(d["projects"]), d["rows_by_tab"], d["report_files"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())