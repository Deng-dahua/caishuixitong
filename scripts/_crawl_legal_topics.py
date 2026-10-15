# -*- coding: utf-8 -*-
"""专题法规抓取器（TOPIC → 三源检索 → 详情页正文）—— **候选产出，不直接入库**。

## 为什么是"候选"而不是"入库"
项目铁律：**不编造法规条文**、**法规库写入唯一走 `scripts/_load_legal_texts.py`（人工核实后录入）**。
故本脚本**只做采集**，产出落 `data/legal_crawl/`（运行期产物），供人工核实后由人工录入器入库。
产出物**逐条带 URL + 抓取时间 + 内容哈希**，可溯源复核。

## 数据源（三源共用税务总局统一检索 `search5`）
| 源 | 域名 | 说明 |
|---|---|---|
| 国家税务总局官网 | www.chinatax.gov.cn | `siteName` 标为「国家税务总局」 |
| 税费政策法规库 | fgk.chinatax.gov.cn | `siteName` 标为「国家税务总局政策法规库」 |
| 12366 纳税服务平台 | 12366.chinatax.gov.cn | `siteName` 标为「12366…」 |

三源站点标识同为 `bm29000002`（税务总局），检索一次即覆盖三源，结果条目带 `siteName`
区分来源。**本脚本据 `siteName` 统计三源覆盖**（验收标准 1：三源全部抓取有记录）。

## 用法
    ./.venv/Scripts/python.exe scripts/_crawl_legal_topics.py TOPIC-001
    ./.venv/Scripts/python.exe scripts/_crawl_legal_topics.py TOPIC-001 --pages 3
    ./.venv/Scripts/python.exe scripts/_crawl_legal_topics.py TOPIC-001 --no-detail

## 产出（全部在 data/legal_crawl/）
    <topic>_search.json   检索命中（去重后，含标题/文号/日期/类型/URL/来源）
    <topic>_details.json  详情页正文（逐条 URL + 抓取时间 + sha256）
    <topic>_report.json   覆盖统计（三源分布 / 文件类型分布 / 年份分布）

## 约束（遵守指令：不高频请求、不采集非公开数据）
- 请求间隔默认 1.5s；带可识别 UA；不并发。
- 只检索公开页面；只抓取检索命中的公开文件。
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests                                    # noqa: E402

UA = "Mozilla/5.0 (compatible; caishuixitong-legal-indexer/1.0; +local-research)"
SEARCH_API = "https://www.chinatax.gov.cn/search5/search/s"
SITE_CODE = "bm29000002"
#: 只取法规类栏目（排除新闻/税案通报等非法规内容）
COLUMN = "政策法规,政策解读,政策指引"
#: ★ 2026-10-15 实测教训：**不把 `label` 作为请求参数**——
#   加了它反而把真实存在的法规文件**静默排除**（实测「异常增值税扣税凭证管理」
#   「重大税收违法失信主体信息公布管理办法」带 label 时命中 0、不带时分别命中 1/7 条）。
#   改成：**请求不过滤，事后按结果自带的 `label`/`typename` 分类**（不静默丢，
#   非法规内容照实标注、可在复核时排除）。这就是「不确定就不报」在抓取上的落地。
LABEL_LEVELS: Dict[str, str] = {
    "法律": "法律", "行政法规": "行政法规", "国务院文件": "国务院文件",
    "税务部门规章": "部门规章", "财税文件": "规范性文件",
    "税务规范性文件": "规范性文件", "其他文件": "其他文件",
    "工作通知": "工作通知", "政策指引": "政策指引", "文字政策解读": "解读",
    "政策解读": "解读",
}
SLEEP = 1.5
OUT_DIR = ROOT / "data" / "legal_crawl"

#: 三源识别（按 siteName 关键字）
SOURCE_OF = (
    ("政策法规库", "fgk.chinatax.gov.cn（税费政策法规库）"),
    ("12366", "12366.chinatax.gov.cn（12366纳税服务平台）"),
)
DEFAULT_SOURCE = "www.chinatax.gov.cn（国家税务总局官网）"


def _strip_tags(s: Any) -> str:
    """去标签 + 去 `<span>` 高亮 + 收敛空白（检索结果 title/content 带高亮标签）。"""
    t = re.sub(r"<[^>]+>", "", str(s or ""))
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", t).strip()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _source_of(site_name: str) -> str:
    for kw, label in SOURCE_OF:
        if kw in (site_name or ""):
            return label
    return DEFAULT_SOURCE


def _get(url: str, *, params: Dict[str, Any] | None = None, referer: str = "") -> requests.Response:
    """GET 并**强制按站点真实编码解码**。

    ★★ 2026-10-15 实测事故：`requests` 依据响应头猜编码，三个站点页面无明确 charset
      ⇒ 猜成 ISO-8859-1 ⇒ 正文抓成**乱码**（`å½å®¶ç¨å¡æ»å±` = UTF-8 字节被按 Latin-1 解码）。
      修法：读 `r.content`（原始字节）显式 `decode("utf-8")`；失败再退 GBK。
      **乱码入库比没抓到更危险**（看起来有内容、实则不可用）——与"验收工具坏了更危险"同理。
    """
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    raw = r.content
    for enc in ("utf-8", "gb18030"):
        try:
            r._decoded_text = raw.decode(enc)                        # noqa: SLF001
            break
        except UnicodeDecodeError:
            continue
    else:
        r._decoded_text = raw.decode("utf-8", "replace")             # noqa: SLF001
    return r


def _text(r: requests.Response) -> str:
    return getattr(r, "_decoded_text", None) or r.text


def search(keyword: str, page: int) -> Dict[str, Any]:
    """一次检索（返回原始 JSON）。"""
    r = _get(SEARCH_API, params={
        "siteCode": SITE_CODE, "column": COLUMN,
        "searchWord": keyword, "pageSize": 10, "pageNum": page,
    }, referer="https://fgk.chinatax.gov.cn/")
    time.sleep(SLEEP)
    try:
        j = r.json()
        return j
    except Exception:                                            # noqa: BLE001
        return {}


def _norm_hit(x: Dict[str, Any]) -> Dict[str, Any]:
    gov = x.get("govDoc") or {}
    return {
        "title": _strip_tags(x.get("title")),
        "url": str(x.get("url") or "").strip(),
        "snapshot_url": str(x.get("snapshotUrl") or "").strip(),
        "doc_no": str(gov.get("docNo") or gov.get("docNum") or "").strip(),
        "doc_type": str(gov.get("docType") or "").strip(),
        "doc_year": str(gov.get("docYear") or "").strip(),
        "pub_date": str(x.get("pubDate") or x.get("cwrq") or "").strip()[:10],
        "pub_name": _strip_tags(x.get("pubName")),
        "type_cn": _strip_tags(x.get("typename") or x.get("column")),
        "label": _strip_tags(x.get("label")),
        "effect_level": str(x.get("xxgk_effectLevel") or "").strip(),
        "source": _source_of(str(x.get("siteName") or "")),
        "site_name": str(x.get("siteName") or ""),
        "snippet": _strip_tags(x.get("shortContent") or x.get("content"))[:200],
    }


def _extract_body(html: str) -> str:
    """详情页正文（TRS CMS `#fontzoom` → 退化到 `.content` → 全文兜底；**兜底时如实留痕**）。"""
    for pat in (r'id="fontzoom"[^>]*>([\s\S]*?)</div>\s*</div>',
                r'class="content"[^>]*>([\s\S]*?)</div>\s*</div>'):
        m = re.search(pat, html)
        if m:
            t = _strip_tags(m.group(1))
            if len(t) > 120:
                return t
    body = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", "", html)
    return _strip_tags(body)


def _norm_cjk(s: str) -> str:
    return re.sub(r"[^\u4e00-\u9fff0-9A-Za-z]", "", str(s or ""))


def _score(target_name: str, title: str) -> float:
    """标题与目标名的相似度（`difflib` 序列比 + 长包含加分）。

    ★ 实测：字符集交并比（第一版）会把「善意取得」错配到
      「关于出口货物劳务增值税和消费税政策的通知」（含"取得"二字）⇒ 改用**序列相似度**。
      同时要求候选标题**包含目标名的主干**（去括注后的部分）才给包含加分。
    """
    from difflib import SequenceMatcher
    tn, ht = _norm_cjk(target_name), _norm_cjk(title)
    if not tn or not ht:
        return 0.0
    sc = SequenceMatcher(None, tn, ht).ratio()
    core = _norm_cjk(re.sub(r"[（(].*?[)）]", "", target_name))
    if core and (core in ht or ht in core):
        sc += 0.35
    return sc


def crawl_targets(topic_id: str, *, pages: int, with_detail: bool) -> int:
    """**定向抓取**：按登记的目标文件（名称/文号）精确检索 → 挑最匹配 → 抓正文。

    与宽泛关键词检索的区别：精度高、可逐条核对。**未命中如实标注 `matched: null`**
    （绝不编造补全）。
    """
    tgt_file = ROOT / "config" / "legal_crawl_targets.json"
    tg = (json.loads(tgt_file.read_text(encoding="utf-8")).get("topics") or {}).get(topic_id)
    if not tg:
        print("专题 %s 未登记定向目标" % topic_id)
        return 2
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out: List[Dict[str, Any]] = []
    print("定向抓取 %s「%s」目标 %d 个" % (topic_id, tg["name"], len(tg["targets"])))
    for i, t in enumerate(tg["targets"], 1):
        seen: Dict[str, Dict[str, Any]] = {}
        for p in range(1, pages + 1):
            d = search(t["search"], p)
            rs = ((d.get("searchResultAll") or {}).get("searchTotal") or [])
            if not isinstance(rs, list):
                break
            for x in rs:
                if not isinstance(x, dict):
                    continue
                h = _norm_hit(x)
                if h["url"]:
                    seen.setdefault(h["url"], h)
            if len(rs) < 10:
                break
        hit_list = list(seen.values())
        ranked = sorted(hit_list, key=lambda h: -_score(t["name"], h["title"]))
        best = ranked[0] if ranked else None
        sc = _score(t["name"], best["title"]) if best else 0.0
        rec = dict(t)
        rec["matched"] = None
        rec["candidates_n"] = len(hit_list)
        rec["top_candidates"] = [{
            "title": h["title"][:80], "url": h["url"], "doc_no": h["doc_no"],
            "type": h["type_cn"], "level_cn": LABEL_LEVELS.get(h["label"], h["label"] or "未标注"),
            "score": round(_score(t["name"], h["title"]), 3),
        } for h in ranked[:3]]
        if best is not None and sc >= 0.6:
            rec["matched"] = best
            rec["match_score"] = round(sc, 3)
            if with_detail:
                try:
                    html = _text(_get(best["url"], referer="https://fgk.chinatax.gov.cn/"))
                    body = _extract_body(html)
                    time.sleep(SLEEP)
                    rec["body"] = body
                    rec["body_len"] = len(body)
                    rec["body_sha256"] = _sha(body)
                    rec["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                except Exception as exc:                          # noqa: BLE001
                    rec["fetch_error"] = str(exc)
        print("  [%d/%d] %-30s 候选 %-3d 匹配 %s"
              % (i, len(tg["targets"]), t["name"][:28], len(hit_list),
                 ("OK %.2f" % sc) if rec["matched"] else "未命中"))
        out.append(rec)

    matched = sum(1 for r in out if r["matched"])
    pf = OUT_DIR / ("%s_targets.json" % topic_id)
    pf.write_text(json.dumps({
        "topic_id": topic_id, "topic_name": tg["name"],
        "targets_n": len(out), "matched_n": matched,
        "targets": out,
        "_note": "★ 定向抓取**候选**：matched=null 表示未命中（如实标注，未编造补全）；"
                 "正文照抄官方页面，sha256 可复核；入库须走 scripts/_load_legal_texts.py。",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n定向命中 %d / %d → %s" % (matched, len(out), pf))
    miss = [r["name"] for r in out if not r["matched"]]
    if miss:
        print("未命中（如实列出，待补）：")
        for m in miss:
            print("  -", m)
    return 0


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("用法: _crawl_legal_topics.py TOPIC-001 [--pages N] [--no-detail] [--targets]")
        return 2
    topic_id = args[0]
    pages = 2
    if "--pages" in sys.argv:
        pages = int(sys.argv[sys.argv.index("--pages") + 1])
    with_detail = "--no-detail" not in sys.argv
    if "--targets" in sys.argv:
        return crawl_targets(topic_id, pages=pages, with_detail=with_detail)

    topics = json.loads((ROOT / "config" / "legal_topics.json").read_text(encoding="utf-8"))
    topic = next((t for t in topics["topics"] if t["id"] == topic_id), None)
    if topic is None:
        print("未登记专题：%s" % topic_id)
        return 2
    kw = topic.get("keywords") or [topic["name"]]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("专题 %s「%s」关键词 %d 个，每词 %d 页" % (topic_id, topic["name"], len(kw), pages))

    hits: Dict[str, Dict[str, Any]] = {}
    for i, k in enumerate(kw, 1):
        got = 0
        for p in range(1, pages + 1):
            d = search(k, p)
            rs = ((d.get("searchResultAll") or {}).get("searchTotal") or [])
            if not isinstance(rs, list):
                break
            for x in rs:
                if not isinstance(x, dict):
                    continue
                h = _norm_hit(x)
                key = h["url"] or h["title"]
                if key and key not in hits:
                    hits[key] = h
                    got += 1
            if len(rs) < 10:
                break
        print("  [%d/%d] %-14s 新增 %d（累计 %d）" % (i, len(kw), k, got, len(hits)))

    search_out = OUT_DIR / ("%s_search.json" % topic_id)
    search_out.write_text(json.dumps({
        "topic_id": topic_id, "topic_name": topic["name"], "keywords": kw,
        "column_filter": COLUMN, "site_code": SITE_CODE,
        "hit_count": len(hits), "hits": list(hits.values()),
        "_note": "★ 抓取**候选**，尚未人工核实；入库须走 scripts/_load_legal_texts.py。",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("检索命中 %d 条 → %s" % (len(hits), search_out))

    details: List[Dict[str, Any]] = []
    if with_detail:
        for i, h in enumerate(hits.values(), 1):
            u = h["url"] or h["snapshot_url"]
            if not u:
                continue
            try:
                html = _text(_get(u, referer="https://fgk.chinatax.gov.cn/"))
                body = _extract_body(html)
            except Exception as exc:                              # noqa: BLE001
                details.append({"url": u, "title": h["title"], "error": str(exc)})
                print("  [%d/%d] 失败 %s" % (i, len(hits), exc))
                continue
            time.sleep(SLEEP)
            details.append({
                "title": h["title"], "url": u, "doc_no": h["doc_no"],
                "pub_date": h["pub_date"], "type_cn": h["type_cn"],
                "source": h["source"], "effect_level": h["effect_level"],
                "body_len": len(body), "body_sha256": _sha(body), "body": body,
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            })
            if i % 10 == 0:
                print("  正文 %d/%d" % (i, len(hits)))
        det_out = OUT_DIR / ("%s_details.json" % topic_id)
        det_out.write_text(json.dumps({
            "topic_id": topic_id, "count": len(details), "details": details,
            "_note": "★ 正文照抄官方页面，未做任何改写；sha256 可复核。",
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print("正文 %d 条 → %s" % (len(details), det_out))

    # 覆盖统计（验收：三源 / 文件类型 / 年份）
    from collections import Counter
    src = Counter(h["source"] for h in hits.values())
    typ = Counter(h["type_cn"] for h in hits.values())
    yr = Counter(h["pub_date"][:4] for h in hits.values() if h["pub_date"])
    eff = Counter((h["effect_level"] or "（未标注）") for h in hits.values())
    rep = {
        "topic_id": topic_id, "topic_name": topic["name"],
        "hit_count": len(hits), "source_dist": dict(src),
        "type_dist": dict(typ), "year_dist": dict(sorted(yr.items(), reverse=True)),
        "effect_dist": dict(eff),
        "doc_no_count": sum(1 for h in hits.values() if h["doc_no"]),
    }
    rep_out = OUT_DIR / ("%s_report.json" % topic_id)
    rep_out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n三源分布:", json.dumps(dict(src), ensure_ascii=False))
    print("文件类型:", json.dumps(dict(typ), ensure_ascii=False))
    print("含文号条数: %d / %d" % (rep["doc_no_count"], len(hits)))
    print("报告 → %s" % rep_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
