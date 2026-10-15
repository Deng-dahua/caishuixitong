# -*- coding: utf-8 -*-
"""**分类全量采集器**：案例 / 解读 / 问答 / 指引（案例类内容的"横向到边"）。

## 为什么单独写
`_crawl_fgk_files.py` 采的是**法规类栏目**（最新文件 / 政策文件，靠 `getFileListByCodeId` 列表接口）。
而**案例 / 解读 / 问答 / 指引**不在那两个栏目里，它们由**检索系统的 label 分面**承载
（实测 label 分面计数：税案通报 851 / 文字政策解读 193 / 政策问答 101）。

## 反解出的采集方式（实测 2026-10-15）
```
GET https://www.chinatax.gov.cn/search5/search/s
    siteCode=bm29000002  searchWord=（空）  label=<label名>  pageSize=10  pageNum=1..N
```
★ **空 `searchWord` + `label` 即可全量遍历**（实测 page=1/2 内容不同、条数稳定 10）。
★ **`pageSize` 被服务端限制为 10**（传 50/100 仍返回 10）⇒ 只能逐页取。
★ 与 `_crawl_legal_topics.py` 的差别：**不带 `column` 参数**（带 column 会漏案例/解读类）。

## 用法
    ./.venv/Scripts/python.exe scripts/_crawl_fgk_categories.py                 # 四类全量
    ./.venv/Scripts/python.exe scripts/_crawl_fgk_categories.py --only 案例      # 单类
    ./.venv/Scripts/python.exe scripts/_crawl_fgk_categories.py --with-detail    # 并抓正文

## 产出（`data/legal_crawl/`）
    fgk_categories.jsonl    逐页原始（断点续爬）
    fgk_categories.json     分类全量清单（按 category 分组）
    fgk_categories_report.json  分类计数与统计
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests                                              # noqa: E402

UA = "Mozilla/5.0 (compatible; caishuixitong-legal-indexer/1.0; +local-research)"
API = "https://www.chinatax.gov.cn/search5/search/s"
SITE_CODE = "bm29000002"
REFERER = "https://fgk.chinatax.gov.cn/"
SLEEP = 1.5
PAGE_SIZE = 10                       # 实测服务端固定 10
OUT_DIR = ROOT / "data" / "legal_crawl"

_S = requests.Session()
_S.trust_env = False                 # ★ 关环境代理（本机有 http_proxy，否则 ProxyError 静默全失败）
_S.headers.update({"User-Agent": UA, "Referer": REFERER})

#: ★ 四类栏目（label 名来自实测 label 分面）。新增一类＝加一行。
CATEGORIES: List[Dict[str, Any]] = [
    {"category": "案例", "label": "税案通报", "expect": 851,
     "note": "税务总局/各地曝光的典型涉税违法案件"},
    {"category": "解读", "label": "文字政策解读", "expect": 193,
     "note": "官方政策解读（文字版）"},
    {"category": "问答", "label": "政策问答", "expect": 101,
     "note": "12366 政策问答"},
    {"category": "指引", "label": "减税降费政策操作指南查询", "expect": None,
     "note": "办税/操作指南（label 名待核实，可能已改名）"},
]


def fetch(label: str, page: int) -> Dict[str, Any]:
    for attempt in (1, 2, 3):
        try:
            r = _S.get(API, params={
                "siteCode": SITE_CODE, "searchWord": "", "label": label,
                "pageSize": PAGE_SIZE, "pageNum": page,
            }, timeout=40)
            r.raise_for_status()
            time.sleep(SLEEP)
            return r.json()
        except Exception as exc:                              # noqa: BLE001
            print("    [重试 %d] %s page=%d 失败：%s" % (attempt, label, page, str(exc)[:70]))
            time.sleep(SLEEP * 2)
    return {}


#: ★ fgk 接口把空值返回成字面量 `"null"`（实测）⇒ 必须归空，否则产生假数据
_BLANK = {"", "null", "none", "None", "NULL", "undefined", "-", "—", "／", "/", "无"}


def _clean(s: Any) -> str:
    t = re.sub(r"<[^>]+>", "", str(s or ""))
    t = re.sub(r"\s+", " ", t.replace("&nbsp;", " ")).strip()
    return "" if t in _BLANK else t


def norm(x: Dict[str, Any], cat: Dict[str, Any]) -> Dict[str, Any]:
    gov = x.get("govDoc") or {}
    return {
        "title": _clean(x.get("title")),
        "url": str(x.get("url") or "").strip(),
        "doc_no": str(gov.get("docNum") or gov.get("docNo") or "").strip(),
        "published_at": str(x.get("pubDate") or x.get("cwrq") or "").strip()[:10],
        "pub_name": _clean(x.get("pubName")),
        "type_name": _clean(x.get("typename") or x.get("column")),
        "label": _clean(x.get("label")),
        "category": cat["category"],
        "source": "www.chinatax.gov.cn（国家税务总局官网）",
        "source_site": str(x.get("siteName") or ""),
        "snippet": _clean(x.get("shortContent") or x.get("content"))[:240],
    }


def _load_cache(pages_file: Path) -> Dict[str, Dict[str, Any]]:
    """从已落盘的 `fgk_categories.jsonl` 重新归一（`--from-cache` 用）。

    ★★ 2026-10-15 实测 bug：断点续爬只记「已完页数」用于**跳过请求**，而 `items` 只在
      内存累积 ⇒ 第二次跑（只采未完成类）时，**前一次已采的类整批丢失**
      （实测：问答 443 条在合并结果里消失，总量 1613→1612）。
      修法：本函数把 jsonl 全量重放一遍；`--from-cache` 即不发请求、纯从缓存重建。
    """
    out: Dict[str, Dict[str, Any]] = {}
    if not pages_file.exists():
        return out
    cat_of = {c["label"]: c for c in CATEGORIES}
    for line in pages_file.read_text(encoding="utf-8").splitlines():
        try:
            o = json.loads(line)
        except Exception:                                     # noqa: BLE001
            continue
        cat = cat_of.get(o.get("label"))
        if not cat:
            continue
        for x in (o.get("results") or []):
            if not isinstance(x, dict):
                continue
            r = norm(x, cat)
            key = r["url"] or r["title"]
            if key and key not in out:
                out[key] = r
    return out


def main() -> int:
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]
    from_cache = "--from-cache" in sys.argv
    cats = [c for c in CATEGORIES if (not only or c["category"] == only)]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pages_file = OUT_DIR / "fgk_categories.jsonl"

    items: Dict[str, Dict[str, Any]] = _load_cache(pages_file)
    if items:
        print("从缓存载入 %d 条（含先前已采各类）" % len(items))
    if from_cache:
        if not items:
            print("!! `--from-cache` 需先有 %s" % pages_file)
            return 2
        cats = []

    done: Dict[str, int] = {}
    if pages_file.exists():
        for line in pages_file.read_text(encoding="utf-8").splitlines():
            try:
                o = json.loads(line)
                done[o["label"]] = max(done.get(o["label"], 0), o["page"])
            except Exception:                                 # noqa: BLE001
                pass
        if done and cats:
            print("断点续爬：已完成页 %s" % done)

    with pages_file.open("a", encoding="utf-8") as fh:
        for cat in cats:
            # 第 1 页取总数
            first = fetch(cat["label"], 1)
            total = int((first.get("searchResultAll") or {}).get("total") or 0)
            npages = (total + PAGE_SIZE - 1) // PAGE_SIZE if total else 0
            print("══ %s「%s」total=%d → %d 页" % (cat["category"], cat["label"], total, npages))
            if not total:
                print("   !! 该 label 无结果（可能已改名/下线）—— 如实记录，不猜测")
                continue
            start = done.get(cat["label"], 0) + 1
            for p in range(start, npages + 1):
                d = first if p == 1 else fetch(cat["label"], p)
                rs = ((d.get("searchResultAll") or {}).get("searchTotal") or [])
                if not isinstance(rs, list):
                    rs = []
                fh.write(json.dumps({"label": cat["label"], "category": cat["category"],
                                     "page": p, "total": total, "results": rs},
                                    ensure_ascii=False) + "\n")
                fh.flush()
                for x in rs:
                    if not isinstance(x, dict):
                        continue
                    r = norm(x, cat)
                    key = r["url"] or r["title"]
                    if key and key not in items:
                        items[key] = r
                if p % 10 == 0 or p == npages:
                    print("  页 %d/%d（累计去重 %d）" % (p, npages, len(items)))
            done[cat["label"]] = npages

    from collections import Counter
    all_items = list(items.values())
    by_cat: Dict[str, List[Dict[str, Any]]] = {}
    for it in all_items:
        by_cat.setdefault(it["category"], []).append(it)
    for k in by_cat:
        by_cat[k].sort(key=lambda r: (r.get("published_at") or ""), reverse=True)

    (OUT_DIR / "fgk_categories.json").write_text(json.dumps({
        "source": "www.chinatax.gov.cn（国家税务总局官网，检索系统 label 分面）",
        "api": API, "site_code": SITE_CODE, "page_size": PAGE_SIZE,
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "count": len(all_items),
        "categories": {k: {"count": len(v), "items": v} for k, v in sorted(by_cat.items())},
        "_note": "★ 分类全量清单（案例/解读/问答/指引）。逐条含 URL 可溯源；"
                 "为采集**候选**，未逐条人工核实。",
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    rep = {
        "count": len(all_items),
        "by_category": {k: len(v) for k, v in sorted(by_cat.items())},
        "by_type_name": dict(Counter(x["type_name"] for x in all_items).most_common(20)),
        "by_year": dict(sorted(Counter((x["published_at"] or "")[:4]
                                       for x in all_items if x["published_at"]).items(), reverse=True)),
        "by_source_site": dict(Counter(x["source_site"] for x in all_items).most_common()),
        "with_doc_no": sum(1 for x in all_items if x["doc_no"]),
    }
    (OUT_DIR / "fgk_categories_report.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n分类全量：%d 条" % len(all_items))
    print("分类计数:", json.dumps(rep["by_category"], ensure_ascii=False))
    print("→ %s" % (OUT_DIR / "fgk_categories.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
