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

# ★★ 2026-10-16 修正（第三个切分缺陷）：原字符集**漏了「千」** ⇒ 「第一千条」起全部匹配失败。
#   实测《民法典》只切出 **999** 条（body 含 1..1260 全部条号），第一千条之后的 261 条**全部丢失**。
#   同类风险：条号 ≥1000 的法律（民法典 1260 条、刑法修正案引用的千位条号）。
_CN = "一二三四五六七八九十百零〇两千"
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
      多命中时必须「**条号严格连续**」（相邻差恰好 1）。
      ★★ 2026-10-16 修正（本轮实测事故）：原判据只要求"首个 = 上一条 + 1 **且递增**"，
      对**行首有条号的行**不够严 ——《刑法》第一百六十三条正文里引用「本法第三百八十六条」，
      该引用**恰在行首之后**（前面是标点/空格），递增检查 163 < 386 通过 ⇒ 被当成新条文起点
      ⇒ `last` 跳到 386，其后所有 <386 的条文**全被当作续行吞掉**。
      实测代价：刑法切出 250 条（原始正文含 **540** 处条号 / 法定 452 条）、
      行政复议法实施条例 25 vs 83、国家赔偿法 20 vs 49、证券法 177 vs 232。
      ⇒ 判据收紧为"连续"：163→386 差 223 ⇒ 不拆（引用）；"第一条 第二条 第三条" ⇒ 拆（真紧凑排版）。
    """
    out: List[Tuple[str, str]] = []
    # `seen`：已出现过的条号（判"续行 vs 新条文"的依据，见下方判据注释）
    state: Dict[str, Any] = {"no": None, "buf": [], "last": 0, "seen": set()}

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
            # ★ 判据（统一用 `article_sort_key` 量纲：第N条=N*100，第N条之一=N*100+1）：
            #   相邻差只允许 {1, 99, 100} 三种，分别对应
            #   「第N条→第N条之一」(1)、「第N条之一→第N+1条」(99)、「第N条→第N+1条」(100)。
            #   刑法 16300 → 38600 差 22300 ⇒ 判为**引用**（不拆）。
            nums = [article_no(a) for a, _ in parts]
            first_ok = nums[0] - state["last"] in (1, 99, 100) if state["last"] else True
            step_ok = all(nums[i + 1] - nums[i] in (1, 99, 100) for i in range(len(nums) - 1))
            if not (first_ok and step_ok):
                # ★ 行内条号不连续 ⇒ 是**引用**（如刑法163条正文引"第三百八十六条"），不拆。
                #   **必须重建为「该条号 + 整行余下全部」**：直接取 parts[:1] 会把后半截丢掉
                #   ——实测《企业所得税法》第三十七条只留下"对非居民企业取得本法"7 个字。
                parts = [(parts[0][0], line[hits[0].end():].strip())]
        for art, content in parts:
            # ★★ 2026-10-16 修正（本轮实测事故，代价最大的一处）：
            #   原判据「条号 <= 上一条 ⇒ 按续行处理」会**连锁吞条**：
            #   《刑法》第一百六十三条正文里有一处行首的"第三百八十六条"（换行后的续写/章节起头），
            #   被当成新条文 ⇒ `last` 跳到 386 ⇒ 其后 第一百六十四条~第三百八十五条 **全部**
            #   被判为"续行"并入 ⇒ 实测刑法只切出 250/452 条（页面本身 452 条俱全）。
            #   判据改为「**该条号是否已出现过**」：
            #     · 已出现过（如《企业所得税法》"第三条第三款规定的所得…"是上一条的续写）
            #       ⇒ 续行，不新起条目（不覆盖真条文）；
            #     · 未出现过（乱序/重复条号）⇒ **接受为新条文**，连锁吞条不再发生。
            if article_no(art) <= state["last"] and art in state["seen"]:
                if state["no"] is not None and content:
                    state["buf"].append(art + (("　" + content) if content else ""))
                continue
            _flush()
            state["no"], state["last"] = art, article_no(art)
            state["seen"].add(art)
            if content:
                state["buf"].append(content)
    _flush()
    out = _drop_isolated_far_jumps(out)
    out = [(a, c) for a, c in out if c]
    return [] if _is_not_article_style(out) else out


#: 「非条文式文本」判据阈值（见 `_is_not_article_style`）
_NONARTICLE_COVER = 0.15


def _is_not_article_style(arts: List[Tuple[str, str]]) -> bool:
    """判定这是**非条文式文本**（修正案 / 决定 / 通知 —— 正文用「一、二、三」编号）。

    ★ 实测（2026-10-16）：《刑法修正案》系列共 6 部的正文体例是
      「一、将刑法第XXX条修改为：…；二、…」（用**中文序号**而非「第X条」），
      其中的「第XXX条」全是**被修改对象**（引用）⇒ 切出的少量条目全是伪条文
      （实测《刑法修正案（十一）》切出 1 条、末条 142；《（八）》3 条 / 末条 105）。
    ★ 判据：**切出条数 / 末条号 < 15% 且 末条号 > 20** ⇒ 判为非条文式。
      正常法律（1..N 全覆盖）覆盖率接近 100%，不受影响；真"条目很少且末条号小"的
      短文本也不会误伤。判为非条文式 ⇒ 返回空列表 ⇒ 由调用方归入 `no_article`
      （**如实登记"该文本无「第X条」条文结构"**，不编造条文）。
    """
    from engine.cnnum import parse_article as _pa
    nums = [n for n, _ in (_pa(a) for a, _ in arts) if n]
    if not nums:
        return True
    last = max(nums)
    return last > 20 and (len(arts) / last) < _NONARTICLE_COVER


#: 「孤立远跳」判据：新条号比上一条号**大出超过这么多条** ⇒ 判为引用误判（而非真跳条）
_FAR_JUMP = 5


def _drop_isolated_far_jumps(arts: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """丢弃**孤立的远跳条号**（实测《国家赔偿法》第一百七十三条）。

    ★ 为什么需要：条文正文里若出现**换行后位于行首**的引用（如"……依照民事诉讼法
      第一百七十三条的规定……"），会被当作新条文起点。实测《国家赔偿法》只此 1 处
      （切出 43 条，条号 1..173 缺 130 个）。
    ★ 判据：条号数字比**上一条**大出 `> _FAR_JUMP` 条 ⇒ 判为引用 ⇒ 其内容**并入上一条**
      （不产出伪条目，也不丢字）。正常相邻条差 1、"之N"差 0 ⇒ 不受影响；
      真"缺条"（如某条被废止，42→44）差 2 ⇒ 也不受影响。
    """
    from engine.cnnum import parse_article as _pa
    out: List[Tuple[str, str]] = []
    prev_no: Optional[int] = None
    for art, content in arts:
        n, _sub = _pa(art)
        if n is not None and prev_no is not None and (n - prev_no) > _FAR_JUMP:
            # 远跳 ⇒ 并入上一条（保留原文，不产出伪条目）
            if out:
                a0, c0 = out[-1]
                out[-1] = (a0, (c0 + "\n" + art + "　" + content).strip())
                continue
        if n is not None:
            prev_no = n
        out.append((art, content))
    return out


# ─────────────────────────── 时效核实 ───────────────────────────

def _canon(law: str) -> str:
    from engine.legal_version import canonical_law
    return canonical_law(law)


def _law_storage_index() -> Dict[str, str]:
    """`法名（归一键）→ 库内**存储用**规范名`（★ 唯一权威 `config/legal_law_codes.json`）。

    ★ 为什么需要它（2026-10-16 实测缺陷）：`canonical_law` 只做**格式归一**
      （去《》、去空白、去"中华人民共和国"），**不做"同一部法多名收敛"**。
      于是**同一个短码**在库里对应了多个 `law` 名 —— 实测 15 个短码各带 2 个法名，
      其中 **14 个只差一个空格**（`财政部 国家税务总局关于…通知` vs
      `财政部国家税务总局关于…通知`），另 1 个是"短名 vs 发布公告全名"。
      后果：同一条文在两套法名下各存一份 ⇒ ①条文重复；②`provision_id`
      （= 短码 + 条号）**撞号 60 处**⇒ 条款级关联会指到错条文。
    ⇒ 存储用的法名一律取**该短码的登记名**（登记表里一部法只有一行）。
    """
    try:
        reg = json.loads((ROOT / "config" / "legal_law_codes.json").read_text(encoding="utf-8"))
    except Exception:                                          # noqa: BLE001
        return {}
    idx: Dict[str, str] = {}
    for l in (reg.get("laws") or []):
        name = str(l.get("name") or "")
        if not name:
            continue
        target = _canon(name)
        for k in [name] + list(l.get("aliases") or []):
            if k:
                idx.setdefault(_canon(str(k)), target)
    return idx


_STORAGE_IDX: Optional[Dict[str, str]] = None


def _storage_law(law: str) -> str:
    """库内 `law` 字段的规范写法（登记名；查不到 ⇒ 退回 `canonical_law`，不臆断）。"""
    global _STORAGE_IDX
    if _STORAGE_IDX is None:
        _STORAGE_IDX = _law_storage_index()
    c = _canon(law)
    return _STORAGE_IDX.get(c) or c


def _dedupe_library(lib: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """按 `(law, article)` 去重（**法名收敛后才会出现重复**）。

    保留规则（先判内容、再判来源，全部留痕）：
      ① 内容**抹空白后相同** ⇒ 视为同一版文本，保留**带 `_from`（采集全文）**的一条
         （采集版保留原始分段换行；人工版常无换行，两者等价）；
      ② 内容真的不同 ⇒ 保留**较长**的一条，并把两条都记入 `merged`（可人工复核，
         不静默丢）。
    """
    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    order: List[Tuple[str, str]] = []
    for e in lib:
        k = (str(e.get("law") or ""), str(e.get("article") or ""))
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(e)
    out: List[Dict[str, Any]] = []
    merged: List[Dict[str, Any]] = []
    for k in order:
        g = groups[k]
        if len(g) == 1:
            out.append(g[0])
            continue
        keys = {_ws_key(str(x.get("content") or "")) for x in g}
        if len(keys) == 1:
            win = next((x for x in g if x.get("_from")), g[0])
            how = "内容一致（仅空白/换行差异）⇒ 保留采集全文版"
        else:
            win = max(g, key=lambda x: len(str(x.get("content") or "")))
            how = "★ 内容不同 ⇒ 保留较长者（须人工复核）"
        out.append(win)
        merged.append({"law": k[0], "article": k[1], "kept_len": len(str(win.get("content") or "")),
                       "dropped": [{"len": len(str(x.get("content") or "")),
                                    "_from": x.get("_from")} for x in g if x is not win],
                       "how": how})
    return out, merged


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


#: **异体字规范化**（历史用字 → 现行规范用字）。★ 只登记**有实证依据**的映射。
#  依据（2026-10-16 采集正文实证）：全部采集正文中「账」出现 **265** 次、「帐」**61** 次；
#  用「帐」的只有《税收征收管理法》《刑法》《海关法》等**沿用旧文本**的少数法，
#  而**同源的《税收征收管理法实施细则》用「账」43 次、0 次「帐」**
#  ⇒ 页面「帐」属**历史用字降级**（"帐"从"巾"用于帷帐；"账"从"贝"用于账目），
#  现行法定文本用「账」。规范化**不改变任何语义**，且与同源法规用字一致。
_VARIANT_MAP = {"帐": "账"}


def _normalize_variants(text: str) -> str:
    """按 `_VARIANT_MAP` 规范化用字（不改语义、不删字、不调序）。"""
    t = str(text or "")
    for a, b in _VARIANT_MAP.items():
        t = t.replace(a, b)
    return t


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
    #: 条目对象索引（**允许按新切分重写采集物**，见下方 `_from` 判据）
    entry_by_key = {(str(x.get("law") or ""), str(x.get("article") or "")): x for x in lib}
    #: ★ **已裁决的冲突**（`config/legal_texts_conflict_resolution.json`）——
    #  人工核实判为 `keep` 的条目，其与采集版的差异是**有意保留**（如法定全角标点、
    #  规范用字），不应每次重跑都重新记为"待处理冲突"（否则台账永远清不掉）。
    adjudicated: Dict[str, str] = {}
    _res_path = ROOT / "config" / "legal_texts_conflict_resolution.json"
    if _res_path.exists():
        try:
            _res = json.loads(_res_path.read_text(encoding="utf-8"))
            for _v in (_res.get("verdicts") or []):
                adjudicated["%s|%s" % (_v.get("law"), _v.get("article"))] = str(_v.get("verdict"))
        except Exception:                                       # noqa: BLE001
            adjudicated = {}
    before = len(lib)
    print("现有正文库 %d 条（已裁决冲突 %d 处）" % (before, len(adjudicated)))

    # ── law 名**归一迁移**（幂等）────────────────────────────────
    #   ★★ 2026-10-16 升级：从「只做格式归一」改为「收敛到**登记名**」。
    #   背景（实测缺陷）：`canonical_law` 不做"同一部法多名收敛" ⇒ 同一短码
    #   在库里带 2 个法名（15 个短码，其中 14 个只差一个空格），导致条文重复
    #   且 `provision_id` 撞号 60 处。现一律取该短码在 `legal_law_codes.json`
    #   的登记名；改名后按 `(law, article)` 去重（见 `_dedupe_library`）。
    try:
        from engine.legal_version import reset_caches as _rc
        _rc()                                     # 改了别名表 ⇒ 清缓存再读
    except Exception:                             # noqa: BLE001
        pass
    global _STORAGE_IDX
    _STORAGE_IDX = None                           # 登记表可能已变 ⇒ 强制重读
    migrated = 0
    for e in lib:
        cur = str(e.get("law") or "")
        new_law = _storage_law(cur)
        if new_law and new_law != cur:
            e["law"] = new_law
            migrated += 1
    if migrated:
        print("law 名归一迁移（收敛到登记名）：%d 条" % migrated)
    lib, merged_entries = _dedupe_library(lib)
    if merged_entries:
        print("法名收敛后去重：合并 %d 组重复条文（保留规则见 `_dedupe_library`）"
              % len(merged_entries))
    # ★ 改名/去重都改变了 key ⇒ 必须**重建**三个索引，否则下面的"不得掉条"断言
    #   会把改名误判成"丢失"（首版即如此误报 18 条）。
    existing = {(str(x.get("law") or ""), str(x.get("article") or "")) for x in lib}
    existing_by_key = {(str(x.get("law") or ""), str(x.get("article") or "")):
                       str(x.get("content") or "") for x in lib}
    entry_by_key = {(str(x.get("law") or ""), str(x.get("article") or "")): x for x in lib}

    loaded: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []
    conflicts: List[Dict[str, Any]] = []
    content_conflicts: List[Dict[str, Any]] = []
    no_article: List[Dict[str, Any]] = []
    #: 按新切分**重写**的采集物（同一来源的新版本 ⇒ 允许覆盖；人工录入的**不覆盖**）
    rewritten: List[Dict[str, Any]] = []

    for fp in sorted(TEXT_DIR.glob("*.json")):
        try:
            o = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as exc:                               # noqa: BLE001
            blocked.append({"id": fp.stem, "reason": "采集文件读不出来：%s" % exc})
            continue
        title = str(o.get("title") or "").strip()
        effect = str(o.get("effect") or "").strip()
        date = str(o.get("written_date") or "").strip()
        law = _storage_law(_canon(title))        # ★ 存储名一律取登记名（防同一部法多名）
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
        n_rewrite = 0
        n_adjudicated = 0
        for art, raw_content in arts:
            content = _normalize_variants(raw_content)          # 用字规范化（见 _VARIANT_MAP）
            key = (law, art)
            if key in existing:
                old = existing_by_key.get(key) or ""
                if not (content and _ws_key(old) != _ws_key(content)):
                    continue                                    # 内容一致 ⇒ 无需处理
                # ★★ 2026-10-16（遗留项「正文冲突即刻复核」）——按**条目身份**分两种处置：
                #   ① 既有条目是**本轮采集物**（`_from=crawl:fgk`）⇒ 与本次是同**一来源**，
                #      差异源于**切分器迭代**（本轮修了"连锁吞条"与"孤立远跳"两处缺陷）
                #      ⇒ **按新切分重写**（人工版与此无关，不受影响）；
                #   ② 既有条目是**人工录入**（无 `_from`）⇒ **一律不覆盖**，只记冲突待人工复核
                #      （人工录入可能用了规范用字/完整款，或另有官方来源）。
                e = entry_by_key.get(key)
                if isinstance(e, dict) and e.get("_from") == "crawl:fgk":
                    e["content"] = content
                    e["_rewritten"] = (
                        "按修正后的切分重录（原 %d 字 → %d 字）：切分器已修「条号未递增即当续行」"
                        "导致的连锁吞条与孤立远跳引用误判" % (len(old), len(content)))
                    n_rewrite += 1
                    continue
                # ★ 已裁决为 keep（人工核实有意保留既有版）⇒ 不重复记为待处理冲突
                if adjudicated.get("%s|%s" % (law, art)) == "keep":
                    n_adjudicated += 1
                    continue
                content_conflicts.append({"law": law, "article": art,
                                          "existing_len": len(old),
                                          "crawled_len": len(content),
                                          "identity": "人工录入",
                                          "note": "两版正文**实质不同**（已抹空白差）⇒ "
                                                  "保留既有（人工录入版），不覆盖，待人工核对"})
                continue
            existing.add(key)
            existing_by_key[key] = content
            n_e = {"law": law, "article": art, "content": content, "source": src_text,
                   "_from": "crawl:fgk", "_effect": effect, "_written_date": date}
            lib.append(n_e)
            entry_by_key[key] = n_e
            n_new += 1
        loaded.append({**rec, "articles": len(arts), "new_articles": n_new,
                       "rewritten": n_rewrite, "adjudicated_kept": n_adjudicated})
        if n_rewrite:
            rewritten.append({"law": law, "title": title, "count": n_rewrite})

    # ── 清理**伪条目**：上一轮旧切分器把"非条文式文本"（修正案/决定/通知）里的
    #    引用条号当成了条文入库（实测 3 条：刑法修正案/（六）/（十一））。
    #    ★ 只清理 `_from=crawl:fgk` 的条目（人工录入的一律不动），并记入台账可追溯。
    nonarticle_laws = {str(x.get("law") or "") for x in no_article}
    purged: List[Dict[str, Any]] = []
    if nonarticle_laws:
        keep_lib: List[Dict[str, Any]] = []
        for e in lib:
            if e.get("_from") == "crawl:fgk" and str(e.get("law") or "") in nonarticle_laws:
                purged.append({"law": e.get("law"), "article": e.get("article"),
                               "reason": "所属文本为**非条文式**（修正案/决定/通知），"
                                         "该条目系旧切分把引用条号误当条文 ⇒ 清理"})
                continue
            keep_lib.append(e)
        lib = keep_lib

    # ── 安全断言：不得掉条（**排除两类有意减少**：伪条目清理、法名收敛后的去重）──
    #   ★ 去重合并是**预期内**的减少（同一部法多名收敛后，同一条文本就只该有一条），
    #     故基线为 `before - len(purged) - len(merged_entries)`；**真实丢失仍必须中止**。
    after_keys = {(str(x.get("law") or ""), str(x.get("article") or "")) for x in lib}
    expected_min = before - len(purged) - len(merged_entries)
    missing = [k for k in existing_by_key
               if k not in after_keys
               and not any(p["law"] == k[0] and p["article"] == k[1] for p in purged)]
    if len(lib) < expected_min or missing:
        print("!! 断言失败：条数 %d→%d（预期下限 %d），非预期丢失 %d 条 ⇒ **中止写盘**"
              % (before, len(lib), expected_min, len(missing)))
        return 3

    new_total = len(lib)
    n_rw = sum(x["count"] for x in rewritten)
    print("切分入库：新增 %d 条（法规 %d 部）⇒ 正文库 %d → %d"
          % (new_total - before, len(loaded), before, new_total))
    print("按新切分**重写采集物** %d 条（涉及 %d 部法；人工录入版不受影响）" % (n_rw, len(rewritten)))
    print("未入库：%d 部（效力非『全文有效』/采集失败/切不出条文）" % len(blocked))
    print("切不出条文：%d 部（含**非条文式文本**：修正案/决定/通知）｜"
          "人工录入冲突：%d 处｜版本冲突：%d 部"
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
            "rewritten_crawled_entries": n_rw,
            "purged_pseudo_entries": len(purged),
            "law_name_migrated": migrated,
            "law_name_merged_groups": len(merged_entries),
            "blocked_laws": len(blocked),
            "no_article_laws": len(no_article),
            "version_conflicts": len(conflicts),
            "content_conflicts": len(content_conflicts),
            "library_total": new_total,
        },
        "rewritten": rewritten,
        "purged_pseudo_entries": purged,
        "law_name_merged": merged_entries,
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
