# -*- coding: utf-8 -*-
"""编号服务 —— 风险/证据/资料缺口/法规/附件/索引/整改台账/底稿 编号的唯一权威。

WB-TRISK-2026-001 §3.2「编号服务」+ §3.3「底稿编号规则」的唯一实现。
规则全部来自 `config/numbering.json`；**新增编号类型只需在该表加一行**，不需要改本模块。

铁律
----
1. **不得跳号、不得重号**：连续编号从 1 起、逐项 +1，且 `max(seq) == 项数`。
2. **不得各处自行拼接**：任何模块要编号必须经本模块 `make()` / `next()`。
3. **法规编号不含企业代码与期间**（法规是全局对象，不是本企业事实），按税种分段。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

__all__ = [
    "NumberingService",
    "ContinuityIssue",
    "validate_continuity",
    "load_rules",
    "VERSION",
]

VERSION = "1.0.0"
_ROOT = Path(__file__).resolve().parent.parent
_CFG = _ROOT / "config" / "numbering.json"
_CACHE: Optional[Dict[str, Any]] = None
_LOAD_ERRORS: List[str] = []


def load_rules() -> Dict[str, Any]:
    """读编号规则表；读不出时返回空表并留痕（不静默给默认值）。"""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    try:
        with open(_CFG, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict) or not data.get("rules"):
            _LOAD_ERRORS.append(f"{_CFG} 缺 rules 键")
            data = {}
    except Exception as exc:  # noqa: BLE001 —— 留痕后返回空表
        _LOAD_ERRORS.append(f"读 {_CFG} 失败：{exc}")
        data = {}
    _CACHE = data
    return _CACHE


def load_errors() -> List[str]:
    load_rules()
    return list(_LOAD_ERRORS)


class NumberingService:
    """某个企业某个期间的一次编号会话。"""

    def __init__(self, company_code: Any = "", period: Any = "", *, rules: Optional[Dict[str, Any]] = None):
        self.rules_cfg = rules if isinstance(rules, dict) else load_rules()
        self.connector = str(self.rules_cfg.get("connector") or "-")
        self.company_code = self._norm_company(company_code)
        self.period = self._norm_period(period)
        self.rules: Dict[str, Dict[str, Any]] = dict(self.rules_cfg.get("rules") or {})
        self._counters: Dict[str, int] = {}
        self.errors: List[str] = []

    # ------------------------------------------------------------ 归一
    def _norm_company(self, raw: Any) -> str:
        spec = self.rules_cfg.get("company_code") or {}
        if isinstance(raw, dict):
            for k in list(spec.get("aliases") or []) + [spec.get("id_key"), "company_id"]:
                if k and raw.get(k):
                    raw = raw[k]
                    break
        s = re.sub(r"\s+", "", str(raw or ""))
        if (spec.get("normalize") or "").startswith("upper"):
            s = s.upper()
        return s or "NA"

    def _norm_period(self, raw: Any) -> str:
        """期间归一 —— 薄转发唯一权威 `engine/findingkit.month_key`。

        ★ 2026-10-08 冗余收敛：旧实现「去分隔符取前 6 位」对个位月份必然算错
        （'2025/1/15' → '202511'），属伪归一化（闸门 `check_pseudo_period_norm` 报 ERROR）。
        别名解析（dict 取值）与配置兜底保留在本层；期间键本身交由 findingkit 计算。
        """
        spec = self.rules_cfg.get("period") or {}
        if isinstance(raw, dict):
            for k in spec.get("aliases") or []:
                if raw.get(k):
                    raw = raw[k]
                    break
        from engine.findingkit import month_key
        return month_key(raw) or str(spec.get("fallback") or "000000")

    # ------------------------------------------------------------ 生成
    def make(self, kind: str, seq: int, *, tax_code: str = "") -> str:
        """纯格式化：不改变计数器。"""
        spec = self.rules.get(kind)
        if not spec:
            self.errors.append(f"make: 未登记的编号类型 {kind!r}（见 config/numbering.json rules）")
            return ""
        width = int(spec.get("seq_width") or 3)
        prefix = str(spec.get("prefix") or kind.upper())
        seq_s = str(int(seq)).zfill(width)
        if kind == "law":
            tc = (tax_code or "OTH").upper()
            return self.connector.join([prefix, tc, seq_s])
        return self.connector.join([prefix, self.company_code, self.period, seq_s])

    def next(self, kind: str, *, tax_code: str = "") -> str:
        """自增取号。"""
        self._counters[kind] = self._counters.get(kind, 0) + 1
        return self.make(kind, self._counters[kind], tax_code=tax_code)

    def allocate(self, kind: str, count: int, *, tax_code: str = "") -> List[str]:
        return [self.next(kind, tax_code=tax_code) for _ in range(max(0, int(count)))]

    def workpaper_no(self, version: Any = 1) -> str:
        """总底稿号：WB-TR-<企业代码>-<期间>-<版本>。"""
        return self.make("workpaper", int(version or 1))

    def reset(self) -> None:
        self._counters.clear()

    # ------------------------------------------------------------ 解析/校验
    def parse(self, number: Any) -> Optional[Dict[str, Any]]:
        s = str(number or "").strip()
        if not s:
            return None
        for kind, spec in self.rules.items():
            prefix = str(spec.get("prefix") or "")
            if not prefix or not s.startswith(prefix + self.connector):
                continue
            rest = s[len(prefix) + len(self.connector):]
            if kind == "law":
                m = re.match(r"^([A-Z]+)" + re.escape(self.connector) + r"(\d+)$", rest)
                if m:
                    return {"kind": kind, "tax_code": m.group(1), "seq": int(m.group(2)), "raw": s}
                continue
            m = re.match(r"^(.*?)" + re.escape(self.connector) + r"(\d+)$", rest)
            if m:
                return {"kind": kind, "body": m.group(1), "seq": int(m.group(2)), "raw": s}
        return None

    def seq_of(self, number: Any) -> Optional[int]:
        p = self.parse(number)
        return p.get("seq") if p else None

    def covered_kinds(self) -> List[str]:
        return sorted(self.rules.keys())


class ReportNumbering:
    """报告正文引用层的短编号（R/C/F/D/S/L/T）。

    薄转发到 config/numbering.json 的 report_layer 段——与底稿层 WB-* 共用同一份配置源，
    避免『编号规则多头维护』。禁止任何模块自行拼接短号字符串。
    """

    LAYER = "report_layer"

    def __init__(self, *, rules: Optional[Dict[str, Any]] = None) -> None:
        cfg = rules if isinstance(rules, dict) else load_rules()
        layer = cfg.get(self.LAYER) or {}
        self.rules: Dict[str, Dict[str, Any]] = dict(layer.get("rules") or {})
        self.connector = str(layer.get("connector") or "-")
        self.ref_examples: List[str] = list((layer.get("cross_ref") or {}).get("examples") or [])
        self.errors: List[str] = []
        self._counters: Dict[str, int] = {}
        # 构成要件需按父级（风险事项）分别计数
        self._constituent: Dict[int, int] = {}

    # ------------------------------------------------------------ 生成
    def make(self, kind: str, seq: int, *, rseq: int = 0) -> str:
        spec = self.rules.get(kind)
        if not spec:
            self.errors.append(f"ReportNumbering.make: 未登记的短号类型 {kind!r}（见 numbering.json report_layer.rules）")
            return ""
        fmt = str(spec.get("format") or "{prefix}{seq}")
        try:
            return fmt.format(prefix=spec.get("prefix"), seq=int(seq), rseq=int(rseq), conn=self.connector)
        except Exception as exc:  # noqa: BLE001 —— 模板错误必须留痕，不静默返回空串
            self.errors.append(f"ReportNumbering.make({kind}): format 渲染失败 {exc}")
            return ""

    #: 需要按父级（风险事项）分别计数的编号类型——事实采用「按疑点分事实子库」
    PARENT_SCOPED = ("constituent", "fact")

    def next(self, kind: str, *, rseq: int = 0) -> str:
        if kind in self.PARENT_SCOPED:
            self._constituent[(kind, rseq)] = self._constituent.get((kind, rseq), 0) + 1
            return self.make(kind, self._constituent[(kind, rseq)], rseq=rseq)
        self._counters[kind] = self._counters.get(kind, 0) + 1
        return self.make(kind, self._counters[kind])

    def allocate(self, kind: str, count: int) -> List[str]:
        return [self.next(kind) for _ in range(max(0, int(count)))]

    # ------------------------------------------------------------ 引用串
    def ref(self, kind: str, seq: int, *, rseq: int = 0) -> str:
        spec = self.rules.get(kind)
        if not spec:
            self.errors.append(f"ReportNumbering.ref: 未登记的短号类型 {kind!r}")
            return ""
        fmt = str(spec.get("ref_format") or "")
        try:
            return fmt.format(seq=int(seq), rseq=int(rseq))
        except Exception as exc:  # noqa: BLE001
            self.errors.append(f"ReportNumbering.ref({kind}): ref_format 渲染失败 {exc}")
            return ""

    # ------------------------------------------------------------ 元信息
    def kinds(self) -> List[str]:
        return sorted(self.rules.keys())

    def cn_of(self, kind: str) -> str:
        return str((self.rules.get(kind) or {}).get("cn") or kind)

    def scope_of(self, kind: str) -> str:
        return str((self.rules.get(kind) or {}).get("scope") or "")

    def reset(self) -> None:
        self._counters.clear()
        self._constituent.clear()


class ContinuityIssue:
    """编号连续性问题（供门禁 B2 使用）。"""

    def __init__(self, code: str, message: str, *, severity: str = "ERROR", sample: Any = None) -> None:
        self.code = code
        self.message = message
        self.severity = severity
        self.sample = sample

    def to_dict(self) -> Dict[str, Any]:
        return {"code": self.code, "message": self.message, "severity": self.severity, "sample": self.sample}

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ContinuityIssue {self.code}: {self.message}>"


def validate_continuity(
    seqs: Sequence[Any],
    *,
    total: Optional[int] = None,
    start_at: int = 1,
    allow_gap: bool = False,
    allow_duplicate: bool = False,
    label: str = "编号",
) -> List[ContinuityIssue]:
    """校验编号序列：起点、连续性、重复、`max == total`。

    入参 `seqs` 可含 None（表示该项未编号），会被单独报出。
    """
    issues: List[ContinuityIssue] = []
    nums: List[int] = []
    for i, s in enumerate(seqs, 1):
        if s is None or s == "":
            if not allow_gap:
                issues.append(
                    ContinuityIssue("MISSING_NUMBER", f"{label}：第 {i} 项未编号", sample=i)
                )
            continue
        try:
            nums.append(int(s))
        except Exception:  # noqa: BLE001
            issues.append(ContinuityIssue("BAD_NUMBER", f"{label}：第 {i} 项编号无法解析：{s!r}", sample=s))

    if not nums:
        return issues

    if len(set(nums)) != len(nums) and not allow_duplicate:
        # 注意：不能在推导式里引用同一行赋值的变量（会 UnboundLocalError）
        _seen: set = set()
        _dup: set = set()
        for _n in nums:
            if _n in _seen:
                _dup.add(_n)
            _seen.add(_n)
        issues.append(ContinuityIssue("DUPLICATE", f"{label}：存在重复编号 {sorted(_dup)}", sample=sorted(_dup)))

    lo, hi = min(nums), max(nums)
    if lo != start_at and not allow_gap:
        issues.append(
            ContinuityIssue("BAD_START", f"{label}：起点应为 {start_at}，实际最小为 {lo}", sample=lo)
        )
    missing = [n for n in range(start_at, hi + 1) if n not in set(nums)]
    if missing and not allow_gap:
        issues.append(ContinuityIssue("GAP", f"{label}：缺号 {missing}", sample=missing))

    expected = int(total) if total is not None else len(seqs)
    if hi != expected:
        issues.append(
            ContinuityIssue(
                "MAX_MISMATCH",
                f"{label}：最大编号 {hi} 与项数 {expected} 不一致（编号必须 1..N 一一对应）",
                sample={"max": hi, "count": expected},
            )
        )
    return issues
