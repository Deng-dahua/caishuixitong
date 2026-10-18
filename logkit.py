# -*- coding: utf-8 -*-
"""日志唯一入口（O-01，2026-10-17）—— **不依赖 engine 包**，避免循环导入。

为什么单独放根目录
------------------
`engine/__init__.py` 导入了 context/memory/phase1… 等重量级模块，
而 `database.py` 等基础模块若 `from engine.logging_setup import ...`，
会在 `engine/__init__` 执行时形成循环导入。日志是最基础的设施，
不该被任何业务包绑住 ⇒ 放在根目录，只依赖 `runtime_storage`。

用法
----
    from logkit import get_logger
    _log = get_logger(__name__)
    _log.info("...")        # 需要格式化时用惰性参数：_log.info("x=%s", x)

★ 分级口径（迁移 print 时遵守，别一律 info）
    · 启动/迁移/正常推进      → info
    · 失败但已兜底/可继续运行  → warning
    · 真正的错误              → error（并在 except 里带 exc_info=True）
    · 高频细节（每条风险、每次循环） → debug（否则日志会被业务量淹没）
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path

try:                                              # 只依赖根模块，缺了也还能退化成纯 console
    from runtime_storage import LOG_DIR
except Exception:                                 # noqa: BLE001
    LOG_DIR = Path(os.environ.get("APP_DATA_DIR", "data")) / "logs"  # type: ignore[assignment]

_CONFIGURED = False
_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def setup(level: str | None = None) -> logging.Logger:
    """初始化根 logger（幂等）。stdout + `data/logs/app.log`（10MB × 5 轮转）。"""
    global _CONFIGURED
    root = logging.getLogger()
    if _CONFIGURED:
        return root

    lvl = (level or os.environ.get("APP_LOG_LEVEL") or "INFO").upper()
    root.setLevel(getattr(logging, lvl, logging.INFO))
    fmt = logging.Formatter(_FMT)

    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
               for h in root.handlers):
        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(fmt)
        root.addHandler(stream)

    try:
        Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            Path(LOG_DIR) / "app.log", maxBytes=10 * 1024 * 1024, backupCount=5,
            encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except Exception:                             # noqa: BLE001
        root.warning("无法创建日志文件 handler，仅输出到控制台：%s", Path(LOG_DIR) / "app.log")

    _CONFIGURED = True
    # ★ O-04（2026-10-18）：日志格式带请求关联 id（`rid`）。这样一次请求跨多个模块的
    #   日志可以用 `grep rid=ab12cd34` 串起来 —— 之前只能靠时间戳猜。
    try:
        from engine.request_context import install_log_filter   # noqa: PLC0415
        install_log_filter("%(asctime)s [%(levelname)s] [rid=%(trace_id)s] %(name)s: %(message)s")
    except Exception:                            # noqa: BLE001
        pass                                     # 装不上只影响可读性，不影响功能
    root.info("日志已初始化 level=%s file=%s", lvl, Path(LOG_DIR) / "app.log")
    return root


def get_logger(name: str) -> logging.Logger:
    """取模块 logger（**新代码统一用它，不再用 print**）。"""
    setup()
    return logging.getLogger(name)


__all__ = ["setup", "get_logger"]
