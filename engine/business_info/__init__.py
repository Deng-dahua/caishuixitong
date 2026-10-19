# -*- coding: utf-8 -*-
"""工商信息查询子系统（2026-10-18 新增）。

对外只暴露四件东西：
· `BusinessInfoService` / `query_company` —— 业务入口（`engine.business_info.service`）
· `channels()` —— 各通道**如实状态**（A/C 是否已配置、哪条现在真能用）
· `config()` —— 配置（唯一权威 `config/business_info.json`）
· `store` —— `sys_company_info` 落库与缓存

分层：`dto`（清洗）→ `providers`（取数）→ `store`（落库）→ `service`（编排）。
★ 通道方案（2026-10-19 用户裁定）：**A（人工 cookie 免费基线）+ C（付费 token 覆盖兜底）**；
  B（逐省适配）与 D（搜索引擎仅线索）不采用，详见配置 `channel_plan`。
★ 禁止在别处再实现"查工商信息"的取数或清洗逻辑（否则即第二套口径）。
"""
from __future__ import annotations

from engine.business_info.service import (BusinessInfoService, channels, config,
                                          query_company, reset_cache)

__all__ = ["BusinessInfoService", "query_company", "config", "reset_cache", "channels"]
