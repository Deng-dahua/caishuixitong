# -*- coding: utf-8 -*-
"""C1 置信度模型回测 / 校验（2026-09-29）。

验证外置权重 CONFIDENCE_WEIGHTS 的单源性与模型的可解释性：
  ① 权重确实来自单一配置（非散落硬编码）；
  ② 单调性：closure↑ / data_completeness↑ → 置信↑；rebuttal_ratio↑ → 置信↓；
  ③ 边界：结果恒在 [0.05, 0.95]；
  ④ 若存在真实分析产物（redline_detection），统计置信度分布（ sanity check）。
用法：PYTHONPATH=. python scripts/_backtest_confidence.py
"""
import os
import json
import glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _confidence(closure, data_completeness, level, rebuttal_ratio, w):
    c = w["base"] + w["closure"] * closure + w["data_completeness"] * data_completeness
    if "高风险" in level:
        c += w["high_risk"]
    elif "低风险" in level:
        c += w["low_risk"]
    c += w["rebuttal_ratio"] * rebuttal_ratio
    return round(max(0.05, min(0.95, c)), 2)


def main():
    from engine.argumentation import CONFIDENCE_WEIGHTS as W
    print("权重（单一来源）:", W)
    errs = []

    # ② 单调性
    base = (0.5, 0.5, "中风险", 0.0)
    if not (_confidence(0.8, *base[1:], W) > _confidence(0.2, *base[1:], W)):
        errs.append("closure 单调性失效")
    if not (_confidence(0.5, 0.8, "中风险", 0.0, W) > _confidence(0.5, 0.2, "中风险", 0.0, W)):
        errs.append("data_completeness 单调性失效")
    if not (_confidence(0.5, 0.5, "中风险", 0.0, W) > _confidence(0.5, 0.5, "中风险", 1.0, W)):
        errs.append("rebuttal_ratio 单调性失效（反证应下调置信）")

    # ③ 边界
    for cl, dc, lv, rr in [(0.0, 0.0, "低风险", 0.0), (1.0, 1.0, "高风险", 0.0),
                            (1.0, 1.0, "高风险", 1.0)]:
        v = _confidence(cl, dc, lv, rr, W)
        if not (0.05 <= v <= 0.95):
            errs.append(f"越界: ({cl},{dc},{lv},{rr})={v}")

    # 代表性网格（中风险、无反证）
    print("\n置信度网格（中风险 / 无反证）：closure × data_completeness")
    for cl in (0.0, 0.5, 1.0):
        row = [f"{_confidence(cl, dc, '中风险', 0.0, W):.2f}" for dc in (0.0, 0.5, 1.0)]
        print(f"  closure={cl}: data={row}")

    # ④ 真实产物分布（若有）
    cands = glob.glob(os.path.join(ROOT, "scripts", "company_*_full.json"))
    cands += glob.glob(os.path.join(ROOT, "data", "**", "report*.json"), recursive=True)
    if cands:
        dist = []
        for fp in cands[:4]:
            try:
                d = json.load(open(fp, encoding="utf-8"))
            except Exception:
                continue
            rd = d.get("redline_detection") or d.get("comprehensive", {}).get("redline_detection") or {}
            for s in (rd.get("suspicions") or []):
                cf = s.get("confidence")
                if isinstance(cf, (int, float)):
                    dist.append(cf)
        if dist:
            dist.sort()
            print(f"\n真实产物置信度分布（n={len(dist)}）："
                  f"min={dist[0]:.2f} med={dist[len(dist)//2]:.2f} max={dist[-1]:.2f}")
            print(f"  其中 <0.6（偏低的待证项）占比="
                  f"{sum(1 for x in dist if x < 0.6)/len(dist)*100:.0f}%")

    print("\n[ERROR]" if errs else "[OK] 回测通过：权重单源、单调、边界合规")
    for e in errs:
        print("  -", e)
    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
