# -*- coding: utf-8 -*-
"""疑点自我怀疑层（证伪优先）—— **唯一权威**（2026-10-06）。

═══════════════════════════════════════════════════════════════════════════
用户原话
═══════════════════════════════════════════════════════════════════════════
「给一键分析按钮增加一个**对疑点产生自我怀疑**的能力，然后一键分析按钮会
 **以终为始拆解疑点的关键信息，自我反驳，并再索取资料信息进行自我验证**。」

═══════════════════════════════════════════════════════════════════════════
为什么需要（根因）
═══════════════════════════════════════════════════════════════════════════
系统已有的推演层（`inference_ladder`）回答的是「**这件事可能是什么**」
（正常解释 / 违规手法 / 哪份资料能区分 / 渠道逻辑限制）。
但它**不问"我这条疑点本身是不是错的"** —— 于是出现两类反复被用户抓到的事故：
  · 依据里写的关键词与实际命中的关键词不一致（写"集体福利"、实际命中"餐饮"）；
  · 结论依赖的前提事实系统里根本没有（判"应转出未转出"，却从未核实票种与是否已抵扣）。
⇒ 结论一旦立起来，就**没有人替它找反证**。本层补的正是这一环：**先证伪自己**。

═══════════════════════════════════════════════════════════════════════════
与 `inference_ladder` 的分工（⚠ 别重复造轮子）
═══════════════════════════════════════════════════════════════════════════
  · `inference_ladder`  —— 「这件事**可能是什么**」（面向对象的推演）
  · `self_doubt`        —— 「我**凭什么这么说**、我**可能错在哪**、**拿什么能推翻我**」（面向自身的证伪）
本层**不重算任何判定**：要件/证据现状/金额口径/待补清单**全部读既有权威字段**：
  · `detail_table`（证据角色表：证据角色/证据名称/证明目的/现状/依据）← 由 `evidence_chain` 产出
  · `confidence_breakdown`（可信度分项：基准分/材料齐全程度/环节数据完整度/反证已提交比例）
  · `tax_impact`（涉案金额 + `amount_context` 口径来源）
  · `missing_material_names` / `verify_materials` / `evidence_have` / `evidence_need`
  · `conclusion_grade` / `verdict`
本模块**只读**，不改变任何结论、不新增线索。

═══════════════════════════════════════════════════════════════════════════
设计原则（数据驱动；新增同类只加一行数据，不改判定分支）
═══════════════════════════════════════════════════════════════════════════
D1 **以终为始**：从"本项若不成立，最可能因为什么"反推，定位到具体的支撑信息，
   而不是泛泛地说"需进一步核实"。
D2 **每条支撑都要有反驳与推翻条件**：说不出"什么情况下它就不成立"的支撑，
   说明它根本不是可验证的事实，应当从依据里撤下。
D3 **只索取能验伪的资料**：要哪份、看哪个字段、满足什么条件就**推翻本项**——
   不说"请提供相关资料"这种无法执行的话。
D4 **诚实标注薄弱环节**：可信度分项里取值最低的那一项，必须点名。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# ── 证据「现状」的**归类**（唯一实现；词表**不在这里重抄**，从既有权威派生）──────────
#   ★★ 2026-10-06（**同一坑今日第三次**）：第一版把 key 写死成 `已有/待核/缺失`，
#      而产物里的「现状」实际是 `已有 / 已提供同类资料 / 待企业提交 / 缺失` —— 猜词表 = 判据空转。
#   ★★ 更隐蔽的一层（由契约测试当场抓到）：`待核` 这个词**在两种语境里含义不同** ——
#      · 在**要件核对**语境（`constituent_checkpoint._MISSING_STATUS`）里它是"未取得"；
#      · 在**证据角色表**语境里它是"同类资料已提供、未逐字对应"，且
#        `report_wording.STATUS_TEXT` 会在输出前把它**改写成「已提供同类资料」**。
#      ⇒ 本模块要的是**证据角色表**语义 ⇒ 词表必须取 `report_wording`，**不能取要件那份**
#        （取错就会出现"内部=missing、输出后=pending"同一状态两支的现象）。
_STATUS_PROVIDED = ("已有", "已提供")
_STATUS_MISSING = ("缺失", "未提供", "待企业提交", "待提交", "未取得", "未上传", "未提供资料")


def _status_branches():
    """返回 (pending 词集, missing 词集, provided 词集)；**从既有权威派生，不重抄**。"""
    pending = set()
    try:
        from engine.report_wording import STATUS_TEXT as _ST
        for _k, _v in (_ST or {}).items():
            for _w in (_k, _v):
                _w = str(_w or "").strip()
                # 只要"状态词"，不要句首/结构标识（如「待核线索：」「待核实事实：」带冒号）
                if _w and not _w.endswith(("：", ":")) and len(_w) <= 12:
                    pending.add(_w)
    except Exception:                                            # noqa: BLE001
        pending |= {"待核", "尚需核实", "尚需核实", "已提供同类资料"}
    provided = {str(x) for x in _STATUS_PROVIDED}
    missing = {str(x) for x in _STATUS_MISSING}
    return pending - provided - missing, missing, provided


def _status_branch(status: str) -> str:
    """把「现状」归到 `missing` / `provided` / `pending` 三支（**唯一归类入口**）。

    ⚠ 未知词归 `pending`（不当作"已有"、也不据此索取），并由闸门断言产物里不出现未知词
      —— 这样**新增一个状态词**会以"闸门报警"的方式暴露，而不是静默走错分支。
    """
    st = _norm(status)
    pending, missing, provided = _status_branches()
    if st in provided:
        return "provided"
    if st in missing:
        return "missing"
    return "pending"


# ── 三支 → 反驳口径（**数据表**；新增同类只加一行）──────────────────────────────
_BRANCH_DOUBT: Dict[str, Dict[str, str]] = {
    "provided": {
        "doubt": "该证据本轮已提供，但是否覆盖本项要求的范围与口径尚未逐项确认；"
                 "若其覆盖范围不足，「已提供」不等于「足以支撑本项」。",
        "overturns_if": "经核对，该资料确已覆盖本项要求的全部范围与口径 ⇒ 这一条的支撑成立"
                        "（不推翻本项，但本项的可信度应据此上调）。",
        "look_for": "该资料是否覆盖本项要求的范围（如：是否含全部账户、是否逐笔到明细、是否含附表）",
    },
    "pending": {
        "doubt": "该证据本轮未逐字见到，只是「同类资料已提供」；"
                 "若该资料其实不含本项所需内容，本项的这一支撑即为空。",
        "overturns_if": "经核对，已提供的同类资料中确实包含本项所需内容且口径一致 ⇒ 支撑成立；"
                        "若确认不包含 ⇒ 本项应退回「资料不足、不作认定」。",
        "look_for": "该类资料中是否真含本项所需的具体内容（逐字比对，不是凭名称相似）",
    },
    "missing": {
        "doubt": "该证据本轮未提供，是支撑链上最弱的一环；"
                 "缺它就无法认定本项成立 —— 只能列为「资料未齐、不作认定」。",
        "overturns_if": "该证据补齐后，若显示相关业务真实、口径一致 ⇒ 本项不成立（可自证清白）。",
        "look_for": "该证据本身（补齐后核对其内容与本项口径是否一致）",
    },
}

# ── 可直接索取资料的支（缺失 = 企业还没交）────────────────────────────────────
_REQUESTABLE_BRANCH = "missing"
# ── 「前置（直接）证据 未取得/未定」⇒ 未验证前不得认定（判据的唯一实现）──────────
_DIRECT_ROLE_KW = ("直接证据",)


def _norm(s: Any) -> str:
    return str(s or "").strip()


def _plain(s: Any) -> str:
    """把**上游文本**搬进本段前先洗一遍（正文禁 markdown）。

    ★ 2026-10-06 实测：`tax_impact.amount_context` 本身就带 `**含税**` 这类标记，
      直接抄进报告会渲染成字面星号 ⇒ 凡本模块**复制**上游字段的地方都要过这里。
    """
    return str(s or "").replace("**", "").strip()


def _evidence_rows(p: Dict) -> List[Dict]:
    dt = p.get("detail_table")
    rows = (dt or {}).get("rows") if isinstance(dt, dict) else None
    return [r for r in (rows or []) if isinstance(r, dict)]


def _amount_input(p: Dict) -> Optional[Dict]:
    """涉案金额及其**口径来源**（金额是本项最容易被忽略的支撑）。"""
    ti = p.get("tax_impact") or {}
    if not isinstance(ti, dict) or not ti.get("available"):
        return None
    basis = ti.get("basis")
    ctx = _plain(ti.get("amount_context"))
    if basis in (None, "", 0):
        return {
            "item": "涉案金额",
            "value": "本项未量化金额",
            "strength": "弱",
            "doubt": "本项未给出可复算的涉案金额 ⇒ 风险量级无从校验；"
                     "「未量化」不等于「金额小」，也不等于「没有」。",
            "overturns_if": "给出可复算的金额口径后，若金额可忽略或实为其他口径的重叠计算 ⇒ 本项量级应下调。",
            "look_for": "本项涉案金额的计算口径与逐笔明细",
        }
    return {
        "item": "涉案金额",
        "value": "约 %s 元" % f"{float(basis):,.2f}",
        "strength": "中",
        "doubt": ("金额是按「%s」这一口径算出来的；若口径变化（含税/不含税、期间口径、"
                  "是否与其他疑点重叠），金额随之变化。" % ctx) if ctx
                 else "金额口径来源未注明；口径一变，金额随之变化。",
        "overturns_if": "按另一口径复算后金额显著变化，或与他项重复计算 ⇒ 本项金额应相应调整。",
        "look_for": "该金额的取数口径与逐笔明细（可否独立复算）",
    }


def _weakest_confidence(p: Dict) -> Optional[Dict]:
    """可信度分项里**取值最低**的一项 —— 本项最薄弱的环节（诚实点名）。"""
    br = p.get("confidence_breakdown") or []
    worst = None
    for it in br:
        if not isinstance(it, dict):
            continue
        try:
            v = float(it.get("取值"))
        except (TypeError, ValueError):
            continue
        if worst is None or v < float(worst.get("取值")):
            worst = it
    if not worst:
        return None
    try:
        v = float(worst.get("取值"))
    except (TypeError, ValueError):
        return None
    if v >= 1.0:
        return None
    return {
        "item": "最薄弱环节（可信度分项）",
        "value": "%s（取值 %s）" % (_norm(worst.get("项")), worst.get("取值")),
        "strength": "弱",
        "doubt": "本项可信度的分项计算中，这一项取值最低 ⇒ 它是决定本项可信度上限的环节；"
                 "只提高其他环节不改变结论。",
        "overturns_if": "把这一项补足（例如材料齐全程度、环节数据完整度）后重新计算可信度即可验证。",
        "look_for": "提升该分项所缺的输入（见本项「需补充资料」）",
    }


def _tier_input(p: Dict) -> Optional[Dict]:
    """按**证据地位**给一条反驳 —— 对"非红线来源"的风险事项尤其重要。

    ★ 2026-10-06：被并入第二章的 8 条（原子规则/域分析/组合画像/专项比对）**没有证据角色表**，
      但它们恰恰是最需要自我怀疑的一类：它们只说"数据事实成立"，**不等于"税务违规成立"**。
      判据用 `evidence_tier`/`source` 的**前缀**匹配（数据驱动；新增同类只加一行）。
    """
    tier = _norm(p.get("evidence_tier")) or _norm(p.get("source"))
    if not tier:
        return None
    for k, v in _TIER_DOUBT.items():
        if k in tier:
            return {
                "item": "结论来源（证据地位）",
                "value": tier,
                "strength": "中",
                "doubt": v["doubt"],
                "overturns_if": v["overturns_if"],
                "look_for": v["look_for"],
            }
    return None


# ── 证据地位 → 反驳口径（**数据表**；key 用前缀匹配）──────────────────────────
_TIER_DOUBT: Dict[str, Dict[str, str]] = {
    "已验原子规则": {
        "doubt": "本项来源是「已验原子规则」——它证明的是数据事实（如名单重叠、金额不一致），"
                 "不等于税务违规；由数据事实到违规之间还隔着业务实质、口径与主观要件。",
        "overturns_if": "若这些数据事实可由正常业务解释（口径差异、跨期、集团内往来、行业惯例）"
                        "⇒ 本项不构成税务风险。",
        "look_for": "能解释该数据事实的业务凭证（合同、结算单、往来说明、跨期调节表）",
    },
    "域分析结论": {
        "doubt": "本项来源是「域分析结论（基于上传资料计算）」——它是对已提供资料的计算与归纳，"
                 "其正确性受资料完整度与口径选择限制；换口径可能得出不同结论。",
        "overturns_if": "按另一合理口径复算后结论不再成立，或所依据的资料本身不完整 ⇒ 本项应重算或撤回。",
        "look_for": "本项计算所依据的原始明细与口径说明（能否独立复算）",
    },
    "组合风险信号": {
        "doubt": "本项来源是「组合风险信号」——它是多条线索同时出现后的合成判断，"
                 "本身不是独立事实；若其中任一环节被合理解释，组合即不成立。",
        "overturns_if": "构成本项的各环节中，只要有环节被合理解释排除 ⇒ 组合信号应相应减弱或撤销。",
        "look_for": "构成本项的各环节各自的举证材料（逐环节排除，而非整体否认）",
    },
    "专项比对结论": {
        "doubt": "本项来源是「专项比对结论」——它按特定规则比对已上传资料得出，"
                 "未经过红线构成要件核对；比对规则的前提若与实际业务不符，结论即不成立。",
        "overturns_if": "比对规则所依赖的前提被推翻（如票种/用途/口径与实际不符）⇒ 本项不成立。",
        "look_for": "检验该比对规则前提的资料（如票种、用途说明、勾选记录）",
    },
}


def _split_sources(text: str) -> List[str]:
    """从「本项依据的独立数据源：A（已上传）、B。」里抽出资料名（唯一解析入口）。"""
    import re as _re
    m = _re.search(r"独立数据源[:：]([^。]{1,120})", str(text or ""))
    if not m:
        return []
    seg = m.group(1)
    seg = _re.sub(r"[（(][^）)]*[）)]", "", seg)          # 去括注（"已上传"等）
    return [x.strip() for x in _re.split(r"[、,，;；]", seg) if x.strip()]


def _fallback_inputs(p: Dict, requested: List[Dict]) -> List[Dict]:
    """没有证据角色表时的兜底：从叙事段取「独立数据源 / 尚需…」，再补证据地位反驳。"""
    out: List[Dict] = []
    seg3 = ""
    for sg in (p.get("narrative_paragraphs") or []):
        h = _norm(sg.get("heading"))
        if h.startswith("三、") or h.startswith("已取得的资料"):
            seg3 = _plain(sg.get("text"))
            break
    srcs = _split_sources(seg3)
    if srcs:
        out.append({
            "item": "本项依据的独立数据源",
            "value": "、".join(srcs),
            "strength": "中",
            "doubt": "这些数据源本轮已上传，但它们是否足以独立支撑本项结论尚未确认；"
                     "由原始数据到本项结论之间还隔着口径与业务实质。",
            "overturns_if": "若这些数据源中的关键项经核对与本项口径不一致 ⇒ 本项依据不成立。",
            "look_for": "各数据源中与本项口径对应的具体内容（逐项比对）",
        })
    if "尚需" in seg3 or "需补充" in seg3:
        _tail = seg3.split("尚需", 1)[-1] if "尚需" in seg3 else seg3.split("需补充", 1)[-1]
        out.append({
            "item": "本项尚未闭合的环节",
            "value": _plain(_tail)[:80],
            "strength": "弱",
            "doubt": "本项尚有环节未闭合：现在的结论只覆盖已核对到的部分，未闭合部分不作认定。",
            "overturns_if": "未闭合环节补齐后若显示业务真实、口径一致 ⇒ 本项不成立（可自证清白）。",
            "look_for": "该未闭合环节所缺的资料",
        })
        # 未闭合环节 ⇒ 需要企业提供资料（不必解析出具体名，给可执行方向）
        if not requested:
            requested.append({
                "material": _plain(_tail)[:40],
                "look_for": "该环节所缺资料的具体内容",
                "overturns_if": "补齐后若业务真实、口径一致 ⇒ 本项不成立。",
            })
    # ★★ 2026-10-06（**自审暴露**）：非红线来源的 8 条（原子规则/域分析/组合画像/专项比对）
    #   没有"证据角色表"，兜底只产出「独立数据源 + 证据地位」两条，**强弱评级全是"中"**；
    #   而红线疑点动辄 4~5 条"弱"支撑 ⇒ **越没做证据核对的项反而显得越扎实**。
    #   ⇒ 补一条**如实**的支撑：本项根本没登记"需要哪些证据、现状如何"。
    out.append({
        "item": "证据核对状态",
        "value": "未做证据角色核对（本项非红线来源，无红线证据要求）",
        "strength": "弱",
        "doubt": "本项没有登记「需要哪些证据、这些证据现状如何」⇒ 无法判断取证是否充分；"
                 "结论只建立在数据事实之上，而数据事实成立不等于税务违规成立。",
        "overturns_if": "按同样的证据核对口径为这类事项补做核对后，若所需证据缺失 "
                        "⇒ 本项同样只能列为待补证，不能认定。",
        "look_for": "本项若按红线口径核对，需要哪些证据、现状如何",
    })
    _t = _tier_input(p)
    if _t:
        out.append(_t)
    return out


def doubt_for_problem(p: Dict, provided_materials: Optional[List[str]] = None) -> Dict:
    """对**一条风险事项**产出「自我怀疑」结果。

    :param p: 风险事项 dict（`confirmed_problems[i]`）
    :param provided_materials: 本轮**已提供**的资料类别名（用于避免索取已提供资料）
    :return: {
        "available": bool,
        "key_inputs": [{item, value, strength, doubt, overturns_if, look_for}],
        "counter_reading": "站在「本项不成立」一侧的最强反驳（一句话）",
        "verdict_before_verify": "未验证前能不能认定本项",
        "requested": [{material, look_for, overturns_if}],
        "note": 口径声明,
      }
    """
    provided = {_norm(x) for x in (provided_materials or []) if _norm(x)}
    rows = _evidence_rows(p)
    key: List[Dict] = []
    requested: List[Dict] = []
    # ★★ 2026-10-06（用户评语 #6「模板重复严重，可读性差」）：
    #   旧实现里**同一「现状」分支共用同一句模板**，只有 `item` 变、句子字字相同
    #   ⇒ 全报告每条疑点后面都挂着同样 4 句话，读者读到的是"复制粘贴"，
    #     核心事实与关键差异被稀释。
    #   两处修正（都不改任何判定，只改表达）：
    #     ① **把证据名嵌进模板句**（"该证据"→「销售台账、发货记录」），
    #        句句落到本项的具体材料上 ⇒ 跨疑点自然不再雷同；
    #     ② **同项内同分支折叠**：同一分支只展开一次完整模板，其余写成一句指向。
    _branch_expanded: Dict[str, str] = {}

    def _embed(txt: str, nm: str) -> str:
        if not nm:
            return txt
        return (txt.replace("该证据", "「%s」" % nm)
                   .replace("该资料", "「%s」" % nm))

    for r in rows:
        role = _norm(r.get("证据角色"))
        name = _norm(r.get("证据名称"))
        purpose = _norm(r.get("证明目的"))
        st = _norm(r.get("现状")) or "未提供"
        _br = _status_branch(st)
        spec = _BRANCH_DOUBT.get(_br) or _BRANCH_DOUBT["pending"]
        _d = _embed(spec["doubt"], name)
        _o = _embed(spec["overturns_if"], name)
        _first = _branch_expanded.get(_br)
        if _first:
            # ② 同分支已展开过 ⇒ 只留一句指向，不再重复整段模板
            _d = "情形与「%s」相同（%s）；不再重复同一段自我反驳。" % (_first, st)
            _o = "同上：该情形一旦核对通过，「%s」这一条的支撑即成立。" % (name or _first)
        else:
            _branch_expanded[_br] = name or ("%s：%s" % (role, st))
        key.append({
            "item": "%s：%s" % (role or "证据", name or "（未命名）"),
            "value": "现状：%s%s" % (st, ("；证明目的：%s" % _plain(purpose)) if purpose else ""),
            "strength": "强" if _br == "provided" else ("中" if _br == "pending" else "弱"),
            "doubt": _d,
            "overturns_if": _o,
            "look_for": spec["look_for"],
        })
        # 只对**未提供**的证据索取资料；已提供/已提供同类资料的不得再要
        # （否则又是"让企业补它已经交过的东西"）
        if _br == _REQUESTABLE_BRANCH and name:
            requested.append({
                "material": name,
                "look_for": spec["look_for"],
                "overturns_if": spec["overturns_if"],
            })

    _ai = _amount_input(p)
    if _ai:
        key.append(_ai)
    # ★ 没有证据角色表的风险事项（被并入第二章的"非红线来源"那几类）走兜底：
    #   从叙事段取独立数据源/尚需环节 + 用证据地位给一条实质反驳。
    if not rows:
        key.extend(_fallback_inputs(p, requested))
    _wc = _weakest_confidence(p)
    if _wc:
        key.append(_wc)

    # ★★ 用户要求「**并再索取资料信息进行自我验证**」⇒ 每条风险事项都必须给出**可执行的**
    #   验证动作。若上面没能从"未提供的证据"里取到具体资料名（如非红线来源的项没有证据角色表），
    #   就用**最薄弱环节的核对方向**作为验证动作 —— 宁可给"看什么"，也不留空。
    if not requested and key:
        _weak = next((k for k in key if k.get("strength") == "弱"), key[-1])
        requested.append({
            "material": _weak.get("look_for") or "能解释本项数据事实的业务凭证",
            "look_for": _weak.get("look_for") or "",
            "overturns_if": _weak.get("overturns_if") or "若能合理解释 ⇒ 本项不成立。",
        })

    # 缺/待核 的**直接证据** ⇒ 未验证前不得认定（前置缺失，最硬的那条）
    _blocking = [r for r in rows
                 if any(k in _norm(r.get("证据角色")) for k in _DIRECT_ROLE_KW)
                 and _status_branch(_norm(r.get("现状"))) in ("missing", "pending")]
    _grade = _norm(p.get("conclusion_grade"))
    if _blocking:
        verdict_before = ("在验证前不能认定本项成立：本项的直接证据尚为"
                          "「%s」，属前置条件未满足。" % _norm(_blocking[0].get("现状")))
        counter = ("最强的反驳是：本项最关键的证据尚未取得——"
                   "现在能说的只是「出现了需要核对的迹象」，而不是「已经发生」。")
    elif _grade in ("待核", "待核实", "待核验"):
        verdict_before = ("在验证前不能认定本项成立：本项尚未认定到构成要件，"
                          "现有资料只支持「值得查」。")
        counter = ("最强的反驳是：本项未认定到任何一条构成要件；"
                   "现有资料只支持「值得查」，不支持「有问题」。")
    elif not rows:
        # ★★ 2026-10-06（自审暴露）：**没有证据角色表**的项（非红线来源）原本落到下面的 else，
        #   被写成「本项证据面相对完整」—— 而它**根本没做过证据核对**，这是**无根据的自信**
        #   （实测 8 条，其中 1 条还是高风险）。
        verdict_before = ("在验证前不能认定本项成立：本项未做证据角色核对，"
                          "现有结论只建立在数据事实之上。")
        counter = ("最强的反驳是：本项只有数据事实，没有登记需要哪些证据、现状如何；"
                   "数据事实成立不等于税务违规成立。")
    else:
        verdict_before = "本项证据面相对完整，但仍须经下列验证后方可定性。"
        counter = "最强的反驳是：本项依据均来自企业自报资料，未与外部数据交叉印证前仍可能另有解释。"

    return {
        "available": bool(key),
        "key_inputs": key,
        "counter_reading": counter,
        "verdict_before_verify": verdict_before,
        "requested": requested,
        "note": "本段是系统对自己结论的复核：每条支撑都给出「可能错在哪」与「什么情况下推翻本项」，"
                "供企业按图举证。系统不对企业的解释作预判。",
    }


def build_self_doubt(problems: List[Dict], provided_materials: Optional[List[str]] = None) -> int:
    """对全部风险事项写入 `p["self_doubt"]`，返回写入条数（**唯一接线入口**）。"""
    n = 0
    for p in problems or []:
        if not isinstance(p, dict):
            continue
        d = doubt_for_problem(p, provided_materials=provided_materials)
        if d.get("available"):
            p["self_doubt"] = d
            n += 1
    return n
