# -*- coding: utf-8 -*-
"""税费政策法规库（`fgk.chinatax.gov.cn`）**全量列表**抓取器 —— 「横向到边」的落地。

## 为什么走"列表遍历"而不是"检索"（实测结论，2026-10-15）
| 方式 | 结果 |
|---|---|
| 检索接口 `search5/search/s` | 覆盖不了「法律/行政法规」（实测刑法/征管法/发票管理办法检索命中 0）；且为**字级松散匹配**，噪声大 |
| **列表接口 `getFileListByCodeId`** | **全库可枚举**：`最新文件` 栏目实测 **total=5022**，逐页可取，带**完整元数据** |

⇒ 本脚本按**栏目列表全量遍历**，这是"横向到边…一个不漏"的正解。

## 反解出的接口（实测）
```
POST https://www.chinatax.gov.cn/getFileListByCodeId
  codeId=<栏目码，可空>  channelId=<栏目ID>  page=<1..N>  size=<每页，实测 200 可用>
```
来源：`/zcfgk/xhtml/js/getManuscript.js`（列表加载器）。

## 条目携带的元数据（`domainMetaList` 三组，实测字段）
| 字段 key | 含义 |
|---|---|
| `effectlevel` | **效力等级**（法律/行政法规/税务部门规章/税务规范性文件/财税文件/其他文件/工作通知） |
| `writtentext` | **发文字号** |
| `writtendepartment` | **发文单位** |
| `taxpolicy` | **税费类型**（税收政策-增值税, …） |
| `labels` | **主题标签** |
| `industrytypename` | 行业分类 |
| `abolishdate` | 废止日期 |
| `revisepolicytitle` / `revisetype` | 修订标题 / 修订类型 |
| `filetype` / `typename` | 文件类型 |
| `source` | 采集来源（`SZfaguiku` = 税费政策法规库） |
+ 顶层：`title` / `url`（正文链接）/ `publishedTimeStr`（发布日期）/ `channelName`（栏目名）

## 产出（`data/legal_crawl/`）
| 文件 | 内容 |
|---|---|
| `fgk_files_pages.jsonl` | **逐页原始落盘**（断点续爬用，每行一页） |
| `fgk_files.json` | 去重后的**全量清单**（含上述全部字段 + 数据源标注） |
| `fgk_files_report.json` | 覆盖统计（效力等级/文件类型/发文单位/年份/税费类型分布） |

## 约束
- 请求间隔 1.5s；关环境代理（`trust_env=False`，本机有 `http_proxy` ⇒ 否则 ProxyError 静默全失败）。
- **只抓列表（元数据）+ 记录正文 URL**；不抓 5000+ 份正文（体量）。
  正文按需抓取 / 入库仍走项目唯一入口 `scripts/_load_legal_texts.py`（人工核实）。

用法
    ./.venv/Scripts/python.exe scripts/_crawl_fgk_files.py                # 全量
    ./.venv/Scripts/python.exe scripts/_crawl_fgk_files.py --max-pages 3  # 试跑
    ./.venv/Scripts/python.exe scripts/_crawl_fgk_files.py --channel c100024
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
API = "https://www.chinatax.gov.cn/getFileListByCodeId"
REFERER = "https://fgk.chinatax.gov.cn/zcfgk/c100006/listflfg.html"
SLEEP = 1.5
SIZE = 200
OUT_DIR = ROOT / "data" / "legal_crawl"

#: ★ 关环境代理（实测：本机 `http_proxy` 会导致 ProxyError 静默全失败）
_S = requests.Session()
_S.trust_env = False
_S.headers.update({"User-Agent": UA, "Referer": REFERER,
                   "X-Requested-With": "XMLHttpRequest"})

#: 栏目 = (栏目码, channelId, 名称)。实测取得；新增栏目＝加一行。
CHANNELS: List[Dict[str, str]] = [
    {"code": "c100006", "channel": "29a88b67e4b149cfa9fac7919dfb08a5",
     "name": "最新文件（法规主库）"},
    {"code": "c100024", "channel": "e95dafc5e54a4c36a24178f86e318b8d",
     "name": "政策文件"},
]

#: ★★ 2026-10-15 实测事故：fgk 接口把**空值返回成字面量字符串 `"null"`**（不是 JSON null）
#   ⇒ 若直接入库，`revise_title`/`abolish_date` 等字段会出现 1248 条值为 `"null"` 的**假数据**
#     （后续按"有值"判断会全部误判为真有修订/废止信息）。**脏数据比缺数据更危险**。
_BLANK = {"", "null", "none", "None", "NULL", "undefined", "-", "—", "／", "/", "无"}
#: 元数据字段抽取表：key → 规范字段名（新增一个元数据字段＝加一行）
META_MAP: Dict[str, str] = {
    "effectlevel": "effect_level",
    "writtentext": "doc_no",
    "writtendepartment": "issuer",
    "taxpolicy": "tax_policy",
    "labels": "labels",
    "industrytypename": "industry",
    "abolishdate": "abolish_date",
    "revisepolicytitle": "revise_title",
    "revisetype": "revise_type",
    "filetype": "file_type",
    "typename": "type_name",
    "writtendate": "written_date",
    "publicpattern": "public_pattern",
    "source": "origin_source",
    "description": "description",
}


def fetch_page(channel: str, page: int, size: int = SIZE) -> Dict[str, Any]:
    """取一页（返回 data：{page, total, results[]}），失败 ⇒ 空 dict。"""
    for attempt in (1, 2, 3):
        try:
            r = _S.post(API, data={"codeId": "", "channelId": channel,
                                   "page": page, "size": size}, timeout=40)
            r.raise_for_status()
            time.sleep(SLEEP)
            return ((r.json().get("results") or {}).get("data") or {})
        except Exception as exc:                              # noqa: BLE001
            print("    [重试 %d] page=%d 失败：%s" % (attempt, page, str(exc)[:80]))
            time.sleep(SLEEP * 2)
    return {}


def _clean(s: Any) -> str:
    t = re.sub(r"<[^>]+>", "", str(s or ""))
    t = re.sub(r"\s+", " ", t.replace("&nbsp;", " ")).strip()
    return "" if t in _BLANK else t          # ★ 字面量 "null" 等一律归空（不污染数据）


def norm_item(x: Dict[str, Any], ch: Dict[str, str]) -> Dict[str, Any]:
    """把一条原始条目归一为规范记录（含**数据源标注**）。"""
    rec: Dict[str, Any] = {
        "title": _clean(x.get("titleHtml") or x.get("title")),
        "sub_title": _clean(x.get("subTitleHtml")),
        "url": str(x.get("url") or "").strip(),
        "published_at": str(x.get("publishedTimeStr") or "").strip()[:10],
        "channel_name": _clean(x.get("channelName")),
        "channel_code": ch["code"],
        "source": "fgk.chinatax.gov.cn（税费政策法规库）",
        "source_type": "tax_bureau_library",
    }
    for g in (x.get("domainMetaList") or []):
        for f in ((g or {}).get("resultList") or []):
            k = str(f.get("key") or "")
            if k in META_MAP:
                v = _clean(f.get("value"))
                if v and not rec.get(META_MAP[k]):
                    rec[META_MAP[k]] = v
    return rec


def main() -> int:
    max_pages = None
    if "--max-pages" in sys.argv:
        max_pages = int(sys.argv[sys.argv.index("--max-pages") + 1])
    only_ch = None
    if "--channel" in sys.argv:
        only_ch = sys.argv[sys.argv.index("--channel") + 1]
    # ★ `--from-cache`：**只从已落盘的 `fgk_files_pages.jsonl` 重新归一**，不发请求。
    #   用途：修了清洗/字段映射逻辑后，免重新抓取即可重生成清单（幂等、秒级）。
    from_cache = "--from-cache" in sys.argv
    chans = [c for c in CHANNELS if (not only_ch or c["code"] == only_ch)]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    pages_file = OUT_DIR / "fgk_files_pages.jsonl"
    items: Dict[str, Dict[str, Any]] = {}
    if from_cache:
        if not pages_file.exists():
            print("!! `--from-cache` 需先有 %s" % pages_file)
            return 2
        chmap = {c["code"]: c for c in CHANNELS}
        n_pages = 0
        for line in pages_file.read_text(encoding="utf-8").splitlines():
            try:
                o = json.loads(line)
            except Exception:                                 # noqa: BLE001
                continue
            ch = chmap.get(o.get("channel"))
            if not ch:
                continue
            n_pages += 1
            for x in (o.get("results") or []):
                if not isinstance(x, dict):
                    continue
                r = norm_item(x, ch)
                key = r["url"] or r["title"]
                if key and key not in items:
                    items[key] = r
        print("从缓存归一：%d 页 → %d 条" % (n_pages, len(items)))
    else:
        seen_pages: Dict[str, int] = {}
        if pages_file.exists():                               # 断点续爬
            for line in pages_file.read_text(encoding="utf-8").splitlines():
                try:
                    o = json.loads(line)
                    seen_pages[o["channel"]] = max(seen_pages.get(o["channel"], 0), o["page"])
                except Exception:                             # noqa: BLE001
                    pass
            if seen_pages:
                print("断点续爬：已完成 %s" % seen_pages)

        with pages_file.open("a", encoding="utf-8") as fh:
            for ch in chans:
                first = fetch_page(ch["channel"], 1, 1)
                total = int(first.get("total") or 0)
                npages = (total + SIZE - 1) // SIZE if total else 0
                if max_pages:
                    npages = min(npages, max_pages)
                print("══ 栏目 %s「%s」total=%d → %d 页" % (ch["code"], ch["name"], total, npages))
                start = seen_pages.get(ch["code"], 0) + 1
                for p in range(start, npages + 1):
                    d = fetch_page(ch["channel"], p)
                    rs = d.get("results") or []
                    if not isinstance(rs, list):
                        rs = []
                    fh.write(json.dumps({"channel": ch["code"], "page": p,
                                         "total": d.get("total"), "results": rs},
                                        ensure_ascii=False) + "\n")
                    fh.flush()
                    for x in rs:
                        if not isinstance(x, dict):
                            continue
                        r = norm_item(x, ch)
                        key = r["url"] or r["title"]
                        if key and key not in items:
                            items[key] = r
                    if p % 5 == 0 or p == npages:
                        print("  页 %d/%d（累计去重 %d）" % (p, npages, len(items)))
                    if p == 1 and not rs:
                        print("  !! 首页无数据 —— 接口或参数可能已变，请核对")
                seen_pages[ch["code"]] = npages

    from collections import Counter

    def _split(v: Any) -> List[str]:
        return [x.strip() for x in str(v or "").replace("，", ",").split(",") if x.strip()]

    all_items = sorted(items.values(), key=lambda r: (r["published_at"] or "", r["title"]), reverse=True)
    eff = Counter((r.get("effect_level") or "（未标注）") for r in all_items)
    typ = Counter((r.get("type_name") or "（未标注）") for r in all_items)
    iss = Counter(_split(r.get("issuer"))[0] if r.get("issuer") else "（未标注）" for r in all_items)
    yr = Counter((r.get("published_at") or "")[:4] for r in all_items if r.get("published_at"))
    tp = Counter(t for r in all_items for t in _split(r.get("tax_policy")))
    lb = Counter(t for r in all_items for t in _split(r.get("labels")))
    docs = [r for r in all_items if r.get("doc_no")]

    (OUT_DIR / "fgk_files.json").write_text(json.dumps({
        "source": "fgk.chinatax.gov.cn（税费政策法规库，国家税务总局）",
        "api": API, "referer": REFERER, "channels": CHANNELS,
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "count": len(all_items), "with_doc_no": len(docs),
        "items": all_items,
        "_note": "★ **全量列表（元数据）**，按栏目遍历取得；正文按需抓取，入库唯一走 "
                 "`scripts/_load_legal_texts.py`（人工核实）。每条含 URL 可溯源。",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT_DIR / "fgk_files_report.json").write_text(json.dumps({
        "count": len(all_items), "with_doc_no": len(docs),
        "by_effect_level": dict(eff.most_common()),
        "by_type_name": dict(typ.most_common()),
        "by_issuer_top": dict(iss.most_common(20)),
        "by_year": dict(sorted(yr.items(), reverse=True)),
        "by_tax_policy_top": dict(tp.most_common(20)),
        "by_label_top": dict(lb.most_common(25)),
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n全量清单：%d 条（含发文字号 %d 条）" % (len(all_items), len(docs)))
    print("效力等级分布：")
    for k, v in eff.most_common():
        print("  %-22s %d" % (k, v))
    print("→ %s" % (OUT_DIR / "fgk_files.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
