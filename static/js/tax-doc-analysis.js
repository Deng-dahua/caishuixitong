// ==================== 涉税资料分析模块 ====================
var taxDocReportData = null;
var taxDocAnalyzing = false;
var taxDocPageActive = false;

// 确保 esc 可用
if (typeof esc === 'undefined') {
  var esc = function(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); };
}

function renderTaxDocAnalysis(container) {
  window.currentModule = '资料分析风险报告';
  taxDocPageActive = true;  // 标记页面激活

  container.innerHTML = ''
    + '<div class="risk-report-container">'
    
    // ── 标题区 ──
    + '<div class="risk-report-header">'
    + '<h2>资料分析风险报告</h2>'
    + '</div>'

    // ── 资料上传区 ──
    + '<div id="tda-upload-section" style="background:#f8fafc;border:2px dashed #cbd5e1;border-radius:10px;padding:20px 24px;margin-bottom:20px">'
    + '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">'
    + '<div>'
    + '<span style="font-weight:600;font-size:16px">上传经营资料</span>'
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

    if (!docs || docs.length === 0) {
      listEl.innerHTML = '<div style="text-align:center;padding:20px;color:var(--gray-400)">暂无上传资料，请点击上方按钮上传</div>';
      return;
    }

    var html = '<div style="margin-bottom:4px"><label><input type="checkbox" onchange="toggleAllTdaDocs(this)" style="margin-right:4px">全选</label></div>';
    try {
      docs.forEach(function(doc) {
        var size = doc.size ? (doc.size / 1024).toFixed(1) + ' KB' : '未知';
        var name = doc.original_name || doc.filename || '未知文件';
        html += '<div style="display:flex;align-items:center;justify-content:space-between;padding:4px 0;border-bottom:1px solid #f1f5f9">'
          + '<span><input type="checkbox" class="tda-doc-check" data-id="' + doc.id + '" style="margin-right:6px">'
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

  var html = ''
    // ── 数据不足警告横幅 ──
    + (r.low_data_warning ? '<div style="background:#fff3cd;border:2px solid #ffc107;border-radius:8px;padding:16px;margin-top:16px;font-size:14px;color:#856404;line-height:1.7">' 
      + '<strong>⚠️ 数据不足警告</strong><br>'
      + '系统未能从上传文件中提取到足够的结构化数据（少于10条记录）。以下分析结果基于有限数据，可能产生误报。'
      + '<br>请检查：① Excel文件第一行是否为表头 ② 文件是否为财税相关数据 ③ 文件格式是否为标准导出模板。'
      + '</div>' : '')
    // ── 综合风险总览卡片 ──
    + '<div style="background:#fff;border:1px solid var(--gray-200);border-radius:10px;padding:24px;margin-top:16px">'
    + '<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px">'
    + '<div>'
    + '<span style="font-weight:600;font-size:15px">综合风险等级：</span>'
    + '<span style="display:inline-block;padding:6px 24px;background:' + lb + ';color:' + lc + ';border-radius:6px;font-weight:700;font-size:18px;margin-left:8px">' + r.overall_level + '</span>'
    + '</div>'
    + '<div style="font-size:13px;color:var(--gray-500)">分析 ' + r.files_count + ' 份文件 · 使用 ' + r.rules_used + ' 条规则 · 识别 ' + r.total_risks + ' 项风险</div>'
    + '<div style="font-size:13px;color:var(--gray-400)">最近更新: ' + (function(){ var n=new Date(); return n.getFullYear()+'-'+String(n.getMonth()+1).padStart(2,'0')+'-'+String(n.getDate()).padStart(2,'0')+' '+String(n.getHours()).padStart(2,'0')+':'+String(n.getMinutes()).padStart(2,'0')+':'+String(n.getSeconds()).padStart(2,'0'); })() + '</div>'
    + '</div>'
    
    // 风险计数卡片
    + '<div style="display:flex;gap:12px;margin-top:16px">'
    + '<div style="flex:1;background:#fef2f2;border-radius:8px;padding:14px;text-align:center"><div style="font-size:28px;font-weight:700;color:#dc2626">' + r.high_risk + '</div><div style="font-size:11px;color:#991b1b">高风险</div></div>'
    + '<div style="flex:1;background:#fffbeb;border-radius:8px;padding:14px;text-align:center"><div style="font-size:28px;font-weight:700;color:#f59e0b">' + r.mid_risk + '</div><div style="font-size:11px;color:#92400e">中风险</div></div>'
    + '<div style="flex:1;background:#ecfdf5;border-radius:8px;padding:14px;text-align:center"><div style="font-size:28px;font-weight:700;color:#059669">' + r.low_risk + '</div><div style="font-size:11px;color:#065f46">低风险</div></div>'
    + '</div>'
    
    // 摘要
    + '<div style="background:#f8fafc;border-radius:8px;padding:14px 18px;margin-top:16px;font-size:13px;color:var(--gray-600);line-height:1.7">' + esc(r.summary_text || '') + '</div>'
    + '</div>'

    // ── 数据统计 ──
    + '<div style="background:#fff;border:1px solid var(--gray-200);border-radius:10px;padding:20px;margin-top:12px">'
    + '<b style="font-size:15px">📈 数据统计</b>'
    + '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:8px;margin-top:12px">';
  if (r.stats) {
    Object.keys(r.stats).forEach(function(k) {
      html += '<div style="background:#f8fafc;border-radius:6px;padding:10px;text-align:center"><div style="font-size:15px;font-weight:700;word-break:break-all">' + esc(String(r.stats[k])) + '</div><div style="font-size:10px;color:var(--gray-400);margin-top:2px">' + esc(k) + '</div></div>';
    });
  }
  html += '</div></div>';

  // ── 处理流水 ──
  if (r.pipeline_log && r.pipeline_log.length > 0) {
    html += '<div style="background:#fff;border:1px solid var(--gray-200);border-radius:10px;padding:20px;margin-top:12px">'
      + '<b style="font-size:15px">📋 处理流水</b>'
      + '<div style="background:#f0fdf4;border-radius:6px;padding:10px 16px;margin-top:8px;font-size:12px">';
    r.pipeline_log.forEach(function(log) {
      html += '<div style="padding:2px 0;color:var(--gray-600)">' + esc(log) + '</div>';
    });
    html += '</div></div>';
  }

  // ── 文件处理详情 ──
  if (r.file_results && r.file_results.length > 0) {
    html += '<div style="background:#fff;border:1px solid var(--gray-200);border-radius:10px;padding:20px;margin-top:12px">'
      + '<b style="font-size:15px">📁 文件处理详情</b>';
    r.file_results.forEach(function(fr) {
      var icon = fr.error ? '❌' : (fr.type === 'bank' ? '🏦' : (fr.type === 'sales_invoice' ? '🧾' : (fr.type === 'purchase_invoice' ? '📥' : (fr.type === 'voucher' ? '📋' : '📄'))));
      html += '<div style="padding:4px 0;font-size:12px;border-bottom:1px solid #f1f5f9">'
        + icon + ' <b>' + esc(fr.file) + '</b>'
        + ' <span style="color:var(--gray-400)">→ ' + esc(fr.type || 'unknown') + '</span>'
        + (fr.actions ? fr.actions.map(function(a) { return ' <span style="color:#059669">✅ ' + esc(a) + '</span>'; }).join('') : '')
        + (fr.error ? ' <span style="color:#dc2626">' + esc(fr.error) + '</span>' : '')
        + '</div>';
    });
    html += '</div>';
  }

  // ── 29域分析结果 ──
  if (r.domain_summary && r.domain_summary.length > 0) {
    html += '<div style="background:#fff;border:1px solid var(--gray-200);border-radius:10px;padding:20px;margin-top:12px">'
      + '<b style="font-size:15px">🔍 29域分析结果</b>';
    r.domain_summary.forEach(function(dr) {
      if (!dr.findings || dr.findings.length === 0) return;
      var dColor = dr.high > 0 ? '#dc2626' : (dr.mid > 0 ? '#f59e0b' : '#059669');
      html += '<div style="margin-top:16px;border:1px solid var(--gray-200);border-radius:8px;overflow:hidden">'
        + '<div style="display:flex;align-items:center;justify-content:space-between;padding:10px 14px;background:#f8fafc;border-bottom:1px solid var(--gray-200)">'
        + '<span style="font-weight:600;font-size:14px">' + esc(dr.name) + '</span>'
        + '<span style="font-size:12px;color:' + dColor + '">' + dr.count + '项发现'
        + (dr.high > 0 ? ' <span style="color:#dc2626">' + dr.high + '高</span>' : '')
        + (dr.mid > 0 ? ' <span style="color:#f59e0b">' + dr.mid + '中</span>' : '')
        + '</span></div>';
      dr.findings.forEach(function(f) {
        var cfColor = f.level === '高风险' ? '#dc2626' : (f.level === '中风险' ? '#f59e0b' : '#059669');
        var cfBg = f.level === '高风险' ? '#fef2f2' : (f.level === '中风险' ? '#fffbeb' : '#ecfdf5');
        html += '<div style="padding:14px 16px;border-bottom:1px solid #f1f5f9;font-size:13px;line-height:1.7" id="finding-' + (f._idx || 0) + '">'
          + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">'
          + '<span style="display:inline-block;padding:2px 10px;background:' + cfColor + ';color:#fff;border-radius:4px;font-size:11px;font-weight:600">' + f.level + '</span>'
          + '<b style="font-size:14px;flex:1">' + esc(f.type || '') + '</b>'
          + '<span style="font-size:11px;color:var(--gray-400)">分值：' + (f.score || '-') + '</span>'
          + '<button onclick="reviewSingleFinding(this)" data-idx="' + (f._idx || 0) + '" style="font-size:11px;padding:3px 10px;border:1px solid #93c5fd;background:#eff6ff;color:#0369a1;border-radius:4px;cursor:pointer;white-space:nowrap">复核此结论</button>'
          + '</div>'
          + '<div style="color:var(--gray-600);margin-bottom:8px">' + esc(f.detail || '') + '</div>'
          + '<div class="finding-review-result" id="review-result-' + (f._idx || 0) + '" style="display:none;margin:8px 0"></div>';
        if (f.description) {
          html += '<div style="background:' + cfBg + ';border-radius:6px;padding:10px 14px;margin-bottom:6px">'
            + '<div style="font-weight:600;font-size:12px;color:' + cfColor + ';margin-bottom:4px">📋 风险解释</div>'
            + '<div style="font-size:12px;color:var(--gray-700)">' + esc(f.description) + '</div></div>';
        }
        if (f.how_found) {
          html += '<div style="background:#f5f3ff;border:1px solid #ddd6fe;border-radius:6px;padding:10px 14px;margin-bottom:6px">'
            + '<div style="font-weight:600;font-size:12px;color:#7c3aed;margin-bottom:4px">🔍 如何得出</div>'
            + '<div style="font-size:11px;color:var(--gray-600);white-space:pre-line">' + esc(f.how_found) + '</div></div>';
        }
        if (f.tax_impact) {
          html += '<div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:6px;padding:10px 14px;margin-bottom:6px">'
            + '<div style="font-weight:600;font-size:12px;color:#ea580c;margin-bottom:4px">⚠️ 税务影响</div>'
            + '<div style="font-size:12px;color:var(--gray-700)">' + esc(f.tax_impact) + '</div></div>';
        }
        if (f.policy_ref) {
          html += '<div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:6px;padding:10px 14px;margin-bottom:6px">'
            + '<div style="font-weight:600;font-size:12px;color:#0369a1;margin-bottom:4px">📜 政策依据</div>'
            + '<div style="font-size:11px;color:var(--gray-600)">' + esc(f.policy_ref) + '</div></div>';
        }
        if (f.suggestion) {
          html += '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:6px;padding:10px 14px;margin-bottom:6px">'
            + '<div style="font-weight:600;font-size:12px;color:#059669;margin-bottom:4px">✅ 整改建议</div>'
            + '<div style="font-size:12px;color:var(--gray-700)">' + esc(f.suggestion) + '</div></div>';
        }
        html += '</div>';
      });
      html += '</div>';
    });
    html += '</div>';
  }

  // ── 详细风险列表（295规则引擎发现） ──
  if (r.all_findings && r.all_findings.length > 0) {
    var engineItems = r.all_findings.filter(function(f) { return f.category && !f.domain; });
    if (engineItems.length > 0) {
      html += '<div style="background:#fff;border:1px solid var(--gray-200);border-radius:10px;padding:20px;margin-top:12px">'
        + '<b style="font-size:15px">🛡️ 295规则引擎发现（基于100%上传文件数据，显示前30条）</b>';
      engineItems.slice(0, 30).forEach(function(f, i) {
        var lv = f.risk_level || f.level || '?';
        var color = lv === '高风险' ? '#dc2626' : (lv === '中风险' ? '#f59e0b' : '#6b7280');
        var bg = lv === '高风险' ? '#fef2f2' : (lv === '中风险' ? '#fffbeb' : '#f9fafb');
        html += '<div style="margin-top:10px;padding:12px 16px;background:' + bg + ';border-left:4px solid ' + color + ';border-radius:6px">'
          + '<div style="display:flex;align-items:center;gap:8px">'
          + '<span style="font-weight:700">#' + (i+1) + '</span>'
          + '<span style="display:inline-block;padding:2px 10px;background:' + color + ';color:#fff;border-radius:4px;font-size:11px;font-weight:600">' + esc(lv) + '</span>'
          + '<span style="font-weight:600;font-size:13px">' + esc(f.item || '') + '</span>'
          + '</div>'
          + '<div style="font-size:12px;color:var(--gray-600);margin-top:4px">' + esc(f.detail || '') + '</div>'
          + (f.suggestion ? '<div style="font-size:12px;color:#059669;margin-top:4px">💡 ' + esc(f.suggestion) + '</div>' : '')
          + '</div>';
      });
      if (engineItems.length > 30) {
        html += '<div style="text-align:center;color:var(--gray-400);padding:8px;font-size:12px">...共' + engineItems.length + '条引擎发现，此处展示前30条</div>';
      }
      html += '</div>';
    }
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
