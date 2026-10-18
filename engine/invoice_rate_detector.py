# -*- coding: utf-8 -*-
"""单张发票「错用税率」检测（GAP-06）。

为什么单独建一个模块
------------------
测评（META-SYSTEM-COMPLETENESS-AUDIT 2.1）实证：全库**没有任何**把"发票票面税率"与
"该货物/服务法定应适用税率"做比对的函数。最接近的是 `monthly_reconcile._rate_consistency`，
它是**月度汇总**口径（税额÷计税基础 vs 1/3/5/6/9/13%），不是单张；且它的产出
（类型串含"配比异常"）会被输出治理的 `hard_ban` 静默删除。

判据（全部数据驱动，逻辑里不写死任何品名）
--------------------------------------
   1. 取票面税率 `tax_rate`（"13%" / "0.13" / 13 都支持）；
   2. 按 `goods`（货物或应税劳务名称）在 `config/invoice_tax_rate_map.json` 里
      做**关键词**匹配 → 法定档位；
   3. 与票面税率比较，偏差 > `TOL`（0.5 个百分点）⇒ 疑点；
   4. **未命中任何关键词 ⇒ 不判**（宁可漏判，不可误伤：品名千变万化，映射表只收高置信项）；
   5. 零税率/免税品名 ⇒ 票面 0% 属正常，不判。

证据定位：每条发现都带票号清单（最多 10 张）+ 品名 + 票面率 + 法定率 + 法条项。

红线归属：复用 **RL-VAT-025「简易计税与一般计税方法适用错误」**（不新增红线条目，
避免打破"红线 127 条"的既有闸门基线）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parent.parent
_MAP_PATH = ROOT / "config" / "invoice_tax_rate_map.json"

#: 税率偏差容限（百分点）。0.5pp 足以吸收四舍五入，又不会放过 13%→6% 这类错档。
TOL = 0.005

_CACHE: Dict[str, Any] = {}


def _load_map() -> Dict[str, Any]:
    st = _MAP_PATH.stat()
    key = "%s_%s" % (st.st_mtime_ns, st.st_size)
    if _CACHE.get("key") == key:
        return _CACHE["data"]
    with _MAP_PATH.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    _CACHE["key"], _CACHE["data"] = key, data
    return data


def parse_rate(value) -> float:
    """票面税率 → 小数（"13%"→0.13，"0.13"→0.13，13→0.13）。取不到返回 -1。"""
    if value is None or value == "":
        return -1.0
    if isinstance(value, (int, float)):
        v = float(value)
        return v / 100.0 if v > 1 else v
    s = str(value).strip().replace("％", "%").replace(" ", "")
    if not s:
        return -1.0
    try:
        if s.endswith("%"):
            return float(s[:-1]) / 100.0
        v = float(s)
        return v / 100.0 if v > 1 else v
    except ValueError:
        return -1.0


def _inv_no(inv: dict) -> str:
    return str(inv.get("invoice_no") or inv.get("inv_no") or inv.get("number") or "").strip()


def _goods(inv: dict) -> str:
    """品名（★ 单一权威 `engine/fieldkit.goods_name`，禁止本地再写一份）。"""
    from engine.fieldkit import goods_name as _fk
    return str(_fk(inv) or "").strip()


def expected_rate(goods: str):
    """按品名给出法定税率。返回 (rate|None, tier, basis, matched_keyword)。"""
    g = str(goods or "")
    if not g:
        return None, "", "", ""
    data = _load_map()
    for kw in (data.get("zero_or_exempt") or {}).get("keywords") or []:
        if kw and kw in g:
            return 0.0, "0", "增值税法第二十四条/第三十三条（免税或零税率）", kw
    for rule in data.get("rules") or []:
        for kw in rule.get("keywords") or []:
            if kw and kw in g:
                return float(rule.get("rate")), str(rule.get("tier") or ""), \
                    str(rule.get("basis") or ""), kw
    return None, "", "", ""


def detect_misused_rate(invoices, ctx=None) -> List[Dict]:
    """扫描发票，检出票面税率与法定税率不符的（逐张）。返回 0 或 1 条发现。"""
    rows = [i for i in (invoices or []) if isinstance(i, dict)]
    if not rows:
        return []

    hits: List[Dict] = []
    skipped_no_goods = 0
    skipped_no_rate = 0
    undetermined = 0
    for inv in rows:
        goods = _goods(inv)
        rate = parse_rate(inv.get("tax_rate") if inv.get("tax_rate") is not None
                          else inv.get("税率"))
        if not goods:
            skipped_no_goods += 1
            continue
        if rate < 0:
            skipped_no_rate += 1
            continue
        exp, tier, basis, kw = expected_rate(goods)
        if exp is None:
            undetermined += 1
            continue
        if abs(rate - exp) <= TOL:
            continue
        # ★ 行内取金额统一走 `numparse.amount_of`（唯一权威；多键回落逻辑只在那一处）
        from engine.numparse import amount_of as _amount_of
        amt = _amount_of(inv, absolute=True)
        hits.append({
            "inv_no": _inv_no(inv),
            "goods": goods[:40],
            "face_rate": rate, "expected_rate": exp,
            "tier": tier, "basis": basis, "keyword": kw,
            "amount": amt,
            "direction": str(inv.get("direction") or ""),
        })

    if not hits:
        return []

    # 按（票面率, 法定率）分组，让文案说清是哪一类错档
    groups: Dict[tuple, List[Dict]] = {}
    for h in hits:
        groups.setdefault((h["face_rate"], h["expected_rate"]), []).append(h)
    pairs_txt = "；".join(
        "%s 应为 %s（%d 张）" % (_pct(f), _pct(e), len(v))
        for (f, e), v in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:4])
    amt_total = sum(h["amount"] for h in hits)
    samples = hits[:10]

    detail = ("检出 %d 张发票的票面税率与所售货物/服务的法定适用税率不一致：%s。"
              "涉及不含税金额合计 %s 元。错用税率会同时导致销项税额少计或多计，"
              "并牵连进项抵扣与申报表勾稽。" % (
                  len(hits), pairs_txt, format(amt_total, ",.2f")))
    # ★ "缺失≠0"：无法判定的张数必须显式说明，不能让读者以为"其余都合规"
    detail += ("另有 %d 张因品名未纳入税率映射表而**未作判定**（不是已核合规）"
               % undetermined) if undetermined else ""

    return [{
        "type": "单张发票错用税率：票面税率与法定适用税率不一致",
        "level": "中风险",
        "score": 6,
        "redline_id": "RL-VAT-025",
        "category": "发票合规",
        "detail": detail,
        "how_found": ("逐票取「货物或应税劳务名称」→ 关键品名映射到法定档位"
                      "（config/invoice_tax_rate_map.json）→ 与票面税率比对，偏差 >0.5 个百分点即计入"),
        "policy_ref": "《中华人民共和国增值税法》第十条（税率）、第九条（小规模纳税人）",
        "suggestion": ("逐张核对上述发票的适用税率：货物销售适用 13%，交通运输/建筑/不动产租赁"
                       "适用 9%，现代服务/金融/生活服务适用 6%；确属错档的应开具红字发票冲正"
                       "并更正对应所属期申报表。"),
        "observed_metrics": {
            "mismatch_count": len(hits),
            "mismatch_amount": round(amt_total, 2),
            "undetermined_count": undetermined,
            "skipped_no_goods": skipped_no_goods,
            "skipped_no_rate": skipped_no_rate,
            "groups": [{"face_rate": f, "expected_rate": e, "count": len(v)}
                       for (f, e), v in groups.items()],
            "samples": samples,
        },
        "constituent_hits": [{
            "index": 1,
            "evidence": "逐票比对：%d 张票面税率与法定税率不符（最大一组 %s），合计金额 %s 元" % (
                len(hits), (pairs_txt.split("；")[0] if pairs_txt else ""),
                format(amt_total, ",.2f")),
        }],
    }]


def _pct(v: float) -> str:
    """小数 → 百分比文本（0.13 → "13%"，0.015 → "1.5%"）。"""
    if not v:
        return "0%"
    s = ("%.2f" % (float(v) * 100)).rstrip("0").rstrip(".")
    return s + "%"
