/* -*- coding: utf-8 -*-
 * 风险结果与复核工作台（P0-6）
 *
 * ★ 契约（后端 `/api/v1`，权威 `engine/risk_service.py` / `engine/risk_review.py`）：
 *   GET  /api/v1/risks/meta
 *   GET  /api/v1/projects/{pid}/risks?tax=&level=&state=&period=&amount_min=&amount_max=
 *                                  &q=&reviewed=&sort=&order=&page=&page_size=
 *   GET  /api/v1/projects/{pid}/risks/stats
 *   GET  /api/v1/risks/{riskId}                （riskId = 风险编号；兼容数字序号）
 *   POST /api/v1/risks/{riskId}/review          {action, note?, company_id?, project_id?}
 *   POST /api/v1/risks/{riskId}/comment         {text, company_id?, project_id?}
 *   GET  /api/v1/rectifications?company_id=…
 *
 * ★ 中文名一律取后端（`/risks/meta`）——前端**不硬编码**状态/动作/等级/排序名。
 * ★ 证据链、明细表、叙述段落、自我怀疑清单**原样展示**（不截断、不摘要、不重排）。
 * ★ 理由必填的动作由后端强制（前端同步提示）；前端**不自行放宽**。
 */
'use strict';

var API = '/api/v1';
var META = null, PROJECTS = [], PID = null, CID = null;
var PAGE = 1, PAGE_SIZE = 20, TOTAL = 0, LAST = null;
var DETAIL = null;                 // 当前详情
var TABS = ['list', 'stats', 'rect', 'exec', 'board'];   // 'board' = P1-4 复核看板

function el(id) { return document.getElementById(id); }
function esc(s) {
  return String(s === null || s === undefined ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
function alertBox(kind, text) {
  var cls = kind === 'err' ? 'err' : (kind === 'warn' ? 'warn' : 'ok');
  el('alert').innerHTML = '<div class="msg ' + cls + '">' + esc(text) + '</div>';
  if (kind === 'ok') { setTimeout(function () { el('alert').innerHTML = ''; }, 6000); }
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
function num(v) {
  if (v === null || v === undefined || v === '') { return '<span class="muted">—</span>'; }
  var n = Number(v);
  if (!isFinite(n)) { return esc(v); }
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function lvTag(lv) {
  var s = String(lv || '');
  return '<span class="tag lv-' + esc(s) + '">' + esc(s || '—') + '</span>';
}
function stTag(v, cn) {
  var s = String(v || 'pending');
  return '<span class="tag st-' + esc(s) + '">' + esc(cn || s) + '</span>';
}

/* ─────────────────── 引导 ─────────────────── */
async function boot() {
  try {
    META = await api('GET', API + '/risks/meta');
  } catch (e) {
    alertBox('err', '字典加载失败：' + e.message); return;
  }
  fillSelect(el('f-state'), META.review.states, 'label');
  fillSelect(el('f-sort'), META.sorts, 'label', null);
  fillSelect(el('f-level'), META.levels, 'label');
  var pl = await api('GET', API + '/projects?page=1&page_size=200');
  PROJECTS = pl.items || pl.projects || [];
  var sel = el('project');
  sel.innerHTML = PROJECTS.length
    ? PROJECTS.map(function (p) {
        return '<option value="' + p.id + '">' + esc(p.name) + '（' + esc(p.code || '') + '）</option>';
      }).join('')
    : '<option value="">（暂无稽查项目，请先在"稽查项目"页新建）</option>';
  if (PROJECTS.length) { PID = String(PROJECTS[0].id); }
  el('who').textContent = '';
  try {
    var me = await fetch('/api/auth/me');
    if (me.ok) { var d = await me.json(); el('who').textContent = d.username || d.user_name || ''; }
  } catch (e) { /* 非关键 */ }
  await refreshAll();
}

function fillSelect(sel, items, labelKey, allLabel) {
  // allLabel: 默认 '全部'；显式传 null ⇒ **不加"全部"项**（如排序键，语义上不存在"全部排序"）
  var all = (allLabel === undefined) ? '全部' : allLabel;
  var base = sel.querySelector('option[value=""]');
  sel.innerHTML = base ? base.outerHTML : (all ? '<option value="">' + esc(all) + '</option>' : '');
  (items || []).forEach(function (x) {
    sel.innerHTML += '<option value="' + esc(x.value) + '">' + esc(x[labelKey] || x.value) + '</option>';
  });
}

/* ─────────────────── 列表 ─────────────────── */
function qs() {
  var p = new URLSearchParams();
  var map = { tax: 'f-tax', level: 'f-level', state: 'f-state', period: 'f-period',
              amount_min: 'f-amin', amount_max: 'f-amax', q: 'f-q',
              reviewed: 'f-reviewed', sort: 'f-sort', order: 'f-order' };
  Object.keys(map).forEach(function (k) {
    var v = el(map[k]).value;
    if (v !== '' && v !== null) { p.set(k, v); }
  });
  p.set('page', PAGE); p.set('page_size', PAGE_SIZE);
  return p.toString();
}

async function loadList() {
  if (!PID) {
    el('tb-risks').innerHTML = '<tr><td colspan="9" class="muted">请先选择稽查项目</td></tr>';
    return;
  }
  el('tb-risks').innerHTML = '<tr><td colspan="9" class="muted">加载中…</td></tr>';
  var j;
  try {
    j = await api('GET', API + '/projects/' + PID + '/risks?' + qs());
  } catch (e) {
    el('tb-risks').innerHTML = '<tr><td colspan="9" class="muted">加载失败：' + esc(e.message) + '</td></tr>';
    return;
  }
  CID = j.company_id;
  if (!j.available) {
    el('tb-risks').innerHTML = '<tr><td colspan="9" class="muted">'
      + esc(j.reason || '无可展示数据') + '</td></tr>';
    el('list-count').textContent = '';
    el('filter-note').innerHTML = '';
    renderKpis(null);
    return;
  }
  LAST = j; TOTAL = j.total;
  el('list-count').textContent = '共 ' + j.total + ' 条（第 ' + j.page + ' / ' + (j.pages || 1) + ' 页）'
    + '（排序：' + (j.sort_cn || '') + ' ' + (j.order === 'asc' ? '升序' : '降序')
    + '，数据生成于 ' + (j.generated_at || '—') + '）';
  var fs = j.filter_stats || {};
  var notes = [];
  if (fs.excluded_unknown_amount) {
    notes.push('★ 有 ' + fs.excluded_unknown_amount + ' 条**金额取不到**（载荷未测算金额），'
      + '**未按 0 元参与金额筛选**，已被排除。');
  }
  if (fs.excluded_no_period) { notes.push('有 ' + fs.excluded_no_period + ' 条无期间信息被排除。'); }
  el('filter-note').innerHTML = notes.length ? notes.map(esc).join(' ') : '';
  el('tb-risks').innerHTML = j.items.map(function (x) {
    return '<tr>'
      + '<td><input type="checkbox" data-pick="' + esc(x.risk_no || x.seq) + '"'
      + (PICKED[x.risk_no || x.seq] ? ' checked' : '') + '></td>'
      + '<td>' + esc(x.seq) + '</td>'
      + '<td class="muted">' + esc(x.risk_no || '—') + '</td>'
      + '<td class="wrap">' + esc(x.title || '') + '</td>'
      + '<td>' + lvTag(x.risk_level) + '</td>'
      + '<td class="num">' + (x.priority_score === null || x.priority_score === undefined
          ? '<span class="muted">信息不足</span>' : esc(x.priority_score)) + '</td>'
      + '<td class="num">' + num(x.amount_known === false ? null : x.tax_impact_amount) + '</td>'
      + '<td>' + esc((x.taxes || []).join('、') || '—') + '</td>'
      + '<td>' + stTag(x.review_state, x.review_state_cn)
          + (x.manual_required ? '<span class="pill">需人工</span>' : '')
          + (x.rectification_no ? '<span class="pill">' + esc(x.rectification_no) + '</span>' : '')
      + '</td>'
      + '<td><button class="btn sm" data-open="' + esc(x.risk_no || x.seq) + '">详情/复核</button></td>'
      + '</tr>';
  }).join('') || '<tr><td colspan="9" class="muted">无符合条件的事项</td></tr>';
  el('pg-info').textContent = '第 ' + j.page + ' / ' + (j.pages || 1) + ' 页';
  el('pg-prev').disabled = j.page <= 1;
  el('pg-next').disabled = j.page >= (j.pages || 1);
  renderKpis(j);
}


function renderKpis(j) {
  if (!j || !j.review_summary) { el('kpi-box').innerHTML = ''; return; }
  var rs = j.review_summary.by_state || {};
  var cn = j.review_summary.by_state_cn || {};
  var html = '';
  html += kpi('风险事项总数', j.total, META ? '' : '');
  META.review.states.forEach(function (s) {
    if (s.value === 'pending') { return; }
    html += kpi(cn[s.label] || s.label, rs[s.value] || 0, '');
  });
  html += kpi('待处理', rs.pending || 0, '');
  html += kpi('复核进度', (j.review_summary.reviewed_total || 0) + ' / ' + j.total,
              (Math.round((j.review_summary.reviewed_ratio || 0) * 1000) / 10) + '%');
  el('kpi-box').innerHTML = html;
}
function kpi(k, v, s) {
  return '<div class="kpi"><div class="k">' + esc(k) + '</div><div class="v">' + esc(v)
    + '</div>' + (s ? '<div class="s">' + esc(s) + '</div>' : '') + '</div>';
}

/* ─────────────────── 统计 ─────────────────── */
async function loadStats() {
  if (!PID) { return; }
  var st;
  try { st = await api('GET', API + '/projects/' + PID + '/risks/stats'); }
  catch (e) { alertBox('err', '统计加载失败：' + e.message); return; }
  if (!st.available) {
    ['chart-level', 'chart-state', 'chart-tax', 'chart-amount'].forEach(function (id) {
      el(id).innerHTML = '<span class="muted">' + esc(st.reason || '') + '</span>';
    });
    return;
  }
  drawBars(el('chart-level'), st.by_level, { 极高风险: '#991b1b', 高风险: '#dc2626',
    中风险: '#ea580c', 低风险: '#16a34a', 待核验: '#4f46e5', 信息: '#64748b' });
  drawBars(el('chart-state'), st.by_state_cn, { 待处理: '#f59e0b', 已确认: '#2563eb',
    已排除: '#64748b', 已整改: '#16a34a', 误报: '#dc2626' });
  drawBars(el('chart-tax'), st.by_tax, {});
  var bands = st.by_amount_band || {};
  drawBars(el('chart-amount'), bands, {});
  el('review-progress').innerHTML = '已复核 ' + st.reviewed_total + ' / ' + st.total
    + '（' + (Math.round((st.reviewed_ratio || 0) * 1000) / 10) + '%）；整改台账 '
    + st.rectification_total + ' 条。';
  el('review-bar').style.width = Math.round((st.reviewed_ratio || 0) * 100) + '%';
  el('amount-note').innerHTML = '测算金额合计 <b>' + num(st.amount_total) + '</b> 元；'
    + '★ 有 <b>' + st.amount_unknown_count + '</b> 条金额取不到（<code>tax_impact.available=false</code>），'
    + '<b>未按 0 元计入</b>。待处理金额合计 ' + num(st.pending_amount_total) + ' 元'
    + (st.pending_amount_unknown_count
        ? '（另有 ' + st.pending_amount_unknown_count + ' 条待处理金额未知，未计入）' : '')
    + '。';
}

function drawBars(host, obj, colors) {
  var keys = Object.keys(obj || {});
  if (!keys.length) { host.innerHTML = '<span class="muted">无数据</span>'; return; }
  var max = Math.max.apply(null, keys.map(function (k) { return Number(obj[k]) || 0; })) || 1;
  host.innerHTML = keys.map(function (k) {
    var v = Number(obj[k]) || 0;
    var h = Math.max(2, Math.round(v / max * 118));
    var c = (colors && colors[k]) || '#3b82f6';
    return '<div class="bar-col"><div class="bar-val">' + v + '</div>'
      + '<div class="bar" style="height:' + h + 'px;background:' + c + '"></div>'
      + '<div class="bar-lbl">' + esc(k) + '</div></div>';
  }).join('');
}

/* ─────────────────── 详情 + 复核 ─────────────────── */
async function openDetail(riskId) {
  el('d-body').innerHTML = '<div class="muted">加载中…</div>';
  el('drawer').classList.add('open'); el('mask').classList.add('open');
  var j;
  try { j = await api('GET', API + '/risks/' + encodeURIComponent(riskId)); }
  catch (e) { el('d-body').innerHTML = '<div class="msg err">' + esc(e.message) + '</div>'; return; }
  if (!j.available) { el('d-body').innerHTML = '<div class="msg err">' + esc(j.reason) + '</div>'; return; }
  DETAIL = j;
  renderDetail(j);
}

function renderDetail(j) {
  var f = j.finding || {}, r = j.review || {}, rule = j.rule || {};
  var sc = j.scoring || {};
  el('d-title').innerHTML = '风险详情：' + esc(f.title || '');
  var H = [];

  /* 概要 */
  H.push('<div class="card"><h3>概要</h3><div class="kv">');
  H.push(kv('风险编号', esc(j.risk_no || '—') + '<span class="pill">序号 ' + esc(j.seq) + '</span>'));
  H.push(kv('风险等级', lvTag(f.risk_level)
    + (f.risk_level_basis ? '<span class="muted">　依据：' + esc(f.risk_level_basis) + '</span>' : '')));
  H.push(kv('结论等级', esc(f.conclusion_grade || '—')));
  H.push(kv('综合排序分', (sc.priority_score === null || sc.priority_score === undefined
      ? '<span class="muted">信息不足（不参与排序）</span>'
      : esc(sc.priority_score) + '　<span class="muted">' + esc(sc.status || '') + '</span>')
      + '<span class="pill">仅排序·不改等级</span>'));
  H.push(kv('税种', esc((f.taxes || []).join('、') || '—')));
  H.push(kv('复核状态', stTag(r.state, r.state_cn)
    + (r.manual_required ? '<span class="pill">需人工介入</span>' : '')
    + (r.rectification_no ? '<span class="pill">' + esc(r.rectification_no) + '</span>' : '')));
  H.push(kv('置信度', esc(f.confidence === undefined ? '—' : f.confidence)));
  H.push('</div></div>');

  /* 复核操作 */
  H.push('<div class="card"><h3>人工复核 <span class="hint">处置状态唯一权威后端；'
    + '★ 复核不改动风险等级</span></h3>');
  H.push('<div class="steps" id="d-flow">');
  (META.review.states || []).forEach(function (s) {
    H.push('<span class="flow-tag' + (s.value === r.state ? ' on' : '') + '">'
      + esc(s.label) + '</span>');
  });
  H.push('</div>');
  H.push('<p class="muted" id="d-flow-msg" style="margin:8px 0 6px">当前可执行的复核动作：</p>');
  H.push('<div class="toolbar" id="d-actions" style="margin-bottom:6px">');
  (META.review.actions || []).forEach(function (a) {
    H.push('<button class="btn sm ' + (a.value === 'rectify' ? '' : 'ghost')
      + (a.value === 'false_positive' ? ' danger' : '')
      + '" data-act="' + esc(a.value) + '" data-note="' + (a.note_required ? '1' : '')
      + '">' + esc(a.label) + (a.note_required ? ' *' : '') + '</button>');
  });
  H.push('</div>');
  H.push('<div class="note-box"><textarea id="d-note" placeholder="理由/说明（标注 * 的动作必填；'
    + '排除、误报、标记已整改、重新打开均需说明）"></textarea>');
  H.push('<div class="toolbar" style="margin-top:6px"><button class="btn" id="d-do">提交复核</button>'
    + '<button class="btn ghost" id="d-cmt">仅批注</button>'
    + '<span class="muted">批注不改状态</span></div></div>');
  H.push('<div id="d-cmts" style="margin-top:10px">' + renderComments(r) + '</div>');
  H.push('<div id="d-hist" style="margin-top:8px">' + renderHistory(r) + '</div>');
  H.push('</div>');

  /* 规则与法规依据 */
  H.push('<div class="card"><h3>规则与法规依据</h3>');
  if (!j.rule_found) {
    H.push('<div class="msg warn">该风险事项的规则**未在规则目录中**（可能只在发现里出现）；'
      + '此处**不编造法规依据**。规则标识：' + esc(f.rule_id || f.redline_id || '—') + '</div>');
  } else {
    H.push('<div class="kv">');
    H.push(kv('规则', esc(rule.rule_id) + '　' + esc(rule.name || '')));
    H.push(kv('层级', esc(rule.layer || '—') + '　<span class="pill">' + esc(rule.source_cn || '') + '</span>'));
    H.push(kv('版本', esc(rule.version || '未登记')
      + (rule.version_registered === false ? '<span class="pill">未登记</span>' : '')));
    H.push('</div>');
    H.push('<table class="grid" style="margin-top:8px"><thead><tr><th>法规</th><th>条文</th>'
      + '<th>原文</th><th>状态</th></tr></thead><tbody>');
    (rule.legal_basis_ref || []).forEach(function (x) {
      H.push('<tr><td>' + esc(x.law || '—') + '</td><td>' + esc(x.article || '—') + '</td>'
        + '<td class="wrap">' + esc(x.raw || '') + '</td><td>'
        + (x.placeholder ? '<span class="tag st-pending">占位（未入库）</span>'
                         : '<span class="tag st-rectified">已核实引用</span>')
        + '</td></tr>');
    });
    H.push('</tbody></table>');
    if (rule.legal_basis_placeholder) {
      H.push('<div class="msg warn">该规则的法规依据为**占位值**（候选规则未入库）⇒ 不可视为已核实。</div>');
    }
  }
  H.push('</div>');

  /* 计算过程 */
  H.push('<div class="card"><h3>计算过程（评分因子）<span class="hint">取不到值的因子'
    + '**剔除并重算权重**，不按 0 分顶替</span></h3>');
  H.push('<table class="grid"><thead><tr><th>因子</th><th>取值</th><th>状态</th>'
    + '<th>权重（归一后）</th><th>来源</th></tr></thead><tbody>');
  (sc.factors || []).forEach(function (x) {
    H.push('<tr><td>' + esc(x.name_cn || x.name) + '</td><td class="num">'
      + (x.value === null || x.value === undefined ? '<span class="muted">取不到</span>' : esc(x.value))
      + '</td><td>' + (x.state === 'missing'
          ? '<span class="tag st-pending">缺失（已剔除）</span>'
          : '<span class="tag st-rectified">' + esc(x.state) + '</span>')
      + '</td><td class="num">' + (x.weight === null || x.weight === undefined ? '—' : esc(x.weight))
      + '</td><td class="muted">' + esc(x.from || '') + '</td></tr>');
  });
  H.push('</tbody></table>');
  H.push('<p class="muted">参与计算的权重和：' + esc(sc.score_basis) + '；被剔除权重：'
    + esc(sc.missing_weight) + '。★ 本分**只作排序**，不得反推定性。</p>');
  if (f.confidence_breakdown && f.confidence_breakdown.length) {
    H.push('<h3 style="margin-top:10px">置信度分项</h3>');
    H.push('<table class="grid"><thead><tr><th>分项</th><th>取值</th><th>贡献</th></tr></thead><tbody>');
    f.confidence_breakdown.forEach(function (x) {
      H.push('<tr><td>' + esc(x['分项'] || x.name || '') + '</td><td class="num">'
        + esc(x['取值'] === undefined ? '' : x['取值']) + '</td><td class="num">'
        + esc(x['贡献'] === undefined ? '' : x['贡献']) + '</td></tr>');
    });
    H.push('</tbody></table>');
  }
  H.push('</div>');

  /* 证据链 */
  H.push('<div class="card"><h3>证据链 <span class="hint">' + (j.evidences || []).length
    + ' 条；可回指本项</span></h3>');
  if (!(j.evidences || []).length) {
    H.push('<div class="msg warn">本项**未归集到证据条目**（不代表无证据，可能是证据未在载荷中登记）——如实标示。</div>');
  } else {
    H.push('<table class="grid"><thead><tr><th>角色</th><th>名称</th><th>说明</th>'
      + '<th>来源</th><th>状态</th></tr></thead><tbody>');
    j.evidences.forEach(function (e) {
      H.push('<tr><td>' + esc(e.role || '—') + '</td><td>' + esc(e.name || '') + '</td>'
        + '<td class="wrap">' + esc(e.detail || '') + '</td>'
        + '<td class="muted wrap">' + esc(typeof e.sources === 'string' ? e.sources
            : JSON.stringify(e.sources || '')) + '</td>'
        + '<td>' + esc(e.status || '') + '</td></tr>');
    });
    H.push('</tbody></table>');
  }
  H.push('<div class="kv" style="margin-top:10px">');
  H.push(kv('已具备证据', esc(j.evidence_gap.have_count === null ? '—' : j.evidence_gap.have_count) + ' 项'));
  H.push(kv('尚需证据', esc(j.evidence_gap.need_count === null ? '—' : j.evidence_gap.need_count) + ' 项'));
  H.push(kv('直接证据缺失', esc(j.evidence_gap.direct_missing || '—')));
  H.push(kv('缺失资料', esc((j.evidence_gap.missing_material_names || []).join('；') || '—')));
  H.push('</div>');
  H.push('<p class="muted">' + esc(j.evidence_gap.note || '') + '</p>');
  H.push('</div>');

  /* 明细表 / 叙述段落 */
  H.push('<div class="card"><h3>原始数据与明细（原样展示）</h3>');
  H.push(renderDetailTable(j.trace.detail_table));
  var nps = j.trace.narrative_paragraphs || [];
  if (nps.length) {
    H.push('<h3 style="margin-top:12px">叙述段落</h3>');
    nps.forEach(function (p) {
      H.push('<div class="cmt"><div class="h">' + esc(p.heading || '') + '</div>'
        + '<div>' + esc(p.text || '') + '</div></div>');
    });
  }
  H.push('</div>');

  /* 触发条件与认定要件 / 自我怀疑 / 建议 */
  H.push('<div class="card"><h3>触发条件与认定要件</h3>'
    + renderTrigger(j.trace.trigger_determination) + '</div>');
  H.push('<div class="card"><h3>本项可能错在哪里（自我怀疑与验证清单）</h3>'
    + renderSelfDoubt(j.self_doubt) + '</div>');
  H.push('<div class="card"><h3>建议</h3><div>' + esc(j.suggestion || '（无）') + '</div></div>');

  el('d-body').innerHTML = H.join('');
  bindDetail(j);
}

function kv(k, v) { return '<div class="k">' + esc(k) + '</div><div>' + v + '</div>'; }

function renderComments(r) {
  var cs = r.comments || [];
  if (!cs.length) { return '<p class="muted">（暂无批注）</p>'; }
  return '<h3 style="font-size:13px">批注（' + cs.length + '）</h3>' + cs.map(function (c) {
    return '<div class="cmt"><div class="h">#' + esc(c.seq) + '　' + esc(c.author || '')
      + '　' + esc(c.at || '') + '</div><div>' + esc(c.text) + '</div></div>';
  }).join('');
}
function renderHistory(r) {
  var hs = (r.history || []).slice().reverse();
  if (!hs.length) { return '<p class="muted">（暂无处置历史）</p>'; }
  return '<h3 style="font-size:13px">处置历史（' + hs.length + '）</h3>' + hs.map(function (h) {
    var s = esc(h.at || '') + '　' + esc(h.actor || '') + '　' + esc(h.action_cn || h.event);
    if (h.from || h.to) {
      s += '　' + esc(h.from || '') + ' → ' + esc(h.to_cn || h.to || '');
    }
    if (h.rectification_no) { s += '　台账 ' + esc(h.rectification_no); }
    if (h.note) { s += '<br><span class="muted">' + esc(h.note) + '</span>'; }
    return '<div class="hist">' + s + '</div>';
  }).join('');
}

function renderDetailTable(dt) {
  if (!dt) { return '<p class="muted">（无明细表）</p>'; }
  if (Array.isArray(dt)) {
    if (!dt.length) { return '<p class="muted">（无明细表）</p>'; }
    var cols = Object.keys(dt[0] || {});
    return '<table class="grid"><thead><tr>' + cols.map(function (c) {
      return '<th>' + esc(c) + '</th>'; }).join('') + '</tr></thead><tbody>'
      + dt.map(function (row) {
          return '<tr>' + cols.map(function (c) {
            return '<td>' + esc(row[c]) + '</td>'; }).join('') + '</tr>';
        }).join('') + '</tbody></table>';
  }
  var columns = dt.columns || [], rows = dt.rows || [];
  if (!columns.length && !rows.length) { return '<p class="muted">（无明细表）</p>'; }
  return '<table class="grid"><thead><tr>' + columns.map(function (c) {
    return '<th>' + esc(c) + '</th>'; }).join('') + '</tr></thead><tbody>'
    + rows.map(function (row) {
        var obj = row || {};
        if (Array.isArray(obj)) {
          return '<tr>' + obj.map(function (v) { return '<td>' + esc(v) + '</td>'; }).join('') + '</tr>';
        }
        return '<tr>' + columns.map(function (c) {
          return '<td class="wrap">' + esc(obj[c]) + '</td>'; }).join('') + '</tr>';
      }).join('') + '</tbody></table>';
}

function renderTrigger(t) {
  if (!t || !Object.keys(t).length) { return '<p class="muted">（无触发条件记录）</p>'; }
  var H = [];
  if (t.risk_code) { H.push('<div class="muted">规则 ' + esc(t.risk_code) + '</div>'); }
  (t.trigger_conditions || []).forEach(function (x) {
    H.push('<div class="cmt"><div class="h">触发条件 ' + esc(x.id || '') + '</div>'
      + '<div>' + esc(x.desc || '') + '</div></div>');
  });
  (t.determination_constituents || t.constituents || []).forEach(function (x) {
    H.push('<div class="cmt"><div class="h">认定要件 ' + esc(x.id || '') + '</div>'
      + '<div>' + esc(x.desc || x) + '</div></div>');
  });
  return H.join('') || '<p class="muted">（无触发条件记录）</p>';
}

function renderSelfDoubt(sd) {
  if (!sd || !Object.keys(sd).length) { return '<p class="muted">（无自我怀疑记录）</p>'; }
  if (sd.available === false) { return '<p class="muted">（本项未产出自我怀疑清单）</p>'; }
  var H = [];
  (sd.key_inputs || []).forEach(function (x) {
    H.push('<div class="cmt"><div class="h">' + esc(x.item || '') + '</div>'
      + '<div>' + esc(x.value || '') + (x.strength ? '　<span class="pill">'
        + esc(x.strength) + '</span>' : '') + '</div></div>');
  });
  (sd.checks || sd.questions || []).forEach(function (x) {
    H.push('<div class="cmt">' + esc(typeof x === 'string' ? x : (x.text || JSON.stringify(x)))
      + '</div>');
  });
  if (!H.length) {
    H.push('<pre class="raw">' + esc(JSON.stringify(sd, null, 1)) + '</pre>');
  }
  return H.join('');
}

function bindDetail(j) {
  el('d-close').onclick = closeDrawer;
  el('d-do').onclick = function () { doReview(null); };
  el('d-cmt').onclick = function () { doComment(); };
  Array.prototype.forEach.call(el('d-actions').querySelectorAll('button'), function (b) {
    b.onclick = function () { doReview(b.getAttribute('data-act')); };
  });
}

function closeDrawer() {
  el('drawer').classList.remove('open'); el('mask').classList.remove('open');
}

async function doReview(action) {
  if (!DETAIL) { return; }
  var note = el('d-note').value || '';
  var act = action;
  var spec = (META.review.actions || []).filter(function (a) { return a.value === act; })[0] || {};
  if (act && spec.note_required && !note.trim()) {
    alertBox('err', '「' + spec.label + '」必须填写理由/说明。');
    return;
  }
  if (!act) { alertBox('err', '请先点击一个复核动作按钮。'); return; }
  try {
    var r = await api('POST', API + '/risks/' + encodeURIComponent(DETAIL.risk_no) + '/review',
      { action: act, note: note, company_id: DETAIL.company_id });
    alertBox('ok', ('noop' in r && r.noop) ? (r.message || '未产生变更') : (r.message || '已完成'));
    el('d-note').value = '';
    await openDetail(DETAIL.risk_no);
    await loadList();
    if (el('pane-stats').style.display !== 'none') { await loadStats(); }
  } catch (e) { alertBox('err', '复核失败：' + e.message); }
}

async function doComment() {
  if (!DETAIL) { return; }
  var note = el('d-note').value || '';
  if (!note.trim()) { alertBox('err', '批注内容不能为空。'); return; }
  try {
    var r = await api('POST', API + '/risks/' + encodeURIComponent(DETAIL.risk_no) + '/comment',
      { text: note, company_id: DETAIL.company_id });
    alertBox('ok', '批注已登记（共 ' + r.comment_count + ' 条）');
    el('d-note').value = '';
    await openDetail(DETAIL.risk_no);
  } catch (e) { alertBox('err', '批注失败：' + e.message); }
}

/* ─────────────────── 整改台账 / 逐条执行 ─────────────────── */
async function loadRect() {
  if (!CID) { el('tb-rect').innerHTML = '<tr><td colspan="6" class="muted">请先选择项目</td></tr>'; return; }
  var j;
  try { j = await api('GET', API + '/rectifications?company_id=' + CID); }
  catch (e) { el('tb-rect').innerHTML = '<tr><td colspan="6" class="muted">' + esc(e.message) + '</td></tr>'; return; }
  el('rect-count').textContent = '共 ' + j.total + ' 条';
  el('tb-rect').innerHTML = j.items.map(function (x) {
    return '<tr><td>' + esc(x.rectification_no) + '</td>'
      + '<td class="muted">' + esc(x.risk_no) + '</td>'
      + '<td class="wrap">' + esc(x.measure) + '</td>'
      + '<td>' + esc(x.author || '') + '</td><td>' + esc(x.at || '') + '</td>'
      + '<td><button class="btn sm ghost" data-open="' + esc(x.risk_no) + '">查看风险</button></td></tr>';
  }).join('') || '<tr><td colspan="6" class="muted">（暂无整改台账）</td></tr>';
}

async function loadExec() {
  if (!CID) { el('tb-exec').innerHTML = '<tr><td colspan="4" class="muted">请先选择项目</td></tr>'; return; }
  var j;
  try { j = await api('GET', API + '/rule-executions?company_id=' + CID); }
  catch (e) { el('tb-exec').innerHTML = '<tr><td colspan="4" class="muted">' + esc(e.message) + '</td></tr>'; return; }
  if (!j.available) { el('tb-exec').innerHTML = '<tr><td colspan="4" class="muted">' + esc(j.reason) + '</td></tr>'; return; }
  var s = j.summary || {};
  el('exec-summary').innerHTML = '共 ' + (s.total || 0) + ' 条：'
    + Object.keys(s.by_status_cn || {}).map(function (k) {
        return esc(k) + ' ' + s.by_status_cn[k]; }).join(' · ');
  el('tb-exec').innerHTML = (j.items || []).map(function (x) {
    return '<tr><td>' + esc(x.rule_id || x.redline_id || '') + '</td>'
      + '<td>' + esc(x.layer || '') + '</td>'
      + '<td>' + esc(x.status_cn || x.status || '') + '</td>'
      + '<td class="wrap muted">' + esc(x.note || x.reason || '') + '</td></tr>';
  }).join('') || '<tr><td colspan="4" class="muted">（无执行记录）</td></tr>';
}

/* ───────────── P1-4 复核看板 / 批量复核 ───────────── */
var PICKED = {};                    // risk_no → true（仅本页勾选，不跨页累积）

function pickedIds() { return Object.keys(PICKED).filter(function (k) { return PICKED[k]; }); }

function renderCheckboxes() {
  var boxes = document.querySelectorAll('[data-pick]');
  for (var i = 0; i < boxes.length; i++) {
    var k = boxes[i].getAttribute('data-pick');
    boxes[i].checked = !!PICKED[k];
  }
}

async function loadBoard() {
  if (!PID) {
    el('board-kpis').innerHTML = '';
    el('board-note').textContent = '请先选择稽查项目';
    el('tb-stale').innerHTML = '<tr><td colspan="3" class="muted">请先选择项目</td></tr>';
    return;
  }
  var j;
  try { j = await api('GET', API + '/risks/review-board?project_id=' + PID); }
  catch (e) {
    el('board-note').textContent = '看板加载失败：' + e.message;
    el('tb-stale').innerHTML = '<tr><td colspan="3" class="muted">加载失败</td></tr>';
    return;
  }
  CID = j.company_id || CID;
  el('board-hint').textContent = j.note || '';
  el('board-kpis').innerHTML =
      kpi('已处置', j.done) + kpi('处置率', Math.round((j.done_ratio || 0) * 100) + '%')
    + kpi('超期待处理', j.overdue_count) + kpi('从未处置', j.never_reviewed_count)
    + Object.keys(j.by_state_cn || {}).map(function (k) {
        return kpi(k, j.by_state_cn[k]); }).join('');
  el('board-note').textContent = '超期阈值 ' + j.stale_days + ' 天；共 ' + j.total + ' 条纳入统计。';
  el('board-stale-hint').textContent = '共 ' + j.overdue_count + ' 条';
  el('tb-stale').innerHTML = (j.overdue || []).map(function (x) {
    return '<tr><td>' + esc(x.risk_no) + '</td><td class="num">' + esc(x.days)
      + '</td><td class="muted">' + esc(x.updated_at || '—') + '</td></tr>';
  }).join('') || '<tr><td colspan="3" class="muted">（无超期待处理）</td></tr>';
  // 批量动作下拉：**取后端字典**（不硬编码中文名与"是否必填理由"）
  var sel = el('bk-action');
  if (!sel.options.length && META && META.review) {
    (META.review.actions || []).forEach(function (a) {
      var o = document.createElement('option');
      o.value = a.value;
      o.textContent = a.label + (a.note_required ? '（需填理由）' : '');
      o.setAttribute('data-note', a.note_required ? '1' : '0');
      sel.appendChild(o);
    });
  }
  el('bk-hint').textContent = '已勾选 ' + pickedIds().length + ' 条（在「风险列表」页勾选）';
}

async function runBulk() {
  var ids = pickedIds();
  if (!ids.length) { alertBox('warn', '请先在「风险列表」页勾选要处置的风险'); return; }
  var sel = el('bk-action');
  var opt = sel.options[sel.selectedIndex];
  var note = (el('bk-note').value || '').trim();
  if (opt && opt.getAttribute('data-note') === '1' && !note) {
    alertBox('warn', '「' + opt.textContent + '」必须填写理由/说明');
    return;
  }
  var body = { risk_ids: ids, action: sel.value, note: note };
  if (CID) { body.company_id = CID; }
  var j;
  try { j = await api('POST', API + '/risks/bulk-review', body); }
  catch (e) { alertBox('err', '批量复核失败：' + e.message); return; }
  el('bk-result').innerHTML =
      '共 ' + j.total + ' 条：<b>成功 ' + j.ok + '</b> · 无变化 ' + j.noop
    + ' · <b>失败 ' + j.failed + '</b>'
    + (j.dup_removed ? '（已自动去重 ' + j.dup_removed + ' 条）' : '')
    + '<br>' + esc(j.note || '')
    + '<br>' + (j.items || []).map(function (x) {
        return '· ' + esc(x.risk_no) + ' → ' + esc(x.status) + '：' + esc(x.message);
      }).join('<br>');
  PICKED = {};
  await loadList();
  await loadBoard();
}

/* ─────────────────── 事件 ─────────────────── */
function switchTab(name) {
  TABS.forEach(function (t) {
    el('tab-' + t).classList.toggle('active', t === name);
    el('pane-' + t).style.display = (t === name ? '' : 'none');
  });
  if (name === 'stats') { loadStats(); }
  if (name === 'rect') { loadRect(); }
  if (name === 'exec') { loadExec(); }
  if (name === 'board') { loadBoard(); }
}

async function refreshAll() {
  await loadList();
  if (el('pane-stats').style.display !== 'none') { await loadStats(); }
  if (el('pane-rect').style.display !== 'none') { await loadRect(); }
  if (el('pane-exec').style.display !== 'none') { await loadExec(); }
  if (el('pane-board').style.display !== 'none') { await loadBoard(); }
}

document.addEventListener('DOMContentLoaded', function () {
  boot();
  TABS.forEach(function (t) {
    el('tab-' + t).onclick = function () { switchTab(t); };
  });
  el('project').onchange = function () {
    PID = el('project').value; PAGE = 1;
    api('GET', API + '/projects/' + PID).then(function (p) { CID = p.company_id; })
      .catch(function () {})
      .then(function () { refreshAll(); });
  };
  el('btn-refresh').onclick = function () { refreshAll(); };
  el('btn-search').onclick = function () { PAGE = 1; loadList(); };
  el('btn-reset').onclick = function () {
    ['f-tax', 'f-level', 'f-state', 'f-period', 'f-amin', 'f-amax', 'f-q', 'f-reviewed']
      .forEach(function (id) { el(id).value = ''; });
    el('f-sort').value = 'priority'; el('f-order').value = 'desc';
    PAGE = 1; loadList();
  };
  el('pg-prev').onclick = function () { if (PAGE > 1) { PAGE--; loadList(); } };
  el('pg-next').onclick = function () {
    if (LAST && PAGE < (LAST.pages || 1)) { PAGE++; loadList(); }
  };
  el('bk-run').onclick = runBulk;
  el('bk-all').onclick = function () {
    (LAST && LAST.items || []).forEach(function (x) { PICKED[x.risk_no || x.seq] = true; });
    renderCheckboxes();
    el('bk-hint').textContent = '已勾选 ' + pickedIds().length + ' 条';
  };
  el('bk-none').onclick = function () {
    PICKED = {};
    renderCheckboxes();
    el('bk-hint').textContent = '已勾选 0 条';
  };
  el('d-close').onclick = closeDrawer;
  el('mask').onclick = closeDrawer;
  document.addEventListener('change', function (ev) {
    var t = ev.target;
    if (t && t.getAttribute && t.getAttribute('data-pick')) {
      PICKED[t.getAttribute('data-pick')] = !!t.checked;
      if (el('bk-hint')) {
        el('bk-hint').textContent = '已勾选 ' + pickedIds().length + ' 条';
      }
    }
  });
  document.addEventListener('click', function (ev) {
    var b = ev.target.closest ? ev.target.closest('[data-open]') : null;
    if (b) { openDetail(b.getAttribute('data-open')); }
  });
});
