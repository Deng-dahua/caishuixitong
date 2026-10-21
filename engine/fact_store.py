# -*- coding: utf-8 -*-
"""全局事实库（SSOT）—— 金额/人数/笔数/日期/税种/企业名的唯一登记口径。

WB-TRISK-2026-001 §2「单一事实源」+ §3.2「金额口径登记表」的唯一权威实现。

设计铁律（与本项目既有约定一致）
--------------------------------
1. **同一事实只有一个权威值**：键为 `(kind, label, period, scope)`。同键重复登记且值不同 ⇒
   记 `FactConflict`（不静默覆盖、不静默取最大/最小），由门禁 B1 阻断输出。
2. **多口径必须显式登记**：全口径与剔除口径是**两个不同 scope 的事实**，必须同时声明
   `related`（同一分组键）与 `scope_note`，否则视为冲突。这样「1,734,859.35（全口径）」
   与「227,659.35（剔除后）」不再打架，而是被强制并列展示。
3. **取不到就说明取不到**：解析失败返回 `None`（复用 `engine.numparse.to_number_checked`
   的「不返回 0」约定），绝不默认 0。
4. **不做静默兜底**：任何异常都留痕到 `FactStore.errors`，并由门禁读取。

不复制既有唯一权威：数值解析用 `engine.numparse`，等级归一用 `engine/risk_levels`。
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from engine import numparse
from engine import risk_levels

__all__ = [
    "KINDS",
    "SCOPES",
    "Fact",
    "FactConflict",
    "FactStore",
    "declare_into",
    "get_store",
    "KIND_AMOUNT",
    "KIND_COUNT",
    "KIND_RATIO",
    "KIND_DATE",
    "KIND_TAX",
    "KIND_ENTITY",
    "KIND_LEVEL",
    "KIND_TEXT",
]

VERSION = "1.0.0"

KIND_AMOUNT = "amount"      # 金额（元）
KIND_COUNT = "count"        # 人数/笔数/张数/份数/项数
KIND_RATIO = "ratio"        # 比例/占比
KIND_DATE = "date"          # 日期/月份
KIND_TAX = "tax"            # 税种
KIND_ENTITY = "entity"      # 企业名/统一社会信用代码/交易对手
KIND_LEVEL = "level"        # 风险等级
KIND_TEXT = "text"          # 其他文本事实（摘要、结论词等）

KINDS: Tuple[str, ...] = (
    KIND_AMOUNT, KIND_COUNT, KIND_RATIO, KIND_DATE, KIND_TAX, KIND_ENTITY, KIND_LEVEL, KIND_TEXT,
)

#: 口径：全口径 / 剔除口径。**不是**「含税/不含税」（那是 `tax_inclusive`），两者正交。
SCOPE_FULL = "full"
SCOPE_ADJUSTED = "adjusted"
SCOPES: Tuple[str, ...] = (SCOPE_FULL, SCOPE_ADJUSTED)

_KIND_ABBR = {
    KIND_AMOUNT: "AMT", KIND_COUNT: "CNT", KIND_RATIO: "RAT", KIND_DATE: "DAT",
    KIND_TAX: "TAX", KIND_ENTITY: "ENT", KIND_LEVEL: "LVL", KIND_TEXT: "TXT",
}

#: 同键同值归一的浮点容差（金额 1 分）
_TOLERANCE = 0.005


def _norm_label(label: Any) -> str:
    """标签归一：去空白、去全半角差异、去尾部标点。"""
    s = str(label or "")
    s = s.replace("\u3000", " ").strip()
    s = re.sub(r"[\s、,，。;；:：]+$", "", s)
    return re.sub(r"\s+", "", s)


def _norm_period(period: Any) -> str:
    """期间归一化 —— 薄转发唯一权威 `engine/findingkit.month_key`。

    ★ 2026-10-08 冗余收敛：旧实现「去分隔符取前 6 位」对**个位月份**必然算错
    （'2025/1/15' → '202511'），且函数名承诺"归一化"却只截断不解析（闸门
    `check_pseudo_period_norm` 报 ERROR）。改为转发 findingkit.month_key：
    按 Y/M 两段取并补零（→ '202501'），对不可解析输入退回温和兜底。
    """
    from engine.findingkit import month_key
    return month_key(period)


def _same_value(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= _TOLERANCE
    return str(a).strip() == str(b).strip()


@dataclass
class Fact:
    """一条被登记的事实。"""

    fact_id: str
    kind: str
    label: str
    value: Any
    unit: str = ""
    scope: str = SCOPE_FULL
    tax_inclusive: Optional[bool] = None
    period: str = ""
    source: str = ""
    derivation: str = ""
    related: str = ""
    scope_note: str = ""
    owner: str = ""
    declared_at: str = ""
    raw: Any = None

    def as_index_row(self) -> Dict[str, Any]:
        """归档用「金额索引」行（字段见 config/archive_spec.json → indexes[amount]）。"""
        return {
            "fact_id": self.fact_id,
            "label": self.label,
            "value": self.value,
            "unit": self.unit,
            "scope": "全口径" if self.scope == SCOPE_FULL else "剔除口径",
            "tax_inclusive": (
                "未登记" if self.tax_inclusive is None else ("含税" if self.tax_inclusive else "不含税")
            ),
            "period": self.period,
            "source": self.source,
            "derivation": self.derivation,
        }

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FactConflict:
    """同键不同值（或口径未声明）的冲突记录。"""

    key: Tuple[str, str, str]
    facts: List[Fact] = field(default_factory=list)
    reason: str = ""

    def describe(self) -> str:
        vals = " / ".join(str(f.value) for f in self.facts)
        return f"『{self.key[1]}』（{self.key[0]}, 期间={self.key[2] or '未登记'}）出现多个值：{vals}；{self.reason}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.key[0],
            "label": self.key[1],
            "period": self.key[2],
            "values": [f.value for f in self.facts],
            "fact_ids": [f.fact_id for f in self.facts],
            "reason": self.reason,
            "describe": self.describe(),
        }


class FactStore:
    """全局事实库。一次分析一个实例；也可挂到 report_data 上跨阶段共享。"""

    def __init__(self, *, company_code: str = "", period: str = "") -> None:
        self.company_code = str(company_code or "")
        self.period = _norm_period(period)
        self._facts: Dict[str, Fact] = {}                      # fact_id → 最新一条
        self._by_key: Dict[Tuple[str, str, str], List[Fact]] = {}  # (kind,label,period) → 全部（含覆盖）
        self._revisions: List[Dict[str, Any]] = []             # 同键覆盖留痕（不静默丢）
        self.errors: List[str] = []
        self.conflicts_cache: Optional[List[FactConflict]] = None

    # ------------------------------------------------------------ 登记
    def declare(
        self,
        *,
        kind: str,
        label: Any,
        value: Any,
        unit: str = "",
        scope: str = SCOPE_FULL,
        tax_inclusive: Optional[bool] = None,
        period: Any = "",
        source: str = "",
        derivation: str = "",
        related: str = "",
        scope_note: str = "",
        owner: str = "",
        raw: Any = None,
    ) -> str:
        """登记一条事实，返回 `fact_id`。

        - 解析失败（value 为 None / 无法转数）⇒ 仍登记，值记 `None`，不填 0。
        - 同键同值 ⇒ 幂等（返回既有 fact_id，不新增）。
        - 同键不同值 ⇒ 新增一条并在 `conflicts()` 中暴露（不覆盖）。
        """
        label_n = _norm_label(label)
        if not label_n:
            self.errors.append("declare: label 为空，已忽略")
            return ""
        kind = kind if kind in KINDS else KIND_TEXT
        per = _norm_period(period) or self.period

        parsed, ok = self._coerce(kind, value)
        if not ok:
            self.errors.append(f"declare: 值无法解析 kind={kind} label={label_n} raw={value!r}（按未取值登记，未默认 0）")

        fid = self._make_id(kind, label_n, per, scope)
        now = datetime.now().isoformat(timespec="seconds")
        new = Fact(
            fact_id=fid, kind=kind, label=label_n, value=parsed, unit=unit, scope=scope,
            tax_inclusive=tax_inclusive, period=per, source=source, derivation=derivation,
            related=related, scope_note=scope_note, owner=owner, declared_at=now, raw=value,
        )
        old = self._facts.get(fid)
        if old is not None and _same_value(old.value, parsed):
            return fid  # 幂等
        key = (kind, label_n, per)
        group = self._by_key.setdefault(key, [])
        if old is not None:
            # ★同键不同值：**保留被覆盖的一条**，否则冲突会被静默丢掉（本模块曾因此漏判）
            group.append(old)
            self._revisions.append({
                "fact_id": fid, "at": now, "from": old.value, "to": parsed,
                "note": "同键不同值覆盖，已保留原值以便门禁判冲突",
            })
        if not any(_same_value(f.value, parsed) for f in group):
            group.append(new)
        self._facts[fid] = new      # 最新值仍以 _facts 为准
        self.conflicts_cache = None
        return fid

    def _coerce(self, kind: str, value: Any) -> Tuple[Any, bool]:
        if value is None or value == "":
            return None, False
        if kind in (KIND_AMOUNT, KIND_COUNT, KIND_RATIO):
            n, ok = numparse.to_number_checked(value, default=0.0)
            return (n if ok else None), ok
        if kind == KIND_LEVEL:
            return risk_levels.normalize(value), True
        return value, True

    def _make_id(self, kind: str, label: str, period: str, scope: str) -> str:
        seed = f"{kind}|{label}|{period}|{scope}".encode("utf-8")
        h = hashlib.sha1(seed).hexdigest()[:10].upper()
        return f"F-{_KIND_ABBR.get(kind, 'TXT')}-{period or 'NA'}-{h}"

    # ------------------------------------------------------------ 读取
    def get(self, fact_id: str) -> Optional[Fact]:
        return self._facts.get(fact_id)

    def value_of(self, fact_id: str, default: Any = None) -> Any:
        f = self._facts.get(fact_id)
        return default if f is None else f.value

    def by_kind(self, kind: str) -> List[Fact]:
        return [f for f in self._facts.values() if f.kind == kind]

    def family(self, kind: str, label: Any, period: Any = "") -> List[Fact]:
        """同 (kind,label,period) 的全部事实（含不同 scope）。"""
        ln, per = _norm_label(label), (_norm_period(period) or self.period)
        return [f for f in self._facts.values() if f.kind == kind and f.label == ln and f.period == per]

    def labels(self, kind: Optional[str] = None) -> List[str]:
        return sorted({f.label for f in self._facts.values() if kind is None or f.kind == kind})

    def snapshot(self) -> List[Fact]:
        return list(self._facts.values())

    def amount_index_rows(self) -> List[Dict[str, Any]]:
        rows = [f.as_index_row() for f in self.by_kind(KIND_AMOUNT)]
        return sorted(rows, key=lambda r: (-(r["value"] or 0), r["label"]))

    # ------------------------------------------------------------ 冲突
    def conflicts(self) -> List[FactConflict]:
        """同键不同值；或同键多 scope 但未两两声明 related ⇒ 冲突。

        注意：按 `_by_key` 判定（含被覆盖的历史值与多 scope 值），**不是**只看最新值
        —— 否则「后写的值把前值顶掉」会让冲突静默消失。
        """
        if self.conflicts_cache is not None:
            return self.conflicts_cache

        out: List[FactConflict] = []
        for key, facts in sorted(self._by_key.items()):
            if len(facts) < 2:
                continue
            vals = {str(f.value) for f in facts}
            if len(vals) == 1:
                continue  # 同值多口径不算冲突
            # 多口径合法条件：每个事实都声明了 related，且 related 一致
            relates = {f.related for f in facts}
            if "" not in relates and len(relates) == 1:
                continue  # 已显式声明为同一口径组
            reason = (
                "未声明口径分组（related 为空或各组不一致）——多值必须显式登记相互口径与差异原因"
            )
            out.append(FactConflict(key=key, facts=facts, reason=reason))
        self.conflicts_cache = out
        return out

    def revisions(self) -> List[Dict[str, Any]]:
        """同键覆盖留痕（供审计轨迹使用）。"""
        return list(self._revisions)

    # ------------------------------------------------------------ 序列化（★ 2026-10-21）
    def to_dict(self) -> Dict[str, Any]:
        """**可 JSON 序列化的快照**（报告出口用；不是内部状态导出）。

        ★ 为什么必须有它（2026-10-21 线上 500 根因）：
          `FactStore` 实例被挂到 `report_data["_fact_store"]`，而 `GET
          /api/tax-risk-docs/last-analysis` 直接 `return cached["report"]` ——
          FastAPI 的 `jsonable_encoder` 对非 dict/list 对象走 `vars(obj)` 分支，
          取出 `_by_key`（`Dict[Tuple[str,str,str], ...]`），
          `jsonable_encoder(key)` 把 tuple 转成 list 后拿去做字典键 ⇒
          `TypeError: unhashable type: 'list'`（encoders.py:297）⇒ 接口 500。
          **磁盘缓存看起来正常是假象**：落盘走 `runtime_storage._to_json_safe`，
          它对非原生类型 `return str(value)`，把实例洗成
          `"<engine.fact_store.FactStore object at 0x...>"`；只有**进程内原始对象**
          才带实例 ⇒ 分析完成后不重启，接口必崩。

          设计取舍：导出**两组**信息，缺一不可 ——
            ① `facts`：每个 `fact_id` 的**最新值**（`_facts`）；
            ② `groups`：**按 (kind,label,period) 分组的全部事实**（`_by_key`，
               含被覆盖的历史值）。若只导 ①，则「同键不同值」的冲突在重建后
            **静默消失**（实测：冲突从 1 降到 0）——事实级门禁（B1）会漏判。
          `groups` 的键用 **`[kind, label, period]` 的 list** 表示（**不用 tuple** ——
          tuple 键正是本次 500 的根因）。
          `conflicts_cache` 不导出（可由 `_by_key` 重算）。
        """
        return {
            "company_code": self.company_code,
            "period": self.period,
            "facts": [f.to_dict() for f in self._facts.values()],
            # ★ 分组快照：保留被覆盖的历史值，冲突才不会在重建后消失
            "groups": [
                {"key": [k[0], k[1], k[2]], "facts": [f.to_dict() for f in v]}
                for k, v in self._by_key.items()
            ],
            "revisions": list(self._revisions),
            "errors": list(self.errors),
            "conflicts": [c.to_dict() for c in self.conflicts()],
            "stats": self.stats(),
        }

    @classmethod
    def from_dict(cls, data: Any) -> Optional["FactStore"]:
        """从 `to_dict()` 的快照**重建**实例（供 reading 侧恢复能力）。

        解析失败返回 None（不抛）——调用方按"事实库未挂载"处理（与既有的
        `get_store(create=False)` 语义一致：拿不到就如实降级，不臆测）。
        """
        if not isinstance(data, dict) or "facts" not in data:
            return None
        try:
            st = cls(company_code=str(data.get("company_code") or ""),
                     period=str(data.get("period") or ""))

            def _mk(row: Any) -> Optional[Fact]:
                """快照行 → Fact。只传**真实存在**的字段：可选字段为 None 时让 dataclass
                默认值生效（`value` 例外 —— None 是合法值，表示"本轮未取得"，不得顶替）。"""
                if not isinstance(row, dict):
                    return None
                kw: Dict[str, Any] = {}
                for k in ("fact_id", "kind", "label", "value", "unit", "scope",
                          "tax_inclusive", "period", "source", "derivation",
                          "related", "scope_note", "owner", "declared_at", "raw"):
                    if k not in row:
                        continue
                    if row[k] is None and k not in ("value", "tax_inclusive", "raw"):
                        continue
                    kw[k] = row[k]
                try:
                    return Fact(**kw)
                except TypeError:
                    return None

            for row in (data.get("facts") or []):
                f = _mk(row)
                if f is not None:
                    st._facts[f.fact_id] = f

            # ★ 优先用 groups 重建 `_by_key`（保留被覆盖的历史值 ⇒ 冲突不丢）。
            #   旧快照无 groups 时回退：按 _facts 自行分组（会丢历史值，但至少可用）。
            groups = data.get("groups")
            if isinstance(groups, list) and groups:
                for g in groups:
                    if not isinstance(g, dict):
                        continue
                    k = g.get("key")
                    if not (isinstance(k, (list, tuple)) and len(k) == 3):
                        continue
                    tkey = (str(k[0]), str(k[1]), str(k[2]))
                    bucket: List[Fact] = []
                    for row in (g.get("facts") or []):
                        f = _mk(row)
                        if f is not None:
                            bucket.append(f)
                    if bucket:
                        st._by_key[tkey] = bucket
            else:
                for f in st._facts.values():
                    tkey = (f.kind, _norm_label(f.label),
                            _norm_period(f.period) or st.period)
                    st._by_key.setdefault(tkey, []).append(f)

            st._revisions = [r for r in (data.get("revisions") or []) if isinstance(r, dict)]
            st.errors = [str(e) for e in (data.get("errors") or [])]
            st.conflicts_cache = None      # 让 conflicts() 按重建后的 _by_key 重算
            return st
        except Exception:                  # noqa: BLE001 —— 快照损坏时如实降级，不抛
            return None

    def conflicting_labels(self) -> List[str]:
        return sorted({c.key[1] for c in self.conflicts()})

    def digest(self) -> str:
        """事实库指纹（用于版本对比）。"""
        parts = sorted(f"{f.fact_id}={f.value}" for f in self._facts.values())
        return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()

    def stats(self) -> Dict[str, Any]:
        by_kind: Dict[str, int] = {}
        for f in self._facts.values():
            by_kind[f.kind] = by_kind.get(f.kind, 0) + 1
        return {
            "total": len(self._facts),
            "by_kind": by_kind,
            "conflicts": len(self.conflicts()),
            "unparsed": sum(1 for f in self._facts.values() if f.value is None),
            "errors": len(self.errors),
            "digest": self.digest(),
        }

    def render(self, fact_id: str) -> str:
        """把一个事实渲染为文本片段（章节引用事实的唯一出口）。"""
        f = self._facts.get(fact_id)
        if f is None:
            self.errors.append(f"render: 未登记的 fact_id={fact_id}")
            return ""
        if f.value is None:
            return "（该数值本轮未取得，未参与测算）"
        if f.kind == KIND_AMOUNT and isinstance(f.value, (int, float)):
            return f"{f.value:,.2f}"
        if f.kind == KIND_RATIO and isinstance(f.value, (int, float)):
            return f"{f.value * 100:.2f}%"
        return str(f.value)


# ---------------------------------------------------------------- 便捷函数
_STORE_KEY = "_fact_store"


def get_store(container: Any, *, create: bool = False, company_code: str = "", period: str = "") -> Optional[FactStore]:
    """从 `report_data` 等 dict 上取事实库；`create=True` 时不存在则创建。

    ★ 2026-10-21：支持**快照 dict**（`to_dict()` 的产物）。
      报告出口为防 FastAPI 序列化崩溃，会把实例替换成快照（见 `FactStore.to_dict`）。
      若本函数只认实例，则 workpaper / quality_gates 等读路径在**跨请求**（读缓存）
      时会看到 dict 而判"事实库未挂载"，能力静默消失。故此处识别快照并**重建实例**，
      保证"出口降级"不影响任何读取方的能力。
    """
    if not isinstance(container, dict):
        return None
    st = container.get(_STORE_KEY)
    if isinstance(st, FactStore):
        return st
    if isinstance(st, dict):                      # 快照 → 重建（跨请求读路径）
        rebuilt = FactStore.from_dict(st)
        if rebuilt is not None:
            container[_STORE_KEY] = rebuilt       # 就地升级为实例，后续调用零开销
            return rebuilt
    if not create:
        return None
    st = FactStore(company_code=company_code, period=period)
    container[_STORE_KEY] = st
    return st


def declare_into(container: Dict[str, Any], **kw: Any) -> str:
    """在 `container` 上登记事实（自动建库）。"""
    st = get_store(container, create=True, company_code=kw.pop("company_code", ""), period=kw.get("period", ""))
    assert st is not None
    return st.declare(**kw)
