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


def _watermark_lines(text: str, font: str, size: float, avail: float):
    """把水印文字排成若干行，使每行宽度不超过 `avail`（GAP-08：解决文字被页边裁掉）。

    ★ 实测问题：旧实现固定 `size=max(14, min(w,h)/26)` 后 `drawCentredString` 居中绘制，
      水印文字（含文书编号+版本+复核状态+复核人+时间，约 60~90 字）在 A4 上旋转 35° 后
      两端超出 mediabox，**每页首部被裁**（PDF 文本提取实测："内部使用 · 内部辅助分析"
      整段消失，只剩"工作底稿（全景）…"）。
    策略：按 " · " 分段 → 逐段累积成行 → 优先保证**不缩字号**；
          单段超宽时按字符二分（CJK 按字数估宽），仍不行才缩字号。
    """
    from reportlab.pdfbase.pdfmetrics import stringWidth      # noqa: PLC0415

    # ★ 宽度估算必须自己算 CJK：`stringWidth` 对 CID 中文字体（STSong-Light）按**西文**
    #   度量返回，实测把 50 个汉字的宽度算成小一半 ⇒ 分行阈值失效 ⇒ 首字仍被裁。
    #   这里按"全角 1.0em / 半角 0.55em"估算（保守，宁可行数多一行）。
    def _w(s):
        em = 0.0
        for ch in str(s):
            em += 1.0 if ("\u4e00" <= ch <= "\u9fff" or "\u3000" <= ch <= "\u303f"
                          or "\uff00" <= ch <= "\uffef") else 0.55
        return em * size

    segs = [s for s in str(text or "").split(" · ") if s] or [str(text or "")]
    lines, cur = [], ""
    for seg in segs:
        cand = (cur + " · " + seg) if cur else seg
        if _w(cand) <= avail:
            cur = cand
            continue
        if cur:
            lines.append(cur)
            cur = ""
        # 单段自身超宽 ⇒ 按字符切
        while _w(seg) > avail and len(seg) > 4:
            cut = max(4, int(len(seg) * avail / max(_w(seg), 1)))
            lines.append(seg[:cut])
            seg = seg[cut:]
        cur = seg
    if cur:
        lines.append(cur)
    return lines or [str(text or "")]


def _pdf_watermark(content: bytes, text: str) -> bytes:
    from pypdf import PdfReader, PdfWriter          # noqa: PLC0415
    from reportlab.pdfgen import canvas             # noqa: PLC0415
    from reportlab.lib.pagesizes import A4          # noqa: PLC0415
    import math as _math                            # noqa: PLC0415

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
        size = max(14.0, min(w, h) / 26.0)
        try:
            c.setFont(font, size)
        except Exception:                            # noqa: BLE001
            font = "Helvetica"
            c.setFont(font, size)
        # ★ 旋转 35° 后的可用文本长度：文本沿 35° 方向延伸，
        #   其**水平投影** L·cos35 必须 ≤ 页宽 w、**垂直投影** L·sin35 必须 ≤ 页高 h
        #   ⇒ L ≤ min(w/cos35, h/sin35)。留 5% 边距。
        #   ⚠ 之前误算成 min(w,h)/sin35（这是"对角线"长度）⇒ 阈值偏大 30%，
        #     首字仍被裁（实测"内部使用"→"部使用"）。
        _rad = _math.radians(35)
        avail = min(w / max(_math.cos(_rad), 0.1),
                    h / max(_math.sin(_rad), 0.1)) * 0.95
        lines = _watermark_lines(text, font, size, avail)
        # 行数多时略降字号（不超过 2 行时保持原字号）
        if len(lines) > 2:
            size = max(9.0, size * 2.0 / len(lines))
            try:
                c.setFont(font, size)
            except Exception:                        # noqa: BLE001
                c.setFont("Helvetica", size)
        c.setFillColorRGB(0.72, 0.72, 0.72)
        c.translate(w / 2.0, h / 2.0)
        c.rotate(35)
        gap = size * 1.7
        y0 = (len(lines) - 1) * gap / 2.0
        for i, ln in enumerate(lines):
            c.drawCentredString(0, y0 - i * gap, ln)
        c.restoreState()
        c.showPage()
        c.save()
        overlay = PdfReader(io.BytesIO(buf.getvalue())).pages[0]
        page.merge_page(overlay)
        writer.add_page(page)
    # ★ 元数据必须**迁移后再写**：pypdf 的 `PdfWriter()` 新建文档不带原 Info，
    #   旧实现只在 reportlab 侧设了 title/author，随后被这里重建 ⇒ 最终只剩
    #   `/Producer: pypdf`（实测 PDF metadata title/author/creationDate 全空）。
    try:
        meta = dict(reader.metadata or {})
    except Exception:                                # noqa: BLE001
        meta = {}
    meta.setdefault("/Title", "报告")
    try:
        writer.add_metadata({k: str(v) for k, v in meta.items() if v})
    except Exception:                                # noqa: BLE001
        pass
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
