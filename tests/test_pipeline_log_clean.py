# -*- coding: utf-8 -*-
"""回归闸门：运行时「无静默失效」验收（pipeline_log 不得出现 异常/失败/错误）。

背景（2026-09-29 #448 P0）：`_extract_material_intel` 的 UnboundLocalError 被
pipeline 的 `except Exception` 吞掉，`material_intel` 恒为 `{}`，只留一行
"资料情报提取异常" 日志（无人看）。⇒ pipeline_log 出现 异常/失败/错误 即代表
本轮存在被吞掉的失效，可能直接抹掉①（风险分析能力）。

本测试反向验证 `scripts/_verify_run_no_silent_failure.count_run_errors`：
  · 干净日志 → 返回空（验收过）。
  · 注入"异常/失败/错误"反模式 → 必须命中（闸门真能拦）。
  · allowlist 豁免 → 显式登记行不误杀（但默认空，不允许静默放行）。
"""
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)

_spec = importlib.util.spec_from_file_location(
    "vrf", os.path.join(SCRIPTS, "_verify_run_no_silent_failure.py")
)
vrf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vrf)


def test_clean_log_passes():
    plog = [
        "[统一主流程] 场景执行门禁通过：12 项结论进入后续阶段",
        "[验收] 五项标准未全部达标: {...}",
        "资料情报提取完成：识别 6 类情报",
    ]
    assert vrf.count_run_errors(plog) == []


def test_injected_exception_is_caught():
    """反向验证：注入"异常"反模式 → 必须被拦（不能静默放过）。"""
    plog = ["[隔离] 资料情报提取异常: 'd' is not defined"]
    hits = vrf.count_run_errors(plog)
    assert hits, "闸门未拦住 injected 异常行 —— 闸门是假的"
    assert "资料情报提取异常" in hits[0]


def test_injected_failure_and_error_caught():
    plog = [
        "Excel/CSV 解析失败: PermissionError",
        "结构分析错误: 表头缺失",
    ]
    hits = vrf.count_run_errors(plog)
    assert len(hits) == 2


def test_allowlist_exempts_known_benign():
    """allowlist 中显式登记（写明理由）的良性行不误杀；但必须显式，不得静默。"""
    plog = ["[调试] 预期内的解析重试异常（已恢复）"]
    # 默认 allowlist 为空 → 仍命中
    assert vrf.count_run_errors(plog) == plog
    # 显式豁免 → 放行
    assert vrf.count_run_errors(plog, allowlist=["预期内的解析重试异常（已恢复）"]) == []


def test_non_list_safe():
    assert vrf.count_run_errors(None) == []
    assert vrf.count_run_errors("not a list") == []
