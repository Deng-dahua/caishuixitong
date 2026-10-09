from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from runtime_storage import (atomic_write_json, atomic_write_text, read_json,
                             safe_filename)


class AtomicWriteTextTests(unittest.TestCase):
    """`atomic_write_text` —— 文本落盘的**唯一原子实现**（2026-10-09 抽出）。

    为什么单独立这一组：JSONL 类整表重写（作业流水 / 版本台账 / purge_log）
    从前各模块**各自** `mkstemp`+`os.replace`+失败 `os.unlink(tmp)`，
    闸门 `check_delete_exits` 逐行扫描"未声明的删除调用"⇒ 一写就 ERROR
    （实测 `engine/analysis_jobs.py::_rewrite_rows` 被抓）。
    现统一走本原语：既补齐"唯一实现"，又保证"删除临时文件"只有一个声明出口。
    """

    def test_writes_text_verbatim_no_trailing_newline_added(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "jobs.jsonl"
            atomic_write_text(p, "a\nb\n")
            self.assertEqual(p.read_text(encoding="utf-8"), "a\nb\n")
            atomic_write_text(p, "x")           # 不加换行
            self.assertEqual(p.read_text(encoding="utf-8"), "x")

    def test_creates_parent_dirs_and_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "deep" / "nested" / "f.txt"
            atomic_write_text(p, "first")
            atomic_write_text(p, "second")
            self.assertEqual(p.read_text(encoding="utf-8"), "second")

    def test_no_temp_residue_left_behind(self):
        """原子替换后**不得**残留临时文件（`os.replace` 已消费，失败路径才 unlink）。"""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f.txt"
            atomic_write_text(p, "v")
            self.assertEqual([f.name for f in Path(d).iterdir()], ["f.txt"])

    def test_atomic_write_json_is_thin_wrapper_same_bytes(self):
        """`atomic_write_json` 是 `atomic_write_text` 的薄包装 —— 序列化口径必须逐字节不变。

        回归意义：`atomic_write_json` 是**全量分析产物**（`company_1_full.json`）的落盘实现，
        曾因非原子写被截断成 3110 字节。重构若改了缩进/转义/中文编码就是事故。
        """
        from runtime_storage import _to_json_safe
        with tempfile.TemporaryDirectory() as d:
            value = {"b": 1, "a": {"s": {1, 2, 3}, "t": (4, 5)}, "n": None, "u": "中文"}
            for indent in (None, 1, 2):
                p = Path(d) / ("i%s.json" % indent)
                atomic_write_json(p, value, indent=indent)
                expected = json.dumps(_to_json_safe(value), ensure_ascii=False,
                                      indent=indent, default=str)
                self.assertEqual(p.read_text(encoding="utf-8"), expected)
                self.assertEqual(read_json(p, {}), {"b": 1, "a": {"s": [1, 2, 3],
                                                                  "t": [4, 5]},
                                                    "n": None, "u": "中文"})

    def test_set_and_tuple_are_serialisable(self):
        """含 `set` 的报告必须能落盘（裸 `json.dumps` 会抛 TypeError —— 既有事故根因）。"""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.json"
            atomic_write_json(p, {"codes": {"A", "B"}})
            self.assertEqual(sorted(read_json(p, {}).get("codes")), ["A", "B"])

    def test_declared_as_delete_exit_primitive(self):
        """`atomic_write_text` 必须登记在 `check_delete_exits` 的原语清单里。

        否则"它内部清理临时文件"就成了**未声明的删除出口**，闸门会报 ERROR
        （这正是它被抽出来的原因：不能再让调用方自己 `os.unlink`）。
        """
        import re
        src = (Path(__file__).resolve().parent.parent
               / "tools" / "audit_consistency.py").read_text(encoding="utf-8")
        m = re.search(r"_PRIMITIVES\s*=\s*\{([^}]*)\}", src)
        self.assertIsNotNone(m, "找不到 _PRIMITIVES 清单")
        self.assertIn('"atomic_write_text"', m.group(1))


class DeletePrimitiveSingleDefinitionTests(unittest.TestCase):
    """底层删除原语**全仓只有一份实现**（2026-10-09 补的闸门缺口）。

    背景（真实违规，非假想）：`check_delete_exits` 声明"底层原语只准在
    `runtime_storage` 里实现（唯一实现）"，但它的 `_SCAN` 只覆盖 `engine/*.py`
    + 4 个根文件 ⇒ `tools/cleanup_20261008.py` 里那份**第二份 `move_to_trash`**
    对闸门完全隐形（实测）。"删除出口唯一"的先决条件就是"原语只有一份"。

    本组直接调**闸门本身**（不另写一份判据），保证测试与闸门口径同源。
    """

    def test_no_primitive_has_a_second_definition(self):
        import tools.audit_consistency as A
        issues = A.check_delete_exits()
        dup = [i for i in issues if "份实现" in i[2] or "全仓找不到实现" in i[2]
               or "不在 runtime_storage.py" in i[2]]
        self.assertEqual(dup, [], "底层删除原语必须全仓唯一：%r" % (dup,))

    def test_each_primitive_defined_in_runtime_storage(self):
        import re
        src = (Path(__file__).resolve().parent.parent
               / "runtime_storage.py").read_text(encoding="utf-8")
        for name in ("move_to_trash", "empty_trash_batch", "purge_file",
                     "atomic_write_json", "atomic_write_text"):
            self.assertIsNotNone(
                re.search(r"^def %s\(" % re.escape(name), src, re.M),
                "唯一实现 `%s` 不在 runtime_storage.py" % name)


class StorageTests(unittest.TestCase):
    def test_safe_filename_removes_traversal(self):
        self.assertEqual(safe_filename("../../secret.pdf"), "secret.pdf")
        self.assertNotIn("/", safe_filename("a/b/../../report.xlsx"))
        self.assertNotIn("\\", safe_filename("..\\..\\report.xlsx"))

    def test_atomic_json_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "cache.json"
            value = {"company": 7, "items": [1, 2, 3]}
            atomic_write_json(path, value)
            self.assertEqual(read_json(path, {}), value)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), value)


if __name__ == "__main__":
    unittest.main()
