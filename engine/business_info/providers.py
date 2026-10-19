# -*- coding: utf-8 -*-
"""工商信息**提供方**（Provider）—— 通道方案 **A + C**（用户 2026-10-19 裁定）。

已实现的提供方（**配置是唯一顺序权威**：`config/business_info.json::providers`）
--------------
1. `local_db`（`LocalDBProvider`）
   查本系统既有的账套库（`companies`）与项目库（`projects`）。
   ★ **唯一 100% 可用的通道**：用户此前录过的企业信息直接复用，
     不产生任何外部请求，也不触发反爬。**但它不是外网来源**——
     数据是用户建项目时自己填进去的，对新企业不产生新数据。
2. `manual_cookie`（`ManualCookieProvider`，**路线 A**）
   国家企业信用信息公示系统（https://www.gsxt.gov.cn）页面抓取 + **人工过验证码后
   配置的 Cookie**：随机 UA、请求间随机延迟、`trust_env=False`、总量超时、字节上限。
   ★ 诚实边界：该站有验证码/滑块与频率风控，**没有免 Key 的公开 API**。
     无 cookie 时实测 **HTTP 521**（风控拒绝）；配置 `GSXT_COOKIE` 后可复用至失效。
     抓不到就 `ok=False` 并给出**可执行的配置步骤**，**绝不**用猜测值/编造值填充 DTO。
3. `paid_api`（`PaidApiProvider`，**路线 C**）
   通用**付费工商数据服务**（天眼查/企查查及同类）：
     · token / 服务商标识 / 接口地址**全部只从环境变量读取**（配置登记变量名，代码零硬编码）；
     · 未配置 ⇒ 如实失败并列出所需变量名（**不假装已对接**）；
     · 响应字段经 `engine.business_info.dto` 统一清洗（别名表覆盖常见服务商字段名与中文标签）。
   ★ 这条路是**覆盖率兜底**：A 保免费基线、C 保新企业也能拿到完整登记字段。

★ 已**不采用**的路线（如实登记，见配置 `channel_plan.retired`）
   B 逐省适配地方市监/税务公开数据：维护成本与覆盖缺口不成比例；
   D 搜索引擎兜底：只能给"线索"、**不能作为工商登记字段来源**（仅保留在
     `engine/external_verifier` 作旁证，**不在本通道链内**）。

★ 为什么不用第三方"工商爬虫库"
  评估过的开源项目（`gsxt_crawler` 等）均依赖**付费打码平台**或内置了不可用的
  接口签名，且多已停更（最后一次提交在 2022 年前后）。引入它们等于把
  "能不能用"绑在一个不可控的外部服务上，并且要在代码里塞 Key —— 与
  "不硬编码 Key" 的约束直接冲突。故自行实现，解析器用 `lxml`
  （**已在 `requirements.lock` 内**，不新增未验证依赖）。
"""
from __future__ import annotations

import json
import os
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


# ─────────────── ② A·人工过验证码（公示系统 + 人工配置 cookie）───────────────
class ManualCookieProvider(BaseProvider):
    """**路线 A**：国家企业信用信息公示系统页面抓取 + 人工过验证码后配置的 Cookie。

    ★ 通道语义（如实）：**没有免 Key 的公开 API**，页面带验证码/滑块。
      无 cookie 时该站实测 **HTTP 521**（风控拒绝）⇒ 本通道**如实失败**，
      并给出**可执行的配置步骤**（不让用户看到"不知道怎么办"的失败）。
      配置 `GSXT_COOKIE`（配置里的 `cookie_env`）后即可复用至 cookie 失效。
    """

    name = "manual_cookie"
    #: 兼容旧配置键（历史配置用 `gsxt` 段）；**优先新键**，缺则回退旧键。
    _LEGACY_CFG_KEY = "gsxt"
    _FIELDS = (
        ("统一社会信用代码", "tax_id"), ("注册号", "tax_id"),
        ("法定代表人", "legal_representative"), ("注册资本", "registered_capital"),
        ("成立日期", "established_date"), ("登记状态", "registration_status"),
        ("住所", "registered_address"), ("注册地址", "registered_address"),
        ("企业类型", "company_type"), ("公司类型", "company_type"),
        ("经营范围", "business_scope"),
    )

    def _cfg(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        """本通道配置段（新键 `manual_cookie` 优先，回退旧键 `gsxt`）。"""
        return (cfg.get(self.name) or cfg.get(self._LEGACY_CFG_KEY) or {})

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

    def _howto(self, gcfg: Dict[str, Any], cfg: Dict[str, Any]) -> str:
        """未配置 cookie 时的**可执行**指引（配置项即唯一来源，不写死字面量）。"""
        return ("【A 通道·人工过验证码】① 用浏览器打开 %s 人工通过验证码 "
                "② 复制请求头 Cookie ③ 写入环境变量 %s 后重启服务；"
                "或改用 C 通道（付费 API，配置 %s）。"
                % (gcfg.get("search_url") or "公示系统",
                   gcfg.get("cookie_env") or "GSXT_COOKIE",
                   (cfg.get("paid_api") or {}).get("token_env") or "BUSINESS_API_TOKEN"))

    def query(self, name: str, cfg: Dict[str, Any], deadline: float) -> ProviderResult:
        t0 = time.time()
        gcfg = self._cfg(cfg)
        req = cfg.get("request") or {}
        if not gcfg.get("enabled", True):
            return ProviderResult(self.name, False, reason="A 通道已关闭（配置）")
        url = str(gcfg.get("search_url") or "")
        if not url:
            return ProviderResult(self.name, False, reason="未配置 search_url")
        cookie_env = str(gcfg.get("cookie_env") or "GSXT_COOKIE")
        cookie = os.environ.get(cookie_env, "")
        min_len = int(gcfg.get("min_cookie_len") or 12)
        if gcfg.get("cookie_required", True) and len(cookie.strip()) < min_len:
            # ★ 不发起注定被拦的请求：无 cookie 时该站实测 521 ⇒ 直接如实失败 + 配置指引
            return ProviderResult(self.name, False,
                                  reason="未配置 Cookie（环境变量 %s）⇒ %s"
                                         % (cookie_env, self._howto(gcfg, cfg)),
                                  elapsed_ms=int((time.time() - t0) * 1000))
        if not self._sleep(cfg, deadline):
            return ProviderResult(self.name, False, reason="剩余时间不足，跳过外部通道",
                                  elapsed_ms=int((time.time() - t0) * 1000))
        try:
            import requests                                         # noqa: PLC0415
        except Exception as exc:                                    # noqa: BLE001
            return ProviderResult(self.name, False, reason="requests 不可用：%s" % exc)

        sess = self._session(cfg)
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
            reason = "HTTP %d" % resp.status_code
            if int(resp.status_code) == 521:
                reason = ("HTTP 521（公示系统风控拒绝）⇒ Cookie 可能已失效："
                          "请重新按【A 通道】人工过验证码后更新 %s" % cookie_env)
            return ProviderResult(self.name, False, reason=reason, elapsed_ms=ms,
                                  extra={"markers": markers})
        if markers:
            return ProviderResult(
                self.name, False,
                reason="被公示系统风控拦截（命中：%s）⇒ Cookie 失效或频控，"
                       "请重新人工过验证码后更新 %s" % ("、".join(markers[:3]), cookie_env),
                elapsed_ms=ms, extra={"markers": markers})

        raw = self._parse(body, str(name), bool(gcfg.get("require_exact_name", True)))
        if not raw:
            return ProviderResult(
                self.name, False,
                reason="页面已返回但未解析到该企业登记信息（页面结构变化或需登录）",
                elapsed_ms=ms)
        return ProviderResult(self.name, True, raw=raw,
                              source_detail="国家企业信用信息公示系统（A 通道·人工 cookie）",
                              elapsed_ms=ms)

    def _parse(self, html: str, want: str, exact: bool) -> Optional[Dict[str, Any]]:
        """从页面文本里按**标签-值**配对取字段（结构无关，容错优先）。

        ★ 2026-10-19 修真实缺陷（结果级验收 `_verify_business_channels.py` 抓出）：
          旧写法 `val = ln.split("：", 1)[-1].split(":", 1)[-1].strip()` 在**行内没有
          冒号**时会**原样返回整行** ⇒ 于是「统一社会信用代码」这一行被当成它的值存进
          `tax_id`，`raw` 看着有值、实际是**标签冒充数据**（比缺字段更危险：后续清洗会
          报"格式不合 18 位"，读者以为页面结构变了）。
          公示系统真实页面正是 `<td>标签</td><td>值</td>` 的**无冒号**形态 ⇒ 必现。
          现按三种形态分别取值，取不到就**不写**（不制造假字段）：
            ① `标签：值` / `标签: 值`  ⇒ 取分隔符后；
            ② `标签 值`（空格/Tab 分隔）⇒ 取标签后的剩余；
            ③ 行**恰好等于标签**         ⇒ 取**下一行**（`<td>` 相邻单元格的常见形态）。
        """
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
                if not ln.startswith(label):
                    continue
                rest = ln[len(label):].strip()
                if rest[:1] in ("：", ":"):
                    val = rest[1:].strip()
                elif rest:
                    val = rest
                else:
                    # 行恰好等于标签 ⇒ 值在下一行（且下一行不能是另一个标签）
                    val = ""
                    if i + 1 < len(lines):
                        nxt = lines[i + 1].strip()
                        if not any(nxt.startswith(lb) for lb, _f in self._FIELDS):
                            val = nxt
                # ★ 绝不把标签本身当值（旧缺陷）
                if val and val.strip() == label:
                    val = ""
                if val and len(val) <= 1000:
                    raw[field] = val
        # 一个业务字段都没取到 ⇒ 视为未解析（不返回只有 name 的空壳）
        if len(raw) <= 1:
            return None
        return raw


# ─────────────── ③ C·付费数据服务（token，全环境变量）───────────────
class PaidApiProvider(BaseProvider):
    """**路线 C**：通用付费工商数据服务（天眼查/企查查及同类）。

    ★ 硬性约束（本项目铁律）：
      · token / 服务商标识 / 接口地址**只从环境变量读取**（变量名在配置里登记）
        ⇒ 代码零硬编码、密钥不落盘、可随账号轮换；
      · 未配置 ⇒ **如实失败**并列出所需变量名（**不假装已对接**、不静默降级）；
      · 响应字段交给 `engine.business_info.dto` 统一清洗（别名表已覆盖常见服务商字段名
        与中文标签）⇒ 本通道**不新建字段口径**；
      · 失败不阻断业务（与整个查询服务的失败语义一致：200 + `ok=false` + 可读原因）。
    """

    name = "paid_api"

    def query(self, name: str, cfg: Dict[str, Any], deadline: float) -> ProviderResult:
        t0 = time.time()
        pcfg = cfg.get("paid_api") or {}
        req = cfg.get("request") or {}
        if not pcfg.get("enabled", True):
            return ProviderResult(self.name, False, reason="C 通道已关闭（配置）")
        token_env = str(pcfg.get("token_env") or "BUSINESS_API_TOKEN")
        base_env = str(pcfg.get("base_url_env") or "BUSINESS_API_BASE_URL")
        prov_env = str(pcfg.get("provider_env") or "BUSINESS_API_PROVIDER")
        token = os.environ.get(token_env, "").strip()
        base = os.environ.get(base_env, "").strip()
        prov = os.environ.get(prov_env, "").strip() or str(
            pcfg.get("default_provider_name") or "付费数据服务")
        if not token or not base:
            miss = [v for v, ok in ((token_env, token), (base_env, base)) if not ok]
            return ProviderResult(
                self.name, False,
                reason=("未配置付费服务：缺少环境变量 %s（%s=token，%s=服务商标识，"
                        "%s=查询接口地址）⇒ 配置后启用 C 通道"
                        % ("、".join(miss), token_env, prov_env, base_env)),
                elapsed_ms=int((time.time() - t0) * 1000))
        try:
            import requests                                         # noqa: PLC0415
        except Exception as exc:                                    # noqa: BLE001
            return ProviderResult(self.name, False, reason="requests 不可用：%s" % exc)

        # ★ 与 A 通道同一铁律：本机 http_proxy 会让请求静默走代理 ⇒ trust_env 由配置决定
        sess = requests.Session()
        sess.trust_env = bool(req.get("trust_env", False))
        sess.headers.update({
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        timeout = max(1.0, min(float(pcfg.get("timeout_sec") or 6.0),
                               deadline - time.time()))
        try:
            resp = sess.get(base, params={"keyword": str(name), "provider": prov},
                            timeout=timeout,
                            verify=not bool(os.environ.get(
                                str(pcfg.get("insecure_tls_env") or
                                    "BUSINESS_API_INSECURE_TLS"))))
        except Exception as exc:                                    # noqa: BLE001
            return ProviderResult(self.name, False,
                                  reason="请求失败：%s" % type(exc).__name__,
                                  elapsed_ms=int((time.time() - t0) * 1000))
        ms = int((time.time() - t0) * 1000)
        if resp.status_code >= 400:
            return ProviderResult(self.name, False,
                                  reason="付费服务 HTTP %d" % resp.status_code, elapsed_ms=ms)
        raw = self._parse(resp.text, resp.headers.get("Content-Type", ""))
        if not raw:
            return ProviderResult(
                self.name, False,
                reason="付费服务已响应但未取到该企业登记信息（未命中或响应结构变更）",
                elapsed_ms=ms)
        return ProviderResult(self.name, True, raw=raw,
                              source_detail="付费数据服务（C 通道·%s）" % prov,
                              elapsed_ms=ms)

    def _parse(self, text: str, content_type: str) -> Optional[Dict[str, Any]]:
        """响应 → raw 字典（JSON 优先；非 JSON 交给调用方按 DTO 清洗，不猜结构）。

        ★ 只做"取到承载企业信息的字典"这一件事：常见包装（`data`/`result`/`items[0]`）
        按**确定性顺序**下钻；取到即返回，取不到返回 None（**不编造字段**）。
        """
        try:
            obj = json.loads(text)
        except Exception:                                           # noqa: BLE001
            return None
        node: Any = obj
        for _ in range(4):
            if isinstance(node, dict):
                for key in ("data", "result", "company", "profile"):
                    if isinstance(node.get(key), (dict, list)):
                        node = node[key]
                        break
                else:
                    break
            elif isinstance(node, list):
                if not node:
                    return None
                node = node[0]
            else:
                break
        return node if isinstance(node, dict) and node else None


# ── 向后兼容别名（历史代码/测试可能引用 `GsxtProvider`）───────────────
GsxtProvider = ManualCookieProvider


_PROVIDERS: Dict[str, BaseProvider] = {
    LocalDBProvider.name: LocalDBProvider(),
    ManualCookieProvider.name: ManualCookieProvider(),
    PaidApiProvider.name: PaidApiProvider(),
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


def channel_status(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """各通道的**如实状态**（供接口/界面展示"现在到底能用哪个"）。

    ★ 2026-10-19 立：此前界面上只有"4通道"这种**能力声称**，没有"哪条现在真能用"的
      **事实**。本函数把事实集中到唯一处（配置驱动），界面/文档都从这里取。
    返回每项：`{provider, route, label, configured, available, note}`。
    """
    out: List[Dict[str, Any]] = []
    routes = (cfg.get("channel_plan") or {}).get("routes") or {}
    for name in (cfg.get("providers") or []):
        p = _PROVIDERS.get(str(name))
        if p is None:
            continue
        c = cfg.get(name) or {}
        route = routes.get(str(c.get("route") or ""), "") or str(c.get("route") or "")
        item: Dict[str, Any] = {
            "provider": str(name), "route": route,
            "label": str(c.get("label") or name),
            "enabled": bool(c.get("enabled", True)),
            "configured": True, "available": True, "note": "",
        }
        if name == LocalDBProvider.name:
            item["note"] = ("离线读本系统已有账套/项目数据 —— **唯一 100% 可用的通道**；"
                            "但它是用户自填值的回读，**不是外网来源**，对新企业不产生新数据。")
        elif name == ManualCookieProvider.name:
            env = str(c.get("cookie_env") or "GSXT_COOKIE")
            has = len(str(os.environ.get(env, "")).strip()) >= int(c.get("min_cookie_len") or 12)
            item["configured"] = has
            item["available"] = bool(c.get("enabled", True)) and has
            item["note"] = ("已配置 %s，可无人值守复用至 cookie 失效。" % env) if has else (
                "未配置环境变量 %s ⇒ 实测公示系统返回 HTTP 521（风控），"
                "**取不到登记字段**；须人工过验证码后配置该变量。" % env)
        elif name == PaidApiProvider.name:
            tenv = str(c.get("token_env") or "BUSINESS_API_TOKEN")
            benv = str(c.get("base_url_env") or "BUSINESS_API_BASE_URL")
            has = bool(str(os.environ.get(tenv, "")).strip()
                       and str(os.environ.get(benv, "")).strip())
            item["configured"] = has
            item["available"] = bool(c.get("enabled", True)) and has
            item["note"] = ("已配置付费服务（%s / %s），覆盖新企业。" % (tenv, benv)) if has else (
                "未配置 %s / %s ⇒ C 通道未启用（需商务账号与 token）。" % (tenv, benv))
        out.append(item)
    return out


__all__ = ["ProviderResult", "BaseProvider", "LocalDBProvider",
           "ManualCookieProvider", "PaidApiProvider", "GsxtProvider",
           "available", "registry", "channel_status"]
