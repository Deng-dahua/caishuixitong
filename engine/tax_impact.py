# -*- coding: utf-8 -*-
"""潜在税额影响量化测算（2026-09-27，P1）。

用户诉求（P1）：资深稽查报告应给每项疑点算"值多少钱"——**潜在税额影响**，
并汇总"本轮潜在税额敞口"。

设计纪律（严格遵守项目铁律）：
  · **取不到就明说"未量化"**，绝不用默认值/文本里随便抓一个数当金额顶数
    （实测教训：把"账面成本总额 418 万"当成成本项敞口，纯属口径错误）。
  · 只认**关键词锚定**的金额（"涉及金额/差额/未匹配金额/少缴/虚增…"+ 数字 + 元），
    且必须 ≥ `_MIN_AMOUNT`（元），否则视为未取得。
  · 测算**必须标注口径与假设**（税率、是否含小微优惠等），并声明"仅供评估量级，
    不构成核定；实际以核实后依法核定为准"。
  · 税率来自 `_RATES` 单一表；新增税种只加一行。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from engine.numparse import to_number_checked

# 低于此金额不作为敞口（滤掉单价、计数、比率等噪音）
_MIN_AMOUNT = 1000.0

# 金额关键词锚（数字必须紧跟在这些词之后才认）
_AMOUNT_KW = (
    "涉及金额", "涉案金额", "未匹配金额", "未匹配", "差额", "差异额", "差异",
    "缺口", "少计收入", "少计销项", "少计", "少缴", "多抵", "虚增", "虚列",
    "隐匿收入", "未申报收入", "未开票收入", "价税合计", "调整金额", "涉及税额",
    "成本列支金额", "开票额",
    # ★★ 2026-10-06（用户第 2 批 疑点1，**真根因**）：本正则的金额必须**前面有关键词**
    #   才会进入候选。而"本项涉案量"的语义词（红冲/红字/作废/冲减…）**不在这张表里**
    #   ⇒ 正文「销项红字/作废**1,015,900.00元**」**从未成为候选**，
    #   只有「价税合计8,050,908.58元」（分母）进了候选 ⇒ 唯一候选＝分母 ⇒ 税额虚高 13 倍。
    #   判据：**凡"本项涉案量"的语义标记，都必须让金额具备参评资格**（否则连比较机会都没有）。
    #   与 `_KW_SUBJECT`/`_KW_SUBJECT_FOR_ANCHOR` 同源（同一批语义词，一处维护）。
    "红冲", "红字", "作废", "冲减", "冲销", "超限", "不得扣除", "应转出", "未转出",
)
_AMOUNT_PAT = re.compile(
    r"(?:" + "|".join(_AMOUNT_KW) + r")[^0-9¥￥]{0,12}?([0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*元"
)

# ═══════════════════════════════════════════════════════════════════════════════
# ★★ 2026-10-03（用户复核疑点1：税额影响虚高 8.4 倍）——**语义锚定**（唯一权威）
# ═══════════════════════════════════════════════════════════════════════════════
# 事故：疑点1 报告里同时出现
#     · 本项涉案金额：销项红字/作废价税合计 **1,015,900.00 元**
#     · 占比分母：剔除红字后的销项价税合计 **8,050,908.58 元**
#   旧规则"取全文绝对值最大的锚定金额"⇒ **分母被当成涉案金额** ⇒
#   敞口 54.10 万（实际约 5.75 万），**虚高 8.4 倍**。
#
# 根因：`_AMOUNT_PAT` 只保证"数字紧跟关键词"，**没有任何"这个金额是不是本项涉案金额"的语义约束**。
#   ⇒ 通用缺陷：凡报告里出现比涉案金额更大的**参照量**（占比分母、年度合计、开票总额、上年同期），
#     税额敞口都会被系统性放大。
#
# 修法（数据驱动，全行业/全疑点通用，**新增同类只需在本表加一行**）：
#   ① **涉案类语境**（分子=/差额/少缴/未匹配/红冲…）→ 优先；
#   ② **参照量语境**（分母/占比/占同期/剔除…后/年度合计/平均…）→ 降权；
#   ③ 分子标记压过分母标记（"分式"表述里，"分子"侧才是本项涉案量）；
#   ④ 仍无正分候选 ⇒ **返回 None**（如实"未量化"，宁缺勿错）；
#      仅当候选**唯一**时采用（无歧义），多候选且判不出主次 ⇒ **不猜**。
_KW_SUBJECT = (
    "涉及金额", "涉案金额", "涉及税额", "未匹配金额", "差额", "差异额", "差异", "缺口",
    "少计收入", "少计销项", "少计", "少缴", "多抵", "虚增", "虚列", "隐匿收入",
    "未申报收入", "未开票收入", "调整金额", "成本列支金额",
    "红字", "作废", "冲减", "冲销", "转出", "损失",
)
_KW_DENOM = (
    "分母", "占比", "占同期", "占全年", "占当年", "剔除后", "剔除红字后", "剔除蓝字后",
    "合计数", "年度合计", "全年合计", "总额", "总计", "平均", "注册资本", "资产总额",
    "收入总额", "开票总额", "销项价税合计", "同期蓝字", "上年同期",
    # ★★ 2026-10-06（用户评语 #3-①）：**红冲/作废类**的涉案金额是"红冲本身"，
    #   而"蓝字开票额"只是**分母**。实测报告把 8,050,908.58（全部蓝字销项）
    #   全额价税分离后乘 6% 估算增值税 ⇒ 严重高估（红冲 ≠ 全部蓝字未申报）。
    #   ⇒ 把"蓝字/开票额"这类**参照量**明确降权，取数时优先红冲/作废金额本身。
    "蓝字", "剔除蓝字", "开票额",
)
_KW_NUMER = ("分子",)
#: **本项涉案量**的语义标记（红冲/作废金额本身就是涉案量，不是分母）
_KW_SUBJECT_FOR_ANCHOR = ("红冲", "红字", "作废", "冲减", "差额", "少缴", "超限", "不得扣除")
_CTX_WIN = 48          # 语境窗口：匹配片段前后各取该字符数
#: 子句分隔符 —— "分子/分母"这类标记**就近才有效**：
#   "（分子=销项红字/作废价税合计；分母=剔除红字后的销项价税合计 8,050,908.58 元"
#   若不切子句，48 字窗口会把"分子="也算进来 ⇒ 分母被误判为分子（实测踩过）。
_CLAUSE_SEP = ("；", ";", "（", "(", "）", ")", "。", "\n", "\r")
#: ★★ 2026-10-06（用户在疑点1 上实测出的**真 bug**）：
#   **同一子句里「分子=…，分母=…」并存时，必须按"离金额最近的那个标记"判分子/分母。**
#   事故：`win` 里同时含"分子="与"分母="，而 `_amount_score` 先用 `any(分子 in win)` 判分子
#   ⇒ **分母 8,050,908.58（全部蓝字销项）被判成分子**，与真分子 1,015,900.00 并列最高分，
#   再按"金额大者优先"取胜 ⇒ 增值税被按全部蓝字开票额估算成 7,595,196.77（虚高 13 倍）。
#   除非另行说明，"…， 分母=…"里的金额就是**参照量**。
_DENOM_MARK = ("分母",)
_NUMER_MARK = ("分子",)
#: "价税合计"类锚点 ⇒ 该金额是**含税**口径，须价税分离后才能进入 estimate_tax
_INCLUSIVE_KW = (
    "价税合计", "含税", "价税合计额",
    # ★★ 2026-10-06（用户评语 #3-②）：**资金/流水/余额类**金额天然是**含税**口径
    #   （它们来自含税的银行收付），若不价税分离，增值税测算会与报告口径声明自相矛盾
    #   （实测：疑点24 银行流水余额滚动差异 29,686.30 × 6%，未分离）。
    "银行流水", "流水余额", "余额滚动", "对公账户", "资金收付", "收付差额",
)


#: 含税口径标注的**前视边界**（★★ 2026-10-08，P0-1）。
#   事故：疑点1 的涉案金额写作「销项红字/作废 1,015,900.00 **元**，占同期销项蓝字开票额 12.6%
#   （分子=销项红字/作废**价税合计**；…」——"价税合计"这个**含税口径标注写在数字之后**。
#   旧实现只扫匹配片段本身 ⇒ 认不出含税 ⇒ 未价税分离 ⇒ 把**含税价税合计当成增值税额**
#   （1,015,900 直接算增值税，高估 5~7 倍）。
#   边界规则：只前视到**本句/本子句结束**——遇句末（。！？\n）或子句分隔（；;）即停，
#   最多 `_LOOKAHEAD_MAX` 字符；否则会把**下一个**金额的"价税合计"误算到本金额头上。
_LOOKAHEAD_MAX = 60
_LOOKAHEAD_STOP = ("。", "！", "？", "\n", "；", ";")


def _clause(win: str) -> str:
    """取窗口里的**最后一段子句**（分式/并列表述里，分子分母标记就近才有效）。"""
    idx = -1
    for s in _CLAUSE_SEP:
        idx = max(idx, win.rfind(s))
    return win[idx + 1:] if idx >= 0 else win


def _lookahead_clause(text: str, start: int) -> str:
    """取金额**之后**、同一句/子句内的文本（含税口径标注常写在数字之后）。

    见 `_LOOKAHEAD_STOP`：遇句末或子句分隔即停（避免跨到下一个金额的口径语上）。
    """
    seg = text[start:start + _LOOKAHEAD_MAX]
    idx = len(seg)
    for s in _LOOKAHEAD_STOP:
        i = seg.find(s)
        if i >= 0:
            idx = min(idx, i)
    return seg[:idx]


def _amount_score(win: str) -> int:
    """给一个锚定金额打"它是不是本项涉案金额"的分（正=涉案、负=参照量）。

    ★★ 2026-10-06：调用方必须先把 `win` 截到**离金额最近的那个「分子/分母」标记之后**
      （见 `_trim_to_nearest_mark`）——否则同一子句里"分子=…，分母=…"并存时，
      分母会被误判成分子（实测虚高 13 倍）。
    """
    is_numer = any(k in win for k in _KW_NUMER)
    is_denom = (not is_numer) and any(k in win for k in _KW_DENOM)
    if is_numer:
        return 3 + (2 if any(k in win for k in _KW_SUBJECT) else 0)
    if is_denom:
        return -3
    return 2 if any(k in win for k in _KW_SUBJECT) else 0


def _trim_to_nearest_mark(win: str) -> str:
    """只保留**离金额最近**的那个「分子/分母」标记之后的内容（无标记则原样返回）。"""
    idx = -1
    for _k in (_NUMER_MARK + _DENOM_MARK):
        idx = max(idx, win.rfind(_k))
    return win[idx:] if idx >= 0 else win


# ★★ 2026-10-04（用户复核疑点5：超限 **211.21 万**已算出却报"未量化"）：
#   **表内金额的"锚"是列名** —— 明细表的列名（如"超限金额（元）"）本身就是口径声明，
#   比正文里的"业务招待费411,111.53元"更适合做锚。旧实现有两处断点：
#     ① `extract_amount_from_problem` 只扫 `detail_table`（**单数**），而明细表实际挂在
#        `narrative_paragraphs[].detail_tables`（**复数**）⇒ 表内金额**完全不在扫描范围**；
#     ② 即使扫到，行被压成 `" ".join(values)` 平串，而正则要求"关键词 + 数字 + **元**"
#        （列名在数字**之前**："超限金额（元） 377,927.53"）⇒ 也匹配不上。
#   ⇒ 两处一起修：**列感知**取数（列名即口径）+ 覆盖复数表；
#      并作为**文本锚定的补充通道**（文本已能判定时不动 ⇒ 零回归，疑点1 的语义锚定结果保持不变）。
# ★ 只认**单向命题型**列名（超限/不得扣除/应调增/准予结转/差额/差异/合计…）：
#   纯"金额（元）"这类**明细行**列**不得**作涉案金额 —— 逐笔明细里"最大的一笔"
#   恰恰不是本项涉案量（实测：疑点3 会取到单笔最大收款 1,611,200 而非累计差额；
#   关联交易会取到单张最大发票 943,396.23）。明细行是**证据**，不是**涉案金额**。
_TABLE_HIT_COLS = ("超限", "不得扣除", "应调增", "调增", "准予结转",
                   "差额", "差异", "合计", "总计")


def _cands_from_tables(p: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从明细表（含复数 `detail_tables`）**按列名**生成金额候选（列名即口径）。

    只采信**单向命题型**列名（见 `_TABLE_HIT_COLS`）：该列本身就是"本项要算的那个量"
    （超限额/应调增额/差额/合计）；纯"金额（元）"明细列一律不采（明细行≠涉案金额）。
    多行时另给"**列合计**"候选并压过单行（当期应调增＝各分项之和）。
    """
    tables: List[Dict[str, Any]] = []
    _dt = p.get("detail_table")
    if isinstance(_dt, dict):
        tables.append(_dt)
    for _np in (p.get("narrative_paragraphs") or []):
        if isinstance(_np, dict):
            for _t in (_np.get("detail_tables") or []):
                if isinstance(_t, dict):
                    tables.append(_t)
    out: List[Dict[str, Any]] = []
    for t in tables:
        cols = [str(c) for c in (t.get("columns") or [])]
        rows = [r for r in (t.get("rows") or []) if isinstance(r, dict)]
        if not cols or not rows:
            continue
        for c in cols:
            if not any(k in c for k in _TABLE_HIT_COLS):
                continue
            _vals = []
            for r in rows:
                v, ok = to_number_checked(r.get(c))
                if ok and v is not None and abs(v) >= _MIN_AMOUNT:
                    _vals.append(abs(round(float(v), 2)))
            if not _vals:
                continue
            _ttl = str(t.get("title") or "明细表")
            for v in _vals:
                out.append({"amount": v, "raw": format(v, ",.2f"),
                            "context": "%s「%s」" % (_ttl[:16], c[:16]),
                            "clause": "%s「%s」逐行" % (_ttl[:16], c[:16]),
                            "inclusive": False, "score": 4})
            if len(_vals) >= 2:
                out.append({"amount": round(sum(_vals), 2),
                            "raw": format(sum(_vals), ",.2f"),
                            "context": "%s「%s」列合计（%d 行）" % (_ttl[:16], c[:16], len(_vals)),
                            "clause": "%s「%s」合计" % (_ttl[:16], c[:16]),
                            "inclusive": False, "score": 5})
    return out


def _pick_best(cands: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """候选筛选（唯一实现）：先按语义分，再按绝对值大小；无正分且多义 ⇒ 不猜。

    ★★ 2026-10-06（用户第 2 批 疑点1）：**负分候选（明确的"参照量/分母"）永远不能当涉案金额**。
      事故：正文里只有「价税合计8,050,908.58元」一个候选（且其子句标着"分母="），
      旧实现"只有一个候选就直接采用" ⇒ 把**分母**当成本项涉案金额，
      再价税分离乘税率 ⇒ 增值税虚高 13 倍（7,595,196.77）。
      口径：只有一个候选时，**只有它不带参照量标记**才采用；否则如实返回 None（→ 未量化）。
    """
    if not cands:
        return None
    _pos = [c for c in cands if c["score"] > 0]
    if _pos:
        return max(_pos, key=lambda c: (c["score"], c["amount"]))
    if len(cands) == 1:
        return cands[0] if cands[0]["score"] >= 0 else None
    return None


def extract_amount(text: Any) -> Optional[Dict[str, Any]]:
    """从文本里**语义锚定**地取一个代表金额；取不到返回 None（不猜）。

    返回 {"amount", "raw", "context", "inclusive", "score", "clause", "clue_only"}；
    `inclusive=True` 表示锚定语境是"价税合计/含税"（须用 `normalize_basis` 价税分离）。
    `inclusive` 的判定范围是**本金额自己的子句**（数字之前）＋**有界前视**（数字之后到本句/
    本子句结束，见 `_lookahead_clause`）——因为含税标注也常写在数字**之后**。
    """
    if not isinstance(text, str) or not text:
        return None
    cands: List[Dict[str, Any]] = []
    for m in _AMOUNT_PAT.finditer(text):
        raw = m.group(1)
        val, ok = to_number_checked(raw)
        if not ok or val is None or abs(val) < _MIN_AMOUNT:
            continue
        # 语境只取**匹配之前**的窗口 + 本片段本身：
        #   若把片段**之后**的文字也算进来，结尾的"；另有…"会把子句切到"另有取得"上（实测踩过）。
        _pre = text[max(0, m.start() - _CTX_WIN): m.start()]
        win = _trim_to_nearest_mark(_clause(_pre) + m.group(0))
        frag = m.group(0)
        # ★★ 2026-10-08（P0-1）：**含税口径的判定范围 = 本金额自己的子句 + 有界前视**。
        #   旧实现只扫 `frag`（匹配片段本身）⇒ 「价税合计」写在数字**之后**时认不出 ⇒
        #   未价税分离 ⇒ 含税金额直接乘税率（实测把含税价税合计当成增值税额，高估 5~7 倍）。
        #   现口径：`win`（本金额所在子句，含数字之前的口径语）
        #           ＋ `_lookahead_clause`（数字之后到本句/本子句结束）。
        _scope = win + _lookahead_clause(text, m.end())
        cands.append({
            "amount": abs(round(float(val), 2)),
            "raw": raw,
            "context": frag[:40],
            # 供闸门/自检回溯：锚定所处的**子句**（含分子/分母/参照量标记，context 里看不到）
            "clause": win[:120],
            "inclusive": any(k in _scope for k in _INCLUSIVE_KW),
            "score": _amount_score(win),
            # ★ 2026-10-06（用户第 2 批 疑点1）：**该金额只是"异常线索"、不代表已确认少缴**
            #   —— 红冲/作废金额本身不等于少缴税款（红冲可能是法定更正）。
            #   下游据此把税额标注为「仅按红冲金额上界估算」，避免把线索当结论。
            "clue_only": any(k in win for k in _KW_SUBJECT_FOR_ANCHOR),
        })
    return _pick_best(cands)


def extract_amount_from_problem(p: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """在一项「具体问题」的检查记录（叙述段 / **单数与复数**明细表）中锚定金额。

    ★ 取数优先级（不变更既有结果）：**文本锚定优先**；文本判不出（无正分/多义）时，
    才走**表内锚定**（`_cands_from_tables`，列名即口径）——这样既修好"表里有数却报未量化"，
    又**不会**改变已能判定的疑点（如疑点1 的语义锚定结果）。
    """
    if not isinstance(p, dict):
        return None
    chunks: List[str] = []
    for np in (p.get("narrative_paragraphs") or []):
        if not isinstance(np, dict):
            continue
        chunks.append(str(np.get("text") or ""))
        chunks.append(" ".join(str(b) for b in (np.get("bullets") or [])))
        chunks.append(str(np.get("tail") or ""))
    for row in ((p.get("detail_table") or {}).get("rows") or []):
        if isinstance(row, dict):
            chunks.append(" ".join(str(v) for v in row.values()))
    _text_am = extract_amount("\n".join(chunks))
    if _text_am is not None:
        return _text_am
    return _pick_best(_cands_from_tables(p))


def normalize_basis(am: Optional[Dict[str, Any]],
                    rate_ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """把锚定金额换算成 `estimate_tax` 要求的**不含税涉案金额**。

    ★ 口径唯一权威 = `engine.tax_rates.to_exclusive`（不另写一份换算）。
    仅当锚定语境明确为「价税合计/含税」时才换算；
    **取不到适用税率 ⇒ 不换算**，并在 `scope_note` 里如实说明（不猜、不静默顶替）。

    返回 {"amount": float|None, "scope_note": str}。
    """
    if not isinstance(am, dict):
        return {"amount": None, "scope_note": ""}
    amt = am.get("amount")
    if amt is None:
        return {"amount": None, "scope_note": ""}
    if not am.get("inclusive"):
        return {"amount": amt, "scope_note": ""}
    rate = None
    if isinstance(rate_ctx, dict):
        rate = rate_ctx.get("vat_rate")
    if not rate:
        return {"amount": amt,
                "scope_note": ("锚定金额为**含税**（价税合计）口径 %s 元，"
                               "但本轮未取得适用增值税税率，**未做价税分离**"
                               % format(float(amt), ",.2f"))}
    try:
        from engine.tax_rates import to_exclusive as _to_ex
        ex = round(float(_to_ex(float(amt), float(rate))), 2)
    except Exception:
        return {"amount": amt,
                "scope_note": "含税金额价税分离失败，按原值进入测算（口径待复核）"}
    return {"amount": ex,
            "scope_note": ("锚定金额为**含税**（价税合计）%s 元，按适用税率 %d%% "
                           "价税分离为**不含税** %s 元"
                           % (format(float(amt), ",.2f"), int(round(float(rate) * 100)),
                              format(ex, ",.2f")))}


# 税率表（单一出处）：税种 → (默认税率, 口径说明)。
# ★ 2026-09-29（点评整改 P0-4）：默认税率只作**取不到语境时的兜底**。
#   实测事故：对销项全为服务费品名的企业按 13% 测增值税、按 25% 测企业所得税，
#   把敞口 66.77 万系统性虚高 2~3 倍。正确做法是先由 infer_rate_context() 从销项
#   品名/有效税率与净利润推断适用税率，再进入测算。
_RATES: Dict[str, tuple] = {
    "增值税": (0.13, "未取得销项税额明细，按 13% 法定上限口径测算；实际以票面适用税率（13%/9%/6%/3%）复核"),
    "企业所得税": (0.25, "按 25% 法定税率测算；小型微利企业另有优惠，实际以汇算清缴为准"),
    "个人所得税": (0.03, "按工资薪金/劳务报酬 3% 起点档测算；实际按超额累进税率计算"),
    "印花税": (0.0003, "按购销合同 0.03% 测算；实际按对应税目税率核对"),
    # ★★ 2026-10-04（疑点10-21 合并批次 ⑫）：随征三税此前**硬编码 0.12**（见 estimate_tax
    #   底部"增值税附加"分支）：税率口径、税种名、附注三处各写一份 ⇒ 改一处必漏两处。
    #   现统一登记到本表（税率单一出处），底部分支改为从本表取值。
    "城市维护建设税": (
        0.07,
        "按市区 7% 测算；县城/建制镇 5%、其他地区 1%，以企业实际所在地为准"
        "（《中华人民共和国城市维护建设税暂行条例》第二条）"),
    "教育费附加": (0.03, "按增值税额的 3% 测算（《征收教育费附加暂行规定》第三条）"),
    "地方教育附加": (0.02, "按增值税额的 2% 测算（《地方教育附加征收使用管理办法》第三条）"),
    "城建税及教育费附加": (
        0.12,
        "按增值税额的 12%（城建税 7%＋教育费附加 3%＋地方教育附加 2%）合并测算；"
        "本项发现已单独列示「城市维护建设税」时不再重复加计"),
    # ★★ 2026-10-04（同批 ⑫）：**非比例/从量税种一律登记 rate=None** ——
    #   这不是"没登记"，而是**如实承认本轮取不到适用税率**：既不用默认值顶替（避免虚增敞口），
    #   也不静默跳过（旧行为：静默跳过 ⇒ 报告里既不说量化了、也不说未量化，读者无从察觉）。
    #   登记后走 estimate_tax 的"未量化披露"分支，按税种给出"为什么算不出来"。
    "土地增值税": (None, "四级超率累进税率（30%~60%），须按增值额与扣除项目分项计算；"
                     "本轮未取得分项目数据 ⇒ 未量化"),
    "房产税": (None, "从价计征 1.2%（原值减除 10%~30%）或从租计征 12%（另有个人住房优惠），"
                 "适用口径取决于计税方式 ⇒ 未量化"),
    "城镇土地使用税": (None, "定额税率（按大/中/小城市与土地等级每平方米年税额），须先定税额标准 ⇒ 未量化"),
    "车船税": (None, "按车船种类、机驶吨位定额征收（年基准税额），须先定税目税额 ⇒ 未量化"),
    "契税": (None, "3%~5% 幅度税率（各地在幅度内确定），须按成交与当地规定核定 ⇒ 未量化"),
    "消费税": (None, "按应税消费品税目税率（如高档化妆品 15%、成品油等）分别计征 ⇒ 未量化"),
    "耕地占用税": (None, "定额税率（按地区人均耕地与税额幅度）⇒ 未量化"),
    "资源税": (None, "从价或从量，按税目幅度税率 ⇒ 未量化"),
    "环境保护税": (None, "按污染当量数 × 适用税额（大气/水按当量、固废与噪声按量）⇒ 未量化"),
    "车辆购置税": (None, "按应税车辆售价（不含税）10% 计征 ⇒ 未量化"),
    "烟叶税": (None, "按收购金额 20% 计征 ⇒ 未量化"),
    "船舶吨税": (None, "按净吨位定额（吨税税目表）⇒ 未量化"),
    "关税": (None, "按税则号列适用税率（最惠国/协定/特惠），须以报关口径核定 ⇒ 未量化"),
    "文化事业建设费": (0.03, "按广告业销售额（不含税）3% 计征（《财政部 税务总局关于文化事业建设费有关政策的通知》）"),
    # ★ 2026-10-15：批次规则（BATCH-005 征管专题）登记税种「其他税费」——
    #   它不是单一税种而是**归类名**，无法给出统一税率 ⇒ 如实登记 rate=None 走"未量化"披露，
    #   既不虚增敞口、也不静默消失（闸门 `check_*` 要求登记的税种必须可量化或明确未量化）。
    "其他税费": (None, "为**税种归类名**（含城建税、附加、印花税等多项），"
                     "无统一适用税率，须按具体税种分别测算 ⇒ 未量化"),
}

# 「本系统分析哪些税种」的唯一权威 = 红线库 `taxes` 字段（tax_redlines 单点维护）。
# 用它区分「真实存在但税率未登记 ⇒ 必须披露未量化」与「压根不存在的税名 ⇒ 静默忽略」。
# 「本系统不参与潜在税额敞口测算」的税种（**本轮不参与**，如实登记理由，不用默认值顶替）。
# ★ 2026-10-04（同批 ⑫）：这是**显式白名单之外的显式黑名单**，作用是让"为什么这项没数"可复核；
#   新增同类对象只加一行（不加 ⇒ 闸门报错，不会静默）。
_NON_ESTIMABLE_TAXES: Dict[str, str] = {
    "住房公积金": "属住房公积金缴存事项，非税务机关征收的税，不进入税额敞口口径",
    "社会保险费": "属社保征收口径（税务代征），与本项税额影响不同层，不进入税额敞口合计",
    "工会经费": "属工会经费拨缴（工会法调整），非税，不进入税额敞口合计",
    "残疾人就业保障金": "属政府性基金（非税），单列政府性基金口径，不混入税额敞口",
    "水利建设基金": "属政府性基金（非税），单列政府性基金口径，不混入税额敞口",
    "出口退税": "属退（抵）税事项（冲减销项），不是潜在补税敞口；须按免抵退办法单独计算",
    "进口环节增值税": "属进口环节海关代征，发生在本企业外的报关环节，不按本项涉案金额测算",
    "进口环节消费税": "同上（进口环节海关代征消费税）",
}


def tax_rate_table() -> Dict[str, Dict[str, object]]:
    """税率表（**唯一权威** = `_RATES`）的**只读**视图，供多税种深度模型页展示。

    返回 `{税种: {"rate": 默认税率或 None, "note": 口径说明, "quantifiable": bool}}`。
    ★ `rate is None` **不是"没登记"**，而是"如实承认本轮取不到适用税率"（未量化），
      调用方必须照此展示，**不得**用默认值顶替。
    """
    out: Dict[str, Dict[str, object]] = {}
    for tax, pair in _RATES.items():
        rate, note = (pair if isinstance(pair, (list, tuple)) and len(pair) == 2
                      else (None, ""))
        out[str(tax)] = {"rate": rate, "note": str(note),
                         "quantifiable": rate is not None}
    return out


def non_estimable_taxes() -> Dict[str, str]:
    """返回"本系统不参与敞口测算"的税种及理由（口径可复核，禁静默）。"""
    return dict(_NON_ESTIMABLE_TAXES)


_KNOWN_TAX_CACHE: List[str] = []


def known_tax_types() -> set:
    """返回红线库登记过的税种集合（唯一权威：tax_redlines 的 taxes 字段）。"""
    global _KNOWN_TAX_CACHE
    if _KNOWN_TAX_CACHE:
        return set(_KNOWN_TAX_CACHE)
    try:
        from engine.tax_redlines import REDLINES as _RLS
        _set: List[str] = []
        for _rl in (_RLS or []):
            for _t in (_rl.get("taxes") or []):
                if str(_t) not in _set:
                    _set.append(str(_t))
        _KNOWN_TAX_CACHE = _set
        return set(_set)
    except Exception:
        return set()

# 增值税税率档（按销项有效税率落档）
_VAT_BRACKETS = (
    (0.028, 0.036, 0.03), (0.055, 0.066, 0.06),
    (0.085, 0.098, 0.09), (0.115, 0.145, 0.13),
)
# 小型微利企业临界值（应纳税所得额≤300万、从业人数≤300、资产总额≤5000万）
_SMALL_MICRO_PROFIT = 3_000_000.0
_SMALL_MICRO_STAFF = 300
_SMALL_MICRO_ASSETS = 50_000_000.0
# 个税基本减除费用（年度）
_PIT_BASIC_DEDUCTION = 60_000.0
#: 企业所得税**法定税率**（上界口径）。小微优惠是有前提的（见 `evaluate_small_micro`）：
#: 三项条件未逐项**取得并满足**时一律回到本税率，避免按 5% 低估敞口。
_CIT_STATUTORY_RATE = 0.25
#: 小微优惠税率（仅当 `evaluate_small_micro()` 判定 verified 时使用）
_CIT_SMALL_MICRO_RATE = 0.05

#: 小型微利企业三项**法定条件**（★ 单一权威：新增/调整条件只改本表）。
#:   (取数字段名, 中文名, 法定上限, 是否要求严格为正)
_SMB_CONDITIONS: tuple = (
    ("employee_count", "从业人数", float(_SMALL_MICRO_STAFF), False),
    ("total_assets", "资产总额", float(_SMALL_MICRO_ASSETS), False),
    ("net_profit", "应纳税所得额", float(_SMALL_MICRO_PROFIT), True),
)


def evaluate_small_micro(employee_count=None, total_assets=None,
                         net_profit=None) -> Dict[str, Any]:
    """判定企业是否**已核实**符合小型微利企业条件（★ 唯一权威，禁止别处再判一次）。

    法定条件三项（财税〔2023〕12 号等）：从业人数≤300、资产总额≤5000 万、
    应纳税所得额≤300 万；另须从事国家非限制和禁止行业。

    ★★ 判据是「**取到数** 且 **满足**」——任一项**未取得**即 `verified=False`：
        - 旧实现把"人数未取得"当成 `staff_ok=True`（未知＝通过）⇒ **未验证就按 5% 估算**，
          实测把 2,112,137.70 的敞口按 5% 算成 105,606.89，**低估 5 倍**。
        - 用户第 3 批 任务3 明确：「企业所得税**必须考虑小型微利条件**；
          **未验证小微条件时不得直接按 5% 估算**」。
        - 本系统口径：未验证 ⇒ 一律回到法定 25% 上界并如实标注（**宁可给上界，
          不给低估**），由企业补充资料后核减。

    ★ 应纳税所得额以**账面净利润为可获得代理**（真正的应纳税所得额须经纳税调整）；
      代理不等于汇算清缴认定值，故文案必须声明"须经纳税调整后确定"。

    返回 {"verified": bool, "missing": [中文名…], "failed": [中文名…],
          "detail": [{field,label,limit,got,obtained,ok}…]}
    """
    detail: List[Dict[str, Any]] = []
    missing: List[str] = []
    failed: List[str] = []
    values = {"employee_count": employee_count, "total_assets": total_assets,
              "net_profit": net_profit}
    for _field, _label, _limit, _strict_pos in _SMB_CONDITIONS:
        _raw = values.get(_field)
        _num = None
        if _raw is not None:
            try:
                _num = float(to_number_checked(_raw)[0])
            except Exception:
                _num = None
        _obtained = _num is not None
        _ok = False
        if _obtained:
            _ok = (_num > 0 and _num <= _limit) if _strict_pos else (0 <= _num <= _limit)
        if not _obtained:
            missing.append(_label)
        elif not _ok:
            failed.append(_label)
        detail.append({"field": _field, "label": _label, "limit": _limit,
                       "got": _num, "obtained": _obtained, "ok": _ok})
    return {"verified": (not missing and not failed),
            "missing": missing, "failed": failed, "detail": detail}


def smb_upper_bound_note(missing: Optional[List[str]] = None) -> str:
    """「按法定 25% 上界估算」的标准文案（★ 单一权威，供 ctx 与 estimate_tax 共用）。"""
    _miss = "、".join(missing or []) or "从业人数/资产总额/应纳税所得额"
    return ("未验证小型微利条件（%s 未逐项取得并满足）⇒ **按法定 %d%% 税率上界估算**；"
            "若经核实符合小型微利条件，实际影响将显著低于本数。"
            "应纳税所得额须经纳税调整后确定，本轮未取得；"
            "未考虑亏损弥补与以前年度结转。" % (_miss, int(_CIT_STATUTORY_RATE * 100)))


def smb_scope_note(ctx: Optional[Dict[str, Any]] = None) -> str:
    """口径声明 ④ 小型微利条件 → 标准文案（★ 单一权威，唯一数据源 `evaluate_small_micro()`）。

    ★★ 事故（2026-10-08，门禁 B7「同一事实多处表述相反」）：本处**曾硬编码**
       「企业所得税若按小型微利口径估算，本轮**未取得**从业人数、资产总额、应纳税所得额，
       **未验证**是否符合小型微利企业条件」——而当轮三项**实际均已取得**（见 `cit_note`
       "三项均已取得且未超临界值"）⇒ 同一份报告的 `tax_impact_summary.note` 与
       `confirmed_problems[].tax_impact.items[].note` 对**同一事实**表述相反（用户可见）。

    根因：**"是否已取得/是否已验证"这一事实被两处各写一套**（本处硬编码 + `cit_note` 实时判定）。
    ⇒ 收敛口径：本函数**只读** `ctx`（= `infer_rate_context()` 产物，其 `smb_verified`
       来自唯一权威 `evaluate_small_micro()`），按其**实际判定结果**生成声明：
         - verified=True  ⇒ 如实说"已按小微优惠口径测算（三项已取得且未超临界值）"；
         - verified=False ⇒ 如实说"未验证 ⇒ 按法定 25% 上界"；
         - 取不到 ctx      ⇒ **不臆断任何一项是否已取得**，只指向权威章节，避免与 cit_note 分叉。
    """
    _v = None
    if isinstance(ctx, dict):
        _v = ctx.get("smb_verified")
    if _v is True:
        return ("④ **未考虑**附加税减半征收等其他税收优惠；企业所得税已按**小型微利**优惠口径"
                "测算（从业人数/资产总额/账面净利润三项均已取得且未超临界值，"
                "判定见「适用税率语境」）；应纳税所得额须经纳税调整后确定，本轮以账面净利润为代理。")
    if _v is False:
        return ("④ **未考虑**附加税减半征收、小微企业等税收优惠；企业所得税**未验证**符合小型微利"
                "企业条件（三条件未逐项取得并满足）⇒ **按法定 %d%% 税率上界**估算；"
                "判定见「适用税率语境」，若经核实符合条件，实际影响将显著低于本数。"
                % int(_CIT_STATUTORY_RATE * 100))
    return ("④ **未考虑**附加税减半征收、小微企业等税收优惠；企业所得税的小型微利条件判定"
            "见「适用税率语境」，本报告按该判定的实际口径测算。")


def infer_rate_context(sal_invs=None, net_profit=None, employee_count=None,
                       total_assets=None) -> Dict[str, Any]:
    """推断本企业的适用税率语境（单一构造点，pipeline 调用一次存入 comprehensive）。

    返回 {"vat_rate": float|None, "vat_note": str,
          "cit_rate": float|None, "cit_note": str, "smb_verified": bool}。
    取不到的维度返回 None（由 estimate_tax 走兜底并如实注明），绝不猜。
    ★ 企业所得税档位**只由 `evaluate_small_micro()` 判定**（唯一权威）：
      verified ⇒ 5%；已取得但不满足或未取得 ⇒ 法定 25% 上界（并说明缺哪项）。
    """
    ctx: Dict[str, Any] = {"vat_rate": None, "vat_note": "", "cit_rate": None,
                           "cit_note": "", "smb_verified": False}
    # ── 增值税：按销项发票有效税率（税额/不含税金额）落档 ──
    try:
        from engine.numparse import amount_of as _amount_of
        amt_sum = 0.0
        tax_sum = 0.0
        for inv in (sal_invs or []):
            if not isinstance(inv, dict):
                continue
            a = _amount_of(inv)
            t = (to_number_checked(inv.get("tax_amount"))[0]
                 or to_number_checked(inv.get("税额"))[0]
                 or to_number_checked(inv.get("tax"))[0]
                 or 0.0)
            if a > 0:
                amt_sum += a
                tax_sum += t
        if amt_sum > 0:
            eff = tax_sum / amt_sum
            for lo, hi, rate in _VAT_BRACKETS:
                if lo <= eff <= hi:
                    ctx["vat_rate"] = rate
                    ctx["vat_note"] = (f"按销项发票有效税率 {rate*100:.0f}% 测算"
                                       f"（销项税额合计/不含税金额 = {eff*100:.1f}%，落 {rate*100:.0f}% 税率档）")
                    break
            if ctx["vat_rate"] is None:
                ctx["vat_note"] = f"销项有效税率 {eff*100:.1f}% 未落入常见税率档，按兜底口径测算"
    except Exception:
        pass
    # ── 企业所得税：小微判定（★ 唯一权威 `evaluate_small_micro`；不再在本函数内自行判 ──
    #    "未知即通过"的旧口径已废弃，见该函数 docstring）──
    try:
        _smb = evaluate_small_micro(employee_count=employee_count,
                                    total_assets=total_assets, net_profit=net_profit)
        ctx["smb_verified"] = bool(_smb.get("verified"))
        _np_val = to_number_checked(net_profit)[0] if net_profit is not None else None
        if _smb.get("verified"):
            ctx["cit_rate"] = _CIT_SMALL_MICRO_RATE
            ctx["cit_note"] = (
                "按小型微利企业优惠口径 %d%% 测算（从业人数/资产总额/账面净利润三项"
                "均已取得且未超临界值）；**应纳税所得额**须经纳税调整后确定，本轮以账面"
                "净利润为代理；**未考虑**亏损弥补与以前年度结转（若可弥补则实际影响更低）。"
                % int(_CIT_SMALL_MICRO_RATE * 100))
        elif _np_val is not None and float(_np_val) > 0:
            ctx["cit_rate"] = _CIT_STATUTORY_RATE
            _n_miss = list(_smb.get("missing") or [])
            _n_fail = list(_smb.get("failed") or [])
            ctx["cit_note"] = smb_upper_bound_note(_n_miss) + (
                ("；其中已取得但已超临界值：" + "、".join(_n_fail)) if _n_fail else "")
    except Exception:
        pass
    return ctx


# ★★ 2026-10-04（疑点4 D12 修复）：**税种 × 基数性质**相容性（单一权威）。
#   事故：RL-INC-002（个人账户收取经营性款项：公私混同隐匿收入）声明含增值税/附加，
#   而 `estimate_tax` 对每个税种用**同一个 amount × 税率**、从不校验基数性质
#   ⇒ 工资差额 928,000 被当成应税收入 × 6% = 55,680，再随征 12% 出附加 6,681.60
#   ⇒ **凭空 62,361.60**（发工资不产生销项税）。
#   本表只声明"各税种的基数必须是什么性质"；性质不符 ⇒ **不估**（如实标注），
#   **不删税种声明** —— 隐匿收入确实可能牵涉增值税，删掉会掩盖真实风险。
_TAX_BASE_NATURE: Dict[str, tuple] = {
    "增值税": ("sales",),
    "城建税及教育费附加": ("sales",),
    "城市维护建设税": ("sales",),
    "教育费附加": ("sales",),
    "地方教育附加": ("sales",),
    "企业所得税": ("profit",),
    # ★★ 2026-10-16 修（实测缺陷）：个税的计税基数**随所得项目而变** ——
    #   工资薪金（wage）、股息红利/经营所得（profit）、财产转让（contract）……
    #   原表写死单个 `"wage"` ⇒ 一旦事实是「股东分红未代扣个税」（基数为利润分配=profit），
    #   相容性判据就报"基数口径与税种要求不符"，而那一项**本该照 20% 正常测算**
    #   （实测：报告产物 seq=8 因此被闸门判 ERROR，且金额还被写成 0.0 = 漏计风险）。
    #   ⇒ 改为**可接受性质集合**（成员判据），既保留 D12 的本意（工资差额不得算增值税），
    #     也不把"个税只认工资"这一错误口径固化。
    "个人所得税": ("wage", "profit"),
    "印花税": ("contract",),
}

#: 个人所得税**按所得项目**取税率 —— 比例税率与综合所得累进**不是一回事**，
#: 一律按工资薪金 3% 起点档测算会把股息红利（20%）低估约 6.7 倍。
#: 数据驱动：新增所得项目 ⇒ 加一行（**先命中者胜**，故特殊的写在前面）。
_PIT_RATE_BY_INCOME: tuple = (
    (("股息", "红利", "分红", "利润分配"), 0.20,
     "股息、红利所得适用 20% 比例税率（《中华人民共和国个人所得税法》第三条第三项）"),
    (("偶然所得",), 0.20,
     "偶然所得适用 20% 比例税率（《中华人民共和国个人所得税法》第三条第九项）"),
    (("财产转让", "股权转让", "转让所得"), 0.20,
     "财产转让所得适用 20% 比例税率（《中华人民共和国个人所得税法》第三条第五项）"),
)


def infer_pit_income(obj: Any) -> Dict[str, Any]:
    """按**所得项目**判定个人所得税税率与口径；判不出返回空字典（调用方走 `_RATES` 兜底）。

    ★ 与 `infer_amount_nature` 同一设计：判据全在数据表 `_PIT_RATE_BY_INCOME`（新增一行即可），
      **判不出就不改行为**（保持既有 3% 保守起点档 + 如实标注）。
    """
    _t = obj if isinstance(obj, str) else " ".join(
        str(obj.get(k) or "") for k in ("title", "finding_type", "detail", "suspect", "taxes")
    )
    for _kws, _r, _n in _PIT_RATE_BY_INCOME:
        for _k in _kws:
            if _k in _t:
                return {"rate": float(_r), "note": _n}
    return {}

#: 事实类型 → 基数性质（**按顺序**匹配，先命中者胜）。
#   ⚠ 账户/往来/公私混同类**必须排在销售类之前**：否则「公私混同隐匿收入」
#   会因含"收入"被判成 sales ⇒ 恰恰放过 D12 这类张冠李戴。
#   ⚠ 判不出就返回 ""（调用方不做判断）——**宁可漏判相容性，也不误不估**。
_FACT_NATURE_RULES: tuple = (
    (("公私混同", "个人账户", "私户", "个人卡", "往来", "借款", "挂账", "其他应收"), "non_sales"),
    (("工资", "薪酬", "薪金", "代发", "劳务"), "wage"),
    (("账外收入", "开票", "销项", "销售额", "收入"), "sales"),
    (("利润", "成本", "费用", "税前", "所得"), "profit"),
)


#: 「锚定金额**本身就是税额**」的事实特征词（进项/销项税额类差异）。
#   ★★ 2026-10-06（用户评语 #3-③）：这类金额**直接就是税额影响**，再乘税率是**逻辑错误**。
#   实测：疑点25 进项发票税额与认证税额差 4,501.34 元，被算成 4,501.34×6%=270.08；
#   若属进项不得抵扣/应转出，影响额**就该是 4,501.34**。
_TAX_AMOUNT_KW = (
    "进项税额", "销项税额", "可抵扣税额", "已抵扣税额", "应转出税额", "转出税额",
    "税额差额", "税额差异", "认证税额", "已纳税额", "抵扣税额",
)


def infer_amount_is_tax(obj: Any) -> bool:
    """锚定金额是否**本身就是税额**（是 ⇒ 影响额＝该金额，不再乘税率）。

    ★★ 2026-10-08（P0-1）：判据必须落在**该金额自己的语境**上，**不得扫整段叙述**。
      事故：疑点1 的 `suspect` 写「涉嫌通过红冲调节**销项税额**、配合受票方虚开后冲回」——
      这是在描述**手法**；旧实现把整段（title/finding_type/detail/suspect/taxes）拼起来做
      关键词命中 ⇒ 判成"本项金额即税额" ⇒ 把**含税价税合计 1,015,900.00** 直接当成增值税额
      （`rate="—"`，不再乘税率），敞口高估 5~7 倍。
      通用判据（全行业/全疑点通用，不针对某家公司）：
        **"这个金额是不是税额"是关于金额本身的陈述** ⇒ 证据只能是**金额所在的子句**
        （`extract_amount` 锚定出的 `clause` + `context`）；同一叙述里别处的"销项税额"
        （描述手法、后果、法条）不构成该金额的口径。
      金额锚不到 ⇒ **无从判断** ⇒ 返回 False（沿用本项目"宁可漏判，也不误不估"的口径）。
    """
    if isinstance(obj, str):
        # 裸字符串无"锚定"可言（且生产链路只传问题对象），沿用整串命中，行为不变。
        return any(_k in obj for _k in _TAX_AMOUNT_KW)
    if not isinstance(obj, dict):
        return False
    _am = extract_amount_from_problem(obj)
    if not isinstance(_am, dict):
        return False
    _scope = "%s %s" % (str(_am.get("clause") or ""), str(_am.get("context") or ""))
    if not _scope.strip():
        return False
    return any(_k in _scope for _k in _TAX_AMOUNT_KW)


def infer_amount_nature(obj: Any) -> str:
    """判定疑点的**基数性质**（sales/profit/wage/contract/non_sales）；判不出返回 ""。

    判据全部取自 `_FACT_NATURE_RULES`（数据驱动，新增事实类型只加一行）。
    判不出 ⇒ 返回 "" ⇒ 调用方不做相容性判断 ⇒ **行为与改动前完全一致**。
    """
    _t = obj if isinstance(obj, str) else " ".join(
        str(obj.get(k) or "") for k in ("title", "finding_type", "detail", "suspect", "taxes")
    )
    for _kws, _nat in _FACT_NATURE_RULES:
        for _k in _kws:
            if _k in _t:
                return _nat
    return ""


def estimate_tax(amount: Optional[float], taxes: Optional[List[str]],

                 rate_ctx: Optional[Dict[str, Any]] = None,
                 amount_nature: str = "",
                 amount_is_tax: bool = False,
                 pit_income: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """按税种测算潜在税额影响。amount 为不含税涉案金额；取不到→未量化。

    ★ 2026-09-29（点评整改 P0-4）：rate_ctx 由 infer_rate_context() 构造
    （pipeline 存于 comprehensive["tax_rate_context"]）；未提供时走 _RATES 兜底。
    个税：涉案金额低于 6 万元基本减除费用的，如实注明"无实际个税影响"，不计入合计。
    """
    if not amount or amount <= 0:
        return {
            "available": False, "basis": None, "items": [], "total": None,
            "note": "未量化：本项检查记录未给出可用于测算的明确金额，须补充资料后测算。",
        }
    rate_ctx = rate_ctx if isinstance(rate_ctx, dict) else {}
    taxes = [str(t) for t in (taxes or [])]
    items: List[Dict[str, Any]] = []
    vat_amount = 0.0
    for t in taxes:
        rate, note = _RATES.get(t, (None, ""))
        if rate is None:
            # ★★ 2026-10-04（同批 ⑫）：旧实现在这里 `continue` ⇒ 税种不在 _RATES 里就
            #   **静默消失**：既不计入敞口，也不说"未量化"，报告出现"有税种却没数"。
            #   现改为：红线库登记过的税种 ⇒ 如实登记一条 amount=None 的未量化项（可读可追溯）；
            #   未登记过的税名（如测试里的"不存在的税种"）⇒ 仍静默忽略。
            if t in known_tax_types():
                items.append({"tax": t, "rate": "", "amount": None,
                              "note": (note or "本税种适用税率本轮未取得，按未量化处理；不套用默认值测算。")})
            continue
        if t == "增值税":
            v_rate = rate_ctx.get("vat_rate")
            if v_rate:
                rate = float(v_rate)
                note = str(rate_ctx.get("vat_note") or note)
        elif t == "企业所得税":
            c_rate = rate_ctx.get("cit_rate")
            if c_rate:
                rate = float(c_rate)
                note = str(rate_ctx.get("cit_note") or note)
            # ★★★ 2026-10-07（用户第 3 批 任务3「企业所得税：**必须考虑小型微利条件**；
            #   **未验证小微条件时不得直接按 5% 估算**」）：
            #   小型微利优惠是**有前提**的（从业人数≤300、资产总额≤5000万、应纳税所得额≤300万，
            #   且非限制/禁止行业）。若 5%/10% 只是"听说适用"而**三项条件未逐项验证**，
            #   直接按 5% 测算会把敞口**低估 5 倍**（实测 2,112,137.70×5%=105,606.89）。
            #   口径：**未验证 ⇒ 按法定 25% 上界估算**，并如实标注（保留量级、不臆断优惠）。
            #   ★ 判定权威是 `evaluate_small_micro()`（在 `infer_rate_context` 内计算并落到
            #     `rate_ctx["smb_verified"]`）；**本处只是不变量执行点**（invariant enforcement），
            #     不重复判条件 —— 口径变更只改那一个函数。
            #   **取不到 smb_verified 就当未验证**，宁可给上界也不给低估。
            _smb_verified = bool(rate_ctx.get("smb_verified"))
            if not _smb_verified and rate and float(rate) < _CIT_STATUTORY_RATE:
                note = smb_upper_bound_note()
                rate = _CIT_STATUTORY_RATE
        _pit = pit_income if isinstance(pit_income, dict) else {}
        if t == "个人所得税" and _pit.get("rate"):
            # ★ 2026-10-16：按**所得项目**取税率（股息红利/财产转让/偶然所得 20%，
            #   综合所得另按累进）。判不出所得项目 ⇒ `_pit` 为空 ⇒ 保持既有兜底口径，行为不变。
            rate = float(_pit["rate"])
            note = str(_pit.get("note") or note)
        if (t == "个人所得税" and float(amount) < _PIT_BASIC_DEDUCTION
                and not _pit.get("rate")):
            # 金额低于年度基本减除费用：**只对综合所得（工资薪金等）**成立。
            #   ★ 2026-10-16 修（实测缺陷）：股息红利、财产转让、偶然所得按次计税、
            #   **没有**年度基本减除费用 ⇒ 旧实现一律套用本分支会把"股东分红未代扣个税"
            #   写成 `amount=0.0 / 无实际个税影响`（漏计 20% 全额）。现按所得项目分流：
            #   已判出所得项目（`_pit` 非空）⇒ 不走本分支，正常按比例税率测算。
            items.append({"tax": t, "rate": "0",
                          "amount": 0.0,
                          "note": f"涉案金额低于 {_PIT_BASIC_DEDUCTION:,.0f} 元基本减除费用，"
                                  "若属工资薪金年度累计则无实际个税影响；不计入敞口合计，"
                                  "实际以全员全额扣缴申报为准。"})
            continue
        # ★ 2026-10-04（疑点4 D12）：**基数性质相容性** —— 基数口径与本税种要求不符
        #   ⇒ **不估**（不删税种、不用默认值顶替），如实登记一条未量化项。
        #   ★ 2026-10-16：要求值改为**可接受性质集合**（个税的基数随所得项目而变，见上表）。
        _need = _TAX_BASE_NATURE.get(t)
        if amount_nature and _need and amount_nature not in _need:
            items.append({"tax": t, "rate": "", "amount": None,
                          "note": ("本项事实的金额口径为「%s」，与本税种要求的基数性质"
                                   "「%s」不符，不作加计（无对应的应税收入/所得/工资事实支撑）；"
                                   "如另存在应税收入事实，应另行核对。"
                                   % (amount_nature, "/".join(_need)))})
            continue
        # ★★ 2026-10-06（用户评语 #3-③）：锚定金额**本身即税额**时，影响额＝该金额，
        #   **不得再乘税率**（旧实现一律 `amount * rate` ⇒ 把 4,501.34 算成 270.08）。
        #   ⚠ 只在"本项税种可唯一归属"时这么做（单税种）；多税种时无法归属，
        #     仍按税率测算并如实标注（不臆断归属）。
        if amount_is_tax and len(taxes) == 1:
            items.append({"tax": t, "rate": "—",
                          "amount": round(float(amount), 2),
                          "note": ("锚定金额本身即税额（如进项/销项税额差额），"
                                   "直接作为本项税额影响，**不再乘税率**；"
                                   "实际影响还取决于该税额是否确属不得抵扣/应转出，须以资料为准。")})
            if t == "增值税":
                vat_amount = round(float(amount), 2)
            continue
        amt = round(amount * rate, 2)
        if t == "增值税":
            vat_amount = amt
        items.append({"tax": t, "rate": "%.4f" % rate,
                      "amount": amt, "note": note})
    # 增值税附加（随增值税附征）。
    # ★ 2026-10-04（同批 ⑫）：税率与附注统一取 _RATES 单一表，删除硬编码 0.12；
    #   且当本项 taxes 已单独列示「城市维护建设税」时不再合并加计，避免同一笔增值税
    #   既按 7% 单独算、又按 12% 合并算 ⇒ 敞口翻倍。
    _sur = _RATES.get("城建税及教育费附加")
    if vat_amount and _sur and _sur[0] and "城市维护建设税" not in taxes:
        items.append({"tax": "城建税及教育费附加", "rate": "%.4f" % _sur[0],
                      "amount": round(vat_amount * _sur[0], 2), "note": _sur[1]})
    total = (round(sum(i["amount"] for i in items if i.get("amount") is not None), 2)
             if items else None)
    return {
        "available": bool(items), "basis": round(float(amount), 2),
        "items": items, "total": total,
        "note": "以上为按适用税率与本期涉案金额的**粗略测算**，仅供评估影响量级；"
                "不构成核定，实际以核实后依法核定为准。各事项间金额可能重叠"
                "（同一笔资金可能同时进入多个疑点口径），敞口合计为最坏情形上界，"
                "不可逐项相加用于缴款。",
    }


def build_tax_impact_summary(problems: List[Dict[str, Any]],
                             ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """汇总本轮的潜在税额敞口（分税种）+ 已量化/未量化覆盖度。

    ★ `ctx` = `report_data["comprehensive"]["tax_rate_context"]`（`infer_rate_context()` 的产物）。
      传入后，口径声明 ④ 的小微条件表述与本项判定**同源**（见 `smb_scope_note()`）；
      不传则只指向权威章节、**不臆断**是否已取得（避免与 `cit_note` 分叉 ⇒ 门禁 B7）。
    """
    by_tax: Dict[str, float] = {}
    quantified = 0
    # ★ 2026-10-04（同批 ⑫）：**未量化的税种必须随敞口一并披露**，否则读者看到"有 25 项"
    #   却只有 12 项有数，无从判断漏了什么（旧实现把这些项整个丢掉）。
    unquantified_by_tax: Dict[str, int] = {}
    for p in (problems or []):
        ti = (p or {}).get("tax_impact") or {}
        if not ti.get("available"):
            continue
        quantified += 1
        for it in ti.get("items") or []:
            _v = to_number_checked(it.get("amount"))[0]
            if _v is None:
                _nm = str(it.get("tax") or "未列名税种")
                unquantified_by_tax[_nm] = unquantified_by_tax.get(_nm, 0) + 1
                continue
            by_tax[it["tax"]] = round(by_tax.get(it["tax"], 0.0) + float(_v), 2)
    total = round(sum(by_tax.values()), 2) if by_tax else None
    _uq_txt = ""
    if unquantified_by_tax:
        _uq_txt = ("；以下 %d 个税种本轮**未量化**（不套用默认值测算，须先取得适用税率/税额标准）：%s。"
                   % (len(unquantified_by_tax),
                      "、".join("%s（%d 项）" % (k, v)
                                for k, v in sorted(unquantified_by_tax.items(),
                                                   key=lambda kv: -kv[1]))))
    return {
        "quantified": quantified,
        "total_items": len(problems or []),
        "by_tax": [{"tax": k, "amount": v}
                   for k, v in sorted(by_tax.items(), key=lambda kv: -kv[1])],
        # ★ 2026-10-04：未量化税种清单随敞口输出（可读、可复核，不再静默丢弃）
        "unquantified_by_tax": [{"tax": k, "items": v}
                                for k, v in sorted(unquantified_by_tax.items(),
                                                   key=lambda kv: -kv[1])],
        "total": total,
        # ★★ 2026-10-06（用户评语 #4「金额测算较粗糙，易高估或误导」）：
        #   用户点名要求说明的四件事，这里**逐条声明口径边界**（写进已渲染的 `note`，
        #   新加"没人渲染的键"等于没做）：
        #     ① 含税/不含税；② 进项留抵与已转出；③ 企业所得税亏损弥补；
        #     ④ 附加税减半等优惠；⑤ 各疑点金额是否重叠；⑥ 红字冲销是否按销项全额估算。
        "note": ("【口径声明】潜在税额敞口为按适用税率的粗略测算（税率语境见各项明细），"
                 "仅供评估量级，不构成核定，也不等于应补税额。"
                 "① 含税口径：锚定语境标注为「价税合计／含税」的，已按适用税率价税分离为"
                 "不含税后再测算；未标注含税的按不含税处理，两者不可混比。"
                 "② 增值税部分**未考虑**进项留抵、已转出进项税额与留抵抵减，"
                 "亦未区分是否实际造成少缴，故为**上界**。"
                 "③ 企业所得税部分**未考虑**亏损弥补与以前年度结转，故为**上界**。"
                 + smb_scope_note(ctx) +
                 "⑤ 红字冲销／作废发票类按销项全额估算上限，**未扣减**对应蓝字发票与已冲回部分。"
                 "⑥ 各事项间金额可能重叠（同一笔款项可能被多个疑点引用），"
                 "敞口合计为最坏情形上界，**不可逐项相加用于缴款**。"
                 "⑦ 未量化的项表示检查记录中尚无明确金额，须补资料后测算。"
                 + _uq_txt),
    }
