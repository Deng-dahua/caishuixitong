# -*- coding: utf-8 -*-
"""「一键分析」接线完整性审计（只读）。

要回答的问题：`engine/*.py` 与 `config/*.json` 里，**哪些没有被一键分析链引用**。

方法（比正则可靠，本项目此前正则核验踩过两个坑）：
  ① 用 **ast** 收集每个 .py 的 import（含函数体内 import 与 importlib 动态导入）；
  ② 从入口（main / engine.pipeline / engine.enterprise_report / engine.report_pipeline）
     沿 import 图做**传递闭包**；
  ③ 未被闭包覆盖的 engine 模块 = 未接线（再人工确认是否真的该接）；
  ④ config/*.json 用"文件名是否出现在闭包内任何源文件里"判定。
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Dict, Set

ROOT = Path(__file__).resolve().parents[1]
ENTRIES = ["main", "engine.pipeline", "engine.enterprise_report",
           "engine.report_pipeline", "engine.dedup_pipeline",
           "engine.selfcheck", "engine.quality_gates"]


def module_path(mod: str) -> Path | None:
    rel = mod.replace(".", "/")
    for cand in (ROOT / (rel + ".py"), ROOT / rel / "__init__.py"):
        if cand.exists():
            return cand
    return None


def imports_of(py: Path) -> Set[str]:
    """收集一个 .py 里的全部导入模块名（含函数内、含 importlib 字符串）。"""
    try:
        tree = ast.parse(py.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return set()
    out: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                out.add(node.module)
                for a in node.names:
                    out.add(node.module + "." + a.name)
        elif isinstance(node, ast.Call):
            f = node.func
            fname = getattr(f, "attr", None) or getattr(f, "id", None)
            if fname in ("import_module", "__import__") and node.args:
                a0 = node.args[0]
                if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                    out.add(a0.value)
    return out


def main() -> None:
    cache: Dict[str, Set[str]] = {}

    def deps(mod: str) -> Set[str]:
        if mod in cache:
            return cache[mod]
        cache[mod] = set()
        p = module_path(mod)
        if not p:
            return set()
        d = imports_of(p)
        cache[mod] = d
        return d

    # ── 传递闭包 ──
    seen: Set[str] = set()
    stack = list(ENTRIES)
    while stack:
        m = stack.pop()
        if m in seen:
            continue
        seen.add(m)
        for d in deps(m):
            if d.startswith("engine") or d.startswith("config"):
                if d not in seen:
                    stack.append(d)
            elif module_path(d):
                if d not in seen:
                    stack.append(d)

    reachable_engine = {m for m in seen if m.startswith("engine")}
    all_engine = {
        "engine." + p.stem
        for p in (ROOT / "engine").glob("*.py")
        if not p.stem.startswith("__")
    }
    missing = sorted(all_engine - reachable_engine)

    print("=" * 78)
    print("engine 模块 %d 个；一键分析可达 %d 个；**未接线 %d 个**"
          % (len(all_engine), len(reachable_engine), len(missing)))
    print("=" * 78)
    for m in missing:
        p = module_path(m)
        try:
            head = p.read_text(encoding="utf-8", errors="ignore").split("\n")[0][:60]
        except Exception:
            head = ""
        print("  ✗ %-38s %s" % (m, head))

    # ── config 表 ──
    cfgs = sorted((ROOT / "config").glob("*.json"))
    src_files = []
    for m in sorted(seen):
        p = module_path(m)
        if p:
            src_files.append(p)
    blob = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in src_files)
    print("\n" + "=" * 78)
    print("config/*.json 共 %d 个；被一键分析可达源文件**引用**的如下" % len(cfgs))
    print("=" * 78)
    orphan = []
    for c in cfgs:
        if c.name in blob:
            print("  ✓ %s" % c.name)
        else:
            orphan.append(c.name)
            print("  ✗ %s" % c.name)
    print("\n未引用 %d 个：%s" % (len(orphan), "、".join(orphan)))


if __name__ == "__main__":
    main()
