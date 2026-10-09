# -*- coding: utf-8 -*-
"""「删除账套 ⇒ 派生物一起清」契约测试（2026-10-06）。

## 背景（用户原话）
> 「若是在系统上进行了删除处理的，你能不能设置成与之相应的文件都删除和修改相应的信息。
>   例如4个产物就必须改为1个产物，公司2/3/4的缓存或相应的资料和信息都应该删除。
>   待重新建立时再新建文件。就是这些常规的思考和动作，能不能都做到位，不要踢一脚动一下！！！」

## 已实测的病根
  · 删除账套 `/api/companies/{id}` 只删 Company 行 + 授权，**不调**"删除报告"的清理
    ⇒ 报告 6 处副本 + 离线产物全部残留；
  · 库被重置（企业直接消失）更没人管 ⇒ `scripts/four_reports/` 躺着 id=2/3/4 的产物，
    而库里只有 id=1（"4 份产物" vs "1 家企业"）；
  · 重建账套若不撤销删除墓碑，复用的 id 会被 `_is_result_deleted` 静默拦下
    ⇒ "新建的企业永远出不来报告"。

## 单一权威
  `main.purge_company_analysis_artifacts(company_id, include_uploads)` ——
  「删除报告」与「删除账套」**都**走它；历史孤儿用
  `scripts/_purge_orphan_company_artifacts.py --apply` 回溯清理。
"""
import io
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from runtime_storage import (                              # noqa: E402
    add_doc_tombstone, atomic_write_json, clear_company_doc_tombstones,
    count_company_doc_tombstones, load_doc_tombstones)

MAIN_SRC = io.open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()


def _code_of(fn_src: str) -> str:
    """去 docstring + 去行注释（与闸门同一视图）——名字出现在文档里**不算**真的调用了。"""
    t = re.sub(r'""".*?"""', " ", fn_src, flags=re.S)
    return re.sub(r"#[^\n]*", "", t)


class TestRuntimeStorageTombstonePurge(unittest.TestCase):
    """墓碑清理：账套没了，它的墓碑也该没（否则复用的 id 会被旧墓碑误伤）。"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._path = os.path.join(self._tmp, "deleted_docs.json")
        self._patcher = mock.patch("runtime_storage.DELETED_DOCS", self._path)
        self._patcher.start()
        self.addCleanup(self._patcher.stop)
        # 两个企业的墓碑
        add_doc_tombstone(1, "发票_1.json", path="/x/1", purged=True)
        add_doc_tombstone(2, "发票_2.json", path="/x/2", purged=True)
        add_doc_tombstone(2, "工资表_2.xlsx", path="/x/3", purged=False)

    def test_clear_only_target_company(self):
        n = clear_company_doc_tombstones(2)
        self.assertEqual(n, 2, "应清掉企业 2 的 2 条墓碑")
        self.assertEqual(count_company_doc_tombstones(2), 0)
        self.assertEqual(count_company_doc_tombstones(1), 1, "不得误伤别的企业")
        left = [v for v in load_doc_tombstones().values()
                if int(v.get("company_id") or 0) == 1]
        self.assertEqual(len(left), 1)

    def test_unknown_company_is_noop(self):
        self.assertEqual(clear_company_doc_tombstones(99999), 0)
        self.assertEqual(count_company_doc_tombstones(1), 1, "清理无关企业不得动现有墓碑")

    def test_invalid_id_is_noop(self):
        self.assertEqual(clear_company_doc_tombstones(0), 0)
        self.assertEqual(clear_company_doc_tombstones(-3), 0)


class TestAtomicWriteJson(unittest.TestCase):
    """唯一落盘实现：indent 可选；写完可读。"""

    def test_indent_optional(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "x.json")
            atomic_write_json(p, {"a": 1, "中文": "值"}, indent=1)
            self.assertEqual(json.load(io.open(p, encoding="utf-8")), {"a": 1, "中文": "值"})
            atomic_write_json(p, {"b": 2})
            self.assertEqual(json.load(io.open(p, encoding="utf-8")), {"b": 2})
            self.assertFalse([f for f in os.listdir(td) if f.endswith(".tmp")],
                             "原子写不得残留 .tmp 文件")


class TestDeleteWiring(unittest.TestCase):
    """静态契约（与闸门同一视图）：两处删除都必须走唯一权威。"""

    def test_delete_company_calls_authority_with_uploads(self):
        m = re.search(r"\ndef delete_company\(.*?(?=\n@app\.|\Z)", MAIN_SRC, re.S)
        self.assertTrue(m, "找不到 delete_company")
        body = _code_of(m.group(0))
        self.assertIn("purge_company_analysis_artifacts", body,
                      "删除账套必须调用唯一权威（只写在文档里不算）")
        self.assertIn("include_uploads=True", body,
                      "删账套必须连上传原件一起清")
        self.assertIn("delete_company_cascade", body,
                      "删账套仍须清用户授权与会话选中态")

    def test_create_company_discards_tombstone(self):
        m = re.search(r"\ndef create_company\(.*?(?=\n@app\.|\Z)", MAIN_SRC, re.S)
        self.assertTrue(m, "找不到 create_company")
        body = _code_of(m.group(0))
        self.assertIn("_deleted_company_ids.discard", body,
                      "重建账套必须撤销删除墓碑（否则 id 复用时新企业出不来报告）")
        self.assertIn("clear_company_doc_tombstones", body,
                      "重建账套必须清该 id 的资料删除墓碑")

    def test_report_endpoint_uses_authority_without_uploads(self):
        m = re.search(r"\ndef delete_tax_risk_report\(.*?(?=\ndef |\n@app\.|\Z)",
                      MAIN_SRC, re.S)
        self.assertTrue(m, "找不到 delete_tax_risk_report")
        body = _code_of(m.group(0))
        self.assertIn("purge_company_analysis_artifacts", body,
                      "删除报告必须走唯一权威")
        self.assertNotIn("include_uploads=True", body,
                         "「删除报告」不得连上传原件一起删（那是「删除账套」的语义）")

    def test_authority_is_single_definition(self):
        """唯一权威在 main.py 里必须只定义一次（同名旧定义会静默覆盖新定义）。"""
        self.assertEqual(MAIN_SRC.count("def purge_company_analysis_artifacts("), 1)

    def test_authority_covers_all_known_artifacts(self):
        """权威必须覆盖已知的全部派生物（清单写在 docstring 之外、代码之内）。"""
        m = re.search(r"\ndef purge_company_analysis_artifacts\(.*?(?=\ndef |\n@app\.|\Z)",
                      MAIN_SRC, re.S)
        self.assertTrue(m, "找不到唯一权威")
        body = _code_of(m.group(0))
        for token, why in (
            ("_last_analysis_cache", "内存分析缓存"),
            ("LAST_ANALYSIS_CACHE", "磁盘分析缓存"),
            ("_analysis_tasks", "分析任务结果"),
            ("_analysis_history", "分析历史"),
            ("CHECKPOINT_DIR", "分析检查点"),
            ("TRANSFER_DIR", "中转站解析缓存"),
            ("offline_reports_root", "离线分析产物（目录必须跟随应用数据根）"),
            ("clear_company_doc_tombstones", "资料删除墓碑"),
            ("RUNTIME_UPLOAD_DIR", "上传原件目录"),
        ):
            self.assertIn(token, body, "清理权威缺少：%s" % why)


class TestSafetyGuard(unittest.TestCase):
    """★ 安全护栏：清上传原件必须**显式确认**（2026-10-06 两次实测事故后定稿）。

    事故一：`purge_company_analysis_artifacts(1, include_uploads=True)` 曾把
      `company_1_full.json` + summary + api_result 清掉（该企业仍在库里）。
    事故二：把护栏改成"活查数据库"后，**全量 pytest 期间**有测试改变了 DB 可见状态
      ⇒ 护栏被判成"企业不存在"⇒ 在库企业产物又被清掉（清理审计日志抓到）。
    ⇒ 定稿设计：**显式确认**。`include_uploads=True` 必须 `confirmed_deleted=True`，
      该参数只允许「删除账套」端点在 Company 行删除并提交之后传入；
      **不依赖任何运行时状态** ⇒ 测试里根本无法误触发。
    """

    PROD = os.path.join(ROOT, "scripts", "four_reports", "company_1_full.json")

    def _product_bytes(self):
        if not os.path.exists(self.PROD):
            return None
        with open(self.PROD, "rb") as fh:
            return fh.read()

    def test_unconfirmed_purge_is_refused(self):
        """未显式确认 ⇒ 必须拒绝且**什么都不删**（本测试不依赖任何运行时状态）。"""
        from main import purge_company_analysis_artifacts             # noqa: PLC0415
        before = self._product_bytes()
        try:
            out = purge_company_analysis_artifacts(1, include_uploads=True)
            self.assertEqual(out["cleared"], [],
                             "未确认就被执行了（护栏失效，这会清掉在库企业的产物）")
            self.assertTrue(any("confirmed_deleted" in x for x in out["leftovers"]),
                            "拒绝时必须说明缺显式确认")
        finally:
            after = self._product_bytes()
            if before is not None and after != before:
                with open(self.PROD, "wb") as fh:
                    fh.write(before)

    def test_confirmed_purge_for_absent_company_touches_nothing_real(self):
        """纵深防御对照：对**不存在**的企业清理 ⇒ 不应碰到真实产物。

        ⚠ 不得用真实在库/刚删的 id 来测 —— 2026-10-06 事故正是测试真调清理
          把真实产物删了。此处用必然不存在的 id=99999，并核对真实产物字节不变。
        """
        from main import purge_company_analysis_artifacts             # noqa: PLC0415
        before = self._product_bytes()
        out = purge_company_analysis_artifacts(99999, include_uploads=True,
                                               confirmed_deleted=True)
        self.assertNotIn("上传原件", " ".join(out["cleared"]),
                         "不存在的企业不可能有上传原件")
        self.assertEqual(self._product_bytes(), before,
                         "对不存在企业的清理不得触碰真实产物")

    def test_report_delete_still_allowed_for_live_company(self):
        """对照：在库企业的「删除报告」语义（不带上传原件）不被护栏挡住 ——
        但为不破坏真产物，这里只断言**调用链可达**（结构级），不真调。"""
        m = re.search(r"\ndef delete_tax_risk_report\(.*?(?=\ndef |\n@app\.|\Z)",
                      MAIN_SRC, re.S)
        body = _code_of(m.group(0))
        self.assertIn("purge_company_analysis_artifacts(company_id, include_uploads=False)", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
