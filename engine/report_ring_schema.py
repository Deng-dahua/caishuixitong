# -*- coding: utf-8 -*-
"""报告「七环」段落 schema —— 唯一权威（P0-5）
================================================================

## 为什么必须有这个模块

同一份报告里，**红线疑点**与**域分析发现**曾各自拼一套段落结构：
  · 红线分支（`enterprise_report._build_redline_problems`）产出 7 段；
  · 域分析分支（`enterprise_report._promote_standalone_to_problems`）自行拼 7 段，
    但**环名不同、且缺 推导链／要件清单／结论句／后果段**（以统一环名判定）；
  · 专项比对分支又是一套。
⇒ 读者看到的是"同一种事、两种讲法"，且域分析项**缺 conclusion_grade、缺办理顺序**
  （门禁 A4 / B2 实测报错）。

本模块把**环名与顺序**收敛到 `RINGS` 一处：两个分支都调 `build_rings()`，
各自只提供"环的内容素材"；环叫什么、排第几、是不是必填，全部由本表决定。
新增环/改环名 ⇒ **只改本表一行**，不改任何分支逻辑。

## 七环（顺序即呈现顺序）

  ① trigger      为何列入检查                    —— 本项凭什么被列入（触发事实）
  ② risk_item    一、涉及的风险事项              —— 本项是什么、等级、构成概要
  ③ basis        二、发现的依据                  —— 从资料里怎么一步步读出来的（推导链）
  ④ materials    三、已取得的资料与待补充的资料  —— 手上有什么、还缺什么
  ⑤ conclusion   四、本项结论及理由              —— 要件清单逐条核对结果 + 结论句
  ⑥ consequence  若不补充资料的后果              —— 未补资料的法定后果（按税费性质）
  ⑦ request      五、需企业提供的资料与说明      —— 面向企业的补件指引

> 环 ⑥ 与 ⑦ 是两个**职责不同**的环：⑥ 回答"不补会怎样"（法律后果），
> ⑦ 回答"要补什么"（行动清单）。红线分支曾缺 ⑦、域分析分支曾缺 ⑥，
> 现两者都由 schema 补齐（缺则用 `default_ring()` 生成，绝不静默少一环）。
"""

from typing import Any, Dict, List, Optional

VERSION = "1.0.0"

#: 唯一权威：环定义（键／中文标题／是否必填／职责）。顺序即呈现顺序。
RINGS: List[Dict[str, Any]] = [
    {"key": "trigger", "title": "为何列入检查", "required": True,
     "duty": "本项凭什么被列入（触发事实，可自证）"},
    {"key": "risk_item", "title": "一、涉及的风险事项", "required": True,
     "duty": "本项是什么、等级、构成概要"},
    {"key": "basis", "title": "二、发现的依据", "required": True,
     "duty": "从资料里怎么一步步读出来的（推导链）"},
    {"key": "materials", "title": "三、已取得的资料与待补充的资料", "required": True,
     "duty": "手上有什么、还缺什么"},
    {"key": "conclusion", "title": "四、本项结论及理由", "required": True,
     "duty": "要件清单逐条核对结果 + 结论句"},
    {"key": "consequence", "title": "若不补充资料的后果", "required": True,
     "duty": "未补资料的法定后果（按税费性质）"},
    {"key": "request", "title": "五、需企业提供的资料与说明", "required": True,
     "duty": "面向企业的补件指引"},
]

RING_KEYS: List[str] = [r["key"] for r in RINGS]
REQUIRED_KEYS: List[str] = [r["key"] for r in RINGS if r.get("required")]

#: 标题 → 环键 的别名表（历史写法一律收敛；新增写法只加一行）。
#  ★ 归一化先做（去序号前缀/括号/空白/markdown 强调符），再查本表。
HEADING_ALIASES: Dict[str, str] = {
    "为何列入检查": "trigger",
    "事实与发现": "trigger",
    "本项之所以列入检查": "trigger",
    "一、涉及的风险事项": "risk_item",
    "涉及的风险事项": "risk_item",
    "二、发现的依据": "basis",
    "发现的依据": "basis",
    "三、已取得的资料与待补充的资料": "materials",
    "已取得的资料与待补充的资料": "materials",
    "资料与待补充的资料": "materials",
    "四、本项结论及理由": "conclusion",
    "本项结论及理由": "conclusion",
    "若不补充资料的后果": "consequence",
    "若不补证的后果": "consequence",
    "不补充资料的后果": "consequence",
    "五、需企业提供的资料与说明": "request",
    "需企业提供的资料与说明": "request",
    "需企业提供的资料": "request",
}

_ORDINAL_PREFIXES = (
    "一、", "二、", "三、", "四、", "五、", "六、", "七、", "八、", "九、", "十、",
    "一.", "二.", "三.", "四.", "五.", "六.", "七.", "八.", "九.", "十.",
    "（一）", "（二）", "（三）", "（四）", "（五）", "（六）", "（七）",
    "(一)", "(二)", "(三)", "(四)", "(五)", "(六)", "(七)",
)


def normalize_heading(heading: Any) -> str:
    """标题归一化：去 markdown 强调符、去空白、去序号前缀、去首尾括号。

    与 `report_dedup.norm_head` 同口径（那是段级去重的权威，这是环归属的权威），
    差别只在：本函数**不剥离**中文数字本身（"一、" 由 `HEADING_ALIASES` 的键承担）。
    """
    s = str(heading or "").strip().replace("*", "")
    s = "".join(s.split())
    s = s.strip("（）()【】[] ")
    for p in _ORDINAL_PREFIXES:
        if s.startswith(p):
            s = s[len(p):]
            break
    return s.strip("（）()【】[] ")


def ring_key_of(heading: Any) -> Optional[str]:
    """把任一段落标题映射到环键；映射不到返回 None（属"额外环"，如「六、推断与联想」）。"""
    h = normalize_heading(heading)
    if not h:
        return None
    if h in HEADING_ALIASES:
        return HEADING_ALIASES[h]
    # 兜底：去掉序号后仍未命中，再按"包含"匹配（容忍少量措辞差异）
    for alias, key in HEADING_ALIASES.items():
        if alias and alias in h:
            return key
    return None


def title_of(key: str) -> str:
    for r in RINGS:
        if r["key"] == key:
            return str(r["title"])
    return ""


#: 结论等级 → 哪些必填环"本情形不适用"（**唯一权威**，生产分支与闸门共用）。
#  ★ 已定性（已核定 / L3）的事项无需再讲「若不补充资料的后果」—— 已定性即不存在"若不补证"
#    这一悬置情形；继续给该环会与"已核定"自相矛盾。
_SKIP_CONSEQUENCE_GRADES = ("已核定", "L3")


def ctx_for_problem(problem: Any) -> Dict[str, Any]:
    """由**问题本身**推导 `build_rings` 的 ctx（**唯一权威**）。

    为什么必须集中在这里：`skip_required` 是一条**判定规则**（"已定性就不要后果环"）。
    生产分支（`enterprise_report._prepare_problems`）与常驻闸门（环完整性）若各写一套，
    就会出现"生产按规则跳过 ⇒ 闸门仍按七环判缺 ⇒ **假红**"，或反过来漏判。
    新增/修改跳过规则 ⇒ **只改本函数一行**。
    """
    p = problem if isinstance(problem, dict) else {}
    _taxes = [str(x) for x in (p.get("taxes") or []) if str(x).strip()]
    return {
        "need": "",
        "risk_level": p.get("risk_level"),
        "taxes_txt": "、".join(_taxes),
        "skip_required": (["consequence"]
                          if str(p.get("conclusion_grade") or "") in _SKIP_CONSEQUENCE_GRADES
                          else []),
    }


def default_ring(key: str, ctx: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """缺失环的**通用**默认内容（仅用于"该环没被任何分支提供"时的兜底）。

    ⚠ 原则：兜底内容必须**如实、不含未证事实**。取不到素材时返回 None（调用方登记缺口），
    绝不用编造内容顶替（缺失≠编造）。
    """
    ctx = ctx or {}
    if key == "consequence":
        # 与红线分支同源：按本项税费性质给出法定去向；不写具体法条（法条在报告级声明）。
        taxes = ctx.get("taxes_txt") or ""
        lv = str(ctx.get("risk_level") or "")
        tail = ""
        if lv and lv not in ("待核验", "信息"):
            tail = "（按本项等级「%s」）" % lv
        return {
            "heading": title_of("consequence"),
            "text": ("如企业未补充上述资料、也未对相关情况作出合理解释，本项风险方向无法排除，"
                     "可能影响相应期间的申报处理口径%s；具体后果须依据适用期间、完整事实、证据"
                     "和法定程序，由有权人员复核后认定。"
                     % (("（涉及" + taxes + "）") if taxes else tail)),
        }
    if key == "request":
        need = str(ctx.get("need") or "").strip()
        return {
            "heading": title_of("request"),
            "text": ("要把这一项查清楚，需要：" + need) if need
                    else "本项结论可通过现有资料复核；如企业有相反证据，请提供并说明。",
        }
    return None


def build_rings(content: Optional[Dict[str, Any]] = None,
                *,
                ctx: Optional[Dict[str, Any]] = None,
                extras: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """按**统一环序**组装段落列表（唯一构造入口）。

    参数
    ----
    content : {环键: 段落dict}  各分支提供的**环内容素材**（键可以是环键，也可以是旧标题，
              本函数内部归一）。段落 dict 可含 heading/text/bullets/detail_table/detail_tables/tail。
    ctx     : 缺失环的兜底上下文（taxes_txt/risk_level/need/...），交给 `default_ring`。
    extras  : 不属于七环的**额外段**（如「六、推断与联想」），一律**追加在七环之后**保持原有顺序。

    返回：按 `RINGS` 顺序排列的段落列表；必填环**保证出现**（无素材则用 `default_ring`，
    再取不到则**不生成**该环，由调用方/闸门登记为缺口 —— 绝不静默）。
    """
    ctx = ctx or {}
    skip = set(str(x) for x in (ctx.get("skip_required") or []))
    by_key: Dict[str, Dict[str, Any]] = {}
    for k, v in (content or {}).items():
        if not isinstance(v, dict):
            continue
        key = k if k in RING_KEYS else ring_key_of(k)
        if key and key not in by_key:
            by_key[key] = v

    out: List[Dict[str, Any]] = []
    for r in RINGS:
        key = r["key"]
        para = by_key.get(key)
        if para is None and r.get("required") and key not in skip:
            para = default_ring(key, ctx)
        if para is None:
            continue
        item = dict(para)
        # 环名由 schema 统一决定（分支只提供内容，不决定环名）
        item["heading"] = title_of(key)
        item["ring_key"] = key
        out.append(item)

    for ex in (extras or []):
        if isinstance(ex, dict):
            item = dict(ex)
            item.setdefault("ring_key", ring_key_of(item.get("heading")) or "extra")
            out.append(item)
    return out


def missing_required_keys(paragraphs: Any, *, ctx: Optional[Dict[str, Any]] = None) -> List[str]:
    """返回**缺失的必填环键**（供闸门与自检使用）。

    `ctx["skip_required"]` 里的环视为"本情形不适用"，不计入缺失
    （如**已核定**事项不再讲「若不补充资料的后果」——已定性即无需"若不补证"）。
    """
    skip = set(str(x) for x in ((ctx or {}).get("skip_required") or []))
    present = set()
    for p in (paragraphs or []):
        if isinstance(p, dict):
            k = p.get("ring_key") or ring_key_of(p.get("heading"))
            if k:
                present.add(k)
    return [k for k in REQUIRED_KEYS if k not in present and k not in skip]


def normalize_problem_rings(problem: Dict[str, Any],
                            *,
                            ctx: Optional[Dict[str, Any]] = None) -> List[str]:
    """把**单个问题**的 `narrative_paragraphs` 收敛到七环（就地把新列表写回）。

    返回缺失的必填环键（空列表＝七环齐全）。额外环（如「六、推断与联想」）保留在末尾。
    """
    if not isinstance(problem, dict):
        return list(REQUIRED_KEYS)
    paras = problem.get("narrative_paragraphs") or []
    content: Dict[str, Dict[str, Any]] = {}
    extras: List[Dict[str, Any]] = []
    for p in paras:
        if not isinstance(p, dict):
            continue
        key = p.get("ring_key") or ring_key_of(p.get("heading"))
        if key and key in RING_KEYS:
            # 同键多段：合并（保留首段的表结构，正文用换行拼）
            if key in content:
                prev = content[key]
                prev["text"] = (str(prev.get("text") or "") + "\n"
                                + str(p.get("text") or "")).strip()
                for tk in ("bullets", "detail_table", "detail_tables", "tail"):
                    if prev.get(tk) is None and p.get(tk) is not None:
                        prev[tk] = p.get(tk)
            else:
                content[key] = dict(p)
        else:
            extras.append(p)
    merged = build_rings(content, ctx=ctx, extras=extras)
    problem["narrative_paragraphs"] = merged
    return missing_required_keys(merged, ctx=ctx)
