/**
 * 税务稽查员手册
 * 系统总结税务稽查工作要求、报告编制规范、法律依据、方法论
 * 全行业适用——所有规则和标准均为通用准则，不针对特定行业
 */

// ═══════════════════════════════════════
// 主渲染函数
// ═══════════════════════════════════════
function renderAuditorHandbook(container) {
  if (!container) return;
  window.currentModule = '税务稽查员手册';

  var html = '';
  html += '<div style="margin-bottom:24px;">';
  html += '<h2 style="font-size:24px;font-weight:700;color:#0f172a;margin:0 0 6px;">⚖️ 税务稽查员手册</h2>';
  html += '<p style="font-size:14px;color:#94a3b8;margin:0;">系统总结税务稽查工作要求、报告编制规范、法律依据与稽查方法论。以下内容提炼自《税务稽查工作规程》《税收征收管理法》及实战经验，全行业适用。</p>';
  html += '</div>';

  // ═══ 导航标签 ═══
  html += '<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:20px;">';
  html += '<button class="btn btn-sm" onclick="scrollToSection(\'workflow\')">📋 稽查工作流程</button>';
  html += '<button class="btn btn-sm" onclick="scrollToSection(\'documents\')">📁 14类必查资料</button>';
  html += '<button class="btn btn-sm" onclick="scrollToSection(\'report\')">📝 报告编制规范</button>';
  html += '<button class="btn btn-sm" onclick="scrollToSection(\'laws\')">⚖️ 关键法律条文</button>';
  html += '<button class="btn btn-sm" onclick="scrollToSection(\'methodology\')">🔬 稽查方法论</button>';
  html += '</div>';

  // ═══════════════════════════════════════
  // 第一部分：稽查工作流程
  // ═══════════════════════════════════════
  html += '<div id="workflow" class="card" style="margin-bottom:20px;">';
  html += '<h2 style="border-left:4px solid #dc2626;padding-left:12px;">📋 一、稽查工作流程</h2>';
  html += '<p class="muted">税务稽查分为四个阶段：选案→检查→审理→执行。每个阶段有明确的法定时限和工作要求。</p>';

  html += '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;margin-top:16px;">';

  // 选案
  html += '<div class="card" style="border-top:3px solid #2563eb;">';
  html += '<h3>① 选案环节</h3>';
  html += '<table class="table table-sm"><tbody>';
  html += '<tr><td style="white-space:nowrap;font-weight:600;width:90px;">数据来源</td><td>金税系统风险预警、举报线索、行业专项检查、随机抽查、上下游协查</td></tr>';
  html += '<tr><td style="font-weight:600;">选案标准</td><td>税负率异常、发票数据异常、申报数据与第三方数据（电力/海关/银行）差异、长期零申报/亏损、关联交易异常</td></tr>';
  html += '<tr><td style="font-weight:600;">时限</td><td>收到案源后15日内确定是否立案</td></tr>';
  html += '<tr><td style="font-weight:600;">法律依据</td><td>《税务稽查工作规程》第十三条至第十九条</td></tr>';
  html += '</tbody></table>';
  html += '</div>';

  // 检查
  html += '<div class="card" style="border-top:3px solid #f59e0b;">';
  html += '<h3>② 检查环节</h3>';
  html += '<table class="table table-sm"><tbody>';
  html += '<tr><td style="white-space:nowrap;font-weight:600;width:90px;">启动方式</td><td>下达《税务检查通知书》→送达《调取账簿资料通知书》→企业3-5日内提供资料</td></tr>';
  html += '<tr><td style="font-weight:600;">资料调取</td><td>14类稽查必查资料（详见第二部分），企业有义务提供完整的会计凭证、账簿、报表、合同、银行流水</td></tr>';
  html += '<tr><td style="font-weight:600;">检查方法</td><td>账簿检查、实地核查、询问、外部调查（银行/上下游企业/海关）、电子数据取证</td></tr>';
  html += '<tr><td style="font-weight:600;">时限</td><td>一般案件60日内完成检查，重大案件可延长</td></tr>';
  html += '<tr><td style="font-weight:600;">法律依据</td><td>《税收征收管理法》第五十四条；《税务稽查工作规程》第二十二条至第三十七条</td></tr>';
  html += '</tbody></table>';
  html += '</div>';

  // 审理
  html += '<div class="card" style="border-top:3px solid #10b981;">';
  html += '<h3>③ 审理环节</h3>';
  html += '<table class="table table-sm"><tbody>';
  html += '<tr><td style="white-space:nowrap;font-weight:600;width:90px;">审理内容</td><td>①违法事实是否清楚→证据是否确实充分→数据是否准确 ②适用法律是否正确 ③程序是否合法 ④处理意见是否适当</td></tr>';
  html += '<tr><td style="font-weight:600;">关键标准</td><td>每一笔认定的税款必须有对应的法律条款+证据支撑。证据链必须形成闭环——不能凭单一来源数据定案</td></tr>';
  html += '<tr><td style="font-weight:600;">时限</td><td>收到检查报告后15日内完成审理</td></tr>';
  html += '<tr><td style="font-weight:600;">法律依据</td><td>《税务稽查工作规程》第三十八条至第四十六条</td></tr>';
  html += '</tbody></table>';
  html += '</div>';

  // 执行
  html += '<div class="card" style="border-top:3px solid #8b5cf6;">';
  html += '<h3>④ 执行环节</h3>';
  html += '<table class="table table-sm"><tbody>';
  html += '<tr><td style="white-space:nowrap;font-weight:600;width:90px;">执行文书</td><td>下达《税务处理决定书》+《税务行政处罚决定书》→责令限期缴纳税款、滞纳金、罚款</td></tr>';
  html += '<tr><td style="font-weight:600;">企业权利</td><td>①60日内申请行政复议 ②复议后15日内提起诉讼 ③缴纳税款或提供担保后可申请复议</td></tr>';
  html += '<tr><td style="font-weight:600;">强制执行</td><td>逾期不履行→加收每日万分之五滞纳金→采取税收保全措施（冻结存款/查封财产）→申请法院强制执行</td></tr>';
  html += '<tr><td style="font-weight:600;">法律依据</td><td>《税收征收管理法》第三十二条（滞纳金）、第四十条（强制执行）、第八十八条（复议前置）</td></tr>';
  html += '</tbody></table>';
  html += '</div>';
  html += '</div>';
  html += '</div>';

  // ═══════════════════════════════════════
  // 第二部分：14类稽查必查资料
  // ═══════════════════════════════════════
  html += '<div id="documents" class="card" style="margin-bottom:20px;">';
  html += '<h2 style="border-left:4px solid #f59e0b;padding-left:12px;">📁 二、14类稽查必查资料清单</h2>';
  html += '<p class="muted">根据《税务稽查工作规程》，稽查通知下达后企业通常只有3-5天准备时间。以下14类资料为稽查必查项，每类资料均有明确的稽查用途、缺失后果和法律依据。</p>';

  // 资料清单卡片
  html += '<div style="display:grid;grid-template-columns:1fr;gap:12px;margin-top:16px;">';

  var docs = [
    {key:'bank', name:'银行流水', level:'高风险', purpose:'验证资金全链路，稽查第一调取对象', 
     consequence:'缺失→无法验证收入完整性+无法检测资金回流→税务机关从金税系统/第三方数据倒推核定收入→核定结果远超企业实际→补税+0.5-5倍罚款+滞纳金',
     law:'《税收征收管理法》第三十五条（核定征收）、第五十四条；《税务稽查工作规程》第二十二条'},
    {key:'sales_invoice', name:'销项发票', level:'高风险', purpose:'验证开票收入与申报收入匹配',
     consequence:'缺失→稽查直接从金税系统调取开票数据+银行流水→银行收款>开票金额→推定为隐匿未开票收入→补缴增值税+企业所得税+0.5-5倍罚款+滞纳金',
     law:'《增值税暂行条例》；《税收征收管理法》第六十三条（偷税处罚）'},
    {key:'purchase_invoice', name:'进项发票', level:'高风险', purpose:'验证成本真实性+进项税额抵扣合法性',
     consequence:'缺失→稽查逐一核验全部进项税额抵扣凭证→异常发票（走逃/失控/虚开/品名不符）做进项税额转出→补缴增值税+滞纳金；对应成本不得税前扣除→补缴企业所得税',
     law:'《增值税暂行条例》；国家税务总局公告2019年第38号；《企业所得税法》第八条'},
    {key:'voucher', name:'记账凭证', level:'高风险', purpose:'追溯账务处理全过程的原始依据',
     consequence:'缺失→无法核查分录准确性/科目运用/原始凭证匹配→会计账簿视为不健全→按《税收征收管理法》第三十五条核定征收',
     law:'《税收征收管理法》第三十五条、第五十四条、第五十六条；《税务稽查工作规程》'},
    {key:'salary', name:'工资表', level:'中风险', purpose:'验证工资费用真实性+个税代扣代缴义务履行',
     consequence:'缺失→无法核实人员真实性（虚列人头/虚增工资）→工资费用不得税前扣除+补缴企业所得税',
     law:'《企业所得税法实施条例》第三十四条；《个人所得税法》第九条'},
    {key:'social_security', name:'社保明细', level:'中风险', purpose:'核实用工合规性+缴费基数真实性',
     consequence:'缺失→无法验证社保缴费基数与工资表的一致性→金税四期人社税务数据联动后差异自动预警→稽查局收到独立推送→社保稽核+税务稽查联动',
     law:'《社会保险法》第五十八条、第八十四条'},
    {key:'inventory', name:'进销存台账', level:'中风险', purpose:'验证存货真实性+购销匹配',
     consequence:'缺失→无法核实期末存货是否账实相符→存货账实不符→认定为账外经营/虚增成本→补税+核定征收',
     law:'《企业所得税法实施条例》；《税收征收管理法》第三十五条'},
    {key:'contract', name:'合同文件', level:'高风险', purpose:'证明交易真实性，四流合一第一环',
     consequence:'缺失→无法证明交易具有商业实质→税务机关可认定为无真实交易的虚开发票→进项税额不得抵扣+移送公安',
     law:'《税收征收管理法》第五十四条；《印花税法》'},
    {key:'trial_balance', name:'科目余额表', level:'中风险', purpose:'验证总账与明细账一致性',
     consequence:'缺失→无法交叉验证账户余额准确性→账账不符→会计信息失真→依据《会计法》第四十二条处罚+核定征收',
     law:'《企业会计准则》；《会计法》第四十二条'},
    {key:'financial', name:'资产负债表+利润表', level:'中风险', purpose:'验证企业财务状况与申报数据匹配',
     consequence:'缺失→无法比对报表收入与申报收入/开票收入→三源比对失效→隐匿收入/虚列成本无法被系统发现→但稽查可现场调取原始账簿逐一核实',
     law:'《税收征收管理法》第五十四条；《企业所得税法》'},
    {key:'vat', name:'增值税申报表', level:'中风险', purpose:'验证销项/进项税额与开票/收票数据一致性',
     consequence:'缺失→无法确认企业是否足额申报增值税→未申报或少申报→补税+滞纳金+0.5-5倍罚款',
     law:'《增值税暂行条例》；《税收征收管理法》第六十三条'},
    {key:'cit', name:'企业所得税申报表', level:'中风险', purpose:'验证收入成本费用与凭证账务匹配',
     consequence:'缺失→无法核实所得税汇算清缴的准确性→少缴企业所得税→补税+滞纳金+罚款',
     law:'《企业所得税法》；《税收征收管理法》第六十三条'},
    {key:'ind_tax', name:'个人所得税申报表', level:'低风险', purpose:'验证个税申报与工资表一致性',
     consequence:'缺失→无法核实代扣代缴义务是否履行→未代扣代缴→补税+滞纳金+0.5-3倍罚款→企业负责人和财务负责人承担连带责任',
     law:'《个人所得税法》第九条、第十条；《税收征收管理法》第六十九条'},
    {key:'other_tax', name:'其他税种申报表', level:'低风险', purpose:'验证印花税/城建税/教育费附加等申报完整性',
     consequence:'缺失→无法确认小税种是否申报→漏缴各项附加税费→逐项补缴+滞纳金+罚款→小税种常成为稽查深挖突破口',
     law:'《印花税法》；《城市维护建设税法》等'}
  ];

  for (var i = 0; i < docs.length; i++) {
    var d = docs[i];
    var levelColor = d.level === '高风险' ? '#dc2626' : (d.level === '中风险' ? '#f59e0b' : '#6b7280');
    html += '<div class="card" style="padding:12px 16px;border-left:4px solid ' + levelColor + ';">';
    html += '<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">';
    html += '<span style="background:' + levelColor + ';color:#fff;padding:2px 8px;border-radius:3px;font-size:12px;">' + d.level + '</span>';
    html += '<strong style="font-size:15px;">' + d.name + '</strong>';
    html += '</div>';
    html += '<div style="font-size:13px;color:#374151;margin-bottom:4px;"><strong>稽查用途：</strong>' + d.purpose + '</div>';
    html += '<div style="font-size:13px;color:#dc2626;margin-bottom:4px;"><strong>缺失后果：</strong>' + d.consequence + '</div>';
    html += '<div style="font-size:12px;color:#6b7280;"><strong>法律依据：</strong>' + d.law + '</div>';
    html += '</div>';
  }
  html += '</div>';
  html += '</div>';

  // ═══════════════════════════════════════
  // 第三部分：稽查报告编制规范
  // ═══════════════════════════════════════
  html += '<div id="report" class="card" style="margin-bottom:20px;">';
  html += '<h2 style="border-left:4px solid #2563eb;padding-left:12px;">📝 三、稽查报告编制规范</h2>';
  html += '<p class="muted">稽查报告是稽查工作的最终成果，必须做到：事实清楚、证据确凿、定性准确、处理适当、程序合法。</p>';

  // 报告结构
  html += '<h3 style="margin-top:16px;">3.1 报告结构</h3>';
  html += '<table class="table table-sm">';
  html += '<thead><tr><th style="width:40px;">序号</th><th style="width:160px;">章节</th><th>内容要求</th></tr></thead><tbody>';
  html += '<tr><td>1</td><td>稽查基本情况</td><td>被查单位名称、纳税人识别号、稽查所属期、稽查类型（日常/专项/举报/协查）、稽查起止时间</td></tr>';
  html += '<tr><td>2</td><td>资料调取情况</td><td>调取资料的清单（14类），逐项标注已提供/未提供/部分提供。未提供的资料标注缺失后果</td></tr>';
  html += '<tr><td>3</td><td>检查方法</td><td>使用的检查方法：账簿检查、实地核查、外部调查、询问、电子数据取证等</td></tr>';
  html += '<tr><td>4</td><td>违法事实</td><td>逐项描述违法事实：时间、业务、金额、违反的具体法律条款。每项事实必须有对应的证据支撑</td></tr>';
  html += '<tr><td>5</td><td>证据材料</td><td>证据清单，每份证据标注来源、日期、证明内容。证据链必须闭环</td></tr>';
  html += '<tr><td>6</td><td>处理建议</td><td>追缴税款、加收滞纳金、处以罚款的具体金额和计算依据、引用的法律条款</td></tr>';
  html += '<tr><td>7</td><td>稽查结论</td><td>总结稽查发现、定性结论、处理意见。必须逐项说明理由</td></tr>';
  html += '</tbody></table>';

  // 叙事风格
  html += '<h3 style="margin-top:20px;">3.2 叙事风格——第一人称稽查员视角</h3>';
  html += '<div class="card" style="background:#f0fdf4;border:1px solid #bbf7d0;padding:16px;">';
  html += '<p style="margin:0 0 8px 0;"><strong>核心原则：</strong>报告以稽查员的视角撰写，使用"我审查了""我发现""我核实了"等第一人称叙事，让读者感受到稽查员的专业判断过程，而非模板化的公文堆砌。</p>';
  html += '<p style="margin:0 0 8px 0;"><strong>示例：</strong></p>';
  html += '<ul style="margin:0;font-size:13px;">';
  html += '<li>✅ <em>"我审查了被查单位提交的全部14类稽查必查资料，发现缺失8类，具体为：…"</em></li>';
  html += '<li>✅ <em>"我发现该公司2024年3-6月银行收款合计580万元，同期申报收入仅210万元，差额370万元未申报。"</em></li>';
  html += '<li>✅ <em>"我逐一比对了销项发票的开票客户与银行回款客户，发现12个回款账户名称与开票客户名称不一致。"</em></li>';
  html += '<li>❌ <em>"经查，该企业存在少申报收入的情形。"</em>（过于概括，缺乏具体数据和判断过程）</li>';
  html += '</ul>';
  html += '</div>';

  // 证据引用规范
  html += '<h3 style="margin-top:20px;">3.3 证据引用规范</h3>';
  html += '<table class="table table-sm">';
  html += '<thead><tr><th>要求</th><th>规范</th></tr></thead><tbody>';
  html += '<tr><td style="white-space:nowrap;font-weight:600;">证据必须可溯源</td><td>每项证据标注来源文件/系统/记录，注明时间、数据范围</td></tr>';
  html += '<tr><td style="font-weight:600;">证据链必须闭环</td><td>单一数据源不足以定案。至少需要两个以上独立数据源交叉验证（如发票+银行流水+合同三源比对）</td></tr>';
  html += '<tr><td style="font-weight:600;">金额必须精确</td><td>所有金额以元为单位，精确到分。计算过程附在报告后</td></tr>';
  html += '<tr><td style="font-weight:600;">数据范围明确</td><td>标注稽查所属期的起止时间，超出所属期的数据需要特别说明</td></tr>';
  html += '<tr><td style="font-weight:600;">禁止模糊表述</td><td>不得使用"大约""估计""若干"等模糊词汇。所有结论必须有具体数据支撑</td></tr>';
  html += '</tbody></table>';

  // 法律条文引用规范
  html += '<h3 style="margin-top:20px;">3.4 法律条文引用规范</h3>';
  html += '<div class="card" style="background:#fef3c7;border:1px solid #fde68a;padding:16px;">';
  html += '<ul style="margin:0;font-size:13px;">';
  html += '<li><strong>引用格式：</strong>法律名称全称 + 条款号 + 条款具体内容摘要。如：《税收征收管理法》第三十五条（核定征收）——"纳税人申报的计税依据明显偏低且无正当理由的，税务机关有权核定其应纳税额。"</li>';
  html += '<li><strong>引用层级：</strong>法律 > 行政法规 > 部门规章 > 规范性文件。优先引用上位法</li>';
  html += '<li><strong>禁止引用：</strong>不得引用已废止的法规、不得引用不适用于该情形的条款、不得断章取义</li>';
  html += '<li><strong>处罚依据必须明确：</strong>罚款倍数、滞纳金计算方式必须在引用条款中明确，不得模糊处理</li>';
  html += '</ul>';
  html += '</div>';
  html += '</div>';

  // ═══════════════════════════════════════
  // 第四部分：关键法律条文索引
  // ═══════════════════════════════════════
  html += '<div id="laws" class="card" style="margin-bottom:20px;">';
  html += '<h2 style="border-left:4px solid #8b5cf6;padding-left:12px;">⚖️ 四、关键法律条文索引</h2>';
  html += '<p class="muted">以下为税务稽查中最常引用的核心法律条款。稽查员应熟练掌握，确保定性准确、处理适当。</p>';

  // 税收征收管理法
  html += '<h3 style="margin-top:16px;">4.1 《税收征收管理法》核心条款</h3>';
  html += '<table class="table table-sm">';
  html += '<thead><tr><th style="width:100px;">条款</th><th>内容摘要</th><th style="width:160px;">适用场景</th></tr></thead><tbody>';
  html += '<tr><td>第三十二条</td><td>纳税人未按规定期限缴纳税款，从滞纳税款之日起按日加收万分之五滞纳金</td><td>追缴税款时同步计算滞纳金</td></tr>';
  html += '<tr><td>第三十五条</td><td>纳税人申报的计税依据明显偏低且无正当理由的，税务机关有权核定应纳税额</td><td>账务混乱/资料缺失→核定征收</td></tr>';
  html += '<tr><td>第四十条</td><td>从事生产经营的纳税人未按规定期限缴纳税款，税务机关可采取强制执行措施</td><td>税款追缴强制执行</td></tr>';
  html += '<tr><td>第五十四条</td><td>税务机关有权检查纳税人账簿/凭证/报表/资料，可责成提供与纳税有关的文件/证明/资料</td><td>检查权——调取资料的法定基础</td></tr>';
  html += '<tr><td>第五十六条</td><td>纳税人必须接受税务机关依法进行的税务检查，如实反映情况，提供有关资料</td><td>资料提供义务——不得拒绝</td></tr>';
  html += '<tr><td>第六十三条</td><td>偷税——伪造/变造/隐匿/擅自销毁账簿凭证，或在账簿上多列支出/不列少列收入→追缴+滞纳金+0.5-5倍罚款</td><td>隐匿收入/虚列成本的核心处罚条款</td></tr>';
  html += '<tr><td>第六十四条</td><td>不进行纳税申报→追缴+滞纳金+罚款</td><td>未申报或少申报收入</td></tr>';
  html += '<tr><td>第六十九条</td><td>扣缴义务人应扣未扣税款→追缴税款+滞纳金+0.5-3倍罚款</td><td>个税/社保未代扣代缴</td></tr>';
  html += '<tr><td>第八十八条</td><td>纳税争议：先缴纳税款或提供担保→再申请行政复议→不服复议可提起诉讼</td><td>企业救济权利——复议前置</td></tr>';
  html += '</tbody></table>';

  // 各税种核心条款
  html += '<h3 style="margin-top:20px;">4.2 各税种核心条款</h3>';
  html += '<table class="table table-sm">';
  html += '<thead><tr><th style="width:120px;">税种/法律</th><th style="width:100px;">核心条款</th><th>内容摘要</th></tr></thead><tbody>';
  html += '<tr><td>增值税暂行条例</td><td>第一条/第十九条</td><td>销售货物/提供劳务→产生纳税义务；纳税义务发生时间为收讫销售款项或取得索取凭据的当天</td></tr>';
  html += '<tr><td>增值税——进项抵扣</td><td>第八条/第九条/第十条</td><td>准予抵扣的进项税额范围；未取得合法扣税凭证的不得抵扣；用于简易计税/免税/集体福利/个人消费的不得抵扣</td></tr>';
  html += '<tr><td>企业所得税法</td><td>第八条</td><td>企业实际发生的与取得收入有关的合理支出准予扣除（真实性+相关性+合理性三要素）</td></tr>';
  html += '<tr><td>企业所得税法实施条例</td><td>第三十四条</td><td>工资薪金——企业每一纳税年度支付给在本企业任职或受雇员工的所有现金/非现金劳动报酬，准予扣除</td></tr>';
  html += '<tr><td>个人所得税法</td><td>第九条</td><td>个人所得税以所得人为纳税人，以支付所得的单位或个人为扣缴义务人</td></tr>';
  html += '<tr><td>税收征收管理法</td><td>第三十五条</td><td>账目混乱/成本资料残缺→税务机关有权核定应纳税额</td></tr>';
  html += '<tr><td>印花税法</td><td>第五条/第八条</td><td>应税合同按合同金额万分之三贴花；营业账簿按实收资本万分之二点五贴花</td></tr>';
  html += '<tr><td>社会保险法</td><td>第五十八条/第八十四条</td><td>用人单位应自用工之日起30日内为职工办理社保登记；未办理→责令改正+罚款</td></tr>';
  html += '<tr><td>会计法</td><td>第四十二条</td><td>不依法设置会计账簿/私设账簿/未按规定填制凭证→罚款+责任人处分</td></tr>';
  html += '<tr><td>国家税务总局公告2019年第38号</td><td>全文</td><td>异常增值税扣税凭证管理——走逃/失控/虚开发票的进项税额处理</td></tr>';
  html += '</tbody></table>';
  html += '</div>';

  // ═══════════════════════════════════════
  // 第五部分：稽查方法论
  // ═══════════════════════════════════════
  html += '<div id="methodology" class="card" style="margin-bottom:20px;">';
  html += '<h2 style="border-left:4px solid #10b981;padding-left:12px;">🔬 五、稽查方法论</h2>';
  html += '<p class="muted">以下方法论提炼自实战经验，全行业适用。每个方法均包含原理、验证路径和常见突破口。</p>';

  // 四流合一
  html += '<div class="card" style="border-top:3px solid #2563eb;margin-bottom:16px;">';
  html += '<h3>5.1 四流合一验证法</h3>';
  html += '<p style="font-weight:600;">原理：真实交易必须同时满足合同流、发票流、货物流、资金流四流一致。</p>';
  html += '<table class="table table-sm"><tbody>';
  html += '<tr><td style="white-space:nowrap;font-weight:600;">合同流</td><td>购销合同/服务协议→证明交易具有商业实质。无合同→交易真实性存疑→虚开发票嫌疑</td></tr>';
  html += '<tr><td style="font-weight:600;">发票流</td><td>增值税发票→品名/数量/金额与合同一致。品名不符→进项税额不得抵扣</td></tr>';
  html += '<tr><td style="font-weight:600;">货物流</td><td>入库单/出库单/运输单据→货物真实交付。无物流记录→无真实交易→虚开发票</td></tr>';
  html += '<tr><td style="font-weight:600;">资金流</td><td>银行付款记录→付款方=购货方/收款方=销货方。付款方与发票不一致→三流不合一→虚开发票嫌疑</td></tr>';
  html += '<tr><td style="font-weight:600;">验证方法</td><td>以发票为起点，逐一检查四流是否一致。任一链条断裂→该笔交易启动深度调查</td></tr>';
  html += '</tbody></table>';
  html += '</div>';

  // 三源比对
  html += '<div class="card" style="border-top:3px solid #f59e0b;margin-bottom:16px;">';
  html += '<h3>5.2 三源比对法</h3>';
  html += '<p style="font-weight:600;">原理：收入确认必须同时满足开票收入、申报收入、银行收款三源一致。</p>';
  html += '<table class="table table-sm"><tbody>';
  html += '<tr><td style="white-space:nowrap;font-weight:600;">源1：开票收入</td><td>金税系统中的销项发票金额合计——这是企业自行开具的法定记录</td></tr>';
  html += '<tr><td style="font-weight:600;">源2：申报收入</td><td>增值税/企业所得税申报表中的营业收入——这是企业向税务机关申报的数据</td></tr>';
  html += '<tr><td style="font-weight:600;">源3：银行收款</td><td>对公账户+法人/股东关联账户中与经营相关的收款——这是资金的实际流动</td></tr>';
  html += '<tr><td style="font-weight:600;">异常信号</td><td>银行收款>申报收入→隐匿未开票收入。开票收入>申报收入→未将开票额全部申报。申报收入>开票收入→存在未开票收入但已申报（需核实来源）</td></tr>';
  html += '</tbody></table>';
  html += '</div>';

  // 资金回流检测
  html += '<div class="card" style="border-top:3px solid #dc2626;margin-bottom:16px;">';
  html += '<h3>5.3 资金回流检测法</h3>';
  html += '<p style="font-weight:600;">原理：虚开发票的典型特征——企业向供应商付款后，相同或相近金额在短期内回流至法人/股东/关联方个人账户。</p>';
  html += '<table class="table table-sm"><tbody>';
  html += '<tr><td style="white-space:nowrap;font-weight:600;">检测方法</td><td>①提取所有大额对公付款（>5万元）；②追踪每笔付款后30天内法人/股东个人账户的收款；③匹配金额（±5%容差）和时差</td></tr>';
  html += '<tr><td style="font-weight:600;">异常信号</td><td>付款给供应商A→30天内法人/股东收到±5%金额→资金回流特征→虚开发票高度嫌疑→移送公安</td></tr>';
  html += '<tr><td style="font-weight:600;">法律后果</td><td>虚开增值税专用发票→进项税额不得抵扣+补缴税款+罚款→情节严重（税额>5万元）→移送公安机关追究刑事责任</td></tr>';
  html += '</tbody></table>';
  html += '</div>';

  // 多源交叉验证
  html += '<div class="card" style="border-top:3px solid #10b981;margin-bottom:16px;">';
  html += '<h3>5.4 多源交叉验证法</h3>';
  html += '<p style="font-weight:600;">原理：单源数据不可信，必须3源以上交叉验证才能定案。</p>';
  html += '<table class="table table-sm"><tbody>';
  html += '<tr><td style="white-space:nowrap;font-weight:600;">收入验证</td><td>销项发票 + 银行收款 + 申报收入 + 合同金额 → 4源比对</td></tr>';
  html += '<tr><td style="font-weight:600;">成本验证</td><td>进项发票 + 银行付款 + 入库单 + 存货账 + 合同 → 5源比对</td></tr>';
  html += '<tr><td style="font-weight:600;">工资验证</td><td>工资表 + 银行代发 + 个税申报 + 社保参保 → 4源比对</td></tr>';
  html += '<tr><td style="font-weight:600;">往来验证</td><td>应收账款 + 银行收款 + 客户对账 + 合同结算条款 → 4源比对</td></tr>';
  html += '<tr><td style="font-weight:600;">定案标准</td><td>至少2个独立数据源交叉验证一致，才能作为证据使用。单一数据源只能是"线索"，不能是"证据"</td></tr>';
  html += '</tbody></table>';
  html += '</div>';

  // 资料缺失→风险推理
  html += '<div class="card" style="border-top:3px solid #8b5cf6;margin-bottom:16px;">';
  html += '<h3>5.5 资料缺失→风险推理法</h3>';
  html += '<p style="font-weight:600;">原理：资料的缺失本身就是信号。每缺一类资料，对应一条可推理的稽查风险链。</p>';
  html += '<div style="font-size:13px;">';
  html += '<p><strong>适用场景：</strong>企业提交的资料不完整时，稽查员不应仅标注"缺"，而应推理出缺失带来的后果——这是稽查报告中最有价值的内容。每类缺失资料的后果已在第二部分详述。</p>';
  html += '<p><strong>推理链路模板：</strong>缺失XX资料 → 无法验证YY → 税务机关将采用ZZ方式替代 → 替代结果远超企业实际 → 法律后果。</p>';
  html += '<p><strong>示例：</strong>缺失记账凭证 → 无法追溯分录准确性/科目运用/原始凭证匹配 → 税务机关认定会计账簿不健全 → 依据《税收征收管理法》第三十五条核定征收 → 核定结果通常远超企业实际税负。</p>';
  html += '</div>';
  html += '</div>';

  // 经营实质分析法
  html += '<div class="card" style="border-top:3px solid #06b6d4;margin-bottom:16px;">';
  html += '<h3>5.6 经营实质分析法</h3>';
  html += '<p style="font-weight:600;">原理：从交易特征反向验证商业合理性。发票数据本身的模式就能暴露问题。</p>';
  html += '<table class="table table-sm"><tbody>';
  html += '<tr><td style="white-space:nowrap;font-weight:600;">供应商地理</td><td>企业注册地在A省，主要供应商集中在千里之外的B省→运输成本合理性存疑→可能为开票公司</td></tr>';
  html += '<tr><td style="font-weight:600;">品名逻辑</td><td>纺织企业采购大量电子产品→品名与经营范围不符→虚开发票嫌疑</td></tr>';
  html += '<tr><td style="font-weight:600;">金额规律</td><td>长期向某供应商采购，金额稳定在起征点以下→规避发票认证→拆分交易</td></tr>';
  html += '<tr><td style="font-weight:600;">时间规律</td><td>月末/季末集中开票→突击开票冲成本→收入成本配比异常</td></tr>';
  html += '<tr><td style="font-weight:600;">价格合理性</td><td>采购价格显著高于/低于市场均价→关联交易转移定价→特别纳税调整</td></tr>';
  html += '</tbody></table>';
  html += '</div>';
  html += '</div>';

  // 底部声明
  html += '<div class="card" style="background:#f0fdf4;border:1px solid #bbf7d0;padding:16px;text-align:center;">';
  html += '<p style="margin:0;font-size:13px;color:#374151;">';
  html += '⚠️ <strong>声明：</strong>本手册内容基于《税务稽查工作规程》《税收征收管理法》及实战经验提炼，全行业适用。';
  html += '手册中的缺失后果因果链和法律后果描述均来自法律条文和稽查实践，供参考使用。具体案件的处理应结合实际情况。';
  html += '</p>';
  html += '</div>';

  container.innerHTML = html;
}

// 辅助函数：滚动到指定区域
function scrollToSection(id) {
  var el = document.getElementById(id);
  if (el) {
    el.scrollIntoView({behavior: 'smooth', block: 'start'});
  }
}
