# 数据驱动——所有数量从 system_config.json 动态读取
# [合并自system_config.py] · 2026-07-08: 改为从 system_config.json 动态加载
import json, os

def _load_config():
    """从 system_config.json 加载权威数据——不再硬编码"""
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'static', 'system_config.json')
    try:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        return cfg
    except Exception:
        # 回退：保守默认值
        return {"rules_count": 1608, "clue_chains": 437, "evidence_chains": 781,
                "analysis_chains": 48, "total_chains": 1266, "domain_functions": 39}

_CFG = _load_config()
rules_count = _CFG.get("rules_count", 1608)
clue_chains = _CFG.get("executable_clues", _CFG.get("clue_chains", 437))
evidence_chains = _CFG.get("evidence_chains", 781)
methodology_count = _CFG.get("methodology_count", 0)
total_chains = _CFG.get("total_chains", 1266)
domain_functions = _CFG.get("domain_functions", 39)

"""
税务合规引擎记忆系统 — 历史分析经验积累与检索

=== 政策引用标准（铁律） ===
税务合规以现行有效法律法规为唯一引用依据。以下政策映射为系统强制规则：
1. 《增值税暂行条例》(1993版/2008修订/2017修订) → 已废止，全部替换为《中华人民共和国增值税法》(2024年1月1日起施行)
2. 《增值税暂行条例实施细则》 → 已废止，全部替换为《中华人民共和国增值税法实施条例》
3. 政策引用以国家税务总局官网(www.chinatax.gov.cn)公告栏最新版本为准
4. 任何生成"政策引用"的代码必须使用上述最新名称，不得使用历史名称

代码实现：engine/legal_reasoner.py 负责政策引用和法条匹配

═════ 引擎核心能力宣言与角色边界 ═════
  本引擎具备六项核心智能能力，全部为可运行代码而非纸上设计。
  引擎（memory.py中的硬逻辑）= 系统做什么 | 智哥（AI行为准则页面）= 怎么写代码

  🧠【有记忆】知识库系统 → static/audit_memory.json，上限500条，12维加权检索
  📚【能学习】审核反馈闭环 → user_corrections.json → 四级回退匹配 → 自进化
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

═════ 系统税务合规判定规则（2026-06-28 老邓亲授，写入引擎记忆）═════

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
  7. 每条发现是否包含五段税务合规叙事？（规则十二、二十一）
  8. 证据数据是否完整渲染？（规则十三）
  9. 报告是否遵循7章标准格式？（规则十四）
  10. 报告是否纯净（无内部标签/按钮/系统参数）？（规则十五、十九）
  11. 税务合规术语是否正确（税务合规性质/事实 vs 违法性质/事实）？（规则十八）
  12. 第二章是否详细化（7段2000字以上+实时数据）？（规则二十）
  13. 同类风险是否已合并展示（同type合并+子项列示）？（规则二十五）
  14. 报告段落是否独立舒展（禁止多逻辑挤在一段、禁止一逗到底）？（规则二十六）
  15. 收款分类是否配置驱动（JSON规则+双字段匹配+零值隐藏+兜底标注）？（规则二十八）
  16. 报告是否存在任何数据截断（经营范围/证据明细/分析步骤/发现描述）？（规则三十）
  上述16项全部通过 + 五项核心能力全部达标，本次分析才算可靠。

【规则十二：税务合规过程叙事】
  每条发现必须包含五段税务合规叙事，将税务合规过程写得明明白白、通俗易懂：
  ① 📌 发现要点——通俗描述这个风险是什么，外行也能看懂
  ② 📡 线索获取——从哪些数据源、通过什么方法锁定了异常
  ③ 🔬 分析过程——展开证据链调查步骤（≥3步），无证据链时自动生成4步默认路径
  ④ 📋 证据组织——证据记录数量、交叉验证方式、证据闭环状态
  ⑤ 💡 通俗理解——用关键数据（偏差比率/涉及金额）解释问题严重性
  叙事基于finding实际字段，每段必须通俗易懂让被查单位也能理解
  代码: static/js/tax-doc-analysis.js _renderReportFallback() 税务合规过程叙事段
  规范: static/js/tax-report-standards.js 第三章·附

【规则二十一：第三章六要素+叙事标准】
  第三章每条发现的标准呈现结构：
  税务合规过程叙事（五段）→ 六要素格式（税务合规性质/税务合规事实/证据材料/证据来源/法律依据/处理建议）→ 关联证据链标签
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
  第三章每条发现按六要素呈现：税务合规性质→税务合规事实→证据材料→证据来源→法律依据→处理建议
  注意：税务合规报告尚未进入法律裁决阶段，使用"税务合规性质/税务合规事实"而非"违法性质/违法事实"
  禁止使用简化版或内部调试版格式（如blocks渲染器）
  代码: static/js/tax-doc-analysis.js _renderReportFallback()
  规范: static/js/tax-report-standards.js

【规则十五：报告纯净度】
  正式报告中禁止出现以下内容：
  - 驳回按钮/审查面板（审查面板应独立于报告之外，折叠显示）
  - 内部技术标签（Synthesis:/Causal:/[AGI]/[Phase]等中英混杂前缀）
  - 税务合规行为准则/税务合规方法论演进（属于系统内部文档）
  - 系统自诊/修正记录（属于引擎内部工作日志）
  代码: static/js/tax-doc-analysis.js 文本清理逻辑

【规则十六：审查驳回学习闭环】
  税务合规员通过审查面板驳回某条发现 → 引擎记录驳回（finding_type + action:dismiss）
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

【规则十八：税务合规术语规范】
  报告用语必须体现"税务合规发现"而非"法律定性"立场：
  正确：税务合规性质/税务合规事实/税务合规发现/涉嫌/存疑/提示风险
  禁止：违法性质/违法事实/违法行为/确定/认定
  原因：税务合规报告阶段尚未进入裁决程序，不得预判法律结论
  代码: static/js/tax-doc-analysis.js 六要素渲染

【规则十九：报告机密保护】
  正式报告（给被查单位/税务机关）禁止暴露系统内部信息：
  - 引擎架构（52步流程/模块数量/阶段名称）
  - 系统能力参数（规则数/线索链数/证据链数）
  - 质量自检清单（全链路闭环打勾）
  - 引擎内部日志（系统自诊/修正记录）
  - 内部文档（税务合规行为准则/方法论演进）
  - 技术标签（Synthesis:/Causal:/[AGI]/[Phase]等前缀）
  原则：报告只呈现税务合规结论和依据，不暴露内部实现
  代码: static/js/tax-doc-analysis.js 移除renderAnalyzeHeader调用

【规则二十：第二章税务合规实施详细化】
  第二章必须按7段2000字以上详细叙述：
  ①资料审阅(四方验证+文件明细表) ②身份锚定(逐行比对+三层分类)
  ③行业判定(金税编码+三层闸门) ④资金核对(收/付两端+方法论约束)
  ⑤穿透分析(供/客/人/关联四项) ⑥行业对标(跳过/适用说明)
  ⑦综合分析(全链路执行顺序)
  每段必须基于实际数据动态生成，不硬编码固定模板
  代码: static/js/tax-doc-analysis.js _renderReportFallback() Ch2

═════ 报告后四章规则（2026-06-28 新增）═════

【规则二十二：第四章税务合规结论详细化】
  第四章必须包含五个结论段落：
  ① 风险分布表——四级风险(极高/高/中/低)各列数量/占比/代表事项
  ② 证据链完整性——跨域交叉验证覆盖范围、核心证据闭环构成
  ③ 税务合规局限性声明——如实列出因资料缺失无法确认的事项（缺什么报什么）
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
  ⑤ 兜底类别标注"待分析"提示税务合规员关注
  ⑥ 覆盖全行业12+收款场景：税费返还/银行内部/股东注资/关联往来/借款/保证金/第三方支付/政府补贴/保险理赔/资产处置/企业客户/个人待分析
  ⑦ 纠错验证——分类后自问。三信息综合分析(对方户名+摘要+交易附言)，不能只看单一字段。常识判断：<20元有零有整且文本全空→银行利息
  代码: engine/domain_analysis.py 收款构成段+纠错验证段，配置: static/industry_data.json

【规则二十九：六员跨企业比对】
  税务合规必须执行六员（法定代表人/董事/监事/财务负责人/股东/经理）跨企业比对：
  ① 一人多角检测——同一人是否在本企业兼任多个角色
  ② 跨企业人员重叠——本企业六员是否同时在其他企业任职
  ③ 供应链交叉比对——供应商/客户的六员与本企业六员逐名比对→重叠=关联交易
  ④ 触发连锁税务合规点——六员重叠+购销交易→关联交易→购销闭环→虚开发票
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
  铁律：宁可报告长，不可漏一字。税务合规不放过任何一个细节。
  代码: static/js/tax-doc-analysis.js 所有 .substring()/.slice() 均应移除

【规则三十一：报告通用方法论标准（2026-06-24 老邓亲授）】

  原则〇：先想为什么，再学怎么做，永远是全行业各企业通用
  - 每次改动不是在修一个公司的Bug，是在建立全行业通用的标准
  - 接到改动指令时，第一反应不是"改哪行代码"，而是思考：
    1. 这个改动背后的税务合规逻辑是什么？（WHY）
    2. 这个逻辑是否脱离当前公司仍然成立？（通用性检验）
    3. 如果成立，代码必须写成行业自适应，不能硬编码当前公司的特征（HOW）

  原则一：发票明细必须完整、统一、可核查
  - 11列标准（全行业通用）：对方公司名称、品名、规格、单位、数量、金额、税额、价税合计、日期、发票类型、发票号
  - WHY：这是税务合规的"最小完整信息集"——回答谁、什么东西、多少数量、多少钱、什么时候、什么票种
  - HOW：后端 _extract_material_intel() 构建字典，前端附件二渲染表格，后端/前端字段名必须一致
  - 无论纺织厂/建筑公司/软件公司/餐饮店，这11列都是审计底稿的必备字段

  原则二：进项发票必须三层分类，不能一刀切
  - 三层分类（全行业通用）：core_cost_invs → major_expense_invs → minor_expense_invs
  - WHY：进项发票里混着原材料、加工费、加油票、差旅费。不分类就做分析=用所有进项去匹配销项，结论必然失真
  - HOW：identify_main_biz_cost(pur_invs, sal_invs) 通过品名关键词匹配实现三层分类
  - 报告叙述必须分别说明：主营业务收入发票（销项）→ 主营业务成本发票（进项core）→ 重大费用发票（进项major）

  原则三：资金流与发票流必须双向四象限核对
  - 四象限：银行收款 vs 销项发票 / 银行付款 vs 进项发票
  - WHY："资金流与发票流核对法"的方法名称本身就要求双向，只做单向是残缺的
  - HOW：报告第3段叙述 = "将银行收款金额与销项开票金额、银行付款金额与进项发票金额逐户比对"
  - 税费支出是税款缴纳，不属于发票流核对范畴，不应混入该段

  原则四：报告叙述的结构化表达
  - 任何涉及"X张发票Y元"的叙述，必须同时给出分类拆解
  - 例："销项发票51张804万元（即主营业务收入发票），进项发票120张736万元，其中主营业务成本发票68张612万元、重大费用发票9张74万元"
  - 不允许仅写"进项发票120张"而不说明构成

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
  存储: static/user_corrections.json → 按"发现类型|行业|经营模式"生成唯一指纹

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

  第三步 — 税务合规重点保护（12类强制保留）
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
  规则数量 → 税务合规指令/引擎仪表盘/AGI/memory.py
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
  跨域分析链 / 方法论过滤器 / 税务合规指令 / 行业对标 / 报告生成 /
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
  为每条税务合规发现匹配对应的法律依据和处罚标准。
  代码: engine/legal_reasoner.py
  调用位置: pipeline.py → 每条finding生成时调用

  【法律条文库】
  覆盖《税收征收管理法》《中华人民共和国增值税法》《企业所得税法》《个人所得税法》
  《发票管理办法》《税务合规工作规程》等核心税法法规。
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
  覆盖常用税务合规资料类型：银行流水/销项发票/进项发票/工资表/社保明细/
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
  【#2 规则库】1825条税务合规指令按分类浏览/搜索/详情查看
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
  税务合规指令 / 域分析 / 线索链 / 证据链 / 分析链

  【文档模块（5个）】
  税务合规员手册 / 报告编制要求 / 审核内容模板 / 全链路质量保障体系 / AI行为准则

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

  【引擎铁律详细解释】
  
  铁律一·科目name：Account表name字段只存本级名称。写入JournalEntry.account_name前必须查Account表以DB实际值为准，不能直接用代码中的映射值。WHY: 代码中的映射可能与DB不同步，产生数据不一致。
  
  铁律二·三号合并：同一(invoice_code, invoice_no, digital_invoice_no)必须合并为一个凭证号。auto_generate_*_journal必须批量调用，禁止逐条for循环逐个传ID（会绕过三号分组）。WHY: 同一张发票的三个号码必须指向同一凭证。
  
  铁律四·ref_id去重：去重用ref_id == tx.id精确匹配，禁止金额模糊匹配。WHY: 1002存贷方并非借方金额，永远对不上。
  
  铁律五·普票税额并入成本：普通发票税额不单独记进项税额(221001002)，并入成本/费用借方。WHY: 普票不可抵扣，税额应计入采购成本。
  
  铁律六·7分类禁止兜底：CATEGORY_ACCOUNT_MAP严格限定7个分类，不在其中返回None跳过，禁止关键词兜底和默认660299。WHY: 不存在的分类强行映射会导致科目归类错误。

═════ 引擎记忆索引（2026-06-30 更新）═════
  ═══ 规则篇 ═══
  01 引擎核心能力宣言与角色边界
  02 行业推断铁律 —— 销项品名=唯一依据
  03 系统税务合规判定规则 —— 33条判定规则逐条代码化
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
  engine/domain_analysis.py（39个域分析函数）
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
  static/user_corrections.json（纠正规则存储）
  static/industry_data.json（25行业产品链词典+12条收款分类规则）
  static/tax_risk_rules_local_export.json（1825条税务合规指令）
  static/audit_memory.json（500条分析记忆）
  audit_consistency.py（数据一致性自检+联动修改）

  【前端页面（JS文件）】
  static/js/tax-pipeline-pages.js（管线页面：域分析/线索链/证据链/分析链/方法论过滤器/AI行为准则/质量保障）
  static/js/tax-doc-analysis.js（资料风险分析报告）
  static/js/tax-auditor-handbook.js（税务合规员手册·12章）
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
# 依据：《中华人民共和国增值税法》第八条、财税[2016]36号、国家税务总局公告2019年第31号等
# 只有以下凭证上注明的增值税额，才能从销项税额中抵扣。
# 增值税普通发票（含电子普票）不可抵扣进项税额，税额应当并入采购成本或费用。
VAT_DEDUCTIBLE_VOUCHER_TYPES = {
    "增值税专用发票": {
        "code": "vat_special",
        "description": "增值税专用发票（含机动车销售统一发票），需在360天内认证或勾选确认",
        "typical_rate": "0.13/0.09/0.06",
        "legal_basis": "《中华人民共和国增值税法》第八条第（一）项",
    },
    "海关进口增值税专用缴款书": {
        "code": "customs_payment",
        "description": "从海关取得的海关进口增值税专用缴款书，需在360天内采集比对",
        "typical_rate": "0.13/0.09",
        "legal_basis": "《中华人民共和国增值税法》第八条第（二）项",
    },
    "农产品收购发票或销售发票": {
        "code": "agri_invoice",
        "description": "向农业生产者个人收购自产农产品时开具的收购发票，按买价×扣除率计算抵扣",
        "typical_rate": "0.09/0.10（深加工加计1%）",
        "legal_basis": "《中华人民共和国增值税法》第八条第（三）项",
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
        "legal_basis": "《中华人民共和国增值税法》第八条第（三）项、财税[2017]37号",
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
# 依据：《中华人民共和国增值税法》第十条、财税[2016]36号附件1第二十七条
# ⚠ 特别警示：即使取得了可抵扣的扣税凭证（如增值税专用发票），
# 如果购进货物/服务用于以下不得抵扣项目，必须做进项税额转出处理！
# 这是税务合规最常发现的问题——企业以为有专票就能抵，实则不然。
VAT_INPUT_TAX_REVERSAL_RULES = {
    "description": "以下项目即使取得了增值税专用发票等扣税凭证，其进项税额也不得从销项税额中抵扣，已抵扣的必须做进项税额转出",
    "legal_basis": "《中华人民共和国增值税法》第十条、《营业税改征增值税试点实施办法》（财税[2016]36号附件1）第二十七条",
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
    "detection_guidance": "税务合规重点：①检查增值税专用发票中品名为'酒''茶叶''礼品''餐饮''旅游'等项目的进项税额是否已做转出；②检查管理费用-业务招待费科目对应的进项税额是否转出；③检查应付职工薪酬-福利费科目对应的进项税额是否转出",
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

# ══════════════════════════════════════════════════════════════
# 天眼AI 集成（2026-07-02 接入）
# ══════════════════════════════════════════════════════════════
TYC_INTEGRATION = {
    "enabled": True,
    "access_method": "CLI + Skill",
    "cli": {
        "package": "tyc-cli",
        "version": "0.3.8",
        "install_path": "~/.workbuddy/binaries/node/versions/22.22.2/tyc",
        "config_path": "~/.tyc/config.json",
        "endpoint": "https://mcp.tianyancha.com/v1",
    },
    "skill": {
        "path": ".workbuddy/skills/tyc-it/SKILL.md（项目级Skill，随财税系统分发）",
        "tools": 162,
        "intent_categories": 12,
    },
    "engine_integration": {
        "module": "engine/agi_enhanced.py → TianyanchaClient",
        "method": "subprocess调用 tyc CLI，多路径自动探测（tyc / which(tyc) / 绝对路径）",
        "encoding": "UTF-8（Windows GBK兼容）",
        "output_parse": "sources.base → company_name/uscc/regStatus/legalPerson/capital/industry/established/staff",
    },
    "capabilities": [
        "企业工商登记信息查询（名称/USCC/法人/注册资本/经营范围/成立日期/行业/社保人数/标签）",
        "供应商资质核查（工商状态+注册资本+经营范围+关联关系四维验证）",
        "风险信息查询（经营异常/行政处罚/严重违法/失信/被执行/税收违法）",
        "股权与控制关系（股东/实控人/受益所有人/股权穿透/集团关系）",
        "关联关系路径（公司间最短关联路径/共同股东/共同高管）",
        "经营真实性（招投标/资质许可/招聘/客户供应商/产品信息）",
        "知识产权（专利/商标/软著/知识产权评分）",
    ],
    "usage_in_system": {
        "追问时自动触发": "用户问'查一下这家供应商'→ AGI引擎调用TianyanchaClient.check_company()",
        "经济实质穿透": "供应商信息导入后自动核查工商状态+经营范围匹配度",
        "报告增强": "一键分析时对高风险供应商自动调天眼AI补充工商数据",
    },
    "self_check": {
        "宁德时代": "91350900587527783P | 曾毓群 | 存续 | 电气机械 | 456360万 | 10000人以上",
        "深圳海更": "91440300MA5H824G7M | 张晓冬 | 存续 | 零售业 | 1000万 | <50人",
        "check_time": "2026-07-02",
    },
    "note": (
        "天眼AI通过tyc CLI调用，API Key存储在~/.tyc/config.json（非环境变量/非代码仓库）。"
        "在不支持CLI的环境中自动降级为HTTP API调用。"
        "调用消耗账号额度，每次查询约消耗1次额度。"
        "系统追问时仅在用户明确要求查供应商/客户信息时才调用，不会对每个发现自动查询。"
    ),
}

# ══════════════════════════════════════════════════════════════
# 税负模拟精准计算规则（2026-07-02 老邓亲授）
# ══════════════════════════════════════════════════════════════
TAX_BURDEN_RULES = {
    "title": "税负模拟三原则——税务合规报告必须做精准呈现，不可预估",
    
    "rule_1_dedup": {
        "name": "发票去重原则",
        "rule": "同一张发票按(invoice_code, invoice_no)去重，不能在多个风险类型中重复计算金额",
        "why": "一张发票可能同时存在'缺少数量字段'和'缺少计量单位'两个风险，但这是同一张票的同一笔金额。不去重会导致涉税金额被放大数倍，报告失去可信度。",
        "how": "main.py get_report_intelligence(): 用set存储已处理的(invoice_code, invoice_no)，新发票先查set再决定是否累加",
        "code": "main.py 第2节税负模拟 → seen_invoices去重集合",
    },
    
    "rule_2_vat": {
        "name": "增值税=发票实际税额，不可预估13%",
        "rule": "增值税专用发票：使用发票上的实际'税额'字段。增值税普通发票：税额为0（普票税额不可抵扣，已并入成本/费用）。禁止用金额×13%做固定预估。",
        "why": "税务合规报告是专业严谨的报告。预估13%这个动作本身就说明'我其实不知道实际税额是多少'。专票有明确税额数据，普票根本不能抵扣——两者混为一谈用13%预估是专业错误。",
        "how": "从evidence_rows提取invoice_type字段判断专票/普票。专票→取tax_amount字段；普票→vat=0（税额已按普票税额并入成本铁律处理）",
        "code": "main.py get_report_intelligence(): 按invoice_type过滤，专票累加tax_amt，普票跳过增值税",
    },
    
    "rule_3_income_tax": {
        "name": "企业所得税税率分级，不可固定25%",
        "rule": "企业所得税率不是固定25%。小微企业优惠5-10%、高新技术企业15%、一般企业25%。必须根据企业类型选择正确税率。报告中标注'企业所得税（最高X%）'——X%是上限，实际可能更低。",
        "why": "税法规定企业所得税有多种优惠税率。不管企业类型一律按25%算，对小微企业来说严重失实。标注'最高'表明这是最大可能补税额，实际可能因成本扣除、优惠叠加而更低。",
        "how": "检查target_entity.enterprise_type → 小微→5%/10%，高新→15%，一般→25%。表头写'企业所得税（最高X%）'。",
        "code": "main.py get_report_intelligence(): 按enterprise_type选inc_rate；前端标注最高",
    },
    
    "note": (
        "以上三原则写入引擎记忆后，任何涉及税负计算的代码模块必须遵守。"
        "禁止在报告中使用'增值税预估'字眼——要么是实际税额，要么写'无增值税（普票）'。"
        "禁止在报告中使用'所得税预估'字眼——标注实际所用税率。"
        "报告底部的免责已改为'基于现有发票数据的精确计算'，不再写'机器估算'。"
    ),

    # ═══════════════════════════════════════════════════════
    # 监控点分类体系（13大类·老邓 2026-07-18 确立·金税四期"以数治税"监控逻辑）
    # 权威源：1825条规则全部带 monitor_category 字段，取值必须来自以下13类。
    # 内在逻辑：企业全量经营数据（票/账/钱/税/产/物/人）解构为数据点→两两比对、
    # 三源交叉、四流合一，任一数据点与其他维度矛盾即触发疑点规则。
    "monitor_point_taxonomy": {
        "title": "监控点分类体系（13大类监管维度）",
        "principle": "不是用规则去套企业，而是让数据自己说话，让矛盾自己暴露。企业上传一次资料，引擎跑完全部规则，触发疑点按风险等级排序，经线索链/证据链/分析链自动完成从信号到结论的全过程。",
        "categories": [
            {"name": "资金流监控", "count": 76, "logic": "银行流水是外部基准，比对申报、发票、账载，揭示隐匿收入、账外循环。私户收款/资金回流/公转私/现金异常/账外支付。"},
            {"name": "发票流监控", "count": 168, "logic": "进销匹配、品名关联、开票行为、发票合规。品名背离/数量不匹配/顶额开票/作废红冲/连号/夜间开票/滞留票。"},
            {"name": "申报流监控", "count": 448, "logic": "增值税、所得税、财报三表比对，税种间勾稽。两税收入不一致/零申报/税负率偏低/留抵异常/预缴不足。含66行业税负率区间规则。"},
            {"name": "社保与个税交叉", "count": 181, "logic": "工资、社保、个税三数勾稽。三源不一致/有薪无保/全员零个税/劳务报酬/股东借款视同分红/年终奖拆分。"},
            {"name": "经营实质穿透", "count": 196, "logic": "用物理世界数据（电、水、场地、人工、产能）验证账面真实性。电耗产量/仓储库存/运费发货/设备产能/物耗能耗产能三线归一。"},
            {"name": "关联交易与利益输送", "count": 55, "logic": "穿透隐藏关联关系，检验交易独立公允性。六员重叠/转移定价/资本弱化/无息拆借/购销闭环。"},
            {"name": "虚开发票专项", "count": 95, "logic": "资金回流、四流不一、闭环开票、短期激增。最高风险级：变名/挂靠/富余票/走逃失联/空壳开票。"},
            {"name": "财产行为税监控", "count": 100, "logic": "房产、土地、印花、城建、环保等小税种与主税、资产变动联动比对。有房无税/合同未贴花/附加税不匹配/土增清算。"},
            {"name": "出口退税监控", "count": 46, "logic": "报关、发票、收汇三单匹配，产能与出口规模匹配。假报出口/循环出口/假自营真代理/留抵退税异常。"},
            {"name": "行业专项监控", "count": 237, "logic": "制造/建筑/房地产/商贸/餐饮/电商/医药/教育/灵活用工/再生资源等行业特定风险。"},
            {"name": "外部数据比对", "count": 24, "logic": "工商、银行、海关、电力、人社等第三方数据与申报数据比对。"},
            {"name": "账表质量与勾稽", "count": 143, "logic": "报表自身平衡、账表一致、跨期逻辑合理。恒等式断裂/科目勾稽/往来挂账/折旧摊销/凭证质量。"},
            {"name": "税务合规与程序", "count": 56, "logic": "备案、申报期限、优惠资格、历史处罚、合同管理、发票程序等合规性监控。"},
        ],
        "classification_priority": "归类优先级：专项优先于一般——出口退税/财产行为税/社保个税/关联交易/虚开专项/外部数据先判定，再判申报流/账表/资金流/经营实质/行业专项/发票流/合规程序。每条规则唯一主类（monitor_category字段）。",
        "maintenance": "新增规则必须赋 monitor_category（13类之一）。智能更新/自动发现规则写入时同步打标；类别名称禁止自创。",
    },

    # ═══════════════════════════════════════════════════════
        "rule_precise_writing": {
            "version": "2026-07-13 · 23字段修订版 + 穷举完成判定标准",
            "principle": "精写标准=23字段完整框架 + 分级深度  + 证据映射。每个字段的下限为最低要求，以异常点实际出发；确实达不到下限如实注明原因。框架是地图，不是尺子。",
            "iron_rules": [
                "【铁律1·字段齐全】23字段一个不能缺。基础字段9项自动填充，深度字段12项须精写。",
                "【铁律2·穷举至稽查终点】穿透追问穷举至稽查终点——问题间环环相扣、因果递进，直到证实违法行为存在或排除违法行为存在为止。推理链推到定性落地或排除风险为止。追问数量和推理层数是因果链条的自然长度，不是硬性指标。",
                "【铁律3·定级映射】定性路径三路径必须对应证据链三档定级——无法证明→线索 / 部分证明→强证据 / 完整证明→铁证。",
                "【铁律4·角色分明】稽查重点(⑮)=策略层(舞弊手法预判)；穿透追问(⑬)=执行层(讯问问题)。现象描述(⑭)=现象层(异常长什么样)；风险表格(⑱)=影响层(影响哪些税种、多大金额)。稽查处理(㉒)=稽查局视角；整改建议(㉓)=企业视角。",
                "【铁律5·证据可校验】推理链每层标注依赖证据类型；证据清单标注优先级(必须/应当/可以)；触发指标含行业差异阈值。"
            ],
            "exhaustion_criteria": {
                "principle": "决定数量的不是模板，是业务本身的复杂程度。每一个疑点都是独特的——复杂疑点追问可能二十条、推理可能五层；简单疑点追问可能四五条、推理两层就到底。复杂就多写，简单就如实写。数量是写完之后的自然结果，不是写之前的硬性规定。这就是'不凑数、不强编、一病一方'。",
                "drill_questions_done": {
                    "标准": "追问的数量不由任何预设数字决定，由事实层/证据层/逻辑层三个维度的覆盖度决定。",
                    "事实层穷举标准": "交易六要素全部覆盖即穷举完成，任一要素空白就还有追问空间：①谁——交易各方(买方/卖方/承运方/签收人)身份已明确；②什么——交易标的(品名/型号/数量/金额)已明确；③什么时候——合同签署/收款/发货/运输/签收各环节时间点已明确；④在哪里——发货地/运输路径/目的地/货物现状位置已明确；⑤怎么做的——交货方式(自提/直运/物流)/运输工具/装卸方式已明确；⑥谁参与的——经办人/提货人/驾驶员/签收人身份及与交易各方关系已明确。",
                    "证据层穷举标准": "四流(合同流/货物流/资金流/发票流)每个环节全部覆盖即穷举完成，任一流关键证据缺失就还有追问空间：①每一流是否都有对应证据类型被追问到；②每一流的关键证据是否都追问了来源和真实性；③四流之间的一致性是否都追问了比对。",
                    "逻辑层穷举标准": "所有合理商业解释全部穷举并追问即完成：合同约定的特殊条款/行业惯例/买方特殊需求/关联方特殊关系是否已追问。判定：当规则编写者再也想不出新的、不重复的、对方可能提出的合理解释时，逻辑层穷举完成。",
                    "最终判定": "当规则编写者对以下三问全部回答'否'时追问穷举完成：①还有没有尚未覆盖的交易要素(谁/什么/什么时候/在哪里/怎么做/谁参与的)？②四流中还有没有尚未追问到对应证据的环节？③对方还可能提出什么我没问到的合理商业解释？全部答'否'，追问数量即最终数量——是13条还是3条都是正确答案。"
                },
                "direction_done": {
                    "标准": "推理链的层数不由异常类型预先决定，由因果链条的自然长度决定。",
                    "结束条件": "满足任一即结束：①定性落地——最后一层已明确指向定性结论(偷税/少缴/虚开/不违规)，无法再追问'然后呢'；②证据尽头——下一层需要的证据当前无法获取，再往下推没有意义，标注'证据断点'；③逻辑闭环——最后一层回到第一层的前提形成完整闭环，无新因果环节需补充。",
                    "层数自然差异": "复杂异常(如关联交易转移利润：关联识别→定价偏离判定→利润流向追踪→税负差异计算→转移利润定性)自然4-5层；中等异常(如预收账款挂账：账龄异常→纳税义务触发→未申报事实固定→隐匿收入定性)自然3-4层；简单异常(如印花税漏缴：合同已签署→未缴印花税→构成少缴税款)自然2-3层，再加一层就是注水。层数是写完推理链之后的自然结果，不是写之前的规定。"
                },
                "normal_reason_done": {
                    "标准": "大部分异常确实穷举不了太多——'异常'本身就意味着不符合正常商业逻辑，如果一个异常有很多种合法解释，它就不叫异常了。",
                    "五个自问": "对以下五问全部回答'否'时穷举完成：①合同条款是否可能给出不同解释？②行业惯例是否可能支持这种做法？③交易对手的特殊情况是否可能合理化这种做法？④税收政策是否存在特殊规定允许这种做法？⑤是否存在不可抗力或第三方因素导致这种做法？全否则如实写当前数量——是2种就写2种，是5种就写5种。",
                    "特别规定": "只能穷举0-3种时必须注明原因：'该异常点违背正常商业逻辑，不存在更多合理商业解释，已穷举全部合法情形'；穷举5种以上时需自问该异常是否真的构成异常——合法解释太多可能说明该异常点的风险识别能力不足。"
                },
                "risk_table_done": {
                    "标准": "疑点影响几个税种就写几个税种，不设数量下限。",
                    "规则": "跨税种影响在2个以上的逐税种列明并区分影响程度(核心/次要/间接)；仅涉及单一税种的不强制跨税种，注明'该异常仅影响XX税，不涉及其他税种'；间接影响标注'间接影响(可能存在但非必然)'，与核心/次要影响明确区分。"
                },
                "quantity_matrix": [
                    {"field": "⑫推理链", "决定因素": "因果链条自然长度", "下限": "2层(简单异常如实写)", "上限": "无上限(推导到定性落地为止)"},
                    {"field": "⑬穿透追问", "决定因素": "交易要素+四流+合理解释的覆盖度", "下限": "不设下限(穷举完就停)", "上限": "无上限(问无可问为止)"},
                    {"field": "⑯正常业务解释", "决定因素": "真实存在的合法情形数量", "下限": "0(确实无合法解释就如实写并注明原因)", "上限": "穷举完毕为止"},
                    {"field": "⑱风险表格", "决定因素": "实际涉及的税种数量", "下限": "1(单税种就写单税种)", "上限": "全部涉及就全部列"},
                    {"field": "⑲证据清单", "决定因素": "四流各环节的证据类型数量", "下限": "每层至少1项'必须获取'", "上限": "穷举完毕为止"},
                    {"field": "㉑稽查动作", "决定因素": "从纸面比对到现场核查的步骤", "下限": "至少3步含1项现场核查", "上限": "穷举完毕为止"}
                ]
            },
            "repealed_law_watch": {
                "principle": "法规时效性核查是policy_ref的强制前置步骤。编写或精写任一规则的法律依据前，必须逐条对照本表核查是否已废止/被替代；已废止的严禁引用，必须替换为现行法并在policy_ref末尾附'法规现行性核验：YYYY-MM-DD'。本表随法规变动持续更新。",
                "repealed": [
                    {"废止法规": "《中华人民共和国增值税暂行条例》及其实施细则", "废止日期": "2026-01-01", "替代法规": "《中华人民共和国增值税法》（主席令第41号，2026-01-01施行）及《增值税法实施条例》（国务院令第826号）", "条文映射": "暂行条例第1条纳税人→增值税法第1条；第2条税率→第9条；第4条应纳税额→第14条；第6条销售额/价外费用→第17条；第19条纳税义务发生时间→第28条"},
                    {"废止法规": "《中华人民共和国营业税暂行条例》", "废止日期": "2016-05-01", "替代法规": "全面营改增，相关业务改征增值税，依《增值税法》", "条文映射": "营业税应税项目→增值税应税交易，不再有营业税"},
                    {"更新法规": "《中华人民共和国会计法》", "现行版本": "2024年修正（2024-07-01施行）", "注意": "引用须标注2024修正版；第9条新增'任何单位不得以虚假的经济业务事项或者资料进行会计核算'"},
                ],
                "current_valid_baseline": "《税收征收管理法》(2015修正)、《企业所得税法》(2018修正)、《个人所得税法》(2018修正)、《发票管理办法》(2023修订)、《会计法》(2024修正)、《增值税法》(2026-01-01施行)、财税〔2003〕158号(现行有效)。引用时仍须在核验日期当日复核。",
                "check_procedure": "①提取policy_ref中每一部法规名称+条号；②对照repealed列表，命中则按条文映射替换为现行法；③对照current_valid_baseline确认版本年份；④policy_ref末尾追加'法规现行性核验：YYYY-MM-DD'；⑤存量规则批量核查时，按法规名称全库检索命中，统一替换。",
                "checker_program": "engine/law_validity_checker.py —— 可运行的法律时效性核查程序（老邓2026-07-13确立）。理念：不把法条写死当永久真理，引用现行有效法律并由程序动态核查+自动处理，无'待人工核验'出口。维护CURRENT_VALID_LAWS(现行有效清单)+REPEALED_LAWS(已废止清单)；提供 check_policy_ref(text)逐条核查、scan_rules(rules)全库扫描、auto_process(rules)引擎自动校验+自动处理(替换废止法条+自动核验补标注)。已接入 audit_consistency.py：--fix 时引擎自动处理，引用废止法自动替换、缺核验的自动核验补标注。法律变动时只更新两张清单+重跑，无需逐条改死代码。"
            },
            "23_fields": {
                "basic": {
                    "count": 9,
                    "desc": "基础字段——身份、等级、法律、影响",
                    "fields": {
                        "id": {"name": "异常编号", "format": "{类型前缀}-{三位序号}，类型: AN=隐匿收入/VC=虚列成本/VI=虚开发票/ST=少缴税款/OT=其他", "example": "AN-001"},
                        "item": {"name": "异常名称", "format": "受控词表统一命名，同义不同名禁止", "example": "预收账款长期挂账不转收入"},
                        "category": {"name": "所属类别", "format": "五类之一: 隐匿收入/虚列成本/虚开发票/少缴税款/其他违规", "example": "隐匿收入"},
                        "level": {"name": "风险等级", "format": "极高/高/中/低/良好。与合规度对应: 极高<40分/高40-60/中60-80/低80-90/良好>90", "example": "高"},
                        "score": {"name": "风险评分", "format": "1-10分。锚点: 10=系统性造假/金额巨大/主观故意; 5=中等风险/需补充证据; 1=低风险/小额/偶发", "example": "8"},
                        "check_frequency": {"name": "稽查频率", "format": "高频=每户必查; 中频=行业匹配时查; 低频=特定条件触发时查", "example": "高频"},
                        "policy_ref": {"name": "法律依据", "format": "引用【现行有效】的法律法规——统一冠以'现行有效的《XX法》(版本)第X条'表述，保留具体条号以保证稽查精确性。法律不写死、不当永久真理：每条引用必须过 engine/law_validity_checker 法律时效性核查程序验证，policy_ref末尾强制附'法规现行性核验：YYYY-MM-DD'。法律废止/更替时，只更新 repealed_law_watch 与 law_validity_checker 清单并重跑核查，即可标出全库需更新的规则。", "example": "现行有效的《中华人民共和国增值税法》（2026-01-01施行）第十七条：销售额…（法规现行性核验：2026-07-13）"},
                        "tax_impact": {"name": "税务影响", "format": "分最低影响和典型影响: 税种(最低补税X万，典型补税Y万)", "example": "增值税(最低5万，典型15万)+企业所得税(最低12.5万，典型37.5万)"},
                        "applicable_condition": {"name": "适用条件", "format": "五维度结构化: 行业限制+纳税人资质+规模门槛+时间条件+金额门槛。非全部必填，以实际为准", "example": "行业=不限; 资质=一般纳税人; 规模=年营收>500万; 时间=账款账龄>365天; 金额=单笔>10万"}
                    }
                },
                "source": {
                    "count": 2,
                    "desc": "来源标记——记录规则的出处和发现方式",
                    "fields": {
                        "source": {"name": "来源", "format": "空=人工精写 / 系统发现 / LLM生成", "example": "系统发现"},
                        "auto_type": {"name": "自动发现类型", "format": "行业基准校准/购销倒挂/毛利为负/缺失数据/综合异常/未知模式", "example": "行业基准校准"}
                    }
                },
                "deep": {
                    "count": 12,
                    "desc": "深度字段——推理、证据、执行。精写核心。",
                    "fields": {
                        "direction": {
                            "name": "推理链",
                            "format": "推理至稽查终点——从现象出发，每一层追问\"为什么会出现这个现象\"，层与层之间因果递进、环环相扣。推理在以下两种终点之一停止：①证实违法行为存在（最后一层落地定性，指向⑰铁证路径）；②排除违法行为存在（最后一层排除定性，确认无违规）。层数是因果链条的自然长度。每层格式: 【推理第N层: XX法则】依赖证据: XX → 结论: XX。",
                            "flexible": "三种结束条件(满足任一): ①定性落地——最后一层已明确指向证实违法或排除违法; ②证据尽头——下一层需要的证据无法获取，标注断点; ③逻辑闭环——最后一层回到第一层前提，无新因果环节。",
                            "example": "【推理第一层: 时间性差异法则】依赖证据: 预收账款明细账+合同交货条款 → 预收账款账龄>365天且无合理延期理由"
                        },
                        "drill_questions": {
                            "name": "穿透追问",
                            "format": "穷举至稽查终点——问题间环环相扣、因果递进。每个问题的答案自然引出下一个问题（问题中的问题→问题中的其他问题），形成完整的追问链条。三组递进方向(事实→证据→逻辑)为追问框架。追问在以下两种终点之一停止：①证实违法行为存在（铁证闭环，所有追问答案自洽且指向违规）；②排除违法行为存在（所有追问答案自洽且指向合法商业行为）。格式 Q{N}:{问题}→潜台词:{稽查真实意图}。A:{应对话术}。",
                            "flexible": "有效追问三标准: ①答案必然引出下一个问题（环环相扣，非孤立提问）；②答案可验证（指向具体证据，非主观判断）；③答案推动稽查进程（要么加深嫌疑，要么排除嫌疑）。追问题环环相扣、因果递进?"
                        },
                        "phenomena": {
                            "name": "现象描述",
                            "format": "典型表现枚举(非穷举)，每种格式: 表现描述+典型行业/场景。兜底条款: '其他同类或类似表现'。增加排除条件: 什么情况下的类似表现不属于本异常",
                            "flexible": "至少5种典型表现。无法枚举到5种的注明原因。",
                            "example": "预收账款长期挂账——典型场景: 建筑企业收到预付款后不开票、不转收入"
                        },
                        "focus": {
                            "name": "稽查重点",
                            "format": "策略层——舞弊手法预判，不直接用于提问。格式: 舞弊手法名称: 具体操作方式 → 识别要点。用①②③④逐条标注。与⑬分工: ⑮是策略层(预判)，⑬是执行层(将预判转化为讯问问题)。",
                            "flexible": "至少①②③，多则不限",
                            "example": "①关联方过账: 通过关联公司收款再转回→识别要点: 收款方与本公司存在股权/人员/地址关联"
                        },
                        "normal_reason": {
                            "name": "正常业务解释",
                            "format": "穷举全部真实存在的合法情形，格式 {情形}——需提供{具体证据(文件类型)}。禁用'提供相关证明'须具体到文件。标记'最常见解释'作为红队攻击一优先素材。穷举判定见exhaustion_criteria.normal_reason_done五个自问。",
                            "flexible": "数量=真实存在的合法情形数量，下限0上限穷举完毕。确无合法情形或仅0-3种时如实写并注明'该异常点违背正常商业逻辑，已穷举全部合法情形'。穷举5种以上需自问该异常是否真的构成异常。不允许编造。",
                            "example": "①季节性旺季——提供过去三年同月销售数据对比表 [最常见解释]"
                        },
                        "determination": {
                            "name": "定性路径",
                            "format": "三路径必须对应证据链三档定级: ①无法证明→线索等级(单源数据触发)→定性'存疑，建议补充调查'+不入正式结论; ②部分证明→强证据(2独立来源验证)→定性'涉嫌XX'+可入正式结论但标注'证据部分闭环'; ③完整证明→铁证(≥3独立来源闭环)→定性'认定XX'+入正式结论可作处罚依据。每路径定义进入条件。设置了量化阈值(㉑)的规则，必须增加'阈值以下处理'分支——门槛未达到时以合规提示形式记录，不入稽查程序、不影响合规度评分。结尾附应对总原则。",
                            "flexible": "至少2-3条路径。应对总原则示例: 能完整证明走铁证路径; 能部分证明走强证据路径补证据后重判; 无法证明入线索池不入正式结论。对于设定了量化阈值(㉑)的规则，必须增加'阈值以下处理'分支——说明门槛未达到时如何处理(不入稽查程序、以合规提示形式记录、不影响合规度评分)。避免'一触发就定性'和'不触发就无视'两个极端。",
                        },
                        "risk_table": {
                            "name": "风险表格",
                            "format": "覆盖实际涉及税种/维度，不设数量下限。跨税种影响≥2个的逐税种列明，仅涉及单一税种的不强制跨税种。每行格式: 税种:具体风险描述 | 影响程度:核心/次要/间接。",
                            "flexible": "只列实际涉及的。单税种异常(如印花税漏缴)不强制跨税种注水。",
                            "example": "增值税:隐匿收入需补缴13%销项税额 | 核心影响"
                        },
                        "evidence": {
                            "name": "证据清单",
                            "format": "四层框架: 货物流+合同资金流+业务合理性+排雷。交易金额分级: 大额(>10万)分AB场景(自提vs直运); 中额(1-10万)至少取2个维度证据; 小额(<1万)抽样核验。每层证据标注优先级: 必须获取/应当获取/可以获取。排雷层与⑯联动——⑯列出合法情形，排雷层验证这些情形的证据是否真实存在。",
                            "flexible": "根据异常性质调整。不涉及货物流的以其他维度替代。"
                        },
                        "threshold": {
                            "name": "触发指标",
                            "format": "必须有量化阈值+前置条件(行业+资质+数据+时间四维度)。阈值增加行业差异: 通用阈值+行业调整。二元异常写'=是即触发'。预警等级: 黄/橙/红。",
                            "flexible": "前置条件四个维度各自独立，全满足才触发。",
                            "example": "通用: 账龄>365天+金额>10万; 行业调整: 建筑业>730天(工程周期长)/商贸业>90天(快周转)/服务业>180天"
                        },
                        "action": {
                            "name": "稽查动作",
                            "format": "从纸面比对到现场核查穷举全部核查步骤。每步格式: 动作类型(现场核查/纸面比对/外调走访/联网核查)+具体操作+预期产出。确实不存在现场核查可能性的(如纯申报类异常)，注明原因后补充替代性核查手段(交叉比对第三方数据/函调/联网核查)，不强制虚构现场核查。",
                            "flexible": "下限至少3步含1项现场核查，上限穷举完毕。步数=核查覆盖度的自然结果，不凑数。不可行时注明并补充替代手段。",
                            "example": "①现场核查: 实地查看仓库→预期产出: 库存盘点记录+仓库租赁合同"
                        },
                        "suggestion": {
                            "name": "稽查处理",
                            "format": "稽查局视角。固定格式: 定性→补税(分税种+金额)→滞纳金(日万分之五+起止日期)→罚款(征管法条款+区间)→移送标准(金额/情节门槛)。与⑰定性路径结论一致。",
                            "flexible": "无",
                            "example": "定性:涉嫌隐匿收入→补税:增值税13万+企业所得税32.5万→滞纳金:自税款所属期至缴清日→罚款:征管法§63税款50%-5倍→移送:金额>10万且主观故意"
                        },
                        "remedy": {
                            "name": "整改建议",
                            "format": "企业视角。三阶段含时间维度: 自查阶段(收到稽查通知前·主动补报可减轻处罚)→应对阶段(稽查进行中·含话术策略:如何配合/提供哪些材料/如何说明)→制度阶段(稽查结束后长期建设·内控制度/发票管理/合同规范)。与㉒分工: ㉒=稽查局视角(处罚)，㉓=企业视角(合规)。",
                            "flexible": "根本性异常(虚开发票)与轻微异常(申报遗漏)的整改内容完全不同。"
                        }
                    }
                }
            },
            "summary": "23字段框架 = 必须覆盖的维度。每个字段的具体深度 = 以异常点实际出发。框架是地图，不是尺子。分级下限+证据映射+角色分明=可执行的精写标准。",
            "canonical_example": {
                "id": 1813,
                "item": "预收账款长期挂账不转收入",
                "quality_notes": {
                    "drill_questions": "13条，三组递进（事实Q1-Q5/证据Q6-Q9/逻辑Q10-Q13），每组穷举至无新的有效追问。最后自检：事实六要素全覆盖、证据四流全追问、逻辑三个合理解释全排除 → 穷举完成。",
                    "direction": "4层，自然结果而非硬性目标。第一层→账龄异常识别，第四层→隐匿收入定性。中间无跳步（第二层纳税义务判定、第三层未申报事实固定）。每层标注依赖证据，可被引擎自动校验。",
                    "normal_reason": "4种，已穷举全部合法情形。注明穷举原因：大额资金无偿存放超过一年违背任何正常市场主体经济理性。不编造。",
                    "risk_table": "5个税种/维度，含核心/次要/间接影响程度标注。",
                    "evidence": "四层框架完整。大额分AB场景（自提/直运），金额分级（大>10万/中1-10万/小<1万），优先级标注（必须/应当/可以）。排雷层与⑯联动。",
                    "threshold": "含行业差异阈值为建筑业730天/商贸业90天/服务业180天/制造业540天。前置条件四维度结构化。",
                    "action": "5步含现场核查（仓库盘点+客户外调）+联网核查。不存在现场核查不可行。",
                    "suggestion": "固定格式：定性→补税→滞纳金→罚款→移送标准。完整。",
                    "remedy": "三阶段含时间维度+话术策略。稽查局视角（㉒）与企业视角（㉓）分工明确。"
                }
            },
            "execution_guide": {
                "version": "v1.0 · 2026-07-14",
                "purpose": "精写编制说明（v3配套执行指引）。不重复定义23字段格式和内容，解决编写者在实际精写过程中反复出现的执行偏差问题。标准管'写什么'，本说明管'怎么写才不会写错'。",
                "id_prefix_map": {
                    "description": "id必须使用{类型前缀}-{三位序号}格式，如AN-001、ST-002",
                    "AN": "隐匿收入", "VC": "虚列成本", "VI": "虚开发票", "ST": "少缴税款", "OT": "其他违规"
                },
                "common_errors": [
                    {"id": 1, "error": "id用#1等非标准格式", "correct": "必须用{类型前缀}-{三位序号}，五类前缀：AN/VC/VI/ST/OT", "field": "①"},
                    {"id": 2, "error": "category写五类之外的词", "correct": "必须从五类中选一。双定性允许双类别(用/分隔)但不超过两个，定性路径须明确分流", "field": "③"},
                    {"id": 3, "error": "level写'高风险'等变体", "correct": "标准格式：极高/高/中/低/良好，不加'风险'二字", "field": "④"},
                    {"id": 4, "error": "追问数量未达穷举就提交", "correct": "用穷举完成判定标准三问自检，全部答'是'才提交", "field": "⑬"},
                    {"id": 5, "error": "推理链未标注依赖证据", "correct": "每层必须写'依赖证据:XX'，漏标=引擎无法验证", "field": "⑫"},
                    {"id": 6, "error": "正常解释证据要求写'提供相关证明'", "correct": "禁止笼统，必须具体到文件类型", "field": "⑯"},
                    {"id": 7, "error": "证据第一层全部套用'货物流'", "correct": "按疑点类型选择贴合的名称，不强制套用", "field": "⑲"},
                    {"id": 8, "error": "附加税费影响标为'间接'", "correct": "附加税费随增值税必然联动→标'次要'。间接=可能存在但非必然", "field": "⑱"},
                    {"id": 9, "error": "定性路径只有一条", "correct": "三路径必须全写(无法证明→线索/部分证明→强证据/完整证明→铁证)", "field": "⑰"},
                    {"id": 10, "error": "policy_ref引用已废止法规", "correct": "强制标注核验日期(格式:法规现行性核验:YYYY-MM-DD)，重跑law_validity_checker", "field": "⑦"},
                    {"id": 11, "error": "定性路径只有三路径，没有写阈值以下怎么处理", "correct": "有量化阈值(㉑)的规则必须补全'阈值以下处理'分支——不生成正式发现但需以合规提示形式记录，不影响合规度评分", "field": "⑰"}
                ],
                "scoring_anchors": {
                    "description": "风险评分锚点（⑤score）",
                    "levels": [
                        {"score": 10, "criterion": "系统性造假/金额>500万/主观故意确凿/可能移送公安", "typical": "两套账、暴力虚开、跨年度持续偷税"},
                        {"score": "8-9", "criterion": "高度疑似造假/100-500万/需进一步取证", "typical": "借贷不平衡>100万、无运输费且设备不在买方"},
                        {"score": "6-7", "criterion": "中等风险/10-100万/需补充证据", "typical": "预收账款挂账1-2年尚无外调结论"},
                        {"score": "4-5", "criterion": "中度可疑/<10万/可能偶发差错", "typical": "单期小额借贷不平、单笔发票红冲无其他异常"},
                        {"score": "2-3", "criterion": "低风险/偶发/极小金额", "typical": "单次印花税漏缴、小额附加税费漏报"},
                        {"score": 1, "criterion": "极低风险/技术性违规/无实质性少缴", "typical": "账簿设置不规范但不影响应纳税额"}
                    ]
                },
                "impact_levels": {
                    "description": "影响程度判定锚点（⑱risk_table）。先锁定核心影响，再判断必然联动的次要影响，最后列出可能的间接影响。不凑数不强编。",
                    "核心": "直接导致补税或触犯法条构成违法",
                    "次要": "随核心影响必然联动，非独立存在",
                    "间接": "可能存在但非必然，需额外证据支持"
                },
                "evidence_priority": {
                    "description": "证据优先级（⑲evidence）",
                    "必须获取": "四流合一直接证据，缺1项闭环不成立→入线索等级",
                    "应当获取": "业务合理性佐证，增强但非必需",
                    "可以获取": "排雷辅助证据，补强或排除作用，不获取不影响闭环"
                },
                "evidence_layer_naming": {
                    "description": "第一层命名指引（⑲evidence）。不强制套用'货物流'，准确描述核心验证内容",
                    "映射": {
                        "实物交易类": "货物流",
                        "账务断裂类": "账实核对层",
                        "纯申报类": "申报数据层",
                        "发票类": "发票与货物流",
                        "成本费用类": "费用真实性层",
                        "关联交易类": "关联关系与定价层"
                    }
                },
                "quality_benchmarks": {
                    "description": "品质标杆对照：不是比数量，是比每个字段是否达到同等穷举深度",
                    "复杂异常": {"id": "ST-001", "item": "借贷不平衡", "layers": 5, "questions": 13, "normal_reasons": "5种已穷举"},
                    "中等异常": {"id": "AN-001", "item": "预收账款长期挂账", "layers": 4, "questions": 13, "normal_reasons": "4种已穷举"},
                    "简单异常": {"id": "ST-XXX", "item": "印花税漏缴(待编写)", "layers": "2-3", "questions": "4-6", "note": "穷举但数量少也是合格的，不把复杂标杆数量当所有规则下限"}
                },
                "submission_checklist": {
                    "description": "提交前17项自检清单",
                    "格式合规": ["①id是否{前缀}-{三位序号}", "③category是否在五类中", "④level是否标准格式", "⑦policy_ref是否核验日期", "字段编号①-⑨+⑫-㉓完整"],
                    "穷举完成": ["⑫推理链推到定性/排除+每层标注证据", "⑬追问三问全答是", "⑯正常解释穷举+证据具体到文件", "⑰定性路径三路径完整"],
                    "角色分明": ["⑮稽查重点=策略层", "⑬追问=执行层（Q&A完整）", "㉓整改=企业视角/㉒处理=稽查局视角"],
                    "证据可校验": ["⑲证据四层完整+优先级标注+第一层名贴合", "⑱风险表格标注影响程度+附加税费标次要", "㉑触发指标含量化阈值+行业调整"],
                    "整体自洽": ["⑫推理结论与⑰定性一致", "⑮舞弊手法与⑬追问形成策略→执行转化"]
                }
            }
        },
}

