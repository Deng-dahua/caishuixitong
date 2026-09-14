# -*- coding: utf-8 -*-
"""VR009「银行流水余额滚动关系不一致」根治回归验证。

根治要点：
  - 识别层（main.py::_parse_bank_sheet）新增本户账号(holder_account)/户名/行名识别；
  - 解析入口（main.py::_parse_by_content）与 pipeline 给每行打 statement_id（来源对账单）；
  - 规则层（verified_rule_engine::_scan_bank_balance_rollforward）按
    statement_id > holder_account > account 分组。

本脚本用真实 transfer 数据直接驱动规则函数，验证：误报归零、真实错录仍可检出。
"""
import json, os, copy, glob, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"C:\Users\Administrator\WorkBuddy\2026-08-04-21-37-33\caishuixitong")
from engine.verified_rule_engine import _scan_bank_balance_rollforward

TR = r"C:\Users\Administrator\WorkBuddy\2026-08-04-21-37-33\caishuixitong\data\uploads\transfer"
spec = {"id": "VR009", "name": "银行流水余额滚动关系不一致", "required_sources": []}


def run(rows):
    return _scan_bank_balance_rollforward({"bank_txs": rows}, spec)


def load_bank_rows(tag_statement=False):
    """加载全部 transfer 文件的银行流水行；可选打 statement_id=文件名。"""
    out = []
    for p in sorted(glob.glob(os.path.join(TR, "*.json"))):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        if str(d.get("type", "")) not in ("bank_statement", "bank", "bank_transaction"):
            continue
        rows = d.get("rows", []) or []
        if not isinstance(rows, list):
            continue
        for r in rows:
            if not isinstance(r, dict):
                continue
            try:
                float(str(r.get("balance")).replace(",", ""))
            except Exception:
                continue
            rr = dict(r)
            if tag_statement:
                rr["statement_id"] = os.path.basename(p)
            out.append(rr)
    return out


# ── (1) 真实整库数据（此前产生 375 条误报）──
all_tagged = load_bank_rows(tag_statement=True)
all_untagged = load_bank_rows(tag_statement=False)
print(f"[1] 真实整库银行行数={len(all_tagged)}")
print(f"    (1a) 打 statement_id 分组 -> findings={len(run(all_tagged))}   (expect 0)")
print(f"    (1b) 不打标签(退回按对方账号分组) -> findings={len(run(all_untagged))}   (对照：旧口径)")

# ── (2) 单份对账单(1_7.json, 41行连续余额) → 0 ──
stmt = json.load(open(os.path.join(TR, "1_7.json"), encoding="utf-8"))["rows"]
stmt = [dict(r) for r in stmt]
for r in stmt:
    r["statement_id"] = "1_7.json"
print(f"[2] 1_7.json 41行(连续余额,单对账单) -> findings={len(run(stmt))}   (expect 0)")

# ── (2b) 同一份对账单、对方账号各不相同(真实形态)，仅靠 statement_id 归组 → 0 ──
print(f"[2b] 同账单+多变对方账号, 仅 statement_id 归组 -> findings={len(run(stmt))}   (expect 0)")

# ── (3) 每行带本户账号(holder_account)且余额正确 → 0 ──
good = copy.deepcopy(stmt)
for r in good:
    r["holder_account"] = "7559000123456789"
print(f"[3] 每行带 holder_account 且余额正确 -> findings={len(run(good))}   (expect 0)")

# ── (4) [3] 注入 1 处真实余额错录(row20 +999) → 必须检出 1 ──
bad = copy.deepcopy(good)
bad[20]["balance"] = str(float(str(bad[20]["balance"]).replace(",", "")) + 999.0)
r4 = run(bad)
print(f"[4] 注入 1 处真实余额错录 -> findings={len(r4)}   (expect 1)")

# ── (5) 同一份对账单重复导入 3 份（同 statement_id）→ 0 ──
print(f"[5] 同账单重复 3 份 -> findings={len(run(good * 3))}   (expect 0)")

# ── (6) 重复 3 份且含错录 → 仍检出 1 ──
print(f"[6] 重复 3 份且含错录 -> findings={len(run(bad * 3))}   (expect 1)")
