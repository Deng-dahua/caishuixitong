# -*- coding: utf-8 -*-
"""更新 `config/doc_consistency.json` 里**会随规模变化的数字锚词**（2026-10-15）。

背景：批次规则入库后规模变化（风险指标 94→130、红线 91→127、认定要件 456→600、
前提条 70→142），而文档一致性闸门用**含具体数字的正则**定位"声明位置" ⇒ 数字变了
锚就失效（报"找不到声明位置"）。本脚本把锚词同步到新规模。

★ 这不是放松判据：正则仍从同一位置取值、仍与权威值比对，只是锚词跟着规模走。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P = ROOT / "config" / "doc_consistency.json"

# (旧串, 新串) —— 用**文件里的原始转义形态**（JSON 文本中 `\s` 写作 `\\s`）
REPS = [
    (r"\s*/\s*94 条风险指标", r"\s*/\s*130 条风险指标"),
    (r"（(\d+)\s*条\s*=\s*91\s*红线", r"（(\d+)\s*条\s*=\s*127\s*红线（原 91"),
    (r"条风险指标（91 红线派生", r"条风险指标（127 红线派生"),
]


def main() -> int:
    s = P.read_text(encoding="utf-8")
    total = 0
    for a, b in REPS:
        if a in s:
            n = s.count(a)
            s = s.replace(a, b)
            total += n
            print("  更新 %-40s → %s（%d 处）" % (a[:40], b[:40], n))
        else:
            print("  [SKIP] 未命中（可能已更新）：%s" % a[:44])
    P.write_text(s, encoding="utf-8")
    json.loads(P.read_text(encoding="utf-8"))            # 语法自检
    print("锚词更新合计 %d 处；JSON 语法 OK" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
