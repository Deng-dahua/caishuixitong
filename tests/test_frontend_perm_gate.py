# -*- coding: utf-8 -*-
"""前端权限门控 —— 全站覆盖 + 漂移闸门（P0-8 扩展轮，2026-10-17）。

背景：
  · `static/js/rbac-nav.js` 是前端门控的**唯一机制**（消费 `/api/auth/me` 下发的
    `permissions` / `is_admin`，**不推断角色**）；
  · `config/frontend_perms.json` 是「**哪个页面的哪个入口需要哪个权限**」的**唯一权威表**；
  · 此前全站只有 5/25 个页面接入（`index/roles/users/audit_logs/reports`），
    其余页面的写入口对无权限角色**可见可点**、点击才被服务端 403。

本文件是**覆盖率 + 漂移**闸门（静态判定）。真浏览器实测见
`scripts/_verify_frontend_perm_gate.js`。

★ 判据口径：`REQUIRED_GATES` 是**表**；下面逐条断言 HTML/JS 与表一致。
  表里新增一行而代码没跟上 ⇒ 变红（防"表建了没落地"）。
  代码里新增写入口而表没跟上 ⇒ 由 `test_no_ungated_write_entry` 尽力发现。
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "frontend_perms.json"
RBAC_JS = ROOT / "static" / "js" / "rbac-nav.js"


def _cfg() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _html(page: str) -> str:
    return (ROOT / "static" / page).read_text(encoding="utf-8")


# ── ① 机制本体 ───────────────────────────────────────────────────────────────
def test_mechanism_exists_and_reads_server_truth() -> None:
    """门控脚本必须存在，且只消费服务端下发的 permissions / is_admin。"""
    assert RBAC_JS.exists(), "static/js/rbac-nav.js 不存在"
    src = RBAC_JS.read_text(encoding="utf-8")
    assert "permissions" in src and "is_admin" in src, "rbac-nav.js 未消费服务端权限/管理员标识"
    assert "data-perm" in src and "data-perm-admin" in src, "rbac-nav.js 缺 data-perm / data-perm-admin"
    # 不得在前端硬编码角色码来判断权限（那会形成第二权威）
    for code in ("'admin'", '"admin"', "system_admin", "enterprise_finance", "review_expert"):
        assert code not in src, "rbac-nav.js 出现硬编码角色字面量 %s ⇒ 变成第二权威" % code


# ── ② 表 ↔ HTML 漂移 ─────────────────────────────────────────────────────────
def test_every_mapped_page_includes_rbac_nav() -> None:
    """表中每个页面都必须引入门控脚本（带 `?v=` 内容哈希）。"""
    missing = []
    for page in _cfg()["pages"]:
        html = _html(page)
        if not re.search(r"/static/js/rbac-nav\.js\?v=[0-9a-f]{10}", html):
            missing.append(page)
    assert not missing, "以下页面缺 rbac-nav.js 引用（或未带 ?v=）: %s" % missing


@pytest.mark.parametrize("page", sorted(_cfg()["pages"].keys()))
def test_mapped_entries_carry_attributes(page: str) -> None:
    """表中每个入口的 HTML 元素必须携带对应的 `data-perm` / `data-perm-admin`。"""
    html = _html(page)
    bad = []
    for entry in _cfg()["pages"][page]:
        m = re.search(r"<[^<>]*\bid=\"%s\"[^<>]*>" % re.escape(entry["id"]), html)
        if not m:
            bad.append("#%s 元素不存在" % entry["id"])
            continue
        tag = m.group(0)
        if entry.get("admin"):
            if 'data-perm-admin="1"' not in tag:
                bad.append("#%s 缺 data-perm-admin" % entry["id"])
        else:
            if 'data-perm="%s"' % entry["perm"] not in tag:
                bad.append("#%s 缺 data-perm=%s" % (entry["id"], entry["perm"]))
    assert not bad, "%s: %s" % (page, "；".join(bad))


def test_perm_codes_are_registered() -> None:
    """表中用到的权限点必须都在 `config/rbac.json`（不新增权限点、不扩模型）。"""
    codes = {
        p["code"]
        for p in json.loads((ROOT / "config" / "rbac.json").read_text(encoding="utf-8"))["permissions"]
    }
    used = set()
    for entries in _cfg()["pages"].values():
        for e in entries:
            if e.get("perm"):
                used.add(e["perm"])
    unknown = sorted(used - codes)
    assert not unknown, "表中出现 rbac.json 之外的权限点: %s" % unknown


# ── ③ 动态渲染的写入口 ────────────────────────────────────────────────────────
def test_dynamic_entries_carry_perm_and_reapply() -> None:
    """JS 动态渲染的写入口必须自带 `data-perm`，且渲染后调用 `RBAC.reapply()`。"""
    cfg = _cfg()["dynamic_entries"]
    for js, entries in cfg.items():
        if js == "note":
            continue
        src = (ROOT / js).read_text(encoding="utf-8")
        for e in entries:
            marker = e["marker"].replace('\\"', '"')
            assert marker in src, "%s: 未找到标记 %s（动态入口可能被改名/删除）" % (js, marker)
        assert "RBAC.reapply" in src, "%s: 渲染后未调用 RBAC.reapply() ⇒ 动态节点不受门控" % js


# ── ④ 未登记页面不得有「明显的写入口」 ────────────────────────────────────────
#: 允许"有写入口但暂不门控"的例外（须写明理由）。当前为空。
WRITE_ENTRY_EXEMPT: dict = {}

#: 写操作动词（保守词表：宁可漏报，也不误报）
_WRITE_WORDS = "保存|删除|提交|发布|回滚|新建|上传|开始解析|一键重析|重试|取消|复核|整改|创建|恢复|禁用|启用"


def _action_texts(html: str):
    """只取**可点击控件**（`<button>` / `<a>`）的可见文字。

    ★ 不能全文搜动词：正文里的"官方**发布**"、"**发布**日期"会被误判为写入口
      （第一版就是这么误报 `legal_materials.html` 的）。
    """
    out = []
    for m in re.finditer(r"<(button|a)\b[^<>]*>(.*?)</\1>", html, re.S | re.I):
        txt = re.sub(r"<[^>]+>", "", m.group(2))
        txt = re.sub(r"\s+", " ", txt).strip()
        if txt:
            out.append(txt)
    return out


def _write_hits(html: str):
    pat = re.compile(_WRITE_WORDS)
    return sorted({w for t in _action_texts(html) for w in pat.findall(t)})


def test_no_ungated_write_entry() -> None:
    """**漏配检测**：未被表登记、也不在只读/免门控清单里的页面，不得出现写操作按钮。

    目的是让"新增了写页面却忘了登记"能被发现。
    """
    cfg = _cfg()
    known = set(cfg["pages"]) | set(cfg["read_only_pages"]) | set(cfg["no_gate_reason"])
    suspects = {}
    for page in sorted(p.name for p in (ROOT / "static").glob("*.html")):
        if page in known:
            continue
        hits = _write_hits(_html(page))
        if hits:
            suspects[page] = hits
    assert not suspects, (
        "以下页面有看似写操作的入口，却既未登记门控、也不在只读/免门控清单中"
        "（请登记到 config/frontend_perms.json）: %s" % suspects
    )


def test_read_only_pages_have_no_write_entry() -> None:
    """被标为**只读**的页面，确实不该出现写操作控件（防止标注与事实脱节）。"""
    bad = {}
    for page, why in _cfg()["read_only_pages"].items():
        hits = _write_hits(_html(page))
        if hits:
            bad[page] = {"what": why, "hits": hits}
    assert not bad, "标为只读的页面出现了写操作入口（标注失真或漏配门控）: %s" % bad


# ── ⑤ 反向验证 ───────────────────────────────────────────────────────────────
def test_reverse_removing_attribute_is_detected() -> None:
    """注入：摘掉某入口的 `data-perm` ⇒ ② 的判据必须报错（否则判据是同义反复）。"""
    html = _html("documents.html")
    m = re.search(r"<[^<>]*\bid=\"btn-del-selected\"[^<>]*>", html)
    assert m, "反向验证前提失效：documents.html 未找到 #btn-del-selected"
    tag = m.group(0)
    assert 'data-perm="document.write"' in tag, "反向验证前提失效：该标签本就未挂属性"
    # 从**实际标签**里摘掉属性（不硬编码属性顺序 —— 第一版硬编码过，导致锚点失配）
    broken_tag = re.sub(r'\s+data-perm="document\.write"', "", tag, count=1)
    assert broken_tag != tag, "摘除动作未生效（锚点问题）"
    broken = html[:m.start()] + broken_tag + html[m.end():]
    m2 = re.search(r"<[^<>]*\bid=\"btn-del-selected\"[^<>]*>", broken)
    assert m2 and 'data-perm="document.write"' not in m2.group(0), (
        "反向验证失败：摘掉属性后判据仍认为已挂载 ⇒ 判据是同义反复"
    )


def test_reverse_write_word_list_catches_control_only() -> None:
    """反向验证：正文里的动词**不应**被判为写入口（判据只在控件内匹配）。"""
    # 正文（非控件）里的"发布" ⇒ 不应命中
    assert _write_hits("<h3>材料来自官方发布</h3><th>发布日期</th>") == []
    # 控件里的"发布" ⇒ 必须命中
    assert _write_hits('<button id="x">发布新版本</button>') == ["发布"]


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
