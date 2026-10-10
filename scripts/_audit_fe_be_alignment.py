# -*- coding: utf-8 -*-
"""前端 ↔ 后端 **方法与路径** 对齐审计（只读）。

为什么需要：(仅比路径会漏掉一类真缺陷——路径存在但 HTTP 方法不符 ⇒ 405）。
  本项目实测口径：`fetch(url, {method:'DELETE'})` 与 `api('POST', url)` 两种写法都要认。

输出：
  【A】前端调用无对应后端路由（真断链，404）
  【B】路径存在但方法不匹配（405）
  【C】后端存在但前端从未调用（僵尸接口，供参考）

用法：python scripts/_audit_fe_be_alignment.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS_DIR = ROOT / "static" / "js"

_LIT = re.compile(r"""['"`](/api/[^'"`\s]*)['"`]""")
_TPL = re.compile(r"\$\{[^}]*\}")
_METHOD_AFTER = re.compile(r"method\s*:\s*['\"](\w+)['\"]")
_METHOD_BEFORE = re.compile(r"['\"](GET|POST|PUT|DELETE|PATCH)['\"]\s*,\s*$", re.I)
_ROUTE = re.compile(
    r"""@(?:app|router|bp|api)\.(get|post|put|delete|patch|api_route)\(\s*['"]([^'"]+)['"]""",
    re.I)


def norm(p: str) -> str:
    p = _TPL.sub("<p>", p)
    p = re.sub(r"/\$\{[^}]*\}", "/<p>", p)
    p = re.sub(r"<[^>]*>", "<p>", p)
    p = re.sub(r"\{[^}]*\}", "<p>", p)
    return p.split("?", 1)[0].rstrip("/") or "/"


def js_calls() -> dict[tuple, set]:
    out: dict[tuple, set] = {}
    for f in sorted(JS_DIR.glob("*.js")):
        txt = f.read_text(encoding="utf-8", errors="ignore")
        for m in _LIT.finditer(txt):
            lit, s, e = m.group(1), m.start(), m.end()
            if lit.rstrip("/") in ("/api", ""):
                continue
            # ★ 拼接写法 `'/api/x/' + id` ⇒ 末段是变量，归一为 <p>
            #   （不处理会把 `DELETE /api/companies/{id}` 误判成 `DELETE /api/companies` ⇒ 假 405）
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
            out.setdefault(key, set()).add(f.name)
    return out


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


def main() -> int:
    js, be = js_calls(), be_routes()
    js_paths, be_paths = path_only(js), path_only(be)
    be_by_path: dict[str, set] = {}
    for (m, p) in be:
        be_by_path.setdefault(p, set()).add(m)

    broken, mismatch = [], []
    for (m, p), files in sorted(js.items()):
        if p not in be_paths:
            # 同长度段匹配（前端拼 id 时可能剩尾斜杠）
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

    print("前端调用 %d 条（方法+路径）；后端路由 %d 条" % (len(js), len(be)))
    print("=" * 84)
    print("\n【A】前端调用无对应后端路由（404）: %d 条" % len(broken))
    for m, p, files, hit in broken:
        extra = ("  ← 路径相近: %s" % hit) if hit else ""
        print("  ✗ %-6s %-46s ← %s%s" % (m, p, ", ".join(sorted(files)), extra))

    print("\n【B】路径存在但 HTTP 方法不匹配（405）: %d 条" % len(mismatch))
    for m, p, files, okm in mismatch:
        print("  ✗ %-6s %-46s 后端只有 %s  ← %s"
              % (m, p, "/".join(sorted(okm)), ", ".join(sorted(files))))

    unread = []
    for (m, p), files in sorted(be.items()):
        if p.startswith("/api/") and p not in js_paths:
            unread.append((m, p))
    print("\n【C】后端存在但前端从未调用（僵尸接口）: %d 条" % len(unread))
    for m, p in unread[:40]:
        print("  · %-6s %s" % (m, p))
    if len(unread) > 40:
        print("  ... 另有 %d 条" % (len(unread) - 40))
    return 0


if __name__ == "__main__":
    sys.exit(main())
