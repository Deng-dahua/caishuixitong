# -*- coding: utf-8 -*-
"""初始化规则版本登记表 `config/rule_versions.json`（一次性迁移）。

规则 id 来源（**只认已发布的真实规则**，不猜）：
  · 税务红线 `engine/tax_redlines.REDLINES`（RL-*）
  · 已验证原子规则 `engine/verified_rule_engine.VERIFIED_RULE_CATALOG`（VR*）
  · 缺口探测器 `engine/gap_risk_detectors.DETECTORS` 的 id（多为 RL-*，与红线重合）
  · 专项关键词探测 `engine/special_redline_detectors.SPECS` 的 id（同为 RL-*）

初版全部登记为 `1.0.0` / `effective_from=2026-10-10` / `changed_note=初始登记`；
**新增同类对象 = 加一行数据**。跑完断言条数，不符即失败。
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine.tax_redlines import REDLINES                      # noqa: E402
from engine.verified_rule_engine import VERIFIED_RULE_CATALOG as VR_CATALOG  # noqa: E402
from engine import gap_risk_detectors as GAP                   # noqa: E402
from engine import special_redline_detectors as SPEC           # noqa: E402

OUT = ROOT / "config" / "rule_versions.json"
EFFECTIVE = "2026-10-10"
RULE_SET_VERSION = "2026.10"


def _ids() -> dict:
    """返回 {rule_id: 来源层}。同一 id 出现在多层时保留首个来源并计数。"""
    got: dict = {}

    def put(rid, layer):
        rid = str(rid or "").strip()
        if rid and rid not in got:
            got[rid] = layer

    for r in REDLINES:
        put(r.get("id"), "tax_redlines")
    for s in VR_CATALOG:
        put(s.get("id"), "verified_rule_engine")
    for rid, _fn in getattr(GAP, "DETECTORS", []):
        put(rid, "gap_risk_detectors")
    for it in (getattr(SPEC, "SPECS", None) or []):
        if isinstance(it, dict):
            put(it.get("id") or it.get("redline_id"), "special_redline_detectors")
    return got


def main() -> int:
    ids = _ids()
    assert len(ids) >= 150, "规则 id 过少，疑似取数失败：%d" % len(ids)
    rules = {
        rid: {
            "version": "1.0.0",
            "effective_from": EFFECTIVE,
            "changed_note": "初始登记（P0-A 规则版本留痕闭环）",
            "layer": layer,
        }
        for rid, layer in sorted(ids.items())
    }
    doc = {
        "schema": 1,
        "name": "规则版本登记表（唯一权威）",
        "purpose": (
            "为每条已发布规则登记版本与生效日，使 finding 能自证「本结论当时按哪版规则计算」。"
            "此前只有 trace_id / Provenance / 法规版本 / 报告版本，缺规则版本。"),
        "discipline": [
            "★ 新增同类对象 = 加一行数据，不改逻辑分支。",
            "★ 未登记的 rule_id：finding 必须显式标 `rule_version=未登记`（status=unregistered），"
            "**绝不用默认版本静默顶替**（否则等于伪造版本溯源）。",
            "★ 无 rule_id 的发现（域分析等）标 `rule_version_status=not_applicable`，不制造假归属。",
            "规则**内容一改，必须同步改本表 version 并追加 rule_set_history**（门禁 check_rule_version_coverage 校验覆盖率）。",
        ],
        "rule_set_version": RULE_SET_VERSION,
        "rule_set_history": [
            {
                "version": RULE_SET_VERSION,
                "date": EFFECTIVE,
                "note": "P0-A 引入规则版本留痕；初版为全部已发布规则登记 1.0.0。",
            }
        ],
        "counts": dict(Counter(rules[r]["layer"] for r in rules)),
        "rules": rules,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[init] 写入 %s" % OUT.relative_to(ROOT))
    print("[init] 规则条数: %d" % len(rules))
    print("[init] 分层计数: %s" % doc["counts"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
