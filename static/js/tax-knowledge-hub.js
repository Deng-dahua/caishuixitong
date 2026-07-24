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
    {id:'agi-memory', icon:'🧠', name:'AGI记忆', file:'agi_memory.json'},
    {id:'self-heal', icon:'🩹', name:'自愈规则库', file:'self_heal_rules.json'},
    {id:'discovered', icon:'🔍', name:'发现规则库', files:['discovered_rules.json','auto_discovered_rules.json']},
    {id:'cross-memory', icon:'🔗', name:'跨企业关联记忆', file:'cross_analysis_memory.json'},
    {id:'hypotheses', icon:'💡', name:'创造性假说', file:'creative_hypotheses.json'},
    {id:'rule-adjust', icon:'📋', name:'规则修正记录', files:['rule_adjustments.json','methodology_adjustments.json','conflict_rules.json']},
    {id:'rectifications', icon:'📝', name:'整改记录', file:'rectifications.json'},
    {id:'report-audits', icon:'📊', name:'报告审计历史', file:'report_audits.json'},
    {id:'chain-adjust', icon:'🔧', name:'链修正记录', files:['analysis_chain_adjustments.json','clue_chain_adjustments.json','evidence_chain_adjustments.json']},
    {id:'signals-maps', icon:'🗺️', name:'信号与映射', files:['signal_domain_map.json','type_anchors.json','filename_type_map.json']},
    {id:'other-logs', icon:'📜', name:'综合日志', files:['silent_learnings.json','event_log.json','one_shot_rules.json','pattern_confidence.json','system_config.json','metacognition_log.json']},
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
    case 'agi-memory':      _khLoadAgiMemory(body); break;
    case 'rule-adjust':     _khLoadRuleAdjustments(body); break;
    case 'chain-adjust':    _khLoadChainAdjustments(body); break;
    case 'signals-maps':    _khLoadSignalsMaps(body); break;
    case 'other-logs':      _khLoadOtherLogs(body); break;
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

// ======== AGI记忆 ========
function _khLoadAgiMemory(body) {
  _khFetch('agi_memory.json', function(d) {
    if (!d) { body.innerHTML = '<div class="kh-placeholder">⚠ AGI记忆数据加载失败</div>'; return; }
    var h = '';
    var analyses = d.analyses || [];
    var corrections = d.corrections || [];
    var fps = d.fingerprints || {};

    h += '<div class="kh-card"><h4>AGI持久化记忆</h4>';
    h += '<div class="kh-meta">分析记录: '+analyses.length+'条 · 纠正记录: '+corrections.length+'条 · 指纹: '+Object.keys(fps).length+'个</div></div>';

    if (Array.isArray(analyses) && analyses.length > 0) {
      h += '<div class="kh-card"><h4>分析记忆（最近20条）</h4>';
      h += '<table class="kh-table"><tr><th>时间</th><th>企业</th><th>发现数</th><th>关键发现</th></tr>';
      analyses.slice(0,20).forEach(function(a) {
        h += '<tr>';
        h += '<td>'+_khEsc(String(a.timestamp||a.date||'').substring(0,10))+'</td>';
        h += '<td>'+_khEsc(a.company||a.company_name||'')+'</td>';
        h += '<td>'+_khEsc(String(a.finding_count||a.findings||''))+'</td>';
        h += '<td>'+_khEsc(String(a.key_finding||a.summary||'').substring(0,150))+'</td>';
        h += '</tr>';
      });
      h += '</table></div>';
    }

    if (Array.isArray(corrections) && corrections.length > 0) {
      h += '<div class="kh-card"><h4>纠正记录</h4>';
      corrections.slice(0,20).forEach(function(c) {
        h += '<div class="kh-detail">· <b>'+_khEsc(String(c.date||c.timestamp||'').substring(0,10))+'</b>: '+_khEsc(String(c.detail||c.reason||'').substring(0,200))+'</div>';
      });
      h += '</div>';
    }

    body.innerHTML = h;
  });
}

// ======== 规则修正记录 ========
function _khLoadRuleAdjustments(body) {
  _khFetchAll(['rule_adjustments.json','methodology_adjustments.json','conflict_rules.json'], function(results) {
    var radj = results['rule_adjustments.json'] || [];
    var madj = results['methodology_adjustments.json'] || [];
    var confl = results['conflict_rules.json'] || {};

    var h = '';

    // 规则修正
    if (Array.isArray(radj) && radj.length > 0) {
      h += '<div class="kh-card"><h4>规则修正历史 · '+radj.length+'条</h4>';
      h += '<div class="kh-meta">每条规则被触发修正的记录，含规则ID、触发条件、修正动作、目标维度和应用次数。</div></div>';
      h += '<table class="kh-table"><tr><th>规则ID</th><th>触发</th><th>动作</th><th>目标</th><th>维度</th><th>应用次数</th></tr>';
      radj.slice(0,50).forEach(function(r) {
        h += '<tr>';
        h += '<td>'+_khEsc(r.id||r.rule_id||'')+'</td>';
        h += '<td>'+_khEsc(String(r.trigger||'').substring(0,80))+'</td>';
        h += '<td>'+_khEsc(String(r.action||'').substring(0,60))+'</td>';
        h += '<td>'+_khEsc(String(r.target||'').substring(0,60))+'</td>';
        h += '<td><span class="kh-badge">'+_khEsc(r.dimension||'')+'</span></td>';
        h += '<td>'+_khEsc(String(r.applied_count||''))+'</td>';
        h += '</tr>';
      });
      h += '</table>';
      if (radj.length > 50) h += '<div style="padding:10px;color:#2563eb">...共'+radj.length+'条，仅显示前50条</div>';
    }

    // 方法论修正
    if (Array.isArray(madj) && madj.length > 0) {
      h += '<div class="kh-card"><h4>方法论修正记录 · '+madj.length+'条</h4>';
      madj.slice(0,20).forEach(function(m) {
        h += '<div class="kh-detail"><b>'+_khEsc(String(m.timestamp||'').substring(0,10))+'</b>: 调整'+_khEsc(String(m.adjusted_count||''))+'项';
        if (m.top_types) h += ' · 主要类型: '+_khEsc(String(m.top_types).substring(0,150));
        if (m.insight) h += ' · 洞察: '+_khEsc(String(m.insight).substring(0,200));
        h += '</div>';
      });
      h += '</div>';
    }

    // 规则冲突
    if (confl && confl.rules && confl.rules.length > 0) {
      h += '<div class="kh-card"><h4>规则冲突定义 · '+confl.rules.length+'条</h4>';
      confl.rules.slice(0,20).forEach(function(r) {
        h += '<div class="kh-detail">· <b>'+_khEsc(r.name||r.id||'')+'</b>: '+_khEsc(String(r.description||r.condition||'').substring(0,200))+'</div>';
      });
      h += '</div>';
    }

    body.innerHTML = h || '<div class="kh-placeholder">暂无规则修正数据</div>';
  });
}

// ======== 链修正记录 ========
function _khLoadChainAdjustments(body) {
  _khFetchAll(['analysis_chain_adjustments.json','clue_chain_adjustments.json','evidence_chain_adjustments.json'], function(results) {
    var aa = results['analysis_chain_adjustments.json'] || [];
    var ca = results['clue_chain_adjustments.json'] || [];
    var ea = results['evidence_chain_adjustments.json'] || [];

    var h = '';
    var sections = [
      {label:'分析链修正记录', data: aa},
      {label:'线索链修正记录', data: ca},
      {label:'证据链修正记录', data: ea}
    ];

    sections.forEach(function(sec) {
      if (Array.isArray(sec.data) && sec.data.length > 0) {
        h += '<div class="kh-card"><h4>'+sec.label+' · '+sec.data.length+'条</h4>';
        sec.data.slice(0,15).forEach(function(r) {
          h += '<div class="kh-detail"><b>'+_khEsc(String(r.timestamp||'').substring(0,10))+'</b>: 调整'+_khEsc(String(r.adjusted_count||''))+'项';
          if (r.top_types) h += ' · 主要类型: '+_khEsc(String(r.top_types).substring(0,120));
          h += '</div>';
        });
        h += '</div>';
      }
    });

    body.innerHTML = h || '<div class="kh-placeholder">暂无链修正数据</div>';
  });
}

// ======== 信号与映射 ========
function _khLoadSignalsMaps(body) {
  _khFetchAll(['signal_domain_map.json','type_anchors.json','filename_type_map.json'], function(results) {
    var sdm = results['signal_domain_map.json'] || {};
    var ta = results['type_anchors.json'] || {};
    var ftm = results['filename_type_map.json'] || {};

    var h = '';

    // 信号领域映射
    if (sdm.mappings) {
      h += '<div class="kh-card"><h4>信号→领域映射</h4>';
      h += '<table class="kh-table"><tr><th>信号</th><th>领域</th></tr>';
      var mappings = sdm.mappings;
      if (Array.isArray(mappings)) {
        mappings.slice(0,30).forEach(function(m) {
          h += '<tr><td>'+_khEsc(m.signal||m.key||'')+'</td><td>'+_khEsc(m.domain||m.value||'')+'</td></tr>';
        });
      } else {
        Object.keys(mappings).slice(0,30).forEach(function(k) {
          h += '<tr><td>'+_khEsc(k)+'</td><td>'+_khEsc(String(mappings[k]).substring(0,100))+'</td></tr>';
        });
      }
      h += '</table></div>';
    }

    // 类型锚点
    if (ta.anchors) {
      var anchors = ta.anchors;
      h += '<div class="kh-card"><h4>类型锚点映射</h4>';
      h += '<table class="kh-table"><tr><th>锚点类型</th><th>映射值</th></tr>';
      Object.keys(anchors).slice(0,30).forEach(function(k) {
        h += '<tr><td>'+_khEsc(k)+'</td><td>'+_khEsc(String(anchors[k]).substring(0,150))+'</td></tr>';
      });
      h += '</table></div>';
    }

    // 文件名映射
    if (ftm.mappings) {
      var fmappings = ftm.mappings;
      h += '<div class="kh-card"><h4>文件名→数据类型映射</h4>';
      h += '<table class="kh-table"><tr><th>文件名模式</th><th>数据类型</th></tr>';
      Object.keys(fmappings).slice(0,30).forEach(function(k) {
        h += '<tr><td>'+_khEsc(k)+'</td><td>'+_khEsc(String(fmappings[k]).substring(0,100))+'</td></tr>';
      });
      h += '</table></div>';
    }

    body.innerHTML = h || '<div class="kh-placeholder">暂无信号与映射数据</div>';
  });
}

// ======== 综合日志 ========
function _khLoadOtherLogs(body) {
  _khFetchAll(['silent_learnings.json','event_log.json','one_shot_rules.json','pattern_confidence.json','system_config.json','metacognition_log.json'], function(results) {
    var h = '';

    // 系统配置
    var cfg = results['system_config.json'];
    if (cfg && Object.keys(cfg).length > 0) {
      h += '<div class="kh-card"><h4>系统配置</h4>';
      h += '<table class="kh-table"><tr><th>配置项</th><th>值</th></tr>';
      Object.keys(cfg).slice(0,30).forEach(function(k) {
        h += '<tr><td>'+_khEsc(k)+'</td><td>'+_khEsc(String(cfg[k]))+'</td></tr>';
      });
      h += '</table></div>';
    }

    // 静默学习
    var sl = results['silent_learnings.json'];
    if (Array.isArray(sl) && sl.length > 0) {
      h += '<div class="kh-card"><h4>静默学习记录 · '+sl.length+'条</h4>';
      sl.forEach(function(s) {
        h += '<div class="kh-detail"><b>'+_khEsc(s.type||'')+'</b> ['+_khEsc(String(s.learned_at||'').substring(0,10))+']: '+_khEsc(String(s.correction_content||s.trigger||'').substring(0,200));
        h += ' <span class="kh-badge">应用'+_khEsc(String(s.applied_count||'0'))+'次</span></div>';
      });
      h += '</div>';
    }

    // 事件日志
    var el = results['event_log.json'];
    if (el && el.events && Array.isArray(el.events) && el.events.length > 0) {
      h += '<div class="kh-card"><h4>事件日志 · '+el.events.length+'条</h4>';
      h += '<div class="kh-meta">更新于: '+_khEsc(el.updated_at||'')+' · 总计: '+_khEsc(String(el.total_events||''))+'事件</div>';
      el.events.slice(0,30).forEach(function(e) {
        h += '<div class="kh-detail">· <b>'+_khEsc(String(e.time||e.timestamp||'').substring(0,10))+'</b>: '+_khEsc(String(e.event||e.description||e.name||'').substring(0,200))+'</div>';
      });
      h += '</div>';
    }

    // 一次性规则
    var os = results['one_shot_rules.json'];
    if (Array.isArray(os) && os.length > 0) {
      h += '<div class="kh-card"><h4>一次性规则 · '+os.length+'条</h4>';
      os.forEach(function(o) {
        h += '<div class="kh-detail">· '+_khEsc(typeof o === 'string' ? o.substring(0,200) : JSON.stringify(o).substring(0,200))+'</div>';
      });
      h += '</div>';
    }

    // 模式置信度
    var pc = results['pattern_confidence.json'];
    if (pc && Object.keys(pc).length > 0) {
      h += '<div class="kh-card"><h4>模式置信度</h4>';
      h += '<table class="kh-table"><tr><th>模式</th><th>置信度</th></tr>';
      Object.keys(pc).slice(0,30).forEach(function(k) {
        h += '<tr><td>'+_khEsc(k)+'</td><td>'+_khEsc(String(pc[k]))+'</td></tr>';
      });
      h += '</table></div>';
    }

    // 元认知日志
    var mc = results['metacognition_log.json'];
    if (mc && Object.keys(mc).length > 0) {
      h += '<div class="kh-card"><h4>元认知日志</h4>';
      h += '<div class="kh-meta">'+_khEsc(JSON.stringify(mc).substring(0,500))+'</div></div>';
    }

    body.innerHTML = h || '<div class="kh-placeholder">暂无综合日志数据</div>';
  });
}

function _khEsc(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
