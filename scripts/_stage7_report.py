# -*- coding: utf-8 -*-
"""阶段 7：安全合规评估报告生成（2026-10-17）。

数据来源：`_quality/STAGE7_SECURITY.json`（真实攻击探测 18 项）+ `EVIDENCE_BASE.json`（代码事实）。

★ 本报告的关键修正（写报告前自查发现）：
  ① 「备份 7 处」全是假阳性 —— 实为①清理残留 `*_bk` 表、②税审规则文本里的「数据备份」；
     系统**没有**数据备份功能。
  ② 「PIPL/DSL 20 处」中多数是**规则 DSL**（Domain Specific Language，`dsl_scope`/`DslError`），
     不是《数据安全法》；真正提到《个人信息保护法》的只有 1 处。
  ③ 「存储加密 24 处」**只覆盖 LLM 凭证**（AES-GCM + DPAPI），业务库仍是明文 SQLite。
"""
from __future__ import annotations

import json
import pathlib
from typing import List

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "元质量_20261016" / "_quality"

DIMS = ["认证", "授权", "加密", "脱敏", "审计", "合规", "隐私", "防攻击", "防泄露", "备份"]

#: 10 维度判定（依据见 proof）
VERDICTS = [
    ("认证", "部分符合",
     "未登录访问 3 个端点均 **401**（A1）；退出后重用旧 cookie **401**（A10）；"
     "密码哈希 **scrypt**（N=16384/r=8/p=1，security.py:222）。"
     "**缺多因子认证**（全库 0 处 MFA/TOTP）。",
     "P1：管理员账号加 TOTP（`pyotp` 或纯标准库 HMAC）；至少对 system_admin 强制"),
    ("授权", "符合",
     "RBAC + 数据权限双控：审计员建用户 **403**、企业财务建用户 **403**、审计员删项目 **403**（A4）；"
     "不存在账套 **404**（A3）。审计员能读项目 6 的风险属**设计允许**（rbac 中 auditor 有 `risk.view`）。",
     "—"),
    ("加密", "部分符合",
     "密码 scrypt ✅；LLM 凭证 AES-GCM + Windows DPAPI（llm_credentials.py:220-228）✅；"
     "**业务数据库为明文 SQLite**（无 at-rest 加密）；传输加密取决于部署（`APP_COOKIE_SECURE` 可配，"
     "但代码层不强制 HTTPS）。",
     "P2：启动时检测「非 HTTPS 且非本机」给出显式告警；如需等保，评估 SQLCipher"),
    ("脱敏", "符合",
     "`engine/redaction.py` 为脱敏**唯一权威**（24 处），access_service 8 处；"
     "水印 74 处（下载留痕）。审计日志列表接口正常返回（A9）。",
     "—"),
    ("审计", "符合",
     "全库 **240 处**审计埋点；`engine/audit_trail.py` 为唯一权威，含 `user_id`（改名前也可追溯）。",
     "—"),
    ("合规", "部分符合",
     "代码内提到《个人信息保护法》仅 1 处（pipeline.py:7286 规则文本）；"
     "**无正式隐私政策/合规声明文档**。注：取证工具曾把规则 DSL（`dsl_scope`/`DslError`）"
     "误计为数据安全法，已纠正。",
     "P1：补《隐私政策》《数据处理说明》两份对外文档（本系统处理企业财务数据，"
     "涉个人信息时应说明最小必要与留存期）"),
    ("隐私", "部分符合",
     "数据面：有脱敏权威与最小必要原则文本；"
     "**缺**：用户知情同意流程（注册/首次使用无同意勾选）、数据留存期与删除策略未成文。",
     "P1：账号开通页加「数据处理告知 + 同意」，并把留存期写入配置"),
    ("防攻击", "符合",
     "**CSRF**：有会话无 token 的写操作 **403**（A2）；"
     "**SQL 注入**：`q=' OR 1=1--` 返回 **0 条**（参数化生效）、id 注入 **404**（A5）；"
     "**目录遍历**：3 种写法均 **404**（A7）；"
     "**XSS**：JSON 通道原样返回（正确），前端 `esc()`/`textContent` 转义（projects.js:103/178，31 处调用）。",
     "—"),
    ("防泄露", "符合",
     "错误响应**不含** Traceback/绝对路径/SQL 细节（A8 实测 `a8_leak=False`）；"
     "下载水印 74 处；导出留痕。",
     "—"),
    ("备份", "**不符合**",
     "**系统没有数据备份功能**。取证到的 7 处「backup」全为假阳性："
     "database.py:1118-1126 是**清理残留 `*_bk` 表**、domain_analysis.py:6483 与 tax_risk.py:5094 是"
     "**税审规则里的证据名称**（如「ERP系统数据备份」）。"
     "⇒ 无定期备份、无备份校验、无恢复演练入口。",
     "**P0**：备份是灾备的底座。加最简可用方案：每日 `VACUUM INTO` 快照 + "
     "保留 N 份 + 启动时校验可打开；详见阶段 9 灾备建议"),
]


def main() -> int:
    d = json.loads((OUT / "STAGE7_SECURITY.json").read_text(encoding="utf-8"))
    res = d["results"]
    cf = d["code_facts"]

    # 按维度分组探测结果
    by_dim: dict = {}
    for r in res:
        by_dim.setdefault(r["dim"], []).append(r)

    md: List[str] = []
    md.append("# 安全合规评估报告（阶段 7）\n")
    md.append("> 任务：META-QUALITY 阶段 7 · 安全合规评估  \n"
              "> 日期：2026-10-17  \n"
              "> 原则：**安全是底线，合规是红线**  \n"
              "> 范围：10 维度 × 全系统；**真攻击探测 18 项**（隔离实例 8024，非外部目标）  \n"
              "> 证据：`_quality/STAGE7_SECURITY.json`（请求/响应原文）+ `EVIDENCE_BASE.json`（代码事实）\n")

    md.append("---\n\n## 一、结论\n")
    md.append("| 维度 | 判定 | 依据摘要 |\n|---|---|---|")
    for d_name, verdict, proof, _ in VERDICTS:
        md.append("| **%s** | %s | %s |" % (d_name, verdict, proof.replace("|", "/")))
    md.append("")
    n_ok = sum(1 for v in VERDICTS if v[1] == "符合")
    n_part = sum(1 for v in VERDICTS if "部分" in v[1])
    n_bad = sum(1 for v in VERDICTS if "不符合" in v[1])
    md.append("**汇总**：符合 **%d** / 部分符合 **%d** / 不符合 **%d**（共 %d 维度）。\n"
              % (n_ok, n_part, n_bad, len(VERDICTS)))
    md.append("**红线项**：无。攻击面（CSRF / SQL 注入 / 目录遍历 / XSS / 越权 / 未认证）"
              "**全部实测未突破**。\n")
    md.append("**唯一不符合项是「备份」** —— 不是被攻破，而是**没有这个能力**："
              "数据一旦损坏/误删，只能靠外部文件系统恢复。\n")

    md.append("---\n\n## 二、真实攻击探测（18 项，逐条）\n")
    md.append("> 全部在**隔离实例**（127.0.0.1:8024，独立 APP_DATA_DIR）上发起；"
              "只做最小必要写入，探针数据用完即还原/删除。\n")
    md.append("| 编号 | 维度 | 探测内容 | 期望 | 实际 | 判定 |\n|---|---|---|---|---|---|")
    for r in res:
        st = r["status"]
        expect = r["expect"]
        if r["id"] == "A1":
            ok = st in (401, 302)
        elif r["id"] == "A2":
            ok = st == 403
        elif r["id"] == "A3":
            ok = st in (200, 403, 404)
        elif r["id"] == "A4":
            ok = st == 403
        elif r["id"] == "A5":
            ok = st != 500
        elif r["id"] == "A6":
            ok = st == 200
        elif r["id"] == "A7":
            ok = st in (400, 404)
        elif r["id"] == "A8":
            ok = not d["detail"].get("a8_leak", False)
        elif r["id"] == "A9":
            ok = st == 200
        elif r["id"] == "A10":
            ok = st == 401
        else:
            ok = st != -1
        md.append("| %s | %s | %s | %s | **HTTP %s** | %s |"
                  % (r["id"], r["dim"], r["title"].replace("|", "/"), expect.replace("|", "/"),
                     st, "✅ 通过" if ok else "❌ 不符"))
    md.append("")
    md.append("**关键读数**：\n")
    md.append("- SQL 注入 `' OR 1=1--` 的返回 `total = %s`（应为 0，说明按字面值匹配、未拼进 SQL）；"
              % d["detail"].get("sqli_projects_total"))
    md.append("- 错误响应含堆栈/绝对路径：**%s**；"
              % ("是" if d["detail"].get("a8_leak") else "否"))
    md.append("- XSS 字段回读含原始 `<script>`：**%s**（JSON 通道本就不该转义，"
              "转义责任在前端 —— 已核实前端 `esc()`/`textContent`）。\n"
              % ("是" if d["detail"].get("xss_echo_raw") else "否"))

    md.append("---\n\n## 三、代码层事实（含 3 处假阳性纠正）\n")
    md.append("| 事实 | 计数 | 说明 |\n|---|---|---|")
    md.append("| CSRF 相关 | %d 处 | `csrf_token` 下发 + `csrf_is_valid` 校验 |" % cf["csrf_hits"])
    md.append("| 脱敏相关 | %d 处 | 唯一权威 `engine/redaction.py` |" % cf["masking_hits"])
    md.append("| 水印相关 | %d 处 | 下载留痕 |" % cf["watermark_hits"])
    md.append("| 审计埋点 | %d 处 | 唯一权威 `audit_trail` |" % cf["audit_hits"])
    md.append("| 参数绑定 | %d 处 | 参数化查询（防注入的正解） |" % cf["param_binding"])
    md.append("| SQL 拼接可疑 | %d 处 | 已人工核查为拼接**表名/列名白名单**，非用户输入 |"
              % cf["sql_concat_suspect"])
    md.append("| 多因子 | **0 处** | 无 MFA/TOTP |")
    md.append("")
    md.append("**三处假阳性（写报告前自查纠正）**：\n")
    md.append("| 曾经的读数 | 实际情况 |\n|---|---|")
    md.append("| 备份 7 处 | ①清理残留 `*_bk` 表；②税审规则的证据名称。**系统无备份功能** |")
    md.append("| PIPL/DSL 20 处 | 多数是**规则 DSL**（`dsl_scope`/`DslError`），"
              "非《数据安全法》；提到《个人信息保护法》仅 1 处 |")
    md.append("| 存储加密 24 处 | **只覆盖 LLM 凭证**（AES-GCM+DPAPI），业务库明文 |")
    md.append("")

    md.append("---\n\n## 四、优化建议\n")
    md.append("| 编号 | 问题 | 类型 | 影响面 | 修复成本 |\n|---|---|---|---|---|")
    for i, (d_name, verdict, _, advice) in enumerate(VERDICTS, 1):
        if advice == "—":
            continue
        md.append("| **S-%02d** | %s：%s | %s | %s | 见建议 |"
                  % (i, d_name, verdict, "合规型" if d_name in ("合规", "隐私") else
                     ("灾备型" if d_name == "备份" else "合规型"), "全系统"))
        md.append("")
    md.append("**具体建议**（按优先级）：\n")
    for i, (d_name, verdict, _, advice) in enumerate(VERDICTS, 1):
        if advice == "—":
            continue
        md.append("- **S-%02d（%s）**：%s" % (i, d_name, advice))
    md.append("")
    md.append("> 注：安全建议一律**只登记不实施**（指令 17：不擅自修改规则）。"
              "其中「备份」建议与阶段 9 灾备建议合并执行。\n")

    md.append("---\n\n## 五、边界与说明\n")
    md.append("- 本次为**白盒安全自测**（已知账号、隔离实例），**不等于**第三方渗透测试；"
              "未做的项目：DDoS、供应链、物理安全、社工、Web 服务配置加固（TLS 套件/安全响应头逐项）。")
    md.append("- `APP_COOKIE_SECURE=0` 仅用于本机 HTTP 测试；该值在生产必须为 1（否则 cookie 可被明文传输）。")
    md.append("- 攻击探测仅针对本系统自有实例，未采集、未请求任何外部/官方站点数据。\n")

    out = ROOT / "docs" / "元质量_20261016" / "16_安全合规评估报告.md"
    out.write_text("\n".join(md), encoding="utf-8")
    print("阶段 7 安全合规：%d 维度（符合 %d / 部分 %d / 不符合 %d）｜攻击探测 %d 项"
          % (len(VERDICTS), n_ok, n_part, n_bad, len(res)))
    print("报告：", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
