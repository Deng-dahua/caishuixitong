// ══════════════════════════════════════════════════════════════
//  稽查管道独立页：文件解析 | 域分析 | 跨域证据链 | 方法论过滤器
// ══════════════════════════════════════════════════════════════

// ==================== 页面1：文件解析 ====================
function renderFileParsingPage(container) {
  if (!container) return;
  window.currentModule = '文件解析';

  container.innerHTML = '<div class="pipeline-page">'
    + '<div class="pipeline-header"><h2>📄 文件解析详情</h2></div>'
    + '<div class="pipeline-body" id="fp-body"><div style="text-align:center;padding:40px;color:#94a3b8">加载中...</div></div>'
    + '</div>';

  loadFileParsingData();
}

async function loadFileParsingData() {
  var cid = typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1;
  try {
    var resp = await fetch('/api/tax-risk-docs/last-analysis?company_id=' + cid);
    var data = await resp.json();
    if (!data.ok) {
      document.getElementById('fp-body').innerHTML = '<div style="text-align:center;padding:40px;color:#94a3b8">⚠️ ' + (data.message || '暂无分析结果') + '</div>';
      return;
    }
    renderFileParsingResult(data.report);
  } catch (e) {
    document.getElementById('fp-body').innerHTML = '<div style="text-align:center;padding:40px;color:#dc2626">加载失败: ' + e.message + '</div>';
  }
}

function renderFileParsingResult(report) {
  var frs = report.file_results || [];
  var plogs = report.pipeline_log || [];

  var html = '';

  // ── 概览卡片 ──
  html += '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px">';
  html += statCard('📁', '文件总数', frs.length, '#2563eb');
  var parsed = frs.filter(function(f) { return f.type !== 'unknown' && !f.error; }).length;
  html += statCard('✅', '解析成功', parsed, '#059669');
  var failed = frs.filter(function(f) { return f.error; }).length;
  html += statCard('❌', '解析失败', failed, '#dc2626');
  html += statCard('📋', '管线日志', plogs.length, '#7c3aed');
  html += '</div>';

  // ── 文件明细表格 ──
  html += '<h3 style="margin:16px 0 8px;font-size:14px;color:#1e293b">文件解析明细</h3>';
  html += '<div style="overflow-x:auto"><table class="pipeline-table">';
  html += '<thead><tr><th>#</th><th>文件名</th><th>识别类型</th><th>提取条数</th><th>解析动作</th><th>状态</th></tr></thead><tbody>';

  frs.forEach(function(fr, i) {
    var typeLabel = fr.type || 'unknown';
    var typeColor = fr.error ? '#dc2626' : (fr.type === 'unknown' ? '#f59e0b' : '#059669');
    var actions = (fr.actions || []).join(', ') || '—';
    // 提取条数
    var rowCount = '';
    if (fr.actions && fr.actions.length) {
      var m = (fr.actions.join(' ')).match(/(\d+)条/);
      if (m) rowCount = m[1] + '条';
    }
    var statusHtml = fr.error
      ? '<span style="color:#dc2626;font-weight:600">❌ 失败</span>'
      : (fr.type === 'unknown'
        ? '<span style="color:#f59e0b">⚠️ 未识别</span>'
        : '<span style="color:#059669">✅ 成功</span>');

    html += '<tr>'
      + '<td>' + (i + 1) + '</td>'
      + '<td style="max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + escHtml(fr.file) + '">' + escHtml(fr.file) + '</td>'
      + '<td><span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;background:' + typeColor + '15;color:' + typeColor + '">' + escHtml(typeLabel) + '</span></td>'
      + '<td>' + (rowCount || '—') + '</td>'
      + '<td style="font-size:11px;color:#64748b">' + escHtml(actions) + '</td>'
      + '<td>' + statusHtml + '</td>'
      + '</tr>';
  });

  html += '</tbody></table></div>';

  // ── 管线日志 ──
  html += '<h3 style="margin:20px 0 8px;font-size:14px;color:#1e293b">分析管线日志</h3>';
  html += '<div style="background:#1e293b;border-radius:8px;padding:16px;max-height:400px;overflow-y:auto;font-family:monospace;font-size:12px;line-height:1.8">';
  plogs.forEach(function(log, i) {
    var color = '#94a3b8';
    if (log.indexOf('异常') >= 0 || log.indexOf('失败') >= 0) color = '#fca5a5';
    else if (log.indexOf('完成') >= 0 || log.indexOf('成功') >= 0) color = '#86efac';
    else if (log.indexOf('发现') >= 0) color = '#fde68a';
    html += '<div style="color:' + color + '">[' + (i + 1) + '] ' + escHtml(log) + '</div>';
  });
  html += '</div>';

  document.getElementById('fp-body').innerHTML = html;
}

// ==================== 页面2：域分析 ====================
function renderDomainAnalysisPage(container) {
  if (!container) return;
  window.currentModule = '域分析';

  container.innerHTML = '<div class="pipeline-page">'
    + '<div class="pipeline-header"><h2>🔍 域分析结果</h2></div>'
    + '<div class="pipeline-body" id="da-body"><div style="text-align:center;padding:40px;color:#94a3b8">加载中...</div></div>'
    + '</div>';

  loadDomainAnalysisData();
}

async function loadDomainAnalysisData() {
  var cid = typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1;
  try {
    var resp = await fetch('/api/tax-risk-docs/last-analysis?company_id=' + cid);
    var data = await resp.json();
    if (!data.ok) {
      document.getElementById('da-body').innerHTML = '<div style="text-align:center;padding:40px;color:#94a3b8">⚠️ ' + (data.message || '暂无分析结果') + '</div>';
      return;
    }
    renderDomainAnalysisResult(data.report);
  } catch (e) {
    document.getElementById('da-body').innerHTML = '<div style="text-align:center;padding:40px;color:#dc2626">加载失败: ' + e.message + '</div>';
  }
}

function renderDomainAnalysisResult(report) {
  var ds = report.domain_summary || [];
  var allF = report.all_findings || [];

  // 按域分组 findings
  var domainMap = {};
  ds.forEach(function(d) {
    domainMap[d.name] = { count: d.count, high: d.high, mid: d.mid, findings: d.findings || [] };
  });

  var totalDomains = Object.keys(domainMap).length;
  var triggeredDomains = Object.values(domainMap).filter(function(d) { return d.count > 0; }).length;

  // ── 概览 ──
  var html = '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px">';
  html += statCard('🔍', '分析域数', totalDomains, '#2563eb');
  html += statCard('⚡', '触发域数', triggeredDomains, '#7c3aed');
  html += statCard('⚠️', '总发现', allF.length, '#dc2626');
  var highTotal = allF.filter(function(f) { return f.level === '高风险'; }).length;
  html += statCard('🔴', '高风险', highTotal, '#dc2626');
  html += '</div>';

  // ── 域网格 ──
  html += '<h3 style="margin:16px 0 8px;font-size:14px;color:#1e293b">分析域概览 · 点击展开详情</h3>';
  html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px">';

  var domainNames = Object.keys(domainMap).sort(function(a, b) {
    return (domainMap[b].high * 2 + domainMap[b].mid) - (domainMap[a].high * 2 + domainMap[a].mid);
  });

  domainNames.forEach(function(name, di) {
    var d = domainMap[name];
    var hasFindings = d.count > 0;
    var borderColor = d.high > 0 ? '#dc2626' : (d.mid > 0 ? '#f59e0b' : (hasFindings ? '#059669' : '#94a3b8'));
    var bgColor = d.high > 0 ? '#fef2f2' : (d.mid > 0 ? '#fffbeb' : (hasFindings ? '#f0fdf4' : '#f8fafc'));
    var dotColor = d.high > 0 ? '🔴' : (d.mid > 0 ? '🟡' : (hasFindings ? '🟢' : '⚪'));

    html += '<div class="domain-card" id="dc-' + di + '" style="border:2px solid ' + borderColor + ';background:' + bgColor + ';border-radius:10px;padding:14px;cursor:' + (hasFindings ? 'pointer' : 'default') + ';transition:all .2s" onclick="' + (hasFindings ? 'toggleDomainDetail(' + di + ')' : '') + '">'
      + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">'
      + '<span style="font-weight:700;font-size:13px;color:#1e293b">' + escHtml(name) + '</span>'
      + '<span style="font-size:20px">' + dotColor + '</span>'
      + '</div>'
      + '<div style="display:flex;gap:12px;font-size:11px;color:#64748b">'
      + '<span>发现 <b style="color:' + (d.count > 0 ? '#1e293b' : '#94a3b8') + '">' + d.count + '</b> 条</span>'
      + '<span>高 <b style="color:#dc2626">' + d.high + '</b></span>'
      + '<span>中 <b style="color:#f59e0b">' + d.mid + '</b></span>'
      + '</div>';

    if (hasFindings) {
      html += '<div id="dd-' + di + '" style="display:none;margin-top:12px;border-top:1px dashed #e2e8f0;padding-top:8px">';
      d.findings.slice(0, 10).forEach(function(f, fi) {
        var lvlColor = f.level === '高风险' ? '#dc2626' : (f.level === '中风险' ? '#f59e0b' : '#059669');
        html += '<div style="margin-bottom:8px;font-size:11px;line-height:1.6">'
          + '<span style="display:inline-block;padding:1px 6px;border-radius:3px;background:' + lvlColor + '15;color:' + lvlColor + ';font-weight:600;margin-right:6px">' + (f.level || '—') + '</span>'
          + '<b>' + escHtml((f.type || '').substring(0, 30)) + '</b>'
          + '<div style="color:#64748b;margin-top:2px">' + escHtml((f.detail || '').substring(0, 120)) + '</div>'
          + '</div>';
      });
      if (d.count > 10) html += '<div style="font-size:10px;color:#94a3b8;text-align:center">... 还有 ' + (d.count - 10) + ' 条发现</div>';
      html += '</div>';
    }

    html += '</div>';
  });

  html += '</div>';

  document.getElementById('da-body').innerHTML = html;
}

// ==================== 页面3：跨域证据链 ====================
function renderCrossDomainEvidencePage(container) {
  if (!container) return;
  window.currentModule = '跨域证据链';

  container.innerHTML = '<div class="pipeline-page">'
    + '<div class="pipeline-header"><h2>🔗 跨域证据链</h2></div>'
    + '<div class="pipeline-body" id="cde-body"><div style="text-align:center;padding:40px;color:#94a3b8">加载中...</div></div>'
    + '</div>';

  loadCrossDomainEvidenceData();
}

async function loadCrossDomainEvidenceData() {
  var cid = typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1;
  try {
    var resp = await fetch('/api/tax-risk-docs/last-analysis?company_id=' + cid);
    var data = await resp.json();
    if (!data.ok) {
      document.getElementById('cde-body').innerHTML = '<div style="text-align:center;padding:40px;color:#94a3b8">⚠️ ' + (data.message || '暂无分析结果') + '</div>';
      return;
    }
    renderCrossDomainResult(data.report);
  } catch (e) {
    document.getElementById('cde-body').innerHTML = '<div style="text-align:center;padding:40px;color:#dc2626">加载失败: ' + e.message + '</div>';
  }
}

function renderCrossDomainResult(report) {
  var allF = report.all_findings || [];
  var domainSummary = report.domain_summary || [];
  var comprehensive = report.comprehensive || {};

  // 从跨域关联推理域提取证据链
  var crossDomainFindings = [];
  var crossDomainDS = null;
  domainSummary.forEach(function(ds) {
    if (ds.name && ds.name.indexOf('跨域关联推理') >= 0) {
      crossDomainDS = ds;
      crossDomainFindings = ds.findings || [];
    }
  });

  // 也从 all_findings 中找证据链类型
  var evidenceFindings = allF.filter(function(f) {
    var t = f.type || '';
    return t.indexOf('证据链') >= 0 || t.indexOf('隐匿收入') >= 0 || t.indexOf('虚开发票') >= 0 || t.indexOf('无实质经营') >= 0 || t.indexOf('会计基础') >= 0 || t.indexOf('资金链') >= 0 || t.indexOf('利润现金流') >= 0 || t.indexOf('发票异常') >= 0;
  });

  var allEvidence = [];
  var seen = {};
  crossDomainFindings.forEach(function(f) {
    var key = f.type || '';
    if (!seen[key]) { seen[key] = true; allEvidence.push(f); }
  });
  evidenceFindings.forEach(function(f) {
    var key = f.type || '';
    if (!seen[key]) { seen[key] = true; allEvidence.push(f); }
  });

  // 从 comprehensive 获取证据链闭环+触发信息
  var closures = comprehensive.evidence_closures || [];
  var closedCount = comprehensive.closed_chain_count || 0;
  var triggeredChains = comprehensive.triggered_chains || [];
  var chainExecution = comprehensive.chain_execution || [];

  // ── 概览 ──
  var html = '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px">';
  html += statCard('🔗', '跨域证据链', allEvidence.length, '#7c3aed');
  html += statCard('🔒', '已闭环', closedCount, closedCount >= 3 ? '#dc2626' : '#f59e0b');
  html += statCard('📊', '触发线索链', chainExecution.length, '#2563eb');
  html += statCard('🎯', '含规则ID链', triggeredChains.length, '#059669');
  html += '</div>';

  // ── 证据链闭环详情 ──
  if (closures.length > 0) {
    html += '<h3 style="margin:16px 0 8px;font-size:14px;color:#1e293b">证据链闭环检测 <span style="font-size:11px;color:#94a3b8">（≥60%规则触发+≥2域交叉=闭环）</span></h3>';
    closures.forEach(function(ec, ei) {
      var isClosed = ec.closed;
      var ratioColor = isClosed ? '#dc2626' : '#f59e0b';
      var borderColor = isClosed ? '#dc2626' : '#f59e0b';
      var bgColor = isClosed ? '#fef2f2' : '#fffbeb';

      html += '<div style="border:2px solid ' + borderColor + ';background:' + bgColor + ';border-radius:10px;padding:16px;margin-bottom:12px">'
        + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">'
        + '<b style="font-size:14px;color:#1e293b">' + escHtml(ec.chain_name) + '</b>'
        + '<span style="display:inline-block;padding:3px 10px;border-radius:4px;background:' + ratioColor + '15;color:' + ratioColor + ';font-size:12px;font-weight:700">'
        + (isClosed ? '🔒 已闭环' : '⚠️ 未闭环') + ' ' + ec.ratio + '%'
        + '</span>'
        + '</div>'
        + '<div style="font-size:11px;color:#64748b;margin-bottom:8px">触发 <b>' + ec.triggered_steps + '</b>/' + ec.total_steps + ' 条规则</div>';

      if (ec.steps && ec.steps.length) {
        html += '<div style="display:flex;gap:6px;flex-wrap:wrap">';
        ec.steps.forEach(function(step) {
          var stepColor = step.triggered ? '#059669' : '#94a3b8';
          var stepBg = step.triggered ? '#f0fdf4' : '#f8fafc';
          html += '<div style="padding:4px 10px;border-radius:4px;background:' + stepBg + ';border:1px solid ' + stepColor + ';font-size:10px">'
            + '<span style="color:' + stepColor + ';font-weight:600">' + (step.triggered ? '✓' : '○') + '</span> '
            + escHtml(step.step.substring(0, 24))
            + (step.rule_id ? ' <span style="color:#94a3b8">R' + step.rule_id + '</span>' : '')
            + '</div>';
        });
        html += '</div>';
      }

      html += '</div>';
    });
  }

  // ── 跨域证据链详细内容 ──
  html += '<h3 style="margin:20px 0 8px;font-size:14px;color:#1e293b">跨域关联推理详情</h3>';

  if (allEvidence.length === 0) {
    html += '<div style="text-align:center;padding:20px;color:#94a3b8;background:#f8fafc;border-radius:8px">暂无跨域证据链数据</div>';
  } else {
    allEvidence.forEach(function(f, ei) {
      var isChain = (f.type || '').indexOf('证据链') >= 0;
      var borderColor = isChain ? '#7c3aed' : (f.level === '高风险' ? '#dc2626' : '#f59e0b');
      var bgColor = isChain ? '#f5f3ff' : '#fff';
      var dotColor = f.level === '高风险' ? '🔴' : (f.level === '中风险' ? '🟡' : '🟢');

      html += '<div style="border:2px solid ' + borderColor + ';background:' + bgColor + ';border-radius:10px;padding:16px;margin-bottom:12px">'
        + '<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px">'
        + '<div>'
        + '<span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;background:' + borderColor + '15;color:' + borderColor + ';margin-right:8px">' + escHtml(f.level || '—') + '</span>'
        + '<b style="font-size:14px;color:#1e293b">' + escHtml(f.type || '') + '</b>'
        + '</div>'
        + '<span style="font-size:18px">' + dotColor + '</span>'
        + '</div>';

      // description
      if (f.description) {
        html += '<div style="font-size:12px;color:#475569;line-height:1.8;margin-bottom:8px;padding:10px;background:#f8fafc;border-radius:6px">' + escHtml(f.description.substring(0, 400)) + '</div>';
      }

      // how_found (溯源)
      if (f.how_found) {
        html += '<div style="font-size:11px;color:#64748b;margin-bottom:6px">📌 <b>溯源：</b>' + escHtml(f.how_found.substring(0, 200)) + '</div>';
      }

      // tax_impact
      if (f.tax_impact) {
        html += '<div style="font-size:11px;color:#991b1b;margin-bottom:6px">💸 <b>纳税影响：</b>' + escHtml(f.tax_impact.substring(0, 200)) + '</div>';
      }

      // policy_ref
      if (f.policy_ref) {
        html += '<div style="font-size:11px;color:#1e40af;margin-bottom:6px">📜 <b>法律依据：</b>' + escHtml(f.policy_ref.substring(0, 200)) + '</div>';
      }

      // suggestion
      if (f.suggestion) {
        html += '<div style="font-size:11px;color:#059669;padding:8px;background:#f0fdf4;border-radius:6px">✅ <b>处理建议：</b>' + escHtml(f.suggestion.substring(0, 200)) + '</div>';
      }

      // 域交叉信息
      if (f.cross_domains) {
        html += '<div style="margin-top:8px;font-size:10px;color:#7c3aed">跨越 <b>' + f.cross_domains + '</b> 个分析域</div>';
      }

      html += '</div>';
    });
  }

  // ── 触发线索链TOP20 ──
  if (chainExecution.length > 0) {
    html += '<h3 style="margin:20px 0 8px;font-size:14px;color:#1e293b">触发线索链 TOP' + Math.min(20, chainExecution.length) + '</h3>';
    html += '<div style="overflow-x:auto"><table class="pipeline-table">';
    html += '<thead><tr><th>线索链名称</th><th>触发/总步数</th><th>触发率</th></tr></thead><tbody>';
    chainExecution.slice(0, 20).forEach(function(ce) {
      var ratioColor = ce.triggered_ratio >= 80 ? '#dc2626' : (ce.triggered_ratio >= 50 ? '#f59e0b' : '#059669');
      html += '<tr>'
        + '<td style="max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + escHtml(ce.chain_name) + '">' + escHtml(ce.chain_name) + '</td>'
        + '<td><b>' + ce.triggered_steps + '</b> / ' + ce.total_steps + '</td>'
        + '<td><span style="color:' + ratioColor + ';font-weight:700">' + ce.triggered_ratio + '%</span></td>'
        + '</tr>';
    });
    html += '</tbody></table></div>';
  }

  document.getElementById('cde-body').innerHTML = html;
}

// ==================== 工具函数 ====================
function statCard(icon, label, value, color) {
  return '<div style="flex:1;min-width:100px;background:#fff;border:2px solid ' + color + ';border-radius:10px;padding:14px;text-align:center">'
    + '<div style="font-size:24px;margin-bottom:4px">' + icon + '</div>'
    + '<div style="font-size:22px;font-weight:700;color:' + color + '">' + value + '</div>'
    + '<div style="font-size:11px;color:#64748b">' + label + '</div>'
    + '</div>';
}

function escHtml(s) {
  if (!s) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function toggleDomainDetail(idx) {
  var el = document.getElementById('dd-' + idx);
  if (!el) return;
  el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

// ==================== 页面4：方法论过滤器 ====================
function renderMethodologyFilterPage(container) {
  if (!container) return;
  window.currentModule = '方法论过滤器';

  container.innerHTML = '<div class="pipeline-page">'
    + '<div class="pipeline-header"><h2>🎯 方法论过滤器</h2></div>'
    + '<div class="pipeline-body" id="mf-body"><div style="text-align:center;padding:40px;color:#94a3b8">加载中...</div></div>'
    + '</div>';

  loadMethodologyFilterData();
}

async function loadMethodologyFilterData() {
  var cid = typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1;
  try {
    var resp = await fetch('/api/tax-risk-docs/last-analysis?company_id=' + cid);
    var data = await resp.json();
    if (!data.ok) {
      document.getElementById('mf-body').innerHTML = '<div style="text-align:center;padding:40px;color:#94a3b8">⚠️ ' + (data.message || '暂无分析结果') + '</div>';
      return;
    }
    renderFilterResult(data.report);
  } catch (e) {
    document.getElementById('mf-body').innerHTML = '<div style="text-align:center;padding:40px;color:#dc2626">加载失败: ' + e.message + '</div>';
  }
}

var FILTER_RULE_NAMES = {
  '自动生成证据链': '证据链自动生成结论（非真实发现）',
  '正常结论': '正常/一致/通过类结论（无风险）',
  '资料缺口超限': '资料缺口类过多（上限5条，非核心发现）',
  '重复发现去重': '同类型重复发现合并',
  '行业不匹配': '发现内容与当前企业行业不匹配',
};

function renderFilterResult(report) {
  var comp = report.comprehensive || {};
  var fl = comp.filter_log;
  if (!fl) {
    document.getElementById('mf-body').innerHTML = '<div style="text-align:center;padding:40px;color:#94a3b8">⚠️ 暂无过滤记录（需重新运行一键分析）</div>';
    return;
  }

  var removedItems = fl.removed_items || [];
  var breakdown = fl.reason_breakdown || {};
  var totalRemoved = fl.total_removed || 0;

  var html = '';

  // ── 概览卡片 ──
  html += '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px">';
  html += statCard('📥', '过滤前', fl.before_count || 0, '#2563eb');
  html += statCard('📤', '过滤后', fl.after_count || 0, '#059669');
  html += statCard('🗑️', '已剔除', totalRemoved, '#dc2626');
  html += statCard('📊', '噪声率', (fl.noise_ratio || 0) + '%', '#7c3aed');
  html += '</div>';

  // ── 过滤规则说明 ──
  html += '<h3 style="margin:16px 0 8px;font-size:14px;color:#1e293b">过滤规则体系</h3>';
  html += '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:8px;margin-bottom:16px">';

  var rules = [
    { title: '① HARD_BAN 硬删除', desc: '禁止词命中（涉税中介/公安/刑事/空壳/走逃/伪造/私户等40+词）→ 立即删除', color: '#dc2626' },
    { title: '② COND_BAN 条件过滤', desc: '数据缺失触发——无申报表→删申报相关结论，无合同→删合同相关，无凭证→删成本核算类', color: '#f59e0b' },
    { title: '③ 正常结论排除', desc: 'type含"一致/正常/无明显差异/通过/良好/合规/无异常"→删除', color: '#059669' },
    { title: '④ 资料缺口限流', desc: '资料缺少/缺失/无法验证/不完备类最多保留5条，超限删除', color: '#2563eb' },
    { title: '⑤ 行业不匹配', desc: '非本行业的专业发现（如纺织企业不报医药/房地产/建筑/餐饮/电商等）→删除', color: '#7c3aed' },
    { title: '⑥ 去重合并', desc: '同type前60字完全相同的发现→只保留第一条', color: '#0891b2' },
  ];

  rules.forEach(function(r) {
    html += '<div style="border:1px solid ' + r.color + ';background:' + r.color + '08;border-radius:8px;padding:12px">'
      + '<div style="font-weight:700;font-size:13px;color:' + r.color + ';margin-bottom:4px">' + r.title + '</div>'
      + '<div style="font-size:11px;color:#64748b;line-height:1.6">' + r.desc + '</div>'
      + '</div>';
  });

  html += '</div>';

  // ── 剔除原因分布 ──
  html += '<h3 style="margin:20px 0 8px;font-size:14px;color:#1e293b">剔除原因分布</h3>';
  if (Object.keys(breakdown).length === 0) {
    html += '<div style="text-align:center;padding:12px;color:#94a3b8;background:#f8fafc;border-radius:8px">本次无剔除</div>';
  } else {
    html += '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px">';
    var breakdownEntries = Object.entries(breakdown).sort(function(a, b) { return b[1] - a[1]; });
    breakdownEntries.forEach(function(entry) {
      var reason = entry[0], count = entry[1];
      var pct = totalRemoved > 0 ? Math.round(count / totalRemoved * 100) : 0;
      var barWidth = Math.max(3, pct);
      var color = reason.indexOf('禁止词') >= 0 ? '#dc2626' : (reason.indexOf('无') >= 0 ? '#f59e0b' : (reason.indexOf('行业') >= 0 ? '#7c3aed' : '#059669'));
      html += '<div style="flex:1;min-width:160px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:10px">'
        + '<div style="font-size:11px;color:#64748b;margin-bottom:4px">' + escHtml(reason) + '</div>'
        + '<div style="display:flex;align-items:center;gap:8px">'
        + '<span style="font-size:20px;font-weight:700;color:' + color + '">' + count + '</span>'
        + '<span style="font-size:11px;color:#94a3b8">' + pct + '%</span>'
        + '</div>'
        + '<div style="margin-top:4px;height:4px;background:#f1f5f9;border-radius:2px">'
        + '<div style="height:100%;width:' + barWidth + '%;background:' + color + ';border-radius:2px"></div>'
        + '</div>'
        + '</div>';
    });
    html += '</div>';
  }

  // ── 详细剔除明细 ──
  html += '<h3 style="margin:20px 0 8px;font-size:14px;color:#1e293b">剔除明细 <span style="font-size:11px;color:#94a3b8">（共' + removedItems.length + '条）</span></h3>';

  if (removedItems.length === 0) {
    html += '<div style="text-align:center;padding:20px;color:#94a3b8;background:#f8fafc;border-radius:8px">无剔除记录</div>';
  } else {
    html += '<div style="overflow-x:auto"><table class="pipeline-table">';
    html += '<thead><tr><th>#</th><th>发现类型</th><th>等级</th><th>分数</th><th>剔除原因</th><th>分类</th></tr></thead><tbody>';

    // 按原因分组显示
    var grouped = {};
    removedItems.forEach(function(item) {
      var r = item.reason || '未知';
      if (!grouped[r]) grouped[r] = [];
      grouped[r].push(item);
    });

    var idx = 0;
    Object.keys(grouped).sort(function(a, b) { return grouped[b].length - grouped[a].length; }).forEach(function(reason) {
      var items = grouped[reason];
      // 显示该组标题
      var reasonLabel = FILTER_RULE_NAMES[reason] || reason;
      var reasonColor = reason.indexOf('禁止词') >= 0 ? '#dc2626' : (reason.indexOf('无') >= 0 ? '#f59e0b' : (reason.indexOf('行业') >= 0 ? '#7c3aed' : (reason.indexOf('重复') >= 0 ? '#0891b2' : '#059669')));
      html += '<tr style="background:' + reasonColor + '06"><td colspan="6" style="padding:8px 12px;font-size:11px;font-weight:600;color:' + reasonColor + '">'
        + '▸ ' + escHtml(reasonLabel) + ' <span style="color:#94a3b8;font-weight:400">(' + items.length + '条)</span>'
        + '</td></tr>';

      items.forEach(function(item) {
        idx++;
        var lvlColor = item.level === '高风险' ? '#dc2626' : (item.level === '中风险' ? '#f59e0b' : '#64748b');
        html += '<tr>'
          + '<td>' + idx + '</td>'
          + '<td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + escHtml(item.type) + '">' + escHtml(item.type) + '</td>'
          + '<td><span style="color:' + lvlColor + ';font-weight:600">' + escHtml(item.level || '—') + '</span></td>'
          + '<td>' + (item.score || '—') + '</td>'
          + '<td style="font-size:11px;color:#64748b">' + escHtml(reason) + '</td>'
          + '<td style="font-size:10px;color:#94a3b8">' + escHtml((item.category || '').substring(0, 20)) + '</td>'
          + '</tr>';
      });
    });

    html += '</tbody></table></div>';
  }

  document.getElementById('mf-body').innerHTML = html;
}
