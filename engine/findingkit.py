"""finding 构造与期间键的**唯一权威**（2026-09-25）

═══════════════════════════════════════════════════════════════════════════════
为什么收敛
═══════════════════════════════════════════════════════════════════════════════
· `_mk(...)` 在 `deduction_limit_detector` / `invoice_pattern_detector` /
  `structure_mismatch_detector` **逐字节重复三份** —— 一旦有人只改其中一份加字段，
  另两个模块产出的 finding 就会**缺字段**，下游渲染/治理按字段读取时行为不一致。
· `_month_key(...)` 在 `chain_executor` / `rule_gate` / `threshold_scanner`
  **三份语义相同但各写一遍**（都是"去分隔符取前 6 位"）。
· **日期→月份**在 6 处各写一遍（`findingkit` / `red_team` / `verified_rule_engine`×2 /
  `domain_analysis`×4 / `monthly_reconcile`），其中"去分隔符取前 6 位"那套对**个位月份
  必然算错**：`2025/1/15 → 202511`、`2025-1-5 → 202515`（月份 15 不存在）、
  `2026-1-31 → 202613`。Excel 导出日期列普遍是个位月，故所有"按月对比/月度波动"
  结论都建立在**被拆散的错误月份桶**上（实测 1 月被拆成 `202511` 与 `202512`）。

原则 F1：**产出结构（finding 字段集）必须只有一处定义**。新增字段只在此加，三处自动同步。
原则 F1b：**同一概念只允许一处实现**。`month_key`（机器分组键 `YYYYMM`）与
  `normalize_month`（展示键 `YYYY-MM`）是本文件导出的两个期间权威，任何模块需要
  月份都必须调用它们，不得自行 replace+切片。
原则 F3：语义不同的同名函数（如 `_finding` 在两处签名不同）**改名区分**，不硬合并。
"""

from __future__ import annotations

import re
from typing import Any, Optional

# ★ finding 的字段集合在此**唯一**定义（新增字段只改这里）
FINDING_FIELDS = (
    "type", "level", "score", "detail", "description", "how_found",
    "tax_impact", "policy_ref", "suggestion", "category", "source_chain",
    "redline_id", "indicator", "indicator_value",
)


# ★ 发现身份键在此**唯一**定义。原先 `output_governance.seal_governed_findings`
#   （封印去重）与 `self_learning`（门禁跨轮豁免记账）**各手写一份**同样的
#   「scene_fact_id → fact_id → type」取值 ⇒ 两处会各自漂移；本函数是唯一权威。
_IDENTITY_FIELDS = ("scene_fact_id", "fact_id", "type")


def finding_identity(finding: Any) -> str:
    """一条发现的稳定身份键；三条字段都取不到时返回 ""（调用方据此判定不可跟踪）。

    字段取值与 `seal_governed_findings` 现网行为逐字节一致（换成本函数后封印去重
    结果不变），只是把「怎么取身份」收敛到一处。
    """
    if not isinstance(finding, dict):
        return ""
    for _k in _IDENTITY_FIELDS:
        _v = finding.get(_k)
        if _v is None or _v == "":
            continue
        return str(_v).strip()
    return ""


def make_finding(type_, level, score, detail, description, how_found, tax_impact,
                 policy_ref, suggestion, category, source_chain, redline_id,
                 indicator, value) -> dict:
    """构造一条 finding —— 全系统唯一实现（原先三份逐字节重复）。"""
    return {
        "type": type_, "level": level, "score": score,
        "detail": detail, "description": description, "how_found": how_found,
        "tax_impact": tax_impact, "policy_ref": policy_ref, "suggestion": suggestion,
        "category": category, "source_chain": source_chain,
        "redline_id": redline_id, "indicator": indicator, "indicator_value": value,
    }


# ★ 只认 19xx/20xx 的四位年 + 分隔符 + 1~2 位月（月后不得紧跟数字）
_MONTH_KEY_RE = re.compile(r"(19|20)(\d{2})\s*[-/.年月]\s*(\d{1,2})(?!\d)")


def month_key(date_like: Any, sep_chars: str = "-/.年") -> str:
    """把日期取成 `YYYYMM` 期间的键 —— 全系统唯一实现。

    ═══ 根因修复（2026-09-25）═══
    旧实现是"去分隔符后取前 6 位"，对**个位月份/个位日**必然算错：

        '2025/1/15' → 去分隔符 '2025115' → 取前 6 位 '202511'   ✗（应为 202501）
        '2025-1-5'  → '202515'  ← 月份 15 根本不存在             ✗
        '2026-1-31' → '202613'  ← 月份 13 不存在                ✗

    Excel 导出的日期列**普遍是个位月**（2025/1/15、2025.1.5），故这不是边角案例：
    同一月会被拆成多个桶（实测 red_team 把 1 月拆成 '202511' 与 '202512'），
    导致所有"按月对比/月度波动/月度差异"结论建立在错误分组上。

    同日历概念原先在 6 处各写一遍（findingkit / red_team / verified_rule_engine ×2 /
    domain_analysis ×4 / monthly_reconcile），其中 5 处带同一缺陷 → 已全部收敛到本函数。

    取月份的正确顺序：①带分隔符按 Y/M 两段取（个位月补零）→ ②纯数字 YYYYMM → ③兜底原行为。
    ⚠ 需"月份必须可信"的分组请用 `month_key_strict`（本函数③兜底会返回非 6 位原串）。
    """
    s = str(date_like or "").strip()
    if not s:
        return ""
    # ① 带分隔符：YYYY[-/.年]M —— 个位月必须补零
    m = _MONTH_KEY_RE.search(s)
    if m:
        mm = int(m.group(3))
        if 1 <= mm <= 12:
            return "%s%s%02d" % (m.group(1), m.group(2), mm)
    # ② 纯数字：YYYYMM[DD…] → 20250115 → 202501（月份非法则不认，交给兜底）
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) >= 6 and 1 <= int(digits[4:6]) <= 12:
        return digits[:6]
    # ③ 兜底：保持旧行为，不抛异常，未知格式仍可分组
    stripped = s
    for ch in sep_chars:
        stripped = stripped.replace(ch, "")
    stripped = stripped.strip()
    return stripped[:6]


def month_key_strict(date_like: Any) -> str:
    """同 `month_key`，但**只**返回可信的 6 位 `YYYYMM`，否则空串。

    用于"月份必须可信"的场景（按月汇总金额、按月对比差异、统计覆盖月数）——
    这些场景下把不可解析的日期塞进一个伪月份桶，会凭空造出一个"月"，污染结论。

    可信 = 6 位纯数字 **且** 后两位是 1~12 的真实月份（`202513` 这类兜底串必须拒绝，
    否则下游按 `int(key[4:6])` 取月份时会拿到 13 月）。
    """
    k = month_key(date_like)
    if len(k) == 6 and k.isdigit() and 1 <= int(k[4:6]) <= 12:
        return k
    return ""


def normalize_month(date_like: Any) -> str:
    """把日期标准化为 `YYYY-MM` —— 全系统唯一实现；取不到返回空串。

    ⚠ 与 `month_key` 的分工：本函数返回 `YYYY-MM`（给人看/做展示键），
    `month_key` 返回 `YYYYMM`（给机器做分组键）。两者**必须同源**，否则同一个
    日期会得到不同月份 —— 这正是本次收敛要消除的问题。

    覆盖：`2026-01-15` / `20260115` / `2026/1/15` / `2026年1月` / `2026-01` / `2026.1.5`
    （个位月自动补零）；月份非法（`202513`）或无法解析时返回空串。
    """
    s = str(date_like or "")
    m = re.search(r"(\d{4})\s*[-/年.]?\s*(\d{1,2})", s)
    if not m:
        return ""
    mm = int(m.group(2))
    return "%s-%02d" % (m.group(1), mm) if 1 <= mm <= 12 else ""


def cjk_bigrams(text: Any) -> set:
    """中文文本相邻 2-gram 集合（全系统唯一实现）。

    用途：「要素/证据 ↔ 发现正文」的**语义相关性**判定 —— 例如判断一条记账凭证的
    摘要「计提1月工资」是否与发现「工资多源对等逐月不匹配（2025-01）」相关。

    ★ 2026-10-01 收敛：此前 `enterprise_report._cjk_bigrams` 与
      `pipeline._cjk_bigrams` 各写一份（后者为证据相关性守卫新增），
      `tools/audit_consistency.py` 的跨模块分歧检查立刻报出「真实分歧」。
      现统一落在本模块，两侧一律转调（函数名保留以兼容既有引用）。
    """
    t = "".join(re.findall(r"[一-鿿]", str(text or "")))
    return set(t[i:i + 2] for i in range(len(t) - 1))
