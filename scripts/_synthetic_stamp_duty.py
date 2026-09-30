# -*- coding: utf-8 -*-
"""合成验证：印花税「税目反推」正确性（不依赖合同原件）。

验证三件事（每个税目都要过）：
  ① 有应税凭据线索、未见印花税缴款 → 触发，且带 redline_id + constituent_hits；
  ② 已识别缴款 ≥ 全部税目推算应缴合计 → 抑制（出罪情形）；
  ③ 无线索 → 不触发（只有「检查通过」）。
另验证：缴款不足推算应缴时 → 仍触发，且 detail 如实写明"已识别缴款 X 元"（缺失≠0）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.domain_analysis import _domain_stamp_duty_check


def fire(**data):
    return _domain_stamp_duty_check(**data)


def ids(findings):
    return [f.get("redline_id") for f in findings if f.get("redline_id")]


cases = []

# ① 逐税目触发
cases.append(("买卖合同：销项 100 万 → 触发 RL-OTH-001",
              "RL-OTH-001" in ids(fire(sal_invs=[{"amount": 1000000}]))))
cases.append(("营业账簿：实收资本 50 万 → 触发 RL-OTH-007",
              "RL-OTH-007" in ids(fire(balances=[{"code": "4001", "close_credit": 500000, "close_debit": 0}]))))
cases.append(("产权转移书据：股权转让款 80 万 → 触发 RL-OTH-008",
              "RL-OTH-008" in ids(fire(vouchers=[{"summary": "股权转让款", "debit_amount": 800000}]))))
cases.append(("借款合同：银行借款 90 万 → 触发 RL-OTH-009",
              "RL-OTH-009" in ids(fire(bank_txs=[{"summary": "银行借款放款", "amount": 900000}]))))
cases.append(("租赁合同：房租 12 万 → 触发 RL-OTH-010",
              "RL-OTH-010" in ids(fire(vouchers=[{"summary": "支付房租租赁费", "debit_amount": 120000}]))))
cases.append(("保险合同：财产保险费 5 万 → 触发 RL-OTH-011",
              "RL-OTH-011" in ids(fire(vouchers=[{"summary": "财产保险费", "debit_amount": 50000}]))))

# ② 已足额 → 出罪抑制（买卖推算应缴 300，缴款 400）
cases.append(("已识别缴款 ≥ 推算应缴 → 抑制（不置疑）",
              ids(fire(sal_invs=[{"amount": 1000000}],
                       bank_txs=[{"summary": "缴纳印花税", "amount": 400}])) == []))

# ③ 无线索 → 不产出任何 redline 发现
cases.append(("无任何线索 → 不触发", ids(fire()) == []))

# ④ 缴款不足 → 仍触发，且如实写明已识别缴款（缺失≠0、不可断言未缴纳）
_partial = fire(sal_invs=[{"amount": 1000000}],
                bank_txs=[{"summary": "缴纳印花税", "amount": 100}])
cases.append(("缴款不足推算应缴 → 仍触发", "RL-OTH-001" in ids(_partial)))
cases.append(("缴款不足 → detail 如实写明已识别缴款金额",
              bool(_partial) and "识别到印花税字样缴款 100.00 元" in str(_partial[0].get("detail"))))

# ⑤ 要件认领纪律：每条发现必须带 constituent_hits 且 index 在范围内
_all = fire(sal_invs=[{"amount": 1000000}],
            balances=[{"code": "4001", "close_credit": 500000}],
            bank_txs=[{"summary": "银行借款", "amount": 900000}])
cases.append(("每条发现都带 constituent_hits（只认领算过的要件）",
              all(f.get("constituent_hits") for f in _all) and len(_all) >= 3))
cases.append(("constituent_hits 要件序号合法（1..5）",
              all(1 <= h["index"] <= 5 for f in _all for h in f.get("constituent_hits", []))))

# ⑥ 无申报表时不得断言"实际缴纳0元"
cases.append(("缺失≠0：不得出现『实际缴纳0元/未缴纳』断言",
              not any(("实际缴纳0元" in str(f.get("detail"))) or ("未缴纳印花税" in str(f.get("detail")))
                      for f in _all)))

ok = 0
for name, passed in cases:
    print(("PASS " if passed else "FAIL "), name)
    ok += 1 if passed else 0
print("\n%d/%d stamp-duty synthetic cases passed" % (ok, len(cases)))
sys.exit(0 if ok == len(cases) else 1)
