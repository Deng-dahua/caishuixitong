"""行业预警指标库与对标探测（2026-09-12）

对应金税四期最核心的能力之一：**行业指标预警**。
税务机关常用的横向比对口径即「本企业指标 vs 同行业预警区间」，偏离即列为风险纳税人。

本模块提供：
1. INDUSTRY_BENCHMARKS —— 分行业的增值税税负率/毛利率/期间费用率/进销比参考预警区间；
2. compute_indicators()  —— 用现有数据计算企业实际指标；
3. run_industry_benchmark_check() —— 实际值 vs 行业区间，产出待核疑点。

★ 边界声明（必须随结果一并告知，绝不定性）：
- 区间为**通用参考预警值**，来源于公开行业经验区间，非税务机关官方口径，
  各地税务机关的行业预警值以本地模型为准；
- 偏离区间只构成**待核线索**，不构成"少缴税款"的定性结论；
- 行业周期、经营模式、出口占比、政策优惠等都会造成合理偏离，须经正当理由核验。
"""

from __future__ import annotations
from engine.numparse import to_number  # ★ 2026-09-25 统一数值解析（唯一实现）

import json
import os
from typing import Any, Dict, List, Tuple

# 实测校准表（由 tools/calibrate_industry_benchmarks.py 用真实账套生成）。
# 存在时**优先于**下方通用参考区间；不存在则回退参考区间。
_CALIBRATED_PATH = os.path.join(
    os.path.dirname(__file__), "..", "static", "industry_benchmarks_calibrated.json"
)
_CALIBRATED: Dict[str, Dict[str, Tuple[float, float]]] = {}


def _load_calibrated() -> Dict[str, Dict[str, Tuple[float, float]]]:
    global _CALIBRATED
    if _CALIBRATED:
        return _CALIBRATED
    try:
        if os.path.exists(_CALIBRATED_PATH):
            with open(_CALIBRATED_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
            out = {}
            for ind, vals in (raw or {}).items():
                if not isinstance(vals, dict):
                    continue
                out[ind] = {
                    k: (float(v[0]), float(v[1]))
                    for k, v in vals.items()
                    if isinstance(v, (list, tuple)) and len(v) == 2
                }
            _CALIBRATED = out
    except Exception:
        _CALIBRATED = {}
    return _CALIBRATED


def benchmark_source(industry: str) -> str:
    """返回该行业当前使用的区间来源：'实测校准' / '通用参考'。"""
    return "实测校准" if industry in _load_calibrated() else "通用参考"


# 系统既有的权威行业档案（audit_enhancements.get_industry_benchmark 同源），
# 含 8 个行业的毛利率区间与进销比等基准。优先于本文件的通用参考表，
# 避免与系统其他模块出现两套口径。
_PROFILES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "static", "industry_profiles.json"
)
_PROFILES: Dict[str, Dict[str, Tuple[float, float]]] = {}


def _load_profiles() -> Dict[str, Dict[str, Tuple[float, float]]]:
    """从 static/industry_profiles.json 读取行业档案基准。"""
    global _PROFILES
    if _PROFILES:
        return _PROFILES
    out: Dict[str, Dict[str, Tuple[float, float]]] = {}
    try:
        if os.path.exists(_PROFILES_PATH):
            with open(_PROFILES_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            for ind, prof in (data.get("industries") or {}).items():
                if not isinstance(prof, dict):
                    continue
                bm = prof.get("benchmarks") or {}
                gp = bm.get("gross_margin_pct") or {}
                entry: Dict[str, Tuple[float, float]] = {}
                if isinstance(gp, dict) and gp.get("low") is not None:
                    entry["gross_margin"] = (float(gp.get("low")), float(gp.get("high")))
                psr = bm.get("purchase_sales_ratio")
                if isinstance(psr, (list, tuple)) and len(psr) == 2:
                    entry["purchase_sales"] = (float(psr[0]), float(psr[1]))
                if entry:
                    out[ind] = entry
                    # 同时也登记 label 名，便于按 label 命中
                    label = str(prof.get("label", "") or "").strip()
                    if label and label not in out:
                        out[label] = entry
    except Exception:
        out = {}
    _PROFILES = out
    return out


def resolve_benchmark(industry: str):
    """按优先级解析区间：实测校准 > 行业档案 industry_profiles > 通用参考表 > 宽松兜底。

    返回 (区间dict, 来源说明)。
    """
    matched = match_industry(industry) if industry else ""
    cal = _load_calibrated()
    prof = _load_profiles()
    if matched and cal.get(matched):
        return matched, cal[matched], "实测校准"
    if matched and prof.get(matched):
        return matched, prof[matched], "行业档案(industry_profiles)"
    if matched and INDUSTRY_BENCHMARKS.get(matched):
        return matched, INDUSTRY_BENCHMARKS[matched], "通用参考"
    return matched, _GENERIC, "通用宽松区间(未匹配到行业)"

# ═══════════════════════════════════════════════════════════════════════════
# 行业名 → 本区间库键名 的**对齐表**（唯一维护处）
# ═══════════════════════════════════════════════════════════════════════════
# ★ 2026-09-25 新增：本模块的 `INDUSTRY_BENCHMARKS` 使用的是**国民经济行业门类**口径
#   （"批发和零售业""租赁和商务服务业"…），而 `static/industry_data.json` 的
#   `benchmarks` 用的是**细分行业**口径（"商贸""纺织制造""广告传媒"…）。
#   两套口径不同名，导致细分行业名在本库"全部落空"→ 静默退到通用宽松区间，
#   读者却以为是"行业区间"（实测：某数字传媒公司毛利率 7.2% 因缺"广告传媒"键而未报警）。
#   这里集中登记口径对应关系（新增行业只需在此加一行，不散落到各处）：
_INDUSTRY_ALIAS = {
    # 细分行业 → 本库门类
    "商贸": "批发零售", "商贸批发": "批发零售", "商贸零售": "批发零售",
    "外贸": "批发零售", "电子商务": "批发零售", "建材销售": "批发零售",
    "广告传媒": "租赁商务", "文化传媒": "租赁商务",
    "咨询服务": "租赁商务", "设计服务": "租赁商务",
    "租赁服务": "租赁商务", "法律服务": "租赁商务",
    "财税服务": "租赁商务", "投资管理": "租赁商务",
    "信息技术": "软件信息服务", "互联网": "软件信息服务",
    "技术服务": "软件信息服务", "研发服务": "软件信息服务",
    "检测服务": "软件信息服务",
    "餐饮服务": "住宿餐饮", "酒店服务": "住宿餐饮",
    "物流运输": "交通运输", "物流仓储": "交通运输",
    "停车服务": "交通运输",
    "建筑工程": "建筑业", "装修装饰": "建筑业", "房地产": "房地产业",
    "纺织制造": "制造业", "服装制造": "制造业", "印染加工": "制造业",
    "染整加工": "制造业", "机械制造": "制造业", "设备制造": "制造业",
    "模具制造": "制造业", "五金加工": "制造业", "电子制造": "制造业",
    "电子元器件": "制造业", "电器制造": "制造业", "仪器仪表": "制造业",
    "汽车制造": "制造业", "汽车零部件": "制造业", "化工": "制造业",
    "塑料制品": "制造业", "橡胶制品": "制造业", "钢铁": "制造业",
    "金属加工": "制造业", "木材加工": "制造业", "家具制造": "制造业",
    "食品加工": "制造业", "医药健康": "制造业", "医疗器械": "制造业",
    "生物医药": "制造业", "新能源": "制造业", "半导体": "制造业",
    "农业生产": "农林牧渔", "畜牧养殖": "农林牧渔", "水产养殖": "农林牧渔",
    "能源": "电力热力燃气水", "环保": "电力热力燃气水",
}


# ── 行业参考预警区间 —— ★ 全部从唯一数据源派生，本文件不再硬编码任何数字 ──────
# ★ 2026-09-25 合并（消除"两套数字"）：
#   原先本模块自带 23 条硬编码区间 + 一条 _GENERIC，与
#   `static/industry_data.json → benchmarks`（65 个细分行业）并存，同一概念两套数字，
#   本模块注释自己也写着"避免两套数字"。现全部改为从唯一数据源派生：
#     · 细分行业层 benchmarks  + 门类层 benchmarks_coarse，**同一套指标名与结构**；
#     · 缺 期间费用率 的细分行业，**按门类继承**（见 _INDUSTRY_ALIAS）；
#     · 对外键名与单位保持不变（vat_burden/gross_margin/expense_ratio/purchase_sales，百分比），
#       以兼容既有调用方；换算在本文件内一次完成。
_METRIC_ZH_TO_EN = {
    "毛利率": "gross_margin",
    "税负率": "vat_burden",
    "期间费用率": "expense_ratio",
    "进销比": "purchase_sales",
}
# ★ 各指标的换算系数（**必须按指标分别换算**）：
#   毛利率/税负率/期间费用率 在数据源里是**比例**（0.12）→ ×100 得百分比；
#   进销比本身就是**比值**（进项/销项，0.4~1.0），**不得**再乘 100。
#   （首版统一 ×100 曾把 进销比 0.4~0.95 变成 40~95，属单位错误。）
_METRIC_SCALE = {"毛利率": 100.0, "税负率": 100.0, "期间费用率": 100.0, "进销比": 1.0}


def _build_industry_benchmarks() -> Dict[str, Dict[str, Tuple[float, float]]]:
    """从唯一数据源（static/industry_data.json）派生区间表。"""
    from engine.industry_resolver import load_industry_data
    data = load_industry_data() or {}
    out: Dict[str, Dict[str, Tuple[float, float]]] = {}
    coarse_rows: Dict[str, Dict[str, Tuple[float, float]]] = {}

    def _row(src: dict) -> Dict[str, Tuple[float, float]]:
        row = {}
        for zh, en in _METRIC_ZH_TO_EN.items():
            tri = (src or {}).get(zh)
            if isinstance(tri, (list, tuple)) and len(tri) >= 2:
                k = _METRIC_SCALE[zh]
                try:
                    row[en] = (round(float(tri[0]) * k, 4), round(float(tri[1]) * k, 4))
                except (TypeError, ValueError):
                    continue
        return row

    for k, v in (data.get("benchmarks_coarse") or {}).items():
        row = _row(v)
        if row:
            coarse_rows[k] = row
    for k, v in (data.get("benchmarks") or {}).items():
        if k == "_default":
            continue
        row = _row(v)
        if row:
            out[k] = row
    # 细分行业缺 期间费用率 → 按其所属门类继承（门类归属见 _INDUSTRY_ALIAS）
    for k, row in out.items():
        if "expense_ratio" in row:
            continue
        coarse_key = _INDUSTRY_ALIAS.get(k)
        inherited = coarse_rows.get(coarse_key or "", {}).get("expense_ratio")
        if inherited:
            row["expense_ratio"] = inherited
    # 门类层同样对外可用（原先只认"门类名"的调用方继续工作）
    for k, row in coarse_rows.items():
        out.setdefault(k, row)
    return out


def _build_generic() -> Dict[str, Tuple[float, float]]:
    """宽松兜底区间 —— 同样从数据源 `benchmarks._default` 派生。"""
    from engine.industry_resolver import load_industry_data
    dflt = (load_industry_data() or {}).get("benchmarks", {}).get("_default") or {}
    row = {}
    for zh, en in _METRIC_ZH_TO_EN.items():
        tri = dflt.get(zh)
        if isinstance(tri, (list, tuple)) and len(tri) >= 2:
            k = _METRIC_SCALE[zh]
            try:
                row[en] = (round(float(tri[0]) * k, 4), round(float(tri[1]) * k, 4))
            except (TypeError, ValueError):
                continue
    # 数据源不可读时返回空字典：下游 `bench.get(k, (None, None))` 会跳过该指标，
    # **绝不在本文件里再写一套兜底数字**（那正是"两套数字"的来源）。
    return row


INDUSTRY_BENCHMARKS: Dict[str, Dict[str, Tuple[float, float]]] = _build_industry_benchmarks()
_GENERIC: Dict[str, Tuple[float, float]] = _build_generic()

def match_industry(name: str) -> str:
    """按行业名/企业描述匹配本库行业键，匹配不到返回空串。

    ★ 2026-09-25 重写（消除两个通用缺陷）：
      ① 先查**显式对齐表** `_INDUSTRY_ALIAS`（细分行业名 → 本库门类），
         解决"两套口径不同名导致细分行业全部落空、静默退通用区间"；
      ② 再按**键长从长到短**精确包含匹配（原先按字典顺序取"键前 4 字"做包含，
         结果依赖键的书写顺序，且短片段易误命中断言）。
    """
    text = str(name or "")
    if not text:
        return ""
    # ① 显式对齐（细分行业名或门类名本身）
    if text in INDUSTRY_BENCHMARKS:
        return text
    for frag, key in _INDUSTRY_ALIAS.items():
        if frag in text:
            return key
    # ② 键长优先的包含匹配（确定、可解释）
    for key in sorted(INDUSTRY_BENCHMARKS, key=len, reverse=True):
        if key in text:
            return key
    for key in sorted(INDUSTRY_BENCHMARKS, key=len, reverse=True):
        frag = key.replace("、", "").replace("和", "")
        if len(frag) >= 3 and frag in text:
            return key
    return ""


def _num(v: Any) -> float:
    """数值解析（统一实现）。

    ★ 2026-09-25 收敛：实现已统一到 engine/numparse.py（唯一权威）。
      原私有实现遇 "12,000.00" / "￥1,234.56" 等会静默返回 0，
      导致同一金额在不同模块被算成不同值（报告自相矛盾 / 规则漏触发）。
    """
    from engine.numparse import to_number as _to_number
    return _to_number(v)


def _sum_field(records: Any, keys: List[str]) -> float:
    """按候选键名求和金额（容错不同来源字段命名）。"""
    total = 0.0
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        for k in keys:
            if rec.get(k) not in (None, ""):
                total += _num(rec.get(k))
                break
    return total


def compute_indicators(engine_data: Dict) -> Dict[str, float]:
    """计算企业实际指标（百分比）。返回 {指标: 值}，取不到数据的指标不返回。"""
    sal_invs = engine_data.get("sal_invs") or []
    pur_invs = engine_data.get("pur_invs") or []
    vouchers = engine_data.get("vouchers") or []

    sales = _sum_field(sal_invs, ["金额", "价税合计", "total", "amount", "不含税金额"])
    sales_tax = _sum_field(sal_invs, ["税额", "tax", "销项税额"])
    purchase = _sum_field(pur_invs, ["金额", "价税合计", "total", "amount", "不含税金额"])
    purchase_tax = _sum_field(pur_invs, ["税额", "tax", "进项税额"])

    # 成本费用：优先从凭证科目归集
    cost = 0.0
    expense = 0.0
    for rec in vouchers:
        if not isinstance(rec, dict):
            continue
        text = str(rec.get("科目", "")) + str(rec.get("摘要", ""))
        amt = _num(rec.get("金额") or rec.get("借方金额") or rec.get("借方"))
        if any(k in text for k in ("主营业务成本", "生产成本", "库存商品", "原材料")):
            cost += amt
        elif any(k in text for k in ("销售费用", "管理费用", "财务费用")):
            expense += amt

    out: Dict[str, float] = {}
    if sales > 0:
        vat_due = sales_tax - purchase_tax
        out["vat_burden"] = round(vat_due / sales * 100, 2)
        if cost > 0:
            out["gross_margin"] = round((sales - cost) / sales * 100, 2)
        if expense > 0:
            out["expense_ratio"] = round(expense / sales * 100, 2)
        if purchase > 0:
            out["purchase_sales"] = round(purchase / sales, 3)
    return out


def build_benchmark_input(bank_txs=None, sal_invs=None, pur_invs=None,
                          vouchers=None, salaries=None, inventory=None,
                          tax_declarations=None, declarations=None) -> Dict:
    """指标测算输入的**唯一构造点**（2026-09-29 B1 收敛）。

    ★ 为什么必须有它：domain 层行业对标与红线注解要的是**同一份输入**，此前两处各拼一份
      dict —— 红线侧漏传 sal_invs/pur_invs/vouchers，导致 compute_indicators 恒返回空，
      「实际值 vs 区间」比对永远落到"未取得实际值"（B1 名实不符的真正根因）。
    收敛后：新增/改名输入字段只改这一处，两处消费方自动一致。
    """
    return {
        "bank_txs": bank_txs or [],
        "sal_invs": sal_invs or [],
        "pur_invs": pur_invs or [],
        "vouchers": vouchers or [],
        "salaries": salaries or [],
        "inventory": inventory or [],
        "tax_declarations": tax_declarations or [],
        "declarations": declarations or [],
    }


def normalize_actual(key: str, actual: float) -> float:
    """实际值归一化 —— **单一权威**（domain 检查与红线注解共用，禁止各处自写换算）。

    进销比在数据源里是比值（0.4~1.0）；若历史数据以百分比形式给出（>1.5）则换算回比值，
    避免与区间口径不一致。（首版曾统一 ×100，把 0.4~0.95 变成 40~95，属单位错误。）
    """
    if key == "purchase_sales" and actual > 1.5:
        return actual / 100.0
    return actual


# ★ 参与行业比对的**合理值域**（数据完整性护栏，2026-09-29）
#   用途：区分「真的偏离」与「本轮数据不全算出来的荒谬值」。
#   实测事故：临时账套 销售收入 26,482 元 vs 采购成本 2,529,450 元 → 毛利率 -9451%、
#   税负率 -683%；这类值并非企业真实经营信号，而是**分母过小/数据不完整**的产物，
#   若照常与行业区间比对并写进报告，会误导读者、损害报告可信度。
#   ⚠ 这是"可否参与比对"的门槛，**不是**行业基准区间，也非税务机关口径；
#      新增/调整指标只改这张表，不改逻辑分支。
_SANE_RANGE: Dict[str, Tuple[float, float]] = {
    "gross_margin": (-200.0, 100.0),    # 上界 100%（成本≥0）；下界 -200%（成本>3倍收入即疑数据不全）
    "vat_burden": (-100.0, 100.0),      # 税负率绝对值超过营收规模即不合理
    "expense_ratio": (0.0, 300.0),      # 期间费用率上限放宽（亏损企业可 >100%）
    "purchase_sales": (0.0, 20.0),      # 进销比（比值）
}


def is_indicator_comparable(key: str, actual: float) -> bool:
    """该指标本轮实际值**可否参与行业比对**（数据完整性护栏，单一权威）。

    超出 `_SANE_RANGE` 即判为「本轮数据异常」，调用方应如实说明不参与比对，
    **绝不能**用它算出"低于/高于行业区间"的结论（那是拿残缺数据冒充发现）。
    未登记值域的指标默认可比（不因护栏漏登记而静默吞掉真实指标）。
    """
    rng = _SANE_RANGE.get(key)
    if not rng:
        return True
    value = normalize_actual(key, actual)
    return bool(rng[0] <= value <= rng[1])


def evaluate_indicator(key: str, actual: float, low: float,
                       high: float) -> Dict[str, object]:
    """实际值 vs 行业区间的比对判定 —— **单一权威**（禁止各处自写比较式）。

    ★ B1 接线（2026-09-29）：此前红线构成要件写「对照行业基准区间上沿」却从不计算，
      只有 domain 层在比对，两处若各写一套比较式必然口径分歧，故收敛到本函数共用。

    返回 {"value","low","high","in_range","direction","bound"}：
      in_range=True  → direction=""、bound=None；
      in_range=False → direction ∈ {"低于","高于"}、bound 为被突破的边界值。
    """
    value = normalize_actual(key, actual)
    comparable = is_indicator_comparable(key, actual)
    in_range = bool(low <= value <= high)
    direction = "" if in_range else ("低于" if value < low else "高于")
    bound = None if in_range else (low if value < low else high)
    return {"value": value, "low": low, "high": high,
            "in_range": in_range, "direction": direction, "bound": bound,
            "comparable": comparable}


def run_industry_benchmark_check(
    engine_data: Dict,
    industry: str = "",
    pipeline_log: List[str] = None,
) -> List[Dict]:
    """实际指标 vs 行业预警区间，产出待核疑点（绝不定性）。"""
    indicators = compute_indicators(engine_data)
    if not indicators:
        return []

    # 优先级：实测校准 > 行业档案(industry_profiles) > 通用参考表 > 宽松兜底
    matched, bench, source = resolve_benchmark(industry)
    if not matched and pipeline_log is not None:
        pipeline_log.append("[行业对标] 未匹配到具体行业，按通用宽松区间比对（降低误报）")

    findings: List[Dict] = []
    for key, actual in indicators.items():
        low, high = bench.get(key, (None, None))
        if low is None:
            continue
        # ★ 比对判定统一委托 evaluate_indicator（单一权威，避免与红线注解口径分歧）
        ev = evaluate_indicator(key, actual, low, high)
        # ★ 数据完整性护栏：超出合理值域说明本轮数据不完整（如销售极小、采购极大），
        #   此时"偏离行业区间"是数据假象而非经营信号，照常产出会误导读者。
        if not ev.get("comparable", True):
            if pipeline_log is not None:
                pipeline_log.append(
                    f"[行业对标] {_LABEL[key]}实测 {actual} 超出合理值域，"
                    f"疑本轮数据不完整，不参与行业区间比对")
            continue
        if ev["in_range"]:
            continue
        value = ev["value"]
        direction = ev["direction"]
        unit = "" if key == "purchase_sales" else "%"
        detail_value = round(value, 3) if key == "purchase_sales" else value
        bound_disp = round(ev["bound"], 3) if key == "purchase_sales" else ev["bound"]

        findings.append({
            "type": f"{_LABEL[key]}偏离行业预警区间（待核）",
            "detail": (
                f"本企业{_LABEL[key]}为 {detail_value}{unit}，{direction}行业"
                f"参考预警区间（{bound_disp}{unit}）。"
                f"该偏离可能由经营模式、行业周期、出口占比、税收优惠等合理因素造成，"
                f"也可能指向收入隐匿、成本虚列或进项异常，须结合业务实质核实。"
            ),
            "level": "中风险",
            "score": 5,
            "tax_type": "增值税" if key == "vat_burden" else "企业所得税",
            "domain": "行业对标",
            "policy_ref": "",
            "suggestion": f"请说明{_LABEL[key]}偏离的原因，并提供同期行业可比资料、"
                          f"经营模式说明及适用税收优惠备案资料。",
            "items": [{"name": "行业可比资料与经营模式说明", "status": "待补充"},
                      {"name": "适用税收优惠备案资料", "status": "待补充"}],
            "evidence": [f"{_LABEL[key]}={detail_value}{unit}", f"行业区间 {low}~{high}"],
            "needs_material": ["行业可比资料与经营模式说明", "适用税收优惠备案资料"],
            "_industry": matched or "通用",
            "_indicator": key,
            "_actual": value,
            "_range": [low, high],
            "_benchmark_source": source,
            "_detection_method": "计算企业实际指标 → 与同行业参考预警区间比对 → 偏离即列为待核线索",
            "_unconfirmed": True,
        })
    return findings
