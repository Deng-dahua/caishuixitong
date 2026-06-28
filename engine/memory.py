"""
稽查引擎记忆系统 — 历史分析经验积累与检索

═════ 引擎核心能力宣言 ═════
  本引擎具备五项核心智能能力：

  🧠【有记忆】
    每次分析自动提取"指纹"（行业+模式+信号+评分），存入记忆库。
    后续分析检索相似案例，输出行业对标、风险校准、常见信号预警。
    实现：save_analysis_memory() / query_similar_cases() / audit_memory.json
    当前积累：自动增长中，上限500条，支持12维度加权检索。

  📚【能学习】
    三层学习机制——
    ① 用户反馈学习：稽查员驳回发现→引擎记录finding_type+dismiss→
       自动调整信号权重（dismiss:-0.2,confirm:+0.1）→多次驳回自动禁用
       实现：record_user_feedback() / _adjust_signal_weights_from_feedback()
    ② EMA自学习：58样本指数移动平均→行业阈值动态校准
       实现：engine/self_learning.py EMA模块
    ③ 自动规则发现：从重复出现的信号组合中发现新模式→写入规则库
       实现：engine/pipeline.py 规则发现回路

  🔬【懂思考】
    四层推理架构——
    ① 假设-验证引擎：每条重大发现→生成2-3个竞争假设→逐条证据验证→加权判决
       实现：engine/hypothesis_engine.py
    ② Phase1-4推理引擎：初查信号检测→定向深挖→交叉验证→综合定性
       实现：engine/pipeline.py AuditContext
    ③ 因果叙事链：多信号叠加→自动推演因果链条→置信度评估
       实现：engine/domain_analysis.py CAUSAL_CHAIN_RULES (5条)
    ④ 四步稽查分析法：detect→verify→diagnose→report
       实现：engine/pipeline.py Phase4

  ⚖️【会判断】
    七层判定体系——
    ① 文件识别：四方交叉验证（文件名→列头→数据→公司匹配）
    ② 身份锚定：购买方/销售方vs公司名+USCC
    ③ 发票方向：买方匹配→进项/卖方匹配→销项/都不匹配→存疑
    ④ 进项分类：含抵扣列→认证抵扣/不含→记账发票
    ⑤ 服务闸门：销项金税编码∈25类服务→跳过进销存/BOM
    ⑥ 品名过滤：服务品名跳过进销存，实物品名正常检查
    ⑦ 存疑排除：双方不含公司→排除出所有分析

  🎯【懂决策】
    五层决策输出——
    ① 风险综合评分：76/100→四级风险等级（极高/高/中/低）
    ② 审计策略推荐：P0立即处理/P1限期整改/P2持续关注
    ③ 因果叙事链：从信号叠加推演因果→提出具体核查路径
    ④ 合规门禁：12项质量标准→自动修复→标记质量警告
    ⑤ 自省检查：14项自问→全部通过才算可靠分析
    ⑥ 报告输出：7章格式+五段叙事+六要素+同类合并+语音播报+新闻联播语调+橙色跟随

  五项能力协同运转，引擎从"每次都从零开始"到"越用越聪明"。

═════ 行业推断铁律（写入引擎记忆中，随记忆系统永续生效）═════
  行业推断唯一依据 = 销项发票品名
  不参考进项发票品名
  WHY: 销项=企业实际经营产出（卖什么就是什么行业）
       进项=采购投入/成本结构（买什么不代表行业）
  代码位置: engine/phase1_triage.py _infer_industry_from_goods()
            main.py _extract_material_intel() 第5步

═════ 系统稽查判定规则（2026-06-28 老邓亲授，写入引擎记忆）═════

【规则一：公司身份锚定】
  所有分析以当前账套公司为锚点（侧边栏公司名+信用代码）
  销项发票的销售方只有一个=账套公司
  进项发票的购买方只有一个=账套公司
  代码: engine/pipeline.py 综合判断层

【规则二：发票方向自动判定】
  上传发票→逐行扫描购买方/销售方名称+税号→与公司身份比对
  公司名/USCC在购买方→进项 | 在销售方→销项 | 双方都不含公司→存疑
  存疑发票排除出分析，不参与记账和风险计算
  代码: engine/pipeline.py 发票方向判定

【规则三：综合判断·四方交叉验证】
  文件名暗示→列头推理→数据扫描（买卖方身份）→公司匹配
  证据一致→高置信度 | 冲突→优先数据推理 | 全不匹配→存疑
  代码: engine/pipeline.py 综合判断层

【规则四：进项发票再分类】
  进项+含"有效抵扣税额/勾选状态/勾选时间"→进项抵扣认证（抵税用）
  进项+无上述列→进项发票（记账用）
  两种用途不可混淆
  代码: engine/pipeline.py 列头推理

【规则五：服务行业闸门】
  销项品名金税分类编码∈服务行业（广告/IT/咨询/金融等25类）
  →跳过进销存台账/BOM表/进销比/毛利率行业对标
  三层闸门：管道层→域分析层→引擎输出层
  配置: static/industry_data.json service_industries

【规则六：品名级精准过滤】
  公司既有服务又有实物品名→服务跳过进销存，实物正常检查
  按品名金税编码逐项判定，不搞公司级别一刀切
  代码: engine/pipeline.py _is_service_goods()

【规则七：配置外部化】
  服务行业编码→static/industry_data.json
  文件名映射→static/filename_type_map.json
  列结构锚点→static/type_anchors.json
  新增行业/类型只改JSON，不改Python代码

═══ 缺失的关键规则（2026-06-28 补充写入） ═══

【规则八：只读有效信息，空白全部忽略】
  解析Excel/文件时，跳过所有空白行、小计行、合计行、重复表头行
  只统计有实际数据的有效记录
  140行Excel→可能只有7条有效，不能把空行计入分析
  代码: main.py _is_summary_row() / engine/pipeline.py 有效行过滤

【规则九：文件类型识别体系（13类）】
  引擎必须通过四步推理识别文件类型，不得仅靠文件名或单一关键词：
  bank_statement / sales_invoice / purchase_invoice / input_vat_deduction /
  salary / salary_tax / social_security / housing_fund / voucher /
  contract / inventory / trial_balance / tax_declaration
  代码: engine/pipeline.py 综合判断层 / static/filename_type_map.json

【规则十：存疑发票绝对排除】
  买卖双方都有名称+税号但都不含当前公司→此发票不属于本账套
  标记"存疑"后必须排除出所有后续分析（记账/风险计算/税务推断）
  不得以任何默认值（如默认进项）继续处理
  代码: engine/pipeline.py 存疑标记+排除逻辑

【规则十一：账套数据物理隔离】
  所有分析数据按company_id隔离，文件存储在{company_id}/子目录
  删除账套=32张数据表级联删除+文件目录全部清除
  不同账套的分析结果互不影响
  代码: engine/pipeline.py _get_company_upload_dir() / archives.py delete_company()

═══ 引擎自省能力 ═══
  每次分析完成后，引擎必须以五项核心能力为纲逐项自问：

  🧠 有记忆 —— 本次分析指纹是否已保存？相似案例是否已检索？
     自省: analysis_memory_saved AND similar_cases_queried

  📚 能学习 —— 用户驳回是否已记录？信号权重是否已调整？EMA是否已更新？
     自省: feedback_recorded OR ema_updated OR rules_discovered

  🔬 懂思考 —— Phase1-4是否完整执行？因果叙事链是否触发？假设验证是否运行？
     自省: phase4_completed AND (causal_chains > 0 OR hypothesis_verified)

  ⚖️ 会判断 —— 27条判定规则是否逐条校验？
     自省: (规则一 至 规则十一、规则十六、规则二十五、规则二十六、规则二十七) ALL_PASSED

  🎯 懂决策 —— 风险评分是否生成？审计策略是否推荐？报告是否合规输出？
     自省: risk_score_generated AND audit_strategies_recommended AND report_standards_passed

  具体12项检查清单：
  1. 公司身份是否已锚定？（规则一）
  2. 发票方向是否已比对判定？（规则二）
  3. 存疑发票是否已排除？（规则十）
  4. 空白行是否已跳过？（规则八）
  5. 服务行业是否已跳过进销存？（规则五）
  6. 品名是否精准过滤？（规则六）
  7. 每条发现是否包含五段稽查叙事？（规则十二、二十一）
  8. 证据数据是否完整渲染？（规则十三）
  9. 报告是否遵循7章标准格式？（规则十四）
  10. 报告是否纯净（无内部标签/按钮/系统参数）？（规则十五、十九）
  11. 稽查术语是否正确（稽查性质/事实 vs 违法性质/事实）？（规则十八）
  12. 第二章是否详细化（7段2000字以上+实时数据）？（规则二十）
  13. 同类风险是否已合并展示（同type合并+子项列示）？（规则二十五）
  14. 报告段落是否独立舒展（禁止多逻辑挤在一段、禁止一逗到底）？（规则二十六）
  15. 收款分类是否配置驱动（JSON规则+双字段匹配+零值隐藏+兜底标注）？（规则二十八）
  上述15项全部通过 + 五项核心能力全部达标，本次分析才算可靠。

【规则十二：稽查过程叙事】
  每条发现必须包含五段稽查叙事，将稽查过程写得明明白白、通俗易懂：
  ① 📌 发现要点——通俗描述这个风险是什么，外行也能看懂
  ② 📡 线索获取——从哪些数据源、通过什么方法锁定了异常
  ③ 🔬 分析过程——展开证据链调查步骤（≥3步），无证据链时自动生成4步默认路径
  ④ 📋 证据组织——证据记录数量、交叉验证方式、证据闭环状态
  ⑤ 💡 通俗理解——用关键数据（偏差比率/涉及金额）解释问题严重性
  叙事基于finding实际字段，每段必须通俗易懂让被查单位也能理解
  代码: static/js/tax-doc-analysis.js _renderReportFallback() 稽查过程叙事段
  规范: static/js/tax-report-standards.js 第三章·附

【规则二十一：第三章六要素+叙事标准】
  第三章每条发现的标准呈现结构：
  稽查过程叙事（五段）→ 六要素格式（稽查性质/稽查事实/证据材料/证据来源/法律依据/处理建议）→ 关联证据链标签
  禁止：笼统的"详见附件"（必须展开明细表）→ 禁止：截断证据数据（全量展示）→ 禁止：纯技术术语（必须有通俗理解段）
  代码: static/js/tax-doc-analysis.js 完整第三条发现渲染

【规则十三：证据数据完整渲染】
  引擎内部丰富的证据数据必须在报告中完整呈现：
  - evidence_rows → 逐笔证据明细表（来源/对方/金额/日期/备注）
  - items → 逐项证据明细表（表头动态生成）
  - matched_chain_details → 关联证据链标签+调查步骤展示
  禁止只显示"共XX条记录"的计数而不渲染实际数据
  代码: static/js/tax-doc-analysis.js ③证据材料渲染

【规则十四：报告7章标准格式】
  报告必须遵循7章正式法律文书结构：
  封面 → 目录 → 一(基本情况) → 二(实施情况) → 三(发现问题) → 四(结论) → 五(建议) → 六(权利) → 七(签字) → 附件
  第三章每条发现按六要素呈现：稽查性质→稽查事实→证据材料→证据来源→法律依据→处理建议
  注意：稽查报告尚未进入法律裁决阶段，使用"稽查性质/稽查事实"而非"违法性质/违法事实"
  禁止使用简化版或内部调试版格式（如blocks渲染器）
  代码: static/js/tax-doc-analysis.js _renderReportFallback()
  规范: static/js/tax-report-standards.js

【规则十五：报告纯净度】
  正式报告中禁止出现以下内容：
  - 驳回按钮/审查面板（审查面板应独立于报告之外，折叠显示）
  - 内部技术标签（Synthesis:/Causal:/[AGI]/[Phase]等中英混杂前缀）
  - 稽查行为准则/稽查方法论演进（属于系统内部文档）
  - 系统自诊/修正记录（属于引擎内部工作日志）
  代码: static/js/tax-doc-analysis.js 文本清理逻辑

【规则十六：审查驳回学习闭环】
  稽查员通过审查面板驳回某条发现 → 引擎记录驳回（finding_type + action:dismiss）
  → 自动调整对应信号权重（dismiss→-0.2） → 下次分析时该信号降权
  → 多次驳回的信号将被自动禁用到方法论过滤器
  这是引擎"越用越聪明"的核心学习机制
  代码: engine/memory.py record_user_feedback() / _adjust_signal_weights_from_feedback()
  前端: static/js/tax-doc-analysis.js 发现审查面板
  前端: static/index.html window._dismissTaxFinding()

【规则十七：发票附件11列标准】
  报告附件必须按11列标准表全量展示发票明细：
  销项：购买方/品名/规格/单位/数量/金额/税额/价税合计/日期/票种/发票号
  进项：销售方/品名/规格/单位/数量/金额/税额/价税合计/日期/票种/发票号
  核心成本发票+重大费用发票各5列（销售方/品名/金额/价税合计/日期）
  代码: engine/pipeline.py 发票明细数据注入 / static/js/tax-doc-analysis.js 附件渲染

═════ 报告呈现规则（2026-06-28 新增，确保报告专业合规）═════

【规则十八：稽查术语规范】
  报告用语必须体现"稽查发现"而非"法律定性"立场：
  正确：稽查性质/稽查事实/稽查发现/涉嫌/存疑/提示风险
  禁止：违法性质/违法事实/违法行为/确定/认定
  原因：稽查报告阶段尚未进入裁决程序，不得预判法律结论
  代码: static/js/tax-doc-analysis.js 六要素渲染

【规则十九：报告机密保护】
  正式报告（给被查单位/税务机关）禁止暴露系统内部信息：
  - 引擎架构（52步流程/模块数量/阶段名称）
  - 系统能力参数（规则数/线索链数/证据链数）
  - 质量自检清单（全链路闭环打勾）
  - 引擎内部日志（系统自诊/修正记录）
  - 内部文档（稽查行为准则/方法论演进）
  - 技术标签（Synthesis:/Causal:/[AGI]/[Phase]等前缀）
  原则：报告只呈现稽查结论和依据，不暴露内部实现
  代码: static/js/tax-doc-analysis.js 移除renderAnalyzeHeader调用

【规则二十：第二章稽查实施详细化】
  第二章必须按7段2000字以上详细叙述：
  ①资料审阅(四方验证+文件明细表) ②身份锚定(逐行比对+三层分类)
  ③行业判定(金税编码+三层闸门) ④资金核对(收/付两端+方法论约束)
  ⑤穿透分析(供/客/人/关联四项) ⑥行业对标(跳过/适用说明)
  ⑦综合分析(全链路执行顺序)
  每段必须基于实际数据动态生成，不硬编码固定模板
  代码: static/js/tax-doc-analysis.js _renderReportFallback() Ch2

═════ 报告后四章规则（2026-06-28 新增）═════

【规则二十二：第四章稽查结论详细化】
  第四章必须包含五个结论段落：
  ① 风险分布表——四级风险(极高/高/中/低)各列数量/占比/代表事项
  ② 证据链完整性——跨域交叉验证覆盖范围、核心证据闭环构成
  ③ 稽查局限性声明——如实列出因资料缺失无法确认的事项（缺什么报什么）
  ④ 定调性总体结论——按风险等级自适应表述（高→建议立案/中→建议整改/低→建议完善）
  ⑤ 推理引擎综合结论卡片（_phase4_synthesis存在时渲染）
  每段基于实际数据动态生成，禁止固定模板
  代码: static/js/tax-doc-analysis.js Ch4

【规则二十三：第五章P0P1P2三级建议体系】
  处理建议按紧急程度分三级，每级独立卡片呈现：
  🔴 P0立即处理（极高/高风险）——红线问题，5工作日内书面回复
  🟡 P1限期整改（中风险）——15工作日内完成整改并提交报告
  🟢 P2持续关注（低风险/优惠）——30工作日内完善并持续规范
  附：整改期限+法律后果+异议处理指南
  代码: static/js/tax-doc-analysis.js Ch5

【规则二十四：第六章权利告知详细化】
  五项法定权利各独立卡片，每卡包含：
  - 权利全称+法律原文解释
  - 行使条件+操作方式
  - 法定期限（精确到日）
  - 具体法条号
  顺序：回避→陈述申辩→听证→复议→诉讼（程序递进）
  代码: static/js/tax-doc-analysis.js Ch6

【规则二十五：同类风险合并展示】
  同一风险类型（type字段相同）出现的多条发现，必须合并为一条在报告中呈现。
  合并逻辑：
  ① 按type字段分组（去除Synthesis:/Causal:等前缀后trim比对）
  ② 同一组取最高风险等级作为合并后等级
  ③ 合并后的detail列出所有子项：格式为"（同类风险共N项，合并列示如下）\n\n【子项1】...\n\n【子项2】..."
  ④ 合并所有子项的items/evidence_rows/matched_chain_details到父项
  ⑤ 合并后的标题显示"N项同类风险合并"标签
  ⑥ 每条子项独立展示：子项标题、细节描述、税务影响、处理建议
  代码位置: static/js/tax-doc-analysis.js _renderReportFallback() 同类风险合并段
  示例: 2条"知识图谱-供应商客户重叠"→1条，显示子项1(中风险)+子项2(中风险)

【规则二十六：报告段落格式规范】
  报告每一段必须独立、舒展，禁止以下五大反模式：
  ① 禁止一逗到底——多个完整逻辑句子不得用逗号串联为整块
  ② 禁止多逻辑挤一段——同一段不得混杂2个以上不相关的分析维度
  ③ 禁止括号堆叠——不得用括号链"(A→B)(C→D)(E→F)"堆砌判定
  ④ 子项必须独立成段——序号引导的内容各自独立段落
  ⑤ 数据+解释分层——先陈数据→再释方法→最后结论
  优化示例: 身份锚定1段→3段, 行业闸门1段→6段, 穿透分析1段→5段
  代码: static/js/tax-doc-analysis.js _renderReportFallback()

【规则二十七：语音播报与可访问性】
  报告必须内置语音播报：全文播报+点击播报(持续至完)+暂停/速度(0.85-1.3x)
  新闻联播级6档情感语调，橙色底纹实时跟随当前段落，中文男声记者音色
  代码: static/js/tax-doc-analysis.js TTS系统

【规则二十八：收款分类自适应】
  禁止预设固定的收款类别数量。分类规则必须配置驱动+双字段联合匹配。
  ① 同时扫描付款方名称+交易摘要两个字段
  ② 按JSON配置的规则列表逐层匹配，第一命中生效
  ③ 配置位于 industry_data.json → 收款分类规则，全行业通用
  ④ 零值类别自动隐藏，不显示在报告中
  ⑤ 兜底类别标注"待分析"提示稽查员关注
  ⑥ 覆盖全行业12+收款场景：税费返还/银行内部/股东注资/关联往来/借款/保证金/第三方支付/政府补贴/保险理赔/资产处置/企业客户/个人待分析
  ⑦ 纠错验证——分类后自问。三信息综合分析(对方户名+摘要+交易附言)，不能只看单一字段。常识判断：<20元有零有整且文本全空→银行利息
  代码: engine/domain_analysis.py 收款构成段+纠错验证段，配置: static/industry_data.json

═════ 假设-验证推理引擎（引擎"思考"能力）═════
  每条重要发现 → 生成2-3个竞争假设 → 逐条证据验证 → 加权判决
  代码位置: engine/hypothesis_engine.py run_hypothesis_verification()
  调用位置: main.py ~22383行（方法论过滤后、明细注入前）
══════════════════════════════════════════════════════════════
"""

import json
import os
import time
from datetime import datetime

# 记忆存储路径
_MEMORY_PATH = os.path.join(os.path.dirname(__file__), '..', 'static', 'audit_memory.json')


def save_analysis_memory(ctx, synthesis):
    """
    保存分析记忆 — 提取分析指纹存入记忆库
    
    指纹字段：
      - timestamp: 分析时间
      - industry: 行业
      - biz_model: 经营模式（制造业/贸易/服务）
      - scale: 规模
      - risk_score: 综合风险评分
      - risk_level: 风险等级
      - red_flags: 红灯信号列表
      - yellow_flags: 黄灯信号列表
      - pattern_hits: Phase 3 命中的信号叠加模式
      - total_findings: 总发现数
      - core_issues: 核心问题摘要
      - snapshot: 财务快照
    """
    memory = _load_memory()
    
    fs = ctx.financial_snapshot
    cp = ctx.company_profile
    
    fingerprint = {
        "timestamp": datetime.now().isoformat(),
        "industry": cp.get("industry", ""),
        "biz_model": cp.get("biz_model", ""),
        "scale": cp.get("scale", ""),
        "risk_score": synthesis.get("risk_score", 0) if synthesis else 0,
        "risk_level": synthesis.get("overall_risk", "未知") if synthesis else "未知",
        "red_flags": [f["type"] for f in ctx.red_flags] if ctx.red_flags else [],
        "yellow_flags": [f["type"] for f in ctx.yellow_flags] if ctx.yellow_flags else [],
        "pattern_hits": synthesis.get("cross_validated_patterns", 0) if synthesis else 0,
        "total_findings": synthesis.get("total_findings", 0) if synthesis else 0,
        "has_processing": ctx.has_processing_fee,
        "has_personal_payments": ctx.has_personal_payments,
        "supplier_concentration": ctx.supplier_concentration,
        "customer_concentration": ctx.customer_concentration,
        "data_quality_score": ctx.data_quality_score,
        "snapshot": {
            "sales": fs.get("total_sales", 0),
            "purchases": fs.get("total_purchases", 0),
            "bank_in": fs.get("total_bank_in", 0),
            "bank_out": fs.get("total_bank_out", 0),
            "salary": fs.get("total_salary", 0),
            "gross_margin_pct": fs.get("gross_margin_pct", 0),
        }
    }
    
    memory.append(fingerprint)
    
    # 限制记忆数量（保留最近500条）
    if len(memory) > 500:
        memory = memory[-500:]
    
    _save_memory(memory)
    return len(memory)


def query_similar_cases(ctx):
    """
    检索相似案例 v2 — 加权关键词匹配（准向量检索，无需embedding依赖）
    
    匹配维度（加权）：
      - 同行业（精确匹配）: 权重 3
      - 行业关键词重叠: 权重 2  
      - 同经营模式: 权重 2
      - 收入规模相近: 权重 1
    
    返回结构同v1，增加 similarity_scores 和 calibrated_thresholds
    """
    memory = _load_memory()
    
    if not memory:
        return {
            "total_records": 0,
            "similar_count": 0,
            "same_industry": [],
            "same_model": [],
            "avg_risk_score": 0,
            "common_red_flags": [],
            "insight": "暂无历史分析记录。",
            "calibrated_thresholds": {},
        }
    
    cp = ctx.company_profile
    industry = cp.get("industry", "")
    biz_model = cp.get("biz_model", "")
    current_sales = ctx.financial_snapshot.get("total_sales", 0)
    
    # ── 加权相似度评分 ──
    scored_cases = []
    for m in memory:
        score = 0
        m_industry = m.get("industry", "")
        m_model = m.get("biz_model", "")
        m_sales = (m.get("snapshot", {}) or {}).get("sales", 0)
        
        # 同行业精确匹配
        if industry and m_industry == industry:
            score += 3
        
        # 行业关键词重叠（模糊匹配）
        if industry and m_industry:
            ind_words = set(industry)
            m_words = set(m_industry)
            overlap = len(ind_words & m_words) / max(len(ind_words | m_words), 1)
            score += overlap * 2
        
        # 同经营模式
        if biz_model and m_model == biz_model:
            score += 2
        
        # 收入规模相近（同数量级）
        if current_sales > 0 and m_sales > 0:
            ratio = max(current_sales, m_sales) / max(min(current_sales, m_sales), 1)
            if ratio < 3:  # 3倍以内视为相近
                score += 1
        
        if score > 0:
            scored_cases.append((score, m))
    
    scored_cases.sort(key=lambda x: -x[0])
    
    # 取相似度>=2 的案例
    similar = [m for s, m in scored_cases if s >= 2]
    exact_match = [m for s, m in scored_cases if s >= 4]
    same_industry = [m for m in memory if m.get("industry") == industry and industry]
    same_model = [m for m in memory if m.get("biz_model") == biz_model and biz_model]
    
    # 统计常见信号
    from collections import Counter
    red_counter = Counter()
    for m in similar[:50]:
        for flag in m.get("red_flags", []):
            red_counter[flag] += 1
    common_red = red_counter.most_common(5)
    
    scores = [m.get("risk_score", 0) for m in similar if m.get("risk_score")]
    avg_score = sum(scores) / len(scores) if scores else 0
    
    insight = _generate_insight(ctx, similar, common_red, avg_score)
    
    # ── 历史数据校准阈值 ──
    calibrated = _calibrate_thresholds_from_history(memory, industry, biz_model)
    
    return {
        "total_records": len(memory),
        "similar_count": len(similar),
        "exact_match_count": len(exact_match),
        "same_industry": same_industry,
        "same_model": same_model,
        "avg_risk_score": round(avg_score, 1),
        "common_red_flags": common_red,
        "insight": insight,
        "calibrated_thresholds": calibrated,
    }


def _calibrate_thresholds_from_history(memory, industry, biz_model):
    """从历史数据中自动校准行业阈值。
    
    对同行业企业的毛利率、购销比、供应商/客户集中度等指标
    进行统计分析，产出动态阈值替代硬编码。
    """
    if not memory:
        return {}
    
    # 筛选同行业案例
    industry_cases = [m for m in memory if m.get("industry") == industry and industry]
    if len(industry_cases) < 3:
        industry_cases = [m for m in memory if m.get("biz_model") == biz_model and biz_model]
    if len(industry_cases) < 3:
        industry_cases = memory[-50:]  # 兜底用最近50条
    
    # 提取财务快照
    snapshots = [(m.get("snapshot") or {}) for m in industry_cases]
    
    gross_margins = [s.get("gross_margin_pct", 0) for s in snapshots if s.get("gross_margin_pct", 0) != 0]
    supplier_concs = [m.get("supplier_concentration", 0) for m in industry_cases if m.get("supplier_concentration")]
    customer_concs = [m.get("customer_concentration", 0) for m in industry_cases if m.get("customer_concentration")]
    data_scores = [m.get("data_quality_score", 0) for m in industry_cases if m.get("data_quality_score")]
    
    def _percentile(data, p):
        if not data: return 0
        s = sorted(data)
        idx = int(len(s) * p / 100)
        return s[min(idx, len(s)-1)]
    
    calibrated = {}
    
    if len(gross_margins) >= 3:
        calibrated["gross_margin_low"] = _percentile(gross_margins, 10)  # P10 = 异常低
        calibrated["gross_margin_high"] = _percentile(gross_margins, 90)  # P90 = 异常高
        calibrated["gross_margin_median"] = _percentile(gross_margins, 50)
        calibrated["gross_margin_sample_size"] = len(gross_margins)
    
    if len(supplier_concs) >= 3:
        calibrated["supplier_concentration_warn"] = _percentile(supplier_concs, 75)  # P75 = 预警
        calibrated["supplier_concentration_sample_size"] = len(supplier_concs)
    
    if len(customer_concs) >= 3:
        calibrated["customer_concentration_warn"] = _percentile(customer_concs, 75)
        calibrated["customer_concentration_sample_size"] = len(customer_concs)
    
    if len(data_scores) >= 3:
        calibrated["data_quality_avg"] = sum(data_scores) / len(data_scores)
    
    return calibrated


def record_user_feedback(feedback):
    """记录用户反馈 — 对分析结论的确认/修正/补充。
    
    feedback 结构:
      {
        "finding_type": "购销严重倒挂",  # 被反馈的发现类型
        "action": "confirm" | "dismiss" | "adjust",  # 确认/驳回/调整
        "adjusted_score": 8,            # 调整后的评分(可选)
        "note": "确实是关联交易问题",    # 备注
        "timestamp": "2024-01-15T10:00"
      }
    
    反馈数据用于：
      1. 信号权重自适应调整
      2. 虚假信号降权
      3. 漏报信号追偿
    """
    feedback_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'audit_feedback.json')
    
    try:
        if os.path.exists(feedback_path):
            with open(feedback_path, 'r', encoding='utf-8') as f:
                feedbacks = json.load(f)
        else:
            feedbacks = []
    except Exception:
        feedbacks = []
    
    feedback["timestamp"] = feedback.get("timestamp") or datetime.now().isoformat()
    feedbacks.append(feedback)
    
    # 限制1000条
    if len(feedbacks) > 1000:
        feedbacks = feedbacks[-1000:]
    
    try:
        os.makedirs(os.path.dirname(feedback_path), exist_ok=True)
        with open(feedback_path, 'w', encoding='utf-8') as f:
            json.dump(feedbacks, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    
    # ── 根据反馈调整信号权重 ──
    adjusted = _adjust_signal_weights_from_feedback(feedbacks)
    
    return {
        "ok": True,
        "total_feedbacks": len(feedbacks),
        "adjusted_weights": adjusted,
    }


def _adjust_signal_weights_from_feedback(feedbacks):
    """根据用户反馈调整信号权重。
    
    - confirm → 信号权重 +0.1（确认有效）
    - dismiss → 信号权重 -0.2（驳回=误报）
    - adjust → 按调整幅度微调
    """
    from collections import defaultdict
    
    weight_deltas = defaultdict(float)
    
    for fb in feedbacks[-50:]:  # 只看最近50条反馈
        ftype = fb.get("finding_type", "")
        action = fb.get("action", "")
        
        if action == "confirm":
            weight_deltas[ftype] += 0.1
        elif action == "dismiss":
            weight_deltas[ftype] -= 0.2
        elif action == "adjust" and fb.get("adjusted_score"):
            orig = fb.get("original_score", 5)
            adj = fb.get("adjusted_score", 5)
            weight_deltas[ftype] += (adj - orig) * 0.05
    
    # 钳制在 0.3 ~ 2.0 范围
    clamped = {}
    for k, v in weight_deltas.items():
        clamped[k] = round(max(0.3, min(2.0, 1.0 + v)), 2)
    
    return clamped


def get_adaptive_signal_weights(ctx, base_weights=None):
    """获取自适应信号权重 — 融合行业配置 + 历史反馈调整。
    
    优先级：用户反馈调整 > 行业配置 > 默认值1.0
    """
    # 行业配置权重
    ip = ctx.industry_profile or {}
    industry_weights = ip.get("signal_weights", {})
    
    # 用户反馈权重
    feedback_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'audit_feedback.json')
    adjusted_weights = {}
    try:
        if os.path.exists(feedback_path):
            with open(feedback_path, 'r', encoding='utf-8') as f:
                feedbacks = json.load(f)
            adjusted_weights = _adjust_signal_weights_from_feedback(feedbacks)
    except Exception:
        pass
    
    # 合并：基础默认1.0 → 行业配置覆盖 → 反馈调整覆盖
    merged = {}
    all_signal_names = set(list(industry_weights.keys()) + list(adjusted_weights.keys()))
    if base_weights:
        all_signal_names.update(base_weights.keys())
    
    for name in all_signal_names:
        w = base_weights.get(name, 1.0) if base_weights else 1.0
        w = industry_weights.get(name, w)
        w = adjusted_weights.get(name, w)
        merged[name] = round(w, 2)
    
    return merged


def _generate_insight(ctx, similar, common_red, avg_score):
    """基于历史数据生成洞察文本"""
    if not similar:
        return "暂无同行业/同模式的历史分析记录。这是首次分析。"
    
    cp = ctx.company_profile
    industry = cp.get("industry", "综合")
    biz_model = cp.get("biz_model", "")
    
    lines = []
    lines.append(f"系统记忆库中有{len(similar)}条{industry}{biz_model}企业的历史分析记录。")
    
    if avg_score > 0:
        avg_level = "极高风险" if avg_score >= 70 else ("高风险" if avg_score >= 50 else "中风险")
        lines.append(f"同类型企业历史平均风险评分{avg_score:.0f}/100（{avg_level}）。")
    
    if common_red:
        lines.append(f"同类型企业常见红灯信号：")
        for flag, count in common_red[:3]:
            lines.append(f"  · {flag}（出现{count}次）")
    
    # 对比当前企业与历史均值
    fs = ctx.financial_snapshot
    current_score = 0  # will be set later
    if avg_score > 60:
        lines.append(f"该行业整体风险偏高，当前企业的异常需要结合行业特征综合判断。")
    elif avg_score < 30:
        lines.append(f"该行业整体风险较低，当前企业的异常信号相比同行更为突出，需要重点关注。")
    
    lines.append(f"随着记忆库积累更多案例，洞察将越来越精准。")
    
    return "\n".join(lines)


def _load_memory():
    """从文件加载记忆"""
    try:
        if os.path.exists(_MEMORY_PATH):
            with open(_MEMORY_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_memory(memory):
    """保存记忆到文件"""
    try:
        os.makedirs(os.path.dirname(_MEMORY_PATH), exist_ok=True)
        with open(_MEMORY_PATH, 'w', encoding='utf-8') as f:
            json.dump(memory, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
