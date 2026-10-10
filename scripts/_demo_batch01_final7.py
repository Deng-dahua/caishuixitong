# -*- coding: utf-8 -*-
"""第1批「7 处不一致」的**可复现抓捕/放行**脚本（用户《最终修正指令》第三/第四步）。

对每一处做**双向**验证（只跑一次"看报不报"是不够的）：
  ① **强制置为「不一致状态」** → 跑**同一个**门禁 → 必须报 ERROR（否则判据没抓住）
  ② **强制置为「一致状态」**   → 跑**同一个**门禁 → **本处消费点**不得再报错（否则判据假红）
  ③ **还原文件**（失败也还原）；还原后复核，绝不留脏文件
  ④ **聚合**：7 处（8 个消费点）**同时**置为一致 ⇒ D1/D4 在这 5 个主题上必须 0 ERROR

```bash
./.venv/Scripts/python.exe scripts/_demo_batch01_final7.py        # 全部 + 聚合
./.venv/Scripts/python.exe scripts/_demo_batch01_final7.py 6      # 只看第 6 处
```
退出码：0 = 全部成立；1 = 有任一处未被抓住（**判据仍有缺口**）。

★ 三条**已踩过的坑**（都在本脚本里上了锁）：
  · **变异无效 ⇒ 假通过**："置为一致"后若文件**没有实际变化**（锚点命中已存在的形态）⇒ 报"用例无效"，
    不得当作通过（`changed` 必须非空）；
  · **"本来就是旧态"不是错误**：置为不一致时若文件本就是旧态，属正常（不得误报"变异未生效"）；
  · **锚点撞车**：`08` 第一张 U 表表头与"修好态"的 6 列表头**逐字相同** ⇒ 第 7 处改用
    **行号 + 行文本双重锚点**（行文本不符即报"用例无效"）。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DOCDIR = ROOT / "docs" / "第01批_触发条件与认定要件分离"
F01 = "01_Skill设计文档.md"
F05 = "05_回归测试报告.md"
F06 = "06_写入系统证据.md"
F08 = "08_未完成事项清单.md"
TBL_FIXED = "| 编号 | 状态 | 事项描述 | 未完成原因 | 需要什么输入 | 是否阻断下一批 |"
TBL_BROKEN = "| 编号 | 事项描述 | 未完成原因 | 需要什么输入 | 是否阻断下一批 |"
SEP_FIXED = "|---|---|---|---|---|---|"
SEP_BROKEN = "|---|---|---|---|---|"

# targets      = [(文件, 一致态子串, 不一致态子串)]
# line_targets = [(文件, 行号, 一致态整行, 不一致态整行)]   ← 锚点会撞车时用
def A(number_id):
    """**现算**权威值（不硬编码）—— 锚点写死会随权威变动而静默失效。"""
    from engine import doc_consistency_core as core
    core.reload_config()
    for n in core.config()["numbers"]:
        if n["id"] == number_id:
            v, why = core.authority_value(n["authority"])
            assert v is not None, (number_id, why)
            return v
    raise KeyError(number_id)


def _cur(fname, pattern):
    import re
    m = re.search(pattern, (DOCDIR / fname).read_text(encoding="utf-8"))
    return m.group(1) if m else None


ITEMS = [
    dict(no=1, gate="D1", subject="全量回归 passed",
         desc="05 §2「passed」vs 05 文末自证段「passed」不一致",
         targets=[(F05, "| passed | **%s** |" % _cur(F05, r"\| passed \| \*{0,2}(\d+)\*{0,2} \|"),
                  "| passed | **1424** |")],
         why="新增 `consistency_checks: CONS-05-passed`（**同文件内多个单值必须相等**）"),
    dict(no=2, gate="D1", subject="全量回归耗时",
         desc="05 §2「耗时」vs 05 文末自证段「耗时」不一致",
         targets=[(F05, "| 耗时 | **%ss**" % _cur(F05, r"\| 耗时 \| \*{0,2}([\d.]+)s\*{0,2}"),
                  "| 耗时 | **62.04s**")],
         why="新增 `consistency_checks: CONS-05-duration`（耗时是**易变值** ⇒ 只做文件内自洽，**不做数值权威**）"),
    dict(no=3, gate="D1", subject="Skill 总数",
         desc="05 §6「total 56」vs `config/skill_specs.json` 实测 61",
         targets=[(F05, "# 实测输出：validate [] | total 61", "# 实测输出：validate [] | total 56")],
         why="新增权威 `skill_total`（`authority.kind = json_len`，权威 = `config/skill_specs.json → skills` 条数）"),
    dict(no=4, gate="D1", subject="Skill 总数",
         desc="06 §1「Skill 总数 56」（表格 + 命令实测输出两处）vs 实测 61",
         targets=[(F06, "| Skill 总数 | **61**（本批 56 → Skill 化 +5） |", "| Skill 总数 | **56**（配置前 54） |"),
                  (F06, "#          validate [] | total 61", "#          validate [] | total 56")],
         why="同上（`skill_total` 的 claims 覆盖 06 §1 两处）"),
    dict(no=5, gate="D1", subject="Skill 总数",
         desc="06 §5「Skill 总数 56」+ 文末自证「total 56」vs 实测 61",
         targets=[(F06, "，Skill 总数 **61**。", "，Skill 总数 **56**。"),
                  (F06, "/ total 61）；", "/ total 56）；")],
         why="同上（**同一指标的第二个消费点**，此前完全没接线 ⇒ 缺口 B：权威已登记但 claims 覆盖不全）"),
    dict(no=6, gate="D1", subject="门禁调用行号",
         desc="06 §4「调用位置 第 11123 行」vs `grep -n` 实测 11200",
         targets=[(F06, "| 调用位置 | 第 **11200** 行", "| 调用位置 | 第 **11123** 行"),
                  (F01, "第 11200 行并入总链", "第 11123 行并入总链")],
         why="权威早已登记（`gate_call_line` = grep_line → 11200），**但 claims 只覆盖 02** ⇒ 扩到 06，"
             "并顺带扩到 01（**同一指标的第三个消费点**，本轮由「消费点枚举」顺带发现）"),
    dict(no=7, gate="D4", subject="表格列数",
         desc="08「补做新增的未完成事项」表：表头 5 列 vs 数据行 6 列",
         line_targets=[(F08, 112, TBL_FIXED, TBL_BROKEN), (F08, 113, SEP_FIXED, SEP_BROKEN)],
         why="新增判据 `check_tables()`（D4）—— **表格每一行的列数必须等于表头列数**"),
]


def _errs(gate):
    from engine import (doc_number_authority as D1, rule_reference_sync as D2,
                        doc_residue_scan as D3, todo_status_sync as D4, doc_ref_graph as D5)
    from engine import doc_consistency_core as core
    core.reload_config()
    m = {"D1": D1, "D2": D2, "D3": D3, "D4": D4, "D5": D5}
    out = [i for i in m[gate].audit() if i["level"] == "ERROR"]
    core.reload_config()
    return out


def _apply(it, texts: dict, direction: str):
    """在 `texts = {文件: 文本}` 上施加方向；返回 (新 texts, 错误说明)。"""
    out = dict(texts)
    for fname, idx, f_line, b_line in it.get("line_targets", []):
        want, other = (b_line, f_line) if direction == "broken" else (f_line, b_line)
        lines = out[fname].split("\n")
        cur = lines[idx - 1] if 0 < idx <= len(lines) else None
        if cur == want:
            continue
        if cur == other:
            lines[idx - 1] = want
            out[fname] = "\n".join(lines)
        else:
            return None, "行 %d 文本不符（当前：%s）⇒ 用例无效（不静默通过）" % (idx, str(cur)[:70])
    for fname, f_sub, b_sub in it.get("targets", []):
        want, other = (b_sub, f_sub) if direction == "broken" else (f_sub, b_sub)
        t = out[fname]
        if want in t:
            continue
        if other in t:
            out[fname] = t.replace(other, want, 1)
        else:
            return None, "锚点未命中（一致/不一致两种形态都找不到）⇒ 用例无效：%s" % other[:60]
    return out, ""


def _read(files):
    return {f: DOCDIR.joinpath(f).read_text(encoding="utf-8") for f in files}


def _changed_map(a: dict, b: dict):
    out = {}
    for f in a:
        la, lb = a[f].split("\n"), b[f].split("\n")
        ch = {i + 1 for i in range(max(len(la), len(lb)))
              if (la[i] if i < len(la) else None) != (lb[i] if i < len(lb) else None)}
        if ch:
            out[f] = ch
    return out


def _files_of(it):
    return sorted({t[0] for t in (it.get("targets", []) + it.get("line_targets", []))})


def _run(it):
    files = _files_of(it)
    snap = _read(files)
    res = dict(it)
    res.update({"ok": False, "changed": [], "broken_hits": [], "fixed_hits": [],
                "broken_changed": [], "files": files})
    try:
        # ---------- ① 置为「不一致状态」 ----------
        broken, err = _apply(it, snap, "broken")
        if err:
            res["error"] = err
            return res
        for f, t in broken.items():
            DOCDIR.joinpath(f).write_text(t, encoding="utf-8")
        bad = _errs(it["gate"])
        res["broken_hits"] = ["%s ｜ %s" % (e.get("where"), str(e.get("detail"))[:150])
                              for e in bad if it["subject"] in str(e.get("detail"))]
        res["caught"] = bool(res["broken_hits"])
        res["broken_changed"] = sorted("%s:%d" % (f, n) for f, s in _changed_map(snap, broken).items()
                                       for n in s)

        # ---------- ② 置为「一致状态」（只修本处消费点） ----------
        fixed, err = _apply(it, snap, "fixed")
        if err:
            res["error"] = err
            return res
        cm = _changed_map(snap, fixed)
        res["changed"] = sorted("%s:%d" % (f, n) for f, s in cm.items() for n in s)
        # ★ 口径：「一致态」本就在文件里 ⇒ cm 为空是**正常**（快照本来就是修好态）；
        #   只有当快照**也**本来就是不一致态（broken_changed 为空）而这里又改不动时，
        #   才说明**变异未生效**（用例无效，不得当作通过）——这是实测踩过的假通过坑。
        if not cm and not res["broken_changed"]:
            res["error"] = "**变异未生效**（两个方向都改不动 ⇒ 用例无效，不得当作通过）"
            return res
        for f, t in fixed.items():
            DOCDIR.joinpath(f).write_text(t, encoding="utf-8")
        # ★ 断言目标取**两个方向的并集**：否则"快照本来已是修好态"时 targets 为空 ⇒ 断言空洞（假通过）
        targets = set(res["changed"]) | set(res["broken_changed"])
        bad = _errs(it["gate"])
        res["fixed_hits"] = ["%s ｜ %s" % (e.get("where"), str(e.get("detail"))[:130])
                             for e in bad if str(e.get("where", "")) in targets]
        res["passes"] = not res["fixed_hits"]
    finally:
        for f, t in snap.items():
            DOCDIR.joinpath(f).write_text(t, encoding="utf-8")
    res["restored"] = all(DOCDIR.joinpath(f).read_text(encoding="utf-8") == snap[f] for f in snap)
    res["ok"] = bool(res.get("caught") and res.get("passes") and res.get("restored"))
    return res


SUBJECTS = ("全量回归 passed", "全量回归耗时", "Skill 总数", "门禁调用行号", "表格列数")


def _subjects_error():
    hits = []
    for g in ("D1", "D4"):
        for e in _errs(g):
            d = str(e.get("detail"))
            if any(s in d for s in SUBJECTS):
                hits.append("%s ｜ %s ｜ %s" % (g, e.get("where"), d[:120]))
    return hits


def _all_at_once():
    """7 处（8 个消费点）**同时**置为一致 ⇒ 这 5 个主题上必须 0 ERROR（决定性证据）。"""
    files = sorted({f for it in ITEMS for f in _files_of(it)})
    snap = _read(files)
    cur = dict(snap)
    try:
        for it in ITEMS:
            cur, err = _apply(it, cur, "fixed")
            if err:
                return {"error": "%s（第 %d 处）" % (err, it["no"]), "before": []}
        for f, t in cur.items():
            DOCDIR.joinpath(f).write_text(t, encoding="utf-8")
        return {"before": _subjects_error(), "error": ""}
    finally:
        for f, t in snap.items():
            DOCDIR.joinpath(f).write_text(t, encoding="utf-8")


def main() -> int:
    only = next((int(a) for a in sys.argv[1:] if a.isdigit()), None)
    print("=" * 80)
    print("第1批 7 处不一致 —— 抓捕/放行**双向**可复现（置为不一致 → 跑同一门禁 → 置为一致 → 再跑 → 还原）")
    print("=" * 80)
    bad = 0
    for it in ITEMS:
        if only and it["no"] != only:
            continue
        r = _run(it)
        print("\n【%02d】%s" % (r["no"], r["desc"]))
        print("     涉及文件：%s ｜ 门禁：%s ｜ 判据：%s"
              % ("、".join(r.get("files") or []), r["gate"], r["why"]))
        if r.get("error"):
            print("     ⚠ %s" % r["error"])
            bad += 1
            continue
        print("     ① 置为不一致（%s）⇒ 报 ERROR %d 条：%s"
              % ("、".join(r.get("broken_changed") or ["本就为不一致态"]),
                 len(r["broken_hits"]), "✅ 抓住" if r["caught"] else "❌ 未抓住"))
        for h in r["broken_hits"][:3]:
            print("        %s" % h)
        _pts = sorted(set(r["changed"]) | set(r["broken_changed"]))
        print("     ② 置为一致（本处消费点 %s）⇒ 该处 ERROR %d 条：%s"
              % ("、".join(_pts) if _pts else "（快照本就是一致态）",
                 len(r["fixed_hits"]), "✅ 放行" if r["passes"] else "❌ 仍报错"))
        for h in r["fixed_hits"][:2]:
            print("        %s" % h)
        print("     ③ 已还原：%s ｜ 判定：%s" % ("✅" if r["restored"] else "❌",
                                                "✅ 抓得住 + 放得过" if r["ok"] else "❌ 不成立"))
        if not r["ok"]:
            bad += 1

    if not only:
        agg = _all_at_once()
        print("\n" + "-" * 80)
        if agg.get("error"):
            print("【聚合】⚠ %s" % agg["error"])
            bad += 1
        else:
            print("【聚合】7 处**同时**置为一致 ⇒ D1/D4 在这 5 个主题上 ERROR %d 条：%s"
                  % (len(agg["before"]), "✅ 全部放行" if not agg["before"] else "❌ 仍有残留"))
            for h in agg["before"][:5]:
                print("        %s" % h)
            if agg["before"]:
                bad += 1

    print("\n" + "=" * 80)
    print("合计：%d 处不成立" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
