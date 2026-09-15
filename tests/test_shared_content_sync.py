# -*- coding: utf-8 -*-
"""共享内容一致性（文本维度）测试（2026-09-15）。

目的：证明该校验**能失败**（否则等于又造一个永远绿灯的假门禁）。
覆盖：逐字不一致→失败、一致→通过、权威源缺失且标 legacy→显式披露不计通过、
      未标 legacy 而权威源缺失→失败。
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from engine import shared_content_sync as scs


class SharedContentSyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="scs_"))
        (self.tmp / "static" / "js").mkdir(parents=True, exist_ok=True)
        self._orig_root, self._orig_map = scs.ROOT, scs.MAP_FILE
        scs.ROOT = self.tmp
        scs.MAP_FILE = self.tmp / "static" / "shared_content_map.json"
        self.addCleanup(self._restore)

    def _restore(self):
        scs.ROOT, scs.MAP_FILE = self._orig_root, self._orig_map
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, rel: str, text: str):
        p = self.tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def _write_map(self, blocks):
        scs.MAP_FILE.write_text(
            json.dumps({"text_sync_blocks": blocks, "concept_links": []},
                       ensure_ascii=False, indent=2), encoding="utf-8")

    # 提取器按文件名分派：权威源用 standards 的 sections 格式，依赖用手册二元数组
    _SRC = "static/js/tax-report-standards.js"
    _DEP = "static/js/tax-auditor-handbook.js"

    def _write_src(self, title, body):
        self._write(self._SRC,
                    "{id:'rpt-1', kicker:'01', title:'%s', summary:'s', body:`%s`}" % (title, body))

    def _write_dep(self, title, body):
        self._write(self._DEP, "['%s','%s']" % (title, body))

    def test_mismatch_fails(self):
        """依赖副本与权威源不一致 → 必须失败（证明门禁有效）"""
        self._write_src("标题X", "权威正文")
        self._write_dep("标题X", "不一样的副本")
        self._write_map([{
            "id": "b1", "label": "标题X", "status": "active",
            "source_file": self._SRC, "dependent_files": [self._DEP],
        }])
        ok, log = scs.verify_shared_content()
        self.assertFalse(ok, "逐字不一致却判通过，门禁失效")
        self.assertTrue(any("不一致" in line for line in log))

    def test_match_passes(self):
        """两方逐字一致 → 通过"""
        self._write_src("标题Y", "相同正文")
        self._write_dep("标题Y", "相同正文")
        self._write_map([{
            "id": "b2", "label": "标题Y", "status": "active",
            "source_file": self._SRC, "dependent_files": [self._DEP],
        }])
        ok, _log = scs.verify_shared_content()
        self.assertTrue(ok)

    def test_legacy_missing_source_disclosed_not_passed(self):
        """权威源缺失但已标 legacy → 显式披露，不计通过也不计失败"""
        self._write_map([{
            "id": "b3", "label": "标题Z", "status": "legacy_unmapped",
            "source_file": "static/js/gone.js", "dependent_files": [],
        }])
        ok, log = scs.verify_shared_content()
        self.assertTrue(ok)
        self.assertTrue(any("历史遗留块" in line for line in log))

    def test_active_missing_source_fails(self):
        """未标 legacy 而权威源缺失 → 必须失败（不得静默通过）"""
        self._write_map([{
            "id": "b4", "label": "标题W", "status": "active",
            "source_file": "static/js/gone.js", "dependent_files": [],
        }])
        ok, log = scs.verify_shared_content()
        self.assertFalse(ok)
        self.assertTrue(any("❌" in line for line in log))


if __name__ == "__main__":
    unittest.main()
