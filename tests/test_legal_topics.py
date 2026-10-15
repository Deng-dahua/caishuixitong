# -*- coding: utf-8 -*-
"""步骤 22 前端/读层测试：专题 · 目录 · 关系 · 材料 · 条款。

分三组：
  ① **读层数据自证**（索引与上游一致、下标不越界、统计可复算）；
  ② **边界与降级**（不存在 id / 空 key / 缺口必须带 reason，不静默）；
  ③ **端到端接线**（路由顺序、页面可达、前端不硬编码）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def LT():
    from engine import legal_topics
    return legal_topics


@pytest.fixture(scope="module")
def LC():
    from engine import legal_catalog
    return legal_catalog


@pytest.fixture(scope="module")
def LE():
    from engine import legal_extras
    return legal_extras


class TestTopicIndexIntegrity:
    """① 专题索引与上游一致（派生层不得与源漂移）。"""

    def test_下标不越界且指向真实条目(self, LT):
        cat = json.loads((ROOT / "config" / "legal_catalog.json").read_text(encoding="utf-8"))
        n = len(cat.get("items") or [])
        for t in LT.list_topics()["items"]:
            det = LT.topic_detail(t["id"])
            docs = LT.topic_documents(t["id"], page=1, page_size=1)
            assert docs["total"] == det["documents_total"], (
                "专题 %s 清单条数(%d) 与索引统计(%d) 不一致 ⇒ 索引过期，须重跑生成器"
                % (t["id"], docs["total"], det["documents_total"]))
            assert all(0 <= i < n for i in (LT._topic_of(t["id"]).get("doc_indexes") or [])[:50])

    def test_核心法规确实在清单内(self, LT):
        """`core_titles` 登记的核心法**必须**出现在该专题清单里（否则登记形同虚设）。"""
        for t in LT.list_topics()["items"]:
            if not t.get("core_titles"):
                continue
            det = LT.topic_detail(t["id"])
            assert det.get("documents_core", 0) > 0, (
                "专题 %s 登记了 %d 个核心法却 0 条命中" % (t["id"], len(t["core_titles"])))

    def test_分组统计求和等于总数(self, LT):
        for t in LT.list_topics()["items"]:
            det = LT.topic_detail(t["id"])
            assert sum((det.get("documents_by_group") or {}).values()) == det["documents_total"]

    def test_条款归属标签有效(self, LT):
        """条款的 `topic_tags` 必须都是索引里真实存在的专题（防打标漂移）。"""
        ids = {t["id"] for t in LT.list_topics()["items"]}
        provs = json.loads((ROOT / "config" / "legal_provisions.json")
                           .read_text(encoding="utf-8")).get("provisions") or []
        for p in provs:
            for tag in (p.get("topic_tags") or []):
                assert tag in ids, "条款 %s 的标签 %s 不是已知专题" % (p.get("provision_id"), tag)


class TestCatalogIntegrity:
    """① 目录/关系数据自证。"""

    def test_目录无同URL路径重复(self):
        """★ 三源合并必须按 URL 去重（指令 3.3）；实测曾 540 种标题重复。"""
        from urllib.parse import urlparse
        items = json.loads((ROOT / "config" / "legal_catalog.json")
                           .read_text(encoding="utf-8")).get("items") or []
        seen, dup = set(), []
        for it in items:
            p = urlparse(str(it.get("url") or "")).path
            if not p:
                continue
            if p in seen:
                dup.append(p)
            seen.add(p)
        assert not dup, "存在 %d 条同 URL 路径重复（未去重）：%s" % (len(dup), dup[:3])

    def test_关系类型只取白名单(self, LC):
        """★ 关系类型不得混入非关系词（实测曾出现「国务院令」「审议结果的报告」）。"""
        rel = LC.relations(page=1, page_size=500)
        known = set((rel.get("relation_types") or {}).keys())
        assert known, "关系类型白名单为空"
        for x in rel["items"]:
            assert str(x.get("relation")) in known, "未登记的关系类型：%s" % x.get("relation")
        # `relation_cn` 也必须是白名单里的中文名（不得是原始 busi_type）
        names = set((rel.get("relation_types") or {}).values())
        for x in rel["items"]:
            assert str(x.get("relation_cn")) in names, (
                "关系中文名不在白名单（疑为原始形态）：%s" % x.get("relation_cn"))

    def test_关系条目带证据原文(self, LC):
        for x in LC.relations(page=1, page_size=100)["items"]:
            assert str(x.get("evidence") or "").strip(), "关系缺 evidence（不可复核）"


class TestBoundaryAndDegrade:
    """② 边界与降级（不静默空、不近似匹配）。"""

    def test_不存在专题返回found_false(self, LT):
        d = LT.topic_detail("TOPIC-999")
        assert d.get("found") is False and d.get("note")

    def test_不存在材料返回found_false(self, LE):
        d = LE.material_detail("MAT-NOT-EXIST")
        assert d.get("found") is False and d.get("note")

    def test_不存在目录下标返回found_false(self, LC):
        d = LC.document(999999)
        assert d.get("found") is False and d.get("note")

    def test_关系查不到必须给reason(self, LC):
        r = LC.relations_of(title="某不存在的法规名称")
        assert r["total"] == 0 and r.get("reason"), "查不到关系必须说明原因，不得静默空"

    def test_专题材料缺口必须带reason(self, LT):
        """★ 遍历全部专题：无材料者必须有 `reason`（≠「没有相关材料」）。"""
        for t in LT.list_topics()["items"]:
            m = LT.topic_materials(t["id"])
            if not m.get("total"):
                assert m.get("reason"), "专题 %s 材料为空却无 reason" % t["id"]

    def test_条款正文缺失如实标注(self, LT, LC):
        """正文未入库 ⇒ `has_content=False`，**不得**编造条文。"""
        # 挑一个术语上必然无正文的：目录条目（非条款）
        d = LC.document(0)
        assert d.get("has_body_in_library") in (True, False)
        assert d.get("body_note"), "目录详情必须说明正文状态"


class TestEndToEndWiring:
    """③ 端到端接线（路由顺序 / 页面 / 前端不硬编码）。"""

    def test_路由顺序字面量先于参数化(self):
        from legal_api import router
        paths = [r.path for r in router.routes]
        assert paths.index("/api/v1/legal-topics/stats") < paths.index("/api/v1/legal-topics/{topic_id}")
        assert paths.index("/api/v1/legal-materials/stats") < paths.index("/api/v1/legal-materials/{material_id}")
        assert paths.index("/api/v1/legal-catalog/stats") < paths.index("/api/v1/legal-catalog/item")

    def test_页面路由已注册(self):
        from legal_api import page_router
        paths = [r.path for r in page_router.routes]
        for p in ("/legal-library", "/legal-topics", "/legal-materials"):
            assert p in paths, "缺页面路由 %s" % p

    def test_侧边栏入口存在(self):
        idx = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        for u in ("/legal-topics", "/legal-materials"):
            assert u in idx, "侧边栏缺入口 %s（孤岛页）" % u

    def test_前端不硬编码专题编号与条文(self):
        for js in ("legal_topics.js", "legal_materials.js"):
            src = (ROOT / "static" / "js" / js).read_text(encoding="utf-8")
            code = re.sub(r"/\*(?:.|\n)*?\*/", " ", src)
            code = re.sub(r"//[^\n]*", " ", code)
            assert not re.search(r"TOPIC-0\d\d", code), "%s 写死专题编号" % js
            assert not re.search(r"第[一二三四五六七八九十百]+条[，。；]", code), "%s 内嵌条文" % js

    def test_专题读层条款正文走唯一读法(self):
        src = (ROOT / "engine" / "legal_topics.py").read_text(encoding="utf-8")
        assert "LM.content_of" in src, "条款正文未走 legal_mapping.content_of（唯一读法）"

    def test_材料粒度声明为法规级(self, LE):
        d = LE.list_materials(page=1, page_size=1)
        assert d["items"], "材料列表为空"
        m = LE.material_detail(d["items"][0]["material_id"])
        assert m.get("granularity") == "law"
