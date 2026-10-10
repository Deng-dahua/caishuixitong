# -*- coding: utf-8 -*-
"""D12 产物级闸门的**双向反向验证**（注入 → 必须变红 → 还原 → 必须回 0）。

A. 注入「不相容却仍有金额」 ⇒ 必须报 ERROR（否则闸门抓不住没修好的情况）
B. 注入「相容却被误不估」   ⇒ 必须报 ERROR（否则闸门会把真实风险藏起来）
"""
import io
import json
import os
import shutil
import subprocess
import sys

ROOT = os.getcwd()
ART = os.path.join(ROOT, "scripts", "four_reports", "company_1_full.json")
BAK = os.path.join(ROOT, "scripts", "_rev_y4d12_keep.json")
NL = chr(10)

RUN = ("import sys; sys.path.insert(0, %r);"
       "from tools.audit_consistency import check_report_consistency as f;"
       "iss=[i for i in f() if i[0]=='ERROR']; print(len(iss));"
       "[print('   ', i[1], i[2][:86]) for i in iss]") % ROOT


def run():
    r = subprocess.run([sys.executable, "-c", RUN], capture_output=True, text=True,
                       cwd=ROOT, encoding="utf-8", errors="replace")
    return ((r.stdout or "") + (r.stderr or "")).strip()


sys.path.insert(0, ROOT)
from engine.tax_impact import infer_amount_nature as _ian

shutil.copy2(ART, BAK)
orig = io.open(BAK, "r", encoding="utf-8").read()
try:
    base = json.loads(orig)
    print("=== 基线（未注入）===")
    print(run())

    # ── A. 找一个"性质非 sales 却有增值税金额"的疑点，注入金额 ──
    d = json.loads(orig)
    ps = (d.get("enterprise_readable_report") or {}).get("confirmed_problems") or []
    tgt_a = None
    for p in ps:
        nat = _ian(p)
        if not nat or nat == "sales":
            continue
        for it in ((p.get("tax_impact") or {}).get("items") or []):
            if it.get("tax") == "增值税":
                it["amount"] = 55555.0
                it["rate"] = "0.0600"
                it["note"] = "测试注入：性质不符却给了金额"
                tgt_a = (p.get("seq"), nat)
                break
        if tgt_a:
            break
    io.open(ART, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False))
    print("")
    print("=== A 注入「不相容却仍有金额」(seq=%s, 性质=%s) ===" % tgt_a)
    print(run())

    # ── B. 找一个"性质相容且有增值税金额"的疑点，改成误不估 ──
    d2 = json.loads(orig)
    ps2 = (d2.get("enterprise_readable_report") or {}).get("confirmed_problems") or []
    tgt_b = None
    for p in ps2:
        nat = _ian(p)
        if nat != "sales":
            continue
        for it in ((p.get("tax_impact") or {}).get("items") or []):
            if it.get("tax") == "增值税" and it.get("amount") is not None:
                it["amount"] = None
                it["note"] = "测试注入：本项事实的金额口径为「sales」，与本税种要求的基数性质「sales」不符，不作加计"
                tgt_b = (p.get("seq"), nat)
                break
        if tgt_b:
            break
    io.open(ART, "w", encoding="utf-8").write(json.dumps(d2, ensure_ascii=False))
    print("")
    print("=== B 注入「相容却被误不估」(seq=%s, 性质=%s) ===" % tgt_b)
    print(run())
finally:
    shutil.copy2(BAK, ART)
    os.remove(BAK)
    print("")
    print("=== 还原后 ===")
    print(run())
    print("产物逐字节一致:", io.open(ART, "r", encoding="utf-8").read() == orig)
