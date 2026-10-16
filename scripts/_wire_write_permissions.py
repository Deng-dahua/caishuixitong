# -*- coding: utf-8 -*-
"""为写类端点补功能权限点校验（META-STAGE1-2-CONSOLIDATE · MQ2-D1）。

★ 原则（不重构权限框架）：
  · 权威仍是 `engine.rbac.rebac_allows()`（既有唯一实现），本脚本不改它；
  · 采用项目**既有**的 API 层模式（与 `rule_versions_api._perm` / `templates_api._request_perm`
    完全同构）—— 每个文件加一个 `_require_perm(session, code)` 薄辅助，
    在各**写端点**函数体首行 `session = _session(request)` 之后插一行校验；
  · **只读端点不动**（一个字符都不改）；
  · 幂等：重复运行不重复插入。

用法：python scripts/_wire_write_permissions.py [--check]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

HELPER = '''

def _require_perm(session, code: str):
    """写操作的**功能权限点**校验（MQ2-D1）。

    权威：`engine.rbac.rebac_allows()`（经 `require_permission` 抛 403）。
    本函数只做「RbacError → HTTPException」的边界转换，**不自判角色**（否则即第二套口径）。
    """
    from engine.rbac import RbacError, require_permission          # noqa: PLC0415
    try:
        require_permission(session, code)
    except RbacError as exc:
        raise HTTPException(status_code=int(getattr(exc, "status", 403)),
                            detail=str(getattr(exc, "message", exc))) from exc
    return session
'''

# (文件名, [(HTTP 方法, 路由路径, 权限点), ...])
PLAN = {
    "reports_api.py": [
        ("post", "/projects/{project_id}/reports", "report.generate"),
    ],
    "risks_api.py": [
        ("post", "/risks/bulk-review", "risk.review"),
        ("post", "/risks/{risk_id}/review", "risk.review"),
        ("post", "/risks/{risk_id}/comment", "risk.review"),
    ],
    "analysis_api.py": [
        ("post", "/projects/{project_id}/analysis-jobs", "analysis.run"),
        ("post", "/analysis-jobs/{job_id}/cancel", "analysis.run"),
        ("post", "/analysis-jobs/{job_id}/retry", "analysis.run"),
        ("delete", "/analysis-jobs/{job_id}", "analysis.run"),
    ],
    "documents_api.py": [
        ("post", "/documents/chunk/init", "document.write"),
        ("put", "/documents/chunk/{upload_id}/{chunk_index}", "document.write"),
        ("post", "/documents/chunk/{upload_id}/complete", "document.write"),
        ("post", "/projects/{project_id}/documents", "document.write"),
        ("delete", "/documents/{document_id}", "document.write"),
        ("post", "/documents/{document_id}/classify", "document.write"),
        ("put", "/documents/{document_id}/parse-status", "document.write"),
    ],
    "projects_api.py": [
        ("post", "", "project.write"),
        ("put", "/{project_id}", "project.write"),
        ("delete", "/{project_id}", "project.write"),
        ("post", "/{project_id}/members", "project.write"),
    ],
    "extract_api.py": [
        ("post", "/documents/{document_id}/extract", "document.write"),
        ("put", "/extracted/{field_id}", "document.write"),
        ("post", "/extract/issues/{issue_id}/resolve", "document.write"),
    ],
}


def _esc(s: str) -> str:
    return re.escape(s)


def patch(name: str, rules: list, *, check: bool) -> tuple:
    p = ROOT / name
    src = p.read_text(encoding="utf-8")
    orig = src
    added, skipped = 0, []

    # ① 加辅助函数（放在 `def _session(request: Request):` 之后、其函数体结束处）
    if "def _require_perm(" not in src:
        m = re.search(r"\ndef _session\(request: Request\):.*?\n(?=\n\n)", src, re.S)
        if not m:
            return added, [f"{name}: 找不到 _session 锚点"], src
        src = src[: m.end()] + HELPER + src[m.end():]

    # ② 各写端点：在**本端点区间内**首个 `session = _session(request)` 之后插入校验。
    #    ★ 不能用"def 行 + 紧邻赋值"的窄正则：签名可能跨行、函数体可能先有 docstring。
    #      做法：定位装饰器 → 取到下一个 `@router.` 之前的区间 → 区间内首个 session 赋值。
    for meth, path, perm in rules:
        dec = re.compile(r'@router\.%s\(\s*"%s"' % (meth, _esc(path)))
        m = dec.search(src)
        if not m:
            skipped.append(f"{name}: 未匹配装饰器 {meth.upper()} {path or '(root)'}")
            continue
        nxt_dec = src.find("@router.", m.end())
        seg_end = nxt_dec if nxt_dec != -1 else len(src)
        seg = src[m.start():seg_end]
        am = re.search(r"\n[ \t]+session = _session\(request\)\n", seg)
        if not am:
            skipped.append(f"{name}: {meth.upper()} {path or '(root)'} 区间内未找到 session 赋值")
            continue
        end = m.start() + am.end()
        guard = '    _require_perm(session, "%s")\n' % perm
        if src[end: end + len(guard)] == guard:
            skipped.append(f"{name}: {meth.upper()} {path or '(root)'} 已有校验（幂等跳过）")
            continue
        src = src[:end] + guard + src[end:]
        added += 1

    if not check and src != orig:
        p.write_text(src, encoding="utf-8")
    return added, skipped, src


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只报告不写盘")
    args = ap.parse_args()

    total = 0
    problems = []
    for name, rules in PLAN.items():
        added, skipped, _ = patch(name, rules, check=args.check)
        total += added
        need = len(rules)
        print(f"[{'check' if args.check else 'patch'}] {name:22s} 应插 {need:2d} · 实插 {added:2d}")
        for s in skipped:
            if "已有校验（幂等跳过）" in s:
                print("        ✓ 幂等跳过：" + s.split(": ", 1)[-1].replace("已有校验（幂等跳过）", "").strip())
            else:
                problems.append(s)
                print("        ⚠ " + s)
    print(f"\n合计新增校验 {total} 处；异常 {len(problems)} 项")
    if problems:
        for x in problems:
            print("  ⚠ " + x)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
