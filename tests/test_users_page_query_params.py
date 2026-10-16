# -*- coding: utf-8 -*-
"""用户管理页：查询参数与错误提示（MQ2-D6）—— 防回退静态断言。

背景（阶段 2 S4-02 实测，阻断型 P0）：
  `static/users.html` 的 `load()` **恒拼** `&tenant_id=`（组织筛选为「全部组织」时值为空串），
  而后端 `GET /api/v1/users` 的 `tenant_id` 是 `Optional[int]`
  ⇒ FastAPI **422** ⇒ 页面「加载失败：[object Object]」、表格停在「加载中…」。
  其余页面（如 `js/risks.js`）早有 `if (v !== '' && v !== null)` 守卫 ⇒ 本页是**单点遗漏**。

修复：① 空值不拼 `tenant_id`；② `detail` 为数组（422 形态）时提取可读文本，不再输出 `[object Object]`。

本文件守：修复不被回退（含**反向验证**：把旧写法还原后断言必须被检出）。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "static" / "users.html").read_text(encoding="utf-8")


def _load_body() -> str:
    m = re.search(r"\n\s*function load\(\) \{", SRC)
    assert m, "找不到 load() 函数"
    nxt = re.search(r"\n\s*function [a-zA-Z_]+\(\)", SRC[m.end():])
    return SRC[m.start(): m.end() + (nxt.start() if nxt else len(SRC))]


def test_no_unconditional_tenant_id() -> None:
    """① 不得出现"恒拼 tenant_id"的旧写法（含 `&tenant_id=`, `tenant_id=" +` 等）。"""
    body = _load_body()
    assert '&tenant_id=' not in body, "load() 仍在恒拼 `&tenant_id=`（空串会触发后端 422）"
    assert re.search(r'tenant_id\s*=?\s*["\']?\s*\+', body) is None, \
        "load() 仍在直接拼接 tenant_id（未做空值判断）"


def test_tenant_id_only_when_present() -> None:
    """① 必须**有值才拼**（守卫形态可识别）。"""
    body = _load_body()
    assert "tenant_id" in body, "load() 完全不再传 tenant_id ⇒ 组织筛选会失效（过度修复）"
    guarded = re.search(r'if\s*\(\s*tenant\s*!==\s*""\s*&&\s*tenant\s*!==\s*null\s*\)', body) \
        or re.search(r'if\s*\(\s*\$\("f-tenant"\)\.value\s*\)', body)
    assert guarded, "load() 未见「空值不拼」守卫（应形如 `if (tenant !== \"\" && tenant !== null)`）"


def test_error_text_is_readable() -> None:
    """② 422 的 `detail` 是数组 ⇒ 必须提取可读文本，不得直拼数组（会显示 [object Object]）。"""
    assert "function errText(" in SRC, "缺少 errText 可读化辅助"
    assert "Array.isArray(d)" in SRC, "errText 未处理 FastAPI 422 的数组 detail"
    body = _load_body()
    assert "errText(" in body, "load() 未使用 errText 输出错误"


def test_reverse_old_pattern_is_detected() -> None:
    """③ **反向验证**：把旧写法塞回片段，断言①的判据能检出（证明判据有效）。"""
    old_snippet = ('var qs = "?page=" + state.page + "&page_size=" + state.size\n'
                   '      + "&tenant_id=" + encodeURIComponent($("f-tenant").value);')
    fake = 'function load() {\n' + old_snippet + '\n}\n'
    assert '&tenant_id=' in fake, "构造的旧片段不含目标特征，反向验证无效"
    assert re.search(r'tenant_id\s*=?\s*["\']?\s*\+', fake) is not None, \
        "反向验证：旧写法的特征未被判据覆盖"
