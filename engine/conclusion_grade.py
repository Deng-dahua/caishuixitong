# -*- coding: utf-8 -*-
"""结论分级 + 关键证据一票否决 —— 唯一权威。

WB-TRISK-2026-001 §3.1（关键证据缺失一票否决）+ §3.2（结论分级引擎）。
四级：L1 风险指标命中 / L2 待核线索 / L3 风险事项成立 / L4 违法认定（系统不输出）。

判据表 = `config/conclusion_grades.json`（含 grades / verdict_mapping / veto_rules / level_vocab）。
本模块只做两件事：① 把 config 的判据落到可执行的谓词；② 保证词表与
`engine/risk_levels.LEGAL_LEVELS` **逐字一致**（防止两套词表并存——本项目高发病根）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from engine import risk_levels

__all__ = [
    "GRADE_L1", "GRADE_L2", "GRADE_L3", "GRADE_L4",
    "GRADE_IDS",
    "load_spec", "load_errors", "vocab_consistency", "veto_trigger_coverage",
    "grades", "grade_by_id", "min_closure", "map_verdict", "allowed_levels",
    "level_ceiling", "cap_level_for_grade", "effective_grade_id",
    "normalize_level", "contains_determinative", "veto_triggers", "veto_applies",
    "apply_veto", "analyze_item", "verdict_vocab_consistency", "VERSION",
    "verdict_text", "pending_clue_phrase", "term_authority", "conclusion_terms", "term_of",
    "authorized_labels",
]

VERSION = "1.0.0"
GRADE_L1, GRADE_L2, GRADE_L3, GRADE_L4 = "L1", "L2", "L3", "L4"
#: 四级标识的**有名集合**（判据里禁止再散落 "L1"/"L2" 字面量判断）。
GRADE_IDS: Tuple[str, ...] = (GRADE_L1, GRADE_L2, GRADE_L3, GRADE_L4)

_ROOT = Path(__file__).resolve().parent.parent
_CFG = _ROOT / "config" / "conclusion_grades.json"
_CACHE: Optional[Dict[str, Any]] = None
_LOAD_ERRORS: List[str] = []

#: 回退词表（config 读不出时用）——与 risk_levels 同源，不新造词。
_FALLBACK_LEVELS: Tuple[str, ...] = tuple(risk_levels.LEGAL_LEVELS)
_FALLBACK_VETO_WORDS: Tuple[str, ...] = (
    "已查明", "已认定", "认定成立", "构成偷税", "认定为偷税", "定性成立",
    "已触碰", "违法行为", "逃税", "虚开成立", "确认虚开", "确定违法",
)


def load_spec() -> Dict[str, Any]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    try:
        with open(_CFG, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict) or not data.get("grades"):
            _LOAD_ERRORS.append(f"{_CFG} 缺 grades 键")
            data = {}
    except Exception as exc:  # noqa: BLE001 —— 留痕后回退
        _LOAD_ERRORS.append(f"读 {_CFG} 失败：{exc}")
        data = {}
    _CACHE = data
    return _CACHE


def load_errors() -> List[str]:
    load_spec()
    return list(_LOAD_ERRORS)


# ---------------------------------------------------------------- 词表
def verdict_vocab_consistency() -> List[str]:
    """★与 `engine/argumentation.py` 的裁决词常量双向校验（防措辞漂移）。

    本项目高发病根：同一句话在两处各写一遍，改一处另一处静默失效。
    实测事故：本模块首版 config 键写「（资料齐全，可初步判断）」，而 argumentation 的常量是
    「（资料齐全，可作初步判断）」——差一个「作」字，映射表整条失效（反向验证当场抓到）。
    """
    errs: List[str] = []
    try:
        from engine import argumentation as arg
    except Exception as exc:  # noqa: BLE001
        return [f"无法导入 engine/argumentation.py：{exc}"]
    mapping = load_spec().get("verdict_mapping") or {}
    consts = {k: v for k, v in vars(arg).items() if k.startswith(("_VERDICT_", "GRADE_")) and isinstance(v, str)}
    for name, text in sorted(consts.items()):
        if text not in mapping:
            errs.append(f"argumentation.{name} 的裁决词未登记到 config/conclusion_grades.json 的 verdict_mapping：{text!r}")
    return errs


def grades() -> List[Dict[str, Any]]:
    return list(load_spec().get("grades") or [])


def grade_by_id(gid: str) -> Optional[Dict[str, Any]]:
    for g in grades():
        if g.get("id") == gid:
            return g
    return None


def level_vocab() -> Dict[str, Any]:
    return dict(load_spec().get("level_vocab") or {})


def term_authority() -> Dict[str, Any]:
    """报告**结论用语**权威表（用户条款《专注税务风险检查条款》第4条）。

    唯一权威为 `config/conclusion_grades.json::term_authority`；本函数只做薄转发。
    """
    return dict(load_spec().get("term_authority") or {})


def conclusion_terms() -> Tuple[str, ...]:
    """四个结论术语：风险信号 / 待核事项 / 已认定事实 / 违法认定。"""
    return tuple(term_authority().get("terms") or ())


def term_of(gid: str) -> str:
    """结论等级 → 对外术语（L1→风险信号、L2→待核事项、L3→已认定事实、L4→违法认定）。"""
    return str((term_authority().get("by_grade") or {}).get(gid, ""))


def authorized_labels() -> Tuple[str, ...]:
    """报告**合法标签**（不得被当作模糊/不确定措辞）—— 唯一权威 `config/conclusion_grades.json`。

    = ① `term_authority.terms`（四个结论用语）＋ ② `verdict_mapping` 的键
      （＝权威登记的裁决语/等级标签，如「待核」「已核定」「已排除」）
      ＋ ③ `risk_levels.LEGAL_LEVELS`（**A5 等级词表**，含合法档位「待核验」）。

    ★★ 2026-10-09（P1-4 **词表冲突**）：A5（等级词表）把「待核」「待核验」当**合法档位**，
      D7（模糊词闸门）却把二者当**禁用模糊词** ⇒ 同一个词两处判定相反。
      修法：D7 的判据一并豁免本表——**从权威表生成**，不新增硬编码词，
      使 A5 与 D7 同源（`report_wording.vague_hits` 消费本函数）。
      ⚠ 豁免是**「整串相等」语义**（`report_wording.vague_hits`）：
        字段值身份（整行就是「待核」）合法；**嵌在句中/事项名里仍是模糊措辞**
        （「其他应付款大额长期挂账（待核）」必须被拦下）。
    """
    spec = load_spec()
    out: List[str] = []
    for t in ((spec.get("term_authority") or {}).get("terms") or ()):
        s = str(t).strip()
        if s and s not in out:
            out.append(s)
    # ⚠ 只取**真正映射到等级 id** 的键：`note` / `authority` 是结构键（值不是等级 id），
    #   第一版按 `startswith("note")` 过滤 ⇒ 漏掉 `authority`（值=引擎文件路径）被当成"合法标签"。
    #   判据改用「值 ∈ grades.id」——新增结构键时自动排除，不必再改代码。
    _grades = {str(g.get("id")).strip() for g in (spec.get("grades") or []) if isinstance(g, dict)}
    for k, v in (spec.get("verdict_mapping") or {}).items():
        if str(v).strip() not in _grades:
            continue
        s = str(k).strip()
        if s and s not in out:
            out.append(s)
    for lv in (risk_levels.LEGAL_LEVELS or ()):          # A5 等级词表（唯一权威）
        s = str(lv).strip()
        if s and s not in out:
            out.append(s)
    return tuple(out)


#: 各等级**裁决语模板**（唯一权威）。`{term}` = 该等级的对外术语（`term_of`）。
#  ★ 2026-10-09（P1-1）：为什么必须收敛到一处 ——
#    L1/L2 条目的裁决语**不得含定性词**（`allow_determinative_words=false`），
#    而"哪些词算定性词"只由 `veto_rules.determinative_words` 定义。
#    若各分支各写一套句式，新增一个定性词时**只有一处会跟着改** ⇒ 另一处静默漏判。
#    收敛后：句式改一处即全报告改；且模板里**一个定性词都不出现**（见闸门 `check_conclusion_wording_authority`）。
_VERDICT_TEMPLATES: Dict[str, str] = {
    # L1：本轮仅命中风险指标，未做构成要件核对
    "L1": "本项属{term}；本轮仅命中风险指标，未做构成要件核对，不作认定",
    # L2：账内已读到与风险指向一致的信号，但构成要件未逐条核对成立
    "L2": "本项属{term}{note}；未认定到构成要件，不作定性",
    # L3：构成要件逐条核对成立且关键证据齐备（术语本身合法，不再叠加定性词）
    "L3": "本项属{term}；构成要件逐条核对成立，可作初步判断",
    # L4：系统永不输出，须转交有权人员
    "L4": "本项属{term}；须由有权人员依法认定",
}


def verdict_text(grade: Any = None, *, source_note: str = "",
                 with_scope_note: bool = False) -> str:
    """**裁决语唯一生成点**（L1~L4）—— 报告结论语句只能由本函数产出（P1-1）。

    ★★ 2026-10-09（P1-1 唯一权威收口）：
      病根：裁决语此前散在多处 —— `pending_clue_phrase()`（L2）、`argumentation` 的
        `GRADE_*` 常量、以及 `enterprise_report` 的若干硬编码句。裁决语**必须**满足
        "L1/L2 不含定性词"，而"定性词"只在 `veto_rules.determinative_words` 一处定义；
        多头产出 ⇒ 新增一个定性词时只有一处跟着改，另一处静默漏判。

      本函数是**唯一**产出裁决语的地方（闸门断言 `grep -c "^def verdict_text" == 1`）。
      句式 = `_VERDICT_TEMPLATES[grade]`，术语 = `term_of(grade)`（改一处即全报告改）。

    :param grade: 结论等级（L1/L2/L3/L4）；取不到或非法 ⇒ 按 L2（最保守的"未定性"档）。
    :param source_note: 本项来源备注（如「另行检出的域分析结论」）；空则不写括注。
    :param with_scope_note: 是否附「（认定范围见本项说明）」——供"范围被裁剪过"的场合使用。
    """
    gid = str(grade or "").strip()
    if gid not in GRADE_IDS:
        gid = GRADE_L2
    _term = term_of(gid)
    if not _term:
        return ""
    _note = ("（来源：%s）" % str(source_note).strip()) if str(source_note or "").strip() else ""
    _tpl = _VERDICT_TEMPLATES.get(gid, _VERDICT_TEMPLATES[GRADE_L2])
    _s = _tpl.format(term=_term, note=_note)
    return _s + "（认定范围见本项说明）" if with_scope_note else _s


def pending_clue_phrase(source_note: str = "", with_scope_note: bool = False) -> str:
    """**L2（待核线索）结论用语** —— `verdict_text("L2", ...)` 的**薄转发**（唯一权威见该函数）。

    ★★ 2026-10-08（P0-2 用语权威收口，四门禁实测取证）：
      病根：`enterprise_report.py` 有 **3 处硬编码**同一句式「本项**已查明**的风险…」。
      ① 措辞违反本文件 `term_authority`（用户条款《专注税务风险检查条款》第 4 条：
         报告结论用语**只能用四个术语**，L2 对应「待核事项」）——
         "已查明"是**定性词**，而 L2 的 `allow_determinative_words=false`；
      ② 质量门禁同一事项因此**双报**：A3「关键证据缺失时仍出现定性词」11 项、
         B5「同一事项内并存『未认定』与『已查明』」11 项 —— 同一病根两处出血；
      ③ 更糟：L2 的 `required_text` 要求含「待核」「不作定性」，字面量里一个都没有。

    ⚠ 本函数**只转发、不再自写句式**（否则又是"同一概念两处维护"）。
    """
    return verdict_text(GRADE_L2, source_note=source_note, with_scope_note=with_scope_note)


def legal_levels() -> Tuple[str, ...]:
    v = level_vocab().get("legal")
    return tuple(v) if isinstance(v, list) and v else _FALLBACK_LEVELS


def determinative_words() -> Tuple[str, ...]:
    w = (load_spec().get("veto_rules") or {}).get("determinative_words")
    return tuple(w) if isinstance(w, list) and w else _FALLBACK_VETO_WORDS


def min_closure() -> float:
    g = grade_by_id(GRADE_L3) or {}
    try:
        return float(g.get("min_closure", 0.8))
    except Exception:  # noqa: BLE001
        return 0.8


def allowed_levels(gid: str) -> Tuple[str, ...]:
    g = grade_by_id(gid) or {}
    v = g.get("allow_risk_level")
    return tuple(v) if isinstance(v, list) else ()


def level_ceiling(gid: str) -> str:
    """结论等级 → **允许的风险等级上限**（唯一权威）。

    = `grades[gid].allow_risk_level` 中**最重**的一档（按 `risk_levels.SEVERITY`）。
    只在「风险档」（`risk_levels.RISK_GRADES`）里取，避免把证据状态「待核验」
    当成风险高低的上限（`待核验` 的 SEVERITY=2 反而重于 `低风险`=1，直接取 max 会取错）。
    允许集合为空（L3/L4 无上限）⇒ 返回 ""。
    """
    lvls = allowed_levels(gid)
    if not lvls:
        return ""
    risk = [l for l in lvls if l in risk_levels.RISK_GRADES]
    pool = risk or list(lvls)
    return max(pool, key=lambda x: risk_levels.severity(x))


def cap_level_for_grade(level: Any, gid: str) -> Tuple[str, str]:
    """把 `level` 压到该结论等级**允许的范围内**（配置 `allow_risk_level` 为唯一权威）。

    ★★ 2026-10-09（P0-5）：L1/L2 是"线索级"结论，**不允许**挂 中/高风险
      （config 的 `allow_risk_level` 只给 信息/待核验/低风险）——否则报告出现
      「结论等级=待核线索，风险等级=高风险」这种自相矛盾（门禁 B3 实测命中）。
      旧实现把这条判据散落在各分支（且只判 ≥高风险），现收敛到本函数一处。

    :return: `(最终等级, 被压前的等级)`；无需压制 ⇒ 第二项为 ""。
    """
    lv = str(level or "").strip()
    if not gid or lv not in risk_levels.LEGAL_LEVELS:
        return lv, ""
    lvls = allowed_levels(gid)
    if not lvls or lv in lvls:
        return lv, ""
    ceil = level_ceiling(gid)
    if not ceil or ceil == lv:
        return lv, ""
    return ceil, lv


def effective_grade_id(item: Any) -> Tuple[str, bool]:
    """条目的**生效结论等级**（唯一权威）：显式 L 级 > 裁决语/旧字面映射。

    返回 `(grade_id, registered)`；取不到 ⇒ `("", False)`（调用方**不得**据此压制等级，
    「未登记 ≠ 按 L2 处理」，避免用默认值静默顶替）。
    """
    if not isinstance(item, dict):
        return "", False
    declared = str(item.get("conclusion_grade") or "").strip()
    if declared in GRADE_IDS:
        return declared, True
    for src in (declared, str(item.get("verdict") or "")):
        if not src:
            continue
        gid, reg = map_verdict(src)
        if reg:
            return gid, True
    return "", False


def vocab_consistency() -> List[str]:
    """★与 `risk_levels.LEGAL_LEVELS` 双向校验；不一致返回 ERROR 文案列表。"""
    errs: List[str] = []
    cfg = list(legal_levels())
    auth = list(risk_levels.LEGAL_LEVELS)
    if cfg != auth:
        errs.append(
            "config/conclusion_grades.json 的 level_vocab.legal 与 engine/risk_levels.LEGAL_LEVELS 不一致："
            f"config={cfg} authority={auth}"
        )
    sev = level_vocab().get("severity") or {}
    for lv in auth:
        if lv in sev and risk_levels.SEVERITY.get(lv) != sev[lv]:
            errs.append(f"等级标度不一致 {lv}: config={sev.get(lv)} authority={risk_levels.SEVERITY.get(lv)}")
    return errs


# ---------------------------------------------------------------- 等级归一
def normalize_level(level: Any) -> Tuple[str, Optional[str]]:
    """返回 (合法等级, 原词或 None)。表外词映射到最近合法档并保留原词以便门禁报错。"""
    legal = legal_levels()
    raw = str(level or "").strip()
    if not raw:
        return "", None
    n = risk_levels.normalize(raw)
    if n in legal:
        return n, (None if n == raw else raw)
    # 尝试补/去「风险」后缀
    cand = [n + "风险", n.replace("风险", "")]
    for c in cand:
        if c in legal:
            return c, raw
    # 证据状态词
    for s in level_vocab().get("evidence_states") or []:
        if s in raw:
            return s, raw
    return "待核验", raw


# ---------------------------------------------------------------- verdict 映射
def map_verdict(verdict: Any) -> Tuple[str, bool]:
    """把裁决文案映射到四级。返回 (grade_id, registered)。

    未登记 ⇒ 返回 L2 且 registered=False（门禁应报 WARN，提示补登记映射）。
    """
    text = str(verdict or "").strip()
    mapping = load_spec().get("verdict_mapping") or {}
    base = text.split("（")[0].strip()
    # 长键优先，避免「本项已查明的风险」抢走更具体的键
    for key in sorted((k for k in mapping if not k.startswith("note")), key=len, reverse=True):
        if not isinstance(mapping.get(key), str):
            continue
        if key and (text.startswith(key) or base.startswith(key)):
            return str(mapping[key]), True
    return GRADE_L2, False


# ---------------------------------------------------------------- 一票否决
def _has_text(item: Any, key: str) -> str:
    texts: List[str] = []
    if not isinstance(item, dict):
        return ""
    for k, v in item.items():
        if k in ("evidence_chain", "constituent_checkpoints", "self_doubt", "tax_impact"):
            texts.append(json.dumps(v, ensure_ascii=False))
        elif isinstance(v, str):
            texts.append(v)
        elif isinstance(v, list):
            for x in v:
                if isinstance(x, str):
                    texts.append(x)
                elif isinstance(x, dict):
                    texts.append(json.dumps(x, ensure_ascii=False))
    return "\n".join(texts)


def _pred_body_text(item: Any) -> str:
    """用于定性词扫描的正文（排除规则字段，避免误伤）。"""
    if not isinstance(item, dict):
        return ""
    skip = {"redline_id", "trace_id", "seq", "办理顺序", "risk_level", "conclusion_grade"}
    out: List[str] = []
    for k, v in item.items():
        if k in skip:
            continue
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, (list, dict)):
            out.append(json.dumps(v, ensure_ascii=False))
    return "\n".join(out)


def _closure_of(item: Any) -> Optional[float]:
    if not isinstance(item, dict):
        return None
    v = item.get("closure")
    try:
        return None if v in (None, "") else float(v)
    except Exception:  # noqa: BLE001
        return None


def _evidence_have(item: Any) -> Optional[int]:
    if not isinstance(item, dict):
        return None
    v = item.get("evidence_have")
    try:
        return None if v in (None, "") else int(v)
    except Exception:  # noqa: BLE001
        return None


def veto_triggers(item: Any) -> List[Dict[str, Any]]:
    """检查关键证据一票否决的触发条件，返回命中的触发项（id/why/detail）。"""
    hits: List[Dict[str, Any]] = []
    closure = _closure_of(item)
    have = _evidence_have(item)
    need = (item or {}).get("evidence_need") if isinstance(item, dict) else None
    grade = str((item or {}).get("conclusion_grade") or "").strip() if isinstance(item, dict) else ""

    if closure is None or have is None:
        hits.append({"id": "V5", "why": "等级无证据支撑（closure/evidence_have 未登记）",
                     "detail": f"closure={closure!r} evidence_have={have!r} evidence_need={need!r}"})
    else:
        if closure <= 0.0 or have <= 0:
            hits.append({"id": "V1", "why": "无任何证据被取得",
                         "detail": f"closure={closure} evidence_have={have}/{need}"})
        elif closure < min_closure():
            hits.append({"id": "V2", "why": f"证据链未闭合（closure<{min_closure()}）",
                         "detail": f"closure={closure}"})

    if isinstance(item, dict) and item.get("direct_missing"):
        hits.append({"id": "V3", "why": "直接证据缺失", "detail": str(item.get("direct_missing"))[:120]})

    missing = (item or {}).get("missing_material_names") if isinstance(item, dict) else None
    if missing:
        alt_hint = str(item.get("remedy") or item.get("alternative_evidence") or "")
        if not alt_hint:
            hits.append({"id": "V4", "why": "关键资料缺失且未登记替代资料程序",
                         "detail": f"missing={missing}"})

    if not grade:
        hits.append({"id": "V6", "why": "结论等级未登记", "detail": "conclusion_grade 为空"})

    return hits


def veto_applies(item: Any) -> bool:
    return bool(veto_triggers(item))


def veto_trigger_coverage() -> List[str]:
    """config 里声明但本模块未实现的触发 id（反向覆盖校验）。"""
    declared = [t.get("id") for t in ((load_spec().get("veto_rules") or {}).get("triggers") or [])]
    implemented = {"V1", "V2", "V3", "V4", "V5", "V6"}
    return [d for d in declared if d and d not in implemented]


#: 否定标记（**识别"否定式定性词"**，唯一权威）。凡定性词**紧接在这些标记之后**，
#  即该词出现在否定语境中（如「**不等于**已触碰红线」「**不构成**认定成立」），
#  不构成"使用了定性词"。★ 新增一种否定写法 ⇒ 只加一行数据。
NEGATION_MARKERS: Tuple[str, ...] = (
    "不等于", "不属于", "不代表", "不构成", "不等同", "不算", "并非", "不是",
    "不能", "不得", "不予", "不应该", "不会", "尚未", "未曾", "未经", "未有",
    "无从", "没有", "缺乏", "缺少",
)
#: 单字否定（紧邻定性词前一个字）。
_NEG_CHARS = "不未无非没"


def _is_negated_prefix(pre: str) -> bool:
    """`pre`（定性词之前 ≤4 字）是否构成否定语境。"""
    p = str(pre or "")
    for m in NEGATION_MARKERS:
        if p.endswith(m):
            return True
    return bool(p) and p[-1] in _NEG_CHARS


def contains_determinative(text: Any) -> List[str]:
    """返回命中的定性词（空列表=无）。

    ★★ 2026-10-09（判据假红修复）：旧实现是**裸子串匹配** ⇒ 报告里那句
      「疑点成立不等于风险成立，也不等于**已触碰**红线、不构成**认定成立**违法认定」
      被 A3 判成"关键证据缺失时仍出现定性词"（实测 5 项假红）——
      它恰恰是在**否认**定性。现改为**否定语境感知**匹配（`NEGATION_MARKERS` 唯一权威）：
      定性词若紧接否定标记之后，不计入命中。
    """
    s = str(text or "")
    if not s:
        return []
    hits: List[str] = []
    for w in determinative_words():
        if not w:
            continue
        start = 0
        while True:
            i = s.find(w, start)
            if i < 0:
                break
            if not _is_negated_prefix(s[max(0, i - 4):i]):
                hits.append(w)
                break
            start = i + len(w)
    return hits


def apply_veto(item: Dict[str, Any]) -> Dict[str, Any]:
    """对单项施加一票否决：降等级、追加声明、**结论压到 L2**。不修改入参。

    旧口径（已核定/待核/已排除）保留到 `conclusion_grade_legacy`，新口径字段统一为 L1~L4。
    """
    out = dict(item or {})
    hits = veto_triggers(out)
    if not hits:
        return out
    on = load_spec().get("veto_rules", {}).get("on_veto") or {}
    cap = str(on.get("max_risk_level") or "待核验")
    lvl, _orig = normalize_level(out.get("risk_level"))
    if risk_levels.severity(lvl) > risk_levels.severity(cap):
        out["risk_level"] = cap
        out["risk_level_veto_from"] = lvl
    old_grade = str(out.get("conclusion_grade") or "").strip()
    if old_grade and not old_grade.startswith("L"):
        out.setdefault("conclusion_grade_legacy", old_grade)
    out["conclusion_grade"] = GRADE_L2          # 一票否决 ⇒ 结论不得高于 L2
    note = str(on.get("append_text") or "")
    if note and note not in str(out.get("verdict") or ""):
        out["verdict"] = f"{out.get('verdict') or ''}{note}"
    out["_veto_applied"] = True
    out["_veto_triggers"] = [h.get("id") for h in hits]
    return out


# ---------------------------------------------------------------- 汇总分析
def analyze_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """对单项做完整结论体检，供门禁 A 使用（只读，不篡改）。"""
    gid, registered = map_verdict((item or {}).get("verdict"))
    lvl, illegal_word = normalize_level((item or {}).get("risk_level"))
    declared_grade = str((item or {}).get("conclusion_grade") or "").strip()
    hits = veto_triggers(item)
    det = contains_determinative(_pred_body_text(item))
    return {
        "seq": (item or {}).get("seq"),
        "title": (item or {}).get("title"),
        "risk_level": (item or {}).get("risk_level"),
        "risk_level_normalized": lvl,
        "illegal_level_word": illegal_word,
        "conclusion_grade_declared": declared_grade,
        "conclusion_grade_mapped": gid,
        "verdict_registered": registered,
        "veto_triggers": hits,
        "veto_applies": bool(hits),
        "determinative_words_hit": det,
        "level_allowed_by_grade": lvl in allowed_levels(declared_grade or gid),
        "closure": (item or {}).get("closure"),
        "evidence_have": (item or {}).get("evidence_have"),
        "evidence_need": (item or {}).get("evidence_need"),
    }
