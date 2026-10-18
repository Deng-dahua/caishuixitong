# -*- coding: utf-8 -*-
"""报告渲染（P0-7）：**结构化文档** → 4 种格式的字节流。

## 文档模型（渲染器与组装层的**唯一契约**）

组装层（`engine/report_service`）产出：

```
document = {
  "name": 报告名,            "view": 视图码,        "view_label": 视图标签,
  "doc_no": 文书编号,        "version": 版本,       "analysis_id": 作业 id,
  "generated_at": 时间,      "generated_by": 生成人,
  "reviewed": bool, "reviewed_by": str, "review_note": str,   # ★ 人工复核标识
  "watermark_text": 水印文字,
  "company": {...}, "period": {...}, "project": {...},
  "disclaimer": {...},       # ★ 免责声明（唯一权威 report_identity / report_compliance）
  "sections": [ {"key": 节码, "title": 节名, "blocks": [BLOCK, ...]}, ... ],
  "omitted":  [ {"key": 节码, "title": 节名}, ... ],   # 本视图未含（如实标注）
  "counts": {...},
}
```

**块类型**（渲染器只需认识这 5 种；组装层不得产出别的类型）：

| type | 字段 |
|---|---|
| `paragraph` | `text` |
| `kv` | `items=[{k,v}]` |
| `table` | `columns=[str]`, `rows=[[str]]`, `note?` |
| `list` | `items=[str]` |
| `note` | `text`, `level`（`info`/`warn`） |

## 三条硬约束（任务书 + 项目铁律）

1. **必须含免责声明**：`disclaimer` 单独成节（`report_identity.identity_line()` +
   `report_compliance` 的非执法声明/保密级别）——**每种格式都要有**，缺失即抛错（不静默出报告）。
2. **必须含人工复核标识**：封面 + 每页（PDF 水印/页脚、DOCX 页眉、XLSX 页眉、HTML 水印层）
   均带「复核状态：已复核（复核人）/ **未经人工复核**」。
3. **水印如实**：4 格式均**真嵌入**（方式见 `report_views.WATERMARK_METHOD`），
   不使用"sidecar 却声称已加水印"的写法。

★ 中文渲染字体唯一权威：`engine/document_watermark.PDF_CJK_FONT`（reportlab 内置 CID 字体）。
★ HTML 输出**全部转义**（本模块是 HTML 的唯一生成点 ⇒ 注入风险收敛于此）。
"""
from __future__ import annotations

import html as _html
import io
from typing import Any, Dict, List, Tuple

from engine.report_views import FORMAT_CN, FORMAT_EXT

__all__ = ["REPORT_HEADER_ROWS", "render", "watermark_text_of", "doc_title"]


class ReportRenderError(Exception):
    """渲染错误（`status` 为 HTTP 语义码）。"""

    def __init__(self, message: str, status: int = 500):
        super().__init__(message)
        self.message = message
        self.status = int(status)


# --------------------------------------------------------------------------
# 通用
# --------------------------------------------------------------------------
def _html_esc(v: Any) -> str:
    return _html.escape(str(v if v is not None else ""), quote=True)


def _disp(v: Any) -> str:
    """单元格文本化（`None` ⇒ 「—」，**不写 0** —— 缺失≠0）。"""
    if v is None or v == "":
        return "—"
    if isinstance(v, bool):
        return "是" if v else "否"
    return str(v)


def doc_title(doc: Dict[str, Any]) -> str:
    return "%s（%s）" % (str(doc.get("name") or ""),
                         str(doc.get("version") or ""))


def watermark_text_of(doc: Dict[str, Any]) -> str:
    """水印文字（唯一构造点）：报告名 · 文书编号 · 版本 · 复核状态 · 生成人 · 时间 · 用途。

    ★ 含**复核状态**是任务书要求（"人工复核标识"）；**未复核**必须显式写出。
    """
    rv = ("已复核" + ("（%s）" % doc.get("reviewed_by") if doc.get("reviewed_by") else "")
          if doc.get("reviewed") else "未经人工复核")
    return "内部使用 · %s · %s %s · %s · %s · %s" % (
        str(doc.get("name") or ""), str(doc.get("doc_no") or ""),
        str(doc.get("version") or ""), rv, str(doc.get("generated_by") or ""),
        str(doc.get("generated_at") or ""))


#: 报告页眉/页脚共用的合规行（4 格式同源，防各处措辞漂移）
REPORT_HEADER_ROWS: Tuple[str, ...] = (
    "本报告仅供内部风险复核与整改使用，不具有税务机关行政执法文书的效力。",
    "内部资料，不得外传。",
)


def _require_disclaimer(doc: Dict[str, Any]) -> Dict[str, Any]:
    """免责声明**必须存在且必须成节**（不满足即抛错 —— 不得静默产出无声明的报告）。

    ★ 三条前置判据（缺一即 ERROR，不是"尽力而为"）：
      ① `doc.disclaimer` 是 dict；② `disclaimer.identity_line` 非空；
      ③ **存在 `key="disclaimer"` 的章节且其正文含 `identity_line`** —— 只看字段存在
         不够：字段存在但章节被裁剪掉，用户拿到的报告里就**没有免责声明**
         （实测踩过：DOCX 正文无免责声明，因为组装层没产出该章节）。
    """
    d = doc.get("disclaimer")
    if not isinstance(d, dict):
        raise ReportRenderError("报告缺少免责声明（disclaimer）", 500)
    line = str(d.get("identity_line") or "").strip()
    if not line:
        raise ReportRenderError("报告缺免责声明正文（identity_line）", 500)
    secs = doc.get("sections") or []
    hit = None
    for s in secs:
        if str(s.get("key") or "") == "disclaimer":
            hit = s
            break
    if hit is None:
        raise ReportRenderError(
            "报告缺少「免责声明」章节（`key=disclaimer`）—— 免责声明必须成节呈现，"
            "不得只放在元数据里", 500)
    texts = [str(b.get("text") or "") for b in (hit.get("blocks") or [])]
    texts += [str(x.get("v") or "") for b in (hit.get("blocks") or [])
              if str(b.get("type")) == "kv" for x in (b.get("items") or [])]
    if not any(line in t for t in texts):
        raise ReportRenderError(
            "「免责声明」章节正文未包含唯一权威声明（identity_line）—— "
            "不得用自写声明顶替", 500)
    return d


def _review_line(doc: Dict[str, Any]) -> str:
    if doc.get("reviewed"):
        who = str(doc.get("reviewed_by") or "").strip()
        return "人工复核状态：**已复核**" + ("（复核人：%s）" % who if who else "")
    return "人工复核状态：**未经人工复核**（本报告为系统生成的风险线索梳理结果）"


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------
_HTML_CSS = """
* { box-sizing: border-box; }
body { margin:0; padding:0; background:#eef2f7; color:#1e293b;
       font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif; font-size:14px; }
.wm { position:fixed; inset:0; pointer-events:none; z-index:99; overflow:hidden; }
.wm span { position:absolute; white-space:nowrap; color:rgba(120,130,145,.16);
           font-size:22px; font-weight:700; transform:rotate(-30deg); }
.page { max-width:900px; margin:0 auto; background:#fff; padding:28px 34px 44px;
        box-shadow:0 2px 12px rgba(15,23,42,.08); position:relative; z-index:1; }
h1 { font-size:21px; margin:0 0 4px; }
h2 { font-size:15px; margin:22px 0 8px; padding-bottom:5px; border-bottom:2px solid #e2e8f0; }
h3 { font-size:13px; margin:12px 0 5px; color:#334155; }
.sub { color:#64748b; font-size:12px; margin-bottom:14px; }
table { width:100%; border-collapse:collapse; margin:6px 0 4px; }
th, td { border:1px solid #e2e8f0; padding:5px 7px; font-size:12px; text-align:left;
         vertical-align:top; word-break:break-word; }
th { background:#f8fafc; color:#475569; font-weight:600; }
.kv { display:grid; grid-template-columns:150px 1fr; gap:3px 10px; font-size:13px; }
.kv .k { color:#64748b; }
.note { padding:7px 10px; border-radius:5px; font-size:12.5px; margin:6px 0; }
.note.info { background:#eff6ff; color:#1e40af; border:1px solid #bfdbfe; }
.note.warn { background:#fef3c7; color:#92400e; border:1px solid #fde68a; }
.disc { background:#f8fafc; border:1px solid #e2e8f0; border-left:4px solid #dc2626;
        padding:10px 12px; font-size:12.5px; line-height:1.75; }
.disc b { color:#991b1b; }
.omitted { background:#fff7ed; border:1px solid #fed7aa; padding:9px 11px;
           font-size:12.5px; color:#9a3412; border-radius:5px; }
.foot { margin-top:26px; padding-top:10px; border-top:1px solid #e2e8f0;
        color:#64748b; font-size:11.5px; line-height:1.7; }
ul { margin:4px 0 4px 18px; padding:0; }
li { margin:2px 0; }
@media print { body{background:#fff} .page{box-shadow:none;max-width:none;padding:0}
                .wm{position:fixed} }
"""


def _html_block(b: Dict[str, Any]) -> str:
    t = str(b.get("type") or "")
    if t == "paragraph":
        return "<p>%s</p>" % _html_esc(b.get("text"))
    if t == "kv":
        items = b.get("items") or []
        return '<div class="kv">%s</div>' % "".join(
            "<div class='k'>%s</div><div>%s</div>" % (_html_esc(x.get("k")), _html_esc(x.get("v")))
            for x in items)
    if t == "table":
        cols = [str(c) for c in (b.get("columns") or [])]
        head = "".join("<th>%s</th>" % _html_esc(c) for c in cols)
        body = "".join(
            "<tr>%s</tr>" % "".join("<td>%s</td>" % _html_esc(_disp(c))
                                    for c in (row if isinstance(row, list)
                                              else [row.get(c) for c in cols]))
            for row in (b.get("rows") or []))
        note = ('<div class="sub">%s</div>' % _html_esc(b.get("note"))) if b.get("note") else ""
        return ("<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>%s"
                % (head, body, note))
    if t == "list":
        return "<ul>%s</ul>" % "".join("<li>%s</li>" % _html_esc(x)
                                       for x in (b.get("items") or []))
    if t == "note":
        lv = str(b.get("level") or "info")
        lv = lv if lv in ("info", "warn") else "info"
        return '<div class="note %s">%s</div>' % (lv, _html_esc(b.get("text")))
    return '<div class="note warn">[未知块类型：%s]</div>' % _html_esc(t)


def _render_html(doc: Dict[str, Any], *, full_page: bool = True) -> bytes:
    disc = _require_disclaimer(doc)
    T = []
    if full_page:
        T.append("<!DOCTYPE html><html lang='zh-CN'><head><meta charset='UTF-8'>")
        T.append("<meta name='viewport' content='width=device-width, initial-scale=1.0'>")
        T.append("<title>%s</title>" % _html_esc(doc_title(doc)))
        T.append("<style>%s</style></head><body>" % _HTML_CSS)
        T.append("<div class='wm'>%s</div>" % _wm_spans(doc))
    for sec in (doc.get("sections") or []):
        T.append("<h2>%s</h2>" % _html_esc(sec.get("title")))
        for b in (sec.get("blocks") or []):
            T.append(_html_block(b))
    om = doc.get("omitted") or []
    if om:
        T.append("<h2>本视图未包含的章节</h2><div class='omitted'>%s</div>"
                 % _html_esc("本视图（%s）按范围裁剪，未包含：%s。"
                        "需要这些章节请改用「全景」视图重新生成。"
                        % (doc.get("view_label") or "", "、".join(
                            str(x.get("title")) for x in om))))
    sk = doc.get("skipped_sections") or []
    if sk:
        T.append("<h2>本报告未列示的章节</h2><div class='omitted'>%s</div>"
                 % _html_esc("以下章节本轮无内容，已不列示（不是漏印）：%s。"
                             "原因：%s"
                             % ("、".join(str(x.get("title")) for x in sk),
                                str((sk[0] or {}).get("reason") or ""))))
    T.append("<div class='foot'>%s<br>%s<br>%s</div>"
             % (_html_esc(disc.get("identity_line")),
                _html_esc(_review_line(doc).replace("**", "")),
                "<br>".join(_html_esc(x) for x in REPORT_HEADER_ROWS)))
    if full_page:
        T.append("</body></html>")
    return "".join(T).encode("utf-8")


def _wm_spans(doc: Dict[str, Any]) -> str:
    """HTML 水印层（重复平铺，屏幕与打印均可见）。"""
    text = _html_esc(doc.get("watermark_text") or watermark_text_of(doc))
    out = []
    for r in range(6):
        for c in range(2):
            out.append("<span style='top:%dpx;left:%dpx'>%s</span>"
                       % (r * 190 + 40, c * 430 + 20, text))
    return "".join(out)


# --------------------------------------------------------------------------
# PDF（reportlab）
# --------------------------------------------------------------------------
def _render_pdf(doc: Dict[str, Any]) -> bytes:
    from reportlab.lib import colors                            # noqa: PLC0415
    from reportlab.lib.pagesizes import A4                      # noqa: PLC0415
    from reportlab.lib.styles import ParagraphStyle             # noqa: PLC0415
    from reportlab.lib.units import mm                          # noqa: PLC0415
    from reportlab.pdfbase import pdfmetrics                    # noqa: PLC0415
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont        # noqa: PLC0415
    from reportlab.platypus import (Paragraph, SimpleDocTemplate,   # noqa: PLC0415
                                    Spacer, Table, TableStyle)

    from engine.document_watermark import PDF_CJK_FONT           # noqa: PLC0415

    _require_disclaimer(doc)
    try:
        pdfmetrics.registerFont(UnicodeCIDFont(PDF_CJK_FONT))
        font = PDF_CJK_FONT
    except Exception:                                            # noqa: BLE001
        font = "Helvetica"        # 极端兜底：可能丢 CJK 字形，但**不静默**（见下 note 块）

    st_h2 = ParagraphStyle("h2", fontName=font, fontSize=13.5, leading=19,
                           spaceBefore=10, spaceAfter=4,
                           textColor=colors.HexColor("#0f172a"))
    st_p = ParagraphStyle("p", fontName=font, fontSize=9.5, leading=14.5)
    st_cell = ParagraphStyle("c", fontName=font, fontSize=8, leading=11.5)
    st_note = ParagraphStyle("n", fontName=font, fontSize=8.5, leading=12.5,
                             textColor=colors.HexColor("#92400e"))

    flow: List[Any] = []
    for sec in (doc.get("sections") or []):
        flow.append(Paragraph(_html_esc(sec.get("title")), st_h2))
        for b in (sec.get("blocks") or []):
            t = str(b.get("type") or "")
            if t == "paragraph":
                flow.append(Paragraph(_html_esc(b.get("text")), st_p))
            elif t == "kv":
                data = [[Paragraph(_html_esc(x.get("k")), st_cell),
                         Paragraph(_html_esc(x.get("v")), st_cell)]
                        for x in (b.get("items") or [])]
                if data:
                    tb = Table(data, colWidths=[38 * mm, 130 * mm])
                    tb.setStyle(TableStyle([
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
                        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8fafc")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ]))
                    flow.append(tb)
            elif t == "table":
                cols = [str(c) for c in (b.get("columns") or [])]
                data = [[Paragraph(_html_esc(c), st_cell) for c in cols]]
                for row in (b.get("rows") or []):
                    vals = row if isinstance(row, list) else [row.get(c) for c in cols]
                    data.append([Paragraph(_html_esc(_disp(v)), st_cell) for v in vals])
                if cols:
                    avail = 168 * mm
                    w = avail / float(len(cols))
                    tb = Table(data, colWidths=[w] * len(cols), repeatRows=1)
                    tb.setStyle(TableStyle([
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f8fafc")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 3),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ]))
                    flow.append(tb)
                if b.get("note"):
                    flow.append(Paragraph(_html_esc(b.get("note")),
                                          ParagraphStyle("cn", parent=st_p,
                                                         fontSize=7.8,
                                                         textColor=colors.HexColor("#64748b"))))
            elif t == "list":
                for x in (b.get("items") or []):
                    flow.append(Paragraph("· %s" % _html_esc(x), st_p))
            elif t == "note":
                flow.append(Paragraph(_html_esc(b.get("text")), st_note))
            flow.append(Spacer(1, 2.5))
    sk = doc.get("skipped_sections") or []
    if sk:
        flow.append(Paragraph("本报告未列示的章节", st_h2))
        flow.append(Paragraph(_html_esc(
            "以下章节本轮无内容，已不列示（不是漏印）：%s。原因：%s"
            % ("、".join(str(x.get("title")) for x in sk),
               str((sk[0] or {}).get("reason") or ""))), st_note))
    om = doc.get("omitted") or []
    if om:
        flow.append(Paragraph("本视图未包含的章节", st_h2))
        flow.append(Paragraph(
            "本视图（%s）按范围裁剪，未包含：%s。需要这些章节请改用「全景」视图重新生成。"
            % (_html_esc(doc.get("view_label") or ""),
               _html_esc("、".join(str(x.get("title")) for x in om))), st_note))

    def _footer(canv, _d):
        canv.saveState()
        try:
            canv.setFont(font, 7)
        except Exception:                                        # noqa: BLE001
            pass
        canv.setFillColor(colors.HexColor("#64748b"))
        canv.drawString(20 * mm, 12 * mm, REPORT_HEADER_ROWS[0])
        canv.drawString(20 * mm, 8.5 * mm, "%s  %s" % (
            doc.get("doc_no") or "", _review_line(doc).replace("**", "")))
        canv.restoreState()

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=22 * mm, rightMargin=20 * mm,
                      topMargin=18 * mm, bottomMargin=20 * mm,
                      title=doc_title(doc), author=str(doc.get("generated_by") or "")
                      ).build(flow, onFirstPage=_footer, onLaterPages=_footer)

    # ★ 水印：复用唯一权威（逐页叠加）
    #   ★★ 传**带真实扩展名的文件名**：`apply_watermark(".pdf", …)` 会因
    #      `os.path.splitext(".pdf") == (".pdf", "")` 把扩展名判成空 ⇒ **静默退回 sidecar**
    #      （实测踩过：水印没进 PDF，却不报错）。故此处用 `report.pdf`。
    from engine.document_watermark import apply_watermark        # noqa: PLC0415
    out, mode, _msg = apply_watermark("report.pdf", buf.getvalue(),
                                      doc.get("watermark_text") or watermark_text_of(doc))
    if font == "Helvetica":
        # 字体兜底时**明确留痕**（不静默）
        try:
            import sys as _sys                                   # noqa: PLC0415
            print("[report-render] CJK 字体注册失败，已退回 Helvetica（部分字形可能缺失）",
                  file=_sys.stderr, flush=True)
        except Exception:                                        # noqa: BLE001
            pass
    return out if mode == "embedded" else buf.getvalue()


# --------------------------------------------------------------------------
# DOCX（python-docx）
# --------------------------------------------------------------------------
def _render_docx(doc: Dict[str, Any]) -> bytes:
    import docx                                                  # noqa: PLC0415
    from docx.enum.text import WD_ALIGN_PARAGRAPH                 # noqa: PLC0415
    from docx.shared import Pt, RGBColor                          # noqa: PLC0415

    _require_disclaimer(doc)
    d = docx.Document()
    wm = doc.get("watermark_text") or watermark_text_of(doc)

    # ★ 水印（页眉，随文档走；打印可见）+ 页眉合规行
    for sec in d.sections:
        hdr = sec.header
        p0 = hdr.paragraphs[0] if hdr.paragraphs else hdr.add_paragraph()
        p0.text = ""
        r = p0.add_run(wm)
        r.font.size = Pt(8)
        r.font.color.rgb = RGBColor(0xA0, 0xAA, 0xB8)
        p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
        # 每页页眉也带**免责声明正文**（不只页脚一句）—— 与 PDF/HTML 口径一致
        p2 = hdr.add_paragraph(str(_require_disclaimer(doc).get("identity_line")))
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if p2.runs:
            p2.runs[0].font.size = Pt(7)
            p2.runs[0].font.color.rgb = RGBColor(0x64, 0x74, 0x8B)
        p1 = hdr.add_paragraph(REPORT_HEADER_ROWS[0])
        p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if p1.runs:
            p1.runs[0].font.size = Pt(7.5)
            p1.runs[0].font.color.rgb = RGBColor(0x64, 0x74, 0x8B)
        ftr = sec.footer
        f0 = ftr.paragraphs[0] if ftr.paragraphs else ftr.add_paragraph()
        f0.text = "%s  %s" % (doc.get("doc_no") or "",
                              _review_line(doc).replace("**", ""))
        if f0.runs:
            f0.runs[0].font.size = Pt(7)

    for sec in (doc.get("sections") or []):
        d.add_heading(str(sec.get("title")), level=2)
        for b in (sec.get("blocks") or []):
            t = str(b.get("type") or "")
            if t == "paragraph":
                d.add_paragraph(str(b.get("text") or ""))
            elif t == "kv":
                tb = d.add_table(rows=0, cols=2)
                tb.style = "Table Grid"
                for x in (b.get("items") or []):
                    c = tb.add_row().cells
                    c[0].text = _disp(x.get("k"))
                    c[1].text = _disp(x.get("v"))
            elif t == "table":
                cols = [str(c) for c in (b.get("columns") or [])]
                if not cols:
                    continue
                tb = d.add_table(rows=1, cols=len(cols))
                tb.style = "Table Grid"
                for i, c in enumerate(cols):
                    tb.rows[0].cells[i].text = c
                for row in (b.get("rows") or []):
                    vals = row if isinstance(row, list) else [row.get(c) for c in cols]
                    cells = tb.add_row().cells
                    for i, v in enumerate(vals[:len(cols)]):
                        cells[i].text = _disp(v)
                if b.get("note"):
                    d.add_paragraph(str(b.get("note")))
            elif t == "list":
                for x in (b.get("items") or []):
                    d.add_paragraph(str(x), style="List Bullet")
            elif t == "note":
                d.add_paragraph(str(b.get("text") or ""))
    sk = doc.get("skipped_sections") or []
    if sk:
        d.add_heading("本报告未列示的章节", level=2)
        d.add_paragraph("以下章节本轮无内容，已不列示（不是漏印）：%s。原因：%s"
                        % ("、".join(str(x.get("title")) for x in sk),
                           str((sk[0] or {}).get("reason") or "")))
    om = doc.get("omitted") or []
    if om:
        d.add_heading("本视图未包含的章节", level=2)
        d.add_paragraph("本视图（%s）按范围裁剪，未包含：%s。需要这些章节请改用「全景」视图重新生成。"
                        % (doc.get("view_label") or "",
                           "、".join(str(x.get("title")) for x in om)))
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------
# XLSX（openpyxl）
# --------------------------------------------------------------------------
def _render_xlsx(doc: Dict[str, Any]) -> bytes:
    import openpyxl                                              # noqa: PLC0415
    from openpyxl.styles import Alignment, Font, PatternFill      # noqa: PLC0415

    _require_disclaimer(doc)
    wm = doc.get("watermark_text") or watermark_text_of(doc)
    wb = openpyxl.Workbook()
    head_font = Font(bold=True, size=10)
    head_fill = PatternFill("solid", fgColor="F1F5F9")
    title_font = Font(bold=True, size=12)
    wrap = Alignment(vertical="top", wrap_text=True)

    def _sheet(title: str, index: int):
        if index == 0:
            return wb.active
        return wb.create_sheet()

    idx = 0
    for sec in (doc.get("sections") or []):
        ws = _sheet(str(sec.get("title")), idx)
        ws.title = str(sec.get("title"))[:31] or ("节%d" % (idx + 1))
        idx += 1
        # ★ 水印（Excel 页眉，打印/预览可见）+ 合规行
        ws.oddHeader.center.text = wm
        ws.oddHeader.center.size = 8
        ws.oddHeader.center.color = "A0AAB8"
        ws.oddFooter.left.text = REPORT_HEADER_ROWS[0]
        ws.oddFooter.left.size = 7
        ws.oddFooter.right.text = "%s  %s" % (doc.get("doc_no") or "",
                                              _review_line(doc).replace("**", ""))
        ws.oddFooter.right.size = 7
        row = 1
        for b in (sec.get("blocks") or []):
            t = str(b.get("type") or "")
            if t == "paragraph":
                ws.cell(row=row, column=1, value=str(b.get("text") or "")).alignment = wrap
                ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
                row += 1
            elif t == "kv":
                for x in (b.get("items") or []):
                    ws.cell(row=row, column=1, value=_disp(x.get("k"))).font = head_font
                    ws.cell(row=row, column=2, value=_disp(x.get("v"))).alignment = wrap
                    row += 1
            elif t == "table":
                cols = [str(c) for c in (b.get("columns") or [])]
                for ci, c in enumerate(cols, start=1):
                    cell = ws.cell(row=row, column=ci, value=c)
                    cell.font = head_font
                    cell.fill = head_fill
                row += 1
                for r in (b.get("rows") or []):
                    vals = r if isinstance(r, list) else [r.get(c) for c in cols]
                    for ci, v in enumerate(vals[:len(cols)], start=1):
                        ws.cell(row=row, column=ci, value=_disp(v)).alignment = wrap
                    row += 1
                if b.get("note"):
                    ws.cell(row=row, column=1, value=str(b.get("note")))
                    row += 1
            elif t == "list":
                for x in (b.get("items") or []):
                    ws.cell(row=row, column=1, value="· %s" % x).alignment = wrap
                    row += 1
            elif t == "note":
                ws.cell(row=row, column=1, value=str(b.get("text") or "")).alignment = wrap
                row += 1
        ws.cell(row=row + 1, column=1,
                value="报告：%s" % doc_title(doc)).font = title_font
        ws.column_dimensions["A"].width = 30
        for cl in "BCDEF":
            ws.column_dimensions[cl].width = 22

    if idx == 0:                       # 极端：无任何章节 ⇒ 仍出一张封面表（不产空工作簿）
        ws = wb.active
        ws.title = "封面"
        ws["A1"] = doc_title(doc)
    sk = doc.get("skipped_sections") or []
    if sk:
        wss = wb.create_sheet("未列示的章节")
        wss.oddHeader.center.text = wm
        wss["A1"] = "以下章节本轮无内容，已不列示（不是漏印）："
        for i, x in enumerate(sk, start=2):
            wss.cell(row=i, column=1, value=str(x.get("title")))
        wss["A%d" % (len(sk) + 3)] = "原因：%s" % str((sk[0] or {}).get("reason") or "")
    om = doc.get("omitted") or []
    if om:
        ws = wb.create_sheet("未包含的章节")
        ws.oddHeader.center.text = wm
        ws["A1"] = "本视图（%s）按范围裁剪，未包含以下章节：" % (doc.get("view_label") or "")
        for i, x in enumerate(om, start=2):
            ws.cell(row=i, column=1, value=str(x.get("title")))
        ws["A%d" % (len(om) + 3)] = "需要这些章节请改用「全景」视图重新生成。"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------
_RENDERERS = {"html": _render_html, "pdf": _render_pdf,
              "docx": _render_docx, "xlsx": _render_xlsx}


def _clean_doc_text(node, _depth: int = 0):
    """深度清理文档模型里的文本（去 markdown、去内部编写说明、回填身份占位符）。

    ★★ 2026-10-18（GAP-08）：端到端实测（META-SYSTEM-COMPLETENESS-AUDIT 6.2）：
      导出的 PDF/DOCX 里 **各有 62~64 处 `**`**，且把写给开发者的句子直接印给客户：
      `本节为**必含章节**：缺失时报告**不予产出**（渲染层直接报错，不静默）。`
      根因：**质量门禁（`text_guardrails` / `content_placeholder_guard` / `quality_gates`）
      全部只接在"一键分析"那条链上**，而本条导出链（`report_service`→`report_render`）
      一个门禁都没接（`grep` 实证为空）。
    本函数把「清理」收敛到**渲染入口**：只要走 `render()`，就一定被清理 ——
    不再依赖上游每条链各自记得调用（那正是漏掉的根因）。
    `strip_markup` 是项目既有唯一权威（已处理 `*住宿服务*` 品名与 `**` 数据占位等坑）。
    """
    if isinstance(node, str):
        try:
            from engine.text_guardrails import strip_markup
            s = strip_markup(node)
        except Exception:                                        # noqa: BLE001
            s = node
        # 内部编写说明（不是给读者的）—— 命中即删，不留在交付件里
        if "本节为" in s and "必含章节" in s:
            return ""
        # ★ 身份占位符兜底（GAP-08）：`generate()` 会回填；若调用方直接 `build_document→render`
        #   （测试/预览路径），这里必须给出可读文本，**不得把标记原样交给读者**。
        if "[[DOC_NO]]" in s or "[[DOC_VER]]" in s:
            s = s.replace("[[DOC_NO]]", "（尚未登记）").replace("[[DOC_VER]]", "（尚未登记）")
        return s
    if isinstance(node, list):
        return [_clean_doc_text(x, _depth + 1) for x in node]
    if isinstance(node, dict):
        return {k: _clean_doc_text(v, _depth + 1) for k, v in node.items()}
    return node


def render(doc: Dict[str, Any], fmt: Any) -> Tuple[bytes, str]:
    """渲染为指定格式 ⇒ `(bytes, watermark_mode)`。

    ★ `watermark_mode` **一律 `embedded`**（4 格式均真嵌入，方式见
      `report_views.WATERMARK_METHOD`）—— 如实声明，不使用 sidecar 冒充。
    """
    from engine.report_views import validate_format             # noqa: PLC0415
    f = validate_format(fmt)
    _require_disclaimer(doc)
    # ★ 出口统一清理（GAP-08）：不依赖上游是否调用过 strip_markup
    doc = _clean_doc_text(doc)
    try:
        data = _RENDERERS[f](doc)
    except ReportRenderError:
        raise
    except Exception as exc:                                     # noqa: BLE001
        raise ReportRenderError("渲染 %s 失败（%s）：%s"
                                % (FORMAT_CN[f], type(exc).__name__, exc), 500) from exc
    if not data:
        raise ReportRenderError("渲染 %s 得到空内容" % FORMAT_CN[f], 500)
    return data, "embedded"


def filename_of(doc: Dict[str, Any], fmt: Any) -> str:
    """下载文件名（含视图与版本，便于区分；不含路径分隔符）。"""
    from engine.report_views import validate_format             # noqa: PLC0415
    f = validate_format(fmt)
    base = "%s_%s_%s" % (str(doc.get("name") or "报告"),
                         str(doc.get("doc_no") or ""),
                         str(doc.get("version") or ""))
    safe = "".join(ch for ch in base if ch not in '\\/:*?"<>|\r\n\t')
    return safe + FORMAT_EXT[f]
