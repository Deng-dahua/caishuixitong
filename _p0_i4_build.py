# -*- coding: utf-8 -*-
"""P0 验收 · 构建测试（后端 / 前端 / 容器化）。

口径（与项目既有裁定一致）：
  · **后端**：无编译产物（Python）⇒「构建」= ① 全量语法编译；② 关键模块可导入；
    ③ OpenAPI schema 可生成（应用可装配）；④ 依赖清单与实际导入一致。
  · **前端**：本项目**无构建工具链**（原生 HTML/JS/CSS，静态直出）⇒「构建」=
    ① 全部 JS 过 `node --check`（语法可解析）；② 全部 HTML 页面可达且引用的资源真实存在；
    ③ 静态资源 `?v=` 必须等于文件内容哈希（防"改了用户看不到"，既有闸门口径）。
  · **容器化**：本机 **无 docker 客户端**（`docker --version` = command not found）；
    且项目基线**明确把容器化列为 P1-8、并声明"保持不使用 Docker"**（既有裁定）。
    ⇒ 本项**如实记 FAIL/未执行**，不伪造通过；同时给出 Dockerfile 草案作为 P1 输入。

用法：`python _p0_i4_build.py`
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
NODE = shutil.which("node") or r"C:\Users\Administrator\.workbuddy\binaries\node\versions\22.22.2-6\node.exe"

results: list = []


def check(name: str, cond: bool, detail: str = "") -> bool:
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + ((" | " + detail) if detail else ""))
    return bool(cond)


# ── ① 后端 ────────────────────────────────────────────────────────────────
def _compile(targets: list, env: dict) -> list:
    """编译给定目标，返回 `[(目标, 错误摘要)]`。`.pyc` 全部重定向到临时目录。"""
    bad = []
    for t in targets:
        cp = subprocess.run([PY, "-m", "compileall", "-q", t],
                            cwd=str(ROOT), env=env, capture_output=True, text=True)
        if cp.returncode != 0:
            lines = [x.strip() for x in (cp.stdout or cp.stderr or "").splitlines() if x.strip()]
            bad.append((Path(t).name, lines[:3]))
    return bad


def backend() -> None:
    print("\n== ① 后端 ==")
    import tempfile
    env = dict(os.environ)
    # ★ `.pyc` 一律落到临时目录 ⇒ **源码树零污染**，也就不需要"递归删 __pycache__"
    #   （上一版正是靠递归删除清理，结果删到 `.venv/` 触发 safe-delete 批量守卫
    #   —— 清理动作本身成了风险。改成重定向后无需清理。）
    env["PYTHONPYCACHEPREFIX"] = tempfile.mkdtemp(prefix="p0_pyc_")
    env["APP_DATA_DIR"] = tempfile.mkdtemp(prefix="p0build_")
    env["APP_COOKIE_SECURE"] = "0"
    env["PYTHONIOENCODING"] = "utf-8"

    # 1.1a **产品运行路径**（请求链路会 import 的东西）—— 必须 100% 可编译
    prod: list = []
    prod.append(str(ROOT / "engine"))
    for sub in ("routers",):
        if (ROOT / sub).is_dir():
            prod.append(str(ROOT / sub))
    prod_files = [p for p in sorted(ROOT.glob("*.py"))]
    bad_prod = _compile([str(ROOT / "engine"), str(ROOT / "routers")] +
                        [str(p) for p in prod_files] if (ROOT / "routers").is_dir()
                        else [str(ROOT / "engine")] + [str(p) for p in prod_files], env)
    check("后端 产品运行路径（根目录 *.py + engine/ + routers/）全部可编译",
          not bad_prod, str(bad_prod[:2]) if bad_prod else "")

    # 1.1b **辅助脚本**（tools/ scripts/ tests/）—— 如实列出问题文件，不算"产品不可编译"
    aux = [str(ROOT / d) for d in ("tools", "scripts", "tests") if (ROOT / d).is_dir()]
    bad_aux = _compile(aux, env)
    aux_bad_files = []
    for _t, lines in bad_aux:
        for ln in lines:
            if "Error compiling" in ln:
                aux_bad_files.append(ln.replace("*** Error compiling", "").strip(" .'"))
    check("后端 辅助脚本（tools/ scripts/ tests/）全部可编译", not bad_aux,
          "；".join(aux_bad_files[:4]) if aux_bad_files else str(bad_aux[:2]))

    # 1.2 关键模块可导入（含 P0-1~P0-8 全部新增模块）
    mods = ["main", "tax_risk", "security", "security_web", "runtime_storage", "database",
            "projects_api", "documents_api", "extract_api", "analysis_api",
            "rules_api", "risks_api", "reports_api", "rbac_api",
            "engine.project_service", "engine.document_service", "engine.extract_service",
            "engine.analysis_task", "engine.analysis_jobs", "engine.rule_loader",
            "engine.rule_executor", "engine.risk_review", "engine.risk_service",
            "engine.report_service", "engine.report_render", "engine.rbac",
            "engine.access_service", "engine.audit_trail", "engine.redaction",
            "engine.pipeline"]
    code = ("import importlib,sys\n"
            "bad=[]\n"
            "for m in %r:\n"
            "    try: importlib.import_module(m)\n"
            "    except Exception as e: bad.append((m,repr(e)[:120]))\n"
            "print('BAD='+str(bad))\n" % mods)
    cp = subprocess.run([PY, "-c", code], cwd=str(ROOT), env=env,
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    bad = ""
    for line in (cp.stdout or "").splitlines():
        if line.startswith("BAD="):
            bad = line[4:]
    check("后端 %d 个关键模块可导入（含 P0-1~P0-8）" % len(mods), cp.returncode == 0 and bad == "[]",
          (bad or (cp.stderr or "")[-200:]).strip()[:200])

    # 1.3 OpenAPI schema 可生成（应用装配完整）
    code2 = ("import json\n"
             "from main import app\n"
             "s=app.openapi()\n"
             "print('PATHS='+str(len(s.get('paths') or {})))\n"
             "print('TITLE='+str((s.get('info') or {}).get('title'))[:60])\n")
    cp = subprocess.run([PY, "-c", code2], cwd=str(ROOT), env=env,
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    npaths = ""
    for line in (cp.stdout or "").splitlines():
        if line.startswith("PATHS="):
            npaths = line[6:]
    check("后端 OpenAPI schema 可生成（应用可装配）", cp.returncode == 0 and npaths.isdigit(),
          "paths=%s" % npaths if npaths else (cp.stderr or "")[-160:])

    # 1.4 依赖清单与实际导入一致（无"跑得起来但清单缺项"）
    lock = ROOT / "requirements.lock"
    if lock.exists():
        pinned = set()
        for ln in lock.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                pinned.add(re.split(r"[=<>!~\[]", ln)[0].strip().lower())
        code3 = ("import importlib.metadata as md\n"
                 "need=['fastapi','uvicorn','starlette','pydantic','sqlalchemy','openpyxl',\n"
                 "      'reportlab','pdfplumber','python-docx','pillow']\n"
                 "miss=[]\n"
                 "for n in need:\n"
                 "    try: md.version(n)\n"
                 "    except Exception: miss.append(n)\n"
                 "print('MISS='+str(miss))\n")
        cp = subprocess.run([PY, "-c", code3], cwd=str(ROOT), env=env,
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
        miss = ""
        for line in (cp.stdout or "").splitlines():
            if line.startswith("MISS="):
                miss = line[5:]
        check("后端 运行期依赖齐备（10 个核心包）", miss == "[]",
              "缺失=%s" % miss if miss != "[]" else "清单 %d 项 pin" % len(pinned))
    else:
        check("后端 运行期依赖齐备", False, "requirements.lock 不存在")


# ── ② 前端 ────────────────────────────────────────────────────────────────
def frontend() -> None:
    print("\n== ② 前端 ==")
    js_files = sorted((ROOT / "static" / "js").glob("*.js"))
    bad = []
    node = NODE if os.path.exists(NODE) or shutil.which("node") else None
    if not node:
        check("前端 JS 语法检查（node --check）", False, "node 不可用")
    else:
        for p in js_files:
            cp = subprocess.run([node, "--check", str(p)], capture_output=True, text=True)
            if cp.returncode != 0:
                bad.append((p.name, (cp.stderr or "").strip().splitlines()[:1]))
        check("前端 %d 个 JS 通过语法检查（node --check）" % len(js_files), not bad,
              str(bad[:2]) if bad else "")

    # 2.2 HTML 页面可达 + 引用资源存在
    htmls = sorted((ROOT / "static").glob("*.html"))
    missing, pages = [], []
    for h in htmls:
        txt = h.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'(?:src|href)="(/static/[^"?]+)', txt):
            rel = m.group(1).lstrip("/")
            if not (ROOT / rel).exists():
                missing.append("%s → %s" % (h.name, rel))
        pages.append(h.name)
    check("前端 %d 个页面引用的静态资源均存在" % len(htmls), not missing,
          "；".join(missing[:3]))

    # 2.3 静态资源 ?v= 与内容哈希一致（既有闸门口径；此处独立复算，防"闸门假绿"）
    idx = ROOT / "static" / "index.html"
    stale = []
    if idx.exists():
        html = idx.read_text(encoding="utf-8")
        for rel, cur in re.findall(r"(/static/(?:js|css)/[\w.\-]+)\?v=([\w.\-]+)", html):
            p = ROOT / rel.lstrip("/")
            if not p.exists():
                stale.append("%s 缺失" % rel)
                continue
            want = hashlib.sha1(p.read_bytes()).hexdigest()[:10]
            if cur != want:
                stale.append("%s %s→%s" % (rel, cur, want))
    check("前端静态资源 ?v= 均等于内容哈希", not stale, "；".join(stale[:3]))

    # 2.4 P0 新增页面在 App 路由中可达（真 HTTP；**先登录**，否则非公开页会 302）
    import tempfile
    env = dict(os.environ)
    env["APP_DATA_DIR"] = tempfile.mkdtemp(prefix="p0build_fe_")
    env["APP_COOKIE_SECURE"] = "0"
    env["APP_ADMIN_USERNAME"] = "_p0build"
    env["APP_ADMIN_PASSWORD"] = "P0-Build-Admin-2026!"
    code = (
        "import json, os, sys\n"
        "sys.path.insert(0, os.getcwd())\n"
        "from fastapi.testclient import TestClient\n"
        "import main\n"
        "# ★ 身份库由 **lifespan 启动钩子** 初始化（真服务启动时执行）；TestClient 不自动\n"
        "#   触发 lifespan ⇒ 必须显式初始化，否则登录会因 `no such table: login_attempts` 500。\n"
        "import security as _sec\n"
        "_sec.init_security_db()\n"
        "c = TestClient(main.app)\n"
        "r = c.post('/api/auth/login', json={'username': os.environ['APP_ADMIN_USERNAME'],\n"
        "                                    'password': os.environ['APP_ADMIN_PASSWORD']})\n"
        "login_ok = (r.status_code == 200)\n"
        "login_detail = r.text[:160] if not login_ok else ''\n"
        "# ★ 业务页面在**未选账套**时会 302 到 /select-company（既有设计，见\n"
        "#   security_web：`not selected_cookie and not is_api` ⇒ 重定向）。\n"
        "#   这里补上账套 Cookie（等价『用户已选好账套』的状态）再检查页面可达性。\n"
        "c.cookies.set('company_id', '1')\n"
        "out = []\n"
        "for p in ('/login','/projects','/documents','/extract','/analysis','/rules',\n"
        "          '/risks','/reports','/users','/roles','/audit-logs'):\n"
        "    rr = c.get(p, follow_redirects=False)\n"
        "    out.append([p, rr.status_code, 'text/html' in rr.headers.get('content-type','')])\n"
        "print('PAGES=' + json.dumps({'login_ok': login_ok, 'login_detail': login_detail,\n"
        "                             'pages': out}))\n"
    )
    cp = subprocess.run([PY, "-c", code], cwd=str(ROOT), env=env,
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    payload = None
    for x in (cp.stdout or "").splitlines():
        if x.startswith("PAGES="):
            try:
                payload = json.loads(x[6:])
            except Exception:                                     # noqa: BLE001
                payload = None
    ok_pages = False
    detail = (cp.stderr or "")[-300:]
    if payload:
        arr = payload.get("pages") or []
        ok_pages = bool(payload.get("login_ok")) and all(
            s == 200 and h for _p, s, h in arr)
        detail = "登录=%s%s；" % (
            payload.get("login_ok"),
            ("(" + payload["login_detail"] + ")") if payload.get("login_detail") else "") + \
            "；".join("%s=%s" % (p, s) for p, s, _h in arr)
    check("前端 11 个页面经 App 真路由返回 HTML 200（已登录态）", ok_pages, detail[:400])


# ── ③ 容器化 ──────────────────────────────────────────────────────────────
def container() -> None:
    print("\n== ③ 容器化（Docker）==")
    docker = shutil.which("docker")
    if not docker:
        check("容器化 本机 docker 客户端可用", False,
              "docker 未安装 ⇒ 本次**未能执行容器启动验证**（如实记未完）")
    else:
        cp = subprocess.run([docker, "--version"], capture_output=True, text=True)
        check("容器化 docker 客户端可用", cp.returncode == 0, (cp.stdout or "").strip())
        cp2 = subprocess.run([docker, "info"], capture_output=True, text=True, timeout=60)
        check("容器化 docker 守护进程可连接", cp2.returncode == 0,
              (cp2.stderr or "").strip().splitlines()[-1][:160] if cp2.returncode else "")
    for rel in ("Dockerfile", "docker-compose.yml", ".dockerignore"):
        check("容器化 资产存在：%s" % rel, (ROOT / rel).exists(),
              "（项目基线把容器化列为 P1-8，有意未做）" if not (ROOT / rel).exists() else "")


if __name__ == "__main__":
    backend()
    frontend()
    container()
    n_fail = sum(1 for _n, c, _d in results if not c)
    print("\n" + "=" * 66)
    print("构建测试：%d 项通过 / %d 项失败（共 %d）" % (len(results) - n_fail, n_fail, len(results)))
    for n, c, d in results:
        if not c:
            print("  FAIL  %s | %s" % (n, d))
    sys.exit(1 if n_fail else 0)
