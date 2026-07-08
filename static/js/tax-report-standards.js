// ==================== 报告编制要求 — 详尽版 ====================

function renderReportStandards(container) {
  if (!container) return;
  window.currentModule = '报告编制要求';

  var S12 = [
    { id:1, name:'客观第三人称叙事', severity:'高',
      requirement:'how_found/description使用"经查""该企业""被查单位"等客观第三人称表述。不得出现第一人称"我"或第二人称"你"。',
      check:'检测文本中是否含"我""你"，是否含"经查""该企业"等客观标识。',
      example:'经查，该企业2024年1-12月期间共取得进项发票158张，合计金额12,456,789元，其中存在数量偏差的发票32张。' },
    { id:2, name:'事实-证据-后果三要素', severity:'高',
      requirement:'每条发现必须同时包含：①具体事实（含数值）②证据来源（规则/线索/文件）③后果推导（→导致XX）。缺一不可。',
      check:'tax_impact长度>20且含"→"因果连接词；how_found长度>20；tax_impact长度>30。',
      example:'进项发票与银行付款金额偏差520,000元→对应的进项税额67,600元可能存在虚抵→少缴增值税67,600元。' },
    { id:3, name:'完整因果链(A→B→C→D)', severity:'中',
      requirement:'tax_impact中至少含一个"→"，完整呈现从异常现象到税务后果的推导过程。',
      check:'检测tax_impact中"→"数量≥1，且总长度≥40字符。',
      example:'毛利率仅2%（大幅低于行业下限15%）→售价低于成本的商业合理性存疑→可能隐匿未开票收入→少缴企业所得税。' },
    { id:4, name:'可操作的紧迫感', severity:'高',
      requirement:'suggestion必须具体到可执行步骤，禁止"请提供相关资料""请核实相关情况"等笼统表述。',
      check:'suggestion长度≥30，不含"请提供相关""请配合""请核实相关""请按要求"等套话模板。',
      example:'逐户在天眼查/企查查核实前3大供应商的工商状态（存续/注销/吊销）；比对注册地址是否为住宅/虚拟地址。' },
    { id:5, name:'特定法律条款引用', severity:'高',
      requirement:'policy_ref必须引用具体法律条款（含"第X条"或"第X款"），不得使用兜底模板文本。',
      check:'检测是否含兜底模板文本；若含则自动清除。',
      example:'《税收征收管理法》第三十五条第一款第（四）项' },
    { id:6, name:'证据明细表', severity:'中',
      requirement:'涉及多项实体的发现（如多家供应商/多个商品/多笔交易）必须附带items数组，列出具体名称、金额、发票号。',
      check:'检测detail中是否含"家""个客户""笔""张发票"等关键词，若含但无items则标记。',
      example:'items: [{供应商:"XX公司",金额:500000,货物:"棉纱",发票号:"4401230001"}]' },
    { id:7, name:'方法在前→过程在后', severity:'低',
      requirement:'detail/how_found应先声明税务合规方法（如"采用银行流水与发票逐票核对法"），再展示具体发现结果。',
      check:'检测detail长度>80且是否含"税务合规方法""核查法""比对法""穿透法"等关键词。',
      example:'采用银行流水与销项发票逐户核对法。核对步骤：①提取全部收款对方名称→②与销项发票购买方名称交叉比对→③发现X个收款对方未出现在销项购买方中。' },
    { id:8, name:'反模板句', severity:'高',
      requirement:'禁止出现："是税务合规重点方向""需逐笔核实""请核实并提供相关佐证材料""申报不合规是税务行政处罚的常见案由"等。',
      check:'_sanitize_finding_boilerplate自动清除：①模板开头detail ②连续重复句 ③空占位描述。',
      example:'（此项为自动清除规则，正确范例为不含模板句的正常税务合规表述）' },
    { id:9, name:'事实具体化', severity:'高',
      requirement:'detail/description必须含具体数值——日期（如2024年1月）、金额（如150,000元）、数量（如共32笔）、百分比（如占比68%）。',
      check:'正则匹配：数字+单位(\u005cd[⑀d,.]*万?元?)、日期格式、数量词(共\u005cd+[条张笔家个])。',
      example:'2024年1-12月期间，共取得进项发票158张，合计金额12,456,789元，其中存在数量偏差的发票32张，偏差金额合计890,000元。' },
    { id:10, name:'防跨发现复制', severity:'中',
      requirement:'同一批分析中，不同发现的tax_impact不得完全相同（疑似复制粘贴）。',
      check:'收集所有tax_impact（长度>20的），检测是否有≥2条完全相同的impact文本。',
      example:'（每条发现的税务影响分析应基于该条的具体事实独立撰写）' },
    { id:11, name:'空占位符检测', severity:'中',
      requirement:'suggestion不得含空占位符如"()""如：()；()；()"等自动填充失效的残留文本。',
      check:'检测suggestion中是否含空占位符模式，_sanitize_finding_boilerplate自动清除。',
      example:'错误：已识别5条关联记录（如：()；()；()）/ 正确：已识别5笔异常交易，涉及3家供应商。' },
    { id:12, name:'法律条款号', severity:'高',
      requirement:'policy_ref必须含"第X条"或"第X款"等具体条款号，不能笼统引用"相关税收法规"。',
      check:'正则匹配"第[一二三四五六七八九十⑀d]+条"或"第[一二三四五六七八九十⑀d]+款"。',
      example:'《中华人民共和国增值税法》第九条 / 《发票管理办法》第二十二条' },
  ];

  var h = '<style>.rs-layout{display:flex;gap:28px;max-width:1100px;margin:0 auto;padding:24px 16px;background:#fff}.rs-toc{width:180px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:12px;line-height:2.2;max-height:calc(100vh-40px);overflow-y:auto}.rs-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.rs-toc a{display:block;color:#475569;text-decoration:none;padding:3px 10px;border-radius:4px;cursor:pointer;font-size:12px}.rs-toc a:hover,.rs-toc a.active{background:#eff6ff;color:#2563eb;font-weight:600}.rs-main{flex:1;min-width:0;background:#fff}.rs-sec{margin-bottom:44px}.rs-sec-title{font-size:16px;font-weight:700;color:#0f172a;padding-bottom:10px;border-bottom:2px solid #e2e8f0;margin-bottom:16px;display:flex;align-items:center;gap:8px}.rs-sec-title .n{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;background:#1e293b;color:#fff;border-radius:4px;font-size:12px;flex-shrink:0}.rs-card{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:18px 22px;margin-bottom:12px}.rs-card-title{font-size:14px;font-weight:700;color:#0f172a;margin-bottom:10px}.rs-tbl{width:100%;border-collapse:collapse;font-size:13px;line-height:1.8}.rs-tbl td{padding:10px 14px;border-bottom:1px solid #f1f5f9;vertical-align:top}.rs-tbl .lbl{color:#94a3b8;font-size:12px;font-weight:600;white-space:nowrap}.rs-tbl .val{color:#334155}.rs-stat{text-align:center;padding:14px 8px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px}.rs-example{margin:8px 0;padding:10px 14px;background:#f8fafc;border-left:3px solid #6366f1;font-size:12px;color:#334155;border-radius:0 4px 4px 0;line-height:1.8}.rs-badge-r{display:inline-block;padding:1px 8px;background:#fee2e2;color:#dc2626;border-radius:3px;font-size:10px;font-weight:600}.rs-badge-a{display:inline-block;padding:1px 8px;background:#fef3c7;color:#d97706;border-radius:3px;font-size:10px;font-weight:600}.rs-badge-g{display:inline-block;padding:1px 8px;background:#dcfce7;color:#059669;border-radius:3px;font-size:10px;font-weight:600}.rs-detail{margin:8px 0 16px;padding:12px 16px;background:#f8fafc;border-radius:6px;font-size:12px;line-height:2;color:#475569}</style>';

  h += '<div class="rs-layout">';

  // TOC
  h += '<nav class="rs-toc"><div class="toc-title">📖 目录</div>';
  h += '<a href="#rs-pipeline">1 质量保障管线</a>';
  h += '<a href="#rs-structure">2 报告7章结构</a>';
  h += '<a href="#rs-terms">3 术语与机密规范</a>';
  h += '<a href="#rs-narrative">4 税务合规叙事规范</a>';
  h += '<a href="#rs-merge">5 同类风险合并</a>';
  h += '<a href="#rs-12std">6 12项质量标准</a>';
  h += '<a href="#rs-reliability">7 判定可靠性要求</a>';
  h += '<a href="#rs-paragraph">8 段落格式规范</a>';
  h += '<a href="#rs-tts">9 语音播报标准</a>';
  h += '<a href="#rs-negotiation">10 跨域协商标记</a>';
  h += '<a href="#rs-review">11 审核反馈呈现</a>';
  h += '<a href="#rs-ironlaw">12 铁律质量映射</a>';
  h += '<a href="#rs-sync">13 同步交付机制</a>';
  h += '<a href="#rs-iterate">14 审核迭代闭环</a>';
  h += '<a href="#rs-negoflow">15 协商工作流程</a>';
  h += '</nav>';

  h += '<div class="rs-main">';
  h += '<h2 style="font-size:20px;font-weight:800;color:#0f172a;margin:0 0 4px">📐 报告编制标准（详尽版）</h2>';
  h += '<p style="font-size:13px;color:#94a3b8;margin:0 0 28px">根据《税务合规工作规程》及税务合规实务标准编制。系统内置12项硬性质量检查指标，质量保障管线自动执行，跨域协商和审核反馈的结果按规范展示。</p>';

  // 统计卡片
  var hi=S12.filter(function(s){return s.severity==='高';}).length;
  var mi=S12.filter(function(s){return s.severity==='中';}).length;
  var lo=S12.filter(function(s){return s.severity==='低';}).length;
  h += '<div style="display:flex;gap:10px;margin-bottom:28px">';
  h += '<div class="rs-stat" style="flex:1"><div style="font-size:22px;font-weight:700;color:#dc2626">'+hi+'</div><div style="font-size:11px;color:#94a3b8">强制项</div></div>';
  h += '<div class="rs-stat" style="flex:1"><div style="font-size:22px;font-weight:700;color:#d97706">'+mi+'</div><div style="font-size:11px;color:#94a3b8">重要项</div></div>';
  h += '<div class="rs-stat" style="flex:1"><div style="font-size:22px;font-weight:700;color:#059669">'+lo+'</div><div style="font-size:11px;color:#94a3b8">建议项</div></div>';
  h += '</div>';

  // ═══ 1. 质量保障管线 ═══
  h += '<div id="rs-pipeline" class="rs-sec"><div class="rs-sec-title"><span class="n">1</span>质量保障管线</div>';
  h += '<div class="rs-card">';
  h += '<p style="font-size:13px;color:#475569;line-height:2;margin:0 0 16px">报告生成后按四阶段流水线自动执行质量保障。12项标准为<strong>检测+标记</strong>模式（非强制阻断）——不通过的发现不会被删除，仅在正文底部标注⚠质量标注供审理环节参考。文本净化和建议增强在标准检查之前运行，能修复大部分常见问题，所以最终报告中真正出现质量标注的情况很少。四阶段管线由generate_report.py统一调度，每个阶段的输出是下一阶段的输入，数据单向流动不回溯。</p>';
  h += '<div style="font-size:13px;line-height:2.2;margin-bottom:12px">';
  h += '<span style="display:inline-block;padding:4px 12px;background:#e0e7ff;border-radius:4px;font-weight:600;color:#3730a3;margin:2px 4px">①文本净化</span> → ';
  h += '<span style="display:inline-block;padding:4px 12px;background:#e0e7ff;border-radius:4px;font-weight:600;color:#3730a3;margin:2px 4px">②12项质量标准检查</span> → ';
  h += '<span style="display:inline-block;padding:4px 12px;background:#e0e7ff;border-radius:4px;font-weight:600;color:#3730a3;margin:2px 4px">③建议质量增强</span> → ';
  h += '<span style="display:inline-block;padding:4px 12px;background:#e0e7ff;border-radius:4px;font-weight:600;color:#3730a3;margin:2px 4px">④报告文本二次净化</span>';
  h += '</div>';
  h += '<div class="rs-detail"><b>①文本净化（generate_report.py _sanitize_finding_boilerplate）：</b>自动清除四类内容：模板句——识别并移除"是税务合规重点方向""需逐笔核实"等8类预定义模板文本；空描述——type字段为空或detail<10字符的发现标记无效；重复句——同一finding内出现≥2次完全相同的句子（长度>30字符），只保留第一次出现；空占位符——清理自动填充失效残留如"如：()""()；()；()⑀"等模式。净化后约70%的格式问题会被自动修复。<br><b>②12项质量标准检查（generate_report.py _check_quality_standards）：</b>对每条发现的description/detail/tax_impact/suggestion/policy_ref五个字段逐条执行12项检测。每项标准含三个要素：检查方法（正则匹配+语义检测）、正确范例（标准格式示例）、错误范例（触发检测的典型错误）。不通过的在发现底部添加⚠标签，含标准编号和问题说明。标签格式如 &lt;span&gt;⚠ 标准N：问题摘要&lt;/span&gt; ——仅供审理环节参考，不影响报告主体内容。<br><b>③建议质量增强（generate_report.py _enhance_suggestions）：</b>对suggestion字段执行11条增强规则：补充具体查证路径（"在天眼查/企查查确认供应商工商状态"而非"请核实供应商"）、添加时间要求（"5个工作日内"）、添加金额参照（"涉及金额XX元"）、补充法律依据引用（如无法条→从policy_ref提取补充）、区分"正常/异常"两个分支的处理路径。增强后每条建议含完整的可执行操作链：查什么文件→怎么查→如果正常怎么办→如果异常怎么办→无法做到会有什么后果。<br><b>④文本二次净化（generate_report.py 最终净化）：</b>再次执行文本净化，清除建议增强过程中可能产生的新模板句或格式残留。二次净化侧重于：①增强过程中拼接产生的重复句 ②增强引用的政策文本中可能携带的格式标记 ③多建议拼接时产生的冗余连接词。经过四阶段管线后，报告中的文本纯净度>95%，12项标准通过率>90%。</div>';
  h += '</div></div>';

  // ═══ 2. 报告7章结构 ═══
  h += '<div id="rs-structure" class="rs-sec"><div class="rs-sec-title"><span class="n">2</span>报告7章结构</div>';
  h += '<div class="rs-detail">正式税务合规报告须含封面+7章正文+附件清单，严格遵循《税务合规工作规程》第42条规定的10项内容。封面的编号格式、日期精确到日；第一章至第七章按以下要求逐章编写；附件中发票明细表按11列标准全量展示。</div>';
  var chaps = [
    {label:'封面',title:'编号格式+报告日期',body:'标题居中"税 务 稽 查 报 告"，字体加粗加大。编号格式：税稽字[YYYY]第XXX号（年份4位+3位流水号），右上角。报告日期精确到日（如2026年6月29日），右下角。封面不编页码，正文从第一页起用阿拉伯数字连续编页码。'},
    {label:'第一章',title:'案件来源及税务合规对象基本情况',body:'必须包含8项基本信息，以表格形式呈现：①案件来源——交代税务合规启动原因（系统分析推送/举报/转办/协查）；②被查单位——企业全称须与工商登记完全一致；③统一社会信用代码——18位，精确到每一位；④法定代表人——姓名+必要信息；⑤企业类型——有限责任公司/股份有限公司/个体工商户等；⑥行业分类——须呈现三层穿透结论（工商登记X/发票推断Y/实质经营Z→综合判断）；⑦税务合规期间——起止年月精确到月份；⑧税务合规范围——本次检查的税种+资料范围+分析维度。行业分类须注明推断依据和联网核查数据来源。缺失的工商数据标注"待联网核查补充"而非"未获取"。'},
    {label:'第二章',title:'税务合规实施情况',body:'必须包含7个执行段落，每段200-400字，整体篇幅2000字以上。以税务合规过程叙事形式展开：①资料审阅与类型识别——四方交叉验证过程详述，文件识别结果表格；②公司身份锚定与发票方向判定——逐行扫描比对逻辑和三类判定规则；③行业判定与服务闸门验证——金税编码统计/三层验证机制/跳过域清单；④资金流与发票流双向核对——收款端+付款端双向详述；⑤穿透分析与知识图谱——四项穿透（供应商/客户/人员/关联方）的执行方法和检测结果；⑥行业对标——适用指标和对比结果，服务行业声明跳过原因；⑦综合分析与结论形成——全链路分析管线的执行顺序。所有数据从report对象实时提取，使用客观第三人称叙事。'},
    {label:'第三章',title:'税务合规发现问题及事实认定',body:'每条发现按六要素格式独立呈现，高风险优先排列：①税务合规性质——发现类型标题；②税务合规事实——具体描述+明细数据（须含供应商名称/金额/发票号/品名/数量/日期，禁止泛泛地说"存在XX问题"）；③证据材料——逐笔列示的证据明细表（items数组，不截断不缺斤短两）；④证据来源——规则ID（可点击溯源）+线索链编号+查证方式；⑤法律依据——完整法条名称+具体条款号，不得笼统引用；⑥处理建议——具体消除路径（"提供XX资料→如果A则做XX→无法做到的后果是XX"格式）。已审核的发现展示绿色审核横幅，不影响原始等级。跨域协商结果以彩色横幅（⛔消解/🔄调整/ℹ️标记）展示在发现标题下方。'},
    {label:'第四章',title:'税务合规结论',body:'包含5个结论段落：①推理引擎综合结论卡片——综合评分+风险等级+完整结论叙述；②风险分布表——四级风险等级（极高/高/中/低）各列出数量/占总发现百分比/代表性事项举例，以表格形式呈现；③证据链完整性——跨36域分析的覆盖范围、多源数据交叉验证构成的核心证据闭环、每条发现的证据追溯能力（规则ID→线索链→证据链→原始数据行）；④税务合规局限性声明——如实列出因资料缺失无法进一步确认的事项，缺什么资料就报什么局限性；⑤定调性总体结论——按风险等级自适应表述：高风险→"建议启动立案程序"；中风险→"建议限期自查整改"；低风险→"建议持续规范完善"。结论应定调性而非定论性。'},
    {label:'第五章',title:'处理处罚建议',body:'按紧急程度分三级，每级独立卡片红黄绿三色区分：🔴P0立即处理——极高风险/高风险发现的处理建议，涉及逃税/虚开等红线问题，标注"5个工作日内书面回复"；🟡P1限期整改——中风险发现的处理建议，涉及发票合规/账务调整等问题，标注"15个工作日内完成整改"；🟢P2持续关注——低风险/优惠机会的处理建议，涉及资料完善/合规提醒/优惠政策享受等，标注"30个工作日内完善"。每级从all_findings中按level筛选并取前5条suggestion，建议文本必须具体含可执行步骤。最后附《自查整改期限总说明》含具体时限/逾期后果/异议处理指引。'},
    {label:'第六章',title:'告知权利义务',body:'五项法定权利各独立卡片（蓝色左边线+灰色背景），文字开头须含被查单位名称："被查单位「XX」在本次税务合规过程中依法享有以下权利"。权利按程序递进排列：①回避权——与案件有利害关系的税务合规人员应当回避，收到通知后3日内书面申请；②陈述申辩权——对税务合规认定的事实/证据/法律适用可提出书面陈述和申辩，收到告知书后7日内；③听证权——对法人10000元以上的罚款处罚有权要求听证，收到告知书后5日内书面申请；④行政复议权——对处理决定不服可申请复议，收到决定书后60日内向上一级税务机关提出；⑤行政诉讼权——对复议决定不服或不经复议直接起诉，收到复议决定书后15日内向人民法院提起。每项权利卡片含4项要素：权利名称+行使条件+法定期限+法律依据。'},
    {label:'第七章',title:'税务合规人员签字',body:'必须包含：①税务合规执行人亲笔签名+执法证件号——不得代签/打印；②审理人亲笔签名+执法证件号——审理岗位人员签名；③税务合规部门盖章——税务机关公章；④报告日期——系统时间自动获取，精确到日；⑤存档说明——"本报告一式三份：税务合规部门留存一份，被查单位一份，报送上一级税务机关备案一份"。系统自动预留签名栏位及执法证件号栏位，正式税务文书需人工手签和盖章。'},
    {label:'附件',title:'证据清单',body:'必须包含以下附件：①附件一：销项发票全量明细——11列格式（购买方/品名/规格/单位/数量/金额/税额/价税合计/日期/票种/发票号）；②附件二：进项发票全量明细——同11列格式（销售方/品名/规格/单位/数量/金额/税额/价税合计/日期/票种/发票号）；③附件三：主营业务成本发票明细——核心成本供应商+品名+金额；④附件四：重大费用发票明细——费用类供应商+品名+金额；⑤附件五：银行流水汇总——收付款总额+收款方TOP5+付款方TOP5；⑥附件六：各资料文件清单——文件名+类型+有效记录数；⑦附件七：12项质量标准自检结果——通过数/未通过数/各标准问题统计。发票明细表上限200条，超出部分以电子附件形式另行提供，不截断不简化。'},
  ];
  chaps.forEach(function(ch){
    h += '<div class="rs-card"><div class="rs-card-title">'+(ch.label!=='封面'&&ch.label!=='附件'?'<span style="color:#2563eb;font-size:11px;margin-right:6px">'+ch.label+'</span>':'<span style="color:#94a3b8;font-size:11px;margin-right:6px">'+ch.label+'</span>')+ch.title+'</div>';
    h += '<div style="font-size:12px;color:#475569;line-height:2">'+ch.body+'</div></div>';
  });
  h += '</div>';

  // ═══ 3. 术语与机密规范 ═══
  h += '<div id="rs-terms" class="rs-sec"><div class="rs-sec-title"><span class="n">3</span>术语与机密规范</div>';
  h += '<div class="rs-card"><div class="rs-card-title">税务合规报告用语规范</div>';
  h += '<div class="rs-detail"><b>核心原则：</b>税务合规报告处于税务合规发现阶段，尚未进入法律裁决程序——报告用语必须体现"发现"而非"定性"的立场。<br><b>正确用语：</b>税务合规性质、税务合规事实、税务合规发现、税务合规结论、涉嫌、存疑、提示风险、可能存在、疑似。<br><b>禁止用语：</b>违法性质、违法事实、违法行为、违法认定、确定、认定、已查明、经核实确认。<br><b>原因：</b>违法认定属于税务机关审理裁决后的法律定性。税务合规报告阶段的发现尚需被查单位陈述申辩、税务机关审理复核——在报告中预判法律结论属于程序违法，审理环节会退回重写。</div></div>';
  h += '<div class="rs-card"><div class="rs-card-title">报告机密保护规则</div>';
  h += '<div class="rs-detail"><b>禁止出现在正式报告中的系统内部信息：</b><br>①引擎执行流程（阶段数量/模块名称/管线结构）——暴露系统架构<br>②规则/线索链/证据链的数量统计——暴露系统能力参数<br>③全链路闭环状态（规则ID追溯/证据链闭环等打勾清单）——系统内部质量自检<br>④系统自诊与自我修正报告——引擎内部工作日志<br>⑤审核审查面板（审查面板折叠于报告之上，不入报告正文）<br>⑥税务合规行为准则/税务合规方法论演进文字——系统内部文档<br>⑦内部技术标签（Synthesis:/Causal:/[AGI]/[Phase]等前缀）——这些是引擎内部使用的分类标签<br><b>原则：</b>报告是给被查单位和税务机关看的，只能呈现税务合规结论和依据，不能暴露"系统是怎么做到的"内部实现细节。凡是标注"⚠仅供分析参考，不入正式报告"的信息，报告生成时必须移除。</div></div></div>';

  // ═══ 4. 税务合规叙事规范 ═══
  h += '<div id="rs-narrative" class="rs-sec"><div class="rs-sec-title"><span class="n">4</span>税务合规过程叙事规范</div>';
  h += '<div class="rs-card"><div class="rs-detail">每条发现必须遵循完整的六要素叙事框架——税务合规性质→税务合规事实→证据材料→证据来源→法律依据→处理建议。<b>叙事语言风格：</b>客观第三人称——所有how_found/description/tax_impact字段使用"经查""该企业""被查单位"表述，禁止出现第一人称"我""我们"或第二人称"你""你们"。<b>叙事递进结构：</b>方法在前→过程在后→数据支撑→后果推导→建议可执行——不是"发现XX问题建议XX"，而是"通过XX方法→核查了XX数据→发现XX异常→导致XX后果→建议从XX方面处理"。<b>叙事颗粒度：</b>每条发现必须含至少1个具体数值（金额/百分比/数量）和1个时间维度（期间/日期）。纯定性的描述如"存在较大偏差"不生硬——必须写"偏差52%""涉及金额423,605.31元""涉及32笔交易"。"较大""严重""异常多"等定性词必须有紧随其后的具体数值支撑。<br><b>已删除的五段叙事：</b>此前的"发现要点→线索获取→分析过程→证据组织→通俗理解"五段叙事已从报告中移除——其内容与六要素高度重叠，保留造成冗余。当前报告仅保留六要素作为发现的核心呈现格式。<br><b>已审核的发现额外展示绿色横幅"✅已审核：审核意见摘要"，跨域协商的发现按第10节规范展示彩色横幅（⛔消解/🔄调整/ℹ️标记）。</div></div></div>';

  // ═══ 5. 同类风险合并 ═══
  h += '<div id="rs-merge" class="rs-sec"><div class="rs-sec-title"><span class="n">5</span>同类风险合并规则</div>';
  h += '<div class="rs-card"><div class="rs-detail">同一风险类型（type字段相同）的多条发现必须合并为一条在报告中呈现，不得逐条罗列导致报告冗长重复。<br>合并步骤：①按type字段分组（去除Synthesis:/Causal:等内部前缀后trim比对）；②同一组取最高风险等级作为合并后等级；③合并后标题显示"N项同类风险合并"标签（蓝色圆角徽章）；④合并后detail列出所有子项，格式为"同类风险共N项，合并列示如下，逐一列示各项细节"；⑤每条子项独立展示：子项标题、细节描述、税务影响、处理建议；⑥合并所有子项的items/evidence_rows/matched_chain_details到父项；⑦适用场景：知识图谱系列（供应商客户重叠/员工多重身份等）、发票合规系列（缺数量/缺单位/缺备注等）、资料缺失触发系列等同一type反复出现的发现。<br>代码实现：tax-doc-analysis.js 同类风险合并段，按type分组→取最高等级→展开子项。</div></div></div>';

  // ═══ 6. 12项质量标准 ═══
  h += '<div id="rs-12std" class="rs-sec"><div class="rs-sec-title"><span class="n">6</span>12项质量标准</div>';
  h += '<div class="rs-detail">以下12项标准在报告生成后依序执行检查。每项标准含要求说明、检测方法和正确范例。不通过的项目在发现底部以⚠标记，不影响报告整体合规性。标准1-5/8-9/12为强制项（红色），6-7/10-11为重要/建议项（橙色/绿色）。</div>';
  S12.forEach(function(std){
    var bdg = std.severity==='高'?'<span class="rs-badge-r">强制</span>':(std.severity==='中'?'<span class="rs-badge-a">重要</span>':'<span class="rs-badge-g">建议</span>');
    h += '<div class="rs-card"><div class="rs-card-title">标准'+std.id+'：'+std.name+' '+bdg+'</div>';
    h += '<table class="rs-tbl"><tbody>';
    h += '<tr><td class="lbl">要求</td><td class="val" style="font-size:12px">'+std.requirement+'</td></tr>';
    h += '<tr><td class="lbl">检测方式</td><td class="val" style="font-size:12px">'+std.check+'</td></tr>';
    h += '<tr><td class="lbl">范例</td><td class="val"><div class="rs-example">'+std.example+'</div></td></tr>';
    h += '</tbody></table></div>';
  });
  h += '</div>';

  // ═══ 7-11章 ═══
  h += '<div id="rs-reliability" class="rs-sec"><div class="rs-sec-title"><span class="n">7</span>7项判定可靠性要求</div>';
  h += '<div class="rs-detail">判定可靠性是比质量标准更底层的要求——质量标准检测的是"表述是否正确"，可靠性要求检测的是"分析本身是否成立"。7项要求按严重程度分为致命（红色）和高（蓝色），致命项不通过视为质量事故。</div>';
  h += '<table class="rs-tbl"><thead><tr style="border-bottom:2px solid #e2e8f0"><td class="lbl" style="width:30px">#</td><td class="lbl" style="width:110px">规则</td><td class="val">报告中的体现</td><td class="lbl" style="width:50px;text-align:center">等级</td></tr></thead><tbody>';
  [['1','公司身份锚定','报告开头必须声明当前分析的公司名称+信用代码，每项发现必须明确对应的账套主体。锚定错误→后面全部分析无效→致命事故。','致命'],
   ['2','发票方向判定','进项/销项分类须有判定依据：购买方=公司→进项，销售方=公司→销项。存疑发票须在附件中单独列出排除原因。方向错→收入/成本全部颠倒→致命事故。','致命'],
   ['3','综合判断','文件类型判定须经四方证据交叉验证（文件名→表头→内容→身份匹配），不得仅凭文件名判定。四方冲突时以数据扫描为准并说明原因。','致命'],
   ['4','只读有效信息','所有数据统计必须基于有效行（排除空白行/小计行/合计行/汇总行），不得将Excel行数直接当作有效数据量。','高'],
   ['5','存疑排除','买卖双方都不含公司的发票必须排除出所有计算和结论——A公司数据污染B公司分析属于跨账套污染。排除的数据在日志中记录并在附件中列出。','高'],
   ['6','服务行业闸门','服务行业（金税编码25类服务）不得出现进销存/BOM/毛利率对标等实物商品域的分析发现。若闸门已跳过需在第二章声明跳过原因。','高'],
   ['7','品名级精度','混合行业（服务+货物）必须品名级区分：服务品名跳过进销存域，实物品名正常执行。混为一谈视为误判。','高'],
  ].forEach(function(r){h+='<tr><td class="lbl">'+r[0]+'</td><td class="lbl" style="color:#0f172a">'+r[1]+'</td><td class="val" style="font-size:12px">'+r[2]+'</td><td style="text-align:center;font-weight:600;color:'+(r[3]==='致命'?'#dc2626':'#2563eb')+';font-size:12px">'+r[3]+'</td></tr>';});
  h += '</tbody></table></div>';

  h += '<div id="rs-paragraph" class="rs-sec"><div class="rs-sec-title"><span class="n">8</span>段落格式规范</div>';
  h += '<div class="rs-card"><div class="rs-detail"><b>五大禁止反模式：</b><br>①禁止一逗到底——多个完整逻辑句子各自独立成段，不得用逗号/分号串联为一个整块段落；②禁止多逻辑挤一段——同段不得混杂2个以上不相关分析维度；③禁止括号堆叠——不得用括号内堆砌多段判定逻辑链；④子项独立成段——"①②③④"引导的子项内容各自独立为一段；⑤数据与解释分层——先陈述数据事实（独立段）→再解释分析方法（独立段）→最后给出结论（独立段）。<br><b>拆分标准：</b>每写完一段自问——这段只有一个主题吗？能用一句话概括主旨吗？超过200字了吗（超了就拆）。换主题=换段，换视角=换段，换分析对象=换段。</div></div></div>';

  h += '<div id="rs-tts" class="rs-sec"><div class="rs-sec-title"><span class="n">9</span>语音播报标准</div>';
  h += '<div class="rs-card"><div class="rs-detail"><b>功能：</b>全文播报——报告顶部固定播报控制条，一键从封面播至附件结束；点击播报——点击报告任意段落从该处开始播报至报告结束；播放控制——暂停/继续/停止，语速0.85x-1.3x可调；视觉跟随——当前播报段落橙色底纹高亮(#fef3c7)，自动滚动至视野中央。<br><b>音色标准：</b>中文男声(zh-CN male)，低沉严肃的中年税务合规员声线。使用浏览器内置SpeechSynthesis API，不依赖外部服务。降级策略：zh-CN male→zh-CN non-Tingting→zh任意。<br><b>6档语调：</b>章节标题0.65音调/0.7x语速庄严缓慢有力；小节标题0.72/0.8x沉稳；高风险内容0.68/0.75x严肃凝重；法律条文0.70/0.72x清晰郑重；处理建议0.80/0.85x清晰有力；普通叙述0.78/0.88x新闻联播标准。</div></div></div>';

  h += '<div id="rs-negotiation" class="rs-sec"><div class="rs-sec-title"><span class="n">10</span>跨域协商标记展示规范</div>';
  h += '<div class="rs-card"><div class="rs-detail">引擎在所有域分析完成后自动运行跨域协商（15条规则四类场景）。协商结果在报告中以彩色横幅展示在发现标题和六要素之间：<br><b>⛔ 协商消解（红色横幅）：</b>域A结论直接推翻域B结论。示例："服务行业→进销存风险不适用"。被发现保留在底稿中但六要素仅作参考。适用规则NEG-001~003/020。<br><b>🔄 协商调整（黄色横幅）：</b>域A结论削弱域B结论。展示原等级→新等级和调整原因。示例："高风险→提示（服务行业毛利率不可制造业对标）"。适用规则NEG-004~005/021。<br><b>ℹ️ 协商标记（蓝色横幅）：</b>域A结论给域B加标签，不改变等级。示例："资料受限结论""含非经营收款"。适用规则NEG-010~040。<br><b>🔴 联合增强（红框新发现）：</b>多域信号同时触发→协商引擎合成更高级别新发现（如空壳企业预警、隐匿收入预警、对倒开票预警）。以红框+新编号展示。适用规则NEG-AUG-001~003。<br>代码：engine/cross_domain_negotiation.py NEGOTIATION_RULES / tax-doc-analysis.js 协商徽章渲染段。</div></div></div>';

  h += '<div id="rs-review" class="rs-sec"><div class="rs-sec-title"><span class="n">11</span>审核反馈在报告中的呈现</div>';
  h += '<div class="rs-card"><div class="rs-detail"><a href="?page=auditor-handbook#hb-s11" style="color:#2563eb;text-decoration:underline">📋 详见税务合规员手册 → 第十一章 审核反馈闭环</a></div></div></div>';

  // ═══
  h += '<div id="rs-ironlaw" class="rs-sec"><div class="rs-sec-title"><span class="n">12</span>引擎铁律与报告质量映射</div>';
  h += '<div class="rs-card"><div class="rs-detail"><a href="?page=auditor-handbook#hb-s13" style="color:#2563eb;text-decoration:underline">📋 引擎铁律完整定义 → 税务合规员手册 第十三章</a><br>以下为铁律→报告质量的交叉映射——每条铁律保证报告的一个质量维度：<br>';
  h += '<b>铁律一（科目name）：</b>保证报告中科目名称的准确性→报告第三章证据材料中的科目名称与DB一致→如果此铁律违反，报告中显示的科目名称与实际账务不符。<br>';
  h += '<b>铁律二（三号合并）：</b>保证凭证编号的唯一性→报告附件中的凭证清单不重复不遗漏→如果此铁律违反，银行余额与实际不符，报告中的资金流分析全部失真。<br>';
  h += '<b>铁律三（审计铁律）：</b>保证报告生成前数据一致性验证→7项审计必须在报告交付前通过→如果此铁律违反，报告中的数据可能借贷不平衡，送到审理环节直接退回。<br>';
  h += '<b>铁律四（ref_id去重）：</b>保证证据清单不重复→报告附件中的交易明细每条唯一→如果此铁律违反，金额模糊匹配导致不同交易被合并，证据链断裂。<br>';
  h += '<b>铁律五（普票税额）：</b>保证税务计算的正确性→报告第五章处理建议中的补税金额计算准确→如果此铁律违反，建议的补缴税额与实际应补税额不符。<br>';
  h += '<b>铁律六（7分类禁止兜底）：</b>保证成本费用分类的准确性→报告第三章的成本分析数据真实反映费用构成→如果此铁律违反，未识别费用全部归入"其他"，数据失真。<br>';
  h += '<b>铁律七（规则=代码）：</b>保证报告中的规则描述与系统行为一致→用户按报告中的规则描述去理解系统，系统实际行为与描述一致→如果此铁律违反，报告"声称"的规则和系统"实际"的逻辑对不上。<br>';
  h += '<b>铁律八（代码即承诺）：</b>保证报告中描述的每一项分析能力都有代码支撑→报告"声称"支持的分析域确实在代码中存在→如果此铁律违反，报告说"已分析XX域"但代码中没有对应函数。<br>';
  h += '<b>铁律九（全行业适用）：</b>保证报告中的行业对标数据与企业的实际行业匹配→报告的行业分类来源可追溯→如果此铁律违反，不同行业的企业看到的是同一套对标数据，部分企业被误判。<br>';
  h += '<b>铁律十（主动关联更新）：</b>保证报告中多处出现的同一数据一致→同一数字在报告的不同章节（概述/详情/附件）中数值相同→如果此铁律违反，概述说52%，详情说48%，附件说50%——三个数字都不对。<br>';
  h += '<b>铁律十一（方法论先行）：</b>保证报告中的每个结论都有方法论支撑→结论追溯到方法论→方法论追溯到代码→每步可查→如果此铁律违反，结论变成"系统判的"无法解释为什么判。</div></div></div>';

  // ═══ 第13节：四触发机制与报告交付 ═══
  h += '<div id="rs-sync" class="rs-sec"><div class="rs-sec-title"><span class="n">13</span>四触发机制与报告交付</div>';
  h += '<div class="rs-card"><div class="rs-detail"><a href="?page=auditor-handbook#hb-s10" style="color:#2563eb;text-decoration:underline">📋 详见税务合规员手册 → 第十章 数据一致性自检</a><br>系统数据的跨模块一致性由审计引擎自动保障，四触发机制（手动/启动/提交/分析）确保全模块数据统一。</div></div></div>';

  // ═══
  h += '<div id="rs-iterate" class="rs-sec"><div class="rs-sec-title"><span class="n">14</span>审核反馈→报告迭代闭环</div>';
  h += '<div class="rs-card"><div class="rs-detail"><a href="?page=auditor-handbook#hb-s11" style="color:#2563eb;text-decoration:underline">📋 详见税务合规员手册 → 第十一章 审核反馈闭环</a><br>审核反馈驱动报告持续进化——累计审核次数越多，系统对同类问题的识别越精准。</div></div></div>';

  // ═══
  // ═══ 第15节：跨域协商详细工作流程 ═══
  h += '<div id="rs-negoflow" class="rs-sec"><div class="rs-sec-title"><span class="n">15</span>跨域协商详细工作流程</div>';
  h += '<div class="rs-card"><div class="rs-detail">跨域协商引擎在报告中不是简单地"加标签"——它有一整套检测→消解→增强的工作流程，确保最终进入报告的发现体系完整且不自相矛盾。以下为从发现生成到报告输出的完整协商流程：<br>';
  h += '<b>步骤1——域分析独立运行：</b>39个域分析函数各自独立产出发现。此时各域之间没有通信——域7说"收款vs开票偏差52%→高风险"，域15说"行业判定=服务行业"——两个结论在各自的域内都是正确的，但存在潜在矛盾。<br>';
  h += '<b>步骤2——协商引擎启动：</b>run_negotiation(all_findings)遍历四类协商场景。先执行行业闸门消解（NEG-001~005），检查是否有域提供了行业判定信息（如服务行业）→通知所有制造业专属域消解/降级发现→再执行资料驱动标记（NEG-010~040）→再执行证据矛盾消解（NEG-020~030）→最后执行联合增强（NEG-AUG-001~003）。顺序不可调换——先消解才能避免矛盾发现被后续的增强引擎误用来合成错误的"增强发现"。<br>';
  h += '<b>步骤3——级联消解处理：</b>一条消解可能触发级联。例如：域15判为服务行业→消解域1的进销存异常（消解1）→域1不再报告进销存异常→域14的资料完备度不再因为"缺进销存台账"而报高风险（消解2）→域17的行业对标不再用制造业基准值（消解3）。一次协商触发三级联动消解。<br>';
  h += '<b>步骤4——协商日志记录：</b>每条发现记录协商前后的状态变化（原始等级→协商后等级/是否被消解/协商规则编号）。日志记录在filter_log中，确保协商过程可审计——不会出现"发现被消解了但说不清为什么被消解"的情况。<br>';
  h += '<b>步骤5——进入过滤管线：</b>协商后的findings进入方法论过滤器（七类规则）→行业对标→综合评分→报告生成。协商引擎是管线的第二站（在域分析之后、过滤器之前），确保后续的过滤和评分建立在"已经消除了内部矛盾的发现体系"之上。<br>';
  h += '<b>对报告质量的意义：</b>没有协商引擎的报告=36个域各自为政——域A说A、域B说B，两个结论可能互相矛盾用户不知道信谁。有协商引擎的报告=系统以"一个整体"的身份输出结论——矛盾的发现被消解/调整/标记，确保报告中的所有结论在同一个逻辑体系内是一致的。</div></div></div>';

  h += '</div></div>';
  container.innerHTML = h;
  // 侧边栏子模块入口：隐藏TOC和无关章节
  if (window._reportSection) {
    var sec = window._reportSection;
    window._reportSection = null;
    var style = document.createElement('style');
    style.textContent = '.rs-toc{display:none!important}.rs-layout{display:block!important}';
    container.appendChild(style);
    var h2 = container.querySelector('.rs-main h2');
    if (h2) h2.style.display = 'none';
    var allSecs = container.querySelectorAll('.rs-sec');
    for (var i = 0; i < allSecs.length; i++) {
      allSecs[i].style.display = allSecs[i].id === sec ? 'block' : 'none';
    }
    setTimeout(function() {
      var el = container.querySelector('#' + sec);
      if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
    }, 100);
  }
}