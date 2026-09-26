# -*- coding: utf-8 -*-
"""① 银行流水 PDF 回归 ② OCR 可用性探测"""
import os, sys, glob
REPO = r"c:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong"
os.chdir(REPO)
sys.path.insert(0, REPO)
import main

print("========== ① 银行流水 PDF 回归（招行对账单）==========")
for fp in sorted(glob.glob(os.path.join(REPO, "data/uploads/1/1_4[89]*.pdf"))) + \
          sorted(glob.glob(os.path.join(REPO, "data/uploads/3/3_25[678]*.pdf"))):
    r = main._parse_pdf_generic(fp, os.path.basename(fp))
    t = r.get("type") if isinstance(r, dict) else type(r).__name__
    n = len(r.get("rows") or []) if isinstance(r, dict) else (len(r) if isinstance(r, list) else 0)
    print("  %-14s -> type=%-16s rows=%s" % (os.path.basename(fp), t, n))

print("\n========== ② OCR / PDF 引擎可用性 ==========")
for mod in ("pymupdf", "fitz", "pypdf", "PyPDF2", "pdfplumber", "easyocr",
            "pytesseract", "PIL", "cv2", "numpy"):
    try:
        m = __import__(mod)
        v = getattr(m, "__version__", "?")
        print("  ✓ %-12s %s" % (mod, v))
    except Exception as e:
        print("  ✗ %-12s %s" % (mod, type(e).__name__))

import shutil as _sh
import pytesseract
print("  tesseract 可执行文件:", _sh.which("tesseract") or pytesseract.pytesseract.tesseract_cmd)
try:
    print("  tesseract 版本:", pytesseract.get_tesseract_version())
except Exception as e:
    print("  tesseract 不可调用:", type(e).__name__, str(e)[:120])
