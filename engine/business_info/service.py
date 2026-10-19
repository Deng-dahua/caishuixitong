# -*- coding: utf-8 -*-
"""`BusinessInfoService` —— 工商信息查询的**业务服务**（唯一入口）。

调用链
------
`business_api.query` → `BusinessInfoService.query_company`
  ① 规范化名称 → ② 查缓存（`sys_company_info`，TTL 内直接返回，**不再发外网请求**）
  → ③ 按配置顺序调提供方（`local_db` → `gsxt`，总超时封顶）
  → ④ 清洗成 DTO（`engine.business_info.dto`）
  → ⑤ 落库并关联稽查项目
  → ⑥ 返回统一结果（成功/失败都是 200 语义，**绝不抛异常阻断项目创建**）

★ 失败语义（用户明确要求）
  「查询超时，请手动填写」+ 逐提供方原因。**不编造、不填默认值、不阻断**。
★ 缓存的意义：既是性能，也是**反爬保护**（同一企业 TTL 内只打一次外网）。
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

from engine.business_info import dto as DTO
from engine.business_info import providers as PR
from engine.business_info import store as ST

_CFG_CACHE: Dict[str, Any] = {}
_CFG_LOCK = threading.Lock()
_CFG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "config", "business_info.json")


def config() -> Dict[str, Any]:
    """读配置（进程内缓存）。★ 配置是唯一权威，代码不复制任何阈值。"""
    with _CFG_LOCK:
        if _CFG_CACHE:
            return _CFG_CACHE
        try:
            with open(_CFG_PATH, encoding="utf-8") as fh:
                _CFG_CACHE.update(json.load(fh))
        except Exception:                                        # noqa: BLE001
            _CFG_CACHE.update({})
        return _CFG_CACHE


def reset_cache() -> None:
    with _CFG_LOCK:
        _CFG_CACHE.clear()


def _now_ms(t0: float) -> int:
    return int((time.time() - t0) * 1000)


def _row_to_profile(row: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    p = DTO.CompanyProfile(
        name=str(row.get("name") or ""),
        tax_id=row.get("tax_id") or None,
        legal_representative=row.get("legal_representative") or None,
        registered_capital=row.get("registered_capital"),
        capital_unit=str(row.get("capital_unit") or "万元"),
        established_date=row.get("established_date") or None,
        registration_status=row.get("registration_status") or None,
        registered_address=row.get("registered_address") or None,
        company_type=row.get("company_type") or None,
        business_scope=row.get("business_scope") or None,
        source=str(row.get("source") or ""),
        source_detail=str(row.get("source_detail") or ""),
        confidence=DTO.to_float(row.get("confidence")),
        notes=list(row.get("notes") or []),
    )
    d = p.to_dict()
    d["fetched_at"] = row.get("fetched_at")
    d["project_id"] = row.get("project_id")
    return d


def _warning_of(profile: Dict[str, Any], cfg: Dict[str, Any]) -> Optional[str]:
    risky = list(cfg.get("risk_statuses") or [])
    st = str(profile.get("registration_status") or "")
    if DTO.is_risky_status(st, risky):
        return ("该企业登记状态为「%s」⇒ 主体资格存疑，签订合同/开票/收款均须核验，"
                "稽查期间内若有经营迹象应重点核查。" % st)
    return None


class BusinessInfoService:
    """工商信息查询服务（可注入 engine 便于测试隔离）。"""

    def __init__(self, engine: Any = None, cfg: Optional[Dict[str, Any]] = None):
        self._engine = engine
        self._cfg = cfg or config()

    # ── 只读：取缓存（供规则/前端复用，不触发外网） ──
    def cached(self, name: str) -> Optional[Dict[str, Any]]:
        row = ST.get(name, self._engine)
        if not row:
            return None
        d = _row_to_profile(row, self._cfg)
        d["age_hours"] = ST.age_hours(row)
        return d

    def query_company(self, name: Any, *, project_id: Optional[int] = None,
                      refresh: bool = False) -> Dict[str, Any]:
        t0 = time.time()
        raw_name = DTO.clean_text(name, 100) or ""
        key = ST.name_key(raw_name)
        cfg = self._cfg
        cache_cfg = cfg.get("cache") or {}
        ttl = float(cache_cfg.get("ttl_hours") or 168)
        grace = float(cache_cfg.get("grace_hours") or 720)
        fb = cfg.get("fallback") or {}

        if len(key) < 2:
            return self._fail(raw_name, "企业名称过短（至少 2 个字符）",
                              fb.get("not_found_message") or "请输入企业全称", t0,
                              code="invalid_name")

        row = ST.get(raw_name, self._engine)
        age = ST.age_hours(row) if row else None
        if row and not refresh and age is not None and age <= ttl:
            prof = _row_to_profile(row, cfg)
            return {"ok": True, "name": prof.get("name") or raw_name, "profile": prof,
                    "cache_hit": True, "stale": False,
                    "source": prof.get("source") or "cache",
                    "source_detail": prof.get("source_detail") or "",
                    "fetched_at": prof.get("fetched_at"), "age_hours": round(age, 2),
                    "elapsed_ms": _now_ms(t0), "attempts": [],
                    "message": "缓存命中（%s 内有效，未发起外网请求）" % ("%g 小时" % ttl),
                    "detail": "", "risk_status_warning": _warning_of(prof, cfg),
                    "data_quality": {"missing": prof.get("missing") or [],
                                     "notes": prof.get("notes") or []}}

        deadline = time.time() + float((cfg.get("request") or {}).get("total_timeout_sec") or 9.0)
        attempts: List[Dict[str, Any]] = []
        best: Optional[DTO.CompanyProfile] = None
        for prov in PR.available(cfg):
            if time.time() >= deadline:
                attempts.append({"provider": prov.name, "ok": False,
                                 "reason": "总超时已到，未执行", "elapsed_ms": 0,
                                 "source_detail": ""})
                continue
            try:
                res = prov.query(raw_name, cfg, deadline)
            except Exception as exc:                             # noqa: BLE001
                res = PR.ProviderResult(prov.name, False,
                                        reason="提供方异常：%s" % type(exc).__name__)
            attempts.append(res.to_dict())
            if not res.ok or not res.raw:
                continue
            prof = DTO.build_profile(res.raw, cfg=cfg, source=res.provider,
                                     source_detail=res.source_detail,
                                     confidence=0.95 if res.provider == "local_db" else 0.7)
            if not prof.name:
                prof.name = raw_name
            if not prof.name:
                continue
            # 至少要有一个**实质字段**才收（避免"查到了空壳"）
            if not any([prof.tax_id, prof.legal_representative, prof.registered_capital,
                        prof.business_scope, prof.registered_address]):
                continue
            best = prof
            break

        if best is not None:
            try:
                ST.upsert(best, project_id=project_id, engine=self._engine)
            except Exception as exc:                             # noqa: BLE001
                # 落库失败不当成查询失败（数据仍可回填表单），但必须如实告知
                best.notes.append("落库失败：%s" % type(exc).__name__)
            prof = best.to_dict()
            prof["fetched_at"] = None
            return {"ok": True, "name": best.name, "profile": prof,
                    "cache_hit": False, "stale": False,
                    "source": best.source, "source_detail": best.source_detail,
                    "fetched_at": None, "age_hours": 0.0,
                    "elapsed_ms": _now_ms(t0), "attempts": attempts,
                    "message": "已从%s取得工商信息" % (best.source_detail or best.source),
                    "detail": "" if not prof.get("notes") else "；".join(prof["notes"]),
                    "risk_status_warning": _warning_of(prof, cfg),
                    "data_quality": {"missing": prof.get("missing") or [],
                                     "notes": prof.get("notes") or []}}

        # 全部失败：若缓存里有**宽限期内**的旧数据，如实返回并标注 stale
        if row and age is not None and age <= grace:
            prof = _row_to_profile(row, cfg)
            return {"ok": True, "name": prof.get("name") or raw_name, "profile": prof,
                    "cache_hit": True, "stale": True,
                    "source": prof.get("source") or "cache",
                    "source_detail": prof.get("source_detail") or "",
                    "fetched_at": prof.get("fetched_at"), "age_hours": round(age, 2),
                    "elapsed_ms": _now_ms(t0), "attempts": attempts,
                    "message": "外网未取到新数据，展示 %s 前的缓存（已标注为陈旧）"
                               % ("%.1f 小时" % age),
                    "detail": fb.get("detail") or "",
                    "risk_status_warning": _warning_of(prof, cfg),
                    "data_quality": {"missing": prof.get("missing") or [],
                                     "notes": prof.get("notes") or []}}

        return self._fail(raw_name, "；".join(
            "%s：%s" % (a.get("provider"), a.get("reason")) for a in attempts) or "无可用通道",
            fb.get("message") or "查询超时，请手动填写", t0,
            code="unavailable", attempts=attempts, detail=fb.get("detail") or "")

    # ── 内部 ──
    def _fail(self, name: str, reason: str, message: str, t0: float, *,
              code: str = "unavailable", attempts: Optional[List[Dict[str, Any]]] = None,
              detail: str = "") -> Dict[str, Any]:
        return {"ok": False, "name": name, "profile": None, "cache_hit": False,
                "stale": False, "source": "", "source_detail": "", "fetched_at": None,
                "age_hours": None, "elapsed_ms": _now_ms(t0),
                "attempts": attempts or [], "code": code,
                "message": message, "detail": detail or reason,
                "risk_status_warning": None,
                "data_quality": {"missing": [], "notes": []}}


def _with_derived(res: Dict[str, Any]) -> Dict[str, Any]:
    """给查询结果补上**可自动填列**的派生字段（行业 / 地区），唯一实现挂载点。

    ## 为什么在这里补（而不是前端算）

    行业推断的唯一权威是 `engine.industry_resolver`（Python），地区解析的唯一权威是
    `engine.project_profile_fill.region_of`。前端如果自己再写一套正则/关键词，
    就是**第二套口径**（同一个企业可能页面上填 A、报告里写 B）—— 本仓明令禁止。

    ## 口径

      · 失败结果（`ok=False`）不补派生字段（没有工商信息可推）；
      · 每个派生项都是 `{value, source, reason}`：`reason` 说明"为什么推不出来"，
        前端据此如实显示，**不留白让人猜**；
      · 只**建议**，不改变 `profile`（调用方决定填不填）。
    """
    if not isinstance(res, dict) or not res.get("ok"):
        return res
    prof = res.get("profile") or {}
    try:
        from engine.project_profile_fill import (                    # noqa: PLC0415
            industry_from_scope, region_of)
        ind = industry_from_scope(
            company_name=str(prof.get("name") or res.get("name") or ""),
            business_scope=str(prof.get("business_scope") or ""),
            registered_industry="",
            sales_goods=[],
        )
        reg = region_of(address=str(prof.get("registered_address") or ""),
                        company_name=str(prof.get("name") or res.get("name") or ""),
                        uscc=str(prof.get("tax_id") or ""))
        res["derived"] = {"industry": ind, "region": reg}
    except Exception as exc:                                          # noqa: BLE001
        # 派生失败不得让整次查询失败（工商信息本身是有效的）
        res["derived"] = {"industry": {"value": "", "source": "",
                                       "reason": "行业推导不可用：%s" % exc},
                          "region": {"value": "", "source": "",
                                     "reason": "地区推导不可用：%s" % exc}}
    return res


def query_company(name: Any, *, project_id: Optional[int] = None,
                  refresh: bool = False, engine: Any = None) -> Dict[str, Any]:
    """模块级便捷入口（供 API 与规则复用）。

    ★ 派生字段（行业/地区）在此**统一挂载**（`_with_derived`）——
      所有调用方（HTTP 接口、规则、脚本）一次到位，不必各自补一遍。
    """
    res = BusinessInfoService(engine=engine).query_company(
        name, project_id=project_id, refresh=refresh)
    return _with_derived(res)


__all__ = ["BusinessInfoService", "query_company", "config", "reset_cache"]
