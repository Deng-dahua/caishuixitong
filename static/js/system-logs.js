// ==================== 系统日志查看器 ====================
var _cachedSystemLogs = null;

function renderSystemLogs(container) {
  window.currentModule = '系统日志';

  container.innerHTML = `
    <style>
      .log-shell{
        max-width:1680px;
        margin:0 auto;
        padding:36px 8px 56px;
        box-sizing:border-box;
        color:#405166;
        background:#f5f7fa;
        font-family:"Microsoft YaHei UI","Microsoft YaHei","PingFang SC",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
        font-size:14px;
        line-height:1.75
      }
      .log-shell *{box-sizing:border-box}
      .log-hero{position:relative;overflow:hidden;margin-bottom:24px;padding:40px 44px 37px;border-radius:16px;color:#fff;background:linear-gradient(135deg,#17273c 0%,#29455f 72%,#405468 100%);box-shadow:0 14px 32px rgba(20,34,52,.14)}
      .log-kicker{display:inline-block;margin-bottom:13px;padding:6px 11px;border:1px solid rgba(255,255,255,.2);border-radius:5px;color:#d8e4ee;background:rgba(255,255,255,.07);font-size:12px;font-weight:750;letter-spacing:.08em}
      .log-hero h1{margin:0 0 12px;color:#fff;font-size:31px;line-height:1.3;font-weight:750}
      .log-hero p{max-width:1000px;margin:0;color:#d9e3ec;font-size:14px;line-height:1.95}
      .log-panel{border:1px solid #dce4ed;border-radius:12px;background:#fff;overflow:hidden;box-shadow:0 5px 16px rgba(20,34,52,.04)}
      .log-toolbar{display:flex;align-items:center;gap:9px;min-height:70px;padding:14px 18px;border-bottom:1px solid #dfe6ee;background:#f8fafc;flex-wrap:wrap}
      .log-filter{padding:9px 14px;border:1px solid #d6dee8;border-radius:7px;color:#52647a;background:#fff;font-size:13px;font-weight:650;cursor:pointer;transition:.15s}
      .log-filter:hover,.log-filter.active{border-color:#345f81;color:#fff;background:#345f81}
      .log-refresh{color:#245f88}
      .log-clear{margin-left:4px;border-color:#ebc9cc;color:#9f3037;background:#fff}
      .log-clear:hover{border-color:#9f3037;color:#fff;background:#9f3037}
      .log-count{margin-left:auto;padding:7px 11px;border-radius:999px;color:#52647a;background:#e9eef3;font-size:12px;font-weight:700}
      .log-table-scroll{width:100%;overflow:auto}
      .log-table{width:100%;min-width:1200px;border-collapse:collapse;table-layout:fixed;font-size:13px}
      .log-table th{position:sticky;top:0;z-index:1;padding:13px 12px;border-bottom:1px solid #cfd9e5;color:#273a50;background:#f5f7fa;font-size:12px;font-weight:750;line-height:1.45;text-align:left;white-space:nowrap}
      .log-table td{padding:12px;border-bottom:1px solid #edf1f5;color:#52647a;line-height:1.6;vertical-align:top}
      .log-table tbody tr:hover{background:#f8fafc}
      .log-time,.log-status,.log-duration,.log-ip{white-space:nowrap}
      .log-operation{color:#20354c!important;font-weight:700}
      .log-request,.log-company{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      .log-company{color:#263a50!important;font-weight:650}
      .log-status{text-align:center}
      .log-status span{display:inline-flex;min-width:48px;justify-content:center;padding:3px 8px;border-radius:999px;font-size:11px;font-weight:750}
      .log-status-ok{color:#116149;background:#e9f6f1}
      .log-status-error{color:#a52f38;background:#fbecee}
      .log-duration{text-align:center;color:#7a8798!important}
      .log-empty{padding:54px 24px;color:#718095;text-align:center;font-size:13px;line-height:1.8}
      @media(max-width:760px){.log-shell{padding:14px 4px 34px}.log-hero{padding:29px 23px}.log-hero h1{font-size:25px}.log-toolbar{padding:12px}.log-count{width:100%;margin-left:0;text-align:center}}
    </style>
    <div class="log-shell">
      <header class="log-hero">
        <div class="log-kicker">操作留痕 · 责任追踪 · 异常定位</div>
        <h1>📋 系统日志</h1>
        <p>集中记录上传、分析、导出、修复及接口访问情况，为故障定位、安全审计和责任复核提供可追踪的运行依据。</p>
      </header>
      <section class="log-panel">
        <div class="log-toolbar" aria-label="日志筛选">
          <button class="log-filter log-refresh active" data-log-filter="all" onclick="loadSystemLogs('all')">全部记录</button>
          <button class="log-filter" data-log-filter="today" onclick="loadSystemLogs('today')">今日</button>
          <button class="log-filter" data-log-filter="upload" onclick="loadSystemLogs('upload')">上传操作</button>
          <button class="log-filter" data-log-filter="analyze" onclick="loadSystemLogs('analyze')">分析操作</button>
          <button class="log-filter log-clear" onclick="clearSystemLogs()">清空日志</button>
          <span id="log-count" class="log-count">正在统计…</span>
        </div>
        <div id="system-logs-table"><div class="log-empty">正在读取系统审计记录…</div></div>
      </section>
    </div>`;

  // 有缓存直接渲染最终态
  if (_cachedSystemLogs) {
    renderSystemLogsTable(_cachedSystemLogs, 'all');
    return;
  }
  loadSystemLogs('all');
}

async function loadSystemLogs(filter) {
  filter = filter || 'all';
  var url = '/api/system-logs?limit=500';
  if (filter === 'today') url += '&today=1';
  var table = document.getElementById('system-logs-table');
  if (!table) return;
  try {
    var resp = await fetch(url + (typeof currentCompanyId !== 'undefined' ? '&company_id=' + currentCompanyId : ''));
    var logs = await resp.json();
    if (!Array.isArray(logs)) { table.innerHTML = '<div class="log-empty">当前没有可显示的日志记录。</div>'; return; }
    if (filter === 'upload') logs = logs.filter(function(l) { return l.action_type === 'upload'; });
    if (filter === 'analyze') logs = logs.filter(function(l) { return l.action_type === 'analyze'; });

    if (filter === 'all') _cachedSystemLogs = logs;
    document.querySelectorAll('[data-log-filter]').forEach(function(button) {
      button.classList.toggle('active', button.getAttribute('data-log-filter') === filter);
    });
    renderSystemLogsTable(logs, filter);
  } catch(e) {
    table.innerHTML = '<div class="log-empty" style="color:#b91c1c">日志读取失败，请稍后刷新重试。</div>';
  }
}

function renderSystemLogsTable(logs, filter) {
  var table = document.getElementById('system-logs-table');
  if (!table) return;
  var countEl = document.getElementById('log-count');
  if (countEl) countEl.textContent = '共 ' + logs.length + ' 条';

  if (!logs.length) {
    table.innerHTML = '<div class="log-empty">当前筛选条件下没有日志记录。</div>';
    return;
  }

  var html = '<div class="log-table-scroll"><table class="log-table">'
    + '<colgroup><col style="width:15%"><col style="width:10%"><col style="width:19%"><col style="width:14%"><col style="width:7%"><col style="width:8%"><col style="width:12%"><col style="width:9%"><col style="width:6%"></colgroup>'
    + '<thead><tr>'
    + '<th>时间</th>'
    + '<th>操作</th>'
    + '<th>请求</th>'
    + '<th>公司</th>'
    + '<th style="text-align:center">状态</th>'
    + '<th style="text-align:center">耗时</th>'
    + '<th>用户</th>'
    + '<th>IP</th>'
    + '<th>地区</th>'
    + '</tr></thead><tbody>';

  logs.forEach(function(l) {
    var actionText = l.action_type || l.method || '-';
    var isError = Number(l.status_code || 0) >= 400;
    var time = l.timestamp ? l.timestamp.substring(0,19).replace('T',' ') : '-';
    var requestPath = String(l.path || '');
    html += '<tr>'
      + '<td class="log-time">' + escLog(time) + '</td>'
      + '<td class="log-operation">' + escLog(actionText) + '</td>'
      + '<td class="log-request" title="' + escLog(requestPath) + '">' + escLog(requestPath.replace('/api/','') || '-') + '</td>'
      + '<td class="log-company" title="' + escLog(l.company_name || '') + '">' + (l.company_name ? escLog(l.company_name) : '<span style="color:#94a3b8">-</span>') + '</td>'
      + '<td class="log-status"><span class="' + (isError ? 'log-status-error' : 'log-status-ok') + '">' + escLog(String(l.status_code || '-')) + '</span></td>'
      + '<td class="log-duration">' + (l.response_time_ms == null ? '-' : escLog(String(l.response_time_ms)) + ' ms') + '</td>'
      + '<td>' + (l.user_name ? escLog(l.user_name) + (l.user_phone ? '<br><span style="color:#8794a5;font-size:11px">' + escLog(l.user_phone) + '</span>' : '') : '<span style="color:#94a3b8">-</span>') + '</td>'
      + '<td class="log-ip">' + escLog(l.client_ip || '-') + '</td>'
      + '<td>' + escLog(l.location || '-') + '</td>'
      + '</tr>';
  });
  html += '</tbody></table></div>';
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

function escLog(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
