# -*- coding: utf-8 -*-
"""疑点1 剩余缺陷（D5/D6/D7 + D2 读数半）根因收口 —— 全部落在 engine/clue_chain.py。

根因（一处两用）：
  ① **资料有无**与**读数有无**各判一次——
     · 首环判据 `if sources:`（发现有没有声明取数来源），而非资料齐备性唯一权威；
     · 首环/中间环取不到数就回落 `metrics[:3]` / `numbers[:3]` / `_terminal_signal`（全文数字）。
  ② `_materials_in_text` 拿**整片**去比 15 类名，剥不掉「（含红字标识）」这类括号说明
     ⇒ 「销项发票（含红字标识）」永远匹配不上 ⇒ 首环被判"未取得资料"。

修法（单一权威 + 薄转发，均为通用规则、不含任何"红冲"特例）：
  · 新增 `materials_available()`：资料有无的唯一权威（走 `material_names.categories_of` 归一）；
    `_materials_in_text` 降为薄转发。
  · 新增 `_on_topic_reading()`：环节读数的唯一权威 —— 取**要件命中证据**里与本环节
    action/output 对题的 evidence；**不再**回落到全文数字/前 3 指标/终端信号。
  · 未取到对题读数 ⇒ 如实标注（缺资料=material_missing / 有资料但无产出=engine_gap），
    **绝不拿别的环节的数顶替**。
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NL = chr(10)


def swap(path, pairs):
    p = os.path.join(ROOT, path)
    raw = io.open(p, "r", encoding="utf-8", newline="").read()
    crlf = "\r\n" in raw
    s = raw.replace("\r\n", NL)
    for old, new in pairs:
        if s.count(old) != 1:
            print("!! %s: anchor命中 %d次(应为1): %r" % (path, s.count(old), old[:80]))
            sys.exit(2)
        s = s.replace(old, new, 1)
    if crlf:
        s = s.replace(NL, "\r\n")
    io.open(p, "w", encoding="utf-8", newline="").write(s)
    print("OK %s (%d处)" % (path, len(pairs)))


# ── ① 资料有无的唯一权威（并修 _materials_in_text 的整片匹配） ──────────
OLD_MAT = '''def _materials_in_text(source_text: str, provided: Optional[List[str]]) -> bool:
    """判断环节声明的资料中是否有任一类别在本轮已提供清单中。

    source_text 形如 "工资表" 或 "考勤记录、门禁记录、社保、个税、银行流水"；
    provided 为 material_readiness["provided"] 的中文 15 类名单。
    """
    if not provided or not source_text:
        return False
    prov = {str(p).strip() for p in provided if p}
    for piece in re.split(r"[、，,;；]", str(source_text)):
        p = piece.strip()
        if p and p in prov:
            return True
    return False
'''

NEW_MAT = '''def materials_available(source_text: str,
                        provided: Optional[List[str]]) -> Tuple[bool, List[str]]:
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
    if not _prov_raw:
        return False, []
    _prov = set()
    for _p in _prov_raw:
        _prov.add(_p)
        _c = _mn.canonical(_p)
        if _c:
            _prov.add(_c)
    # 候选片段：先按分隔符切，再补上"整段"（覆盖"退货单、折让协议、拒收证明"这类组合名）
    pieces = [x.strip() for x in re.split(r"[、，,;；／/\\n]+", str(source_text)) if x.strip()]
    pieces.append(str(source_text).strip())
    _ok = False
    _missing: List[str] = []
    for piece in pieces:
        cats = _mn.categories_of(piece) or []
        if not cats:
            continue
        if any(c in _prov for c in cats):
            _ok = True
        else:
            if piece not in _missing:
                _missing.append(piece)
    return _ok, _missing


def _materials_in_text(source_text: str, provided: Optional[List[str]]) -> bool:
    """薄转发：环节声明的资料中是否有任一类别本轮已提供（唯一权威见上方函数）。"""
    _ok, _ = materials_available(source_text, provided)
    return _ok
'''

# ── ② 环节读数的唯一权威 + 逐环改判 ────────────────────────────────────
OLD_LOOP_HEAD = '''    def _gap_reason(source_text: str) -> str:
        return "engine_gap" if _materials_in_text(source_text, provided_materials) else "material_missing"
'''

NEW_LOOP_HEAD = '''    def _gap_reason(source_text: str) -> str:
        """本环节无读数时，缺的是"资料"还是"程序"（资料齐备性走唯一权威）。"""
        _ok, _missing = materials_available(source_text, provided_materials)
        return "material_missing" if (_missing and not _ok) else "engine_gap"
'''

OLD_TEMPLATE_BODY = '''    if template:
        # 有红线模板：按模板骨架逐环落地，并把实际观察值填进去
        total = len(template)
        for i, tpl in enumerate(template):
            step_no = i + 1
            observed = ""
            has_data = True
            if step_no == 1:
                # 首环：资料来源与实际读取到的规模
                if sources:
                    observed = "已读取资料：" + "、".join(sources[:6])
                    if len(sources) > 6:
                        observed += f" 等{len(sources)}类"
                else:
                    _r = _gap_reason(tpl.get("source", ""))
                    observed = ("该环节未取得可展示数据；所需资料（"
                                + str(tpl.get("source") or "—") + "）已在本轮提供，"
                                "属检查程序待完善项，不计入资料缺失"
                                if _r == "engine_gap" else "本轮未取得该项资料")
                    has_data = False
            elif step_no == total:
                # 末环：终端信号（触红值）
                terminal = _terminal_signal(detail, numbers, finding)
                observed = terminal or "本轮未取得可量化的终端数据"
                has_data = bool(terminal)
            else:
                # 中间环：优先用指标，其次用叙述中的数字
                mrows = _metric_rows(metrics)
                if mrows:
                    observed = "；".join(f"{k}={v}" for k, v in mrows[:3])
                elif numbers:
                    observed = "计算得到：" + "、".join(numbers[:3])
                else:
                    _r = _gap_reason(tpl.get("source", ""))
                    observed = ("该环节未产出可展示数据；所需资料已在本轮提供，"
                                "属检查程序待完善项，不计入资料缺失"
                                if _r == "engine_gap" else "本轮未取得该环节可量化数据")
                    has_data = False
            nodes.append({
                "step": step_no,
                "source": tpl.get("source", ""),
                "action": tpl.get("action", ""),
                "output": tpl.get("output", ""),
                "observed": observed,
                "trace_ref": f"底稿编号 {finding.get('scene_fact_id') or finding.get('fact_id') or '—'} "
                             f"第{step_no}环",
                "has_data": has_data,
            })
'''

NEW_TEMPLATE_BODY = '''    if template:
        # 有红线模板：按模板骨架逐环落地，并把**对题**的读数填进去
        total = len(template)
        for i, tpl in enumerate(template):
            step_no = i + 1
            observed = _on_topic_reading(tpl, hits, redline.get("constituents"))
            if observed:
                nodes.append({
                    "step": step_no,
                    "source": tpl.get("source", ""),
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
            _ok, _missing = materials_available(tpl.get("source", ""), provided_materials)
            if _reason == "material_missing":
                observed = ("因缺少资料（" + "、".join(_missing[:4]) +
                            "）未取得本环节数据，该部分无法核对")
            else:
                observed = ("本环节未产出对题读数"
                            + ("（所需资料已在本轮提供，属检查程序待完善项）" if _ok
                               else "（所需资料类别无法识别，按检查程序待完善项处理）"))
            nodes.append({
                "step": step_no,
                "source": tpl.get("source", ""),
                "action": tpl.get("action", ""),
                "output": tpl.get("output", ""),
                "observed": observed,
                "trace_ref": f"底稿编号 {finding.get('scene_fact_id') or finding.get('fact_id') or '—'} "
                             f"第{step_no}环",
                "has_data": False,
                "_gap_reason": _reason,
            })
'''

OLD_ELSE_BODY = '''    else:
        # 无模板：退化为「资料 → 计算 → 结果」三环，仍要求每环有数字
        nodes = [
            {"step": 1, "source": "、".join(sources) or "本轮已上传并成功读取的资料",
             "action": "读取并归集与本项相关的记录",
             "output": "可复核的数据集",
             "observed": f"已读取{len(sources)}类资料" if sources else "本轮未取得该项资料",
             "trace_ref": f"底稿编号 {finding.get('scene_fact_id') or '—'} 第1环",
             "has_data": bool(sources)},
            {"step": 2, "source": detail[:60] or "—",
             "action": how or "按同一口径重新计算并比对",
             "output": "差异或异常指标",
             "observed": ("；".join(f"{k}={v}" for k, v in _metric_rows(metrics)[:3])
                          or ("计算得到：" + "、".join(numbers[:3]) if numbers else "本轮未取得可量化数据")),
             "trace_ref": f"底稿编号 {finding.get('scene_fact_id') or '—'} 第2环",
             "has_data": bool(metrics or numbers)},
            {"step": 3, "source": "上述比对结果",
             "action": "判断是否触碰红线构成要件",
             "output": redline.get("name", ""),
             "observed": _terminal_signal(detail, numbers, finding) or "本轮未取得终端数据",
             "trace_ref": f"底稿编号 {finding.get('scene_fact_id') or '—'} 第3环",
             "has_data": bool(_terminal_signal(detail, numbers, finding))},
        ]
'''

NEW_ELSE_BODY = '''    else:
        # 无模板：退化为「资料 → 计算 → 结果」三环；读数同样只取**对题**来源
        _no_tpl = [
            {"step": 1, "source": "、".join(sources) or "",
             "action": "读取并归集与本项相关的记录", "output": "可复核的数据集"},
            {"step": 2, "source": detail[:60] or "",
             "action": how or "按同一口径重新计算并比对", "output": "差异或异常指标"},
            {"step": 3, "source": "上述比对结果",
             "action": "判断是否触碰红线构成要件", "output": redline.get("name", "")},
        ]
        nodes = []
        for tpl in _no_tpl:
            step_no = tpl["step"]
            observed = _on_topic_reading(tpl, hits, redline.get("constituents"))
            if not observed:
                _reason = _gap_reason(tpl.get("source", ""))
                _ok, _missing = materials_available(tpl.get("source", ""), provided_materials)
                if _reason == "material_missing":
                    observed = ("因缺少资料（" + "、".join(_missing[:4]) +
                                "）未取得本环节数据，该部分无法核对")
                else:
                    observed = "本环节未产出对题读数（属检查程序待完善项）"
                nodes.append({
                    "step": step_no, "source": tpl.get("source", ""),
                    "action": tpl.get("action", ""), "output": tpl.get("output", ""),
                    "observed": observed,
                    "trace_ref": f"底稿编号 {finding.get('scene_fact_id') or '—'} 第{step_no}环",
                    "has_data": False, "_gap_reason": _reason,
                })
            else:
                nodes.append({
                    "step": step_no, "source": tpl.get("source", ""),
                    "action": tpl.get("action", ""), "output": tpl.get("output", ""),
                    "observed": observed,
                    "trace_ref": f"底稿编号 {finding.get('scene_fact_id') or '—'} 第{step_no}环",
                    "has_data": True,
                })
'''

OLD_GAPS = '''    data_gaps = []
    for n in nodes:
        if n.get("has_data"):
            continue
        data_gaps.append({
            "step": n["step"], "gap": n["source"] or n["output"],
            "reason": _gap_reason(n.get("source", "")),
        })
'''

NEW_GAPS = '''    data_gaps = []
    for n in nodes:
        if n.get("has_data"):
            continue
        data_gaps.append({
            "step": n["step"], "gap": n["source"] or n["output"],
            # 复用逐环已判定的原因，避免"同一件事判两次"
            "reason": n.pop("_gap_reason", None) or _gap_reason(n.get("source", "")),
        })
'''

# ── ③ 新增对题读数唯一权威 + 词元/2gram 工具（插在 build_clue_chain 之前） ──
ANCHOR_BUILD = '''def build_clue_chain(finding: Dict, redline: Dict, engine_data: Optional[Dict] = None,
                     provided_materials: Optional[List[str]] = None) -> Dict:'''

NEW_HELPERS = '''# ★★ 2026-10-04（疑点1 四维自检 D6/D7）：**环节读数的唯一权威**。
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
    s = re.sub(r"[^\\u4e00-\\u9fffA-Za-z0-9]", "", str(text or ""))
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


''' + ANCHOR_BUILD

OLD_METRICS = '''    metrics = finding.get("observed_metrics")
    sources = _sources_of(finding)'''
NEW_METRICS = '''    metrics = finding.get("observed_metrics")
    # ★ 2026-10-04：要件命中证据 = 各环节读数的**唯一来源**（见 `_on_topic_reading`）
    hits = finding.get("constituent_hits") or []
    sources = _sources_of(finding)'''

swap("engine/clue_chain.py", [
    (OLD_MAT, NEW_MAT),
    (ANCHOR_BUILD, NEW_HELPERS),
    (OLD_METRICS, NEW_METRICS),
    (OLD_LOOP_HEAD, NEW_LOOP_HEAD),
    (OLD_TEMPLATE_BODY, NEW_TEMPLATE_BODY),
    (OLD_ELSE_BODY, NEW_ELSE_BODY),
    (OLD_GAPS, NEW_GAPS),
])
print("[DONE] clue_chain 环节资料/读数唯一权威已落地")
