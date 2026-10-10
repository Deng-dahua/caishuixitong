# -*- coding: utf-8 -*-
"""在**进程内**重跑 company_1 的一键分析（与前端按钮同一条主流程）。

用途：改了引擎（.py）后，让 `data/cache/last_analysis_cache.json` 与新代码一致，
      这样重启服务后前端刷新即可看到新产物，无需人工再点按钮。

为什么不用 HTTP：`/api/tax-risk-docs/analyze-start` 需要登录态（auth_token cookie），
      脚本环境拿不到；而按钮最终调用的就是 `main._execute_tax_risk_analysis`（同一函数）。

★★ 2026-10-08 重要修正（踩坑记录，勿回退）：
  首版直接 `import main` 后调 `_execute_tax_risk_analysis` —— **错**。
  因为「从磁盘恢复分析缓存 / 恢复分析历史」的代码位于 FastAPI 的
  **`lifespan` 应用启动钩子**（`@asynccontextmanager async def lifespan(app)`），
  **plain import 不会执行它** ⇒ 本进程内 `_last_analysis_cache` / `_analysis_history` 全空 ⇒
    · `round_no = max(_max_round+1, len(_hist)+1)` 算成 **1**（实际应为 6）；
    · 落盘时把 `analysis_history.json` **覆盖成 1 条**（原 5 条，明细不可恢复）。
  修法：**直接进入应用的 lifespan**（`async with main.lifespan(main.app)`），
  与服务器启动走**同一份**初始化逻辑（单一权威，不复制实现）。
  并加两道护栏：跑前**备份缓存+历史**；跑后**断言历史未缩水**。

用法：python scripts/_rerun_company1_analysis.py [company_id]
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CACHE = ROOT / "data" / "cache" / "last_analysis_cache.json"
HIST = ROOT / "data" / "cache" / "analysis_history.json"


def _hist_len() -> int:
    try:
        h = json.loads(HIST.read_text(encoding="utf-8"))
        return sum(len(v) for v in h.values()) if isinstance(h, dict) else 0
    except Exception:
        return -1


def main() -> int:
    cid = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 1
    before_hist = _hist_len()
    print("[重跑] 跑前历史条数=%d" % before_hist)

    # ── 护栏 1：跑前备份（缓存 + 历史）──
    bak = ROOT / "baseline" / "_bak"
    bak.mkdir(parents=True, exist_ok=True)
    import datetime as _dt
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    for src, tag in ((CACHE, "last_analysis_cache"), (HIST, "analysis_history")):
        if src.exists():
            dst = bak / ("%s.bak_before_rerun_%s.json" % (tag, stamp))
            shutil.copy2(src, dst)
            print("[重跑] 已备份 %s → %s" % (src.name, dst.name))

    t0 = time.time()

    async def _run():
        import main as app_main
        from database import SessionLocal
        # ★ 关键：进入应用 lifespan（= 服务器启动时的同一份初始化：init_db + 恢复缓存/历史）
        async with app_main.lifespan(app_main.app):
            from shared_state import _analysis_history, _last_analysis_cache
            print("[重跑] lifespan 内：缓存 %d 条 / 历史 %d 条"
                  % (len(_last_analysis_cache), sum(len(v) for v in _analysis_history.values())))
            db = SessionLocal()
            try:
                return app_main._execute_tax_risk_analysis(cid, db)
            finally:
                db.close()

    res = asyncio.run(_run())
    print("[重跑] 用时 %.1fs；ok=%s" % (time.time() - t0, (res or {}).get("ok")))

    rep = (res or {}).get("report") or {}
    err = rep.get("enterprise_readable_report") or {}
    oc = err.get("overall_conclusion") or {}
    ps = oc.get("paragraphs") or []
    s = err.get("summary") or {}
    cr = rep.get("compliance_round") or {}
    print("[重跑] 轮次：round_no=%s round_id=%s" % (cr.get("round_no"), cr.get("round_id")))
    print("[重跑] 第一章 %d 段 / %d 字" % (len(ps), sum(len(p) for p in ps)))
    print("[重跑] summary: 已确认=%s 已核定=%s 待核=%s 受阻=%s"
          % (s.get("confirmed_problem_count"), s.get("verified_problem_count"),
             s.get("pending_problem_count"), s.get("further_check_count")))
    print("[重跑] 自洽：待核==已确认−已核定 → %s"
          % (s.get("pending_problem_count")
             == (s.get("confirmed_problem_count", 0) - s.get("verified_problem_count", 0))))

    # ── 护栏 2：历史不得缩水 ──
    after_hist = _hist_len()
    if 0 <= before_hist and after_hist < before_hist:
        print("[重跑] !! 严重：历史条数 %d → %d 缩水，请检查 lifespan 是否被执行"
              % (before_hist, after_hist))
        return 2
    print("[重跑] 历史条数 %d → %d（未缩水）" % (before_hist, after_hist))
    return 0


if __name__ == "__main__":
    sys.exit(main())
