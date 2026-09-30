# -*- coding: utf-8 -*-
"""
红线判定引擎 —— 风险检查方法论的编排核心
==================================================

方法论主线（2026-09-06 确立，替代原「按行业套场景」的做法）
----------------------------------------------------------
    原始资料
      ↓ 原子观察（已有能力）
    税务红线判定 ← 行业无关：符合构成要件即触红，红线不因行业而变
      ↓
    ┌─────────────┬──────────────┬───────────────┐
   线索链        证据链          论证链
   （怎么发现的）（要什么证据）  （主张/反证/裁决）
    └─────────────┴──────────────┴───────────────┘
      ↓
    税务疑点（按红线归并输出，不再按「待核事实：XXX核验」罗列）

为什么按红线归而不是按发现罗列
--------------------------------------------------
同一条红线可能被多条发现命中（如「供应商地域分散」与「供应商集中度」
同属 RL-PTY-002）。按发现罗列会让报告变成碎片清单；按红线归并后，
一个疑点 = 一条红线 + 多条支撑线索 + 一条证据链 + 一次论证裁决。
"""

from typing import Any, Dict, List, Optional, Tuple

from engine.tax_redlines import (
    match_redlines, match_redline_grounded, get_redline, stats as redline_stats,
)
from engine.clue_chain import build_clue_chain
from engine.evidence_chain import build_evidence_chain
from engine.argumentation import (
    build_argumentation, _VERDICT_CONFIRMED, _VERDICT_HIT_PENDING,
    _VERDICT_EXCLUDED, _VERDICT_WEAK,
)
from engine.redline_benchmark import (
    benchmark_note,
    benchmark_refs,
    compare_redline_benchmark,
)
# 本企业实际指标的**唯一测算来源**（B1 接线：红线判定要用到实际值，禁止另起炉灶重算）
from engine.industry_benchmark import compute_indicators as _ib_compute_indicators

# 裁决优先级：成立可定性 > 成立待补证 > 线索不足 > 排除
_VERDICT_RANK = {
    _VERDICT_CONFIRMED: 4, _VERDICT_HIT_PENDING: 3,
    _VERDICT_WEAK: 2, _VERDICT_EXCLUDED: 1,
}

ENGINE_VERSION = "1.0.0"


def _available_materials(engine_data: Optional[Dict],
                         material_readiness: Optional[Dict],
                         finding: Dict) -> List[str]:
    """汇总本轮已提供的资料类别"""
    mats: List[str] = []
    if isinstance(material_readiness, dict):
        for m in (material_readiness.get("provided") or []):
            if m and m not in mats:
                mats.append(str(m))
    if not mats and isinstance(engine_data, dict):
        for f in (engine_data.get("file_results") or []):
            if isinstance(f, dict):
                t = str(f.get("type") or f.get("doc_type") or "")
                if t and t not in mats:
                    mats.append(t)
    # 注意：不得把发现自身声明的独立来源当作「已提供资料」。
    # 独立来源是数据域名称（如「发票申报」「商品库存」），不是资料类别，
    # 混入后会把缺失的证据误判为已有，导致证据链闭合度虚高、错误定性。
    return mats


def _map_finding(finding: Dict, available_materials: Optional[List[str]] = None
                 ) -> Tuple[Optional[Dict], Dict]:
    """为单条发现匹配红线 → `(红线或 None, 配对说明)`。

    ★ 2026-09-25 根因修复：旧版是
        `cands = match_redlines(text, domain=..., limit=3); return cands[0] if cands else None`
      —— **只要得分为正就取第一名**。后果：一条"增值税申报进项税额与进项发票税额月度差异"
      因为文本含"增值税"、而「固定资产取得、投用与折旧不匹配」红线的 taxes 里也有"增值税"
      （得 1 分）→ 被采纳 → 报告随即用**固定资产折旧的构成要件**论证一个增值税差异，
      并写出"这些事实是从固定资产明细账、试生产记录、折旧计算表…核对出来的"。
      实测 13 条发现里 7 条配错红线。

    现分两条路径：
      ① 发现**显式声明** `redline_id`（扫描器前置认领）→ 直接采用，`mode="declared"`；
      ② 否则走 `match_redline_grounded()` —— 要求信号足够具体**且**该红线所需资料本轮有提供；
         不满足则返回 `(None, mode="unmatched")`，由调用方列为"未归入已知风险情形"，
         **绝不改挂次优红线**（宁可不归类，也不可套错构成要件）。
    """
    rid = finding.get("redline_id")
    if rid:
        rl = get_redline(rid)
        if rl:
            mats = [m for m in (rl.get("required_materials") or [])
                    if m in (available_materials or [])]
            return rl, {
                "mode": "declared",
                "score": None,
                "reasons": ["declared_by_scanner"],
                "materials": mats,
                "note": "发现自身声明了所属红线（扫描器前置认领）",
            }
    title = str(finding.get("type") or "")
    text = " ".join(str(finding.get(k) or "") for k in
                    ("type", "domain", "detail", "description", "target_fact"))
    return match_redline_grounded(title, text, available_materials,
                                  domain=finding.get("domain"))


# ★ 2026-09-28 逐条判定中枢兜底：未显式附 constituent_hits 的红线，按"检测信号→要件"映射补齐，
#   证据取自发现自身的 detail/how_found（即账内实际命中的事实），保证报告 (A)+(B) 闭环。
#   仅对"明确建立"的构成要件序号兜底；显式注入的 constituent_hits（16+ 条红线各检测器）优先，不被覆盖。
#   索引严格对应 engine/tax_redlines.REDLINES 中各红线的 constituents 顺序。
_DEFAULT_HIT_INDEX = {
    # —— 原兜底（外部核验待办 + 关键字匹配型红线），序号对应 constituents 顺序 ——
    "RL-PTY-002": [2, 5],
    "RL-FUND-001": [1, 4],
    "RL-CIT-001": [1, 4],
    "RL-PTY-004": [1, 2, 4],
    "RL-SPT-008": [1, 5],
    "RL-SPT-011": [1, 4],
    "RL-PAY-005": [2, 3, 4],
    "RL-PTY-003": [1, 3, 4],
    "RL-INC-002": [1, 3, 4],
    "RL-AST-003": [1, 2, 4],
    "RL-PAY-002": [1, 2, 4],
    "RL-PAY-003": [1, 4],
    "RL-AST-001": [1, 2, 3, 4],
    "RL-FUND-002": [1, 2, 3, 4],
    "RL-OTH-003": [1, 2, 3],
    "RL-VAT-002": [1, 2, 3, 4, 5],
    "RL-VAT-006": [1, 2, 3, 4],
    "RL-COST-003": [1, 2, 3],
    # —— 本轮新增场景追加（逐条判定兜底，序号按 constituents 顺序计算）——
    # ★ 2026-09-29 A 类新增 6 条：均指向客观构成要件（非末项出罪要件）。
    "RL-CIT-008": [1, 2, 3, 4],
    "RL-CIT-009": [1, 2, 3, 4],
    "RL-INV-004": [1, 2, 3, 4],
    "RL-VAT-012": [1, 2, 3, 4],
    "RL-SPT-012": [1, 2, 3, 4],
    "RL-SPT-013": [1, 2, 3, 4],
}


# ★ 2026-09-29（C3 风险组合画像）：四类业务轴（单一权威映射）。
#   红线 ID 前缀即其所属业务轴；组合画像在「≥2 个轴同时出现未排除疑点」时触发，
#   提示多税种联动稽查（业务闭环任一环节异常都可能是孤立的，但多个环节同时异常
#   往往指向系统性账务失真，单一税种核查难以还原事实）。
#   新增红线时只需在 REDLINES 加一条 + 此处前缀已覆盖（PTY/INC/FUND/COST 四族），
#   无需改组合逻辑。
_COMBO_AXES = {
    "PTY":  {"label": "票账差异", "prefix": "RL-PTY-"},
    "INC":  {"label": "收入",     "prefix": "RL-INC-"},
    "FUND": {"label": "资金",     "prefix": "RL-FUND-"},
    "COST": {"label": "成本",     "prefix": "RL-COST-"},
}
_COMBO_AXIS_PREFIX = {v["prefix"]: k for k, v in _COMBO_AXES.items()}


def _combo_axis_of(rid: str) -> Optional[str]:
    """红线 ID → 所属业务轴（PTY/INC/FUND/COST）；非四族红线返回 None。"""
    rid = str(rid or "")
    for _p, _k in _COMBO_AXIS_PREFIX.items():
        if rid.startswith(_p):
            return _k
    return None


def _build_combo_profiles(suspicions: List[Dict]) -> List[Dict]:
    """C3：当 ≥2 个业务轴（票账差异/收入/资金/成本）同时出现「未排除」疑点时，
    生成组合风险画像，提示多税种联动稽查。

    入参 suspicions：已归并的红线疑点（含 verdict/confidence/redline_id/redline_name/taxes）。
    返回：组合画像列表（0 或 1 条；0 条表示未达组合触发条件）。
    注意：组合画像**不是**一条独立红线，不计入红线库总数（RL-COMBO 不存在于 REDLINES）。
    """
    _by_axis: Dict[str, List[Dict]] = {}
    for s in (suspicions or []):
        if not isinstance(s, dict):
            continue
        # ★ 排除情形（已有合理解释）不计入组合信号——它们已被论证为未触碰红线。
        if s.get("verdict") == _VERDICT_EXCLUDED:
            continue
        _ax = _combo_axis_of(s.get("redline_id", ""))
        if not _ax:
            continue
        _by_axis.setdefault(_ax, []).append(s)

    _hit_axes = [k for k, v in _by_axis.items() if v]
    if len(_hit_axes) < 2:
        return []

    # 汇总贡献红线与跨税种
    _contrib: List[Dict] = []
    _taxes: set = set()
    _max_conf = 0.0
    _any_confirmed = False
    for _ax in _hit_axes:
        for s in _by_axis[_ax]:
            _contrib.append({
                "redline_id": s.get("redline_id", ""),
                "redline_name": s.get("redline_name", ""),
                "axis": _ax,
                "axis_label": _COMBO_AXES[_ax]["label"],
                "verdict": s.get("verdict", ""),
                "confidence": float(s.get("confidence") or 0.0),
            })
            for t in (s.get("taxes") or []):
                _taxes.add(str(t))
            _max_conf = max(_max_conf, float(s.get("confidence") or 0.0))
            if s.get("verdict") == _VERDICT_CONFIRMED:
                _any_confirmed = True

    _axis_labels = [_COMBO_AXES[a]["label"] for a in _hit_axes]
    _n = len(_hit_axes)
    # 等级：三轴及以上、或任一已定性 → 高风险；否则中风险。
    _level = "高风险" if (_n >= 3 or _any_confirmed) else "中风险"
    _signal = ("经分析，本企业在「{axes}」等多个业务环节同时触发税务风险指标（共 {n} 个环节），"
               "呈现业务全链条勾稽断裂的系统性异常信号，而非孤立的单点问题；"
               "上述各环节疑点均未经合理解释排除。"
               .format(axes="、".join(_axis_labels), n=_n))
    _rec = ("建议启动多税种联动稽查：上述疑点指向收入—成本—资金—票据全链条勾稽断裂，"
            "单一税种核查难以还原事实，应统筹增值税、企业所得税、个人所得税及印花税等"
            "跨税种联动核查，并重点追查「票流—资金流—货物流—账簿」四流是否一致。")
    return [{
        "combo_id": "RL-COMBO",
        "axes": _hit_axes,
        "axis_labels": _axis_labels,
        "axis_count": _n,
        "contributing_redlines": _contrib,
        "combined_taxes": sorted(_taxes),
        "combined_confidence": round(_max_conf, 2),
        "level": _level,
        "signal": _signal,
        "recommendation": _rec,
    }]


def run_redline_detection(findings: List[Dict],
                          engine_data: Optional[Dict] = None,
                          material_readiness: Optional[Dict] = None,
                          pipeline_log: Optional[List] = None) -> Dict:
    """
    红线判定主入口。

    返回：
        {
          "version",
          "suspicions": [ {redline_id, redline_name, suspect, taxes, domain,
                            level, confidence, verdict, closure,
                            clue_chain, evidence_chain, argumentation,
                            supporting_findings:[...], finding_count} ],
          "confirmed": [...], "unconfirmed": [...], "excluded": [...],
          "unmapped": [...],
          "summary": {...}
        }
    """
    findings = [f for f in (findings or []) if isinstance(f, dict)]
    grouped: Dict[str, Dict] = {}
    unmapped: List[Dict] = []

    # 本轮实际已提供的资料类别对所有发现都一样 → 只算一次
    _mats_all = _available_materials(engine_data, material_readiness, {})

    for f in findings:
        rl, minfo = _map_finding(f, _mats_all)
        if not rl:
            # 未能与任何红线可靠配对：如实列为"未归入已知风险情形"，
            # **不**改挂次优红线（否则报告会用不相干的构成要件去论证本发现）
            unmapped.append({
                "type": f.get("type", ""),
                "domain": f.get("domain", ""),
                "level": f.get("level", ""),
                "detail": f.get("detail", ""),
                "match_note": minfo.get("note", ""),
            })
            continue
        rid = rl["id"]
        mats = _available_materials(engine_data, material_readiness, f)
        # ★ 2026-09-29（点评整改 P0-1②）：线索链的"资料缺失/程序待完善"三态判定，
        #   只认资料齐备性唯一权威 material_readiness 的已提供清单。
        clue = build_clue_chain(f, rl, engine_data, provided_materials=_mats_all)
        ev = build_evidence_chain(f, rl, mats, engine_data)
        arg = build_argumentation(f, rl, clue, ev, engine_data)
        # ★ 2026-09-28 逐条判定兜底：显式 constituent_hits 优先；未附时按"检测信号→要件"映射补齐，
        #   证据取自发现自身的 detail/how_found（账内实际命中的事实），保证报告 (A)+(B) 闭环。
        if not arg.get("constituent_hits"):
            _di = _DEFAULT_HIT_INDEX.get(rid)
            if _di:
                _ev_src = f.get("detail") or f.get("how_found") or f.get("description") or ""
                if isinstance(_ev_src, str):
                    _ev_src = _ev_src.strip().replace("\n", " ")[:240]
                if _ev_src:
                    # ★ 2026-09-29（点评整改 P0-5）：兜底命中只落**首个**序号。
                    #   旧版把同一段发现级证据复制进全部兜底序号（实测同一句话填 4~5 个
                    #   要件括号），把"发现级证据"伪装成"逐要件核对"——专业读者一眼识破，
                    #   是报告可信度最大的结构性风险。其余要件由报告统一标注
                    #   "未括注=未单独核对"，绝不复制填充；逐要件独立判定留待后续
                    #   按 _DEFAULT_HIT_INDEX 序号逐个接真实数据源。
                    arg["constituent_hits"] = [
                        {"index": _di[0], "evidence": f"账内检测到：{_ev_src}"}
                    ]
        entry = grouped.get(rid)
        if not entry:
            entry = {
                "redline_id": rid,
                "redline_name": rl.get("name", ""),
                "suspect": rl.get("suspect", ""),
                "taxes": list(rl.get("taxes") or []),
                "domain": rl.get("domain", ""),
                "legal_basis": list(rl.get("legal_basis") or []),
                "constituents": list(rl.get("constituents") or []),
                # ★ 2026-09-29（#448）：逐要件独立数据源（与 constituents 按序对齐），
                #   供 constituent_checkpoint 解析"该要件的数据源本轮是否已取得"。
                "constituent_sources": list(rl.get("constituent_sources") or []),
                "clue_chain": clue,
                "evidence_chain": ev,
                "argumentation": arg,
                "supporting_findings": [],
                "level": f.get("level", ""),
                "confidence": arg.get("confidence", 0.0),
                "closure": ev.get("closure", 0.0),
                "verdict": arg.get("verdict", ""),
                "conclusion_grade": arg.get("conclusion_grade", "待核"),
                "redline_hit": bool(arg.get("redline_hit")),
                "remedy": ev.get("remedy", ""),
                "missing_materials": list(ev.get("missing_materials") or []),
                # ★ 2026-09-25：「待核」（有相关类别但须人工确认）必须与「缺失」分开上报，
                #   否则报告要么漏掉该确认动作，要么把企业其实已交的资料说成"缺"。
                "verify_materials": list(ev.get("verify_materials") or []),
                # ★ 2026-09-25：配对方式与依据必须随结论一起留给报告/审计核对，
                #   使"为什么这条发现被归到这条红线"可被复核。
                "match_mode": minfo.get("mode", ""),
                "match_score": minfo.get("score"),
                "match_reasons": list(minfo.get("reasons") or []),
                "match_materials": list(minfo.get("materials") or []),
            }
            # ★ 2026-09-27（A 收敛）：累计各来源判定的"要件命中"（域/模式检测器/VR 规则）。
            entry["_constituent_hits"] = list(arg.get("constituent_hits") or [])
            grouped[rid] = entry
        else:
            entry["supporting_findings"].append({
                "type": f.get("type", ""),
                "domain": f.get("domain", ""),
                "terminal_signal": clue.get("terminal_signal", ""),
                "clue_nodes": clue.get("nodes", []),
                "numbers": clue.get("numbers", []),
                "samples": clue.get("samples", []),
            })
            # ★ 2026-09-29（#448 接线升级 / 违「静默吃掉发现」红线）：红线配对是 first-finder-wins，
            #   match_mode 在建入口（L336）只取**首条**映射发现的配对方式。若先到的是模糊匹配
            #   （mode="matched"，来自 match_redline_grounded 兜底），而本条发现是**声明型**
            #   （VR 显式写了 redline_id → _map_finding 返回 mode="declared"，才是该红线的真实检测器），
            #   必须把配对方式升为 declared，并以声明型发现的逐要件命中覆盖 _DEFAULT_HIT_INDEX 兜底
            #   （兜底只填首个序号、论证更弱，留着会把"发现级证据"伪装成"逐要件核对"）。
            #   否则声明型检测器虽已接好，运行期却仍被标成模糊匹配，① 检出能力被静默低估。
            if minfo.get("mode") == "declared":
                entry["match_mode"] = "declared"
                if minfo.get("score") is not None:
                    entry["match_score"] = minfo.get("score")
                entry["match_reasons"] = list(minfo.get("reasons") or [])
                entry["match_materials"] = list(minfo.get("materials") or [])
                # 声明型发现是权威来源：以其 argumentation / 逐要件命中覆盖首条（模糊）发现的兜底命中
                entry["argumentation"] = arg
                entry["_constituent_hits"] = list(arg.get("constituent_hits") or [])
            # 归并时取更强的信号：闭合度更高者为主证据链，置信度取最高
            if ev.get("closure", 0) > entry["closure"]:
                entry["evidence_chain"] = ev
                entry["clue_chain"] = clue
                entry["closure"] = ev.get("closure", 0.0)
            # 同一条红线被多条发现命中时，取裁决层级最强的一次作为疑点结论
            if _VERDICT_RANK.get(arg.get("verdict"), 0) > _VERDICT_RANK.get(entry.get("verdict"), 0):
                entry["verdict"] = arg.get("verdict", "")
                entry["conclusion_grade"] = arg.get("conclusion_grade", "待核")
                entry["argumentation"] = arg
            entry["redline_hit"] = bool(entry.get("redline_hit") or arg.get("redline_hit"))
            if arg.get("confidence", 0) > entry["confidence"]:
                entry["confidence"] = arg.get("confidence", 0.0)
            for m in (ev.get("missing_materials") or []):
                if m not in entry["missing_materials"]:
                    entry["missing_materials"].append(m)
            for m in (ev.get("verify_materials") or []):
                if m not in entry.get("verify_materials", []):
                    entry.setdefault("verify_materials", []).append(m)
            # ★ 2026-09-27（A 收敛）：合并本条红线各来源的要件命中（按 index 去重）
            _acc = entry.setdefault("_constituent_hits", [])
            _seen = {(h.get("index") if isinstance(h, dict) else h) for h in _acc}
            for _h in (arg.get("constituent_hits") or []):
                _k = _h.get("index") if isinstance(_h, dict) else _h
                if _k not in _seen:
                    _acc.append(_h)
                    _seen.add(_k)

    # 把累计的要件命中写回 argumentation（供企业报告"一、涉及的风险事项"采用）
    _industry = str((engine_data or {}).get("industry") or "").strip()
    # ★ B1 接线（2026-09-29）：本企业实际指标（唯一来源 compute_indicators）。
    #   取不到即空字典 —— 由 compare_redline_benchmark 如实回「未取得实际值」，
    #   绝不用默认值静默顶替后照常出比对结论。
    _actual_ind: Dict[str, float] = {}
    if engine_data:
        try:
            _actual_ind = _ib_compute_indicators(engine_data) or {}
        except Exception:
            _actual_ind = {}
    for _s in grouped.values():
        _acc = _s.pop("_constituent_hits", None)
        if _acc:
            _s.setdefault("argumentation", {})["constituent_hits"] = _acc
        # ★ 2026-09-28（B2 行业基准动态化）：对"以行业基准为判定口径"的红线，
        #   注入按实际行业解析出的基准区间与口径声明（来源 industry_data.json，非税务机关官方口径）。
        #   不在此写死任何数字；缺行业时只说明"须按实际行业取值"，绝不编造区间。
        _bm = benchmark_note(_s.get("redline_id", ""), _industry or None)
        if _bm.get("metric"):
            _s["benchmark_ref"] = _bm
            _s.setdefault("argumentation", {})["benchmark_ref"] = _bm
            # ★ 2026-09-29（B1 接线）：补上「实际值 vs 行业区间」的真实比对，
            #   使"对照行业基准区间"这类要件名实相符——此前只挂静态区间文本、从未计算实际值。
            #   偏离仅作待核线索，不改裁决（发现≠确认）。
            _cmp = compare_redline_benchmark(_s.get("redline_id", ""),
                                             _industry or None, _actual_ind)
            _s["benchmark_compare"] = _cmp
            _s.setdefault("argumentation", {})["benchmark_compare"] = _cmp

    # 主 findings 也要进 supporting（第一条）
    suspicions = sorted(
        grouped.values(),
        key=lambda x: (-float(x.get("confidence") or 0), -float(x.get("closure") or 0), x["redline_id"]),
    )
    for s in suspicions:
        s["finding_count"] = len(s.get("supporting_findings", [])) + 1

    confirmed = [s for s in suspicions if s.get("verdict") == _VERDICT_CONFIRMED]
    excluded = [s for s in suspicions if s.get("verdict") == _VERDICT_EXCLUDED]
    unconfirmed = [s for s in suspicions
                   if s.get("verdict") in (_VERDICT_HIT_PENDING, _VERDICT_WEAK)]

    # ★ 2026-09-29（C3 风险组合画像）：基于「未排除」疑点跨业务轴聚合，
    #   生成 0/1 条组合信号（不计入红线总数，仅作多税种联动稽查提示）。
    combo_profiles = _build_combo_profiles(suspicions)

    summary = {
        "version": ENGINE_VERSION,
        "knowlege_version": redline_stats().get("version"),
        "redline_total": redline_stats().get("total"),
        "finding_total": len(findings),
        "suspicion_total": len(suspicions),
        "confirmed": len(confirmed),
        "excluded": len(excluded),
        "unconfirmed": len(unconfirmed),
        "unmapped": len(unmapped),
        "combo_profiles": combo_profiles,
    }
    if pipeline_log is not None:
        pipeline_log.append(
            f"[红线判定] {len(findings)}项发现 → 归并命中{len(suspicions)}条税务红线"
            f"（可定性{len(confirmed)}/待补证{len(unconfirmed)}/排除{len(excluded)}"
            f"/未归类{len(unmapped)}），按红线组织线索链·证据链·论证链"
        )
    return {
        "version": ENGINE_VERSION,
        "suspicions": suspicions,
        "confirmed": confirmed,
        "unconfirmed": unconfirmed,
        "excluded": excluded,
        "unmapped": unmapped,
        "summary": summary,
    }


def suspicion_title(s: Dict) -> str:
    """疑点标题：红线名称（禁止再用「待核事实：XXX核验」）"""
    return f"{s.get('redline_id','')} {s.get('redline_name','')}".strip()
