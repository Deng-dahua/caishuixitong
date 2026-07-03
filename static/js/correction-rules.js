/**
 * 纠正规则中转站 — 编辑/审核/追问/重置 四通道规则汇总
 * 数据源：user_corrections.json + content_feedback.json
 */
function renderCorrectionRulesHub(container) {
  if (!container) return;
  window.currentModule = '规则中转站';

  container.innerHTML = '<style>' +
    '.crh-layout{max-width:1100px;margin:0 auto;padding:24px 16px;background:#fff}' +
    '.crh-h2{font-size:20px;font-weight:800;color:#0f172a;margin:0 0 4px}' +
    '.crh-sub{font-size:13px;color:#94a3b8;margin:0 0 24px;line-height:2}' +
    '.crh-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:28px}' +
    '.crh-stat{text-align:center;padding:16px 12px;background:#fff;border:1px solid #e2e8f0;border-radius:8px}' +
    '.crh-stat-num{font-size:28px;font-weight:800;color:#0f172a}' +
    '.crh-stat-label{font-size:12px;color:#94a3b8;margin-top:4px}' +
    '.crh-filter{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}' +
    '.crh-filter-btn{padding:6px 16px;border:1px solid #e2e8f0;border-radius:20px;font-size:12px;cursor:pointer;background:#fff;color:#475569}' +
    '.crh-filter-btn:hover,.crh-filter-btn.active{background:#2563eb;color:#fff;border-color:#2563eb}' +
    '.crh-card{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px 20px;margin-bottom:10px}' +
    '.crh-card:hover{box-shadow:0 2px 8px rgba(0,0,0,.06)}' +
    '.crh-card-hd{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}' +
    '.crh-card-type{font-weight:700;color:#0f172a;font-size:14px}' +
    '.crh-badge{padding:2px 10px;border-radius:10px;font-size:11px;font-weight:600}' +
    '.crh-badge-edit{background:#eff6ff;color:#2563eb}' +
    '.crh-badge-audit{background:#ecfdf5;color:#059669}' +
    '.crh-badge-ask{background:#fef3c7;color:#d97706}' +
    '.crh-badge-reset{background:#fef2f2;color:#dc2626}' +
    '.crh-badge-high{background:#fee2e2;color:#dc2626}' +
    '.crh-badge-mid{background:#fef3c7;color:#d97706}' +
    '.crh-badge-low{background:#ecfdf5;color:#059669}' +
    '.crh-meta{font-size:11px;color:#94a3b8;display:flex;gap:16px;flex-wrap:wrap}' +
    '.crh-reason{font-size:12px;color:#475569;margin-top:8px;padding:8px 12px;background:#f8fafc;border-radius:6px;line-height:1.8}' +
    '.crh-chain{font-size:11px;color:#64748b;margin-top:6px}' +
    '.crh-empty{text-align:center;padding:60px;color:#94a3b8}' +
    '</style>' +
    '<div class="crh-layout">' +
    '<h2 class="crh-h2">🔄 纠正规则中转站</h2>' +
    '<p class="crh-sub">编辑/审核/追问/重置 — 四通道汇总。每条规则自动传播到五链（稽查指令/线索链/证据链/分析链/方法论），下次一键分析时自动应用。<br>自动化机制：纠正>=3次+置信度>=0.8→注入自愈规则库、跨公司合成（公司间相似规则自动提炼）。</p>' +
    '<div class="crh-stats" id="crh-stats"></div>' +
    '<div class="crh-filter" id="crh-filter"></div>' +
    '<div id="crh-body"><div style="text-align:center;padding:60px"><span class="spinner"></span> 加载纠正规则...</div></div>' +
    '</div>';

  loadCorrectionRules();
}

async function loadCorrectionRules() {
  try {
    var r1 = await fetch('/api/feedback/corrections').then(function(r){return r.json()});
    var r2 = await fetch('/api/feedback/content-logs').then(function(r){return r.json()});
    renderCorrectionData(r1, r2);
  } catch(e) {
    document.getElementById('crh-body').innerHTML = '<div class="crh-empty" style="color:#dc2626">加载失败: ' + e.message + '</div>';
  }
}

function renderCorrectionData(corrections, contents) {
  var rules = (corrections.ok ? corrections.rules : []) || [];
  var logs = (contents.ok ? contents.logs : []) || [];
  
  // 统计
  var editCount = 0, auditCount = 0, askCount = 0, resetCount = 0;
  logs.forEach(function(l) {
    var txt = (l.correct_content || l.wrong_content || '').toLowerCase();
    if (txt.indexOf('[重置]') >= 0) resetCount++;
    else if (txt.indexOf('审核') >= 0 || txt.indexOf('audit') >= 0) auditCount++;
    else if (txt.indexOf('追问') >= 0 || txt.indexOf('ask') >= 0) askCount++;
    else editCount++;
  });
  
  document.getElementById('crh-stats').innerHTML =
    '<div class="crh-stat"><div class="crh-stat-num">' + rules.length + '</div><div class="crh-stat-label">总规则数</div></div>' +
    '<div class="crh-stat"><div class="crh-stat-num" style="color:#2563eb">' + editCount + '</div><div class="crh-stat-label">📝 编辑</div></div>' +
    '<div class="crh-stat"><div class="crh-stat-num" style="color:#059669">' + auditCount + '</div><div class="crh-stat-label">✅ 审核</div></div>' +
    '<div class="crh-stat"><div class="crh-stat-num" style="color:#d97706">' + (askCount + logs.length - editCount - auditCount - resetCount) + '</div><div class="crh-stat-label">🔍 追问/重置</div></div>';

  // 筛选器
  document.getElementById('crh-filter').innerHTML =
    '<button class="crh-filter-btn active" onclick="filterCRH(\'all\')">全部 (' + rules.length + ')</button>' +
    '<button class="crh-filter-btn crh-badge-edit" onclick="filterCRH(\'high\')" style="background:#eff6ff;color:#2563eb;border-color:#bfdbfe">高置信度(>=0.8)</button>' +
    '<button class="crh-filter-btn crh-badge-low" onclick="filterCRH(\'auto\')" style="background:#ecfdf5;color:#059669;border-color:#a7f3d0">自动应用</button>';
  
  window._crhRules = rules;
  window._crhFilter = 'all';
  renderCRHList(rules, 'all');
}

function filterCRH(type) {
  window._crhFilter = type;
  var btns = document.querySelectorAll('.crh-filter-btn');
  btns.forEach(function(b){ b.classList.remove('active'); });
  event.target.classList.add('active');
  
  var filtered = window._crhRules;
  if (type === 'high') filtered = window._crhRules.filter(function(r){ return (r.confidence||0) >= 0.8; });
  else if (type === 'auto') filtered = window._crhRules.filter(function(r){ return r.auto_apply; });
  renderCRHList(filtered, type);
}

function renderCRHList(rules, filter) {
  var body = document.getElementById('crh-body');
  if (!rules || rules.length === 0) {
    body.innerHTML = '<div class="crh-empty">暂无纠正规则。<br><br>在报告中使用 ✏️编辑/✅审核/🔍追问/🔄重置 后，规则将出现在这里。</div>';
    return;
  }

  var html = '';
  rules.forEach(function(r) {
    var ft = r.finding_type || r.type || '未分类';
    var industry = r.industry || '通用';
    var conf = (r.confidence || 0);
    var confPct = Math.round(conf * 100);
    var corrCount = (r.correction_count || r.corrections || []).length || 0;
    var auto = r.auto_apply ? '✅ 自动' : '⏳ 积累中';
    var latest = (r.corrections || []);
    latest = latest.length > 0 ? latest[latest.length-1] : {};
    var reason = latest.reason || r.last_reason || '';
    var origRisk = latest.original_risk || '中风险';
    var corrRisk = latest.corrected_risk || origRisk;
    
    var confColor = conf >= 0.8 ? '#059669' : conf >= 0.5 ? '#d97706' : '#94a3b8';
    var riskBadge = origRisk.indexOf('高') >= 0 ? 'crh-badge-high' : (origRisk.indexOf('低') >= 0 ? 'crh-badge-low' : 'crh-badge-mid');
    var timestamp = latest.timestamp || r.updated_at || '';
    
    html += '<div class="crh-card">' +
      '<div class="crh-card-hd">' +
        '<div class="crh-card-type">' + ft + '</div>' +
        '<div style="display:flex;gap:8px;align-items:center">' +
          '<span class="crh-badge ' + riskBadge + '">' + origRisk + ' → ' + corrRisk + '</span>' +
          '<span style="font-size:11px;color:' + confColor + ';font-weight:600">置信度 ' + confPct + '%</span>' +
          '<span style="font-size:11px;color:#94a3b8">' + auto + '</span>' +
        '</div>' +
      '</div>' +
      '<div class="crh-meta">' +
        '<span>🏭 ' + industry + '</span>' +
        '<span>📊 累计纠正 ' + corrCount + ' 次</span>' +
        (timestamp ? '<span>🕐 ' + timestamp.slice(0,16) + '</span>' : '') +
      '</div>' +
      (reason ? '<div class="crh-reason">' + reason.slice(0,300) + '</div>' : '') +
      (r._auto_corrected ? '<div class="crh-chain">🔗 已传播: 指令链/线索链/证据链/分析链/方法论链</div>' : '') +
    '</div>';
  });

  body.innerHTML = html;
}
