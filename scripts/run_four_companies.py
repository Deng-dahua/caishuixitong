# -*- coding: utf-8 -*-
"""对 4 家真实公司逐一跑全量财税风险分析，并把报告结构化落盘供审阅。
仅读取 data/uploads/<id>/ 下已上传的真实资料，不涉及任何凭证类外部源。
"""
import sys, os, json, traceback

ROOT = r"c:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong"
os.chdir(ROOT)
sys.path.insert(0, ROOT)

import main
from database import SessionLocal, Company
from runtime_storage import _to_json_safe

OUT = os.path.join(ROOT, "scripts", "four_reports")
os.makedirs(OUT, exist_ok=True)

COMPANY_IDS = [1, 2, 3, 4]
CAP_KEYS = ["two_tax_income", "bank_flow", "input_voucher", "false_invoice", "fund_loop", "cross_enterprise"]


def _str(v, n=400):
    if isinstance(v, str):
        return v[:n]
    try:
        return json.dumps(v, ensure_ascii=False)[:n]
    except Exception:
        return str(v)[:n]


def capability_verdicts(comprehensive):
    """抽取 6 大能力的 available/verdict/key metrics。"""
    out = []
    for k in CAP_KEYS:
        sec = (comprehensive or {}).get(k)
        if not isinstance(sec, dict):
            continue
        avail = sec.get("available")
        verdict = sec.get("verdict") or sec.get("risk_level") or ""
        summary = sec.get("summary") or ""
        metrics = sec.get("metrics") or {}
        out.append({
            "capability": k,
            "available": avail,
            "verdict": _str(verdict, 200),
            "summary": _str(summary, 300),
            "metrics_keys": list(metrics.keys())[:12] if isinstance(metrics, dict) else [],
        })
    return out


def main_chapter_inventory(er):
    """遍历 enterprise_readable_report，列出各章节标题/available/verdict。"""
    inv = []
    if not isinstance(er, dict):
        return inv
    for k, v in er.items():
        if isinstance(v, dict):
            inv.append({
                "key": k,
                "title": _str(v.get("title") or v.get("heading") or "", 120),
                "available": v.get("available"),
                "verdict": _str(v.get("verdict") or v.get("risk_level") or "", 120),
            })
        else:
            inv.append({"key": k, "value": _str(v, 120)})
    return inv


def run_one(cid):
    db = SessionLocal()
    try:
        co = db.query(Company).filter(Company.id == cid).first()
        name = co.name if co else f"company_{cid}"
        print(f"\n===== COMPANY {cid}: {name} =====", flush=True)
        result = main._execute_tax_risk_analysis(cid, db)
        # _execute_tax_risk_analysis 可能返回 {"ok":True,"report":<data>} 或直接是 <data>
        if isinstance(result, dict) and "report" in result:
            report = result["report"]
        elif isinstance(result, dict):
            report = result  # 直接就是 report_data
        else:
            report = None
        comprehensive = report.get("comprehensive", {}) if isinstance(report, dict) else {}
        er = report.get("enterprise_readable_report", {}) if isinstance(report, dict) else {}

        # 落盘完整报告（indent 便于检索阅读）
        with open(os.path.join(OUT, f"company_{cid}_full.json"), "w", encoding="utf-8") as f:
            json.dump(_to_json_safe(report), f, ensure_ascii=False, indent=1, default=str)

        # 落盘精炼摘要
        caps = capability_verdicts(comprehensive)
        inv = main_chapter_inventory(er)
        summary = {
            "company_id": cid,
            "company_name": name,
            "capabilities": caps,
            "report_chapters": inv,
            "overall_risk": _str(report.get("risk_level") or report.get("verdict") or comprehensive.get("verdict") or "", 200),
        }
        with open(os.path.join(OUT, f"company_{cid}_summary.json"), "w", encoding="utf-8") as f:
            json.dump(_to_json_safe(summary), f, ensure_ascii=False, indent=1)

        print(f"[CAPS]", flush=True)
        for c in caps:
            print(f"  - {c['capability']:16s} avail={c['available']} verdict={c['verdict']}", flush=True)
        print(f"[CHAPTERS] total={len(inv)}", flush=True)
        for ch in inv[:40]:
            print(f"  - {ch.get('key')}: {ch.get('title','')} (avail={ch.get('available')})", flush=True)
        print(f"[OK] wrote company_{cid}_full.json + company_{cid}_summary.json", flush=True)
        return True
    except Exception as e:
        print(f"[ERROR] company {cid}: {e}", flush=True)
        traceback.print_exc()
        return False
    finally:
        try:
            db.close()
        except Exception:
            pass


if __name__ == "__main__":
    for cid in COMPANY_IDS:
        run_one(cid)
    print("\n===== ALL DONE =====", flush=True)
