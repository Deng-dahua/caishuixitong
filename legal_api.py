# -*- coding: utf-8 -*-
"""法规库 HTTP 接口（P2-1）。

路径前缀 `/api/v1`（**新增**端点专用；既有法规引用链路一字未改）。

| 端点 | 说明 |
|---|---|
| `GET /api/v1/legal-library/meta` | 字典（数据来源文件 / 版本状态枚举 / 覆盖口径） |
| `GET /api/v1/legal-library/stats` | 统计（条数/法数/来源分布/版本状态分布/覆盖率） |
| `GET /api/v1/legal-library/laws` | 法清单（条数 + 版本状态） |
| `GET /api/v1/legal-library` | 正文条目检索（法名/条款号/正文关键词 + 分页） |
| `GET /api/v1/legal-library/{law}` | 单部法详情（全部条目 + 版本登记 + 版本括注） |
| `GET /legal-library`（页面） | 法规库浏览/检索页 |

★ 路由顺序铁律：字面量段（`meta`/`stats`/`laws`）必须注册在参数化段（`{law}`）**之前**，
  否则会被路径参数吃掉 ⇒ 静默 404。本模块的注册顺序即以此为准（闸门 `check_legal_library_wiring` 断言）。
★ 权限：`legal.view`（唯一权威 `engine.rbac.rbac_allows`）。
★ 法规库**不硬编码条文**：全部条文来自数据文件，本模块只做透出（见 `engine.legal_library`）。
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from engine import legal_library as LIB

router = APIRouter(prefix="/api/v1", tags=["法规库（P2-1）"])
page_router = APIRouter(tags=["法规库（页面）"])

_ROOT = os.path.dirname(os.path.abspath(__file__))


def _request_perm(request: Request, perm: str):
    auth = getattr(request.state, "auth", None)
    if auth is None:
        raise HTTPException(status_code=401, detail="未登录")
    from engine.rbac import rbac_allows                      # noqa: PLC0415
    if not rbac_allows(auth, perm):
        raise HTTPException(status_code=403, detail="缺少权限：%s" % perm)
    return auth


def _serve_static(name: str) -> str:
    """读 `static/` 下的页面（无服务端模板）。**编码回退链唯一实现**（三处页面共用）。

    ★ 为什么要有回退链：Windows 上手工编辑过的 HTML 可能是 GBK/GB18030 或带 BOM，
      单一 `utf-8` 打开会抛 `UnicodeDecodeError` ⇒ 页面 500。早前 `legal_library_page`
      内联了这段逻辑，新增两页若各抄一份即三份实现（易漂移）⇒ 抽为本函数。
    """
    path = os.path.join(_ROOT, "static", name)
    for enc in ("utf-8-sig", "gbk", "gb18030", "utf-8"):
        try:
            with open(path, "r", encoding=enc) as fh:
                return fh.read()
        except (UnicodeDecodeError, LookupError):
            continue
    return "<h1>Encoding error</h1>"


# ── 字面量段（必须在前）────────────────────────────────────────────────────
@router.get("/legal-library/meta", summary="法规库字典（来源文件 / 状态枚举 / 覆盖口径）")
def legal_library_meta(request: Request) -> Dict[str, Any]:
    _request_perm(request, "legal.view")
    return LIB.metadata()


@router.get("/legal-library/stats", summary="法规库统计（条数/法数/来源/版本状态/覆盖率）")
def legal_library_stats(request: Request) -> Dict[str, Any]:
    _request_perm(request, "legal.view")
    return LIB.stats()


@router.get("/legal-library/laws", summary="法清单（条数 + 版本状态）")
def legal_library_laws(request: Request, q: Optional[str] = None) -> Dict[str, Any]:
    _request_perm(request, "legal.view")
    return LIB.laws(q=q)


@router.get("/legal-library", summary="正文条目检索（关键词 + 分页）")
def legal_library_entries(request: Request,
                          q: Optional[str] = None,
                          law: Optional[str] = None,
                          only_current: bool = Query(False),
                          page: int = Query(1),
                          page_size: int = Query(50)) -> Dict[str, Any]:
    _request_perm(request, "legal.view")
    return LIB.article_entries(q=q, law=law, only_current=bool(only_current),
                       limit=max(1, min(int(page_size or 50), 200)),
                       offset=max(1, int(page or 1)))


# ── 参数化段（必须在后）────────────────────────────────────────────────────
@router.get("/legal-library/{law}", summary="单部法详情（条目 + 版本登记 + 版本括注）")
def legal_library_law(law: str, request: Request):
    _request_perm(request, "legal.view")
    item = LIB.law_detail(law)
    if item is None:
        raise HTTPException(status_code=404, detail="法规库中无此法：%s" % law)
    return item


@page_router.get("/legal-library", response_class=HTMLResponse, include_in_schema=False)
def legal_library_page():
    """法规库浏览页（静态 HTML，无服务端模板）。"""
    return _serve_static("legal_library.html")


# ══════════════════════════════════════════════════════════════════════════
# 专题 / 目录 / 关系 / 材料 / 条款（STEP-EXT-LEGAL-FULL-MATCH 步骤 22）
# ── 全部**只读薄转发**到读层（engine/legal_topics、legal_catalog、legal_extras、
#    legal_mapping），本模块不做任何统计计算、不硬编码任何条数或条文。
# ── 路由顺序铁律同 P2-1：同前缀内**字面量段必须先于参数化段**注册，
#    否则会被路径参数吃掉 ⇒ 静默 404。故本段内 `/{id}` 一律排在最后。
# ══════════════════════════════════════════════════════════════════════════

# ── 专题：字面量段 ──
@router.get("/legal-topics", summary="专题列表（20 个：P0/P1/P2；含各专题统计）")
def legal_topics(request: Request, batch: str = Query(""), status: str = Query(""),
                 q: str = Query("")):
    _request_perm(request, "legal.view")
    from engine import legal_topics as TP                          # noqa: PLC0415
    return TP.list_topics(batch=batch, status=status, q=q)


@router.get("/legal-topics/stats", summary="专题索引统计（源文件/口径如实）")
def legal_topics_stats(request: Request):
    _request_perm(request, "legal.view")
    from engine import legal_topics as TP                          # noqa: PLC0415
    return TP.stats()


# ── 目录 / 关系 / 材料 的**字面量段**（必须各自先于同前缀的参数化段）──
@router.get("/legal-catalog", summary="法规目录（三源全量元数据；筛选+关键词+分页）")
def legal_catalog_list(request: Request, kind: str = Query(""), source: str = Query(""),
                       q: str = Query(""), year: str = Query(""),
                       with_body: str = Query(""),
                       page: int = Query(1), page_size: int = Query(50)):
    _request_perm(request, "legal.view")
    from engine import legal_catalog as CAT                        # noqa: PLC0415
    return CAT.list_documents(kind=kind, source=source, q=q, year=year,
                              with_body=with_body or None,
                              page=page, page_size=page_size)


@router.get("/legal-catalog/stats", summary="法规目录统计（条数/类型/来源/关系数）")
def legal_catalog_stats(request: Request):
    _request_perm(request, "legal.view")
    from engine import legal_catalog as CAT                        # noqa: PLC0415
    return CAT.stats()


@router.get("/legal-catalog/item", summary="单条目录详情（按 index 或 url）+ 关系链")
def legal_catalog_item(request: Request, index: Optional[int] = Query(None),
                       url: str = Query("")):
    _request_perm(request, "legal.view")
    from engine import legal_catalog as CAT                        # noqa: PLC0415
    if index is None and not url:
        raise HTTPException(status_code=400, detail="须给 index 或 url 之一")
    return CAT.document(index, url=url or None)


@router.get("/legal-relations", summary="法规关系检索（amended/abolished/cited_by/related）")
def legal_relations(request: Request, relation: str = Query(""), q: str = Query(""),
                    page: int = Query(1), page_size: int = Query(50)):
    _request_perm(request, "legal.view")
    from engine import legal_catalog as CAT                        # noqa: PLC0415
    return CAT.relations(relation=relation, q=q, page=page, page_size=page_size)


@router.get("/legal-relations/lookup", summary="按法规查关系链（标题或文号）")
def legal_relations_lookup(request: Request, title: str = Query(""), doc_no: str = Query("")):
    _request_perm(request, "legal.view")
    from engine import legal_catalog as CAT                        # noqa: PLC0415
    if not title and not doc_no:
        raise HTTPException(status_code=400, detail="须给 title 或 doc_no 之一")
    return CAT.relations_of(title=title or None, doc_no=doc_no or None)


@router.get("/legal-materials", summary="案例/解读/问答材料列表（类型/关键词/关联法筛选）")
def legal_materials(request: Request, kind: str = Query(""), q: str = Query(""),
                    law_code: str = Query(""), linked: str = Query(""),
                    page: int = Query(1), page_size: int = Query(20),
                    with_snippet: bool = Query(True)):
    _request_perm(request, "legal.view")
    from engine import legal_extras as EX                          # noqa: PLC0415
    return EX.list_materials(kind=kind, q=q, law_code=law_code,
                             linked=linked or None, page=page,
                             page_size=page_size, with_snippet=with_snippet)


@router.get("/legal-materials/stats", summary="材料统计（类型分布/关联法数）")
def legal_materials_stats(request: Request):
    _request_perm(request, "legal.view")
    from engine import legal_extras as EX                          # noqa: PLC0415
    return EX.stats()


# ── 参数化段（必须排在各自前缀的字面量段之后）──
@router.get("/legal-topics/{topic_id}", summary="专题详情（统计 + 归属清单）")
def legal_topic_detail(topic_id: str, request: Request):
    _request_perm(request, "legal.view")
    from engine import legal_topics as TP                          # noqa: PLC0415
    d = TP.topic_detail(topic_id)
    if d.get("found") is False:
        raise HTTPException(status_code=404, detail="无此专题：%s" % topic_id)
    return d


@router.get("/legal-topics/{topic_id}/documents",
            summary="专题法规清单（分层 + 类型筛选 + 分页）")
def legal_topic_documents(topic_id: str, request: Request, kind: str = Query(""),
                          q: str = Query(""), page: int = Query(1),
                          page_size: int = Query(50)):
    _request_perm(request, "legal.view")
    from engine import legal_topics as TP                          # noqa: PLC0415
    d = TP.topic_documents(topic_id, kind=kind, q=q, page=page, page_size=page_size)
    if d.get("found") is False:
        raise HTTPException(status_code=404, detail="无此专题：%s" % topic_id)
    return d


@router.get("/legal-topics/{topic_id}/rules", summary="专题规则清单（含已确证条款数）")
def legal_topic_rules(topic_id: str, request: Request):
    _request_perm(request, "legal.view")
    from engine import legal_topics as TP                          # noqa: PLC0415
    d = TP.topic_rules(topic_id)
    if d.get("found") is False:
        raise HTTPException(status_code=404, detail="无此专题：%s" % topic_id)
    return d


@router.get("/legal-topics/{topic_id}/provisions", summary="专题已核实条款（含正文 + 反查规则）")
def legal_topic_provisions(topic_id: str, request: Request):
    _request_perm(request, "legal.view")
    from engine import legal_topics as TP                          # noqa: PLC0415
    d = TP.topic_provisions(topic_id)
    if d.get("found") is False:
        raise HTTPException(status_code=404, detail="无此专题：%s" % topic_id)
    return d


@router.get("/legal-topics/{topic_id}/materials", summary="专题相关官方材料（按法分列）")
def legal_topic_materials(topic_id: str, request: Request, law_code: str = Query(""),
                          limit: int = Query(20), offset: int = Query(0)):
    _request_perm(request, "legal.view")
    from engine import legal_topics as TP                          # noqa: PLC0415
    d = TP.topic_materials(topic_id, law_code=law_code, limit=limit, offset=offset)
    if d.get("found") is False:
        raise HTTPException(status_code=404, detail="无此专题：%s" % topic_id)
    return d


@router.get("/legal-materials/{material_id}", summary="材料详情（关联法规 + 引用该法的规则）")
def legal_material_detail(material_id: str, request: Request):
    _request_perm(request, "legal.view")
    from engine import legal_extras as EX                          # noqa: PLC0415
    d = EX.material_detail(material_id)
    if d.get("found") is False:
        raise HTTPException(status_code=404, detail="无此材料：%s" % material_id)
    return d


@router.get("/legal-provisions/{provision_id}", summary="条款详情（正文 + 引用该条款的规则）")
def legal_provision_detail(provision_id: str, request: Request):
    _request_perm(request, "legal.view")
    from engine import legal_mapping as LM                         # noqa: PLC0415
    meta = LM.provision_index().get(provision_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="条款索引中无此条款：%s" % provision_id)
    got = LM.content_of(provision_id)
    return {
        "provision_id": provision_id,
        "law": meta.get("law"), "law_code": meta.get("law_code"),
        "article": meta.get("article"), "kind": meta.get("kind"),
        "topic_tags": meta.get("topic_tags") or [],
        "content": got.get("content") or "", "has_content": bool(got.get("has_content")),
        "content_source": got.get("content_source", ""),
        "related_rules": LM.rules_of(provision_id),
        "note": ("正文来自 `static/legal_library.json`（唯一录入权威）；"
                 "`related_rules` 是引用该条款的规则（关联表反查）。"),
    }


@page_router.get("/legal-topics", response_class=HTMLResponse, include_in_schema=False)
def legal_topics_page():
    """法规专题页（静态 HTML，无服务端模板）。"""
    return _serve_static("legal_topics.html")


@page_router.get("/legal-materials", response_class=HTMLResponse, include_in_schema=False)
def legal_materials_page():
    """法规材料页（案例/解读/问答）—— 静态 HTML。"""
    return _serve_static("legal_materials.html")


__all__ = ["router", "page_router"]
