# -*- coding: utf-8 -*-
"""
论证链引擎 —— 分析论证贯穿整个风险检查过程
==================================================

稽查不是「发现异常→下结论」，而是**论证**：
    主张（触了哪条红线）
      → 论据（线索链+证据链支撑到什么程度）
        → 反证（企业可能的正当理由）
          → 反驳/检验（反证需什么证据才能成立，现有资料能否支撑）
            → 裁决（成立 / 不成立 / 证据不足待证）

三种裁决（不可逾越的边界）
--------------------------------------------------
    红线成立（confirmed）   证据链闭合且无有效反证 —— 可以作出确定性判断
    红线不成立（excluded）  反证成立并足以解释全部异常 —— 予以排除
    红线待证（unconfirmed） 证据不足或正反双方势均力敌 —— 转入置疑清单，
                            由企业提供资料自证，**系统既不认定也不否认**

铁律
--------------------------------------------------
1. 发现 ≠ 确认。触碰红线只表示「有法定情形需要核实」。
2. 缺失型信号（该有的没有）一律作为待证信号抓取，禁止通过提高阈值放过。
3. 证据不足一律转置疑清单，系统绝不自动定罪，也绝不自动免责。
"""

import math
import re
from typing import Any, Dict, List, Optional, Tuple

# 四个裁决层级：「触碰红线」与「定性」是两个层次，不可混为一谈
#   —— 符合红线的构成要件即已触碰红线（客观判断，与行业无关）；
#   —— 证据链是否闭合只决定能否「定性」，不决定「是否触碰红线」。
# ★ 2026-09-27（用户要求通俗化）：把"红线成立"等内部裁定词改为老板也能看懂的说法。
#   语义不变：仍严格区分「触碰红线（出现法定禁止情形）」与「定性（证据链是否闭合）」，
#   且绝不写"已认定违法"——系统只作初步判断，以税务机关最终认定为准。
_VERDICT_CONFIRMED = "已触碰税务违规红线（资料齐全，可作初步判断）"   # 触碰红线 + 材料齐全 → 可初步判断
# ★★ 2026-10-06（用户评语 #2「结论与证据、定性严重脱节」）：
#   旧文案是「**已**触碰税务违规红线（资料不足，待补证后判断）」——
#   前半句是**断言**、后半句又说资料不足，而用户口径很明确：
#   **证据不足时不得写"触碰红线"**，只能写"红线疑点"。
#   实测症状（用户举的三条）：印花税类疑点缺借款合同/申报表等核心证据，
#   结论却写「本企业已触碰税务违规红线」⇒ 与报告自身"证据不足不作认定"的原则正面冲突。
#   ⇒ 资料不足档一律改为「**疑似**触碰…」，把"断言"降级为"疑点"。
_VERDICT_HIT_PENDING = "疑似触碰税务违规红线（资料不足，待补充资料后判断）"
_VERDICT_EXCLUDED = "经核查未触碰违规红线（已有合理解释）"       # 反证成立 → 排除
_VERDICT_WEAK = "现有资料不足以形成税务疑点"                   # 无线索支撑 → 仅作观察
# ★ 2026-10-02（用户复核疑点5）：第五档 —— **外部数据核验待办**。
#   这类发现（category="外部核验"）的性质是「账内检出信号、认定结论取决于工商/税务/海关/
#   银行等外部数据」，其自身已声明"不作定性"。旧版只看线索链终端信号就把它们判成
#   「已触碰税务违规红线」，而报告同项下一段却写「本企业涉及上述第 无 条构成要件」——
#   同一疑点内部正面矛盾（用户复核实测）。
#   根因：把「有信号」直接等同于「已核对到法定情形」。外部数据未取得 ⇒ 要件无从核对
#   ⇒ 既不触碰红线、也不出罪，必须走独立裁决档，不能挤进触碰红线档。
_VERDICT_EXTERNAL = "账内检出需外部数据核验的信号（不作定性，待外部核验后再判断）"

# ★ 2026-10-02：触碰红线档（HIT_PENDING）的**段尾断言**，抽为模块常量。
#   理由：它是一句会进报告的**触碰红线断言**，而「能不能这么说」取决于报告端才有的
#   `participating`（要件是否被认定为成立）；报告输出闸门
#   `enterprise_report.sanitize_conclusion_assertion` 需要按整句替换它 ——
#   锚点必须与产出方同源，否则两处措辞一改就再也替换不到（静默失效）。
# ★★ 2026-10-06：与 `_VERDICT_HIT_PENDING` 同步降级为「疑似」——
#   资料不足时不得写"已经触碰"，否则报告一边说"未认定到任何一条构成要件"、
#   一边断言"已经触碰"，正面自相矛盾（用户评语 #2）。
_TAIL_HIT_PENDING = ("疑似触碰税务红线，但材料还不够齐全，本轮暂不下结论，"
                     "转由企业补充上述材料后重新检查；补充资料之前既不认定违法，也不予排除。")

# ── 「零要件认定 ⇒ 不得断言触碰红线」的唯一净化实现（2026-10-02）──────────────────
#   背景（用户复核疑点5）：同一疑点里「一、未认定到任何一条构成要件」＋
#   「四、本项结论是已触碰税务违规红线」＋段尾「已经触碰税务红线…」三句话正面冲突。
#   口径结论：触碰红线是「符合构成要件」的判断结果；一条要件都没认定时它没有依据。
#   本函数是**唯一实现**，供文本产出侧（`redline_engine` 落案卷时）与
#   报告输出侧（`enterprise_report`）共用，避免两处各写一套措辞。
# ★★ 2026-10-06（用户评语 #2「结论与证据存在冲突」+ 我的复发错误：只改了裁决词、
#   漏了这句**开头断言**）：
#   旧文案 `本企业触碰红线，即「X」，涉嫌…` 是**无条件断言**—— 不管要件是否认定、
#   资料是否齐全，开头先扣一顶"已触碰红线"的帽子；与同段的
#   「未认定到任何一条构成要件」正面冲突。
#   用户口径：「风险检查报告可以列『红线疑点』，但**不能在证据不足时写『触碰红线』**」。
#   ⇒ 统一改为**法定表述「涉嫌」**（报告不作违法认定，"涉嫌"才是合规措辞），
#     且产出侧必须**引用本常量**（禁止再硬编码，否则又是两处措辞各写一份）。
_TOUCH_REDLINE_PREFIX = "本条涉嫌触碰红线，即"
_NEUTRAL_HIT_VERDICT = "逐条要件尚未认定成立（结论只到「账内已读到与该风险指向一致的信号」这一层）"
# ★ 2026-10-06：原措辞含「待核实」——用户口径是「**报告永远不能出现待核实**」。
#   注意 `plain_language.to_plain` 会把引擎侧写的「待核」改写成「待核实」⇒
#   **引擎侧就必须避开「待核/待核实/待核验」**，不能指望出口词表兜底
#   （`scrub_vague` 只改写"整串就是状态值"的情形，嵌在句中不会被改写）。
_NEUTRAL_HIT_TAIL = (
    "账内已读到与该项风险指向一致的信号，但本轮未认定到任何一条具体构成要件成立，"
    "材料也不够齐全；因此本项只作为待核疑点登记，暂不作出触碰红线的结论，"
    "转由企业补充上述材料后重新检查；补证之前既不认定违法，也不予排除。"
)
# ★ 锚点必须**容错**：上游 `plain_language.to_plain` 会把「补证」改写成「补充资料」，
#   逐字比对 `_VERDICT_HIT_PENDING` / `_TAIL_HIT_PENDING` 会**静默失效**（实测：
#   报告里出现「待补充资料后判断」，而常量是「待补证后判断」→ 替换一次也没发生）。
#   故这里改用不含易改写词的前缀锚点，替换范围延伸到该句结束。
# ⚠ 锚点取"两档共有"的前缀（`已触碰…`/`疑似触碰…` 都含它），
#   否则档位措辞一改锚点就找不到 ⇒ 净化静默失效。
_VERDICT_HIT_ANCHOR = "触碰税务违规红线"
_TAIL_HIT_ANCHOR = "触碰税务红线，但材料还不够齐全"


def neutralize_assertion_when_no_constituent(text, redline_name=""):
    """把「一条构成要件都没认定」的论证文本里的**触碰红线断言**中性化。

    规则（宁缺勿错）：
      ① 先把 `红线「名称」` 自然化为 `红线，即名称`，使本函数**不依赖渲染顺序**
         （不论在产出侧还是输出侧调用，识别结果一致）；
      ② 首句不是本条红线的触碰红线开场（标题被裁剪过）→ 原样返回，不误伤；
      ③ 首句是 → 换成「逐条核对未认定到要件 + 只构成需核实的疑点、不等于已触碰红线
         + 待补料与外部核验」；
      ④ 段中「本项结论是<触碰红线裁决>」与段尾「已经触碰税务红线，但材料还不够齐全…」
         一并中性化 —— 只改首句会把矛盾留在同一段里。
    """
    _t = str(text or "").strip()
    if not _t:
        return _t
    _t = re.sub(r"红线[「『]([^」』]{1,60})[」』]", r"红线，即\1", _t)
    if not _t.startswith(_TOUCH_REDLINE_PREFIX):
        return _t
    _seg = _t[len(_TOUCH_REDLINE_PREFIX):]
    _cut = _seg.find("。")
    if _cut <= 0:
        return _t
    _head, _tail = _seg[:_cut + 1], _seg[_cut + 1:].strip()
    _said = _head.split("，")[0].strip().rstrip("。").strip()
    _name = str(redline_name or "").strip()
    if _name and _said and _said != _name:
        return _t
    # ★ 2026-10-05（用户：「报告永远不能出现待核实」）：原句三处问题 ——
    #   ①「需核实的疑点」把已查明的确定事实说成不确定；
    #   ②「未认定到任何一条构成要件成立」是**内部判定口径**，对企业是噪声；
    #   ③「是否触碰红线须待补充资料与外部数据核验后再判断」把"须补充资料"写成悬而未决。
    #   改为：说清**已查明什么** + **要补什么**（正面表述，不用"待核实"）。
    # ★ 2026-10-05（用户：「报告永远不能出现待核实」）：
    #   原句「本轮对「X」逐条核对，未认定到任何一条构成要件成立；账内检出需进一步核验的
    #   信号，但这只说明本项构成需核实的疑点、不等于已触碰红线，是否触碰红线须待补充资料…」有三处：
    #   ①「需核实的疑点」把已查明的事实说成不确定 ⇒ 去掉；
    #   ②「未认定到任何一条构成要件成立」是**必要的风险提示**（企业须知道这不等于已认定违法，
    #      否则会以为已被查处）⇒ **保留**；
    #   ③ 措辞改为正面表述，不用"待核实/待核验"。
    #   ⚠ 闸门 `check_constituent_traceability` 要求零认定时必须出现
    #      「未认定到任何一条构成要件」与「不等于已触碰红线」两句，删了会被判 ERROR。
    # ★★ 2026-10-07（触发条件与认定要件分离）—— **替换病句**：
    #   原句「本轮对「X」逐条核对，**未认定到任何一条构成要件成立**」与触发条件/认定要件分离冲突：
    #   本项之所以被列示，正是因为**触发条件已命中**（现象已被检出），
    #   写"未认定到任何一条构成要件"就等于否认自己的列示依据（用户 4 条验收明确禁止）。
    #   分层口径（唯一权威 `trigger_conditions`）：疑点成立（触发条件命中）≠ 风险成立（要件组合满足）；
    #   要件级的"共N条已满足M条待核实K条"由紧随其后的要件清单段给出（见 enterprise_report `_head`）。
    _t = ("本轮对「%s」逐条核对：本项**已因触发条件命中而列为疑点**（现象已在账内资料中检出）；"
          "认定要件逐条核对结果见本项要件清单（共几条、已满足几条、待核实几条）。"
          "**疑点成立不等于风险成立**，也不等于已触碰红线、不构成违法认定。"
          "具体认定范围与需补充的资料见本项各段。"
          "%s"
          % (_name or _said or "本项风险指标", _tail))
    # ④-a 段中裁决：按前缀锚点换掉整段裁决（含括号内措辞；上游可能已改写括号内容）
    _i = _t.find(_VERDICT_HIT_ANCHOR)
    if _i >= 0:
        _j = _t.find("）", _i)
        _end = _j + 1 if 0 <= _j <= _i + 40 else _i + len(_VERDICT_HIT_ANCHOR)
        _t = _t[:_i] + _NEUTRAL_HIT_VERDICT + _t[_end:]
    # ④-b 段尾触碰红线断言：整句替换（保留"不认定违法、也不予排除"的承诺）
    _k = _t.find(_TAIL_HIT_ANCHOR)
    if _k >= 0:
        _m = _t.find("。", _k)
        if _m >= 0:
            _t = _t[:_k] + _NEUTRAL_HIT_TAIL + _t[_m + 1:]
    return _t


# 报告用的结论分级
GRADE_CONFIRMED = "已核定"
GRADE_PENDING = "待核"
GRADE_EXCLUDED = "已排除"


# ── 置信度模型权重（2026-09-29 外置可配）──────────────────────────────────────
# 原硬编码于 build_argumentation 内（0.50/0.25/0.10/±0.08/±0.05/−0.20），现统一收敛为
# 单一权威配置，便于回测调参、避免散落多处导致同一模型两套权重。
# 语义（逐项可解释，不靠拍脑袋）：
#   base                —— 触碰红线即有的基础置信（有法定情形需核实）；
#   closure             —— 证据链闭合度每提升 1.0 的加权（材料越齐越可信）；
#   data_completeness   —— 线索链数据完整度每提升 1.0 的加权；
#   high_risk / low_risk—— 风险等级对置信的微调（高则+ / 低则−）；
#   rebuttal_ratio      —— 反证提交比例每提升 1.0 的加权（**为负**：企业提交正当理由
#                          证据越充分，疑点置信越应下调，防误判偏高风险）。
# 设计约束：base + closure(=1) + data(=1) ≈ 1.0（证据与数据全齐时接近满置信），
#          高风险的 +0.08 不应突破 0.95 上界（下方 clamp）。
CONFIDENCE_WEIGHTS: Dict[str, float] = {
    "base": 0.50,
    "closure": 0.25,
    "data_completeness": 0.10,
    "high_risk": 0.08,
    "low_risk": -0.05,
    "rebuttal_ratio": -0.20,
}

# ★★ P1-2（2026-10-09）「可信度必须可复算」——**唯一权威三件套**（公式文本 / 复算 / 百分比）。
#   事故：正文百分比、条目 `confidence` 字段、分项明细 `confidence_breakdown` 三方各说各话。
#   实测真实产物 16 条中 8 条不一致（例：正文 55% 而 `confidence`=0.68）；更严重的是前端
#   「可能性档位」读 `item.confidence`、正文却读自己的加权和 ⇒ 同一条疑点出现**两个档位**
#   （4 条：正文"偏低"、前端"中等"）。根因有三：
#     ① 5%/95% 截断与「触碰红线不低于 60%」两处调整**只改数值、不登记分项** ⇒ Σ分项 ≠ 数值；
#     ② 正文百分比取自**调整前**的值（`_compose_reasoning` 在 60% 地板之前调用）；
#     ③ `redline_engine` 归并时按"取最强"覆盖 `confidence`，而报告渲染的却是 entry 自己的论证
#        ⇒ 字段值与正文取值再次分叉。
#   修法（一次收敛）：分项明细是唯一账本 —— **所有调整都作为显式分项登记**，
#   `confidence = round(Σ分项贡献, 2)`，正文百分比由同一函数算出；`redline_engine`
#   归并时把 `confidence` 与 `confidence_breakdown` **一起**跟着"实际渲染的那份论证"走。
#: 置信度区间下限（原始加权和低于此值按下限计）
_CONF_FLOOR: float = 0.05
#: 置信度区间上限
_CONF_CAP: float = 0.95
#: 触碰红线（且未被反证排除）后的置信度下限
_CONF_HIT_MIN: float = 0.60

#: 可信度公式在正文中的**锚点**（闸门判定"可见域是否披露了同源公式"用；
#: 容忍全/半角等号与标点规范化带来的空格差异）—— 与公式文本同源生成，禁止闸门自写字面量。
CONFIDENCE_FORMULA_ANCHOR = re.compile(r"可信度\s*[=＝]\s*基准分")


def confidence_formula_text() -> str:
    """可信度公式文本 —— **唯一权威**（报告级通用口径与逐项共用，权重取自 CONFIDENCE_WEIGHTS）。

    ★ P1-2：公式措辞此前在 `argumentation` 与 `inspection_overview` **两处各写一份**
    （实测两处还漂移成"证据链闭合度"/"材料齐全程度"不同用词）⇒ 现收敛为一处生成，
    消费方只做转引。新增或调整权重只需改 `CONFIDENCE_WEIGHTS`，公式与分项名自动跟随。
    """
    w = CONFIDENCE_WEIGHTS
    return ("可信度 = 基准分 %.2f + %.2f×证据链闭合度 + %.2f×环节数据完整度 "
            "+ %.2f×（高风险时）/ − %.2f×（低风险时）− %.2f×反证已提交比例，"
            "结果截断在 %d%%~%d%% 之间；各分项为加权和，权重固定、可复算。"
            % (w["base"], w["closure"], w["data_completeness"],
               abs(w["high_risk"]), abs(w["low_risk"]), abs(w["rebuttal_ratio"]),
               int(_CONF_FLOOR * 100), int(_CONF_CAP * 100)))


def confidence_from_breakdown(breakdown: Any) -> Optional[float]:
    """由分项明细**复算**置信度（唯一算法）。

    口径：`confidence = round(Σ分项贡献, 2)`。分项明细里**已含**区间截断
    （`_CONF_FLOOR`/`_CONF_CAP`）与「触碰红线不低于 `_CONF_HIT_MIN`」的**补足项**，
    故"分项之和恒等于最终值"是可用闸门断言的不变量。

    取不到 / 为空 / 分项非法 ⇒ 返回 `None`（＝**不可复算**）——
    调用方**不得**据此输出任何百分比（宁缺勿假）。
    """
    if not isinstance(breakdown, (list, tuple)) or not breakdown:
        return None
    total = 0.0
    seen = 0
    for p in breakdown:
        if not isinstance(p, dict):
            continue
        v = p.get("贡献")
        if v is None:
            continue
        try:
            total += float(v)
            seen += 1
        except (TypeError, ValueError):
            return None
    if not seen:
        return None
    return round(total, 2)


def confidence_percent(confidence: Any) -> Optional[int]:
    """置信度 → 正文百分比整数（**唯一算法**；正文与闸门同源，禁各写一份）。

    取整口径与前端 `Math.round(v*100)` 一致（四舍五入、非 Python 的银行家舍入），
    避免同一条疑点在前端摘要行与正文叙事里差一个百分点。
    """
    try:
        c = float(confidence)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(c) or c < 0:
        return None
    return int(math.floor(c * 100 + 0.5))

# 数据源标识 → 中文名（论证叙述「线索链」用，避免 salaries 等英文标识进入报告正文）
# 与 enterprise_report._SOURCE_LABELS 保持一致；长键在前，避免 inventory 抢先命中 inventory_ledger。
_SOURCE_ZH = [
    ("tax_declarations", "纳税申报表"), ("social_security", "社保明细"),
    ("transport_contracts", "运输合同"), ("inventory_ledger", "进销存台账"),
    ("company_profile", "企业基础信息"), ("target_entity", "目标企业信息"),
    ("fixed_assets", "固定资产台账"), ("trial_balance", "科目余额表"),
    ("declaration", "纳税申报表"), ("salaries", "工资表"),
    ("bank_txs", "银行流水"), ("sal_invs", "销项发票"),
    ("pur_invs", "进项发票"), ("vouchers", "记账凭证"),
    ("inventory", "进销存台账"), ("contracts", "合同台账"),
    ("bom", "物料清单"),
]


def _zh_source(src: Any) -> str:
    """把数据源标识（salaries 或「salaries、social_security」复合串）转为中文。"""
    s = str(src or "")
    if not s:
        return ""
    for en, zh in sorted(_SOURCE_ZH, key=lambda x: -len(x[0])):
        s = s.replace(en, zh)
    return s


def _justifications(finding: Dict, redline: Dict, premise_unverified: str = "") -> List[str]:
    """汇总正当理由（反证）：红线库定义 + 发现自带的合理解释。

    ★★ 2026-10-05（疑点7 D12）：正当理由分两类，**前提依赖性不同**，不可混为一谈：
      ① 红线库 `justifications` —— 「不属于下列正当情形：……」那类出罪清单，
         **以红线名称所断言的前提成立为前提**（亏损前提未认定，"市场培育期"就无从谈起）；
      ② 发现自带的 `reasonable_explanations` / `alternative_explanations` /
         `opposing_evidence` —— 针对**本轮已读到的那个信号**的解释（贡献率低可能是
         优惠/弥补/跨期），与前提无关，前提未认定时依然成立。
    `premise_unverified` 非空（＝前提未认定，唯一权威 `tax_redlines.
    naming_premise_unverified` 给出）时只保留②，避免报告逻辑倒置。
    """
    outs: List[str] = []
    if not premise_unverified:
        for j in (redline.get("justifications") or []):
            s = str(j).strip()
            if s and s not in outs:
                outs.append(s)
    for key in ("reasonable_explanations", "alternative_explanations", "opposing_evidence"):
        vals = finding.get(key) or []
        if isinstance(vals, dict):
            vals = list(vals.values())
        for v in vals:
            if isinstance(v, dict):
                s = str(v.get("text") or v.get("explanation") or v.get("name") or "").strip()
            else:
                s = str(v).strip()
            if s and s not in outs:
                outs.append(s)
    return outs


def _grounds(finding: Dict, clue: Dict, evidence: Dict) -> List[str]:
    """论据：支撑主张的具体事实"""
    grounds: List[str] = []
    if clue.get("terminal_signal"):
        grounds.append(f"线索链终端信号：{clue['terminal_signal']}")
    for n in (clue.get("nodes") or []):
        if n.get("has_data") and n.get("observed") and n.get("step", 0) >= 2:
            g = f"第{n['step']}环：{n.get('action','')}——{n.get('observed','')}"
            if g not in grounds:
                grounds.append(g)
    for e in (evidence.get("elements") or []):
        if e.get("status") == "已有":
            grounds.append(f"{e['role']}「{e['name']}」已在案（{e['purpose']}）")
    return grounds[:6]


# ★ 2026-10-02：外部数据核验待办的识别口径（**单一权威**，pipeline/报告层复用）。
#   判据只取发现自身声明的语义类别（`external_check_reminder` 唯一出处），
#   不猜关键词、不看红线归属 —— 避免同一件事在两处被判成两种性质。
_EXTERNAL_CATEGORY = "外部核验"
# ★★ 2026-10-04（疑点10-21 合并批次）：**"外部核验类"的两个真实前缀**，权威里只登记了一个。
#   事故：外部核验判据说自己是唯一权威（"结论取决于外部数据"），可实际产出的一类清单项
#   前缀是「待核事实：」而**不在**本名单里 ⇒ `is_external_check_finding` 恒为 False ⇒
#   这些待办项被当成普通触碰红线发现：一边「已触碰税务违规红线」，一边「涉及第 无 条构成要件」
#   （自相矛盾，疑点9 的同名症状），并拿到一份它根本用不上的税法条款。
#   修法：把真实产出里通行的前缀一并登记（新增同类只加一行，不再另写判断分支）。
_EXTERNAL_TYPE_PREFIXES: Tuple[str, ...] = (
    "需外部数据核验：",
    "待核事实：",      # 外部数据尚需核实的账内信号（真实产出里数量最多的一类）
)
_EXTERNAL_TYPE_PREFIX = _EXTERNAL_TYPE_PREFIXES[0]  # 兼容旧调用/旧外部引用


def is_external_check_finding(finding: Dict) -> bool:
    """该发现是否属「需外部数据核验」待办项（账内有信号、结论文案取决于外部数据）。"""
    if not isinstance(finding, Dict):
        return False
    if str(finding.get("category") or "").strip() == _EXTERNAL_CATEGORY:
        return True
    return str(finding.get("type") or "").strip().startswith(_EXTERNAL_TYPE_PREFIXES)


def build_argumentation(finding: Dict, redline: Dict, clue: Dict,
                        evidence: Dict, engine_data: Optional[Dict] = None) -> Dict:
    """
    构建单条疑点的论证链。

    返回：
        {
          "claim": "主张：...",
          "legal_basis": [...],
          "grounds": [...],           # 论据
          "rebuttals": [...],         # 反证（正当理由）
          "rebuttal_tests": [...],    # 每项反证成立所需的证据与当前能否验证
          "verdict": "红线成立（证据闭合）/...",
          "confidence": 0~1,
          "reasoning": "论证过程叙述（大白话）",
          "next_actions": [...]       # 下一步要做什么
        }
    """
    engine_data = engine_data or {}
    # ★ 2026-10-02（用户复核疑点5）：外部核验待办项**不得用触碰红线口径开场**。
    #   它的结论取决于本系统拿不到的外部数据，自身已声明不作定性；
    #   若仍套「触碰红线，涉嫌……」，就会和同项「涉及第 无 条构成要件」正面冲突。
    _external = is_external_check_finding(finding)
    _suspect = str(redline.get('suspect') or '税务风险')
    # suspect 已含「涉嫌」字样，不得重复叠加
    _suspect_txt = _suspect if _suspect.startswith("涉嫌") else f"涉嫌{_suspect}"
    # ★ 2026-09-25：claim 文本**不带红线编号** —— 编号是内部追溯标识，已在条目
    #   `redline_id` 字段中透传；写进面向读者的表述里，一旦某条渲染路径没过净化闸门
    #   就会泄漏给企业（实测内部树里 16 处 claim 仍带 RL-XXX）。
    if _external:
        # 主张只报「账内信号 + 结论待外部核验」，不报触碰红线、不报红线 suspect 罪名
        _sig = str(finding.get("detail") or finding.get("how_found") or "").strip()
        _sig = _sig.rstrip("。；；,，").strip()
        claim = (f"本项在账内检出信号——{_sig or '与该项风险指标对应的账内线索'}，"
                 f"但能否成立取决于工商、税务、海关、银行等外部数据的核验结果，"
                 f"现有资料不足以作出定性认定")
    else:
        # ⚠ 必须引用**同一常量**：旧实现这里硬编码"本企业触碰红线"，与
        #   `_TOUCH_REDLINE_PREFIX` 两处措辞各写一份 ⇒ 改一处必漏一处（本轮实测）。
        claim = (f"{_TOUCH_REDLINE_PREFIX}「{redline.get('name','')}」，{_suspect_txt}")
    grounds = _grounds(finding, clue, evidence)
    # ★★ 2026-10-05（疑点7 D12 逻辑倒置）：**红线名称所断言的前提本轮未认定时，
    #   不得把"以该前提成立为前提的正当情形"当作本项的解除理由。**
    #   事故（RL-CIT-004，公司1 真实产物）：标题与结论段已声明
    #   「未就本风险指标名称中的『亏损』前提本身作出认定」（净利润实测为正），
    #   同一页 §四 却写「企业如果认为这不成立，通常可以说明：市场培育期、前期投入大；
    #   行业周期性低谷；新业务板块拖累」—— 这三条正当情形全部以"企业确实在亏损"为
    #   前提，前提未认定就拿来解释，读者会以为系统已认定其亏损。
    #   判据走**唯一权威** `tax_redlines.naming_premise_unverified`（与报告标题裁剪
    #   `trim_redline_title` 同源，禁止两处各判一次）；数据驱动，新增同类红线只加一行。
    _premise: str = ""
    try:
        from engine.tax_redlines import naming_premise_unverified as _npu
        _premise = str(_npu(str(redline.get("id") or ""), finding.get("constituent_hits") or []) or "")
    except Exception:  # noqa: BLE001 —— 取不到前提信息时按"未认定"处理会误伤，故按已认定放行存量行为
        _premise = ""
    rebuttals = _justifications(finding, redline, premise_unverified=_premise)

    closure = float(evidence.get("closure") or 0.0)
    nodes = clue.get("nodes") or []
    data_completeness = (
        sum(1 for n in nodes if n.get("has_data")) / len(nodes) if nodes else 0.0
    )
    level = str(finding.get("level") or "")

    # 反证可验证性：反证所需证据是否已提供
    rebuttal_elements = [e for e in (evidence.get("elements") or []) if e.get("role") == "反证"]
    rebuttal_supported = sum(1 for e in rebuttal_elements if e.get("status") == "已提交")
    rebuttal_ratio = (rebuttal_supported / len(rebuttal_elements)) if rebuttal_elements else 0.0

    # 置信度模型（不靠拍脑袋，逐项可解释；权重外置，见 CONFIDENCE_WEIGHTS 可配）
    # ★★ P1-2（可复算）：**分项明细是唯一账本** —— 一切调整（区间截断、触碰红线补足）
    #   都必须落成一条显式分项，使 `round(Σ贡献, 2)` 恒等于最终 `confidence`。
    w = CONFIDENCE_WEIGHTS
    _conf_parts: List[Dict[str, Any]] = [{"项": "基准分", "权重": w["base"], "取值": 1.0,
                                          "贡献": round(w["base"], 4)}]
    _conf_parts.append({"项": "证据链闭合度", "权重": w["closure"], "取值": round(closure, 4),
                        "贡献": round(w["closure"] * closure, 4)})
    _conf_parts.append({"项": "环节数据完整度", "权重": w["data_completeness"],
                        "取值": round(data_completeness, 4),
                        "贡献": round(w["data_completeness"] * data_completeness, 4)})
    if "高风险" in level:
        _conf_parts.append({"项": "风险等级为高", "权重": w["high_risk"], "取值": 1.0,
                            "贡献": round(w["high_risk"], 4)})
    elif "低风险" in level:
        _conf_parts.append({"项": "风险等级为低", "权重": w["low_risk"], "取值": 1.0,
                            "贡献": round(w["low_risk"], 4)})
    _conf_parts.append({"项": "反证已提交比例（反向计分）", "权重": w["rebuttal_ratio"],
                        "取值": round(rebuttal_ratio, 4),
                        "贡献": round(w["rebuttal_ratio"] * rebuttal_ratio, 4)})
    # 区间截断：**显式登记为一条分项**（旧实现直接 clamp 数值、不登记 ⇒ 分项之和与最终值脱钩）
    _raw = sum(float(p["贡献"]) for p in _conf_parts)
    if _raw < _CONF_FLOOR or _raw > _CONF_CAP:
        _tgt = _CONF_FLOOR if _raw < _CONF_FLOOR else _CONF_CAP
        _conf_parts.append({
            "项": "置信截断（限 %d%%~%d%%）" % (int(_CONF_FLOOR * 100), int(_CONF_CAP * 100)),
            "权重": None, "取值": 1.0, "贡献": round(_tgt - _raw, 4),
            "说明": "原始加权和超出区间，按区间端点计入",
        })

    # ── 第一层：是否触碰红线（客观判断） ──
    # 方法论铁律：一旦符合某项风险情形即触碰税务红线，触碰红线与否**只取决于
    # 线索链是否给出可量化的触碰红线事实**，与证据链闭合度无关——闭合度决定
    # 的是「能否定性」，不是「是否触碰红线」。用闭合度卡触碰红线会让真实疑点被吞掉。
    has_signal = bool(clue.get("terminal_signal"))
    # ★ 2026-10-02：外部核验待办项**有信号也不判触碰红线** ——
    #   触碰红线必须是「逐条要件已可核对到法定情形」；外部数据缺失时要件无从核对，
    #   把它算触碰红线会让同一疑点出现「已触碰税务违规红线」+「涉及第 无 条构成要件」的
    #   自相矛盾。它走独立的 `_VERDICT_EXTERNAL` 档。
    redline_hit = has_signal and not _external

    # ── 第二层：能否定性（取决于证据链闭合度与反证） ──
    if _external:
        # 外部核验待办：账内有信号、结论待外部数据 —— 既非已定性，也非触碰红线待补证
        # （此时 redline_hit 已由上一行置 False，故不会落进下面的触碰红线分支）
        verdict, grade = _VERDICT_EXTERNAL, GRADE_PENDING
    elif redline_hit and rebuttal_ratio >= 0.5 and closure < 0.60:
        verdict, grade = _VERDICT_EXCLUDED, GRADE_EXCLUDED
    elif redline_hit and closure >= 0.80 and not evidence.get("direct_missing"):
        verdict, grade = _VERDICT_CONFIRMED, GRADE_CONFIRMED
    elif redline_hit:
        verdict, grade = _VERDICT_HIT_PENDING, GRADE_PENDING
    else:
        verdict, grade = _VERDICT_WEAK, GRADE_PENDING

    # 勾稽异常类红线（借贷不平 / 余额滚动关系断裂等）：仅揭示数据勾稽断裂，
    # 本身不足以证明隐瞒收入或账外资金循环，须有正面隐瞒 / 账外证据方可定性。
    # 证据链齐全只说明异常「可读出」，不说明「已定性」；故即使闭合度达标也不自动确认
    # （遵守铁律：发现不等于确认，证据不足一律转置疑清单）。
    if redline.get("disposition") == "reconciliation_anomaly" and verdict == _VERDICT_CONFIRMED:
        verdict, grade = _VERDICT_HIT_PENDING, GRADE_PENDING

    # ★★ 触碰红线后置信度下限 60%：既然符合构成要件，就不能因证据未齐而说成「没把握」。
    #   但被有效反证排除（rebuttal_ratio≥0.5 且闭合度不足 → 已判 EXCLUDED）的红线，
    #   其低置信是"正当理由成立"的真实反映，不得被地板顶回 60%，否则反证机制被掩盖。
    #   ★ P1-2：这条下限**同样登记为一条显式分项**（旧实现只改数值不登记 ⇒ Σ分项 ≠ 最终值）；
    #     且必须在 `_compose_reasoning` **之前**执行 —— 否则正文百分比取自地板之前的值，
    #     与条目 `confidence`/分项之和三方分叉（实测正是该症状）。
    if redline_hit and verdict != _VERDICT_EXCLUDED:
        _cur = round(sum(float(p["贡献"]) for p in _conf_parts), 4)
        if _cur < _CONF_HIT_MIN:
            _conf_parts.append({
                "项": "触碰红线最低置信补足（不低于 %d%%）" % int(_CONF_HIT_MIN * 100),
                "权重": None, "取值": 1.0, "贡献": round(_CONF_HIT_MIN - _cur, 4),
                "说明": "既已符合构成要件，不因证据未齐而下调至该下限以下",
            })

    # 置信度**由分项明细导出**（唯一算法）—— 保证 `confidence == round(Σ贡献, 2)`，可复算。
    confidence = confidence_from_breakdown(_conf_parts)
    if confidence is None:              # 理论上不会发生；一旦发生不得静默给数（百分比将不写）
        confidence = 0.0

    # 反证成立条件检验
    rebuttal_tests = []
    for r in rebuttals[:5]:
        rebuttal_tests.append({
            "rebuttal": r,
            "needs": "须提供与该理由对应的书面协议、原始单据与履行记录",
            "verifiable_now": "本轮资料能够验证" if rebuttal_supported else "本轮资料无法验证，须补充资料",
        })

    reasoning = _compose_reasoning(redline, claim, clue, evidence, rebuttals, verdict,
                                   confidence, _conf_parts)

    # ★★ 2026-10-04（用户复核疑点6 D11/D13）——**"要求企业补充"的资料名必须是"具体材料名"，
    #   绝不能是"资料类别名"**。根因与修法：
    #   ① 旧实现从 `evidence.missing_materials` 生成 `补充提供「{类别名}」`。
    #      `missing_materials` 是**15 类类别名**（`material_names.CATEGORY_KEYWORDS`），
    #      而类别名与"企业该交的那份材料"**不是一回事**：实测疑点6 因此出现
    #      「补充提供**合同文件**」——而本项真正缺的是「**劳动合同与用工名册**」
    #      （"劳动合同"按关键词归入"合同文件"类别）⇒ 读者以为要交易合同（幽灵名，第 5 次）。
    #   ② 旧实现另有一段"按发现文本关键词**新增**补充要求"（`_mat_hits`）：
    #      注释写的是"前置（去重，**不删既有需求**）"，代码却 `_pre + next_actions` **凭空新增**——
    #      实测多出「补充提供**社保明细**」（同疑点要件①⑤ 已判**已有**）与
    #      「补充提供**记账凭证**」（本项任何要件的数据源都没有它）。**实现与意图不符。**
    #   修法（一次收敛，两端都用**证据角色名**这一唯一权威）：
    #      · "补充提供"只列**本轮未取得的、非反证的证据角色名**（＝企业真正要交的那份材料），
    #        不再列类别名、不再按发现文本关键词凭空新增；
    #      · "文本命中前置"改由 `_na_rel_rank` 排序实现（原文意图），不新增任何需求。
    next_actions: List[str] = []
    _pending_names: List[str] = []
    for _e in (evidence.get("elements") or []):
        if not isinstance(_e, dict):
            continue
        if _e.get("role") == "反证" or _e.get("status") in ("已有", "待核"):
            continue          # 反证另述；「待核」走下面的"确认"分支（已有相关资料，不是缺）
        _nm = str(_e.get("name") or "").strip()
        if _nm and _nm not in _pending_names:
            _pending_names.append(_nm)
    for m in _pending_names[:5]:
        next_actions.append(f"补充提供「{m}」")
    # ★ 2026-09-25：「待核」项不是"缺材料"，而是"已有相关资料但未必含本项所需"，
    #   动作应为"确认"而非"补充提供" —— 否则报告会让企业去补一份其实已经交了的资料。
    for m in (evidence.get("verify_materials") or [])[:5]:
        next_actions.append(f"确认已提供的「{m}」中是否包含本项所需内容")
    for e in (evidence.get("direct_missing") or [])[:3]:
        if e and str(e) not in _pending_names:      # 已被"补充提供"覆盖的不重复
            next_actions.append(f"取得直接证据：{e}")
    if rebuttals:
        # ★ 2026-10-05（疑点7 D12）：`rebuttals` 已按前提是否认定过滤（见 `_justifications`）——
        #   前提未认定时只剩"针对已读到信号"的解释，这句话仍然成立，无需另改文案。
        next_actions.append("由企业对上述正当理由逐项提交书面证明与原始单据")
    elif _premise:
        # 前提未认定且无任何可用的解释性材料 → 要求企业先**核实前提**，
        # 而不是先替一个尚未认定的前提作解释（与 §四 同一口径，不两处各判一次）。
        next_actions.append(f"先核实「{_premise}」这一前提是否成立（以申报与账面数据为准）")
    steps = finding.get("investigation_steps") or []
    for s in steps[:3]:
        if isinstance(s, dict):
            s = str(s.get("step") or s.get("action") or s)
        s = str(s).strip()
        if s and s not in next_actions:
            next_actions.append(s)

    # ★ 2026-09-27（P3）：next_actions 相关性排序键（资料名出现在本项文本里 → 0，排前）
    #   —— "把本项文本真正提到的资料**前置**"这一原意，**由排序实现、不新增需求**。
    _ftext = " ".join(str(finding.get(k) or "") for k in ("type", "detail", "description", "title"))

    def _na_rel_rank(a):
        t = str(a)
        for _p in ("补充提供「", "确认已提供的「", "取得直接证据："):
            t = t.replace(_p, "")
        t = t.split("」")[0].split("：")[-1].strip()
        return 0 if (t and t in _ftext) else 1

    return {
        "claim": claim,
        "redline_id": redline.get("id", ""),
        "redline_name": redline.get("name", ""),
        "suspect": redline.get("suspect", ""),
        "legal_basis": list(redline.get("legal_basis") or []),
        "constituents": list(redline.get("constituents") or []),
        # ★ 2026-09-27：本企业**实际涉及**的构成要件（由域逐条判定后带出；只列命中的）。
        #   企业报告「一、涉及的风险事项」优先采用它（不再罗列通用要件清单）。
        "constituent_hits": list(finding.get("constituent_hits") or []),
        "grounds": grounds,
        "rebuttals": rebuttals,
        "rebuttal_tests": rebuttal_tests,
        "verdict": verdict,
        "conclusion_grade": grade,
        "redline_hit": redline_hit,
        "confidence": confidence,
        # ★ 2026-09-29（点评整改 P1-9）：可信度的**分项计算依据**（可逐项复算）。
        #   外部点评指出「判断可信度约75%（较高）」类表述无任何计算公式披露，
        #   读者无法判断这个数是怎么来的 → 现随结论一并输出各分项权重与取值。
        "confidence_breakdown": _conf_parts,
        # ★ P1-2：公式文本**唯一权威** `confidence_formula_text()`（权重表生成），
        #   本处与报告级「报告性质和使用说明」、总述「关键口径对照」三处共用同一份。
        "confidence_formula": confidence_formula_text(),
        "closure": closure,
        "reasoning": reasoning,
        "next_actions": sorted(next_actions, key=_na_rel_rank)[:8],
        "remedy": evidence.get("remedy", ""),
    }


def _compose_reasoning(redline: Dict, claim: str, clue: Dict, evidence: Dict,
                       rebuttals: List[str], verdict: str, confidence: float,
                       conf_parts: Optional[List[Dict[str, Any]]] = None) -> str:
    """把论证过程写成一段自然叙述（检查人员口吻，不出现字段标记与编号）。

    报告是给人看的文书，不保留【主张】【依据】这类内部字段标记，
    也不出现 RL-XXX 这样的红线编号（编号只在系统内部用于追溯）。
    叙述按「查到了什么 → 凭什么这样判断 → 现在能定到什么程度 → 企业可以怎么解释」
    的自然逻辑展开。
    """
    parts = []
    # 去掉 claim 里的红线编号（「本企业触碰红线 RL-PAY-001「名称」，涉嫌…」→ 自然表述）
    claim_text = re.sub(r"红线\s*RL-[A-Z]+-\d+\s*", "红线", claim or "")
    claim_text = re.sub(r"RL-[A-Z]+-\d+\s*", "", claim_text).strip()
    parts.append(f"{claim_text}。")
    # ★ 2026-09-25：构成要件是**待核对的判断标准**，不是已成立的事实。
    #   旧文案写"这样判断的依据是：…"，读起来像这些要件已经成立 ——
    #   用户无法分辨哪些是"标准"、哪些是"本轮核对到的事实"。
    constituents = redline.get("constituents") or []
    if constituents:
        parts.append(f"判断本项是否成立，要看这几项标准是否同时满足：{_join(constituents, '；')}。")
    if clue.get("terminal_signal"):
        parts.append(f"本轮从所报资料中直接核对到的事实是：{clue.get('terminal_signal')}。")

    # ★ 2026-09-25 根因修复：资料归属必须按**实际取得情况**陈述。
    #   旧文案把红线模板声明的"应查资料路径"当成"已核对路径"，写出
    #   "这些事实是从固定资产明细账、试生产记录、折旧计算表、设备产能这几类资料里
    #     逐层核对出来的" —— 而该企业这几类资料**一份都没提交**（证据表里全是缺失）。
    #   现改为：只说本轮**实际读取到**的资料（可核验），并把未取得数据的环节显式点出。
    real_sources = [_zh_source(s) for s in (clue.get("sources_used") or []) if s]
    if real_sources:
        parts.append("本轮实际读取到的资料是：" + "、".join(real_sources[:6]) + "。")
    nodes = clue.get("nodes") or []
    gap_nodes = [n for n in nodes if not n.get("has_data")]
    if gap_nodes:
        parts.append(
            "本项核查共%d环，其中" % len(nodes)
            + "、".join("第%s环" % n.get("step") for n in gap_nodes)
            + "因本轮未取得该环节所需资料，未取得数据（各环实际读到的数据见上一段明细表）。"
        )
    elif nodes:
        # ★ 不写"全部取得数据"：各环有数据只代表该环节取得了可量化数据，
        #   不代表"该环对应资料已提供/已读取"（环的对应资料是检查路径上的应查项）。
        #   可证的表述是"各环数据见明细表"，读什么、读到什么由表逐环列示。
        parts.append("本项核查共%d环，各环实际读到的数据见上一段明细表。" % len(nodes))
    _v = evidence.get('verdict', '')
    # ★ 2026-09-27（用户要求通俗化）：材料齐全程度用项数，并补列「还缺的具体材料名」，
    #   让非财税背景的负责人知道缺的是哪几样（仅列前 6 样，避免过长）。
    # ★ 2026-10-04（疑点5 D11 收口）：**§四 与 §三 同一套缺料口径**。
    #   实测：§三「需要5项＝逐字2＋同类3」自洽；§四 却写「逐字1＋同类1」⇒ 同页两套口径。
    #   根因：这里用引擎三态计数（**元素数**），§三 用**材料名原子数**（拆复合名、去重）
    #   ＋业态剔除后的权威字段 ⇒ 必然对不上。权威字段缺失时**回落**到原计数（存量行为不变）。
    _SEPS11 = ("、", "，", ",", "；", ";", "／", "/", "或者", "以及", "与", "和", "及", "或")

    def _atoms11(_names):
        _o = []
        for _x in (_names or []):
            _n = _x.get("name") if isinstance(_x, dict) else _x
            _s = str(_n or "")
            for _p in _SEPS11:
                _s = _s.replace(_p, "\x00")
            for _y in _s.split("\x00"):
                _y = _y.strip()
                if _y and _y not in _o:
                    _o.append(_y)
        return _o

    _els11 = evidence.get('elements') or []
    _mn11 = list(evidence.get('missing_material_names') or [])
    if _els11:
        _av = len(_atoms11([e for e in _els11 if e.get('status') == '已有']))
        _vf = len(_atoms11([e for e in _els11 if str(e.get('status') or '') in ('待核', '待核验')]))
        if _mn11:
            _mc = len(_atoms11(_mn11))
        else:
            _mc = int(evidence.get('missing_atom_count') if evidence.get('missing_atom_count') is not None else evidence.get('missing_count', 0) or 0)  # ★D11 原子数权威（单行·全量）
    else:
        _av = int(evidence.get('available_atom_count') if evidence.get('available_atom_count') is not None else evidence.get('available_count', 0) or 0)  # ★D11 原子数权威（单行·全量）
        _vf = int(evidence.get('verify_atom_count') if evidence.get('verify_atom_count') is not None else evidence.get('verify_count', 0) or 0)  # ★D11 原子数权威（单行·全量）
        _mc = int(evidence.get('missing_atom_count') if evidence.get('missing_atom_count') is not None else evidence.get('missing_count', 0) or 0)  # ★D11 原子数权威（单行·全量）
    _mm = evidence.get('missing_materials') or []

    # ★★ 2026-10-03（用户复核疑点11："本项检查需要4项材料，目前还没有一项材料与要求逐字对应"，
    #   而同一页正文正在引用序时账/销项发票/银行流水的数字 —— 读者会以为企业什么都没交）：
    #   "已提供0项"这一句只统计**名称逐字对应**的材料，**不含"已提供同类资料、须确认范围"那一类**。
    #   三态必须各说各话：逐字对应 N 项 / 同类待确认 M 项 / 确未提供 K 项，
    #   不得用"已提供0项"把"待核"一起吞成"没有"。
    _vf = int(evidence.get('verify_atom_count') if evidence.get('verify_atom_count') is not None else evidence.get('verify_count', 0) or 0)  # ★D11 原子数权威（单行·全量）
    _mat_txt = f"就资料来说，{_v}（名称逐字对应已提供{_av}项"
    if _vf:
        _mat_txt += f"；另有{_vf}项已提供同类资料、范围须人工确认"
    _mn = evidence.get('missing_material_names') or []
    if _mm:
        # ★★ 2026-10-05（疑点7 D10，幽灵资料名）**具体材料名必须是主位，类别名只作括注**。
        #   事故：正文写「尚缺：资产负债表、利润表」—— 这两个是 **15 类类别名**，
        #   而同一页 §三 证据角色表与 §五 待办写的是「历年财务报表与审计报告」
        #   「亏损原因说明与经营计划」⇒ 同一页两份清单对不上，且"资产负债表"这个
        #   类别名并不是企业该交的那份材料（读者不知交什么文件）。
        #   旧实现只在 `_mm and _mn` 同时非空时才补具体名，_mn 为空就只剩类别名 ⇒ 退化成幽灵名。
        #   现规则：**有具体名就以它为主**（类别名放括注，帮助读者理解属于哪一类）；
        #   只有在**一个具体名都拿不到**时，才允许退化为类别名（并明说这是类别口径）。
        if _mn:
            _mat_txt += "；尚缺：" + "、".join(str(m) for m in _mn[:6]) + (
                ("（属" + "、".join(str(m) for m in _mm[:3]) + "类）") if _mm else "")
        else:
            _mat_txt += ("；尚缺（按资料类别列示，本项未取到具体材料名）："
                         + "、".join(str(m) for m in _mm[:6]))
    elif _mn:
        # ★ 2026-10-04（疑点3 D13）：与 §三 **同一计数单位**（材料名，复合名拆开去重）。
        #   旧实现用 `missing_count`（**证据元素个数**）⇒ 同一页 §三 4 项 / §四 3 项。
        import re as _r9
        _at = []
        for _x9 in _mn:
            for _y9 in _r9.split(r"[、，,；;／/]|与|和|及|以及|或", str(_x9)):
                _y9 = _y9.strip()
                if _y9 and _y9 not in _at:
                    _at.append(_y9)
        if _at:
            _mat_txt += "；还缺%d项（%s）" % (len(_at), "、".join(_at[:6]))
        else:
            _mat_txt += f"；还缺{_mc}项"
    elif not _vf:
        _mat_txt += "，所需资料已齐备"
    # ★ 2026-10-02：**括号必须闭合**。旧版只写了左括号「（已提供N项…」，
    #   却从未补右括号 —— 正文出现「…现有资料不足以排除本项涉嫌风险。」后面永远缺一个「）」，
    #   靠人眼几乎发现不了，但读者一眼能看出句子没说完（实测公司1 疑点5 四、段）。
    #   同时把 rebuttal_status 自带的句号剥掉，避免「…风险。）。」这种双句号。
    _rb = str(evidence.get('rebuttal_status') or '').strip().rstrip('。；; ')
    _mat_txt += (f"；{_rb}" if _rb else "") + "）。"
    parts.append(_mat_txt)
    if rebuttals:
        parts.append(
            f"企业如果认为这不成立，通常可以说明：{_join(rebuttals[:3], '；')}。"
            "但这些说明能不能采信，要看有没有书面协议和原始单据，口头解释不能作为认定依据。"
        )
    if verdict == _VERDICT_CONFIRMED:
        tail = "支撑材料已经齐全，这一项可以直接认定；企业如有异议，需要更正所报资料本身或者提出相反证据。"
    elif verdict == _VERDICT_HIT_PENDING:
        if redline.get("disposition") == "reconciliation_anomaly":
            tail = ("该项属于数据勾稽异常（借贷不平或余额滚动关系断裂），本身不足以认定违法；"
                    "需企业说明原因（如红字冲销、补记凭证、在途未达账项等），"
                    "无法合理解释且存在账外资金或隐瞒收入线索的，转进一步核查。")
        else:
            # ★ 2026-10-02：抽成模块常量（`_TAIL_HIT_PENDING`）——报告输出闸门
            #   `enterprise_report.sanitize_conclusion_assertion` 要按「是否认定到构成要件」
            #   把它整句**中性化**，锚点必须取自同一权威，不能在两处各写一份措辞。
            tail = _TAIL_HIT_PENDING
    elif verdict == _VERDICT_EXTERNAL:
        tail = ("这一项不属于本轮能自行定论的事项：账内信号已经读到，但认定所需的信息在"
                "税务端与跨部门数据池（工商登记、开票环境、参保与注销、报关收汇、账户实名等），"
                "单账套拿不到，须由主管机关调取或企业补充外部资料后再判断；"
                "本轮既不认定违法，也不予排除。")
    elif verdict == _VERDICT_EXCLUDED:
        tail = "企业给出的解释合理且有证据支撑，这一项予以排除。"
    else:
        tail = "现有资料还不足以形成税务疑点，本轮只作观察记录，等资料补充后再判断。"
    # ★ 2026-09-27（用户要求通俗化）："把握程度"改为"判断可信度"并附通俗档位
    #   （很高/较高/中等/偏低/低），让老板一眼知道我们分析有多有把握。
    # ★★ P1-2（可信度必须可复算）：**百分比只在能从同源分项明细复算出来时才写**。
    #   判据：`confidence_from_breakdown(分项) == round(confidence, 2)` 且百分比可由同一函数算出。
    #   算不出（无分项依据 / 分项与最终值不一致）⇒ 整句只留结论，**宁缺勿假**，
    #   绝不"静默给一个数"。闸门 `quality_gates` D11 对同一判据做端到端断言。
    _recomputed = confidence_from_breakdown(conf_parts) if conf_parts is not None else None
    _pct = confidence_percent(confidence)
    if _recomputed is None or _pct is None or _recomputed != round(float(confidence), 2):
        _conf_txt = ""
    else:
        _band = _conf_band(confidence)
        _conf_txt = f"，判断可信度约{_pct}%（{_band}）" if _band else f"，判断可信度约{_pct}%"
    parts.append(f"综合以上，本项结论是{verdict}{_conf_txt}。{tail}")
    return "".join(parts)


def _join(items: List[Any], sep: str) -> str:
    return sep.join(str(i).strip() for i in items if str(i).strip())


def _conf_band(confidence: Any) -> str:
    """把 0~1 的可信度映射为通俗档位（供报告正文展示，便于非财税背景负责人理解）。"""
    try:
        c = float(confidence)
    except (TypeError, ValueError):
        return ""
    if c >= 0.85:
        return "很高"
    if c >= 0.70:
        return "较高"
    if c >= 0.55:
        return "中等"
    if c >= 0.40:
        return "偏低"
    return "低"
