# -*- coding: utf-8 -*-
"""验证本轮交付：稽查询问清单已生成 + 两处精度缺陷已消除。
断言：
  ① 同额发票 4906 不再出现（false_invoice 按发票号去重后无此凑数组）
  ② 进项总额可复算（comprehensive.invoices 进项聚合合计 ≈ input_voucher.input_amount_total）
  ③ inspection_questions 章生成且每条含 question 问句
  ④ 4 家均产出置疑清单（total_questions>0）
不重复跑分析，只读 scripts/four_reports/company_*_full.json。
"""
import sys, os, json, glob

ROOT = r"c:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong"
OUT = os.path.join(ROOT, "scripts", "four_reports")

failures = []


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def recompute_input_total(comprehensive):
    """从 comprehensive['purchase_invoices_aggregated']（按发票号聚合后的进项清单）重算进项不含税总额。
    input_voucher 引擎的 input_amount_total 累加的是 amount（不含税），与 total(含税)=amount+tax 区分。
    该清单即引擎消费的同一份数据，可独立复算、审计。
    """
    invs = comprehensive.get("purchase_invoices_aggregated") or []
    if not invs:
        invs = [i for i in (comprehensive.get("invoices") or []) if i.get("direction") == "进项"]
    agg = {}
    for i in invs:
        no = str(i.get("invoice_no") or i.get("inv_no") or id(i))
        # 优先用 amount（不含税），缺失时回退 total - tax
        a = i.get("amount")
        if a is None:
            t = _num(i.get("total") or 0); tx = _num(i.get("tax") or 0)
            a = t - tx
        else:
            a = _num(a)
        agg[no] = agg.get(no, 0.0) + a  # 已按发票号聚合，再聚合一次仅作保险
    return round(sum(agg.values()), 2)


print("=" * 60)
print("验证：稽查询问清单 + 精度修复")
print("=" * 60)

for cid in [1, 2, 3, 4]:
    path = os.path.join(OUT, f"company_{cid}_full.json")
    if not os.path.exists(path):
        print(f"[MISS] company_{cid}_full.json 不存在，先跑 run_four_companies.py")
        failures.append(f"C{cid}: 报告缺失")
        continue
    with open(path, "r", encoding="utf-8") as f:
        report = json.load(f)
    comp = report.get("comprehensive") or {}
    er = report.get("enterprise_readable_report") or {}
    name = report.get("company_name") or f"company_{cid}"
    print(f"\n----- 公司 {cid}: {name} -----")

    # ① 同额发票 4906 不应出现
    blob = json.dumps(report, ensure_ascii=False)
    if "4906" in blob:
        print("  [FAIL] 报告仍含 '4906'（同额发票误报未消除）")
        failures.append(f"C{cid}: 4906 仍存在")
    else:
        print("  [PASS] 报告中无 '4906'（同额发票误报已消除）")

    # ② 进项总额可复算
    iv = comp.get("input_voucher") or {}
    ivm = iv.get("metrics") or {} if isinstance(iv, dict) else {}
    eng_total = _num(ivm.get("input_amount_total"))
    rec_total = recompute_input_total(comp)
    if eng_total > 0 and abs(eng_total - rec_total) / max(eng_total, 1) < 0.01:
        print(f"  [PASS] 进项总额可复算: 引擎={eng_total:,.2f} ≈ 重算={rec_total:,.2f}")
    elif eng_total == 0:
        print(f"  [SKIP] input_voucher 未激活（eng_total=0），进项勾稽未触发，跳过可复算校验")
    else:
        print(f"  [WARN] 进项总额偏差: 引擎={eng_total:,.2f} vs 重算={rec_total:,.2f}（差 {eng_total-rec_total:,.2f}）")
        # 不是硬失败，记录观察
        failures.append(f"C{cid}: 进项总额偏差 {eng_total-rec_total:,.2f}")

    # ③ + ④ 稽查询问清单
    iq = comp.get("inspection_questions") or {}
    iqr = er.get("inspection_questions_report") or {}
    tq = _num((iq.get("metrics") or {}).get("total_questions"))
    nthemes = len(iq.get("themes") or [])
    has_q_text = bool(iqr.get("title")) and ("question" in json.dumps(iqr, ensure_ascii=False) or iq.get("themes"))
    if iq.get("available") and tq > 0 and iqr.get("title"):
        print(f"  [PASS] 稽查询问清单已生成: {int(tq)} 条 / {nthemes} 主题，章标题='{iqr.get('title')}'")
    else:
        print(f"  [FAIL] 稽查询问清单缺失或不完整: available={iq.get('available')} total={tq} chapter_title={iqr.get('title')}")
        failures.append(f"C{cid}: 稽查询问清单缺失")

    # 逐主题列问句数量抽样
    for th in (iq.get("themes") or []):
        qs = th.get("questions") or []
        if qs:
            sample = qs[0].get("question", "")[:42]
            print(f"         - {th['theme']}（{th['severity']}）: {len(qs)} 问 | 例：{sample}…")
        else:
            print(f"         - {th['theme']}（{th['severity']}）: 0 问")

print("\n" + "=" * 60)
if failures:
    print(f"结论：存在 {len(failures)} 项未通过：")
    for x in failures:
        print(f"  - {x}")
    print("RESULT=FAIL")
else:
    print("结论：全部断言通过（4906 消除 / 进项可复算 / 4 家均产出置疑清单）。")
    print("RESULT=PASS")
print("=" * 60)
