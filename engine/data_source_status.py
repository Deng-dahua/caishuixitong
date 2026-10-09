# -*- coding: utf-8 -*-
"""数据源状态一致性（Skill 7 唯一权威 / v1.0.0）。

## 为什么要它
用户复核（2026-10-07）指出多疑点存在"**数据已取得却写未取得**"的同页矛盾：
  · 疑点1：明细表逐笔列出「红字发票信息确认单编号」（13 行），核对表第 4 条却写
    「未单独核对（独立数据源本轮未取得）」——而该条声明的独立数据源里
    「销项发票、进项发票」**本轮明明已取得、且正文正在用它们的金额**。
  · 疑点7/8/13：正文用「销项发票金额」「实缴增值税 205,744.69 元」「命中技术服务费」
    得出前提条结论，同一条的「数据源状态」列却写「须核对」——**同一行自相矛盾**。

**根因（实测量化）**：要件声明的「独立数据源」是**多源组合串**（如
「红字发票信息确认单、销项发票、进项发票、被冲减蓝字发票」），而判定把它**当成一份材料**
整体去匹配（`evidence_chain._match_material(整串)`）⇒ 只要有一个源不在"已提供类别"里，
整组就落「未取得」，**已取得的源被一起否定**，且报告不说明"哪个缺、哪个有"。
实测：全量产物 **65 条要件行中 26 条**（40%）命中该形态。

## 三条硬规则（本模块唯一实现）
1. **同一数据源在全文状态一致**：明细表/正文里出现过的数据源，核对表不得写「未取得」。
2. **逐源判定 + 合成**：四态（已有/缺失/须核对/待企业提交）**逐源**判，再按
   「全有 → 已有；部分 → 须核对并列出缺哪些；全无 → 缺失」合成；文案必须**逐源点名**，
   不得在"有已取得项"时笼统写「独立数据源本轮未取得」。
3. **硬证据优先**：本项**明细表**里出现该数据源名/别名/专有标识（`markers`）⇒ 判「已有」；
   该源是某份已取得资料的**字段/内容**（`provided_by`）⇒ 判「已有」。
   两者都只认**能证实**的依据（泛词、猜测一律不算）。

## 口径说明（与用户规格的一处有意保留）
用户规格列了 4 个状态；本系统另有第 5 个状态「**本业态不适用**」
（该要件的独立数据源与本企业业态天然不符，如服务型企业的货物流凭证）。
它不是"资料缺口"——删掉会把服务型企业钉在"缺物流单据"上（既有验收，见
`industry_resolver.not_required_materials`）。故 4 态为**主词表**，第 5 态作为
**扩展状态**保留并在本文件登记。

## 数据表
`config/data_sources.json`（唯一权威）：`data_source_id / data_source_name / aliases /
provided_by / markers`。新增数据源**只加一行**（生成器自动补行，人工补 markers）⇒
自动纳入一致性校验（门禁 `check_data_source_status_consistency`）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

VERSION = "1.0.0"

_ROOT = Path(__file__).resolve().parent.parent
_CFG = _ROOT / "config" / "data_sources.json"
_CACHE: Optional[Dict[str, Any]] = None

#: 主状态词表（用户规格 4 态）
STATUS_HAVE = "已有"
STATUS_MISSING = "缺失"
STATUS_NEED = "须核对"
STATUS_PENDING = "待企业提交"
STATUSES = (STATUS_HAVE, STATUS_MISSING, STATUS_NEED, STATUS_PENDING)
#: 扩展状态：不是"资料缺口"，不构成缺失（既有能力，见模块头）
STATUS_NA = "本业态不适用"
STATUSES_ALL = STATUSES + (STATUS_NA,)

#: 多源串的切分符 —— **不另立一份**（本项目铁律：并列分隔符表全系统只此一处）。
#: 唯一权威 = `industry_resolver.MATERIAL_SEG_SEP`（「且」语义）/ `MATERIAL_ALT_SEP`（「或」语义）。
#: ⚠ 首版在本模块里自写了一张 `[、,，;/]|(以及|或者|及|与|和|或)`，**当场被门禁
#:   `test_only_one_separator_table` 判红**（"除 industry_resolver.py 外又出现并列分隔符表"）
#:   —— 这正是本项目要消灭的"同一概念多头维护"。改为由权威表**派生**（惰性求值，
#:   避免模块导入顺序问题；派生式里没有字面量分隔符表，门禁不会再误报）。
_TOKEN_RE = None
_SPLIT_RE = None


def _seps():
    """惰性构造派生分隔符正则（(仅且, 含或)；由唯一权威表派生，不另立一份）。"""
    global _TOKEN_RE, _SPLIT_RE
    if _TOKEN_RE is None:
        from engine.industry_resolver import MATERIAL_SEG_SEP, MATERIAL_ALT_SEP
        _p = "(?:%s)|(?:%s)" % (MATERIAL_SEG_SEP.pattern, MATERIAL_ALT_SEP.pattern)
        _SPLIT_RE = re.compile(_p)
        _TOKEN_RE = re.compile("(%s)" % _p)
    return _SPLIT_RE, _TOKEN_RE


def load_config() -> Dict[str, Any]:
    global _CACHE
    if _CACHE is None:
        try:
            raw = json.loads(_CFG.read_text(encoding="utf-8"))
            _CACHE = raw if isinstance(raw, dict) else {}
        except Exception:                    # 留痕：配置缺失 ⇒ 空表（门禁按"无表不校验"处理）
            _CACHE = {}
    return _CACHE


def reload_config() -> Dict[str, Any]:
    global _CACHE
    _CACHE = None
    return load_config()


def sources() -> List[Dict[str, Any]]:
    return [s for s in (load_config().get("sources") or []) if isinstance(s, dict)]


def _index() -> Dict[str, Dict[str, Any]]:
    """名称 + 别名 → 条目（唯一索引；别名归一后互相指向同一条）。"""
    idx: Dict[str, Dict[str, Any]] = {}
    for s in sources():
        nm = str(s.get("data_source_name") or "").strip()
        if not nm:
            continue
        idx[nm] = s
        for a in (s.get("aliases") or []):
            a = str(a or "").strip()
            if a and a not in idx:
                idx[a] = s
    return idx


def entry_of(name: Any) -> Optional[Dict[str, Any]]:
    return _index().get(str(name or "").strip())


def data_source_id(name: Any) -> str:
    e = entry_of(name) or {}
    return str(e.get("data_source_id") or "DS_UNKNOWN")


def canonical_name(name: Any) -> str:
    """别名 → 规范名（同一数据源只有一个展示名，防"同一物两种写法"被当成两个源）。"""
    e = entry_of(name) or {}
    return str(e.get("data_source_name") or str(name or "").strip())


def split_sources(text: Any) -> List[str]:
    """把「A、B、C」切成单源（去空、去重、保序）。

    ★ 必须先"整串识别 + 回并"，否则会把**数据源名里自带的分隔字**切坏（实测事故）：
      「**合同或协议**」本身就是一个数据源名（红线库里就这么写），粗暴按「或」切
      ⇒ 变成「合同」「协议」两项 —— 前者还会被别名归一到「合同文件」，
      于是报告里凭空多出一个"未取得的数据源"，而本项要的其实是那一个词。

    做法：按分隔符切 token，然后**贪心回并** —— 只要「已累积 + 分隔符 + 下一段」
    整个是已登记的数据源名/别名，就继续并；否则在该分隔符处断句。
    """
    s = str(text or "").strip()
    if not s:
        return []
    if entry_of(s) is not None:              # 整串就是一个已登记的数据源
        return [canonical_name(s)]
    _split_re, _token_re = _seps()
    toks = [t for t in _token_re.split(s) if t != ""]
    out: List[str] = []
    cur = ""
    i = 0
    while i < len(toks):
        tk = toks[i]
        if not _split_re.fullmatch(tk):      # 实词段
            cur = cur + tk
            i += 1
            continue
        # 分隔符：看"回并"是否构成一个已登记数据源
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        if nxt and entry_of(cur + tk + nxt) is not None:
            cur = cur + tk + nxt
            i += 2
            continue
        if cur:
            out.append(cur)
        cur = ""
        i += 1
    if cur:
        out.append(cur)
    res: List[str] = []
    for x in out:
        x = x.strip()
        if x and x not in res:
            res.append(x)
    return res


# --------------------------------------------------------------------------
# 明细表硬证据（规则 3）
# --------------------------------------------------------------------------
def detail_text(problem: Dict[str, Any]) -> str:
    """**本项明细表**的全部文本（标题 + 列名 + 单元格）。

    ⚠ 只取明细表，**不取正文**：正文里会出现"增值税申报表"这类**提及**（甚至"未提供增值税申报表"），
      把它当"已取得"会造成假"已有"。用户规则也是"明细表中出现的数据"。

    ⚠⚠ **必须排除"要件核对表"自己**（自引用陷阱，实测）：核对表里就写着
      「独立数据源 = 退货单、折让协议、拒收证明」——若把自己的文字当"明细表证据"，
      每个数据源都会**自己证明自己已取得**（首版实测：疑点1 第3条「退货单、折让协议、拒收证明」
      被判「已有」，而它们本轮**根本没提供**）。判据输入必须排除**判定产物自身**。
    """
    parts: List[str] = []
    for np_ in ((problem or {}).get("narrative_paragraphs") or []):
        if not isinstance(np_, dict):
            continue
        for t in (np_.get("detail_tables") or []):
            if not isinstance(t, dict):
                continue
            _title = str(t.get("title") or "")
            if "构成要件" in _title or "核对表" in _title:
                continue                     # ← 自引用屏障：核对表不能当明细表证据
            parts.append(_title)
            for c in (t.get("columns") or []):
                parts.append(str(c or ""))
            for row in (t.get("rows") or []):
                if isinstance(row, dict):
                    parts.extend(str(v) for v in row.values())
                elif isinstance(row, (list, tuple)):
                    parts.extend(str(v) for v in row)
    return " ".join(parts)


def detail_text_from_suspicion(s: Dict[str, Any]) -> str:
    """**运行期**取「明细表证据文本」——与报告渲染明细表**同源**。

    ⚠ 为什么需要它：要件核对发生在**报告段落构造之前**（`constituent_checkpoint`
    在 `_enterprise_situations` 里被调用），此时明细表还没渲染出来。但明细表的**数据源**
    是固定的：`engine/enterprise_report._evidence_rows_to_detail_table(finding.evidence_rows)`
    —— 即 `supporting_findings[].evidence_rows`。此处直接读**同一份数据**，
    保证"核对表看到的数据"与"明细表列出的数据"是同一批（同源铁律）。
    """
    if not isinstance(s, dict):
        return ""
    parts: List[str] = []
    for f in (s.get("supporting_findings") or []):
        if not isinstance(f, dict):
            continue
        for r in (f.get("evidence_rows") or []):
            if isinstance(r, dict):
                parts.extend(str(v) for v in r.values())
            elif isinstance(r, (list, tuple)):
                parts.extend(str(v) for v in r)
        # 发现的明细文本本身（含"红字发票信息确认单编号：…"这类备注原文）
        for k in ("detail", "description"):
            v = f.get(k)
            if isinstance(v, str) and v.strip():
                parts.append(v)
    # 疑点自带的逐笔/明细行（若有）
    for k in ("evidence_rows", "detail_rows"):
        for r in (s.get(k) or []):
            if isinstance(r, dict):
                parts.extend(str(v) for v in r.values())
    return " ".join(parts)


#: 允许"按名称命中明细表即判已有"的**最小名称长度**（短名＝通用词，须靠 markers 证实）
_MIN_NAME_HIT = 3


def _detail_evidence(name: str, detail: str) -> str:
    """该数据源在本项明细表里的**硬证据**（命中什么就返回什么；未命中返回空串）。

    命中判据（由紧到松，只认**能证实**的）：
      ① 专有标识（`markers`，如「红字发票信息确认单编号」）；
      ② 数据源名/别名 —— **仅当名称长度 ≥ `_MIN_NAME_HIT` 才允许按名称命中**。

    ⚠ 为什么给名称命中加长度门槛（实测事故）：数据源「**收入**」只有两个字，
      而明细表里"收入合计/营业收入/…"随处可见 ⇒ 满篇命中、判「已有」，
      与核对表的「缺失」直接打架（门禁首跑即报出 1 处冲突：疑点5「收入」）。
      口径：**短名（≤2 字）属通用词，必须靠专有标识（markers）证实**；
      要给某个短名开"可证实"通道 ⇒ 在 `config/data_sources.json` 里给它补 `markers`（改数据不改逻辑）。
    """
    e = entry_of(name) or {}
    for mk in (e.get("markers") or []):
        mk = str(mk or "").strip()
        if mk and mk in detail:
            return mk
    for nm in [canonical_name(name)] + [str(a) for a in (e.get("aliases") or [])]:
        nm = str(nm or "").strip()
        if nm and len(nm) >= _MIN_NAME_HIT and nm in detail:
            return nm
    return ""


# --------------------------------------------------------------------------
# 逐源状态判定（唯一实现）
# --------------------------------------------------------------------------
def _material_status(name: str, available: Sequence[str]) -> Tuple[str, str]:
    """借**唯一权威** `evidence_chain._match_material` 判单源（已有/待核/缺失 + 依据）。"""
    try:
        from engine.evidence_chain import _match_material
        m = _match_material(str(name or "").strip(), "", list(available or [])) or {}
        return str(m.get("status") or "").strip(), str(m.get("basis") or "").strip()
    except Exception as exc:                 # noqa: BLE001 - 留痕：取不到权威 ⇒ 如实"未知"
        return "", "资料匹配权威不可用（%s）" % str(exc)[:60]


def status_of(name: str, *, available: Sequence[str] = (), detail: str = "",
              not_required: Any = None) -> Dict[str, Any]:
    """**单个数据源**的状态（四态 + 扩展态）与理由（唯一实现）。

    判定优先级（先硬后软，先"能证实"后"要人工确认"）：
      ① 本项明细表里出现（名称/别名/专有标识）        ⇒ 已有
      ② 由某份已取得资料提供（`provided_by`）        ⇒ 已有
      ③ `_match_material` 单源判定：已有 / 待核⇒须核对 / 缺失
      ④ 本业态不适用（`not_required` 命中）          ⇒ 本业态不适用（扩展态）
    """
    nm = canonical_name(name)
    e = entry_of(name) or {}
    # ① 明细表硬证据
    ev = _detail_evidence(name, detail) if detail else ""
    if ev:
        return {"name": nm, "status": STATUS_HAVE,
                "reason": "本项明细表已列示该数据源（命中「%s」）" % ev, "basis": "detail"}
    # ② 由已取得资料提供
    for host in (e.get("provided_by") or []):
        host = str(host or "").strip()
        if not host:
            continue
        hs, _hb = _material_status(host, available)
        if hs == STATUS_HAVE:
            return {"name": nm, "status": STATUS_HAVE,
                    "reason": "由已取得的「%s」提供（本数据源是该资料的字段/内容）" % host,
                    "basis": "provided_by"}
    # ③ 资料匹配唯一权威
    st, basis = _material_status(nm, available)
    if st == STATUS_HAVE:
        return {"name": nm, "status": STATUS_HAVE, "reason": basis or "本轮已提供", "basis": "material"}
    # ④ 本业态不适用（不构成资料缺失）
    try:
        from engine.industry_resolver import classify_not_required_segments as _cls
        _keep, _na, _had = _cls(nm, not_required)
        if _had and not _keep:
            return {"name": nm, "status": STATUS_NA,
                    "reason": "该数据源与本企业业态不符（不构成资料缺失、不计入要求）",
                    "basis": "not_required"}
    except Exception:                        # noqa: BLE001 - 取不到权威 ⇒ 不改判
        pass
    if st == "待核":
        return {"name": nm, "status": STATUS_NEED, "reason": basis or "须人工确认是否含本项内容",
                "basis": "material_pending"}
    return {"name": nm, "status": STATUS_MISSING, "reason": basis or "本轮未提供该数据源",
            "basis": "material_missing"}


def combine(items: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """逐源状态 → **要件级合成状态 + 逐源说明**（唯一实现）。

    合成规则（用户规格第 2 条）：
      全有（含"不适用"）= 已有；部分 = 须核对（**点名缺哪些**）；
      全缺 —— **看缺的形态**：凡有源属「须核对」（有关联类别、须人工确认），组合也是「须核对」；
              只有**全部**都是「缺失/待企业提交」才判「缺失」。
    ★ 为什么"全缺"要分两种（实测）：把"须人工确认"一并说成「缺失」＝**说重了**
      （"本轮未提供"与"提供了相关类别但需确认"是两件事），企业会以为自己没交资料。
    """
    have = [i["name"] for i in items if i["status"] == STATUS_HAVE]
    na = [i["name"] for i in items if i["status"] == STATUS_NA]
    need = [i["name"] for i in items if i["status"] == STATUS_NEED]
    miss = [i["name"] for i in items if i["status"] in (STATUS_MISSING, STATUS_PENDING)]
    lack = need + miss
    if not items:
        return {"status": STATUS_NEED, "have": [], "missing": [], "na": [],
                "reason": "未声明独立数据源", "provided": False}
    if not lack:
        return {"status": STATUS_HAVE, "have": have, "missing": [], "na": na,
                "reason": ("本轮已取得：%s" % "、".join(have)) if have else "均属本业态不适用",
                "provided": True}
    if have or na:
        return {"status": STATUS_NEED, "have": have, "missing": lack, "na": na,
                "reason": "本轮已取得：%s；尚未取得：%s"
                          % ("、".join(have) if have else "（无）", "、".join(lack)),
                "provided": False}
    if need:
        return {"status": STATUS_NEED, "have": [], "missing": need + miss, "na": na,
                "reason": "本轮尚未取得：%s（已提供资料中有类别相关内容，须人工确认是否含本项内容）"
                          % "、".join(need + miss), "provided": False}
    return {"status": STATUS_MISSING, "have": [], "missing": miss, "na": na,
            "reason": "本轮均未提供：%s" % "、".join(miss), "provided": False}


def resolve_group(group_text: Any, *, available: Sequence[str] = (), detail: str = "",
                  not_required: Any = None) -> Dict[str, Any]:
    """多源组合串 → 逐源判定 + 合成（要件核对表的**唯一取数入口**）。"""
    names = split_sources(group_text)
    items = [status_of(n, available=available, detail=detail, not_required=not_required)
             for n in names]
    comb = combine(items)
    comb["items"] = items
    comb["group"] = "、".join(names)
    return comb


# --------------------------------------------------------------------------
# 规格【输出】：数据源状态表
# --------------------------------------------------------------------------
def available_of_suspicion(s: Dict[str, Any]) -> List[str]:
    """本项**本轮已取得资料**清单（唯一取法：`evidence_chain.available_materials`）。"""
    ec = (s or {}).get("evidence_chain") or {}
    if not isinstance(ec, dict):
        return []
    return [str(a) for a in (ec.get("available_materials") or []) if a]


def declared_sources(s: Dict[str, Any]) -> List[str]:
    """本项**全部要件声明的数据源**（去重保序；用于报告级状态表）。"""
    out: List[str] = []
    for src in ((s or {}).get("constituent_sources") or []):
        raw = src if isinstance(src, str) else ((src or {}).get("name") if isinstance(src, dict) else "")
        for nm in split_sources(raw):
            cnm = canonical_name(nm)
            if cnm and cnm not in out:
                out.append(cnm)
    return out


def source_status_map(s: Dict[str, Any], *, not_required: Any = None,
                      detail: Any = None) -> Dict[str, Dict[str, Any]]:
    """疑点对象 → **逐源状态表**（唯一取数；要件核对与报告级状态表**都走这里**）。

    ⚠ 必须同一入口：两处各算一遍 ⇒ "核对表一种状态、状态表另一种状态"的两张皮
      （两者都"看起来对"，靠人眼几乎查不出来）。
    """
    d = detail if detail is not None else detail_text_from_suspicion(s)
    avail = available_of_suspicion(s)
    return {nm: status_of(nm, available=avail, detail=d, not_required=not_required)
            for nm in declared_sources(s)}


def table_from(problem: Dict[str, Any], suspicion: Dict[str, Any], *,
               not_required: Any = None) -> List[Dict[str, Any]]:
    """报告级「数据源状态表」（规格【输出】字段；**唯一产出点**）。

    `status_in_checklist` 取自 `source_status_map(suspicion)` —— 与要件核对表**同一份判定**；
    `status_in_detail` 取自**渲染后的明细表**（`detail_text(problem)`，这是"明细表侧"的事实）。
    """
    detail_rendered = detail_text(problem)
    smap = source_status_map(suspicion, not_required=not_required)
    rows: List[Dict[str, Any]] = []
    for nm, st in smap.items():
        ev = _detail_evidence(nm, detail_rendered) if detail_rendered else ""
        in_detail = STATUS_HAVE if ev else ""
        status = str(st.get("status") or "")
        conflict = ""
        if in_detail == STATUS_HAVE and status in (STATUS_MISSING, STATUS_NEED, STATUS_PENDING):
            conflict = ("明细表已列示该数据源（命中「%s」），核对表却判「%s」" % (ev, status))
        rows.append({
            "data_source_id": data_source_id(nm),
            "data_source_name": nm,
            "status_in_detail": in_detail,
            "status_in_checklist": status,
            "consistency": not conflict,
            "conflict_reason": conflict,
            "_detail_evidence": ev,
            "_reason": str(st.get("reason") or ""),
        })
    return rows


def table_for(problem: Dict[str, Any], *, available: Sequence[str] = (),
              not_required: Any = None) -> List[Dict[str, Any]]:
    """本项「数据源状态表」（字段完全按用户规格）。

    字段：`data_source_id / data_source_name / status_in_detail / status_in_checklist
          / consistency / conflict_reason`

    **同源取数（关键）**：`status_in_checklist` 优先取要件核对表行里带出的**逐源状态**
    （`_data_sources`，由 `constituent_checkpoint` 判定时一并写入）——**不另算一遍**；
    取不到才用 `status_of()` 兜底重算。两处各算一遍必然出现"核对表一种状态、状态表另一种状态"
    的两张皮，而两者都"看起来对"。

    `status_in_detail`：明细表里是否出现该数据源（规则 3 的"明细表侧状态"）。
    `consistency`：两者不得矛盾 —— **明细表里已出现**却判成缺口类状态即为冲突。
    """
    detail = detail_text(problem)
    rows: List[Dict[str, Any]] = []
    seen: Dict[str, Dict[str, Any]] = {}
    # ① 从要件核对表行聚合（逐源状态 + 明细表证据）
    for np_ in ((problem or {}).get("narrative_paragraphs") or []):
        for t in (np_.get("detail_tables") or []):
            if "构成要件" not in str((t or {}).get("title") or ""):
                continue
            for r in (t.get("rows") or []):
                if not isinstance(r, dict):
                    continue
                per = r.get("_data_sources")
                if not isinstance(per, list) or not per:
                    continue
                for it in per:
                    nm = str((it or {}).get("name") or "").strip()
                    if not nm or nm in seen:
                        continue
                    seen[nm] = {"status": str(it.get("status") or ""),
                                "reason": str(it.get("reason") or ""),
                                "basis": str(it.get("basis") or "")}
    # ② 组装（按"要件表声明顺序"稳定输出）
    declared: List[str] = []
    for np_ in ((problem or {}).get("narrative_paragraphs") or []):
        for t in (np_.get("detail_tables") or []):
            if "构成要件" not in str((t or {}).get("title") or ""):
                continue
            for r in (t.get("rows") or []):
                if isinstance(r, dict):
                    for nm in split_sources(r.get("独立数据源")):
                        nm = canonical_name(nm)
                        if nm and nm not in declared:
                            declared.append(nm)
    for nm in declared:
        ev = _detail_evidence(nm, detail) if detail else ""
        in_detail = STATUS_HAVE if ev else ""
        info = seen.get(nm) or {}
        st = str(info.get("status") or "")
        reason = str(info.get("reason") or "")
        if not st:                            # 兜底：没有逐源结果时按规则重算（留痕 basis=fallback）
            d = status_of(nm, available=available, detail=detail, not_required=not_required)
            st, reason = d["status"], d["reason"]
        conflict = ""
        if in_detail == STATUS_HAVE and st in (STATUS_MISSING, STATUS_NEED, STATUS_PENDING):
            conflict = ("明细表已列示该数据源（命中「%s」），核对表却判「%s」" % (ev, st))
        rows.append({
            "data_source_id": data_source_id(nm),
            "data_source_name": nm,
            "status_in_detail": in_detail,
            "status_in_checklist": st,
            "consistency": not conflict,
            "conflict_reason": conflict,
            "_detail_evidence": ev,
            "_reason": reason,
        })
    return rows


#: 去重引用语标记（★ 唯一权威：engine/dupkit.DEDUP_REF_MARK / is_dedup_ref）。
#: ★ 2026-10-08 冗余清理：本模块此前自持一份 `_DEDUP_REF_MARK` + `_is_dedup_ref`，
#:   **全仓无任何调用点（死代码）**，已删除。若后续需跳过被去重替换的引用语，
#:   请 `from engine.dupkit import is_dedup_ref`，勿再自持字面量。


def audit_product(rep: Dict[str, Any], *,
                  available_of=None) -> List[Dict[str, Any]]:
    """**产物级自检**（门禁唯一入口）：明细表与核对表的状态不得互相矛盾。

    `available_of(problem)` 由调用方提供"本项已取得资料清单"取法（产物里按疑点存的是
    `evidence_chain.available_materials`；门禁读产物时用它，运行时用 suspicion 对象）。
    """
    issues: List[Dict[str, Any]] = []
    if not isinstance(rep, dict):
        return issues
    er = rep.get("enterprise_readable_report") or rep
    for p in (er.get("confirmed_problems") or []):
        if not isinstance(p, dict):
            continue
        rid = str(p.get("redline_id") or p.get("title") or "")
        title = str(p.get("title") or "")[:20]
        avail = list(available_of(p) or []) if available_of else []
        detail = detail_text(p)
        # ① 每条要件行：独立数据源组内"已取得的源"不得被整体否定
        for np_ in (p.get("narrative_paragraphs") or []):
            for t in (np_.get("detail_tables") or []):
                if "构成要件" not in str((t or {}).get("title") or ""):
                    continue
                for r in (t.get("rows") or []):
                    if not isinstance(r, dict):
                        continue
                    src = str(r.get("独立数据源") or "")
                    if not src or src.startswith("（红线定义未标注"):
                        continue
                    st_col = str(r.get("数据源状态") or "")
                    cc = str(r.get("核对结论") or "")
                    comb = resolve_group(src, available=avail, detail=detail)
                    have = comb.get("have") or []
                    if have and "未取得" in cc:
                        issues.append({
                            "parent": rid, "kind": "detail_have_but_checklist_missing",
                            "detail": "疑点「%s」%s：独立数据源组内本轮**已取得** %s，"
                                      "核对结论却写「未取得」（%s）"
                                      % (title, r.get("要件序号") or "", "、".join(have),
                                         cc[:40])})
                    if have and st_col in (STATUS_MISSING, "未取得"):
                        issues.append({
                            "parent": rid, "kind": "status_column_contradicts_have",
                            "detail": "疑点「%s」%s：独立数据源组内本轮已取得 %s，"
                                      "「数据源状态」列却写「%s」"
                                      % (title, r.get("要件序号") or "", "、".join(have),
                                         st_col)})
                    # ★★ 2026-10-09（根因）：原规则「结论含『符合情形』⇒ 状态不得是缺口类」
                    #   **已删除**。它假定"现象已检出 ⇒ 本要件声明的独立数据源必已取得"，
                    #   而**前提条的现象可由触发信号（其他资料）检出**，其声明源仍可未取得
                    #   ⇒ 该假定不成立，会把**如实登记**误报成同页矛盾（实测 12 条前提条中
                    #   6 条被判"自相矛盾"）；旧实现为躲它，把状态列**无据改写成「已有」**，
                    #   反过来又与「数据源状态表」打架，并让审计闸门把"补充提供「X」"
                    #   误报成"X 已判已有却又要补"（seq=16 实测）。
                    #   现口径：**状态列必须等于唯一权威 `resolve_group/combine` 的合成结论**
                    #   —— 该断言已落在审计闸门 `check_data_source_status_consistency` 规则④
                    #   （读落盘的「数据源状态表」，与被检对象同一份判定，不另算一遍）。
                    #   此处保留 `status_column_contradicts_have`（组内已取得却写缺口）即可。
                    _ = cc  # cc 仍用于上方"未取得"文案断言；此处不再据它判缺口矛盾
        # ② 结构化数据源状态表必须落盘且自洽
        tbl = p.get("data_source_status")
        if not isinstance(tbl, list) or not tbl:
            if detail:
                issues.append({"parent": rid, "kind": "table_missing",
                               "detail": "疑点「%s」缺「数据源状态表」data_source_status"
                                         "（规格【输出】字段）" % title})
            continue
        for row in tbl:
            if not isinstance(row, dict):
                continue
            for f in ("data_source_id", "data_source_name", "status_in_detail",
                      "status_in_checklist", "consistency", "conflict_reason"):
                if f not in row:
                    issues.append({"parent": rid, "kind": "field_missing",
                                   "detail": "疑点「%s」数据源状态表缺字段「%s」" % (title, f)})
            if row.get("consistency") is False and str(row.get("conflict_reason") or "").strip():
                issues.append({"parent": rid, "kind": "inconsistent",
                               "detail": "疑点「%s」数据源「%s」状态不一致：%s"
                                         % (title, row.get("data_source_name"),
                                            row.get("conflict_reason"))})
    return issues


__all__ = ["VERSION", "STATUS_HAVE", "STATUS_MISSING", "STATUS_NEED", "STATUS_PENDING",
           "STATUS_NA", "STATUSES", "STATUSES_ALL", "load_config", "reload_config",
           "sources", "entry_of", "data_source_id", "canonical_name", "split_sources",
           "detail_text", "detail_text_from_suspicion", "available_of_suspicion",
           "declared_sources", "status_of", "combine", "resolve_group",
           "source_status_map", "table_from", "table_for", "audit_product"]
