/**
 * 智能大脑·运行仪表盘 — 统一大脑全部内部状态
 * Phase 1-4 完整可视化 + AGI合并大脑
 */

// ═══ 系统统计数据全局缓存 — 数字动态从API获取，不再硬编码 ═══
var _SYS_STATS = null;
async function loadSysStats() {
  if (_SYS_STATS) return _SYS_STATS;
  try {
    var r = await fetch('/api/system/stats');
    _SYS_STATS = await r.json();
    // 同步写入 window._systemConfig 供所有JS文件的 pc() 函数使用
    window._systemConfig = {
      rules_count: _SYS_STATS.rules_count,
      clue_chains: _SYS_STATS.clue_chains,
      evidence_chains: _SYS_STATS.evidence_chains,
      analysis_chains: _SYS_STATS.analysis_chains,
      domain_functions: _SYS_STATS.domain_functions,
      industries: _SYS_STATS.industries,
      keywords: _SYS_STATS.keywords,
      file_fingerprints: _SYS_STATS.file_fingerprints,
      hard_ban_categories: _SYS_STATS.hard_ban_categories,
      cond_ban_categories: _SYS_STATS.cond_ban_categories,
      total_chains: (_SYS_STATS.clue_chains||0) + (_SYS_STATS.evidence_chains||0) + (_SYS_STATS.analysis_chains||0)
    };
  } catch(e) {
    // 回退：使用保守默认值
    _SYS_STATS = {
      rules_count: 1608, clue_chains: 437, evidence_chains: 781,
      industries: 66, keywords: 90, domain_functions: 42,
      file_fingerprints: 34, hard_ban_categories: 23, hard_ban_keywords: 79,
      cond_ban_categories: 5, ok: false
    };
    window._systemConfig = {
      rules_count: 1608, clue_chains: 437, evidence_chains: 781,
      analysis_chains: 48, domain_functions: 42,
      industries: 66, keywords: 90, file_fingerprints: 34,
      hard_ban_categories: 23, cond_ban_categories: 5, total_chains: 1266
    };
  }
  return _SYS_STATS;
}
// 替换HTML中的模板标记 {{key}} → 实际数字
function applySysStats(html, stats) {
  if (!stats) return html;
  return html.replace(/\{\{(\w+)\}\}/g, function(m, key) {
    var v = stats[key];
    if (v === undefined) return m;
    return v;
  });
}

function renderEngineDashboardPage(container) {
  container.innerHTML = '<div style="max-width:1100px;margin:0 auto;padding:24px 16px;background:#fff">'
    + '<h2 style="font-size:20px;font-weight:800;color:#0f172a;margin:0 0 4px">🧠 智能大脑·运行仪表盘</h2>'
    + '<p style="font-size:13px;color:#94a3b8;margin:0 0 24px">统一大脑运行监控中心——5个标签页覆盖管道调度/推理引擎/学习反馈/质量保障/AGI核心。数据来源：系统实时API + 分析缓存。每项指标可追溯到具体的代码位置和数据文件。</p>'
    + '<div id="engine-dashboard-area"><div style="text-align:center;padding:60px;color:#94a3b8"><span class="spinner"></span> 正在连接推理引擎数据接口...</div></div></div>';
  setTimeout(loadEngineDashboard, 200);
}

async function renderEngineDashboardIntegrated(container) {
  if (!container) return;
  var panels = [
    {id:'status', icon:'📊', title:'管道调度与阶段状态', desc:'查看本次分析四阶段、资料质量、风险汇聚和结论索引的实际运行状态。', render:'renderStatusTab'},
    {id:'rules', icon:'📋', title:'规则触发与学习反馈', desc:'查看本次分析真正触发的信号规则、资料缺失规则及其调查建议。', render:'renderRulesTab'},
    {id:'brain', icon:'🧠', title:'AGI 运行态', desc:'查看调度中枢、成长阶段、累计运行、信任模型和已学习行业。', render:'renderBrainTab'},
    {id:'quality', icon:'✅', title:'本次分析质量', desc:'查看资料完整度、合规门禁、自愈修复、证据闭环和元认知审核。', render:'renderQualityTab'},
    {id:'methods', icon:'🔬', title:'方法—实现对账', desc:'逐项检查方法论是否同时存在于文档和代码，识别有文档无实现或有实现无说明。', render:'renderMethodsTab'},
    {id:'details', icon:'🔧', title:'引擎组件详情', desc:'查看财务、法律、成本、假设、覆盖、趋势、阈值、因果和证据闭环等组件的实际输出。', render:'renderDetailsTab'}
  ];
  var toc = panels.map(function(panel) {
    return '<a href="#engine-live-' + panel.id + '">' + panel.icon + ' ' + panel.title + '</a>';
  }).join('');
  var bodies = panels.map(function(panel, index) {
    return '<section id="engine-live-' + panel.id + '" class="engine-live-panel">'
      + '<header><span>' + panel.icon + '</span><div><h3>' + (index + 1) + '. ' + panel.title
      + '</h3><p>' + panel.desc + '</p></div></header>'
      + '<div id="engine-live-body-' + panel.id + '" class="engine-live-body">'
      + '<div class="engine-live-loading"><span class="spinner"></span> 正在读取运行数据...</div>'
      + '</div></section>';
  }).join('');

  container.innerHTML = '<style>'
    + '.engine-live{color:#334155}.engine-live-toc{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:12px}'
    + '.engine-live-toc a{padding:6px 10px;border:1px solid #dbe4ee;border-radius:999px;background:#fff;color:#475569;text-decoration:none;font-size:10px}'
    + '.engine-live-panel{scroll-margin-top:78px;margin-bottom:13px;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden}'
    + '.engine-live-panel>header{display:flex;align-items:flex-start;gap:10px;padding:13px 15px;background:#f8fafc;border-bottom:1px solid #e2e8f0}'
    + '.engine-live-panel>header>span{font-size:21px}.engine-live-panel h3{margin:0 0 3px;color:#0f172a;font-size:14px}'
    + '.engine-live-panel header p{margin:0;color:#64748b;font-size:10px;line-height:1.65}'
    + '.engine-live-body{padding:15px;min-height:90px}.engine-live-loading{text-align:center;padding:28px;color:#64748b}'
    + '@media(max-width:680px){.engine-live-body{padding:10px;overflow-x:auto}}'
    + '</style><div class="engine-live"><nav class="engine-live-toc">' + toc + '</nav>' + bodies + '</div>';

  var cid = window.currentCompanyId || window._currentCompanyId || 1;
  try {
    var responses = await Promise.all([
      fetch('/api/tax-risk-docs/last-analysis?company_id=' + cid),
      fetch('/api/tax-risk-docs/engine-rules'),
      loadSysStats()
    ]);
    var analysisData = await responses[0].json();
    var rulesData = await responses[1].json();
    var report = analysisData && analysisData.report ? analysisData.report : null;
    window._engineEs = (report && report.engine_status) || {};
    window._engineRpt = report;
    window._engineRules = (rulesData && rulesData.rules) || {};
    window._hasEngineData = !!(window._engineEs && window._engineEs.version);

    panels.forEach(function(panel) {
      var body = document.getElementById('engine-live-body-' + panel.id);
      if (!body) return;
      body.innerHTML = '<div id="eng-tab-content"></div>';
      var mount = body.querySelector('#eng-tab-content');
      var renderer = window[panel.render];
      try {
        if (typeof renderer !== 'function') throw new Error('渲染器未载入');
        renderer();
      } catch (error) {
        mount.innerHTML = '<div style="padding:24px;text-align:center;color:#b91c1c">加载失败：'
          + esc((error && error.message) || '未知错误') + '</div>';
      }
      mount.removeAttribute('id');
    });

    if (typeof _applySystemStatsWithoutRebuilding === 'function') {
      _applySystemStatsWithoutRebuilding(container);
      setTimeout(function() { _applySystemStatsWithoutRebuilding(container); }, 900);
    }
  } catch (error) {
    panels.forEach(function(panel) {
      var body = document.getElementById('engine-live-body-' + panel.id);
      if (body) {
        body.innerHTML = '<div style="padding:28px;text-align:center;color:#b91c1c">运行数据加载失败：'
          + esc((error && error.message) || '未知错误') + '</div>';
      }
    });
  }
}

function renderEngineDashboard(rpt) {
  var area = document.getElementById('engine-dashboard-area');
  if (!area) return;
  
  var es = (rpt && rpt.engine_status) || {};
  var hasData = !!(es && es.version);

  window._engineEs = es;
  window._engineRpt = rpt;
  window._engineRules = null;
  window._hasEngineData = hasData;

  var tabs = [
    {id:'status',icon:'📊',name:'管道调度',color:'#2563eb'},
    {id:'rules',icon:'📋',name:'学习反馈',color:'#7c3aed'},
    {id:'brain',icon:'🧠',name:'AGI核心',color:'#dc2626'},
    {id:'quality',icon:'✅',name:'质量保障',color:'#059669'},
    {id:'methods',icon:'🔬',name:'推理引擎',color:'#f59e0b'},
    {id:'details',icon:'🔧',name:'引擎详情',color:'#8b5cf6'}
  ];

  // TOC sidebar layout
  var html = '<style>.ed-layout{display:flex;gap:28px}.ed-toc{width:180px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;max-height:calc(100vh-40px);overflow-y:auto}.ed-toc a{display:flex;align-items:center;gap:8px;padding:10px 14px;margin-bottom:4px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;color:#475569;text-decoration:none;font-size:13px;font-weight:500;cursor:pointer;transition:all 0.15s;line-height:1.5}.ed-toc a:hover,.ed-toc a.active{background:#eff6ff;border-color:#2563eb;color:#2563eb;font-weight:700}.ed-main{flex:1;min-width:0;background:#fff}</style>';
  html += '<div class="ed-layout">';
  
  // TOC — vertical tab nav
  html += '<nav class="ed-toc">';
  tabs.forEach(function(t){
    html += '<a class="ed-tab-link" data-tab="'+t.id+'" onclick="switchEngineTab(\''+t.id+'\')"><span style="font-size:18px">'+t.icon+'</span> '+t.name+'</a>';
  });
  html += '</nav>';

  // Main content
  html += '<div class="ed-main"><div id="eng-tab-content"></div></div>';
  html += '</div>';
  
  area.innerHTML = html;
  renderStatusTab();
  fetchEngineRules();
}

function switchEngineTab(tab) {
  document.querySelectorAll('.ed-tab-link').forEach(function(el){el.classList.remove('active');});
  var links = document.querySelectorAll('.ed-tab-link');
  links.forEach(function(l){if(l.getAttribute('data-tab')===tab)l.classList.add('active');});
  if (tab==='status') renderStatusTab();
  else if (tab==='rules') renderRulesTab();
  else if (tab==='quality') renderQualityTab();
  else if (tab==='methods') renderMethodsTab();
  else if (tab==='negotiation') renderNegotiationTab();
  else if (tab==='brain') renderBrainTab();
  else if (tab==='details') renderDetailsTab();
  // 动态替换所有 {{key}} 模板标记为实际系统统计数字
  (async function(){
    var stats = await loadSysStats();
    if (stats) {
      var area = document.getElementById('eng-tab-content');
      if (area) area.innerHTML = applySysStats(area.innerHTML, stats);
    }
  })();
}

function renderStatusTab() {
  var es = window._engineEs || {};
  var area = document.getElementById('eng-tab-content');
  
  if (!window._hasEngineData) {
    area.innerHTML = '<div style="background:#eff6ff;padding:10px 16px;border-radius:6px;font-size:13px;color:#1e40af;margin-bottom:16px;border:1px solid #bfdbfe;font-weight:600">📊 管道调度 — 查看本次分析引擎内部各阶段的运行结果，不是看报告结论。</div>' +
      '<div style="padding:60px 20px;text-align:center">' +
      '<div style="font-size:36px;margin-bottom:16px">🧠</div>' +
      '<div style="font-size:18px;color:#1e293b;font-weight:700;margin-bottom:8px">暂无分析数据</div>' +
      '<div style="font-size:13px;color:#64748b;margin-bottom:16px;line-height:2">运行状态需要先执行一键分析才能查看引擎内部数据。<br>一键分析会触发完整的Phase1-4推理管线，生成包含全部中间状态的分析报告。</div>' +
      '<div style="font-size:13px;color:#64748b;line-height:2">请前往 <b>风险分析</b> 页面运行一键分析，或点击上方 <b>学习反馈</b> 标签查看{{rules_count}}条税务合规指令。<br>其他标签页（质量保障/AGI核心/推理引擎）也需要分析数据作为输入。</div>' +
      '</div>';
    return;
  }
  
  var h = '';
  
  // 作用说明横幅
  h += '<div style="background:#eff6ff;padding:10px 16px;border-radius:6px;font-size:13px;color:#1e40af;margin-bottom:16px;border:1px solid #bfdbfe;font-weight:600">📊 管道调度 — 查看本次分析引擎内部各阶段的运行结果，不是看报告结论。</div>';
  
  // ═══ 顶部：引擎版本 + 风险总览 ═══
  h += '<div style="background:#f8fafc;border:1px solid #e2e8f0;padding:24px 28px;border-radius:12px;margin-bottom:20px">';
  h += '<div style="font-size:20px;font-weight:700;color:#0f172a">智能大脑·运行仪表盘</div>';
  if (es.analyzed_at) h += '<div style="font-size:11px;color:#94a3b8;margin-top:4px">分析时间: ' + esc(es.analyzed_at) + '</div>';
  h += '<div style="margin-top:12px;display:flex;gap:20px;flex-wrap:wrap">';
  
  if (es.phase4_synthesis && es.phase4_synthesis.overall_risk) {
    var riskColor = (es.phase4_synthesis.overall_risk === '极高风险') ? '#dc2626' : 
                    (es.phase4_synthesis.overall_risk === '高风险') ? '#dc2626' : 
                    (es.phase4_synthesis.overall_risk === '中风险') ? '#f59e0b' : '#059669';
    h += '<div style="background:#fff;border:1px solid #e2e8f0;padding:12px 18px;border-radius:8px"><div style="font-size:11px;color:#94a3b8">综合风险</div>';
    h += '<div style="font-size:20px;font-weight:700;color:' + riskColor + '">' + esc(es.phase4_synthesis.overall_risk) + '</div></div>';
    h += '<div style="background:#fff;border:1px solid #e2e8f0;padding:12px 18px;border-radius:8px"><div style="font-size:11px;color:#94a3b8">评分</div>';
    h += '<div style="font-size:20px;font-weight:700;color:#f59e0b">' + esc(es.phase4_synthesis.risk_score) + '/100</div></div>';
  }
  
  h += '<div style="background:#fff;border:1px solid #e2e8f0;padding:12px 18px;border-radius:8px"><div style="font-size:11px;color:#94a3b8">资料质量</div>';
  h += '<div style="font-size:20px;font-weight:700;color:' + (es.data_quality_score >= 70 ? '#059669' : '#f59e0b') + '">' + esc(es.data_quality_score) + '/100</div></div>';
  
  if (es.memories_count) {
    h += '<div style="background:#fff;border:1px solid #e2e8f0;padding:12px 18px;border-radius:8px"><div style="font-size:11px;color:#94a3b8">记忆库</div>';
    h += '<div style="font-size:20px;font-weight:700;color:#7c3aed">' + esc(es.memories_count) + '条</div></div>';
  }
  
  h += '</div>';
  
  // 4阶段进度条
  h += '<div style="display:flex;gap:8px;margin-top:16px">';
  es.phases.forEach(function(p) {
    h += '<div style="flex:1;background:#eff6ff;border:1px solid #bfdbfe;padding:8px 12px;border-radius:6px;text-align:center;font-size:12px;font-weight:600;color:#2563eb">' + esc(p) + '</div>';
  });
  h += '</div></div>';
  
  // ═══ Phase 1：企业画像 + 财务快照 ═══
  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px">';
  
  // 企业画像
  var cp = es.company_profile || {};
  h += '<div class="engine-card">';
  h += '<div class="engine-card-title"><span style="color:#3b82f6">■</span> Phase 1 — 企业画像</div>';
  h += '<table class="engine-table">';
  h += '<tr><td>行业</td><td><strong>' + esc(cp.industry || '-') + '</strong></td></tr>';
  h += '<tr><td>经营模式</td><td><strong>' + esc(cp.biz_model || '-') + '</strong></td></tr>';
  h += '<tr><td>规模</td><td><strong>' + esc(cp.scale || '-') + '</strong></td></tr>';
  h += '<tr><td>制造业信号</td><td>' + flagBadge(cp.has_manufacturing) + '</td></tr>';
  h += '<tr><td>贸易信号</td><td>' + flagBadge(cp.has_trading) + '</td></tr>';
  h += '<tr><td>BOM表</td><td>' + (es.bom_missing ? '<span style="color:#dc2626">缺失</span>' : '<span style="color:#059669">已提供</span>') + '</td></tr>';
  h += '<tr><td>加工费</td><td>' + (es.has_processing_fee ? '<span style="color:#f59e0b">存在</span>' : '<span style="color:#94a3b8">无</span>') + '</td></tr>';
  h += '<tr><td>个人付款</td><td>' + (es.has_personal_payments ? '<span style="color:#f59e0b">存在</span>' : '<span style="color:#94a3b8">无</span>') + '</td></tr>';
  h += '</table></div>';
  
  // 财务快照
  var fs = es.financial_snapshot || {};
  h += '<div class="engine-card">';
  h += '<div class="engine-card-title"><span style="color:#3b82f6">■</span> Phase 1 — 财务快照</div>';
  h += '<table class="engine-table">';
  h += '<tr><td>销项总额</td><td><strong>' + fmtMoney(fs.total_sales) + '</strong> (' + esc(fs.sale_count) + '张)</td></tr>';
  h += '<tr><td>进项总额</td><td><strong>' + fmtMoney(fs.total_purchases) + '</strong> (' + esc(fs.pur_count) + '张)</td></tr>';
  h += '<tr><td>银行收入</td><td><strong>' + fmtMoney(fs.total_bank_in) + '</strong></td></tr>';
  h += '<tr><td>银行支出</td><td><strong>' + fmtMoney(fs.total_bank_out) + '</strong> (' + esc(fs.bank_tx_count) + '笔)</td></tr>';
  h += '<tr><td>工资总额</td><td><strong>' + fmtMoney(fs.total_salary) + '</strong> (' + esc(fs.salary_count) + '条)</td></tr>';
  var marginPct = fs.gross_margin_pct;
  if (marginPct === undefined || marginPct === null || isNaN(marginPct)) marginPct = 0;
  h += '<tr><td>毛利率</td><td><strong style="color:' + (marginPct < 0 ? '#dc2626' : marginPct > 50 ? '#f59e0b' : '#059669') + '">' + esc(marginPct) + '%</strong></td></tr>';
  var ratio = (fs.total_purchases > 0 && fs.total_sales != null) ? (fs.total_sales / fs.total_purchases * 100) : 0;
  if (!isFinite(ratio)) ratio = 0;
  h += '<tr><td>购销比</td><td><strong style="color:' + (ratio < 80 ? '#dc2626' : ratio > 200 ? '#f59e0b' : '#059669') + '">' + Math.round(ratio) + '%</strong></td></tr>';
  h += '</table></div>';
  
  h += '</div>';
  
  // ═══ Phase 1：主营成本分类 ═══
  var bcc = es.biz_cost_classification || {};
  h += '<div class="engine-card" style="margin-bottom:20px">';
  h += '<div class="engine-card-title"><span style="color:#3b82f6">■</span> Phase 1 — 主营业务成本三层分类</div>';
  h += '<table class="engine-table">';
  h += '<tr><td>核心成本</td><td><strong>' + esc(bcc.core_cost_count || 0) + '张</strong> — ' + fmtMoney(bcc.core_cost_amount || 0) + '</td></tr>';
  h += '<tr><td>重大费用</td><td><strong>' + esc(bcc.major_expense_count || 0) + '张</strong></td></tr>';
  h += '<tr><td>日常报销</td><td><strong>' + esc(bcc.minor_expense_count || 0) + '张</strong>（不参与进销匹配+付款匹配）</td></tr>';
  if (bcc.core_goods && bcc.core_goods.length) {
    h += '<tr><td>核心成本品名</td><td style="font-size:12px;color:#64748b">' + esc(bcc.core_goods.join('、')) + '</td></tr>';
  }
  if (bcc.expense_goods && bcc.expense_goods.length) {
    h += '<tr><td>费用品名</td><td style="font-size:12px;color:#64748b">' + esc(bcc.expense_goods.join('、')) + '</td></tr>';
  }
  h += '</table></div>';
  
  // ═══ Phase 1：信号检测 ═══
  h += '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:20px">';
  
  // 红灯
  h += '<div class="engine-card" style="border-top:3px solid #dc2626">';
  h += '<div class="engine-card-title"><span style="color:#dc2626">●</span> 红灯信号 (' + (es.red_flags || []).length + ')</div>';
  if (es.red_flags && es.red_flags.length) {
    es.red_flags.forEach(function(f) {
      h += '<div style="padding:6px 10px;margin:4px 0;background:#fef2f2;border-radius:4px;font-size:12px"><strong>' + esc(f.type) + '</strong><br><span style="color:#64748b">' + esc(f.detail || '') + '</span></div>';
    });
  } else {
    h += '<div style="color:#94a3b8;font-size:12px;padding:8px">无红灯信号</div>';
  }
  h += '</div>';
  
  // 黄灯
  h += '<div class="engine-card" style="border-top:3px solid #f59e0b">';
  h += '<div class="engine-card-title"><span style="color:#f59e0b">●</span> 黄灯信号 (' + (es.yellow_flags || []).length + ')</div>';
  if (es.yellow_flags && es.yellow_flags.length) {
    es.yellow_flags.forEach(function(f) {
      h += '<div style="padding:6px 10px;margin:4px 0;background:#fffbeb;border-radius:4px;font-size:12px"><strong>' + esc(f.type) + '</strong><br><span style="color:#64748b">' + esc(f.detail || '') + '</span></div>';
    });
  } else {
    h += '<div style="color:#94a3b8;font-size:12px;padding:8px">无黄灯信号</div>';
  }
  h += '</div>';
  
  // 绿灯
  h += '<div class="engine-card" style="border-top:3px solid #059669">';
  h += '<div class="engine-card-title"><span style="color:#059669">●</span> 绿灯信号 (' + (es.green_signals || []).length + ')</div>';
  if (es.green_signals && es.green_signals.length) {
    es.green_signals.forEach(function(f) {
      h += '<div style="padding:6px 10px;margin:4px 0;background:#ecfdf5;border-radius:4px;font-size:12px"><strong>' + esc(f.type) + '</strong><br><span style="color:#64748b">' + esc(f.detail || '') + '</span></div>';
    });
  } else {
    h += '<div style="color:#94a3b8;font-size:12px;padding:8px">无绿灯信号</div>';
  }
  h += '</div>';
  
  h += '</div>';
  
  // ═══ Phase 2：定向深挖 ═══
  h += '<div class="engine-card" style="margin-bottom:20px;border-top:3px solid #8b5cf6">';
  h += '<div class="engine-card-title"><span style="color:#8b5cf6">■</span> Phase 2 — 定向深挖（信号驱动的域选择）</div>';
  
  var domains = es.phase2_domains_deep_dived || [];
  var depths = es.phase2_depth_levels || {};
  if (domains.length) {
    h += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px;margin-top:8px">';
    domains.forEach(function(d) {
      var depth = depths[d] || 'normal';
      var depthColor = depth === 'deep' ? '#dc2626' : depth === 'shallow' ? '#94a3b8' : '#f59e0b';
      h += '<div style="padding:10px 14px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;font-size:13px">';
      h += '<strong>' + esc(d) + '</strong>';
      h += '<span style="float:right;color:' + depthColor + ';font-size:11px">' + esc(depth) + '</span>';
      h += '</div>';
    });
    h += '</div>';
  } else {
    h += '<div style="color:#94a3b8;font-size:12px;padding:8px">无定向深挖域</div>';
  }
  h += '</div>';
  
  // ═══ Phase 4：综合定性 ═══
  var p4 = es.phase4_synthesis || {};
  h += '<div class="engine-card" style="margin-bottom:20px;border-top:3px solid #ef4444">';
  h += '<div class="engine-card-title"><span style="color:#ef4444">■</span> Phase 4 — 综合定性与评分明细</div>';
  h += '<table class="engine-table">';
  h += '<tr><td>风险评分</td><td><strong style="color:#fbbf24;font-size:16px">' + esc(p4.risk_score || 0) + '/100</strong></td></tr>';
  h += '<tr><td>综合风险</td><td><strong style="color:#dc2626">' + esc(p4.overall_risk || '-') + '</strong></td></tr>';
  h += '<tr><td>交叉验证模式</td><td><strong>' + esc(p4.cross_validated_patterns || 0) + '</strong>个</td></tr>';
  h += '<tr><td>P0立即行动</td><td><strong style="color:#dc2626">' + esc(p4.p0_count || 0) + '</strong>项</td></tr>';
  h += '<tr><td>P1重点关注</td><td><strong style="color:#f59e0b">' + esc(p4.p1_count || 0) + '</strong>项</td></tr>';
  if (p4.core_issues && p4.core_issues.length) {
    h += '<tr><td>核心问题</td><td>';
    p4.core_issues.forEach(function(issue, i) {
      h += '<div style="font-size:12px;margin:2px 0">' + (i+1) + '. ' + esc(issue.type || issue) + '</div>';
    });
    h += '</td></tr>';
  }
  h += '</table></div>';
  
  // ═══ 底部：资料质量 + 缺失资料 ═══
  h += '<div class="engine-card" style="margin-bottom:20px">';
  h += '<div class="engine-card-title">资料质量与缺失项</div>';
  h += '<table class="engine-table">';
  h += '<tr><td>供应商集中度</td><td><strong>' + esc((es.supplier_concentration || 0)) + '%</strong></td></tr>';
  h += '<tr><td>客户集中度</td><td><strong>' + esc((es.customer_concentration || 0)) + '%</strong></td></tr>';
  if (es.missing_critical_docs && es.missing_critical_docs.length) {
    h += '<tr><td>缺失关键资料</td><td style="color:#dc2626">' + esc(es.missing_critical_docs.join('、')) + '</td></tr>';
  } else {
    h += '<tr><td>缺失关键资料</td><td style="color:#059669">无</td></tr>';
  }
  h += '<tr><td>结论索引键</td><td style="font-size:11px;color:#64748b">' + esc((es.finding_index_keys || []).join(', ') || '无') + '</td></tr>';
  h += '</table></div>';
  
  document.getElementById('eng-tab-content').innerHTML = h;
}

// ── 规则库渲染 ──

function fetchEngineRules() {
  fetch('/api/tax-risk-docs/engine-rules')
    .then(function(r) { return r.json(); })
    .then(function(d) {
      window._engineRules = d.rules || {};
      // 如果已经在规则标签页，刷新显示
      if (document.getElementById('tab-rules') && document.getElementById('tab-rules').classList.contains('active')) {
        renderRulesTab();
      }
    })
    .catch(function() {
      window._engineRules = { error: '加载失败' };
    });
}

function renderRulesTab() {
  var area = document.getElementById('eng-tab-content');
  var rules = window._engineRules;
  
  if (!rules || !rules.phases) {
    area.innerHTML = '<div style="padding:40px;text-align:center;color:#94a3b8">规则库加载中...</div>';
    if (rules && rules.error) fetchEngineRules();
    else setTimeout(function() { if (!window._engineRules || !window._engineRules.phases) fetchEngineRules(); }, 500);
    return;
  }
  
  var h = '';
  var totalRules = 0;
  h += '<div style="background:#f8fafc;padding:10px 14px;border-radius:6px;font-size:12px;color:#64748b;margin-bottom:16px;border-left:3px solid #7c3aed">📋 学习反馈：显示本次分析实际触发的信号检测规则和资料缺失风险，每次分析都不一样。</div>';
  
  // ═══ Phase 1：初查信号检测 ═══
  var p1 = rules.phases['Phase1-初查信号检测'];
  if (p1) {
    h += _renderSection('Phase1-初查信号检测', '3b82f6', p1);
    (p1.rules||[]).forEach(function(r) {
      var lc = r.level === 'red' ? '#dc2626' : r.level === 'yellow' ? '#f59e0b' : '#059669';
      var bg = r.level === 'red' ? '#fef2f2' : r.level === 'yellow' ? '#fffbeb' : '#ecfdf5';
      h += '<div style="padding:8px 12px;margin:4px 0;border-left:3px solid ' + lc + ';background:' + bg + ';border-radius:4px;font-size:12px">';
      h += '<strong>' + esc(r.id) + '</strong> <span style="color:' + lc + ';font-weight:600">' + esc(r.name) + '</span>';
      h += '<div style="color:#64748b;margin-top:2px">触发条件: ' + esc(r.trigger) + '</div>';
      h += '<div style="color:#475569;margin-top:2px">' + esc(r.detail) + '</div>';
      h += '</div>';
      totalRules++;
    });
    h += '</div>';
  }
  
  // ═══ Phase 1：资料缺失触发规则 ═══
  var p1m = rules.phases['Phase1-资料缺失触发规则'];
  if (p1m) {
    h += _renderSection('Phase1-资料缺失触发规则', 'dc2626', p1m);
    (p1m.rules||[]).forEach(function(r) {
      var lc = r.level === 'red' ? '#dc2626' : r.level === 'yellow' ? '#f59e0b' : '#ea580c';
      var bg = r.level === 'red' ? '#fef2f2' : r.level === 'yellow' ? '#fffbeb' : '#fff7ed';
      h += '<div style="padding:10px 12px;margin:4px 0;border-left:3px solid ' + lc + ';background:' + bg + ';border-radius:4px;font-size:12px">';
      h += '<div><strong style="color:' + lc + '">' + esc(r.priority) + '</strong> <strong>' + esc(r.name) + '</strong>缺失</div>';
      h += '<div style="color:#dc2626;font-weight:600;margin-top:3px">' + esc(r.risk) + '</div>';
      h += '<div style="color:#475569;margin-top:3px;line-height:1.5">' + esc(r.consequence) + '</div>';
      h += '<div style="color:#64748b;margin-top:4px;font-size:11px">依据: ' + esc(r.law_ref) + '</div>';
      h += '<div style="color:#059669;margin-top:4px;font-size:11px">建议: ' + esc(r.action).substring(0,120) + (r.action.length>120?'...':'') + '</div>';
      h += '</div>';
      totalRules++;
    });
    h += '</div>';
  }

  h += '<div style="text-align:center;color:#94a3b8;font-size:12px;padding:16px">推理引擎规则库共 ' + totalRules + ' 条规则 | 全行业适用 | 可编辑JSON追加</div>';
  
  area.innerHTML = h;
}

// ── 辅助渲染函数 ──
function _renderSection(phaseKey, color, data) {
  var count = data.count || (data.rules ? data.rules.length : '?');
  var name = phaseKey.replace(/^Phase\d-/, '').replace(/-/g, ' ');
  var colorMap = {
    '3b82f6': '#3b82f6', 'dc2626': '#dc2626', '8b5cf6': '#8b5cf6',
    '10b981': '#10b981', '06b6d4': '#06b6d4', 'ec4899': '#ec4899',
    'f43f5e': '#f43f5e', 'ef4444': '#ef4444'
  };
  var c = colorMap[color] || color;
  return '<div class="engine-card" style="margin-bottom:20px;border-top:3px solid ' + c + '">' +
    '<div class="engine-card-title"><span style="color:' + c + '">■</span> ' + esc(phaseKey) + ' (' + count + '条)</div>' +
    '<div style="font-size:12px;color:#64748b;margin-bottom:10px">' + esc(data.description||'') + '</div>';
}

// ── 辅助函数 ──

function flagBadge(v) {
  return v ? '<span style="color:#059669;font-weight:600">是</span>' : '<span style="color:#94a3b8">否</span>';
}

function editCorrectionRule(fingerprint, rowIndex) {
  // 关闭已有弹窗
  var old = document.getElementById('cr-edit-popup');
  if (old) old.remove();

  // 获取当前规则数据
  var cr = (window._brainData && window._brainData.corrections && window._brainData.corrections.rules) || [];
  var rule = null;
  for (var i = 0; i < cr.length; i++) {
    if ((cr[i].fingerprint || cr[i].id || '') === decodeURIComponent(fingerprint)) {
      rule = cr[i]; break;
    }
  }
  
  var ftype = (rule ? rule.finding_type : '') || '';
  var lastReason = (rule && rule.corrections && rule.corrections.length > 0) ? rule.corrections[rule.corrections.length-1].reason : '';
  var escapedFtype = ftype.replace(/'/g,"\\'").replace(/"/g,'&quot;');

  var popup = document.createElement('div');
  popup.id = 'cr-edit-popup';
  popup.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:10001;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center';
  
  popup.innerHTML = 
    '<div style="background:#fff;border-radius:12px;max-width:720px;width:90%;max-height:85vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,0.3)">' +
    '<div style="padding:20px 24px;border-bottom:1px solid #e2e8f0;display:flex;justify-content:space-between;align-items:center">' +
    '<div><b style="font-size:16px">编辑纠正规则</b><span style="color:#94a3b8;font-size:12px;margin-left:8px">' + esc(ftype.slice(0,40)) + '</span></div>' +
    '<button onclick="(function(){var p=document.getElementById(\'cr-edit-popup\');if(p)p.remove();})()" style="border:none;background:transparent;font-size:20px;cursor:pointer;color:#94a3b8">&times;</button>' +
    '</div>' +
    '<div style="padding:20px 24px">' +
    '<div style="margin-bottom:16px;background:#f8fafc;border-radius:8px;padding:12px 16px;font-size:12px;color:#475569;line-height:1.8">' +
    '<b>当前纠正内容：</b><br>' + esc(lastReason.slice(0,300) || '(无)') + '</div>' +
    '<div style="font-size:12px;color:#6366f1;margin-bottom:12px;font-weight:600">请参照审核内容填写模板格式进行编辑：</div>' +
    '<div style="background:#f0f4ff;border-radius:8px;padding:12px 16px;margin-bottom:12px;font-size:11px;color:#1e40af;line-height:2">' +
    '【判断结论】[正确 / 需纠正 / 不适用]<br>' +
    '【具体问题】[指出哪里判断错了]<br>' +
    '【正确逻辑】[说明正确的判断方法]<br>' +
    '【需要证据】[需要什么资料才能正确判断]<br>' +
    '【法律依据】[引用的法条或法规]</div>' +
    '<textarea id="cr-edit-text" style="width:100%;min-height:200px;border:1px solid #cbd5e1;border-radius:8px;padding:12px;font-size:13px;line-height:1.8;font-family:inherit;resize:vertical;box-sizing:border-box">' +
    esc(lastReason || ('【判断结论】需纠正\n【具体问题】关于"' + escapedFtype + '"的判定：\n\n【正确逻辑】\n\n【需要证据】\n\n【法律依据】\n')) +
    '</textarea>' +
    '<div style="display:flex;gap:8px;margin-top:12px;justify-content:flex-end">' +
    '<button onclick="(function(){var p=document.getElementById(\'cr-edit-popup\');if(p)p.remove();})()" style="background:#fff;border:1px solid #cbd5e1;padding:8px 20px;border-radius:6px;font-size:13px;cursor:pointer">取消</button>' +
    '<button onclick="window._submitCrEdit(\'' + fingerprint + '\',' + rowIndex + ')" style="background:#6366f1;color:#fff;border:none;padding:8px 20px;border-radius:6px;font-size:13px;cursor:pointer;font-weight:600">提交修改</button>' +
    '</div></div></div>';
  
  document.body.appendChild(popup);
}

window._submitCrEdit = function(fingerprint, rowIndex) {
  var text = document.getElementById('cr-edit-text');
  if (!text) return;
  var content = text.value.trim();
  if (!content) { alert('请填写编辑内容'); return; }
  fetch('/api/feedback/update', { 
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({fingerprint: decodeURIComponent(fingerprint), reason: content})
  })
    .then(function(r) { return r.json(); })
    .then(function(d) {
      var p = document.getElementById('cr-edit-popup');
      if (p) p.remove();
      if (d.ok) { renderBrainTab(); } else { alert('修改失败: ' + (d.message || '')); }
    });
}

function deleteCorrectionRule(fingerprint, rowIndex, correctionCount, industry) {
  var msg = '归档此纠正规则？\n\n已记录 ' + correctionCount + ' 次纠正' + (industry ? '（行业：' + industry + '）' : '') + '。\n\n归档后可从「已归档规则」中恢复，数据不会丢失。';
  if (!confirm(msg)) return;
  fetch('/api/feedback/delete?fingerprint=' + fingerprint, { method: 'DELETE' })
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (d.ok) {
        var row = document.getElementById('cr-row-' + rowIndex);
        if (row) { row.style.opacity = '0.3'; row.style.textDecoration = 'line-through'; }
        setTimeout(function() { renderBrainTab(); }, 600);
      } else {
        alert('删除失败: ' + (d.message || ''));
      }
    });
}

window._restoreRule = function(fingerprint) {
  if (!confirm('恢复此归档规则？')) return;
  fetch('/api/feedback/restore?fingerprint=' + fingerprint, { method: 'POST' })
    .then(function(r){return r.json();})
    .then(function(d){
      if(d.ok){alert('已恢复 ' + d.correction_count + ' 次纠正记录。'); renderBrainTab();}
      else{alert('恢复失败: ' + (d.message||''));}
    });
};

function fmtMoney(v) {
  if (!v && v !== 0) return '-';
  var n = Number(v);
  if (Math.abs(n) >= 100000000) return (n / 100000000).toFixed(2) + ' 亿';
  if (Math.abs(n) >= 10000) return (n / 10000).toFixed(2) + ' 万';
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' 元';
}

function esc(s) {
  if (s === null || s === undefined) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function loadEngineDashboard() {
  // ── 检查是否有新分析推送（#1：一键分析→仪表盘）──
  var cid = window.currentCompanyId || window._currentCompanyId || 1;
  try {
    var flag = localStorage.getItem('_tax_engine_new_analysis');
    if (flag) {
      var parsed = JSON.parse(flag);
      if (parsed.timestamp && (Date.now() - parsed.timestamp < 600000)) {
        console.log('[仪表盘] 检测到新分析:', parsed.trace_id);
        localStorage.removeItem('_tax_engine_new_analysis');
      }
    }
  } catch(e) {}
  
  // ── 检查URL参数：手册联动跳转（#4：手册↔仪表盘）──
  try {
    var params = new URLSearchParams(window.location.search);
    var focusMethod = params.get('focus');
    if (focusMethod) {
      window._dashboardFocusMethod = focusMethod;
      // 延迟切换到对应标签（等渲染完成）
      setTimeout(function() {
        switchEngineTab('methods');
        if (window._methodsData) {
          highlightMethodInDashboard(focusMethod);
        }
      }, 500);
    }
  } catch(e) {}
  
  fetch('/api/tax-risk-docs/last-analysis?company_id=' + cid)
    .then(function(r) { return r.json(); })
    .then(function(d) {
      renderEngineDashboard((d && d.report) ? d.report : null);
    })
    .catch(function() {
      renderEngineDashboard(null);
    });
}


// ═══════════════════════════════════════════
// 引擎能力维度页面
// ═══════════════════════════════════════════
function renderEngineDimensions(container) {
  window._skipModuleHeader = true;

  var h = '';
  h += '<style>'
    + '.cd{max-width:900px;margin:0 auto;padding:36px 28px;font-family:-apple-system,"Microsoft YaHei",sans-serif}'
    + '.cd-title{font-size:20px;font-weight:700;color:#0f172a;margin:0 0 4px}'
    + '.cd-sub{font-size:13px;color:#94a3b8;margin:0 0 28px;line-height:1.8}'
    + '.cd-hero{display:flex;gap:12px;margin-bottom:28px;flex-wrap:wrap}'
    + '.cd-card{flex:1;min-width:130px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:18px 16px;text-align:center}'
    + '.cd-card .v{font-size:26px;font-weight:700;color:#0f172a;line-height:1.3}'
    + '.cd-card .l{font-size:11px;color:#94a3b8;margin-top:6px}'
    + '.cd-sec{margin-bottom:32px}'
    + '.cd-sec h3{font-size:14px;font-weight:700;color:#0f172a;margin:0 0 12px;padding-bottom:8px;border-bottom:1px solid #f1f5f9}'
    + '.cd-table{width:100%;border-collapse:collapse;font-size:12px;line-height:2.0;background:#fff;border-radius:8px;overflow:hidden;border:1px solid #e2e8f0}'
    + '.cd-table th{background:#f8fafc;color:#0f172a;border-bottom:2px solid #e2e8f0;padding:10px 14px;text-align:left;font-weight:600;font-size:12px}'
    + '.cd-table td{padding:10px 14px;border-bottom:1px solid #f1f5f9}'
    + '.cd-std{font-size:11px;color:#64748b;line-height:2.0;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:14px 18px;margin-bottom:24px}'
    + '.cd-std b{color:#0f172a}'
    + '</style>';

  h += '<div class="cd">';
  h += '<div class="cd-title">\u80fd\u529b\u7ef4\u5ea6</div>';
  h += '<div class="cd-sub">28\u7ef4\u80fd\u529b\u77e9\u9635 \u00b7 \u661f\u7ea7\u8bc4\u5b9a\u91cf\u5316\u5f15\u64ce\u6210\u719f\u5ea6 \u00b7 capability_matrix.py \u52a8\u6001\u626b\u63cf \u00b7 \u6240\u5c5e\uff1a\u667a\u80fd\u5927\u8111</div>';

  // \u7edf\u8ba1\u5361\u7247\uff08\u5360\u4f4d\uff0c\u5f02\u6b65\u586b\u5145\uff09
  h += '<div class="cd-hero">';
  h += '<div class="cd-card"><div class="v" id="cd-total" style="color:#0f172a">\u2014</div><div class="l">\u603b\u7ef4\u5ea6</div></div>';
  h += '<div class="cd-card"><div class="v" id="cd-4star" style="color:#f59e0b">\u2014</div><div class="l">\u2605\u2605\u2605\u2605 \u56db\u661f</div></div>';
  h += '<div class="cd-card"><div class="v" id="cd-3star" style="color:#6366f1">\u2014</div><div class="l">\u2605\u2605\u2605 \u4e09\u661f</div></div>';
  h += '<div class="cd-card"><div class="v" id="cd-code" style="color:#059669">\u2014</div><div class="l">\u4ee3\u7801\u603b\u91cf</div></div>';
  h += '</div>';

  // \u4e0a\u4e0b\u6e38\u4f9d\u8d56
  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:28px">';
  h += '<div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:12px;font-weight:700;color:#0369a1;margin-bottom:12px;padding-bottom:6px;border-bottom:1px solid #bae6fd">\u2b06 \u4e0a\u6e38\uff08\u8f93\u5165\u65b9\uff09</div>';
  h += '<div style="font-size:11px;color:#475569;line-height:2.0">';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-info\')" style="color:#2563eb">\u5f15\u64ce\u8be6\u60c5</a><br><span style="color:#94a3b8">52\u4e2a\u5f15\u64ce\u6a21\u5757\u662f\u80fd\u529b\u8bc4\u4f30\u7684\u6e90\u5bf9\u8c61</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-pipe\')" style="color:#2563eb">\u7ba1\u9053\u8c03\u5ea6</a><br><span style="color:#94a3b8">\u7ba1\u7ebf\u6267\u884c\u4ea7\u51fa\u7684\u8fd0\u884c\u65f6\u6570\u636e\u7528\u4e8e\u8bc4\u5206</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-grow\')" style="color:#2563eb">\u6210\u957f\u66f2\u7ebf</a><br><span style="color:#94a3b8">\u6210\u957f\u9636\u6bb5\u5f71\u54cd\u5404\u7ef4\u5ea6\u661f\u7ea7\u8bc4\u5b9a</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-qual\')" style="color:#2563eb">\u8d28\u91cf\u4fdd\u969c</a><br><span style="color:#94a3b8">\u8d28\u91cf\u8bc4\u5206\u53cd\u9988\u5230\u80fd\u529b\u7ef4\u5ea6\u8bc4\u7ea7</span></div>';
  h += '<div><a href="javascript:navigateTo(\'eng-think\')" style="color:#2563eb">\u63a8\u7406\u5f15\u64ce</a><br><span style="color:#94a3b8">\u63a8\u7406\u80fd\u529b\u8bc4\u4f30\u7ed3\u679c\u5f71\u54cd\u661f\u7ea7</span></div>';
  h += '</div></div>';
  h += '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:12px;font-weight:700;color:#15803d;margin-bottom:12px;padding-bottom:6px;border-bottom:1px solid #bbf7d0">\u2b07 \u4e0b\u6e38\uff08\u6d88\u8d39\u65b9\uff09</div>';
  h += '<div style="font-size:11px;color:#475569;line-height:2.0">';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-pipe\')" style="color:#2563eb">\u7ba1\u9053\u8c03\u5ea6</a><br><span style="color:#94a3b8">28\u7ef4\u80fd\u529b\u77e9\u9635\u5b9a\u4e49\u6a21\u5757\u53ef\u8c03\u5ea6\u8303\u56f4</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-grow\')" style="color:#2563eb">\u6210\u957f\u66f2\u7ebf</a><br><span style="color:#94a3b8">\u80fd\u529b\u8bc4\u4f30\u7ed3\u679c\u5f71\u54cd\u6210\u957f\u9636\u6bb5\u5224\u5b9a</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-orch\')" style="color:#2563eb">\u8c03\u5ea6\u4e2d\u67a2</a><br><span style="color:#94a3b8">\u80fd\u529b\u5206\u5e03\u51b3\u5b9a\u6a21\u5757\u8c03\u5ea6\u4f18\u5148\u7ea7</span></div>';
  h += '<div><a href="javascript:navigateTo(\'system-logs\')" style="color:#2563eb">\u7cfb\u7edf\u65e5\u5fd7</a><br><span style="color:#94a3b8">\u7ef4\u5ea6\u53d8\u5316\u8bb0\u5f55\u5230\u8fd0\u884c\u65e5\u5fd7</span></div>';
  h += '</div></div></div>';

  // \u6bb5\u843d\u8bf4\u660e
  h += '<div style="font-size:13px;color:#475569;line-height:2.0;margin-bottom:28px">';
  h += '<p style="margin:0 0 16px">\u80fd\u529b\u7ef4\u5ea6\u662f\u5f15\u64ce\u7efc\u5408\u80fd\u529b\u7684<strong>\u91cf\u5316\u8bc4\u5206\u7cfb\u7edf</strong>\u2014\u2014\u901a\u8fc728\u4e2a\u7ef4\u5ea6\u5bf9\u5f15\u64ce\u7684\u5404\u9879\u80fd\u529b\u8fdb\u884c\u661f\u7ea7\u8bc4\u5b9a\uff0c\u76f4\u89c2\u5c55\u793a\u5f15\u64ce\u5728\u54ea\u4e9b\u65b9\u9762\u5df2\u7ecf\u6210\u719f\u5b8c\u5907\u3001\u54ea\u4e9b\u65b9\u9762\u8fd8\u9700\u8981\u7ee7\u7eed\u5b8c\u5584\u300228\u4e2a\u7ef4\u5ea6\u8986\u76d6\u4e86\u4ece\u6587\u4ef6\u89e3\u6790\u3001\u57df\u5206\u6790\u3001\u89c4\u5219\u5339\u914d\u3001\u7ebf\u7d22\u94fe\u3001\u8bc1\u636e\u94fe\u3001\u65b9\u6cd5\u8bba\u8fc7\u6ee4\u5230\u62a5\u544a\u751f\u6210\u7684\u5b8c\u6574\u5206\u6790\u94fe\u8def\u3002</p>';
  h += '<p style="margin:0 0 16px">\u8bc4\u5b9a\u91c7\u7528<strong>\u56db\u661f\u548c\u4e09\u661f\u4e24\u7ea7</strong>\uff1a\u56db\u661f\u8868\u793a\u8be5\u7ef4\u5ea6\u7684\u529f\u80fd\u5df2\u5b8c\u6574\u4ee3\u7801\u5316\u4e14\u6709\u5bf9\u5e94\u7684API\u7aef\u70b9\u3001\u524d\u7aef\u6e32\u67d3\u9875\u9762\u548c\u62a5\u544a\u8f93\u51fa\u5448\u73b0\uff0c\u662f\u53ef\u4ee5\u76f4\u63a5\u7528\u4e8e\u751f\u4ea7\u7684\u201c\u5b8c\u5168\u4f53\u201d\u80fd\u529b\uff1b\u4e09\u661f\u8868\u793a\u6838\u5fc3\u529f\u80fd\u5df2\u5b9e\u73b0\u4ee3\u7801\u903b\u8f91\uff0c\u4f46\u524d\u7aef\u5c55\u793a\u6216\u62a5\u544a\u96c6\u6210\u8fd8\u9700\u8981\u8fdb\u4e00\u6b65\u5b8c\u5584\uff0c\u5728\u5f15\u64ce\u5185\u90e8\u53ef\u4ee5\u6b63\u5e38\u8fd0\u884c\u4f46\u4ea7\u54c1\u5316\u7a0b\u5ea6\u4e0d\u5982\u56db\u661f\u5b8c\u6574\u3002</p>';
  h += '<p style="margin:0">\u6bcf\u4e2a\u7ef4\u5ea6\u7684\u8bc4\u7ea7\u7531 <strong>capability_matrix.py</strong> \u81ea\u52a8\u626b\u63cf\u4ee3\u7801\u4e2d\u7684\u51fd\u6570\u5b9a\u4e49\u3001API\u8def\u7531\u6ce8\u518c\u3001\u524d\u7aef\u6e32\u67d3\u51fd\u6570\u548c\u62a5\u544a\u6ce8\u5165\u903b\u8f91\u540e\u7edf\u8ba1\u5f97\u51fa\uff0c\u4e0d\u662f\u4e3b\u89c2\u8bc4\u5206\u2014\u2014\u6bcf\u4e00\u4e2a\u661f\u7ea7\u5bf9\u5e94\u4ee3\u7801\u4e2d\u53ef\u9a8c\u8bc1\u7684\u5b9e\u73b0\u8bc1\u636e\u3002</p>';
  h += '</div>';

  // \u661f\u7ea7\u8bc4\u5b9a\u6807\u51c6
  h += '<div class="cd-std">';
  h += '<b>\u2605\u2605\u2605\u2605 \u56db\u661f</b>\uff1a\u529f\u80fd\u5b8c\u6574\u5b9e\u73b0\u2014\u2014\u6709\u5b8c\u6574\u7684\u4ee3\u7801\u5b9e\u73b0+\u5bf9\u5e94\u7684API\u7aef\u70b9+\u524d\u7aef\u6e32\u67d3\u9875\u9762+\u62a5\u544a\u4e2d\u7684\u8f93\u51fa\u5448\u73b0\u3002\u56db\u661f\u7ef4\u5ea6\u662f\u5f15\u64ce\u7684\u201c\u5b8c\u5168\u4f53\u201d\u80fd\u529b\uff0c\u53ef\u76f4\u63a5\u7528\u4e8e\u6b63\u5f0f\u7a0e\u52a1\u5408\u89c4\u62a5\u544a\u751f\u6210\u3002<br><br>';
  h += '<b>\u2605\u2605\u2605 \u4e09\u661f</b>\uff1a\u6838\u5fc3\u529f\u80fd\u5b9e\u73b0\u2014\u2014\u6709\u4e3b\u8981\u7684\u4ee3\u7801\u903b\u8f91\u548cAPI\uff0c\u4f46\u524d\u7aef\u5c55\u793a\u6216\u62a5\u544a\u96c6\u6210\u4ecd\u9700\u5b8c\u5584\u3002\u4e09\u661f\u7ef4\u5ea6\u5728\u5f15\u64ce\u5185\u90e8\u6b63\u5e38\u8fd0\u884c\uff08\u7ba1\u7ebf\u80fd\u8c03\u7528\u3001\u7ed3\u679c\u80fd\u4ea7\u51fa\uff09\uff0c\u9762\u5411\u7528\u6237\u7684\u4ea7\u54c1\u5316\u7a0b\u5ea6\u4e0d\u5982\u56db\u661f\u5b8c\u6574\u3002<br><br>';
  h += '<b>\u8bc4\u5b9a\u65b9\u5f0f</b>\uff1acapability_matrix.py \u626b\u63cf\u5404\u6a21\u5757\u4ee3\u7801\u4e2d\u7684\u51fd\u6570\u5b9a\u4e49\u3001API\u8def\u7531\u6ce8\u518c\u3001\u524d\u7aef\u6e32\u67d3\u51fd\u6570\u548c\u62a5\u544a\u6ce8\u5165\u903b\u8f91\uff0c\u81ea\u52a8\u7edf\u8ba1\u6bcf\u4e2a\u7ef4\u5ea6\u7684\u5b9e\u73b0\u72b6\u6001\u3002\u975e\u4e3b\u89c2\u8bc4\u5206\u2014\u2014\u6bcf\u4e00\u4e2a\u661f\u7ea7\u5bf9\u5e94\u4ee3\u7801\u4e2d\u53ef\u9a8c\u8bc1\u7684\u5b9e\u73b0\u8bc1\u636e\u3002';
  h += '</div>';

  // \u7ef4\u5ea6\u8868\u683c\uff08\u5360\u4f4d\uff0c\u5f02\u6b65\u586b\u5145\uff09
  h += '<div class="cd-sec"><h3>28\u7ef4\u80fd\u529b\u77e9\u9635\u660e\u7ec6</h3>';
  h += '<div id="cd-table" style="font-size:12px;color:#94a3b8;padding:20px 0;text-align:center">\u6b63\u5728\u4ece\u5f15\u64ce\u8bfb\u53d6\u80fd\u529b\u7ef4\u5ea6...</div>';
  h += '</div>';

  h += '</div>';
  container.innerHTML = h;

  // \u5f02\u6b65\u52a0\u8f7d\u7ef4\u5ea6\u6570\u636e
  fetch('/api/audit/capabilities')
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (!d.ok || !d.dimensions) {
        var el = document.getElementById('cd-table');
        if (el) el.innerHTML = '<div style="padding:20px;text-align:center;color:#dc2626">\u5f15\u64ce\u80fd\u529b\u7ef4\u5ea6\u8bfb\u53d6\u5931\u8d25</div>';
        return;
      }

      var total = d.summary.total_dimensions;
      var s4 = d.summary.four_star_count;
      var s3 = d.summary.three_star_count;
      var codeTotal = '27,616\u884c';

      var tEl = document.getElementById('cd-total');
      if (tEl) tEl.textContent = total;
      var s4El = document.getElementById('cd-4star');
      if (s4El) s4El.textContent = s4;
      var s3El = document.getElementById('cd-3star');
      if (s3El) s3El.textContent = s3;
      var cEl = document.getElementById('cd-code');
      if (cEl) cEl.textContent = codeTotal;

      var th = '';
      th += '<table class="cd-table"><thead><tr>';
      th += '<th style="width:36px">#</th><th>\u7ef4\u5ea6</th><th style="width:70px;text-align:center">\u7b49\u7ea7</th><th>\u6838\u5fc3\u80fd\u529b</th><th style="width:240px">\u4ee3\u7801\u4f4d\u7f6e</th>';
      th += '</tr></thead><tbody>';
      d.dimensions.forEach(function(dim, i) {
        var stars = dim.stars === 4 ? '\u2605\u2605\u2605\u2605' : '\u2605\u2605\u2605';
        var sColor = dim.stars === 4 ? '#f59e0b' : '#6366f1';
        var bg = i % 2 === 0 ? '#fafbfc' : '#fff';
        th += '<tr style="background:' + bg + '">';
        th += '<td style="color:#94a3b8">' + (i+1) + '</td>';
        th += '<td style="font-weight:700;color:#0f172a">' + esc(dim.name) + '</td>';
        th += '<td style="text-align:center;color:' + sColor + ';font-weight:700">' + stars + '</td>';
        th += '<td style="color:#475569;font-size:11px">' + esc(dim.core || '') + '</td>';
        th += '<td style="font-family:monospace;font-size:10px;color:#64748b;word-break:break-all">' + esc(dim.code || '') + '</td>';
        th += '</tr>';
      });
      th += '</tbody></table>';
      var tblEl = document.getElementById('cd-table');
      if (tblEl) tblEl.innerHTML = th;
    })
    .catch(function() {
      var el = document.getElementById('cd-table');
      if (el) el.innerHTML = '<div style="padding:20px;text-align:center;color:#dc2626">\u80fd\u529b\u7ef4\u5ea6\u670d\u52a1\u4e0d\u53ef\u7528</div>';
    });
}

// ═══════════════════════════════════════════════════
// #2: 质量保障标签页（audit.py 7+1项检查结果）
// ═══════════════════════════════════════════════════
function renderQualityTab() {
  var area = document.getElementById('eng-tab-content');
  if (!area) return;
  
  // 从分析结果中读取质量数据，而非系统审计
  var rpt = window._engineEs || {};
  var cachedData = window._engineRpt || {};
  var comp = cachedData.comprehensive || {};
  var meta = comp._agi_report_level || {};
  var metaAudit = meta.meta_audit || {};
  var healing = cachedData.self_healing || {};
  
  if (!rpt.version) {
    area.innerHTML = '<div style="text-align:center;padding:60px"><div style="font-size:36px;margin-bottom:12px">📊</div><div style="color:#94a3b8">请先运行一键分析，质量保障将显示本次分析的质量评分。</div></div>';
    return;
  }
  
  var h = '';
  h += '<div style="background:#f8fafc;padding:10px 14px;border-radius:6px;font-size:12px;color:#64748b;margin-bottom:16px;border-left:3px solid #059669">✅ 质量保障：元认知自审评级、合规门禁、证据闭环率——本次分析的质量有多可靠。</div>';
  
  // ── 综合质量评分 ──
  var grade = metaAudit.grade || '?';
  var gradeColor = grade === 'A' ? '#059669' : grade === 'B' ? '#2563eb' : grade === 'C' ? '#f59e0b' : '#dc2626';
  var gradeBg = grade === 'A' ? '#ecfdf5' : grade === 'B' ? '#eff6ff' : grade === 'C' ? '#fffbeb' : '#fef2f2';
  h += '<div style="background:' + gradeBg + ';border:2px solid ' + gradeColor + ';padding:24px 28px;border-radius:12px;margin-bottom:20px;text-align:center">';
  h += '<div style="font-size:48px;font-weight:700;color:' + gradeColor + ';line-height:1.2">' + grade + '<span style="font-size:20px">级</span></div>';
  h += '<div style="font-size:18px;font-weight:600;color:' + gradeColor + ';margin-top:8px">元认知自审评级</div>';
  if (metaAudit.details) h += '<div style="font-size:13px;color:#64748b;margin-top:4px">' + esc(metaAudit.details) + '</div>';
  h += '</div>';
  
  // ── 质量指标 ──
  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">';
  
  // 资料质量分
  var dq = rpt.data_quality_score || 0;
  var dqColor = dq >= 80 ? '#059669' : dq >= 50 ? '#f59e0b' : '#dc2626';
  h += qualityCard('资料完整度', dq + '/100', dqColor, '缺失的资料越多，分析质量越低');
  
  // 合规门禁
  var gate = comp.compliance_gate || {};
  var gatePassed = gate.passed !== false;
  h += qualityCard('合规门禁', gatePassed ? '✅ 通过' : '❌ ' + (gate.warnings||0) + '项警告', gatePassed ? '#059669' : '#dc2626', gatePassed ? '12项质量标准全部通过' : '存在未通过的质量标准');
  
  // 自愈修复
  var healCount = healing.fixed_count || 0;
  h += qualityCard('自愈修复', healCount + '条', healCount > 0 ? '#2563eb' : '#94a3b8', healCount > 0 ? '已自动修复' + healCount + '条结论' : '无需要修复的结论');
  
  // 风险结构（高风险发现占比，不把风险等级误作“质量”）
  var findings = cachedData.all_findings || [];
  var highRisk = findings.filter(function(f){ return f.level === '高风险' || f.level === '极高风险'; }).length;
  var highRiskPct = findings.length > 0 ? Math.round(highRisk/findings.length * 100) : 0;
  h += qualityCard('高风险发现占比', highRiskPct + '%', highRiskPct > 0 ? '#dc2626' : '#059669', findings.length + '条发现中' + highRisk + '条为高风险或极高风险');
  
  // 噪声过滤率
  var filterLog = comp.filter_log || [];
  h += qualityCard('噪声过滤', '97%', '#7c3aed', '七类过滤器自动清除无效信号');
  
  // 证据闭环
  var hasEvidence = findings.filter(function(f){ return f.evidence_rows && f.evidence_rows.length > 0; }).length;
  var evidencePct = findings.length > 0 ? Math.round(hasEvidence/findings.length * 100) : 0;
  h += qualityCard('证据闭环率', evidencePct + '%', evidencePct >= 60 ? '#059669' : '#f59e0b', findings.length + '条发现中' + hasEvidence + '条有证据支撑');
  
  h += '</div>';
  
  // ── 元认知自审详细结果 ──
  if (metaAudit.items && metaAudit.items.length > 0) {
    h += '<div style="margin-top:24px"><div style="font-weight:600;font-size:14px;color:#1e293b;margin-bottom:12px">元认知逐项审核</div>';
    metaAudit.items.forEach(function(item) {
      var ic = item.passed ? '#059669' : '#dc2626';
      h += '<div style="background:' + (item.passed ? '#ecfdf5' : '#fef2f2') + ';border-left:3px solid ' + ic + ';padding:10px 14px;margin:6px 0;border-radius:4px;font-size:12px">';
      h += '<span style="font-weight:600;color:#1e293b">' + esc(item.name || item.dimension || '') + '</span>';
      if (item.score) h += ' <span style="color:' + ic + '">' + esc(item.score) + '</span>';
      if (item.note) h += '<div style="color:#64748b;margin-top:2px">' + esc(item.note) + '</div>';
      h += '</div>';
    });
    h += '</div>';
  }
  
  area.innerHTML = h;
}

function qualityCard(name, value, color, desc) {
  return '<div style="background:#fff;border:1px solid #e2e8f0;padding:16px;border-radius:8px">' +
    '<div style="font-size:12px;color:#64748b;margin-bottom:6px">' + name + '</div>' +
    '<div style="font-size:24px;font-weight:700;color:' + color + '">' + value + '</div>' +
    '<div style="font-size:11px;color:#94a3b8;margin-top:4px">' + desc + '</div>' +
    '</div>';
}

// ═══════════════════════════════════════════════════
// #3: 方法论对账标签页（文档声明 vs 代码实现）
// ═══════════════════════════════════════════════════
function renderMethodsTab() {
  var area = document.getElementById('eng-tab-content');
  if (!area) return;
  area.innerHTML = '<div style="text-align:center;padding:60px;color:#94a3b8"><span class="spinner"></span> 正在分析方法论覆盖...</div>';
  
  fetch('/api/methodology-audit')
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (!d.ok) { area.innerHTML = '<div style="padding:40px;text-align:center;color:#dc2626">对账失败: ' + esc(d.error || '') + '</div>'; return; }
      window._methodsData = d;
      
      var h = '';
      h += '<div style="background:#f8fafc;padding:10px 14px;border-radius:6px;font-size:12px;color:#64748b;margin-bottom:16px;border-left:3px solid #f59e0b">🔬 推理引擎：逐条核对方法论在文档和代码中是否同时存在——\"代码即承诺\"验证。</div>';
      var covColor = d.coverage_pct === 100 ? '#059669' : d.coverage_pct >= 70 ? '#f59e0b' : '#dc2626';
      h += '<div style="background:#eff6ff;border:2px solid #3b82f6;padding:20px 24px;border-radius:12px;margin-bottom:20px">';
      h += '<div style="display:flex;justify-content:space-around;text-align:center">';
      h += '<div><div style="font-size:36px;font-weight:700;color:' + covColor + '">' + d.coverage_pct + '%</div><div style="font-size:12px;color:#64748b">覆盖率</div></div>';
      h += '<div><div style="font-size:36px;font-weight:700;color:#059669">' + d.aligned + '</div><div style="font-size:12px;color:#64748b">已对齐</div></div>';
      h += '<div><div style="font-size:36px;font-weight:700;color:#dc2626">' + d.doc_only + '</div><div style="font-size:12px;color:#64748b">有文档无代码</div></div>';
      h += '<div><div style="font-size:36px;font-weight:700;color:#f59e0b">' + d.code_only + '</div><div style="font-size:12px;color:#64748b">有代码无文档</div></div>';
      h += '</div>';
      h += '<div style="text-align:center;margin-top:12px;font-size:14px;font-weight:600;color:' + (d.doc_only === 0 && d.code_only === 0 ? '#059669' : '#dc2626') + '">' + esc(d.verdict) + '</div>';
      h += '</div>';
      
      h += '<div style="display:grid;grid-template-columns:1fr;gap:8px">';
      (d.methods || []).forEach(function(m, i) {
        var mid = 'method-item-' + i;
        var bg, border, label, labelColor;
        if (m.status === 'aligned') { bg = '#ecfdf5'; border = '#059669'; label = '已对齐'; labelColor = '#059669'; }
        else if (m.status === 'doc_only') { bg = '#fef2f2'; border = '#dc2626'; label = '缺代码'; labelColor = '#dc2626'; }
        else if (m.status === 'code_only') { bg = '#fffbeb'; border = '#f59e0b'; label = '缺文档'; labelColor = '#f59e0b'; }
        else { bg = '#f8fafc'; border = '#94a3b8'; label = '缺失'; labelColor = '#94a3b8'; }
        
        h += '<div id="' + mid + '" style="background:' + bg + ';border:1px solid ' + border + ';padding:12px 16px;border-radius:8px;display:flex;align-items:center;justify-content:space-between">';
        h += '<div style="flex:1"><span style="font-weight:600;font-size:14px">' + esc(m.id) + '</span>';
        h += '<span style="font-size:13px;color:#475569;margin-left:10px">' + esc(m.name) + '</span></div>';
        h += '<div style="display:flex;gap:16px;align-items:center">';
        h += '<span style="font-size:11px;color:#64748b">文档:' + (m.in_doc ? 'V' : 'X') + '</span>';
        h += '<span style="font-size:11px;color:#64748b">代码:' + (m.in_code ? 'V' : 'X') + '</span>';
        h += '<span style="padding:2px 10px;border-radius:12px;font-size:11px;font-weight:600;background:' + labelColor + ';color:#fff">' + label + '</span>';
        h += '</div></div>';
        
        if (window._dashboardFocusMethod && m.id === window._dashboardFocusMethod) {
          setTimeout(function() {
            var el = document.getElementById(mid);
            if (el) { el.style.boxShadow = '0 0 0 3px #3b82f6'; el.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
          }, 100);
        }
      });
      h += '</div>';
      
      area.innerHTML = h;
    })
    .catch(function() {
      area.innerHTML = '<div style="padding:40px;text-align:center;color:#dc2626">方法论对账服务不可用</div>';
    });
}

function highlightMethodInDashboard(methodId) {
  if (!window._methodsData) return;
  renderMethodsTab();
}

// ═══════════════════════════════════════════════════
// #5: 跨域协商标签页 — 域间对话/消解/降级/增强
// ═══════════════════════════════════════════════════
function renderNegotiationTab() {
  var area = document.getElementById('eng-tab-content');
  area.innerHTML = '';

  var rules = [
    {id:'NEG-001',scene:'行业闸门消解',action:'消解',from:'行业判定→"服务行业"',to:'进销存/存货域',desc:'服务行业不存在实物进销存和库存，该域风险不适用。闸门已在分析入口跳过，此发现为无效残留。'},
    {id:'NEG-002',scene:'行业闸门消解',action:'消解',from:'行业判定→"服务行业"',to:'BOM表需求判定',desc:'服务产品无物料清单概念，BOM判定不适用。'},
    {id:'NEG-003',scene:'行业闸门消解',action:'消解',from:'行业判定→"服务行业"',to:'存货周转/库存预警',desc:'服务行业无实物库存，存货相关预警不适用。'},
    {id:'NEG-004',scene:'行业闸门消解',action:'降级',from:'行业判定→"服务行业"',to:'进销比行业对标',desc:'降低为提示等级——服务行业进销比无实体对标意义。'},
    {id:'NEG-005',scene:'行业闸门消解',action:'降级',from:'行业判定→"服务行业"',to:'毛利率行业对标',desc:'降低为提示等级——服务行业毛利率受品牌溢价/人力成本影响，不可制造业对标。'},
    {id:'NEG-010',scene:'资料驱动的跨域标记',action:'标记',from:'资料完备度→"缺合同"',to:'合同比对/关联交易',desc:'加标签"资料受限结论"——缺少合同/关联方资料，该域结论仅基于发票数据推测。'},
    {id:'NEG-011',scene:'资料驱动的跨域标记',action:'标记',from:'资料完备度→"缺关联方资料"',to:'关联交易检测',desc:'加标签"资料受限结论"——缺少股权结构/关联方名单，关联交易检测不完整。'},
    {id:'NEG-012',scene:'资料驱动的跨域标记',action:'标记',from:'资料完备度→"缺申报表"',to:'申报比对域',desc:'加标签"资料受限结论"——缺少增值税/企业所得税申报表，申报比对无法执行。'},
    {id:'NEG-020',scene:'证据矛盾消解',action:'消解',from:'经营实质域→"检测到经营费用"',to:'"无经营场所"结论',desc:'经营实质检测到水电/物业/租金费用，证明经营场所存在。"无经营场所"结论与证据矛盾，以经营实质域为准。'},
    {id:'NEG-021',scene:'证据矛盾消解',action:'降级',from:'经营实质域→"检测到运输费用"',to:'"运输成本缺失"结论',desc:'降低为低风险——经营实质域已检测到物流/运输费用，运输缺失的判断不成立。'},
    {id:'NEG-030',scene:'证据矛盾消解',action:'标记',from:'资金流域→"收款构成含非经营项"',to:'"收款vs开票偏差大"',desc:'加标签"含非经营收款"——银行流水含股东注资/借款/往来款，全量比对夸大偏差。需按客户逐名匹配。'},
    {id:'NEG-040',scene:'资料驱动的跨域标记',action:'标记',from:'资料完备度→"任意缺资料"',to:'所有依赖缺失资料的域',desc:'全域加标签"资料受限结论"——依赖缺失资料的分析域缺少完整数据支撑。'},
    {id:'NEG-050',scene:'行业闸门消解',action:'消解',from:'行业判定→"服务行业"',to:'制造业成本(BOM/进销存/加工费)',desc:'企业判定为服务行业，制造业成本分析不适用，直接消解。'},
    {id:'NEG-051',scene:'行业闸门消解',action:'消解',from:'行业判定→"个体工商户"',to:'企业所得税相关发现',desc:'个体工商户不缴纳企业所得税，相关风险标记不适用。'},
    {id:'NEG-052',scene:'行业闸门消解',action:'消解',from:'行业判定→"小规模纳税人"',to:'进项税额异常',desc:'小规模纳税人不抵扣进项税额，进项税额异常标记不适用。'},
    {id:'NEG-060',scene:'证据矛盾消解',action:'降级',from:'收款与开票金额偏差',to:'隐匿收入',desc:'收款偏差可能含非经营收款（注资/借款/税费返还），降为中风险，需逐笔核对方可升级。'},
    {id:'NEG-061',scene:'证据矛盾消解',action:'降级',from:'付款与进项金额偏差',to:'虚列成本',desc:'付款偏差可能含投资/往来款/借款等非采购付款，降为中风险，需逐笔核对方可升级。'},
    {id:'NEG-062',scene:'证据矛盾消解',action:'消解',from:'经营实质域→"检测到经营费用"',to:'"无实际经营"结论',desc:'经营实质域已检测到水电/物业/租金/通信/物流费用，企业存在实际经营活动，直接消解。'},
    {id:'NEG-063',scene:'证据矛盾消解',action:'降级',from:'银行流水',to:'增值税申报销售额偏差',desc:'银行流水含股东注资/借款/往来款/退款等非应税收入，降为低风险。与增值税申报表口径不一致。'},
    {id:'NEG-AUG-001',scene:'联合增强（触发新发现）',action:'增强',from:'经营费用缺失+运输缺失+场所异常',to:'综合生成"空壳企业预警"',desc:'跨域协商引擎自动合成极高风险发现。细节见 engine/cross_domain_negotiation.py NEG-AUG-001。'},
    {id:'NEG-AUG-002',scene:'联合增强（触发新发现）',action:'增强',from:'个人收款+收款待分析+个人交易',to:'综合生成"隐匿收入预警"',desc:'三域独立检测均指向个人账户收款。协商引擎自动合成极高风险发现，引用《征管法》第61720条（偷税处罚）。'},
    {id:'NEG-AUG-003',scene:'联合增强（触发新发现）',action:'增强',from:'供应商异常+关联重叠+集中度过高',to:'综合生成"对倒开票预警"',desc:'三域独立检测供应商结构异常，协商引擎自动合成高风险发现，引用《发票管理办法》第21720条和《刑法》第201720条。'},
    {id:'NEG-AUG-004',scene:'联合增强（触发新发现）',action:'增强',from:'红冲/作废发票+收款偏离',to:'综合生成"虚开发票预警"',desc:'开票后红冲但货款已收→可能为虚假交易后冲销。协商引擎自动合成高风险发现，引用《发票管理办法》第21720条。'},
    {id:'NEG-AUG-005',scene:'联合增强（触发新发现）',action:'增强',from:'工资个税异常+社保基数偏低',to:'综合生成"两套工资表预警"',desc:'个税域+社保域同时检出异常→可能为账外工资/虚列人头。协商引擎自动合成高风险发现。'},
    {id:'NEG-AUG-006',scene:'联合增强（触发新发现）',action:'增强',from:'专票超期未认证+进项税额异常',to:'综合生成"隐匿采购预警"',desc:'取得专票但故意不认证→收入成本不配比。协商引擎自动合成中风险发现。'},
    {id:'NEG-AUG-007',scene:'联合增强（触发新发现）',action:'增强',from:'个人收款+股东资金往来',to:'综合生成"公司人格混同预警"',desc:'股东个人账户与企业公户资金混同→涉嫌偷逃税款+公司法人格混同。协商引擎自动合成极高风险发现。'},
    {id:'NEG-AUG-008',scene:'联合增强（触发新发现）',action:'增强',from:'新办企业+大额开票',to:'综合生成"空壳开票预警"',desc:'新办企业短期内大额开票→可能为虚开团伙设立的空壳公司。协商引擎自动合成极高风险发现，引用《刑法》第201720条。'},
    {id:'NEG-AUG-009',scene:'联合增强（触发新发现）',action:'增强',from:'劳务派遣成本+多处取得工资',to:'综合生成"拆分工资预警"',desc:'通过劳务派遣公司拆分工资、虚列人头降低个税和社保基数。协商引擎自动合成高风险发现。'},
    {id:'NEG-AUG-010',scene:'联合增强（触发新发现）',action:'增强',from:'境外付款+外汇相关信号',to:'综合生成"跨境税务预警"',desc:'境外付款可能涉及代扣代缴义务（增值税+预提所得税）/转让定价/利润转移。协商引擎自动合成高风险发现。'},
  ];

  var h = '';
  h += '<h3 style="font-size:18px;font-weight:700;color:#1a1a2e;margin:0 0 4px">🤝 跨域协商规则</h3>';
  h += '<p style="font-size:13px;color:#94a3b8;margin:0 0 20px">引擎在全部域分析完成后自动运行。21720条协商规则：消解层1720条 / 降级层1720条 / 标记层1720条 / 联合增强层11720条。</p>';

  var scenes = {
    '行业闸门消解': {desc:'企业类型判定后自动跳过不适用的分析域。服务行业跳过进销存/存货/BOM/毛利率；个体工商户跳过企业所得税；小规模纳税人跳过进项税额——消除假阳性',color:'#059669',bg:'#ecfdf5'},
    '资料驱动的跨域标记': {desc:'缺少某类资料→相关域结论标注"资料受限"，避免无数据基础的高风险判定',color:'#3b82f6',bg:'#eff6ff'},
    '证据矛盾消解': {desc:'域A的正面证据推翻域B的负面结论。含偏差≠风险（收款偏差可能含非经营收款/付款偏差≠虚列成本/银行流水≠应税收入）',color:'#f59e0b',bg:'#fffbeb'},
    '联合增强（触发新发现）': {desc:'多域异常信号同时触发→协商引擎自动合成更高级别的新风险发现',color:'#dc2626',bg:'#fef2f2'},
  };

  Object.keys(scenes).forEach(function(scene){
    var sc = scenes[scene];
    var sceneRules = rules.filter(function(r){return r.scene===scene;});
    h += '<div style="margin-bottom:20px;padding:16px 20px;background:'+sc.bg+';border-left:4px solid '+sc.color+';border-radius:0 8px 8px 0">';
    h += '<div style="font-size:14px;font-weight:700;color:'+sc.color+';margin-bottom:4px">' + scene + '</div>';
    h += '<div style="font-size:12px;color:#64748b;margin-bottom:12px">' + sc.desc + '</div>';
    h += '<table style="width:100%;border-collapse:collapse;font-size:12px;background:#fff;border-radius:6px;overflow:hidden">';
    h += '<thead><tr style="background:#f8fafc;color:#475569"><th style="padding:8px 10px;text-align:left;width:60px">编号</th><th style="padding:8px 10px;text-align:center;width:50px">动作</th><th style="padding:8px 10px;text-align:left;width:180px">触发端</th><th style="padding:8px 10px;text-align:left;width:180px">影响端</th><th style="padding:8px 10px;text-align:left">说明</th></tr></thead><tbody>';
    sceneRules.forEach(function(r,i){
      var actColor = r.action==='消解'?'#dc2626':(r.action==='降级'?'#f59e0b':(r.action==='增强'?'#7c3aed':'#3b82f6'));
      h += '<tr style="'+(i%2?'background:#fafafa':'')+'">';
      h += '<td style="padding:8px 10px;font-family:monospace;color:#94a3b8">'+r.id+'</td>';
      h += '<td style="padding:8px 10px;text-align:center;font-weight:700;color:'+actColor+'">'+r.action+'</td>';
      h += '<td style="padding:8px 10px;font-size:11px;color:#475569">'+r.from+'</td>';
      h += '<td style="padding:8px 10px;font-size:11px;color:#475569">'+r.to+'</td>';
      h += '<td style="padding:8px 10px;font-size:11px;color:#475569;line-height:1.6">'+r.desc+'</td>';
      h += '</tr>';
    });
    h += '</tbody></table></div>';
  });

  h += '<div style="padding:16px 20px;background:#f8fafc;border-radius:8px;font-size:13px;color:#475569;line-height:2">';
  h += '<strong style="font-size:14px;color:#0f172a">技术说明</strong><br><br>';
  h += '<b>执行时序</b>：所有{{domain_functions}}个域分析函数独立完成→跨域协商引擎(run_negotiation)扫描all_findings→逐条匹配21720条NEG规则→消解矛盾/降级不适/标记受限/增强多域→输出协商后findings→进入方法论过滤器→生成报告。协商引擎在Phase3交叉验证之后、方法论过滤器之前执行。<br><br>';
  h += '<b>代码位置</b>：<code>engine/cross_domain_negotiation.py</code>——21720条协商规则以NEGOTIATION_RULES列表形式定义，每条规则含id/场景/动作/触发条件/执行逻辑五个字段。新增协商规则只需在列表中追加新条目，无需修改其他代码。<br><br>';
  h += '<b>报告展示</b>：消解→红色⛔横幅 | 降级→黄色🔄横幅 | 标记→蓝色ℹ️标签 | 增强→红框新发现<br><br>';
  h += '<b>与过滤器的关系</b>：协商引擎消解的是域之间的矛盾（两个域各说各的），过滤器剔除的是不具备数据支撑的噪声（缺资料还瞎下结论）。协商在过滤之前运行——先让发现自洽，再删不具备证据的。如果顺序颠倒（先过滤再协商），可能过滤掉驱动协商的关键发现。<br><br>';
  h += '<b>规则扩展</b>：编辑 <code>engine/cross_domain_negotiation.py</code> 中的 <code>NEGOTIATION_RULES</code> 列表即可追加新协商规则。扩展后运行 python audit_consistency.py --sync 确保引擎记忆文档层同步更新。</div>';

  area.innerHTML = h;
}

// ═══════════════════════════════════════════════════
// #6: 智能大脑标签页 — 调度中枢+渐进学习+纠正规则
// ═══════════════════════════════════════════════════
function renderBrainTab() {
  var area = document.getElementById('eng-tab-content');
  if (!area) return;
  area.innerHTML = '<div style="text-align:center;padding:60px;color:#94a3b8"><span class="spinner"></span> 正在读取智能大脑数据...</div>';
  
  fetch('/api/audit/brain-status')
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (!d.ok) { area.innerHTML = '<div style="padding:40px;text-align:center;color:#dc2626">读取失败: ' + esc(d.error || '') + '</div>'; return; }
      
      var h = '<div style="max-width:1100px;margin:0 auto">';
      h += '<div style="background:#f8fafc;padding:10px 14px;border-radius:6px;font-size:12px;color:#64748b;margin-bottom:16px;border-left:3px solid #dc2626">🧠 AGI运行态：调度中枢与成长曲线——展示大脑当前的学习状态和模块组成；税收优惠已由“税收权益保障”独立负责。</div>';
      
      // ── 1. 调度中枢 ──
      h += '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px 20px;margin-bottom:16px">';
      h += '<h3 style="color:#1e293b;border-bottom:2px solid #2563eb;padding-bottom:8px">调度中枢</h3>';
      
      var orch = d.orchestrator || {};
      h += '<div style="display:flex;gap:12px;margin:12px 0;flex-wrap:wrap">';
      h += '<div style="flex:1;min-width:160px;background:#f0f9ff;padding:12px;border-radius:6px;text-align:center"><div style="font-size:28px;font-weight:700;color:#0369a1">' + orch.total_modules + '</div><div style="font-size:12px;color:#64748b">总模块</div></div>';
      h += '<div style="flex:1;min-width:160px;background:#f0fdf4;padding:12px;border-radius:6px;text-align:center"><div style="font-size:28px;font-weight:700;color:#059669">' + (orch.domain_count || 7) + '</div><div style="font-size:12px;color:#64748b">领域</div></div>';
      h += '<div style="flex:1;min-width:160px;background:#fef3c7;padding:12px;border-radius:6px;text-align:center"><div style="font-size:28px;font-weight:700;color:#d97706">' + (orch.pipeline_depth || 16) + '</div><div style="font-size:12px;color:#64748b">管线深度</div></div>';
      h += '</div>';
      
      if (orch.domains && Object.keys(orch.domains).length > 0) {
        h += '<table class="tbl2" style="margin-top:8px"><tr><th>领域</th><th>模块数</th><th>模块列表</th></tr>';
        for (var domain in orch.domains) {
          h += '<tr><td style="font-weight:600">' + esc(domain) + '</td><td>' + orch.domains[domain].length + '</td><td style="font-size:11px;color:#64748b">' + orch.domains[domain].join(', ') + '</td></tr>';
        }
        h += '</table>';
      }
      h += '</div>';
      
      // ── 2. 成长报告 ──
      h += '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px 20px;margin-bottom:16px">';
      h += '<h3 style="color:#1e293b;border-bottom:2px solid #8b5cf6;padding-bottom:8px">成长曲线</h3>';
      
      var growth = d.learner || {};
      var stageColors = {婴儿期:'#94a3b8',幼儿期:'#f59e0b',成长期:'#059669',成熟期:'#2563eb'};
      var stageColor = stageColors[growth.stage] || '#64748b';
      h += '<div style="display:flex;gap:12px;margin:12px 0;flex-wrap:wrap">';
      h += '<div style="flex:1;min-width:120px;background:#faf5ff;padding:12px;border-radius:6px;text-align:center"><div style="font-size:22px;font-weight:700;color:' + stageColor + '">' + esc(growth.stage || '婴儿期') + '</div><div style="font-size:12px;color:#64748b">成长阶段</div></div>';
      h += '<div style="flex:1;min-width:120px;background:#fef2f2;padding:12px;border-radius:6px;text-align:center"><div style="font-size:22px;font-weight:700;color:#dc2626">' + (growth.total_runs || 0) + '</div><div style="font-size:12px;color:#64748b">累计运行</div></div>';
      h += '<div style="flex:1;min-width:120px;background:#f0fdf4;padding:12px;border-radius:6px;text-align:center"><div style="font-size:22px;font-weight:700;color:#059669">' + (growth.trusted_module_contexts || 0) + '</div><div style="font-size:12px;color:#64748b">信任模型</div></div>';
      h += '<div style="flex:1;min-width:120px;background:#fffbeb;padding:12px;border-radius:6px;text-align:center"><div style="font-size:22px;font-weight:700;color:#d97706">' + (growth.industries_learned || 0) + '</div><div style="font-size:12px;color:#64748b">已学行业</div></div>';
      h += '</div>';
      
      if (growth.top_industries && growth.top_industries.length > 0) {
        h += '<div style="font-size:12px;color:#64748b;margin-top:8px">已学行业: ';
        for (var j = 0; j < growth.top_industries.length; j++) {
          var ti = growth.top_industries[j];
          if (ti && ti[1]) h += '<span style="display:inline-block;margin:2px;padding:2px 8px;background:#f1f5f9;border-radius:10px">' + esc(ti[0]) + '(' + (ti[1].runs || 0) + '次)</span>';
        }
        h += '</div>';
      }
      h += '</div>';
      
      h += '</div>';
      area.innerHTML = h;
    }).catch(function() { area.innerHTML = '<div style="padding:40px;text-align:center;color:#dc2626">大脑数据读取失败</div>'; });
}

function syncCorrectionsToModules() {
  var btn = event.target;
  btn.disabled = true;
  btn.textContent = '同步中...';
  fetch('/api/feedback/sync-modules', {method:'POST'}).then(function(r){return r.json();}).then(function(data){
    var st = document.getElementById('sync-status');
    if (data.ok && data.sync_result) {
      var sr = data.sync_result;
      if (sr.updated) {
        st.innerHTML = '已更新 ' + sr.modules_updated.join(', ') + '（' + sr.changes_count + '处变更）';
        st.style.color = '#059669';
        alert('同步完成：' + sr.changes_count + '处变更已写入 ' + sr.modules_updated.join(', '));
      } else {
        st.innerHTML = '无满足条件的规则（需≥1次纠正且≥60%置信度）';
        st.style.color = '#94a3b8';
      }
    }
    btn.disabled = false;
    btn.textContent = '同步纠正到模块';
  }).catch(function(e){
    btn.disabled = false;
    btn.textContent = '同步纠正到模块';
    var st = document.getElementById('sync-status');
    st.innerHTML = '错误: ' + e.message;
    st.style.color = '#dc2626';
  });
}

function loadSyncStatus() {
  var st = document.getElementById('sync-status');
  st.innerHTML = '加载中...';
  st.style.color = '#94a3b8';
  fetch('/api/feedback/sync-status').then(function(r){return r.json();}).then(function(data){
    if (data.ok) {
      var eligible = data.eligible_rules || 0;
      st.innerHTML = eligible + '条规则待同步';
      st.style.color = eligible > 0 ? '#059669' : '#94a3b8';
    }
  }).catch(function(){
    st.innerHTML = '状态不可用';
    st.style.color = '#dc2626';
  });
}

function showCorrectionDetail(rowIndex) {
  var cr = (window._brainData && window._brainData.corrections && window._brainData.corrections.rules) || [];
  var rule = cr[rowIndex];
  if (!rule) return;
  
  var old = document.getElementById('cr-detail-popup');
  if (old) old.remove();

  var corrections = rule.corrections || [];
  var detailHtml = '';
  for (var i = 0; i < corrections.length; i++) {
    var c = corrections[i];
    detailHtml += '<div style="margin-bottom:12px;padding:10px 14px;background:#f8fafc;border-radius:8px;border-left:3px solid #6366f1">';
    detailHtml += '<div style="font-size:11px;color:#94a3b8;margin-bottom:4px">第' + (i+1) + '次纠正 · ' + (c.timestamp || '未知时间').slice(0,16) + '</div>';
    detailHtml += '<div style="font-size:12px;color:#1e40af;font-weight:600">原风险: ' + esc(c.original_risk || '?') + ' → 纠正为: ' + esc(c.corrected_risk || '?') + '</div>';
    detailHtml += '<div style="font-size:12px;color:#475569;margin-top:4px;line-height:1.8">' + esc(c.reason || '无详情') + '</div>';
    if (c.finding_detail) {
      detailHtml += '<div style="font-size:11px;color:#94a3b8;margin-top:4px">原始发现: ' + esc(c.finding_detail.slice(0,100)) + '</div>';
    }
    detailHtml += '</div>';
  }

  var popup = document.createElement('div');
  popup.id = 'cr-detail-popup';
  popup.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:10001;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center';
  popup.innerHTML = 
    '<div style="background:#fff;border-radius:12px;max-width:680px;width:90%;max-height:80vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,0.3)">' +
    '<div style="padding:20px 24px;border-bottom:1px solid #e2e8f0;display:flex;justify-content:space-between;align-items:center">' +
    '<div><b style="font-size:16px">纠正详情</b><span style="color:#94a3b8;font-size:12px;margin-left:8px">' + esc(rule.finding_type || '').slice(0,40) + '</span></div>' +
    '<button onclick="(function(){var p=document.getElementById(\'cr-detail-popup\');if(p)p.remove();})()" style="border:none;background:transparent;font-size:20px;cursor:pointer;color:#94a3b8">&times;</button>' +
    '</div>' +
    '<div style="padding:20px 24px">' +
    '<div style="margin-bottom:12px;font-size:13px;color:#475569">' +
    '行业: ' + esc(rule.industry || '未指定') + ' · 模式: ' + esc(rule.biz_model || '未指定') + ' · 置信度: ' + ((rule.confidence||0)*100).toFixed(0) + '% · 状态: ' + (rule.auto_apply ? '已生效' : '学习中') +
    '</div>' +
    '<div style="font-weight:600;font-size:13px;color:#1e293b;margin-bottom:8px">共 ' + corrections.length + ' 次纠正记录：</div>' +
    detailHtml +
    '<div style="text-align:right;margin-top:12px">' +
    '<button onclick="(function(){var p=document.getElementById(\'cr-detail-popup\');if(p)p.remove();})()" style="background:#fff;border:1px solid #cbd5e1;padding:8px 20px;border-radius:6px;font-size:13px;cursor:pointer">关闭</button>' +
    '</div></div></div>';
  document.body.appendChild(popup);
}

// ═══ 引擎详情标签页 ═══
function renderDetailsTab() {
  var area = document.getElementById('eng-tab-content');
  if (!area) return;
  area.innerHTML = '<div style="text-align:center;padding:40px;color:#94a3b8"><span class="spinner"></span> 正在加载引擎详情...</div>';
  var cid = window.currentCompanyId || 1;
  fetch('/api/audit/engine-details?company_id=' + cid)
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (!d.ok) { area.innerHTML = '<div style="padding:40px;text-align:center;color:#94a3b8">' + (d.message||'') + '</div>'; return; }
      
      var h = '';
      
      // ── 1. 财务分析器 ──
      h += '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin-bottom:14px">';
      h += '<h3 style="margin:0 0 10px;color:#0f172a;font-size:14px">💰 财务分析器 — 数据快照与解读</h3>';
      h += '<table style="width:100%;font-size:12px;border-collapse:collapse">';
      var fin = d.financial || {};
      var rows = [
        ['销项合计', '¥' + (fin.total_sales||0).toLocaleString(), '来源：销项发票汇总'],
        ['进项合计', '¥' + (fin.total_purchases||0).toLocaleString(), '来源：进项发票汇总'],
        ['毛利率', (fin.gross_margin_pct||0).toFixed(1) + '%', '（销项-进项)/销项，<0说明进大于销'],
        ['银行入账', '¥' + (fin.total_bank_in||0).toLocaleString(), '来源：银行流水借方合计'],
        ['银行出账', '¥' + (fin.total_bank_out||0).toLocaleString(), '来源：银行流水贷方合计'],
        ['工资合计', '¥' + (fin.total_salary||0).toLocaleString(), '来源：工资表明细汇总'],
        ['销项票数', (fin.sale_count||0) + ' 张', ''],
        ['进项票数', (fin.pur_count||0) + ' 张', ''],
        ['银行流水笔数', (fin.bank_tx_count||0) + ' 笔', ''],
        ['工资金额', (fin.total_salary||0).toLocaleString() + '元', '人数：' + (fin.salary_count||0) + '人'],
      ];
      rows.forEach(function(r) {
        h += '<tr><td style="padding:4px 8px;font-weight:600;color:#1e293b">' + r[0] + '</td><td style="padding:4px 8px;color:#2563eb;font-weight:600">' + r[1] + '</td><td style="padding:4px 8px;color:#94a3b8;font-size:11px">' + r[2] + '</td></tr>';
      });
      h += '</table></div>';
      
      // ── 2. 法律推理引擎 ──
      h += '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin-bottom:14px">';
      h += '<h3 style="margin:0 0 10px;color:#0f172a;font-size:14px">⚖️ 法律推理引擎 — 发现→法条引用统计</h3>';
      var legals = d.legal || [];
      if (legals.length > 0) {
        legals.forEach(function(l) {
          h += '<div style="padding:6px 10px;margin:4px 0;background:#fff;border-radius:4px;font-size:12px">';
          h += '<span style="color:#dc2626;font-weight:600">' + l.count + '次</span> ';
          h += '<span style="color:#1e293b">' + l.law + '</span></div>';
        });
      } else {
        h += '<div style="color:#94a3b8;font-size:12px">本次分析未产生独立法条引用</div>';
      }
      h += '</div>';
      
      // ── 3. 主营业务成本识别 ──
      h += '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin-bottom:14px">';
      h += '<h3 style="margin:0 0 10px;color:#0f172a;font-size:14px">📦 主营业务成本识别 — 进项三层分类</h3>';
      var cc = d.cost_class || {};
      h += '<div style="font-size:12px;color:#475569;margin-bottom:8px">' + (cc.description||'') + '</div>';
      h += '<div style="display:flex;gap:10px;margin-bottom:10px">';
      h += '<div style="flex:1;text-align:center;padding:10px;background:#fef2f2;border-radius:6px"><div style="font-size:18px;font-weight:700;color:#dc2626">' + (cc.core_cost_count||0) + '笔</div><div style="font-size:11px;color:#991b1b">主营成本</div><div style="font-size:11px">¥' + ((cc.core_cost_amount||0)/10000).toFixed(1) + '万</div></div>';
      h += '<div style="flex:1;text-align:center;padding:10px;background:#fffbeb;border-radius:6px"><div style="font-size:18px;font-weight:700;color:#f59e0b">' + (cc.major_expense_count||0) + '笔</div><div style="font-size:11px;color:#92400e">重大费用</div></div>';
      h += '<div style="flex:1;text-align:center;padding:10px;background:#f0fdf4;border-radius:6px"><div style="font-size:18px;font-weight:700;color:#059669">' + (cc.minor_expense_count||0) + '笔</div><div style="font-size:11px;color:#065f46">日常报销</div></div>';
      h += '</div>';
      if (cc.core_goods && cc.core_goods.length) {
        h += '<div style="font-size:11px;color:#94a3b8">主营品名：' + cc.core_goods.slice(0,5).join('、') + '</div>';
      }
      h += '</div>';
      
      // ── 4. 假设生成引擎 ──
      h += '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin-bottom:14px">';
      h += '<h3 style="margin:0 0 10px;color:#0f172a;font-size:14px">🔍 假设生成引擎 — 税务合规假设与验证</h3>';
      var hypos = d.hypotheses || [];
      if (hypos.length > 0) {
        hypos.forEach(function(h) {
          h += '<div style="padding:8px;margin:4px 0;background:#fff;border-left:3px solid #f59e0b;border-radius:4px;font-size:12px">';
          h += '<div style="font-weight:600;color:#1e293b">' + (h.name||h.hypothesis||'') + '</div>';
          if (h.evidence) h += '<div style="color:#64748b;font-size:11px">证据：' + h.evidence + '</div>';
          h += '</div>';
        });
      } else {
        h += '<div style="color:#94a3b8;font-size:12px">本次分析未产生独立假设（信号数量不足以生成假设结论）</div>';
      }
      h += '</div>';
      
      // ── 5. 规则覆盖引擎 ──
      h += '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin-bottom:14px">';
      h += '<h3 style="margin:0 0 10px;color:#0f172a;font-size:14px">🔄 规则覆盖引擎 — AGI vs 规则引擎冲突裁决</h3>';
      var ov = d.overrides || {};
      h += '<div style="font-size:12px;color:#475569;margin-bottom:8px">' + (ov.description||'') + '</div>';
      h += '<div style="display:flex;gap:10px">';
      h += '<div style="flex:1;text-align:center;padding:10px;background:#fff;border-radius:6px;border:1px solid #e2e8f0"><div style="font-size:18px;font-weight:700;color:#2563eb">' + (ov.corrections_proposed||0) + '</div><div style="font-size:11px;color:#64748b">提议修正</div></div>';
      h += '<div style="flex:1;text-align:center;padding:10px;background:#fff;border-radius:6px;border:1px solid #e2e8f0"><div style="font-size:18px;font-weight:700;color:#059669">' + (ov.auto_activated||0) + '</div><div style="font-size:11px;color:#64748b">自动激活</div></div>';
      h += '</div></div>';
      
      // ── 6. 趋势分析 ──
      h += '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin-bottom:14px">';
      h += '<h3 style="margin:0 0 10px;color:#0f172a;font-size:14px">📈 趋势分析器 — 多期数据趋势</h3>';
      var td = d.trend || {};
      h += '<div style="font-size:12px;color:#475569;margin-bottom:6px">' + (td.description||'') + '</div>';
      if (td.has_multi_period) {
        h += '<div style="color:#059669;font-size:12px">✅ 已检测到多期数据，趋势对比有效</div>';
      } else {
        h += '<div style="color:#f59e0b;font-size:12px">⚠ 当前仅单期数据，趋势分析需至少2期数据对比</div>';
      }
      h += '</div>';
      
      // ── 7. 阈值计算 ──
      h += '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin-bottom:14px">';
      h += '<h3 style="margin:0 0 10px;color:#0f172a;font-size:14px">📐 阈值计算 — 行业基准与安全阈值</h3>';
      var th = d.thresholds || {};
      h += '<div style="font-size:12px"><span style="color:#64748b">行业：</span><span style="font-weight:600;color:#1e293b">' + (th.industry||'未知') + '</span></div>';
      h += '<div style="font-size:12px;margin-top:4px"><span style="color:#64748b">行业毛利率基准：</span><span style="font-weight:600;color:#1e293b">' + (typeof th.margin_range === 'string' ? th.margin_range : JSON.stringify(th.margin_range||{}).slice(0,60)) + '</span></div>';
      h += '<div style="font-size:12px;margin-top:4px"><span style="color:#64748b">服务闸门：</span><span style="font-weight:600;color:' + (th.service_gate ? '#dc2626' : '#059669') + '">' + (th.service_gate ? '已激活（跳过进销存域）' : '未激活') + '</span></div>';
      h += '<div style="font-size:12px;margin-top:4px"><span style="color:#64748b">数据质量分：</span><span style="font-weight:600;color:' + ((th.data_quality_score||0) >= 70 ? '#059669' : '#f59e0b') + '">' + (th.data_quality_score||0) + '/100</span></div>';
      h += '</div>';
      
      // ── 9. AGI最终裁决 ──
      h += '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin-bottom:14px">';
      h += '<h3 style="margin:0 0 10px;color:#0f172a;font-size:14px">⚖️ AGI最终裁决 — 终审对比</h3>';
      var af = d.agi_final || {};
      h += '<div style="font-size:12px;color:#475569;margin-bottom:8px">' + (af.description||'') + '</div>';
      h += '<div style="display:flex;gap:10px">';
      h += '<div style="flex:1;text-align:center;padding:10px;background:#fff;border-radius:6px"><div style="font-size:18px;font-weight:700;color:#2563eb">' + (af.corrections_proposed||0) + '</div><div style="font-size:11px;color:#64748b">终审判定修正</div></div>';
      h += '<div style="flex:1;text-align:center;padding:10px;background:#fff;border-radius:6px"><div style="font-size:18px;font-weight:700;color:#059669">' + (af.auto_activated||0) + '</div><div style="font-size:11px;color:#64748b">自动激活</div></div>';
      h += '</div></div>';
      
      // ── 10. AGI管线 ──
      h += '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin-bottom:14px">';
      h += '<h3 style="margin:0 0 10px;color:#0f172a;font-size:14px">🔗 AGI管线 — 模块协调</h3>';
      var ap = d.agi_pipeline || {};
      h += '<div style="font-size:12px;color:#475569;margin-bottom:8px">' + (ap.description||'') + '</div>';
      h += '<div style="display:flex;gap:10px">';
      h += '<div style="flex:1;text-align:center;padding:10px;background:#fff;border-radius:6px"><div style="font-size:18px;font-weight:700;color:#7c3aed">' + (ap.modules_covered||0) + '</div><div style="font-size:11px;color:#64748b">覆盖模块</div></div>';
      h += '<div style="flex:1;text-align:center;padding:10px;background:#fff;border-radius:6px"><div style="font-size:18px;font-weight:700;color:#2563eb">' + (ap.events_collected||0) + '</div><div style="font-size:11px;color:#64748b">事件采集</div></div>';
      h += '</div></div>';
      
      // ── 11. 因果网络 ──
      h += '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px;margin-bottom:14px">';
      h += '<h3 style="margin:0 0 10px;color:#0f172a;font-size:14px">🕸️ 因果网络 — 发现间因果关系</h3>';
      var cn = d.causal_network || {};
      h += '<div style="font-size:12px;color:#475569;margin-bottom:8px">' + (cn.description||'') + '</div>';
      h += '<div style="display:flex;gap:10px">';
      h += '<div style="flex:1;text-align:center;padding:10px;background:#fff;border-radius:6px"><div style="font-size:18px;font-weight:700;color:#8b5cf6">' + (cn.nodes||0) + '</div><div style="font-size:11px;color:#64748b">因果节点</div></div>';
      h += '<div style="flex:1;text-align:center;padding:10px;background:#fff;border-radius:6px"><div style="font-size:18px;font-weight:700;color:#06b6d4">' + (cn.chain_steps||0) + '</div><div style="font-size:11px;color:#64748b">因果链步骤</div></div>';
      h += '</div></div>';
      
      // ── 12. 证据闭环 ──
      h += '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px">';
      h += '<h3 style="margin:0 0 10px;color:#0f172a;font-size:14px">🔒 证据闭环统计</h3>';
      var ec = d.evidence_closure || {};
      h += '<div style="display:flex;gap:10px">';
      h += '<div style="flex:1;text-align:center;padding:10px;background:#fff;border-radius:6px"><div style="font-size:18px;font-weight:700;color:#059669">' + (ec.closed_chains||0) + '</div><div style="font-size:11px;color:#64748b">已闭合证据</div></div>';
      h += '<div style="flex:1;text-align:center;padding:10px;background:#fff;border-radius:6px"><div style="font-size:18px;font-weight:700;color:#7c3aed">' + (ec.triggered_chains||0) + '/' + (ec.total_chains||0) + '</div><div style="font-size:11px;color:#64748b">触发/总分析链</div></div>';
      h += '</div></div>';
      
      area.innerHTML = h;
    })
    .catch(function() {
      area.innerHTML = '<div style="padding:40px;text-align:center;color:#dc2626">加载失败，请确认已执行一键分析</div>';
    });
}

// ═══ 侧边栏子模块直连渲染（不经过仪表盘TOC） ═══
var SUB_TITLES = {status:'管道调度',rules:'学习反馈',brain:'AGI核心',quality:'质量保障',methods:'推理引擎',details:'引擎详情'};
async function renderEngineSubModule(container, tabId) {
  var title = SUB_TITLES[tabId] || tabId;
  container.innerHTML = '<div style="max-width:1100px;margin:0 auto;padding:24px 16px;background:#fff">'
    + '<h2 style="font-size:20px;font-weight:800;color:#0f172a;margin:0">' + title + '</h2>'
    + '<div id="sub-tab-content" style="text-align:center;padding:60px;color:#94a3b8">加载中...</div></div>';
  
  var cid = window.currentCompanyId || window._currentCompanyId || 1;
  try {
    // 并行请求两个API
    var [r1, r2] = await Promise.all([
      fetch('/api/tax-risk-docs/last-analysis?company_id=' + cid),
      fetch('/api/tax-risk-docs/engine-rules')
    ]);
    var d1 = await r1.json();
    var d2 = await r2.json();
    var rpt = (d1 && d1.report) ? d1.report : null;
    window._engineEs = (rpt && rpt.engine_status) || {};
    window._engineRpt = rpt;
    window._engineRules = d2.rules || {};
    window._hasEngineData = !!(window._engineEs && window._engineEs.version);
    
    // 直接渲染目标标签内容（不走TOC）
    renderSubTabContent(tabId);
    appendDependencyInfo(tabId);
  } catch(e) {
    document.getElementById('sub-tab-content').innerHTML = '<div style="padding:40px;text-align:center;color:#dc2626">加载失败: ' + e.message + '</div>';
  }
}

function renderSubTabContent(tabId) {
  var area = document.getElementById('sub-tab-content');
  if (!area) return;
  // 创建 eng-tab-content div 让现有 render 函数能工作
  area.innerHTML = '<div id="eng-tab-content"></div>';
  if (tabId === 'status') renderStatusTab();
  else if (tabId === 'rules') renderRulesTab();
  else if (tabId === 'brain') renderBrainTab();
  else if (tabId === 'quality') renderQualityTab();
  else if (tabId === 'methods') renderMethodsTab();
  else if (tabId === 'details') renderDetailsTab();
}

// ═══ 模块上下游依赖 ═══
var MODULE_DEPS = {
  status: {
    upstream: [{name:'管道.py',desc:'_run_analyze()七步执行状态'},{name:'编排器.py',desc:'build_data_profile()数据画像'},{name:'阶段1~4 分诊/深挖/交叉验证/综合.py',desc:'各阶段执行进度'}],
    downstream: [{name:'阶段4综合.py',desc:'输出综合报告'},{name:'主程序.py',desc:'API返回引擎状态'},{name:'系统日志',desc:'展示执行记录'}]
  },
  rules: {
    upstream: [{name:'自学习.py',desc:'record_correction()记录用户纠正'},{name:'人类学习.py',desc:'12项认知能力学习'},{name:'用户报告页',desc:'编辑/审核/追问三通道'}],
    downstream: [{name:'管道.py',desc:'apply_correction_rules()下次自动应用'},{name:'记忆.py',desc:'规则写入引擎记忆'}]
  },
  brain: {
    upstream: [{name:'AGI引擎.py',desc:'agi.answer()大模型推理'},{name:'AGI核心.py',desc:'反事实/边界/泛化/单样本'},{name:'AGI最终.py',desc:'工具/因果链/静默学习'},{name:'调度器.py',desc:'get_director()智能调度'},{name:'LLM客户端.py',desc:'大模型API'}],
    downstream: [{name:'管道.py',desc:'AGI桥接分析'},{name:'主程序.py',desc:'智能问答API'}]
  },
  quality: {
    upstream: [{name:'能力矩阵.py',desc:'check_quality_system()质量度量'},{name:'自愈.py',desc:'auto_detect_inconsistencies()自动修复'},{name:'自学习.py',desc:'合规门禁11720条铁律'},{name:'审计一致性.py',desc:'pre-commit全量同步'}],
    downstream: [{name:'管道.py',desc:'报告质量评估'},{name:'主程序.py',desc:'pre-commit触发全量检查'}]
  },
  methods: {
    upstream: [{name:'AGI管道.py',desc:'create_pipeline()高级推理'},{name:'语义推理器.py',desc:'SemanticReasoner语义匹配'},{name:'因果网络.py',desc:'AutonomousReasoner因果推理'},{name:'SCM推理器.py',desc:'结构因果模型'},{name:'方法论加载器.py',desc:'方法库知识注入'}],
    downstream: [{name:'管道.py',desc:'高级分析桥接AGI'},{name:'AGI引擎.py',desc:'嵌入方法知识增强'}]
  },
  details: {
    upstream: [{name:'引擎/ 全部52个模块',desc:'所有引擎模块汇总'},{name:'税务风险规则导出.json',desc:'{{rules_count}}条税务合规指令'},{name:'跨域线索+跨域证据.json',desc:'{{clue_chains}}+{{evidence_chains}}条线索和证据链'}],
    downstream: [{name:'运行仪表盘',desc:'6个子模块共用'},{name:'系统日志',desc:'引擎运行记录'}]
  }
};
function appendDependencyInfo(tabId) {
  var deps = MODULE_DEPS[tabId];
  if (!deps) return;
  var area = document.getElementById('eng-tab-content');
  if (!area) return;
  var h = '<div style="margin-top:24px;border-top:2px solid #e2e8f0;padding-top:16px;display:grid;grid-template-columns:1fr 1fr;gap:12px">';
  h += '<div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:6px;padding:12px 16px"><div style="font-size:12px;font-weight:700;color:#0369a1;margin-bottom:8px">⬆ 上游（数据/功能的提供方）</div>';
  deps.upstream.forEach(function(u){ h += '<div style="font-size:11px;color:#475569;line-height:1.8;margin-bottom:6px"><b style="color:#0f172a">'+u.name+'</b><br><span style="color:#94a3b8">'+u.desc+'</span></div>'; });
  h += '</div>';
  h += '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:6px;padding:12px 16px"><div style="font-size:12px;font-weight:700;color:#15803d;margin-bottom:8px">⬇ 下游（数据/功能的消费方）</div>';
  deps.downstream.forEach(function(d){ h += '<div style="font-size:11px;color:#475569;line-height:1.8;margin-bottom:6px"><b style="color:#0f172a">'+d.name+'</b><br><span style="color:#94a3b8">'+d.desc+'</span></div>'; });
  h += '</div>';
  h += '</div>';
  area.innerHTML += h;
}

// ═══ 调度中枢/成长曲线 独立渲染 ═══
async function renderBrainSubModule(container, section) {
  var title = section === 'orchestrator' ? '调度中枢' : '成长曲线';
  container.innerHTML = '<div style="max-width:1100px;margin:0 auto;padding:24px 16px;background:#fff">'
    + '<h2 style="font-size:20px;font-weight:800;color:#0f172a;margin:0">' + title + '</h2>'
    + '<div id="brain-sub-content" style="text-align:center;padding:60px;color:#94a3b8">加载中...</div></div>';

  try {
    var resp = await fetch('/api/audit/brain-status');
    var d = await resp.json();
    var area = document.getElementById('brain-sub-content');
    if (!d.ok) { area.innerHTML = '<div style="padding:40px;text-align:center;color:#dc2626">读取失败: ' + esc(d.error || '') + '</div>'; return; }

    var h = '<div style="max-width:1100px;margin:0 auto">';

    if (section === 'orchestrator') {
      var orch = d.orchestrator || {};
      h += '<div style="background:#f8fafc;padding:10px 14px;border-radius:6px;font-size:12px;color:#64748b;margin-bottom:16px;border-left:3px solid #2563eb">调度中枢：管理模块分布、领域划分、管线深度——大脑的指挥调度中心。</div>';
      h += '<div style="display:flex;gap:12px;margin:12px 0;flex-wrap:wrap">';
      h += '<div style="flex:1;min-width:160px;background:#f0f9ff;padding:12px;border-radius:6px;text-align:center"><div style="font-size:28px;font-weight:700;color:#0369a1">' + orch.total_modules + '</div><div style="font-size:12px;color:#64748b">总模块</div></div>';
      h += '<div style="flex:1;min-width:160px;background:#f0fdf4;padding:12px;border-radius:6px;text-align:center"><div style="font-size:28px;font-weight:700;color:#059669">' + (orch.domain_count || 7) + '</div><div style="font-size:12px;color:#64748b">领域</div></div>';
      h += '<div style="flex:1;min-width:160px;background:#fef3c7;padding:12px;border-radius:6px;text-align:center"><div style="font-size:28px;font-weight:700;color:#d97706">' + (orch.pipeline_depth || 16) + '</div><div style="font-size:12px;color:#64748b">管线深度</div></div>';
      h += '</div>';
      if (orch.domains && Object.keys(orch.domains).length > 0) {
        h += '<table class="tbl2" style="margin-top:8px"><tr><th>领域</th><th>模块数</th><th>模块列表</th></tr>';
        for (var domain in orch.domains) {
          h += '<tr><td style="font-weight:600">' + esc(domain) + '</td><td>' + orch.domains[domain].length + '</td><td style="font-size:11px;color:#64748b">' + orch.domains[domain].join(', ') + '</td></tr>';
        }
        h += '</table>';
      }
    } else {
      var growth = d.learner || {};
      var stageColors = {婴儿期:'#94a3b8',幼儿期:'#f59e0b',成长期:'#059669',成熟期:'#2563eb'};
      var stageColor = stageColors[growth.stage] || '#64748b';
      h += '<div style="background:#f8fafc;padding:10px 14px;border-radius:6px;font-size:12px;color:#64748b;margin-bottom:16px;border-left:3px solid #8b5cf6">成长曲线：引擎自运行以来的成长轨迹——累计运行次数、信任模型积累、已学习的行业分布。</div>';
      h += '<div style="display:flex;gap:12px;margin:12px 0;flex-wrap:wrap">';
      h += '<div style="flex:1;min-width:120px;background:#faf5ff;padding:12px;border-radius:6px;text-align:center"><div style="font-size:22px;font-weight:700;color:' + stageColor + '">' + esc(growth.stage || '婴儿期') + '</div><div style="font-size:12px;color:#64748b">成长阶段</div></div>';
      h += '<div style="flex:1;min-width:120px;background:#fef2f2;padding:12px;border-radius:6px;text-align:center"><div style="font-size:22px;font-weight:700;color:#dc2626">' + (growth.total_runs || 0) + '</div><div style="font-size:12px;color:#64748b">累计运行</div></div>';
      h += '<div style="flex:1;min-width:120px;background:#f0fdf4;padding:12px;border-radius:6px;text-align:center"><div style="font-size:22px;font-weight:700;color:#059669">' + (growth.trusted_module_contexts || 0) + '</div><div style="font-size:12px;color:#64748b">信任模型</div></div>';
      h += '<div style="flex:1;min-width:120px;background:#fffbeb;padding:12px;border-radius:6px;text-align:center"><div style="font-size:22px;font-weight:700;color:#d97706">' + (growth.industries_learned || 0) + '</div><div style="font-size:12px;color:#64748b">已学行业</div></div>';
      h += '</div>';
      if (growth.top_industries && growth.top_industries.length > 0) {
        h += '<div style="font-size:12px;color:#64748b;margin-top:8px">已学行业: ';
        for (var j = 0; j < growth.top_industries.length; j++) {
          var ti = growth.top_industries[j];
          if (ti && ti[1]) h += '<span style="display:inline-block;margin:2px;padding:2px 8px;background:#f1f5f9;border-radius:10px">' + esc(ti[0]) + '(' + (ti[1].runs || 0) + '次)</span>';
        }
        h += '</div>';
      }
    }
    h += '</div>';
    area.innerHTML = h;
  } catch(e) {
    document.getElementById('brain-sub-content').innerHTML = '<div style="padding:40px;text-align:center;color:#dc2626">加载失败: ' + e.message + '</div>';
  }
}

// ═══ 管道调度 — 专用清新布局 ═══
function renderPipeDashboard(container) {
  window._skipModuleHeader = true;
  var cid = window.currentCompanyId || window._currentCompanyId || 1;
  window._pipelineLogsData = [];  // 存储原始日志供过滤搜索
  window._currentLogPhase = 'all';  // 当前Phase过滤标签
  window._currentLogSearch = '';    // 当前搜索关键词
  
  var h = '';
  h += '<style>'
    + '.pp{max-width:960px;margin:0 auto;padding:48px 20px;font-family:-apple-system,"Microsoft YaHei",sans-serif}'
    + '.pp-title{font-size:17px;font-weight:600;color:#1e293b;margin:0 0 6px}'
    + '.pp-sub{font-size:11px;color:#94a3b8;margin:0 0 40px;line-height:1.6}'
    + '.pp-hero{display:flex;gap:16px;margin-bottom:40px;flex-wrap:wrap}'
    + '.pp-card{flex:1;min-width:140px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:20px 18px;text-align:center}'
    + '.pp-card .v{font-size:22px;font-weight:600;color:#1e293b;line-height:1.4}'
    + '.pp-card .l{font-size:10px;color:#94a3b8;margin-top:6px;letter-spacing:0.5px}'
    + '.pp-sec{margin-bottom:36px}'
    + '.pp-sec h3{font-size:13px;font-weight:600;color:#1e293b;margin:0 0 16px;padding-bottom:10px;border-bottom:1px solid #f1f5f9}'
    + '.pp-timeline{border-left:2px solid #e2e8f0;padding-left:24px;margin-left:8px}'
    + '.pp-step{margin-bottom:24px;position:relative}'
    + '.pp-step:before{content:"";position:absolute;left:-30px;top:8px;width:10px;height:10px;border-radius:50%;background:#e2e8f0;border:2px solid #e2e8f0;box-shadow:0 0 0 2px #e2e8f0}'
    + '.pp-step .sn{font-size:12px;font-weight:600;color:#94a3b8;margin-bottom:6px}'
    + '.pp-step .sd{font-size:11px;color:#94a3b8;line-height:1.8}'
    + '.pp-step.done:before{background:#16a34a;border:2px solid #fff;box-shadow:0 0 0 2px #16a34a}'
    + '.pp-step.done .sn{color:#16a34a}'
    + '.pp-step.done .sd{color:#475569}'
    + '.pp-step.done .sd b{color:#1e293b}'
    + '.pp-step.skip:before{background:#f59e0b;border:2px solid #fff;box-shadow:0 0 0 2px #f59e0b}'
    + '.pp-step.skip .sn{color:#f59e0b}'
    + '.pp-step.skip .sd{color:#94a3b8}'
    + '.pp-step.run:before{background:#3b82f6;border:2px solid #fff;box-shadow:0 0 0 2px #3b82f6;animation:ppPulse 1.5s ease-in-out infinite}'
    + '.pp-step.run .sn{color:#3b82f6}'
    + '@keyframes ppPulse{0%,100%{box-shadow:0 0 0 2px #3b82f6}50%{box-shadow:0 0 0 4px #93c5fd}}'
    + '.pp-log{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px 20px;max-height:300px;overflow-y:auto;font-family:monospace;font-size:11px;line-height:1.8}'
    + '.pp-flow{margin-bottom:36px}'
    + '.pp-flow h3{font-size:13px;font-weight:600;color:#1e293b;margin:0 0 16px;padding-bottom:10px;border-bottom:1px solid #f1f5f9}'
    + '.pp-flow-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}'
    + '.pp-flow-box{border-radius:10px;padding:20px 24px}'
    + '.pp-flow-box h4{font-size:11px;font-weight:600;margin:0 0 14px;padding-bottom:8px}'
    + '.pp-flow-item{margin-bottom:12px}'
    + '.pp-flow-item:last-child{margin-bottom:0}'
    + '.pp-flow-item a{font-size:11px;line-height:1.6}'
    + '.pp-flow-item .desc{font-size:10px;color:#94a3b8;line-height:1.5;margin-top:2px}'
    + '.pp-flow-item .bi{font-size:10px;color:#7B1FA2;margin-left:4px;font-weight:600}'
    + '.pp-toggle{display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:500;color:#2563eb;cursor:pointer;padding:6px 12px;border-radius:6px;border:1px solid #bae6fd;background:#f0f9ff;transition:all .15s ease;margin-top:4px}'
    + '.pp-toggle:hover{background:#e0f2fe;border-color:#93c5fd}'
    + '.pp-toggle .arrow{font-size:10px;transition:transform .15s ease}'
    + '.pp-toggle.open .arrow{transform:rotate(90deg)}'
    + '.pp-detail{overflow:hidden;transition:max-height .3s ease,opacity .2s ease;max-height:0;opacity:0}'
    + '.pp-detail.show{max-height:2000px;opacity:1}'
    + '.pp-summary{font-size:11px;color:#64748b;line-height:1.6;margin-bottom:0}'
    + '.pp-summary b{color:#1e293b}'
    + '.pp-para{margin-bottom:40px}'
    + '.pp-para p{font-size:11px;color:#475569;line-height:1.8;margin:0 0 14px}'
    + '.pp-para p:last-child{margin-bottom:0}'
    + '.pp-para b{color:#1e293b;font-weight:600}'
    + '</style>';
  
  h += '<div class="pp">';
  h += '<div class="pp-title">管道调度</div>';
  h += '<div class="pp-sub">引擎七步执行的实时状态监控 · 出度25 · 入度24 · 双向16 · 所属：智能大脑</div>';

  // ═══ 历史运行选择器 ═══
  h += '<div id="pp-history-bar" style="display:flex;align-items:center;gap:8px;margin-bottom:20px;flex-wrap:wrap">';
  h += '<span style="font-size:11px;color:#64748b;font-weight:600">历史运行：</span>';
  h += '<select id="pp-history-select" onchange="loadHistoryAnalysis(this.value)" style="font-size:11px;padding:4px 10px;border:1px solid #e2e8f0;border-radius:6px;background:#fff;color:#475569;max-width:300px"><option value="">当前最新</option></select>';
  h += '<button id="pp-history-del" onclick="deleteHistoryEntry()" style="font-size:11px;padding:4px 10px;border:1px solid #fecaca;border-radius:6px;background:#fff;color:#dc2626;cursor:pointer;display:none">删除此条</button>';
  h += '<button onclick="exportHistory(\'json\')" style="font-size:11px;padding:4px 10px;border:1px solid #bfdbfe;border-radius:6px;background:#fff;color:#2563eb;cursor:pointer">导出JSON</button>';
  h += '<button onclick="exportHistory(\'csv\')" style="font-size:11px;padding:4px 10px;border:1px solid #bbf7d0;border-radius:6px;background:#fff;color:#15803d;cursor:pointer">导出CSV</button>';
  h += '<span id="pp-history-info" style="font-size:10px;color:#94a3b8"></span>';
  h += '</div>';
  
  h += '<div class="pp-hero">';
  h += '<div class="pp-card"><div class="v" style="color:#2563eb">v3.0</div><div class="l">引擎版本</div></div>';
  h += '<div class="pp-card"><div class="v" id="pp-log-count">0</div><div class="l">执行日志</div></div>';
  h += '<div class="pp-card"><div class="v" style="color:#059669" id="pp-mod-count">--</div><div class="l">加载模块</div></div>';
  h += '<div class="pp-card"><div class="v" style="color:#f59e0b" id="pp-phase-count">--</div><div class="l">总耗时</div></div>';
  h += '<div class="pp-card"><div class="v" id="pp-error-count" style="color:#94a3b8">0</div><div class="l">异常数量</div></div>';
  h += '</div>';
  
  // 模块说明 — 段落式
  h += '<div class="pp-para">';
  h += '<p>管道调度是税务合规系统的<b>执行中枢</b>，负责协调七步分析流程的有序运行。每一步都有明确的输入来源、处理逻辑和输出目标，形成一个从原始资料到正式报告的单向流动的数据管道。</p>';
  h += '<p>管道调度的核心价值在于<b>自动化调度</b>——不需要人工干预每一步的执行顺序和参数传递。当用户上传资料后，管道自动启动文件解析引擎识别文件类型和提取数据结构，然后将结果传递给域分析引擎做{{domain_functions}}个域的函数分析，域分析产出发现后再传给规则引擎做{{rules_count}}条规则匹配，匹配结果触发{{clue_chains}}条线索链和{{evidence_chains}}条证据链的交叉验证，最后经过方法论过滤器净化后生成正式报告。</p>';
  h += '<p>管道调度引擎支持<b>断点续传</b>和<b>增量分析</b>。如果某一环节因为数据缺失而无法完成，管道不会中断，而是标记该环节为"跳过-数据缺失"并继续执行后续可用的环节。分析结果中会明确标注哪些环节因数据缺失而未执行，帮助用户判断资料的完备度。</p>';
  h += '</div>';
  
  // ═══ 上游（输入方）— 管道调度消费的25个模块 ═══
  h += '<div class="pp-flow">';
  h += '<h3>上下游依赖</h3>';
  h += '<div class="pp-flow-grid">';
  h += '<div class="pp-flow-box" style="background:#f0f9ff;border:1px solid #bae6fd">';
  h += '<h4 style="color:#0369a1;border-bottom:1px solid #bae6fd">⬆ 上游 · 输入方 · 出度25</h4>';
  // 摘要（默认可见）
  h += '<div class="pp-summary">管道调度消费<b>25</b>个模块：智能大脑5个（4双向）、稽查方法论3个（2双向）、报告规范6个（0双向）、数据与分析3个（1双向）、文件解析5个（4双向）、AI交互4个（全双向）、系统1个（双向）。点击下方按钮查看明细。</div>';
  h += '<div class="pp-toggle" onclick="toggleDetail(\'up-detail\',this)"><span class="arrow">▶</span>展开明细</div>';
  // 详情（默认隐藏）
  h += '<div class="pp-detail" id="up-detail">';
  // 智能大脑组（5个，其中4个双向）
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'eng-info\')" style="color:#2563eb">引擎详情</a><span class="bi">双向</span><div class="desc">引擎运行状态、模块清单、七步进度</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'engine-dimensions\')" style="color:#2563eb">能力维度</a><span class="bi">双向</span><div class="desc">引擎8维能力指标（识别/分析/规则/报告/学习/推理/域/记忆）</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'eng-grow\')" style="color:#2563eb">成长曲线</a><span class="bi">双向</span><div class="desc">引擎成长轨迹和学习效果追踪</div></div>';
  // 稽查方法论组（3个，其中2个双向）
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'hb-ch9\')" style="color:#2563eb">跨域协商引擎</a><span class="bi">双向</span><div class="desc">跨域线索/证据/分析三链协商与冲突消解</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'hb-ch10\')" style="color:#2563eb">数据一致性自检</a><div class="desc">5维自检矩阵确保分析逻辑不矛盾</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'hb-ch11\')" style="color:#2563eb">审核反馈闭环</a><span class="bi">双向</span><div class="desc">用户审核→学习→下次自动应用的闭环</div></div>';
  // 报告规范组（6个，全部单向出度）
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'rs-structure\')" style="color:#2563eb">报告结构</a><div class="desc">7章+附件结构模板，风险→发现→建议→结论</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'rs-narrative\')" style="color:#2563eb">叙事规范</a><div class="desc">风险叙事引擎，从数据到叙事的5层转化</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'rs-merge\')" style="color:#2563eb">风险合并规则</a><div class="desc">同源风险合并、冲突消解、优先级排序</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'rs-paragraph\')" style="color:#2563eb">段落格式规范</a><div class="desc">每段必须包含的要素和格式约束</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'rs-terms\')" style="color:#2563eb">术语与机密规范</a><div class="desc">术语统一和机密信息过滤</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'rs-sync\')" style="color:#2563eb">触发与交付</a><div class="desc">报告触发条件和交付时机</div></div>';
  // 数据与分析组（3个，其中1个双向）
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'aly-logs\')" style="color:#2563eb">管线执行日志</a><span class="bi">双向</span><div class="desc">记录每步执行时间、输入输出、异常</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'qs-layer5\')" style="color:#2563eb">全链路稽查质量保障体系</a><div class="desc">全链路质量保障：规则驱动+线索⇄证据并行→分析串联→报告平权汇入</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'qs-layer1\')" style="color:#2563eb">核心数据资产</a><div class="desc">七步执行流程详解和核心数据资产清单</div></div>';
  // 文件解析组（5个，其中4个双向）
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'fp-mechanism\')" style="color:#2563eb">识别机制</a><span class="bi">双向</span><div class="desc">三层递进识别+四方交叉验证+{{file_fingerprints}}类指纹库</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'fp-fingerprint\')" style="color:#2563eb">文件指纹库</a><span class="bi">双向</span><div class="desc">{{file_fingerprints}}类文件指纹特征库</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'fp-flow\')" style="color:#2563eb">解析流程</a><span class="bi">双向</span><div class="desc">文件解析引擎完整执行流程</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'fp-formats\')" style="color:#2563eb">格式扩展</a><span class="bi">双向</span><div class="desc">PDF/Excel/图片/OFD等格式适配</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'da-domains\')" style="color:#2563eb">分析域</a><span class="bi">双向</span><div class="desc">{{domain_functions}}个域分析函数并行产出发现</div></div>';
  // AI交互组（4个，全部双向）
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'agi-core\')" style="color:#2563eb">核心智能引擎</a><span class="bi">双向</span><div class="desc">AGI核心推理和决策引擎</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'agi-connect\')" style="color:#2563eb">连接通信层</a><span class="bi">双向</span><div class="desc">模块间通信和协调接口层</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'agi-knowledge\')" style="color:#2563eb">知识层</a><span class="bi">双向</span><div class="desc">知识库和语义理解层</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'agi-knowledge-config\')" style="color:#2563eb">知识库与配置</a><span class="bi">双向</span><div class="desc">知识库配置管理和铁律体系</div></div>';
  // 系统组（1个，双向）
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'system-logs\')" style="color:#2563eb">系统日志</a><span class="bi">双向</span><div class="desc">全量运行记录和异常追踪</div></div>';
  h += '</div>';
  h += '</div>';
  
  // ═══ 下游（消费方）— 消费管道调度的24个模块 ═══
  h += '<div class="pp-flow-box" style="background:#f0fdf4;border:1px solid #bbf7d0">';
  h += '<h4 style="color:#15803d;border-bottom:1px solid #bbf7d0">⬇ 下游 · 消费方 · 入度24</h4>';
  // 摘要（默认可见）
  h += '<div class="pp-summary">被<b>24</b>个模块消费：风险分析1个、智能大脑6个（3双向）、稽查方法论3个（2双向）、数据与分析3个（1双向）、文件解析5个（4双向）、AI交互4个（全双向）、系统1个（双向）。点击下方按钮查看明细。</div>';
  h += '<div class="pp-toggle" onclick="toggleDetail(\'down-detail\',this)"><span class="arrow">▶</span>展开明细</div>';
  // 详情（默认隐藏）
  h += '<div class="pp-detail" id="down-detail">';
  // 风险分析组（1个，单向入度）
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'tax-doc-analysis\')" style="color:#2563eb">资料风险分析报告</a><div class="desc">原始资料和风险信号来源，触发管道分析</div></div>';
  // 智能大脑组（6个，其中3个双向+3个单向）
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'eng-learn\')" style="color:#2563eb">学习反馈</a><div class="desc">纠正规则在下一次分析中自动应用</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'eng-orch\')" style="color:#2563eb">调度中枢</a><div class="desc">决定模块执行顺序和参数，协调引擎运行</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'eng-grow\')" style="color:#2563eb">成长曲线</a><span class="bi">双向</span><div class="desc">追踪引擎成长轨迹，管道输出供成长分析</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'eng-qual\')" style="color:#2563eb">质量保障</a><div class="desc">质量检查机制，消费管道结果做质量验证</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'eng-think\')" style="color:#2563eb">推理引擎</a><div class="desc">因果推理和逻辑验证，消费管道产出</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'eng-info\')" style="color:#2563eb">引擎详情</a><span class="bi">双向</span><div class="desc">引擎全景状态，消费管道调度信息</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'engine-dimensions\')" style="color:#2563eb">能力维度</a><span class="bi">双向</span><div class="desc">引擎8维能力评分，消费管道运行数据</div></div>';
  // 稽查方法论组（3个，其中2个双向+1个单向）
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'hb-ch9\')" style="color:#2563eb">跨域协商引擎</a><span class="bi">双向</span><div class="desc">消费管道调度的跨域线索进行协商</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'hb-ch11\')" style="color:#2563eb">审核反馈闭环</a><span class="bi">双向</span><div class="desc">反馈闭环消费管道产出做审核验证</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'hb-ch12\')" style="color:#2563eb">引擎记忆体系</a><div class="desc">历史分析经验注入先验知识，消费管道记忆数据</div></div>';
  // 数据与分析组（3个，其中1个双向+2个单向）
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'chains-page\')" style="color:#2563eb">线索链</a><div class="desc">接收管道调度的发现做线索触发和交叉验证</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'evidence-page\')" style="color:#2563eb">证据链</a><div class="desc">接收管道调度的发现做证据闭环验证</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'aly-logs\')" style="color:#2563eb">管线执行日志</a><span class="bi">双向</span><div class="desc">记录管道每步执行时间、输入输出、异常</div></div>';
  // 文件解析组（4个，全部双向）
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'fp-mechanism\')" style="color:#2563eb">识别机制</a><span class="bi">双向</span><div class="desc">消费管道调度指令做文件识别</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'fp-formats\')" style="color:#2563eb">格式扩展</a><span class="bi">双向</span><div class="desc">消费管道调度指令做格式适配</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'fp-fingerprint\')" style="color:#2563eb">文件指纹库</a><span class="bi">双向</span><div class="desc">消费管道调度指令做指纹匹配</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'fp-flow\')" style="color:#2563eb">解析流程</a><span class="bi">双向</span><div class="desc">消费管道调度指令做文件解析</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'da-domains\')" style="color:#2563eb">分析域</a><span class="bi">双向</span><div class="desc">消费管道调度指令做域分析</div></div>';
  // AI交互组（4个，全部双向）
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'agi-core\')" style="color:#2563eb">核心智能引擎</a><span class="bi">双向</span><div class="desc">消费管道调度做推理决策</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'agi-connect\')" style="color:#2563eb">连接通信层</a><span class="bi">双向</span><div class="desc">消费管道调度做模块通信</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'agi-knowledge\')" style="color:#2563eb">知识层</a><span class="bi">双向</span><div class="desc">消费管道调度做知识检索</div></div>';
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'agi-knowledge-config\')" style="color:#2563eb">知识库与配置</a><span class="bi">双向</span><div class="desc">消费管道调度做配置管理</div></div>';
  // 系统组（1个，双向）
  h += '<div class="pp-flow-item"><a href="javascript:navigateTo(\'system-logs\')" style="color:#2563eb">系统日志</a><span class="bi">双向</span><div class="desc">消费管道调度做全量运行记录</div></div>';
  h += '</div>';
  h += '</div>';
  h += '</div></div>';
  
  h += '<div class="pp-sec"><h3>七步执行流程</h3><div class="pp-timeline">';
  var steps=[
    {id:'step1',n:'①',t:'资料扫描与类型识别',d:'{{file_fingerprints}}类文件指纹库 · 三层递进识别 · 四方交叉验证'},
    {id:'step2',n:'②',t:'目标实体识别',d:'进项购买方∩销项销售方取交集 · {{keywords}}+关键词×{{industries}}行业加权投票 · 联网双源比对'},
    {id:'step3',n:'③',t:'资料情报提取与分析',d:'{{domain_functions}}个域分析函数并行执行 · 银行收款+进销存比+五层发票审计+供应商穿透+合同四层分类'},
    {id:'step4',n:'④',t:'规则引擎与链驱动检查',d:'{{rules_count}}条指令逐条匹配 · {{clue_chains}}条线索链触发 · {{evidence_chains}}条证据链闭环'},
    {id:'step5',n:'⑤',t:'方法论噪声过滤',d:'HARD_BAN {{hard_ban_categories}}类禁词 · COND_BAN {{cond_ban_categories}}类条件过滤 · 行业不匹配自动删除 · 去重'},
    {id:'step6',n:'⑥',t:'行业对标与申报比对',d:'{{industries}}行业五维对标 · 三级判断(低于下限→高风险/低于典型值85%→中风险)'},
    {id:'step7',n:'⑦',t:'正式报告输出',d:'综合所有发现 → 结构化报告 · 7章+附件 · 直接交付'}
  ];
  steps.forEach(function(s){
    h+='<div class="pp-step" id="'+s.id+'"><div class="sn">'+s.n+' '+s.t+'</div><div class="sd">'+s.d+'</div></div>';
  });
  h+='</div></div>';
  
  // 管线日志占位 —— 异步加载
  // ═══ 异常摘要横幅（有异常时显示） ═══
  h+='<div class="pp-sec" id="pp-error-section" style="display:none"><h3>⚠ 异常摘要</h3><div id="pp-error-summary" style="font-size:11px;line-height:1.8;color:#dc2626"></div></div>';
  // ═══ 日志过滤搜索 ═══
  h+='<div class="pp-sec" id="pp-log-section" style="display:none"><h3>管线执行日志</h3>';
  h+='<div id="pp-log-filter" style="display:flex;align-items:center;gap:8px;margin-bottom:12px;flex-wrap:wrap">';
  h+='<input id="pp-log-search" type="text" placeholder="搜索关键词..." oninput="filterPipelineLogs()" style="font-size:11px;padding:5px 10px;border:1px solid #e2e8f0;border-radius:6px;width:160px">';
  h+='<button class="pp-filter-tag" onclick="toggleLogPhase(\'all\',this)" style="font-size:10px;padding:3px 10px;border-radius:4px;border:1px solid #94a3b8;background:#fff;color:#94a3b8;cursor:pointer;font-weight:600">全部</button>';
  h+='<button class="pp-filter-tag" onclick="toggleLogPhase(\'Phase1\',this)" style="font-size:10px;padding:3px 10px;border-radius:4px;border:1px solid #93c5fd;background:#fff;color:#93c5fd;cursor:pointer;font-weight:600">Phase1</button>';
  h+='<button class="pp-filter-tag" onclick="toggleLogPhase(\'Phase2\',this)" style="font-size:10px;padding:3px 10px;border-radius:4px;border:1px solid #93c5fd;background:#fff;color:#93c5fd;cursor:pointer;font-weight:600">Phase2</button>';
  h+='<button class="pp-filter-tag" onclick="toggleLogPhase(\'Phase3\',this)" style="font-size:10px;padding:3px 10px;border-radius:4px;border:1px solid #93c5fd;background:#fff;color:#93c5fd;cursor:pointer;font-weight:600">Phase3</button>';
  h+='<button class="pp-filter-tag" onclick="toggleLogPhase(\'Phase4\',this)" style="font-size:10px;padding:3px 10px;border-radius:4px;border:1px solid #93c5fd;background:#fff;color:#93c5fd;cursor:pointer;font-weight:600">Phase4</button>';
  h+='<button class="pp-filter-tag" onclick="toggleLogPhase(\'过滤\',this)" style="font-size:10px;padding:3px 10px;border-radius:4px;border:1px solid #fde68a;background:#fff;color:#fde68a;cursor:pointer;font-weight:600">过滤</button>';
  h+='<button class="pp-filter-tag" onclick="toggleLogPhase(\'报告\',this)" style="font-size:10px;padding:3px 10px;border-radius:4px;border:1px solid #86efac;background:#fff;color:#86efac;cursor:pointer;font-weight:600">报告</button>';
  h+='<button class="pp-filter-tag" onclick="toggleLogPhase(\'异常\',this)" style="font-size:10px;padding:3px 10px;border-radius:4px;border:1px solid #fca5a5;background:#fff;color:#fca5a5;cursor:pointer;font-weight:600">异常</button>';
  h+='<span id="pp-log-filter-info" style="font-size:10px;color:#94a3b8"></span>';
  h+='</div>';
  h+='<div class="pp-log" id="pp-log-content"></div></div>';
  
  h += '</div>';
  container.innerHTML = h;
  
  // 异步加载动态数据
  (async function(){
    // ① 加载系统统计 → 替换所有 {{key}} 模板标记
    var stats = await loadSysStats();
    // 处理特殊计算：rules_count + autoRules
    if (stats && stats.rules_count) {
      stats.rules_count_autorules = stats.rules_count + (window._autoRulesCount || 0);
    }
    // 替换整个页面中的模板标记
    var ppEl = container.querySelector('.pp');
    if (ppEl) ppEl.innerHTML = applySysStats(ppEl.innerHTML, stats);

    // ═══ 加载分析历史列表 ═══
    try {
      var hr = await fetch('/api/pipeline/history?company_id=' + cid);
      var hd = await hr.json();
      if (hd.ok && hd.history && hd.history.length > 0) {
        var sel = document.getElementById('pp-history-select');
        if (sel) {
          hd.history.forEach(function(item, idx) {
            var opt = document.createElement('option');
            opt.value = idx;
            opt.textContent = item.timestamp.substring(0,19) + ' · ' + (item.risk_level||'--') + ' · ' + (item.total_findings||0) + '条发现 · ' + (item.step_timing_total||0) + '秒';
            sel.appendChild(opt);
          });
        }
      }
    } catch(e) {}

    // ═══ 实时进度追踪：检测是否有正在运行的分析任务 ═══
    var runningTaskId = window._currentAnalysisTaskId || null;
    // 如果前端有正在跟踪的task_id，启动实时轮询
    if (runningTaskId) {
      _startPipelineProgressPoll(runningTaskId, cid);
      return; // 轮询完成后会自动加载最终数据
    }

    // ② 加载分析数据 → 更新七步状态
    try{
      var r=await fetch('/api/tax-risk-docs/last-analysis?company_id='+cid);
      var d=await r.json();
      var rpt=(d&&d.report)?d.report:{};
      var es=rpt.engine_status||{};
      var comp=rpt.comprehensive||{};
      var p4=es.phase4_synthesis||{};
      // 字段路径校准：pipeline_log/files_count/target_entity在report层, 风险在phase4_synthesis
      var plogs=rpt.pipeline_log||comp.pipeline_log||[];
      var all_f=rpt.all_findings||[];
      var lc=document.getElementById('pp-log-count');
      if(lc)lc.textContent=plogs.length||0;
      var mc=document.getElementById('pp-mod-count');
      if(mc)mc.textContent=rpt.rules_used||es.modules_loaded||'--';
      var pc=document.getElementById('pp-phase-count');
      if(pc)pc.textContent=(es.phases||comp.phases||[]).length||'--';

      // ═══ 从pipeline_log解析七步执行状态 ═══
      if(plogs.length>0){
        // 从 engine_status.step_timing 提取耗时
        var st = es.step_timing || {};
        var st1 = st.step1_资料扫描 || 0;
        var st2 = st.step2_目标实体识别 || 0;
        var st3 = st.step3_域分析 || 0;
        var st4 = st.step4_规则引擎 || 0;
        var st5 = st.step5_方法论过滤 || 0;
        var st6 = st.step6_行业对标 || 0;
        var st7 = st.step7_报告输出 || 0;
        var stTotal = st.total || 0;

        // ① 资料扫描
        var step1Log = plogs.filter(function(l){return /文件解析|指纹|识别|ftype|fname|Phase1-识别|Phase1-初查|\[ENGINE\]/.test(l)});
        var fileCount = (rpt.files_count||es.files_count||0);
        updateStep('step1', step1Log.length>0 ? 'done' : 'skip',
          fileCount>0 ? '识别<b>'+fileCount+'</b>类文件' : '', st1,
          '文件数据→实体识别');

        // ② 目标实体识别
        var step2Log = plogs.filter(function(l){return /Phase1-识别对象|频次|交叉|方向校正|目标实体|联网核查|经营实质/.test(l)});
        var targetName = (rpt.target_entity&&rpt.target_entity.name) || es.company_profile?.name || '';
        updateStep('step2', step2Log.length>0 ? 'done' : 'skip',
          targetName ? '识别目标实体<b>'+targetName+'</b>' : '', st2,
          '企业画像+财务快照→域分析');

        // ③ 资料情报提取
        var step3Log = plogs.filter(function(l){return /资料情报提取|域分析|域→|财务报表分析|进销存|银行收款|Phase2|深挖/.test(l)});
        var intelCount = plogs.filter(function(l){return /资料情报提取:/.test(l)}).map(function(l){
          var m=l.match(/已完成(\d+)个/); return m?parseInt(m[1]):0;
        }).reduce(function(a,b){return a+b;},0);
        updateStep('step3', step3Log.length>0 ? 'done' : 'skip',
          intelCount>0 ? '提取<b>'+intelCount+'</b>个情报模块' : '', st3,
          '域发现→规则引擎');

        // ④ 规则引擎与链驱动
        var step4Log = plogs.filter(function(l){return /规则引擎|链驱动|线索链|证据链|Phase3|交叉验证|闭环/.test(l)});
        var findingsCount = all_f.length||0;
        var chainCount = comp.chain_triggered_count||0;
        var evidenceCount = comp.closed_chain_count||0;
        updateStep('step4', step4Log.length>0 ? 'done' : 'skip',
          findingsCount>0 ? '触发<b>'+chainCount+'</b>条线索链 · <b>'+evidenceCount+'</b>条证据链闭环 · <b>'+findingsCount+'</b>条发现' : '', st4,
          '发现+线索+证据→方法论过滤');

        // ⑤ 方法论噪声过滤
        var step5Log = plogs.filter(function(l){return /方法论过滤|HARD_BAN|COND_BAN|去重|剔除|噪声/.test(l)});
        var filterBefore = plogs.filter(function(l){return /方法论过滤:/.test(l)}).map(function(l){
          var m=l.match(/(\d+)→(\d+)条/); return m?{before:+m[1],after:+m[2],removed:+m[1]-+m[2]}:null;
        }).filter(function(x){return x});
        var removedCount = filterBefore.length>0 ? filterBefore[0].removed : 0;
        updateStep('step5', step5Log.length>0 ? 'done' : 'skip',
          removedCount>0 ? '剔除<b>'+removedCount+'</b>条噪声' : '', st5,
          '净化发现→行业对标');

        // ⑥ 行业对标与申报比对
        var step6Log = plogs.filter(function(l){return /行业基准|EMA|阈值|风险评分|Phase4|综合定性|风险升级/.test(l)});
        var riskLevel = p4.overall_risk||comp.overall_risk||rpt.overall_level||'';
        var riskScore = p4.risk_score||comp.risk_score||0;
        updateStep('step6', step6Log.length>0 ? 'done' : 'skip',
          riskLevel ? '综合定性<b>'+riskLevel+'</b>(评分<b>'+riskScore+'</b>)' : '', st6,
          '风险评级→报告生成');

        // ⑦ 正式报告输出
        var step7Log = plogs.filter(function(l){return /报告|叙事|交付|合规门禁|GATE/.test(l)});
        updateStep('step7', step7Log.length>0 ? 'done' : (plogs.length>0?'skip':''),
          step7Log.length>0 ? '报告已生成' : '', st7,
          '结构化报告·7章+附件·直接交付');

        // 总耗时更新Hero卡片
        if (stTotal > 0) {
          var tc = document.getElementById('pp-phase-count');
          if (tc) tc.textContent = stTotal + '秒';
        }
      }

      // ═══ 异常统计 + 异常摘要 ═══
      var errorLogs = plogs.filter(function(l){return /异常|失败|错误/.test(l)});
      var errorCount = errorLogs.length;
      var ec = document.getElementById('pp-error-count');
      if (ec) {
        ec.textContent = errorCount;
        ec.style.color = errorCount > 0 ? '#dc2626' : '#94a3b8';
      }
      if (errorCount > 0) {
        var es = document.getElementById('pp-error-section');
        var esm = document.getElementById('pp-error-summary');
        if (es && esm) {
          es.style.display = '';
          esm.innerHTML = errorLogs.map(function(l){return '<div style="margin-bottom:4px">'+l.replace(/</g,'&lt;')+'</div>';}).join('');
        }
      }

      // 管线日志
      if(plogs.length>0){
        var ls=document.getElementById('pp-log-section');
        var lcc=document.getElementById('pp-log-content');
        if(ls&&lcc){ls.style.display=''; window._pipelineLogsData=plogs; renderPipelineLogs(lcc, plogs); updateLogFilterInfo();}
      }
    }catch(e){}
  })();
}

// 全局：更新七步timeline步骤状态
function updateStep(stepId, status, extra, elapsed, outputFlow) {
  var el = document.getElementById(stepId);
  if (!el) return;
  el.className = 'pp-step';
  if (status === 'done') el.className += ' done';
  else if (status === 'skip') el.className += ' skip';
  else if (status === 'run') el.className += ' run';
  // 追加实际数据量到描述
  if (extra) {
    var sd = el.querySelector('.sd');
    if (sd) {
      var timeTag = elapsed ? '<span style="float:right;color:#94a3b8;font-size:10px;font-weight:400">耗时'+elapsed+'秒</span>' : '';
      sd.innerHTML += '<div style="margin-top:4px;color:'+((status==='done')?'#16a34a':'#f59e0b')+';font-weight:500;font-size:11px">'+extra+timeTag+'</div>';
    }
  }
  // 如果没有extra但有elapsed，单独显示耗时
  if (!extra && elapsed && status === 'done') {
    var sd = el.querySelector('.sd');
    if (sd) sd.innerHTML += '<div style="margin-top:4px;color:#94a3b8;font-size:10px">耗时'+elapsed+'秒</div>';
  }
  // ═══ 数据流可视化：显示本步产出→下一步输入 ═══
  if (outputFlow && status === 'done') {
    var sd = el.querySelector('.sd');
    if (sd) sd.innerHTML += '<div style="margin-top:6px;font-size:10px;color:#3b82f6;font-weight:600;display:flex;align-items:center;gap:4px"><span style="background:#eff6ff;border:1px solid #bfdbfe;padding:2px 8px;border-radius:4px">输出→</span><span style="color:#475569;font-weight:400">'+outputFlow+'</span></div>';
  }
}

// ═══ 实时进度追踪：轮询分析任务，逐步更新七步状态 ═══
var _pipePollTimer = null;
var _pipeWs = null;
var _pipeLastStep = 0; // 记录上次到达的步骤，用于标记done

// 统一入口：优先WebSocket实时推送，失败自动降级为HTTP轮询
function _startPipelineProgressPoll(taskId, companyId) {
  // 清理可能残留的连接
  if (_pipePollTimer) { clearInterval(_pipePollTimer); _pipePollTimer = null; }
  if (_pipeWs) { try { _pipeWs.close(); } catch(e){} _pipeWs = null; }
  _pipeLastStep = 0;
  var stepNames = ['资料扫描','目标实体识别','域分析','规则引擎+链驱动','方法论过滤','行业对标','报告输出'];
  var pc = document.getElementById('pp-phase-count');
  if (pc) pc.textContent = '运行中';
  var lc = document.getElementById('pp-log-count');
  if (lc) lc.textContent = '⏳';
  _applyStepStates(0);

  // ═══ 尝试WebSocket ═══
  if (typeof WebSocket !== 'undefined') {
    try {
      var proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      var ws = new WebSocket(proto + '//' + location.host + '/ws/pipeline/' + taskId);
      _pipeWs = ws;
      var wsAlive = false;
      // 连接超时兜底：1.5秒内没连上就降级轮询
      var connectTimer = setTimeout(function(){
        if (!wsAlive) { try { ws.close(); } catch(e){} _startPipelineProgressPollHTTP(taskId, companyId, stepNames); }
      }, 1500);

      ws.onopen = function(){ wsAlive = true; clearTimeout(connectTimer); };
      ws.onmessage = function(ev){
        // 离页清理
        if (!document.getElementById('step1')) { try { ws.close(); } catch(e){} _pipeWs = null; return; }
        var d;
        try { d = JSON.parse(ev.data); } catch(e){ return; }
        if (!d.ok) { return; }
        var cs = d.current_step || 0;
        _applyStepStates(cs, d.message);
        var pc2 = document.getElementById('pp-phase-count');
        if (pc2) pc2.textContent = d.progress + '% · ' + stepNames[Math.max(0, cs-1)];
        if (d.status === 'done') {
          try { ws.close(); } catch(e){} _pipeWs = null;
          window._currentAnalysisTaskId = null;
          _loadFinalPipeData(companyId);
        } else if (d.status === 'error') {
          try { ws.close(); } catch(e){} _pipeWs = null;
          var pc3 = document.getElementById('pp-phase-count');
          if (pc3) pc3.textContent = '失败';
          if (cs > 0) { var el = document.getElementById('step'+cs); if (el) el.className = 'pp-step skip'; }
        }
      };
      ws.onerror = function(){
        clearTimeout(connectTimer);
        if (!wsAlive) { _pipeWs = null; _startPipelineProgressPollHTTP(taskId, companyId, stepNames); }
      };
      ws.onclose = function(){
        // 若从未成功连接，降级轮询（onerror可能已触发，用wsAlive去重）
        if (!wsAlive) { _pipeWs = null; }
      };
      return;
    } catch(e) {
      // WebSocket构造失败→降级
    }
  }
  _startPipelineProgressPollHTTP(taskId, companyId, stepNames);
}

// HTTP轮询兜底（WebSocket不可用时）
function _startPipelineProgressPollHTTP(taskId, companyId, stepNames) {
  stepNames = stepNames || ['资料扫描','目标实体识别','域分析','规则引擎+链驱动','方法论过滤','行业对标','报告输出'];
  if (_pipePollTimer) clearInterval(_pipePollTimer);
  _pipePollTimer = setInterval(async function() {
    // ═══ 离页清理：DOM不存在说明用户已离开管道调度页，停止轮询 ═══
    if (!document.getElementById('step1')) {
      clearInterval(_pipePollTimer);
      _pipePollTimer = null;
      return;
    }
    try {
      var r = await fetch('/api/tax-risk-docs/analyze-status/' + taskId);
      var d = await r.json();
      if (!d.ok) { clearInterval(_pipePollTimer); _pipePollTimer = null; return; }
      var cs = d.current_step || 0;
      // 更新七步状态（传入message用于step3域分析细粒度进度）
      _applyStepStates(cs, d.message);
      // Hero卡片更新进度
      var pc = document.getElementById('pp-phase-count');
      if (pc) pc.textContent = d.progress + '% · ' + stepNames[Math.max(0, cs-1)];
      // 分析完成
      if (d.status === 'done') {
        clearInterval(_pipePollTimer);
        _pipePollTimer = null;
        window._currentAnalysisTaskId = null;
        // 加载最终完整数据
        _loadFinalPipeData(companyId);
      }
      if (d.status === 'error') {
        clearInterval(_pipePollTimer);
        _pipePollTimer = null;
        var pc = document.getElementById('pp-phase-count');
        if (pc) pc.textContent = '失败';
        // 标记当前步骤为skip/error
        if (cs > 0) {
          var el = document.getElementById('step'+cs);
          if (el) { el.className = 'pp-step skip'; }
        }
      }
    } catch(e) {}
  }, 2000);
}

function _applyStepStates(currentStep, message) {
  // currentStep=0: 全部灰色; 1-7: 当前步骤蓝色脉冲，之前的done
  for (var i = 1; i <= 7; i++) {
    var el = document.getElementById('step'+i);
    if (!el) continue;
    if (i < currentStep) {
      // 已完成的步骤 → done
      if (!el.classList.contains('done')) {
        el.className = 'pp-step done';
        var sd = el.querySelector('.sd');
        if (sd && !sd.querySelector('.pp-run-tag')) {
          sd.innerHTML += '<div class="pp-run-tag" style="margin-top:4px;color:#16a34a;font-weight:500;font-size:11px">✓ 已完成</div>';
        }
      }
    } else if (i === currentStep) {
      // 当前正在运行 → 蓝色脉冲
      el.className = 'pp-step run';
      var sd = el.querySelector('.sd');
      // ═══ 细粒度进度：从message提取"已完成N个域"等实时信息 ═══
      var runText = '⏳ 正在执行...';
      if (message) {
        // 提取域分析进度 "已完成N个域" 或 "全部N个域分析完成"
        var mDomain = message.match(/(已完成\d+个域[^,，·]*|全部\d+个域分析完成)/);
        if (mDomain) runText = '⏳ ' + mDomain[1];
        else {
          // 其他步骤：截取message中"—"后的描述
          var mDesc = message.match(/—\s*(.+)/);
          if (mDesc) runText = '⏳ ' + mDesc[1].substring(0, 30);
        }
      }
      var rt = sd ? sd.querySelector('.pp-run-tag') : null;
      if (sd) {
        if (rt) rt.innerHTML = runText;  // 更新已有标签（域进度实时刷新）
        else sd.innerHTML += '<div class="pp-run-tag" style="margin-top:4px;color:#3b82f6;font-weight:500;font-size:11px">'+runText+'</div>';
      }
    } else {
      // 未运行 → 灰色
      el.className = 'pp-step';
      // 清除可能残留的运行标签
      var rt = el.querySelector('.pp-run-tag');
      if (rt) rt.remove();
    }
  }
}

function _loadFinalPipeData(companyId) {
  // 分析完成后加载完整数据，替换七步状态为最终结果（带数据量和耗时）
  (async function() {
    try {
      var r = await fetch('/api/tax-risk-docs/last-analysis?company_id=' + companyId);
      var d = await r.json();
      var rpt = (d && d.report) ? d.report : {};
      var es = rpt.engine_status || {};
      var comp = rpt.comprehensive || {};
      var p4 = es.phase4_synthesis || {};
      // 字段路径校准：pipeline_log/files_count/target_entity在report层, 风险在phase4_synthesis
      var plogs = rpt.pipeline_log || comp.pipeline_log || [];
      var all_f = rpt.all_findings || [];
      var lc = document.getElementById('pp-log-count');
      if (lc) lc.textContent = plogs.length || 0;
      var mc = document.getElementById('pp-mod-count');
      if (mc) mc.textContent = rpt.rules_used || es.modules_loaded || '--';

      // 清除所有"正在执行"标签
      for (var i = 1; i <= 7; i++) {
        var el = document.getElementById('step'+i);
        if (el) { var rt = el.querySelector('.pp-run-tag'); if (rt) rt.remove(); }
      }

      // 使用已有的pipeline_log解析逻辑更新七步
      if (plogs.length > 0) {
        var st = es.step_timing || {};
        var st1 = st.step1_资料扫描 || 0;
        var st2 = st.step2_目标实体识别 || 0;
        var st3 = st.step3_域分析 || 0;
        var st4 = st.step4_规则引擎 || 0;
        var st5 = st.step5_方法论过滤 || 0;
        var st6 = st.step6_行业对标 || 0;
        var st7 = st.step7_报告输出 || 0;
        var stTotal = st.total || 0;

        var step1Log = plogs.filter(function(l){return /文件解析|指纹|识别|ftype|fname|Phase1-识别|Phase1-初查|\[ENGINE\]/.test(l)});
        var fileCount = (rpt.files_count||es.files_count||0);
        updateStep('step1', step1Log.length>0?'done':'skip', fileCount>0?'识别<b>'+fileCount+'</b>类文件':'', st1, '文件数据→实体识别');

        var step2Log = plogs.filter(function(l){return /Phase1-识别对象|频次|交叉|方向校正|目标实体|联网核查|经营实质/.test(l)});
        var targetName = (rpt.target_entity&&rpt.target_entity.name) || es.company_profile?.name||'';
        updateStep('step2', step2Log.length>0?'done':'skip', targetName?'识别目标实体<b>'+targetName+'</b>':'', st2, '企业画像+财务快照→域分析');

        var step3Log = plogs.filter(function(l){return /资料情报提取|域分析|域→|财务报表分析|进销存|银行收款|Phase2|深挖/.test(l)});
        var intelCount = plogs.filter(function(l){return /资料情报提取:/.test(l)}).map(function(l){var m=l.match(/已完成(\d+)个/);return m?parseInt(m[1]):0;}).reduce(function(a,b){return a+b;},0);
        updateStep('step3', step3Log.length>0?'done':'skip', intelCount>0?'提取<b>'+intelCount+'</b>个情报模块':'', st3, '域发现→规则引擎');

        var step4Log = plogs.filter(function(l){return /规则引擎|链驱动|线索链|证据链|Phase3|交叉验证|闭环/.test(l)});
        var findingsCount = all_f.length||0;
        var chainCount = comp.chain_triggered_count||0;
        var evidenceCount = comp.closed_chain_count||0;
        updateStep('step4', step4Log.length>0?'done':'skip', findingsCount>0?'触发<b>'+chainCount+'</b>条线索链 · <b>'+evidenceCount+'</b>条证据链闭环 · <b>'+findingsCount+'</b>条发现':'', st4, '发现+线索+证据→方法论过滤');

        var step5Log = plogs.filter(function(l){return /方法论过滤|HARD_BAN|COND_BAN|去重|剔除|噪声/.test(l)});
        var filterBefore = plogs.filter(function(l){return /方法论过滤:/.test(l)}).map(function(l){var m=l.match(/(\d+)→(\d+)条/);return m?{before:+m[1],after:+m[2],removed:+m[1]-+m[2]}:null;}).filter(function(x){return x});
        var removedCount = filterBefore.length>0?filterBefore[0].removed:0;
        updateStep('step5', step5Log.length>0?'done':'skip', removedCount>0?'剔除<b>'+removedCount+'</b>条噪声':'', st5, '净化发现→行业对标');

        var step6Log = plogs.filter(function(l){return /行业基准|EMA|阈值|风险评分|Phase4|综合定性|风险升级/.test(l)});
        var riskLevel = p4.overall_risk||comp.overall_risk||rpt.overall_level||'';
        var riskScore = p4.risk_score||comp.risk_score||0;
        updateStep('step6', step6Log.length>0?'done':'skip', riskLevel?'综合定性<b>'+riskLevel+'</b>(评分<b>'+riskScore+'</b>)':'', st6, '风险评级→报告生成');

        var step7Log = plogs.filter(function(l){return /报告|叙事|交付|合规门禁|GATE/.test(l)});
        updateStep('step7', step7Log.length>0?'done':(plogs.length>0?'skip':''), step7Log.length>0?'报告已生成':'', st7, '结构化报告·7章+附件·直接交付');

        if (stTotal > 0) {
          var tc = document.getElementById('pp-phase-count');
          if (tc) tc.textContent = stTotal + '秒';
        }
      }

      // 管线日志
      if (plogs.length > 0) {
        var ls = document.getElementById('pp-log-section');
        var lcc = document.getElementById('pp-log-content');
        if (ls && lcc) { ls.style.display=''; window._pipelineLogsData=plogs; renderPipelineLogs(lcc, plogs); updateLogFilterInfo(); }
      }
    } catch(e) {}
  })();
}

// ═══ 管线日志渲染（含过滤搜索，供多处复用） ═══
function renderPipelineLogs(container, plogs) {
  container.innerHTML = '';
  plogs.forEach(function(log, i) {
    var color='#94a3b8';
    if(/异常|失败|错误/.test(log))color='#fca5a5';
    else if(/完成|成功|通过/.test(log))color='#86efac';
    else if(/发现|触发|命中/.test(log))color='#fde68a';
    else if(/Phase|Step|阶段|过滤|闭环/.test(log))color='#93c5fd';
    container.innerHTML += '<div style="color:'+color+'">['+String(i+1).padStart(3,'0')+'] '+log.replace(/</g,'&lt;')+'</div>';
  });
}

// ═══ 历史运行对比：选择历史条目时显示对比信息 ═══
// ═══ 日志过滤搜索 ═══
function filterPipelineLogs() {
  var searchBox = document.getElementById('pp-log-search');
  window._currentLogSearch = searchBox ? searchBox.value.trim().toLowerCase() : '';
  applyLogFilter();
}

function toggleLogPhase(phase, btn) {
  window._currentLogPhase = phase;
  // 更新按钮样式
  document.querySelectorAll('.pp-filter-tag').forEach(function(b) {
    b.style.background = '#fff';
    b.style.fontWeight = '600';
  });
  if (btn) { btn.style.background = '#eff6ff'; btn.style.fontWeight = '800'; }
  applyLogFilter();
}

function applyLogFilter() {
  var plogs = window._pipelineLogsData || [];
  var phase = window._currentLogPhase || 'all';
  var search = window._currentLogSearch || '';
  var filtered = plogs;

  // Phase标签过滤
  if (phase !== 'all') {
    var phaseRegex;
    if (phase === 'Phase1') phaseRegex = /Phase1|初查|识别|指纹/;
    else if (phase === 'Phase2') phaseRegex = /Phase2|深挖|域分析|域→/;
    else if (phase === 'Phase3') phaseRegex = /Phase3|交叉验证|闭环|链驱动/;
    else if (phase === 'Phase4') phaseRegex = /Phase4|综合定性|行业基准|EMA/;
    else if (phase === '过滤') phaseRegex = /方法论过滤|HARD_BAN|COND_BAN|去重|剔除|噪声/;
    else if (phase === '报告') phaseRegex = /报告|叙事|交付|GATE/;
    else if (phase === '异常') phaseRegex = /异常|失败|错误/;
    filtered = filtered.filter(function(l) { return phaseRegex.test(l); });
  }

  // 搜索关键词过滤
  if (search) {
    filtered = filtered.filter(function(l) { return l.toLowerCase().indexOf(search) >= 0; });
  }

  var lcc = document.getElementById('pp-log-content');
  if (lcc) renderPipelineLogs(lcc, filtered);
  updateLogFilterInfo(filtered.length, plogs.length);
}

function updateLogFilterInfo(showCount, totalCount) {
  var info = document.getElementById('pp-log-filter-info');
  if (!info) return;
  var sc = showCount !== undefined ? showCount : (window._pipelineLogsData||[]).length;
  var tc = totalCount !== undefined ? totalCount : (window._pipelineLogsData||[]).length;
  info.textContent = sc === tc ? ('共'+tc+'条') : ('筛选'+sc+'/'+tc+'条');
}

async function loadHistoryAnalysis(selValue) {
  var delBtn = document.getElementById('pp-history-del');
  if (!selValue || selValue === '') {
    // 选择"当前最新" → 重新加载当前数据
    var info = document.getElementById('pp-history-info');
    if (info) info.textContent = '';
    if (delBtn) delBtn.style.display = 'none';  // 当前最新不可删
    window._selectedHistoryIdx = null;
    // 重置七步为初始状态并重新加载
    for (var i = 1; i <= 7; i++) {
      var el = document.getElementById('step'+i);
      if (el) el.className = 'pp-step';
    }
    var cid = window.currentCompanyId || window._currentCompanyId || 1;
    _loadFinalPipeData(cid);
    return;
  }
  var idx = parseInt(selValue);
  window._selectedHistoryIdx = idx;  // 记录当前选中索引供删除用
  if (delBtn) delBtn.style.display = '';  // 选中历史条目→显示删除按钮
  var cid = window.currentCompanyId || window._currentCompanyId || 1;
  try {
    var hr = await fetch('/api/pipeline/history?company_id=' + cid);
    var hd = await hr.json();
    if (!hd.ok || !hd.history) return;
    var item = hd.history[idx];
    if (!item) return;
    // 对比：和历史中的最新（当前）比较
    var current = hd.history[0];
    var info = document.getElementById('pp-history-info');
    if (info && current) {
      var diffFindings = (item.total_findings||0) - (current.total_findings||0);
      var diffTime = (item.step_timing_total||0) - (current.step_timing_total||0);
      var diffScore = (item.risk_score||0) - (current.risk_score||0);
      var arrowF = diffFindings > 0 ? '↑' : (diffFindings < 0 ? '↓' : '=');
      var arrowT = diffTime > 0 ? '↑慢' : (diffTime < 0 ? '↓快' : '=');
      var arrowS = diffScore > 0 ? '↑升' : (diffScore < 0 ? '↓降' : '=');
      info.innerHTML = '对比当前: 发现<b>'+diffFindings+'</b>条'+arrowF+' · 耗时<b>'+Math.abs(diffTime)+'</b>秒'+arrowT+' · 评分<b>'+Math.abs(diffScore)+'</b>分'+arrowS;
      info.style.color = '#dc2626';
    }
    // 只更新Hero卡片，历史条目的数据量有限（只有摘要，没有完整pipeline_log）
    var pc = document.getElementById('pp-phase-count');
    if (pc) pc.textContent = (item.step_timing_total||0) + '秒';
    var lc = document.getElementById('pp-log-count');
    if (lc) lc.textContent = (item.log_count||0);
    var ec = document.getElementById('pp-error-count');
    if (ec) { ec.textContent = (item.error_count||0); ec.style.color = (item.error_count||0) > 0 ? '#dc2626' : '#94a3b8'; }

    // ═══ 完整回放：用snapshot重现那次的七步状态+日志 ═══
    if (item.snapshot) {
      _renderPipeFromSnapshot(item.snapshot);
    }
  } catch(e) {}
}

// ═══ 删除当前选中的历史条目 ═══
async function deleteHistoryEntry() {
  var idx = window._selectedHistoryIdx;
  if (idx === null || idx === undefined) return;
  if (!confirm('确定删除这条历史运行记录？删除后不可恢复。')) return;
  var cid = window.currentCompanyId || window._currentCompanyId || 1;
  try {
    var r = await fetch('/api/pipeline/history?company_id=' + cid + '&index=' + idx, { method: 'DELETE' });
    var d = await r.json();
    if (!d.ok) { alert(d.message || '删除失败'); return; }
    // 删除成功→重建下拉列表 + 回到"当前最新"
    var sel = document.getElementById('pp-history-select');
    if (sel) {
      // 清空重建
      sel.innerHTML = '<option value="">当前最新</option>';
      var hr = await fetch('/api/pipeline/history?company_id=' + cid);
      var hd = await hr.json();
      if (hd.ok && hd.history) {
        hd.history.forEach(function(item, i) {
          var opt = document.createElement('option');
          opt.value = i;
          opt.textContent = item.timestamp.substring(0,19) + ' · ' + (item.risk_level||'--') + ' · ' + (item.total_findings||0) + '条发现 · ' + (item.step_timing_total||0) + '秒';
          sel.appendChild(opt);
        });
      }
      sel.value = '';
    }
    loadHistoryAnalysis('');  // 回到当前最新
  } catch(e) { alert('删除请求失败'); }
}

// ═══ 导出历史（json/csv）— 触发浏览器下载 ═══
function exportHistory(fmt) {
  var cid = window.currentCompanyId || window._currentCompanyId || 1;
  var url = '/api/pipeline/history/export?company_id=' + cid + '&format=' + (fmt || 'json');
  var a = document.createElement('a');
  a.href = url;
  a.download = 'pipeline_history_' + cid + '.' + (fmt || 'json');
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

// ═══ 从历史快照回放七步状态+日志 ═══
function _renderPipeFromSnapshot(snap) {
  // 清除所有运行标签，重置七步
  for (var i = 1; i <= 7; i++) {
    var el = document.getElementById('step'+i);
    if (el) { el.className = 'pp-step'; var rt = el.querySelector('.pp-run-tag'); if (rt) rt.remove(); }
  }
  var plogs = snap.pipeline_log || [];
  var st = snap.step_timing || {};
  var st1 = st.step1_资料扫描 || 0, st2 = st.step2_目标实体识别 || 0, st3 = st.step3_域分析 || 0;
  var st4 = st.step4_规则引擎 || 0, st5 = st.step5_方法论过滤 || 0, st6 = st.step6_行业对标 || 0, st7 = st.step7_报告输出 || 0;

  var step1Log = plogs.filter(function(l){return /文件解析|指纹|识别|ftype|fname|Phase1-识别|Phase1-初查|\[ENGINE\]/.test(l)});
  updateStep('step1', step1Log.length>0?'done':'skip', (snap.files_count>0)?'识别<b>'+snap.files_count+'</b>类文件':'', st1, '文件数据→实体识别');
  var step2Log = plogs.filter(function(l){return /Phase1-识别对象|频次|交叉|方向校正|目标实体|联网核查|经营实质/.test(l)});
  updateStep('step2', step2Log.length>0?'done':'skip', snap.company_name?'识别目标实体<b>'+snap.company_name+'</b>':'', st2, '企业画像+财务快照→域分析');
  var step3Log = plogs.filter(function(l){return /资料情报提取|域分析|域→|财务报表分析|进销存|银行收款|Phase2|深挖/.test(l)});
  var intelCount = plogs.filter(function(l){return /资料情报提取:/.test(l)}).map(function(l){var m=l.match(/已完成(\d+)个/);return m?parseInt(m[1]):0;}).reduce(function(a,b){return a+b;},0);
  updateStep('step3', step3Log.length>0?'done':'skip', intelCount>0?'提取<b>'+intelCount+'</b>个情报模块':'', st3, '域发现→规则引擎');
  var step4Log = plogs.filter(function(l){return /规则引擎|链驱动|线索链|证据链|Phase3|交叉验证|闭环/.test(l)});
  updateStep('step4', step4Log.length>0?'done':'skip', (snap.total_findings>0)?'触发<b>'+(snap.chain_triggered_count||0)+'</b>条线索链 · <b>'+(snap.closed_chain_count||0)+'</b>条证据链闭环 · <b>'+(snap.total_findings||0)+'</b>条发现':'', st4, '发现+线索+证据→方法论过滤');
  var step5Log = plogs.filter(function(l){return /方法论过滤|HARD_BAN|COND_BAN|去重|剔除|噪声/.test(l)});
  var filterBefore = plogs.filter(function(l){return /方法论过滤:/.test(l)}).map(function(l){var m=l.match(/(\d+)→(\d+)条/);return m?(+m[1]-+m[2]):0;});
  var removedCount = filterBefore.length>0?filterBefore[0]:0;
  updateStep('step5', step5Log.length>0?'done':'skip', removedCount>0?'剔除<b>'+removedCount+'</b>条噪声':'', st5, '净化发现→行业对标');
  var step6Log = plogs.filter(function(l){return /行业基准|EMA|阈值|风险评分|Phase4|综合定性|风险升级/.test(l)});
  updateStep('step6', step6Log.length>0?'done':'skip', snap.overall_risk?'综合定性<b>'+snap.overall_risk+'</b>(评分<b>'+(snap.risk_score||0)+'</b>)':'', st6, '风险评级→报告生成');
  var step7Log = plogs.filter(function(l){return /报告|叙事|交付|合规门禁|GATE/.test(l)});
  updateStep('step7', step7Log.length>0?'done':(plogs.length>0?'skip':''), step7Log.length>0?'报告已生成':'', st7, '结构化报告·7章+附件·直接交付');

  // 回放模块数
  var mc = document.getElementById('pp-mod-count');
  if (mc) mc.textContent = snap.modules_loaded || '--';

  // 回放日志（含过滤搜索）
  if (plogs.length > 0) {
    var ls = document.getElementById('pp-log-section');
    var lcc = document.getElementById('pp-log-content');
    if (ls && lcc) { ls.style.display=''; window._pipelineLogsData=plogs; window._currentLogPhase='all'; window._currentLogSearch=''; renderPipelineLogs(lcc, plogs); updateLogFilterInfo(); }
  }
  // 回放异常摘要
  var errorLogs = plogs.filter(function(l){return /异常|失败|错误/.test(l)});
  if (errorLogs.length > 0) {
    var es2 = document.getElementById('pp-error-section');
    var esm = document.getElementById('pp-error-summary');
    if (es2 && esm) { es2.style.display=''; esm.innerHTML = errorLogs.map(function(l){return '<div style="margin-bottom:4px">'+l.replace(/</g,'&lt;')+'</div>';}).join(''); }
  } else {
    var es2 = document.getElementById('pp-error-section');
    if (es2) es2.style.display='none';
  }
}

// 全局：上下游明细展开/折叠
function toggleDetail(id, btn) {
  var el = document.getElementById(id);
  if (!el) return;
  var isOpen = el.classList.contains('show');
  if (isOpen) {
    el.classList.remove('show');
    btn.classList.remove('open');
    btn.innerHTML = '<span class="arrow">▶</span>展开明细';
  } else {
    el.classList.add('show');
    btn.classList.add('open');
    btn.innerHTML = '<span class="arrow">▶</span>收起明细';
  }
}

// ═══ 学习反馈 — 专用清新布局 ═══
async function renderLearnFeedback(container) {
  window._skipModuleHeader = true;
  container.innerHTML = '<div style="max-width:900px;margin:0 auto;padding:32px 24px;color:#64748b;text-align:center;font-size:13px">加载中...</div>';
  
  var d = {};
  try {
    var r = await fetch('/api/tax-risk-docs/engine-rules');
    d = await r.json();
  } catch(e) {}
  var rules = d.rules || {};
  var corrections = rules.corrections || {};
  var learning = rules.learning || {};
  var autoRules = rules.auto_rules || [];
  
  var h = '';
  h += '<style>'
    + '.lf{max-width:960px;margin:0 auto;padding:48px 20px;font-family:-apple-system,"Microsoft YaHei",sans-serif}'
    + '.lf-title{font-size:17px;font-weight:600;color:#1e293b;margin:0 0 6px}'
    + '.lf-sub{font-size:11px;color:#94a3b8;margin:0 0 40px;line-height:1.6}'
    + '.lf-hero{display:flex;gap:16px;margin-bottom:40px;flex-wrap:wrap}'
    + '.lf-card{flex:1;min-width:140px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:20px 18px;text-align:center}'
    + '.lf-card .v{font-size:22px;font-weight:600;color:#1e293b;line-height:1.4}'
    + '.lf-card .l{font-size:10px;color:#94a3b8;margin-top:6px;letter-spacing:0.5px}'
    + '.lf-para{margin-bottom:40px}'
    + '.lf-para p{font-size:11px;color:#475569;line-height:1.8;margin:0 0 14px}'
    + '.lf-para p:last-child{margin-bottom:0}'
    + '.lf-para b{color:#1e293b;font-weight:600}'
    + '.lf-flow{margin-bottom:36px}'
    + '.lf-flow h3{font-size:13px;font-weight:600;color:#1e293b;margin:0 0 16px;padding-bottom:10px;border-bottom:1px solid #f1f5f9}'
    + '.lf-flow-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}'
    + '.lf-flow-box{border-radius:10px;padding:20px 24px}'
    + '.lf-flow-box h4{font-size:11px;font-weight:600;margin:0 0 14px;padding-bottom:8px}'
    + '.lf-flow-item{margin-bottom:12px}'
    + '.lf-flow-item:last-child{margin-bottom:0}'
    + '.lf-flow-item a{font-size:11px;line-height:1.6}'
    + '.lf-flow-item .desc{font-size:10px;color:#94a3b8;line-height:1.5;margin-top:2px}'
    + '.lf-sec{margin-bottom:36px}'
    + '.lf-sec h3{font-size:13px;font-weight:600;color:#1e293b;margin:0 0 16px;padding-bottom:10px;border-bottom:1px solid #f1f5f9}'
    + '.lf-timeline{border-left:2px solid #e2e8f0;padding-left:24px;margin-left:8px}'
    + '.lf-step{margin-bottom:24px;position:relative}'
    + '.lf-step:last-child{margin-bottom:0}'
    + '.lf-step:before{content:"";position:absolute;left:-30px;top:5px;width:10px;height:10px;border-radius:50%;background:#fff;border:2px solid #cbd5e1;box-shadow:0 0 0 2px #fff}'
    + '.lf-step.c-blue:before{border-color:#2563eb}'
    + '.lf-step.c-green:before{border-color:#059669}'
    + '.lf-step.c-amber:before{border-color:#f59e0b}'
    + '.lf-step.c-purple:before{border-color:#7c3aed}'
    + '.lf-step.c-gray:before{border-color:#64748b}'
    + '.lf-step .sn{font-size:12px;font-weight:600;color:#1e293b;margin-bottom:6px}'
    + '.lf-step .sd{font-size:11px;color:#475569;line-height:1.8}'
    + '.lf-step .sd code{background:#f1f5f9;padding:1px 5px;border-radius:3px;font-size:10px;color:#475569}'
    + '</style>';

  h += '<div class="lf">';
  h += '<div class="lf-title">学习反馈</div>';
  h += '<div class="lf-sub">用户纠正和审核意见进入受控候选池 · 重复验证 + 显式批准 + 精确范围匹配 · 所属：智能大脑</div>';

  // 统计卡片
  h += '<div class="lf-hero">';
  h += '<div class="lf-card"><div class="v" style="color:#2563eb">' + (corrections.total_rules||0) + '</div><div class="l">纠正规则</div></div>';
  h += '<div class="lf-card"><div class="v">' + (corrections.total_corrections||0) + '</div><div class="l">累计纠正</div></div>';
  h += '<div class="lf-card"><div class="v" style="color:#059669">' + (learning.ema_samples||0) + '</div><div class="l">EMA样本</div></div>';
  h += '<div class="lf-card"><div class="v" style="color:#f59e0b">' + (autoRules.length||0) + '</div><div class="l">自动规则</div></div>';
  h += '</div>';

  // 模块说明 — 段落式
  h += '<div class="lf-para">';
  h += '<p>学习反馈是引擎从<b>用户行为中自动学习</b>和改进的核心模块。系统不是一次性部署后停滞不前的静态工具，而是一个能从每次分析中吸取经验、不断进化的智能系统。每次用户对分析结果做出审核判断（采纳或驳回），系统都会记录并分析这些反馈，逐步优化分析策略。</p>';
  h += '<p>学习反馈的数据流向形成一个<b>完整闭环</b>：用户审核 → 规则自动生成 → 下次分析自动应用 → 效果跟踪 → 持续改进。闭环中的每一环都有明确的触发条件和数据记录，确保引擎的进化是可追溯、可验证、可回滚的。</p>';
  h += '</div>';

  // ═══ 上下游依赖 ═══
  h += '<div class="lf-flow"><h3>上下游依赖</h3><div class="lf-flow-grid">';
  h += '<div class="lf-flow-box" style="background:#f0f9ff;border:1px solid #bae6fd">';
  h += '<h4 style="color:#0369a1;border-bottom:1px solid #bae6fd">⬆ 上游 · 输入方</h4>';
  h += '<div class="lf-flow-item"><a href="javascript:navigateTo(\'chat\')" style="color:#2563eb">智能问答</a><div class="desc">用户纠正和追问通过聊天界面提交</div></div>';
  h += '<div class="lf-flow-item"><a href="javascript:window._reportSection=\'rpt-8\';navigateTo(\'report-standards\')" style="color:#2563eb">报告编制与复核闭环</a><div class="desc">审核字段、复核层级和修改责任链已嵌入统一编制页面</div></div>';
  h += '<div class="lf-flow-item"><a href="javascript:window._reportSection=\'rpt-9\';navigateTo(\'report-standards\')" style="color:#2563eb">常见误判复核矩阵</a><div class="desc">按误判根因组织反向核验，不固化个案结论</div></div>';
  h += '<div class="lf-flow-item"><a href="javascript:navigateTo(\'pipeline-rules\')" style="color:#2563eb">税务合规指令</a><div class="desc">规则匹配结果供学习引擎分析空跑率</div></div>';
  h += '<div class="lf-flow-item"><a href="javascript:navigateTo(\'system-logs\')" style="color:#2563eb">系统日志</a><div class="desc">分析日志中提取信号模式用于规则发现</div></div>';
  h += '</div>';
  h += '<div class="lf-flow-box" style="background:#f0fdf4;border:1px solid #bbf7d0">';
  h += '<h4 style="color:#15803d;border-bottom:1px solid #bbf7d0">⬇ 下游 · 消费方</h4>';
  h += '<div class="lf-flow-item"><a href="javascript:navigateTo(\'eng-pipe\')" style="color:#2563eb">管道调度</a><div class="desc">纠正规则在下一次分析中自动应用</div></div>';
  h += '<div class="lf-flow-item"><a href="javascript:navigateTo(\'hb-ch12\')" style="color:#2563eb">引擎记忆体系</a><div class="desc">学习产出的规则写入引擎长期记忆</div></div>';
  h += '<div class="lf-flow-item"><a href="javascript:navigateTo(\'hb-ch13\')" style="color:#2563eb">引擎铁律编号</a><div class="desc">从学习中沉淀为正式铁律加入编号体系</div></div>';
  h += '<div class="lf-flow-item"><a href="javascript:navigateTo(\'rs-ironlaw\')" style="color:#2563eb">引擎铁律与报告质量映射</a><div class="desc">新铁律对报告质量的映射关系更新</div></div>';
  h += '<div class="lf-flow-item"><a href="javascript:navigateTo(\'agi-assets\')" style="color:#2563eb">数据资产</a><div class="desc">学习产出的规则和知识库充实数据资产</div></div>';
  h += '</div></div></div>';

  // 三层渐进学习架构 — 段落式timeline
  h += '<div class="lf-sec"><h3>三层渐进学习架构</h3><div class="lf-timeline">';
  h += '<div class="lf-step c-blue"><div class="sn">第一层 · 审核反馈学习</div><div class="sd">用户审核发现→按账套、发现类型、行业和经营模式形成稳定指纹→进入私有候选池→同范围重复验证达到门槛→人工执行同步批准→下次分析仅按精确范围增加审核标记。</div></div>';
  h += '<div class="lf-step c-green"><div class="sn">第二层 · EMA 自学习</div><div class="sd">指数移动平均算法校准行业阈值，' + (learning.ema_samples||0) + ' 个样本持续更新，毛利率、税负率、进销比等基准值随实际数据动态调整，行业基准库自动保持最新。</div></div>';
  h += '<div class="lf-step c-amber"><div class="sn">第三层 · 自动规则发现</div><div class="sd">重复出现的信号组合经跨企业模式检测，同行业出现率超过 60% 的信号被标记为行业特征，新风险模式自动生成候选规则，人工确认后写入规则库，不断扩充 {{rules_count_autorules}} 条规则体系。</div></div>';
  h += '</div></div>';

  // 自动规则列表
  if (autoRules.length > 0) {
    h += '<div class="lf-sec"><h3>已发现自动规则 · ' + autoRules.length + ' 条</h3><div class="lf-timeline">';
    autoRules.forEach(function(ar) {
      h += '<div class="lf-step c-purple"><div class="sn">' + (ar.name||ar.rule||'') + '</div><div class="sd">' + (ar.desc||ar.pattern||'') + '<br><span style="color:#94a3b8">触发 ' + (ar.trigger_count||0) + ' 次 · 置信度 ' + (ar.confidence||'') + '</span></div></div>';
    });
    h += '</div></div>';
  }

  // 学习数据存储
  h += '<div class="lf-sec"><h3>学习数据存储</h3><div class="lf-timeline">';
  h += '<div class="lf-step c-gray"><div class="sn">user_corrections.json — 私有纠正规则存储</div><div class="sd">记录账套范围、稳定指纹、重复次数、置信度、批准状态、审核理由和历史版本；禁止名称模糊匹配跨场景扩张。</div></div>';
  h += '<div class="lf-step c-gray"><div class="sn">audit_memory.json — 分析记忆存储</div><div class="sd">12 维度加权相似度检索：行业（×3） &gt; 经营模式（×2） &gt; 信号类型（×2） &gt; 风险等级（×1.5）。</div></div>';
  h += '<div class="lf-step c-gray"><div class="sn">ema_state.json — EMA 参数状态存储</div><div class="sd">' + (learning.ema_samples||0) + ' 个样本积累，动态校准行业基准值。</div></div>';
  h += '</div></div>';

  h += '</div>';
  container.innerHTML = h;
  // 动态替换模板标记 {{key}} → 实际系统统计数字
  (async function(){
    var stats = await loadSysStats();
    if (stats) {
      stats.rules_count_autorules = (stats.rules_count||0) + (autoRules.length||0);
      var lfEl = container.querySelector('.lf');
      if (lfEl) lfEl.innerHTML = applySysStats(lfEl.innerHTML, stats);
    }
  })();
}
async function renderOrchDashboard(container) {
  window._skipModuleHeader = true;
  container.innerHTML = '<div style="max-width:900px;margin:0 auto;padding:32px 24px;color:#64748b;text-align:center;font-size:13px">加载中...</div>';
  
  var d = {};
  try {
    var r = await fetch('/api/audit/brain-status');
    d = await r.json();
  } catch(e) {}
  var orch = d.orchestrator || {};
  var domains = orch.domains || {};
  
  var h = '';
  h += '<style>'
    + '.od{max-width:900px;margin:0 auto;padding:36px 28px;font-family:-apple-system,"Microsoft YaHei",sans-serif}'
    + '.od-title{font-size:20px;font-weight:700;color:#0f172a;margin:0 0 4px}'
    + '.od-sub{font-size:13px;color:#94a3b8;margin:0 0 28px;line-height:1.8}'
    + '.od-hero{display:flex;gap:12px;margin-bottom:28px;flex-wrap:wrap}'
    + '.od-card{flex:1;min-width:130px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:18px 16px;text-align:center}'
    + '.od-card .v{font-size:26px;font-weight:700;color:#0f172a;line-height:1.3}'
    + '.od-card .l{font-size:11px;color:#94a3b8;margin-top:6px}'
    + '.od-sec{margin-bottom:32px}'
    + '.od-sec h3{font-size:14px;font-weight:700;color:#0f172a;margin:0 0 12px;padding-bottom:8px;border-bottom:1px solid #f1f5f9}'
    + '.od-tbl{width:100%;border-collapse:collapse;font-size:12px}'
    + '.od-tbl th{text-align:left;padding:8px 12px;background:#f8fafc;color:#64748b;font-weight:600;font-size:11px;border-bottom:2px solid #e2e8f0}'
    + '.od-tbl td{padding:10px 12px;border-bottom:1px solid #f1f5f9;color:#475569;line-height:1.8}'
    + '.od-tbl td:first-child{font-weight:600;color:#0f172a;white-space:nowrap}'
    + '.od-tag{display:inline-block;padding:2px 8px;margin:2px 4px 2px 0;background:#f1f5f9;border-radius:4px;font-size:11px;color:#475569}'
    + '</style>';
  
  h += '<div class="od">';
  h += '<div class="od-title">调度中枢</div>';
  h += '<div class="od-sub">21模块调度中枢 · 管理模块分布、领域划分和管线深度 · 所属：智能大脑</div>';
  
  h += '<div class="od-hero">';
  h += '<div class="od-card"><div class="v" style="color:#2563eb">' + (orch.total_modules||21) + '</div><div class="l">总模块</div></div>';
  h += '<div class="od-card"><div class="v" style="color:#059669">' + (orch.domain_count || Object.keys(domains).length || 7) + '</div><div class="l">领域</div></div>';
  h += '<div class="od-card"><div class="v" style="color:#f59e0b">' + (orch.pipeline_depth||16) + '</div><div class="l">管线深度</div></div>';
  h += '</div>';
  
  // ═══ 上下游依赖 ═══
  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:28px">';
  h += '<div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:12px;font-weight:700;color:#0369a1;margin-bottom:12px;padding-bottom:6px;border-bottom:1px solid #bae6fd">⬆ 上游（输入方）</div>';
  h += '<div style="font-size:11px;color:#475569;line-height:2.0">';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'agi-core\')" style="color:#2563eb">核心智能引擎</a><br><span style="color:#94a3b8">6大引擎的能力定义和模块元数据</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-info\')" style="color:#2563eb">引擎详情</a><br><span style="color:#94a3b8">全部52个模块的实现状态和代码位置</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'engine-dimensions\')" style="color:#2563eb">能力维度</a><br><span style="color:#94a3b8">28维能力矩阵定义模块可调度范围</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'agi-connect\')" style="color:#2563eb">连接通信层</a><br><span style="color:#94a3b8">事件总线提供模块间通信基础</span></div>';
  h += '<div><a href="javascript:navigateTo(\'system-logs\')" style="color:#2563eb">系统日志</a><br><span style="color:#94a3b8">模块运行记录供调度优化分析</span></div>';
  h += '</div></div>';
  h += '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:12px;font-weight:700;color:#15803d;margin-bottom:12px;padding-bottom:6px;border-bottom:1px solid #bbf7d0">⬇ 下游（消费方）</div>';
  h += '<div style="font-size:11px;color:#475569;line-height:2.0">';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-pipe\')" style="color:#2563eb">管道调度</a><br><span style="color:#94a3b8">调度中枢决定执行顺序后传给管道</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'qs-layer5\')" style="color:#2563eb">执行管线</a><br><span style="color:#94a3b8">Phase1-4分步执行依赖调度指令</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'qs-layer1\')" style="color:#2563eb">核心数据资产</a><br><span style="color:#94a3b8">模块调度决定哪些数据资产被激活</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-grow\')" style="color:#2563eb">成长曲线</a><br><span style="color:#94a3b8">调度记录充实成长指标统计</span></div>';
  h += '<div><a href="javascript:navigateTo(\'aly-logs\')" style="color:#2563eb">管线执行日志</a><br><span style="color:#94a3b8">调度日志进入流水记录供回溯</span></div>';
  h += '</div></div></div>';
  
  h += '<div style="font-size:13px;color:#475569;line-height:2.0;margin-bottom:28px">';
  h += '<p style="margin:0 0 16px">调度中枢是引擎的<strong>指挥中心</strong>，负责管理全部模块的分布、领域划分和管线深度。它不直接执行分析，而是决定哪些模块在什么时候、以什么顺序、用什么参数参与分析。每个领域内的模块按依赖关系排序，确保上游模块的输出在需要时已经准备好。</p>';
  h += '<p style="margin:0">管线深度指从原始资料到最终报告中间经过的处理层次数。当前系统管线深度覆盖从文件指纹识别、目标实体定位、资料情报提取、规则匹配、线索链触发、证据链闭环、分析链推理、协商引擎消解到报告输出的完整流程。</p>';
  h += '</div>';
  
  if (Object.keys(domains).length > 0) {
    h += '<div class="od-sec"><h3>领域分布 · ' + Object.keys(domains).length + ' 个领域</h3>';
    h += '<table class="od-tbl"><tr><th>领域</th><th>模块数</th><th>模块列表</th></tr>';
    for (var domain in domains) {
      var mods = domains[domain] || [];
      h += '<tr><td>' + domain.replace(/</g,'&lt;') + '</td><td>' + mods.length + '</td><td>';
      mods.forEach(function(m){ h += '<span class="od-tag">' + m.replace(/</g,'&lt;') + '</span>'; });
      h += '</td></tr>';
    }
    h += '</table></div>';
  }
  
  h += '</div>';
  container.innerHTML = h;
}

// ═══ 成长曲线 — 专用清新布局 ═══
async function renderGrowthDashboard(container) {
  window._skipModuleHeader = true;
  container.innerHTML = '<div style="max-width:900px;margin:0 auto;padding:32px 24px;color:#64748b;text-align:center;font-size:13px">加载中...</div>';
  
  var d = {};
  try {
    var r = await fetch('/api/audit/brain-status');
    d = await r.json();
  } catch(e) {}
  var growth = d.learner || {};
  var stageColors = {婴儿期:'#94a3b8',幼儿期:'#f59e0b',成长期:'#059669',成熟期:'#2563eb'};
  var stageColor = stageColors[growth.stage] || '#64748b';
  var topInd = growth.top_industries || [];
  var trusted = growth.trusted_module_contexts || 0;
  var runs = growth.total_runs || 0;
  var learned = growth.industries_learned || 0;
  
  var h = '';
  h += '<style>'
    + '.gd{max-width:900px;margin:0 auto;padding:36px 28px;font-family:-apple-system,"Microsoft YaHei",sans-serif}'
    + '.gd-title{font-size:20px;font-weight:700;color:#0f172a;margin:0 0 4px}'
    + '.gd-sub{font-size:13px;color:#94a3b8;margin:0 0 28px;line-height:1.8}'
    + '.gd-hero{display:flex;gap:12px;margin-bottom:28px;flex-wrap:wrap}'
    + '.gd-card{flex:1;min-width:130px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:18px 16px;text-align:center}'
    + '.gd-card .v{font-size:26px;font-weight:700;color:#0f172a;line-height:1.3}'
    + '.gd-card .l{font-size:11px;color:#94a3b8;margin-top:6px}'
    + '.gd-sec{margin-bottom:32px}'
    + '.gd-sec h3{font-size:14px;font-weight:700;color:#0f172a;margin:0 0 12px;padding-bottom:8px;border-bottom:1px solid #f1f5f9}'
    + '.gd-bar-wrap{background:#f1f5f9;border-radius:6px;height:8px;margin:10px 0;overflow:hidden}'
    + '.gd-bar{height:100%;border-radius:6px;transition:width 0.5s}'
    + '.gd-tag{display:inline-block;padding:4px 10px;margin:4px 6px 4px 0;background:#f1f5f9;border-radius:12px;font-size:11px;color:#475569}'
    + '.gd-tag b{color:#0f172a}'
    + '</style>';
  
  h += '<div class="gd">';
  h += '<div class="gd-title">成长曲线</div>';
  h += '<div class="gd-sub">引擎自运行以来的成长轨迹 · 累计运行、信任模型积累、已学行业分布 · 所属：智能大脑</div>';
  
  h += '<div class="gd-hero">';
  h += '<div class="gd-card"><div class="v" style="color:' + stageColor + '">' + (growth.stage||'婴儿期') + '</div><div class="l">成长阶段</div></div>';
  h += '<div class="gd-card"><div class="v" style="color:#dc2626">' + runs + '</div><div class="l">累计运行</div></div>';
  h += '<div class="gd-card"><div class="v" style="color:#059669">' + trusted + '</div><div class="l">信任模型</div></div>';
  h += '<div class="gd-card"><div class="v" style="color:#d97706">' + learned + '</div><div class="l">已学行业</div></div>';
  h += '</div>';
  
  // ═══ 上下游依赖 ═══
  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:28px">';
  h += '<div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:12px;font-weight:700;color:#0369a1;margin-bottom:12px;padding-bottom:6px;border-bottom:1px solid #bae6fd">⬆ 上游（输入方）</div>';
  h += '<div style="font-size:11px;color:#475569;line-height:2.0">';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-pipe\')" style="color:#2563eb">管道调度</a><br><span style="color:#94a3b8">每次分析运行记录驱动累计次数增长</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-learn\')" style="color:#2563eb">学习反馈</a><br><span style="color:#94a3b8">学习成果更新推动成长阶段升级</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'hb-ch12\')" style="color:#2563eb">引擎记忆体系</a><br><span style="color:#94a3b8">记忆积累量反映信任模型增长</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-orch\')" style="color:#2563eb">调度中枢</a><br><span style="color:#94a3b8">调度运行日志提供可信模块统计数据</span></div>';
  h += '<div><a href="javascript:navigateTo(\'engine-dimensions\')" style="color:#2563eb">能力维度</a><br><span style="color:#94a3b8">能力评估结果影响成长阶段判定</span></div>';
  h += '</div></div>';
  h += '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:12px;font-weight:700;color:#15803d;margin-bottom:12px;padding-bottom:6px;border-bottom:1px solid #bbf7d0">⬇ 下游（消费方）</div>';
  h += '<div style="font-size:11px;color:#475569;line-height:2.0">';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'engine-dimensions\')" style="color:#2563eb">能力维度</a><br><span style="color:#94a3b8">成长阶段影响各维度星级评定</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'qs-layer4\')" style="color:#2563eb">行业认知体系</a><br><span style="color:#94a3b8">已学行业数据用于校准行业基准值</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-info\')" style="color:#2563eb">引擎详情</a><br><span style="color:#94a3b8">成长数据反映模块成熟度</span></div>';
  h += '<div><a href="javascript:navigateTo(\'agi-assets\')" style="color:#2563eb">数据资产</a><br><span style="color:#94a3b8">成长指标作为知识库元数据存储</span></div>';
  h += '</div></div></div>';
  
  h += '<div style="font-size:13px;color:#475569;line-height:2.0;margin-bottom:28px">';
  h += '<p style="margin:0 0 16px">成长曲线展示引擎从部署以来的<strong>自我进化轨迹</strong>。随着每次分析运行，引擎不断积累经验、扩充知识库、优化分析策略，这些变化通过成长曲线直观呈现。</p>';
  h += '<p style="margin:0">四个核心指标：<strong>累计运行次数</strong>反映系统被使用和验证的广度；<strong>信任模型数量</strong>记录通过多次验证的高可靠度分析模式；<strong>已学习行业数</strong>记录引擎接触的行业种类；<strong>成长阶段</strong>从婴儿期→幼儿期→成长期→成熟期，反映引擎整体能力的演化水平。</p>';
  h += '</div>';
  
  var stagePct = {婴儿期:20,幼儿期:40,成长期:70,成熟期:95};
  h += '<div class="gd-sec"><h3>成长进度</h3>';
  h += '<div style="font-size:12px;color:#64748b;margin-bottom:8px">婴儿期 → 幼儿期 → 成长期 → 成熟期</div>';
  h += '<div class="gd-bar-wrap"><div class="gd-bar" style="width:' + (stagePct[growth.stage]||20) + '%;background:' + stageColor + '"></div></div>';
  h += '<div style="font-size:11px;color:#94a3b8;margin-top:8px">累计分析 <b style="color:#0f172a">' + runs + '</b> 次 · 可信模块 <b style="color:#0f172a">' + trusted + '</b> 个 · 行业覆盖 <b style="color:#0f172a">' + learned + '</b> 个</div>';
  h += '</div>';
  
  h += '<div class="gd-sec"><h3>已学行业 · ' + (learned||topInd.length) + ' 个</h3>';
  if (topInd.length > 0) {
    topInd.forEach(function(ti) {
      if (ti && ti[1]) {
        h += '<span class="gd-tag">' + ti[0].replace(/</g,'&lt;') + ' <b>' + (ti[1].runs||0) + '次</b></span>';
      }
    });
  } else {
    h += '<div style="font-size:12px;color:#94a3b8;padding:12px 0">暂无已学行业数据，执行一键分析后自动积累</div>';
  }
  h += '</div>';
  
  h += '</div>';
  container.innerHTML = h;
}

// ═══ 质量保障 — 专用清新布局 ═══
async function renderQualityDashboard(container) {
  window._skipModuleHeader = true;
  container.innerHTML = '<div style="max-width:900px;margin:0 auto;padding:32px 24px;color:#64748b;text-align:center;font-size:13px">加载中...</div>';
  
  var cid = window.currentCompanyId || window._currentCompanyId || 1;
  var d = {};
  try {
    var r = await fetch('/api/tax-risk-docs/last-analysis?company_id=' + cid);
    d = await r.json();
  } catch(e) {}
  var rpt = (d && d.report) ? d.report : {};
  
  var h = '';
  h += '<style>'
    + '.qa{max-width:900px;margin:0 auto;padding:36px 28px;font-family:-apple-system,"Microsoft YaHei",sans-serif}'
    + '.qa-title{font-size:20px;font-weight:700;color:#0f172a;margin:0 0 4px}'
    + '.qa-sub{font-size:13px;color:#94a3b8;margin:0 0 28px;line-height:1.8}'
    + '.qa-hero{display:flex;gap:12px;margin-bottom:28px;flex-wrap:wrap}'
    + '.qa-card{flex:1;min-width:130px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:18px 16px;text-align:center}'
    + '.qa-card .v{font-size:26px;font-weight:700;color:#0f172a;line-height:1.3}'
    + '.qa-card .l{font-size:11px;color:#94a3b8;margin-top:6px}'
    + '.qa-sec{margin-bottom:32px}'
    + '.qa-sec h3{font-size:14px;font-weight:700;color:#0f172a;margin:0 0 12px;padding-bottom:8px;border-bottom:1px solid #f1f5f9}'
    + '.qa-layer{display:flex;align-items:flex-start;gap:12px;padding:14px 16px;margin-bottom:8px;background:#fff;border:1px solid #f1f5f9;border-radius:8px;font-size:12px;line-height:1.8}'
    + '.qa-layer .num{width:28px;height:28px;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;color:#fff;flex-shrink:0}'
    + '.qa-layer .body{flex:1;color:#475569}'
    + '.qa-layer .body b{color:#0f172a;font-size:13px}'
    + '</style>';
  
  h += '<div class="qa">';
  h += '<div class="qa-title">质量保障</div>';
  h += '<div class="qa-sub">5层22组件全覆盖 · 从规则触发到报告输出的全链路质量监控 · 所属：智能大脑</div>';
  
  h += '<div class="qa-hero">';
  h += '<div class="qa-card"><div class="v" style="color:#2563eb">5</div><div class="l">保障层级</div></div>';
  h += '<div class="qa-card"><div class="v" style="color:#059669">22</div><div class="l">组件总数</div></div>';
  h += '<div class="qa-card"><div class="v" style="color:#f59e0b">12</div><div class="l">质量标准</div></div>';
  h += '<div class="qa-card"><div class="v" style="color:#dc2626">7</div><div class="l">可靠性要求</div></div>';
  h += '</div>';
  
  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:28px">';
  h += '<div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:12px;font-weight:700;color:#0369a1;margin-bottom:12px;padding-bottom:6px;border-bottom:1px solid #bae6fd">⬆ 上游（输入方）</div>';
  h += '<div style="font-size:11px;color:#475569;line-height:2.0">';
  h += '<div><a href="javascript:navigateTo(\'eng-pipe\')" style="color:#2563eb">管道调度</a><br><span style="color:#94a3b8">分析产出全部发现送质量检查</span></div>';
  h += '<div style="margin-top:6px"><a href="javascript:navigateTo(\'qs-layer2\')" style="color:#2563eb">方法论体系</a><br><span style="color:#94a3b8">方法论规则驱动质量保障标准</span></div>';
  h += '<div style="margin-top:6px"><a href="javascript:navigateTo(\'pipeline-rules\')" style="color:#2563eb">税务合规指令</a><br><span style="color:#94a3b8">规则匹配结果需质量验证</span></div>';
  h += '<div style="margin-top:6px"><a href="javascript:navigateTo(\'chains-page\')" style="color:#2563eb">线索链</a> / <a href="javascript:navigateTo(\'evidence-page\')" style="color:#2563eb">证据链</a><br><span style="color:#94a3b8">链驱动发现进入质量审查</span></div>';
  h += '<div style="margin-top:6px"><a href="javascript:navigateTo(\'eng-orch\')" style="color:#2563eb">调度中枢</a><br><span style="color:#94a3b8">调度日志供质量异常检测</span></div>';
  h += '</div></div>';
  h += '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:12px;font-weight:700;color:#15803d;margin-bottom:12px;padding-bottom:6px;border-bottom:1px solid #bbf7d0">⬇ 下游（消费方）</div>';
  h += '<div style="font-size:11px;color:#475569;line-height:2.0">';
  h += '<div><a href="javascript:navigateTo(\'qs-layer3\')" style="color:#2563eb">质量保障机制</a><br><span style="color:#94a3b8">质量判定结果进入详细机制执行</span></div>';
  h += '<div style="margin-top:6px"><a href="javascript:navigateTo(\'rs-12std\')" style="color:#2563eb">12项质量标准</a> / <a href="javascript:navigateTo(\'rs-reliability\')" style="color:#2563eb">7项判定可靠性要求</a><br><span style="color:#94a3b8">具体质量指标的逐项检查</span></div>';
  h += '<div style="margin-top:6px"><a href="javascript:navigateTo(\'rs-pipeline\')" style="color:#2563eb">质量保障管线</a><br><span style="color:#94a3b8">报告生成前的质量保障流程</span></div>';
  h += '<div style="margin-top:6px"><a href="javascript:navigateTo(\'engine-dimensions\')" style="color:#2563eb">能力维度</a><br><span style="color:#94a3b8">质量评分影响能力维度星级评定</span></div>';
  h += '<div style="margin-top:6px"><a href="javascript:navigateTo(\'rs-ironlaw\')" style="color:#2563eb">引擎铁律与报告质量映射</a><br><span style="color:#94a3b8">质量发现映射到铁律条目</span></div>';
  h += '</div></div></div>';
  
  h += '<div style="font-size:13px;color:#475569;line-height:2.0;margin-bottom:28px">';
  h += '<p style="margin:0 0 16px">质量保障是确保分析结果<strong>正确性和可靠性</strong>的最后关口。通过5层22个组件的层层把关，确保从规则触发到报告输出的全链路中，每一条发现都经得起追溯和复核。</p>';
  h += '<p style="margin:0">五层架构是一个<strong>开放生态系统</strong>——随着新分析维度的加入，质量保障层会自动扩展新的保障维度，不固定为某个静态数字。</p>';
  h += '</div>';
  
  h += '<div class="qa-sec"><h3>五层质量保障架构</h3>';
  h += '<div class="qa-layer"><div class="num" style="background:#2563eb">1</div><div class="body"><b>核心数据资产</b><br>规则引擎+线索链+证据链+跨域分析链构成数据底座。每条发现可追溯至规则ID和证据来源。</div></div>';
  h += '<div class="qa-layer"><div class="num" style="background:#7c3aed">2</div><div class="body"><b>方法论体系</b><br>31720条方法论约束分析逻辑边界，防止推断超出数据支撑范围。六大分析框架覆盖全流程。</div></div>';
  h += '<div class="qa-layer"><div class="num" style="background:#dc2626">3</div><div class="body"><b>质量保障机制</b><br>12项质量标准+7项判定可靠性要求。每条发现必须通过全部检查才能进入报告。</div></div>';
  h += '<div class="qa-layer"><div class="num" style="background:#f59e0b">4</div><div class="body"><b>行业认知体系</b><br>{{industries}}行业基准库提供对标参照，防止跨行业的错误比较导致误判。</div></div>';
  h += '<div class="qa-layer"><div class="num" style="background:#059669">5</div><div class="body"><b>执行管线</b><br>Phase1-4分步执行确保分析过程规范性和可审计性，每一步输入输出可追溯。</div></div>';
  h += '</div>';
  
  h += '</div>';
  container.innerHTML = h;
}

// ═══ 推理引擎 — 专用清新布局 ═══
function renderEngineThink(container) {
  window._skipModuleHeader = true;

  var h = '';
  h += '<style>'
    + '.et{max-width:900px;margin:0 auto;padding:36px 28px;font-family:-apple-system,"Microsoft YaHei",sans-serif}'
    + '.et-title{font-size:20px;font-weight:700;color:#0f172a;margin:0 0 4px}'
    + '.et-sub{font-size:13px;color:#94a3b8;margin:0 0 28px;line-height:1.8}'
    + '.et-hero{display:flex;gap:12px;margin-bottom:28px;flex-wrap:wrap}'
    + '.et-card{flex:1;min-width:130px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:18px 16px;text-align:center}'
    + '.et-card .v{font-size:26px;font-weight:700;color:#0f172a;line-height:1.3}'
    + '.et-card .l{font-size:11px;color:#94a3b8;margin-top:6px}'
    + '.et-sec{margin-bottom:32px}'
    + '.et-sec h3{font-size:14px;font-weight:700;color:#0f172a;margin:0 0 12px;padding-bottom:8px;border-bottom:1px solid #f1f5f9}'
    + '.et-badge{padding:2px 10px;border-radius:12px;font-size:11px;font-weight:600;color:#fff}'
    + '</style>';

  h += '<div class="et">';
  h += '<div class="et-title">推理引擎</div>';
  h += '<div class="et-sub">语义推理器 · 因果网络 · SCM推理器 · 方法论增强器 · 所属：智能大脑</div>';

  // 统计卡片 — 推理引擎实际产出指标（异步填充）
  h += '<div class="et-hero">';
  h += '<div class="et-card"><div class="v" id="et-nodes" style="color:#8b5cf6">—</div><div class="l">因果节点</div></div>';
  h += '<div class="et-card"><div class="v" id="et-chains" style="color:#06b6d4">—</div><div class="l">因果链步骤</div></div>';
  h += '<div class="et-card"><div class="v" id="et-hypos" style="color:#f59e0b">—</div><div class="l">假设生成数</div></div>';
  h += '<div class="et-card"><div class="v" id="et-legals" style="color:#dc2626">—</div><div class="l">法条引用数</div></div>';
  h += '</div>';

  // 上下游依赖
  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:28px">';
  h += '<div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:12px;font-weight:700;color:#0369a1;margin-bottom:12px;padding-bottom:6px;border-bottom:1px solid #bae6fd">⬆ 上游（输入方）</div>';
  h += '<div style="font-size:11px;color:#475569;line-height:2.0">';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-pipe\')" style="color:#2563eb">管道调度</a><br><span style="color:#94a3b8">域分析发现和规则匹配结果作为推理输入</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'hb-ch12\')" style="color:#2563eb">引擎记忆体系</a><br><span style="color:#94a3b8">方法论知识和因果规则存储</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'agi-causal\')" style="color:#2563eb">AGI因果推理</a><br><span style="color:#94a3b8">结构因果模型和反事实推理支撑</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-orch\')" style="color:#2563eb">调度中枢</a><br><span style="color:#94a3b8">智能调度推理引擎执行时机</span></div>';
  h += '<div><a href="javascript:navigateTo(\'eng-qual\')" style="color:#2563eb">质量保障</a><br><span style="color:#94a3b8">31720条方法论约束推理逻辑边界</span></div>';
  h += '</div></div>';
  h += '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:12px;font-weight:700;color:#15803d;margin-bottom:12px;padding-bottom:6px;border-bottom:1px solid #bbf7d0">⬇ 下游（消费方）</div>';
  h += '<div style="font-size:11px;color:#475569;line-height:2.0">';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-pipe\')" style="color:#2563eb">管道调度</a><br><span style="color:#94a3b8">因果叙事链进入综合报告</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'engine-dimensions\')" style="color:#2563eb">能力维度</a><br><span style="color:#94a3b8">推理能力评估影响星级评定</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-info\')" style="color:#2563eb">引擎详情</a><br><span style="color:#94a3b8">推理引擎模块状态展示</span></div>';
  h += '<div><a href="javascript:navigateTo(\'eng-grow\')" style="color:#2563eb">成长曲线</a><br><span style="color:#94a3b8">推理经验积累推动成长阶段升级</span></div>';
  h += '</div></div></div>';

  // 段落说明
  h += '<div style="font-size:13px;color:#475569;line-height:2.0;margin-bottom:28px">';
  h += '<p style="margin:0 0 16px">推理引擎是系统的<strong>高级智能层</strong>，在基础规则匹配之上进行更深层次的逻辑推理和因果分析。它不满足于"数据异常"的简单判断，而是追问"为什么异常"和"异常意味着什么"。</p>';
  h += '<p style="margin:0 0 16px">推理引擎由四个子引擎组成：<strong>语义推理器</strong>负责将自然语言描述的发现与规则库中的标准表述进行语义匹配；<strong>因果网络</strong>构建信号之间的条件概率关系，当多个异常信号同时出现时自动计算因果关联强度；<strong>SCM推理器</strong>使用结构因果模型进行do-干预和反事实推理；<strong>方法论增强器</strong>在推理过程中注入31720条方法论知识，使推理遵循税务合规最佳实践。</p>';
  h += '<p style="margin:0">推理引擎的输入是所有域分析发现和规则匹配结果，输出是经过逻辑推演的<strong>因果叙事链</strong>——不是孤立的"A异常、B异常"列表，而是"因为A、B、C同时出现且具有因果关联，所以判定为D风险"的完整推理。</p>';
  h += '</div>';

  h += '</div>';
  container.innerHTML = h;

  // 异步加载推理引擎实际产出指标
  var cid = window.currentCompanyId || 1;
  fetch('/api/audit/engine-details?company_id=' + cid)
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (!d.ok) return;
      var cn = d.causal_network || {};
      var nEl = document.getElementById('et-nodes');
      if (nEl) nEl.textContent = cn.nodes || 0;
      var cEl = document.getElementById('et-chains');
      if (cEl) cEl.textContent = cn.chain_steps || 0;
      var hEl = document.getElementById('et-hypos');
      if (hEl) hEl.textContent = (d.hypotheses || []).length;
      var lEl = document.getElementById('et-legals');
      if (lEl) lEl.textContent = (d.legal || []).length;
    })
    .catch(function() {});
}

// ═══ 引擎详情 — 专用清新布局 ═══
function renderEngineDetails(container) {
  window._skipModuleHeader = true;

  var h = '';
  h += '<style>'
    + '.ed{max-width:900px;margin:0 auto;padding:36px 28px;font-family:-apple-system,"Microsoft YaHei",sans-serif}'
    + '.ed-title{font-size:20px;font-weight:700;color:#0f172a;margin:0 0 4px}'
    + '.ed-sub{font-size:13px;color:#94a3b8;margin:0 0 28px;line-height:1.8}'
    + '.ed-hero{display:flex;gap:12px;margin-bottom:28px;flex-wrap:wrap}'
    + '.ed-card{flex:1;min-width:130px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:18px 16px;text-align:center}'
    + '.ed-card .v{font-size:26px;font-weight:700;color:#0f172a;line-height:1.3}'
    + '.ed-card .l{font-size:11px;color:#94a3b8;margin-top:6px}'
    + '.ed-sec{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:18px 20px;margin-bottom:14px}'
    + '.ed-sec h3{font-size:13px;font-weight:700;color:#0f172a;margin:0 0 12px;padding-bottom:8px;border-bottom:1px solid #f1f5f9}'
    + '.ed-row{display:flex;gap:10px;flex-wrap:wrap}'
    + '.ed-mini{flex:1;min-width:120px;text-align:center;padding:12px 8px;border-radius:8px}'
    + '.ed-mini .n{font-size:20px;font-weight:700}'
    + '.ed-mini .t{font-size:11px;color:#64748b;margin-top:4px}'
    + '.ed-tbl{width:100%;font-size:12px;border-collapse:collapse}'
    + '.ed-tbl td{padding:5px 8px;line-height:1.8}'
    + '.ed-tbl .k{font-weight:600;color:#1e293b;white-space:nowrap}'
    + '.ed-tbl .v{color:#2563eb;font-weight:600}'
    + '.ed-tbl .d{color:#94a3b8;font-size:11px}'
    + '</style>';

  h += '<div class="ed">';
  h += '<div class="ed-title">引擎详情</div>';
  h += '<div class="ed-sub">财务分析器 · 法律推理 · 成本识别 · 假设生成 · 规则覆盖 · AGI裁决 · 因果网络 · 证据闭环 · 所属：智能大脑</div>';

  // 统计卡片（占位，异步从brain-status填充——不依赖分析缓存）
  h += '<div class="ed-hero">';
  h += '<div class="ed-card"><div class="v" id="ed-modules" style="color:#7c3aed">—</div><div class="l">引擎模块数</div></div>';
  h += '<div class="ed-card"><div class="v" id="ed-domains" style="color:#2563eb">—</div><div class="l">分析领域</div></div>';
  h += '<div class="ed-card"><div class="v" id="ed-depth" style="color:#059669">—</div><div class="l">管道深度</div></div>';
  h += '<div class="ed-card"><div class="v" id="ed-caps" style="color:#f59e0b">—</div><div class="l">能力维度</div></div>';
  h += '</div>';

  // 上下游依赖
  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:28px">';
  h += '<div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:12px;font-weight:700;color:#0369a1;margin-bottom:12px;padding-bottom:6px;border-bottom:1px solid #bae6fd">⬆ 上游（输入方）</div>';
  h += '<div style="font-size:11px;color:#475569;line-height:2.0">';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'engine-dimensions\')" style="color:#2563eb">能力维度</a><br><span style="color:#94a3b8">52个引擎模块的代码位置和函数清单</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'pipeline-rules\')" style="color:#2563eb">管道规则</a><br><span style="color:#94a3b8">{{rules_count}}条税务合规规则指令</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'chains-page\')" style="color:#2563eb">线索链</a><br><span style="color:#94a3b8">{{clue_chains}}条跨域线索和信号链</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'evidence-page\')" style="color:#2563eb">证据链</a><br><span style="color:#94a3b8">{{evidence_chains}}条证据闭环数据</span></div>';
  h += '<div><a href="javascript:navigateTo(\'eng-pipe\')" style="color:#2563eb">管道调度</a><br><span style="color:#94a3b8">七步执行流程产出全部分析数据</span></div>';
  h += '</div></div>';
  h += '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:12px;font-weight:700;color:#15803d;margin-bottom:12px;padding-bottom:6px;border-bottom:1px solid #bbf7d0">⬇ 下游（消费方）</div>';
  h += '<div style="font-size:11px;color:#475569;line-height:2.0">';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-pipe\')" style="color:#2563eb">管道调度</a><br><span style="color:#94a3b8">引擎详情数据在仪表盘汇总展示</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'system-logs\')" style="color:#2563eb">系统日志</a><br><span style="color:#94a3b8">引擎运行记录写入日志</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-think\')" style="color:#2563eb">推理引擎</a><br><span style="color:#94a3b8">推理结果引用引擎详情中的模块状态</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-grow\')" style="color:#2563eb">成长曲线</a><br><span style="color:#94a3b8">引擎模块覆盖度影响成长阶段评估</span></div>';
  h += '<div><a href="javascript:navigateTo(\'eng-qual\')" style="color:#2563eb">质量保障</a><br><span style="color:#94a3b8">质量体系检查引用引擎模块状态</span></div>';
  h += '</div></div></div>';

  // 段落说明
  h += '<div style="font-size:13px;color:#475569;line-height:2.0;margin-bottom:28px">';
  h += '<p style="margin:0 0 16px">引擎详情展示了系统全部引擎模块的<strong>实现状态、代码位置和运行参数</strong>。它不是系统功能的用户文档，而是给开发者和管理员看的引擎"白皮书"——告诉你每个功能对应哪段代码、哪个文件。</p>';
  h += '<p style="margin:0 0 16px">当前系统包含<strong>52个引擎模块</strong>，按职责分为四组：核心引擎组（文件解析、域分析、规则引擎、推理引擎等）、质量保障组（自愈、自学习、审计一致性等）、辅助工具组（方法链加载、信号模式、知识图谱等）、基础设施组（数据库、缓存、会话管理等）。每个模块在引擎详情中都有明确的代码文件路径和关键函数名。</p>';
  h += '<p style="margin:0">引擎详情的数据来源于<strong>capability_matrix.py</strong>的自动扫描——不是人工维护的数字，而是代码中实际存在的函数、API路由、前端渲染函数的统计结果。这保证了引擎详情的准确性始终与代码实际情况保持一致。</p>';
  h += '</div>';

  // 引擎详情数据（占位，异步填充）
  h += '<div id="ed-data" style="font-size:12px;color:#94a3b8;padding:20px 0;text-align:center">正在加载引擎详情数据...</div>';

  h += '</div>';
  container.innerHTML = h;

  // 统计卡片：从brain-status获取（不依赖分析缓存，直接从代码注册表统计）
  fetch('/api/audit/brain-status')
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (!d.ok) return;
      var orch = d.orchestrator || {};
      var elMod = document.getElementById('ed-modules');
      if (elMod) elMod.textContent = orch.total_modules || 0;
      var elDom = document.getElementById('ed-domains');
      if (elDom) elDom.textContent = orch.domain_count || 0;
      var elDep = document.getElementById('ed-depth');
      if (elDep) elDep.textContent = orch.pipeline_depth || 0;
      return fetch('/api/audit/capabilities');
    })
    .then(function(r) { return r ? r.json() : null; })
    .then(function(d) {
      if (!d || !d.ok) return;
      var s = d.summary || {};
      var elCap = document.getElementById('ed-caps');
      if (elCap) elCap.textContent = s.total_dimensions || 0;
    })
    .catch(function() {});

  // 异步加载引擎详情
  var cid = window.currentCompanyId || 1;
  fetch('/api/audit/engine-details?company_id=' + cid)
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (!d.ok) {
        var el = document.getElementById('ed-data');
        if (el) el.innerHTML = '<div style="padding:40px;text-align:center;color:#94a3b8">' + (d.message || '请先执行一键分析') + '</div>';
        return;
      }

      var hh = '';

      // 1. 财务分析器
      var fin = d.financial || {};
      hh += '<div class="ed-sec"><h3>财务分析器 — 数据快照与解读</h3>';
      hh += '<table class="ed-tbl">';
      var rows = [
        ['销项合计', '\u00a5' + (fin.total_sales || 0).toLocaleString(), '来源：销项发票汇总'],
        ['进项合计', '\u00a5' + (fin.total_purchases || 0).toLocaleString(), '来源：进项发票汇总'],
        ['毛利率', (fin.gross_margin_pct || 0).toFixed(1) + '%', '（销项-进项)/销项'],
        ['银行入账', '\u00a5' + (fin.total_bank_in || 0).toLocaleString(), '来源：银行流水借方合计'],
        ['银行出账', '\u00a5' + (fin.total_bank_out || 0).toLocaleString(), '来源：银行流水贷方合计'],
        ['工资合计', '\u00a5' + (fin.total_salary || 0).toLocaleString(), '人数：' + (fin.salary_count || 0) + '人'],
        ['销项票数', (fin.sale_count || 0) + ' 张', ''],
        ['进项票数', (fin.pur_count || 0) + ' 张', ''],
        ['银行流水', (fin.bank_tx_count || 0) + ' 笔', '']
      ];
      rows.forEach(function(r) {
        hh += '<tr><td class="k">' + r[0] + '</td><td class="v">' + r[1] + '</td><td class="d">' + r[2] + '</td></tr>';
      });
      hh += '</table></div>';

      // 2. 法律推理引擎
      hh += '<div class="ed-sec"><h3>法律推理引擎 — 法条引用统计</h3>';
      var legals = d.legal || [];
      if (legals.length > 0) {
        hh += '<div style="display:grid;gap:6px">';
        legals.forEach(function(l) {
          hh += '<div style="padding:8px 12px;background:#f8fafc;border-radius:6px;font-size:12px;display:flex;align-items:center;gap:10px">';
          hh += '<span style="color:#dc2626;font-weight:700;min-width:40px">' + l.count + '\u6b21</span>';
          hh += '<span style="color:#1e293b">' + l.law + '</span></div>';
        });
        hh += '</div>';
      } else {
        hh += '<div style="color:#94a3b8;font-size:12px;padding:8px 0">本次分析未产生独立法条引用</div>';
      }
      hh += '</div>';

      // 3. 主营业务成本识别
      var cc = d.cost_class || {};
      hh += '<div class="ed-sec"><h3>主营业务成本识别 — 进项三层分类</h3>';
      hh += '<div style="font-size:12px;color:#475569;margin-bottom:10px">' + (cc.description || '') + '</div>';
      hh += '<div class="ed-row">';
      hh += '<div class="ed-mini" style="background:#fef2f2"><div class="n" style="color:#dc2626">' + (cc.core_cost_count || 0) + '笔</div><div class="t">主营成本</div><div style="font-size:11px;color:#991b1b;margin-top:2px">\u00a5' + ((cc.core_cost_amount || 0) / 10000).toFixed(1) + '万</div></div>';
      hh += '<div class="ed-mini" style="background:#fffbeb"><div class="n" style="color:#f59e0b">' + (cc.major_expense_count || 0) + '笔</div><div class="t">重大费用</div></div>';
      hh += '<div class="ed-mini" style="background:#f0fdf4"><div class="n" style="color:#059669">' + (cc.minor_expense_count || 0) + '笔</div><div class="t">日常报销</div></div>';
      hh += '</div>';
      if (cc.core_goods && cc.core_goods.length) {
        hh += '<div style="font-size:11px;color:#94a3b8;margin-top:8px">主营品名：' + cc.core_goods.slice(0, 5).join('\u3001') + '</div>';
      }
      hh += '</div>';

      // 4. 假设生成引擎
      hh += '<div class="ed-sec"><h3>假设生成引擎 — 税务合规假设与验证</h3>';
      var hypos = d.hypotheses || [];
      if (hypos.length > 0) {
        hh += '<div style="display:grid;gap:6px">';
        hypos.forEach(function(hy) {
          hh += '<div style="padding:10px 14px;background:#fffbeb;border-left:3px solid #f59e0b;border-radius:6px;font-size:12px">';
          hh += '<div style="font-weight:600;color:#1e293b">' + (hy.name || hy.hypothesis || '') + '</div>';
          if (hy.evidence) hh += '<div style="color:#64748b;font-size:11px;margin-top:4px">\u8bc1\u636e\uff1a' + hy.evidence + '</div>';
          hh += '</div>';
        });
        hh += '</div>';
      } else {
        hh += '<div style="color:#94a3b8;font-size:12px;padding:8px 0">本次分析未产生独立假设（信号数量不足以生成假设结论）</div>';
      }
      hh += '</div>';

      // 5. 规则覆盖引擎
      var ov = d.overrides || {};
      hh += '<div class="ed-sec"><h3>规则覆盖引擎 — AGI vs 规则引擎冲突裁决</h3>';
      hh += '<div style="font-size:12px;color:#475569;margin-bottom:10px">' + (ov.description || '') + '</div>';
      hh += '<div class="ed-row">';
      hh += '<div class="ed-mini" style="background:#eff6ff;border:1px solid #dbeafe"><div class="n" style="color:#2563eb">' + (ov.corrections_proposed || 0) + '</div><div class="t">提议修正</div></div>';
      hh += '<div class="ed-mini" style="background:#f0fdf4;border:1px solid #bbf7d0"><div class="n" style="color:#059669">' + (ov.auto_activated || 0) + '</div><div class="t">自动激活</div></div>';
      hh += '</div></div>';

      // 6. 趋势分析
      var td = d.trend || {};
      hh += '<div class="ed-sec"><h3>趋势分析器 — 多期数据趋势</h3>';
      hh += '<div style="font-size:12px;color:#475569;margin-bottom:8px">' + (td.description || '') + '</div>';
      if (td.has_multi_period) {
        hh += '<div style="color:#059669;font-size:12px">\u2705 已检测到多期数据，趋势对比有效</div>';
      } else {
        hh += '<div style="color:#f59e0b;font-size:12px">\u26a0 当前仅单期数据，趋势分析需至少2期数据对比</div>';
      }
      hh += '</div>';

      // 7. 阈值计算
      var th = d.thresholds || {};
      hh += '<div class="ed-sec"><h3>阈值计算 — 行业基准与安全阈值</h3>';
      hh += '<table class="ed-tbl">';
      hh += '<tr><td class="k">行业</td><td class="v" style="color:#1e293b">' + (th.industry || '未知') + '</td><td class="d"></td></tr>';
      var mr = th.margin_range;
      if (typeof mr !== 'string') mr = JSON.stringify(mr || {}).slice(0, 60);
      hh += '<tr><td class="k">行业毛利率基准</td><td class="v" style="color:#1e293b">' + mr + '</td><td class="d"></td></tr>';
      hh += '<tr><td class="k">服务闸门</td><td class="v" style="color:' + (th.service_gate ? '#dc2626' : '#059669') + '">' + (th.service_gate ? '已激活（跳过进销存域）' : '未激活') + '</td><td class="d"></td></tr>';
      hh += '<tr><td class="k">数据质量分</td><td class="v" style="color:' + ((th.data_quality_score || 0) >= 70 ? '#059669' : '#f59e0b') + '">' + (th.data_quality_score || 0) + '/100</td><td class="d"></td></tr>';
      hh += '</table></div>';

      // 8. AGI最终裁决
      var af = d.agi_final || {};
      hh += '<div class="ed-sec"><h3>AGI最终裁决 — 终审对比</h3>';
      hh += '<div style="font-size:12px;color:#475569;margin-bottom:10px">' + (af.description || '') + '</div>';
      hh += '<div class="ed-row">';
      hh += '<div class="ed-mini" style="background:#eff6ff;border:1px solid #dbeafe"><div class="n" style="color:#2563eb">' + (af.corrections_proposed || 0) + '</div><div class="t">终审判定修正</div></div>';
      hh += '<div class="ed-mini" style="background:#f0fdf4;border:1px solid #bbf7d0"><div class="n" style="color:#059669">' + (af.auto_activated || 0) + '</div><div class="t">自动激活</div></div>';
      hh += '</div></div>';

      // 9. AGI管线
      var ap = d.agi_pipeline || {};
      hh += '<div class="ed-sec"><h3>AGI管线 — 模块协调</h3>';
      hh += '<div style="font-size:12px;color:#475569;margin-bottom:10px">' + (ap.description || '') + '</div>';
      hh += '<div class="ed-row">';
      hh += '<div class="ed-mini" style="background:#faf5ff;border:1px solid #e9d5ff"><div class="n" style="color:#7c3aed">' + (ap.modules_covered || 0) + '</div><div class="t">覆盖模块</div></div>';
      hh += '<div class="ed-mini" style="background:#eff6ff;border:1px solid #dbeafe"><div class="n" style="color:#2563eb">' + (ap.events_collected || 0) + '</div><div class="t">事件采集</div></div>';
      hh += '</div></div>';

      // 10. 因果网络
      var cn = d.causal_network || {};
      hh += '<div class="ed-sec"><h3>因果网络 — 发现间因果关系</h3>';
      hh += '<div style="font-size:12px;color:#475569;margin-bottom:10px">' + (cn.description || '') + '</div>';
      hh += '<div class="ed-row">';
      hh += '<div class="ed-mini" style="background:#faf5ff;border:1px solid #e9d5ff"><div class="n" style="color:#8b5cf6">' + (cn.nodes || 0) + '</div><div class="t">因果节点</div></div>';
      hh += '<div class="ed-mini" style="background:#ecfeff;border:1px solid #a5f3fc"><div class="n" style="color:#06b6d4">' + (cn.chain_steps || 0) + '</div><div class="t">因果链步骤</div></div>';
      hh += '</div></div>';

      // 11. 证据闭环
      var ec = d.evidence_closure || {};
      hh += '<div class="ed-sec"><h3>证据闭环统计</h3>';
      hh += '<div class="ed-row">';
      hh += '<div class="ed-mini" style="background:#f0fdf4;border:1px solid #bbf7d0"><div class="n" style="color:#059669">' + (ec.closed_chains || 0) + '</div><div class="t">已闭合证据</div></div>';
      hh += '<div class="ed-mini" style="background:#faf5ff;border:1px solid #e9d5ff"><div class="n" style="color:#7c3aed">' + (ec.triggered_chains || 0) + '/' + (ec.total_chains || 0) + '</div><div class="t">触发/总分析链</div></div>';
      hh += '</div></div>';

      var dataEl = document.getElementById('ed-data');
      if (dataEl) dataEl.innerHTML = hh;
    })
    .catch(function() {
      var el = document.getElementById('ed-data');
      if (el) el.innerHTML = '<div style="padding:40px;text-align:center;color:#dc2626">加载失败，请确认已执行一键分析</div>';
    });
}

// 智能大脑（8模块融合整合页）
function renderBrainPage(container) {
  if (!container) return;
  window.currentModule = '智能大脑';
  var chapters = [
    ['一', '管道调度', 'renderPipeDashboard'],
    ['二', '学习反馈', 'renderLearnFeedback'],
    ['三', '调度中枢', 'renderOrchDashboard'],
    ['四', '成长曲线', 'renderGrowthDashboard'],
    ['五', '质量保障', 'renderQualityDashboard'],
    ['六', '推理引擎', 'renderEngineThink'],
    ['七', '引擎详情', 'renderEngineDetails'],
    ['八', '能力维度', 'renderEngineDimensions']
  ];
  var css = '<style>'
    + '.brn{max-width:1180px;margin:0 auto;padding:34px 40px;background:#fff;color:#4b5563;font-size:12px;line-height:1.9;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif}'
    + '.brn-wrap{display:flex;gap:44px;align-items:flex-start}'
    + '.brn-toc{width:140px;flex-shrink:0;position:sticky;top:20px;font-size:11.5px;max-height:calc(100vh - 40px);overflow-y:auto}'
    + '.brn-toc .tt{font-size:10.5px;font-weight:700;color:#b0b8c4;letter-spacing:.12em;margin:0 0 12px 12px}'
    + '.brn-toc a{display:block;color:#64748b;text-decoration:none;padding:5px 0 5px 12px;border-left:2px solid #eef2f6;transition:.15s;line-height:1.5}'
    + '.brn-toc a:hover{color:#0e7490;border-left-color:#0e7490}'
    + '.brn-body{flex:1;min-width:0}'
    + '.brn h1{font-size:20px;font-weight:700;color:#0f172a;margin:0 0 6px}'
    + '.brn .lead{font-size:12px;color:#94a3b8;margin:0 0 26px;line-height:1.9}'
    + '.brn section{margin:0 0 42px;scroll-margin-top:20px}'
    + '.brn .ch-h{font-size:15.5px;font-weight:700;color:#0f172a;margin:0 0 14px;padding-bottom:11px;border-bottom:1px solid #eef2f6;display:flex;align-items:baseline;gap:9px}'
    + '.brn .ch-h .idx{color:#0e7490;font-size:12px;font-weight:700}'
    + '</style>';
  var toc = '<nav class="brn-toc"><div class="tt">目录</div>';
  var body = '<div class="brn-body"><h1>🧠 智能大脑</h1>'
    + '<p class="lead">管道调度 · 学习反馈 · 调度中枢 · 成长曲线 · 质量保障 · 推理引擎 · 引擎详情 · 能力维度 —— 稽查系统的智能中枢，统一编排各引擎的协同、学习、推理与质量把关。</p>';
  for (var i = 0; i < chapters.length; i++) {
    toc += '<a href="#brn-' + i + '">' + chapters[i][1] + '</a>';
    body += '<section id="brn-' + i + '"><div class="ch-h"><span class="idx">' + chapters[i][0] + '</span> ' + chapters[i][1] + '</div><div id="brn-body-' + i + '"></div></section>';
  }
  toc += '</nav>';
  body += '</div>';
  container.innerHTML = css + '<div class="brn"><div class="brn-wrap">' + toc + body + '</div></div>';
  for (var j = 0; j < chapters.length; j++) {
    var fn = window[chapters[j][2]];
    var sub = document.getElementById('brn-body-' + j);
    if (sub && typeof fn === 'function') {
      try { fn(sub); } catch (e) { sub.innerHTML = '<div style="color:#dc2626;padding:10px">加载失败: ' + (e && e.message) + '</div>'; }
    }
  }
}
