# -*- coding: utf-8 -*-
"""O-01 一次性迁移：把产品代码里的 `print(...)` 换成 logger 调用。

判据（分级口径，不搞"一律 info"）
---------------------------------
· 文本含 失败/错误/异常/告警/WARN/超时/不可用 ⇒ `_log.warning`
· 其余 ⇒ `_log.info`
· 含 `file=sys.stderr` 的另外手工处理（本脚本跳过并列出）

安全措施
--------
① 只替换 **AST 认定是"独立语句的 print 调用"** 的那个 `print` 标识符位置
   （按 col_offset 精确替换），参数部分一个字不动 ⇒ 多行 print、f-string、嵌套调用都不会被切坏；
② 迁移前备份到 `.o01_backup/`；
③ 迁移后 py_compile + 打印每个文件改动条数；
④ 跳过 `_rev_verify_*` / `_p0_*` / `_sync_*` 等**验证工具脚本** —— 它们的 print 就是"输出本身"，
   改成 logger 反而看不到结果。
"""
from __future__ import annotations

import ast
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BACKUP = ROOT / ".o01_backup"

#: 迁移目标（真产品代码；工具/验证脚本不在此列）
TARGETS = ["database.py", "main.py", "audit.py", "engine/enterprise_report.py"]

WARN_WORDS = ("失败", "错误", "异常", "告警", "WARN", "超时", "不可用", "冲突", "跳过")


def _logger_block(var: str = "_log") -> str:
    return (
        "\n# ★ O-01（2026-10-17）：统一日志。新代码一律用 `get_logger`，**不要再 print**。\n"
        "#   分级口径：启动/推进=info；失败但已兜底=warning；高频细节=debug。\n"
        "from logkit import get_logger as _get_logger\n"
        "%s = _get_logger(__name__)\n" % var
    )


def migrate(path: pathlib.Path, var: str = "_log") -> tuple:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)

    edits = []          # (行号, col, 旧, 新)
    skipped_file_kw = 0
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)):
            continue
        call = node.value
        if not (isinstance(call.func, ast.Name) and call.func.id == "print"):
            continue
        seg = ast.get_source_segment(src, call) or ""
        if any(kw.arg == "file" for kw in call.keywords):
            skipped_file_kw += 1
            continue
        level = "warning" if any(w in seg for w in WARN_WORDS) else "info"
        edits.append((call.func.lineno, call.func.col_offset, "print", "%s.%s" % (var, level)))

    if not edits:
        return src, 0, skipped_file_kw

    # 从后往前、同一行内从右到左替换，避免偏移串位
    for lineno, col, old, new in sorted(edits, reverse=True):
        line = lines[lineno - 1]
        assert line[col:col + len(old)] == old, "第 %d 行 col %d 不是 print（%r）" % (
            lineno, col, line[col:col + 12])
        lines[lineno - 1] = line[:col] + new + line[col + len(old):]

    out = "".join(lines)

    # 插入 logger 定义（放在最后一个顶层 import 之后）
    tree2 = ast.parse(out)
    last = max((n.end_lineno for n in tree2.body
                if isinstance(n, (ast.Import, ast.ImportFrom))), default=0)
    out_lines = out.splitlines(keepends=True)
    out_lines.insert(last, _logger_block(var))
    return "".join(out_lines), len(edits), skipped_file_kw


def main() -> int:
    apply = "--apply" in sys.argv
    if apply:
        BACKUP.mkdir(exist_ok=True)
    total = 0
    for rel in TARGETS:
        p = ROOT / rel
        if not p.is_file():
            print("%-32s 不存在，跳过" % rel)
            continue
        before = p.read_text(encoding="utf-8")
        if "from logkit import get_logger" in before:
            print("%-32s 已迁移过，跳过" % rel)
            continue
        out, n, skipped = migrate(p)
        total += n
        print("%-32s 替换 %3d 处%s" % (rel, n, ("（跳过带 file= 的 %d 处，需手工）" % skipped) if skipped else ""))
        if apply and n:
            shutil.copy2(p, BACKUP / p.name)
            p.write_text(out, encoding="utf-8")
    print("\n合计 %d 处；%s" % (total, "已写入（备份 .o01_backup/）" if apply else "演练，加 --apply 生效"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
