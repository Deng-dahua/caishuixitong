// ==================== 数据看板 ====================
async function renderDashboard(container) {
  const el = container || document.getElementById('page-' + currentPage) || document.getElementById('content-area');
  el.innerHTML = '<div style="color:#999;padding:20px">加载中...</div>';
  try {
    const data = await api('/api/dashboard');
    var companyName = window._currentCompanyName || '';
    var h = '';
    h += '<div class="card card-fill">';

    // ── 页面标题 ──
    h += '<div class="page-header">';
    h += '<h1>' + (companyName ? '📊 ' + companyName + ' · 数据看板' : '📊 数据看板') + '</h1>';
    h += '<p>企业核心经营数据一览 · ' + new Date().toLocaleDateString('zh-CN', {year:'numeric',month:'long',day:'numeric'}) + '</p>';
    h += '</div>';

    // ── KPI 卡片 ──
    h += '<div class="kpi-grid">';
    h += '<div class="kpi-card"><div class="kpi-icon blue">👥</div><div class="kpi-info"><div class="kpi-label">客户档案</div><div class="kpi-value">' + (data.customer_count||0) + '</div><div class="kpi-sub">个</div></div></div>';
    h += '<div class="kpi-card"><div class="kpi-icon purple">🏭</div><div class="kpi-info"><div class="kpi-label">供应商</div><div class="kpi-value">' + (data.supplier_count||0) + '</div><div class="kpi-sub">个</div></div></div>';
    h += '<div class="kpi-card"><div class="kpi-icon green">👷</div><div class="kpi-info"><div class="kpi-label">员工</div><div class="kpi-value">' + (data.employee_count||0) + '</div><div class="kpi-sub">人</div></div></div>';
    h += '<div class="kpi-card"><div class="kpi-icon slate">📚</div><div class="kpi-info"><div class="kpi-label">会计科目</div><div class="kpi-value">' + (data.account_count||0) + '</div><div class="kpi-sub">个</div></div></div>';
    h += '</div>';

    // ── 发票统计 ──
    h += '<div class="kpi-grid">';
    h += '<div class="kpi-card"><div class="kpi-icon blue">📋</div><div class="kpi-info"><div class="kpi-label">开具发票</div><div class="kpi-value" style="color:#2563eb">' + (data.sales_invoice_count||0) + '</div><div class="kpi-sub">张</div></div></div>';
    h += '<div class="kpi-card"><div class="kpi-icon green">📥</div><div class="kpi-info"><div class="kpi-label">取得发票</div><div class="kpi-value" style="color:#16a34a">' + (data.purchase_invoice_count||0) + '</div><div class="kpi-sub">张</div></div></div>';
    h += '<div class="kpi-card"><div class="kpi-icon amber">📒</div><div class="kpi-info"><div class="kpi-label">记账发票</div><div class="kpi-value" style="color:#ca8a04">' + (data.bookkeeping_invoice_count||0) + '</div><div class="kpi-sub">张</div></div></div>';
    h += '</div>';

    // ── 快捷操作 ──
    h += '<div class="quick-actions">';
    h += '<div class="quick-actions-title">快捷操作 · 全部模块</div>';
    h += '<div style="display:flex;flex-wrap:wrap;gap:8px">';
    
    var allActions = [
      {group:'账务处理', items:[
        {page:'sales-invoices', label:'📋 销项发票', cls:'btn-primary'},
        {page:'purchase-invoices', label:'📥 进项发票', cls:'btn-outline'},
        {page:'bookkeeping-invoices', label:'📒 记账发票', cls:'btn-outline'},
        {page:'bank-transactions', label:'🏦 银行流水', cls:'btn-outline'},
      ]},
      {group:'税务申报', items:[
        {page:'vat-declaration', label:'📊 增值税', cls:'btn-outline'},
        {page:'salary', label:'💳 工资薪金', cls:'btn-outline'},
        {page:'social-security', label:'🛡️ 社保', cls:'btn-outline'},
        {page:'housing-fund', label:'🏠 公积金', cls:'btn-outline'},
      ]},
      {group:'稽查分析', items:[
        {page:'tax-doc-analysis', label:'🔬 一键分析', cls:'btn-primary'},
        {page:'tax-risk-rules', label:'📋 稽查指令', cls:'btn-outline'},
        {page:'tax-risk-report', label:'📊 账务风险', cls:'btn-outline'},
        {page:'file-parsing', label:'📁 文件解析', cls:'btn-outline'},
        {page:'domain-analysis', label:'🔬 域分析', cls:'btn-outline'},
        {page:'methodology-filter', label:'🎯 方法论过滤', cls:'btn-outline'},
      ]},
      {group:'线索证据链', items:[
        {page:'chains-page', label:'🔍 线索链', cls:'btn-outline'},
        {page:'evidence-page', label:'🔒 证据链', cls:'btn-outline'},
        {page:'analyze-page', label:'⚡ 分析链', cls:'btn-outline'},
      ]},
      {group:'系统引擎', items:[
        {page:'engine-dashboard', label:'🖥️ 引擎仪表盘', cls:'btn-outline'},
        {page:'quality-system', label:'🛡️ 质量保障', cls:'btn-outline'},
        {page:'ai-rules', label:'🧠 行为准则', cls:'btn-outline'},
        {page:'tax-agi', label:'🧬 税务AGI', cls:'btn-outline'},
        {page:'system-logs', label:'📜 系统日志', cls:'btn-outline'},
      ]},
      {group:'规范手册', items:[
        {page:'auditor-handbook', label:'⚖️ 稽查员手册', cls:'btn-outline'},
        {page:'report-standards', label:'📐 编制要求', cls:'btn-outline'},
        {page:'feedback-template', label:'📝 审核模板', cls:'btn-outline'},
      ]}
    ];
    
    allActions.forEach(function(group){
      h += '<div style="width:100%;margin-top:4px"><span style="font-size:11px;color:#94a3b8;font-weight:600">'+group.group+'</span></div>';
      group.items.forEach(function(item){
        h += '<button class="btn '+item.cls+'" onclick="navigateTo(\''+item.page+'\')">'+item.label+'</button>';
      });
    });
    
    h += '</div></div>';

    h += '</div>'; // card-fill
    el.innerHTML = h;
  } catch (e) {
    showError(el, e, '加载看板数据');
  }
}


// ── 简易趋势图（Canvas柱状图）──
function renderTrendChart(data, containerId) {
  var container = document.getElementById(containerId);
  if (!container || !data || data.length === 0) return;
  
  var canvas = document.createElement('canvas');
  canvas.width = 600; canvas.height = 200;
  canvas.style.width = '100%'; canvas.style.maxWidth = '600px';
  canvas.style.height = '200px';
  container.appendChild(canvas);
  
  var ctx = canvas.getContext('2d');
  var w = canvas.width, h = canvas.height;
  var padding = {top: 20, right: 20, bottom: 30, left: 50};
  var chartW = w - padding.left - padding.right;
  var chartH = h - padding.top - padding.bottom;
  
  var maxVal = Math.max.apply(null, data.map(function(d){return d.value||0})) * 1.2 || 1;
  var barW = Math.min(40, chartW / data.length * 0.7);
  var gap = chartW / data.length;
  
  // Grid
  ctx.strokeStyle = '#e2e8f0';
  ctx.lineWidth = 0.5;
  for (var i = 0; i <= 4; i++) {
    var y = padding.top + chartH * i / 4;
    ctx.beginPath(); ctx.moveTo(padding.left, y); ctx.lineTo(w - padding.right, y); ctx.stroke();
    ctx.fillStyle = '#94a3b8'; ctx.font = '10px sans-serif';
    ctx.fillText((maxVal*(4-i)/4).toFixed(0), 2, y+3);
  }
  
  // Bars
  data.forEach(function(d, i){
    var x = padding.left + gap * i + (gap - barW) / 2;
    var barH = (d.value || 0) / maxVal * chartH;
    var y = padding.top + chartH - barH;
    
    var grad = ctx.createLinearGradient(x, y, x, padding.top + chartH);
    grad.addColorStop(0, d.color || '#3b82f6');
    grad.addColorStop(1, (d.color || '#3b82f6')+'88');
    ctx.fillStyle = grad;
    ctx.fillRect(x, y, barW, barH);
    
    ctx.fillStyle = '#64748b'; ctx.font = '9px sans-serif'; ctx.textAlign = 'center';
    ctx.fillText(d.label||'', x + barW/2, padding.top + chartH + 15);
    ctx.fillText((d.value||0).toLocaleString(), x + barW/2, y - 4);
  });
}
