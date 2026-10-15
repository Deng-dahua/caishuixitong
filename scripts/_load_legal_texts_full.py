# -*- coding: utf-8 -*-
"""**整部法全文 → 条款库**入库器（含**逐部时效核实**）—— 遗留项①的落地。

## 与既有两个脚本的分工（不得混用）
| 脚本 | 职责 |
|---|---|
| `scripts/_crawl_legal_texts.py` | **采集**：把 fgk 的整部法全文+页面效力标识抓下来（`data/legal_crawl/legal_texts/`） |
| `scripts/_load_legal_texts.py` | **人工逐条核实**入库（`_BATCH_*` 字面量，条目少而精） |
| **本脚本** | 把**采集到的整部法**按「第X条」切分后入库，并对**过时条文/过时法规逐部核实** |

## 时效核实的判据（遗留项①的原话：「对过时的条款、过时的法律法规全文进行一一核实」）
三道闸，**任一不过 ⇒ 该法规整体不入正文库**，并写入台账 `config/legal_texts_currency.json`：
- **A 页面效力标识**（`span.xg`，采集时原样抄录）：只接受 `全文有效`；
  `全文废止 / 全文失效 / 已修改` 一律**不入库**（★ 不拿旧版文本顶替现行文本 —— 报告一旦引用
  已废止条文，比"缺条文"更危险）；
- **B 版本登记交叉核实**（`config/legal_versions.json`）：登记 `status ∈ {expired, superseded}`
  的法规，即使页面写"全文有效"也**不入库**（两者不一致 ⇒ 记 `version_conflicts` 待人工裁定）；
- **C 效力标识缺失**（`span.xg` 取不到）⇒ 视为**未经核实**，不入库（保守：宁可缺，不可错用）。

## 切分纪律
- **只认行首条号**：`^第<中文数字>条[之一]?`。正文里"依照本法第二十三条规定"这类**行内引用**不切分。
- **章节标题与目录跳过**：`^第<中文数字>[章节编]` 既不作条文，也不并入上一条。
- **公布令（"中华人民共和国国务院令 第NNN号…"）与目录**落在第一个条号之前 ⇒ 自然丢弃。
- **逐字保留**：条文内容只做行拼接，**不改写、不概括、不补全**。

## 幂等与安全
- 按 `(law, article)` 去重：**已存在的条目一律保留**（人工录入的更可靠），
  若采集版与既有版**正文不同** ⇒ 记入 `content_conflicts` 供人工核对，**不覆盖**。
- 写入前断言：原有 `(law, article)` 集合必须**全部保留**（防误删）；条数不得减少。

用法
    ./.venv/Scripts/python.exe scripts/_load_legal_texts_full.py --dry-run    # 只报告
    ./.venv/Scripts/python.exe scripts/_load_legal_texts_full.py              # 入库
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TEXT_DIR = ROOT / "data" / "legal_crawl" / "legal_texts"
LIB_PATH = ROOT / "static" / "legal_library.json"
CURRENCY_PATH = ROOT / "config" / "legal_texts_currency.json"
VERSION_PATH = ROOT / "config" / "legal_versions.json"

#: A 闸：只接受这个效力标识
ALLOWED_EFFECT = "全文有效"
#: A 闸：明确拒绝的效力标识（如实登记，不用旧版顶替）
BLOCKED_EFFECTS = ("全文废止", "全文失效", "已修改")
#: B 闸：这些版本状态属"非现行"
BLOCKING_STATUS = ("expired", "superseded")

_CN = "一二三四五六七八九十百零〇两"
#: ★★ 条号**前置断言**（实测事故，2026-10-15）：条文起始的"第X条"前面**必须是空位/行首**，
#   不能紧贴汉字或字母 —— 否则「增值税法第三条所称货物…」中的**引用**会被当成条文起点，
#   把上一条切成两半（实测《增值税法实施条例》第二条只剩"增值税法"三个字，
#   第三条把三段"增值税法第三条所称…"全并进来）。汉字/字母/数字/全角数字均视为"紧贴"。
_GUARD = r"(?<![\u4e00-\u9fffA-Za-z0-9０-９])"
#: 定位行内**所有**条号（用于紧凑排版与"引用判伪"）
_ART_SEARCH = re.compile(rf"{_GUARD}第([{_CN}]+)条((?:之[{_CN}]+)?)")
#: 条文起始（要求条号在行首）
_ART_RE = re.compile(rf"^{_GUARD}第([{_CN}]+)条((?:之[{_CN}]+)?)[\s\u3000]*(.*)$")
#: 章节/编 标题行（`第一章　总　　则`）；★ 不含"条"，故不会与条文抢匹配
_SEC_RE = re.compile(rf"^{_GUARD}第[{_CN}]+[章节编]")
_NUM_RE = re.compile(rf"^第([{_CN}]+)条((?:之[{_CN}]+)?)$")

# ★★ 2026-10-15 收敛：中文数字解析改用**唯一权威** `engine/cnnum.py`（本模块原自带一份，
#   与 `_gen_legal_index.py` / `_gen_legal_mappings.py` 的同名实现构成多头维护）。
from engine.cnnum import cn_to_int as _cn_to_int, article_sort_key as _article_sort_key  # noqa: E402


def article_no(article: str) -> int:
    """条号 → 排序用整数（唯一权威 `engine.cnnum.article_sort_key`；带"之一"排在本条之后）。"""
    return _article_sort_key(article)


# ─────────────────────────── 切分 ───────────────────────────

def split_articles(body: str) -> List[Tuple[str, str]]:
    """整部法全文 → [(条号, 条文内容)]。见模块头「切分纪律」。

    ★ 实测两种排版都要吃下（2026-10-15）：
      ① **规整排版**：一条一行（多数法规）；
      ② **紧凑排版**：整部法挤在一行、条间用全角空格分隔（实测《对外合作开采海洋石油资源条例》
         等 `第一章　总则　　 第一条　…　　 第二条　…` 全在一行）⇒ 必须做**行内切分**。
      ③ 「章节标题 + 条文同行」⇒ 先丢弃条号之前那截（章节标题/目录），再从条号起处理。

    ★ 行内切分的**防误切**判据（不满足则**不拆**，整行只认第一个条号）：
      多命中时要求「首个条号序号 = 上一条序号 + 1」**且**序号严格递增。
      否则该行多半是**行内引用**（如「第十一条　依照本法第二条规定…」），拆开会把引用当条文。
    """
    out: List[Tuple[str, str]] = []
    state: Dict[str, Any] = {"no": None, "buf": [], "last": 0}

    def _flush() -> None:
        if state["no"] and state["buf"]:
            out.append((state["no"], "\n".join(state["buf"]).strip()))
        state["no"], state["buf"] = None, []

    for raw in str(body or "").split("\n"):
        line = raw.strip()
        if not line:
            continue
        m0 = _ART_SEARCH.search(line)
        if not m0:
            if _SEC_RE.match(line):                 # 纯章节标题行 ⇒ 上一条结束
                _flush()
                continue
            if state["no"] is not None:             # 上一条的续行（列举项等）
                state["buf"].append(line)
            # 条号之前的前言/目录/公布令 ⇒ 丢弃
            continue
        if m0.start() > 0:
            line = line[m0.start():]                # 丢弃条号前的章节标题/目录文字

        hits = list(_ART_SEARCH.finditer(line))
        parts: List[Tuple[str, str]] = []
        for i, m in enumerate(hits):
            end = hits[i + 1].start() if i + 1 < len(hits) else len(line)
            parts.append((f"第{m.group(1)}条{m.group(2) or ''}", line[m.end():end].strip()))
        if len(parts) > 1:
            nums = [article_no(a) for a, _ in parts]
            continuous = nums[0] == state["last"] + 1 and all(
                nums[i] < nums[i + 1] for i in range(len(nums) - 1))
            if not continuous:
                # ★ 疑似行内引用 ⇒ 不拆。**必须重建为「该条号 + 整行余下全部」**：
                #   直接取 parts[:1] 会把后半截（第二个条号之后的内容）丢掉
                #   ——实测《企业所得税法》第三十七条只留下"对非居民企业取得本法"7 个字。
                parts = [(parts[0][0], line[hits[0].end():].strip())]
        for art, content in parts:
            # ★ 条号必须**严格递增**才作新条文：否则该行是**行内引用**（实测《企业所得税法》里
            #   「第三条第三款规定的所得，适用税率为20％」以"第三条"起行，被误判为新条文，
            #   会把真正的第三条挤掉）⇒ 此时按"上一条的续行"处理，内容归位不回丢。
            if article_no(art) <= state["last"]:
                if state["no"] is not None and content:
                    state["buf"].append(art + (("　" + content) if content else ""))
                continue
            _flush()
            state["no"], state["last"] = art, article_no(art)
            if content:
                state["buf"].append(content)
    _flush()
    return [(a, c) for a, c in out if c]


# ─────────────────────────── 时效核实 ───────────────────────────

def _canon(law: str) -> str:
    from engine.legal_version import canonical_law
    return canonical_law(law)


def _version_status(law: str) -> Tuple[str, str]:
    """查 `config/legal_versions.json` 的登记状态。返回 (status, doc)。未登记 ⇒ ("", "")。"""
    try:
        d = json.loads(VERSION_PATH.read_text(encoding="utf-8"))
    except Exception:                                          # noqa: BLE001
        return "", ""
    for e in (d.get("laws") or []):
        if _canon(str(e.get("law") or "")) == law:
            return str(e.get("status") or "").lower(), str(e.get("source") or "")
    return "", ""


def _ws_key(s: str) -> str:
    """比较用归一：**去掉全部空白**。

    ★ 实测（2026-10-15）：正文库既有条目是人工录入（段落间无空格），采集版保留段落间的
      排版空格 ⇒ 直接字符串比较会产生大量**假冲突**（354 处中绝大多数是此因）。
      比对内容是否真的不同，必须先抹掉空白差异。
    """
    return re.sub(r"\s+", "", str(s or ""))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只报告，不写盘")
    args = ap.parse_args()

    if not TEXT_DIR.exists():
        print("!! 缺 %s（先跑 scripts/_crawl_legal_texts.py）" % TEXT_DIR)
        return 2

    lib: List[Dict[str, Any]] = json.loads(LIB_PATH.read_text(encoding="utf-8"))
    existing = {(str(x.get("law") or ""), str(x.get("article") or "")) for x in lib}
    existing_by_key = {(str(x.get("law") or ""), str(x.get("article") or "")): str(x.get("content") or "")
                       for x in lib}
    before = len(lib)
    print("现有正文库 %d 条" % before)

    loaded: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []
    conflicts: List[Dict[str, Any]] = []
    content_conflicts: List[Dict[str, Any]] = []
    no_article: List[Dict[str, Any]] = []

    for fp in sorted(TEXT_DIR.glob("*.json")):
        try:
            o = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as exc:                               # noqa: BLE001
            blocked.append({"id": fp.stem, "reason": "采集文件读不出来：%s" % exc})
            continue
        title = str(o.get("title") or "").strip()
        effect = str(o.get("effect") or "").strip()
        date = str(o.get("written_date") or "").strip()
        law = _canon(title)
        rec = {"id": o.get("id"), "title": title, "law": law, "level": o.get("effect_level"),
               "effect": effect, "written_date": date}

        if not o.get("ok"):
            blocked.append({**rec, "reason": "采集失败：%s" % (o.get("reason") or "未取到正文")})
            continue
        # ── A 闸：页面效力标识 ──
        if effect != ALLOWED_EFFECT:
            r = ("页面效力标识为 %r（非『%s』）⇒ 不入库：这是**过时/非现行**文本，"
                 "用来引用会与法定原文不符" % (effect or "（缺失）", ALLOWED_EFFECT))
            if not effect:
                r = "页面效力标识**缺失**（span.xg 取不到）⇒ 未经核实，保守不入库"
            blocked.append({**rec, "reason": r})
            continue
        # ── B 闸：版本登记交叉核实 ──
        st, src = _version_status(law)
        if st in BLOCKING_STATUS:
            blocked.append({**rec, "reason": "版本登记 status=%s（%s）与页面『全文有效』**不一致** ⇒ "
                                            "待人工裁定，本轮回不入库" % (st, src[:60])})
            conflicts.append({**rec, "registry_status": st, "registry_source": src})
            continue

        # ── 切分 ──
        arts = split_articles(o.get("body") or "")
        if not arts:
            no_article.append({**rec, "reason": "全文切不出『第X条』条文（可能是公布令/决定类文本）"})
            continue
        src_text = "《%s》%s（%s，成文日期 %s）" % (
            title, (o.get("doc_no") + "，" if o.get("doc_no") else ""), effect, date or "未知")
        n_new = 0
        for art, content in arts:
            key = (law, art)
            if key in existing:
                if content and _ws_key(existing_by_key.get(key)) != _ws_key(content):
                    content_conflicts.append({"law": law, "article": art,
                                              "existing_len": len(existing_by_key[key]),
                                              "crawled_len": len(content),
                                              "note": "两版正文**实质不同**（已抹空白差）⇒ "
                                                      "保留既有（人工核实版），不覆盖，待人工核对"})
                continue
            existing.add(key)
            existing_by_key[key] = content
            lib.append({"law": law, "article": art, "content": content, "source": src_text,
                        "_from": "crawl:fgk", "_effect": effect, "_written_date": date})
            n_new += 1
        loaded.append({**rec, "articles": len(arts), "new_articles": n_new})

    # ── 安全断言：不得掉条 ──
    after_keys = {(str(x.get("law") or ""), str(x.get("article") or "")) for x in lib}
    missing = [k for k in existing_by_key if k not in after_keys]
    if len(lib) < before or missing:
        print("!! 断言失败：条数 %d→%d，丢失 %d 条 ⇒ **中止写盘**" % (before, len(lib), len(missing)))
        return 3

    new_total = len(lib)
    print("切分入库：新增 %d 条（法规 %d 部）⇒ 正文库 %d → %d"
          % (new_total - before, len(loaded), before, new_total))
    print("未入库：%d 部（效力非『全文有效』/采集失败/切不出条文）" % len(blocked))
    print("切不出条文：%d 部｜正文冲突：%d 处｜版本冲突：%d 部"
          % (len(no_article), len(content_conflicts), len(conflicts)))

    if args.dry_run:
        print("\n（--dry-run：未写盘）")
        for b in blocked[:12]:
            print("  跳过 %s —— %s" % (b.get("title", b.get("id"))[:34], str(b.get("reason"))[:60]))
        return 0

    # ── 排序：按 (法名, 条号) 使同一部法条文连续，便于人工核对 ──
    lib.sort(key=lambda x: (str(x.get("law") or ""), article_no(str(x.get("article") or "")),
                            str(x.get("article") or "")))
    LIB_PATH.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    CURRENCY_PATH.write_text(json.dumps({
        "schema": 1,
        "updated": time.strftime("%Y-%m-%d"),
        "source": "data/legal_crawl/legal_texts/*.json（fgk 政策法规库整部法全文）",
        "policy": "★ 只入页面效力标识＝『全文有效』且版本登记非 expired/superseded 的法规；"
                  "其余**一律不入库**并在此逐部登记原因 —— 不拿过时文本顶替现行文本"
                  "（引用已废止条文比缺条文更危险）。",
        "counts": {
            "scanned": len(loaded) + len(blocked) + len(no_article),
            "loaded_laws": len(loaded),
            "loaded_articles_new": new_total - before,
            "blocked_laws": len(blocked),
            "no_article_laws": len(no_article),
            "version_conflicts": len(conflicts),
            "content_conflicts": len(content_conflicts),
            "library_total": new_total,
        },
        "blocked": blocked,
        "no_article": no_article,
        "version_conflicts": conflicts,
        "content_conflicts": content_conflicts,
        "loaded": loaded,
        "_note": "★ 本台账是**时效核实的过程证据**：每一部未入库的法规都写明原因，可逐条复核。",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("→ %s" % LIB_PATH)
    print("→ %s" % CURRENCY_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
