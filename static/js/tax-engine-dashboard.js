/**
 * 推理引擎仪表盘 — 独立展示推理引擎 v2.0 的全部内部状态
 * Phase 1-4 完整可视化
 */

function renderEngineDashboardPage(container) {
  container.innerHTML = '<div style="max-width:1200px;margin:0 auto;padding:20px">'
    + '<h2 style="font-size:22px;font-weight:800;color:#0f172a;margin:0 0 4px">⚙️ 推理引擎仪表盘</h2>'
    + '<p style="font-size:13px;color:#94a3b8;margin:0 0 24px">智能体感知→推理→学习→表达→记忆五层架构运行状态</p>'
    + '<div id="engine-dashboard-area"><div style="text-align:center;padding:60px;color:#94a3b8"><span class="spinner"></span> 正在加载推理引擎数据...</div></div></div>';
  setTimeout(loadEngineDashboard, 200);
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
    {id:'status',icon:'📊',name:'运行状态',color:'#2563eb'},
    {id:'rules',icon:'📋',name:'规则库',color:'#7c3aed'},
    {id:'quality',icon:'✅',name:'质量保障',color:'#059669'},
    {id:'methods',icon:'🔬',name:'方法论对账',color:'#f59e0b'},
    {id:'negotiation',icon:'🤝',name:'跨域协商',color:'#0ea5e9'},
    {id:'brain',icon:'🧠',name:'智能大脑',color:'#dc2626'}
  ];

  // TOC sidebar layout
  var html = '<style>.ed-layout{display:flex;gap:24px}.ed-toc{width:180px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start}.ed-toc a{display:flex;align-items:center;gap:8px;padding:10px 14px;margin-bottom:4px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;color:#475569;text-decoration:none;font-size:13px;font-weight:500;cursor:pointer;transition:all 0.15s}.ed-toc a:hover,.ed-toc a.active{background:#eff6ff;border-color:#2563eb;color:#2563eb;font-weight:700}.ed-main{flex:1;min-width:0}</style>';
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
}

function renderStatusTab() {
  var es = window._engineEs || {};
  var area = document.getElementById('eng-tab-content');
  
  if (!window._hasEngineData) {
    area.innerHTML = '<div style="padding:60px 20px;text-align:center">' +
      '<div style="font-size:36px;margin-bottom:16px">🧠</div>' +
      '<div style="font-size:18px;color:#1e293b;font-weight:700;margin-bottom:8px">暂无分析数据</div>' +
      '<div style="font-size:13px;color:#64748b;margin-bottom:16px">运行状态需要先执行一键分析才能查看。</div>' +
      '<div style="font-size:13px;color:#64748b">请前往 <b>资料风险分析报告</b> 页面运行一键分析，或点击上方 <b>规则库</b> 标签查看全部推理规则。</div>' +
      '</div>';
    return;
  }
  
  var h = '';
  
  // ═══ 顶部：引擎版本 + 风险总览 ═══
  h += '<div style="background:linear-gradient(135deg,#1e293b,#334155);color:#fff;padding:24px 28px;border-radius:12px;margin-bottom:20px">';
  h += '<div style="font-size:22px;font-weight:700">推理引擎仪表盘 <span style="font-size:14px;color:#93c5fd;margin-left:12px">' + esc(es.version) + '</span></div>';
  h += '<div style="margin-top:12px;display:flex;gap:20px;flex-wrap:wrap">';
  
  if (es.phase4_synthesis && es.phase4_synthesis.overall_risk) {
    var riskColor = (es.phase4_synthesis.overall_risk === '极高风险') ? '#dc2626' : 
                    (es.phase4_synthesis.overall_risk === '高风险') ? '#dc2626' : 
                    (es.phase4_synthesis.overall_risk === '中风险') ? '#f59e0b' : '#059669';
    h += '<div style="background:rgba(255,255,255,0.1);padding:12px 18px;border-radius:8px"><div style="font-size:11px;color:#94a3b8">综合风险</div>';
    h += '<div style="font-size:20px;font-weight:700;color:' + riskColor + '">' + esc(es.phase4_synthesis.overall_risk) + '</div></div>';
    h += '<div style="background:rgba(255,255,255,0.1);padding:12px 18px;border-radius:8px"><div style="font-size:11px;color:#94a3b8">评分</div>';
    h += '<div style="font-size:20px;font-weight:700;color:#fbbf24">' + esc(es.phase4_synthesis.risk_score) + '/100</div></div>';
  }
  
  h += '<div style="background:rgba(255,255,255,0.1);padding:12px 18px;border-radius:8px"><div style="font-size:11px;color:#94a3b8">资料质量</div>';
  h += '<div style="font-size:20px;font-weight:700;color:' + (es.data_quality_score >= 70 ? '#4ade80' : '#fbbf24') + '">' + esc(es.data_quality_score) + '/100</div></div>';
  
  if (es.memories_count) {
    h += '<div style="background:rgba(255,255,255,0.1);padding:12px 18px;border-radius:8px"><div style="font-size:11px;color:#94a3b8">记忆库</div>';
    h += '<div style="font-size:20px;font-weight:700;color:#c084fc">' + esc(es.memories_count) + '条</div></div>';
  }
  
  h += '</div>';
  
  // 4阶段进度条
  h += '<div style="display:flex;gap:8px;margin-top:16px">';
  es.phases.forEach(function(p) {
    h += '<div style="flex:1;background:rgba(255,255,255,0.15);padding:8px 12px;border-radius:6px;text-align:center;font-size:12px;font-weight:600">' + esc(p) + '</div>';
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
  h += '<tr><td>毛利率</td><td><strong style="color:' + (fs.gross_margin_pct < 0 ? '#dc2626' : fs.gross_margin_pct > 50 ? '#f59e0b' : '#059669') + '">' + esc(fs.gross_margin_pct) + '%</strong></td></tr>';
  var ratio = fs.total_purchases > 0 ? (fs.total_sales / fs.total_purchases * 100) : 0;
  h += '<tr><td>购销比</td><td><strong style="color:' + (ratio < 80 ? '#dc2626' : ratio > 200 ? '#f59e0b' : '#059669') + '">' + ratio.toFixed(0) + '%</strong></td></tr>';
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
  
  // ═══ Phase 3：交叉验证 ═══
  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px">';
  
  // 信号叠加模式
  h += '<div class="engine-card" style="border-top:3px solid #06b6d4">';
  h += '<div class="engine-card-title"><span style="color:#06b6d4">■</span> Phase 3 — 信号叠加模式命中 (' + (es.phase3_pattern_hits || []).length + ')</div>';
  if (es.phase3_pattern_hits && es.phase3_pattern_hits.length) {
    es.phase3_pattern_hits.forEach(function(p) {
      var lc = p.level === '极高风险' || p.level === '高风险' ? '#dc2626' : p.level === '中风险' ? '#f59e0b' : '#059669';
      h += '<div style="padding:8px 12px;margin:4px 0;border-left:3px solid ' + lc + ';font-size:12px">';
      h += '<strong>' + esc(p.name) + '</strong>';
      h += '<span style="color:' + lc + ';margin-left:8px">' + esc(p.level) + '</span>';
      if (p.score) h += '<span style="color:#64748b;margin-left:8px">评分:' + esc(p.score) + '</span>';
      h += '</div>';
    });
  } else {
    h += '<div style="color:#94a3b8;font-size:12px;padding:8px">无信号叠加模式命中</div>';
  }
  h += '</div>';
  
  // 冲突消解
  h += '<div class="engine-card" style="border-top:3px solid #ec4899">';
  h += '<div class="engine-card-title"><span style="color:#ec4899">■</span> Phase 3 — 冲突消解 (' + (es.phase3_conflicts || []).length + ')</div>';
  if (es.phase3_conflicts && es.phase3_conflicts.length) {
    es.phase3_conflicts.forEach(function(c) {
      var lc = c.level === '极高风险' || c.level === '高风险' ? '#dc2626' : c.level === '中风险' ? '#f59e0b' : '#059669';
      h += '<div style="padding:8px 12px;margin:4px 0;border-left:3px solid ' + lc + ';font-size:12px">';
      h += '<span style="font-size:10px;color:#94a3b8">' + esc(c.rule_id) + '</span><br>';
      h += '<strong>' + esc(c.type.replace('交叉验证-冲突消解：','')) + '</strong>';
      h += '<span style="color:' + lc + ';margin-left:8px">' + esc(c.level) + '</span>';
      h += '</div>';
    });
  } else {
    h += '<div style="color:#94a3b8;font-size:12px;padding:8px">无冲突消解触发</div>';
  }
  h += '</div>';
  
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

  // ═══ Phase 2：信号→域映射 ═══
  var p2 = rules.phases['Phase2-信号→域映射'];
  if (p2 && !p2.error) {
    h += _renderSection('Phase2-信号→域映射', '8b5cf6', p2);
    var mappings = p2.mappings || {};
    Object.keys(mappings).forEach(function(signal) {
      var m = mappings[signal];
      var depthColor = m.depth === 'deep' ? '#dc2626' : m.depth === 'shallow' ? '#94a3b8' : '#f59e0b';
      h += '<div style="padding:8px 12px;margin:4px 0;border:1px solid #e2e8f0;border-radius:4px;font-size:12px">';
      h += '<strong>' + esc(signal) + '</strong> <span style="color:' + depthColor + ';font-size:11px">' + esc(m.depth) + '</span>';
      h += '<div style="color:#64748b">→ ' + esc((m.domains||[]).join(' / ')) + '</div>';
      if (m.reason) h += '<div style="color:#94a3b8;font-size:11px">' + esc(m.reason) + '</div>';
      h += '</div>';
    });
    h += '</div>';
  }
  
  // ═══ Phase 2：行业自适应知识库 ═══
  var p2i = rules.phases['Phase2-行业自适应知识库'];
  if (p2i && !p2i.error) {
    h += _renderSection('Phase2-行业自适应知识库', '10b981', p2i);
    (p2i.industries||[]).forEach(function(ind) {
      h += '<div style="padding:10px 14px;margin:6px 0;border:1px solid #e2e8f0;border-radius:6px">';
      h += '<div style="font-weight:700;font-size:13px;color:#1e293b">' + esc(ind.name);
      if (ind.subtypes && ind.subtypes.length) h += ' <span style="font-size:11px;color:#94a3b8">(' + esc(ind.subtypes.join('、')) + ')</span>';
      h += '</div>';
      h += '<div style="margin-top:4px;font-size:11px;color:#64748b">毛利率基准: ' + esc(ind.benchmarks['毛利率范围']) + ' | 购销比基准: ' + esc(ind.benchmarks['购销比范围']) + '</div>';
      if (ind.focus_domains && ind.focus_domains.length) {
        h += '<div style="margin-top:3px;font-size:11px;color:#8b5cf6">关注域: ' + esc(ind.focus_domains.join('、')) + '</div>';
      }
      if (ind.always_check && ind.always_check.length) {
        h += '<div style="margin-top:3px;font-size:11px;color:#059669">必查: ' + esc(ind.always_check.join('、')) + '</div>';
      }
      if (ind.risk_patterns && ind.risk_patterns.length) {
        h += '<div style="margin-top:4px">';
        ind.risk_patterns.forEach(function(rp) {
          h += '<div style="font-size:11px;color:#ea580c;margin:2px 0">⚠ ' + esc(rp.name) + ': ' + esc(rp.explanation).substring(0,80) + '</div>';
        });
        h += '</div>';
      }
      h += '</div>';
    });
    h += '</div>';
  }
  
  // ═══ Phase 3：信号叠加模式 ═══
  var p3p = rules.phases['Phase3-信号叠加模式'];
  if (p3p && !p3p.error) {
    h += _renderSection('Phase3-信号叠加模式', '06b6d4', p3p);
    (p3p.patterns||[]).forEach(function(p) {
      h += '<div style="padding:10px 14px;margin:6px 0;border:1px solid #e2e8f0;border-radius:6px">';
      h += '<div style="font-weight:700;font-size:13px;color:#1e293b">' + esc(p.id) + ' ' + esc(p.name) + '</div>';
      h += '<div style="margin-top:4px;font-size:12px;color:#64748b">';
      h += '必要条件: ' + esc((p.triggers.must_have||[]).join(', '));
      if (p.triggers.any_of) h += ' | 任一满足: ' + esc(p.triggers.any_of.join(', '));
      h += '</div>';
      h += '<div style="margin-top:4px;font-size:12px;color:#1e293b">结论: ' + esc(p.conclusion||'') + '</div>';
      h += '<div style="margin-top:4px;color:#ea580c;font-size:12px">风险: ' + esc(p.risk_override) + ' | 优先级: ' + esc(p.priority) + '</div>';
      if (p.actions) {
        h += '<div style="margin-top:4px;font-size:11px;color:#059669">';
        p.actions.slice(0,3).forEach(function(a, i) { h += (i+1) + '. ' + esc(a) + '<br>'; });
        h += '</div>';
      }
      h += '</div>';
      totalRules++;
    });
    h += '</div>';
  }
  
  // ═══ Phase 3：冲突消解规则 ═══
  var p3c = rules.phases['Phase3-冲突消解规则'];
  if (p3c && !p3c.error) {
    h += _renderSection('Phase3-冲突消解规则', 'ec4899', p3c);
    (p3c.rules||[]).forEach(function(r) {
      h += '<div style="padding:8px 12px;margin:4px 0;border:1px solid #e2e8f0;border-radius:4px;font-size:12px">';
      h += '<strong>' + esc(r.id) + '</strong> ' + esc(r.name);
      h += '<div style="color:#64748b;margin-top:2px">' + esc(r.signal_a) + ' + ' + esc(r.signal_b) + ' → ' + esc(r.resolution) + '</div>';
      h += '<div style="color:#ea580c;font-size:11px">风险操作: ' + esc(r.risk_action) + '</div>';
      h += '</div>';
      totalRules++;
    });
    h += '</div>';
  }
  
  // ═══ Phase 3：结论自洽性检测 ═══
  var p3z = rules.phases['Phase3-结论自洽性检测'];
  if (p3z) {
    h += _renderSection('Phase3-结论自洽性检测', 'f43f5e', p3z);
    (p3z.rules||[]).forEach(function(r) {
      var lc = r.level === 'red' ? '#dc2626' : r.level === 'yellow' ? '#f59e0b' : '#ea580c';
      var bg = r.level === 'red' ? '#fef2f2' : r.level === 'yellow' ? '#fffbeb' : '#fff7ed';
      h += '<div style="padding:10px 14px;margin:6px 0;border-left:3px solid ' + lc + ';background:' + bg + ';border-radius:4px;font-size:12px">';
      h += '<div><strong>' + esc(r.id) + '</strong> <span style="color:' + lc + ';font-weight:600">' + esc(r.name) + '</span> ';
      h += '<span style="background:' + lc + ';color:#fff;padding:1px 6px;border-radius:3px;font-size:10px">' + esc(r.priority) + '</span></div>';
      h += '<div style="color:#475569;margin-top:4px;line-height:1.5">' + esc(r.explanation) + '</div>';
      h += '<div style="color:#059669;margin-top:4px;font-size:11px">消解: ' + esc(r.resolution) + '</div>';
      h += '</div>';
      totalRules++;
    });
    h += '</div>';
  }
  
  // ═══ Phase 3：跨域分析推理链 ═══
  var p3xa = rules.phases['Phase3-跨域分析推理链'];
  if (p3xa && !p3xa.error) {
    h += _renderSection('Phase3-跨域分析推理链', '0ea5e9', p3xa);
    (p3xa.rules||[]).forEach(function(xa) {
      var lc = xa.level === 'red' ? '#dc2626' : xa.level === 'yellow' ? '#f59e0b' : '#ea580c';
      h += '<div style="padding:12px 14px;margin:6px 0;border-left:3px solid ' + lc + ';border-radius:4px;font-size:12px;background:#f8fafc">';
      h += '<div style="font-weight:700;font-size:13px;color:#1e293b">' + esc(xa.id) + ' ' + esc(xa.name) + '</div>';
      h += '<div style="color:#64748b;margin-top:4px;font-size:11px">触发: ' + esc(xa.trigger_signal||'') + '</div>';
      if (xa.reasoning_steps && xa.reasoning_steps.length) {
        h += '<div style="margin-top:6px">';
        xa.reasoning_steps.forEach(function(step) {
          h += '<div style="display:flex;align-items:flex-start;margin:3px 0;font-size:11px">';
          h += '<span style="background:#0ea5e9;color:#fff;min-width:18px;height:18px;border-radius:50%;text-align:center;line-height:18px;margin-right:6px;font-weight:700">' + esc(step.order) + '</span>';
          h += '<span><strong>' + esc(step.from) + '</strong> → ' + esc(step.finding) + ' <span style="color:#0ea5e9">→</span> <em>' + esc(step.to) + ': ' + esc(step.action) + '</em></span></div>';
        });
        h += '</div>';
      }
      if (xa.methodology) h += '<div style="color:#8b5cf6;font-size:11px;margin-top:4px">方法论: ' + esc(xa.methodology) + '</div>';
      h += '<div style="color:#475569;font-size:11px;margin-top:3px">' + esc(xa.description||'') + '</div>';
      h += '</div>';
      totalRules++;
    });
    h += '</div>';
  }
  
  // ═══ Phase 3：跨域线索链 ═══
  var p3xc = rules.phases['Phase3-跨域线索链'];
  if (p3xc && !p3xc.error) {
    h += _renderSection('Phase3-跨域线索链', 'd946ef', p3xc);
    (p3xc.rules||[]).forEach(function(xc) {
      var lc = xc.level === 'red' ? '#dc2626' : xc.level === 'yellow' ? '#f59e0b' : '#ea580c';
      h += '<div style="padding:10px 14px;margin:6px 0;border:1px solid #e2e8f0;border-radius:6px">';
      h += '<div style="font-weight:700;font-size:13px;color:#1e293b">' + esc(xc.id) + ' ' + esc(xc.name);
      h += ' <span style="font-size:11px;color:#94a3b8">[' + esc(xc.sub_topic||'') + ']</span></div>';
      h += '<div style="margin-top:4px;font-size:11px;color:#64748b">关键词: ' + esc((xc.trigger_keywords||[]).join(' | ')) + '</div>';
      h += '<div style="margin-top:4px;font-size:11px;color:#ea580c">最少证据维度: ' + esc(xc.min_evidence) + '</div>';
      if (xc.investigation_path && xc.investigation_path.length) {
        h += '<div style="margin-top:4px;font-size:11px;color:#475569">调查路径: ';
        xc.investigation_path.forEach(function(s) {
          h += '<span style="margin:0 4px;color:#8b5cf6">' + esc(s.step) + '.' + esc(s.domain) + '</span>→ ';
        });
        h += '</div>';
      }
      h += '</div>';
      totalRules++;
    });
    h += '</div>';
  }

  // ═══ Phase 3：跨域证据链 ═══
  var p3xe = rules.phases['Phase3-跨域证据链'];
  if (p3xe && !p3xe.error) {
    h += _renderSection('Phase3-跨域证据链', '059669', p3xe);
    (p3xe.rules||[]).forEach(function(xe) {
      var lc = xe.level === 'red' ? '#dc2626' : xe.level === 'yellow' ? '#f59e0b' : '#ea580c';
      h += '<div style="padding:10px 14px;margin:6px 0;border:1px solid #e2e8f0;border-radius:6px">';
      h += '<div style="font-weight:700;font-size:13px;color:#1e293b">' + esc(xe.id) + ' ' + esc(xe.name);
      h += ' <span style="font-size:11px;color:#94a3b8">[' + esc(xe.sub_topic||'') + ']</span></div>';
      h += '<div style="margin-top:4px;font-size:11px;color:#64748b">关键词: ' + esc((xe.trigger_keywords||[]).join(' | ')) + '</div>';
      h += '<div style="margin-top:4px;font-size:11px;color:#ea580c">最少证据维度: ' + esc(xe.min_evidence) + '</div>';
      if (xe.dimensions && xe.dimensions.length) {
        h += '<div style="margin-top:4px;display:flex;gap:6px;flex-wrap:wrap">';
        xe.dimensions.forEach(function(d) {
          h += '<div style="padding:4px 8px;background:#ecfdf5;border-radius:4px;font-size:11px"><strong>' + esc(d.code) + '</strong> ' + esc(d.source) + ': ' + esc(d.desc) + '</div>';
        });
        h += '</div>';
      }
      h += '</div>';
      totalRules++;
    });
    h += '</div>';
  }

  // ═══ Phase 4：因果叙事链 ═══
  var p4n = rules.phases['Phase4-因果叙事链'];
  if (p4n) {
    h += _renderSection('Phase4-因果叙事链', 'ef4444', p4n);
    (p4n.rules||[]).forEach(function(ch) {
      var lc = ch.level === 'red' ? '#dc2626' : ch.level === 'yellow' ? '#f59e0b' : '#ea580c';
      var bg = ch.level === 'red' ? '#fef2f2' : ch.level === 'yellow' ? '#fffbeb' : '#fff7ed';
      h += '<div style="padding:12px 14px;margin:6px 0;border-left:3px solid ' + lc + ';background:' + bg + ';border-radius:4px;font-size:12px">';
      h += '<div style="font-weight:700;font-size:13px;color:#1e293b">' + esc(ch.id) + ' ' + esc(ch.name) + '</div>';
      h += '<div style="margin-top:4px;padding:6px 10px;background:#fff;border-radius:4px;font-size:12px;font-weight:600;color:#dc2626">' + esc(ch.narrative) + '</div>';
      h += '<div style="color:#475569;margin-top:6px;line-height:1.5">' + esc(ch.explanation) + '</div>';
      h += '<div style="margin-top:4px;font-size:11px">';
      h += '<span style="color:#8b5cf6">必要信号: ' + esc((ch.required_signals||[]).join('、')) + '</span>';
      if (ch.optional_signals && ch.optional_signals.length) h += ' | <span style="color:#94a3b8">辅助: ' + esc(ch.optional_signals.join('、')) + '</span>';
      h += '</div>';
      h += '<div style="margin-top:4px;font-size:11px;color:#64748b">' + esc(ch.confidence_rule) + '</div>';
      h += '<div style="margin-top:4px;font-size:11px;color:#059669">证据链: ' + esc(ch.evidence_chain) + '</div>';
      h += '<div style="margin-top:4px"><span style="background:' + lc + ';color:#fff;padding:1px 6px;border-radius:3px;font-size:10px">' + esc(ch.priority) + '</span> <span style="color:' + lc + ';font-weight:600;font-size:11px">' + esc(ch.level) + '</span></div>';
      h += '</div>';
      totalRules++;
    });
    h += '</div>';
  }

  // ═══ Phase 4：事前预警升级路径 ═══
  var p4w = rules.phases['Phase4-事前预警升级路径'];
  if (p4w) {
    h += _renderSection('Phase4-事前预警升级路径', 'f97316', p4w);
    (p4w.rules||[]).forEach(function(ew) {
      var lc = ew.level === 'red' ? '#dc2626' : ew.level === 'yellow' ? '#f59e0b' : '#ea580c';
      var bg = ew.level === 'red' ? '#fef2f2' : ew.level === 'yellow' ? '#fffbeb' : '#fff7ed';
      h += '<div style="padding:12px 14px;margin:6px 0;border-left:3px solid ' + lc + ';background:' + bg + ';border-radius:4px;font-size:12px">';
      h += '<div style="font-weight:700;font-size:13px;color:#1e293b">' + esc(ew.id) + ' ' + esc(ew.name) + '</div>';
      h += '<div style="margin-top:6px;padding:8px 10px;background:#fff;border-radius:4px;font-size:12px;line-height:1.6;color:#475569"><strong style="color:#dc2626">演变推演：</strong>' + esc(ew.forward_projection) + '</div>';
      h += '<div style="margin-top:4px;font-size:11px;color:#059669"><strong>建议：</strong><span style="color:#475569">' + esc(ew.checklist) + '</span></div>';
      h += '<div style="margin-top:4px;display:flex;gap:8px;align-items:center">';
      h += '<span style="background:' + lc + ';color:#fff;padding:1px 6px;border-radius:3px;font-size:10px">' + esc(ew.risk_level) + '</span>';
      h += '<span style="font-size:11px;color:#64748b">触发时间窗: ' + esc(ew.timeframe) + '</span>';
      h += '<span style="font-size:10px;color:#94a3b8">匹配模式: ' + esc((ew.patterns||[]).slice(0,3).join(' / ')) + '</span>';
      h += '</div>';
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
  var cid = window._currentCompanyId || 1;
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
  container.innerHTML = '<div style="text-align:center;padding:60px;color:#94a3b8"><span class="spinner"></span> 正在从引擎读取能力维度...</div>';
  
  fetch('/api/audit/capabilities')
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (!d.ok || !d.dimensions) { container.innerHTML = '<div style="padding:40px;color:#dc2626">引擎能力维度读取失败</div>'; return; }
      
      var dims = d.dimensions.map(function(c) {
        return {n: c.name, s: c.stars, t: c.core, f: c.code};
      });
      var stars4 = d.summary.four_star_count;
      var stars3 = d.summary.three_star_count;
      var totalDims = d.summary.total_dimensions;
      var qs = d.quality_system || {};
      var codeTotal = '27,616行';
      
      renderDimensionsTable(container, dims, stars4, stars3, totalDims, qs, codeTotal);
    });
}

function renderDimensionsTable(container, dims, stars4, stars3, totalDims, qs, codeTotal) {
  var h = '';
  h += '<style>.dim-layout{display:flex;gap:24px;max-width:1200px;margin:0 auto;padding:20px}.dim-toc{width:200px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:12px;line-height:2.2}.dim-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.dim-toc a{display:block;color:#475569;text-decoration:none;padding:2px 8px;border-radius:4px;cursor:pointer}.dim-main{flex:1;min-width:0}</style>';
  h += '<div class="dim-layout">';

  // TOC
  h += '<nav class="dim-toc"><div class="toc-title">📖 导航</div>';
  h += '<a href="#dim-overview">总览</a>';
  h += '<a href="#dim-table">维度明细</a>';
  h += '<a href="#dim-pipeline">管道信息</a>';
  h += '</nav>';

  h += '<div class="dim-main">';
  h += '<h2 style="font-size:22px;font-weight:800;color:#0f172a;margin:0 0 4px">📐 引擎能力维度</h2>';
  h += '<p style="font-size:13px;color:#94a3b8;margin:0 0 24px">推理引擎'+totalDims+'维能力矩阵 · 星级评估 · 质量保障体系覆盖</p>';

  // Stats
  h += '<div id="dim-overview" style="display:flex;gap:12px;margin-bottom:24px">';
  h += '<div style="flex:1;text-align:center;padding:16px;background:#f8fafc;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#0f172a">'+totalDims+'</div><div style="font-size:12px;color:#64748b">总维度</div></div>';
  h += '<div style="flex:1;text-align:center;padding:16px;background:#fffbeb;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#f59e0b">'+stars4+'</div><div style="font-size:12px;color:#64748b">★★★★ 四星</div></div>';
  h += '<div style="flex:1;text-align:center;padding:16px;background:#eff6ff;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#6366f1">'+stars3+'</div><div style="font-size:12px;color:#64748b">★★★ 三星</div></div>';
  h += '<div style="flex:1;text-align:center;padding:16px;background:#f0fdf4;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#059669">'+codeTotal+'</div><div style="font-size:12px;color:#64748b">代码总量</div></div>';
  h += '</div>';

  // Table
  h += '<div id="dim-table">';
  h += '<table style="width:100%;border-collapse:collapse;font-size:13px;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08)">';
  h += '<thead><tr style="background:#1e293b;color:#fff">';
  h += '<th style="padding:10px 14px;text-align:left">#</th><th style="padding:10px 14px;text-align:left">维度</th><th style="padding:10px 14px;text-align:center">等级</th><th style="padding:10px 14px;text-align:left">核心能力</th><th style="padding:10px 14px;text-align:left">代码位置</th>';
  h += '</tr></thead><tbody>';

  dims.forEach(function(d,i){
    var stars = d.s===4 ? '★★★★' : '★★★';
    var color = d.s===4 ? '#f59e0b' : '#6366f1';
    var bg = i%2===0 ? '#f8fafc' : '#fff';
    h += '<tr style="background:'+bg+'">';
    h += '<td style="padding:10px 14px;color:#94a3b8">'+(i+1)+'</td>';
    h += '<td style="padding:10px 14px;font-weight:700">'+d.n+'</td>';
    h += '<td style="padding:10px 14px;text-align:center;color:'+color+';font-weight:700;font-size:14px">'+stars+'</td>';
    h += '<td style="padding:10px 14px;color:#475569;font-size:12px">'+d.t+'</td>';
    h += '<td style="padding:10px 14px;font-family:monospace;font-size:11px;color:#64748b;max-width:260px;word-break:break-all">'+d.f+'</td>';
    h += '</tr>';
  });

  h += '</tbody></table></div>';

  // Footer
  h += '<div id="dim-pipeline" style="margin-top:20px;padding:16px 20px;background:#f1f5f9;border-radius:8px;font-size:12px;color:#475569;line-height:1.8">';
  h += '<b>代码分布</b>：main.py (18个函数+6个API) | engine/ (信号检测+记忆+自学习) | tax-doc-analysis.js (前端渲染+图可视化+响应式)<br>';
  h += '<b>管道流程</b>：文件解析 → Phase1初查 → Phase2深挖 → Phase3交叉验证 → Phase4综合定性 → 12维增强 → HTML报告<br>';
  h += '<b>数据流</b>：Excel上传 → 归一化 → AuditContext贯穿 → all_findings聚集 → 各维增强 → report JSON → 前端渲染';
  h += '</div>';

  h += '</div></div>';
  container.innerHTML = h;
}

// ═══════════════════════════════════════════════════
// #2: 质量保障标签页（audit.py 7+1项检查结果）
// ═══════════════════════════════════════════════════
function renderQualityTab() {
  var area = document.getElementById('eng-tab-content');
  if (!area) return;
  area.innerHTML = '<div style="text-align:center;padding:60px;color:#94a3b8"><span class="spinner"></span> 正在运行质量检查...</div>';
  
  fetch('/api/audit/status?company_id=' + (window._currentCompanyId || 1))
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (!d.ok) { area.innerHTML = '<div style="padding:40px;text-align:center;color:#dc2626">质量检查失败: ' + esc(d.error || '') + '</div>'; return; }
      
      var h = '';
      var sc = d.score;
      var scoreColor = sc === 100 ? '#059669' : sc >= 80 ? '#3b82f6' : sc >= 60 ? '#f59e0b' : '#dc2626';
      var scoreBg = sc === 100 ? '#ecfdf5' : sc >= 80 ? '#eff6ff' : sc >= 60 ? '#fffbeb' : '#fef2f2';
      h += '<div style="background:' + scoreBg + ';border:2px solid ' + scoreColor + ';padding:24px 28px;border-radius:12px;margin-bottom:20px;text-align:center">';
      h += '<div style="font-size:48px;font-weight:700;color:' + scoreColor + ';line-height:1.2">' + sc + '<span style="font-size:20px">/100</span></div>';
      h += '<div style="font-size:18px;font-weight:600;color:' + scoreColor + ';margin-top:8px">系统健康度: ' + esc(d.level) + '</div>';
      h += '<div style="font-size:13px;color:#64748b;margin-top:4px">' + d.passed + '/' + d.total + ' 项通过</div>';
      h += '</div>';
      
      h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">';
      (d.items || []).forEach(function(item) {
        var icon = item.passed ? 'V' : 'X';
        var cardBg = item.passed ? '#ecfdf5' : '#fef2f2';
        var cardBorder = item.passed ? '#059669' : '#dc2626';
        h += '<div style="background:' + cardBg + ';border:1px solid ' + cardBorder + ';padding:14px 16px;border-radius:8px">';
        h += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">';
        h += '<span style="font-weight:600;font-size:14px;color:' + (item.passed ? '#065f46' : '#991b1b') + '">' + esc(item.name) + '</span>';
        h += '<span style="font-size:20px;color:' + (item.passed ? '#059669' : '#dc2626') + '">' + icon + '</span>';
        h += '</div>';
        h += '<div style="font-size:12px;color:#64748b">' + esc(item.description) + '</div>';
        if (!item.passed) {
          h += '<div style="font-size:12px;color:#dc2626;font-weight:600;margin-top:4px">' + item.error_count + '个问题</div>';
        }
        h += '</div>';
      });
      h += '</div>';
      
      if (d.audit_errors && d.audit_errors.length > 0) {
        h += '<div style="margin-top:20px"><div style="font-weight:600;font-size:14px;margin-bottom:10px;color:#991b1b">详细错误</div>';
        d.audit_errors.forEach(function(err) {
          h += '<div style="background:#fef2f2;border-left:3px solid #dc2626;padding:8px 12px;margin:4px 0;font-size:12px;color:#7f1d1d;border-radius:4px">' + esc(err) + '</div>';
        });
        h += '</div>';
      }
      
      area.innerHTML = h;
    })
    .catch(function() {
      area.innerHTML = '<div style="padding:40px;text-align:center;color:#dc2626">质量检查服务不可用</div>';
    });
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
    {id:'NEG-AUG-001',scene:'联合增强（触发新发现）',action:'增强',from:'经营费用缺失+运输缺失+场所异常',to:'综合生成"空壳企业预警"',desc:'三域交叉指向企业可能无实际经营场所和物流活动。跨域协商引擎自动合成极高风险发现，引用《刑法》第205条（虚开发票罪）。'},
    {id:'NEG-AUG-002',scene:'联合增强（触发新发现）',action:'增强',from:'个人收款+收款待分析+个人交易',to:'综合生成"隐匿收入预警"',desc:'三域独立检测均指向个人账户收款。协商引擎自动合成极高风险发现，引用《征管法》第63条（偷税处罚）。'},
    {id:'NEG-AUG-003',scene:'联合增强（触发新发现）',action:'增强',from:'供应商异常+关联重叠+集中度过高',to:'综合生成"对倒开票预警"',desc:'三域独立检测供应商结构异常，协商引擎自动合成高风险发现，引用《发票管理办法》第22条和《刑法》第205条。'},
  ];

  var h = '';
  h += '<h3 style="font-size:18px;font-weight:700;color:#1a1a2e;margin:0 0 4px">🤝 跨域协商规则</h3>';
  h += '<p style="font-size:13px;color:#94a3b8;margin:0 0 20px">引擎在全部域分析完成后自动运行。15条协商规则覆盖四类场景：行业闸门消解 / 资料驱动的跨域标记 / 证据矛盾消解 / 联合增强。</p>';

  var scenes = {
    '行业闸门消解': {desc:'服务行业自动跳过不适用域（进销存/存货/BOM/毛利率对标），消除假阳性',color:'#059669',bg:'#ecfdf5'},
    '资料驱动的跨域标记': {desc:'缺少某类资料→相关域结论标注"资料受限"，避免无数据基础的高风险判定',color:'#3b82f6',bg:'#eff6ff'},
    '证据矛盾消解': {desc:'域A的正面证据推翻域B的负面结论（如检测到经营费用→推翻"无经营场所"）',color:'#f59e0b',bg:'#fffbeb'},
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

  h += '<div style="padding:16px 20px;background:#f8fafc;border-radius:8px;font-size:12px;color:#64748b;line-height:2">';
  h += '<b>执行时序</b>：所有域分析完成→跨域协商引擎运行→链驱动分析引擎→报告生成<br>';
  h += '<b>代码位置</b>：<code>engine/cross_domain_negotiation.py</code>（15条NEGOTIATION_RULES）<br>';
  h += '<b>报告展示</b>：消解→红色⛔横幅 | 降级→黄色🔄横幅 | 标记→蓝色ℹ️标签 | 增强→红框新发现<br>';
  h += '<b>规则扩展</b>：编辑 <code>NEGOTIATION_RULES</code> 列表即可追加新协商规则。</div>';

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
      
      // ── 1. 调度中枢 ──
      h += '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px 20px;margin-bottom:16px">';
      h += '<h3 style="color:#1e293b;border-bottom:2px solid #2563eb;padding-bottom:8px">调度中枢</h3>';
      
      var orch = d.orchestrator || {};
      h += '<div style="display:flex;gap:12px;margin:12px 0;flex-wrap:wrap">';
      h += '<div style="flex:1;min-width:160px;background:#f0f9ff;padding:12px;border-radius:6px;text-align:center"><div style="font-size:28px;font-weight:700;color:#0369a1">' + orch.total_modules + '</div><div style="font-size:12px;color:#64748b">总模块</div></div>';
      h += '<div style="flex:1;min-width:160px;background:#f0fdf4;padding:12px;border-radius:6px;text-align:center"><div style="font-size:28px;font-weight:700;color:#059669">' + (orch.domain_count || 7) + '</div><div style="font-size:12px;color:#64748b">领域</div></div>';
      h += '<div style="flex:1;min-width:160px;background:#fef3c7;padding:12px;border-radius:6px;text-align:center"><div style="font-size:28px;font-weight:700;color:#d97706">' + (orch.pipeline_depth || 16) + '</div><div style="font-size:12px;color:#64748b">管线深度</div></div>';
      h += '</div>';
      
      if (orch.domains) {
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
          h += '<span style="display:inline-block;margin:2px;padding:2px 8px;background:#f1f5f9;border-radius:10px">' + esc(growth.top_industries[j][0]) + '(' + growth.top_industries[j][1].runs + '次)</span>';
        }
        h += '</div>';
      }
      h += '</div>';
      
      // ── 3. 纠正规则库 ──
      h += '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px 20px;margin-bottom:16px">';
      h += '<h3 style="color:#1e293b;border-bottom:2px solid #059669;padding-bottom:8px">纠正规则库（老邓教的）</h3>';
      
      var corr = d.corrections || {};
      h += '<div style="display:flex;gap:12px;margin:12px 0;flex-wrap:wrap">';
      h += '<div style="flex:1;min-width:100px;background:#f0fdf4;padding:12px;border-radius:6px;text-align:center"><div style="font-size:22px;font-weight:700;color:#059669">' + (corr.total_rules || 0) + '</div><div style="font-size:12px;color:#64748b">规则总数</div></div>';
      h += '<div style="flex:1;min-width:100px;background:#dcfce7;padding:12px;border-radius:6px;text-align:center"><div style="font-size:22px;font-weight:700;color:#166534">' + (corr.auto_rules || 0) + '</div><div style="font-size:12px;color:#64748b">已自动生效</div></div>';
      h += '</div>';
      
      if (corr.rules && corr.rules.length > 0) {
        h += '<table class="tbl2"><tr><th>发现类型</th><th>行业</th><th>模式</th><th>纠正次数</th><th>置信度</th><th>状态</th></tr>';
        for (var k = 0; k < corr.rules.length; k++) {
          var r = corr.rules[k];
          var autoLabel = r.auto_apply ? '<span style="color:#059669;font-weight:600">已生效</span>' : '<span style="color:#d97706">学习中</span>';
          h += '<tr>';
          h += '<td style="font-weight:600">' + esc(r.finding_type) + '</td>';
          h += '<td>' + esc(r.industry) + '</td>';
          h += '<td>' + esc(r.biz_model) + '</td>';
          h += '<td style="text-align:center">' + r.correction_count + '</td>';
          h += '<td style="text-align:center">' + (r.confidence*100).toFixed(0) + '%</td>';
          h += '<td>' + autoLabel + '</td>';
          h += '</tr>';
        }
        h += '</table>';
      } else {
        h += '<div style="text-align:center;padding:20px;color:#94a3b8">尚无纠正规则 — 老邓点在报告中发现上点击驳回后，系统将自动学习</div>';
      }
      h += '</div>';
      
      // ── 4. 税收优惠政策核实 ──
      var pv = d.policy_verification;
      if (pv) {
        h += '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px 20px;margin-bottom:16px">';
        h += '<h3 style="color:#1e293b;border-bottom:2px solid #8b5cf6;padding-bottom:8px">税收优惠政策核实</h3>';
        h += '<div style="display:flex;gap:12px;margin:12px 0;flex-wrap:wrap">';
        h += '<div style="flex:1;min-width:100px;background:#f5f3ff;padding:12px;border-radius:6px;text-align:center"><div style="font-size:22px;font-weight:700;color:#7c3aed">' + pv.total_policies + '</div><div style="font-size:12px;color:#64748b">政策总数</div></div>';
        h += '<div style="flex:1;min-width:100px;background:#f0fdf4;padding:12px;border-radius:6px;text-align:center"><div style="font-size:22px;font-weight:700;color:#059669">' + pv.valid_count + '</div><div style="font-size:12px;color:#64748b">有效政策</div></div>';
        if (pv.expired_count > 0) {
          h += '<div style="flex:1;min-width:100px;background:#fef2f2;padding:12px;border-radius:6px;text-align:center"><div style="font-size:22px;font-weight:700;color:#dc2626">' + pv.expired_count + '</div><div style="font-size:12px;color:#64748b">已到期</div></div>';
        }
        h += '</div>';
        var policies = pv.policies || [];
        if (policies.length > 0) {
          h += '<table class="tbl2"><tr><th>政策</th><th>文号</th><th>到期日</th><th>状态</th><th>系统核实</th></tr>';
          for (var pi = 0; pi < policies.length; pi++) {
            var pol = policies[pi];
            var icon = pol.valid ? '<span style="color:#059669">✅ 有效</span>' : '<span style="color:#dc2626">⚠ 已到期</span>';
            var verify = pol.auto_verify_source || pol.status || '';
            h += '<tr>';
            h += '<td style="font-weight:600">' + esc(pol.name) + '</td>';
            h += '<td style="font-size:12px;color:#64748b">' + esc(pol.law) + '</td>';
            h += '<td>' + esc(pol.expiry) + '</td>';
            h += '<td>' + icon + '</td>';
            h += '<td style="font-size:12px;max-width:200px">' + esc(verify) + '</td>';
            h += '</tr>';
          }
          h += '</table>';
        }
        h += '</div>';
      }
      
      // ── 5. 学习方法论 ──
      h += '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px 20px;font-size:12px;color:#475569">';
      h += '<b>智能大脑工作原理：</b><br>';
      h += '<b>调度中枢</b>：根据数据画像自动决定激活哪些模块、跳过哪些模块。<br>';
      h += '<b>渐进学习</b>：同类企业分析3次后建立信任模型，长期零产出模块自动降权。<br>';
      h += '<b>纠正规则</b>：老邓在报告中点击驳回→系统记录模式→累计1次→升级为自动规则→下次同类场景自动修正。<br>';
      h += '<b>合规门禁</b>：12条稽查铁律作为事前检查，不通过的报告标记违规。<br>';
      h += '<b>政策核实</b>：9类税收优惠政策自动联网核实有效期，已到期政策自动搜索延续公告。';
      h += '</div>';
      
      h += '</div>';
      area.innerHTML = h;
    });
}

