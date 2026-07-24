// ==================== 引擎知识中枢 ====================
// 聚合展示所有后端有但前端未独立展示的内容（2026-07-24 老邓要求）
// 全部文字使用蓝色(#2563eb)便于辨认

var _khLoaded = {};
var _khTab = 'audit-knowledge';

function renderKnowledgeHub(container) {
  if (!container) return;
  window.currentModule = '知识中枢';

  var TABS = [
    {id:'audit-knowledge', icon:'📚', name:'稽查知识库', file:'audit_knowledge.json'},
    {id:'industry-data', icon:'🏭', name:'行业基准数据', files:['industry_data.json','industry_profiles.json']},
    {id:'self-heal', icon:'🩹', name:'自愈规则库', file:'self_heal_rules.json'},
    {id:'discovered', icon:'🔍', name:'发现规则库', files:['discovered_rules.json','auto_discovered_rules.json']},
    {id:'cross-memory', icon:'🔗', name:'跨企业关联记忆', file:'cross_analysis_memory.json'},
    {id:'hypotheses', icon:'💡', name:'创造性假说', file:'creative_hypotheses.json'},
    {id:'rectifications', icon:'📝', name:'整改记录', file:'rectifications.json'},
    {id:'report-audits', icon:'📊', name:'报告审计历史', file:'report_audits.json'},
  ];

  var h = '';
  h += '<style>'
    + '.kh-wrap{max-width:1100px;margin:0 auto;padding:20px 24px;background:#fff;font-size:10px;line-height:1.8;color:#2563eb}'
    + '.kh-wrap h2{font-size:20px;font-weight:800;color:#2563eb;margin:0 0 4px}'
    + '.kh-wrap .kh-lead{color:#2563eb;margin:0 0 18px;font-size:12px;opacity:0.75}'
    + '.kh-tabs{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:18px;border-bottom:2px solid #dbeafe;padding-bottom:10px}'
    + '.kh-tab{padding:6px 14px;border-radius:6px;cursor:pointer;background:#eff6ff;color:#2563eb;font-size:10px;font-weight:500;border:1px solid transparent;transition:.15s}'
    + '.kh-tab:hover{background:#dbeafe;font-weight:600}'
    + '.kh-tab.active{background:#2563eb;color:#fff;font-weight:700}'
    + '.kh-body{min-height:400px;color:#2563eb}'
    + '.kh-body .kh-placeholder{text-align:center;padding:80px 20px;color:#2563eb;opacity:0.6}'
    + '.kh-body .kh-spin{display:inline-block;width:24px;height:24px;border:3px solid #dbeafe;border-top-color:#2563eb;border-radius:50%;animation:khSpin 0.8s linear infinite;vertical-align:middle;margin-right:10px}'
    + '@keyframes khSpin{to{transform:rotate(360deg)}}'
    + '.kh-card{background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:14px 18px;margin-bottom:8px;color:#2563eb}'
    + '.kh-card:hover{border-color:#2563eb;box-shadow:0 2px 8px rgba(37,99,235,.1)}'
    + '.kh-card h4{font-size:10px;font-weight:700;color:#2563eb;margin:0 0 6px}'
    + '.kh-card .kh-meta{font-size:10px;color:#2563eb;opacity:0.7;line-height:1.6}'
    + '.kh-card .kh-detail{font-size:10px;color:#2563eb;line-height:1.8;margin-top:6px;padding-top:6px;border-top:1px solid #bfdbfe}'
    + '.kh-table{width:100%;border-collapse:collapse;font-size:10px;color:#2563eb;margin-top:8px}'
    + '.kh-table th{background:#dbeafe;padding:8px 10px;text-align:left;font-weight:700;color:#2563eb;border-bottom:2px solid #bfdbfe}'
    + '.kh-table td{padding:6px 10px;border-bottom:1px solid #bfdbfe;color:#2563eb}'
    + '.kh-table tr:hover{background:#eff6ff}'
    + '.kh-badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600;background:#dbeafe;color:#2563eb}'
    + '.kh-badge.warn{background:#fef3c7;color:#2563eb}'
    + '.kh-badge.ok{background:#d1fae5;color:#2563eb}'
    + '.kh-stat{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;background:#dbeafe;border-radius:6px;margin-right:8px;margin-bottom:4px;font-size:10px;color:#2563eb;font-weight:600}'
    + '.kh-stat .num{font-size:10px;color:#2563eb}'
    + '</style>';

  h += '<div class="kh-wrap">';
  h += '<h2>🧠 引擎知识中枢</h2>';
  h += '<p class="kh-lead">聚合展示引擎后端全部隐藏数据——稽查知识库 · 行业基准 · 自愈规则 · 发现规则 · 关联记忆 · 假说 · 整改 · 审计历史。全部来自静态JSON数据文件，由引擎实时维护。</p>';

  // Tabs
  h += '<div class="kh-tabs">';
  TABS.forEach(function(t, i) {
    h += '<div class="kh-tab" data-khtab="'+t.id+'" onclick="_khSwitch(\''+t.id+'\')">'+t.icon+' '+t.name+'</div>';
  });
  h += '</div>';

  // Body
  h += '<div class="kh-body" id="kh-body"><div class="kh-placeholder"><span class="kh-spin"></span> 加载中...</div></div>';
  h += '</div>';

  container.innerHTML = h;

  // 加载第一个标签
  _khSwitch(TABS[0].id);
  document.querySelector('.kh-tab[data-khtab="'+TABS[0].id+'"]').classList.add('active');
}

window._khSwitch = function(tabId) {
  _khTab = tabId;
  document.querySelectorAll('.kh-tab').forEach(function(el) { el.classList.remove('active'); });
  var el = document.querySelector('.kh-tab[data-khtab="'+tabId+'"]');
  if (el) el.classList.add('active');

  var body = document.getElementById('kh-body');
  if (!body) return;

  body.innerHTML = '<div class="kh-placeholder"><span class="kh-spin"></span> 加载 '+tabId+' 数据...</div>';

  switch(tabId) {
    case 'audit-knowledge': _khLoadAuditKnowledge(body); break;
    case 'industry-data':   _khLoadIndustryData(body); break;
    case 'self-heal':       _khLoadSelfHeal(body); break;
    case 'discovered':      _khLoadDiscovered(body); break;
    case 'cross-memory':    _khLoadCrossMemory(body); break;
    case 'hypotheses':      _khLoadHypotheses(body); break;
    case 'rectifications':  _khLoadRectifications(body); break;
    case 'report-audits':   _khLoadReportAudits(body); break;
  }
};

function _khFetch(file, cb) {
  if (_khLoaded[file]) { cb(_khLoaded[file]); return; }
  fetch('/static/'+file+'?_t='+Date.now())
    .then(function(r) { return r.json(); })
    .then(function(d) { _khLoaded[file] = d; cb(d); })
    .catch(function(e) { cb(null, e); });
}

function _khFetchAll(files, cb) {
  var results = {};
  var loaded = 0;
  files.forEach(function(f) {
    _khFetch(f, function(d, err) {
      results[f] = d;
      loaded++;
      if (loaded >= files.length) cb(results);
    });
  });
}

// ======== 稽查知识库 ========
function _khLoadAuditKnowledge(body) {
  _khFetch('audit_knowledge.json', function(d) {
    if (!d) { body.innerHTML = '<div class="kh-placeholder">⚠ 稽查知识库数据加载失败</div>'; return; }

    var h = '';
    var title = d.title || '稽查知识库';
    var desc = d.description || '';
    var groups = d.groups || [];

    h += '<div class="kh-card"><h4>'+_khEsc(title)+'</h4>';
    h += '<div class="kh-meta">'+_khEsc(desc)+'</div></div>';

    groups.forEach(function(g) {
      h += '<div class="kh-card">';
      h += '<h4>'+_khEsc(g.name||'未命名')+'</h4>';
      if (g.description) h += '<div class="kh-meta">'+_khEsc(g.description)+'</div>';
      var items = g.items || g.rules || [];
      items.forEach(function(it) {
        if (typeof it === 'string') {
          h += '<div class="kh-detail">· '+_khEsc(it)+'</div>';
        } else if (typeof it === 'object') {
          h += '<div class="kh-detail">';
          h += '<b>'+_khEsc(it.title||it.name||it.question||'')+'</b>';
          if (it.answer || it.content || it.description) {
            h += ': '+_khEsc((it.answer||it.content||it.description||'').substring(0,500));
          }
          if (it.tags) h += ' <span class="kh-badge">'+_khEsc(String(it.tags).substring(0,60))+'</span>';
          h += '</div>';
        }
      });
      h += '</div>';
    });

    body.innerHTML = h || '<div class="kh-placeholder">暂无稽查知识库内容</div>';
  });
}

// ======== 行业基准数据 ========
function _khLoadIndustryData(body) {
  _khFetchAll(['industry_data.json','industry_profiles.json'], function(results) {
    var idata = results['industry_data.json'];
    var iprof = results['industry_profiles.json'];

    var h = '';

    // 行业基准
    if (idata && idata.benchmarks) {
      var bm = idata.benchmarks;
      var bmKeys = Object.keys(bm);
      h += '<div class="kh-card"><h4>行业基准数据（'+bmKeys.length+'个行业）</h4>';
      h += '<div class="kh-meta">';
      bmKeys.forEach(function(k) {
        var v = bm[k];
        h += '<span class="kh-stat">'+_khEsc(k)+': <span class="num">';
        if (typeof v === 'object') {
          var pairs = [];
          Object.keys(v).slice(0,3).forEach(function(vk) { pairs.push(vk+'='+v[vk]); });
          h += pairs.join(', ');
        } else {
          h += v;
        }
        h += '</span></span> ';
      });
      h += '</div></div>';
    }

    if (idata && idata.product_chains) {
      h += '<div class="kh-card"><h4>产业链映射</h4>';
      h += '<div class="kh-meta">';
      var pc = idata.product_chains;
      Object.keys(pc).slice(0,10).forEach(function(k) {
        h += '<span class="kh-badge">'+_khEsc(k)+' → '+_khEsc(String(pc[k]).substring(0,60))+'</span> ';
      });
      if (Object.keys(pc).length > 10) h += ' ...共'+Object.keys(pc).length+'条';
      h += '</div></div>';
    }

    if (idata && idata.all_industries) {
      h += '<div class="kh-card"><h4>全行业列表</h4>';
      h += '<div class="kh-meta">';
      var ai = idata.all_industries;
      if (Array.isArray(ai)) {
        ai.forEach(function(ind) { h += '<span class="kh-badge">'+_khEsc(String(ind))+'</span> '; });
      }
      h += '</div></div>';
    }

    if (idata && idata.industry_map) {
      h += '<div class="kh-card"><h4>行业分类映射</h4>';
      h += '<table class="kh-table"><tr><th>大分类</th><th>子行业</th></tr>';
      var im = idata.industry_map;
      Object.keys(im).slice(0,20).forEach(function(k) {
        h += '<tr><td>'+_khEsc(k)+'</td><td>'+_khEsc(String(im[k]).substring(0,200))+'</td></tr>';
      });
      h += '</table></div>';
    }

    // 行业画像
    if (iprof && iprof.industries) {
      h += '<div class="kh-card"><h4>行业画像（'+Object.keys(iprof.industries).length+'个行业）</h4>';
      var inds = iprof.industries;
      Object.keys(inds).slice(0,8).forEach(function(k) {
        var v = inds[k];
        h += '<div class="kh-detail"><b>'+_khEsc(k)+'</b>';
        if (typeof v === 'object') {
          var descKeys = ['profile','特征','description','tax_risks','税务风险','profit_rate_range','毛利率'];
          descKeys.forEach(function(dk) {
            if (v[dk]) h += ' | '+_khEsc(dk)+': '+_khEsc(String(v[dk]).substring(0,120));
          });
        }
        h += '</div>';
      });
      h += '</div>';
    }

    body.innerHTML = h || '<div class="kh-placeholder">暂无行业数据</div>';
  });
}

// ======== 自愈规则库 ========
function _khLoadSelfHeal(body) {
  _khFetch('self_heal_rules.json', function(d) {
    if (!d || !Array.isArray(d)) { body.innerHTML = '<div class="kh-placeholder">⚠ 自愈规则库数据加载失败</div>'; return; }

    var h = '';
    h += '<div class="kh-card"><h4>自愈规则库 · '+d.length+'条规则</h4>';
    h += '<div class="kh-meta">引擎在运行时自动检测数据不一致、逻辑矛盾等异常，发现后自动生成自愈规则并记录。每条规则含触发条件、修复动作和详情。</div></div>';

    h += '<table class="kh-table"><tr><th style="width:80px">时间</th><th>触发条件</th><th>修复动作</th><th>详情</th></tr>';
    d.slice(0,50).forEach(function(r) {
      h += '<tr>';
      h += '<td>'+_khEsc(String(r.timestamp||'').substring(0,10))+'</td>';
      h += '<td>'+_khEsc(String(r.trigger||'').substring(0,120))+'</td>';
      h += '<td>'+_khEsc(String(r.action||'').substring(0,120))+'</td>';
      h += '<td>'+_khEsc(String(r.detail||'').substring(0,150))+'</td>';
      h += '</tr>';
    });
    h += '</table>';
    if (d.length > 50) h += '<div style="padding:10px;color:#2563eb">...共'+d.length+'条，仅显示前50条</div>';

    body.innerHTML = h;
  });
}

// ======== 发现规则库 ========
function _khLoadDiscovered(body) {
  _khFetchAll(['discovered_rules.json','auto_discovered_rules.json'], function(results) {
    var disc = results['discovered_rules.json'] || [];
    var auto = results['auto_discovered_rules.json'] || [];

    var h = '';

    // 自动发现规则
    if (Array.isArray(auto) && auto.length > 0) {
      h += '<div class="kh-card"><h4>自动发现规则 · '+auto.length+'条</h4>';
      h += '<div class="kh-meta">由引擎自动发现模式（行业基准校准/购销倒挂/毛利为负/缺失数据/综合异常）生成的规则，待人工确认转正。</div></div>';

      h += '<table class="kh-table"><tr><th>ID</th><th>名称</th><th>分类</th><th>等级</th><th>评分</th><th>发现类型</th></tr>';
      auto.slice(0,30).forEach(function(r) {
        h += '<tr>';
        h += '<td>'+_khEsc(r.id||'')+'</td>';
        h += '<td>'+_khEsc(String(r.item||'').substring(0,80))+'</td>';
        h += '<td>'+_khEsc(r.category||'')+'</td>';
        h += '<td>'+_khEsc(r.level||'')+'</td>';
        h += '<td>'+_khEsc(String(r.score||''))+'</td>';
        h += '<td><span class="kh-badge">'+_khEsc(r.auto_type||'')+'</span></td>';
        h += '</tr>';
      });
      h += '</table>';
    }

    // 完整发现规则库
    if (Array.isArray(disc) && disc.length > 0) {
      h += '<div class="kh-card"><h4>完整发现规则库 · '+disc.length+'条</h4>';
      h += '<div class="kh-meta">所有自动发现+人工确认的规则，包含类型、行业、风险评分、样本量等元数据。</div></div>';

      h += '<table class="kh-table"><tr><th>类型</th><th>规则ID</th><th>行业</th><th>平均风险</th><th>样本量</th><th>发现时间</th></tr>';
      disc.slice(0,50).forEach(function(r) {
        h += '<tr>';
        h += '<td>'+_khEsc(String(r.type||'').substring(0,40))+'</td>';
        h += '<td>'+_khEsc(String(r.rule_id||''))+'</td>';
        h += '<td>'+_khEsc(String(r.industry||'').substring(0,30))+'</td>';
        h += '<td>'+_khEsc(String(r.avg_risk_score||''))+'</td>';
        h += '<td>'+_khEsc(String(r.sample_size||''))+'</td>';
        h += '<td>'+_khEsc(String(r.discovered_at||'').substring(0,10))+'</td>';
        h += '</tr>';
      });
      h += '</table>';
      if (disc.length > 50) h += '<div style="padding:10px;color:#2563eb">...共'+disc.length+'条，仅显示前50条</div>';
    }

    body.innerHTML = h || '<div class="kh-placeholder">暂无发现规则数据</div>';
  });
}

// ======== 跨企业关联记忆 ========
function _khLoadCrossMemory(body) {
  _khFetch('cross_analysis_memory.json', function(d) {
    if (!d) { body.innerHTML = '<div class="kh-placeholder">⚠ 跨企业关联记忆数据加载失败</div>'; return; }

    var h = '';
    var analyses = d.analyses || [];
    var patterns = d.industry_patterns || {};
    var lessons = d.lesson_learned || [];

    h += '<div class="kh-card"><h4>跨企业分析记忆</h4>';
    h += '<div class="kh-meta">分析记录: '+analyses.length+'条 · 行业模式: '+Object.keys(patterns).length+'种 · 经验教训: '+lessons.length+'条</div></div>';

    if (Array.isArray(analyses) && analyses.length > 0) {
      h += '<div class="kh-card"><h4>分析记录（最近20条）</h4>';
      h += '<table class="kh-table"><tr><th>时间</th><th>企业</th><th>发现数</th><th>关键发现</th></tr>';
      analyses.slice(0,20).forEach(function(a) {
        h += '<tr>';
        h += '<td>'+_khEsc(String(a.timestamp||a.date||'').substring(0,10))+'</td>';
        h += '<td>'+_khEsc(a.company||a.company_name||'')+'</td>';
        h += '<td>'+_khEsc(String(a.finding_count||a.findings||''))+'</td>';
        h += '<td>'+_khEsc(String(a.key_finding||a.summary||'').substring(0,150))+'</td>';
        h += '</tr>';
      });
      h += '</table>';
    }

    if (patterns && Object.keys(patterns).length > 0) {
      h += '<div class="kh-card"><h4>行业模式发现</h4>';
      Object.keys(patterns).slice(0,10).forEach(function(k) {
        var v = patterns[k];
        h += '<div class="kh-detail"><b>'+_khEsc(k)+'</b>: '+(typeof v === 'object' ? _khEsc(JSON.stringify(v).substring(0,300)) : _khEsc(String(v).substring(0,200)))+'</div>';
      });
      h += '</div>';
    }

    if (Array.isArray(lessons) && lessons.length > 0) {
      h += '<div class="kh-card"><h4>经验教训</h4>';
      lessons.slice(0,10).forEach(function(l) {
        h += '<div class="kh-detail">· '+_khEsc(typeof l === 'string' ? l : (l.lesson||l.title||JSON.stringify(l)).substring(0,300))+'</div>';
      });
      h += '</div>';
    }

    body.innerHTML = h || '<div class="kh-placeholder">暂无跨企业关联记忆</div>';
  });
}

// ======== 创造性假说 ========
function _khLoadHypotheses(body) {
  _khFetch('creative_hypotheses.json', function(d) {
    if (!d) { body.innerHTML = '<div class="kh-placeholder">⚠ 创造性假说数据加载失败</div>'; return; }

    var h = '';
    var generated = d.generated || [];
    var verified = d.verified || [];

    h += '<div class="kh-card"><h4>创造性假说</h4>';
    h += '<div class="kh-meta">LLM在分析过程中生成的创造性稽查假说：已生成'+generated.length+'条 · 已验证'+verified.length+'条</div></div>';

    if (Array.isArray(generated) && generated.length > 0) {
      h += '<div class="kh-card"><h4>已生成假说</h4>';
      generated.slice(0,20).forEach(function(g) {
        h += '<div class="kh-detail">';
        if (typeof g === 'string') { h += '· '+_khEsc(g.substring(0,300)); }
        else if (typeof g === 'object') {
          h += '<b>'+_khEsc(g.hypothesis||g.title||'')+'</b>';
          if (g.evidence) h += ' | 证据: '+_khEsc(String(g.evidence).substring(0,150));
          if (g.confidence) h += ' | 置信度: '+_khEsc(String(g.confidence));
          if (g.impact) h += ' | 影响: '+_khEsc(String(g.impact).substring(0,100));
        }
        h += '</div>';
      });
      h += '</div>';
    }

    if (Array.isArray(verified) && verified.length > 0) {
      h += '<div class="kh-card"><h4>已验证假说</h4>';
      verified.slice(0,10).forEach(function(v) {
        h += '<div class="kh-detail">';
        if (typeof v === 'string') { h += '· '+_khEsc(v.substring(0,300)); }
        else { h += '<b>'+_khEsc(v.hypothesis||v.title||'')+'</b>: '+_khEsc((v.result||v.conclusion||'').substring(0,200)); }
        h += '</div>';
      });
      h += '</div>';
    }

    body.innerHTML = h || '<div class="kh-placeholder">暂无创造性假说数据</div>';
  });
}

// ======== 整改记录 ========
function _khLoadRectifications(body) {
  _khFetch('rectifications.json', function(d) {
    if (!d || !Array.isArray(d)) { body.innerHTML = '<div class="kh-placeholder">⚠ 整改记录数据加载失败</div>'; return; }

    var h = '';
    h += '<div class="kh-card"><h4>整改记录 · '+d.length+'条</h4>';
    h += '<div class="kh-meta">系统自动生成的整改任务，含企业信息、发现类型、风险等级、截止日期和当前状态。</div></div>';

    h += '<table class="kh-table"><tr><th>企业</th><th>发现类型</th><th>风险等级</th><th>状态</th><th>截止天数</th><th>详情</th></tr>';
    d.forEach(function(r) {
      h += '<tr>';
      h += '<td>'+_khEsc(r.company_name||'')+'</td>';
      h += '<td>'+_khEsc(String(r.finding_type||'').substring(0,60))+'</td>';
      h += '<td><span class="kh-badge '+(r.risk_level==='极高'||r.risk_level==='高'?'warn':'ok')+'">'+_khEsc(r.risk_level||'')+'</span></td>';
      h += '<td>'+_khEsc(r.status||'')+'</td>';
      h += '<td>'+_khEsc(String(r.deadline_days||''))+'天</td>';
      h += '<td>'+_khEsc(String(r.finding_detail||'').substring(0,120))+'</td>';
      h += '</tr>';
    });
    h += '</table>';

    body.innerHTML = h;
  });
}

// ======== 报告审计历史 ========
function _khLoadReportAudits(body) {
  _khFetch('report_audits.json', function(d) {
    if (!d || !Array.isArray(d)) { body.innerHTML = '<div class="kh-placeholder">⚠ 报告审计历史数据加载失败</div>'; return; }

    var h = '';
    h += '<div class="kh-card"><h4>报告审计历史 · '+d.length+'条</h4>';
    h += '<div class="kh-meta">每次一键分析生成的报告审计记录，含企业名称、发现数量、综合评分、各维度得分和等级评定。</div></div>';

    h += '<table class="kh-table"><tr><th>时间</th><th>企业</th><th>发现数</th><th>综合评分</th><th>严重</th><th>警告</th><th>等级</th><th>各维度</th></tr>';
    d.forEach(function(r) {
      h += '<tr>';
      h += '<td>'+_khEsc(String(r.timestamp||'').substring(0,10))+'</td>';
      h += '<td>'+_khEsc(r.company||'')+'</td>';
      h += '<td>'+_khEsc(String(r.finding_count||''))+'</td>';
      h += '<td>'+_khEsc(String(r.overall_score||''))+'</td>';
      h += '<td>'+_khEsc(String(r.critical_count||''))+'</td>';
      h += '<td>'+_khEsc(String(r.warning_count||''))+'</td>';
      h += '<td><span class="kh-badge">'+_khEsc(r.grade||'')+'</span></td>';
      h += '<td>'+_khEsc(JSON.stringify(r.dimensions||{}).substring(0,150))+'</td>';
      h += '</tr>';
    });
    h += '</table>';

    body.innerHTML = h;
  });
}

function _khEsc(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
