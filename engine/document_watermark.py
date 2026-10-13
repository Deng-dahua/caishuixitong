# -*- coding: utf-8 -*-
"""资料下载**水印**（P0-2）。

设计原则（★ 诚实优先，不假装）
  · **能真叠加的就真叠加**：PDF（`pypdf` + `reportlab`）逐页叠加斜向文字水印；
    图片（`Pillow`）叠加斜向文字水印。
  · **不能叠加的如实标注**：xlsx / csv / docx / doc / txt / xml / ofd / zip 等格式，
    在**不改动文件内容**的前提下无法嵌入可视水印 ⇒ 返回**随附水印信息**
    （HTTP 头 `X-Watermark-Mode: sidecar` + `X-Watermark-Text`），由调用方/前端提示，
    **绝不静默当作"已加水印"**。
  · 水印**只作用于下载副本**，**绝不覆盖原件**（原件可追溯性是铁律）。

水印文字示例：`内部使用 · 张审查 · 2026-10-13 17:50 · 仅供本次核查`
"""
from __future__ import annotations

import io
import os
from typing import Tuple

#: 可**真叠加**水印的扩展名
EMBEDDABLE = frozenset({".pdf", ".jpg", ".jpeg", ".png", ".bmp", ".tiff"})

#: ★ 中文水印的字体（事故：`Helvetica` / PIL 默认字体**渲染不了 CJK**）
#:   · PDF：reportlab **内置** CID 字体 `STSong-Light`（无需外部字体文件）；
#:   · 图片：需系统 CJK TrueType；找不到 ⇒ **降级为 sidecar 并说明原因**（不渲染方块）。
PDF_CJK_FONT = "STSong-Light"
#: ★ 公开（供报告渲染复用同一字体口径 —— 中文渲染的字体唯一权威在本模块）
_IMAGE_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
)


def _pdf_font_name() -> str:
    """注册并返回可渲染中文的 PDF 字体名；失败退回 Helvetica（**调用方须知晓可能丢字形**）。"""
    from reportlab.pdfbase import pdfmetrics                 # noqa: PLC0415
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont    # noqa: PLC0415
    try:
        pdfmetrics.registerFont(UnicodeCIDFont(PDF_CJK_FONT))
        return PDF_CJK_FONT
    except Exception:                                        # noqa: BLE001
        return "Helvetica"


def _image_font(size: int):
    """加载可渲染中文的 TrueType 字体；找不到 ⇒ 返回 `None`（调用方据此降级）。"""
    from PIL import ImageFont                                # noqa: PLC0415
    for path in _IMAGE_FONT_CANDIDATES:
        try:
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
        except Exception:                                    # noqa: BLE001
            continue
    return None


def is_embeddable(filename: str) -> bool:
    return os.path.splitext(filename or "")[1].lower() in EMBEDDABLE


def _pdf_watermark(content: bytes, text: str) -> bytes:
    from pypdf import PdfReader, PdfWriter          # noqa: PLC0415
    from reportlab.pdfgen import canvas             # noqa: PLC0415
    from reportlab.lib.pagesizes import A4          # noqa: PLC0415

    reader = PdfReader(io.BytesIO(content))
    writer = PdfWriter()
    font = _pdf_font_name()
    for page in reader.pages:
        try:
            w = float(page.mediabox.width)
            h = float(page.mediabox.height)
        except Exception:                            # noqa: BLE001
            w, h = A4
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(w, h))
        c.saveState()
        try:
            c.setFont(font, max(14.0, min(w, h) / 26.0))
        except Exception:                            # noqa: BLE001
            c.setFont("Helvetica", max(14.0, min(w, h) / 26.0))
        c.setFillColorRGB(0.72, 0.72, 0.72)
        c.translate(w / 2.0, h / 2.0)
        c.rotate(35)
        c.drawCentredString(0, 0, text)
        c.restoreState()
        c.showPage()
        c.save()
        overlay = PdfReader(io.BytesIO(buf.getvalue())).pages[0]
        page.merge_page(overlay)
        writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _image_watermark(content: bytes, text: str) -> bytes:
    from PIL import Image, ImageDraw                  # noqa: PLC0415

    img = Image.open(io.BytesIO(content))
    fmt = img.format or "PNG"
    base = img.convert("RGBA")
    font = _image_font(max(14, int(min(base.size) / 18)))
    if font is None:
        # ★ 环境缺 CJK 字体 ⇒ **宁可降级也不渲染方块**（由调用方转为 sidecar 并说明）
        raise RuntimeError("环境未找到可渲染中文的字体（CJK TrueType）")
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.text((int(base.size[0] * 0.08), int(base.size[1] * 0.5)), text,
              font=font, fill=(120, 120, 120, 128))
    merged = Image.alpha_composite(base, layer)
    if fmt in ("JPEG", "JPG", "BMP", "TIFF"):
        merged = merged.convert("RGB")
    out = io.BytesIO()
    merged.save(out, format=fmt if fmt else "PNG")
    return out.getvalue()


def apply_watermark(filename: str, content: bytes, text: str) -> Tuple[bytes, str, str]:
    """给下载副本加水印。

    返回 `(bytes, mode, message)`：
      · `mode="embedded"` ⇒ 水印**已嵌入**文件内容（PDF/图片）；
      · `mode="sidecar"`  ⇒ 该格式**无法嵌入**可视水印，返回**原内容**并给出随附说明
        （调用方须把 `message` 呈现给用户，**不得当作已加水印**）；
      · 任何异常 ⇒ 退回 `sidecar`（**不静默**，把原因写进 `message`）。
    """
    t = str(text or "").strip()
    if not t:
        return content, "sidecar", "未指定水印文字，已按原样返回（原件未改动）"
    ext = os.path.splitext(filename or "")[1].lower()
    try:
        if ext == ".pdf":
            return _pdf_watermark(content, t), "embedded", "已逐页嵌入水印"
        if ext in {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}:
            return _image_watermark(content, t), "embedded", "已嵌入水印"
        return content, "sidecar", (
            "该格式（%s）无法在不改动内容的前提下嵌入可视水印："
            "文件内容保持原样，水印信息随附于响应头（%s）" % (ext or "(无扩展名)", t))
    except Exception as exc:                          # noqa: BLE001
        return content, "sidecar", (
            "水印嵌入失败（%s），已按原样返回原件；水印信息：%s" % (exc, t))
