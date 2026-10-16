# -*- coding: utf-8 -*-
"""把 scripts/metaq2_sim/*.js 产出的场景 JSON 汇总为《场景模拟报告》。

用法：`python scripts/metaq2_sim/report.py`
输出：`docs/元质量_20261016/02_场景模拟报告.md`
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCEN = ROOT / "docs" / "元质量_20261016" / "_scenarios"
OUT = ROOT / "docs" / "元质量_20261016" / "02_场景模拟报告.md"

FILES = ["S1.json", "S2.json", "S3.json", "S4.json", "S5.json", "S6.json", "S7.json"]
COVER = {
    "S1": ["1. 登录系统", "2. 创建稽查项目", "3. 上传财税资料", "4. 等待解析完成",
           "5. 查看解析结果，人工校正错误", "6. 点击「开始稽查分析」", "7. 等待分析完成",
           "8. 查看风险清单", "9. 查看风险详情", "10. 生成风险分析报告", "11. 导出 PDF", "12. 退出系统"],
    "S2": ["1. 登录系统", "2. 打开待复核项目", "3. 逐条查看风险", "4. 确认高风险",
           "5. 排除误报", "6. 添加批注", "7. 提交复核结果"],
    "S3": ["1. 登录系统", "2. 打开待审批报告", "3. 查看风险汇总", "4. 查看证据链",
           "5. 确认报告", "6. 签字", "7. 归档"],
    "S4": ["1. 登录系统", "2. 打开用户管理（附加诊断）", "3. 创建用户", "4. 分配角色", "5. 配置权限", "6. 查看审计日志"],
    "S5": ["1. 上传错误格式文件", "2. 上传超大文件", "3. 上传重复文件", "4. 解析失败",
           "5. 分析中断", "6. 报告生成失败", "7. 权限不足", "8. 会话过期"],
    "S6": ["1. 多个用户同时登录", "2. 多个用户同时上传", "3. 多个用户同时分析",
           "4. 多个用户同时生成报告", "5. 多个用户同时复核"],
    "S7": ["1. 上传中途断网", "2. 分析中途断网", "3. 报告生成中途断网", "4. 恢复后继续"],
}
RESULT_CN = {"success": "成功", "fail": "失败", "blocked": "卡住"}


def load() -> list:
    out = []
    for f in FILES:
        p = SCEN / f
        if p.exists():
            out.append(json.loads(p.read_text(encoding="utf-8")))
    return out


def md_esc(v: object, limit: int = 260) -> str:
    s = str(v if v is not None else "").replace("|", "\\|").replace("\n", " ").strip()
    return (s[: limit - 1] + "…") if len(s) > limit else s


def main() -> int:
    data = load()
    lines: list[str] = []
    A = lines.append

    total_steps = sum(d["step_count"] for d in data)
    n_ok = sum(1 for d in data if d["conclusion"] == "success")
    n_bad = sum(1 for d in data if d["conclusion"] == "fail")
    n_blk = sum(1 for d in data if d["conclusion"] == "blocked")
    blockers = [b for d in data for b in d["blockers"]]
    fail_steps = [s for d in data for s in d["steps"] if s["result"] == "fail"]

    A("# 场景模拟报告")
    A("")
    A("> 指令：META-QUALITY-COMPREHENSIVE · 阶段 2（机制二：真实场景模拟）")
    A("> 执行时间：2026-10-16　执行方式：**真浏览器（Playwright/Chromium）+ 真 HTTP**，逐步操作")
    A("> 环境：**隔离实例**（独立数据目录与端口 8023，复制自本项目样例数据），不触碰生产数据目录")
    A("> 数据：使用本仓库**指定样例账套**（`WB-TRISK-SAMPLE-001`，深圳海更数字传媒有限公司）与自建合成测试企业；"
      "**不使用真实纳税人数据**")
    A("> 硬约束遵守：不用开发者视角（全部走用户可点的界面路径）· 不编造数据 · 不跳过测试 · 不修改现有规则")
    A("")
    A("## 统计")
    A("")
    A(f"- 场景数：**{len(data)}**")
    A(f"- 走通：**{n_ok}**")
    A(f"- 未走通：**{n_bad}**（其中整场景受阻 {n_blk}）")
    A(f"- 卡点：**{len(blockers)}**")
    A(f"- 步骤总数：**{total_steps}**（失败 {len(fail_steps)} 步）")
    A("")
    A("| 场景 | 名称 | 角色 | 步骤 | 成功 | 失败 | 卡住 | 结论 | 总耗时 |")
    A("|---|---|---|---|---|---|---|---|---|")
    for d in data:
        su = sum(1 for s in d["steps"] if s["result"] == "success")
        fa = sum(1 for s in d["steps"] if s["result"] == "fail")
        bl = sum(1 for s in d["steps"] if s["result"] == "blocked")
        A(f"| {d['scenario']} | {d['name']} | {d['role']} | {d['step_count']} | {su} | {fa} | {bl} "
          f"| {'✅ 走通' if d['conclusion'] == 'success' else ('❌ 未走通' if d['conclusion'] == 'fail' else '⚠ 受阻')} "
          f"| {d['total_ms'] / 1000:.1f}s |")
    A("")
    A("> 截图证据目录：`docs/元质量_20261016/场景模拟_截图/`（每步一张，文件名前缀即步骤编号）")
    A("> ⚠ 截图与导出的 PDF 为**可重生成产物**，按仓库既定约定**不入版本库**（单轮约 6MB）；"
      "逐步台账 JSON 在 `docs/元质量_20261016/_scenarios/`（进库，可追溯）。")
    A("")
    A("**复现全部场景**（隔离实例，端口 8023）：")
    A("```bash")
    A("# 1) 建隔离环境（5 角色账号 + 合成测试企业）")
    A("python scripts/metaq2_sim/set_env.py")
    A("# 2) 起隔离实例（APP_DATA_DIR 指向 _scenario_sim/data，端口 8023）")
    A("# 3) 逐个跑场景（NODE_PATH 指向工作区 node_modules）")
    A("node scripts/metaq2_sim/s1.js      # 场景1（含 3 分钟全量分析）")
    A("node scripts/metaq2_sim/s234.js    # 场景2/3（S4 另有独立脚本 s4.js）")
    A("node scripts/metaq2_sim/s4.js      # 场景4")
    A("node scripts/metaq2_sim/s5.js      # 场景5（异常）")
    A("node scripts/metaq2_sim/s67.js     # 场景6/7（并发 / 断网）")
    A("node scripts/metaq2_sim/perm_matrix.js   # 权限矩阵取证")
    A("python scripts/metaq2_sim/report.py      # 汇总生成本报告")
    A("```"
      )
    A("")

    A("## 场景详情")
    A("")
    for d in data:
        cover = COVER.get(d["scenario"], [])
        A(f"### {d['scenario']}　{d['name']}　（角色：{d['role']}，账号 `{d['user']}`）")
        A("")
        A(f"**覆盖指令步骤**：{'；'.join(cover) if cover else '—'}")
        A("")
        A(f"**结论**：{'✅ 场景走通' if d['conclusion'] == 'success' else ('❌ 场景未走通' if d['conclusion'] == 'fail' else '⚠ 场景受阻')}"
          f"　|　步骤 {d['step_count']}，失败 {d['fail_count']}，卡住 {d['blocked_count']}，卡点 {len(d['blockers'])}")
        A("")
        A("| 步骤 | 操作 | 结果 | 耗时 | 用户可见提示 / 读数 | 错误提示 | 卡点 | 截图 |")
        A("|---|---|---|---|---|---|---|---|")
        for s in d["steps"]:
            shot = Path(s["shot"]).name if s.get("shot") else "—"
            A(f"| {s['sid']} | {md_esc(s['name'], 40)} | {RESULT_CN.get(s['result'], s['result'])} "
              f"| {s['ms'] / 1000:.1f}s | {md_esc(s['note'], 300) or '—'} | {md_esc(s['error'], 240) or '—'} "
              f"| {md_esc(s['blocker'], 160) or '—'} | {shot} |")
        A("")
        if d.get("console_errors") or d.get("page_errors"):
            A(f"**浏览器控制台错误**：{len(d.get('console_errors') or [])} 条；"
              f"**未捕获异常**：{len(d.get('page_errors') or [])} 条")
            for e in (d.get("page_errors") or [])[:5]:
                A(f"- 未捕获异常：{md_esc(e, 200)}")
            for e in (d.get("console_errors") or [])[:5]:
                A(f"- 控制台：{md_esc(e, 200)}")
            A("")


    # ── 附：权限矩阵实测（场景5-7「权限不足」的系统性取证，同时供阶段7使用）──
    pm_path = SCEN / "PERM_MATRIX.json"
    if pm_path.exists():
        pm = json.loads(pm_path.read_text(encoding="utf-8"))
        A("")
        A("## 附：权限矩阵实测（系统性取证）")
        A("")
        A("> 动机：场景 2/3 实测发现「复核专家能生成报告」，与 `config/rbac.json` 声明（复核专家**不导出报告**）矛盾。")
        A("> 为免单点推断，对 5 个角色 × 12 个端点（含读/写两类）做**真 HTTP 逐项比对**：")
        A("> 判定 = 「声明有权限 ⇒ 期望非 403」∧「声明无权限 ⇒ 期望 403」。")
        A("")
        S = pm["summary"]
        A(f"- 探测项：**{S['total']}**（5 角色 × {len(pm['probes'])} 端点）")
        A(f"- 一致：**{S['consistent']}**")
        A(f"- **声明无权限却放行：{S['missing_enforcement']}**")
        A(f"- 声明有权限却被拒（误拒）：**{S['over_denied']}**")
        A(f"- 数据范围先行拦截(404，无法判定权限点)：**{S.get('scope_blocked', 0)}**")
        A("")
        A("| 角色 | 端点 | 所需权限 | 声明 | 实测 | 判定 |")
        A("|---|---|---|---|---|---|")
        for r in pm["rows"]:
            if r["verdict"].startswith("✅"):
                continue
            A(f"| {r['role']} | {r['name']} | `{r['perm']}` | {'有' if r['declared'] else '**无**'} "
              f"| HTTP {r['status']} | {r['verdict']} |")
        A("")
        A("**结论（只读类全部正确，写/动作类缺强制）**：")
        A("")
        A("- **只读类端点 100% 一致**：`project.view`/`risk.view`/`report.view`/`document.view`/`user.view`/`audit.view`")
        A("  六类均按声明放行或 403；跨角色对比可见它们**确实在服务端被强制**（如企业财务取用户名单 ⇒ 403）。")
        A("- **写/动作类端点未见权限点强制**：`risk.review`（复核处置）、`report.generate`（生成报告）、"
          "`analysis.run`（发起分析）、`document.write`（上传）、`project.write`（新建项目）"
          "五类在**声明无权限的角色**下仍返回 200/201（**已实际产生数据**，非仅放行）。")
        A("  ⇒ 现状可表述为：**认证 + 数据范围（租户/账套可见性）已强制；功能权限点（permission）未强制**。")
        A("- 误拒 **0** 处。")
        A("")
        A("> 复现：`node scripts/metaq2_sim/perm_matrix.js`（隔离实例，读为主；写操作落在测试项目上）")
        A("")

    A("## 本轮实证缺陷（供阶段 13 优化准入使用）")
    A("")
    A("> 判定纪律：以下每条均有**实测复现命令 / 可回读证据**；测试驱动自身的问题（选择器、时序、确认框）")
    A("> 一律**不计入缺陷**，只在场景详情里如实标注。")
    A("")
    A("| 编号 | 类型 | 缺陷 | 证据（可回读） | 影响面 | 建议优先级 |")
    A("|---|---|---|---|---|---|")
    A("| MQ2-D1 | 合规型 | **写/动作类端点未强制功能权限点**：`report.generate`/`analysis.run`/"
      "`document.write`/`project.write`/`risk.review` 在**声明无权限**的角色下仍 200/201 且**实际产生数据** | "
      "`PERM_MATRIX.json`；审计员发起分析 HTTP 201（job_id=1b32065b8eec）；复核专家生成报告 HTTP 200（doc_no=RW-1-…）；"
      "复核专家/审计员新建项目 HTTP 201 | 全部写操作接口 | **P0** |")
    A("| MQ2-D2 | 数据错误型 | **并发下报告版本号竞争**：版本号取「当前最大+1」无并发保护 ⇒ 多路并发生成登记**重复版本号** | "
      "`data/report_versions.jsonl`：`(RW-1-177dd0,V38)×3`、`(RW-1-8c983f,V44)×2`；复现 `node scripts/metaq2_sim/s67.js`（S6-04） | "
      "报告版本台账 / 报告编号 / 归档可追溯性 | **P0** |")
    A("| MQ2-D3 | 数据错误型 | **空内容被判「解析成功」**：①`.txt`（非财税资料）入库后 `parse_status=success`、`doc_type` 为空；"
      "②损坏的 `.xlsx` 解析后 `success` 但 `row_count=0/col_count=0/字段 0` | "
      "doc id=332（.txt）、doc id=333（伪装 xlsx，`tables=1` 但 `rows_preview=null`） | 解析页 / 资料清单「解析成功」语义 | **P0** |")
    A("| MQ2-D4 | 体验型（**已降级为观察项**） | 取消为「软取消」：前端 `window.confirm` + 服务端置旗标，"
      "引擎自然收尾。实测**取消有效**（终态 CANCELLED、进度停在 8 未达 100），但若引擎已过收尾点则可能仍出报告 | "
      "S5-05 实测：取消前「执行中」→ 取消后标签「已取消」，接口 `CANCELLED`，页面提示「本次结果不予采用」 | 分析任务页（用户预期管理） | P2 |")
    A("| MQ2-D6 | 阻断型 | **用户管理列表默认加载失败**：`static/users.html` 的组织筛选默认「全部组织」"
      "（`value=""`），而 `load()` 恒拼 `tenant_id=`（空串）；后端 `GET /api/v1/users` 的 `tenant_id` 为 "
      "`Optional[int]` ⇒ **FastAPI 422**，页面显示「加载失败：[object Object]」、表格停在「加载中…」 | "
      "浏览器实测：请求 `?page=1&page_size=20&q=&tenant_id=` → 422；`#f-tenant` 值=`""`；选择任一组织后列表正常 | "
      "用户管理页（进入即不可用） | **P0** |")
    A("| MQ2-D5 | 可观测型 | **前端仍调用 9 个已下线的 `/api/agi/*`**（AGI 子系统 2026-09-30 已整体移除），"
      "其中 `core.js` 两处 `fetch` 走 `.catch(()=>({}))` ⇒ **静默空面板** | 阶段 1 报告 T-03；`static/js/core.js:1022-1023` | 引擎状态面板 / 接口清单 | P1 |")
    A("")
    A("**未计为缺陷（测试驱动自身问题，已在场景详情注明）**：")
    A("")
    A("- S2-04/S2-05 首轮失败：取到**已复核**条目，服务端幂等拒绝（「本次未产生变更」）——是**正确行为**；")
    A("  改为按 `state=pending` 过滤后通过。")
    A("- S5-05 首轮失败：`window.confirm` 被浏览器自动化**默认驳回** ⇒ 取消请求未发出（`cancel_requested=false`）；")
    A("  加对话框接受后重测。")
    A("- 场景 2/3 首轮失败：测试账号未绑定样例账套 ⇒ 看不到项目（**权限设计正确**），补绑后通过。")
    A("- 场景 1 首轮失败：项目 USCC 与样例资料主体不一致 ⇒ 被**主体一致性闸门**正确拦截（本报告 S5-09 已作为正例保留）。")
    A("")
    A("## 卡点与失败清单（汇总）")
    A("")
    if not blockers and not fail_steps:
        A("无。")
    for b in blockers:
        A(f"- **卡点** `{b['sid']}` {b['name']}：{b['blocker']}")
    for s in fail_steps:
        A(f"- **失败** `{s['sid']}` {s['name']}：{s['error'] or s['note']}")
    A("")

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"已生成 {OUT}（{len(data)} 个场景 / {total_steps} 步）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
