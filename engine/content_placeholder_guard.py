# -*- coding: utf-8 -*-
"""占位符与空内容检测（Skill 4 唯一权威）。

## 为什么要它
用户复核（2026-10-07，文末「说明2」）：
  报告文末写着「说明2。 要把这一项查清楚，需要：」——**后面没有任何内容**。
  同段落里其他"要把这一项查清楚，需要：XXX"都有正文，只有它是**孤立的引导句**。
根因：引导句（以「：」收尾、承诺后文）被**单独**放进条目数组（如 `report_statement`），
  而其正文在别处被丢弃/未生成 ⇒ 渲染出"有标题没有内容"的空条目。

## 三类问题
1. **空内容**：条目为空或仅空白。
2. **孤立引导句**：条目本身是"……："/"……如下："/"……需要："这类**承诺后文**的句子，且**无正文**。
3. **占位符**：条目含未替换的占位/待填标记（`见上文`/`参见…部分`/`待补充`/`TODO`/`XXX`/`（空）` 等）。

## 口径
- 判据是**文本形态 + 词表**，数据驱动；新增同类只加一行。
- **命中即问题**：报告生成后由 `scan()` 统一体检；被 `blocked=True` 的问题**必须阻断生成**
  （由调用方 `assert_clean()` 或闸门执行）。
- **不得**把正常句子误判为占位符：`待补充资料`（作为要求企业补材料的正常表述）不算占位符 ——
  只在**条目整体**是占位符时才判（整句匹配/极短句）。
"""
from __future__ import annotations
import re
from typing import Any, Dict, Iterable, List, Tuple

VERSION = "1.0.0"

#: "承诺后文"的引导句收尾（**数据驱动**）
LEAD_TAILS: tuple = ("需要：", "如下：", "包括：", "分别是：", "详见：", "如下。", "：", ":")

#: 明确的占位符（**整条**命中才算，避免误伤正常句子）
PLACEHOLDER_PATTERNS: tuple = (
    r"^参见.*部分$", r"^详见.*$", r"^见上文$", r"^见下文$", r"^同上$", r"^略$",
    r"^待补充$", r"^待填$", r"^待定$", r"^TODO.*$", r"^XXX.*$", r"^（空）$", r"^\(空\)$",
    r"^[—\-–]+$", r"^N/?A$", r"^\{\{.*\}\}$", r"^<.*>$",
)

#: "孤立引导句"的最小长度保护：短于此长度的整条"…："大概率是标题，不算孤立引导句
_MIN_LEAD_LEN = 6
_WS_RE = re.compile(r"[\s\u3000]+")


def _norm(s: Any) -> str:
    return _WS_RE.sub("", str(s or "")).strip()


def is_empty(item: Any) -> bool:
    return not _norm(item)


def is_orphan_lead(item: Any) -> bool:
    """条目是否为**孤立引导句**（承诺后文但无正文）。"""
    raw = str(item or "").strip()
    if len(raw) < _MIN_LEAD_LEN:
        return False
    s = _norm(raw)
    if not any(s.endswith(t) for t in LEAD_TAILS):
        return False
    # 去掉编号前缀（如「说明2。」「五、」）与引导词后，若还有实质正文则不算孤立
    body = s
    for t in LEAD_TAILS:
        if body.endswith(t):
            body = body[: -len(t)]
            break
    body = re.sub(r"^[（(]?[0-9一二三四五六七八九十]+[）)\.、．]?", "", body)
    # 引导句本体 = 只含"要把这一项查清楚/需要/如下"这类**无信息量**的引导词
    body = re.sub(r"(要把这一项查清楚|要把本项查清楚|本项需要|需要|企业需提供|整改需要|"
                  r"还请|请提供|如下|包括|分别是|详见|即|由|就)", "", body)
    return len(body) <= 4


def is_placeholder(item: Any) -> bool:
    s = _norm(item)
    if not s:
        return False
    return any(re.match(p, s, re.I) for p in PLACEHOLDER_PATTERNS)


#: 段落除 `text` 外**仍会被渲染层输出**的字段（"可见载荷"）。
PAYLOAD_KEYS: tuple = ("bullets", "detail_table", "detail_tables", "tail")


def has_payload(holder: Any) -> bool:
    """该块是否除正文外还带**可见载荷**（bullets / 明细表 / 尾注）。

    ★★ 2026-10-09（P0-7 连带根因）：**薄转发唯一权威** `engine.report_dedup.has_visible_payload`
      —— "什么算有内容"必须只有一处判据（段级上提、空内容体检、D2 门禁三处共用）。
    """
    if not isinstance(holder, dict):
        return False
    try:
        from engine.report_dedup import has_visible_payload as _hp
        return bool(_hp(holder))
    except Exception:  # noqa: BLE001 —— 权威取不到时按本模块口径兜底（保守：按字段判）
        for k in PAYLOAD_KEYS:
            v = holder.get(k)
            if isinstance(v, (list, tuple, dict)) and len(v) > 0:
                return True
            if isinstance(v, str) and v.strip():
                return True
        return False


def is_orphan_block(text: Any, holder: Any = None) -> bool:
    """**块级**孤立引导句（唯一权威）：引导句收尾 **且** 该块没有承载内容。

    ★★ 2026-10-09 真实假红（D2 由 2 处涨到 13 处）：报告里「五、需企业提供的资料与说明」
      段的**正文**是结构性引导句「要把这一项查清楚，需要：」，而补件清单在**同段的
      `bullets` / `detail_table`** 里（前端 `_renderNarrativeBody` 确实渲染它们）。
      此时"其后无内容"是**假的** —— 内容就在同一块的载荷里。
    ⇒ 判据必须是"**整块**是否有内容"（正文 ∪ 载荷），而不是只看正文。
    """
    if not is_orphan_lead(text):
        return False
    return not has_payload(holder)


def scan_item(item: Any, path: str = "") -> List[Dict[str, Any]]:
    """检测单条内容（返回问题清单）。"""
    out: List[Dict[str, Any]] = []
    if isinstance(item, dict):
        return out
    if is_empty(item):
        out.append({"kind": "empty_item", "level": "ERROR", "path": path,
                    "detail": "条目为空（渲染出来是有标题没有内容的空块）。", "text": ""})
        return out
    if is_orphan_lead(item):
        out.append({"kind": "orphan_lead", "level": "ERROR", "path": path,
                    "detail": "孤立引导句：本条以「：」承诺后文，但**没有正文** "
                              "（其正文在生成时被丢弃/未产出）。", "text": str(item)[:120]})
    elif is_placeholder(item):
        out.append({"kind": "placeholder", "level": "ERROR", "path": path,
                    "detail": "未替换的占位符：必须替换为实际内容。", "text": str(item)[:120]})
    return out


def scan(obj: Any, *, skip_keys: Iterable[str] = ()) -> List[Dict[str, Any]]:
    """递归扫描报告结构中的**列表条目/字符串**（迭代去环，禁递归爆栈）。

    只扫"会原样渲染成条目"的位置：列表元素与 dict 的字符串值；
    跳过 `skip_keys`（如 `pipeline_log` 这类运行日志，不是报告正文）。
    """
    skip = set(skip_keys or ())
    out: List[Dict[str, Any]] = []
    stack: List[Tuple[str, Any]] = [("", obj)]
    seen: set = set()
    while stack:
        path, cur = stack.pop()
        if isinstance(cur, (dict, list)):
            if id(cur) in seen:
                continue
            seen.add(id(cur))
            if isinstance(cur, dict):
                for k, v in cur.items():
                    if str(k) in skip:
                        continue
                    stack.append(("%s.%s" % (path, k), v))
            else:
                for i, v in enumerate(cur):
                    stack.append(("%s[%d]" % (path, i), v))
            continue
        out.extend(scan_item(cur, path))
    return out


def assert_clean(obj: Any, *, skip_keys: Iterable[str] = ()) -> None:
    """命中即抛（供生成流程"阻断生成"用）。"""
    issues = scan(obj, skip_keys=skip_keys)
    if issues:
        head = "；".join("%s: %s" % (i["kind"], i["detail"]) for i in issues[:3])
        raise ValueError("报告存在空内容/占位符（共 %d 处）：%s" % (len(issues), head))


__all__ = ["VERSION", "LEAD_TAILS", "PLACEHOLDER_PATTERNS", "PAYLOAD_KEYS", "is_empty",
           "is_orphan_lead", "has_payload", "is_orphan_block", "is_placeholder",
           "scan_item", "scan", "assert_clean"]
