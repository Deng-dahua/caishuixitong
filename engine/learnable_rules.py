# -*- coding: utf-8 -*-
"""**可学习内容分级**的唯一权威（2026-10-07，用户第 3 批 任务7）。

## 为什么必须分级（用户原话）
> 「区分四类可学习内容：**可自动学习**（格式错误、字段映射、重复段落、表格校验、占位符）；
>   **需人工确认**（风险指标、风险族、税额测算、风险等级、法律适用、模板、重要性水平）；
>   **只能积累**（行业基准、企业画像、历史案例、分析视角偏好）；
>   **禁止自动学习**（法律条文、追征期、滞纳金、处罚标准、主观故意认定、企业申辩结论）。」

把"系统自己改自己"的范围**用数据划定**——否则一次误学就会把结论口径改坏，
而且**没有任何痕迹**（本项目反复出现的"静默改变结论"）。

## 四档语义
| 档 | 谁来决定 | 能否直接进正式报告 |
|---|---|---|
| `auto` | 系统可自动采纳（有回归闸门兜底） | ✅ 可以 |
| `manual` | **必须人工确认**后才可生效 | 未确认 ❌ |
| `accumulate` | 只入库作参考，**不改变判定** | ✅ 作为参考可呈现，标注来源 |
| `forbidden` | **禁止**自动学习/自动应用 | ❌ 一律不得由系统写入 |

## 用法
```
from engine.learnable_rules import tier_of, may_write_rule, describe
tier_of("表格校验")        # -> "auto"
may_write_rule("法律条文")  # -> (False, "禁止自动学习：法律条文")
```
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

#: 档 → 该档包含的**内容类别**（新增类别只加一行；不新增档）
TIERS: Dict[str, Tuple[str, ...]] = {
    # ✅ 可自动学习：**只影响呈现，不影响结论**——这类改动错了也只会让文字更难读，
    #    且有"格式/表格/占位符"三道闸门与回归测试兜底。
    "auto": (
        "格式错误", "字段映射", "重复段落", "表格校验", "占位符",
        "错别字", "标点", "措辞清洗",
    ),
    # ⚠ 需人工确认：**会改变结论或口径**——系统可以"建议"，但必须人确认后生效。
    "manual": (
        "风险指标", "风险族", "税额测算", "风险等级", "法律适用",
        "模板", "重要性水平", "阈值", "判据",
    ),
    # 📚 只能积累：作**参考**呈现，**不得**改变任何判定（如行业基准区间）。
    "accumulate": (
        "行业基准", "企业画像", "历史案例", "分析视角偏好",
    ),
    # ⛔ 禁止自动学习：涉及**法律责任与主观认定**，只能引用官方现行文本、由人适用。
    "forbidden": (
        "法律条文", "征缴期限", "征期", "追征期", "滞纳金", "处罚标准",
        "主观故意认定", "企业申辩结论",
    ),
}

#: 档 → 一句话解释（报告/日志里呈现口径用；**唯一解释处**）
TIER_NOTE: Dict[str, str] = {
    "auto": "可自动学习：只影响呈现、不影响结论，且有闸门与回归测试兜底",
    "manual": "需人工确认：会改变结论或口径，系统只可建议，须人工确认后生效",
    "accumulate": "只能积累：仅作参考呈现，不得改变任何判定",
    "forbidden": "禁止自动学习：涉及法律责任与主观认定，只能引用官方现行文本并由人适用",
}

#: 档 → 是否允许系统**直接**写入规则库并用于正式报告
_TIER_WRITABLE = {"auto": True, "manual": False, "accumulate": False, "forbidden": False}


def _index() -> Dict[str, str]:
    """类别 → 档（构建一次；重复登记即报错，防止两处口径不一）。"""
    global _IDX
    if _IDX is None:
        _idx: Dict[str, str] = {}
        for tier, kinds in TIERS.items():
            for k in kinds:
                if k in _idx and _idx[k] != tier:
                    raise ValueError("可学习内容「%s」重复登记在 %s 与 %s 两档"
                                     % (k, _idx[k], tier))
                _idx[k] = tier
        _IDX = _idx
    return _IDX


_IDX: Optional[Dict[str, str]] = None


def tier_of(kind: str) -> str:
    """内容类别（或档名）→ 档；**未登记一律按最严档 `manual` 处理**（不臆断为可自动学习）。

    ★ 入参有**两个合法空间**（2026-10-07 修：此前只认"内容类别"，把档名当类别查
      ⇒ `tier_of("forbidden")` 落回 `manual`，于是"禁止档"的提示词变成"需人工确认"，
      调用方据此判"拒绝入库"的理由整个错位）：
        ① **档名**（`auto`/`manual`/`accumulate`/`forbidden`）：精确命中 `TIERS` 键 ⇒ 直接返回；
        ② **内容类别**（如「法律条文」「表格校验」）：查 `TIERS` 类别表；含包含式匹配。
      ⚠ 档名优先：否则档名会被当成"未登记类别"而落回 `manual`（静默降/升档）。

    ⚠ 取不到就按 `manual`：未知类别的默认必须是"需人工确认"，
      绝不能默认 `auto`（那等于给系统一张空白授权）。
    """
    k = str(kind or "").strip()
    if not k:
        return "manual"
    if k in TIERS:                     # ① 传进来的本身就是档名
        return k
    idx = _index()
    if k in idx:                       # ② 内容类别精确命中
        return idx[k]
    for _k, _t in idx.items():         # ③ 允许"税率测算"匹配到"税额测算"这类包含式
        if _k in k or k in _k:
            return _t
    return "manual"


def may_write_rule(kind: str) -> Tuple[bool, str]:
    """该类别的新规则能否**由系统直接写入**并用于正式报告？返回 (可否, 原因)。"""
    t = tier_of(kind)
    ok = _TIER_WRITABLE.get(t, False)
    return ok, ("%s（%s）" % (TIER_NOTE.get(t, "未登记档"), kind if kind else "未指明类别"))


def describe(kind: str) -> str:
    return "%s → %s" % (kind, TIER_NOTE.get(tier_of(kind), "未登记档"))


def guard_rule_write(kind: str) -> None:
    """规则入库前的**守卫**：不允许写入时抛错（调用方不得用 try 吞掉）。"""
    ok, why = may_write_rule(kind)
    if not ok:
        raise PermissionError("不允许系统自动写入该规则：%s。"
                              "需人工确认或改由人工维护。" % why)


def all_tiers() -> List[Tuple[str, str]]:
    """返回 [(档, 解释)]（报告/日志口径声明用）。"""
    return [(t, TIER_NOTE[t]) for t in ("auto", "manual", "accumulate", "forbidden")]
