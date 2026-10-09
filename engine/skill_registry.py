# -*- coding: utf-8 -*-
"""Skill 规范登记表与校验器（用户第 3 批 任务1「Skill 通用结构规范」的可机检形式）。

## 为什么要有

"规范写在文档里"只能约束写文档那一刻。登记表 + 校验器让规范**可被机器检查**：
module 改名/删除、入口函数被重命名、声称的测试文件不存在、依赖闭环、
数据表路径失效、把"未量化约定"漏写 —— 这些**在闸门里是 ERROR**。

## 字段（唯一权威 = `config/skill_specs.json` 的 `fields`）

`id` `name` `version` `impl` `entry_points` `input_schema` `output_schema`
`unquantified` `unquantified_convention` `params` `deps` `tests` `log_fields`

## 口径

- **`unquantified=true` 的 Skill 必须写清"取不到值怎么办"**（本项目最贵的教训：
  用 0 或默认值顶替 ⇒ 结论照常输出）。漏写 = ERROR。
- **`params` 是可调参数的去处**：`{"kind":"config","path":…}` 或 `{"kind":"in_code","ref":"module.attr"}`，
  两者都可机检存在性 ⇒ "新增同类对象只加一行数据、不改分支"这句话能被验证。
- **`tests` 允许为空**（有些 Skill 靠上层集成测试覆盖），但**空集会被计数并打印**：
  未覆盖是可见的，不是隐形的（禁止"看起来有测试"）。
- **新增一个 Skill 只加一条数据**，不改本模块逻辑。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

_ROOT = Path(__file__).resolve().parent.parent
_SPEC_PATH = _ROOT / "config" / "skill_specs.json"

#: 必填字段（★ 与 `config/skill_specs.json` 的 `fields` 必须一致，见 `validate()`）
SPEC_FIELDS: Tuple[str, ...] = (
    "id", "name", "version", "impl", "entry_points", "input_schema", "output_schema",
    "unquantified", "unquantified_convention", "params", "deps", "tests", "log_fields",
)

_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")

_CACHE: Optional[Dict[str, Any]] = None


def load_specs() -> Dict[str, Any]:
    global _CACHE
    if _CACHE is None:
        try:
            _CACHE = json.loads(_SPEC_PATH.read_text(encoding="utf-8"))
        except Exception:
            _CACHE = {"schema": 0, "skills": []}
    if not isinstance(_CACHE, dict):
        _CACHE = {"schema": 0, "skills": []}
    return _CACHE


def specs() -> List[Dict[str, Any]]:
    return [s for s in (load_specs().get("skills") or []) if isinstance(s, dict)]


def spec_of(skill_id: str) -> Optional[Dict[str, Any]]:
    for s in specs():
        if s.get("id") == skill_id:
            return s
    return None


def declared_fields() -> Tuple[str, ...]:
    f = load_specs().get("fields")
    return tuple(f) if isinstance(f, list) and f else SPEC_FIELDS


def _defines(path: Path, name: str) -> bool:
    """`path` 里是否存在顶层或类内的 `def name(`（按行首匹配，避免命中调用）。"""
    if not path.exists():
        return False
    try:
        txt = path.read_text(encoding="utf-8")
    except Exception:
        return False
    return bool(re.search(r"^\s*def\s+%s\s*\(" % re.escape(name), txt, re.M))


def _has_test(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        return bool(re.search(r"^\s*def\s+test_\w+\s*\(", path.read_text(encoding="utf-8"), re.M))
    except Exception:
        return False


def validate() -> List[str]:
    """校验登记表，返回问题描述（空 = 合规）。全部判据均为**可机检**事实。"""
    probs: List[str] = []
    reg = load_specs()
    if int(reg.get("schema") or 0) < 1:
        probs.append("skill_specs.json schema 缺失或版本过低")
    # 字段声明必须与代码口径一致（防"文档说的字段"与"校验器认的字段"不一致）
    if tuple(reg.get("fields") or ()) != SPEC_FIELDS:
        probs.append("登记表 fields 与校验器 SPEC_FIELDS 不一致：%s vs %s"
                     % (reg.get("fields"), list(SPEC_FIELDS)))
    ids: List[str] = []
    for i, s in enumerate(specs()):
        tag = "第 %d 条(%s)" % (i + 1, s.get("id") or "无 id")
        for f in SPEC_FIELDS:
            if f not in s:
                probs.append("%s 缺字段 %s" % (tag, f))
        extra = set(s) - set(SPEC_FIELDS)
        if extra:
            probs.append("%s 含未登记字段 %s（新增字段须同时改 SPEC_FIELDS 与登记表）"
                         % (tag, sorted(extra)))
        sid = str(s.get("id") or "")
        if sid:
            ids.append(sid)
            if not _ID_RE.match(sid):
                probs.append("%s id 非蛇形小写" % tag)
        if not _VERSION_RE.match(str(s.get("version") or "")):
            probs.append("%s version 非语义化 X.Y.Z：%s" % (tag, s.get("version")))
        impl = str(s.get("impl") or "")
        p = _ROOT / impl
        if not impl or not p.exists():
            probs.append("%s impl 文件不存在：%s" % (tag, impl))
        else:
            for ep in (s.get("entry_points") or []):
                if not _defines(p, str(ep)):
                    probs.append("%s impl 内未定义入口 %s" % (tag, ep))
        if not str(s.get("input_schema") or "").strip():
            probs.append("%s input_schema 为空" % tag)
        if not str(s.get("output_schema") or "").strip():
            probs.append("%s output_schema 为空" % tag)
        if bool(s.get("unquantified")) and not str(s.get("unquantified_convention") or "").strip():
            probs.append("%s 声明可能取不到值，但未写 unquantified_convention（口径缺失）")
        if not str(s.get("log_fields") or "").strip():
            probs.append("%s log_fields 为空（改了要看得见）" % tag)
        for prm in (s.get("params") or []):
            if not isinstance(prm, dict):
                probs.append("%s params 项非对象：%r" % (tag, prm))
                continue
            kind = str(prm.get("kind") or "")
            if kind == "config":
                if not (_ROOT / str(prm.get("path") or "")).exists():
                    probs.append("%s 参数文件不存在：%s" % (tag, prm.get("path")))
            elif kind == "in_code":
                ref = str(prm.get("ref") or "")
                mod_name, _, attr = ref.rpartition(".")
                if not mod_name or not attr:
                    probs.append("%s in_code 参数引用格式非法：%s" % (tag, ref))
                else:
                    mp = _ROOT / (mod_name.replace(".", "/") + ".py")
                    if not mp.exists():
                        probs.append("%s in_code 参数所在模块不存在：%s" % (tag, ref))
                    elif not (re.search(r"^%s\s*(?::[^=]+)?=" % re.escape(attr),
                                        mp.read_text(encoding="utf-8"), re.M)
                              or _defines(mp, attr)):
                        probs.append("%s in_code 参数未定义：%s" % (tag, ref))
            else:
                probs.append("%s params kind 非法（须 config|in_code）：%r" % (tag, kind))
        for t in (s.get("tests") or []):
            if not _has_test(_ROOT / str(t)):
                probs.append("%s 声明的测试文件不存在或无测试用例：%s" % (tag, t))
    # id 唯一
    dup = {x for x in ids if ids.count(x) > 1}
    for d in sorted(dup):
        probs.append("Skill id 重复：%s" % d)
    # deps 必须已登记、不得自依、不得成环
    known = set(ids)
    graph: Dict[str, Set[str]] = {}
    for s in specs():
        sid = str(s.get("id") or "")
        deps = [str(d) for d in (s.get("deps") or [])]
        graph[sid] = set(deps)
        for d in deps:
            if d == sid:
                probs.append("Skill %s 依赖自己" % sid)
            elif d not in known:
                probs.append("Skill %s 依赖未登记 Skill：%s" % (sid, d))

    def _cycle(node: str, stack: List[str], seen: Set[str]) -> Optional[List[str]]:
        if node in stack:
            return stack[stack.index(node):] + [node]
        if node in seen:
            return None
        seen.add(node)
        for nxt in graph.get(node, ()):
            r = _cycle(nxt, stack + [node], seen)
            if r:
                return r
        return None

    _seen: Set[str] = set()
    for n in graph:
        c = _cycle(n, [], _seen)
        if c:
            probs.append("Skill 依赖成环：%s" % " → ".join(c))
            break
    return probs


def coverage() -> Dict[str, Any]:
    """登记口径的**可见性台账**：多少 Skill 有回归测试、多少声明了未量化约定。"""
    ss = specs()
    no_test = [str(s.get("id")) for s in ss if not (s.get("tests") or [])]
    unq = [str(s.get("id")) for s in ss if s.get("unquantified")]
    return {"skills": len(ss), "with_tests": len(ss) - len(no_test),
            "without_tests": no_test, "unquantified_skills": unq,
            "ids": [str(s.get("id")) for s in ss]}


__all__ = ["SPEC_FIELDS", "specs", "spec_of", "declared_fields",
           "validate", "coverage"]
