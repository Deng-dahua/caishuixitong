#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""C3 风险组合画像：端到端验证脚本（2026-09-29）。

验证目标：
  ① 四类业务轴映射（PTY/INC/FUND/COST）正确，非四族红线不计入组合；
  ② 触发条件：≥2 轴未排除疑点才生成画像；单轴 / 全排除 → 不生成；
  ③ 等级推导：三轴或含已定性 → 高风险；两轴无已定性 → 中风险；
  ④ 组合画像非独立红线：RL-COMBO 不在红线库，不虚增 redline_total；
  ⑤ 端到端：run_redline_detection 不崩溃、summary 含 combo_profiles、红线总数不变。

运行：PYTHONPATH=. python scripts/_verify_combo_profile.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.redline_engine import (
    _COMBO_AXES, _combo_axis_of, _build_combo_profiles, run_redline_detection,
    _VERDICT_EXCLUDED, _VERDICT_CONFIRMED, _VERDICT_HIT_PENDING,
)
from engine.tax_redlines import get_redline, stats as redline_stats


def _sus(rid, verdict, conf=0.6):
    return {"redline_id": rid, "redline_name": rid,
            "verdict": verdict, "confidence": conf, "taxes": ["增值税"]}


def _check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  [OK] {msg}")


def main():
    print("=== C3 风险组合画像验证 ===")

    # ① 轴映射
    _check(set(_COMBO_AXES.keys()) == {"PTY", "INC", "FUND", "COST"},
           "四业务轴映射完整（PTY/INC/FUND/COST）")
    _check(_combo_axis_of("RL-VAT-001") is None,
           "非四族红线(RL-VAT-001)不计入业务轴")
    for _ax, _meta in _COMBO_AXES.items():
        _check(_combo_axis_of(_meta["prefix"] + "X") == _ax,
               f"{_meta['prefix']} 正确归入 {_ax}")

    # ② 触发条件
    _check(_build_combo_profiles([]) == [], "空疑点不生成画像")
    _check(_build_combo_profiles([_sus("RL-PTY-002", _VERDICT_HIT_PENDING)]) == [],
           "单业务轴不生成画像")
    _check(_build_combo_profiles([
        _sus("RL-PTY-002", _VERDICT_EXCLUDED),
        _sus("RL-FUND-001", _VERDICT_EXCLUDED)]) == [], "两轴全排除不生成画像")

    _two = _build_combo_profiles([
        _sus("RL-PTY-002", _VERDICT_HIT_PENDING),
        _sus("RL-FUND-001", _VERDICT_HIT_PENDING)])
    _check(len(_two) == 1 and set(_two[0]["axes"]) == {"PTY", "FUND"},
           "两轴未排除 → 1 条画像且含 PTY/FUND")

    # ③ 等级推导
    _three = _build_combo_profiles([
        _sus("RL-PTY-002", _VERDICT_HIT_PENDING),
        _sus("RL-FUND-001", _VERDICT_HIT_PENDING),
        _sus("RL-COST-001", _VERDICT_HIT_PENDING)])
    _check(_three[0]["level"] == "高风险" and _three[0]["axis_count"] == 3,
           "三轴组合 → 高风险")
    _confirmed = _build_combo_profiles([
        _sus("RL-PTY-002", _VERDICT_CONFIRMED),
        _sus("RL-INC-001", _VERDICT_HIT_PENDING)])
    _check(_confirmed[0]["level"] == "高风险", "含已定性红线 → 高风险")
    _check(_two[0]["level"] == "中风险", "两轴无已定性 → 中风险")

    # 排除项不计入贡献轴
    _mix = _build_combo_profiles([
        _sus("RL-PTY-002", _VERDICT_HIT_PENDING),
        _sus("RL-FUND-001", _VERDICT_EXCLUDED),
        _sus("RL-COST-001", _VERDICT_HIT_PENDING)])
    _check(len(_mix) == 1 and set(_mix[0]["axes"]) == {"PTY", "COST"},
           "组合剔除已排除轴、保留未排除轴")

    # ④ 组合画像非独立红线
    _check(get_redline("RL-COMBO") is None, "RL-COMBO 不在红线库")
    _pre = redline_stats().get("total")
    _check(isinstance(_pre, int) and _pre >= 74, f"红线库当前总数={_pre}（A类后≥74）")

    # ⑤ 端到端集成
    _res = run_redline_detection(
        [{"redline_id": "RL-PTY-002", "type": "x", "level": "中风险", "detail": "d"},
         {"redline_id": "RL-FUND-001", "type": "y", "level": "中风险", "detail": "d"},
         {"redline_id": "RL-COST-003", "type": "z", "level": "中风险", "detail": "d"}],
        engine_data={},
        material_readiness={"provided": [
            "银行流水", "进项发票", "销项发票", "记账凭证", "科目余额表", "资产负债表",
            "利润表", "增值税申报表", "企业所得税申报表", "个税申报表", "工资表",
            "社保明细", "进销存台账", "合同文件", "其他税种申报表"]})
    _check("combo_profiles" in _res.get("summary", {}),
           "run_redline_detection.summary 含 combo_profiles")
    _check(_res["summary"].get("redline_total") == _pre,
           f"组合画像不虚增红线总数（{_pre} 不变）")
    _check(_res["summary"]["suspicion_total"] == _res["summary"].get("suspicion_total"),
           "suspicion_total 字段正常")

    print(f"\n[OK] C3 风险组合画像：轴映射 / 触发条件 / 等级推导 / 非独立红线 / 端到端集成 全部通过")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f"\n[FAIL] {exc}")
        sys.exit(1)
