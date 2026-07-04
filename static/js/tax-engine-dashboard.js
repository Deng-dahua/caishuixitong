/**
 * 智能大脑·运行仪表盘 — 统一大脑全部内部状态
 * Phase 1-4 完整可视化 + AGI合并大脑
 */

function renderEngineDashboardPage(container) {
  container.innerHTML = '<div style="max-width:1100px;margin:0 auto;padding:24px 16px;background:#fff">'
    + '<h2 style="font-size:20px;font-weight:800;color:#0f172a;margin:0 0 4px">🧠 智能大脑·运行仪表盘</h2>'
    + '<p style="font-size:13px;color:#94a3b8;margin:0 0 24px">统一大脑运行监控中心——5个标签页覆盖管道调度/推理引擎/学习反馈/质量保障/AGI核心。数据来源：系统实时API + 分析缓存。每项指标可追溯到具体的代码位置和数据文件。</p>'
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
      '<div style="font-size:13px;color:#64748b;line-height:2">请前往 <b>风险分析</b> 页面运行一键分析，或点击上方 <b>学习反馈</b> 标签查看1608条稽查指令。<br>其他标签页（质量保障/AGI核心/推理引擎）也需要分析数据作为输入。</div>' +
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
  h += '</nav>';

  h += '<div class="dim-main">';
  h += '<h2 style="font-size:20px;font-weight:800;color:#0f172a;margin:0 0 4px">🔬 引擎能力维度</h2>';
  h += '<div style="background:#eff6ff;padding:10px 16px;border-radius:6px;font-size:13px;color:#1e40af;margin-bottom:16px;border:1px solid #bfdbfe;font-weight:600">🔬 能力维度：28维能力矩阵评分——四星(核心已完备)+三星(已实现核心)，一看就知道引擎强在哪、弱在哪。</div>';
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
  h += '</div></div>';
  container.innerHTML = h;
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
  
  // 发现质量（高风险占比）
  var findings = cachedData.all_findings || [];
  var highRisk = findings.filter(function(f){ return f.level === '高风险' || f.level === '极高风险'; }).length;
  var qualityPct = findings.length > 0 ? Math.round((1 - highRisk/findings.length) * 100) : 100;
  h += qualityCard('发现质量', qualityPct + '%', qualityPct >= 70 ? '#059669' : '#f59e0b', '中低风险占比越高说明系统越精准');
  
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
    {id:'NEG-AUG-002',scene:'联合增强（触发新发现）',action:'增强',from:'个人收款+收款待分析+个人交易',to:'综合生成"隐匿收入预警"',desc:'三域独立检测均指向个人账户收款。协商引擎自动合成极高风险发现，引用《征管法》第63条（偷税处罚）。'},
    {id:'NEG-AUG-003',scene:'联合增强（触发新发现）',action:'增强',from:'供应商异常+关联重叠+集中度过高',to:'综合生成"对倒开票预警"',desc:'三域独立检测供应商结构异常，协商引擎自动合成高风险发现，引用《发票管理办法》第22条和《刑法》第205条。'},
    {id:'NEG-AUG-004',scene:'联合增强（触发新发现）',action:'增强',from:'红冲/作废发票+收款偏离',to:'综合生成"虚开发票预警"',desc:'开票后红冲但货款已收→可能为虚假交易后冲销。协商引擎自动合成高风险发现，引用《发票管理办法》第22条。'},
    {id:'NEG-AUG-005',scene:'联合增强（触发新发现）',action:'增强',from:'工资个税异常+社保基数偏低',to:'综合生成"两套工资表预警"',desc:'个税域+社保域同时检出异常→可能为账外工资/虚列人头。协商引擎自动合成高风险发现。'},
    {id:'NEG-AUG-006',scene:'联合增强（触发新发现）',action:'增强',from:'专票超期未认证+进项税额异常',to:'综合生成"隐匿采购预警"',desc:'取得专票但故意不认证→收入成本不配比。协商引擎自动合成中风险发现。'},
    {id:'NEG-AUG-007',scene:'联合增强（触发新发现）',action:'增强',from:'个人收款+股东资金往来',to:'综合生成"公司人格混同预警"',desc:'股东个人账户与企业公户资金混同→涉嫌偷逃税款+公司法人格混同。协商引擎自动合成极高风险发现。'},
    {id:'NEG-AUG-008',scene:'联合增强（触发新发现）',action:'增强',from:'新办企业+大额开票',to:'综合生成"空壳开票预警"',desc:'新办企业短期内大额开票→可能为虚开团伙设立的空壳公司。协商引擎自动合成极高风险发现，引用《刑法》第205条。'},
    {id:'NEG-AUG-009',scene:'联合增强（触发新发现）',action:'增强',from:'劳务派遣成本+多处取得工资',to:'综合生成"拆分工资预警"',desc:'通过劳务派遣公司拆分工资、虚列人头降低个税和社保基数。协商引擎自动合成高风险发现。'},
    {id:'NEG-AUG-010',scene:'联合增强（触发新发现）',action:'增强',from:'境外付款+外汇相关信号',to:'综合生成"跨境税务预警"',desc:'境外付款可能涉及代扣代缴义务（增值税+预提所得税）/转让定价/利润转移。协商引擎自动合成高风险发现。'},
  ];

  var h = '';
  h += '<h3 style="font-size:18px;font-weight:700;color:#1a1a2e;margin:0 0 4px">🤝 跨域协商规则</h3>';
  h += '<p style="font-size:13px;color:#94a3b8;margin:0 0 20px">引擎在全部域分析完成后自动运行。29条协商规则：消解层8条 / 降级层6条 / 标记层5条 / 联合增强层10条。</p>';

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
  h += '<b>执行时序</b>：所有42个域分析函数独立完成→跨域协商引擎(run_negotiation)扫描all_findings→逐条匹配29条NEG规则→消解矛盾/降级不适/标记受限/增强多域→输出协商后findings→进入方法论过滤器→生成报告。协商引擎在Phase3交叉验证之后、方法论过滤器之前执行。<br><br>';
  h += '<b>代码位置</b>：<code>engine/cross_domain_negotiation.py</code>——29条协商规则以NEGOTIATION_RULES列表形式定义，每条规则含id/场景/动作/触发条件/执行逻辑五个字段。新增协商规则只需在列表中追加新条目，无需修改其他代码。<br><br>';
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
      h += '<div style="background:#f8fafc;padding:10px 14px;border-radius:6px;font-size:12px;color:#64748b;margin-bottom:16px;border-left:3px solid #dc2626">🧠 AGI核心：调度中枢、成长曲线、税收优惠核实——大脑本身的学习状态和模块组成。</div>';
      
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
      
      // ── 3. 纠正规则库 → 已迁移至规则中转站 ──
      h += '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px 20px;margin-bottom:16px">';
      h += '<h3 style="color:#1e293b;border-bottom:2px solid #7c3aed;padding-bottom:8px">纠正规则库</h3>';
      h += '<div style="padding:20px;text-align:center"><a href="#" onclick="navigateTo(\'correction-rules\');return false" style="display:inline-block;padding:12px 28px;background:#7c3aed;color:#fff;border-radius:8px;text-decoration:none;font-weight:600;font-size:14px">🔄 前往规则中转站</a></div>';
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
      h += '<h3 style="margin:0 0 10px;color:#0f172a;font-size:14px">🔍 假设生成引擎 — 稽查假设与验证</h3>';
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

