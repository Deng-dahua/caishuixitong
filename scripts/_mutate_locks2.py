# -*- coding: utf-8 -*-
"""上轮三件事一次做完（短行写法，规避括号/换行陷阱）。

③ 补资料清单：依赖度 0 的行不再一律丢弃 ——
   只要该疑点**确实存在未核对要件**，就保留这些行并**如实标注**
   「未挂到具体要件（该资料是证据链要求）」；一个未核对要件都没有时才返回 None。
   （上轮只放宽了状态过滤，4/26 未变 ⇒ 真正原因是"名字与要件数据源对不上"，
     那属于"该资料未被任何要件单独依赖"，如实标注比丢掉更有用。）
①② 两道闸门：报告结论层不得触红 / 数据源已有却判未单独核对必须为 0。
   全部用短行写，避免长拼接。
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NL = chr(10)
CRLF = chr(13) + chr(10)


def swap(path, pairs):
    p = os.path.join(ROOT, path)
    raw = io.open(p, "r", encoding="utf-8", newline="").read()
    crlf = CRLF in raw
    t = raw.replace(CRLF, NL)
    for _i, _p in enumerate(pairs):
        tag, old, new = (_p if len(_p) == 3 else (str(_i + 1), _p[0], _p[1]))
        c = t.count(old)
        if c != 1:
            print("!! %s 命中 %d 次" % (tag, c))
            sys.exit(2)
        t = t.replace(old, new, 1)
    io.open(p, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
    print("OK " + path)


# ══ ③ 依赖度 0 的行：保留并如实标注 ═══════════════════════════════════
OLD3 = (
    '    _zero = [r for r in out_rows if int(r["依赖度（条）"]) == 0]' + NL +
    '    out_rows = [r for r in out_rows if int(r["依赖度（条）"]) > 0]' + NL +
    '    if not out_rows:' + NL +
    '        return None'
)
NEW3 = (
    '    _rows_unchecked = [r for r in _rows_cp' + NL +
    '                      if isinstance(r, dict)' + NL +
    '                      and "未单独核对" in str(r.get("核对结论") or "")]' + NL +
    '    if not _rows_unchecked:' + NL +
    '        return None' + NL +
    '    _zero = [r for r in out_rows if int(r["依赖度（条）"]) == 0]' + NL +
    '    for _z in _zero:' + NL +
    '        _z["关联未核对要件"] = "未挂到具体要件"' + NL +
    '        _z["补齐后可核什么"] = "该资料是证据链要求，未被任何单条要件单独依赖"'
)
swap("engine/enterprise_report.py", [(OLD3, NEW3)])

# ══ ①② 闸门（短行）════════════════════════════════════════════════════
ANCH = '                           "剔除了汇总行却未如实披露（不得静默少算）"))'
GATE_LINES = [
    ANCH,
    NL,
    '        # ④ 分层口径 + D13 复发防护（2026-10-04，短行写法）',
    '        try:',
    '            import json as _j5',
    '            _a5 = ROOT / "scripts" / "four_reports" / "company_1_full.json"',
    '            if not _a5.exists():',
    '                issues.append(("WARN", "scripts/four_reports/company_1_full.json",',
    '                               "无真跑产物，跳过分层口径与 D13 防护校验"))',
    '            else:',
    '                _d5 = _j5.loads(_a5.read_text(encoding="utf-8", errors="replace"))',
    '                _cp5 = _d5.get("enterprise_readable_report") or {}',
    '                _ps5 = _cp5.get("confirmed_problems") or []',
    '                for _p5 in _ps5:',
    '                    _v5 = str(_p5.get("verdict") or "")',
    '                    if "已触碰税务违规红线" in _v5:',
    '                        issues.append(("ERROR", "enterprise_readable_report",',
    '                                       "报告结论层出现触红断言 seq=%s" % _p5.get("seq")))',
    '                _b5 = 0',
    '                for _p5 in _ps5:',
    '                    for _n5 in (_p5.get("narrative_paragraphs") or []):',
    '                        for _t5 in (_n5.get("detail_tables") or []):',
    '                            _tt5 = str((_t5 or {}).get("title") or "")',
    '                            if "独立核对表" not in _tt5:',
    '                                continue',
    '                            for _r5 in ((_t5 or {}).get("rows") or []):',
    '                                _c5 = str(_r5.get("核对结论") or "")',
    '                                _s5 = str(_r5.get("数据源状态") or "")',
    '                                if "未单独核对" in _c5 and _s5 == "已有":',
    '                                    _b5 += 1',
    '                if _b5:',
    '                    issues.append(("ERROR", "enterprise_readable_report",',
    '                                   "数据源已有却判未单独核对 %d 条" % _b5))',
    '        except Exception as _e5:',
    '            issues.append(("ERROR", "tools/audit_consistency.py",',
    '                           "分层口径/D13 防护断言失败: %s" % _e5))',
]
swap("tools/audit_consistency.py", [(ANCH, NL.join(GATE_LINES))])
print("[DONE] ③ + ①② 已落地")
