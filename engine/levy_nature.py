# -*- coding: utf-8 -*-
"""**税费性质**与各自法律依据的唯一权威（2026-10-06）。

## 为什么必须有它（用户评语 #4「税费法律适用混同」）
用户原话：
> 「报告将住房公积金、社会保险费、文化事业建设费**与税种并列**，并多处在『若不补充资料
>   后果』中引用《税收征收管理法》**第六十三条偷税**条款。这里需要区分：
>   · 住房公积金**不是税**，主要依据《住房公积金管理条例》，**处罚主体通常是住房公积金
>     管理中心**，不宜直接套用税收征管法偷税条款；
>   · 社保费**不是税**，虽然由税务机关征收，但**法律依据和处罚规则与税收不同**；
>   · 文化事业建设费是**政府性基金**，虽有税务代征，但不宜简单等同于『税』；
>   · 印花税、企业所得税、增值税、个人所得税可以适用税收征管法，但仍需区分偷税、
>     少缴、未申报等不同性质。
>   这类混同会削弱报告的专业性和合法性。」

实测病根：`enterprise_report` 的「若不补证的后果」段**对所有事项一律**写
"主管税务机关可依《税收征收管理法》第三十二条加收滞纳金，并依第六十三条追缴税款、
处不缴或少缴税款百分之五十以上五倍以下罚款"—— 对公积金/社保/文建费项**适用错误的法律**。

## 设计（数据驱动：新增一种费/基金只加一行）
`LEVIES`：性质键 → {名称, 类别(税/费/基金), 征收依据, 不缴后果, 追责主体, 能否引偷税条款}
```
from engine.levy_nature import nature_of, natures_of, consequence_text
nat  = nature_of(problem)     # → 主性质键（涉税则优先"税"）
nats = natures_of(problem)    # → **全部**性质键，如 ["税","社会保险费"]（混性质项）
consequence_text(nats)        # → 按性质分段的"若不补证后果"（各段含各自法律依据）
item_consequence_text(nats)   # → **逐项**用：本项情形 + 引用（法条上提报告级一次）
consequence_declarations(全部)  # → **报告级**声明列表（每种性质一条，法条只出现一次）
```

### 为什么要"多性质"（2026-10-06 追加，避免过度纠正）
实测 `RL-PAY-001`「工资表人数与社保参保人数不符」的 `taxes` 同时含
`个人所得税/企业所得税/社会保险费` —— 它**既有**虚列工资成本少缴企业所得税（适用
征管法偷税条款）**也有**未依法参保（依《社会保险法》）。若只判单一性质，
无论选哪一边都会丢掉另一半的法律依据。故：
- `natures_of` 返回**全部**命中性质（"+税"由 `_TAX_NAME_KW` 正向识别，不靠"未命中即税"）；
- `consequence_text` 对多性质**逐段标注**（"就税款部分：…；就社会保险费部分：…"），
  各段自带依据与追责主体，读者不会把两者混为一谈。
新增一种税/费/基金 ⇒ 只在 `LEVIES` 加一行、在 `_TAX_NAME_KW`/`_NATURE_KW` 加词，不改逻辑分支。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

#: 性质键 → 定义。`can_cite_tax_collection_law`＝能否引用《税收征收管理法》偷税条款。
LEVIES: Dict[str, Dict[str, Any]] = {
    "税": {
        "label": "税款",
        "category": "税",
        "basis": "《税收征收管理法》及其实施细则、各税种单行法",
        "consequence": ("主管税务机关可依《税收征收管理法》第三十二条加收滞纳金；"
                        "构成偷税、抗税、骗税的，依第六十三条等规定追缴税款、滞纳金并处罚款。"
                        "**是否构成偷税、以及是否移送，须由税务机关依法调查认定**"),
        "authority": "税务机关",
        "can_cite_tax_collection_law": True,
    },
    "社会保险费": {
        "label": "社会保险费",
        "category": "费（社保费）",
        "basis": "《中华人民共和国社会保险法》（第五十八条参保义务、第八十四条、第八十六条）",
        # ★ 社保费由税务机关征收，但**追缴与处罚规则依社会保险法**，不套用偷税条款。
        "consequence": ("由税务机关依《社会保险法》第八十六条责令限期缴纳或补足，"
                        "并自欠缴之日起按日加收万分之五滞纳金；逾期仍不缴纳的，"
                        "可处欠缴数额一倍以上三倍以下罚款。"
                        "**社保费不是税，不适用《税收征收管理法》偷税条款**"),
        "authority": "税务机关（依《社会保险法》）／社会保险经办机构",
        "can_cite_tax_collection_law": False,
    },
    "住房公积金": {
        "label": "住房公积金",
        "category": "住房公积金属职工个人所有（住房公积金制度）",
        "basis": "《住房公积金管理条例》（第十五条登记、第十六条缴存额、第二十条缴存、第三十七/三十八条）",
        "consequence": ("由住房公积金管理中心责令限期办理缴存登记／限期缴存；"
                        "逾期不缴或少缴的，可申请人民法院强制执行。"
                        "**公积金不是税，追责主体是住房公积金管理中心，"
                        "不适用《税收征收管理法》偷税条款**"
                        "（但少缴公积金会影响工资薪金的个税前扣除凭证与社保基数一致性）。"),
        "authority": "住房公积金管理中心",
        "can_cite_tax_collection_law": False,
    },
    "政府性基金": {
        "label": "文化事业建设费（政府性基金）",
        "category": "政府性基金（非税收入，由税务代征）",
        "basis": "《文化事业建设费征收管理暂行办法》等非税收入征收管理规定",
        "consequence": ("按规定补缴并加收滞纳金；**文化事业建设费是政府性基金，"
                        "不是税**，不适用《税收征收管理法》偷税条款"),
        "authority": "税务机关（代征）／财政部门",
        "can_cite_tax_collection_law": False,
    },
}

#: 判据关键词（按**税费名称**识别；只看主题字段，避免正文串味）
#  ★ 声明顺序 = 命中多种非税时的**主次顺序**，与 `LEVIES` 次序保持一致（社保费→公积金→基金）。
_NATURE_KW: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("社会保险费", ("社会保险", "社保", "参保", "养老保险", "医疗保险", "失业保险",
                    "工伤保险", "生育保险")),
    ("住房公积金", ("公积金", "住房公积金")),
    ("政府性基金", ("文化事业建设费", "政府性基金", "非税收入")),
)

#: 我国**税收**名称全表（18 个税种）—— 用于"正向识别涉税"，而不是"未命中非税即税"。
#  数据表：新增税种只加一行，不改逻辑分支。
_TAX_NAME_KW: Tuple[str, ...] = (
    "增值税", "消费税", "企业所得税", "个人所得税", "城市维护建设税", "烟叶税",
    "资源税", "房产税", "印花税", "城镇土地使用税", "土地增值税", "车船税",
    "船舶吨税", "车辆购置税", "关税", "耕地占用税", "契税", "环境保护税",
)

#: 主题字段（只看这些，不扫正文 —— 正文里提到税种名会造成串味）
_SUBJECT_KEYS: Tuple[str, ...] = (
    "title", "redline_id", "redline_name", "finding_type", "taxes", "category",
)


def _subject_text(obj: Any) -> str:
    """取本项的**主题文本**（用于性质判定）；dict 只取 `_SUBJECT_KEYS`。"""
    if isinstance(obj, dict):
        return " ".join(str(obj.get(k) or "") for k in _SUBJECT_KEYS)
    return str(obj or "")


def natures_of(obj: Any) -> List[str]:
    """判定本项涉及的**全部**性质键（有序、去重）；一个都判不出 ⇒ `["税"]`。

    规则（与 `nature_of` 同源，唯一权威）：
      · 命中任一非税性质关键词 ⇒ 计入该性质；
      · 主题文本命中任一税种名 ⇒ 计入「税」；
      · 两者都没有 ⇒ 按"纯税款事项"处理（`["税"]`），不臆造费/基金。
    顺序：涉税在前（读者先看税款后果），非税按 `_NATURE_KW` 声明顺序。
    """
    _t = _subject_text(obj)
    _fees = [nat for nat, kws in _NATURE_KW if any(k in _t for k in kws)]
    _has_tax = any(k in _t for k in _TAX_NAME_KW)
    out: List[str] = []
    if _has_tax or not _fees:
        out.append("税")
    for _n in _fees:
        if _n not in out:
            out.append(_n)
    return out


def nature_of(obj: Any) -> str:
    """判定本项**主性质**键（= `natures_of` 的首项）；取不到 ⇒ "税"（不臆造费/基金）。

    注：混性质项（如"个税/企业所得税 + 社保费"）返回 `"税"`，
    完整性质集合请用 `natures_of(obj)`。
    """
    return natures_of(obj)[0]


def levy(nature: str) -> Dict[str, Any]:
    return LEVIES.get(nature) or LEVIES["税"]


def _norm_natures(nature: Any) -> List[str]:
    """把入参归一为性质键列表（接受 str / 可迭代）。"""
    if isinstance(nature, str):
        _lst = [nature] if nature.strip() else []
    else:
        try:
            _lst = [str(x) for x in (nature or []) if str(x or "").strip()]
        except TypeError:
            _lst = []
    _seen, _out = set(), []
    for _n in _lst:
        if _n not in _seen:
            _seen.add(_n)
            _out.append(_n)
    return _out or ["税"]


#: 免责声明（唯一字面量）——「若不补证的后果」的两种形态（逐项/整段）共用。
DISCLAIMER = "本报告不作定性，在补证核实之前既不认定违法，也不予排除。"

#: 性质的**规范顺序**（= `LEVIES` 声明次序）：涉税在前，非税按社保费→公积金→基金。
#  排序不写死在调用方（新增一种费/基金只加一行 `LEVIES`，本表自动跟随）。
NATURE_ORDER: Tuple[str, ...] = tuple(LEVIES.keys())


def canonical_natures(natures: Any) -> List[str]:
    """把性质集合**去重 + 按 `NATURE_ORDER` 规范化排序**（顺序的唯一权威）。"""
    _seen = set()
    for _n in _norm_natures(natures):
        _seen.add(_n)
    _idx = {n: i for i, n in enumerate(NATURE_ORDER)}
    return sorted(_seen, key=lambda n: _idx.get(n, len(_idx)))


def consequence_text(nature: Any, suspect: str = "", taxes_txt: str = "",
                     grade_txt: str = "尚待补证与核实") -> str:
    """按**性质**生成「若不补证的后果」段（含正确法律依据与追责主体）。

    `nature` 可为单个性质键（str）或性质键列表 —— 混性质项会**逐段标注**：
      "…本项存在被认定为「X」的风险（涉及Y）。就税款部分：…；
       就社会保险费部分：…。本报告不作定性，…"

    ★ 本函数是**整段（法条全量）**形态：报告级声明与闸门行为断言用它的产出。
      逐项位置请用 `item_consequence_text()`（只留本项情形 + 引用），理由见该函数。
    """
    _nats = _norm_natures(nature)
    _sus = ("按目前的分析结论（%s）：若企业未能补充上述资料、也未对差额或异常作出合理解释，"
            "本项存在被认定为「%s」的风险%s。"
            % (grade_txt, suspect or "账簿少列收入、少缴应纳税款",
               ("（涉及%s）" % taxes_txt) if taxes_txt else ""))
    _multi = len(_nats) > 1
    _parts = []
    for _n in _nats:
        _l = levy(_n)
        _c = str(_l.get("consequence") or "").rstrip("。；; \t")
        _parts.append(("就%s部分：%s" % (_l.get("label") or _n, _c)) if _multi else _c)
    _tail = ("%s。%s" % ("；".join(_parts), DISCLAIMER))
    return _sus + _tail


# ═══════════════════════════════════════════════════════════════════════════════
# ★★ 2026-10-08（P0-2 去重收口）：**共性法条按性质上提报告级一次 + 逐项引用**
# ═══════════════════════════════════════════════════════════════════════════════
# 病根（实测，只读脚本 `scripts/_eval_dup_pipeline.py`）：同一性质的法条文本在 N 个事项里
#   **逐字相同**（税 13 项、社保费/公积金/基金各若干），逐项铺开 ⇒
#   整体重复率 11.11%（>10% 阈值）⇒ `dedup_pipeline.duplicate_rate` 判「阻断」⇒ 报告不得输出。
#   而**法条不得因去重被删**（合规底线，且删了就是法律适用错误）。
#
# 为什么不能靠现有上提机制解决：这些法条句属 `report_dedup._is_nature_specific`
#   （故意阻止跨性质上提，防税款条款被套到非税事项上）⇒ 句级上提**永远打不中**，
#   只能原地重复。
#
# 解法（数据驱动，新增一种税费只加一行 `LEVIES`）：
#   · **报告级**：每种性质声明一次「法定后果 + 追责主体」（`consequence_declarations`）；
#   · **逐项**：只留本项自己的涉嫌情形 + **指向该声明的引用**（`item_consequence_text`）；
#   · 性质**逐段分开**声明（绝不合并成一段）⇒ 读者按本项涉及的性质即可查到对应后果，
#     既解决冗余，又不发生"把征管法偷税条款套到公积金上"的混同。
CONSEQUENCE_DECL_NAME = "税费性质与法定后果"


def _clean_decl_text(text: Any) -> str:
    """声明的可读文本（去 markdown 强调符 —— 与报告终局清洗 `strip_markup` 同口径）。"""
    return str(text or "").replace("**", "").strip()


def consequence_decl_ref() -> str:
    """逐项后果段指向报告级声明的**引用语**（唯一生成点，薄转发 `engine.reference.prose_ref`）。

    ⚠ 引用语形态的唯一权威在 `engine.reference` —— 此处只取名字，不自拼括号。
    """
    try:
        from engine.reference import prose_ref
        return prose_ref(CONSEQUENCE_DECL_NAME)
    except Exception:  # noqa: BLE001 —— 取不到权威时用同形态兜底（不裸奔、不静默）
        return "（见%s）" % CONSEQUENCE_DECL_NAME


def consequence_declaration(nature: str) -> str:
    """**报告级**声明的一条（一种性质一条）：法定后果 + 追责主体，全文只出现一次。"""
    _l = levy(nature)
    return "%s（%s）：%s" % (CONSEQUENCE_DECL_NAME, _l.get("label") or nature,
                            _clean_decl_text(_l.get("consequence")))


def consequence_declarations(natures: Any) -> List[str]:
    """报告级声明**列表**（只为**本报告实际涉及**的性质声明；顺序走 `canonical_natures`）。

    :param natures: 本报告涉及的性质集合（可为任一可迭代对象）；空 ⇒ 返回 `[]`（不臆造）。
    """
    _lst = [str(x) for x in (_norm_raw(natures))]
    if not _lst:
        return []
    out: List[str] = []
    for _n in canonical_natures(_lst):
        _t = consequence_declaration(_n)
        if _t and _t not in out:
            out.append(_t)
    return out


def _norm_raw(natures: Any) -> List[str]:
    """把入参归一为性质键列表；**空就是空**（不套用 `_norm_natures` 的「取不到⇒税」）。"""
    if isinstance(natures, str):
        _lst = [natures.strip()] if natures.strip() else []
    else:
        try:
            _lst = [str(x).strip() for x in (natures or []) if str(x or "").strip()]
        except TypeError:
            _lst = []
    _seen, _out = set(), []
    for _n in _lst:
        if _n not in _seen:
            _seen.add(_n)
            _out.append(_n)
    return _out


def item_consequence_text(nature: Any, suspect: str = "", taxes_txt: str = "",
                          grade_txt: str = "尚待补证与核实") -> str:
    """**逐项**「若不补证的后果」段：本项自己的情形（专属）+ 指向报告级声明的引用。

    与 `consequence_text` 的关系（同一权威的两半，缺一不可）：
      · 本函数 = 逐项版：`<本项情形>` + 「本项涉及<性质>，其法定后果与追责主体（见…）。」
                    + `DISCLAIMER`；
      · `consequence_text` = 报告级/整段版：逐段给出**法条原文**（供 `consequence_declarations`
        与闸门行为断言使用）。
    ⇒ 同一法条文本在报告里**只出现一次**（报告级），逐项只留情形与引用 ——
      企业可在报告级声明中逐字对照，信息不丢（引用可回溯）。
    ⚠ 引用语形态的唯一权威是 `engine.reference.prose_ref`（已含"见"字），
      本函数**不得**再自行加"见"（曾拼成"见（见X）"病句）。
    """
    _nats = canonical_natures(nature)
    _labels = "、".join(str(levy(_n).get("label") or _n) for _n in _nats)
    _sus = ("按目前的分析结论（%s）：若企业未能补充上述资料、也未对差额或异常作出合理解释，"
            "本项存在被认定为「%s」的风险%s。"
            % (grade_txt, suspect or "账簿少列收入、少缴应纳税款",
               ("（涉及%s）" % taxes_txt) if taxes_txt else ""))
    # ★★ 2026-10-08（P0-2 去重收口·病句修复）：**引用语本身已带「见」**。
    #   `consequence_decl_ref()` 的唯一权威是 `engine.reference.prose_ref`，其形态固定为
    #   「（见X）」；而本行旧稿又在其前加了一个"见"字 ⇒ 实跑产物写成
    #     「其法定后果与追责主体见（见税费性质与法定后果）」—— 同一个"见"重复两遍的病句。
    #   根因：**引用语的形态变化（带不带"见"）没有被生成侧当契约**，靠调用方"猜着拼"。
    #   修法（不再猜）：整句只由引用语承担"见"，即「……追责主体{引用语}」；取不到引用语时
    #     整句仍然成立（只留本项涉及的性质名，不拼半个引用、不裸奔）。
    _ref = consequence_decl_ref()
    if _ref:
        _link = "本项涉及%s，其法定后果与追责主体%s。" % (_labels, _ref)
    else:
        _link = "本项涉及%s。" % _labels
    return _sus + _link + DISCLAIMER
