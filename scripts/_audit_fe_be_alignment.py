# -*- coding: utf-8 -*-
"""前端 ↔ 后端 **方法与路径** 对齐审计（只读）。

为什么需要：仅比路径会漏掉一类真缺陷 —— 路径存在但 HTTP 方法不符 ⇒ 405。
  本项目实测口径：`fetch(url, {method:'DELETE'})` 与 `api('POST', url)` 两种写法都要认。

★★ 2026-10-14（R-6）两项改造，均为"假判据"教训的落地：
  ① **先剥 JS 注释再提取**：原实现用 `['"`](/api/...)` 直接在源码上找字面量，
     连**注释里提到的路径**也会算成"前端调用"（实测被自己的注释坑到）；
     与项目既有铁律「存在性断言必须先剥注释」同源。
  ② **分层呈现**：原来只报一个「22 条 404」，会被读成"前端坏了 22 处"。实测逐条核实后：
     其中绝大多数是**字符串常量**（`var API = "/api/v1"`）或**死代码**
     （调用所在的函数全仓从未被调用）。分层后结论才可供决策。

输出分层：
  【A1】真断链（真实调用 + 归属函数确有调用）
  【A2】死代码（真实调用，但归属函数全仓从未被调用 ⇒ 不在生效路径）
  【A3】路径常量（非调用上下文，如 `var API = "/api/..."`）
  【B】 路径存在但方法不匹配（405）
  【C】 后端存在但前端从未调用（僵尸接口，供参考）

用法：python scripts/_audit_fe_be_alignment.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS_DIR = ROOT / "static" / "js"
STATIC_DIR = ROOT / "static"

_LIT = re.compile(r"""['"`](/api/[^'"`\s]*)['"`]""")
_TPL = re.compile(r"\$\{[^}]*\}")
_METHOD_AFTER = re.compile(r"method\s*:\s*['\"](\w+)['\"]")
_METHOD_BEFORE = re.compile(r"['\"](GET|POST|PUT|DELETE|PATCH)['\"]\s*,\s*$", re.I)
_ROUTE = re.compile(
    r"""@(?:app|router|bp|api)\.(get|post|put|delete|patch|api_route)\(\s*['"]([^'"]+)['"]""",
    re.I)
# 真实调用上下文：`api(` / `fetch(` / `api("GET", ` / `.open("GET", ` 等
_CALL_CTX = re.compile(
    r"""(?:^|[^\w$.])(?:api|fetch|_api|axios|request|sendBeacon|open)\s*\(\s*"""
    r"""(?:['"](?:GET|POST|PUT|DELETE|PATCH)['"]\s*,\s*)?$""",
    re.I)
_FN_DEF = re.compile(r"(?:async\s+)?function\s+([A-Za-z_$][\w$]*)")


# ★ 唯一权威：`engine/js_source.strip_comments`（只剥注释、**保留字面量**）。
#   本脚本**不得**再自带实现 —— 曾因自带朴素实现遇正则字面量脱同步而产出假判据。
sys.path.insert(0, str(ROOT))
from engine.js_source import strip_comments as strip_js_comments      # noqa: E402


def norm(p: str) -> str:
    p = _TPL.sub("<p>", p)
    p = re.sub(r"/\$\{[^}]*\}", "/<p>", p)
    p = re.sub(r"<[^>]*>", "<p>", p)
    p = re.sub(r"\{[^}]*\}", "<p>", p)
    return p.split("?", 1)[0].rstrip("/") or "/"


def _enclosing_fn(src: str, pos: int) -> str | None:
    ms = list(_FN_DEF.finditer(src, 0, pos))
    return ms[-1].group(1) if ms else None


def _call_sites() -> dict[str, int]:
    """全仓（JS + HTML）里 `NAME(` 的出现次数，用于判"该函数是否被调用"。"""
    counts: dict[str, int] = {}
    for f in list(STATIC_DIR.rglob("*.js")) + list(STATIC_DIR.glob("*.html")):
        src = f.read_text(encoding="utf-8", errors="ignore")
        if f.suffix == ".js":
            src = strip_js_comments(src)
        for m in re.finditer(r"([A-Za-z_$][\w$]*)\s*\(", src):
            counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    return counts


def js_calls() -> tuple[dict[tuple, set], dict[tuple, set], dict[tuple, set]]:
    """返回 (真调用, 死代码, 路径常量) 三组 `{(method, path): {file:line}}`。"""
    real: dict[tuple, set] = {}
    dead: dict[tuple, set] = {}
    const: dict[tuple, set] = {}
    fn_counts = _call_sites()
    for f in sorted(JS_DIR.glob("*.js")):
        raw = f.read_text(encoding="utf-8", errors="ignore")
        txt = strip_js_comments(raw)          # ★① 先剥注释
        for m in _LIT.finditer(txt):
            lit, s, e = m.group(1), m.start(), m.end()
            if lit.rstrip("/") in ("/api", ""):
                continue
            tail = txt[e:e + 12].lstrip()
            if tail.startswith("+"):
                lit = lit.rstrip("/") + "/<p>"
            after = txt[e:e + 220]
            before = txt[max(0, s - 60):s]
            mm = _METHOD_BEFORE.search(before)
            if mm:
                method = mm.group(1).upper()
            else:
                ma = _METHOD_AFTER.search(after)
                method = ma.group(1).upper() if ma else "GET"
            if method == "API_ROUTE":
                method = "GET"
            key = (method, norm(lit))
            where = "%s:%d" % (f.name, raw[:s].count("\n") + 1)
            if not _CALL_CTX.search(before):
                const.setdefault(key, set()).add(where)      # ★② 非调用上下文
                continue
            fn = _enclosing_fn(txt, s)
            if fn and fn_counts.get(fn, 0) <= 1:
                dead.setdefault(key, set()).add("%s（在 %s 内，该函数全仓无调用）" % (where, fn))
            else:
                real.setdefault(key, set()).add(where)
    return real, dead, const


def be_routes() -> dict[tuple, set]:
    out: dict[tuple, set] = {}
    for f in ROOT.rglob("*.py"):
        parts = f.relative_to(ROOT).parts
        if parts and parts[0] in {"baseline", ".venv", "venv", "node_modules", "__pycache__"}:
            continue
        if len(parts) >= 2 and parts[0] == "data" and parts[1] == "trash":
            continue
        try:
            txt = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for m in _ROUTE.finditer(txt):
            meth, p = m.group(1).upper(), norm(m.group(2))
            meth = "GET" if meth == "API_ROUTE" else meth
            out.setdefault((meth, p), set()).add(str(f.relative_to(ROOT)).replace("\\", "/"))
    return out


def path_only(calls_or_routes) -> dict[str, set]:
    d: dict[str, set] = {}
    for (_m, p), v in calls_or_routes.items():
        d.setdefault(p, set()).update(v)
    return d


def _diff(calls: dict[tuple, set], be_paths: dict[str, set],
          be_by_path: dict[str, set]) -> tuple[list, list]:
    broken, mismatch = [], []
    for (m, p), files in sorted(calls.items()):
        if p not in be_paths:
            pseg = p.strip("/").split("/")
            hit = None
            for bp in be_paths:
                bseg = bp.strip("/").split("/")
                if len(bseg) == len(pseg) and all(
                        a == b or a == "<p>" or b == "<p>" for a, b in zip(pseg, bseg)):
                    hit = bp
                    break
            broken.append((m, p, files, hit))
        elif m not in be_by_path.get(p, set()):
            mismatch.append((m, p, files, be_by_path[p]))
    return broken, mismatch


def main() -> int:
    real, dead, const = js_calls()
    be = be_routes()
    be_paths, be_by_path = path_only(be), {}
    for (m, p) in be:
        be_by_path.setdefault(p, set()).add(m)

    b_real, mm_real = _diff(real, be_paths, be_by_path)
    b_dead, _ = _diff(dead, be_paths, be_by_path)

    print("前端**真实调用** %d 条（方法+路径）；后端路由 %d 条" % (len(real), len(be)))
    print("=" * 88)
    print("\n【A1】真断链（真实调用 + 归属函数确有调用）: %d 条" % len(b_real))
    for m, p, files, hit in b_real:
        extra = ("  ← 路径相近: %s" % hit) if hit else ""
        print("  ✗ %-6s %-44s ← %s%s" % (m, p, ", ".join(sorted(files)[:3]), extra))
    if not b_real:
        print("  （无 —— 前端每个生效中的调用都能在后端找到路由）")
    else:
        print("  ↑ 是否在**页面加载路径**上请以浏览器实测为准（本轮 Chrome 实测：主加载路径 0 条）。")

    print("\n【A2】死代码（真实调用，但归属函数全仓从未被调用 ⇒ 不在生效路径）: %d 条" % len(b_dead))
    for m, p, files, _hit in b_dead:
        print("  · %-6s %-44s ← %s" % (m, p, ", ".join(sorted(files)[:2])))

    print("\n【A3】路径常量（非调用上下文，如 `var API = \"/api/...\"`）: %d 条" % len(const))
    for (m, p), files in sorted(const.items()):
        print("  · %-6s %-44s ← %s" % (m, p, ", ".join(sorted(files))))

    print("\n【B】路径存在但 HTTP 方法不匹配（405）: %d 条" % len(mm_real))
    for m, p, files, okm in mm_real:
        print("  ✗ %-6s %-44s 后端只有 %s  ← %s"
              % (m, p, "/".join(sorted(okm)), ", ".join(sorted(files)[:3])))

    js_paths = path_only(real)
    unread = []
    for (m, p), files in sorted(be.items()):
        if p.startswith("/api/") and p not in js_paths:
            unread.append((m, p))
    print("\n【C】后端存在但前端从未调用（僵尸接口，供参考）: %d 条" % len(unread))
    for m, p in unread[:40]:
        print("  · %-6s %s" % (m, p))
    if len(unread) > 40:
        print("  ... 另有 %d 条" % (len(unread) - 40))
    print("\n结论口径：**只需关注【A1】与【B】**；【A2】【A3】不在生效路径（详见脚本头注释）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
