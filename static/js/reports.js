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
var TABS = ['analysis', 'gen', 'history', 'versions'];

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
  // ★ 2026-10-19：默认页签是「分析报告」（HTML 里 `#tab-analysis` 带 active、
  //   `#pane-analysis` 默认可见）。`refreshAll()` 已包含 `loadAnalysisReport()`，
  //   此处无需再切；显式调 `switchTab('analysis')` 只用于**对齐显隐状态**
  //   （防止 `pane-gen` 等在 HTML 里残留可见）。
  switchTab('analysis');
}

function renderViewCards() {
  el('view-cards').innerHTML = (META.views || []).map(function (v) {
    return '<div class="vcard' + (v.value === VIEW ? ' on' : '') + '" data-view="' + esc(v.value) + '">'
      + '<div class="vt">' + esc(v.label) + '</div>'
      + '<div class="vn">' + esc(v.name) + '</div>'
      + '<div class="vd">' + esc(v.desc) + '</div>'
      // ★ 2026-10-19（真做税种聚焦）：把**组织维度**显式写出来 ——
      //   此前 `tax_specific` 与 `full` 内容相同，用户无法从卡片看出差别
      //   （当时唯一差别是报告名）。`focus_label` 由后端下发（唯一权威
      //   `report_views.FOCUS_LABEL`），前端不自写文案。
      + (v.focus_label ? '<div class="vc">组织方式：' + esc(v.focus_label) + '</div>' : '')
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
// ★ 2026-10-19（用户要求：报告列表加勾选 + 「删除选中」）：
//   勾选状态只记「本页已勾选的文书编号」。**切页签/换项目/重新加载列表即清空**
//   —— 与本仓 `/projects` 的批量删除同一口径：绝不删"用户当前看不到的行"。
var REP_PICKED = {};

/** 同步「删除选中」按钮的可见性与计数（未勾选 ⇒ 不显示）。 */
function syncReportSel() {
  var n = Object.keys(REP_PICKED).length;
  var btn = el('btn-del-reports');
  if (btn) { btn.hidden = (n === 0); }
  var c = el('del-picked-n');
  if (c) { c.textContent = String(n); }
  // 全选框：本页全部勾选才打勾；一份都没有时保持未勾且禁用
  var all = el('rep-sel-all');
  if (all) {
    var boxes = document.querySelectorAll('#tb-reports input.rep-sel');
    var checked = document.querySelectorAll('#tb-reports input.rep-sel:checked');
    all.checked = boxes.length > 0 && checked.length === boxes.length;
    all.disabled = boxes.length === 0;
    all.indeterminate = checked.length > 0 && checked.length < boxes.length;
  }
}

async function loadList() {
  if (!PID) { return; }
  REP_PICKED = {};                       // ★ 重新加载 ⇒ 清空勾选（不删看不见的行）
  syncReportSel();
  el('tb-reports').innerHTML = '<tr><td colspan="11" class="muted">加载中…</td></tr>';
  var q = 'project_id=' + PID + '&page=1&page_size=100';
  var v = el('f-listview').value;
  if (v) { q += '&view=' + encodeURIComponent(v); }
  var j;
  try { j = await api('GET', API + '/reports?' + q); }
  catch (e) {
    el('tb-reports').innerHTML = '<tr><td colspan="11" class="muted">' + esc(e.message) + '</td></tr>';
    return;
  }
  el('list-hint').textContent = '共 ' + j.total + ' 份（本页展示 ' + j.items.length + ' 份）；'
    + '文书编号/版本以版本台账为唯一权威';
  el('tb-reports').innerHTML = j.items.map(function (x) {
    var fmts = (x.formats_cn || []).map(function (f) { return esc(f); }).join(' / ');
    return '<tr>'
      + '<td style="text-align:center"><input type="checkbox" class="rep-sel" data-doc="'
      + esc(x.doc_no) + '" title="勾选后可批量删除"></td>'
      + '<td><code>' + esc(x.doc_no) + '</code></td><td>' + esc(x.version) + '</td>'
      + '<td class="wrap">' + esc(x.name) + '</td><td>' + esc(x.view_label) + '</td>'
      + '<td>' + fmts + '</td>'
      + '<td>' + (x.reviewed ? '<span class="tag t-ok">已复核</span>'
                            : '<span class="tag t-warn">未复核</span>') + '</td>'
      + '<td>' + esc(x.finding_count) + '</td>'
      + '<td>' + esc((x.generated_at || '').slice(0, 19)) + '</td>'
      + '<td>' + esc(x.generated_by) + '</td>'
      + '<td><button class="btn sm ghost" data-open="' + esc(x.doc_no) + '">详情</button></td></tr>';
  }).join('') || '<tr><td colspan="11" class="muted">该项目尚无报告</td></tr>';
  syncReportSel();
}

/** 批量删除选中报告（走 `POST /api/v1/reports/delete`，必须显式 confirm）。 */
async function delSelectedReports() {
  var ids = Object.keys(REP_PICKED);
  if (!ids.length) { return; }
  // ★ 2026-10-19：本对话框是 `window.confirm()` —— **纯文本**，不解析 HTML/markdown。
  //   故这里既不能用 `**…**`（会显示星号），也不能用 `<b>`（会显示尖括号）⇒ 一律纯文本。
  if (!window.confirm('确定删除选中的 ' + ids.length + ' 份报告吗？\n\n'
      + '· 删除的是交付物登记与落盘文件（pdf/docx/xlsx/html）；\n'
      + '· 文件会移入回收站，可在「回收站」还原；\n'
      + '· 版本台账（append-only 审计留痕）不被删除。')) { return; }
  var btn = el('btn-del-reports');
  var old = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = '删除中…'; }
  var ok = 0, skip = 0, left = 0, details = [];
  for (var i = 0; i < ids.length; i += 1) {
    // ★ 逐条调用（不是一次性批量）：这样"哪份失败、为什么"能如实落到用户眼前，
    //   而不是一个笼统的"部分失败"。条数上限 200 由服务端把关。
    try {
      var r = await api('POST', API + '/reports/delete',
                        { report_ids: [ids[i]], confirm: true });
      if ((r.deleted || []).length) { ok += 1; }
      (r.skipped || []).forEach(function (s) {
        skip += 1; details.push(s.id + '：' + (s.reason || ''));
      });
      if ((r.leftovers || []).length) {
        left += (r.leftovers || []).length;
        details.push(ids[i] + '：' + r.leftovers.join('；'));
      }
    } catch (e) {
      skip += 1; details.push(ids[i] + '：' + (e && e.message ? e.message : e));
    }
  }
  if (btn) { btn.disabled = false; btn.textContent = old; }
  REP_PICKED = {};
  var msg = '删除完成：成功 ' + ok + ' 份' + (skip ? '，跳过 ' + skip + ' 份' : '')
    + (left ? '，有 ' + left + ' 项文件未清干净（登记已保留，可重试）' : '');
  if (details.length) { msg += '\n\n' + details.slice(0, 8).join('\n'); }
  window.alert(msg);
  await loadList();
  await loadVersions();
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
  // ★ 换页签也是"进入"，一律从页面顶端开始（否则会停在上一页签的滚动位置，
  //   切到「分析报告」时直接落在正文中段，看不到页签与报告信息卡）。
  _scrollPageTop();
  if (name === 'analysis') { loadAnalysisReport(); }
  if (name === 'history') { loadList(); }
  if (name === 'versions') { loadVersions(); }
}

/* ─────────── 分析报告（原「资料风险分析报告」内页，2026-10-19 并入）───────────
 *
 * ★ 渲染**复用** `tax-doc-analysis.js::renderTaxDocReport`（报告级渲染的唯一实现）
 *   —— 本页不另写一份渲染，否则两条链会各出各的报告（本项目反复强调的铁律）。
 *   该函数只要求：① 页面存在 `#tda-report-area` 容器；② 传入**报告正文对象**。
 *
 * ★ 数据契约（★ 双层嵌套，写错就见不到任何内容）：
 *   `GET /api/tax-risk-docs/last-analysis?company_id=` 返回**外层**对象
 *   `{ok, report, blocks, ...}`；真正的报告正文是 **`data.report`**（123 个字段）。
 *   原内页的写法就是 `taxDocReportData = data.report`（不可写成 `data`）。
 *
 * ★ 口径如实：没有分析结果时**如实说明原因**（不假装已生成、不用空报告顶替）。
 */
async function loadAnalysisReport() {
  var area = el('tda-report-area');
  if (!area) { return; }
  if (!CID) {
    try { var p = await api('GET', API + '/projects/' + PID); CID = p.company_id; } catch (e) { }
  }
  // ★ 2026-10-19 关键接线：`tax-doc-analysis.js::_tdaCid()` 读的是全局
  //   `currentCompanyId`（原由 `core.js` 里的账套上下文维护）。本页**刻意不引 core.js**
  //   ⇒ 必须由本页把它设好，否则「导出PDF / 缓存 / 删除报告」会因 cid=0 报
  //   「未选择账套」（且这三个按钮就在同一个页签上，用户一定会点到）。
  //   `_tdaCid` 用 `typeof` 探测，故这里赋值即可生效，无需改 tax-doc-analysis.js。
  if (CID) { window.currentCompanyId = Number(CID); }
  if (!CID) {
    area.innerHTML = '<div class="msg warn">无法确定账套 —— 请先在上方选择一个稽查项目。</div>';
    return;
  }
  if (typeof renderTaxDocReport !== 'function') {
    // 不静默：渲染器没加载出来必须让用户看见（否则只是一个空白页）
    area.innerHTML = '<div class="msg err">报告渲染器未加载（tax-doc-analysis.js）。'
      + '这不影响本页其它功能，请刷新页面重试。</div>';
    return;
  }
  area.innerHTML = '<div class="muted" style="padding:40px 16px;text-align:center">加载中…</div>';
  try {
    var r = await fetch('/api/tax-risk-docs/last-analysis?company_id=' + encodeURIComponent(CID),
                        { credentials: 'same-origin', cache: 'no-store' });
    if (r.status === 401) { window.location.href = '/login'; return; }
    var d = await r.json();
    if (!d || !d.ok || !d.report) {
      area.innerHTML = '<div class="msg warn">该项目尚无分析报告。'
        + (d && d.message ? esc(d.message) : '请先到「⚡ 一键稽查分析任务」发起分析；分析完成后本页签会自动展示。')
        + '</div>';
      return;
    }
    window.taxDocReportData = d.report;      // 让「导出PDF / 缓存 / 删除报告」可用
    renderTaxDocReport(d.report);
    _demoteReportCover();
    _scrollPageTop();
  } catch (e) {
    area.innerHTML = '<div class="msg err">读取分析报告失败：' + esc(e.message) + '</div>';
  }
}

/* ─── 进入「分析报告」即显示**页面顶端**（2026-10-19 用户要求）───────────────
 *
 * 为什么需要显式处理：报告正文很长（实测 10 万+ 字、整页高 10 万像素），
 * 而 `tax-doc-analysis.js` 渲染完会 `scrollIntoView` 到报告区 —— 那是它作为
 * **独立内页**时的合理行为；内嵌到本页后，用户一进来就看不到页面标题与页签，
 * 观感像"页面被吞掉一截"（实测 scrollY=119）。
 *
 * 本页已用 `<body class="embed-report">` 让它**不再自动滚动**；这里再主动
 * 把视口归位到顶部，确保：进页面 / 切回「分析报告」页签 / 换项目重渲染，
 * 三种进入方式都从**页面顶端**开始读。
 */
function _scrollPageTop() {
  try {
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
  } catch (e) {
    window.scrollTo(0, 0);
  }
}

/* ─── 封面标题降级（2026-10-19，用户报「切换模块时还显示资料风险分析报告的页面」）───
 *
 * ## 用户看到的现象与真实原因
 * 用户切到「报告生成与导出」模块，看到页面上赫然写着报告封面的大标题
 * （现为「内部辅助分析工作底稿」，由 `config/report_identity.json` 唯一权威下发），
 * 于是认为「资料风险分析报告」这个模块并没有被删掉。
 *
 * **真实原因**：报告正文**自带整页封面** —— `tax-doc-analysis.js` 渲染时注入
 * `<div class="cover"><h1>{报告名}</h1>…</div>`（封面含报告编号/被审企业/报告日期/资料数量）。
 * 内嵌到 `/reports` 后，就与本页主标题（`<h1>📄 报告生成与导出</h1>`）**并存两个 H1**
 * ⇒ 视觉上像"两个模块叠在一起"。
 *
 * ## 为什么不是"把封面删掉"
 * 封面里的**报告编号 / 被审查企业 / 报告日期 / 资料数量**是"看报告"时的必要信息，
 * 删掉等于丢内容（且导出 PDF 走的是同一条渲染链，删了会连带影响交付物）。
 *
 * ## 采用的修法：**降级，不删除**
 * 只把封面那个**与页面标题重复的大标题 `h1`** 降为次级标题样式（视觉上成为
 * "报告信息卡"的标题），信息一项不减；同时把封面块的"整页居中留白"改为紧凑卡片，
 * 使页面层级变成：**页面标题（报告生成与导出）→ 分析报告页签 → 报告信息卡 → 正文**。
 *
 * ★ 只在本页签内生效（作用域限定 `#tda-report-area`），不改 `tax-doc-analysis.js`
 *   —— 那是报告渲染的唯一实现（导出 PDF / 离线链路共用），不能为一个页面的观感去动它。
 */
function _demoteReportCover() {
  var area = el('tda-report-area');
  if (!area) { return; }
  var cover = area.querySelector('.cover');
  if (!cover) { return; }
  var h1 = cover.querySelector('h1');
  if (h1) {
    // 保留文字，降为「报告信息卡」的标题：改标签名会破坏 CSS 选择器，
    // 故只加类 + 覆盖样式（可逆、不影响导出用的同一份 DOM 结构语义）。
    h1.classList.add('rpt-cover-demoted');
    h1.setAttribute('title', '报告名称（唯一权威：config/report_identity.json）');
  }
  cover.classList.add('rpt-cover-card');
}
async function refreshAll() {
  try { var p = await api('GET', API + '/projects/' + PID); CID = p.company_id; } catch (e) { }
  await loadAnalysisReport();
  await loadList();
  await loadVersions();
}

document.addEventListener('DOMContentLoaded', function () {
  boot();
  TABS.forEach(function (t) { el('tab-' + t).onclick = function () { switchTab(t); }; });
  el('btn-generate').onclick = doGenerate;
  // ★ 2026-10-19（用户要求）：顶栏【刷新】与报告列表内【刷新】按钮均已删除，绑定随之移除。
  //   刷新能力未丢失：切到「报告列表」页签会自动 `loadList()`、切「版本台账」自动 `loadVersions()`，
  //   换项目触发 `refreshAll()`（三块全覆盖）；「删除选中」完成后也会自动重载列表。
  el('f-listview').onchange = function () { loadList(); };
  // ★ 2026-10-19：报告列表勾选 + 删除选中（口径与 `/projects` 批量删除一致）
  if (el('rep-sel-all')) {
    el('rep-sel-all').onchange = function () {
      var on = el('rep-sel-all').checked;
      Array.prototype.forEach.call(
        document.querySelectorAll('#tb-reports input.rep-sel'),
        function (b) {
          b.checked = on;
          var d = b.getAttribute('data-doc');
          if (on) { REP_PICKED[d] = true; } else { delete REP_PICKED[d]; }
        });
      syncReportSel();
    };
  }
  if (el('tb-reports')) {
    // 事件委托（列表是动态 innerHTML，逐行绑会随重渲染丢失）
    el('tb-reports').addEventListener('change', function (ev) {
      var t = ev.target;
      if (!t || !t.classList || !t.classList.contains('rep-sel')) { return; }
      var d = t.getAttribute('data-doc');
      if (t.checked) { REP_PICKED[d] = true; } else { delete REP_PICKED[d]; }
      syncReportSel();
    });
  }
  if (el('btn-del-reports')) { el('btn-del-reports').onclick = delSelectedReports; }
  syncReportSel();
  el('project').onchange = function () {
    PID = el('project').value; CID = null;
    window.currentCompanyId = 0;   // ★ 换项目 ⇒ 先清账套，避免「分析报告」页签沿用上一个项目的导出目标
    refreshAll();
  };
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
  // ★ P0-8 前端门控（2026-10-17）：无 report.generate（复核专家/审计员）时，
  //   「生成报告」页签与表单已被 `data-perm` 隐藏（rbac-nav.js）。
  //   ★ 2026-10-19 更新：默认页签现为「**分析报告**」（不需要 report.generate，
  //   它读的是 /api/tax-risk-docs/last-analysis，属只读查阅）⇒ 无该权限时
  //   **不再需要切走**；仅当「分析报告」页签本身也被隐藏（不存在）时才切「报告列表」。
  if (window.RBAC && window.RBAC.ready) {
    window.RBAC.ready(function () {
      var analysisTab = el('tab-analysis');
      var analysisVisible = analysisTab && analysisTab.style.display !== 'none'
        && !analysisTab.hidden;
      if (!analysisVisible) { switchTab('history'); }
    });
  }
});
