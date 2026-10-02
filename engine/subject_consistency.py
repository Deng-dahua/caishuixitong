# -*- coding: utf-8 -*-
"""疑点主体一致性 —— 判断「写进某个疑点的内容」与「该疑点的主体」是不是同一件事。

## 为什么需要（根因）

报告里反复出现**"疑点编辑的内容与疑点主体错配"**，实测三例：

  · 标题「白条入账：无合规凭证列支成本费用」，正文与附表却是
    「银行存款支出方对等逐月不匹配 / 应付账款发生额对等逐月不匹配」；
  · 标题「附加税费计税依据与增值税不匹配」，附表挂的是
    「增值税进项税额对等逐月不匹配」；
  · 标题「有进无销：大量进项无对应销售实现」，附表挂的是
    「增值税进项税额对等逐月不匹配」。

三类根因，互相独立：

  ① **归属层**：勾稽引擎（`monthly_reconcile`）给每条勾稽轴"就近"挑了一个红线编号，
     而该红线的**名字描述的是另一件事**（银行存款支出对等 → RL-COST-003「白条入账」；
     进项税额对等 → RL-VAT-002「有进无销」）⇒ 报告用红线名当标题，**主体从源头就错了**。
  ② **挂载层**：报告给疑点挂逐笔明细时，先按红线编号精确关联，未命中就用
     「红线名 ↔ 发现类型」的汉字 2-gram 重叠兜底 ⇒ 把别的发现的表挂了过来
     （RL-OTH-003 拿到一张增值税进项表）。
  ③ **判据层**：上面两层都想用"文字相似度"当判据。实测**文字相近 ≠ 主体同一**，
     且双向都错：真配对被判成错配（「成本列支的资金与负债证据不足」＋「表1 主营成本
     总额·按供应商分布」，语义完全对口、字面重叠 0.00），用词相近的错配反被"看起来相关"。

## 做法（唯一权威）

判据**不靠文字相似度**，靠两条可证伪的口径：

  ① **来源归属**（权威、零猜测）：这张表来自哪条发现？该发现是不是**本疑点自己声明的
     支撑发现**？`supporting_findings` 是引擎给出的"本疑点由哪些发现构成"，是唯一权威。
     归属不符的表一律不挂。
  ② **声明 + 主体可核**（归属层）：允许某条发现声明某个红线编号，前提是**红线库自己
     声明过"这类主体属于我"**（`REDLINE_SUBJECT_DECL`，新增同类只加一行）。声明不成立
     的归属一律拒绝 —— 该发现退回按构成要件做有据匹配（`match_redline_grounded`），
     或如实列为"未归入已知风险情形"，**绝不套错构成要件**（宁缺勿错）。

本模块是该判据的唯一实现：报告自检、红线归属、勾稽轴选线三处都调它，不各自再写一份。
"""

from __future__ import annotations

import re
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Tuple

# ═══════════════════════════════════════════════════════════════════════════
# 一、主体词（用于"同一主体"的宽容判据；不做主判据）
# ═══════════════════════════════════════════════════════════════════════════

# 泛词/结构性词：任何两条税务报告文本都可能共有，不描述"是哪一件事"。
SUBJECT_STOP: FrozenSet[str] = frozenset({
    # 报告语言结构性词
    "事项", "风险", "问题", "情况", "内容", "数据", "信息", "结果", "分析",
    "存在", "可能", "涉嫌", "需要", "核实", "确认", "检查", "核查", "疑点",
    "金额", "数量", "比例", "合计", "差异", "差额", "一致", "匹配", "符合",
    "逐月", "逐季", "逐年", "对等", "勾稽", "比对", "不符", "不一致", "不匹配",
    "本项", "本企业", "企业", "单位", "相关", "有关", "上述", "以下", "如下",
    # 税种/税目名（同一税种下的不同事项不是同一主体）
    # ★ 「附加」「印花」这类**必须保留**：它们是"附加税费/印花税"与其它事项的区分点
    #   （「附加税费计税依据与增值税不匹配」的正当支撑正是「城建税及教育费附加…」）。
    "增值", "值税", "增值税", "所得", "得税", "所得税", "企业所得税", "个人所得税",
    "印花税", "消费税", "资源税", "契税", "车船税",
    "税费", "税额", "税金", "税负", "纳税", "申报", "进项", "销项", "留抵", "开票", "发票",
})

# 上位泛化词：单靠它相同**不足以**判定"同一主体"（如「营业」同时出现在
# 「营业账簿印花税」与「营业收入差异」）——避免用语料高频前缀把两件事并成一件。
_GENERIC_TERMS: FrozenSet[str] = frozenset({
    "营业", "主营", "业务", "本期", "期末", "上年", "本年", "同期", "上述", "有关", "公司",
})

# 功能字：含这些字的 2-gram 多为跨词切分产物（「据与」「与增」「不匹」），不参与判定。
# ★ 「有」「无」**不列入**：它们是领域惯用语的有义成分（有进无销／有销无进／无票列支／
#   无对应挂账），剔掉会让这类主体无法与其他主体区分。而「不」「未」是纯否定、
#   本身不构成主体，仍剔除（否则「不匹配」「不一致」会把任意两条勾稽发现变成"同一主体"）。
_FUNC_CHARS: FrozenSet[str] = frozenset(
    "的与和及或在为不是未等按以对从向由被把并还也都要可将已到就该其此这那让使"
    "上中下前后时而而且但所之则如若因此故才只更更多少很"
)

# 尾部期间/批次/口径括注：主体比对前必须剥掉（否则「（2025-01）」会污染判据）
_TAIL_PAREN = re.compile(
    r"[（(]\s*(?:"
    r"\d{4}\s*[-/年]\s*\d{1,2}\s*月?(?:\s*[~～至\-—]\s*\d{4}\s*[-/年]\s*\d{1,2}\s*月?)?"
    r"|第\s*\d+\s*[批轮月期次]"
    r"|共\s*\d+\s*[项笔张个月批次]"
    r"|待核|抽样\s*\d+\s*笔|合计[^）)]{0,28}|来源[:：][^）)]{0,24}"
    r")\s*[）)]\s*$"
)
_BRACKET_ANY = re.compile(r"[（(][^（()）]{0,60}[）)]")


def strip_period_brackets(s: Any) -> str:
    """重复剥掉尾部的期间/批次/（共N笔）括注，返回裸主体文本。"""
    t = str(s or "").strip()
    prev = None
    while t and t != prev:
        prev = t
        t = _TAIL_PAREN.sub("", t).strip()
    return t


def norm_subject_key(s: Any) -> str:
    """主体规范键：去尾部期间括注 + 只留中文与字母数字（用于归属比对）。

    ★ 与 `ledger_governance.canonical_ledger_key` 同口径（同去尾部期间括注），
      但本函数**再剥一层中间括注**并去掉所有标点，用于"同一主体"的严格相等判定。
    """
    t = strip_period_brackets(s)
    t = _BRACKET_ANY.sub("", t)          # 再剥中间括注（如「（共3笔）」夹在中间）
    return "".join(re.findall(r"[一-鿿A-Za-z0-9]", t))


def subject_terms(text: Any) -> FrozenSet[str]:
    """抽取"主题词"：中文连续段上的 2-gram，剔除泛词与含功能字的切分产物。"""
    t = strip_period_brackets(text)
    out = set()
    for run in re.findall(r"[一-鿿]{2,}", t):
        for i in range(len(run) - 1):
            bg = run[i:i + 2]
            if bg in SUBJECT_STOP or any(c in _FUNC_CHARS for c in bg):
                continue
            out.add(bg)
    return frozenset(out)


def same_subject(a: Any, b: Any) -> bool:
    """两段文本是否"同一主体"。

    判据：① 主题词有交集；② 且交集**够实**——
      · 交集 ≥2 个主题词；或
      · 只有 1 个，但该词不是上位泛化词（`_GENERIC_TERMS`）。
    单一个泛化词相同（如都含"营业"）不足以说明是同一件事 —— 那正是"文字相近"的陷阱。
    """
    ov = subject_terms(a) & subject_terms(b)
    if len(ov) >= 2:
        return True
    if len(ov) == 1:
        return next(iter(ov)) not in _GENERIC_TERMS
    return False


# ═══════════════════════════════════════════════════════════════════════════
# 二、红线归属声明（归属层唯一权威；新增同类只加一行）
# ═══════════════════════════════════════════════════════════════════════════
# 语义：`红线编号 -> 允许声明它的「发现主体短语」`。
# 一条发现声明某红线编号时，其主体（发现类型，剥掉期间括注后）**必须包含**
# 该红线声明的任一短语；否则该声明不成立 → 拒绝归属（退回有据匹配 / 列为未归类）。
#
# ★ 判据是"红线库自认领哪些主体"，不是"文字像不像"：因此它可被审、可被证伪。
#   漏加一行 ⇒ 该检测器声明的归属被拒绝（并在审计里留痕），**不会**静默套错要件。
REDLINE_SUBJECT_DECL: Dict[str, Tuple[str, ...]] = {
    # —— 勾稽/对等类（账·票·表·申报 多源比对）——
    # 主体短语取"勾稽轴名"，与 monthly_reconcile 的轴标题逐字对齐。
    "RL-CIT-008": (
        "表间勾稽", "四方比对", "多源对等", "三源对等", "税价配比",
        "对等逐月不匹配", "对等逐年不匹配", "对等逐季不匹配",
    ),
    "RL-FUND-005": (
        "银行流水余额滚动", "勾稽断裂", "银行存款收入方对等", "银行存款支出方对等",
    ),
    "RL-FUND-006": ("同一凭证借贷不平", "借贷失衡", "借贷不平"),
    "RL-PAY-002": (
        "个税申报工资", "工资多源对等", "个税三源对等", "社保缴纳对等",
        "工资差异", "社保基数",
    ),
    "RL-SPT-010": ("住房公积金", "公积金缴存对等", "缴存基数", "公积金"),
    "RL-PTY-001": (
        "资金与负债", "应付账款发生额对等", "未匹配到付款", "无支付流水",
        "成本资金", "无对应挂账",
    ),
    # —— 成本/费用列支凭证类 ——
    "RL-COST-003": (
        "白条", "无合规凭证", "无票", "有票支撑", "取得发票对成本费用",
        "列支无发票",
    ),
    # —— 增值税勾稽 ——
    "RL-VAT-002": ("有进无销", "进项无对应销售", "无销项实现"),
    "RL-VAT-001": ("有销无进", "销售品名无对应进项"),
    "RL-OTH-003": ("附加税费", "城建税", "教育费附加", "附征"),
    # —— 银行收款 vs 申报收入 ——
    "RL-INC-001": ("银行收款大于申报收入", "银行收款", "应收账款发生额对等"),
    # —— 固定资产账实/折旧勾稽 ——
    "RL-AST-001": ("固定资产原值勾稽", "累计折旧勾稽", "固定资产取得", "折旧"),
    # ★ 以下两条由"自检误报"反推补登记（实测同一件事的两种说法，不是错配）：
    #   · RL-FUND-001「公转私大额频繁支出」的外部核验项主语是**对私资金往来**
    #     （同一件事的内/外部两种表述）—— 不登记会把正当疑点误标成错配；
    #   · RL-CIT-004「长期亏损仍持续经营」的**要件本身**含"税负贡献与规模不匹配"，
    #     故「企业所得税贡献率偏低」是该红线的正当实例（标题已按要件裁剪并声明范围）。
    "RL-FUND-001": ("公转私", "对私资金往来", "变相分配", "私户支付", "私账支付"),
    "RL-CIT-004": ("企业所得税贡献率偏低", "贡献率偏低", "税负贡献", "长期亏损", "持续经营"),
}

# 兜底：未在 `REDLINE_SUBJECT_DECL` 中登记的红线，是否允许被声明。
#   ★ 必须为 True：91 条红线里绝大多数由专用检测器声明，类型五花八门，
#     不可能也不应该逐条穷举主体短语。未登记的红线走"宽松"档（允许声明），
#     但**已登记的必须严格**——这样新增同类只加一行即可收紧，且不会误伤存量。
DECL_UNLISTED_ALLOWED = True


def declared_subject_ok(redline_id: Any, subject: Any) -> Tuple[bool, str]:
    """某条「发现主体」是否有资格声明该红线编号。返回 `(是否允许, 原因)`。

    ★ 判据：红线库声明的短语之一出现在主体里（子串匹配，剥期间括注后）。
      未登记该红线的 → 按 `DECL_UNLISTED_ALLOWED` 处理。
    """
    rid = str(redline_id or "").strip()
    if not rid:
        return False, "无红线编号"
    phrases = REDLINE_SUBJECT_DECL.get(rid)
    if not phrases:
        return DECL_UNLISTED_ALLOWED, ("该红线未登记主体声明（宽松档）"
                                       if DECL_UNLISTED_ALLOWED else "该红线未登记主体声明")
    key = norm_subject_key(subject)
    if not key:
        return False, "发现主体为空，无法核对归属"
    for p in phrases:
        if norm_subject_key(p) and norm_subject_key(p) in key:
            return True, "主体命中该红线声明的「%s」" % p
    return False, ("主体「%s」不在该红线声明的主体范围内（应为：%s）"
                   % (str(subject)[:40], "／".join(phrases[:4])))


# ═══════════════════════════════════════════════════════════════════════════
# 三、勾稽轴 → 红线（勾稽引擎唯一映射；每条都在模块导入时自检）
# ═══════════════════════════════════════════════════════════════════════════
# 背景：勾稽轴（"银行存款支出方对等"等）产出的发现**必须**落到一条主体对得上的
# 红线；旧版在 `monthly_reconcile` 里就地硬编码、按"就近"挑，实测多处张冠李戴
# （银行存款支出对等→"白条入账"、进项税额对等→"有进无销"、工资多源对等→
#  "同一自然人同时列支工资与劳务报酬"、序时账↔余额表不符→"白条入账"）。
# 现收进本表：`轴标题 -> (红线编号, 该轴产出的发现主体样例)`；`""` 表示
# **该轴没有主体对得上的红线**（发现仍产出，作为待核事实进台账，宁缺勿错）。
# 每条在导入时被 `selfcheck_axis_map()` 自检：轴主体必须能命中该红线声明的主体短语，
# 否则该轴**不声明红线**（自检不通过即拒绝，不静默沿用错归属）。
RECONCILE_AXIS_REDLINE: Dict[str, Tuple[str, str]] = {
    "收入多源对等":            ("RL-CIT-008", "收入多源对等逐月不匹配"),
    "工资多源对等":            ("RL-PAY-002", "工资多源对等逐月不匹配"),
    "个税三源对等":            ("RL-PAY-002", "个税三源对等逐月不匹配"),
    "增值税销项税额对等":      ("RL-CIT-008", "增值税销项税额对等逐月不匹配"),
    "增值税进项税额对等":      ("RL-CIT-008", "增值税进项税额对等逐月不匹配"),
    "银行存款收入方对等":      ("RL-FUND-005", "银行存款收入方对等逐月不匹配"),
    "银行存款支出方对等":      ("RL-FUND-005", "银行存款支出方对等逐月不匹配"),
    "社保缴纳对等":            ("RL-PAY-002", "社保缴纳对等逐月不匹配"),
    "公积金缴存对等":          ("RL-SPT-010", "公积金缴存对等逐月不匹配"),
    "应收账款发生额对等":      ("RL-CIT-008", "应收账款发生额对等逐月不匹配"),
    "应付账款发生额对等":      ("RL-PTY-001", "应付账款发生额对等逐月不匹配"),
    "收入税价配比":            ("RL-CIT-008", "收入税价配比异常"),
    "采购税价配比":            ("RL-CIT-008", "采购税价配比异常"),
    "固定资产原值勾稽":        ("RL-AST-001", "固定资产原值勾稽"),
    "累计折旧勾稽":            ("RL-AST-001", "累计折旧勾稽"),
    # ★ 该轴是"账簿记录质量"问题，91 条红线里没有主体对得上的一条 → 刻意留空：
    #   发现仍产出（待核验），由台账/勾稽章节如实呈现，不套用上下文无关的红线名。
    "序时账与科目余额表逐科目不一致（账账不符）": ("", "序时账与科目余额表逐科目不一致（账账不符）"),
}


def reconcile_finding_subject(axis: str, kind: str = "") -> str:
    """勾稽轴 → 该类发现的**主体短语**（自检用；与引擎拼出的发现类型同口径）。

    例：`("银行存款支出方对等", "month")` → `"银行存款支出方对等逐月不匹配"`。
    """
    hit = RECONCILE_AXIS_REDLINE.get(str(axis))
    if hit:
        return hit[1]
    unit = {"month": "逐月", "quarter": "逐季", "year": "逐年"}.get(str(kind), "逐期")
    return "%s%s不匹配" % (str(axis), unit)


def axis_redline(axis: str, kind: str = "month") -> Tuple[str, str]:
    """勾稽轴 → `(红线编号或 "", 依据)`。**先自检再返回**：自检不过返回空编号。"""
    hit = RECONCILE_AXIS_REDLINE.get(str(axis))
    rid = (hit[0] if hit else "") or ""
    if not rid:
        return "", "勾稽轴「%s」无主体对得上的红线，只作待核事实（不套用红线名）" % axis
    ok, why = declared_subject_ok(rid, reconcile_finding_subject(axis, kind))
    if not ok:
        return "", "勾稽轴「%s」→ %s 自检不通过：%s" % (axis, rid, why)
    return rid, "勾稽轴「%s」→ %s（%s）" % (axis, rid, why)


def selfcheck_axis_map() -> List[Dict[str, str]]:
    """对 `RECONCILE_AXIS_REDLINE` 逐条自检，返回不通过项（空表 = 全部通过）。"""
    bad = []
    for axis, (rid, subject) in RECONCILE_AXIS_REDLINE.items():
        if not rid:
            continue          # 刻意留空（无匹配红线）＝通过
        ok, why = declared_subject_ok(rid, subject)
        if not ok:
            bad.append({"axis": axis, "redline_id": rid, "reason": why})
    return bad


# ═══════════════════════════════════════════════════════════════════════════
# 四、附表准入（挂载层唯一权威）
# ═══════════════════════════════════════════════════════════════════════════

def table_source_ok(support_keys: Iterable[str], source: Any) -> Tuple[bool, str]:
    """一张附表可否挂到本疑点：**看它的来源发现是不是本疑点的支撑发现**。

    参数：
      · `support_keys`：本疑点支撑发现的主体规范键集合（`norm_subject_key(type)`）；
      · `source`：附表的来源——发现的主体规范键（权威），或表标题（回退）。

    ★ 主判据是来源归属（零猜测）；来源取不到时才用标题做"同一主体"宽容判据，
      且要求标题与**某一条**支撑发现是同一主体 —— 单纯 2-gram 重叠不算（那正是错配的来源）。
    """
    keys = {k for k in (str(x or "") for x in (support_keys or [])) if k}
    src = norm_subject_key(source)
    if not keys:
        return False, "本疑点未声明支撑发现，无从判定附表归属"
    if not src:
        return False, "附表来源不可识别"
    if src in keys:
        return True, "附表来源即本疑点的支撑发现"
    for k in keys:
        if same_subject(src, k):
            return True, "附表来源与支撑发现「%s」属同一主体" % k[:24]
    return False, ("附表来源「%s」不在本疑点的支撑发现内（支撑：%s）"
                   % (str(src)[:32], "／".join(sorted(keys))[:44]))


def suspicion_subject_ok(redline_name: Any, support_subjects: Iterable[Any],
                         redline_id: Any = "") -> Tuple[bool, str]:
    """疑点主体自检：**红线名**与它的**支撑发现**是不是同一件事。

    不成立 ⇒ 报告不得用该红线名充当本疑点的主体（否则标题与内容必然错配）。

    判据两级，缺一不可地"宽":
      ① 红线名与某条支撑发现**属同一主体**（主题词有交集；泛词已剔除）；
      ② 红线库**自己声明过**这类主体归它（`REDLINE_SUBJECT_DECL`）—— 覆盖
         "泛名红线（如「表间勾稽四方比对不一致」）＋ 具体勾稽轴"这种正当情形，
         否则泛名红线会被误判为错配。
    """
    name = str(redline_name or "").strip()
    subs = [str(x or "").strip() for x in (support_subjects or []) if str(x or "").strip()]
    if not name:
        return False, "疑点无主体名"
    if not subs:
        return False, "疑点无支撑发现，主体无从核对"
    for s in subs:
        if same_subject(name, s):
            return True, "红线名与支撑发现「%s」属同一主体" % s[:24]
    _rid = str(redline_id or "").strip()
    if _rid:
        for s in subs:
            ok, why = declared_subject_ok(_rid, s)
            if ok and _rid in REDLINE_SUBJECT_DECL:
                return True, "红线库已声明该类主体归本红线（%s）" % why
    return False, ("红线名「%s」与本疑点支撑发现（%s）找不到共同主体，"
                   "红线库也未声明该类主体归本红线"
                   % (name[:26], "／".join(subs)[:44]))


# ═══════════════════════════════════════════════════════════════════════════
# 四·B、建入口那条发现（entry）的选择（归属层第二处唯一权威）
# ═══════════════════════════════════════════════════════════════════════════
# 背景：一条红线常被多条发现命中，其中一条成为疑点的"entry" —— 它决定疑点的
# **标题裁剪口径 / 线索链 / 证据链 / 论证链 / 附表来源 / 主体自检基准**。
# 旧实现是 first-finder-wins（谁先来谁当 entry），于是软匹配来的无关发现一旦排在最前，
# 整条疑点就建立在错的那条发现上（实测 RL-SPT-017「广告/娱乐服务未申报文化事业建设费」
# 的 entry 是「同一供应商同品名单价不一致」—— 只因该发现正文里举了"广告服务"这个例子）。
#
# 选择规则（可审、可证伪）：
#   ① **主体一致优先**（权重 2）：声明型发现只要能过红线自己的主体声明表即算一致；
#      红线未登记主体声明表时，**声明型即视为一致**（检测器本身是权威，不因"没登记"贬低它）；
#      非声明型（软匹配）必须与红线名属同一主体（主题词有交集）。
#   ② **声明型优先**（权重 1）：检测器真算过的 > 文本相似度凑出来的。
#   ③ 同分取证据链**闭合度更高**者，再同取先出现者（稳定）。
ENTRY_SUBJECT_WEIGHT = 2
ENTRY_DECLARED_WEIGHT = 1


def entry_subject_ok(redline_id: Any, redline_name: Any, subject: Any,
                     declared: bool = False) -> Tuple[bool, str]:
    """该条发现是否有资格代表本红线（entry 候选的主体判据）。"""
    subj = str(subject or "").strip()
    if not subj:
        return False, "发现主体为空"
    if declared:
        rid = str(redline_id or "").strip()
        if rid and rid in REDLINE_SUBJECT_DECL:
            ok, why = declared_subject_ok(rid, subj)
            return ok, why
        return True, "声明型发现（该红线未登记主体声明表，检测器本身即权威）"
    if str(redline_name or "").strip() and same_subject(redline_name, subj):
        return True, "与本红线名属同一主体"
    return False, "与本红线名找不到共同主体（软匹配不可代表本红线）"


def entry_score(redline_id: Any, redline_name: Any, candidate: Dict[str, Any]) -> Tuple[int, str]:
    """entry 候选打分：`(分数, 依据)`。分数 = 2×主体一致 + 1×声明型。"""
    subj = str((candidate or {}).get("type") or "")
    declared = bool((candidate or {}).get("declared"))
    ok, why = entry_subject_ok(redline_id, redline_name, subj, declared)
    return ((ENTRY_SUBJECT_WEIGHT if ok else 0)
            + (ENTRY_DECLARED_WEIGHT if declared else 0)), why


def pick_entry_index(redline_id: Any, redline_name: Any,
                     candidates: Iterable[Dict[str, Any]]) -> int:
    """从本红线的候选发现里选"建入口那条"，返回下标（唯一权威）。

    `candidates` 每项：`{"type": 发现类型, "declared": 是否声明型, "closure": 证据闭合度}`。
    """
    cands = list(candidates or [])
    if not cands:
        return 0
    best_i, best_key = 0, None
    for i, c in enumerate(cands):
        sc, _why = entry_score(redline_id, redline_name, c)
        try:
            clo = float((c or {}).get("closure") or 0)
        except (TypeError, ValueError):
            clo = 0.0
        key = (sc, clo)
        if best_key is None or key > best_key:
            best_i, best_key = i, key
    return best_i


def format_entry_choice(redline_id: Any, redline_name: Any,
                        candidates: Iterable[Dict[str, Any]]) -> str:
    """把 entry 选择过程写成一行（供日志/审计：为什么选它）。"""
    cands = list(candidates or [])
    i = pick_entry_index(redline_id, redline_name, cands)
    if not cands:
        return "无候选发现"
    sc, why = entry_score(redline_id, redline_name, cands[i])
    return "entry=「%s」（得分%d：%s；候选%d条）" % (
        str((cands[i] or {}).get("type") or "")[:30], sc, why, len(cands))


# ═══════════════════════════════════════════════════════════════════════════
# 五、自检（写进一键分析：报告对"自己编辑的内容"做核对）
# ═══════════════════════════════════════════════════════════════════════════

ISSUE_TABLE_SOURCE = "附表来源与本项主体不符"
ISSUE_SUBJECT_MISMATCH = "疑点主体与其证据不是同一件事"
ISSUE_ROW_SUBJECT = "明细行与本项主体无可识别关联"


def audit_report(problems: Iterable[Dict[str, Any]],
                 resolve_support: Optional[Any] = None) -> Dict[str, Any]:
    """对成品报告逐条自检「疑点主体 ↔ 自己写进去的内容」，返回审计结果。

    `resolve_support(problem) -> list[str]`：取该疑点的支撑发现主体（报告层提供；
    缺省时只做"标题 ↔ 附表标题"的宽容判据）。返回：

        {"checked": n, "ok": n, "issues": [{"seq","title","code","detail"}], "by_code": {...}}

    ★ 本函数**只读不写**：判定结果由报告层决定如何落地（不挂表 / 改写标题 / 如实说明），
      使"自检"与"处置"分离——同一套判据可被报告、台账、审计脚本共用。
    """
    issues: List[Dict[str, Any]] = []
    checked = 0
    for p in (problems or []):
        if not isinstance(p, dict):
            continue
        checked += 1
        title = str(p.get("title") or "")
        support = []
        if resolve_support:
            try:
                support = list(resolve_support(p) or [])
            except Exception:
                support = []
        sup_keys = {norm_subject_key(x) for x in support if str(x or "").strip()}
        sup_keys.discard("")

        # ① 主体：标题 vs 支撑发现
        if support:
            ok, why = suspicion_subject_ok(title, support)
            if not ok:
                issues.append({"seq": p.get("seq"), "title": title[:40],
                               "code": ISSUE_SUBJECT_MISMATCH, "detail": why})
        # ② 附表来源归属
        for para in (p.get("narrative_paragraphs") or []):
            for tb in ((para or {}).get("detail_tables") or []):
                ttl = str((tb or {}).get("title") or "")
                src = (tb or {}).get("_source_subject") or ttl
                ok, why = table_source_ok(sup_keys, src)
                if not ok:
                    issues.append({"seq": p.get("seq"), "title": title[:40],
                                   "code": ISSUE_TABLE_SOURCE,
                                   "detail": "%s｜%s" % (ttl[:28], why)})
    by_code: Dict[str, int] = {}
    for it in issues:
        by_code[it["code"]] = by_code.get(it["code"], 0) + 1
    return {
        "checked": checked,
        "issue_count": len(issues),
        "ok_count": max(0, checked - len({i["seq"] for i in issues})),
        "issues": issues,
        "by_code": by_code,
    }


def format_audit_line(audit: Dict[str, Any]) -> str:
    """审计结果 → 一行（写进 pipeline 日志，使"自检真的跑了"可见可证）。"""
    if not isinstance(audit, dict):
        return "主体一致性自检：未执行"
    by = audit.get("by_code") or {}
    if not audit.get("issue_count"):
        return "主体一致性自检：%s 项全部通过（疑点主体与所写内容一致）" % audit.get("checked", 0)
    return "主体一致性自检：检查 %s 项，发现 %s 项不一致（%s）；已按判据剔除错配内容并如实说明" % (
        audit.get("checked", 0), audit.get("issue_count", 0),
        "，".join("%s×%d" % (k, v) for k, v in sorted(by.items())) or "—",
    )
