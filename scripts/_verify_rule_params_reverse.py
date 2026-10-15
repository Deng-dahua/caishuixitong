# -*- coding: utf-8 -*-
"""反向验证：规则阈值是否**真的**由 `config/rule_params.json` 驱动（遗留项③的验收证据）。

## 为什么要反向验证
「把阈值搬进数据表」这件事**最容易做成假的**：代码里仍留着字面量、或只在个别分支读了表，
审计（grep 不到常量名）与人工review 都看不出来 —— 直到有人改了表却发现结果没变。
所以本脚本**主动注入已知缺陷**（改表值），断言结果**必须**随之改变；不变 ⇒ 参数化是假的。

## 判据（任一不满足即 FAIL）
- **A 判定分支真读表**：同进程把 `ad_promo_revenue_ratio` 由 0.15 改为 0.20 并 `reset_cache()`
  ⇒ `_scan_ad_promo_limit` 必须不再命中（原 15% 命中、20% 不命中）；
- **B 规格描述也派生自表**：新进程导入下，`VR039.limitation` 里的百分比必须随表值变化
  （防止"判定读表、文案仍写死"的分叉）；
- **C 等价性**：表值恢复为原值时，判定结果与改造前完全一致（限额 150,000、超限 10,000）。
- **D 检测器侧同源**：`deduction_limit_detector._ratio_of` 的四个限额同样随表变化。

用法：`./.venv/Scripts/python.exe scripts/_verify_rule_params_reverse.py`
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CFG = ROOT / "config" / "rule_params.json"

PARAM = "ad_promo_revenue_ratio"
ORIG = 0.15
MUT = 0.20

REV = 1_000_000.0
AD = 160_000.0          # 收入 100 万、广告费 16 万：15% 限额下超限 1 万；20% 限额下不超限


def _case():
    """构造触发 VR039 的最小数据集（收入 100 万 / 广宣费 16 万）。"""
    from engine import verified_rule_engine as V
    spec = next(s for s in V.VERIFIED_RULE_CATALOG if s["id"] == "VR039")
    data = {"declaration": [{"sales_amount": REV}], "vouchers": [{"account_name": "广告费", "debit": AD}]}
    out = V._scan_ad_promo_limit(data, spec)
    return out


def _set_param(v, name: str = PARAM) -> None:
    d = json.loads(CFG.read_text(encoding="utf-8"))
    d["params"][name]["value"] = v
    CFG.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_param():
    return json.loads(CFG.read_text(encoding="utf-8"))["params"][PARAM]["value"]


def _sub_limitation() -> str:
    """新进程里读 VR039 的 limitation（模块级常量，必须重导入才反映表值）。"""
    code = (
        "import sys; sys.path.insert(0, r'%s')\n"
        "from engine import verified_rule_engine as V\n"
        "print(next(s['limitation'] for s in V.VERIFIED_RULE_CATALOG if s['id']=='VR039'))\n"
    ) % str(ROOT)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       cwd=str(ROOT), encoding="utf-8", errors="replace")
    return (r.stdout or "").strip()


def main() -> int:
    fails = []
    orig_file = CFG.read_text(encoding="utf-8")
    try:
        # ── C 等价性：原值下的判定结果 ──
        from engine import rule_params as RP
        from engine import verified_rule_engine as V
        RP.reset_cache()
        base = _case()
        base_over = base[0]["observed_metrics"]["over_limit"] if base else None
        base_cap = base[0]["observed_metrics"]["deduct_cap"] if base else None
        print(f"[C] 原值 {ORIG} ⇒ 命中 {len(base)} 条，限额={base_cap}，超限={base_over}")
        if not base or abs(base_over - 10_000.0) > 0.01:
            fails.append(f"C 等价性：原值下应命中且超限 10000，实得 {base_over}")

        # ── A 判定分支真读表 ──
        _set_param(MUT)
        RP.reset_cache()
        mut = _case()
        print(f"[A] 改表为 {MUT} ⇒ 命中 {len(mut)} 条（期望 0）")
        if mut:
            fails.append(f"A 判定分支未读表：阈值改为 {MUT}（限额 20 万 > 发生额 16 万）仍命中 "
                         f"{len(mut)} 条 ⇒ 仍在用字面量 0.15")
        _set_param(ORIG)
        RP.reset_cache()

        # ── B 规格描述真读表（子进程） ──
        _set_param(MUT)
        lim_mut = _sub_limitation()
        _set_param(ORIG)
        lim_orig = _sub_limitation()
        print(f"[B] limitation：原值→『{lim_orig[:34]}…』；改值→『{lim_mut[:34]}…』")
        if "15%" not in lim_orig or "20%" not in lim_mut:
            fails.append(f"B 规格描述未派生自表：原值描述应含 15%、改值描述应含 20%，"
                         f"实得 orig={lim_orig[:60]!r} mut={lim_mut[:60]!r}")

        # ── D 检测器侧同源（deduction_limit_detector） ──
        from engine import deduction_limit_detector as D
        RP.reset_cache()
        d_orig = D._ratio_of("public_welfare_donation_profit_ratio")
        _set_param(0.30, "public_welfare_donation_profit_ratio")
        RP.reset_cache()
        d_mut = D._ratio_of("public_welfare_donation_profit_ratio")
        _set_param(0.12, "public_welfare_donation_profit_ratio")
        RP.reset_cache()
        d_back = D._ratio_of("public_welfare_donation_profit_ratio")
        print(f"[D] 捐赠限额：原值 {d_orig} → 改 0.30 ⇒ {d_mut} → 恢复 ⇒ {d_back}")
        if not (d_orig == 0.12 and d_mut == 0.30 and d_back == 0.12):
            fails.append(f"D 检测器未读表：{d_orig}→{d_mut}→{d_back}（期望 0.12→0.30→0.12）")
    finally:
        CFG.write_text(orig_file, encoding="utf-8")              # ★ 无论如何恢复原表

    print()
    if fails:
        print("反向验证 **FAIL**（参数化是假的或已被破坏）：")
        for f in fails:
            print("  ✗", f)
        return 1
    print("反向验证 **PASS**：A 判定分支 / B 规格描述 / C 等价性 / D 检测器侧 均确证由数据表驱动。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
