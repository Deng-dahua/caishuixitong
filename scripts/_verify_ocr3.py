# -*- coding: utf-8 -*-
"""验证三处 OCR 入口：_parse_image_ocr / _try_ocr_pdf / _try_ocr_image。"""
import os, sys, glob
REPO = r"c:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong"
os.chdir(REPO)
sys.path.insert(0, REPO)
import main

SRC = glob.glob(os.path.join(REPO, "data/trash/1_295_*.pdf"))[0]
IMG = os.path.join(REPO, "data/_ocr_test_page.png")

import pymupdf
d = pymupdf.open(SRC)
pix = d[0].get_pixmap(dpi=200)
pix.save(IMG)
d.close()
print("测试图片:", IMG, os.path.getsize(IMG), "bytes\n")

print("========== ① _parse_image_ocr（图片→结构化）==========")
r = main._parse_image_ocr(IMG, "test.png")
if isinstance(r, dict):
    print("  type =", r.get("type"), " rows =", len(r.get("rows") or []))
    for row in (r.get("rows") or [])[:4]:
        print("   ", str(row)[:160])
else:
    print("  返回:", type(r).__name__, str(r)[:200])

print("\n========== ② _try_ocr_pdf（OCR接口·PDF字节）==========")
with open(SRC, "rb") as f:
    pdf_bytes = f.read()
t = main._try_ocr_pdf(pdf_bytes)
print("  提取字符数 =", len(t))
print("  片段:", t[:200].replace("\n", " / "))

print("\n========== ③ _try_ocr_image（OCR接口·图片字节）==========")
with open(IMG, "rb") as f:
    img_bytes = f.read()
t2 = main._try_ocr_image(img_bytes)
print("  提取字符数 =", len(t2))
print("  片段:", t2[:200].replace("\n", " / "))

print("\n========== 汇总 ==========")
print("  _parse_image_ocr 有效 :", bool(isinstance(r, dict) and r.get("rows")))
print("  _try_ocr_pdf     有效 :", len(t) > 200)
print("  _try_ocr_image   有效 :", len(t2) > 200)
