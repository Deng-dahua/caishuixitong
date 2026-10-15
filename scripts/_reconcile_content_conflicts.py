# -*- coding: utf-8 -*-
"""正文冲突**逐条复核**器（遗留项：62 处 `content_conflicts`）。

## 为什么要复核（不能"一律用采集版"）
冲突里混着**两类完全不同的问题**，处置相反：
1. **既有版条号错位** —— 既有条目把"另条的内容"标成了本条号（实测《发票管理办法》
   既有「第二十二条」的内容实为其**第二十一条**）。这类若沿用，报告引用条款号会
   **指向错误条文**（比缺条文更危险）⇒ 必须改用采集版。
2. **既有版正确、采集版降级** —— 实测两类真降级：
   · **标点全半角**：fgk 页面正文用半角 `;` `()`，法定文本应为全角 `；` `（）`；
   · **异体字**：页面作「帐簿/帐户/帐目/帐号」，现行规范用字为「账簿/账户/账目/账号」。
   ⇒ 这类必须**保留既有版**（人工录入用了规范用字）。

## 判定方法（三步，均为**机器可复核**）
- **S1 条号对齐核验**：把既有版正文去掉标点/空白后，在**采集全文**里检索；
  若它出现在**别的条号**下 ⇒ 既有版条号错位（`misnumbered`）。
- **S2 降级核验**：正文与既有版除标点/异体字外一致 ⇒ 标记 `degraded`
  （判据：把两侧都做「标点归一 + 异体字归一」后**完全相同**）。
- **S3 内容包含**：采集版是既有版的**超集**（既有版省略了列举项编号/后续款）⇒ `superset`
  ⇒ 采用采集版（保留原编号与完整款）。
其余归 `manual` 交人工。

用法：`./.venv/Scripts/python.exe scripts/_reconcile_content_conflicts.py [--apply]`
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import importlib.util                                          # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "_lltf", str(ROOT / "scripts" / "_load_legal_texts_full.py"))
LLTF = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(LLTF)                                  # noqa: E402

LIB = ROOT / "static" / "legal_library.json"
CUR = ROOT / "config" / "legal_texts_currency.json"
OUT = ROOT / "config" / "legal_texts_conflict_resolution.json"

#: 标点归一（全角→半角便于比对；**只用于比对，不改写正文**）
_PUNCT = {"，": ",", "。": ".", "；": ";", "：": ":", "（": "(", "）": ")",
          "、": ",", "“": '"', "”": '"', "‘": "'", "’": "'", "％": "%",
          "－": "-", "—": "-", "…": ".", "％": "%"}
#: 异体字归一（比对用）：页面旧体 → 现行规范用字
_VARIANT = {"帐": "账"}
#: 条号（中文数字）
_ART = re.compile(r"第([零〇一二三四五六七八九十百千两]+)条")


#: ★ **人工核实终判表**（2026-10-16，逐条对照官方文本后定论）。
#  键：`法名|条号`；值：(裁决, 理由)。裁决 ∈ {replace, keep}。
#  **为什么需要人工表**：机器判据只能覆盖"条号错位/内容超集/仅标点差"三类可机械识别的形态；
#  其余差异（如既有版省略列举项编号、或某条内容被截断）**必须逐条看内容**才能定，
#  机器硬判会出错。故此表是**人工核实结论的落盘**，可逐条复核，而非"默认放行"。
_HUMAN_VERDICTS: Dict[str, tuple] = {
    "个人所得税法|第二条": ("replace",
        "既有版把九项所得的**列举项编号（一）~（九）去掉**，且**漏掉第二款**"
        "（居民个人综合所得按年合并计算、非居民按月/按次）；采集版两项俱全 ⇒ 改采集版"),
    "个人所得税法|第六条": ("replace",
        "既有版仅 144 字，**省略**各项所得应纳税所得额的计算规则（非居民个人、劳务报酬、"
        "稿酬、特许权使用费……）；采集版 650 字为完整条文 ⇒ 改采集版"),
    "个人所得税法|第十条": ("replace",
        "既有版省略七项**列举项编号**；采集版保留编号与完整七项 ⇒ 改采集版"),
    "个人所得税法实施条例|第六条": ("replace",
        "★ 既有版**正文被截断**（结尾停在「书画、雕」），系录入时丢字；"
        "采集版 708 字完整 ⇒ 改采集版（残缺正文比编号差异严重得多）"),
    "税收征收管理法|第三十五条": ("replace",
        "既有版省略六项**列举项编号**（核定应纳税额的情形）；采集版保留编号与完整各项 "
        "⇒ 改采集版"),
    "税收征收管理法|第六十条": ("replace",
        "既有版省略列举项编号；采集版保留（一）~（五）与完整各项 ⇒ 改采集版"),
    "发票管理办法|第二十二条": ("replace",
        "★ 既有版**条号错位**：其正文（「开具发票应当按照规定的时限……虚开发票行为（一）(二)(三)」）"
        "实为**第二十一条**内容；采集版第二十二条（安装税控装置、电子器具开具发票）为现行文本 "
        "⇒ 改采集版（沿用错位正文会让报告**引错条文号**）"),
    "发票管理办法|第二十三条": ("replace",
        "既有版省略（一）~（五）编号；采集版保留编号与完整各项（转借转让、明知伪造受让、"
        "拆本使用、扩大使用范围、以其他凭证代替）⇒ 改采集版"),
    "发票管理办法|第二十七条": ("replace",
        "★ 既有版**条号错位**：其正文（「开具发票后，如发生销货退回需开红字发票……」）"
        "属**红字发票**条文（现行文本另有其条号）；采集版第二十七条（办理变更/注销税务登记时"
        "办理发票变更、缴销手续）为现行文本 ⇒ 改采集版"),
    "印花税法|第五条": ("keep",
        "两版**内容实质相同**（同为印花税四项计税依据），差异仅在：既有版用**全角**标点、"
        "采集版用半角「(一)」且带编号。法定文本用全角 ⇒ **保留既有版**（不因标点体例替换）"),
}


def _human_verdict(law: str, art: str) -> Optional[tuple]:
    return _HUMAN_VERDICTS.get("%s|%s" % (law, art))


def _norm_compare(s: str) -> str:
    """**仅用于比对**的归一：去空白 + 标点全角转半角 + 异体字归一。"""
    t = "".join(str(s or "").split())
    for a, b in _PUNCT.items():
        t = t.replace(a, b)
    for a, b in _VARIANT.items():
        t = t.replace(a, b)
    return t


def _norm_hard(s: str) -> str:
    """更硬的归一：再**去掉全部标点**，只留字与数字（判断"是否仅标点差异"）。"""
    t = _norm_compare(s)
    return re.sub(r"[^\w\u4e00-\u9fff%‰]", "", t)


def build_crawled() -> Dict[Any, str]:
    """(法名, 条号) → 采集版正文（沿用入库器同一套切分，保证与入库一致）。"""
    out: Dict[Any, str] = {}
    for fp in sorted((ROOT / "data" / "legal_crawl" / "legal_texts").glob("*.json")):
        try:
            o = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:                                       # noqa: BLE001
            continue
        if not o.get("ok") or o.get("effect") != "全文有效":
            continue
        # ★ 与入库脚本同一存储口径（法名收敛到**登记名**），否则 key 对不上。
        law = LLTF._storage_law(LLTF._canon(str(o.get("title") or "")))
        for a, c in LLTF.split_articles(o.get("body") or ""):
            # ★ 必须套用**与入库脚本同一套用字规范化**（`帐`→`账` 等）。
            #   实测事故（2026-10-16）：首版复核脚本直接用原始切分结果，替换人工录入条目时
            #   把规范用字「账簿」换成了页面旧体「帐簿」—— **完整性提升了、用字却退步**。
            #   两处写入路径必须用同一实现（否则同一字段两个来源）。
            out.setdefault((law, a), LLTF._normalize_variants(c))
    return out


def incomplete_laws() -> Dict[str, str]:
    """**采集源不完整**的法 → 原因（★ 决定性判据，2026-10-16 实测新增）。

    ## 为什么必须加这道前置
    冲突里有些"采集版明显更短"的条目，**不是**切分 bug，而是**采集源本身不完整**：
    实测《刑法》fgk 页面只含 **250 条**（法定全文 452 条）且存在跳号
    （第一百六十三条 → 第三百八十六条）；《证券法》177/226 亦跳号。
    ⇒ 若不加判别就用采集版覆盖，等于用**残缺文本**替换正确的完整文本，
      比"沿用旧版"严重得多（项目铁律：结论必须可自证来源）。

    判据（机器可复核）：新切分结果的条号序列中，**相邻条号差 > 100**
    （表示跳过了整条）即判该法采集源不完整 ⇒ 该法**一律 keep**，不得 replace。
    """
    from engine.cnnum import article_sort_key as _k
    bad: Dict[str, str] = {}
    for fp in sorted((ROOT / "data" / "legal_crawl" / "legal_texts").glob("*.json")):
        try:
            o = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:                                       # noqa: BLE001
            continue
        if not o.get("ok") or o.get("effect") != "全文有效":
            continue
        # ★ 与入库脚本同一存储口径（法名收敛到**登记名**），否则 key 对不上。
        law = LLTF._storage_law(LLTF._canon(str(o.get("title") or "")))
        arts = LLTF.split_articles(o.get("body") or "")
        ks = [_k(a) for a, _ in arts]
        gaps = ["%s→%s" % (arts[i][0], arts[i + 1][0])
                for i in range(len(ks) - 1) if ks[i + 1] - ks[i] > 100]
        if gaps:
            bad[law] = "条号跳号 %d 处（%s）⇒ 采集源不完整" % (len(gaps), gaps[0])
    return bad


def main() -> int:
    apply = "--apply" in sys.argv
    lib: List[Dict[str, Any]] = json.loads(LIB.read_text(encoding="utf-8"))
    idx = {(str(x.get("law")), str(x.get("article"))): x for x in lib}
    crawled = build_crawled()
    # 采集全文（按法）：用于 S1「既有正文出现在别的条号下」检索
    by_law: Dict[str, Dict[str, str]] = {}
    for (law, art), c in crawled.items():
        by_law.setdefault(law, {})[art] = c

    cur = json.loads(CUR.read_text(encoding="utf-8"))
    conflicts = cur.get("content_conflicts") or []
    print("待复核冲突：%d 处" % len(conflicts))
    bad_laws = incomplete_laws()
    if bad_laws:
        print("★ 采集源不完整的法（%d 部，其冲突一律保留既有版）：" % len(bad_laws))
        for k, v in bad_laws.items():
            print("   %-22s %s" % (k, v))

    verdicts: List[Dict[str, Any]] = []
    for x in conflicts:
        law, art = str(x["law"]), str(x["article"])
        e = idx.get((law, art))
        if e is None:
            verdicts.append({**x, "verdict": "manual", "reason": "正文库已无此条目（不臆断）"})
            continue
        old = str(e.get("content") or "")
        new = crawled.get((law, art), "")
        rec = {"law": law, "article": art,
               "is_crawled_entry": bool(e.get("_from")),
               "existing_len": len(old), "crawled_len": len(new)}
        # ★ S-人工：**人工核实终判表**优先于一切机器判据（逐条看过内容后的定论）
        hv = _human_verdict(law, art)
        if hv is not None:
            rec.update(verdict=hv[0], reason="【人工核实】" + hv[1])
            verdicts.append(rec)
            continue
        if not new:
            rec.update(verdict="keep", reason="无采集版可比 ⇒ 保留既有")
            verdicts.append(rec)
            continue
        # S0 前置：采集源不完整 ⇒ 一律保留既有（不得用残缺文本覆盖）
        if law in bad_laws:
            rec.update(verdict="keep",
                       reason="**采集源不完整**（%s）⇒ 保留既有版" % bad_laws[law])
            verdicts.append(rec)
            continue
        # S2 降级核验（仅标点/异体字差异）
        if _norm_compare(old) != _norm_compare(new) and _norm_hard(old) == _norm_hard(new):
            rec.update(verdict="keep", reason="**仅标点全半角差异**（法定文本用全角）⇒ 保留既有版")
            verdicts.append(rec)
            continue
        # S1 条号对齐：既有正文是否落在**别的条号**下
        key = _norm_hard(old)
        elsewhere = [a for a, c in (by_law.get(law) or {}).items()
                     if a != art and key and key in _norm_hard(c) and len(key) > 20]
        if elsewhere:
            rec.update(verdict="replace", reason="既有版条号**错位**（其正文实为 %s）⇒ 改用采集版"
                       % "、".join(elsewhere[:3]))
            verdicts.append(rec)
            continue
        # S3 采集版是超集（既有版省略了列举项编号/后续款）
        if _norm_hard(new).startswith(_norm_hard(old)[:max(20, len(_norm_hard(old)) - 10)]) \
                and len(_norm_hard(new)) > len(_norm_hard(old)):
            rec.update(verdict="replace",
                       reason="采集版为**超集**（既有版省略列举项编号/后续款）⇒ 改用采集版")
            verdicts.append(rec)
            continue
        # 异体字（账/帐）：两侧仅异体字不同 ⇒ 保留既有（规范用字）
        if _norm_hard(old) == _norm_hard(new):
            rec.update(verdict="keep", reason="仅**标点 + 异体字**差异 ⇒ 保留既有（现行规范用字「账」）")
            verdicts.append(rec)
            continue
        rec.update(verdict="manual", reason="差异无法机器判定（须人工对照官方文本）")
        verdicts.append(rec)

    from collections import Counter
    c = Counter(v["verdict"] for v in verdicts)
    print("\n判定分布：", dict(c))
    for v in verdicts:
        if v["verdict"] in ("replace", "manual"):
            print("  [%s] %s %s —— %s" % (v["verdict"], v["law"], v["article"],
                                          str(v.get("reason"))[:84]))

    if apply:
        n = 0
        lost_content: List[Dict[str, Any]] = []
        for v in verdicts:
            if v["verdict"] != "replace":
                continue
            e = idx[(v["law"], v["article"])]
            new = crawled.get((v["law"], v["article"]), "")
            old = str(e.get("content") or "")
            # ★ 安全校验（**独立于是否刚替换**，且**仅对人工录入条目**）：
            #   被替换掉的**原内容**是否仍能在**同法其他条号**下找到？
            #   找不到 ⇒ 该内容属**旧版文本**（现行版已无此条）或已移位，须如实登记。
            #   ★ 2026-10-16 修：采集物条目（`_from=crawl:fgk`）原地重写时，
            #     "原内容"本就是**同一来源的旧切分版本**，不是第三方旧版文本
            #     ⇒ 对它做本校验会误报（首版把征管法第三十五条误列为"旧版文本"）。
            key = _norm_hard(old)
            if (not e.get("_from")) and key and len(key) > 20 and not any(
                    key in _norm_hard(c) for a2, c in (by_law.get(v["law"]) or {}).items()
                    if a2 != v["article"]):
                lost_content.append({"law": v["law"], "article": v["article"],
                                     "old_len": len(old),
                                     "finding": "被替换的原内容在**现行文本同法其他条号**下找不到 "
                                                "⇒ 属**旧版文本**（现行版已无此条或已移位）；"
                                                "已按现行版替换，原内容留档于本台账可复核"})
            if new and new != old:
                e["content"] = new
                e["_conflict_resolved"] = v["reason"]
                n += 1
        LIB.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("\n已按判定替换 %d 处（其余保留既有版）" % n)
        if lost_content:
            print("★ 其中 %d 处的原内容属**旧版文本**（现行版无此条）——已登记：" % len(lost_content))
            for x in lost_content:
                print("   %s %s（原 %d 字）" % (x["law"], x["article"], x["old_len"]))
        # ── 回写台账：只保留**仍存在**的冲突（已裁决的不再重复列出，避免"复核完还在报警"）──
        still: List[Dict[str, Any]] = []
        for v in verdicts:
            if v["verdict"] == "manual":
                still.append({k: v.get(k) for k in
                              ("law", "article", "existing_len", "crawled_len")} |
                             {"identity": "人工录入", "note": v.get("reason")})
        cur["content_conflicts"] = still
        cur["conflict_resolution"] = {
            "resolved_at": "2026-10-16",
            "verdicts": {v["verdict"]: sum(1 for x in verdicts if x["verdict"] == v["verdict"])
                         for v in verdicts},
            "superseded_old_text": lost_content,
            "ledger": "config/legal_texts_conflict_resolution.json（逐条理由）",
        }
        CUR.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
        print("台账已回写：剩余冲突 %d 处（已裁决 %d 处）"
              % (len(still), len(verdicts) - len(still)))
    else:
        print("\n（未加 --apply，仅报告）")

    # ★ 台账**合并保留历史裁决**：本次输入为空（冲突已全部解决）时**不得清空**，
    #   否则既丢裁决记录，也会让入库脚本下次重跑时重新报"待处理冲突"。
    hist: Dict[str, Dict[str, Any]] = {}
    if OUT.exists():
        try:
            for _v in (json.loads(OUT.read_text(encoding="utf-8")).get("verdicts") or []):
                hist["%s|%s" % (_v.get("law"), _v.get("article"))] = _v
        except Exception:                                       # noqa: BLE001
            hist = {}
    for v in verdicts:
        hist["%s|%s" % (v["law"], v["article"])] = v
    # ★ **人工核实终判全表落盘**：`_HUMAN_VERDICTS` 是人工逐条看内容后的定论，
    #   即使该条已解决（内容已与现行版一致、不再出现在冲突里），**也必须留档**
    #   —— 否则台账会"越跑越少"，后人无法复核当初为何这样裁决。
    for _k, (_vd, _why) in _HUMAN_VERDICTS.items():
        _law, _art = _k.split("|", 1)
        hist.setdefault(_k, {"law": _law, "article": _art, "verdict": _vd,
                             "reason": "【人工核实】" + _why, "source": "人工核实终判表",
                             "resolved": "内容已与现行版一致（无需再替换）"})
    all_verdicts = sorted(hist.values(), key=lambda x: (str(x.get("law")), str(x.get("article"))))
    from collections import Counter as _C
    cc = _C(str(v.get("verdict")) for v in all_verdicts)
    OUT.write_text(json.dumps({
        "schema": 1, "note": "★ 正文冲突**逐条复核结论**（可逐条复核，**含历史裁决**）。"
                             "verdict: replace=改用采集版（既有版条号错位/内容残缺）；"
                             "keep=保留既有版（采集版标点降级/异体字/内容等价）；manual=待人工。",
        "counts": dict(cc), "counts_this_run": dict(c),
        "verdicts": all_verdicts,
        "superseded_old_text": locals().get("lost_content") or [],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("→ %s（累计裁决 %d 处：本次 %s）" % (OUT, len(all_verdicts), dict(c)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
