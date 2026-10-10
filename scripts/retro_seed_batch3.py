# -*- coding: utf-8 -*-
"""把第 3 批实测到的复发根因登记为复盘事件，并跑完整四步复盘。

用途：① 让「自我复盘与规则萃取」（任务7）在**真实事件**上跑一遍，产出 5 份文档；
② 让复发签名台账从空开始积累 —— 下一次同类事故发生时，系统能回答"这是第几次"。

事件全部来自本批的**实测事实**（不编造）：
  · 未取得从业人数/资产总额被当成"满足小微条件" ⇒ 企业所得税按 5% 低估 5 倍；
  · 线索链"资料未提供却给读数"（同类根因的另一处实现）；
  · 反向验证的变异打在**不参与判定**的分支上 ⇒ "变红失败"被误读；
  · 同一部《发票管理办法》出现「（2023修订）」与「无括注」两套法名；
  · 交付文档声称 `levy_nature` 支持 effective_from/effective_to/source，代码里没有；
  · `clue_chain` 首环判据 docstring 声称的口径与实现不符；
  · `report_dedup._covered_by` "逐字覆盖"与"双向包含"不一致。

用法：`python scripts/retro_seed_batch3.py`（幂等：已存在同 id 的事件会跳过）。
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from engine.retrospective import (  # noqa: E402
    load_events, record_event, run_retrospective,
)

_TESTS = "tests/test_batch3_skills.py"
_GATE = "tools/audit_consistency.py"

EVENTS = [
    {
        "id": "EV-20261007-0001", "date": "2026-10-07", "source": "闸门+真跑",
        "module": "engine/tax_impact.py", "severity": "high",
        "symptom": "企业所得税未验证小型微利条件即按 5% 估算（敞口低估 5 倍）",
        "root_cause": "把『从业人数/资产总额未取得』当作条件满足（未知即通过）",
        "fix": "抽出唯一权威 evaluate_small_micro：未取得即 verified=False ⇒ 回到法定 25% 上界并如实标注",
        "pattern_signature": "unknown_treated_as_pass",
        "evidence": [_TESTS + "::TestTaxEstimateSkill::test_cit_requires_smb_verification",
                     _GATE + "::check_report_consistency"],
    },
    {
        "id": "EV-20261007-0002", "date": "2026-10-07", "source": "用户点评+自检",
        "module": "engine/clue_chain.py", "severity": "high",
        "symptom": "环节写『资料未提供』却仍给出读数（动作与读数不同源）",
        "root_cause": "读数取不到对题证据时回落到 metrics[:3]/numbers[:3]（等于用不相关数字顶替）",
        "fix": "资料有无与读数有无同源判据（materials_available + _on_topic_reading）；取不到就如实标注 material_missing/engine_gap",
        "pattern_signature": "unknown_treated_as_pass",
        "evidence": [_GATE],
    },
    {
        "id": "EV-20261007-0003", "date": "2026-10-07", "source": "本轮反向验证",
        "module": "tools/audit_consistency.py", "severity": "mid",
        "symptom": "反向验证第一次跑出『0 项』，几乎被当成『闸门覆盖到了』",
        "root_cause": "变异打在**不参与判定**的分支（改 _ok 但 verified 只看 missing/failed）⇒ 被检查量根本没变",
        "fix": "换有效变异（复现旧『未知即通过』）后闸门报 2 项 ERROR；把该教训写进 PATTERN_SIGNATURES",
        "pattern_signature": "gate_ineffective_mutation",
        "evidence": [_TESTS + "::TestLegalVersioning"],
    },
    {
        "id": "EV-20261007-0004", "date": "2026-10-07", "source": "本轮普查",
        "module": "engine/tax_redlines.py", "severity": "mid",
        "symptom": "同一部《发票管理办法》在红线库里有两套法名（「（2023修订）」与无括注）",
        "root_cause": "版本信息被写进法名 ⇒ 同一部法被当成两部（多头维护，改版本必漏一处）",
        "fix": "法名统一 + 版本只登记在 config/legal_versions.json；闸门禁止『版本写进法名』",
        "pattern_signature": "single_concept_multi_impl",
        "evidence": [_TESTS + "::TestLegalVersioning::test_citations_carry_no_version_in_law_name"],
    },
    {
        "id": "EV-20261007-0005", "date": "2026-10-07", "source": "本轮自查",
        "module": "engine/levy_nature.py", "severity": "mid",
        "symptom": "交付文档声称 levy_nature 支持 effective_from/effective_to/source，实际代码里没有这些字段",
        "root_cause": "文档写了『已实现』而实现没有 ⇒ 读文档的人会以为法条版本化已完成",
        "fix": "改为真实登记表 config/legal_versions.json + 校验器 + 闸门；文档按实际改写",
        "pattern_signature": "doc_says_a_code_does_b",
        "evidence": [_TESTS + "::TestLegalVersioning::test_registry_self_audit_clean_and_core_registered"],
    },
    {
        "id": "EV-20261007-0006", "date": "2026-10-07", "source": "历史复发（本轮再次命中）",
        "module": "engine/clue_chain.py", "severity": "high",
        "symptom": "函数 docstring 声称『资料已提供则不列缺失』，实现逐字比较导致口径不符",
        "root_cause": "注释说 A、代码做 B（本项目最高频复发病根）",
        "fix": "改判据前先读 docstring 声称的口径，再逐字核对实现；纳入复盘签名以统计复发次数",
        "pattern_signature": "doc_says_a_code_does_b",
        "evidence": [_GATE],
    },
    {
        "id": "EV-20261007-0007", "date": "2026-10-07", "source": "历史复发（本轮再次命中）",
        "module": "engine/report_dedup.py", "severity": "mid",
        "symptom": "_covered_by 声称『逐字覆盖』，实现却是『双向包含』⇒ 去重判断与声称口径不一致",
        "root_cause": "同一概念（覆盖判定）在两处各写一份，注释与实现不同步",
        "fix": "收敛为唯一权威 + 薄转发；docstring 与实现逐字对齐",
        "pattern_signature": "doc_says_a_code_does_b",
        "evidence": [_GATE],
    },
]


def main() -> int:
    existing = {str(e.get("id")) for e in load_events()}
    added = 0
    for ev in EVENTS:
        if ev["id"] in existing:
            continue
        record_event(ev)
        added += 1
    print("[事件登记] 新增 %d 条，台账累计 %d 条" % (added, len(load_events())))
    r = run_retrospective(as_of="2026-10-07")
    print("[复盘产出] %s" % r["dir"])
    for name in sorted(r["files"]):
        print("   -", name)
    for c in r["clusters"]:
        print("[模式] %-28s 复发 %d 次 %s" % (
            c["pattern_signature"], c["count"], "✅升级" if c["promoted"] else "未达阈值"))
    print("[入库] %s" % {k: len(v) for k, v in r["commit"].items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
