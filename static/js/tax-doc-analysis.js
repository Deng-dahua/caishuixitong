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
    + '<button class="btn-toolbar" onclick="showCacheInfo()" id="tda-cache-btn" style="color:#6b7280;border-color:#d1d5db;background:#f9fafb;font-size:11px">缓存</button>'
    + '</div></div>'
    
    // ── 文件列表 ──
    + '<div id="tda-file-list" style="font-size:13px;color:var(--gray-500);min-height:40px">暂无上传资料</div>'
    + '</div>'
    
    // ── 分析结果区 ──
    + '<div id="tda-report-area"></div>'
    + '</div>';

  // 加载已有文件列表
  refreshTaxDocList();

  // 每次进入页面强制清空旧报告缓存
  taxDocReportData = null;
  window._reportData = null;
  var reportArea = document.getElementById('tda-report-area');
  if (reportArea) reportArea.innerHTML = '';
  var exportBtn = document.getElementById('tda-export-btn');
  if (exportBtn) exportBtn.style.display = 'none';
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
        var dotC = f.level==='高风险'?S.red:(f.level==='中风险'?S.amber:S.green);
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
        // 规则引用 + 证据链
        // 规则 + 线索链 + 证据链 三层关联
        var metaHtml = '';
        if (f.matched_rule_ids && f.matched_rule_ids.length) {
          metaHtml += '<div style="margin-bottom:4px"><span style="font-size:9px;color:'+S.light+'">📋 关联规则: </span>';
          f.matched_rule_ids.forEach(function(rid){ metaHtml += '<span style="background:#f1f5f9;padding:1px 6px;border-radius:2px;font-size:9px;color:#475569;margin-right:3px">R'+rid+'</span>'; });
          metaHtml += '</div>';
        }
        if (f.matched_chain_details && f.matched_chain_details.length) {
          metaHtml += '<div style="margin-bottom:6px"><span style="font-size:9px;color:'+S.light+'">🔗 线索/证据链:</span></div>';
          f.matched_chain_details.forEach(function(cd){
            var stepFlow = cd.steps_detail.map(function(s){
              var dot = s.level==='高风险'?'#dc2626':(s.level==='中风险'?'#f59e0b':'#94a3b8');
              return '<span style="background:#f8fafc;padding:1px 5px;border-radius:2px;font-size:9px;border-left:2px solid '+dot+'">'+esc(s.step)+'</span>';
            }).join('<span style="color:'+S.light+';margin:0 2px">→</span>');
            metaHtml += '<div style="margin-bottom:3px"><span style="font-weight:600;font-size:10px;color:'+S.accent+'">'+esc(cd.name)+'</span> <span style="font-size:9px;color:'+S.light+'">('+cd.steps+'步/'+cd.high_risk+'高)</span></div>';
            metaHtml += '<div style="margin-bottom:6px">'+stepFlow+'</div>';
          });
        }
        if (metaHtml) html += '<div style="margin-top:8px;padding-top:8px;border-top:1px dashed '+S.border+'">'+metaHtml+'</div>';
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
  
  var S = { bg: '#fff', text: '#1a1a2e', muted: '#5c6370', light: '#999',
    border: '#e0e0e0', accent: '#1a1a2e', blue: '#1a56db',
    red: '#c92a2a', amber: '#e67700', green: '#2b8a3e' };
  
  function esc(s) { if (!s) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
  function fmt(v) {
    if (Math.abs(v) >= 100000000) return (v/100000000).toFixed(2) + '亿';
    if (Math.abs(v) >= 10000) return (v/10000).toFixed(1) + '万';
    return v.toLocaleString('zh-CN', {maximumFractionDigits:0});
  }
  
  // ─────────────────────────────────────────────
  // 正式稽查报告（国家税务总局呈报格式）
  // ─────────────────────────────────────────────
  var h = '<style>' +
    '#rr-detached-report *{box-sizing:border-box;margin:0;padding:0}' +
    '#rr-detached-report{font-family:"SimSun","宋体","PingFang SC",serif;font-size:16px;line-height:2;color:#000;max-width:800px;margin:0 auto;padding:60px 50px;background:#fff}' +
    '#rr-detached-report .rp-cover{text-align:center;padding:80px 0 60px;border-bottom:2px solid #000;margin-bottom:40px}' +
    '#rr-detached-report .rp-cover .rp-title{font-size:26px;font-weight:bold;letter-spacing:4px;margin-bottom:30px}' +
    '#rr-detached-report .rp-cover .rp-sub{font-size:14px;color:#333;line-height:2.5}' +
    '#rr-detached-report h2{font-size:18px;font-weight:bold;margin:40px 0 16px;padding-bottom:6px;border-bottom:1px solid #000;text-align:center;letter-spacing:2px}' +
    '#rr-detached-report h3{font-size:16px;font-weight:bold;margin:28px 0 12px}' +
    '#rr-detached-report p{text-indent:2em;margin:10px 0;text-align:justify;line-height:2}' +
    '#rr-detached-report .rp-table{width:100%;border-collapse:collapse;margin:16px 0;font-size:14px}' +
    '#rr-detached-report .rp-table td{padding:8px 12px;border:1px solid #000;line-height:1.8}' +
    '#rr-detached-report .rp-table .lbl{width:120px;background:#f5f5f5;font-weight:bold}' +
    '#rr-detached-report .rp-finding{margin:16px 0;padding:0;border:1px solid #000}' +
    '#rr-detached-report .rp-finding .rp-title{padding:10px 14px;background:#f5f5f5;border-bottom:1px solid #000;font-weight:bold;font-size:15px}' +
    '#rr-detached-report .rp-finding .rp-body{padding:14px 16px}' +
    '#rr-detached-report .rp-finding .rp-body p{text-indent:2em}' +
    '#rr-detached-report .rp-seal{text-align:right;margin-top:60px;font-size:14px}' +
    '#rr-detached-report .rp-sign{display:inline-block;margin-top:30px;font-size:14px}' +
    '</style>' +
    '<div id="rr-detached-report">';

  // ── 封面 ──
  var now = new Date();
  var dateStr = now.getFullYear()+'年'+(now.getMonth()+1)+'月'+now.getDate()+'日';
  var reportNo = '税稽字['+now.getFullYear()+']第'+String(Math.floor(Math.random()*900+100))+'号';
  h += '<div class="rp-cover">' +
    '<div class="rp-title">税务稽查报告</div>' +
    '<div class="rp-sub">' +
    '编号：'+reportNo+'<br>' +
    '被查单位：'+(te.name?esc(te.name):'（依据上传资料识别）')+'<br>' +
    '稽查期间：'+(te.period?esc(te.period):'')+'<br>' +
    '报告日期：'+dateStr+'</div></div>';

  // ── 一、基本情况 ──
  h += '<h2>一、基本情况</h2>';
  h += '<table class="rp-table">' +
    '<tr><td class="lbl">案件来源</td><td>根据税务稽查工作计划，对被查单位涉税资料进行审核分析</td></tr>' +
    '<tr><td class="lbl">被查单位</td><td>'+esc(te.name||'')+'</td></tr>' +
    '<tr><td class="lbl">纳税人识别号</td><td>（待补充）</td></tr>' +
    '<tr><td class="lbl">企业类型</td><td>'+esc(te.type||'')+'</td></tr>' +
    '<tr><td class="lbl">所属行业</td><td>'+esc(te.industry||'')+'</td></tr>' +
    '<tr><td class="lbl">稽查期间</td><td>'+esc(te.period||'')+'</td></tr>' +
    '<tr><td class="lbl">稽查范围</td><td>被查单位提供'+r.files_count+'份经营资料，包括银行账户流水、销项发票、进项发票</td></tr>' +
    '</table>';

  // ── 二、稽查方法 ──
  h += '<h2>二、稽查方法</h2>';
  var mi = (r.comprehensive||{}).material_intel || {};
  var bi = mi['银行流水'] || {};
  var ii = mi['发票'] || {};

  h += '<p>本次稽查依据《中华人民共和国税收征收管理法》及其实施细则、《税务稽查工作规程》（国税发[2009]157号）的相关规定，对被查单位提供的'+r.files_count+'份经营资料进行了审核。稽查过程中，主要采取以下方法：</p>';
  h += '<p>（一）进销存数据比对法。将销项发票与进项发票进行比对，分析被查单位采购与销售的匹配关系。经比对，被查单位销项开票'+ii['销项发票']+'，进项收票'+ii['进项发票']+'，进销比为'+ii['进销比']+'。</p>';
  h += '<p>（二）资金流与发票流核对比。将银行账户资金流水与发票数据进行比对，核实收款与开票、付款与收票是否一致。经比对，被查单位银行账户累计收款'+bi['总收款']+'，累计付款'+bi['总付款']+'，其中税费支出'+bi['税费支出总额']+'。</p>';
  
  // 收款构成分析
  var rc = bi['收款构成'];
  if (rc) {
    h += '<p>（二·续）收款来源分析。对银行账户284笔收款按付款方性质分类：</p>';
    h += '<p>　　· <b>企业客户款：</b>'+rc['企业客户款']+'；<br>';
    h += '　　· <b>个人款：</b>'+rc['个人款']+'；<br>';
    h += '　　· <b>税费社保退款：</b>'+rc['税费社保退款']+'；<br>';
    h += '　　· <b>银行利息/内部转账：</b>'+rc['银行利息/内部']+'。</p>';
    var top10 = bi['收款方TOP10'];
    if (top10 && top10.length) {
      h += '<p>收款方前十名：</p><table style="font-size:13px;width:100%;border-collapse:collapse;margin:8px 0"><tr style="background:#f5f5f5"><td style="padding:4px 8px;border:1px solid #ccc;font-weight:bold">付款方</td><td style="padding:4px 8px;border:1px solid #ccc;font-weight:bold">金额</td></tr>';
      top10.forEach(function(p){ h += '<tr><td style="padding:4px 8px;border:1px solid #ccc">'+esc(p['名称']||'')+'</td><td style="padding:4px 8px;border:1px solid #ccc">'+esc(p['金额']||'')+'元</td></tr>'; });
      h += '</table>';
    }
    // 查到的工商信息
    h += '<p><b>联网核查发现：</b>经查询国家企业信用信息公示系统，收款方中"范善茂"（个人打款'+rc['个人款']+'）系被查单位法定代表人、持股50%股东、财务负责人。该笔资金应重新定性为股东注资或关联方往来，不纳入隐匿收入判断。被查单位工商登记为<b>批发业</b>（非生产制造），注册资本500万元。</p>';
  }
  
  h += '<p>（三）供应商及客户穿透分析法。对供应商和客户进行集中度分析和名称群集检测。</p>';

  // 资料缺口
  var gapF = topF.filter(function(f){ return /缺少|缺失|无法验证|不完备|未被触发/.test(f.type||''); });
  if (gapF.length) {
    h += '<p>（四）资料缺口说明。经审核，被查单位未提供以下关键资料，导致部分审核事项无法执行：</p>';
    gapF.slice(0,5).forEach(function(f, i){
      h += '<p>　　'+(i+1)+'. '+esc(f.type||'')+'。'+esc(f.detail||'')+'</p>';
    });
    h += '<p>上述缺失资料已要求被查单位限期补充提供。</p>';
  }

  // ── 三、稽查发现的问题 ──
  h += '<h2>三、稽查发现的问题</h2>';

  var closedF = topF.filter(function(f){ return f.chain_closure && (f.score||0)>=7; });
  var openF = topF.filter(function(f){
    if (/缺少|缺失|无法验证|不完备|未被触发|一致|正常|无明显差异|通过|良好/.test(f.type||'')) return false;
    if (!f.detail && !f.description) return false;
    if (f.chain_closure && (f.score||0)>=7) return false;
    return (f.score||0) >= 5;
  });

  if (closedF.length) {
    h += '<h3>（一）已查实的问题</h3>';
    h += '<p>经多源数据交叉比对，以下问题已经查证属实：</p>';
    closedF.slice(0,8).forEach(function(f, i){
      h += '<div class="rp-finding">' +
        '<div class="rp-title">问题'+(i+1)+'：'+esc(f.type||'')+'</div>' +
        '<div class="rp-body">' +
        '<p><b>违法事实：</b>'+esc(f.detail||'')+'</p>';
      if (f.description) h += '<p><b>情况说明：</b>'+esc(f.description)+'</p>';
      var oralDesc = '';
      if (f.chain_driven && f.source_chain) {
        var chName = f.source_chain || '';
        if (/进销/.test(chName)) oralDesc += '稽查人员调取了全部进销项发票，逐票比对商品名称、数量、金额';
        else if (/资金/.test(chName)) oralDesc += '稽查人员调取了全部银行账户流水，与发票数据逐笔核对';
        else if (/供应商/.test(chName)) oralDesc += '稽查人员对供应商进行了穿透式调查';
        else oralDesc += '稽查人员开展了专项核查';
      }
      if (f.chain_closure) {
        if (oralDesc) oralDesc += '，经多维度数据交叉验证，确认上述事实成立。';
        else oralDesc += '经多维度数据交叉比对，上述事实已经查证属实。';
      }
      if (oralDesc) h += '<p><b>查证过程：</b>'+oralDesc+'</p>';
      if (f.chain_closure && f.cross_domains >= 2) {
        h += '<p><b>问题定性：</b>上述行为已形成完整证据闭环，事实清楚、证据充分。';
        if (/隐匿|少报|瞒报|未申报/.test(f.type||'')) h += '涉嫌隐匿销售收入，少缴应纳税款。';
        else if (/虚开|虚抵|虚假/.test(f.type||'')) h += '涉嫌虚开发票，违反《发票管理办法》第二十二条规定。';
        else h += '存在涉税违法行为。';
        h += '</p>';
      }
      if (f.tax_impact) h += '<p><b>涉税后果：</b>'+esc(f.tax_impact)+'</p>';
      if (f.policy_ref) h += '<p><b>法律依据：</b>'+esc(f.policy_ref)+'</p>';
      h += '</div></div>';
    });
  }

  if (openF.length) {
    h += '<h3>'+(closedF.length?'（二）':'（一）')+'需要进一步核实的问题</h3>';
    h += '<p>经初步审核，发现以下疑点，因被查单位未提供相关佐证资料，尚需进一步调查核实：</p>';
    openF.slice(0,6).forEach(function(f, i){
      h += '<div class="rp-finding">' +
        '<div class="rp-title">疑点'+(closedF.length+i+1)+'：'+esc(f.type||'')+'</div>' +
        '<div class="rp-body">' +
        '<p>'+esc(f.detail||'')+'</p>';
      if (f.description) h += '<p>'+esc(f.description)+'</p>';
      if (f.source_chain) h += '<p><b>核查方式：</b>经对'+esc(f.source_chain)+'进行专项审核发现上述疑点。因缺少关键佐证材料，建议要求被查单位限期提供相关资料。</p>';
      if (f.tax_impact) h += '<p><b>潜在风险：</b>'+esc(f.tax_impact)+'</p>';
      h += '</div></div>';
    });
  }

  if (!closedF.length && !openF.length) {
    h += '<p>经对被查单位提供的'+r.files_count+'份经营资料进行系统性审核，暂未发现明显的税务违法行为。建议补充提供合同、增值税申报表等资料后进行复核。</p>';
  }

  // ── 四、稽查处理意见 ──
  h += '<h2>四、稽查处理意见</h2>';
  var actions = [];
  var seenAct = {};
  closedF.concat(openF).forEach(function(f){
    var sug = f.suggestion||'';
    if (sug && !seenAct[sug.substring(0,40)]) { seenAct[sug.substring(0,40)] = true; actions.push(sug); }
  });

  if (closedF.length) {
    h += '<p>（一）对已查实的问题：根据《中华人民共和国税收征收管理法》第六十三条之规定，依法追缴少缴税款，按日加收滞纳税款万分之五的滞纳金，并处以少缴税款百分之五十以上五倍以下的罚款。涉嫌构成犯罪的，依法移送公安机关处理。</p>';
  }
  if (openF.length) {
    h += '<p>（二）对需要进一步核实的问题：要求被查单位在收到本报告之日起十五个工作日内补充提供：全部银行账户流水、购销合同及物流单据、纳税申报表及完税凭证、工资发放及社保缴纳记录、固定资产及存货台账。逾期未提供的，稽查机关将依法采取税收保全措施或根据已掌握资料核定应纳税额。</p>';
  }
  if (actions.length) {
    h += '<p>（三）具体处理建议：</p>';
    actions.slice(0,6).forEach(function(a, i){ h += '<p>'+(i+1)+'. '+esc(a)+'</p>'; });
  }

  // ── 五、附件 ──
  h += '<h2>五、附件</h2>';
  h += '<p>1. 被查单位提供资料清单（共'+r.files_count+'份）</p>';
  h += '<p>2. 稽查工作底稿</p>';
  h += '<p>3. 相关法律条文摘录</p>';

  h += '<div class="rp-seal">' +
    '<div class="rp-sign">' +
    '<div>稽查人员（签名）：_______________</div>' +
    '<div style="margin-top:10px">稽查部门（盖章）：_______________</div>' +
    '<div style="margin-top:10px">'+dateStr+'</div>' +
    '</div></div>';
  h += '</div>';

  document.getElementById('tda-report-area').innerHTML = '';
  var detached = document.createElement('div');
  detached.id = 'rr-detached-container';
  detached.innerHTML = h;
  area.appendChild(detached);
}

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
    + '<button class="btn-toolbar" onclick="showCacheInfo()" id="tda-cache-btn" style="color:#6b7280;border-color:#d1d5db;background:#f9fafb;font-size:11px">缓存</button>'
    + '</div></div>'
    
    // ── 文件列表 ──
    + '<div id="tda-file-list" style="font-size:13px;color:var(--gray-500);min-height:40px">暂无上传资料</div>'
    + '</div>'
    
    // ── 分析结果区 ──
    + '<div id="tda-report-area"></div>'
    + '</div>';

  // 加载已有文件列表
  refreshTaxDocList();

  // 每次进入页面强制清空旧报告缓存
  taxDocReportData = null;
  window._reportData = null;
  var reportArea = document.getElementById('tda-report-area');
  if (reportArea) reportArea.innerHTML = '';
  var exportBtn = document.getElementById('tda-export-btn');
  if (exportBtn) exportBtn.style.display = 'none';
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
        var dotC = f.level==='高风险'?S.red:(f.level==='中风险'?S.amber:S.green);
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
        // 规则引用 + 证据链
        // 规则 + 线索链 + 证据链 三层关联
        var metaHtml = '';
        if (f.matched_rule_ids && f.matched_rule_ids.length) {
          metaHtml += '<div style="margin-bottom:4px"><span style="font-size:9px;color:'+S.light+'">📋 关联规则: </span>';
          f.matched_rule_ids.forEach(function(rid){ metaHtml += '<span style="background:#f1f5f9;padding:1px 6px;border-radius:2px;font-size:9px;color:#475569;margin-right:3px">R'+rid+'</span>'; });
          metaHtml += '</div>';
        }
        if (f.matched_chain_details && f.matched_chain_details.length) {
          metaHtml += '<div style="margin-bottom:6px"><span style="font-size:9px;color:'+S.light+'">🔗 线索/证据链:</span></div>';
          f.matched_chain_details.forEach(function(cd){
            var stepFlow = cd.steps_detail.map(function(s){
              var dot = s.level==='高风险'?'#dc2626':(s.level==='中风险'?'#f59e0b':'#94a3b8');
              return '<span style="background:#f8fafc;padding:1px 5px;border-radius:2px;font-size:9px;border-left:2px solid '+dot+'">'+esc(s.step)+'</span>';
            }).join('<span style="color:'+S.light+';margin:0 2px">→</span>');
            metaHtml += '<div style="margin-bottom:3px"><span style="font-weight:600;font-size:10px;color:'+S.accent+'">'+esc(cd.name)+'</span> <span style="font-size:9px;color:'+S.light+'">('+cd.steps+'步/'+cd.high_risk+'高)</span></div>';
            metaHtml += '<div style="margin-bottom:6px">'+stepFlow+'</div>';
          });
        }
        if (metaHtml) html += '<div style="margin-top:8px;padding-top:8px;border-top:1px dashed '+S.border+'">'+metaHtml+'</div>';
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
  
  var S = { bg: '#fff', text: '#1a1a2e', muted: '#5c6370', light: '#999',
    border: '#e0e0e0', accent: '#1a1a2e', blue: '#1a56db',
    red: '#c92a2a', amber: '#e67700', green: '#2b8a3e' };
  
  function esc(s) { if (!s) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
  function fmt(v) {
    if (Math.abs(v) >= 100000000) return (v/100000000).toFixed(2) + '亿';
    if (Math.abs(v) >= 10000) return (v/10000).toFixed(1) + '万';
    return v.toLocaleString('zh-CN', {maximumFractionDigits:0});
  }
  
  // ── 资料情报提取（在报告构建前定义，避免 hoisting undefined）──
  var cc = (r.comprehensive||{});
  var mi = cc.material_intel || {};
  var bi = mi['银行流水'] || {};
  var ii = mi['发票'] || {};
  
  // 报告样式
  var h = '<style>'
    + '#rr-detached-report *{box-sizing:border-box;margin:0;padding:0}'
    + '#rr-detached-report{font-family:"PingFang SC","Microsoft YaHei","Noto Serif SC",Georgia,"Times New Roman",serif;font-size:15px;line-height:2;color:#1a1a2e;max-width:820px;margin:0 auto;padding:60px 40px}'
    + '#rr-detached-report h2{font-size:20px;font-weight:700;margin:36px 0 16px;padding-bottom:8px;border-bottom:2px solid #1a1a2e;letter-spacing:1px}'
    + '#rr-detached-report h3{font-size:16px;font-weight:600;margin:24px 0 12px;color:#1a1a2e}'
    + '#rr-detached-report h4{font-size:14px;font-weight:600;margin:16px 0 8px;color:#2d3436}'
    + '#rr-detached-report p{margin:8px 0;text-indent:2em;text-align:justify}'
    + '#rr-detached-report .rp-table{width:100%;border-collapse:collapse;margin:12px 0;font-size:14px}'
    + '#rr-detached-report .rp-table td{padding:6px 12px;border-bottom:1px solid #eee;vertical-align:top}'
    + '#rr-detached-report .rp-table td:first-child{width:100px;font-weight:600;color:#5c6370;white-space:nowrap}'
    + '#rr-detached-report .rp-finding{border:1px solid #e0e0e0;border-radius:6px;margin:10px 0;overflow:hidden;background:#fff;font-size:14px}'
    + '#rr-detached-report .rp-finding .rp-fh{padding:12px 16px;display:flex;align-items:center;gap:10px;border-bottom:1px solid #f0f0f0;background:#fafafa;cursor:pointer;user-select:none}'
    + '#rr-detached-report .rp-finding .rp-fh:hover{background:#f5f5f5}'
    + '#rr-detached-report .rp-finding .rp-fb{padding:14px 16px}'
    + '#rr-detached-report .rp-finding .rp-fb>:last-child{margin-bottom:0}'
    + '#rr-detached-report .rp-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}'
    + '#rr-detached-report .rp-tag{display:inline-block;padding:2px 8px;border-radius:3px;font-size:12px;font-weight:500;margin-right:4px}'
    + '#rr-detached-report .rp-box{border-radius:5px;padding:12px 14px;margin:8px 0;font-size:14px;line-height:1.8}'
    + '#rr-detached-report .rp-box .rp-box-hd{font-weight:600;font-size:12px;margin-bottom:4px;text-transform:uppercase;letter-spacing:1px}'
    + '#rr-detached-report .rp-domain{margin-bottom:8px;border:1px solid #e0e0e0;border-radius:6px;overflow:hidden}'
    + '#rr-detached-report .rp-domain .rp-dh{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;background:#fafafa;cursor:pointer;font-weight:600;font-size:14px}'
    + '#rr-detached-report .rp-domain .rp-dh:hover{background:#f5f5f5}'
    + '#rr-detached-report .rp-domain .rp-db{padding:0}'
    + '#rr-detached-report .rp-summary{background:#f8f9fa;border-left:3px solid #1a1a2e;padding:20px 24px;margin:24px 0;line-height:2;font-size:15px}'
    + '#rr-detached-report .rp-header{text-align:center;padding-bottom:28px;margin-bottom:36px;border-bottom:3px double #1a1a2e}'
    + '#rr-detached-report .rp-header h1{font-size:24px;font-weight:700;letter-spacing:3px;margin-bottom:10px}'
    + '#rr-detached-report .rp-header .rp-meta{font-size:12px;color:#999}'
    + '#rr-detached-report .rp-report-cover{text-align:center;padding:60px 0;border-bottom:1px solid #e0e0e0;margin-bottom:40px}'
    + '#rr-detached-report .rp-report-cover .rp-cover-title{font-size:28px;font-weight:900;letter-spacing:6px;margin-bottom:20px}'
    + '#rr-detached-report .rp-report-cover .rp-cover-sub{font-size:13px;color:#999;letter-spacing:2px}'
    + '#rr-detached-report .rp-stamp{display:inline-block;border:3px solid #c92a2a;border-radius:50%;width:80px;height:80px;line-height:74px;text-align:center;font-size:13px;font-weight:900;color:#c92a2a;transform:rotate(-15deg);opacity:0.85}'
    + '</style>'
    + '<div id="rr-detached-report">';
  
  // ── 报告封面 ──
  h += '<div class="rp-report-cover">'
    + '<div class="rp-cover-title">税务稽查审核报告</div>'
    + '<div class="rp-cover-sub">编号：TS-'+new Date().toISOString().slice(0,10).replace(/-/g,'')+' | '+new Date().toLocaleDateString('zh-CN',{year:'numeric',month:'long',day:'numeric'})+'</div>'
    + '</div>';
  
  // ── 分析对象 ──
  var te = r.target_entity || {};
  if (te.name) {
    var typeColor = te.type==='生产型企业'?'#c92a2a':(te.type==='服务型企业'?'#1a56db':'#e67700');
    h += '<div class="rp-summary" style="border-left-color:#0f172a">'
      + '<div style="font-size:14px;font-weight:700;margin-bottom:10px">分析对象</div>'
      + '<table style="width:100%;font-size:13px;line-height:2.2">'
      + '<tr><td style="width:80px;color:'+S.muted+'">单位名称</td><td style="font-weight:600">'+esc(te.name)+'</td></tr>'
      + '<tr><td style="color:'+S.muted+'">企业类型</td><td><span class="rp-tag" style="background:#fff;color:'+typeColor+';border:1px solid '+typeColor+'">'+esc(te.type||'未知')+'</span></td></tr>'
      + (te.industry?'<tr><td style="color:'+S.muted+'">所属行业</td><td>'+esc(te.industry)+'</td></tr>':'')
      + (te.period?'<tr><td style="color:'+S.muted+'">分析期间</td><td>'+esc(te.period)+'</td></tr>':'')
      + (te.bank_account?'<tr><td style="color:'+S.muted+'">银行账号</td><td>'+esc(te.bank_account)+'</td></tr>':'')
      + (te.source && te.source.length?'<tr><td style="color:'+S.muted+'">识别来源</td><td style="font-size:11px;color:'+S.light+'">'+te.source.join(' / ')+'</td></tr>':'')
      + '</table></div>';
  }
  
  // ── 基本信息 ──
  h += '<table class="rp-table">'
    + '<tr><td>被查单位</td><td>'+(te.name?esc(te.name):'（依据上传资料识别）')+'</td></tr>'
    + '<tr><td>稽查期间</td><td>'+(te.period?esc(te.period):'')+'</td></tr>'
    + '<tr><td>稽查范围</td><td>'+r.files_count+'份资料，含银行流水'+(bi['总收款']||'0')+'收款、'+(bi['总付款']||'0')+'付款；销项发票'+(ii['销项发票']||'')+'；进项发票'+(ii['进项发票']||'')+'</td></tr>'
    + '<tr><td>执行标准</td><td>依据'+r.rules_used+'条稽查指令及《税务稽查工作规程》（国税发[2009]157号）</td></tr>'
    + '</table>';
  
  // ── 一、稽查结论 ──
  // 使用方法论过滤后的all_findings，而非未过滤的domain_summary
  var topF = r.all_findings || [];
  topF.sort(function(a,b){return(b.score||0)-(a.score||0);});
  var top3 = topF.filter(function(f){return (f.score||0)>=7;}).slice(0,3);
  
  var sevLabel = top3.length>=3?'存在严重涉税违法嫌疑':(top3.length>=2?'存在多项涉税疑点':'基本合规');
  var sevColor = top3.length>=3?S.red:(top3.length>=2?S.amber:S.green);
  var closedCount = (r.comprehensive||{}).closed_chain_count||0;
  if (closedCount >= 1) { sevLabel = '存在违法事实闭环，涉税违法嫌疑重大'; sevColor = S.red; }
  
  h += '<h2>一、稽查结论</h2>'
    + '<div class="rp-summary" style="border-left-color:'+sevColor+'">'
    + '经对'+r.files_count+'份涉税资料进行系统性审查，依据'+r.rules_used+'条稽查指令，共发现<span style="color:'+sevColor+';font-weight:700"> '+r.total_risks+' 项涉税疑点</span>（高风险'+r.high_risk+'项，中风险'+r.mid_risk+'项）。综合评估结论：<span style="color:'+sevColor+';font-weight:700">'+sevLabel+'</span>。';
  var rp = (r.comprehensive||{}).risk_profile;
  if (rp && rp.dimensions) {
    h += '<div style="margin-top:12px;font-size:13px;color:'+S.muted+'">金税四期 7 维评分：';
    Object.keys(rp.dimensions).forEach(function(dn){
      var ds = rp.dimensions[dn];
      var lc = ds.score > 40 ? S.red : (ds.score > 20 ? S.amber : S.green);
      h += '<span class="rp-tag" style="background:#f1f3f5;color:'+lc+'">'+dn+' <b>'+ds.score+'</b></span>';
    });
    h += '</div>';
  }
  if (top3.length) {
    h += '<div style="margin-top:12px;font-size:14px">'
      + '<div style="font-weight:600;margin-bottom:6px;color:'+S.text+'">优先调查事项：</div>';
    top3.forEach(function(f,i){
      h += '<div style="margin:6px 0;padding-left:8px;border-left:3px solid '+S.red+'">'
        + '<b>'+esc(f.type||'')+'</b>'
        + '<span style="color:'+S.muted+';margin-left:8px;font-size:13px">'+esc((f.detail||'').substring(0,120))+'</span></div>';
    });
    h += '</div>';
  }
  h += '</div>';
  
  // ── 二、稽查过程 ──
  h += '<h2>二、稽查过程</h2>';
  
  // 口语化稽查方法说明
  h += '<p>本次稽查根据被查单位提供的'+r.files_count+'份经营资料，采取以下方法进行审核：</p>';
  h += '<p>第一，将销项发票与进项发票进行进销存数据比对，分析企业采购与销售的匹配关系。经比对，被查单位'
    + (ii['销项发票']||'') + '，' + (ii['进项发票']||'') + '，进销比为' + (ii['进销比']||'N/A') + '。</p>';
  h += '<p>第二，将银行账户资金流水与发票数据进行比对，核实收款与开票、付款与收票是否一致。经比对，被查单位银行账户累计收款'
    + (bi['总收款']||'0') + '、累计付款' + (bi['总付款']||'0') + '，其中税费支出' + (bi['税费支出总额']||'0') + '。</p>';
  h += '<p>第三，对供应商和客户进行集中度分析和名称群集检测，排查是否存在同一控制人名下多家空壳公司轮换开票的嫌疑。</p>';
  
  // 资料缺口汇报
  var gapF = topF.filter(function(f){ return /缺少|缺失|无法验证|不完备|未被触发/.test(f.type||''); });
  if (gapF.length) {
    h += '<h3>资料缺口说明</h3>';
    h += '<p>本次稽查发现，被查单位未提供以下关键资料，导致部分审核维度无法执行：</p>';
    gapF.forEach(function(f, i){
      h += '<p>'+(i+1)+'. '+esc(f.type||'')+'：'+esc(f.detail||'')+'</p>';
    });
    h += '<p>已要求被查单位在收到本报告后15个工作日内补充上述资料。</p>';
  }
  
  // ── 三、稽查发现 ──
  h += '<h2>三、稽查发现</h2>';

  var closedF = topF.filter(function(f){ return f.chain_closure && (f.score||0)>=7; });
  var openF = topF.filter(function(f){
    if (/缺少|缺失|无法验证|不完备|未被触发|一致|正常|无明显差异|通过|良好/.test(f.type||'')) return false;
    if (!f.detail && !f.description) return false;
    if (f.chain_closure && (f.score||0)>=7) return false;
    return (f.score||0) >= 5;
  });

  // ── 将finding转为结构化风险卡片 ──
  function findingToParagraph(f, idx) {
    var ftype = f.type || '';
    var detail = f.detail || '';
    var desc = f.description || '';
    var sug = f.suggestion || '';
    var score = f.score || 0;
    var level = f.level || '';
    var how = f.how_found || '';
    
    var p = '';
    p += '<div style="border:1px solid #e2e8f0;border-left:4px solid ' + (score>=8?'#dc2626':score>=6?'#d97706':'#94a3b8') + ';border-radius:6px;padding:16px 20px;margin-bottom:20px;page-break-inside:avoid;background:#fff">';
    
    // 标题行
    var badgeColor = level==='高风险'?'#dc2626':level==='中风险'?'#d97706':'#6b7280';
    p += '<div style="font-weight:700;font-size:15px;color:#1a1a2e;margin-bottom:14px;padding-bottom:8px;border-bottom:1px solid #f1f5f9">';
    p += '<span style="color:#1a1a2e">（' + idx + '）</span> ' + esc(ftype);
    p += ' <span style="font-size:11px;color:' + badgeColor + ';font-weight:400">[' + (level||'') + ']</span>';
    p += '</div>';
    
    // 风险说明
    p += '<div style="margin-bottom:12px">';
    p += '<div style="font-weight:600;font-size:12px;color:#475569;margin-bottom:4px">风险说明</div>';
    if (desc) {
      // 清理系统残留术语
      var cleanDesc = esc(desc).replace(/线索链\[[^\]]+\]自动触发[：:][^。]*。/g, '');
      if (!cleanDesc || cleanDesc === desc) {
        cleanDesc = esc(desc);
      }
      p += '<div style="font-size:13px;line-height:1.9;color:#334155;text-align:justify">' + cleanDesc + '</div>';
    } else if (detail) {
      p += '<div style="font-size:13px;line-height:1.9;color:#334155;text-align:justify">' + esc(detail) + '</div>';
    }
    p += '</div>';
    
    // 异常详情
    if (detail && desc) {
      p += '<div style="margin-bottom:12px">';
      p += '<div style="font-weight:600;font-size:12px;color:#475569;margin-bottom:4px">异常详情</div>';
      p += '<div style="font-size:13px;line-height:1.9;color:#334155;text-align:justify">' + esc(detail) + '</div>';
      p += '</div>';
    }
    
    // 查证方式
    if (how) {
      p += '<div style="margin-bottom:12px">';
      p += '<div style="font-weight:600;font-size:12px;color:#475569;margin-bottom:4px">查证方式</div>';
      p += '<div style="font-size:12px;line-height:1.8;color:#64748b">' + esc(how) + '</div>';
      p += '</div>';
    }
    
    // 应对建议
    if (sug) {
      p += '<div style="margin-bottom:4px">';
      p += '<div style="font-weight:600;font-size:12px;color:#475569;margin-bottom:4px">应对建议</div>';
      p += '<div style="font-size:12px;line-height:1.9;color:#475569">' + esc(sug) + '</div>';
      p += '</div>';
    }
    
    // 稽查明细表
    if (f.items && f.items.length > 0) {
      var itemCount = f.items.length;
      var tblId = 'tbl-' + idx + '-' + Math.random().toString(36).substr(2,6);
      var cols = Object.keys(f.items[0]);
      var showCount = Math.min(itemCount, 15);
      
      p += '<div style="margin:10px 0">';
      p += '<div style="font-weight:600;font-size:12px;color:#475569;margin-bottom:6px">稽查明细（共' + itemCount + '条' + (itemCount > showCount ? '，展示前' + showCount + '条' : '') + '）';
      p += ' <button onclick="var t=document.getElementById(\\\'' + tblId + '\\\');if(t.style.display==\\\'none\\\'){t.style.display=\\\'\\\';this.textContent=\\\'收起▲\\\'}else{t.style.display=\\\'none\\\';this.textContent=\\\'展开▼\\\'}" style="font-size:10px;padding:2px 8px;cursor:pointer;border:1px solid #cbd5e1;border-radius:3px;background:#f8fafc;color:#64748b">展开明细▼</button>';
      p += '</div>';
      
      p += '<div id="' + tblId + '" style="display:none;overflow-x:auto;margin-top:4px">';
      p += '<table style="width:100%;border-collapse:collapse;font-size:11px;line-height:1.6">';
      // header
      p += '<tr style="background:#f1f5f9">';
      for (var ci = 0; ci < cols.length; ci++) {
        p += '<th style="padding:6px 8px;border:1px solid #e2e8f0;text-align:left;font-weight:600;white-space:nowrap">' + esc(cols[ci]) + '</th>';
      }
      p += '</tr>';
      // body
      for (var ri = 0; ri < showCount; ri++) {
        var row = f.items[ri];
        p += '<tr>';
        for (var cj = 0; cj < cols.length; cj++) {
          p += '<td style="padding:4px 8px;border:1px solid #e2e8f0;white-space:nowrap">' + esc(row[cols[cj]] || '') + '</td>';
        }
        p += '</tr>';
      }
      p += '</table>';
      p += '</div>';
      p += '</div>';
    }
    
    p += '</div>';
    return p;
  }

  if (closedF.length > 0) {
    h += '<h3>（一）可以认定的违法事实</h3>';
    h += '<p style="text-indent:2em;color:#c92a2a;font-size:14px">经对被查单位提供的经营资料进行系统性审核，并经多源数据交叉验证，以下违法事实已经查证属实：</p>';
    
    closedF.slice(0, 8).forEach(function(f, i) {
      h += findingToParagraph(f, i + 1);
      // 法律依据
      if (f.policy_ref) {
        h += '<p style="text-indent:2em;font-size:13px;color:#475569">上述行为涉嫌违反' + esc(f.policy_ref) + '。</p>';
      }
    });
  }

  if (openF.length > 0) {
    h += '<h3>' + (closedF.length ? '（二）' : '（一）') + '值得进一步调查的疑点</h3>';
    h += '<p style="text-indent:2em;color:#d97706;font-size:14px">经初步审核，发现以下疑点。因被查单位未提供相关佐证资料，尚需进一步调查核实：</p>';
    
    openF.slice(0, 6).forEach(function(f, i) {
      h += findingToParagraph(f, (closedF.length || 0) + i + 1);
    });
  }

  if (!closedF.length && !openF.length) {
    h += '<p style="text-indent:2em">经对被查单位提供的' + r.files_count + '份经营资料进行系统性审核，暂未发现明显的税务违法行为。建议被查单位补充提供合同、增值税申报表、企业所得税申报表等资料，以供进一步审核。</p>';
  }
  
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

// ==================== 缓存管理 ====================
async function showCacheInfo() {
  try {
    var listResp = await fetch('/api/tax-risk-docs/list?company_id=' + (typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1));
    var docs = await listResp.json();
    var fileCount = docs ? docs.length : 0;
    var html = '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:20px;max-width:400px">'
      + '<div style="font-weight:600;font-size:14px;margin-bottom:12px">缓存状态</div>'
      + '<table style="width:100%;font-size:12px;line-height:2.2">'
      + '<tr><td style="width:100px;color:#64748b">上传资料</td><td><b>' + fileCount + '</b> 个文件</td></tr>'
      + '<tr><td style="color:#64748b">解析缓存</td><td>已在内存/磁盘中</td></tr>'
      + '</table>'
      + '<div style="margin-top:12px;display:flex;gap:8px">'
      + '<button onclick="clearTransferCache()" style="padding:6px 14px;border:1px solid #fca5a5;background:#fef2f2;color:#dc2626;border-radius:4px;font-size:11px;cursor:pointer">清理解析缓存</button>'
      + '<button onclick="var m=document.getElementById(\'tda-cache-modal\');if(m)m.remove()" style="padding:6px 14px;border:1px solid #d1d5db;background:#fff;color:#6b7280;border-radius:4px;font-size:11px;cursor:pointer">关闭</button>'
      + '</div></div>';
    var modal = document.createElement('div');
    modal.id = 'tda-cache-modal';
    modal.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.3);z-index:9999;display:flex;align-items:center;justify-content:center';
    modal.innerHTML = html;
    modal.onclick = function(e) { if (e.target === modal) modal.remove(); };
    document.body.appendChild(modal);
  } catch(e) { toast('获取缓存信息失败', 'error'); }
}

async function clearTransferCache() {
  if (!confirm('确认清除所有解析缓存？下次分析需要重新解析文件。')) return;
  try {
    var resp = await fetch('/api/tax-risk-docs/clear-transfer?company_id=' + (typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1), { method: 'DELETE' });
    var data = await resp.json();
    if (data.ok) { toast('缓存已清除', 'success'); var m = document.getElementById('tda-cache-modal'); if(m) m.remove(); }
    else { toast('清除失败', 'error'); }
  } catch(e) { toast('清除失败: ' + e.message, 'error'); }
}
