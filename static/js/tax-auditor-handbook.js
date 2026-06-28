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
  // ═══ 两栏布局：左目录 + 右内容 ═══
  html += '<div class="handbook-layout">';

  // ── 左侧固定目录 ──
  html += '<nav class="handbook-toc" id="handbook-toc">';
  html += '<div class="toc-title">📖 目录</div>';
  html += '<a class="toc-item active" data-target="workflow">📋 稽查工作流程</a>';
  html += '<a class="toc-item" data-target="documents">📁 14类必查资料</a>';
  html += '<a class="toc-item" data-target="report">📝 报告编制规范</a>';
  html += '<a class="toc-item" data-target="laws">⚖️ 关键法律条文</a>';
  html += '<a class="toc-item" data-target="methodology">🔬 稽查方法论</a>';
  html += '<a class="toc-item" data-target="judgment-rules">🔍 稽查判定规则</a>';
  html += '<a class="toc-item" data-target="system-mapping">🔗 系统与规程映射</a>';
  html += '</nav>';

  // ── 右侧内容区 ──
  html += '<main class="handbook-content">';

  // 页头
  html += '<section class="hb-hero">';
  html += '<h1>⚖️ 税务稽查员手册</h1>';
  html += '<p>系统总结税务稽查工作要求、报告编制规范、法律依据与稽查方法论。以下内容提炼自《税务稽查工作规程》《税收征收管理法》及实战经验，全行业适用。</p>';
  html += '<div id="handbook-pipeline-status"><div class="hb-status-bar hb-status-loading">🔗 正在连接一键分析管道…</div></div>';
  html += '</section>';

  // ═══ 第一部分：稽查工作流程 ═══
  html += '<section id="workflow" class="hb-section">';
  html += '<h2 class="hb-section-title"><span class="hb-section-num">一</span> 稽查工作流程</h2>';
  html += '<p class="hb-section-lead">税务稽查分为四个阶段：选案→检查→审理→执行。每个阶段有明确的法定时限和工作要求。</p>';

  // ── 流程时间线 ──
  html += '<div class="hb-timeline">';
  
  // ① 选案
  html += '<div class="hb-tl-item">';
  html += '<div class="hb-tl-dot" style="background:#2563eb;"></div>';
  html += '<div class="hb-tl-card">';
  html += '<h3>① 选案环节 <span class="hb-law-tag">《规程》第14-20条</span></h3>';
  html += '<table class="hb-table"><tbody>';
  html += '<tr><td class="hb-td-label">案源获取</td><td>稽查局通过多种渠道获取案源信息，<strong>集体研究</strong>，合理准确地选择和确定稽查对象。</td></tr>';
  html += '<tr><td class="hb-td-label">稽查计划</td><td>年度终了前制定下一年度稽查工作计划，<strong>严格控制检查次数</strong>。</td></tr>';
  html += '<tr><td class="hb-td-label">8类案源</td><td>财务指标/上级交办/专项检查/部门移交/<strong style="color:#dc2626;">检举信息</strong>/其他部门转来/社会公共信息/其他。<br><em class="hb-note">⚠ 检举是企业的最大不可控风险——任何人可实名或匿名检举。</em></td></tr>';
  html += '<tr><td class="hb-td-label">筛选方法</td><td><strong>计算机分析、人工分析、人机结合分析</strong>筛选案源——有嫌疑的确定为待查对象。<br><em class="hb-note">💡 本系统自动化风险扫描+一键分析本质上就是"计算机分析"端——在稽查立案前模拟案源筛选逻辑。</em></td></tr>';
  html += '<tr><td class="hb-td-label">立案检查</td><td>批准立案后制作《税务稽查任务通知书》，连同资料移交检查部门。</td></tr>';
  html += '</tbody></table>';
  html += '</div></div>';

  // ② 检查
  html += '<div class="hb-tl-item">';
  html += '<div class="hb-tl-dot" style="background:#f59e0b;"></div>';
  html += '<div class="hb-tl-card">';
  html += '<h3>② 检查环节 <span class="hb-law-tag">《规程》第21-45条</span></h3>';
  html += '<table class="hb-table"><tbody>';
  html += '<tr><td class="hb-td-label">检查前准备</td><td>查阅纳税档案，了解生产经营、行业特点、财务会计制度，确定检查方法。<br><em class="hb-note">💡 线索链引擎自动完成上述工作——从数据中提取行业特征、识别异常模式。</em></td></tr>';
  html += '<tr><td class="hb-td-label">检查时限</td><td>自实施之日起<strong>60日内</strong>完成，需<strong>两名以上</strong>检查人员共同实施。</td></tr>';
  html += '<tr><td class="hb-td-label">检查方法</td><td>实地检查 / 调取账簿资料 / 询问 / 查询存款账户 / 异地协查。<br><em class="hb-note">💡 文件解析模块(域0)提取电子数据→域分析逐一检查→线索链生成发现。</em></td></tr>';
  html += '<tr><td class="hb-td-label">证据收集</td><td>证据须<strong>真实、相关联</strong>。类型：书证/物证/视听资料/电子数据/证人证言/当事人陈述/勘验笔录。<br><em class="hb-note">💡 证据链引擎——每项发现自动收集关联规则ID+数据域→触发率≥60%+≥3规则+≥2域→证据闭环。</em></td></tr>';
  html += '<tr><td class="hb-td-label">调取资料</td><td>以前年度资料<strong>3个月</strong>内退还，当年资料<strong>30日</strong>内退还。</td></tr>';
  html += '<tr><td class="hb-td-label">稽查底稿</td><td>必须制作《税务稽查工作底稿》，记录案件事实，归集证据材料——没有底稿就没有稽查报告。</td></tr>';
  html += '<tr><td class="hb-td-label">稽查报告</td><td>须含<strong>10项内容</strong>：案件来源→基本情况→检查时间→方法措施→违法事实→拒绝阻挠情形→被查对象意见→处理建议→其他事项→签名日期。</td></tr>';
  html += '<tr><td class="hb-td-label">移交审理</td><td>检查完毕，<strong>5个工作日内</strong>移交审理部门。</td></tr>';
  html += '</tbody></table>';
  html += '</div></div>';

  // ③ 审理
  html += '<div class="hb-tl-item">';
  html += '<div class="hb-tl-dot" style="background:#10b981;"></div>';
  html += '<div class="hb-tl-card">';
  html += '<h3>③ 审理环节 <span class="hb-law-tag">《规程》第46-60条</span></h3>';
  html += '<table class="hb-table"><tbody>';
  html += '<tr><td class="hb-td-label">审核重点</td><td>逐项审核<strong>7项</strong>：对象准确性/事实清楚证据充分/法律适用/程序合法/权限适当/处理建议/其他事项。<br><em class="hb-note">💡 分析链引擎逐条验证"how_found→tax_impact→policy_ref"三要素。</em></td></tr>';
  html += '<tr><td class="hb-td-label">退回补正</td><td>事实不清、证据不足→退回检查部门补充调查。<br><em class="hb-note">💡 方法论过滤器自动剔除"证据不足"的噪声发现——预审理。</em></td></tr>';
  html += '<tr><td class="hb-td-label">纠正建议</td><td>事实清楚但适用法律错误→审理部门另行提出处理意见（直接纠正，不退回）。</td></tr>';
  html += '<tr><td class="hb-td-label">审理时限</td><td>收到稽查报告后<strong>15日内</strong>提出审理意见。</td></tr>';
  html += '<tr><td class="hb-td-label">告知听证</td><td>拟处罚→送达告知书→告知陈述权/申辩权/听证权。审理人员须认真对待陈述申辩意见。</td></tr>';
  html += '<tr><td class="hb-td-label">四种决定</td><td>有违法行为→《税务处理决定书》/ 应处罚→《税务行政处罚决定书》/ 轻微→《不予处罚决定书》/ 无违法→《税务稽查结论》。文书须注明<strong>文件全称、文号、条款</strong>。</td></tr>';
  html += '<tr><td class="hb-td-label">涉罪移送</td><td>涉嫌犯罪→《涉嫌犯罪案件移送书》→经局长批准→移送公安机关。</td></tr>';
  html += '</tbody></table>';
  html += '</div></div>';

  // ④ 执行
  html += '<div class="hb-tl-item">';
  html += '<div class="hb-tl-dot" style="background:#8b5cf6;"></div>';
  html += '<div class="hb-tl-card">';
  html += '<h3>④ 执行环节</h3>';
  html += '<table class="hb-table"><tbody>';
  html += '<tr><td class="hb-td-label">执行文书</td><td>下达《税务处理决定书》+《税务行政处罚决定书》→责令限期缴纳税款、滞纳金、罚款</td></tr>';
  html += '<tr><td class="hb-td-label">企业权利</td><td>60日内申请行政复议 / 复议后15日内提起诉讼 / 缴纳税款或提供担保后可申请复议</td></tr>';
  html += '<tr><td class="hb-td-label">强制执行</td><td>逾期不履行→加收每日万分之五滞纳金→税收保全（冻结存款/查封财产）→申请法院强制执行</td></tr>';
  html += '<tr><td class="hb-td-label">法律依据</td><td>《税收征收管理法》第三十二条（滞纳金）、第四十条（强制执行）、第八十八条（复议前置）</td></tr>';
  html += '</tbody></table>';
  html += '</div></div>';

  // ⑤ 案卷管理
  html += '<div class="hb-tl-item">';
  html += '<div class="hb-tl-dot" style="background:#ec4899;"></div>';
  html += '<div class="hb-tl-card">';
  html += '<h3>⑤ 案卷管理 <span class="hb-law-tag">《规程》第72-77条</span></h3>';
  html += '<table class="hb-table"><tbody>';
  html += '<tr><td class="hb-td-label">立卷归档</td><td>处理决定执行完毕后<strong>60日内</strong>收集各环节全部资料，整理成稽查案卷，归档保管。</td></tr>';
  html += '<tr><td class="hb-td-label">正卷副卷</td><td>正卷列入可公开材料（证据、文书）；副卷列入检举材料、讨论记录、法定秘密——<strong>副卷为密卷管理</strong>。<br><em class="hb-note" style="color:#dc2626;">⚠ 正卷可被查阅（第76条）——违法事实和证据可被后续检查、复议、诉讼反复调取。</em></td></tr>';
  html += '<tr><td class="hb-td-label" style="color:#dc2626;">保管期限</td><td><strong>偷税/骗税/抗税/涉罪案件：永久保存。</strong>一般行政处罚：30年。其他：10年。</td></tr>';
  html += '<tr><td class="hb-td-label">查阅借阅</td><td>税务机关人员查阅需经局长批准；外部人员查阅需经税务局领导批准。</td></tr>';
  html += '</tbody></table>';
  html += '</div></div>';

  html += '</div>'; // hb-timeline

  // ── 制度基础卡片 ──
  html += '<div class="hb-card-grid" style="margin-top:24px;">';
  html += '<div class="hb-info-card hb-info-purple"><strong>四分离原则（第5条）</strong><p>选案、检查、审理、执行分工制约——选案的人不检查，检查的人不审理，审理的人不执行。</p></div>';
  html += '<div class="hb-info-card hb-info-red"><strong>8项工作纪律（第7-8条）</strong><p>回避/不得违反程序/不得谋取利益/不得玩忽职守/<strong>不得泄密通风报信</strong>/不得弄虚作假/不得请客送礼/不得私自会见被查对象。</p></div>';
  html += '<div class="hb-info-card hb-info-blue"><strong>信息化要求（第9条）</strong><p>税务机关必须<strong>不断提高稽查信息化应用水平</strong>。本系统的自动化管道正是第9条的实践落地。</p></div>';
  html += '<div class="hb-info-card hb-info-green"><strong>基本任务（第2条）</strong><p>依法查处税收违法行为，以<strong>事实为根据，以法律为准绳</strong>，坚持公平、公开、公正、效率原则。</p></div>';
  html += '</div>';

  html += '</section>';

  // ═══ 第二部分：14类必查资料 ═══
  html += '<section id="documents" class="hb-section">';
  html += '<h2 class="hb-section-title"><span class="hb-section-num">二</span> 14类稽查必查资料清单</h2>';
  html += '<p class="hb-section-lead">根据《税务稽查工作规程》，稽查通知下达后企业通常只有3-5天准备时间。以下14类资料为稽查必查项。</p>';
  html += '<div class="hb-card-grid" style="grid-template-columns:repeat(auto-fill,minmax(420px,1fr));">';

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
    var isHigh = d.level === '高风险';
    var cardClass = isHigh ? 'hb-doc-card hb-doc-high' : 'hb-doc-card';
    html += '<div class="' + cardClass + '">';
    html += '<div class="hb-doc-header">';
    html += '<span class="hb-doc-badge ' + (isHigh ? 'hb-badge-red' : (d.level === '中风险' ? 'hb-badge-yellow' : 'hb-badge-gray')) + '">' + d.level + '</span>';
    html += '<strong>' + d.name + '</strong>';
    html += '</div>';
    html += '<div class="hb-doc-purpose">📌 ' + d.purpose + '</div>';
    html += '<div class="hb-doc-consequence">⚠ 缺失后果：' + d.consequence + '</div>';
    html += '<div class="hb-doc-law">📜 ' + d.law + '</div>';
    html += '</div>';
  }
  html += '</div></section>';

  // ═══ 第三部分：稽查报告编制规范 ═══
  html += '<section id="report" class="hb-section">';
  html += '<h2 class="hb-section-title"><span class="hb-section-num">三</span> 报告编制规范</h2>';
  html += '<p class="hb-section-lead">稽查报告是稽查工作的最终成果，必须做到：事实清楚、证据确凿、定性准确、处理适当、程序合法。</p>';

  // 3.1 报告结构（摘要，详见报告编制要求模块）
  html += '<h3 class="hb-subtitle">3.1 标准分析报告结构（7章·正式法律文书）</h3>';
  html += '<table class="hb-table hb-table-striped">';
  html += '<thead><tr><th style="width:40px;">章</th><th>内容</th><th style="width:280px;">汇报视角</th></tr></thead><tbody>';
  html += '<tr><td class="hb-td-num">一</td><td>案件来源及稽查对象基本情况</td><td>案件来源→联网核查→工商登记全貌→稽查期间与范围</td></tr>';
  html += '<tr><td class="hb-td-num">二</td><td>稽查实施情况</td><td>数据比对→资金核对→穿透分析→行业对标→综合分析</td></tr>';
  html += '<tr><td class="hb-td-num">三</td><td>稽查发现问题及事实认定</td><td>每条发现按六要素格式：违法性质→违法事实→证据材料→证据来源→法律依据→处理建议</td></tr>';
  html += '<tr><td class="hb-td-num">四</td><td>稽查结论</td><td>综合风险评级→主要高风险事项→证据链完整性→总体结论</td></tr>';
  html += '<tr><td class="hb-td-num">五</td><td>处理处罚建议</td><td>去重后的处理建议列表→自查整改期限</td></tr>';
  html += '<tr><td class="hb-td-num">六</td><td>告知权利义务</td><td>5项法定权利（回避/陈述申辩/听证/复议/诉讼）→注明法定期限</td></tr>';
  html += '<tr><td class="hb-td-num">七</td><td>稽查人员签字</td><td>稽查执行人+审理人+稽查部门（盖章）+报告日期</td></tr>';
  html += '</tbody></table>';
  html += '<div class="hb-callout hb-callout-info">📜 本报告结构覆盖《规程》第42条和第54条的全部要求。<br>📐 详细的12项质量标准、六要素格式示例、判定可靠性要求，请参见 <strong>「📐 报告编制要求」模块</strong>。</div>';

  // 3.2 叙事风格
  html += '<h3 class="hb-subtitle">3.2 叙事风格——客观第三人称正式法律语体</h3>';
  html += '<div class="hb-callout hb-callout-green">';
  html += '<p><strong>核心原则：</strong>采用客观第三人称正式法律文书格式，使用"经查""该企业""被查单位"等客观表述。</p>';
  html += '<ul style="margin:8px 0 0 16px;font-size:13px;">';
  html += '<li>✅ "经依法受理并按照《税务稽查工作规程》组织实施稽查，以下为被查单位基本情况。"</li>';
  html += '<li>✅ "经审核发现实质经营模式与工商登记存在差异，详见稽查实施情况。"</li>';
  html += '<li>❌ "我审查了XX资料""领导，我得出以下结论"（禁止第一人称/口头汇报体）</li>';
  html += '</ul>';
  html += '</div>';

  // 3.3 证据引用规范
  html += '<h3 class="hb-subtitle">3.3 证据引用规范</h3>';
  html += '<div class="hb-card-grid" style="grid-template-columns:repeat(auto-fill,minmax(220px,1fr));">';
  html += '<div class="hb-info-card hb-info-blue"><strong>证据可溯源</strong><p>标注来源文件/系统/记录，注明时间、数据范围</p></div>';
  html += '<div class="hb-info-card hb-info-purple"><strong>证据链闭环</strong><p>≥2个独立数据源交叉验证才能定案</p></div>';
  html += '<div class="hb-info-card hb-info-green"><strong>金额精确</strong><p>以元为单位，精确到分，计算过程附后</p></div>';
  html += '<div class="hb-info-card hb-info-yellow"><strong>禁止模糊</strong><p>不得使用"大约""估计""若干"等词汇</p></div>';
  html += '</div>';

  // 3.4 法律条文引用
  html += '<h3 class="hb-subtitle">3.4 法律条文引用规范</h3>';
  html += '<div class="hb-callout hb-callout-yellow">';
  html += '<ul style="margin:0;font-size:13px;padding-left:16px;">';
  html += '<li><strong>格式：</strong>法律全称+条款号+内容摘要。如：《税收征收管理法》第三十五条（核定征收）</li>';
  html += '<li><strong>层级：</strong>法律 > 行政法规 > 部门规章 > 规范性文件，优先引用上位法</li>';
  html += '<li><strong>禁止：</strong>不得引用已废止法规、不得断章取义、处罚依据必须明确（罚款倍数/滞纳金计算方式）</li>';
  html += '</ul>';
  html += '</div>';

  // 3.5 十二项质量标准
  html += '<h3 class="hb-subtitle">3.5 稽查报告质量标准——十二项硬指标</h3>';
  html += '<div class="hb-quality-grid">';
  var standards = [
    {n:'1',name:'客观第三人称叙事',rule:'how_found和description必须使用"经查""该企业"等客观第三人称表述',bad:'❌ "我审查了被查单位提交的银行流水"'},
    {n:'2',name:'事实-证据-后果三要素',rule:'每条发现必须同时包含：具体事实+证据来源+缺失后果',bad:'❌ "销项发票购方名称与银行收款付款方名称不匹配"（无数据）'},
    {n:'3',name:'完整因果链(A→B→C→D)',rule:'后果必须写成至少三步推导：缺失X→无法验证Y→税务机关采取Z→法律后果',bad:'❌ "缺失凭证→补税+罚款"'},
    {n:'4',name:'可操作的紧迫感',rule:'suggestion必须具体到"做什么、怎么做、分几步"',bad:'❌ "请提供相关合同、单据、凭证等佐证材料"'},
    {n:'5',name:'特定法律条款引用',rule:'policy_ref必须含条款号+名称+摘要。禁止"依据相关法律规定"',bad:'❌ "依据相关税收法规"'},
    {n:'6',name:'证据明细表(items)',rule:'涉及多项明细的发现必须附items数组，前端渲染可折叠明细表',bad:'❌ 一句话带过'},
    {n:'7',name:'方法在前/过程在后',rule:'先声明稽查方法(并列清单)，再展示核查过程与结果',bad:'❌ "需要按六种商业模式逐笔分析"'},
    {n:'8',name:'反模板句',rule:'禁止"是税务稽查重点方向""需逐笔核实""请提供相关佐证材料"等通用模板句',bad:'❌ "收款来源与开票客户严重不匹配是税务稽查重点方向"'},
    {n:'9',name:'事实具体化',rule:'事实描述必须含具体数值——日期/金额/数量/百分比等',bad:'❌ "经营场所银行付款未入账"（零事实）'},
    {n:'10',name:'防跨发现复制',rule:'不同发现的tax_impact不能完全相同，必须独立撰写',bad:'❌ Findings 7/8/9的tax_impact完全相同'},
    {n:'11',name:'空占位符检测',rule:'suggestion不能含()/()()等空占位符',bad:'❌ "已识别10条关联记录（如：()；()；()）"'},
    {n:'12',name:'法律条款号',rule:'policy_ref必须含"第X条"或"第X款"',bad:'❌ "《企业所得税法实施条例》"（无条款号）'}
  ];
  for (var s = 0; s < standards.length; s++) {
    var st = standards[s];
    html += '<div class="hb-q-item"><span class="hb-q-num">' + st.n + '</span><div><strong>' + st.name + '</strong><p>' + st.rule + '</p><p class="hb-q-bad">' + st.bad + '</p></div></div>';
  }
  html += '</div>';
  html += '<div class="hb-callout hb-callout-green" style="margin-top:16px;">🔧 系统在生成最终报告前自动执行两轮质量保障——模板句剔除+12项标准逐条检查。</div>';

  // 3.6 四要素
  html += '<h3 class="hb-subtitle">3.6 报告四要素</h3>';
  html += '<div class="hb-card-grid" style="grid-template-columns:repeat(auto-fill,minmax(220px,1fr));">';
  html += '<div class="hb-info-card hb-info-red"><strong>① 处理优先级</strong><p>高风险立即处理/中风险限期整改/低风险持续关注</p></div>';
  html += '<div class="hb-info-card hb-info-blue"><strong>② 交叉引用</strong><p>每项发现标注共享同一域/线索链的关联发现</p></div>';
  html += '<div class="hb-info-card hb-info-purple"><strong>③ 对比基准</strong><p>偏差多少？跟什么比？必须有行业基准值+企业值+偏离%</p></div>';
  html += '<div class="hb-info-card hb-info-green"><strong>④ 证据闭环</strong><p>提取原始数据→逐票核对→多域交叉→形成闭环</p></div>';
  html += '</div>';
  html += '</section>';

  // ═══ 第四部分：关键法律条文索引 ═══
  html += '<section id="laws" class="hb-section">';
  html += '<h2 class="hb-section-title"><span class="hb-section-num">四</span> 关键法律条文索引</h2>';
  html += '<p class="hb-section-lead">以下为税务稽查中最常引用的核心法律条款，稽查员应熟练掌握。</p>';

  html += '<h3 class="hb-subtitle">4.1 《税收征收管理法》核心条款</h3>';
  html += '<table class="hb-table hb-table-striped">';
  html += '<thead><tr><th style="width:100px;">条款</th><th>内容摘要</th><th style="width:150px;">适用场景</th></tr></thead><tbody>';
  html += '<tr><td class="hb-td-num">第32条</td><td>未按规定期限缴纳税款，按日加收万分之五滞纳金</td><td>追缴税款时同步计算滞纳金</td></tr>';
  html += '<tr><td class="hb-td-num">第35条</td><td>计税依据明显偏低且无正当理由→税务机关有权核定应纳税额</td><td>账务混乱/资料缺失→核定征收</td></tr>';
  html += '<tr><td class="hb-td-num">第40条</td><td>未按规定期限缴纳税款→可采取强制执行措施</td><td>税款追缴强制执行</td></tr>';
  html += '<tr><td class="hb-td-num">第54条</td><td>有权检查账簿/凭证/报表/资料，可责成提供相关文件</td><td>检查权——调取资料的法定基础</td></tr>';
  html += '<tr><td class="hb-td-num">第56条</td><td>必须接受检查，如实反映情况，提供有关资料</td><td>资料提供义务——不得拒绝</td></tr>';
  html += '<tr><td class="hb-td-num" style="color:#dc2626;">第63条</td><td>偷税——伪造/变造/隐匿账簿，多列支出/少列收入→追缴+滞纳金+<strong>0.5-5倍罚款</strong></td><td>隐匿收入/虚列成本核心处罚条款</td></tr>';
  html += '<tr><td class="hb-td-num">第64条</td><td>不进行纳税申报→追缴+滞纳金+罚款</td><td>未申报或少申报收入</td></tr>';
  html += '<tr><td class="hb-td-num">第69条</td><td>扣缴义务人应扣未扣→追缴+滞纳金+0.5-3倍罚款</td><td>个税/社保未代扣代缴</td></tr>';
  html += '<tr><td class="hb-td-num">第88条</td><td>纳税争议：先缴税或担保→行政复议→不服可诉讼</td><td>企业救济权利——复议前置</td></tr>';
  html += '</tbody></table>';

  html += '<h3 class="hb-subtitle">4.2 各税种核心条款</h3>';
  html += '<div class="hb-card-grid" style="grid-template-columns:repeat(auto-fill,minmax(300px,1fr));">';
  var laws = [
    {tax:'增值税暂行条例',art:'第1/19条',desc:'销售货物/提供劳务→产生纳税义务；收讫款项或取得索取凭据当天'},
    {tax:'增值税——进项抵扣',art:'第8-10条',desc:'准予抵扣范围；未取得合法凭证不得抵扣；简易计税/免税/集体福利/个人消费不得抵扣'},
    {tax:'企业所得税法',art:'第8条',desc:'实际发生且与收入有关的合理支出准予扣除（真实性+相关性+合理性）'},
    {tax:'企业所得税法实施条例',art:'第34条',desc:'工资薪金——支付给任职员工的现金/非现金劳动报酬准予扣除'},
    {tax:'个人所得税法',art:'第9条',desc:'以支付所得的单位或个人为扣缴义务人'},
    {tax:'印花税法',art:'第5/8条',desc:'应税合同按万分之三贴花；营业账簿按万分之二点五贴花'},
    {tax:'社会保险法',art:'第58/84条',desc:'用工30日内办理社保登记；未办理→责令改正+罚款'},
    {tax:'会计法',art:'第42条',desc:'不依法设置账簿/私设账簿/未按规定填制凭证→罚款+责任人处分'},
    {tax:'国税总局2019年38号公告',art:'全文',desc:'异常增值税扣税凭证管理——走逃/失控/虚开发票的进项税额处理'}
  ];
  for (var l = 0; l < laws.length; l++) {
    var law = laws[l];
    html += '<div class="hb-law-card"><strong>' + law.tax + '</strong><span class="hb-law-tag">' + law.art + '</span><p>' + law.desc + '</p></div>';
  }
  html += '</div>';

  // 4.3 文书规范
  html += '<h3 class="hb-subtitle">4.3 稽查处理决定文书规范</h3>';
  html += '<table class="hb-table hb-table-striped">';
  html += '<thead><tr><th style="width:180px;">文书类型</th><th>条款</th><th>核心内容</th></tr></thead><tbody>';
  html += '<tr><td>《税务处理决定书》</td><td>第55-56条</td><td>被查对象信息+违法事实+<strong>税款金额+缴纳期限+滞纳金计算</strong>+救济途径</td></tr>';
  html += '<tr><td>《税务行政处罚决定书》</td><td>第55/57条</td><td>违法事实+<strong>处罚种类和依据+履行方式和期限</strong>+救济途径</td></tr>';
  html += '<tr><td>《不予处罚决定书》</td><td>第55/58条</td><td>违法事实+<strong>不予处罚的理由及依据</strong>+救济途径</td></tr>';
  html += '<tr><td>《税务稽查结论》</td><td>第55/59条</td><td>被查对象信息+检查范围和内容+<strong>检查结论</strong></td></tr>';
  html += '</tbody></table>';
  html += '</section>';

  // ═══ 第五部分：稽查方法论 ═══
  html += '<section id="methodology" class="hb-section">';
  html += '<h2 class="hb-section-title"><span class="hb-section-num">五</span> 稽查方法论</h2>';
  html += '<p class="hb-section-lead">以下方法论提炼自实战经验，全行业适用。每个方法均包含原理、验证路径和常见突破口。</p>';

  html += '<div class="hb-method-grid">';

  // 5.1 四流合一
  html += '<div class="hb-method-card">';
  html += '<div class="hb-method-icon hb-m-icon-blue">🔗</div>';
  html += '<h3>5.1 四流合一验证法</h3>';
  html += '<p class="hb-method-principle">真实交易必须同时满足合同流、发票流、货物流、资金流四流一致。</p>';
  html += '<div class="hb-method-items">';
  html += '<div class="hb-mi"><span class="hb-mi-label">合同流</span>购销合同/服务协议→证明交易具有商业实质</div>';
  html += '<div class="hb-mi"><span class="hb-mi-label">发票流</span>增值税发票→品名/数量/金额与合同一致</div>';
  html += '<div class="hb-mi"><span class="hb-mi-label">货物流</span>入库单/出库单/运输单据→货物真实交付</div>';
  html += '<div class="hb-mi"><span class="hb-mi-label">资金流</span>银行付款记录→付款方=购货方/收款方=销货方</div>';
  html += '</div>';
  html += '</div>';

  // 5.2 进项三层分类
  html += '<div class="hb-method-card">';
  html += '<div class="hb-method-icon hb-m-icon-red">📊</div>';
  html += '<h3>5.2 进项发票三层分类法</h3>';
  html += '<p class="hb-method-principle">不同类别进项发票有不同付款模式——不能一刀切用"供应商名称必须匹配银行付款方"的标准。</p>';
  html += '<div class="hb-method-items">';
  html += '<div class="hb-mi"><span class="hb-mi-label red">第一层</span>主营业务成本（原料/材料/加工费）——<strong>必须</strong>匹配供应商付款</div>';
  html += '<div class="hb-mi"><span class="hb-mi-label yellow">第二层</span>重大费用（房租/咨询/运输）——<strong>应当</strong>匹配，未匹配需合同佐证</div>';
  html += '<div class="hb-mi"><span class="hb-mi-label gray">第三层</span>日常报销（餐饮/住宿/加油/差旅）——<strong>不参与</strong>供应商名称匹配</div>';
  html += '</div>';
  html += '</div>';

  // 5.3 三源比对
  html += '<div class="hb-method-card">';
  html += '<div class="hb-method-icon hb-m-icon-yellow">⚡</div>';
  html += '<h3>5.3 三源比对法</h3>';
  html += '<p class="hb-method-principle">收入确认必须开票收入、申报收入、银行收款三源一致。</p>';
  html += '<div class="hb-method-items">';
  html += '<div class="hb-mi"><span class="hb-mi-label">源1</span>开票收入——金税系统销项发票金额合计</div>';
  html += '<div class="hb-mi"><span class="hb-mi-label">源2</span>申报收入——增值税/企业所得税申报表营业收入</div>';
  html += '<div class="hb-mi"><span class="hb-mi-label">源3</span>银行收款——对公+关联账户的经营相关收款</div>';
  html += '</div>';
  html += '</div>';

  // 5.3b 资金回流
  html += '<div class="hb-method-card">';
  html += '<div class="hb-method-icon hb-m-icon-red">🔄</div>';
  html += '<h3>5.3b 资金回流检测法</h3>';
  html += '<p class="hb-method-principle">企业向供应商付款后，相同/相近金额短期内回流至法人/股东账户→虚开特征。</p>';
  html += '<div class="hb-method-items">';
  html += '<div class="hb-mi"><span class="hb-mi-label red">检测</span>大额付款(>5万)→30天内法人/股东收款→金额±5%容差匹配</div>';
  html += '<div class="hb-mi"><span class="hb-mi-label red">后果</span>虚开专用发票→进项不得抵扣+补税+罚款→情节严重移送公安</div>';
  html += '</div>';
  html += '</div>';

  // 5.4 多源交叉
  html += '<div class="hb-method-card">';
  html += '<div class="hb-method-icon hb-m-icon-green">🔍</div>';
  html += '<h3>5.4 多源交叉验证法</h3>';
  html += '<p class="hb-method-principle">单源数据不可信，必须3源以上交叉验证才能定案。</p>';
  html += '<div class="hb-method-items">';
  html += '<div class="hb-mi"><span class="hb-mi-label">收入</span>销项发票+银行收款+申报收入+合同→4源比对</div>';
  html += '<div class="hb-mi"><span class="hb-mi-label">成本</span>进项发票+银行付款+入库单+存货账+合同→5源比对</div>';
  html += '<div class="hb-mi"><span class="hb-mi-label">工资</span>工资表+银行代发+个税申报+社保参保→4源比对</div>';
  html += '</div>';
  html += '</div>';

  // 5.5 资料缺失
  html += '<div class="hb-method-card">';
  html += '<div class="hb-method-icon hb-m-icon-purple">🔮</div>';
  html += '<h3>5.5 资料缺失→风险推理法</h3>';
  html += '<p class="hb-method-principle">资料的缺失本身就是信号。每缺一类资料，对应一条可推理的稽查风险链。</p>';
  html += '<div class="hb-method-items">';
  html += '<div class="hb-mi"><span class="hb-mi-label">链路</span>缺失XX→无法验证YY→税务机关采用ZZ替代→替代结果远超实际→法律后果</div>';
  html += '<div class="hb-mi"><span class="hb-mi-label">示例</span>缺失凭证→无法追溯分录准确性→账簿不健全→核定征收→远超实际税负</div>';
  html += '</div>';
  html += '</div>';

  // 5.6 经营实质
  html += '<div class="hb-method-card">';
  html += '<div class="hb-method-icon hb-m-icon-cyan">🌐</div>';
  html += '<h3>5.6 经营实质分析法</h3>';
  html += '<p class="hb-method-principle">从交易特征反向验证商业合理性——发票数据模式本身就能暴露问题。</p>';
  html += '<div class="hb-method-items">';
  html += '<div class="hb-mi"><span class="hb-mi-label">地理</span>企业A省/供应商B省/加工商C省+零运输费→货物流断裂→交易存疑</div>';
  html += '<div class="hb-mi"><span class="hb-mi-label">品名</span>生产企业采购与经营范围无关的消费品→虚开发票嫌疑</div>';
  html += '<div class="hb-mi"><span class="hb-mi-label">时间</span>月末/季末集中开票→突击冲成本→配比异常</div>';
  html += '</div>';
  html += '</div>';

  // 5.7 客户三源穿透
  html += '<div class="hb-method-card">';
  html += '<div class="hb-method-icon hb-m-icon-red">🎯</div>';
  html += '<h3>5.7 客户维度三源穿透法</h3>';
  html += '<p class="hb-method-principle">不以"总收款vs总开票"算偏差，穿透到每个客户维度——逐户匹配开票金额与银行收款金额。</p>';
  html += '<div class="hb-method-items">';
  html += '<div class="hb-mi"><span class="hb-mi-label">逻辑</span>总额偏差可能因多收少收互抵，逐户偏差才暴露真实问题</div>';
  html += '<div class="hb-mi"><span class="hb-mi-label">五时点</span>合同签订→发货/交付→开票→收款→会计确认收入</div>';
  html += '<div class="hb-mi"><span class="hb-mi-label">收款>开票</span>已交货未开票（隐匿收入）| 预收货款</div>';
  html += '</div>';
  html += '</div>';

  html += '</div>'; // hb-method-grid
  html += '</section>';

  // ═══ 第六部分：稽查判定规则（2026-06-28 老邓亲授）═══
  html += '<section id="judgment-rules" class="hb-section">';
  html += '<h2 class="hb-section-title"><span class="hb-section-num">六</span> 稽查判定规则</h2>';
  html += '<p class="hb-section-lead">以下规则定义了系统如何综合分析资料——不是靠硬编码关键词，而是通过思考、对比、交叉验证得出综合判断结论。所有规则已写入代码自动执行。</p>';

  // 规则1: 公司身份锚定
  html += '<div class="hb-card" style="margin-bottom:16px">';
  html += '<h3 style="font-size:14px;font-weight:700;color:#0f172a;margin:0 0 8px">📌 规则一：公司身份锚定</h3>';
  html += '<p style="font-size:13px;color:#475569;line-height:1.8;margin:0">所有分析必须以当前账套公司为锚点。系统从主页侧边栏读取公司名称与统一社会信用代码，作为后续所有判断的基准。销项发票的销售方只有一个——就是账套公司；进项发票的购买方也只有一个——就是账套公司。</p>';
  html += '<p style="font-size:12px;color:#94a3b8;margin:4px 0 0"><strong>执行位置：</strong>engine/pipeline.py 综合判断层 · engine/domain_analysis.py _is_service_industry</p>';
  html += '</div>';

  // 规则2: 发票方向自动判定
  html += '<div class="hb-card" style="margin-bottom:16px">';
  html += '<h3 style="font-size:14px;font-weight:700;color:#0f172a;margin:0 0 8px">🧭 规则二：发票方向自动判定</h3>';
  html += '<p style="font-size:13px;color:#475569;line-height:1.8;margin:0">上传发票资料后，系统逐行扫描购买方名称/税号与销售方名称/税号，与当前账套公司比对：</p>';
  html += '<ul style="font-size:13px;color:#475569;margin:6px 0;padding-left:20px">';
  html += '<li><strong>公司名/USCC出现在购买方列</strong> → 进项发票（供应商开给公司）</li>';
  html += '<li><strong>公司名/USCC出现在销售方列</strong> → 销项发票（公司开给客户）</li>';
  html += '<li><strong>买卖双方都有信息但都不含公司</strong> → 存疑（此发票不属于本账套，排除出分析）</li>';
  html += '<li><strong>仅有销售方信息无购买方</strong> → 进项（公司推断为购买方）</li>';
  html += '</ul>';
  html += '<p style="font-size:12px;color:#94a3b8;margin:4px 0 0"><strong>执行位置：</strong>engine/pipeline.py 发票方向判定 · 存疑过滤</p>';
  html += '</div>';

  // 规则3: 综合判断
  html += '<div class="hb-card" style="margin-bottom:16px">';
  html += '<h3 style="font-size:14px;font-weight:700;color:#0f172a;margin:0 0 8px">🧩 规则三：综合判断（四方交叉验证）</h3>';
  html += '<p style="font-size:13px;color:#475569;line-height:1.8;margin:0">系统判定文件类型不依赖单一来源，而是收集四方证据交叉验证：<strong>文件名暗示 → 列头推理 → 数据扫描（买卖方身份收集）→ 公司匹配</strong>。证据一致→高置信度确认；证据冲突→优先相信数据推理（因为文件名可能误命名，但数据说了真话）；全部不匹配→标注存疑。</p>';
  html += '<p style="font-size:12px;color:#94a3b8;margin:4px 0 0"><strong>执行位置：</strong>engine/pipeline.py _is_service_goods · 综合判断层 · 三方证据记录</p>';
  html += '</div>';

  // 规则4: 进项再分类
  html += '<div class="hb-card" style="margin-bottom:16px">';
  html += '<h3 style="font-size:14px;font-weight:700;color:#0f172a;margin:0 0 8px">📊 规则四：进项发票再分类</h3>';
  html += '<p style="font-size:13px;color:#475569;line-height:1.8;margin:0">判定为进项后，系统进一步区分用途：含<strong>"有效抵扣税额""勾选状态""勾选时间"</strong>等列的 → 进项抵扣认证（用于增值税进项税额抵扣）；不含上述列的 → 进项发票（用于记账）。两种用途不可混淆——抵扣认证独立于记账发票。</p>';
  html += '<p style="font-size:12px;color:#94a3b8;margin:4px 0 0"><strong>执行位置：</strong>engine/pipeline.py 列头推理 · filename_type_map.json</p>';
  html += '</div>';

  // 规则5: 服务行业闸门
  html += '<div class="hb-card" style="margin-bottom:16px">';
  html += '<h3 style="font-size:14px;font-weight:700;color:#0f172a;margin:0 0 8px">🚫 规则五：服务行业闸门</h3>';
  html += '<p style="font-size:13px;color:#475569;line-height:1.8;margin:0">销项品名的金税分类编码属于服务行业（广告服务/信息技术服务/咨询服务/金融服务等25类）时，自动跳过以下分析：<strong>进销存台账、BOM表（物料清单）、进销比、毛利率行业对标</strong>。服务行业以人力/知识/创意为核心成本，不适用基于实物商品流转的指标。三层闸门确保全覆盖：管道层→域分析层→引擎输出层。</p>';
  html += '<p style="font-size:12px;color:#94a3b8;margin:4px 0 0"><strong>执行位置：</strong>industry_data.json service_industries · pipeline.py 三层过滤 · domain_analysis.py _is_service_industry</p>';
  html += '</div>';

  // 规则6: 品名级精准过滤
  html += '<div class="hb-card" style="margin-bottom:16px">';
  html += '<h3 style="font-size:14px;font-weight:700;color:#0f172a;margin:0 0 8px">🎯 规则六：品名级精准过滤</h3>';
  html += '<p style="font-size:13px;color:#475569;line-height:1.8;margin:0">当一家公司既有服务品名又有实物品名时，系统不搞一刀切：<strong>服务品名（如*广告服务*广告发布）跳过进销存比对，实物品名（如*印刷品*宣传册）正常纳入进销存检查</strong>。按品名的金税分类编码逐项判定，精准到品名级别。</p>';
  html += '<p style="font-size:12px;color:#94a3b8;margin:4px 0 0"><strong>执行位置：</strong>engine/pipeline.py _is_service_goods() · sale_by_goods 过滤</p>';
  html += '</div>';

  // 规则7: 配置外部化
  html += '<div class="hb-card" style="margin-bottom:16px">';
  html += '<h3 style="font-size:14px;font-weight:700;color:#0f172a;margin:0 0 8px">⚙️ 规则七：规则配置外部化</h3>';
  html += '<p style="font-size:13px;color:#475569;line-height:1.8;margin:0">服务行业编码、文件名类型映射、行业基准值等规则数据全部从JSON配置文件读取，不硬编码在代码中。新增行业或文件类型只需修改配置文件（industry_data.json / filename_type_map.json），无需改动任何Python代码。确保跨行业扩展时核心逻辑不受影响。</p>';
  html += '<p style="font-size:12px;color:#94a3b8;margin:4px 0 0"><strong>配置文件：</strong>static/industry_data.json · static/filename_type_map.json · static/type_anchors.json</p>';
  html += '</div>';
  html += '</section>';

  // ═══ 第七部分：系统与规程映射 ═══
  html += '<section id="system-mapping" class="hb-section">';
  html += '<h2 class="hb-section-title"><span class="hb-section-num">七</span> 系统方法论与法定程序映射</h2>';
  html += '<p class="hb-section-lead">本系统五大核心引擎一一对应《税务稽查工作规程》的法定程序——确保每一步都有法可依、有据可查。</p>';

  // 映射总览
  html += '<div class="hb-engine-grid">';
  var engines = [
    {icon:'📋', name:'线索链引擎', color:'#2563eb', law:'第21条(检查前准备)<br>第24条(收集证据)', desc:'自动扫描14类资料异常模式，生成初步线索。每条含触发条件、风险等级、调查步骤。<strong>当前391条线索链，覆盖29个数据域。</strong>'},
    {icon:'🔒', name:'证据链引擎', color:'#dc2626', law:'第24条(证据真实关联)<br>第40条(稽查底稿)', desc:'每条线索自动收集关联规则ID和数据域→触发率≥60%+≥3规则+≥2域→证据闭环。<strong>当前740条证据链+10条跨域链，234条闭环。</strong>'},
    {icon:'⚡', name:'分析链引擎', color:'#10b981', law:'第47条(审理7项)<br>第54条(审理报告)', desc:'逐条验证how_found→tax_impact→policy_ref三要素，确保事实清楚、证据充分、法律适用正确。'},
    {icon:'🎯', name:'方法论过滤器', color:'#8b5cf6', law:'第48条(退回补正)', desc:'自动剔除不具备数据支撑的噪声发现，只有通过过滤的发现才进入最终报告。CAP/COND_BAN/DEDUP三层。'},
    {icon:'🛡️', name:'全链路质量体系', color:'#06b6d4', law:'第72-75条(案卷管理)', desc:'全流程可追溯——每份报告可还原到证据链、线索链和原始数据。<strong>18组件覆盖5大层次。</strong>'}
  ];
  for (var e = 0; e < engines.length; e++) {
    var eng = engines[e];
    html += '<div class="hb-engine-card" style="border-left:4px solid ' + eng.color + ';">';
    html += '<h3>' + eng.icon + ' ' + eng.name + '</h3>';
    html += '<div class="hb-engine-law">📜 ' + eng.law + '</div>';
    html += '<p class="hb-engine-desc">' + eng.desc + '</p>';
    html += '</div>';
  }
  html += '</div>';

  // 流程对照
  html += '<h3 class="hb-subtitle">6.1 工作流程对照</h3>';
  html += '<div class="hb-compare-grid">';
  html += '<div class="hb-compare-col hb-compare-law">';
  html += '<h4>📜 法定稽查流程</h4>';
  html += '<div class="hb-compare-step">① 选案（第14-20条）<br><small>确定待查对象</small></div>';
  html += '<div class="hb-compare-arrow">↓</div>';
  html += '<div class="hb-compare-step">② 检查（第21-45条）<br><small>收集证据→制作底稿→撰写报告</small></div>';
  html += '<div class="hb-compare-arrow">↓</div>';
  html += '<div class="hb-compare-step">③ 审理（第46-60条）<br><small>逐项审核→退回补正→作出决定</small></div>';
  html += '<div class="hb-compare-arrow">↓</div>';
  html += '<div class="hb-compare-step">④ 执行（第61-71条）<br><small>送达文书→追缴税款→强制执行</small></div>';
  html += '<div class="hb-compare-arrow">↓</div>';
  html += '<div class="hb-compare-step">⑤ 案卷管理（第72-77条）<br><small>立卷归档</small></div>';
  html += '</div>';
  html += '<div class="hb-compare-col hb-compare-sys">';
  html += '<h4>⚙️ 系统自动化流程</h4>';
  html += '<div class="hb-compare-step">① 文件解析（域0）<br><small>提取结构化数据→识别14类资料</small></div>';
  html += '<div class="hb-compare-arrow">↓</div>';
  html += '<div class="hb-compare-step">② 域分析（域1-35）<br><small>线索链391+证据链740+</small></div>';
  html += '<div class="hb-compare-arrow">↓</div>';
  html += '<div class="hb-compare-step">③ 方法论过滤+分析链验证<br><small>跨域关联推理→证据闭环升级</small></div>';
  html += '<div class="hb-compare-arrow">↓</div>';
  html += '<div class="hb-compare-step">④ 综合定性层<br><small>生成正式稽查报告→P0/P1/P2分级</small></div>';
  html += '<div class="hb-compare-arrow">↓</div>';
  html += '<div class="hb-compare-step">⑤ 全链路质量保障<br><small>18组件可追溯→发现可还原到原始数据</small></div>';
  html += '</div>';
  html += '</div>';

  // 证据标准对照
  html += '<h3 class="hb-subtitle">6.2 证据标准对照</h3>';
  html += '<table class="hb-table hb-table-striped">';
  html += '<thead><tr><th style="width:200px;">法定证据标准（《规程》）</th><th style="width:90px;">条款</th><th>系统实现</th></tr></thead><tbody>';
  html += '<tr><td>证据材料应当<strong>真实</strong>，与所证明事项<strong>相关联</strong></td><td>第24条</td><td>证据链引擎要求≥2个独立数据域交叉验证——单源数据只是线索，不是证据</td></tr>';
  html += '<tr><td>电子数据应打印并注明"与电子数据核对无误"</td><td>第30条</td><td>文件解析保留原始文件名+时间戳，每条数据可追溯到原始文件行列</td></tr>';
  html += '<tr><td>应当制作稽查底稿，记录事实，归集证据</td><td>第40条</td><td>证据链引擎自动归集每条线索关联的所有规则ID</td></tr>';
  html += '<tr><td>稽查报告须含违法事实+处理处罚建议及依据</td><td>第42条</td><td>每项发现含：how_found+tax_impact+policy_ref+suggestion</td></tr>';
  html += '<tr><td>审理须审核：事实是否清楚+证据是否充分+法律是否适当+程序是否合法</td><td>第47条</td><td>分析链引擎+方法论过滤器=自动化预审理</td></tr>';
  html += '</tbody></table>';
  html += '</section>';

  // 底部声明
  html += '<div class="hb-footer">';
  html += '<p>⚠ 本手册内容基于《税务稽查工作规程》《税收征收管理法》及实战经验提炼，全行业适用。具体案件处理应结合实际情况。</p>';
  html += '</div>';

  html += '</main>'; // handbook-content
  html += '</div>'; // handbook-layout

  container.innerHTML = html;

  // ── 初始化滚动监听 ──
  setTimeout(initHandbookScrollSpy, 200);

  // ── #4: 绑定方法论→仪表盘联动 ──
  setTimeout(bindMethodologyDashboardLinks, 300);

  // ═══ 异步加载管道数据：深度串联一键分析 ═══
  (function() {
    try {
      if (typeof getSharedAnalysis !== 'function') {
        document.getElementById('handbook-pipeline-status').innerHTML =
          '<div class="hb-status-bar hb-status-warn">⚠ 稽查管道尚未加载，请先运行一键分析后刷新页面。</div>';
        return;
      }
      getSharedAnalysis().then(function(data) {
        var report = (data && data.report) ? data.report : {};
        var allF = report.all_findings || [];
        var high = report.high_risk || 0;
        var mid = report.mid_risk || 0;
        var total = report.total_risks || allF.length;

        var statusHtml = '<div class="hb-status-bar hb-status-connected">';
        statusHtml += '🔗 <strong>已连接一键分析管道</strong>';
        statusHtml += ' &nbsp;|&nbsp; 📊 ' + total + '条发现';
        statusHtml += ' &nbsp;|&nbsp; <span style="color:#dc2626;">🔴 高风险 ' + high + '</span>';
        statusHtml += ' &nbsp;|&nbsp; <span style="color:#f59e0b;">🟡 中风险 ' + mid + '</span>';
        statusHtml += ' &nbsp; <a href="#" onclick="navigateTo(\'tax-doc-analysis\');return false" style="color:#2563eb;margin-left:8px;">查看完整报告 →</a>';
        statusHtml += '</div>';
        document.getElementById('handbook-pipeline-status').innerHTML = statusHtml;

        // ─── 2. 14类必查资料动态标记───
        var completenessFinding = null;
        for (var fi = 0; fi < allF.length; fi++) {
          if (allF[fi].type === '资料完备度综合评估') { completenessFinding = allF[fi]; break; }
        }
        if (completenessFinding && completenessFinding.items) {
          var missingNames = {};
          for (var mi = 0; mi < completenessFinding.items.length; mi++) {
            missingNames[completenessFinding.items[mi]['缺失资料']] = completenessFinding.items[mi]['缺失后果'];
          }
          // 更新每一张资料卡片的状态
          var docCards = document.querySelectorAll('#documents .hb-doc-card');
          for (var dc = 0; dc < docCards.length; dc++) {
            var card = docCards[dc];
            var strongEl = card.querySelector('strong');
            if (strongEl) {
              var docName = strongEl.textContent.trim();
              if (missingNames[docName]) {
                var badge = document.createElement('span');
                badge.className = 'hb-doc-badge hb-badge-red';
                badge.textContent = '❌ 未提交';
                badge.style.marginLeft = '8px';
                strongEl.parentNode.insertBefore(badge, strongEl.nextSibling);
                card.classList.add('hb-doc-high');
              } else {
                var badge2 = document.createElement('span');
                badge2.className = 'hb-doc-badge hb-badge-green';
                badge2.textContent = '✅ 已提交';
                badge2.style.marginLeft = '8px';
                strongEl.parentNode.insertBefore(badge2, strongEl.nextSibling);
              }
            }
          }
        }

        // ─── 3. 方法论关联计数 ───
        var methodCounts = { '四流合一': 0, '三源比对': 0, '资金回流': 0, '多源交叉': 0, '经营实质': 0 };
        for (var fj = 0; fj < allF.length; fj++) {
          var ft = allF[fj].type || '';
          var fd = allF[fj].detail || '';
          var combined = ft + ' ' + fd;
          if (combined.indexOf('四流') > -1 || combined.indexOf('合同') > -1 || combined.indexOf('发票') > -1) methodCounts['四流合一']++;
          if (combined.indexOf('申报') > -1 && (combined.indexOf('开票') > -1 || combined.indexOf('收款') > -1)) methodCounts['三源比对']++;
          if (combined.indexOf('资金回流') > -1 || combined.indexOf('回流') > -1) methodCounts['资金回流']++;
          if (combined.indexOf('交叉') > -1 || combined.indexOf('多源') > -1) methodCounts['多源交叉']++;
          if (combined.indexOf('经营实质') > -1 || combined.indexOf('地理') > -1 || combined.indexOf('品名') > -1) methodCounts['经营实质']++;
        }
        // 更新方法论各节标题
        var methodSections = document.getElementById('methodology');
        if (methodSections) {
          var h3s = methodSections.querySelectorAll('h3');
          for (var h = 0; h < h3s.length; h++) {
            var hText = h3s[h].textContent;
            for (var mk in methodCounts) {
              if (hText.indexOf(mk) > -1 && methodCounts[mk] > 0) {
                h3s[h].innerHTML += ' <span style="font-size:11px;color:#2563eb;font-weight:400;">（本次分析关联' + methodCounts[mk] + '条发现）</span>';
                break;
              }
            }
          }
        }
      }).catch(function() {
        document.getElementById('handbook-pipeline-status').innerHTML =
          '<div class="hb-status-bar hb-status-warn">📋 暂无分析数据 — <a href="#" onclick="navigateTo(\'tax-doc-analysis\');return false" style="color:#2563eb;">点击运行一键分析</a> 后将显示实时数据关联。</div>';
      });
    } catch(e) {
      document.getElementById('handbook-pipeline-status').innerHTML = '';
    }
  })();
}

// 辅助函数：滚动到指定区域 + TOC联动
function scrollToSection(id) {
  var el = document.getElementById(id);
  if (el) {
    el.scrollIntoView({behavior: 'smooth', block: 'start'});
  }
  // 更新TOC高亮
  document.querySelectorAll('.toc-item').forEach(function(t) {
    t.classList.toggle('active', t.getAttribute('data-target') === id);
  });
}

// 滚动监听：自动高亮当前区域的TOC条目
function initHandbookScrollSpy() {
  var tocItems = document.querySelectorAll('.toc-item');
  var sections = [];
  tocItems.forEach(function(item) {
    var id = item.getAttribute('data-target');
    var el = document.getElementById(id);
    if (el) sections.push({id: id, el: el, toc: item});
  });
  if (!sections.length) return;

  var contentArea = document.getElementById('content-area');
  if (!contentArea) return;

  contentArea.addEventListener('scroll', function() {
    var scrollTop = contentArea.scrollTop + 120; // offset for hero
    for (var i = sections.length - 1; i >= 0; i--) {
      if (sections[i].el.offsetTop <= scrollTop) {
        tocItems.forEach(function(t) { t.classList.remove('active'); });
        sections[i].toc.classList.add('active');
        break;
      }
    }
  });
}

// TOC点击事件委托
document.addEventListener('click', function(e) {
  var tocItem = e.target.closest('.toc-item');
  if (tocItem) {
    e.preventDefault();
    var target = tocItem.getAttribute('data-target');
    if (target) scrollToSection(target);
  }
});

// ── #4: 手册→仪表盘联动：点击方法论→跳转仪表盘对账标签页 ──
function navigateToDashboardWithMethod(methodId) {
  if (typeof navigateTo === 'function') {
    // 更新URL参数后跳转
    navigateTo('engine-dashboard');
    setTimeout(function() {
      if (window.location.hash === '#engine-dashboard' || (typeof currentPage !== 'undefined' && currentPage === 'engine-dashboard')) {
        if (typeof switchEngineTab === 'function') {
          switchEngineTab('methods');
          window._dashboardFocusMethod = methodId;
        }
      }
    }, 300);
  }
}

// 为手册中每个方法论卡片绑定仪表盘联动
function bindMethodologyDashboardLinks() {
  var cards = document.querySelectorAll('#methodology .card');
  var methodMap = {
    '四流合一': '③',
    '三层分类': '④',
    '三源比对': '⑥',
    '资金回流': 'causal',
    '多源交叉': 'missing',
    '资料缺失': 'missing',
    '经营实质': 'geo',
    '三源穿透': '㉕',
  };
  for (var i = 0; i < cards.length; i++) {
    var h3 = cards[i].querySelector('h3');
    if (!h3) continue;
    var hText = h3.textContent || '';
    for (var kw in methodMap) {
      if (hText.indexOf(kw) > -1) {
        var methodId = methodMap[kw];
        h3.style.cursor = 'pointer';
        h3.title = '点击查看方法论对账详情';
        h3.setAttribute('data-method-id', methodId);
        
        // 添加仪表盘链接标记
        var linkSpan = document.createElement('span');
        linkSpan.style.cssText = 'font-size:10px;color:#3b82f6;margin-left:8px;font-weight:400;opacity:0.8';
        linkSpan.textContent = '[对账]';
        h3.appendChild(linkSpan);
        break;
      }
    }
  }
  
  // 委托事件：点击h3跳转仪表盘
  document.getElementById('methodology').addEventListener('click', function(e) {
    var target = e.target.closest('h3[data-method-id]');
    if (target) {
      navigateToDashboardWithMethod(target.getAttribute('data-method-id'));
    }
  });
}
