/* -*- coding: utf-8 -*-
 * 一键稽查分析任务页（P0-4）
 *
 * ★ 契约（后端 `/api/v1`，权威 `engine/analysis_task.py`）：
 *   GET  /api/v1/analysis-jobs/meta                        → {steps, statuses, ...}
 *   POST /api/v1/projects/{pid}/analysis-jobs              → {job_id, preflight, ...}
 *   GET  /api/v1/projects/{pid}/analysis-jobs              → {total, jobs: [...]}
 *   GET  /api/v1/analysis-jobs/{id}                        → 任务详情（状态/进度/8 步）
 *   POST /api/v1/analysis-jobs/{id}/cancel                 → 取消（结果不予采用）
 *   POST /api/v1/analysis-jobs/{id}/retry                  → 重试（仅失败/已取消）
 *
 * ★ 中文名一律取后端 `/meta`（步名/状态名/触发名）——**前端不硬编码**，
 *   否则后端改名即前端失配（本项目已把"前端不得有报告名字面量"定为铁律，同理）。
 */
'use strict';

var API = '/api/v1';
var META = null;          // /meta 结果（步名/状态名/触发名的唯一来源）
var PROJECTS = [];        // 项目列表
var CURRENT = null;       // 当前任务详情
var POLL = null;          // 轮询定时器
var POLL_MS = 1500;

function el(id) { return document.getElementById(id); }
function esc(s) {
  return String(s === null || s === undefined ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function alertBox(kind, text) {
  var cls = kind === 'err' ? 'err' : (kind === 'warn' ? 'warn' : 'ok');
  el('alert').innerHTML = '<div class="msg ' + cls + '">' + esc(text) + '</div>';
  if (kind === 'ok') {
    setTimeout(function () { el('alert').innerHTML = ''; }, 6000);
  }
}

async function api(method, url, body) {
  var opt = { method: method, headers: {} };
  if (body !== undefined && body !== null) {
    opt.headers['Content-Type'] = 'application/json';
    opt.body = JSON.stringify(body);
  }
  var r = await fetch(url, opt);
  var text = await r.text();
  var data = null;
  try { data = JSON.parse(text); } catch (e) {
    throw new Error('服务器返回异常（HTTP ' + r.status + '）：' + text.slice(0, 160));
  }
  if (!r.ok) {
    var d = (data && (data.detail || data.message)) || ('HTTP ' + r.status);
    var err = new Error(typeof d === 'string' ? d : JSON.stringify(d));
    err.status = r.status; err.data = data;
    throw err;
  }
  return data;
}

function statusCn(s) {
  if (META) {
    for (var i = 0; i < META.statuses.length; i++) {
      if (META.statuses[i].value === s) { return META.statuses[i].label; }
    }
  }
  return s || '';
}

function stepCn(s) {
  if (META) {
    for (var i = 0; i < META.steps.length; i++) {
      if (META.steps[i].no === s) { return META.steps[i].name; }
    }
  }
  return '';
}

function tagHtml(st) {
  return '<span class="tag st-' + esc(st || 'PENDING') + '">' + esc(statusCn(st)) + '</span>';
}

// ── 初始化 ──────────────────────────────────────────────────────────────
async function boot() {
  try {
    META = await api('GET', API + '/analysis-jobs/meta');
  } catch (e) {
    alertBox('err', '读取任务字典失败：' + e.message);
  }
  try {
    var p = await api('GET', API + '/projects?page=1&page_size=200');
    PROJECTS = (p && p.items) || [];
  } catch (e) {
    PROJECTS = [];
  }
  var sel = el('f-project');
  sel.innerHTML = PROJECTS.length
    ? PROJECTS.map(function (x) {
        return '<option value="' + x.id + '">' + esc(x.name) + '（' + esc(x.status_cn || x.status) + '）</option>';
      }).join('')
    : '<option value="">（无项目，请先在「稽查项目」中新建）</option>';
  // ★ 2026-10-15 自动匹配项目：URL ?project=N（从项目页/资料页带参跳入）优先；
  //   否则取**最近更新的项目**（列表接口默认按 updated_at 降序 ⇒ 首项即最近活跃），
  //   不再落在任意首项；匹配结果在按钮旁明示，用户仍可手动更换。
  var autoId = 0;
  var fromUrl = Number(new URLSearchParams(location.search).get('project')) || 0;
  if (fromUrl && PROJECTS.some(function (x) { return String(x.id) === String(fromUrl); })) {
    autoId = fromUrl;
  } else if (PROJECTS.length) {
    autoId = PROJECTS[0].id;   // 列表默认按 updated_at 降序 ⇒ 首项即最近活跃
  }
  if (autoId) sel.value = String(autoId);   // ★ 自动匹配仅静默选中（2026-10-15 用户裁定：不显示提示文字）
  sel.onchange = function () { loadHistory(); };
  if (PROJECTS.length) { await loadHistory(); }
  else { el('history').innerHTML = '<tr><td colspan="11" class="empty">暂无项目</td></tr>'; }
  try {
    var me = await api('GET', '/api/auth/me');
    el('who').textContent = '当前用户：' + ((me && (me.username || me.user_name)) || '');
  } catch (e) { /* 非关键信息，取不到就不显示（不伪造） */ }
}

function currentProjectId() {
  var v = el('f-project').value;
  return v ? parseInt(v, 10) : 0;
}

// ── 发起 ────────────────────────────────────────────────────────────────
async function startAnalysis() {
  var pid = currentProjectId();
  if (!pid) { alertBox('err', '请先选择稽查项目'); return; }
  var btn = el('btn-start');
  btn.disabled = true; btn.textContent = '⏳ 启动中…';
  try {
    var r = await api('POST', API + '/projects/' + pid + '/analysis-jobs',
                      { force: !!el('f-force').checked });
    var pf = r.preflight || {};
    alertBox(r.reused ? 'warn' : 'ok',
             (r.reused ? '已有同账套任务在跑，已接管：' : '已发起：')
             + (pf.message || '') );
    await loadHistory();
    await selectJob(r.job_id);
  } catch (e) {
    alertBox('err', '发起失败：' + e.message);
  } finally {
    btn.disabled = false; btn.textContent = '▶ 开始稽查分析';
  }
}

// ── 详情渲染 ────────────────────────────────────────────────────────────
function renderCurrent(g) {
  CURRENT = g;
  el('cur-id').textContent = g.job_id ? ('作业号 ' + g.job_id) : '';
  var bar = el('bar');
  var pct = g.status === 'SUCCESS' ? 100 : Math.max(0, Math.min(g.progress || 0, 100));
  bar.style.width = pct + '%';
  bar.className = 'progress-inner'
    + (g.status === 'SUCCESS' ? ' done' : (g.status === 'FAILED' ? ' failed'
      : (g.status === 'CANCELLED' ? ' cancelled' : '')));
  el('cur-status').outerHTML = tagHtml(g.status).replace('class="tag', 'id="cur-status" class="tag');
  el('cur-step').textContent = g.current_step
    ? ('当前步骤：' + g.current_step + '. ' + (g.current_step_name || stepCn(g.current_step))) : '';
  el('cur-progress').textContent = '进度 ' + pct + '%'
    + (g.cancel_pending ? '（正在取消…）' : '')
    + (g.timed_out ? '（已超时）' : '');
  el('cur-module').textContent = (g.current_module && g.status === 'RUNNING')
    ? ('正在执行：' + g.current_module) : '';   // ★ 2026-10-15 终态不显示「正在执行」（后端同步清空）
  el('step-list').innerHTML = (g.steps || []).map(function (s) {
    return '<div class="step ' + esc(s.status) + '">'
      + '<span class="no">' + s.no + '</span>'
      + '<span><span class="t">' + esc(s.name) + '</span>'
      + '<div class="d">' + esc(s.desc || '') + '</div></span></div>';
  }).join('');
  var errHtml = '';
  if (g.error) {
    errHtml = '<div class="err-box"><b>失败原因：</b>' + esc(g.error) + '</div>';
  } else if (g.status === 'CANCELLED') {
    errHtml = '<div class="msg warn">已取消（本次结果不予采用）。可点「重试」重新分析。</div>';
  }
  el('cur-err').innerHTML = errHtml;
  el('btn-cancel').disabled = !g.can_cancel;
  el('btn-retry').disabled = !g.can_retry;
}

async function selectJob(jobId) {
  try {
    var g = await api('GET', API + '/analysis-jobs/' + jobId);
    renderCurrent(g);
    schedulePoll(jobId, g.status);
    revealCurrent(jobId);
  } catch (e) {
    alertBox('err', '读取任务失败：' + e.message);
  }
}

/* ★ 2026-10-18（用户反馈「查看按钮没有任何反应」）：真因**不是**按钮没绑定，
 *   而是「当前任务」卡片在**任务历史表格上方**——用户看的是表格里那一行，
 *   点完只有上方卡片内容变了，屏幕可见区域**什么都没动** ⇒ 主观上就是"没反应"。
 *   修法：① 行内高亮被选中的那一行（就近反馈）；② 平滑滚到「当前任务」卡片并短暂描边，
 *   让"点了→结果在哪"这件事在屏幕上可见。
 *   同时把行内 `onclick` 换成事件委托（内联 onclick 一旦被 CSP/编码问题破坏就彻底静默，
 *   委托失败至少还能报错定位）。 */
var _REVEAL_TIMER = null;
function revealCurrent(jobId) {
  var rows = document.querySelectorAll('#history tr');
  Array.prototype.forEach.call(rows, function (tr) {
    var cb = tr.querySelector('input.job-sel');
    var jid = cb ? cb.getAttribute('data-jid') : null;
    if (!jid) {
      var tds = tr.querySelectorAll('td');
      jid = tds.length > 1 ? (tds[1].textContent || '').trim().split(' ')[0] : null;
    }
    tr.classList.toggle('row-active', !!jid && jid === jobId);
  });
  var card = document.getElementById('cur-card');
  if (card && card.scrollIntoView) {
    try { card.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
    catch (e) { card.scrollIntoView(); }
    card.classList.add('flash');
    if (_REVEAL_TIMER) clearTimeout(_REVEAL_TIMER);
    _REVEAL_TIMER = setTimeout(function () { card.classList.remove('flash'); }, 1400);
  }
}

function schedulePoll(jobId, status) {
  if (POLL) { clearTimeout(POLL); POLL = null; }
  if (status === 'SUCCESS' || status === 'FAILED' || status === 'CANCELLED') { return; }
  POLL = setTimeout(async function () {
    try {
      var g = await api('GET', API + '/analysis-jobs/' + jobId);
      renderCurrent(g);
      schedulePoll(jobId, g.status);
      if (g.status !== 'RUNNING' && g.status !== 'PENDING') { await loadHistory(); }
    } catch (e) {
      // 轮询失败：停止轮询并如实提示（**不静默重试**）
      alertBox('err', '轮询中断：' + e.message);
    }
  }, POLL_MS);
}

async function refreshCurrent() {
  if (!CURRENT || !CURRENT.job_id) { alertBox('warn', '尚未选择任务'); return; }
  await selectJob(CURRENT.job_id);
}

async function cancelCurrent() {
  if (!CURRENT || !CURRENT.job_id) { return; }
  if (!window.confirm('确认取消作业 ' + CURRENT.job_id + ' ？\n取消后本次结果不予采用（可重试）。')) { return; }
  try {
    var g = await api('POST', API + '/analysis-jobs/' + CURRENT.job_id + '/cancel');
    renderCurrent(g);
    alertBox(g.cancel_accepted === false ? 'warn' : 'ok',
             g.reason || '已请求取消；引擎线程会自然收尾，本次结果不予采用');
    await loadHistory();
  } catch (e) {
    alertBox('err', '取消失败：' + e.message);
  }
}

async function retryCurrent() {
  if (!CURRENT || !CURRENT.job_id) { return; }
  try {
    var r = await api('POST', API + '/analysis-jobs/' + CURRENT.job_id + '/retry');
    alertBox('ok', '已重试：新作业 ' + r.job_id + '（原作业 ' + (r.retry_of || '') + '）');
    await loadHistory();
    await selectJob(r.job_id);
  } catch (e) {
    alertBox('err', '重试失败：' + e.message);
  }
}

// ── 历史 ────────────────────────────────────────────────────────────────
function fmtDur(ms) {
  if (ms === null || ms === undefined) { return '—'; }
  var s = Math.round(ms / 1000);
  if (s < 60) { return s + ' 秒'; }
  return Math.floor(s / 60) + ' 分 ' + (s % 60) + ' 秒';
}

function fmtTime(t) {
  if (!t) { return '—'; }
  return String(t).replace('T', ' ').slice(0, 19);
}

var PICKED_JOBS = {};   // ★ 2026-10-15 批量删除：job_id -> true（切换项目/刷新即清空）
var _DELETABLE = { SUCCESS: 1, FAILED: 1, CANCELLED: 1, BLOCKED: 1 };   // 终态才可删
async function loadHistory() {
  var pid = currentProjectId();
  if (!pid) { el('history').innerHTML = '<tr><td colspan="11" class="empty">请选择项目</td></tr>'; return; }
  PICKED_JOBS = {};   // 切换项目/刷新即清空
  try {
    var r = await api('GET', API + '/projects/' + pid + '/analysis-jobs?limit=50');
    if (!r.jobs || !r.jobs.length) {
      el('history').innerHTML = '<tr><td colspan="11" class="empty">该项目暂无分析任务</td></tr>';
      _syncDelBtn();
      return;
    }
    el('history').innerHTML = r.jobs.map(function (j) {
      var ops = '<a href="javascript:void(0)" class="job-view" data-jid="'
        + esc(j.job_id) + '">查看</a>';
      if (j.can_retry) {
        ops += ' · <a href="javascript:void(0)" onclick="retryById(\'' + esc(j.job_id) + '\')">重试</a>';
      }
      var delable = _DELETABLE[j.status] && !j.cancel_pending;
      return '<tr><td style="text-align:center">'
        + (delable
           ? '<input type="checkbox" class="job-sel" data-jid="' + esc(j.job_id) + '"'
             + (PICKED_JOBS[j.job_id] ? ' checked' : '') + '>'
           : '<span class="muted" title="运行中任务须先取消才能删除">—</span>')
        + '</td><td>' + esc(j.job_id) + (j.retry_of ? ' <span class="muted">(重试)</span>' : '') + '</td>'
        + '<td>' + tagHtml(j.status) + (j.cancel_pending ? ' <span class="muted">收尾中</span>' : '') + '</td>'
        + '<td>' + esc(j.trigger_cn || j.trigger || '—') + '</td>'
        + '<td>' + (j.progress || 0) + '%</td>'
        + '<td>' + esc(fmtTime(j.started_at)) + '</td>'
        + '<td>' + esc(fmtDur(j.duration_ms)) + '</td>'
        + '<td>' + (j.findings_count === null || j.findings_count === undefined ? '—' : j.findings_count) + '</td>'
        + '<td>' + esc(j.overall_level || '—') + '</td>'
        + '<td>' + esc(j.report_doc_no || '—') + '</td>'
        + '<td>' + ops + '</td></tr>';
    }).join('');
  } catch (e) {
    _syncDelBtn();
    el('history').innerHTML = '<tr><td colspan="11" class="empty">加载失败：' + esc(e.message) + '</td></tr>';
  }
}

async function retryById(jobId) {
  try {
    var r = await api('POST', API + '/analysis-jobs/' + jobId + '/retry');
    alertBox('ok', '已重试：新作业 ' + r.job_id);
    await loadHistory();
    await selectJob(r.job_id);
  } catch (e) {
    alertBox('err', '重试失败：' + e.message);
  }
}

window.addEventListener('beforeunload', function () { if (POLL) { clearTimeout(POLL); } });
boot();

// ★ 2026-10-15 批量删除：选择同步 / 删除按钮 / 逐条删除（权威出口 DELETE /analysis-jobs/{id}）
function _syncDelBtn() {
  var btn = el('btn-del-jobs');
  if (!btn) return;
  var n = Object.keys(PICKED_JOBS).length;
  btn.hidden = n === 0;
  btn.textContent = '\uD83D\uDDD1 删除选中（' + n + '）';
}
window.__delSelectedJobs = async function () {
  var ids = Object.keys(PICKED_JOBS);
  if (!ids.length) return;
  if (!window.confirm('确定删除选中的 ' + ids.length + ' 条分析任务记录？只删任务历史记录；分析结果与报告不受影响。')) return;
  var okN = 0, errs = [];
  for (var i = 0; i < ids.length; i++) {
    try {
      await api('DELETE', API + '/analysis-jobs/' + ids[i]);
      okN++;
      if (CURRENT && CURRENT.job_id === ids[i]) { CURRENT = null; el('cur-id').textContent = ''; }
    } catch (e) {
      errs.push(ids[i] + '：' + e.message);
    }
  }
  PICKED_JOBS = {};
  alertBox(errs.length ? 'err' : 'ok',
    '已删除 ' + okN + ' 条任务记录' + (errs.length ? ('；失败 ' + errs.length + ' 条：' + errs.join('；')) : ''));
  await loadHistory();
};
(function bindJobView() {
  var tb = el('history');
  if (tb) tb.addEventListener('click', function (e) {
    var a = e.target && e.target.closest ? e.target.closest('a.job-view') : null;
    if (!a) return;
    e.preventDefault();
    var jid = a.getAttribute('data-jid');
    if (!jid) return;
    selectJob(jid);
  });
})();

(function bindJobDel() {
  var tb = el('history');
  if (tb) tb.addEventListener('change', function (e) {
    var t = e.target;
    if (t && t.classList && t.classList.contains('job-sel')) {
      var jid = t.getAttribute('data-jid');
      if (t.checked) PICKED_JOBS[jid] = true; else delete PICKED_JOBS[jid];
      _syncDelBtn();
    }
  });
  var ja = document.getElementById('job-sel-all');
  if (ja) ja.addEventListener('change', function () {
    PICKED_JOBS = {};
    document.querySelectorAll('#history input.job-sel').forEach(function (cb) {
      cb.checked = ja.checked;
      if (ja.checked) PICKED_JOBS[cb.getAttribute('data-jid')] = true;
    });
    _syncDelBtn();
  });
})();
