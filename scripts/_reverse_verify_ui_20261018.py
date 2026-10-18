# -*- coding: utf-8 -*-
"""五项界面改造的**反向验证**：把关键点逐个改坏，验收脚本必须变红。

★ 为什么必须做：38 项判据若恒真（假绿）等于没测。每个注入都对应一条**真实会发生的
  退化路径**（按钮不受控、hidden 又被 flex 覆盖、层名退回英文、候选处置不认、解析页复活）。

用法：`./.venv/Scripts/python.exe scripts/_reverse_verify_ui_20261018.py --base http://127.0.0.1:8006`
前提：目标实例已起、账号可登录（脚本会自己登录并跑 `_verify_ui_20261018.py` 的全部判据）。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
VERIFY = os.path.join(ROOT, "scripts", "_verify_ui_20261018.py")

FILES = {
    "projects_html": os.path.join(ROOT, "static", "projects.html"),
    "projects_js": os.path.join(ROOT, "static", "js", "projects.js"),
    "documents_html": os.path.join(ROOT, "static", "documents.html"),
    "documents_js": os.path.join(ROOT, "static", "js", "documents.js"),
    "analysis_html": os.path.join(ROOT, "static", "analysis.html"),
    "analysis_js": os.path.join(ROOT, "static", "js", "analysis.js"),
    "rules_html": os.path.join(ROOT, "static", "rules.html"),
    "rules_js": os.path.join(ROOT, "static", "js", "rules.js"),
    "index_html": os.path.join(ROOT, "static", "index.html"),
}


def _bump(path: str) -> None:
    st = os.stat(path)
    os.utime(path, (st.st_atime + 120, st.st_mtime + 120))


def _patch(path: str, old: str, new: str) -> None:
    txt = open(path, encoding="utf-8").read()
    assert old in txt, "注入锚点不存在：%r（%s）" % (old[:60], os.path.basename(path))
    open(path, "w", encoding="utf-8", newline="").write(txt.replace(old, new, 1))
    _bump(path)


# ── ① 项目列表：按钮不再随勾选显隐 ──
def inj_btn_always_hidden() -> None:
    _patch(FILES["projects_js"], "      btn.hidden = n === 0;", "      btn.hidden = true;")


# ── ② hidden 又被 flex 覆盖（把刚修的那条 CSS 去掉）──
def inj_hidden_css_removed() -> None:
    _patch(FILES["projects_html"], "    [hidden] { display: none !important; }", "")


# ── ③ 资料页「项目管理」按钮复活 ──
def inj_doc_project_link() -> None:
    _patch(FILES["documents_html"], '<h1>📎 资料上传与管理</h1>',
           '<h1>📎 资料上传与管理</h1>\n    <a href="/projects">项目管理</a>')


# ── ④ 上传不再自动解析（回到"要另点开始解析"）──
def inj_no_autoparse() -> None:
    _patch(FILES["documents_js"], "        var px = await autoParse(up.id);",
           '        var px = {ok: false, reason: "需手动解析"};')


# ── ⑤ 解析页入口复活（侧边栏）──
def inj_nav_extract_back() -> None:
    _patch(FILES["index_html"],
           """    <div class="nav-item" onclick="location.href='/documents'" title=""",
           """    <div class="nav-item" onclick="location.href='/extract'"><span class="icon">🧩</span> 资料解析与校正</div>
    <div class="nav-item" onclick="location.href='/documents'" title=""")


# ── ⑥ 分析页「查看」不再给可见反馈（回到"点了没反应"）──
def inj_no_reveal() -> None:
    _patch(FILES["analysis_js"], "    revealCurrent(jobId);\n  } catch (e) {",
           "  } catch (e) {")


# ── ⑦ 规则层名退回英文原值 ──
def inj_layer_english() -> None:
    _patch(FILES["rules_js"], "esc(x.layer_cn || x.layer)", "esc(x.layer)")


# ── ⑧ 候选处置列不再给出结论 ──
def inj_disp_removed() -> None:
    _patch(FILES["rules_js"], "          + '<td>' + dispCell(x) + '</td>'",
           "          + '<td>—</td>'")


CASES = [
    ("① 删除选中按钮恒隐藏", inj_btn_always_hidden),
    ("② hidden 被 flex 覆盖（CSS 被删）", inj_hidden_css_removed),
    ("③ 资料页「项目管理」按钮复活", inj_doc_project_link),
    ("④ 上传不再自动解析", inj_no_autoparse),
    ("⑤ 侧边栏「资料解析与校正」复活", inj_nav_extract_back),
    ("⑥ 「查看」不再滚动/高亮", inj_no_reveal),
    ("⑦ 规则层名退回英文", inj_layer_english),
    ("⑧ 候选处置列无结论", inj_disp_removed),
]


def _run(base: str, user: str, password: str):
    p = subprocess.run([PY, VERIFY, "--base", base, "--user", user,
                        "--password", password],
                       cwd=ROOT, capture_output=True, text=True, timeout=900)
    out = (p.stdout or "") + (p.stderr or "")
    tail = ""
    for ln in out.splitlines():
        if "汇总：" in ln:
            tail = ln.strip()
    return p.returncode, tail, out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8006")
    ap.add_argument("--user", default="uiuser")
    ap.add_argument("--password", default="Ui-Test-2026!")
    args = ap.parse_args()

    base_rc, base_tail, base_out = _run(args.base, args.user, args.password)
    print("基线：rc=%d %s" % (base_rc, base_tail))
    if base_rc != 0:
        print("✗ 基线未绿，反向验证无意义：\n%s" % base_out[-1500:])
        return 2

    results = []
    for name, fn in CASES:
        baks = {}
        for k, path in FILES.items():
            b = path + ".bak"
            shutil.copy2(path, b)
            baks[path] = b
        try:
            fn()
            # 静态资源有 ?v= 内容哈希 ⇒ 改完必须同步，否则浏览器仍拿旧文件（等于没注入）
            subprocess.run([PY, os.path.join(ROOT, "tools", "sync_asset_versions.py")],
                           cwd=ROOT, capture_output=True, text=True)
            rc, tail, _out = _run(args.base, args.user, args.password)
            results.append({"case": name, "turned_red": rc != 0, "detail": tail})
            print("%s %s → %s" % ("✓" if rc != 0 else "✗", name, tail))
        finally:
            for path, b in baks.items():
                shutil.move(b, path)
                _bump(path)
            subprocess.run([PY, os.path.join(ROOT, "tools", "sync_asset_versions.py")],
                           cwd=ROOT, capture_output=True, text=True)

    after_rc, after_tail, _o = _run(args.base, args.user, args.password)
    print("还原后：rc=%d %s" % (after_rc, after_tail))
    ok = all(r["turned_red"] for r in results) and after_rc == 0
    print("\n===== 结论 =====")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print("反向验证 %d/%d 触发红灯；还原后 %s"
          % (sum(1 for r in results if r["turned_red"]), len(results),
             "绿" if after_rc == 0 else "仍红（异常）"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
