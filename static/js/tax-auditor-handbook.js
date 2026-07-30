/**
 * 税务合规员手册 - 14章详尽版
 */

function renderAuditorHandbook(container) {
  if (!container) return;
  window.currentModule = '税务合规员手册';

  var h = '';
  h += '<style>.hb-layout{display:flex;gap:28px;max-width:1100px;margin:0 auto;padding:24px 16px;background:#fff}.hb-toc{width:180px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:16px;font-size:12px;line-height:2.2;max-height:calc(100vh-40px);overflow-y:auto}.hb-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.hb-toc a{display:block;color:#475569;text-decoration:none;padding:3px 10px;border-radius:4px;cursor:pointer;font-size:12px}.hb-toc a:hover,.hb-toc a.active{background:#eff6ff;color:#2563eb;font-weight:600}.hb-main{flex:1;min-width:0;background:#fff}.hb-sec{margin-bottom:44px}.hb-sec-title{font-size:16px;font-weight:700;color:#0f172a;padding-bottom:10px;border-bottom:2px solid #e2e8f0;margin-bottom:16px;display:flex;align-items:center;gap:8px}.hb-sec-title .num{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;background:#1e293b;color:#fff;border-radius:4px;font-size:12px;flex-shrink:0}.hb-tbl{width:100%;border-collapse:collapse;font-size:13px;line-height:2}.hb-tbl td{padding:10px 14px;border-bottom:1px solid #f1f5f9;vertical-align:top}.hb-tbl .lbl{width:110px;color:#94a3b8;font-size:12px;font-weight:600;white-space:nowrap}.hb-tbl .val{color:#334155}.hb-card-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:16px 0}.hb-card{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:18px;font-size:12px;line-height:1.8}.hb-card strong{display:block;font-size:13px;color:#0f172a;margin-bottom:8px}.hb-card p{margin:0;color:#475569}.hb-stat{text-align:center;padding:14px 8px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px}.hb-detail{margin:8px 0 16px;padding:12px 16px;background:#f8fafc;border-radius:8px;font-size:13px;line-height:2.2;color:#475569}.hb-detail b{color:#0f172a}.hb-timeline{border-left:2px solid #e2e8f0;margin-left:8px;padding-left:20px}.hb-tl-dot{width:10px;height:10px;border-radius:50%;position:absolute;left:-26px;top:6px}.hb-law-tag{font-size:11px;color:#2563eb;background:#eff6ff;padding:2px 8px;border-radius:10px;font-weight:500;margin-left:6px}.hb-note{color:#94a3b8;font-size:11px;display:block;margin-top:2px}</style>';

  h += '<div class="hb-layout"><nav class="hb-toc"><div class="toc-title">📖 目录</div>';
  ['系统数据概览','税务合规工作流程','14类必查资料','税务合规方法论31720条','税务合规判定规则','报告编制规范','关键法律条文','系统与规程映射','全链路质量保障','跨域协商引擎','数据一致性自检','审核反馈闭环','引擎记忆体系','引擎铁律编号','系统文件关联'].forEach(function(t,i){
    var lbl = i===0?'':['一 ','二 ','三 ','四 ','五 ','六 ','七 ','八 ','九 ','十 ','十一 ','十二 ','十三 ','十四 '][i-1];
    h += '<a href="#hb-s'+i+'">'+lbl+t+'</a>';
  });
  h += '</nav><div class="hb-main">';
  h += '<h2 style="font-size:20px;font-weight:800;color:#0f172a;margin:0 0 4px">⚖️ 税务合规员手册</h2>';
  h += '<p style="font-size:13px;color:#94a3b8;margin:0 0 28px;line-height:2">14章完整税务合规知识体系。提炼自《税务合规工作规程》《税收征收管理法》及实战经验，全行业适用。每章含理论依据、操作方法和代码实现位置。</p>';

  // ═══ 第0章 ═══
  h += '<div id="hb-s0" class="hb-sec"><div class="hb-sec-title"><span class="num">0</span>系统数据概览</div>';
  h += '<div class="hb-detail">税务合规系统是存勤法税的智能化税务合规推理引擎。基于<b>{{rules_count}}条税务合规规则+{{clue_chains}}条线索链+{{evidence_chains}}条证据链+41720条分析链+{{domain_functions}}个域分析函数</b>构建，实现从原始资料上传到正式税务合规报告输出的全自动化处理。引擎具备六项核心智能能力——记忆、学习、思考、判断、决策、自知——每项能力均有可运行的代码实现，代码位置可追溯至具体文件和行号。</div>';
  h += '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:20px">';
  [{n:'1608',l:'税务合规规则',d:'29个分类，每条含触发条件+风险等级+调查步骤+处罚依据'},{n:'437',l:'线索链',d:'全部可执行，含触发关键词+rule_id+风险等级+建议+法条'},{n:'781',l:'证据链',d:'investigation_path多源交叉验证，≥2维独立数据源形成证据闭环'},{n:'48',l:'分析链',d:'reasoning_path多步推理，综合判定定案'},{n:'42',l:'域分析',d:'覆盖银行流水/进销存/费用/往来款/资产/税务/经营实质等13大类'},{n:'41',l:'引擎模块',d:'engine/*.py共41个模块，各模块独立加载，协同工作'}].forEach(function(s){
    h += '<div class="hb-stat" style="flex:1;min-width:110px"><div style="font-size:22px;font-weight:700;color:#0f172a">'+s.n+'</div><div style="font-size:11px;color:#94a3b8">'+s.l+'</div><div style="font-size:10px;color:#cbd5e1;margin-top:4px">'+s.d+'</div></div>';
  });
  h += '</div>';
  h += '<div class="hb-card-grid">';
  h += '<div class="hb-card"><strong>🧠 有记忆</strong><p>每次分析自动提取指纹（行业+模式+信号+评分）存入audit_memory.json。上限501720条，12维度加权相似度检索——行业(×3)>经营模式(×2)>信号类型(×2)>风险等级(×1.5)。后续分析自动检索相似案例，输出行业对标校准和常见信号预警。</p></div>';
  h += '<div class="hb-card"><strong>📚 能学习</strong><p>三层渐进学习：①审核反馈先进入私有候选池，限定账套和场景，重复验证并经显式同步批准后才可增加审核标记；②历史样本只用于校准和提出建议，不替代当前证据；③新模式先进入观察与复核流程，保留版本、冲突记录和回退能力。代码：self_learning.py。</p></div>';
  h += '<div class="hb-card"><strong>🔬 懂思考</strong><p>四层推理：假设验证引擎（每条发现2-3个竞争假设+逐条证据验证+加权判决）→Phase1-4推理引擎（初查信号检测→定向深挖→交叉验证→综合定性）→因果叙事链（多信号叠加自动推演因果链条）→四步税务合规分析法（detect→verify→diagnose→report）。</p></div>';
  h += '<div class="hb-card"><strong>⚖️ 会判断</strong><p>七层自动判定体系：四方交叉验证（文件名→列头→数据→公司匹配）→身份锚定（购买方/销售方vs公司名+统一社会信用代码）→发票方向判定→进项三层分类→服务行业闸门→品名级精准过滤→存疑排除。31720条判定规则逐条自动校验，每层独立运行。</p></div>';
  h += '<div class="hb-card"><strong>🎯 懂决策</strong><p>五层决策输出：风险综合评分（76/100→四级等级）→审计策略推荐（P0立即处理/P1限期整改/P2持续关注）→因果叙事链（从信号推演因果）→合规门禁（12项质量标准+16项自省检查）→正式报告（7章格式+六要素+同类合并+语音播报）。</p></div>';
  h += '<div class="hb-card"><strong>🔮 有自知</strong><p>引擎知道自己是财税税务合规系统的大脑。新规则/新方法/新标准写入engine/memory.py规则篇+架构篇（26章）。数据一致性自检（audit_consistency.py）启动时自动运行，四触发机制（--sync/start.bat/pre-commit/一键分析）确保全模块数据统一。自记忆、自学习、自思考、自判断、自决策——五项能力协同运转。</p></div>';
  h += '</div></div>';

  // ═══ 第一章 ═══
  h += '<div id="hb-s1" class="hb-sec"><div class="hb-sec-title"><span class="num">1</span>税务合规工作流程</div>';
  h += '<div class="hb-detail">税务合规分为选案→检查→审理→执行→案卷管理五个阶段，每个阶段有明确的法定时限、工作要求和法律依据。以下为《税务合规工作规程》（国税发[2009]157号）规定的标准化流程及本系统的对应实现方式。企业接到税务合规通知后通常只有<b>3-5天准备时间</b>，系统的价值在于把"被查前的手忙脚乱"变为"日常化的持续自检"。</div>';
  h += '<div class="hb-timeline">';
  [{title:'① 选案环节（第14-21720条）',body:'税务合规局通过计算机分析、人工分析、人机结合分析等多种渠道获取案源信息，经集体研究后合理准确地选择和确定税务合规对象。年度终了前制定下一年度税务合规工作计划，严格控制检查次数。<b>8类案源</b>包括：财务指标异常/上级交办/专项检查/部门移交/检举信息/其他部门转来/社会公共信息/其他。其中<b>检举</b>是企业的最大不可控风险——任何人可实名或匿名检举，且检举信息不公开。本系统的自动化风险扫描+一键分析功能本质上就是"计算机分析"环节——在税务合规立案前模拟案源筛选逻辑，帮助企业提前发现并修复涉税风险，降低进入选案名单的概率。',rows:[['案源获取','多渠道获取案源信息，集体研究，合理准确选择确定税务合规对象'],['税务合规计划','年度终了前制定下一年度工作计划，严格控制检查次数'],['8类案源','财务指标/上级交办/专项/部门移交/检举/其他部门转来/社会公共信息/其他'],['筛选方法','计算机分析、人工分析、人机结合分析——有嫌疑的确定为待查对象'],['立案检查','批准立案后制作《税务合规任务通知书》，连同资料移交检查部门']]},
  {title:'② 检查环节（第21-41720条）',body:'检查环节是税务合规的核心阶段。检查前需查阅纳税档案，了解生产经营、行业特点、财务会计制度，确定检查方法。检查时限为自实施之日起<strong>60日内</strong>完成，需<strong>两名以上</strong>检查人员共同实施。检查方法包括实地检查/调取账簿资料/询问/查询存款账户/异地协查。证据须真实、相关联，类型涵盖书证/物证/视听资料/电子数据/证人证言/当事人陈述/勘验笔录。必须制作《税务合规工作底稿》，记录案件事实、归集证据材料——<b>没有底稿就没有税务合规报告</b>。税务合规报告须含10项内容。检查完毕5个工作日内移交审理部门。本系统的一键分析管线完全模拟此环节——文件上传→实体识别→情报提取→规则扫描→链驱动发现→证据收集→形成底稿→输出报告。',rows:[['检查前准备','查阅纳税档案，了解生产经营、行业特点、财务会计制度，确定检查方法'],['检查时限','自实施之日起60日内完成，需两名以上检查人员共同实施'],['检查方法','实地检查/调取账簿资料/询问/查询存款账户/异地协查'],['证据类型','书证/物证/视听资料/电子数据/证人证言/当事人陈述/勘验笔录'],['税务合规底稿','必须制作，记录案件事实，归集证据材料——无底稿则无报告'],['税务合规报告','须含10项：案件来源→基本情况→检查时间→方法措施→违法事实→拒绝阻挠→被查对象意见→处理建议→其他→签名日期'],['移交审理','检查完毕5个工作日内移交审理部门']]},
  {title:'③ 审理环节（第46-1720条）',body:'审理部门收到税务合规报告后，逐项审核7项内容：对象准确性/事实清楚证据充分/法律适用/程序合法/权限适当/处理建议/其他事项。事实不清、证据不足的退回检查部门补充调查。事实清楚但适用法律错误的，审理部门另行提出处理意见直接纠正不退回。审理时限为收到报告后<strong>15日内</strong>提出审理意见。拟处罚的需送达告知书，告知陈述权/申辩权/听证权。审理结论分四种：有违法行为→《税务处理决定书》/应处罚→《税务行政处罚决定书》/轻微→《不予处罚决定书》/无违法→《税务合规结论》。涉嫌犯罪的移送公安机关。本系统的质量保障体系完全对应审理环节——方法论过滤器+报告纯净度规范+合规门禁=自动审理。',rows:[['审核重点','逐项审核7项：对象准确性/事实证据/法律适用/程序合法/权限适当/处理建议/其他'],['退回补正','事实不清、证据不足→退回检查部门补充调查'],['纠正建议','事实清楚但适用法律错误→审理部门直接纠正，不退回'],['审理时限','收到税务合规报告后15日内提出审理意见'],['告知听证','拟处罚→送达告知书→告知陈述权/申辩权/听证权'],['四种决定','有违法→处理决定书/应处罚→处罚决定书/轻微→不予处罚/无违法→税务合规结论'],['涉罪移送','涉嫌犯罪→移送书→经局长批准→移送公安机关']]},
  {title:'④ 执行环节',body:'下达《税务处理决定书》和《税务行政处罚决定书》，责令限期缴纳税款、滞纳金和罚款。企业权利：60日内申请行政复议/复议后15日内提起诉讼/缴纳税款或提供担保后可申请复议。逾期不履行的，加收每日万分之五滞纳金，实施税收保全措施（冻结存款/查封财产），并申请法院强制执行。本系统报告的第五章"处理处罚建议"直接对应执行环节——P0立即处理/P1限期整改/P2持续关注，三级策略让企业在税务合规正式下达前提前整改。',rows:[['执行文书','下达处理决定书+处罚决定书→责令限期缴纳'],['企业权利','60日内申请行政复议/复议后15日内提起诉讼'],['强制执行','逾期→每日万分之五滞纳金→税收保全→申请法院强制执行'],['法律依据','《征管法》第31720条(滞纳金)/第41720条(强制执行)/第81720条(复议前置)']]},
  {title:'⑤ 案卷管理（第72-71720条）',body:'一案一卷，按年度、按案卷分类立卷。过程资料全部纳入案卷，不得遗漏。正卷含税务合规报告/审理报告/处理决定/证据材料，可对外提供。副卷含内部请示/报告/研究记录，不得对外提供。保管期限随案卷定，直至最终审结。电子数据与纸质档案同步保管。本系统的全链路溯源体系对应案卷管理——每条发现的结论可追溯到规则ID→线索链ID→证据来源→原始数据行，形成完整的电子税务合规底稿。',rows:[['立卷标准','一案一卷，按年度、按案卷分类立卷，过程资料全部纳入'],['正卷副卷','正卷(可对外)含报告/决定/证据；副卷含内部请示/研究记录'],['保管期限','随案卷定，直至最终审结。电子数据与纸质档案同步保管']]}].forEach(function(s){
    h += '<div style="position:relative;margin-bottom:20px"><div class="hb-tl-dot"></div>';
    h += '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px 20px">';
    h += '<h3 style="font-size:14px;font-weight:700;color:#0f172a;margin:0 0 8px">'+s.title+'</h3>';
    h += '<div class="hb-detail">'+s.body+'</div>';
    if (s.rows) {h += '<table class="hb-tbl"><tbody>';s.rows.forEach(function(r){h+='<tr><td class="lbl">'+r[0]+'</td><td class="val">'+r[1]+'</td></tr>';});h += '</tbody></table>';}
    h += '</div></div>';
  });
  h += '</div></div>';

  // ═══ 第二章 ═══
  h += '<div id="hb-s2" class="hb-sec"><div class="hb-sec-title"><span class="num">2</span>14类税务合规必查资料</div>';
  h += '<div class="hb-detail">根据税务合规经验，以下14类资料为必查项。每缺一类资料，税务合规时就少一道防线——缺少资料意味着对应风险无法排除，税务机关将从其他数据源倒推核定应纳税额，核定结果通常高于企业实际申报。系统通过文件解析模块（{{file_fingerprints}}类文件指纹+三层递进识别）自动检测资料提交状态，逐类标注已提交/缺失，缺失资料的具体后果在报告中一一列明。以下按重要性从必备→建议→据需三级分类。</div>';
  h += '<table class="hb-tbl"><thead><tr style="border-bottom:2px solid #e2e8f0"><td class="lbl">资料</td><td class="lbl" style="width:50px">等级</td><td class="val">核心要求</td><td class="val" style="font-size:12px;color:#dc2626">缺失后果</td></tr></thead><tbody>';
  [['银行流水','必备','含交易日期/对方户名/交易金额/摘要/备注。系统自动提取收款方/付款方身份、计算资金净流向、识别异常交易模式。','资金流真实性无法验证，收入收款和成本付款无法核实。税务机关从第三方数据倒推资金流向。'],
   ['销项发票','必备','含购方名称/品名/规格/数量/金额/税额/发票号码。系统自动统计收入构成、行业分类、客户集中度。','无法确认企业对外开票情况，无法进行收入端分析。税务机关以行业均值推定收入。'],
   ['进项发票','必备','含销方名称/品名/数量/金额/税额。系统自动三层成本分类（主营/重大费用/日常报销）、供应商集中度分析。','无法确认采购成本和进项税额，无法进行成本端分析。进项税额的可抵扣性无法验证。'],
   ['工资表','必备','含姓名/身份证号/应发工资/社保扣款/公积金扣款/个税扣款/实发工资。与社保明细+个税申报三方交叉验证。','人工成本无法核实，个税和社保扣缴的合规性无法验证。可能面临补缴个税+罚款。'],
   ['社保明细','必备','含姓名/身份证号/缴费基数/单位缴纳额/个人缴纳额。与工资表交叉验证——人数、基数必须一致。','社保合规性无法验证，存在少缴漏缴风险。至少补缴差额+每日万分之五滞纳金。'],
   ['公积金明细','建议','含姓名/缴存基数/单位缴存额/个人缴存额。与社保同源验证，缴费基数须一致。','公积金合规性无法验证，不影响税务但影响企业信用评级。'],
   ['记账凭证','必备','含凭证编号/日期/摘要/科目编码/借方金额/贷方金额。用于科目级借贷平衡验证。','无法从账务层面验证收入/成本/费用的真实性，无法进行科目级借贷平衡检查。'],
   ['科目余额表','建议','提供各科目期末余额全景图。用于验证报表数据的连续性和一致性、关联方往来余额。','无法从会计科目维度进行全面分析，关联方往来余额无法确认。'],
   ['财务报表','建议','完整反映财务状况和经营成果，含资产负债表+利润表+现金流量表。','财务指标分析受限，行业对标缺少基准数据。无法计算偿债/营运/盈利/成长能力。'],
   ['增值税申报表','建议','含销售额/销项税额/进项税额/应纳税额。与销项/进项发票交叉比对申报数据。','无法验证申报数据与发票数据的匹配性。发票金额与申报金额的差异无法识别。'],
   ['企业所得税申报表','建议','收入/成本/费用/利润的申报核验。与财务报表数据交叉比对。','所得税申报合规性无法验证。成本费用的税前扣除合规性无法核查。'],
   ['合同/协议','建议','四流合一（合同/发票/资金/货物）的起始环节。印花税计税基础核查和交易真实性验证。','交易真实性缺少核心证据，大额交易的商业合理性存疑。印花税计税基础无据可查。'],
   ['关联方交易资料','建议','关联交易定价（转让定价）、关联方名录、关联业务往来报告表。','关联交易合规性无法验证。存在转移利润嫌疑但无法证实或排除。'],
   ['进出口/报关','据需','进出口企业提供报关单、收付汇核销单。仅进出口企业需要提供。','进出口业务合规性无法验证。关税/消费税/增值税的进出口环节风险无法排除。']].forEach(function(d){
    h+='<tr><td class="lbl" style="font-weight:600;color:#0f172a">'+d[0]+'</td><td class="lbl" style="color:'+(d[1]==='必备'?'#dc2626':'#94a3b8')+'">'+d[1]+'</td><td class="val" style="font-size:12px">'+d[2]+'</td><td class="val" style="font-size:12px;color:#dc2626">'+d[3]+'</td></tr>';
  });
  h += '</tbody></table></div>';

  // ═══ 第三章 — 从 methodology_items.json 统一加载 ═══
  h += '<div id="hb-s3" class="hb-sec"><div class="hb-sec-title"><span class="num">3</span>税务合规方法论31720条</div>';
  h += '<div class="hb-detail">每条方法论均来自审计准则和税务合规实战。方法本身全行业适用——仅数据不同，逻辑通用。31720条按处理阶段分为五层：<b>文件识别层</b>（①②）→<b>数据提取层</b>（③④⑤⑥）→<b>分析推理层</b>（⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔）→<b>结论输出层</b>（㉕㉖㉗㉘㉙）→<b>质量保障层</b>（㉚㉛㉜㉝）。<a href="/static/methodology_items.json" target="_blank" style="color:#2563eb;font-size:12px;margin-left:8px">📋 查看JSON源文件</a></div>';
  h += '<table class="hb-tbl"><thead><tr style="border-bottom:2px solid #e2e8f0"><td class="lbl" style="width:25px">#</td><td class="lbl" style="width:100px">名称</td><td class="val">详解</td></tr></thead><tbody id="hb-methods-body">';
  h += '<tr><td colspan="3" style="text-align:center;color:#94a3b8;padding:20px"><span class="spinner"></span> 加载方法论数据...</td></tr>';
  h += '</tbody></table></div>';
  
  // 异步加载方法论数据
  fetch('/static/methodology_items.json').then(function(r){return r.json()}).then(function(data){
    var tbody = document.getElementById('hb-methods-body');
    if (!tbody) return;
    var rows = '';
    data.forEach(function(m){
      rows += "<tr><td class=\"lbl\">"+m.id+"</td><td class=\"lbl\" style=\"color:#0f172a;font-weight:600\">"+m.name+"</td><td class=\"val\" style=\"font-size:12px;color:#059669\">"+m.desc+" | 代码："+m.code+"</td></tr>";
    });
    tbody.innerHTML = rows;
  }).catch(function(){
    var tbody = document.getElementById('hb-methods-body');
    if (tbody) tbody.innerHTML = '<tr><td colspan="3" style="color:#dc2626;text-align:center;padding:20px">加载失败，请刷新页面</td></tr>';
  });
  
  // ═══ 第四章 ═══
  h += '<div id="hb-s4" class="hb-sec"><div class="hb-sec-title"><span class="num">4</span>税务合规判定规则</div>';
  h += '<div class="hb-detail">以下1720条判定规则是系统分析的基础——每一条都在分析启动前完成判定，判定结论贯穿后续所有分析域。判定规则的执行顺序不可颠倒：身份锚定→发票方向→进项再分类→服务闸门→品名过滤→四方交叉→COND_BAN→证据闭环。如果第一步的身份锚定出错，后续所有判定都建立在错误基础上。</div>';
  h += '<table class="hb-tbl"><tbody id="hb-audit-rules-body"><tr><td colspan="2" style="text-align:center;color:#94a3b8;padding:20px"><span class="spinner"></span> 加载判定规则...</td></tr></tbody></table></div>';
  
  fetch('/static/audit_rules.json').then(function(r){return r.json()}).then(function(data){
    var tbody = document.getElementById('hb-audit-rules-body');
    if (!tbody) return;
    var rows = '';
    data.forEach(function(r){
      rows += '<tr><td class="lbl" style="font-weight:600;color:#0f172a;white-space:normal;width:130px">'+r.id+'.'+r.name+'</td><td class="val" style="font-size:12px">'+r.desc+'</td></tr>';
    });
    tbody.innerHTML = rows;
  }).catch(function(){
    var tbody = document.getElementById('hb-audit-rules-body');
    if (tbody) tbody.innerHTML = '<tr><td colspan="2" style="color:#dc2626;text-align:center;padding:20px">加载失败，请刷新</td></tr>';
  });

  // ═══ 第五章 ═══
  h += '<div id="hb-s5" class="hb-sec"><div class="hb-sec-title"><span class="num">5</span>报告编制规范</div>';
  h += '<div class="hb-detail">报告结构应由文种、权限和使用目的决定，不采用对所有场景一刀切的固定章数、字数、文号或处理时限。每条发现按统一编号连接事实、支持与反向证据、分析路径、法律核验、金额底稿和行动建议，并可反向定位到原始资料。<br><br><a href="javascript:window._reportSection=\'rpt-7\';navigateTo(\'report-standards\')" style="display:inline-block;padding:10px 20px;background:#2563eb;color:#fff;border-radius:6px;text-decoration:none;font-weight:600">📋 查看 报告编制要求 → 成稿结构、叙事与呈现</a></div>';
  h += '</div>';
  
// ═══ 第六章 ═══
  h += '<div id="hb-s6" class="hb-sec"><div class="hb-sec-title"><span class="num">6</span>关键法律条文</div>';
  h += '<div class="hb-detail">以下11720条法律条文为税务合规中最常引用的核心依据。税务合规报告的每项发现必须引用具体法条——笼统引用"相关税收法规"的表述在审理环节会被退回重写。条文的适用场景和处罚标准直接写入报告的法律依据字段，由法律推理引擎（legal_reasoner.py）自动匹配。</div>';
  h += '<table class="hb-tbl"><thead><tr style="border-bottom:2px solid #e2e8f0"><td class="lbl" style="width:120px">法条</td><td class="val">核心内容</td><td class="val" style="width:200px">适用场景与处罚标准</td></tr></thead><tbody id="hb-legal-body"><tr><td colspan="3" style="text-align:center;color:#94a3b8;padding:20px"><span class="spinner"></span> 加载法律条文...</td></tr></tbody></table></div>';
  
  fetch('/static/legal_refs.json').then(function(r){return r.json()}).then(function(data){
    var tbody = document.getElementById('hb-legal-body');
    if (!tbody) return;
    var rows = '';
    data.forEach(function(l){
      rows += '<tr><td class="lbl" style="font-weight:600;color:#0f172a">'+l.law+'</td><td class="val" style="font-size:12px">'+l.content+'</td><td class="val" style="font-size:12px;color:#64748b">'+l.scenario+'</td></tr>';
    });
    tbody.innerHTML = rows;
  }).catch(function(){
    var tbody = document.getElementById('hb-legal-body');
    if (tbody) tbody.innerHTML = '<tr><td colspan="3" style="color:#dc2626;text-align:center;padding:20px">加载失败，请刷新</td></tr>';
  });

  // ═══ 第七章 ═══
  h += '<div id="hb-s7" class="hb-sec"><div class="hb-sec-title"><span class="num">7</span>系统功能与税务合规规程映射</div>';
  h += '<div class="hb-detail">系统每一个功能模块都对应《税务合规工作规程》的具体条款要求。这确保了系统产出不是凭空制造的——每一项分析、每一条结论都有法定的规程依据。12个功能模块完整覆盖了从案源筛选到报告输出的全税务合规流程。</div>';
  h += '<table class="hb-tbl">';
  [['一键分析','第21-41720条(检查)','_run_analyze自动执行全部分析域+四步核查法+链驱动引擎+协商引擎+方法论语料对账。一次点击=完整模拟税务合规检查环节——从文件上传到报告输出，全部自动化。'],
   ['文件解析','第21720条(取证)','{{file_fingerprints}}类文件指纹+三层递进识别+四方交叉验证。82+列名映射自适应匹配。自动完成文件取证的数据准备——把格式各异的原始资料转化为结构化分析数据。'],
   ['线索链','第21720条(取证逻辑)','{{clue_chains}}条线索链(全部可执行),管理于cross_domain_clues.json。每条含触发关键词+investigation_path调查步骤+rule_refs关联规则ID+风险等级+建议+法条引用。每条线索链=一个税务合规员的调查思路——\"从这里开始查，每一步查什么，查到了怎么办\"。'],
   ['证据链','第21720条(证据真实性)','{{evidence_chains}}条证据链≥2域交叉→≥min_evidence触发→多维印证闭环。investigation_path数组从不同数据源收集支撑证据→满足最小证据数→证据闭环→结论的证明力达到可交付标准。'],
   ['分析链','第41720条(审理审核)','11720条分析链→reasoning_path[]多步推理→从证据→结论的综合判定。模拟审理部门的逐项审核——检查对象的准确性/事实证据的充分性/法律适用的正确性→0-7维异常评分→定案。'],
   ['方法论过滤器','第41720条(审核重点)','全链路质量保障体系→七类过滤规则依次执行→剔除证据不足的噪声→97%噪声过滤率。HARD_BAN 23类→COND_BAN 5类→税务合规重点保护12类→正常结论排除→资料缺口限流→行业不匹配过滤→去重合并。'],
   ['跨域协商引擎','第41720条(审核重点)','21720条协商规则四类场景：行业闸门消解(NEG-001~005)/资料驱动的跨域标记(NEG-010~040)/证据矛盾消解(NEG-020~030)/联合增强(NEG-AUG-001~003)。域间自动对话——确保报告不会出现自相矛盾的结论。'],
   ['风险评分','第41720条(审理意见)','综合评分(76/100)→四级风险等级→P0/P1/P2策略→因果叙事链→证据闭环→形成税务合规结论。完全对应审理环节的"审理意见"——对检查结果的综合判断和定性建议。'],
   ['报告生成','文种与制度要求','按风险分析、检查底稿、检查报告或法定执法文书的实际用途配置结构；统一保留范围、方法、发现、依据、金额、限制、复核、签批和附件索引，不把固定模板冒充普遍法定格式。'],
   ['合规门禁','第1720条(程序合法)','12项质量标准(模板句清除/重复句合并/空描述删除/人性化表述/六要素完整/法律引用准确/具体数值/因果链/可执行建议/条款号/反跨复制/空占位符清除)+16项自省检查。全通过→绿色交付。'],
   ['数据一致性自检','全文','audit_consistency.py启动前扫描全部JS/PY文件→对比system_config.json权威数据源→发现不一致→自动标记或一键修复(--sync)。从tax_risk_rules/audit_chains/domain_analysis实时统计权威值。四触发机制覆盖手动/启动/提交/分析。'],
   ['审核反馈闭环','受控学习要求','审核意见先形成限定账套和场景的候选规则，保留原始结论和修改记录；只有通过重复验证、冲突检查和人工批准后才可激活，且自动应用只增加审核标记，不覆盖原风险等级。']].forEach(function(m){h+='<tr><td class="lbl" style="font-weight:600;color:#0f172a">'+m[0]+'</td><td class="lbl" style="color:#2563eb;font-size:11px">'+m[1]+'</td><td class="val" style="font-size:12px">'+m[2]+'</td></tr>';});
  h += '</table></div>';

  // ═══ 第八章 ═══
  h += '<div id="hb-s8" class="hb-sec"><div class="hb-sec-title"><span class="num">8</span>全链路质量保障体系</div>';
  h += '<div class="hb-detail">6大维度25个组件覆盖从数据输入到报告输出的完整质量链。每个维度有明确的检查项、检查方法和代码位置。质量保障是递进式而非一次性——数据质量→规则质量→发现质量→证据质量→报告质量→合规性保障，前一层不合格直接影响后一层。代码位置：static/js/tax-pipeline-pages.js renderQualitySystem()。</div>';
  h += '<div class="hb-card-grid">';
  [['数据质量保障','文件解析前验证数据有效性/结构完整性/字段合法性。自动过滤空白行/汇总行/无效行。含82+列名映射和四方交叉验证，确保解析正确。文件格式识别失败→降级到数据推断兜底模式。'],
   ['规则质量保障','{{rules_count}}条规则全部经格式校验+触发条件校对+法律依据核实。规则ID可全程回溯至原始数据行。每条规则含9个结构化字段（触发条件/风险等级/调查步骤/处罚依据等）。规则变更时运行audit_consistency.py确保全局一致。'],
   ['发现质量保障','双重验证(COND_BAN防误杀：条件A+条件B同时满足才触发)+自洽检查(7项逻辑矛盾检测)+证据闭环验证(≥60%触发率+≥3规则+≥2域)。跨域协商引擎在发现之间执行对话消解——确保不同域的发现不矛盾。'],
   ['证据质量保障','≥2数据域交叉触发+≥1720条规则支持+≥60%触发率→有效证据链。11720条跨域证据链从不同数据源独立收集证据。SHA256哈希存证保证证据不可篡改。证据链完整度在报告中量化展示（X/Y条链形成闭环）。'],
   ['报告质量保障','12项质量标准：模板句清除/重复句合并/空描述删除/人性化表述/六要素完整/法律引用准确/具体数值/因果链/可执行建议/条款号/反跨复制/空占位符清除。报告纯净度规范在生成管线末端执行——系统内部标注全部移除，四步框架表现为自然段落衔接。'],
   ['合规性保障','合规门禁：178项自动检测+自动修复+质量标记。全通过→绿色交付。部分通过→黄色交付(标注未通过项及原因)。严重不通过→红色阻断(禁止交付，需人工介入修复)。门禁在报告生成后、用户查看前执行，确保用户看到的报告已经过质量审查。']].forEach(function(q){h+='<div class="hb-card"><strong>'+q[0]+'</strong><p>'+q[1]+'</p></div>';});
  h += '</div></div>';

  // ═══ 第九章 ═══
  h += '<div id="hb-s9" class="hb-sec"><div class="hb-sec-title"><span class="num">9</span>跨域协商引擎</div>';
  h += '<div class="hb-detail">{{domain_functions}}个域分析函数各自独立产出发现后，协商引擎自动执行跨域对话——一个域的结论影响其他域的判定。21720条协商规则覆盖四类场景，确保报告中的结论不自相矛盾。协商在all_findings生成后、进入过滤管线前执行。代码：engine/cross_domain_negotiation.py → run_negotiation()。协商结果在报告中以⛔消解/🔄调整/ℹ️标记/🔴增强四种横幅展示。</div>';
  h += '<table class="hb-tbl">';
  [['行业闸门消解（1720条）','NEG-001~005。服务行业判定成立→自动消解进销存/存货/BOM/进销比/毛利率五个制造业域的发现。例如：行业判定="服务行业"→域1的"进销存匹配异常"发现被自动标记为"不适用"，从高风险降为弱提示。','消除假阳性——服务行业不存在实物商品的进销存，这些域的发现没有分析意义。'],
   ['资料驱动标记（1720条）','NEG-010~040。资料完备度域检测到某类文件缺失→通知所有依赖该文件的域标注"资料受限"。例如：缺合同→合同分层判断法的"无正式合同"发现从高风险降为提示级并标注蓝色横幅"此结论基于不完整资料"。','防止因缺数据而产生的伪发现——没有合同≠交易不真实。'],
   ['证据矛盾消解（1720条）','NEG-020~030。域A的正面证据推翻域B的负面结论→自动消解域B的发现。例如：社保域"参保人数<工资人数"→人员分类域显示15人属于合法不参保（实习生/返聘/兼职）→消解"少缴社保"发现。','正面证据优先于基于间接信号推导的负面结论。'],
   ['联合增强（1720条）','NEG-AUG-001~003。多个域的异常信号同时触发→协商引擎合成更高级别的新发现。例如：资金流域"个人大额收款"+发票域"无对应销项发票"+工资域"收款人不在工资表中"→三域联合→合成"疑似系统性隐匿收入"增强发现。','降低漏报率——单域信号可能被忽略，多域叠加提升证明力。']].forEach(function(r){h+='<tr><td class="lbl" style="font-weight:600;color:#0f172a">'+r[0]+'</td><td class="val" style="font-size:12px">'+r[1]+'</td><td class="val" style="font-size:12px;color:#64748b">'+r[2]+'</td></tr>';});
  h += '</table></div>';

  // ═══ 第十章 ═══
  h += '<div id="hb-s10" class="hb-sec"><div class="hb-sec-title"><span class="num">10</span>数据一致性自检</div>';
  h += '<div class="hb-detail">引擎记忆（engine/memory.py）是系统的核心知识库，分为两层：<b>文档层</b>（26章规则+架构，存储在docstring中）+ <b>代码层</b>（Python函数：存储/检索/学习/纠正）。一键分析驱动数据层（audit_memory.json分析记忆 + user_corrections.json纠正规则），四触发机制确保文档层自动与代码层同步——任何时候启动系统，数据一致性自检自动运行。</div>';
  h += '<table class="hb-tbl">';
  h += '<tr><td class="lbl">代码位置</td><td class="val" style="font-size:12px">audit_consistency.py（扫描引擎+同步引擎）+ system_config.json（权威数据源）+ engine/system_config.py（Python端配置）</td></tr>';
  h += '<tr><td class="lbl">权威数据源</td><td class="val" style="font-size:12px">从原始数据文件实时统计生成：tax_risk_rules_local_export.json→规则数 / cross_domain_clues.json→线索链数 / cross_domain_evidence.json→证据链数 / cross_domain_analysis.json→分析链数。每次--calibrate重新统计。</td></tr>';
  h += '<tr><td class="lbl">扫描范围</td><td class="val" style="font-size:12px">所有JS文件（static/js/*.js）+ 所有PY文件（engine/*.py + *.py）。扫描硬编码数字与权威数据对比，跳过system_config/getConfig等动态获取行。</td></tr>';
  h += '<tr><td class="lbl">四触发机制</td><td class="val" style="font-size:12px">①手动：python audit_consistency.py --sync ②start.bat启动：先--sync再审计验证 ③git commit：.git/hooks/pre-commit自动--sync ④一键分析：pipeline.py启动时subprocess调用--sync。任一入口触发→全项目扫描→修正→报告。</td></tr>';
  h += '<tr><td class="lbl">同步范围</td><td class="val" style="font-size:12px">代码层：硬编码数字 vs 权威数据，逐行替换。文档层：engine/memory.py docstring中的规则数/链数/方法论数/域函数数/权威数据区块，正则匹配更新。</td></tr>';
  h += '<tr><td class="lbl">三种命令</td><td class="val" style="font-size:12px">python audit_consistency.py（纯审计，只报告） / --sync（联动同步，自动修复代码+文档） / --calibrate（重新统计权威数据源）</td></tr>';
  h += '</table></div>';

  // ═══ 第十一章 ═══
  h += '<div id="hb-s11" class="hb-sec"><div class="hb-sec-title"><span class="num">11</span>审核反馈与自学习闭环</div>';
  h += '<div class="hb-detail">报告中每条发现均可提交结构化审核意见。审核须记录处置状态、具体缺陷、正确逻辑、待补证据、依据或金额口径以及修改责任链。反馈先作为候选规则保存，限定适用账套和场景；未经验证和批准，不得直接跨企业或跨期间套用。</div>';
  h += '<table class="hb-tbl">';
  [['审核入口','报告中每条发现右侧的"🔍审核"按钮。提交内容应定位到发现编号和具体字段，并说明正确逻辑、待补证据、依据或测算口径。'],
   ['记录结构','处置状态（通过/修改后通过/退回/待补证/不适用）+具体缺陷+正确逻辑+待补证据+依据与口径+修改责任链。完整要求已经融入报告编制要求单页。'],
   ['存储与隔离','反馈写入私有纠正规则库，按账套、发现类型、行业和经营模式限定范围；原始结论、反馈文本、修改人、时间和版本并存。'],
   ['激活门槛','单次反馈只形成候选。至少经过重复验证、冲突检查和人工同步批准后才可激活；不同主体、期间或业务模式不得仅凭名称相似自动扩张。'],
   ['生效方式','已批准规则只给匹配发现增加审核标记和建议，不删除原始事实，不覆盖风险等级，也不替代法律、金额和终审人员的判断。'],
   ['查看入口','智能引擎中枢→纠正规则中转站。可查看适用范围、累计验证、置信度、激活状态和最近理由，并按权限停用或回退。']].forEach(function(r){h+='<tr><td class="lbl" style="font-weight:600;color:#0f172a">'+r[0]+'</td><td class="val" style="font-size:12px">'+r[1]+'</td></tr>';});
  h += '</table></div>';

  // ═══ 第12-14章 ═══
  h += '<div id="hb-s12" class="hb-sec"><div class="hb-sec-title"><span class="num">12</span>引擎记忆体系</div>';
  h += '<div class="hb-detail">引擎记忆（engine/memory.py）是系统的核心知识库，<b>文档层26章</b>（规则篇9章+架构篇16章+索引1章）记录系统"应该是怎样的"——规则、架构、方法论。<b>代码层</b>（7个Python函数）负责"做"——save_analysis_memory()保存分析指纹/query_similar_cases()检索历史/add_correction_rules()加载纠正规则。两者配合：文档层指导代码层的设计，代码层验证文档层的正确性。四触发机制确保任何时候两者保持同步。</div>';
  h += '<table class="hb-tbl">';
  h += '<tr><td class="lbl">规则篇9章</td><td class="val" style="font-size:12px">行业推断铁律/系统税务合规判定规则31720条/缺失的关键信息处理/收款分类规则11720条/账务处理引擎铁律1720条/引擎核心铁律1720条/报告呈现规则/报告后四章规则/审核反馈闭环规则</td></tr>';
  h += '<tr><td class="lbl">架构篇16章</td><td class="val" style="font-size:12px">假设验证推理引擎/跨域协商引擎/审核反馈闭环/联动修改与数据一致性/方法论过滤器体系/模块联动关系矩阵/四阶段推理管线/调度中枢/知识库系统/法律推理引擎/财务分析引擎/文件解析引擎/账套隔离机制/登录与会话管理/推理引擎仪表盘/前端页面体系</td></tr>';
  h += '<tr><td class="lbl">代码层7函数</td><td class="val" style="font-size:12px">save_analysis_memory()保存分析指纹 / query_similar_cases()检索历史参考 / record_correction()记录账套与场景候选反馈 / apply_correction_rules()应用已批准的精确范围标记 / record_user_feedback()记录用户意见 / _adjust_signal_weights_from_feedback()提出权重调整 / get_adaptive_signal_weights()读取受控权重</td></tr>';
  h += '<tr><td class="lbl">关联清单</td><td class="val" style="font-size:12px">引擎记忆末尾的系统文件关联清单列出30+核心文件的路径、用途和关系。每次--sync自动更新清单中的数字和文件引用。</td></tr>';
  h += '</table></div>';

  h += '<div id="hb-s13" class="hb-sec"><div class="hb-sec-title"><span class="num">13</span>引擎铁律编号体系</div>';
  h += '<div class="hb-detail">2026-06-29重新划清边界：引擎铁律（engine/memory.py规则篇）= 系统硬逻辑，不可违反，每条在代码中有对应的实现或检测机制。AI行为准则（前端AI行为准则页面）= 智哥编码规范，约束写代码的行为方式和质量流程。共11720条引擎铁律 + 1720条AI准则，编号互不重叠，各自独立维护。</div>';
  h += '<table class="hb-tbl">';
  h += '<tr><td class="lbl" colspan="2" style="font-weight:700;color:#dc2626;text-align:center">引擎铁律（engine/memory.py 规则篇 · 11720条 · 系统硬逻辑）</td></tr>';
  h += '<tr><td class="lbl">铁律一~六（账务处理）</td><td class="val" style="font-size:12px">铁律一：科目name——写入前查DB以实际值为准 / 铁律二：三号合并——禁止逐条for调用，必须批量分组 / 铁律三：审计铁律——python audit.py 1，7项全过才提交 / 铁律四：ref_id去重——精确匹配，禁止金额模糊匹配 / 铁律五：普票税额并入成本——普票不拆税额 / 铁律六：7分类禁止兜底——不在7分类返回None跳过</td></tr>';
  h += '<tr><td class="lbl">铁律七~十一（核心规范）</td><td class="val" style="font-size:12px">铁律七：规则=代码——记忆与实现必须一致 / 铁律八：代码即承诺——声称的功能必须代码存在 / 铁律九：全行业适用——禁止行业特化硬编码 / 铁律十：主动关联更新——一处过时全项目同步 / 铁律十一：方法论先行——功能必须先有方法论定义</td></tr>';
  h += '<tr><td class="lbl" colspan="2" style="font-weight:700;color:#2563eb;text-align:center">AI行为准则（前端页面 · 1720条 · 智哥编码规范）</td></tr>';
  h += '<tr><td class="lbl">#1-3 行事风格</td><td class="val" style="font-size:12px">#1做事要狠（改就改彻底）/ #2自作主张（技术决策直接做）/ #3主动进攻（同类问题全揪出）</td></tr>';
  h += '<tr><td class="lbl">#4/8/15/16 质量保障</td><td class="val" style="font-size:12px">#4自行验证（重启+预览确认）/ #8变更影响分析（grep引用逐条验证）/ #15提交前自查（铁律checklist逐条检查）/ #16交付前输出自检（文本逐句读一遍）</td></tr>';
  h += '<tr><td class="lbl" style="font-weight:700;color:#0ea5e9">查找</td><td class="val" style="font-size:12px">引擎铁律→engine/memory.py（规则篇第6-7章）| AI准则→侧边栏"AI行为准则"页面 | 完整编号对照表→engine/memory.py末尾规则编号对照表</td></tr>';
  h += '</table></div>';

  h += '<div id="hb-s14" class="hb-sec"><div class="hb-sec-title"><span class="num">14</span>系统文件关联清单</div>';
  h += '<div class="hb-detail">核心文件共30+个，按职责分为四组。此清单同时记录在engine/memory.py末尾的"系统文件关联清单"章节中，每次--sync自动更新其中的数字和文件引用。清单帮助快速定位任何功能的代码位置。</div>';
  h += '<table class="hb-tbl">';
  h += '<tr><td class="lbl" colspan="2" style="font-weight:700;text-align:center">核心引擎（12个文件）</td></tr>';
  h += '<tr><td class="lbl">engine/</td><td class="val" style="font-size:12px">pipeline.py（主分析管线·25000行）/ domain_analysis.py（36域函数·70000行） / phase1_triage.py（初查）/ phase2_deep_dive.py（深挖）/ phase3_cross_validate.py（交叉验证）/ phase4_synthesis.py（综合定性）/ cross_domain_negotiation.py（21720条协商规则）/ self_learning.py（审核反馈）/ hypothesis_engine.py（假设验证）/ orchestrator.py（调度中枢）/ knowledge_base.py（知识库）/ legal_reasoner.py（法律推理）</td></tr>';
  h += '<tr><td class="lbl" colspan="2" style="font-weight:700;text-align:center">数据与配置（8个文件）</td></tr>';
  h += '<tr><td class="lbl">static/ + 根目录</td><td class="val" style="font-size:12px">system_config.json（权威数据源）/ audit_chains.json（线索链+证据链+方法论·7MB）/ user_corrections.json（纠正规则）/ industry_data.json（25行业词典+11720条收款分类）/ tax_risk_rules_local_export.json（{{rules_count}}条税务合规指令·2MB）/ audit_memory.json（501720条分析记忆）/ sessions.json（会话持久化）/ database.py（SQLite数据库定义）</td></tr>';
  h += '<tr><td class="lbl" colspan="2" style="font-weight:700;text-align:center">前端页面（9个JS文件）</td></tr>';
  h += '<tr><td class="lbl">static/js/</td><td class="val" style="font-size:12px">tax-pipeline-pages.js（方法论与管线页面）/ tax-doc-analysis.js（资料风险分析报告）/ tax-auditor-handbook.js（岗位手册）/ tax-report-standards.js（编制、审核、误判复核与交付融合单页）/ tax-engine-dashboard.js（推理引擎仪表盘）/ core.js（全局路由）/ report-block-renderer.js（报告发现与审核入口）/ tax-risk-rules.js（税务合规指令浏览）</td></tr>';
  h += '<tr><td class="lbl" colspan="2" style="font-weight:700;text-align:center">基础设施（4个文件）</td></tr>';
  h += '<tr><td class="lbl">根目录</td><td class="val" style="font-size:12px">main.py（主入口·25000行·227路由·FastAPI服务器）/ start.bat（启动脚本·杀僵尸+清缓存+--sync+审计+启动）/ audit_consistency.py（数据一致性自检+联动修改+引擎记忆文档同步）/ static/index.html（侧边栏导航+全部JS加载）</td></tr>';
  h += '</table></div>';

  h += '</div></div>';
  container.innerHTML = (typeof applySysStats === 'function' && window._systemConfig) ? applySysStats(h, window._systemConfig) : h;
  // 侧边栏子模块入口：隐藏TOC和无关章节
  if (window._hbChapter) {
    var chapter = window._hbChapter;
    window._hbChapter = null;
    // 直接注入CSS隐藏TOC
    var style = document.createElement('style');
    style.textContent = '.hb-toc{display:none!important}.hb-layout{display:block!important}';
    container.appendChild(style);
    // 隐藏页面标题
    var h2 = container.querySelector('.hb-main h2');
    if (h2) h2.style.display = 'none';
    var p = container.querySelector('.hb-main > p');
    if (p) p.style.display = 'none';
    // 只显示目标章节
    var allSecs = container.querySelectorAll('.hb-sec');
    for (var i = 0; i < allSecs.length; i++) {
      allSecs[i].style.display = allSecs[i].id === chapter ? 'block' : 'none';
    }
    setTimeout(function() {
      var el = container.querySelector('#' + chapter);
      if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
    }, 100);
  }
}
