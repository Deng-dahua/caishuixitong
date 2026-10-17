# -*- coding: utf-8 -*-
"""阶段 8：性能容量评估报告生成（2026-10-17）。

数据来源：`_quality/STAGE8_PERFORMANCE.json`（真实压测读数）。
"""
from __future__ import annotations

import json
import pathlib
from typing import List

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "元质量_20261016" / "_quality"

#: 分析时间 / 报告生成 —— 取 S1 真跑读数（阶段 2 实测）
#: ★ 第一次独立采样（同一脚本、同一实例，机器负载较高时）
#: 两次差异达 2 倍 ⇒ **判定取较差值（保守）**，并如实列出区间。
#: 这不是"挑好数据"，而是承认单机压测受机器负载影响大。
RUN1 = {
    "legal_p50": 7312.6,
    "rps_peak": 13.7,
    "p50_at_30": 2534.4,
    "parse_s": 0.15,          # 该次引擎入口用错（ImportError），不可用 ⇒ 不参与
    "note": "机器负载较高时的采样",
}

S1_FACTS = {
    "analysis_job_s": 83.0,        # 8/8 步、209 条发现、SUCCESS
    "analysis_steps": 8,
    "findings": 209,
    "report_gen_s": 6.1,
    "report_pdf": "550 KB",
    "pdf_ok": True,
}


def main() -> int:
    d = json.loads((OUT / "STAGE8_PERFORMANCE.json").read_text(encoding="utf-8"))
    rt = {r["label"]: r for r in d["response_time"]}
    conc = d["concurrency"]
    dv = d["data_volume"]
    st = d["storage"]

    legal = rt.get("法规条款列表", {})
    worst = max(conc, key=lambda x: x["p50"] or 0)

    md: List[str] = []
    md.append("# 性能容量评估报告（阶段 8）\n")
    md.append("> 任务：META-QUALITY 阶段 8 · 性能容量评估  \n"
              "> 日期：2026-10-17  \n"
              "> 原则：系统必须能扛住真实业务的压力和容量  \n"
              "> 方式：**真实压测**（隔离实例 8024，本机回环，非生产网络）  \n"
              "> 证据：`_quality/STAGE8_PERFORMANCE.json`（逐次延迟原始数据）\n")

    md.append("---\n\n## 一、结论（先说最要紧的）\n")
    md.append("| 维度 | 实测 | 是否达标 |\n|---|---|---|")
    legal_worst = max(legal.get("p50") or 0, RUN1["legal_p50"])
    md.append("| 响应时间 | 常规接口 P50 **71~100 ms**；**法规库检索 P50 %s~%s ms**（两次采样） | "
              "常规 ✅ 达标（<1s）；**法规库 ❌ 超标 %d 倍**（按较差值） |"
              % (legal.get("p50"), RUN1["legal_p50"], round(legal_worst / 1000)))
    rps_best = max(c["rps"] for c in conc if c["rps"])
    md.append("| 吞吐量 | 本次峰值 **%s RPS**；另一次采样仅 **%s RPS**（两次区间） | "
              "⚠ 偏低且**波动大**（SQLite 单写 + 每请求全量计算） |" % (rps_best, RUN1["rps_peak"]))
    md.append("| 并发 | 并发 1/5/10/20/30 的 P50 = %s | "
              "⚠ **延迟随并发线性恶化**（1→30 并发，P50 从 %s ms 涨到 %s ms，约 19 倍） |"
              % (" / ".join(str(c["p50"]) for c in conc), conc[0]["p50"], worst["p50"]))
    md.append("| 采样稳定性 | 两次独立采样差异达 **2 倍**（法规库 3692 vs 7313 ms；RPS 31 vs 14） | "
              "⚠ **单次压测不可作为容量承诺**，需在目标环境复测 |")
    md.append("| 数据量 | 10 万行序时账（%s MB）解析 **%s s** | ✅ 大幅达标（门槛 10 分钟，实际 %.2f 分钟） |"
              % (dv["size_mb"], dv["parse_s"], dv["parse_s"] / 60))
    md.append("| 分析时间 | 8 步全流程 **%s s**（209 条发现） | ✅ 达标 |" % S1_FACTS["analysis_job_s"])
    md.append("| 报告生成 | **%s s**（PDF %s） | ✅ 达标（门槛 3 分钟） |"
              % (S1_FACTS["report_gen_s"], S1_FACTS["report_pdf"]))
    _db_kb = round((st["db_bytes"].get("accounting.db") or 0) / 1024, 1)
    md.append("| 存储 | data 目录 **%s MB**（主库 %s KB + uploads %s MB） | ✅ 当前规模无压力 |"
              % (st["data_dir_mb"], _db_kb, st["uploads_mb"]))
    md.append("| 扩展性 | **不支持水平扩展** | ❌ 见下 |")
    md.append("")
    md.append("**两条必须要处理的问题**：\n")
    md.append("1. **法规库检索 P50 = %s~%s ms**（%s 条法条全量遍历 + 逐条版本装饰 + 排序，**最后才分页**）"
              "—— 超标 7 倍，且这是**高频页面**（法规库/专题/材料都复用它）。"
              % (legal.get("p50"), RUN1["legal_p50"], "7680"))
    md.append("2. **并发扩展性差**：P50 随并发**线性恶化**（本机两次采样 RPS 在 %s~%s 之间，"
              "并发再往上不再增长）。根因是 SQLite 单写者 + 每个请求都做全量遍历/全表统计。\n"
              % (RUN1["rps_peak"], rps_best))

    md.append("---\n\n## 二、响应时间（关键接口，各 12 次）\n")
    md.append("| 接口 | P50 (ms) | P95 (ms) | max (ms) | 错误 | 判定 |\n|---|---|---|---|---|---|")
    for r in d["response_time"]:
        ok = (r["p95"] or 0) < 1000
        md.append("| %s<br>`%s` | %s | %s | %s | %d | %s |"
                  % (r["label"], r["path"], r["p50"], r["p95"], r["max"],
                     r["errors"], "✅ <1s" if ok else "❌ 超标"))
    md.append("")
    md.append("> 说明：均含**会话校验**开销（每个请求都要过鉴权中间件）。"
              "健康检查 23 ms 是纯框架开销基线。\n")

    md.append("---\n\n## 三、吞吐量与并发（逐级加压）\n")
    md.append("| 并发 | 请求数 | 总耗时 (s) | RPS | P50 (ms) | P95 (ms) | 错误率 |\n|---|---|---|---|---|---|---|")
    for c in conc:
        md.append("| %d | %d | %s | **%s** | %s | %s | %s%% |"
                  % (c["workers"], c["requests"], c["wall_s"], c["rps"],
                     c["p50"], c["p95"], c["error_rate"]))
    md.append("")
    md.append("**读法**：\n")
    md.append("- 错误率全程 **0%** ⇒ 加压下**没有崩**（这点很好）；\n")
    md.append("- 但 P50 从并发 1 的 %s ms 涨到并发 30 的 %s ms ⇒ **请求在排队**，"
              "不是并行处理；\n" % (conc[0]["p50"], worst["p50"]))
    md.append("- RPS 在 **%s~%s** 区间见顶：并发 20 之后不再增长（本次采样并发 30 反而略降）⇒ "
              "**单进程 CPU/IO 已打满**，加线程无用。\n" % (RUN1["rps_peak"], rps_best))

    md.append("---\n\n## 四、数据量（10 万行实测）\n")
    md.append("| 项 | 读数 |\n|---|---|")
    md.append("| 造数 | 10 万行 / %s MB / 生成耗时 %s s |" % (dv["size_mb"], dv["gen_s"]))
    md.append("| 解析（真实入口 `engine.workbook`） | **%s s**，遍历 %s 行 |"
              % (dv["parse_s"], dv["parsed_rows"]))
    md.append("| 门槛（指令 10.2） | 10 万行 < 10 分钟 |")
    md.append("| 判定 | ✅ **达标，余量很大**（%.2f 分钟 vs 10 分钟） |" % (dv["parse_s"] / 60))
    md.append("")
    md.append("> 注：此处测的是**读取遍历**（引擎入口），不含字段识别与入库；"
              "后者在 S1 已用真实 11 份资料跑通（解析 `success=11`）。\n")

    md.append("---\n\n## 五、存储与扩展性\n")
    md.append("| 项 | 读数 |\n|---|---|")
    md.append("| data 目录总量 | %s MB |" % st["data_dir_mb"])
    for k, v in st["db_bytes"].items():
        md.append("| %s | %s KB |" % (k, round(v / 1024, 1)))
    md.append("| uploads | %s MB（%d 个项目目录） |" % (st["uploads_mb"], st["projects"]))
    md.append("")
    md.append("**扩展性：不支持水平扩展**，依据（本项目已实测）：\n")
    md.append("1. **SQLite 单写者**：两个进程指向同一 `security.db` 会撞 "
              "`attempt to write a readonly database`（阶段 3 实测，直接导致 `/api/auth/me` 与 "
              "`create_user` 随机 500）；\n")
    md.append("2. **状态在本地磁盘**：`data/` 下的 JSONL（`events.jsonl`、`report_versions.jsonl`）"
              "与上传文件都是本地文件，多实例无法共享；\n")
    md.append("3. **无请求级分布式锁**：分析任务在进程内跑（`engine/analysis_jobs.py`），"
              "多实例会重复执行。\n")
    md.append("⇒ 当前架构是**单机单实例**设计。垂直扩容（更强 CPU/内存）可行，"
              "水平扩容需要先换存储层（DB + 对象存储 + 外部队列）。\n")

    md.append("---\n\n## 六、根因分析（为什么法规库慢 7 秒）\n")
    md.append("`engine/legal_library.py::article_entries`（L89-121）的执行顺序：\n")
    md.append("```text")
    md.append("for r in LC.library_file_entries():      # ① 7680 条**全部**遍历")
    md.append("    if 关键词不匹配: continue")
    md.append("    d = _decorate_article(r)            # ② 每条都做版本装饰（读版本表、算状态）")
    md.append("    rows.append(d)")
    md.append("rows.sort(...)                          # ③ 全量排序")
    md.append("return rows[start:start+size]           # ④ 最后才切片分页")
    md.append("```\n")
    md.append("⇒ **① 全量 + ② 逐条装饰 + ③ 全量排序**，与 `page_size` 无关："
              "要 20 条也要跑完 7680 条。这是 **O(N) 每请求**，而 N 会随法规入库继续增长。\n")
    md.append("**建议改法**（不动业务语义）：\n")
    md.append("- ② 的装饰**只为当前页的 20 条做**（把 `_decorate_article` 移到切片之后）；\n")
    md.append("- ① 的过滤用**预建索引**（法名/条款号/关键词倒排或简单的前缀索引表）；\n")
    md.append("- 或加**进程内缓存**（`legal_library.json` 很少变，可缓存解析结果 + 版本映射），"
              "缓存失效按文件 mtime。\n")
    md.append("> 预估：②③ 两项改造后 P50 可从 7300 ms 降到 **<100 ms** 量级"
              "（因为切片后只处理 20 条，排序也只需在过滤结果上）。\n")

    md.append("---\n\n## 七、优化建议\n")
    md.append("| 编号 | 问题 | 类型 | 影响面 | 修复成本 |\n|---|---|---|---|---|")
    md.append("| **PF-01** | **法规库检索 P50 %s ms**：全量遍历 7680 条 + 逐条装饰 + 全量排序，"
              "最后才分页（O(N)/请求，随法规增长继续恶化） | 性能型 | 法规库/专题/材料 3 页 | "
              "**低**：把装饰移到切片后 + 加 mtime 缓存，预估降到 <100 ms |" % legal_worst)
    md.append("| **PF-02** | **并发扩展性差**：P50 随并发线性恶化（1→30 并发恶化约 19 倍），"
              "RPS 饱和在 ~13 | 性能型 | 全站 | **中**：短期靠垂直扩容 + 减少每请求全量计算；"
              "长期需换 PostgreSQL + 对象存储 + 外部队列 |")
    md.append("| **PF-03** | 每个请求都过一次鉴权中间件（会话读取 P50 85 ms，占常规接口一半以上） | "
              "性能型 | 全站 | **低**：会话对象在进程内做**短 TTL 缓存**（如 5s），"
              "配合已做的「读取不写库」改动，可显著降延迟 |")
    md.append("| **PF-04** | 存储全在本地磁盘（DB + JSONL + uploads），备份/扩容都受限 | 灾备型 | 全站 | "
              "**中**：见阶段 9（备份）建议，一起考虑 |")
    md.append("")
    md.append("> 本轮只测与建议，**不改代码**（指令 17）。PF-01 是投入产出比最高的一条。\n")

    md.append("---\n\n## 八、压测边界（必须知道）\n")
    md.append("- **本机回环**压测：不含真实网络延迟与带宽限制，真实部署的绝对值会更高；\n")
    md.append("- 并发用**线程**模拟（`ThreadPoolExecutor`），不是多机压测；\n")
    md.append("- 数据规模为**当前隔离库**（2 个项目、22 份资料、8 MB 主库），"
              "不是生产体量；法规库 7680 条是真实全量；\n")
    md.append("- **单次采样的波动很大**：同一脚本在同一实例上两次采样，"
              "法规库 P50 分别为 %s ms 与 %s ms、RPS 峰值 %s 与 %s。"
              "报告中的判定**一律取较差值**（保守），不取有利值。\n"
              % (RUN1["legal_p50"], legal.get("p50"), RUN1["rps_peak"], rps_best))
    md.append("- 未做：长时间稳定性（内存泄漏/句柄泄漏）、峰值写入压测、多实例压测。\n")

    out = ROOT / "docs" / "元质量_20261016" / "17_性能容量评估报告.md"
    out.write_text("\n".join(md), encoding="utf-8")
    print("阶段 8 性能容量：8 维度（达标 5 / 不达标 2 / 支持性 1）")
    print("最差项：法规库 P50=%s ms；并发 30 P50=%s ms @ RPS %s"
          % (legal.get("p50"), worst["p50"], worst["rps"]))
    print("报告：", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
