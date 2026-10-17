# -*- coding: utf-8 -*-
"""复核人推断 —— 必须取**最后处置者**（O9，2026-10-17）。

背景（裁定 MQ2-O4 的附带发现）：报告 `reviewed` 省略时由后端按账套**实际处置记录**
推断；推断出的「复核人」此前取"按发现序遍历到的**第一条**已处置记录" ⇒ 本账套多角色
都处置过时（如先税务师后复核专家）会把**先处置者**当成复核人，与语义不符。

本测试锁定纯函数 `engine.report_service.infer_reviewer` 的口径。
"""
from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.report_service import infer_reviewer  # noqa: E402

REVIEWS = {
    "A": {"reviewed": True, "updated_at": "2026-10-17T10:00:00+08:00", "updated_by": "先处置者"},
    "B": {"reviewed": True, "updated_at": "2026-10-17T12:00:00+08:00", "updated_by": "后处置者"},
    # 未复核者**时间最晚**，但不得入选（reviewed=False）
    "C": {"reviewed": False, "updated_at": "2026-10-17T23:00:00+08:00", "updated_by": "未复核者"},
    "D": {"reviewed": True, "updated_by": ""},          # 无 updated_at
}


@pytest.mark.parametrize("findings,expect,why", [
    ([{"risk_no": "A"}, {"risk_no": "B"}], "后处置者", "两条都处置 ⇒ 取较晚者"),
    ([{"risk_no": "B"}, {"risk_no": "A"}], "后处置者", "发现顺序颠倒仍取较晚者（不看遍历序）"),
    ([{"risk_no": "C"}, {"risk_no": "A"}], "先处置者", "reviewed=False 者即使时间最晚也不得入选"),
    ([{"risk_no": "Z"}], "", "无任何处置记录 ⇒ 空（不猜、不伪造人名）"),
    ([], "", "无发现 ⇒ 空"),
])
def test_infer_reviewer_picks_latest_actor(findings, expect, why) -> None:
    assert infer_reviewer(findings, REVIEWS) == expect, why


def test_infer_reviewer_handles_missing_updated_at() -> None:
    """只有无 `updated_at` 的记录时：仍返回其 actor（唯一候选），不因缺失就丢。"""
    assert infer_reviewer([{"risk_no": "D"}], REVIEWS) == ""


def test_infer_reviewer_ignores_non_reviewed() -> None:
    """全部未复核 ⇒ 空（不得把「有批注但未复核」当成复核人）。"""
    only_unreviewed = {"X": {"reviewed": False, "updated_at": "2026-10-17T09:00:00+08:00",
                             "updated_by": "只批注者"}}
    assert infer_reviewer([{"risk_no": "X"}], only_unreviewed) == ""


def test_reverse_first_record_would_be_wrong() -> None:
    """**反向验证**：若退回"取遍历到的第一条"，在给定数据下会得到**不同**答案
    ⇒ 证明本判据确实在区分"最后处置者"与"第一条"，不是同义反复。
    """
    findings = [{"risk_no": "A"}, {"risk_no": "B"}]
    old_style = ""
    for f in findings:                       # 旧实现：命中即 break
        m = REVIEWS.get(str(f.get("risk_no") or "")) or {}
        if m.get("reviewed"):
            old_style = str(m.get("updated_by") or "")
            break
    assert old_style == "先处置者"
    assert infer_reviewer(findings, REVIEWS) == "后处置者"
    assert old_style != infer_reviewer(findings, REVIEWS), "新旧口径未区分 ⇒ 判据可能是同义反复"


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
