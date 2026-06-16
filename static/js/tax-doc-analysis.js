// ==================== 涉税资料分析模块 ====================
var taxDocReportData = null;
var taxDocAnalyzing = false;
var taxDocPageActive = false;

// 确保 esc 可用
if (typeof esc === 'undefined') {
  var esc = function(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); };
}

function renderTaxDocAnalysis(container) {
  window.currentModule = '资料风险分析报告';
  taxDocPageActive = true;  // 标记页面激活

  container.innerHTML = ''
    + '<div class="risk-report-container">'
    
    // ── 标题区 ──
    + '<div class="risk-report-header">'
    + '<h2>资料风险分析报告</h2>'
    + '</div>'

    // ── 资料上传区 ──
    + '<div id="tda-upload-section" style="background:#f8fafc;border:2px dashed #cbd5e1;border-radius:10px;padding:20px 24px;margin-bottom:20px">'
    + '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">'
    + '<div>'
    + '<span style="font-weight:600;font-size:16px">上传经营资料 <span id="tda-file-count" style="color:var(--gray-400);font-weight:400;font-size:14px">(0 份)</span></span>'
    + '<span style="font-size:12px;color:var(--gray-400);margin-left:12px">支持 Excel / PDF 格式，可多文件同时上传</span>'
    + '</div>'
    + '<div style="display:flex;gap:10px">'
    + '<label class="btn-toolbar" for="tda-file-input" style="cursor:pointer">'
    + '<input type="file" id="tda-file-input" multiple style="display:none" onchange="uploadTaxDocs()">上传资料</label>'
    + '<button class="btn-toolbar" onclick="batchDelTdaDocs()">删除选中资料</button>'
    + '<button class="btn-toolbar" onclick="analyzeTaxDocs()" id="tda-analyze-btn">一键分析</button>'
    + '<button class="btn-toolbar" onclick="reviewTaxDocReport()" id="tda-review-btn" style="color:#0369a1;border-color:#93c5fd;background:#eff6ff">报告复核</button>'
    + '<button class="btn-toolbar" onclick="exportTaxDocReport()" id="tda-export-btn">导出报告</button>'
    + '<button class="btn-toolbar" onclick="deleteTaxDocReport()" id="tda-delete-btn" style="color:#dc2626;border-color:#fca5a5;background:#fef2f2">删除报告</button>'
    + '</div></div>'
    
    // ── 文件列表 ──
    + '<div id="tda-file-list" style="font-size:13px;color:var(--gray-500);min-height:40px">暂无上传资料</div>'
    + '</div>'
    
    // ── 分析结果区 ──
    + '<div id="tda-report-area"></div>'
    + '</div>';

  // 加载已有文件列表
  refreshTaxDocList();

  // 如果有之前的报告数据，恢复显示
  if (taxDocReportData) {
    setTimeout(function() { renderTaxDocReport(taxDocReportData); }, 200);
  }
}

// ==================== 文件上传 ====================
async function uploadTaxDocs() {
  var input = document.getElementById('tda-file-input');
  if (!input || !input.files || input.files.length === 0) return;

  var formData = new FormData();
  for (var i = 0; i < input.files.length; i++) {
    formData.append('files', input.files[i]);
  }

  var btn = document.getElementById('tda-analyze-btn');
  try {
    btn.disabled = true; btn.textContent = '上传中...';
    var resp = await fetch('/api/tax-risk-docs/upload?company_id=' + (typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1), {
      method: 'POST', body: formData
    });
    var data = await resp.json();
    if (data.ok) {
      toast('成功上传 ' + input.files.length + ' 个文件', 'success');
    } else {
      toast(data.message || '上传失败', 'error');
    }
    input.value = '';
    refreshTaxDocList();
  } catch (e) {
    toast('上传失败: ' + e.message, 'error');
  } finally {
    btn.disabled = false; btn.textContent = '一键分析';
  }
}

// ==================== 文件列表 ====================
async function refreshTaxDocList() {
  try {
    var resp = await fetch('/api/tax-risk-docs/list?company_id=' + (typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1));
    var docs = await resp.json();
    var listEl = document.getElementById('tda-file-list');
    if (!listEl) return;

    // 更新文件数量显示
    var countEl = document.getElementById('tda-file-count');
    if (countEl) countEl.textContent = '(' + (docs ? docs.length : 0) + ' 份)';

    if (!docs || docs.length === 0) {
      listEl.innerHTML = '<div style="text-align:center;padding:20px;color:var(--gray-400)">暂无上传资料，请点击上方按钮上传</div>';
      return;
    }

    var html = '<div style="margin-bottom:4px"><label><input type="checkbox" onchange="toggleAllTdaDocs(this)" style="margin-right:4px">全选</label> <span style="color:#94a3b8;font-size:10px">共 ' + docs.length + ' 个</span></div>';
    try {
      docs.forEach(function(doc, idx) {
        var size = doc.size ? (doc.size / 1024).toFixed(1) + ' KB' : '未知';
        var name = doc.original_name || doc.filename || '未知文件';
        var rowInfo = '';
        // 如果有分析结果，从 _reportFileRows 获取行数
        if (window._reportFileRows && window._reportFileRows[name]) {
          var ri = window._reportFileRows[name];
          rowInfo = '<span style="color:'+(ri.error?'#dc2626':'#059669')+';font-size:10px;margin-left:6px">' + (ri.rows||'') + '</span>';
        }
        html += '<div style="display:flex;align-items:center;justify-content:space-between;padding:4px 0;border-bottom:1px solid #f1f5f9">'
          + '<span><span style="color:#94a3b8;font-size:10px;width:24px;display:inline-block;text-align:right;margin-right:4px">' + (idx+1) + '.</span>'
          + '<input type="checkbox" class="tda-doc-check" data-id="' + doc.id + '" style="margin-right:6px">'
          + esc(name) + rowInfo + ' <span style="color:var(--gray-400);font-size:11px">' + size + '</span></span>'
          + '<span style="color:var(--gray-400);font-size:11px">' + (doc.uploaded_at || '').substring(0,10) + '</span>'
          + '<span style="color:#dc2626;cursor:pointer;font-size:11px" onclick="delTaxDoc(' + doc.id + ')">删除</span>'
          + '</div>';
      });
    } catch(e) {
      console.error('文件列表渲染错误:', e);
      html += '<div style="color:#dc2626">渲染错误: ' + esc(String(e.message || e)) + '</div>';
    }
    html += '</div>';
    listEl.innerHTML = html;
  } catch (e) {
    console.error('刷新文件列表失败:', e);
  }
}

async function delTaxDoc(id) {
  if (!confirm('确认删除该文件？')) return;
  try {
    var resp = await fetch('/api/tax-risk-docs/' + id + '?company_id=' + (typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1), { method: 'DELETE' });
    var data = await resp.json();
    if (data.ok) toast('已删除', 'success');
    refreshTaxDocList();
  } catch (e) {
    toast('删除失败', 'error');
  }
}

function toggleAllTdaDocs(cb) {
  var boxes = document.querySelectorAll('.tda-doc-check');
  boxes.forEach(function(b) { b.checked = cb.checked; });
}

async function batchDelTdaDocs() {
  var boxes = document.querySelectorAll('.tda-doc-check:checked');
  if (boxes.length === 0) { toast('请先选择要删除的资料', 'warning'); return; }
  var ids = Array.from(boxes).map(function(b) { return b.getAttribute('data-id'); });
  if (!confirm('确定删除选中的 ' + ids.length + ' 个文件？')) return;
  var fail = 0;
  for (var i = 0; i < ids.length; i++) {
    try {
      await fetch('/api/tax-risk-docs/' + ids[i] + '?company_id=' + (typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1), { method: 'DELETE' });
    } catch(e) { fail++; }
  }
  toast('已删除 ' + (ids.length - fail) + ' 个文件' + (fail > 0 ? '，' + fail + '个失败' : ''), 'success');
  refreshTaxDocList();
}

// ==================== 一键分析 ====================
async function analyzeTaxDocs() {
  if (taxDocAnalyzing) return;
  taxDocAnalyzing = true;
  var btn = document.getElementById('tda-analyze-btn');
  btn.disabled = true; btn.textContent = '⏳ 分析中...（约2-3分钟）';

  try {
    var resp = await fetch('/api/tax-risk-docs/analyze?company_id=' + (typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1), { method: 'POST' });
    var data = await resp.json();
    if (!taxDocPageActive) return;  // 页面已离开，不渲染
    if (data.ok) {
      taxDocReportData = data.report;
      renderTaxDocReport(data.report);
      var exportBtn = document.getElementById('tda-export-btn');
      if (exportBtn) exportBtn.style.display = 'inline-block';
      toast('分析完成：' + data.report.total_risks + '项风险发现', 'success');
      var now2 = new Date();
      var ts2 = now2.getFullYear() + '-' + String(now2.getMonth()+1).padStart(2,'0') + '-' + String(now2.getDate()).padStart(2,'0') + ' ' + String(now2.getHours()).padStart(2,'0') + ':' + String(now2.getMinutes()).padStart(2,'0');
      var el2 = document.getElementById('tda-last-update');
      if (el2) el2.textContent = '最近更新: ' + ts2;
    } else {
      toast(data.message || '分析失败', 'error');
    }
  } catch (e) {
    toast('分析失败: ' + e.message, 'error');
  } finally {
    taxDocAnalyzing = false;
    btn.disabled = false; btn.textContent = '一键分析';
  }
}

// ==================== 报告渲染 ====================
function renderTaxDocReport(r) {
  var area = document.getElementById('tda-report-area');
  if (!area || !r) return;

  // 给所有finding分配全局唯一索引
  var fIdx = 0;
  window._allFindings = [];
  if (r.domain_summary) {
    r.domain_summary.forEach(function(dr) {
      if (dr.findings) dr.findings.forEach(function(f) {
        f._idx = fIdx++;
        window._allFindings.push(f);
      });
    });
  }

  var lc = r.overall_level === '高风险' ? '#dc2626' : (r.overall_level === '中风险' ? '#f59e0b' : '#059669');
  var lb = r.overall_level === '高风险' ? '#fef2f2' : (r.overall_level === '中风险' ? '#fffbeb' : '#ecfdf5');

  var S = { bg: '#fff', text: '#1e293b', muted: '#64748b', light: '#94a3b8',
    border: '#e2e8f0', accent: '#0f172a', blue: '#2563eb',
    red: '#dc2626', amber: '#f59e0b', green: '#059669',
    shadow: '0 1px 2px rgba(0,0,0,0.04)', radius: '6px' };

  function secHdr(title) {
    return '<div style="margin:24px 0 12px;display:flex;align-items:center;gap:10px">'
      + '<div style="width:3px;height:18px;background:'+S.accent+';border-radius:2px;flex-shrink:0"></div>'
      + '<span style="font-weight:600;font-size:14px;color:'+S.accent+';letter-spacing:0.3px">'+title+'</span></div>';
  }
  function pill(label, v, c) {
    return '<div style="text-align:center;flex:1"><div style="font-size:28px;font-weight:700;color:'+c+';line-height:1">'+v+'</div><div style="font-size:11px;color:'+S.muted+';margin-top:2px">'+label+'</div></div>';
  }
  function fmtAmt(v) {
    if (Math.abs(v) >= 100000000) return (v/100000000).toFixed(2) + '亿';
    if (Math.abs(v) >= 10000) return (v/10000).toFixed(1) + '万';
    return v.toLocaleString('zh-CN', {maximumFractionDigits:0});
  }

  var html = '';

  // ═══ 稽查审核报告格式 ═══
  // 工具栏切换
  html += '<div style="display:flex;gap:8px;margin-bottom:16px">'
    + '<button onclick="renderAuditReport()" style="padding:6px 16px;border:2px solid '+S.accent+';background:'+S.accent+';color:#fff;border-radius:4px;font-size:12px;font-weight:600;cursor:pointer">稽查审核报告</button>'
    + '<button onclick="renderAnalysisReport()" style="padding:6px 16px;border:1px solid '+S.border+';background:#fff;color:'+S.muted+';border-radius:4px;font-size:12px;cursor:pointer">分析视图</button>'
    + '</div>';
  
  // 缓存报告数据
  window._reportData = r;
  // 从 file_results 提取每个文件的行数
  window._reportFileRows = {};
  if (r.file_results) {
    r.file_results.forEach(function(fr){
      var rows = '';
      if (fr.actions && fr.actions.length) {
        var m = fr.actions[0].match(/(\d+)条/);
        if (m) rows = m[1] + '条';
      }
      if (fr.error) rows = '失败';
      window._reportFileRows[fr.file] = { rows: rows, error: !!fr.error };
    });
  }
  // 刷新文件列表以显示行数
  if (typeof refreshTaxDocList === 'function') refreshTaxDocList();
  
  // 直接渲染稽查报告，跳过分析视图
  renderAuditReport();
  area.scrollIntoView({ behavior: 'smooth' });
  return;  // 跳过后续分析视图HTML构建

  // Data warning
  if (r.low_data_warning) {
    html += '<div style="background:#fffbeb;border-left:3px solid '+S.amber+';padding:14px 18px;border-radius:4px;margin-bottom:16px;font-size:12px;color:#92400e;line-height:1.7">'
      + '<strong>数据不足</strong> — 系统未能提取足够结构化数据，以下分析结果可能产生误报。</div>';
  }

  // ═══ 1. Risk Overview ═══
  html += '<div style="background:'+S.bg+';border:1px solid '+S.border+';border-radius:6px;padding:24px">'
    + '<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px">'
    + '<div style="display:flex;align-items:center;gap:12px">'
    + '<span style="font-size:13px;color:'+S.muted+';letter-spacing:0.5px">综合风险等级</span>'
    + '<span style="display:inline-block;padding:4px 16px;background:'+lb+';color:'+lc+';border-radius:3px;font-weight:700;font-size:15px">'+r.overall_level+'</span>'
    + '</div>'
    + '<span style="font-size:11px;color:'+S.light+'">'+r.total_risks+' 项发现 · '+r.files_count+' 份文件 · '+r.rules_used+' 条指令</span>'
    + '</div>'
    + '<div style="display:flex;gap:24px;margin-top:16px;padding-top:16px;border-top:1px solid '+S.border+'">'
    + pill('高风险', r.high_risk, S.red) + pill('中风险', r.mid_risk, S.amber) + pill('低风险', r.low_risk, S.green)
    + '</div></div>'
    // 摘要文字单独放到下面
    + '<div style="background:#f8fafc;border:1px solid '+S.border+';border-radius:4px;padding:10px 16px;margin-top:12px;font-size:11px;color:'+S.muted+';line-height:1.7">'+esc(r.summary_text||'')+'</div>';

  // ═══ 2. Executive Summary ═══
  // Build from top findings: merge duplicates, estimate tax impact, prioritize
  if (r.comprehensive && r.domain_summary) {
    var comp = r.comprehensive;
    var allF = [];
    r.domain_summary.forEach(function(dr){ if (dr.findings) dr.findings.forEach(function(f){ f._domain = dr.name; allF.push(f); }); });
    
    // Sort by score, pick top risks
    allF.sort(function(a,b){ return (b.score||0)-(a.score||0); });
    var top3 = allF.filter(function(f){ return (f.score||0) >= 7; }).slice(0, 3);
    
    // Build exec summary
    html += '<div style="background:#f8fafc;border:1px solid '+S.border+';border-radius:6px;padding:24px;margin-top:16px">'
      + '<div style="font-size:11px;color:'+S.light+';letter-spacing:1px;text-transform:uppercase;margin-bottom:8px">执行摘要</div>';
    
    if (top3.length) {
      // Determine actual severity from top findings
      var sevColor = top3.length >= 3 ? S.red : (top3.length >= 2 ? S.amber : S.green);
      var sevLabel = top3.length >= 3 ? '严重' : (top3.length >= 2 ? '需关注' : '较轻');
      
      html += '<div style="font-size:15px;font-weight:700;color:'+S.accent+';margin-bottom:4px;line-height:1.6">'
        + '经分析发现 <span style="color:'+sevColor+'">'+top3.length+' 项优先处理问题</span>，风险评估等级为 <span style="color:'+sevColor+'">'+sevLabel+'</span></div>'
        + '<div style="font-size:11px;color:'+S.muted+';margin-bottom:16px">基于 '+r.total_risks+' 项风险发现、'+r.rules_used+' 条稽查指令、'+r.files_count+' 份文件分析</div>';
      
      top3.forEach(function(f, i){
        html += '<div style="display:flex;gap:12px;align-items:baseline;margin-bottom:10px;padding-bottom:10px;border-bottom:1px solid '+S.border+'">'
          + '<span style="font-size:20px;font-weight:800;color:'+sevColor+';min-width:24px">'+(i+1)+'</span>'
          + '<div style="flex:1"><div style="font-size:13px;font-weight:600;color:'+S.accent+';margin-bottom:2px">'+esc(f.type||'')+'</div>'
          + '<div style="font-size:10px;color:'+S.muted+';line-height:1.5">'+esc((f.detail||'').substring(0, 150))+'</div></div>'
          + '<span style="font-size:10px;color:#fff;background:'+sevColor+';padding:2px 8px;border-radius:3px;white-space:nowrap;align-self:flex-start">'+(f.score||0)+'分</span></div>';
      });
      
      // Immediate actions
      html += '<div style="background:#fff;border:1px solid '+S.border+';border-radius:4px;padding:14px;margin-top:12px">'
        + '<div style="font-size:11px;font-weight:600;color:'+S.accent+';margin-bottom:8px">今日可执行</div>';
      top3.forEach(function(f){
        var sug = (f.suggestion||'').substring(0, 120);
        if (sug) html += '<div style="display:flex;gap:8px;margin-bottom:4px;font-size:10px;color:'+S.muted+'">'
          + '<span style="color:'+S.green+'">✔</span><span>'+esc(sug)+'</span></div>';
      });
      html += '</div>';
    }
    html += '</div>';
  }

  // ═══ 3. Comprehensive ═══
  if (r.comprehensive) {
    var comp = r.comprehensive;
    var present = comp.data_overview.present || [];
    var missing = comp.data_overview.missing || [];
    html += secHdr('数据覆盖') + '<div style="display:flex;flex-wrap:wrap;gap:8px">';
    present.forEach(function(s){ html += '<span style="background:#f0fdf4;color:#166534;border:1px solid #bbf7d0;padding:4px 10px;border-radius:3px;font-size:11px">'+esc(s)+'</span>'; });
    missing.forEach(function(s){ html += '<span style="background:#f9fafb;color:'+S.light+';border:1px dashed '+S.border+';padding:4px 10px;border-radius:3px;font-size:11px">'+esc(s)+'</span>'; });
    html += '</div>';

    // Risk Profile
    if (comp.risk_profile) {
      var rp = comp.risk_profile;
      html += secHdr('风险画像')
        + '<div style="display:flex;gap:16px;align-items:stretch;flex-wrap:wrap">'
        + '<div style="background:'+S.bg+';border:1px solid '+S.border+';border-radius:6px;padding:24px;text-align:center;min-width:140px">'
        + '<div style="font-size:11px;color:'+S.muted+';margin-bottom:6px;letter-spacing:0.5px">综合评分</div>'
        + '<div style="font-size:40px;font-weight:800;color:'+S.blue+';line-height:1">'+rp.composite_score+'</div>'
        + '<div style="font-size:12px;color:'+S.accent+';font-weight:600;margin-top:4px">'+rp.composite_level+'</div>'
        + '<div style="font-size:10px;color:'+S.light+';margin-top:4px">x'+rp.cross_multiplier+' · '+rp.high_dimensions+'维高风险</div></div>'
        + '<div style="flex:1;background:'+S.bg+';border:1px solid '+S.border+';border-radius:6px;padding:20px">';
      var rd = rp.radar;
      for (var i=0; i<rd.labels.length; i++) {
        var dn = rd.labels[i], ds = rp.dimensions[dn], pct = Math.max(2, Math.min(100, ds.score));
        html += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">'
          + '<span style="font-size:10px;color:'+S.muted+';width:60px;text-align:right">'+dn+'</span>'
          + '<div style="flex:1;height:10px;background:#f1f5f9;border-radius:5px;overflow:hidden"><div style="width:'+pct+'%;height:100%;background:'+rd.colors[i]+';border-radius:5px"></div></div>'
          + '<span style="font-size:10px;font-weight:600;width:28px;color:'+rd.colors[i]+'">'+ds.score+'</span></div>';
      }
      if (rp.cross_patterns && rp.cross_patterns.length) {
        html += '<div style="margin-top:10px;padding-top:8px;border-top:1px solid '+S.border+'">';
        rp.cross_patterns.forEach(function(p){ html += '<span style="background:#fef2f2;color:'+S.red+';padding:2px 8px;border-radius:3px;font-size:10px;margin-right:6px">'+esc(p)+'</span>'; });
        html += '</div>';
      }
      html += '</div></div>';
    }

    // KPI cards
    var tIn=0,tOut=0,tTax=0;
    if (comp.cashflow) { comp.cashflow.income.forEach(function(v){tIn+=v;}); comp.cashflow.expense.forEach(function(v){tOut+=v;}); comp.cashflow.tax.forEach(function(v){tTax+=v;}); }
    html += secHdr('经营概览') + '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px">';
    if (tIn>0) html += '<div style="background:'+S.bg+';border:1px solid '+S.border+';border-radius:6px;padding:14px"><div style="font-size:10px;color:'+S.light+';letter-spacing:0.5px">年度总收入</div><div style="font-size:18px;font-weight:700;color:'+S.accent+';margin-top:4px">'+fmtAmt(tIn)+'</div></div>';
    if (tOut>0) html += '<div style="background:'+S.bg+';border:1px solid '+S.border+';border-radius:6px;padding:14px"><div style="font-size:10px;color:'+S.light+';letter-spacing:0.5px">年度总支出</div><div style="font-size:18px;font-weight:700;color:'+S.accent+';margin-top:4px">'+fmtAmt(tOut)+'</div></div>';
    if (tTax>0) html += '<div style="background:'+S.bg+';border:1px solid '+S.border+';border-radius:6px;padding:14px"><div style="font-size:10px;color:'+S.light+';letter-spacing:0.5px">年度纳税</div><div style="font-size:18px;font-weight:700;color:'+S.accent+';margin-top:4px">'+fmtAmt(tTax)+'</div><div style="font-size:10px;color:'+S.muted+'">税负率 '+(tIn>0?(tTax/tIn*100).toFixed(1):'0')+'%</div></div>';
    html += '</div>';

    // Counterparty table
    var allCp = [];
    if (comp.top_receivers) comp.top_receivers.forEach(function(t){allCp.push({name:t.name,amount:t.amount,type:'收'});});
    if (comp.top_payers) comp.top_payers.forEach(function(t){allCp.push({name:t.name,amount:t.amount,type:'付'});});
    allCp.sort(function(a,b){return b.amount-a.amount;}).slice(0,10);
    if (allCp.length) {
      html += secHdr('主要往来方')
        + '<div style="background:'+S.bg+';border:1px solid '+S.border+';border-radius:6px;overflow:hidden">'
        + '<table style="width:100%;font-size:11px;border-collapse:collapse"><thead><tr style="background:#f8fafc;border-bottom:2px solid '+S.border+'"><th style="padding:8px 12px;text-align:left;font-weight:600;color:'+S.muted+'">#</th><th style="padding:8px 12px;text-align:left;font-weight:600;color:'+S.muted+'">对方名称</th><th style="padding:8px 12px;text-align:right;font-weight:600;color:'+S.muted+'">金额</th></tr></thead><tbody>';
      allCp.forEach(function(t,i){ html += '<tr style="border-bottom:1px solid #f8fafc"><td style="padding:6px 12px;color:'+S.light+'">'+(i+1)+'</td><td style="padding:6px 12px;color:'+S.text+'">'+esc(t.name)+'</td><td style="padding:6px 12px;text-align:right;font-weight:600;color:'+(t.type==='收'?S.green:S.accent)+'">'+fmtAmt(t.amount)+'</td></tr>'; });
      html += '</tbody></table></div>';
    }

    // Actions
    var act = comp.actions || {};
    var secs = [['p0_urgent','需立即处理',S.red],['p1_important','重要',S.amber],['p2_normal','建议',S.green]];
    var anyAct = secs.some(function(s){return act[s[0]] && act[s[0]].length;});
    if (anyAct) {
      html += secHdr('行动建议');
      secs.forEach(function(s){
        var items = act[s[0]] || [];
        if (!items.length) return;
        html += '<div style="border-left:3px solid '+s[2]+';padding-left:14px;margin-bottom:16px"><div style="font-size:12px;font-weight:600;color:'+s[2]+';margin-bottom:6px">'+s[1]+' ('+items.length+'项)</div>';
        items.forEach(function(it){ html += '<div style="margin-bottom:10px"><div style="font-size:11px;font-weight:600;color:'+S.text+'">'+esc(it.type||'')+'</div><div style="font-size:10px;color:'+S.muted+';line-height:1.7">'+esc(it.suggestion||'')+'</div></div>'; });
        html += '</div>';
      });
    }
  }

  // ═══ 3-5. Bottom sections ═══
  if (r.pipeline_log && r.pipeline_log.length > 0) {
    html += secHdr('处理日志');
    html += '<div style="background:#f8fafc;border:1px solid '+S.border+';border-radius:6px;padding:10px 14px;font-size:10px;font-family:ui-monospace,monospace;color:'+S.muted+';max-height:160px;overflow-y:auto">';
    r.pipeline_log.forEach(function(log){ html += '<div style="padding:1px 0">'+esc(log)+'</div>'; });
    html += '</div>';
  }

  if (r.file_results && r.file_results.length > 0) {
    html += secHdr('文件详情');
    html += '<div style="background:'+S.bg+';border:1px solid '+S.border+';border-radius:6px;overflow:hidden">';
    r.file_results.forEach(function(fr){
      var icon = fr.error ? '✕' : '●', icoC = fr.error ? S.red : S.green;
      html += '<div style="padding:6px 14px;font-size:11px;border-bottom:1px solid #f8fafc;display:flex;align-items:center;gap:8px">'
        + '<span style="color:'+icoC+'">'+icon+'</span><span style="font-weight:500;color:'+S.text+';flex:1">'+esc(fr.file)+'</span>'
        + '<span style="color:'+S.light+';font-size:10px">'+esc((fr.type||'?').replace(/_/g,' '))+'</span>'
        + (fr.actions?fr.actions.map(function(a){return '<span style="color:'+S.green+';font-size:9px">✓ '+esc(a)+'</span>';}).join(''):'')
        + (fr.error?'<span style="color:'+S.red+';font-size:9px">✕ '+esc(fr.error)+'</span>':'')+'</div>';
    });
    html += '</div>';
  }

  if (r.domain_summary && r.domain_summary.length > 0) {
    html += secHdr('域分析');
    r.domain_summary.forEach(function(dr){
      if (!dr.findings || !dr.findings.length) return;
      html += '<div style="margin-bottom:6px;border:1px solid '+S.border+';border-radius:6px;overflow:hidden">'
        + '<div style="display:flex;align-items:center;justify-content:space-between;padding:10px 14px;background:#f8fafc;cursor:pointer" onclick="var n=this.nextElementSibling;n.hidden=!n.hidden">'
        + '<span style="font-weight:600;font-size:12px;color:'+S.text+'">'+esc(dr.name)+'</span><span style="font-size:10px;color:'+S.muted+'">'+dr.count+' 项</span></div>'
        + '<div>';
      dr.findings.forEach(function(f){
        var dotC = f.level==='高风险'?S.red:(f.level==='中风险'?S.amber:S.light);
        var cfBg = f.level==='高风险'?'#fef2f2':(f.level==='中风险'?'#fffbeb':'#f8fafc');
        var cfBorder = f.level==='高风险'?'#fecaca':(f.level==='中风险'?'#fde68a':'#e2e8f0');
        html += '<div style="padding:12px 14px;border-bottom:1px solid #f8fafc;font-size:12px;line-height:1.7">'
          + '<div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">'
          + '<span style="width:5px;height:5px;border-radius:50%;background:'+dotC+';flex-shrink:0"></span>'
          + '<b style="font-size:13px;color:'+S.text+';flex:1">'+esc(f.type||'')+'</b>'
          + '<span style="font-size:9px;color:'+S.light+'">'+(f.score||0)+'分</span>'
          + '<button onclick="reviewSingleFinding(this)" data-idx="'+(f._idx||0)+'" style="font-size:10px;padding:2px 8px;border:1px solid '+S.border+';background:#fff;color:'+S.muted+';border-radius:3px;cursor:pointer">复核</button></div>'
          + '<div style="color:'+S.muted+';margin-bottom:6px">'+esc(f.detail||'')+'</div>';
        if (f.description) html += '<div style="background:'+cfBg+';border:1px solid '+cfBorder+';border-radius:5px;padding:10px 12px;margin-bottom:6px"><div style="font-weight:600;font-size:11px;color:'+dotC+';margin-bottom:3px">风险解释</div><div style="font-size:11px;color:#475569;white-space:pre-line">'+esc(f.description)+'</div></div>';
        if (f.how_found) html += '<div style="background:#f5f3ff;border:1px solid #ddd6fe;border-radius:5px;padding:10px 12px;margin-bottom:6px"><div style="font-weight:600;font-size:11px;color:#7c3aed;margin-bottom:3px">如何得出</div><div style="font-size:10px;color:'+S.muted+';white-space:pre-line">'+esc(f.how_found)+'</div></div>';
        if (f.tax_impact) html += '<div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:5px;padding:10px 12px;margin-bottom:6px"><div style="font-weight:600;font-size:11px;color:#ea580c;margin-bottom:3px">税务影响</div><div style="font-size:11px;color:#475569">'+esc(f.tax_impact)+'</div></div>';
        if (f.policy_ref) html += '<div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:5px;padding:10px 12px;margin-bottom:6px"><div style="font-weight:600;font-size:11px;color:#0369a1;margin-bottom:3px">政策依据</div><div style="font-size:10px;color:'+S.muted+'">'+esc(f.policy_ref)+'</div></div>';
        if (f.suggestion) html += '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:5px;padding:10px 12px"><div style="font-weight:600;font-size:11px;color:#059669;margin-bottom:3px">整改建议</div><div style="font-size:11px;color:#475569">'+esc(f.suggestion)+'</div></div>';
        html += '</div>';
      });
      html += '</div></div>';
    });
  }

  // 保存分析视图HTML
  window._analysisViewHtml = html;
  // 默认展示稽查报告
  renderAuditReport();
  area.scrollIntoView({ behavior: 'smooth' });
}

// ==================== 导出报告 ====================
function exportTaxDocReport() {
  var area = document.getElementById('tda-report-area');
  if (!area) return;
  var content = area.innerHTML;
  var html = '<!DOCTYPE html><html><head><meta charset="utf-8"><title>涉税资料分析报告</title>'
    + '<style>body{font-family:"Microsoft YaHei","PingFang SC",sans-serif;max-width:900px;margin:0 auto;padding:20px;color:#333;line-height:1.8}'
    + 'h2{color:#1e293b;border-bottom:2px solid #e2e8f0;padding-bottom:8px}'
    + '@media print{body{padding:0;font-size:11pt}}</style></head><body>'
    + '<h1 style="text-align:center">涉税资料分析报告</h1>'
    + '<p style="text-align:center;color:#64748b">生成时间：' + new Date().toLocaleString('zh-CN') + '</p>'
    + content + '</body></html>';
  var blob = new Blob([html], {type: 'text/html;charset=utf-8'});
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = '涉税资料分析报告_' + new Date().toISOString().substring(0,10) + '.html';
  a.click();
  URL.revokeObjectURL(url);
  toast('报告已导出', 'success');
}

function deleteTaxDocReport() {
  if (!taxDocReportData) { toast('暂无报告可删除', 'warning'); return; }
  if (!confirm('确定要删除当前报告吗？')) return;
  taxDocReportData = null;
  document.getElementById('tda-report-area').innerHTML = '';
  toast('报告已删除', 'success');
}

// ==================== 报告复核 ====================
var reviewData = null;

async function reviewTaxDocReport() {
  var btn = document.getElementById('tda-review-btn');
  if (!btn) return;
  btn.disabled = true; btn.textContent = '复核中...';

  try {
    var resp = await fetch('/api/tax-risk-docs/review?company_id=' + (typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1), { method: 'POST' });
    var data = await resp.json();
    if (!data.ok) { toast(data.message || '复核失败', 'error'); return; }

    reviewData = data;
    renderReviewResult(data);

    if (data.passed) {
      toast('复核通过：未发现错误，但有' + data.report_issues + '项提示', 'success');
    } else {
      toast('复核发现' + data.report_issues + '项问题，请查看详情', 'warning');
    }
  } catch (e) {
    toast('复核失败: ' + e.message, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '报告复核'; }
  }
}

function renderReviewResult(data) {
  var area = document.getElementById('tda-report-area');
  if (!area) return;

  var issues = data.review || [];
  var errorCount = issues.filter(function(i) { return i.level === '错误'; }).length;
  var warnCount = issues.filter(function(i) { return i.level === '警告'; }).length;
  var infoCount = issues.filter(function(i) { return i.level === '信息' || i.level === '注意'; }).length;

  var html = '<div style="background:#fff;border:1px solid var(--gray-200);border-radius:10px;padding:20px;margin-top:12px">'
    + '<b style="font-size:15px">报告复核结果</b>'
    + '<div style="display:flex;gap:12px;margin-top:12px">';

  if (errorCount > 0) {
    html += '<div style="flex:1;background:#fef2f2;border-radius:8px;padding:14px;text-align:center"><div style="font-size:24px;font-weight:700;color:#dc2626">' + errorCount + '</div><div style="font-size:11px;color:#991b1b">错误</div></div>';
  }
  if (warnCount > 0) {
    html += '<div style="flex:1;background:#fffbeb;border-radius:8px;padding:14px;text-align:center"><div style="font-size:24px;font-weight:700;color:#f59e0b">' + warnCount + '</div><div style="font-size:11px;color:#92400e">警告</div></div>';
  }
  if (infoCount > 0) {
    html += '<div style="flex:1;background:#f0f9ff;border-radius:8px;padding:14px;text-align:center"><div style="font-size:24px;font-weight:700;color:#0369a1">' + infoCount + '</div><div style="font-size:11px;color:#1e40af">提示</div></div>';
  }
  if (issues.length === 0) {
    html += '<div style="flex:1;background:#ecfdf5;border-radius:8px;padding:14px;text-align:center"><div style="font-size:24px">✅</div><div style="font-size:11px;color:#065f46">全部通过</div></div>';
  }

  html += '</div>';

  // 复核方法说明
  html += '<div style="margin-top:16px;background:#f0fdf4;border-radius:8px;padding:12px 16px;font-size:12px;color:#065f46">'
    + '<b>复核方法：</b>'
    + '① 数据源验证（结论引用的数字是否真实存在） | '
    + '② 计算复核（关键数字重新从源数据计算） | '
    + '③ 逻辑一致性（不同域结论是否自相矛盾） | '
    + '④ 空值陷阱检测（分母/分组键是否有效） | '
    + '⑤ 极端值合理性（>95%占比需人工确认）'
    + '</div>';

  // 逐条展示复核发现
  if (issues.length > 0) {
    issues.forEach(function(iss, i) {
      var color = iss.level === '错误' ? '#dc2626' : (iss.level === '警告' ? '#f59e0b' : '#0369a1');
      var bg = iss.level === '错误' ? '#fef2f2' : (iss.level === '警告' ? '#fffbeb' : '#f0f9ff');
      var icon = iss.level === '错误' ? '❌' : (iss.level === '警告' ? '⚠️' : 'ℹ️');
      html += '<div style="margin-top:10px;padding:12px 16px;background:' + bg + ';border-left:4px solid ' + color + ';border-radius:6px;font-size:13px">'
        + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">'
        + '<span style="font-size:18px">' + icon + '</span>'
        + '<span style="font-weight:600">#' + (i+1) + ' [' + iss.level + '] ' + esc(iss.item) + '</span>'
        + '</div>'
        + '<div style="color:var(--gray-600);margin-bottom:4px">' + esc(iss.detail) + '</div>'
        + '<div style="color:' + color + ';font-size:12px">💡 ' + esc(iss.suggestion) + '</div>'
        + '</div>';
    });
  }

  html += '</div>';

  // 插入到报告区域顶部
  area.insertBefore(createElementFromString(html), area.firstChild);
  area.scrollIntoView({ behavior: 'smooth' });
}

function createElementFromString(htmlStr) {
  var div = document.createElement('div');
  div.innerHTML = htmlStr.trim();
  return div.firstChild;
}

// ==================== 单结论复核 ====================
async function reviewSingleFinding(btn) {
  var idx = parseInt(btn.getAttribute('data-idx'));
  var finding = window._allFindings ? window._allFindings[idx] : null;
  if (!finding) { toast('找不到该结论', 'error'); return; }

  var resultDiv = document.getElementById('review-result-' + idx);
  if (!resultDiv) return;

  btn.disabled = true; btn.textContent = '复核中...';

  try {
    var resp = await fetch('/api/tax-risk-docs/review-single?company_id=' + (typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(finding)
    });
    var data = await resp.json();
    if (!data.ok) { toast('复核失败', 'error'); return; }

    var ri = data.review;
    var issues = ri.issues || [];
    var color = ri.passed ? '#059669' : (ri.level === '错误' ? '#dc2626' : '#f59e0b');
    var bg = ri.passed ? '#ecfdf5' : (ri.level === '错误' ? '#fef2f2' : '#fffbeb');
    var icon = ri.passed ? '✅' : (ri.level === '错误' ? '❌' : '⚠️');

    var html = '<div style="background:' + bg + ';border:1px solid ' + color + ';border-radius:6px;padding:10px 14px;margin-top:8px">'
      + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">'
      + '<span style="font-size:16px">' + icon + '</span>'
      + '<b style="color:' + color + '">复核结论：' + esc(ri.summary || '通过') + '</b>'
      + '</div>'
      + '<div style="font-size:11px;color:var(--gray-500);margin-bottom:6px">' + esc(ri.method || '') + '</div>';

    if (issues.length > 0) {
      issues.forEach(function(iss) {
        html += '<div style="font-size:12px;padding:6px 8px;margin:4px 0;background:rgba(255,255,255,0.7);border-radius:4px">'
          + '<span style="font-weight:600">' + esc(iss.check || '') + '：</span>'
          + '<span style="color:var(--gray-600)">' + esc(iss.result || '') + '</span>'
          + '</div>';
      });
    }
    html += '</div>';

    resultDiv.innerHTML = html;
    resultDiv.style.display = 'block';
  } catch (e) {
    toast('复核失败: ' + e.message, 'error');
  } finally {
    btn.disabled = false; btn.textContent = '复核此结论';
  }
}

// ═══════════════════════════════════════
// 稽查审核报告渲染 —— 税务稽查局执行人员向上级汇报格式
// ═══════════════════════════════════════
function renderAuditReport() {
  var r = window._reportData;
  if (!r) return;
  var targetId = window._auditReportTarget || 'tda-report-area';
  var area = document.getElementById(targetId);
  if (!area) return;
  var toolbar = area.querySelector('.tda-toolbar');
  
  var S = { bg: '#fff', text: '#1e293b', muted: '#64748b', light: '#94a3b8',
    border: '#e2e8f0', accent: '#0f172a', blue: '#2563eb',
    red: '#dc2626', amber: '#f59e0b', green: '#059669' };
  
  function fmt(v) {
    if (Math.abs(v) >= 100000000) return (v/100000000).toFixed(2) + '亿';
    if (Math.abs(v) >= 10000) return (v/10000).toFixed(1) + '万';
    return v.toLocaleString('zh-CN', {maximumFractionDigits:0});
  }
  
  var h = '<div style="padding:40px 0;max-width:780px;margin:0 auto;font-size:13px;line-height:1.9;color:'+S.text+'">';
  
  // ── 表头 ──
  h += '<div style="text-align:center;margin-bottom:32px;padding-bottom:24px;border-bottom:3px double '+S.accent+'">'
    + '<div style="font-size:20px;font-weight:700;color:'+S.accent+';letter-spacing:2px;margin-bottom:8px">税务稽查审核报告</div>'
    + '<div style="font-size:11px;color:'+S.muted+'">编号：TS-'+new Date().toISOString().slice(0,10).replace(/-/g,'')+'-001 | '+new Date().toLocaleString('zh-CN')+'</div>'
    + '</div>';
  
  // ── 基本信息 ──
  h += '<table style="width:100%;font-size:11px;border-collapse:collapse;margin-bottom:24px">'
    + '<tr><td style="padding:4px 12px;width:100px;color:'+S.muted+';font-weight:600">被查单位</td><td style="padding:4px 12px">（依据上传资料识别）</td></tr>'
    + '<tr><td style="padding:4px 12px;color:'+S.muted+';font-weight:600">稽查期间</td><td style="padding:4px 12px">'+ (r.summary_text||'').match(/\d{4}年/) + '（以凭证及发票数据覆盖期间为准）</td></tr>'
    + '<tr><td style="padding:4px 12px;color:'+S.muted+';font-weight:600">稽查范围</td><td style="padding:4px 12px">'+r.files_count+'份资料，涵盖银行流水、进销项发票、记账凭证、工资社保</td></tr>'
    + '<tr><td style="padding:4px 12px;color:'+S.muted+';font-weight:600">执行标准</td><td style="padding:4px 12px">'+r.rules_used+' 条稽查指令，《税务稽查工作规程》（国税发[2009]157号）</td></tr>'
    + '</table>';
  
  // ── 一、稽查结论 ──
  var topF = [];
  r.domain_summary.forEach(function(dr){ if(dr.findings) dr.findings.forEach(function(f){f._d=dr.name;topF.push(f);}); });
  topF.sort(function(a,b){return(b.score||0)-(a.score||0);});
  var top3 = topF.filter(function(f){return (f.score||0)>=7;}).slice(0,3);
  
  var sevLabel = top3.length>=3?'存在严重涉税违法嫌疑':(top3.length>=2?'存在多项涉税疑点':'基本合规');
  var sevColor = top3.length>=3?S.red:(top3.length>=2?S.amber:S.green);
  
  h += '<div style="margin-bottom:28px"><div style="font-size:15px;font-weight:700;color:'+S.accent+';border-bottom:2px solid '+S.accent+';padding-bottom:6px;margin-bottom:14px">一、稽查结论</div>'
    + '<div style="font-size:13px;line-height:2;padding:16px;background:#f8fafc;border-left:3px solid '+sevColor+'">'
    + '经对'+r.files_count+'份涉税资料进行系统性审查，依据'+r.rules_used+'条稽查指令，共发现<span style="color:'+sevColor+';font-weight:700"> '+r.total_risks+' 项涉税疑点</span>（高风险'+r.high_risk+'项，中风险'+r.mid_risk+'项）。综合评估结论：<span style="color:'+sevColor+';font-weight:700">'+sevLabel+'</span>。';
  // 7维评分 + 交叉模式
  var rp = (r.comprehensive||{}).risk_profile;
  if (rp && rp.dimensions) {
    h += '<br><br><span style="font-weight:600;color:'+S.accent+'">金税四期 7 维风险评分：</span>';
    Object.keys(rp.dimensions).forEach(function(dn){
      var ds = rp.dimensions[dn];
      var lc = ds.score > 40 ? S.red : (ds.score > 20 ? S.amber : S.green);
      h += '<span style="font-size:10px;padding:2px 6px;margin:0 3px;background:#f8fafc;border-radius:3px">'+dn+' <b style="color:'+lc+'">'+ds.score+'</b></span>';
    });
  }
  if (rp && rp.cross_patterns && rp.cross_patterns.length) {
    h += '<br><span style="font-weight:600;color:'+S.red+';font-size:11px">交叉预警：</span>';
    rp.cross_patterns.forEach(function(p){ h += '<span style="background:#fef2f2;color:'+S.red+';padding:2px 6px;border-radius:3px;font-size:10px;margin:0 3px">'+esc(p)+'</span>'; });
  }
  // 数据导入流水
  h += '<br><span style="font-size:10px;color:'+S.light+'">数据导入：';
  r.pipeline_log.forEach(function(log){
    var m = log.match(/导入DB.*/);
    if (m) h += esc(m[0]);
  });
  h += '</span>';
  if (top3.length) {
    h += '<br><br>三项优先度最高的问题：<br>';
    top3.forEach(function(f,i){
      h += (i+1)+'. <b>'+esc(f.type||'')+'</b>：'+esc((f.detail||'').substring(0,100))+'<br>';
    });
  }
  h += '</div></div>';
  
  // ═══ 触发的证据链 ═══
  var tc = (r.comprehensive||{}).triggered_chains||[];
  if (tc.length > 0) {
    h += '<div style="margin-bottom:28px"><div style="font-size:15px;font-weight:700;color:'+S.accent+';border-bottom:2px solid '+S.accent+';padding-bottom:6px;margin-bottom:14px">触发的证据链 (' + tc.length + '条)</div>';
    tc.forEach(function(chain) {
      h += '<div style="border:1px solid '+S.border+';border-radius:4px;padding:10px 14px;margin-bottom:8px;font-size:11px">'
        + '<span style="font-weight:700;color:'+S.accent+'">' + esc(chain.name) + '</span> '
        + '<span style="color:'+S.muted+'">' + chain.hits + '/' + chain.steps + '步命中, '+chain.high_risk+'高风险</span>';
      if (chain.tax_impacts && chain.tax_impacts.length) {
        h += '<div style="margin-top:4px;color:#dc2626;font-size:10px">' + esc(chain.tax_impacts[0]||'') + '</div>';
      }
      h += '</div>';
    });
    h += '</div>';
  }
  
  // ── 二、稽查过程 ──
  h += '<div style="margin-bottom:28px"><div style="font-size:15px;font-weight:700;color:'+S.accent+';border-bottom:2px solid '+S.accent+';padding-bottom:6px;margin-bottom:14px">二、稽查过程</div>';
  
  // 2a. 稽查方法
  var present = (r.comprehensive||{}).data_overview||{};
  h += '<div style="margin-bottom:16px"><div style="font-weight:600;font-size:12px;color:'+S.text+';margin-bottom:6px">（一）稽查方法</div>'
    + '<div style="font-size:11px;color:'+S.muted+';line-height:1.9;padding:0 8px">'
    + '依据《税务稽查工作规程》，对'+r.files_count+'份涉税资料执行'+r.rules_used+'条稽查指令。主要方法包括：<br>'
    + '1. 数据比对法：对银行流水、进销项发票、记账凭证、工资社保四源数据进行交叉比对。<br>'
    + '2. 比率分析法：计算进销比率、税负率、毛利率、购销弹性等关键指标，与行业基准和税法规定阈值比较。<br>'
    + '3. 穿透核验法：对供应商/客户进行身份核验，检查是否存在群集注册、异常关联等风险特征。<br>'
    + '4. 资金流追踪法：追踪大额、整数、非工作日交易，匹配资金流向与发票购销方的对应关系。<br>'
    + '5. 证据链串联法：将多域发现的孤立疑点串并为完整证据链，判断是否构成系统性违法行为。<br>'
    + '<br>上述方法交叉运用，已有'+r.total_risks+'项疑点经多通道验证后形成实质性发现。</div></div>';
  
  // 2b. 稽查线索链 —— 从跨域推理中提取
  var crossDomain = r.domain_summary.filter(function(dr){ return dr.name.indexOf('跨域')>=0; });
  if (crossDomain.length && crossDomain[0].findings) {
    h += '<div style="margin-bottom:16px"><div style="font-weight:600;font-size:12px;color:'+S.text+';margin-bottom:6px">（二）稽查线索链</div>';
    h += '<div style="font-size:11px;line-height:1.9;padding:0 8px">'
      + '以下为跨域串联形成的稽查线索链，展示单一疑点如何通过多源交叉验证升级为系统性违法证据：<br><br>';
    
    crossDomain[0].findings.forEach(function(cf, ci){
      var chainColor = '#7c3aed';
      h += '<div style="background:#f5f3ff;border:1px solid #ddd6fe;border-radius:4px;padding:14px;margin-bottom:12px">'
        + '<div style="font-weight:700;font-size:12px;color:'+chainColor+';margin-bottom:8px">线索链 '+(ci+1)+'：'+esc(cf.type||'')+'</div>';
      
      // Show the chain from description
      var desc = cf.description || '';
      // Extract evidence chain markers [A-xxx] [B-xxx] etc
      var markers = desc.match(/\[[A-Z\u4e00-\u9fa5]+?-[^\]]+\]/g) || [];
      if (markers.length) {
        h += '<div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:8px">';
        for (var mi = 0; mi < markers.length; mi++) {
          var m = markers[mi];
          h += '<span style="background:#ede9fe;color:'+chainColor+';padding:3px 10px;border-radius:3px;font-size:10px;font-weight:600">'+esc(m)+'</span>';
          if (mi < markers.length - 1) h += '<span style="color:'+chainColor+';font-weight:700">→</span>';
        }
        h += '</div>';
      }
      h += '<div style="font-size:10px;color:'+S.muted+'">'+esc(desc.substring(0, 200))+'</div></div>';
    });
    h += '</div></div>';
  } else {
    // 如果没有跨域推理，为top3发现构建审计链
    h += '<div style="margin-bottom:16px"><div style="font-weight:600;font-size:12px;color:'+S.text+';margin-bottom:6px">（二）稽查审计链</div>';
    h += '<div style="font-size:11px;line-height:1.9;padding:0 8px">';
    
    // Build audit chains from related findings
    var chainMap = {};
    topF.forEach(function(f){
      if ((f.score||0) < 5) return;
      var key = f.type||'';
      var deps = [];
      // Find related findings by keyword overlap
      var words = (f.detail||'').match(/[\u4e00-\u9fa5]{2,}/g) || [];
      topF.forEach(function(of){
        if (of === f) return;
        var od = of.detail||'';
        var hits = 0;
        words.forEach(function(w){
          if (od.indexOf(w) >= 0) hits++;
        });
        if (hits >= 3 && (of.score||0) >= 5) deps.push(of.type||'');
      });
      if (deps.length) chainMap[key] = deps.slice(0, 3);
    });
    
    Object.keys(chainMap).slice(0, 5).forEach(function(key, ci){
      var deps = chainMap[key];
      h += '<div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:4px;padding:10px 14px;margin-bottom:8px;font-size:11px">'
        + '<span style="font-weight:700;color:'+S.accent+'">审计项：</span>'+esc(key);
      if (deps.length) {
        h += '<div style="margin-top:4px;color:'+S.muted+'">';
        for (var di=0; di<deps.length; di++) {
          h += '├─ '+esc(deps[di])+'<br>';
        }
        h += '</div>';
      }
      h += '</div>';
    });
    h += '</div></div>';
  }
  
  // 2c. 数据源统计
  h += '<div><div style="font-weight:600;font-size:12px;color:'+S.text+';margin-bottom:6px">（三）稽查数据源</div>'
    + '<div style="font-size:11px;color:'+S.muted+';line-height:1.9;padding:0 8px">'
    + '本次稽查共调用以下数据源：<br>';
  var p = r.comprehensive.data_overview.present || [];
  p.forEach(function(s){ h += '· '+esc(s)+'<br>'; });
  h += '<br>已采集资料类型：' + p.length + ' 类</div>';
  
  // 4. 审计基础检查
  var auditLogs = r.pipeline_log.filter(function(l){ return l.indexOf('审计')>=0 || l.indexOf('平衡')>=0; });
  if (auditLogs.length) {
    h += '<div style="margin-top:8px;font-size:10px;color:'+S.muted+';line-height:1.7">'
      + '<span style="font-weight:600;color:'+S.text+'">基础账务审计：</span>';
    auditLogs.forEach(function(l){ h += esc(l)+'<br>'; });
    h += '</div>';
  }
  h += '</div>';
  h += '</div>';
  
  // ── 三、主要违法事实 ──
  h += '<div style="margin-bottom:28px"><div style="font-size:15px;font-weight:700;color:'+S.accent+';border-bottom:2px solid '+S.accent+';padding-bottom:6px;margin-bottom:14px">三、主要违法事实</div>';
  
  var factNum = 1;
  topF.forEach(function(f){
    if ((f.score||0) < 5) return;
    h += '<div style="margin-bottom:14px;page-break-inside:avoid">'
      + '<div style="font-weight:600;color:'+S.text+';margin-bottom:4px"><span style="color:'+S.accent+'">（'+(factNum++)+'）</span> '+esc(f.type||'')+' <span style="font-size:10px;color:'+(f.level==='高风险'?S.red:f.level==='中风险'?S.amber:S.green)+'">['+(f.level||'?')+']</span></div>'
      + '<div style="padding:4px 0;color:'+S.muted+'">'+esc(f.detail||'')+'</div>';
    if (f.description) h += '<div style="background:#f8fafc;padding:8px 12px;border-radius:4px;margin:6px 0;font-size:11px;color:'+S.text+'">'+esc(f.description)+'</div>';
    if (f.tax_impact) h += '<div style="font-size:11px;color:'+S.red+'">税务后果：'+esc(f.tax_impact)+'</div>';
    if (f.policy_ref) h += '<div style="font-size:10px;color:'+S.muted+'">依据：'+esc(f.policy_ref)+'</div>';
    h += '</div>';
  });
  h += '</div>';
  
  // ── 三、税款估算 ──
  var estVAT = 0, estCIT = 0;
  // Rough estimate from findings that mention amounts
  topF.forEach(function(f){
    var d = (f.detail||'') + (f.description||'');
    var m = d.match(/(\d[\d,.]*)\s*[万元]/g);
  });
  
  // ── 收入口径说明 ──
  var revenueNote = r.summary_text||'';
  var revMatch = revenueNote.match(/凭证主营收入[\d,]+元[^。]*/);
  if (revMatch) {
    h += '<div style="background:#f0f9ff;border:1px solid #bae6fd;padding:14px;border-radius:4px;margin-bottom:28px;font-size:11px;color:'+S.muted+';line-height:1.8">'
      + '<div style="font-weight:600;color:'+S.accent+';margin-bottom:4px">收入口径说明</div>'
      + '本次审核使用三种收入口径交叉验证：<br>'
      + '① 发票口径（销项发票汇总）→ 用于进销发票比对<br>'
      + '② 凭证口径（主营业务收入贷方）→ 用于总收入计算，含未开票收入<br>'
      + '③ 银行口径（对公账户入账）→ 用于收款来源匹配<br>'
      + esc(revMatch[0]) + '</div>';
  }

  h += '<div style="margin-bottom:28px"><div style="font-size:15px;font-weight:700;color:'+S.accent+';border-bottom:2px solid '+S.accent+';padding-bottom:6px;margin-bottom:14px">四、拟处理建议</div>';
  
  h += '<table style="width:100%;font-size:11px;border-collapse:collapse;margin-bottom:16px">'
    + '<tr style="background:#f8fafc"><th style="padding:8px 12px;text-align:left;border:1px solid '+S.border+'">优先级</th><th style="padding:8px 12px;text-align:left;border:1px solid '+S.border+'">处理事项</th><th style="padding:8px 12px;text-align:left;border:1px solid '+S.border+'">法律依据</th></tr>';
  
  var actions = [];
  topF.forEach(function(f){
    var sug = (f.suggestion||'').split('\n')[0];
    if (sug) {
      var pri = (f.score||0) >= 8 ? 'P0' : ((f.score||0) >= 6 ? 'P1' : 'P2');
      var priColor = pri === 'P0' ? S.red : (pri === 'P1' ? S.amber : S.green);
      actions.push({item: esc(f.type||''), basis: esc((f.policy_ref||'').substring(0,40)), pri: pri, priColor: priColor});
    }
  });
  actions = actions.slice(0, 5);
  actions.forEach(function(a){
    h += '<tr><td style="padding:6px 12px;border:1px solid '+S.border+'"><span style="display:inline-block;background:'+a.priColor+';color:#fff;padding:1px 6px;border-radius:3px;font-size:10px;font-weight:700">'+a.pri+'</span></td><td style="padding:6px 12px;border:1px solid '+S.border+'">'+a.item+'</td><td style="padding:6px 12px;border:1px solid '+S.border+';font-size:10px;color:'+S.muted+'">'+a.basis+'</td></tr>';
  });
  h += '</table></div>';
  
  // ── 四、整改建议 ──
  h += '<div style="margin-bottom:28px"><div style="font-size:15px;font-weight:700;color:'+S.accent+';border-bottom:2px solid '+S.accent+';padding-bottom:6px;margin-bottom:14px">五、整改建议</div>';
  
  var fixNum = 1;
  topF.forEach(function(f){
    if ((f.score||0) < 6 || !f.suggestion) return;
    h += '<div style="margin-bottom:12px"><div style="font-weight:600;font-size:12px;color:'+S.text+';margin-bottom:4px">'+(fixNum++)+'. '+esc(f.type||'')+'</div>'
      + '<div style="font-size:11px;color:'+S.muted+';padding-left:16px;border-left:2px solid '+S.green+'">'+esc(f.suggestion||'')+'</div></div>';
  });
  
  // 补充通用整改要求
  h += '<div style="margin-top:16px;padding:12px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:4px;font-size:11px;color:#166534;line-height:1.8">'
    + '<div style="font-weight:600;margin-bottom:4px">稽查整改通用要求</div>'
    + '1. 上述整改事项应于收到本报告后30日内完成，整改结果书面报告至主管税务机关。<br>'
    + '2. 涉及补缴税款的，应在整改期内主动申报补缴，可依法申请从轻或减轻处罚。<br>'
    + '3. 整改过程中发现的账务错误应同步调整会计账簿和财务报表。<br>'
    + '4. 建立完善的内控制度，防止同类问题再次发生。<br>'
    + '5. 整改材料包括但不限于：补缴税款凭证、调整后账务记录、补充合同及其他证明文件。</div>'
    + '</div>';
  
  // ── 五、附件 ──
  h += '<div style="margin-bottom:28px"><div style="font-size:15px;font-weight:700;color:'+S.accent+';border-bottom:2px solid '+S.accent+';padding-bottom:6px;margin-bottom:14px">六、附件清单</div>'
    + '<div style="font-size:11px;color:'+S.muted+'">';
  r.file_results.forEach(function(fr,i){
    h += (i+1)+'. '+esc(fr.file)+' （'+esc((fr.type||'?').replace(/_/g,' '))+'）<br>';
  });
  h += '</div></div>';
  
  // ── 签章 ──
  h += '<div style="text-align:right;margin-top:40px;padding-top:20px;border-top:1px solid '+S.border+'">'
    + '<div style="font-size:11px;color:'+S.muted+'">稽查执行人：___________</div>'
    + '<div style="font-size:11px;color:'+S.muted+';margin-top:8px">审理意见：___________</div>'
    + '<div style="font-size:11px;color:'+S.muted+';margin-top:16px">'+new Date().toLocaleString('zh-CN')+'</div>'
    + '</div>';
  
  h += '</div>';
  
  // Render directly without toolbar
  area.innerHTML = h;
  area.scrollIntoView({ behavior: 'smooth' });
}

function renderAnalysisReport() {
  var area = document.getElementById('tda-report-area');
  var toolbarHtml = '<div class="tda-toolbar" style="display:flex;gap:8px;margin-bottom:16px">'
    + '<button onclick="renderAuditReport()" style="padding:6px 16px;border:1px solid #e2e8f0;background:#fff;color:#64748b;border-radius:4px;font-size:12px;cursor:pointer">稽查审核报告</button>'
    + '<button onclick="renderAnalysisReport()" style="padding:6px 16px;border:2px solid #0f172a;background:#0f172a;color:#fff;border-radius:4px;font-size:12px;font-weight:600;cursor:pointer">分析视图</button>'
    + '</div>';
  area.innerHTML = toolbarHtml + (window._analysisViewHtml || '');
  area.scrollIntoView({ behavior: 'smooth' });
}
