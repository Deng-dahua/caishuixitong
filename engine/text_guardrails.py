# -*- coding: utf-8 -*-
"""风险检查输出门禁（文本净化 / 不自动定性；原 methodology_guardrails 重命名）。

统一把规则、模型和链路输出限制在“筛查—调查—证据复核—人工审理”边界内。
该模块不删除原始资料，也不判断最终法律责任。
"""

from __future__ import annotations

import re
from typing import List


_DIRECT_REPLACEMENTS = (
    # ★ 2026-09-27：**去掉冗余的"（待核实）"**——"涉嫌/待核"已含此意，叠加即累赘
    #   （用户 2026-09-27：第三/第四点）。此为兜底，源头模板已同步改。
    ("（尚需核实）", ""),
    # ★ 2026-09-27：**系统自述 → 检查人员口径**（长句优先，故置于表首）。
    #   报告是给企业的对外文书，只写"本轮核查到什么 / 需企业说明什么"，
    #   不写"系统做了什么、系统不能做什么"（用户 2026-09-27 实测：
    #   "系统通过结构化读取逐份解析""系统不能下户盘货"这类不该出现）。
    #   ⚠ 只替换**具体句式**，绝不替换裸"系统"（"收银系统/财税风险防控系统/税控系统"是正当用法）。
    ("系统不能下户盘货、不能查金税四期、不能穿透资金最终去向",
     "本报告为案头核查，不含下户盘点、金税四期内部数据核验与资金最终去向穿透"),
    ("系统已识别到文件并进行了分析尝试，但无法提取有效数据",
     "已识别到该文件并尝试解析，但未能提取有效数据"),
    ("系统通过结构化读取逐份解析，读取结果为", "以上资料经逐份读取解析，"),
    ("系统通过多域交叉分析自动发现", "经多域交叉分析发现"),
    ("系统能做的交叉验证越多", "可做的交叉验证越多"),
    ("系统按已上传资料分析", "本报告按已上传资料分析"),
    ("系统按行业承载密度测算", "本轮按行业承载密度测算"),
    ("系统结论均为待证线索", "本报告结论均为待证线索"),
    ("系统仅提供询问清单", "本清单仅提供询问事项"),
    ("系统仅给出待核特征组合", "此处仅给出待核特征组合"),
    ("系统仅提供待核线索", "此处仅提供待核线索"),
    ("本结论仅反映系统识别能力", "本结论仅反映解析能力"),
    ("系统无法解析当前文件格式", "无法解析当前文件格式"),
    ("系统局限→企业自证：", "案头核查局限→企业自证："),
    ("系统已识别资金回流结构", "本轮已识别资金回流结构"),
    ("把系统识别的", "把本轮识别的"),
    ("属系统能力边界内的待补强项", "属本轮案头核查能力边界内的待补强项"),
    ("系统能力存在边界", "本轮案头核查能力存在边界"),
    ("系统已量化", "本轮已量化"),
    ("系统已组合", "本轮已组合"),
    ("系统已加载", "本轮已加载"),
    ("系统已内置", "本报告已内置"),
    # ★ 2026-09-25：**系统内部推理过程自述**的自然化（长句优先，故置于表首）。
    #   报告是给企业的对外文书，只写"需企业说明什么 / 本轮核对到什么"，
    #   不写"系统用了什么方法、怎么竞争的、怎么裁决的"。
    #   实测漏网句（`all_findings[].limitations / cleared_reason / adjudication`，
    #   这三字段原先不在 review_finding 的字段清单里，绕过了文字门禁）：
    #     「竞争假设裁决：个人采购金额8.68元…，正常经营假设胜出；」
    #     「销售侧须先作经营模式裁决：…」
    #     「正常经营假设胜出（经竞争假设裁决后排除）」
    ("正常经营假设胜出（经竞争假设裁决后排除）", "经核对两种可能后，采信正常经营解释，不作为风险事项"),
    ("经竞争假设裁决后排除", "经核对两种可能后排除"),
    ("竞争假设裁决：", "经核对两种可能："),
    ("竞争假设裁决", "两种可能的核对"),
    ("竞争假设", "可能解释"),
    ("经营模式裁决", "经营模式认定"),
    ("正常经营假设胜出", "采信正常经营解释"),
    ("假设胜出", "该解释被采信"),
    # ★ 2026-09-25：**内部术语 → 业务语言** 的映射收敛到本表（唯一出处）。
    #   原先它们只写在 `enterprise_report._naturalize_report_text` 里，而该函数
    #   只在报告闸门与少数调用点执行 → **findings（走 review_finding）不受约束**：
    #   实测 `all_findings[].type` 带着「主营业务成本资金与负债**证据链**核验」进前端。
    #   顺序要紧：**先长后短**（「证据链未闭合」必须先于「证据链」）。
    ("证据链未闭合", "支撑材料不足"),
    ("证据链闭合度", "材料齐全程度"),
    ("证据链基本闭合", "支撑材料已基本齐全"),
    ("证据链部分闭合", "支撑材料尚不齐全"),
    ("证据链", "支撑材料"),
    ("线索链终端信号", "资料中直接读到的事实"),
    ("线索链", "发现过程"),
    ("闭合度", "齐全程度"),
    ("论证过程与裁决", "结论及理由"),
    ("论证与裁决", "结论及理由"),
    ("论证过程", "判断理由"),
    # 通用兜底：-内部术语，统一改「认定」
    ("裁决", "认定"),
    ("封存手机和电脑防止串供", "依法固定与待证事实相关且经批准取得的电子数据，并完整记录提取、校验和交接程序"),
    ("扣押所有开票设备(电脑、税控盘、UKey)、账务资料、银行U盾，并对现场人员进行控制", "经权限、批准和必要性审查后，依法固定与待证事实相关的开票、账务及电子数据；涉及人员的措施由有权机关依法决定"),
    ("查封所有企业的财务资料、电脑、服务器", "经权限、批准和必要性审查后，依法固定与待证事实相关的资料和电子数据"),
    ("封存财务软件服务器和电脑硬盘", "经权限和程序审查后，依法固定与待证事实相关的财务系统电子数据"),
    # ★★ 2026-10-04（疑点3 D10 根因修复）：**这两条已移除**。
    #   原规则：「全部银行账户流水」→「与待证事实相关且依法获准核验的特定账户、期间和交易资料」。
    #   它本意是规范**执法措施类**口语表述，但**匹配侧恰好就是资料名** ⇒ 护栏被应用到
    #   证据名/材料名上，把「全部银行账户流水（含已销户账户）」改写成一句法条措辞 ⇒
    #   **材料名变成"企业无法准备的东西"**（读者根本不知道该交什么）。
    #   实测：这些规则改写出的执法表述在报告里出现 **0 次** ⇒ 移除对报告零损失，
    #   唯一作用就是损坏材料名。**不要加回来**；材料名一律逐字呈现，不做术语改写。
    ("隔离询问", "依照法定程序分别询问"),
    ("人员审讯", "依法询问相关人员"),
    ("突击检查", "依法依权限开展现场检查"),
    ("全量资金穿透", "按待证事实、权限和期间开展必要的资金核验"),
    ("防止证据转移", "依法做好证据保全"),
    ("不给思考时间", "保障如实陈述、说明和申辩的权利"),
    ("直接追问", "围绕待证事实询问"),
    ("自认材料", "当事人陈述材料"),
    ("隐匿收入定性成立", "存在收入完整性待核事项"),
    ("虚开发票定性成立", "存在发票与交易真实性待核事项"),
    ("定性成立", "达到提交人工复核条件"),
    ("证据闭环成立", "达到内部多源提示阈值"),
    ("确认线索成立", "形成待核线索"),
    ("认定为偷税", "需由有权人员依法复核相关法律性质"),
    ("认定偷税", "相关法律性质须由有权人员依法复核"),
    ("定性为偷税", "相关法律性质须由有权人员依法复核"),
    ("构成偷税", "是否涉及相关法律责任尚待依法复核"),
    ("依法定性为偷税", "相关法律性质须由有权人员依法复核"),
    ("构成虚开", "是否涉及发票违法尚待依法复核"),
    ("建议追缴", "税款影响须按适用期间和法定程序复核；原模板建议为"),
    ("移送公安", "是否需要行政刑事衔接须由有权机关依法判断"),
    ("按虚开发票立案", "是否达到立案或移送条件须由有权机关依法判断"),
    ("多笔闭环叠加则立案", "多笔闭环只提高核验优先级，立案条件须另行依法判断"),
    ("多维异常是定案", "多维异常提高核验优先级但不能替代审理"),
    ("七维全异常=企业账务大概率全面造假", "七维异常须逐项排除合理解释并提交人工复核"),
    ("三个及以上维度的矛盾通常足以形成认定结论", "三个及以上维度的矛盾可提高调查优先级，但仍须审查来源独立性、反证和程序"),
    ("涉税违法的主观意图明显", "主观状态和客观行为均需结合完整证据依法复核"),
    ("主观故意成立", "主观状态待结合完整证据复核"),
    ("唯一合理解释", "需要重点核验的解释之一"),
    ("两证即可定案", "两个来源可提高核验优先级，但仍须审查来源独立性和证明力"),
    ("单此一条即触发风险检查", "单项达到内部筛查阈值"),
    ("铁证级", "多源支持级"),
    ("铁证", "经来源谱系去重的多源材料"),
    ("系统性造假", "多域异常待核"),
    ("全面造假", "多域异常待核"),
    ("即可定案", "可提交人工复核"),
)

_PENALTY_SENTENCE = re.compile(
    r"[^。；\n]*(?:罚款|刑事追诉|追缴少缴|补缴[^。；\n]*滞纳金|立即立案)[^。；\n]*[。；]?"
)

# ★ 2026-09-29（点评复核发现的真缺陷）：**法定口径豁免**。
#   实测事故：报告「九、时效与滞纳金提示」原文写"更正申报与补缴将依法自汇算期结束次日起
#   按日加收万分之五滞纳金…在补缴资金安排中计入滞纳金成本…小税种的补缴同样自法定缴纳期限
#   届满起计算滞纳金"，因**含"补缴…滞纳金"**被上面正则整句命中 → 三处全部替换为同一句
#   中性模板（"具体税款、滞纳金、处罚或移送后果须依据…"），于是：
#     ① 点评 P1-12 要求的**时效与滞纳金提示实际没能进入报告**（改完却看不见）；
#     ② 同一模板句连续出现 3 次（读者看到复读）。
#   根因：把**法定期限/滞纳金计算规则**的陈述，误当成"对本企业作出处罚断言"。
#   判据：句中含法定口径词（期限/按日/万分之五/汇算清缴…）→ 属**规则陈述**，原样保留。
_STATUTORY_RULE_HINTS = (
    "汇算清缴", "法定缴纳期限", "申报期限", "缴纳期限届满", "按日加收", "按日万分之五",
    "万分之五", "截止于", "计算滞纳金", "滞纳金成本", "起计算滞纳金",
)

# ── 定性越界拦截（**规则式**，2026-09-25 补）──────────────────────────────────
# 上面 `_DIRECT_REPLACEMENTS` 是**黑名单**：只能挡住已逐条列举的说法，
# 任何新写法都能原样流进企业报告。实测漏网的真实句子：
#   「部分收入经个人账户归集，**是账外收款的直接证据**，须逐一核验个人账户性质与去向」
#   「…**是账外收款/资金滞留个人账户的直接证据**」
# 这类句式把"筛查到的线索"直接断言为"已成立的违法事实"，越过「发现≠确认」的边界。
# 故此处按**句式**（而非词条）拦截：凡把线索称作"证据/铁证/定罪依据"，
# 或直接断言"构成<罪名>"、"已认定违法"、"必然/一定 违法"，一律降为待核表述。
# ⚠ 量词用**贪婪**（`{0,N}`）不用惰性（`{0,N}?`）：惰性会在最早的罪名词处收尾，
#   把「构成逃税罪」切成「构成逃税」+ 残留「罪」（实测）。贪婪会让罪名整体吃掉。
# 与处罚句规则一致：命中片段所在句子若含《》视为法规引文，不改（避免误伤法条原文）。
_EVIDENCE_WORD = r"的(?:直接)?(?:证据|铁证|确凿证据|认定依据|定罪依据|定案依据)"
# 罪名/违法性词的**完整搭配**（长词在前：正则取最先匹配的选项，
# 若把"逃税"排在"逃税罪"前，贪婪回溯会在"逃税"处收尾、残留一个"罪"）。
_OFFENCE_WORD = (r"(?:违法行为|发票行为|账外行为|逃税罪|偷税罪|虚开发票罪|"
                 r"骗取出口退税罪|虚开增值税专用发票罪|罪|偷税|逃税|虚开|骗税|走私|"
                 r"隐瞒收入|账外收入)")
_OVERCLAIM_RULES = (
    # ① X（是|属于|构成|即为）… 的证据/铁证/定罪依据
    (re.compile(r"(?:是|属于|构成|即为|成为)[^。；，、\n]{0,26}" + _EVIDENCE_WORD),
     "可作为待核线索"),
    # ② 构成<罪名/违法>
    (re.compile(r"构成[^。；，、\n]{0,16}" + _OFFENCE_WORD),
     "是否涉及相关法律责任尚待依法复核"),
    # ③ 已（证实|认定|确认|坐实）<违法性>
    (re.compile(r"(?:已|业已)(?:证实|认定|确认|坐实)[^。；，、\n]{0,16}" + _OFFENCE_WORD),
     "相关法律性质须由有权人员依法复核"),
    # ④ 必然/一定/肯定/无疑 <违法>
    (re.compile(r"(?:必然|一定|肯定|无疑|势必)[^。；，、\n]{0,12}" + _OFFENCE_WORD),
     "需由有权人员依法复核"),
    # ⑤ X（即是|即为|已是|已经构成）账外收入/隐匿收入
    (re.compile(r"(?:即是|即为|已是|已经构成|已经形成)[^。；，、\n]{0,10}(?:账外收入|账外收款|隐匿收入|隐瞒收入)"),
     "存在收入完整性待核事项"),
    # ⑥ 定性成立 / 证据闭环成立 / 已形成完整证据链
    #    ⚠ 2026-10-01 误伤修复：本规则**只拦断言**（"部分收入定性成立"）。
    #      实测事故：报告「三、已取得的资料与待补充的资料」写的是
    #      「本项要**定性为成立还是不成立**，须先把材料补齐」——这是**待核/双向问句**，
    #      却被整段替换成「本项要**达到提交人工复核条件还是不成立**」，读者完全看不懂。
    #      根因：正则里 `成立` 会把"成立还是不成立""成立与否"这类**否定向/选择式**一并吃掉。
    #      故 ⑥ 拆到 `_OVERCLAIM_FACT_RULE`，由 `_HEDGE_QUERY` 先判句子是不是待核问句，
    #      是则只应用 ①~⑤、跳过 ⑥；否则照旧拦截。
    #      白名单是**声明式**的： future 新增同类问句须写进 `_HEDGE_QUERY`，否则仍会被改。
    (re.compile(r"(?:定性|举证|证明|证据链)[^。；，、\n]{0,8}?成立"),
     "达到提交人工复核条件"),
)

# ⑥ 单独成组：待核/双向问句**不适用** ⑥（见下方 `_HEDGE_QUERY`）
_OVERCLAIM_FACT_RULE = _OVERCLAIM_RULES[-1:]

# ★ 待核/双向表述的识别式：句中含有"成立还是不成立""成立与否""能否定性成立"等，
#   说明这句话在问"能不能成立"，不是在断言"已经成立" → 跳过 ⑥，其余规则照常。
_HEDGE_QUERY = re.compile(
    r"成立还是不成立|成立与否|是否定性成立|能否定性成立|"
    r"定性为成立(?:还是|与否)|是否足以(?:成立|定性)|是否构成(?:成立|违法)"
)


def _clean_text(value):
    if not isinstance(value, str) or not value:
        return value
    cleaned = value
    for old, new in _DIRECT_REPLACEMENTS:
        # ★★ 2026-10-03：**替换词必须与所在句子的语法槽位相容**。
        #   事故：模板写「是否构成偷税、以及是否移送」——黑名单把「构成偷税」整词替换成
        #   「是否涉及相关法律责任尚待依法复核」（自带前导"是否"），于是 24 条疑点的
        #   「若不补证的后果」全部出现 **「是否是否涉及相关法律责任…」**。
        #   根因：黑名单值是按"独立断言句"写的（"该行为构成偷税" → "是否涉及…"），
        #   而它会被用在**已被"是否"引导**的从句里。现做上下文适配：
        #   若前面已有"是否"，则用**述谓形式**（去掉前导"是否"），替换后仍然中性、
        #   且句子通顺（"是否涉及相关法律责任尚待依法复核"）。
        if new.startswith("是否"):
            cleaned = re.sub(r"(?<=是否)" + re.escape(old), new[len("是否"):], cleaned)
            cleaned = cleaned.replace(old, new)
        else:
            cleaned = cleaned.replace(old, new)

    # 2026-08-26 审计修复（P2-2）：处罚正则白名单。
    # 仅当命中片段不是已有法规引文（含《》）时才替换为中性复核提示，
    # 避免误伤合法的法条引用（如"依据《税收征收管理法》处五倍以下罚款"）。
    def _penalty_repl(match):
        seg = match.group(0)
        if "《" in seg:
            return seg
        # ★ 法定口径豁免：期限/滞纳金计算规则的陈述不是"对本企业的处罚断言"，原样保留
        #   （否则点评要求的时效与滞纳金提示会被整句替换掉、且连续重复）。
        if any(_h in seg for _h in _STATUTORY_RULE_HINTS):
            return seg
        return "具体税款、滞纳金、处罚或移送后果须依据适用期间、完整事实、证据和法定程序由有权人员复核。"

    cleaned = _PENALTY_SENTENCE.sub(_penalty_repl, cleaned)
    # ★ 去复读：中性化可能把多处命中替换成**同一句**，连续重复对读者无意义（实测 3 连）。
    cleaned = _collapse_duplicate_sentences(cleaned)
    # 2026-09-25：定性越界（规则式，见 _OVERCLAIM_RULES 注释）
    cleaned = _apply_overclaim_rules(cleaned)
    # ★★ 2026-10-03：**替换后去"口吃"** —— 中性化是"整词换整词"，当替换词与
    #   上下文已有功能词重合时会产生「是否是否…」「是否需要…」这类重复
    #   （事故：24 条疑点的后果段全部出现「是否是否涉及相关法律责任…」）。
    #   上面已按槽位适配黑名单；此处再兜一道通用归并，使**新增同类替换词**不会复发。
    return _collapse_stutter(cleaned)


# 会被中性化替换词"撞上"的功能词（重复即成口吃，需归并）
_STUTTER_WORDS = ("是否", "需要", "相关", "应当", "须由", "依法", "可以", "认定")


def _collapse_stutter(text: str) -> str:
    """连续重复的功能词归并一次：`是否是否` → `是否`（幂等，不触碰其它内容）。"""
    if not text:
        return text
    out = text
    for w in _STUTTER_WORDS:
        prev = None
        while out != prev:
            prev = out
            out = out.replace(w + w, w)
    return out


def _collapse_duplicate_sentences(text: str) -> str:
    """把**连续重复**的句子压成一次（净化加工的收尾保险）。

    真实事故：一处文本里 3 个片段命中同一条中性化规则 → 同一句模板连续出现 3 次。
    判据只处理**相邻**重复（不跨句去重），避免误删正当的重复强调。
    """
    if not text or "。" not in text:
        return text
    try:
        from engine.sentencekit import split_sentences
        pieces = split_sentences(text, keep_delims=True)
    except Exception:
        return text
    out = []
    prev_key = None
    for p in pieces:
        key = re.sub(r"[\s，。；：、（）()【】\[\]「」“”\"'\-—_/|]", "", str(p))
        if key and prev_key is not None and key == prev_key:
            continue
        out.append(p)
        prev_key = key or prev_key
    return "".join(out)


def _apply_overclaim_rules(text: str) -> str:
    """逐句应用定性越界规则。

    ⚠ 必须**逐句**判断豁免：法条引文的《》可能在匹配片段之外
      （如「依据《税收征收管理法》第六十三条，构成偷税的可处…」——
       命中片段只有"构成偷税"，但其所在句子是法条引文，不得改）。
    ⚠ 同时逐句切分也天然阻止规则跨越「。」「；」误匹配整段。
    """
    if not text:
        return text
    from engine.sentencekit import split_sentences
    pieces = split_sentences(text, keep_delims=True)
    out: List[str] = []
    for seg in pieces:
        if not seg or seg in ("。", "；", "\n") or "《" in seg or "》" in seg:
            out.append(seg)
            continue
        # ★ 待核/双向问句（"成立还是不成立""成立与否"）不得被 ⑥ 中性化——
        #   ⑥ 的成立是拦"已定性成立"的断言，问句不含该断言（2026-10-01 实测误伤事故）。
        _rules = (_OVERCLAIM_RULES if not _HEDGE_QUERY.search(seg)
                  else _OVERCLAIM_RULES[:-1])
        for pattern, repl in _rules:
            seg = pattern.sub(repl, seg)
        out.append(seg)
    return "".join(out)


def neutralise_methodology_text(value):
    """供只读方法论资产接口复用的文本边界净化。"""
    return _clean_text(value)


def _alternative_explanations(text):
    groups = []
    if any(word in text for word in ("收款", "银行", "资金", "回流")):
        groups.extend(["借款或还款", "股东投入或资本往来", "代收代付", "退款冲正", "跨期结算或预收款"])
    if any(word in text for word in ("发票", "开票", "进项", "销项")):
        groups.extend(["开票与履约时点差异", "红冲或退货", "第三方付款", "免税或不征税事项", "票面品名与实际业务映射差异"])
    if any(word in text for word in ("存货", "进销", "产能", "能耗", "加工", "物流")):
        groups.extend(["委托加工或外包生产", "在途、退货或盘点差异", "季节性和停工", "客户自提或包价运输", "产品转换和合理损耗"])
    if any(word in text for word in ("工资", "人员", "社保", "个税")):
        groups.extend(["劳务外包或派遣", "兼职或灵活用工", "入离职期间差异", "非工资所得分类", "社保缴费口径差异"])
    if any(word in text for word in ("费用", "成本", "资产")):
        groups.extend(["受益期或资本化差异", "关联方代垫", "暂估和跨期结算", "业务模式造成的结构差异"])
    if not groups:
        groups = ["主体或期间口径差异", "资料缺失或解析误差", "正常商业安排", "政策例外或过渡规则"]
    return list(dict.fromkeys(groups))[:6]


def _evidence_state(finding, combined_text):
    current = finding.get("finding_status")
    if current:
        return current
    if any(word in combined_text for word in ("缺少", "缺失", "无数据", "无法评估", "资料不足")):
        return "insufficient_data"
    cross = finding.get("cross_domain_evidence") or {}
    dimensions = cross.get("dimensions_triggered", []) if isinstance(cross, dict) else []
    if len(dimensions) >= 2 or finding.get("_phase3_cross_validated"):
        return "partially_supported_pending_human_review"
    if finding.get("source_chain") == "analysis":
        return "hypothesis_pending_evidence_review"
    return "clue_pending_investigation"


def review_finding(finding):
    """原地规范一条发现，并返回同一对象以兼容现有流水线。"""
    if not isinstance(finding, dict):
        return finding

    for field in (
        "type", "detail", "description", "how_found", "tax_impact", "suggestion",
        "policy_ref", "determination", "action", "remedy", "focus", "normal_reason",
        "drill_questions", "evidence", "risk_table", "direction", "phenomena",
        "threshold", "applicable_condition",
    ):
        if field in finding:
            finding[field] = _clean_text(finding.get(field))
    # ★ 2026-09-25：**兜底覆盖其余所有字符串字段** —— 上面的字段清单是"白名单"，
    #   任何新增字段（如 `adjudication` / `limitations` / `cleared_reason`）都会**绕过文字门禁**，
    #   实测这三个字段带着「竞争假设裁决」原样进了报告数据（前端会渲染发现明细）。
    #   改为白名单 + 兜底：已列字段按原顺序处理（保持既有语义），其余字符串字段一并净化。
    _KNOWN = {
        "type", "detail", "description", "how_found", "tax_impact", "suggestion",
        "policy_ref", "determination", "action", "remedy", "focus", "normal_reason",
        "drill_questions", "evidence", "risk_table", "direction", "phenomena",
        "threshold", "applicable_condition",
    }
    # ★ 2026-09-25：**机器枚举字段豁免**。
    #   这些字段的值是程序约定的枚举标识（用于分组/统计/放行判断），不是给人读的散文。
    #   文案门禁对它们做词条替换会**破坏程序语义**：实测 `terminal_state="铁证如山"`
    #   被黑名单把「铁证」替换成「经来源谱系去重的多源材料」，于是终局值变成
    #   「经来源谱系去重的多源材料如山」——报告里按终局分组的统计随之全部落空。
    #   枚举值的"措辞"由定义处负责（已避开黑名单词），此处不得二次改写。
    _ENUM_FIELDS = {
        "level", "risk_level", "severity", "terminal_state", "conclusion_grade",
        "release_status", "direction", "verdict", "status", "analysis_status",
        "grade", "state", "source_type", "doc_type", "file_type",
    }
    for field, value in list(finding.items()):
        if (field in _KNOWN or field in _ENUM_FIELDS
                or not isinstance(value, str) or field.startswith("_")):
            continue
        finding[field] = _clean_text(value)
    for field, value in list(finding.items()):
        if field.startswith("_rule_") and isinstance(value, str):
            finding[field] = _clean_text(value)

    # ── 自动补全缺失的 how_found ──
    how = (finding.get("how_found") or "").strip()
    if not how:
        ftype = finding.get("type", "未命名")
        fdomain = finding.get("domain", finding.get("category", ""))
        # ★ 2026-09-25：安全截断（朴素 [:80] 会切在括号内部，产出不闭合残句）
        from engine.sentencekit import clamp_text as _clamp
        fdetail = _clamp(finding.get("detail", finding.get("description", "")), 80)
        ev_count = 0
        ev = finding.get("evidence", []) or finding.get("evidence_rows", []) or finding.get("items", []) or []
        if isinstance(ev, list):
            ev_count = len(ev)
        # ★ 2026-09-25：① 去掉「系统分析:」这类**系统自述**——报告是给企业的对外文书，
        #   只写"发现了什么、依据什么"，不写"系统做了什么"（报告纪律）；
        #   ② 冒号改全角 —— 半角冒号+空格混在中文里（实测 `系统分析: 对…检测`）。
        _scope = f"对{fdomain}执行{ftype}检测" if fdomain else f"对{ftype}执行检测"
        how = _scope
        if ev_count:
            how += f"，基于{ev_count}条证据记录"
        if fdetail:
            how += f"。详情：{fdetail}"
        finding["how_found"] = how

    combined = " ".join(str(finding.get(field, "")) for field in (
        "type", "detail", "description", "category", "domain"
    ))
    state = _evidence_state(finding, combined)
    if state == "insufficient_data":
        finding["level"] = "信息"
        try:
            score = float(finding.get("score", 0) or 0)
        except (TypeError, ValueError):
            score = 0
        finding["score"] = min(score, 2)

    finding["finding_status"] = state
    # ── 证据驱动的复核分级（2026-08-26 审计修复 P0-3）──
    # 统一政策：无论证据强弱，required_human_review 恒为 True。
    # 强证据仅降低复核工作量（快速复核通道），绝不免除人工复核、绝不引入"系统辅助定性"。
    # 【原实现备查（已停用）：强证据分支曾设 required_human_review=False、
    #   determination_status="system_assisted_pending_confirmation"、
    #   safe_grade="多源交叉验证-系统辅助定性"，与 RQ3/五条禁令冲突，已按统一政策改写。】
    observed_sources = finding.get("independent_sources")
    source_count = len(set(observed_sources)) if isinstance(observed_sources, (list, tuple, set)) else 0
    finding_type = finding.get("type", "")
    finding_score = max(0, min(10, int(finding.get("score", 0) or 0)))
    
    # 根据证据强度决定复核级别（所有分支均强制人工复核）
    if source_count >= 3 and finding_score >= 6:
        # 强证据: 多源交叉验证通过，进入快速复核通道（仍须人工确认，不免除复核）
        finding["required_human_review"] = True
        finding["review_level"] = "快速复核"
        finding["determination_status"] = "strong_evidence_pending_human_confirmation"
        # 基于score映射风险等级
        if finding_score >= 9:
            finding["level"] = "极高风险"
        elif finding_score >= 7:
            finding["level"] = "高风险"
        elif finding_score >= 5:
            finding["level"] = "中风险"
        elif finding_score >= 3:
            finding["level"] = "低风险"
        else:
            finding["level"] = "信息"
        safe_grade = "多源交叉验证-证据充分待人工确认"
    elif source_count >= 2:
        # 双源证据: 标注"多源材料-建议人工复核"
        finding["required_human_review"] = True
        finding["review_level"] = "标准复核"
        finding["determination_status"] = "multi_source_pending_review"
        if finding_score >= 7:
            finding["level"] = "高风险"
        elif finding_score >= 5:
            finding["level"] = "中风险"
        elif finding_score >= 3:
            finding["level"] = "低风险"
        else:
            finding["level"] = "待核验"
        safe_grade = "多源材料待人工复核"
    elif source_count >= 1:
        finding["required_human_review"] = True
        finding["review_level"] = "深度复核"
        finding["determination_status"] = "single_source_pending_evidence"
        if finding_score >= 7:
            finding["level"] = "中风险"
        elif finding_score >= 5:
            finding["level"] = "低风险"
        else:
            finding["level"] = "待核验"
        safe_grade = "单一来源待补证"
    else:
        finding["required_human_review"] = True
        finding["review_level"] = "全面复核"
        finding["determination_status"] = "unverified_source"
        finding["level"] = "待核验"
        safe_grade = "来源未核验"
    
    finding["evidence_grade"] = safe_grade
    finding["_evidence_grade"] = safe_grade
    # 客观域发现（BOM/仓储/运输/存货勾稽等由域引擎按数据模式判定等级）：
    # 证据成熟度已用 evidence_grade 表达，level 保留域引擎的风险信号，不因证据链评价而降级为"待核验"
    if finding.get("_objective_domain_finding") and finding.get("_domain_risk_level"):
        finding["level"] = finding["_domain_risk_level"]
    finding["independent_source_count"] = source_count
    # 2026-08-26 审计修复（P0-3）：evidence_maturity / determination_path 中的
    # "系统辅助定性""复核后定性"话术全部改为"人工确认"口径。
    # 【原实现备查（已停用）："multi_source_system_assisted"、
    #   "多源交叉验证→系统辅助定性→人工确认后发布"、
    #   "双源证据→建议人工复核后定性"、"单一来源→需补充证据后定性"】
    finding["evidence_maturity"] = (
        "multi_source_strong_evidence_pending_confirmation" if source_count >= 3 and finding_score >= 6
        else ("multi_source_pending_human_review" if source_count >= 2
        else ("single_source" if source_count == 1 else "unverified_source_lineage"))
    )
    finding["determination_path"] = (
        "多源交叉验证→证据充分→人工复核确认后发布" if source_count >= 3 and finding_score >= 6
        else ("双源证据→建议人工复核确认" if source_count >= 2
        else ("单一来源→需补充证据并经人工复核确认" if source_count == 1
        else "不自动定性；按证据成熟度移交人工复核"))
    )
    finding["alternative_explanations"] = finding.get("alternative_explanations") or _alternative_explanations(combined)
    finding["governance_controls"] = {
        "source_trace_required": True,
        "applicability_review_required": True,
        "supporting_and_opposing_evidence_required": True,
        "independent_source_lineage_required": True,
        "authority_approval_and_minimum_necessary_scope_required": True,
        "statement_defence_and_privacy_protection_required": True,
        "amount_and_legal_characterisation_separate": True,
        "decision_boundary": "系统输出不得替代行政认定、处理处罚、移送或司法判断。",
    }
    return finding


def review_findings(findings):
    return [review_finding(finding) for finding in findings if isinstance(finding, dict)]


def _clean_review_section(value, _seen=None):
    """递归净化文本/嵌套结构。

    关键防护：用 id() 访问集合检测环。report_data（尤其 comprehensive）可能含
    自引用/祖孙引用（个别企业数据结构存在循环），无防护会触发 RecursionError。
    """
    if _seen is None:
        _seen = set()
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, (list, dict)):
        vid = id(value)
        if vid in _seen:
            return value  # 已访问过，直接返回以断环，避免无限递归
        _seen.add(vid)
        try:
            if isinstance(value, list):
                return [_clean_review_section(item, _seen) for item in value]
            # dict
            if "type" in value and any(key in value for key in ("detail", "description", "level", "score")):
                review_finding(value)
            for key, item in list(value.items()):
                value[key] = _clean_review_section(item, _seen)
            return value
        finally:
            _seen.discard(vid)
    return value


def strip_markup(text: str) -> str:
    """去掉报告正文里的 **markdown 标记**（唯一权威）。

    ★ 为什么单独立一个函数（2026-10-07 实测事故）：
      规则原本只写在 `enterprise_report._naturalize_report_text` 里，而该函数只在
      **疑点段落构造路径**上被调用 —— `tax_impact_summary.note`、`risk_level_basis`、
      `related_analyses[].data`、要件/触发情况文本**没走到它** ⇒ 星号直通前端：
      实测产物 `**` **120 处**、**渲染到网页上 73 处**（企业会看到
      「② 增值税部分**未考虑**进项留抵…故为**上界**。」这种带星号的句子）。
      项目里其实早有这条规则，只是**局部**（`test_bank_nature` / `test_overall_conclusion` /
      `test_self_doubt` 各自断言自己那块"不得含 `**`"）⇒ 漏掉的容器没人管。
      故把它收敛成**一个**函数，并要求在**终局收口**对整份报告跑一遍。

    实现要点（都是踩过的坑）：
      · **只把"连续 ≥2 个星号"当 markdown**（本项目强调一律写 `**加粗**`）。
        ⚠ 这一点是**修 bug**：旧式 `\\*{1,3}([^*\\n]{1,40})\\*{1,3}` 把**单个星号**也当标记，
        而报告里大量引用**增值税发票品名**形如 `*现代服务*代言服务费`（实测报告内 **547 处**）
        ⇒ 旧规则把它们吃成「现代服务代言服务费」，**分类星号被删、品名不再逐字可校验**。
        注释里写的"本式要求成对，不会误伤品名"是**错的**（`*现代服务*` 本身就是一对）。
      · **必须同时吃掉 2~3 个星号**：旧式 `\\*([^*]+)\\*` 对 `**业态兜底**` 只吃到"中间那对"，
        替换后剩 `*业态兜底*`，**把加粗半剥成斜体**（实测三处：cost_recon_detail 的
        「业态兜底」、special_redline_detectors 的「转让方自然人」、
        verified_redline_engine 的「无法核实」）。
      · **幂等**：已无星号的串原样返回，可重复执行。
      · **兜底**：成对规则（上限 40 字）处理不了的，一律按"**连续 2 个以上星号即标记**"
        整体删除。实测该兜底是必要的 —— `key_points` / `discovery_overview` 里的
        「…自然人自有账户（私户）的流水**（已读到的是…」正是**加粗段被截断**后剩下的
        **落单 `**`**（原文是 `**本轮未提供…的流水**`），成对规则救不了它。
        ⚠ **单个 `*` 绝不删**：增值税发票品名形如 `*住宿服务*住宿服务`，删了会损坏品名。
    """
    if not isinstance(text, str) or not text:
        return text
    # ★ 数据占位符护栏：**整串只有星号**（如发票「规格型号」列的值就是 `**`）不是 markdown
    #   —— 强调一定是"包着内容"的，裸 `**` 只能是数据。实测 `report_compliance` 的
    #   发票明细里有 449 个 `"spec": "**"`，无此护栏会被清成空串（数据被删）。
    if text.strip() and set(text.strip()) <= {"*"}:
        return text
    s = text
    if "*" in s:
        s = re.sub(r"\*{2,3}([^*\n]{1,40})\*{2,3}", r"\1", s)
        # 兜底：落单/超长的星号串（连续 ≥2 个）＝ markdown 残留，整体删掉；单个 `*` 保留
        s = re.sub(r"\*{2,}", "", s)
    if "#" in s:
        # 行首标题号：`MULTILINE` —— 必须逐行剥（原实现即如此），只判首字符会漏掉
        # 多行文本里第 2 行起的 `### 标题`。
        s = re.sub(r"^\s*#{1,6}\s*", "", s, flags=re.M)
    return s


def review_report_methodology(report_data):
    """净化报告中的综合判断和域结果，并标明评分用途。"""
    if not isinstance(report_data, dict):
        return report_data
    for key in (
        "all_findings", "domain_results", "comprehensive", "overall_assessment",
        "governance_summary", "core_issues", "prioritized_actions",
    ):
        if key in report_data:
            report_data[key] = _clean_review_section(report_data[key])

    comprehensive = report_data.get("comprehensive")
    if isinstance(comprehensive, dict):
        assessment = comprehensive.get("overall_assessment")
        if isinstance(assessment, dict):
            assessment["assessment_scope"] = "screening_priority_not_legal_conclusion"
            assessment["assessment_status"] = "pending_human_review"
            assessment["score_usage"] = "仅用于安排资料核验顺序，不决定违法性质、处理处罚或纳税信用。"
    return report_data


# 向后兼容别名（旧名含 methodology，已弃用）
neutralise_output_text = neutralise_methodology_text
review_report_text = review_report_methodology


# ═══════════════════════════════════════════════════════════════════════════
# 措辞审计（本批由「知识库自学习」提炼并入；来源：WB-TRISK-SAMPLE-001）
# 两条判据来自阶段1 诊断实测（P3 定性口径破句 / P3-b 已查明与未认定同段冲突）。
# ═══════════════════════════════════════════════════════════════════════════
_WORDING_RULES = (
    {
        "id": "W1", "name": "定性口径破句（缺谓语）",
        "regex": r"本企业本项已查明的风险[；;]",
        "why": "模板变量位为空导致句子断裂，且与全文『不作认定』正面冲突",
        "fix": "改用 L1/L2/L3 分级句式，禁止缺谓语短句",
    },
    {
        "id": "W2", "name": "『已查明的风险』未同时声明『未认定』（口径不完整）",
        # ★★ 2026-10-08（P0-2 根因已修 ⇒ 判据收敛，**不再靠白名单避险**）：
        #   旧版此处有一串 80 字负向前瞻豁免（未认定／不作定性／待核／须由风险检查员／
        #   涉及定性的部分／以已上传资料的可复核证据为限 …）—— 那串豁免的**唯一存在理由**
        #   是"产出里确有一句合规的『本项已查明的风险；未认定到构成要件』"。
        #   现该句已**下线**：结论用语唯一由 `conclusion_grade.pending_clue_phrase` 生成
        #   （输出「本项属待核事项（…）；未认定到构成要件，不作定性」，**不含任何定性词**）。
        #   ⇒ 报告正文里**不应再出现**「已查明的风险」；本判据恢复为**纯粹的重现护栏**
        #     （任何位置出现即命中），并由 `check_conclusion_phrase_authority`（源码级
        #     "私有实现归零"）与质量门禁 A3/B5（数据级）三重锁定。实测产物 occurrences = 0。
        "regex": r"已查明的风险",
        "why": "报告已不再使用『已查明』作结论用语（L2 禁定性词，统一由 pending_clue_phrase 生成）"
               "⇒ 出现即为旧实现回潮/新写了字面量",
        "fix": "改走 `engine.conclusion_grade.pending_clue_phrase()`（唯一生成点），禁止手写结论句",
    },
)


def audit_wording(text: str) -> list:
    """措辞审计：返回命中清单（空列表 = 通过）。供门禁与产出链调用。"""
    import re as _re
    hits = []
    for r in _WORDING_RULES:
        for m in _re.finditer(r["regex"], str(text or "")):
            hits.append({"rule": r["id"], "name": r["name"],
                         "at": m.group(0)[:60], "why": r["why"], "fix": r["fix"]})
    return hits
