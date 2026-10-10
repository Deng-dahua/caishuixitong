# -*- coding: utf-8 -*-
"""确认疑点5 §三/§四 的三态数字是否一致（D11 收口验收）。"""
import io
import json
import os

ROOT = os.getcwd()
D = json.load(io.open(os.path.join(ROOT, "scripts", "four_reports",
                                  "company_1_full.json"), "r", encoding="utf-8"))
CP = (D.get("enterprise_readable_report") or {}).get("confirmed_problems") or []
p = [x for x in CP if "税前扣除限额" in str(x.get("title") or "")][0]
T = json.dumps(p, ensure_ascii=False)
i = T.find("本项检查需要")
j = T.find("就资料来说")
print("§三 =", T[i:i + 130])
print()
print("§四 =", T[j:j + 120])
