# -*- coding: utf-8 -*-
"""
P3.5 接线闭环验证：直接驱动「一键分析按钮」真实使用的文件解析器
（pipeline._run_analyze 按扩展名路由的那几个），用**真实格式文件**证明
补充自证资料在按钮路径上也会被识别为 sup_* 并翻成 provided 类别。
"""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main
from engine.enterprise_report import _doc_covered_categories

tmp = tempfile.mkdtemp(prefix="p35wire_")

def new(name):
    return os.path.join(tmp, name)

# ── 真实格式文件 ──
import openpyxl
def make_xlsx(name):
    p = new(name); wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["序号", "项目", "金额"]); ws.append([1, "测试", 100])
    wb.save(p); return p

import docx
def make_docx(name):
    p = new(name); d = docx.Document(); d.add_paragraph("BOM 物料清单测试")
    d.save(p); return p

import fitz
def make_pdf(name):
    p = new(name); doc = fitz.open(); pg = doc.new_page()
    pg.insert_text((50, 50), "出口报关单 测试内容"); doc.save(p); doc.close(); return p

from PIL import Image
def make_png(name):
    p = new(name); Image.new("RGB", (40, 40), (120, 80, 40)).save(p); return p

def make_csv(name):
    p = new(name)
    with open(p, "w", encoding="utf-8") as f:
        f.write("a,b,c\n1,2,3\n")
    return p

cases = [
    # (说明, 文件名, 真实按钮解析器调用, 期望 doc_type)
    ("xlsx", "完税凭证.xlsx",            lambda p, n: main._parse_excel_structured(p, ".xlsx", n), "sup_tax_paid_cert"),
    ("csv",  "出口报关单.csv",           lambda p, n: main._parse_excel_structured(p, ".csv", n),  "sup_export_customs"),
    ("pdf",  "出口报关单.pdf",           lambda p, n: main._parse_pdf_generic(p, n),                "sup_export_customs"),
    ("pdf",  "免税简易计税项目资料.pdf",   lambda p, n: main._parse_pdf_generic(p, n),                "sup_vat_exempt"),
    ("docx", "BOM物料清单.docx",          lambda p, n: main._parse_docx(p, n),                       "sup_bom"),
    ("xlsx", "住房公积金缴存明细.xlsx",    lambda p, n: main._parse_excel_structured(p, ".xlsx", n),  "sup_hf_detail"),
    ("png",  "不动产权证.png",           lambda p, n: main._parse_image_ocr(p, n),                  "sup_property_cert"),
]

builders = {
    "完税凭证.xlsx": lambda: make_xlsx("完税凭证.xlsx"),
    "出口报关单.csv": lambda: make_csv("出口报关单.csv"),
    "出口报关单.pdf": lambda: make_pdf("出口报关单.pdf"),
    "免税简易计税项目资料.pdf": lambda: make_pdf("免税简易计税项目资料.pdf"),
    "BOM物料清单.docx": lambda: make_docx("BOM物料清单.docx"),
    "住房公积金缴存明细.xlsx": lambda: make_xlsx("住房公积金缴存明细.xlsx"),
    "不动产权证.png": lambda: make_png("不动产权证.png"),
}

print("="*72)
print("A. 按钮路径解析器 → doc_type（命中 P3.5 早返回，文件名优先）")
all_ok = True
file_results = []
for ext, name, parser, expect in cases:
    path = builders[name]()
    res = parser(path, name)
    dt = (res or {}).get("type")
    ok = dt == expect
    all_ok &= ok
    print(f"  [{ext:4}] {name:24} → type={dt}  期望={expect}  {'OK' if ok else 'FAIL'}")
    if dt and dt.startswith("sup_"):
        file_results.append({"file": name, "type": dt})

print("="*72)
print("B. _doc_covered_categories（红线 material_readiness 用的同一函数）")
cov = _doc_covered_categories({"file_results": file_results})
print("  已提供类别:", sorted(cov))
need = {"完税凭证", "出口报关单", "免税/简易计税项目资料", "BOM物料清单", "住房公积金缴存明细", "不动产权证或土地使用证"}
miss = need - cov
print("  缺漏类别:", sorted(miss) if miss else "无")
all_ok &= (not miss)

print("="*72)
print("C. 反例：正常发票不得被误吞")
inv = main._parse_excel_structured(make_xlsx("销项发票2024.xlsx"), ".xlsx", "销项发票2024.xlsx")
print("  销项发票2024.xlsx → type=", (inv or {}).get("type"), "(应为 sales_invoice)")
all_ok &= ((inv or {}).get("type") == "sales_invoice")

print("="*72)
print("结论:", "PASS ✅ 全文件类型经按钮解析器真实命中 P3.5，且正常发票未被误吞" if all_ok else "FAIL ❌")
sys.exit(0 if all_ok else 1)
