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
#: `APIRouter(prefix="...")` —— ★ 2026-10-19 补：此前**从未解析前缀**。
#: 事故：`business_api.py` 用 `APIRouter(prefix="/api/v1/business")` + `@router.get("/query")`，
#: 旧脚本把后端路径记成 `/query` ⇒ 前端真实的 `/api/v1/business/query` 被判 404（假红），
#: 反之也可能把"后端真有、前端拼错前缀"判成通过（假绿）。项目 v1 接口几乎全是这种写法。
_ROUTER_PREFIX = re.compile(
    r"""(\w+)\s*=\s*APIRouter\(\s*(?:[^)]*?)prefix\s*=\s*['"]([^'"]+)['"]""", re.I)
#: 路由装饰器归属哪个 router 变量（`@router.get` / `@rt.get` …）
_ROUTE_OWNER = re.compile(
    r"""@(\w+)\.(get|post|put|delete|patch|api_route)\(\s*['"]([^'"]+)['"]""", re.I)
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


def _loaded_scripts() -> set[str]:
    """被**任一** `static/*.html` 引用加载的 js 文件名集合。

    ★ 2026-10-19 加：用于把"孤儿脚本"从【A1 真断链】里分出去。
      事故样本：`human-learning-page.js` 在后端接口删除后仍留在 `index.html` 里被加载，
      但它**没有任何页面容器**（`page-human-learning` 不存在于 html，也不在 `_allowedPages`）
      ⇒ 用户根本到不了那个页面，它的调用不属于"生效路径上的断链"。
      删掉那行加载后，若判据仍把该文件算进 A1，就会**永远剩 2 条红**（常红判据会掩盖真回归）。
      ⇒ 正确分层：**是否被页面加载**决定它是否可能影响用户；未加载的脚本单列【A5】。
    """
    names: set[str] = set()
    for h in STATIC_DIR.glob("*.html"):
        try:
            txt = h.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in re.finditer(r"""<script[^>]+src=["']/static/js/([^"'?]+)""", txt):
            names.add(m.group(1))
    return names


def js_calls() -> tuple[dict[tuple, set], dict[tuple, set], dict[tuple, set], dict[tuple, set]]:
    """返回 (真调用, 死代码, 路径常量, 未加载脚本里的调用) 四组 `{(method, path): {file:line}}`。

    第四组单独返回：这些调用所在的 js **没有被任何页面加载** ⇒ 用户碰不到，
    不应计入【A1 真断链】（否则删了加载也永远红）。
    """
    real: dict[tuple, set] = {}
    dead: dict[tuple, set] = {}
    const: dict[tuple, set] = {}
    orphan: dict[tuple, set] = {}
    fn_counts = _call_sites()
    loaded = _loaded_scripts()
    for f in sorted(JS_DIR.glob("*.js")):
        raw = f.read_text(encoding="utf-8", errors="ignore")
        txt = strip_js_comments(raw)          # ★① 先剥注释
        is_loaded = f.name in loaded
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
            if not is_loaded:
                orphan.setdefault(key, set()).add(where)     # ★③ 孤儿脚本（页面未加载）
                continue
            fn = _enclosing_fn(txt, s)
            if fn and fn_counts.get(fn, 0) <= 1:
                dead.setdefault(key, set()).add("%s（在 %s 内，该函数全仓无调用）" % (where, fn))
            else:
                real.setdefault(key, set()).add(where)
    return real, dead, const, orphan


def be_routes() -> tuple[dict[tuple, set], dict[str, str]]:
    """(路由表, 动态路由的 handler 源码片段)。

    第二项用于**从 handler 里读它自己承认的允许值**（`virtual_assets` / `filenames` 等），
    从而判定"路径被 `{param}` 接管后到底是不是 404" —— 而不是靠比路径猜。
    """
    out: dict[tuple, set] = {}
    bodies: dict[str, str] = {}
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
        # ★ 先取该文件的 router 前缀表（`rt = APIRouter(prefix="/api/v1/x")`）
        prefixes = {m.group(1): m.group(2).rstrip("/")
                    for m in _ROUTER_PREFIX.finditer(txt)}
        for m in _ROUTE_OWNER.finditer(txt):
            owner, meth, raw_path = m.group(1), m.group(2).upper(), m.group(3)
            # 只有非 app 的 router 才拼前缀（`@app.get` 的路径本身已含完整前缀）
            pfx = "" if owner in ("app",) else prefixes.get(owner, "")
            full = (pfx + "/" + raw_path.lstrip("/")) if pfx else raw_path
            p = norm(full)
            meth = "GET" if meth == "API_ROUTE" else meth
            out.setdefault((meth, p), set()).add(str(f.relative_to(ROOT)).replace("\\", "/"))
            if "<p>" in p and p not in bodies:   # norm 后参数段已归一为 `<p>`
                # 取 handler 主体近似：从装饰器之后到下一个顶层装饰器/函数定义（够覆盖参数解析）
                tail = txt[m.end():m.end() + 6000]
                cut = re.search(r"\n@(?:app|router|bp|api|rt|r)\.", tail)
                bodies[p] = tail[:cut.start()] if cut else tail
    return out, bodies


def path_only(calls_or_routes) -> dict[str, set]:
    d: dict[str, set] = {}
    for (_m, p), v in calls_or_routes.items():
        d.setdefault(p, set()).update(v)
    return d


#: 动态路由里"允许值"的**解析来源**（不另立白名单 —— 从 handler 源码读，避免多头维护）。
#: 只认这几个已知的映射变量名；其它动态路由若解析不到，判据会标注"需运行时确认"，
#: 而不是像旧版那样**一律当 404**。
_ALLOW_MAP = re.compile(r"(?:virtual_assets|filenames|_ASSETS|_MAP)\s*=\s*\{([\s\S]{0,4000}?)\n\s*\}")
_ALLOW_KEY = re.compile(r"""['"]([\w.\-]+)['"]\s*:""")


def _dyn_allow(bodies: dict[str, str], route_path: str) -> set[str]:
    """从该路由 handler 源码里取"允许的 asset 值"集合（取不到 ⇒ 空集）。"""
    body = bodies.get(route_path) or ""
    out: set[str] = set()
    for m in _ALLOW_MAP.finditer(body):
        out.update(_ALLOW_KEY.findall(m.group(1)))
    return out


def _diff(calls: dict[tuple, set], be_paths: dict[str, set],
          be_by_path: dict[str, set], dyn_allow: dict[str, set] | None = None
          ) -> tuple[list, list, list]:
    """三段结果：真断链 / 动态路由接管 / 方法不匹配（405）。

    ★ 2026-10-19 修假红（skill 已记的坑 5 终于落到脚本里）：
      旧实现把"路径相近"的 `hit` 只当**提示**打印，仍算进真断链 ⇒
      `/api/tax-assets/analysis` 这类**被 `{asset_name}` 动态路由接管**的调用被列成 404。
      实测后端 `main.py::get_tax_asset` 的 `virtual_assets` 白名单**含** analysis/clues/evidence
      ⇒ 完全可达，是假红。
      现改为：命中的 `hit` 若是 `{param}` 动态路由 ⇒ 再查 handler 白名单：
        · 值在白名单（或白名单解析不到）⇒ 归入【A4 动态路由接管】，**不算断链**；
        · 值**明确不在**白名单 ⇒ 仍算真断链（那是真 404，不能放过）。
    """
    dyn_allow = dyn_allow or {}
    broken, dynamic, mismatch = [], [], []
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
            # ★ 动态路由：末段是 `{param}`（已在 norm 里归一成 `<p>`）⇒ 由该 handler 接管
            if hit and "<p>" in hit:
                val = pseg[-1]
                allow = dyn_allow.get(hit) or set()
                if not allow or val in allow:
                    dynamic.append((m, p, files, hit, sorted(allow)[:6]))
                    continue
                # 值明确不在白名单 ⇒ 真 404
                broken.append((m, p, files, hit))
                continue
            broken.append((m, p, files, hit))
        elif m not in be_by_path.get(p, set()):
            mismatch.append((m, p, files, be_by_path[p]))
    return broken, dynamic, mismatch


def main() -> int:
    real, dead, const, orphan = js_calls()
    be, bodies = be_routes()
    be_paths, be_by_path = path_only(be), {}
    for (m, p) in be:
        be_by_path.setdefault(p, set()).add(m)

    # 动态路由 ⇒ 从 handler 源码读它承认的允许值（唯一来源，不另立白名单）
    dyn_allow = {p: _dyn_allow(bodies, p) for p in bodies}

    b_real, b_dyn, mm_real = _diff(real, be_paths, be_by_path, dyn_allow)
    b_dead, _, _ = _diff(dead, be_paths, be_by_path, dyn_allow)

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

    print("\n【A4】由 `{param}` 动态路由接管（**不是断链**，已按 handler 白名单核实）: %d 条"
          % len(b_dyn))
    for m, p, files, hit, allow in b_dyn:
        print("  ✓ %-6s %-40s ← %s" % (m, p, ", ".join(sorted(files)[:2])))
        print("      由 %s 接管；handler 承认的值%s"
              % (hit, ("：" + "、".join(allow)) if allow else "**解析不到** ⇒ 需运行时确认"))

    print("\n【A5】孤儿脚本里的调用（所在 js **未被任何页面加载** ⇒ 用户碰不到，不算断链）: %d 条"
          % len(orphan))
    for (mm_, pp_), files in sorted(orphan.items()):
        print("  ○ %-6s %-40s ← %s" % (mm_, pp_, ", ".join(sorted(files))))
    if orphan:
        print("      处置建议：要么把该 js 从 static/js 删掉、要么在 index.html 恢复加载；"
              "留着不加载只会让下一次审计继续看到它。")

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
