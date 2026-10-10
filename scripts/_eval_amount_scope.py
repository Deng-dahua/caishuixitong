# -*- coding: utf-8 -*-
"""只读核验：**税额口径**（P0-1）修复前后的差异 —— 全部调用**真实函数**，不重新实现判据。

为什么要"真实函数"：本项目铁律「判据口径必须与去重/测算口径同口径」。若核验脚本自己再写
一套 `infer_amount_is_tax`/`inclusive` 逻辑，就会变成"同义反复的假判据"（验证的是脚本，
不是产品）。故本脚本只调 `engine.tax_impact` 的公开函数。

做法（A/B 定义）：
  · **A（修复前）**= 产物里**已落盘的** `tax_impact`（由修复前的代码产出）；
  · **B（修复后）**= 用**当前代码**在同一批问题对象上重算 `tax_impact`。
  两者输入完全一致，故差异 100% 来自代码改动。
  ⚠ B 不含报告层（`enterprise_report`）对"红冲/作废线索"追加的注记，故比较只针对**测算部分**。

输出：
  ① 逐项 `infer_amount_is_tax` / `inclusive` 判定与命中词（可回溯到子句）；
  ② A/B 税额明细差异（basis / 分税种金额 / 合计）；
  ③ 汇总：翻转项数、金额变动项数、进出敞口合计。

用法：.venv/Scripts/python.exe scripts/_eval_amount_scope.py [产物路径...]
"""
import sys, io, json, glob, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from engine.tax_impact import (
    extract_amount_from_problem, normalize_basis, estimate_tax,
    infer_amount_nature, infer_amount_is_tax, _TAX_AMOUNT_KW, _INCLUSIVE_KW,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _arts(argv):
    if argv:
        return [a for a in argv if os.path.exists(a)]
    out = []
    for pat in ("scripts/four_reports/*_full.json", "baseline/_bak/*.json"):
        out += sorted(glob.glob(os.path.join(ROOT, pat)))
    return [p for p in out if "summary" not in os.path.basename(p)]


def _load(path):
    d = json.load(open(path, encoding="utf-8"))
    rep = d.get("report") if isinstance(d.get("report"), dict) else d
    er = (rep or {}).get("enterprise_readable_report") or {}
    rc = ((rep or {}).get("comprehensive") or {}).get("tax_rate_context") or {}
    return er.get("confirmed_problems") or [], rc


def _items(ti):
    return {i.get("tax"): i.get("amount") for i in (ti.get("items") or [])}


total = {"flip_is_tax": 0, "flip_incl": 0, "money_changed": 0,
         "amt_A": 0.0, "amt_B": 0.0, "n": 0}

for path in _arts(sys.argv[1:]):
    probs, rc = _load(path)
    if not probs:
        continue
    print("=" * 118)
    print("产物：%s  （疑点 %d 项，vat_rate=%s）"
          % (os.path.relpath(path, ROOT), len(probs), rc.get("vat_rate")))
    print("=" * 118)
    print("%-4s %-26s %-6s %-6s %-8s %-8s %-12s %s"
          % ("seq", "标题", "旧is_tax", "新is_tax", "旧incl", "新incl", "basis A→B", "命中/口径"))
    print("-" * 118)
    _sub = {"n": 0, "flip_is_tax": 0, "flip_incl": 0, "money": 0, "A": 0.0, "B": 0.0}
    for p in probs:
        if not isinstance(p, dict):
            continue
        total["n"] += 1
        ti_old = p.get("tax_impact") or {}
        am = extract_amount_from_problem(p) or {}
        norm = normalize_basis(am, rc)
        _is_tax_new = infer_amount_is_tax(p)
        ti_new = estimate_tax(norm.get("amount"), p.get("taxes"), rate_ctx=rc,
                              amount_nature=infer_amount_nature(p),
                              amount_is_tax=_is_tax_new)
        # 旧 inclusive：产物里没存，用"旧口径"（只看匹配片段）重建，仅为诊断展示
        _frag = str(am.get("context") or "")
        incl_old = any(k in _frag for k in _INCLUSIVE_KW) if am else False
        incl_new = bool(am.get("inclusive"))
        # 旧 is_tax：用"整段命中"重建（旧实现），仅为诊断展示
        _blob = " ".join(str(p.get(k) or "") for k in
                         ("title", "finding_type", "detail", "suspect", "taxes"))
        is_tax_old = any(k in _blob for k in _TAX_AMOUNT_KW)
        if is_tax_old != _is_tax_new:
            total["flip_is_tax"] += 1
            _sub["flip_is_tax"] += 1
        if incl_old != incl_new:
            total["flip_incl"] += 1
            _sub["flip_incl"] += 1
        _bA, _bB = ti_old.get("basis"), ti_new.get("basis")
        _iA, _iB = _items(ti_old), _items(ti_new)
        # `available` 在产物里可能是 None（旧代码）也可能是 False（新代码），二者等价，
        # 不得因类型差异把"没有金额"误报成"金额变动"。
        _avA, _avB = bool(ti_old.get("available")), bool(ti_new.get("available"))
        _diff = (_iA != _iB) or (_avA != _avB) or (_bA != _bB)
        if _diff:
            total["money_changed"] += 1
            _sub["money"] += 1
        total["amt_A"] += (ti_old.get("total") or 0.0)
        total["amt_B"] += (ti_new.get("total") or 0.0)
        _sub["n"] += 1
        _sub["A"] += (ti_old.get("total") or 0.0)
        _sub["B"] += (ti_new.get("total") or 0.0)
        _hit = ([k for k in _TAX_AMOUNT_KW if k in (str(am.get("clause") or "") + " " + _frag)]
                if am else [])
        _incl_kw = [k for k in _INCLUSIVE_KW if k in (str(am.get("clause") or "") + " " + _frag
                                                     + str(am.get("context") or ""))]
        _tag = ("is_tax命中%s" % _hit) if _hit else ""
        if incl_new and not incl_old:
            _tag += " incl↑" + str([k for k in _INCLUSIVE_KW if k in str(am.get("clause") or "")])
        print("%-4s %-26s %-6s %-6s %-8s %-8s %-12s %s"
              % (p.get("seq"), str(p.get("title"))[:24], is_tax_old, _is_tax_new,
                 incl_old, incl_new,
                 ("%s→%s" % (_bA, _bB)) if _bA != _bB else str(_bA),
                 _tag or ("改动" if _diff else "同")))
        if _diff:
            print("      A: %s  合计 %s"
                  % ([(k, v) for k, v in _iA.items()], ti_old.get("total")))
            print("      B: %s  合计 %s"
                  % ([(k, v) for k, v in _iB.items()], ti_new.get("total")))
            if norm.get("scope_note"):
                print("      口径: %s" % norm["scope_note"])
            if _frag or am.get("clause"):
                print("      片段: %s ｜ 子句: %s" % (_frag, str(am.get("clause"))[:90]))
    print("-" * 118)
    print("本产物：%d 项 ｜ is_tax 翻转 %d ｜ inclusive 翻转 %d ｜ 税额变动 %d ｜ 敞口 %s → %s"
          % (_sub["n"], _sub["flip_is_tax"], _sub["flip_incl"], _sub["money"],
             round(_sub["A"], 2), round(_sub["B"], 2)))

print("=" * 118)
print("汇总：疑点 %d 项 ｜ is_tax 判定翻转 %d ｜ inclusive 判定翻转 %d ｜ 税额明细变动 %d"
      % (total["n"], total["flip_is_tax"], total["flip_incl"], total["money_changed"]))
print("      逐项合计之和：修复前 %s → 修复后 %s"
      % (round(total["amt_A"], 2), round(total["amt_B"], 2)))
