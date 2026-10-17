# -*- coding: utf-8 -*-
"""阶段 10 / 11 / 12：文档知识 + CI/CD + 伦理合规（2026-10-17）。

一次生成三份报告（三阶段评估口径不同，互不依赖，但共用同一份证据）。
"""
from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "元质量_20261016" / "_quality"
DOCS_DIR = ROOT / "docs"
MD_OUT = ROOT / "docs" / "元质量_20261016"

# ══════════════════════════════════════════════════════════════════════════
# 阶段 10：文档知识（9 类）
# ══════════════════════════════════════════════════════════════════════════
#: (类型, 判定, 是否有独立可执行文档, 问题)
DOC_VERDICTS = [
    ("需求文档", "部分完整",
     False,
     "有《需求规格与概要设计_V1.0.md》（docs/），但后续 12 个批次的增量需求散落在"
     "各批次报告里，**无统一的需求基线**（哪条需求已实现、哪条变更过，无法一处查全）。"),
    ("设计文档（架构）", "完整",
     True,
     "README + 《需求规格与概要设计》+ 各批次设计文档；模块职责多写在源码 docstring 里"
     "（如 legal_*/report_* 的分层）。可读、可追溯。"),
    ("设计文档（数据库）", "**不完整**",
     False,
     "**无独立表结构文档**。42+ 张表的字段与语义只能读 `database.py` / 各 `*_store.py` 的 "
     "`CREATE TABLE` 与 ORM 注释；无 ER 图、无字段字典。交接成本高。"),
    ("设计文档（接口）", "完整",
     True,
     "FastAPI 自带 OpenAPI（289 条路由自动生成 schema），`/docs` 与 `/redoc` 可用"
     "（**但被登录拦截，见下**）。"),
    ("API 文档", "部分可用",
     True,
     "**`/docs`、`/redoc`、`/openapi.json` 实测均 302 → 重定向到登录页**："
     "开发者拿到 schema 前必须先有账号。功能存在、可达性受限。"),
    ("部署文档", "**不完整**",
     False,
     "**无独立部署手册**（标题级检索 0 篇）。README 有首次启动 4 步 + 生产部署 6 条要点，"
     "质量不错；但**端口写错**：README 说 `http://127.0.0.1:8000`，实际 `start8001.bat` 是 "
     "`set PORT=8001` ⇒ **照 README 操作会访问失败**。"),
    ("运维文档", "**缺失**",
     False,
     "**无运维手册**：日志在哪（`data/logs/`）、常见故障怎么判（如 `readonly database`、"
     "端口未监听）、巡检做什么，都没有成文。本轮遇到的多个运维问题只能靠现场排查。"),
    ("用户手册", "**缺失**",
     False,
     "**无面向最终用户的操作手册**。用户只能靠自己摸索界面；"
     "阶段 4 的「可学习性」评分偏低（3.79）与这里互为因果。"),
    ("测试文档", "完整",
     True,
     "`tests/` 内 2000+ 用例（本轮全量跑 2209 passed）；"
     "`docs/` 下有失败样例、回归报告、反向验证记录。可复跑、可追溯。"),
    ("变更日志", "**不完整**",
     False,
     "**无连续 CHANGELOG**（`CHANGELOG.md` 不存在）。变更有记录，但形式是"
     "**按批次/按专项的报告**（如“第01批…”“元质量…报告”），不是按版本累计的变更流。"),
    ("知识库（FAQ/最佳实践）", "部分完整",
     True,
     "有大量**开发侧**知识（MEMORY.md、各类基线文档、裁决记录）；"
     "**无用户侧 FAQ**。开发者能查，使用者查不到。"),
]


def stage10() -> pathlib.Path:
    d = json.loads((OUT / "EVIDENCE_BASE.json").read_text(encoding="utf-8"))
    doc = d["docs"]
    n_ok = sum(1 for v in DOC_VERDICTS if v[1] == "完整" or v[1] == "部分可用")
    n_part = sum(1 for v in DOC_VERDICTS if "部分" in v[1])
    n_bad = sum(1 for v in DOC_VERDICTS if "缺失" in v[1] or "不完整" in v[1])

    md: List[str] = []
    md.append("# 文档知识评估报告（阶段 10）\n")
    md.append("> 任务：META-QUALITY 阶段 10 · 文档知识评估  \n"
              "> 日期：2026-10-17  \n"
              "> 原则：**没有文档的系统，等于没有系统**  \n"
              "> 范围：9 类文档（指令 12.2）× 完整性 / 时效性 / 可读性  \n"
              "> 证据：全库 471 篇 Markdown（%d 行）逐篇扫描 + `/docs` 端点实测\n" % doc["total_lines"])

    md.append("---\n\n## 一、结论\n")
    md.append("| 文档类型 | 是否完整 | 有独立可执行文档 | 问题 |\n|---|---|---|---|")
    for name, verdict, standalone, prob in DOC_VERDICTS:
        md.append("| **%s** | %s | %s | %s |"
                  % (name, verdict, "是" if standalone else "**否**", prob.replace("|", "/")))
    md.append("")
    md.append("**汇总**：完整/可用 **%d** · 部分 **%d** · 不完整或缺失 **%d**（共 %d 类）。\n"
              % (n_ok, n_part, n_bad, len(DOC_VERDICTS)))
    md.append("**一句话**：**开发者侧文档很厚（471 篇 / 6.7 万行），"
              "但「运维、部署、用户」这三类面向“非开发者”的文档全缺** —— "
              "系统换个人接手或交给客户，前 30 分钟就会卡住。\n")

    md.append("---\n\n## 二、逐类明细\n")
    for i, (name, verdict, standalone, prob) in enumerate(DOC_VERDICTS, 1):
        md.append("### %d. %s —— %s\n" % (i, name, verdict))
        md.append("- **有独立可执行文档**：%s" % ("是" if standalone else "否"))
        md.append("- **问题**：%s\n" % prob)

    md.append("---\n\n## 三、可验证的具体缺陷（不是“感觉不够”）\n")
    md.append("| # | 缺陷 | 验证方式 | 后果 |\n|---|---|---|---|")
    md.append("| 1 | README 写 `127.0.0.1:8000`，实际 `set PORT=8001` | "
              "`grep PORT start8001.bat` vs `grep 127.0.0.1 README.md` | 照 README 部署**访问失败** |")
    md.append("| 2 | `/docs` `/redoc` `/openapi.json` 全部 302 | 实测三个端点 | "
              "外部开发者**拿不到接口 schema** |")
    md.append("| 3 | 无 `CHANGELOG.md` | 全仓检索 | 无法回答「当前版本比上版改了什么」 |")
    md.append("| 4 | 无表结构文档 / ER 图 | 按标题检索 0 篇 | 新人只能读 `CREATE TABLE` 反推 |")
    md.append("| 5 | 无运维手册 | 按标题检索 0 篇 | "
              "`readonly database`、端口未监听这类故障只能现场摸索 |")
    md.append("| 6 | 无用户手册 | 按标题检索 0 篇 | 用户学习成本高（呼应阶段 4「可学习性 3.79」） |")
    md.append("")

    md.append("---\n\n## 四、优化建议\n")
    md.append("| 编号 | 问题 | 类型 | 影响面 | 修复成本 |\n|---|---|---|---|---|")
    md.append("| **DOC-01** | **修 README 端口**（8000 → 8001） | 文档型 | 所有新部署者 | "
              "**极低**：改 1 个数字 |")
    md.append("| **DOC-02** | **补《运维手册》**：日志位置、"
              "5 个高频故障（readonly/端口未监听/任务卡住/解析失败/磁盘满）的判定与处置、巡检清单 | 文档型 | 运维 | "
              "**低**：本轮已积累大量真实故障与处置，整理即成 |")
    md.append("| **DOC-03** | **补《部署手册》**：把 README 的 4 步 + 生产 6 条扩成可执行清单"
              "（含反向代理、开机自启、备份调度） | 文档型 | 部署 | **低** |")
    md.append("| **DOC-04** | **补《用户手册》**：按 21 个模块各 1 页（做什么 / 怎么点 / 看到什么算成功） | 文档型 | 全部用户 | "
              "**中**：阶段 3+4 的评估已产出素材，可直接改写成手册 |")
    md.append("| **DOC-05** | **建 `CHANGELOG.md`**：按版本累计（可从现有批次报告回溯） | 文档型 | 交付/验收 | "
              "**低** |")
    md.append("| **DOC-06** | **补表结构文档 + ER 图**（42 张表） | 文档型 | 交接/维护 | "
              "**中**：可从 `database.py` 自动生成字段清单 |")
    md.append("| **DOC-07** | **API 文档可达性**：`/docs` 允许「登录后访问」或提供离线 `openapi.json` 交付 | 文档型 | 集成方 | "
              "**低**：新增一个需登录的下载端点即可 |")
    md.append("")

    md.append("---\n\n## 五、判定口径\n")
    md.append("| 判定 | 含义 |\n|---|---|")
    md.append("| 完整 | 有独立、可执行、与实现一致的文档 |")
    md.append("| 部分可用 | 有文档但可达性受限（如被鉴权拦住） |")
    md.append("| 部分完整 | 有内容但散落多处、无统一基线 |")
    md.append("| 不完整 | 有零散提及，但**照它做不成事** |")
    md.append("| 缺失 | 按标题与内容双重检索均无 |")
    md.append("")
    md.append("> ⚠ 本阶段的判定**不按文件名**，而是「**照它能不能做成事**」。"
              "例如「部署」二字在 23 篇文档里出现，但都不是可执行手册 —— 那不算有部署文档。\n")

    p = MD_OUT / "19_文档知识评估报告.md"
    p.write_text("\n".join(md), encoding="utf-8")
    return p


# ══════════════════════════════════════════════════════════════════════════
# 阶段 11：CI/CD（8 环节）
# ══════════════════════════════════════════════════════════════════════════
CICD_VERDICTS = [
    ("持续集成", "无", False,
     "**无 CI 配置**（`.github/`、`.gitlab-ci.yml`、`Jenkinsfile` 全部不存在）。"
     "提交代码不会自动构建。"),
    ("持续测试", "无（有手动脚本）", False,
     "无自动化测试流水线；但有 **62 个 `_verify_*.py` 脚本 + 2209 条 pytest 用例**，"
     "可手动一键跑。能力有、自动化没有。"),
    ("持续部署", "无", False,
     "部署方式：手动双击 `start8001.bat`（或 `start.sh`）。"),
    ("蓝绿部署", "无", False, "单实例单端口，无蓝绿。"),
    ("灰度发布", "无", False, "无流量切分能力。"),
    ("回滚", "部分", False,
     "**代码**可回滚（git 有完整历史，本轮已用 `git checkout` 恢复过文件）；"
     "**数据**无版本化（DB 无迁移框架，回滚代码不保证兼容旧表结构）。"),
    ("版本管理", "部分", False,
     "git 提交历史完整（本轮新增 4 次提交）；但 **0 个 tag**，无版本号体系 ⇒ "
     "「当前是哪个版本」只能靠 commit hash。报告里有 `V81/V84` 等版本号，但那是**报告版本**不是**系统版本**。"),
    ("环境管理", "部分", True,
     "有 `APP_DATA_DIR` 环境变量隔离（本轮所有测试都用独立目录，**机制有效**）；"
     "但无「开发/测试/生产」三套配置文件的约定，也没有环境标识。"),
]


def stage11() -> pathlib.Path:
    d = json.loads((OUT / "EVIDENCE_BASE.json").read_text(encoding="utf-8"))
    ci = d["cicd"]
    n_ok = sum(1 for v in CICD_VERDICTS if v[1] == "有")
    n_part = sum(1 for v in CICD_VERDICTS if "部分" in v[1] or "有手动" in v[1])
    n_bad = sum(1 for v in CICD_VERDICTS if v[1] == "无")

    md: List[str] = []
    md.append("# CI/CD 评估报告（阶段 11）\n")
    md.append("> 任务：META-QUALITY 阶段 11 · CI/CD 评估  \n"
              "> 日期：2026-10-17  \n"
              "> 原则：**自动化构建、测试、部署、回滚**  \n"
              "> 证据：仓库结构检索 + git 状态 + `.git/hooks` 检查 + 脚本清单\n")

    md.append("---\n\n## 一、结论\n")
    md.append("| 环节 | 是否自动化 | 是否可靠 | 是否可追溯 | 问题 |\n|---|---|---|---|---|")
    for name, auto, _sa, prob in CICD_VERDICTS:
        reliable = "是" if auto in ("有", "部分") else "否"
        trace = ("是" if name in ("版本管理", "回滚", "环境管理") else "—")
        md.append("| **%s** | %s | %s | %s | %s |"
                  % (name, auto, reliable, trace, prob.replace("|", "/")))
    md.append("")
    md.append("**汇总**：自动化 **%d** · 部分 **%d** · 无 **%d**（共 %d 环节）。\n"
              % (n_ok, n_part, n_bad, len(CICD_VERDICTS)))
    md.append("**一句话**：**这是一套「手工交付」的系统** —— 没有 CI、没有 CD、没有灰度、没有版本号，"
              "但有**很厚的自检脚本**（62 个）与**完整 git 历史**。"
              "换句话说：**质量意识在，工程化基础设施不在**。\n")

    md.append("---\n\n## 二、实测事实\n")
    md.append("| 项 | 实测 |\n|---|---|")
    md.append("| CI 配置文件 | **0 个**（`.github`/`.gitlab-ci.yml`/`Jenkinsfile`/`.travis.yml`/`azure-pipelines.yml` 均无） |")
    _hooks = ROOT / ".git" / "hooks"
    _samples = len(list(_hooks.glob("*.sample"))) if _hooks.is_dir() else 0
    md.append("| 自定义 git hooks | **%d 个**（仅有 %d 个未启用的 `*.sample`） |"
              % (len(ci["custom_git_hooks"]), _samples))
    md.append("| git tag | **%d 个** |" % len(ci["git_tags"]))
    md.append("| 分支 | %s |" % (ci["git_branches"] or "无"))
    md.append("| 最近提交 | %s |" % (" / ".join(ci["recent_commits"][:3]) or "—"))
    md.append("| 自检脚本 `scripts/*verify*` | **%d 个** |" % len(ci["scripts_verify"]))
    md.append("| 审计工具 `tools/*.py` | **%d 个** |" % len(ci["tools_audit"]))
    md.append("| 启动脚本 | %s |" % (", ".join(ci["start_scripts"]) or "—"))
    md.append("")

    md.append("---\n\n## 三、优化建议\n")
    md.append("| 编号 | 问题 | 类型 | 影响面 | 修复成本 |\n|---|---|---|---|---|")
    md.append("| **CI-01** | **无版本号**：0 个 tag，「当前什么版本」说不清 | 文档型 | 交付/验收 | "
              "**极低**：`git tag v1.0.0`（当前状态打第一个基线），之后每次交付打 tag |")
    md.append("| **CI-02** | **无自动测试流水线**：2209 条用例靠人记得跑 | 效率型 | 代码质量 | "
              "**低**：加 `.github/workflows/ci.yml`（或本地 `pre-push` hook）跑 "
              "`pytest -q` + `tools/audit_consistency.py` + `tools/verify_release.py` 三道 |")
    md.append("| **CI-03** | **无 CHANGELOG 与版本号联动** | 文档型 | 交付 | "
              "**低**：与 DOC-05 合并做 |")
    md.append("| **CI-04** | **回滚只回代码不回数据**：DB 无迁移框架 | 灾备型 | 升级/回滚 | "
              "**中**：加轻量迁移记录表（`schema_version` + 每次 DDL 登记），"
              "回滚前检查兼容性 |")
    md.append("| **CI-05** | 无环境标识（开发/测试/生产共用一份代码无标识） | 效率型 | 运维 | "
              "**低**：加 `APP_ENV` 并在启动日志与页脚显示 |")
    md.append("")
    md.append("> 建议先做 **CI-01 + CI-02**（合计半天工作量），"
              "投入产出比最高：版本可说清、回归可自动。\n")

    md.append("---\n\n## 四、边界\n")
    md.append("- 本阶段**不要求**系统具备云原生 CI/CD（当前是单机内部系统，"
              "强行上灰度/蓝绿无收益）；判定按「**有没有把已有能力自动化**」而非「是否先进」。\n")
    md.append("- 未评估：构建产物体积、依赖锁定完整度（`requirements.lock` 存在）、供应链安全扫描。\n")

    p = MD_OUT / "20_CICD评估报告.md"
    p.write_text("\n".join(md), encoding="utf-8")
    return p


# ══════════════════════════════════════════════════════════════════════════
# 阶段 12：伦理合规（8 维度）
# ══════════════════════════════════════════════════════════════════════════
ETHICS_VERDICTS = [
    ("可解释性", "符合",
     "每条风险都带「依据」：`engine/legal_citation.py`（法条引用）+ `evidence_chain.py`（证据链）+ "
     "`determination_criteria`（认定要件）。**风险等级不因复核而改动**（复核只改处置状态），"
     "避免「人说了算」。"),
    ("可审计性", "符合",
     "240 处审计埋点 + `audit_trail` 唯一权威 + `user_id` 可追溯改名/重名；"
     "报告的复核标识由**处置记录推断**（不靠手填）。"),
    ("无偏见", "**部分符合**",
     "无「按企业规模/地区/行业差别对待」的规则（规则按事实条件判定，不按主体属性）；"
     "但**未做偏见测试**（如同一事实、不同行业名，结论是否一致）。"
     "代码内偏见/公平相关守卫仅 6 处，且多为文本。"),
    ("人工复核", "符合",
     "5 态复核状态机 + `review_expert` 独立复核岗（不导出报告）+ 批量复核上限（`BULK_LIMIT`）+ "
     "「转人工」动作（不改状态、只打标记）。"),
    ("免责声明", "符合",
     "报告内「（见报告性质和使用说明）」+ 页脚性质说明；`output_variants` 有内部/对外版差异"
     "（对外版剔除内部字段，**但保留主体与金额**——按用户铁律不脱敏主体）。"),
    ("数据合规", "**部分符合**",
     "数据来源为**企业自有财务资料**与公开法规；法规正文经官方源入库且带 provenance；"
     "**但**：无正式《数据处理说明》，用户也不被显式告知数据用途。"),
    ("用户知情", "**不符合**",
     "**无知情同意流程**：账号由管理员开通、用户直接使用，"
     "未见「数据处理告知与同意」页面/勾选。"),
    ("隐私保护", "**部分符合**",
     "有脱敏权威（`engine/redaction.py`）与最小必要原则文本；"
     "**缺**：留存期限成文规定、用户删除请求的处理路径。"),
]


def stage12() -> pathlib.Path:
    d = json.loads((OUT / "EVIDENCE_BASE.json").read_text(encoding="utf-8"))
    e = d["ethics"]
    n_ok = sum(1 for v in ETHICS_VERDICTS if v[1] == "符合")
    n_part = sum(1 for v in ETHICS_VERDICTS if "部分" in v[1])
    n_bad = sum(1 for v in ETHICS_VERDICTS if v[1] == "不符合")

    md: List[str] = []
    md.append("# 伦理合规评估报告（阶段 12）\n")
    md.append("> 任务：META-QUALITY 阶段 12 · 伦理合规评估  \n"
              "> 日期：2026-10-17  \n"
              "> 原则：**系统决策必须可解释、可审计、无偏见**  \n"
              "> 证据：代码取证（免责 43 处 / 可解释 1020 处 / 人工复核 263 处 / "
              "偏见守卫 6 处 / 知情 6 处）+ 报告实读\n")

    md.append("---\n\n## 一、结论\n")
    md.append("| 维度 | 判定 | 依据 |\n|---|---|---|")
    for name, verdict, proof in ETHICS_VERDICTS:
        md.append("| **%s** | %s | %s |" % (name, verdict, proof.replace("|", "/")))
    md.append("")
    md.append("**汇总**：符合 **%d** · 部分符合 **%d** · 不符合 **%d**（共 %d 维度）。\n"
              % (n_ok, n_part, n_bad, len(ETHICS_VERDICTS)))
    md.append("**一句话**：**技术侧的伦理做得比制度侧好**。"
              "「可解释、可审计、可人工复核」这三项是本系统最扎实的部分（风险必有依据、决策必留痕、"
              "复核独立成岗）；但**「用户知情」完全缺失**、偏见从未被测试过 —— "
              "这两项是真正的合规风险点。\n")

    md.append("---\n\n## 二、逐维度明细\n")
    for i, (name, verdict, proof) in enumerate(ETHICS_VERDICTS, 1):
        md.append("### %d. %s —— %s\n" % (i, name, verdict))
        md.append("%s\n" % proof)

    md.append("---\n\n## 三、优化建议\n")
    md.append("| 编号 | 问题 | 类型 | 影响面 | 修复成本 |\n|---|---|---|---|---|")
    md.append("| **E-01** | **无知情同意**：账号开通后直接使用，未告知数据处理范围 | 伦理型 | 全部用户 | "
              "**低**：账号开通/首次登录加一页「数据处理告知 + 同意」（含用途、留存期、联系方式） |")
    md.append("| **E-02** | **偏见未测**：同一事实、不同行业/规模名称，结论是否一致从未验证 | 伦理型 | 风险判定 | "
              "**低**：造 10 组同事实不同主体名的样本，跑分析比对结论一致性 |")
    md.append("| **E-03** | **留存期与删除路径未成文** | 伦理型 | 数据治理 | "
              "**低**：写入配置（如「资料保留 3 年」）+ 运维手册写明删除流程 |")
    md.append("| **E-04** | 免责声明在报告内，但**登录页/首页无提示** | 伦理型 | 全部用户 | "
              "**极低**：页脚加一行「本系统输出为专业辅助意见，不构成正式鉴证结论」 |")
    md.append("")
    md.append("> E-01 是最该补的一条：它同时是《个人信息保护法》的**告知义务**要求，"
              "也是阶段 7「合规」维度判为部分符合的直接原因。\n")

    md.append("---\n\n## 四、边界\n")
    md.append("- 本阶段评估**系统输出的伦理属性**，不评估商业伦理、不评估采集环节（本系统不自采数据）。\n")
    md.append("- 「无偏见」判定为部分符合，是**因为没测过**，不是因为发现了偏见 —— "
              "两者要分清（未测 ≠ 有问题，但也 ≠ 没问题）。\n")

    p = MD_OUT / "21_伦理合规评估报告.md"
    p.write_text("\n".join(md), encoding="utf-8")
    return p


def main() -> int:
    p10 = stage10()
    p11 = stage11()
    p12 = stage12()
    data = {"stage10": [{"type": a, "verdict": b, "standalone": c, "problem": d}
                        for a, b, c, d in DOC_VERDICTS],
            "stage11": [{"stage": a, "auto": b, "standalone": c, "problem": d}
                        for a, b, c, d in CICD_VERDICTS],
            "stage12": [{"dim": a, "verdict": b, "proof": c} for a, b, c in ETHICS_VERDICTS]}
    (OUT / "STAGE10_11_12.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    for p in (p10, p11, p12):
        print("已生成：", p.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
