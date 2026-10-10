# -*- coding: utf-8 -*-
"""批次一「下次分析自动应用」验证（Skill 1 触发条件与认定要件分离）。

## 验证什么
用户要求：**用一份新数据跑一次分析**，看本 Skill 是否自动生效（不得写"应该自动应用"）。
本仓库库内只有 1 家企业（`SELECT id FROM companies` 实测 = [1]），无法跑"另一家企业"的
真实上传资料 ⇒ 按用户许可（"可以是模拟数据"）用**合成新数据**走**同一条生产代码路径**
（`constituent_checkpoint.build_constituent_checkpoints` + `trigger_conditions.classify`），
不另写判定逻辑。

## 两个方向
1. **正例（新数据含红冲）**：合成一条新疑点（红字发票 8 张、未做进项转出），
   期望：触发条件命中 → 疑点成立；第 1 条前提条自动写「符合情形」；无"已列为疑点却无触发条件"。
2. **反例（新数据无红冲）**：同一条红线的疑点**未列示**（listed=False），
   期望：`suspicion_established=False`（不列为疑点），且不产出"符合情形"。

用法：
  ./.venv/Scripts/python.exe scripts/_demo_batch01_newdata.py
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.constituent_checkpoint import build_constituent_checkpoints   # noqa: E402
from engine.trigger_conditions import classify, is_precondition           # noqa: E402

#: 合成的"新数据"：另一家企业的红冲情形（金额/张数与库内企业不同，确保不是照抄旧产物）
NEW_CONSTITUENTS = [
    "存在红字发票或作废发票（红冲行为）",
    "红冲发生在月末、季末或申报期前后等敏感时点",
    "红冲无对应退货单、折让协议等合法事由",
    "红字发票缺《红字发票信息确认单》，或与被冲减蓝字发票不配平",
]
NEW_SOURCES = [
    "销项发票、进项发票",
    "销项发票、进项发票",
    "退货单、折让协议、拒收证明",
    "红字发票信息确认单、销项发票、进项发票",
]
#: 新数据里"已提供"的资料（与库内企业不同的组合）
NEW_AVAILABLE = ["销项发票", "进项发票", "银行流水", "增值税申报表"]
#: 新数据里"明细表"留下的硬证据（红字发票备注栏的确认单编号 —— 与库内企业不同的号码）
NEW_DETAIL = ("发票号25952000000999888777｜红冲｜价税合计-188,000.00元｜"
              "被红冲蓝字数电发票号码：25952000000999000111 "
              "红字发票信息确认单编号：44030725123000999888 来源资料：销项发票")


def _suspicion(listed: bool) -> dict:
    return {
        "redline_id": "RL-VAT-007",
        "constituents": NEW_CONSTITUENTS,
        "constituent_sources": NEW_SOURCES,
        "evidence_chain": {"available_materials": NEW_AVAILABLE, "elements": []},
        "clue_chain": {"nodes": []},
        "argumentation": {"constituent_hits": []},
        "supporting_findings": [
            {"detail": "检出8张涉及红冲/作废的发票。" + NEW_DETAIL,
             "evidence_rows": [{"source": "销项发票", "note": NEW_DETAIL}]},
        ],
    }


def main() -> int:
    print("=" * 78)
    print("【正例】合成新数据：红字发票 8 张（另一家企业的号码与金额）")
    s = _suspicion(listed=True)
    cps = build_constituent_checkpoints(s)
    c1 = cps[0]
    print("  第1条要件：%s" % str(c1.get("要件"))[:40])
    print("  → is_precondition=%s ｜ 数据源状态=%s ｜ 核对结论=%s"
          % (is_precondition("RL-VAT-007", 1, c1.get("要件")), c1.get("数据源状态"),
             c1.get("核对结论")))
    blk = classify("RL-VAT-007", cps, NEW_CONSTITUENTS,
                   reading="检出8张涉及红冲/作废的发票", listed=True, fallback_desc="红字冲销与作废发票比例异常")
    print("  触发条件命中数=%s ｜ 疑点成立=%s ｜ 风险成立=%s"
          % (blk["trigger_status"]["hit_count"], blk["suspicion_established"],
             blk["risk_established"]))
    print("  结论表述：%s" % str(blk.get("conclusion"))[:90])
    ok1 = (c1.get("_conclusion") == "checked_hit"
           and str(c1.get("核对结论")).startswith("符合情形")
           and blk["trigger_status"]["hit_count"] >= 1
           and blk["suspicion_established"] is True)
    print("  【正例判定】%s" % ("通过（前提条自动写「符合情形」+ 触发命中 + 疑点成立）" if ok1 else "不通过"))

    print("=" * 78)
    print("【反例】同一红线的疑点**未列示**（新数据里没有红冲信号）")
    blk2 = classify("RL-VAT-007", cps, NEW_CONSTITUENTS, reading="", listed=False,
                    fallback_desc="红字冲销与作废发票比例异常")
    print("  触发条件命中数=%s ｜ 疑点成立=%s" % (blk2["trigger_status"]["hit_count"],
                                                blk2["suspicion_established"]))
    ok2 = blk2["trigger_status"]["hit_count"] == 0 and blk2["suspicion_established"] is False
    print("  【反例判定】%s" % ("通过（未列示 ⇒ 不成立疑点，与「出现信号才列疑点」一致）"
                              if ok2 else "不通过"))
    return 0 if (ok1 and ok2) else 1


if __name__ == "__main__":
    raise SystemExit(main())
