# -*- coding: utf-8 -*-
"""工商信息**提供方**（Provider）—— 全部免费、无 Key、无写死代理。

已实现的提供方
--------------
1. `local_db`（`LocalDBProvider`）
   查本系统既有的账套库（`companies`）与项目库（`projects`）。
   ★ 这是**唯一 100% 可用的通道**：用户此前录过的企业信息直接复用，
     不产生任何外部请求，也不触发反爬。
2. `gsxt`（`GsxtProvider`）
   国家企业信用信息公示系统（https://www.gsxt.gov.cn）**页面抓取**：随机 UA、
   请求间随机延迟、`trust_env=False`、总量超时、字节上限。
   ★ 诚实边界：该站有验证码/滑块与频率风控，**没有免 Key 的公开 API**。
     抓不到就 `ok=False` 并给出可读原因（含风控标志命中项），
     **绝不**用猜测值/编造值填充 DTO。

★ 为什么不用第三方"工商爬虫库"
  评估过的开源项目（`gsxt_crawler` 等）均依赖**付费打码平台**或内置了不可用的
  接口签名，且多已停更（最后一次提交在 2022 年前后）。引入它们等于把
  "能不能用"绑在一个不可控的外部服务上，并且要在代码里塞 Key —— 与
  "免费 + 无硬编码 Key" 两条约束直接冲突。故按任务书的兜底方案
  （`requests` + HTML 解析）自行实现，解析器用 `lxml`（**已在 `requirements.lock`
  内**，不新增未验证依赖）。
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from engine.business_info import store as ST


@dataclass
class ProviderResult:
    provider: str = ""
    ok: bool = False
    raw: Optional[Dict[str, Any]] = None
    reason: str = ""
    elapsed_ms: int = 0
    source_detail: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"provider": self.provider, "ok": bool(self.ok),
                "reason": self.reason, "elapsed_ms": int(self.elapsed_ms),
                "source_detail": self.source_detail}


class BaseProvider:
    name = "base"

    def query(self, name: str, cfg: Dict[str, Any], deadline: float) -> ProviderResult:
        raise NotImplementedError


# ─────────────────────────── ① 本地库 ───────────────────────────
class LocalDBProvider(BaseProvider):
    """从本系统既有数据里取（免费、离线、零反爬）。"""

    name = "local_db"

    def query(self, name: str, cfg: Dict[str, Any], deadline: float) -> ProviderResult:
        t0 = time.time()
        key = ST.name_key(name)
        if not key:
            return ProviderResult(self.name, False, reason="企业名称为空",
                                  elapsed_ms=int((time.time() - t0) * 1000))
        try:
            from database import engine as _e                       # noqa: PLC0415
            from sqlalchemy import text as _text                    # noqa: PLC0415
        except Exception as exc:                                    # noqa: BLE001
            return ProviderResult(self.name, False, reason="本地库不可用：%s" % exc,
                                  elapsed_ms=int((time.time() - t0) * 1000))

        hit: Optional[Dict[str, Any]] = None
        where = ""
        with _e.connect() as conn:
            # ① 账套库（工商登记口径，字段最全）
            try:
                rows = conn.execute(_text(
                    "SELECT name, uscc, registered_capital, established_date, "
                    "legal_representative, address, business_scope, company_type "
                    "FROM companies WHERE name LIKE :p LIMIT 20"),
                    {"p": "%" + str(name).strip()[:40] + "%"}).all()
            except Exception:                                       # noqa: BLE001
                rows = []
            for r in rows:
                m = dict(r._mapping)
                if ST.name_key(m.get("name")) == key:
                    hit = {"name": m.get("name"), "tax_id": m.get("uscc"),
                           "registered_capital": m.get("registered_capital"),
                           "established_date": m.get("established_date"),
                           "legal_representative": m.get("legal_representative"),
                           "registered_address": m.get("address"),
                           "business_scope": m.get("business_scope"),
                           "company_type": m.get("company_type")}
                    where = "账套库（companies）"
                    break
            # ② 项目库（用户建项目时填的工商与稽查要素）
            if hit is None:
                try:
                    rows = conn.execute(_text(
                        "SELECT name, taxpayer_id, legal_representative, registered_capital, "
                        "established_date, registration_status, registered_address, "
                        "company_type, business_scope FROM projects "
                        "WHERE name LIKE :p LIMIT 20"),
                        {"p": "%" + str(name).strip()[:40] + "%"}).all()
                except Exception:                                   # noqa: BLE001
                    rows = []
                for r in rows:
                    m = dict(r._mapping)
                    if ST.name_key(m.get("name")) == key:
                        hit = {"name": m.get("name"), "tax_id": m.get("taxpayer_id"),
                               "legal_representative": m.get("legal_representative"),
                               "registered_capital": m.get("registered_capital"),
                               "established_date": m.get("established_date"),
                               "registration_status": m.get("registration_status"),
                               "registered_address": m.get("registered_address"),
                               "company_type": m.get("company_type"),
                               "business_scope": m.get("business_scope")}
                        where = "稽查项目库（projects）"
                        break
        ms = int((time.time() - t0) * 1000)
        if hit is None:
            return ProviderResult(self.name, False, reason="本地库无该企业（需外部通道）",
                                  elapsed_ms=ms)
        # 全部字段为空 ⇒ 等同于没有（不制造"查到了空壳"的假象）
        if not any(v not in (None, "", 0) for k, v in hit.items() if k != "name"):
            return ProviderResult(self.name, False, reason="本地库有同名记录但工商字段全空",
                                  elapsed_ms=ms)
        return ProviderResult(self.name, True, raw=hit,
                              source_detail="本地%s" % where,
                              elapsed_ms=ms)


# ─────────────────────── ② 公示系统（尽力而为） ───────────────────────
class GsxtProvider(BaseProvider):
    """国家企业信用信息公示系统页面抓取（随机 UA + 随机延迟 + 无 Key）。"""

    name = "gsxt"
    _FIELDS = (
        ("统一社会信用代码", "tax_id"), ("注册号", "tax_id"),
        ("法定代表人", "legal_representative"), ("注册资本", "registered_capital"),
        ("成立日期", "established_date"), ("登记状态", "registration_status"),
        ("住所", "registered_address"), ("注册地址", "registered_address"),
        ("企业类型", "company_type"), ("公司类型", "company_type"),
        ("经营范围", "business_scope"),
    )

    def _session(self, cfg: Dict[str, Any]):
        import requests                                             # noqa: PLC0415
        req = cfg.get("request") or {}
        s = requests.Session()
        # ★ 项目铁律：本机存在 http_proxy 时 requests 会静默走代理 ⇒ 全部失败。
        s.trust_env = bool(req.get("trust_env", False))
        uas = list(req.get("user_agents") or [])
        s.headers.update({
            "User-Agent": random.choice(uas) if uas else "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "close",
        })
        return s

    def _sleep(self, cfg: Dict[str, Any], deadline: float) -> bool:
        """请求前随机延迟（反爬礼貌间隔）。返回 False 表示会超期，直接放弃。"""
        lo, hi = (list((cfg.get("request") or {}).get("delay_ms_range") or [0, 0]) + [0, 0])[:2]
        wait = random.uniform(float(lo), float(hi)) / 1000.0
        if time.time() + wait >= deadline:
            return False
        time.sleep(wait)
        return True

    def query(self, name: str, cfg: Dict[str, Any], deadline: float) -> ProviderResult:
        t0 = time.time()
        gcfg = cfg.get("gsxt") or {}
        req = cfg.get("request") or {}
        if not gcfg.get("enabled", True):
            return ProviderResult(self.name, False, reason="公示系统通道已关闭（配置）")
        url = str(gcfg.get("search_url") or "")
        if not url:
            return ProviderResult(self.name, False, reason="未配置 search_url")
        if not self._sleep(cfg, deadline):
            return ProviderResult(self.name, False, reason="剩余时间不足，跳过外部通道",
                                  elapsed_ms=int((time.time() - t0) * 1000))
        try:
            import requests                                         # noqa: PLC0415
            import os                                               # noqa: PLC0415
        except Exception as exc:                                    # noqa: BLE001
            return ProviderResult(self.name, False, reason="requests 不可用：%s" % exc)

        sess = self._session(cfg)
        cookie = os.environ.get(str(gcfg.get("cookie_env") or "GSXT_COOKIE"), "")
        if cookie:
            # 只从环境变量读（人工过验证码后手工配置）；**不落盘、不入代码**
            sess.headers["Cookie"] = cookie
        timeout = max(1.0, min(float(req.get("provider_timeout_sec") or 7.0),
                               deadline - time.time()))
        try:
            resp = sess.get(url, timeout=timeout, params={"keyword": str(name)},
                            verify=bool(req.get("verify_tls", True)),
                            allow_redirects=True)
        except Exception as exc:                                    # noqa: BLE001
            return ProviderResult(self.name, False,
                                  reason="请求失败：%s" % type(exc).__name__,
                                  elapsed_ms=int((time.time() - t0) * 1000))
        ms = int((time.time() - t0) * 1000)
        body = resp.text if resp.content is not None else ""
        maxb = int(req.get("max_bytes") or 6291456)
        if len(body.encode("utf-8", "ignore")) > maxb:
            body = body[:maxb]

        markers = [m for m in (gcfg.get("anti_bot_markers") or []) if m and m.lower() in body.lower()]
        if resp.status_code >= 400:
            return ProviderResult(self.name, False,
                                  reason="HTTP %d" % resp.status_code, elapsed_ms=ms,
                                  extra={"markers": markers})
        if markers:
            return ProviderResult(
                self.name, False,
                reason="被公示系统风控拦截（命中：%s）⇒ 免费通道无法自动通过验证码" % "、".join(markers[:3]),
                elapsed_ms=ms, extra={"markers": markers})

        raw = self._parse(body, str(name), bool(gcfg.get("require_exact_name", True)))
        if not raw:
            return ProviderResult(
                self.name, False,
                reason="页面已返回但未解析到该企业登记信息（页面结构变化或需登录）",
                elapsed_ms=ms)
        return ProviderResult(self.name, True, raw=raw,
                              source_detail="国家企业信用信息公示系统（%s）" % url,
                              elapsed_ms=ms)

    def _parse(self, html: str, want: str, exact: bool) -> Optional[Dict[str, Any]]:
        """从页面文本里按**标签-值**配对取字段（结构无关，容错优先）。"""
        text = ""
        try:
            from lxml import html as _lh                            # noqa: PLC0415
            doc = _lh.fromstring(html)
            text = "\n".join(t.strip() for t in doc.xpath("//text()") if str(t).strip())
        except Exception:                                           # noqa: BLE001
            text = html
        if not text:
            return None
        flat = text.replace("\u00a0", " ")
        if exact and ST.name_key(want) not in ST.name_key(flat):
            return None
        raw: Dict[str, Any] = {"name": want}
        lines = [ln.strip() for ln in flat.split("\n") if ln.strip()]
        for i, ln in enumerate(lines):
            for label, field in self._FIELDS:
                if field in raw:
                    continue
                if ln == label or ln.startswith(label + "：") or ln.startswith(label + ":"):
                    val = ln.split("：", 1)[-1].split(":", 1)[-1].strip()
                    if not val and i + 1 < len(lines):
                        val = lines[i + 1].strip()
                    if val and len(val) <= 1000:
                        raw[field] = val
        # 一个业务字段都没取到 ⇒ 视为未解析（不返回只有 name 的空壳）
        if len(raw) <= 1:
            return None
        return raw


_PROVIDERS: Dict[str, BaseProvider] = {
    LocalDBProvider.name: LocalDBProvider(),
    GsxtProvider.name: GsxtProvider(),
}


def available(cfg: Dict[str, Any]) -> List[BaseProvider]:
    """按配置顺序返回可用提供方（配置是唯一顺序权威）。"""
    out: List[BaseProvider] = []
    for name in (cfg.get("providers") or []):
        p = _PROVIDERS.get(str(name))
        if p is not None:
            out.append(p)
    return out


def registry() -> Dict[str, BaseProvider]:
    return dict(_PROVIDERS)


__all__ = ["ProviderResult", "BaseProvider", "LocalDBProvider", "GsxtProvider",
           "available", "registry"]
