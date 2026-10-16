"""P0-5 规则**加载器** —— 统一读取四种规则载体（**只读，不改任何判定**）。

★ 为什么要"统一加载"而不是"统一到一种格式"：本项目规则有**四个权威载体**，
  职责不同、都不能废（历史多起事故正是"把一个概念收敛成一处"而丢掉语义）：

    | 载体 | 位置 | 地位 | 说明 |
    |---|---|---|---|
    | Python（执行权威） | `engine/tax_redlines.py` · `verified_rule_engine.py` · 四个检测器模块 | **在库规则，真执行** | 规则主体 **176 条**（红线 91 + 已验证 85）；判定逻辑与护栏都在这里 |
    | JSON（候选权威） | `config/rulelist_v1|v11|v12.json` | **外部候选清单** | 460 条；含阈值 `params`（唯一权威在 `config/rulelist_*.json::params`） |
    | YAML（交换格式） | `rules_export/*.yaml` | **同源导出，非第二权威** | 由 `tools/export_rulelist_yaml.py` 从 JSON 生成；`wired: false` |
    | DSL（条件表达式） | `engine/rule_dsl.py` + `config/rule_dsl_scope.json` | **表达力边界登记** | T-6 裁定 `NOT_EQUIVALENT` ⇒ **不切换**；只登记边界与字段缺口 |

  ⇒ 加载器**只做"读 + 规范化"**：把四种载体的条目收敛成同一个 `RuleRecord` 形状，
    供目录/接口/前端消费。**不合并、不改写、不切换**（那是 T-6 的边界）。

★ 关于"规则与代码分离"（任务书约束）：
  本项目对这一条有**既有裁定**：`rules_export/*.yaml` 是**交换格式**（同源双份），
  **执行权威仍是 Python**；T-6 实测候选 DSL 与 Python 判据**有 8/12 用例分歧**
  （漏报 + 误报，见 `config/dsl_equivalence.json`）⇒ `switch_allowed: false`。
  故本模块**不把规则从代码搬到 YAML**（那会引入漏报），而是把"分离"落实为：
  **规则可导出（YAML）+ 阈值可外置（config）+ 边界可登记（DSL scope）**，
  并让**加载器**成为唯一读取入口。

★ 纪律：
  · 任一载体读不出来 ⇒ **必须留痕**（`last_error()` 可读），不得静默当空（缺失≠空表）；
  · 未知字段一律**原样保留**在 `raw` 里，不丢弃（防"加载即丢信息"）。
"""

from __future__ import annotations

import glob
import json
import os
from typing import Any, Dict, List, Optional, Tuple

#: 载体种类（★ 唯一权威：新增一类只加这里一处）
SOURCE_KINDS: Tuple[str, ...] = ("python", "json", "yaml", "dsl", "governance")

SOURCE_CN: Dict[str, str] = {
    "python": "系统在库规则（Python 执行权威）",
    "json": "外部候选清单（JSON 候选权威）",
    "yaml": "候选导出（YAML 交换格式）",
    "dsl": "条件表达式（DSL 边界登记）",
    "governance": "权威事实核查规则（另一维度体系）",
}

#: 各载体是**执行权威**还是**派生/登记**（前端与接口据此措辞，防把导出当权威）
AUTHORITY_OF: Dict[str, str] = {
    "python": "authoritative",      # 真执行
    "json": "candidate",            # 候选权威（尚未入库）
    "yaml": "derived",              # 同源导出，非第二权威
    "dsl": "registry",              # 能力边界登记，不执行
    "governance": "other_axis",     # ★ 另一维度体系，**独立列示、不得与规则主体相加**
}

AUTHORITY_CN: Dict[str, str] = {
    "authoritative": "执行权威",
    "candidate": "候选权威（未入库）",
    "derived": "同源导出（非权威）",
    "registry": "边界登记（不执行）",
    "other_axis": "另一维度（不得相加）",
}

_LAST_ERRORS: List[str] = []


def last_errors() -> List[str]:
    """最近一次加载过程中的问题清单（**空 = 全部读到**）。"""
    return list(_LAST_ERRORS)


def _note(msg: str) -> None:
    """留痕（绝不静默）。"""
    _LAST_ERRORS.append(str(msg))
    try:
        import sys as _sys
        print("[rule-loader] %s" % msg, file=_sys.stderr, flush=True)
    except Exception:                                    # noqa: BLE001
        pass


def _root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ══════════════════════════════════════════════════════════════════════════
# ① Python（执行权威）
# ══════════════════════════════════════════════════════════════════════════
def load_python_rules() -> List[Dict[str, Any]]:
    """系统**在库**规则：红线 91 + 已验证 85 + 四个检测器层（专项/缺口/缺口税种/扣限）。

    ★ 检测器层（`special_redline_detectors` 等）是**红线的检测器实现层**，
      **不得**计成独立规则条数（见 `layer_semantics.forbidden_aggregations`）；
      本函数如实标 `layer` 与 `counts_toward_rule_total`，由调用方按权威分层口径统计。
    """
    out: List[Dict[str, Any]] = []
    try:
        from engine.tax_redlines import REDLINES            # noqa: PLC0415
        for r in REDLINES:
            out.append(_rec(r, kind="python", layer="tax_redlines"))
    except Exception as exc:                                # noqa: BLE001
        _note("读取红线库失败：%s" % exc)
    try:
        from engine.verified_rule_engine import VERIFIED_RULE_CATALOG   # noqa: PLC0415
        for r in VERIFIED_RULE_CATALOG:
            out.append(_rec(r, kind="python", layer="verified_rule_engine"))
    except Exception as exc:                                # noqa: BLE001
        _note("读取已验证规则库失败：%s" % exc)
    # ★ 检测器层载体常量名**各不相同**（实测：SPECS / DETECTORS / SPECS）——
    #   按 `layer_semantics.layers` 的五个层逐一登记（含两个规则库共 5 层）。
    for mod_name, attr in (("special_redline_detectors", "SPECS"),
                           ("gap_risk_detectors", "DETECTORS"),
                           ("gap_tax_obligations", "SPECS")):
        try:
            mod = __import__("engine.%s" % mod_name, fromlist=[attr])
            _items = getattr(mod, attr, None) or []
            # ★ `gap_risk_detectors.DETECTORS` 的元素是 **(rule_id, 检测函数) 二元组**
            #   （实测），不是 dict ⇒ 必须单独处理；其余两个层是 dict 列表。
            for r in _items:
                if isinstance(r, (tuple, list)) and r and isinstance(r[0], str):
                    out.append(_rec({"redline_id": r[0],
                                     "name": str(getattr(r[1], "__doc__", "") or "").strip()
                                             .splitlines()[0] if len(r) > 1 else ""},
                                    kind="python", layer=mod_name, detector_layer=True))
                elif isinstance(r, dict):
                    out.append(_rec(r, kind="python", layer=mod_name, detector_layer=True))
                else:
                    _note("%s 出现无法识别的条目形态：%s" % (mod_name, type(r).__name__))
        except Exception as exc:                            # noqa: BLE001
            _note("读取检测器层 %s 失败：%s" % (mod_name, exc))
    return out


# ══════════════════════════════════════════════════════════════════════════
# ② JSON（候选权威）
# ══════════════════════════════════════════════════════════════════════════
def load_json_candidates() -> List[Dict[str, Any]]:
    """外部候选清单（`config/rulelist_v*.json`）；阈值唯一权威在其 `params` 段。"""
    out: List[Dict[str, Any]] = []
    for name in ("rulelist_v1.json", "rulelist_v11.json", "rulelist_v12.json"):
        path = os.path.join(_root(), "config", name)
        if not os.path.exists(path):
            _note("候选清单不存在：%s" % name)
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except Exception as exc:                            # noqa: BLE001
            _note("候选清单读取失败 %s：%s" % (name, exc))
            continue
        params = doc.get("params") or {}
        for r in (doc.get("rules") or []):
            rec = _rec(r, kind="json", layer=name)
            rid = rec["rule_id"]
            rec["action"] = str(r.get("action") or "")
            rec["status"] = str(r.get("status") or "")
            rec["condition"] = str(r.get("logic") or "")
            rec["note"] = str(r.get("note") or "")
            rec["params_ref"] = ("config/%s::params.%s" % (name, rid)) if rid else ""
            rec["params"] = params.get(rid) or {}
            out.append(rec)
    return out


# ══════════════════════════════════════════════════════════════════════════
# ③ YAML（同源导出）
# ══════════════════════════════════════════════════════════════════════════
def load_yaml_exports() -> List[Dict[str, Any]]:
    """候选导出（`rules_export/*.yaml`）——**交换格式，非第二权威**。

    `wired: false` 是**事实**（该清单未接入系统）；本函数原样传递，不改写为 true。
    """
    out: List[Dict[str, Any]] = []
    files = sorted(glob.glob(os.path.join(_root(), "rules_export", "*.yaml")))
    if not files:
        _note("rules_export/*.yaml 一个都没有（导出器未运行？）")
        return out
    try:
        import yaml                                          # noqa: PLC0415
    except Exception as exc:                                 # noqa: BLE001
        _note("yaml 库不可用，YAML 载体跳过：%s" % exc)
        return out
    for path in files:
        try:
            with open(path, encoding="utf-8") as fh:
                doc = yaml.safe_load(fh) or {}
        except Exception as exc:                             # noqa: BLE001
            _note("YAML 读取失败 %s：%s" % (os.path.basename(path), exc))
            continue
        wired = bool(doc.get("wired"))
        for r in (doc.get("rules") or []):
            rec = _rec(r, kind="yaml", layer=os.path.basename(path))
            rec["enabled"] = bool(r.get("enabled"))
            rec["wired"] = wired
            rec["condition"] = str(r.get("condition") or "")
            rec["params_ref"] = str(r.get("params_ref") or "")
            rec["coverage"] = r.get("coverage")
            out.append(rec)
    return out


# ══════════════════════════════════════════════════════════════════════════
# ④ DSL（边界登记）
# ══════════════════════════════════════════════════════════════════════════
def load_dsl_scope() -> Dict[str, Any]:
    """DSL 表达力边界（`config/rule_dsl_scope.json`）——**不执行**，只登记能力边界。"""
    path = os.path.join(_root(), "config", "rule_dsl_scope.json")
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh) or {}
    except Exception as exc:                                 # noqa: BLE001
        _note("DSL 边界登记表读取失败：%s" % exc)
        return {}


# ══════════════════════════════════════════════════════════════════════════
# ⑤ 权威事实核查规则（**另一维度体系**，不是第六个"规则主体"层）
# ══════════════════════════════════════════════════════════════════════════
def load_governance_rules() -> List[Dict[str, Any]]:
    """权威事实核查规则（89 条）—— `layer_semantics` 明示它属 `rule_other_axis`：
    「与红线/已验证规则属**不同维度**体系，独立列示，**不得与二者相加**」。

    来源：`engine/fact_rules.py::governance_inventory()['rules']`
          ← `static/methodology_canonical_catalog.json`。
    ★ 实测教训：我最初只加载了 5 层（漏了这第 6 层）⇒ 规则库**覆盖不全**；
      本函数补齐，并以 `source_kind="governance"` 与主体严格分开（防被相加）。
    """
    out: List[Dict[str, Any]] = []
    try:
        from engine.fact_rules import load_flat_rules            # noqa: PLC0415
        # ★ 实测：`governance_inventory()['rules']` 是**计数（int）**，不是清单；
        #   真正的扁平明细在 `load_flat_rules()`（89 条，键 `id/fact_hypothesis/required_fields/excludes`）。
        #   若误用 inventory 会得到"0 条 + 不报错"的静默空表 —— 故此处直接取明细函数。
        for r in (load_flat_rules() or []):
            if isinstance(r, dict):
                rec = _rec({"id": r.get("id"),
                            "name": str(r.get("fact_hypothesis") or r.get("id") or ""),
                            "legal_basis_ref": r.get("legal_basis_ref"),
                            "legal_basis": r.get("legal_basis"),
                            "required_sources": r.get("required_fields") or [],
                            "raw": r},
                           kind="governance", layer="fact_check_rules")
                rec["required_fields"] = [str(x) for x in (r.get("required_fields") or [])]
                rec["excludes"] = [str(x) for x in (r.get("excludes") or [])]
                out.append(rec)
            else:
                _note("fact_check_rules 出现无法识别的条目形态：%s" % type(r).__name__)
    except Exception as exc:                                    # noqa: BLE001
        _note("读取权威事实核查规则失败：%s" % exc)
    return out


# ══════════════════════════════════════════════════════════════════════════
# 规范化
# ══════════════════════════════════════════════════════════════════════════
def _rec(raw: Dict[str, Any], *, kind: str, layer: str,
         detector_layer: bool = False) -> Dict[str, Any]:
    """把任一载体的条目规范化成统一 `RuleRecord`。**未知字段全部保留在 `raw`。**

    ★ `legal_basis_ref`：任务书约束「法规依据只写 legal_basis_ref」——
      这里把载体的法规依据规范化成**引用列表**（法律名 + 条文），并**同时保留原文**
      （`legal_basis_text`）以便可追溯；两者都不丢。
    """
    # ★ 各载体 id 键名**各不相同**（实测）：红/已验证=`id`；检测器层=`redline_id`；
    #   候选 JSON=`src`；YAML 导出=`rule_id`。故统一按优先级取值。
    rid = str(raw.get("id") or raw.get("rule_id") or raw.get("redline_id")
              or raw.get("src") or "")
    taxes = raw.get("taxes") or ([raw["tax_type"]] if raw.get("tax_type") else [])
    lb_text = _legal_texts(raw)
    # ★ 候选库自带 `legal_basis_ref` —— **优先用它**（那是作者口径）。实测其取值形态有两类：
    #   ① 结构化引用数组（`[{law, article, raw}]`）⇒ 直接用；
    #   ② **占位字符串**（实测 `config/rulelist_v*.json` 460 条**全部**是「法规库自动匹配」）
    #      ⇒ 必须**如实标记为占位**（`placeholder=True`），**不得**当"已有法规依据"。
    lb_ref = raw.get("legal_basis_ref")
    refs: List[Dict[str, Any]] = []
    if isinstance(lb_ref, list) and lb_ref:
        refs = [({"law": str(x.get("law") or ""), "article": str(x.get("article") or ""),
                  "raw": str(x.get("raw") or x.get("law") or ""), "placeholder": False}
                 if isinstance(x, dict) else
                 {"law": str(x), "article": "", "raw": str(x), "placeholder": False})
                for x in lb_ref]
    elif isinstance(lb_ref, str) and lb_ref.strip():
        refs = [{"law": "", "article": "", "raw": lb_ref.strip(), "placeholder": True}]
    else:
        refs = _legal_refs(lb_text)
    return {
        "rule_id": rid,
        "name": str(raw.get("name") or raw.get("topic") or ""),
        "source_kind": kind,
        "layer": layer,
        "detector_layer": bool(detector_layer),
        "tax": str(raw.get("tax_type") or ""),
        "taxes": [str(t) for t in taxes if str(t or "").strip()],
        "severity": str(raw.get("severity") or raw.get("sev") or raw.get("level") or ""),
        "version": str(raw.get("version") or ""),
        "enabled": (bool(raw.get("enabled")) if "enabled" in raw else None),
        "condition": str(raw.get("condition") or raw.get("logic") or ""),
        "inputs": [str(x) for x in (raw.get("inputs") or [])],
        "required_sources": [str(x) for x in (raw.get("required_sources") or [])],
        "params_ref": str(raw.get("params_ref") or ""),
        "params": raw.get("params") or {},
        "legal_basis_ref": refs,
        "legal_basis_text": lb_text,
        "raw": raw,
    }


def _legal_texts(raw: Dict[str, Any]) -> List[str]:
    """从条目里取法规依据原文（可能的键：`legal_basis` / `policy_ref` / `basis`）。"""
    for key in ("legal_basis", "policy_ref", "basis"):
        v = raw.get(key)
        if isinstance(v, str) and v.strip():
            return [v.strip()]
        if isinstance(v, (list, tuple)):
            items = [str(x).strip() for x in v if str(x or "").strip()]
            if items:
                return items
    return []


def _legal_refs(texts: List[str]) -> List[Dict[str, Any]]:
    """法规依据原文 → **结构化引用**（`{law, article, raw}`）。

    ★ 复用既有唯一权威 `engine/legal_citation.split_citation`（不另写一套正则）；
      解析不出 ⇒ 原样留在 `raw` 字段，**不丢**（缺失≠空）。
    """
    out: List[Dict[str, str]] = []
    try:
        from engine.legal_citation import split_citation      # noqa: PLC0415
    except Exception as exc:                                  # noqa: BLE001
        _note("法规引用解析器不可用（法规依据原样保留）：%s" % exc)
        return [{"law": "", "article": "", "raw": t, "placeholder": False} for t in texts]
    for t in texts:
        try:
            parts = split_citation(t) or []
        except Exception:                                     # noqa: BLE001
            parts = []
        # ★ `split_citation` 的返回是 **4 元组** `(law, article, ?, text)`（实测），
        #   不是 dict —— 按位置解析，两种形态都兼容（防上游改形导致静默丢引用）。
        if not parts:
            out.append({"law": "", "article": "", "raw": t, "placeholder": False})
            continue
        if isinstance(parts, (list, tuple)) and parts and isinstance(parts[0], str):
            out.append({"law": parts[0], "article": (parts[1] if len(parts) > 1 else ""),
                        "raw": t, "placeholder": False})
            continue
        for p in parts:
            if isinstance(p, dict):
                out.append({"law": str(p.get("law") or ""),
                            "article": str(p.get("article") or ""), "raw": t,
                            "placeholder": False})
            elif isinstance(p, (list, tuple)) and p and isinstance(p[0], str):
                out.append({"law": p[0], "article": (p[1] if len(p) > 1 else ""), "raw": t, "placeholder": False})
            else:
                out.append({"law": str(p), "article": "", "raw": t, "placeholder": False})
    return out


# ══════════════════════════════════════════════════════════════════════════
# ⑤ 候选阈值唯一索引（D-01：把三册 params 收敛为单一入口，含冲突登记）
# ══════════════════════════════════════════════════════════════════════════
#: 候选阈值所在分册（★ 唯一权威：新增一册只加这里一行）
CANDIDATE_BOOKS: Tuple[str, ...] = ("rulelist_v1.json", "rulelist_v11.json", "rulelist_v12.json")

#: 分册短名（对外展示用；与文件名一一对应）
BOOK_SHORT: Dict[str, str] = {
    "rulelist_v1.json": "V1.0",
    "rulelist_v11.json": "V1.1",
    "rulelist_v12.json": "V1.2",
}


def param_index() -> Dict[str, Any]:
    """**候选阈值唯一索引**：`rule_id → {book, key, file, value}`。

    ## 为什么需要它（D-01 裁定）
    三册 `config/rulelist_v1|v11|v12.json` 各自维护 `params` 段（合 128 个阈值键）。
    此前消费方有两条**不一致**的取法：
      ① `tools/export_rulelist_yaml.py::_collect()` 用 `dict.update()` 把三册合并 ——
         **同名键静默覆盖**（后册胜出，无任何留痕）；且 `params_ref` 仍写死在各自分册。
      ② `engine/rulelist_v1.py::params_of()` 只读 V1.0 一册。
    ⇒ 取同一规则阈值可能得到两个答案，且冲突无人发现。

    现在：**取候选阈值只有本函数一个入口**（分册差异由索引内部消化），
    冲突**必须显式登记**、绝不静默覆盖。

    ## 纪律
    · 同一 key 出现在多册且**值不等** ⇒ 记入 `conflicts`（**不算通过**，须人工收敛）；
    · 值相等 ⇒ 记入 `redundant`（可收敛为一行，非错误）；
    · 未登记的 rule_id ⇒ `params.get(rid)` 为 `None`（**不兜底为 {}**，
      与 `engine.rule_params.value()` 同纪律：缺失≠默认值）。
    """
    params: Dict[str, Dict[str, Any]] = {}
    seen_in: Dict[str, List[str]] = {}
    conflicts: List[Dict[str, Any]] = []
    redundant: List[str] = []

    for name in CANDIDATE_BOOKS:
        path = os.path.join(_root(), "config", name)
        if not os.path.exists(path):
            _note("候选阈值分册不存在：%s" % name)
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except Exception as exc:                            # noqa: BLE001
            _note("候选阈值分册读取失败 %s：%s" % (name, exc))
            continue
        for key, val in (doc.get("params") or {}).items():
            if str(key).startswith("_"):                    # `_note` 等说明键不参与索引
                continue
            seen_in.setdefault(key, []).append(name)
            if key not in params:
                params[key] = {"book": BOOK_SHORT.get(name, name), "key": key,
                               "file": "config/%s" % name,
                               "params_ref": "config/%s::params.%s" % (name, key),
                               "value": val}
                continue
            # ★ 重复登记：值相等 ⇒ 可收敛；值不等 ⇒ **冲突**（不得静默取后者）
            prev = params[key]
            if prev.get("value") == val:
                redundant.append(key)
            else:
                conflicts.append({
                    "key": key,
                    "books": list(seen_in[key]),
                    "kept": prev["params_ref"],
                    "conflicting": "config/%s::params.%s" % (name, key),
                    "kept_value": prev.get("value"),
                    "conflicting_value": val,
                })

    if conflicts:
        _note("候选阈值**冲突**（同一键在多册取值不同，已保留先册、须人工收敛）：%s"
              % [c["key"] for c in conflicts])
    if redundant:
        _note("候选阈值重复登记（多册同键同值，建议收敛为一行）：%s" % redundant)

    return {
        "params": params,
        "conflicts": conflicts,
        "redundant": sorted(set(redundant)),
        "books": [_B for _B in CANDIDATE_BOOKS],
        "stats": {
            "keys": len(params),
            "conflicts": len(conflicts),
            "redundant": len(set(redundant)),
            "books": {BOOK_SHORT.get(b, b): sum(1 for v in params.values() if v["file"].endswith(b))
                      for b in CANDIDATE_BOOKS},
        },
    }


def param_of(rule_id: str) -> Optional[Dict[str, Any]]:
    """按 **rule_id** 取该规则的候选阈值条目（`param_index()` 的单点取用）。

    未登记 ⇒ `None`（**不返回空 dict、不兜底**）。索引内已含 `params_ref`，
    消费方不必再判"这条属于哪一册"。
    """
    if not rule_id:
        return None
    return param_index()["params"].get(str(rule_id))


def param_conflicts() -> List[Dict[str, Any]]:
    """候选阈值冲突清单（**空 = 无冲突**）。供闸门与接口直接消费。"""
    return list(param_index()["conflicts"])
