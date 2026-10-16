# -*- coding: utf-8 -*-
"""合并 `config/legal_law_codes.json` 里**同一部法的重复登记**（幂等）。

## 为什么要合并（2026-10-16 实测）
同一份文件在短码表里出现两行、两个短码 —— 一行用**主题型名**
（如「关于异常增值税扣税凭证管理等有关事项的公告」），
一行用**文号型名**（如「国家税务总局公告2019年第38号」）。
后果（都是真缺陷）：
  ① `_storage_law()` 的返回值取决于**登记表行序**（`setdefault` 先到先得）
     ⇒ 同一份数据在不同机器/不同顺序下可能落到不同短码 ⇒ **不稳定**；
  ② 条款 ID 前缀二选一 ⇒ 同一部法在两次生成里给出不同的 `provision_id`；
  ③ 覆盖率按法名比对时**时对时不对**（实测导致覆盖率从 241 掉到 240）。

## 合并口径（保守、可追溯）
保留**主题型短码**（信息量大、材料与专题页已在用），
把被删行的 `name` 追加为保留行的 `alias`（保证文号/全称引用仍能解析），
并在台账 `merged_codes` 里留痕（`from_code` → `to_code` + 原因）。
**幂等**：已合并过的行不再存在，重跑为 0 改动。

用法：`./.venv/Scripts/python.exe scripts/_merge_duplicate_law_codes.py [--dry-run]`
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
REG = ROOT / "config" / "legal_law_codes.json"

#: `文号型短码 → 保留的主题型短码`（一行一部法；新增重复 ⇒ 加一行）
MERGES: Dict[str, str] = {
    "SAT-ANN-2019-38": "SAT-ABNORMAL-VOUCHER-ANN",            # 国家税务总局公告2019年第38号
    "SAT-ANN-2014-67": "EQUITY-TRANSFER-IIT-MEASURE",         # 国家税务总局公告2014年第67号
    "CS-2008-121": "MOF-CIT-RELATED-INTEREST",                # 财税〔2008〕121号
}


def main() -> int:
    dry = "--dry-run" in sys.argv
    reg = json.loads(REG.read_text(encoding="utf-8"))
    laws: List[Dict[str, Any]] = reg.get("laws") or []
    by_code = {l["code"]: l for l in laws}

    ledger: List[Dict[str, Any]] = list(reg.get("merged_codes") or [])
    done = {str(x.get("from_code")) for x in ledger}
    merged, missing = [], []
    for src, dst in MERGES.items():
        if src in done:                                      # 幂等
            continue
        if src not in by_code:
            missing.append(src)
            continue
        if dst not in by_code:
            print("!! 保留目标 `%s` 不在登记表中 ⇒ 中止（不猜）" % dst)
            return 2
        a, b = by_code[src], by_code[dst]
        keep_aliases = set(b.get("aliases") or [])
        keep_aliases.add(str(a.get("name")))
        keep_aliases.discard(str(b.get("name")))
        b["aliases"] = sorted(k for k in keep_aliases if k)
        ledger.append({"from_code": src, "to_code": dst, "from_name": a.get("name"),
                       "reason": "同一部法的**重复登记**（文号型 vs 主题型）⇒ "
                                 "保留主题型短码，文号型名并入别名；"
                                 "原 `provision_id` 前缀作废（派生层已重建）"})
        merged.append((src, dst))
        if not dry:
            laws.remove(a)

    if missing:
        print("（表内已无这些行，视为已完成）%s" % "、".join(missing))
    if not merged:
        print("无重复登记需合并（幂等：已为最新）")
        return 0
    reg["laws"] = laws
    reg["law_count"] = len(laws)
    reg["coded_count"] = len([l for l in laws if l.get("code")])
    reg["merged_codes"] = ledger
    reg["updated"] = "2026-10-16"
    if dry:
        print("[dry-run] 将合并 %d 组：%s" % (len(merged), merged))
        return 0
    REG.write_text(json.dumps(reg, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("已合并 %d 组重复登记 ⇒ 短码表 %d 部：" % (len(merged), len(laws)))
    for s, d in merged:
        print("   %s → %s" % (s, d))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
