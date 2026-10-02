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
    _VERDICT_EXCLUDED, _VERDICT_WEAK, _VERDICT_EXTERNAL,
)
from engine.redline_benchmark import (
    benchmark_note,
    benchmark_refs,
    compare_redline_benchmark,
)
# 本企业实际指标的**唯一测算来源**（B1 接线：红线判定要用到实际值，禁止另起炉灶重算）
from engine.industry_benchmark import compute_indicators as _ib_compute_indicators

# 裁决优先级：成立可定性 > 成立待补证 > 外部待核 > 线索不足 > 排除
# ★ 2026-10-02：新增 `外部待核` 档（argumentation._VERDICT_EXTERNAL）。
#   它排在「成立待补证」之下——外部核验项并**未**认定触碰红线，只是账内信号待外部数据佐证。
_VERDICT_RANK = {
    _VERDICT_CONFIRMED: 4, _VERDICT_HIT_PENDING: 3,
    _VERDICT_EXTERNAL: 2, _VERDICT_WEAK: 2, _VERDICT_EXCLUDED: 1,
}
#
# ★ 配套名单：这些红线**有意**不参与上面的 `_DEFAULT_HIT_INDEX` 盲发兜底 ——
#   要件异质（同一条红线要各不相同的数据源），盲发会把任何命中都记成同一条要件、
#   报告则出现「认下第①条要件」却拿不出该要件证据的假闭环。它们的“可达”由软匹配
#   检测器保证（RL-CIT-001 已在公司1 真账套实测产出疑点），故准入闸门
#   `check_redline_admission` 把它们与“登记兜底”同等看待，不算盲区红线。
#   ⚠ 必须落在字典**外面**：它是声明，不是兜底表的一个条目。
_NO_BLIND_CONSTITUENT_FALLBACK = {"RL-CIT-001"}

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


# ★★ 2026-10-02：**正向（非风险）结论等级**——这类发现只讲"企业享有/符合什么"，
#   不是涉税风险；把它们配成风险红线必然产出"疑点主体与内容错配"的报告。
#   用系统既有的等级值即判，新增同类无需改代码（数据驱动）。
_NON_RISK_LEVELS = {"优惠机会", "政策红利", "税收优惠"}


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
    # ★★ 2026-10-02（用户：疑点内容与疑点主体错配，彻底修复）：
    #   **税收优惠/红利类发现不是风险事项，不得配成风险红线**。
    #   事故：`tax_incentive_analyzer` 的「残保金免征(应享)」（level=优惠机会，
    #   带 `tax_benefit` 键）因文本含"残保金"被软匹配到 RL-SPT-019
    #   「未按规定安排残疾人就业且未申报缴纳残保金」—— 报告于是出现
    #   "疑点：未申报残保金"却把"依法免征、应享优惠"当证据的自相矛盾。
    #   判据用系统既有的 level 值（`优惠机会`）与正负向字段（`tax_benefit`），
    #   不针对具体税种写特例：凡正向优惠一律不进风险配对。
    if str(finding.get("level") or "").strip() in _NON_RISK_LEVELS or finding.get("tax_benefit"):
        return None, {
            "mode": "not_a_risk", "score": 0, "reasons": [],
            "materials": [],
            "note": "税收优惠/红利类发现，属正向机会提示，不作为税务风险事项配对",
        }
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
    # ★★ 2026-10-02：**配对文本只用"事实层"字段，不含 `description`**。
    #   事故：「人均效能评估」的 `description` 是一段通用说明（"…可能表明存在虚列人员
    #   工资或收入申报不足的问题"），于是仅凭这句解释性文字就把它配到
    #   RL-PAY-003「虚列人员：工资表人员无真实用工痕迹」—— 报告标题说"虚列人员"，
    #   证据却只是"人均产值 X 元"。
    #   说明性文字天然会列举多种可能风险 ⇒ 用它做配对，任何发现都能"命中"任意红线。
    #   事实层＝发现类型 + 具体读数(detail) + 目标事实；how_found 只述方法、也不参与。
    text = " ".join(str(finding.get(k) or "") for k in
                    ("type", "domain", "detail", "target_fact"))
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
    # ★ 2026-10-02（用户复核疑点5：宁缺勿错）—— **RL-CIT-001 故意不登记兜底序号。**
    #   该红线是「构成要件异质」的典型：①六员/地址/电话/账户重叠 ②购销占比超基准
    #   ③定价偏离或无合理商业目的 ④未备同期资料 ⑤正当情形 —— 五种情形要各不相同的数据源。
    #   旧的 [1, 4] 兜底会对**任何**命中该红线的未声明发现一律记成"第①条六员重叠"，
    #   而实测全系统没有任何扫描器真算过六员/地址/电话比对：于是报告出现
    #   「认下第①条要件」却拿不出六员证据的假闭环（同项要件表却是「涉及第 无 条」）。
    #   改为**谁真算过要件谁自己声明 constituent_hits**，算不出的不认领：
    #   报告如实写「未认定到任何一条构成要件 + 账内信号」，而不是编一条。
    #   （外部核验项 ext_related_party_docs_verify 同理，见 external_check_reminder。）
    #
    # ★ 配套名单：`_NO_BLIND_CONSTITUENT_FALLBACK`。这些红线**有意**不参与盲发兜底，
    #   但可达性由软匹配检测器保证（已在公司1 真账套实测产出疑点），因此不能算"盲区红线"
    #   ——准入闸门 `check_redline_admission` 据此把它们也算作"可达"。
    #
    #   ⚠ 名单必须放在字典**外面**：它是一份声明，不是兜底表的一条目。
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
    _signal = ("经分析，本企业在「{axes}」等多个业务环节同时触发税务风险指标，"
               "呈现业务全链条勾稽断裂的系统性异常信号，而非孤立的单点问题；"
               "上述各环节疑点均未经合理解释排除。"
               .format(axes="、".join(_axis_labels), n=_n))
    _rec = ""  # 2026-10-01 按用户定调：删除「建议启动多税种联动稽查」类编排建议
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


def _entry_candidates(rid: str, group: List[Dict]) -> List[Dict]:
    """把本红线的候选发现规整成 entry 选择所需的形态（唯一权威接口的输入）。"""
    name = ""
    for rec in (group or []):
        name = str((rec.get("rl") or {}).get("name") or "")
        break
    out = []
    for rec in (group or []):
        _f = rec.get("f") or {}
        _mi = rec.get("minfo") or {}
        _ev = rec.get("ev") or {}
        try:
            _clo = float(_ev.get("closure") or 0)
        except (TypeError, ValueError):
            _clo = 0.0
        out.append({
            "type": str(_f.get("type") or "").strip(),
            "declared": _mi.get("mode") == "declared",
            "closure": _clo,
        })
    return out


def _pick_entry(rid: str, group: List[Dict]) -> int:
    """选"建入口那条发现"（唯一权威 `subject_consistency.pick_entry_index`，本名薄转发）。"""
    try:
        from engine.subject_consistency import pick_entry_index as _pei
        _name = ""
        for rec in (group or []):
            _name = str((rec.get("rl") or {}).get("name") or "")
            break
        return int(_pei(rid, _name, _entry_candidates(rid, group)))
    except Exception as exc:  # 不得静默：留痕并退回"取首条"（与旧行为一致）
        print(f"[redline_engine] entry 选择失败，退回首条: {exc}", flush=True)
        return 0


def _entry_choice(rid: str, group: List[Dict]) -> str:
    """本疑点 entry 选择的依据（一行，供日志/审计复核"为什么是它"）。"""
    try:
        from engine.subject_consistency import format_entry_choice as _fec
        _name = ""
        for rec in (group or []):
            _name = str((rec.get("rl") or {}).get("name") or "")
            break
        return _fec(rid, _name, _entry_candidates(rid, group))
    except Exception:
        return ""


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

    # ★★ 2026-10-02（用户：疑点内容与疑点主体错配，彻底修复｜第二轮）：
    #   **先收全每条红线的候选发现，再统一选"建入口那条"（entry）**，取消 first-finder-wins。
    #   旧实现两个错配来源：
    #     ① entry 固定为**第一条**映射到该红线的发现；若它是软匹配来的无关发现，
    #        整条疑点的标题裁剪口径/线索链/证据链/附表归属/主体自检**全部建立在错的那条上**
    #        （实测 RL-SPT-017「广告/娱乐服务未申报文化事业建设费」的 entry 是
    #        「同一供应商同品名单价不一致」—— 只因该发现正文里举了"广告服务"这个例子）；
    #     ② 归并时按 closure「取更强信号」把 entry 的 clue/evidence 换成**另一条**发现的，
    #        于是同一疑点内"finding_type 讲A、证据链讲B"。
    #   现规则（唯一权威 `subject_consistency.pick_entry_index`）：主体一致 → 声明型 → 闭合度高；
    #   entry 定了之后，它的 clue/evidence/argumentation/finding_type/level **只来自这一条**
    #   （同一来源）；其余发现只贡献支撑清单、要件命中与资料并集。
    pending: Dict[str, List[Dict]] = {}
    order: List[str] = []
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
        if rid not in pending:
            pending[rid] = []
            order.append(rid)
        pending[rid].append({"f": f, "rl": rl, "minfo": minfo,
                             "clue": clue, "ev": ev, "arg": arg})

    for rid in order:
        group = pending[rid]
        _idx = _pick_entry(rid, group)
        _base = group[_idx]
        f = _base["f"]
        rl = _base["rl"]
        minfo = _base["minfo"]
        clue = _base["clue"]
        ev = _base["ev"]
        arg = _base["arg"]
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
            # ★★ 2026-10-02（用户：疑点内容与疑点主体错配，彻底修复）：
            #   **建入口那条发现（entry）的类型必须留下来**。
            #   根因：`supporting_findings` 只装**第 2 条及以后**的发现，entry 自己的类型
            #   此前没有落到任何字段 ⇒ 下游（报告）拿不到"本疑点到底依据了哪条发现"：
            #     · `trim_redline_title` 的 `own_type` 取不到 → 标题只能沿用红线包名；
            #     · 报告挂逐笔明细时无从按来源归属 → 退回"红线名 ↔ 类型"2-gram 兜底 → 挂错表；
            #     · 主体一致性自检无从核对 → 只能误报"疑点无支撑发现"。
            #   现把 entry 的 `type` 作为**本疑点主体**显式落盘（唯一权威来源）。
            "finding_type": str(f.get("type") or "").strip(),
            # entry 选择依据（供日志/审计复核"为什么是它"）
            "entry_choice": _entry_choice(rid, group),
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
        for _j, _rec in enumerate(group):
            if _j == _idx:
                continue
            _rf, _rmi = _rec["f"], _rec["minfo"]
            _rclue, _rev, _rarg = _rec["clue"], _rec["ev"], _rec["arg"]
            entry["supporting_findings"].append({
                "type": _rf.get("type", ""),
                "domain": _rf.get("domain", ""),
                "terminal_signal": _rclue.get("terminal_signal", ""),
                "clue_nodes": _rclue.get("nodes", []),
                "numbers": _rclue.get("numbers", []),
                "samples": _rclue.get("samples", []),
            })
            # ★ 2026-09-29（#448）：配对方式是**红线级**事实 —— 只要本红线被任一"声明型"
            #   发现认领过（VR 显式写了 redline_id / 扫描器前置认领），就标 declared，
            #   否则声明型检测器虽已接好、运行期仍被标成模糊匹配，检出能力被静默低估。
            if _rmi.get("mode") == "declared":
                entry["match_mode"] = "declared"
                if _rmi.get("score") is not None:
                    entry["match_score"] = _rmi.get("score")
                entry["match_reasons"] = list(_rmi.get("reasons") or [])
                entry["match_materials"] = list(_rmi.get("materials") or [])
            # 同一条红线被多条发现命中时，**裁决层级取最强的一次**（这是红线级裁决，
            #   与"由哪条发现讲这条疑点的故事"是两件事）；同时记下该裁决来自哪条发现，
            #   供报告自检与复核追溯 —— 不再用它替换 entry 的论证/证据（那正是错配来源）。
            if _VERDICT_RANK.get(_rarg.get("verdict"), 0) > _VERDICT_RANK.get(entry.get("verdict"), 0):
                entry["verdict"] = _rarg.get("verdict", "")
                entry["conclusion_grade"] = _rarg.get("conclusion_grade", "待核")
                entry["verdict_source_type"] = str(_rf.get("type") or "").strip()
            entry["redline_hit"] = bool(entry.get("redline_hit") or _rarg.get("redline_hit"))
            if _rarg.get("confidence", 0) > entry["confidence"]:
                entry["confidence"] = _rarg.get("confidence", 0.0)
            for _m in (_rev.get("missing_materials") or []):
                if _m not in entry["missing_materials"]:
                    entry["missing_materials"].append(_m)
            for _m in (_rev.get("verify_materials") or []):
                if _m not in entry.get("verify_materials", []):
                    entry.setdefault("verify_materials", []).append(_m)
            # ★ 2026-09-27（A 收敛）：合并本条红线各来源的要件命中（按 index 去重）
            _acc = entry.setdefault("_constituent_hits", [])
            _seen = {(h.get("index") if isinstance(h, dict) else h) for h in _acc}
            for _h in (_rarg.get("constituent_hits") or []):
                _k = _h.get("index") if isinstance(_h, dict) else _h
                if _k not in _seen:
                    _acc.append(_h)
                    _seen.add(_k)
        grouped[rid] = entry

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
        # ★ 2026-10-02（用户复核疑点5）：**疑点级裁决必须跟着"实际渲染的那份论证"走。**
        #   事故：归并过程中 verdict 被"最强信号"分支改写、argumentation 又被"声明型发现"
        #   分支改写（两分支各写一份、互不同步），报告于是同时输出
        #   「结论=已触碰税务违规红线」与「一、未认定到任何一条构成要件 / 四、本轮不作定性」。
        #   铁律：读者看到的裁决与读到的论证必须出自同一处，故在此统一对齐（只对齐、不重判）：
        #   渲染用哪份 argumentation，verdict/grade/redline_hit 就是那一份的。
        _rendered = _s.get("argumentation") or {}
        if _rendered:
            _s["verdict"] = _rendered.get("verdict", _s.get("verdict", ""))
            _s["conclusion_grade"] = _rendered.get(
                "conclusion_grade", _s.get("conclusion_grade", "待核"))
            _s["redline_hit"] = bool(_rendered.get("redline_hit"))
        _acc = _s.pop("_constituent_hits", None)
        if _acc:
            _s.setdefault("argumentation", {})["constituent_hits"] = _acc
        # ★ 2026-10-02（用户复核疑点5 的第二个矛盾）：**「触红断言」必须与「要件认定」同步**。
        #   判据用唯一权威 `constituent_checkpoint`（`enterprise_report` 的
        #   `_participating`、报告里的「本企业涉及上述第 N 条」都出自它，不另立口径）。
        #   若一条要件都没认定，就把本疑点论证里的触红断言（开场句 / 「本项结论是<裁决>」
        #   / 段尾「已经触碰税务红线…」）中性化。
        #   ★ 必须**在这里**做：报告侧读到的文本已经被 `plain_language.to_plain`
        #     改写过（「补证」→「补充资料」），在报告侧逐字找锚点会静默失效（实测过一次）。
        _cp = 0
        try:
            from engine.constituent_checkpoint import (
                build_constituent_checkpoints as _bcc,
                participating_indices as _pind,
            )
            _cp = len(_pind(_bcc(_s)) or [])
        except Exception as _exc:  # 留痕：静默失败会让矛盾文本重新进报告
            if pipeline_log is not None:
                pipeline_log.append(f"[红线论证] 要件认定口径核对异常：{_exc}")
            _cp = None
        if _cp == 0:
            try:
                from engine.argumentation import neutralize_assertion_when_no_constituent as _neu
                _arg = _s.setdefault("argumentation", {})
                if _arg.get("reasoning"):
                    # `reasoning` 是唯一进报告正文的论证文本（`claim` 只作内部字段，
                    # 全库无消费方），故只净化它。
                    _arg["reasoning"] = _neu(_arg["reasoning"], _s.get("redline_name", ""))
            except Exception as _exc:
                if pipeline_log is not None:
                    pipeline_log.append(f"[红线论证] 触红断言中性化异常：{_exc}")
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
    # ★ 2026-10-02：外部核验档虽不判触红，但仍属「待后续核验后才能有结论」，
    #   必须计入待补证桶，否则 summary 各类计数加总会少于疑点总数（计数对不上账）。
    unconfirmed = [s for s in suspicions
                   if s.get("verdict") in (_VERDICT_HIT_PENDING, _VERDICT_WEAK,
                                           _VERDICT_EXTERNAL)]

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
