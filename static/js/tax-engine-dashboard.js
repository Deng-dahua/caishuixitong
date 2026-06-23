/**
 * 推理引擎仪表盘 — 独立展示推理引擎 v2.0 的全部内部状态
 * Phase 1-4 完整可视化
 */

function renderEngineDashboardPage(container) {
  container.innerHTML = '<div id="engine-dashboard-area" style="max-width:1200px;margin:0 auto;padding:16px"><div style="text-align:center;padding:60px;color:#94a3b8"><span class="spinner"></span> 正在加载推理引擎数据...</div></div>';
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

  // 标签切换 — 始终显示（规则库不需要分析数据）
  var tabBar = '<div style="display:flex;gap:8px;margin-bottom:16px;border-bottom:2px solid #e2e8f0;padding-bottom:8px">' +
    '<div class="eng-tab active" onclick="switchEngineTab(\'status\')" id="tab-status">运行状态</div>' +
    '<div class="eng-tab" onclick="switchEngineTab(\'rules\')" id="tab-rules">规则库 (53条)</div>' +
    '</div><div id="eng-tab-content"></div>';
  
  area.innerHTML = tabBar;
  renderStatusTab();
  fetchEngineRules();
}

function switchEngineTab(tab) {
  document.querySelectorAll('.eng-tab').forEach(function(el) { el.classList.remove('active'); });
  document.getElementById('tab-' + tab).classList.add('active');
  if (tab === 'status') renderStatusTab();
  else renderRulesTab();
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
  
  // Phase 1
  var p1 = rules.phases['Phase1-初查信号检测'];
  if (p1) {
    h += '<div class="engine-card" style="margin-bottom:20px;border-top:3px solid #3b82f6">';
    h += '<div class="engine-card-title"><span style="color:#3b82f6">■</span> Phase 1 — 初查信号检测 (' + (p1.rules||[]).length + '条规则)</div>';
    h += '<div style="font-size:12px;color:#64748b;margin-bottom:10px">' + esc(p1.description) + '</div>';
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
  
  // Phase 2
  var p2 = rules.phases['Phase2-信号→域映射'];
  if (p2 && !p2.error) {
    h += '<div class="engine-card" style="margin-bottom:20px;border-top:3px solid #8b5cf6">';
    h += '<div class="engine-card-title"><span style="color:#8b5cf6">■</span> Phase 2 — 信号→域映射 (' + (p2.count||0) + '条)</div>';
    h += '<div style="font-size:12px;color:#64748b;margin-bottom:10px">' + esc(p2.description) + '</div>';
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
  
  // Phase 3 信号叠加模式
  var p3p = rules.phases['Phase3-信号叠加模式'];
  if (p3p && !p3p.error) {
    h += '<div class="engine-card" style="margin-bottom:20px;border-top:3px solid #06b6d4">';
    h += '<div class="engine-card-title"><span style="color:#06b6d4">■</span> Phase 3 — 信号叠加模式 (' + (p3p.count||0) + '条)</div>';
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
  
  // Phase 3 冲突消解
  var p3c = rules.phases['Phase3-冲突消解规则'];
  if (p3c && !p3c.error) {
    h += '<div class="engine-card" style="margin-bottom:20px;border-top:3px solid #ec4899">';
    h += '<div class="engine-card-title"><span style="color:#ec4899">■</span> Phase 3 — 冲突消解规则 (' + (p3c.count||0) + '条)</div>';
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
  
  h += '<div style="text-align:center;color:#94a3b8;font-size:12px;padding:16px">规则库共 ' + totalRules + ' 条规则 | 全行业适用 | 可编辑JSON追加</div>';
  
  area.innerHTML = h;
}

// ── 辅助函数 ──

function flagBadge(v) {
  return v ? '<span style="color:#059669;font-weight:600">是</span>' : '<span style="color:#94a3b8">否</span>';
}

function fmtMoney(v) {
  if (!v && v !== 0) return '-';
  var n = Number(v);
  if (Math.abs(n) >= 100000000) return (n / 100000000).toFixed(2) + ' 亿';
  if (Math.abs(n) >= 10000) return (n / 10000).toFixed(0) + ' 万';
  return n.toLocaleString('zh-CN') + ' 元';
}

function esc(s) {
  if (s === null || s === undefined) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function loadEngineDashboard() {
  var cid = window._currentCompanyId || 1;
  fetch('/api/tax-risk-docs/last-analysis?company_id=' + cid)
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (d && d.report) {
        renderEngineDashboard(d.report);
      } else {
        document.getElementById('engine-dashboard-area').innerHTML = 
          '<div style="padding:40px;text-align:center;color:#94a3b8">暂无分析数据。请先在资料风险分析页面运行一键分析。</div>';
      }
    })
    .catch(function() {
      document.getElementById('engine-dashboard-area').innerHTML = 
        '<div style="padding:40px;text-align:center;color:#dc2626">加载失败，请确认服务器已启动。</div>';
    });
}
