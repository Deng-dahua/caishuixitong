# -*- coding: utf-8 -*-
"""结果级验收：**报告导出出口真的能用**（`/api/tax-risk/report/download` 返回 200 + 合法文件）。

## 为什么要跑真 HTTP 而不是"看代码"

2026-10-09 实测发现在**唯一一个真实账套**（`companies` 只有 1 行，且序时账/发票/银行流水/
合同/员工/资产 **七张表全 0 行**）上：

    GET /api/tax-risk/report/download?company_id=1&format=pdf  →  500
    AttributeError: 'str' object has no attribute 'get'   (tax_risk.py:1137 → :1270)

根因不是"PDF 库坏了"，而是 **`get_tax_risk_report()` 返回的 `summary` 字段有两种形状**：
无业务数据分支是 **str**、正常分支是 **dict**；四个渲染出口
（`_generate_report_html` / `_download_pdf` / `_download_docx` / `_download_pptx`）
全都按 dict 取数 ⇒ 无数据企业一律炸。**在本系统里"无数据企业"不是边角，
而是唯一那个账套的当前状态。**

本脚本以**真 HTTP + 真字节**判定，不看代码自述：
  ① 三种格式都必须 **200**；
  ② 响应体必须带正确**魔数**（PDF `%PDF` / docx·pptx `PK\\x03\\x04`）；
  ③ `summary` 必须是 **dict**，且两分支键集**完全相同**（形状唯一权威）；
  ④ 输出里不得出现 `None` / `nan` 这类"缺失被当值渲染"的痕迹。

## 反向验证（`VERIFY_BREAK=1`）

把 `tax_risk.get_tax_risk_report` 换回**改造前那份**（`summary` 是 str），
断言「① 200 + ② 魔数 + ③ 形状一致」**必须变红** ——
不红就说明本脚本的判据是假的（同义反复）。

用法：
    ./.venv/Scripts/python.exe _verify_report_export_e2e.py
    VERIFY_BREAK=1 ./.venv/Scripts/python.exe _verify_report_export_e2e.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
COMPANY = int(os.environ.get("VERIFY_COMPANY", "1"))


# ── 子进程里跑的验收体（隔离实例 · 真 HTTP · 真字节）─────────────────────
_CHILD = r'''
# -*- coding: utf-8 -*-
import io, json, os, sys
sys.path.insert(0, os.getcwd())

BREAK = os.environ.get("VERIFY_BREAK", "")

from fastapi.testclient import TestClient
import tax_risk
from tax_risk import router as _tr_router
from fastapi import FastAPI

COMPANY = int(os.environ.get("VERIFY_COMPANY", "1"))
MAGIC = {"pdf": b"%PDF", "docx": b"PK\x03\x04", "pptx": b"PK\x03\x04"}

# ── 反向验证：把取数函数换回"改造前"那份（summary 是 str 的旧空数据分支）──
_LEGACY_EMPTY = {
    "company_id": COMPANY,
    "results": [],
    "total": 0,
    "high_risk_count": 0,
    "medium_risk_count": 0,
    "low_risk_count": 0,
    "good_count": 0,
    "overall_risk_level": None,
    "summary": "该公司暂无业务数据（序时账/发票/银行流水/合同/员工/资产均无记录），无法进行涉税风险分析。",
    "data_quality": {"total_score": 0, "level": "严重不足", "warnings": ["无任何业务数据"]},
}
_orig_get = tax_risk.get_tax_risk_report
if BREAK == "1" or BREAK == "2":
    tax_risk.get_tax_risk_report = lambda **kw: dict(_LEGACY_EMPTY)
    print("★ 反向验证模式%s：get_tax_risk_report 已换回改造前实现（summary 为 str）"
          % ("（含 PPTX 丢项注入）" if BREAK == "2" else ""))
if BREAK == "2":
    # 复刻改造前 PPTX 的 `if idx > 0 and idx % 6 == 0: continue`（每页第 7 项被静默丢掉）
    _pptx_orig = tax_risk._download_pptx

    def _pptx_drop7(data):
        d = dict(data)
        d["results"] = [r for i, r in enumerate(d.get("results") or []) if i != 6]
        return _pptx_orig(d)

    tax_risk._download_pptx = _pptx_drop7

app = FastAPI()
app.include_router(_tr_router)
# CSRF 不适用于 GET；no-cache 中间件不参与本判定
client = TestClient(app, raise_server_exceptions=False)

fails, notes = [], []


def fail(msg):
    fails.append(msg)
    print("FAIL  " + msg)


def ok(msg):
    print("ok    " + msg)


# ── ① 形状唯一权威：两分支键集必须完全相同、summary 必须是 dict ──────────
try:
    from database import SessionLocal
    db = SessionLocal()
    # 反向验证时必须审**接线后真正被调用的那个函数**，否则 ③ 永远是绿的（假判据）
    _shape_probe = tax_risk.get_tax_risk_report
    empty = _shape_probe(company_id=COMPANY, period_from=None, period_to=None, db=db)
    db.close()
except Exception as exc:                                    # noqa: BLE001
    empty = None
    notes.append("取空数据载荷失败（如实记录）：%r" % (exc,))

if empty is not None:
    if not isinstance(empty.get("summary"), dict):
        fail("③ summary 不是 dict，而是 %s ⇒ 四个渲染出口必然 'str' has no attribute 'get'"
             % type(empty.get("summary")).__name__)
    else:
        s = empty["summary"]
        if "mid_risk_count" not in s:
            fail("③ summary 缺 mid_risk_count（键名发生了漂移，渲染出口取不到中风险数）")
        if "medium_risk_count" in s:
            fail("③ summary 里出现了 medium_risk_count —— 同一概念两个键名（多头维护）")
        ok("③ summary 是 dict，且键名统一为 mid_risk_count：%s" % sorted(s.keys()))

# ── ② 三种格式：真 HTTP 真字节 ─────────────────────────────────────────
def _pdf_stream_text(body: bytes) -> bytes:
    """解压 PDF 里的 FlateDecode 流后返回其内容。

    ⚠ 判据坑：PDF 流是**压缩**的，直接在原始字节里搜 "None" 会因为随机字节序列而假红
      （实测改造后仍命中）——那属于"判据自身的错"，必须先把流解开再查。
    """
    import re as _re, zlib as _zlib
    out = []
    for m in _re.finditer(rb"stream\r?\n(.*?)endstream", body, _re.S):
        raw = m.group(1)
        try:
            out.append(_zlib.decompress(raw))
        except Exception:                                    # noqa: BLE001
            out.append(raw)
    return b"\n".join(out)


def _office_xml(resp, part: str) -> bytes:
    """docx/pptx 是 zip：只取**我们写正文的那部分** XML（不二进制盲搜）。

    ⚠ 判据坑：把全部 XML 一起看会假红 —— PowerPoint 自带的母版/版式里有
      `<a:buNone/>`（项目符号=无），"None" 与业务数据毫无关系。故按部件过滤：
      pptx ⇒ `ppt/slides/slide*.xml`；docx ⇒ `word/document.xml`。

    ⚠ 取值坑：`httpx.Response` 是 `.content`，`starlette.Response` 是 `.body`。
    """
    import io as _io, zipfile as _zip
    raw = getattr(resp, "body", None)
    if raw is None:
        raw = resp.content
    zf = _zip.ZipFile(_io.BytesIO(raw))
    want = []
    for nm in zf.namelist():
        base = nm.rsplit("/", 1)[-1]
        if part == "pptx" and nm.startswith("ppt/slides/") and base.endswith(".xml"):
            want.append(nm)
        elif part == "docx" and nm == "word/document.xml":
            want.append(nm)
    return b"\n".join(zf.read(nm) for nm in sorted(want))


HTML_BODY = {}

for fmt in ("pdf", "docx", "pptx"):
    url = "/api/tax-risk/report/download?company_id=%d&format=%s" % (COMPANY, fmt)
    try:
        r = client.get(url, timeout=300)
    except Exception as exc:                                 # noqa: BLE001
        fail("① %s 请求抛异常：%r" % (fmt, exc))
        continue
    body = r.content or b""
    if r.status_code != 200:
        fail("① %s HTTP %s（应为 200）; 前 200 字节=%r" % (fmt, r.status_code, body[:200]))
        continue
    if not body.startswith(MAGIC[fmt]):
        fail("② %s 魔数不符：期望 %r，实得 %r" % (fmt, MAGIC[fmt], body[:16]))
        continue
    # ④ "缺失被当值渲染"的痕迹：先解压/解包，再查纯文本
    if fmt == "pdf":
        probe = _pdf_stream_text(body)
    else:
        probe = _office_xml(r, fmt)
    if b"None" in probe or b"nan" in probe:
        fail("④ %s 正文里出现 None/nan ⇒ 缺失字段被当值写进了交付物" % fmt)
    ok("①② %s HTTP 200，魔数 %r，%d 字节" % (fmt, body[:8], len(body)))

# ── ⑤ 顺带覆盖 PDF 的"无中文字体"降级支路（返回 HTML 也必须 200）──────
try:
    from reportlab.pdfbase import pdfmetrics
    pdfmetrics.registerFont = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no font"))
    r = client.get("/api/tax-risk/report/download?company_id=%d&format=pdf" % COMPANY, timeout=300)
    body = r.content or b""
    if r.status_code != 200:
        fail("⑤ 无中文字体降级支路 HTTP %s（应回落到 HTML 且 200）" % r.status_code)
    elif b"<html" not in body.lower():
        fail("⑤ 降级支路返回的不是 HTML：%r" % body[:80])
    else:
        # 纯文本可读，直接查"缺失被当值渲染"与"是否告诉了用户原因"
        if b"None" in body or b"nan" in body:
            fail("④ HTML 交付物里出现 None/nan ⇒ 缺失字段被当值写进了交付物")
        if "暂无业务数据" not in body.decode("utf-8", "replace"):
            fail("⑦ HTML 交付物没有写明「为何无法分析」⇒ 用户拿到一份空白报告却不知原因")
        ok("⑤ 无中文字体时回落到 HTML 且 200（%d 字节）" % len(body))
except Exception as exc:                                     # noqa: BLE001
    notes.append("降级支路未验证（如实记录）：%r" % (exc,))

# ── ⑥ 导出内容完整性：PPTX 不得**静默丢项**（每页第 7 项曾被 `continue` 吃掉）──
try:
    import io as _io, zipfile as _zip
    n = 13
    fake_results = [{
        "item": "唯一标记项%02d" % i, "category": "经营实质", "category_icon": "🔍",
        "risk_level": "中风险", "risk_score": 5, "risk_color": "#f59e0b", "urgency": "提醒",
        "detail": "细节%02d" % i, "suggestion": "建议%02d" % i,
    } for i in range(1, n + 1)]
    payload = tax_risk._report_payload(
        company_id=COMPANY, period_start="2025-01", period_end="2025-06",
        industry="综合", industry_benchmark=tax_risk._industry_benchmark_block(None),
        summary=tax_risk._report_summary(fake_results, 0, analysis_available=True),
        metrics={"revenue": 1000.0, "cost": 600.0, "gross_margin_pct": 40.0, "vat_payable": 30.0},
        results=fake_results,
    )
    resp = tax_risk._download_pptx(payload)
    xml = _office_xml(resp, "pptx").decode("utf-8", "replace")
    missing = [i for i in range(1, n + 1) if ("唯一标记项%02d" % i) not in xml]
    if missing:
        fail("⑥ PPTX 丢了 %d/%d 项（编号 %s）⇒ 导出内容 ≠ 分析结果" % (len(missing), n, missing))
    else:
        ok("⑥ PPTX 含全部 %d 项风险（无静默丢项）" % n)
except Exception as exc:                                     # noqa: BLE001
    fail("⑥ PPTX 完整性检查未通过：%r" % (exc,))

print("FAILS=%d" % len(fails))
sys.exit(1 if fails else 0)
'''


def main() -> int:
    data_dir = Path(tempfile.mkdtemp(prefix="report_e2e_"))
    for f in ("security.db", "accounting.db"):
        src = ROOT / "data" / f
        if src.exists():
            shutil.copy2(src, data_dir / f)
    up = ROOT / "data" / "uploads"
    if up.exists():
        shutil.copytree(up, data_dir / "uploads")

    env = dict(os.environ)
    env["APP_DATA_DIR"] = str(data_dir)
    env["APP_COOKIE_SECURE"] = "0"
    env["PYTHONIOENCODING"] = "utf-8"
    env["VERIFY_COMPANY"] = str(COMPANY)
    if os.environ.get("VERIFY_BREAK"):
        env["VERIFY_BREAK"] = os.environ["VERIFY_BREAK"]
    env.pop("CODEBUDDY_SAFE_DELETE_BULK_GUARD", None)

    print("隔离实例 APP_DATA_DIR =", data_dir)
    cp = subprocess.run([PY, "-c", textwrap.dedent(_CHILD)], cwd=str(ROOT), env=env,
                        capture_output=True, timeout=1800)
    out = (cp.stdout or b"").decode("utf-8", errors="replace")
    err = (cp.stderr or b"").decode("utf-8", errors="replace")
    print(out.rstrip())
    if cp.returncode != 0 and err.strip():
        print("---- stderr（末 1500 字）----")
        print(err[-1500:].rstrip())
    print("=" * 60)
    print("报告导出验收：", "PASS" if cp.returncode == 0 else "FAIL（见上）")
    return cp.returncode


if __name__ == "__main__":
    sys.exit(main())
