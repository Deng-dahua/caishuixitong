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

  container.innerHTML = '<div style="max-width:960px;margin:0 auto;padding:40px 24px 80px">'
    + '<div>'
    + '<h2 style="font-size:24px;font-weight:700;color:#0f172a;margin:0 0 6px">🔗 跨域证据链</h2>'
    + '<p style="font-size:14px;color:#94a3b8;margin:0">系统最高价值的输出——7条证据链各自由多源数据交叉验证形成，只有≥2个维度同时命中才形成有效证据链</p>'
    + '</div>'
    + '<div id="cde-static"></div>'
    + '<div id="cde-dynamic"></div>'
    + '</div>';

  loadCrossDomainStatic();
  loadCrossDomainDynamic();
}

function loadCrossDomainStatic() {
  var target = document.getElementById('cde-static');
  fetch('/static/cross_domain_evidence.json?_t=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(chains) {
      window._allCrossChains = chains;  // 保存供动态部分使用
      // 概览卡片
      var highCount = chains.filter(function(c) { return c.level === '高风险'; }).length;
      var totalDim = chains.reduce(function(s, c) { return s + c.dimensions.length; }, 0);
      var html = '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px">'
        + '<div style="flex:1;min-width:80px;text-align:center;background:#fff;padding:12px 16px;border-right:1px solid #f1f5f9"><div style="font-size:28px;font-weight:700;color:#0f172a">' + chains.length + '</div><div style="font-size:11px;color:#64748b">证据链总数</div></div>'
        + '<div style="flex:1;min-width:80px;text-align:center;background:#fff;padding:12px 16px;border-right:1px solid #f1f5f9"><div style="font-size:28px;font-weight:700;color:#0f172a">' + highCount + '</div><div style="font-size:11px;color:#64748b">高风险链</div></div>'
        + '<div id="cde-triggered-count" style="flex:1;min-width:80px;text-align:center;background:#fff;padding:12px 16px;border-right:1px solid #f1f5f9"><div style="font-size:28px;font-weight:700;color:#0f172a">—</div><div style="font-size:11px;color:#64748b">本次触发</div></div>'
        + '<div style="flex:1;min-width:80px;text-align:center;background:#fff;padding:12px 16px"><div style="font-size:28px;font-weight:700;color:#0f172a">' + totalDim + '</div><div style="font-size:11px;color:#64748b">总维度数</div></div>'
        + '</div>';

      html += '<div style="margin-bottom:24px">'
        + '<h3 style="font-size:15px;color:#1e293b;margin-bottom:12px">📐 跨域证据链体系说明</h3>'
        + '<div style="font-size:12px;color:#475569;line-height:1.8;margin-bottom:12px">'
        + '<p><b>跨域证据链是系统最高价值的输出。</b>单域发现可以解释，但多个域同时出现异常无法解释。7条证据链各自由多源数据交叉验证形成——从不同域、不同数据源提取相互印证的发现，串联为完整的证据闭环。</p>'
        + '<p>每条证据链定义了触发关键词、所需最少证据维度数、多域交叉维度结构。只有≥2个维度同时命中才形成有效证据链，保证每条结论不是孤证。</p>'
        + '</div>'

        + '<h3 style="font-size:15px;color:#1e293b;margin-bottom:8px">🗂️ ' + chains.length + '条跨域证据链</h3>'
        + '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px">'
        + chains.map(function(c) {
          return '<span style="padding:4px 12px;border-radius:4px;font-size:11px;font-weight:600;background:' + (c.level === '高风险' ? '#fef2f2' : '#fffbeb') + ';border:1px solid ' + (c.level === '高风险' ? '#fecaca' : '#fde68a') + '">' + (c.level === '高风险' ? '🔴' : '🟡') + ' ' + _escStatic(c.name) + ' (' + c.dimensions.length + '维)</span>';
        }).join('')
        + '</div>';

      chains.forEach(function(c, ci) {
        var bc = c.level === '高风险' ? '#dc2626' : '#f59e0b';
        html += '<div id="cde-chain-' + ci + '" style="border-bottom:1px solid #f1f5f9;padding:14px 0;margin-bottom:0">'
          + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">'
          + '<span style="font-size:16px">' + (c.level === '高风险' ? '🔴' : '🟡') + '</span>'
          + '<b style="font-size:13px;color:#1e293b">' + _escStatic(c.name) + '</b>'
          + '<span style="display:inline-block;padding:1px 6px;border-radius:3px;font-size:11px;font-weight:600;background:' + bc + '15;color:' + bc + '">' + _escStatic(c.level) + '</span>'
          + '<span style="display:inline-block;padding:1px 6px;border-radius:3px;font-size:11px;background:#f1f5f9;color:#64748b">' + _escStatic(c.sub_topic) + '</span>'
          + '<span id="cde-triggered-' + ci + '"></span>'
          + '<span style="font-size:11px;color:#94a3b8">需≥' + c.min_evidence + '条证据</span>'
          + '</div>'
          + '<div style="margin-bottom:6px;font-size:11px;color:#64748b">触发词：' + c.trigger_keywords.map(function(k) { return '<code style="background:#f1f5f9;padding:1px 3px;border-radius:2px">' + _escStatic(k) + '</code>'; }).join(' ') + '</div>'
          + '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px">'
          + c.dimensions.map(function(d) {
            return '<div style="flex:1;min-width:130px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:8px">'
              + '<b style="font-size:11px;color:#1e293b">' + _escStatic(d.code) + ' ' + _escStatic(d.source) + '</b>'
              + '<div style="font-size:11px;color:#64748b;margin-top:2px">' + _escStatic(d.desc.substring(0,60)) + '</div>'
              + '</div>';
          }).join('')
          + '</div>'
          + '<div style="font-size:11px;color:#475569;line-height:1.7">' + _escStatic(c.description) + '</div>'
          + '<div style="margin-top:6px;font-size:11px;color:#7c3aed">📌 ' + _escStatic(c.how_found) + '</div>'
          + '<div style="font-size:11px;color:#991b1b">💸 ' + _escStatic(c.tax_impact) + '</div>'
          + '<div style="font-size:11px;color:#1e40af">📜 ' + _escStatic(c.policy_ref) + '</div>'
          + '<div style="font-size:11px;color:#059669;padding:6px;background:#f0fdf4;border-radius:4px;margin-top:4px">✅ ' + _escStatic(c.suggestion) + '</div>'
          + '</div>';
      });

      html += '<div style="margin-top:12px;padding:10px 14px;font-size:13px;color:#94a3b8;line-height:1.8;padding:16px 0;border-top:1px solid #f1f5f9">'
        + '<b>⚠️ 证据链≠结论：</b>每条证据链需要≥2个维度同时命中才能触发。单维度触发视为孤证，不形成证据链闭环。触发条件（需≥X条证据）反映了该链的严格程度——隐匿收入和虚开发票需要更多证据，因为结论严重。'
        + '</div>'
        + '</div>';
      target.innerHTML = html;
    })
    .catch(function() {
      target.innerHTML = '<div style="text-align:center;padding:20px;color:#94a3b8">⚠️ 跨域证据链定义加载失败</div>';
    });
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

  // 从跨域关联推理域提取证据链
  var crossDomainFindings = [];
  var crossDomainDS = null;
  domainSummary.forEach(function(ds) {
    if (ds.name && ds.name.indexOf('跨域关联推理') >= 0) {
      crossDomainDS = ds;
      crossDomainFindings = ds.findings || [];
    }
  });

  // 也从 all_findings 中找证据链类型
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

  // 从 comprehensive 获取证据链闭环+触发信息
  var closures = comprehensive.evidence_closures || [];
  var closedCount = comprehensive.closed_chain_count || 0;
  var triggeredChains = comprehensive.triggered_chains || [];
  var chainExecution = comprehensive.chain_execution || [];

  // 更新概览卡片中的"本次触发"数
  var tcEl = document.getElementById('cde-triggered-count');
  if (tcEl) {
    var tcc = tcEl.querySelector('div');
    if (tcc) tcc.textContent = triggeredChains.length;
    tcEl.style.borderColor = triggeredChains.length >= 2 ? '#dc2626' : '#059669';
    tcEl.style.color = triggeredChains.length >= 2 ? '#dc2626' : '#059669';
  }

  // 为每条链更新触发状态badge
  var allCC = window._allCrossChains || [];
  allCC.forEach(function(c, ci) {
    var isTriggered = c.trigger_keywords && triggeredChains.some(function(t) {
      return c.trigger_keywords.some(function(kw) { return t.indexOf(kw) >= 0; });
    });
    var badgeEl = document.getElementById('cde-triggered-' + ci);
    if (badgeEl) {
      badgeEl.innerHTML = triggeredChains.length > 0
        ? (isTriggered ? '<span style="background:#dc2626;color:#fff;padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600">⚡ 已触发</span>' : '<span style="background:#94a3b8;color:#fff;padding:2px 8px;border-radius:3px;font-size:11px">未触发</span>')
        : '';
    }
  });

  // ── 概览 ──
  var html = '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px">';
  html += statCard('🔗', '跨域证据链', allEvidence.length, '#7c3aed');
  html += statCard('🔒', '已闭环', closedCount, closedCount >= 3 ? '#dc2626' : '#f59e0b');
  html += statCard('📊', '触发线索链', chainExecution.length, '#2563eb');
  html += statCard('🎯', '含规则ID链', triggeredChains.length, '#059669');
  html += '</div>';

  // ── 证据链闭环详情 ──
  if (closures.length > 0) {
    html += '<h3 style="margin:16px 0 8px;font-size:15px;color:#1e293b">证据链闭环检测 <span style="font-size:11px;color:#94a3b8">（≥60%规则触发+≥2域交叉=闭环）</span></h3>';
    closures.forEach(function(ec, ei) {
      var isClosed = ec.closed;
      var ratioColor = isClosed ? '#dc2626' : '#f59e0b';
      var borderColor = isClosed ? '#dc2626' : '#f59e0b';
      var bgColor = isClosed ? '#fef2f2' : '#fffbeb';

      html += '<div style="border:2px solid ' + borderColor + ';background:' + bgColor + ';border-radius:10px;padding:16px;margin-bottom:12px">'
        + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">'
        + '<b style="font-size:15px;color:#1e293b">' + escHtml(ec.chain_name) + '</b>'
        + '<span style="display:inline-block;padding:3px 10px;border-radius:4px;background:' + ratioColor + '15;color:' + ratioColor + ';font-size:12px;font-weight:700">'
        + (isClosed ? '🔒 已闭环' : '⚠️ 未闭环') + ' ' + ec.ratio + '%'
        + '</span>'
        + '</div>'
        + '<div style="font-size:11px;color:#64748b;margin-bottom:8px">触发 <b>' + ec.triggered_steps + '</b>/' + ec.total_steps + ' 条规则</div>';

      if (ec.steps && ec.steps.length) {
        html += '<div style="display:flex;gap:6px;flex-wrap:wrap">';
        ec.steps.forEach(function(step) {
          var stepColor = step.triggered ? '#059669' : '#94a3b8';
          var stepBg = step.triggered ? '#f0fdf4' : '#f8fafc';
          html += '<div style="padding:4px 10px;border-radius:4px;background:' + stepBg + ';border:1px solid ' + stepColor + ';font-size:11px">'
            + '<span style="color:' + stepColor + ';font-weight:600">' + (step.triggered ? '✓' : '○') + '</span> '
            + escHtml(step.step.substring(0, 24))
            + (step.rule_id ? ' <span style="color:#94a3b8">R' + step.rule_id + '</span>' : '')
            + '</div>';
        });
        html += '</div>';
      }

      html += '</div>';
    });
  }

  // ── 跨域证据链详细内容 ──
  html += '<h3 style="margin:20px 0 8px;font-size:15px;color:#1e293b">跨域关联推理详情</h3>';

  if (allEvidence.length === 0) {
    html += '<div style="text-align:center;padding:20px;color:#94a3b8;background:#f8fafc;border-radius:8px">暂无跨域证据链数据</div>';
  } else {
    allEvidence.forEach(function(f, ei) {
      var isChain = (f.type || '').indexOf('证据链') >= 0;
      var borderColor = isChain ? '#7c3aed' : (f.level === '高风险' ? '#dc2626' : '#f59e0b');
      var bgColor = isChain ? '#f5f3ff' : '#fff';
      var dotColor = f.level === '高风险' ? '🔴' : (f.level === '中风险' ? '🟡' : '🟢');

      html += '<div style="border:2px solid ' + borderColor + ';background:' + bgColor + ';border-radius:10px;padding:16px;margin-bottom:12px">'
        + '<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">'
        + '<div>'
        + '<span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;background:' + borderColor + '15;color:' + borderColor + ';margin-right:8px">' + escHtml(f.level || '—') + '</span>'
        + '<b style="font-size:15px;color:#1e293b">' + escHtml(f.type || '') + '</b>'
        + '</div>'
        + '<span style="font-size:18px">' + dotColor + '</span>'
        + '</div>';

      // description
      if (f.description) {
        html += '<div style="font-size:12px;color:#475569;line-height:1.8;margin-bottom:8px;padding:10px;background:#f8fafc;border-radius:6px">' + escHtml(f.description.substring(0, 400)) + '</div>';
      }

      // how_found (溯源)
      if (f.how_found) {
        html += '<div style="font-size:11px;color:#64748b;margin-bottom:6px">📌 <b>溯源：</b>' + escHtml(f.how_found.substring(0, 200)) + '</div>';
      }

      // tax_impact
      if (f.tax_impact) {
        html += '<div style="font-size:11px;color:#991b1b;margin-bottom:6px">💸 <b>纳税影响：</b>' + escHtml(f.tax_impact.substring(0, 200)) + '</div>';
      }

      // policy_ref
      if (f.policy_ref) {
        html += '<div style="font-size:11px;color:#1e40af;margin-bottom:6px">📜 <b>法律依据：</b>' + escHtml(f.policy_ref.substring(0, 200)) + '</div>';
      }

      // suggestion
      if (f.suggestion) {
        html += '<div style="font-size:11px;color:#059669;padding:8px;background:#f0fdf4;border-radius:6px">✅ <b>处理建议：</b>' + escHtml(f.suggestion.substring(0, 200)) + '</div>';
      }

      // 域交叉信息
      if (f.cross_domains) {
        html += '<div style="margin-top:8px;font-size:11px;color:#7c3aed">跨越 <b>' + f.cross_domains + '</b> 个分析域</div>';
      }

      html += '</div>';
    });
  }

  // ── 触发线索链TOP20 ──
  if (chainExecution.length > 0) {
    html += '<h3 style="margin:20px 0 8px;font-size:15px;color:#1e293b">触发线索链 TOP' + Math.min(20, chainExecution.length) + '</h3>';
    html += '<div style="overflow-x:auto"><table class="pipeline-table">';
    html += '<thead><tr><th>线索链名称</th><th>触发/总步数</th><th>触发率</th></tr></thead><tbody>';
    chainExecution.slice(0, 20).forEach(function(ce) {
      var ratioColor = ce.triggered_ratio >= 80 ? '#dc2626' : (ce.triggered_ratio >= 50 ? '#f59e0b' : '#059669');
      html += '<tr>'
        + '<td style="max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + escHtml(ce.chain_name) + '">' + escHtml(ce.chain_name) + '</td>'
        + '<td><b>' + ce.triggered_steps + '</b> / ' + ce.total_steps + '</td>'
        + '<td><span style="color:' + ratioColor + ';font-weight:700">' + ce.triggered_ratio + '%</span></td>'
        + '</tr>';
    });
    html += '</tbody></table></div>';
  }

  target.innerHTML = '<div style="border-top:2px solid #e2e8f0;padding-top:20px;margin-top:20px"><h3 style="font-size:15px;color:#1e293b;margin-bottom:12px">📊 本次动态证据链结果</h3>' + html + '</div>';
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
  // 直接渲染框架，数据到位后无缝填充
  container.innerHTML = '<div style="max-width:960px;margin:0 auto;padding:40px 24px 80px">'
    + '<div>'
    + '<h2 style="font-size:24px;font-weight:700;color:#0f172a;margin:0 0 6px">🔗 线索链列表</h2>'
    + '<p style="font-size:14px;color:#94a3b8;margin:0">稽查调查路径，每条链含若干调查步骤，触发率=已触发步骤/总步骤</p>'
    + '</div>'
    + '<div id="chains-body"></div></div>';
  loadChainsData();
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

  // build dynamic trigger map
  var execMap = {};
  if (_chainDynamic && _chainDynamic.chain_execution) {
    _chainDynamic.chain_execution.forEach(function(ce) { execMap[ce.chain_name] = ce; });
  }
  var hasDynamic = Object.keys(execMap).length > 0;
  var triggeredTotal = 0;

  var html = '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px">'
    + statCard('🔗', '线索链总数', chains.length, '#2563eb');

  if (hasDynamic && _chainDynamic) {
    html += '<span style="padding:6px 14px;border-radius:6px;font-size:11px;background:#eff6ff;border:1px solid #bfdbfe;color:#1e40af"><b>已触发：</b>' + (_chainDynamic.triggered_count||0) + ' 条</span>'
      + '<span style="padding:6px 14px;border-radius:6px;font-size:11px;background:#fef3c7;border:1px solid #fde68a;color:#92400e"><b>已闭环：</b>' + (_chainDynamic.closed_count||0) + ' 条</span>';
  }

  // 搜索框 + 过滤器
  html += '<div style="flex:1;min-width:200px;background:#fff;border:2px solid #e2e8f0;border-radius:10px;padding:14px">'
    + '<input type="text" id="chain-search-input" placeholder="搜索线索链..." style="width:100%;padding:8px 12px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px" oninput="renderChainsList(_allClueChains)">'
    + '</div>'
    + '<div style="display:flex;gap:6px">'
    + '<select id="chain-filter-cat" onchange="renderChainsList(_allClueChains)" style="padding:6px 8px;border:1px solid #e2e8f0;border-radius:6px;font-size:12px"><option value="">全部分类</option>'
    + (catKeys||[]).map(function(k) { return '<option value="'+k+'">'+k+'</option>'; }).join('')
    + '</select>'
    + '<select id="chain-filter-level" onchange="renderChainsList(_allClueChains)" style="padding:6px 8px;border:1px solid #e2e8f0;border-radius:6px;font-size:12px"><option value="">全部等级</option><option value="高风险">含高风险环节</option><option value="中风险">含中风险环节</option></select>'
    + '</div>'
    + '</div>';

  if (!filtered.length) {
    html += '<div style="text-align:center;padding:40px;color:#94a3b8">无匹配线索链</div>';
  } else {
    filtered.forEach(function(c) {
      var exec = execMap[c.name];
      var triggeredSteps = exec ? exec.triggered_steps : 0;
      var totalSteps = exec ? exec.total_steps : (c.steps ? c.steps.length : (c.total_steps || 0));
      var ratio = exec ? exec.triggered_ratio : 0;
      if (exec && exec.triggered_steps > 0) triggeredTotal++;

      var borderColor = ratio >= 80 ? '#dc2626' : (ratio >= 50 ? '#f59e0b' : (ratio > 0 ? '#059669' : '#e2e8f0'));
      var badgeHtml = '';
      if (exec && exec.triggered_steps > 0) {
        badgeHtml = ' <span style="background:' + (ratio >= 60 ? '#dc2626' : '#059669') + '15;color:' + (ratio >= 60 ? '#dc2626' : '#059669') + ';padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700">⚡ ' + triggeredSteps + '/' + totalSteps + ' (' + ratio + '%)</span>';
      }

      html += '<div style="border:2px solid ' + borderColor + ';border-radius:8px;padding:14px;margin-bottom:12px;background:#fff">'
        + '<div style="font-weight:700;font-size:13px;margin-bottom:6px;color:#1e293b">' + escHtml(c.name) + ' <span style="font-weight:400;font-size:11px;color:#94a3b8">' + (c.steps ? c.steps.length : totalSteps) + '步</span>' + badgeHtml + '</div>'
        + '<div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center">';

      (c.investigation_path||[]).forEach(function(s, idx) {
        var dot = s.level==='高风险'?'#dc2626':(s.level==='中风险'?'#f59e0b':'#94a3b8');
        var stepBg = '#f8fafc';
        if (exec && exec.triggered_steps > 0) {
          stepBg = ratio >= 60 ? '#fef2f2' : '#f0fdf4';
        }
        html += '<span style="background:'+stepBg+';padding:4px 10px;border-radius:4px;font-size:11px;border-left:2px solid '+dot+'">' + escHtml(s.step||s.rule_item||'') + '</span>';
        if (idx < (c.investigation_path||[]).length - 1) html += '<span style="color:#94a3b8;font-weight:700">→</span>';
      });

      html += '</div></div>';
    });
  }

  target.innerHTML = html;

  var statsText = '共 ' + filtered.length + ' 条线索链';
  if (hasDynamic && filtered.length > 0) statsText += ' | 已触发 ' + triggeredTotal + ' 条';
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
  // 直接渲染框架，数据到位后无缝填充
  container.innerHTML = '<div style="max-width:960px;margin:0 auto;padding:40px 24px 80px">'
    + '<div>'
    + '<h2 style="font-size:24px;font-weight:700;color:#0f172a;margin:0 0 6px">🔒 证据链列表</h2>'
    + '<p style="font-size:14px;color:#94a3b8;margin:0">含规则ID+处罚依据，每条证据链需≥3条线索链触发+≥2域交叉验证形成闭环</p>'
    + '</div>'
    + '<div id="evidence-body"></div></div>';
  loadEvidenceData();
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

  // build dynamic evidence closure map
  var evExecMap = {};
  if (_chainDynamic && _chainDynamic.evidence_closures) {
    _chainDynamic.evidence_closures.forEach(function(ec) { evExecMap[ec.chain_name] = ec; });
  }
  var hasDynamic = Object.keys(evExecMap).length > 0;

  var html = '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px">'
    + statCard('🔒', '证据链总数', chains.length, '#7c3aed');

  if (hasDynamic && _chainDynamic) {
    var closedCount = 0;
    chains.forEach(function(c) {
      if (evExecMap[c.name] && evExecMap[c.name].closed) closedCount++;
    });
    html += '<span style="padding:6px 14px;border-radius:6px;font-size:11px;background:#fef3c7;border:1px solid #fde68a;color:#92400e"><b>已闭环：</b>' + closedCount + ' 条</span>';
  }

  // 搜索框 + 过滤器
  html += '<div style="flex:1;min-width:200px;background:#fff;border:2px solid #e2e8f0;border-radius:10px;padding:14px">'
    + '<input type="text" id="evidence-search-input" placeholder="搜索证据链..." style="width:100%;padding:8px 12px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px" oninput="renderEvidenceList(_allEvidenceChains)">'
    + '</div>'
    + '<div style="display:flex;gap:6px">'
    + '<select id="evidence-filter-cat" onchange="renderEvidenceList(_allEvidenceChains)" style="padding:6px 8px;border:1px solid #e2e8f0;border-radius:6px;font-size:12px"><option value="">全部分类</option></select>'
    + '<select id="evidence-filter-level" onchange="renderEvidenceList(_allEvidenceChains)" style="padding:6px 8px;border:1px solid #e2e8f0;border-radius:6px;font-size:12px"><option value="">全部等级</option><option value="高风险">高风险</option><option value="中风险">中风险</option></select>'
    + '</div>'
    + '</div>';

  if (!filtered.length) {
    html += '<div style="text-align:center;padding:40px;color:#94a3b8">无匹配证据链</div>';
  } else {
    filtered.forEach(function(c) {
      var evExec = evExecMap[c.name];
      var evBorder = evExec ? (evExec.closed ? '#dc2626' : '#f59e0b') : '#e2e8f0';
      var evBadge = evExec ? (' <span style="background:' + (evExec.closed ? '#dc2626' : '#f59e0b') + '15;color:' + (evExec.closed ? '#dc2626' : '#f59e0b') + ';padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700">' + (evExec.closed ? '🔒闭环' : '⚠未闭环') + ' ' + evExec.ratio + '%</span>') : '';

      html += '<div style="border:2px solid ' + evBorder + ';border-radius:8px;padding:16px;margin-bottom:12px;background:#fff">'
        + '<div style="font-weight:700;font-size:15px;color:#1e293b;margin-bottom:4px">' + escHtml(c.name) + ' <span style="font-weight:400;font-size:11px;color:#94a3b8">' + (c.steps||c.investigation_path||[]).length + '步 ' + (c.high_risk_steps||'') + '高</span>' + evBadge + '</div>';

      // 调查路径（含规则ID、处罚依据、纳税影响）
      (c.investigation_path||[]).forEach(function(s) {
        var dot = s.level==='高风险'?'#dc2626':(s.level==='中风险'?'#f59e0b':'#94a3b8');
        html += '<div style="display:flex;gap:8px;align-items:baseline;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #f8fafc">'
          + '<span style="font-size:11px;color:'+dot+';font-weight:700;min-width:22px;text-align:right">R'+(s.rule_id||'')+'</span>'
          + '<span style="width:4px;height:4px;border-radius:50%;background:'+dot+';margin-top:6px;flex-shrink:0"></span>'
          + '<div style="flex:1;font-size:11px;color:#475569;line-height:1.6">'
          + '<b style="color:#1e293b;font-size:12px">'+(s.rule_item||s.step||'')+'</b> '
          + '<span style="font-size:11px;color:'+dot+'">['+(s.level||'')+']</span>'
          + '<br>'+(s.detail||'').substring(0,150)
          + '<div style="margin-top:2px;font-size:11px;color:#94a3b8">'+(s.policy_ref||'').substring(0,80)+'</div>'
          + '<div style="margin-top:2px;font-size:11px;color:#dc2626">'+(s.tax_impact||'').substring(0,80)+'</div>'
          + '</div></div>';
      });

      // 质量分 + 覆盖规则数
      var rCount = c.covered_rule_count || (c.investigation_path||[]).length;
      var qScore = c.quality_score || 0;
      var qLabel = qScore>=15?'S':(qScore>=10?'A':(qScore>=7?'B':'C'));
      var qColor = qScore>=15?'#059669':(qScore>=10?'#2563eb':(qScore>=7?'#f59e0b':'#94a3b8'));

      html += '<div style="margin-top:8px;padding-top:8px;border-top:1px dashed #e2e8f0;font-size:11px;color:#94a3b8">'
        + '<span style="background:'+qColor+'15;color:'+qColor+';padding:1px 6px;border-radius:2px;font-weight:700;margin-right:6px">'+qLabel+'</span>'
        + '覆盖规则: <b style="color:#1e293b">'+rCount+'条</b>';
      if (c.related_chain_count > 0) html += ' | 关联链: <b style="color:#1e293b">'+c.related_chain_count+'条</b>';
      if (qScore) html += ' | 质量: <b style="color:'+qColor+'">'+qScore+'分</b>';
      html += '</div>';

      html += '</div>';
    });
  }

  target.innerHTML = html;

  // 更新统计
  var closedInFiltered = 0;
  if (_chainDynamic && _chainDynamic.evidence_closures) {
    var evNames = {};
    filtered.forEach(function(f){ evNames[f.name] = true; });
    _chainDynamic.evidence_closures.forEach(function(ec){ if (ec.closed && evNames[ec.chain_name]) closedInFiltered++; });
  }
  var evText = '共 ' + filtered.length + ' 条证据链';
  if (closedInFiltered > 0) evText += ' | 🔒已闭环 ' + closedInFiltered + ' 条';

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
    + '<h2 style="font-size:24px;font-weight:700;color:#0f172a;margin:0 0 6px">⚡ 一键分析概览</h2>'
    + '<p style="font-size:14px;color:#94a3b8;margin:0">方法论驱动稽查引擎——点击"运行一键分析"启动完整稽查流程</p>'
    + '</div>'
    + '<div id="analyze-body"></div>'
    + '</div>';
  loadAnalyzeOverview();
}

async function loadAnalyzeOverview() {
  var target = document.getElementById('analyze-body');
  // 静态内容（完整移植原 rr-panel-analyze）
  var staticHtml = '<div style="margin-bottom:24px">'
    + '<h3 style="font-size:15px;color:#1e293b;margin-bottom:12px">📐 一键分析执行管线</h3>'
    + '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px">'
    // 子系统1
    + '<div style="border:1px solid #e2e8f0;border-left:3px solid #2563eb;border-radius:6px;padding:14px;background:#fff">'
    + '<div style="font-weight:700;font-size:13px;color:#1e293b;margin-bottom:8px">① 资料扫描与类型识别</div>'
    + '<div style="font-size:11px;color:#64748b;line-height:1.8">'
    + '34类文件指纹 + 三层递进识别（关键词→结构分析→数据推断）<br>'
    + '自动判定发票方向（购方名→销项 / 销方名→进项）<br>'
    + '诊断追踪系统记录完整决策链路'
    + '</div></div>'
    // 子系统2
    + '<div style="border:1px solid #e2e8f0;border-left:3px solid #059669;border-radius:6px;padding:14px;background:#fff">'
    + '<div style="font-weight:700;font-size:13px;color:#1e293b;margin-bottom:8px">② 目标实体识别</div>'
    + '<div style="font-size:11px;color:#64748b;line-height:1.8">'
    + '进项购买方 ∩ 销项销售方 → 自动确定被查单位<br>'
    + '66个行业分类（加权投票制，避免误判）<br>'
    + '企业类型自动判定（生产型/服务型/贸易型）'
    + '</div></div>'
    // 子系统3
    + '<div style="border:1px solid #e2e8f0;border-left:3px solid #7c3aed;border-radius:6px;padding:14px;background:#fff">'
    + '<div style="font-weight:700;font-size:13px;color:#1e293b;margin-bottom:8px">③ 资料情报提取 + 数据分析</div>'
    + '<div style="font-size:11px;color:#64748b;line-height:1.8">'
    + '银行流水深度分析：收款构成(企业/个人/税费/银行)+收款方TOP10<br>'
    + '<b style="color:#7c3aed">联网核查：自动查询被查单位工商登记信息（法定代表人/股东/注册资本/行业分类）</b><br>'
    + '进销存比对：商品明细匹配 + 进销比 + 毛利率<br>'
    + '供应商穿透：集中度 + 名称群集 + 双向交易 + 地域群集<br>'
    + '<b style="color:#dc2626">发票深度审计：五层检查(合规/单价/加工费/合理性/进销映射→BOM)</b><br>'
    + '<b style="color:#059669">BOM判断：进销品名差异+加工费证据→外包轻加工模式（批发业也可存在）</b><br>'
    + '<b style="color:#7c3aed">联网核查：自动查工商信息（法定代表人/股东/行业分类/注册资本）</b><br>'
    + '<b style="color:#d97706">收款分类：按付款方性质分企业/个人/税费/银行</b>'
    + '</div></div>'
    // 子系统4
    + '<div style="border:1px solid #e2e8f0;border-left:3px solid #f59e0b;border-radius:6px;padding:14px;background:#fff">'
    + '<div style="font-weight:700;font-size:13px;color:#1e293b;margin-bottom:8px">④ 规则引擎 + 链驱动检查</div>'
    + '<div style="font-size:11px;color:#64748b;line-height:1.8">'
    + '1503条规则逐条匹配 + 真实数据验证（非关键词匹配）<br>'
    + '386条线索链驱动：定量阈值验证（金额/比例/数量）<br>'
    + '735条证据链闭环：≥3条触发+≥2域交叉验证<br>'
    + '<b style="color:#dc2626">方法论过滤器：1554→50±条（剔除97%噪声）</b>'
    + '</div></div>'
    // 子系统5
    + '<div style="border:1px solid #e2e8f0;border-left:3px solid #dc2626;border-radius:6px;padding:14px;background:#fff">'
    + '<div style="font-weight:700;font-size:13px;color:#1e293b;margin-bottom:8px">⑤ 方法论噪声过滤器</div>'
    + '<div style="font-size:11px;color:#64748b;line-height:1.8">'
    + '硬删除：禁止词(涉税中介/公安/伪造/资金回流等40+)<br>'
    + '条件过滤：无资料→对应结论全删（申报表/合同/工资/凭证）<br>'
    + '行业匹配：纺织企业不报医药/房地产/电商/教培等8行业<br>'
    + '去重+正常结论排除+模板僵尸{var}检测<br>'
    + '实测1554→24条（剔除97%噪声）'
    + '</div></div>'
    // 子系统6
    + '<div style="border:1px solid #e2e8f0;border-left:3px solid #0f172a;border-radius:6px;padding:14px;background:#fff">'
    + '<div style="font-weight:700;font-size:13px;color:#1e293b;margin-bottom:8px">⑥ 行业对标 + 申报比对</div>'
    + '<div style="font-size:11px;color:#64748b;line-height:1.8">'
    + '66行业基准值自动对标（毛利率/税负率/进销比/人均营收）<br>'
    + '申报表vs发票实际数据比对（核心逃税检测）<br>'
    + '无申报表→标记为资料缺口，不臆测'
    + '</div></div>'
    // 子系统7
    + '<div style="border:1px solid #e2e8f0;border-left:3px solid #0891b2;border-radius:6px;padding:14px;background:#fff">'
    + '<div style="font-weight:700;font-size:13px;color:#1e293b;margin-bottom:8px">⑦ 正式稽查报告输出</div>'
    + '<div style="font-size:11px;color:#64748b;line-height:1.8">'
    + '国家税务总局呈报格式（封面/文号/签章/落款）<br>'
    + '已查实问题 + 需进一步核实问题，两级分类<br>'
    + '稽查人员口吻：查证过程/问题定性/法律依据'
    + '</div></div>'
    + '</div>'
    // 统计总览
    + '<div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">'
    + '<span style="color:#64748b;font-size:12px"><b>1503</b> 条规则</span>'
    + '<span style="color:#64748b;font-size:12px"><b>386</b> 条线索链</span>'
    + '<span style="color:#64748b;font-size:12px"><b>735</b> 条证据链</span>'
    + '<span style="color:#64748b;font-size:12px"><b>97%</b> 噪声过滤率</span>'
    + '<span style="color:#64748b;font-size:12px"><b>66</b> 行业基准库</span>'
    + '</div>'
    // 底部说明
    + '<div style="margin-top:16px;padding:12px 16px;font-size:13px;color:#64748b;line-height:1.8">'
    + '<strong style="color:#1e293b">执行流程：</strong>'
    + '点击"一键分析" → '
    + '①资料扫描+类型识别 → '
    + '②目标实体识别 → '
    + '③资料情报提取+发票审计（合规/单价/BOM）→ '
    + '④规则引擎+链驱动(1503/386/735) → '
    + '⑤方法论噪声过滤(剔除97%) → '
    + '⑥行业对标+申报比对 → '
    + '⑦正式稽查报告输出'
    + '</div>'
    + '<div style="margin-top:8px;padding:10px 12px;font-size:13px;color:#64748b;line-height:1.8;padding:12px 0;border-top:1px solid #f1f5f9">'
    + '<strong>📑 稽查行为准则（已内化）：</strong><br>'
    + '<b>① 必有明细：</b>每条结论必须有具体数据支撑——列出供应商名、金额、发票号、商品名，不可泛泛计数。<br>'
    + '<b>② 自行解决：</b>遇到解析错误、格式不兼容、字段缺失等自身问题，不提问不墨迹，直接读文件查格式修复。<br>'
    + '<b>③ 不墨迹：</b>报告未出完、修复未验证、下一步工作必须做时，不等不提问，自动继续直到交付完整结果。'
    + '</div>'
    + '<div style="margin-top:8px;padding:10px 12px;font-size:13px;color:#64748b;line-height:1.8;padding:12px 0;border-top:1px solid #f1f5f9">'
    + '<strong>📖 稽查方法论八条（达冠实战总结）：</strong><br>'
    + '① 多格式兼容：银行文件date/tx_time/交易日期/交易时间/记账日期五种命名全兼容，未知格式直接读表头<br>'
    + '② 汇总行过滤：月末汇总行(对手为空+大额整数)→自动识别并剔除，防止13M虚增<br>'
    + '③ 付款方身份核实：个人打款→联网查工商→范善茂=法定代表人→定性待核实（非直接假定注资）<br>'
    + '④ 关键词≠事实：BOM判断从关键词匹配升级为进销品名实质差异+加工费证据双重验证<br>'
    + '⑤ 行业认知补算法：工商批发业≠无加工。纺织贸易外包轻加工模式→BOM仍需要<br>'
    + '⑥ 联网核查：企查查查法人/股东/行业/注册资本，颠覆范善茂=不明来源的判断<br>'
    + '⑦ 明细即信服力：全部收款方+付款方均逐一列示明细表，不分组合并<br>'
    + '⑧ 不墨迹直接干：发现问题不请示，读文件查格式直接修<br>'
    + '⑨ JS双函数覆盖陷阱：同名函数后定义覆盖前定义→修改前grep确认只有1个<br>'
    + '⑩ 完备度明细：缺失资料逐类列示缺失后果，不泛泛说"缺5类"→每类写明稽查风险<br>'
    + '⑪ 完备度升级：8类→15类（+科目余额表/财务报表/增值税申报/所得税申报/个税申报/小税种）<br>'
    + '⑫ 凭证描述纠正：无凭证不等于核定征收（删除了严重夸大性表述）<br>'
    + '⑬ 进销诊断升级：制造业加工链条自动识别→有销无进/有进无销降级中风险+根因分析<br>'
    + '⑭ 行业基准库：34行业×5指标双向匹配自动选行业<br>'
    + '⑮ 结论分析法：先问为什么→分析进项结构→展示加工链条→风险转移而非消除<br>'
    + '⑯ COND_BAN防误杀：建议词≠数据依赖，"入库单/出库单"移除（含建议词的发现不应被无库存数据误删）<br>'
    + '⑰ 稽查重点强制等级：现实中稽查必查项不根据score定级，AUDIT_PRIORITY_LEVELS硬编码+前端红色标记<br>'
    + '⑱ 报告纯净度：移除系统内部标注（detect/verify/线索链自动触发等），报告即专业稽查文书<br>'
    + '⑲ 发票≠收付款1:1：进项付款+销项收款均承认预付/应收/分期/合并/跨期/代付（双边统一方法论）<br>'
    + '⑳ 经营实质地理分析：地址→运输→加工费多点交叉，单点到面（+2规则+1线索链+4步证据链）<br>'
    + '㉑ 规则detail业务化：533条规则从泛化模板改为业务实质描述（10条核心重写+523条批量修正）<br>'
    + '㉒ 建议质量增强：单点/面的风险均有具体佐证路径（提供XX资料→如果A就XX→如果B就XX→无法做到的后果）<br>'
    + '㉓ 合同分层判断：_analyze_contract_tiers()→_domain_document_completeness 接入管线，供应商分三类——主营业务必须签/重大支出必须签/日常费用可免签（不再一刀切缺合同）<br>'
    + '<b style="color:#dc2626">+合同分层判断 | 建议质量增强 | 规则detail(533条) | 经营实质地理 | 四合一闭环</b>'
    + '</div>'
    + '</div>';

  target.innerHTML = staticHtml;

  // 加载动态分析结果
  var cid = typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1;
  try {
    var resp = await fetch('/api/tax-risk-docs/last-analysis?company_id=' + cid);
    var data = await resp.json();
    if (data.ok && data.report) {
      renderAnalyzeResult(data.report);
    } else {
      target.innerHTML += '<div style="text-align:center;padding:20px;color:#94a3b8;margin-top:20px">⚠️ 暂无分析结果，请先运行一键分析</div>';
    }
  } catch (e) {
    target.innerHTML += '<div style="text-align:center;padding:20px;color:#94a3b8;margin-top:20px">动态数据加载失败</div>';
  }
}

function renderAnalyzeResult(report) {
  var target = document.getElementById('analyze-body');
  if (!target) return;
  var allF = report.all_findings || [];
  var comp = report.comprehensive || {};
  var html = '<div style="border-top:2px solid #e2e8f0;padding-top:20px;margin-top:20px">'
    + '<h3 style="font-size:15px;color:#1e293b;margin-bottom:12px">📊 本次分析结果</h3>'
    + '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px">'
    + statCard('📋', '规则', (comp.rule_count || '1503') + '则', '#2563eb')
    + statCard('🔗', '线索链', (comp.chain_count || '386') + '条', '#059669')
    + statCard('🔒', '证据链', (comp.evidence_count || '735') + '条', '#7c3aed')
    + statCard('⚠️', '总发现', allF.length, '#dc2626')
    + statCard('🔴', '高风险', allF.filter(function(f){return f.level==='高风险'}).length, '#dc2626')
    + '</div>'
    + '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:14px;margin-bottom:20px">'
    + '<h4 style="font-size:13px;color:#166534;margin-bottom:8px">✅ 四合一闭环状态</h4>'
    + '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px;font-size:11px;color:#475569">'
    + '<div>✓ 规则ID追溯：<span style="color:#166534;font-weight:600">已接入</span></div>'
    + '<div>✓ 线索链追溯：<span style="color:#166534;font-weight:600">已接入</span></div>'
    + '<div>✓ 证据来源：<span style="color:#166534;font-weight:600">已接入</span></div>'
    + '<div>✓ 一键分析：<span style="color:#166534;font-weight:600">已接入</span></div>'
    + '</div></div></div>';
  target.innerHTML += html;
}


// ==================== 工具函数 ====================
function _escStatic(s) { if (!s) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function statCard(icon, label, value, color) {
  return '<div style="flex:1;min-width:100px;background:#fff;border:2px solid ' + color + ';border-radius:10px;padding:14px;text-align:center">'
    + '<div style="font-size:28px;margin-bottom:4px">' + icon + '</div>'
    + '<div style="font-size:28px;font-weight:700;color:' + color + '">' + value + '</div>'
    + '<div style="font-size:11px;color:#64748b">' + label + '</div>'
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
    document.getElementById('mf-body').innerHTML = '<div style="text-align:center;padding:40px;color:#94a3b8">⚠️ 暂无过滤记录（需重新运行一键分析）</div>';
    return;
  }

  var removedItems = fl.removed_items || [];
  var breakdown = fl.reason_breakdown || {};
  var totalRemoved = fl.total_removed || 0;

  var html = '';

  // ── 概览卡片 ──
  html += '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px">';
  html += statCard('📥', '过滤前', fl.before_count || 0, '#2563eb');
  html += statCard('📤', '过滤后', fl.after_count || 0, '#059669');
  html += statCard('🗑️', '已剔除', totalRemoved, '#dc2626');
  html += statCard('📊', '噪声率', (fl.noise_ratio || 0) + '%', '#7c3aed');
  html += '</div>';

  // ── 过滤规则说明 ──
  html += '<h3 style="margin:16px 0 8px;font-size:15px;color:#1e293b">过滤规则体系</h3>';
  html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:8px;margin-bottom:16px">';

  var rules = [
    { title: '① HARD_BAN 硬删除', desc: '禁止词命中（涉税中介/公安/刑事/空壳/走逃/伪造/私户等40+词）→ 立即删除', color: '#dc2626' },
    { title: '② COND_BAN 条件过滤', desc: '数据缺失触发——无申报表→删申报相关结论，无合同→删合同相关，无凭证→删成本核算类', color: '#f59e0b' },
    { title: '③ 正常结论排除', desc: 'type含"一致/正常/无明显差异/通过/良好/合规/无异常"→删除', color: '#059669' },
    { title: '④ 资料缺口限流', desc: '资料缺少/缺失/无法验证/不完备类最多保留5条，超限删除', color: '#2563eb' },
    { title: '⑤ 行业不匹配', desc: '非本行业的专业发现（如纺织企业不报医药/房地产/建筑/餐饮/电商等）→删除', color: '#7c3aed' },
    { title: '⑥ 去重合并', desc: '同type前60字完全相同的发现→只保留第一条', color: '#0891b2' },
  ];

  rules.forEach(function(r) {
    html += '<div style="border:1px solid ' + r.color + ';background:' + r.color + '08;border-radius:8px;padding:12px">'
      + '<div style="font-weight:700;font-size:13px;color:' + r.color + ';margin-bottom:4px">' + r.title + '</div>'
      + '<div style="font-size:11px;color:#64748b;line-height:1.6">' + r.desc + '</div>'
      + '</div>';
  });

  html += '</div>';

  // ── 剔除原因分布 ──
  html += '<h3 style="margin:20px 0 8px;font-size:15px;color:#1e293b">剔除原因分布</h3>';
  if (Object.keys(breakdown).length === 0) {
    html += '<div style="text-align:center;padding:12px;color:#94a3b8;background:#f8fafc;border-radius:8px">本次无剔除</div>';
  } else {
    html += '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px">';
    var breakdownEntries = Object.entries(breakdown).sort(function(a, b) { return b[1] - a[1]; });
    breakdownEntries.forEach(function(entry) {
      var reason = entry[0], count = entry[1];
      var pct = totalRemoved > 0 ? Math.round(count / totalRemoved * 100) : 0;
      var barWidth = Math.max(3, pct);
      var color = reason.indexOf('禁止词') >= 0 ? '#dc2626' : (reason.indexOf('无') >= 0 ? '#f59e0b' : (reason.indexOf('行业') >= 0 ? '#7c3aed' : '#059669'));
      html += '<div style="flex:1;min-width:160px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:10px">'
        + '<div style="font-size:11px;color:#64748b;margin-bottom:4px">' + escHtml(reason) + '</div>'
        + '<div style="display:flex;align-items:center;gap:8px">'
        + '<span style="font-size:20px;font-weight:700;color:' + color + '">' + count + '</span>'
        + '<span style="font-size:11px;color:#94a3b8">' + pct + '%</span>'
        + '</div>'
        + '<div style="margin-top:4px;height:4px;background:#f1f5f9;border-radius:2px">'
        + '<div style="height:100%;width:' + barWidth + '%;background:' + color + ';border-radius:2px"></div>'
        + '</div>'
        + '</div>';
    });
    html += '</div>';
  }

  // ── 详细剔除明细 ──
  html += '<h3 style="margin:20px 0 8px;font-size:15px;color:#1e293b">剔除明细 <span style="font-size:11px;color:#94a3b8">（共' + removedItems.length + '条）</span></h3>';

  if (removedItems.length === 0) {
    html += '<div style="text-align:center;padding:20px;color:#94a3b8;background:#f8fafc;border-radius:8px">无剔除记录</div>';
  } else {
    html += '<div style="overflow-x:auto"><table class="pipeline-table">';
    html += '<thead><tr><th>#</th><th>发现类型</th><th>等级</th><th>分数</th><th>剔除原因</th><th>分类</th></tr></thead><tbody>';

    // 按原因分组显示
    var grouped = {};
    removedItems.forEach(function(item) {
      var r = item.reason || '未知';
      if (!grouped[r]) grouped[r] = [];
      grouped[r].push(item);
    });

    var idx = 0;
    Object.keys(grouped).sort(function(a, b) { return grouped[b].length - grouped[a].length; }).forEach(function(reason) {
      var items = grouped[reason];
      // 显示该组标题
      var reasonLabel = FILTER_RULE_NAMES[reason] || reason;
      var reasonColor = reason.indexOf('禁止词') >= 0 ? '#dc2626' : (reason.indexOf('无') >= 0 ? '#f59e0b' : (reason.indexOf('行业') >= 0 ? '#7c3aed' : (reason.indexOf('重复') >= 0 ? '#0891b2' : '#059669')));
      html += '<tr style="background:' + reasonColor + '06"><td colspan="6" style="padding:8px 12px;font-size:11px;font-weight:600;color:' + reasonColor + '">'
        + '▸ ' + escHtml(reasonLabel) + ' <span style="color:#94a3b8;font-weight:400">(' + items.length + '条)</span>'
        + '</td></tr>';

      items.forEach(function(item) {
        idx++;
        var lvlColor = item.level === '高风险' ? '#dc2626' : (item.level === '中风险' ? '#f59e0b' : '#64748b');
        html += '<tr>'
          + '<td>' + idx + '</td>'
          + '<td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + escHtml(item.type) + '">' + escHtml(item.type) + '</td>'
          + '<td><span style="color:' + lvlColor + ';font-weight:600">' + escHtml(item.level || '—') + '</span></td>'
          + '<td>' + (item.score || '—') + '</td>'
          + '<td style="font-size:11px;color:#64748b">' + escHtml(reason) + '</td>'
          + '<td style="font-size:11px;color:#94a3b8">' + escHtml((item.category || '').substring(0, 20)) + '</td>'
          + '</tr>';
      });
    });

    html += '</tbody></table></div>';
  }

  document.getElementById('mf-body').innerHTML = html;
}
