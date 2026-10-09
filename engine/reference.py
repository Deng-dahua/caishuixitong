# -*- coding: utf-8 -*-
"""引用模块（唯一权威实现）——把重复陈述自动替换为编号引用。

指令依据（阶段9 第13项）：「引用模块：其他位置自动生成编号引用。」
指令阶段5 第10条：引用格式统一为
  「见疑点R1、见要件R1-C2、见事实F-012、见资料D-003、见声明S-02、见法规L-05」

设计原则：
  · **引用串一律由 `engine/numbering.ReportNumbering.ref()` 生成**，本模块不拼接任何编号字符串；
  · 只做「首次完整保留、后续改引用」的替换，**不删信息**（引用可回溯到唯一完整位置）；
  · 替换前先做必要重复判定（薄转发 `dedup_pipeline.is_necessary`）——模板/格式/明细行不替换。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from engine import dupkit
from engine.numbering import ReportNumbering


def ref(kind: str, seq: int, *, rseq: int = 0) -> str:
    """生成引用串（薄转发到唯一权威；不自行拼接）。"""
    return ReportNumbering().ref(kind, seq, rseq=rseq)


# ═══════════════════════════════════════════════════════════════════════════════
# ★★ 2026-10-08（P0-2 根因治理）：**引用串形态的唯一权威**（生成与识别共用）
# ═══════════════════════════════════════════════════════════════════════════════
# 事故（报告正文被引用语吃掉的直接机制）：
#   生成侧 `report_pipeline._dup_replacement` 用**方头括号**包裹引用串 → 「〔见疑点R4〕」
#   （方头括号是为了不让 `child_item_completeness` / `data_source_status` 把它当成
#    "未登记子项"）；而识别侧 `is_reference()` 的正则只认「（见…」/「见…」，
#   **不认自己产出的方头括号形态** ⇒ 权威识别不了自己的产出。
# 实测同一形态此前在 **6 处**各写一遍（本模块 is_reference、numbering.ref_format、
#   report_pipeline._dup_replacement、dupkit.DEDUP_REF_MARK、dedup_pipeline._RE_REF_ANY、
#   config/dedup_rules.json 的两条 regex）。任一处改字 ⇒ 其余各处**静默失效**。
# 口径：**引用串的"括号 + 短号形态"只在本模块定义一次**；
#   生成一律走 `token()`，识别一律走 `is_reference()` / `REF_TOKEN_RE`，
#   其余模块（dupkit / dedup_pipeline / report_pipeline / report_dedup）**薄转发**。
REF_OPEN = "〔"
REF_CLOSE = "〕"
#: 允许的括号对（生成只用方头；识别一律认全）——全角/半角圆括号是历史形态，保留兼容。
_REF_BR = (r"[〔(（]", r"[〕)）]")
#: 各类短号的**裸形态**（不含括号）——`coverage()` 与 `REF_TOKEN_RE` 共用本表
_REF_KIND_BODY: Dict[str, str] = {
    "risk": r"见疑点R\d+",
    "constituent": r"见要件R\d+-C\d+",
    "fact": r"见事实R\d+-F\d+",
    "material": r"见资料D-\d{3}",
    "statement": r"见声明S-\d{2}",
    "law": r"见法规L-\d{2}",
    "table": r"见表T-\d+",
}
#: 裸引用串的联合模式（由 `_REF_KIND_BODY` 派生，不另写字面量）
_REF_BODY = "|".join("(?:%s)" % v for v in _REF_KIND_BODY.values())
#: **散文式**引用（第 4 种形态）：括号内是说明名而非短号，如「（见报告性质和使用说明）」。
#  历史形态，由 `report_pipeline.REPORT_LEVEL_REF` 产出（指向报告级通用口径声明）。
#  ⚠ 必须与短号形态一样被识别 —— 否则"近纯引用块"豁免失效、引用块会被当成冗余重复。
_REF_PROSE = r"[〔(（]见[^〕)）\n]{1,24}[〕)）]"
#: 文本中**出现**引用串（方头/圆括号/裸皆命中；短号与散文式皆命中）
REF_TOKEN_RE = re.compile(r"(?:%s?(?:%s)%s?)|(?:%s)"
                          % (_REF_BR[0], _REF_BODY, _REF_BR[1], _REF_PROSE))
#: **整串即引用串**（前后可有空白，但不得夹带其它内容）
_REF_FULL_RE = re.compile(r"\A\s*(?:%s?(?:%s)%s?|%s)\s*\Z"
                          % (_REF_BR[0], _REF_BODY, _REF_BR[1], _REF_PROSE))


def token(kind: str, seq: int, *, rseq: int = 0) -> str:
    """**报告可见的引用串**（带方头括号）—— 生成侧唯一入口。

    与 `is_reference()` 共用 `REF_OPEN/REF_CLOSE`，故"生成什么"与"认什么"天然一致。
    短号取不到（`ReportNumbering.ref` 返回空）⇒ 返回空串，由调用方回退（不拼半个引用）。
    """
    _bare = ref(kind, seq, rseq=rseq)
    return ("%s%s%s" % (REF_OPEN, _bare, REF_CLOSE)) if _bare else ""


def contains_reference(text: str) -> bool:
    """文本中**是否含**引用串（不要求整串）。"""
    return bool(REF_TOKEN_RE.search(str(text or "")))


def prose_ref(where: str) -> str:
    """**散文式**引用串（指向报告级说明的唯一生成点）——如「（见报告性质和使用说明）」。

    ★ 与短号引用同属"引用串形态"，故生成与识别都在本模块（`_REF_PROSE`）单点定义。
    """
    return "（见%s）" % str(where or "").strip()


#: 报告级通用口径声明的名称（唯一权威）与其逐项引用语。
#  逐项重复的通用口径（如"可信度公式""风险等级依据"）上提为报告级声明一次，
#  逐项位置用本引用语指向它。名称与引用语**同一处定义**，调用方不得再拼字面量。
REPORT_LEVEL_NOTE_NAME = "报告性质和使用说明"
REPORT_LEVEL_REF = prose_ref(REPORT_LEVEL_NOTE_NAME)


def strip_references(text: str) -> str:
    """剥掉全部引用串，留下实质正文（供"整段是否只剩引用"判定）。"""
    return REF_TOKEN_RE.sub("", str(text or ""))


def ref_map() -> Dict[str, str]:
    """七类引用的示例格式（供文档与判据使用，取自配置而非硬编码）。"""
    rn = ReportNumbering()
    return {
        "risk": rn.ref("risk", 1),
        "constituent": rn.ref("constituent", 2, rseq=1),
        "fact": rn.ref("fact", 12, rseq=3),
        "material": rn.ref("material", 3),
        "statement": rn.ref("statement", 2),
        "law": rn.ref("law", 5),
        "table": rn.ref("table", 1),
    }


def is_reference(text: str) -> bool:
    """是否**整串就是**引用串（命中即不再二次替换）。

    ★★ 2026-10-08：改为**括号无关 + 整串匹配**。
      · 括号无关：方头〔〕（本系统产出的标准形态）/全角（）/半角() 与裸串一律认
        —— 旧实现只认圆括号，**认不出自己产出的方头形态**（P0-2 事故根因之一）。
      · 整串匹配（旧为前缀 match）：前缀匹配会把「〔见疑点R1〕随后还有大段正文」
        也判成"已是引用串"而整条跳过，属于把保护范围放得过宽。
    """
    return bool(_REF_FULL_RE.match(str(text or "")))


def replace_duplicates(lines: List[str], *,
                       keep_first: bool = True,
                       fact_refs: Optional[Dict[str, str]] = None) -> Tuple[List[str], List[dict]]:
    """把「同一事实的重复完整陈述」替换为引用（保留首次完整位置）。

    fact_refs: 数值 → 事实编号（如 {"6,636,800.57": "R5-F01"}），来自 fact_store / 阶段3 分配。
    """
    from engine import dedup_pipeline as dpipe
    seen: List[Tuple[str, str]] = []
    out: List[str] = []
    log: List[dict] = []
    for i, ln in enumerate(lines or []):
        t = str(ln or "").strip()
        if not t or dpipe.is_necessary(t) or is_reference(t):
            out.append(ln)
            continue
        hit = next((w for og, w in seen if dupkit.is_sentence_dup(t, og)), None)
        if hit:
            refstr = ""
            if fact_refs:
                for v, fno in fact_refs.items():
                    if v in t:
                        refstr = f"（见事实{fno}）"
                        break
            log.append({"line": i + 1, "原": t[:80],
                        "处置": (f"替换为引用{refstr}" if refstr else f"删除（重复，首次见 {hit}）")})
            if keep_first:
                out.append(refstr if refstr else "")
            continue
        seen.append((t, f"line{i + 1}"))
        out.append(ln)
    return out, log


def coverage(text: str) -> Dict[str, Any]:
    r"""统计报告里的引用覆盖情况（供自检第 7 项「可追溯」使用）。

    ★ 2026-10-08：各类模式**由 `_REF_KIND_BODY` 派生**（不再各处重写一遍正则字面量）。
      旧实现把 7 条 `见疑点R\d+` 之类的模式又写了一遍 —— 与 `is_reference` / 配置表
      构成"同一形态多处维护"，任一处改字即静默漂移。
    """
    _cn = {"risk": "疑点引用", "constituent": "要件引用", "fact": "事实引用",
           "material": "资料引用", "statement": "声明引用", "law": "法规引用",
           "table": "表引用"}
    pats = {_cn[k]: (r"%s?(?:%s)%s?" % (_REF_BR[0], v, _REF_BR[1]))
            for k, v in _REF_KIND_BODY.items()}
    got = {k: len(re.findall(v, text or "")) for k, v in pats.items()}
    return {"各类引用数": got, "合计": sum(got.values()),
            "summary": "引用合计 " + str(sum(got.values())) + " 处：" +
                       "、".join(f"{k}{v}" for k, v in got.items() if v)}
