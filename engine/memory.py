# 数据驱动——所有数量从配置中心动态读取
from engine.system_config import rules_count, clue_chains, evidence_chains, methodology_count, total_chains, domain_functions

"""
稽查引擎记忆系统 — 历史分析经验积累与检索

═════ 引擎核心能力宣言与角色边界 ═════
  本引擎具备六项核心智能能力，全部为可运行代码而非纸上设计。
  引擎（memory.py中的硬逻辑）= 系统做什么 | 智哥（AI行为准则页面）= 怎么写代码

  🧠【有记忆】知识库系统 → static/audit_memory.json，上限500条，12维加权检索
  📚【能学习】审核反馈闭环 → correction_rules.json → 四级回退匹配 → 自进化
  🔬【懂思考】四阶段推理管线 → Phase1初查→Phase2深挖→Phase3交叉验证→Phase4综合定性
  ⚖️【会判断】七层判定体系 → 文件识别/身份锚定/发票方向/进项分类/服务闸门/品名过滤/存疑排除
  🎯【懂决策】五层决策输出 → 风险评分/P0-P2策略/因果叙事/合规门禁/自省检查 → 正式报告
  🔮【有自知】数据一致性自检 → audit_consistency.py → 启动前扫描 + 跨模块联动修正

  引擎负责：账务处理/跨域协商/审核闭环/过滤器/数据自检/行业认知/调度/知识库/法律推理
  智哥负责：编码态度/质量流程/验证自查/输出自检/框架搭建（不把业务逻辑硬编码）

══════════════════════════════════════════════════════════════
  ═══ 规则篇 —— 引擎的硬逻辑规范，不可违反 ═══
  以下章节定义引擎在各环节必须遵守的规则和判定标准。
  每条规则在代码中有对应的实现或检测机制，不是纸上条文。
══════════════════════════════════════════════════════════════

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
  16. 报告是否存在任何数据截断（经营范围/证据明细/分析步骤/发现描述）？（规则三十）
  上述16项全部通过 + 五项核心能力全部达标，本次分析才算可靠。

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

═════ 引擎核心铁律（2026-06-29 从AI行为准则迁移至引擎记忆）═════
  以下5条是引擎层面的硬性规范——不是对智哥编码行为的约束，而是系统本身的不可违反原则。
  每条铁律在代码中有对应的实现机制或检查工具。

【引擎铁律七：规则=代码】
  规则描述必须与代码实现严格一致。engine/memory.py 中的规则描述改变→
  必须同步修改 main.py 中的对应代码逻辑。禁止只改记忆不改代码。
  检测机制: audit_consistency.py 扫描 memory.py 的规则声明与 main.py 的实现是否匹配。
  违反后果: 记忆描述与代码行为脱节→系统"声称"的能力与实际不符→信任崩溃。

【引擎铁律八：代码即承诺】
  所有在文档/记忆/方法论中声称"已实现"的功能，必须在代码中存在对应的可运行实现，
  且可以通过"文件名:行号"精确追溯。禁止将"计划实现"表述为"已实现"。
  检测机制: 方法论渲染页面 auto-generate from audit_chains.json，天然防伪。
  违反后果: 文档中的"已实现"声明变成待验证的怀疑列表→文档可信度归零。

【引擎铁律九：全行业适用】
  所有分析逻辑、规则引擎、行业对标代码必须面向全行业各企业通用。
  行业特定的数据（关键词/阈值/基准值）存储在 JSON 配置文件中（industry_data.json），
  代码只负责读取和匹配。禁止在代码中硬编码任何行业特定的条件分支。
  检测机制: audit_consistency.py 扫描 JS/PY 文件中的行业关键词硬编码。
  违反后果: 非硬编码行业的企业分析结果失真→系统从"通用工具"退化为"行业专用工具"。

【引擎铁律十：主动关联更新】
  发现系统中某一处概念/数值/描述过时→主动扫描全项目所有相关位置→一次性全部更新。
  不等用户逐一指出。通过 audit_consistency.py --sync 自动执行。
  违反后果: 同一信息多处不一致→用户在不同页面看到不同版本→"到底信哪个？"

【引擎铁律十一：方法论先行】
  任何新增功能在上代码之前，必须先有明确的方法论定义——
  包括方法论的名称、适用场景、执行步骤、输入输出。
  方法论与代码的关系：方法论是设计文档（WHY），代码是实现（HOW）。
  禁止先写代码再补方法论（"按实现反推设计"不可信）。
  检测机制: audit_consistency.py 对比 audit_chains.json 中的方法论条目与 main.py 的实现。
  违反后果: 功能可运行但无法解释为什么这样做→用户质疑时无法给出令人信服的依据。

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

【规则二十九：六员跨企业比对】
  稽查必须执行六员（法定代表人/董事/监事/财务负责人/股东/经理）跨企业比对：
  ① 一人多角检测——同一人是否在本企业兼任多个角色
  ② 跨企业人员重叠——本企业六员是否同时在其他企业任职
  ③ 供应链交叉比对——供应商/客户的六员与本企业六员逐名比对→重叠=关联交易
  ④ 触发连锁稽查点——六员重叠+购销交易→关联交易→购销闭环→虚开发票
  ⑤   联网失败时从本地DB回退读取，不死等网络
  代码: engine/pipeline.py _check_six_personnel_risk() + _lookup_supply_chain()

【规则三十：禁止数据截断——全部信息完整呈现】
  报告中的任何信息均不得截断或隐藏，必须全量列示：
  ① 经营范围→全文展示，不设字符上限
  ② 发现描述 detail/description→全文，不截断
  ③ 证据明细 items/evidence_rows→全部列示，不限制条数
  ④ 分析步骤→全部展开，不限制步数
  ⑤ 合并子项 detail/tax_impact/suggestion→全文，不截断
  ⑥ 资金流往来方→全部列示，废除TOP限制
  铁律：宁可报告长，不可漏一字。税务稽查不放过任何一个细节。
  代码: static/js/tax-doc-analysis.js 所有 .substring()/.slice() 均应移除

══════════════════════════════════════════════════════════════
  ═══ 架构篇 —— 引擎的系统架构与功能模块 ═══
  以下章节描述引擎的架构设计、功能模块和运行机制。
  每个模块有对应的代码文件和调用位置。
══════════════════════════════════════════════════════════════

═════ 假设-验证推理引擎（引擎"思考"能力）═════
  每条重要发现 → 生成2-3个竞争假设 → 逐条证据验证 → 加权判决
  代码位置: engine/hypothesis_engine.py run_hypothesis_verification()
  调用位置: main.py ~22383行（方法论过滤后、明细注入前）
══════════════════════════════════════════════════════════════

═════ 跨域协商引擎（2026-07-01 更新为29条）═════
  域分析独立运行后，42个域产生的发现可能存在逻辑矛盾。
  跨域协商引擎在 all_findings 生成后、进入过滤管线前自动执行。
  代码: engine/cross_domain_negotiation.py → run_negotiation()

  【四层协商 — 29条协商规则】
  一、消解层（NEG-001~005 + NEG-050~052 + NEG-020/062，8条）
    触发：域A的结论直接否定域B的结论
    NEG-001: 进销存匹配异常 → 消解（服务行业无实物商品）
    NEG-002: BOM表需求判定 → 消解（服务产品无物料清单）
    NEG-003: 存货周转/库存预警 → 消解（无实物库存）
    NEG-004: 进销比行业对标 → 降为提示级
    NEG-005: 毛利率行业对标 → 降为提示级
    NEG-020: 经营实质检测到经营费用 → 消解"无经营场所"
    NEG-050: 服务行业 → 消解制造业成本(BOM/进销存/加工费)
    NEG-051: 个体工商户 → 消解企业所得税相关发现
    NEG-052: 小规模纳税人 → 消解进项税额异常
    NEG-062: 经营实质检测到经营费用 → 消解"无实际经营"

  二、降级层（NEG-004/005/021 + NEG-060~063，6条）
    触发：域A的结论削弱域B的结论
    NEG-004/005: 服务行业 → 进销比/毛利率降为提示
    NEG-021: 检测到运输费用 → "运输成本缺失"降为低风险
    NEG-060: 收款偏差可能含非经营收款 → "隐匿收入"降为中风险
    NEG-061: 付款偏差可能含非经营付款 → "虚列成本"降为中风险
    NEG-063: 银行流水与应税收入口径不同 → 申报偏差降为低风险

  三、标记层（NEG-010~012 + NEG-030/040，5条）
    触发：资料缺失 → 给依赖该资料的域结论打标签
    NEG-010: 缺合同 → 合同分层/合同比对 → 降为提示级
    NEG-011: 缺关联方资料 → 关联交易检测不完整
    NEG-012: 缺申报表 → 申报比对无法执行
    NEG-030: 收款含非经营项 → 标注"含非经营收款"
    NEG-040: 任意缺资料 → 全局标注"资料受限结论"

  四、联合增强层（NEG-AUG-001~010，10条）
    触发：多域异常信号同时触发 → 合成更高级别新发现
    NEG-AUG-001: 经营费用缺失+运输缺失+场所异常 → "空壳企业预警"
    NEG-AUG-002: 个人收款+收款待分析+个人交易 → "隐匿收入预警"
    NEG-AUG-003: 供应商异常+关联重叠+集中度 → "对倒开票预警"
    NEG-AUG-004: 红冲/作废发票+收款偏离 → "虚开发票预警"
    NEG-AUG-005: 工资个税异常+社保基数偏低 → "两套工资表预警"
    NEG-AUG-006: 专票超期未认证+进项税额异常 → "隐匿采购预警"
    NEG-AUG-007: 个人收款+股东资金往来 → "公司人格混同预警"
    NEG-AUG-008: 新办企业+大额开票 → "空壳开票公司预警"
    NEG-AUG-009: 劳务派遣成本+多处工资 → "拆分工资预警"
    NEG-AUG-010: 境外付款+外汇信号 → "跨境税务预警"

  执行时序：all_findings 生成 → run_negotiation() → 消解/降级/标记/增强 → 过滤管线。

═════ 审核反馈闭环（2026-06-29 新增）═════
  用户对报告发现的每一条审核都是系统的学习机会。
  代码: engine/self_learning.py → record_correction() + apply_correction_rules()
  存储: static/correction_rules.json → 按"发现类型|行业|经营模式"生成唯一指纹

  【五步闭环流程】
  第一步：用户点击审核 → 按审核内容模板填写 → 前端 postFeedback()
  第二步：POST /api/feedback → record_correction() → 生成指纹 → 存入JSON → 累加计数
  第三步：累计 ≥1次纠正 → auto_apply=true → 升级为自动规则
  第四步：下次一键分析 → apply_correction_rules() → 四级回退匹配 → 打_dismissed/negotiated标签
  第五步：报告渲染展示绿色审核横幅 → 不影响原始风险等级

  【四级回退匹配策略】
  L1 精确匹配：类型+行业+模式三者完全一致 → 置信度 0.7 生效
  L2 行业匹配：类型+行业一致，模式通配 → 置信度 0.7
  L3 通用匹配：仅类型一致，行业和模式通配 → 置信度 0.8
  L4 名称匹配：类型名称模糊匹配 → 置信度 0.8
  L1-L4 均未匹配 → 按原始逻辑输出

  【关键设计原则】
  - 审核不改变发现的风险等级（仅打标签，不降级）
  - 同指纹多次审核累积计数，不同行业/模式独立存储
  - 每次审核后清空前端+后端分析缓存

═════ 联动修改与数据一致性（2026-06-29 新增）═════
  系统中任一数据/概念变动 → 必须同步更新所有引用位置。
  代码: audit_consistency.py → 扫描 + 对比 + 修复 + 校准

  【数据一致性自检】
  权威数据源: static/system_config.json → 从原始数据文件实时统计生成
  Python 配置: engine/system_config.py → 从 system_config.json 自动生成
  启动集成: start.bat 在启动前执行 python audit_consistency.py
  检测范围: 所有 JS/PY 文件中的硬编码数字 vs 权威配置

  【三种运行模式】
  python audit_consistency.py          → 审计模式：扫描并报告不一致
  python audit_consistency.py --sync   → 同步模式：自动修正所有不一致
  python audit_consistency.py --calibrate → 校准模式：重新统计权威数据源

  【当前权威数据（2026-06-29）】
  rules_count=1608 | clue_chains=396 | evidence_chains=745
  methodology_count=1250 | total_chains=1250 | domain_functions=39
  cross_domain_clues=1215 (41 executable + 1250 legacy) | cross_domain_evidence=22 | engine_modules=28
  file_fingerprints=34 | quality_standards=12 | noise_filter_rate=97

═════ 跨模块内容一致性铁律（2026-06-30 新增·引擎铁律第七条）═════
  同一内容在多个模块中出现时，必须保持完全一致。
  每个共享内容块有且仅有一个权威源，其他模块为依赖副本。

  【标准定义】
  今天手册第5章（报告编制规范）与编制要求第2节（报告7章结构）
  封面+7章+附件共9块内容出现了3处不一致——日期示例不同、
  第一章正文长度不同、附件编号格式不同。这不是偶然错误——
  两份文档各自维护必然产生漂移。因此建立以下机制：

  【权威源规则】
  - 报告7章结构 → 权威源：tax-report-standards.js
  - 引擎数据数字 → 权威源：system_config.json
  - 方法论定义 → 权威源：audit_chains.json
  - 引擎规则 → 权威源：engine/memory.py

  【同步机制】（四触发全覆盖）
  1. start.bat 启动 → python audit_consistency.py --sync
  2. git pre-commit → python audit_consistency.py --sync
  3. 一键分析开始 → pipeline.py subprocess调用 --sync
  4. 手动执行 → python audit_consistency.py --sync

  【技术实现】
  代码位置：engine/shared_content_sync.py
  - sync_shared_content()：从权威源读取→对比依赖模块→自动覆盖
  - verify_shared_content()：静默验证，不修改文件
  - rebuild_shared_map()：重新扫描生成映射表
  数据位置：static/shared_content_map.json（定义所有共享块）

  【违反后果】
  两个模块对同一内容描述不一致 → 用户看到矛盾信息 → 
  信任崩溃 → 可能做出错误判断。同一内容的文字描述不同比数字
  不同更隐蔽——数字不同一眼能看出，文字描述不同很难察觉。

  【新增共享块流程】
  在 shared_content_map.json 的 shared_blocks 数组中追加：
  {
    "id": "唯一标识",
    "label": "内容标签",
    "title": "内容标题",
    "source_file": "权威源文件路径",
    "dependent_files": ["依赖模块1", "依赖模块2"],
    "content_hash": "自动计算的哈希",
    "content_length": 自动计算的长度
  }
  或执行 python audit_consistency.py --rebuild-shared-map 自动重建。

═════ 方法论过滤器体系（2026-06-29 新增）═════
  七类过滤规则在分析管线中依次执行，噪声过滤率 97%。
  执行位置: pipeline.py → _apply_methodology_filter()

  【七类过滤规则执行顺序】
  第一步 — 23类）
  23类禁止词：公安/经侦/刑事/走逃/失联/空壳/皮包/逃税/骗税/抗税/
  洗钱/走私/贩毒/赌博/非法集资/传销/涉黑/涉恶/暴恐/间谍/叛国/颠覆/分裂。
  → 物理删除，不可恢复。

  第二步 — COND_BAN 条件过滤（5类）
  无申报表→删除申报差异 / 无合同→删除合同分层 / 无工资→删除薪酬
  无台账→删除库存 / 无凭证→删除凭证匹配

  第三步 — 稽查重点保护（12类强制保留）
  虚开发票/骗取退税/隐匿收入/账外经营/阴阳合同/资金回流/
  关联交易转移利润/虚假申报/骗取优惠/恶意注销/走逃失联/暴力抗税。
  → 三层保护（后端修正+过滤器绕过+前端标记）

  第四步 — 正常结论排除
  含"一致/正常/无异常/OK/通过/合规"等词→删除。有转折词→保留。

  第五步 — 资料缺口限流
  资料缺失类 >5条 → 只保留score最高的5条。

  第六步 — 行业不匹配过滤
  行业特定关键词与企业行业不匹配 → 删除。

  第七步 — 去重合并
  同type前60字符一致 → 只保留score最高的一条，ref_id精确匹配。

═════ 模块联动关系矩阵（2026-06-29 新增）═════
  【文档类模块联动】
  手册（12章）↔ 编制要求（11节）↔ 审核模板（20场景）↔ 质量保障（6层25组件）
  → 任一个模块内容变动，其他三个必须同步检查

  【数据类联动】
  方法论数量 → 手册/分析链/引擎仪表盘/AGI/质量保障/core.js
  规则数量 → 稽查指令/引擎仪表盘/AGI/memory.py
  域函数数量 → 域分析/分析链/引擎仪表盘

  【变更触发链】
  修改 → git status → audit_consistency.py --sync → 手动补漏 → 统一提交

═════ 四阶段推理管线（2026-06-30 补录）═════
  系统核心推理引擎采用四阶段递进推理架构，数据在四个阶段之间单向流动。
  代码: engine/phase1_triage.py → phase2_deep_dive.py → phase3_cross_validate.py → phase4_synthesis.py
  调用位置: pipeline.py → _run_analyze()

  【Phase1 初查（triage）】
  对上传的全部资料执行快速扫描，识别表面异常信号。
  包括：文件类型识别、表头解析、行业推断（从销项品名推断真实行业）、
  基础数据校验（金额正负/日期范围/税率合法性）。
  代码: engine/phase1_triage.py

  【Phase2 深挖（deep_dive）】
  对Phase1识别的异常信号执行深度分析。每一类信号触发对应的分析域函数，
  域分析函数从原始数据中提取结构化证据（如逐笔比对银行流水与发票）。
  代码: engine/phase2_deep_dive.py / engine/domain_analysis.py（39个域函数）

  【Phase3 交叉验证（cross_validate）】
  将Phase2的结果放入跨域分析框架——检查不同域之间的结论是否一致。
  如果域A和域B的结论矛盾→触发矛盾消解。如果多个域信号同时指向同一问题→联合增强。
  代码: engine/phase3_cross_validate.py / engine/cross_domain_negotiation.py

  【Phase4 综合定性（synthesis）】
  汇总前三个阶段的所有发现→执行方法论过滤器（七类规则）→应用审核反馈规则→
  行业对标→生成最终的风险综合评分→输出正式报告JSON。
  代码: engine/phase4_synthesis.py / pipeline.py → _apply_methodology_filter()

═════ 调度中枢（2026-06-30 补录）═════
  系统的中央调度器，负责协调16个功能模块、7个数据域、16级处理管线。
  代码: engine/orchestrator.py
  调用位置: main.py → 每次一键分析启动时由orchestrator统一调度

  【16个功能模块】
  文件解析 / 域分析 / 线索链 / 证据链 / 跨域线索链 / 跨域证据链 /
  跨域分析链 / 方法论过滤器 / 稽查指令 / 行业对标 / 报告生成 /
  推理引擎 / 知识库 / 自学习 / 联网核查 / 审计

  【7个数据域】
  银行流水 / 销项发票 / 进项发票 / 工资表 / 社保明细 /
  进销存台账 / 合同与凭证

  【16级处理管线】
  文件上传→格式识别→结构化提取→情报抽取→规则扫描→线索链触发→
  证据链收集→跨域交叉验证→行业判定→噪声过滤→审核规则应用→
  行业对标→综合评分→报告生成→纯净度检查→输出交付

═════ 知识库系统（2026-06-30 补录）═════
  存储历史分析经验，支持12维度加权相似度检索，上限500条记忆。
  代码: engine/knowledge_base.py / static/audit_memory.json
  调用位置: pipeline.py → 每次分析结束后自动提取指纹存入知识库

  【记忆指纹】
  每次分析自动提取：行业 + 经营模式 + 信号类型 + 风险评分 → 生成唯一指纹
  存储字段：company_id / industry / biz_model / signals_detected / risk_score /
  findings_summary / timestamp / pipeline_version

  【检索机制】
  12维度加权相似度检索：行业(×3) > 经营模式(×2) > 信号类型(×2) >
  风险等级(×1.5) > 企业规模(×1) > 地域(×0.5) > ...
  检索结果用于：行业对标校准 / 阈值自适应 / 常见信号预警

═════ 法律推理引擎（2026-06-30 补录）═════
  为每条稽查发现匹配对应的法律依据和处罚标准。
  代码: engine/legal_reasoner.py
  调用位置: pipeline.py → 每条finding生成时调用

  【法律条文库】
  覆盖《税收征收管理法》《增值税暂行条例》《企业所得税法》《个人所得税法》
  《发票管理办法》《税务稽查工作规程》等核心税法法规。
  每条条文存储：法条编号 / 完整条文 / 适用场景 / 触发条件 / 处罚标准。

  【推理流程】
  发现类型 → 匹配适用法条 → 判断违法程度（一般/严重/特别严重）→
  输出处罚标准（补税/滞纳金/罚款倍数）→ 附在finding的policy_ref字段中。

═════ 财务分析引擎（2026-06-30 补录）═════
  对资产负债表/利润表/现金流量表执行专业财务分析。
  代码: engine/financial_analyzer.py

  【分析维度】
  偿债能力（流动比率/速动比率/资产负债率）
  营运能力（应收账款周转率/存货周转率/总资产周转率）
  盈利能力（毛利率/净利率/ROE/ROA）
  成长能力（收入增长率/利润增长率/资产增长率）
  现金流量（经营/投资/筹资现金流结构分析）

  【输出格式】
  每个维度输出：企业实际值 / 行业P25/P50/P75基准值 / 偏差方向 / 风险等级

═════ 文件解析引擎（2026-06-30 补录）═════
  三层递进识别：文件指纹匹配 → 关键词打分 → 数据结构分析 → 数据推断兜底。
  代码: main.py → _extract_material_intel()
  支持格式: Excel(.xlsx/.xls) / CSV / PDF(含扫描件)

  【34类文件指纹库】
  覆盖常用稽查资料类型：银行流水/销项发票/进项发票/工资表/社保明细/
  科目余额表/试算平衡表/财务报表/增值税申报表/企业所得税申报表/
  个税申报表/其他税种申报表/进销存台账/合同文件/凭证文件/...
  每类指纹含：表头关键词列表 / 列名模式 / 数据格式特征 / 兼容策略

  【识别流程】
  第一层：表头关键词精确匹配（最快，优先使用）
  第二层：列名+数据格式组合打分（关键词部分命中时启用）
  第三层：纯数据特征推断（完全无表头或表头损坏时启用，最低优先级）

═════ 账套隔离机制（2026-06-30 补录）═════
  多企业数据物理隔离——每个企业独立拥有一套完整的数据库表和文件存储。
  代码: database.py / main.py → 所有数据操作函数

  【数据库隔离】
  32张数据表按 company_id 字段隔离。所有查询/写入/更新/删除操作必须带 company_id 条件。
  删除账套时：32张表级联删除该 company_id 的所有记录。

  【文件存储隔离】
  上传文件存储: static/uploads/tax-risk-docs/{company_id}/ 子目录
  分析缓存: 每个 company_id 独立缓存
  会话管理: sessions.json 中按 company_id 记录当前选中账套

  【Cookie安全】
  前端 cookie: company_id + company_name → initAppFlow 优先读取 → currentCompanyId 全程锁定。

═════ 登录与会话管理（2026-06-30 补录）═════
  个人登录+账套选择+会话持久化，服务器重启不丢失。
  代码: main.py → /api/login /api/logout / sessions.json

  【登录流程】
  用户输入姓名+手机号（必填，中文姓名UTF-8编码）→ 验证通过 →
  写入 sessions.json → 设置 cookie → 跳转账套选择页。

  【账套选择】
  登录后呈现账套列表（按用户关联的company_id过滤）。
  新建账套：公司名称+信用代码 → 创建DB表+文件目录 → 返回选择页。
  删除账套：32表级联删除 + 文件目录完全清除。

  【会话持久化】
  sessions.json 存储所有活跃会话：user_name / phone / company_id / login_time / expire_time。
  服务器重启→读取 sessions.json → 恢复全部会话→用户无需重新登录。

═════ 推理引擎仪表盘（2026-06-30 补录）═════
  引擎的实时状态监控中心，6个标签页覆盖引擎全部运行维度。
  代码: static/js/tax-engine-dashboard.js

  【#1 运行状态】引擎实时状态/内存使用/缓存命中率/最近分析记录
  【#2 规则库】1608条稽查指令按分类浏览/搜索/详情查看
  【#3 质量保障】4条质量标准逐条检查/合规报告生成
  【#4 方法论对账】1266条方法论与audit_chains.json的实时核对
  【#5 跨域协商】29条协商规则四层场景的可视化矩阵
  【#6 智能大脑】调度中枢进度/学习事件/纠正规则库/渐进学习曲线

═════ 前端页面体系（2026-06-30 补录）═════
  系统侧边栏完整模块清单，共17个主要功能页面。
  代码: static/index.html（导航结构）+ static/js/core.js（路由）

  【一级模块（12个）】
  系统看板 / 序时账 / 发票与凭证 / 工资社保 / 财务报表 / 资产管理 /
  合同管理 / 档案管理 / 税务申报 / 资料风险分析 / 推理引擎仪表盘 / 税务AGI

  【二级模块（5个）】
  稽查指令 / 域分析 / 线索链 / 证据链 / 分析链

  【文档模块（5个）】
  税务稽查员手册 / 报告编制要求 / 审核内容模板 / 全链路质量保障体系 / AI行为准则

  【管线模块（5个）】
  文件解析 / 跨域线索链 / 跨域证据链 / 跨域分析链 / 方法论过滤器

═════ 规则编号对照表（2026-06-30）═════
  引擎铁律与AI行为准则的完整对应关系。引擎铁律在本文档中（规则篇），
  AI行为准则在前端页面中（static/js/tax-pipeline-pages.js → renderAiRules）。

  【AI行为准则页面（7条，约束智哥编码行为）】
  #1 做事要狠 | #2 自作主张 | #3 主动进攻
  #4 自行验证 | #8 变更影响分析 | #15 提交前自查 | #16 交付前输出自检

  【引擎铁律 — 规则篇（本文档，约束系统硬逻辑）】
  引擎铁律一：科目name → 写入前查DB（第6章）
  引擎铁律二：三号合并 → 禁止逐条for调用（第6章）
  引擎铁律三：审计铁律 → audit.py 7项全过（第6章）
  引擎铁律四：ref_id去重 → 精确匹配禁模糊（第6章）
  引擎铁律五：普票税额并入成本 → 普票不拆税额（第6章）
  引擎铁律六：7分类禁止兜底 → 不在7分类返回None（第6章）
  引擎铁律七：规则=代码 → 记忆与实现必须一致（第7章）
  引擎铁律八：代码即承诺 → 声称的功能必须代码存在（第7章）
  引擎铁律九：全行业适用 → 禁止行业特化硬编码（第7章）
  引擎铁律十：主动关联更新 → 一处过时全项目同步（第7章）
  引擎铁律十一：方法论先行 → 功能必须先有方法论定义（第7章）
  引擎铁律十二：跨模块内容一致性 → 同一内容多模块出现必须一致（第8章·新增）

═════ 引擎记忆索引（2026-06-30 更新）═════
  ═══ 规则篇 ═══
  01 引擎核心能力宣言与角色边界
  02 行业推断铁律 —— 销项品名=唯一依据
  03 系统稽查判定规则 —— 33条判定规则逐条代码化
  04 缺失的关键信息 —— 回退与推定策略
  05 收款分类规则 —— 12条分类规则+个人识别
  06 账务处理引擎铁律 —— 铁律一至铁律六（6条）
  07 引擎核心铁律 —— 铁律七至铁律十一（5条）
  08 跨模块内容一致性铁律 —— 铁律十二·共享内容映射+四触发同步（新增）
  09 报告呈现规则 —— 12类呈现规范
  10 报告后四章规则 —— 第四到第七章

  ═══ 架构篇 ═══
  11 假设-验证推理引擎 —— 竞争假设+证据验证+加权判决
  12 跨域协商引擎 —— 29条协商规则四层场景
  13 审核反馈闭环 —— 五步闭环+四级回退匹配
  14 联动修改与数据一致性 —— 三种运行模式
  15 方法论过滤器体系 —— 七类过滤规则
  16 模块联动关系矩阵 —— 文档联动+数据联动
  17 四阶段推理管线 —— Phase1-4
  18 调度中枢 —— 16模块/7域/16级管线
  19 知识库系统 —— 500条记忆/12维检索
  20 法律推理引擎 —— 税法条文库+自动化匹配
  21 财务分析引擎 —— 5维度比率分析
  22 文件解析引擎 —— 34类指纹/三层递进
  23 账套隔离机制 —— 32表+文件目录+Cookie
  24 登录与会话管理 —— 个人登录+持久化
  25 推理引擎仪表盘 —— 6个标签页
  26 前端页面体系 —— 17个页面完整清单

═════ 系统文件关联清单（2026-06-30）═════
  引擎记忆（本文档）关联的系统文件——

  【核心引擎】
  engine/pipeline.py（主分析管线，本文档主要引用对象）
  engine/domain_analysis.py（42个域分析函数）
  engine/phase1_triage.py / phase2_deep_dive.py / phase3_cross_validate.py / phase4_synthesis.py
  engine/cross_domain_negotiation.py（跨域协商）
  engine/self_learning.py（审核反馈闭环）
  engine/hypothesis_engine.py（假设验证推理）
  engine/orchestrator.py（调度中枢）
  engine/knowledge_base.py（知识库）
  engine/legal_reasoner.py（法律推理）
  engine/financial_analyzer.py（财务分析）
  engine/methodology_loader.py（方法论加载）
  engine/system_config.py（数据配置）

  【数据与配置】
  static/system_config.json（权威数据源）
  static/audit_chains.json（线索链/证据链/方法论）
  static/correction_rules.json（纠正规则存储）
  static/industry_data.json（25行业产品链词典+12条收款分类规则）
  static/tax_risk_rules_local_export.json（1608条稽查指令）
  static/audit_memory.json（500条分析记忆）
  audit_consistency.py（数据一致性自检+联动修改）

  【前端页面（JS文件）】
  static/js/tax-pipeline-pages.js（管线页面：域分析/线索链/证据链/分析链/方法论过滤器/AI行为准则/质量保障）
  static/js/tax-doc-analysis.js（资料风险分析报告）
  static/js/tax-auditor-handbook.js（税务稽查员手册·12章）
  static/js/tax-report-standards.js（报告编制要求·11节）
  static/js/tax-feedback-template.js（审核内容模板·20场景）
  static/js/tax-engine-dashboard.js（推理引擎仪表盘·6标签页）
  static/js/core.js（全局路由+税务AGI页面）
  static/js/report-block-renderer.js（报告六要素渲染+审核按钮）

  【基础设施】
  main.py（主入口，~25000行，227路由）
  database.py（32表模型+账套隔离）
  start.bat（启动脚本：杀僵尸+清缓存+审计+启动）
  sessions.json（会话持久化）
  static/index.html（侧边栏导航+JS加载）
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


# ═══════════════════════════════════════════════
#  域分析通用关键词配置（全行业自适应）
#  所有硬编码关键词从此处统一管理，不再分散在 domain_analysis.py 中
# ═══════════════════════════════════════════════

# 经营费用要素关键词 — _domain_business_substance
BIZ_EXPENSE_KEYWORDS = {
    "租赁": ["租金","租赁","房租","场地","物业费-房租"],
    "水电": ["电费","水费","电","水","自来水","供电","用水"],
    "物业": ["物业","物管","管理费-物业","物业管理"],
    "通信": ["通信","网络","宽带","电话","电信","移动","联通"],
    "物流": ["快递","物流","运输","配送","货运","快运"],
    "办公": ["办公用品","文具","打印","复印","墨盒","硒鼓","纸张"],
    "维修": ["维修","维护","保养","修缮","修理"],
    "安保": ["保安","安保","门卫","监控","消防"],
}

# 银行流水交易类型映射 — _domain_business_substance
BANK_KW_MAP = {
    "租赁": ("房租","租金","租赁","场地费"),
    "水电": ("电费","水费","自来水"),
    "物业": ("物业费","物管费"),
    "工资": ("工资","代发","薪"),
}

# 服务行业代码兜底 — _is_service_industry
SERVICE_CODES_FALLBACK = [
    "广告服务","信息技术服务","研发和技术服务","文化创意服务",
    "物流辅助服务","鉴证咨询服务","广播影视服务","商务辅助服务",
    "金融服务","现代服务","生活服务","电信服务","建筑服务",
    "教育服务","医疗服务","旅游服务","娱乐服务","餐饮服务",
    "居民日常服务","其他现代服务","经纪代理服务","人力资源服务",
    "安全保护服务","会议展览服务","租赁服务","无形资产",
]

# 服务类品名排除词 — 进销存/毛利率分析
SERVICE_EXCLUDE_KEYWORDS = [
    "服务费","服务","咨询","设计","广告","策划","制作","推广",
    "租赁","维修","维护","运输","配送","快递","物流",
    "培训","会议","展览","软件","会员","预付卡","充值",
]

# 发票深度特征敏感关键词 — _domain_invoice_deep
SENSITIVE_INVOICE_KEYWORDS = [
    "咨询","服务费","技术","设计","广告","推广","策划",
]

# 供应商异常名称检测模式 — _domain_supplier_deep
SUPPLIER_ABNORMAL_PATTERNS = {
    "min_name_length": 3,
    "mask_chars": ["***", "..."],
}


# ═══════════ 域→规则自动映射 (RULE_DOMAIN_MAP) ═══════════
# 用途: _auto_assign_rule_ids() 根据域名称自动为发现分配 rule_id
# 格式: "域名称": ["规则分类1", "规则分类2", ...]
# 维护: 新增域分析函数时在此处添加映射条目
RULE_DOMAIN_MAP = {
    "CIT汇算清缴": ["企业所得"],
    "业务费用分析": ["成本费用"],
    "个人交易检测": ["资金流", "个税"],
    "主营业务成本识别": ["成本费用"],
    "付款分析": ["资金流"],
    "代扣代缴分析": ["个税", "税务合规"],
    "企业所得税分析": ["企业所得", "税务合规"],
    "供应商客户重叠检测": ["关联交易", "关联风险"],
    "供应商穿透分析": ["关联交易", "关联风险", "虚开风险"],
    "出口退税验证": ["出口退税"],
    "加工费分析": ["成本费用", "经营实质"],
    "印花税检查": ["财产行为税"],
    "发票深度特征": ["发票流", "虚开风险"],
    "合同交叉对比": ["合同风险"],
    "合同清单分析": ["合同风险"],
    "固定资产分析": ["资产负债", "财产行为税"],
    "增值税分析": ["增值税", "税务合规"],
    "客户三源穿透": ["关联交易", "虚开风险"],
    "客户分析": ["关联交易", "关联风险"],
    "工资社保公积金三方对比": ["薪酬社保"],
    "收入时间线分析": ["收入确认", "跨期调节"],
    "收款来源分类": ["资金流"],
    "文件解析": ["资料完备"],
    "社保公积金分析": ["薪酬社保"],
    "税收优惠分析": ["企业所得", "税务合规"],
    "经营实质分析": ["经营实质", "经营穿透"],
    "经营费用与规模匹配": ["经营实质"],
    "经营费用完整性": ["成本费用", "经营实质"],
    "薪酬分析": ["薪酬社保", "个税"],
    "行业对标分析": ["行业对标"],
    "规则全覆盖验证": ["跨域推理"],
    "资产折旧分析": ["资产负债"],
    "资料完备度检测": ["资料完备"],
    "资金全链路追踪": ["资金流"],
    "资金流向分析": ["资金流"],
    "跨域关联推理": ["跨域推理"],
    "跨域分析链": ["跨域推理"],
    "跨域线索链": ["跨域推理"],
    "跨域证据链": ["跨域推理"],
    "进销匹配分析": ["进销存", "发票匹配"],
    "进销品名交叉映射": ["进销存", "虚开风险"],
    "进销存分析": ["进销存"],
    "进销存实物分析": ["进销存"],
    "进销毛利率分析": ["进销存", "行业对标"],
    "进项发票分析": ["发票流", "发票合规", "发票匹配"],
    "银行流水画像": ["资金流"],
    "销项发票分析": ["发票流", "发票合规", "发票匹配"],
}

# ═══════════════════════════════════════════════════════════════
# 可抵扣进项税额的扣税凭证（全国统一，全行业通用）
# ═══════════════════════════════════════════════════════════════
# 依据：《增值税暂行条例》第八条、财税[2016]36号、国家税务总局公告2019年第31号等
# 只有以下凭证上注明的增值税额，才能从销项税额中抵扣。
# 增值税普通发票（含电子普票）不可抵扣进项税额，税额应当并入采购成本或费用。
VAT_DEDUCTIBLE_VOUCHER_TYPES = {
    "增值税专用发票": {
        "code": "vat_special",
        "description": "增值税专用发票（含机动车销售统一发票），需在360天内认证或勾选确认",
        "typical_rate": "0.13/0.09/0.06",
        "legal_basis": "《增值税暂行条例》第八条第（一）项",
    },
    "海关进口增值税专用缴款书": {
        "code": "customs_payment",
        "description": "从海关取得的海关进口增值税专用缴款书，需在360天内采集比对",
        "typical_rate": "0.13/0.09",
        "legal_basis": "《增值税暂行条例》第八条第（二）项",
    },
    "农产品收购发票或销售发票": {
        "code": "agri_invoice",
        "description": "向农业生产者个人收购自产农产品时开具的收购发票，按买价×扣除率计算抵扣",
        "typical_rate": "0.09/0.10（深加工加计1%）",
        "legal_basis": "《增值税暂行条例》第八条第（三）项",
    },
    "代扣代缴税收缴款凭证": {
        "code": "withholding_voucher",
        "description": "从境外单位或个人购进服务/无形资产/不动产时代扣代缴增值税的完税凭证",
        "typical_rate": "0.06/0.13",
        "legal_basis": "财税[2016]36号附件1第二十五条",
    },
    "收费公路通行费增值税电子普通发票": {
        "code": "toll_elec_invoice",
        "description": "纳税人支付的道路通行费，取得收费公路通行费增值税电子普通发票",
        "typical_rate": "0.03/0.05（简易计税）",
        "legal_basis": "财税[2017]90号、交通运输部公告2020年第24号",
    },
    "国内旅客运输服务增值税电子普通发票": {
        "code": "travel_elec_invoice",
        "description": "购进国内旅客运输服务取得的增值税电子普通发票，按发票注明税额抵扣",
        "typical_rate": "0.03/0.09",
        "legal_basis": "国家税务总局公告2019年第31号",
    },
    "航空运输电子客票行程单": {
        "code": "airline_itinerary",
        "description": "航空运输电子客票行程单，按（票价+燃油附加费）÷(1+9%)×9%计算抵扣",
        "typical_rate": "0.09（计算抵扣）",
        "legal_basis": "国家税务总局公告2019年第31号",
    },
    "铁路车票": {
        "code": "railway_ticket",
        "description": "注明旅客身份信息的铁路车票，按票面金额÷(1+9%)×9%计算抵扣",
        "typical_rate": "0.09（计算抵扣）",
        "legal_basis": "国家税务总局公告2019年第31号",
    },
    "公路、水路等其他客票": {
        "code": "other_transport_ticket",
        "description": "注明旅客身份信息的公路、水路等其他客票，按票面金额÷(1+3%)×3%计算抵扣",
        "typical_rate": "0.03（计算抵扣）",
        "legal_basis": "国家税务总局公告2019年第31号",
    },
    # ═══ 以下为特殊扣税凭证（由用户补充，2026-06-30）═══
    "加计扣除农产品进项税额": {
        "code": "agri_additional",
        "description": "纳税人购进用于生产或委托加工13%税率货物的农产品，按照10%的扣除率计算进项税额（9%+加计1%）",
        "typical_rate": "0.10（9%+加计1%）",
        "legal_basis": "《增值税暂行条例》第八条第（三）项、财税[2017]37号",
    },
    "购建不动产的扣税凭证": {
        "code": "real_estate_voucher",
        "description": "纳税人取得不动产或者不动产在建工程的进项税额，应按规定分期抵扣或一次性抵扣（2019年4月1日后取得的不动产可一次性全额抵扣）",
        "typical_rate": "0.09/0.05（按取得时间适用不同政策）",
        "legal_basis": "国家税务总局公告2019年第39号、财税[2016]36号",
    },
    "外贸企业进项税额抵扣证明": {
        "code": "foreign_trade_cert",
        "description": "外贸企业出口货物转内销时，经税务机关核定的进项税额抵扣证明，用于抵扣内销货物的销项税额",
        "typical_rate": "0.13/0.09（按原进项税率）",
        "legal_basis": "《出口货物退（免）税管理办法》、国家税务总局相关公告",
    },
}

# ═══════════════════════════════════════════════════════════════
# 进项税额转出规则（凭证类型可抵扣但用途不可抵扣的情形）
# ═══════════════════════════════════════════════════════════════
# 依据：《增值税暂行条例》第十条、财税[2016]36号附件1第二十七条
# ⚠ 特别警示：即使取得了可抵扣的扣税凭证（如增值税专用发票），
# 如果购进货物/服务用于以下不得抵扣项目，必须做进项税额转出处理！
# 这是稽查最常发现的问题——企业以为有专票就能抵，实则不然。
VAT_INPUT_TAX_REVERSAL_RULES = {
    "description": "以下项目即使取得了增值税专用发票等扣税凭证，其进项税额也不得从销项税额中抵扣，已抵扣的必须做进项税额转出",
    "legal_basis": "《增值税暂行条例》第十条、《营业税改征增值税试点实施办法》（财税[2016]36号附件1）第二十七条",
    "non_deductible_uses": [
        {
            "item": "个人消费",
            "examples": ["高档烟酒", "奢侈品", "个人日用品", "私家车加油维修（非生产经营用）"],
            "keywords": ["个人", "自用", "私用", "私家"],
            "rule": "用于个人消费的购进货物、服务，即使取得增值税专用发票，进项税额也不得抵扣",
        },
        {
            "item": "业务招待",
            "examples": ["招待用酒", "餐饮招待", "娱乐消费", "商务宴请", "高档茶叶"],
            "keywords": ["招待", "宴请", "餐饮", "娱乐", "酒", "茶", "礼品"],
            "rule": "用于业务招待的购进货物（烟酒、餐饮、娱乐等），即使取得增值税专用发票，进项税额必须转出",
        },
        {
            "item": "集体福利",
            "examples": ["员工福利物品", "节日礼品", "员工旅游", "团建活动", "食堂采购"],
            "keywords": ["福利", "员工", "团建", "食堂", "工会", "旅游", "聚餐"],
            "rule": "用于集体福利或个人消费的购进货物，即使取得增值税专用发票，进项税额必须转出",
        },
        {
            "item": "免税项目",
            "examples": ["免税农产品", "免税技术服务", "免税教育"],
            "keywords": ["免税", "零税率"],
            "rule": "用于免征增值税项目的购进货物，其进项税额不得抵扣",
        },
        {
            "item": "简易计税项目",
            "examples": ["简易计税方法下的购进货物和服务"],
            "keywords": ["简易计税", "简易征收"],
            "rule": "用于简易计税方法计税项目的进项税额不得抵扣",
        },
        {
            "item": "非正常损失",
            "examples": ["因管理不善造成货物被盗、丢失、霉烂变质", "违反法律法规被没收、销毁"],
            "keywords": ["被盗", "丢失", "霉烂", "销毁", "没收", "毁损"],
            "rule": "非正常损失的购进货物及相关的加工修理修配劳务和交通运输服务，进项税额必须转出",
        },
        {
            "item": "贷款服务",
            "examples": ["贷款利息", "投融资顾问费", "手续费"],
            "keywords": ["贷款", "利息", "融资", "投融"],
            "rule": "购进的贷款服务进项税额不得抵扣（无论取得何种凭证）",
        },
    ],
    "detection_guidance": "稽查重点：①检查增值税专用发票中品名为'酒''茶叶''礼品''餐饮''旅游'等项目的进项税额是否已做转出；②检查管理费用-业务招待费科目对应的进项税额是否转出；③检查应付职工薪酬-福利费科目对应的进项税额是否转出",
}

# ═══════════════════════════════════════════════════════════════
# 进项税额转出的上下文豁免规则（关键词触发 ≠ 必须转出！）
# ═══════════════════════════════════════════════════════════════
# 引擎学习要点（2026-06-30 老邓亲授）：
# 同一个品名关键词，在不同企业类型、不同用途下，抵扣结果完全不同。
# 引擎必须做"企业画像 → 品名 → 用途"三要素综合判定，而非简单关键词匹配。
# 
# 例如：
#   "酒" → 餐饮企业买入料酒作烹饪调料 → ✅可抵扣（生产经营用）
#   "酒" → 酒厂买入原酒作原材料 → ✅可抵扣（直接用于生产）
#   "酒" → 化工企业买入酒精作燃料 → ✅可抵扣（生产经营消耗）
#   "酒" → 贸易公司买入茅台招待客户 → ❌不可抵扣（业务招待）
#   "酒" → 任何企业买入红酒发员工福利 → ❌不可抵扣（集体福利）
#
# 同样的品名"酒"，四种完全不同的税务处理！
# 引擎必须学会：先看企业是谁，再看用来干什么，最后做判定。
VAT_CONTEXTUAL_REVERSAL_OVERRIDES = {
    "description": "关键词触发了进项税额转出嫌疑，但以下上下文可豁免——引擎的'二次思考'机制",
    "principle": "企业画像 + 品名 + 用途 → 三要素综合判定，而非单一关键词匹配",
    
    "overrides": [
        {
            "keyword": "酒",
            "trigger_suspicion": "业务招待/集体福利嫌疑",
            "exempt_when": [
                {
                    "condition": "餐饮企业 + 品名为料酒/黄酒/啤酒/白酒 + 入原材料或主营业务成本",
                    "reason": "餐饮企业购酒作为烹饪调料或销售商品，属于生产经营用，可抵扣进项税额",
                    "enterprise_types": ["餐饮", "酒店", "食品", "住宿"],
                    "account_keywords": ["原材料", "主营业务成本", "库存商品", "生产成本"],
                },
                {
                    "condition": "酒类生产企业 + 品名为原酒/基酒/酒精 + 入原材料或半成品",
                    "reason": "酒厂买入酿酒原料或半成品，直接用于生产应税货物，可抵扣进项税额",
                    "enterprise_types": ["酒", "酿酒", "食品制造", "饮料"],
                    "account_keywords": ["原材料", "半成品", "生产成本", "委托加工物资"],
                },
                {
                    "condition": "化工/制药企业 + 品名为酒精/乙醇 + 入原材料或制造费用",
                    "reason": "化工/制药企业买入酒精作溶剂、燃料或生产原料，属于生产经营消耗",
                    "enterprise_types": ["化工", "制药", "生物", "电子", "印刷", "新能源"],
                    "account_keywords": ["原材料", "制造费用", "辅助材料", "燃料"],
                },
                {
                    "condition": "商贸企业批量采购酒类 + 入库存商品",
                    "reason": "商贸企业采购酒类作为待售商品（非自用），属于正常的商品采购，可抵扣进项税额",
                    "enterprise_types": ["贸易", "商贸", "批发", "零售", "电商"],
                    "account_keywords": ["库存商品", "在途物资", "采购"],
                },
            ],
            "note": "如果以上豁免条件均不满足（如：贸易公司单瓶购买茅台、任何企业购买红酒发放员工等），则维持进项税额转出判定",
        },
        {
            "keyword": "茶叶",
            "trigger_suspicion": "业务招待/个人消费嫌疑",
            "exempt_when": [
                {
                    "condition": "茶叶/茶饮企业 + 品名含茶叶 + 入原材料或库存商品",
                    "reason": "茶叶企业买入茶叶作为生产原料或待售商品，属于生产经营用",
                    "enterprise_types": ["茶", "食品", "饮料", "商贸", "零售"],
                    "account_keywords": ["原材料", "库存商品", "主营业务成本"],
                },
            ],
        },
        {
            "keyword": "礼品",
            "trigger_suspicion": "业务招待/赠送客户嫌疑",
            "exempt_when": [
                {
                    "condition": "商贸/零售企业 + 批量采购 + 品名为礼品/促销品 + 入库存商品或销售费用-促销费",
                    "reason": "商贸企业采购促销赠品附赠给客户，属于正常的营销支出（视同销售），可抵扣进项税额",
                    "enterprise_types": ["贸易", "商贸", "零售", "电商", "批发"],
                    "account_keywords": ["库存商品", "销售费用", "促销", "宣传", "推广"],
                    "note": "⚠ 同时需确认是否已做视同销售的销项税额处理",
                },
            ],
        },
        {
            "keyword": "餐饮",
            "trigger_suspicion": "业务招待嫌疑",
            "exempt_when": [
                {
                    "condition": "餐饮/酒店企业 + 采购食材/原料 + 入原材料或主营业务成本",
                    "reason": "餐饮企业的食材采购属于正常生产经营成本，可抵扣进项税额",
                    "enterprise_types": ["餐饮", "酒店", "食品"],
                    "account_keywords": ["原材料", "主营业务成本", "食材"],
                },
                {
                    "condition": "任何企业 + 差旅费中的员工工作餐 + 入差旅费或管理费用（非招待费）",
                    "reason": "员工因公出差的工作餐不属于业务招待，但需有出差审批和差旅报销单佐证",
                    "enterprise_types": ["*"],  # 全行业适用
                    "account_keywords": ["差旅费", "管理费用-差旅"],
                    "note": "需出差审批单+差旅报销单佐证，否则仍按招待费处理",
                },
            ],
        },
        {
            "keyword": "旅游",
            "trigger_suspicion": "集体福利/个人消费嫌疑",
            "exempt_when": [
                {
                    "condition": "旅游/会展企业 + 采购旅游服务/门票 + 入主营业务成本",
                    "reason": "旅游企业采购旅游服务作为其经营产品再销售，属于正常经营成本",
                    "enterprise_types": ["旅游", "旅行社", "会展", "酒店"],
                    "account_keywords": ["主营业务成本", "旅游服务", "门票"],
                },
            ],
        },
        {
            "keyword": "利息",
            "trigger_suspicion": "贷款服务不可抵扣嫌疑",
            "exempt_when": [
                {
                    "condition": "金融企业 + 利息收入为主营业务 + 相关的融资成本",
                    "reason": "金融企业的融资成本属于正常经营支出（但贷款服务本身的进项仍不可抵扣——这是硬性规定。此处指金融企业作为借款方支付给其他金融机构的利息，该利息支出的进项税额按现行税法仍不可抵扣。引擎保留此条作为特殊情况记录待税法修正。）",
                    "enterprise_types": ["银行", "金融", "保险", "证券"],
                    "account_keywords": [],
                    "note": "现行税法下贷款服务进项一律不可抵扣，此为硬性规定，不支持任何豁免。引擎记录此条作为与用户的讨论备忘。",
                    "override_allowed": False,  # 硬性规定，不可豁免
                },
            ],
        },
    ],
    
    "engine_learning_note": (
        "这是引擎的'二次思考'机制——"
        "第一轮用关键词快速筛查风险信号（宁可错杀不可放过），"
        "第二轮结合企业画像和会计科目进行上下文分析，"
        "排除误判后给出终审结论。"
        "引擎记录了老邓2026-06-30的教导：同一个'酒'字，在餐饮店是调料，在酒厂是原料，在化工厂是燃料，在贸易公司才可能是招待费。"
    ),
}

# 不可抵扣进项税额的发票类型（必须明确排除，税额应并入成本/费用）
VAT_NON_DEDUCTIBLE_TYPES = [
    "增值税普通发票",
    "增值税电子普通发票（非通行费/旅客运输类）",
    "定额发票",
    "通用机打发票",
    "其他普通发票",
]

# [引擎自更新 2026-07-01] 引擎记忆关键词词典更新：制造业/贸易型企业通过委托加工实现进销品名转化是常见模式。当进销品名不匹配+同时存在合理加工费→降低升级等级→同时检查加工链条真实性。（行业:，置信度:80%）
