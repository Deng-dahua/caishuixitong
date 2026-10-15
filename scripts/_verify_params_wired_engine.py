# -*- coding: utf-8 -*-
"""**模拟数据 → 引擎判定**验收（遗留项③「模拟数据后接引擎」的落地证据）。

## 验证四件事（缺一即 FAIL）
- **A 命中**：构造符合各检测器数据前提的模拟账套 ⇒ 三个检测器**各命中 1 条**，
  且 finding 带合法 `redline_id` / `constituent_hits` / 三件套字段；
- **B 不误报**：同数据的**合规版本**（亏损在 5 年内弥补 / 已按 20% 代扣 / 申报基数
  未超 80% 上限）⇒ **零命中**（防"见数就报"）；
- **C 缺一侧即静默**：只给"应付股利"不给"应交个人所得税"⇒ **零命中**
  （铁律：缺资料 ≠ 违规，且不重复报——覆盖度模块已列明缺口）；
- **D ★ 阈值真读表**：把 `rule_params` 的阈值改小/改大并 `reset_cache()`
  ⇒ **命中结果必须随之改变**（参数化是真的；不证明这一点就等于没接引擎）。
  同时校验 `engine_wired` 声明与实现一致（`params_wired_detectors.wired_params()`）。

用法：`./.venv/Scripts/python.exe scripts/_verify_params_wired_engine.py`
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CFG = ROOT / "config" / "rule_params.json"


# ───────────────────────── 模拟账套 ─────────────────────────

def sim_bad() -> dict:
    """**命中版**：三类问题各一处（金额刻意构造为刚好越过阈值）。"""
    return {
        "vouchers": [
            # 分红 100 万，但只代扣 5 万（应 20 万）
            {"account_name": "利润分配—应付股利", "credit": 1_000_000.0},
            {"account_name": "应交税费—应交个人所得税", "credit": 50_000.0},
            # 委托研发实际发生 100 万
            {"account_name": "研发支出—费用化支出—委托研发", "debit": 1_000_000.0},
        ],
        "tax_declarations": [{
            "tax_year": 2026,
            # 历年亏损台账：2019 年亏损 80 万在 2026 年弥补（逾 6 年 > 5 年）
            "prior_year_losses": [
                {"year": 2019, "loss": 800_000.0, "used": 800_000.0},
                {"year": 2024, "loss": 300_000.0, "used": 300_000.0},
            ],
            # 申报加计基数 100 万（上限应为 100 万 × 80% = 80 万）
            "entrusted_rd_base": 1_000_000.0,
        }],
    }


def sim_good() -> dict:
    """**合规版**：同类业务但不触发。"""
    return {
        "vouchers": [
            {"account_name": "利润分配—应付股利", "credit": 1_000_000.0},
            {"account_name": "应交税费—应交个人所得税", "credit": 200_000.0},   # 足额 20%
            {"account_name": "研发支出—费用化支出—委托研发", "debit": 1_000_000.0},
        ],
        "tax_declarations": [{
            "tax_year": 2026,
            "prior_year_losses": [
                {"year": 2023, "loss": 800_000.0, "used": 800_000.0},          # 3 年，未超期
            ],
            "entrusted_rd_base": 800_000.0,                                    # = 100 万 × 80%
        }],
    }


def sim_one_side() -> dict:
    """**只给一侧**：有应付股利、无应交个人所得税 ⇒ 必须静默。"""
    return {"vouchers": [{"account_name": "利润分配—应付股利", "credit": 1_000_000.0}],
            "tax_declarations": [{"tax_year": 2026}]}


def _run(data: dict):
    from engine.params_wired_detectors import detect_params_wired
    return detect_params_wired(data, None)


def main() -> int:
    ok = fail = 0

    def chk(name, cond, info=""):
        nonlocal ok, fail
        if cond:
            ok += 1
            print("  [OK] %s" % name)
        else:
            fail += 1
            print("  [FAIL] %s — %s" % (name, info))

    # ── A 命中 ──
    got = _run(sim_bad())
    rids = sorted({str(f.get("redline_id")) for f in got})
    print("[A] 命中 %d 条，红线 %s" % (len(got), rids))
    chk("A 三个检测器各命中（共 3 条）", len(got) == 3, len(got))
    chk("A 红线齐全", rids == ["RL-CIT-016", "RL-PAY-009", "RL-SPT-024"], rids)
    chk("A 均带 constituent_hits", all(f.get("constituent_hits") for f in got),
        [bool(f.get("constituent_hits")) for f in got])
    chk("A 均带三件套（处置定性/已核实事实/待举证）",
        all(f.get("finding_disposition") and f.get("verified_facts") and f.get("to_prove")
            for f in got), "缺三件套")
    chk("A 均带阈值留痕（可核验取自 rule_params）",
        all(any(k in (f.get("observed_metrics") or {})
                for k in ("carryforward_limit_years", "dividend_iit_rate",
                          "entrusted_rd_deduction_ratio")) for f in got), "缺阈值字段")

    # ── B 不误报 ──
    good = _run(sim_good())
    print("[B] 合规版命中 %d 条（期望 0）" % len(good))
    chk("B 合规版零命中", not good, [f.get("redline_id") for f in good])

    # ── C 缺一侧即静默 ──
    one = _run(sim_one_side())
    print("[C] 只给一侧命中 %d 条（期望 0）" % len(one))
    chk("C 缺一侧静默（缺资料≠违规）", not one, [f.get("redline_id") for f in one])

    # ── D 阈值真读表（反向验证）──
    from engine import rule_params as RP
    from engine.params_wired_detectors import wired_params
    chk("D 接线参数与 rule_params 登记一致",
        set(wired_params()) == {"loss_carryforward_years", "dividend_iit_rate",
                                "entrusted_rd_deduction_ratio"}, wired_params())
    orig = CFG.read_text(encoding="utf-8")
    try:
        # ① 亏损年限 5 → 10：2019 年亏损（距 2026 为 7 年）不再超期 ⇒ RL-CIT-016 应消失
        d = json.loads(orig)
        d["params"]["loss_carryforward_years"]["value"] = 10
        CFG.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        RP.reset_cache()
        got2 = _run(sim_bad())
        r2 = sorted({str(f.get("redline_id")) for f in got2})
        print("[D1] 亏损年限改 10 年 ⇒ 红线 %s（期望不含 RL-CIT-016）" % r2)
        chk("D1 亏损年限阈值真读表", "RL-CIT-016" not in r2, r2)

        # ② 分红税率 20% → 5%：代扣 5 万恰好达标 ⇒ RL-PAY-009 应消失
        d = json.loads(orig)
        d["params"]["dividend_iit_rate"]["value"] = 0.05
        CFG.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        RP.reset_cache()
        got3 = _run(sim_bad())
        r3 = sorted({str(f.get("redline_id")) for f in got3})
        print("[D2] 分红税率改 5%% ⇒ 红线 %s（期望不含 RL-PAY-009）" % r3)
        chk("D2 分红税率阈值真读表", "RL-PAY-009" not in r3, r3)

        # ③ 委托研发比例 80% → 120%：上限 120 万 > 申报 100 万 ⇒ RL-SPT-024 应消失
        d = json.loads(orig)
        d["params"]["entrusted_rd_deduction_ratio"]["value"] = 1.2
        CFG.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        RP.reset_cache()
        got4 = _run(sim_bad())
        r4 = sorted({str(f.get("redline_id")) for f in got4})
        print("[D3] 委托研发比例改 120%% ⇒ 红线 %s（期望不含 RL-SPT-024）" % r4)
        chk("D3 委托研发阈值真读表", "RL-SPT-024" not in r4, r4)
    finally:
        CFG.write_text(orig, encoding="utf-8")                  # ★ 无论如何恢复原表
        RP.reset_cache()

    # 恢复后必须回到原行为
    back = _run(sim_bad())
    chk("D4 恢复阈值后回到 3 条命中", len(back) == 3, len(back))

    print("\n验收：OK %d / FAIL %d" % (ok, fail))
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
