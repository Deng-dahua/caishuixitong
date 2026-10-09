# -*- coding: utf-8 -*-
"""
线索链引擎 —— 回答「这个税务疑点是怎么被发现的」
==================================================

线索链的定义
--------------------------------------------------
线索链是「原始资料 → 税务疑点」之间可回溯、可复核的推导路径。它回答稽查员
最关心的问题：**这条疑点是拍脑袋想出来的，还是从资料里一步步算出来的？**

每一环必须回答三件事：
    ① 用了什么资料（source）
    ② 做了什么计算或比对（action）
    ③ 实际看到了什么数字（observed）——没有数字就说明这一环没数据

设计原则
--------------------------------------------------
1. 每一环都必须落到具体数字。写不出数字的环节标注「本轮未取得该项数据」，
   绝不用「经分析发现异常」这类空话充数。
2. 线索链可回溯：每环给出 trace_ref（回查位置），专业人员能按图索骥复核。
3. 无资料支撑的环节不隐藏——它本身就是「风险盲区」，要暴露给报告。
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from engine.sentencekit import (  # ★ 报告文本唯一实现
    split_sentences, strip_meta_prefix, pick_best,
    render_value, translate_key, clamp_text,
)

# 金额/占比/数量/人次的数字提取（保留原始写法，不改写、不换算）
_NUM_PATTERNS = [
    r"[-+]?\d[\d,]*(?:\.\d+)?\s*万元",
    r"[-+]?\d[\d,]*(?:\.\d+)?\s*元",
    r"[-+]?\d[\d,]*(?:\.\d+)?\s*%",
    r"[-+]?\d[\d,]*(?:\.\d+)?\s*笔",
    r"[-+]?\d[\d,]*(?:\.\d+)?\s*张",
    r"[-+]?\d[\d,]*(?:\.\d+)?\s*人",
    r"[-+]?\d[\d,]*(?:\.\d+)?\s*组",
    r"[-+]?\d[\d,]*(?:\.\d+)?\s*个月",
    r"[-+]?\d[\d,]*(?:\.\d+)?\s*家",
    r"[-+]?\d[\d,]*(?:\.\d+)?\s*次",
]


# 报告增强时拼入的方法论后缀标记（税务合规方法/影响/建议/法规依据）。
# 这些不是「核对到的事实」，其中的阈值文字（如「>=3张触发」）若被抽进 numbers 会污染线索链。
_METHODOLOGY_MARKERS = ("税务合规方法", "税务影响", "处理建议", "法规依据")


def _strip_methodology(detail: str) -> str:
    """剥掉报告增强（_enrich_short_findings）拼入的方法论后缀。

    ★ 2026-09-26 修复：短 finding 的 how_found（含「>=3张触发」阈值文字）会被拼进 detail，
       `extract_numbers(detail + " " + how)` 据此抽出了伪数字「3张」，导致线索链
       numbers 出现「-1,285,450.57元、13张、3张」三值，其中「3张」纯属方法论阈值而非事实。
       现只从**事实原文**抽数，方法论后缀一律丢弃。
    """
    s = str(detail or "")
    for mk in _METHODOLOGY_MARKERS:
        idx = s.find(mk)
        # 仅当标记出现在字段**中部**（idx>0）才剥——开头出现的视为事实原文，保留
        if idx > 0:
            s = s[:idx].rstrip("。；; ").rstrip()
    return s


def extract_numbers(text: str, limit: int = 8) -> List[str]:
    """从叙述文本中提取带单位的确定性数字串（原样保留，不做格式化）"""
    if not text:
        return []
    out, seen = [], set()
    for pat in _NUM_PATTERNS:
        for m in re.findall(pat, str(text)):
            s = m.strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
    # 补充无单位但显著的数字（如发票号、税率、笔数）
    if len(out) < 3:
        for m in re.findall(r"\d[\d,]*\.?\d*", str(text)):
            s = m.strip()
            if s and s not in seen and len(s) >= 2:
                seen.add(s)
                out.append(s)
            if len(out) >= limit:
                break
    return out[:limit]


def _metric_rows(metrics: Any) -> List[Tuple[str, str]]:
    """把 observed_metrics 摊平成 (指标名, 值)

    ★ 2026-09-25 根因修复：值一律经 `sentencekit.render_value` 渲染（**禁止 Python repr**）。
      旧实现对"值为 list[dict]"的指标用 `str(x)[:16]`，把内部结构截断后写进企业报告：

          「…—counterparty_count=2；examples=[{'counterparty':，{'counterparty'」

      企业内部数据结构泄漏给企业，且 `[`/`{` 被截断成**括号不闭合**的残句。
      现由 render_value 统一渲染：键名汉化、用中文分隔符、超出写「等N项」，绝不出现 { [ ' 等 repr 记号。
    """
    rows: List[Tuple[str, str]] = []
    if isinstance(metrics, dict):
        for k, v in metrics.items():
            vs = render_value(v, max_len=90)
            if vs:
                rows.append((translate_key(k), vs))
    elif isinstance(metrics, list):
        for i, v in enumerate(metrics[:8]):
            if isinstance(v, dict):
                k = v.get("name") or v.get("metric") or v.get("key") or f"指标{i+1}"
                rows.append((translate_key(k),
                             render_value(v.get("value") if "value" in v else v, max_len=80)))
            else:
                rows.append((f"指标{i+1}", render_value(v, max_len=80)))
    return rows


def _sources_of(finding: Dict) -> List[str]:
    """取发现所依据的资料来源"""
    srcs: List[str] = []
    for s in (finding.get("independent_sources") or []):
        if s and s not in srcs:
            srcs.append(str(s))
    for s in (finding.get("source_files") or []):
        if isinstance(s, dict):
            name = str(s.get("type") or s.get("file") or "")
        else:
            name = str(s)
        if name and name not in srcs:
            srcs.append(name)
    for key in ("data_sources", "evidence_sources"):
        for s in (finding.get(key) or []):
            if s and str(s) not in srcs:
                srcs.append(str(s))
    return srcs


def _sample_rows(finding: Dict, limit: int = 5) -> List[str]:
    """取代表性明细样本（逐笔/逐人）

    ★ 2026-09-25：改用 `sentencekit.render_value`（键名汉化、中文分隔符、禁止 repr）。
      旧实现 `"、".join(f"{k}={v}")` 对嵌套值会 `str(dict)` → 报告里出现
      `examples={'counterparty': '…'}` 这类内部结构。
    """
    rows = finding.get("evidence_rows") or finding.get("detail_rows") or []
    out: List[str] = []
    for r in rows[:limit]:
        s = render_value(r, max_len=120)
        if s:
            out.append(s)
    return out


def materials_available(source_text: str,
                        provided: Optional[List[str]],
                        not_required: Optional[List[str]] = None) -> Tuple[bool, List[str]]:
    """本环节声明的资料，本轮是否已提供 —— **唯一权威**。

    返回 `(是否至少有一类已提供, 未提供/无法核对的资料名列表)`。

    ★★ 2026-10-04（疑点1 四维自检 D5）：旧实现 `_materials_in_text` 把文本按
      `、，,;；` 切开后拿**整片**去比 15 类名，于是「销项发票（含红字标识）」——
      带括号说明的资料名 —— **永远匹配不上**，首环据此被判"本轮未取得该项资料"，
      同时把 `data_gaps` 记成 `material_missing`；可销项发票明明已提供，
      整个疑点就是靠它得出的 13 张读数。**同一条发现里"资料未取得"与"给出读数"并存**。
      修法：归一由 `material_names.categories_of`（资料名唯一权威，能剥括号、认别名）
      统一完成，本函数只做"归一 → 与 provided 归一集合比对"。
    """
    if not source_text:
        return False, []
    try:
        from engine import material_names as _mn  # 资料名唯一权威
    except Exception:  # noqa: BLE001
        return False, []
    _prov_raw = {str(p).strip() for p in (provided or []) if p}
    # ★ 清单为空 ⇒ 语义是"本轮确未提供任何资料"（与既有闸门口径一致），
    #   不得当成"清单未知"而回落成 engine_gap —— 那会把"缺资料"说成"程序待完善"。
    _prov = set()
    for _p in _prov_raw:
        _prov.add(_p)
        _c = _mn.canonical(_p)
        if _c:
            _prov.add(_c)
    # 候选片段：先按分隔符切，再补上"整段"（覆盖"退货单、折让协议、拒收证明"这类组合名）
    _whole = str(source_text).strip()
    pieces = [x.strip() for x in re.split(r"[、，,;；／/\n]+", _whole) if x.strip()]
    pieces.append(_whole)
    # ⚠ 片段**不再逐字切半**：「利润表成本费用」「资产负债表应交税费」这类
    #   **复合资料名**（要看的不只是利润表/资产负债表本体，还有其成本费用/应交税费明细）。
    #   切半会得出"缺利润表"这种**缩小口径**的结论 —— 实测源串
    #   「利润表成本费用、进项税额、银行付款」在只提供进项发票与银行流水时，
    #   正确结论是缺「利润表成本费用」（精确），而非缺「利润表」（把成本费用那块漏掉）。
    #   `、` 分隔符切出的就是作者声明的资料粒度，**尊重它**，不擅自归并或切细。
    # ★★ 2026-10-04（疑点1 D5 收口的连带）：**本业态不适用**的资料不计入"缺失"。
    #   唯一权威 `industry_resolver.not_required_materials()`（与疑点2 那批同一口径）。
    #   事故：新写的环节缺料文案「因缺少资料（物流单据与承运记录）未取得本环节数据」
    #   被渲染进报告段落，对服务型企业把**天然没有**的资料说成"缺失导致无法核对"
    #   ⇒ 闸门 `check_waiting_materials_respect_industry` 判 ERROR（闸门是对的）。
    _nr = [str(x).strip() for x in (not_required or []) if str(x).strip()]
    _ok = False
    _missing: List[str] = []
    # ★★ 2026-10-05（疑点7 D6）**不可识别的资料名不得静默跳过**。
    #   事故：环节2 声明「销项发票、人员、产能数据」，其中「人员」「产能数据」
    #   **归不了 15 类任何一类**（`categories_of` 返回空）⇒ 旧实现 `continue` 跳过
    #   ⇒ `missing=[]`、`_ok=True` ⇒ 报告写"所需资料已在本轮提供"，
    #   而"人员/产能数据"企业根本没交 —— **凭空认定已提供**，缺口被掩盖。
    #   正确口径：归不了类的**必须单独登记**为"无法归类、须人工确认"，
    #   既不算已提供、也不算"缺失"（它可能确实交了，只是本系统认不出这个名字）。
    #   这样环节文案会如实说"另有人工口径资料无法归类，须确认是否已提供"。
    _unclassified: List[str] = []
    for piece in pieces:
        cats = _mn.categories_of(piece) or []
        if not cats:
            if piece and piece not in _unclassified:
                _unclassified.append(piece)
            continue
        if any(c in _prov for c in cats):
            _ok = True
        else:
            # 该资料属本业态不适用 ⇒ 不列为缺失（企业天然不会有）
            if _nr and any((_n == piece) or (_n in piece) or (piece in _n) for _n in _nr):
                continue
            if piece not in _missing:
                _missing.append(piece)
    # 保持返回签名不变（`Tuple[bool, List[str]]`），把"认不出名字"的并入 `_missing`。
    # ★★ 2026-10-06（用户第 2 批 AC7）：**不用"无法归类、须人工确认是否已提供"这种占位符**
    #   —— 它是"我们不知道"的自述，读者拿不到可用信息（实测 32 处）。
    #   改为三态之一（与"已提供/未提供/须核对"口径对齐）：
    #     · 该名字能与**已提供清单**任一资料判为同一份 ⇒ 已提供 ⇒ 不计缺失；
    #     · 对不上 ⇒ 如实标「须核对是否已提供」（不臆断成"未提供"）。
    #   ⚠ "是不是同一份资料"的唯一权威＝`engine.material_names.same_material`（不自造归一）。
    try:
        from engine.material_names import same_material as _same_mat
    except Exception:  # noqa: BLE001
        _same_mat = None
    _prov = [str(x) for x in (provided or []) if str(x or "").strip()]
    for _u in _unclassified:
        if _same_mat is not None and any(_same_mat(_u, _p) for _p in _prov):
            continue                      # 已提供 ⇒ 不是缺失
        _tag = "须核对是否已提供：" + _u
        if _tag not in _missing:
            _missing.append(_tag)
    return _ok, _missing


def _materials_in_text(source_text: str, provided: Optional[List[str]]) -> bool:
    """薄转发：环节声明的资料中是否有任一类别本轮已提供（唯一权威见上方函数）。"""
    _ok, _ = materials_available(source_text, provided)
    return _ok


# ★★ 2026-10-04（疑点1 四维自检 D6/D7）：**环节读数的唯一权威**。
#   病根：旧实现取不到对题读数时回落到 `metrics[:3]` / `numbers[:3]` / `_terminal_signal`，
#   这三者都是"本项全局的某个数"，与**本环节**在核什么毫无关系。实测两处对撞：
#     · 第2环 action=「核对是否有退货单、折让协议、拒收证明」，读数却是「红字发票笔数=13…」
#       —— 拿"统计读数"冒充"事由核对结论"；
#     · 末环 action=「核对红冲是否对应退款」，读数却是「按方向拆分：销项4张…」
#       —— 号称核了退款，却没有任何退款核对结果（并让"银行流水已提供"顺势冒充"已核对退款"）。
#   修法：环节读数只能来自**要件命中证据**（`constituent_hits[].evidence`）—— 它才是
#   "本环节实际核对到了什么"的唯一来源，且与 `constituent_checkpoint` 的要件表同源。
#   对题判据用**字符 2-gram 交集**（中文不切词，词元匹配实测 65 个环节只命中 7 个，不可用）。
#
#   阈值 4 为**实测标定**（真实产物 65 个环节）：≥2 会把「核对红冲是否对应退款」错配到
#   要件③（事由核对，交集=3）—— 恰是 D7 那种"不适用的资料冒充已核对"；≥4 时该环正确地
#   判为"未产出对题读数"，而应的环节（第1环=6、第2环=9）正常命中。覆盖率 51%（33/65）。
_ON_TOPIC_MIN_BIGRAMS = 4


def _two_grams(text: Any) -> set:
    """字符级 2-gram（去标点/空白）。中文不切词，2-gram 是本项目可用的对题度量。"""
    s = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", str(text or ""))
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _on_topic_reading(node: Dict, hits: List[Dict],
                      constituents: Optional[List[str]]) -> str:
    """从要件命中证据里取与本环节 action/output **对题**的读数；取不到返回 ""。

    唯一权威：`constituent_hits`（要件命中证据）。命中证据为空、或无一达到对题阈值时
    返回 ""，由调用方**如实标注**（缺资料 / 检查程序待完善），**不得**改用别的环节的数。
    """
    if not hits:
        return ""
    _nt = _two_grams(str(node.get("action", "")) + str(node.get("output", "")))
    if not _nt:
        return ""
    best = (0, -1, "")
    for h in hits:
        if not isinstance(h, dict):
            continue
        try:
            _idx = int(h.get("index"))
        except Exception:  # noqa: BLE001
            continue
        _ev = str(h.get("evidence", "") or "")
        if not _ev:
            continue
        _con = ""
        if isinstance(constituents, list) and 1 <= _idx <= len(constituents):
            _con = str(constituents[_idx - 1] or "")
        _score = len(_nt & _two_grams(_ev + " " + _con))
        if _score > best[0]:
            best = (_score, _idx, _ev)
    if best[0] >= _ON_TOPIC_MIN_BIGRAMS:
        return best[2]
    return ""


def _metrics_reading(node: Dict, finding: Dict) -> str:
    """从**本条发现自己的 observed_metrics** 取与本环节 action 对题的读数（取不到返回 ""）。

    ★ 2026-10-05（疑点5 D6）：`_on_topic_reading` 的唯一来源是 `constituent_hits`；
      疑点5（RL-CIT-007）5 条要件全部「未单独核对」⇒ hits 为空 ⇒ 三环都写"未产出读数"，
      而「分项扣除限额测算」表里**确实有金额**（业务招待费账面 411,111.53／超限 377,927.53；
      广告费和业务宣传费账面 2,729,730.26／超限 1,734,210.17）
      ⇒ 数据在**同疑点内可回指**，不是"未产出"。
      ⚠ 守铁律：只用**本条发现自己**的指标、只取与本环节 action **对题**的键；
        不得改用别的环节/别的发现的数；未达阈值返回 ""（沿用调用方的如实标注）。
    """
    _m = (finding or {}).get("observed_metrics")
    if not isinstance(_m, dict) or not _m:
        return ""
    _nt = _two_grams(str(node.get("action", "")) + str(node.get("output", "")) + str(node.get("source", "")))
    if not _nt:
        return ""
    _best = (0, "", "")
    for _k in _m:
        _v = _m.get(_k)
        if _v in (None, ""):
            continue
        _sc = len(_nt & _two_grams(str(_k)))
        if _sc > _best[0]:
            _best = (_sc, str(_k), _v)
    if _best[0] < _ON_TOPIC_MIN_BIGRAMS:
        return ""
    try:
        _txt = "{:,.2f}".format(float(str(_best[2]).replace(",", "")))
    except Exception:  # noqa: BLE001
        _txt = str(_best[2])
    return "本环节读数（来自本项测算表）：%s = %s" % (_best[1], _txt)

def build_clue_chain(finding: Dict, redline: Dict, engine_data: Optional[Dict] = None,
                     provided_materials: Optional[List[str]] = None,
                     not_required_materials: Optional[List[str]] = None) -> Dict:
    """
    构建单条发现的线索链。

    ★ 2026-09-29（点评整改 P0-1②/P1-4 三态化）：环节无数据时区分两种性质——
      · material_missing：环节所需资料本轮确未提供 → "因缺少资料未取得数据"（计入检查受限）；
      · engine_gap：所需资料**已提供**但该环节未产出可展示数据 → 属检查程序待完善项，
        **不计入资料缺失**（旧版把此类写成"本轮未取得该项资料"，与资料清单"已提供"
        直接矛盾——实测"工资表已提供、疑点16 第1环却写未取得"）。
      判据只能来自 provided_materials（资料齐备性唯一权威 material_readiness），
      不得以"发现是否声明了取数来源"判断资料是否存在。

    返回结构：
        {
          "redline_id", "redline_name",
          "sources_used": [...],                 # 本条线索实际使用的资料
          "nodes": [ {step, source, action, observed, trace_ref, has_data} ],
          "terminal_signal": "...",              # 终端信号（触碰红线的具体数值）
          "numbers": [...],                      # 链路上出现的确定性数字
          "samples": [...],                      # 代表性明细
          "data_gaps": [...]                     # 无数据环节（含 reason: material_missing / engine_gap）
        }
    """
    engine_data = engine_data or {}
    detail = str(finding.get("detail") or finding.get("description") or "")
    how = str(finding.get("how_found") or "")
    metrics = finding.get("observed_metrics")
    # ★ 2026-10-04：要件命中证据 = 各环节读数的**唯一来源**（见 `_on_topic_reading`）
    hits = finding.get("constituent_hits") or []
    sources = _sources_of(finding)
    # ★ 2026-09-26：只从事实原文抽数，剥掉方法论后缀（避免「>=3张触发」等阈值被当事实数字）
    numbers = extract_numbers(_strip_methodology(detail))
    samples = _sample_rows(finding)

    nodes: List[Dict] = []
    template = list(redline.get("clue_chain") or [])

    def _gap_reason(source_text: str) -> str:
        """本环节无读数时，缺的是"资料"还是"程序"（资料齐备性走唯一权威）。

        ★★ 2026-10-05（疑点2 D11 复诊）：**业态不适用必须先排除**，否则同一环被归两处。
          事故：RL-FUND-002 第4环 source=「合同与物流单据（本轮未提供）」，
          节点正文已如实写「（物流单据）属本业态不适用，不计入资料缺失」，
          但本函数判成 `material_missing` ⇒ `data_gaps` 把它计入
          「第3环、第4环因缺少资料未取得数据，已计入检查受限范围」
          —— 同一页里"不适用"与"缺资料"并存，自相矛盾（闸门 `check_waiting_
          materials_respect_industry` 只查"待补清单"，抓不到这里）。
          修法：唯一权威 `materials_available` 本就接 `not_required_materials`，
          这里显式先判业态不适用，返回独立 reason `not_applicable_industry`。
        """
        _ok, _missing = materials_available(source_text, provided_materials,
                                            not_required_materials)
        # 本业态天然不适用的资料 ⇒ 既不是"缺资料"，也不是"程序待完善"，单列一档
        try:
            for _n in (not_required_materials or []):
                _n = str(_n or "").strip()
                if _n and _n in str(source_text or ""):
                    return "not_applicable_industry"
        except Exception:  # noqa: BLE001
            pass
        return "material_missing" if (_missing and not _ok) else "engine_gap"

    def _src_disp(_s: str) -> str:
        """环节「对应资料」的显示：**已提供**原样；**未提供**如实标注（本轮未提供）。

        ★ 2026-08-05（疑点5 D7）：环的 `source` 原本是**红线模板写死的静态声明**，
          与实际取数来源可能不符（实测环2 声称「利润表…」而证据表写「底稿未逐字见到」）。
          同一函数已有 `materials_available` 判资料有无的能力，这里只用于**校正显示**，
          **不改任何判定**。
        """
        _t = str(_s or "").strip()
        if not _t:
            return _t
        try:
            _ok, _miss = materials_available(_t, provided_materials)
        except Exception:  # noqa: BLE001
            return _t
        if _ok or not _miss:
            return _t
        return _t + "（本轮未提供）"

    if template:
        # 有红线模板：按模板骨架逐环落地，并把**对题**的读数填进去
        total = len(template)
        for i, tpl in enumerate(template):
            step_no = i + 1
            observed = _on_topic_reading(tpl, hits, redline.get("constituents"))
            if observed:
                nodes.append({
                    "step": step_no,
                    "source": _src_disp(tpl.get("source", "")),
                    "action": tpl.get("action", ""),
                    "output": tpl.get("output", ""),
                    "observed": observed,
                    "trace_ref": f"底稿编号 {finding.get('scene_fact_id') or finding.get('fact_id') or '—'} "
                                 f"第{step_no}环",
                    "has_data": True,
                })
                continue
            # 取不到对题读数：如实标注缺的是"资料"还是"程序"，**不拿别的环节的数顶替**
            _reason = _gap_reason(tpl.get("source", ""))
            _ok, _missing = materials_available(tpl.get("source", ""), provided_materials,
                                                not_required_materials)
            _nr_hit = [str(_n) for _n in (not_required_materials or [])
                       if _n and str(_n) in str(tpl.get("source", ""))]
            if _nr_hit:
                # 环节所需资料属**本业态不适用** ⇒ 如实说明（不含"缺失"口径）
                observed = ("本环节所需资料（" + "、".join(_nr_hit[:3]) +
                            "）属本业态不适用，不计入资料缺失；该环节按检查程序待完善项处理")
            elif _reason == "material_missing":
                observed = ("因缺少资料（" + "、".join(_missing[:4]) +
                            "）未取得本环节数据，该部分无法核对")
            else:
                # ★★ 2026-10-05（疑点7 D6）**部分提供不得说成"已在本轮提供"**。
                #   事故：环节2 声明「销项发票、人员、产能数据」，实际只提供了销项发票
                #   （人员/产能数据本轮没有）⇒ `materials_available` 的 `_ok=True`
                #   （语义是"**至少有一类**已提供"）⇒ 旧文案笼统写"所需资料已在本轮提供"，
                #   读者以为三样都有，环节的数据缺口被这句话掩盖。
                #   现按 `_missing` 是否为空分三种口径，**逐样如实说**：
                #     · 全有 → "所需资料已在本轮提供"
                #     · 部分有 → "所需资料中已提供 X、尚缺 Y"（点名，不含糊）
                #     · 全无 → 由上面 `_reason == "material_missing"` 分支处理
                if _ok and _missing:
                    # 「无法归类、须人工确认是否已提供：X」是登记时的**前缀标记**，
                    #   拼句时剥掉，只在句尾点出这些名字，避免同一句话说三遍。
                    _names = [m.split("：", 1)[-1] if m.startswith("无法归类") else m
                              for m in _missing[:3]]
                    _tag = ("其中" + "、".join(_names) + "属本系统无法归类的资料，"
                            "须确认本轮是否已提供") if len(_names) < len(_missing) else ""
                    observed = ("本环节所需资料中已提供部分、尚缺 " + "、".join(_names)
                                + "，该环节未能完成核对（属检查程序待完善项，不计入资料缺失）"
                                + ("；" + _tag if _tag else ""))
                else:
                    observed = ("本环节未产出对题读数"
                                + ("（所需资料已在本轮提供，属检查程序待完善项）" if _ok
                                   else "（所需资料类别无法识别，按检查程序待完善项处理）"))
            nodes.append({
                "step": step_no,
                "source": _src_disp(tpl.get("source", "")),
                "action": tpl.get("action", ""),
                "output": tpl.get("output", ""),
                "observed": observed,
                "trace_ref": f"底稿编号 {finding.get('scene_fact_id') or finding.get('fact_id') or '—'} "
                             f"第{step_no}环",
                "has_data": False,
                "_gap_reason": _reason,
                # ★ 2026-10-05（疑点7 D6）：把本环缺口明细带到 node 上，
                #   再由 `data_gaps` 原样透出（唯一权威仍是 `materials_available`）。
                "_gap_missing": list(_missing or []),
            })
    else:
        # 无模板：退化为「资料 → 计算 → 结果」三环；读数同样只取**对题**来源
        _no_tpl = [
            # 各环 source 必须有内容（契约：每环都要写明"使用资料"）
            {"step": 1, "source": "、".join(sources) or "本轮已上传并成功读取的资料",
             "action": "读取并归集与本项相关的记录", "output": "可复核的数据集"},
            {"step": 2, "source": detail[:60] or "本项事实原文",
             "action": how or "按同一口径重新计算并比对", "output": "差异或异常指标"},
            {"step": 3, "source": "上述比对结果",
             "action": "判断是否触碰红线构成要件", "output": redline.get("name", "")},
        ]
        nodes = []
        for tpl in _no_tpl:
            step_no = tpl["step"]
            observed = _on_topic_reading(tpl, hits, redline.get("constituents"))
            if not observed:
                # ★ 2026-10-05（疑点5 D6）：回落到**本条发现自己的** observed_metrics ——
                #   数据在同疑点内可回指时，不得写「未产出读数」（那是否定已算出的数）。
                observed = _metrics_reading(tpl, finding)
            if not observed:
                _reason = _gap_reason(tpl.get("source", ""))
                _ok, _missing = materials_available(tpl.get("source", ""), provided_materials,
                                                    not_required_materials)
                if _reason == "material_missing":
                    observed = ("因缺少资料（" + "、".join(_missing[:4]) +
                                "）未取得本环节数据，该部分无法核对")
                else:
                    observed = "本环节未产出对题读数（属检查程序待完善项）"
                nodes.append({
                    "step": step_no, "source": _src_disp(tpl.get("source", "")),
                    "action": tpl.get("action", ""), "output": tpl.get("output", ""),
                    "observed": observed,
                    "trace_ref": f"底稿编号 {finding.get('scene_fact_id') or '—'} 第{step_no}环",
                    "has_data": False, "_gap_reason": _reason,
                })
            else:
                nodes.append({
                    "step": step_no, "source": _src_disp(tpl.get("source", "")),
                    "action": tpl.get("action", ""), "output": tpl.get("output", ""),
                    "observed": observed,
                    "trace_ref": f"底稿编号 {finding.get('scene_fact_id') or '—'} 第{step_no}环",
                    "has_data": True,
                })

    data_gaps = []
    for n in nodes:
        if n.get("has_data"):
            continue
        # ★ 2026-10-05（疑点7 D6 收口）带上**缺口明细** `_gap_missing`。
        #   报告层要按"该环到底缺哪几样"分口径（"已提供" vs "未取到部分资料"），
        #   只有 step+reason 不足以判断 —— 旧实现只能一律写"所需资料已在本轮提供"，
        #   与正文"尚缺…"自相矛盾。`_gap_missing` 来自同一份 `materials_available`
        #   权威结果，**不另判一次**。
        data_gaps.append({
            "step": n["step"], "gap": n["source"] or n["output"],
            # 复用逐环已判定的原因，避免"同一件事判两次"
            "reason": n.pop("_gap_reason", None) or _gap_reason(n.get("source", "")),
            "_gap_missing": list(n.pop("_gap_missing", []) or []),
        })

    return {
        "redline_id": redline.get("id", ""),
        "redline_name": redline.get("name", ""),
        "sources_used": sources,
        "nodes": nodes,
        "terminal_signal": _terminal_signal(detail, numbers, finding),
        "numbers": numbers,
        "samples": samples,
        "data_gaps": data_gaps,
    }


def _terminal_signal(detail: str, numbers: List[str], finding: Dict) -> str:
    """
    终端信号：把「触碰红线的具体数值」说清楚。
    优先取叙述中第一段带数字的句子（通常是结论句）。

    ★ 2026-09-25 修复：切句改用 `sentencekit.split_sentences`（**括号感知**）。
      旧实现 `re.split(r"[。；\n]", detail)` 会把括号内的分号当句末切点，
      切出「…（取销项发票不含税金额」这种**括号不闭合**的残句，
      而该残句会原样进企业报告（实测），一句话读不通即损害报告可信度。
      同时剥离源文本自带的前置语（"已经核实的事实是："），避免与报告引导语叠加。
    """
    if not detail:
        return ""
    sentences = split_sentences(str(detail))
    # ★★ 2026-10-04（㊷）：**不再"最长者优先"**。
    #   旧实现 `pick_best(sentences[:4])` 按长度选，于是触发信号总落在那句最长的
    #   免责/口径长句上，把差异与口径说明挤掉（实测 80/80 条勾稽发现都不带差异说明）。
    #   现改为**对题优先**：与本项 type 的字符 2-gram 交集最大者胜；平手取**更短**的
    #   （短句更可能是结论句，长句更可能是堆砌说明）。判据与环节读数同源（`_two_grams`）。
    cands = sentences[:6] or sentences
    if cands:
        _t = _two_grams(str(finding.get("type", "")))
        def _score(_s: str):
            return (len(_t & _two_grams(_s)), -len(_s))
        best = max(cands, key=_score)
    else:
        best = ""
    if best:
        return clamp_text(strip_meta_prefix(best), 180)
    if numbers:
        return "涉及金额与占比：" + "、".join(numbers[:4])
    return ""


def chain_text(chain: Dict) -> str:
    """把线索链压成一段可直读的话（报告用，大白话）"""
    nodes = chain.get("nodes") or []
    if not nodes:
        return ""
    parts = []
    for n in nodes:
        seg = f"第{n['step']}步，从「{n.get('source') or '—'}」{n.get('action') or ''}"
        if n.get("observed"):
            seg += f"，实际看到：{n['observed']}"
        parts.append(seg)
    return "；".join(parts) + "。"
