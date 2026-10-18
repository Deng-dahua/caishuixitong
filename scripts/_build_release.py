# -*- coding: utf-8 -*-
"""生成 **release-v1.0.0** 交付包（2026-10-18）。

产出（不打包第三方依赖，只打包**可运行的最小集**）：

    release-v1.0.0/
      ├── backend/          后端运行包（全部 .py + 配置 + 启动脚本 + 依赖锁）
      ├── frontend/         前端静态资源（static/）
      ├── db-init/          数据初始化（规则库 / 法规库 / 分层与行次映射）
      ├── docs/             全套文档（含终验报告与确认单）
      ├── evidence/         验收证据（截图 / 审计日志 / 机制取证 / 回归摘要）
      ├── MANIFEST.sha256   逐文件校验值
      └── README_交付说明.md

★ 只读：不改动源仓库任何文件；不打包 `data/`（运行期数据）与 `.venv/`。
用法：python scripts/_build_release.py [--out release-v1.0.0]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: 后端运行包要收的目录/文件（**白名单**：宁缺勿滥，避免把隔离实例数据打进去）
BACKEND_DIRS = ("engine", "routers", "tools", "scripts")
BACKEND_FILES = (
    "main.py", "security.py", "security_web.py", "database.py", "logkit.py",
    "runtime_storage.py", "request_context.py", "projects_api.py", "documents_api.py",
    "analysis_api.py", "extract_api.py", "parse_api.py", "risks_api.py", "reports_api.py",
    "rules_api.py", "rule_versions_api.py", "legal_api.py", "rbac_api.py",
    "dashboard_api.py", "backup_api.py", "consent_api.py", "industry_api.py",
    "ai_assist_api.py", "tax_models_api.py", "tax_rules_api.py", "ocr_api.py",
    "error_pages_api.py",
    "requirements.lock", "start8001.bat", "start.sh", "pytest.ini", ".gitattributes",
)

#: 数据初始化（含规则库/法规库/法规分层/申报行次映射）
DB_INIT_FILES = (
    "config/legal_law_tiers.json", "config/declaration_lines.json",
    "config/standard_fields.json", "config/document_categories.json",
    "config/rbac.json", "config/frontend_perms.json", "config/rule_versions.json",
    "config/conclusion_grades.json", "config/report_identity.json",
    "config/legal_text_coverage.json", "config/industry_params.json",
    "static/legal_library.json", "static/filename_type_map.json",
    "static/legal_catalog.json", "static/legal_provisions.json",
)
DB_INIT_DIRS = ("config",)

#: 文档与证据
DOC_DIRS = ("docs",)

#: 明确排除（大件/环境/运行期数据）
# ★ `scripts/four_reports/` 是**产物目录**（`.gitignore` 已排除）：里面是历次真跑生成的
#   20~34MB JSON 快照，属"当次验收产物"，不是交付物；打进包会让 269MB → 30MB 级差异，
#   且会让人误以为"系统自带样例报告"。
EXCLUDE_PAT = ("__pycache__", ".pyc", "_audit_20261018", "_scenario_sim",
               ".venv", "data", "baseline", "_bak", "_archive",
               "scripts/four_reports", "four_reports")


def _skip(path: str) -> bool:
    low = path.replace("\\", "/")
    return any(p in low for p in EXCLUDE_PAT)


def _copy_tree(src: str, dst: str, exts=None) -> int:
    n = 0
    for base, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if not _skip(os.path.join(base, d))]
        for f in files:
            sp = os.path.join(base, f)
            if _skip(sp):
                continue
            if exts and os.path.splitext(f)[1].lower() not in exts:
                continue
            rel = os.path.relpath(sp, ROOT)
            dp = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(dp), exist_ok=True)
            shutil.copy2(sp, dp)
            n += 1
    return n


def _sha256(p: str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


README = """# 财税稽查系统 · 交付包 v1.0.0-release

生成时间：%(ts)s
代码基线：%(commit)s
标签：v1.0.0-release

## 目录说明

| 目录 | 内容 |
|---|---|
| `backend/` | 后端运行包：全部 Python 源码（engine / routers / tools / scripts + 根级模块）、`requirements.lock`、`start8001.bat` |
| `frontend/` | 前端静态资源（`static/`，28 个页面 / 37 个 JS，版本号已同步） |
| `db-init/` | 数据初始化：规则库、法规库正文（7,692 条）、法规分层、申报行次映射、RBAC 与前端权限表 |
| `docs/` | 全套文档（66 份），**含本版终验报告与交付确认单**（`docs/收口_20261018/`） |
| `evidence/` | 验收证据：6 张真实浏览器截图、一致性审计日志、回归摘要、十二机制取证 JSON |
| `MANIFEST.sha256` | 逐文件校验值（可用 `sha256sum -c MANIFEST.sha256` 校验） |

## 部署步骤（单机）

1. 安装 Python 3.13。
2. `cd backend && python -m venv .venv`
3. `.venv/Scripts/python.exe -m pip install -r requirements.lock`
4. 把 `frontend/static` 与 `db-init/` 的内容放回 `backend/` 对应位置
   （交付包为便于检查而分目录；运行要求 `static/` 与 `config/` 位于 `backend/` 下）。
5. 双击 `start8001.bat`，浏览器打开 `http://127.0.0.1:8001`
6. 首次登录后用管理员账号进入，**立即修改初始口令**。

## 三条使用边界（务必知悉）

1. **单实例部署**：SQLite + WAL，同一库只允许一个服务进程（多实例会争锁）。
2. **单份明细表上限 5,000 行**（序时账/银行流水/发票/存货/科目余额）；超限会截断并给出
   可见回执（"共 X 行，本次读入前 5,000 行，超出部分未参与分析"）。
3. **外部工商核验未对接**（天眼查/企查查），系统按"外部核验不可得"走中性口径。

## 结论性质

系统输出为**内部辅助分析**（待核事项与线索），**不构成税务行政执法文书效力**；
最终结论须由有权人员依法复核。无法规依据的发现已自动降级为"线索"并显式标注。

## 遗留事项

见 `docs/收口_20261018/v2_Backlog_20261018.md`（8 项，含启动条件）。
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="release-v1.0.0")
    args = ap.parse_args(argv)
    out = os.path.join(ROOT, args.out)
    if os.path.isdir(out):
        # 只清本脚本自己的产物目录（限定具体路径，不用通配）
        for sub in ("backend", "frontend", "db-init", "docs", "evidence"):
            p = os.path.join(out, sub)
            if os.path.isdir(p):
                shutil.rmtree(p)
    os.makedirs(out, exist_ok=True)

    counts = {}
    # 1) backend
    bdir = os.path.join(out, "backend")
    n = 0
    for d in BACKEND_DIRS:
        src = os.path.join(ROOT, d)
        if os.path.isdir(src):
            n += _copy_tree(src, bdir, exts={".py", ".json", ".txt", ".md"})
    # 根级必需模块 + 全部 *api*.py
    import glob
    for p in glob.glob(os.path.join(ROOT, "*.py")):
        base = os.path.basename(p)
        if base.startswith("_") or base.startswith("test_"):
            continue
        os.makedirs(bdir, exist_ok=True)
        shutil.copy2(p, os.path.join(bdir, base))
        n += 1
    for f in BACKEND_FILES:
        sp = os.path.join(ROOT, f)
        if os.path.isfile(sp) and not any(
                os.path.exists(os.path.join(bdir, f)) for _ in (0,)):
            os.makedirs(os.path.dirname(os.path.join(bdir, f)) or bdir, exist_ok=True)
            shutil.copy2(sp, os.path.join(bdir, f))
            n += 1
    counts["backend"] = n

    # 2) frontend
    counts["frontend"] = _copy_tree(os.path.join(ROOT, "static"),
                                    os.path.join(out, "frontend"))

    # 3) db-init
    n = 0
    for f in DB_INIT_FILES:
        sp = os.path.join(ROOT, f)
        if os.path.isfile(sp):
            dp = os.path.join(out, "db-init", f)
            os.makedirs(os.path.dirname(dp), exist_ok=True)
            shutil.copy2(sp, dp)
            n += 1
    for d in DB_INIT_DIRS:
        src = os.path.join(ROOT, d)
        if os.path.isdir(src):
            for base, dirs, files in os.walk(src):
                dirs[:] = [x for x in dirs if not _skip(os.path.join(base, x))]
                for f in files:
                    sp = os.path.join(base, f)
                    if _skip(sp) or not f.endswith(".json"):
                        continue
                    rel = os.path.relpath(sp, ROOT)
                    dp = os.path.join(out, "db-init", rel)
                    os.makedirs(os.path.dirname(dp), exist_ok=True)
                    shutil.copy2(sp, dp)
                    n += 1
    counts["db-init"] = n

    # 4) docs
    counts["docs"] = _copy_tree(os.path.join(ROOT, "docs"),
                                os.path.join(out, "docs"), exts={".md", ".txt"})

    # 5) evidence（已在 docs/收口_20261018/evidence，另复制一份到顶层便于查看）
    ev_src = os.path.join(ROOT, "docs", "收口_20261018", "evidence")
    counts["evidence"] = _copy_tree(ev_src, os.path.join(out, "evidence")) \
        if os.path.isdir(ev_src) else 0

    # 6) MANIFEST + README
    commit = ""
    try:
        import subprocess
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                capture_output=True, text=True).stdout.strip()
    except Exception:                                     # noqa: BLE001
        commit = "（未知）"
    import time
    with open(os.path.join(out, "README_交付说明.md"), "w", encoding="utf-8") as fh:
        fh.write(README % {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "commit": commit})

    lines = []
    for base, dirs, files in os.walk(out):
        dirs[:] = sorted(dirs)
        for f in sorted(files):
            p = os.path.join(base, f)
            rel = os.path.relpath(p, out).replace("\\", "/")
            if rel == "MANIFEST.sha256":
                continue
            lines.append("%s  %s" % (_sha256(p), rel))
    with open(os.path.join(out, "MANIFEST.sha256"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    total_bytes = 0
    for base, _d, files in os.walk(out):
        for f in files:
            total_bytes += os.path.getsize(os.path.join(base, f))
    summary = {"out": out, "commit": commit, "counts": counts,
               "files": len(lines), "size_mb": round(total_bytes / 1024 / 1024, 2)}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
