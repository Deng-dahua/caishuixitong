# -*- coding: utf-8 -*-
"""疑点7 D12 改动的端到端产出 diff（只读脚本，不改任何产物）。

对比改动前后两份 `company_1_full.json`：
  A. **税额锚定未被带偏**（记忆铁律：改报告文案必须做 tax_impact 全量 diff，
     变值项数须为 0，除非本次就是要改它）——逐疑点比 `tax_impact`；
  B. **D12 目标变更确实发生**——RL-CIT-004 疑点的 `rebuttals` / §四 正文；
  C. **无误伤**——其余疑点的标题/正文关键锚点未变。

用法：python scripts/_d12_diff.py
"""
import io
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
BEFORE = os.path.join(BASE, "_bk_d12", "company_1_full.baseline.json")
AFTER = os.path.join(BASE, "four_reports", "company_1_full.json")
sys.stdout.reconfigure(encoding="utf-8")


def load(p):
    with io.open(p, encoding="utf-8") as f:
        return json.load(f)


def problems(d):
    out = []
    seen = set()
    for path in (("enterprise_readable_report", "confirmed_problems"),
                 ("enterprise_readable_report", "unconfirmed"),
                 ("enterprise_readable_report", "one_sided_digest", "items")):
        cur = d
        ok = True
        for k in path:
            if isinstance(cur, dict):
                cur = cur.get(k)
            else:
                ok = False
                break
            if cur is None:
                ok = False
                break
        if ok and isinstance(cur, list):
            for p in cur:
                if isinstance(p, dict):
                    key = (str(p.get("title") or ""), str(p.get("redline_id") or ""))
                    if key not in seen:
                        seen.add(key)
                        out.append(p)
    return out


def main():
    b, a = load(BEFORE), load(AFTER)
    print("顶层 overall_level: before=%s after=%s" % (
        json.dumps(b.get("overall_level"), ensure_ascii=False),
        json.dumps(a.get("overall_level"), ensure_ascii=False)))
    pb, pa = problems(b), problems(a)
    print("疑点条数: before=%d after=%d" % (len(pb), len(pa)))

    # ── A. tax_impact 全量 diff（必须 0 变值） ──
    idx = lambda lst: [str(p.get("title") or "")[:40] for p in lst]
    tb, ta = idx(pb), idx(pa)
    changed_tax = []
    for i, p in enumerate(pb):
        if i >= len(pa):
            break
        if tb[i] != ta[i]:
            continue
        if json.dumps(p.get("tax_impact"), ensure_ascii=False, sort_keys=True) != \
           json.dumps(pa[i].get("tax_impact"), ensure_ascii=False, sort_keys=True):
            changed_tax.append(tb[i])
    print("\n[A] tax_impact 变值项数 = %d %s" % (
        len(changed_tax), "（应为 0）" if not changed_tax else changed_tax))

    # ── B. D12/D2 目标变更（按发现 type「贡献率偏低」定位，不靠标题——标题本轮已改） ──
    print("\n[B] 目标疑点（发现 type 含「贡献率偏低」）：")

    def find_target(lst):
        for p in lst:
            blob = json.dumps(p, ensure_ascii=False)
            if "贡献率偏低" in blob and ("narrative_paragraphs" in p):
                return p
        return None

    for tag, lst in (("before", pb), ("after", pa)):
        p = find_target(lst)
        if not p:
            print("  %s: 未定位到目标疑点" % tag)
            continue
        print("  [%s] title = %s" % (tag, str(p.get("title"))[:96]))
        txt = ""
        for par in (p.get("narrative_paragraphs") or []):
            if isinstance(par, dict) and str(par.get("heading") or "").startswith("四"):
                txt = str(par.get("text") or "")
        i = txt.find("通常可以说明")
        print("       §四「通常可以说明」句 = %s" % ("仍在" if i >= 0 else "已消除"))
        if i >= 0:
            print("         %s" % txt[i:i + 110].replace("\n", " "))
        # §五 待办首条与"前提"相关项
        bl = []
        for par in (p.get("narrative_paragraphs") or []):
            if isinstance(par, dict):
                bl += [str(x) for x in (par.get("bullets") or [])]
        print("       §五 含「核实…前提」= %s" % any("前提" in x for x in bl))

    # ── C. 其他疑点正文是否被误伤 ──
    print("\n[C] 其他疑点 §四 正文是否变化：")
    n_diff = 0
    for i, p in enumerate(pb):
        if i >= len(pa) or tb[i] != ta[i]:
            continue
        g = lambda d: [str(x.get("text") or "") for x in (d.get("narrative_paragraphs") or [])
                       if isinstance(x, dict) and str(x.get("heading") or "").startswith("四")]
        if g(p) != g(pa[i]):
            n_diff += 1
            print("  变化: %s" % tb[i])
    print("  §四 变化疑点数 = %d（预期仅 RL-CIT-004 一条）" % n_diff)


if __name__ == "__main__":
    main()
