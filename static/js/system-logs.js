// ==================== 系统日志查看器 ====================
function renderSystemLogs(container) {
  window.currentModule = '系统日志';
  container.innerHTML = ''
    + '<div style="max-width:1200px;margin:0 auto">'
    + '<h2 style="margin-bottom:16px">📋 系统使用日志</h2>'
    + '<div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;align-items:center">'
    + '<button class="btn-toolbar" onclick="loadSystemLogs()">刷新</button>'
    + '<button class="btn-toolbar" onclick="loadSystemLogs(\'today\')">今日</button>'
    + '<button class="btn-toolbar" onclick="loadSystemLogs(\'upload\')">上传操作</button>'
    + '<button class="btn-toolbar" onclick="loadSystemLogs(\'analyze\')">分析操作</button>'
    + '<button class="btn-toolbar" onclick="clearSystemLogs()" style="color:#dc2626;border-color:#fca5a5">清空日志</button>'
    + '<span id="log-count" style="color:var(--gray-400);font-size:12px;margin-left:8px"></span>'
    + '</div>'
    + '<div id="system-logs-table" style="font-size:12px">加载中...</div>'
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
    
    var html = '<table style="width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden;border:1px solid var(--gray-200)">'
      + '<thead><tr style="background:#f8fafc;font-weight:600">'
      + '<th style="padding:8px 12px;text-align:left;border-bottom:2px solid var(--gray-200)">时间</th>'
      + '<th style="padding:8px 12px;text-align:left;border-bottom:2px solid var(--gray-200)">操作</th>'
      + '<th style="padding:8px 12px;text-align:left;border-bottom:2px solid var(--gray-200)">请求</th>'
      + '<th style="padding:8px 12px;text-align:center;border-bottom:2px solid var(--gray-200)">状态</th>'
      + '<th style="padding:8px 12px;text-align:center;border-bottom:2px solid var(--gray-200)">耗时</th>'
      + '<th style="padding:8px 12px;text-align:left;border-bottom:2px solid var(--gray-200)">IP</th>'
      + '</tr></thead><tbody>';
    
    logs.forEach(function(l) {
      var actionIcon = l.action_type === 'upload' ? '📤' : (l.action_type === 'analyze' ? '🔍' : (l.action_type === 'export' ? '📥' : (l.action_type === 'audit' ? '🛡️' : (l.action_type === 'fix' ? '🔧' : '📋'))));
      var statusColor = l.status_code >= 400 ? '#dc2626' : '#059669';
      var time = l.timestamp ? l.timestamp.substring(0,19).replace('T',' ') : '-';
      html += '<tr style="border-bottom:1px solid var(--gray-100)">'
        + '<td style="padding:6px 12px;white-space:nowrap">' + time + '</td>'
        + '<td style="padding:6px 12px">' + actionIcon + ' ' + (l.action_type || l.method || '-') + '</td>'
        + '<td style="padding:6px 12px;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + esc(l.path) + '">' + esc(l.path.replace('/api/','')) + '</td>'
        + '<td style="padding:6px 12px;text-align:center;color:' + statusColor + '">' + l.status_code + '</td>'
        + '<td style="padding:6px 12px;text-align:center">' + (l.response_time_ms || '-') + 'ms</td>'
        + '<td style="padding:6px 12px">' + esc(l.client_ip || '-') + '</td>'
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
