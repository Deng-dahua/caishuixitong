"""行业预警指标实测校准器（2026-09-12）

用途：用**真实账套**回归出本地化的行业预警区间，替代 industry_benchmark 中的
通用参考区间，使"行业对标"从经验值升级为实测分位值（更接近税务机关的本地化模型）。

原理：
  对同一行业内各样本企业计算指标 → 取稳健分位（默认 P10 / P90）作为预警区间边界。
  用分位而非极值，避免个别异常样本把区间拉宽到失去预警意义。

用法：
  # 从 JSON 样本文件校准（推荐，样本可来自任意导出）
  python tools/calibrate_industry_benchmarks.py --from-json samples.json

  # 从数据库全量校准（需 venv，依赖 sqlalchemy）
  python tools/calibrate_industry_benchmarks.py --from-db

  # 指定分位与最少样本数
  python tools/calibrate_industry_benchmarks.py --from-db --low 10 --high 90 --min-samples 5

样本 JSON 格式（--from-json）：
  [
    {"industry": "制造业", "indicators": {"vat_burden": 2.6, "gross_margin": 18.0}},
    ...
  ]

输出：static/industry_benchmarks_calibrated.json（industry_benchmark 会自动优先加载）。
样本不足的行业不产出（沿用通用参考区间），并在终端提示。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(ROOT, "static", "industry_benchmarks_calibrated.json")

INDICATORS = ["vat_burden", "gross_margin", "expense_ratio", "purchase_sales"]


def _percentile(values: List[float], p: float) -> float:
    """线性插值分位数。"""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return s[lo] + (s[hi] - s[lo]) * frac


def collect_from_db() -> List[Dict]:
    """从数据库全量收集样本（每家企业计算一次指标）。"""
    sys.path.insert(0, ROOT)
    from database import SessionLocal  # noqa: WPS433
    from engine.industry_benchmark import compute_indicators  # noqa: WPS433

    samples: List[Dict] = []
    db = SessionLocal()
    try:
        from database import Company  # noqa: WPS433
        companies = db.query(Company).all()
        for c in companies:
            try:
                cid = getattr(c, "id", None)
                if cid is None:
                    continue
                from database import (  # noqa: WPS433
                    SalesInvoice, PurchaseInvoice, Voucher,
                )
                data = {
                    "sal_invs": [{"金额": i.amount, "税额": getattr(i, "tax", 0)}
                                 for i in db.query(SalesInvoice).filter(
                                     SalesInvoice.company_id == cid).all()],
                    "pur_invs": [{"金额": i.amount, "税额": getattr(i, "tax", 0)}
                                 for i in db.query(PurchaseInvoice).filter(
                                     PurchaseInvoice.company_id == cid).all()],
                    "vouchers": [{"科目": v.subject, "金额": v.amount}
                                 for v in db.query(Voucher).filter(
                                     Voucher.company_id == cid).all()],
                }
                ind = compute_indicators(data)
                if ind:
                    samples.append({
                        "industry": getattr(c, "industry", "") or "",
                        "indicators": ind,
                    })
            except Exception:
                continue
    finally:
        db.close()
    return samples


def calibrate(samples: List[Dict], low_p: float = 10.0, high_p: float = 90.0,
              min_samples: int = 5) -> Dict[str, Dict[str, List[float]]]:
    """按行业计算稳健分位区间。"""
    buckets: Dict[str, Dict[str, List[float]]] = defaultdict(
        lambda: defaultdict(list))
    for s in samples or []:
        industry = str(s.get("industry", "") or "").strip()
        if not industry:
            continue
        for key, val in (s.get("indicators") or {}).items():
            if key in INDICATORS and isinstance(val, (int, float)):
                buckets[industry][key].append(float(val))

    out: Dict[str, Dict[str, List[float]]] = {}
    skipped: List[str] = []
    for industry, series in buckets.items():
        n = max((len(v) for v in series.values()), default=0)
        if n < min_samples:
            skipped.append(f"{industry}({n}家)")
            continue
        out[industry] = {}
        for key, vals in series.items():
            if len(vals) < min_samples:
                continue
            lo = _percentile(vals, low_p)
            hi = _percentile(vals, high_p)
            if hi <= lo:
                hi = lo + 0.01
            out[industry][key] = [round(lo, 2), round(hi, 2)]
    if skipped:
        print(f"样本不足已跳过（沿用通用参考区间）：{'、'.join(skipped)}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="行业预警指标实测校准")
    parser.add_argument("--from-json", help="样本 JSON 文件路径")
    parser.add_argument("--from-db", action="store_true", help="从数据库全量校准")
    parser.add_argument("--low", type=float, default=10.0, help="下分位（默认 P10）")
    parser.add_argument("--high", type=float, default=90.0, help="上分位（默认 P90）")
    parser.add_argument("--min-samples", type=int, default=5, help="每行业最少样本数")
    args = parser.parse_args()

    if args.from_json:
        with open(args.from_json, "r", encoding="utf-8") as f:
            samples = json.load(f)
    elif args.from_db:
        samples = collect_from_db()
    else:
        parser.error("必须指定 --from-json 或 --from-db")
        return 2

    if not samples:
        print("无有效样本，未生成校准表")
        return 1

    result = calibrate(samples, args.low, args.high, args.min_samples)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"已生成校准表：{OUT_PATH}")
    for ind, vals in result.items():
        print(f"  {ind}:")
        for k, v in vals.items():
            print(f"    {k}: {v[0]} ~ {v[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
