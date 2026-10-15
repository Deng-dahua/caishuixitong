# -*- coding: utf-8 -*-
"""国家法律法规数据库（`flk.npc.gov.cn`）抓取器 —— **法律/行政法规/司法解释**的权威元数据与关系链。

## 为什么需要它（实测结论）
税务总局统一检索接口（`www.chinatax.gov.cn/search5`）**覆盖不了「法律」与部分「行政法规」**：
实测「中华人民共和国刑法 / 税收征收管理法 / 行政处罚法 / 发票管理办法 / 征管法实施细则」
检索命中数均为 0（候选返回的全是税务新闻）。根因：`fgk` 库收录**税务总局及财税部门文件**，
法律（全国人大）与行政法规（国务院）不在其范围。
⇒ 按用户裁定（E1）：**法律/行政法规/司法解释改用全国人大官方库 flk**；
  总局文件/解读/问答仍走三源（`scripts/_crawl_legal_topics.py`）。

## flk 接口（实测反解，2026-10-15）
| 接口 | 方式 | 说明 |
|---|---|---|
| `/law-search/search/list` | POST | 检索。`searchType` 1=精确 2=模糊；`flfgCodeId` 过滤层级 |
| `/law-search/search/enumData` | GET | 分类字典（`flfgfl`：100宪法/101法律/201行政法规/220监察法规/221地方法规/311司法解释） |
| `/law-search/search/flfgDetails` | GET `?bbbs=` | 详情：元数据 + **`lsyg` 历史沿革** + **`xgzl` 相关制度** + `ossFile` |

**时效性 `sxx`（实测自前端枚举 `L4e`）**：`1=已废止` `2=已修改` `3=有效` `4=尚未生效`
——与指令 3.3 的效力状态过滤规则直接对应。

## 正文说明（**如实声明边界**）
flk 正文存于 OSS（`.docx`/`.ofd`），下载链接为**内网地址**（`obs-bj2-internal…`），
公网不可取；阅读器为 OFD 专用。⇒ 本脚本**只取元数据与关系链**，
**不抓正文**；正文补录仍走项目既有唯一入口 `scripts/_load_legal_texts.py`（人工核实后录入）。

## 用法
    ./.venv/Scripts/python.exe scripts/_crawl_flk_laws.py            # 抓 config/legal_law_codes.json 全部法
    ./.venv/Scripts/python.exe scripts/_crawl_flk_laws.py --only 法律,行政法规
    ./.venv/Scripts/python.exe scripts/_crawl_flk_laws.py --names 中华人民共和国刑法,中华人民共和国发票管理办法
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
BASE = "https://flk.npc.gov.cn"
SEARCH = BASE + "/law-search/search/list"
DETAIL = BASE + "/law-search/search/flfgDetails"
SLEEP = 1.5
OUT_DIR = ROOT / "data" / "legal_crawl"

#: ★★ 2026-10-15 实测事故：本机环境有 `http_proxy`，`requests` **默认读环境代理** ⇒
#   连 flk 时 `ProxyError: Tunnel connection failed: 502`（curl 侧因加 `--noproxy '*'` 才通）。
#   修法：统一关掉环境代理（`trust_env=False`），否则**抓取静默全失败**。
_S = requests.Session()
_S.trust_env = False
_S.headers.update({"User-Agent": UA})

#: 时效性（实测自前端枚举；与指令 3.3 效力状态过滤规则对应）
SXX_CN: Dict[int, str] = {1: "已废止", 2: "已修改", 3: "有效", 4: "尚未生效"}
#: 层级 codeId（enumData.flfgfl）
LEVEL_CODE: Dict[str, int] = {"宪法": 100, "法律": 101, "行政法规": 201,
                              "监察法规": 220, "地方法规": 221, "司法解释": 311}
#: 指令 3.3：只有「已废止/已失效」不抓正文（但记目录）
FETCHABLE_SXX = {2, 3, 4}          # 已修改 / 有效 / 尚未生效


def _post(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    r = _S.post(path, json=payload, timeout=30,
                headers={"Referer": BASE + "/", "Content-Type": "application/json"})
    r.raise_for_status()
    time.sleep(SLEEP)
    try:
        return r.json()
    except Exception:                                        # noqa: BLE001
        return {}


def _get(path: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    r = _S.get(path, params=params, timeout=30, headers={"Referer": BASE + "/"})
    r.raise_for_status()
    time.sleep(SLEEP)
    try:
        return r.json()
    except Exception:                                        # noqa: BLE001
        return {}


def _clean(s: Any) -> str:
    """去 flk 的 `<em class='highlight'>` 高亮标签。"""
    return re.sub(r"<[^>]+>", "", str(s or "")).strip()


def search_law(title: str, *, level_code: Optional[int] = None) -> List[Dict[str, Any]]:
    """精确检索一部法（`searchType=1`）。可选按层级过滤。"""
    payload: Dict[str, Any] = {
        "searchRange": 1, "sxrq": [], "gbrq": [], "searchType": 1, "sxx": [],
        "gbrqYear": [], "flfgCodeId": ([level_code] if level_code else []),
        "zdjgCodeId": [], "searchContent": title, "pageNum": 1, "pageSize": 20,
    }
    d = _post(SEARCH, payload)
    rows = d.get("rows") or []
    out = []
    for x in rows:
        if not isinstance(x, dict):
            continue
        out.append({
            "bbbs": x.get("bbbs"),
            "title": _clean(x.get("title")),
            "flxz": x.get("flxz"),                    # 法律性质（法律/行政法规/…）
            "zdjg_name": x.get("zdjgName"),           # 制定机关
            "gbrq": x.get("gbrq"),                    # 公布日期
            "sxrq": x.get("sxrq"),                    # 施行日期
            "sxx": x.get("sxx"),                      # 时效性编码
            "sxx_cn": SXX_CN.get(x.get("sxx"), "未知"),
            "flfg_code_id": x.get("flfgCodeId"),
        })
    return out


def detail(bbbs: str) -> Dict[str, Any]:
    d = _get(DETAIL, {"bbbs": bbbs})
    return d.get("data") or {}


def _pick(cands: List[Dict[str, Any]], want: str) -> Optional[Dict[str, Any]]:
    """从候选里挑**标题与目标完全一致**且**时效性最优**的一条（有效 > 尚未生效 > 已修改）。"""
    want_n = re.sub(r"^中华人民共和国", "", want).strip()
    same = [c for c in cands
            if re.sub(r"^中华人民共和国", "", c["title"]).strip() == want_n]
    if not same:
        return None
    rank = {3: 0, 4: 1, 2: 2, 1: 3}
    same.sort(key=lambda c: rank.get(c.get("sxx"), 9))
    return same[0]


def crawl(names: Optional[List[str]] = None,
          levels: Optional[List[str]] = None) -> int:
    reg = json.loads((ROOT / "config" / "legal_law_codes.json").read_text(encoding="utf-8"))
    laws = reg["laws"]
    if names:
        laws = [l for l in laws if l["name"] in names]
    if levels:
        laws = [l for l in laws if l.get("level") in levels]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("flk 抓取 %d 部法（层级过滤：%s）" % (len(laws), levels or "无"))

    out: List[Dict[str, Any]] = []
    for i, l in enumerate(laws, 1):
        # 检索时带上「中华人民共和国」变体（flk 标题多为全称）
        cands = search_law(l["name"])
        if not cands:
            cands = search_law("中华人民共和国" + l["name"])
        best = _pick(cands, l["name"])
        rec: Dict[str, Any] = {"law_code": l["code"], "law_name": l["name"],
                               "level": l.get("level"), "candidates_n": len(cands),
                               "candidates": [{k: c[k] for k in
                                               ("title", "flxz", "zdjg_name", "gbrq", "sxx_cn")}
                                              for c in cands[:4]],
                               "matched": None}
        if not best:
            # ★ 未命中要有**原因分类**（不是笼统"失败"）：
            #   flk = 国家法律法规数据库（全国人大）⇒ **只收 法律/行政法规/司法解释**；
            #   项目注册表里的 部门规章/规范性文件（总局公告、财税文件…）**本就不在其范围**
            #   ⇒ 标注 `out_of_scope`（这类由 fgk 全量库承担），与"该收未收"区分开。
            lv = str(l.get("level") or "")
            rec["miss_reason"] = ("out_of_scope" if lv not in ("法律", "行政法规", "司法解释", "宪法")
                                  else "not_found_in_flk")
            rec["miss_note"] = ("flk 只收法律/行政法规/司法解释 ⇒ 本层级由 fgk 全量库承担"
                                if rec["miss_reason"] == "out_of_scope" else "应属 flk 范围但未检索到，待人工核查")
        if best:
            rec["matched"] = {k: v for k, v in best.items() if k != "bbbs"}
            rec["matched"]["bbbs"] = best["bbbs"]
            det = detail(best["bbbs"])
            if det:
                rec["doc_num_from_xgzl"] = [
                    {"title": _clean(x.get("title")), "busi_type": x.get("busiType"),
                     "file_type": x.get("fileType"), "file_id": x.get("fileId")}
                    for x in (det.get("xgzl") or []) if isinstance(x, dict)]
                rec["history"] = [
                    {"title": _clean(x.get("title")), "gbrq": x.get("gbrq"),
                     "bbbs": x.get("bbbs")}
                    for x in (det.get("lsyg") or []) if isinstance(x, dict)]
                rec["oss_file"] = det.get("ossFile")
                rec["related_docs_n"] = len(det.get("xgwj") or [])
        print("  [%d/%d] %-32s 候选 %-3d %s"
              % (i, len(laws), l["name"][:30], len(cands),
                 ("→ %s %s/%s" % (rec["matched"]["gbrq"], rec["matched"]["sxx_cn"],
                                  rec["matched"]["flxz"])) if rec["matched"] else "未命中"))
        out.append(rec)

    matched = sum(1 for r in out if r["matched"])
    oos = sum(1 for r in out if r.get("miss_reason") == "out_of_scope")
    nf = sum(1 for r in out if r.get("miss_reason") == "not_found_in_flk")
    from collections import Counter
    _lv = Counter((r["matched"] or {}).get("flxz") for r in out if r["matched"])
    _sx = Counter((r["matched"] or {}).get("sxx_cn") for r in out if r["matched"])
    pf = OUT_DIR / "flk_laws.json"
    pf.write_text(json.dumps({
        "source": "flk.npc.gov.cn（国家法律法规数据库，全国人大官方）",
        "scope": "只收 法律 / 行政法规 / 司法解释（部门规章与规范性文件不在其范围）",
        "api": {"search": SEARCH, "detail": DETAIL},
        "sxx_cn": SXX_CN, "level_code": LEVEL_CODE,
        "laws_n": len(out), "matched_n": matched,
        "out_of_scope_n": oos, "not_found_n": nf,
        "by_level": dict(_lv.most_common()), "by_effect": dict(_sx.most_common()),
        "laws": out,
        "_note": "★ 只取元数据与关系链；**正文**存于内网 OSS（公网不可取）⇒ 正文补录仍走 "
                 "`scripts/_load_legal_texts.py`（人工核实）。`sxx` 为效力状态编码。"
                 "★ 未命中分两类：`out_of_scope`（本层级不属 flk 收录范围，由 fgk 承担）/ "
                 "`not_found_in_flk`（应属其范围但未检索到，待人工核查）。",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n命中 %d / %d（不在 flk 范围 %d，应属范围未检索到 %d）"
          % (matched, len(out), oos, nf))
    print("层级分布:", dict(_lv), "| 效力分布:", dict(_sx))
    print("→ %s" % pf)
    miss = [r["law_name"] for r in out if not r["matched"] and r.get("miss_reason") == "not_found_in_flk"]
    if miss:
        print("★ 应属 flk 范围但未检索到（待人工核查）：")
        for m in miss:
            print("  -", m)
    return 0


def main() -> int:
    names = levels = None
    if "--names" in sys.argv:
        names = [x for x in sys.argv[sys.argv.index("--names") + 1].split(",") if x]
    if "--only" in sys.argv:
        levels = [x for x in sys.argv[sys.argv.index("--only") + 1].split(",") if x]
    return crawl(names, levels)


if __name__ == "__main__":
    raise SystemExit(main())
