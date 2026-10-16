# -*- coding: utf-8 -*-
"""按闸门权威表**同步文档里的行号数字**（`config/doc_consistency.json` 的 `grep_line` 项）。

## 为什么需要它
`check_doc_number_authority` 跟踪「某函数定义在第 N 行」这类数字：文档手抄的数字
一旦与现算不符就报 ERROR。而**每次在 `tools/audit_consistency.py` 里新增/删改函数**，
其后所有行号都会整体平移 ⇒ 文档立刻失准。

处置有两条路：
  ① 改代码去迁就行号（上一轮用过：压缩注释保持行数）—— 只在"改动是纯注释"时可行；
  ② **同步文档数字**（本脚本）—— 新增真函数时只能走这条。

★ 纪律：**只改数字，不动文档其它任何文字**（逐处就地替换捕获组，保留原文与格式）。

用法：
    ./.venv/Scripts/python.exe scripts/_sync_doc_line_numbers.py            # 干跑，只报告差异
    ./.venv/Scripts/python.exe scripts/_sync_doc_line_numbers.py --apply    # 就地更新
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config" / "doc_consistency.json"
DOCS = ROOT / "docs"


def _grep_line(path: str, pattern: str) -> int:
    """权威值：**用 grep 现算**（与闸门同一口径，不靠本脚本另算）。"""
    r = subprocess.run(["grep", "-n", "-E", pattern, str(ROOT / path)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    for line in (r.stdout or "").splitlines():
        if ":" in line:
            try:
                return int(line.split(":", 1)[0])
            except ValueError:
                continue
    return 0


def _items() -> List[Dict[str, Any]]:
    d = json.loads(CFG.read_text(encoding="utf-8"))
    out: List[Dict[str, Any]] = []

    def walk(o: Any) -> None:
        if isinstance(o, dict):
            a = o.get("authority") or {}
            if isinstance(a, dict) and a.get("kind") == "grep_line":
                out.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for y in o:
                walk(y)

    walk(d)
    return out


def _find_doc(name: str) -> Path | None:
    for p in DOCS.rglob(name):
        return p
    return None


def main() -> int:
    apply = "--apply" in sys.argv
    total = changed = 0
    for item in _items():
        a = item["authority"]
        val = _grep_line(str(a["path"]), str(a["pattern"]))
        if not val:
            print("!! 取不到权威值：%s（pattern=%r）⇒ 跳过" % (item.get("id"), a.get("pattern")))
            continue
        for claim in (item.get("claims") or []):
            fp = _find_doc(str(claim.get("file") or ""))
            if fp is None:
                print("!! 找不到文档：%s" % claim.get("file"))
                continue
            text = fp.read_text(encoding="utf-8")
            rx = re.compile(str(claim.get("regex")))
            m = rx.search(text)
            total += 1
            if not m:
                print("   [未命中] %s ← %s" % (item.get("id"), fp.name))
                continue
            old = m.group(1)
            if str(old) == str(val):
                continue
            new_text = text[:m.start(1)] + str(val) + text[m.end(1):]
            print("   [更新] %s ← %s：%s → %s" % (item.get("id"), fp.name, old, val))
            changed += 1
            if apply:
                fp.write_text(new_text, encoding="utf-8")
    print("\n跟踪项 %d 处｜需更新 %d 处%s" % (total, changed, "" if apply else "（干跑，未写盘）"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
