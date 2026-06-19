// ==================== 系统日志查看器 ====================
function renderSystemLogs(container) {
  window.currentModule = '系统日志';
  container.innerHTML = ''
    + '<div class="pipeline-page">'
    + '<div class="pipeline-header">'
    + '<h2 class="pipeline-title">📋 系统使用日志</h2>'
    + '<p class="pipeline-subtitle">上传、分析、导出、修复操作的完整审计追踪记录</p>'
    + '</div>'
    + '<div class="pipeline-body">'
    + '<div class="pipeline-filter-bar">'
    + '<button class="pipeline-btn pipeline-btn-secondary" onclick="loadSystemLogs()">🔄 刷新</button>'
    + '<button class="pipeline-btn pipeline-btn-secondary" onclick="loadSystemLogs(\'today\')">📅 今日</button>'
    + '<button class="pipeline-btn pipeline-btn-secondary" onclick="loadSystemLogs(\'upload\')">📤 上传操作</button>'
    + '<button class="pipeline-btn pipeline-btn-secondary" onclick="loadSystemLogs(\'analyze\')">🔍 分析操作</button>'
    + '<button class="pipeline-btn pipeline-btn-danger" onclick="clearSystemLogs()">🗑 清空日志</button>'
    + '<span id="log-count" class="pipeline-badge pipeline-badge-gray"></span>'
    + '</div>'
    + '<div id="system-logs-table" class="pipeline-loading">加载中...</div>'
    + '</div>'
    + '</div>';
  loadSystemLogs();
}

async function loadSystemLogs(filter) {
  var url = '/api/system-logs?limit=500';
  if (filter === 'today') url += '&today=1';
  var table = document.getElementById('system-logs-table');
  if (!table) return;
  try {
    var resp = await fetch(url + (typeof currentCompanyId !== 'undefined' ? '&company_id=' + currentCompanyId : ''));
    var logs = await resp.json();
    if (!Array.isArray(logs)) { table.innerHTML = '<p>无日志</p>'; return; }
    if (filter === 'upload') logs = logs.filter(function(l) { return l.action_type === 'upload'; });
    if (filter === 'analyze') logs = logs.filter(function(l) { return l.action_type === 'analyze'; });
    
    document.getElementById('log-count').textContent = '共 ' + logs.length + ' 条';
    
    var html = '<table class="pipeline-table" style="font-size:11px">'
      + '<thead><tr>'
      + '<th>时间</th>'
      + '<th>操作</th>'
      + '<th>请求</th>'
      + '<th style="text-align:center">状态</th>'
      + '<th style="text-align:center">耗时</th>'
      + '<th>用户</th>'
      + '<th>IP</th>'
      + '<th>地区</th>'
      + '</tr></thead><tbody>';
    
    logs.forEach(function(l) {
      var actionIcon = l.action_type === 'upload' ? '📤' : (l.action_type === 'analyze' ? '🔍' : (l.action_type === 'export' ? '📥' : (l.action_type === 'audit' ? '🛡️' : (l.action_type === 'fix' ? '🔧' : '📋'))));
      var statusColor = l.status_code >= 400 ? '#dc2626' : '#059669';
      var time = l.timestamp ? l.timestamp.substring(0,19).replace('T',' ') : '-';
      html += '<tr>'
        + '<td style="white-space:nowrap">' + time + '</td>'
        + '<td>' + actionIcon + ' ' + (l.action_type || l.method || '-') + '</td>'
        + '<td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + esc(l.path) + '">' + esc(l.path.replace('/api/','')) + '</td>'
        + '<td style="text-align:center;color:' + statusColor + '">' + l.status_code + '</td>'
        + '<td style="text-align:center">' + (l.response_time_ms || '-') + 'ms</td>'
        + '<td style="font-weight:500">' + (l.user_name ? esc(l.user_name) + ' <span style="color:#94a3b8;font-weight:400">' + esc(l.user_phone || '') + '</span>' : '<span style="color:#94a3b8">-</span>') + '</td>'
        + '<td>' + esc(l.client_ip || '-') + '</td>'
        + '<td style="color:#64748b">' + esc(l.location || '') + '</td>'
        + '</tr>';
    });
    html += '</tbody></table>';
    table.innerHTML = html;
  } catch(e) {
    table.innerHTML = '<p style="color:#dc2626">加载失败</p>';
  }
}

async function clearSystemLogs() {
  if (!confirm('确定清空所有日志？此操作不可恢复。')) return;
  try {
    await fetch('/api/system-logs/clear', { method: 'POST' });
    toast('日志已清空', 'success');
    loadSystemLogs();
  } catch(e) { toast('清空失败', 'error'); }
}
