# -*- coding: utf-8 -*-
"""阶段 5：冗余检测（2026-10-17）。

检测范围（指令原文 7.1）：模块 / 功能 / 数据 / 规则，两两对比。
分类（指令原文 7.2）：完全重复 / 部分重叠 / 视角互补 / 伪冗余。

纪律：本阶段判定全部经过查证（不是名字像就算重复）。
每条都在「查证依据」里写明凭什么这么判，并给 file:line。
本轮共 6 处曾被误判，已在报告§三逐条记录并纠正。

写法约定：本文件内所有中文引用一律用「」，不使用英文双引号包中文
（曾因字符串内嵌英文双引号导致语法错误，重写时统一规避）。
"""
from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "元质量_20261016" / "_quality"

ITEMS: List[Dict[str, Any]] = [
    dict(
        id="R-01", kind="部分重叠", category="数据之间（表）",
        modules="database.py / engine/audit_trail.py",
        tables="audit_logs", apis="—", rules="—",
        overlap="字段 100%（7 列完全一致）；audit_trail.py 额外 ALTER TABLE 加 user_id",
        proof="database.py:2057 与 engine/audit_trail.py:189 两处 CREATE TABLE IF NOT EXISTS audit_logs，"
              "列定义逐字相同；audit_trail.py:199-202 另加 user_id 列",
        verdict="真冗余（部分重叠）：同一张表由两个模块各自建。当前无害（IF NOT EXISTS 幂等），"
                "但建表口径分裂 —— 将来只在一边加列，另一环境的表结构就会不一致。",
        action="收敛到 engine/audit_trail.py（它更完整），database.py 删掉建表；"
               "或反过来只留 database.py。不建议保留两处。",
    ),
    dict(
        id="R-02", kind="完全重复", category="功能之间（代码）",
        modules="analysis_api / documents_api / extract_api / projects_api / risks_api 等 9 个 API 文件",
        tables="—", apis="—", rules="—",
        overlap="_session 逻辑约 100%、_call 异常转 HTTP 约 90%、_require_perm 约 100%",
        proof="9 个文件分别定义 _session / _call / _require_perm（取证 dup_function_names 中 "
              "_session x9、_call x7、_require_perm x7），实现均委托同一权威（rbac/session）",
        verdict="真冗余（完全重复）：同一段样板代码复制 7~9 份。风险不是多几行代码，"
                "而是改一处忘一处导致权限校验口径漂移 —— 这正是阶段 2 权限缺口反复复发的机制。",
        action="抽 api_common.py（_session / _call / _require_perm / _request_perm），"
               "9 个文件改为 import。判据：dup_function_names 里这 4 个名字应降到 1 处。",
    ),
    dict(
        id="R-03", kind="部分重叠", category="接口之间（新旧并存）",
        modules="main.py（旧 /api）对 各 *api.py（/api/v1）",
        tables="—", apis="159 条旧 /api 对 119 条 /api/v1", rules="—",
        overlap="架构级：289 条路由中 159 条（55%）是旧版，与 v1 并存；"
                "其中 12 条末段资源名与 v1 同名（疑似同功能）",
        proof="取证 routes_list：v1 119 + 旧 /api 159 + 非 /api 11 = 289。"
              "抽样 3 条查证：① /api/audit-logs（main.py:13714）对 /api/v1/audit-logs"
              "（rbac_api.py:203，标注「组织隔离 + 脱敏」），同功能且 v1 更安全；"
              "② /api/auth/change-password（main.py:15237）对 v1 change-password；"
              "③ /api/tax-risk-docs/review（main.py:7666）对 v1 review",
        verdict="真冗余（部分重叠）：同一能力两个入口，且旧入口安全等级更低"
                "（无组织隔离、无脱敏）。这是阶段 2「71 个旧路由权限缺口」的同源问题。",
        action="不删除功能（红线）：① 旧路由全部登记进 security_web._LEGACY_WRITE_PERMS（已做）；"
               "② 前端停止调用旧路由（新页面已走 v1）；③ 旧路由加 Deprecation 响应头标注迁移目标；"
               "④ 待外部调用方为 0 后再议下线。",
    ),
    dict(
        id="R-04", kind="伪冗余", category="数据之间（表）",
        modules="engine/extract_store.py 对 database.py",
        tables="invoices 对 sales_invoices / purchase_invoices", apis="—", rules="—",
        overlap="字段约 40% 重叠（invoice_no/amount/tax/total 等）",
        proof="extract_store.py:136 的 invoices 为 14 列扁平表（含 direction）；"
              "database.py:522 的 sales_invoices 为业务完整表（含 invoice_code/digital_invoice_no/"
              "seller_tax_no 等）。且 extract_store.py:142 明确 "
              "BUILD_OPTIONAL_TABLES = False（默认不建，沿用现有同义表）",
        verdict="伪冗余：invoices 表默认根本不创建，作者已显式声明沿用同义表。"
                "代码上留着定义、数据上不产生重复。",
        action="保留。建议在定义处补一句「何时才置 True」的触发条件，避免后人误开导致双写。",
    ),
    dict(
        id="R-05", kind="伪冗余", category="功能之间（工具函数）",
        modules="engine/fieldkit.py / gap_risk_detectors.py / chapter_dedup.py / constituent_threshold.py",
        tables="—", apis="—", rules="—",
        overlap="同名 _num(x8) / _norm(x9) / _fmt(x5) 分散定义",
        proof="抽查：gap_risk_detectors._num(L390) 与 fieldkit._num(L386) 均 "
              "from engine.numparse import to_number（薄包装，未绕过权威）；"
              "chapter_dedup._norm(L43) 是长度保持归一化、constituent_threshold._fmt(L155) "
              "是千分位格式化，语义各不相同",
        verdict="伪冗余：看似重复，实为①统一权威的薄包装（合规），②语义各异的局部工具（合理）。"
                "不是缺陷，反而是单一权威的正确用法。",
        action="保留。不做统一 —— 强行合并反而会破坏各自语义（如 length-preserving 归一化）。",
    ),
    dict(
        id="R-06", kind="视角互补", category="模块之间",
        modules="engine/legal_*.py（11 个）",
        tables="—", apis="legal_api", rules="—",
        overlap="名字同含 legal，职责各不相同",
        proof="catalog（目录元数据）/ citation（引用解析）/ coverage（覆盖率）/ extras（扩展）/ "
              "library（正文库）/ mapping（映射）/ reasoner（推理）/ version（版本），"
              "项目长期记忆中已登记各自为单一权威",
        verdict="视角互补：从不同层（元数据/正文/引用/覆盖率/推理）处理法规，各自不可替代。",
        action="保留，并在文档中明确各自边界（部分已写在模块 docstring）。",
    ),
    dict(
        id="R-07", kind="视角互补", category="模块之间",
        modules="engine/report_*.py（19 个）",
        tables="reports / report_versions", apis="reports_api", rules="—",
        overlap="名字同含 report，职责分层",
        proof="compliance（合规声明）/ layout（章节布局）/ metrics（取数）/ payload（载荷）/ "
              "pipeline（流水线）/ dedup（去重）/ identity（标识）/ service（服务），"
              "项目长期记忆中已登记 report_compliance / report_metrics 等为单一权威",
        verdict="视角互补：报告生成链的不同环节，缺一不可。",
        action="保留。",
    ),
    dict(
        id="R-08", kind="无冗余", category="规则之间",
        modules="config/risk_conditions.json",
        tables="—", apis="—", rules="130 条风险规则",
        overlap="0",
        proof="130 条规则：risk_code 无重复、name 无重复、"
              "trigger_conditions 无完全相同的组、determination_criteria 无完全相同的组",
        verdict="无冗余",
        action="—",
    ),
    dict(
        id="R-09", kind="无冗余", category="接口之间",
        modules="全部 289 条路由",
        tables="—", apis="289", rules="—",
        overlap="0（同 method + path 重复注册 = 0）",
        proof="取证 dup_route_paths 为空。"
              "（注：第一版曾报 /api/agi/report/export 重复，经查是注释里的说明文字被误计，已修）",
        verdict="无冗余（无重复注册）",
        action="—",
    ),
    dict(
        id="R-10", kind="可接受", category="工具之间",
        modules="根目录 62 个 _verify_*.py",
        tables="—", apis="—", rules="—",
        overlap="_load_gate x5、_md5 x5 等小工具在各验证脚本里重复",
        proof="取证 dup_function_names：_load_gate / _md5 / main 等在多个 _verify_* 脚本出现",
        verdict="可接受：一次性验证脚本，各自独立可运行是优点（不引入相互依赖）。"
                "且它们不参与产品运行（product_files 已排除 19 个工具文件）。",
        action="不处理。可考虑归档到 scripts/verify/ 以减少根目录噪音。",
    ),
]

FALSE_ALARMS = [
    ("/api/agi/report/export 重复注册",
     "取证器未抹注释，把 main.py 说明「原装饰器误挂在这里」的注释当成真实注册",
     "修取证器：路由扫描改用抹注释文本，重复路由 = 0"),
    ("130 条风险规则条件完全相同",
     "比较时取错字段（expression / field），实际是 risk_code / trigger_conditions，"
     "导致签名全空、误判全重复",
     "改按真实字段比较，0 组重复"),
    ("_num 在 8 个模块重复，疑似绕过数值权威",
     "只看函数名就下判断；实际 from engine.numparse import to_number（薄包装）",
     "抽查实现后改判伪冗余"),
    ("_norm 在 9 个模块重复，疑似归一化口径分裂",
     "chapter_dedup._norm 是长度保持归一化，与一般归一化语义不同",
     "改判伪冗余（语义各异）"),
    ("invoices 与 sales_invoices 表字段重叠，疑似双写风险",
     "未看 BUILD_OPTIONAL_TABLES = False：invoices 默认不建",
     "改判伪冗余（预留未启用）"),
    ("legal_* 11 个模块名字太像，疑似模块重复",
     "未读职责就下判断；实际分属目录/正文/引用/覆盖率/推理等不同层",
     "改判视角互补"),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    kinds: Dict[str, int] = {}
    for it in ITEMS:
        kinds[it["kind"]] = kinds.get(it["kind"], 0) + 1
    data = {
        "generated_at": __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"),
        "items": ITEMS, "by_kind": kinds, "false_alarms": len(FALSE_ALARMS),
    }
    (OUT / "STAGE5_REDUNDANCY.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    md: List[str] = []
    md.append("# 冗余检测报告（阶段 5）\n")
    md.append("> 任务：META-QUALITY 阶段 5 · 冗余检测  \n"
              "> 日期：2026-10-17  \n"
              "> 范围：**模块 / 功能 / 表 / 字段 / 接口 / 规则 六类两两对比**  \n"
              "> 证据：`_quality/EVIDENCE_BASE.json`（全库 AST 取证）+ `_quality/STAGE5_REDUNDANCY.json`\n")
    md.append("---\n\n## 一、结论\n")
    md.append("| 分类 | 条数 |\n|---|---|")
    for k in ("完全重复", "部分重叠", "视角互补", "伪冗余", "无冗余", "可接受"):
        if kinds.get(k):
            md.append("| %s | %d |" % (k, kinds[k]))
    md.append("")
    md.append("**需要处理的真冗余 3 条**：R-01（同一张表两处建）、R-02（样板代码复制 7~9 份）、"
              "R-03（旧 /api 159 条与 v1 并存，且旧版安全等级更低）。\n")
    md.append("**判为伪冗余/视角互补的 4 条**（R-04~R-07）：看似重复、查证后不重复，"
              "强行合并会破坏语义或引入风险，明确建议保留。\n")

    md.append("---\n\n## 二、冗余清单\n")
    for it in ITEMS:
        md.append("### %s｜%s（%s）\n" % (it["id"], it["kind"], it["category"]))
        md.append("| 字段 | 内容 |\n|---|---|")
        md.append("| 涉及模块 | %s |" % it["modules"])
        md.append("| 涉及表 | %s |" % it["tables"])
        md.append("| 涉及接口 | %s |" % it["apis"])
        md.append("| 涉及规则 | %s |" % it["rules"])
        md.append("| 重叠程度 | %s |" % it["overlap"])
        md.append("| **查证依据** | %s |" % it["proof"].replace("|", "/"))
        md.append("| **判定** | %s |" % it["verdict"].replace("|", "/"))
        md.append("| **处理建议** | %s |" % it["action"].replace("|", "/"))
        md.append("")

    md.append("---\n\n## 三、被排除的假冗余（本轮自查）\n")
    md.append("> 本阶段共 **%d 处**判断错误，全部在写报告前自查纠正。"
              "记录在此是为了说明：**名字像、字段像都不等于重复**。\n" % len(FALSE_ALARMS))
    md.append("| # | 曾经的误判 | 为什么会误判 | 纠正 |\n|---|---|---|---|")
    for i, (a, b, c) in enumerate(FALSE_ALARMS, 1):
        md.append("| %d | %s | %s | %s |"
                  % (i, a.replace("|", "/"), b.replace("|", "/"), c.replace("|", "/")))
    md.append("")

    md.append("---\n\n## 四、处理原则\n")
    md.append("1. **不删除已有功能**（红线）：R-03 只做停止新调用与标注迁移，不摘除旧路由；\n")
    md.append("2. **真冗余优先收敛到一处，而不是两边都改**：R-01 收敛建表、R-02 抽公共模块；\n")
    md.append("3. **伪冗余必须写明为什么不重复**：否则下一轮又会被当成重复重新提一遍；\n")
    md.append("4. 本轮只登记与建议，不改代码（指令 17：不修改现有规则、不擅自优化）。\n")

    out = ROOT / "docs" / "元质量_20261016" / "14_冗余检测报告.md"
    out.write_text("\n".join(md), encoding="utf-8")

    print("阶段 5 冗余检测：%d 条（%s）｜假冗余纠正 %d 处"
          % (len(ITEMS), " ".join("%s=%d" % (k, v) for k, v in kinds.items()), len(FALSE_ALARMS)))
    print("报告：", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
