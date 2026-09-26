"""删除语义回归测试 —— 锁死"删除必须是可验证的真实删除"。

背景（用户 2026-09-25 反馈）：
  「删除选中资料，删除得不够彻底，怎么感觉还是有选中的资料没删除。
    删除报告，还是感觉没有删除，感觉后台还有备份一样的。
    再重新生成报告时，感觉都是旧报告。」

调查结论 —— 三个抱怨来自同一批 fail-open 缺陷：
  ① 服务端 delete_tax_risk_doc 丢弃 move_to_trash 的 bool 返回值，
     无条件把 removed_file 置 True → 文件被 Excel/WPS 占用时仍回"删除成功"；
  ② 前端逐条 DELETE 只 try/catch 网络异常，fetch 对 4xx/5xx 不 reject，
     失败也计入"已删除"，toast 谎报；
  ③ 内存列表删了、磁盘文件还在，服务器重启后扫描磁盘会把资料重新扫回列表
     （表现为"删了又回来"）；
  ④ 删除报告只清 last_analysis_cache 一处，另有 5 处副本（已完成任务结果、
     分析历史、检查点、中转站明细、磁盘缓存）留存 → "感觉后台还有备份"；
  ⑤ 删除报告的磁盘写回没有回读校验，写失败时 key 仍在，重启即"复活"。

本测试锁死修复后的契约：
  - purge_file 返回 (bool, reason)，绝不谎报；
  - 物理删除失败必须登记墓碑，墓碑使文件永久排除出列表与扫描；
  - 报告删除返回结构化 cleared/leftovers，ok 仅在无残留时为真；
  - 一键分析 force=1 必须绕过增量复用。
"""
import json
import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import runtime_storage as rs  # noqa: E402


# ═══════════════ 1. purge_file：真实移除 + 如实报告 ═══════════════

class TestPurgeFileTruthfulness:
    def test_missing_file_is_success(self, tmp_path):
        removed, reason = rs.purge_file(tmp_path / "不存在.xlsx")
        assert removed is True
        assert "不存在" in reason

    def test_directory_is_refused(self, tmp_path):
        d = tmp_path / "adir"
        d.mkdir()
        removed, reason = rs.purge_file(d)
        assert removed is False, "目录不得被当作文件删除"
        assert reason

    def test_real_file_removed_from_source(self, tmp_path):
        f = tmp_path / "1_9_x.xlsx"
        f.write_text("data", encoding="utf-8")
        removed, reason = rs.purge_file(f)
        assert removed is True
        assert not f.exists(), "物理删除必须真正移除源文件"
        assert reason

    def test_failure_reports_reason_not_success(self, tmp_path, monkeypatch):
        """move_to_trash 失败且唯一名兜底也失败时，必须返回 False + 原因。"""
        f = tmp_path / "locked.xlsx"
        f.write_text("data", encoding="utf-8")
        monkeypatch.setattr(rs, "move_to_trash", lambda _p: False)
        monkeypatch.setattr(rs.os, "replace", lambda *a, **k: (_ for _ in ()).throw(PermissionError("被占用")))
        removed, reason = rs.purge_file(f)
        assert removed is False, "物理删除失败时不得返回成功"
        assert "PermissionError" in reason
        assert f.exists(), "删除失败不得销毁原文件"


# ═══════════════ 2. 墓碑：删除失败也不得复活 ═══════════════

class TestDocTombstone:
    def test_add_and_load(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rs, "DELETED_DOCS", tmp_path / "deleted_docs.json")
        rs.add_doc_tombstone(1, "1_7_a.xlsx", "/tmp/1_7_a.xlsx", "被占用", purged=False)
        tombstones = rs.load_doc_tombstones()
        key = rs.doc_tombstone_key(1, "1_7_a.xlsx")
        assert key in tombstones
        assert tombstones[key]["purged"] is False
        assert tombstones[key]["company_id"] == 1
        assert tombstones[key]["filename"] == "1_7_a.xlsx"

    def test_key_is_company_scoped(self):
        assert rs.doc_tombstone_key(1, "x") != rs.doc_tombstone_key(2, "x")

    def test_clear(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rs, "DELETED_DOCS", tmp_path / "deleted_docs.json")
        rs.add_doc_tombstone(3, "3_5_b.pdf", purged=True)
        rs.clear_doc_tombstone(3, "3_5_b.pdf")
        assert rs.doc_tombstone_key(3, "3_5_b.pdf") not in rs.load_doc_tombstones()

    def test_idempotent_add(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rs, "DELETED_DOCS", tmp_path / "deleted_docs.json")
        rs.add_doc_tombstone(1, "n.xlsx", purged=False, reason="第一次")
        rs.add_doc_tombstone(1, "n.xlsx", purged=True, reason="第二次")
        tombstones = rs.load_doc_tombstones()
        assert len(tombstones) == 1
        assert tombstones[rs.doc_tombstone_key(1, "n.xlsx")]["purged"] is True


# ═══════════════ 3. 源码级契约：不得回归 fail-open ═══════════════

def _read_main():
    with open(os.path.join(PROJECT_ROOT, "main.py"), "r", encoding="utf-8") as fh:
        return fh.read()


def _read_js():
    with open(os.path.join(PROJECT_ROOT, "static", "js", "tax-doc-analysis.js"),
              "r", encoding="utf-8") as fh:
        return fh.read()


class TestNoFailOpenRegression:
    def test_no_unconditional_removed_file_true(self):
        """删除路径不得再出现无条件 removed_file = True 这类谎报。"""
        src = _read_main()
        assert "removed_file = True" not in src, (
            "delete_tax_risk_doc 不得丢弃 move_to_trash 返回值后无条件宣告删除成功"
        )

    def test_doc_delete_uses_purge_file(self):
        src = _read_main()
        assert "purge_file(fpath)" in src, "资料删除必须经 purge_file 走可验证的真实移除"
        assert "add_doc_tombstone(company_id, fname" in src, "物理删除失败必须登记墓碑"

    def test_scan_skips_tombstoned_files(self):
        """启动扫描必须跳过墓碑，否则重启后已删资料会复活。"""
        src = _read_main()
        assert "load_doc_tombstones()" in src
        assert "doc_tombstone_key(company_id, fname_clean) in tombstones" in src

    def test_report_delete_clears_all_copies(self):
        src = _read_main()
        for marker in ("内存分析缓存", "磁盘分析缓存", "分析任务结果",
                       "分析历史", "分析检查点", "中转站解析缓存"):
            assert marker in src, f"删除报告必须同时清理：{marker}"
        assert "leftovers" in src, "删除报告必须返回残留清单，不得只会说'已删除'"

    def test_report_delete_verifies_disk_write(self):
        src = _read_main()
        assert "verify = read_json(LAST_ANALYSIS_CACHE, {})" in src, (
            "磁盘缓存删除后必须回读校验，否则写入失败时报告会在重启后复活"
        )

    def test_frontend_checks_http_status(self):
        js = _read_js()
        assert "if (!resp.ok) { throw new Error" in js, (
            "前端必须检查 HTTP 状态码；fetch 对 4xx/5xx 不会 reject"
        )

    def test_frontend_batch_delete_single_request(self):
        js = _read_js()
        assert "/api/tax-risk-docs/batch-delete" in js, "批量删除必须走服务端批量接口"
        assert "'/api/tax-risk-docs/' + batch[j]" not in js, (
            "前端不得再逐条 DELETE（失败会被静默计为成功）"
        )

    def test_frontend_delete_report_no_fake_success(self):
        js = _read_js()
        assert "toast('报告已删除', 'success')" not in js, (
            "删除报告的网络异常分支不得再谎报成功"
        )

    def test_analyze_force_supported(self):
        src = _read_main()
        assert "if not force:" in src, "增量复用必须可被 force=1 绕过"
        assert "&force=1" in _read_js(), "前端必须能发起强制重算"

    def test_report_carries_freshness(self):
        src = _read_main()
        assert 'report_data["_freshness"]' in src, (
            "报告必须携带计算时间/数据指纹，用户才能自证拿到的是新结果"
        )
        js = _read_js()
        assert "function _freshnessStrip" in js, "前端必须展示结果新鲜度"


# ═══════════════ 4. 行为级：删除资料核心函数的真实语义 ═══════════════

class TestDeleteCoreBehaviour:
    """直接驱动 main._delete_tax_risk_docs，验证三条契约：
       ① 真实移除成功 → disk_removed 计数；② 移除失败 → 墓碑 + failures；
       ③ 同 id 多版本一次全清（旧实现只 pop 第一条）。"""

    @pytest.fixture()
    def app_ctx(self, tmp_path, monkeypatch):
        monkeypatch.setenv("APP_DATA_DIR", str(tmp_path))
        # 数据目录必须在导入 runtime_storage 前生效，故用子进程隔离不可行时
        # 直接对已导入模块打补丁（模块变量在导入期已解析，故逐个替换）
        import importlib
        import runtime_storage
        importlib.reload(runtime_storage)
        # 重新加载 main 代价过高，改为对 main 模块注入替身
        import main as main_mod
        monkeypatch.setattr(main_mod, "TRANSFER_DIR", str(tmp_path / "transfer"))
        os.makedirs(str(tmp_path / "transfer"), exist_ok=True)
        monkeypatch.setattr(main_mod, "purge_file", runtime_storage.purge_file)
        monkeypatch.setattr(main_mod, "add_doc_tombstone", runtime_storage.add_doc_tombstone)
        monkeypatch.setattr(runtime_storage, "TRASH_DIR", tmp_path / "trash")
        monkeypatch.setattr(runtime_storage, "DELETED_DOCS", tmp_path / "deleted_docs.json")
        return main_mod

    def test_real_delete_removes_file(self, app_ctx, tmp_path):
        f = tmp_path / "1_11_a.xlsx"
        f.write_text("x", encoding="utf-8")
        app_ctx._tax_risk_docs.append({
            "id": 11, "filename": f.name, "original_name": "a.xlsx",
            "path": str(f), "size": 1, "uploaded_at": "", "company_id": 1,
        })
        res = app_ctx._delete_tax_risk_docs([11], 1)
        assert res["removed"] == 1
        assert res["disk_removed"] == 1
        assert res["left_on_disk"] == 0
        assert res["failures"] == []
        assert not f.exists()

    def test_locked_file_is_tombstoned_and_reported(self, app_ctx, tmp_path, monkeypatch):
        f = tmp_path / "1_12_b.xlsx"
        f.write_text("x", encoding="utf-8")
        app_ctx._tax_risk_docs.append({
            "id": 12, "filename": f.name, "original_name": "b.xlsx",
            "path": str(f), "size": 1, "uploaded_at": "", "company_id": 1,
        })
        monkeypatch.setattr(app_ctx, "purge_file", lambda _p: (False, "PermissionError: 被占用"))
        res = app_ctx._delete_tax_risk_docs([12], 1)
        assert res["removed"] == 1, "即使物理删除失败，也必须从待分析列表移除"
        assert res["left_on_disk"] == 1
        assert res["tombstoned"] == 1
        assert res["failures"] and res["failures"][0]["reason"]
        tombstones = rs.load_doc_tombstones()
        assert rs.doc_tombstone_key(1, f.name) in tombstones
        assert tombstones[rs.doc_tombstone_key(1, f.name)]["purged"] is False

    def test_same_id_multiple_versions_all_removed(self, app_ctx, tmp_path):
        paths = []
        for i in range(2):
            f = tmp_path / f"1_13_v{i}.xlsx"
            f.write_text("x", encoding="utf-8")
            paths.append(f)
            app_ctx._tax_risk_docs.append({
                "id": 13, "filename": f.name, "original_name": f"v{i}.xlsx",
                "path": str(f), "size": 1, "uploaded_at": "", "company_id": 1,
            })
        res = app_ctx._delete_tax_risk_docs([13], 1)
        assert res["removed"] == 2, "同一 doc_id 的多版本必须一次全清（旧实现只删第一条）"
        assert all(not p.exists() for p in paths)
        assert not [d for d in app_ctx._tax_risk_docs if d["id"] == 13]

    def test_company_isolation(self, app_ctx, tmp_path):
        f = tmp_path / "2_14_c.xlsx"
        f.write_text("x", encoding="utf-8")
        app_ctx._tax_risk_docs.append({
            "id": 14, "filename": f.name, "original_name": "c.xlsx",
            "path": str(f), "size": 1, "uploaded_at": "", "company_id": 2,
        })
        res = app_ctx._delete_tax_risk_docs([14], 1)
        assert res["removed"] == 0, "不得跨账套删除"
        assert f.exists()


# ═══════════════ 5. 反向验证：闸门必须真的拦得住回归 ═══════════════

class TestDeleteGateFiresOnRegression:
    """闸门本身也要被验证：若改回旧的 fail-open 写法，check_delete_semantics
    必须报 ERROR。否则"闸门存在"只是自我安慰（本项目历史教训：闸门扫不到的
    代码 = 没有闸门）。"""

    def _gated_issues(self, tmp_path, monkeypatch, main_src, js_src):
        import tools.audit_consistency as ac
        (tmp_path / "static" / "js").mkdir(parents=True, exist_ok=True)
        (tmp_path / "main.py").write_text(main_src, encoding="utf-8")
        (tmp_path / "static" / "js" / "tax-doc-analysis.js").write_text(js_src, encoding="utf-8")
        monkeypatch.setattr(ac, "ROOT", tmp_path)
        return ac.check_delete_semantics()

    def test_clean_source_passes(self, tmp_path, monkeypatch):
        good = (
            "purge_file(fpath)\n"
            "add_doc_tombstone(company_id, fname, fpath, reason, purged=True)\n"
            "load_doc_tombstones()\n"
            "分析任务结果 分析历史 分析检查点 中转站解析缓存\n"
            "leftovers = []\n"
            "verify = read_json(LAST_ANALYSIS_CACHE, {})\n"
            "if not force:\n"
            'report_data["_freshness"] = {}\n'
            "release_all()\n"
            "is_file_locked(fpath)\n"
        )
        js = ("if (!resp.ok) { throw new Error('x'); }\n"
              "/api/tax-risk-docs/batch-delete\n")
        assert self._gated_issues(tmp_path, monkeypatch, good, js) == []

    def test_fail_open_success_flag_is_caught(self, tmp_path, monkeypatch):
        bad = ("removed_file = True\n")
        issues = self._gated_issues(tmp_path, monkeypatch, bad, "")
        assert any("无条件成功标记" in m for _, _, m in issues), (
            "丢弃物理删除返回值后无条件宣告成功必须被闸门拦下"
        )

    def test_missing_tombstone_is_caught(self, tmp_path, monkeypatch):
        bad = ("purge_file(fpath)\n" "分析任务结果 分析历史 分析检查点 中转站解析缓存\n"
               "leftovers = []\nverify = read_json(LAST_ANALYSIS_CACHE, {})\nif not force:\n"
               'report_data["_freshness"] = {}\nrelease_all()\nis_file_locked(p)\n')
        issues = self._gated_issues(tmp_path, monkeypatch, bad, "")
        assert any("墓碑" in m for _, _, m in issues)

    def test_frontend_fail_open_is_caught(self, tmp_path, monkeypatch):
        good_main = (
            "purge_file(fpath)\nadd_doc_tombstone(company_id, fname, fpath, r, p)\n"
            "load_doc_tombstones()\n分析任务结果 分析历史 分析检查点 中转站解析缓存\n"
            "leftovers = []\nverify = read_json(LAST_ANALYSIS_CACHE, {})\nif not force:\n"
            'report_data["_freshness"] = {}\nrelease_all()\nis_file_locked(p)\n'
        )
        issues = self._gated_issues(tmp_path, monkeypatch, good_main, "var x = 1;\n")
        msgs = " ".join(m for _, _, m in issues)
        assert "HTTP 状态码" in msgs and "批量接口" in msgs, (
            "前端把失败计为成功必须被闸门拦下"
        )

    def test_missing_force_and_freshness_is_caught(self, tmp_path, monkeypatch):
        bad = ("purge_file(fpath)\nadd_doc_tombstone(company_id, fname, fpath, r, p)\n"
               "load_doc_tombstones()\n分析任务结果 分析历史 分析检查点 中转站解析缓存\n"
               "leftovers = []\nverify = read_json(LAST_ANALYSIS_CACHE, {})\n"
               "release_all()\nis_file_locked(p)\n")
        issues = self._gated_issues(tmp_path, monkeypatch, bad, "")
        msgs = " ".join(m for _, _, m in issues)
        assert "强制重算" in msgs, "缺少 force 绕过必须被闸门拦下"
        assert "数据指纹" in msgs, "报告缺少新鲜度标识必须被闸门拦下"

    def test_missing_handle_release_is_caught(self, tmp_path, monkeypatch):
        """删除前不释放本服务工作簿句柄 → 必须被拦下（本次真实事故）。"""
        bad = ("purge_file(fpath)\nadd_doc_tombstone(company_id, fname, fpath, r, p)\n"
               "load_doc_tombstones()\n分析任务结果 分析历史 分析检查点 中转站解析缓存\n"
               "leftovers = []\nverify = read_json(LAST_ANALYSIS_CACHE, {})\nif not force:\n"
               'report_data["_freshness"] = {}\n')
        issues = self._gated_issues(tmp_path, monkeypatch, bad, "")
        msgs = " ".join(m for _, _, m in issues)
        assert "工作簿句柄" in msgs, "删除前未释放自家句柄必须被闸门拦下"
        assert "是否真的被占用" in msgs, "不得替用户猜占用原因"
