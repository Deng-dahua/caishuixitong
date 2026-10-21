# -*- coding: utf-8 -*-
"""报告对象的 **JSON 原生化**（内存 → 可安全交给 FastAPI/落盘的形态）。

## 为什么必须有它（2026-10-21 线上 500 根因）

`GET /api/tax-risk-docs/last-analysis?company_id=3` 返回 **500**：

    TypeError: unhashable type: 'list'
    fastapi/encoders.py:297   encoded_dict[encoded_key] = encoded_value

链路：`_execute_tax_risk_analysis` 产出 `report_data` → 挂 `report_data["_fact_store"]
= FactStore 实例 → `_persist_one_click_result` 把它**原样**放进内存缓存
`_last_analysis_cache[company_id]["report"]` → 接口 `return cached["report"]`
→ FastAPI `jsonable_encoder` 对非 dict/list 对象走 `vars(obj)` 分支，取出
`FactStore._by_key`（`Dict[Tuple[str,str,str], ...]`）→ `jsonable_encoder(key)`
把 **tuple 键转成 list** → `encoded_dict[list]` 崩。

**为什么磁盘缓存看起来正常（假象）**：落盘走 `runtime_storage._to_json_safe`，
它对非原生类型 `return str(value)`，把实例洗成 `"<FactStore object at 0x...>"`；
只有**进程内原始对象**才带实例 ⇒ **分析完成后不重启，该接口必崩**；
重启后从磁盘回填缓存就"自愈"了 —— 这正是本缺陷长期未被发现的原因。

## 修法口径（单一权威）

`normalize(value)` 把任意对象转成 **JSON 原生**（dict/list/str/int/float/bool/None）：

  1. **dict**：键一律 `str()`（tuple/set 作键是 Python 允许但 JSON 不允许的形态）；
  2. **list/tuple/set/frozenset**：转 list（`set` 排序以保证**稳定输出**，便于比对）；
  3. **datetime/date/time**：转 ISO 字符串（**不**用 `str()`，避免 locale 差异）；
  4. **自定义对象**：优先调它的 `to_dict()`（如 `FactStore.to_dict`），
     否则 `vars()`，再否则 `str()` —— **绝不抛异常**；
  5. **循环引用**：按 `id()` 检测，回指替换为 `"<circular reference>"`。

与既有实现的关系（**不得各写一份**）：
  · `runtime_storage._to_json_safe` 只管**落盘**，且对非原生类型直接 `str(value)`
    （会丢信息，如把 FactStore 洗成对象地址字符串）——**落盘用**，本项目保留；
  · 本模块是**出口归一**（面向 FastAPI 响应 / 内存缓存），要求"保信息 + 稳定"。
    两者口径不同故并存，但**响应路径必须统一走本模块**。

## 用法

    from engine.report_serialization import normalize
    cached["report"] = normalize(report_data)      # 写入缓存前归一（覆盖所有读取端）

或者就地归一（保留原对象引用，逐层替换非原生值）：

    scrub_in_place(report_data)
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any, Dict, List, Set

__all__ = ["normalize", "scrub_in_place", "CIRCULAR_MARKER"]

#: 循环引用占位符（与 `runtime_storage._to_json_safe` 同名同形，便于两侧一致判读）
CIRCULAR_MARKER = "<circular reference>"

#: JSON 原生标量
_SCALARS = (str, int, float, bool, type(None))


def _obj_to_dict(value: Any) -> Dict[str, Any] | None:
    """自定义对象 → dict。优先 `to_dict()`（本仓约定），其次 `vars()`；取不到返回 None。"""
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            got = to_dict()
            if isinstance(got, dict):
                return got
        except Exception:                     # noqa: BLE001 —— 兜底不外抛
            pass
    try:
        attrs = vars(value)
    except TypeError:
        return None
    return attrs if isinstance(attrs, dict) else None


def normalize(value: Any, _seen: Set[int] | None = None) -> Any:
    """把任意对象转成 **JSON 原生**结构（可安全 `json.dumps` / 交 FastAPI）。

    不抛异常：任何无法处理的类型最终退回 `str(value)`。
    """
    if _seen is None:
        _seen = set()
    if isinstance(value, _SCALARS):
        return value
    # datetime 家族：ISO 字符串（先于自定义对象分支，因为 date 无 __dict__）
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        try:
            return value.isoformat()
        except Exception:                     # noqa: BLE001
            return str(value)
    if isinstance(value, Path):
        return str(value)

    vid = id(value)
    if vid in _seen:
        return CIRCULAR_MARKER

    if isinstance(value, dict):
        _seen.add(vid)
        try:
            out: Dict[str, Any] = {}
            for k, v in value.items():
                # ★ 键一律字符串化 —— 这是本次 500 的直接修因（杜绝 list/tuple 键）
                ks = k if isinstance(k, str) else str(k)
                out[ks] = normalize(v, _seen)
            return out
        finally:
            _seen.discard(vid)

    if isinstance(value, (list, tuple)):
        _seen.add(vid)
        try:
            return [normalize(v, _seen) for v in value]
        finally:
            _seen.discard(vid)

    if isinstance(value, (set, frozenset)):
        _seen.add(vid)
        try:
            # 排序保证**稳定输出**（同一份数据两次归一结果一致，便于比对与测试）
            try:
                items: List[Any] = sorted(value, key=lambda x: (type(x).__name__, str(x)))
            except Exception:                 # noqa: BLE001
                items = list(value)
            return [normalize(v, _seen) for v in items]
        finally:
            _seen.discard(vid)

    # 自定义对象：优先 to_dict()，其次 vars()，最后 str()
    as_dict = _obj_to_dict(value)
    if as_dict is not None:
        _seen.add(vid)
        try:
            return normalize(as_dict, _seen)
        finally:
            _seen.discard(vid)
    try:
        return str(value)
    except Exception:                         # noqa: BLE001
        return "<unserializable>"


def scrub_in_place(value: Any, _seen: Set[int] | None = None) -> Any:
    """**就地**把容器内的非原生值替换掉（尽量保留原对象引用，减小内存翻倍）。

    与 `normalize` 的差别：`normalize` 返回新结构；本函数改写入参容器本身。
    主要用于"报告已生成、只想在出口前把杂质洗掉"的场景。

    标量一律原样返回；dict/list **原地改写后返回自身**；tuple/set/自定义对象
    无法原地改写 ⇒ 返回 `normalize` 后的**新对象**（调用方须接收返回值）。
    """
    if _seen is None:
        _seen = set()
    if isinstance(value, _SCALARS):
        return value
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        try:
            return value.isoformat()
        except Exception:                     # noqa: BLE001
            return str(value)
    vid = id(value)
    if vid in _seen:
        return CIRCULAR_MARKER
    if isinstance(value, dict):
        _seen.add(vid)
        try:
            for k in list(value.keys()):
                if not isinstance(k, str):
                    # 非串键必须重建条目（dict 的键不能"就地改名"）
                    nk = str(k)
                    nv = scrub_in_place(value.pop(k), _seen)
                    value[nk] = nv
                    continue
                value[k] = scrub_in_place(value[k], _seen)
            return value
        finally:
            _seen.discard(vid)
    if isinstance(value, list):
        _seen.add(vid)
        try:
            for i, v in enumerate(value):
                value[i] = scrub_in_place(v, _seen)
            return value
        finally:
            _seen.discard(vid)
    # tuple / set / 自定义对象：无法原地改 ⇒ 交 normalize 出新对象
    return normalize(value, _seen)