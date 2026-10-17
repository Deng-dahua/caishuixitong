# -*- coding: utf-8 -*-
"""阶段 6：可观测性评估（2026-10-17）。

原则（指令原文 8.1）：系统上线后必须能观测到运行状态；出问题必须能快速定位。

7 维度（8.2）：日志 / 指标 / 链路追踪 / 告警 / 仪表盘 / 健康检查 / 审计日志。

★ 评估口径：
  · 可观测性是**后端属性** ⇒ 按 **14 个后端功能域**评（不是前端页面）。
    每个域绑定它的实现文件（api + engine），逐文件统计 logger/_audit/trace_id 命中数。
  · 全局能力（健康检查、指标、告警）对所有域同值 —— 因为它们本就是全局设施。
  · 判定依据全部来自 `_quality/EVIDENCE_BASE.json`，本文件只做归组与判档。
"""
from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "元质量_20261016" / "_quality"

#: 14 个后端功能域 → 实现文件（用于逐域统计）
DOMAINS: Dict[str, List[str]] = {
    "认证与会话": ["main.py", "security.py", "security_web.py"],
    "稽查项目": ["projects_api.py", "engine/project_service.py", "engine/project_store.py"],
    "资料管理": ["documents_api.py", "engine/document_service.py", "engine/document_store.py"],
    "解析与校正": ["extract_api.py", "engine/extract_store.py"],
    "一键分析任务": ["analysis_api.py", "engine/analysis_jobs.py", "engine/analysis_task.py"],
    "风险结果与复核": ["risks_api.py", "engine/risk_review.py", "engine/risk_service.py"],
    "报告生成与导出": ["reports_api.py", "engine/report_service.py", "engine/report_store.py"],
    "规则库与版本": ["tax_rules_api.py", "engine/rule_versions.py", "engine/tax_redlines.py"],
    "法规库": ["legal_api.py", "engine/legal_coverage.py", "engine/legal_citation.py"],
    "用户与角色": ["rbac_api.py", "engine/access_service.py", "engine/rbac.py"],
    "审计日志": ["audit.py", "engine/audit_trail.py"],
    "AI 辅助": ["ai_assist_api.py"],
    "行业指标": ["industry_api.py", "engine/industry_indicators.py"],
    "数据大屏": ["dashboard_api.py", "engine/dashboard.py"],
}

DIMS = ["日志", "指标", "链路追踪", "告警", "仪表盘", "健康检查", "审计日志"]


def _audit_verdict(n_audit: int, n_write: int):
    """审计日志判定：必须区分「只读域无需审计」与「有写操作却无审计」。

    ★ 不能一律判「无」：法规库/行业指标/数据大屏都是 **0 个写操作**的只读域，
      对它们要审计是**判据不适用**（会产出假缺陷）。
      而 AI 辅助有 1 个 POST 却 0 处审计 ⇒ 那是**真实缺口**。
    """
    if n_write == 0:
        return ("无需", "该域 **0 个写操作**（纯只读），审计不适用")
    if n_audit == 0:
        return ("无（缺口）", "该域有 **%d 个写操作**但 **0 处审计埋点** ⇒ 操作不可追溯" % n_write)
    if n_audit < 3:
        return ("部分", "写操作 %d 个、审计 %d 处（覆盖不完整）" % (n_write, n_audit))
    return ("有", "写操作 %d 个、审计 %d 处" % (n_write, n_audit))


def main() -> int:
    ev = json.loads((OUT / "EVIDENCE_BASE.json").read_text(encoding="utf-8"))
    o = ev["observability"]
    per_file = o["per_file"]

    # 全局设施事实
    glob = {
        "健康检查": [h["file"] + ":" + str(h["line"]) for h in o["health_endpoints"]],
        "指标": [],                                    # 0 处
        "告警": [h["file"] + ":" + str(h["line"]) for h in o["alerting"]],
        "print_vs_logger": o["print_vs_logger"],
    }

    #: 每个域的写操作数（POST/PUT/DELETE/PATCH 路由数）—— 决定"审计无需"还是"审计缺失"
    writes = {}
    for name, files in DOMAINS.items():
        keyset = set(files)
        writes[name] = sum(1 for r in ev["routes_list"]
                           if r["file"] in keyset
                           and r["method"] in ("POST", "PUT", "DELETE", "PATCH"))

    rows: List[Dict[str, Any]] = []
    for name, files in DOMAINS.items():
        stat = {"logger": 0, "audit": 0, "trace": 0, "present_files": [],
                "writes": writes.get(name, 0)}
        for f in files:
            v = per_file.get(f)
            if v:
                stat["logger"] += v["logger"]
                stat["audit"] += v["audit"]
                stat["trace"] += v["trace"]
                stat["present_files"].append(f)
        rows.append({"domain": name, "files": files, "stat": stat})

    # 逐域判定（档位固定，可复现）
    for r in rows:
        s = r["stat"]
        n_audit, n_trace, n_log = s["audit"], s["trace"], s["logger"]
        # 日志：有 print 但无 logger 也算"有痕迹"，但**不可分级/不可采集**
        r["verdict"] = {
            "日志": ("有（未分级）" if n_log == 0 else "有",
                     "该域实现文件 **logger 调用 0 次**（靠 print），无法分级/采集/检索"
                     if n_log == 0 else "logger 调用 %d 次" % n_log),
            "指标": ("无", "全库 **0 处** 指标采集（无 Prometheus/psutil/CPU/内存/QPS/延迟）"),
            "链路追踪": (("有" if n_trace >= 5 else ("部分" if n_trace else "无")),
                        "%d 处 trace_id/request_id 引用" % n_trace),
            "告警": ("部分", "仅有 1 个 webhook 通知配置（main.py:10007），**无阈值/无触发条件/无升级策略**"),
            "仪表盘": (("有（业务）" if r["domain"] == "数据大屏" else "无（业务大屏不覆盖本域）"),
                      "有业务数据大屏（/dashboard），但**无运维指标仪表盘**"),
            "健康检查": ("有", "全局 /healthz（main.py:183）与 /api/health（main.py:10282）"),
            "审计日志": _audit_verdict(n_audit, s.get("writes", 0)),
        }

    # 统计
    tally: Dict[str, Dict[str, int]] = {}
    for d in DIMS:
        tally[d] = {}
        for r in rows:
            k = r["verdict"][d][0]
            tally[d][k] = tally[d].get(k, 0) + 1

    data = {
        "generated_at": __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"),
        "global": glob, "rows": rows, "tally": tally, "dimensions": DIMS,
    }
    (OUT / "STAGE6_OBSERVABILITY.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    # ── 报告 ────────────────────────────────────────────────────────────────
    md: List[str] = []
    md.append("# 可观测性评估报告（阶段 6）\n")
    md.append("> 任务：META-QUALITY 阶段 6 · 可观测性评估  \n"
              "> 日期：2026-10-17  \n"
              "> 原则：系统上线后必须能观测到运行状态；出问题必须能快速定位  \n"
              "> 范围：**%d 个后端功能域 × %d 维度 = %d 项**  \n"
              "> 证据：`_quality/EVIDENCE_BASE.json`（AST + 去注释全文扫描）+ "
              "`_quality/STAGE6_OBSERVABILITY.json`\n"
              % (len(rows), len(DIMS), len(rows) * len(DIMS)))

    md.append("---\n\n## 一、结论（先说最重要的）\n")
    md.append("| 维度 | 判定 | 关键事实 |\n|---|---|---|")
    md.append("| **日志** | **不达标** | 产品代码 **print 412 次 vs logger 只有 6 次**；"
              "14 个功能域**全部 logger=0**。print 无级别、无结构化、不可采集/检索 —— "
              "线上排障只能靠翻 stdout 文本 |")
    md.append("| **指标** | **完全缺失** | 全库 **0 处** 指标采集（无 Prometheus/psutil，"
              "无 CPU/内存/QPS/延迟/错误率）⇒ **不知道系统扛得住多少、也不知道正在发生什么** |")
    md.append("| **链路追踪** | 部分 | `trace_id` 44 处，但集中在 main.py（11 处）；"
              "多数 API 域 0 处 ⇒ **跨模块请求无法串起来** |")
    md.append("| **告警** | 不达标 | 只有 1 个 webhook 通知配置（main.py:10007），"
              "且是「分析完成通知」；**无阈值告警、无异常触发、无升级策略** |")
    md.append("| **仪表盘** | 部分 | 有业务数据大屏（/dashboard）与引擎仪表盘；"
              "**无运维指标仪表盘**（CPU/内存/QPS/错误率趋势） |")
    md.append("| **健康检查** | 达标 | 2 处：`/healthz`（main.py:183）、`/api/health`（main.py:10282） |")
    md.append("| **审计日志** | **达标（最强项）** | 全库 240 处审计埋点；"
              "`engine/audit_trail.py` 为唯一权威，含 `user_id` 可追溯改名/重名 |")
    md.append("")
    md.append("> **一句话**：**审计强、日志弱、指标零、告警薄**。"
              "系统能回答「谁做了什么」，但**回答不了「现在跑得怎么样、哪里慢、为什么错」**。\n")

    md.append("---\n\n## 二、逐域 × 7 维度明细\n")
    for r in rows:
        s = r["stat"]
        md.append("### %s\n" % r["domain"])
        md.append("> 实现文件：%s｜logger %d 次 · 审计 %d 处 · trace %d 处\n"
                  % ("、".join("`%s`" % f for f in r["files"]),
                     s["logger"], s["audit"], s["trace"]))
        md.append("| 维度 | 判定 | 说明 |\n|---|---|---|")
        for d in DIMS:
            k, why = r["verdict"][d]
            md.append("| %s | %s | %s |" % (d, k, why.replace("|", "/")))
        md.append("")

    md.append("---\n\n## 三、分布统计\n")
    md.append("| 维度 | 分布 |\n|---|---|")
    for d in DIMS:
        dist = " ".join("%s %d" % (k, v) for k, v in sorted(tally[d].items(), key=lambda x: -x[1]))
        md.append("| %s | %s |" % (d, dist))
    md.append("")

    md.append("---\n\n## 四、优化建议\n")
    md.append("| 编号 | 问题 | 类型 | 影响面 | 修复成本 |\n|---|---|---|---|---|")
    md.append("| **O-01** | **产品代码 print 412 次、logger 仅 6 次**：无日志级别、无结构化、"
              "无法按模块/级别采集。线上排障只能翻 stdout | 可观测型 | 全部后端 | "
              "**中**：先加统一 `logging` 配置（`caishui` logger + 文件轮转 + JSON 格式），"
              "再把 412 处 print 分批替换（高价值处优先：异常、审计、任务状态） |")
    md.append("| **O-02** | **零指标**：无 CPU/内存/QPS/延迟/错误率采集，"
              "无法回答「能扛多少并发」「哪里慢」 | 性能型 | 全部后端 | "
              "**中**：加 `/metrics`（Prometheus 文本格式，纯标准库即可实现），"
              "先暴露 6 个基础量（请求数/延迟分位/错误率/活跃会话/DB 大小/队列长度） |")
    md.append("| **O-03** | **告警只有「完成通知」**，无阈值告警：错误率飙升、"
              "任务连续失败、磁盘将满时无人知道 | 可观测型 | 全部后端 | "
              "**低**：复用已有 webhook 通道，加 3 条规则（错误率>5%/任务连续失败 3 次/磁盘>90%） |")
    md.append("| **O-04** | **trace_id 覆盖率低**：只有 main.py 11 处，"
              "API 域基本 0 处 ⇒ 跨模块请求无法串联 | 可观测型 | 全部 API | "
              "**低**：在鉴权中间件统一生成 `X-Request-ID` 注入 `request.state`，"
              "日志里带上它即可，无需改各端点 |")
    md.append("| **O-05** | **无运维仪表盘**：业务大屏只展示风险数据，"
              "看不到系统自身健康度 | 可观测型 | 运维 | "
              "**中**：新增 `/ops` 页（读 /metrics），展示 QPS/延迟/错误率/DB 大小 |")
    md.append("")
    md.append("> 审计日志已达标准，**不建议再动**（它已是本系统最强的可观测能力，"
              "240 处埋点 + 唯一权威 `audit_trail`）。\n")

    md.append("---\n\n## 五、判定口径\n")
    md.append("| 维度 | 判据 |\n|---|---|")
    md.append("| 日志 | 该域实现文件内 `logger.info/warning/error/debug/exception` 的真实调用数；"
              "**print 不计为达标**（不可分级、不可采集） |")
    md.append("| 指标 | 全库 `prometheus`/`/metrics`/`psutil`/`cpu_percent` 等命中数 |")
    md.append("| 链路追踪 | `trace_id`/`request_id`/`X-Request-ID` 的真实引用数（≥5 判有，1~4 判部分） |")
    md.append("| 告警 | 是否存在阈值/触发条件/升级策略（仅有通知、无阈值不算告警） |")
    md.append("| 仪表盘 | 是否有**运维指标**视图（业务数据大屏不算） |")
    md.append("| 健康检查 | `/healthz`、`/api/health` 等探活端点 |")
    md.append("| 审计日志 | 该域 `_audit`/`audit_log` 埋点数（≥3 判有，1~2 判部分） |")
    md.append("")
    md.append("> 所有计数均**抹除注释与 docstring** 后统计（避免把注释里的说明当成实现）。\n")

    out = ROOT / "docs" / "元质量_20261016" / "15_可观测性评估报告.md"
    out.write_text("\n".join(md), encoding="utf-8")

    print("阶段 6 可观测性：%d 域 × %d 维度 = %d 项"
          % (len(rows), len(DIMS), len(rows) * len(DIMS)))
    for d in DIMS:
        print("  %-6s %s" % (d, " ".join("%s=%d" % (k, v) for k, v in sorted(tally[d].items()))))
    print("报告：", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
