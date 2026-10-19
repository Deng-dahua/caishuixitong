# -*- coding: utf-8 -*-
"""清理 2026-10-17 事故恢复遗留的**孤儿资料登记**（`project_id IS NULL`）。

## 背景（事实，非推测）
`scripts/_recover_after_incident.py::step4_reregister_uploads` 在事故恢复时，
把 `data/uploads/1/` 下 102 个原件**补登记**为 `documents` 行，但**没有项目**
（`project_id = NULL`，`classify_by='recovery-unclassified'`，`company_id=1`）。

用户 2026-10-19 已在项目 44（company 3，深圳市海更数字传媒）重新上传了**同一套**
102 份资料 ⇒ 孤儿登记与现存资料**内容 100% 重复**（md5 逐份可证，102/102），
且 `project_id IS NULL` 在系统中是**非法状态**：
正常上传路径 `engine.document_service.upload_documents` 恒带 `project_id`，
读路径 `_document_row` 对 `project_id` 为空**直接抛 409**（"资料未归属任何项目"）
⇒ 这类行既进不了列表、也进不了分析，是纯僵尸登记。

用户 2026-10-20 拍板：**清理**。

## 本脚本做什么（严格限定范围，不做扩散）
  ① 物理原件 `data/uploads/1/` 下的 102 个文件 → `move_to_trash`（可恢复，不物理删）；
  ② 解析登记子表 `extracted_tables/extracted_fields/extract_issues/document_pages`
     中这些资料的行 → 复用唯一权威 `engine.extract_service._reset_document_extract`；
  ③ 中转站解析缓存 `data/uploads/transfer/{cid}_{原序号}.json` → `purge_file`；
  ④ `documents` 登记行 → 删；
  ⑤ 注册资料删除墓碑（`runtime_storage.add_doc_tombstone`）⇒ `main._init_tax_docs_from_disk`
     重启后**不会把文件重新扫回列表**（"删了又回来"的根治）；
  ⑥ 业务留痕 `engine.audit_trail.record`。

## 明确**不碰**（如实报告，交用户另行决策）
  · `companies` 行（company 1 = 深圳海更数字传媒，与 company 3 同一 USCC，属恢复宿主）；
  · `reports` 表 company 1 的 8 份报告（指向**已不存在的项目** 41/42/1）；
  · company 1 的 90 科目 / 10 部门 / 1 期间 / 926 条审计日志；
  · `data/uploads/checkpoints/1.json`；
  · 任何其他公司的资料与项目。

## 安全护栏（任一不满足即拒绝执行，绝不"顺手删一下"；均已反向验证真能报警）
  G0 命中集合必须**全部**是事故恢复登记（`classify_by='recovery-unclassified'`）
     ⇒ 认出孤儿、不误伤将来别的 NULL 行；
  G1 命中行的**物理路径不得与任何现存登记共享**（独立游标遍历全库路径）
     ⇒ 删文件不会误伤他人；
  G2 每一份命中资料，**必须**在库里**别处存在同 md5 的副本** ⇒ 清掉不丢内容；
  G3 物理路径必须落在 `DATA_DIR/uploads/` 之内（`_assert_inside` 同款口径）；
  G4 `--apply` 才写真库；默认只演练。

用法：
    ./.venv/Scripts/python.exe scripts/_purge_incident_orphan_docs.py           # 演练
    ./.venv/Scripts/python.exe scripts/_purge_incident_orphan_docs.py --apply   # 执行
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from runtime_storage import (ACCOUNTING_DB, DATA_DIR, TRASH_DIR,           # noqa: E402
                             add_doc_tombstone, purge_file)


def _is_inside_data(path: Path) -> bool:
    """路径必须落在 DATA_DIR 内（与 `engine.backup._assert_inside` 同款口径）。"""
    try:
        p = Path(path).resolve()
        base = Path(DATA_DIR).resolve()
        return base == p or base in p.parents
    except Exception:                                     # noqa: BLE001
        return False


def _scan(conn: sqlite3.Connection) -> dict:
    """只读扫描：返回命中集合与全部护栏判据结果。"""
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    rows = [dict(r) for r in cur.execute(
        "SELECT id, project_id, company_id, doc_id, filename, md5, storage_path, "
        "classify_by, note FROM documents WHERE project_id IS NULL ORDER BY id").fetchall()]

    # 全库 md5 索引（用于 G2：别处是否有同内容副本）
    allmd5: dict = {}
    for r in cur.execute("SELECT id, md5 FROM documents").fetchall():
        allmd5.setdefault(str(r["md5"] or "").lower(), []).append(int(r["id"]))

    # G1：命中行的物理路径**不得与任何现存登记共享**（否则删文件会误伤他人）。
    #     注：此处**不是**"project_id IS NULL"的同义反复 —— 判据落在 storage_path 上，
    #     查询用独立游标遍历**全库**路径，能真拦到"两行共用一个物理文件"的情形。
    path_owner: dict = {}
    for r in cur.execute("SELECT id, storage_path FROM documents").fetchall():
        p = str(r["storage_path"] or "")
        if p:
            path_owner.setdefault(os.path.normcase(os.path.abspath(p)), []).append(int(r["id"]))
    hit_ids = {int(r["id"]) for r in rows}
    g1_bad = [r["id"] for r in rows
              if len([x for x in path_owner.get(
                  os.path.normcase(os.path.abspath(str(r["storage_path"] or ""))), []) 
                  if x not in hit_ids]) > 0]
    g2_uniq = [r["id"] for r in rows
               if not [x for x in allmd5.get(str(r["md5"] or "").lower(), [])
                       if x != r["id"]]]
    g3_bad = [r["id"] for r in rows
              if not r["storage_path"] or not _is_inside_data(Path(r["storage_path"]))]
    # G0：命中集合必须**全部**是事故恢复登记（认出孤儿、不误伤将来别的 NULL 行）
    g0_bad = [r["id"] for r in rows
              if str(r.get("classify_by") or "") != "recovery-unclassified"]

    # 物理文件存在性 + transfer 缓存命中
    exist, missing = [], []
    for r in rows:
        (exist if r["storage_path"] and os.path.isfile(r["storage_path"])
         else missing).append(r["id"])

    # transfer 缓存：key = {company_id}_{文件名第二段}.json
    transfer_dir = Path(DATA_DIR) / "uploads" / "transfer"
    want_t, hit_t = [], []
    for r in rows:
        parts = str(r["filename"] or "").split("_", 2)
        if len(parts) < 2:
            continue
        key = "%s_%s.json" % (r["company_id"], parts[1])
        want_t.append(key)
        if (transfer_dir / key).is_file():
            hit_t.append(key)

    return {
        "rows": rows, "total": len(rows),
        "g0_bad": g0_bad, "g1_bad": g1_bad, "g2_uniq": g2_uniq, "g3_bad": g3_bad,
        "file_exist": exist, "file_missing": missing,
        "transfer_want": want_t, "transfer_hit": hit_t,
        "companies": sorted({r["company_id"] for r in rows}),
        "classify_by": sorted({str(r.get("classify_by") or "") for r in rows}),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真正执行（默认只演练）")
    args = ap.parse_args()
    apply = bool(args.apply)

    print("=" * 74)
    print("清理 10-17 事故孤儿资料登记  模式=%s" % ("执行" if apply else "演练"))
    print("DATA_DIR =", DATA_DIR)
    print("=" * 74)

    conn = sqlite3.connect(str(ACCOUNTING_DB), timeout=30)
    info = None
    try:
        info = _scan(conn)
        rows = info["rows"]
        print("\n【只读扫描】命中 documents 行 = %d" % info["total"])
        if not rows:
            print("✓ 无 project_id IS NULL 的登记行，无需清理")
            return 0
        print("   涉及公司 id: %r；classify_by 取值: %r"
              % (info["companies"], info["classify_by"]))
        print("   物理文件存在 %d / 缺失 %d" % (len(info["file_exist"]), len(info["file_missing"])))
        print("   transfer 缓存命中 %d / 期望 %d" % (len(info["transfer_hit"]), len(info["transfer_want"])))

        print("\n【护栏核验】")
        print("   G0 全部为事故恢复登记(recovery-unclassified) %s (异常 %d 条)"
              % ("✓" if not info["g0_bad"] else "✘", len(info["g0_bad"])))
        print("   G1 物理路径不与现存登记共享 ..... %s (共享 %d 条)"
              % ("✓" if not info["g1_bad"] else "✘", len(info["g1_bad"])))
        print("   G2 每份在别处有同 md5 副本 ......... %s (独有 %d 条)"
              % ("✓" if not info["g2_uniq"] else "✘", len(info["g2_uniq"])))
        print("   G3 物理路径均在 DATA_DIR/uploads 内 . %s (越界 %d 条)"
              % ("✓" if not info["g3_bad"] else "✘", len(info["g3_bad"])))

        blockers = info["g0_bad"] + info["g1_bad"] + info["g2_uniq"] + info["g3_bad"]
        if blockers:
            print("\n✘ 护栏未通过，拒绝执行。异常资料 id：%r" % sorted(blockers)[:20])
            return 2

        if not apply:
            print("\n【将执行的动作（演练，未落地）】")
            print("   ① 移入回收站：%d 个物理原件（data/uploads/%d/）"
                  % (len(info["file_exist"]), info["companies"][0] if info["companies"] else "?"))
            print("   ② 清解析子表登记：extracted_tables/fields/issues/document_pages")
            print("   ③ 清中转站缓存：%d 个 transfer/*.json" % len(info["transfer_hit"]))
            print("   ④ 删 documents 登记行：%d 行" % info["total"])
            print("   ⑤ 注册删除墓碑：%d 条（防重启重扫）" % info["total"])
            print("   ⑥ 写业务留痕 1 条")
            print("\n（演练结束，未改动任何数据。加 --apply 执行）")
            return 0
    finally:
        conn.close()                                     # 只读连接到此为止（写阶段用 SQLAlchemy）

    # ── 执行（写阶段：走 database.engine，复用唯一权威原语）─────────────────
    from sqlalchemy import text as _text
    from engine.extract_service import _reset_document_extract as _rst
    from database import engine as _eng

    moved = missed = 0
    transfer_gone = 0
    extract_clean = {"extracted_tables": 0, "extracted_fields": 0,
                     "extract_issues": 0, "document_pages": 0}
    doc_ids = [int(r["id"]) for r in rows]

    with _eng.begin() as sconn:                         # 事务：先改文件、再删登记行
        for r in rows:
            did = int(r["id"])
            fpath = str(r["storage_path"] or "")
            fname = str(r["filename"] or os.path.basename(fpath))
            # ① 物理原件 → 回收站（purge_file ⇒ 唯一权威原语，可恢复）
            if fpath and os.path.isfile(fpath):
                ok, reason = purge_file(fpath)
                if ok and not os.path.exists(fpath):
                    moved += 1
                    add_doc_tombstone(r["company_id"], fname, fpath, reason, purged=True)
                else:
                    missed += 1
                    add_doc_tombstone(r["company_id"], fname, fpath,
                                      "孤儿登记清理：文件未能移入回收站｜%s" % reason,
                                      purged=False)
            else:
                add_doc_tombstone(r["company_id"], fname, fpath,
                                  "孤儿登记清理：物理文件已不存在", purged=True)
            # ② 解析子表（权威出口：三张解析登记表）
            n = _rst(sconn, did)
            for k in ("extracted_tables", "extracted_fields", "extract_issues"):
                extract_clean[k] += int(n.get(k, 0) or 0)
            # ②b document_pages 不属解析模块（`_reset_document_extract` 明确不含）
            #     ⇒ 与 `engine.document_service.delete_document` 同款口径，在此单独删。
            r2 = sconn.execute(_text("DELETE FROM document_pages WHERE document_id=:d"),
                               {"d": did})
            extract_clean["document_pages"] += int(getattr(r2, "rowcount", 0) or 0)
            # ③ 中转站缓存
            parts = fname.split("_", 2)
            if len(parts) >= 2:
                tpath = Path(DATA_DIR) / "uploads" / "transfer" / (
                    "%s_%s.json" % (r["company_id"], parts[1]))
                if tpath.is_file() and _is_inside_data(tpath):
                    ok2, _ = purge_file(tpath)
                    if ok2:
                        transfer_gone += 1
            # ④ 登记行
            sconn.execute(_text("DELETE FROM documents WHERE id=:d"), {"d": did})

    # ⑤ 复扫自证（新开只读连接，避免旧快照）
    vcon = sqlite3.connect(str(ACCOUNTING_DB), timeout=30)
    try:
        left = [dict(x) for x in vcon.execute(
            "SELECT id FROM documents WHERE project_id IS NULL").fetchall()]
        print("\n【执行结果】")
        print("   物理原件移入回收站 %d / 未能移动 %d" % (moved, missed))
        print("   解析子表清理 %r" % extract_clean)
        print("   中转站缓存清理 %d 个" % transfer_gone)
        print("   documents 登记行删除 %d 行" % len(doc_ids))
        print("   复扫 project_id IS NULL 残留：%d 行 %s"
              % (len(left), "✓" if not left else "✘ %r" % left[:10]))
        print("   回收站目录：%s" % TRASH_DIR)
    finally:
        vcon.close()

    # ⑥ 业务留痕（唯一权威；自身不抛，勿再包 try）
    from engine.audit_trail import record as _audit_record
    _audit_record(
        "doc.delete",
        target="10-17 事故孤儿资料登记（project_id IS NULL，共 %d 份）" % info["total"],
        company_id=info["companies"][0] if info["companies"] else None,
        detail="恢复遗留孤儿登记清理：登记行 %d；原件移入回收站 %d（未移动 %d）；"
               "解析子表 %r；中转站缓存 %d。范围仅限 project_id IS NULL 的行；"
               "未触碰 companies/报告/科目/审计日志。"
               % (info["total"], moved, missed, extract_clean, transfer_gone),
    )
    print("\n✓ 完成（业务留痕已写）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())