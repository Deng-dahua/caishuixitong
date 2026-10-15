# -*- coding: utf-8 -*-
"""**案例 / 解读 / 问答正文**采集器 —— 遗留项④（"只有元数据+摘要，要采正文"）。

## 为什么需要
`config/legal_materials.json` 现有 2055 条材料（案例 966 / 解读 646 / 问答 443），
但每条**只有 `snippet`（摘要）**，且关联结论只到**法规级**（`granularity="law"`，
`granularity_note` 原话：「摘要未写明 ⇒ 条款级留空待人工，不猜」）。
⇒ 补上正文后，才能从**正文里的显式条号引用**把关联提升到条款级（遗留项②）。

## 正文来源（实测，2026-10-15）
| 材料 | 主机 | 正文容器 |
|---|---|---|
| 案例（966） | `www.chinatax.gov.cn` | `div#zoomcon`（`class="article-content"`） |
| 解读（646）/ 问答（443） | `fgk.chinatax.gov.cn` | `div.arc_cont` |

★ 两条链路的容器**不同**，必须按主机分派；正文提取实现**复用**
`scripts/_crawl_legal_texts.py`（同一套 HTML→文本规则，避免两处各写一份）。

## 纪律
1. 只做 HTML→纯文本，**不改写、不概括**；图片/附件**不下载**，仅记录 `has_attachment`。
2. 抽不出正文 ⇒ `content_kind="failed"` + `reason`，**不生成占位正文**。
3. 幂等 + 断点续传（按 `material_id` 一文件；`--force` 重采）。

用法
    ./.venv/Scripts/python.exe scripts/_crawl_material_texts.py --limit 5
    ./.venv/Scripts/python.exe scripts/_crawl_material_texts.py            # 全量 2055 条
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
sys.path.insert(0, str(ROOT / "scripts"))

import requests                                              # noqa: E402
from _crawl_legal_texts import extract_container, to_text    # noqa: E402

UA = "Mozilla/5.0 (compatible; caishuixitong-legal-indexer/1.0; +local-research)"
SLEEP = 1.0
MATERIALS = ROOT / "config" / "legal_materials.json"
OUT_DIR = ROOT / "data" / "legal_crawl" / "material_texts"
INDEX_FILE = ROOT / "data" / "legal_crawl" / "material_texts_index.json"

#: ★ 判"真抽不到"的下限（2026-10-15 修正）：原先设 120 字，**误伤问答类** ——
#   实测 118 条被判"正文过短"，实为**内容本身就短**（如「平台企业报送的收入信息
#   可否剔除刷单收入？」答案仅一两句，41~111 字）。二者必须区分：
#     · `body` 为空 / 极短（< MIN_BODY）⇒ 真抽不到（容器改版等），标 failed；
#     · `body` 非空但短 ⇒ **有效正文**，标 `html_fulltext_short` 并如实记长度，**不丢数据**。
MIN_BODY = 10
#: 短正文提示线（超过它算"正常长度"；低于它仍收，只加标记）
SHORT_HINT = 120

#: 主机 → 正文容器 **class 名**（实测；新增一种来源＝加一行）
#   ★ 案例页是 `<div class="article-content" id="zoomcon">` —— 容器要用 **class**（`article-content`）
#     而不是 id（`extract_container` 按 class 匹配）；两条链路的 class **不同**，故按主机分派。
CONTAINER_BY_HOST: Dict[str, str] = {
    "www.chinatax.gov.cn": "article-content",
    "fgk.chinatax.gov.cn": "arc_cont",
}

_S = requests.Session()
_S.trust_env = False
_S.headers.update({"User-Agent": UA})


def _container_for(url: str) -> str:
    """按主机选正文容器 class（未登记主机 ⇒ 退回政策法规库模板 `arc_cont`）。"""
    parts = str(url or "").split("/")
    host = parts[2] if len(parts) > 2 else ""
    return CONTAINER_BY_HOST.get(host, "arc_cont")


def fetch_one(url: str) -> Dict[str, Any]:
    for attempt in (1, 2, 3):
        try:
            r = _S.get(url, timeout=45, allow_redirects=True)
            if r.status_code != 200:
                if attempt == 3:
                    return {"ok": False, "http": r.status_code, "reason": f"HTTP {r.status_code}"}
                time.sleep(SLEEP)
                continue
            r.encoding = r.apparent_encoding or "utf-8"
            src = r.text
            body = to_text(extract_container(src, _container_for(url)))
            has_att = bool(re.search(r"(?i)\.(pdf|docx?|xlsx?|wps)(\?|\"|')", src))
            time.sleep(SLEEP)
            if len(body) < MIN_BODY:
                return {"ok": False, "http": 200, "body": body,
                        "reason": f"正文过短（{len(body)} 字）"}
            return {"ok": True, "http": 200, "body": body, "has_attachment": has_att}
        except Exception as exc:                              # noqa: BLE001
            if attempt == 3:
                return {"ok": False, "reason": f"{type(exc).__name__}: {str(exc)[:90]}"}
            time.sleep(SLEEP * 2)
    return {"ok": False, "reason": "未取到"}


def main() -> int:
    args = sys.argv[1:]
    force = "--force" in args
    only_failed = "--only-failed" in args
    limit: Optional[int] = None
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])
    only_kind = None
    if "--kind" in args:
        only_kind = args[args.index("--kind") + 1]

    d = json.loads(MATERIALS.read_text(encoding="utf-8"))
    mats: List[Dict[str, Any]] = [m for m in (d.get("materials") or [])
                                  if m.get("url") and (not only_kind or m.get("kind") == only_kind)]
    if only_failed:
        # ★ 只重跑**判据修正后需复核**的条目：已落盘但 `ok=False`（或 body 为空）的。
        #   用途：改了抽取/判据逻辑后免全量重采（2055 条 ≈ 40 分钟 ⇒ 只补漏网的百来条）。
        need: List[Dict[str, Any]] = []
        for m in mats:
            fp = OUT_DIR / f"{m['material_id']}.json"
            if not fp.exists():
                need.append(m)
                continue
            try:
                o = json.loads(fp.read_text(encoding="utf-8"))
            except Exception:                                 # noqa: BLE001
                need.append(m)
                continue
            if not o.get("ok") or not str(o.get("body") or "").strip():
                need.append(m)
        print("--only-failed：需重跑 %d / %d 条" % (len(need), len(mats)))
        mats = need
    print("目标材料：%d 条" % len(mats))
    if limit:
        mats = mats[:limit]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    done = skipped = 0
    failed: List[Dict[str, Any]] = []
    for i, m in enumerate(mats, 1):
        fp = OUT_DIR / f"{m['material_id']}.json"
        if fp.exists() and not force:
            try:
                if json.loads(fp.read_text(encoding="utf-8")).get("ok"):
                    skipped += 1
                    continue
            except Exception:                                 # noqa: BLE001
                pass
        res = fetch_one(m["url"])
        rec = {"material_id": m["material_id"], "kind": m.get("kind"), "title": m.get("title"),
               "url": m.get("url"), "published_at": m.get("published_at"),
               "ok": bool(res.get("ok")), "http": res.get("http"),
               "content_kind": ("html_fulltext" if res.get("ok") else "failed"),
               "content_len": len(res.get("body") or ""),
               "has_attachment": bool(res.get("has_attachment")),
               "reason": res.get("reason"), "body": res.get("body"),
               "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        if rec["ok"] and rec["content_len"] < SHORT_HINT:
            rec["content_kind"] = "html_fulltext_short"        # 有效但短（内容本身少）
        fp.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        if res.get("ok"):
            done += 1
        else:
            failed.append({"material_id": m["material_id"], "title": (m.get("title") or "")[:34],
                           "reason": rec.get("reason")})
        if i % 50 == 0 or i == len(mats):
            print("  %d/%d（成功 %d / 跳过 %d / 失败 %d）" % (i, len(mats), done, skipped, len(failed)))

    index: List[Dict[str, Any]] = []
    for fp in sorted(OUT_DIR.glob("*.json")):
        try:
            o = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:                                     # noqa: BLE001
            continue
        index.append({k: o.get(k) for k in ("material_id", "kind", "title", "url", "ok",
                                            "content_len", "content_kind", "has_attachment",
                                            "reason", "published_at")})
    from collections import Counter
    kj = Counter(x.get("kind") for x in index)
    okj = Counter(x.get("kind") for x in index if x.get("ok"))
    INDEX_FILE.write_text(json.dumps({
        "source": "www.chinatax.gov.cn + fgk.chinatax.gov.cn",
        "containers": CONTAINER_BY_HOST,
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "count": len(index), "ok_count": sum(1 for x in index if x.get("ok")),
        "by_kind": dict(kj.most_common()),
        "ok_by_kind": dict(okj.most_common()),
        "items": index,
        "_note": "★ 采集层产物：材料**正文全文**（HTML→纯文本）。图片/附件未下载，"
                 "仅记 has_attachment。关联提升唯一走 scripts/_gen_legal_materials.py 的重跑。",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n完成：成功 %d / 跳过 %d / 失败 %d → %s"
          % (sum(1 for x in index if x.get("ok")), skipped, len(failed), INDEX_FILE))
    if failed:
        print("失败（如实列出）：")
        for f in failed[:12]:
            print("  %s %s —— %s" % (f["material_id"], f["title"], f["reason"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
