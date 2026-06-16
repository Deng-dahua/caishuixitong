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
        html += '<div style="display:flex;align-items:center;justify-content:space-between;padding:4px 0;border-bottom:1px solid #f1f5f9">'
          + '<span><span style="color:#94a3b8;font-size:10px;width:24px;display:inline-block;text-align:right;margin-right:4px">' + (idx+1) + '.</span>'
          + '<input type="checkbox" class="tda-doc-check" data-id="' + doc.id + '" style="margin-right:6px">'
          + esc(name) + ' <span style="color:var(--gray-400);font-size:11px">' + size + '</span></span>'
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
    + '<div style="flex:1;text-align:center"><div style="font-size:11px;color:'+S.muted+';line-height:1.6;margin-top:4px">'+esc(r.summary_text||'')+'</div></div>'
    + '</div></div>';

  // ═══ 2. Comprehensive ═══
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

  area.innerHTML = html;
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
