# -*- coding: utf-8 -*-
"""存量资料治理（2026-10-19，配合四项修正，**幂等**可重跑）：

① 分类代码统一：`documents.category` 的中文字面「其他」→ 代码 `other`
   （旧实现把中文名当代码落库 ⇒ 同概念两种拼法，统计/过滤各认一半）。
② 内容识别回填：`classify_by != 'manual'` 且（doc_type 为空或 category=other）的资料，
   用 `extracted_tables.doc_type`（表头内容识别权威 `main._FILE_FINGERPRINTS` 的产物）
   回填 doc_type / category —— 不重新解析，只用已落库的识别结果。
③ 孤儿清理：删除资料时旧代码漏清三张解析登记表 ⇒ 清理引用已删资料的
   extracted_tables / extracted_fields / extract_issues 行（派生数据，随主档消亡）。
④ 异常重算：按**修正后的校验规则**（bank 余额勾稽 / 红字冲销分诊 / 凭证域重复豁免）
   重算所有存活资料的 extract_issues；`resolved`/`ignored` 的人工处置按
   (document_id, rule, message) 保留。

★ 只动派生数据（解析登记、异常清单）与分类字段；**不碰**原件文件与 reports。
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DB = os.path.join(ROOT, "data", "accounting.db")


def main() -> int:
    sys.path.insert(0, ROOT)
    from engine.extract_service import _domain_of, _registered_names   # noqa: PLC0415
    from engine.extract_validate import validate_rows                  # noqa: PLC0415
    from engine.document_types import type_to_category                 # noqa: PLC0415

    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    out: list[str] = []

    # ── ① 分类代码统一 ──
    n = c.execute("UPDATE documents SET category='other' WHERE category='其他'").rowcount
    c.commit()
    out.append("① 「其他」→ other 归一：%d 行" % n)

    # ── ② 内容识别回填 ──
    docs = c.execute(
        "SELECT id, original_name, doc_type, category, classify_by, IFNULL(note,'') AS note "
        "FROM documents WHERE classify_by <> 'manual' AND (IFNULL(doc_type,'')='' "
        " OR category IN ('other','其他','') OR IFNULL(note,'') LIKE '内容识别：%')"
    ).fetchall()
    filled = 0
    picks: Counter = Counter()
    for d in docs:
        types = [r[0] for r in c.execute(
            "SELECT doc_type FROM extracted_tables WHERE document_id=? AND IFNULL(doc_type,'')<>''",
            (d["id"],))]
        if not types:
            continue
        best, cnt = Counter(types).most_common(1)[0]
        cat = type_to_category().get(best, "")
        if not cat:
            continue
        c.execute(
            "UPDATE documents SET doc_type=?, category=?, classify_by='auto', "
            "note=COALESCE(?, note) WHERE id=?",
            (best, cat,
             "内容识别：%s（依据 %d 张解析表；原分类 %s / 类型 %s）"
             % (best, len(types), d["category"] or "空", d["doc_type"] or "空"),
             d["id"]))
        picks["%s→%s" % (d["category"] or "空", cat)] += 1
        filled += 1
    c.commit()
    out.append("② 内容识别回填：%d 份（%s）" % (filled, dict(picks)))

    # ── ③ 孤儿清理 ──
    orphan = {}
    for tbl in ("extracted_tables", "extracted_fields", "extract_issues"):
        n = c.execute("DELETE FROM %s WHERE document_id NOT IN (SELECT id FROM documents)" % tbl).rowcount
        orphan[tbl] = n
    c.commit()
    out.append("③ 孤儿清理：表 %d / 字段 %d / 异常 %d" % (
        orphan["extracted_tables"], orphan["extracted_fields"], orphan["extract_issues"]))

    # ── ④ 异常重算（保留人工处置）──
    kept = c.execute(
        "SELECT document_id, rule, message, status FROM extract_issues "
        "WHERE status IN ('resolved','ignored')").fetchall()
    preserved = {(k["document_id"], k["rule"], k["message"]): k["status"] for k in kept}
    n = c.execute("DELETE FROM extract_issues").rowcount
    c.commit()

    tables = c.execute(
        "SELECT t.id, t.document_id, t.doc_type, t.rows_json, d.project_id, d.company_id "
        "FROM extracted_tables t JOIN documents d ON d.id=t.document_id "
        "WHERE t.rows_json IS NOT NULL AND t.rows_json<>''").fetchall()
    regenerated = 0
    reused = 0
    for t in tables:
        try:
            rows = json.loads(t["rows_json"])
        except Exception:                                 # noqa: BLE001
            continue
        if not isinstance(rows, list) or not rows:
            continue
        dom = _domain_of(t["doc_type"])
        names = _registered_names(rows, t["doc_type"])
        issues = validate_rows(rows, domain=dom, standard_names=names)
        for it in issues:
            key = (t["document_id"], str(it.get("rule")), str(it.get("message"))[:2000])
            status = preserved.get(key, "open")
            if status != "open":
                reused += 1
            c.execute(
                "INSERT INTO extract_issues (document_id, table_id, project_id, company_id, "
                " rule, severity, message, detail_json, status, created_at) "
                "SELECT ?,?,?,?,?,?,?,?,'open', datetime('now','localtime') "
                "WHERE NOT EXISTS (SELECT 1 FROM extract_issues WHERE document_id=? "
                "                  AND table_id=? AND rule=? AND message=?)",
                (t["document_id"], t["id"], t["project_id"], t["company_id"],
                 str(it.get("rule")), str(it.get("severity")),
                 str(it.get("message"))[:2000],
                 json.dumps(it.get("detail") or {}, ensure_ascii=False, default=str)[:20000],
                 t["document_id"], t["id"], str(it.get("rule")),
                 str(it.get("message"))[:2000]))
            regenerated += 1
    c.commit()

    # 人工处置回填（同 key）
    restored = 0
    for (did, rule, msg), status in preserved.items():
        n = c.execute(
            "UPDATE extract_issues SET status=? WHERE document_id=? AND rule=? AND message=? "
            "AND status='open'", (status, did, rule, msg)).rowcount
        restored += n
    c.commit()

    out.append("④ 异常重算：旧 %d 条 → 新 %d 条（人工处置恢复 %d 条）"
               % (n, regenerated, restored))

    # ── 结果速览 ──
    out.append("")
    out.append("== 分类分布（改后）==")
    for r in c.execute("SELECT category, COUNT(*) FROM documents GROUP BY category ORDER BY 2 DESC"):
        out.append("   %s: %d" % (r[0], r[1]))
    out.append("== 异常分布（改后）==")
    for r in c.execute("SELECT rule, COUNT(*) FROM extract_issues GROUP BY rule ORDER BY 2 DESC"):
        out.append("   %s: %d" % (r[0], r[1]))
    orphan_left = c.execute(
        "SELECT COUNT(*) FROM extract_issues WHERE document_id NOT IN (SELECT id FROM documents)"
    ).fetchone()[0]
    out.append("== 孤儿异常残留：%d（应为 0）==" % orphan_left)
    c.close()
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
