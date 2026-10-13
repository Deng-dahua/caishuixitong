/* -*- coding: utf-8 -*-
 * 报告生成与导出页（P0-7）
 *
 * ★ 契约（后端 `/api/v1`，权威 `engine/report_service.py` / `report_views.py`）：
 *   GET  /api/v1/reports/meta                          → {views, formats, sections, ...}
 *   POST /api/v1/projects/{pid}/reports                 {view, formats, reviewed, ...}
 *   GET  /api/v1/reports?project_id=&view=&page=
 *   GET  /api/v1/reports/{reportId}                     （归档号 = doc_no）
 *   GET  /api/v1/reports/{reportId}/download?format=pdf|docx|xlsx|html
 *   GET  /api/v1/reports/versions?company_id=
 *
 * ★ 中文名一律取后端（`/reports/meta`）——前端**不硬编码**视图/格式名。
 * ★ 下载一律走**已落盘原件**（不触发重新生成 ⇒ 不产生新版本）。
 * ★ 预览用 iframe 打开 html 下载 URL（同源，带 cookie）。
 */
'use strict';

var API = '/api/v1';
var META = null, PROJECTS = [], PID = null, CID = null, VIEW = 'full';
var TABS = ['gen', 'history', 'versions'];

function el(id) { return document.getElementById(id); }
function esc(s) {
  return String(s === null || s === undefined ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
function alertBox(kind, text) {
  var cls = kind === 'err' ? 'err' : (kind === 'warn' ? 'warn' : 'ok');
  el('alert').innerHTML = '<div class="msg ' + cls + '">' + esc(text) + '</div>';
  if (kind === 'ok') { setTimeout(function () { el('alert').innerHTML = ''; }, 8000); }
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
    throw new Error(typeof d === 'string' ? d : JSON.stringify(d));
  }
  return data;
}
function fmtSize(n) {
  var v = Number(n);
  if (!isFinite(v)) { return '—'; }
  if (v > 1048576) { return (v / 1048576).toFixed(2) + ' MB'; }
  if (v > 1024) { return (v / 1024).toFixed(1) + ' KB'; }
  return v + ' B';
}

/* ─────────────────── 引导 ─────────────────── */
async function boot() {
  try { META = await api('GET', API + '/reports/meta'); }
  catch (e) { alertBox('err', '字典加载失败：' + e.message); return; }
  renderViewCards();
  renderFormatBox();
  var sel = el('f-listview');
  (META.views || []).forEach(function (v) {
    sel.innerHTML += '<option value="' + esc(v.value) + '">' + esc(v.label) + '</option>';
  });
  var pl = await api('GET', API + '/projects?page=1&page_size=200');
  PROJECTS = pl.items || pl.projects || [];
  el('project').innerHTML = PROJECTS.length
    ? PROJECTS.map(function (p) {
        return '<option value="' + p.id + '">' + esc(p.name) + '（' + esc(p.code || '') + '）</option>';
      }).join('')
    : '<option value="">（暂无稽查项目，请先在"稽查项目"页新建）</option>';
  if (PROJECTS.length) { PID = String(PROJECTS[0].id); }
  try {
    var me = await fetch('/api/auth/me');
    if (me.ok) { var d = await me.json(); el('who').textContent = d.username || d.user_name || ''; }
  } catch (e) { /* 非关键 */ }
  if (PID) { await refreshAll(); }
}

function renderViewCards() {
  el('view-cards').innerHTML = (META.views || []).map(function (v) {
    return '<div class="vcard' + (v.value === VIEW ? ' on' : '') + '" data-view="' + esc(v.value) + '">'
      + '<div class="vt">' + esc(v.label) + '</div>'
      + '<div class="vn">' + esc(v.name) + '</div>'
      + '<div class="vd">' + esc(v.desc) + '</div>'
      + '<div class="vc">含 ' + (v.sections || []).length + ' 章'
      + ((v.omitted_sections || []).length
          ? '；未含：' + (v.omitted_sections || []).map(function (x) { return esc(x.label); }).join('、')
          : '')
      + (v.item_limit ? '；每节≤' + v.item_limit + ' 条' : '') + '</div></div>';
  }).join('');
  var cur = (META.views || []).filter(function (v) { return v.value === VIEW; })[0] || {};
  el('view-note').innerHTML = '当前视图：<b>' + esc(cur.label || '')
    + '</b>　报告名：' + esc(cur.name || '')
    + '　（名称唯一权威 <code>engine/report_compliance.document_meta</code>）';
  Array.prototype.forEach.call(el('view-cards').querySelectorAll('.vcard'), function (c) {
    c.onclick = function () {
      VIEW = c.getAttribute('data-view');
      Array.prototype.forEach.call(el('view-cards').querySelectorAll('.vcard'), function (x) {
        x.classList.toggle('on', x === c);
      });
      var m = (META.views || []).filter(function (v) { return v.value === VIEW; })[0] || {};
      el('view-note').innerHTML = '当前视图：<b>' + esc(m.label || '') + '</b>　报告名：'
        + esc(m.name || '') + '　（名称唯一权威 <code>engine/report_compliance.document_meta</code>）';
    };
  });
}
function renderFormatBox() {
  el('fmt-box').innerHTML = (META.formats || []).map(function (f) {
    return '<label class="chk"><input type="checkbox" class="fmt" value="' + esc(f.value)
      + '" checked>' + esc(f.label) + '<span class="muted">（水印：' + esc(f.watermark_method) + '）</span></label>';
  }).join('') + '<button class="btn ghost sm" id="btn-allfmt">全选</button>'
    + '<button class="btn ghost sm" id="btn-noffmt">全不选</button>';
  el('btn-allfmt').onclick = function () { setFmt(true); };
  el('btn-noffmt').onclick = function () { setFmt(false); };
}
function setFmt(v) {
  Array.prototype.forEach.call(document.querySelectorAll('.fmt'), function (c) { c.checked = v; });
}
function chosenFormats() {
  return Array.prototype.filter.call(document.querySelectorAll('.fmt'), function (c) { return c.checked; })
    .map(function (c) { return c.value; });
}

/* ─────────────────── 生成 ─────────────────── */
async function doGenerate() {
  if (!PID) { alertBox('err', '请先选择稽查项目。'); return; }
  var fmts = chosenFormats();
  if (!fmts.length) { alertBox('err', '请至少选择一种导出格式。'); return; }
  var rv = el('f-reviewed').value;
  el('btn-generate').disabled = true;
  el('gen-bar').style.width = '18%';
  el('gen-status').textContent = '正在生成（渲染 + 落盘 + 登记版本）…';
  var t0 = Date.now();
  try {
    el('gen-bar').style.width = '60%';
    var out = await api('POST', API + '/projects/' + PID + '/reports', {
      view: VIEW, formats: fmts,
      reviewed: rv === '' ? null : (rv === '1'),
      reviewed_by: el('f-reviewer').value || '',
      change_note: el('f-note').value || ''
    });
    el('gen-bar').style.width = '100%';
    el('gen-status').textContent = '';
    alertBox('ok', out.message || '报告已生成');
    renderResult(out, Date.now() - t0);
    await loadList();
    await loadVersions();
  } catch (e) {
    el('gen-bar').style.width = '100%';
    el('gen-bar').style.background = '#dc2626';
    el('gen-status').textContent = '';
    alertBox('err', '生成失败：' + e.message);
  } finally {
    el('btn-generate').disabled = false;
    setTimeout(function () {
      el('gen-bar').style.width = '0';
      el('gen-bar').style.background = '#3b82f6';
    }, 1500);
  }
}

function renderResult(out, ms) {
  el('result-card').style.display = '';
  var files = out.files || {};
  var rows = (META.formats || []).filter(function (f) { return files[f.value]; })
    .map(function (f) {
      return '<tr><td>' + esc(f.label) + '</td>'
        + '<td class="wrap muted">' + esc(String(files[f.value]).split('/').pop()) + '</td>'
        + '<td>' + fmtSize((out.bytes || {})[f.value]) + '</td>'
        + '<td>' + esc(f.watermark_method) + '</td>'
        + '<td><button class="btn sm" data-dl="' + esc(out.doc_no) + '" data-fmt="' + esc(f.value)
        + '">下载</button> '
        + (f.value === 'html'
            ? '<button class="btn sm ghost" data-prev="' + esc(out.doc_no) + '">预览</button>' : '')
        + '</td></tr>';
    }).join('');
  el('result-body').innerHTML =
    '<div class="kv">'
    + '<div class="k">报告名称</div><div>' + esc(out.name) + '</div>'
    + '<div class="k">文书编号</div><div><code>' + esc(out.doc_no) + '</code></div>'
    + '<div class="k">版本</div><div>' + esc(out.version) + '</div>'
    + '<div class="k">视图</div><div>' + esc(out.view_label) + '</div>'
    + '<div class="k">人工复核标识</div><div>'
      + (out.reviewed ? '<span class="tag t-ok">已复核</span>' : '<span class="tag t-warn">未经人工复核</span>')
      + '</div>'
    + '<div class="k">章节 / 风险项 / 税种</div><div>' + esc(out.section_count) + ' / '
      + esc(out.finding_count) + ' / ' + esc(out.tax_count) + '</div>'
    + '<div class="k">生成耗时</div><div>' + esc(out.elapsed_seconds) + ' 秒（前端计时 '
      + (ms / 1000).toFixed(2) + ' 秒；验收要求 < 180 秒）</div>'
    + '<div class="k">未含章节</div><div>'
      + ((out.omitted_sections || []).length
          ? (out.omitted_sections || []).map(function (x) { return esc(x.title); }).join('、')
            + '<span class="muted">（已在报告内如实标注）</span>'
          : '<span class="muted">无（本视图含全部章节）</span>')
      + '</div></div>'
    + '<table class="grid" style="margin-top:10px"><thead><tr><th>格式</th><th>文件名</th>'
    + '<th>大小</th><th>水印方式</th><th>操作</th></tr></thead><tbody>' + rows + '</tbody></table>';
  bindDownloadButtons(el('result-body'));
}

function bindDownloadButtons(root) {
  Array.prototype.forEach.call(root.querySelectorAll('[data-dl]'), function (b) {
    b.onclick = function () {
      var url = API + '/reports/' + encodeURIComponent(b.getAttribute('data-dl'))
        + '/download?format=' + b.getAttribute('data-fmt');
      window.location.href = url;
    };
  });
  Array.prototype.forEach.call(root.querySelectorAll('[data-prev]'), function (b) {
    b.onclick = function () {
      openPreview(b.getAttribute('data-prev'));
    };
  });
}

/* ─────────────────── 列表 / 版本台账 ─────────────────── */
async function loadList() {
  if (!PID) { return; }
  el('tb-reports').innerHTML = '<tr><td colspan="10" class="muted">加载中…</td></tr>';
  var q = 'project_id=' + PID + '&page=1&page_size=100';
  var v = el('f-listview').value;
  if (v) { q += '&view=' + encodeURIComponent(v); }
  var j;
  try { j = await api('GET', API + '/reports?' + q); }
  catch (e) {
    el('tb-reports').innerHTML = '<tr><td colspan="10" class="muted">' + esc(e.message) + '</td></tr>';
    return;
  }
  el('list-hint').textContent = '共 ' + j.total + ' 份（本页展示 ' + j.items.length + ' 份）；'
    + '文书编号/版本以版本台账为唯一权威';
  el('tb-reports').innerHTML = j.items.map(function (x) {
    var fmts = (x.formats_cn || []).map(function (f) { return esc(f); }).join(' / ');
    return '<tr><td><code>' + esc(x.doc_no) + '</code></td><td>' + esc(x.version) + '</td>'
      + '<td class="wrap">' + esc(x.name) + '</td><td>' + esc(x.view_label) + '</td>'
      + '<td>' + fmts + '</td>'
      + '<td>' + (x.reviewed ? '<span class="tag t-ok">已复核</span>'
                            : '<span class="tag t-warn">未复核</span>') + '</td>'
      + '<td>' + esc(x.finding_count) + '</td>'
      + '<td>' + esc((x.generated_at || '').slice(0, 19)) + '</td>'
      + '<td>' + esc(x.generated_by) + '</td>'
      + '<td><button class="btn sm ghost" data-open="' + esc(x.doc_no) + '">详情</button></td></tr>';
  }).join('') || '<tr><td colspan="10" class="muted">该项目尚无报告</td></tr>';
}

async function loadVersions() {
  var cid = CID;
  if (!cid && PID) {
    try { var p = await api('GET', API + '/projects/' + PID); cid = p.company_id; CID = cid; }
    catch (e) { /* 忽略 */ }
  }
  if (!cid) { return; }
  var j;
  try { j = await api('GET', API + '/reports/versions?company_id=' + cid); }
  catch (e) {
    el('tb-versions').innerHTML = '<tr><td colspan="8" class="muted">' + esc(e.message) + '</td></tr>';
    return;
  }
  el('tb-versions').innerHTML = (j.items || []).map(function (x) {
    return '<tr><td><code>' + esc(x.doc_no) + '</code></td><td>' + esc(x.version) + '</td>'
      + '<td class="wrap">' + esc(x.doc_name) + '</td><td>' + esc(x.edition_kind) + '</td>'
      + '<td>' + (x.reviewed ? '<span class="tag t-ok">已复核</span>'
                             : '<span class="tag t-mute">未复核</span>') + '</td>'
      + '<td>' + esc((x.generated_at || '').slice(0, 19)) + '</td>'
      + '<td>' + esc(x.analysis_id || '—') + '</td>'
      + '<td class="wrap muted">' + esc(x.change_note || '') + '</td></tr>';
  }).join('') || '<tr><td colspan="8" class="muted">该账套尚无版本记录</td></tr>';
}

/* ─────────────────── 详情 / 预览 ─────────────────── */
async function openDetail(docNo) {
  el('d-body').innerHTML = '<div class="muted">加载中…</div>';
  el('drawer').classList.add('open'); el('mask').classList.add('open');
  var j;
  try { j = await api('GET', API + '/reports/' + encodeURIComponent(docNo)); }
  catch (e) { el('d-body').innerHTML = '<div class="msg err">' + esc(e.message) + '</div>'; return; }
  el('d-title').textContent = '报告详情：' + (j.name || '');
  var H = [];
  H.push('<div class="card"><h3>登记信息</h3><div class="kv">');
  H.push(kv('报告名称', esc(j.name)));
  H.push(kv('文书编号', '<code>' + esc(j.doc_no) + '</code>'));
  H.push(kv('版本', esc(j.version) + (j.version_in_ledger
      ? ' <span class="tag t-ok">台账已核对</span>'
      : ' <span class="tag t-warn">台账未找到（如实标示）</span>')));
  H.push(kv('视图', esc(j.view_label)));
  H.push(kv('人工复核标识', j.reviewed
      ? '<span class="tag t-ok">已复核</span>' + (j.reviewed_by ? '（' + esc(j.reviewed_by) + '）' : '')
      : '<span class="tag t-warn">未经人工复核</span>'));
  H.push(kv('期间', esc((j.period_start || '—') + ' ~ ' + (j.period_end || '—'))));
  H.push(kv('章节 / 风险项 / 税种', esc(j.section_count) + ' / ' + esc(j.finding_count) + ' / ' + esc(j.tax_count)));
  H.push(kv('水印方式', esc(j.watermark_mode || '')));
  H.push(kv('水印文字', esc(j.watermark_text || '')));
  H.push(kv('生成时间 / 人', esc(j.generated_at) + '　' + esc(j.generated_by)));
  H.push(kv('分析作业', esc(j.analysis_id || '—')));
  H.push('<div class="k">未含章节</div><div>'
    + ((j.omitted_sections || []).length ? esc((j.omitted_sections || []).join('、'))
                                          : '<span class="muted">无</span>') + '</div>');
  H.push('</div></div>');

  H.push('<div class="card"><h3>下载 <span class="hint">取已落盘原件（不重新生成 ⇒ 不改版本）</span></h3>');
  H.push('<div class="toolbar">');
  (j.available_formats || []).forEach(function (f) {
    var lbl = ((META.formats || []).filter(function (x) { return x.value === f; })[0] || {}).label || f;
    H.push('<button class="btn" data-dl2="' + esc(j.doc_no) + '" data-fmt="' + esc(f) + '">下载 '
      + esc(lbl) + '</button>');
  });
  if ((j.available_formats || []).indexOf('html') >= 0) {
    H.push('<button class="btn ghost" data-prev2="' + esc(j.doc_no) + '">在页内预览（HTML）</button>');
  }
  H.push('</div><div id="preview-box" style="margin-top:10px"></div></div>');

  H.push('<div class="card"><h3>版本台账回读 <span class="hint">唯一权威 data/report_versions.jsonl</span></h3>');
  var vr = j.version_record || {};
  if (vr && Object.keys(vr).length) {
    H.push('<div class="kv">');
    H.push(kv('文书编号', esc(vr.doc_no)));
    H.push(kv('版本', esc(vr.version)));
    H.push(kv('报告名称', esc(vr.doc_name)));
    H.push(kv('文稿类型', esc(vr.edition_kind)));
    H.push(kv('生成时间', esc(vr.generated_at)));
    H.push(kv('复核', vr.reviewed ? '已复核' : '未复核'));
    H.push(kv('变更说明', esc(vr.change_note || '')));
    H.push('</div>');
  } else {
    H.push('<div class="msg warn">台账中未找到该文书编号的行 —— 如实标示，不以本表内容顶替。</div>');
  }
  H.push('</div>');
  el('d-body').innerHTML = H.join('');
  bindDownloadButtons(el('d-body'));
  Array.prototype.forEach.call(el('d-body').querySelectorAll('[data-dl2]'), function (b) {
    b.onclick = function () {
      window.location.href = API + '/reports/' + encodeURIComponent(b.getAttribute('data-dl2'))
        + '/download?format=' + b.getAttribute('data-fmt');
    };
  });
  Array.prototype.forEach.call(el('d-body').querySelectorAll('[data-prev2]'), function (b) {
    b.onclick = function () {
      el('preview-box').innerHTML = '<iframe class="preview" src="' + API + '/reports/'
        + encodeURIComponent(b.getAttribute('data-prev2')) + '/download?format=html"></iframe>';
    };
  });
}

function kv(k, v) { return '<div class="k">' + esc(k) + '</div><div>' + v + '</div>'; }

function openPreview(docNo) {
  var w = window.open('', '_blank');
  if (!w) { alertBox('warn', '浏览器拦截了新窗口，请允许弹窗后重试。'); return; }
  w.location.href = API + '/reports/' + encodeURIComponent(docNo) + '/download?format=html';
}

/* ─────────────────── 事件 ─────────────────── */
function switchTab(name) {
  TABS.forEach(function (t) {
    el('tab-' + t).classList.toggle('active', t === name);
    el('pane-' + t).style.display = (t === name ? '' : 'none');
  });
  if (name === 'history') { loadList(); }
  if (name === 'versions') { loadVersions(); }
}
async function refreshAll() {
  try { var p = await api('GET', API + '/projects/' + PID); CID = p.company_id; } catch (e) { }
  await loadList();
  await loadVersions();
}

document.addEventListener('DOMContentLoaded', function () {
  boot();
  TABS.forEach(function (t) { el('tab-' + t).onclick = function () { switchTab(t); }; });
  el('btn-generate').onclick = doGenerate;
  el('btn-refresh').onclick = function () { refreshAll(); };
  el('btn-list-refresh').onclick = function () { loadList(); };
  el('f-listview').onchange = function () { loadList(); };
  el('project').onchange = function () { PID = el('project').value; CID = null; refreshAll(); };
  el('d-close').onclick = function () {
    el('drawer').classList.remove('open'); el('mask').classList.remove('open');
  };
  el('mask').onclick = function () {
    el('drawer').classList.remove('open'); el('mask').classList.remove('open');
  };
  document.addEventListener('click', function (ev) {
    var b = ev.target.closest ? ev.target.closest('[data-open]') : null;
    if (b) { openDetail(b.getAttribute('data-open')); }
  });
});
