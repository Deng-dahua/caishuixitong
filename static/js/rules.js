/* -*- coding: utf-8 -*-
 * 规则库与风险发现页（P0-5）
 *
 * ★ 契约（后端 `/api/v1`，权威 `engine/rule_catalog.py` / `rule_executor.py` / `risk_scoring.py`）：
 *   GET /api/v1/rules/meta  · /rules/stats · /rules/versions · /rules?… · /rules/{id}
 *   GET /api/v1/risk-scoring/meta
 *   GET /api/v1/risk-findings?company_id=…&level=&q=  · /risk-findings/{seq}?company_id=…
 *   GET /api/v1/rule-executions?company_id=…
 *
 * ★ 中文名一律取后端（`/rules/meta` 与 `/risk-scoring/meta`）——**前端不硬编码**。
 * ★ 「启用/禁用」**不提供开关**：后端明确 `runtime_switch_available=false`
 *   （在库规则的执行权威是 Python 常量，无运行时开关）⇒ 前端只**展示**启用态并如实说明，
 *   **不放一个点了没反应的按钮**。
 */
'use strict';

var API = '/api/v1';
var META = null, SCOPE = null, STATS = null;
var COMPANIES = [], TAB = 'rules';
var RULE_PAGE = 1;

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

function badgeOf(kind) {
  var map = { authoritative: 't-auth', candidate: 't-cand', derived: 't-deriv',
              registry: 't-reg' };
  var label = (META && (META.sources || []).filter(function (s) {
    return s.authority === kind; })[0] || {}).authority_cn || kind;
  return '<span class="tag ' + (map[kind] || 't-reg') + '">' + esc(label) + '</span>';
}

function lvTag(lv) {
  var s = String(lv || '');
  var cls = 'lv-' + s.replace(/[^\u4e00-\u9fa5]/g, '');
  return s ? '<span class="tag ' + cls + '">' + esc(s) + '</span>' : '<span class="muted">—</span>';
}

function pgTag(pg) {
  if (!pg) { return '<span class="muted">—</span>'; }
  return '<span class="tag pg-' + esc(pg) + '">' + esc(pg) + '</span>';
}

// ── 初始化 ──────────────────────────────────────────────────────────────
async function boot() {
  try { META = await api('GET', API + '/rules/meta'); } catch (e) {
    alertBox('err', '规则库字典读取失败：' + e.message); META = { sources: [], layers: [], taxes: [] };
  }
  try { SCOPE = await api('GET', API + '/risk-scoring/meta'); } catch (e) { SCOPE = {}; }
  var sel = el('f-source');
  sel.innerHTML = '<option value="">全部来源</option>' + (META.sources || []).map(function (s) {
    return '<option value="' + esc(s.value) + '">' + esc(s.label) + '</option>'; }).join('');
  el('f-layer').innerHTML = '<option value="">全部层</option>' + (META.layers || []).map(function (s) {
    return '<option value="' + esc(s.value) + '">' + esc(s.label) + '</option>'; }).join('');
  if (!META.runtime_switch_available) {
    alertBox('warn', META.runtime_switch_note || '当前无运行时启用/禁用开关（已如实标注）');
  }
  try {
    var p = await api('GET', API + '/projects?page=1&page_size=200');
    COMPANIES = (p && p.items) || [];
  } catch (e) { COMPANIES = []; }
  el('f-company').innerHTML = COMPANIES.length
    ? COMPANIES.map(function (x) {
        return '<option value="' + esc(x.company_id) + '">' + esc(x.name) + '</option>'; }).join('')
    : '<option value="">（无项目，风险发现需先有账套与报告）</option>';
  try {
    var me = await api('GET', '/api/auth/me');
    el('who').textContent = '当前用户：' + ((me && (me.username || me.user_name)) || '');
  } catch (e) { /* 非关键信息，取不到就不显示 */ }
  await loadStats();
  await loadRules(1);
}

function switchTab(t) {
  TAB = t;
  ['rules', 'findings', 'exec', 'versions'].forEach(function (k) {
    el('pane-' + k).hidden = (k !== t);
    el('tab-' + k).className = 'tab' + (k === t ? ' active' : '');
  });
  if (t === 'findings') { loadFindings(); }
  if (t === 'exec') { loadExec(); }
  if (t === 'versions') { loadVersions(); }
}

// ── 规则库 ──────────────────────────────────────────────────────────────
async function loadStats() {
  try {
    STATS = await api('GET', API + '/rules/stats');
  } catch (e) { STATS = null; return; }
  var cov = STATS.legal_basis_coverage || {};
  var kpis = [
    ['规则主体（权威口径）', STATS.rule_subject_total],
    ['目录总条目', STATS.total_entries],
    ['系统在库（Python）', STATS.python_rules],
    ['候选清单（未入库）', STATS.candidate_rules],
    ['法规依据·真引用', cov.with_real_ref],
    ['法规依据·占位', cov.placeholder],
    ['法规依据·缺失', cov.missing]
  ];
  el('rule-kpis').innerHTML = kpis.map(function (kv) {
    return '<div class="kpi"><div class="v">' + esc(kv[1]) + '</div><div class="k">' + esc(kv[0]) + '</div></div>';
  }).join('');
  if ((STATS.loader_errors || []).length) {
    alertBox('warn', '加载器留痕：' + STATS.loader_errors.join('；'));
  }
}

function resetRuleFilters() {
  el('f-source').value = ''; el('f-layer').value = ''; el('f-q').value = '';
  el('f-enabled').value = '';
  loadRules(1);
}

async function loadRules(page) {
  RULE_PAGE = page || 1;
  var qs = ['page=' + RULE_PAGE, 'page_size=20'];
  if (el('f-source').value) { qs.push('source=' + encodeURIComponent(el('f-source').value)); }
  if (el('f-layer').value) { qs.push('layer=' + encodeURIComponent(el('f-layer').value)); }
  if (el('f-q').value.trim()) { qs.push('q=' + encodeURIComponent(el('f-q').value.trim())); }
  if (el('f-enabled').value) { qs.push('enabled=' + el('f-enabled').value); }
  try {
    var r = await api('GET', API + '/rules?' + qs.join('&'));
    el('rule-count').textContent = '共 ' + r.total + ' 条规则（第 ' + r.page + '/' + (r.pages || 1) + ' 页）';
    if (!r.items.length) {
      el('rule-rows').innerHTML = '<tr><td colspan="10" class="empty">无匹配规则</td></tr>';
    } else {
      el('rule-rows').innerHTML = r.items.map(function (x) {
        var en = (x.enabled === null || x.enabled === undefined)
          ? '<span class="muted">—</span>'
          : (x.enabled ? '<span class="tag t-auth">已启用</span>' : '<span class="tag t-reg">未启用</span>');
        var lb = x.has_legal_basis
          ? '<span class="tag t-auth">有</span>'
          : (x.legal_basis_placeholder ? '<span class="tag t-cand">占位</span>'
                                       : '<span class="problem prob">缺失</span>');
        return '<tr><td>' + esc(x.rule_id) + '</td>'
          + '<td class="wrap">' + esc(x.name) + '</td>'
          + '<td>' + badgeOf(x.authority) + '</td>'
          + '<td class="muted">' + esc(x.layer) + '</td>'
          + '<td>' + esc(x.tax || '') + '</td>'
          + '<td>' + esc(x.severity || '—') + '</td>'
          + '<td>' + esc(x.version || '') + (x.version_registered ? '' : ' <span class="problem prob">(未登记)</span>') + '</td>'
          + '<td>' + en + '</td>'
          + '<td>' + lb + '</td>'
          + '<td><a href="javascript:void(0)" onclick="showRule(\'' + esc(x.rule_id) + '\')">详情</a></td></tr>';
      }).join('');
    }
    var pages = r.pages || 1;
    el('rule-pager').innerHTML =
      '<button onclick="loadRules(' + (r.page - 1) + ')" ' + (r.page <= 1 ? 'disabled' : '') + '>上一页</button>'
      + '<span>第 ' + r.page + ' / ' + pages + ' 页</span>'
      + '<button onclick="loadRules(' + (r.page + 1) + ')" ' + (r.page >= pages ? 'disabled' : '') + '>下一页</button>';
  } catch (e) {
    el('rule-rows').innerHTML = '<tr><td colspan="10" class="empty">加载失败：' + esc(e.message) + '</td></tr>';
  }
}

async function showRule(rid) {
  try {
    var d = await api('GET', API + '/rules/' + encodeURIComponent(rid));
    var refs = (d.legal_basis_ref || []).map(function (r) {
      return '<div>' + esc(r.law || '（未解析出法名）') + (r.article ? ' ' + esc(r.article) : '')
        + (r.placeholder ? ' <span class="tag t-cand">占位</span>' : '')
        + '<div class="muted">' + esc(r.raw || '') + '</div></div>';
    }).join('') || '<div class="problem prob">无任何法规依据（如实为空，非"未登记"）</div>';
    /* ★ 2026-10-15（步骤 19）已确证到具体条款者（含条款正文，可复核） */
    var lp = (d.legal_provisions || []);
    var refsConfirmed = lp.length
      ? lp.map(function (p) {
        return '<div><strong>' + esc(p.provision_id || '') + '</strong> '
          + esc(p.law || '') + ' ' + esc(p.article || '')
          + ' <span class="tag t-reg">已确证</span>'
          + '<div class="muted">' + esc(p.content || '（正文库无原文）') + '</div></div>';
      }).join('')
      : '';
    var inputs = (d.inputs || []).map(function (s) { return '<span class="tag t-reg">' + esc(s) + '</span>'; }).join(' ')
      || '<span class="muted">—</span>';
    var reqs = (d.required_sources || []).map(function (s) { return '<span class="tag t-reg">' + esc(s) + '</span>'; }).join(' ')
      || '<span class="muted">—</span>';
    el('modal-title').textContent = '规则详情 · ' + (d.rule_id || '');
    el('modal-body').innerHTML =
      '<div class="kv">'
      + '<div class="k">规则号</div><div>' + esc(d.rule_id) + '</div>'
      + '<div class="k">名称</div><div>' + esc(d.name) + '</div>'
      + '<div class="k">来源</div><div>' + esc(d.source_cn || '') + ' · ' + esc(d.authority_cn || '') + '</div>'
      + '<div class="k">所属层</div><div>' + esc(d.layer) + '</div>'
      + '<div class="k">税种</div><div>' + esc((d.taxes || []).join('、') || d.tax || '—') + '</div>'
      + '<div class="k">严重度</div><div>' + esc(d.severity || '—') + '</div>'
      + '<div class="k">版本</div><div>' + esc(d.version) + '（' + (d.version_registered ? '已登记' : '<span class="problem prob">未登记</span>') + '）</div>'
      + (d.effective_from ? '<div class="k">生效日</div><div>' + esc(d.effective_from) + '</div>' : '')
      + (d.changed_note ? '<div class="k">变更说明</div><div>' + esc(d.changed_note) + '</div>' : '')
      + '<div class="k">启用态</div><div>' + (d.enabled === null || d.enabled === undefined ? '<span class="muted">—</span>' : (d.enabled ? '已启用' : '未启用')) + '</div>'
      + '</div>'
      + '<div class="sect">法规依据（legal_basis_ref · 规则作者口径）</div>' + refs
      + (refsConfirmed ? '<div class="sect">已确证条款（含条款原文，可复核）</div>' + refsConfirmed : '')
      + '<div class="sect">条件 / 判据</div><div>' + esc(d.condition || '（未登记表达式）') + '</div>'
      + '<div class="sect">依赖字段</div><div>' + inputs + '</div>'
      + '<div class="sect">依赖数据源</div><div>' + reqs + '</div>'
      + '<div class="sect">阈值引用</div><div>' + esc(d.params_ref || '（未登记）') + '</div>'
      + '<div class="sect">原文（可追溯）</div><pre style="white-space:pre-wrap;font-size:12px;background:#f8fafc;padding:8px;border-radius:5px;max-height:240px;overflow:auto">'
      + esc(JSON.stringify(d.raw || {}, null, 2)) + '</pre>';
    el('mask').hidden = false;
  } catch (e) { alertBox('err', '规则详情读取失败：' + e.message); }
}

function closeModal() { el('mask').hidden = true; }

// ── 风险发现 ────────────────────────────────────────────────────────────
function curCompany() { return el('f-company').value || ''; }

async function loadFindings() {
  var cid = curCompany();
  if (!cid) {
    el('find-rows').innerHTML = '<tr><td colspan="9" class="empty">请选择账套</td></tr>';
    return;
  }
  var qs = ['company_id=' + encodeURIComponent(cid)];
  if (el('f-level').value) { qs.push('level=' + encodeURIComponent(el('f-level').value)); }
  if (el('f-fq').value.trim()) { qs.push('q=' + encodeURIComponent(el('f-fq').value.trim())); }
  try {
    var r = await api('GET', API + '/risk-findings?' + qs.join('&'));
    if (!r.available) {
      el('find-rows').innerHTML = '<tr><td colspan="9" class="empty">' + esc(r.reason || '暂无数据') + '</td></tr>';
      el('find-count').textContent = '';
      el('find-note').textContent = '';
      return;
    }
    el('find-note').textContent = r.note || '';
    el('find-count').textContent = '共 ' + r.total + ' 条风险发现';
    if (!r.items.length) {
      el('find-rows').innerHTML = '<tr><td colspan="9" class="empty">无匹配风险发现</td></tr>';
      return;
    }
    el('find-rows').innerHTML = r.items.map(function (x) {
      var sc = (x.priority_score === null || x.priority_score === undefined)
        ? '<span class="muted">—</span>' : String(x.priority_score);
      return '<tr><td>' + esc(x.seq) + '</td>'
        + '<td class="wrap">' + esc(x.title) + '</td>'
        + '<td>' + lvTag(x.risk_level) + '</td>'
        + '<td>' + sc + '</td>'
        + '<td>' + pgTag(x.priority_grade) + '</td>'
        + '<td>' + (x.confidence === null || x.confidence === undefined ? '<span class="muted">—</span>' : esc(Math.round(x.confidence * 100) + '%')) + '</td>'
        + '<td>' + esc(x.redline_id || x.rule_id || '') + '</td>'
        + '<td>' + esc(x.conclusion_grade || '') + '</td>'
        + '<td><a href="javascript:void(0)" onclick="showFinding(' + esc(x.seq) + ')">详情</a></td></tr>';
    }).join('');
  } catch (e) {
    el('find-rows').innerHTML = '<tr><td colspan="9" class="empty">加载失败：' + esc(e.message) + '</td></tr>';
  }
}

async function showFinding(seq) {
  var cid = curCompany();
  if (!cid) { return; }
  try {
    var d = await api('GET', API + '/risk-findings/' + seq + '?company_id=' + encodeURIComponent(cid));
    var f = d.finding || {}, sc = d.scoring || {}, rule = d.rule || {};
    var facs = (sc.factors || []).map(function (x) {
      var st = x.state === 'missing' ? '<span class="problem prob">缺失</span>'
        : (x.state === 'default_one' ? '<span class="tag t-cand">缺省下界</span>' : '');
      return '<tr><td>' + esc(x.name_cn) + '</td><td>' + esc(x.weight) + '</td><td>'
        + (x.value === null ? '—' : esc(x.value)) + '</td><td>' + st + '</td>'
        + '<td class="muted">' + esc(x.source) + '</td></tr>';
    }).join('');
    var evs = {};
    (d.evidences || []).forEach(function (e) { evs[e.kind] = (evs[e.kind] || 0) + 1; });
    var evHtml = Object.keys(evs).map(function (k) {
      return '<span class="tag t-reg">' + esc(k) + ' × ' + evs[k] + '</span>'; }).join(' ') || '<span class="muted">无证据归集</span>';
    var evList = (d.evidences || []).slice(0, 40).map(function (e) {
      return '<div style="font-size:12px;padding:3px 0;border-bottom:1px dashed #f1f5f9">'
        + '<span class="muted">[' + esc(e.kind) + ']</span> ' + esc(e.name || '')
        + (e.status ? ' <span class="muted">' + esc(e.status) + '</span>' : '')
        + (e.detail ? '<div class="muted">' + esc(String(e.detail).slice(0, 160)) + '</div>' : '') + '</div>';
    }).join('');
    var lb = (rule.legal_basis_ref || []).map(function (r) {
      return '<div>' + esc(r.law || '（未解析出法名）') + (r.article ? ' ' + esc(r.article) : '')
        + (r.placeholder ? ' <span class="tag t-cand">占位</span>' : '') + '</div>';
    }).join('') || '<div class="muted">规则未登记法规依据</div>';

    el('modal-title').textContent = '风险详情 · 第 ' + seq + ' 项';
    el('modal-body').innerHTML =
      '<div class="kv">'
      + '<div class="k">标题</div><div>' + esc(f.title) + '</div>'
      + '<div class="k">等级（定性）</div><div>' + lvTag(f.risk_level) + ' <span class="muted">唯一权威 engine/risk_levels.py</span></div>'
      + '<div class="k">综合排序分</div><div><b>' + (sc.priority_score === null ? '—' : esc(sc.priority_score)) + '</b>'
      + ' ' + pgTag(sc.priority_grade) + ' <span class="muted">（只作排序，不改等级）</span></div>'
      + '<div class="k">置信度</div><div>' + (f.confidence === null || f.confidence === undefined ? '—' : esc(Math.round(f.confidence * 100) + '%')) + '</div>'
      + '<div class="k">结论</div><div>' + esc(f.conclusion_grade || '') + ' · ' + esc(f.verdict || '') + '</div>'
      + '<div class="k">红线 / 规则</div><div>' + esc(f.redline_id || '') + (f.rule_id ? ' / ' + esc(f.rule_id) : '') + '</div>'
      + '<div class="k">疑似手法</div><div>' + esc(f.suspect || '') + '</div>'
      + '</div>'
      + '<div class="sect">规则与法规依据</div>'
      + (d.rule_found
          ? '<div class="kv"><div class="k">规则名</div><div>' + esc(rule.name) + '</div>'
            + '<div class="k">层 / 来源</div><div>' + esc(rule.layer) + ' · ' + esc(rule.source_cn || '') + '</div>'
            + '<div class="k">版本</div><div>' + esc(rule.version) + '</div></div>'
            + '<div style="margin-top:6px">' + lb + '</div>'
          : '<div class="msg warn">' + esc(d.note || '规则未在目录中') + '</div>')
      + '<div class="sect">计算过程（综合排序分分项）</div>'
      + '<table class="grid"><thead><tr><th>因子</th><th>权重</th><th>取值</th><th>状态</th><th>来源</th></tr></thead>'
      + '<tbody>' + (facs || '<tr><td colspan="5" class="muted">无分项</td></tr>') + '</tbody></table>'
      + '<div class="muted" style="margin-top:6px">参与权重和 ' + esc(sc.score_basis) + '｜缺失权重和 '
      + esc(sc.missing_weight) + '｜' + esc(sc.note || '') + '</div>'
      + '<div class="sect">证据归集（' + (d.evidences || []).length + ' 条）</div>' + evHtml
      + '<div style="margin-top:6px;max-height:280px;overflow:auto">' + evList + '</div>';
    el('mask').hidden = false;
  } catch (e) { alertBox('err', '风险详情读取失败：' + e.message); }
}

// ── 逐条执行记录 ────────────────────────────────────────────────────────
async function loadExec() {
  var cid = curCompany();
  if (!cid) { el('exec-rows').innerHTML = '<tr><td colspan="4" class="empty">请选择账套</td></tr>'; return; }
  try {
    var r = await api('GET', API + '/rule-executions?company_id=' + encodeURIComponent(cid));
    if (!r.available) {
      el('exec-rows').innerHTML = '<tr><td colspan="4" class="empty">' + esc(r.reason || '暂无数据') + '</td></tr>';
      el('exec-kpis').innerHTML = ''; el('exec-note').textContent = '';
      return;
    }
    var s = r.summary || {};
    el('exec-kpis').innerHTML = [
      ['执行记录总数', s.total], ['已执行', s.executed],
      ['未运行（缺数据源）', s.not_run], ['已跳过（行业不适用）', s.skipped],
      ['执行异常', s.errored]
    ].map(function (kv) {
      return '<div class="kpi"><div class="v">' + esc(kv[1]) + '</div><div class="k">' + esc(kv[0]) + '</div></div>';
    }).join('');
    el('exec-note').textContent = s.note || '';
    var cn = r.status_cn || {};
    el('exec-rows').innerHTML = (r.items || []).map(function (e) {
      return '<tr><td>' + esc(e.rule_id || '—') + '</td><td>' + esc(e.engine || '') + '</td>'
        + '<td>' + esc(cn[e.status] || e.status) + (e.status === 'unknown' ? ' <span class="problem prob">(原值 ' + esc(e.raw_status) + ')</span>' : '') + '</td>'
        + '<td class="wrap muted">' + esc(e.message || e.note || (e.missing_sources ? '缺：' + (e.missing_sources || []).join('、') : '') || '') + '</td></tr>';
    }).join('') || '<tr><td colspan="4" class="empty">无执行记录</td></tr>';
  } catch (e) {
    el('exec-rows').innerHTML = '<tr><td colspan="4" class="empty">加载失败：' + esc(e.message) + '</td></tr>';
  }
}

// ── 规则版本 ────────────────────────────────────────────────────────────
async function loadVersions() {
  try {
    var v = await api('GET', API + '/rules/versions');
    var hist = (v.history || []).map(function (h) {
      return '<div class="logline">' + esc(h.version) + ' · ' + esc(h.date) + ' — ' + esc(h.note || '') + '</div>';
    }).join('');
    var dist = Object.keys(v.by_version || {}).map(function (k) {
      return '<span class="tag t-reg">' + esc(k) + ' × ' + esc(v.by_version[k]) + '</span>'; }).join(' ');
    var layers = v.layer_semantics && v.layer_semantics.layers ? v.layer_semantics.layers : {};
    var lrows = Object.keys(layers).map(function (k) {
      var L = layers[k] || {};
      return '<tr><td>' + esc(k) + '</td><td>' + esc(L.count) + '</td><td>'
        + (L.counts_toward_rule_total ? '<span class="tag t-auth">计入</span>' : '<span class="tag t-reg">不计入</span>')
        + '</td><td class="muted">' + esc(L.note || '') + '</td></tr>';
    }).join('');
    el('ver-card').innerHTML =
      '<div class="kv"><div class="k">当前规则集版本</div><div><b>' + esc(v.rule_set_version) + '</b></div>'
      + '<div class="k">已登记规则数</div><div>' + esc(v.registered_count) + '</div>'
      + '<div class="k">版本分布</div><div>' + dist + '</div></div>'
      + '<div class="sect">版本历史</div>' + (hist || '<div class="muted">无</div>')
      + '<div class="sect">分层口径（唯一权威 layer_semantics）</div>'
      + '<table class="grid"><thead><tr><th>层</th><th>条数</th><th>是否计入规则主体</th><th>说明</th></tr></thead><tbody>'
      + lrows + '</tbody></table>';
  } catch (e) {
    el('ver-card').innerHTML = '<div class="msg err">版本读取失败：' + esc(e.message) + '</div>';
  }
}

el('f-company').addEventListener('change', function () {
  if (TAB === 'findings') { loadFindings(); }
  if (TAB === 'exec') { loadExec(); }
});
window.addEventListener('keydown', function (e) { if (e.key === 'Escape') { closeModal(); } });
boot();
