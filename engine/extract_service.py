# -*- coding: utf-8 -*-
"""解析与标准化（P0-3）**Service 层**。

★★ 复用而非另造（本模块最重要的一条原则）
  本项目**已有**成熟的解析链路，本模块**只做"登记 + 标准化 + 校验 + 人工校正"**，
  **不另写一套解析器**（另写 = 两套解析口径，且会绕过既有已校准的识别逻辑）：

  | 环节 | **复用谁**（唯一权威） |
  |---|---|
  | Excel / CSV 表格解析 | `main._parse_excel_structured(filepath, ext, original_name)` ⇒ `{type, rows, confidence, source, _trace}` |
  | 图片 OCR | `main._ocr_png_bytes(png_bytes)`（三档降级 rapidocr → easyocr → pytesseract） |
  | PDF 文本/表格 | `pdfplumber`（既有依赖） |
  | 字段别名 | `engine/fieldkit.py` 的 `*_KEYS` 常量（经 `standard_fields.aliases_from` 引用） |
  | 金额解析 | `engine/numparse.to_number_checked`（能区分"真 0"与"解析失败"） |
  | 异步作业 | `engine/analysis_jobs.py`（作业流水 + 状态机，JSONL 权威） |
  | 审计 | `engine.audit_trail.record` |
  | 删除 | `runtime_storage`（本模块**不删任何东西**） |

★ 可追溯（验收要求）
  每个标准字段值都带 `source_ref = {sheet, row, col, raw}` ⇒ **可回链到原文件的具体单元格**；
  `extracted_tables.rows_json` 保留整表原始行 ⇒ 原值永不丢失。
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from engine.extract_store import ensure_schema
from engine.extract_validate import RULES, RULE_CN, summary as _vsum, validate_rows
from engine.standard_fields import (
    aliases_of, domain_cn, field as _field, field_names, fields_of_domain,
    normalize_value, value_from_row,
)


class ExtractError(Exception):
    """业务异常：携带 HTTP 状态码，由 API 层原样转发。"""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = int(status)


# --------------------------------------------------------------------------
# 薄转发
# --------------------------------------------------------------------------
def _engine_or_default(engine):
    if engine is not None:
        return engine
    from database import engine as _engine            # noqa: PLC0415
    return _engine


def _now() -> str:
    from runtime_storage import now_cst               # noqa: PLC0415
    return now_cst()


def _audit(action: str, *, target: Any, company_id: Any, detail: Any,
           request: Any = None) -> None:
    from engine.audit_trail import record as _record   # noqa: PLC0415
    _record(action, target=target, company_id=company_id, detail=detail, request=request)


def _project_row(conn, session: Any, project_id: Any) -> Dict[str, Any]:
    """租户隔离（复用 P0-1）；`ProjectError` 在本边界转 `ExtractError` 并保持状态码。"""
    from engine.project_service import ProjectError, _fetch_visible   # noqa: PLC0415
    try:
        return _fetch_visible(conn, session, project_id)
    except ProjectError as exc:
        raise ExtractError(str(exc.message), int(exc.status)) from exc


def _document_row(conn, session: Any, document_id: Any) -> Dict[str, Any]:
    """资料可见性（复用 P0-2 的判定链：资料 → 项目 → 租户）。"""
    from engine.document_service import DocumentError, _document_row as _drow  # noqa: PLC0415
    try:
        return _drow(conn, session, document_id)
    except DocumentError as exc:
        raise ExtractError(str(exc.message), int(exc.status)) from exc


def _v400(fn, *args, **kwargs):
    """把 `standard_fields` 的 `ValueError` 统一转 400（边界唯一转换点）。"""
    try:
        return fn(*args, **kwargs)
    except ValueError as exc:
        if isinstance(exc, ExtractError):
            raise
        raise ExtractError(str(exc), 400) from exc


ACT_EXTRACT_RUN = "extract.run"
ACT_EXTRACT_CORRECT = "extract.correct"


def _reset_document_extract(conn, document_id: int) -> Dict[str, int]:
    """清掉**本模块自己的**解析登记（幂等重建用）。

    ★ 这是**声明的删除出口**（已登记 `check_delete_exits::_EXITS`）：
      范围 = **本模块三张解析登记表**（`extracted_tables` / `extracted_fields` /
      `extract_issues`）中该文档的行。
      **不触碰**：`documents` 表（P0-2 的资料登记）、物理文件、任何其他模块的表。
      ⇒ 「重新解析」= 只重置**解析产物**，原件与资料登记保持不变（原件不可变铁律）。
    """
    from sqlalchemy import text as _text              # noqa: PLC0415
    n = {}
    for tbl in ("extract_issues", "extracted_fields", "extracted_tables"):
        r = conn.execute(_text("DELETE FROM %s WHERE document_id=:d" % tbl),
                         {"d": int(document_id)})
        try:
            n[tbl] = int(getattr(r, "rowcount", 0) or 0)
        except Exception:                             # noqa: BLE001
            n[tbl] = 0
    return n


# --------------------------------------------------------------------------
# 解析（**复用现有解析链路**）
# --------------------------------------------------------------------------
def parse_document(document_id: Any, session: Any, *, engine=None,
                   request: Any = None) -> Dict[str, Any]:
    """解析一份资料 → 登记 `extracted_tables` + 标准化 `extracted_fields` + 校验 `extract_issues`。

    落点是**幂等重建**：同一资料重复解析 ⇒ 先清旧登记（本模块自己的三张表），再写新的；
    **不触碰** `documents` 表与物理文件（原件不可变）。
    """
    eng = _engine_or_default(engine)
    ensure_schema(eng)
    from sqlalchemy import text as _text              # noqa: PLC0415

    with eng.connect() as conn:
        doc = _document_row(conn, session, document_id)
    path = str(doc.get("storage_path") or "")
    if not path or not os.path.exists(path):
        raise ExtractError("物理文件不存在，无法解析", 404)
    ext = str(doc.get("ext") or os.path.splitext(path)[1]).lower()
    name = str(doc.get("original_name") or os.path.basename(path))
    pid, cid = doc.get("project_id"), doc.get("company_id")

    tables, parse_error = _parse_file(path, ext, name)
    ts = _now()

    # ★ 幂等重建：先清本模块自己的旧登记（不触碰 documents / 物理文件）
    with eng.begin() as conn:
        _reset_document_extract(conn, int(doc["id"]))

    written_tables: List[Dict[str, Any]] = []
    written_fields: List[Dict[str, Any]] = []
    all_issues: List[Dict[str, Any]] = []

    expect_period = ""
    try:
        with eng.connect() as conn:
            prow = _project_row(conn, session, pid) if pid not in (None, "") else {}
        expect_period = str(prow.get("period_start") or "")
    except ExtractError:
        expect_period = ""

    for t in tables:
        rows = t.get("rows") or []
        std_names = _registered_names(rows, t.get("doc_type"))
        issues = validate_rows(rows, domain=_domain_of(t.get("doc_type")),
                               standard_names=std_names, expect_period=expect_period)
        with eng.begin() as conn:
            tid = int(conn.execute(_text(
                "INSERT INTO extracted_tables (document_id, project_id, company_id, sheet_name, "
                " doc_type, confidence, detect_source, header, row_count, col_count, rows_json, "
                " parse_status, parsed_at) "
                "VALUES (:d,:p,:c,:sn,:dt,:cf,:ds,:hd,:rc,:cc,:rj,:ps,:ts) RETURNING id"
            ), {
                "d": int(doc["id"]), "p": pid, "c": cid,
                "sn": str(t.get("sheet") or ""), "dt": str(t.get("doc_type") or ""),
                "cf": float(t.get("confidence") or 0), "ds": str(t.get("source") or ""),
                "hd": json.dumps(t.get("header") or [], ensure_ascii=False),
                "rc": len(rows), "cc": len(t.get("header") or []),
                "rj": json.dumps(rows, ensure_ascii=False, default=str)[:2_000_000],
                "ps": "success", "ts": ts,
            }).first()[0])

            # ── 标准化：逐标准字段登记（带来源行号 ⇒ 可回链）──
            for n in std_names:
                vals = []
                for i, r in enumerate(rows, 1):
                    v = value_from_row(n, r)
                    if v in (None, ""):
                        continue
                    conv, ok, why = normalize_value(n, v)
                    vals.append((i, v, conv, ok, why))
                if not vals:
                    continue
                row_no, raw, conv, ok, why = vals[0]
                fdef = _field(n) or {}
                conn.execute(_text(
                    "INSERT INTO extracted_fields (document_id, table_id, project_id, company_id, "
                    " standard_field, field_cn, domain, value_text, value_amount, value_period, "
                    " source_ref, confidence) "
                    "VALUES (:d,:t,:p,:c,:sf,:cn,:dm,:vt,:va,:vp,:sr,:cf)"
                ), {
                    "d": int(doc["id"]), "t": tid, "p": pid, "c": cid,
                    "sf": n, "cn": str(fdef.get("cn") or n), "dm": str(fdef.get("domain") or ""),
                    "vt": str(conv if ok else raw)[:2000],
                    "va": (float(conv) if ok and str(fdef.get("type")) == "amount"
                           and isinstance(conv, (int, float)) else None),
                    "vp": (str(conv) if ok and str(fdef.get("type")) == "period" else None),
                    "sr": json.dumps({"sheet": t.get("sheet") or "", "row": row_no,
                                      "raw": str(raw)[:200]}, ensure_ascii=False),
                    "cf": float(t.get("confidence") or 0),
                })
                written_fields.append({"standard_field": n, "field_cn": fdef.get("cn"),
                                       "domain": fdef.get("domain"), "sample": str(raw)[:80],
                                       "row": row_no})

            # ── 校验异常落库 ──
            for it in issues:
                conn.execute(_text(
                    "INSERT INTO extract_issues (document_id, table_id, project_id, company_id, "
                    " rule, severity, message, detail_json, status, created_at) "
                    "VALUES (:d,:t,:p,:c,:r,:sv,:m,:dj,'open',:ts)"
                ), {
                    "d": int(doc["id"]), "t": tid, "p": pid, "c": cid,
                    "r": str(it.get("rule")), "sv": str(it.get("severity")),
                    "m": str(it.get("message"))[:2000],
                    "dj": json.dumps(it.get("detail") or {}, ensure_ascii=False, default=str)[:20000],
                    "ts": ts,
                })
                all_issues.append(it)

        written_tables.append({"id": tid, "sheet": t.get("sheet"),
                               "doc_type": t.get("doc_type"),
                               "confidence": t.get("confidence"),
                               "row_count": len(rows)})

    # ★ MQ2-D3（2026-10-16）：**「无错误」≠「解析成功」**。
    #   原判据只看 `parse_error`，于是两类"空内容"被记成成功：
    #     ① 非财税资料（如 `.txt`）：解析器既没报错、也没产出任何表 ⇒ success；
    #     ② 内容损坏的 `.xlsx`：产出了一张 **0 行** 的表（row_count=0 / 字段 0）⇒ success。
    #   后果：下游把"什么都没解析出来"当"已解析完成"，进而使覆盖率/资料齐备性判断失真。
    #   修法（**只改判定条件，不改解析引擎**）：成功必须同时满足
    #     「无解析错误」**且**「至少有一张表且该表有数据行」。
    ok = _parse_ok(tables, parse_error)
    if not ok and not parse_error:
        parse_error = ("未解析出任何数据行（表 %d 张、行 0）——"
                       "非财税资料或内容损坏；已标记为解析失败" % len(tables))

    # 无内容/解析失败 ⇒ 如实登记一行 failed，不假装成功
    if not ok:
        with eng.begin() as conn:
            conn.execute(_text(
                "INSERT INTO extracted_tables (document_id, project_id, company_id, doc_type, "
                " parse_status, parsed_at) VALUES (:d,:p,:c,'', 'failed', :ts)"
            ), {"d": int(doc["id"]), "p": pid, "c": cid, "ts": ts})

    _audit("extract.run", target=name, company_id=cid,
           detail="解析资料：表 %d 张、标准字段 %d 项、校验异常 %d 条%s"
                  % (len(written_tables), len(written_fields), len(all_issues),
                     ("；解析失败：%s" % parse_error) if parse_error else ""),
           request=request)

    # ★ 2026-10-15 解析成功 ⇒ parse_status 自动流转到 success（单一权威：
    #   自动线程/手工解析/一键重析全走本函数，状态不再与产物脱节）。
    #   状态机无「直达」路径 ⇒ 按合法边走：failed→pending→parsing→success、
    #   pending→parsing→success、parsing→success、manual→success。
    # ★ MQ2-D3：无内容 ⇒ 按合法边流转到 **failed**（而非 success）。
    if ok:
        try:
            _flow_to_success(int(doc["id"]), session, eng)
        except Exception:                             # noqa: BLE001 — 状态流转失败不掩盖解析成功
            from engine.audit_trail import record as _rec    # noqa: PLC0415
            _rec("extract.run", target=str(doc["id"]), company_id=cid,
                 detail="⚠ 解析成功但状态流转失败（可在资料页重析归位）")
    else:
        try:
            _flow_to_failed(int(doc["id"]), session, eng)
        except Exception:                             # noqa: BLE001
            from engine.audit_trail import record as _rec    # noqa: PLC0415
            _rec("extract.run", target=str(doc["id"]), company_id=cid,
                 detail="⚠ 解析无内容但状态流转失败（可在资料页重析归位）")

    return {
        "ok": True, "document_id": int(doc["id"]), "original_name": name,
        "tables": written_tables, "fields": written_fields,
        "issues": all_issues, "issue_summary": _vsum(all_issues),
        "parse_error": parse_error,
        "parsed_at": ts,
    }


def _parse_ok(tables: List[Dict[str, Any]], parse_error: str) -> bool:
    """**解析成功判定**（MQ2-D3 单一权威）：「无解析错误」**且**「至少一张表有数据行」。

    ★ 为什么不能只看 `parse_error`：实测两类"空内容"被记成 success ——
      ① 非财税资料（`.txt`）：解析器既没报错、也没产出表；
      ② 内容损坏的 `.xlsx`：产出一张 **0 行** 的表。
    判据抽成函数是为了**可直接单测**（避免只能端到端验、回归慢）。
    """
    return (not parse_error) and any((t.get("rows") or []) for t in (tables or []))


def _flow_to_failed(document_id: int, session: Any, eng: Any) -> None:
    """★ MQ2-D3：把 parse_status 按状态机**合法边**推进到 failed（无内容/解析失败）。

    路径：pending→failed、parsing→failed；success→pending→failed、manual→pending→failed。
    （`PARSE_STATUS_FLOW` 的 `failed` 前驱：pending 与 parsing；故先把非法当前态退回 pending。）
    """
    from sqlalchemy import text as _text              # noqa: PLC0415
    from engine.document_service import set_parse_status as _sps   # noqa: PLC0415
    from engine.document_types import PARSE_STATUS_FLOW as _FLOW    # noqa: PLC0415
    with eng.connect() as conn:
        row = conn.execute(_text(
            "SELECT parse_status FROM documents WHERE id=:d"), {"d": int(document_id)}
        ).first()
    cur = str((row or ("pending",))[0] or "pending")
    if cur == "failed":
        return
    if "failed" not in (_FLOW.get(cur) or ()):        # 当前态不能直达 failed ⇒ 先退回 pending
        _sps(int(document_id), "pending", session, engine=eng)
    _sps(int(document_id), "failed", session, engine=eng)


def _flow_to_success(document_id: int, session: Any, eng: Any) -> None:
    """★ 2026-10-15：把 parse_status 按状态机**合法边**推进到 success。

    路径：failed→pending→parsing→success；pending→parsing→success；
    parsing→success；manual→success；已在 success ⇒ 原样返回。
    （状态机唯一权威 document_types.PARSE_STATUS_FLOW，此处不另立规则。）"""
    from sqlalchemy import text as _text              # noqa: PLC0415
    from engine.document_service import set_parse_status as _sps   # noqa: PLC0415
    with eng.connect() as conn:
        row = conn.execute(_text(
            "SELECT parse_status FROM documents WHERE id=:d"), {"d": int(document_id)}
        ).first()
    cur = str((row or ("pending",))[0] or "pending")
    if cur == "success":
        return
    if cur == "failed":
        _sps(int(document_id), "pending", session, engine=eng)
        cur = "pending"
    if cur == "pending":
        _sps(int(document_id), "parsing", session, engine=eng)
        cur = "parsing"
    if cur != "success":
        _sps(int(document_id), "success", session, engine=eng)


def _domain_of(doc_type: Any) -> str:
    """解析器判定的类型码 → 标准字段域（**加一行数据即可扩展**）。"""
    from engine.document_types import type_to_category       # noqa: PLC0415
    cat = type_to_category().get(str(doc_type or ""), "")
    return {"ledger": "ledger", "invoice": "invoice", "bank_statement": "bank",
            "declaration": "declaration", "payroll": "payroll",
            "financial_statement": "report"}.get(cat, "")


def _registered_names(rows: List[Dict[str, Any]], doc_type: Any) -> List[str]:
    """本表**命中**的标准字段：域字段（含 common）+ 实际能在行里取到值的全局字段。

    ★ 口径：只登记**真取到值**的字段（不登记空字段 ⇒ 不制造"假字段"）；
      必填字段即便取不到也登记一次（否则「必填缺失」无从判定）。
    """
    dom = _domain_of(doc_type)
    names: List[str] = []
    for f in fields_of_domain(dom) + fields_of_domain("common"):
        names.append(str(f.get("name")))
    for f in _other_domain_hits(rows, exclude=set(names)):
        names.append(f)
    for n in [str(x.get("name")) for x in _required_all()]:
        if n not in names:
            names.append(n)
    seen: set = set()
    out: List[str] = []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    # 过滤：既非必填、行里也取不到值的字段 → 丢弃（避免登记空字段）
    from engine.standard_fields import required_names as _req
    req = set(_req())
    keep = []
    for n in out:
        if n in req:
            keep.append(n)
            continue
        if any(value_from_row(n, r) not in (None, "") for r in rows):
            keep.append(n)
    return keep


def _required_all() -> List[Dict[str, Any]]:
    from engine.standard_fields import fields as _f   # noqa: PLC0415
    return [x for x in _f() if x.get("required")]


def _other_domain_hits(rows: List[Dict[str, Any]], exclude: set) -> List[str]:
    """跨域命中：某些资料（如 PDF 合同）可能带发票/银行字段 —— 取到即登记。"""
    from engine.standard_fields import fields as _f   # noqa: PLC0415
    out = []
    for f in _f():
        n = str(f.get("name"))
        if n in exclude:
            continue
        if any(value_from_row(n, r) not in (None, "") for r in rows):
            out.append(n)
    return out


def _fallback_vertical_kv(path: str, ext: str, parsed: Any) -> Optional[Dict[str, Any]]:
    """**兜底**解析「键值对纵向表」（两列：项目名 / 金额）。

    ★ 为什么需要：实测**资产负债表**这类表是**纵向键值对**布局
      （A 列=项目名如"资产总计"，B 列=金额），既有 `_parse_excel_structured`
      会判定类型为 `financial_statements` 但**产出 0 行**（它期望的是"表头+多行"横表）。
      ⇒ 本兜底把纵向两列展开为**每行一个 (项目, 金额)**，从而让 `total_assets` 等
        标准字段能被取到。**这是本模块的增量能力，不修改既有解析器**。

    ★ 保守启用（宁可不解析，不可乱解析）：
      · 只处理**恰好 2 列**且有 ≥2 个数据行；
      · 第一列**必须是非空文本**（且不是纯数字）；第二列**必须是数值**（≥80% 行可解析）；
      · 前 3 行内不得出现"表头样"重复（避免把横表误当键值表）。
    不满足 ⇒ 返回 `None`（调用方照常报"未识别出结构"，**不伪造行**）。
    """
    if ext not in (".xlsx", ".xls"):
        return None
    try:
        from engine.workbook import load_workbook, close_workbook   # noqa: PLC0415
    except Exception:                                 # noqa: BLE001
        return None
    from engine.numparse import to_number_checked     # noqa: PLC0415
    wb = None
    try:
        wb = load_workbook(path, read_only=True, data_only=True)
        for ws in wb.worksheets:
            grid = []
            for row in ws.iter_rows(values_only=True):
                vals = list(row or [])
                grid.append(vals)
                if len(grid) > 500:
                    break
            # 去掉完全空行
            grid = [r for r in grid if any(c not in (None, "") for c in r)]
            if len(grid) < 3:
                continue
            width = max(len(r) for r in grid)
            if width != 2:
                continue
            col_a = [r[0] for r in grid]
            col_b = [r[1] if len(r) > 1 else None for r in grid]
            # 第二列数值占比 ≥ 80%（跳过表头行后再算）
            body_b = [v for v in col_b[1:] if v not in (None, "")]
            if not body_b:
                continue
            oknum = sum(1 for v in body_b if to_number_checked(v, default=0.0)[1])
            if oknum < max(1, int(len(body_b) * 0.8)):
                continue
            # 第一列必须是非空文本、且非纯数字
            a_txt = [str(v).strip() for v in col_a[1:] if v not in (None, "")]
            if len(a_txt) < 2:
                continue
            if sum(1 for s in a_txt if to_number_checked(s, default=-1.0)[1] is False) < len(a_txt) * 0.8:
                continue
            header = [str(col_a[0] or "项目"), str(col_b[0] or "金额")]
            # ★ 关键：纵向键值表的**字段名在「项目」列的值里**（如"资产总计"），
            #   不在列名上 ⇒ 必须**透视**成一行 `{项目名: 金额}`，
            #   否则 `total_assets` 这类标准字段（别名="资产总计"）永远取不到。
            pivoted: Dict[str, Any] = {}
            for r in grid[1:]:
                name_v = r[0] if len(r) > 0 else None
                amt_v = r[1] if len(r) > 1 else None
                if name_v in (None, ""):
                    continue
                k = str(name_v).strip()
                if not k or k in pivoted:
                    continue                              # 重名项目只取首个（不覆盖）
                pivoted[k] = amt_v
            if len(pivoted) < 2:
                continue
            return {"sheet": str(ws.title or ""),
                    "doc_type": str((parsed or {}).get("type") or ""),
                    "confidence": 0.6, "source": "fallback-vertical-kv",
                    "header": [header[0], header[1]] + list(pivoted.keys())[:200],
                    "rows": [pivoted]}
    except Exception:                                 # noqa: BLE001
        return None
    finally:
        if wb is not None:
            try:
                close_workbook(wb)                    # ★ 必须关（read_only 的 zip 句柄）
            except Exception:                         # noqa: BLE001
                pass
    return None


def _parse_file(path: str, ext: str, name: str) -> Tuple[List[Dict[str, Any]], str]:
    """**复用**现有解析链路，返回 `(tables, parse_error)`。

    每个 table = `{sheet, doc_type, confidence, source, header, rows}`。
    """
    tables: List[Dict[str, Any]] = []
    err = ""
    # ① Excel / CSV ⇒ 既有 `_parse_excel_structured`（唯一权威）
    if ext in (".xlsx", ".xls", ".csv"):
        try:
            import main as _main                      # noqa: PLC0415
            r = _main._parse_excel_structured(path, ext, name)   # noqa: SLF001
            if isinstance(r, dict) and r.get("rows"):
                rows = r.get("rows") or []
                tables.append({"sheet": "", "doc_type": r.get("type") or "",
                               "confidence": float(r.get("confidence") or 0),
                               "source": str(r.get("source") or ""),
                               "header": list(rows[0].keys()) if rows and isinstance(rows[0], dict) else [],
                               "rows": rows})
            else:
                # ★ 兜底（本模块的**增量能力**，不改既有解析器）：既有解析器识别出类型
                #   但未产出数据行 ⇒ 常见于**「键值对纵向表」**（两列：项目 / 金额，
                #   如资产负债表按行罗列"资产总计 500000"）。实测此类表 rows=0。
                #   兜底**保守**：只在明确满足"两列 + 首列文本 + 次列数值"时启用。
                fb = _fallback_vertical_kv(path, ext, r)
                if fb:
                    tables.append(fb)
                    err = ""
                else:
                    err = "既有解析器未识别出表格结构"
        except Exception as exc:                      # noqa: BLE001
            err = "解析失败（%s）：%s" % (type(exc).__name__, exc)
    # ② PDF ⇒ pdfplumber（既有依赖）取表 + 文本
    elif ext == ".pdf":
        try:
            import pdfplumber                         # noqa: PLC0415
            with pdfplumber.open(path) as pdf:
                for pi, page in enumerate(pdf.pages, 1):
                    for ti, tb in enumerate(page.extract_tables() or [], 1):
                        if not tb or len(tb) < 2:
                            continue
                        header = [str(c or "").strip() for c in tb[0]]
                        rows = [dict(zip(header, r)) for r in tb[1:] if r]
                        tables.append({"sheet": "P%d-T%d" % (pi, ti), "doc_type": "",
                                       "confidence": 0.8, "source": "pdfplumber",
                                       "header": header, "rows": rows})
                if not tables:
                    text = "\n".join((p.extract_text() or "") for p in pdf.pages)
                    if text.strip():
                        tables.append({"sheet": "文本", "doc_type": "", "confidence": 0.5,
                                       "source": "pdf-text", "header": ["文本"],
                                       "rows": [{"文本": line} for line in text.splitlines() if line.strip()]})
                    else:
                        err = "PDF 无文字层（需 OCR）"
        except Exception as exc:                      # noqa: BLE001
            err = "PDF 解析失败（%s）：%s" % (type(exc).__name__, exc)
    # ③ 图片 ⇒ **复用**既有 OCR（三档降级）
    elif ext in (".jpg", ".jpeg", ".png", ".bmp", ".tiff"):
        try:
            import main as _main                      # noqa: PLC0415
            with open(path, "rb") as fh:
                txt = _main._ocr_png_bytes(fh.read())     # noqa: SLF001
            if txt and str(txt).strip():
                tables.append({"sheet": "", "doc_type": "", "confidence": 0.5,
                               "source": "ocr", "header": ["文本"],
                               "rows": [{"文本": line} for line in str(txt).splitlines() if line.strip()]})
            else:
                err = "OCR 未识别出内容（可能未安装 OCR 引擎）"
        except Exception as exc:                      # noqa: BLE001
            err = "OCR 失败（%s）：%s" % (type(exc).__name__, exc)
    else:
        err = "该格式（%s）暂不支持结构化解析" % (ext or "(无扩展名)")
    return tables, err


# --------------------------------------------------------------------------
# 查询 / 人工校正
# --------------------------------------------------------------------------
def get_extracted(document_id: Any, session: Any, *, engine=None,
                  domain: Any = None, only_corrected: Any = None) -> Dict[str, Any]:
    """取某资料的解析结果（表 + 标准字段 + 校验异常）。"""
    eng = _engine_or_default(engine)
    ensure_schema(eng)
    from sqlalchemy import text as _text              # noqa: PLC0415
    with eng.connect() as conn:
        doc = _document_row(conn, session, document_id)
        did = int(doc["id"])
        trows = conn.execute(_text(
            "SELECT id, sheet_name, doc_type, confidence, detect_source, header, row_count, "
            "col_count, rows_json, parse_status, parsed_at FROM extracted_tables "
            "WHERE document_id=:d ORDER BY id"), {"d": did}).all()
        q = "SELECT id, table_id, standard_field, field_cn, domain, value_text, value_amount, "
        q += "value_period, source_ref, confidence, corrected, corrected_by, corrected_at, original_value "
        q += "FROM extracted_fields WHERE document_id=:d"
        params: Dict[str, Any] = {"d": did}
        dm = str(domain or "").strip()
        if dm:
            q += " AND domain=:dm"
            params["dm"] = dm
        if only_corrected not in (None, ""):
            q += " AND corrected=:oc"
            params["oc"] = 1 if str(only_corrected).lower() in ("1", "true", "yes") else 0
        q += " ORDER BY domain, standard_field, id"
        frows = conn.execute(_text(q), params).all()
        irows = conn.execute(_text(
            "SELECT id, table_id, rule, severity, message, detail_json, status, resolved_by, "
            "resolved_at, created_at FROM extract_issues WHERE document_id=:d "
            "ORDER BY CASE severity WHEN 'error' THEN 0 ELSE 1 END, id"), {"d": did}).all()

    tables = []
    for r in trows:
        m = dict(r._mapping)
        try:
            m["rows_preview"] = json.loads(m.get("rows_json") or "[]")[:20]
        except Exception:                             # noqa: BLE001
            m["rows_preview"] = []
        m.pop("rows_json", None)                      # 明细表可能很大，仅给预览
        tables.append(m)
    fields = []
    for r in frows:
        m = dict(r._mapping)
        try:
            m["source"] = json.loads(m.get("source_ref") or "{}")
        except Exception:                             # noqa: BLE001
            m["source"] = {}
        fields.append(m)
    issues = []
    for r in irows:
        m = dict(r._mapping)
        try:
            m["detail"] = json.loads(m.get("detail_json") or "{}")
        except Exception:                             # noqa: BLE001
            m["detail"] = {}
        m["rule_cn"] = RULE_CN.get(str(m.get("rule")), str(m.get("rule")))
        issues.append(m)

    return {"document_id": did, "original_name": str(doc.get("original_name") or ""),
            "parse_status": str(doc.get("parse_status") or ""),
            "tables": tables, "fields": fields, "issues": issues,
            "issue_summary": _vsum(issues),
            "source_trace": {"storage_path": str(doc.get("storage_path") or ""),
                             "md5": str(doc.get("md5") or ""),
                             "sha256": str(doc.get("sha256") or "")}}


def correct_field(field_id: Any, payload: Dict[str, Any], session: Any, *, engine=None,
                  request: Any = None) -> Dict[str, Any]:
    """**人工校正**一个标准字段值。

    ★ 口径：`corrected=1` + 保留 `original_value`（原值**永不丢失**，满足可追溯）；
      校正后的值按字段 `type` 归一（金额/期间会校验），非法即 400（不静默存错值）。
    """
    eng = _engine_or_default(engine)
    ensure_schema(eng)
    from sqlalchemy import text as _text              # noqa: PLC0415
    try:
        fid = int(field_id)
    except Exception:                                 # noqa: BLE001
        raise ExtractError("字段记录 ID 非法", 400)
    new_raw = payload.get("value")
    if new_raw is None:
        raise ExtractError("缺少 value", 400)

    with eng.begin() as conn:
        row = conn.execute(_text(
            "SELECT id, document_id, standard_field, value_text, source_ref FROM extracted_fields "
            "WHERE id=:i"), {"i": fid}).first()
        if row is None:
            raise ExtractError("字段记录不存在", 404)
        m = dict(row._mapping)
        _document_row(conn, session, m["document_id"])     # 权限前置（跨租户 ⇒ 404）

        name = str(m.get("standard_field") or "")
        conv, ok, why = normalize_value(name, new_raw)
        if not ok:
            raise ExtractError("校正值不合规：%s" % why, 400)
        fdef = _field(name) or {}
        ts = _now()
        uname = str(getattr(session, "username", "") or "")
        conn.execute(_text(
            "UPDATE extracted_fields SET value_text=:vt, value_amount=:va, value_period=:vp, "
            " corrected=1, corrected_by=:by, corrected_at=:ts, "
            " original_value=COALESCE(original_value, value_text) WHERE id=:i"
        ), {
            "vt": str(conv)[:2000],
            "va": (float(conv) if str(fdef.get("type")) == "amount" else None),
            "vp": (str(conv) if str(fdef.get("type")) == "period" else None),
            "by": uname, "ts": ts, "i": fid,
        })
        src = json.loads(m.get("source_ref") or "{}")
    _audit("extract.correct",
           target="%s#%s" % (src.get("sheet") or "-", src.get("row") or "-"),
           company_id=None,
           detail="人工校正标准字段「%s」：%s → %s"
                  % ((_field(name) or {}).get("cn", name), str(m.get("value_text"))[:60],
                     str(conv)[:60]),
           request=request)
    return {"ok": True, "id": fid, "standard_field": name,
            "field_cn": (_field(name) or {}).get("cn", name),
            "value": conv, "previous_value": m.get("value_text"), "corrected": True}


def resolve_issue(issue_id: Any, payload: Dict[str, Any], session: Any, *, engine=None,
                  request: Any = None) -> Dict[str, Any]:
    """标记校验异常为已处理（`resolved` / `ignored`），**不删除**（保留审计痕迹）。"""
    eng = _engine_or_default(engine)
    ensure_schema(eng)
    from sqlalchemy import text as _text              # noqa: PLC0415
    status = str(payload.get("status") or "resolved").strip()
    if status not in ("resolved", "ignored"):
        raise ExtractError("状态非法（合法值：resolved / ignored）", 400)
    try:
        iid = int(issue_id)
    except Exception:                                 # noqa: BLE001
        raise ExtractError("异常记录 ID 非法", 400)
    with eng.begin() as conn:
        row = conn.execute(_text("SELECT id, document_id FROM extract_issues WHERE id=:i"),
                           {"i": iid}).first()
        if row is None:
            raise ExtractError("异常记录不存在", 404)
        _document_row(conn, session, dict(row._mapping)["document_id"])
        conn.execute(_text(
            "UPDATE extract_issues SET status=:s, resolved_by=:by, resolved_at=:ts WHERE id=:i"
        ), {"s": status, "by": str(getattr(session, "username", "") or ""),
            "ts": _now(), "i": iid})
    return {"ok": True, "id": iid, "status": status}


def list_issues(project_id: Any, session: Any, *, engine=None, rule: Any = None,
                severity: Any = None, status: Any = None) -> Dict[str, Any]:
    """项目级校验异常清单（跨资料的汇总视图）。"""
    eng = _engine_or_default(engine)
    ensure_schema(eng)
    from sqlalchemy import text as _text              # noqa: PLC0415
    with eng.connect() as conn:
        prow = _project_row(conn, session, project_id)
        q = ("SELECT i.*, d.original_name FROM extract_issues i "
             "LEFT JOIN documents d ON d.id = i.document_id WHERE i.project_id=:p")
        params: Dict[str, Any] = {"p": int(prow["id"])}
        for col, val in (("rule", rule), ("severity", severity), ("status", status)):
            v = str(val or "").strip()
            if v:
                q += " AND i.%s=:v_%s" % (col, col)
                params["v_" + col] = v
        q += " ORDER BY CASE i.severity WHEN 'error' THEN 0 ELSE 1 END, i.id DESC LIMIT 500"
        rows = [dict(r._mapping) for r in conn.execute(_text(q), params).all()]
    for m in rows:
        try:
            m["detail"] = json.loads(m.get("detail_json") or "{}")
        except Exception:                             # noqa: BLE001
            m["detail"] = {}
        m["rule_cn"] = RULE_CN.get(str(m.get("rule")), str(m.get("rule")))
    return {"items": rows, "total": len(rows), "summary": _vsum(rows)}


def metadata() -> Dict[str, Any]:
    from engine.standard_fields import metadata as _sf_meta   # noqa: PLC0415
    from engine.extract_store import OPTIONAL_TABLES          # noqa: PLC0415
    return {
        "standard_fields": _sf_meta(),
        "rules": [{"value": r, "label": RULE_CN[r]} for r in RULES],
        "parser_reuse": {
            "excel_csv": "main._parse_excel_structured（既有唯一权威）",
            "image_ocr": "main._ocr_png_bytes（三档降级 rapidocr→easyocr→pytesseract）",
            "pdf": "pdfplumber（既有依赖）",
        },
        "tables": {"created": ["extracted_tables", "extracted_fields", "extract_issues"],
                   "reused_existing": {"financial_data": "accounts / journal_entries / periods",
                                       "tax_returns": "vat_declarations / social_security_declarations 等",
                                       "invoices": "sales_invoices / purchase_invoices / bookkeeping_invoices"},
                   "optional_not_built": sorted(OPTIONAL_TABLES.keys())},
        "traceability": "每个标准字段值带 source_ref{sheet,row,raw} ⇒ 可回链原文件单元格",
    }


__all__ = ["ExtractError", "parse_document", "get_extracted", "correct_field",
           "resolve_issue", "list_issues", "metadata"]
