# 财税系统引擎 · 全面审计报告

- **审计对象**：`caishuixitong/engine/`（47 个模块）+ `engine/agents/`（4 个模块）+ 根级核心文件（main.py / tax_risk.py / database.py / file_parser.py 等）
- **审计目录**：`C:\Users\26726\WorkBuddy\2026-06-22-10-40-26`
- **审计时间**：2026-07-08
- **审计方法**：语法编译（py_compile）→ 逐模块导入完整性 → 全链路端到端运行（analyze_tax_risk_docs）→ 危险模式静态扫描（except:pass / 数据截断 / 行业特化硬编码 / 合并遗留）

---

## 一、结论摘要

审计发现引擎存在 **2 个 P0 级致命缺陷**（AGI 大脑整体无法导入，导致对话追问、报告 AGI 注入、`/api/agi/learn` 端点全部失效），已当场修复并验证。另有 1 个 P1、若干 P2 观察项。核心分析管线（域分析→规则→报告）本身健康，全链路可正常完成。

| 级别 | 数量 | 说明 | 状态 |
|------|------|------|------|
| P0 致命 | 2 | AGI 引擎导入炸弹（coordinator / agi_engine 合并遗留注解） | ✅ 已修复并验证 |
| P1 严重 | 1 | pipeline 静默吞掉 AGI 导入失败（掩盖 P0） | ✅ 已修复 |
| P1 合规 | 1 | knowledge_base 行业画像仅硬编码「纺织业」单一行业 | ⚠️ 待老邓决策 |
| P2 观察 | 4 | 孤立脚本语法错误 / 72 处 except:pass / AGI 增强覆盖上限 / 语义词典偏纺织 | 📋 已记录 |

---

## 二、P0 致命缺陷（已修复）

### P0-1　`engine/agents/coordinator.py` — 合并遗留导致导入即崩

**现象**：`import engine.agi_engine` 抛 `NameError: name 'DialogAgent' is not defined`（coordinator.py:26）。

**根因**：该文件由 `dialog.py / learning.py / rule_reasoner.py` 合并而来，`DialogAgent / LearningAgent / RuleReasonerAgent` 三个类被挪到文件**后半部**（128 / 624 / 781 行）定义，但顶部的 `AgentCoordinator` 类：
- 第 26/30/34 行用它们做**返回值类型注解**（`-> DialogAgent`）——类定义时立即求值 → NameError；
- 第 111 行 `coordinator = AgentCoordinator()` 在类定义前就实例化，`_init_agents()` 调用 `DialogAgent()` → 同样在定义前引用。

**修复**：
1. 文件头加 `from __future__ import annotations`（注解延迟求值）；
2. 将模块级 `coordinator = AgentCoordinator()` 与 `get_coordinator()` 移到文件**末尾**（全部类定义之后）。

### P0-2　`engine/agi_engine.py` — 同类合并遗留注解炸弹

**现象**：修复 P0-1 后暴露下一个 `NameError: name 'ReasoningResult' is not defined`（agi_engine.py:179）。

**根因**：`AGIEngine._inject_reasoning` 的形参注解 `reasoning: ReasoningResult`，而 `ReasoningResult` 类在同文件 519 行才定义（合并遗留，第 16 行 `# [merged] # ... ReasoningResult` 是被删掉的原 import）。

**修复**：文件头加 `from __future__ import annotations`。

### P0 影响面（修复前）

| 受影响功能 | 表现 |
|------------|------|
| `/api/agi/learn` 端点（main.py:7936） | 未包 try，直接 **HTTP 500** |
| 对话追问 `agi.ask()`（main.py:4957） | 被 try 兜底，AGI 深度回答静默失效 |
| 报告 AGI 注入 `_inject_agi_into_report`（main.py:6590） | 每次分析打印 NameError 堆栈，报告**缺失 AGI 推理章节** |
| 管线「合并大脑」增强（pipeline.py:3557） | 被 except:pass 静默吞掉，增强块从未执行 |

**验证**：修复后 47 个引擎模块 100% 可导入；`agi.ask()` 冒烟测试返回 10 个分析块；全链路 `analyze_tax_risk_docs(2)` 不再打印 NameError。

---

## 三、P1 问题

### P1-1　`engine/pipeline.py:208` — 静默吞错掩盖了 P0（已修复）

```python
try:
    from engine.agi_engine import agi as agi_engine_instance
    ...
except Exception: pass   # ← 把 P0 的导入失败彻底吞掉，管线永远拿不到 agi_engine
```
违反「try/except:pass 高危」铁律：agi_engine 导入失败被静默吞掉，`agi_engine` 恒为 None，「合并大脑」增强（3557 行 `if agi_engine:`）从未运行，且**无任何日志线索**。

**修复**：改为 `except Exception as _ae: pipeline_log.append(f"[AGI] 合并大脑接入失败→跳过推理增强: {_ae}")`。

### P1-2　`engine/knowledge_base.py` — 行业画像仅硬编码「纺织业」（待决策）

`DEFAULT_KNOWLEDGE["industry_profiles"]` 只有 `"纺织业"` 一个行业：
```python
"industry_profiles": {
    "纺织业": {"typical_risks": [...], "common_goods": ["坯布","棉纱","面料","染整加工费"], ...},
},
```
违反「全行业适用」铁律：当知识库 JSON 不存在（走默认）时，系统内置行业认知只覆盖纺织业，对制造/贸易/建筑/服务/软件等行业无默认画像，存在纺织行业偏向。

**建议**：此项涉及产品数据设计，未擅自改动。建议二选一——① 由 human_learning/self_learning 引擎数据驱动动态生成行业画像；② 补齐多行业默认画像。请老邓定夺方向后再落地。

---

## 四、P2 观察项

- **P2-1　`generate_report.py` 语法错误**：第 296 行未闭合三引号，`py_compile` 失败。但该文件**未被任何模块 import**（仅 `audit_commit_check.py` 作为文件路径引用、及一处 JS 说明字符串提及），属孤立/损坏脚本，不影响引擎运行。建议删除或修复归档。
- **P2-2　引擎内 72 处 `except:pass`**：多数为金额解析等良性兜底，但数据生成/AGI 增强路径（pipeline.py:3565/3573/3575/3584/3588 等）静默吞错，一旦出错无线索。建议关键数据生成处至少记 `pipeline_log`。
- **P2-3　AGI 增强覆盖上限**：pipeline.py 中 `all_findings[:20]`（不确定性量化）、`[:5]`（反事实推理）——第 21 条及以后的发现不获得 AGI 增强字段。若追求全量增强需评估性能后放开。
- **P2-4　`semantic_reasoner.py` 语义词典偏纺织**：`染色加工/棉纱/布料` 等纺织词较全，但同时含钢材/租金/水电等通用类目，整体多行业；建议后续补齐其他行业专属品名词条。
- **P2-5　`system_config` 规则数漂移（既存，非本次引擎改动引入）**：`audit.py 2` 第 8 项报 `system_config.rules_count=1608 ≠ tax_risk_rules_local_export.json 实际 1610`。系新增 2 条规则后未同步计数常量。属数据层配置漂移，低风险；因涉及规则数据（老邓归口），未擅自改动，建议同步计数或改为运行时动态读取。

---

## 五、正常项（通过）

- ✅ 47 个引擎模块 + 4 个 agents 模块 + main/tax_risk/database/file_parser 等根级核心文件全部 `py_compile` 通过（generate_report.py 除外，见 P2-1）。
- ✅ 修复后全部引擎模块 100% 导入成功（0 失败）。
- ✅ 全链路 `analyze_tax_risk_docs(2, db)` 返回 `ok=True`，报告含 35 个数据键，`invoice_counts` 键存在（历史 P0 未回归）。
- ✅ 无其他导入级合并遗留炸弹（9 处 `# [merged]` 标记中，其余均为运行时同模块引用，已加 try 或后方定义可解析）。
- ✅ DB 级 `audit.py 2` 会计七项全通过（重复记账/借贷不平/三号拆分/BK 凭证号/科目名称/档案锁定/来源一致），仅第 8 项系统一致性报 1 处**既存**规则计数漂移（见 P2-5）。

---

## 六、本次修复清单

| 文件 | 修改 |
|------|------|
| `engine/agents/coordinator.py` | 加 `from __future__ import annotations`；全局实例化移至文件末尾 |
| `engine/agi_engine.py` | 加 `from __future__ import annotations` |
| `engine/pipeline.py` | `except Exception: pass` → 记录失败日志到 pipeline_log |

验证方式：全模块 import + `agi.ask()` 冒烟 + 全链路 `analyze_tax_risk_docs(2)` 复跑。

**修复前后全链路对比（账套 2，88 份资料）**：

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| NameError 堆栈 | 每次分析打印 `ReasoningResult` NameError | ✅ 无 |
| `ok` | True（AGI 注入被吞） | ✅ True |
| 报告数据键数 | 35 | ✅ **36**（AGI 推理章节回归注入） |
| `invoice_counts` | 存在 | ✅ 存在（历史 P0 未回归） |
