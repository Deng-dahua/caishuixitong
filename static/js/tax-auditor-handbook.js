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

  // ═══ 系统实时状态（连接一键分析管道）═══
  html += '<div id="handbook-pipeline-status" style="margin-bottom:16px;">';
  html += '<div class="card" style="padding:12px 16px;background:#f0f9ff;border:1px solid #bae6fd;">';
  html += '<div style="display:flex;align-items:center;gap:8px;">';
  html += '<span style="font-size:16px;">🔗</span>';
  html += '<span style="font-size:13px;color:#0369a1;">正在连接一键分析管道…</span>';
  html += '</div>';
  html += '</div>';
  html += '</div>';

  // ═══ 导航标签 ═══
  html += '<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:20px;">';
  html += '<button class="btn btn-sm" onclick="scrollToSection(\'workflow\')">📋 稽查工作流程</button>';
  html += '<button class="btn btn-sm" onclick="scrollToSection(\'documents\')">📁 14类必查资料</button>';
  html += '<button class="btn btn-sm" onclick="scrollToSection(\'report\')">📝 报告编制规范</button>';
  html += '<button class="btn btn-sm" onclick="scrollToSection(\'laws\')">⚖️ 关键法律条文</button>';
  html += '<button class="btn btn-sm" onclick="scrollToSection(\'methodology\')">🔬 稽查方法论</button>';
  html += '<button class="btn btn-sm" onclick="scrollToSection(\'system-mapping\')">🔗 系统与规程映射</button>';
  html += '</div>';

  // ═══════════════════════════════════════
  // 第一部分：稽查工作流程
  // ═══════════════════════════════════════
  html += '<div id="workflow" class="card" style="margin-bottom:20px;">';
  html += '<h2 style="border-left:4px solid #dc2626;padding-left:12px;">📋 一、稽查工作流程</h2>';
  html += '<p class="muted">税务稽查分为四个阶段：选案→检查→审理→执行。每个阶段有明确的法定时限和工作要求。</p>';

  html += '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;margin-top:16px;">';

  // 稽查制度基础
  html += '<div class="card" style="border-top:3px solid #6366f1;margin-bottom:16px;grid-column:1/-1;">';
  html += '<h3>稽查制度基础——总则核心要点（《规程》第1-9条）</h3>';
  html += '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;margin-top:8px;">';
  
  html += '<div style="background:#f5f3ff;padding:12px;border-radius:6px;">';
  html += '<strong style="color:#6366f1;">四分离原则（第5条）</strong>';
  html += '<p style="margin:6px 0 0;font-size:13px;">稽查局查处税收违法案件时，实行<strong>选案、检查、审理、执行分工制约</strong>原则。四个部门各司其职、相互制衡——选案的人不检查，检查的人不审理，审理的人不执行。这是稽查公正性的制度保障。</p>';
  html += '</div>';
  
  html += '<div style="background:#fef2f2;padding:12px;border-radius:6px;">';
  html += '<strong style="color:#dc2626;">8项工作纪律（第7-8条）</strong>';
  html += '<ul style="margin:6px 0 0;font-size:13px;padding-left:16px;">';
  html += '<li>有回避情形的应当回避（第7条）</li>';
  html += '<li>不得违反程序/超越权限（第8条）</li>';
  html += '<li>不得利用职权谋取利益</li>';
  html += '<li>不得玩忽职守</li>';
  html += '<li><strong>不得泄露秘密、通风报信、泄露案情</strong></li>';
  html += '<li>不得弄虚作假、夸大或隐瞒案情</li>';
  html += '<li>不得接受请客送礼</li>';
  html += '<li>未经批准不得私自会见被查对象</li>';
  html += '</ul>';
  html += '</div>';
  
  html += '<div style="background:#eff6ff;padding:12px;border-radius:6px;">';
  html += '<strong style="color:#2563eb;">信息化要求（第9条）</strong>';
  html += '<p style="margin:6px 0 0;font-size:13px;">税务机关必须<strong>不断提高稽查信息化应用水平</strong>，充分利用现代信息技术采集涉税信息，强化稽查管理和执法监督。<br><span style="color:#6b7280;">💡 本系统的文件解析→域分析→线索链→证据链→分析链→报告生成的自动化管道，正是第9条的实践落地。</span></p>';
  html += '</div>';
  
  html += '<div style="background:#f0fdf4;padding:12px;border-radius:6px;">';
  html += '<strong style="color:#10b981;">基本任务（第2条）</strong>';
  html += '<p style="margin:6px 0 0;font-size:13px;">依法查处税收违法行为，保障税收收入，维护税收秩序，促进依法纳税。以<strong>事实为根据，以法律为准绳</strong>，坚持公平、公开、公正、效率原则（第3条）。</p>';
  html += '</div>';
  html += '</div>';
  html += '</div>';

  // 选案
  html += '<div class="card" style="border-top:3px solid #2563eb;">';
  html += '<h3>① 选案环节（《规程》第14-20条）</h3>';
  html += '<table class="table table-sm"><tbody>';
  html += '<tr><td style="white-space:nowrap;font-weight:600;width:100px;">案源获取<br><span style="font-size:11px;color:#6b7280;">第14条</span></td><td>稽查局通过多种渠道获取案源信息，<strong>集体研究</strong>，合理准确地选择和确定稽查对象。选案部门负责稽查对象选取，并对案件查处情况进行跟踪管理。</td></tr>';
  html += '<tr><td style="font-weight:600;">稽查计划<br><span style="font-size:11px;color:#6b7280;">第15条</span></td><td>必须有计划地实施稽查，<strong>严格控制检查次数</strong>。年度终了前制定下一年度稽查工作计划，经批准后实施并报上一级备案。</td></tr>';
  html += '<tr><td style="font-weight:600;">8类案源信息<br><span style="font-size:11px;color:#6b7280;">第16条</span></td><td>①财务指标/税收征管资料/稽查资料/情报交换和协查线索 ②上级交办案件 ③上级安排的专项检查 ④税务局相关部门移交的违法信息 ⑤<strong>检举涉税违法信息</strong> ⑥其他部门和单位转来的信息 ⑦社会公共信息 ⑧其他相关信息<br><span style="color:#dc2626;font-size:12px;">⚠ 第⑤类（检举）是企业的最大不可控风险——任何人（离职员工、竞争对手、纠纷对方）都可以向举报中心实名或匿名检举。</span></td></tr>';
  html += '<tr><td style="font-weight:600;">举报处理<br><span style="font-size:11px;color:#6b7280;">第17-18条</span></td><td>稽查局设立<strong>税收违法案件举报中心</strong>。实名检举经查实为国家挽回损失的，给予奖励。举报中心区分处理：线索清楚→列入案源；内容不详→暂存；属于其他部门职责→转交。</td></tr>';
  html += '<tr><td style="font-weight:600;">筛选方法<br><span style="font-size:11px;color:#6b7280;">第19条</span></td><td>采取<strong>计算机分析、人工分析、人机结合分析</strong>等方法筛选案源——有税收违法嫌疑的确定为待查对象→填制《税务稽查立案审批表》→经稽查局局长批准后立案。<br><span style="color:#6b7280;font-size:12px;">💡 系统对应：本系统的自动化风险扫描+一键分析，本质上是"计算机分析"端——在稽查立案前模拟税务机关的案源筛选逻辑，让企业提前发现自身风险。</span></td></tr>';
  html += '<tr><td style="font-weight:600;">立案检查<br><span style="font-size:11px;color:#6b7280;">第20条</span></td><td>批准立案后，选案部门制作《税务稽查任务通知书》，连同有关资料移交检查部门。选案部门建立案件管理台账，跟踪查处进展。</td></tr>';
  html += '</tbody></table>';
  html += '</div>';

  // 检查
  html += '<div class="card" style="border-top:3px solid #f59e0b;">';
  html += '<h3>② 检查环节（《规程》第21-45条）</h3>';
  html += '<table class="table table-sm"><tbody>';
  html += '<tr><td style="white-space:nowrap;font-weight:600;width:100px;">检查前准备<br><span style="font-size:11px;color:#6b7280;">第21条</span></td><td>查阅被查对象纳税档案，了解生产经营情况、所属行业特点、财务会计制度和会计核算软件，熟悉相关税收政策，确定检查方法。<br><span style="color:#6b7280;font-size:12px;">💡 系统对应：线索链引擎在检查前自动完成上述工作——从数据中自动提取行业特征、识别异常模式、生成初步线索。</span></td></tr>';
  html += '<tr><td style="font-weight:600;">检查时限<br><span style="font-size:11px;color:#6b7280;">第22条</span></td><td>检查应当自实施检查之日起<strong>60日内</strong>完成，确需延长的经稽查局局长批准。检查应当由<strong>两名以上</strong>检查人员共同实施，出示税务检查证和《税务检查通知书》。</td></tr>';
  html += '<tr><td style="font-weight:600;">检查方法<br><span style="font-size:11px;color:#6b7280;">第23条</span></td><td>①实地检查 ②调取账簿资料 ③询问 ④查询存款账户或储蓄存款 ⑤异地协查。对电子信息系统管理的被查对象，可要求其打开系统或提供电子数据复制件；拒不提供的，经批准可采取技术手段直接检查。<br><span style="color:#6b7280;font-size:12px;">💡 系统对应：文件解析模块（域0）自动提取电子数据→域分析模块逐一检查各数据域→线索链从异常中生成发现。</span></td></tr>';
  html += '<tr><td style="font-weight:600;">证据收集<br><span style="font-size:11px;color:#6b7280;">第24-32条</span></td><td>收集的证据材料应当<strong>真实</strong>，并与所证明的事项<strong>相关联</strong>。禁止偷拍/偷录/窃听/利诱/欺诈/胁迫/暴力取证。证据类型包括：书证（账簿/凭证/合同/发票）、物证（存货/设备）、视听资料（录音/录像）、电子数据、证人证言、当事人陈述、勘验笔录。<br><span style="color:#6b7280;font-size:12px;">💡 系统对应：证据链引擎——每项发现自动收集关联规则ID+数据域→计算触发率→≥60%且≥3规则+≥2域→形成证据闭环。</span></td></tr>';
  html += '<tr><td style="font-weight:600;">调取资料<br><span style="font-size:11px;color:#6b7280;">第25-26条</span></td><td>出具《调取账簿资料通知书》和《调取账簿资料清单》。以前年度资料<strong>3个月</strong>内退还，当年资料<strong>30日</strong>内退还（需经设区的市以上税务局局长批准）。<br><span style="color:#6b7280;font-size:12px;">💡 调取范围即14类稽查必查资料——详见本手册第二部分。</span></td></tr>';
  html += '<tr><td style="font-weight:600;">稽查工作底稿<br><span style="font-size:11px;color:#6b7280;">第40条</span></td><td>检查过程中必须制作《税务稽查工作底稿》，<strong>记录案件事实，归集相关证据材料，并签字注明日期</strong>。工作底稿是稽查报告的基础——没有工作底稿就没有稽查报告。</td></tr>';
  html += '<tr><td style="font-weight:600;">稽查报告<br><span style="font-size:11px;color:#6b7280;">第42条</span></td><td>检查结束时制作《税务稽查报告》，必须包含<strong>10项内容</strong>：①案件来源 ②被查对象基本情况 ③检查时间和所属期间 ④检查方式方法及措施 ⑤查明的违法事实及性质手段 ⑥是否有拒绝阻挠检查情形 ⑦被查对象对调查事实的意见 ⑧税务处理处罚建议及依据 ⑨其他应说明事项 ⑩检查人员签名和报告时间</td></tr>';
  html += '<tr><td style="font-weight:600;">移交审理<br><span style="font-size:11px;color:#6b7280;">第43条</span></td><td>检查完毕，将《税务稽查报告》《税务稽查工作底稿》及相关证据材料在<strong>5个工作日内</strong>移交审理部门。</td></tr>';
  html += '<tr><td style="font-weight:600;">中止/终结<br><span style="font-size:11px;color:#6b7280;">第44-45条</span></td><td>中止检查条件：当事人被限制人身自由、账簿被其他国家机关调取未归还等。终结检查条件：被查对象死亡/注销且无财产、违法行为超过法定追究期限等。</td></tr>';
  html += '</tbody></table>';
  html += '</div>';

  // 审理
  html += '<div class="card" style="border-top:3px solid #10b981;">';
  html += '<h3>③ 审理环节（《规程》第46-60条）</h3>';
  html += '<table class="table table-sm"><tbody>';
  html += '<tr><td style="white-space:nowrap;font-weight:600;width:100px;">审理审核重点<br><span style="font-size:11px;color:#6b7280;">第47条</span></td><td>审理人员对《税务稽查报告》逐项审核<strong>7项内容</strong>：<br>①被查对象是否准确<br>②<strong>税收违法事实是否清楚、证据是否充分、数据是否准确、资料是否齐全</strong><br>③适用法律是否适当，定性是否正确<br>④是否符合法定程序<br>⑤是否超越或滥用职权<br>⑥税务处理、处罚建议是否适当<br>⑦其他应审核确认的事项<br><span style="color:#6b7280;font-size:12px;">💡 系统对应：分析链引擎——逐条验证每条发现的"how_found→tax_impact→policy_ref"三要素，确保②③④三项均有据可查。</span></td></tr>';
  html += '<tr><td style="font-weight:600;">退回补正<br><span style="font-size:11px;color:#6b7280;">第48条</span></td><td>有下列情形之一的，审理部门<strong>退回检查部门补正或补充调查</strong>：<br>①被查对象认定错误<br>②<strong>税收违法事实不清、证据不足</strong><br>③不符合法定程序<br>④税务文书不规范不完整<br><span style="color:#6b7280;font-size:12px;">💡 系统对应：方法论过滤器——自动剔除"证据不足/数据不支撑/逻辑不闭环"的噪声发现，相当于审理前的预筛选。</span></td></tr>';
  html += '<tr><td style="font-weight:600;">纠正处理建议<br><span style="font-size:11px;color:#6b7280;">第49条</span></td><td>事实清楚、证据充分，但<strong>适用法律错误或处理建议不当</strong>的，审理部门另行提出处理意见。注意：不是退回补正，而是直接纠正——说明事实层面没问题，法律适用层面需要调整。</td></tr>';
  html += '<tr><td style="font-weight:600;">审理时限<br><span style="font-size:11px;color:#6b7280;">第50条</span></td><td>收到《税务稽查报告》后<strong>15日内</strong>提出审理意见。检查人员补充调查时间和向上级请示政策时间不计入。案情复杂的经批准可延长。</td></tr>';
  html += '<tr><td style="font-weight:600;">告知及听证<br><span style="font-size:11px;color:#6b7280;">第51-53条</span></td><td>拟作出税务行政处罚的，须送达《税务行政处罚事项告知书》，告知<strong>陈述权、申辩权、听证权</strong>。当事人要求听证的，应依法组织听证。审理人员对陈述申辩意见必须认真对待并提出判断意见——<strong>不能直接忽略</strong>。</td></tr>';
  html += '<tr><td style="font-weight:600;">审理报告<br><span style="font-size:11px;color:#6b7280;">第54条</span></td><td>审理完毕制作《税务稽查审理报告》，须包含<strong>6项内容</strong>：①审理基本情况 ②检查人员查明的事实及证据 ③被查对象的陈述申辩情况 ④经审理认定的事实及证据 ⑤税务处理处罚意见及依据 ⑥审理人员和日期</td></tr>';
  html += '<tr><td style="font-weight:600;">四种处理决定<br><span style="font-size:11px;color:#6b7280;">第55-59条</span></td><td>审理部门区分情形作出：<br>①有税收违法行为→《税务处理决定书》（第56条：含税款金额+滞纳金计算+缴纳期限+救济途径）<br>②应当行政处罚→《税务行政处罚决定书》（第57条：含处罚种类+履行方式+救济途径）<br>③违法行为轻微→《不予税务行政处罚决定书》（第58条：含不予处罚理由）<br>④无违法行为→《税务稽查结论》（第59条：含检查结论）<br>所有文书须注明<strong>文件全称、文号和有关条款</strong>。</td></tr>';
  html += '<tr><td style="font-weight:600;">涉嫌犯罪移送<br><span style="font-size:11px;color:#6b7280;">第60条</span></td><td>税收违法行为涉嫌犯罪的→制作《涉嫌犯罪案件移送书》→经所属税务局局长批准→移送公安机关。附送：涉嫌犯罪调查报告、处理/处罚决定书复制件、主要证据材料复制件、补缴税款及罚款明细。</td></tr>';
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

  // ═══ 案卷管理 ═══
  html += '<div style="display:grid;grid-template-columns:1fr;gap:12px;margin-top:4px;">';
  html += '<div class="card" style="border-top:3px solid #ec4899;">';
  html += '<h3>⑤ 案卷管理（《规程》第72-77条）</h3>';
  html += '<table class="table table-sm"><tbody>';
  html += '<tr><td style="white-space:nowrap;font-weight:600;width:100px;">立卷归档<br><span style="font-size:11px;color:#6b7280;">第72条</span></td><td>处理决定执行完毕（或终结检查/终结执行）后，审理部门在<strong>60日内</strong>收集稽查各环节全部资料，整理成税务稽查案卷，归档保管。</td></tr>';
  html += '<tr><td style="font-weight:600;">正卷与副卷<br><span style="font-size:11px;color:#6b7280;">第73条</span></td><td>一案一卷，分别立<strong>正卷</strong>和<strong>副卷</strong>：正卷列入各类证据材料、税务文书等可对外公开的材料；副卷列入检举及奖励材料、案件讨论记录、法定秘密材料等不宜公开的材料。副卷作为<strong>密卷</strong>管理。<br><span style="color:#dc2626;font-size:12px;">⚠ 正卷可被查阅（第76条），意味着你的违法事实和证据材料可以被后续检查、复议、诉讼反复调取。</span></td></tr>';
  html += '<tr><td style="font-weight:600;">排列规则<br><span style="font-size:11px;color:#6b7280;">第74条</span></td><td>原则上按实际稽查程序依次排列；证据材料按问题特征分类，主要证据在前、旁证在后；其他材料按时间顺序+重要程度排列。正件在前，附件在后；重要材料在前，其他在后；汇总性在前，基础性在后。</td></tr>';
  html += '<tr><td style="font-weight:600;color:#dc2626;">保管期限<br><span style="font-size:11px;color:#6b7280;">第75条</span></td><td><strong>偷税、逃避追缴欠税、骗税、抗税案件及涉嫌犯罪案件：永久保存</strong>。一般行政处罚案件：30年。其他案件：10年。<br><span style="color:#dc2626;font-size:12px;">⚠ 这是企业最该恐惧的条款——一旦被认定为偷税，你的案卷永远不会被销毁。30年后你的企业可能不在了，但案卷还在。</span></td></tr>';
  html += '<tr><td style="font-weight:600;">查阅借阅<br><span style="font-size:11px;color:#6b7280;">第76条</span></td><td>税务机关人员查阅需经稽查局局长批准；外部人员查阅需经所属税务局领导批准。未经批准，不得摘抄、复制案卷内容。案卷应在立卷次年6月30日前移交档案管理部门。</td></tr>';
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
  html += '<h3 style="margin-top:16px;">3.1 报告结构——向上级领导汇报的标准化框架</h3>';
  html += '<p style="font-size:13px;color:#6b7280;">本系统生成的稽查报告模拟真实稽查员向上级领导汇报的场景。"标准分析报告"采用正式法律文书格式（7章），"叙事增强报告"采用口头汇报体（8章）。两份报告使用同一数据源，展示角度不同。</p>';

  html += '<h4 style="margin-top:12px;">标准分析报告（7章·正式法律文书）</h4>';
  html += '<table class="table table-sm">';
  html += '<thead><tr><th>章</th><th>内容</th><th>汇报视角</th></tr></thead><tbody>';
  html += '<tr><td>一</td><td>案件来源及稽查对象基本情况</td><td>受理依据+联网核查结果+工商信息表</td></tr>';
  html += '<tr><td>二</td><td>稽查实施情况</td><td>六种稽查方法+经营实质核查过程+资金流/发票流分析</td></tr>';
  html += '<tr><td>三</td><td>稽查结论</td><td>风险评级+发现统计+线索链覆盖+主要高风险事项</td></tr>';
  html += '<tr><td>四</td><td>稽查发现问题及事实认定</td><td>逐项标注调查过程→线索链→证据→法律→建议</td></tr>';
  html += '<tr><td>五</td><td>处理处罚建议</td><td>向领导汇报处理意见+请求审议</td></tr>';
  html += '<tr><td>六</td><td>告知权利义务</td><td>被查单位法定权利告知</td></tr>';
  html += '<tr><td>七</td><td>签字</td><td>稽查执行人签名+日期</td></tr>';
  html += '</tbody></table>';

  html += '<h4 style="margin-top:16px;">叙事增强报告（8章·口头汇报体）</h4>';
  html += '<table class="table table-sm">';
  html += '<thead><tr><th>章</th><th>内容</th><th>汇报场景</th></tr></thead><tbody>';
  html += '<tr><td>开篇</td><td>关于XX公司涉税资料的稽查情况汇报</td><td>"领导，现就XX公司的稽查情况向您汇报"</td></tr>';
  html += '<tr><td>第一章</td><td>案件受理与基本情况</td><td>"本案来源于…我受理后立即启动了稽查工作"</td></tr>';
  html += '<tr><td>第二章</td><td>稽查方案与工作部署</td><td>"在正式稽查前，我制定了六步工作法…"</td></tr>';
  html += '<tr><td>第三章</td><td>稽查实施过程</td><td>按方案顺序逐项执行——资金流→发票流→多源交叉验证</td></tr>';
  html += '<tr><td>第四章</td><td>稽查结论</td><td>"领导，以上稽查工作完成后，我得出以下结论"</td></tr>';
  html += '<tr><td>第五章</td><td>风险疑点详报与证据链</td><td>逐项详报：调查过程→线索链→证据来源→专业判断</td></tr>';
  html += '<tr><td>第六章</td><td>证据链组织总结</td><td>"我如何将孤立疑点串联为完整证据链"——四步证据法</td></tr>';
  html += '<tr><td>第七章</td><td>处理处罚建议</td><td>"根据上述稽查发现和证据链，我提出以下建议…请领导审议"</td></tr>';
  html += '<tr><td>第八章</td><td>告知事项+双签</td><td>被查单位权利告知+汇报人签名+领导审批意见</td></tr>';
  html += '</tbody></table>';
  html += '<div style="margin-top:12px;padding:10px 14px;background:#eff6ff;border-radius:6px;font-size:13px;">';
  html += '<strong>📜 法定依据：</strong>';
  html += '本报告结构同时覆盖《税务稽查工作规程》第42条（<em>《税务稽查报告》10项内容</em>）和第54条（<em>《税务稽查审理报告》6项内容</em>）的全部要求。';
  html += '第42条侧重"检查端"（案件来源+违法事实+处理建议），第54条侧重"审理端"（审理认定+陈述申辩+处理意见）。';
  html += '本系统的"一键分析报告"将两者融合——既包含检查端的发现过程（how_found），也包含审理端的定性依据（tax_impact + policy_ref）。';
  html += '</div>';

  // 叙事风格
  html += '<h3 style="margin-top:20px;">3.2 叙事风格——第一人称稽查员视角 + 汇报体</h3>';
  html += '<div class="card" style="background:#f0fdf4;border:1px solid #bbf7d0;padding:16px;">';
  html += '<p style="margin:0 0 8px 0;"><strong>核心原则：</strong>报告模拟稽查员向上级领导汇报的真实场景。标准报告用正式法律语体（"本人经稽查发现…"），叙事报告用口头汇报体（"领导，我做了以下稽查工作…"）。</p>';
  html += '<p style="margin:0 0 8px 0;"><strong>汇报体示例：</strong></p>';
  html += '<ul style="margin:0;font-size:13px;">';
  html += '<li>✅ <em>"领导，现就XX公司的稽查情况向您详细汇报。"</em>（开篇建立场景）</li>';
  html += '<li>✅ <em>"在正式稽查前，我制定了六步工作法：第一步…第二步…"</em>（展示稽查方案）</li>';
  html += '<li>✅ <em>"我审查了被查单位提交的全部14类稽察必查资料，发现缺失8类，具体为：…"</em></li>';
  html += '<li>✅ <em>"根据上述稽查发现和证据链，我提出以下建议，请领导审议。"</em>（请求上级决策）</li>';
  html += '<li>❌ <em>"经查，该企业存在少申报收入的情形。"</em>（过于概括，缺乏具体数据和判断过程）</li>';
  html += '</ul>';
  html += '<p style="margin:8px 0 0 0;font-size:12px;color:#6b7280;"><strong>场景纪律：</strong>稽查报告同时是法律文书——所有事实陈述必须有证据支撑，所有法律引用必须有条款号，所有金额必须精确。汇报体不是"随便说"，而是"在严谨证据基础上的清晰汇报"。</p>';
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

  // 3.5 稽查报告质量标准
  html += '<h3 style="margin-top:20px;">3.5 稽查报告质量标准——十二项硬指标</h3>';
  html += '<p style="font-size:13px;color:#6b7280;">以下12项标准由两部分构成：前7项提炼自标杆发现"资料完备度综合评估"的优秀实践，后5项从实际缺陷中总结（反模板/反空述/反复制/法条号/空占位符）。每条发现必须过12项检查，不达标标记但不阻塞。</p>';

  html += '<table class="table table-sm">';
  html += '<thead><tr><th style="width:30px;">#</th><th style="width:140px;">标准名称</th><th>判定规则</th><th style="width:200px;">不合格示例</th></tr></thead><tbody>';

  html += '<tr><td style="font-weight:700;">1</td><td><strong>第一人称稽查员叙事</strong></td>';
  html += '<td><code>how_found</code> 和 <code>description</code> 必须以"我"为主语，使用"我审查了""我逐一比对了""我发现"等主动语态。禁止第三人称（"经查""该企业"）、禁止被动语态（"被发现在…"）。</td>';
  html += '<td style="color:#dc2626;font-size:12px;">❌ "经查，该企业存在少申报收入的情形"<br>❌ "销项开票与银行收款名称不匹配，需要按六种商业模式逐笔分析"</td></tr>';

  html += '<tr><td style="font-weight:700;">2</td><td><strong>事实-证据-后果三要素</strong></td>';
  html += '<td>每条发现必须同时包含：①具体事实（多少笔/多少金额/哪些主体）②证据来源（来自哪个数据源/如何交叉验证的）③缺失后果（缺失会导致什么→用什么替代→法律后果是什么）。三者缺一不可。</td>';
  html += '<td style="color:#dc2626;font-size:12px;">❌ "销项发票购方名称与银行收款付款方名称不匹配" — 未说明具体是哪些主体不匹配、差多少金额</td></tr>';

  html += '<tr><td style="font-weight:700;">3</td><td><strong>完整因果链（A→B→C→D）</strong></td>';
  html += '<td>每个后果必须写成因果链，至少三步推导：缺失X→导致Y无法验证→税务机关将采取Z替代手段→最终法律后果。禁止一步到位（缺失→罚款）。</td>';
  html += '<td style="color:#dc2626;font-size:12px;">❌ "缺失凭证→补税+罚款"<br>✅ "缺失凭证→无法追溯分录准确性/科目运用/原始凭证匹配→会计账簿视为不健全→按《税收征收管理法》第三十五条核定征收"</td></tr>';

  html += '<tr><td style="font-weight:700;">4</td><td><strong>可操作的紧迫感</strong></td>';
  html += '<td><code>suggestion</code> 必须具体到"做什么、怎么做、分几步"，给企业明确的可执行路径。同时体现时限压力——"你现在不处理，到时来不及"。</td>';
  html += '<td style="color:#dc2626;font-size:12px;">❌ "请提供相关合同、单据、凭证等业务佐证材料"<br>✅ "①为{must_total:,.0f}元主营业务交易的供应商补签购销合同（{len(mc_list)}家）；②{should_total:,.0f}元重要费用补签服务合同…"</td></tr>';

  html += '<tr><td style="font-weight:700;">5</td><td><strong>特定法律条款引用</strong></td>';
  html += '<td><code>policy_ref</code> 必须引用特定条款号+条款名称+摘要内容。禁止"依据相关法律规定""参照有关税收法规"等模糊引用。</td>';
  html += '<td style="color:#dc2626;font-size:12px;">❌ "依据相关税收法规"<br>✅ "《税收征收管理法》第三十五条（核定征收）+第五十四条（检查权）+第五十六条（资料提供义务）"</td></tr>';

  html += '<tr><td style="font-weight:700;">6</td><td><strong>证据明细表（items）</strong></td>';
  html += '<td>凡是涉及多项明细的发现，必须附 <code>items</code> 数组，每项含关键字段（名称、金额、后果等），前端渲染为可折叠明细表。</td>';
  html += '<td style="color:#dc2626;font-size:12px;">❌ 一句话带过<br>✅ items数组：[{缺失资料:"记账凭证", 缺失后果:"完整因果链…"}, …]</td></tr>';

  html += '<tr><td style="font-weight:700;">7</td><td><strong>方法在前，过程在后</strong></td>';
  html += '<td>每条稽查发现必须先声明使用了什么稽查方法（并列清单），再展示方法执行后的核查过程与结果。读者应先看到"我怎么查的"，再看到"我查到了什么"。方法必须是可复用的具体手段——工商登记核查法、进销存数据比对法、资金流发票流核对法、供应商客户穿透法、加工环节穿透法、五步核查法等。</td>';
  html += '<td style="color:#dc2626;font-size:12px;">❌ "需要按六种商业模式逐笔分析" — 没说方法<br>✅ "（一）稽查方法。第一，工商登记核查法…第二，进销存数据比对法…"</td></tr>';

  html += '<tr style="background:#fef2f2;"><td style="font-weight:700;">8</td><td><strong>反模板句</strong></td>';
  html += '<td>禁止出现"是税务稽查重点方向""需逐笔核实""请提供相关佐证材料""通过调取企业各税种申报表…""申报不合规是税务行政处罚的常见案由"等通用模板句。这些句子在所有发现中重复出现，除了增加字数外毫无信息量。</td>';
  html += '<td style="color:#dc2626;font-size:12px;">❌ "收款来源与开票客户严重不匹配是税务稽查重点方向"<br>✅ 删掉模板句，直接进入事实</td></tr>';

  html += '<tr style="background:#fef2f2;"><td style="font-weight:700;">9</td><td><strong>事实具体化</strong></td>';
  html += '<td>事实描述（detail/description）必须含具体数值——日期（年月日）、金额（元/万元）、数量（笔/张/家）、百分比等。禁止纯定性描述（"存在风险""可能有问题"），必须有量化的数据支撑。</td>';
  html += '<td style="color:#dc2626;font-size:12px;">❌ "经营场所银行付款未入账。经营场所银行付款未入账。" — 零事实<br>✅ "经查银行流水，2023年1月-12月期间向XX物业支付房租12笔共36万元，但序时账中无对应记录"</td></tr>';

  html += '<tr style="background:#fef2f2;"><td style="font-weight:700;">10</td><td><strong>防跨发现复制</strong></td>';
  html += '<td>同一份报告中，不同发现的<code>tax_impact</code>（税务影响）不能完全相同。每条发现的税务影响必须针对该发现的具体情形独立撰写——不能多条发现共用一个"被认定无实质经营→一般纳税人资格取消→已抵扣进项税额全部转出"。</td>';
  html += '<td style="color:#dc2626;font-size:12px;">❌ Findings 7/8/9 的tax_impact完全相同<br>✅ 每条发现的后果独立撰写</td></tr>';

  html += '<tr style="background:#fef2f2;"><td style="font-weight:700;">11</td><td><strong>空占位符检测</strong></td>';
  html += '<td><code>suggestion</code> 不能含空占位符如 <code>()</code> <code>()()</code> "已识别N条关联记录（如：）；" 等。占位符说明变量未注入——要么补数据，要么删掉整句。</td>';
  html += '<td style="color:#dc2626;font-size:12px;">❌ "已识别10条关联记录（如：()；()；()）"<br>✅ 补全变量或删除该句</td></tr>';

  html += '<tr style="background:#fef2f2;"><td style="font-weight:700;">12</td><td><strong>法律条款号</strong></td>';
  html += '<td><code>policy_ref</code> 必须含具体的"第X条"或"第X款"等条款号。禁止只写法律名称不加条款号（如"《企业所得税法实施条例》"后面什么都没写）。</td>';
  html += '<td style="color:#dc2626;font-size:12px;">❌ "《企业所得税法实施条例》"<br>✅ "《企业所得税法实施条例》第三十四条（工资薪金扣除）"</td></tr>';

  html += '</tbody></table>';

  html += '<div style="margin-top:12px;padding:10px 14px;background:#f0fdf4;border-radius:6px;font-size:13px;">';
  html += '<strong>🔧 系统实现：</strong>本系统在生成最终报告前，自动执行两轮质量保障——①<code>_sanitize_finding_boilerplate()</code> 剔除模板句/重复句/空描述 ②<code>_enforce_report_quality_standards()</code> 对全部发现做12项标准逐条检查——';
  html += '每份报告末尾附两轮质量检查统计。模板句先剔除再检查，确保进入报告的文本天然清洁。';
  html += '</div>';

  // 3.6 汇报四要素增强
  html += '<h3 style="margin-top:20px;">3.6 汇报四要素——真实场景必备</h3>';
  html += '<p style="font-size:13px;color:#6b7280;">以下四项是模拟真实稽查员向上级领导汇报时不可或缺的要素。系统在生成报告时自动注入。</p>';

  html += '<table class="table table-sm">';
  html += '<thead><tr><th style="width:120px;">要素</th><th>说明</th><th style="width:200px;">在报告中的位置</th></tr></thead><tbody>';
  html += '<tr><td style="font-weight:700;">① 处理优先级</td><td>真实汇报结尾必然有一句"领导，我建议优先处理以下最紧急的问题"。报告在结论末尾列出优先处理顺序——高风险立即处理、中风险限期整改、低风险持续关注——并标注每项的紧急理由。</td><td>标准报告：三、稽查结论 → 处理优先级建议<br>叙事报告：第四章结论末尾</td></tr>';
  html += '<tr><td style="font-weight:700;">② 交叉引用</td><td>真实报告中稽查员会说"如调查事项3所述，收款来源不匹配的问题与调查事项7的供应商地理异常是相互关联的"。每项发现底部自动标注与其共享同一域/线索链的关联发现。</td><td>标准报告：每项发现 → 关联发现行<br>叙事报告：同标准报告</td></tr>';
  html += '<tr><td style="font-weight:700;">③ 对比基准</td><td>只说有偏差不够，必须说偏差多少、跟什么比。如"开票收入1000万，同行业同规模企业在800-1200万之间——被查单位在此范围内，此项未见异常"。有基准才有说服力。</td><td>稽查管道 → 行业对标域分析<br>（系统已产出域分析发现）</td></tr>';
  html += '<tr><td style="font-weight:700;">④ 调查时间线</td><td>报告最缺时间叙事——"我收到案件→我调取资料→我发现第一个异常→我顺着线索扩大范围→我锁定核心问题"。叙事报告开篇以六阶段时间线表格呈现从受理到汇报的完整稽查轨迹。</td><td>叙事报告：第一章末尾 → 调查时间线表格</td></tr>';
  html += '</tbody></table>';

  html += '<div style="margin-top:12px;padding:10px 14px;background:#f0fdf4;border-radius:6px;font-size:13px;">';
  html += '<strong>🔧 系统实现：</strong>以上四要素在每次一键分析时自动注入——①优先级排序在结论输出阶段生成 ②交叉引用通过共享域/线索链自动匹配 ③对比基准来源于域分析中的行业对标数据 ④时间线在叙事报告第一章自动绘制。';
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
  
  // 处理决定文书规范
  html += '<h3 style="margin-top:20px;">4.3 稽查处理决定文书规范（《规程》第55-59条）</h3>';
  html += '<table class="table table-sm">';
  html += '<thead><tr><th style="width:180px;">文书类型</th><th style="width:100px;">条款</th><th>必须包含的核心内容</th></tr></thead><tbody>';
  html += '<tr><td>《税务处理决定书》</td><td>第55-56条</td><td>被查对象信息+检查范围和内容+税收违法事实及所属期间+<strong>税款金额、缴纳期限及地点</strong>+<strong>滞纳金计算方法</strong>+不履行责任+行政复议和诉讼途径</td></tr>';
  html += '<tr><td>《税务行政处罚决定书》</td><td>第55/57条</td><td>被查对象信息+检查范围和内容+税收违法事实及所属期间+<strong>行政处罚种类和依据</strong>+<strong>履行方式、期限和地点</strong>+不履行责任+行政复议和诉讼途径</td></tr>';
  html += '<tr><td>《不予税务行政处罚决定书》</td><td>第55/58条</td><td>被查对象信息+检查范围和内容+税收违法事实及所属期间+<strong>不予处罚的理由及依据</strong>+行政复议和诉讼途径</td></tr>';
  html += '<tr><td>《税务稽查结论》</td><td>第55/59条</td><td>被查对象信息+检查范围和内容+检查时间和所属期间+<strong>检查结论</strong></td></tr>';
  html += '<tr><td style="font-weight:700;color:#dc2626;">共同要求</td><td>第55条</td><td>所有文书引用的法律、行政法规、规章及其他规范性文件，<strong>应当注明文件全称、文号和有关条款</strong>——不得仅写"依据相关法律规定"等模糊表述。</td></tr>';
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

  // 进项发票分层匹配法
  html += '<div class="card" style="border-top:3px solid #dc2626;margin-bottom:16px;">';
  html += '<h3>5.2 进项发票三层分类法</h3>';
  html += '<p style="font-weight:600;">原理：真实企业经营中，不同类别的进项发票有不同的付款模式——不能把所有进项发票都用同一个"供应商名称必须匹配银行付款方"的标准来衡量。</p>';
  html += '<table class="table table-sm"><tbody>';
  html += '<tr><td style="white-space:nowrap;font-weight:600;">核心认知</td><td>做进项发票与银行付款匹配之前，必须先对发票按品名做分层分类。餐饮、住宿、汽油、差旅等日常费用是员工先垫付后凭发票报销——对公账户的付款对象是员工而非开票单位。如果不排除这些发票，"未匹配"统计会严重虚高，把正常的报销行为错误标记为异常。</td></tr>';
  html += '<tr><td style="font-weight:600;">第一层<br>主营业务成本</td><td>原料/材料/辅料/配件/加工费/设备/机器等——作为企业核心经营活动的采购支出。<strong>必须</strong>能通过银行付款匹配到供应商名称。未匹配→需逐笔核实是否属于六种付款模式之一（跨期/合并/分期/预付/应付/代付）。</td></tr>';
  html += '<tr><td style="font-weight:600;">第二层<br>重大费用</td><td>房租/咨询/广告/运输/维修/设计/软件/保险等——金额较大、一般有合同约定的费用支出。<strong>应当</strong>能通过银行付款匹配。未匹配→需提供合同+对账明细佐证。</td></tr>';
  html += '<tr><td style="font-weight:600;">第三层<br>日常费用报销</td><td>餐饮/住宿/汽油/差旅/办公/通讯/快递/过路费等——金额较小、员工垫付后凭发票报销。<strong>不参与</strong>供应商名称匹配。这些发票的付款对象是员工而非开票单位，"名称未匹配"属于商业正常现象。只需确保：①发票真实 ②与经营相关 ③非个人消费 ④有费用审批单。</td></tr>';
  html += '<tr><td style="font-weight:600;">分类方法</td><td>系统通过{20+}个日常报销关键词自动识别发票类别——基于发票"货物或应税劳务名称"字段判断。全行业通用，不依赖行业分类。</td></tr>';
  html += '<tr><td style="font-weight:600;">稽查影响</td><td>排除日常报销后重新评估"未匹配"风险——如果原来是42张/832,456元未匹配，排除餐饮住宿汽油后只剩5张/643,542元→风险画像从"大面积异常"变为"少数核心供应商需核实"。</td></tr>';
  html += '</tbody></table>';
  html += '</div>';

  // 三源比对
  html += '<div class="card" style="border-top:3px solid #f59e0b;margin-bottom:16px;">';
  html += '<h3>5.3 三源比对法</h3>';
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
  html += '<p style="font-weight:600;">原理：从交易特征反向验证商业合理性——发票数据本身的模式就能暴露问题。包括经营模式核查和地理空间分析两个维度。</p>';
  html += '<table class="table table-sm"><tbody>';
  html += '<tr><td style="white-space:nowrap;font-weight:600;">供应商地理</td><td>企业注册地在A省，主要供应商集中在千里之外的B省→运输成本合理性存疑→可能为开票公司</td></tr>';
  html += '<tr><td style="font-weight:600;">品名逻辑</td><td>生产企业采购大量与其经营范围无关的消费品（如服装厂采购电子产品/食品厂采购建材）→品名与主营业务不符→虚开发票嫌疑</td></tr>';
  html += '<tr><td style="font-weight:600;">外地加工费</td><td>企业位于A市，但加工费发票来自B市的外地加工商→为什么不找本地加工商？外地加工意味着额外运输成本和更长加工周期，商业上不合理。需核实：委托加工物资往返运输记录、加工费单价是否包含运费、加工地是否真实存在。</td></tr>';
  html += '<tr><td style="font-weight:600;">运输成本缺失</td><td>原料来自外地、成品销往外地、加工也在外地→必然产生大量运输费。但银行流水中完全没有运输费/物流费/快递费支出→货物流断裂→交易真实性存疑。重物（纺织原料/建材/金属等）的运输成本缺失尤其致命。</td></tr>';
  html += '<tr><td style="font-weight:600;">点面推理法</td><td>从单一异常点出发，横向扩展到全链条分析。如：加工费来自外地→检查供应商是否也在外地→检查客户是否也在外地→检查是否有运输成本→三地分离+零运输成本=全链条经营实质不可信。这是一个从"点"（单笔异常）推理到"面"（全链条存疑）的系统化方法。</td></tr>';
  html += '<tr><td style="font-weight:600;">金额规律</td><td>长期向某供应商采购，金额稳定在起征点以下→规避发票认证→拆分交易</td></tr>';
  html += '<tr><td style="font-weight:600;">时间规律</td><td>月末/季末集中开票→突击开票冲成本→收入成本配比异常</td></tr>';
  html += '<tr><td style="font-weight:600;">价格合理性</td><td>采购价格显著高于/低于市场均价→关联交易转移定价→特别纳税调整</td></tr>';
  html += '</tbody></table>';
  html += '</div>';
  html += '</div>';

  // 5.7 客户维度三源穿透法（老邓方法论）
  html += '<div class="card" style="border-top:3px solid #dc2626;margin-bottom:16px;">';
  html += '<h3>5.7 客户维度三源穿透法</h3>';
  html += '<p style="font-weight:600;">原理：收款与开票的总额偏差只是信号，逐客户匹配才是证据。这是资深稽查员的实战逻辑——不看总额看个体。</p>';
  html += '<table class="table table-sm"><tbody>';
  html += '<tr><td style="white-space:nowrap;font-weight:600;">核心逻辑</td><td>不以"总收款vs总开票"算偏差，而是穿透到每个客户维度——逐户匹配该客户的开票金额与银行收款金额。总额偏差可能因不同客户的多收少收相互抵消，逐户偏差才能暴露真实问题。</td></tr>';
  html += '<tr><td style="font-weight:600;">匹配方法</td><td>①提取所有销项发票的购方名称→按客户汇总开票金额 ②提取所有银行收款的付款方名称→按付款方汇总收款金额 ③逐对进行模糊匹配（前缀匹配+全文包含+去公司后缀）→计算每户偏差 ④偏差>30%且>5万元→触发稽查</td></tr>';
  html += '<tr><td style="font-weight:600;">五时点验证</td><td>对偏差客户，按五个时点逐项核实：<strong>合同签订→发货/交付→开票→收款→会计确认收入</strong>。时点错乱即问题——如已发货未开票→延迟确认收入；已收款未发货→预收账款是否正确核算。</td></tr>';
  html += '<tr><td style="font-weight:600;">收款>开票</td><td>客户付的钱多于开票金额→两种可能：①已交货未开票（隐匿收入）→需查合同条款+发货记录+预收账款科目 ②预收货款（开了票但客户预付部分款项）→需查合同付款节点是否匹配</td></tr>';
  html += '<tr><td style="font-weight:600;">开票>收款</td><td>开票金额多于客户付的钱→两种可能：①正常赊销（客户尚未付款）→需查应收账款账龄+客户工商状态 ②虚开发票（根本没有真实交易）→需查是否有真实货物交付+客户是否真实经营</td></tr>';
  html += '<tr><td style="font-weight:600;">零开票大额收款</td><td>付款方支付了大量款项（>10万元），但销项发票库中完全找不到该客户的开票记录→高度嫌疑为隐匿收入。需排查：付款方是否为企业？摘要是否含经营关键词？金额是否非整数？</td></tr>';
  html += '<tr><td style="font-weight:600;">付款方≠开票对象</td><td>发票开给A，但付款的是B→三流不合一→虚开嫌疑。稽查追问：B为什么替A付钱？是否有代付协议？若无→两套账嫌疑。</td></tr>';
  html += '<tr><td style="font-weight:600;">整数收款特征</td><td>真实交易收款通常有零有整。频繁出现整数收款（如恰好50万、100万）→可能是非经营性资金（借款/注资）或刻意安排的交易。</td></tr>';
  html += '<tr><td style="font-weight:600;">对应科目穿透</td><td>偏差客户还需调取：应收账款明细账（核查赊销真实性）、预收账款明细账（核查是否已发货未转收入）、客户明细账（核查完整往来记录）、销售合同（核查金额+付款节点+交货条款）。</td></tr>';
  html += '</tbody></table>';
  html += '</div>';
  html += '</div>';

  // ═══════════════════════════════════════
  // 第六部分：系统方法论与法定程序映射
  // ═══════════════════════════════════════
  html += '<div id="system-mapping" class="card" style="margin-bottom:20px;">';
  html += '<h2 style="border-left:4px solid #dc2626;padding-left:12px;">🔗 六、系统方法论与法定程序映射</h2>';
  html += '<p class="muted">以下展示本系统的五大核心引擎如何一一对应《税务稽查工作规程》的法定程序要求。系统不是替代稽查员，而是将法定程序固化为自动化引擎——确保每一步都有法可依、有据可查。</p>';

  // 映射总览表
  html += '<table class="table table-sm" style="margin-top:16px;">';
  html += '<thead><tr><th style="width:140px;">系统引擎</th><th style="width:180px;">法定程序对应</th><th style="width:140px;">《规程》条款</th><th>功能说明</th></tr></thead><tbody>';
  
  html += '<tr>';
  html += '<td style="font-weight:700;color:#2563eb;">📋 线索链引擎</td>';
  html += '<td>检查前准备 + 违法事实发现</td>';
  html += '<td>第21条（检查前准备）<br>第24条（收集证据）</td>';
  html += '<td>从上传的14类资料中自动扫描异常模式，生成初步线索。每条线索包含：触发条件（定量阈值/定性模式/缺失数据）、风险等级、调查步骤。相当于稽查员的"检查前查阅纳税档案+了解生产经营+确定检查方法"的自动化实现。<br><strong>当前规模：391条线索链，覆盖29个数据域。</strong></td>';
  html += '</tr>';
  
  html += '<tr>';
  html += '<td style="font-weight:700;color:#dc2626;">🔒 证据链引擎</td>';
  html += '<td>证据收集与固定 + 工作底稿</td>';
  html += '<td>第24条（证据真实性关联性）<br>第40条（稽查工作底稿）</td>';
  html += '<td>每条线索自动收集关联的规则ID和所属数据域，计算触发率——≥60%且≥3条规则+≥2个数据域同时触发→形成证据闭环。证据闭环强制升级为高风险。相当于将"工作底稿→归集证据→签字确认"固化为自动计算规则。<br><strong>当前规模：740条证据链+10条跨域证据链，234条证据闭环。</strong></td>';
  html += '</tr>';
  
  html += '<tr>';
  html += '<td style="font-weight:700;color:#10b981;">⚡ 分析链引擎</td>';
  html += '<td>审理逐项审核</td>';
  html += '<td>第47条（审理审核7项）<br>第54条（审理报告6项）</td>';
  html += '<td>逐条验证每条发现的"how_found→tax_impact→policy_ref"三要素——确保事实清楚（how_found说明发现过程）、证据充分（tax_impact引用具体数据）、适用法律正确（policy_ref逐条标注条款）。相当于审理人员"逐项审核7项内容"的系统化实现。<br><strong>当前覆盖：全29域分析+跨域关联推理。</strong></td>';
  html += '</tr>';
  
  html += '<tr>';
  html += '<td style="font-weight:700;color:#8b5cf6;">🎯 方法论过滤器</td>';
  html += '<td>退回补正（预筛选）</td>';
  html += '<td>第48条（退回补正5项）</td>';
  html += '<td>在生成最终报告前，自动剔除"不具备数据支撑"的噪声发现——对应审理部门退回补正的"事实不清、证据不足"标准。只有通过过滤器的发现才能进入最终报告。相当于在稽查报告生成前完成一轮预审理。<br><strong>过滤规则：CAP（强制保留标记）/ COND_BAN（禁止条件）/ DEDUP（同类去重）三层。</strong></td>';
  html += '</tr>';
  
  html += '<tr>';
  html += '<td style="font-weight:700;color:#06b6d4;">🛡️ 全链路质量体系</td>';
  html += '<td>案卷管理（立卷归档）</td>';
  html += '<td>第72-75条（案卷管理）</td>';
  html += '<td>确保从文件解析→域分析→线索生成→证据闭环→报告输出的全流程可追溯——每一份分析报告均可还原到具体的证据链、线索链和原始数据。相当于"一案一卷、目录清晰、资料齐全"的数字化实现。<br><strong>18组件覆盖5大层次：输入层→检查层→审理层→输出层→管理层。</strong></td>';
  html += '</tr>';
  html += '</tbody></table>';

  // 法定程序 vs 系统引擎对照流程图
  html += '<h3 style="margin-top:24px;">6.1 工作流程对照</h3>';
  html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">';
  
  html += '<div class="card" style="border:2px solid #2563eb;padding:16px;">';
  html += '<h4 style="color:#2563eb;margin:0 0 12px;">📜 法定稽查流程</h4>';
  html += '<div style="font-size:13px;line-height:2;">';
  html += '<div style="background:#eff6ff;padding:8px;border-radius:6px;margin-bottom:4px;">① 选案（第14-20条）→ 确定待查对象</div>';
  html += '<div style="text-align:center;color:#94a3b8;">↓</div>';
  html += '<div style="background:#fef3c7;padding:8px;border-radius:6px;margin-bottom:4px;">② 检查（第21-45条）→ 收集证据→制作工作底稿→撰写稽查报告</div>';
  html += '<div style="text-align:center;color:#94a3b8;">↓</div>';
  html += '<div style="background:#f0fdf4;padding:8px;border-radius:6px;margin-bottom:4px;">③ 审理（第46-60条）→ 逐项审核→退回补正或提出处理意见→作出处理决定</div>';
  html += '<div style="text-align:center;color:#94a3b8;">↓</div>';
  html += '<div style="background:#f5f3ff;padding:8px;border-radius:6px;margin-bottom:4px;">④ 执行（第61-71条）→ 送达文书→追缴税款→强制执行</div>';
  html += '<div style="text-align:center;color:#94a3b8;">↓</div>';
  html += '<div style="background:#fdf2f8;padding:8px;border-radius:6px;">⑤ 案卷管理（第72-77条）→ 立卷归档</div>';
  html += '</div>';
  html += '</div>';

  html += '<div class="card" style="border:2px solid #10b981;padding:16px;">';
  html += '<h4 style="color:#10b981;margin:0 0 12px;">⚙️ 系统自动化流程</h4>';
  html += '<div style="font-size:13px;line-height:2;">';
  html += '<div style="background:#eff6ff;padding:8px;border-radius:6px;margin-bottom:4px;">① 文件解析（域0）→ 提取结构化数据→识别14类资料</div>';
  html += '<div style="text-align:center;color:#94a3b8;">↓</div>';
  html += '<div style="background:#fef3c7;padding:8px;border-radius:6px;margin-bottom:4px;">② 域分析（域1-35）→ 线索链引擎扫描390+线索→证据链引擎归集740+证据</div>';
  html += '<div style="text-align:center;color:#94a3b8;">↓</div>';
  html += '<div style="background:#f0fdf4;padding:8px;border-radius:6px;margin-bottom:4px;">③ 方法论过滤器→分析链验证→跨域关联推理→证据闭环升级</div>';
  html += '<div style="text-align:center;color:#94a3b8;">↓</div>';
  html += '<div style="background:#f5f3ff;padding:8px;border-radius:6px;margin-bottom:4px;">④ 叙事增强层→生成第一人称稽查报告→P0/P1/P2建议分级</div>';
  html += '<div style="text-align:center;color:#94a3b8;">↓</div>';
  html += '<div style="background:#fdf2f8;padding:8px;border-radius:6px;">⑤ 全链路质量保障→18组件可追溯→一条发现可还原到原始数据</div>';
  html += '</div>';
  html += '</div>';
  html += '</div>';

  // 证据标准对照
  html += '<h3 style="margin-top:24px;">6.2 证据标准对照——法定要求 vs 系统实现</h3>';
  html += '<table class="table table-sm">';
  html += '<thead><tr><th style="width:170px;">法定证据标准（《规程》）</th><th style="width:180px;">条款</th><th>系统如何实现</th></tr></thead><tbody>';
  html += '<tr><td>证据材料应当<strong>真实</strong>，并与所证明的事项<strong>相关联</strong></td><td>第24条</td><td>证据链引擎要求≥2个独立数据域交叉验证才形成闭环——单源数据只是线索，不能是证据。确保证据的多源性和关联性。</td></tr>';
  html += '<tr><td>以电子数据的内容证明案件事实的，应打印纸质资料并注明"与电子数据核对无误"</td><td>第30条</td><td>文件解析模块保留原始文件名+解析时间戳，每条数据可追溯到原始文件的具体行列。分析报告中的每条发现均标注数据来源。</td></tr>';
  html += '<tr><td>检查人员应当制作《税务稽查工作底稿》，记录案件事实，归集相关证据材料</td><td>第40条</td><td>证据链引擎自动归集每条线索关联的所有规则ID→每条规则ID可追溯到tax_risk.py中的具体规则定义（规则编号+触发条件+风险等级+处罚依据）。</td></tr>';
  html += '<tr><td>稽查报告须包含：查明的违法事实及性质手段 + 税务处理处罚建议及依据</td><td>第42条</td><td>每项发现自动包含：how_found（发现过程=事实）+ tax_impact（税务影响=性质手段）+ policy_ref（法律依据）+ suggestion（处理建议）。四要素一一对应法定报告要求。</td></tr>';
  html += '<tr><td>审理须审核：事实是否清楚、证据是否充分、适用法律是否适当、程序是否合法</td><td>第47条</td><td>分析链引擎逐条验证三要素，方法论过滤器剔除不达标的发现——相当于自动化预审理。全链路质量体系确保全过程可追溯——相当于程序合法性审查。</td></tr>';
  html += '</tbody></table>';
  html += '</div>';

  // 底部声明
  html += '<div class="card" style="background:#f0fdf4;border:1px solid #bbf7d0;padding:16px;text-align:center;">';
  html += '<p style="margin:0;font-size:13px;color:#374151;">';
  html += '⚠️ <strong>声明：</strong>本手册内容基于《税务稽查工作规程》《税收征收管理法》及实战经验提炼，全行业适用。';
  html += '手册中的缺失后果因果链和法律后果描述均来自法律条文和稽查实践，供参考使用。具体案件的处理应结合实际情况。';
  html += '</p>';
  html += '</div>';

  container.innerHTML = html;

  // ═══ 异步加载管道数据：深度串联一键分析 ═══
  (function() {
    try {
      if (typeof getSharedAnalysis !== 'function') {
        document.getElementById('handbook-pipeline-status').innerHTML =
          '<div class="card" style="padding:12px 16px;background:#fef2f2;border:1px solid #fecaca;">' +
          '<span style="font-size:13px;color:#dc2626;">⚠ 稽查管道尚未加载，请先运行一键分析后刷新页面。</span>' +
          '</div>';
        return;
      }
      getSharedAnalysis().then(function(data) {
        var report = (data && data.report) ? data.report : {};
        var allF = report.all_findings || [];
        var pipelineLog = report.pipeline_log || [];
        var high = report.high_risk || 0;
        var mid = report.mid_risk || 0;
        var total = report.total_risks || allF.length;

        // ─── 1. 状态栏 ───
        var domainCount = 0;
        for (var i = 0; i < pipelineLog.length; i++) {
          if (pipelineLog[i].indexOf('域') > -1) domainCount++;
        }
        var statusHtml = '<div class="card" style="padding:12px 16px;background:#f0fdf4;border:1px solid #bbf7d0;">';
        statusHtml += '<div style="display:flex;align-items:center;flex-wrap:wrap;gap:16px;">';
        statusHtml += '<span style="font-size:14px;">🔗 <strong>已连接一键分析管道</strong></span>';
        statusHtml += '<span style="font-size:12px;color:#374151;">📊 ' + total + '条发现</span>';
        statusHtml += '<span style="font-size:12px;color:#dc2626;">🔴 高风险 ' + high + '</span>';
        statusHtml += '<span style="font-size:12px;color:#f59e0b;">🟡 中风险 ' + mid + '</span>';
        statusHtml += '<span style="font-size:12px;color:#6b7280;">📁 ' + domainCount + '个分析域</span>';
        statusHtml += '<a href="#" onclick="navigateTo(\'tax-doc-analysis\');return false" style="font-size:12px;color:#2563eb;margin-left:auto;">查看完整报告 →</a>';
        statusHtml += '</div></div>';
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
          var docCards = document.querySelectorAll('#documents .card[style*=\"border-left\"]');
          for (var dc = 0; dc < docCards.length; dc++) {
            var card = docCards[dc];
            var strongEl = card.querySelector('strong');
            if (strongEl) {
              var docName = strongEl.textContent.trim();
              if (missingNames[docName]) {
                // 未提交 → 标红
                var badge = document.createElement('span');
                badge.style.cssText = 'display:inline-block;margin-left:8px;padding:1px 8px;border-radius:3px;font-size:11px;background:#fee2e2;color:#dc2626;';
                badge.textContent = '❌ 未提交';
                strongEl.parentNode.insertBefore(badge, strongEl.nextSibling);
                card.style.borderLeftColor = '#dc2626';
                card.style.background = '#fef2f2';
              } else {
                // 已提交 → 标绿
                var badge2 = document.createElement('span');
                badge2.style.cssText = 'display:inline-block;margin-left:8px;padding:1px 8px;border-radius:3px;font-size:11px;background:#dcfce7;color:#16a34a;';
                badge2.textContent = '✅ 已提交';
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
          '<div class="card" style="padding:12px 16px;background:#fefce8;border:1px solid #fde68a;">' +
          '<span style="font-size:13px;color:#92400e;">📋 暂无分析数据 — <a href="#" onclick="navigateTo(\'tax-doc-analysis\');return false" style="color:#2563eb;">点击运行一键分析</a> 后将显示实时数据关联。</span>' +
          '</div>';
      });
    } catch(e) {
      document.getElementById('handbook-pipeline-status').innerHTML = '';
    }
  })();
}

// 辅助函数：滚动到指定区域
function scrollToSection(id) {
  var el = document.getElementById(id);
  if (el) {
    el.scrollIntoView({behavior: 'smooth', block: 'start'});
  }
}
