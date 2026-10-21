# -*- coding: utf-8 -*-
"""报告出口序列化：防「分析完成后接口 500」（2026-10-21 线上缺陷）。

缺陷链（已复现）
---------------
`report_data["_fact_store"]` = `FactStore` 实例（内部 `_by_key` 是
`Dict[Tuple[str,str,str], ...]`）→ 被原样放进 `_last_analysis_cache`
→ `GET /api/tax-risk-docs/last-analysis` 直接 `return cached["report"]`
→ FastAPI `jsonable_encoder` 对非 dict/list 对象走 `vars()` 分支，
取出 tuple 键 dict → `jsonable_encoder(key)` 把 tuple 转 list →
`encoded_dict[list]` ⇒ `TypeError: unhashable type: 'list'`（encoders.py:297）。

★ 为什么长期未发现：落盘走 `runtime_storage._to_json_safe`，它对非原生类型
  `return str(value)`，把实例洗成 `"<FactStore object at 0x...>"`；
  重启后从磁盘回填的缓存是"干净"的 ⇒ **只有分析完成且未重启时才崩**。

本测试覆盖
---------
1. 复现缺陷（用真实 FactStore 实例，证明判据真能抓到问题 —— 反向验证）；
2. `normalize` 修复后必须可序列化；
3. `scrub_in_place` 就地清洗（生产路径实际用的那个）；
4. 全量扫描：归一后不得残留任何非 JSON 原生类型（tuple/set/date/自定义对象）；
5. 能力不丢：`FactStore.to_dict()` → `from_dict()` 往返后 digest 一致；
6. `get_store()` 能从快照 dict 恢复实例（跨请求读路径）；
7. 源码契约：报告出口必须调用归一化（防"接线被删"）。
"""
from __future__ import annotations

import datetime
import io
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi.encoders import jsonable_encoder                      # noqa: E402

from engine.fact_store import FactStore, get_store                 # noqa: E402
from engine.report_serialization import (                          # noqa: E402
    CIRCULAR_MARKER, normalize, scrub_in_place,
)

NATIVE = (str, int, float, bool, type(None))


def _scan_nonjson(obj, path="ROOT", depth=0, out=None, seen=None, limit=200):
    if out is None:
        out = []
    if seen is None:
        seen = set()
    if depth > 80 or len(out) >= limit:
        return out
    if isinstance(obj, NATIVE):
        return out
    oid = id(obj)
    if oid in seen:
        return out
    seen.add(oid)
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                out.append((path, "非串键=%s" % type(k).__name__))
            _scan_nonjson(v, path + "/" + (k[:24] if isinstance(k, str) else "?"),
                          depth + 1, out, seen, limit)
    elif isinstance(obj, (list, tuple, set, frozenset)):
        if not isinstance(obj, list):
            out.append((path, "容器=%s" % type(obj).__name__))
        for i, v in enumerate(list(obj)[:2000]):
            _scan_nonjson(v, "%s[%d]" % (path, i), depth + 1, out, seen, limit)
    else:
        out.append((path, "对象=%s" % type(obj).__name__))
    return out


def _store_with_facts() -> FactStore:
    st = FactStore(company_code="TESTCO", period="2026-01")
    st.declare(kind="amount", label="营业收入", value=1_000_000, period="2026-01",
               source="test")
    st.declare(kind="amount", label="销项税额", value=130_000, period="2026-01",
               source="test")
    return st


class TestDefectReproduction:
    """① 反向验证：判据（jsonable_encoder）必须能抓到原始缺陷。"""

    def test_raw_factstore_instance_crashes_jsonable_encoder(self):
        """未归一的 FactStore 实例必须让 FastAPI 序列化崩溃（证明缺陷真实）。"""
        d = {"_fact_store": _store_with_facts(), "x": 1}
        with pytest.raises(TypeError) as ei:
            jsonable_encoder(d)
        assert "unhashable" in str(ei.value).lower(), (
            "期望 unhashable type 错误，实得：%s" % ei.value)

    def test_raw_tuple_and_set_and_date_also_crash(self):
        """tuple 键 / set / date 同样会让序列化出问题（本仓同类项）。"""
        d1 = {"m": {("a", "b"): 1}}
        with pytest.raises(TypeError):
            jsonable_encoder(d1)

    def test_by_key_is_tuple_keyed(self):
        """根因确认：`FactStore._by_key` 的键是 tuple。"""
        st = _store_with_facts()
        assert st._by_key, "事实库应有键"
        assert all(isinstance(k, tuple) for k in st._by_key), (
            "_by_key 键应为 tuple —— 这是 500 的根因")


class TestNormalize:
    """② normalize：任意对象 → JSON 原生，且**信息不丢**。"""

    def test_factstore_becomes_serializable_snapshot(self):
        st = _store_with_facts()
        out = normalize({"_fact_store": st})
        jsonable_encoder(out)                                # 不抛即通过
        snap = out["_fact_store"]
        assert isinstance(snap, dict)
        assert snap["stats"]["total"] == 2
        assert len(snap["facts"]) == 2

    def test_tuple_becomes_list(self):
        assert normalize((1, 2, 3)) == [1, 2, 3]

    def test_set_becomes_sorted_list(self):
        assert normalize({"b", "a", "c"}) == ["a", "b", "c"]

    def test_date_becomes_iso_string(self):
        assert normalize(datetime.date(2026, 3, 31)) == "2026-03-31"
        assert normalize(datetime.datetime(2026, 3, 31, 12, 30, 5)).startswith("2026-03-31T12:30:05")

    def test_nonstr_dict_key_becomes_str(self):
        out = normalize({("a", "b"): 1, 2: "x"})
        assert set(out.keys()) == {"('a', 'b')", "2"}

    def test_none_inside_value_preserved(self):
        """★ 缺失≠0：value=None 必须保留为 None，不得被默认值顶替。"""
        st = FactStore(company_code="C", period="2026-01")
        st.declare(kind="amount", label="未取到值", value=None, period="2026-01")
        out = normalize(st.to_dict())
        assert out["facts"][0]["value"] is None

    def test_circular_reference_marked_not_crash(self):
        d = {"a": 1}
        d["self"] = d
        out = normalize(d)
        assert out["self"] == CIRCULAR_MARKER or out["self"]["self"] == CIRCULAR_MARKER

    def test_never_raises_on_weird_object(self):
        class Weird:
            __slots__ = ()
        out = normalize({"w": Weird()})
        jsonable_encoder(out)                                # 不抛即通过


class TestScrubInPlace:
    """③ 生产路径用的就地清洗。"""

    def test_scrub_makes_whole_payload_serializable(self):
        payload = {
            "_fact_store": _store_with_facts(),
            "span": (datetime.date(2026, 1, 1), datetime.date(2026, 3, 31)),
            "names": {"甲", "乙"},
            "nested": {"deep": {("k1", "k2"): "v"}},
            "list": [(1, 2), {"s": {1, 2}}],
        }
        scrub_in_place(payload)
        jsonable_encoder(payload)                            # 不抛即通过
        assert _scan_nonjson(payload) == [], (
            "残留非 JSON 原生值：%r" % _scan_nonjson(payload)[:6])

    def test_scrub_preserves_dict_identity_when_possible(self):
        """就地清洗应尽量保留原容器引用（减小内存翻倍）。"""
        inner = {"a": 1}
        payload = {"inner": inner}
        scrub_in_place(payload)
        assert payload["inner"] is inner


class TestCapabilityPreserved:
    """④ 能力不丢：快照可重建事实库，digest 一致。"""

    def test_roundtrip_digest_identical(self):
        st = _store_with_facts()
        before = st.digest()
        snap = normalize(st.to_dict())
        rebuilt = FactStore.from_dict(snap)
        assert rebuilt is not None, "快照必须可重建"
        assert rebuilt.digest() == before, "往返后 digest 必须一致"

    def test_get_store_recovers_from_snapshot(self):
        """跨请求读路径：容器里是快照 dict 时，`get_store` 必须能给出可用实例。"""
        st = _store_with_facts()
        container = {"_fact_store": normalize(st.to_dict())}
        got = get_store(container)
        assert isinstance(got, FactStore), "get_store 应从快照恢复实例"
        assert got.stats()["total"] == 2
        assert isinstance(container["_fact_store"], FactStore), "应就地升级为实例"

    def test_from_dict_rejects_garbage(self):
        assert FactStore.from_dict(None) is None
        assert FactStore.from_dict({"no_facts": 1}) is None
        assert FactStore.from_dict("not a dict") is None

    def test_conflicts_survive_roundtrip(self):
        st = FactStore(company_code="C", period="2026-01")
        st.declare(kind="amount", label="营业收入", value=100, period="2026-01")
        st.declare(kind="amount", label="营业收入", value=200, period="2026-01")
        assert st.conflicts(), "同键不同值应构成冲突"
        rebuilt = FactStore.from_dict(normalize(st.to_dict()))
        assert rebuilt is not None
        assert len(rebuilt.conflicts()) == len(st.conflicts()), "冲突数应一致"


class TestWiringContract:
    """⑤ 源码契约：报告出口必须调用归一化（防接线被删 / 被挪走）。"""

    def _main_src(self) -> str:
        return io.open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()

    def test_persist_calls_scrub_before_cache_write(self):
        src = self._main_src()
        # 归一化必须出现在 `_persist_one_click_result` 里，且在写缓存之前
        i_fn = src.find("def _persist_one_click_result")
        assert i_fn > 0, "找不到 _persist_one_click_result"
        i_cache = src.find("_last_analysis_cache[company_id] = {", i_fn)
        assert i_cache > 0, "找不到写缓存处"
        seg = src[i_fn:i_cache]
        assert re.search(r"scrub_in_place\s*\(|report_serialization", seg), (
            "写缓存前必须调用归一化（否则分析后接口 500 复发）")

    def test_reuses_single_authority_not_local_copy(self):
        """归一化口径不得在 main.py 里另写一份。"""
        src = self._main_src()
        i_fn = src.find("def _persist_one_click_result")
        i_cache = src.find("_last_analysis_cache[company_id] = {", i_fn)
        seg = src[i_fn:i_cache]
        assert "report_serialization" in seg, "必须复用唯一权威模块"
        # 不得自己写 json.dumps/json.loads 往返来实现归一
        assert "json.dumps" not in seg, "不得在出口自写一份归一化（多头维护）"

    def test_fund_invoice_flexible_jsonable_wiring(self):
        """柔性匹配引擎的 objects 必须过归一化（本模块自带 tuple/date）。"""
        src = io.open(os.path.join(ROOT, "engine", "fund_invoice_flexible.py"),
                      encoding="utf-8").read()
        assert re.search(r'"objects":\s*_jsonable\(', src), (
            "objects 必须经 _jsonable 归一化（含 invoice_span tuple 与 date）")
        assert "report_serialization" in src, "必须复用唯一权威，不得自写转换"

    def test_pipeline_supply_personnel_names_not_set(self):
        """`supply_personnel_map[*].their_names` 返回前必须转成可序列化类型。"""
        src = io.open(os.path.join(ROOT, "engine", "pipeline.py"),
                      encoding="utf-8").read()
        assert re.search(r'_spm\["their_names"\]\s*=\s*sorted', src), (
            "their_names 必须在返回前由 set 转为 list（否则序列化出问题）")