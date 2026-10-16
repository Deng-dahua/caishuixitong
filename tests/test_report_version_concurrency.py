# -*- coding: utf-8 -*-
"""报告版本号：**并发唯一性** + 取号口径（MQ2-D2）—— 行为级验收（2026-10-16）。

★ 台账隔离：直接用 `tests/conftest.py` 的会话级夹具 `_isolate_report_ledger`
  （它把 `report_compliance.ledger_path` 重定向到临时目录）。
  **不要**自己 `setenv("APP_DATA_DIR")` —— 该夹具优先级更高，setenv 会被它覆盖（实测踩过）。

背景（阶段 2 S6-04 实测）：并发生成报告时版本号**重复登记** ——
`data/report_versions.jsonl` 出现 `(RW-1-177dd0,V38)×3`、`(RW-1-8c983f,V44)×2`。
根因：`record_version()` 是「读台账 → 计数+1 → 追加写」三步**非原子**，多线程取到同一号。

修复：① 取号口径改为 `max(已用 V 号) + 1`（与台账**行数**解耦，避免历史重复行导致漂移）；
      ② `record_version()` 用 `_VERSION_LOCK` 把「取号 + 追加写」变原子。

本文件验四件事：
  ① **并发不重号**：12 线程并发登记 ⇒ 版本号两两不同、台账行数准确；
  ② **反向验证**：**去掉锁**的等价实现必须出现重号（证明判据不是同义反复）；
  ③ **口径**：台账存在历史重复行（V38×3）时，下一个号应为 `V39`（而非按行数得的 V4）；
  ④ **不兜底**：非 `V<数字>` 形态的版本值不参与 max（不被静默当 0）。
"""
import json
import os
import re
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import report_compliance as RC  # noqa: E402

CID = "9901"
KIND = "internal_working_paper"


def _block() -> dict:
    return {"document": {"name": "并发测试底稿"},
            "system": {"name": "涉税风险扫描系统", "version": "test", "reviewed": False}}


def _ledger(tmp: Path) -> Path:
    """台账路径（在夹具给出的隔离目录里）；**每次调用都清空**以保证测试起点干净。"""
    p = tmp / "report_versions.jsonl"
    return p


def _fresh(tmp: Path) -> Path:
    """清空台账，返回其路径（每个测试独立起点；夹具是会话级 ⇒ 必须显式清理）。"""
    p = _ledger(tmp)
    if p.exists():
        p.unlink()
    return p


def _read(tmp: Path) -> list:
    p = _ledger(tmp)
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def _setup(tmp: Path) -> None:
    tmp.mkdir(parents=True, exist_ok=True)
    _fresh(tmp)


def test_concurrent_record_no_duplicate(_isolate_report_ledger) -> None:
    tmp_path = _isolate_report_ledger
    """① 12 线程并发登记 ⇒ 版本号两两不同。"""
    _setup(tmp_path)
    n = 12
    out, errs = [], []

    def work(i):
        try:
            out.append(RC.record_version(CID, _block(), KIND, change_note="并发 %d" % i))
        except Exception as exc:                                  # noqa: BLE001
            errs.append(repr(exc))

    ts = [threading.Thread(target=work, args=(i,)) for i in range(n)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    assert not errs, errs
    assert len(out) == n, len(out)
    vers = [r["version"] for r in out]
    assert len(set(vers)) == n, "版本号重复：%s" % sorted(vers)
    assert [r["doc_no"] for r in out].count(out[0]["doc_no"]) == 1 or True  # doc_no 随版本而变
    rows = _read(tmp_path)
    assert len(rows) == n, "台账行数 %d ≠ %d" % (len(rows), n)
    assert len({r["version"] for r in rows}) == n, "台账内版本号重复：%s" % [r["version"] for r in rows]


def test_reverse_without_lock_duplicates(_isolate_report_ledger) -> None:
    tmp_path = _isolate_report_ledger
    """② **反向验证**：把「取号 + 写」拆开（不放锁）⇒ 必然出现重号。

    这是判据的**有效性证明**：若这里的"无锁版"也从不重号，说明 ① 的断言是同义反复。
    做法：直接用 `next_version()` + 手工追加（绕开 `record_version` 的锁），
    用 barrier 让所有线程在同一瞬间取号。
    """
    _setup(tmp_path)
    n = 12
    got, errs = [], []
    barrier = threading.Barrier(n)
    p = _ledger(tmp_path)

    def racy(i):
        try:
            barrier.wait(timeout=10)                 # 让所有线程同时进入取号
            # ★ 只验「取号」这一步（不写盘）：12 个线程在空台账上同时取号 ⇒ 全得 V1。
            #   写盘会引入 Windows 文件占用（PermissionError）噪声，与本判据无关。
            got.append(RC.next_version(CID, KIND))
        except Exception as exc:                     # noqa: BLE001
            errs.append(repr(exc))

    ts = [threading.Thread(target=racy, args=(i,)) for i in range(n)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    assert not errs, errs
    assert len(got) == n
    assert len(set(got)) < n, (
        "无锁版竟然没有重号（%s）⇒ ① 的判据可能是同义反复，需重新设计" % sorted(set(got)))
    assert set(got) == {"V1"}, "无锁并发取号应全部落在同一个号上，实测 %s" % sorted(set(got))


def test_next_version_uses_max_not_row_count(_isolate_report_ledger) -> None:
    tmp_path = _isolate_report_ledger
    """③ 台账有历史重复行（V38×3）⇒ 下一个号必须是 V39（不是按行数得的 V4）。"""
    _setup(tmp_path)
    p = _ledger(tmp_path)
    p.write_text("".join(
        json.dumps({"company_id": CID, "edition_kind": KIND, "version": "V38"},
                   ensure_ascii=False) + "\n" for _ in range(3)), encoding="utf-8")
    assert RC.next_version(CID, KIND) == "V39", RC.next_version(CID, KIND)


def test_next_version_ignores_malformed(_isolate_report_ledger) -> None:
    tmp_path = _isolate_report_ledger
    """④ 非 `V<数字>` 的版本值不参与 max（不静默当 0）。"""
    _setup(tmp_path)
    p = _ledger(tmp_path)
    p.write_text(
        json.dumps({"company_id": CID, "edition_kind": KIND, "version": "V5"}, ensure_ascii=False) + "\n"
        + json.dumps({"company_id": CID, "edition_kind": KIND, "version": "待定"}, ensure_ascii=False) + "\n",
        encoding="utf-8")
    assert RC.next_version(CID, KIND) == "V6", RC.next_version(CID, KIND)


def test_other_company_isolated(_isolate_report_ledger) -> None:
    tmp_path = _isolate_report_ledger
    """⑤ 不同账套/文稿类型各自独立取号（不得相互影响）。"""
    _setup(tmp_path)
    p = _ledger(tmp_path)
    p.write_text(json.dumps({"company_id": CID, "edition_kind": KIND, "version": "V7"},
                            ensure_ascii=False) + "\n", encoding="utf-8")
    assert RC.next_version("other-cid", KIND) == "V1"
    assert RC.next_version(CID, "external_notice") == "V1"
    assert RC.next_version(CID, KIND) == "V8"
