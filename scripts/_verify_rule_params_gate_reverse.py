# -*- coding: utf-8 -*-
"""反向验证：`check_rule_params_single_source` 闸门**真的会报错**（防"假闸门"）。

## 为什么必须做
一个从不报错的检查 = 没有检查。本项目已立规：「新增检查项后必须做反向验证 ——
注入已知缺陷，确认检查真的变红；不变红说明判据是假的」。

## 三段注入（每段都应让闸门报出对应 ERROR）
- **A 缺字段**：抹掉某参数的 `value` ⇒ 期望「缺 `value`」；
- **B 跨表重名**：把某参数名改成与 `config/region_params.json` 同名 ⇒ 期望「重名」；
- **D 假接入**：把 `wired_in` 指向一个**不含该参数名**的真实文件 ⇒ 期望「找不到该参数名」。

用法：`./.venv/Scripts/python.exe scripts/_verify_rule_params_gate_reverse.py`
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CFG = ROOT / "config" / "rule_params.json"


def _gate():
    from tools.audit_consistency import check_rule_params_single_source as C
    return C()


def _msgs(issues):
    return " | ".join(m for _lv, _f, m in issues)


def main() -> int:
    orig = CFG.read_text(encoding="utf-8")
    fails = []

    def _write(d):
        CFG.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    try:
        # ── A 缺字段 ──
        d = json.loads(orig)
        d["params"]["ad_promo_revenue_ratio"].pop("value", None)
        _write(d)
        iss = _gate()
        ok_a = any("ad_promo_revenue_ratio" in m and "value" in m for _l, _f, m in iss)
        print(f"[A] 抹掉 value ⇒ 报 {len(iss)} 项，命中判据={ok_a}")
        if not ok_a:
            fails.append("A 未报错：抹掉 value 后闸门未指出缺字段")

        # ── B 跨表重名 ──
        d = json.loads(orig)
        rp = json.loads((ROOT / "config" / "region_params.json").read_text(encoding="utf-8"))
        foreign = next(iter((rp.get("params") or {}).keys()))
        d["params"][foreign] = dict(d["params"]["ad_promo_revenue_ratio"])
        _write(d)
        iss = _gate()
        ok_b = any("重名" in m and foreign in m for _l, _f, m in iss)
        print(f"[B] 注入与地区表重名 `{foreign}` ⇒ 报 {len(iss)} 项，命中判据={ok_b}")
        if not ok_b:
            fails.append(f"B 未报错：参数名与 region_params 重名（{foreign}）闸门未指出")

        # ── D 假接入（wired_in 指向不含该参数名的文件） ──
        d = json.loads(orig)
        d["params"]["ad_promo_revenue_ratio"]["wired_in"] = ["engine/numparse.py"]
        _write(d)
        iss = _gate()
        ok_d = any("找不到该参数名" in m for _l, _f, m in iss)
        print(f"[D] wired_in 指向不含该参数名的文件 ⇒ 报 {len(iss)} 项，命中判据={ok_d}")
        if not ok_d:
            fails.append("D 未报错：假接入（wired_in 文件里没有该参数名）闸门未指出")

        # ── 对照：恢复原表后必须为 0 ──
        CFG.write_text(orig, encoding="utf-8")
        iss0 = _gate()
        print(f"[对照] 恢复原表 ⇒ 报 {len(iss0)} 项（期望 0）")
        if iss0:
            fails.append(f"对照失败：原表下仍报 {len(iss0)} 项 → {_msgs(iss0)[:200]}")
    finally:
        CFG.write_text(orig, encoding="utf-8")

    print()
    if fails:
        print("闸门反向验证 **FAIL**（闸门是假的或过于宽松）：")
        for f in fails:
            print("  ✗", f)
        return 1
    print("闸门反向验证 **PASS**：A 缺字段 / B 跨表重名 / D 假接入 三段均变红，恢复后归零。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
