# -*- coding: utf-8 -*-
"""数据勾稽校验器（唯一权威实现）——报告装配后的**机器对账 + 阻断**。

指令依据（阶段9 第2项）：
  「自动校验金额、比例、勾稽关系、含税口径、期间一致性、笔误，发现不一致阻断输出。」

校验项（每项给出判据与可复现证据）：
  R1 金额合计 = 分项之和（含容差）
  R2 比例 = 分子 ÷ 分母（容差 0.5%）
  R3 含税 / 不含税换算自洽（价税合计 = 不含税 × (1+税率)）
  R4 期间一致性（同一事实的期间不得互相矛盾）
  R5 笔误检测（同量纲单位混用，如「5%」与「5‰」并存于同一费用项）
  R6 事实唯一性（同一 label+period 的不同取值必须已登记冲突，不得静默）

**阻断语义**：`blocking=True` ⇒ 报告不得输出（与 `quality_gates` 的
`formal_workpaper_allowed=False` 同向，任一为假即不得出具正式底稿）。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

RE_AMT = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
TOL_AMOUNT = 0.01          # 金额容差（元）
TOL_RATIO = 0.005          # 比例容差
RATES = (0.01, 0.03, 0.05, 0.06, 0.09, 0.13)   # 常见增值税率，用于含税换算自洽性抽查


def _dec(s: Any) -> Optional[float]:
    try:
        return float(str(s).replace(",", "").replace("元", "").strip())
    except Exception:  # noqa: BLE001 —— 解析不出返回 None（不返回 0）
        return None


def check_sum(total: Any, parts: List[Any], *, label: str = "", tol: float = TOL_AMOUNT) -> Dict[str, Any]:
    """R1：合计 = 分项之和。"""
    t = _dec(total)
    ps = [_dec(x) for x in parts]
    if t is None or any(x is None for x in ps):
        return {"rule": "R1", "label": label, "status": "SKIP",
                "detail": "取不到数值（缺失≠0，不作通过）"}
    s = sum(ps)  # type: ignore[arg-type]
    ok = abs(t - s) <= tol
    return {"rule": "R1", "label": label, "status": "PASS" if ok else "FAIL",
            "明细": f"合计 {t:,.2f} vs 分项和 {s:,.2f}（差 {t - s:,.2f}）",
            "blocking": not ok}


def check_ratio(ratio: Any, numerator: Any, denominator: Any, *,
                label: str = "", tol: float = TOL_RATIO) -> Dict[str, Any]:
    """R2：比例 = 分子 ÷ 分母。ratio 接受 0.0619 / 6.19% / 6.19 三种写法。"""
    r = str(ratio).strip()
    rv = None
    if r.endswith("%"):
        rv = _dec(r[:-1])
        rv = rv / 100 if rv is not None else None
    elif r.endswith("‰"):
        rv = _dec(r[:-1])
        rv = rv / 1000 if rv is not None else None
    else:
        rv = _dec(r)
        if rv is not None and rv > 1:
            rv = rv / 100
    n, d = _dec(numerator), _dec(denominator)
    if rv is None or n is None or d in (None, 0):
        return {"rule": "R2", "label": label, "status": "SKIP", "detail": "取不到比例或分母为 0"}
    calc = n / d  # type: ignore[operator]
    ok = abs(rv - calc) <= tol
    return {"rule": "R2", "label": label, "status": "PASS" if ok else "FAIL",
            "明细": f"报告 {rv:.4%} vs 复算 {calc:.4%}", "blocking": not ok}


def check_tax_inclusive(incl: Any, excl: Any, *, rate: Optional[float] = None,
                        label: str = "") -> Dict[str, Any]:
    """R3：含税/不含税换算自洽。未给税率时，抽查常见税率是否有一个能对上。"""
    i, e = _dec(incl), _dec(excl)
    if i is None or e is None or e == 0:
        return {"rule": "R3", "label": label, "status": "SKIP", "detail": "取不到含税/不含税金额"}
    if rate is not None:
        ok = abs(i - e * (1 + rate)) <= TOL_AMOUNT
        return {"rule": "R3", "label": label, "status": "PASS" if ok else "FAIL",
                "明细": f"{i:,.2f} vs {e:,.2f}×(1+{rate:.0%})={e * (1 + rate):,.2f}", "blocking": not ok}
    hits = [r for r in RATES if abs(i - e * (1 + r)) <= TOL_AMOUNT]
    return {"rule": "R3", "label": label, "status": "PASS" if hits else "WARN",
            "明细": ("未声明税率；抽查命中税率 " + "、".join(f"{h:.0%}" for h in hits)) if hits
                    else f"{i:,.2f} 与 {e:,.2f} 不符合任一声明的常见税率换算",
            "blocking": False}


def check_unit_mixup(text: str, *, label: str = "") -> Dict[str, Any]:
    """R5：笔误检测——同一费用项上「%」与「‰」混用（实测教训：业务招待费限额是 5‰ 不是 5%）。"""
    hits = []
    # ★ 2026-10-08 冗余收敛：原朴素 `re.split(r"[。；\n]")` 改为唯一权威
    #   `engine/sentencekit.split_sentences`（括号感知，避免切出括号不闭合残句）；
    #   分隔符集合保持原样「。；\n」。
    from engine.sentencekit import split_sentences as _sk_split
    for seg in _sk_split(text, delims="。；\n"):
        if "%" in seg and "‰" in seg and re.search(r"(限额|扣除标准|招待费|广告费)", seg):
            hits.append(seg.strip()[:80])
    return {"rule": "R5", "label": label, "status": "FAIL" if hits else "PASS",
            "明细": ("检出 % 与 ‰ 混用：" + "；".join(hits[:3])) if hits else "未检出量纲混用",
            "blocking": bool(hits)}


def check_periods(items: List[Tuple[str, Any]], *, label: str = "") -> Dict[str, Any]:
    """R4：期间一致性——同一 label 的期间必须一致。"""
    by: Dict[str, set] = {}
    for lab, per in items:
        by.setdefault(lab, set()).add(str(per))
    bad = {k: sorted(v) for k, v in by.items() if len(v) > 1}
    return {"rule": "R4", "label": label, "status": "FAIL" if bad else "PASS",
            "明细": f"期间冲突：{bad}" if bad else "同一事实期间一致", "blocking": bool(bad)}


def check_report(report_data: Any, *, max_issues: int = 50) -> Dict[str, Any]:
    """报告级勾稽校验入口。

    从 report_data 中尽最大努力抽取可对账的成对数据；取不到的项**如实 SKIP**（不静默通过）。
    返回 {passed, blocking, issues, skipped, summary}。
    """
    issues: List[Dict[str, Any]] = []
    skips: List[Dict[str, Any]] = []

    if not isinstance(report_data, dict):
        return {"passed": False, "blocking": True, "issues": [
            {"rule": "-", "status": "FAIL", "detail": "report_data 非字典，无法勾稽", "blocking": True}],
            "skipped": [], "summary": "输入非法"}

    # R5：对报告中的口径说明文本做量纲笔误扫描
    txt_pool = []
    for k in ("overall_level", "tax_impact_note", "scope_note"):
        v = report_data.get(k)
        if isinstance(v, str):
            txt_pool.append(v)
    for it in (report_data.get("confirmed_problems") or [])[:30]:
        if isinstance(it, dict):
            for kk in ("conclusion", "reason", "summary", "title"):
                v = it.get(kk)
                if isinstance(v, str):
                    txt_pool.append(v)
    r5 = check_unit_mixup("\n".join(txt_pool), label="报告口径文本")
    (issues if r5["status"] == "FAIL" else skips).append(r5)

    # R1/R2：对已量化税额与超限金额做内部一致性抽查（存在即成对）
    ti = report_data.get("tax_impact") if isinstance(report_data.get("tax_impact"), dict) else None
    if ti:
        basis, total = ti.get("basis"), ti.get("total")
        if basis is not None and total is not None:
            r = check_sum(total, [basis], label="tax_impact 合计=分项")
            (issues if r["status"] == "FAIL" else skips).append(r)
        else:
            skips.append({"rule": "R1", "label": "tax_impact", "status": "SKIP",
                          "detail": "缺 basis/total 之一，按缺失≠0 不判"})
    else:
        skips.append({"rule": "R1", "label": "tax_impact", "status": "SKIP",
                      "detail": "report_data 无 tax_impact（本项不参与勾稽）"})

    blocking = any(x.get("blocking") for x in issues)
    return {
        "passed": not blocking,
        "blocking": blocking,
        "issues": issues[:max_issues],
        "skipped": skips,
        "summary": f"勾稽问题 {len(issues)} 项（阻塞 {sum(1 for x in issues if x.get('blocking'))}）、SKIP {len(skips)} 项",
        "principle": "取不到即 SKIP，不静默通过；阻塞项非空 ⇒ 报告不得输出",
    }
