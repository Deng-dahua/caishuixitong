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
    '.crh-history{margin-top:10px;border-top:1px dashed #e2e8f0;padding-top:8px}' +
    '.crh-history summary{font-size:12px;color:#2563eb;cursor:pointer}' +
    '.crh-history-item{font-size:12px;color:#475569;padding:8px 0;border-bottom:1px solid #f1f5f9;line-height:1.7}' +
    '.crh-empty{text-align:center;padding:60px;color:#94a3b8}' +
    '@media(max-width:760px){.crh-stats{grid-template-columns:repeat(2,1fr)}.crh-card-hd{align-items:flex-start;gap:8px}.crh-meta{display:grid;gap:5px}}' +
    '</style>' +
    '<div class="crh-layout">' +
    '<h2 class="crh-h2">🔄 纠正规则中转站</h2>' +
    '<p class="crh-sub">编辑/审核/追问 — 三通道规则汇总。编辑和追问触发引擎自学习生成新规则，经过中转站分类后注入对应模块（税务合规指令/线索链/证据链/分析链/方法论/规则引擎等），标注【引擎自学习】。<br>规则可重置（暂停使用）或恢复（重新激活）。</p>' +
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
  
}

function _crhEscape(value) {
  if (typeof escapeHtml === 'function') return escapeHtml(String(value == null ? '' : value));
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function _crhConfidence(rule) {
  var value = Number(rule && rule.confidence);
  if (!Number.isFinite(value)) value = 0;
  if (value > 1) value = value / 100;
  return Math.max(0, Math.min(1, value));
}

function _crhIsAuto(rule) {
  return rule && (rule.auto_apply === true || rule.auto_apply === 1 || rule.auto_apply === 'true');
}

function _crhFormatDate(value) {
  if (!value) return '暂无时间';
  var date = new Date(value);
  if (Number.isNaN(date.getTime())) return _crhEscape(value);
  return _crhEscape(date.toLocaleString('zh-CN', {hour12:false}));
}

function renderCRHList(rules, filter) {
  var body = document.getElementById('crh-body');
  if (!body) return;
  var source = Array.isArray(rules) ? rules : [];
  var visible = source.filter(function(rule) {
    if (filter === 'high') return _crhConfidence(rule) >= 0.8;
    if (filter === 'auto') return _crhIsAuto(rule);
    return true;
  });

  if (!visible.length) {
    var label = filter === 'all' ? '尚未形成纠正规则' : '当前筛选条件下没有规则';
    body.innerHTML = '<div class="crh-empty">📭 ' + label +
      '<div style="font-size:12px;margin-top:8px">审核、编辑或追问形成反馈后，系统会在这里展示可追溯的学习结果。</div></div>';
    return;
  }

  body.innerHTML = visible.map(function(rule) {
    var confidence = _crhConfidence(rule);
    var confidencePct = Math.round(confidence * 100);
    var confidenceClass = confidence >= 0.8 ? 'crh-badge-high' :
      (confidence >= 0.5 ? 'crh-badge-mid' : 'crh-badge-low');
    var autoApply = _crhIsAuto(rule);
    var type = rule.finding_type || rule.rule_id || '未分类纠正规则';
    var reason = rule.last_reason || rule.reason || '尚未填写纠正原因';
    var corrections = Array.isArray(rule.corrections) ? rule.corrections : [];
    var fingerprint = String(rule.fingerprint || '');
    var shortFingerprint = fingerprint.length > 36 ?
      fingerprint.slice(0, 18) + '…' + fingerprint.slice(-12) : fingerprint;
    var history = '';

    if (corrections.length) {
      history = '<details class="crh-history"><summary>查看最近 ' + corrections.length + ' 次纠正记录</summary>' +
        corrections.slice().reverse().map(function(item) {
          var itemReason = item.reason || item.corrected || item.correct_content || '未记录说明';
          return '<div class="crh-history-item"><b>' + _crhFormatDate(item.timestamp || item.time) +
            '</b><br>' + _crhEscape(itemReason) + '</div>';
        }).join('') + '</details>';
    }

    return '<article class="crh-card">' +
      '<div class="crh-card-hd"><div class="crh-card-type">' + _crhEscape(type) + '</div>' +
      '<div><span class="crh-badge ' + (autoApply ? 'crh-badge-audit' : 'crh-badge-edit') + '">' +
      (autoApply ? '已进入自动应用' : '学习观察中') + '</span> ' +
      '<span class="crh-badge ' + confidenceClass + '">置信度 ' + confidencePct + '%</span></div></div>' +
      '<div class="crh-meta">' +
      '<span>行业：' + _crhEscape(rule.industry || '通用') + '</span>' +
      '<span>经营模式：' + _crhEscape(rule.biz_model || '通用') + '</span>' +
      '<span>累计纠正：' + Math.max(0, Number(rule.correction_count || rule.count || 0)) + ' 次</span>' +
      '<span>最近更新：' + _crhFormatDate(rule.updated_at || rule.timestamp) + '</span>' +
      '</div>' +
      '<div class="crh-reason"><b>纠正依据：</b>' + _crhEscape(reason) + '</div>' +
      (shortFingerprint ? '<div class="crh-chain">规则指纹：<span title="' +
        _crhEscape(fingerprint) + '">' + _crhEscape(shortFingerprint) + '</span></div>' : '') +
      history + '</article>';
  }).join('');
}

function filterCRH(filter) {
  var allowed = {all:true, high:true, auto:true};
  var selected = allowed[filter] ? filter : 'all';
  window._crhFilter = selected;
  var mount = document.getElementById('engine-mount-corrections') || document;
  var buttons = mount.querySelectorAll('#crh-filter .crh-filter-btn');
  buttons.forEach(function(button, index) {
    var buttonFilter = index === 1 ? 'high' : (index === 2 ? 'auto' : 'all');
    var active = buttonFilter === selected;
    button.classList.toggle('active', active);
    button.style.background = active ? '#2563eb' : '#fff';
    button.style.color = active ? '#fff' : '#475569';
    button.style.borderColor = active ? '#2563eb' : '#e2e8f0';
    button.setAttribute('aria-pressed', active ? 'true' : 'false');
  });
  renderCRHList(window._crhRules || [], selected);
}
