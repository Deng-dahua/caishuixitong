// ==================== 税务疑点库页面 ====================
var taxRiskRulesData = [];
var _triggeredRuleFindings = {};  // rule_id → [finding, ...] 触发溯源

var RISK_LEVEL_COLORS = {
  '高风险': '#dc2626', '中风险': '#f59e0b', '低风险': '#3b82f6', '良好': '#10b981'
};
var RISK_LEVEL_ICONS = {
  '高风险': '🔴', '中风险': '🟡', '低风险': '🔵', '良好': '🟢'
};

// 分类描述
var CATEGORY_DESCRIPTIONS = {
  '资金流': '资金流向追踪、收款来源分析、付款方身份核实、异常交易检测。银行流水是税务合规的第一切入资料。',
  '发票进销匹配': '进销品名交叉映射、进销比分析、有进无销/有销无进诊断、BOM加工链条验证、存货周转预警、发票合规检查、税率异常、红冲作废追踪。',
  '经营实质': '企业是否具备真实经营条件——经营费用/仓储/物流/人员/产能。全链条经营实质地理分析。',
  '资料完备': '14类税务合规必查资料逐项检测，合同需求四层自动分层，缺失资料标注风险等级。',
  '税务合规': '增值税/企业所得税/个税/印花税/城建税等各税种申报与实际数据比对验证。',
  '财务数据': '科目余额、凭证完整性、报表勾稽、利润质量、资产负债结构等基础财务质量评估。',
  '薪酬社保': '工资表vs社保明细vs公积金三方交叉验证——基数匹配、人数一致、比例合规。',
  '关联交易': '名称相似度检测、同法人/同注册地/同电话识别、客户供应商重叠对倒检测。',
  '申报合规': '各税种申报表的填写规范性和数据准确性检查，申报期限和报送要求验证。',
  '行业专项': '针对特定行业的专属税务合规规则——制造业/建筑业/服务业/贸易等行业的特殊检查标准。',
  '个税': '个人所得税代扣代缴、专项附加扣除、工资薪金与劳务报酬的合规检查。',
  '资产负债': '资产和负债科目的真实性验证——存货/应收账款/固定资产/负债的计价和存在性。',
  '资产负债往来': '资产负债往来对应关系检查——借贷不平衡/应付账款占比/应收账款账龄/预收账款挂账等。',
  '企业所得税': '企业所得税的收入确认、成本扣除、税收优惠、纳税调整等申报合规检查。',
  '成本费用': '成本和费用的真实性、合理性与配比性检查——虚列成本、费用资本化等。',
  '成本费用配比': '毛利率/净利率/期间费用/业务招待费/资产损失等多项财务指标的综合配比分析。',
  '收入合规': '收入确认的真实性、完整性与及时性——预收账款转收入/其他应收款/存货周转/应付账款等。',
  '增值税税负': '增值税税负率偏高/偏低分析、文化事业建设费、长期零申报、免税收入进项转出等。',
  '增值税': '增值税销项税额、进项税额、应纳税额的计算准确性和申报及时性。',
  '个人所得税': '个人所得税代扣代缴、劳务报酬、经营所得、财产转让等个人所得税的申报与缴纳合规检查。',
  '虚开风险': '虚开发票风险检测——三流不一致/空壳供应商/资金回流/品名不匹配等虚开发票的典型特征识别与证据链构建。',
  '经营穿透': '经营实质深度穿透——从发票/合同/物流/资金多维度核查企业经营真实性，识别空壳/虚假交易。',
  '财产行为税': '房产税、契税、土地增值税、印花税、车船税等财产行为税种的申报缴纳合规检查。',
  '外部数据比对': '通过工商/海关/外汇/社保/电力等外部数据与税务申报数据的交叉比对，发现不一致和隐匿信息。',
  '合同风险': '合同签订与执行的税务风险——阴阳合同/时间倒挂/付款不符/金额不一致等合同异常检测。',
  '关联风险': '关联方穿透识别——同一法人/同址/同电话/交叉任职/利益输送等关联风险排查。',
  '出口退税': '出口退税合规检查——出口收入真实性/退税率/收汇/产能/货源穿透等出口退税全链条核查。',
};

function renderTaxRiskRules(container) {
  if (!container) return;
  var h = '';
  h += '<style>'
    + '.rr{max-width:960px;margin:0 auto;padding:32px 20px;font-family:-apple-system,"Microsoft YaHei",sans-serif;color:#3a4048;font-size:12px;line-height:1.95}'
    + '.rr-pre{font-size:12.5px;color:#5b6675;line-height:2.1;margin:0 0 20px;padding:12px 16px;background:#fef8f8;border-left:3px solid #9a1f2b;border-radius:0 6px 6px 0}'
    + '.rr-pre em{font-style:normal;color:#9a1f2b;font-weight:600}'
    + '.rr-hero{display:flex;gap:12px;margin-bottom:24px;flex-wrap:wrap}'
    + '.rr-stat{flex:1;min-width:120px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px 14px;text-align:center}'
    + '.rr-stat .v{font-size:20px;font-weight:700;color:#16233a;line-height:1.3}'
    + '.rr-stat .l{font-size:10px;color:#94a3b8;margin-top:4px}'
    + '.rr-tax{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:8px;margin:0 0 20px}'
    + '.rr-tax .rt{padding:8px 10px;background:#fafbfc;border:1px solid #eff2f6;border-radius:6px;font-size:11px}'
    + '.rr-tax .rt b{color:#16233a}'
    + '.rr-tax .rt span{font-size:10px;color:#94a3b8;float:right}'
    + '.rr-search{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}'
    + '.rr-search input{flex:1;min-width:180px;padding:6px 10px;border:1px solid #e2e8f0;border-radius:6px;font-size:11px;color:#475569;outline:none}'
    + '.rr-search input:focus{border-color:#9a1f2b}'
    + '.rr-search select{padding:6px 8px;border:1px solid #e2e8f0;border-radius:6px;font-size:11px;color:#475569;background:#fff}'
    + '.rr-rule{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px;margin-bottom:8px;transition:box-shadow .12s}'
    + '.rr-rule:hover{box-shadow:0 2px 6px rgba(0,0,0,.04)}'
    + '.rr-rule .rh{font-size:13px;font-weight:600;color:#16233a;margin:0 0 4px}'
    + '.rr-rule .rl{display:inline-block;padding:1px 8px;border-radius:4px;font-size:10px;font-weight:600;margin-right:6px}'
    + '.rr-rule .rb{font-size:11px;color:#64748b;line-height:1.8;margin:4px 0}'
    + '.rr-rule .ra{font-size:10.5px;color:#94a3b8}'
    + '</style>';
  h += '<div class="rr-pre">此库非凭空而来——每一条指令，都是<em>五十年稽查判例、被查企业真实手法、行政复议和法院判决</em>提炼出的量化标尺。规则库不是"猜疑清单"，而是<em>把经验变成可复核的判定条件</em>——什么数据特征构成疑点、这个疑点有多严重、接下来该查什么、法律依据在哪。引擎对照这些指令扫数据、出信号、给溯源。以下为引擎已加载的全部指令。</div>';

  h += '<div class="rr-search">'
    + '<input id="rr-search-input" type="text" placeholder="搜索规则..." oninput="window._rrFilter()" style="max-width:220px">'
    + '<select id="rr-level-filter" onchange="window._rrFilter()">'
    + '<option value="">全部等级</option>'
    + '<option value="极高风险">极高风险</option>'
    + '<option value="高风险">高风险</option>'
    + '<option value="中风险">中风险</option>'
    + '<option value="低风险">低风险</option>'
    + '<option value="良好">良好/正常</option>'
    + '</select>'
    + '<select id="rr-cat-filter" onchange="window._rrFilter()"><option value="">全部分类</option></select>'
    + '<select id="rr-source-filter" onchange="window._rrFilter()"><option value="">全部来源</option><option value="manual">人工规则</option><option value="auto">自动发现规则</option></select>'
    + '<select id="rr-sort-by" onchange="window._rrFilter()" style="padding:6px 8px;border:1px solid #e2e8f0;border-radius:6px;font-size:11px;color:#475569;background:#fff"><option value="id">编号排序</option><option value="level">风险等级排序</option><option value="category">分类排序</option><option value="updated">更新时间排序</option></select>'
    + '<button id="rr-update-btn" onclick="window._smartUpdate()" style="padding:6px 14px;background:#9a1f2b;color:#fff;border:none;border-radius:6px;font-size:11px;font-weight:600;cursor:pointer;white-space:nowrap">🤖 智能更新</button>'
    + '<span id="rr-update-time" style="font-size:10px;color:#94a3b8;white-space:nowrap"></span>'
    + '<span id="rr-update-status" style="font-size:10px;color:#94a3b8"></span>'
    + '</div>';

  h += '<div class="rr-hero" id="rr-hero"></div>';
  h += '<details id="rr-standard" style="margin-bottom:16px;background:#fafbfc;border:1px solid #eef2f6;border-radius:8px;padding:12px 16px;font-size:12px;line-height:1.9;color:#334155" open><summary style="font-weight:700;color:#16233a;cursor:pointer;font-size:13px">📐 精写编制标准（23字段完整版 · v3穷举至稽查终点）</summary>'
    + '<div style="margin-top:14px">'
    + '<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:6px;padding:12px 16px;margin-bottom:16px">'
    + '<div style="font-weight:800;color:#dc2626;margin-bottom:8px">五条铁律</div>'
    + '<b>铁律1·字段齐全：</b>23字段一个不能缺。基础字段9项自动填充，深度字段12项须精写。<br>'
    + '<b>铁律2·穷举至稽查终点：</b>穿透追问穷举至稽查终点——问题间环环相扣、因果递进，直到证实违法行为存在或排除违法行为存在为止。推理链推到定性落地或排除风险为止。追问数量和推理层数是因果链条的自然长度。<br>'
    + '<b>铁律3·定级映射：</b>定性路径三路径必须对应证据链三档定级——无法证明→线索 / 部分证明→强证据 / 完整证明→铁证。<br>'
    + '<b>铁律4·角色分明：</b>稽查重点=策略层(舞弊手法预判)；穿透追问=执行层(讯问问题)。现象描述=现象层；风险表格=影响层。稽查处理=稽查局视角；整改建议=企业视角。<br>'
    + '<b>铁律5·证据可校验：</b>推理链每层标注依赖证据类型；证据清单标注优先级(必须/应当/可以)；触发指标含行业差异阈值。'
    + '</div>'
    + '<div style="font-weight:800;color:#0f172a;margin-bottom:10px;border-bottom:2px solid #e2e8f0;padding-bottom:6px">一、基础字段（9项·每条必填）</div>'
    + '<b>① id（异常编号）：</b>{类型前缀}-{三位序号}，类型: AN=隐匿收入/VC=虚列成本/VI=虚开发票/ST=少缴税款/OT=其他。示例: AN-001<br>'
    + '<b>② item（异常名称）：</b>受控词表统一命名，同义不同名禁止。示例: 预收账款长期挂账不转收入<br>'
    + '<b>③ category（所属类别）：</b>五类之一: 隐匿收入/虚列成本/虚开发票/少缴税款/其他违规。示例: 隐匿收入<br>'
    + '<b>④ level（风险等级）：</b>极高/高/中/低/良好。与合规度对应: 极高<40分/高40-60/中60-80/低80-90/良好>90。示例: 高<br>'
    + '<b>⑤ score（风险评分）：</b>1-10分。锚点: 10=系统性造假/金额巨大/主观故意; 5=中等风险/需补充证据; 1=低风险/小额/偶发。示例: 8<br>'
    + '<b>⑥ check_frequency（稽查频率）：</b>高频=每户必查; 中频=行业匹配时查; 低频=特定条件触发时查。示例: 高频<br>'
    + '<b>⑦ policy_ref（法律依据）：</b>引用<b>现行有效</b>的法律法规——统一冠以'现行有效的《XX法》(版本)第X条'，保留条号保证稽查精确性。法律不写死、不当永久真理：每条引用须过<b>法律时效性核查程序</b>（engine/law_validity_checker，已接入审计）验证，末尾强制附核验日期。法律变动时核查程序自动识别废止法规并替换为现行法，重跑即可自动更新——无需人工维护废止对照表。示例: 现行有效的《增值税法》(2026-01-01施行)第十七条…（法规现行性核验：2026-07-13）<br>'
    + '<b>⑧ tax_impact（税务影响）：</b>分最低影响和典型影响: 税种(最低补税X万，典型补税Y万)。示例: 增值税(最低5万，典型15万)+企业所得税(最低12.5万，典型37.5万)<br>'
    + '<b>⑨ applicable_condition（适用条件）：</b>五维度结构化: 行业限制+纳税人资质+规模门槛+时间条件+金额门槛。非全部必填。示例: 行业=不限; 资质=一般纳税人; 时间=账款账龄>365天; 金额=单笔>10万<br>'
    + '<div style="font-weight:800;color:#0f172a;margin:14px 0 10px;border-bottom:2px solid #e2e8f0;padding-bottom:6px">二、来源标记（2项）</div>'
    + '<b>⑩ source（来源）：</b>空=人工精写 / 系统发现 / LLM生成。示例: 系统发现<br>'
    + '<b>⑪ auto_type（自动发现类型）：</b>行业基准校准/购销倒挂/毛利为负/缺失数据/综合异常/未知模式<br>'
    + '<div style="font-weight:800;color:#0f172a;margin:14px 0 10px;border-bottom:2px solid #e2e8f0;padding-bottom:6px">三、深度字段（12项·精写核心）</div>'
    + '<b>一、推理链（direction）：</b>推理至稽查终点——证实违法或排除违法。层与层之间因果递进、环环相扣。每层格式: 【推理第N层: XX法则】依赖证据: XX → 结论: XX。三种结束条件: ①定性落地——最后一层已明确指向证实违法或排除违法; ②证据尽头——下一层需要的证据无法获取，标注断点; ③逻辑闭环——最后一层回到第一层前提。<br>'
    + '<b>二、穿透追问（drill_questions）：</b>穷举至稽查终点——问题间环环相扣、因果递进，每个答案自然引出下一个问题。三组递进方向(事实→证据→逻辑)为追问框架。有效追问三标准: ①答案必然引出下一个问题（非孤立提问）; ②答案可验证（指向具体证据）; ③答案推动稽查进程（要么加深嫌疑，要么排除嫌疑）。追问在证实违法或排除违法时停止。格式: Q{N}:{问题}→潜台词:{稽查真实意图}。A:{应对话术}。<br>'
    + '<b>三、现象描述（phenomena）：</b>典型表现枚举(非穷举)，每种格式: 表现描述+典型行业/场景。至少5种典型表现。兜底条款: 其他同类或类似表现。增加排除条件: 什么情况下的类似表现不属于本异常。<br>'
    + '<b>四、稽查重点（focus）：</b>策略层——舞弊手法预判，不直接用于提问。格式: 舞弊手法名称: 具体操作方式 → 识别要点。用①②③④逐条标注。与穿透追问分工: focus=策略层(预判)，drill_questions=执行层(将预判转化为讯问问题)。<br>'
    + '<b>五、正常业务解释（normal_reason）：</b>至少4种情形，格式 {情形}——需提供{具体证据(文件类型)}。禁用\"提供相关证明\"须具体到文件。标记\"最常见解释\"作为红队攻击一优先素材。确无合法情形时如实写0-3种并注明原因，不允许编造。<br>'
    + '<b>六、定性路径（determination）：</b>三路径必须对应证据链三档定级: ①无法证明→线索等级(单源数据触发)→定性\"存疑，建议补充调查\"+不入正式结论; ②部分证明→强证据(2独立来源验证)→定性\"涉嫌XX\"+可入正式结论但标注\"证据部分闭环\"; ③完整证明→铁证(≥3独立来源闭环)→定性\"认定XX\"+入正式结论可作处罚依据。每路径定义进入条件。应对总原则: 能完整证明走铁证路径; 能部分证明走强证据路径补证据后重判; 无法证明入线索池不入正式结论。<br>'
    + '<b>七、风险表格（risk_table）：</b>覆盖实际涉及税种/维度，不设数量下限。跨税种影响≥2个的逐税种列明，仅涉及单一税种的不强制跨税种。每行格式: 税种:具体风险描述 | 影响程度:核心/次要/间接。<br>'
    + '<b>八、证据清单（evidence）：</b>四层框架: 货物流+合同资金流+业务合理性+排雷。交易金额分级: 大额(>10万)分AB场景(自提vs直运); 中额(1-10万)至少取2个维度证据; 小额(<1万)抽样核验。每层证据标注优先级: 必须获取/应当获取/可以获取。排雷层与正常业务解释联动——列出合法情形，排雷层验证这些情形的证据是否真实存在。<br>'
    + '<b>九、触发指标（threshold）：</b>必须有量化阈值+前置条件(行业+资质+数据+时间四维度)。阈值增加行业差异: 通用阈值+行业调整。二元异常写\"=是即触发\"。预警等级: 黄/橙/红。前置条件四个维度各自独立，全满足才触发。<br>'
    + '<b>十、稽查动作（action）：</b>从纸面比对到现场核查穷举全部核查步骤，下限至少3步含1项现场核查、上限穷举完毕。每步格式: 动作类型(现场核查/纸面比对/外调走访/联网核查)+具体操作+预期产出。确实不存在现场核查可能性的(如纯申报类异常)，注明原因后补充替代性核查手段(交叉比对第三方数据/函调/联网核查)，不强制虚构现场核查。<br>'
    + '<b>十一、稽查处理（suggestion）：</b>稽查局视角。固定格式: 定性→补税(分税种+金额)→滞纳金(日万分之五+起止日期)→罚款(征管法条款+区间)→移送标准(金额/情节门槛)。与定性路径结论一致。示例: 定性:涉嫌隐匿收入→补税:增值税13万+企业所得税32.5万→滞纳金:自税款所属期至缴清日→罚款:征管法§63税款50%-5倍→移送:金额>10万且主观故意<br>'
    + '<b>十二、整改建议（remedy）：</b>企业视角。三阶段含时间维度: 自查阶段(收到稽查通知前·主动补报可减轻处罚)→应对阶段(稽查进行中·含话术策略:如何配合/提供哪些材料/如何说明)→制度阶段(稽查结束后长期建设·内控制度/发票管理/合同规范)。与稽查处理分工: suggestion=稽查局视角(处罚)，remedy=企业视角(合规)。<br>'
    + '<div style="font-weight:800;color:#0f172a;margin:16px 0 10px;border-bottom:2px solid #dc2626;padding-bottom:6px">四、穷举完成判定标准（数量由业务复杂度决定，不是模板规定）</div>'
    + '<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:6px;padding:10px 14px;margin-bottom:12px;font-size:11.5px;color:#7f1d1d;line-height:1.9"><b>核心原则：</b>决定数量的不是模板，是业务本身的复杂程度。复杂疑点追问可能二十条、推理可能五层；简单疑点追问四五条、推理两层就到底。<b>数量是写完之后的自然结果，不是写之前的硬性规定</b>——不凑数、不强编、一病一方。</div>'
    + '<b>1. 追问穷举（⑬）——不是13条，是问无可问：</b>数量由三维覆盖度决定。<br>'
    + '&nbsp;&nbsp;<b>事实层</b>：交易六要素全覆盖（谁/什么/什么时候/在哪里/怎么做的/谁参与的），任一空白即还有追问空间。<br>'
    + '&nbsp;&nbsp;<b>证据层</b>：四流（合同流/货物流/资金流/发票流）每环节全追问（证据类型/来源真实性/四流一致性比对），任一流关键证据缺失即还有追问空间。<br>'
    + '&nbsp;&nbsp;<b>逻辑层</b>：所有合理商业解释全排除（合同特殊条款/行业惯例/买方特殊需求/关联方关系），想不出新解释即完成。<br>'
    + '&nbsp;&nbsp;<b>最终判定</b>：对「还有未覆盖的交易要素吗/四流还有未追问的证据环节吗/对方还可能提哪些没问到的解释」三问全答「否」→穷举完成。13条还是3条都是正确答案。<br>'
    + '<b>2. 推理链层数（⑫）——不是4层，是推无可推：</b>由因果链条自然长度决定。结束条件满足任一即停：①定性落地（指向偷税/少缴/虚开/不违规，无法再问「然后呢」）；②证据尽头（下一层证据无法获取，标注「证据断点」）；③逻辑闭环（回到第一层前提）。复杂异常自然4-5层、中等3-4层、简单2-3层，再加一层就是注水。<br>'
    + '<b>3. 正常业务解释（⑯）——不是5种，是穷举完毕：</b>「异常」本身意味着不符合正常商业逻辑，合法解释太多它就不叫异常了。五个自问全答「否」即完成（合同条款/行业惯例/交易对手特殊情况/税收政策特殊规定/不可抗力）。仅0-3种时注明「已穷举全部合法情形」；5种以上需自问该异常是否真构成异常。<br>'
    + '<b>4. 风险表格（⑱）——不是6税种，是覆盖实际涉及：</b>影响几个税种写几个，不设下限。跨税种≥2个逐税种列明并区分核心/次要/间接；仅单一税种注明「仅影响XX税不涉及其他」，不强制跨税种注水。<br>'
    + '<div style="margin:12px 0;overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:10.5px">'
    + '<tr style="background:#fef2f2"><td style="padding:4px 8px;border:1px solid #fcc;font-weight:700">字段</td><td style="padding:4px 8px;border:1px solid #fcc;font-weight:700">数量决定因素</td><td style="padding:4px 8px;border:1px solid #fcc;font-weight:700">下限</td><td style="padding:4px 8px;border:1px solid #fcc;font-weight:700">上限</td></tr>'
    + '<tr><td style="padding:4px 8px;border:1px solid #e2e8f0">⑫推理链</td><td style="padding:4px 8px;border:1px solid #e2e8f0">因果链条自然长度</td><td style="padding:4px 8px;border:1px solid #e2e8f0">2层(简单异常如实写)</td><td style="padding:4px 8px;border:1px solid #e2e8f0">无上限(推导到定性落地)</td></tr>'
    + '<tr><td style="padding:4px 8px;border:1px solid #e2e8f0">⑬穿透追问</td><td style="padding:4px 8px;border:1px solid #e2e8f0">交易要素+四流+合理解释覆盖度</td><td style="padding:4px 8px;border:1px solid #e2e8f0">不设下限(穷举完就停)</td><td style="padding:4px 8px;border:1px solid #e2e8f0">无上限(问无可问为止)</td></tr>'
    + '<tr><td style="padding:4px 8px;border:1px solid #e2e8f0">⑯正常业务解释</td><td style="padding:4px 8px;border:1px solid #e2e8f0">真实存在的合法情形数量</td><td style="padding:4px 8px;border:1px solid #e2e8f0">0(确实无就如实写并注明)</td><td style="padding:4px 8px;border:1px solid #e2e8f0">穷举完毕为止</td></tr>'
    + '<tr><td style="padding:4px 8px;border:1px solid #e2e8f0">⑱风险表格</td><td style="padding:4px 8px;border:1px solid #e2e8f0">实际涉及的税种数量</td><td style="padding:4px 8px;border:1px solid #e2e8f0">1(单税种就写单税种)</td><td style="padding:4px 8px;border:1px solid #e2e8f0">全部涉及就全部列</td></tr>'
    + '<tr><td style="padding:4px 8px;border:1px solid #e2e8f0">⑲证据清单</td><td style="padding:4px 8px;border:1px solid #e2e8f0">四流各环节的证据类型数量</td><td style="padding:4px 8px;border:1px solid #e2e8f0">每层至少1项「必须获取」</td><td style="padding:4px 8px;border:1px solid #e2e8f0">穷举完毕为止</td></tr>'
    + '<tr><td style="padding:4px 8px;border:1px solid #e2e8f0">㉑稽查动作</td><td style="padding:4px 8px;border:1px solid #e2e8f0">从纸面比对到现场核查的步骤</td><td style="padding:4px 8px;border:1px solid #e2e8f0">至少3步含1项现场核查</td><td style="padding:4px 8px;border:1px solid #e2e8f0">穷举完毕为止</td></tr>'
    + '</table></div>'
    + '<div style="background:#fffbeb;border:1px solid #fde68a;border-radius:6px;padding:10px 14px;margin-top:14px;font-size:11px;color:#92400e">'
    + '<div style="font-weight:700;margin-bottom:4px">📌 品质标杆（canonical_example: #1813 预收账款长期挂账）</div>'
    + '穿透追问: 13条，三组递进（事实Q1-Q5/证据Q6-Q9/逻辑Q10-Q13），每组穷举至无新有效追问。<br>推理链: 4层，自然结果非硬性目标（账龄异常→纳税义务→未申报固定→隐匿定性）。<br>正常解释: 4种已穷举，注明穷举原因。风险表格: 5税种含核心/次要/间接标注。<br>证据清单: 四层框架完整，AB场景+金额分级+优先级，排雷与⑯联动。阈值: 四行业差异调整。'
    + '</div>'
    + '<em style="color:#64748b;display:block;margin-top:10px">* 追问穷举至稽查终点（证实违法或排除违法），问题间环环相扣、因果递进。数量是因果链条的自然长度，不是硬性指标。不凑数、不强编、一病一方。</em>'
    + '</div>'
    + '</details>';
  h += '<details id="rr-exec-guide" style="margin-bottom:16px;background:#f8faf9;border:1px solid #d4ede3;border-radius:8px;padding:12px 16px;font-size:12px;line-height:1.9;color:#334155"><summary style="font-weight:700;color:#0f766e;cursor:pointer;font-size:13px">📋 精写编制说明（v3配套执行指引 · 怎么写才不会写错）</summary>'
    + '<div id="rr-exec-guide-content" style="margin-top:12px;color:#64748b">加载中...</div>'
    + '</details>';
  h += '<div id="rr-list"></div>';
  h += '<div id="rr-compare" style="display:none;margin:0 0 20px;padding:16px;background:#fef8f8;border:1px solid #f4c2c7;border-radius:8px"></div>';

  container.innerHTML = h;

  // 加载编制说明
  fetch('/api/tax-risk-rules/execution-guide').then(function(r){return r.json()}).then(function(d){
    if (!d.ok) { document.getElementById('rr-exec-guide-content').innerHTML = '<span style=color:#dc2626>加载失败:'+d.message+'</span>'; return; }
    var eg = d.data, html = '';
    // 定位
    html += '<div style=background:#f0faf6;border:1px solid #bae6d3;border-radius:6px;padding:10px 14px;margin-bottom:14px;font-size:11px;color:#0f766e>' + eg.purpose + '</div>';
    // 常犯错误
    html += '<div style=font-weight:700;color:#0f172a;margin:12px 0 6px;border-bottom:1px solid #e2e8f0>二、常犯错误防错清单</div>';
    var errs = eg.common_errors || [];
    errs.forEach(function(e){ html += '<div style=margin:3px 0><b style=color:#dc2626>❌ </b>' + e.error + ' → <b style=color:#166534>✓</b> ' + e.correct + '</div>'; });
    // 评分锚点
    html += '<div style=font-weight:700;color:#0f172a;margin:12px 0 6px;border-bottom:1px solid #e2e8f0>三、风险评分锚点</div>';
    var sa = eg.scoring_anchors, lvs = sa.levels || [];
    lvs.forEach(function(l){ html += '<div style=margin:3px 0><b>'+l.score+'分</b>: '+l.criterion+' ('+l.typical+')</div>'; });
    // 影响程度
    html += '<div style=font-weight:700;color:#0f172a;margin:12px 0 6px;border-bottom:1px solid #e2e8f0>四、影响程度 & 证据优先级</div>';
    var il = eg.impact_levels || {};
    for (var k in il) { if (k=='description') continue; html += '<b>'+k+'</b>: '+il[k]+'<br>'; }
    var ep = eg.evidence_priority || {};
    html += '<b>证据优先级——必须获取</b>: '+ep['必须获取']+'<br><b>应当获取</b>: '+ep['应当获取']+'<br><b>可以获取</b>: '+ep['可以获取']+'<br>';
    // 证据命名
    var en = eg.evidence_layer_naming, emap = en.映射 || {};
    html += '<div style=font-weight:700;color:#0f172a;margin:12px 0 6px;border-bottom:1px solid #e2e8f0>五、证据第一层命名指引</div>';
    for (var k in emap) { html += '<b>'+k+'</b> → '+emap[k]+'<br>'; }
    // 品质标杆
    var qb = eg.quality_benchmarks || {};
    html += '<div style=font-weight:700;color:#0f172a;margin:12px 0 6px;border-bottom:1px solid #e2e8f0>六、品质标杆</div>';
    for (var k in qb) { if (k=='description') continue; var b=qb[k]; html += '<b>'+b.id+' '+b.item+'</b>: '+b.layers+'层 '+b.questions+'条追问 '+b.normal_reasons+'<br>'; }
    // 自检清单
    var sc = eg.submission_checklist || {};
    html += '<div style=font-weight:700;color:#0f172a;margin:12px 0 6px;border-bottom:1px solid #e2e8f0>七、提交前自检（6组17项）</div>';
    var groups = ['格式合规','穷举完成','角色分明','证据可校验','整体自洽'];
    for (var gi=0;gi<groups.length;gi++) { var gn=groups[gi], items=sc[gn]; if (items) { html += '<b>'+gn+'</b>: '; items.forEach(function(it){ html += '<span style=background:#f1f5f9;padding:1px 6px;border-radius:3px;margin:2px;font-size:10.5px>'+it+'</span>'; }); html += '<br>'; } }
    document.getElementById('rr-exec-guide-content').innerHTML = html;
  }).catch(function(e){ document.getElementById('rr-exec-guide-content').innerHTML = '<span style=color:#dc2626>加载失败:'+e+'</span>'; });

  var dataUrl = '/static/tax_risk_rules_local_export.json';
  // 显示规则文件最后修改时间
  fetch(dataUrl, {method:'HEAD'}).then(function(r){
    var lm = r.headers.get('Last-Modified');
    if (lm) {
      var d = new Date(lm);
      var ds = (d.getMonth()+1)+'/'+d.getDate()+' '+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0');
      var tu = document.getElementById('rr-update-time'); if (tu) tu.textContent = '最后更新 ' + ds;
    }
  }).catch(function(){});

  // 加载数据
  fetch(dataUrl + '?' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(rules) {
      window._rrData = rules;
      // 更新自动发现规则计数（自动面板数据已分离到独立文件，计数始终准确）
      var autoCount = rules.filter(function(rl){ return rl.type === 'auto_signal' || rl.source === '系统发现' || !!rl.auto_type; }).length;
      var acEl = document.getElementById('au-auto-count'); if (acEl) acEl.textContent = autoCount;
      var cats = {};
      var total = 0, high = 0, mid = 0, low = 0, good = 0;
      rules.forEach(function(rl) {
        total++; 
        var lv = rl.level || rl.level || '';
        if (lv.indexOf('极高') >= 0 || lv.indexOf('高') >= 0) high++;
        else if (lv.indexOf('中') >= 0) mid++;
        else if (lv.indexOf('低') >= 0) low++;
        else good++;
        var cat = rl.category || rl.分类 || '其他';
        cats[cat] = (cats[cat] || 0) + 1;
      });

      // 统计面板
      var hero = document.getElementById('rr-hero');
      if (hero) hero.innerHTML = 
        '<div class="rr-stat"><div class="v" style="color:#16233a">' + total + '</div><div class="l">指令总数</div></div>'
        + '<div class="rr-stat"><div class="v" style="color:#dc2626">' + high + '</div><div class="l">极高/高风险</div></div>'
        + '<div class="rr-stat"><div class="v" style="color:#f59e0b">' + mid + '</div><div class="l">中风险</div></div>'
        + '<div class="rr-stat"><div class="v" style="color:#059669">' + (low + good) + '</div><div class="l">低风险/良好</div></div>';

      // 分类标签
      var catFilter = document.getElementById('rr-cat-filter');
      if (catFilter) {
        Object.keys(cats).sort(function(a, b) { return cats[b] - cats[a]; }).forEach(function(c) {
          var o = document.createElement('option');
          o.value = c; o.textContent = c + ' (' + cats[c] + ')';
          catFilter.appendChild(o);
        });
      }

      var rrSortBy = 'id';
window._rrSort = function(rules, sortBy) {
  if (sortBy === 'level') {
    var order = {'极高':0,'高':1,'中':2,'低':3,'良好':4};
    return rules.slice().sort(function(a,b){return (order[a.level]||5)-(order[b.level]||5);});
  } else if (sortBy === 'category') {
    return rules.slice().sort(function(a,b){return (a.category||'').localeCompare(b.category||'');});
  } else if (sortBy === 'updated') {
    return rules.slice().sort(function(a,b){return (b.updated_at||'').localeCompare(a.updated_at||'');});
  }
  return rules.slice().sort(function(a,b){return (a.id||0)-(b.id||0);});
};
window._rrFilter = function() {
        var kw = (document.getElementById('rr-search-input') && document.getElementById('rr-search-input').value || '').toLowerCase();
        var lv = document.getElementById('rr-level-filter') && document.getElementById('rr-level-filter').value || '';
        var ct = document.getElementById('rr-cat-filter') && document.getElementById('rr-cat-filter').value || '';
        var sc = document.getElementById('rr-source-filter') && document.getElementById('rr-source-filter').value || '';
        var list = document.getElementById('rr-list');
        if (!list) return;
        var sb = document.getElementById('rr-sort-by'); var sortBy = sb ? sb.value : 'id';
        var filtered = window._rrSort(rules, sortBy).filter(function(rl) {
          var txt = (rl.item || '') + ' ' + (rl.direction || '') + ' ' + (rl.focus || '') + ' ' + (rl.action || '') + ' ' + (rl.policy_ref || '') + ' ' + (rl.id || '');
          if (kw && txt.toLowerCase().indexOf(kw) < 0) return false;
          if (lv && (rl.level || rl.level || '').indexOf(lv) < 0) return false;
          if (ct && (rl.category || '') !== ct) return false;
          if (sc) {
            var isAuto = rl.source === '系统发现' || rl.type === 'auto_signal';
            if (sc === 'auto' && !isAuto) return false;
            if (sc === 'manual' && isAuto) return false;
          }
          return true;
        });
        if (filtered.length === 0) {
          list.innerHTML = '<div style="text-align:center;padding:24px;color:#94a3b8">未找到匹配的规则</div>';
          return;
        }
        var html = '';
        filtered.forEach(function(rl) {
          var lv = rl.level || rl.level || '信息';
          var lc = '#64748b';
          if (lv.indexOf('极高') >= 0) lc = '#991b1b';
          else if (lv.indexOf('高') >= 0) lc = '#dc2626';
          else if (lv.indexOf('中') >= 0) lc = '#f59e0b';
          else if (lv.indexOf('低') >= 0) lc = '#059669';
          var card = '<div class="rr-rule">'
            + '<div class="rh">#' + (rl.id || '') + ' ' + escHtml(rl.item || '未命名') + '</div>'
            + (rl.type === 'auto_signal' || rl.source === '系统发现' || rl.auto_type ? '<span style="font-size:9px;background:#eff6ff;color:#2563eb;padding:2px 6px;border-radius:4px;font-weight:600;margin-right:4px">🤖 自动发现</span>' : '<span style="font-size:9px;background:#f5f3ff;color:#7c3aed;padding:2px 6px;border-radius:4px;font-weight:600;margin-right:4px">✍ 人工规则</span>')
            + '<span class="rl" style="background:' + lc + '15;color:' + lc + ';border:1px solid ' + lc + '30">' + lv + '</span>'
            + (rl.score ? '<span style="font-size:9px;color:#94a3b8;margin-left:4px">评分' + rl.score + '/10</span>' : '')
            + (rl.category ? '<span style="font-size:10px;color:#94a3b8;margin-left:6px">' + rl.category + '</span>' : '')
            + (rl.check_frequency ? '<span style="font-size:9px;color:#94a3b8;margin-left:6px;border:1px solid #e2e8f0;border-radius:4px;padding:0 4px">' + rl.check_frequency + '</span>' : '');

          // 7段式新格式：phenomena → direction → focus → risk_table → normal_reason → determination → drill_questions
          if (rl.phenomena) {
            card += '<div style="font-size:12px;font-weight:600;color:#16233a;margin:8px 0 4px;border-bottom:1px solid #e2e8f0;padding-bottom:4px">一、异常现象描述</div>';
            card += '<div style="font-size:11px;color:#3a4048;line-height:2;margin:4px 0 10px;white-space:pre-wrap">' + escHtml(rl.phenomena) + '</div>';
          }
          if (rl.direction) {
            card += '<div style="font-size:12px;font-weight:600;color:#16233a;margin:8px 0 4px;border-bottom:1px solid #e2e8f0;padding-bottom:4px">' + (rl.phenomena ? '二' : '一') + '、异常逻辑分析（为何成为疑点）</div>';
            card += '<div style="font-size:11px;color:#64748b;line-height:2;padding-left:10px;border-left:2px solid #9a1f2b;margin:4px 0 10px;white-space:pre-wrap">' + escHtml(rl.direction) + '</div>';
          }
          if (rl.focus && rl.focus !== '待明确重点') {
            card += '<div style="font-size:12px;font-weight:600;color:#16233a;margin:8px 0 4px;border-bottom:1px solid #e2e8f0;padding-bottom:4px">稽查重点指向</div>';
            card += '<div style="font-size:11px;color:#dc2626;line-height:2;padding-left:10px;border-left:2px solid #dc2626;margin:4px 0 10px;white-space:pre-wrap">' + escHtml(rl.focus) + '</div>';
          }
          
          // 风险表格
          if (rl.risk_table) {
            card += '<div style="font-size:12px;font-weight:600;color:#16233a;margin:8px 0 4px;border-bottom:1px solid #e2e8f0;padding-bottom:4px">触发的稽查风险点</div>';
            card += '<table style="width:100%;border-collapse:collapse;font-size:10px;margin:4px 0 10px"><tr style="background:#fef2f2"><td style="padding:3px 6px;border:1px solid #fcc;font-weight:600;width:80px">风险维度</td><td style="padding:3px 6px;border:1px solid #fcc">风险点描述</td></tr>';
            var rows = typeof rl.risk_table === 'string' ? rl.risk_table.split('\n') :
  (Array.isArray(rl.risk_table) ? rl.risk_table.map(function(rr){
    var tax = rr.税种 || rr.tax || rr.name || '';
    var desc = rr.具体风险描述 || rr.风险描述 || rr.desc || rr.描述 || '';
    return tax + ':' + desc;
  }) : []);
            for (var ri = 0; ri < rows.length; ri++) {
              var parts = rows[ri].split(':');
              if (parts.length >= 2) {
                card += '<tr><td style="padding:3px 6px;border:1px solid #e2e8f0;font-weight:600">' + escHtml(parts[0]) + '</td><td style="padding:3px 6px;border:1px solid #e2e8f0">' + escHtml(parts.slice(1).join(':')) + '</td></tr>';
              }
            }
            card += '</table>';
          }
          
          // 正常业务解释
          if (rl.normal_reason) {
            card += '<div style="font-size:12px;font-weight:600;color:#16233a;margin:8px 0 4px;border-bottom:1px solid #e2e8f0;padding-bottom:4px">可能的业务解释（正常情形）</div>';
            card += '<div style="font-size:11px;color:#059669;line-height:2;margin:4px 0 10px;padding:8px 12px;background:#f0fdf4;border-radius:6px;white-space:pre-wrap">' + escHtml(rl.normal_reason) + '</div>';
          }
          
          // 定性路径
          if (rl.determination) {
            card += '<div style="font-size:12px;font-weight:600;color:#16233a;margin:8px 0 4px;border-bottom:1px solid #e2e8f0;padding-bottom:4px">稽查定性路径</div>';
            card += '<div style="font-size:11px;color:#3a4048;line-height:2;margin:4px 0 10px;white-space:pre-wrap">' + escHtml(rl.determination) + '</div>';
          }
          
          // 穿透式追问（整段完整展示，忠实原文换行，不做正则截取）
          if (rl.drill_questions) {
            card += '<div style="font-size:12px;font-weight:600;color:#16233a;margin:8px 0 4px;border-bottom:1px solid #e2e8f0;padding-bottom:4px">稽查常见穿透式追问与应对</div>';
            var dq = typeof rl.drill_questions === 'string' ? rl.drill_questions : (Array.isArray(rl.drill_questions) ? rl.drill_questions.join('\n') : '');
            card += '<div style="font-size:11px;color:#3a4048;line-height:2;margin:4px 0 10px;padding:8px 12px;background:#fef8f8;border-left:3px solid #9a1f2b;border-radius:0 6px 6px 0;white-space:pre-wrap">' + escHtml(dq) + '</div>';
          }
          
          // 传统字段（兼容未升级的规则）
          card += (rl.action ? '<div style="font-size:11px;color:#3a4048;margin:2px 0 4px;white-space:pre-wrap">🔍 核查动作：' + escHtml(rl.action) + '</div>' : '')
            + (rl.threshold && !rl.threshold.startsWith('评分阈值') ? '<div style="font-size:10px;color:#94a3b8;margin:2px 0;white-space:pre-wrap">📏 触发指标：' + escHtml(rl.threshold) + '</div>' : '')
            + (rl.evidence ? '<div style="font-size:10px;color:#94a3b8;margin:2px 0;white-space:pre-wrap">📎 证据清单：' + escHtml(rl.evidence) + '</div>' : '')
            + (rl.policy_ref ? '<div class="ra" style="white-space:pre-wrap">📜 法律依据：' + escHtml(rl.policy_ref) + '</div>' : '')
            + (rl.suggestion ? '<div class="ra" style="white-space:pre-wrap">⚖ 稽查处理：' + escHtml(rl.suggestion) + '</div>' : '')
            + (rl.tax_impact ? '<div class="ra" style="white-space:pre-wrap">💰 税务影响：' + escHtml(rl.tax_impact) + '</div>' : '')
            + (rl.remedy && rl.remedy !== rl.suggestion ? '<div class="ra" style="white-space:pre-wrap">🔧 整改建议：' + escHtml(rl.remedy) + '</div>' : '')
            + (rl.applicable_condition ? '<div class="ra" style="white-space:pre-wrap">📋 适用条件：' + escHtml(rl.applicable_condition) + '</div>' : '');
          card += '</div>';
          html += card;
        });
        list.innerHTML = html;
      };
      window._rrFilter();
    })
    .catch(function(e) {
      var list = document.getElementById('rr-list');
      if (list) list.innerHTML = '<div style="text-align:center;padding:24px;color:#dc2626">规则库加载失败：' + escHtml(e.message) + '</div>';
    });
}

function toggleTriggeredOnly() {
  _showTriggeredOnly = !_showTriggeredOnly;
  var btn = document.getElementById('rr-trigger-btn');
  if (btn) {
    btn.style.background = _showTriggeredOnly ? '#eff6ff' : '#fff';
    btn.style.borderColor = _showTriggeredOnly ? '#2563eb' : '#e2e8f0';
    btn.style.color = _showTriggeredOnly ? '#2563eb' : '#0f172a';
  }
  filterRules();
}

var _currentSort = 'time';  // 当前排序模式

function sortAndRenderRules() {
  var sel = document.getElementById('rr-sort-filter');
  _currentSort = sel?.value || 'time';
  renderTaxRiskRulesList();
  filterRules();
}

async function promoteAutoRule(ruleId, btn) {
  if (!confirm('确定将这条自动发现规则升级为正式规则？')) return;
  btn.disabled = true;
  btn.textContent = '...';
  try {
    var r = await fetch('/api/tax-risk-rules/promote-auto-rule?rule_id=' + ruleId, { method: 'POST' });
    var d = await r.json();
    if (d.ok) {
      btn.textContent = '✓ 已确认';
      btn.style.background = '#059669';
      btn.style.color = '#fff';
      // 2秒后刷新规则列表
      setTimeout(function(){ loadTaxRiskRules(); }, 1500);
    } else {
      alert(d.message || '操作失败');
      btn.disabled = false;
      btn.textContent = '✗ 重试';
    }
  } catch(e) {
    btn.disabled = false;
    btn.textContent = '✗ 重试';
  }
}

// ═══ 规则编辑面板 ═══
function toggleRuleEdit(ruleId, btn) {
  var card = btn.closest('[data-rule-id]');
  if (!card) return;
  var existing = card.querySelector('.rr-edit-panel');
  if (existing) { existing.remove(); return; }  // 关闭
  // 读取当前值
  var rule = (taxRiskRulesData || []).find(function(r){ return String(r.id||'') === ruleId; });
  if (!rule) return;
  var fields = [
    {k:'item',label:'指令名称',v:rule.item||''},
    {k:'level',label:'风险等级',v:rule.level||'',type:'select',opts:['高风险','中风险','低风险','良好']},
    {k:'score',label:'评分',v:rule.score||''},
    {k:'detail',label:'详细标准',v:rule.detail||'',ta:true},
    {k:'suggestion',label:'税务合规建议',v:rule.suggestion||'',ta:true},
    {k:'evidence',label:'所需佐证',v:rule.evidence||'',ta:true},
    {k:'tax_impact',label:'税务影响',v:rule.tax_impact||'',ta:true},
    {k:'policy_ref',label:'法律依据',v:rule.policy_ref||'',ta:true},
    {k:'category',label:'分类',v:rule.category||''},
    {k:'dataSource',label:'数据来源',v:rule.dataSource||''},
    {k:'detectable',label:'可检测性',v:rule.detectable||''},
  ];
  var h = '<div class="rr-edit-panel" style="margin:12px 0;padding:16px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px">';
  h += '<div style="font-size:12px;font-weight:600;color:#1e293b;margin-bottom:12px">✏️ 编辑规则 ' + ruleId + '</div>';
  fields.forEach(function(f){
    h += '<div style="margin-bottom:8px"><span style="font-size:10px;color:#94a3b8">' + f.label + '</span>';
    if (f.type === 'select') {
      h += '<select id="rr-edit-' + f.k + '" style="width:100%;font-size:11px;padding:4px 8px;border:1px solid #e2e8f0;border-radius:4px;margin-top:2px">';
      (f.opts||[]).forEach(function(o){ h += '<option ' + (o===f.v?'selected':'') + '>' + o + '</option>'; });
      h += '</select>';
    } else if (f.ta) {
      h += '<textarea id="rr-edit-' + f.k + '" rows="2" style="width:100%;font-size:11px;padding:4px 8px;border:1px solid #e2e8f0;border-radius:4px;margin-top:2px;resize:vertical">' + escHtml(String(f.v)) + '</textarea>';
    } else {
      h += '<input id="rr-edit-' + f.k + '" value="' + escHtml(String(f.v)) + '" style="width:100%;font-size:11px;padding:4px 8px;border:1px solid #e2e8f0;border-radius:4px;margin-top:2px">';
    }
    h += '</div>';
  });
  h += '<div style="display:flex;gap:8px;margin-top:12px">';
  h += '<button onclick="saveRuleEdit(\'' + ruleId + '\',this)" style="font-size:11px;padding:5px 16px;border:none;border-radius:4px;background:#2563eb;color:#fff;cursor:pointer;font-weight:600">保存</button>';
  h += '<button onclick="toggleRuleEdit(\'' + ruleId + '\',this)" style="font-size:11px;padding:5px 16px;border:1px solid #e2e8f0;border-radius:4px;background:#fff;color:#64748b;cursor:pointer">取消</button>';
  h += '</div></div>';
  card.insertAdjacentHTML('beforeend', h);
}

async function saveRuleEdit(ruleId, btn) {
  var card = btn.closest('[data-rule-id]');
  if (!card) return;
  var fields = ['item','level','score','detail','suggestion','evidence','tax_impact','policy_ref','category','dataSource','detectable'];
  var body = {rule_id: ruleId};
  fields.forEach(function(k){
    var el = card.querySelector('#rr-edit-'+k);
    if (el) body[k] = el.value || '';
  });
  btn.disabled = true;
  btn.textContent = '保存中...';
  try {
    var r = await fetch('/api/tax-risk-rules/update-rule', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    var d = await r.json();
    if (d.ok) {
      var panel = card.querySelector('.rr-edit-panel');
      if (panel) panel.innerHTML = '<div style="color:#059669;font-weight:600;font-size:12px;padding:8px">✓ 已保存（' + d.changed.length + '字段）· 1.5秒后刷新</div>';
      setTimeout(function(){ loadTaxRiskRules(); }, 1500);
    } else { alert(d.message); btn.disabled = false; btn.textContent = '保存'; }
  } catch(e) { btn.disabled = false; btn.textContent = '重试'; }
}

async function batchRefreshRules(btn) {
  if (!confirm('统一刷新全部人工规则的时效标记？此操作会备份原文件。')) return;
  btn.disabled = true;
  btn.textContent = '刷新中...';
  try {
    var r = await fetch('/api/tax-risk-rules/batch-refresh', {method:'POST'});
    var d = await r.json();
    if (d.ok) { alert(d.message); loadTaxRiskRules(); }
    else { alert(d.message); btn.disabled = false; btn.textContent = '🔄 统一刷新政策法律'; }
  } catch(e) { btn.disabled = false; btn.textContent = '重试'; }
}

function filterRules() {
  var search = (document.getElementById('rr-search')?.value || '').toLowerCase();
  var level = document.getElementById('rr-level-filter')?.value || '';
  var cat = document.getElementById('rr-cat-filter')?.value || '';
  var rtype = document.getElementById('rr-type-filter')?.value || '';
  
  var listEl = document.getElementById('risk-rules-list');
  if (!listEl) return;
  
  var allCards = listEl.querySelectorAll('[data-rule-id]');
  var visible = 0;
  
  allCards.forEach(function(card) {
    var text = (card.textContent || '').toLowerCase();
    var ruleLevel = card.getAttribute('data-level') || '';
    var ruleCat = card.getAttribute('data-category') || '';
    var ruleType = card.getAttribute('data-type') || '';
    var triggered = card.getAttribute('data-triggered') === '1';
    
    var matches = true;
    if (search && text.indexOf(search) < 0) matches = false;
    if (level && ruleLevel !== level) matches = false;
    if (cat && ruleCat !== cat) matches = false;
    if (rtype && ruleType !== rtype) matches = false;
    if (_showTriggeredOnly && !triggered) matches = false;
    
    card.style.display = matches ? '' : 'none';
    if (matches) visible++;
    
    // Also show/hide parent category header
    var header = card.closest('[id^="rr-cat-"]');
    if (header) {
      var anyVisible = header.querySelectorAll('[data-rule-id]:not([style*="display: none"])').length > 0;
      header.style.display = anyVisible ? '' : 'none';
    }
  });
  
  var cntEl = document.getElementById('rr-filter-count');
  if (cntEl) cntEl.textContent = '显示 ' + visible + ' 条';
}

async function loadTaxRiskRules() {
  await loadDefaultTaxRiskRules();
}

async function loadDefaultTaxRiskRules() {
  try {
    var resp = await fetch('/static/tax_risk_rules_local_export.json?_t=' + Date.now());
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    var rules = await resp.json();
    if (!Array.isArray(rules) || rules.length === 0) throw new Error('数据为空');
    taxRiskRulesData = rules;
    try { localStorage.setItem('taxRiskRulesData', JSON.stringify(rules)); } catch(e) {}
    // 记录数据更新时间（从HTTP响应头取Last-Modified）
    try {
      var lm = resp.headers.get('Last-Modified');
      if (lm) { window._rulesUpdateTime = lm; }
    } catch(e) {}
    
    // 先加载触发溯源数据，再渲染
    await loadTriggeredRules();
    renderTaxRiskRulesList();
  } catch (e) {
    var el = document.getElementById('risk-rules-list');
    if (el) el.innerHTML = '<div style="text-align:center;padding:40px;color:#dc2626">加载失败: ' + e.message + '</div>';
  }
}

async function loadTriggeredRules() {
  _triggeredRuleFindings = {};
  try {
    if (typeof getSharedAnalysis === 'function') {
      var sa = await getSharedAnalysis();
      if (sa && sa.ok && sa.report) {
        (sa.report.all_findings || []).forEach(function(f) {
          var rid = String(f.rule_id || '').trim();
          if (!rid) return;
          if (!_triggeredRuleFindings[rid]) _triggeredRuleFindings[rid] = [];
          _triggeredRuleFindings[rid].push({
            type: f.type || f.domain || '',
            domain: f.domain || '',
            detail: f.detail || '',
            level: f.level || '',
            score: f.score || 0
          });
        });
      }
    }
  } catch(e) {}
}

function renderTaxRiskRulesList() {
  var data = taxRiskRulesData;
  var listEl = document.getElementById('risk-rules-list');
  var statsEl = document.getElementById('risk-rules-stats');
  if (!listEl) return;

  var triggeredCount = Object.keys(_triggeredRuleFindings).length;
  var countEl = document.getElementById('risk-rules-count');
  var triggerText = triggeredCount > 0 ? '（本次触发 <span style="color:#dc2626;font-weight:600">' + triggeredCount + '</span> 条）' : '（暂无触发）';
  var sortNames = {time:'按时间排序', high:'高风险优先', low:'低风险优先', trigger:'触发优先'};
  var sortName = sortNames[_currentSort] || '按时间排序';
  var timeStr = window._rulesUpdateTime ? ' · 数据更新于 ' + window._rulesUpdateTime : '';
  if (countEl) countEl.innerHTML = data.length + ' 条税务疑点 ' + triggerText + ' · ' + sortName + ' · 支持搜索筛选' + timeStr;

  if (data.length === 0) {
    listEl.innerHTML = '<div style="padding:40px 0;font-size:12px;color:#94a3b8">暂无税务疑点，请加载数据</div>';
    return;
  }

  // 排序
  var sortedData = data.slice();
  if (_currentSort === 'high') {
    var lv={'极高风险':0,'高风险':1,'中风险':2,'低风险':3,'良好':4};
    sortedData.sort(function(a,b){return (lv[a.level||'']||9)-(lv[b.level||'']||9);});
  } else if (_currentSort === 'low') {
    var lv2={'极高风险':4,'高风险':3,'中风险':2,'低风险':1,'良好':0};
    sortedData.sort(function(a,b){return (lv2[a.level||'']||9)-(lv2[b.level||'']||9);});
  } else if (_currentSort === 'trigger') {
    sortedData.sort(function(a,b){
      var ta=(_triggeredRuleFindings[String(a.id||'').trim()]||[]).length;
      var tb=(_triggeredRuleFindings[String(b.id||'').trim()]||[]).length;
      return tb-ta || ((b.id||0)-(a.id||0));
    });
  } else {
    // 按生成时间（ID越大越新）
    sortedData.sort(function(a, b) { return (b.id || 0) - (a.id || 0); });
  }

  // 统计 — 填充顶部卡片
  var high = data.filter(function(r) { return (r.level === '极高风险' || r.level === '高风险'); }).length;
  var mid = data.filter(function(r) { return r.level === '中风险'; }).length;
  var low = data.filter(function(r) { return r.level === '低风险' || r.level === '良好'; }).length;
  _fillEl('tr-total', data.length);
  _fillEl('tr-high', high);
  _fillEl('tr-mid', mid);
  _fillEl('tr-low', low);
  _fillEl('tr-trigger', triggeredCount);

  var html = '';

  // 按生成时间渲染所有指令
  sortedData.forEach(function(rule) {
      // 自动发现规则的字段映射
      var isAutoRule = rule.type === 'auto_signal' || rule.source === '系统发现' || !!rule.auto_type;
      var itemName = rule.item || rule.signal || '';
      var levelName = rule.level || rule.severity || '';
      var scoreVal = rule.score !== undefined ? rule.score : (rule.confidence !== undefined ? Math.round(rule.confidence * 10) : '-');
      var detailText = rule.detail || '';
      var suggestText = rule.suggestion || rule.action || '';
      var evidenceText = rule.evidence || '';
      var impactText = rule.tax_impact || '';
      var policyText = rule.policy_ref || '';
      
      // 自动发现规则用蓝色标识
      var color = isAutoRule ? '#2563eb' : (RISK_LEVEL_COLORS[levelName] || '#64748b');
      var icon = isAutoRule ? '🤖' : (RISK_LEVEL_ICONS[levelName] || '⚪');
      var rid = String(rule.id || '').trim();
      var triggered = _triggeredRuleFindings[rid] || [];
      var isTriggered = triggered.length > 0;
      var borderColor = isTriggered ? '#dc2626' : color;
      var borderWidth = isTriggered ? '4px' : '3px';

      html += '<div data-rule-id="' + rid + '" data-level="' + (levelName || '') + '" data-triggered="' + (isTriggered ? '1' : '0') + '" data-category="' + (rule.category || '') + '" data-type="' + (isAutoRule ? 'auto' : 'manual') + '"'
        + ' style="padding:14px 18px;margin-bottom:8px;background:#fff;border:1px solid #e2e8f0;border-left:' + borderWidth + ' solid ' + borderColor + ';border-radius:6px" class="tr-rule-card">'
        
        // 标题行
        + '<div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:6px">'
        + '<div style="font-size:13px;font-weight:600;color:#0f172a">'
        + (isAutoRule ? '🤖 ' : '') + escHtml(itemName)
        + (isAutoRule ? '<span style="margin-left:6px;font-size:11px;font-weight:400;color:#64748b">[' + escHtml(rule.industry || '') + ']</span>' : '')
        + (isTriggered ? '<span style="margin-left:8px;font-size:11px;padding:2px 8px;border-radius:4px;background:#fef2f2;color:#dc2626;font-weight:600">✅ 本次触发(' + triggered.length + ')</span>' : '')
        + '</div>'
        + '<div style="display:flex;gap:8px;align-items:center;flex-shrink:0;margin-left:16px">'
        + (isAutoRule 
            ? '<span style="font-size:11px;padding:2px 8px;border-radius:4px;background:#eff6ff;color:#2563eb;font-weight:600">🤖 自动发现</span>'
            : '<span style="font-size:11px;padding:2px 8px;border-radius:4px;background:' + color + '15;color:' + color + ';font-weight:600">' + icon + ' ' + (levelName || '') + '</span>')
        + (!isAutoRule ? '<button onclick="toggleRuleEdit(\'' + rid + '\',this)" style="font-size:10px;padding:2px 8px;border:1px solid #cbd5e1;border-radius:4px;background:#fff;color:#64748b;cursor:pointer">✏️</button>' : '')
        + (isAutoRule 
            ? '<span style="font-size:11px;color:#94a3b8">置信度 ' + (rule.confidence !== undefined ? Math.round(rule.confidence * 100) + '%' : '-') + '</span>'
            + '<button onclick="promoteAutoRule(\'' + rid + '\',this)" style="font-size:10px;padding:3px 10px;border:1px solid #059669;border-radius:4px;background:#ecfdf5;color:#059669;cursor:pointer;font-weight:600">✓ 确认为正式规则</button>'
            : '<span style="font-size:11px;color:#94a3b8">评分 ' + scoreVal + '</span>')
        + (rid ? '<span style="font-size:10px;color:#94a3b8">ID:' + rid + '</span>' : '')
        + '</div>'
        + '</div>'

        // 触发溯源
        + (isTriggered ? '<div style="margin-bottom:6px;padding:8px 12px;background:#fef2f2;border-radius:4px;font-size:11px;line-height:2.0">'
        + '<div style="font-weight:600;color:#991b1b;margin-bottom:4px">🔗 触发溯源：</div>'
        + triggered.map(function(t) {
            return '<div style="color:#7f1d1d">→ <strong>' + escHtml(t.domain || t.type || '') + '</strong>' + (t.detail ? ': ' + escHtml(t.detail.substring(0, 150)) : '') + (t.level ? ' [' + t.level + ']' : '') + '</div>';
          }).join('')
        + '</div>' : '')

        // 详细内容 —— 自动发现规则也展示7段式字段
        + (rule.phenomena ? '<div style="font-size:11px;color:#475569;line-height:2.0;margin-bottom:4px"><b>现象：</b>' + escHtml(rule.phenomena) + '</div>' : '')
        + (rule.direction ? '<div style="font-size:11px;color:#475569;line-height:2.0;margin-bottom:4px"><b>逻辑：</b>' + escHtml(rule.direction) + '</div>' : '')
        + (rule.focus && rule.focus !== '待明确重点' ? '<div style="font-size:11px;color:#dc2626;line-height:2.0;margin-bottom:4px"><b>重点：</b>' + escHtml(rule.focus) + '</div>' : '')
        + (rule.drill_questions ? '<div style="font-size:11px;color:#475569;line-height:2.0;margin-bottom:4px"><b>追问：</b>' + escHtml(rule.drill_questions.replace(/\n/g,'<br>')) + '</div>' : '')
        + (detailText ? '<div style="font-size:12px;color:#475569;line-height:2.0;margin-bottom:6px">' + escHtml(detailText) + '</div>' : '')
        + (rule.normal_reason && rule.normal_reason.length > 20 ? '<div style="font-size:11px;color:#059669;line-height:2.0;margin-bottom:4px"><b>正常解释：</b>' + escHtml(rule.normal_reason) + '</div>' : '')
        + (rule.risk_table ? '<div style="font-size:11px;color:#dc2626;line-height:2.0;margin-bottom:4px"><b>风险：</b>' + escHtml(rule.risk_table).replace(/\n/g,'<br>') + '</div>' : '')

        // 建议 + 佐证
        + (suggestText ? '<div style="font-size:12px;color:#334155;line-height:2.0;margin-bottom:4px"><span style="font-weight:600;color:#0f172a">' + (isAutoRule ? '系统建议：' : '税务合规建议：') + '</span>' + escHtml(suggestText) + '</div>' : '')
        + (evidenceText ? '<div style="font-size:12px;color:#334155;line-height:2.0;margin-bottom:4px"><span style="font-weight:600;color:#0f172a">' + (isAutoRule ? '发现依据：' : '所需佐证：') + '</span>' + escHtml(evidenceText) + '</div>' : '')

        // 自动发现额外信息
        + (isAutoRule ? '<div style="font-size:12px;color:#334155;line-height:2.0;margin-bottom:4px"><span style="font-weight:600;color:#0f172a">信号出现率：</span>' + escHtml(rule.prevalence || '') + '</div>' : '')
        + (isAutoRule && rule.auto_discovered_at ? '<div style="font-size:12px;color:#334155;line-height:2.0;margin-bottom:4px"><span style="font-weight:600;color:#0f172a">自动发现时间：</span>' + escHtml(rule.auto_discovered_at.substring(0, 19)) + '</div>' : '')

        // 底栏
        + '<div style="display:flex;gap:16px;flex-wrap:wrap;margin-top:6px;padding-top:6px;border-top:1px solid #e2e8f0;font-size:11px;color:#94a3b8">'
        + (impactText ? '<span><span style="color:#64748b">税务影响：</span>' + escHtml(impactText.substring(0, 120)) + (impactText.length > 120 ? '...' : '') + '</span>' : '')
        + (policyText ? '<span><span style="color:#64748b">法条：</span>' + escHtml(policyText.substring(0, 100)) + (policyText.length > 100 ? '...' : '') + '</span>' : '')
        + (rule.dataSource ? '<span><span style="color:#64748b">数据源：</span>' + escHtml(rule.dataSource) + '</span>' : '')
        + (rule.detectable !== undefined ? '<span>' + (rule.detectable ? '✅ 可自动检测' : '⚠️ 需人工') + '</span>' : '')
        + '</div>'
        + '</div>';
    });

  listEl.innerHTML = html;

  if (statsEl) {
    statsEl.innerHTML = '共 ' + data.length + ' 条税务疑点 · '
      + '<span style="color:#dc2626">高 ' + high + '</span> · '
      + '<span style="color:#f59e0b">中 ' + mid + '</span> · '
      + '<span style="color:#10b981">低/良 ' + low + '</span> · '
      + '按ID排序';
  }
  
  // 初始化筛选计数
  var cntEl = document.getElementById('rr-filter-count');
  if (cntEl) cntEl.textContent = '显示 ' + data.length + ' 条';
}

function _fillEl(id, val) {
  var el = document.getElementById(id);
  if (el) el.textContent = val;
}

window._smartUpdate = function() {
  
  
  var st = document.getElementById('rr-update-status');
  var btn = document.getElementById('rr-update-btn');
  if (st) st.textContent = '分析中...';
  if (btn) { btn.disabled = true; btn.textContent = '分析中...'; }
  fetch('/api/tax-risk-rules/smart-update', {method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})
    .then(function(r){return r.json();})
    .then(function(d){
      var now = new Date().toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});
      var tu = document.getElementById('rr-update-time'); if (tu) tu.textContent = '最后更新 ' + now;
      if (st) st.textContent = d.ok ? '完成' : '失败';
      if (btn) { btn.disabled = false; btn.textContent = d.ok ? '🤖 再次更新' : '🤖 重试'; }
      if (!d.ok) { alert('更新失败: ' + (d.message||'')); return; }
      var c = d.compare || {};
      var total = (c.new_count||0) + (c.modify_count||0) + (c.delete_count||0);
      // 弹窗提示结果
      if (total === 0) {
        alert('✅ 智能更新完成：当前规则库已覆盖完善，无更新建议。');
      } else {
        alert('✅ 智能更新完成：新增 '+(c.new_count||0)+' 条 / 修改 '+(c.modify_count||0)+' 条 / 删除 '+(c.delete_count||0)+' 条\n详情见下方对比报告 →');
      }
      var cp = document.getElementById('rr-compare');
      if (!cp) return;
      if (total === 0) {
        cp.innerHTML = '<div style="font-size:14px;font-weight:700;color:#059669;margin:0 0 8px">✅ 本次分析无更新建议</div><div style="font-size:12px;color:#5b6675">依据9个维度全面扫描，当前规则库已覆盖完善，无需新增、修改或删除。规则库状态：' + (c.before_total||0) + '条。</div>';
        cp.style.display = 'block';
        return;
      }
      var h = '<div style="font-size:14px;font-weight:700;color:#9a1f2b;margin:0 0 12px">📊 智能更新对比报告</div>';
      h += '<div style="font-size:12px;color:#5b6675;margin:0 0 12px">' + escHtml(c.summary||'') + '</div>';
      h += '<div style="display:flex;gap:16px;margin:0 0 12px;flex-wrap:wrap"><div style="flex:1;min-width:80px;text-align:center;padding:10px;background:#f0fdf4;border-radius:6px"><div style="font-size:18px;font-weight:700;color:#059669">' + (c.new_count||0) + '</div><div style="font-size:10px;color:#64748b">建议新增</div></div><div style="flex:1;min-width:80px;text-align:center;padding:10px;background:#fff7ed;border-radius:6px"><div style="font-size:18px;font-weight:700;color:#f59e0b">' + (c.modify_count||0) + '</div><div style="font-size:10px;color:#64748b">建议修改</div></div><div style="flex:1;min-width:80px;text-align:center;padding:10px;background:#fef2f2;border-radius:6px"><div style="font-size:18px;font-weight:700;color:#dc2626">' + (c.delete_count||0) + '</div><div style="font-size:10px;color:#64748b">建议删除</div></div></div>';
      h += '<div style="font-size:11px;color:#64748b">更新前: ' + (c.before_total||0) + '条 → 更新后: ' + (c.after_total||0) + '条</div>';
      if (c.new_rules && c.new_rules.length) {
        h += '<div style="margin:12px 0"><div style="font-size:12px;font-weight:600;color:#059669;margin:8px 0">新增规则</div>';
        c.new_rules.forEach(function(r,i){
          h += '<div style="margin:6px 0;padding:10px 14px;background:#f0fdf4;border-radius:6px;border-left:3px solid #059669;font-size:11px;line-height:1.8">';
          h += '<b style="color:#0f172a">#'+(i+1)+' '+escHtml(r.item||'无名称')+'</b>';
          h += ' <span style="display:inline-block;padding:1px 6px;border-radius:3px;font-size:9px;background:#e0f2fe;color:#0369a1">'+escHtml(r.category||'')+'</span>';
          h += ' <span style="display:inline-block;padding:1px 6px;border-radius:3px;font-size:9px;background:#fef3c7;color:#92400e">'+escHtml(r.level||'')+'</span>';
          if (r.detail) h += '<div style="color:#475569;margin:4px 0">'+escHtml(r.detail).substring(0,200)+'</div>';
          if (r.direction) h += '<div style="color:#64748b;font-size:10px;margin:2px 0">推理链：'+escHtml(r.direction).substring(0,150)+'</div>';
          if (r.policy_ref) h += '<div style="color:#94a3b8;font-size:10px">📜 '+escHtml(r.policy_ref)+'</div>';
          h += '</div>';
        });
        h += '</div>';
      }
      if (c.modify && c.modify.length) {
        h += '<div style="margin:12px 0"><div style="font-size:12px;font-weight:600;color:#f59e0b;margin:8px 0">修改建议</div>';
        h += '<table style="width:100%;border-collapse:collapse;font-size:11px"><tr style="background:#fff7ed"><td style="padding:6px 8px;border:1px solid #fed7aa;font-weight:600">ID</td><td style="padding:6px 8px;border:1px solid #fed7aa;font-weight:600">原名称</td><td style="padding:6px 8px;border:1px solid #fed7aa;font-weight:600;color:#059669">建议改为</td><td style="padding:6px 8px;border:1px solid #fed7aa;font-weight:600">原因</td></tr>';
        c.modify.forEach(function(r){
          h += '<tr><td style="padding:6px 8px;border:1px solid #e2e8f0;font-weight:600">'+(r.id||'?')+'</td>';
          h += '<td style="padding:6px 8px;border:1px solid #e2e8f0;color:#dc2626">'+escHtml(r.old_item||'')+'</td>';
          h += '<td style="padding:6px 8px;border:1px solid #e2e8f0;color:#059669;font-weight:600">'+escHtml(r.new_item||r.reason||'')+'</td>';
          h += '<td style="padding:6px 8px;border:1px solid #e2e8f0;font-size:10px">'+(r.reason !== r.new_item ? escHtml(r.reason||'') : '')+'</td></tr>';
        });
        h += '</table></div>';
      }
      if (c.delete && c.delete.length) {
        h += '<div style="margin:12px 0"><div style="font-size:12px;font-weight:600;color:#dc2626;margin:8px 0">删除建议</div>';
        c.delete.forEach(function(r){
          h += '<div style="margin:4px 0;padding:8px 12px;background:#fef2f2;border-radius:6px;border-left:3px solid #dc2626;font-size:11px">';
          h += '<b>ID['+escHtml(r.id||'')+']</b> '+escHtml(r.item||'')+'';
          if (r.reason) h += ' <span style="color:#9ca3af;font-size:10px">— '+escHtml(r.reason).substring(0,100)+'</span>';
          h += '</div>';
        });
        h += '</div>';
      }
      h += '<div style="margin:12px 0 0;font-size:10px;color:#94a3b8">以上为LLM建议，请人工审核确认后再执行更新操作。</div>';
      cp.innerHTML = h;
      cp.style.display = 'block';
      cp.scrollIntoView({behavior:'smooth',block:'center'});
    })
    .catch(function(e){
      if (st) st.textContent = '异常';
      if (btn) { btn.disabled = false; btn.textContent = '🤖 重试'; }
      alert('请求异常: ' + e.message);
    });
};

