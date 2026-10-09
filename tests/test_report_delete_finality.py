# -*- coding: utf-8 -*-
"""删除报告必须是**终局状态**：删除后，进行中/刚跑完的分析不得把结果写回。

2026-10-01 事故实测（用户复核「删除报告提示数据不对」）：
  12:21 启动的那轮一键分析跑到 12:24:49 才完成，而用户 12:22:35 已删除报告；
  分析跑完把 last_analysis_cache / analysis_history / checkpoints 里的 "1"
  全部重新写回，界面上表现为「删了又回来」。
  ★ 关键事实：删除接口当时**如实**报了「清理 6 处」，并非谎报；真正的问题是
  删除不取消进行中的分析、且写回路径没有终局守卫。
本文件把「删除=终局」钉死，并做反向验证（摘掉守卫必须变红，否则闸门是假的）。
"""
import os
import sys

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import main as app_main  # noqa: E402

_MAIN_SRC = open(os.path.join(_PROJECT_ROOT, "main.py"), encoding="utf-8").read()


# 测试专用账套，避开真实账套 id（9991 等），用完即清
_GUARD_CID = 999971


@pytest.fixture
def guard_cid():
    app_main._deleted_company_ids.discard(_GUARD_CID)
    yield _GUARD_CID
    app_main._deleted_company_ids.discard(_GUARD_CID)
    for _tid in list(app_main._analysis_tasks):
        if app_main._analysis_tasks[_tid].get("company_id") == _GUARD_CID:
            app_main._analysis_tasks.pop(_tid, None)


class TestDeleteFinalityGuard:
    """删除终局判据本身。"""

    def test_guard_false_before_delete(self, guard_cid):
        assert app_main._is_result_deleted(guard_cid) is False

    def test_guard_true_after_delete_registered(self, guard_cid):
        app_main._deleted_company_ids.add(guard_cid)
        assert app_main._is_result_deleted(guard_cid) is True

    def test_guard_true_for_run_started_before_report_delete(self, guard_cid):
        """★ 2026-10-06 起第二路判据＝**时间水位线**（不再扫任务状态）。

        为什么换掉：旧判据是"该账套存在 status=deleted 的任务"，它把"某一条任务的删除"
        放大成"整个账套永久不许写回"，与「删除报告」共用墓碑 ⇒ 用户删过报告后，
        **此后每次重跑的结果都被永久拦下、永不落盘**（2026-10-06 用户实测：
        删账套→重建→重跑，报告一模一样且保存不下来；服务端日志有 `[删除终局] … 跳过写回`）。
        新语义：删除报告只拦"**删除发生时正在跑的那一轮**"。
        """
        import time as _t
        app_main._report_deleted_at[guard_cid] = _t.time()
        # 启动于删除**之前** ⇒ 属被删的那一份，不得写回
        assert app_main._is_result_deleted(guard_cid, started_at=app_main._report_deleted_at[guard_cid] - 10) is True

    def test_guard_false_for_run_started_after_report_delete(self, guard_cid):
        """删除报告**之后**新发起的分析必须允许写回（否则重跑的报告永远存不下来）。"""
        import time as _t
        app_main._report_deleted_at[guard_cid] = _t.time()
        assert app_main._is_result_deleted(guard_cid, started_at=app_main._report_deleted_at[guard_cid] + 10) is False

    def test_guard_true_when_company_deleted(self, guard_cid):
        """删除账套 ⇒ 永久拦截（直到重建账套）。"""
        app_main._deleted_company_ids.add(guard_cid)
        assert app_main._is_result_deleted(guard_cid, started_at=1e18) is True


class TestNoWriteBackAfterDelete:
    """删除后三个写回路径全部不得落盘（打桩，不污染真实缓存）。

    ★ 血泪教训（2026-10-01）：反向验证时我把守卫改坏去跑测试，而
      `test_persist_skips_after_delete` 只在自己函数里打桩 —— 守卫一失效，
      它真的执行了 `atomic_write_json`，把生产缓存 `last_analysis_cache.json`
      （26MB，公司1/9999 完整报告）覆盖成只剩测试假账套 `999971`。
      故本类打桩必须 **autouse 全类生效**：任何一条用例都不许碰真实缓存文件。
    """

    @pytest.fixture(autouse=True)
    def stubbed(self, monkeypatch):
        writes = []
        monkeypatch.setattr(app_main, "atomic_write_json", lambda p, v: writes.append(str(p)))
        monkeypatch.setattr(app_main, "_analysis_history", {})
        app_main._last_analysis_cache.pop(_GUARD_CID, None)
        # ★ 2026-10-06：**测试卫生** —— 本类新增了「删除报告水位线」用例，
        #   若不在每个用例前后清干净，水位线会污染后续"无守卫必须落盘"的反向用例
        #   （实测：2 条反向用例因此误判为失败）。三个状态一并复位。
        def _reset():
            app_main._deleted_company_ids.discard(_GUARD_CID)
            app_main._report_deleted_at.pop(_GUARD_CID, None)
            app_main._analysis_started_at.pop(_GUARD_CID, None)
        _reset()
        yield writes
        _reset()

    # ---- ① 分析历史 -------------------------------------------------------
    def test_history_not_appended_after_delete(self, stubbed, guard_cid):
        app_main._deleted_company_ids.add(guard_cid)
        app_main._append_analysis_history(guard_cid, {"report": {}})
        assert stubbed == [], "删除后仍写了分析历史 → 删除会被静默撤销"

    def test_history_would_be_appended_without_guard(self, stubbed, guard_cid):
        """反向验证：不登记删除时，同一路径必须真的落盘（证明守卫不是空守卫）。"""
        app_main._append_analysis_history(guard_cid, {"report": {}})
        assert len(stubbed) == 1

    # ---- ② 分析检查点 -----------------------------------------------------
    def test_checkpoint_not_written_after_delete(self, stubbed, guard_cid):
        app_main._deleted_company_ids.add(guard_cid)
        app_main._write_analysis_checkpoint(guard_cid, "done", "ok")
        assert stubbed == [], "删除后仍写了检查点 → 12:24:49 那种写回复活会重演"

    def test_checkpoint_would_be_written_without_guard(self, stubbed, guard_cid):
        """反向验证：未登记删除时，检查点必须真的落盘。"""
        app_main._write_analysis_checkpoint(guard_cid, "done", "ok")
        assert len(stubbed) == 1

    # ---- ③ 最近结果缓存 ---------------------------------------------------
    def test_persist_skips_after_delete(self, stubbed, monkeypatch, guard_cid):
        """_persist_one_click_result 是最近结果缓存的唯一写入点（内存+磁盘）。"""
        app_main._last_analysis_cache.pop(guard_cid, None)
        app_main._deleted_company_ids.add(guard_cid)
        called = []
        monkeypatch.setattr(app_main, "_append_analysis_history", lambda c, r: called.append(c))
        app_main._persist_one_click_result(guard_cid, {"ok": True, "report": {}})
        assert guard_cid not in app_main._last_analysis_cache, "删除后被写回最近结果缓存"
        assert called == [], "删除后仍追加了分析历史"
        # ★ 防污染闸门：测试进程绝不允许把内容写进真实的 last_analysis_cache.json
        #   （守卫被摘掉时这条会红，正是我们要的信号：不是产品错，是测试不能再碰生产文件）
        assert not any("last_analysis_cache" in p for p in stubbed), (
            f"测试写到了真实缓存文件，已污染生产数据：{stubbed}")


class TestDeleteFinalityWiringSource:
    """源码级：三条写回路径都必须挂守卫，漏一处 = 删除可被复活。"""

    def test_all_result_write_paths_guarded(self):
        for marker in (
            "def _persist_one_click_result(",
            "def _append_analysis_history(",
            "def _write_analysis_checkpoint(",
        ):
            start = _MAIN_SRC.index(marker)
            nxt = _MAIN_SRC.find("\ndef ", start + len(marker))
            body = _MAIN_SRC[start: nxt if nxt > 0 else len(_MAIN_SRC)]
            assert "_is_result_deleted(" in body, (
                f"{marker} 未挂删除终局守卫：进行中的分析跑完会把已删结果写回"
            )
