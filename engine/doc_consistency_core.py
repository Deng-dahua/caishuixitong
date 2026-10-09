# -*- coding: utf-8 -*-
"""文档一致性 —— **共享核心**（Skill 1~5 的唯一实现；5 个 Skill 都是本核心的薄转发）。

## 为什么把 5 个 Skill 的核心收在一处
用户提出 5 个 Skill：① 文档数字一致性 ② 规则引用一致性 ③ 全文残留校验 ④ 未完成事项状态同步
⑤ 跨文件引用一致性。它们**要做的事只有三件**：
  (a) **取权威值**（配置计数 / 测试收集数 / 文件数 / 产物计数 / 规则清单条数）；
  (b) **抽文档里写的值**（正则声明 → 文本抽取）；
  (c) **比对并出清单**（不一致 = ERROR；旧值残留 = ERROR；规则引用缺失 = ERROR；状态不同步 = ERROR）。
若 5 个模块各写一遍取数与比对 ⇒ 就是本项目最忌的"同一概念 5 处实现、5 种判法"。
故：**本模块是唯一实现**；5 个 Skill 模块**只声明各自的判据范围**（薄转发），
数据全部来自 `config/doc_consistency.json`（数字/规则/引用边）与 `config/doc_synonyms.json`（同义词典）。

## 口径
- 权威值**必须现算**（`_authority_value`），不缓存、不手抄。
- 文档取值**必须由配置里的正则声明**（`claims[].regex`）—— 加一个数字 = 加一行数据。
- 所有检查返回统一的 `issue` 结构：`{"level": "ERROR/WARN", "where": "文件:行", "detail": "..."}`。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

VERSION = "1.0.1"
ROOT = Path(__file__).resolve().parent.parent
_CFG = ROOT / "config" / "doc_consistency.json"
_SYN = ROOT / "config" / "doc_synonyms.json"
_RECEIPT = ROOT / "data" / "logs" / "pytest_last_run.json"   # 全量运行回执（tests/conftest.py 写）
_CACHE: Dict[str, Any] = {}
_LOAD_ERRORS: Dict[str, str] = {}          # 读取失败留痕（**不得静默吞掉** ⇒ 见 `_guard()`）


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(p)


def _load(p: Path) -> Dict[str, Any]:
    key = str(p)
    if key not in _CACHE:
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            _CACHE[key] = raw if isinstance(raw, dict) else {}
            if not isinstance(raw, dict):
                _LOAD_ERRORS[key] = "顶层不是 JSON 对象"
            else:
                _LOAD_ERRORS.pop(key, None)
        except Exception as exc:              # 留痕：**必须记录**（否则坏表 = 判据全部静默通过 = 假绿）
            _LOAD_ERRORS[key] = "%s: %s" % (type(exc).__name__, str(exc)[:120])
            _CACHE[key] = {}
    return _CACHE[key]


def _load_error(p: Path) -> str:
    return _LOAD_ERRORS.get(str(p), "")


def reload_config() -> None:
    _CACHE.clear()
    _LOAD_ERRORS.clear()


def _guard(path: Path, what: str, need: List[str]) -> List[Dict[str, Any]]:
    """**数据表健康闸门**：表读不出来或缺必需键 ⇒ ERROR（判据无法执行，**不得静默通过**）。

    ⚠ 实测事故：`config/doc_consistency.json` 因一处半角引号导致 JSON 非法 ⇒ `_load` 返回 `{}`
      ⇒ 5 个门禁全部"0 项问题"（**假绿**）。故判据的第一条必须是"表能用"。
    """
    d = _load(path)                          # ⚠ 必须**先加载**再查错误（否则首次调用时错误还没被记录 ⇒ 报成"缺键"）
    err = _load_error(path)
    if err:
        return [{"level": "ERROR", "where": _rel(path),
                 "detail": "%s**读取失败**（%s）—— 判据无法执行；**不得静默通过**，"
                           "请先修复该 JSON" % (what, err)}]
    missing = [k for k in need if not d.get(k)]
    if missing:
        return [{"level": "ERROR", "where": _rel(path),
                 "detail": "%s**缺少必需键**：%s —— 判据无法执行（空表不等于「没问题」）"
                           % (what, "、".join(missing))}]
    return []



def config() -> Dict[str, Any]:
    return _load(_CFG)


def synonyms() -> Dict[str, Any]:
    return _load(_SYN)


def doc_dir() -> Path:
    return ROOT / str(config().get("doc_root") or "docs/第01批_触发条件与认定要件分离")


def doc_files() -> List[Path]:
    """本批交付物文件（唯一取法：目录下 `*.md`，按名排序）。"""
    d = doc_dir()
    return sorted(d.glob("*.md")) if d.is_dir() else []


# --------------------------------------------------------------------------
# (a) 权威值（唯一实现；kind 由数据表声明）
# --------------------------------------------------------------------------
def authority_value(spec: Dict[str, Any]) -> Tuple[Optional[int], str]:
    """按 `spec` 现算权威值 → `(值, 说明)`；取不到返回 `(None, 原因)`。"""
    kind = str((spec or {}).get("kind") or "")
    try:
        if kind == "catalog_count":
            return len(config().get("rule_catalog") or []), "config/doc_consistency.json → rule_catalog 条数"
        if kind == "config_count":
            d = _load(ROOT / str(spec.get("path")))
            expr = str(spec.get("expr") or "")
            risks = [r for r in (d.get("risks") or []) if isinstance(r, dict)]
            if expr == "len:risks":
                return len(risks), "%s → risks 条数" % spec.get("path")
            if expr == "sum:determination_criteria":
                return sum(len(r.get("determination_criteria") or []) for r in risks), \
                    "%s → 各风险认定要件求和" % spec.get("path")
            if expr == "sum:trigger_conditions":
                return sum(len(r.get("trigger_conditions") or []) for r in risks), \
                    "%s → 各风险触发条件求和" % spec.get("path")
            if expr == "count:is_precondition":
                return sum(1 for r in risks for c in (r.get("determination_criteria") or [])
                           if c.get("is_precondition")), "%s → is_precondition 计数" % spec.get("path")
            return None, "未登记的 expr：%s" % expr
        if kind == "pytest_collect":
            r = subprocess.run([sys.executable, "-m", "pytest", str(spec.get("target")),
                                "-q", "--collect-only"],
                               cwd=str(ROOT), capture_output=True, text=True)
            m = re.search(r"(\d+)\s+tests?\s+collected", r.stdout or "")
            if m:
                return int(m.group(1)), "pytest --collect-only %s" % spec.get("target")
            return None, "collect-only 未输出测试数"
        if kind == "file_count":
            return len(sorted(ROOT.glob(str(spec.get("glob"))))), "glob %s" % spec.get("glob")
        if kind == "grep_line":
            src = (ROOT / str(spec.get("path"))).read_text(encoding="utf-8", errors="replace")
            pat = re.compile(str(spec.get("pattern") or ""))
            for i, line in enumerate(src.split("\n"), start=1):
                if pat.search(line):
                    return i, "grep -n '%s' %s" % (spec.get("pattern"), spec.get("path"))
            return None, "grep 未命中：%s" % spec.get("pattern")
        if kind == "json_len":
            d = _load(ROOT / str(spec.get("path")))
            expr = str(spec.get("expr") or "")
            if expr.startswith("distinct:"):
                # `distinct:<list路径>.<每元素字段路径>` ⇒ 去重后的种类数
                #   实测用途：「`numbers[].authority.kind` 有几种」——**元事实**（关于事实的事实）
                body = expr[len("distinct:"):]
                segs = body.split(".")
                cur: Any = d
                i = 0
                while i < len(segs) and isinstance(cur, dict):   # 走到"数组"为止
                    cur = cur.get(segs[i])
                    i += 1
                if not isinstance(cur, list):
                    return None, "distinct 的数组路径不存在：%s" % body
                field_segs = segs[i:]                            # 剩余段 = 每个元素的字段路径
                vals = set()
                for x in cur:
                    v: Any = x
                    for f in field_segs:
                        v = (v or {}).get(f) if isinstance(v, dict) else None
                    if v is not None:
                        vals.add(v)
                return len(vals), "distinct(%s → %s) = %s" % (spec.get("path"), body, sorted(str(v) for v in vals))
            cur = d
            for k in expr.replace("len:", "").split("."):
                cur = (cur or {}).get(k) if isinstance(cur, dict) else None
            return (len(cur) if isinstance(cur, list) else None), \
                "len(%s → %s)" % (spec.get("path"), expr.replace("len:", ""))
        if kind == "regex_count":
            # 在某个文件里**数符合正则的行数** ⇒ 用于"元事实"：判据条数 / 用例分类条数
            #   （实测教训：这类"有几条"的事实，靠人分必然漂 —— 上一轮"22 例兜底残差"就是人分的）
            src = (ROOT / str(spec.get("path"))).read_text(encoding="utf-8", errors="replace")
            pat = re.compile(str(spec.get("pattern") or ""))
            n = sum(1 for line in src.split("\n") if pat.search(line))
            return n, "regex_count(%s, /%s/) = %d" % (spec.get("path"), spec.get("pattern"), n)
        if kind == "pytest_receipt":
            # ★ 全量回归的权威 = **最近一次全量运行的回执**（由 `tests/conftest.py` 自动写）
            #   为什么用回执而不是"每次现算"：全量跑一次 1~4 分钟，闸门不可能每次都跑。
            #   ⇒ 用"回执 + 过期判据"保证**文档写的 passed 永远对应真的跑过**：
            #     · 无回执 ⇒ 取不到（ERROR，不静默通过）
            #     · `tests/` 有文件比回执更新 ⇒ 取不到（回执过期，须重跑）
            rec = _load(_RECEIPT)
            if not rec:
                return None, "全量运行回执不存在（先跑一次 `pytest tests/ -q`）"
            err = _load_error(_RECEIPT)
            if err:
                return None, "回执读取失败：%s" % err
            cur_mtime = max((q.stat().st_mtime for q in (ROOT / "tests").rglob("*.py")), default=0.0)
            if cur_mtime > float(rec.get("tests_max_mtime") or 0.0) + 0.5:
                return None, "回执**已过期**：`tests/` 有文件在最近一次全量运行（%s）之后被改动，请重跑 `pytest tests/ -q`" \
                    % rec.get("finished_at")
            # ★ 只有**全绿**的全量运行，其 passed 才是"可写进文档的权威值"。
            #   若最近一次运行有失败，passed 只是"当前有 N 项失败"的瞬时状态 ⇒ **不作为权威值**
            #   （如实 WARN，绝不静默通过；也避免"文档必须等于一次红运行的计数"这种死循环）。
            bad = int(rec.get("failed") or 0) + int(rec.get("errors") or 0)
            if bad:
                return None, ("最近一次全量运行（%s）有 **%d 项失败** ⇒ passed 计数不是稳定权威值"
                              "（请先修到全绿再取该值）" % (rec.get("finished_at"), bad))
            fld = str(spec.get("field") or "passed")
            v = rec.get(fld)
            if not isinstance(v, int):
                return None, "回执里没有整数字段 `%s`" % fld
            return v, "全量运行回执 %s（命令 `%s`）→ %s" % (rec.get("finished_at"), rec.get("command"), fld)
        if kind == "product_count":
            d = _load(ROOT / "scripts" / "four_reports" / "company_1_full.json")
            cur: Any = d
            for k in str(spec.get("path") or "").split("."):
                cur = (cur or {}).get(k) if isinstance(cur, dict) else None
            return (len(cur) if isinstance(cur, list) else None), "产物 %s 条数" % spec.get("path")
    except Exception as exc:                  # noqa: BLE001 - 留痕，不静默
        return None, "权威值取值异常：%s" % str(exc)[:80]
    return None, "未知 authority.kind：%s" % kind


# --------------------------------------------------------------------------
# (b) 文档取值（唯一实现）
# --------------------------------------------------------------------------
def read_lines(name: str) -> List[str]:
    p = doc_dir() / name
    if not p.is_file():
        return []
    return p.read_text(encoding="utf-8", errors="replace").split("\n")


def quote_files() -> set:
    """**允许引用旧值作对照**的文件（修订记录/诊断报告/补做记录）—— Skill 1/5 对其跳过 claims 校验。

    ⚠ 为什么必须显式登记（实测）：这些文件**按设计要求**要写「修订前 → 修订后」，
      其"修订前"列必然包含旧值；若不排除，Skill 1 会把**合规的对照**判成"数字写错"（假红）。
    """
    return {str(x) for x in (config().get("quote_files") or [])}


def claims_of(number_id: str) -> List[Dict[str, Any]]:
    for n in (config().get("numbers") or []):
        if isinstance(n, dict) and str(n.get("id")) == number_id:
            return [c for c in (n.get("claims") or []) if isinstance(c, dict)]
    return []


def extract_claim(claim: Dict[str, Any]) -> List[Tuple[int, int, str]]:
    """在一份文件里按声明正则抓"文档写的值" → `[(行号, 值, 该行文本)]`。"""
    rx = re.compile(str(claim.get("regex") or ""))
    out: List[Tuple[int, int, str]] = []
    for i, line in enumerate(read_lines(str(claim.get("file"))), start=1):
        for m in rx.finditer(line):
            try:
                out.append((i, int(m.group(1)), line.strip()))
            except (IndexError, ValueError):
                continue
    return out


def check_numbers() -> List[Dict[str, Any]]:
    """**Skill 1 判据**：文档里写的每个数字必须 == 权威值（现算）。"""
    issues: List[Dict[str, Any]] = _guard(_CFG, "文档一致性数据表", ["numbers"])
    nums = [n for n in (config().get("numbers") or []) if isinstance(n, dict)]
    if not nums:
        if not issues:
            issues.append({"level": "ERROR", "where": "config/doc_consistency.json",
                           "detail": "未登记任何数字权威映射 —— 判据为空，**不得静默通过**"})
        return issues
    for n in nums:
        val, why = authority_value(n.get("authority") or {})
        if val is None:
            issues.append({"level": "WARN", "where": "config/doc_consistency.json",
                           "detail": "数字「%s」权威值取不到：%s" % (n.get("name"), why)})
            continue
        _must = {str(x) for x in (n.get("must_state_in") or [])}
        for claim in (n.get("claims") or []):
            # ★ 对照文件（quote_files）默认跳过（它们按设计要求引用旧值）。
            #   但**同一个文件里也可能有"必须等于当前权威值"的数字**（如 5 个 Skill 文档的
            #   "全量 1456 passed"）⇒ 用 `claims[].enforce = true` **逐条**强制校验。
            #   （实测教训：只用"文件级豁免"太粗 ⇒ 整份文件的所有数字都失去校验 = 覆盖漏洞。）
            if str(claim.get("file")) in quote_files() and not claim.get("enforce"):
                continue
            hits = extract_claim(claim)
            if not hits:
                _lvl = "ERROR" if str(claim.get("file")) in _must else "WARN"
                issues.append({"level": _lvl,
                               "where": "%s（未命中声明正则）" % claim.get("file"),
                               "detail": "数字「%s」在该文件里%s**找不到声明位置**"
                                         "（正则 `%s`）—— %s"
                                         % (n.get("name"),
                                            "**必须声明**却" if _lvl == "ERROR" else "（正则可能过时）",
                                            claim.get("regex"),
                                            "补写该数字" if _lvl == "ERROR" else "核对该处文本或更新正则声明")})
                continue
            for ln, got, text in hits:
                if got != val:
                    issues.append({"level": "ERROR",
                                   "where": "%s:%d" % (claim.get("file"), ln),
                                   "detail": "数字「%s」文档写 %d、权威值 %d（%s）｜原文：%s"
                                             % (n.get("name"), got, val, why, text[:80])})
    return issues


def number_authority(number_id: str) -> Dict[str, Any]:
    """按数字 id 取它的 `authority` 声明（供"合计 == 权威值"复用）。"""
    for n in (config().get("numbers") or []):
        if isinstance(n, dict) and str(n.get("id")) == str(number_id):
            return n.get("authority") or {}
    return {}


def check_sums() -> List[Dict[str, Any]]:
    """**Skill D1 判据（文档自洽）**：分项加总必须 == 合计，且合计 == 权威值。

    ⚠ 实测事故：`01` §6 写「分项 3+4+3+3+3+15 = 31」而合计写 **28**（**文档自相矛盾**）。
      只抓单值的正则（`claims[].regex`）**抓不到这类错** —— 它只看第一个数字。
      故新增本判据：`sum_checks` 声明「哪份文件的哪一句是分项、合计值必须等于哪个权威数字」。
    """
    issues: List[Dict[str, Any]] = _guard(_CFG, "文档一致性数据表", ["sum_checks"])
    specs = [s for s in (config().get("sum_checks") or []) if isinstance(s, dict)]
    if not specs:
        return [i for i in issues if i["level"] == "ERROR"] or [
            {"level": "ERROR", "where": "config/doc_consistency.json",
             "detail": "未登记任何「分项加总」判据 —— 判据为空，**不得静默通过**"}]
    for s in specs:
        fname = str(s.get("file"))
        rx = re.compile(str(s.get("items_regex") or ""))
        hits = 0
        for ln, line in enumerate(read_lines(fname), start=1):
            m = rx.search(line)
            if not m:
                continue
            hits += 1
            items = [int(x) for x in re.findall(r"\d+", m.group(1))]
            stated = int(m.group(2))
            if sum(items) != stated:
                issues.append({"level": "ERROR", "where": "%s:%d" % (fname, ln),
                               "detail": "「%s」**分项加总 %d ≠ 合计 %d**（分项 %s）—— 文档自相矛盾"
                                         % (s.get("name"), sum(items), stated,
                                            " + ".join(str(x) for x in items))})
            nid = str(s.get("must_equal_number") or "")
            if nid:
                val, why = authority_value(number_authority(nid))
                if val is None:
                    issues.append({"level": "ERROR", "where": "config/doc_consistency.json",
                                   "detail": "「%s」引用的数字「%s」权威值取不到：%s"
                                             % (s.get("name"), nid, why)})
                elif stated != val:
                    issues.append({"level": "ERROR", "where": "%s:%d" % (fname, ln),
                                   "detail": "「%s」合计写 %d、权威值 %d（%s）"
                                             % (s.get("name"), stated, val, why)})
        if hits == 0:
            lvl = "ERROR" if fname in {str(x) for x in (s.get("must_state_in") or [])} else "WARN"
            issues.append({"level": lvl, "where": fname,
                           "detail": "「%s」的**分项加总表达式找不到**（正则 `%s` 未命中）"
                                     % (s.get("name"), s.get("items_regex"))})
    return issues


def check_consistency() -> List[Dict[str, Any]]:
    """**Skill D1 判据（同文件内部自洽）**：同一指标在同一文件里出现多次时，**单值必须彼此相等**。

    ⚠ 为什么需要它（实测）：`05` §2 表格写 `62.04s`，而同一文件文末自证段写 `214.90s`
      —— **同一份报告里两个耗时**，读者无从判断哪个可信。

    ⚠ 为什么**不**把它做成"数值权威"：耗时是**易变值**（同代码多次跑实测 55.94~214.90s，取决于机器负载）。
      若登记为数值权威 ⇒ 每跑一次都必然与文档不等 ⇒ **必然长期假红** ⇒ 判据迟早被人为关掉。
      ⇒ 正确口径 = **文件内自洽（本判据） + 必须注明「与本次 passed 同次运行」**（`required_any`）。

    数据表：`consistency_checks[] = {id, name, file, regexes[], exclude_if_range, required_any, must_state_in}`
    新增一个"必须自洽的指标" = **加一行数据**。
    """
    issues: List[Dict[str, Any]] = _guard(_CFG, "文档一致性数据表", ["consistency_checks"])
    specs = [s for s in (config().get("consistency_checks") or []) if isinstance(s, dict)]
    if not specs:
        return [i for i in issues if i["level"] == "ERROR"] or [
            {"level": "ERROR", "where": "config/doc_consistency.json",
             "detail": "未登记任何「同文件自洽」判据 —— 判据为空，**不得静默通过**"}]
    for s in specs:
        fname = str(s.get("file"))
        pats = [str(x) for x in ((s.get("regexes") or []) or ([s.get("regex")] if s.get("regex") else []))]
        hits: List[Tuple[int, str]] = []
        lines = read_lines(fname)
        for rx_src in pats:
            rx = re.compile(rx_src)
            for ln, line in enumerate(lines, start=1):
                for m in rx.finditer(line):
                    val = str(m.group(1))
                    if s.get("exclude_if_range"):
                        # 区间形态（前后紧邻 – — ~ ～ - 至）不算"单值"
                        _tail = line[m.end():m.end() + 1]
                        _head = line[max(0, m.start() - 1):m.start()]
                        if _tail in "–—~～-至" or _head in "–—~～-至":
                            continue
                    hits.append((ln, val))
        hits = sorted(set(hits))
        if not hits:
            lvl = "ERROR" if fname in {str(x) for x in (s.get("must_state_in") or [])} else "WARN"
            issues.append({"level": lvl, "where": fname,
                           "detail": "「%s」在该文件里**找不到声明位置**（正则 %s 未命中）"
                                     % (s.get("name"), " / ".join("`%s`" % x for x in pats))})
            continue
        vals = {v for _, v in hits}
        if len(vals) > 1:
            detail = "、".join("%s（第 %d 行）" % (v, ln) for ln, v in hits)
            issues.append({"level": "ERROR", "where": fname,
                           "detail": "「%s」**同一文件内前后不一致**：%s —— 同一指标的多个单值必须相等"
                                     "（修法：统一为实测值；易变指标请写区间并注明同一口径）"
                                     % (s.get("name"), detail)})
        need = [str(x) for x in (s.get("required_any") or [])]
        if need:
            blob = "\n".join(read_lines(fname))
            if not any(x in blob for x in need):
                issues.append({"level": "ERROR", "where": fname,
                               "detail": "「%s」必须注明口径（文档里必须出现 %s 之一，例如"
                                         "「与本次 passed 同次运行」）—— 否则读者无法判断该值可不可比"
                                         % (s.get("name"), "、".join("「%s」" % y for y in need))})
    return issues


def check_snapshot_records() -> List[Dict[str, Any]]:
    """**Skill D3 判据（快照记录时效性，D3-R4）**：记录类文件的历史值必须**有时点声明**且**与登记一致**。

    ⚠ 为什么需要（实测）：用户复核时看到 `02_被抓记录` 写「权威值 27 / 23」、`06_修正记录` 写「破坏性 3 / 口径锁 6」，
      而 `04_最小检查集` / `05_最终判断` 写 31 / 24 / 7 / 8 ⇒ 直接怀疑「**5 个 Skill 假绿**」。
      追查结论：**不是假绿** —— `02` 是有意登记的对照文件（D1/D3 按设计跳过），而且把豁免撤掉后**仍 0 ERROR**
      （因为**没有任何 claims 扫描它**）。真正的问题是：**这些历史值此前不在任何判据的管辖范围内** ——
      既是「历史观测」（不该按当前值校验），又「无人登记」（**事后把 27 改成 31、把 3 改成 7 都无人发现**）。

    判据（`config/doc_consistency.json → snapshot_records`，数据表驱动）：
      ① 每个登记的记录文件必须含 `marker`（「快照时点」）声明行 —— 用于区分「**当时值** vs **当前值**」；
      ② 对 `probe_patterns` 里每种模式：该文件里命中的数字集合必须与登记的 `expect[模式]` **双向一致** ——
         出现**未登记的历史值** ⇒ ERROR（有人改了记录 / 漏登记）；登记的**历史值丢失** ⇒ ERROR（记录被删改）；
      ③ 某模式在文件里出现却完全没登记 ⇒ ERROR（漏登记）。
      新增一个历史值 = 改一行数据。
    """
    issues: List[Dict[str, Any]] = _guard(_CFG, "文档一致性数据表", ["snapshot_records"])
    if any(i["level"] == "ERROR" for i in issues):
        return issues
    spec = config().get("snapshot_records") or {}
    marker = str(spec.get("marker") or "快照时点")
    pats = [x for x in (spec.get("probe_patterns") or []) if isinstance(x, dict)]
    files = spec.get("files") if isinstance(spec.get("files"), dict) else {}
    if not files:
        return [{"level": "ERROR", "where": "config/doc_consistency.json",
                 "detail": "未登记任何记录文件的快照元数据 —— 判据为空，**不得静默通过**"}]
    for fname in sorted(files):
        info = files[fname] or {}
        expect = info.get("expect") if isinstance(info.get("expect"), dict) else {}
        lines = read_lines(fname)
        if not lines:
            issues.append({"level": "ERROR", "where": fname,
                           "detail": "登记为记录文件但**不存在**（幽灵登记 / 改名后未同步）"})
            continue
        # ① 时点声明
        if not any(marker in l for l in lines):
            issues.append({"level": "ERROR", "where": fname,
                           "detail": "缺**快照时点声明**（须含「%s」字样）—— 读者无法分辨其中的数字是"
                                     "**当时值**还是**当前值**（实测：正因此被误判为「5 个 Skill 假绿」）" % marker})
        # ②③ 逐模式双向比对
        for pt in pats:
            pid = str(pt.get("id"))
            try:
                rx = re.compile(str(pt.get("regex") or "$^"))
            except re.error as exc:
                issues.append({"level": "ERROR", "where": fname,
                               "detail": "探针模式「%s」正则非法：%s" % (pid, exc)})
                continue
            got = sorted({int(m.group(1)) for l in lines for m in rx.finditer(l) if m.groups()})
            exp = [int(x) for x in (expect.get(pid) or [])]
            if not got and not exp:
                continue
            if got and not exp:
                issues.append({"level": "ERROR", "where": "%s（登记表）" % _rel(_CFG),
                               "detail": "`%s` 里出现了「%s」= %s，但**未登记**在 `snapshot_records` —— "
                                         "改一行数据即可（防下次改动无人发现）" % (fname, pid, got)})
                continue
            if exp and not got:
                issues.append({"level": "ERROR", "where": fname,
                               "detail": "登记的「%s」历史值 %s **在文件里已找不到** —— 记录被删改"
                                         "（%s）" % (pid, exp, pt.get("note") or "")})
                continue
            added = sorted(set(got) - set(exp))
            lost = sorted(set(exp) - set(got))
            if added:
                issues.append({"level": "ERROR", "where": fname,
                               "detail": "「%s」出现**未登记的历史值** %s（登记的是 %s）—— 要么记录被改过，"
                                         "要么改了数却没登记" % (pid, added, exp)})
            if lost:
                issues.append({"level": "ERROR", "where": fname,
                               "detail": "「%s」登记的**历史值丢失** %s —— 记录被删改（%s）"
                                         % (pid, lost, pt.get("note") or "")})
    return issues


def check_tables() -> List[Dict[str, Any]]:
    """**Skill D4 判据（文档结构自洽）**：同一 Markdown 表格里，**每一行的列数必须等于表头列数**。

    ⚠ 为什么需要它（实测）：`08` 的「补做新增的未完成事项」表 **表头 5 列 / 数据行 6 列**
      （数据行多了一个「状态」列）⇒ 渲染时**整体串列**：读者看到的"未完成原因"其实是"状态"。
      **Markdown 不报错、任何语法检查都不报、肉眼在小字号下极难发现** ⇒ 必须机检。

    口径：只把"整行以 `|` 开头且以 `|` 结尾"的**连续行**当表格；**跳过围栏代码块**；
    处理单元格内的转义 `\\|`（先替换为占位符再切分）。
    """
    issues: List[Dict[str, Any]] = []
    for p in doc_files():
        lines = p.read_text(encoding="utf-8", errors="replace").split("\n")
        in_fence = False
        group: List[Tuple[int, str]] = []

        def _cells(row: str) -> List[str]:
            body = row.strip()[1:-1] if row.strip().endswith("|") else row.strip()
            return [c.strip() for c in body.replace("\\|", "\x00").split("|")]

        def _flush(grp: List[Tuple[int, str]]) -> None:
            if len(grp) < 2:
                return
            head = _cells(grp[0][1])
            for ln, row in grp[1:]:
                cells = _cells(row)
                if all(set(c) <= set("-: ") and c for c in cells):
                    continue                      # 分隔行 |---|---|
                if len(cells) != len(head):
                    issues.append({"level": "ERROR", "where": "%s:%d" % (p.name, ln),
                                   "detail": "**表格列数与表头不一致**：表头 %d 列、本行 %d 列"
                                             "（第 %d 行）｜表头：%s｜本行：%s"
                                             % (len(head), len(cells), grp[0][0],
                                                " | ".join(head)[:70], " | ".join(cells)[:70])})

        for i, line in enumerate(lines, start=1):
            s = line.strip()
            if s.startswith("```"):
                in_fence = not in_fence
                if group:
                    _flush(group)
                    group = []
                continue
            if in_fence:
                continue
            if len(s) > 1 and s.startswith("|") and s.endswith("|"):
                group.append((i, s))
            else:
                if group:
                    _flush(group)
                    group = []
        if group:
            _flush(group)
    return issues


def check_meta_coverage() -> List[Dict[str, Any]]:
    """**元判据（D1-R9）**：文档里出现的「指标短语 + 数字」**必须已被某条 claims 覆盖**。

    ⚠ 为什么需要它（实测）：上一轮 6 处不一致里 **5 处**属于同一病根 —— **"元事实"（关于事实的事实）
      从未被登记为权威**：「数字权威有几个 / kind 有几种 / 判据有几条 / 反向验证有几例 / 口径锁有几例」。
      文档里明明写着这些数字，但 `numbers` 里没有对应权威 ⇒ **写什么都不校验**。

    本判据把"应登记"变成可机检：登记一份**指标短语模式**清单（`meta_checks[]`），
    对每个匹配行，检查它是否被**任一条 claims**（同一文件）覆盖；**未覆盖 ⇒ ERROR**（"该指标应登记权威"）。
    这样下次新增一种指标短语却忘记登记权威时，会被当场抓住，而不是等人工发现口径打架。
    """
    issues: List[Dict[str, Any]] = _guard(_CFG, "文档一致性数据表", ["meta_checks"])
    specs = [s for s in (config().get("meta_checks") or []) if isinstance(s, dict)]
    if not specs:
        return [i for i in issues if i["level"] == "ERROR"] or [
            {"level": "ERROR", "where": "config/doc_consistency.json",
             "detail": "未登记任何「指标短语覆盖」元判据 —— 判据为空，**不得静默通过**"}]
    claim_pats = []
    for n in (config().get("numbers") or []):
        for c in (n.get("claims") or []):
            claim_pats.append((str(n.get("id")), str(c.get("file")), re.compile(str(c.get("regex") or "$^"))))
    # ★ 扫描范围 = `declaration_scope`（**声明类文件 = 交付物正文**）；
    #   与 `quote_files`（**对照类文件**，允许引用旧值/历史值）是**两个正交维度**：
    #   5 个 Skill 文档既是对照类（要展示旧值）又是声明类（要声明当前事实）⇒ 必须分开表达。
    scope = {str(x) for x in (config().get("declaration_scope") or [])}
    for s in specs:
        rx = re.compile(str(s.get("regex") or "$^"))
        skip = {str(x) for x in (s.get("skip_files") or [])}
        for p in doc_files():
            if p.name in skip:
                continue
            if scope and p.name not in scope:
                continue
            for ln, line in enumerate(p.read_text(encoding="utf-8", errors="replace").split("\n"), start=1):
                m = rx.search(line)
                if not m:
                    continue
                if any(cf == p.name and crx.search(line) for _, cf, crx in claim_pats):
                    continue
                issues.append({"level": "ERROR", "where": "%s:%d" % (p.name, ln),
                               "detail": "**元判据**：文档里出现指标短语「%s」（%s），但**未被任何已登记的 "
                                         "claims 覆盖** ⇒ 该指标**应登记权威**（在 `config/doc_consistency.json` 的 "
                                         "`numbers[]` 加一行，并让 claims 覆盖此写法）；否则「写什么都不校验」"
                                         % (s.get("name"), m.group(0)[:40])})
    return issues


def check_deliverable_naming() -> List[Dict[str, Any]]:
    """**Skill D1 判据（交付物命名规范，D1-R10）**：文件名必须唯一、已登记、前缀合规、不含程度词。

    ⚠ 为什么需要（实测）：同一批次追加 4 轮交付物后，出现 3 份「…修正记录」、2 份「…诊断报告」、
      2 份「…被抓记录」，且**「最终」之后又出「终极」** ⇒ 程度词不可持续、近名难辨、同名难查。
      更进一步：**同一文件名被两轮指令点名**（`修完后5个Skill实跑结果.md`）而我复用了同一份文件
      ⇒ 目录里只有一份、但一个名字出现在多轮清单里，外人核对时就会问「怎么会有同名的交付物？」。

    判据（`config/doc_consistency.json`）：`naming_rules`（规范）+ `deliverable_registry`（登记表 = 唯一权威）；
      ① 目录内**文件名唯一**（防同名）；
      ② 目录里的**每个文件都已登记**（未登记 ⇒ ERROR）；
      ③ 登记表里的**每个文件都真实存在**（幽灵登记 ⇒ ERROR）；
      ④ 命名规范：∈ 常驻前缀白名单 **或** 匹配 `^R<数字>_`；
      ⑤ 文件名**不得含程度词**（`最终/终极/最新/新版/final/latest`）；
      ⑥ 同一 **(轮次, 角色)** 不得重复（防"同题材重复交付"）；
      ⑦ 文件名前缀的轮次必须与登记的轮次一致（`R3_x` ⇒ round 必须 `R3`）。
    """
    issues: List[Dict[str, Any]] = _guard(_CFG, "文档一致性数据表", ["naming_rules", "deliverable_registry"])
    if any(i["level"] == "ERROR" for i in issues):
        return issues
    rules = config().get("naming_rules") or {}
    reg = [r for r in (config().get("deliverable_registry") or []) if isinstance(r, dict)]
    names = [p.name for p in doc_files()]
    where = "%s" % _rel(doc_dir())

    # ① 唯一
    if len(names) != len(set(names)):
        dup = sorted({n for n in names if names.count(n) > 1})
        issues.append({"level": "ERROR", "where": where,
                       "detail": "**出现同名交付物**：%s（文件名必须唯一）" % "、".join(dup)})
    registered = {str(r.get("file")) for r in reg}
    # ② 未登记
    for n in names:
        if n not in registered:
            issues.append({"level": "ERROR", "where": "%s/%s" % (where, n),
                           "detail": "该交付物**未登记**在 `deliverable_registry` —— 新增交付物必须同时登记"
                                     "（文件名/轮次/角色的唯一权威）"})
    # ③ 幽灵登记
    for r in reg:
        if str(r.get("file")) not in names:
            issues.append({"level": "ERROR", "where": "%s（登记表）" % _rel(_CFG),
                           "detail": "登记了 `%s` 但目录里**不存在**（幽灵登记 / 改名后未同步）" % r.get("file")})
    # ④ 前缀规范
    import re as _re
    ok_pre = tuple(str(x) for x in (rules.get("resident_prefix_ok") or []))
    ok_exact = {str(x) for x in (rules.get("resident_files") or [])}
    rx_round = _re.compile(str(rules.get("round_prefix_pattern") or r"^R\d+_"))

    def _is_resident(n: str) -> bool:
        return n in ok_exact or n.startswith(ok_pre)

    for n in names:
        if not (_is_resident(n) or rx_round.search(n)):
            issues.append({"level": "ERROR", "where": "%s/%s" % (where, n),
                           "detail": "命名不合规：必须是**常驻名**（%s 或 %s）**或**以 `R<轮次>_` 开头"
                                     % ("、".join(sorted(ok_exact)), "、".join(ok_pre[:3]) + "…")})
    # ⑤ 禁程度词（★ 只对**轮次文件**生效：常驻名是指令契约，如《最终判断》不得因含「最终」而改）
    for w in (rules.get("forbidden_words") or []):
        for n in names:
            if _is_resident(n):
                continue
            if str(w) in n:
                issues.append({"level": "ERROR", "where": "%s/%s" % (where, n),
                               "detail": "**轮次文件的文件名含程度词**「%s」—— 轮次必须用编号前缀表达"
                                         "（`R1_/R3_/R4_`）；程度词不可持续（实测：「最终」之后又出「终极」）"
                                         "（注：常驻名如 `最终判断.md` 由指令给定，不受此限）" % w})
    # ⑥ (轮次, 角色) 不重复
    seen2 = {}
    for r in reg:
        k = (str(r.get("round")), str(r.get("role")))
        if k in seen2:
            issues.append({"level": "ERROR", "where": "%s（登记表）" % _rel(_CFG),
                           "detail": "**同一（轮次, 角色）重复**：%s / %s ↔ %s（同一轮同一角色只应一份交付物）"
                                     % (k[0], k[1], seen2[k])})
        seen2[k] = str(r.get("file"))
    # ⑦ 前缀与轮次一致
    for r in reg:
        n = str(r.get("file"))
        m = rx_round.match(n)
        if m and not n.startswith(str(r.get("round")) + "_"):
            issues.append({"level": "ERROR", "where": "%s（登记表）" % _rel(_CFG),
                           "detail": "`%s` 的前缀轮次与登记的轮次「%s」不一致" % (n, r.get("round"))})
    return issues


def check_rules() -> List[Dict[str, Any]]:
    """**Skill 2 判据**：规则编号引用一致（有效性 + 覆盖完整性）。"""
    issues: List[Dict[str, Any]] = _guard(_CFG, "文档一致性数据表", ["rule_catalog", "rule_id_pattern"])
    cat = [r for r in (config().get("rule_catalog") or []) if isinstance(r, dict)]
    pat = re.compile(str(config().get("rule_id_pattern") or r"TDS-[①-⑩0-9]+"))
    if not cat:
        if not issues:
            issues.append({"level": "ERROR", "where": "config/doc_consistency.json",
                           "detail": "规则清单为空 —— 判据为空，**不得静默通过**"})
        return issues
    known = {str(r.get("id")) for r in cat}
    # ★ 逐字符校验（数据表 `rule_id_parse` 声明的口径）：「TDS-⑤⑥⑦⑧」是**合法的集合引用**
    #   （＝⑤⑥⑦⑧ 四条），拆成单个编号逐一核对；整体当一个 id 会**假红**（实测）。
    _quote = quote_files()
    for p in doc_files():
        lines = p.read_text(encoding="utf-8", errors="replace").split("\n")
        for i, line in enumerate(lines, start=1):
            # ⚠ 对照/样例文件（修订记录、Skill 化文档等）**允许引用尚不存在的编号**以演示判据
            #   （如"新增 TDS-⑩ 而不更新引用 ⇒ 应报红"）⇒ 与 D1/D5 同口径跳过。
            if p.name in _quote:
                break
            for m in pat.finditer(line):
                for ch in m.group(0)[len("TDS-"):]:
                    rid = "TDS-%s" % ch
                    if rid not in known:
                        issues.append({"level": "ERROR", "where": "%s:%d" % (p.name, i),
                                       "detail": "引用了**不存在**的规则编号「%s」（出自「%s」；"
                                                 "规则清单里没有 ⇒ 笔误或漏登记）"
                                                 % (rid, m.group(0))})
        # 覆盖完整性：指定文件必须列出**全部**规则
        if p.name in (config().get("rule_catalog_files") or []):
            blob = p.read_text(encoding="utf-8", errors="replace")
            missing = sorted(known - set(pat.findall(blob)))
            if missing:
                issues.append({"level": "ERROR", "where": p.name,
                               "detail": "该文件须完整列出规则清单，缺：%s（新增规则后未同步）"
                                         % "、".join(missing)})
    return issues


def _fenced_spans(text: str) -> List[Tuple[int, int]]:
    """围栏代码块（``` … ```）在全文里的字符区间 —— **"引用区"**。

    ⚠ 为什么需要：交付物里**必须**贴出「依据命令 + 实测输出」（用户硬约束），
      而"实测输出"本身就可能**逐字包含旧值**（如 `grep -rnE "(25 例|25 passed|…)"` 的展开式命令）。
      那不叫"残留"，那叫**引用**。故：**围栏内的内容不计残留**。
      防滥用：围栏外出现旧值仍**必须**报 ERROR（反向验证见
      `tests/test_doc_consistency_skills.py::TestNewJudgments::test_residue_outside_fence_still_red`）。
    """
    spans: List[Tuple[int, int]] = []
    pos = 0
    start = -1
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            if start < 0:
                start = pos
            else:
                spans.append((start, pos + len(line)))
                start = -1
        pos += len(line) + 1
    if start >= 0:
        spans.append((start, len(text)))
    return spans


def check_residue() -> List[Dict[str, Any]]:
    """**Skill 3 判据**：按**同义词典**展开检索旧值残留（未收录写法 ⇒ WARN 提示补词典）。"""
    issues: List[Dict[str, Any]] = _guard(_SYN, "同义写法词典", ["stale_values", "scan_scope"])
    syn = synonyms()
    scope = syn.get("scan_scope") or {}
    excl = set(scope.get("exclude_files") or [])
    items = [s for s in (syn.get("stale_values") or []) if isinstance(s, dict)]
    if not items:
        if not issues:
            issues.append({"level": "ERROR", "where": "config/doc_synonyms.json",
                           "detail": "同义词典为空 —— 判据为空，**不得静默通过**"})
        return issues
    globs: List[Path] = []
    for g in (scope.get("include_globs") or []):
        globs.extend(sorted(ROOT.glob(str(g))))
    skip_fenced = bool(scope.get("skip_fenced_blocks", True))
    # ★ 口径补充：**「已登记的当前值声明行」不计残留**。
    #   实测病根：新增权威后「正例/自证 25 例」的 25 恰好等于历史旧值「25 例」⇒ 假阳性。
    #   判据应当是"**旧值**不得残留"，而"当前值恰好等于某个旧值"**不是**残留。
    cur_decl: Dict[str, set] = {}
    for n in (config().get("numbers") or []):
        val, _why = authority_value(n.get("authority") or {})
        if val is None:
            continue
        for c in (n.get("claims") or []):
            f = str(c.get("file"))
            try:
                rx_c = re.compile(str(c.get("regex") or "$^"))
            except re.error:
                continue
            for ln, line in enumerate(read_lines(f), start=1):
                if any(m.group(1) == str(val) for m in rx_c.finditer(line) if m.groups()):
                    cur_decl.setdefault(f, set()).add(ln)
    for p in globs:
        if p.name in excl:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        fences = _fenced_spans(text) if skip_fenced else []
        _skip_lines = cur_decl.get(p.name, set())
        for s in items:
            for v in (s.get("variants") or []):
                v = str(v)
                if not v:
                    continue
                start = 0
                while True:
                    idx = text.find(v, start)
                    if idx < 0:
                        break
                    start = idx + len(v)
                    # ★ 引用区（围栏代码块）内不计残留
                    if any(a <= idx < b for a, b in fences):
                        continue
                    # ★ 区间/并列形态不算残留（实测假红）：左右紧邻为 – - ~ ～ 至 的，
                    #   是"浮动区间/并列"写法（如「55.94–86.36s」），**允许保留**。
                    _l = text[idx - 1] if idx > 0 else ""
                    _tail = text[idx + len(v): idx + len(v) + 2]
                    # 跳过可选单位（`s`/`秒`）再看右侧是否为区间分隔符（实测「55.94s–86.36s」）
                    _r = ""
                    for _off in (0, 1):
                        if idx + len(v) + _off < len(text):
                            _c = text[idx + len(v) + _off]
                            if _off == 0 and _c in "s秒":
                                continue
                            _r = _c
                            break
                    if _l in "–—~～-至" or _r in "–—~～-至":
                        continue
                    ln = text[:idx].count("\n") + 1
                    if ln in _skip_lines:      # ★ 已登记的当前值声明行 ⇒ 不计残留
                        continue
                    issues.append({"level": "ERROR", "where": "%s:%d" % (p.name, ln),
                                   "detail": "残留旧值「%s」（同义写法「%s」，应改为「%s」）"
                                             % (s.get("old"), v, s.get("replaced_by"))})
    # 词典自检：旧值本体若在词典里找不到（说明登记不全）⇒ WARN
    for s in items:
        vs = [str(x) for x in (s.get("variants") or [])]
        if str(s.get("old")) not in vs:
            issues.append({"level": "WARN", "where": "config/doc_synonyms.json",
                           "detail": "旧值「%s」未收录在自身 variants 里（词典可能漏写法）" % s.get("old")})
    return issues


def parse_todo_table() -> Dict[str, Dict[str, str]]:
    """解析 `08_未完成事项清单.md` 的「未完成事项清单」表 → `{U-id: {状态, 行}}`。"""
    out: Dict[str, Dict[str, str]] = {}
    lines = read_lines("08_未完成事项清单.md")
    for i, line in enumerate(lines, start=1):
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        m = re.match(r"^\*{0,2}(U\d+)\*{0,2}$", cells[0])
        if not m:
            continue
        # 状态列：优先取"状态"字样所在列；否则取最后一列里的状态词
        status = ""
        for c in cells:
            for w in (config().get("status_vocab") or []):
                if w in c:
                    status = w
                    break
            if status:
                break
        out[m.group(1)] = {"状态": status, "行": str(i), "原文": line.strip()[:120]}
    return out


def check_todo_status() -> List[Dict[str, Any]]:
    """**Skill 4 判据**：未完成清单的状态必须与「补做记录」声明一致。"""
    issues: List[Dict[str, Any]] = _guard(_CFG, "文档一致性数据表", ["status_vocab", "todo_declaration_marker"])
    vocab = [str(v) for v in (config().get("status_vocab") or [])]
    if not vocab:
        if not issues:
            issues.append({"level": "ERROR", "where": "config/doc_consistency.json",
                           "detail": "未登记状态词表 —— 判据为空，**不得静默通过**"})
        return issues
    todos = parse_todo_table()
    if not todos:
        return [{"level": "ERROR", "where": "08_未完成事项清单.md",
                 "detail": "未解析到任何未完成事项（U1..Un）—— 清单缺失或表头格式变了"}]
    for tid, info in todos.items():
        if not info.get("状态"):
            issues.append({"level": "ERROR", "where": "08_未完成事项清单.md:%s" % info.get("行"),
                           "detail": "未完成项 %s **缺状态字段**（状态须 ∈ %s）" % (tid, "/".join(vocab))})
    # ★ 补做记录里的声明：**只在标注了「状态同步声明」标记的行上抽取**
    #   （实测：初版扫全文，结果**我自己的解释性散文**「把 U1 那一行的状态改回『未开始』」
    #    被判成"补做记录声明 U1 = 未开始"，与清单里的「已修复」冲突 ⇒ **自造假红**。
    #    口径改为：声明必须写在带标记的段落里 ⇒ 散文不可能被误判，且"没写声明"能被发现。）
    marker = str(config().get("todo_declaration_marker") or "状态同步声明")
    lines = read_lines("08_未完成事项清单.md")
    decl_lines = [(i, ln) for i, ln in enumerate(lines, start=1) if marker in ln]
    if not decl_lines:
        issues.append({"level": "ERROR", "where": "08_未完成事项清单.md",
                       "detail": "未找到任何「%s」标记行 —— 状态同步判据**无法执行**"
                                 "（补做完成后必须显式声明，否则「清单状态」没有第二个出处可比对）"
                                 % marker})
    for i, line in decl_lines:
        for m in re.finditer(r"(U\d+)\s*[^。\n]{0,12}?[已修]?为?[「\"']?(%s)" % "|".join(vocab), line):
            tid = m.group(1)
            claimed = m.group(2)
            got = (todos.get(tid) or {}).get("状态") or ""
            if not got:
                continue
            if got != claimed:
                issues.append({"level": "ERROR", "where": "08_未完成事项清单.md:%d" % i,
                               "detail": "补做记录声明 %s 为「%s」，而未完成清单里记的是「%s」—— 状态未同步"
                                         % (tid, claimed, got)})
    return issues


def check_ref_graph() -> List[Dict[str, Any]]:
    """**Skill 5 判据**：引用关系图里"下游必须标注上游数字"，未标注 ⇒ ERROR。"""
    issues: List[Dict[str, Any]] = _guard(_CFG, "文档一致性数据表", ["ref_graph", "numbers"])
    graph = [e for e in (config().get("ref_graph") or []) if isinstance(e, dict)]
    if not graph:
        if not issues:
            issues.append({"level": "ERROR", "where": "config/doc_consistency.json",
                           "detail": "引用关系图为空 —— 判据为空，**不得静默通过**"})
        return issues
    for e in graph:
        for num in (e.get("numbers") or []):
            claims = claims_of(str(num))
            for dn in (e.get("down") or []):
                if str(dn) in quote_files():
                    continue                  # 对照文件不要求标注当前权威值
                hit = [c for c in claims if str(c.get("file")) == dn]
                if not hit:
                    issues.append({"level": "ERROR", "where": str(dn),
                                   "detail": "下游文件未声明上游数字「%s」的权威映射"
                                             "（规则：下游引用上游数据必须标注来源；"
                                             "修法：在 config/doc_consistency.json 的该数字下加一行 claims）" % num})
                    continue
                if not extract_claim(hit[0]):
                    issues.append({"level": "ERROR", "where": str(dn),
                                   "detail": "下游文件声明了数字「%s」但**实际未写**（正则 `%s` 未命中）"
                                             % (num, hit[0].get("regex"))})
    return issues


def affected_downstream(upstream_file: str) -> List[str]:
    """上游变更 → 受影响的下游文件清单（Skill 5 的"通知"能力）。"""
    out: List[str] = []
    for e in (config().get("ref_graph") or []):
        if not isinstance(e, dict) or str(e.get("up")) != str(upstream_file):
            continue
        for d in (e.get("down") or []):
            if d not in out:
                out.append(str(d))
    return out
