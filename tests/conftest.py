# -*- coding: utf-8 -*-
"""pytest 会话钩子：每次**全量**运行收尾时写"全量运行回执"。

## 为什么需要它（Skill D1 的权威源）

`Skill D1（文档数字一致性）` 要求"文档里写的全量 `passed` 必须等于实测值"。
但全量跑一次要 1~4 分钟，**闸门不可能每次都跑** ⇒ 采用**回执 + 过期判据**：

- 每次 `pytest tests/`（**完整范围**、非 `--collect-only`、非 `-k/-m`）结束即刷新
  `data/logs/pytest_last_run.json`；
- 回执里记下**当时 `tests/` 下所有 `.py` 的最大 mtime**；
- `engine.doc_consistency_core.authority_value()` 读回执时校验：
  · 回执不存在 ⇒ **ERROR**（不得静默通过）；
  · `tests/` 有文件比回执更新 ⇒ **ERROR「回执过期，请重跑全量」**。

⇒ 保证"文档写的 passed"永远对应**真的跑过**，且**不会静默用旧值**。

★ 安全阀：**只覆盖全量**。单文件/`-k`/`--collect-only` 的运行**不写回执**
（否则"跑了一个文件得到 32 passed"会污染全量权威）。
"""
from __future__ import annotations

import atexit
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ★★ 2026-10-12（实测根因）：**嵌套 pytest（子进程）不得写回执**。
#   缺陷：`_is_full_run()` 只看命令行参数，无法识别"我本身是被测试调起的子进程"。
#   而部分测试会 `subprocess` 跑 `pytest tests/`（如 D1 反向验证）⇒ 子进程
#   `pytest_sessionfinish` 也写回执 ⇒ **覆盖全量权威值** ⇒ 主进程后续的 D1 校验
#   读到"别的进程的 passed" ⇒ 报「文档写 X、权威值 Y」**假红**（实测一轮 12 项 ERROR）。
#   为什么以前没暴露：上一轮子进程写的 passed **恰好等于**文档值，巧合掩盖了缺陷；
#   一旦新增/删除测试改变了收集数，缺陷立刻显形。
#   修法：会话开始时若**已存在**本标记 ⇒ 我是子进程 ⇒ 本次不写回执；否则由我设置
#   标记供下级继承（`subprocess` 默认继承环境变量）。
_RECEIPT_GUARD_ENV = "PB_PYTEST_NESTED"
_IS_NESTED = bool(os.environ.get(_RECEIPT_GUARD_ENV))

# ★★ 2026-10-08（实测根因，用户"冗余"追问引出的硬证据）：**测试的回收站必须隔离**。
#   问题：`runtime_storage.TRASH_DIR` 在 import 时固化为 `<project>/data/trash`（仅当
#   未设 APP_DATA_DIR）。而 `tests/test_delete_semantics.py` / `tests/test_safe_delete.py`
#   会调用**真实的** `move_to_trash()` ⇒ 每跑一次测试就往**真实项目回收站**写文件
#   （同名则按 `<stem>.<n><suffix>` 加序号）。
#   实测证据：`data/trash/1_9_x.{1..133}.xlsx`，**序号 = 历史运行次数**；定向验证
#   `pytest tests/test_delete_semantics.py tests/test_safe_delete.py` 前后文件数
#   10365 → 10366（新增 `1_9_x.133.xlsx`），累计 10366 文件 / 244MB 无人清理。
#   修法：在 conftest **顶层**（早于所有测试模块 import）把 TRASH_DIR 重定向到 pytest
#   会话临时目录，会话结束自动清除。测试模块的 `from runtime_storage import TRASH_DIR`
#   与 `move_to_trash()` 内部引用的模块全局，都会拿到重定向后的新值。
#   注意：**只隔离回收站**，不动 `data/logs`（`pytest_last_run.json` 回执是 D1 权威源，
#   必须写真实路径），也不动 `data/cache` 等既有测试依赖的路径。
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
try:
    import runtime_storage as _rs

    _PYTEST_TRASH = Path(tempfile.mkdtemp(prefix="pytest-trash-"))
    _rs.TRASH_DIR = _PYTEST_TRASH
    atexit.register(shutil.rmtree, _PYTEST_TRASH, True)
except Exception as _exc:                       # 留痕：隔离失败必须可见（否则又回到污染真实回收站）
    print("[conftest] ⚠ 回收站隔离失败：TRASH_DIR 未重定向，测试仍会污染 data/trash —— %r"
          % (_exc,), file=sys.stderr)

RECEIPT = ROOT / "data" / "logs" / "pytest_last_run.json"
_T0 = time.time()


def _tests_max_mtime() -> float:
    d = ROOT / "tests"
    return max((p.stat().st_mtime for p in d.rglob("*.py")), default=0.0)


def _is_full_run(args) -> bool:
    """是否"覆盖 tests/ 全量"的运行（单文件 / -k / -m / --collect-only 一律不算）。"""
    args = [str(a) for a in (args or [])]
    for a in args:
        if a.startswith(("--collect-only", "--co", "-k", "-m", "--deselect", "--lf", "--ff")):
            return False
        if a.endswith(".py"):
            return False
    for a in args:
        norm = a.replace("\\", "/").rstrip("/")
        if norm in ("tests",) or norm.endswith("/tests") or norm.endswith("/tests/"):
            return True
    return False


MARKERS = ("reverse", "breaking", "lock", "plain")


def pytest_configure(config):
    """注册用例分类 marker（口径由 marker **现算**，不靠人分）。

    · `reverse`  —— 反向验证（构造不一致 ⇒ 必须报 ERROR）
    · `breaking` —— 破坏性用例（改真文件 ⇒ 必须报错，但不是 test_reverse_*）
    · `lock`     —— 口径锁（**不得报错** / 口径自证）
    · `plain`    —— 正例 / 自证
    """
    for m in MARKERS:
        config.addinivalue_line("markers", "%s: 文档一致性用例分类（D1 的判据口径权威）" % m)
    # 顶层会话设置标记，供其下起的子进程 pytest 识别"我是嵌套运行"（见文件头说明）
    if not _IS_NESTED:
        os.environ[_RECEIPT_GUARD_ENV] = "1"


def pytest_sessionfinish(session, exitstatus):        # noqa: ARG001 - pytest 钩子签名
    if _IS_NESTED:
        return                                        # ★ 嵌套运行不写回执（防污染全量权威）
    cfg = getattr(session, "config", None)
    args = list(getattr(getattr(cfg, "invocation_params", None), "args", ()) or ())
    if not _is_full_run(args):
        return
    try:
        tr = cfg.pluginmanager.getplugin("terminalreporter")
        stats = getattr(tr, "stats", {}) or {}
    except Exception:                                  # 留痕：拿不到统计就不写（宁可无回执，不写假回执）
        return

    def _n(key: str) -> int:
        return len(stats.get(key) or [])

    subtests = _n("subtests passed")
    rec = {
        "schema": 1,
        "command": "pytest " + " ".join(args),
        "passed": _n("passed"),
        "failed": _n("failed"),
        "errors": _n("error"),
        "skipped": _n("skipped"),
        "subtests": subtests,
        "collected": int(getattr(session, "testscollected", 0) or 0),
        "duration_s": round(time.time() - _T0, 2),
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tests_max_mtime": _tests_max_mtime(),
    }
    try:
        RECEIPT.parent.mkdir(parents=True, exist_ok=True)
        RECEIPT.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:                                  # 留痕：写不进去不影响测试结果
        pass
