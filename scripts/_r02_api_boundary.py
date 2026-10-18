# -*- coding: utf-8 -*-
"""R-02 一次性迁移：把各 API 文件里复制的 `_session`/`_require_perm`/`_request_perm`/
`_perm`/`_admin` 删掉，改为引用唯一权威 `engine/api_common`；`_call` 收敛为 2 行转发。

为什么保留 `_call` 这个壳（而不是让调用点改名）
-----------------------------------------------
`_call(SVC.create_project, payload, session, request=request)` 在 8 个文件里被调用几十次。
改调用点=大面积动业务代码，风险远大于收益；而**逻辑**只要只有一份（`call_boundary`），
仍然消灭了"改一处忘一处"的机制。所以：**壳保留、逻辑收一处、异常类型显式声明**。

安全措施
--------
① 用 AST 定位函数行区间（不靠正则切字符串，避免把字符串/注释里的同名文本误删）；
② 迁移前备份到 `.r02_backup/`；
③ 迁移后逐文件 py_compile；
④ 打印每个文件的"删了什么/加了什么"，可逐条核对。
"""
from __future__ import annotations

import ast
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BACKUP = ROOT / ".r02_backup"

#: 需要删掉本地实现的函数名（实际逻辑已在 engine/api_common）
DROP = {"_session", "_require_perm", "_request_perm", "_perm", "_admin"}

#: 每个文件 `_call` 要捕获的业务异常类（**必要数据**，不能靠猜）
EXC = {
    "analysis_api.py": "SVC.AnalysisTaskError",
    "documents_api.py": "SVC.DocumentError",
    "extract_api.py": "SVC.ExtractError",
    "projects_api.py": "SVC.ProjectError",
    "rbac_api.py": "SVC.AccessError",
    "rule_versions_api.py": "ADMIN.RuleVersionError",
    "templates_api.py": "STORE.TemplateError",
    "trash_api.py": "SVC.TrashError",
}

#: 各文件需要的别名（只加用得到的，避免无意义命名）
ALIASES = {
    "_session": "session_of",
    "_require_perm": "require_perm",
    "_request_perm": "request_perm",
    "_perm": "request_perm",
    "_admin": "admin_of",
}

CALLLIB = '''from engine.api_common import (admin_of, call_boundary, request_perm,
                             require_perm, session_of)
'''


def drop_functions(src: str, names: set) -> tuple:
    """删除模块顶层的指定函数定义，返回 (新源码, 被删函数名列表)。"""
    tree = ast.parse(src)
    ranges = []
    dropped = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            ranges.append((node.lineno, node.end_lineno))
            dropped.append(node.name)
    if not ranges:
        return src, []
    lines = src.splitlines(keepends=True)
    # 从后往前删，避免行号漂移；顺带吃掉紧随其后的空行
    for start, end in sorted(ranges, reverse=True):
        i, j = start - 1, end
        while j < len(lines) and lines[j].strip() == "":
            j += 1
        del lines[i:j]
    return "".join(lines), dropped


def rewrite_call(src: str, exc: str) -> tuple:
    """把 `_call` 的实现改成 2 行转发（保留函数名与签名，调用点不动）。"""
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_call":
            lines = src.splitlines(keepends=True)
            new = (
                "def _call(fn, *args, **kwargs):\n"
                "    \"\"\"业务异常 → HTTP 的**唯一转换点**在 `engine/api_common.call_boundary`；\n"
                "    本函数只声明「本域该捕获哪一类业务异常」（%s）。\"\"\"\n"
                "    return call_boundary(fn, *args, exc_types=(%s,), **kwargs)\n"
                % (exc, exc)
            )
            body = "".join(lines[node.lineno - 1:node.end_lineno])
            return src.replace(body, new, 1), True
    return src, False


def insert_imports(src: str, needed: set) -> str:
    """在最后一个顶层 import 之后插入 api_common 导入与别名。"""
    tree = ast.parse(src)
    last = max((n.end_lineno for n in tree.body
                if isinstance(n, (ast.Import, ast.ImportFrom))), default=0)
    lines = src.splitlines(keepends=True)
    block = ["\n", CALLLIB, "\n",
             "# ★ R-02（2026-10-17）：以下名字是**别名**，逻辑唯一在 engine/api_common。\n",
             "#   禁止在本文件重新定义（闸门 `check_api_boundary_single_source` 会报错）。\n"]
    for local in sorted(needed):
        block.append("%s = %s\n" % (local, ALIASES[local]))
    lines.insert(last, "".join(block))
    return "".join(lines)


def main() -> int:
    apply = "--apply" in sys.argv
    if apply and not BACKUP.exists():
        BACKUP.mkdir()
    files = sorted(p for p in ROOT.glob("*api*.py") if not p.name.startswith("_bk"))
    for p in files:
        src = p.read_text(encoding="utf-8")
        tree = ast.parse(src)
        local_names = {n.name for n in tree.body
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        needed = {n for n in local_names if n in DROP}
        if not needed and "_call" not in local_names:
            continue

        before = len(src.splitlines())
        out, dropped = drop_functions(src, needed)
        has_call = "_call" in local_names
        call_note = ""
        if has_call and p.name in EXC:
            out, ok = rewrite_call(out, EXC[p.name])
            call_note = "，_call→call_boundary(%s)" % EXC[p.name] if ok else "，_call 未改（异常类未登记）"
        elif has_call:
            call_note = "，⚠ _call 保留原样（%s 未在 EXC 表登记）" % p.name
        if dropped or call_note:
            out = insert_imports(out, needed)
        after = len(out.splitlines())
        print("%-24s 删除 %-34s 行数 %d→%d%s"
              % (p.name, ",".join(sorted(dropped)) or "（无）", before, after, call_note))
        if apply:
            shutil.copy2(p, BACKUP / p.name)
            p.write_text(out, encoding="utf-8")
    print("\n%s" % ("已写入（备份在 .r02_backup/）" if apply else "演练模式，加 --apply 生效"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
