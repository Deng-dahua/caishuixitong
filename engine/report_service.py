# -*- coding: utf-8 -*-
"""报告生成与交付（P0-7）—— 组装 / 渲染 / 登记 / 下载。

## 复用清单（**一个都不另造**）

| 章节 | 数据来源（唯一权威） |
|---|---|
| 封面 | `report_compliance.document_meta`（报告名）+ `report_store`（本表：文书编号/版本） |
| 免责声明 | `report_identity.identity_line()` + `report_compliance.security_block/compliance_block` |
| 项目概况 | P0-1 `project_service.get_project` |
| 数据来源 | P0-2 `document_service.list_documents` + P0-3 `extract_store.counts` + 载荷 `files_count/read_failures` |
| 风险总览 | P0-5/P0-6 `risk_service.stats`（等级/税种/复核状态/金额分档） |
| 分税种明细 / 重点风险 | P0-5 `rule_executor.collect_from_report`（归一发现）+ `risk_scoring`（排序分） |
| 证据链 | P0-5 同上的 `evidences`（按 `finding_seq` 归属） |
| 法规依据 | P0-5 `rule_catalog.get`（含**占位**标记，如实） |
| 复核记录 | P0-6 `risk_review.states_of`（状态/批注/处置历史/整改编号） |
| 整改建议 | 发现自带 `suggestion` + P0-6 `risk_review.rectifications`（整改台账） |
| 附件 | P0-2 资料清单 + 本次产出的 4 格式文件 + `report_compliance.change_log`（版本历史） |

## 版本登记：**不另写一份**

生成时调 `report_compliance.internal_edition()` ⇒ 版本台账
（`data/report_versions.jsonl`）**唯一权威**照旧登记；本模块只把 `doc_no`
作为**指针**存进 `reports` 表（**不复制**台账字段）。

## 审计：**不新增动作**

复用既有 `report.export`（语义即"报告导出（生成交付件）"）记**生成**，
`report.download` 记**下载**。新增动作会与既有语义重复。

## 时间戳 / 落盘

`runtime_storage.now_cst()`（时间唯一权威）、`atomic_write_bytes()`（字节落盘唯一实现）、
`report_output_root()`（产物目录唯一权威）。
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from engine import legal_mapping as LM          # 法规⇄规则关联（唯一读路径；步骤 19）
from engine import report_render as RENDER
from engine import report_store as STORE
from engine import report_views as VIEWS
# ★ 2026-10-15（用户裁定「涉嫌风险」统一呈现）：报告正文里出现的一切等级词，
#   一律经唯一权威 `risk_levels.display_label` 翻译；**禁止**把结构化字段值
#   （risk_level / by_level 的键）直接写进表格或卡片 —— 那正是本文件三处
#   等级渲染点长期绕过权威、把裸「待核验」印进导出报告的根因（闸门
#   `check_level_display_single_source` 行为级锁死，见 tools/audit_consistency.py）。
from engine.risk_levels import display_label as _display_label


def _conclusion_label(value: Any) -> str:
    """结论等级字段值 → **对外术语**（唯一权威 `config/conclusion_grades.json::term_authority`）。

    「待核」这类裁决语/旧字面是**降级疑点的内部标识**，读者看到的应是术语
    「待核事项」（L2），不是裸标识；L1~L4 显式级直接取 `term_of`。
    取不到映射时**原样返回**（缺失≠编造）。
    """
    s = str(value or "").strip()
    if not s:
        return ""
    try:
        from engine.conclusion_grade import term_of as _term_of
        from engine.conclusion_grade import effective_grade_id as _egid
        if s.upper() in ("L1", "L2", "L3", "L4"):
            return _term_of(s.upper()) or s
        gid, _reg = _egid({"conclusion_grade": s})
        return (_term_of(gid) or s) if gid else s
    except Exception:                                            # noqa: BLE001
        return s

__all__ = ["ReportServiceError", "generate", "get", "list_reports", "versions",
           "download", "metadata", "build_document"]


class ReportServiceError(Exception):
    """报告层错误（`status` 为 HTTP 语义码，由 API 层转 `HTTPException`）。"""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = int(status)


def _boundary(fn):
    """★ **边界唯一转换处**：把下层异常统一翻成 `ReportServiceError`。

    为什么必须有一处（2026-10-13 实测）：`VIEWS`（视图/格式校验）与 `RENDER`（渲染）
    各有自己的异常类型；若不转换，它们会**穿透到 FastAPI ⇒ 500 且无原因**
    （P0-2 / P0-4 / P0-6 各踩过一次同类坑）。装饰在**Service 入口**上 ⇒
    HTTP 调用与**直接调用**两条路径都拿到同一种可解释的错误，不必依赖 API 层。
    """
    import functools as _ft                                  # noqa: PLC0415

    @_ft.wraps(fn)
    def _wrap(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ReportServiceError:
            raise
        except (VIEWS.ReportViewError, RENDER.ReportRenderError) as exc:
            raise ReportServiceError(getattr(exc, "message", str(exc)),
                                     int(getattr(exc, "status", 400))) from exc
    return _wrap


# ══════════════════════════════════════════════════════════════════════════
# 小工具
# ══════════════════════════════════════════════════════════════════════════
def _now() -> str:
    from runtime_storage import now_cst                          # noqa: PLC0415
    return str(now_cst())


def _to_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:                                            # noqa: BLE001
        return default


def _opt_cell(v: Any) -> Any:
    """单元格值：`None`/空 ⇒ `None`（渲染层显示「—」，**不写 0** —— 缺失≠0）。"""
    return v if v not in (None, "") else None


def _money(v: Any) -> Any:
    try:
        return "%,.2f".replace("%,", "").replace("f", "") if False else \
            "{:,.2f}".format(float(v))
    except Exception:                                            # noqa: BLE001
        return None


def _brief(v: Any, limit: int = 400) -> str:
    s = str(v if v is not None else "").strip()
    if limit and len(s) > limit:
        return s[:limit] + "…"      # ★ 截断**可见**（项目铁律）
    return s


def _nk(v: Any) -> str:
    """法名/条号**归一**（去空白 + 去「中华人民共和国」前缀）——仅供**完全等值去重**。"""
    t = "".join(str(v or "").split())
    return t[7:] if t.startswith("中华人民共和国") else t


def _block_para(text: Any) -> Dict[str, Any]:
    return {"type": "paragraph", "text": _brief(text, 4000)}


def _block_kv(items: List[Tuple[str, Any]]) -> Dict[str, Any]:
    return {"type": "kv",
            "items": [{"k": str(k), "v": _opt_cell(v)} for k, v in items]}


def _block_table(columns: List[str], rows: Any,
                 note: str = "") -> Dict[str, Any]:
    """表格块 —— **唯一构造处**。

    ★ 行归一化在此完成（渲染器只认 `[[...]]`）：
      · `tuple`（生成器/`dict.items()` 直传）⇒ `list`；
      · `dict` ⇒ 按列名取值（渲染器也能吃 dict，但**统一在源头归一**更省事）；
      · 标量 ⇒ 单列。
      实测（2026-10-13）：`_sec_rectification` 曾用元组构造行 ⇒ PDF 渲染 `AttributeError`
      （`tuple` 没有 `.get`）。**只修那一处会复发**，故在唯一构造处归一。
    """
    cols = [str(c) for c in columns]
    norm: List[List[Any]] = []
    for row in (rows or []):
        if isinstance(row, list):
            norm.append(row)
        elif isinstance(row, tuple):
            norm.append(list(row))
        elif isinstance(row, dict):
            norm.append([row.get(c) for c in cols])
        else:
            norm.append([row])
    return {"type": "table", "columns": cols, "rows": norm, "note": note}


def _block_list(items: List[Any]) -> Dict[str, Any]:
    return {"type": "list", "items": [str(x) for x in items]}


def _block_note(text: str, level: str = "info") -> Dict[str, Any]:
    return {"type": "note", "text": str(text), "level": level}


# ══════════════════════════════════════════════════════════════════════════
# 取数（全部复用既有 Service）
# ══════════════════════════════════════════════════════════════════════════
def _risk_data(company_id: int, session: Any) -> Dict[str, Any]:
    """风险发现 + 证据 + 执行（唯一来源 = P0-5 归一器；本模块不重算）。"""
    from engine import risk_service as RISK                      # noqa: PLC0415
    return RISK.collect(company_id, session)


def _stats(company_id: int, session: Any) -> Dict[str, Any]:
    from engine import risk_service as RISK                      # noqa: PLC0415
    return RISK.stats(company_id, session)


def _reviews(company_id: int) -> Dict[str, Any]:
    from engine import risk_review as REVIEW                     # noqa: PLC0415
    return REVIEW.states_of(company_id)


def _rectifications(company_id: int) -> List[Dict[str, Any]]:
    from engine import risk_review as REVIEW                     # noqa: PLC0415
    return REVIEW.rectifications(company_id)


def _documents(project_id: Any, session: Any, *, limit: int = 200) -> Dict[str, Any]:
    from engine import document_service as DSVC                  # noqa: PLC0415
    return DSVC.list_documents(project_id, session, page=1, page_size=limit)


def _extract_counts(company_id: int, project_id: Any) -> Dict[str, int]:
    try:
        from engine import extract_store as ESTORE               # noqa: PLC0415
        return ESTORE.artifact_counts(company_id, project_id=project_id)
    except Exception:                                            # noqa: BLE001
        return {"tables": 0, "fields": 0, "issues": 0, "corrected_fields": 0}


def _rule_of(rule_id: Any, redline_id: Any) -> Dict[str, Any]:
    from engine import rule_catalog as CAT                       # noqa: PLC0415
    for rid in (rule_id, redline_id):
        if not rid:
            continue
        try:
            return CAT.get(rid)
        except Exception:                                        # noqa: BLE001
            continue
    return {}


def _latest_analysis_id(project_id: Any) -> str:
    """报告 → 分析作业的单向回指（P0-4）。取不到 ⇒ 空串（**不伪造**）。"""
    try:
        from engine import analysis_task as T                    # noqa: PLC0415
        links = T.jobs_of_project(project_id) or []
        if links:
            return str(links[-1].get("job_id") or "")
    except Exception:                                            # noqa: BLE001
        pass
    return ""


# ══════════════════════════════════════════════════════════════════════════
# 文档组装（12 章节）
# ══════════════════════════════════════════════════════════════════════════
def _sec_cover(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    c, p = ctx["company"], ctx["project"]
    return [
        _block_kv([
            ("报告名称", ctx["name"]),
            ("视图", "%s（%s）" % (ctx["view_label"], ctx["view"])),
            # ★ 2026-10-18（GAP-08）：用**不可见标记**占位，`generate` 拿到台账编号后回填。
            #   旧版直接写 "（尚未登记）"：因为 `build_document` 在版本登记**之前**执行，
            #   于是封面永远显示"（尚未登记）"，而同一份文件的页眉/水印却写着 `RW-… V2`
            #   —— 同一份报告自相矛盾（端到端实测 6.2 抓到）。
            ("文书编号", ctx["doc_no"] or "[[DOC_NO]]"),
            ("版本", ctx["version"] or "[[DOC_VER]]"),
            ("企业名称", c.get("name")),
            ("纳税人识别号", c.get("uscc")),
            ("行业", c.get("industry")),
            ("地区", c.get("region")),
            ("稽查项目", p.get("name")),
            ("项目编号", p.get("code")),
            ("稽查期间", "%s ~ %s" % (ctx["period_start"] or "—", ctx["period_end"] or "—")),
            ("税种范围", "、".join(p.get("tax_scopes") or []) or "—"),
            ("规则版本", ctx["rule_version"] or "—"),
            ("分析作业", ctx["analysis_id"] or "（无关联作业）"),
            ("生成时间", ctx["generated_at"]),
            ("生成人", ctx["generated_by"]),
            ("人工复核状态", ctx["review_label"]),
        ]),
    ]


def _sec_disclaimer(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    d = ctx["disclaimer"]
    blocks = [
        _block_para(d.get("identity_line")),
        _block_kv([
            ("报告性质", d.get("non_enforcement_note")),
            ("保密级别", d.get("security_level")),
            ("使用限制", d.get("security_restriction")),
            ("留存与销毁", d.get("security_retention")),
            ("授权", d.get("authorization")),
            ("免责声明正文", d.get("identity_line")),
        ]),
    ]
    # ★ 2026-10-18（GAP-22）：**行业模板口径声明**。导出链（本模块 → report_render）
    #   用的是 12 节结构，与「一键分析」报告的 9 章结构是两套文档模型，
    #   行业模板（`engine/report_template`）目前只作用于后者。
    #   **要么接进来、要么如实声明** —— 这里选"如实声明"，并且把该行业模板的
    #   重点与章节顺序**照实列出**，让读者自己判断导出件与屏幕件的关系。
    #   （不静默：用户不会以为"导出件也按行业适配过了"。）
    decl = str(ctx.get("template_declaration") or "").strip()
    if decl:
        blocks.append(_block_note(decl))
    return blocks


def _sec_project(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    p = ctx["project"]
    return [
        _block_kv([
            ("项目名称", p.get("name")),
            ("项目编号", p.get("code")),
            ("项目状态", p.get("status_cn") or p.get("status")),
            ("负责人", p.get("owner_name")),
            ("行业", p.get("industry")),
            ("地区", p.get("region")),
            ("稽查期间", "%s ~ %s" % (p.get("period_start") or "—",
                                    p.get("period_end") or "—")),
            ("税种范围", "、".join(p.get("tax_scopes") or []) or "—"),
            ("备注", p.get("remark")),
            ("建档时间", p.get("created_at")),
        ]),
        _block_note("项目信息唯一权威：P0-1 `engine/project_service`（本报告不复制、不改写）。"),
    ]


def _sec_data_source(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    docs = ctx["documents"] or {}
    items = docs.get("items") or []
    rows = [[_brief(d.get("original_name"), 60), d.get("category_cn") or d.get("category"),
             d.get("parse_status_cn") or d.get("parse_status"),
             _money(d.get("size")) or "—", d.get("uploaded_at")]
            for d in items[:ctx["limit"] or 200]]
    ex = ctx["extract_counts"] or {}
    payload = ctx["payload"] or {}
    out = [
        _block_kv([
            ("项目资料份数", docs.get("total")),
            ("已解析表格", ex.get("tables")),
            ("已标准化字段", ex.get("fields")),
            ("人工校正字段", ex.get("corrected_fields")),
            ("校验异常条数", ex.get("issues")),
            ("分析读取的文件数", payload.get("files_count")),
            ("读取失败数", len(payload.get("read_failures") or [])),
        ]),
    ]
    if rows:
        out.append(_block_table(["资料名称", "分类", "解析状态", "大小(字节)", "上传时间"],
                                rows, note="分类与解析状态唯一权威：P0-2/P0-3 各自模块。"))
    else:
        out.append(_block_note("本项目**尚无已上传资料**（或资料未登记），本报告的数据来源为空。",
                               "warn"))
    fails = payload.get("read_failures") or []
    if fails:
        out.append(_block_table(
            ["读取失败的文件", "原因"],
            [[_brief(x if isinstance(x, str) else (x or {}).get("file"), 60),
              _brief((x or {}).get("error") if isinstance(x, dict) else "", 120)]
             for x in fails[:50]],
            note="★ 读取失败**如实列出**，不隐藏。"))
    return out


def _sec_risk_overview(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    st = ctx["stats"] or {}
    if not st.get("available"):
        return [_block_note("风险数据不可用：%s" % (st.get("reason") or "未生成分析产物"), "warn")]
    lv = st.get("by_level") or {}
    tx = st.get("by_tax") or {}
    stt = st.get("by_state_cn") or {}
    band = st.get("by_amount_band") or {}
    amt = st.get("amount_by_band") or {}
    out = [
        _block_kv([
            ("风险事项总数", st.get("total")),
            ("测算涉税金额合计（元）", _money(st.get("amount_total")) or "—"),
            ("金额取不到的条数", st.get("amount_unknown_count")),
            ("待处理金额合计（元）", _money(st.get("pending_amount_total")) or "—"),
            ("已人工复核", st.get("reviewed_total")),
            ("整改台账条数", st.get("rectification_total")),
        ]),
        _block_table(["风险等级", "件数"],
                     [[_display_label(k), v] for k, v in lv.items()],
                     note="等级唯一权威 `engine/risk_levels.py`（5 档）；本报告不重算等级。"),
        _block_table(["复核处置状态", "件数"], [[k, v] for k, v in stt.items()],
                     note="处置状态唯一权威 P0-6 `engine/risk_review.py`。"),
        _block_table(["税种", "件数"], [[k, v] for k, v in list(tx.items())[:30]]),
        _block_table(["金额分档", "件数", "金额合计（元）"],
                     [[k, v, _money(amt.get(k)) or "—"] for k, v in band.items()],
                     note=str((st.get("notes") or {}).get("amount_unknown") or "")),
    ]
    return out


def _findings_by_tax(findings: List[Dict[str, Any]]) -> List[Tuple[str, List[Dict[str, Any]]]]:
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for f in findings:
        taxes = [str(x) for x in (f.get("taxes") or [])] or (
            [str(f.get("tax"))] if f.get("tax") else ["未标注税种"])
        for t in taxes:
            buckets.setdefault(t, []).append(f)
    return sorted(buckets.items(), key=lambda kv: (-len(kv[1]), kv[0]))


def _sec_tax_detail(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    groups = _findings_by_tax(ctx["findings"])
    if not groups:
        return [_block_note("无风险事项，故无分税种明细。")]
    out: List[Dict[str, Any]] = []
    lim = ctx["limit"]
    for tax, fs in groups:
        rows = [[f.get("seq"), _brief(f.get("title"), 70), _display_label(f.get("risk_level")),
                 f.get("priority_score"), _money((ctx["amounts"] or {}).get(f.get("seq")))
                 or "—", (ctx["state_cn"] or {}).get(str(f.get("risk_no")), "待处理")]
                for f in (fs[:lim] if lim else fs)]
        note = ("本税种共 %d 项，本表列出 %d 项（视图条数上限 %s）。"
                % (len(fs), len(rows), lim if lim else "不限"))
        out.append(_block_para("【%s】%s" % (tax, note)))
        out.append(_block_table(
            ["序号", "风险事项", "等级", "排序分", "涉税金额（元）", "复核状态"], rows,
            note="排序分只作排序、**不改等级**；金额取不到的项显示「—」，**未按 0 元计入**。"))
    return out


def _sec_key_risks(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    top = ctx["key_findings"]
    if not top:
        return [_block_note("无风险事项。")]
    out: List[Dict[str, Any]] = []
    for f in top:
        rn = str(f.get("risk_no") or "")
        rv = (ctx["reviews"] or {}).get(rn) or {}
        out.append(_block_para("【%s】%s" % (f.get("seq"), _brief(f.get("title"), 90))))
        out.append(_block_kv([
            ("风险编号", rn),
            ("风险等级", _display_label(f.get("risk_level"))),
            ("结论等级", _conclusion_label(f.get("conclusion_grade"))),
            ("综合排序分", f.get("priority_score")),
            ("涉税金额（测算，元）", _money((ctx["amounts"] or {}).get(f.get("seq"))) or "—"),
            ("税种", "、".join(f.get("taxes") or []) or "—"),
            ("置信度", f.get("confidence")),
            ("复核状态", rv.get("state_cn") or "待处理"),
            ("认定说明", _brief(f.get("verdict"), 300)),
            ("整改建议", _brief(f.get("suggestion"), 400)),
        ]))
    out.append(_block_note("本表按「等级轻重 → 排序分」取前 %d 项（共 %d 项风险事项）。"
                           % (len(top), len(ctx["findings"]))))
    return out


def _sec_evidence(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    evs = ctx["evidences"]
    if not evs:
        return [_block_note("**未归集到证据条目**（不代表无证据，可能是证据未在载荷中登记）"
                            "—— 如实标示，不编造。", "warn")]
    lim = ctx["limit"]
    rows = [[e.get("finding_seq"), e.get("role"), _brief(e.get("name"), 40),
             _brief(e.get("detail"), 90), _brief(e.get("sources"), 70), e.get("status")]
            for e in evs[:lim or len(evs)]]
    out = [_block_table(["所属事项序号", "证据角色", "证据名称", "说明", "来源", "现状"], rows,
                        note="证据唯一来源 P0-5 `rule_executor` 归集结果；本报告不新增证据。")]
    if lim and len(evs) > lim:
        out.append(_block_note("证据共 %d 条，本视图列出前 %d 条（条数上限 %d）。"
                               % (len(evs), lim, lim)))
    return out


def _sec_legal_basis(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """法规依据章 —— **两种口径并列、各自标注来源**（STEP-EXT-LEGAL-FULL-MATCH 步骤 19）。

    ★★ 铁律（防"两个法规依据权威"）：
      · **作者口径** = 规则自己登记的 `legal_basis_ref`（可能为占位）—— 原样呈现；
      · **已确证口径** = 关联表 `config/legal_mappings.json` 里真落到具体条款、
        且**正文库有原文**的引用（含 `provision_id`）—— 追加呈现。
      两者**不互相覆盖**，各自标注状态；报告读者可区分「规则作者写了什么」与
      「已核到什么条款」，不再出现"有引用就当已核实"的假闭环。
    """
    seen, rows, placeholders = set(), [], 0
    lim = ctx["limit"]
    confirmed_n = 0
    for f in ctx["findings"]:
        rule = ctx["rules"].get((str(f.get("rule_id") or ""),
                                 str(f.get("redline_id") or "")))
        if not rule:
            continue
        rid = str(rule.get("rule_id") or "")
        if rid in seen:
            continue
        seen.add(rid)
        # ── ① 已确证条款（关联表唯一权威；含条款 ID 与原文节选）──
        provs = LM.provisions_of(rid)
        for p in provs:
            confirmed_n += 1
            rows.append([rid, _brief(rule.get("name"), 40),
                         _brief(p.get("law"), 30), _brief(p.get("article"), 16),
                         p.get("provision_id") or "—",
                         _brief(p.get("content"), 110) or "（正文库无原文）",
                         "已确证"])
        # ── ② 作者口径（原样；占位一律标注，不得视为已核实）──
        refs = rule.get("legal_basis_ref") or []
        if not refs:
            if not provs:
                rows.append([rid, _brief(rule.get("name"), 40), "（无登记的法规依据）",
                             "", "—", "—", "缺失"])
            continue
        # 已确证的 (法名, 条号) 集合：作者口径中**完全同键**者不再重复列（已在上方展示）；
        # ★ 只做**完全等值**去重，不做模糊配对（"第十一条、第十三条"这类多条引用
        #   无法精确配对 ⇒ 一律保留原样，不猜）。
        _ok_keys = {(_nk(p.get("law")), _nk(p.get("article"))) for p in provs}
        for x in refs:
            if x.get("placeholder"):
                placeholders += 1
            if not x.get("placeholder") and (_nk(x.get("law")), _nk(x.get("article"))) in _ok_keys:
                continue
            rows.append([rid, _brief(rule.get("name"), 40),
                         _brief(x.get("law"), 30),
                         _brief(x.get("article"), 16) or "—",
                         "—", "—",
                         "占位（未入库）" if x.get("placeholder")
                         else ("作者口径（已另有确证条款）" if provs else "未确证（仅作者口径）")])
    if not rows:
        return [_block_note("本次风险事项**未匹配到规则目录中的法规依据**——如实标示，不编造法规。",
                            "warn")]
    out = [_block_table(["规则", "规则名称", "法规", "条文", "条款ID", "条款原文（节选）", "依据状态"],
                        rows[:lim or len(rows)],
                        note=("**两种口径并列**：状态「已确证」= 关联表 `config/legal_mappings.json` "
                              "落到具体条款（`provision_id`）且正文库有原文；「未确证（仅作者口径）」"
                              "= 规则自己写了引用但**无法确证到具体条款**；「占位（未入库）」"
                              "= 候选规则尚未入库 ⇒ **不可作为定性依据**。"))]
    if confirmed_n:
        out.append(_block_note("本轮共 **%d 处**法规依据已确证到具体条款（含条款原文可复核）。"
                               % confirmed_n))
    if placeholders:
        out.append(_block_note(
            "★ 有 %d 处法规依据为**占位值**（候选规则未入库）⇒ 不可作为定性依据引用。"
            % placeholders, "warn"))
    if lim and len(rows) > lim:
        out.append(_block_note("法规依据共 %d 行，本视图列出前 %d 行。" % (len(rows), lim)))
    return out


def _sec_rectification(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    lim = ctx["limit"]
    sug = [[f.get("seq"), _brief(f.get("title"), 50), _brief(f.get("suggestion"), 300)]
           for f in ctx["findings"] if _brief(f.get("suggestion"), 300)]
    if sug:
        out.append(_block_para("一、按风险事项给出的整改建议（%d 项）" % len(sug)))
        out.append(_block_table(["序号", "风险事项", "建议"], sug[:lim or len(sug)],
                                note="建议由引擎按本项证据缺口与规则要求生成，原样呈现、不改写。"))
    rects = ctx["rectifications"]
    if rects:
        out.append(_block_para("二、整改台账（已在系统登记的整改措施与结果）"))
        out.append(_block_table(["整改编号", "风险编号", "整改措施与结果", "登记人", "登记时间"],
                                [[x.get("rectification_no"), x.get("risk_no"),
                                  _brief(x.get("measure"), 200), x.get("author"), x.get("at")]
                                 for x in (rects[:lim] if lim else rects)],
                                note="整改编号唯一权威 `engine/numbering`（WB-RC-…）。"))
    if not out:
        out.append(_block_note("本次无整改建议与整改台账记录。"))
    return out


def _sec_review_record(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    reviews = ctx["reviews"] or {}
    rn_of_findings = [str(f.get("risk_no") or "") for f in ctx["findings"]]
    done = [reviews[rn] for rn in rn_of_findings if rn in reviews and reviews[rn].get("reviewed")]
    out: List[Dict[str, Any]] = [
        _block_kv([
            ("人工复核状态", ctx["review_label"]),
            ("风险事项总数", len(rn_of_findings)),
            ("已产生处置记录的事项", len(done)),
        ]),
    ]
    if not done:
        out.append(_block_note(
            "**本报告未经人工复核**：尚无任何风险事项产生处置记录（确认/排除/误报/已整改/转人工/批注）。"
            "本报告为系统生成的风险线索梳理结果，**不构成对任何事实的定性与对任何税款的核定**。",
            "warn"))
        return out
    rows = []
    for m in done:
        hist = m.get("history") or []
        last = hist[-1] if hist else {}
        rows.append([m.get("risk_no"), m.get("state_cn"),
                     last.get("action_cn") or "", last.get("actor") or "",
                     (last.get("at") or "")[:19], m.get("rectification_no") or "—",
                     _brief((m.get("comments") or [{}])[-1].get("text") if m.get("comments") else "",
                           60)])
    out.append(_block_table(
        ["风险编号", "当前处置状态", "最近动作", "操作人", "时间", "整改编号", "最近批注"], rows,
        note="处置状态与历史唯一权威 P0-6 `engine/risk_review`（append-only 事件流折叠）。"))
    for m in done:
        if m.get("comments"):
            out.append(_block_para("【%s】批注：" % m.get("risk_no")))
            out.append(_block_list(["%s（%s）：%s" % (c.get("author"), (c.get("at") or "")[:19],
                                                     c.get("text"))
                                    for c in m["comments"]]))
    return out


def _sec_attachments(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    docs = ctx["documents"] or {}
    items = docs.get("items") or []
    out: List[Dict[str, Any]] = []
    if items:
        out.append(_block_table(
            ["附件（项目资料）", "分类", "解析状态"],
            [[_brief(d.get("original_name"), 60), d.get("category_cn") or d.get("category"),
              d.get("parse_status_cn") or d.get("parse_status")] for d in items[:200]],
            note="附件清单来自 P0-2 资料登记；原件与解析结果可按需调取。"))
    else:
        out.append(_block_note("本项目暂无附件（资料）。"))
    out.append(_block_para("本次生成的交付件"))
    out.append(_block_table(
        ["格式", "文件名", "水印方式"],
        [[VIEWS.FORMAT_CN[f], ctx["files"].get(f, "（本次未产出）"),
          VIEWS.WATERMARK_METHOD[f] if f in ctx["files"] else "—"]
         for f in VIEWS.FORMATS],
        note="4 种格式**均可导出**；水印均为**真嵌入**（方式如上），不使用 sidecar 冒充。"))
    cl = ctx["change_log"]
    if cl:
        out.append(_block_para("版本历史（同一企业最近若干次登记）"))
        out.append(_block_table(
            ["文书编号", "版本", "报告名称", "生成时间", "复核"],
            [[x.get("doc_no"), x.get("version"), _brief(x.get("doc_name"), 40),
              (x.get("generated_at") or "")[:19], "已复核" if x.get("reviewed") else "未复核"]
             for x in cl],
            note="版本台账唯一权威 `data/report_versions.jsonl`（`engine/report_compliance`）。"))
    return out


#: 空章节的**唯一**原因文案（GAP-21）。
#: ★ 不写"其余/兜底/略"这类含糊词；要说清"为什么没有"，让读者知道下一步做什么。
_EMPTY_SECTION_REASON = "本轮所报资料未产出该章内容，已不列示；补齐相关资料后重新生成即会出现。"


_SECTION_BUILDERS = {
    "cover": _sec_cover,
    "disclaimer": _sec_disclaimer,
    "project": _sec_project,
    "data_source": _sec_data_source,
    "risk_overview": _sec_risk_overview,
    "tax_detail": _sec_tax_detail,
    "key_risks": _sec_key_risks,
    "evidence": _sec_evidence,
    "legal_basis": _sec_legal_basis,
    "rectification": _sec_rectification,
    "review_record": _sec_review_record,
    "attachments": _sec_attachments,
}


# ══════════════════════════════════════════════════════════════════════════
# 组装入口
# ══════════════════════════════════════════════════════════════════════════
def infer_reviewer(findings: List[Dict[str, Any]],
                   reviews: Dict[str, Any]) -> str:
    """从**处置记录**推断复核人 = **最后处置者**（`updated_at` 最新的一条）。

    ★ O9（2026-10-17）：此前取"按发现序遍历到的**第一条**已处置记录" —— 在本账套
      多角色都处置过时（如先税务师后复核专家）会把**先处置者**当成复核人，与
      「复核人」语义不符。现按 `updated_at`（ISO 文本，可直接字符串比较）取最新；
      同刻取遍历到的后者（确定性）。取不到 ⇒ 返回 `""`（**不猜**、不伪造人名）。
    """
    latest_at = ""
    who = ""
    for f in findings or []:
        m = reviews.get(str(f.get("risk_no") or "")) or {}
        if not m.get("reviewed"):
            continue
        at = str(m.get("updated_at") or "")
        if at >= latest_at:
            latest_at = at
            who = str(m.get("updated_by") or "")
    return str(who or "")


@_boundary
def _fill_identity_placeholders(node, doc_no: str, version: str):
    """把封面里的身份占位标记换成真实编号（见 `_sec_cover` 的注释）。

    ★ 用**可见**占位标记 `[[DOC_NO]]`（不用控制字符：`\x01` 会让 python-docx 抛
      `ValueError: All strings must be XML compatible`，实测把报告 API 测试打红）；
      也不匹配"（尚未登记）"字面量 —— 后者可能合法出现在别的章节里，全局替换会误伤。
    """
    repl = {"[[DOC_NO]]": doc_no or "（尚未登记）",
            "[[DOC_VER]]": version or "（尚未登记）"}
    if isinstance(node, str):
        s = node
        for k, v in repl.items():
            if k in s:
                s = s.replace(k, v)
        return s
    if isinstance(node, list):
        return [_fill_identity_placeholders(x, doc_no, version) for x in node]
    if isinstance(node, dict):
        return {k: _fill_identity_placeholders(v, doc_no, version) for k, v in node.items()}
    return node


def build_document(project_id: Any, session: Any, *, view: Any = "full",
                   reviewed: Optional[bool] = None, reviewed_by: str = "",
                   reviewed_note: str = "", company_id: Any = None,
                   engine: Any = None) -> Dict[str, Any]:
    """组装**文档模型**（纯数据，不渲染、不落盘、不登记）。

    `reviewed` 为 `None` ⇒ **按事实推断**：该账套已有任一条风险产生处置记录 ⇒ 视为已复核，
    否则**明确标为未复核**（不得默认"已复核"）。
    """
    from engine import project_service as PSVC                   # noqa: PLC0415
    from engine import risk_service as RISK                      # noqa: PLC0415
    from engine import report_compliance as RC                   # noqa: PLC0415
    from engine import report_identity as IDENT                  # noqa: PLC0415

    view_code = str(view or "full").strip() or "full"
    proj = None
    if project_id not in (None, ""):
        try:
            proj = PSVC.get_project(project_id, session, engine=engine,
                                    with_members=False, with_logs=False)
        except getattr(PSVC, "ProjectError") as exc:
            raise ReportServiceError(getattr(exc, "message", str(exc)),
                                     int(getattr(exc, "status", 404))) from exc
    cid = _to_int(company_id or (proj or {}).get("company_id"), 0)
    if cid <= 0:
        raise ReportServiceError("无法确定账套（请传 project_id 或 company_id）", 400)
    checker = getattr(session, "can_access_company", None)
    if callable(checker) and not checker(cid):
        raise ReportServiceError("账套不存在或无权访问", 404)

    collected = _risk_data(cid, session)
    payload = {}
    try:
        got = RISK.load_payload(cid, session)
        payload = got.get("payload") or {}
    except Exception:                                            # noqa: BLE001
        payload = {}

    findings = collected.get("findings") or []
    stats = _stats(cid, session)
    reviews = _reviews(cid)
    rects = _rectifications(cid)
    docs = _documents((proj or {}).get("id"), session) if proj else {"items": [], "total": 0}
    ex_counts = _extract_counts(cid, (proj or {}).get("id"))

    # 金额（唯一权威 risk_scoring.amount_of）
    from engine import risk_scoring as SCORE                     # noqa: PLC0415
    amounts = {f.get("seq"): SCORE.amount_of(f) for f in findings}

    # 复核状态（不传 ⇒ 按事实）
    done_any = any((reviews.get(str(f.get("risk_no") or "")) or {}).get("reviewed")
                   for f in findings)
    if reviewed is None:
        reviewed = bool(done_any)
    who = str(reviewed_by or "")
    if reviewed and not who:
        # ★ O9：复核人取**最后处置者**（见 `infer_reviewer` 的说明）
        who = infer_reviewer(findings, reviews)
    review_label = ("已复核" + ("（%s）" % who if who else "")
                    if reviewed else "未经人工复核")

    # 规则目录（法规依据）
    rules: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for f in findings:
        key = (str(f.get("rule_id") or ""), str(f.get("redline_id") or ""))
        if key in rules:
            continue
        rules[key] = _rule_of(key[0], key[1])

    # 重点风险：等级重者优先，其次排序分
    from engine.risk_levels import SEVERITY                      # noqa: PLC0415
    key_findings = sorted(
        findings,
        key=lambda f: (-int(SEVERITY.get(str(f.get("risk_level") or ""), -1)),
                       -(SCORE.score(f).get("priority_score") or 0),
                       int(f.get("seq") or 0)))[:VIEWS.KEY_RISK_LIMIT]

    secs = VIEWS.sections_of(view_code)
    ctx: Dict[str, Any] = {
        "view": view_code, "view_label": VIEWS.VIEW_LABEL[view_code],
        "name": VIEWS.name_of(view_code),
        "doc_no": "", "version": "",
        "generated_at": _now(), "generated_by": str(getattr(session, "username", "") or ""),
        "reviewed": bool(reviewed), "reviewed_by": who,
        "review_note": str(reviewed_note or ""), "review_label": review_label,
        "company": {"name": (proj or {}).get("name") or payload.get("target_entity") or
                    "(未命名企业)",
                    "uscc": (proj or {}).get("taxpayer_id") or "",
                    "industry": (proj or {}).get("industry") or payload.get("industry") or "",
                    "region": (proj or {}).get("region") or ""},
        "project": proj or {},
        "period_start": (proj or {}).get("period_start") or "",
        "period_end": (proj or {}).get("period_end") or "",
        "payload": payload, "findings": findings, "evidences": collected.get("evidences") or [],
        "stats": stats, "reviews": reviews, "rectifications": rects,
        "documents": docs, "extract_counts": ex_counts, "rules": rules,
        "amounts": amounts, "key_findings": key_findings,
        "state_cn": {rn: (m or {}).get("state_cn") for rn, m in reviews.items()},
        "rule_version": str(payload.get("rule_version") or ""),
        "analysis_id": _latest_analysis_id((proj or {}).get("id")),
        "change_log": RC.change_log(cid, limit=10),
        "files": {},
        "limit": VIEWS.item_limit_of(view_code),
    }
    # ★ 2026-10-18（GAP-22）：行业模板与导出链的**关系要显式声明**。
    #   事实：行业模板（`engine/report_template`，9 章口径）只作用于一键分析报告；
    #   本模块组装的是 12 节结构的**报告管理/导出**文档模型 ⇒ 行业模板不参与重排。
    #   以前这件事**完全没说**，用户从导出件里看不出"行业适配到底生没生效"。
    #   现在：`out_doc["template_meta"]` 如实登记，并在免责声明章写一段口径声明。
    _tpl_meta, _tpl_decl = _industry_template_meta(ctx["company"].get("industry"))
    ctx["template_declaration"] = _tpl_decl
    # 免责声明（唯一权威）
    sec_blk = RC.security_block("internal_working_paper")
    ctx["disclaimer"] = {
        "identity_line": str(IDENT.identity_line()),
        "non_enforcement_note": str((RC.document_meta("internal_working_paper") or {})
                                    .get("non_enforcement_note") or ""),
        "security_level": str((sec_blk or {}).get("level") or ""),
        "security_restriction": str((sec_blk or {}).get("restriction") or ""),
        "security_retention": str((sec_blk or {}).get("retention") or ""),
        "authorization": str((RC.authorization_block() or {}).get("text")
                             or (RC.authorization_block() or {}).get("note") or ""),
    }
    sections = []
    skipped: List[Dict[str, Any]] = []
    for key in secs:
        builder = _SECTION_BUILDERS.get(key)
        if builder is None:
            continue
        blocks = [b for b in builder(ctx) if not _is_blank(b)]
        # ★ 2026-10-18（GAP-21）：**空章节整章剔除**，并在 `skipped_sections` 里如实登记。
        #   旧口径只丢空块、不丢空章 ⇒ 报告里会出现"只有标题的章节壳"（观感与可信度都受损）。
        #   两种做法都不许"静默"：剔除必须留下原因，渲染层必须写明"本章无内容"，
        #   否则读者会以为是漏印。
        if not blocks:
            skipped.append({"key": key, "title": VIEWS.SECTION_CN[key],
                            "reason": _EMPTY_SECTION_REASON})
            continue
        sections.append({"key": key, "title": VIEWS.SECTION_CN[key], "blocks": blocks})
    out_doc = {
        "name": ctx["name"], "view": view_code, "view_label": ctx["view_label"],
        "doc_no": ctx["doc_no"], "version": ctx["version"],
        "generated_at": ctx["generated_at"], "generated_by": ctx["generated_by"],
        "reviewed": ctx["reviewed"], "reviewed_by": ctx["reviewed_by"],
        "watermark_text": "",
        "company": ctx["company"], "period": {"start": ctx["period_start"],
                                             "end": ctx["period_end"]},
        "project": ctx["project"], "disclaimer": ctx["disclaimer"],
        "sections": sections,
        # ★ 2026-10-18（GAP-21）：**空章节**（本轮无数据，已整章剔除）如实登记 + 给原因。
        #   与 `omitted`（视图按范围裁剪）**语义不同**，不得混用：
        #     · `omitted`  = "这个视图不看这一章"（换视图就有）
        #     · `skipped_sections` = "这一章本轮确实没内容"（换视图也没有，须补数据）
        "skipped_sections": skipped,
        "omitted": [{"key": k, "title": VIEWS.SECTION_CN[k]}
                    for k in VIEWS.omitted_sections_of(view_code)],
        # ★ 2026-10-18（GAP-22）：行业模板与导出链的关系（如实声明，详见
        #   `_industry_template_meta`）。`applied=False` 是**事实**，不是缺陷标记。
        "template_meta": _tpl_meta,
        "counts": {"sections": len(sections), "findings": len(findings),
                   "taxes": len({t for f in findings for t in (f.get("taxes") or [])}),
                   "evidences": len(collected.get("evidences") or []),
                   "reviewed": int(bool(reviewed))},
        "analysis_id": ctx["analysis_id"],
    }
    # ★ 文档模型**自洽**：水印文字在此即算出（`doc_no`/`version` 未知时留空占位），
    #   使 `build_document` 的产物单独拿去渲染也**必然带水印**（不依赖调用方补算）。
    #   `generate` 在拿到台账编号后会**重算一次**（那时才有 doc_no/version）。
    out_doc["watermark_text"] = RENDER.watermark_text_of(out_doc)
    return out_doc


def _industry_template_meta(industry: Any) -> Tuple[Dict[str, Any], str]:
    """行业模板与**本导出链**的关系（GAP-22，唯一实现）。

    返回 `(meta, declaration_text)`：
      · `meta.applied` 恒为 `False` 并写明原因 —— 本链走 12 节结构，
        行业模板的 9 章重排**不适用**（不是"忘了接"，是两套文档模型）；
      · 适配信息（是否匹配、重点、9 章顺序）**照实列出**，供读者对照；
      · 行业匹配不上 ⇒ 明说"按通用结构"，不冒用别行业模板（与模板模块铁律一致）。
    """
    meta: Dict[str, Any] = {"industry": str(industry or ""), "applied": False,
                            "matched": False, "template_id": "", "emphasis": "",
                            "sections": [], "reason": ""}
    decl = ""
    try:
        from engine import report_template as RT                 # noqa: PLC0415
        tpl = RT.template_of(str(industry or ""))
        meta["matched"] = bool(tpl)
        meta["template_id"] = str(tpl.get("template_id") or "")
        meta["emphasis"] = str(tpl.get("emphasis") or "")
        meta["sections"] = list(RT.section_order(str(industry or "")) or [])
        meta["reason"] = ("本导出件按 12 节通用结构装配，行业模板的 9 章重排只适用于"
                          "「一键分析」报告；行业模板的适配信息见 meta，导出件不重排章节。")
        if tpl:
            decl = ("行业模板口径：本导出件按 12 节通用结构装配，未按行业模板重排章节"
                    "（行业模板仅作用于「一键分析」报告）。本次识别行业「%s」，"
                    "该行业模板重点为「%s」。需要行业适配版请使用「一键分析」报告。"
                    % (str(industry or "（未识别）"), meta["emphasis"] or "（模板未登记重点）"))
        else:
            decl = ("行业模板口径：未匹配到「%s」的行业模板，本导出件按通用结构装配；"
                    "不冒用其他行业模板。" % (str(industry or "（未填行业）")))
    except Exception as exc:                                     # noqa: BLE001
        # 取不到就如实说"不可得"，不留空让人猜
        meta["reason"] = "行业模板信息不可得：%s" % exc
        decl = "行业模板口径：行业模板信息读取失败（%s），本导出件按通用结构装配。" % exc
    return meta, decl


def _is_blank(b: Dict[str, Any]) -> bool:
    """丢弃**空块**（空段落/空表/空 kv）—— 不留空壳。"""
    t = str(b.get("type") or "")
    if t == "paragraph":
        return not str(b.get("text") or "").strip()
    if t == "kv":
        return not [x for x in (b.get("items") or []) if x.get("v") not in (None, "")]
    if t == "table":
        return not (b.get("columns") and b.get("rows"))
    if t == "list":
        return not (b.get("items") or [])
    if t == "note":
        return not str(b.get("text") or "").strip()
    return True


# ══════════════════════════════════════════════════════════════════════════
# 生成（渲染 + 落盘 + 版本登记 + 登记表 + 审计）
# ══════════════════════════════════════════════════════════════════════════
@_boundary
def generate(project_id: Any, session: Any, *, view: Any = "full",
             formats: Any = None, reviewed: Optional[bool] = None,
             reviewed_by: str = "", reviewed_note: str = "", change_note: str = "",
             with_attachments: bool = True, request: Any = None,
             engine: Any = None) -> Dict[str, Any]:
    """生成报告：渲染 4 格式 ⇒ 落盘 ⇒ 登记版本台账 ⇒ 登记 `reports` ⇒ 审计。"""
    import time as _time

    from engine import report_compliance as RC                   # noqa: PLC0415
    from runtime_storage import (atomic_write_bytes,             # noqa: PLC0415
                                 report_output_root)

    t0 = _time.time()
    fmts = VIEWS.validate_formats(formats)
    doc = build_document(project_id, session, view=view, reviewed=reviewed,
                         reviewed_by=reviewed_by, reviewed_note=reviewed_note,
                         engine=engine)
    cid = _to_int((doc.get("project") or {}).get("company_id"), 0)
    pid = _to_int((doc.get("project") or {}).get("id"), 0)

    # ── ① 版本登记（**唯一权威** report_compliance ⇒ 拿 doc_no / version）──
    try:
        edition = RC.internal_edition(
            {"document_meta": RC.document_meta("internal_working_paper")},
            company_id=cid,
            reviewed=bool(doc.get("reviewed")),
            generated_at=doc.get("generated_at"),
            change_note=(str(change_note or "").strip() or
                         "生成报告（视图：%s）。" % doc.get("view_label")),
            analysis_id=str(doc.get("analysis_id") or ""))
        rec = edition.get("version_record") or {}
    except Exception as exc:                                     # noqa: BLE001
        raise ReportServiceError("版本登记失败（%s）：%s" % (type(exc).__name__, exc), 500) from exc
    doc["doc_no"] = str(rec.get("doc_no") or "")
    doc["version"] = str(rec.get("version") or "")
    doc["watermark_text"] = RENDER.watermark_text_of(doc)
    # ★ 回填封面占位（见 `_sec_cover`）：文书编号/版本在登记之后才有值
    doc = _fill_identity_placeholders(doc, doc["doc_no"], doc["version"])

    # ── ② 渲染（免责声明缺失/被顶替 ⇒ 此处即抛错，不产报告）──
    outdir = os.path.join(report_output_root(), str(cid))
    files: Dict[str, str] = {}
    modes: Dict[str, str] = {}
    rendered: Dict[str, bytes] = {}
    for f in fmts:
        data, mode = RENDER.render(doc, f)
        rendered[f] = data
        modes[f] = mode
        name = RENDER.filename_of(doc, f)
        # 文件名已去路径分隔符（见 filename_of）；仍做一次兜底，防越界写
        name = os.path.basename(name)
        path = os.path.join(outdir, name)
        atomic_write_bytes(path, data)
        files[f] = os.path.relpath(path, report_output_root()).replace(os.sep, "/")

    # 附件章节需要"本次产出文件" ⇒ 用产出后的 files 重渲染（只在含 attachments 时做一次）
    if with_attachments and "attachments" in VIEWS.sections_of(doc.get("view")):
        doc2 = _replace_attachments(doc, files)
        for f in fmts:
            data, mode = RENDER.render(doc2, f)
            rendered[f] = data
            atomic_write_bytes(os.path.join(outdir, os.path.basename(
                RENDER.filename_of(doc, f))), data)
        doc = doc2

    # ── ③ 登记 reports 表（只存**新维度**；doc_no 是指向台账的指针）──
    STORE.ensure_schema(engine) if engine is not None else STORE.ensure_schema()
    row = _insert_report(doc, project_id=pid, company_id=cid, files=files,
                         modes=modes, change_note=change_note, engine=engine)

    # ── ④ 审计（复用既有 report.export —— 语义即"报告导出（生成交付件）"）──
    _audit("report.export", doc, cid,
           "生成报告：视图「%s」、格式 %s、风险 %d 项、文书编号 %s（版本 %s）；"
           "复核状态：%s"
           % (doc.get("view_label"), "、".join(VIEWS.FORMAT_CN[f] for f in fmts),
              doc["counts"]["findings"], doc["doc_no"], doc["version"],
              "已复核" if doc.get("reviewed") else "未经人工复核"),
           request)

    elapsed = round(_time.time() - t0, 3)
    out = dict(row)
    out["doc_no"] = doc["doc_no"]
    out["version"] = doc["version"]
    out["name"] = doc["name"]
    out["files"] = files
    out["bytes"] = {f: len(rendered[f]) for f in fmts}
    out["watermark_mode"] = modes
    out["elapsed_seconds"] = elapsed
    out["disclaimer_present"] = True          # 渲染层已强制；此处为回执可读性
    out["omitted_sections"] = doc.get("omitted") or []
    out["message"] = ("报告已生成：%s（%s），格式 %s，耗时 %.2f 秒。"
                      % (doc["name"], doc["version"],
                         "、".join(VIEWS.FORMAT_CN[f] for f in fmts), elapsed))
    return out


def _replace_attachments(doc: Dict[str, Any], files: Dict[str, str]) -> Dict[str, Any]:
    """把「本次生成的交付件」清单回填进附件章节后重渲染（**只改该节**）。"""
    import copy as _copy
    d = _copy.deepcopy(doc)
    for sec in d.get("sections") or []:
        if str(sec.get("key")) != "attachments":
            continue
        for b in sec.get("blocks") or []:
            if str(b.get("type")) != "table":
                continue
            cols = [str(c) for c in (b.get("columns") or [])]
            if cols[:1] == ["格式"]:
                b["rows"] = [[VIEWS.FORMAT_CN[f], files.get(f, "（本次未产出）"),
                              VIEWS.WATERMARK_METHOD[f] if f in files else "—"]
                             for f in VIEWS.FORMATS]
    return d


def _insert_report(doc: Dict[str, Any], *, project_id: int, company_id: int,
                   files: Dict[str, str], modes: Dict[str, str],
                   change_note: str, engine: Any) -> Dict[str, Any]:
    from sqlalchemy import text as _sql                         # noqa: PLC0415
    from engine.report_store import _default_engine              # noqa: PLC0415
    eng = engine if engine is not None else _default_engine()
    STORE.ensure_schema(eng)
    params = {
        "doc_no": doc.get("doc_no") or "", "ver": doc.get("version") or "",
        "pid": project_id, "cid": company_id,
        "view": doc.get("view") or "", "name": doc.get("name") or "",
        "p0": (doc.get("period") or {}).get("start") or "",
        "p1": (doc.get("period") or {}).get("end") or "",
        "rv": 1 if doc.get("reviewed") else 0,
        "rvb": str(doc.get("reviewed_by") or ""),
        "wm_mode": ",".join(modes.get(f, "") for f in sorted(modes)),
        "wm_text": doc.get("watermark_text") or "",
        "fmts": json.dumps(sorted(files), ensure_ascii=False),
        "files": json.dumps(files, ensure_ascii=False),
        "sec": int((doc.get("counts") or {}).get("sections") or 0),
        "fc": int((doc.get("counts") or {}).get("findings") or 0),
        "tc": int((doc.get("counts") or {}).get("taxes") or 0),
        "om": json.dumps([x.get("key") for x in (doc.get("omitted") or [])],
                         ensure_ascii=False),
        "at": doc.get("generated_at") or "", "by": doc.get("generated_by") or "",
        "aid": str(doc.get("analysis_id") or ""),
        "note": str(change_note or ""), "st": "ready",
    }
    with eng.begin() as conn:
        new_id = conn.execute(_sql(
            "INSERT INTO reports (doc_no, version, project_id, company_id, view, name, "
            "period_start, period_end, reviewed, reviewed_by, watermark_mode, "
            "watermark_text, formats, files, section_count, finding_count, tax_count, "
            "omitted_sections, generated_at, generated_by, analysis_id, change_note, status) "
            "VALUES (:doc_no,:ver,:pid,:cid,:view,:name,:p0,:p1,:rv,:rvb,:wm_mode,:wm_text,"
            ":fmts,:files,:sec,:fc,:tc,:om,:at,:by,:aid,:note,:st) RETURNING id"
        ), params).scalar()
        row = conn.execute(_sql("SELECT * FROM reports WHERE id=:i"),
                           {"i": int(new_id)}).mappings().first()
    return _row_out(dict(row) if row else {"id": new_id})


def _row_out(r: Dict[str, Any]) -> Dict[str, Any]:
    """行 → 接口可读形状（JSON 字段还原；**不隐藏任何字段**）。"""
    o = dict(r or {})
    for k in ("formats", "files", "omitted_sections"):
        v = o.get(k)
        if isinstance(v, str) and v.strip():
            try:
                o[k] = json.loads(v)
            except Exception:                                    # noqa: BLE001
                o[k] = []
        elif v is None:
            o[k] = []
    o["reviewed"] = bool(o.get("reviewed"))
    o["formats_cn"] = [VIEWS.FORMAT_CN.get(f, f) for f in (o.get("formats") or [])]
    o["view_label"] = VIEWS.VIEW_LABEL.get(str(o.get("view") or ""), "")
    return o


def _audit(action: str, doc: Dict[str, Any], company_id: Any, detail: str,
           request: Any = None, session: Any = None) -> None:
    """薄转发 `audit_trail.record`（**不吞异常**；操作人显式给出）。"""
    from engine.audit_trail import record as _rec                # noqa: PLC0415
    uid = getattr(session, "user_id", None) if session is not None else None
    uname = (str(getattr(session, "username", "") or "") if session is not None
             else str(doc.get("generated_by") or ""))
    _rec(action, target=str(doc.get("doc_no") or doc.get("name") or ""),
         company_id=(int(company_id) or None), detail=detail, request=request,
         user_id=(int(uid) if uid not in (None, "") else None),
         user_name=(uname or None))


# ══════════════════════════════════════════════════════════════════════════
# 查询 / 下载
# ══════════════════════════════════════════════════════════════════════════
def _require_company(company_id: Any, session: Any) -> int:
    try:
        cid = int(company_id)
    except Exception:                                            # noqa: BLE001
        raise ReportServiceError("company_id 非法", 400) from None
    if cid <= 0:
        raise ReportServiceError("company_id 非法", 400)
    checker = getattr(session, "can_access_company", None)
    if callable(checker) and not checker(cid):
        raise ReportServiceError("报告不存在或无权访问", 404)     # 不泄露存在性
    return cid


def _fetch(report_id: Any, session: Any, *, engine: Any = None) -> Dict[str, Any]:
    """按 `reportId` 取一行。

    ★ 支持两种身份：**文书编号 `doc_no`**（版本台账权威，跨系统稳定）或
      `reports.id`（本表主键）。用主键时**必须**同时满足租户可见（下同）。
    """
    from sqlalchemy import text as _sql                         # noqa: PLC0415
    from engine.report_store import _default_engine              # noqa: PLC0415
    rid = str(report_id or "").strip()
    if not rid:
        raise ReportServiceError("报告标识不能为空", 400)
    eng = engine if engine is not None else _default_engine()
    STORE.ensure_schema(eng)
    with eng.connect() as conn:
        row = None
        if rid.isdigit():
            row = conn.execute(_sql("SELECT * FROM reports WHERE id=:i"),
                               {"i": int(rid)}).mappings().first()
        if row is None:
            row = conn.execute(_sql(
                "SELECT * FROM reports WHERE doc_no=:d ORDER BY id DESC LIMIT 1"),
                {"d": rid}).mappings().first()
    if row is None:
        raise ReportServiceError("报告不存在：%s（可能尚未生成）" % rid, 404)
    out = _row_out(dict(row))
    _require_company(out.get("company_id"), session)
    return out


@_boundary
def get(report_id: Any, session: Any, *, engine: Any = None) -> Dict[str, Any]:
    """报告详情（登记信息 + 版本台账（唯一权威）读回 + 可下载格式）。"""
    out = _fetch(report_id, session, engine=engine)
    cid = _to_int(out.get("company_id"), 0)
    try:
        from engine import report_compliance as RC               # noqa: PLC0415
        ledger = [x for x in RC.change_log(cid, limit=200)
                  if str(x.get("doc_no") or "") == str(out.get("doc_no") or "")]
    except Exception:                                            # noqa: BLE001
        ledger = []
    out["version_record"] = (ledger[0] if ledger else {})
    out["version_in_ledger"] = bool(ledger)
    out["available_formats"] = [f for f in VIEWS.FORMATS if f in (out.get("files") or {})]
    out["download_urls"] = {f: "/api/v1/reports/%s/download?format=%s"
                            % (out.get("doc_no") or out.get("id"), f)
                            for f in out["available_formats"]}
    out["note"] = ("报告文件由本系统生成并**真嵌入水印**（含人工复核标识）；"
                   "版本与文书编号唯一权威 `data/report_versions.jsonl`。"
                   + ("" if ledger else " ⚠ 已在登记表中但**台账未找到对应行** —— 如实标示。"))
    return out


@_boundary
def list_reports(session: Any, *, project_id: Any = None, company_id: Any = None,
                 view: Any = None, page: int = 1, page_size: int = 20,
                 engine: Any = None) -> Dict[str, Any]:
    """报告列表（按项目或账套；分页倒序）。"""
    from sqlalchemy import text as _sql                         # noqa: PLC0415
    from engine.report_store import _default_engine              # noqa: PLC0415
    eng = engine if engine is not None else _default_engine()
    STORE.ensure_schema(eng)
    where, params = [], {}
    if company_id not in (None, ""):
        params["cid"] = _require_company(company_id, session)
        where.append("company_id = :cid")
    if project_id not in (None, ""):
        params["pid"] = _to_int(project_id)
        where.append("project_id = :pid")
    v = str(view or "").strip()
    if v:
        params["view"] = VIEWS._validate_view(v)                 # noqa: SLF001
        where.append("view = :view")
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    try:
        pg = max(1, int(page)); ps = max(1, min(int(page_size), 200))
    except Exception:                                            # noqa: BLE001
        pg, ps = 1, 20
    with eng.connect() as conn:
        rows = conn.execute(_sql(
            "SELECT * FROM reports%s ORDER BY id DESC LIMIT :lim OFFSET :off"
            % clause), dict(params, lim=ps, off=(pg - 1) * ps)).mappings().all()
        total = int(conn.execute(_sql("SELECT COUNT(*) FROM reports%s" % clause),
                                 params).scalar() or 0)
    if not (company_id not in (None, "")) and not (project_id not in (None, "")):
        # 未给范围 ⇒ 只返回**当前用户可见账套**的行（不泄露他人数据）
        allowed = {int(x) for x in (getattr(session, "allowed_company_ids", ()) or ())}
        if not getattr(session, "is_admin", False):
            rows = [r for r in rows if int(r["company_id"]) in allowed]
            total = len(rows)
    items = [_row_out(dict(r)) for r in rows]
    viewed = [f for f in VIEWS.FORMATS if f in (items[0].get("files") if items else {})]
    return {"items": items, "total": total, "page": pg, "page_size": ps,
            "pages": (total + ps - 1) // ps if total else 0,
            "formats_seen": viewed,
            "note": ("报告列表来自 `reports` 表（**交付物登记**）；"
                     "文书编号/版本以 `data/report_versions.jsonl` 为唯一权威。")}


@_boundary
def versions(company_id: Any, session: Any) -> Dict[str, Any]:
    """某账套的报告**版本台账**（唯一权威 `report_compliance.change_log`）。"""
    from engine import report_compliance as RC                   # noqa: PLC0415
    cid = _require_company(company_id, session)
    return {"company_id": cid, "items": RC.change_log(cid, limit=200),
            "note": "版本台账唯一权威 `data/report_versions.jsonl`（append-only）。"}


@_boundary
def download(report_id: Any, session: Any, *, fmt: Any = "pdf",
             request: Any = None, engine: Any = None) -> Tuple[bytes, str, Dict[str, str]]:
    """取回已生成的报告文件 ⇒ `(bytes, filename, headers)`。

    ★ **重新生成会改版本号**，故下载一律**取已落盘的原件**（不重渲染）；
      文件缺失 ⇒ 明确报错（提示重新生成），**不静默用新版本顶替**。
    """
    from runtime_storage import report_output_root               # noqa: PLC0415
    f = VIEWS.validate_format(fmt)
    out = _fetch(report_id, session, engine=engine)
    files = out.get("files") or {}
    rel = str(files.get(f) or "")
    if not rel:
        raise ReportServiceError(
            "该报告未产出 %s 格式（已产出：%s）—— 请按该格式重新生成"
            % (VIEWS.FORMAT_CN[f],
               "、".join(VIEWS.FORMAT_CN.get(x, x) for x in files) or "无"), 404)
    root = os.path.abspath(report_output_root())
    path = os.path.abspath(os.path.join(root, rel))
    if not path.startswith(root + os.sep):
        raise ReportServiceError("报告路径非法（越界）", 400)
    if not os.path.exists(path):
        raise ReportServiceError(
            "报告文件已不存在（%s）—— 请重新生成报告（**不以新版本顶替**）" % rel, 404)
    with open(path, "rb") as fh:
        data = fh.read()
    fname = os.path.basename(path)
    from urllib.parse import quote as _quote                     # noqa: PLC0415
    headers = {
        "Content-Disposition": "attachment; filename*=UTF-8''%s" % _quote(fname),
        "X-Watermark-Mode": "embedded",          # 4 格式均真嵌入（见 report_views）
        "X-Watermark-Method": VIEWS.WATERMARK_METHOD[f],
        "X-Watermark-Text-Encoding": "percent-utf8",
        "X-Watermark-Text": _quote(str(out.get("watermark_text") or "")),
        "X-Report-No": str(out.get("doc_no") or ""),
        "X-Report-Version": str(out.get("version") or ""),
        "X-Review-Status": "reviewed" if out.get("reviewed") else "not_reviewed",
    }
    # 审计：下载
    _audit("report.download", out, out.get("company_id"),
           "下载报告：格式 %s、文件 %s、文书编号 %s（版本 %s）"
           % (VIEWS.FORMAT_CN[f], fname, out.get("doc_no"), out.get("version")),
           request, session)
    return data, fname, headers


def metadata() -> Dict[str, Any]:
    """字典（视图/格式/章节 + 口径说明）。"""
    m = VIEWS.metadata()
    m["storage"] = {"output_root": "runtime_storage.report_output_root()",
                    "registry_table": "reports（交付物登记）",
                    "version_ledger": "data/report_versions.jsonl（唯一权威）"}
    m["audit"] = {"generate": "report.export（复用既有动作）",
                  "download": "report.download（复用既有动作）"}
    m["disclaimer_source"] = ("engine/report_identity.identity_line() + "
                              "engine/report_compliance（非执法声明/保密级别）")
    return m
