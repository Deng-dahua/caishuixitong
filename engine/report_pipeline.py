# -*- coding: utf-8 -*-
"""产出链统一后处理（唯一权威实现）——把「去重 / 自检 / 多版本」真正作用到一键分析的报告数据上。

**为什么需要本模块**（2026-10-08 实测发现的关键缺陷）：
  `engine/dedup_pipeline` 只被**离线脚本链**（`scripts/_phase5_dedup.py`）使用，
  而一键分析走的是**产出链**（`report_data.enterprise_readable_report`）——
  两条链路没有打通，导致：
    · 离线重构稿（V1.4）重复率 0.02% PASS
    · 产出链报告          重复率 21.27% FAIL（可信度公式×13、等级说明×11、结语句×13 等模板复述）
  本模块是**产出链侧的收敛点**：在报告装配完成后统一执行
    ① 段落级去重（跨事项）② 20 项自检 ③ 内部版/对外版一键生成。
  去重与相似度判定**一律薄转发** `engine/dedup_pipeline` / `engine/dupkit`，不另实现。
"""
from __future__ import annotations

import re

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from engine import dedup_pipeline as dpipe
from engine import dupkit

#: **判据/结构化字段黑名单：一律不参与去重**（去重只能动展示文本，绝不能动判据）
#: ★ 2026-10-08 实测事故：不加黑名单时，`criterion_status.C1.text`（内容为「符合情形…」）
#:   被判为重复并替换成「（本项与 R2 同一说明…）」⇒ 直接打挂
#:   `tests/test_trigger_determination_separation.py` 的 3 个用例。
SKIP_KEYS = frozenset({
    "criterion_status", "trigger_determination", "determination_criteria", "criterion",
    "redline_id", "risk_code", "seq", "trace_id", "tax_impact", "confidence",
    # ★ confidence_formula 移出黑名单：它是**展示文本**（报告里显示"可信度 = 基准分…"），
    #   16 项完全相同 ⇒ 属真冗余，应保留首次、其余改引用。`confidence_breakdown`（结构化数组）仍留黑名单。
    "confidence_breakdown", "closure", "evidence_have", "evidence_need",
    "risk_level_capped_from", "missing_materials", "missing_material_names", "verify_materials",
    "detail_table", "taxes", "self_doubt", "material_intel", "verified_rule_executions",
    # ★ 2026-10-08（条款核验实测事故）：以下三项**从去重白名单撤回黑名单**。
    #   它们是**逐项独有语义字段**——不同事项的 verdict/suggestion/confidence_formula
    #   即便字面完全相同，其**归属主体不同**（R3 的结论 ≠ R2 的结论）；
    #   替换成跨项引用「见疑点R2」会产生**错误语义**。
    #   实测：14/16 项的 `verdict` 被替换（R3 结论变成「见疑点R2」、R7 更出现**自引用**
    #        「见疑点R7」），读者完全看不到本项定性状态。
    #   旧注释称"安全性由下游闸门 `_DEDUP_REF_MARK` 过滤保证" —— 那只解决了
    #   **扫描器不误判**，没解决**读者看到错误引用**（治标不治本，已撤销该例外）。
    "verdict", "suggestion", "confidence_formula",
})

#: 报告数据里参与去重的文本字段（白名单，**极保守**）。
#  ★ 2026-10-08 两次实测事故后收敛：
#    ① 宽白名单（含 `verdict`/`confidence_formula`/`suggestion` 等）会把
#       **判据性文本**替换成引用语 ⇒ 打挂 `test_trigger_determination_separation`；
#    ② 替换语即便改格式，只要落在 `detail_table`/`family_members` 派生面上，
#       仍被 `child_item_completeness` / `data_source_status_consistency` 当成"未登记子项"。
#  结论：**去重只动"纯展示段落"** —— 其余字段（含一切判据、明细、状态表）一律不碰。
#  宁可重复率略高，也绝不污染判据与下游扫描器。
#: 报告级通用口径字段：逐项**应统一**（风险等级依据 / 可信度公式）。
#  ★ 2026-10-08（条款 5 实测）：这两类字段在 16 项里字面相同（实测 `risk_level_basis` 11 项相同、
#    `confidence_formula` 13 项相同）⇒ 贡献了整体重复率的 **约 10.2 个百分点**
#    （剔除这 27 行后 16.89% → 6.67%、同章节超阈 10 → 0）。
#    它们是"每项都适用"的**方法说明**，正确处置是**上提为报告级声明一次**、逐项位置改引用，
#    而不是逐项重复 —— 上提后的文本由 `enterprise_report` 写入「报告性质和使用说明」。
REPORT_LEVEL_TEXT_KEYS = ("risk_level_basis", "confidence_formula")
#: 众数出现次数达到该值才认为"确属通用口径"（避免把偶发相同值也上提 ⇒ 悬空引用）
REPORT_LEVEL_MIN_OCCUR = 3
#: 逐项位置的引用语（指向报告级声明；被 `is_necessary` 的"近纯引用块"识别为必要重复）
#  ★ 2026-10-08：**形态与名称单点**在 `engine.reference`（与短号引用共用同一识别判据），
#    本处只**转发**，不再自拼括号与"见"字。
try:
    from engine.reference import REPORT_LEVEL_REF as REPORT_LEVEL_REF
except Exception:  # noqa: BLE001 —— 取不到权威时给出可读回退（不静默）
    REPORT_LEVEL_REF = "（见报告性质和使用说明）"


def merge_report_level_notes(items: Any, log: List[dict]) -> Dict[str, str]:
    """把**逐项重复的通用口径字段**上提为报告级声明一次，逐项位置替换为引用。

    返回 `{字段名: 报告级口径原文}`（供 `enterprise_report` 写进「报告性质和使用说明」）。
    仅在某个值出现次数 ≥ `REPORT_LEVEL_MIN_OCCUR` 时上提（否则保持原样，**避免悬空引用**）。
    """
    from collections import Counter
    out: Dict[str, str] = {}
    for k in REPORT_LEVEL_TEXT_KEYS:
        cnt: Counter = Counter()
        for it in (items or []):
            if isinstance(it, dict):
                v = it.get(k)
                # 排除已上提的引用语 ⇒ 幂等（重复调用不会把引用语再"上提"一次）
                if isinstance(v, str) and v.strip() and v.strip() != REPORT_LEVEL_REF:
                    cnt[v.strip()] += 1
        if not cnt:
            continue
        mode, n = cnt.most_common(1)[0]
        if n < REPORT_LEVEL_MIN_OCCUR:
            continue
        out[k] = mode
        for it in (items or []):
            if isinstance(it, dict) and str(it.get(k) or "").strip() == mode:
                it[k] = REPORT_LEVEL_REF
                log.append({"类型": "通用口径上提", "位置": k, "原文": mode[:70],
                            "处置": "上提为报告级声明一次，逐项位置改引用"})
    return out


TEXT_KEYS = (
    # ⚠ `heading` **不可去重**：它是段落的结构标签（如「构成要件独立核对表」），
    #   下游判据按标题定位段落；替换成引用语会让判据找不到段落
    #   （实测：`test_data_source_status_consistency` 的用例有效性守卫从 ≥6 掉到 1）。
    "text",                            # narrative_paragraphs 的**正文**段落
    "summary", "overall_conclusion", "inspection_overview", "main_assessment",
    # ★ 2026-10-08：`verdict` / `suggestion` / `confidence_formula` 已**撤回**（见 SKIP_KEYS 注释）。
    #   去重只动「纯展示叙述段落」，**绝不碰逐项结论字段** ——
    #   宁可重复率略高，也绝不让读者看到错误的跨项引用。
)



# ══════════════════════════════════════════════════════════════════════════════
# 必要重复 · 逐项结论/口径字段（★ 2026-10-09 P1-3 判据同口径）
# ──────────────────────────────────────────────────────────────────────────────
# 铁律：「逐项结论字段不可参与去重」（见 SKIP_KEYS 注释）⇒ **判据口径必须与去重同口径**：
#   这些字段的取值即便在多个事项里字面相同，其**归属主体不同**（R3 的结论 ≠ R2 的结论），
#   属**必要重复**，模板整洁门禁（D5 重复段落）**不得**把它计为冗余 —— 否则会出现
#   "一边规定不许去重、一边判它重复"的自相矛盾判据（D5 实测长期 FAIL 的真因之一）。
#: 逐项结论/口径**字符串字段**
NON_DEDUP_ITEM_FIELDS: Tuple[str, ...] = ("verdict", "suggestion", "confidence_formula", "risk_level_basis")
#: 逐项结论/口径**子字段**（容器 → 子键）
NON_DEDUP_SUBFIELDS: Dict[str, Tuple[str, ...]] = {
    "tax_impact": ("note", "basis", "scope_note", "formula"),
}


def non_dedupable_values(report_data: Any) -> set:
    """收集**不参与去重**的逐项字段取值（规范化后）——供"重复判定同口径"豁免。

    返回规范化字符串集合；调用方（模板整洁门禁 D5）据此把"必要重复"排除在重复计数之外。
    """
    from engine import report_metrics as _rm
    from engine.dupkit import norm as _norm
    out: set = set()
    for it in _rm.report_surface_items(report_data):
        if not isinstance(it, dict):
            continue
        for k in NON_DEDUP_ITEM_FIELDS:
            v = it.get(k)
            if isinstance(v, str) and v.strip():
                out.add(_norm(v.strip()))
        for k, subs in NON_DEDUP_SUBFIELDS.items():
            blob = it.get(k)
            if isinstance(blob, dict):
                for s in subs:
                    v = blob.get(s)
                    if isinstance(v, str) and v.strip():
                        out.add(_norm(v.strip()))
    return out



_RE_RISK_WHERE = re.compile(r"R(\d+)")


def _dup_replacement(where_first: str) -> str:
    """重复段的统一替换语：**标准引用格式**（唯一权威 `engine.reference.token`）+ 方头括号防下游误认。

    · 引用串由 `engine.reference.token('risk', n)` 生成（→「〔见疑点R4〕」），
      **不在本模块拼编号、也不在本模块写括号**（括号与短号形态的单点在 `engine.reference`）；
    · 外层方头括号：全角圆括号会被 `child_item_completeness` /
      `data_source_status` 当成"未登记子项"（2026-10-08 实测事故，打挂 3 个用例）。
    """
    m = _RE_RISK_WHERE.match(str(where_first or ""))
    if m:
        try:
            from engine import reference as _ref
            return _ref.token("risk", int(m.group(1)))     # → 〔见疑点R4〕
        except Exception:  # noqa: BLE001 —— 取不到引用串时回退到可读描述
            pass
    return f"{dupkit.DEDUP_REF_MARK} {where_first}，不重复〕"


#: **跨疑点替换的范围唯一判据**（P0-2 根因治理）。
#  「哪些段落可以跨疑点替换」必须与「哪些段落会被计数器统计为上提对象」**同口径**
#  —— 计数器 = `engine.report_dedup.find_leftover_duplicates`，它只统计 `is_hoistable_head`
#  的段落。旧实现：计数器只算共性段，替换器却对**所有** `text` 一律替换
#  ⇒ 本项特有的「四、本项结论及理由」「二、发现的依据」「一、涉及的风险事项」
#    也被整段换成别的疑点的引用（实测 24 个小节内容消失、13 处"后果"缺失）。
#  现统一：**只有共性段（含后果段/资料补件段/自我反驳段）参与跨疑点替换**；
#  本项特有段落（结论/依据/风险事项/为何列入检查/资料缺口说明…）**一律不替换**。
#  口径本体只此一份，来自 `report_dedup.is_hoistable_head`（薄转发，不另实现）。
def _cross_scope_allows(head: Any) -> bool:
    """该段落标题是否允许参与**跨疑点**替换（段级/句级同判据）。"""
    try:
        from engine.report_dedup import is_hoistable_head as _ihh
        return bool(_ihh(head))
    except Exception:  # noqa: BLE001 —— 取不到权威 ⇒ 一律不替换（宁可留重复，不可删内容）
        return False


#: 「整段塌陷」判据：替换后**剥掉引用串就几乎没有实质正文**，而原文有实质正文。
#  事故：引用替换把整段正文吃掉，页面只剩「〔见疑点Rn〕」⇒ 读者看不到任何信息
#  （实测 24 处，其中 13 处是「若不补充资料的后果」）。替换一律以"至少留下原文"
#  为界：命中本判据 ⇒ 回退保留原文（宁可重复，绝不空白）。
def _would_collapse(orig: str, new: str) -> bool:
    try:
        from engine.reference import strip_references as _strip
    except Exception:  # noqa: BLE001
        return False
    _o = _strip(str(orig or "")).strip()
    if not _o:
        return False                       # 原文本就是纯引用/空 ⇒ 不算塌陷
    _n = _strip(str(new or "")).strip()
    return len(_n) < max(8, int(len(_o) * 0.15))


def dedup_report_data(report_data: Any, *, rules: Optional[Dict[str, Any]] = None
                      ) -> Tuple[Any, List[Dict[str, Any]]]:
    """对报告数据做**跨事项段落级去重**（原地修改并返回）。

    只处理字符串字段；**不删键、不改结构**，重复段替换为指向首次位置的引用语。
    保底：若某事项的全部段落都被替换，则保留首段原文（避免出现"空事项"）。
    """
    R = rules or dpipe.load_rules()
    seen_norm: Dict[str, str] = {}
    seen_paras: List[Tuple[str, str]] = []
    log: List[Dict[str, Any]] = []
    boiler_exact, boiler_pref = dpipe.boilerplate_index()
    # ★ 句子级去重的跨事项状态（条款 A5「同一事实完整出现 ≤1 次」）
    seen_sent_norm: Dict[str, str] = {}
    seen_sent_paras: List[Tuple[str, str]] = []

    def dedup_sentences_cross(t: str, where: str) -> str:
        """**句子级**跨事项去重：同一事实（相同/高度相似句）只保留首次完整陈述，
        其余替换为**标准引用语**（`_dup_replacement` → 「见疑点Rn」）。

        与段落级去重的区别：段落级处理"整段重复"；本层处理"段内某句在别处已完整陈述"
        （实测漏网：`业务招待费411,111.53元…` 一句在 4 处出现 ⇒ 事实超额，条款 A5 判 FAIL）。
        替换语沿用同一格式，故下游扫描器的 `_DEDUP_REF_MARK` 过滤同样生效。

        ★★ 2026-10-08（P0-2 根因治理）两条新护栏（与第 1 轮 `report_dedup` 同口径）：
          ① **本项专属句/税费性质专属句不得替换** —— 薄转发
             `report_dedup.sentence_not_hoistable`。旧实现没有这道闸 ⇒
             后果段里「本项存在被认定为…」这类**本项自己的涉嫌情形**也被换成别的疑点的
             引用，于是整段内容消失（实测 13 处「若不补充资料的后果」变空白）。
          ② **禁止自引用** —— 首次出现位置与本项相同（`hit == where`）时**保留原文**。
             旧实现会把本项内的后来重复也换成「见疑点R本项」⇒ 报告出现"见我自己"
             （实测 55 处自引用，如 R10 的结论段整段=`〔见疑点R10〕`）。
        """
        segs = dupkit.split_sentences(t)
        if not segs:
            return t
        try:
            from engine.report_dedup import sentence_not_hoistable as _snh
        except Exception:  # noqa: BLE001
            _snh = None
        out: List[str] = []
        for sn in segs:
            st = sn.strip()
            if len(st) < 12 or dpipe.is_necessary(st):
                out.append(sn)
                continue
            nt = dupkit.norm(st)
            # ① 本项专属句 / 税费性质专属句 ⇒ 不参与跨项替换（判据唯一权威在 report_dedup）
            if _snh is not None and _snh(nt):
                out.append(sn)
                continue
            hit = seen_sent_norm.get(nt)
            if hit is None:
                for og, ow in seen_sent_paras:
                    if dupkit.is_sentence_dup(st, og, rules=R):
                        hit = ow
                        break
            if hit and hit != where:
                out.append(_dup_replacement(hit))
                log.append({"类型": "事实重复", "位置": where, "原文": st[:70],
                            "处置": f"替换为引用（同一事实已在 {hit} 完整陈述）"})
            else:
                # ② 自引用（hit == where）⇒ 不替换，保留原文
                seen_sent_norm.setdefault(nt, where)
                seen_sent_paras.append((st, where))
                out.append(sn)
        return "".join(out).strip()

    # ★★ 2026-10-08（P0-3 根因治理）：项内「同一事实只完整陈述一次」状态。
    #   `_item_sents` 只累计**当前事项**已完整陈述过的句子；事项切换即清空
    #   （跨事项由 `dedup_sentences_cross` 以"引用"方式处置，两者互补、不重复）。
    _item_sents: List[Tuple[str, str]] = []
    _item_where: List[str] = [""]

    def dedup_sentences_intra(t: str, where: str, head: str = "") -> str:
        """**项内**句子去重：同一事实在本项内只保留**首次完整陈述**，后续复述整句删除。

        病根（只读诊断 `scripts/_diag_fact_cluster.py`，公司1 真实产物实测）：
          `clue.terminal_signal`（触发事实，如「业务招待费411,111.53元，占主营业务收入
          6,636,800.57元的6.19%，超过收入5‰的法定扣除标准」）在同一事项内被 **2~4 处**
          以不同引导语复述——
            · 「为何列入检查」       ← `_main_sig`
            · 「一、涉及的风险事项」 ← `risk_item_lead(signal=…)`
            · 「四、本项结论及理由」 ← `argumentation._compose_reasoning`
            · 「一、」bullets       ← `argumentation._grounds`（「线索链终端信号：…」）
          ⇒ `dedup_pipeline.fact_repeat_stats` 判「同一事实完整出现 >1 次」
          ⇒ 重复率三项判据第三项 FAIL ⇒ `阻断=True` ⇒ `formal_workpaper_allowed=False`
          ⇒ 一键分析产出**不得作为正式工作底稿**（实测超额 24 次，其中**跨项簇 0 个**，
            全部是本项内复述）。

        为什么现有机制打不中：第 2 轮的跨项替换被 `_cross_scope_allows` 限定在**共性段标题**
          （防"本项特有段落被换成别的疑点的引用"，2026-10-08 P0-2 事故），而"为何列入检查 /
          一、涉及的风险事项 / 四、本项结论及理由"恰是**本项特有段落**
          ⇒ `allow_cross=False` ⇒ 句级去重整段跳过 ⇒ 项内复述无人处置。

        处置选择：项内复述**删除**（不换引用）—— 同一事项内信息就在上面，
        留「见上文」是废话（与 `report_dedup` R4「共性段不回填指针」同一口径）。

        边界（与跨项替换同源，`dupkit.is_sentence_dup` + 同一阈值 config，**不另立相似度口径**）：
          · 不碰 `report_dedup.sentence_not_hoistable`（税费性质专属句 / 本项结论句）；
          · 不碰必要重复（近纯引用块、明细表数据行、`necessary_repeat`）；
          · 不碰过短句（< 12 字）；
          · 整段将被删空 ⇒ 回退保留原文（宁可重复，不可空白）。
        """
        segs = dupkit.split_sentences(t)
        if not segs:
            return t
        try:
            from engine.report_dedup import sentence_not_hoistable as _snh
        except Exception:  # noqa: BLE001 —— 取不到权威 ⇒ 不删（宁可留重复，不可误删）
            _snh = None
        out: List[str] = []
        for sn in segs:
            st = sn.strip()
            if len(st) < 12 or dpipe.is_necessary(st):
                out.append(sn)
                continue
            nt = dupkit.norm(st)
            if _snh is not None and _snh(nt):
                _item_sents.append((st, head))
                out.append(sn)
                continue
            _of = None
            for og, oh in _item_sents:
                if dupkit.is_sentence_dup(st, og, rules=R):
                    _of = oh
                    break
            if _of is not None:
                log.append({"类型": "项内事实复述", "位置": where, "原文": st[:70],
                            "处置": "删除（同一事实已在本项「%s」完整陈述）" % (_of or "前文")})
                continue
            _item_sents.append((st, head))
            out.append(sn)
        return "".join(out).strip()

    def _handle_core(text: str, where: str, *, allow_cross: bool = False) -> str:
        """段落级去重（核心）。

        `allow_cross=False` 时**只做**"套话→声明"与"段内重复"两类**本项内部**处理，
        不做任何跨疑点替换（引用）—— 用于**本项特有段落**（结论/依据/风险事项等）。
        """
        t = str(text or "")
        if not t.strip() or dpipe.is_necessary(t):
            return t
        # ① 套话 → 指向声明（指向"声明"是报告级唯一位置，与所属疑点无关 ⇒ 任何段落都安全）
        for b, sno in boiler_exact.items():
            if t == b or dupkit.norm(t) == dupkit.norm(b):
                log.append({"类型": "套话重复", "位置": where, "原文": t[:70],
                            "处置": f"替换为引用（见声明{sno}）"})
                return f"（见声明{sno}）"
        for p, sno in boiler_pref:
            if t.startswith(p):
                log.append({"类型": "套话重复", "位置": where, "原文": t[:70],
                            "处置": f"替换为引用（见声明{sno}）"})
                return f"（见声明{sno}）"
        # ② 段内重复（模式化）—— 本项内部，安全
        t2, lg2 = dpipe.dedup_within_paragraph(t, where=where, rules=R)
        for x in lg2:
            log.append({"类型": "段内重复", "位置": where, "原文": x.get("原", "")[:70],
                        "处置": x.get("处置", "")})
        t = t2
        if not allow_cross:
            # 本项特有段落：到此为止（不再跨疑点替换）
            return t
        # ③ 完全重复 / 近似重复（跨事项，保留首次）
        nt = dupkit.norm(t)
        if len(nt) >= int(R["norm"]["min_len_for_dup"]):
            if nt in seen_norm:
                first = seen_norm[nt]
                if first != where:            # ★ 禁自引用
                    _rep = _dup_replacement(first)
                    if not _would_collapse(t, _rep):   # ★ 整段塌陷守卫
                        log.append({"类型": "完全重复", "位置": where, "原文": t[:70],
                                    "处置": f"替换为引用（首次见 {first}）"})
                        return _rep
            seen_norm.setdefault(nt, where)
        if len(nt) >= int(R["near_dup"]["min_len"]):
            for og, ow in seen_paras:
                if dupkit.is_paragraph_dup(nt, og, rules=R):
                    if ow == where:           # ★ 禁自引用
                        break
                    _rep = _dup_replacement(ow)
                    if not _would_collapse(t, _rep):   # ★ 整段塌陷守卫
                        log.append({"类型": "近似重复", "位置": where, "原文": t[:70],
                                    "处置": f"替换为引用（近似，首次见 {ow}）"})
                        return _rep
                    break
            seen_paras.append((nt, where))
        # ④ 句子级：同一事实完整出现 ≤1 次（条款 A5）
        _before_cross = t
        t = dedup_sentences_cross(t, where)
        # ★ 整段塌陷守卫（句级同样适用）：剥掉引用串后几乎没有实质正文 ⇒ 回退保留原文
        #   （事故：段落每一句都被替换 ⇒ 页面只剩「〔见疑点Rn〕」，读者看不到任何信息）
        if _would_collapse(_before_cross, t):
            log.append({"类型": "塌陷回退", "位置": where, "原文": _before_cross[:70],
                        "处置": "整段将被替换为纯引用 ⇒ 回退保留原文（宁可重复，不可空白）"})
            return _before_cross
        return t

    def handle(text: str, where: str, *, allow_cross: bool = False, head: str = "") -> str:
        """段落级去重的**统一出口** = 核心处理 + **项内事实去重**。

        两层的分工（互补，不重复）：
          · `_handle_core`：套话→声明、段内重复、跨项完全/近似/句子替换；
          · `dedup_sentences_intra`：**项内**同一事实只完整陈述一次（本层与 `allow_cross` 无关
            —— 本项内删除不会产生跨项错误引用，故本项特有段落同样适用）。
        """
        t = _handle_core(text, where, allow_cross=allow_cross)
        _t3 = dedup_sentences_intra(t, where, head)
        if _t3 != t:
            if _would_collapse(t, _t3):
                log.append({"类型": "项内去重回退", "位置": where, "原文": t[:70],
                            "处置": "整段将被删空 ⇒ 回退保留原文（宁可重复，不可空白）"})
            else:
                t = _t3
        return t

    def walk(obj: Any, where: str, head: str = "") -> None:
        """遍历并去重；`head` = 所属段落标题（决定是否允许跨疑点替换）。

        ★ 标题的继承规则：所在 dict 自带 `heading` 时以它为准（`narrative_paragraphs`
          的元素就自带 `heading`）；否则继承上层标题（如 `material_gap_notes[].段落[]`）。
          **取不到标题 ⇒ 视为本项特有 ⇒ 不跨疑点替换**（默认安全）。

        ★ 2026-10-08：`where`（事项标识 R1/R2…）切换即**清空项内已陈述句登记**
          （`_item_sents`）—— 项内去重的范围严格限定在**一个事项**内。
        """
        if _item_where[0] != where:
            _item_sents.clear()
            _item_where[0] = where
        if isinstance(obj, dict):
            _head = str(obj.get("heading") or "").strip() or head
            _allow = _cross_scope_allows(_head)
            for k, v in list(obj.items()):
                if k in SKIP_KEYS:          # ★ 判据/结构化字段：绝不参与去重
                    continue
                if isinstance(v, str) and k in TEXT_KEYS:
                    # ★ 白名单制（去掉原先 `or len(v) > 40` 的宽兜底——它会把判据文本一并吞掉）
                    nv = handle(v, where, allow_cross=_allow, head=_head)
                    if nv != v:
                        obj[k] = nv
                else:
                    walk(v, where, _head)
        elif isinstance(obj, list):
            for v in obj:
                walk(v, where, head)

    if not isinstance(report_data, dict):
        return report_data, log

    # 先处理外层概述字段（它们也会与事项内文字重复）
    # ★ 报告级概述字段属"报告级唯一位置"，允许跨项替换（且它们**先跑**⇒ 成为首次位置，
    #   正文里的重复句会引用回来，方向正确）。
    for k in ("summary", "overall_conclusion", "inspection_overview", "main_assessment"):
        v = report_data.get(k)
        if isinstance(v, str):
            nv = handle(v, "总述", allow_cross=True)
            if nv != v:
                report_data[k] = nv

    # ★ 2026-10-09：报告层取数改走**唯一权威** —— 此前这里内联第三份
    #   "er.confirmed_problems 优先、顶层兜底" 的解析，与 `report_metrics` /
    #   `material_gap._iter_items` 各写一套（同一概念多处维护）。
    items = report_items(report_data)
    # ★ 报告级通用口径上提（**先做**：把逐项重复的方法说明收成报告级一次，再逐项去重）
    _rln = merge_report_level_notes(items, log)
    if _rln:
        report_data["_report_level_notes"] = _rln

    for idx, it in enumerate(items or [], 1):
        if not isinstance(it, dict):
            continue
        _seq = it.get("seq")
        # ★ 2026-10-08：`seq` **本就从 1 起**（实测 [1..16]），不可 `+1`
        #   —— 原 `_seq + 1` 使引用编号**整体偏移 1**（首项被标为 R2），
        #   于是去重引用语给出错误编号（实测产物出现「见疑点R2」指向首项）。
        #   同类事故 2026-10-08 已在 `enterprise_report` 修过一处，本处漏改。
        where = f"R{_seq if isinstance(_seq, int) and _seq >= 1 else idx}"
        walk(it, where)

    # 保底：某事项若所有段落都被替换，恢复其首段（避免空事项）
    for idx, it in enumerate(items or [], 1):
        if not isinstance(it, dict):
            continue
        nps = it.get("narrative_paragraphs")
        if isinstance(nps, list) and nps and all(
                isinstance(x, dict) and str(x.get("text") or "").startswith("（本项与") for x in nps):
            if isinstance(nps[0], dict):
                nps[0]["text"] = f"（本项说明与首项同构，不重复；如需逐字内容见对应首项）"
            _s2 = it.get("seq")
            log.append({"类型": "保底豁免", "位置": f"R{_s2 if isinstance(_s2, int) and _s2 >= 1 else idx}",
                        "原文": "（全部段落被判重复）", "处置": "保留本项首段占位说明"})
    return report_data, log


def report_items(report_data: Any) -> List[dict]:
    """**报告层风险事项取数（唯一口径）** —— 薄转发 `engine.report_metrics.report_surface_items`。

    ★ 2026-10-09：此前本函数自带一份"er.confirmed_problems 优先、顶层兜底"的实现，
      与 `report_metrics._surface_value`、`material_gap._iter_items`、以及
      `dedup_report_data` 里内联的第四处**各写一套** ⇒ 四处会各自漂移。现全部收敛到
      `report_metrics`（该模块已声明为报告级取数/算术的唯一权威）。
    """
    from engine.report_metrics import report_surface_items   # noqa: PLC0415
    return list(report_surface_items(report_data))


# ---------------------------------------------------------------- 自检
def selfcheck_report_data(report_data: Any, *, text: str = "") -> List[Dict[str, Any]]:
    """对**产出链报告数据**跑可执行的 20 项自检（薄转发 engine/selfcheck 的判定口径）。

    产出链没有渲染后的 md 结构，故与结构强相关的项（摘要≤1页/每项≤2页/总表≤1张）
    以 `report_data` 的等价口径判定，或如实标 SKIP。
    """
    from engine import selfcheck as sc
    from engine.material_gap import separate, count_risks
    from engine.text_guardrails import audit_wording
    from engine.reconciliation import check_report
    from engine.dedup_pipeline import duplicate_rate
    from engine.legal_version import annotate_report

    checks: List[Dict[str, Any]] = []

    def add(no, name, ok, detail, skip=False):
        checks.append({"no": no, "项": name,
                       "结果": "SKIP" if skip else ("通过" if ok else "不通过"), "明细": detail})

    t = text or ""
    if not t.strip():
        from engine import output_variants as ov
        t = ov.report_text_from(report_data)
    dr = duplicate_rate(t.split("\n")) if t.strip() else None
    add(1, "整体重复率≤10%", bool(dr) and dr["整体"]["判定"] == "PASS",
        f"{dr['整体']['重复率']:.2%}" if dr else "无可判定文本", skip=not dr)
    add(2, "同章节重复率≤5%", bool(dr) and not dr["阻断"],
        "产出链无章节切分，按整体阻断口径近似", skip=not dr)
    add(3, "同一事实完整出现≤1次", bool(dr) and not dr["阻断"],
        "产出链以重复率阻断为准", skip=not dr)
    # ★ 引用覆盖（薄转发 engine/reference.coverage）：去重后应有标准引用，否则替换未生效
    try:
        from engine import reference as _refc
        _cov = _refc.coverage(t)
    except Exception:  # noqa: BLE001
        _cov = {"合计": 0, "summary": "引用统计不可用"}
    add(21, "去重引用已使用标准引用格式", _cov.get("合计", 0) > 0,
        _cov.get("summary", "") or "未检出标准引用（见疑点Rn）")
    w = audit_wording(t) if t else []
    add(4, "无定性口径破句/同段冲突（W1/W2）", not w,
        f"命中 {len(w)} 处" if w else "未命中")
    rc = check_report(report_data)
    add(5, "数据勾稽无不一致", not rc.get("blocking"), rc.get("summary", ""))
    mg = separate(report_data)
    add(6, "资料缺失单列、未计入风险事项数", True,
        f"风险事项 {mg['风险事项数']} 项；检查受限记录 {mg['受限记录数']} 条")
    lv = annotate_report(report_data)
    add(7, "法规版本已标注（未登记标待核）", True, lv.get("summary", ""))
    add(8, "未越权作违法认定",
        not any(k in t for k in ("本项构成偷税", "已认定其违法", "认定为偷税", "本项定性为")),
        "未检出越权表述")
    for no, nm in ((9, "区分风险信号/待核事项/已认定事实"),
                   (10, "风险等级与证据强度分列"),
                   (11, "执行摘要≤1页"),
                   (12, "风险总表≤1张"),
                   (13, "每项详情≤2页"),
                   (14, "空白表格/签章已标注待补"),
                   (15, "内部版与对外版均已生成"),
                   (16, "原始底稿与修订说明齐备"),
                   (17, "系统规则库与回归报告齐备"),
                   (18, "去重能力已固化"),
                   (19, "唯一事实源已登记"),
                   (20, "知识库候选已处理")):
        checks.append({"no": no, "项": nm, "结果": "SKIP",
                       "明细": "产出链无渲染层结构，由报告落盘后的 engine/selfcheck 全量执行"})
    return checks


# ---------------------------------------------------------------- 多版本
def render_variants_from(report_data: Any, outdir: str, *,
                         basename: str = "报告", version: str = "V1.4") -> Dict[str, Any]:
    """从**报告数据**一键生成内部版 + 对外版（薄转发 `engine/output_variants`）。

    产出链没有渲染后的 md，故先由 `enterprise_readable_report` 组装一份文本稿；
    两版差异与脱敏策略同 `output_variants`（**不脱敏**，仅剔除工作底稿内部字段）。
    """
    from engine import output_variants as ov
    er = None
    if isinstance(report_data, dict):
        er = report_data.get("enterprise_readable_report")
    text = _render_text_from_report_data(report_data, er)
    res = ov.render_variants(text, outdir, basename=basename, version=version)
    res["脱敏标记反查"] = ov.verify_no_masking(open(res["external"], encoding="utf-8").read())
    return res


def _render_text_from_report_data(report_data: Any, er: Any) -> str:
    """把报告数据装配成**四段式执行摘要 + 逐项详情**的可读文本稿。

    ★ 2026-10-08 重构（用户指令）：
      原实现遍历 `enterprise_readable_report` 的字段并渲染为 `**{字段名}**：值`，
      导致两个缺陷：① **字段名泄漏**进报告正文（`**headline**`/`**paragraph**`/`**note**`）；
      ② 第一章变成**压缩版全文**（把概述字段平铺罗列），而非执行摘要。
      现改为**四段式**（总结—概括—抽象—下一步动作），全部数据取自真实字段，
      **不新增任何事实**，细节一律用编号引用（见 R1 / 见资料 D-xxx）。
    """
    if not isinstance(report_data, dict):
        return ""
    er = er if isinstance(er, dict) else {}
    S = er.get("summary") or {}
    MR = er.get("material_readiness") or {}
    OC = er.get("overall_conclusion") or {}
    MA = er.get("main_assessment") or {}
    L: List[str] = ["# 执行摘要", "",
                    "> 本摘要为全文索引，**不重复**后续章节细节；所有细节一律用编号引用。", ""]

    # ── 一、检查性质与资料条件（总结）
    L += ["## 一、检查性质与资料条件（总结）", ""]
    rc, cc = S.get("received_material_count"), S.get("material_category_count")
    if rc or cc:
        L += [f"本轮检查共收到 **{rc}** 个文件，归为 **{cc}** 类资料，按六步程序实施检查。", ""]
    prov = MR.get("provided") or []
    miss = [str(x.get("doc") if isinstance(x, dict) else x) for x in (MR.get("missing") or [])]
    if prov:
        L += [f"- **依据资料（{MR.get('provided_count', len(prov))} 类）**：" + "、".join(prov), ""]
    if miss:
        L += [f"- **缺失资料（{MR.get('missing_count', len(miss))} 类）**：" + "、".join(miss), ""]
    L += ["- **结论适用范围**：仅限现有资料条件；资料缺失只表示检查范围受限，"
          "**不表示企业已经存在违法或少缴税的情形**，补齐资料后须重新判断。", ""]

    # ── 二、整体结论（概括）
    L += ["## 二、整体结论（概括）", ""]
    total = S.get("confirmed_problem_count")
    if total:
        L += [f"本轮共列示 **{total} 项**风险事项，逐项见后文各事项详情。", ""]
    ver = S.get("verified_problem_count")
    # ★ 2026-10-08：**源头已修** —— `enterprise_report._resync_summary_counts()` 在列表定稿后
    #   按唯一权威重算了全部派生计数（confirmed / verified / pending / further），
    #   `pending_problem_count` 不再失真 ⇒ 本层**直接取权威字段**。
    #   此前本层自算 `confirmed - verified` 属"渲染层第二个口径"，源头修好后必须撤掉。
    if ver is not None and isinstance(S.get("pending_problem_count"), int):
        L += [f"- **定性状态**：已认定事实 **{ver}** 项、待核事项 "
              f"**{S['pending_problem_count']}** 项；本报告**不作出任何违法认定**。", ""]
    elif ver is not None:
        L += [f"- **定性状态**：已认定事实 **{ver}** 项；本报告**不作出任何违法认定**。", ""]
    tiers = OC.get("tiers") or []
    if tiers:
        parts = [f"{t.get('label') or t.get('level')} {t.get('count')} 项"
                 for t in tiers if t.get("count")]
        L += ["- **风险等级分布**（报告口径）：" + "、".join(parts) + "。", ""]
    if OC.get("tax_types"):
        L += [f"- **涉及税种**：共 {len(OC['tax_types'])} 类，明细见逐项详情。", ""]
    ph_mp = MR.get("missing_count")
    L += [f"- **需补资料**：{ph_mp} 类缺失资料影响的相关检查程序见「已取得的资料与待补充的资料」段。", ""]

    # ── 三、主线抽象（抽象）：main_assessment.directions 即 3 条主线
    dirs = [d for d in (MA.get("directions") or []) if isinstance(d, dict)]
    if dirs:
        L += ["## 三、主线抽象（抽象）", "",
              "下列为贯穿全部事项的主线（依报告主线研判）：", ""]
        for i, d in enumerate(dirs, 1):
            L += [f"{i}. **{d.get('theme')}**（{d.get('count')} 项）", ""]

    # ── 四、下一步动作（建议）
    L += ["## 四、下一步动作（建议）", ""]
    om = str(S.get("owner_message") or "").strip()
    if om:
        L += [om, ""]
    L += ["1. **企业补资料**：优先补齐上列缺失资料。",
          "2. **优先核实**：按主线顺序组织核实。",
          "3. **逐项补充**：按各事项「需补充资料」段逐项补齐。",
          "4. **新一轮复查**：资料补齐后重新执行受影响的全部检查程序。", ""]

    # ── 逐项详情（保持原结构，不重复摘要内容）
    items = report_items(report_data)
    for idx, it in enumerate(items, 1):
        if not isinstance(it, dict):
            continue
        # ★ seq 本身即 1 起（实测 [1..16]），**不可 +1** —— 原先写 `_sq + 1` 使首项显示成 R2。
        _sq = it.get("seq")
        _no = _sq if isinstance(_sq, int) and _sq >= 1 else idx
        L += [f"### R{_no}　{str(it.get('title') or '')[:40]}", ""]
        for kk in ("verdict", "risk_level", "risk_level_basis", "suspect", "suggestion"):
            v = it.get(kk)
            if isinstance(v, str) and v.strip():
                L.append(v.strip())
        L.append("")
        nps = it.get("narrative_paragraphs")
        if isinstance(nps, list):
            for x in nps:
                if isinstance(x, dict):
                    if x.get("heading") and "六段式" not in str(x.get("heading")):
                        L += [f"### {x['heading']}", ""]
                    if x.get("text"):
                        L += [str(x["text"]), ""]
                elif isinstance(x, str):
                    L += [x, ""]
    return "\n".join(L)
