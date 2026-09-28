# -*- coding: utf-8 -*-
"""
红线行业基准解析器 —— 红线构成要件中"与行业基准偏离"类要件的**唯一动态取值源**
==================================================================================

为什么单独建这个模块（不重复实现基准计算，2026-09-28 收敛）
--------------------------------------------------------------------------------
本轮质量升级（B 类）发现：68 条红线中有 19 条构成要件写"毛利率偏离行业均值"/
"金额重大需结合行业水平综合研判"之类软尾注，但**数值从不落地**。

★ 单一权威收敛（关键，避免多头维护）：
  行业基准的**数值与口径**唯一来自 `engine/industry_benchmark.py`
  （它已从 `static/industry_data.json` 派生 `INDUSTRY_BENCHMARKS`，含
  实测校准 > 行业档案 > 通用参考 > 宽松兜底 的优先级与 细分行业→门类 对齐表）。
  本模块**不重新实现任何基准计算**，只做三件事：
    ① `BENCHMARK_REFS`：红线 id → 对标指标（唯一登记点，新增同类对象只加一行）；
    ② 把红线的中文指标（毛利率/税负率/期间费用率/进销比/人均营收）映射到
       industry_benchmark 的口径并取数；
    ③ `benchmark_note(rid, industry)`：生成可直读、带口径声明的基准说明句。
  全程不写死任何数字；行业未确定时如实返回"须按实际行业取值"，绝不编造区间。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

# ★ 复用行业基准单一权威（数值/口径均来自此处，不重复实现）
from engine.industry_benchmark import (
    resolve_benchmark as _ib_resolve,
    _METRIC_ZH_TO_EN,
)
from engine.industry_resolver import load_industry_data

# 中文指标键（与 industry_data.json 严格一致；人均营收仅本模块对标用，单独取数）
_METRIC_KEYS = ("毛利率", "净利率", "税负率", "进销比", "人均营收(万)", "期间费用率")
_PCT_METRICS = {"毛利率", "净利率", "税负率", "期间费用率"}


def metric_keys() -> List[str]:
    """全部合法指标键（供闸门校验，避免登记了库中不存在的指标）。"""
    return list(_METRIC_KEYS)


# ── 红线 → 对标指标（唯一登记点）──────────────────────────────────────────────
# 仅登记"构成要件确实以行业基准为判定口径"的红线；不盲目铺满 68 条。
# 取值逻辑：销项/采购配比 → 进销比；费用类 → 期间费用率；毛利类 → 毛利率；
#          税负/所得类 → 税负率；工资/资金拆借/损失类规模 → 人均营收。
BENCHMARK_REFS: Dict[str, str] = {
    "RL-VAT-001": "进销比",     # 无对应进项来源的销售额
    "RL-VAT-002": "进销比",     # 无对应销项实现的进项税额
    "RL-VAT-003": "税负率",     # 增值税税负异常
    "RL-VAT-005": "税负率",     # 税负率横向偏离
    "RL-INC-001": "税负率",     # 申报收入与开票/账面差异
    "RL-INC-002": "税负率",     # 两税收入差异
    "RL-COST-002": "期间费用率",  # 咨询费等无形服务支出重大
    "RL-COST-004": "期间费用率",  # 年末费用占比偏高
    "RL-COST-005": "进销比",     # 未付款金额占比
    "RL-INV-001": "毛利率",      # 毛利率偏离行业均值
    "RL-INV-002": "期间费用率",  # 不动销存货占用（以期间费用率区间作占用参照）
    "RL-INV-003": "进销比",      # 异地采购占比异常
    "RL-PAY-001": "人均营收(万)",    # 工资列支金额重大
    "RL-CIT-001": "税负率",      # 企业所得税税负异常
    "RL-CIT-002": "税负率",      # 成本费用列支异常
    "RL-CIT-006": "税负率",      # 应纳税所得额差异
    "RL-PTY-001": "进销比",      # 关联方交易价格偏离
    "RL-PTY-002": "进销比",      # 重大购销交易
    "RL-PTY-003": "人均营收(万)",    # 关联方大额资金拆借
    "RL-PTY-004": "期间费用率",  # 委托加工费支出重大
    "RL-OTH-001": "人均营收(万)",    # 资金/票据链路断裂涉及金额重大
    "RL-OTH-006": "期间费用率",  # 折扣折让比例异常
    "RL-SPT-008": "人均营收(万)",    # 资产损失金额异常
}


def _fmt(metric: str, val: float) -> str:
    """按指标类型格式化数值（百分比带 %，金额/倍数原值）。"""
    if metric in _PCT_METRICS:
        return f"{val:.1f}%"
    if metric == "人均营收(万)":
        return f"{val:.0f}万"
    return f"{val:.3f}"


def resolve_redline_benchmark(industry: Optional[str], metric: str
                      ) -> Optional[Dict[str, object]]:
    """按行业取基准区间（委托 industry_benchmark 单一权威取数）。

    返回 `{"lo","hi","mid","industry","metric","source","reliable"}` 或
    `None`（行业不在库中 / 指标不存在 / 行业未确定）。
    source/reliable 用于报告自报口径（R4 铁律）。
    """
    if metric not in _METRIC_KEYS:
        return None

    # ★ 铁律：行业未确定时**绝不**静默套用宽松兜底编造区间，明确返回 None。
    ind = str(industry or "").strip()
    if not ind:
        return None

    if metric == "人均营收(万)":
        # 人均营收仅作规模对标，industry_benchmark 未纳入横向比对指标；
        # 直接读同一数据源 industry_data.json（与 industry_benchmark 同源，非另起炉灶）。
        data = load_industry_data()
        bm = (data.get("benchmarks") or {}).get(ind) or (data.get("benchmarks_coarse") or {}).get(ind)
        rec = (bm or {}).get(metric) if bm else None
        if not isinstance(rec, (list, tuple)) or len(rec) < 2:
            return None
        lo, hi = float(rec[0]), float(rec[1])
        mid = float(rec[2]) if len(rec) >= 3 else round((lo + hi) / 2, 4)
        return {"lo": lo, "hi": hi, "mid": mid, "industry": ind,
                "metric": metric, "source": "industry_data.json",
                "reliable": "通用参考值（非税务机关官方口径）"}

    # 其余 4 个比率/百分比指标：委托 industry_benchmark 单一权威
    en = _METRIC_ZH_TO_EN.get(metric)
    if not en:
        return None
    matched, bench, source = _ib_resolve(ind)
    if not matched:
        return None
    pair = bench.get(en)
    if not isinstance(pair, (list, tuple)) or len(pair) < 2 or pair[0] is None:
        return None
    lo, hi = float(pair[0]), float(pair[1])
    mid = round((lo + hi) / 2, 4)
    return {"lo": lo, "hi": hi, "mid": mid, "industry": matched,
            "metric": metric, "source": f"industry_benchmark（{source}）",
            "reliable": "通用参考值（非税务机关官方口径）"}


def benchmark_note(rid: str, industry: Optional[str] = None) -> Dict[str, object]:
    """生成可直读、带口径声明的基准说明。

    返回 `{"rid","metric","resolved":bool,"text":str,"range":[...]|None}`。
    resolved=False 时不编造数字，只说明"须按实际行业从 industry_data.json 取值"。
    """
    metric = BENCHMARK_REFS.get(rid)
    if not metric:
        return {"rid": rid, "metric": None, "resolved": False, "text": "", "range": None}
    b = resolve_redline_benchmark(industry, metric)
    if b is None:
        text = (f"该项以行业基准「{metric}」区间为参照，须按实际所属行业从 "
                f"industry_data.json 取对应区间（通用参考值，非税务机关官方口径）")
        return {"rid": rid, "metric": metric, "resolved": False, "text": text, "range": None}
    rng_txt = f"[{_fmt(metric, b['lo'])}~{_fmt(metric, b['hi'])}]"
    text = (f"以行业基准「{metric}」区间{rng_txt}为参照"
            f"（来源 {b['source']}，{b['reliable']}）")
    return {"rid": rid, "metric": metric, "resolved": True,
            "text": text, "range": [b["lo"], b["hi"], b["mid"]]}


def benchmark_refs() -> Dict[str, str]:
    """返回红线→指标登记表的副本（供闸门与渲染消费）。"""
    return dict(BENCHMARK_REFS)
