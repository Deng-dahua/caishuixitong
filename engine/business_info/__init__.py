# -*- coding: utf-8 -*-
"""工商信息查询子系统（2026-10-18 新增）。

对外只暴露三件东西：
· `BusinessInfoService` / `query_company` —— 业务入口（`engine.business_info.service`）
· `config()` —— 配置（唯一权威 `config/business_info.json`）
· `store` —— `sys_company_info` 落库与缓存

分层：`dto`（清洗）→ `providers`（取数）→ `store`（落库）→ `service`（编排）。
★ 禁止在别处再实现"查工商信息"的取数或清洗逻辑（否则即第二套口径）。
"""
from __future__ import annotations

from engine.business_info.service import (BusinessInfoService, config,
                                          query_company, reset_cache)

__all__ = ["BusinessInfoService", "query_company", "config", "reset_cache"]
