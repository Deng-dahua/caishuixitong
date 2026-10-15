# -*- coding: utf-8 -*-
"""**法律 / 行政法规全文**采集器 —— 把「正文」补进语料（STEP-EXT-LEGAL 遗留项 ①）。

## 背景（遗留项的实测状态）
上一轮只采了 fgk 的**列表元数据**（5475 条：标题/文号/时间/URL），
`static/legal_library.json` 里只有 **131 条**散条文（红线实际引用的那些），
⇒「法律/行政法规正文多数未入正文库」。本脚本补这一环。

## 正文从哪来（实测，2026-10-15）
| 尝试 | 结果 |
|---|---|
| `http://www.chinatax.gov.cn/zcfgk/{ch}/{id}/content.html` | **404**（列表给的是 www 域，政策法规库正文不在该域） |
| `https://fgk.chinatax.gov.cn/zcfgk/{ch}/{id}/content.html` | **200，含整部法全文** |

⇒ **域名必须换成 `fgk.chinatax.gov.cn`**（列表 `url` 字段的域名不可直接用）。

## 页面结构（实测，稳定）
```html
<p class="arc_date"><span class="xg">全文有效</span>&nbsp;<span class="date">成文日期：2025-10-28</span></p>
...
<div class="arc_cont"> ... 正文全部 <p> 段落 ... </div>
```
- **效力标识** = `span.xg`（实测取值：`全文有效` / `全文失效` …）。★ 正文里出现「尚未生效」等词
  **不是**效力标识（实测 `c5212285` 正文第五十七条含该词）⇒ **只认 `span.xg`**，不得全文关键词判效力。
- **成文日期** = `span.date`。
- **正文** = `div.arc_cont`（用 **div 平衡匹配**截取；后续有版权/相关推荐等同级 div，不能到文件尾）。

## 纪律
1. **逐部核实、如实标注**：效力标识原样抄录，**不解释、不推断**；正文抽不出就写
   `content_kind="failed"` + `reason`，**绝不生成占位正文**。
2. **幂等 + 断点续传**：按条目 id 一文件，已存在的跳过（`--force` 重采）。
3. **不改内容**：正文只做 HTML→纯文本与实体还原，**不删句、不改字**。
4. 入库（切分成条文写 `static/legal_library.json`）仍走 `scripts/_load_legal_texts.py` —— 本脚本**只采集**。

用法
    ./.venv/Scripts/python.exe scripts/_crawl_legal_texts.py --dry-run   # 只列目标，不发请求
    ./.venv/Scripts/python.exe scripts/_crawl_legal_texts.py --limit 5   # 试跑 5 条
    ./.venv/Scripts/python.exe scripts/_crawl_legal_texts.py             # 全量（法律 + 行政法规）
"""
from __future__ import annotations

import html as _html
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests                                              # noqa: E402

UA = "Mozilla/5.0 (compatible; caishuixitong-legal-indexer/1.0; +local-research)"
HOST = "https://fgk.chinatax.gov.cn"
SLEEP = 1.2
OUT_DIR = ROOT / "data" / "legal_crawl"
TEXT_DIR = OUT_DIR / "legal_texts"
LIST_FILE = OUT_DIR / "fgk_files.json"
INDEX_FILE = OUT_DIR / "legal_texts_index.json"
REPORT_FILE = OUT_DIR / "legal_texts_report.json"

#: 采集范围（效力等级）。新增一类＝加一项。
TARGET_LEVELS: Tuple[str, ...] = ("法律", "行政法规")

#: 极短正文判定阈值（小于此值视为抽取失败，如实标注而不入库）
MIN_BODY = 200

_S = requests.Session()
_S.trust_env = False                     # ★ 关环境代理（本机 http_proxy 会让请求静默失败）
_S.headers.update({"User-Agent": UA, "Referer": HOST + "/zcfgk/index.html"})


# ─────────────────────────── URL 规范化 ───────────────────────────

_URL_RE = re.compile(r"/zcfgk/(?P<ch>c\d+)/(?P<id>c\d+)/content\.html")


def to_fgk_url(url: str) -> str:
    """把列表里的 www 域 URL 换成 fgk 域（实测 www 域 404）。

    >>> to_fgk_url("http://www.chinatax.gov.cn/zcfgk/c100009/c5237365/content.html")
    'https://fgk.chinatax.gov.cn/zcfgk/c100009/c5237365/content.html'
    """
    m = _URL_RE.search(str(url or ""))
    return f"{HOST}/zcfgk/{m.group('ch')}/{m.group('id')}/content.html" if m else ""


def item_id(url: str) -> str:
    """条目唯一 id（取 URL 末段前的 `cNNNNNN`）。无则空串。"""
    m = _URL_RE.search(str(url or ""))
    return m.group("id") if m else ""


# ─────────────────────────── HTML → 正文 ───────────────────────────

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_blocks(src: str, tag: str) -> str:
    return re.sub(rf"(?is)<{tag}\b.*?</{tag}>", "", src)


def extract_container(src: str, class_name: str) -> str:
    """按 **div 平衡匹配**取 `<div class="...{class_name}...">` 的内部 HTML。

    ★ 不能用到文件尾：`.arc_cont` 之后仍有版权/相关推荐等同级 div。
    """
    m = re.search(rf'<div\b[^>]*class="[^"]*\b{re.escape(class_name)}\b[^"]*"[^>]*>', src)
    if not m:
        return ""
    start = m.end()
    depth = 1
    for t in re.finditer(r"<div\b[^>]*>|</div>", src[start:]):
        depth += -1 if t.group(0).startswith("</") else 1
        if depth == 0:
            return src[start:start + t.start()]
    return src[start:]


def to_text(fragment: str) -> str:
    """HTML 片段 → 纯文本（保留段落换行、全角空格；实体还原；不改字）。"""
    if not fragment:
        return ""
    t = _strip_blocks(fragment, "script")
    t = _strip_blocks(t, "style")
    # 段落/换行标签 → 换行（先于去标签，否则段落会粘连）
    t = re.sub(r"(?i)<br\s*/?>", "\n", t)
    t = re.sub(r"(?i)</(p|div|h[1-6]|li|tr)>", "\n", t)
    t = _TAG_RE.sub("", t)
    t = _html.unescape(t)
    t = t.replace("\u00a0", " ").replace("\u2002", " ").replace("\u2003", " ")
    # 空段落（页面上是 `<p>&ensp;</p>` 排版空行）一律丢弃 —— 否则正文里
    # 会出现大量空行，切分条文时噪声大。非空段落各占一行，保序。
    out = [re.sub(r"[ \t]+", " ", ln).strip() for ln in t.split("\n")]
    out = [ln for ln in out if ln]
    return "\n".join(out).strip()


def _span_value(src: str, cls: str) -> str:
    m = re.search(rf'<span\b[^>]*class="[^"]*\b{re.escape(cls)}\b[^"]*"[^>]*>(.*?)</span>',
                  src, re.S)
    return _TAG_RE.sub("", _html.unescape(m.group(1))).strip() if m else ""


def fetch_one(url: str) -> Dict[str, Any]:
    """抓一部法的页面，返回 {ok, body, effect, written_date, http, reason, title}。"""
    for attempt in (1, 2, 3):
        try:
            r = _S.get(url, timeout=45, allow_redirects=True)
            if r.status_code != 200:
                reason = f"HTTP {r.status_code}"
                time.sleep(SLEEP)
                if attempt == 3:
                    return {"ok": False, "reason": reason, "http": r.status_code}
                continue
            r.encoding = r.apparent_encoding or "utf-8"
            src = r.text
            body = to_text(extract_container(src, "arc_cont"))
            eff = _span_value(src, "xg")
            date_txt = _span_value(src, "date")
            m = re.search(r"(\d{4}-\d{2}-\d{2})", date_txt)
            title = ""
            mt = re.search(r"<title>(.*?)</title>", src, re.S)
            if mt:
                title = _TAG_RE.sub("", _html.unescape(mt.group(1))).strip()
            time.sleep(SLEEP)
            if len(body) < MIN_BODY:
                return {"ok": False, "http": 200, "reason": f"正文过短（{len(body)} 字）",
                        "effect": eff, "written_date": m.group(1) if m else "",
                        "title": title, "body": body}
            return {"ok": True, "http": 200, "body": body, "effect": eff,
                    "written_date": m.group(1) if m else "", "title": title}
        except Exception as exc:                              # noqa: BLE001
            if attempt == 3:
                return {"ok": False, "reason": f"{type(exc).__name__}: {str(exc)[:90]}"}
            time.sleep(SLEEP * 2)
    return {"ok": False, "reason": "未取到"}


# ─────────────────────────── 主流程 ───────────────────────────

def load_targets(levels: Tuple[str, ...]) -> List[Dict[str, Any]]:
    if not LIST_FILE.exists():
        raise SystemExit(f"!! 缺 {LIST_FILE}（先跑 scripts/_crawl_fgk_files.py）")
    data = json.loads(LIST_FILE.read_text(encoding="utf-8"))
    out: List[Dict[str, Any]] = []
    for it in data.get("items") or []:
        if (it.get("effect_level") or "") not in levels:
            continue
        iid = item_id(it.get("url"))
        if not iid:
            continue
        out.append({"id": iid, "url": to_fgk_url(it.get("url")),
                    "title": it.get("title") or "", "doc_no": it.get("doc_no") or "",
                    "effect_level": it.get("effect_level") or "",
                    "channel_code": it.get("channel_code") or "",
                    "published_at": it.get("published_at") or "",
                    "issuer": it.get("issuer") or "",
                    "list_url": it.get("url") or ""})
    return sorted(out, key=lambda r: (r["effect_level"], r["title"]))


def main() -> int:
    args = sys.argv[1:]
    dry = "--dry-run" in args
    force = "--force" in args
    limit: Optional[int] = None
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])
    levels = TARGET_LEVELS
    if "--levels" in args:
        levels = tuple(args[args.index("--levels") + 1].split(","))

    targets = load_targets(levels)
    print("目标（%s）：%d 条" % ("/".join(levels), len(targets)))
    if limit:
        targets = targets[:limit]
    if dry:
        for t in targets[:40]:
            print("  [%s] %s → %s" % (t["effect_level"], t["title"][:44], t["url"]))
        print("  …（共 %d 条）" % len(targets))
        return 0

    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    done = 0
    skipped = 0
    failed: List[Dict[str, Any]] = []
    for i, t in enumerate(targets, 1):
        fp = TEXT_DIR / f"{t['id']}.json"
        if fp.exists() and not force:
            try:
                prev = json.loads(fp.read_text(encoding="utf-8"))
                if prev.get("ok"):
                    skipped += 1
                    continue
            except Exception:                                 # noqa: BLE001
                pass
        res = fetch_one(t["url"])
        # ★ 页面 `<title>` 是全站标题（"国家税务总局政策法规库"），**不是法名**；
        #   法名以列表元数据为准（权威），页面 title 只留作对照。
        rec = {**t, "page_title": res.get("title") or "",
               **{k: v for k, v in res.items() if k not in ("ok", "title")},
               "ok": bool(res.get("ok")), "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        if res.get("ok"):
            rec["content_len"] = len(res.get("body") or "")
            rec["content_kind"] = "html_fulltext"
            done += 1
        else:
            rec["content_len"] = len(res.get("body") or "")
            rec["content_kind"] = "failed"
            failed.append({"id": t["id"], "title": t["title"], "reason": rec.get("reason")})
        fp.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        if i % 10 == 0 or i == len(targets):
            print("  %d/%d（成功新增 %d / 跳过 %d / 失败 %d）"
                  % (i, len(targets), done, skipped, len(failed)))

    # 索引（断点续跑时也重扫目录，保证与磁盘一致）
    index: List[Dict[str, Any]] = []
    for fp in sorted(TEXT_DIR.glob("*.json")):
        try:
            o = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:                                     # noqa: BLE001
            continue
        index.append({k: o.get(k) for k in
                      ("id", "title", "doc_no", "effect_level", "channel_code",
                       "written_date", "effect", "ok", "content_len", "content_kind",
                       "url", "published_at", "issuer", "reason")})
    INDEX_FILE.write_text(json.dumps({
        "source": "fgk.chinatax.gov.cn（政策法规库）",
        "host": HOST,
        "levels": list(levels),
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "count": len(index),
        "ok_count": sum(1 for x in index if x.get("ok")),
        "items": index,
        "_note": "★ 采集层产物：整部法**全文** + 页面原样效力标识（span.xg）。"
                 "效力判定入库时与 config/legal_versions.json 交叉核实；"
                 "入库唯一走 scripts/_load_legal_texts.py。",
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    from collections import Counter
    eff = Counter((x.get("effect") or "（无标识）") for x in index if x.get("ok"))
    lvl = Counter((x.get("effect_level") or "?") for x in index)
    REPORT_FILE.write_text(json.dumps({
        "count": len(index), "ok": len([x for x in index if x.get("ok")]),
        "by_effect_level": dict(lvl.most_common()),
        "by_effect_tag": dict(eff.most_common()),
        "failed": failed,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n完成：成功 %d / 跳过 %d / 失败 %d → %s"
          % (sum(1 for x in index if x.get("ok")), skipped, len(failed), INDEX_FILE))
    if eff:
        print("页面效力标识分布：")
        for k, v in eff.most_common():
            print("  %-12s %d" % (k, v))
    if failed:
        print("失败条目（如实列出，不生成占位正文）：")
        for f in failed[:15]:
            print("  %s %s —— %s" % (f["id"], f["title"][:34], f["reason"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
