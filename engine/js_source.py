# -*- coding: utf-8 -*-
"""JS 源码净化（**唯一权威**）。

★★ 先分清**两个不同概念**（历史上已被混淆过一次）：

  | 概念 | 函数 | 字面量（字符串/模板串） | 用途 |
  |---|---|---|---|
  | **只剥注释**（保留字面量） | 本模块 `strip_comments()` | **保留** | 要读**字面量里的内容**（如提取 `/api/...` 路径做前后端对齐审计） |
  | **只留代码**（字面量也抹掉） | `tools/audit_consistency.py::_js_code_only()` | **抹成空格** | 找**裸名调用**（字面量里出现的 CSS `linear-gradient(`、中文说明里的函数名都会造成成片误报） |

  两者都需要，但**不可互相替代**：用 `code_only` 去提取 API 路径会一个字都取不到（路径全在字面量里）；
  用 `strip_comments` 去查裸名调用则会被字面量内容淹掉。本模块只负责**前者**。

★ 为什么必须识别**字符串**与**正则字面量**（两次实测教训）
  · 不识别字符串：`"http://x"` 里的 `//` 会被当注释起点 ⇒ 后半行被吃掉；
  · 不识别正则字面量：`static/js/documents.js:22` 的 `.replace(/"/g, "&quot;")` 里的引号
    会让状态机**脱同步**（把后面整段代码当字符串）⇒ 注释再也剥不掉 ⇒ **假判据**。
    （同一坑在 2026-10-07 已让 `_js_code_only` 对 `loadCompanies is not defined` 完全失明。）

★ 保证：**长度与行数守恒**（注释/正则内容以空格替换）⇒ 可用"行号"回指原文件、可用于注入式反向验证。
"""
from __future__ import annotations

#: 这些符号之后的 `/` 视为正则字面量起点（标准启发式；除法 `a / b` 前是标识符/数字，不受影响）
_REGEX_PREV_CHARS = set("(,=:[!&|?{};+-*%~^<>")
#: 这些关键字之后的 `/` 也视为正则起点
_REGEX_PREV_WORDS = ("return", "typeof", "case", "in", "of", "new", "delete",
                     "void", "do", "else", "instanceof", "yield", "await")


def strip_comments(s: str) -> str:
    """剥掉 JS 注释（**保留字符串/模板串/正则字面量**），长度与行数不变。"""
    out: list = []
    i, n, quote = 0, len(s), None
    last_sig, last_word = "", ""
    while i < n:
        ch = s[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(s[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "\"'`":
            quote = ch
            out.append(ch)
            last_sig, last_word = "", ""
            i += 1
            continue
        if ch == "/" and i + 1 < n and s[i + 1] == "/":
            while i < n and s[i] != "\n":
                out.append(" ")
                i += 1
            continue
        if ch == "/" and i + 1 < n and s[i + 1] == "*":
            while i < n and not (s[i] == "*" and i + 1 < n and s[i + 1] == "/"):
                out.append("\n" if s[i] == "\n" else " ")
                i += 1
            for _ in range(2):
                if i < n:
                    out.append(" ")
                    i += 1
            continue
        if ch == "/" and (last_sig in _REGEX_PREV_CHARS or last_word in _REGEX_PREV_WORDS):
            out.append(ch)
            i += 1
            in_class = False
            closed = False
            while i < n:
                c2 = s[i]
                out.append(c2)
                if c2 == "\\" and i + 1 < n:
                    out.append(s[i + 1])
                    i += 2
                    continue
                if c2 == "[":
                    in_class = True
                elif c2 == "]":
                    in_class = False
                elif c2 == "/" and not in_class:
                    i += 1
                    closed = True
                    break
                elif c2 == "\n":            # 换行 ⇒ 不是正则（避免吞掉整文件）
                    i += 1
                    break
                i += 1
            if closed:
                while i < n and s[i] in "gimsuy":
                    out.append(s[i])
                    i += 1
            last_sig, last_word = "/", ""
            continue
        out.append(ch)
        if not ch.isspace():
            last_sig = ch
            if ch.isalnum() or ch in "_$":
                last_word = (last_word + ch) if last_word else ch
            else:
                last_word = ""
        i += 1
    return "".join(out)


__all__ = ["strip_comments"]
