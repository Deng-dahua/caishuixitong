# -*- coding: utf-8 -*-
"""重复判定的单一权威实现。

**为什么需要这个模块**：句子级去重（阶段5 生成器）与重复率诊断（阶段1 诊断器）
曾各自实现相似度计算 —— 前者用 2-gram Jaccard、后者用另一种口径，导致
『去重做过了，诊断仍报重复』（实测：事实重复 21 次 → 去重后仍 9 次）。
同一判据两处实现 ⇒ 必然漂移。故收敛为本模块唯一实现。

参数唯一权威：`config/dedup_rules.json`
  - near_dup.metric           段落级相似度度量（jaccard | sequence_ratio）
  - near_dup.jaccard_min      段落级阈值
  - fact_anchor.sentence_metric / sentence_min   句子级度量与阈值

口径说明：
  段落级用 Jaccard（长文本，词元覆盖更稳）；句子级用 SequenceMatcher.ratio()
  （短句常有不同前缀，Jaccard 会低估相似度 —— 实测同一事实的两句 Jaccard≈0.54
   但 ratio≈0.79，用 Jaccard 会漏判）。
"""
from __future__ import annotations

import json
import os
import re
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional, Set

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CFG = os.path.join(_ROOT, "config", "dedup_rules.json")
_CACHE: Optional[Dict[str, Any]] = None


def load_rules() -> Dict[str, Any]:
    """读判据配置；读不出时返回空表（调用方须自行留痕，不静默给默认值）。"""
    global _CACHE
    if _CACHE is None:
        try:
            with open(_CFG, "r", encoding="utf-8") as fh:
                _CACHE = json.load(fh)
        except Exception:  # noqa: BLE001 —— 交给调用方判断空配置
            _CACHE = {}
    return _CACHE


def norm(s: str) -> str:
    """归一化：折叠空白。"""
    return re.sub(r"\s+", " ", str(s or "").strip())


def bigrams(s: str) -> Set[str]:
    if len(s) < 2:
        return {s} if s else set()
    return {s[i:i + 2] for i in range(len(s) - 1)}


def jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def seq_ratio(a: str, b: str) -> float:
    """序列相似度（SequenceMatcher.ratio），对长短差异与不同前缀更稳健。"""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------- 对外判据
def paragraph_similar(a: str, b: str, *, rules: Optional[Dict[str, Any]] = None) -> float:
    """段落级相似度：按配置选用度量，返回 0~1。"""
    cfg = (rules or load_rules()).get("near_dup", {})
    metric = str(cfg.get("metric") or "jaccard")
    na, nb = norm(a), norm(b)
    if metric == "sequence_ratio":
        return seq_ratio(na, nb)
    return jaccard(bigrams(na), bigrams(nb))


def paragraph_threshold(rules: Optional[Dict[str, Any]] = None) -> float:
    return float((rules or load_rules()).get("near_dup", {}).get("jaccard_min") or 0.62)


def is_paragraph_dup(a: str, b: str, *, rules: Optional[Dict[str, Any]] = None) -> bool:
    return paragraph_similar(a, b, rules=rules) >= paragraph_threshold(rules)


def sentence_similar(a: str, b: str, *, rules: Optional[Dict[str, Any]] = None) -> float:
    """句子级相似度：默认 SequenceMatcher.ratio（短句常有不同前缀）。"""
    cfg = (rules or load_rules()).get("fact_anchor", {})
    metric = str(cfg.get("sentence_metric") or "sequence_ratio")
    na, nb = norm(a), norm(b)
    if metric == "jaccard":
        return jaccard(bigrams(na), bigrams(nb))
    return seq_ratio(na, nb)


def sentence_threshold(rules: Optional[Dict[str, Any]] = None) -> float:
    return float((rules or load_rules()).get("fact_anchor", {}).get("sentence_min") or 0.62)


def is_sentence_dup(a: str, b: str, *, rules: Optional[Dict[str, Any]] = None) -> bool:
    """同一事实的两句是否属『重复的完整陈述』。"""
    return sentence_similar(a, b, rules=rules) >= sentence_threshold(rules)


def split_sentences(txt: str, *, keep_delim: bool = True) -> List[str]:
    """中文句子切分（。！？；）—— 薄转发唯一权威 `engine/sentencekit.split_sentences`。

    ★ 2026-10-08 冗余收敛：此处原有一份朴素 `re.split(r"([。！？；])")`，与
    `engine/sentencekit.split_sentences`（**括号感知**）构成同一概念的两套实现，
    会把括号内的句读当句末、切出括号不闭合的残句（闸门 `check_naive_sentence_split` 报 ERROR）。
    转发时**保留原分隔符集合**「。！？；」（不含 \\n / 半角 !?），并按 keep_delim 语义
    映射到 `keep_delims`，故仅新增"括号内不误切"这一严格更优的行为。
    """
    from engine.sentencekit import split_sentences as _sk_split
    return _sk_split(txt, delims="。！？；", keep_delims=keep_delim)


def group_similar(items: Iterable[tuple], *, sim=None, threshold: Optional[float] = None) -> List[List[int]]:
    """把相似项聚成组，返回各组的下标列表（组内 >=2 才算重复）。

    items: 可迭代的 (key, text) 或 text；sim(a,b)->float，默认 sentence_similar。
    """
    seq = [(str(k), str(t)) for k, t in items] if items and isinstance(
        next(iter(items)), tuple) else [(str(i), str(t)) for i, t in enumerate(items)]

    def _sim(a: str, b: str) -> float:
        return (sim or sentence_similar)(a, b)

    thr = threshold if threshold is not None else sentence_threshold()
    groups: List[List[int]] = []
    used: Set[int] = set()
    for i in range(len(seq)):
        if i in used:
            continue
        grp = [i]
        for j in range(i + 1, len(seq)):
            if j in used:
                continue
            if _sim(seq[i][1], seq[j][1]) >= thr:
                grp.append(j)
                used.add(j)
        if len(grp) > 1:
            used.add(i)
            groups.append(grp)
    return groups


# ── 去重引用语标记（★ 唯一权威）────────────────────────────────────────────
#: ★ 2026-10-08 收敛：报告去重（engine/report_pipeline._dup_replacement）会把重复段的
#: 正文替换为「〔本项说明同 R4，不重复〕」。此前该前缀字面量在 **三处** 各写一遍
#: （report_pipeline 产出方 + child_item_completeness / data_source_status 两个扫描器）——
#: 任一处改字，下游扫描器立刻失效（实测踩过，一次性打挂 3 个用例）。
#: 故收敛到本模块唯一实现，产出方与扫描器**共用同一常量与判定**。
DEDUP_REF_MARK = "〔本项说明同"


def is_dedup_ref(v: Any) -> bool:
    """判定一段文字是否为「去重引用语」。

    这类引用**不是**子项名/资料名/数据源名，产物级扫描器必须跳过，
    否则会误报"未登记子项"。

    ★★ 2026-10-08（P0-2 根因治理）：**两种形态都要认**。
      去重替换语有两条产生路径（同一产出方 `report_pipeline._dup_replacement`）：
        ① 能解析出疑点编号 ⇒ 标准引用串 **`〔见疑点R4〕`**（方头括号包裹）；
        ② 解析不出编号 ⇒ 回退形态 ``〔本项说明同 R4，不重复〕``（本常量）。
      旧实现**只认 ②**（`DEDUP_REF_MARK in s`）⇒ 占绝大多数的 ① 在
      `child_item_completeness` / `data_source_status` 里**不被跳过**，被当成"未登记子项"。
      ⇒ 现委托**唯一权威** `engine.reference.is_reference`（括号无关、形态单点定义），
        本模块只保留回退形态常量，不再自持引用串正则。
    """
    s = str(v or "")
    if DEDUP_REF_MARK in s:
        return True
    try:
        from engine.reference import is_reference as _is_ref
        return _is_ref(s)
    except Exception:  # noqa: BLE001 —— 取不到权威时退回"只认回退形态"（不误伤）
        return False
