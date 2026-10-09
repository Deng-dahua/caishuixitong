# -*- coding: utf-8 -*-
"""仓库根 pytest 配置。

★ 2026-10-07：此前从仓库根直接执行 `pytest`（不带路径）时，`scripts/` 与 `tools/` 下的
**一次性运维/修补脚本**（文件名恰好形如 `*_test.py`，如 `scripts/_fix_collision_and_test.py`）
会被 pytest 当作测试用例收集；这些脚本在导入期就执行源码打补丁并 assert 锚点，
一旦锚点消失即 **collection error**，导致整套测试**根本没跑**却看着像失败
（实测：`pytest -q` 1 error during collection，而 `pytest tests/ -q` 1317 passed）。

本文件把扫描范围收敛到真正的测试目录，避免"收集噪音掩盖真实用例"。
新增测试请放 `tests/`；`scripts/`、`tools/` 视为工具目录。
"""

collect_ignore_glob = [
    "scripts/*",
    "tools/*",
    "output/*",
    "reports/*",
]
