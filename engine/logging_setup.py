# -*- coding: utf-8 -*-
"""统一日志配置（O-01，2026-10-17）。

评估结论：「产品代码 **print 412 次、logger 仅 6 次** —— 无级别、无结构、不可采集；
线上排障只能翻 stdout」。

本模块先解决**基础设施**（这一步风险最低、收益最直接）：
  · 一处配置 root logger：同时输出到 stdout 与 `data/logs/app.log`（按大小轮转）；
  · 统一格式（时间/级别/模块/消息），级别由 `APP_LOG_LEVEL` 控制；
  · 提供 `get_logger(name)`，新代码一律用它（**不要再用 print**）。

★ 为什么不一上来就把 412 处 print 全改掉：
  那会同时改动几十个业务文件的执行路径，风险远大于收益。正确顺序是
  ① 先把 logger 落地（本模块）→ ② 新代码只用 logger → ③ 按模块分批迁移 print。
  当前状态：① 已完成；② 本模块与 backup/consent/metrics/trash 已用；③ 待分批。
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys

from runtime_storage import LOG_DIR

_CONFIGURED = False
_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def setup(level: str | None = None) -> logging.Logger:
    """初始化根 logger（幂等，可重复调用）。返回根 logger。"""
    global _CONFIGURED
    root = logging.getLogger()
    if _CONFIGURED:
        return root

    lvl = (level or os.environ.get("APP_LOG_LEVEL") or "INFO").upper()
    root.setLevel(getattr(logging, lvl, logging.INFO))

    fmt = logging.Formatter(_FMT)

    # ① 控制台（保留既有"看窗口就知道在跑什么"的习惯）
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    root.addHandler(stream)

    # ② 文件（轮转：单文件 10 MB × 5 份 ≈ 50 MB 上限，避免日志把磁盘写满）
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            LOG_DIR / "app.log", maxBytes=10 * 1024 * 1024, backupCount=5,
            encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except Exception:                                  # noqa: BLE001
        # 日志文件写不了不能阻断启动（只影响可观测性，不影响业务）
        root.warning("无法创建日志文件 handler，仅输出到控制台：%s", LOG_DIR / "app.log")

    _CONFIGURED = True
    root.info("日志已初始化 level=%s file=%s", lvl, LOG_DIR / "app.log")
    return root


def get_logger(name: str) -> logging.Logger:
    """取模块 logger（**新代码统一用它，不用 print**）。"""
    setup()
    return logging.getLogger(name)


__all__ = ["setup", "get_logger"]
