# -*- coding: utf-8 -*-
"""反向验证 `tools.audit_consistency.check_clause_compliance` —— **每轮独立子进程**。

为什么必须子进程：同进程内改文件后 `from engine.report_pipeline import SKIP_KEYS`
取的是 **sys.modules 缓存**（第一次导入时的值），会造成假红/假绿。
本脚本每轮：备份 → 注入破坏 → **子进程**跑闸门 → 还原。
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
CODE = ("from tools.audit_consistency import check_clause_compliance as g\n"
        "iss=g()\n"
        "print('N=%d' % len(iss))\n"
        "for lv,f,m in iss[:3]: print('  [%s] %s' % (lv, m[:88]))\n")


def run_gate() -> str:
    r = subprocess.run([PY, "-c", CODE], cwd=str(ROOT),
                       capture_output=True, text=True, encoding="utf-8", errors="ignore")
    return (r.stdout or "").strip() or ("(无输出) " + (r.stderr or "")[-200:])


CASES = [
    ("变异1 SKIP_KEYS 去掉 verdict",
     "engine/report_pipeline.py",
     '    "verdict", "suggestion", "confidence_formula",',
     '    "verdict2", "suggestion", "confidence_formula",'),
    ("变异2 编号回退 _seq + 1",
     "engine/report_pipeline.py",
     'where = f"R{_seq if isinstance(_seq, int) and _seq >= 1 else idx}"',
     'where = f"R{(_seq + 1) if isinstance(_seq, int) else idx}"'),
    ("变异3 术语表改字",
     "config/conclusion_grades.json",
     '"terms": [\n      "风险信号",',
     '"terms": [\n      "风险线索",'),
    ("变异4 update_knowledge 不传 case",
     "main.py",
     "update_knowledge(_problems, None, sample_id=str(company_id), case=_case)",
     "update_knowledge(_problems, None, sample_id=str(company_id))"),
    ("变异5 删效力声明",
     "engine/enterprise_report.py",
     "本报告不替代税务机关依法定程序作出的认定；是否达到相应标准，",
     "本报告不具有行政执法文书的效力；是否达到相应标准，"),
    ("变异6 duplicate_rate 去掉三项",
     "engine/dedup_pipeline.py",
     '        "章节统计": {"总章节": len(per_ch), "参与判定章节": len(judged),',
     '        "章节统计X": {"总章节": len(per_ch), "参与判定章节": len(judged),'),
    ("变异7 去掉通用口径上提",
     "engine/report_pipeline.py",
     "    _rln = merge_report_level_notes(items, log)",
     "    _rln = {}"),
    ("变异8 术语被通俗化改写",
     "engine/plain_language.py",
     '(r"待核(?!验|线索|事项)", "须核对"),',
     '(r"待核(?!验|线索)", "须核对"),'),
]


def main() -> int:
    print("— 正常态 —")
    print(run_gate())
    ok = 0
    for name, rel, old, new in CASES:
        p = ROOT / rel
        snap = p.read_text(encoding="utf-8")
        if old not in snap:
            print("\n%-30s → ❌ 锚点未命中（验证本身失效）" % name)
            continue
        try:
            p.write_text(snap.replace(old, new, 1), encoding="utf-8")
            out = run_gate()
        finally:
            p.write_text(snap, encoding="utf-8")
        hit = "N=0" not in out
        print("\n%-30s → %s" % (name, "✅ 报红" if hit else "❌ 未报红（闸门失效）"))
        if hit:
            ok += 1
        print("\n".join("    " + x for x in out.splitlines()[:3]))
    print("\n— 还原后 —")
    print(run_gate())
    print("\n反向验证通过 %d/%d" % (ok, len(CASES)))
    return 0 if ok == len(CASES) else 1


if __name__ == "__main__":
    sys.exit(main())
