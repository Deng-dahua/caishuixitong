# -*- coding: utf-8 -*-
"""第1批「11 处文档修正」的**可复现失败/通过样例**（先还原成修正前 → 再跑同一门禁）。

用户要求（第1批完整交付物生成指令）：
  · 失败样例必须**来自实际运行**，不得推断；
  · 每处必须给出「修正前逐字 / 修正后逐字 / 依据命令 / 实测输出」；
  · 门禁必须**反向验证**（构造破坏 ⇒ 必须变红），否则是假门禁。

本脚本做的事（**逐处**）：
  ① 备份文件 → ② 把该处**还原成修正前状态**（变异）→ ③ 跑**同一个**门禁 / grep → ④ 记录输出
  → ⑤ **还原文件**（失败即中止并还原，绝不留下脏文件）→ ⑥ 再跑一次确认已复原（全绿）。

```bash
./.venv/Scripts/python.exe scripts/_demo_batch01_fix11.py          # 全部 11 处
./.venv/Scripts/python.exe scripts/_demo_batch01_fix11.py 5        # 只看第 5 处
```
退出码：0 = 11 处**全部**满足"旧态报红 / 新态全绿"；1 = 有任一处未被门禁抓住（**说明判据有缺口**）。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DOCDIR = ROOT / "docs" / "第01批_触发条件与认定要件分离"
F01 = "01_Skill设计文档.md"
F02 = "02_系统配置变更清单.md"
F05 = "05_回归测试报告.md"
R1_DIGITS = "R1_数字统一修订记录.md"
F08 = "08_未完成事项清单.md"
FMIN = "最小检查集.md"


# --------------------------------------------------------------------------
# 门禁执行（**同一批判据**，逐处调用；不做任何"特例放宽"）
# --------------------------------------------------------------------------
def _gates(names):
    from engine import (doc_number_authority as D1, rule_reference_sync as D2,
                        doc_residue_scan as D3, todo_status_sync as D4, doc_ref_graph as D5)
    from engine import doc_consistency_core as core
    core.reload_config()
    m = {"D1": D1, "D2": D2, "D3": D3, "D4": D4, "D5": D5}
    out = {}
    for n in names:
        iss = m[n].audit()
        out[n] = [i for i in iss if i["level"] == "ERROR"]
    core.reload_config()
    return out


def _errs(names):
    """返回 {门禁: [错误描述...]}（只保留 ERROR）。"""
    g = _gates(names)
    return {k: ["%s ｜ %s" % (e.get("where"), str(e.get("detail"))[:110]) for e in v] for k, v in g.items()}


# --------------------------------------------------------------------------
# 11 处修正（每处：修正前状态 = 把旧写法写回去；判据 = 同一门禁必须报 ERROR）
# --------------------------------------------------------------------------
ITEMS = [
    dict(
        no=1, file=F01, desc="§6 合计行的测试用例数：`25 passed` → `28 passed`",
        muts=[("**28 passed**（分项 10 + 7 + 3 + 3 + 2 + 3 = 28）", "**25 passed**")],
        gates=["D1"], why="单值正则抓「N passed」；旧值 25 ≠ 权威 28 ⇒ ERROR",
    ),
    dict(
        no=2, file=F01, desc="§6 分项加总与合计自相矛盾（旧分项加总 31，合计 28）",
        muts=[("分项 10 + 7 + 3 + 3 + 2 + 3 = 28", "分项 10 + 7 + 3 + 3 + 2 + 6 = 31")],
        gates=["D1"], why="新增「分项加总 == 合计」判据（`sum_checks`）⇒ ERROR",
    ),
    dict(
        no=3, file=F02, desc="§3 规则清单缺 `TDS-⑨`（新增规则未同步到引用文件）",
        muts=[("（**TDS-①~⑨ 全部在本函数内**", "（**TDS-①~⑧ 全部在本函数内**"),
              ("**TDS-⑨**（本批补做新增）", "**TDS-⑧bis**（本批补做新增）")],
        gates=["D2"], why="覆盖完整性判据：`rule_catalog_files` 的文件必须列全 9 条 ⇒ ERROR",
    ),
    dict(
        no=4, file=F02, desc="文末自证段「门禁 9 条规则」曾写 8 条",
        muts=[("门禁 **9** 条规则", "门禁 **8** 条规则")],
        gates=["D1"], why="rule_count 权威值 9（`rule_catalog` 条数）⇒ ERROR",
    ),
    dict(
        no=5, file=F02, desc="§3 门禁调用行号 11123（失真）→ 11200（grep 实测）",
        muts=[("第 **11200** 行 `run_checks()` 总链", "第 **11123** 行 `run_checks()` 总链")],
        gates=["D1"], why="新增 `grep_line` 权威：行号必须 == `grep -n` 实测 ⇒ ERROR",
    ),
    dict(
        no=6, file=F08, desc="补做2 的「位置」列漏了 `01:92`（§6 合计行）",
        muts=[("、**`01:92`（§6 合计行）**", "")],
        gates=[], marker="01:92",
        why="文本完整性：修正后 `01:92` 必须出现在 08 补做2 表里（旧态缺失）",
    ),
    dict(
        no=7, file=F08, desc="补做2 的 grep 结论未展开同义写法（旧结论不成立）",
        muts=[("按 Skill D3 的**同义写法词典**展开，原 grep 只搜「25 例」会漏「25 passed」",
               "`grep -rn \"25 例\"` 无残留")],
        gates=[], marker="同义写法词典",
        why="修正后必须写明「按词典展开」；旧态只写窄式 grep（结论不成立）",
    ),
    dict(
        no=8, file=F08, desc="U 表的 U1 状态未同步（补做记录声明「已修复」，表里仍是旧状态）",
        muts=[("| **U1** | **已修复** |", "| **U1** | **未开始** |")],
        gates=["D4"], why="状态同步判据（清单状态 ≠ 补做记录声明）⇒ ERROR",
    ),
    dict(
        no=9, file=R1_DIGITS,
        desc="§2 的旧 grep 结论（只搜「25 例」）—— 结论不成立，改为展开式（`expand_grep`）",
        muts=[("from engine.doc_residue_scan import expand_grep; print(expand_grep())",
               "print('grep -rn \\\"25 例\\\" docs/第01批_触发条件与认定要件分离/*.md')")],
        gates=[], marker="expand_grep",
        why="修正后必须给出**展开式**命令；旧态是窄式 grep（漏「25 passed」，见第 1 处）",
    ),
    dict(
        no=10, file=FMIN, desc="最小检查集「本 Skill 专项 28 tests」与 01 不一致（曾写 25）",
        muts=[("→ **28 tests** |", "→ **25 tests** |")],
        gates=["D1"], why="D1 的 `最小检查集.md` claims + D5 引用图（下游必须与上游同步）⇒ ERROR",
    ),
    dict(
        no=11, file=FMIN, desc="最小检查集「门禁 9 条规则」与 02 不一致（曾写 8）",
        muts=[("门禁 **9** 条规则（`TDS-①`…`TDS-⑨`）", "门禁 **8** 条规则（`TDS-①`…`TDS-⑨`）")],
        gates=["D1"], why="D1 的 `最小检查集.md` 规则条数 claims（权威 = `rule_catalog` 9）⇒ ERROR",
    ),
]


def _run_item(it):
    path = DOCDIR / it["file"]
    backup = path.read_text(encoding="utf-8")
    result = {"no": it["no"], "file": it["file"], "desc": it["desc"], "why": it["why"], "ok": False}
    try:
        for cur, old in it["muts"]:
            if cur not in backup:
                result["error"] = "变异锚点（修正后文本）未找到 ⇒ **用例无效**：%s" % cur[:60]
                return result
        # ② 还原成"修正前"
        text = backup
        for cur, old in it["muts"]:
            text = text.replace(cur, old, 1)
        path.write_text(text, encoding="utf-8")
        assert path.read_text(encoding="utf-8") != backup, "变异未生效"
        # ③ 跑同一门禁
        if it["gates"]:
            errs = _errs(it["gates"])
            result["before"] = errs
            result["caught"] = all(len(v) > 0 for v in errs.values())
        else:
            mutated = path.read_text(encoding="utf-8")
            result["before"] = {"grep": ["标记 `%s` 在旧态文档中：**不存在**（%s）"
                                         % (it["marker"], "符合预期" if it["marker"] not in mutated else "仍存在！")]}
            result["caught"] = it["marker"] not in mutated
    finally:
        # ⑤ 还原（无论成败）
        path.write_text(backup, encoding="utf-8")

    # ⑥ 复原后必须全绿（否则说明还原失败）
    if it["gates"]:
        after = _errs(it["gates"])
        result["after"] = after
        result["restored"] = all(len(v) == 0 for v in after.values())
    else:
        restored = path.read_text(encoding="utf-8")
        result["after"] = {"grep": ["标记 `%s` 在新态文档中：**存在**" % it["marker"]]}
        result["restored"] = it["marker"] in restored
    result["ok"] = bool(result.get("caught") and result.get("restored"))
    return result


def main() -> int:
    only = None
    for a in sys.argv[1:]:
        if a.isdigit():
            only = int(a)
    print("=" * 78)
    print("第1批 11 处文档修正 —— 失败样例/通过样例可复现（先还原旧态 → 跑同一门禁 → 再还原）")
    print("=" * 78)
    bad = 0
    for it in ITEMS:
        if only and it["no"] != only:
            continue
        r = _run_item(it)
        print("\n【%02d】%s" % (r["no"], r["desc"]))
        print("     文件：%s ｜ 判据：%s" % (r["file"], r["why"]))
        if r.get("error"):
            print("     ⚠ %s" % r["error"])
            bad += 1
            continue
        for k, v in (r.get("before") or {}).items():
            for line in v:
                print("     旧态 %s → ERROR：%s" % (k, line))
            if not v:
                print("     旧态 %s → （无 ERROR！判据未覆盖）" % k)
        for k, v in (r.get("after") or {}).items():
            print("     新态 %s → ERROR %d 项 %s" % (k, len(v), "（全绿）" if not v else v))
        print("     判定：%s" % ("✅ 旧态报红 + 新态全绿" if r["ok"] else "❌ 不成立"))
        if not r["ok"]:
            bad += 1
    print("\n" + "=" * 78)
    print("合计：%d 处不成立" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
