# -*- coding: utf-8 -*-
"""线索链环节的"缺资料"必须过**业态剔除**（唯一权威 `industry_resolver.not_required_materials`）。

实证：`tools/audit_consistency.py::check_waiting_materials_respect_industry` 报
  `confirmed_problems[seq=13]: 待补资料清单出现本业态（广告传媒）不适用资料「物流单据」`
——来源不是我改的 `document_requests`（两次基线逐字节一致），而是我新写的**环节缺料文案**
被渲染进 `narrative_paragraphs`：「因缺少资料（物流单据与承运记录）未取得本环节数据」。
对服务型企业，物流单据**本就不适用**，说它"缺失导致无法核对"是错的 ⇒ 闸门抓得对。

修法（沿用疑点2 那批的同一口径）：
  · `build_clue_chain` 增参 `not_required_materials`；
  · `materials_available` 把**本业态不适用**的资料从"缺失"里剔除；
  · 若某环节的缺口**全是**不适用资料 ⇒ 文案写"属本业态不适用，不计入资料缺失"；
  · `redline_engine` 调用点从唯一权威取不适用清单并传入。
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


# ── ① materials_available：不适用资料不计入缺失 ─────────────────────────
OLD_SIG = '''def materials_available(source_text: str,
                        provided: Optional[List[str]]) -> Tuple[bool, List[str]]:'''
NEW_SIG = '''def materials_available(source_text: str,
                        provided: Optional[List[str]],
                        not_required: Optional[List[str]] = None) -> Tuple[bool, List[str]]:'''
swap("engine/clue_chain.py", [(OLD_SIG, NEW_SIG)])

OLD_LOOP = '''    _ok = False
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
    return _ok, _missing'''
NEW_LOOP = '''    # ★★ 2026-10-04（疑点1 D5 收口的连带）：**本业态不适用**的资料不计入"缺失"。
    #   唯一权威 `industry_resolver.not_required_materials()`（与疑点2 那批同一口径）。
    #   事故：新写的环节缺料文案「因缺少资料（物流单据与承运记录）未取得本环节数据」
    #   被渲染进报告段落，对服务型企业把**天然没有**的资料说成"缺失导致无法核对"
    #   ⇒ 闸门 `check_waiting_materials_respect_industry` 判 ERROR（闸门是对的）。
    _nr = [str(x).strip() for x in (not_required or []) if str(x).strip()]
    _ok = False
    _missing: List[str] = []
    for piece in pieces:
        cats = _mn.categories_of(piece) or []
        if not cats:
            continue
        if any(c in _prov for c in cats):
            _ok = True
        else:
            # 该资料属本业态不适用 ⇒ 不列为缺失（企业天然不会有）
            if _nr and any((_n == piece) or (_n in piece) or (piece in _n) for _n in _nr):
                continue
            if piece not in _missing:
                _missing.append(piece)
    return _ok, _missing'''
swap("engine/clue_chain.py", [(OLD_LOOP, NEW_LOOP)])

# ── ② build_clue_chain 增参 + 逐环传参 ──────────────────────────────────
OLD_B = '''def build_clue_chain(finding: Dict, redline: Dict, engine_data: Optional[Dict] = None,
                     provided_materials: Optional[List[str]] = None) -> Dict:'''
NEW_B = '''def build_clue_chain(finding: Dict, redline: Dict, engine_data: Optional[Dict] = None,
                     provided_materials: Optional[List[str]] = None,
                     not_required_materials: Optional[List[str]] = None) -> Dict:'''
swap("engine/clue_chain.py", [(OLD_B, NEW_B)])

# 逐环：把 not_required 透传，并在文案里如实说明"本业态不适用"
OLD_GAP = '''            _reason = _gap_reason(tpl.get("source", ""))
            _ok, _missing = materials_available(tpl.get("source", ""), provided_materials)
            if _reason == "material_missing":
                observed = ("因缺少资料（" + "、".join(_missing[:4]) +
                            "）未取得本环节数据，该部分无法核对")
            else:
                observed = ("本环节未产出对题读数"
                            + ("（所需资料已在本轮提供，属检查程序待完善项）" if _ok
                               else "（所需资料类别无法识别，按检查程序待完善项处理）"))'''
NEW_GAP = '''            _reason = _gap_reason(tpl.get("source", ""))
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
                observed = ("本环节未产出对题读数"
                            + ("（所需资料已在本轮提供，属检查程序待完善项）" if _ok
                               else "（所需资料类别无法识别，按检查程序待完善项处理）"))'''
swap("engine/clue_chain.py", [(OLD_GAP, NEW_GAP)])

OLD_ELSE_GAP = '''            if not observed:
                _reason = _gap_reason(tpl.get("source", ""))
                _ok, _missing = materials_available(tpl.get("source", ""), provided_materials)
                if _reason == "material_missing":'''
NEW_ELSE_GAP = '''            if not observed:
                _reason = _gap_reason(tpl.get("source", ""))
                _ok, _missing = materials_available(tpl.get("source", ""), provided_materials,
                                                    not_required_materials)
                if _reason == "material_missing":'''
swap("engine/clue_chain.py", [(OLD_ELSE_GAP, NEW_ELSE_GAP)])

# ── ③ redline_engine 调用点：从唯一权威取不适用清单并传入 ────────────────
OLD_CALL = '''        clue = build_clue_chain(f, rl, engine_data, provided_materials=_mats_all)'''
NEW_CALL = '''        # ★ 2026-10-04：环节"缺资料"必须过**业态剔除**（唯一权威 industry_resolver）
        try:
            from engine.industry_resolver import not_required_materials as _nrm
            _nr_docs = _nrm(str((engine_data or {}).get("industry") or ""))[0]
        except Exception:  # noqa: BLE001
            _nr_docs = set()
        clue = build_clue_chain(f, rl, engine_data, provided_materials=_mats_all,
                                not_required_materials=_nr_docs)'''
swap("engine/redline_engine.py", [(OLD_CALL, NEW_CALL)])
