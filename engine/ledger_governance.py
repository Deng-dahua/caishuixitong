# -*- coding: utf-8 -*-
"""台账治理 —— **企业版「全部风险事项台账」的准入过滤与类型级聚合**（唯一权威）。

## 为什么需要本模块（根因）

外部点评对台账（156 项）提了三个问题，根因是**同一个**：台账直接把 `all_findings`
逐条平铺，既不过滤"这条是不是给企业看的风险事项"，也不做类型级归并。

1. **内部工具条目混入**：`审计检查：系统一致性`、`风险检查取证要求补充资料单`
   —— 这是**系统自查/资料请求单**，不是企业的涉税风险事项；其"需补自证资料"还是
   六段自引用循环文本（模板套模板）。企业看到只会困惑。
2. **同质未聚合**：约 82 项形如「XX逐月不匹配（2025-01）…（2025-12）」——
   同一件事按月份拆成 12 行，台账被拉长到无法使用。
3. **无统一发现 ID、与疑点无映射**：读者无法把台账某行与「具体问题」章的某疑点对上，
   两章之间没有可引用的公共编号。

## 做法（数据驱动，新增同类规则只加一行）

- **准入**：`is_enterprise_risk_item()` —— 命中内部工具名表、或"需补自证资料"呈
  **自引用循环**（同一子句重复 ≥3 次）的一律不列入企业台账（它们仍留在内部底稿）。
- **聚合**：`canonical_ledger_key()` 去掉括注里的期间/批次，把同类型合并为一行，
  期间/批次差异落到该行的「明细」；聚合行标 `聚合项数`。
- **统一 ID**：`make_finding_id()` 由规范键的 CRC32 派生（**同一输入必得同一编号**，
  与行序无关），供全文引用。
- **疑点映射**：按 `redline_id` 对齐「具体问题」章，写「关联疑点」=「具体问题第N项」。
"""

from __future__ import annotations

import re
import zlib
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ── ① 准入：内部工具/自查条目名（唯一权威；新增同类只加一行）──────────────────
_INTERNAL_TYPE_PATTERNS: Tuple[str, ...] = (
    "审计检查", "系统一致性", "引擎自检", "自检与自我修正", "质量检查", "检查程序待完善",
    "取证要求", "补充资料单", "资料缺口报告", "分析覆盖", "能力边界",
    "方法论", "工作底稿", "报告章节", "目录", "模板",
)

# 自查/程序类条目的典型措辞（出现在类型名中即判为内部条目）
_INTERNAL_TYPE_HINTS: Tuple[str, ...] = (
    "系统", "引擎", "程序", "口径核对", "章节", "校验",
)

# 自引用循环检测：同一子句在"需补自证资料"里重复出现即视为模板套模板
_SELF_REF_MIN_REPEAT = 3


def _norm(s: Any) -> str:
    return str(s or "").strip()


def is_enterprise_risk_item(finding: Dict[str, Any]) -> Tuple[bool, str]:
    """该发现是否应进入**企业版台账**。返回 `(是否准入, 原因)`。

    准入 = 是「企业涉税风险事项」；不准入 = 系统内部工具条目/资料请求单（仍留内部底稿）。
    """
    if not isinstance(finding, dict):
        return False, "非字典"
    t = _norm(finding.get("type"))
    if not t:
        return False, "无事项名称"
    for p in _INTERNAL_TYPE_PATTERNS:
        if p in t:
            return False, f"内部工具条目（命中「{p}」）"
    # 类型名里同时出现"系统/引擎/程序/章节/校验"与"检查"，视为自查条目
    if ("检查" in t or "核对" in t) and any(h in t for h in _INTERNAL_TYPE_HINTS):
        return False, "系统自查条目（类型名含检查+系统类字样）"
    # 自引用循环：需补自证资料里同一子句重复 ≥3 次（模板套模板，对行动无指引）
    proof = finding.get("self_proof_materials") or []
    blob = "；".join(
        "{0}——{1}".format(_norm(p.get("material")), _norm(p.get("proves")))
        for p in proof if isinstance(p, dict)
    )
    if blob and _is_self_referential(blob):
        return False, "需补自证资料为自引用循环文本（模板套模板，无行动指引）"
    return True, ""


def _is_self_referential(text: str) -> bool:
    """判断"需补自证资料"是否自引用循环：同一 ≥8 字子句重复 ≥3 次。"""
    s = _norm(text)
    if len(s) < 24:
        return False
    # 以「；」切段，看重复段
    segs = [x.strip() for x in re.split(r"[；;]", s) if len(x.strip()) >= 8]
    if segs:
        from collections import Counter
        c = Counter(segs)
        if c.most_common(1)[0][1] >= _SELF_REF_MIN_REPEAT:
            return True
    # 无分号：用最长重复子串近似（同一 8 字窗口出现 ≥3 次）
    for i in range(0, max(1, len(s) - 8)):
        win = s[i:i + 8]
        if win.strip() and s.count(win) >= _SELF_REF_MIN_REPEAT:
            return True
    return False


# ── ② 聚合：规范键（去掉期间/批次括注）──────────────────────────────────────────
# 括注型期间/批次：全角或半角括号内的 年-月 / 年-月~年-月 / 第N批 / 第N月 / 共N项
_BRACKET_TAIL = re.compile(
    r"[（(]\s*(?:"
    r"\d{4}\s*[-/年]\s*\d{1,2}\s*(?:月)?"
    r"(?:\s*[~～至\-—]\s*\d{4}\s*[-/年]\s*\d{1,2}\s*(?:月)?)?"
    r"|第\s*\d+\s*[批轮月期次]"
    r"|共\s*\d+\s*[项笔张个月批次]"
    r"|涉及\s*[^）)]{1,24}"
    r")\s*[）)]\s*$"
)


def canonical_ledger_key(name: Any) -> str:
    """规范键 = 事项名去掉**尾部期间/批次括注**。同类型的月度展开因此归并。"""
    s = _norm(name)
    prev = None
    while s and s != prev:
        prev = s
        s = _BRACKET_TAIL.sub("", s).strip()
    return s


def make_finding_id(canonical_key: str) -> str:
    """统一发现 ID：由规范键 CRC32 派生 —— **同一输入必得同一编号**（与行序无关）。"""
    k = _norm(canonical_key)
    if not k:
        return ""
    return "R-%04d" % (zlib.crc32(k.encode("utf-8")) % 10000)


def _extract_bracket(name: Any) -> str:
    """取出被 canonical 去掉的括注内容（作为明细里的"期间/批次"）。"""
    s = _norm(name)
    m = re.search(r"[（(]([^（()）]{1,40})[）)]\s*$", s)
    return m.group(1).strip() if m else ""


def build_related_problem_index(problems: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    """`redline_id` → 「具体问题第N项」标签（供台账行写「关联疑点」）。"""
    idx: Dict[str, str] = {}
    for p in (problems or []):
        if not isinstance(p, dict):
            continue
        rid = _norm(p.get("redline_id"))
        seq = p.get("seq")
        if rid and seq and rid not in idx:
            idx[rid] = "具体问题第%s项" % seq
    return idx


def govern_ledger_rows(rows: Sequence[Dict[str, Any]],
                       findings: Sequence[Dict[str, Any]],
                       problems: Sequence[Dict[str, Any]] = None) -> Dict[str, Any]:
    """对台账行做**准入过滤 + 类型级聚合 + 统一 ID + 疑点映射**。

    入参 `rows` 与 `findings` 按下标一一对应（由企业报告构建处保证）。
    返回 `{"rows": [...], "excluded": [...], "merged_count": n}`：
      · each row 追加：`发现ID` / `关联疑点` / `聚合项数` / `明细`（成员列表，聚合时才有）
      · `excluded` 记录被剔除的内部条目（供内部清单/日志，不进企业台账）
    """
    idx = build_related_problem_index(problems or [])
    excluded: List[Dict[str, Any]] = []
    kept: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    for i, row in enumerate(rows or []):
        f = findings[i] if i < len(findings or []) else {}
        ok, reason = is_enterprise_risk_item(f if isinstance(f, dict) else {})
        if not ok:
            excluded.append({"风险事项": _norm((f or {}).get("type")), "剔除原因": reason})
            continue
        kept.append((row, f if isinstance(f, dict) else {}))

    # 聚合：按规范键 + 等级 + 终局方向 分组（解除方式/自证资料可能逐月不同 → 取首条为代表，
    # 差异逐条落在「明细」里，不丢信息）
    groups: Dict[Tuple[str, str, str], List[Tuple[Dict[str, Any], Dict[str, Any]]]] = {}
    order: List[Tuple[str, str, str]] = []
    for row, f in kept:
        name = _norm(row.get("风险事项"))
        key = (canonical_ledger_key(name), _norm(row.get("等级")), _norm(row.get("终局方向")))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append((row, f))

    out_rows: List[Dict[str, Any]] = []
    merged = 0
    for key in order:
        members = groups[key]
        ckey, level, terminal = key
        head_row, head_f = members[0]
        rid = _norm(head_f.get("redline_id"))
        if len(members) == 1:
            new_row = dict(head_row)
            new_row["风险事项"] = ckey or _norm(head_row.get("风险事项"))
            new_row["发现ID"] = make_finding_id(ckey or _norm(head_row.get("风险事项")))
            new_row["关联疑点"] = idx.get(rid, "")
            new_row["聚合项数"] = ""
            out_rows.append(new_row)
            continue
        merged += 1
        # 聚合行的"解除方式/需补自证资料"取各成员**去重后**的并集，避免只留首条而丢出口
        def _union(field: str) -> str:
            seen: List[str] = []
            for r, _ in members:
                v = _norm(r.get(field))
                if v and v not in seen:
                    seen.append(v)
            return "；".join(seen)
        detail = []
        for r, _f in members:
            detail.append({
                "期间/批次": _extract_bracket(r.get("风险事项")) or _norm(r.get("风险事项")),
                "等级": _norm(r.get("等级")),
                "终局方向": _norm(r.get("终局方向")),
                "解除方式": _norm(r.get("解除方式")),
                "需补自证资料": _norm(r.get("需补自证资料")),
            })
        new_row = {
            "风险事项": ckey or _norm(head_row.get("风险事项")),
            "等级": level,
            "证据地位": _norm(head_row.get("证据地位")),
            "终局方向": terminal,
            "解除方式": _union("解除方式"),
            "需补自证资料": _union("需补自证资料"),
            "发现ID": make_finding_id(ckey),
            "关联疑点": idx.get(rid, ""),
            "聚合项数": "含 %d 项（明细见下表）" % len(members),
            "明细": detail,
        }
        out_rows.append(new_row)
    return {"rows": out_rows, "excluded": excluded, "merged_count": merged}
