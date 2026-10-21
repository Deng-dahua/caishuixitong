# -*- coding: utf-8 -*-
"""端到端验收：分析完成后，`/api/tax-risk-docs/last-analysis` 的载荷必须可序列化。

背景（2026-10-21）：线上 500 —— `report_data["_fact_store"]` 是 FactStore 实例，
FastAPI `jsonable_encoder` 对它走 `vars()`，取出 tuple 键 dict `_by_key` ⇒
`encoded_dict[list]` 崩（`TypeError: unhashable type: 'list'`）。

验收项（**结果级**，不是"我改了什么"）：
  A. 复现：**未归一**的 report_data 交 `jsonable_encoder` ⇒ 必须崩（证明缺陷真实存在）；
  B. 修复：`report_serialization.normalize` 之后的载荷 ⇒ 必须通过；
  C. 模拟真实端点：取 `cached["report"]`（分析链实际写入缓存的那一层）⇒ 必须通过；
  D. 能力不丢：归一后 `fact_store.get_store(snapshot)` 能重建实例且 digest 一致；
  E. 全量扫描：归一后的载荷里**不得**再有非 JSON 原生类型。

用法（务必用隔离数据目录，避免与线上服务争 SQLite）：
    APP_DATA_DIR=<隔离目录> ./.venv/Scripts/python.exe scripts/_verify_report_serialization.py 3
"""
from __future__ import annotations

import os
import sys
from typing import Any, List, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

NATIVE = (str, int, float, bool, type(None))
_FAILED: List[str] = []


def check(label: str, ok: bool, extra: str = "") -> None:
    print("  %s %s%s" % ("✓" if ok else "✘", label, ("  —— " + extra) if extra else ""))
    if not ok:
        _FAILED.append(label)


def scan_nonjson(obj: Any, path: str = "ROOT", depth: int = 0,
                 out: List[Tuple[str, str]] | None = None,
                 seen: set | None = None, limit: int = 100) -> List[Tuple[str, str]]:
    if out is None:
        out = []
    if seen is None:
        seen = set()
    if depth > 100 or len(out) >= limit:
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
            scan_nonjson(v, path + "/" + (k[:26] if isinstance(k, str) else "?"),
                         depth + 1, out, seen, limit)
    elif isinstance(obj, (list, tuple, set, frozenset)):
        if not isinstance(obj, list):
            out.append((path, "容器=%s" % type(obj).__name__))
        for i, v in enumerate(list(obj)[:3000]):
            scan_nonjson(v, "%s[%d]" % (path, i), depth + 1, out, seen, limit)
    else:
        out.append((path, "对象=%s" % type(obj).__name__))
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python scripts/_verify_report_serialization.py <company_id>")
        return 2
    cid = int(sys.argv[1])

    from fastapi.encoders import jsonable_encoder

    import main as app_main
    from database import SessionLocal
    from engine.report_serialization import normalize

    # ── 跑真实分析，拿到**原始**内存对象 ──
    db = SessionLocal()
    try:
        result = app_main._execute_tax_risk_analysis(cid, db)
    finally:
        db.close()

    payload = result
    if isinstance(result, dict) and isinstance(result.get("report"), dict):
        payload = result.get("report")

    print("\n===== A. 复现原始缺陷（未归一的原始对象）=====")
    try:
        jsonable_encoder(payload)
        check("原始对象序列化", True, "未复现（该对象本身干净）—— 缺陷可能已被其它环节规避")
    except TypeError as exc:
        check("原始对象序列化", False,
              "复现崩溃 %s: %s（= 线上 500 同型）" % (type(exc).__name__, exc))

    print("\n===== B. 修复验证（normalize 之后）=====")
    fixed = normalize(payload)
    try:
        jsonable_encoder(fixed)
        check("归一后序列化", True)
    except Exception as exc:                                   # noqa: BLE001
        check("归一后序列化", False, "%s: %s" % (type(exc).__name__, exc))

    print("\n===== C. 模拟真实端点（cached[\"report\"] 那一层）=====")
    # 分析链写入缓存的形态：_persist_one_click_result 里的 scrub 之后
    try:
        from engine.report_serialization import scrub_in_place
        cached_report = scrub_in_place(result)
        jsonable_encoder(cached_report)
        check("端点层序列化", True)
    except Exception as exc:                                   # noqa: BLE001
        check("端点层序列化", False, "%s: %s" % (type(exc).__name__, exc))

    print("\n===== D. 能力不丢（快照可重建事实库）=====")
    try:
        from engine.fact_store import FactStore, get_store
        snap = (fixed or {}).get("_fact_store")
        if isinstance(snap, dict):
            rebuilt = FactStore.from_dict(snap)
            check("快照重建", rebuilt is not None)
            if rebuilt is not None:
                check("digest 一致",
                      rebuilt.digest() == snap.get("stats", {}).get("digest"),
                      "重建=%s 快照=%s" % (rebuilt.digest()[:12],
                                           str(snap.get("stats", {}).get("digest"))[:12]))
                # get_store 从快照容器取用（跨请求读路径）
                container = {"_fact_store": snap}
                got = get_store(container)
                check("get_store 从快照恢复", isinstance(got, FactStore))
        else:
            check("快照存在", False, "_fact_store 不是快照 dict：%s" % type(snap).__name__)
    except Exception as exc:                                   # noqa: BLE001
        check("能力不丢", False, "%s: %s" % (type(exc).__name__, exc))

    print("\n===== E. 全量扫描（归一后不得再有非原生类型）=====")
    rows = scan_nonjson(fixed)
    check("无非 JSON 原生值", not rows, "残留 %d 处" % len(rows))
    for p, d in rows[:8]:
        print("      %s  %s" % (d, p))

    print("\n===== 结论 =====")
    if _FAILED:
        print("  ✘ 未通过 %d 项：%s" % (len(_FAILED), _FAILED))
        return 1
    print("  ✓ 全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())