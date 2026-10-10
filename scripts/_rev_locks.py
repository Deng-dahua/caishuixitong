# -*- coding: utf-8 -*-
"""两道新闸门的反向验证（不验证的闸门等于白设 —— 今天已经吃过这个亏）。

A. 人为在报告结论层塞一条「已触碰税务违规红线」 ⇒ ① 必须报 ERROR；
B. 人为造一条「数据源状态=已有 且 核对结论含未单独核对」 ⇒ ② 必须报 ERROR；
C. 还原后必须回到 0 项，且产物**逐字节一致**。
"""
import io
import json
import os
import shutil
import subprocess
import sys

ROOT = os.getcwd()
ART = os.path.join(ROOT, "scripts", "four_reports", "company_1_full.json")
BAK = os.path.join(ROOT, "scripts", "_rev_locks_keep.json")
NL = chr(10)

RUN = ("import sys; sys.path.insert(0, %r);"
       "from tools.audit_consistency import check_report_consistency as f;"
       "iss=[i for i in f() if i[0]=='ERROR']; print(len(iss));"
       "[print('   ', i[1], i[2][:80]) for i in iss]") % ROOT


def run():
    r = subprocess.run([sys.executable, "-c", RUN], capture_output=True, text=True,
                       cwd=ROOT, encoding="utf-8", errors="replace")
    return ((r.stdout or "") + (r.stderr or "")).strip()


shutil.copy2(ART, BAK)
orig = io.open(BAK, "r", encoding="utf-8").read()
try:
    print("=== 基线（未破坏）===")
    print(run())

    d = json.loads(orig)
    cp = (d.get("enterprise_readable_report") or {}).get("confirmed_problems") or []
    # A：报告结论层塞触红
    cp[0]["verdict"] = "已触碰税务违规红线（测试注入）"
    io.open(ART, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False))
    print("")
    print("=== A 注入「报告层触红」===")
    print(run())

    # B：造「已有却判未单独核对」
    d2 = json.loads(orig)
    cp2 = (d2.get("enterprise_readable_report") or {}).get("confirmed_problems") or []
    for _p in cp2:
        for _n in (_p.get("narrative_paragraphs") or []):
            for _t in (_n.get("detail_tables") or []):
                if "独立核对表" in str((_t or {}).get("title") or ""):
                    _t.setdefault("rows", []).append({
                        "要件序号": "第99条", "构成要件": "注入用例",
                        "独立数据源": "注入资料", "数据源状态": "已有",
                        "核对结论": "未单独核对（测试注入）",
                    })
                    io.open(ART, "w", encoding="utf-8").write(
                        json.dumps(d2, ensure_ascii=False))
                    print("")
                    print("=== B 注入「已有却判未单独核对」===")
                    print(run())
                    break
            else:
                continue
            break
        else:
            continue
        break
finally:
    shutil.copy2(BAK, ART)
    os.remove(BAK)
    print("")
    print("=== 还原后 ===")
    print(run())
    print("产物逐字节一致:", io.open(ART, "r", encoding="utf-8").read() == orig)
