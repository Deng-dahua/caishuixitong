# -*- coding: utf-8 -*-
"""日志配置（O-01）—— **实现已下沉到根目录 `logkit.py`**，本文件只做转发。

★ 为什么要下沉：`engine/__init__.py` 会导入 context/memory/phase1 等重量级模块，
  而 `database.py` 这类基础模块如果 `from engine.logging_setup import ...`，
  就会在 `engine/__init__` 执行期间形成循环导入。
  日志是最基础的设施，**不该被业务包绑住** ⇒ 实现放根目录 `logkit`，
  这里保留同签名转发，既有调用点（`main.py` 启动时）不用改。

新代码请直接用：

    from logkit import get_logger
    _log = get_logger(__name__)
"""
from __future__ import annotations

from logkit import get_logger, setup

__all__ = ["setup", "get_logger"]
