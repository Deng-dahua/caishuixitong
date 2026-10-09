# -*- coding: utf-8 -*-
"""报告**去重与去元话语**的唯一权威（2026-10-06）。

## 为什么必须有它（用户评语：「重复冗余内容可能占全文三分之一以上」）
原报告每个疑点都按同一模板铺开，同一内容在「总述 / 分述 / 结论 / 自我反驳 / 补资料」
里反复出现，且大量**逐字相同**的共性段被复制到几十个疑点上：
  · 「若不补充资料的后果」（含滞纳金/第六十三条/不作定性）：20+ 次逐字重复；
  · 「未收到"合同文件"…」缺失资料声明：20+ 个疑点各来一遍；
  · 「本表列出的是该风险事项所依据的基础逐笔明细（全量）…」：每张明细表前一遍；
  · 「本段是系统对自己结论的复核」「系统不对企业的解释作预判」：**系统自述**（元话语），
    按报告口径**根本不该出现在给企业看的正文里**。
后果：重点被淹没、篇幅虚长、专业性下降；企业还面对**同一份资料被要求三次**。

## 设计（数据驱动，不做逐条特判）
  R1 **删元话语**：命中 `_META_PATTERNS` 的句子直接删除（系统自述/自我证明/指针）。
  R2 **逐字重复段上提**：同一段文本（去空白后）出现在 **≥ `_HOIST_MIN` 个疑点**里 ⇒
     报告级保留一次（记入 `common_statements`），疑点内删除该段。
  R2b **逐字重复句上提**（2026-10-06 追加）：共性段往往**整段不同、逐句相同** ——
     典型是「已取得的资料与待补充的资料」：每个疑点缺的资料不同，但
     「未收到"合同文件"导致相关检查未完成」这类**句子**在 20+ 个疑点里一字不差地重复。
     只做 R2 会让这些句子全部漏网（企业面对"同一份资料被要求 N 次"）。
     故对共性段标题按**句子**再统计一次，命中即整句上提（同样记入 `common_statements`）。
  R3 **表注去重**：同一表注文本只保留**首次**出现（其余删除）。
  R4 **共性段不回填**：被删除处**不留"见上文"式指针**（用户口径：指针也是废话）。

## 边界（必须守住）
  · **只动"逐字相同"的共性文本**，绝不改写任何**本项特有**的事实、金额、资料名、结论；
  · **不改变任何判定/等级/金额**，只减少重复表述；
  · 被删除的共性文本**必须**在 `common_statements` 里可查（否则企业无处对照 ⇒ 等于丢信息）；
  · 幂等：连跑两次结果一致。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

#: **元话语**（系统自述/自我证明/内部指针）—— 命中即整句删除。
#: 依据报告口径：给企业看的内容里不得出现"我怎么做的""我复核了自己"这类系统动作描述。
_META_PATTERNS = (
    re.compile(r"本段是系统对自己结论的复核"),
    re.compile(r"系统不对企业的解释作预判"),
    re.compile(r"^本段由系统"),
    re.compile(r"^系统自动"),
    re.compile(r"^由系统生成"),
)

#: 需要"逐字重复即上提"的段落标题（这些是共性段；本项特有内容不在此列）。
#  ⚠ 这里存的是**归一化后**的标题（见 `norm_head`）：去掉序号前缀（"三、"）与空白。
#  ★★ 2026-10-06 事故（"注释说 A、代码做 B"）：本表原先存的是**未归一化**的字面标题，
#    而匹配用的是 `head in _HOISTABLE_HEADS`（**精确相等**）—— 于是几乎全部漏配：
#      · 实际标题是「三、已取得的资料与待补充的资料」，表里写「已取得的资料与待补充的资料」；
#      · 实际标题有「若不补证的后果」「若不补充资料的后果」**两种**，表里只写后一种；
#      · 「本项可能错在哪里：自我反驳与验证清单」只由**前端**渲染，引擎侧根本不存在该段。
#    后果：去重引擎"看起来接上了"，实际上什么都没上提（报告仍逐疑点重复）。
#    修法（数据驱动、加标题无需改分支）：标题先过 `norm_head` 归一，再按**模式**判定。
_HOISTABLE_HEADS = (
    "若不补充资料的后果",
    "已取得的资料与待补充的资料",
    "需企业提供的资料与说明",
    "本项可能错在哪里：自我反驳与验证清单",
)

#: 序号前缀，两种形态：①「（三）」「(3)」；②「三、」「三.」「三，」
_HEAD_ORDINAL = re.compile(
    r"^(?:[（(][一二三四五六七八九十0-9]+[)）]|[一二三四五六七八九十0-9]+\s*[、.．，,])")

#: markdown 强调符（`**加粗**` / `*斜体*`）——**判据比对前必须剥掉**。
#  ★★ 2026-10-08 真实事故（后果＝正文被替换成悬空引用）：权威数据
#    `levy_nature.LEVIES[*]["consequence"]` 里带 `**…**`（如
#    "**是否构成偷税、以及是否移送，须由税务机关依法调查认定**"），
#    而报告正文的强调符已被 `_naturalize_report_text` 剥掉 ⇒ 两侧不同键 ⇒
#    该句**未被识别为税费性质专属句** ⇒ 第 2 轮跨项替换把它换成「〔见疑点R1〕」，
#    实测疑点 R4 的「若不补充资料的后果」段尾被整句删除。
_MD_EMPH = re.compile(r"\*+")


def _cmp_key(text: Any) -> str:
    """**判据比对键**（唯一实现）——去 markdown 强调符 + 去全部空白 + 去首尾句末分隔符。

    为什么必须只有这一个键：同一条判据（"这句是不是性质专属/本项专属/与那句相同"）
    的两侧文本来自**不同来源**（权威数据表 vs 报告正文；带分隔符的句子 vs 表末无分隔符），
    字面比对必然漏配。历史教训两类：
      · **分隔符**：调用方传入的句子带「。」，而权威文本里该句位于文末（无「。」）；
      · **强调符**：权威数据表带 `**`，正文已被渲染层剥掉。
    幂等：`_cmp_key(_cmp_key(x)) == _cmp_key(x)`（三种剥离都是幂等的）。
    """
    s = _MD_EMPH.sub("", str(text or ""))
    s = _WS.sub("", s)
    return s.strip(_TERM_CHARS)


def cmp_key(text: Any) -> str:
    """**公开别名**（唯一判据键，供跨模块薄转发，如 `engine/common_clauses`）。

    为什么公开：『这句是不是同一句』是**同一个判据**，登记表侧（正则）与正文侧（句子）
    必须用同一个键，否则因空白/标点差异必然漏配。判据本体仍只此一份（`_cmp_key`）。
    """
    return _cmp_key(text)


def norm_head(head: Any) -> str:
    """段落标题**归一化**：去 markdown 强调符、去空白、去序号前缀（"三、"）、去首尾括号。

    为什么必须归一：标题里带序号是**排版**需要，与"这是不是共性段"无关；
    拿带序号的标题去和字面表做精确比较，必然漏配（实测 3/3 漏配）。
    """
    h = _cmp_key(head).strip("　 ")
    h = _HEAD_ORDINAL.sub("", h)
    return h.strip("　 ").strip("（）()【】[]")


def is_consequence_head(head: Any) -> bool:
    """该标题是否为「若不补（充）资料的后果」段（**唯一权威**）。

    ★★ 2026-10-06 事故（又一例"注释说 A、代码做 B"）：闸门原先用
      `"若不补证" in heading` 识别后果段，而**产物里的标题是「若不补充资料的后果」**
      （"若不补充"里没有子串"若不补证"）⇒ 识别不到 ⇒ 闸门把"缺依据"假报成 ERROR
      （实测：文建费项被判"未点出政府性基金"，实际文本里明明写着）。
    ⇒ 识别口径只此一处：归一化后以「若不」开头且含「后果」。
      三个真实变体（「若不补证的后果」「若不补充资料的后果」「若不补充资料可能承担的后果」）
      一律覆盖；新增措辞无需改任何调用方。
    """
    h = norm_head(head)
    return bool(h) and h.startswith("若不") and "后果" in h


def is_hoistable_head(head: Any) -> bool:
    """该标题是否为**共性段**（逐字重复即应上提为报告级一次）。

    判据按**模式**（不是字面枚举），使新增标题变体无需改逻辑分支：
      · 后果段：见 `is_consequence_head`；
      · 资料与补件段：归一后命中 `_HOISTABLE_HEADS` 中的资料类标题；
      · 自我反驳段：归一后含「自我反驳」（前端标题为「本项可能错在哪里：自我反驳与验证清单」）。
    """
    h = norm_head(head)
    if not h:
        return False
    if is_consequence_head(h):
        return True
    if h in _HOISTABLE_HEADS:
        return True
    if "自我反驳" in h:
        return True
    return False


#: 段落除 `text` 外**仍会被渲染层输出**的字段（"可见载荷"）。
#  ★★ 2026-10-09 真实事故（P0-5 收口 / "request 环整环消失"）：
#    R2 段级上提只比对 `(heading, text)`，把「五、需企业提供的资料与说明」这类
#    **容器段**当成了"逐字重复的共性段"——
#      · 13 个疑点该段 text 都是同一句结构性引导句「要把这一项查清楚，需要：」（逐字相同）；
#      · 但各自的 `bullets`（补件清单）与 `detail_table`（`_supplement_table` 明细）
#        **互不相同**（本项专属）。
#    R2 判"重复"后**整段删除** ⇒ 企业专属的补件清单/补件明细表被当成重复内容删掉
#    （前端 `_renderNarrativeBody` / `_renderBullets` 确实渲染 bullets 与明细表，
#     即用户可见内容**真的丢了**，且删除不可逆 —— 违反"删了就是真删了，但它不是重复"）。
#    ⇒ 纪律：**段级上提的删除粒度是"整段"**，因此带可见载荷的段落一律不参与段级上提；
#     段内**共同的句子**交给句级上提（R2b）处理，载荷原样保留。
_VISIBLE_PAYLOAD_KEYS = ("bullets", "detail_table", "detail_tables", "tail")


def has_visible_payload(para: Any) -> bool:
    """该段落除 `text` 外是否还带**用户可见载荷**（bullets / 明细表 / 尾注）。

    为什么必须由它决定"能否整段上提"：段级删除是**整段**，载荷是**本项专属**的，
    只看 `text` 相同就删段 = 删掉别人没有的内容（唯一权威；调用方不得自写一套判据）。
    """
    if not isinstance(para, dict):
        return False
    for k in _VISIBLE_PAYLOAD_KEYS:
        v = para.get(k)
        if isinstance(v, (list, tuple, dict)) and len(v) > 0:
            return True
        if isinstance(v, str) and v.strip():
            return True
    return False


def is_structural_lead(text: Any) -> bool:
    """该文本是否为**结构性引导句**（以「：」承诺后文、本体无信息量）。

    为什么不得上提/替换：它是**结构**（"下面列一份清单"），不是**报告级通用口径**；
    抽到报告级会渲染成"有标题没内容"的空条目（历史事故：`report_statement` 里出现
    「说明2。要把这一项查清楚，需要：」）。判据唯一权威
    `engine.content_placeholder_guard.is_orphan_lead`（形态 + 词表，数据驱动）。
    """
    try:
        from engine.content_placeholder_guard import is_orphan_lead as _orphan
    except Exception:  # noqa: BLE001 —— 权威取不到时保守判"不是"（不误删正文）
        return False
    return bool(_orphan(text))


def is_paragraph_hoistable(para: Any) -> bool:
    """该段落是否**允许参与段级上提**（**唯一判据**：R2 计数、R2 删除、闸门探测器三处共用）。

    四个条件缺一不可：
      ① 标题是**共性段**（`is_hoistable_head`）；
      ② 文本非空；
      ③ 不含**税费性质专属**文本（刻意不上提 —— 防税款条款被套到社保/公积金/基金事项上）；
      ④ **不带可见载荷**（bullets / 明细表 / 尾注）。

    为什么要 ④（2026-10-09 真实事故）：段级上提的删除粒度是**整段**，而载荷是**本项专属**
    内容。实测 13 个疑点的「五、需企业提供的资料与说明」段文本同为引导句、载荷各不相同
    ⇒ 判"重复"后整段删除，**把企业专属的补件清单与补件明细表一起删了**
    （前端确实渲染这两个字段 = 用户可见内容真丢）。
    ⚠ 本判据必须与 `find_leftover_duplicates`（闸门探测）**同口径**，否则闸门会把
      合法保留的容器段报成"该上提未上提"。
    """
    if not isinstance(para, dict):
        return False
    if not is_hoistable_head(para.get("heading")):
        return False
    if has_visible_payload(para):
        return False
    k = _norm_key(para.get("text"))
    if not k:
        return False
    return not _text_has_nature_specific(k)


#: 上提阈值：同一文本出现在 ≥ N 个疑点即视为共性段
_HOIST_MIN = 3

#: 句级上提的最小字数（去空白后）。过短的句子（"同上"）不参与，避免误删有效短句。
_SENT_HOIST_MIN_CHARS = 8

#: 归一到"可比对文本"：去空白、去全角空格、去多余标点差异
_WS = re.compile(r"[\s\u3000]+")


def _norm_key(text: Any) -> str:
    """**薄转发** `_cmp_key`（保留旧名，避免散落调用点各持一套归一化）。

    ★ 2026-10-08：本函数此前只做"去空白"，与 `_sent_key`（再去句末分隔符）**两套口径**
      ——段级键与句级键对同一段文本给出不同结果，是上面那起"漏配⇒内容被替换"的同一病根。
      现统一为唯一实现 `_cmp_key`。
    """
    return _cmp_key(text)


#: 句末分隔符（判断/计数时剔除，保证"带分隔符"与"不带分隔符"的切句结果同键）
_TERM_CHARS = "。；；！？!?;.\u3000 "


def _sent_key(piece: Any) -> str:
    """句子的**比对键**：薄转发 `_cmp_key`（去强调符 + 去空白 + 去句末分隔符）。

    为什么需要它（2026-10-06 真实事故）：`split_sentences` 默认**丢掉**句末分隔符，
    而"原样回拼"必须用 `keep_delims=True`（保留分隔符）。两处若各用一套键，
    "删哪些句"的判定与实际回拼就对不上。统一走 `_cmp_key` 后，
    两种形态的同一句子得到**同一个键**，判据与回拼必然一致。
    """
    return _cmp_key(piece)


def _split_keep(text: Any) -> List[str]:
    """切句**且保留句末分隔符**（`"".join(结果) == 原文`，可原样回拼）。

    取不到权威 → 返回 `[]`（调用方据此放弃切分，宁可保留原文也不切坏）。
    """
    try:
        from engine.sentencekit import split_sentences as _ss
        return list(_ss(str(text or ""), keep_delims=True) or [])
    except TypeError:                   # 兼容旧签名（无 keep_delims 参数）
        try:
            from engine.sentencekit import split_sentences as _ss2
            return list(_ss2(str(text or "")) or [])
        except Exception:  # noqa: BLE001
            return []
    except Exception:  # noqa: BLE001
        return []


def _nature_specific_blob() -> str:
    """**税费性质专属**的法条文本（归一化后拼接），用于阻止跨性质上提（数据驱动）。

    ★★ 2026-10-06 真实回归（比"闸门报错"严重得多）：
      句级上提把「主管税务机关可依《税收征收管理法》第三十二条加收滞纳金」
      「构成偷税、抗税、骗税的，依第六十三条等规定追缴税款、滞纳金并处罚款」这类
      **税款专属**句从 ≥3 个疑点抽到**报告级** ⇒ 报告级那段话对**所有**事项都成立，
      于是「文化事业建设费」「社会保险费」等**非税**事项也被套上了征管法偷税条款
      —— 正是用户评语 #4「税费法律适用混同」，被去重悄悄打回原形。
    判据：句子若落在任一税费性质的 `consequence`/`basis` 文本内 ⇒ **不得上提**
    （新增一种费/基金只在 `levy_nature.LEVIES` 加一行，本处自动生效）。
    """
    try:
        from engine.levy_nature import LEVIES
    except Exception:  # noqa: BLE001
        return ""
    _parts = []
    for _d in (LEVIES or {}).values():
        for _k in ("consequence", "basis"):
            _t = _norm_key(_d.get(_k))
            if _t:
                _parts.append(_t)
    return "".join(_parts)


#: 税费性质专属文本（模块级缓存，避免每个疑点都重建）
_NATURE_BLOB: Optional[str] = None
#: 税费性质专属**句**集合（归一化）——段级判定用
_NATURE_SENTS: Optional[frozenset] = None


def _nature_sentences() -> frozenset:
    """税费性质专属的**句**集合（归一化），用于段级"含专属句即不上提"判定。"""
    global _NATURE_SENTS
    if _NATURE_SENTS is None:
        _s: set = set()
        try:
            from engine.levy_nature import LEVIES
            from engine.sentencekit import split_sentences as _ss
        except Exception:  # noqa: BLE001
            _NATURE_SENTS = frozenset()
            return _NATURE_SENTS
        for _d in (LEVIES or {}).values():
            for _k in ("consequence", "basis"):
                for _x in (_ss(str(_d.get(_k) or "")) or []):
                    _n = _sent_key(_x)
                    if len(_n) >= _SENT_HOIST_MIN_CHARS:
                        _s.add(_n)
        _NATURE_SENTS = frozenset(_s)
    return _NATURE_SENTS


def _is_nature_specific(norm_text: str) -> bool:
    """该（任意形态）文本是否为**税费性质专属**文本 ⇒ 不得跨疑点上提/替换。

    ★ 2026-10-08：入参**先过 `_cmp_key`**（内部归一，不信任调用方）——
      本节判据曾因"调用方传带「。」的句子、权威表里该句在文末无「。」"而漏配，
      导致该保护的句子被替换掉。归一放在本函数内，任何调用方传什么都不再影响正确性。
    """
    global _NATURE_BLOB
    _k = _cmp_key(norm_text)
    if not _k:
        return False
    if _NATURE_BLOB is None:
        _NATURE_BLOB = _nature_specific_blob()
    if _NATURE_BLOB and _k in _NATURE_BLOB:
        return True
    return _k in _nature_sentences()


#: **本项专属**句（含本项自己的涉嫌情形/结论），逐字相同也不得上提。
#   「本项存在被认定为「少缴税款」的风险」里的情形是**这一项**的判定结论，
#   抽到报告级会让读者以为它适用于所有事项（与"等级/口径不得跨项漂移"同一条纪律）。
#   数据驱动：新增同类句只加一行正则。
_NEVER_HOIST_SENT_PATTERNS = (
    re.compile(r"本项存在被认定为"),
    re.compile(r"本项所涉"),
)


def _is_item_specific_sentence(norm_text: str) -> bool:
    """该文本是否**本项专属**（不得上提/替换）。入参内部归一（同 `_is_nature_specific`）。"""
    t = _cmp_key(norm_text)
    return bool(t) and any(rx.search(t) for rx in _NEVER_HOIST_SENT_PATTERNS)


def _sentence_not_hoistable(norm_text: str) -> bool:
    """句子不得上提/替换的**统一判据**（性质专属 ∪ 本项专属 ∪ 结构性引导句）。

    ★ 2026-10-08：入参内部归一 ⇒ 第 1 轮（`report_dedup`）与第 2 轮
      （`report_pipeline.dedup_sentences_cross`，传 `dupkit.norm` 结果）**必然同口径**。
    ★ 2026-10-09（P0-5 收口）：追加**结构性引导句**（`is_structural_lead`）——
      「要把这一项查清楚，需要：」这类句子是清单的**引子**，不是通用口径；
      上提到报告级会变成空条目，替换成「〔见疑点R…〕」更会让清单失去引导
      （且第 2 轮替换会把它写到**别的**疑点上）。
    """
    return (_is_nature_specific(norm_text) or _is_item_specific_sentence(norm_text)
            or is_structural_lead(norm_text))


def sentence_not_hoistable(norm_text: str) -> bool:
    """**公开别名**（唯一判据，供 `report_pipeline` 薄转发）。

    ★★ 2026-10-08（P0-2 根因治理）：「什么句子可以跨疑点替换/上提」是**同一个判据**，
      第 1 轮（本模块 R2b 句级上提）与第 2 轮（`report_pipeline.dedup_sentences_cross`
      跨项替换）**必须同口径**。旧实现只有本模块私有的 `_sentence_not_hoistable`，
      第 2 轮未复用 ⇒ 本项专属句（「本项存在被认定为…」「本项所涉…」）在第 2 轮
      **照样被替换成别的疑点的引用** ⇒ 后果段整段塌陷（实测 13 处）。
      现公开本判据，两轮共用；判据本体仍只此一份（改动只改上面两处）。
    """
    return _sentence_not_hoistable(norm_text)


def _text_has_nature_specific(norm_text: str) -> bool:
    """整段文本是否**含**不得上提的内容（性质专属句 ∪ 本项专属句）。入参内部归一。

    为什么段级也要判：税种事项的后果段彼此**逐字相同**（同性质 ⇒ 同文本），
    R2 会把整段上提到报告级，而报告级那段话对**所有**事项都成立
    ⇒ 非税事项照样被套上征管法偷税条款。
    再进一步：后果段必然含**本项自己的**涉嫌情形（「本项存在被认定为…」），
    故它**永远不是纯共性文本** —— 段级一律不上提，共性部分交给句级（R2b）处理。
    """
    _k = _cmp_key(norm_text)
    if not _k:
        return False
    if _is_nature_specific(_k) or _is_item_specific_sentence(_k):
        return True
    for _n in _nature_sentences():
        if _n and _n in _k:
            return True
    return any(rx.search(_k) for rx in _NEVER_HOIST_SENT_PATTERNS)


def _strip_meta(text: str) -> Tuple[str, int]:
    """R1：删除元话语句（按句切分，命中即删整句）。返回 (新文本, 删除句数)。"""
    t = str(text or "")
    if not t:
        return t, 0
    # ⚠ 切句必须走**唯一权威** `sentencekit.split_sentences`（括号感知）——
    #   朴素 `re.split(r"(?<=[。；！？])")` 会在括号内切断，切出"读不通的残句"（本项目踩过，
    #   闸门 `check_report_credibility` 会直接报 ERROR）。
    # ★★ 2026-10-06 **必须 `keep_delims=True`**（真实事故，"读不通"级）：
    #   默认切句**丢掉句末分隔符**（`'甲。乙'` → `['甲','乙']`），回拼时
    #   "".join 会把整段标点吃光 —— 实测产物出现
    #   「…按规定补缴并加收滞纳金文化事业建设费是政府性基金，不是税…」
    #   （"滞纳金"与"文化"之间的「；」被吃掉），读者看到的是断句错乱的长串。
    #   `keep_delims=True` 保证 `"".join(切句结果) == 原文`，只删目标句、不动其余一字。
    try:
        from engine.sentencekit import split_sentences as _ss
        parts = _ss(t, keep_delims=True)
    except TypeError:                   # 兼容旧签名
        try:
            from engine.sentencekit import split_sentences as _ss2
            parts = _ss2(t)
        except Exception:  # noqa: BLE001
            return t, 0
    except Exception:  # noqa: BLE001
        return t, 0                     # 取不到权威 ⇒ 不删（宁可留元话语，也不切坏正文）
    kept, dropped = [], 0
    for p in parts:
        s = p.strip()
        if s and any(rx.search(s) for rx in _META_PATTERNS):
            dropped += 1
            continue
        kept.append(p)
    return "".join(kept), dropped


def dedup_report(report: Dict[str, Any]) -> Dict[str, Any]:
    """对报告做**一次**去重/去元话语，原地修改并返回统计。

    :param report: `enterprise_readable_report` dict（含 confirmed_problems 等）
    :return: {"meta_removed": n, "hoisted": n, "table_notes_removed": n,
              "common_statements": [...]}
    """
    stat = {"meta_removed": 0, "hoisted": 0, "sentences_hoisted": 0,
            "table_notes_removed": 0, "payload_kept": 0, "common_statements": []}
    if not isinstance(report, dict):
        return stat
    problems = report.get("confirmed_problems")
    if not isinstance(problems, list) or not problems:
        return stat

    # ── R1 元话语（所有文本字段）──
    def _walk_meta(_o) -> None:
        if isinstance(_o, dict):
            for k in list(_o.keys()):
                v = _o[k]
                if isinstance(v, str):
                    nv, dn = _strip_meta(v)
                    if dn:
                        _o[k] = nv
                        stat["meta_removed"] += dn
                else:
                    _walk_meta(v)
        elif isinstance(_o, list):
            for v in _o:
                _walk_meta(v)

    _walk_meta(problems)

    # ── R2 逐字重复段上提（只对共性段标题）──
    counts: Dict[str, List[int]] = {}
    for i, p in enumerate(problems):
        if not isinstance(p, dict):
            continue
        for para in (p.get("narrative_paragraphs") or []):
            # 唯一判据（含**容器段护栏**：带载荷的段落不参与段级上提）
            if not is_paragraph_hoistable(para):
                continue
            key = _norm_key((para or {}).get("text"))
            counts.setdefault("%s||%s" % (str((para or {}).get("heading") or "").strip(), key),
                              []).append(i)

    hoisted = {k for k, idx in counts.items() if len(idx) >= _HOIST_MIN}
    if hoisted:
        # ★ 用户口径（第九条"如果要改，应该怎么去重"）：**共性声明前置** ——
        #   不是"只在第一个疑点留一份"，而是**从所有疑点删除**、由报告级**一次性**给出。
        #   原文存入 `common_statements`（含出处样本），确保企业仍能逐字对照，不丢信息。
        _samples: Dict[str, Dict[str, str]] = {}
        for i, p in enumerate(problems):
            if not isinstance(p, dict):
                continue
            for para in (p.get("narrative_paragraphs") or []):
                head = str((para or {}).get("heading") or "").strip()
                key = "%s||%s" % (head, _norm_key((para or {}).get("text")))
                if key in hoisted:
                    _samples.setdefault(key, {"heading": head, "text": str(para.get("text") or "")})
        for i, p in enumerate(problems):
            if not isinstance(p, dict):
                continue
            kept = []
            for para in (p.get("narrative_paragraphs") or []):
                head = str((para or {}).get("heading") or "").strip()
                key = "%s||%s" % (head, _norm_key((para or {}).get("text")))
                if key in hoisted:
                    # ★ 2026-10-09：判定与删除**必须同口径、且同一权威** —— 计数阶段用的是
                    #   `is_paragraph_hoistable`（含**容器段护栏**），删除阶段必须调**同一个**函数：
                    #   若这里内联一套自己的判据（曾用 `has_visible_payload`），两处一旦漂移，
                    #   别的疑点贡献的 key 仍会把它删掉（"计数对了、动作错了"）。
                    if not is_paragraph_hoistable(para):
                        stat["payload_kept"] += 1
                        kept.append(para)
                        continue
                    stat["hoisted"] += 1
                    continue
                kept.append(para)
            p["narrative_paragraphs"] = kept
        stat["common_statements"] = [
            {"heading": v["heading"], "text": v["text"]}
            for v in _samples.values()
        ]

    # ── R2b 逐字重复**句**上提（共性段"整段不同、逐句相同"的情形）──
    #   ★ 2026-10-06（用户：「同一份资料被要求三次」「同一补资料清单三处重复」）：
    #     典型病根段落＝「已取得的资料与待补充的资料」——每个疑点缺的资料不同，故 R2
    #     （整段逐字比对）永远打不中；但「未收到"合同文件"导致相关检查未完成」这类**句子**
    #     在 20+ 个疑点里一字不差，读者看到的是"同一件事说了二十遍"。
    #   判据与 R2 同源（同一权威、同一阈值、同一落档 `common_statements`），只是统计粒度＝句。
    _sent_counts: Dict[str, List[int]] = {}
    _sent_owner: Dict[str, str] = {}
    _sent_sample: Dict[str, str] = {}
    _split = None
    try:
        from engine.sentencekit import split_sentences as _split  # 唯一权威（括号感知）
    except Exception:  # noqa: BLE001
        _split = None
    if _split is not None:
        for i, p in enumerate(problems):
            if not isinstance(p, dict):
                continue
            for para in (p.get("narrative_paragraphs") or []):
                head = str((para or {}).get("heading") or "").strip()
                if not is_hoistable_head(head):
                    continue
                for _s in (_split_keep((para or {}).get("text")) or []):
                    _k = _sent_key(_s)
                    if len(_k) < _SENT_HOIST_MIN_CHARS:
                        continue          # 太短的句子不参与（"同上""详见下表"之类）
                    # ★ 不得上提的句：①税费性质专属句（「依《征管法》第六十三条…」抽到报告级
                    #   会被套到文建费/社保等**非税**事项上，用户评语 #4 回归）；
                    #   ②本项专属结论句（含本项自己的涉嫌情形）。
                    if _sentence_not_hoistable(_k):
                        continue
                    _sent_counts.setdefault(_k, []).append(i)
                    _sent_owner.setdefault(_k, head)
                    _sent_sample.setdefault(_k, str(_s).strip())
        _hot_sents = {k for k, idx in _sent_counts.items() if len(set(idx)) >= _HOIST_MIN}
        if _hot_sents:
            for p in problems:
                if not isinstance(p, dict):
                    continue
                kept_paras = []
                for para in (p.get("narrative_paragraphs") or []):
                    head = str((para or {}).get("heading") or "").strip()
                    if not is_hoistable_head(head):
                        kept_paras.append(para)
                        continue
                    # ★ 必须用 `_split_keep`（保留句末分隔符）——默认切句会丢分隔符，
                    #   `"".join` 回拼就把整段标点吃光（实测"…滞纳金文化事业建设费是…"）。
                    _pieces = _split_keep((para or {}).get("text")) or []
                    _keep = []
                    for _s in _pieces:
                        if _sent_key(_s) in _hot_sents:
                            stat["sentences_hoisted"] += 1
                            continue
                        _keep.append(_s)
                    _nt = "".join(_keep).strip()
                    para["text"] = _nt
                    # ★ 2026-10-09（容器段护栏）：正文被抽空**不能**连带丢掉载荷。
                    #   前端 `_renderNarrativeBody`/`_renderBullets` 会渲染 bullets 与明细表，
                    #   正文清空只是"这句话在报告级已给过一次"，载荷仍是本项专属内容。
                    if _nt or has_visible_payload(para):
                        kept_paras.append(para)
                p["narrative_paragraphs"] = kept_paras
            for _k in sorted(_hot_sents):
                stat["common_statements"].append({
                    "heading": _sent_owner.get(_k, ""),
                    "text": _sent_sample.get(_k, _k),
                    "scope": "sentence",
                })

    # ── R3 表注去重（同一表注只留首次）──
    _note_seen = set()
    for p in problems:
        if not isinstance(p, dict):
            continue
        for holder in list(p.get("narrative_paragraphs") or []) + [p]:
            for tkey in ("detail_table", "detail_tables"):
                tv = holder.get(tkey)
                tables = tv if isinstance(tv, list) else ([tv] if isinstance(tv, dict) else [])
                for t in tables:
                    if not isinstance(t, dict):
                        continue
                    note = str(t.get("note") or "").strip()
                    if not note:
                        continue
                    nk = _norm_key(note)
                    if nk in _note_seen:
                        t["note"] = ""
                        stat["table_notes_removed"] += 1
                    else:
                        _note_seen.add(nk)

    _ = (_HOISTABLE_HEADS, _HOIST_MIN, _META_PATTERNS)   # 保持常量被引用（供闸门读取）
    return stat


def find_leftover_duplicates(report: Any) -> Dict[str, List[Tuple[str, int, str]]]:
    """探测**去重后的残留重复**（唯一权威；闸门不得自写一套计数）。

    返回：
      {
        "paragraphs": [(heading, 出现疑点数, 段落文本[:40]), ...],   # 段级残留
        "sentences":  [(heading, 出现疑点数, 句子文本[:40]), ...],   # 句级残留
      }
    只列出出现疑点数 **≥ `_HOIST_MIN`** 的项（即"本该被上提却没上提"的共性文本）。
    同一疑点内重复出现只计 1 次（与上提口径一致：判据是"跨疑点重复"）。
    """
    out: Dict[str, List[Tuple[str, int, str]]] = {"paragraphs": [], "sentences": []}
    probs = report
    if isinstance(report, dict):
        probs = report.get("confirmed_problems")
    if not isinstance(probs, list):
        return out
    probs = [p for p in probs if isinstance(p, dict)]

    _pcnt: Dict[str, int] = {}
    _ptxt: Dict[str, str] = {}
    for p in probs:
        _local = set()
        for para in (p.get("narrative_paragraphs") or []):
            head = str((para or {}).get("heading") or "").strip()
            # ★ 2026-10-09：段级残留探测必须与 `dedup_report` 的段级上提**同口径、同一权威**
            #   （`is_paragraph_hoistable`）—— 否则闸门会把"合法保留的容器段/性质专属段"
            #   报成"该上提未上提"，制造**假红**。判据只有一处：`engine/report_dedup.is_paragraph_hoistable`。
            if not is_paragraph_hoistable(para):
                continue
            k = _norm_key((para or {}).get("text"))
            _key = "%s||%s" % (head, k)
            _local.add(_key)
            _ptxt.setdefault(_key, str((para or {}).get("text") or "")[:40])
        for _key in _local:
            _pcnt[_key] = _pcnt.get(_key, 0) + 1
    for _key, n in _pcnt.items():
        if n >= _HOIST_MIN:
            out["paragraphs"].append((_key.split("||")[0], n, _ptxt.get(_key, "")))

    # 句级残留：与 `dedup_report` 同口径（`_split_keep` 保留分隔符 ⇒ 键由 `_sent_key` 归一到"不带分隔符"）
    _scnt: Dict[str, int] = {}
    _stxt: Dict[str, str] = {}
    for p in probs:
        _local = set()
        for para in (p.get("narrative_paragraphs") or []):
            head = str((para or {}).get("heading") or "").strip()
            if not is_hoistable_head(head):
                continue
            for _s in (_split_keep((para or {}).get("text")) or []):
                k = _sent_key(_s)
                if len(k) < _SENT_HOIST_MIN_CHARS:
                    continue
                if _sentence_not_hoistable(k):   # 同 `dedup_report`：不得上提的句保留在各项
                    continue
                _key = "%s||%s" % (head, k)
                _local.add(_key)
                _stxt.setdefault(_key, str(_s).strip()[:40])
        for _key in _local:
            _scnt[_key] = _scnt.get(_key, 0) + 1
    for _key, n in _scnt.items():
        if n >= _HOIST_MIN:
            out["sentences"].append((_key.split("||")[0], n, _stxt.get(_key, "")))
    return out
