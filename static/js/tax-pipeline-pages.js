// ══════════════════════════════════════════════════════════════
//  稽查管道独立页：文件解析 | 域分析 | 跨域证据链 | 方法论过滤器
// ══════════════════════════════════════════════════════════════

// ==================== 页面1：文件解析（极简风） ====================
function renderFileParsingPage(container) {
  if (!container) return;
  window.currentModule = '文件解析';
  container.innerHTML = ''
    + '<div style="max-width:960px;margin:0 auto;padding:40px 24px 80px">'
    + '  <div style="margin-bottom:48px">'
    + '    <h2 style="font-size:24px;font-weight:700;color:#0f172a;margin:0 0 6px">文件解析</h2>'
    + '    <p style="font-size:14px;color:#94a3b8;margin:0">三层递进识别 · 34类文件指纹 · 数据推断兜底</p>'
    + '  </div>'
    + '  <div id="fp-static"></div>'
    + '  <div id="fp-analysis-result"></div>'
    + '</div>';
  renderFileParsingStatic();
  loadFileParsingData();
}

function renderFileParsingStatic() {
  var target = document.getElementById('fp-static');
  if (!target) return;
  target.innerHTML = ''
    // 三层递进
    + '<div style="margin-bottom:48px">'
    + '  <h4 style="font-size:13px;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin:0 0 12px">识别机制</h4>'
    + '  <div style="display:flex;gap:24px">'
    + '    <div style="flex:1;border-top:2px solid #0f172a;padding-top:12px">'
    + '      <div style="font-size:12px;color:#94a3b8;margin-bottom:4px">Step 1</div>'
    + '      <div style="font-size:15px;font-weight:600;color:#0f172a">关键词匹配</div>'
    + '      <div style="font-size:13px;color:#64748b;line-height:1.7;margin-top:4px">检测表头特征词快速判定类型</div>'
    + '    </div>'
    + '    <div style="flex:1;border-top:2px solid #cbd5e1;padding-top:12px">'
    + '      <div style="font-size:12px;color:#94a3b8;margin-bottom:4px">Step 2</div>'
    + '      <div style="font-size:15px;font-weight:600;color:#0f172a">结构分析</div>'
    + '      <div style="font-size:13px;color:#64748b;line-height:1.7;margin-top:4px">列数+位置+表头组合模式确认</div>'
    + '    </div>'
    + '    <div style="flex:1;border-top:2px solid #cbd5e1;padding-top:12px">'
    + '      <div style="font-size:12px;color:#94a3b8;margin-bottom:4px">Step 3</div>'
    + '      <div style="font-size:15px;font-weight:600;color:#0f172a">数据推断兜底</div>'
    + '      <div style="font-size:13px;color:#64748b;line-height:1.7;margin-top:4px">读前200行按列角色判定，确保不丢数据</div>'
    + '    </div>'
    + '  </div>'
    + '</div>'
    // 34类指纹
    + '<div style="margin-bottom:24px">'
    + '  <h4 style="font-size:13px;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin:0 0 16px">文件指纹库 · 34 类</h4>'
    + '  <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:2px">'
    + fpFingerprints().map(function(item) {
        return '<div style="padding:6px 0;font-size:13px;color:#334155">'
          + '<span style="color:#0f172a;font-weight:500">' + item.icon + ' ' + item.name + '</span>'
          + '<span style="color:#94a3b8;font-size:12px;margin-left:6px">' + item.sig + '</span></div>';
      }).join('')
    + '  </div>'
    + '</div>'
    // 兼容策略
    + '<div style="padding:16px 0;border-top:1px solid #f1f5f9;border-bottom:1px solid #f1f5f9;margin-bottom:48px">'
    + '  <div style="font-size:13px;color:#64748b;line-height:1.8">'
    + '    <span style="font-weight:600;color:#0f172a">兼容策略</span> '
    + '    银行流水兼容5种日期列名 · 发票兼容多种购方命名 · 汇总行自动过滤 · 未知格式不放弃</div>'
    + '</div>';
}

// 34类文件指纹数据
function fpFingerprints() {
  return [
    {icon:'🏧',name:'银行流水',sig:'交易日期+对方户名+借贷金额'},
    {icon:'🧾',name:'销项发票',sig:'购方名称+金额+税率+税额'},
    {icon:'📥',name:'进项发票',sig:'销方名称+金额+税率+税额'},
    {icon:'📋',name:'通用发票',sig:'自动判定进销方向'},
    {icon:'💰',name:'工资表',sig:'姓名+本期收入+代扣社保'},
    {icon:'🛡️',name:'社保明细',sig:'姓名+社保基数+单位/个人'},
    {icon:'🏡',name:'公积金',sig:'姓名+公积金基数+缴存比例'},
    {icon:'📝',name:'记账凭证',sig:'凭证号+科目+借贷金额'},
    {icon:'📦',name:'进销存台账',sig:'品名+期初+入库+出库+期末'},
    {icon:'📊',name:'增值税申报表',sig:'销售额+销项税额+进项税额'},
    {icon:'📈',name:'企业所得税申报表',sig:'营业收入+利润总额+应纳税额'},
    {icon:'👤',name:'个税申报表',sig:'姓名+收入+应纳税所得额'},
    {icon:'📑',name:'科目余额表',sig:'科目编码+期初+本期+期末余额'},
    {icon:'💰',name:'利润表',sig:'营业收入+营业成本+利润总额'},
    {icon:'🏦',name:'资产负债表',sig:'资产合计+负债合计+所有者权益'},
    {icon:'💵',name:'现金流量表',sig:'经营+投资+筹资活动'},
    {icon:'📄',name:'合同文件',sig:'合同编号+签约方+金额+日期'},
    {icon:'🏢',name:'公司档案',sig:'工商登记/股东名册/章程'},
    {icon:'🔗',name:'关联交易',sig:'关联方+交易类型+金额+定价'},
    {icon:'🏭',name:'固定资产',sig:'资产名称+原值+折旧+净值'},
    {icon:'📜',name:'无形资产',sig:'专利/商标+摊销+净值'},
    {icon:'🤝',name:'应收账款',sig:'客户名称+欠款金额+账龄'},
    {icon:'🏗️',name:'应付账款',sig:'供应商名称+应付金额+账龄'},
    {icon:'💳',name:'预收预付',sig:'客户/供应商+预收/预付金额'},
    {icon:'📋',name:'费用明细',sig:'费用类型+金额+报销人'},
    {icon:'🚗',name:'差旅费',sig:'出差人+目的地+天数+金额'},
    {icon:'📋',name:'纳税记录',sig:'税种+所属期+计税金额+实缴'},
    {icon:'📄',name:'印花税',sig:'税目+计税金额+税率'},
    {icon:'🏭',name:'环保税',sig:'污染物+排放量+税额'},
    {icon:'🗂️',name:'通用表格',sig:'按数据结构反推'},
    {icon:'📋',name:'诊断追踪记录',sig:'系统解析决策日志'},
    {icon:'🔗',name:'关联数据',sig:'多文件交叉关联分析'},
    {icon:'📤',name:'导出数据',sig:'外部系统数据导出'},
    {icon:'🏷️',name:'其他格式',sig:'自动检测+数据推断'}
  ];
}

function statLine(label, value, color) {
  return '<div style="text-align:center;padding:0 24px;border-right:1px solid #f1f5f9">'
    + '<div style="font-size:32px;font-weight:700;color:' + color + ';line-height:1.2">' + value + '</div>'
    + '<div style="font-size:12px;color:#94a3b8;margin-top:2px">' + label + '</div></div>';
}

async function loadFileParsingData() {
  var target = document.getElementById('fp-analysis-result');
  if (!target) return;
  var cid = typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1;
  try {
    var resp = await fetch('/api/tax-risk-docs/last-analysis?company_id=' + cid);
    var data = await resp.json();
    if (!data.ok) {
      target.innerHTML = '<div style="text-align:center;padding:48px 0;color:#94a3b8;font-size:14px">暂无分析结果，请先运行一键分析</div>';
      return;
    }
    renderFileParsingResult(data.report);
  } catch (e) {
    target.innerHTML = '<div style="text-align:center;padding:48px 0;color:#94a3b8;font-size:14px">加载失败</div>';
  }
}

function renderFileParsingResult(report) {
  var target = document.getElementById('fp-analysis-result');
  if (!target) return;
  var frs = report.file_results || [];
  var plogs = report.pipeline_log || [];

  var parsed = frs.filter(function(f) { return f.type !== 'unknown' && !f.error; }).length;
  var failed = frs.filter(function(f) { return f.error; }).length;

  var html = ''
    // 薄分隔线
    + '<div style="height:1px;background:#f1f5f9;margin-bottom:32px"></div>'
    // 统计行
    + '<div style="display:flex;justify-content:center;margin-bottom:40px">'
    + statLine('文件', frs.length, '#0f172a')
    + statLine('已解析', parsed, '#059669')
    + statLine('未解析', failed, failed > 0 ? '#dc2626' : '#94a3b8')
    + statLine('日志', plogs.length, '#0f172a')
    + '</div>'
    // 文件列表
    + '<h4 style="font-size:13px;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin:0 0 16px">解析明细</h4>';

  if (frs.length === 0) {
    html += '<div style="color:#94a3b8;font-size:13px;padding:24px 0">无文件数据</div>';
  } else {
    html += '<table style="width:100%;border-collapse:collapse;font-size:13px">'
      + '<thead><tr style="border-bottom:2px solid #0f172a;text-align:left">'
      + '<th style="padding:8px 12px 8px 0;font-weight:600;color:#0f172a">#</th>'
      + '<th style="padding:8px 12px;font-weight:600;color:#0f172a">文件名</th>'
      + '<th style="padding:8px 12px;font-weight:600;color:#0f172a">类型</th>'
      + '<th style="padding:8px 12px;font-weight:600;color:#0f172a">条数</th>'
      + '<th style="padding:8px 0;font-weight:600;color:#0f172a"></th>'
      + '</tr></thead><tbody>';

    frs.forEach(function(fr, i) {
      var typeLabel = fr.type || '未知';
      var status = fr.error ? 'fail' : (fr.type === 'unknown' ? 'warn' : 'ok');
      var rowCount = '';
      if (fr.actions && fr.actions.length) {
        var m = (fr.actions.join(' ')).match(/(\d+)条/);
        if (m) rowCount = m[1];
      }
      var dot = status === 'fail' ? '●' : (status === 'warn' ? '●' : '●');
      var dotColor = status === 'fail' ? '#dc2626' : (status === 'warn' ? '#f59e0b' : '#22c55e');

      html += '<tr style="border-bottom:1px solid #f1f5f9">'
        + '<td style="padding:10px 12px 10px 0;color:#94a3b8">' + (i + 1) + '</td>'
        + '<td style="padding:10px 12px;color:#0f172a;max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + escHtml(fr.file) + '">' + escHtml(fr.file) + '</td>'
        + '<td style="padding:10px 12px;font-size:12px;color:#64748b">' + escHtml(typeLabel) + '</td>'
        + '<td style="padding:10px 12px;color:#64748b">' + (rowCount || '—') + '</td>'
        + '<td style="padding:10px 0;color:' + dotColor + ';font-size:10px">' + dot + '</td>'
        + '</tr>';
    });

    html += '</tbody></table>';
  }

  // 管线日志
  if (plogs.length > 0) {
    html += '<h4 style="font-size:13px;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin:40px 0 16px">管线日志</h4>';
    html += '<div style="background:#0f172a;border-radius:6px;padding:20px 24px;max-height:360px;overflow-y:auto;font-family:\'SF Mono\',\'Fira Code\',monospace;font-size:12px;line-height:2">';
    plogs.forEach(function(log, i) {
      var color = '#64748b';
      if (log.indexOf('异常') >= 0 || log.indexOf('失败') >= 0) color = '#fca5a5';
      else if (log.indexOf('完成') >= 0 || log.indexOf('成功') >= 0) color = '#86efac';
      else if (log.indexOf('发现') >= 0) color = '#fde68a';
      html += '<div style="color:' + color + '">[' + (i + 1) + '] ' + escHtml(log) + '</div>';
    });
    html += '</div>';
  }

  target.innerHTML = html;
}

// ==================== 页面2：域分析（极简风） ====================
function renderDomainAnalysisPage(container) {
  if (!container) return;
  window.currentModule = '域分析';
  container.innerHTML = ''
    + '<div style="max-width:960px;margin:0 auto;padding:40px 24px 80px">'
    + '  <div style="margin-bottom:48px">'
    + '    <h2 style="font-size:24px;font-weight:700;color:#0f172a;margin:0 0 6px">域分析</h2>'
    + '    <p style="font-size:14px;color:#94a3b8;margin:0">31个分析域 · 跨域关联推理 · 多源证据链串联</p>'
    + '  </div>'
    + renderDomainAnalysisStatic()
    + '<div id="da-analysis-result"></div>'
    + '</div>';
  loadDomainAnalysisData();
}

function renderDomainAnalysisStatic() {
  var domains = [
    {name:'进销存匹配分析', desc:'进销品名交叉映射、进销比检测。有进无销/有销无进触发制造业加工诊断。', category:'进销存'},
    {name:'供应商穿透分析', desc:'集中度、同城群集、名称异常检测。前3大占比>70%触发依赖预警。', category:'供应商'},
    {name:'多源交叉验证', desc:'资金流+发票流+货物流三源采购验证；收入+发票双源验证；合同+发票+付款三角验证。', category:'交叉验证'},
    {name:'资料完备度评估', desc:'15类稽查必查资料逐一检测，合同需求分层自动判定哪些供应商必须签合同。', category:'资料完备'},
    {name:'经营实质分析', desc:'基础经营费用检测+企业能力评估+发票与人员规模匹配。', category:'经营实质'},
    {name:'经营实质地理分析', desc:'供应商/客户/加工商地址三角验真+重物运输成本+跨省经营合理性。', category:'经营实质'},
    {name:'发票深度特征', desc:'开具时间分布、价格区间、金额尾数、连续性、顶额开票检测。', category:'发票'},
    {name:'发票实质性审计', desc:'五层审计——格式合规→价格合理性→加工真实性→投入产出逻辑→税额。', category:'发票'},
    {name:'发票生命周期', desc:'未认证占比、超期未认证、税率异常、类型分布、红冲作废追踪。', category:'发票'},
    {name:'合同比对分析', desc:'合同与发票/付款的对应关系验证，合同覆盖度+金额偏差检测。', category:'合同'},
    {name:'凭证科目异常', desc:'科目使用合规性、借贷方向、摘要规范性、异常科目组合检测。', category:'凭证'},
    {name:'凭证发票收入对比', desc:'主营业务收入vs销项发票金额vs银行入账三源对比，偏差>20%预警。', category:'凭证'},
    {name:'存货周转预警', desc:'周转率+库龄分析+库存结构合理性。入库>>出库→积压预警。', category:'存货'},
    {name:'税务缴纳一致性', desc:'银行税费支出vs发票推算应纳税额差异。', category:'税务'},
    {name:'工资社保比对', desc:'工资表vs社保明细交叉验证——基数匹配、人数一致、比例合规。', category:'薪酬'},
    {name:'收入时间线调查', desc:'凭证收入/开票收入/银行入账按月趋势对比。年末突击开票检测。', category:'收入'},
    {name:'供应商画像分析', desc:'行业/地域/注册资本综合分析。新注册零实缴→可疑交易方。', category:'供应商'},
    {name:'资金流向追踪', desc:'收款方/付款方分类。个人转账/关联方/税费/手续费。第三方支付占比预警。', category:'资金流'},
    {name:'人员与业务匹配', desc:'员工vs营收合理性、人均薪资vs行业均值、社保人数vs工资人数匹配。', category:'人员'},
    {name:'发票存货付款三角验证', desc:'进项发票vs存货入库vs银行付款三向验证——票货分离、虚开嫌疑。', category:'交叉验证'},
    {name:'红冲作废发票追踪', desc:'红冲率+作废率+时间模式+金额占比+集中度。', category:'发票'},
    {name:'利润现金流矛盾检测', desc:'账面利润vs经营现金流背离。利润正/现金流负→利润质量存疑。', category:'财务报表'},
    {name:'异常交易时间分析', desc:'非工作时间交易、特殊日期突击交易检测。', category:'资金流'},
    {name:'关联交易穿透检测', desc:'名称相似度+同法人+同注册地+同电话→关联交易未披露。', category:'关联交易'},
    {name:'资产折旧费用匹配', desc:'固定资产采购vs折旧匹配。有资产无折旧→利润虚增。', category:'资产'},
    {name:'增值税申报比对', desc:'销项税额/进项税额/应纳税额vs申报表。差异>1000元预警。', category:'税务'},
    {name:'上下游穿透分析', desc:'客户vs供应商关联。同一企业既是客户又是供应商→对倒开票嫌疑。', category:'交叉验证'},
    {name:'行业对标分析', desc:'66个行业基准——毛利率/税负率/进销比/人均营收/费用率五维对标。', category:'行业对标'},
    {name:'账务系统风险', desc:'有发票流水无凭证→账务缺失。账务不牢所有维度无法验证。', category:'账务'},
    {name:'规则全覆盖验证', desc:'312条规则逐条检查，数据不足标记为资料缺口，不作风险结论。', category:'规则引擎'},
    {name:'跨域关联推理', desc:'单点→多域印证→7条证据链。A域+B域+C域异常→多源交叉→闭环。', category:'证据链'},
    {name:'审计基础检查', desc:'数据完整性——科目平衡/凭证连续/日期连续/号码连续。', category:'审计'},
  ];

  // 分类颜色映射（仅文字色，无背景）
  var catColors = {
    '进销存':'#dc2626','供应商':'#f59e0b','交叉验证':'#7c3aed','资料完备':'#2563eb',
    '经营实质':'#059669','发票':'#0891b2','合同':'#0f172a','凭证':'#b45309',
    '存货':'#92400e','税务':'#065f46','薪酬':'#d97706','收入':'#4f46e5',
    '资金流':'#dc2626','人员':'#6d28d9','财务报表':'#1e40af','关联交易':'#0369a1',
    '资产':'#047857','行业对标':'#6366f1','账务':'#475569','规则引擎':'#0f172a',
    '证据链':'#7c3aed','审计':'#64748b'
  };

  return ''
    // 说明
    + '<div style="margin-bottom:40px;font-size:13px;color:#64748b;line-height:1.8">'
    + '域分析是稽查分析的核心工作台。每个域是独立分析维度，由专门的域分析函数驱动。域之间不孤立——跨域关联推理将单域发现串联为多源交叉证据链。'
    + '</div>'
    // 分类小标题+域列表
    + (function() {
      var html = '';
      var seenCats = {};
      domains.forEach(function(d) {
        if (!seenCats[d.category]) {
          seenCats[d.category] = true;
          html += '<h4 style="font-size:13px;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin:36px 0 12px">' + d.category + '</h4>';
        }
        var c = catColors[d.category] || '#64748b';
        html += '<div style="display:flex;align-items:baseline;padding:8px 0;border-bottom:1px solid #f8fafc;font-size:13px">'
          + '<span style="font-weight:600;color:' + c + ';min-width:140px;margin-right:12px">' + escHtml(d.name) + '</span>'
          + '<span style="color:#94a3b8;font-size:13px;line-height:1.6">' + escHtml(d.desc) + '</span>'
          + '</div>';
      });
      return html;
    })()
    // 域间关系
    + '<div style="margin-top:36px;padding:16px 0;border-top:1px solid #f1f5f9;font-size:13px;color:#94a3b8;line-height:1.8">'
    + '<span style="font-weight:600;color:#0f172a">域间关系</span> '
    + '资料完备度决定置信度 → 经营实质提供企业画像 → 多源交叉串联单域发现 → 跨域关联输出最终证据链'
    + '</div>';
}

function statLine(label, value, color) {
  return '<div style="text-align:center;padding:0 24px;border-right:1px solid #f1f5f9">'
    + '<div style="font-size:32px;font-weight:700;color:' + color + ';line-height:1.2">' + value + '</div>'
    + '<div style="font-size:12px;color:#94a3b8;margin-top:2px">' + label + '</div></div>';
}

async function loadDomainAnalysisData() {
  var target = document.getElementById('da-analysis-result');
  if (!target) return;
  var cid = typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1;
  try {
    var resp = await fetch('/api/tax-risk-docs/last-analysis?company_id=' + cid);
    var data = await resp.json();
    if (!data.ok) {
      target.innerHTML = '<div style="text-align:center;padding:48px 0;color:#94a3b8;font-size:14px">暂无分析结果，请先运行一键分析</div>';
      return;
    }
    renderDomainAnalysisResult(data.report);
  } catch (e) {
    target.innerHTML = '<div style="text-align:center;padding:48px 0;color:#94a3b8;font-size:14px">加载失败</div>';
  }
}

function renderDomainAnalysisResult(report) {
  var target = document.getElementById('da-analysis-result');
  if (!target) return;
  var ds = report.domain_summary || [];
  var allF = report.all_findings || [];

  var domainMap = {};
  ds.forEach(function(d) {
    domainMap[d.name] = { count: d.count, high: d.high, mid: d.mid, findings: d.findings || [] };
  });

  var domainNames = Object.keys(domainMap).sort(function(a, b) {
    return (domainMap[b].high * 2 + domainMap[b].mid) - (domainMap[a].high * 2 + domainMap[a].mid);
  });

  var totalDomains = domainNames.length;
  var triggeredDomains = domainNames.filter(function(n) { return domainMap[n].count > 0; }).length;
  var highTotal = allF.filter(function(f) { return f.level === '高风险'; }).length;

  var html = ''
    // 分隔线
    + '<div style="height:1px;background:#f1f5f9;margin-bottom:32px"></div>'
    // 统计行
    + '<div style="display:flex;justify-content:center;margin-bottom:40px">'
    + statLine('分析域', totalDomains, '#0f172a')
    + statLine('已触发', triggeredDomains, '#7c3aed')
    + statLine('发现', allF.length, '#0f172a')
    + statLine('高风险', highTotal, highTotal > 0 ? '#dc2626' : '#94a3b8')
    + '</div>'
    // 域列表
    + '<h4 style="font-size:13px;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin:0 0 16px">域概览</h4>';

  if (domainNames.length === 0) {
    html += '<div style="color:#94a3b8;font-size:13px;padding:24px 0">无域分析数据</div>';
  } else {
    domainNames.forEach(function(name, di) {
      var d = domainMap[name];
      var hasFindings = d.count > 0;
      var dot = d.high > 0 ? '●' : (d.mid > 0 ? '●' : (hasFindings ? '●' : '○'));
      var dotColor = d.high > 0 ? '#dc2626' : (d.mid > 0 ? '#f59e0b' : (hasFindings ? '#22c55e' : '#cbd5e1'));

      html += '<div style="border-bottom:1px solid #f8fafc;padding:12px 0;cursor:' + (hasFindings ? 'pointer' : 'default') + '" onclick="' + (hasFindings ? 'toggleDomainDetail(' + di + ')' : '') + '">'
        + '<div style="display:flex;align-items:center;justify-content:space-between">'
        + '<div style="display:flex;align-items:center;gap:10px">'
        + '<span style="color:' + dotColor + ';font-size:10px">' + dot + '</span>'
        + '<span style="font-size:14px;font-weight:600;color:#0f172a">' + escHtml(name) + '</span>'
        + '</div>'
        + '<div style="display:flex;gap:16px;font-size:12px;color:#94a3b8">'
        + '<span>发现 <b style="color:#0f172a">' + d.count + '</b></span>'
        + '<span style="color:#dc2626">' + d.high + '</span>'
        + '<span style="color:#f59e0b">' + d.mid + '</span>'
        + (hasFindings ? '<span style="color:#94a3b8;font-size:11px">▸</span>' : '')
        + '</div>'
        + '</div>';

      // 展开的发现详情
      if (hasFindings) {
        html += '<div id="dd-' + di + '" style="display:none;margin-top:12px;padding-left:20px">';
        d.findings.slice(0, 10).forEach(function(f) {
          var lvlColor = f.level === '高风险' ? '#dc2626' : (f.level === '中风险' ? '#f59e0b' : '#22c55e');
          html += '<div style="padding:8px 0;border-bottom:1px solid #f8fafc;font-size:13px;line-height:1.7">'
            + '<span style="font-weight:600;color:#0f172a">' + escHtml((f.type || '').substring(0, 40)) + '</span>'
            + '<span style="margin-left:8px;font-size:11px;color:' + lvlColor + '">' + (f.level || '') + '</span>'
            + '<div style="color:#64748b;margin-top:2px">' + escHtml((f.detail || '').substring(0, 160)) + '</div>'
            + '</div>';
        });
        if (d.count > 10) html += '<div style="padding:8px 0;font-size:12px;color:#94a3b8">... 还有 ' + (d.count - 10) + ' 条</div>';
        html += '</div>';
      }

      html += '</div>';
    });
  }

  target.innerHTML = html;
}

// ==================== 页面3：跨域证据链 ====================
function renderCrossDomainEvidencePage(container) {
  if (!container) return;
  window.currentModule = '跨域证据链';

  var hasCache = window._allCrossChains && window._allCrossChains.length > 0;

  container.innerHTML = '<div style="max-width:960px;margin:0 auto;padding:40px 24px 80px">'
    + '<div>'
    + '<h2 style="font-size:24px;font-weight:700;color:#0f172a;margin:0 0 6px">跨域证据链</h2>'
    + '<p style="font-size:14px;color:#94a3b8;margin:0">系统最高价值的输出——7条证据链各自由多源数据交叉验证形成，只有≥2个维度同时命中才形成有效证据链</p>'
    + '</div>'
    + '<div id="cde-static"></div>'
    + '<div id="cde-dynamic"></div>'
    + '</div>';

  if (hasCache) {
    renderCrossDomainStaticContent(window._allCrossChains);
    loadCrossDomainDynamic();
  } else {
    loadCrossDomainStatic();
    loadCrossDomainDynamic();
  }
}

function loadCrossDomainStatic() {
  var target = document.getElementById('cde-static');
  fetch('/static/cross_domain_evidence.json?_t=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(chains) {
      window._allCrossChains = chains;
      renderCrossDomainStaticContent(chains);
    })
    .catch(function() {
      if (target) target.innerHTML = '<div style="padding:40px 0;font-size:13px;color:#94a3b8">跨域证据链定义加载失败</div>';
    });
}

function renderCrossDomainStaticContent(chains) {
  var target = document.getElementById('cde-static');
  if (!target) return;
  var highCount = chains.filter(function(c) { return c.level === '高风险'; }).length;
  var totalDim = chains.reduce(function(s, c) { return s + c.dimensions.length; }, 0);

  var html = '<div style="display:flex;margin-bottom:24px;margin-top:24px;border-bottom:1px solid #f1f5f9;padding-bottom:16px">'
    + '<div style="flex:1;text-align:center;padding:12px 16px;border-right:1px solid #f1f5f9"><div style="font-size:28px;font-weight:700;color:#0f172a">' + chains.length + '</div><div style="font-size:13px;color:#94a3b8;margin-top:2px">证据链总数</div></div>'
    + '<div style="flex:1;text-align:center;padding:12px 16px;border-right:1px solid #f1f5f9"><div style="font-size:28px;font-weight:700;color:#0f172a">' + highCount + '</div><div style="font-size:13px;color:#94a3b8;margin-top:2px">高风险链</div></div>'
    + '<div id="cde-triggered-count" style="flex:1;text-align:center;padding:12px 16px;border-right:1px solid #f1f5f9"><div style="font-size:28px;font-weight:700;color:#0f172a">—</div><div style="font-size:13px;color:#94a3b8;margin-top:2px">本次触发</div></div>'
    + '<div style="flex:1;text-align:center;padding:12px 16px"><div style="font-size:28px;font-weight:700;color:#0f172a">' + totalDim + '</div><div style="font-size:13px;color:#94a3b8;margin-top:2px">总维度数</div></div>'
    + '</div>';

  chains.forEach(function(c, ci) {
    html += '<div id="cde-chain-' + ci + '" style="padding:16px 0;border-bottom:1px solid #f1f5f9">'
      + '<div style="font-size:15px;font-weight:600;color:#0f172a;margin-bottom:6px">' + _escStatic(c.name)
      + ' <span style="font-size:13px;color:' + (c.level === '高风险' ? '#dc2626' : '#f59e0b') + ';font-weight:400">' + _escStatic(c.level) + '</span>'
      + ' <span style="font-size:13px;color:#94a3b8">' + _escStatic(c.sub_topic) + '</span>'
      + ' <span id="cde-triggered-' + ci + '"></span>'
      + ' <span style="font-size:13px;color:#94a3b8">需≥' + c.min_evidence + '条证据</span>'
      + '</div>'
      + '<div style="font-size:13px;color:#64748b;line-height:1.8">' + _escStatic(c.description) + '</div>';

    html += '<div style="font-size:13px;color:#64748b;margin-top:6px">维度：';
    c.dimensions.forEach(function(d, di) {
      html += (di > 0 ? ' · ' : '') + _escStatic(d.code) + ' ' + _escStatic(d.source);
    });
    html += '</div>';

    if (c.how_found) html += '<div style="font-size:13px;color:#64748b;margin-top:4px">溯源：' + _escStatic(c.how_found.substring(0,200)) + '</div>';
    if (c.tax_impact) html += '<div style="font-size:13px;color:#64748b;margin-top:4px">纳税影响：' + _escStatic(c.tax_impact.substring(0,200)) + '</div>';
    if (c.policy_ref) html += '<div style="font-size:13px;color:#64748b;margin-top:4px">法律依据：' + _escStatic(c.policy_ref.substring(0,200)) + '</div>';
    if (c.suggestion) html += '<div style="font-size:13px;color:#64748b;margin-top:4px">建议：' + _escStatic(c.suggestion.substring(0,200)) + '</div>';

    html += '</div>';
  });

  html += '<div style="padding:14px 0;font-size:13px;color:#94a3b8;line-height:1.8">证据链≠结论：每条证据链需要≥2个维度同时命中才能触发。单维度触发视为孤证，不形成证据链闭环。</div>';

  target.innerHTML = html;
}

function loadCrossDomainDynamic() {
  var target = document.getElementById('cde-dynamic');
  if (!target) return;

  var cid = typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1;
  fetch('/api/tax-risk-docs/last-analysis?company_id=' + cid)
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (!data.ok) {
        target.innerHTML = '<div style="text-align:center;padding:20px;color:#94a3b8;margin-top:20px">⚠️ 暂无分析结果，请先运行一键分析以获取动态证据链数据</div>';
        return;
      }
      renderCrossDomainDynamic(data.report);
    })
    .catch(function(e) {
      target.innerHTML = '<div style="text-align:center;padding:20px;color:#94a3b8;margin-top:20px">动态数据加载失败: ' + e.message + '</div>';
    });
}

function renderCrossDomainDynamic(report) {
  var target = document.getElementById('cde-dynamic');
  if (!target) return;
  var domainSummary = report.domain_summary || [];
  var comprehensive = report.comprehensive || {};

  var crossDomainFindings = [];
  domainSummary.forEach(function(ds) {
    if (ds.name && ds.name.indexOf('跨域关联推理') >= 0) {
      crossDomainFindings = ds.findings || [];
    }
  });

  var evidenceFindings = allF.filter(function(f) {
    var t = f.type || '';
    return t.indexOf('证据链') >= 0 || t.indexOf('隐匿收入') >= 0 || t.indexOf('虚开发票') >= 0 || t.indexOf('无实质经营') >= 0 || t.indexOf('会计基础') >= 0 || t.indexOf('资金链') >= 0 || t.indexOf('利润现金流') >= 0 || t.indexOf('发票异常') >= 0;
  });

  var allEvidence = [];
  var seen = {};
  crossDomainFindings.forEach(function(f) {
    var key = f.type || '';
    if (!seen[key]) { seen[key] = true; allEvidence.push(f); }
  });
  evidenceFindings.forEach(function(f) {
    var key = f.type || '';
    if (!seen[key]) { seen[key] = true; allEvidence.push(f); }
  });

  var closures = comprehensive.evidence_closures || [];
  var closedCount = comprehensive.closed_chain_count || 0;
  var triggeredChains = comprehensive.triggered_chains || [];
  var chainExecution = comprehensive.chain_execution || [];

  // 更新"本次触发"数
  var tcEl = document.getElementById('cde-triggered-count');
  if (tcEl) {
    var tcc = tcEl.querySelector('div');
    if (tcc) tcc.textContent = triggeredChains.length;
  }

  // 更新各链触发badge
  var allCC = window._allCrossChains || [];
  allCC.forEach(function(c, ci) {
    var isTriggered = c.trigger_keywords && triggeredChains.some(function(t) {
      return c.trigger_keywords.some(function(kw) { return t.indexOf(kw) >= 0; });
    });
    var badgeEl = document.getElementById('cde-triggered-' + ci);
    if (badgeEl) {
      badgeEl.innerHTML = triggeredChains.length > 0
        ? (isTriggered ? '<span style="color:#dc2626;font-weight:600"> 已触发</span>' : '<span style="color:#94a3b8"> 未触发</span>')
        : '';
    }
  });

  var html = '<div style="padding:20px 0;border-top:1px solid #f1f5f9;margin-top:20px">'
    + '<div style="font-size:15px;font-weight:600;color:#0f172a;margin-bottom:12px">本次动态证据链结果</div>'
    + '<div style="font-size:13px;color:#64748b;line-height:2">'
    + '跨域证据链 ' + allEvidence.length + ' · 已闭环 ' + closedCount + ' · 触发线索链 ' + chainExecution.length + ' · 含规则ID链 ' + triggeredChains.length
    + '</div>';

  if (closures.length > 0) {
    html += '<div style="margin-top:16px;font-size:15px;font-weight:600;color:#0f172a;margin-bottom:8px">证据链闭环检测</div>';
    closures.forEach(function(ec) {
      html += '<div style="padding:12px 0;border-bottom:1px solid #f1f5f9">'
        + '<span style="font-size:14px;font-weight:600;color:#0f172a">' + escHtml(ec.chain_name) + '</span>'
        + ' <span style="font-size:13px;color:' + (ec.closed ? '#dc2626' : '#f59e0b') + '">' + (ec.closed ? '已闭环' : '未闭环') + ' ' + ec.ratio + '%</span>'
        + '<div style="font-size:13px;color:#94a3b8">触发 ' + ec.triggered_steps + '/' + ec.total_steps + ' 条规则</div>'
        + '</div>';
    });
  }

  if (allEvidence.length > 0) {
    html += '<div style="margin-top:20px;font-size:15px;font-weight:600;color:#0f172a;margin-bottom:8px">跨域关联推理详情</div>';
    allEvidence.forEach(function(f) {
      html += '<div style="padding:12px 0;border-bottom:1px solid #f1f5f9">'
        + '<div style="font-size:14px;font-weight:600;color:#0f172a">' + escHtml(f.type || '') + '</div>';
      if (f.description) html += '<div style="font-size:13px;color:#64748b;line-height:1.8;margin-top:4px">' + escHtml(f.description.substring(0,300)) + '</div>';
      if (f.how_found) html += '<div style="font-size:13px;color:#94a3b8;margin-top:4px">溯源：' + escHtml(f.how_found.substring(0,150)) + '</div>';
      if (f.tax_impact) html += '<div style="font-size:13px;color:#94a3b8;margin-top:4px">纳税影响：' + escHtml(f.tax_impact.substring(0,150)) + '</div>';
      html += '</div>';
    });
  }

  if (chainExecution.length > 0) {
    html += '<div style="margin-top:20px;font-size:15px;font-weight:600;color:#0f172a;margin-bottom:8px">触发线索链 TOP' + Math.min(20, chainExecution.length) + '</div>';
    chainExecution.slice(0, 20).forEach(function(ce) {
      var ratioColor = ce.triggered_ratio >= 80 ? '#dc2626' : (ce.triggered_ratio >= 50 ? '#f59e0b' : '#059669');
      html += '<div style="padding:8px 0;border-bottom:1px solid #f1f5f9;font-size:13px">'
        + '<span style="color:#0f172a">' + escHtml(ce.chain_name) + '</span>'
        + ' <span style="color:#64748b">' + ce.triggered_steps + '/' + ce.total_steps + '</span>'
        + ' <span style="color:' + ratioColor + ';font-weight:600">' + ce.triggered_ratio + '%</span>'
        + '</div>';
    });
  }

  html += '</div>';
  target.innerHTML = html;
}


// ==================== 全局变量（供线索链/证据链页面共享） ====================
var _allChains = [];
var _chainDynamic = null;
var _allClueChains = [];
var _allEvidenceChains = [];

// ==================== 页面：线索链 ====================
function renderChainsPage(container) {
  if (!container) return;
  window.currentModule = '线索链';

  var hasCache = _allClueChains && _allClueChains.length > 0;
  var cats = {};
  if (hasCache) _allClueChains.forEach(function(c) { var p = (c.name || '').split('-')[0]; if (p) cats[p] = true; });
  var catKeys = hasCache ? Object.keys(cats).sort() : [];

  container.innerHTML = '<div style="max-width:960px;margin:0 auto;padding:40px 24px 80px">'
    + '<div>'
    + '<h2 style="font-size:24px;font-weight:700;color:#0f172a;margin:0 0 6px">线索链列表</h2>'
    + '<p style="font-size:14px;color:#94a3b8;margin:0">稽查调查路径，每条链含若干调查步骤，触发率=已触发步骤/总步骤</p>'
    + '</div>'
    + '<div style="display:flex;gap:12px;align-items:center;margin-bottom:24px;padding-bottom:16px;border-bottom:1px solid #f1f5f9;margin-top:24px">'
    + '<input type="text" id="chain-search-input" placeholder="搜索线索链..." ' + (hasCache ? '' : 'disabled') + ' oninput="renderChainsList(_allClueChains)" style="flex:1;border:none;outline:none;font-size:14px;color:#0f172a;padding:8px 0;background:transparent">'
    + '<select id="chain-filter-cat" ' + (hasCache ? '' : 'disabled') + ' onchange="renderChainsList(_allClueChains)" style="border:none;font-size:13px;color:#64748b;padding:6px 8px;background:transparent;cursor:pointer"><option value="">全部分类</option>'
    + catKeys.map(function(k) { return '<option value="'+k+'">'+k+'</option>'; }).join('')
    + '</select>'
    + '<select id="chain-filter-level" ' + (hasCache ? '' : 'disabled') + ' onchange="renderChainsList(_allClueChains)" style="border:none;font-size:13px;color:#64748b;padding:6px 8px;background:transparent;cursor:pointer"><option value="">全部等级</option><option value="高风险">含高风险环节</option><option value="中风险">含中风险环节</option></select>'
    + '<span style="font-size:13px;color:#94a3b8"><strong id="chain-header-count">' + (hasCache ? _allClueChains.length : '...') + '</strong> 条</span>'
    + '</div>'
    + '<div id="chains-body"></div></div>';

  if (hasCache) {
    renderChainsList(_allClueChains, catKeys);
  } else {
    loadChainsData();
  }
}

async function loadChainsData() {
  var target = document.getElementById('chains-body');
  try {
    var resp = await fetch('/static/audit_chains.json?_t=' + Date.now());
    var data = await resp.json();
    _allChains = data.chains || [];
    var clueChains = _allChains.filter(function(c) { return c.chain_type === '线索链' || !c.chain_type; });
    if (!clueChains.length) clueChains = _allChains.slice(0, 386);

    // 加载动态触发状态
    await loadChainDynamicStatus();

    // 提取分类
    var cats = {};
    clueChains.forEach(function(c) { var p = (c.name || '').split('-')[0]; if (p) cats[p] = true; });
    var catKeys = Object.keys(cats).sort();

    _allClueChains = clueChains;
    renderChainsList(clueChains, catKeys);
  } catch (e) {
    if (target) target.innerHTML = '<div style="text-align:center;padding:20px;color:#dc2626">加载失败: ' + e.message + '</div>';
  }
}

async function loadChainDynamicStatus() {
  try {
    var cid = typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1;
    var resp = await fetch('/api/tax-risk-docs/last-analysis?company_id=' + cid);
    var data = await resp.json();
    if (data.ok && data.report) {
      var comp = data.report.comprehensive || {};
      _chainDynamic = {
        chain_execution: comp.chain_execution || [],
        evidence_closures: comp.evidence_closures || [],
        closed_count: comp.closed_chain_count || 0,
        triggered_count: comp.chain_triggered_count || 0
      };
    } else {
      _chainDynamic = { chain_execution: [], evidence_closures: [], closed_count: 0, triggered_count: 0 };
    }
  } catch(e) { _chainDynamic = { chain_execution: [], evidence_closures: [], closed_count: 0, triggered_count: 0 }; }
}

function renderChainsList(chains, catKeys) {
  var target = document.getElementById('chains-body');
  if (!target) return;

  var q = (document.getElementById('chain-search-input')?.value || '').toLowerCase();
  var cat = document.getElementById('chain-filter-cat')?.value || '';
  var lvl = document.getElementById('chain-filter-level')?.value || '';

  var filtered = chains.filter(function(c) {
    if (q && (c.name||'').toLowerCase().indexOf(q) === -1) return false;
    if (cat && !(c.name||'').startsWith(cat)) return false;
    if (lvl === '高风险') {
      var hasHigh = false;
      (c.investigation_path||[]).forEach(function(s) { if (s.level==='高风险') hasHigh=true; });
      if (!hasHigh) return false;
    }
    if (lvl === '中风险') {
      var hasMid = false;
      (c.investigation_path||[]).forEach(function(s) { if (s.level==='中风险') hasMid=true; });
      if (!hasMid) return false;
    }
    return true;
  });

  var execMap = {};
  if (_chainDynamic && _chainDynamic.chain_execution) {
    _chainDynamic.chain_execution.forEach(function(ce) { execMap[ce.chain_name] = ce; });
  }
  var hasDynamic = Object.keys(execMap).length > 0;

  var html = '';
  if (!filtered.length) {
    html = '<div style="text-align:center;padding:40px;color:#94a3b8">无匹配线索链</div>';
  } else {
    filtered.forEach(function(c, ci) {
      var exec = execMap[c.name];
      var triggeredSteps = exec ? exec.triggered_steps : 0;
      var totalSteps = exec ? exec.total_steps : (c.steps ? c.steps.length : (c.total_steps || 0));
      var ratio = exec ? exec.triggered_ratio : 0;

      var badge = '';
      if (exec && exec.triggered_steps > 0) {
        badge = ' <span style="color:' + (ratio >= 60 ? '#dc2626' : '#059669') + ';font-size:13px;font-weight:600">' + triggeredSteps + '/' + totalSteps + ' (' + ratio + '%)</span>';
      }

      html += '<div style="padding:14px 0;border-bottom:1px solid #f1f5f9">'
        + '<div style="font-size:15px;font-weight:600;color:#0f172a;margin-bottom:6px">' + escHtml(c.name) + badge + '</div>'
        + '<div style="font-size:13px;color:#64748b;line-height:1.8">';

      (c.investigation_path||[]).forEach(function(s, idx) {
        var levelTag = s.level==='高风险' ? '<span style="color:#dc2626">[高]</span>' : (s.level==='中风险' ? '<span style="color:#f59e0b">[中]</span>' : '<span style="color:#94a3b8">[低]</span>');
        html += (idx > 0 ? ' → ' : '') + levelTag + ' ' + escHtml(s.step||s.rule_item||'');
      });

      html += '</div></div>';
    });
  }

  target.innerHTML = html;

  var hc = document.getElementById('chain-header-count');
  if (hc) hc.textContent = chains.length + (hasDynamic && _chainDynamic && _chainDynamic.triggered_count ? ' (' + _chainDynamic.triggered_count + '触发)' : '');
}

function filterChainsList() {
  if (_allClueChains.length) renderChainsList(_allClueChains, []);
}

// ==================== 页面：证据链 ====================
function renderEvidencePage(container) {
  if (!container) return;
  window.currentModule = '证据链';

  var hasCache = _allEvidenceChains && _allEvidenceChains.length > 0;

  container.innerHTML = '<div style="max-width:960px;margin:0 auto;padding:40px 24px 80px">'
    + '<div>'
    + '<h2 style="font-size:24px;font-weight:700;color:#0f172a;margin:0 0 6px">证据链列表</h2>'
    + '<p style="font-size:14px;color:#94a3b8;margin:0">含规则ID+处罚依据，每条证据链需≥3条线索链触发+≥2域交叉验证形成闭环</p>'
    + '</div>'
    + '<div style="display:flex;gap:12px;align-items:center;margin-bottom:24px;padding-bottom:16px;border-bottom:1px solid #f1f5f9;margin-top:24px">'
    + '<input type="text" id="evidence-search-input" placeholder="搜索证据链..." ' + (hasCache ? '' : 'disabled') + ' oninput="renderEvidenceList(_allEvidenceChains)" style="flex:1;border:none;outline:none;font-size:14px;color:#0f172a;padding:8px 0;background:transparent">'
    + '<select id="evidence-filter-cat" ' + (hasCache ? '' : 'disabled') + ' onchange="renderEvidenceList(_allEvidenceChains)" style="border:none;font-size:13px;color:#64748b;padding:6px 8px;background:transparent;cursor:pointer"><option value="">全部分类</option></select>'
    + '<select id="evidence-filter-level" ' + (hasCache ? '' : 'disabled') + ' onchange="renderEvidenceList(_allEvidenceChains)" style="border:none;font-size:13px;color:#64748b;padding:6px 8px;background:transparent;cursor:pointer"><option value="">全部等级</option><option value="高风险">高风险</option><option value="中风险">中风险</option></select>'
    + '<span style="font-size:13px;color:#94a3b8"><strong>' + (hasCache ? _allEvidenceChains.length : '...') + '</strong> 条</span>'
    + '</div>'
    + '<div id="evidence-body"></div></div>';

  if (hasCache) {
    renderEvidenceList(_allEvidenceChains);
  } else {
    loadEvidenceData();
  }
}

async function loadEvidenceData() {
  var target = document.getElementById('evidence-body');
  try {
    var resp = await fetch('/static/audit_chains.json?_t=' + Date.now());
    var data = await resp.json();
    _allChains = data.chains || [];
    var evChains = _allChains.filter(function(c) { return c.chain_type === '证据链'; });
    if (!evChains.length) evChains = _allChains.slice(386, 386 + 735);

    // 确保动态状态已加载
    if (!_chainDynamic) await loadChainDynamicStatus();

    _allEvidenceChains = evChains;
    renderEvidenceList(evChains);
  } catch (e) {
    if (target) target.innerHTML = '<div style="text-align:center;padding:20px;color:#dc2626">加载失败: ' + e.message + '</div>';
  }
}

function renderEvidenceList(chains) {
  var target = document.getElementById('evidence-body');
  if (!target) return;

  var q = (document.getElementById('evidence-search-input')?.value || '').toLowerCase();
  var cat = document.getElementById('evidence-filter-cat')?.value || '';
  var lvl = document.getElementById('evidence-filter-level')?.value || '';

  var filtered = chains.filter(function(c) {
    if (q && (c.name||'').toLowerCase().indexOf(q) === -1) {
      var found = false;
      (c.investigation_path||[]).forEach(function(s) {
        if ((s.rule_item||'').toLowerCase().indexOf(q) !== -1) found = true;
        if ((s.step||'').toLowerCase().indexOf(q) !== -1) found = true;
      });
      if (!found) return false;
    }
    if (cat && !(c.name||'').startsWith(cat)) return false;
    if (lvl) {
      var hasLevel = false;
      (c.investigation_path||[]).forEach(function(s) { if (s.level === lvl) hasLevel = true; });
      if (!hasLevel) return false;
    }
    return true;
  });

  var evExecMap = {};
  if (_chainDynamic && _chainDynamic.evidence_closures) {
    _chainDynamic.evidence_closures.forEach(function(ec) { evExecMap[ec.chain_name] = ec; });
  }

  var html = '';
  if (!filtered.length) {
    html = '<div style="text-align:center;padding:40px;color:#94a3b8">无匹配证据链</div>';
  } else {
    filtered.forEach(function(c) {
      var evExec = evExecMap[c.name];
      var badge = '';
      if (evExec) {
        badge = ' <span style="color:' + (evExec.closed ? '#dc2626' : '#f59e0b') + ';font-size:13px;font-weight:600">' + (evExec.closed ? '已闭环' : '未闭环') + ' ' + evExec.ratio + '%</span>';
      }

      html += '<div style="padding:16px 0;border-bottom:1px solid #f1f5f9">'
        + '<div style="font-size:15px;font-weight:600;color:#0f172a;margin-bottom:8px">' + escHtml(c.name) + badge + '</div>';

      (c.investigation_path||[]).forEach(function(s) {
        var levelTag = s.level==='高风险' ? '<span style="color:#dc2626">[高]</span>' : (s.level==='中风险' ? '<span style="color:#f59e0b">[中]</span>' : '<span style="color:#94a3b8">[低]</span>');
        html += '<div style="font-size:13px;color:#64748b;line-height:1.8;margin-bottom:6px;padding-left:16px">'
          + '<span style="color:#94a3b8;font-size:12px">R' + (s.rule_id||'') + '</span> '
          + levelTag + ' <b style="color:#0f172a">' + escHtml(s.rule_item||s.step||'') + '</b>';
        if (s.detail) html += '<br><span style="color:#64748b">' + escHtml(s.detail.substring(0,150)) + '</span>';
        if (s.policy_ref) html += '<br><span style="color:#94a3b8;font-size:12px">依据：' + escHtml(s.policy_ref.substring(0,80)) + '</span>';
        html += '</div>';
      });

      var rCount = c.covered_rule_count || (c.investigation_path||[]).length;
      var qScore = c.quality_score || 0;
      html += '<div style="font-size:13px;color:#94a3b8;margin-top:6px">覆盖规则 ' + rCount + ' 条';
      if (c.related_chain_count > 0) html += ' · 关联链 ' + c.related_chain_count + ' 条';
      if (qScore) html += ' · 质量 ' + qScore + ' 分';
      html += '</div>';

      html += '</div>';
    });
  }

  target.innerHTML = html;
  window._allEvidenceChains = chains;
}

function filterEvidenceList() {
  if (window._allEvidenceChains) renderEvidenceList(window._allEvidenceChains);
}

// ==================== 页面：一键分析 ====================
function renderAnalyzePage(container) {
  if (!container) return;
  window.currentModule = '一键分析';
  container.innerHTML = '<div style="max-width:960px;margin:0 auto;padding:40px 24px 80px">'
    + '<div>'
    + '<h2 style="font-size:24px;font-weight:700;color:#0f172a;margin:0 0 6px">一键分析概览</h2>'
    + '<p style="font-size:14px;color:#94a3b8;margin:0">方法论驱动稽查引擎——点击"运行一键分析"启动完整稽查流程</p>'
    + '</div>'
    + '<div id="analyze-body"></div>'
    + '</div>';
  loadAnalyzeOverview();
}

async function loadAnalyzeOverview() {
  var target = document.getElementById('analyze-body');
  var steps = [
    { title: '① 资料扫描与类型识别', desc: '34类文件指纹 + 三层递进识别（关键词→结构分析→数据推断）。自动判定发票方向。诊断追踪系统记录完整决策链路。' },
    { title: '② 目标实体识别', desc: '进项购买方 ∩ 销项销售方 → 自动确定被查单位。66个行业分类（加权投票制）。企业类型自动判定（生产型/服务型/贸易型）。' },
    { title: '③ 资料情报提取 + 数据分析', desc: '银行流水深度分析：收款构成+收款方TOP10。联网核查工商登记信息。进销存比对：商品明细匹配+进销比+毛利率。供应商穿透：集中度+群集+双向交易。发票深度审计：五层检查(合规/单价/加工费/合理性/进销映射→BOM)。' },
    { title: '④ 规则引擎 + 链驱动检查', desc: '1503条规则逐条匹配 + 真实数据验证。386条线索链驱动：定量阈值验证。735条证据链闭环：≥3条触发+≥2域交叉验证。方法论过滤器：剔除97%噪声。' },
    { title: '⑤ 方法论噪声过滤器', desc: '硬删除：禁止词40+。条件过滤：无资料→对应结论全删。行业匹配：不报非本行业发现。去重+正常结论排除+模板僵尸检测。实测1554→24条。' },
    { title: '⑥ 行业对标 + 申报比对', desc: '66行业基准值自动对标（毛利率/税负率/进销比/人均营收）。申报表vs发票实际数据比对。无申报表→标记为资料缺口，不臆测。' },
    { title: '⑦ 正式稽查报告输出', desc: '国家税务总局呈报格式。已查实问题+需进一步核实问题，两级分类。稽查人员口吻：查证过程/问题定性/法律依据。' },
  ];

  var html = '';
  steps.forEach(function(s) {
    html += '<div style="padding:14px 0;border-bottom:1px solid #f1f5f9">'
      + '<div style="font-size:15px;font-weight:600;color:#0f172a;margin-bottom:4px">' + s.title + '</div>'
      + '<div style="font-size:13px;color:#64748b;line-height:1.8">' + s.desc + '</div>'
      + '</div>';
  });

  html += '<div style="padding:14px 0;font-size:13px;color:#94a3b8">'
    + '1503 条规则 · 386 条线索链 · 735 条证据链 · 97% 噪声过滤率 · 66 行业基准库'
    + '</div>';

  html += '<div style="padding:14px 0;border-top:1px solid #f1f5f9;font-size:13px;color:#64748b;line-height:1.8">'
    + '<strong style="color:#0f172a">执行流程：</strong>'
    + '点击"一键分析" → ①资料扫描 → ②目标实体识别 → ③资料情报提取+发票审计 → ④规则引擎+链驱动 → ⑤方法论噪声过滤 → ⑥行业对标+申报比对 → ⑦正式稽查报告输出'
    + '</div>';

  target.innerHTML = html;

  // 加载动态分析结果
  var cid = typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1;
  try {
    var resp = await fetch('/api/tax-risk-docs/last-analysis?company_id=' + cid);
    var data = await resp.json();
    if (data.ok && data.report) {
      renderAnalyzeResult(data.report);
    }
  } catch (e) {}
}

function renderAnalyzeResult(report) {
  var target = document.getElementById('analyze-body');
  if (!target) return;
  var allF = report.all_findings || [];
  var comp = report.comprehensive || {};
  var highCount = allF.filter(function(f){return f.level==='高风险'}).length;
  var html = '<div style="padding:20px 0;border-top:1px solid #f1f5f9;margin-top:20px">'
    + '<div style="font-size:15px;font-weight:600;color:#0f172a;margin-bottom:12px">本次分析结果</div>'
    + '<div style="font-size:13px;color:#64748b;line-height:2">'
    + '规则 ' + (comp.rule_count || '1503') + ' 则 · '
    + '线索链 ' + (comp.chain_count || '386') + ' 条 · '
    + '证据链 ' + (comp.evidence_count || '735') + ' 条 · '
    + '总发现 ' + allF.length + ' · '
    + '高风险 ' + highCount
    + '</div>'
    + '<div style="font-size:13px;color:#94a3b8;margin-top:8px">'
    + '四合一闭环：规则ID追溯 ✓ · 线索链追溯 ✓ · 证据来源 ✓ · 一键分析 ✓'
    + '</div>'
    + '</div>';
  target.innerHTML += html;
}


// ==================== 工具函数 ====================
function _escStatic(s) { if (!s) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function statCard(icon, label, value, color) {
  return '<div style="flex:1;min-width:80px;padding:12px 16px;text-align:center;border-right:1px solid #f1f5f9">'
    + '<div style="font-size:28px;font-weight:700;color:#0f172a">' + value + '</div>'
    + '<div style="font-size:13px;color:#94a3b8;margin-top:2px">' + label + '</div>'
    + '</div>';
}

function escHtml(s) {
  if (!s) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function toggleDomainDetail(idx) {
  var el = document.getElementById('dd-' + idx);
  if (!el) return;
  el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

// ==================== 页面4：方法论过滤器 ====================
function renderMethodologyFilterPage(container) {
  if (!container) return;
  window.currentModule = '方法论过滤器';

  container.innerHTML = '<div style="max-width:960px;margin:0 auto;padding:40px 24px 80px">'
    + '<div>'
    + '<h2 style="font-size:24px;font-weight:700;color:#0f172a;margin:0 0 6px">🎯 方法论过滤器</h2>'
    + '<p style="font-size:14px;color:#94a3b8;margin:0">HARD_BAN+COND_BAN+去重——三大噪声过滤机制，剔除97%无效发现，确保报告纯净度</p>'
    + '</div>'
    + '<div id="mf-body"></div>'
    + '</div>';

  loadMethodologyFilterData();
}

async function loadMethodologyFilterData() {
  var cid = typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1;
  try {
    var resp = await fetch('/api/tax-risk-docs/last-analysis?company_id=' + cid);
    var data = await resp.json();
    if (!data.ok) {
      document.getElementById('mf-body').innerHTML = '<div style="text-align:center;padding:40px;color:#94a3b8">⚠️ ' + (data.message || '暂无分析结果') + '</div>';
      return;
    }
    renderFilterResult(data.report);
  } catch (e) {
    document.getElementById('mf-body').innerHTML = '<div style="text-align:center;padding:40px;color:#dc2626">加载失败: ' + e.message + '</div>';
  }
}

var FILTER_RULE_NAMES = {
  '自动生成证据链': '证据链自动生成结论（非真实发现）',
  '正常结论': '正常/一致/通过类结论（无风险）',
  '资料缺口超限': '资料缺口类过多（上限5条，非核心发现）',
  '重复发现去重': '同类型重复发现合并',
  '行业不匹配': '发现内容与当前企业行业不匹配',
};

function renderFilterResult(report) {
  var comp = report.comprehensive || {};
  var fl = comp.filter_log;
  if (!fl) {
    document.getElementById('mf-body').innerHTML = '<div style="padding:40px 0;font-size:13px;color:#94a3b8">暂无过滤记录（需重新运行一键分析）</div>';
    return;
  }

  var removedItems = fl.removed_items || [];
  var breakdown = fl.reason_breakdown || {};
  var totalRemoved = fl.total_removed || 0;

  var html = '';

  // 概览
  html += '<div style="display:flex;margin-bottom:24px;margin-top:24px;border-bottom:1px solid #f1f5f9;padding-bottom:16px">';
  html += '<div style="flex:1;text-align:center;padding:12px 16px;border-right:1px solid #f1f5f9"><div style="font-size:28px;font-weight:700;color:#0f172a">' + (fl.before_count || 0) + '</div><div style="font-size:13px;color:#94a3b8;margin-top:2px">过滤前</div></div>';
  html += '<div style="flex:1;text-align:center;padding:12px 16px;border-right:1px solid #f1f5f9"><div style="font-size:28px;font-weight:700;color:#0f172a">' + (fl.after_count || 0) + '</div><div style="font-size:13px;color:#94a3b8;margin-top:2px">过滤后</div></div>';
  html += '<div style="flex:1;text-align:center;padding:12px 16px;border-right:1px solid #f1f5f9"><div style="font-size:28px;font-weight:700;color:#0f172a">' + totalRemoved + '</div><div style="font-size:13px;color:#94a3b8;margin-top:2px">已剔除</div></div>';
  html += '<div style="flex:1;text-align:center;padding:12px 16px"><div style="font-size:28px;font-weight:700;color:#0f172a">' + (fl.noise_ratio || 0) + '%</div><div style="font-size:13px;color:#94a3b8;margin-top:2px">噪声率</div></div>';
  html += '</div>';

  // 过滤规则体系
  html += '<div style="font-size:15px;font-weight:600;color:#0f172a;margin-bottom:12px">过滤规则体系</div>';
  var rules = [
    { title: 'HARD_BAN 硬删除', desc: '禁止词命中（涉税中介/公安/刑事/空壳/走逃/伪造/私户等40+词）→ 立即删除' },
    { title: 'COND_BAN 条件过滤', desc: '数据缺失触发——无申报表→删申报相关结论，无合同→删合同相关，无凭证→删成本核算类' },
    { title: '正常结论排除', desc: 'type含"一致/正常/无明显差异/通过/良好/合规/无异常"→删除' },
    { title: '资料缺口限流', desc: '资料缺少/缺失/无法验证/不完备类最多保留5条，超限删除' },
    { title: '行业不匹配', desc: '非本行业的专业发现（如纺织企业不报医药/房地产/建筑/餐饮/电商等）→删除' },
    { title: '去重合并', desc: '同type前60字完全相同的发现→只保留第一条' },
  ];
  rules.forEach(function(r) {
    html += '<div style="padding:12px 0;border-bottom:1px solid #f1f5f9">'
      + '<div style="font-size:14px;font-weight:600;color:#0f172a;margin-bottom:2px">' + r.title + '</div>'
      + '<div style="font-size:13px;color:#64748b;line-height:1.8">' + r.desc + '</div>'
      + '</div>';
  });

  // 剔除原因分布
  if (Object.keys(breakdown).length > 0) {
    html += '<div style="margin-top:20px;font-size:15px;font-weight:600;color:#0f172a;margin-bottom:12px">剔除原因分布</div>';
    var breakdownEntries = Object.entries(breakdown).sort(function(a, b) { return b[1] - a[1]; });
    breakdownEntries.forEach(function(entry) {
      var reason = entry[0], count = entry[1];
      var pct = totalRemoved > 0 ? Math.round(count / totalRemoved * 100) : 0;
      html += '<div style="padding:8px 0;border-bottom:1px solid #f1f5f9;font-size:13px;display:flex;justify-content:space-between">'
        + '<span style="color:#0f172a">' + escHtml(reason) + '</span>'
        + '<span style="color:#64748b">' + count + ' <span style="color:#94a3b8">(' + pct + '%)</span></span>'
        + '</div>';
    });
  }

  // 剔除明细
  if (removedItems.length > 0) {
    html += '<div style="margin-top:20px;font-size:15px;font-weight:600;color:#0f172a;margin-bottom:12px">剔除明细（共' + removedItems.length + '条）</div>';
    var grouped = {};
    removedItems.forEach(function(item) {
      var r = item.reason || '未知';
      if (!grouped[r]) grouped[r] = [];
      grouped[r].push(item);
    });
    Object.keys(grouped).sort(function(a, b) { return grouped[b].length - grouped[a].length; }).forEach(function(reason) {
      var items = grouped[reason];
      var reasonLabel = FILTER_RULE_NAMES[reason] || reason;
      html += '<div style="padding:8px 0;border-bottom:1px solid #f1f5f9;font-size:13px;color:#64748b">' + escHtml(reasonLabel) + ' <span style="color:#94a3b8">(' + items.length + '条)</span></div>';
    });
  }

  document.getElementById('mf-body').innerHTML = html;
}
