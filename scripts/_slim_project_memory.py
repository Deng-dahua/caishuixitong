# -*- coding: utf-8 -*-
"""整理项目 MEMORY.md（超注入上限被截断）—— **归档不删除**，可逆。

做法：
  1. 前 `KEEP` 行（标题/优先级/架构红线/五条静默/单一权威/关键铁律）**原文保留**；
  2. 其余全部**原文归档**到 `_archive/MEMORY_detail_2026Q4.md`（逐字不丢）；
  3. MEMORY.md 末尾改为**索引段**（列归档章节标题 + 关键词），并追加本轮（2026-10-08）要点。
"""
from __future__ import annotations

import io
import os

BASE = r"C:\Users\Administrator\WorkBuddy\2026-08-04-21-37-33\.workbuddy\memory"
SRC = os.path.join(BASE, "MEMORY.md")
ARC_DIR = os.path.join(BASE, "_archive")
ARC = os.path.join(ARC_DIR, "MEMORY_detail_2026Q4.md")
KEEP = 83  # 第 84 行起为「## 闸门与环境」

NEW_SECTION = """
## 2026-10-08 条款治理（要点；细节与证据见 `memory/2026-10-08.md`）
- **逐项结论字段（`verdict`/`suggestion`/`confidence_formula`）绝不可参与去重** ——
  替换为跨项引用会产生**错误语义**（实测 14/16 项 verdict 被污染：R3 结论变成「见疑点R2」、R7 自引用）。
  去重只动"纯展示叙述段落"。
- **去重口径唯一权威** `dedup_pipeline.duplicate_rate`（三项：整体≤10% / 同章节≤5% / 同一事实≤1 次）；
  `scripts/_phase1_diagnose.py` 薄转发，**不得**再自行实现判定。
- **报告级通用口径字段必须上提**（`risk_level_basis` / `confidence_formula`）：唯一实现
  `report_pipeline.merge_report_level_notes` + `enterprise_report._report_level_notes_statement`（**共用常量表**
  `REPORT_LEVEL_TEXT_KEYS`）。实测不上提 ⇒ 整体重复率 16.89%、同章节超阈 10（虚假达标）；
  上提后达标且逐项位置引用「见报告性质和使用说明」。
- **结论用语唯一权威** `config/conclusion_grades.json::term_authority`
  ＝「风险信号 / 待核事项 / 已认定事实 / 违法认定」（L1~L4 映射 + 越权定性词表）。
- **闸门** `tools/audit_consistency.check_clause_compliance()`（C1 三项去重 / C2 去重字段安全 /
  C3 编号不偏移 / C4 术语权威 / C5 知识闭环传 `case=` / C6 效力声明）。
  **反向验证必须子进程逐轮**（`scripts/_rev_verify_clause_gates.py`，同进程有 `sys.modules` 缓存 ⇒ 假红/假绿）；
  判据**先剥注释**（`_strip_comments_keep_lines`），且优先**运行时断言权威函数**而非整文件 grep。
- **只读核验脚本** 必须 `sys.path.insert(0, ROOT)` —— 否则 `import engine` 静默失败、取数全空。

---

## 详细条目索引（**已归档**，原文见 `_archive/MEMORY_detail_2026Q4.md`）
- `## 闸门与环境` —— 跨日通用坑：交付物命名权威 / D1~D5 文档一致性 / 反向验证陷阱（变异无效·空断言·import 缓存 /
  数据表读坏假绿 / 判据先量化再收窄）/ 三种"一模一样" / 报告 3 条渲染链路 / 脱敏分链路 / 中文姓名与数字边界
  / 服务常驻只能用户双击 `start8001.bat` / 跨 bash-Python 必用绝对路径 / 覆盖产物须 `atomic_write_json`
  / 跑批企业清单必须来自 DB。
- `## 2026-10-06 新增`、`（第三/四/五/六轮追加）` —— 当日新增权威与复发模式。
- `## 第一章（检查情况总述与总体结论）—— 唯一改造点与配套闸门`（2026-10-08）。
- `## 报告级"单一权威"与对齐三形态`（2026-10-08）。

> **归档原因**：本文件超出注入上限被截断（原 380 行 / 53KB）。骨架留本文件；
> 细节一律在 `_archive/`、`~/.workbuddy/skills/caishuixitong-*` 与 `memory/YYYY-MM-DD.md`。
"""


def main() -> int:
    txt = io.open(SRC, encoding="utf-8").read()
    lines = txt.split("\n")
    if "_archive/MEMORY_detail_2026Q4.md" in txt:
        print("已整理过，跳过")
        return 0
    head, tail = lines[:KEEP], lines[KEEP:]
    os.makedirs(ARC_DIR, exist_ok=True)
    io.open(ARC, "w", encoding="utf-8", newline="\n").write(
        "# MEMORY.md 详细条目归档（2026-10-08 清理；**原文逐字未删**）\n"
        "# 来源：整理前的 MEMORY.md 第 %d 行起\n\n" % (KEEP + 1) + "\n".join(tail))
    io.open(SRC, "w", encoding="utf-8", newline="\n").write(
        "\n".join(head).rstrip("\n") + "\n" + NEW_SECTION)
    print("整理完成：保留 %d 行，归档 %d 行 → %s" % (len(head), len(tail), ARC))
    print("MEMORY.md 现有 %d 行 / %d 字节"
          % (len(io.open(SRC, encoding="utf-8").read().split("\n")),
             os.path.getsize(SRC)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
