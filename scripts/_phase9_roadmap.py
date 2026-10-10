# -*- coding: utf-8 -*-
"""阶段9：系统固化（14 个模块）+ 迭代路线图。"""
from __future__ import annotations
import json, os
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs", "第12批_报告修订闭环")
NOW = datetime.now().strftime("%Y-%m-%d %H:%M")
RM = json.load(open(os.path.join(ROOT, "config", "module_roadmap.json"), encoding="utf-8"))


def exists(p: str) -> bool:
    """权威落点存在性：支持多路径（"A ＋ B" / "A + B"）与 `file::fn` 写法。

    ★ 2026-10-08 修复：原实现只解析**单一路径**，遇到「A ＋ B」型 authority
    （如 dedup_pipeline 同时指向 dedup_pipeline.py 与 report_dedup.py）会解析失败，
    被误计为"未落地"（实测报 15/18，实际 18/18 文件都存在）。
    """
    import re as _re
    txt = str(p or "")
    cands = [x.strip() for x in _re.split(r"[＋+]", txt) if x.strip()]
    for one in cands:
        # 先截掉尾部的中文/英文括号注释（如 "engine/fact_store.py（已接入 main.py）"），
        # 再取第一段并去掉 file::fn 的成员后缀
        rel = one.split("（")[0].split("(")[0].split(" ")[0].strip().split("::")[0].strip()
        if not rel:
            continue
        for c in (os.path.join(ROOT, rel), os.path.join(ROOT, rel + ".py"),
                  os.path.join(ROOT, rel.replace(".", os.sep) + ".py")):
            if os.path.exists(c):
                return True
    return False


def main() -> int:
    os.makedirs(DOCS, exist_ok=True)
    rows, det = [], []
    landed = 0
    for m in RM["modules"]:
        ok = exists(m["authority"])
        landed += ok
        rows.append(f"| {m['no']} | {m['name']} | `{m['authority']}` | {m['priority']} | "
                    f"{'✓' if ok else '✗'} | {m['status']} |")
        det.append(f"""
### {m['no']}. {m['name']}

| 项 | 内容 |
|---|---|
| **功能** | {m['func']} |
| **输入** | {m['input']} |
| **输出** | {m['output']} |
| **规则** | {m['rules']} |
| **校验** | {m['check']} |
| **优先级** | {m['priority']} |
| **依赖** | {'、'.join(m['depends']) or '无'} |
| **验收** | {m['accept']} |
| **状态** | {m['status']} |
""")
    road = "\n".join(
        f"**{p['phase']}**\n\n" + "\n".join(f"- {i}" for i in p["items"]) + "\n"
        for p in RM["roadmap"])
    unfinished = [m for m in RM["modules"] if "未完成" in m["status"] or "未接入" in m["status"] or "未固化" in m["status"]]
    md = f"""# 阶段9：《系统固化与迭代路线图》

**样本**：WB-TRISK-SAMPLE-001
**生成时间**：{NOW}
**路线图唯一权威**：`config/module_roadmap.json`（新增模块只加一条）
**执行**：`scripts/_phase9_roadmap.py`

---

## 一、14 个模块总览（权威落点存在性校验：{landed}/{len(RM['modules'])}）

| # | 模块 | 唯一权威 | 优先级 | 权威落地 | 状态 |
|---|---|---|---|---|---|
{chr(10).join(rows)}

## 二、模块逐条（8 项齐备：功能/输入/输出/规则/校验/优先级/依赖/验收）
{''.join(det)}

## 三、迭代路线图

{road}

## 四、诚实登记：**未完成项**（{len(unfinished)} 项）

| 模块 | 状态 | 影响 |
|---|---|---|
{chr(10).join(f"| {m['name']} | {m['status']} | 见该模块验收项 |" for m in unfinished)}

> 按指令「不得把未完成说成已完成」：上表 4 项**未接入产出链或未固化为引擎模块**，
> 其中 `fact_store` 未接入导致门禁 B1 仍为 SKIP、`closure` 未进 DIGEST_FIELDS 导致 A8 WARN。

## 五、复跑命令

```
./.venv/Scripts/python.exe scripts/_phase9_roadmap.py
```
"""
    b = md.encode("utf-8")
    with open(os.path.join(DOCS, "10_阶段9_系统固化与迭代路线图.md"), "wb") as f:
        f.write(b)
    print(f"[OK] 模块 {len(RM['modules'])} 个，权威落地 {landed}；未完成 {len(unfinished)} 项")
    print(f"[OK] 10_阶段9_系统固化与迭代路线图.md  {len(b):,} 字节")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
