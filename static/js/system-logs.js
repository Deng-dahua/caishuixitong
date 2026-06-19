// ==================== 系统日志查看器 ====================
var _cachedSystemLogs = null;

function renderSystemLogs(container) {
  window.currentModule = '系统日志';

  container.innerHTML = ''
    + '<div style="max-width:960px;margin:0 auto;padding:40px 24px 80px">'
    + '  <div style="margin-bottom:32px">'
    + '    <h2 style="font-size:24px;font-weight:700;color:#0f172a;margin:0 0 6px">系统日志</h2>'
    + '    <p style="font-size:14px;color:#94a3b8;margin:0">上传、分析、导出、修复操作的完整审计追踪记录</p>'
    + '  </div>'
    + '  <div style="display:flex;gap:8px;align-items:center;margin-bottom:24px;padding-bottom:16px;border-bottom:1px solid #f1f5f9">'
    + '    <button onclick="loadSystemLogs()" style="border:none;background:transparent;font-size:13px;color:#0f172a;cursor:pointer;padding:6px 12px">刷新</button>'
    + '    <button onclick="loadSystemLogs(\'today\')" style="border:none;background:transparent;font-size:13px;color:#64748b;cursor:pointer;padding:6px 12px">今日</button>'
    + '    <button onclick="loadSystemLogs(\'upload\')" style="border:none;background:transparent;font-size:13px;color:#64748b;cursor:pointer;padding:6px 12px">上传</button>'
    + '    <button onclick="loadSystemLogs(\'analyze\')" style="border:none;background:transparent;font-size:13px;color:#64748b;cursor:pointer;padding:6px 12px">分析</button>'
    + '    <button onclick="clearSystemLogs()" style="border:none;background:transparent;font-size:13px;color:#dc2626;cursor:pointer;padding:6px 12px">清空</button>'
    + '    <span id="log-count" style="font-size:13px;color:#94a3b8;margin-left:auto"></span>'
    + '  </div>'
    + '  <div id="system-logs-table"></div>'
    + '</div>';

  // 有缓存直接渲染最终态
  if (_cachedSystemLogs) {
    renderSystemLogsTable(_cachedSystemLogs, '');
    return;
  }
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
    if (!Array.isArray(logs)) { table.innerHTML = '<div style="font-size:13px;color:#94a3b8;padding:40px 0">无日志</div>'; return; }
    if (filter === 'upload') logs = logs.filter(function(l) { return l.action_type === 'upload'; });
    if (filter === 'analyze') logs = logs.filter(function(l) { return l.action_type === 'analyze'; });

    if (!filter || filter === 'today') _cachedSystemLogs = logs;
    renderSystemLogsTable(logs, filter);
  } catch(e) {
    table.innerHTML = '<div style="font-size:13px;color:#dc2626;padding:40px 0">加载失败</div>';
  }
}

function renderSystemLogsTable(logs, filter) {
  var table = document.getElementById('system-logs-table');
  if (!table) return;
  var countEl = document.getElementById('log-count');
  if (countEl) countEl.textContent = '共 ' + logs.length + ' 条';

  var html = '<table style="width:100%;border-collapse:collapse;font-size:13px">'
    + '<thead><tr style="border-bottom:2px solid #0f172a;text-align:left">'
    + '<th style="padding:8px 12px 8px 0;font-weight:600;color:#0f172a">时间</th>'
    + '<th style="padding:8px 12px;font-weight:600;color:#0f172a">操作</th>'
    + '<th style="padding:8px 12px;font-weight:600;color:#0f172a">请求</th>'
    + '<th style="padding:8px 12px;font-weight:600;color:#0f172a;text-align:center">状态</th>'
    + '<th style="padding:8px 12px;font-weight:600;color:#0f172a;text-align:center">耗时</th>'
    + '<th style="padding:8px 12px;font-weight:600;color:#0f172a">用户</th>'
    + '<th style="padding:8px 12px;font-weight:600;color:#0f172a">IP</th>'
    + '<th style="padding:8px 0;font-weight:600;color:#0f172a">地区</th>'
    + '</tr></thead><tbody>';

  logs.forEach(function(l) {
    var actionText = l.action_type || l.method || '-';
    var statusColor = l.status_code >= 400 ? '#dc2626' : '#059669';
    var time = l.timestamp ? l.timestamp.substring(0,19).replace('T',' ') : '-';
    html += '<tr style="border-bottom:1px solid #f1f5f9">'
      + '<td style="padding:8px 12px 8px 0;white-space:nowrap;color:#64748b">' + time + '</td>'
      + '<td style="padding:8px 12px;color:#0f172a">' + actionText + '</td>'
      + '<td style="padding:8px 12px;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#64748b" title="' + esc(l.path) + '">' + esc(l.path.replace('/api/','')) + '</td>'
      + '<td style="padding:8px 12px;text-align:center;color:' + statusColor + '">' + l.status_code + '</td>'
      + '<td style="padding:8px 12px;text-align:center;color:#94a3b8">' + (l.response_time_ms || '-') + 'ms</td>'
      + '<td style="padding:8px 12px;color:#0f172a">' + (l.user_name ? esc(l.user_name) + ' <span style="color:#94a3b8">' + esc(l.user_phone || '') + '</span>' : '<span style="color:#94a3b8">-</span>') + '</td>'
      + '<td style="padding:8px 12px;color:#64748b">' + esc(l.client_ip || '-') + '</td>'
      + '<td style="padding:8px 0;color:#94a3b8">' + esc(l.location || '') + '</td>'
      + '</tr>';
  });
  html += '</tbody></table>';
  table.innerHTML = html;
}

async function clearSystemLogs() {
  if (!confirm('确定清空所有日志？此操作不可恢复。')) return;
  try {
    await fetch('/api/system-logs/clear', { method: 'POST' });
    _cachedSystemLogs = null;
    toast('日志已清空', 'success');
    loadSystemLogs();
  } catch(e) { toast('清空失败', 'error'); }
}

function esc(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
