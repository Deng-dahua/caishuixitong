# -*- coding: utf-8 -*-
"""疑点3 · D13 收口（第二次尝试，保守版）：§三 的缺料来源改为**唯一权威**。

上一版失败原因：把 `_lack_names` 的**定义删了**、下一行仍在引用它 ⇒ NameError
⇒ 报告构建崩溃（产物里 `enterprise_readable_report` 键消失）、12 个测试失败。

本版纪律：
  ① **只替换一行**（`_lack_ok` 的取值来源），**不删任何定义** ⇒ 不会断引用；
  ② 新增独立变量 `_lack_auth`，不覆盖 `_lack_names`；
  ③ 权威字段缺失时**回落**到原计算（不丢信息、不臆断"天然不适用"）；
  ④ 改完必须验证产物键完整 + pytest 全绿（这次就是靠 `enterprise_readable_report`
     键消失才发现崩溃的）。
"""
import io
import os
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
P = os.path.join(ROOT, "engine", "enterprise_report.py")

OLD = "        _lack_ok = _filter_not_required(list(_lack_names), not_required_docs)"
NEW = (
    "        # ★ 2026-10-04（疑点3 D13 收口）：缺料来源改为**唯一权威**。" + NL +
    "        #   `evidence_chain` 已完成「业态剔除 + 未归类材料登记」，直接读它 ⇒" + NL +
    "        #   字段 / §三 / §四 三处构造上一致，不会再漂移。" + NL +
    "        #   ⚠ 保留 `_lack_names`（下一行仍引用它）；权威字段缺失时**回落**到原计算。" + NL +
    "        _lack_auth = [str(_z9) for _z9 in (ev.get(\"missing_material_names\") or [])" + NL +
    "                      if str(_z9).strip()]" + NL +
    "        if _lack_auth:" + NL +
    "            _lack_ok = _filter_not_required(list(_lack_auth), not_required_docs)" + NL +
    "        else:" + NL +
    "            _lack_ok = _filter_not_required(list(_lack_names), not_required_docs)"
)

raw = io.open(P, "r", encoding="utf-8", newline="").read()
crlf = CRLF in raw
t = raw.replace(CRLF, NL)
if t.count(OLD) != 1:
    print("!! 命中 %d 次" % t.count(OLD))
    sys.exit(2)
t = t.replace(OLD, NEW, 1)

# 自检：改动块内变量名齐全（_lack_names / _lack_ok / _lack_auth 各有定义与使用）
seg_start = t.index("        _lack_names = []")
seg_end = t.index("        _verdict3 = ", seg_start)
seg = t[seg_start:seg_end]
for v in ("_lack_names", "_lack_ok", "_lack_auth"):
    if seg.count(v + " = ") < 1 or seg.count(v) < 2:
        print("!! 变量 %s 在块内定义/使用不完整（定义%d 使用%d）" % (v, seg.count(v + " = "), seg.count(v)))
        sys.exit(3)
io.open(P, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
print("OK §三 缺料来源已改为唯一权威（并通过块内变量自检）")
