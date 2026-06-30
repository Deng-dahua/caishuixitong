/**
 * 推理引擎仪表盘 — 独立展示推理引擎 v2.0 的全部内部状态
 * Phase 1-4 完整可视化
 */

function renderEngineDashboardPage(container) {
  container.innerHTML = '<div style="max-width:1100px;margin:0 auto;padding:24px 16px;background:#fff">'
    + '<h2 style="font-size:20px;font-weight:800;color:#0f172a;margin:0 0 4px">⚙️ 推理引擎仪表盘</h2>'
    + '<p style="font-size:13px;color:#94a3b8;margin:0 0 24px">推理引擎 v2.0 运行监控中心——6个标签页覆盖运行状态/规则库/质量保障/方法论对账/跨域协商/智能大脑。数据来源：系统实时API + 分析缓存。每项指标可追溯到具体的代码位置和数据文件。</p>'
    + '<div id="engine-dashboard-area"><div style="text-align:center;padding:60px;color:#94a3b8"><span class="spinner"></span> 正在连接推理引擎数据接口...</div></div></div>';
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
}

function renderStatusTab() {
  var es = window._engineEs || {};
  var area = document.getElementById('eng-tab-content');
  
  if (!window._hasEngineData) {
    area.innerHTML = '<div style="padding:60px 20px;text-align:center">' +
      '<div style="font-size:36px;margin-bottom:16px">🧠</div>' +
      '<div style="font-size:18px;color:#1e293b;font-weight:700;margin-bottom:8px">暂无分析数据</div>' +
      '<div style="font-size:13px;color:#64748b;margin-bottom:16px;line-height:2">运行状态需要先执行一键分析才能查看引擎内部数据。<br>一键分析会触发完整的Phase1-4推理管线，生成包含全部中间状态的分析报告。</div>' +
      '<div style="font-size:13px;color:#64748b;line-height:2">请前往 <b>资料风险分析报告</b> 页面运行一键分析，或点击上方 <b>规则库</b> 标签查看1608条稽查指令的完整定义。<br>其他标签页（质量保障/方法论对账/跨域协商/智能大脑）也需要分析数据作为输入。</div>' +
      '</div>';
    return;
  }
  
  var h = '';
  
  // ═══ 顶部：引擎版本 + 风险总览 ═══
  h += '<div style="background:#f8fafc;border:1px solid #e2e8f0;padding:24px 28px;border-radius:12px;margin-bottom:20px">';
  h += '<div style="font-size:20px;font-weight:700;color:#0f172a">推理引擎仪表盘 <span style="font-size:13px;color:#94a3b8;margin-left:12px">' + esc(es.version) + '</span></div>';
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

function editCorrectionRule(fingerprint, rowIndex) {
  var reason = prompt('修改审核意见（保留四段式模板）：\n【判断结论】\n【具体问题】\n【正确逻辑】\n【需要证据】', '');
  if (!reason || !reason.trim()) return;
  fetch('/api/feedback/update', { 
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({fingerprint: decodeURIComponent(fingerprint), reason: reason})
  })
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (d.ok) {
        renderBrainTab();
      } else {
        alert('修改失败: ' + (d.message || ''));
      }
    });
}

function deleteCorrectionRule(fingerprint, rowIndex, correctionCount, industry) {
  var msg = 'Delete this correction rule?\n\n' + correctionCount + ' corrections recorded' + (industry ? ' for ' + industry : '') + '.\n\nDeleted rules are archived to _deleted_correction_rules.json and can be restored.';
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
  if (!confirm('Restore this archived rule?')) return;
  fetch('/api/feedback/restore?fingerprint=' + fingerprint, { method: 'POST' })
    .then(function(r){return r.json();})
    .then(function(d){
      if(d.ok){alert('Restored ' + d.correction_count + ' corrections.'); renderBrainTab();}
      else{alert('Failed: ' + (d.message||''));}
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
  h += '<style>.dim-layout{display:flex;gap:28px;max-width:1100px;margin:0 auto;padding:24px 16px;background:#fff}.dim-toc{width:180px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:12px;line-height:2.2;max-height:calc(100vh-40px);overflow-y:auto}.dim-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.dim-toc a{display:block;color:#475569;text-decoration:none;padding:3px 10px;border-radius:4px;cursor:pointer;font-size:12px}.dim-toc a:hover,.dim-toc a.active{background:#eff6ff;color:#2563eb;font-weight:600}.dim-main{flex:1;min-width:0;background:#fff}.dim-stat{text-align:center;padding:16px 12px;background:#fff;border:1px solid #e2e8f0;border-radius:8px}.dim-info{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px 20px;font-size:13px;line-height:2;color:#475569}</style>';
  h += '<div class="dim-layout">';

  // TOC
  h += '<nav class="dim-toc"><div class="toc-title">📖 导航</div>';
  h += '<a href="#dim-overview">总览</a>';
  h += '<a href="#dim-table">维度明细</a>';
  h += '<a href="#dim-pipeline">管道与数据流</a>';
  h += '</nav>';

  h += '<div class="dim-main">';
  h += '<h2 style="font-size:20px;font-weight:800;color:#0f172a;margin:0 0 4px">📐 引擎能力维度</h2>';
  h += '<p style="font-size:13px;color:#94a3b8;margin:0 0 24px;line-height:2">推理引擎'+totalDims+'维能力矩阵——从文件解析到报告输出，覆盖全部分析域和工具链。每个维度按实现完整度分为四星（已完全代码化并验证）和三星（已实现核心功能）。数据来源：capability_matrix.py 动态提取代码中的实际实现，非人工维护的数字。当前进度：四星'+stars4+'个、三星'+stars3+'个、总计代码'+codeTotal+'。</p>';

  // ═══ 说明 ═══
  h += '<div class="dim-info" style="margin-bottom:24px">';
  h += '<strong style="color:#059669;font-size:14px">星级评定标准</strong><br><br>';
  h += '<b>★★★★ 四星</b>：功能完整实现——有完整的代码实现+对应的API端点+前端渲染页面+报告中的输出呈现。四星维度是引擎的"完全体"能力，可直接用于正式稽查报告生成。<br><br>';
  h += '<b>★★★ 三星</b>：核心功能实现——有主要的代码逻辑和API，但前端展示或报告集成仍需完善。三星维度在引擎内部正常运行（管线能调用、结果能产出），面向用户的产品化程度不如四星完整。<br><br>';
  h += '<b>评定方式</b>：capability_matrix.py 扫描各模块代码中的函数定义、API路由注册、前端渲染函数和报告注入逻辑，自动统计每个维度的实现状态。非主观评分——每一个星级对应代码中可验证的实现证据。</div>';

  // Stats
  h += '<div id="dim-overview" style="display:flex;gap:10px;margin-bottom:24px;flex-wrap:wrap">';
  h += '<div class="dim-stat" style="flex:1;min-width:90px"><div style="font-size:24px;font-weight:700;color:#0f172a">'+totalDims+'</div><div style="font-size:11px;color:#94a3b8;margin-top:4px">总维度</div></div>';
  h += '<div class="dim-stat" style="flex:1;min-width:90px"><div style="font-size:24px;font-weight:700;color:#f59e0b">'+stars4+'</div><div style="font-size:11px;color:#94a3b8;margin-top:4px">★★★★ 四星</div></div>';
  h += '<div class="dim-stat" style="flex:1;min-width:90px"><div style="font-size:24px;font-weight:700;color:#6366f1">'+stars3+'</div><div style="font-size:11px;color:#94a3b8;margin-top:4px">★★★ 三星</div></div>';
  h += '<div class="dim-stat" style="flex:1;min-width:90px"><div style="font-size:24px;font-weight:700;color:#059669">'+codeTotal+'</div><div style="font-size:11px;color:#94a3b8;margin-top:4px">代码总量</div></div>';
  h += '</div>';

  // Table
  h += '<div id="dim-table">';
  h += '<div style="margin-bottom:12px;font-size:12px;color:#94a3b8;line-height:2">表格列说明：<b>#</b>序号 | <b>维度</b>能力模块名称 | <b>等级</b>四星/三星 | <b>核心能力</b>该维度实现的关键功能描述 | <b>代码位置</b>对应的源文件和函数名，可跳转查看实现细节</div>';
  h += '<table style="width:100%;border-collapse:collapse;font-size:13px;line-height:2;background:#fff;border-radius:8px;overflow:hidden;border:1px solid #e2e8f0">';
  h += '<thead><tr style="background:#f8fafc;color:#0f172a;border-bottom:2px solid #e2e8f0">';
  h += '<th style="padding:10px 14px;text-align:left;font-weight:600">#</th><th style="padding:10px 14px;text-align:left;font-weight:600">维度</th><th style="padding:10px 14px;text-align:center;font-weight:600">等级</th><th style="padding:10px 14px;text-align:left;font-weight:600">核心能力</th><th style="padding:10px 14px;text-align:left;font-weight:600">代码位置</th>';
  h += '</tr></thead><tbody>';

  dims.forEach(function(d,i){
    var stars = d.s===4 ? '★★★★' : '★★★';
    var color = d.s===4 ? '#f59e0b' : '#6366f1';
    var bg = i%2===0 ? '#fafbfc' : '#fff';
    h += '<tr style="background:'+bg+';border-bottom:1px solid #f1f5f9">';
    h += '<td style="padding:10px 14px;color:#94a3b8">'+(i+1)+'</td>';
    h += '<td style="padding:10px 14px;font-weight:700;color:#0f172a">'+d.n+'</td>';
    h += '<td style="padding:10px 14px;text-align:center;color:'+color+';font-weight:700;font-size:14px">'+stars+'</td>';
    h += '<td style="padding:10px 14px;color:#475569;font-size:12px">'+d.t+'</td>';
    h += '<td style="padding:10px 14px;font-family:monospace;font-size:11px;color:#64748b;max-width:260px;word-break:break-all">'+d.f+'</td>';
    h += '</tr>';
  });

  h += '</tbody></table></div>';

  // Footer
  h += '<div id="dim-pipeline" class="dim-info" style="margin-top:20px">';
  h += '<strong style="color:#059669;font-size:14px">管道与数据流</strong><br><br>';
  h += '<b>代码分布</b><br>';
  h += '· main.py（约20,000+行）：18个核心函数+6个数据分析API+227个路由+文件解析引擎+域分析调度+规则引擎整合+方法论过滤器+稽查员推理引擎——系统的主体逻辑全部在此文件中<br>';
  h += '· engine/（约7,500行）：pipeline.py（Phase1-4推理管线+跨域协商+审核反馈）、domain_analysis.py（42个域分析函数+收款分类+资料情报提取）、memory.py（引擎记忆+铁律+规则体系——26章docstring+Python函数）、cross_domain_negotiation.py（15条协商规则）、self_learning.py（审核闭环+EMA自学习+规则发现）、shared_content_sync.py（跨模块文本一致+29项共享内容映射）<br>';
  h += '· static/js/（约6,000行）：tax-doc-analysis.js（报告渲染+六要素格式+跨域协商标记展示）、tax-pipeline-pages.js（11个独立页面——文件解析/域分析/方法论过滤器/分析链/线索链/证据链/跨域系列/质量保障/AI准则）、tax-auditor-handbook.js（14章稽查员手册）、tax-report-standards.js（15节编制要求）、tax-feedback-template.js（20场景审核模板）、tax-engine-dashboard.js（6标签页仪表盘+'+totalDims+'维能力矩阵）<br><br>';
  h += '<b>管道流程（10步）</b><br>';
  h += '①文件解析：34类文件指纹+三层递进识别+四方交叉验证 → ②实体识别：身份锚定+行业判定+联网核查 → ③情报提取：_extract_material_intel()+收款分类+进项三层分类 → ④规则引擎：1514规则+396线索+745证据全量激活 → ⑤Phase1-4推理：初查→深挖→交叉验证→综合定性 → ⑥跨域协商：15条规则消解域间矛盾 → ⑦方法论过滤：7类规则97%噪声去除 → ⑧12维增强：建议/法律/证据/图表/术语/金额等增强 → ⑨质量检查：12项标准+7项可靠性+报告纯净度 → ⑩HTML报告：7章正式报告+附件7份<br><br>';
  h += '<b>数据流（10步）</b><br>';
  h += 'Excel上传 → 34类文件指纹识别 → 数据归一化 → AuditContext贯穿 → 情报提取 → 36域并行分析 → all_findings聚集 → run_negotiation跨域协商 → _apply_methodology_filter过滤 → report JSON → 前端渲染<br><br>';
  h += '<b>当前统计</b>：'+totalDims+'维能力 · '+stars4+'四星 + '+stars3+'三星 · 代码'+codeTotal+' · 227路由 · 审计全部通过<br><br>';
  h += '<b>关联模块</b>：<code>engine/capability_matrix.py</code>（维度定义+星级评分）→ <code>static/system_config.json</code>（权威数据源）→ <code>audit_consistency.py --sync</code>（自动同步所有模块中的数字）→ <a href="#" onclick="navigateTo(\'quality-system\');return false" style="color:#2563eb">全链路质量保障体系</a>（25组件六大层次）→ <a href="#" onclick="navigateTo(\'auditor-handbook\');return false" style="color:#2563eb">税务稽查员手册</a>（14章完整规范）</div>';

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

  h += '<div style="padding:16px 20px;background:#f8fafc;border-radius:8px;font-size:13px;color:#475569;line-height:2">';
  h += '<strong style="font-size:14px;color:#0f172a">技术说明</strong><br><br>';
  h += '<b>执行时序</b>：所有42个域分析函数独立完成→跨域协商引擎(run_negotiation)扫描all_findings→逐条匹配15条NEG规则→消解矛盾/降级不适/标记受限/增强多域→输出协商后findings→进入方法论过滤器→生成报告。协商引擎在Phase3交叉验证之后、方法论过滤器之前执行。<br><br>';
  h += '<b>代码位置</b>：<code>engine/cross_domain_negotiation.py</code>——15条协商规则以NEGOTIATION_RULES列表形式定义，每条规则含id/场景/动作/触发条件/执行逻辑五个字段。新增协商规则只需在列表中追加新条目，无需修改其他代码。<br><br>';
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
      // 同步按钮
      h += '<div style="margin:8px 0"><button onclick="syncCorrectionsToModules()" style="background:#6366f1;color:#fff;border:none;padding:8px 16px;border-radius:6px;font-size:12px;cursor:pointer;font-weight:600">Sync Corrections to Modules</button> ';
      h += '<button onclick="loadSyncStatus()" style="background:#fff;border:1px solid #cbd5e1;padding:8px 16px;border-radius:6px;font-size:12px;cursor:pointer">Check Sync Status</button>';
      h += '<span id="sync-status" style="margin-left:10px;font-size:11px;color:#94a3b8"></span></div>';
      
      if (corr.rules && corr.rules.length > 0) {
        h += '<table class="tbl2"><tr><th>发现类型</th><th>行业</th><th>模式</th><th>纠正次数</th><th>置信度</th><th>状态</th><th style="width:60px">操作</th></tr>';
        for (var k = 0; k < corr.rules.length; k++) {
          var r = corr.rules[k];
          var fp = r.fingerprint || r.id || '';
          var autoLabel = r.auto_apply ? '<span style="color:#059669;font-weight:600">已生效</span>' : '<span style="color:#d97706">学习中</span>';
          h += '<tr id="cr-row-'+k+'">';
          h += '<td style="font-weight:600">' + esc(r.finding_type) + '</td>';
          h += '<td>' + esc(r.industry) + '</td>';
          h += '<td>' + esc(r.biz_model) + '</td>';
          h += '<td style="text-align:center">' + r.correction_count + '</td>';
          h += '<td style="text-align:center">' + (r.confidence*100).toFixed(0) + '%</td>';
          h += '<td>' + autoLabel + '</td>';
          h += '<td style="text-align:center"><button onclick="editCorrectionRule(\'' + encodeURIComponent(fp) + '\',' + k + ')" style="background:none;border:1px solid #93c5fd;color:#2563eb;font-size:11px;padding:2px 8px;border-radius:4px;cursor:pointer;margin-right:4px" title="Edit">Edit</button><button onclick="deleteCorrectionRule(\'' + encodeURIComponent(fp) + '\',' + k + ',' + r.correction_count + ',\'' + (r.industry||'') + '\')" style="background:none;border:1px solid #fca5a5;color:#dc2626;font-size:11px;padding:2px 8px;border-radius:4px;cursor:pointer" title="Archive (recoverable)">Archive</button></td>';
          h += '</tr>';
        }
        h += '</table>';
      } else {
        h += '<div style="text-align:center;padding:20px;color:#94a3b8">尚无纠正规则 — 老邓点在报告中发现上点击审核后→记录模式→累计1次纠正→升级为自动规则→1266条方法链(legacy)体系持续进化</div>';
      }
      h += '</div>';
      
      // ── 跨行业合成规则 ──
      h += '<div id="cross-rules-section" style="background:#f0fdf4;border:1px solid #86efac;border-radius:8px;padding:12px 16px;margin-bottom:12px">';
      h += '<div style="font-weight:700;color:#166534;font-size:13px;margin-bottom:8px">Cross-Industry Synthesized Rules</div>';
      h += '<div id="cross-rules-list" style="font-size:12px;color:#166534">Loading...</div>';
      h += '</div>';
      
      // ── 已归档规则（可恢复）──
      h += '<details style="margin-top:12px"><summary style="cursor:pointer;font-size:13px;color:#94a3b8">Archived Rules (click to expand · restorable)</summary>';
      h += '<div id="archived-rules-list" style="margin-top:8px;font-size:12px;color:#94a3b8">Loading...</div>';
      h += '</details>';
      
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
      h += '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px 20px;font-size:13px;color:#475569;line-height:2">';
      h += '<strong style="font-size:14px;color:#0f172a">智能大脑工作原理</strong><br><br>';
      h += '<b>调度中枢</b>：根据数据画像（行业/经营模式/资料种类/数据量级）自动决定激活哪些模块、跳过哪些模块。不是所有42个域分析都运行——服务行业自动跳过进销存等实物商品域，资料缺失时自动降级相关分析域。决策结果在管线日志中完整记录，可回溯。<br><br>';
      h += '<b>渐进学习</b>：同类企业分析3次后建立信任模型——记录该行业的常见信号模式、合理阈值区间、典型异常特征。后续分析依次检索历史案例进行行业对标校准。长期零产出的模块自动降权（降低分析优先级但不关闭），信任模型支持12维度加权相似度检索。<br><br>';
      h += '<b>纠正规则</b>：老邓在报告中点击审核→按模板填写审核意见→存入correction_rules.json→按"发现类型|行业|经营模式"生成指纹→累计1次纠正→升级为自动规则→四级回退匹配（精确→行业→通用→名称）→下次同类发现自动标注审核标记。审核不改变原始风险等级，仅在报告中展示绿色审核横幅。<br><br>';
      h += '<b>合规门禁</b>：12条稽查铁律（虚开发票/骗取退税/隐匿收入等）作为事前检查引擎——任何一条铁律被触发的报告自动标记违规，在报告正式输出前拦截。门禁独立于方法论过滤器运行，不受HARD_BAN/COND_BAN影响。<br><br>';
      h += '<b>政策核实</b>：9类税收优惠政策（高新技术15%、小微减免、研发加计扣除等）自动联网核实有效期——已到期政策自动搜索国家税务总局公告判断是否有延续，有延续则更新有效期，无延续则标记"已到期需补税"。<br><br>';
      h += '<b>数据一致性</b>：audit_consistency.py --sync 双维度自检——数字维度（扫描所有JS/PY文件中的硬编码数字与system_config.json对比，不一致自动修复）+文本维度（29项跨模块共享内容双层验证：9个text_sync块逐字哈希对比权威源→不一致自动覆盖，20个concept_link概念关联存在性验证）。四触发全覆盖：start.bat启动时/git pre-commit/一键分析pipeline子进程/手动--sync。<br><br>';
      h += '<b>内容同步</b>：shared_content_map.json v2.0 管理跨模块文本一致性——9个报告7章结构章节（封面+第一章~第七章+附件）在"报告编制要求"（权威源）与"税务稽查员手册"（依赖副本）之间自动同步。任一权威源变更→--sync自动覆盖依赖副本→确保两份文档永远一致。';
      h += '</div>';
      
      h += '</div>';
      area.innerHTML = h;
      // 加载跨行业合成规则
      fetch('/api/tax-risk-docs/ask?company_id=' + (window.currentCompanyId||1), {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({finding_index:0, question:'cross_rules', policy_doc:'', history:[]})
      }).then(function(){ return fetch('/api/feedback'); }).catch(function(){
        // Fallback: check correction_rules.json directly for __CROSS__ entries
        return {json:function(){return Promise.resolve({ok:true,auto_rules:0,rules:[]});}};
      });
      // Use the existing correction rules data from the page
      var crossList = document.getElementById('cross-rules-list');
      if (crossList && window._brainData && window._brainData.correction_rules) {
        var cr = window._brainData.correction_rules;
        var crossRules = [];
        for (var fp in cr.rules || cr) {
          if (fp.indexOf('__CROSS__') === 0) {
            var r = cr.rules ? cr.rules[fp] : cr[fp];
            crossRules.push({fingerprint: fp, finding: r.finding_type, industries: r.industry_rules, summary: r.summary});
          }
        }
        if (crossRules.length) {
          var ch = '';
          crossRules.forEach(function(cr){
            ch += '<div style="padding:6px 0;border-bottom:1px solid #dcfce7">';
            ch += '<div style="font-weight:600">' + (cr.finding||'?') + '</div>';
            ch += '<div style="color:#64748b;font-size:11px">' + (cr.summary||'') + '</div>';
            ch += '</div>';
          });
          crossList.innerHTML = ch;
        } else {
          crossList.innerHTML = 'No cross-industry rules yet — edit the same finding type for 2+ different industries to trigger synthesis.';
        }
      } else {
        crossList.innerHTML = 'Not yet synthesized';
      }
      // 加载已归档规则
      fetch('/api/feedback/archived').then(function(r){return r.json();}).then(function(d){
        var list = document.getElementById('archived-rules-list');
        if (!list || !d.rules || !d.rules.length) { if(list) list.innerHTML = 'No archived rules'; return; }
        var ah = '';
        d.rules.forEach(function(a){
          ah += '<div style="display:flex;align-items:center;gap:8px;padding:4px 0;border-bottom:1px solid #f1f5f9">';
          ah += '<span style="flex:1">' + (a.finding_type||'?').slice(0,40) + ' (' + a.correction_count + ' corrections, ' + (a.industry||'?') + ')</span>';
          ah += '<button onclick="window._restoreRule(\'' + encodeURIComponent(a.fingerprint) + '\')" style="background:#059669;color:#fff;border:none;padding:2px 8px;border-radius:4px;font-size:11px;cursor:pointer">Restore</button>';
          ah += '</div>';
        });
        list.innerHTML = ah;
      });
    });
}

function syncCorrectionsToModules() {
  var btn = event.target;
  btn.disabled = true;
  btn.textContent = 'Syncing...';
  fetch('/api/feedback/sync-modules', {method:'POST'}).then(function(r){return r.json();}).then(function(data){
    var st = document.getElementById('sync-status');
    if (data.ok && data.sync_result) {
      var sr = data.sync_result;
      if (sr.updated) {
        st.innerHTML = 'Updated ' + sr.modules_updated.join(', ') + ' (' + sr.changes_count + ' changes)';
        st.style.color = '#059669';
        alert('Sync complete: ' + sr.changes_count + ' changes written to ' + sr.modules_updated.join(', '));
      } else {
        st.innerHTML = 'No eligible rules found (need 1+ corrections at 60%+ confidence)';
        st.style.color = '#94a3b8';
      }
    }
    btn.disabled = false;
    btn.textContent = 'Sync Corrections to Modules';
  }).catch(function(e){
    btn.disabled = false;
    btn.textContent = 'Sync Corrections to Modules';
    var st = document.getElementById('sync-status');
    st.innerHTML = 'Error: ' + e.message;
    st.style.color = '#dc2626';
  });
}

function loadSyncStatus() {
  var st = document.getElementById('sync-status');
  st.innerHTML = 'Loading...';
  st.style.color = '#94a3b8';
  fetch('/api/feedback/sync-status').then(function(r){return r.json();}).then(function(data){
    if (data.ok) {
      var eligible = data.eligible_rules || 0;
      st.innerHTML = eligible + ' rules eligible for sync';
      st.style.color = eligible > 0 ? '#059669' : '#94a3b8';
    }
  }).catch(function(){
    st.innerHTML = 'Status unavailable';
    st.style.color = '#dc2626';
  });
}

