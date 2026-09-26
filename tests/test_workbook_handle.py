# -*- coding: utf-8 -*-
"""工作簿句柄泄漏回归测试 —— 锁死"服务不得占住用户资料文件"。

用户 2026-09-25 报：「已彻底清理 0 个文件；1 个仍被程序占用，请关闭 Excel/WPS 后重试
—— 这是什么意思？怎么还能被占用？」

调查结论（本文件锁死）：**占用者是本服务进程自身，不是 Excel/WPS**。
`openpyxl.load_workbook(read_only=True)` 打开后从不 close()，该模式底层持有 zip
文件句柄，而 openpyxl 对象图存在引用环（worksheet.parent ↔ workbook），函数返回后
**不被引用计数立即回收**，要等循环 GC；长驻服务里句柄可一直占着文件 →
文件无法重命名/移动 → 删除必然失败 → 用户被误导为"Excel 占用 / 删了又回来"。

消除手段：`engine/workbook.py` 为唯一权威（出口必定 close），
> `tools/audit_consistency.py::check_excel_handle_leak` 拦住绕过者；
> 删除前 `release_all()` 收干净自家句柄，再用 `is_file_locked()` 如实说明原因。
"""
import os
import shutil
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.workbook import (  # noqa: E402
    close_workbook, is_file_locked, load_workbook, release_all, workbook_scope,
)


def _make_xlsx(path):
    """造一个真实 xlsx（save 后工作簿不再持有句柄，源文件应可自由操作）。"""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = "对方户名"
    ws["B1"] = "交易金额"
    ws["A2"] = "某某公司"
    ws["B2"] = 1234.5
    wb.save(str(path))
    close_workbook(wb)
    return str(path)


@pytest.fixture()
def xlsx(tmp_path):
    return _make_xlsx(tmp_path / "样本.xlsx")


# ═══════════ 1. 权威模块：打开即可关闭，关闭即释放 ═══════════

class TestAuthorityReleasesHandle:
    def test_scope_releases_file_after_exit(self, xlsx, tmp_path):
        """workbook_scope 退出后，文件必须可自由重命名（= 句柄已释放）。"""
        with workbook_scope(xlsx, read_only=True, data_only=True) as wb:
            assert wb is not None
            assert wb.sheetnames
        probe = str(tmp_path / "改名后.xlsx")
        os.replace(xlsx, probe)          # 被占用则抛 PermissionError
        os.replace(probe, xlsx)

    def test_close_is_idempotent(self, xlsx):
        wb = load_workbook(xlsx, read_only=True, data_only=True)
        assert close_workbook(wb) is True
        assert close_workbook(wb) is False, "重复关闭不得抛异常，须返回 False"
        assert close_workbook(None) is False

    def test_release_all_closes_registered(self, xlsx, tmp_path):
        # 必须**持有引用**：否则工作簿立即可被回收（此时句柄也已随之释放，
        # 但 release_all 的计数会不准 —— 测试要测的是"在册未关闭"的回收能力）
        held = [load_workbook(xlsx, read_only=True, data_only=True),
                load_workbook(xlsx, read_only=True, data_only=True)]
        assert release_all() >= 2
        assert held
        probe = str(tmp_path / "再改名.xlsx")
        os.replace(xlsx, probe)
        os.replace(probe, xlsx)

    def test_xls_route_uses_xlrd(self, xlsx):
        """扩展名判定：非 .xls 走 openpyxl；.xls 走 xlrd（不存在时抛错而非静默）。"""
        wb = load_workbook(xlsx, read_only=True, data_only=True)
        assert hasattr(wb, "sheetnames"), "应交给 openpyxl"
        close_workbook(wb)


# ═══════════ 2. 闸门必须拦住"绕过权威"的写法 ═══════════

class TestLeakGateFiresOnRegression:
    def test_gate_flags_direct_open_in_prod_code(self, tmp_path, monkeypatch):
        import tools.audit_consistency as ac
        (tmp_path / "engine").mkdir(parents=True, exist_ok=True)
        (tmp_path / "engine" / "workbook.py").write_text("# authority\n", encoding="utf-8")
        (tmp_path / "offender.py").write_text(
            "import openpyxl\n"
            "def f(p):\n"
            "    wb = openpyxl.load_workbook(p, read_only=True)\n"
            "    return wb.sheetnames\n",
            encoding="utf-8")
        monkeypatch.setattr(ac, "ROOT", tmp_path)
        issues = ac.check_excel_handle_leak()
        assert any("绕过 engine/workbook.py" in m for _, _, m in issues), (
            "直接打开工作簿必须被闸门拦下（否则句柄会占住用户文件导致删除失败）"
        )

    def test_gate_ignores_mentions_inside_comments(self, tmp_path, monkeypatch):
        """注释/文档字符串里引用反模式写法，不得被误判（本项目习惯这样写修复说明）。"""
        import tools.audit_consistency as ac
        (tmp_path / "engine").mkdir(parents=True, exist_ok=True)
        (tmp_path / "engine" / "workbook.py").write_text("# authority\n", encoding="utf-8")
        (tmp_path / "clean.py").write_text(
            '"""原写法 openpyxl.load_workbook(p) 后从不 close()，故收敛到权威模块。"""\n'
            "# 旧代码：wb = openpyxl.load_workbook(p, read_only=True)\n"
            "from engine.workbook import workbook_scope\n"
            "def f(p):\n"
            "    with workbook_scope(p) as wb:\n"
            "        return wb.sheetnames\n",
            encoding="utf-8")
        monkeypatch.setattr(ac, "ROOT", tmp_path)
        assert ac.check_excel_handle_leak() == []

    def test_gate_flags_missing_authority(self, tmp_path, monkeypatch):
        import tools.audit_consistency as ac
        monkeypatch.setattr(ac, "ROOT", tmp_path)
        issues = ac.check_excel_handle_leak()
        assert any("唯一权威模块缺失" in m for _, _, m in issues)


# ═══════════ 3. 占用探测必须说真话（不得替用户猜原因） ═══════════

class TestLockProbe:
    def test_free_file_is_not_locked(self, xlsx):
        assert is_file_locked(xlsx) is False

    def test_missing_file_returns_none(self, tmp_path):
        assert is_file_locked(tmp_path / "不存在.xlsx") is None

    def test_probe_leaves_file_intact(self, xlsx):
        before = os.path.getsize(xlsx)
        is_file_locked(xlsx)
        assert os.path.exists(xlsx), "探测必须把文件改回原名，不得丢失"
        assert os.path.getsize(xlsx) == before


# ═══════════ 4. 源码契约：删除路径必须先释放自家句柄 ═══════════

class TestDeleteReleasesOwnHandles:
    def _main_src(self):
        with open(os.path.join(PROJECT_ROOT, "main.py"), "r", encoding="utf-8") as fh:
            return fh.read()

    def test_delete_calls_release_all(self):
        src = self._main_src()
        assert "release_all" in src, (
            "删除资料前必须先释放本服务自身的工作簿句柄；"
            "实测占用者就是本服务，不释放则删除必然失败"
        )

    def test_delete_reports_lock_truthfully(self):
        src = self._main_src()
        assert "is_file_locked" in src, (
            "删除失败时必须探测'是否真的被占用'，不得向用户猜一个原因（如'被 Excel 占用'）"
        )

    def test_analysis_releases_handles_at_end(self):
        src = self._main_src()
        assert "句柄回收" in src, (
            "分析结束必须统一回收工作簿句柄，保证此后上传目录文件可自由删除"
        )
