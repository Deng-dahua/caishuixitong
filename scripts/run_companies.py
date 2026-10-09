# -*- coding: utf-8 -*-
"""对**库里实际存在的**每一家公司跑全量财税风险分析，并把报告结构化落盘供审阅。
仅读取 data/uploads/<id>/ 下已上传的真实资料，不涉及任何凭证类外部源。

★★ 2026-10-06（用户质疑「哪里来的四家」）：**企业清单必须由数据派生，不得硬编码**。
  旧版写死 `COMPANY_IDS = [1, 2, 3, 4]` —— 而当前库里只有 1 家（id=1 某传媒企业数字传媒）。
  后果（差点发生）：对不存在的 id 跑分析 → 取不到公司档案 → 返回的失败字典
  （`{"ok": false, …}`）会被当成"报告"**写进 `company_{id}_full.json`**，
  把 09-30 遗留的、有历史意义的产物**覆盖成垃圾**（id=2/3 的报告企业名分别是
  「中山市达冠纺织有限公司」「北京桦橙佳业商贸有限公司」，当前库里已无此档案与资料）。
  ⇒ 现在：① 企业清单 = `SELECT id FROM companies`；
     ② **只有 `ok` 且拿到报告字典才允许写入**；失败一律不落盘、只打印。
  用法：
    ./.venv/Scripts/python.exe scripts/run_companies.py            # 全部在库企业
    ./.venv/Scripts/python.exe scripts/run_companies.py 1 3        # 只跑指定 id
"""
import sys, os, json, traceback

ROOT = r"c:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong"
os.chdir(ROOT)
sys.path.insert(0, ROOT)

import main
from database import SessionLocal, Company
from runtime_storage import atomic_write_json

OUT = os.path.join(ROOT, "scripts", "four_reports")
os.makedirs(OUT, exist_ok=True)

CAP_KEYS = ["two_tax_income", "bank_flow", "input_voucher", "false_invoice", "fund_loop", "cross_enterprise",
            "revenue_authenticity"]


def _company_ids_from_db():
    """库里**真实存在**的企业 id 清单（升序）。这是"跑哪几家"的唯一来源。"""
    db = SessionLocal()
    try:
        return [int(r.id) for r in db.query(Company.id).order_by(Company.id).all()]
    finally:
        db.close()


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
        if co is None:
            # ★ 库里没有这家 ⇒ **绝不跑、绝不落盘**（跑了只会把历史产物覆盖成失败字典）
            print(f"\n[SKIP] company {cid}：数据库中不存在该企业档案（不跑、不落盘）", flush=True)
            return False
        name = co.name
        print(f"\n===== COMPANY {cid}: {name} =====", flush=True)
        result = main._execute_tax_risk_analysis(cid, db)
        # ★ 失败守卫：只有"成功且真拿到报告字典"才允许落盘。
        #   旧版无论成败都往下走 ⇒ 失败字典被当成"报告"写进正式产物（差点覆盖 2/3 的遗留产物）。
        if isinstance(result, dict) and result.get("ok") is False:
            print(f"[FAIL] company {cid}：分析未成功（{str(result.get('error') or result)[:160]}）"
                  f"—— 不落盘（保留既有产物）", flush=True)
            return False
        # _execute_tax_risk_analysis 可能返回 {"ok":True,"report":<data>} 或直接是 <data>
        if isinstance(result, dict) and isinstance(result.get("report"), dict):
            report = result["report"]
        elif isinstance(result, dict):
            report = result  # 直接就是 report_data
        else:
            report = None
        if not isinstance(report, dict) or not report.get("comprehensive"):
            print(f"[FAIL] company {cid}：未产出可用报告（{type(report).__name__}）"
                  f"—— 不落盘（保留既有产物）", flush=True)
            return False
        # 崩溃判据（本项目既有约定）：顶层 overall_level 为 {"ok": false} 即崩
        _lv = report.get("overall_level")
        if isinstance(_lv, dict) and _lv.get("ok") is False:
            print(f"[FAIL] company {cid}：overall_level={_lv!r} ⇒ 本轮分析崩溃 —— 不落盘", flush=True)
            return False
        comprehensive = report.get("comprehensive", {}) or {}
        er = report.get("enterprise_readable_report", {}) or {}

        # 落盘完整报告（indent=1 便于检索阅读）
        # ★ 2026-10-06：改走**唯一落盘实现** `atomic_write_json`（fsync + 原子替换）。
        #   此前手写 `open(...,"w")` 非原子 —— 磁盘写满/中断会把**正式产物截断**
        #   （实测 company_1_full.json 被截成 3110 字节、只剩 4 个键）。
        atomic_write_json(os.path.join(OUT, f"company_{cid}_full.json"), report, indent=1)

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
        atomic_write_json(os.path.join(OUT, f"company_{cid}_summary.json"), summary, indent=1)

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
    # 企业清单来源：① 命令行显式给出 ② 否则 = 库里实际存在的全部企业（**不硬编码**）
    _argv = [a for a in sys.argv[1:] if not a.startswith("-")]
    ids = [int(a) for a in _argv] if _argv else _company_ids_from_db()
    print("将分析的企业 id：%r（来源：%s）"
          % (ids, "命令行" if _argv else "数据库 companies 表"), flush=True)
    ok_n = 0
    for cid in ids:
        if run_one(cid):
            ok_n += 1
    print("\n===== DONE：成功 %d / 共 %d =====" % (ok_n, len(ids)), flush=True)
    sys.exit(0 if ok_n == len(ids) else 1)
