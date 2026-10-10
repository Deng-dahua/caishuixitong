# -*- coding: utf-8 -*-
"""P0-A 规则版本留痕 —— 反向验证（改坏⇒必红）与端到端取证。

证明三件事：
  R31：从 `config/rule_versions.json` 删掉一条已发布规则 ⇒ `check_rule_version_coverage` **必须 ERROR**
       （证明"未登记即红灯"这条判据是活的，不是恒真）。篡改后逐字节还原。
  R32：抹掉 `rule_set_version` ⇒ **必须 ERROR**（否则报告无法自证规则集口径）。
  R33：端到端 —— 未登记规则的 finding 进报告载荷后，`rule_version` 块必须**列出**该 id
       （证明"未登记"不会被静默吞掉）。

跑法：`.venv/Scripts/python.exe _rev_verify_p0a.py`
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from tools.audit_consistency import check_rule_version_coverage as CHECK  # noqa: E402
from engine import rule_versions as RV                                   # noqa: E402

VERSIONS = ROOT / "config" / "rule_versions.json"
_PASS, _FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (_PASS if ok else _FAIL).append(name)
    print("  %s %s%s" % ("PASS" if ok else "FAIL", name,
                         ("  | " + detail) if (detail and not ok) else ""))


def main() -> int:
    orig = VERSIONS.read_bytes()
    try:
        # ── 基线 ──────────────────────────────────────────────────────
        print("\n[R31a] 基线：版本表完整 ⇒ 门禁必须无 ERROR")
        base = CHECK()
        check("基线无 ERROR", [i for i in base if i[0] == "ERROR"] == [], repr(base[:2]))

        # ── R31：删一条已发布规则 ⇒ 必红 ─────────────────────────────
        print("\n[R31b] 从版本表删掉 RL-VAT-001 ⇒ 门禁必须 ERROR（未登记即红灯）")
        try:
            d = json.loads(orig.decode("utf-8"))
            assert "RL-VAT-001" in d["rules"], "样本规则不存在，检查样本选择"
            del d["rules"]["RL-VAT-001"]
            VERSIONS.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            got = CHECK()
            hit = any(i[0] == "ERROR" and "RL-VAT-001" in i[2] for i in got)
            check("抓「已发布规则未登记版本」", hit, repr(got[:2]))
        finally:
            VERSIONS.write_bytes(orig)
        check("还原后无 ERROR", [i for i in CHECK() if i[0] == "ERROR"] == [])

        # ── R32：抹掉 rule_set_version ⇒ 必红 ───────────────────────
        print("\n[R32] 抹掉 rule_set_version ⇒ 门禁必须 ERROR")
        try:
            d = json.loads(orig.decode("utf-8"))
            d["rule_set_version"] = ""
            VERSIONS.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            got = CHECK()
            check("抓「未登记 rule_set_version」",
                  any(i[0] == "ERROR" and "rule_set_version" in i[2] for i in got), repr(got[:2]))
        finally:
            VERSIONS.write_bytes(orig)
        check("还原后无 ERROR", [i for i in CHECK() if i[0] == "ERROR"] == [])

        # ── R33：端到端 —— 未登记规则不得被静默吞掉 ─────────────────
        print("\n[R33] 端到端：未登记规则的 finding ⇒ 报告载荷须列出该 id")
        import tax_risk as T
        RV.reload()
        findings = [{"redline_id": "RL-VAT-001", "level": "中风险"},
                    {"rule_id": "ZZ-NOT-REGISTERED-1", "level": "低风险"}]
        payload = T._report_payload(
            company_id=1, period_start="2025-01", period_end="2025-06",
            summary=T._report_summary(findings, 0, analysis_available=True),
            results=findings)
        blk = payload.get("rule_version") or {}
        check("已登记规则带出版本", blk.get("hit_rule_versions", {}).get("RL-VAT-001") == RV.version_of("RL-VAT-001"),
              json.dumps(blk, ensure_ascii=False)[:200])
        check("未登记规则被显式列出（未静默吞掉）",
              "ZZ-NOT-REGISTERED-1" in (blk.get("unregistered_rule_ids") or []),
              json.dumps(blk, ensure_ascii=False)[:200])
        check("规则集版本随载荷输出", blk.get("rule_set_version") == RV.rule_set_version())

    finally:
        VERSIONS.write_bytes(orig)

    # ── 最终还原自证 ────────────────────────────────────────────────
    same = VERSIONS.read_bytes() == orig
    check("版本表已逐字节还原", same)
    check("还原后门禁无 ERROR", [i for i in CHECK() if i[0] == "ERROR"] == [])

    print("\n%s" % ("=" * 62))
    print("P0-A 反向验证：%d PASS / %d FAIL" % (len(_PASS), len(_FAIL)))
    if _FAIL:
        for f in _FAIL:
            print("  FAILED: %s" % f)
        return 1
    print("★ 全部通过：判据非恒真（改坏⇒变红已自证），且版本表已完整还原。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
