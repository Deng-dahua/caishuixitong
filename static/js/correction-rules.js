/**
 * 纠正规则中转站 — 编辑/审核/追问 四通道规则汇总
 * 数据源：user_corrections.json + content_feedback.json
 */
function renderCorrectionRulesHub(container) {
  if (!container) return;
  window.currentModule = '规则中转站';

  container.innerHTML = '<style>' +
    '.crh-layout{max-width:1100px;margin:0 auto;padding:24px 16px;background:#fff}' +
    '.crh-h2{font-size:20px;font-weight:800;color:#0f172a;margin:0 0 4px}' +
    '.crh-sub{font-size:13px;color:#94a3b8;margin:0 0 24px;line-height:2}' +
    '.crh-stats{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:28px}' +
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
    '<p class="crh-sub">编辑/审核/追问 — 三通道规则汇总。编辑和追问触发引擎自学习生成新规则，经过中转站分类后注入对应模块（稽查指令/线索链/证据链/分析链/方法论/规则引擎等），标注【引擎自学习】。<br>规则可重置（暂停使用）或恢复（重新激活）。</p>' +
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
    '<div class="crh-stat"><div class="crh-stat-num" style="color:#7c3aed">' + askCount + '</div><div class="crh-stat-label">🔍 追问</div></div>' +
    '<div class="crh-stat"><div class="crh-stat-num" style="color:#dc2626">' + resetCount + '</div><div class="crh-stat-label">🔄 重置</div></div>';

  // 筛选器
  document.getElementById('crh-filter').innerHTML =
    '<button class="crh-filter-btn active" onclick="filterCRH(\'all\')">全部 (' + rules.length + ')</button>' +
    '<button class="crh-filter-btn crh-badge-edit" onclick="filterCRH(\'high\')" style="background:#eff6ff;color:#2563eb;border-color:#bfdbfe">高置信度(>=0.8)</button>' +
    '<button class="crh-filter-btn crh-badge-low" onclick="filterCRH(\'auto\')" style="background:#ecfdf5;color:#059669;border-color:#a7f3d0">自动应用</button>';
  
  window._crhRules = rules;
  window._crhFilter = 'all';
  renderCRHList(rules, 'all');
  
  // 渲染LLM自学习规则
  var learned = corrections.learned_rules || {};
  renderLearnedRules(learned);
}

function renderLearnedRules(learned) {
  var body = document.getElementById('crh-body');
  var active = learned.active || [];
  var reset = learned.reset || [];
  
  if (active.length === 0 && reset.length === 0) return;
  
  var h = '<div style="margin-top:32px;padding-top:24px;border-top:2px solid #e2e8f0">' +
    '<h3 style="font-size:16px;font-weight:700;color:#0f172a;margin:0 0 8px">🧠 引擎自学习规则</h3>' +
    '<p style="font-size:12px;color:#94a3b8;margin:0 0 16px">编辑和追问触发的引擎自主学习，经LLM分析后生成新规则，分类注入对应模块</p>';
  
  if (active.length > 0) {
    h += '<div style="font-size:13px;font-weight:600;color:#059669;margin-bottom:8px">✅ 已激活 (' + active.length + '条)</div>';
    active.forEach(function(r) {
      var mod = r.module || '其他';
      var modColor = {'稽查指令':'#2563eb','线索链':'#7c3aed','证据链':'#8b5cf6','分析链':'#06b6d4','方法论':'#f59e0b','规则引擎':'#dc2626','行业适配':'#059669','合规门禁':'#d97706','其他':'#94a3b8'}[mod] || '#94a3b8';
      var fm = r.module_info || {};
      h += '<div class="crh-card" style="border-left:3px solid ' + modColor + '">' +
        '<div class="crh-card-hd">' +
        '<span class="crh-card-type">' + (r.content||'').split('\\n')[0].replace('【规则名称】','') + '</span>' +
        '<div style="display:flex;gap:6px;align-items:center">' +
        '<span style="font-size:10px;padding:2px 8px;border-radius:8px;background:' + modColor + '15;color:' + modColor + ';font-weight:600">📦 ' + mod + '</span>' +
        '<span style="font-size:10px;color:' + (r.source==='编辑'?'#2563eb':'#7c3aed') + '">' + (r.source==='编辑'?'📝':'🔍') + r.source + '</span>' +
        '<button onclick="event.stopPropagation();resetLearnedRule(\'' + r.id + '\')" style="font-size:10px;padding:2px 10px;background:#fef2f2;color:#dc2626;border:1px solid #fecaca;border-radius:4px;cursor:pointer">🔄 重置</button>' +
        '</div></div>' +
        '<div class="crh-meta"><span>📅 ' + (r.created_at||'').slice(0,10) + '</span><span>🏭 ' + (r.industry||'通用') + '</span><span>📂 目标模块：' + (fm.file||'') + '</span></div>' +
        '<pre class="crh-reason" style="white-space:pre-wrap;font-size:11px;max-height:120px;overflow-y:auto">' + (r.content||'') + '</pre>' +
        '</div>';
    });
  }
  
  if (reset.length > 0) {
    h += '<div style="font-size:13px;font-weight:600;color:#94a3b8;margin:16px 0 8px">⚠️ 已重置 (' + reset.length + '条)</div>';
    reset.forEach(function(r) {
      h += '<div class="crh-card" style="opacity:0.6;background:#f1f5f9">' +
        '<div class="crh-card-hd">' +
        '<span class="crh-card-type" style="text-decoration:line-through">' + (r.content||'').split('\\n')[0].replace('【规则名称】','') + '</span>' +
        '<button onclick="event.stopPropagation();restoreLearnedRule(\'' + r.id + '\')" style="font-size:10px;padding:2px 10px;background:#ecfdf5;color:#059669;border:1px solid #a7f3d0;border-radius:4px;cursor:pointer">↩ 恢复</button>' +
        '</div>' +
        '<div class="crh-meta"><span>📅 ' + (r.reset_at||r.created_at||'').slice(0,10) + '</span><span>📦 ' + (r.module||'其他') + '</span></div>' +
        '<pre class="crh-reason" style="white-space:pre-wrap;font-size:11px;max-height:60px;overflow-y:auto">' + (r.content||'') + '</pre>' +
        '</div>';
    });
  }
  
  h += '</div>';
  body.innerHTML += h;
}

function resetLearnedRule(ruleId) {
  if (!confirm('确定重置此规则？重置后引擎不再使用，但可随时恢复。')) return;
  fetch('/api/feedback/rules/reset', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({rule_id: ruleId})
  }).then(function(r){ return r.json(); }).then(function(d){
    if (d.ok) location.reload();
    else alert(d.message);
  });
}

function restoreLearnedRule(ruleId) {
  fetch('/api/feedback/rules/restore', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({rule_id: ruleId})
  }).then(function(r){ return r.json(); }).then(function(d){
    if (d.ok) location.reload();
    else alert(d.message);
  });
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
    body.innerHTML = '<div class="crh-empty">暂无纠正规则。<br><br>在报告中使用 ✏️编辑/✅审核/🔍追问 后，规则将出现在这里。<br>编辑和追问会触发引擎自学习生成新规则。</div>';
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
