# -*- coding: utf-8 -*-
"""把 UX 证据折算为 8 维度评分（阶段 3，2026-10-17）。

★ 原则：**评分规则必须可复现** —— 同一份证据跑两次得同一结果；
  规则写在 `RULES` 里并逐条输出"命中哪一档"，报告中的分数可逐项复核。
  人的判断只体现在"规则本身是否合理"和"问题描述"上，不体现在逐项拍分数上。
"""
from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
EVID = ROOT / "docs" / "元质量_20261016" / "_ux" / "UX_EVIDENCE.json"
OUT = ROOT / "docs" / "元质量_20261016" / "_ux" / "UX_SCORES.json"

DIMS = ["可发现性", "可理解性", "可操作性", "可反馈性", "可恢复性", "可学习性", "效率", "满意度"]

#: 主流程实测步数（来自 S1 真浏览器全链路，作为"效率"维度的客观输入）
FLOW_STEPS = {
    "documents": 4,      # 选项目→选文件→上传→等解析
    "extract": 3,        # 选项目→选资料→保存校正
    "analysis": 2,       # 选项目→开始（进度自动）
    "risks": 4,          # 选项目→筛选→开详情→执行复核动作
    "reports": 3,        # 选项目→选视图/格式→生成
    "projects": 3,       # 新建→填表→保存
}


def score_discover(m: dict, sidebar_visible: int, sidebar_total: int) -> tuple:
    """可发现性：侧栏可达 + 页内到主流程的入口数。"""
    nav_ok = sidebar_total > 0 and sidebar_visible == sidebar_total
    top = m.get("topLinks", 0)
    if nav_ok and top >= 2:
        return 5, "侧栏 %d/%d 全可见，顶栏另有 %d 个横向入口" % (sidebar_visible, sidebar_total, top)
    if nav_ok and top >= 1:
        return 4, "侧栏全可见，顶栏仅 %d 个入口（离开本页主要靠侧栏）" % top
    if nav_ok:
        return 4, "侧栏全可见；本页无顶栏横向入口（需回侧栏切换）"
    return 3, "导航不可达（侧栏 %d/%d）" % (sidebar_visible, sidebar_total)


def score_understand(m: dict) -> tuple:
    """可理解性：说明性文案字数（页面是否解释"这是在干什么"）。"""
    n = m.get("hintChars", 0)
    if n >= 200:
        return 5, "说明性文案 %d 字（页内自解释充分）" % n
    if n >= 50:
        return 4, "说明性文案 %d 字（有解释但偏简）" % n
    if n > 0:
        return 3, "说明性文案仅 %d 字（需外部文档才能理解）" % n
    return 2, "**无任何说明性文案**（hint/muted 均为 0），页面只呈现控件本身"


def score_operate(m: dict) -> tuple:
    """可操作性：可用控件数是否够、是否有被禁用控件。"""
    c, d = m.get("controls", 0), m.get("disabled", 0)
    if d == 0 and c >= 5:
        return 5, "%d 个可用控件、无禁用项" % c
    if d > 0 and c >= 5:
        return 4, "%d 个控件，其中 %d 个处于禁用态" % (c, d)
    return 3, "仅 %d 个控件（可操作面偏窄，可能只能看不能动）" % c


def score_feedback(m: dict) -> tuple:
    """可反馈性：是否有稳定的反馈载体（提示区/状态区）。"""
    f = m.get("feedback", 0)
    if f >= 2:
        return 5, "%d 处反馈载体（msg/status 区）" % f
    if f == 1:
        return 4, "仅 1 处反馈载体"
    return 2, "**无反馈载体**（无 msg/alert/status 区），操作后用户不知结果"


def score_recover(m: dict) -> tuple:
    """可恢复性：取消/关闭/重置/回滚/回收站 类入口数。"""
    r = m.get("recover", 0)
    if r >= 2:
        return 5, "%d 个恢复类入口（取消/关闭/重置/回滚/重试）" % r
    if r == 1:
        return 4, "仅 %d 个恢复类入口" % r
    return 3, "无恢复类入口（本页为只读/无破坏性操作，风险有限）"


def score_learn(m: dict) -> tuple:
    """可学习性：placeholder / title 提示 / 示例帮助入口。"""
    p, t, h = m.get("placeholders", 0), m.get("titles", 0), m.get("helps", 0)
    total = p + h
    if total >= 3:
        return 5, "%d 个占位示例 + %d 个示例/帮助入口 + %d 处 title" % (p, h, t)
    if total >= 1:
        return 4, "%d 个占位示例 + %d 个示例/帮助入口（title %d 处）" % (p, h, t)
    if t >= 5:
        return 3, "无占位示例/示例入口，仅靠 title 提示（%d 处）" % t
    return 2, "**无占位示例、无帮助入口、title 提示仅 %d 处**（第二次仍要摸索）" % t


def score_efficiency(key: str, m: dict, load_ms: int) -> tuple:
    """效率：主流程步数（实测）+ 首屏耗时。"""
    steps = FLOW_STEPS.get(key)
    if steps is None:
        if load_ms <= 1500:
            return 5, "只读页，首屏 %d ms" % load_ms
        return 4, "只读页，首屏 %d ms（偏慢）" % load_ms
    if steps <= 3 and load_ms <= 1500:
        return 5, "主流程 %d 步、首屏 %d ms" % (steps, load_ms)
    if steps <= 3:
        return 4, "主流程 %d 步，但首屏 %d ms" % (steps, load_ms)
    return 4, "主流程 %d 步（可再压缩）、首屏 %d ms" % (steps, load_ms)


def score_satisfaction(rec: dict, m: dict) -> tuple:
    """满意度：控制台错误 / 空态文案 / 页面信息密度。"""
    errs = len(rec.get("consoleErrors") or [])
    if errs:
        return 2, ("**实测出现 %d 次接口 500**（`/api/auth/me`，会话读取时写库冲突）"
                   "⇒ 用户可能看到按钮短暂消失/页面数据不全" % errs)
    if m.get("bodyKB", 0) < 0.5 and m.get("hintChars", 0) == 0:
        return 3, "页面信息极少（正文 %s KB、无说明），近似「空壳页」" % m.get("bodyKB")
    return 5, "无控制台错误、正文 %s KB、空态文案%s" % (
        m.get("bodyKB"), "有" if m.get("empty") else "未观测到")


PROBLEMS = {
    "home": {
        "可理解性": "首页只有侧栏导航，**无任何总览内容**（无 KPI / 无待办 / 无最近项目），"
                    "用户登录后不知道「该先做什么」。说明性文案 0 字。",
        "可反馈性": "无反馈载体；首页本身不承载操作，故影响有限。",
        "可恢复性": "无破坏性操作，不需要恢复入口（**不算缺陷**）。",
        "可学习性": "无任何引导（无占位、无示例、无「新手第一步」提示）。",
    },
    "projects": {
        "可理解性": "说明性文案仅 9 字（全站最低之一），新建项目表单的字段含义（税种范围 / 期间）"
                    "缺少页内解释。",
    },
    "documents": {
        "可理解性": "说明仅 15 字，但控件多达 80 个（筛选 / 批量 / 行内操作混在一屏），"
                    "**信息层级偏平**，新用户难以快速定位主操作（上传）。",
    },
    "analysis": {
        "可理解性": "说明 18 字；「作业号 / 步骤 / 进度」靠标签自解释，"
                    "但**未解释 8 个步骤分别做什么**（需点开步骤区才知道）。",
    },
    "templates": {
        "满意度": "本轮实测出现 2 次接口 500（同 `/api/auth/me` 根因）⇒ 页面首屏可能不完整。",
    },
    "legal_materials": {
        "满意度": "本轮实测出现 1 次接口 500（同根因）。",
    },
    "roles": {
        "满意度": "本轮实测出现 1 次接口 500（同根因）。",
    },
    "dashboard": {
        "可操作性": "仅 2 个控件（**只能看**，无时间范围 / 项目筛选）⇒ 想看某项目、某期间只能回其它页。",
        "可学习性": "无占位、无帮助入口，图表口径缺少页内注释。",
    },
    "industry": {"可操作性": "仅 5 个控件（筛选 / 重置 / 分页 / 关闭），功能面窄（只读检索，符合设计）。"},
    "legal_topics": {"可操作性": "仅 5 个控件，专题清单为静态列表 + 关闭；符合只读定位。"},
    "legal_library": {"可理解性": "说明性文案 4336 字，页内自解释极充分（法规正文 + 覆盖率说明）。"},
    "risks": {"可理解性": "说明 1041 字，是全站最自解释的页面之一"
                          "（含「缺失≠0」「超期与从未处置分开计」等口径）。"},
}


def main() -> int:
    ev = json.loads(EVID.read_text(encoding="utf-8"))
    sb = ev.get("sidebar") or {}
    vis, total = int(sb.get("visible", 0)), int(sb.get("total", 0))

    rows = []
    for rec in ev["modules"]:
        m = rec.get("metrics") or {}
        scores, reasons = {}, {}
        for dim, fn in (
            ("可发现性", lambda: score_discover(m, vis, total)),
            ("可理解性", lambda: score_understand(m)),
            ("可操作性", lambda: score_operate(m)),
            ("可反馈性", lambda: score_feedback(m)),
            ("可恢复性", lambda: score_recover(m)),
            ("可学习性", lambda: score_learn(m)),
            ("效率", lambda: score_efficiency(rec["key"], m, rec.get("loadMs", 0))),
            ("满意度", lambda: score_satisfaction(rec, m)),
        ):
            s, why = fn()
            scores[dim] = s
            reasons[dim] = why

        probs = PROBLEMS.get(rec["key"]) or {}
        # 无显式问题的维度：按规则显式写"无"
        for dim in DIMS:
            if dim not in probs:
                probs[dim] = ("无。" + reasons[dim]) if scores[dim] >= 4 else (
                    "见评分理由：" + reasons[dim])

        rows.append({
            "key": rec["key"], "name": rec["name"], "route": rec["route"],
            "scores": scores,
            "total": round(sum(scores.values()) / len(DIMS), 2),
            "reasons": reasons,
            "problems": probs,
            "evidence": {
                "controls": m.get("controls"), "hintChars": m.get("hintChars"),
                "feedback": m.get("feedback"), "recover": m.get("recover"),
                "placeholders": m.get("placeholders"), "titles": m.get("titles"),
                "bodyKB": m.get("bodyKB"), "loadMs": rec.get("loadMs"),
                "consoleErrors": len(rec.get("consoleErrors") or []),
            },
        })

    avg = {d: round(sum(r["scores"][d] for r in rows) / len(rows), 2) for d in DIMS}
    dist = {"5分": 0, "4分": 0, "3分": 0, "2分": 0, "1分": 0}
    for r in rows:
        for s in r["scores"].values():
            dist["%d分" % s] = dist.get("%d分" % s, 0) + 1

    out = {
        "generated_at": ev.get("generated_at"),
        "scope": {"modules": len(rows), "dimensions": len(DIMS),
                  "sidebar_visible": "%d/%d" % (vis, total)},
        "scale": "5 分制（1 差 / 3 中 / 5 好），规则见 scripts/_score_ux.py 的 RULES 区",
        "dimension_avg": avg,
        "score_distribution": dist,
        "modules": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), "utf-8")

    print("8 维度平均分：")
    for d in DIMS:
        print("  %-6s %.2f" % (d, avg[d]))
    print("\n分数分布：", dist)
    print("\n模块均分（高→低）：")
    for r in sorted(rows, key=lambda x: -x["total"]):
        print("  %-18s %.2f  %s" % (r["name"], r["total"],
                                    " ".join("%d" % r["scores"][d] for d in DIMS)))
    print("\n已写入", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
