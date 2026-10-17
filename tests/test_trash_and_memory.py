# -*- coding: utf-8 -*-
"""回收站接口（H-04）与记忆脚本（H-01）守护测试。

判据重点在**安全边界**（这些都是"能删/能搬文件"的入口）：
  ① 还原的文件名不得逃出回收站（`../` 之类必须被剥掉）；
  ② 还原目标必须在 `DATA_DIR` 内（2026-10-17 事故后的统一要求）；
  ③ 清空必须显式 `confirm`，且单批上限硬编码 20（超了也不给）。
"""
from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import trash_api as T          # noqa: E402
from engine import trash_service as SVC   # noqa: E402


def test_company_prefix_parsing() -> None:
    """文件名首段是账套 id ⇒ 能推断还原目录；推不出就是 None（不瞎猜）。"""
    assert SVC.company_of("1_100_AI账务系统银行10.xlsx") == 1
    assert SVC.company_of("102_账套_报表.pdf") == 102
    assert SVC.company_of("company_1_full.json") is None      # 下划线前不是纯数字
    assert SVC.company_of("") is None
    assert SVC.company_of("1234567890123_x.bin") is None      # 超长数字不当作 id


def test_inside_guard_rejects_outside_paths(tmp_path, monkeypatch) -> None:
    """★ 写操作护栏：`DATA_DIR` 之外的目标必须被拒绝。"""
    monkeypatch.setattr(SVC, "DATA_DIR", tmp_path / "data")
    (tmp_path / "data").mkdir()
    ok = SVC.assert_inside(tmp_path / "data" / "uploads" / "1")
    assert ok == (tmp_path / "data" / "uploads" / "1").resolve()
    with pytest.raises(Exception):
        SVC.assert_inside(ROOT / "data" / "uploads" / "1")


def test_restore_name_strips_traversal() -> None:
    """还原只按**文件名**处理：传 `../../evil.db` 不会被当成路径。"""
    assert SVC._safe_name("../../evil.db") == "evil.db", "未取 basename"
    import pytest as _pytest
    with _pytest.raises(SVC.TrashError):
        SVC._safe_name("..")


def test_empty_requires_confirm() -> None:
    """清空必须确认（默认 false ⇒ 409）。"""
    assert T.EmptyIn().confirm is False


def test_page_memory_script_covers_selects_and_skips_secrets() -> None:
    """H-01 记忆脚本：必须接管 select，且**跳过密码/文件**字段。"""
    src = (ROOT / "static" / "js" / "page-memory.js").read_text(encoding="utf-8")
    assert "querySelectorAll('select[id]" in src, "未接管 select"
    assert "password" in src and "file" in src, "未排除密码/文件字段"
    assert "localStorage" in src, "未持久化"
    assert "try {" in src and "catch" in src, "存储不可用时未静默降级"


def test_page_memory_injected_into_pages() -> None:
    """所有业务页面都应引入记忆脚本（否则"改了等于没改"）。"""
    # 与注入器 `scripts/_inject_page_memory.py` 的 SKIP 保持一致：
    # 登录/告知是一次性表单，不参与"记住上次选择"。
    skip = {"login.html", "consent.html"}
    pages = sorted(p.name for p in (ROOT / "static").glob("*.html") if p.name not in skip)
    missing = [n for n in pages
               if "page-memory.js" not in (ROOT / "static" / n).read_text(encoding="utf-8")]
    assert not missing, "以下页面未引入 page-memory.js：%s" % missing


def test_recycle_and_backup_pages_are_admin_gated() -> None:
    """回收站/备份页的清空、备份按钮必须管理员门控（服务端仍是最终拦截）。"""
    for page, btn in (("recycle.html", "btn-empty"), ("backup.html", "btn-create")):
        html = (ROOT / "static" / page).read_text(encoding="utf-8")
        i = html.index('id="%s"' % btn)
        seg = html[max(0, i - 120):i + 160]
        assert 'data-perm-admin="1"' in seg, "%s 的 %s 未加管理员门控" % (page, btn)
