"""Validate rule structure and create a human review queue without changing semantics."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RULE_FILE = ROOT / "static" / "tax_risk_rules_local_export.json"
REPORT_DIR = ROOT / "reports"
REQUIRED = {
    "id", "item", "category", "level", "score", "policy_ref", "direction",
    "drill_questions", "evidence", "determination", "action", "remedy",
}
VALID_LEVELS = {"低风险", "中风险", "高风险", "极高风险"}


def main() -> int:
    rules = json.loads(RULE_FILE.read_text(encoding="utf-8"))
    ids = [str(rule.get("id")) for rule in rules]
    duplicate_ids = sorted(item for item, count in Counter(ids).items() if count > 1)
    missing = []
    invalid_levels = []
    review = []
    levels = Counter()
    scores = Counter()
    for rule in rules:
        rule_id = rule.get("id")
        absent = sorted(field for field in REQUIRED if not rule.get(field))
        if absent:
            missing.append({"id": rule_id, "fields": absent})
        level = str(rule.get("level", ""))
        score = float(rule.get("score", 0) or 0)
        levels[level] += 1
        scores[str(rule.get("score"))] += 1
        if level not in VALID_LEVELS:
            invalid_levels.append({"id": rule_id, "level": level})
        reasons = []
        if level == "极高风险" and score < 8:
            reasons.append("极高风险但评分低于8")
        if level == "中风险" and score >= 9:
            reasons.append("中风险但评分不低于9")
        if len(str(rule.get("policy_ref", ""))) < 30:
            reasons.append("法规依据过短")
        if "待核验" in str(rule.get("policy_ref", "")):
            reasons.append("法规依据标记为待核验")
        if reasons:
            review.append({
                "id": rule_id,
                "item": rule.get("item", ""),
                "level": level,
                "score": score,
                "reasons": "；".join(reasons),
            })

    total = len(rules)
    high_ratio = (
        levels.get("高风险", 0) + levels.get("极高风险", 0)
    ) / total if total else 0
    warnings = []
    if high_ratio > 0.80:
        warnings.append(
            f"高风险与极高风险占比 {high_ratio:.1%}，会削弱规则优先级区分度；"
            "建议由税务、审计和法务联合分批复核。"
        )
    report = {
        "file": RULE_FILE.name,
        "total": total,
        "required_fields": sorted(REQUIRED),
        "duplicate_ids": duplicate_ids,
        "missing_required_fields": missing,
        "invalid_levels": invalid_levels,
        "level_distribution": dict(levels),
        "score_distribution": dict(sorted(scores.items())),
        "high_or_extreme_ratio": round(high_ratio, 6),
        "review_queue_count": len(review),
        "warnings": warnings,
        "result": "pass" if not (duplicate_ids or missing or invalid_levels) else "fail",
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "rule_quality_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with (REPORT_DIR / "rule_review_queue.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("id", "item", "level", "score", "reasons"))
        writer.writeheader()
        writer.writerows(review)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
