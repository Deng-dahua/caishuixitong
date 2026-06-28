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
    + '#rpt-stds *{margin:0;padding:0;box-sizing:border-box}'
    + '#rpt-stds{max-width:960px;margin:0 auto;padding:40px;font-family:"PingFang SC","Microsoft YaHei",serif;font-size:14px;line-height:2;color:#1a1a2e}'
    + '#rpt-stds h2{font-size:20px;font-weight:800;margin:0 0 8px 0;color:#0f172a}'
    + '#rpt-stds h3{font-size:15px;font-weight:700;color:#0f172a;margin:24px 0 12px;padding-bottom:6px;border-bottom:2px solid #2563eb;display:inline-block}'
    + '#rpt-stds .subtitle{font-size:13px;color:#64748b;margin-bottom:24px}'
    + '#rpt-stds .std-card{margin:16px 0;padding:20px 24px;border:1px solid #e2e8f0;border-radius:8px;background:#fff}'
    + '#rpt-stds .std-card .std-header{display:flex;align-items:center;gap:12px;margin-bottom:12px}'
    + '#rpt-stds .std-card .std-num{width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:14px;color:#fff;flex-shrink:0}'
    + '#rpt-stds .std-card .std-num.high{background:#dc2626}'
    + '#rpt-stds .std-card .std-num.mid{background:#d97706}'
    + '#rpt-stds .std-card .std-num.low{background:#059669}'
    + '#rpt-stds .std-card .std-name{font-size:16px;font-weight:700;color:#0f172a}'
    + '#rpt-stds .std-card .std-sev{font-size:11px;padding:2px 8px;border-radius:3px;font-weight:600}'
    + '#rpt-stds .std-card .std-sev.high{background:#fee2e2;color:#dc2626}'
    + '#rpt-stds .std-card .std-sev.mid{background:#fef3c7;color:#d97706}'
    + '#rpt-stds .std-card .std-sev.low{background:#dcfce7;color:#059669}'
    + '#rpt-stds .std-card .std-section{margin:8px 0;font-size:13px}'
    + '#rpt-stds .std-card .std-label{font-weight:600;color:#475569;min-width:70px;display:inline-block}'
    + '#rpt-stds .std-card .std-example{margin:8px 0;padding:10px 14px;background:#f8fafc;border-left:3px solid #6366f1;font-size:12px;color:#334155;border-radius:0 4px 4px 0;line-height:1.8}'
    + '#rpt-stds .std-card .std-example .ex-label{font-size:10px;color:#6366f1;font-weight:600;margin-bottom:4px;text-transform:uppercase}'
    + '#rpt-stds .overview{margin:20px 0;padding:20px 24px;background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px}'
    + '#rpt-stds .overview h3{color:#0369a1;margin:0 0 12px 0;padding:0;border:none;font-size:15px}'
    + '#rpt-stds .pipeline{font-size:13px;color:#475569;line-height:2.2}'
    + '#rpt-stds .pipeline .step{display:inline-block;padding:2px 10px;margin:2px 4px;background:#e0e7ff;border-radius:3px;font-weight:600;color:#3730a3;font-size:12px}'
    + '#rpt-stds .pipeline .arrow{color:#94a3b8;margin:0 2px}'
    + '</style>';

  h += '<div class="card card-fill"><div id="rpt-stds">';
  h += '<div class="page-header"><h1>📐 报告编制标准</h1><p>根据《税务稽查工作规程》及稽查实务标准，系统内置12项硬性质量检查指标</p></div>';

  // 管线说明
  h += '<div class="overview">';
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

  // ══════ 报告7章结构 ══════
  h += '<div class="rpt-section" style="margin-bottom:0">';
  h += '<h3>📄 报告结构（7章节 + 附件）</h3>';
  h += '<div style="font-size:13px;color:#475569;line-height:2;padding:0 8px">';
  h += '<div><strong>封面</strong>：编号（税稽字[YYYY]第XXX号）+ 报告日期</div>';
  h += '<div><strong>目录</strong>：7章节锚点跳转</div>';
  h += '<div><strong>一、案件来源及稽查对象基本情况</strong>：案件来源 / 被查单位 / 法定代表人 / 企业类型 / 行业 / 稽查期间 / 稽查范围 / 执行标准</div>';
  h += '<div><strong>二、稽查实施情况</strong>：数据比对（进销存）→ 资金核对（银行流水）→ 穿透分析（供应商/客户）→ 行业对标 → 综合分析</div>';
  h += '<div><strong>三、稽查发现问题及事实认定</strong>：每条发现按六要素格式（违法性质/违法事实/证据材料/证据来源/法律依据/处理建议）</div>';
  h += '<div><strong>四、稽查结论</strong>：综合风险评级 + 主要高风险事项 + 证据链完整性 + 总体结论</div>';
  h += '<div><strong>五、处理处罚建议</strong>：去重后的处理建议列表 + 自查整改期限</div>';
  h += '<div><strong>六、告知权利义务</strong>：5项法定权利（回避/陈述申辩/听证/复议/诉讼）</div>';
  h += '<div><strong>七、稽查人员签字</strong>：稽查执行人 + 审理人 + 稽查部门（盖章）+ 报告日期</div>';
  h += '<div><strong>附件：证据清单</strong>：进销项发票数据 / 银行流水数据 / 其他经营资料</div>';
  h += '</div>';
  h += '<div style="margin:8px 0;padding:8px 12px;background:#f0fdf4;border-radius:6px;font-size:12px;color:#166534">⚖️ 与正式税务稽查报告对照：✅ 已符合 6项 · ⚠️ 部分符合 1项（基本情况缺少工商数据） · ❌ 待补充 3项（需税务局内部流程）</div>';
  h += '</div>';

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
  h += '</tbody></table></div>';

  h += '</div>'; // close rpt-stds
  h += '</div>'; // close card-fill

  container.innerHTML = h;
}
