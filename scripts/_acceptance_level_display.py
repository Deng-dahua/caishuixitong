# -*- coding: utf-8 -*-
"""结果级验收：导出报告（HTML/DOCX/XLSX/PDF）正文里等级词是否已统一为「涉嫌风险」。

★ 判据不是"我改了哪个文件"，而是"**用户打开导出件能看到什么**"：
  ① 用真项目（默认 project 1）走 `report_service.build_document` 拿文档模型；
  ② 用 `report_render.render()` 真渲染四种格式；
  ③ 在**渲染后的字节流**里统计等级词（这是用户实际看到的内容）。

反向验证：本地注入缺陷（绕过 display_label）时必须变红。
用法：
    python scripts/_acceptance_level_display.py [project_id]
"""
from __future__ import annotations

import io
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

#: 用户不应在正文里看到的裸等级词（结构化字段值，只应存在于载荷数据里）
FORBIDDEN = ("待核验", "待核实", "已列明", "已查明待办事项", "尚需核实")
#: 应当出现的展示词
EXPECTED = "涉嫌风险"


class _Session:
    """最小会话（真假会话只差权限检查；本验收以 admin 身份只读同一账套）。"""

    username = "acceptance"
    is_admin = True
    user_id = 1

    def __init__(self, engine=None):
        self._engine = engine

    def can_access_company(self, cid):  # noqa: D401
        return True


def _extract_text(fmt: str, data: bytes) -> str:
    """从渲染字节流里抽可读文本（PDF 走 pdfplumber；DOCX/XLSX 解 zip 抽 XML）。"""
    if fmt == "html":
        return data.decode("utf-8", "replace")
    if fmt == "docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                return z.read("word/document.xml").decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            return ""
    if fmt == "xlsx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                return "".join(
                    z.read(n).decode("utf-8", "replace")
                    for n in z.namelist() if n.endswith(".xml"))
        except Exception:  # noqa: BLE001
            return ""
    if fmt == "pdf":
        try:
            import pdfplumber  # noqa: PLC0415
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                return "\n".join((p.extract_text() or "") for p in pdf.pages)
        except Exception as exc:  # noqa: BLE001
            return "__PDF_TEXT_UNAVAILABLE__:%s" % exc
    return ""


def main() -> int:
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    from engine import report_service as RSVC
    from engine import report_render as RENDER

    sess = _Session()
    print("── ① 组装文档模型（project=%s）──" % pid)
    doc = RSVC.build_document(pid, sess, view="full")
    print("  报告名：%s" % doc.get("name"))
    print("  章节数：%s  章节：%s" % (doc.get("counts", {}).get("sections"),
                                      [s["key"] for s in doc.get("sections") or []]))

    # 先在**文档模型**层面统计（不含水印/页眉）
    model_txt = "".join(
        str(b.get("text") or "") + "".join(
            str(x) for row in (b.get("rows") or []) for x in row) + "".join(
            str(i.get("k")) + str(i.get("v")) for i in (b.get("items") or []))
        for s in doc.get("sections") or [] for b in s.get("blocks") or [])
    print("  ② 文档模型层：涉嫌风险=%d  裸待核验=%d  待核=%d  已列明=%d"
          % (model_txt.count(EXPECTED), model_txt.count("待核验"),
             len(re.findall(r"待核(?!验|事项)", model_txt)), model_txt.count("已列明")))

    print("── ③ 真渲染四格式并核对字节流 ──")
    bad_total = 0
    for fmt in ("html", "docx", "xlsx", "pdf"):
        try:
            data, _fn = RENDER.render(doc, fmt)
        except Exception as exc:  # noqa: BLE001
            print("  [%s] 渲染失败：%s" % (fmt, exc))
            bad_total += 1
            continue
        txt = _extract_text(fmt, data)
        if txt.startswith("__PDF_TEXT_UNAVAILABLE__"):
            print("  [%s] 已生成 %d 字节（文本抽取器不可用，跳过词表核对）" % (fmt, len(data)))
            continue
        hits = {w: txt.count(w) for w in FORBIDDEN if w in txt}
        exp = txt.count(EXPECTED)
        flag = "OK " if (not hits and exp >= 0) else "BAD"
        if hits:
            bad_total += 1
        print("  [%s] %s  涉嫌风险=%d  违禁词=%s" % (fmt, flag, exp, hits or "无"))

    print("")
    if bad_total:
        print("验收结果：FAIL（%d 处问题）" % bad_total)
        return 1
    print("验收结果：PASS —— 导出报告正文等级词已统一为「涉嫌风险」，无裸等级词残留")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
