# -*- coding: utf-8 -*-
"""法条引用单一权威：把「法名 / 法名+条款号」补全为「《法名》第X条：条文内容」。

用户口径（2026-09-27）：「法定依据要写到**具体哪一条、什么内容**」——只写法名
（如「《发票管理办法》」）或只写条款号（如「《增值税专用发票使用规定》第十四条」）
都不够，必须给出条款号 + 条文内容。

数据源（优先级）：
  1. `static/legal_library.json` —— 法条内容库（法名+条款号 → 内容），人工维护、可复核；
  2. 红线库 `tax_redlines.REDLINES` 的 `legal_basis` 中**已内嵌条文**的条目（`《X》第Y条：内容`），
     自动抽取复用（口径一致，非特例）；
  3. `static/legal_refs.json`（历史法条要点库，短名，如「征管法第63条」）。

解析规则：`《……》（可含公告号）` + `第X条[、第Y条][第Z款]` + `（说明）` + `：内容`。
解析不了或查不到内容的，**原样保留**（绝不臆造法条）。所有条目只读、不改引擎结论。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent

# 条款号：第X条[、第Y条]… [第Z款]
# ★ 2026-10-12 修正（T-5 根因，实测）：原正则**只认「第X条、第Y条」**，不认
#   「第X条**至**第Y条」这种**范围**写法 ⇒ `split_citation` 在末尾只能匹配到
#   「第四十五条」，剩「第四十条至」被末段 `if rest: law = law + rest` **拼回法名**
#   ⇒ 法名被污染成「企业所得税法实施条例第四十条至」，进而在法条版本闸门里
#   被当成一个"不存在的法名"（假缺口）。此处补范围分隔符，法名不再被污染。
_ART_RE = re.compile(
    r"(第[一二三四五六七八九十百零〇\d]+条"
    r"(?:\s*[、,，]\s*第[一二三四五六七八九十百零〇\d]+条)*"
    r"(?:\s*[至~～\-—－]\s*第[一二三四五六七八九十百零〇\d]+条)?"
    r"(?:第[一二三四五六七八九十]+款)?)\s*$"
)
_LIB_CACHE: Optional[Dict[Tuple[str, str], str]] = None


# ── 「法律依据写在哪个字段」的**唯一权威** ─────────────────────────────────────────
# ★★ 2026-10-04（疑点10-21 合并批次 ⑭）：同一份法条会被写进**两个字段**——
#    `policy_ref`（报告呈现侧优先读）与 `law_ref`（门禁/自动修复侧默认写）。
#    事故（实测）：4 项高风险发现被 `auto_heal` 写进 `policy_ref`，而 M06 判据只读
#    `law_ref` ⇒ 明明已有《社会保险法》第五十八条，仍被判"高风险发现缺少法律依据"
#    ⇒ 报告被打成「合规门禁阻断：4 项阻断性违规」。判据与产出不同源＝口径错。
# ⇒ 凡要判断"这项发现有没有可呈现的法律依据"，一律走本函数，
#    新增/调整法条字段名只改这里一行。
_LEGAL_REF_FIELDS: Tuple[str, ...] = ("policy_ref", "law_ref", "legal_ref")


def legal_reference_of(finding: Dict) -> str:
    """取该发现的**可呈现法律依据**（优先级见 `_LEGAL_REF_FIELDS`）；没有则返回 ""。

    判空规则：**非空即视为已具备依据**——不得用"字段值看着不像法条"去反推没有，
    那会把合法引用（如汇总型说明）误判成缺法条。
    """
    if not isinstance(finding, Dict):
        return ""
    for f in _LEGAL_REF_FIELDS:
        v = str((finding.get(f) or "")).strip()
        if v:
            return v
    return ""


def has_legal_reference(finding: Dict) -> bool:
    return bool(legal_reference_of(finding))


def norm_law(s: str) -> str:
    """法名归一：去《》（），去掉「中华人民共和国」，去空白。"""
    s = str(s or "").replace("《", "").replace("》", "")
    s = s.replace("中华人民共和国", "")
    return re.sub(r"\s+", "", s)


def norm_art(a: str) -> str:
    return re.sub(r"\s+", "", str(a or ""))


def strip_article_from_law(law: str) -> str:
    """法名**兜底**：法名里不得残留条文号（2026-10-12，T-5 根因）。

    为什么需要兜底：源数据里存在"两处条文"写法（如
    `《增值税暂行条例》第六条及其实施细则第十二条`），按末尾条文剥离后
    前缀仍含「第六条」⇒ 法名被污染 ⇒ 法条版本闸门当成"不存在的法名"（假缺口）。
    法名一旦出现条文号，即截止于**第一个**条文号。

    抽成独立函数是为了**可反向验证**（测试可临时替换为恒等函数，证明不变量非空）。
    """
    return re.split(r"第[一二三四五六七八九十百零〇\d]+条", str(law or ""))[0].strip()


def split_citation(s: str) -> Tuple[str, str, str, str]:
    """把一条引用拆成 (法名, 条款号, 括注, 内容)。拆不出的部分留空。

    支持：「《法名》第X条：内容」「《法名》（公告号）第X条」「《法名》第X条、第Y条（说明）」
    「（前缀）《法名》第X条：内容」等写法。
    """
    raw = str(s or "").strip()
    if not raw:
        return "", "", "", ""
    content = ""
    head = raw
    m = re.search(r"[：:]", raw)
    if m:
        head, content = raw[: m.start()], raw[m.end():].strip()
    head = head.strip()
    # ① 法名 = 首个《…》及其后紧跟的（…）；否则退化为取《…》所在片段
    # ① 法名 = 首个《…》及其后紧跟的（…）；否则退化为取《…》所在片段
    law = ""
    rest = head
    ml = re.match(r"^(.*?《[^》]+》)(（[^（）]+）)?", head)
    if ml:
        law = (ml.group(1) + (ml.group(2) or "")).strip()
        rest = head[ml.end():].strip()
    else:
        # ★ 2026-10-12 修正：**无书名号**的引用（如「财税〔2003〕158号第二条」）也要能
        #   剥离条文 —— 原实现 `law = head; rest = ""` 会把**条文一起吞进法名**
        #   （实测 4 处：RL-FUND-003 / RL-CIT-006 / RL-PAY-006 / 同类）。
        #   改为法名留空、把整串交给 ③ 段按条文切分。
        law = ""
        rest = head
    # ② 尾部括注（如「（扣缴义务人全员全额扣缴申报）」）
    note = ""
    mn = re.search(r"（[^（）]{1,40}）\s*$", rest)
    if mn:
        note = mn.group(0)
        rest = rest[: mn.start()].strip()
    # ③ 条款号
    # ★ 2026-10-12 修正（T-5 根因，实测 6 处）：原实现只在**条文位于末尾**时才剥离，
    #   若条文后还有内容（「…第四十六条**及其实施细则**」「…第四十六条**（长说明）**」
    #   「财税〔2018〕164号**第一条**」），`_ART_RE` 因 `$` 锚定匹配失败 ⇒
    #   整段被末段 `if rest: law = law + rest` **拼回法名** ⇒ 法名含条文号。
    #   修法：条文一旦出现，法名即在其**前**截止；条文号单独取出，其余不再入法名。
    art = ""
    ma = _ART_RE.search(rest)
    if ma:
        art = ma.group(1)
        rest = rest[: ma.start()].strip()
    else:
        mb = re.search(r"第[一二三四五六七八九十百零〇\d]+条", rest)
        if mb:
            art = mb.group(0)
            rest = rest[: mb.start()].strip()
    if rest:
        law = (law + rest).strip()
    # ★ 2026-10-12 兜底：法名**不得残留条文号**（见 `strip_article_from_law` 说明）
    law = strip_article_from_law(law)
    return norm_law(law), norm_art(art), note, content


def _extract_from_redlines() -> Dict[Tuple[str, str], str]:
    """从红线库 legal_basis 已内嵌条文的条目抽取 (法名, 条款号) → 内容。"""
    out: Dict[Tuple[str, str], str] = {}
    try:
        from engine.tax_redlines import REDLINES
    except Exception:
        return out
    for r in REDLINES or []:
        lb = (r or {}).get("legal_basis")
        if isinstance(lb, str):
            lb = [lb]
        for item in (lb or []):
            if not isinstance(item, str):
                continue
            law, art, _note, content = split_citation(item)
            if law and content:
                out.setdefault((law, art), content)
    return out


def _load_library() -> Dict[Tuple[str, str], str]:
    global _LIB_CACHE
    if _LIB_CACHE is not None:
        return _LIB_CACHE
    lib: Dict[Tuple[str, str], str] = {}
    # ① 法条内容库
    for name in ("legal_library.json", "legal_refs.json"):
        p = _ROOT / "static" / name
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for e in (data if isinstance(data, list) else []):
            if not isinstance(e, dict):
                continue
            content = str(e.get("content") or "").strip()
            if not content:
                continue
            if e.get("law") and e.get("article"):
                lib.setdefault((norm_law(e["law"]), norm_art(e["article"])), content)
            elif e.get("law"):
                # 短名（如「征管法第63条」）→ 拆出条款号
                law, art, _n, _c = split_citation(str(e.get("law")))
                lib.setdefault((law, art), content)
    # ② 红线库内嵌条文（不覆盖①②中已有的同名同条）
    for k, v in _extract_from_redlines().items():
        lib.setdefault(k, v)
    _LIB_CACHE = lib
    return lib


def resolve_citation(s) -> str:
    """把一条引用解析为「《法名》第X条（括注）：内容」；查不到内容时原样返回。"""
    if isinstance(s, dict):  # 数据缺陷兜底：legal_basis 里混入 dict
        s = s.get("article") or s.get("law") or ""
    if not isinstance(s, str) or not s.strip():
        return ""
    raw = s.strip()
    law, art, note, content = split_citation(raw)
    if not law:
        return raw
    lib = _load_library()
    if content:                       # 条目内已内嵌条文
        head = f"《{law}》{art}" if art else f"《{law}》"
        return f"{head}{note}：{content}"
    if art:
        whole = lib.get((law, art))
        if whole:
            return f"《{law}》{art}{note}：{whole}"
        # 多条款并列：「第九条、第十条」→ 逐条拼内容
        parts = [p for p in re.split(r"[、,，]", art) if p.strip()]
        segs = []
        for p in parts:
            c = lib.get((law, norm_art(p)))
            if c:
                segs.append(f"{p}：{c}")
        if segs and len(segs) == len(parts):
            return f"《{law}》" + "；".join(segs) + note
        return raw
    # 裸法名（无条款号）：库中该法恰有一条时补全，否则原样（不臆造条款号）
    cands = [c for (l, _a), c in lib.items() if l == law]
    if len(cands) == 1:
        return f"《{law}》{note}：{cands[0]}"
    return raw


def format_legal_basis(items, with_version: bool = False) -> str:
    """把 legal_basis（list/str）渲染为「…；…」，逐条补全条款号与内容，去重保序。

    ★ `with_version=True`（2026-10-07 用户第 3 批 任务4「法条版本化」）：
      每条引用后附**版本括注**（唯一权威 `engine.legal_version.version_note`）——
      已登记 ⇒「（2023年修订；国务院令第764号，现行有效）」；**未登记 ⇒
      「（版本未登记，须核对现行有效文本）」**，绝不默认按现行有效呈现。
      **同一部法只注一次**（首次出现处），避免同一段里重复刷版本。
      ★ 版本括注只含"年/文号/状态"语义，**不含金额锚点词与"元"** ⇒
        不会改变 `tax_impact.extract_amount` 的锚定（改后须做 tax_impact 全量 diff 证明）。
    """
    if isinstance(items, str):
        items = [items]
    out: List[str] = []
    seen = set()
    for it in (items or []):
        t = resolve_citation(it)
        if not t:
            continue
        k = re.sub(r"\s+", "", t)
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
    if with_version and out:
        try:
            from engine.legal_version import version_note as _vn
        except Exception:
            _vn = None
        if _vn is not None:
            _noted: set = set()
            _out2: List[str] = []
            for t in out:
                law, _art, _note, _c = split_citation(t)
                lk = norm_law(law)
                if lk and lk not in _noted:
                    _noted.add(lk)
                    t = t + _vn(law)
                _out2.append(t)
            out = _out2
    return "；".join(out)
