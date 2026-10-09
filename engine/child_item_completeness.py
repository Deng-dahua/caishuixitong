# -*- coding: utf-8 -*-
"""子项与关联项完整性（Skill 6 唯一权威 / v1.1.0）。

## 为什么要它
用户复核（2026-10-07）指出四类"**列了子项却不分析**"：
  · 疑点1：明细表列了进项侧 9 笔红冲（269,550.57 元），正文只写"属购方侧红冲，不参与销项占比"
    —— 以"不参与本项口径"为由**跳过**，未分析**是否已做进项税额转出**。
  · 疑点3：风险族「薪酬与用工三源」列了 **5 个子项**，正文只分析了 2 项。
  · 疑点4：构成要件第④条「个人账户代收经营款项后转入公司账户但未确认收入」标注"须核对"，
    正文未做任何具体分析。
  · 疑点15：个人垫付 116,504.85 元，只列金额，未说明**对应供应商、笔数、是否已报销冲账**。
根因：**疑点形成时列了子项，但没有强制要求每个子项都必须有独立的核对结论或资料缺口说明**。

## 三条硬规则（本模块唯一实现）
1. **每个子项必须有独立结论**：状态 ∈ {已核对, 未核对, 须核对, 资料缺失}，
   `已核对` 必须有结论，其余必须有 `gap`（原因 + 需补资料）。
2. **关联项必须单独分析**：`related_items[].analysis_required=true` 的，
   **不得**以"不参与本项口径/不参与本项占比"为由跳过 —— 跳过即判未分析。
3. **子项清单与正文一一对应**：子项清单里出现的每一项，正文必须有对应分析段落；
   反之正文提到的子项必须在清单里（防"清单与正文两张皮"）。

## ★ 本版（1.1.0）修掉的四个根因
| # | 病根（实测） | 修法 |
|---|---|---|
| ① | **判据两侧标点不对称**：`_keywords(desc)` 会剥掉「、，。；」等标点，而被比对的正文不剥 ⇒ 同一句话在两侧的关键字对不上（"进项发票9行、金额合计269,550.57元" 的 4-gram 全部落空）⇒ 判据**假阴性** | 标点归一化收敛为 `_PUNCT_RE`，**desc 与正文同一套**（唯一权威） |
| ② | **"提到"判据脆弱**：旧版"命中率≥50% + 至少一个 len≥4 关键词命中"，词表里混着大量 2-gram ⇒ 子项描述里有一个常见二字词出现在正文就算"提到"（把标题级提及当已分析） | 改为**4-gram 重合率 ≥ 50%**（单一、可解释的判据；中文不切词时的等价物） |
| ③ | **"有结论"判据被表格标题骗过**：`CONCLUSION_MARKERS` 里含「合计/共 /逐笔」，而表标题天然带「（合计 4,513,064.91 元…）」⇒ 任何"表 N"子项都自动判「已核对」（实测：疑点15 表1/表2/表3 全假通过） | ① 结论标记只保留**核对动作/结果**词（去掉会计词）；② 结论只在**分析性文本**里找，**表格标题与表内数据行不算分析**（`problem_texts()` 分 `mention` / `analysis` 两路） |
| ④ | **判据输入不同源**：配置初值在生成器里用**整篇正文**算，报告端却只用**要件 bullet**算 ⇒ 同一子项配置写「已核对」、报告写「未核对」，且 gap 文案里出现"配置声明/判别性词根"这类**内部术语**（企业看不懂） | 判据源唯一权威 = `problem_texts(problem)`，生成器与报告端**都调它**；gap 一律用企业看得懂的话 |

## 口径
- 子项清单来自 `config/child_items.json`（新增子项只加一行）；枚举规则唯一权威
  `enumerate_children()`（生成器 `scripts/_gen_child_items.py` 与门禁共用同一函数）。
- **枚举源 ⊇ 判据源**：枚举除了报告正文，还扫**本项绑定发现的明细**（`finding_texts`）——
  发现明细里说了、报告正文没给结论 ⇒ 判「未核对」（这正是用户点名的疑点15 情形）。
- 取不到子项清单 ⇒ 返回空（**不臆造**），但由门禁保证"有清单就必须逐项分析"。
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

VERSION = "1.1.0"

_ROOT = Path(__file__).resolve().parent.parent
_CFG = _ROOT / "config" / "child_items.json"
_CACHE: Optional[Dict[str, Any]] = None

#: 子项状态（唯一词表；报告与门禁共用）
STATUS_CHECKED = "已核对"
STATUS_UNCHECKED = "未核对"
STATUS_NEED = "须核对"
STATUS_MISSING = "资料缺失"
STATUSES = (STATUS_CHECKED, STATUS_UNCHECKED, STATUS_NEED, STATUS_MISSING)

#: 被"跳过"的措辞（以这些为由不分析 ⇒ 判未分析）
SKIP_PHRASES = ("不参与本项", "不参与销项", "不属于本项", "不在本项范围", "本项不含",
                "不纳入本项", "另属他项", "不予考虑")

#: 结论性表述（**只放"逐条核对动作/结果"**，三类词一律不放，每次都踩过坑）：
#:   · 会计词「合计/共/逐笔/笔数」 —— 表格标题天然带，会把"列了张表"当"做了分析"（模块头 ③）；
#:   · 状态词「已入账/未入账/已报销/未报销/已冲账」 —— **事项名称与要件文本**里就有
#:     （如「涉嫌虚列成本、发票**未入账**或接受虚开发票」），实测把 RL-PTY-001 表1–表4
#:     全部变成"已核对"；
#:   · 报告自身统计句「已单独核对 N 条」 —— 是清单级汇总，不是对某个子项的结论。
#:   · **本项级动作句**（"共6名员工55组配对记录纳入比对"）—— 它是对**整个疑点**的核对动作，
#:     不是对某个子项的结论；实测把 RL-PAY-001 的 6 个子项（含"住房公积金"这种正文确实
#:     一句话都没分析的）全部变成"已核对"。宁缺勿错 ⇒ 该类词一律不收；真被分析过的子项
#:     由人工复核后在正文补一句带"经核对/已核对"的结论即可，不靠模糊词放行。
#: 标记集**按实测收缩**（每加一个词都要先数它在真实报告里出现几次、出现在哪）：
#: 实测真实报告里「经核对/已核对/已查验/经查/笔数为/供应商为/对应供应商/逐笔核对」全部 0 次；
#: 只有两类词真正出现 ——
#:   · 「读数来自本项X」（1 次，RL-CIT-007）＝ 引擎确实读到了该子项的数据 ⇒ **算结论**；
#:   · 「…外部数据的核实结果」（2 次）＝ **本项级套话**（"能否成立取决于外部数据的核实结果"）
#:     ⇒ 实测把 RL-CIT-007「分项扣除限额测算」误判成已核对，**已剔除**。
CONCLUSION_MARKERS = (
    "经核对", "已核对", "已查验", "经查", "读数来自本项",
    "已做转出", "已转出", "未见转出", "笔数为", "供应商为", "对应供应商", "逐笔核对",
)

#: 需补资料类表述
GAP_MARKERS = ("须补充", "待补充", "需补充", "请提供", "缺少", "缺失", "未取得",
               "无法核实", "待核实资料", "未提供")

#: 「被口径跳过」的缺口前缀（**唯一权威**，且**必须幂等**）。
#: 实测事故：生成器已把该前缀写进配置的 `gap`，报告端再跑一次 `analyze_status` 又拼一遍
#: ⇒ 报告里出现「以不参与本项口径为由跳过…；以不参与本项口径为由跳过…」重复句。
#: 去重判据用**不含书名号的核心片段**（报告净化会把「」剥掉，用带「」的原文判会失效）。
_SKIP_NOTE = "以「不参与本项口径」为由跳过、未单独分析；"
_SKIP_NOTE_CORE = "为由跳过、未单独分析"

#: 归一化时剥离的标点（**desc 与正文必须同一套**，见模块头 ①）
_PUNCT_RE = re.compile(r"[（）()【】\[\]、，,。；;：:「」\"'/\\|]")

#: 判"提到"的最小 4-gram 重合率
_MENTION_RATIO = 0.5
_GRAM = 4

#: 对象级事项关键词（"什么钱、谁垫的、和谁往来"）—— 新增同类只加一个词
OBJECT_ITEM_KWS = ("个人垫付", "垫付", "代付", "预付款", "其他应付款", "其他应收款",
                   "往来款", "借款", "备用金", "押金", "保证金", "代收代付")

#: 子项清单的引导句（**自引用屏障**，必须与 `render_child_list()` 产出的引导句逐字一致）。
#: ★ 为什么必须挡住：子项清单是**本模块自己的产物**，它被写进报告后又会进入 `problem_texts()`。
#:   实测（2026-10-07）：上一轮清单里的「未核对原因与需补资料：配置声明为**已核对**，
#:   但正文未见该子项的核对证据」被当成"正文有结论"的证据 ⇒ 清单**自己证明自己**，
#:   把 RL-PTY-001 表3/表4 判成"已核对"。判据输入必须排除派生文本。
CHECKLIST_LEAD = "本项子项与关联项逐项核对如下"

#: 清单条目的状态标记（识别"派生文本"的第二判据；清单条目以「；」分隔 ⇒ 可整段剔除）
_CHILD_STATUS_MARKS = ("[未核对]", "[须核对]", "[已核对]", "[资料缺失]", "[关联项")


def _strip_derived(s: str) -> str:
    """剔除**本模块自己的产物**（唯一实现，见 `CHECKLIST_LEAD` 自引用屏障）。

    按句读切段，凡含清单引导句或清单状态标记的段整段丢弃 ——
    这样"清单文本"无论被拼进哪一段，都不会成为判据。

    ⚠ 切句必须用**唯一权威** `engine.sentencekit.split_sentences`：
      朴素 `re.split(r"[；;。\\n]")` 会在**括号内**切错（门禁
      `check_...` 直接报 ERROR，实测第 124 行被抓出来）—— 括号不闭合的残句
      会让"含清单引导句的段"判断失真。另补切英文 `;`（中文清单用「；」，数据里两种都可能出现）。
    """
    if not s:
        return s
    if CHECKLIST_LEAD not in s and not any(m in s for m in _CHILD_STATUS_MARKS):
        return s
    try:
        from engine.sentencekit import split_sentences as _split
        segs = _split(s)
    except Exception:                     # 留痕：词表不可用时退化为整段保留（绝不静默丢内容）
        return s
    keep = [seg for seg in segs
            for seg in seg.split(";")
            if CHECKLIST_LEAD not in seg and not any(m in seg for m in _CHILD_STATUS_MARKS)]
    return "；".join(keep)

#: 各类子项的**默认缺口说明**（企业看得懂的话；生成器写入配置，报告端原样引用）。
#: ★ 模板铁律（2026-10-07 实测修订）：**不得要求企业补"系统已经给出的东西"**。
#:   首版写"须写明明细对象的名称、笔数、金额"，而报告上方那张表已经列了名称/笔数/金额
#:   （触发情况句里还带"本表 36 行、合计 4,513,064.91 元"）⇒ 等于让企业重复提供已有内容。
#:   现改为：**承认已列示什么**，只索要真正缺的那一项（逐项核对结论）。
GAP_TPL_DEFAULT = "本子项未在正文单独给出核对结论；须补充该子项本企业的实际情况、依据资料与金额。"
GAP_TPL_FAMILY = ("本同族子项未在正文单独给出核对结论；须说明本企业在该子项上的实际情况"
                  "（涉及对象或人员、笔数、金额、所属期间）、依据资料与处理口径。")
GAP_TPL_TABLE = ("本表已列示明细 %s；尚未给出逐行核对结论"
                 "（每一行是否核对一致、存在差异的差异原因与金额）。"
                 "请补充逐行核对结论，或由企业按行确认。")
GAP_TPL_SIDE = ("该方向明细已在报告列示；尚未给出本方向的核对结论 —— 须说明该方向发票的税务处理"
                "（进项侧是否已做进项税额转出、转出金额与凭证；销项侧是否属正常冲销且金额匹配）。")
GAP_TPL_CRITERION = "本构成要件未在正文单独给出核对结论；须补独立数据源与逐条核对结论。"
GAP_TPL_RELATED = ("该关联项必须在本项单独说明结论（或注明未纳入本项的理由），"
                   "不得以「不参与本项口径」跳过。")

#: 配置默认项（可被 `config/child_items.json` 的 `options` 覆盖；**改数据不改逻辑**）
#: `include_criteria`：构成要件是否也登记为子项。默认 **False** ——
#:   要件已由 `engine/constituent_checkpoint.py` **原位**逐条给出「独立数据源｜数据源状态｜
#:   核对结论」，再登记为子项会让同一件事在报告里出现两遍（用户明确反对重复冗余）。
#:   交换条件是门禁④：**每条要件条目必须自带结论 + 独立数据源**，否则 ERROR。
_DEFAULT_OPTIONS: Dict[str, Any] = {"include_criteria": False}


def options() -> Dict[str, Any]:
    """本 Skill 的可配置项（唯一读取点；生成器会把旧配置的 `options` 原样带下去）。"""
    o = load_config().get("options")
    o = o if isinstance(o, dict) else {}
    return {**_DEFAULT_OPTIONS, **o}


def _gap_object_item(kind: str) -> str:
    """对象级事项的缺口模板（用户规格原文：须说明对应供应商、笔数、是否已报销冲账）。

    ⚠ 不用 markdown 强调符：报告正文一律过 `_naturalize_report_text` 去星号，
      但那是"正则兜底"，真实正文不该依赖它（本项目铁律：正文禁 markdown）。
    """
    return ("本项须说明：%s的对应供应商或对方名称、笔数、是否已报销冲账或入账；"
            "本轮正文未逐项说明。" % kind)


def load_config() -> Dict[str, Any]:
    global _CACHE
    if _CACHE is None:
        try:
            raw = json.loads(_CFG.read_text(encoding="utf-8"))
            _CACHE = raw if isinstance(raw, dict) else {}
        except Exception:                 # 留痕：配置缺失 ⇒ 空表（门禁按"有清单才校验"处理）
            _CACHE = {}
    return _CACHE


def reload_config() -> Dict[str, Any]:
    """丢掉缓存重新读（自检/门禁在改过配置后调用，避免读到旧表）。"""
    global _CACHE
    _CACHE = None
    return load_config()


def entry_of(parent_risk_code: Any) -> Optional[Dict[str, Any]]:
    pc = str(parent_risk_code or "").strip()
    if not pc:
        return None
    for r in (load_config().get("risks") or []):
        if isinstance(r, dict) and str(r.get("parent_risk_code")) == pc:
            return r
    return None


def children_of(parent_risk_code: Any) -> List[Dict[str, Any]]:
    e = entry_of(parent_risk_code) or {}
    return [c for c in (e.get("child_items") or []) if isinstance(c, dict)]


def related_of(parent_risk_code: Any) -> List[Dict[str, Any]]:
    e = entry_of(parent_risk_code) or {}
    return [r for r in (e.get("related_items") or []) if isinstance(r, dict)]


# --------------------------------------------------------------------------
# 归一化 / 关键词 / 匹配（唯一权威）
# --------------------------------------------------------------------------
def _norm(s: Any) -> str:
    return re.sub(r"\s+", "", str(s or ""))


def _strip_punct(s: str) -> str:
    """剥标点（**唯一实现**；desc 与正文两侧都必须过它，见模块头 ①）。"""
    return _PUNCT_RE.sub("", str(s or ""))


def norm_key(s: Any) -> str:
    """子项身份键（去空白 + 去标点）——登记/去重/门禁比对**只用它**。"""
    return _strip_punct(_norm(s))


def _keywords(desc: Any) -> List[str]:
    """从子项描述里提取判定关键词（中文不切词 ⇒ 取 2-gram + 显式关键词）。"""
    s = _strip_punct(_norm(desc))
    kws = [w for w in re.findall(r"[0-9A-Za-z]+|[一-龥]{2,}", s)]
    grams = {s[i:i + 2] for i in range(len(s) - 1)} if len(s) >= 2 else set()
    return sorted(set(kws) | grams, key=len, reverse=True)


def _grams(s: str, n: int = _GRAM) -> set:
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def _as_bag(text_blob: Any) -> Dict[str, str]:
    """判据文本载体。既可传字符串（两侧同一份），也可传 `problem_texts()` 的两路载体。

    为什么要两路（模块头 ③）：表格标题/表内数据行只能证明"报告里出现过该子项"，
    **不能**证明"报告分析过该子项" —— 后者只能在**分析性文本**（正文段落与条目）里找。
    """
    if isinstance(text_blob, dict):
        m = str(text_blob.get("mention") or "")
        a = str(text_blob.get("analysis") or "")
        return {"mention": _strip_punct(_norm(_strip_derived(m))),
                "analysis": _strip_punct(_norm(_strip_derived(a)))}
    s = _strip_punct(_norm(_strip_derived(str(text_blob or ""))))
    return {"mention": s, "analysis": s}


def mentions(text_blob: Any, child: Dict[str, Any], min_hits: int = 0) -> bool:
    """正文是否**真的**提到该子项（4-gram 重合率 ≥ `_MENTION_RATIO`）。

    ★ 判据演进（都留痕，防止再退回旧坑）：
      · 首版"命中 ≥3 个关键词"——词表里大量 2-gram，只要有个常见二字词出现就算命中
        ⇒ 把"标题级提及"误判为已分析（实测疑点3「私户发薪」子项：正文 0 次出现却判已核对）。
      · 二版"命中率 ≥50% + 至少一个 len≥4 关键词命中"——核心词要求会被**拼接型描述**
        卡死（生成器把"进项侧"+"进项发票…"拼成一条描述，正文只有后半段）⇒ 假阴性；
        且两侧标点不对称（正文里的"、"没剥）⇒ 4-gram 全部落空。
      · **现版**：两侧都过 `_strip_punct` 后比 4-gram 重合率。单一判据、可解释、无拼接假设。
    """
    desc = _strip_punct(_norm(child.get("desc")))
    blob = _as_bag(text_blob)["mention"]
    if not desc or not blob:
        return False
    if len(desc) < _GRAM:                      # 极短描述：退化为子串包含
        return desc in blob
    g = _grams(desc)
    if not g:
        return False
    hit = sum(1 for k in g if k in blob)
    if min_hits > 1 and hit < min_hits:        # 兼容旧调用（显式要求更多命中）
        return False
    return (hit / len(g)) >= _MENTION_RATIO


def has_skip_reason(text_blob: Any, child: Dict[str, Any]) -> bool:
    """正文是否**以"不参与本项"为由跳过**该子项（用户点名的疑点1 情形）。"""
    blob = _as_bag(text_blob)["mention"]
    return mentions(text_blob, child) and any(p in blob for p in SKIP_PHRASES)


def has_conclusion(text_blob: Any, child: Dict[str, Any], window: int = 80) -> bool:
    """正文是否对该子项给出了**结论性分析**。

    ★ 三条硬要求（每条都对应一次实测事故）：
      ① **先过 `mentions`**（防止"只要描述里任一关键词出现在某处"就去找结论窗口）；
      ② 结论标记只在**该子项出现的附近窗口**内找，**不能**全篇找
         （否则整段文本里的"经核对"会让**任何**被提到的子项都判"已核对"）；
      ③ 只在**分析性文本**（正文段落与条目）里找 —— 表格标题与表内数据行不算分析
         （否则表标题的「（合计 4,513,064.91 元…）」会把"表 N"子项全部变成"已核对"）。
    """
    if not mentions(text_blob, child):
        return False
    blob = _as_bag(text_blob)["analysis"]
    kws = _keywords(child.get("desc"))
    if not kws or not blob:
        return False
    for kw in kws:
        start = 0
        while True:
            i = blob.find(kw, start)
            if i < 0:
                break
            lo = max(0, i - window)
            hi = min(len(blob), i + len(kw) + window)
            seg = blob[lo:hi]
            if any(m in seg for m in CONCLUSION_MARKERS):
                return True
            start = i + len(kw)
    return False


def analyze_status(child: Dict[str, Any], text_blob: Any) -> Dict[str, Any]:
    """判定单个子项的**实际**核对状态（唯一实现）。

    规则（宁缺勿错）：
      ① 正文明确"跳过"（不参与本项口径）⇒ `未核对`，并对"关联项"额外标注必须单独分析；
      ② 正文提到且有结论性表述 ⇒ `已核对`；
      ③ 正文提到但无结论 ⇒ `须核对`（列了没分析）；
      ④ 正文未提到 ⇒ 取配置声明状态；配置也没写 ⇒ `未核对`（列了却没进正文）。
    """
    declared = str(child.get("status") or "").strip()
    gap = str(child.get("gap") or "").strip()
    conclusion = str(child.get("conclusion") or "").strip()
    out = {"id": str(child.get("id") or ""), "desc": str(child.get("desc") or ""),
           "declared_status": declared, "status": "", "conclusion": conclusion,
           "gap": gap, "skipped_by_caliber": False}
    if has_skip_reason(text_blob, child):
        out.update({"status": STATUS_UNCHECKED, "skipped_by_caliber": True})
        # 跳过原因必须**写在缺口里**（否则报告只看到"未核对"，看不到"因为被口径跳过"）；
        # 且**幂等**（配置里已带该前缀时不再叠一次，见 `_SKIP_NOTE` 注释）。
        if _SKIP_NOTE_CORE not in out["gap"]:
            out["gap"] = _SKIP_NOTE + (out["gap"] or "请补齐该子项的核对结论或写明所需资料。")
        return out
    if has_conclusion(text_blob, child):
        out["status"] = STATUS_CHECKED
        # 已核对 ⇒ 不展示缺口（配置里的模板缺口只在"未核对"时才用；配置本身仍保留该列，
        # 便于状态回退时立刻有话可说，也避免"配置没写 gap"成为静默漏洞）。
        out["gap"] = ""
        return out
    if mentions(text_blob, child):
        out["status"] = STATUS_NEED
        if not out["gap"]:
            out["gap"] = "正文已列示但未给出核对结论，须补核对结论或所需资料。"
        return out
    # ★★ 2026-10-07（判据收紧）：**配置里声明「已核对」必须被正文证据支持**。
    #   事故：疑点3 风险族的子项「待核线索：公私混同发薪/私户支付薪酬」在正文里
    #   「私户发薪」出现 **0 次**，却因"声明=已核对"而被判已核对 ⇒ 假通过。
    #   口径：声明只作**初值**，最终状态以正文为准；无证据即判「须核对」并写 gap。
    if declared == STATUS_CHECKED:
        out["status"] = STATUS_NEED
        if not out["gap"]:
            out["gap"] = ("本子项未在正文给出核对结论（判别性词根未命中）⇒ "
                          "须补核对结论或所需资料。")
        return out
    out["status"] = declared if declared in STATUSES else STATUS_UNCHECKED
    if out["status"] != STATUS_CHECKED and not out["gap"]:
        out["gap"] = GAP_TPL_DEFAULT
    return out


def analyze_related(item: Dict[str, Any], text_blob: Any) -> Dict[str, Any]:
    """关联项分析判定（`analysis_required=true` 的不得跳过）。

    ★ 两个来源，语义不同（别混）：
      · `analysis_output=True`（配置由本项 `related_analyses` 派生）：**该关联分析的产出
        已经在报告里**（同级章节有 summary/data）⇒ 视为已单独分析；
      · 否则以本项正文是否给出结论为准。
      **两者都不豁免"被口径跳过"**——凡出现"不参与本项口径/占比"即以跳过论处（规则②）。
    """
    req = bool(item.get("analysis_required"))
    skipped = has_skip_reason(text_blob, item)
    analysed = bool(item.get("analysis_output")) or has_conclusion(text_blob, item)
    return {"id": str(item.get("id") or ""), "desc": str(item.get("desc") or ""),
            "analysis_required": req, "analysed": bool(analysed and not skipped),
            "skipped_by_caliber": bool(skipped)}


# --------------------------------------------------------------------------
# 判据文本（**唯一权威**：生成器初值 与 报告端判定 必须同一份）
# --------------------------------------------------------------------------
def _paragraph_texts(problem: Dict[str, Any], with_data: bool) -> List[str]:
    """本项呈现文本。`with_data=False` ⇒ 只取**分析性文本**（正文/条目/tail）。

    `with_data=True` ⇒ 再并上表格标题与表内数据行（只用于"报告里出现过"的判定，
    不用于"是否分析过"的判定 —— 见模块头 ③）。

    ⚠ **本模块自己的产物必须排除**（见 `CHECKLIST_LEAD`）：子项清单会被写回报告，
      再进本函数就会"自己证明自己"。
    """
    out: List[str] = []

    def _push(v: Any) -> None:
        s = _strip_derived(str(v or ""))
        if s.strip():
            out.append(s)

    for np_ in (problem.get("narrative_paragraphs") or []):
        if not isinstance(np_, dict):
            continue
        for k in ("text", "tail"):
            _push(np_.get(k))
        for b in (np_.get("bullets") or []):
            _push(b)
        if with_data:
            for t in (np_.get("detail_tables") or []):
                if not isinstance(t, dict):
                    continue
                _push(t.get("title"))
                for row in (t.get("rows") or []):
                    if isinstance(row, dict):
                        _push(" ".join(str(v) for v in row.values()))
                    elif isinstance(row, (list, tuple)):
                        _push(" ".join(str(v) for v in row))
    return out


def problem_texts(problem: Dict[str, Any]) -> Dict[str, str]:
    """本项判据文本载体（唯一权威）。

    返回 `{"mention": 报告里出现过的全部文本, "analysis": 报告做过分析的全部文本}`。
    ⚠ 生成器（配置初值）与报告端（子项清单）**都必须调它** —— 历史上两处各取一段，
      导致同一子项"配置写已核对、报告写未核对"（模块头 ④）。
    """
    return {"mention": " ".join(_paragraph_texts(problem, True)),
            "analysis": " ".join(_paragraph_texts(problem, False))}


def finding_texts(rep: Dict[str, Any], redline_id: Any) -> List[str]:
    """本项**绑定发现**的明细文本（枚举用，不作判据源）。

    为什么要它（用户点名的疑点15）：`个人垫付116,504.85元` 只出现在**发现明细**里
    （`all_findings[].description/detail`），报告正文一个数都没给结论 ——
    枚举源不扫它 ⇒ 这个子项**根本不会进清单**，"列了不分析"就永远查不出来。
    """
    out: List[str] = []
    rid = str(redline_id or "")
    if not isinstance(rep, dict) or not rid:
        return out
    fs = rep.get("all_findings")
    if not isinstance(fs, list):
        fs = ((rep.get("scenario_execution") or {}).get("findings") or [])
    if not isinstance(fs, list):
        return out
    for f in fs:
        if not isinstance(f, dict) or str(f.get("redline_id") or "") != rid:
            continue
        for k in ("description", "detail"):
            v = f.get(k)
            if isinstance(v, str) and v.strip():
                out.append(v)
    return out


# --------------------------------------------------------------------------
# 子项枚举（**唯一权威**：生成器与门禁共用）
# --------------------------------------------------------------------------
_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"


def problem_key(problem: Dict[str, Any]) -> str:
    """本项在子项配置里的**绑定键**（唯一权威）：红线编号 > 规则编号 > **完整标题**（兜底）。

    ★ 兜底到标题是必须的（实测）：全量产物里存在**既无 redline_id 也无 rule_id** 的疑点
      （如「资金回流/公私混同」族，实测 seq=2 带 5 个族成员）。只用红线编号作键 ⇒
      这些疑点的子项**永远登记不上**；而门禁按同一规则枚举又要求"必须登记"⇒ 自相矛盾、
      永远报红。口径与 `config/risk_conditions.json` 的 `aliases` 兜底一致（键取完整标题）。
    """
    if not isinstance(problem, dict):
        return ""
    return str(problem.get("redline_id") or problem.get("rule_id")
               or problem.get("title") or "").strip()


#: 「该条构成要件**已在原位**给出独立核对结论」的标志（数据源 + 结论任一形态）。
#: ★ 口径（防同一件事说两遍）：构成要件类由 `engine/constituent_checkpoint.py` **原位**逐条
#:   给出「独立数据源｜数据源状态｜核对结论」，报告里 ①…⑤ 每条 bullet 都自带结论与所需资料
#:   ⇒ **不再重复登记为子项**（否则报告里同一件事出现两遍）。
#:   但判据是**数据驱动**的：哪天某条要件在原位丢了结论，它就会自动落进子项清单并带上 gap
#:   ——「列了却没分析」依然跑不掉（门禁 ④ 另有原位结论断言，双保险）。
_CRITERION_CONCLUDED = ("符合情形", "未发现符合", "未形成核对结论", "未单独核对",
                        "未达数值门槛", "独立数据源")

_OBJ_ITEM_RE = re.compile(
    r"(%s)[^，。；;、\n]{0,14}?([\d,]+\.\d{2})\s*元" % "|".join(OBJECT_ITEM_KWS))


def _enum_texts(problem: Dict[str, Any], extra_texts: Sequence[Any] = ()) -> List[str]:
    txts = _paragraph_texts(problem, True) + [str(t) for t in (extra_texts or []) if str(t or "").strip()]
    return txts


def enumerate_children(problem: Dict[str, Any],
                       extra_texts: Sequence[Any] = ()) -> Dict[str, List[Dict[str, Any]]]:
    """从**本项真实数据**枚举子项与关联项（唯一规则实现）。

    来源（新增同类只需在数据里出现，不改逻辑分支）：
      ① 风险族成员（同族子项）
      ② 本项明细表（每表一项）
      ③ 分述文本/表标题里的**按方向分列**（销项侧/进项侧）
      ④ 未被判"符合情形/未发现符合"的**构成要件**（bullet 与要件核对表两条入口）
      ⑤ **对象级事项**（垫付/代付/预付款/往来款/借款/备用金… + 金额）
         —— 扫报告正文、表内数据行**以及本项绑定发现的明细**
      ⑥ 关联项：本项 `related_analyses`（系统已产出的跨项分析），**不与子项重复登记**
    """
    kids: List[Dict[str, Any]] = []
    seen: set = set()

    def _add(desc: str, source: str, gap: str) -> None:
        d = str(desc or "").strip()
        if not d:
            return
        k = norm_key(d)
        if not k or k in seen:
            return
        seen.add(k)
        kids.append({"id": "S%d" % (len(kids) + 1), "desc": d[:90],
                     "gap": gap, "_source": source})

    # ① 风险族成员
    for m in (problem.get("family_members") or []):
        if _is_dedup_ref(m):                 # ★ 跳过被去重替换的引用语
            continue
        if isinstance(m, dict) and str(m.get("title") or "").strip():
            _add(m.get("title"), "family_members", GAP_TPL_FAMILY)
    # ② 明细表（缺口里带上"本表几行"——不得让企业重复提供报告已经列出的内容） + ③ 方向分列
    for np_ in (problem.get("narrative_paragraphs") or []):
        if not isinstance(np_, dict):
            continue
        for t in (np_.get("detail_tables") or []):
            if not isinstance(t, dict):
                continue
            title = str(t.get("title") or "").strip()
            if not title or "构成要件" in title:
                continue
            _rows = t.get("rows")
            _n = len(_rows) if isinstance(_rows, list) else 0
            _add(title, "detail_table",
                 GAP_TPL_TABLE % ("%d 行" % _n if _n else "（行数未取到）"))
            for side, kw in (("销项侧", "销项发票"), ("进项侧", "进项发票")):
                if kw in title:
                    _add("%s%s" % (side, title), "direction_split", GAP_TPL_SIDE)
    # ③-b 分述文本里的按方向分列
    for _txt in _enum_texts(problem):
        for _m in re.finditer(r"(销项发票|进项发票)\s*(\d+)\s*行、金额合计\s*([\d,]+\.\d{2})\s*元",
                              _txt):
            side, nrow, amt = _m.group(1), _m.group(2), _m.group(3)
            _add("%s%s %s 行、金额合计 %s 元" % ("销项侧" if side == "销项发票" else "进项侧",
                                                 side, nrow, amt),
                 "direction_split_text", GAP_TPL_SIDE)
    # ④ 构成要件（bullet 入口）—— **已在原位给出结论的不重复登记**（见 _CRITERION_CONCLUDED）；
    #   且整体受 `options().include_criteria` 开关控制（默认关闭，口径见 _DEFAULT_OPTIONS）
    if options().get("include_criteria"):
        for np_ in (problem.get("narrative_paragraphs") or []):
            if not isinstance(np_, dict):
                continue
            for b in (np_.get("bullets") or []):
                s2 = str(b or "")
                if not s2 or s2[0] not in _CIRCLED:
                    continue
                if any(k in s2 for k in _CRITERION_CONCLUDED):
                    continue
                _add(s2.split("（")[0][1:].strip(), "determination_criteria", GAP_TPL_CRITERION)
        # ④-b 构成要件（要件核对表入口）—— 同上：结论列非空的照原位算，不重复登记
        for np_ in (problem.get("narrative_paragraphs") or []):
            if not isinstance(np_, dict):
                continue
            for t in (np_.get("detail_tables") or []):
                if "构成要件" not in str((t or {}).get("title") or ""):
                    continue
                for row in (t.get("rows") or []):
                    if isinstance(row, dict):
                        joined = " ".join(str(v) for v in row.values())
                        conc = str(row.get("核对结论") or "")
                        cells = [str(v) for v in row.values()]
                    else:
                        cells = [str(c) for c in (row if isinstance(row, (list, tuple)) else [])]
                        joined = " ".join(cells)
                        conc = ""
                    if not joined:
                        continue
                    if any(k in joined for k in _CRITERION_CONCLUDED) or conc.strip():
                        continue          # 原位已有结论 ⇒ 不重复登记
                    desc = ""
                    for c in cells:
                        if c and len(c) > 6 and not c.startswith("第"):
                            desc = c
                            break
                    _add(desc, "criteria_table", GAP_TPL_CRITERION)
    # ⑤ 对象级事项（正文 + 表内数据行 + 绑定发现明细）
    for _txt in _enum_texts(problem, extra_texts):
        for _m in _OBJ_ITEM_RE.finditer(_txt):
            kind, amt = _m.group(1), _m.group(2)
            try:
                if float(amt.replace(",", "")) == 0:
                    continue          # 0 元 = 无此项，不立子项
            except Exception:         # 留痕：取不到数值就照常登记（宁可多列，不漏项）
                pass
            _add("%s %s 元" % (kind, amt), "object_item", _gap_object_item(kind))
    # ⑥ 关联项（不与子项重复）
    rels: List[Dict[str, Any]] = []
    for a in (problem.get("related_analyses") or []):
        if not isinstance(a, dict):
            continue
        title = str(a.get("title") or "").strip()
        if not title or norm_key(title) in seen:
            continue
        seen.add(norm_key(title))
        _d = a.get("data") if isinstance(a.get("data"), dict) else {}
        _out = bool(str(_d.get("summary") or "").strip()) or bool(_d.get("available"))
        rels.append({"id": "R%d" % (len(rels) + 1), "desc": title[:90],
                     "analysis_required": True, "analysis_output": _out})
    return {"child_items": kids, "related_items": rels}


# --------------------------------------------------------------------------
# 审计 / 渲染
# --------------------------------------------------------------------------
def audit(parent_risk_code: Any, narrative_texts: Any) -> Dict[str, Any]:
    """父风险 → 子项/关联项完整性的**唯一审计入口**。

    返回（**用户规格要求的输出字段**）：
      parent_risk_code / child_items / child_status / child_conclusion / child_gap
      / related_items / related_analysis / unanalysed / issues
    """
    blob = narrative_texts if isinstance(narrative_texts, dict) else \
        _as_bag(" ".join(str(t or "") for t in (narrative_texts or [])))
    kids = children_of(parent_risk_code)
    rels = related_of(parent_risk_code)
    cstat: Dict[str, Any] = {}
    for k in kids:
        r = analyze_status(k, blob)
        cstat[r["id"]] = r
    ran = {str(r.get("id") or ""): analyze_related(r, blob) for r in rels}
    unanalysed = [k for k, v in cstat.items() if v["status"] != STATUS_CHECKED]
    rel_bad = [k for k, v in ran.items() if v["analysis_required"] and not v["analysed"]]
    issues: List[Dict[str, Any]] = []
    for k, v in cstat.items():
        if v["status"] != STATUS_CHECKED:
            issues.append({"kind": "child_unanalysed" if not v["skipped_by_caliber"] else "child_skipped",
                           "level": "ERROR", "child": k, "status": v["status"],
                           "detail": "子项「%s」未给出核对结论（%s）：%s"
                                     % (v["desc"][:40], v["status"], v["gap"][:80])})
    for k, v in ran.items():
        if v["analysis_required"] and not v["analysed"]:
            issues.append({"kind": "related_unanalysed", "level": "ERROR", "child": k,
                           "detail": "关联项「%s」必须单独分析（不得以口径为由跳过），当前未分析。"
                                     % v["desc"][:40]})
    return {
        "parent_risk_code": str(parent_risk_code or ""),
        "child_items": kids,
        "child_status": {k: {"status": v["status"], "skipped_by_caliber": v["skipped_by_caliber"]}
                         for k, v in cstat.items()},
        "child_conclusion": {k: v["conclusion"] for k, v in cstat.items()},
        "child_gap": {k: v["gap"] for k, v in cstat.items() if v["gap"]},
        "related_items": rels,
        "related_analysis": ran,
        "unanalysed": unanalysed,
        "related_unanalysed": rel_bad,
        "issues": issues,
    }


def render_child_list(parent_risk_code: Any, narrative_texts: Any) -> str:
    """报告用「子项核对清单」文本（**逐一列示 + 状态 + 未核对原因**）。

    ★ 单行输出（**不得含换行**）：报告段落把换行渲染成「 ， 」，实测出现过
      「…所需资料）： ， [未核对] …」这种像乱码的文本 ⇒ 一律用中文标点单行成句。
    """
    a = audit(parent_risk_code, narrative_texts)
    if not a["child_items"] and not a["related_items"]:
        return ""
    parts = [CHECKLIST_LEAD + "（每项均给出状态，未核对的写明原因与所需资料）："]
    for k in a["child_items"]:
        cid = str(k.get("id") or "")
        st = (a["child_status"].get(cid) or {}).get("status") or STATUS_UNCHECKED
        seg = "[%s] %s" % (st, str(k.get("desc") or "")[:60])
        if st != STATUS_CHECKED:
            seg += "，未核对原因与需补资料：" + (a["child_gap"].get(cid) or GAP_TPL_DEFAULT)
        parts.append(seg)
    for r in a["related_items"]:
        v = a["related_analysis"].get(str(r.get("id") or "")) or {}
        parts.append("[关联项·%s] %s"
                     % ("已单独分析" if v.get("analysed") else "未单独分析（不得以口径为由跳过）",
                        str(r.get("desc") or "")[:60]))
    return "；".join(parts) + "。"


def checklist_text(problem: Dict[str, Any], extra_texts: Sequence[Any] = ()) -> str:
    """按**本项定稿数据**产出子项核对清单（报告端唯一调用点）。

    判据源 = `problem_texts(problem)`（与生成器初值同源，根因④）。
    """
    if not isinstance(problem, dict):
        return ""
    return render_child_list(problem_key(problem), problem_texts(problem))


def audit_for_problem(problem: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    """**一次计算**同时产出「结构化审计块」与「清单文本」（报告端唯一调用点）。

    ★ 为什么必须一次算（本项目铁律『同源』）：
      文本与结构化数据若各算一遍，就会出现"清单里写未核对、结构里写已核对"这种**两张皮**，
      而两者都"看起来对"。这里用**同一份 `problem_texts(problem)`** 算一次、
      再分别输出，结构上不可能漂移。

    返回的审计块字段**完全按用户规格**：
      parent_risk_code / child_items / child_status / child_conclusion / child_gap
      / related_items / related_analysis（+ unanalysed / related_unanalysed / issues）
    """
    if not isinstance(problem, dict):
        return {}, ""
    bag = problem_texts(problem)
    key = problem_key(problem)
    a = audit(key, bag)
    return a, render_child_list(key, bag)


def config_completeness() -> List[Dict[str, Any]]:
    """配置自检：每个子项必须有 status；非"已核对"必须有 gap（用户规格 1/3 条）。

    另检 `options`：**未知键一律报错** —— 否则用户改了开关却发现没生效（拼错 key 静默无效），
    与"改了看不出生效＝事故"同一条铁律。
    """
    out: List[Dict[str, Any]] = []
    _unk = sorted(set((load_config().get("options") or {})) - set(_DEFAULT_OPTIONS))
    for k in _unk:
        out.append({"parent": "-", "id": "-", "kind": "unknown_option",
                    "detail": "options 里的「%s」不是本 Skill 认识的配置项（可选：%s）⇒ 改它不会生效"
                              % (k, "、".join(sorted(_DEFAULT_OPTIONS)))})
    for r in (load_config().get("risks") or []):
        if not isinstance(r, dict):
            continue
        pc = str(r.get("parent_risk_code") or "")
        for c in (r.get("child_items") or []):
            if not isinstance(c, dict):
                continue
            if str(c.get("status") or "") not in STATUSES:
                out.append({"parent": pc, "id": c.get("id"), "kind": "status_missing",
                            "detail": "子项 %s 未标注合法状态（应属 %s）" % (c.get("id"), "、".join(STATUSES))})
            elif str(c.get("status")) != STATUS_CHECKED and not str(c.get("gap") or "").strip():
                out.append({"parent": pc, "id": c.get("id"), "kind": "gap_missing",
                            "detail": "子项 %s 状态为「%s」但未写 gap（原因+需补资料）" % (c.get("id"), c.get("status"))})
        for it in (r.get("related_items") or []):
            if isinstance(it, dict) and "analysis_required" not in it:
                out.append({"parent": pc, "id": it.get("id"), "kind": "analysis_required_missing",
                            "detail": "关联项 %s 未声明 analysis_required" % it.get("id")})
    return out


#: ★ 2026-10-08 收敛：去重引用语标记与判定统一到 engine/dupkit.py（唯一权威）。
#: 本模块只**薄转发**，不自持字面量（此前与 report_pipeline / data_source_status
#: 各写一遍，改字即静默失效）。产出方 report_pipeline 亦引用同一常量。
from engine.dupkit import is_dedup_ref as _is_dedup_ref  # noqa: E402


def audit_product(rep: Dict[str, Any]) -> List[Dict[str, Any]]:
    """**产物级自检**：报告正文/明细表/绑定发现明细里出现的子项，必须已登记到配置。

    这条断言把"漏登记"从"靠人工发现"变成 **ERROR**（用户规格第 3 项）：
    判据与生成器**同一函数**（`enumerate_children`）⇒ 只要生成器跑过、配置写过一行，
    就不会报；反过来，数据里新出现一个对象级事项而配置没登记，立刻变红。
    """
    issues: List[Dict[str, Any]] = []
    if not isinstance(rep, dict):
        return issues
    er = rep.get("enterprise_readable_report") or rep
    for p in (er.get("confirmed_problems") or []):
        if not isinstance(p, dict):
            continue
        rc = problem_key(p)
        enum = enumerate_children(p, extra_texts=finding_texts(rep, rc))
        reg = {norm_key(c.get("desc")) for c in children_of(rc)}
        for c in enum["child_items"]:
            if _is_dedup_ref(c.get("desc")):     # ★ 去重引用语不是子项名
                continue
            if norm_key(c.get("desc")) not in reg:
                issues.append({
                    "parent": rc, "id": c.get("id"), "kind": "child_unregistered",
                    "detail": "本项正文/明细表/发现明细里出现的子项「%s」未登记为子项"
                              "（来源 %s）—— 请重跑 scripts/_gen_child_items.py 并复核"
                              % (str(c.get("desc"))[:50], c.get("_source"))})
        regr = {norm_key(r.get("desc")) for r in related_of(rc)}
        for r in enum["related_items"]:
            if _is_dedup_ref(r.get("desc")):     # ★ 去重引用语不是关联项名
                continue
            if norm_key(r.get("desc")) not in regr:
                issues.append({
                    "parent": rc, "id": r.get("id"), "kind": "related_unregistered",
                    "detail": "本项关联分析「%s」未登记为关联项" % str(r.get("desc"))[:50]})
    return issues


__all__ = ["VERSION", "STATUS_CHECKED", "STATUS_UNCHECKED", "STATUS_NEED", "STATUS_MISSING",
           "STATUSES", "SKIP_PHRASES", "CONCLUSION_MARKERS", "OBJECT_ITEM_KWS",
           "GAP_TPL_DEFAULT", "GAP_TPL_FAMILY", "GAP_TPL_TABLE", "GAP_TPL_SIDE",
           "load_config", "reload_config", "options", "entry_of", "children_of", "related_of",
           "norm_key", "mentions", "has_skip_reason", "has_conclusion", "analyze_status",
           "analyze_related", "problem_texts", "finding_texts", "enumerate_children",
           "audit", "render_child_list", "checklist_text", "audit_for_problem",
           "config_completeness", "audit_product", "problem_key"]
