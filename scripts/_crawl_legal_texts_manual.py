# -*- coding: utf-8 -*-
"""**非 fgk 来源**的现行法规正文采集器 —— 读 `config/legal_texts_manual_sources.json`。

## 为什么要单独一个采集器
`fgk` 法规库对**部分部门规章**只保留**历史版本**（页面 `span.xg` 效力标识为
「已修改」/「全文废止」）⇒ 按项目铁律**不得用旧版顶替现行文本**。
但"缺条文"同样有代价：条款级关联会指向不存在的条文。折中且诚实的做法：
从**其它官方来源**（中国政府网国务院公报、国家税务总局/省级局网站）取现行文本，
并把 **provenance 显式落盘**（`effect_source` / `effect_evidence` / `effective_from`），
由 `_load_legal_texts_full.py` 写进正文条目的 `_effect_source` —— 可逐条复核。

★ 实测来源形态（2026-10-16）：`gov.cn` 文章页正文在 `div#UCAP-CONTENT`，
  且**条号与正文常分属两个 `<span>`** ⇒ 提取后条号**独占一行**。
  该排版由切分器 `_load_legal_texts_full.split_articles` 的「条号独占一行」预处理合并
  （不在本采集器里做 —— 切分口径必须唯一）。

用法：
    ./.venv/Scripts/python.exe scripts/_crawl_legal_texts_manual.py [--force]
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "config" / "legal_texts_manual_sources.json"
OUT_DIR = ROOT / "data" / "legal_crawl" / "legal_texts"
INDEX = ROOT / "data" / "legal_crawl" / "legal_texts_manual_index.json"

UA = "Mozilla/5.0 (compatible; caishuixitong-legal-indexer/1.0; +local-research)"
MIN_BODY = 300                     # 低于此长度视为提取失败（整部法规不可能这么短）

_TAG_RE = re.compile(r"<[^>]+>")
_ENT = {"&ensp;": " ", "&nbsp;": " ", "&amp;": "&", "&ldquo;": "“", "&rdquo;": "”",
        "&mdash;": "—", "&hellip;": "…", "&lsquo;": "‘", "&rsquo;": "’", "&middot;": "·"}


def _strip_blocks(h: str) -> str:
    h = re.sub(r"(?is)<script.*?</script>", "", h)
    h = re.sub(r"(?is)<style.*?</style>", "", h)
    h = re.sub(r"(?is)<!--.*?-->", "", h)
    return h


def extract_by_id(html: str, node_id: str) -> str:
    """按 `id="<node_id>"` 取容器（**div 配平**，避免嵌套截断），返回纯文本。"""
    i = html.find('id="%s"' % node_id)
    if i < 0:
        i = html.find("id='%s'" % node_id)
    if i < 0:
        return ""
    start = html.find(">", i) + 1
    depth, end = 1, len(html)
    for m in re.finditer(r"<div\b[^>]*>|</div>", html[start:]):
        depth += 1 if not m.group(0).startswith("</") else -1
        if depth == 0:
            end = start + m.start()
            break
    return html[start:end]


def to_text(seg: str) -> str:
    t = _strip_blocks(seg)
    t = re.sub(r"(?i)<br\s*/?>", "\n", t)
    t = re.sub(r"(?i)</p\s*>", "\n", t)
    t = _TAG_RE.sub("\n", t)
    for a, b in _ENT.items():
        t = t.replace(a, b)
    t = t.replace("\u2002", " ").replace("\u3000", " ")
    t = re.sub(r"[ \t\xa0]+", " ", t)
    return "\n".join(x.strip() for x in t.split("\n") if x.strip())


def fetch_one(src: Dict[str, Any]) -> Dict[str, Any]:
    s = requests.Session()
    s.trust_env = False                                  # 不走系统代理（本项目实测必需）
    s.headers.update({"User-Agent": UA})
    out: Dict[str, Any] = {"ok": False, "http": None, "reason": None, "body": ""}
    try:
        r = s.get(src["url"], timeout=40)
        out["http"] = r.status_code
        r.encoding = r.apparent_encoding or "utf-8"
        if r.status_code != 200:
            out["reason"] = "HTTP %s" % r.status_code
            return out
        seg = extract_by_id(r.text, str(src.get("container") or ""))
        if not seg:
            out["reason"] = "未找到正文容器 id=%r" % src.get("container")
            return out
        body = to_text(seg)
        # ★ 效力证据必须**逐字出现**在正文里（不靠转述，机器可核）
        ev = str(src.get("effect_evidence") or "")
        if ev:
            key = re.sub(r"\s+", "", ev)
            if key not in re.sub(r"\s+", "", body):
                out["reason"] = "来源页面正文里**找不到登记的沿革句**（effect_evidence 对不上）⇒ 拒绝入库"
                return out
        out["body"] = body
        out["ok"] = len(body) >= MIN_BODY
        if not out["ok"]:
            out["reason"] = "正文过短（%d 字，阈值 %d）" % (len(body), MIN_BODY)
    except Exception as exc:                             # noqa: BLE001
        out["reason"] = "请求异常：%s" % exc
    return out


def main() -> int:
    args = sys.argv[1:]
    force = "--force" in args
    if not REG.exists():
        print("!! 缺 %s" % REG)
        return 2
    reg = json.loads(REG.read_text(encoding="utf-8"))
    sources: List[Dict[str, Any]] = reg.get("sources") or []
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("人工源目标：%d 部" % len(sources))

    results: List[Dict[str, Any]] = []
    for src in sources:
        sid = str(src.get("id") or "")
        fp = OUT_DIR / ("%s.json" % sid)
        if fp.exists() and not force:
            print("  跳过（已采）：%s" % sid)
            results.append(json.loads(fp.read_text(encoding="utf-8")))
            continue
        res = fetch_one(src)
        rec = {
            "id": sid,
            "url": src.get("url"),
            "title": src.get("title"),
            "doc_no": src.get("doc_no") or "",
            "effect_level": src.get("effect_level") or "税务部门规章",
            "effect": src.get("effect") if res.get("ok") else "",
            # ★ provenance：与 fgk 的 `span.xg` 效力标识**并列**的另一种效力依据
            "effect_source": src.get("publisher"),
            "effect_evidence": src.get("effect_evidence"),
            "version": src.get("version"),
            "effective_from": src.get("effective_from"),
            "written_date": src.get("published_at") or "",
            "ok": bool(res.get("ok")),
            "http": res.get("http"),
            "reason": res.get("reason"),
            "body": res.get("body") or "",
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        fp.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        print("  %s %s | ok=%s len=%d %s" % ("OK " if rec["ok"] else "FAIL", sid,
                                             rec["ok"], len(rec["body"]), rec["reason"] or ""))
        results.append(rec)

    INDEX.write_text(json.dumps({
        "schema": 1, "updated": time.strftime("%Y-%m-%d"),
        "note": "★ **非 fgk 来源**现行文本的采集回执（`effect_source`/`effect_evidence` 可逐条复核）。",
        "counts": {"total": len(results), "ok": sum(1 for r in results if r["ok"])},
        "items": [{k: v for k, v in r.items() if k != "body"} for r in results],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("→ %s" % INDEX)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
