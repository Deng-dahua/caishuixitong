# -*- coding: utf-8 -*-
"""多类型 PDF 识别验收：把真实 xls/xlsx 渲染成带表格线的 PDF，验证类型识别与路由。

原理：用 pymupdf 把单元格画成带边框的网格 → find_tables() 能识别出真实表结构
      → 与原生 xlsx 走同一套指纹分类，可直接对比「xlsx 识别类型 vs PDF 识别类型」。
"""
import os, sys, glob
REPO = r"c:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong"
os.chdir(REPO)
sys.path.insert(0, REPO)
import pymupdf
import main

OUT = os.path.join(REPO, "data/_pdftest")
os.makedirs(OUT, exist_ok=True)


def read_sheet(path, max_rows=30):
    """读 xls/xlsx 第一个 sheet 的前若干行，返回 list[list[str]]。"""
    ext = os.path.splitext(path)[1].lower()
    rows = []
    if ext == ".xls":
        import xlrd
        wb = xlrd.open_workbook(path)
        sh = wb.sheet_by_index(0)
        for r in range(min(sh.nrows, max_rows)):
            rows.append([str(sh.cell_value(r, c)) for c in range(sh.ncols)])
    else:
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True)
        ws = wb[wb.sheetnames[0]]
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i >= max_rows:
                break
            rows.append(["" if v is None else str(v) for v in row])
    return rows


def grid_pdf(rows, dst, fontsize=7.5, cell_h=13):
    """把二维文本画成带边框的表格 PDF。"""
    if not rows:
        return False
    ncols = max(len(r) for r in rows)
    # 列宽按内容长度估算（中文字符算 2 倍宽）
    widths = []
    for c in range(ncols):
        w = 0
        for r in rows:
            s = r[c] if c < len(r) else ""
            w = max(w, min(len(s) * fontsize * 0.62, 150))
        widths.append(max(w, 34))
    doc = pymupdf.open()
    page = doc.new_page(width=sum(widths) + 20, height=len(rows) * cell_h + 20)
    for ri, r in enumerate(rows):
        x = 10
        y = 10 + ri * cell_h
        for ci in range(ncols):
            w = widths[ci]
            rect = pymupdf.Rect(x, y, x + w, y + cell_h)
            page.draw_rect(rect, color=(0.6, 0.6, 0.6), width=0.4)
            s = (r[ci] if ci < len(r) else "")[:26]
            if s.strip():
                try:
                    page.insert_text((x + 2, y + cell_h - 3.5), s,
                                     fontsize=fontsize, fontname="china-s")
                except Exception:
                    page.insert_text((x + 2, y + cell_h - 3.5), "?",
                                     fontsize=fontsize)
            x += w
    doc.save(dst)
    doc.close()
    return True


# 待测样本：真实业务文件（xlsx/xls）
SAMPLES = [
    ("data/uploads/1/1_492_猩猩织光_北京_商贸有限公司_2026年1账期_进项发票列表.xlsx", "purchase_invoice"),
    ("data/uploads/1/1_493_猩猩织光_北京_商贸有限公司_2026年1账期_销项发票列表.xlsx", "sales_invoice"),
    ("data/uploads/1/1_491_猩猩织光_北京_商贸有限公司_2026年1账期_工资表.xls", "salary"),
    ("data/uploads/1/1_501_猩猩织光_北京_商贸有限公司_社保明细_2026年01期.xls_.xlsx", "social_security"),
    ("data/uploads/1/1_500_猩猩织光_北京_商贸有限公司_2026年第1期-2026年第3期_凭证.xls", "voucher"),
    ("data/uploads/4/4_231_北京潘祥记餐饮有限公司_2024年01月-2024年12月_科目余额.xls", "trial_balance"),
]

print("=" * 92)
print("%-34s %-20s %-22s %s" % ("样本", "xlsx识别类型", "PDF识别类型", "结果"))
print("-" * 92)
ok = bad = 0
for rel, expect in SAMPLES:
    src = os.path.join(REPO, rel)
    if not os.path.exists(src):
        print("%-34s  (文件不存在)" % os.path.basename(rel)[:34]); continue
    # ① 原生 xlsx 识别（基线）
    try:
        base = main._parse_excel_structured(src, os.path.splitext(src)[1].lower())
        base_type = (base or {}).get("type", "?")
        base_rows = len((base or {}).get("rows") or [])
    except Exception as e:
        base_type, base_rows = f"ERR:{type(e).__name__}", 0
    # ② 渲染成 PDF 再识别（文件名保持原样——文件名是识别依据之一，不可截断）
    dst = os.path.join(OUT, os.path.splitext(os.path.basename(rel))[0] + ".pdf")
    try:
        grid_pdf(read_sheet(src), dst)
        r = main._parse_pdf_generic(dst, os.path.basename(dst))
        if isinstance(r, list):
            pdf_type, pdf_rows = "bank(list)", len(r)
        else:
            pdf_type = (r or {}).get("type", "?"); pdf_rows = len((r or {}).get("rows") or [])
    except Exception as e:
        pdf_type, pdf_rows = f"ERR:{type(e).__name__}", 0
    same = (pdf_type == base_type)
    ok, bad = (ok + 1, bad) if same else (ok, bad + 1)
    print("%-34s %-20s %-22s %s" % (
        os.path.basename(rel)[:34], f"{base_type}({base_rows})",
        f"{pdf_type}({pdf_rows})", "✓ 一致" if same else "✗ 不一致"))

print("-" * 92)
print("类型一致 %d / %d" % (ok, ok + bad))

# ═══════════════ 未知内容 PDF：必须不丢、且不得误判成银行流水 ═══════════════
print("\n" + "=" * 92)
print("【任意内容兜底】构造一份业务无关的 PDF（散文+随机数字），验证：识别为 generic_data、内容保留、不误判 bank")
print("-" * 92)
unknown_rows = [
    ["会议纪要", "部门", "主持人", "记录人"],
    ["关于下半年工作安排的讨论", "综合部", "李四", "王五"],
    ["一、指导思想：坚持稳中求进，统筹推进各项任务", "", "", ""],
    ["二、重点事项：1) 优化流程 2) 加强协作 3) 落实责任", "", "", ""],
    ["三、时间节点：9月底前完成阶段目标", "", "", ""],
    ["四、其他事项：暂无", "", "", ""],
]
unk_pdf = os.path.join(OUT, "一份与财税无关的会议纪要.pdf")
grid_pdf(unknown_rows, unk_pdf)
try:
    ru = main._parse_pdf_generic(unk_pdf, os.path.basename(unk_pdf))
    if isinstance(ru, list):
        print("  ✗ 被判成银行流水（list %d 条）——答非所问" % len(ru))
    else:
        t = ru.get("type")
        n = len(ru.get("rows") or [])
        print("  识别类型 = %s，保留内容 %d 行，source=%s" % (t, n, ru.get("source")))
        print("  >>", "✓ 未丢弃内容且未误判成流水" if n > 0 else "✗ 内容被丢弃")
except Exception as e:
    import traceback; traceback.print_exc()
