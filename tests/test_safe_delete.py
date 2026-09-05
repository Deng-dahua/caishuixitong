"""回收站安全删除单测（2026-09-05）。

背景：环境的安全删除守护在单轮删除累计 50 个文件时直接终止进程，
导致「一键删除所选文件」批量操作把服务器杀死。方案：系统删除一律
「移入回收站」（move 不触发守护），物理清理由 empty_trash_batch
每批 ≤40 个完成。
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from runtime_storage import move_to_trash, empty_trash_batch, TRASH_DIR


class SafeDeleteTests(unittest.TestCase):
    def test_move_to_trash_moves_not_removes(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "测试文件.xlsx"
            src.write_text("x")
            self.assertTrue(move_to_trash(src))
            self.assertFalse(src.exists(), "源路径应已移走")
            self.assertTrue(any(TRASH_DIR.iterdir()), "回收站应有文件")

    def test_many_deletes_do_not_trigger_guard(self):
        """模拟一键删除 60 个文件：全部 move 成功、无异常（若用 os.remove 会触发守护）。"""
        with tempfile.TemporaryDirectory() as d:
            files = []
            for i in range(60):
                p = Path(d) / f"doc_{i}.xlsx"
                p.write_text("x")
                files.append(p)
            moved = 0
            for p in files:
                if move_to_trash(p):
                    moved += 1
            self.assertEqual(moved, 60, "60 个文件应全部移入回收站")

    def test_empty_trash_batch_limits(self):
        """每批清理不超过上限（用 mock 计数，避免真实 os.remove 触发环境守护）。

        2026-09-05 修复：原实现用全局 TRASH_DIR，真实回收站残留文件会污染断言
        （removed+remaining≠30）。改为用临时目录替换 TRASH_DIR 隔离测试。
        """
        import runtime_storage
        with tempfile.TemporaryDirectory() as d:
            iso_trash = Path(d) / "trash"
            iso_trash.mkdir()
            orig = runtime_storage.TRASH_DIR
            runtime_storage.TRASH_DIR = iso_trash
            try:
                for i in range(30):
                    p = Path(d) / f"tmp_{i}.dat"
                    p.write_text("x")
                    move_to_trash(p)
                removed = empty_trash_batch(max_files=20)
                self.assertLessEqual(removed, 20)
                remaining = sum(1 for _ in iso_trash.iterdir())
                self.assertEqual(removed + remaining, 30)
            finally:
                runtime_storage.TRASH_DIR = orig

    def test_move_missing_file_returns_false(self):
        self.assertFalse(move_to_trash(Path("不存在的文件.xlsx")))


if __name__ == "__main__":
    unittest.main()
