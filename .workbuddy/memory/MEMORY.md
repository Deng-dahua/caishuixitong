# 项目长期记忆（caishuixitong 财税风险防控系统）

## ★ 红线驱动方法论（2026-09-06 确立，替代「按行业套场景」）
**核心立场**：税务红线不因行业而变。行业只影响「线索长什么样」，不影响
「红线是什么」。一旦符合某项风险情形即触碰红线；原架构按行业场景输出
「待核事实：XXX核验」，从不回答「触碰了哪条红线」，已废弃。
**主线**：红线判定 → 线索链（怎么发现的）→ 证据链（要什么证据）→ 论证链（主张/反证/裁决）。
**模块**：`engine/tax_redlines.py`(红线库42条) / `clue_chain.py` / `evidence_chain.py` /
`argumentation.py` / `redline_engine.py`(按红线归并，不按 finding 罗列)；
pipeline 场景执行后接入，结果入 `comprehensive.redline_detection`；
报告 `enterprise_report._build_redline_problems` 五段式输出。
**四条判定铁律（契约测试 tests/test_redline_methodology.py 锁死）**：
1. 触红≠定性：是否触红**只取决于线索链是否给出可量化触红事实**，与证据链
   闭合度无关；闭合度只决定能否定性。（坑：曾用闭合度 0.35 卡触红，吞掉真实疑点）
2. 反证（正当理由）**只认企业是否实际提交**，严禁按资料类别关键词猜测。
   （坑：「银行承兑汇票」含「转账」二字被判反证已提供 → 147万成本无付款流水被误排除）
3. 证据「已有/缺失」必须对齐 15 类稽查资料，**禁止模糊命中**。
   （坑：清单含「渠道订单」把「采购合同」判已有 → 闭合度虚高100% → 错误定性）
4. 触红后置信度下限 0.60（符合构成要件就不能说成没把握）。
**报告标题必须是红线名**（如「RL-PTY-001 采购成本无对公付款资金证据」），
禁止再出现「待核事实：XXX核验」空壳。

## 问题挖掘四层机制（设计基线，2026-08 确立）
1. 规则触发（阈值/关键词命中）2. 方法论证析（行业方法论比对）3. 要素完备性/缺失型异常（"该有的没有"：零运费/无场地/无能耗/必要费用缺失，指向空壳·账外·虚开）4. 假设-证据裁决（竞争假设贝叶斯更新）。
核心原则：**发现≠确认**。缺失型疑点必须经竞争假设裁决，证据不足一律转「置疑清单」抛企业自证，系统绝不自动定罪。

## ⚠️ 铁律：「调保守阈值」是伪命题（老邓 2026-09-01 明确）
- 一个违法事实**不会**因为它没超过保守阈值就变成不违法。缺失败象（零运费/无场地/无能耗/无外省加工费产能等）**一律作为待证信号抓取**，确认/待证仅区分「现有资料能否直接断言」，绝不通过抬高阈值来放过任何信号。
- 裁决三态：① 风险假设后验≥0.60（缺失型）或置信差>0.6（通用）→ **直接确认风险**（升级 score）；② 正常假设胜出 → **降级**（判非风险）；③ 两假设后验接近、风险仅微弱胜出（后验 0.55~0.60）→ **unconfirmed 转置疑清单**。禁止为"降低误报"而调高确认阈值。

## 缺失型（missing_element）实现要点
- 引擎：`engine/hypothesis_engine.py` 的 `missing_element` 模板 + `SIGNAL_TO_TEMPLATE` 映射 + `_evaluate_evidence` 缺失型分支 + `run_hypothesis_verification` 的 `adjudication=="missing"→_hypothesis_unconfirmed`。
- 联动：`engine/inspection_questions.py` `run_inspection_questions(unconfirmed_findings=...)` 把 unconfirmed 缺失型发现转成具体询问；`engine/pipeline.py` 中稽查询问步骤须**在假设验证之后**执行（consumes unconfirmed）。
- **已知坑**：`_evaluate_evidence` 中缺失型分支必须位于 `if "制造" in desc` 等通用经营模式分支**之前**，否则「制造业无生产能耗支出」被误判恒真。
- 地区推断：`engine/geo_infer.py` 从购销方名称反推省份（发票无 city/税号字段）；`collect_regions(invs, self_names)` **始终剔除本企业所在省**，仅返回外埠省份（2026-09-01 修复：旧逻辑在「全部同省」时误将本省返回为外埠，导致同省加工费被误判「外省加工费无自有产能」→ 误报）；`is_cross_region` 取外埠省份数≥2。
- `missing_element` 模板为**经营实质整体性**裁决（7 项必要要素综合聚合）：单一要素补全不足以翻案（如仅补租金但缺运输+能耗+车辆仍判风险）；正常型须场地/运输/能耗/车辆齐备方判良性。`unconfirmed` 标志在 `_verify_hypothesis` 返回与 `run_hypothesis_verification` 的 `details` 双写，`enterprise_report._build_confirmed_problems` 以 details 为权威源剔除 unconfirmed，避免既"已核定"又"待证"矛盾。

## 服务器
- 后台 uvicorn 进程随会话/关机被回收，须手动 `start8001.bat` 起重启（默认 8001）。系统级自启（schtasks/WScript.Shell）被环境安全策略阻断，不要重试。

## 报告四类呈现（2026-08-26 重构）
确认问题 / 已执行无异常 / 处理意见+复查标准 / 资料缺失+能力边界+置疑清单。前端 `tax-doc-analysis.js` 收敛四类；`capb`/`iqSec` 变量声明勿随删除块消失（否则 ReferenceError）。
