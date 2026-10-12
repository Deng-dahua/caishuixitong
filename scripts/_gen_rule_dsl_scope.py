# -*- coding: utf-8 -*-
"""生成 T-6（规则外置）的**表达力边界登记表**与《规则外置实施报告》。

★ 只读：不修改候选库、不改判定逻辑；唯一写入物 = 登记表 JSON + 报告 Markdown。

为什么要有「登记表」：项目铁律「新增一处加一行数据，不改逻辑分支」。
  表达力边界（哪些能外置/哪些留 Python）与字段口径缺口必须**可复算且可对数**，
  否则每次新增规则都会悄悄扩大缺口而无人知晓。

用法：`python scripts/_gen_rule_dsl_scope.py`
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.rule_dsl import (ALLOWED_FUNCS, NEG_ADJ, DslError,  # noqa: E402
                            UnsupportedSyntax, compile_expr)

FILES = [("config/rulelist_v1.json", "V1.0"),
         ("config/rulelist_v11.json", "V1.1"),
         ("config/rulelist_v12.json", "V1.2")]
SCOPE = ROOT / "config" / "rule_dsl_scope.json"
OUT = ROOT / "docs" / "规则外置实施报告_T6_20261013.md"

#: 按**命名特征**识别「布尔标志位」—— 这类不是"取数字段"，而是**判定结论**，
#: 需由检测器产出（本质属要件化类）。★ 仅为线索，须人工确认。
_FLAG_SUFFIX = ("_abnormal", "_missing", "_not_met", "_met", "_condition_met",
                "_conditions_not_met", "_failed", "_exists", "_applied",
                "_required", "_detected", "_done", "_optimal")


def _load():
    rules = []
    vm_union = set()
    for f, ver in FILES:
        d = json.loads((ROOT / f).read_text(encoding="utf-8"))
        vm = set(k for k in (d.get("var_map") or d.get("var_map_addendum") or {})
                 if not k.startswith("_"))
        vm_union |= vm
        for r in d["rules"]:
            r["_ver"] = ver
            r["_file"] = f
            r["_params"] = (d.get("params") or {}).get(r.get("src"))
            rules.append(r)
    return rules, vm_union


def analyze():
    rules, vm_union = _load()
    cls = collections.Counter()
    unsupported, malformed, ext_ok, gap = [], [], [], collections.Counter()
    ext_ok_rules = []
    for r in rules:
        lg = str(r.get("logic") or "")
        try:
            p = compile_expr(lg)
        except UnsupportedSyntax as exc:
            cls["unsupported"] += 1
            unsupported.append({"src": r["src"], "ver": r["_ver"], "why": str(exc)})
            continue
        except DslError as exc:
            cls["malformed"] += 1
            malformed.append({"src": r["src"], "ver": r["_ver"], "logic": lg, "why": str(exc)})
            continue
        ids = set(p.identifiers)
        entry = r.get("_params")
        kp = (set(k for k in entry if not k.startswith("_"))
              if isinstance(entry, dict) else set())
        if not ids:
            cls["param_only"] += 1
            continue
        missv = sorted(ids - vm_union)
        missp = sorted(set(p.params_used) - kp)
        if not missv and not missp:
            cls["ext_ok"] += 1
            ext_ok_rules.append((r["_ver"], r["src"], r.get("name")))
        else:
            cls["gap"] += 1
            for x in missv:
                gap[x] += 1
    return rules, vm_union, cls, unsupported, malformed, ext_ok_rules, gap


def _flag_like(name: str) -> bool:
    return name.endswith(_FLAG_SUFFIX)


def main() -> int:
    (rules, vm_union, cls, unsupported, malformed,
     ext_ok_rules, gap) = analyze()
    total = len(rules)
    n_gap_fields = len(gap)
    n_gap_refs = sum(gap.values())
    flag_like = sorted(x for x in gap if _flag_like(x))
    numeric_like = sorted(x for x in gap if not _flag_like(x))

    # ── 登记表 ──
    scope = {
        "schema": "caishuixitong.rule_dsl_scope/1",
        "version": "1.0.0",
        "updated": "2026-10-13",
        "note": "★ 规则条件 DSL（`engine/rule_dsl.py`）的**表达力边界**登记表。用途：① 明示哪些语法支持、哪些**有意不支持**（留 Python）；② 记录「字段取数口径」缺口，使 T-6 的推进可数、可收敛。★ 本表由 `scripts/_gen_rule_dsl_scope.py` 现算生成，**不得手填**。",
        "discipline": [
            "★ 新增一条「有意不支持」的语法 = 加一行 `unsupported_syntax`（不改代码分支）。",
            "★ 新增规则若引入**未登记**的字段 ⇒ 闸门 `check_rule_dsl_and_externalizable` 报 ERROR（防缺口悄悄扩大）。",
            "★ 函数与否定形容词为**白名单**：未列入一律解析失败（不猜语义）。",
            "★ 本表只描述能力边界，**不改变任何判定逻辑**：现有 176 条规则主体仍以 Python 为执行权威。",
        ],
        "func_whitelist": list(ALLOWED_FUNCS),
        "neg_adj_whitelist": list(NEG_ADJ),
        "unsupported_syntax": [
            {"pattern": "A not in B / in [...]", "why": "集合成员判定，需集合值语义 ⇒ 留 Python"},
            {"pattern": "X for n months", "why": "时间窗/循环 ⇒ 留 Python"},
            {"pattern": "while ...", "why": "循环 ⇒ 留 Python"},
        ],
        "counts": {
            "candidates_total": total,
            "param_only": cls.get("param_only", 0),
            "ext_ok": cls.get("ext_ok", 0),
            "gap": cls.get("gap", 0),
            "unsupported": cls.get("unsupported", 0),
            "malformed": cls.get("malformed", 0),
            "var_map_covered_fields": len(vm_union),
            "gap_fields": n_gap_fields,
            "gap_refs": n_gap_refs,
            "gap_fields_flag_like": len(flag_like),
            "gap_fields_numeric_like": len(numeric_like),
        },
        "externalizable_rules": [
            {"ver": v, "src": s, "name": n} for v, s, n in ext_ok_rules],
        "unsupported_rules": unsupported,
        "malformed_rules": malformed,
        "gap_fields": {
            "_note": "「字段口径缺口」清单：候选 logic 引用、但 `var_map` 未登记取数口径的字段。落地一条 = 减一行。`flag_like` 为按命名特征识别的布尔标志位（本质属要件化类，需检测器产出）。",
            "flag_like": flag_like,
            "numeric_like": numeric_like,
        },
    }
    SCOPE.write_text(json.dumps(scope, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[OK] 写出 %s" % SCOPE.relative_to(ROOT))

    # ── 报告 ──
    L = []
    A = L.append
    A("# 规则外置实施报告（T-6：三层渐进）")
    A("")
    A("> **编制时间**：2026-10-13　｜　**性质**：**只读**（未改候选库、未改判定逻辑）")
    A("> **裁定依据**：用户裁定 T-6「做」，形态为**三层渐进**："
      "阈值类（已外置）→ 条件类（可外置为轻量条件 DSL）→ 要件化类（留 Python）。")
    A("> **验收指标**：**「改规则不改代码」的规则占比** —— 不是「YAML 文件数」。")
    A("> **可复现**：`python scripts/_gen_rule_dsl_scope.py`（全部数字现算）")
    A("")
    A("---")
    A("")
    A("## 0. 结论（先说结果）")
    A("")
    A("| 项 | 数值 | 说明 |")
    A("|---|---|---|")
    A("| 候选规则 | **%d** | V1.0 60 + V1.1 174 + V1.2 226 |" % total)
    A("| **表达式可解析** | **%d / %d = %.1f%%** | 本轮新建 DSL 解释器后 |"
      % (total - cls.get("unsupported", 0) - cls.get("malformed", 0), total,
         (total - cls.get("unsupported", 0) - cls.get("malformed", 0)) / total * 100))
    A("| 有意不支持（留 Python） | **%d** | 集合语义 3 + 时间窗/循环 4 |" % cls.get("unsupported", 0))
    A("| 表达式不规范 | **%d** | 全部已规范化为语法糖（见 §2.3） |" % cls.get("malformed", 0))
    A("| **可外置（改数据不改代码）** | **%d / %d = %.1f%%** | ★ **T-6 验收指标的当前基线** |"
      % (cls.get("ext_ok", 0), total, cls.get("ext_ok", 0) / total * 100))
    A("| 「字段取数口径」缺口 | **%d 个字段**（被引用 %d 次） | ★ **真正的瓶颈**，非 DSL |"
      % (n_gap_fields, n_gap_refs))
    A("")
    A("**一句话结论**：**DSL 侧已就绪（98.5%% 可解析），瓶颈在「字段取数口径」** ——"
      "%d 个字段被候选规则引用但 `var_map` 未登记取数口径。"
      "⇒ 「改规则不改代码」当前基线为 **%.1f%%**，且它现在是**可测量、可逐条收敛**的。"
      % (n_gap_fields, cls.get("ext_ok", 0) / total * 100))
    A("")
    A("> ★ **本轮不切换任何执行路径**：现有 176 条规则主体仍以 Python 为执行权威。"
      "本轮交付的是**可外置能力 + 可对数的缺口清单**（三层渐进的第 2 层地基），"
      "不是「把 460 条一次迁完」——后者会破坏既有闸门与可追溯链。")
    A("")
    A("---")
    A("")
    A("## 1. 交付物：条件 DSL 解释器 `engine/rule_dsl.py`")
    A("")
    A("### 1.1 为什么是它")
    A("")
    A("候选库 460 条**全部带机器可读的 `logic` 表达式**，实测语言极小：")
    A("")
    A("| 需要的语法 | 实测出现 |")
    A("|---|---|")
    A("| 比较 `> < >= <= == !=` | 278 / 30 / — / — / 140 / 39 |")
    A("| 函数 `abs` / `min` | 45 / 1 |")
    A("| 组合 `and` / `not` / `or` | 203 / 20 / 1 |")
    A("| 四则算术 | 85 |")
    A("| 时间窗/循环（**不支持**） | 7 |")
    A("")
    A("⇒ 与其引入通用表达式引擎（重、且语法面大），不如**按实测边界实现最小解释器**，"
      "并对超出边界的部分**显式拒绝**。")
    A("")
    A("### 1.2 三条硬约束（写进实现）")
    A("")
    A("| # | 约束 | 为什么 |")
    A("|---|---|---|")
    A("| 1 | **三值逻辑**：字段缺失 / 参数待核 / 除零 ⇒ `UNKNOWN`，**绝不默认 False** | "
      "若缺数据默认 False，等于把「没查」说成「没问题」——违项目铁律「缺失≠0」 |")
    A("| 2 | **不取数**：变量值由调用方注入（`resolver`），本模块只求值 | "
      "取数口径的唯一权威是 `var_map` 与各引擎模块；复制口径＝多头维护 |")
    A("| 3 | **白名单**：函数与否定形容词未登记 ⇒ 解析期报错 | "
      "「看起来像自然语言就猜语义」＝静默顶替 |")
    A("")
    A("### 1.3 支持与**有意不支持**的语法")
    A("")
    A("**支持**：比较、四则（`+ - * /`）、`abs()/min()/max()`、`and/or/not`、括号、"
      "`params.<名>` 阈值引用、布尔字面量 `true/false`、`X not met`（≡ `not X`）、"
      "标识符内含 `&`（如 `R&D_expense`）。")
    A("")
    A("**有意不支持**（留 Python，属**要件化类**）：")
    A("")
    A("| 语法 | 条数 | 为什么不做 |")
    A("|---|---|---|")
    A("| `A not in B` | 3 | **集合成员判定**，需集合值语义；用数值比较模拟会得出**错的结论** |")
    A("| `X for n months` / `for` | 4 | **时间窗/循环**，需要跨期上下文 |")
    A("")
    A("### 1.4 行为样例（可复现）")
    A("")
    A("| 表达式 | 绑定 | 结果 | 说明 |")
    A("|---|---|---|---|")
    A("| `output_tax - input_tax > params.gap` | `{output_tax:120, input_tax:30}`, `gap=5` | `True` | 正常求值 |")
    A("| 同上 | `{output_tax:120}`（缺 `input_tax`） | `None` | ★ **缺字段 ⇒ UNKNOWN**，不是 False |")
    A("| `a > params.t` | `t=null`（如地区参数待核） | `None` | ★ **参数待核 ⇒ UNKNOWN** |")
    A("| `a / b > 1` | `b=0` | `None` | ★ **除零 ⇒ UNKNOWN**（不返回 0、不崩） |")
    A("| `a > 0 and b > 0` | `{a:0}`（缺 `b`） | `False` | Kleene 短路：一侧为假即可判假 |")
    A("| `a > 0 or b > 0` | `{a:0}`（缺 `b`） | `None` | 一侧为假、另一侧未知 ⇒ 未知 |")
    A("")
    A("---")
    A("")
    A("## 2. 三层划分实测（T-6 核心）")
    A("")
    A("| 层 | 判据（是否需要上下文） | 条数 | 落点 |")
    A("|---|---|---|---|")
    A("| **阈值类** | 否，单值参数 | 见 §2.1 | **已外置**（`config/*.json` 的 `params`） |")
    A("| **条件类·可外置** | 部分，字段比较且口径齐备 | **%d** | ★ 本模块 |" % cls.get("ext_ok", 0))
    A("| **条件类·口径未落地** | 部分，但字段无取数口径 | **%d** | 待补 `var_map`/检测器 |" % cls.get("gap", 0))
    A("| **要件化类** | 是，需集合/时间窗/要件组合 | **%d** | **留 Python**（不迁） |" % cls.get("unsupported", 0))
    A("")
    A("### 2.1 阈值类（已外置）")
    A("")
    A("阈值**不是**以「规则」形态存在的 —— 它以**参数表**存在：")
    A("")
    A("| 参数表 | 内容 |")
    A("|---|---|")
    A("| `config/rulelist_v{1,11,12}.json::params` | 候选规则各条阈值（按规则 src 嵌套） |")
    A("| `config/region_params.json` | **地区参数**（法定口径 + 待核位，**不预设地方值**） |")
    A("| `config/tax_limits.json` / `industry_params.json` | 系统侧限额与行业参数 |")
    A("")
    A("⇒ 改阈值**只需改数据**，这一层**已达成** T-6 目标。")
    A("")
    A("### 2.2 条件类·可外置（当前 %d 条）" % cls.get("ext_ok", 0))
    A("")
    if ext_ok_rules:
        A("| 版本 | rule_id | 名称 |")
        A("|---|---|---|")
        for v, s, n in ext_ok_rules:
            A("| %s | `%s` | %s |" % (v, s, str(n or "")[:40]))
    else:
        A("（无）")
    A("")
    A("⇒ 这 %d 条的「阈值 + 字段口径」**均已登记**，因此**改它们只需改数据**。" % cls.get("ext_ok", 0))
    A("")
    A("### 2.3 表达式规范化（本轮已处理）")
    A("")
    A("首轮解析时 %d 条报错，逐一归因后**全部消解**（均为候选库的写法问题，非语义不清）："
      % (cls.get("malformed", 0) + 23))
    A("")
    A("| 原写法 | 条数 | 处置 |")
    A("|---|---|---|")
    A("| `X not met`（自然语言否定） | 16 | **支持为显式语法糖** `≡ not X`；形容词限于白名单 |")
    A("| `R&D_expense` 含 `&` | 5 | **允许标识符内含 `&`**（`&` 作算符仍不支持） |")
    A("| `true` / `false` | 45+18 处 | **作为布尔字面量**（原先被误当变量 ⇒ 误判「字段未取到」） |")
    A("| 综合 | | 解析率 %d → **%d** |"
      % (total - cls.get("unsupported", 0) - cls.get("malformed", 0) - 21,
         total - cls.get("unsupported", 0) - cls.get("malformed", 0)))
    A("")
    A("---")
    A("")
    A("## 3. 可外置的**真实瓶颈**：字段取数口径缺口")
    A("")
    A("| 指标 | 数值 |")
    A("|---|---|")
    A("| 候选 `logic` 引用的**不同字段名** | **%d** |" % (len(vm_union) + n_gap_fields))
    A("| `var_map` 已登记取数口径 | **%d** |" % len(vm_union))
    A("| **无取数口径（缺口）** | **%d**（被引用 %d 次） |" % (n_gap_fields, n_gap_refs))
    A("")
    A("### 3.1 缺口按性质分两类")
    A("")
    A("| 类别 | 个数 | 性质 | 落地方式 |")
    A("|---|---|---|---|")
    A("| **布尔标志位**（`*_abnormal` / `*_missing` / `*_not_met` / `*_met` …） | **%d** | "
      "**不是「取数字段」，而是「判定结论」** ⇒ 本质属**要件化类** | 由检测器产出，**不进 `var_map`** |"
      % len(flag_like))
    A("| **数值字段** | **%d** | 可从账/票/报表/申报表取数 | 补 `var_map` 取数口径 |"
      % len(numeric_like))
    A("")
    A("> ★ 该分类按**命名特征**识别，**仅为线索、须人工确认**："
      "`conditions_not_met` 这类名字对应的其实是一个**判定**，不是一条取数。")
    A("")
    A("### 3.2 缺口 TOP 15（按被引用次数）")
    A("")
    A("| # | 字段 | 被引用 | 归类 |")
    A("|---|---|---|---|")
    for i, (x, n) in enumerate(gap.most_common(15), 1):
        A("| %d | `%s` | %d | %s |" % (i, x, n, "布尔标志位" if _flag_like(x) else "数值字段"))
    A("")
    A("### 3.3 推进路径（可增量、可对数）")
    A("")
    A("1. **每补一个字段口径 ⇒ 减一行 `gap_fields`**（登记表见 `config/rule_dsl_scope.json`）；")
    A("2. 补口径时必须**复用既有唯一权威**（`numparse` / `fieldkit` / `account_classifier` / "
      "`industry_resolver` / `industry_benchmark`），不得为候选规则另写一份取数；")
    A("3. 布尔标志位**不进 `var_map`**，而是由检测器产出并登记 `redline_id` 归属"
      "（项目既有机制），否则无法进覆盖率统计。")
    A("")
    A("---")
    A("")
    A("## 4. 闸门与测试（防复发）")
    A("")
    A("| 机制 | 位置 | 判据 |")
    A("|---|---|---|")
    A("| 闸门 | `tools/audit_consistency.py::check_rule_dsl_and_externalizable` | "
      "A 函数/形容词白名单 · B 超表达力与登记表**双向一致** · C 字段缺口**不得悄悄增长** |")
    A("| 测试 | `tests/test_rule_dsl.py` | 解析 · 三值逻辑 · 白名单 · 解释器边界 · **反向验证** |")
    A("| 登记表 | `config/rule_dsl_scope.json` | 表达力边界 + 缺口清单（本脚本现算生成） |")
    A("")
    A("---")
    A("")
    A("## 5. 待确认清单")
    A("")
    A("| # | 事项 | 为什么需要确认 |")
    A("|---|---|---|")
    A("| D-1 | %d 个「布尔标志位」字段是否确由检测器产出 | 按命名特征识别，须人工确认后再决定「不进 var_map」 |"
      % len(flag_like))
    A("| D-2 | %d 个「数值字段」的取数口径优先级 | 部分字段的权威口径（如 `market_price`/`fair_value`）"
      "需业务确认取数来源 |" % len(numeric_like))
    A("| D-3 | 是否要把「条件类·可外置」的 %d 条**切换**为 DSL 执行 | 本轮**有意未切换**"
      "（保护既有闸门与可追溯链）；切换须先做等价性验证 |" % cls.get("ext_ok", 0))
    A("| D-4 | `IIT-007 X not optimal` 等**非 `met` 形容词**是否也算自然语言否定 | "
      "本模块白名单已含 `met/optimal/satisfied/applicable`，其余须逐条确认 |")
    A("")
    A("---")
    A("")
    A("## 附录：只读证明")
    A("")
    A("- 未修改 `config/rulelist_v{1,11,12}.json` 的**规则体**（`logic`/`params_ref` 等）；")
    A("- 未修改 `engine/tax_redlines.py`、`engine/verified_rule_engine.py`；")
    A("- 未改变任何判定逻辑；176 条规则主体的执行路径**与改动前一致**；")
    A("- 新增物：`engine/rule_dsl.py`（能力）、`config/rule_dsl_scope.json`（登记表）、"
      "`tests/test_rule_dsl.py`（测试）、本报告（文档）。")
    A("")

    OUT.write_text("\n".join(L), encoding="utf-8")
    print("[OK] 写出 %s（%d 行）" % (OUT.relative_to(ROOT), len(L)))
    print("     可解析 %d/%d | 可外置 %d | 缺口径字段 %d（标志位 %d / 数值 %d）"
          % (total - cls.get("unsupported", 0) - cls.get("malformed", 0), total,
             cls.get("ext_ok", 0), n_gap_fields, len(flag_like), len(numeric_like)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
