# -*- coding: utf-8 -*-
"""批量解析（H-05）守护测试。

评估结论：「10 个模块只能逐条操作」——解析页此前**只能"选一份 → 点解析"**，
102 份资料要点 102 次（而恢复后正好有 102 份待解析资料）。

判据压住四件事：
  ① **逐条独立**：一份失败不影响后续（部分失败不回滚）；
  ② **不静默截断**：超过上限必须报错，不能"以为都解析了"；
  ③ **默认不重解析已成功的**（`only_pending` 缺省 True），避免无谓重算；
  ④ **失败要带原因**，不许只回一个数字。
"""
from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import document_service as DSVC   # noqa: E402
from engine import extract_service as SVC     # noqa: E402


class _Sess:
    username = "probe"
    is_admin = True
    selected_company_id = 1

    def can_access_company(self, cid):        # noqa: ANN001
        return True


@pytest.fixture()
def fake(monkeypatch):
    """替掉取数与解析两个外部依赖，只测编排逻辑。"""
    calls = {"parsed": [], "listed": []}

    def fake_list(project_id, session, *, engine=None, parse_status=None, page=1,
                  page_size=100, sort=None, order=None):
        calls["listed"].append(parse_status)
        # ★ pending 只给 1 份 ⇒ 必须回落到 failed 才凑够 limit（这才是"两类都覆盖"的真实场景；
        #   第一版 pending 给 200 份，pending 一档就填满了，测不到回落）
        n = 1 if parse_status == "pending" else 200
        items = [{"id": 1000 + i, "parse_status": parse_status or "success"}
                 for i in range(n)]
        return {"items": items, "total": len(items), "pages": 1}

    def fake_parse(document_id, session, *, engine=None, request=None):
        calls["parsed"].append(document_id)
        if document_id == 1000:
            raise SVC.ExtractError("物理文件不存在，无法解析", 404)
        return {"tables": [1], "fields": [1, 2], "issues": [], "parse_error": ""}

    monkeypatch.setattr(DSVC, "list_documents", fake_list)
    monkeypatch.setattr(SVC, "parse_document", fake_parse)
    return calls


def test_batch_continues_after_one_failure(fake) -> None:
    """★ 核心：第 2 份失败，第 1/3 份仍必须成功（逐条独立、不回滚）。"""
    r = SVC.parse_batch(1, _Sess(), document_ids=[999, 1000, 1001])
    assert r["total"] == 3
    assert r["ok"] == 2 and r["failed"] == 1, r
    assert fake["parsed"] == [999, 1000, 1001], "失败后没有继续处理后续资料"
    bad = [x for x in r["items"] if x["status"] == "failed"][0]
    assert "物理文件不存在" in bad["message"], "失败项没带原因"


def test_batch_rejects_over_limit_instead_of_truncating() -> None:
    """★ 超过上限必须报错 —— 静默截断会让人以为全解析完了。"""
    too_many = list(range(1000, 1000 + SVC.BATCH_LIMIT + 1))
    with pytest.raises(SVC.ExtractError) as ei:
        SVC.parse_batch(1, _Sess(), document_ids=too_many)
    assert "分批" in str(ei.value.message)


def test_batch_rejects_bad_limit(fake) -> None:
    with pytest.raises(SVC.ExtractError):
        SVC.parse_batch(1, _Sess(), limit=0)
    with pytest.raises(SVC.ExtractError):
        SVC.parse_batch(1, _Sess(), limit=SVC.BATCH_LIMIT + 1)


def test_default_only_picks_pending_and_failed(fake) -> None:
    """默认不重解析已成功的：只按 pending / failed 两个状态取。"""
    SVC.parse_batch(1, _Sess(), limit=3)
    assert set(fake["listed"]) == {"pending", "failed"}, fake["listed"]


def test_all_scope_does_not_filter_status(fake) -> None:
    """选「含已解析」时不按状态筛（listed 里应出现 None）。"""
    SVC.parse_batch(1, _Sess(), only_pending=False, limit=3)
    assert fake["listed"] == [None], fake["listed"]


def test_batch_respects_limit(fake) -> None:
    r = SVC.parse_batch(1, _Sess(), limit=5)
    assert r["total"] == 5, "没有按 limit 截取"
    assert len(fake["parsed"]) == 5


def test_empty_candidates_is_explicit(fake, monkeypatch) -> None:
    """没粮时要说清楚"为什么没有"，而不是回一个 0 了事。"""
    monkeypatch.setattr(DSVC, "list_documents",
                        lambda *a, **k: {"items": [], "total": 0, "pages": 1})
    r = SVC.parse_batch(1, _Sess())
    assert r["total"] == 0
    assert "没有符合条件" in r["note"]


def test_api_registered_and_permission_required() -> None:
    """端点必须存在，且挂 `document.write` 权限（不能只靠前端隐藏）。"""
    import ast

    src = (ROOT / "extract_api.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    found = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "run_extract_batch":
            found = ast.get_source_segment(src, node) or ""
    assert found, "未找到 run_extract_batch"
    assert '_require_perm(session, "document.write")' in found, "批量解析未校验写权限"
    assert "extract-batch" in src, "路由未注册"
