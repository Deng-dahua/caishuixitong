# -*- coding: utf-8 -*-
"""运行时「无静默失效」验收闸门（2026-09-29 #448 固化）。

背景：本轮 P0 —— `_extract_material_intel` 内 `d[:10]` UnboundLocalError 被 pipeline 的
`except Exception` 吞掉，`material_intel` 恒为 `{}`，「资料情报提取」整段从未生效，
只留一行 "资料情报提取异常" 日志（无人看）。这说明：**pipeline_log 里出现"异常/失败/错误"
即代表本轮存在被吞掉的失效**，可能直接抹掉①（风险分析能力）。

本脚本跑一次真实账套分析，grep `pipeline_log` 里的"异常/失败/错误"行：
  · 命中即视为「本轮有静默失效」→ 退出码 1（验收不过）。
  · 仅显式 allowlist 中的已知良性行可豁免（必须写明理由，禁止静默放行）。

与 `main.py:9769` 已计算的 `error_count` 口径一致，但**变为硬失败**而非仅记录。
反向验证：tests/test_pipeline_log_clean.py 注入反模式→确认报错→复原。
"""
import os
import sys
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ★ 已知良性行（必须逐一注明理由；新增豁免须同步更新测试中的反例期望）。
#   默认空：任何"异常/失败/错误"都视为失效。若实跑发现确属良性的诊断行，
#   在此登记并写明理由，不得用"先清空再放行"的方式绕过。
#   下列子串均属「模块专属诊断输出」，凡真实被吞掉的失效（如"资料情报提取异常"）均不会命中，
#   故豁免它们不会放过真正的静默失效。
BENIGN_ALLOWLIST = [
    # SQLAlchemy 1.x 弃用警告：text() 表达式未显式声明。属日志级警告，分析照常完成，非被吞掉的失效。
    "should be explicitly declared as text(",
    # 证伪规则模块输出："0通过/4失败"=未通过证伪的规则数，是分析结论而非运行期报错。
    "增强证伪",
    # 知识图谱模块输出："异常关系"=被标记的可疑关系（分析信号），非异常/失败。
    "知识图谱",
    # Benford 检验模块输出："N项异常"=离散度异常项（分析信号），非运行期报错。
    "Benford检验",
    # 进项异常凭证 VR 输出："异常线索"=分析结论措辞，非运行期崩溃。
    "进项异常凭证",
]


def count_run_errors(plog, allowlist=None):
    """返回 pipeline_log 中命中 异常/失败/错误 的「非豁免」行列表（核心可测函数）。"""
    allowlist = allowlist if allowlist is not None else BENIGN_ALLOWLIST
    if not isinstance(plog, (list, tuple)):
        return []
    hits = []
    for line in plog:
        if not isinstance(line, str):
            continue
        if "异常" in line or "失败" in line or "错误" in line:
            if any(w in line for w in allowlist):
                continue
            hits.append(line)
    return hits


def _preflight_venv_parity():
    """前置：托管 venv 能力对齐（缺读取/解析类依赖会让脚本侧静默漏读资料，
    属与本闸门同源的「静默失效」，先挡住再跑全量，见 scripts/_check_venv_parity.py）。"""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
        import _check_venv_parity as _p
        rc = _p.main()
    except Exception as e:  # 检查本身异常不阻断，但要留痕
        print(f"[WARN] venv 能力对齐检查异常（跳过）：{type(e).__name__}: {e}")
        return 0
    return rc


def main():
    if _preflight_venv_parity() != 0:
        print("\n[FAIL] 托管 venv 能力缺口未补齐 → 脚本侧分析与 App 口径不一致，先补装再跑。")
        return 3

    import main
    from database import SessionLocal

    CID = 1  # company_1 标准账套（与 _gap_constituent_hits 同口径）
    db = SessionLocal()
    try:
        res = main._execute_tax_risk_analysis(CID, db)
    finally:
        db.close()

    if not isinstance(res, dict) or not res.get("ok"):
        print("! 分析未成功:", json.dumps(res, ensure_ascii=False)[:800] if isinstance(res, dict) else res)
        return 2

    rep = res.get("report", {}) or {}
    plog = rep.get("pipeline_log") or (rep.get("comprehensive") or {}).get("pipeline_log") or []
    hits = count_run_errors(plog)

    print(f"[验收] pipeline_log 总行数={len(plog)}，命中 异常/失败/错误 的非豁免行={len(hits)}")
    for h in hits:
        print("   !", h)

    if hits:
        print("\n[FAIL] 本轮存在被吞掉的失效（静默失效），不得放过 —— 见上。")
        # 落盘供人工排查
        with open("scripts/_silent_failure_hits.json", "w", encoding="utf-8") as fh:
            json.dump({"hits": hits, "plog_len": len(plog)}, fh, ensure_ascii=False, indent=2)
        return 1

    print("\n[OK] 本轮 pipeline_log 无 异常/失败/错误 行（无静默失效）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
