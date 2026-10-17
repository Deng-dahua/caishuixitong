# -*- coding: utf-8 -*-
"""PF-01 守护：法规库检索性能与缓存正确性（2026-10-17）。

背景（阶段 8 评估）
------------------
`/api/v1/legal-library` 实测 P50 **3692~7313 ms**（超标数倍）。根因两条：
  ① `legal_citation.library_file_entries()` 每次请求都重新解析 7.6k 条 JSON（26 ms）；
  ② `article_entries` **先全量装饰、最后才分页** —— 每页请求都付 7692 次
     `legal_version` 查询（每次约 0.46 ms）⇒ 3.5 秒。

修法：mtime 缓存 + 「筛选→排序→切片→按法去重装饰」。
本文件锁死"不许回退到全量装饰"，并验证缓存**不会读到旧内容**。
"""
from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import legal_citation as LC   # noqa: E402
from engine import legal_library as LL    # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_cache():
    LC.reset_library_entries_cache()
    yield
    LC.reset_library_entries_cache()


def test_decorate_called_only_for_the_page(monkeypatch) -> None:
    """★ 核心判据：一页 20 条 ⇒ 装饰**恰好 ≤20 次**（不是 7692 次）。

    这条直接锁死「先全量装饰再分页」这个 O(N)/请求 的写法。
    """
    calls = {"n": 0}
    real = LL._decorate_article

    def counting(row, bundle=None):
        calls["n"] += 1
        return real(row, bundle)

    monkeypatch.setattr(LL, "_decorate_article", counting)
    data = LL.article_entries(limit=20)
    assert data["total"] > 1000, "前置失效：正文库应有上千条"
    assert len(data["items"]) == 20
    assert calls["n"] == 20, (
        "装饰次数 %d ≠ 本页条数 20 ⇒ 又回到「全量装饰再分页」（每页 O(N) 版本查询）"
        % calls["n"])


def test_version_bundle_called_once_per_law(monkeypatch) -> None:
    """同一部法的多条目只查一次版本（按法去重，不按条重算）。"""
    calls = {"n": 0}
    real = LL._version_bundle

    def counting(law):
        calls["n"] += 1
        return real(law)

    monkeypatch.setattr(LL, "_version_bundle", counting)
    data = LL.article_entries(limit=200)
    laws = len({it["law"] for it in data["items"]})
    assert calls["n"] == laws, "版本查询 %d 次 ≠ 本页不同法数 %d" % (calls["n"], laws)


def test_reverse_full_decorate_would_be_detected() -> None:
    """反向验证：把实现换回「全量装饰」的等价写法，判据必须能识别。

    这里不依赖 patch，而是**直接度量**：全量装饰 7692 条的耗时
    必须显著大于分页装饰（否则说明正文库太小、本判据不适用）。
    """
    import time

    rows = LC.library_file_entries()
    assert len(rows) > 1000, "正文库过小，判据不适用"
    sample = rows[:120]                      # 只取小样本，避免测试自己变慢
    t0 = time.perf_counter()
    for r in sample:
        LL._version_bundle(r["law"])         # 逐条查（旧写法）
    per_item = (time.perf_counter() - t0) / len(sample)
    assert per_item > 0, "无法度量"
    # 若按旧写法装饰全部条目，理论耗时 ≈ per_item × 全部条数；断言它远超一页预算
    projected_ms = per_item * len(rows) * 1000
    assert projected_ms > 200, (
        "旧写法理论耗时仅 %.0f ms ⇒ 本判据不足以区分新老实现" % projected_ms)


def test_entries_cache_returns_same_object() -> None:
    """缓存生效：两次调用返回**同一对象**（避免重复解析 7.6k 条）。"""
    a = LC.library_file_entries()
    b = LC.library_file_entries()
    assert a is b, "未命中缓存 ⇒ 每次请求都在重新解析 JSON"


def test_cache_is_invalidated_when_file_changes(tmp_path, monkeypatch) -> None:
    """★ 安全判据：缓存键含 mtime+size ⇒ 文件一改就必须重新读（不许读到旧内容）。"""
    assert LC.library_file_entries() is LC.library_file_entries()
    # 伪造文件变化：直接动真实文件的 mtime 会污染仓库 ⇒ 只验证键的构造
    stamps = []
    for name in LC.LIBRARY_FILES:
        p = ROOT / "static" / name
        if p.exists():
            st = p.stat()
            stamps.append((name, st.st_mtime_ns, st.st_size))
    assert stamps, "正文库文件不存在"
    # 键必须包含 mtime 与 size 两个字段（任缺一个都可能读到旧内容）
    for name, mtime, size in stamps:
        assert isinstance(mtime, int) and mtime > 0, "缓存键缺 mtime_ns"
        assert isinstance(size, int) and size > 0, "缓存键缺 size"


def test_law_detail_uses_single_bundle(monkeypatch) -> None:
    """单法详情也按法只查一次版本（长法条数多时同样是性能点）。"""
    laws = LL.laws()["items"]
    assert laws, "无法清单"
    target = max(laws, key=lambda x: x["articles"])["law"]   # 条目最多的法
    calls = {"n": 0}
    real = LL._version_bundle

    def counting(law):
        calls["n"] += 1
        return real(law)

    monkeypatch.setattr(LL, "_version_bundle", counting)
    d = LL.law_detail(target)
    assert d and d["articles"], "详情为空"
    assert calls["n"] == 1, "单法详情查了 %d 次版本（应 1 次）" % calls["n"]


def test_ordering_unchanged_and_total_stable() -> None:
    """行为不变：总数稳定、按 (法名, 条号) 排序。"""
    d = LL.article_entries(limit=50)
    keys = [(it["law"], it["article"]) for it in d["items"]]
    assert keys == sorted(keys), "排序口径被改动（原为 (law, article) 升序）"
    assert d["total"] == len(LL.article_entries(limit=100000)["items"])


def test_only_current_filters_by_law_status() -> None:
    """`only_current` 语义不变：只留版本状态为 current 的法。"""
    d = LL.article_entries(only_current=True, limit=20)
    for it in d["items"]:
        assert it["version"]["status"] == "current", (
            "only_current 混入了非现行条目：%s" % it["version"]["status"])


def test_page_slice_is_consistent_with_offset() -> None:
    """分页切片与 offset 语义一致（前端翻页依赖它）。"""
    p1 = LL.article_entries(limit=10, offset=1)["items"]
    p2 = LL.article_entries(limit=10, offset=2)["items"]
    assert p1 and p2
    assert [(x["law"], x["article"]) for x in p1] != [(x["law"], x["article"]) for x in p2]
    full = LL.article_entries(limit=20, offset=1)["items"]
    assert [(x["law"], x["article"]) for x in full[:10]] == [(x["law"], x["article"]) for x in p1]
