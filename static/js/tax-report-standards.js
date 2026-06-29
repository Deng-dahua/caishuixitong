// ==================== 报告编制要求模块 ====================

function renderReportStandards(container) {
  if (!container) return;
  window.currentModule = '报告编制要求';

  var S12 = [
    { id: 1, name: '客观第三人称叙事',
      requirement: 'how_found / description 使用"经查""该企业""被查单位"等客观第三人称表述，不得使用第一人称"我"。',
      check: '检测文本中是否含"我"，以及是否含"经查""该企业"等客观标识。',
      example: '经查，该企业2024年1-12月期间共取得进项发票XX张，金额XX元。',
      severity: '高' },
    { id: 2, name: '事实-证据-后果三要素',
      requirement: '每条发现必须同时包含：①具体事实（含数值）②证据来源（规则/线索/文件）③后果推导（→导致XX）。缺一不可。',
      check: 'tax_impact长度>20且含"→"等因果连接词；how_found长度>20；tax_impact长度>30。',
      example: '进项发票与银行付款金额偏差XX元→对应的进项税额可能存在虚抵→少缴增值税XX元。',
      severity: '高' },
    { id: 3, name: '完整因果链 A→B→C→D',
      requirement: 'tax_impact 中至少含一个"→"，完整呈现从异常现象到税务后果的推导过程。',
      check: '检测tax_impact中"→"数量≥1，且总长度≥40字符。',
      example: '毛利率异常（仅XX%）→售价低于成本的商业合理性存疑→可能隐匿未开票收入→少缴企业所得税。',
      severity: '中' },
    { id: 4, name: '可操作的紧迫感',
      requirement: 'suggestion 必须具体到可执行的步骤，禁止"请提供相关资料""请核实相关情况"等笼统表述。',
      check: 'suggestion长度≥30，且不含"请提供相关""请配合""请核实相关""请按要求"等套话模板。',
      example: '逐户在天眼查/企查查核实供应商工商状态（存续/注销/吊销）；比对注册地址是否为住宅/虚拟地址。',
      severity: '高' },
    { id: 5, name: '特定法律条款引用',
      requirement: 'policy_ref 必须引用具体法律条款，不得使用兜底模板文本（含"具体条文由审理环节根据违法事实最终认定"等）。',
      check: '检测是否含兜底模板文本；若含则自动清除，保留其他有效引用或置空。',
      example: '《中华人民共和国税收征收管理法》第三十五条第一款第（四）项',
      severity: '高' },
    { id: 6, name: '证据明细表',
      requirement: '涉及多项实体的发现（多家供应商/多个商品/多笔交易等）必须附带 items 数组，列出具体名称、金额、发票号等。',
      check: '检测detail/finding.type中是否含"家""个客户""笔""张发票""项""类"等关键词，若含但无items则标记。',
      example: 'items: [{供应商: "XX公司", 金额: "500,000", 货物: "棉纱", 发票号: "4401XXXX"}]',
      severity: '中' },
    { id: 7, name: '方法在前→过程在后',
      requirement: 'detail / how_found 应先声明稽查方法（如"采用银行流水与发票逐票核对法"），再展示具体发现结果。',
      check: '检测detail长度>80且是否含"稽查方法""核查法""比对法""穿透法"等关键词。',
      example: '采用银行流水与销项发票逐户核对法。核对步骤：①提取全部收款对方名称→②与销项发票购买方名称交叉比对→③发现X个收款对方未出现在销项购买方中。',
      severity: '低' },
    { id: 8, name: '反模板句',
      requirement: '禁止出现以下模板句："是税务稽查重点方向""需逐笔核实""请核实并提供相关佐证材料""申报不合规是税务行政处罚的常见案由"等。',
      check: '_sanitize_finding_boilerplate 自动清除：①以模板开头的detail ②连续重复的句子 ③空的占位描述。',
      example: '（此项为自动清除规则，正确范例为不含模板句的正常稽查表述）',
      severity: '高' },
    { id: 9, name: '事实具体化',
      requirement: 'detail / description 必须含具体数值——日期（如2024年1月）、金额（如150,000元）、数量（如共32笔）、百分比（如占比68%）。',
      check: '正则匹配数字+单位：\\d[\\d,.]*万?元? 或日期格式 或 数量词（共\\d+[条张笔家个]）。',
      example: '2024年1-12月期间，共取得进项发票158张，合计金额12,456,789元，其中存在数量偏差的发票32张，偏差金额合计890,000元。',
      severity: '高' },
    { id: 10, name: '防跨发现复制',
      requirement: '同一批分析中，不同发现的 tax_impact 不得完全相同（疑似复制粘贴）。',
      check: '收集所有tax_impact（长度>20的），检测是否有≥2条完全相同的impact文本。',
      example: '（每条发现的税务影响分析应基于该条的具体事实独立撰写）',
      severity: '中' },
    { id: 11, name: '空占位符检测',
      requirement: 'suggestion 不得含空占位符如"()""已识别N条关联记录（如：）""如：()；()；()"等自动填充失效的残留文本。',
      check: '检测suggestion中是否含空占位符模式，_sanitize_finding_boilerplate 自动清除。',
      example: '错误：已识别5条关联记录（如：()；()；()） / 正确：已识别5笔异常交易，涉及3家供应商。',
      severity: '中' },
    { id: 12, name: '法律条款号',
      requirement: 'policy_ref 必须含"第X条"或"第X款"等具体条款号，不能笼统引用"相关税收法规"。',
      check: '正则匹配"第[一二三四五六七八九十\\d]+条"或"第[一二三四五六七八九十\\d]+款"。',
      example: '《中华人民共和国增值税暂行条例》第九条 / 《中华人民共和国发票管理办法》第二十二条',
      severity: '高' },
  ];

  var h = '<style>'
    + '.rpt-layout{display:flex;gap:24px;max-width:1200px;margin:0 auto}'
    + '.rpt-toc{width:200px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:12px;line-height:2.2}'
    + '.rpt-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}'
    + '.rpt-toc a{display:block;color:#475569;text-decoration:none;padding:2px 8px;border-radius:4px;transition:all 0.15s}'
    + '.rpt-toc a:hover,.rpt-toc a.active{background:#eff6ff;color:#2563eb;font-weight:600}'
    + '#rpt-stds *{margin:0;padding:0;box-sizing:border-box}'
    + '#rpt-stds{flex:1;min-width:0;font-family:"PingFang SC","Microsoft YaHei",serif;font-size:14px;line-height:2;color:#1a1a2e}'
    + '#rpt-stds h2{font-size:20px;font-weight:800;margin:0 0 8px 0;color:#0f172a}'
    + '#rpt-stds h3{font-size:15px;font-weight:700;color:#0f172a;margin:24px 0 12px;padding-bottom:6px;border-bottom:2px solid #2563eb;display:inline-block}'
    + '#rpt-stds .subtitle{font-size:13px;color:#64748b;margin-bottom:24px}'
    + '#rpt-stds .std-card{margin:12px 0;padding:16px 20px;border:1px solid #e2e8f0;border-radius:8px;background:#fff}'
    + '#rpt-stds .std-card .std-header{display:flex;align-items:center;gap:10px;margin-bottom:10px}'
    + '#rpt-stds .std-card .std-num{width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:13px;color:#fff;flex-shrink:0}'
    + '#rpt-stds .std-card .std-num.high{background:#dc2626}'
    + '#rpt-stds .std-card .std-num.mid{background:#d97706}'
    + '#rpt-stds .std-card .std-num.low{background:#059669}'
    + '#rpt-stds .std-card .std-name{font-size:15px;font-weight:700;color:#0f172a}'
    + '#rpt-stds .std-card .std-sev{font-size:10px;padding:1px 6px;border-radius:3px;font-weight:600}'
    + '#rpt-stds .std-card .std-sev.high{background:#fee2e2;color:#dc2626}'
    + '#rpt-stds .std-card .std-sev.mid{background:#fef3c7;color:#d97706}'
    + '#rpt-stds .std-card .std-sev.low{background:#dcfce7;color:#059669}'
    + '#rpt-stds .std-card .std-section{margin:6px 0;font-size:13px}'
    + '#rpt-stds .std-card .std-label{font-weight:600;color:#475569;min-width:70px;display:inline-block}'
    + '#rpt-stds .std-card .std-example{margin:8px 0;padding:10px 14px;background:#f8fafc;border-left:3px solid #6366f1;font-size:12px;color:#334155;border-radius:0 4px 4px 0;line-height:1.8}'
    + '#rpt-stds .std-card .std-example .ex-label{font-size:10px;color:#6366f1;font-weight:600;margin-bottom:4px;text-transform:uppercase}'
    + '#rpt-stds .overview{margin:16px 0;padding:16px 20px;background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px}'
    + '#rpt-stds .overview h3{color:#0369a1;margin:0 0 12px 0;padding:0;border:none;font-size:15px}'
    + '#rpt-stds .pipeline{font-size:13px;color:#475569;line-height:2.2}'
    + '#rpt-stds .pipeline .step{display:inline-block;padding:2px 10px;margin:2px 4px;background:#e0e7ff;border-radius:3px;font-weight:600;color:#3730a3;font-size:12px}'
    + '#rpt-stds .pipeline .arrow{color:#94a3b8;margin:0 2px}'
    + '.rpt-table{width:100%;border-collapse:collapse;font-size:13px;margin:12px 0}'
    + '.rpt-table th{background:#f8fafc;padding:10px 12px;text-align:left;font-weight:600;border-bottom:2px solid #e2e8f0;color:#475569}'
    + '.rpt-table td{padding:10px 12px;border-bottom:1px solid #f1f5f9;vertical-align:top}'
    + '</style>';

  h += '<div class="rpt-layout">';
  
  // ── 左侧目录 ──
  h += '<nav class="rpt-toc">';
  h += '<div class="toc-title">📖 目录</div>';
  h += '<a href="#rpt-overview" class="active">一 质量保障管线</a>';
  h += '<a href="#rpt-structure">二 报告7章结构</a>';
  h += '<a href="#rpt-terms">三 术语与机密规范</a>';
  h += '<a href="#rpt-narrative">四 稽查过程叙事规范</a>';
  h += '<a href="#rpt-merge">五 同类风险合并规则</a>';
  h += '<a href="#rpt-12std">六 12项质量标准</a>';
  h += '<a href="#rpt-reliability">七 7项判定可靠性要求</a>';
  h += '</nav>';

  h += '<div id="rpt-stds">';
  h += '<h2>📐 报告编制标准</h2>';
  h += '<p class="subtitle">根据《税务稽查工作规程》及稽查实务标准，系统内置12项硬性质量检查指标</p>';


  // ══════ 一、质量保障管线 ══════
  h += '<div id="rpt-overview" class="overview">';
  h += '<h3>⚙️ 质量保障管线</h3>';
  h += '<div class="pipeline">';
  h += '报告生成后按以下顺序自动执行质量保障：<br>';
  h += '<span class="step">文本净化</span> <span class="arrow">→</span> ';
  h += '<span class="step">12项质量标准检查</span> <span class="arrow">→</span> ';
  h += '<span class="step">建议质量增强</span> <span class="arrow">→</span> ';
  h += '<span class="step">报告文本净化</span>';
  h += '</div>';
  h += '<div style="margin-top:12px;font-size:12px;color:#64748b">';
  h += '注意：12项标准为<strong>检测+标记</strong>模式（非强制阻断）。不通过的发现不会被删除，仅在正文底部标注 ⚠ 质量标注。文本净化和建议增强在标准检查之前运行，能修复大部分常见问题。';
  h += '</div>';
  h += '</div>';

  // 统计概览
  var highCount = S12.filter(function(s){return s.severity==='高';}).length;
  var midCount = S12.filter(function(s){return s.severity==='中';}).length;
  var lowCount = S12.filter(function(s){return s.severity==='低';}).length;
  h += '<div style="display:flex;gap:12px;margin:16px 0">';
  h += '<div style="flex:1;text-align:center;padding:12px;background:#fef2f2;border-radius:6px;font-size:13px"><div style="font-size:24px;font-weight:800;color:#dc2626">' + highCount + '</div><div style="color:#991b1b">严重</div></div>';
  h += '<div style="flex:1;text-align:center;padding:12px;background:#fffbeb;border-radius:6px;font-size:13px"><div style="font-size:24px;font-weight:800;color:#d97706">' + midCount + '</div><div style="color:#92400e">重要</div></div>';
  h += '<div style="flex:1;text-align:center;padding:12px;background:#f0fdf4;border-radius:6px;font-size:13px"><div style="font-size:24px;font-weight:800;color:#059669">' + lowCount + '</div><div style="color:#166534">建议</div></div>';
  h += '</div>';

  // ══════ 二、报告7章结构 ══════
  h += '<div id="rpt-structure">';
  h += '<h3>📄 报告结构（7章节 + 附件）</h3>';
  
  // 封面
  h += '<div class="std-card">';
  h += '<div class="std-header"><div class="std-num" style="background:#1a1a2e;width:auto;padding:0 12px;border-radius:4px">封 面</div><div class="std-name">编号格式 + 报告日期</div></div>';
  h += '<div class="std-section"><span class="std-label">📋 内容要求</span>标题"税 务 稽 查 报 告"，居中。编号格式：税稽字[YYYY]第XXX号（年份+3位序号）。报告日期精确到日。</div>';
  h += '</div>';
  
  // 一
  h += '<div class="std-card">';
  h += '<div class="std-header"><div class="std-num" style="background:#1a1a2e;width:auto;padding:0 12px;border-radius:4px">第一章</div><div class="std-name">案件来源及稽查对象基本情况</div></div>';
  h += '<div class="std-section"><span class="std-label">📋 板块内容</span>必须包含以下8项：<br>';
  h += '① <strong>案件来源</strong>——交代来龙去脉：系统分析推送/举报/转办/协查，说明稽查启动原因<br>';
  h += '② <strong>被查单位</strong>——企业全称（须与工商登记完全一致）<br>';
  h += '③ <strong>统一社会信用代码</strong>——18位信用代码，精确到每一位<br>';
  h += '④ <strong>法定代表人</strong>——姓名+身份证号脱敏后6位<br>';
  h += '⑤ <strong>企业类型</strong>——有限责任公司/股份有限公司/个体工商户等<br>';
  h += '⑥ <strong>行业分类</strong>——发票推断行业+联网核查结果<br>';
  h += '⑦ <strong>稽查期间</strong>——起止年月，精确到月份<br>';
  h += '⑧ <strong>稽查范围</strong>——本次检查的税种+资料范围+分析维度</div>';
  h += '<div class="std-section"><span class="std-label">✏️ 编制方法</span>以表格形式呈现8项基本信息，格式统一。行业分类应注明推断依据（销项发票品名金税分类编码）。联网核查结果应注明数据来源（天眼查/企查查/国家公示系统）。</div>';
  h += '</div>';
  
  // 二
  h += '<div class="std-card">';
  h += '<div class="std-header"><div class="std-num" style="background:#1a1a2e;width:auto;padding:0 12px;border-radius:4px">第二章</div><div class="std-name">稽查实施情况</div></div>';
  h += '<div class="std-section"><span class="std-label">📋 板块内容</span>必须包含以下7个执行段落（每段200-400字），以稽查过程叙事形式展开：<br>';
  h += '① <strong>资料审阅与类型识别</strong>——列出本次分析加载的全部资料（份数+类型+有效记录数），详细说明四方交叉验证的四步过程（文件名关键词→列头结构指纹→数据内容扫描→公司身份匹配），并以表格形式呈现每份文件的识别结果<br>';
  h += '② <strong>公司身份锚定与发票方向判定</strong>——声明以账套公司（名称+信用代码）为锚点，详述逐行扫描购买方/销售方的比对逻辑和三类判定规则（买方匹配→进项/卖方匹配→销项/都不匹配→存疑），给出判定结果统计，并进一步说明进项发票的三层分类（主营成本/重大费用/日常报销）<br>';
  h += '③ <strong>行业判定与服务行业闸门</strong>——提取销项品名金税编码并统计占比，根据25类服务行业列表判定是否触发闸门。若触发则详述三层验证机制（管线层/域分析层/输出层）和跳过/适用的分析域清单<br>';
  h += '④ <strong>资金流与发票流双向核对</strong>——分收款端（贷方汇总+收款构成+与销项客户比对）和付款端（借方汇总+付款构成+与进项供应商比对）两端详述，并明确引用"发票≠收付款1:1"方法论的六大类非采购支出说明<br>';
  h += '⑤ <strong>穿透分析与知识图谱</strong>——列出供应商穿透、客户穿透、人员穿透（员工与交易方交叉比对）、关联方穿透（法代/股东与交易对方比对）四项穿透分析的具体执行方法和检测结果<br>';
  h += '⑥ <strong>行业对标</strong>——说明适用的行业基准指标及对比结果。服务行业声明跳过进销比/毛利率对标的原因（成本结构以人力为主非原材料），但保留人均产值等适用指标的对比<br>';
  h += '⑦ <strong>综合分析与结论形成</strong>——说明全链路分析管线的执行顺序：域分析→规则引擎→线索链/证据链→因果叙事→Benford检验→方法论过滤器→合规门禁</div>';
  h += '<div class="std-section"><span class="std-label">✏️ 编制方法</span>每段200-400字，必须基于实际分析数据动态生成（文件数/记录数/金额/占比等均从report对象实时提取），不得硬编码固定模板文本。使用客观第三人称（"本次核查采用…""经逐行比对…""系统自动执行…"）。第二章整体篇幅应在2000字以上，呈现完整的稽查实施画卷。</div>';
  h += '</div>';
  
  // ══════ 三、术语与机密规范 ══════
  h += '<div id="rpt-terms">';
  // 稽查术语规范
  h += '<div class="std-card">';
  h += '<div class="std-header"><div class="std-num" style="background:#dc2626;width:auto;padding:0 12px;border-radius:4px">术语规范</div><div class="std-name">稽查报告用语规范（2026-06-28确立）</div></div>';
  h += '<div class="std-section"><span class="std-label">📋 核心原则：</span>稽查报告处于稽查发现阶段，尚未进入法律裁决程序，因此报告用语必须体现"发现"而非"定性"的立场。<br>';
  h += '<strong>正确用语：</strong>稽查性质、稽查事实、稽查发现、稽查结论、涉嫌、存疑、提示风险<br>';
  h += '<strong>禁止用语：</strong>违法性质、违法事实、违法行为、违法认定、确定、认定<br>';
  h += '<strong>原因：</strong>违法认定属于税务机关审理裁决后的法律定性，稽查报告阶段的发现尚需被查单位陈述申辩、税务机关审理复核，不得在报告中预判法律结论。</div>';
  h += '</div>';
  
  // 报告机密保护
  h += '<div class="std-card">';
  h += '<div class="std-header"><div class="std-num" style="background:#7c3aed;width:auto;padding:0 12px;border-radius:4px">机密保护</div><div class="std-name">报告机密保护规则（2026-06-28确立）</div></div>';
  h += '<div class="std-section"><span class="std-label">📋 禁止出现在正式报告中的系统内部信息：</span><br>';
  h += '① 引擎执行流程（52步/模块数量/阶段名称）——暴露系统架构<br>';
  h += '② 规则/线索链/证据链的数量统计——暴露系统能力参数<br>';
  h += '③ 全链路闭环状态（规则ID追溯/证据链闭环等打勾清单）——系统内部质量自检<br>';
  h += '④ 系统自诊与自我修正报告——引擎内部工作日志<br>';
  h += '⑤ 驳回按钮/审查面板（审查面板折叠于报告之上，不入报告正文）<br>';
  h += '⑥ 稽查行为准则/稽查方法论演进文字——系统内部文档<br>';
  h += '⑦ 内部技术标签（Synthesis:/Causal:/[AGI]/[Phase]等前缀）<br>';
  h += '<strong>原则：</strong>报告给被查单位和税务机关看的，只能呈现稽查结论和依据，不能暴露"系统是怎么做到的"的内部实现细节。</div>';
  h += '</div>';
  
  // 三
  h += '<div class="std-card">';
  h += '<div class="std-header"><div class="std-num" style="background:#1a1a2e;width:auto;padding:0 12px;border-radius:4px">第三章</div><div class="std-name">稽查发现问题及事实认定</div></div>';
  h += '<div class="std-section"><span class="std-label">📋 板块内容</span>每条发现必须按<strong>六要素</strong>格式逐项呈现，高风险优先排列：<br>';
  h += '① <strong>稽查性质</strong>——发现类型标题（如"收款来源与开票客户不匹配""进项发票缺少计量单位"）<br>';
  h += '② <strong>稽查事实</strong>——具体描述+明细数据（必须含：供应商名称/金额/发票号/品名/数量/日期，禁止泛泛说"存在XX问题"）<br>';
  h += '③ <strong>证据材料</strong>——逐笔列示的证据明细表（不截断、不缺斤短两）<br>';
  h += '④ <strong>证据来源</strong>——规则ID（可点击溯源）+ 线索链编号 + 查证方式（如"银行流水与发票双向核对法"）<br>';
  h += '⑤ <strong>法律依据</strong>——完整法条名称+具体条款号（如《税收征收管理法》第六十三条第一款），不得笼统引用<br>';
  h += '⑥ <strong>处理建议</strong>——具体消除路径（"提供XX资料→如果A则做XX→无法做到的后果是XX"格式）</div>';
  h += '<div class="std-section"><span class="std-label">✏️ 编制方法</span>每条发现独立成段，结构统一：标题行 → 稽查过程叙事段 → 六要素格式 → 证据链路。事实描述必须含具体数值（金额/数量/百分比/日期）。禁止出现"该企业存在XX问题，需进一步核实"这种笼统表述——要么列出具体数据，要么不报。高风险发现必须附带items明细数组。</div>';
  h += '</div>';
  
  // 第三章补充：稽查过程叙事规范
  h += '<div class="std-card">';
  h += '<div class="std-header"><div class="std-num" style="background:#2563eb;width:auto;padding:0 12px;border-radius:4px">第三章·附</div><div class="std-name">稽查过程叙事规范（2026-06-28确立）</div></div>';
  h += '<div class="std-section"><span class="std-label">📋 每条发现必须包含以下五段稽查叙事，将稽查过程写得明明白白、通俗易懂：</span><br>';
  h += '① <strong>📌 发现要点</strong>——通俗描述这个风险是什么、为什么会被关注。用外行也能看懂的语言，让被查单位一眼就明白问题所在。取finding.description或finding.detail的前300字。<br>';
  h += '② <strong>📡 线索获取</strong>——这个风险是怎么被发现的？说明从哪些数据源（银行流水/销项发票/进项发票/工资表/社保明细等）开始排查，通过什么方法（逐票比对/三方交叉/百分比阈值等）锁定了异常。基于finding.provenance.sources和finding.how_found。<br>';
  h += '③ <strong>🔬 分析过程</strong>——稽查是怎么一层层查下去的？当finding.matched_chain_details存在时，从中提取steps_detail，按序号展开调查步骤（带风险等级图标🔴🟡🟢）。当无证据链时，自动生成4步默认分析路径（初步筛查→交叉比对→阈值判定→深度核查）。<br>';
  h += '④ <strong>📋 证据组织</strong>——证据是怎么串起来的？说明调用了多少类数据源，提取了多少条证据记录（evidence_rows数量），形成了多少项证据明细（items数量），通过多少条关联证据链进行交叉验证（matched_chain_count）。<br>';
  h += '⑤ <strong>💡 通俗理解</strong>——为什么会这样？用关键数据（偏差百分比/涉及金额/异常项数）解释问题的严重性。从finding.tax_impact中提取税务影响，从finding.detail中提取百分比和金额数据做通俗化表述。<br>';
  h += '</div>';
  h += '<div class="std-section"><span class="std-label">✏️ 编制方法</span>五段叙事必须基于finding对象中的实际字段动态生成，不得硬编码固定文本。每段2-5句话，总字数控制在300-500字。语言风格：像老稽查员在给新人讲解——既专业又通俗，既有数据又有解释。无证据链时自动生成默认路径，确保每条发现都有完整的分析过程描述。</div>';
  h += '<div class="std-section" style="background:#fffbeb;border-left:3px solid #e67700"><span class="std-label">🔗 同类风险合并规则（规则二十五·2026-06-28新增）</span><br>';
  h += '同一风险类型（type字段相同）出现的多条发现，<strong>必须合并为一条</strong>在报告中呈现，不得逐条罗列导致报告冗长重复。合并规则：<br>';
  h += '① 按type字段分组（去除Synthesis:/Causal:等内部前缀后trim比对）<br>';
  h += '② 同一组取最高风险等级作为合并后的等级<br>';
  h += '③ 合并后标题显示"N项同类风险合并"标签<br>';
  h += '④ 合并后的detail列出所有子项：格式为"（同类风险共N项，合并列示如下）\\n\\n【子项1】...\\n\\n【子项2】..."<br>';
  h += '⑤ 每条子项独立展示：子项标题、细节描述、税务影响、处理建议<br>';
  h += '⑥ 合并所有子项的items/evidence_rows/matched_chain_details到父项<br>';
  h += '⑦ 适用场景：知识图谱系列（供应商客户重叠/员工多重身份等）、发票合规系列（缺数量/缺单位等）、资料缺失触发系列等同一type反复出现的发现<br>';
  h += '代码：static/js/tax-doc-analysis.js _renderReportFallback() 同类风险合并段</div>';
  h += '</div>';
  
  // 四
  h += '<div class="std-card">';
  h += '<div class="std-header"><div class="std-num" style="background:#1a1a2e;width:auto;padding:0 12px;border-radius:4px">第四章</div><div class="std-name">稽查结论</div></div>';
  h += '<div class="std-section"><span class="std-label">📋 板块内容</span>必须包含以下5个结论段落：<br>';
  h += '① <strong>推理引擎综合结论卡片</strong>——若存在_phase4_synthesis发现则渲染，展示综合评分+风险等级+完整结论叙述<br>';
  h += '② <strong>风险分布表</strong>——四级风险等级（极高/高/中/低）各列出：数量、占总发现百分比、代表性事项举例。以表格形式呈现，一目了然<br>';
  h += '③ <strong>证据链完整性</strong>——说明跨18域分析的覆盖范围、多源数据交叉验证构成的核心证据闭环、每条发现的证据追溯能力<br>';
  h += '④ <strong>稽查局限性声明</strong>——如实列出因资料缺失无法进一步确认的事项。缺什么资料就报什么局限性，不存在"没资料不影响判断"的逻辑<br>';
  h += '⑤ <strong>定调性总体结论</strong>——按风险等级自适应：高风险→建议启动立案程序/中风险→建议限期自查整改/低风险→建议持续规范完善。使用"存在XX疑点""涉嫌XX""提示XX风险"等发现性表述</div>';
  h += '<div class="std-section"><span class="std-label">✏️ 编制方法</span>结论应定调性而非定论性。风险分布表的数据（数量/占比）从all_findings实时计算。局限性声明从MISSING_CONSEQUENCE_TRIGGER中提取缺失资料清单。总体结论根据risk_score和overall_risk自适应生成，不硬编码固定文字。</div>';
  h += '</div>';
  
  // 五
  h += '<div class="std-card">';
  h += '<div class="std-header"><div class="std-num" style="background:#1a1a2e;width:auto;padding:0 12px;border-radius:4px">第五章</div><div class="std-name">处理处罚建议</div></div>';
  h += '<div class="std-section"><span class="std-label">📋 板块内容</span>按紧急程度分为三级，每级独立卡片，红/黄/绿三色区分：<br>';
  h += '🔴 <strong>P0立即处理</strong>——极高风险/高风险发现的处理建议。涉及逃税、虚开等红线问题。从all_findings中筛选level为极高/高风险且有suggestion的发现，取前5条。卡片标注"5工作日内书面回复"。<br>';
  h += '🟡 <strong>P1限期整改</strong>——中风险发现的处理建议。涉及发票合规、账务调整等问题。从all_findings中筛选level为中风险且有suggestion的发现，取前5条。卡片标注"15工作日内完成整改"。<br>';
  h += '🟢 <strong>P2持续关注</strong>——低风险/优惠机会的处理建议。涉及资料完善、合规提醒、优惠政策享受等。从all_findings中筛选level为低风险/优惠机会且有suggestion的发现，取前5条。卡片标注"30工作日内完善"。<br>';
  h += '最后附《自查整改期限》总说明：包含P0/P1/P2各级的具体时限、逾期后果、异议处理指引。</div>';
  h += '<div class="std-section"><span class="std-label">✏️ 编制方法</span>每级建议从all_findings中按level筛选并取前5条suggestion。建议文本必须具体（含可执行步骤），禁止笼统模板。三级卡片间用空行+色块边框分隔，视觉上一目了然。整改期限附法律依据。</div>';
  h += '</div>';
  
  // 六
  h += '<div class="std-card">';
  h += '<div class="std-header"><div class="std-num" style="background:#1a1a2e;width:auto;padding:0 12px;border-radius:4px">第六章</div><div class="std-name">告知权利义务</div></div>';
  h += '<div class="std-section"><span class="std-label">📋 板块内容</span>五项法定权利各独立卡片，每卡包含4项要素：<br>';
  h += '① <strong>权利名称+法律解释</strong>——用通俗语言说明该权利的含义<br>';
  h += '② <strong>行使条件+操作方式</strong>——什么情况下可以行使、如何操作（书面申请/向谁提出/需要什么材料）<br>';
  h += '③ <strong>法定期限</strong>——精确到日（如"收到通知后3日内""收到决定书后60日内"）<br>';
  h += '④ <strong>法律依据</strong>——具体法条号（如《税收征收管理法》第十二条）<br>';
  h += '权利顺序按程序递进排列：回避→陈述申辩→听证→复议→诉讼<br>';
  h += '文本开头须包含被查单位名称（"被查单位「XX」在本次稽查过程中依法享有以下权利"）</div>';
  h += '<div class="std-section"><span class="std-label">✏️ 编制方法</span>每张权利卡片左边蓝色竖线+灰色背景，与其他章节视觉区分。法定人数/金额标准（如听证标准"法人10000元以上"）必须明确标注。语言既要法律严谨又要通俗易懂。</div>';
  h += '</div>';
  
  // 七
  h += '<div class="std-card">';
  h += '<div class="std-header"><div class="std-num" style="background:#1a1a2e;width:auto;padding:0 12px;border-radius:4px">第七章</div><div class="std-name">稽查人员签字</div></div>';
  h += '<div class="std-section"><span class="std-label">📋 板块内容</span>必须包含：<br>';
  h += '① <strong>稽查执行人签名+执法证件号</strong>——亲笔签名，不得代签/打印，同时注明执法证件编号<br>';
  h += '② <strong>审理人签名+执法证件号</strong>——审理岗位人员亲笔签名<br>';
  h += '③ <strong>稽查部门盖章</strong>——税务机关公章<br>';
  h += '④ <strong>报告日期</strong>——精确到日<br>';
  h += '⑤ <strong>存档说明</strong>——"本报告一式三份：稽查部门留存一份，被查单位一份，报送上一级税务机关备案一份"</div>';
  h += '<div class="std-section"><span class="std-label">✏️ 编制方法</span>系统自动预留签名栏位及执法证件号栏位。正式税务文书需人工手签和盖章。报告日期从系统时间自动获取。</div>';
  h += '</div>';
  
  // 附件
  h += '<div class="std-card">';
  h += '<div class="std-header"><div class="std-num" style="background:#1a1a2e;width:auto;padding:0 12px;border-radius:4px">附 件</div><div class="std-name">证据清单</div></div>';
  h += '<div class="std-section"><span class="std-label">📋 板块内容</span>必须包含以下附件：<br>';
  h += '① <strong>销项发票全量明细</strong>——11列格式（购买方/品名/规格/单位/数量/金额/税额/价税合计/日期/票种/发票号）<br>';
  h += '② <strong>进项发票全量明细</strong>——11列格式（销售方/品名/规格/单位/数量/金额/税额/价税合计/日期/票种/发票号）<br>';
  h += '③ <strong>主营业务成本发票明细</strong>——核心成本供应商+品名+金额<br>';
  h += '④ <strong>重大费用发票明细</strong>——费用类供应商+品名+金额<br>';
  h += '⑤ <strong>银行流水汇总</strong>——收款/付款总额+收款方TOP5<br>';
  h += '⑥ <strong>各资料文件清单</strong>——文件名+类型+有效记录数<br>';
  h += '⑦ <strong>质量标准自检结果</strong>——12项标准的通过/未通过统计</div>';
  h += '<div class="std-section"><span class="std-label">✏️ 编制方法</span>附件一至四为发票明细表（11列标准格式），附件五为银行流水摘要，附件六为文件清单，附件七为质量自检。发票明细表必须按11列全量展示（上限200条），不可截断不可简化。系统自动生成。</div>';
  h += '</div>';
  
  h += '<div style="margin:8px 0;padding:8px 12px;background:#f0fdf4;border-radius:6px;font-size:12px;color:#166534">⚖️ 与正式税务稽查报告对照：✅ 已符合 封编号/7章结构/六要素/5项权利/签字栏位/证据清单 · ⚠️ 部分符合 基本情况缺少工商数据 · ❌ 待补充 送达回证/审理意见书/行政处罚告知书（需税务局内部流程）</div>';

  // 逐条标准
  h += '<h3>逐条标准</h3>';

  S12.forEach(function(std) {
    var sevCls = std.severity === '高' ? 'high' : (std.severity === '中' ? 'mid' : 'low');
    var sevText = std.severity === '高' ? '强制' : (std.severity === '中' ? '重要' : '建议');
    var numCls = std.severity === '高' ? 'high' : (std.severity === '中' ? 'mid' : 'low');

    h += '<div class="std-card">';
    h += '<div class="std-header">';
    h += '<div class="std-num ' + numCls + '">' + std.id + '</div>';
    h += '<div class="std-name">标准' + std.id + '：' + std.name + '</div>';
    h += '<div class="std-sev ' + sevCls + '">' + sevText + '</div>';
    h += '</div>';

    h += '<div class="std-section"><span class="std-label">📋 要求</span>' + std.requirement + '</div>';
    h += '<div class="std-section"><span class="std-label">🔍 检测方式</span>' + std.check + '</div>';

    h += '<div class="std-example">';
    h += '<div class="ex-label">✅ 正确范例</div>';
    h += std.example;
    h += '</div>';

    h += '</div>';
  });

  // 附件说明
  h += '<div style="margin:24px 0;padding:16px 20px;background:#fafbfc;border:1px solid #e2e8f0;border-radius:8px;font-size:12px;color:#64748b;line-height:2">';
  h += '<strong style="color:#0f172a">附件说明：</strong><br>';
  h += '报告正文末尾的<strong>附件二</strong>为本次分析的质量标准自检结果（通过数/未通过数/各标准问题统计）。<br>';
  h += '未通过的项目在正文对应发现的底部以 <span style="background:#fef3c7;padding:0 4px;border-radius:2px;font-size:11px">⚠ 质量标注</span> 形式呈现，不影响报告整体合规性，仅作为审理环节的补充参考。';
  h += '</div>';

  h += '<div class="rpt-section" style="margin-top:40px">';
  h += '<h2 class="rpt-title">🔍 判定可靠性要求（2026-06-28新增）</h2>';
  h += '<table class="rpt-table"><thead><tr><th style="width:6%">#</th><th style="width:18%">规则</th><th style="width:40%">报告中的体现</th><th style="width:12%">质量等级</th></tr></thead><tbody>';
  
  h += '<tr><td>1</td><td><strong>公司身份锚定</strong></td>';
  h += '<td>报告开头必须声明当前分析的公司名称+信用代码，每项发现必须明确对应的账套主体</td><td style="color:#dc2626">致命</td></tr>';
  
  h += '<tr><td>2</td><td><strong>发票方向判定</strong></td>';
  h += '<td>报告中的进项/销项分类必须有判定依据：购买方=公司→进项，销售方=公司→销项。存疑发票必须在附件中单独列出排除原因</td><td style="color:#dc2626">致命</td></tr>';
  
  h += '<tr><td>3</td><td><strong>综合判断</strong></td>';
  h += '<td>文件类型判定必须经过四方证据交叉验证，不得仅凭文件名判定。证据冲突时必须在报告中说明原因</td><td style="color:#dc2626">致命</td></tr>';
  
  h += '<tr><td>4</td><td><strong>只读有效信息</strong></td>';
  h += '<td>所有数据统计必须基于有效行（排除空白/小计/合计），不得将Excel行数直接当作数据量</td><td style="color:#2563eb">高</td></tr>';

  h += '<tr><td>5</td><td><strong>存疑排除</strong></td>';
  h += '<td>买卖双方都不含公司的发票必须排除出所有计算和结论，不得以任何默认值处理</td><td style="color:#2563eb">高</td></tr>';
  
  h += '<tr><td>6</td><td><strong>服务行业闸门</strong></td>';
  h += '<td>服务行业（25类）不得出现进销存/BOM/进销比/毛利率对标等实物商品的发现。已跳过时需在报告"分析方法"段声明</td><td style="color:#2563eb">高</td></tr>';
  
  h += '<tr><td>7</td><td><strong>品名级精度</strong></td>';
  h += '<td>混合行业（服务+货物）必须品名级区分：服务品名跳过进销存，实物品名正常检查。混为一谈视为质量事故</td><td style="color:#2563eb">高</td></tr>';

  h += '<tr><td>8</td><td><strong>段落格式规范</strong></td>';
  h += '<td>禁止一逗到底、禁止多逻辑挤一段、禁止括号堆叠判定链、子项必须独立成段、数据与解释分层。违者退回重写</td><td style="color:#2563eb">高</td></tr>';
  
  h += '<tr><td>9</td><td><strong>语音播报覆盖</strong></td>';
  h += '<td>报告必须内置播报功能——全文播报+点击任意段落从该处播至结束，新闻联播级6档语调，橙色底纹跟随</td><td style="color:#059669">中</td></tr>';
  h += '</tbody></table></div>';

  // ── 段落格式规范（新增）──
  h += '<h2 class="rpt-title">📝 段落格式规范（规则二十六·2026-06-28确立）</h2>';
  h += '<div class="std-card" style="margin-bottom:12px">';
  h += '<div class="std-section"><span class="std-label">🚫 五大禁止反模式</span><br>';
  h += '① <strong>禁止一逗到底</strong>——多个完整逻辑句子不得用逗号、分号串联为一个整块段落，必须各自独立成段<br>';
  h += '② <strong>禁止多逻辑挤一段</strong>——同一段落内不得混杂2个以上不相关的分析维度（如同时描述"供应商穿透"和"客户穿透"）<br>';
  h += '③ <strong>禁止括号堆叠</strong>——不得使用"(若A→B)(若C→D)(若E→F)"的方式在括号内堆砌多段判定逻辑<br>';
  h += '④ <strong>子项必须独立成段</strong>——"①②③④"等序号引导的子项内容必须各自独立为一段，不得全部塞入同一段<br>';
  h += '⑤ <strong>数据与解释分层</strong>——先陈述数据事实（独立段），再解释分析方法（独立段），最后给出结论（独立段）</div>';
  h += '<div class="std-section"><span class="std-label">✅ 正确范例</span>身份锚定：判定一/判定二/判定三各自独立一段，每段100-150字。行业闸门：四条跳过各自独立一段，每段含逻辑+原因+后果。穿透分析：四项穿透各自独立一段，每段含方法+检测对象+风险含义。综合分析：五环节各自独立一段，每段含环节名+输入+处理+输出</div>';
  h += '<div class="std-section"><span class="std-label">✏️ 编制方法</span>每写完一段自问：这段只有一个主题吗？这段能用一句话概括主旨吗？这段超过200字了吗（超了就拆）。拆分标准：换主题=换段，换视角=换段，换分析对象=换段。不得因为"反正写得下"就把三四个意思堆在同一段里。代码位置：static/js/tax-doc-analysis.js _renderReportFallback() Ch2各段</div>';
  h += '</div>';

  // ── 语音播报规范（新增）──
  h += '<h2 class="rpt-title">🔊 语音播报标准（规则二十七·2026-06-28确立）</h2>';
  h += '<div class="std-card">';
  h += '<div class="std-section"><span class="std-label">📋 功能要求</span><br>';
  h += '① <strong>全文播报</strong>——报告顶部固定播报控制条，一键从封面播至附件结束<br>';
  h += '② <strong>点击播报</strong>——点击报告任意段落文字，从该处开始播报并持续至报告结束<br>';
  h += '③ <strong>播放控制</strong>——暂停/继续/停止，语速0.85x-1.3x可调<br>';
  h += '④ <strong>视觉跟随</strong>——当前播报段落橙色底纹高亮（#fef3c7），自动滚动至视野中央<br>';
  h += '⑤ <strong>音色标准</strong>——中文男声（zh-CN male），低沉严肃的中年稽查员声线</div>';
  h += '<div class="std-section"><span class="std-label">🎙️ 新闻联播级情感语调（6档）</span><br>';
  h += '章节标题 0.65音调/0.7x语速 庄严缓慢有力 · 小节标题 0.72/0.8x 沉稳 · 高风险内容 0.68/0.75x 严肃凝重 · 法律条文 0.70/0.72x 清晰郑重 · 处理建议 0.80/0.85x 清晰有力 · 普通叙述 0.78/0.88x 新闻联播标准</div>';
  h += '<div class="std-section"><span class="std-label">✏️ 编制方法</span>使用浏览器内置SpeechSynthesis API，不依赖外部服务。系统自动检测可用中文男声，降级策略：zh-CN male→zh-CN non-Tingting→zh任意。代码位置：static/js/tax-doc-analysis.js TTS函数族（_initReportTTS/_ttsSpeakNext/_ttsSetNewsTone/_bindClickToSpeak）</div>';
  h += '</div>';

  h += '</div>'; // close rpt-stds
  h += '</div>'; // close rpt-layout

  container.innerHTML = h;
}
