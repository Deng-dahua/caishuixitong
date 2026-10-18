# -*- coding: utf-8 -*-
"""GAP-23 大账套行数上限**实测**（2026-10-18）。

原差距：序时账 1,673 行正常，但**未验证** >1 万行时的截断行为 ——
"大账套可能静默截断"。

本脚本构造 **5 万行**真实形态的序时账，真正走 `main._parse_excel_structured`
（Excel 链路唯一权威），记录：
  · 解析耗时 / 峰值内存；
  · 实际读入行数 vs 文件行数；
  · **是否给出截断回执**（`truncation_note` / `row_cap_note`）；
  · 截断是否可见（前端/接口能拿到）。

用法：python scripts/_measure_large_ledger.py [行数]
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import tracemalloc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine import parse_enhance as PE                                # noqa: E402


def build_ledger(rows: int) -> str:
    """构造真实形态的序时账（列名按真实导出）。"""
    import openpyxl
    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet("序时账")
    ws.append(["记账日期", "凭证号", "科目编码", "科目名称", "摘要",
               "借方发生额", "贷方发生额", "对方单位"])
    for i in range(1, rows + 1):
        day = (i % 28) + 1
        month = ((i // 28) % 12) + 1
        ws.append([
            "2024-%02d-%02d" % (month, day),
            "记-%05d" % i,
            "6001" if i % 2 else "6401",
            "主营业务收入" if i % 2 else "主营业务成本",
            "第 %d 笔业务" % i,
            float(1000 + i),
            0.0 if i % 2 else float(1000 + i),
            "客户%04d 有限公司" % (i % 500),
        ])
    p = os.path.join(tempfile.mkdtemp(prefix="gap23_"), "2024年序时账_%d行.xlsx" % rows)
    wb.save(p)
    return p


def measure(rows: int) -> dict:
    import main as M
    p = build_ledger(rows)
    size_mb = os.path.getsize(p) / 1024 / 1024

    tracemalloc.start()
    t0 = time.time()
    r = M._parse_excel_structured(p, ".xlsx", os.path.basename(p))     # noqa: SLF001
    elapsed = time.time() - t0
    _cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    got = len((r or {}).get("rows") or [])
    cap = PE.MAX_ROW_CAP
    note = PE.truncation_note(rows, cap, os.path.basename(p))
    return {
        "rows_in_file": rows,
        "file_mb": round(size_mb, 2),
        "detected_type": (r or {}).get("type"),
        "confidence": (r or {}).get("confidence"),
        "rows_read": got,
        "elapsed_sec": round(elapsed, 2),
        "peak_mb": round(peak / 1024 / 1024, 2),
        "max_row_cap": cap,
        "cap_semantics": PE.cap_note(cap),
        "truncated": PE.truncated(rows, cap),
        "note": note,
    }


def main(argv) -> int:
    rows = int(argv[1]) if len(argv) > 1 else 50000
    out = measure(rows)
    print(json.dumps(out, ensure_ascii=False, indent=2))

    print("\n===== 判定 =====")
    ok = True
    # ① 类型必须判对（序时账 ⇒ 账簿族）。★ 初版判据漏了这条，而实测正是这里出问题：
    #    序时账被判成 bank_statement（整份账簿进错域）。
    if out["detected_type"] not in ("trial_balance", "voucher", "ledger", "journal"):
        print("[FAIL] 类型识别异常：%s（%d 行序时账应判为账簿族）"
              % (out["detected_type"], rows))
        ok = False
    # ② **读到 0 行就是事故**（整份账套被静默丢光）。初版把"截断且有回执"当通过，
    #    于是 0 行也"通过" —— 那是假判据。
    if out["rows_read"] <= 0:
        print("[FAIL] 读到 0 行 ⇒ 整份账套被静默丢弃（不是截断，是丢光）")
        ok = False
    elif out["rows_read"] < rows:
        # ③ 截断必须**有回执**，且读入量应贴近上限（防止"默默只读几十行"）
        if not out["note"]:
            print("[FAIL] 读入 %d/%d 行且**没有截断回执** ⇒ 静默截断"
                  % (out["rows_read"], rows))
            ok = False
        elif out["rows_read"] < out["max_row_cap"] - 2:
            print("[FAIL] 读入 %d 行远低于上限 %d ⇒ 上限之外的二次截断或解析缺行"
                  % (out["rows_read"], out["max_row_cap"]))
            ok = False
        else:
            print("[OK] 读入 %d/%d 行（达上限 %d），回执可见：%s"
                  % (out["rows_read"], rows, out["max_row_cap"], out["note"]))
    else:
        print("[OK] 全量读入 %d 行，无截断" % rows)
    if out["elapsed_sec"] > 300:
        print("[WARN] 耗时 %.1fs 偏长" % out["elapsed_sec"])
    print("结论：%s" % ("通过" if ok else "未通过"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
