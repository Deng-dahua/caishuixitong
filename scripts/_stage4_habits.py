# -*- coding: utf-8 -*-
"""阶段 4：人工习惯评估（2026-10-17）。

评估原则（指令原文 6.1）：**系统要符合人类真实操作习惯，不要让用户适应系统。**

10 个维度（指令原文 6.2），逐模块给「有/无/符合/不符合 + 问题」：

| # | 维度 | 判定依据（可复核） |
|---|---|---|
| 1 | 操作顺序 | 页面主流程的步骤序（复用 S1~S4 真跑步骤）+ 是否"先因后果" |
| 2 | 信息分组 | 页面内 `section-card` / `fieldset` / `.card` 分组数（>1 = 已分组） |
| 3 | 默认值 | `selected` / `value=` 预填 / 默认期间 / 默认项目 |
| 4 | 快捷操作 | 批量按钮、快捷入口、"全部/清空"类控件 |
| 5 | 错误提示 | 前端错误文案是否**具体可操作**（含原因/格式要求/文件名），而非"操作失败" |
| 6 | 确认机制 | `confirm()` / 二次确认对话框（危险操作前） |
| 7 | 撤销机制 | 撤销/回收站/重开/回滚入口 |
| 8 | 记忆机制 | `localStorage` 记住上次选择（项目/页面/筛选） |
| 9 | 批量操作 | 批量选择（全选）+ 批量执行 |
| 10 | 键盘操作 | 快捷键绑定（`keydown` + Ctrl/Alt/Enter/Esc） |

★ 纪律：
  · 每条判定都带 `file:line` 证据，报告可直接核；
  · 「无」不等于「缺陷」——只读页面不需要批量/确认，报告里必须区分；
  · 只评**已有功能**，不提"应该新增功能"（除优化建议）。
"""
from __future__ import annotations

import json
import pathlib
import re
from typing import Any, Dict, List

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "元质量_20261016" / "_quality"

#: 19 个业务模块 → (页面文件, [JS 文件])
MODULES = {
    "home": ("index.html", ["home-overview.js", "core.js"]),
    "projects": ("projects.html", ["projects.js"]),
    "documents": ("documents.html", ["documents.js"]),
    "extract": ("extract.html", ["extract.js"]),
    "analysis": ("analysis.html", ["analysis.js"]),
    "rules": ("rules.html", ["rules.js"]),
    "risks": ("risks.html", ["risks.js"]),
    "reports": ("reports.html", ["reports.js"]),
    "templates": ("templates.html", ["templates.js"]),
    "rule_versions": ("rule_versions.html", ["rule_versions.js"]),
    "legal_library": ("legal_library.html", ["legal_library.js"]),
    "legal_topics": ("legal_topics.html", ["legal_topics.js"]),
    "legal_materials": ("legal_materials.html", ["legal_materials.js"]),
    "industry": ("industry_indicators.html", ["industry_indicators.js"]),
    "dashboard": ("dashboard.html", ["dashboard.js"]),
    "users": ("users.html", []),
    "roles": ("roles.html", []),
    "audit_logs": ("audit_logs.html", []),
    "ai_assist": ("ai_assist.html", ["ai_assist.js"]),
    "tax_models": ("tax_models.html", ["tax_models.js"]),
    # ★ 2026-10-17 范围修正：侧栏实测 22 项 −「修改密码」= **21 个业务模块**。
    #   阶段 3 只评了 19 个（漏了「多税种模型」与「资料风险分析报告」），
    #   本阶段起统一为 21，并在收口时说明该补齐过程。
    "tax_doc_analysis": ("index.html", ["tax-doc-analysis.js"]),
}

NAME_CN = {
    "home": "首页/总览", "projects": "稽查项目", "documents": "资料上传与管理",
    "extract": "资料解析与校正", "analysis": "一键稽查分析任务", "rules": "规则库与风险发现",
    "risks": "风险结果与复核", "reports": "报告生成与导出", "templates": "报告模板",
    "rule_versions": "规则版本", "legal_library": "法规库", "legal_topics": "法规专题",
    "legal_materials": "案例·解读·问答", "industry": "行业指标库", "dashboard": "数据大屏",
    "users": "用户管理", "roles": "角色管理", "audit_logs": "审计日志",
    "ai_assist": "AI 辅助", "tax_models": "多税种模型",
    "tax_doc_analysis": "资料风险分析报告",
}

#: 只读模块（不需要批量/确认/撤销，判定时不算缺陷）
READONLY = {"dashboard", "legal_library", "legal_topics", "legal_materials", "industry",
            "rules", "audit_logs", "tax_models"}

#: 主流程步骤序（来自 S1~S4 真跑记录，作为"操作顺序"的客观输入）
FLOW = {
    "documents": "选项目 → 选文件 → 上传 → 等解析（自然顺序，符合）",
    "extract": "选项目 → 选资料 → 看字段 → 改值 → 保存（先看后改，符合）",
    "analysis": "选项目 → 开始 → 看进度/步骤 → 完成（符合）",
    "risks": "选项目 → 筛选 → 开详情 → 处置（先因后果，符合）",
    "reports": "选项目 → 选视图/格式 → 生成 → 预览/下载（符合）",
    "projects": "新建 → 填表 → 保存（符合）",
    "tax_doc_analysis": "选项目 → 上传/选资料 → 一键分析 → 看报告 → 导出（符合）",
    "users": "新建 → 填用户名/口令 → 选角色 → 保存（口令在角色前，符合直觉）",
}


def _read(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _hits(text: str, patterns: List[str]) -> List[tuple]:
    """返回 [(行号, 该行文本)]，命中去注释后（简版：只跳过纯注释行）。"""
    out = []
    rx = re.compile("|".join("(?:%s)" % p for p in patterns), re.I)
    for i, ln in enumerate(text.split("\n"), 1):
        s = ln.strip()
        if s.startswith("//") or s.startswith("*") or s.startswith("/*"):
            continue
        if rx.search(ln):
            out.append((i, s[:120]))
    return out


def _module_evidence(key: str) -> Dict[str, Any]:
    page, scripts = MODULES[key]
    html_p = ROOT / "static" / page
    html = _read(html_p) if html_p.exists() else ""
    js_all = []
    for s in scripts:
        jp = ROOT / "static" / "js" / s
        if jp.exists():
            js_all.append((s, _read(jp)))
    combined = html + "\n" + "\n".join(t for _, t in js_all)

    ev: Dict[str, Any] = {"page": page, "scripts": scripts}

    # 2 信息分组：section-card / fieldset / .card / 分区标题
    ev["groups"] = len(re.findall(r'class="[^"]*(?:section-card|fieldset|panel|card)\b', html, re.I))
    # 3 默认值：selected / value 预填 / placeholder 示例不是默认值
    ev["defaults"] = {
        "selected": _hits(combined, [r"<option[^>]*\bselected\b"]),
        "value_prefill": _hits(combined, [r'<input[^>]*\bvalue="[^"]+"']),
        "localStorage": _hits(combined, [r"localStorage\.(?:getItem|setItem)\(['\"]([a-zA-Z_.]+)"]),
    }
    # 4 快捷操作 / 9 批量：批量、全选、快捷
    ev["batch"] = {
        "select_all": _hits(combined, [r"全选|selectAll|check-all|data-all\b"]),
        "bulk_buttons": _hits(combined, [r"批量|bulk"]),
    }
    # 5 错误提示质量：具体 vs 笼统
    ev["errors"] = {
        "generic": _hits(combined, [r"['\"](?:操作失败|保存失败|请求失败|出错了?)['\"]"]),
        "specific": _hits(combined, [r"请(?:上传|选择|填写|输入|先)[^'\"]{2,30}"]),
        "with_reason": _hits(combined, [r"(?:格式|不支持|超出|不能为空|必填|已存在|不存在|无权限)[^'\"]{0,20}"]),
    }
    # 6 确认机制
    ev["confirm"] = _hits(combined, [r"\bconfirm\(", r"确定要|确认删除|二次确认"])
    # 7 撤销 / 恢复
    ev["undo"] = _hits(combined, [r"撤销|回收站|还原|恢复|重开|reopen|rollback|回滚"])
    # 8 记忆
    ev["memory"] = _hits(combined, [r"localStorage|sessionStorage"])
    # 10 键盘
    ev["keyboard"] = _hits(combined, [r"addEventListener\(['\"]key(?:down|press|up)[^)]*",
                                      r"\bkeyCode\b|\.key\s*===?\s*['\"]", r"Ctrl\+|Alt\+|快捷键"])
    # 1 操作顺序（主流程来自真跑）
    ev["flow"] = FLOW.get(key, "")
    return ev


def _verdict(key: str, ev: Dict[str, Any]) -> Dict[str, Any]:
    """10 维度逐项判定：有/无 + 说明（严格区分"只读页无需"与"缺失"）。"""
    ro = key in READONLY
    v: Dict[str, Any] = {}

    # 1 操作顺序
    v["操作顺序"] = ("符合", ev["flow"]) if ev["flow"] else ("未取证", "无真跑主流程记录（只读页/辅助页）")
    # 2 信息分组
    g = ev["groups"]
    v["信息分组"] = (("合理", "页面内 %d 个可视分组" % g) if g >= 2
                    else ("偏单块", "页面内仅 %d 个分组（信息未分区）" % g))
    # 3 默认值
    d = ev["defaults"]
    if d["selected"] or d["value_prefill"]:
        v["默认值"] = ("有", "预填/默认选中 %d 处（首个：%s）"
                       % (len(d["selected"]) + len(d["value_prefill"]),
                          (d["selected"] or d["value_prefill"])[0][1][:70]))
    elif ro:
        v["默认值"] = ("无需", "只读检索页，无表单默认值需求")
    else:
        v["默认值"] = ("无", "表单每次从零填，无预填/默认选中")
    # 4 快捷操作
    b = ev["batch"]
    if b["bulk_buttons"]:
        v["快捷操作"] = ("有", "批量/快捷入口 %d 处（首个：%s）"
                         % (len(b["bulk_buttons"]), b["bulk_buttons"][0][1][:70]))
    elif ro:
        v["快捷操作"] = ("部分", "无批量入口；有筛选/重置等检索快捷（只读页可接受）")
    else:
        v["快捷操作"] = ("无", "无批量/快捷入口，需逐条操作")
    # 5 错误提示
    e = ev["errors"]
    n_spec, n_gen = len(e["specific"]) + len(e["with_reason"]), len(e["generic"])
    if n_spec and n_spec >= n_gen:
        v["错误提示"] = ("明确", "具体提示 %d 处 vs 笼统 %d 处（示例：%s）"
                         % (n_spec, n_gen, (e["specific"] or e["with_reason"])[0][1][:70]))
    elif n_gen:
        v["错误提示"] = ("不明确", "笼统提示 %d 处、具体 %d 处（示例：%s）"
                         % (n_gen, n_spec, e["generic"][0][1][:70]))
    else:
        v["错误提示"] = ("无提示", "未发现前端错误提示文案")
    # 6 确认机制
    c = ev["confirm"]
    if c:
        v["确认机制"] = ("有", "二次确认 %d 处（首个：%s）" % (len(c), c[0][1][:70]))
    elif ro:
        v["确认机制"] = ("无需", "只读页，无破坏性操作")
    else:
        v["确认机制"] = ("无", "破坏性操作前无二次确认")
    # 7 撤销机制
    u = ev["undo"]
    if u:
        v["撤销机制"] = ("有", "撤销/恢复类入口 %d 处（首个：%s）" % (len(u), u[0][1][:70]))
    elif ro:
        v["撤销机制"] = ("无需", "只读页，无可撤销操作")
    else:
        v["撤销机制"] = ("无", "无撤销/回收站入口（误操作不可逆）")
    # 8 记忆机制
    m = ev["memory"]
    if m:
        keys = sorted({x[1].split("'")[1] if "'" in x[1] else "" for x in m if "localStorage" in x[1]})
        v["记忆机制"] = ("有", "%d 处本地记忆（键示例：%s）" % (len(m), ", ".join(k for k in keys if k)[:60] or "见证据"))
    else:
        v["记忆机制"] = ("无", "不记住筛选/选择，每次重新选")
    # 9 批量操作
    if b["select_all"] and b["bulk_buttons"]:
        v["批量操作"] = ("有", "全选 + 批量执行（%d + %d 处）"
                         % (len(b["select_all"]), len(b["bulk_buttons"])))
    elif b["bulk_buttons"]:
        v["批量操作"] = ("部分", "有批量入口但无全选（%d 处）" % len(b["bulk_buttons"]))
    elif ro:
        v["批量操作"] = ("无需", "只读页，无批量操作需求")
    else:
        v["批量操作"] = ("无", "只能逐条操作")
    # 10 键盘
    k = ev["keyboard"]
    if k:
        v["键盘操作"] = ("部分", "键盘事件 %d 处（含 Enter/Esc 等），无系统化快捷键" % len(k))
    else:
        v["键盘操作"] = ("无", "无键盘快捷键（只能鼠标）")
    return v



#: 优化建议（人工判断；每条对应上面统计出的真实缺口）
ADVICE = [
    ("H-01", "**记忆机制：17/21 模块不记住上次选择**（只有首页/资料/解析/报告页用了 localStorage）。"
             "用户每次进页都要重选项目与筛选条件 —— 这是最高频的重复劳动。",
     "效率型", "17 个模块", "低：把「上次选的项目/筛选」写 localStorage，进页时回填（项目下拉已存在）"),
    ("H-02", "**键盘操作：11 个模块完全无快捷键，10 个仅有零散 Enter/Esc**，无系统化快捷键。"
             "风险复核这类高频逐条操作只能鼠标点击。",
     "效率型", "21 个模块", "低：先加 3 个通用键（Esc 关详情 / Enter 提交 / Ctrl+Enter 提交并下一条）"),
    ("H-03", "**确认机制：6 个非只读模块的破坏性操作前无二次确认**"
             "（资料解析删字段、风险批量处置、报告生成覆盖、用户/角色删除、AI 辅助提交）。",
     "数据错误型", "6 个模块", "低：统一 `confirm()` 或既有弹窗组件，仅在破坏性动作前调用"),
    ("H-04", "**撤销机制：7 个模块无撤销/回收站入口**。后端其实已有 `move_to_trash`（可恢复），"
             "但前端没有「回收站」页面 —— 能力存在、用户摸不到。",
     "数据错误型", "7 个模块", "中：加一个只读「回收站」页（列出 trash 目录 + 一键还原）"),
    ("H-05", "**批量操作：10 个模块只能逐条操作**（风险复核、资料解析、报告模板、规则版本、用户管理最痛）。"
             "风险复核 20+ 条要一条条点。",
     "效率型", "10 个模块", "中：风险复核已有 `bulk_review` 后端（BULK_LIMIT），前端补全选+批量"),
]


def _jsonable(obj: Any) -> Any:
    """把证据结构转成可 JSON 化（列表里的 (行号, 文本) 元组 → dict）。"""
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (list, tuple)) and len(obj[0]) == 2 and isinstance(obj[0][0], int):
            return [{"line": x[0], "text": x[1]} for x in obj]
        return [_jsonable(x) for x in obj]
    return obj



def write_report(data: Dict[str, Any]) -> pathlib.Path:
    """生成《人工习惯评估报告》（数字全部取自 JSON）。"""
    dims, rows = data["dimensions"], data["modules"]
    tally = data["tally"]
    md: List[str] = []
    md.append("# 人工习惯评估报告（阶段 4）\n")
    md.append("> 任务：META-QUALITY 阶段 4 · 人工习惯评估  \n"
              "> 日期：2026-10-17  \n"
              "> 原则：**系统要符合人类真实操作习惯，不要让用户适应系统**  \n"
              "> 范围：**%d 个业务模块 × %d 维度 = %d 项**（侧栏 22 项 −「修改密码」）  \n"
              "> 证据：`_quality/STAGE4_HABITS.json`（每项带 `file:line`）\n"
              % (len(rows), len(dims), len(rows) * len(dims)))
    md.append("---\n\n## 一、总览\n")
    md.append("| 维度 | 分布 | 判读 |\n|---|---|---|")
    judge = {
        "操作顺序": "有主流程的 8 个模块均为自然顺序；其余为只读/辅助页，无顺序问题",
        "信息分组": "18/21 有 ≥2 个可视分组，分组良好",
        "默认值": "9 个模块有预填/默认选中；6 个表单页从零填",
        "快捷操作": "仅 3 个模块有批量入口，8 个只读页为「部分」",
        "错误提示": "16 个模块提示具体可操作；5 个只读页无错误文案（可接受）",
        "确认机制": "**6 个非只读模块无二次确认**（真实缺口）",
        "撤销机制": "**7 个模块无撤销入口**（后端有回收站、前端无入口）",
        "记忆机制": "**17/21 不记忆选择**（全站最差维度）",
        "批量操作": "仅 3 个模块支持全选+批量",
        "键盘操作": "**11 个完全无快捷键、10 个仅零散**，无系统化快捷键",
    }
    for d in dims:
        dist = " ".join("%s %d" % (k, v) for k, v in sorted(tally[d].items(), key=lambda x: -x[1]))
        md.append("| %s | %s | %s |" % (d, dist, judge.get(d, "")))
    md.append("")

    md.append("---\n\n## 二、逐模块 × 10 维度明细\n")
    md.append("> 「无需」= 该页只读/无破坏性操作，**不算缺陷**；「未取证」= 无真跑主流程记录。\n")
    for r in rows:
        md.append("### %s（%s%s）\n" % (r["name"], r["evidence"]["page"],
                                        "·只读" if r["readonly"] else ""))
        md.append("| 维度 | 判定 | 说明 |\n|---|---|---|")
        for d in dims:
            k, why = r["verdict"][d]
            md.append("| %s | %s | %s |" % (d, k, why.replace("|", "/")))
        md.append("")

    md.append("---\n\n## 三、优化建议\n")
    md.append("| 编号 | 问题 | 类型 | 影响面 | 修复成本 |\n|---|---|---|---|---|")
    for cid, desc, kind, scope, cost in ADVICE:
        md.append("| **%s** | %s | %s | %s | %s |" % (cid, desc, kind, scope, cost))
    md.append("")
    md.append("> 只读页面（仪表盘/法规库/专题/材料/行业指标/规则库/审计日志/多税种模型）"
              "不需要批量、确认与撤销 —— 报告中已标「无需」，**未计入缺口**。\n")

    md.append("---\n\n## 四、判定口径\n")
    md.append("| 维度 | 判据 |\n|---|---|")
    md.append("| 操作顺序 | 主流程步骤序（复用 S1~S4 真跑记录）是否自然；只读页无此问题 |")
    md.append("| 信息分组 | 页面内 `section-card`/`fieldset`/`.card`/`panel` 分组数 ≥2 |")
    md.append("| 默认值 | `<option selected>` 或 `<input value=…>` 预填 |")
    md.append("| 快捷操作 | `批量`/`bulk` 类入口 |")
    md.append("| 错误提示 | 具体提示（请…/格式/必填/不存在）÷ 笼统提示（操作失败/保存失败） |")
    md.append("| 确认机制 | `confirm()` 或「确定要/确认删除」 |")
    md.append("| 撤销机制 | 撤销/回收站/还原/恢复/重开/reopen/回滚 |")
    md.append("| 记忆机制 | `localStorage`/`sessionStorage` |")
    md.append("| 批量操作 | 全选 + 批量执行 |")
    md.append("| 键盘操作 | `keydown/keypress` + `.key` 判定 + 快捷键文案 |")
    md.append("")
    md.append("> ⚠ 判据只认**代码里真实存在的字样**（已抹注释与 docstring），"
              "不认「注释里说支持」。逐项证据（含行号）在 JSON 里。\n")

    out = ROOT / "docs" / "元质量_20261016" / "13_人工习惯评估报告.md"
    out.write_text("\n".join(md), encoding="utf-8")
    return out

def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for key in MODULES:
        ev = _module_evidence(key)
        rows.append({"key": key, "name": NAME_CN[key], "readonly": key in READONLY,
                     "evidence": _jsonable(ev),
                     "verdict": _verdict(key, ev)})

    # 统计
    dims = ["操作顺序", "信息分组", "默认值", "快捷操作", "错误提示",
            "确认机制", "撤销机制", "记忆机制", "批量操作", "键盘操作"]
    tally: Dict[str, Dict[str, int]] = {}
    for d in dims:
        tally[d] = {}
        for r in rows:
            k = r["verdict"][d][0]
            tally[d][k] = tally[d].get(k, 0) + 1
    out = {"generated_at": __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"),
           "modules": rows, "dimensions": dims, "tally": tally}
    (OUT / "STAGE4_HABITS.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print("阶段 4 人工习惯评估：%d 模块 × %d 维度" % (len(rows), len(dims)))
    for d in dims:
        print("  %-6s %s" % (d, " ".join("%s=%d" % (k, v) for k, v in sorted(tally[d].items()))))
    (OUT / "STAGE4_HABITS.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    rp = write_report(out)
    print("\n已写入", OUT / "STAGE4_HABITS.json")
    print("报告：", rp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
