# -*- coding: utf-8 -*-
"""**规则条件 DSL 解释器** —— T-6「规则外置」条件类的唯一权威（2026-10-13）。

## 这一层解决什么

T-6 裁定为**三层渐进**：

| 层 | 判据（是否需要上下文） | 现状 | 本模块的角色 |
|---|---|---|---|
| **阈值类** | 否，单值参数 | **已外置**（`config/*.json` 的 `params`） | 不涉及 |
| **条件类** | 部分，需字段比较 | 候选库已有 `logic` 表达式，但**无解释器** | ★ **本模块** |
| **要件化类** | 是，需要件组合 + 反证 + 序号语义 | 在 Python（`engine/tax_redlines.py`） | 不涉及（**留 Python**） |

候选库三条清单（`config/rulelist_v{1,11,12}.json`）的规则**全部带机器可读的 `logic`**，
语言极小（实测算子分布；条数与缺口口径见 `config/rule_dsl_scope.json`，由
`scripts/_gen_rule_dsl_scope.py` 现算 —— **本模块不硬编码条数**）：

    比较 > 278 / = 140（写作 `=`，语义为 `==`）/ != 39 / < 30
    and 203 / not 20 / or 1 ；abs 45 / min 1 ；四则算术 85 ；「for n months」7（**不可外置**）

⇒ 本模块把该语言**实现为可求值的解释器**，使「改规则不改代码」成为可测量的事实。

## 三条硬约束（写进实现，不写进注释）

1. **三值逻辑**：字段缺失 / 参数未登记（如 `region_params` 的待核项）/ 除零 ⇒ **`UNKNOWN`**，
   **绝不默认 False 或 True**。理由：项目铁律「取不到数据时明确说明未确定，绝不用默认值静默顶替」
   —— 若缺数据默认 False，等于把「没查」说成「没问题」。
2. **不取数**：本模块**只求值**，变量值由调用方注入（`resolver`）。
   取数口径的唯一权威是 `config/rulelist_v*.json::var_map` 与各引擎模块；本模块不复制这些口径。
3. **函数白名单**：未登记函数 ⇒ 解析期报错（不静默当未知变量），防止悄悄引入新语义。

用法::

    from engine.rule_dsl import compile_expr, evaluate
    r = compile_expr("output_tax - input_tax > params.gap and output_tax > 0")
    r.identifiers          # {'output_tax', 'input_tax'}
    r.params_used          # {'gap'}
    evaluate(r, {"output_tax": 120, "input_tax": 30}, {"gap": 5})   # True
    evaluate(r, {"output_tax": 120}, {"gap": 5})                    # None（缺 input_tax）

闸门：`tools/audit_consistency.py::check_rule_dsl_and_externalizable`
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

#: 允许的函数名（白名单）。新增须同时改这里与闸门的期望集（显式登记，不隐式支持）。
ALLOWED_FUNCS: Tuple[str, ...] = ("abs", "min", "max")

#: 布尔字面量（`true`/`false` 在候选库中作为值出现，实测 45+18 处；
#: 若当作变量名处理会误判为"字段未取到值" ⇒ 必须按字面量解析）。
_BOOL_LITERALS: Dict[str, bool] = {"true": True, "false": False}

#: `X not <adj>` 语法的**显式白名单**（候选库实测 16+1 处自然语言否定）。
#: 语义统一为 `not X`（X 须为布尔值）。**未列入的形容词一律报错**，
#: 以免"看起来像自然语言就猜语义"（项目铁律：不得静默顶替）。
NEG_ADJ: Tuple[str, ...] = ("met", "optimal", "satisfied", "applicable")

#: 比较运算符（`=` 在候选库中语义即 `==`，实测 140 处）
_CMP_OPS: Tuple[str, ...] = (">=", "<=", "!=", "==", ">", "<", "=")

#: 明确**不支持**的语法（须如实报出，不得静默当变量）。实测：`for n months`（4 条）、
#: `A not in B`（3 条，**集合语义**，非数值比较）。
_UNSUPPORTED_PAT: Tuple[Tuple[str, str], ...] = (
    (r"\bnot\s+in\b", "集合成员判定（`not in`，需集合值语义）"),
    (r"\bin\b\s*[\(\[]", "集合成员判定（`in [...]`）"),
    (r"\bfor\b.*\bmonth", "时间窗/循环语法（for n months）"),
    (r"\bfor\b", "'for' 循环"),
    (r"\bwhile\b", "'while' 循环"),
)


class DslError(ValueError):
    """解析/求值错误（解析期抛出；求值期的数据缺失用 UNKNOWN 表达，不抛）。"""


class UnsupportedSyntax(DslError):
    """该表达式超出 DSL 表达力（如时间窗/循环）⇒ 属**要件化类**，应留在 Python。"""


# ══════════════════════════════════════════════════════════════════════════════
#  词法
# ══════════════════════════════════════════════════════════════════════════════

_TOKEN_RE = re.compile(r"""
    (?P<num>\d+(?:\.\d+)?)
  | (?P<op>>=|<=|!=|==|>|<|=|\+|-|\*|/|\(|\)|,)
  | (?P<ident>[A-Za-z_][A-Za-z0-9_&]*)
  | (?P<ws>\s+)
""", re.VERBOSE)

#: 视为关键字而非变量的标识符
_KEYWORDS = ("and", "or", "not")


def _tokenize(src: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    i, n = 0, len(src)
    while i < n:
        m = _TOKEN_RE.match(src, i)
        if not m:
            # 中文/其他字符：如实报错（不猜测语义）
            raise DslError("无法识别的字符：%r（位置 %d）" % (src[i], i))
        kind = m.lastgroup
        text = m.group()
        i = m.end()
        if kind == "ws":
            continue
        if kind == "ident" and text in _KEYWORDS:
            out.append(("kw", text))
        else:
            out.append((kind, text))
    out.append(("eof", ""))
    return out


# ══════════════════════════════════════════════════════════════════════════════
#  语法树（轻量元组表示，便于断言与序列化）
# ══════════════════════════════════════════════════════════════════════════════
#  ("num", float) | ("var", name) | ("param", name) | ("call", fn, (args...))
#  ("cmp", op, l, r) | ("and", l, r) | ("or", l, r) | ("not", x) | ("neg", x)
#  ("bin", "+|-|*|/", l, r)


class ParsedRule:
    """解析结果：AST + 它用到的变量/参数/函数（供闸门与可外置判定使用）。"""

    __slots__ = ("source", "ast", "identifiers", "params_used", "funcs_used")

    def __init__(self, source: str, ast: Any, identifiers: Set[str],
                 params_used: Set[str], funcs_used: Set[str]):
        self.source = source
        self.ast = ast
        self.identifiers = identifiers
        self.params_used = params_used
        self.funcs_used = funcs_used

    def __repr__(self) -> str:  # pragma: no cover - 便于调试
        return "ParsedRule(%r, ids=%s, params=%s)" % (
            self.source[:40], sorted(self.identifiers), sorted(self.params_used))


class _Parser:
    def __init__(self, tokens: Sequence[Tuple[str, str]]):
        self.toks = list(tokens)
        self.i = 0
        self.identifiers: Set[str] = set()
        self.params_used: Set[str] = set()
        self.funcs_used: Set[str] = set()

    # ── 基础 ──
    def peek(self) -> Tuple[str, str]:
        return self.toks[self.i]

    def next(self) -> Tuple[str, str]:
        t = self.toks[self.i]
        self.i += 1
        return t

    def expect(self, kind: str, text: Optional[str] = None) -> Tuple[str, str]:
        k, t = self.next()
        if k != kind or (text is not None and t != text):
            raise DslError("期望 %s%s，实际 %r" % (kind, ("(%s)" % text) if text else "", t))
        return k, t

    # ── 文法 ──
    def parse(self) -> Any:
        node = self.or_expr()
        if self.peek()[0] != "eof":
            raise DslError("表达式尾部有多余内容：%r" % (self.peek()[1],))
        return node

    def or_expr(self) -> Any:
        node = self.and_expr()
        while self.peek() == ("kw", "or"):
            self.next()
            node = ("or", node, self.and_expr())
        return node

    def and_expr(self) -> Any:
        node = self.not_expr()
        while self.peek() == ("kw", "and"):
            self.next()
            node = ("and", node, self.not_expr())
        return node

    def not_expr(self) -> Any:
        if self.peek() == ("kw", "not"):
            self.next()
            return ("not", self.not_expr())
        return self.cmp_expr()

    def cmp_expr(self) -> Any:
        left = self.arith()
        k, t = self.peek()
        if k == "op" and t in _CMP_OPS:
            self.next()
            op = "==" if t == "=" else t       # ★ 候选库 `=` 即 `==`
            return ("cmp", op, left, self.arith())
        # ★ 自然语言否定语法糖：`X not met` ≡ `not X`（仅限 `NEG_ADJ` 白名单内，
        #   未列入的形容词一律走正常语法 ⇒ 报错，不猜语义）
        if k == "kw" and t == "not":
            nxt = self.toks[self.i + 1]
            if nxt[0] == "ident" and nxt[1] in NEG_ADJ:
                self.next()                     # 吃 'not'
                self.next()                     # 吃 形容词
                return ("not", left)
        return left

    def arith(self) -> Any:
        node = self.term()
        while self.peek()[0] == "op" and self.peek()[1] in ("+", "-"):
            op = self.next()[1]
            node = ("bin", op, node, self.term())
        return node

    def term(self) -> Any:
        node = self.unary()
        while self.peek()[0] == "op" and self.peek()[1] in ("*", "/"):
            op = self.next()[1]
            node = ("bin", op, node, self.unary())
        return node

    def unary(self) -> Any:
        if self.peek() == ("op", "-"):
            self.next()
            return ("neg", self.unary())
        if self.peek() == ("op", "+"):
            self.next()
            return self.unary()
        return self.atom()

    def atom(self) -> Any:
        k, t = self.next()
        if k == "num":
            return ("num", float(t))
        if k == "op" and t == "(":
            node = self.or_expr()
            self.expect("op", ")")
            return node
        if k == "ident":
            # 函数调用？
            if self.peek() == ("op", "("):
                self.next()
                args: List[Any] = []
                if self.peek() != ("op", ")"):
                    args.append(self.or_expr())
                    while self.peek() == ("op", ","):
                        self.next()
                        args.append(self.or_expr())
                self.expect("op", ")")
                if t not in ALLOWED_FUNCS:
                    raise DslError("未登记的函数 %s()（白名单：%s）"
                                   % (t, ", ".join(ALLOWED_FUNCS)))
                self.funcs_used.add(t)
                return ("call", t, tuple(args))
            # params.X ？
            if t == "params" and self.peek() == ("op", "."):
                # '.' 不在词法表中 ⇒ 需显式支持：见 _normalize_dotted
                raise DslError("内部错误：点号应在预处理阶段归一")
            # 布尔字面量（`true`/`false` 实测 45+18 处；当变量处理会被误判"字段未取到"）
            if t in _BOOL_LITERALS and self.peek()[0] != "op":
                return ("bool", _BOOL_LITERALS[t])
            self.identifiers.add(t)
            return ("var", t)
        raise DslError("无法解析的记号：%r" % (t,))


#: `params.xxx` 在词法中不产生 '.' ⇒ 预处理阶段把它整体替换成**占位标识符**，
#: 解析后据前缀还原。这样避免为 '.' 单独加词法规则，也保证 `a.b` 与 `params.b` 不混淆。
_DOTTED_RE = re.compile(r"\bparams\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)")


def _normalize_dotted(src: str) -> Tuple[str, Dict[str, str]]:
    mapping: Dict[str, str] = {}

    def _sub(m: "re.Match") -> str:
        name = m.group(1)
        placeholder = "__PARAM_%s__" % name
        mapping[placeholder] = name
        return placeholder

    return _DOTTED_RE.sub(_sub, src), mapping


def _rewrite_params(node: Any, dotted: Dict[str, str]) -> Any:
    """把 `('var', '__PARAM_x__')` 占位节点改写成 `('param', 'x')`。

    ★ 为什么必须做：`params.X` 经 `_normalize_dotted` 变成占位标识符，
      若不在 AST 上改写，求值时会**被当成普通变量** ⇒ 合法表达式被误判为"字段未取到值"。
      （实测踩到：`output_tax - input_tax > params.gap` 返回 UNKNOWN。）
    """
    if not isinstance(node, tuple):
        return node
    if node[0] == "var" and node[1] in dotted:
        return ("param", dotted[node[1]])
    if node[0] == "call":
        return ("call", node[1], tuple(_rewrite_params(a, dotted) for a in node[2]))
    if node[0] in ("neg", "not"):
        return (node[0], _rewrite_params(node[1], dotted))
    if node[0] in ("and", "or"):                    # 3 元组：(op, l, r)
        return (node[0], _rewrite_params(node[1], dotted),
                _rewrite_params(node[2], dotted))
    if node[0] in ("cmp", "bin"):                   # 4 元组：(op, o, l, r)
        return (node[0], node[1], _rewrite_params(node[2], dotted),
                _rewrite_params(node[3], dotted))
    return node


def compile_expr(logic: str) -> ParsedRule:
    """解析一条 DSL 表达式。超出表达力 ⇒ `UnsupportedSyntax`；语法错 ⇒ `DslError`。"""
    src = str(logic or "").strip()
    if not src:
        raise DslError("表达式为空")
    for pat, why in _UNSUPPORTED_PAT:
        if re.search(pat, src, re.IGNORECASE):
            raise UnsupportedSyntax("超出 DSL 表达力：%s ⇒ 属要件化类，应留在 Python" % why)
    normalized, dotted = _normalize_dotted(src)
    p = _Parser(_tokenize(normalized))
    ast = _rewrite_params(p.parse(), dotted)
    # 还原参数名
    ids = {dotted.get(x, x) for x in p.identifiers if not x.startswith("__PARAM_")}
    params = {dotted[x] for x in p.identifiers if x in dotted}
    return ParsedRule(src, ast, ids, params, set(p.funcs_used))


# ══════════════════════════════════════════════════════════════════════════════
#  求值（三值逻辑）
# ══════════════════════════════════════════════════════════════════════════════


class _Unk:
    """UNKNOWN 的内部表示（携带原因，供"未确定须说明原因"自证）。"""

    __slots__ = ("reason",)

    def __init__(self, reason: str):
        self.reason = reason

    def __repr__(self) -> str:  # pragma: no cover
        return "UNKNOWN(%s)" % self.reason


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def evaluate(rule: ParsedRule, variables: Dict[str, Any],
             params: Optional[Dict[str, Any]] = None,
             unknown_sink: Optional[List[str]] = None) -> Optional[bool]:
    """求值。返回 **True / False / None**（None = UNKNOWN，原因写入 `unknown_sink`）。

    UNKNOWN 的三种来源（**任何一种都不得被当成 False**）：
      · 变量缺失（调用方未提供该字段的取数结果）
      · 参数未登记或为 `null`（如 `region_params` 的地区参数待属地确认）
      · 除零 / 非数值参与算术
    """
    reasons: List[str] = []
    val = _eval(rule.ast, variables or {}, params or {}, reasons)
    if unknown_sink is not None:
        unknown_sink.extend(reasons)
    if isinstance(val, _Unk):
        return None
    if isinstance(val, bool):
        return val
    # 顶层不是布尔：按"非零为真"处理会把 UNKNOWN 混进来 ⇒ 明确要求布尔语义
    if _is_num(val):
        return bool(val)
    reasons.append("表达式结果不是布尔值：%r" % (val,))
    return None


def _eval(node: Any, v: Dict[str, Any], p: Dict[str, Any],
          reasons: List[str]) -> Any:
    kind = node[0]

    if kind == "num":
        return node[1]

    if kind == "bool":
        return node[1]

    if kind == "param":
        name = node[1]
        if name not in p:
            reasons.append("参数未登记：%s" % name)
            return _Unk("missing-param:%s" % name)
        val = p[name]
        if val is None:
            # ★ 参数登记为 null（如 region_params 的待核项）⇒ UNKNOWN，**绝不当 0**
            reasons.append("参数未提供（待核）：%s" % name)
            return _Unk("null-param:%s" % name)
        return val

    if kind == "var":
        name = node[1]
        if name not in v:
            reasons.append("字段未取到值：%s" % name)
            return _Unk("missing:%s" % name)
        val = v[name]
        if val is None:
            reasons.append("字段值为空：%s" % name)
            return _Unk("null:%s" % name)
        return val

    if kind == "call":
        fn = node[1]
        args = [_eval(a, v, p, reasons) for a in node[2]]
        if any(isinstance(a, _Unk) for a in args):
            return _Unk("arg-unknown")
        if not all(_is_num(a) for a in args):
            reasons.append("%s() 的参数不是数值：%r" % (fn, args))
            return _Unk("bad-arg")
        if fn == "abs":
            return abs(args[0])
        if fn == "min":
            return min(args)
        if fn == "max":
            return max(args)
        reasons.append("未登记的函数：%s" % fn)
        return _Unk("unknown-func")

    if kind == "neg":
        a = _eval(node[1], v, p, reasons)
        return a if isinstance(a, _Unk) else (-a if _is_num(a) else _Unk("neg"))

    if kind == "bin":
        op = node[1]
        a = _eval(node[2], v, p, reasons)
        b = _eval(node[3], v, p, reasons)
        if isinstance(a, _Unk) or isinstance(b, _Unk):
            return _Unk("operand-unknown")
        if not (_is_num(a) and _is_num(b)):
            reasons.append("算术运算的操作数不是数值：%r %s %r" % (a, op, b))
            return _Unk("bad-operand")
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            if b == 0:
                # ★ 除零 ⇒ UNKNOWN（不是 0、不是崩溃）—— 与项目「比例判定分母须为正」一致
                reasons.append("除数为零：%r / %r" % (a, b))
                return _Unk("div-zero")
            return a / b
        reasons.append("未登记的算术运算符：%s" % op)
        return _Unk("unknown-op")

    if kind == "cmp":
        op = node[1]
        a = _eval(node[2], v, p, reasons)
        b = _eval(node[3], v, p, reasons)
        if isinstance(a, _Unk) or isinstance(b, _Unk):
            return _Unk("cmp-unknown")
        if op == "==":
            return a == b
        if op == "!=":
            return a != b
        if not (_is_num(a) and _is_num(b)):
            reasons.append("大小比较的操作数不是数值：%r %s %r" % (a, op, b))
            return _Unk("bad-cmp")
        return {">": a > b, ">=": a >= b, "<": a < b, "<=": a <= b}[op]

    if kind == "not":
        a = _eval(node[1], v, p, reasons)
        if isinstance(a, _Unk):
            return a                       # Kleene：not UNKNOWN = UNKNOWN
        return not a

    if kind in ("and", "or"):
        a = _eval(node[1], v, p, reasons)
        # Kleene 短路：and 遇 False 即 False；or 遇 True 即 True（无需看另一侧）
        if kind == "and" and a is False:
            return False
        if kind == "or" and a is True:
            return True
        b = _eval(node[2], v, p, reasons)
        if kind == "and":
            if b is False:
                return False
            if isinstance(a, _Unk) or isinstance(b, _Unk):
                return _Unk("and-unknown")
            return bool(a and b)
        if b is True:
            return True
        if isinstance(a, _Unk) or isinstance(b, _Unk):
            return _Unk("or-unknown")
        return bool(a or b)

    reasons.append("未登记的 AST 节点：%r" % (kind,))
    return _Unk("unknown-node")


# ══════════════════════════════════════════════════════════════════════════════
#  可外置判定（T-6 的**验收指标**：改规则不改代码的占比）
# ══════════════════════════════════════════════════════════════════════════════


def externalizable(logic: str, known_vars: Iterable[str],
                   known_params: Iterable[str]) -> Tuple[bool, str]:
    """该规则能否**只改数据、不改代码**地生效（T-6 验收口径）。

    返回 `(可外置, 原因)`。判据三段：
      ① 表达式在 DSL 表达力内（可解析）；
      ② 用到的**全部变量**都在 `known_vars`（= `var_map` 已登记取数口径）；
      ③ 用到的**全部参数**都在 `known_params`（= 该规则 `params` 已登记）。
    ⇒ 三者齐备时，改阈值/改字段口径**只需改数据表**，无需改代码。
    """
    try:
        r = compile_expr(logic)
    except UnsupportedSyntax as exc:
        return False, "超表达力：%s" % exc
    except DslError as exc:
        return False, "解析失败：%s" % exc
    miss_v = sorted(r.identifiers - set(known_vars))
    if miss_v:
        return False, "字段无取数口径：%s" % "、".join(miss_v)
    miss_p = sorted(r.params_used - set(known_params))
    if miss_p:
        return False, "参数未登记：%s" % "、".join(miss_p)
    return True, "可外置（阈值/字段改数据即可）"
