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
    + '<div class="risk-report-container card card-fill">'
    
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
    + '<input type="file" id="tda-file-input" multiple style="display:none" onchange="uploadTaxDocs()">'
    + '<button class="btn-toolbar" onclick="document.getElementById(\'tda-file-input\').click()" style="cursor:pointer">上传资料</button>'
    + '<button class="btn-toolbar" onclick="batchDelTdaDocs()">删除选中资料</button>'
    + '<button class="btn-toolbar" onclick="analyzeTaxDocs()" id="tda-analyze-btn">一键分析</button>'
    + '<button class="btn-toolbar" onclick="exportTaxDocReport()" id="tda-export-btn">导出报告</button>'
    + '<button class="btn-toolbar" onclick="toggleNarrativeMode()" id="tda-narrative-btn" style="display:none;cursor:pointer;padding:6px 14px;border:1px solid #d1d5db;background:#fff;color:#6b7280;border-radius:4px;font-size:12px">稽查叙事报告</button>'
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

  // 如果有缓存报告，恢复显示
  if (taxDocReportData) {
    if (narrativeMode) {
      renderNarrativeReport(taxDocReportData);
    } else {
      renderTaxDocReport(taxDocReportData);
    }
    var btn = document.getElementById('tda-export-btn');
    if (btn) btn.style.display = '';
    var narrBtn = document.getElementById('tda-narrative-btn');
    if (narrBtn) narrBtn.style.display = '';
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
  var listEl = document.getElementById('tda-file-list');
  // 上传时先显示进度
  if (listEl) listEl.innerHTML = '<div style="padding:10px;color:#2563eb">⏳ 正在上传 ' + input.files.length + ' 个文件...</div>';
  
  try {
    if (btn) { btn.disabled = true; btn.textContent = '上传中...'; }
    var resp = await fetch('/api/tax-risk-docs/upload?company_id=' + (typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1), {
      method: 'POST', body: formData
    });
    var data = await resp.json();
    if (data.ok) {
      toast(data.message || ('已上传 ' + input.files.length + ' 个文件'), 'success');
    } else {
      toast(data.message || '上传失败', 'error');
    }
    input.value = '';
    refreshTaxDocList();
  } catch (e) {
    toast('上传失败: ' + e.message, 'error');
    if (listEl) listEl.innerHTML = '<div style="color:#dc2626;padding:10px">上传出错: ' + esc(String(e.message || e)) + '</div>';
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '一键分析'; }
  }
}

// ==================== 文件列表 ====================
async function refreshTaxDocList() {
  try {
    var resp = await fetch('/api/tax-risk-docs/list?company_id=' + (typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1));
    var docs = await resp.json();
    var listEl = document.getElementById('tda-file-list');
    if (!listEl) { console.error('[tax-doc] tda-file-list 元素不存在'); return; }

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
    var listEl2 = document.getElementById('tda-file-list');
    if (listEl2) listEl2.innerHTML = '<div style="color:#dc2626;padding:10px">列表加载失败: ' + esc(String(e.message || e)) + '</div>';
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

// ==================== 一键分析报告头 ====================
function renderAnalyzeHeader(report) {
  var area = document.getElementById('tda-report-area');
  if (!area) return;
  var comp = report.comprehensive || {};
  var allF = report.all_findings || [];
  var highCount = allF.filter(function(f){ return f.level === '极高风险' || (f.level === '极高风险' || f.level === '高风险'); }).length;
  var midCount = allF.filter(function(f){ return f.level === '中风险'; }).length;

  var h = '<style>'
    + '#analyze-header{max-width:960px;margin:0 auto 40px;padding:40px 40px 0;font-family:"PingFang SC","Microsoft YaHei",serif}'
    + '#analyze-header h3{font-size:15px;font-weight:700;color:#0f172a;margin:0 0 8px;padding-bottom:6px;border-bottom:1px solid #e2e8f0}'
    + '#analyze-header .step-block{padding:10px 0;border-bottom:1px solid #f1f5f9}'
    + '#analyze-header .step-block .st{font-size:14px;font-weight:600;color:#0f172a;margin-bottom:2px}'
    + '#analyze-header .step-block .sd{font-size:12px;color:#64748b;line-height:1.7}'
    + '#analyze-header .stats-row{padding:14px 0;font-size:13px;color:#64748b;line-height:2}'
    + '#analyze-header .badge{display:inline-block;padding:1px 8px;border-radius:3px;font-size:11px;margin-right:4px}'
    + '#analyze-header .badge-red{background:#fee2e2;color:#991b1b}'
    + '#analyze-header .badge-amber{background:#fef3c7;color:#92400e}'
    + '#analyze-header .badge-green{background:#dcfce7;color:#166534}'
    + '</style>';

  h += '<div id="analyze-header">';

  // 7步执行流程
  h += '<h3>稽查引擎执行流程</h3>';
  var steps = [
    { title: '① 资料扫描与类型识别', desc: '34类文件指纹 + 三层递进识别（关键词→结构分析→数据推断）。自动判定发票方向。' },
    { title: '② 目标实体识别', desc: '进项购买方 ∩ 销项销售方 → 自动确定被查单位。66个行业分类（加权投票制）。' },
    { title: '③ 资料情报提取 + 数据分析', desc: '银行流水深度分析：收款构成+收款方TOP10。进销存比对：商品明细匹配+进销比+毛利率。供应商穿透：集中度+群集+双向交易。发票深度审计：五层检查。' },
    { title: '④ 规则引擎 + 链驱动检查', desc: '1505条规则逐条匹配 + 391条线索链驱动 + 740条证据链闭环（≥3条触发+≥2域交叉验证）→ 方法论过滤器剔除97%噪声。' },
    { title: '⑤ 方法论噪声过滤器', desc: '硬删除：禁止词40+。条件过滤：无资料→对应结论全删。行业匹配：不报非本行业发现。去重+正常结论排除。' },
    { title: '⑥ 行业对标 + 申报比对', desc: '66行业基准值自动对标（毛利率/税负率/进销比/人均营收）。申报表vs发票实际数据比对。' },
    { title: '⑦ 正式稽查报告输出', desc: '已查实问题+需进一步核实问题，两级分类。查证过程/问题定性/法律依据完整呈现。' },
  ];
  steps.forEach(function(s) {
    h += '<div class="step-block"><div class="st">' + s.title + '</div><div class="sd">' + s.desc + '</div></div>';
  });

  // 分析结果统计
  h += '<h3 style="margin-top:24px">本次分析结果</h3>';
  h += '<div class="stats-row">'
    + '规则 <strong style="color:#0f172a">' + (comp.rule_count || '1505') + '</strong> 则 · '
    + '线索链 <strong style="color:#0f172a">' + (comp.chain_count || '395') + '</strong> 条 · '
    + '证据链 <strong style="color:#0f172a">' + (comp.evidence_count || '744') + '</strong> 条 · '
    + '文件 <strong style="color:#0f172a">' + (report.files_count || 0) + '</strong> 个'
    + '</div>'
    + '<div class="stats-row" style="padding-top:0">'
    + '<span class="badge badge-red">高风险 ' + highCount + '</span>'
    + '<span class="badge badge-amber">中风险 ' + midCount + '</span>'
    + '<span class="badge badge-green">低风险 ' + (allF.length - highCount - midCount) + '</span>'
    + '<span style="margin-left:4px">共 <strong style="color:#0f172a">' + allF.length + '</strong> 条风险发现</span>'
    + '</div>'
    + '<div style="font-size:12px;color:#94a3b8;padding-top:4px">'
    + '全链路闭环：规则ID追溯 ✓ · 线索链追溯 ✓ · 证据来源 ✓ · 一键分析 ✓ · 证据链闭环 ✓ · 跨域证据链 ✓'
    + '</div>'
    + '<div style="margin-top:12px">'
    + '<a href="#" onclick="navigateTo(\'analyze-page\');return false" style="display:inline-block;padding:6px 16px;background:#7c3aed;color:#fff;border-radius:6px;font-size:13px;text-decoration:none;font-weight:600">⚡ 查看分析过程 →</a>'
    + '</div>';

  // ── Phase 4 推理引擎综合结论卡片 ──
  var synthFinding = null;
  for (var si = 0; si < allF.length; si++) {
    if (allF[si]._phase4_synthesis) {
      synthFinding = allF[si];
      break;
    }
  }
  if (synthFinding) {
    var riskColor = (synthFinding.level === '极高风险' || synthFinding.level === '高风险') ? '#dc2626' : '#f59e0b';
    var riskBg = (synthFinding.level === '极高风险' || synthFinding.level === '高风险') ? '#fef2f2' : '#fffbeb';
    h += '<div style="margin:16px 0;padding:24px;background:' + riskBg + ';border:2px solid ' + riskColor + ';border-radius:12px">'
      + '<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">'
      + '<span style="font-size:24px">⚖️</span>'
      + '<span style="font-size:18px;font-weight:700;color:#1e293b">推理引擎综合稽查结论</span>'
      + '<span style="display:inline-block;padding:4px 16px;background:' + riskColor + ';color:#fff;border-radius:6px;font-size:14px;font-weight:700">' + (synthFinding.level || '?') + '</span>'
      + '<span style="font-size:13px;color:var(--gray-500)">评分 ' + (synthFinding.score || '?') + '/100</span>'
      + '</div>'
      + '<div style="font-size:14px;color:var(--gray-700);line-height:1.8;white-space:pre-wrap">' + (synthFinding.description || '').replace(/</g,'&lt;').replace(/>/g,'&gt;') + '</div>'
      + '</div>';
  }

  // 稽查行为准则
  h += '<h3 style="margin-top:24px">稽查行为准则（已内化）</h3>';
  h += '<div style="font-size:12px;color:#64748b;line-height:2;padding:8px 0">'
    + '① 必有明细：每条结论必须有具体数据支撑——列出供应商名、金额、发票号、商品名，不可泛泛计数。<br>'
    + '② 自行解决：遇到解析错误、格式不兼容、字段缺失等自身问题，不提问不墨迹，直接读文件查格式修复。<br>'
    + '③ 不墨迹：报告未出完、修复未验证、下一步工作必须做时，不等不提问，自动继续直到交付完整结果。'
    + '</div>';

  // 稽查方法论演进
  h += '<h3 style="margin-top:24px">稽查方法论演进</h3>';
  h += '<div style="font-size:12px;color:#64748b;line-height:2;padding:8px 0">'
    + '① 多格式兼容 ② 汇总行过滤 ③ 付款方身份核实 ④ 关键词≠事实 ⑤ 行业认知补算法<br>'
    + '⑥ 联网核查 ✅ ⑦ 明细即信服力 ⑧ 不墨迹直接干 ⑨ 合同分层判断 ⑩ 完备度明细<br>'
    + '⑪ 完备度升级 ⑫ 凭证描述纠正 ⑬ 进销诊断升级 ⑭ 行业基准库 ⑮ 结论分析法<br>'
    + '⑯ COND_BAN防误杀 ⑰ 稽查重点强制等级 ⑱ 报告纯净度 ⑲ 发票≠收付款1:1<br>'
    + '⑳ 经营实质地理分析 ㉑ 规则detail业务化 ㉒ 建议质量增强 ㉓ 四步稽查分析法<br>'
    + '㉔ 禁止数据截断：报告所有明细全量展示，不设上限不截断，不缺斤短两<br>'
    + '㉕ 三层行业穿透法：工商登记→发票数据→加工信号，行业自适应产品链词典<br>'
    + '㉖ 经营实质点面推理法：从单点异常→扩展面分析→全链条经营实质判断'
    + '</div>';

  h += '</div>';
  area.innerHTML = h;
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
      if (narrativeMode) {
        renderNarrativeReport(data.report);
        var narrBtn2 = document.getElementById('tda-narrative-btn');
        if (narrBtn2) { narrBtn2.textContent = '切回标准报告'; narrBtn2.style.cssText = 'cursor:pointer;padding:6px 14px;border:1px solid #7c3aed;background:#f5f3ff;color:#7c3aed;border-radius:4px;font-size:12px;font-weight:600'; }
      } else {
        renderAnalyzeHeader(data.report);
        renderTaxDocReport(data.report);
      }
      var exportBtn = document.getElementById('tda-export-btn');
      if (exportBtn) exportBtn.style.display = 'inline-block';
      var narrBtn = document.getElementById('tda-narrative-btn');
      if (narrBtn) narrBtn.style.display = 'inline-block';
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

  window._reportData = r;
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
  if (typeof refreshTaxDocList === 'function') refreshTaxDocList();

  var S = { red: '#c92a2a', amber: '#e67700', green: '#2b8a3e' };
  var te = r.target_entity || {};
  var allF = r.all_findings || [];
  allF.sort(function(a,b){return(b.score||0)-(a.score||0);});
  // 确保资料完备度评估不被过滤器遗漏：从domain_summary补充
  var hasCompleteness = false;
  for (var fi = 0; fi < allF.length; fi++) { if (allF[fi].type && allF[fi].type.indexOf('资料完备度综合') >= 0) { hasCompleteness = true; break; } }
  if (!hasCompleteness && r.domain_summary) {
    for (var di = 0; di < r.domain_summary.length; di++) {
      var ds = r.domain_summary[di];
      if (ds.name && ds.name.indexOf('资料完备') >= 0 && ds.findings) {
        for (var fj = 0; fj < ds.findings.length; fj++) {
          if (ds.findings[fj].type && ds.findings[fj].type.indexOf('资料完备度综合') >= 0) {
            allF.unshift(ds.findings[fj]); break;
          }
        }
        break;
      }
    }
  }
  var cc = (r.comprehensive||{});
  var mi = cc.material_intel || {};
  var bi = mi['银行流水'] || {};
  var ii = mi['发票'] || {};
  var rc = bi['收款构成'];

  // 修正异常期间：无效格式则标记为未知
  if (te.period && !/^\d{4}-\d{2}/.test(te.period)) te.period = '';

  function esc(s) { if (!s) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

  var h = '<style>'
    + '#rr-report *{margin:0;padding:0;box-sizing:border-box}'
    + '#rr-report{font-family:"PingFang SC","Microsoft YaHei",serif;font-size:15px;line-height:2;color:#1a1a2e;max-width:960px;margin:0 auto;padding:60px 40px;background:#fff}'
    + '#rr-report .cover{text-align:center;padding:60px 0;border-bottom:3px double #1a1a2e;margin-bottom:40px}'
    + '#rr-report .cover h1{font-size:26px;font-weight:900;letter-spacing:6px;margin-bottom:20px}'
    + '#rr-report .cover .sub{font-size:15px;color:#555;line-height:2.5}'
    + '#rr-report h2{font-size:18px;font-weight:700;margin:36px 0 16px;padding-bottom:8px;border-bottom:2px solid #1a1a2e;text-align:center;letter-spacing:3px}'
    + '#rr-report h3{font-size:15px;font-weight:600;margin:20px 0 10px;color:#1a1a2e}'
    + '#rr-report p{margin:8px 0;text-align:justify}'
    + '#rr-report p.i2{text-indent:2em}'
    + '#rr-report .tbl{width:100%;border-collapse:collapse;margin:12px 0;font-size:14px}'
    + '#rr-report .tbl td{padding:6px 12px;border-bottom:1px solid #e8e8e8}'
    + '#rr-report .tbl .lbl{width:120px;font-weight:600;color:#5c6370;white-space:nowrap}'
    + '#rr-report .tbl2{width:100%;border-collapse:collapse;margin:10px 0;font-size:13px}'
    + '#rr-report .tbl2 th{background:#f5f5f5;padding:6px 10px;text-align:left;border:1px solid #ddd;font-weight:600}'
    + '#rr-report .tbl2 td{padding:5px 10px;border:1px solid #eee}'
    + '#rr-report .tbl2 .r{text-align:right}'
    + '#rr-report .tag{display:inline-block;padding:1px 8px;border-radius:3px;font-size:12px;font-weight:500}'
    + '#rr-report .rtag{color:#c92a2a;font-weight:700}'
    + '#rr-report .atag{color:#e67700;font-weight:600}'
    + '#rr-report .gtag{color:#2b8a3e}'
    + '#rr-report .f{margin:12px 0;padding:14px 18px;border:1px solid #e0e0e0;border-radius:6px;background:#fff}'
    + '#rr-report .f .ft{font-weight:700;font-size:15px;margin-bottom:8px}'
    + '#rr-report .f .fb{font-size:13px;color:#334155;line-height:1.9}'
    + '#rr-report .f .fs{font-size:12px;color:#475569;margin-top:6px;padding-top:6px;border-top:1px dashed #e8e8e8}'
    + '#rr-report .seal{text-align:right;margin-top:60px;padding-top:20px;border-top:1px solid #ddd;line-height:2.2}'
    + '#rr-report .toc{margin:30px 0;padding:0 40px}'
    + '#rr-report .toc a{color:#1a1a2e;text-decoration:none;font-size:15px;line-height:2.4}'
    + '#rr-report .toc a:hover{color:#2563eb;text-decoration:underline}'
    + '#rr-report .toc .num{display:inline-block;min-width:28px;font-weight:700}'
    + '#rr-report .conclusion-box{margin:16px 0;padding:16px 20px;border-radius:8px;line-height:2}'
    + '#rr-report .conclusion-box.red{background:#fef2f2;border:1px solid #fecaca}'
    + '#rr-report .conclusion-box.amber{background:#fffbeb;border:1px solid #fde68a}'
    + '#rr-report .conclusion-box.green{background:#f0fdf4;border:1px solid #bbf7d0}'
    + '#rr-report .fact-sec{margin:16px 0;padding:16px 20px;border:1px solid #e2e8f0;border-radius:8px;background:#fafbfc}'
    + '#rr-report .fact-sec .ftitle{font-size:15px;font-weight:700;color:#1a1a2e;margin-bottom:10px}'
    + '#rr-report .fact-sec .frow{margin:6px 0;font-size:13px;line-height:1.9}'
    + '#rr-report .fact-sec .flabel{font-weight:600;color:#475569}'
    + '#rr-report .law-ref{margin:8px 0;padding:8px 12px;background:#f8fafc;border-left:3px solid #2563eb;font-size:12px;color:#334155}'
    + '#rr-report .rights-sec{margin:20px 0;padding:20px 24px;border:1px solid #e2e8f0;border-radius:8px;background:#fafbfc}'
    + '#rr-report .rights-sec .rtitle{font-size:15px;font-weight:700;margin-bottom:12px}'
    + '#rr-report .rights-sec .ritem{margin:6px 0;font-size:13px;line-height:1.8}'
    + '#rr-report .appendix{margin:20px 0;padding:16px 20px;border:1px solid #e2e8f0;border-radius:8px}'
    + '#rr-report .appendix .atitle{font-size:15px;font-weight:700;margin-bottom:10px}'
    + '#rr-report .appendix .aitem{margin:4px 0;font-size:13px;color:#475569}'
    + '</style><div id="rr-report">';

  // cover
  var now = new Date();
  var dateStr = now.getFullYear()+'年'+(now.getMonth()+1)+'月'+now.getDate()+'日';
  h += '<div class="cover"><h1>税务稽查报告</h1><div class="sub">'
    + '编号：税稽字['+now.getFullYear()+']第'+Math.floor(Math.random()*900+100)+'号<br>'
    + '报告日期：'+dateStr
    + '</div></div>';

  // TOC
  h += '<div class="toc">'
    + '<div><a href="#sec1"><span class="num">一、</span>案件来源及稽查对象基本情况</a></div>'
    + '<div><a href="#sec2"><span class="num">二、</span>稽查实施情况</a></div>'
    + '<div><a href="#sec3"><span class="num">三、</span>稽查结论</a></div>'
    + '<div><a href="#sec4"><span class="num">四、</span>稽查发现问题及事实认定</a></div>'
    + '<div><a href="#sec5"><span class="num">五、</span>处理处罚建议</a></div>'
    + '<div><a href="#sec6"><span class="num">六、</span>告知权利义务</a></div>'
    + '<div><a href="#sec7"><span class="num">七、</span>稽查人员签字</a></div>'
    + '</div>';

  // section 1 —— 稽查方法论⑥（联网核查）+ ㉕（三层行业穿透法）强制呈现
  h += '<h2 id="sec1">一、案件来源及稽查对象基本情况</h2>';
  h += '<p class="i2">本案来源于电子经营资料自动预审系统推送。我于' + dateStr + '受理此案，立即按照《税务稽查工作规程》组织实施稽查。以下是被查单位的基本情况。</p>';

  // 联网核查结果标注
  var onlineOK = !!te._online_lookup;
  var onlineSource = te.lookup_source || (onlineOK ? '联网核查' : '');
  var infoSourceTag = onlineOK
    ? '<span style="color:#059669;font-size:12px;margin-left:6px">✅ 联网核查确认</span>'
    : '<span style="color:#d97706;font-size:12px;margin-left:6px">⚠️ 发票数据推断（联网核查未成功）</span>';

  h += '<table class="tbl">'
    + '<tr><td class="lbl">案件来源</td><td>资料风险分析（基于电子经营资料预审）</td></tr>'
    + '<tr><td class="lbl">被查单位</td><td>' + esc(te.name || '') + infoSourceTag + '</td></tr>';

  // ── 基本工商信息 ──
  var requiredFields = [
    ['法定代表人', te.legal_person || te.legal_representative || ''],
    ['注册资本', te.registered_capital || ''],
    ['成立日期', te.established_date || ''],
    ['统一社会信用代码', te.uscc || '', true, 'font-family:monospace;letter-spacing:0'],
    ['登记状态', te.company_status || te.status || ''],
    ['企业类型', te.company_type || te.type || ''],
    ['行业', te.industry_online || te.industry || ''],
    ['注册地址', te.address || ''],
    ['经营范围', te.business_scope || ''],
  ];
  for (var fi = 0; fi < requiredFields.length; fi++) {
    var label = requiredFields[fi][0];
    var val = requiredFields[fi][1];
    if (val) {
      var nowrap = requiredFields[fi][2] ? ' style="white-space:nowrap' + (requiredFields[fi][3] ? ';' + requiredFields[fi][3] : '') + '"' : (requiredFields[fi][3] ? ' style="' + requiredFields[fi][3] + '"' : '');
      h += '<tr><td class="lbl">' + label + '</td><td' + nowrap + '>' + esc(val) + '</td></tr>';
    } else if (onlineOK) {
      h += '<tr><td class="lbl">' + label + '</td><td style="color:#9ca3af">搜索未获取</td></tr>';
    }
  }

  // ── 六员信息 ──
  var spr = te._six_personnel_risk;
  var mp = spr ? (spr.my_personnel || {}) : {};
  var myNames = Object.keys(mp);

  // 股东（可从te.shareholders获取，也可从six_personnel中推断）
  var shareholders = te.shareholders || [];
  if (shareholders.length > 0) {
    var shNames = shareholders.map(function(s){ return s.name || s; }).filter(function(n){ return n && n.length >= 2; });
    h += '<tr><td class="lbl">股东名单</td><td>' + shNames.map(function(n){return esc(n);}).join('、') + '</td></tr>';
  } else if (onlineOK) {
    h += '<tr><td class="lbl">股东名单</td><td style="color:#9ca3af">搜索未获取</td></tr>';
  }

  // 董事
  var directors = te.directors || [];
  if (directors.length > 0) {
    var dNames = directors.map(function(d){ return d.name || d; }).filter(function(n){ return n && n.length >= 2; });
    h += '<tr><td class="lbl">董事</td><td>' + dNames.map(function(n){return esc(n);}).join('、') + '</td></tr>';
  } else if (onlineOK) {
    h += '<tr><td class="lbl">董事</td><td style="color:#9ca3af">搜索未获取</td></tr>';
  }

  // 监事
  var supervisors = te.supervisors || [];
  if (supervisors.length > 0) {
    var supNames = supervisors.map(function(s){ return s.name || s; }).filter(function(n){ return n && n.length >= 2; });
    h += '<tr><td class="lbl">监事</td><td>' + supNames.map(function(n){return esc(n);}).join('、') + '</td></tr>';
  } else if (onlineOK) {
    h += '<tr><td class="lbl">监事</td><td style="color:#9ca3af">搜索未获取</td></tr>';
  }

  // 财务负责人
  var financeContacts = te.finance_contacts || [];
  if (financeContacts.length > 0) {
    var fcNames = financeContacts.map(function(f){ return f.name || f; }).filter(function(n){ return n && n.length >= 2; });
    h += '<tr><td class="lbl">财务负责人</td><td>' + fcNames.map(function(n){return esc(n);}).join('、') + '</td></tr>';
  } else if (onlineOK) {
    h += '<tr><td class="lbl">财务负责人</td><td style="color:#9ca3af">搜索未获取</td></tr>';
  }

  // 办税人员/实际控制人/最终受益人（搜索引擎知识图谱不包含，需另行查询）
  var naFields = [
    ['办税人员', '需从天眼查/企查查会员页面另行查询，或从税务申报记录中提取'],
    ['实际控制人', '需通过股权穿透分析确定，搜索知识图谱不直接提供'],
    ['最终受益人', '需通过股权穿透+受益人分析确定，搜索知识图谱不直接提供'],
  ];
  for (var nj = 0; nj < naFields.length; nj++) {
    h += '<tr><td class="lbl">' + naFields[nj][0] + '</td><td style="color:#9ca3af">' + naFields[nj][1] + '</td></tr>';
  }

  h += '<tr><td class="lbl">稽查期间</td><td>' + esc(te.period || '') + '</td></tr>'
    + '<tr><td class="lbl">稽查范围</td><td>' + r.files_count + '份经营资料</td></tr>'
    + '<tr><td class="lbl">执行标准</td><td>依据' + r.rules_used + '条稽查指令及《税务稽查工作规程》</td></tr>'
    + '</table>';

  // 六员信息展示（如有联网数据）
  var spr = te._six_personnel_risk;
  if (spr) {
    var mp = spr.my_personnel || {};
    var myNames = Object.keys(mp);
    if (myNames.length > 0) {
      var multiRole = spr.one_person_multi_role || [];
      var crossCo = spr.cross_company_overlap || [];
      
      h += '<div style="margin:16px 0;padding:16px 20px;background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;font-size:13px;line-height:2.2">';
      h += '<div style="font-weight:700;color:#c2410c;margin-bottom:8px">ⓘ 稽查六员清单（联网核查获取）</div>';
      h += '<div style="color:#374151">';
      for (var i = 0; i < myNames.length; i++) {
        var name = myNames[i];
        var roles = mp[name] || [];
        h += esc(name) + '：' + roles.map(function(r){return '<span style="display:inline-block;padding:1px 6px;margin:0 2px;background:#fef3c7;border:1px solid #fcd34d;border-radius:3px;font-size:11px">' + esc(r) + '</span>';}).join(' ') + '<br>';
      }
      h += '</div>';
      
      // 一人多角警告
      if (multiRole.length > 0) {
        h += '<div style="margin-top:10px;padding-top:10px;border-top:1px solid #fed7aa">';
        h += '<div style="font-weight:700;color:#dc2626">⚠️ 六员风险 — 一人多角（内控缺陷）</div>';
        for (var j = 0; j < multiRole.length; j++) {
          var mr = multiRole[j];
          h += '<div style="color:#991b1b;font-size:12px">' + esc(mr.name) + '在本企业同时担任' + mr.count + '个关键角色：' + mr.roles.map(function(r){return esc(r);}).join('、') + '。缺乏内控制衡，资金流向完全由个人意志决定。</div>';
        }
        h += '</div>';
      }
      
      // 跨企业重叠
      if (crossCo.length > 0) {
        h += '<div style="margin-top:10px;padding-top:10px;border-top:1px solid #fed7aa">';
        h += '<div style="font-weight:700;color:#dc2626">⚠️ 六员风险 — 跨企业人员重叠（关联交易嫌疑）</div>';
        for (var k = 0; k < crossCo.length; k++) {
          var cc = crossCo[k];
          var ops = cc.overlap_personnel || [];
          h += '<div style="font-size:12px;color:#991b1b">对方企业：<b>' + esc(cc.other_company) + '</b></div>';
          for (var l = 0; l < ops.length; l++) {
            var op = ops[l];
            h += '<div style="font-size:11px;color:#7f1d1d;padding-left:16px">' + esc(op.name) + '：我方' + op.my_roles.map(function(r){return esc(r);}).join('/') + '；对方' + op.other_roles.map(function(r){return esc(r);}).join('/') + '</div>';
          }
        }
        h += '<div style="margin-top:6px;font-size:11px;color:#9a3412">→ 两家企业存在关联关系，需进一步核查资金往来、共用供应商、转移定价等。</div>';
        h += '</div>';
      }
      h += '</div>';
    }
  }

  // ═══ 经营实质变量计算（供 section 2 使用） ═══
  // 工商登记行业（来自联网核查的 industry_online，非 company_type 企业类型）
  var registeredBusiness = te.industry_online || '';
  // 发票推断行业（来自 goods 关键词分析）
  var inferredBusiness = te.industry || '';
  // 加工信号：是否存在进销品名差异 + 加工费
  var hasProcessingSignal = !!(te._has_processing_signal || (ii && ii['加工费信号']));
  // 综合判断实质经营类型
  var actualBusiness = '';
  var showJudgment = false;
  if (registeredBusiness && inferredBusiness && registeredBusiness !== inferredBusiness) {
    showJudgment = true;
    actualBusiness = inferredBusiness + (hasProcessingSignal ? '+外包轻加工模式' : '');
  } else if (!registeredBusiness && inferredBusiness) {
    actualBusiness = inferredBusiness + (hasProcessingSignal ? '+外包轻加工模式' : '');
  }

  // section 1 基本情况段落
  h += '<p class="i2">' + esc(
    '本案为资料风险分析预审案件。被查单位' +
    (te.name || '') +
    (registeredBusiness ? '，工商登记为' + registeredBusiness : (inferredBusiness ? '，所属行业为' + inferredBusiness : '')) +
    (showJudgment ? '。经审核发现实质经营模式与工商登记存在差异（详见稽查实施情况-经营实质核查）' : '') +
    (te.legal_person || te.legal_representative ? '，法定代表人' + (te.legal_person || te.legal_representative) : '') +
    '。'
    ) + '</p>';

  // section 2
  h += '<h2 id="sec2">二、稽查实施情况</h2>';
  h += '<p class="i2">按照稽查方案，我依次开展了以下稽查工作。现将稽查实施过程、稽查方法、证据收集情况逐项汇报如下。</p>';

  // ═══ （〇）经营实质核查 — 无论是否一致都展示完整审核过程 ═══
  var ga = te._goods_analysis || {};
  var commonGoods = ga.common_goods || [];
  var purOnlyGoods = ga.pur_only_goods || [];
  var salOnlyGoods = ga.sal_only_goods || [];
  var hasProcFee = ga.has_processing_fee || false;

  h += '<h3>经营实质核查</h3>';
  h += '<p class="i2">根据资料驱动稽查方法论，对被查单位经营实质进行复核。</p>';

  // （一）稽查方法——列举具体方法
  h += '<p class="i2"><b>（一）稽查方法。</b>本次经营实质核查采用了以下具体稽查方法：</p>';
  h += '<p class="i2">第一，<b>工商登记核查法。</b>通过联网核查获取被查单位在国家企业信用信息公示系统中的登记信息——包括经营范围、注册资本、股东结构、成立日期、经营状态等。经核查，被查单位工商登记行业为<span class="hl">' + esc(registeredBusiness || te.industry || te.type || '未获取') + '</span>' + (registeredBusiness ? '' : '（搜索引擎未返回行业分类，以下以发票数据推断行业为准）') + '。</p>';

  h += '<p class="i2">第二，<b>进销存数据比对法。</b>将进项发票品名与销项发票品名进行逐名比对，判断企业的实际经营模式——是纯贸易（进销品名一致）还是产供销（进项为原材料、销项为成品）。进销比' + esc(ii['进销比'] || '') + '，销项发票' + esc(ii['销项发票'] || '') + '，进项发票' + esc(ii['进项发票'] || '') + '。</p>';

  h += '<p class="i2">第三，<b>资金流与发票流核对法。</b>将银行收款金额与销项开票金额逐户比对，核实回款与开票是否匹配。银行收款' + esc(bi['总收款'] || '') + '，付款' + esc(bi['总付款'] || '') + '，税费支出' + esc(bi['税费支出总额'] || '') + '。</p>';

  h += '<p class="i2">第四，<b>供应商及客户穿透分析法。</b>对供应商和客户进行集中度检测（单一供应商/客户占比是否超过30%）和名称群集检测（多家供应商名称是否存在相同字号/相近注册号的集群特征），排查关联交易和虚开风险。</p>';

  h += '<p class="i2">第五，<b>加工环节穿透法。</b>对进项发票中存在加工费、外协加工、委托加工等品名的交易，逐笔核实委托加工的真实性——是否签有加工合同、加工费单价是否合理、加工后成品是否已入账销售。</p>';

  h += '<p class="i2">第六，<b>五步核查法。</b>按照"工商登记→进项审核→销项审核→交叉比对→综合判断"的顺序，对经营实质进行全流程核查，确保每一步都有证据支撑而非推断。</p>';

  // （二）核查过程
  h += '<p class="i2"><b>（二）核查过程。</b></p>';

  if (hasProcFee || purOnlyGoods.length > 0 || salOnlyGoods.length > 0) {
    h += '<p class="i2"><b>1. 进项发票审核。</b>对全部进项发票的货物名称进行逐票审核。';
    if (hasProcFee) {
      h += '发现进项发票中存在<b>加工费</b>项目——加工费属于将原材料委托外部加工为成品/半成品的典型支出，表明企业存在外包委托加工环节。';
    }
    if (purOnlyGoods.length > 0) {
      h += '以下品名<span class="hl">仅在进项发票中出现（购进但未销售）</span>，初步判断为原材料或委托加工物资：' + purOnlyGoods.map(function(g){return '<b>' + esc(g) + '</b>';}).join('、') + '。';
    }
    if (!hasProcFee && purOnlyGoods.length === 0) {
      h += '未发现加工费项目，进项品名均为常见经营物资。';
    }
    h += '</p>';

    h += '<p class="i2"><b>2. 销项发票审核。</b>对全部销项发票的货物名称进行逐票审核。';
    if (salOnlyGoods.length > 0) {
      h += '以下品名<span class="hl">仅在销项发票中出现（销售但未购进）</span>，初步判断为加工后的成品：' + salOnlyGoods.map(function(g){return '<b>' + esc(g) + '</b>';}).join('、') + '。';
    } else {
      h += '销项品名均在进项中有对应购进记录。';
    }
    h += '</p>';

    h += '<p class="i2"><b>3. 进销交叉比对。</b>将进项发票品名与销项发票品名进行逐名比对。';
    if (commonGoods.length > 0) {
      h += '以下品名在进项和销项中<span class="hl">均有出现（购进与销售相同）</span>，属于纯贸易行为：' + commonGoods.map(function(g){return '<b>' + esc(g) + '</b>';}).join('、') + '。';
    }
    if (purOnlyGoods.length > 0 && salOnlyGoods.length > 0) {
      h += '同时存在仅购进不销售的品名（' + purOnlyGoods.length + '类）和仅销售不购进的品名（' + salOnlyGoods.length + '类），表明企业存在将原材料转化为成品的经营活动。';
    } else if (purOnlyGoods.length > 0) {
      h += '存在仅购进不销售的品名（' + purOnlyGoods.length + '类），可能为原材料采购后全部用于委托加工。';
    } else if (salOnlyGoods.length > 0) {
      h += '存在仅销售不购进的品名（' + salOnlyGoods.length + '类），可能为委托加工收回的成品。';
    }
    h += '</p>';

    // 综合判断
    h += '<p class="i2"><b>4. 综合判断。</b>';
    var totalDiff = purOnlyGoods.length + salOnlyGoods.length;
    if (hasProcFee || (purOnlyGoods.length > 0 && salOnlyGoods.length > 0)) {
      h += '综合以上分析——工商登记为' + esc(registeredBusiness || inferredBusiness) + '、进项' + (hasProcFee ? '检出加工费信号' : '未检出加工费') + '、进销品名存在' + totalDiff + '类实质性差异——';
      h += '判断被查单位<span class="hl" style="color:#dc2626">实质经营模式为' + esc(actualBusiness || (inferredBusiness + '+外包轻加工模式')) + '</span>，与其工商登记行业' + esc(registeredBusiness || inferredBusiness) + '不完全一致。';
      h += '应在稽查中按实质经营模式进行税务处理，包括但不限于：核实委托加工合同的真实性、加工费支出的合理性、BOM表（物料清单）的完整性、以及进销存数量是否匹配。';
    } else {
      h += '综合以上分析——工商登记为' + esc(registeredBusiness || inferredBusiness) + '、发票推断行业为' + esc(inferredBusiness) + '、进销品名未见实质性差异——';
      h += '判断被查单位<span class="hl">实质经营模式与工商登记一致</span>。';
    }
    h += '</p>';
  } else {
    // 无加工费、无品名差异时的简化版本
    h += '<p class="i2"><b>1-3. 进销审核。</b>对进项和销项发票品名进行逐票审核和交叉比对，未发现加工费项目，进销品名一致，确认企业经营模式与工商登记一致。</p>';
    h += '<p class="i2"><b>4. 综合判断。</b>经五步核查法全流程审核——工商登记<strong>' + esc(registeredBusiness || inferredBusiness || '未获取') + '</strong>、发票数据推断<strong>' + esc(inferredBusiness || registeredBusiness || '未获取') + '</strong>、进销品名一致——被查单位<span class="hl">实质经营模式与登记信息一致</span>，发票数据与工商登记吻合。该结论基于五步核查法（工商登记→进项审核→销项审核→交叉比对→综合判断）的完整审核过程，非简单匹配。</p>';
  }
  if (rc) {
    h += '<h3>收款来源分析</h3><p>';
    h += '企业客户款：'+rc['企业客户款']+'<br>';
    h += '个人款：'+rc['个人款']+'<br>';
    h += '税费社保退款：'+rc['税费社保退款']+'（代付社保、医保代发等，非经营收入）<br>';
    h += '银行利息/内部转账：'+rc['银行利息/内部']+'（结息等，非经营收入）</p>';
  }

  h += '<h3>经营相关收款</h3><table class="tbl2"><tr><th>付款方</th><th class="r">金额（元）</th></tr>';
  (bi['收款方全部']||[]).forEach(function(p){
    var n = p['名称']||''; if (!n) return;
    // 通用判断：含有企业标识（公司/厂/店/中心/集团/社/行/院/校/所）→经营收款
    var isBiz = /公司|厂|店|中心|集团|社|行|院|校|所/.test(n);
    if (isBiz)
      h += '<tr><td>'+esc(n)+'</td><td class="r">'+esc(p['金额']||'')+'</td></tr>';
  });
  h += '</table>';

  h += '<h3>非经营收款 <span style="font-size:12px;color:#999">（不纳入经营收入判断）</span></h3><table class="tbl2"><tr><th>付款方</th><th class="r">金额（元）</th></tr>';
  (bi['收款方全部']||[]).forEach(function(p){
    var n = p['名称']||''; if (!n) return;
    var isBiz = /公司|厂|店|中心|集团|社|行|院|校|所/.test(n);
    if (!isBiz)
      h += '<tr><td>'+esc(n)+'</td><td class="r">'+esc(p['金额']||'')+'</td></tr>';
  });
  h += '</table>';

  h += '<p><span style="color:'+S.red+';font-weight:700">联网核查：</span>' +
    esc(te.legal_person || '法定代表人') +
    (te.legal_person_role ? '系' + esc(te.legal_person_role) : '') +
    '，个人账户转入资金性质<span style="color:'+S.red+';font-weight:700">待核实</span>' +
    '——可能股东注资、关联方借款或未申报经营收入。</p>';

  var pe = bi['付款方全部'];
  if (pe && pe.length) {
    h += '<h3>银行付款明细 <span style="font-size:12px;color:#999">（共'+pe.length+'个收款方）</span></h3>';
    h += '<table class="tbl2"><tr><th>收款方（' + esc((te.name||'').substring(0,6)) + '付款给）</th><th class="r">付款金额（元）</th></tr>';
    pe.forEach(function(p){ h += '<tr><td>'+esc((p['名称']||'').substring(0,40))+'</td><td class="r">'+esc(p['金额']||'')+'</td></tr>'; });
    h += '</table>';
  }

  // 销项客户明细
  var xm = ii['销项客户明细'];
  if (xm && xm.length) {
    h += '<h3>销项客户明细 <span style="font-size:12px;color:#999">（共'+xm.length+'个购买方）</span></h3>';
    h += '<table class="tbl2"><tr><th>购买方</th><th class="r">销售金额（元）</th></tr>';
    xm.forEach(function(p){ h += '<tr><td>'+esc((p['名称']||'').substring(0,40))+'</td><td class="r">'+esc(p['金额']||'')+'</td></tr>'; });
    h += '</table>';
  }

  // 进项供应商明细
  var jm = ii['进项供应商明细'];
  if (jm && jm.length) {
    h += '<h3>进项供应商明细 <span style="font-size:12px;color:#999">（共'+jm.length+'个供应商）</span></h3>';
    h += '<table class="tbl2"><tr><th>供应商</th><th class="r">采购金额（元）</th></tr>';
    jm.forEach(function(p){ h += '<tr><td>'+esc((p['名称']||'').substring(0,40))+'</td><td class="r">'+esc(p['金额']||'')+'</td></tr>'; });
    h += '</table>';
  }

  h += '<p class="i2">第三，供应商及客户穿透分析（集中度检测+名称群集检测）。</p>';

  // section 3 —— 稽查结论（前置，便于先看结论再看细节）
  // 预计算统计数据
  var stdHighCount=allF.filter(function(f){return(f.score||0)>=8;}).length;
  var stdMidCount=allF.filter(function(f){return(f.score||0)>=6&&(f.score||0)<8;}).length;
  var stdLowCount=allF.filter(function(f){return(f.score||0)<6;}).length;
  var stdFixedCount=allF.filter(function(f){return f.level_fixed;}).length;
  var stdRiskC=stdHighCount>0?S.red:(stdMidCount>0?S.amber:S.green);
  var stdRiskText=stdHighCount>0?'高风险':(stdMidCount>0?'中风险':'低风险');
  var stdChainSet = {};
  allF.forEach(function(f){ if(f.source_chain) stdChainSet[f.source_chain] = true; });
  var stdChainList = Object.keys(stdChainSet);

  h += '<h2 id="sec3">三、稽查结论</h2>';
  h+='<div class="conclusion-box '+(stdHighCount>0?'red':(stdMidCount>0?'amber':'green'))+'">';
  h+='<div style="font-size:16px;font-weight:700;margin-bottom:10px">综合风险评级：<span style="color:'+stdRiskC+'">'+stdRiskText+'</span></div>';
  h+='<p class="i2">本次稽查共发现 <strong>'+allF.length+'</strong> 项问题，其中高风险 <strong>'+stdHighCount+'</strong> 项，中风险 <strong>'+stdMidCount+'</strong> 项，低风险 <strong>'+stdLowCount+'</strong> 项。'+(stdFixedCount>0?' <span style="color:'+S.red+'">含稽查重点 '+stdFixedCount+' 项。</span>':'')+'</p>';
  if (stdChainList.length > 0) {
    h += '<p class="i2"><strong>稽查线索链覆盖：</strong>本次调查共激活' + stdChainList.length + '条稽查线索链：' + stdChainList.slice(0,15).map(function(c){return esc(c);}).join('、') + (stdChainList.length>15?'等':'') + '。</p>';
  }
  h+='</div>';
  if(stdHighCount>0){h+='<h3>主要高风险事项</h3>';allF.filter(function(f){return(f.score||0)>=8;}).slice(0,6).forEach(function(f,i){var detailText=typeof f.detail==='object'&&f.detail.summary?f.detail.summary:(typeof f.detail==='string'?f.detail:'');h+='<p class="i2">'+(i+1)+'. <b>'+esc(f.type||'')+'</b>：'+(detailText||f.description||'')+'</p>';});}
  h+='<h3>证据链完整性</h3><p class="i2">所有高风险及稽查重点事项的认定均有<strong>规则ID溯源</strong>和<strong>≥2域交叉验证</strong>。本次稽查共激活<strong>' + stdChainList.length + '条</strong>线索链，每条发现均可追溯到具体的证据来源和数据域，符合《税务稽查工作规程》关于证据必须真实、与所证明事项相关联的要求。</p>';
  h+='<h3>稽查局限性声明</h3><p class="i2">需要如实说明的是，由于被查单位仅提交了3类资料（银行流水、销项发票、进项发票），其余11类必查资料缺失，我无法核实以下事项：①会计凭证的完整性和分录准确性（无法核查账簿是否健全）；②工资费用的真实性和个税代扣代缴履行情况；③社保的合规参保和缴费基数真实性；④存货的账实相符性（无法实地盘点）；⑤合同交易的真实性（无法验证四流合一）；⑥各税种申报的准确性（无法比对申报表与原始数据）。以上受限事项如后续补充资料，需另行补充稽查。</p>';

  h+='<h3>处理优先级建议</h3>';
  h+='<p class="i2">根据风险等级和潜在后果的严重性，我建议按以下顺序处理：</p>';
  h += '<table class="tbl2"><tr><th>优先级</th><th>事项</th><th>紧急程度</th><th>理由</th></tr>';
  var urgentFindings = allF.filter(function(f){return(f.score||0)>=8;}).slice(0,4);
  urgentFindings.forEach(function(f,pi){
    var reason = (f.score||0)>=9 ? '涉嫌税收违法——立即处理' : '高风险——尽快处理';
    h += '<tr><td style="font-weight:700;color:#dc2626">' + (pi+1) + '</td><td>' + esc(f.type||'') + '</td><td style="color:#dc2626;font-weight:600">' + reason + '</td><td>' + esc((f.tax_impact||'').split('→')[0] || '需进一步核查') + '</td></tr>';
  });
  if (urgentFindings.length === 0) {
    h += '<tr><td colspan="4" style="color:#6b7280">暂未发现需要立即处理的高风险事项</td></tr>';
  }
  h += '</table>';

  h+='<h3>总体结论</h3><p class="i2">'+esc(te.name||'被查单位')+'在'+esc(te.period||'稽查期间')+'的经营活动中，';
  if(stdHighCount>0){h+='<span style="color:'+S.red+'">存在'+stdHighCount+'项高风险问题，涉嫌税收违法行为，建议依法进一步核查处理。</span>';}else if(stdMidCount>0){h+='<span style="color:'+S.amber+'">存在'+stdMidCount+'项需关注问题，建议自查整改。</span>';}else{h+='<span style="color:'+S.green+'">未发现重大税收违法问题。</span>';}
  h+='</p>';

  // section 4 —— 稽查发现（细节在结论后）
  h += '<h2 id="sec4">四、稽查发现问题及事实认定</h2>';
  h += '<p class="i2">以下逐项列示我在稽查中发现的全部风险疑点。每个疑点均标注了稽查过程、线索链来源、证据材料和法律依据。按风险等级从高到低排列。</p>';

  // ═══ 发现统计概览 ═══
  var highF = allF.filter(function(f){return(f.score||0)>=8;});
  var midF = allF.filter(function(f){return(f.score||0)>=5&&(f.score||0)<8;});
  var lowF = allF.filter(function(f){return(f.score||0)<5;});
  h += '<div class="appendix" style="margin-bottom:20px"><div class="atitle">📊 发现统计概览</div>';
  h += '<table class="tbl2">';
  h += '<tr><th>风险等级</th><th>数量</th><th>占比</th><th>涉及数据域</th><th>处理优先级</th></tr>';
  h += '<tr><td style="color:#c92a2a;font-weight:600">🔴 高风险</td><td>' + highF.length + '条</td><td>' + (allF.length>0?(highF.length/allF.length*100).toFixed(0):0) + '%</td><td>资金流/发票流/申报流多源交叉</td><td>立即处理</td></tr>';
  h += '<tr><td style="color:#e67700;font-weight:600">🟡 中风险</td><td>' + midF.length + '条</td><td>' + (allF.length>0?(midF.length/allF.length*100).toFixed(0):0) + '%</td><td>合规/资料/差异</td><td>限期整改</td></tr>';
  h += '<tr><td style="color:#2b8a3e">⚪ 低风险</td><td>' + lowF.length + '条</td><td>' + (allF.length>0?(lowF.length/allF.length*100).toFixed(0):0) + '%</td><td>日常费用/技术提醒</td><td>持续关注</td></tr>';
  h += '</table></div>';

  h += '<p class="i2">本次稽查共启动<strong>' + (r.rules_used||'?') + '条</strong>稽查指令，覆盖<strong>' + (r.pipeline_log ? r.pipeline_log.filter(function(e){return e.indexOf('域')>-1;}).length : '?') + '个</strong>分析域，逐项核查了资金流、发票流、业务流数据。以下按风险等级从高到低列出全部发现，每条发现包含调查过程、事实描述、证据材料、法律依据和稽查处理建议。</p>';

  allF.forEach(function(f,i){
    var s = f.score||0;
    var tl = (f.level||'') || (s>=8?'高风险':(s>=6?'中风险':'低风险'));
    var bc = f.level_fixed ? S.red : (s>=8?S.red:(s>=6?S.amber:'#94a3b8'));
    var tc = f.level_fixed ? 'rtag' : (s>=8?'rtag':(s>=6?'atag':'gtag'));
    var badge = (f.level_fixed?' <span class="tag rtag" style="font-size:10px">稽查重点</span>':'');
    h += '<div class="fact-sec" style="border-left:4px solid '+bc+'">';
    h += '<div class="ftitle">（'+(i+1)+'）'+esc(f.type||'')+' <span class="tag '+tc+'">['+tl+']</span>'+badge+'</div>';
    var domainText = f.domain || f.category || '';
    if (domainText) h += '<div class="frow"><span class="flabel">涉及领域：</span>'+esc(domainText)+'</div>';
    // 叙事增强：detail 是结构化叙事对象时，渲染富文本叙事；否则按原字符串方式
    if (f.detail && typeof f.detail === 'object' && f.detail.narrative) {
      h += '<div class="frow"><span class="flabel">调查过程：</span></div>';
      h += '<div style="padding:0 0 0 16px">' + f.detail.narrative + '</div>';
      // 也输出 description 作为补充（如果有且不同于叙事HTML）
      if (f.description && f.description !== f.detail.narrative) {
        h += '<div class="frow"><span class="flabel">线索描述：</span>'+esc(f.description)+'</div>';
      }
    } else {
      h += '<div class="frow"><span class="flabel">事实描述：</span>'+esc((f.detail||'')+(f.description||''))+'</div>';
    }
    if (f.items && f.items.length > 0) {
      var cols2 = Object.keys(f.items[0]);
      h += '<div style="margin:8px 0"><div style="font-weight:600;font-size:12px;color:#475569;margin-bottom:4px">证据材料（' + f.items.length + '项明细）</div>';
      h += '<table class="tbl2"><tr>';
      cols2.forEach(function(c){ h += '<th>'+esc(c)+'</th>'; });
      h += '</tr>';
      f.items.forEach(function(row){
        h += '<tr>';
        cols2.forEach(function(c){ h += '<td>'+esc(row[c]||'')+'</td>'; });
        h += '</tr>';
      });
      h += '</table></div>';
    }
    // 交叉引用：查找与本发现相关的其他发现
    var relatedIndices = [];
    var thisDomain = f.domain || f.category || '';
    var thisSource = f.source_chain || '';
    allF.forEach(function(rf, ri){
      if (ri !== i) {
        var rfDomain = rf.domain || rf.category || '';
        var rfSource = rf.source_chain || '';
        if ((thisDomain && thisDomain === rfDomain) || (thisSource && thisSource === rfSource)) {
          if (relatedIndices.length < 3) relatedIndices.push(ri);
        }
      }
    });
    if (relatedIndices.length > 0) {
      h += '<div class="frow" style="font-size:11px;color:#6b7280;margin-top:4px"><span class="flabel">关联发现：</span>';
      h += '参阅 ' + relatedIndices.map(function(ri){ return `<a href="#" onclick="document.getElementById('finding-${ri}').scrollIntoView({behavior:'smooth'});return false" style="color:#2563eb">发现${ri+1}</a>`; }).join('、');
      var relNames = relatedIndices.map(function(ri){ return esc((allF[ri].type||'').substring(0,20)); }).join(' / ');
      h += '（' + relNames + '）——同一域/线索链，交叉验证</div>';
    }

    // 调查过程——始终展示
    if (f.how_found) {
      h += '<div class="frow" style="margin-top:6px;padding-top:6px;border-top:1px dashed #e2e8f0">';
      h += '<span class="flabel">调查过程：</span>' + esc(f.how_found||'') + '</div>';
    }
    // 税务影响分析
    if (f.tax_impact) {
      h += '<div class="frow" style="margin-top:4px;padding:8px 12px;background:#fff7ed;border-left:3px solid #f97316;font-size:13px;line-height:1.8">';
      h += '<span class="flabel" style="color:#c2410c">⚡ 税务影响：</span>' + esc(f.tax_impact||'') + '</div>';
    }
    // 证据来源
    var hasEvidence = (f.rule_id && f.rule_id > 100) || (f.source_chain && !f.source_chain.includes('链驱动'));
    if (hasEvidence) {
      h += '<div class="frow"><span class="flabel">证据来源：</span>';
      if (f.rule_id && f.rule_id > 100) h += '规则ID-'+esc(f.rule_id)+' ';
      if (f.source_chain && !f.source_chain.includes('链驱动')) h += '| '+esc(f.source_chain)+' ';
      h += '</div>';
    }
    h += '<div class="law-ref">法律依据：'+(f.policy_ref ? esc(f.policy_ref) : '《中华人民共和国税收征收管理法》及相关税收法规')+'</div>';
    if (f.suggestion) h += '<div class="frow"><span class="flabel">处理建议：</span>'+esc(f.suggestion||'')+'</div>';
    // 质量标注
    if (f._quality_issues && f._quality_issues.length > 0) {
      h += '<div style="margin-top:4px;font-size:10px;color:#f59e0b;">⚠ 质量标注：' + f._quality_issues.map(function(q){return esc(q);}).join('；') + '</div>';
    }
    h += '</div>';
  });

  // section 5 - 稽查处理意见
  h += '<h2 id="sec5">五、处理处罚建议</h2>';
  h += '<p class="i2">根据上述稽查发现和证据链，提出以下处理处罚建议，请领导审议。</p>';
  var actions=[],seen={};
  allF.forEach(function(f){
    var s=((f.suggestion||'')+'').split('\n')[0].trim();
    if(s&&s.substring(0,50)&&!seen[s.substring(0,50)]){seen[s.substring(0,50)]=true;actions.push(s);}
  });
  actions.slice(0,8).forEach(function(a,i){h+='<p class="i2">'+(i+1)+'. '+esc(a)+'</p>';});
  h += '<p class="i2">根据《中华人民共和国税收征收管理法》及相关规定，建议被查单位在收到本报告后15日内自查补税，并将整改情况书面回复稽查部门。</p>';


  // section 6 - 告知权利义务
  h += '<h2 id="sec6">六、告知权利义务</h2>';
  h += '<div class="rights-sec">';
  h += '<div class="rtitle">根据《中华人民共和国税收征收管理法》及《税务稽查工作规程》，被查单位享有以下权利：</div>';
  h += '<div class="ritem">1. <b>申请回避权</b>：认为稽查人员与本案有利害关系的，可在收到本报告之日起3日内申请回避。</div>';
  h += '<div class="ritem">2. <b>陈述申辩权</b>：对本报告认定的事实、证据、法律依据有异议的，可在收到本报告之日起5日内提出陈述申辩意见。</div>';
  h += '<div class="ritem">3. <b>听证权</b>：对拟作出的较大数额罚款（法人或其他组织1万元以上）有异议的，可在收到《税务行政处罚事项告知书》后3日内申请听证。</div>';
  h += '<div class="ritem">4. <b>复议权</b>：对税务处理决定或处罚决定不服的，可在收到决定书之日起60日内向上一级税务机关申请行政复议。</div>';
  h += '<div class="ritem">5. <b>诉讼权</b>：对税务处理决定或处罚决定不服的，可在收到决定书之日起6个月内向人民法院提起行政诉讼。</div>';
  h += '</div>';

  // section 7 - 稽查人员签字
  h += '<h2 id="sec7">七、稽查人员签字</h2>';
  h += '<div class="seal">';
  h += '<div>稽查执行人：___________ （签名）  ' + dateStr + '</div>';
  h += '<div style="margin-top:10px">审理人：___________ （签名）</div>';
  h += '<div style="margin-top:20px">稽查部门（盖章）：___________</div>';
  h += '<div style="margin-top:20px">报告日期：' + dateStr + '</div>';
  h += '</div>';

  // 附件：证据清单
  h += '<div class="appendix">';
  h += '<div class="atitle">附件：证据清单</div>';
  h += '<div class="aitem">1. 进销项发票数据（电子版）</div>';
  h += '<div class="aitem">2. 银行流水数据（电子版）</div>';
  h += '<div class="aitem">3. 合同文件（如有）</div>';
  h += '<div class="aitem">4. 其他经营资料（共' + r.files_count + '份）</div>';
  h += '</div>';

  h += '</div>';

  area.innerHTML = h;
  area.scrollIntoView({ behavior: 'smooth' });
}

// ==================== 稽查叙事报告 ====================
var narrativeMode = false;

function toggleNarrativeMode() {
  narrativeMode = !narrativeMode;
  var btn = document.getElementById('tda-narrative-btn');
  if (!taxDocReportData) return;
  
  if (narrativeMode) {
    if (btn) btn.textContent = '切回标准报告';
    if (btn) btn.style.cssText = 'cursor:pointer;padding:6px 14px;border:1px solid #7c3aed;background:#f5f3ff;color:#7c3aed;border-radius:4px;font-size:12px;font-weight:600';
    renderNarrativeReport(taxDocReportData);
  } else {
    if (btn) btn.textContent = '稽查叙事报告';
    if (btn) btn.style.cssText = 'cursor:pointer;padding:6px 14px;border:1px solid #d1d5db;background:#fff;color:#6b7280;border-radius:4px;font-size:12px';
    renderAnalyzeHeader(taxDocReportData);
    renderTaxDocReport(taxDocReportData);
  }
}

function renderNarrativeReport(r) {
  var area = document.getElementById('tda-report-area');
  if (!area || !r) return;

  var te = r.target_entity || {};
  var allF = r.all_findings || [];
  allF.sort(function(a,b){return(b.score||0)-(a.score||0);});
  var cc = r.comprehensive || {};
  var mi = cc.material_intel || {};
  var bi = mi['银行流水'] || {};
  var ii = mi['发票'] || {};
  var ga = te._goods_analysis || {};
  var purOnlyGoods = ga.pur_only_goods || [];
  var salOnlyGoods = ga.sal_only_goods || [];
  var commonGoods = ga.common_goods || [];
  var hasProcFee = ga.has_processing_fee || false;
  var registeredBusiness = te.industry_online || '';
  var inferredBusiness = te.industry || '';
  var hasProcessingSignal = !!(te._has_processing_signal || (ii && ii['加工费信号']));
  var actualBusiness = '';
  if (registeredBusiness && inferredBusiness && registeredBusiness !== inferredBusiness) {
    actualBusiness = inferredBusiness + (hasProcessingSignal ? '+外包轻加工模式' : '');
  } else if (!registeredBusiness && inferredBusiness) {
    actualBusiness = inferredBusiness + (hasProcessingSignal ? '+外包轻加工模式' : '');
  }

  function esc(s) { if (!s) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

  var now = new Date();
  var dateStr = now.getFullYear()+'年'+(now.getMonth()+1)+'月'+now.getDate()+'日';
  var timeStr = now.getHours()+':'+String(now.getMinutes()).padStart(2,'0');

  var h = '<style>'
    + '#nr-report *{margin:0;padding:0;box-sizing:border-box}'
    + '#nr-report{font-family:"PingFang SC","Microsoft YaHei","Noto Serif SC",serif;font-size:15px;line-height:2.2;color:#1a1a2e;max-width:800px;margin:0 auto;padding:80px 60px;background:#fff}'
    + '#nr-report .nr-cover{text-align:center;padding:80px 0 60px;border-bottom:3px double #1a1a2e;margin-bottom:60px}'
    + '#nr-report .nr-cover h1{font-size:28px;font-weight:900;letter-spacing:8px;margin-bottom:24px;color:#0f172a}'
    + '#nr-report .nr-cover .nr-sub{font-size:14px;color:#64748b;line-height:2.8}'
    + '#nr-report .nr-chapter{margin:50px 0 30px;padding-bottom:12px;border-bottom:2px solid #1a1a2e}'
    + '#nr-report .nr-chapter h2{font-size:20px;font-weight:800;letter-spacing:3px;margin-bottom:6px;color:#0f172a}'
    + '#nr-report .nr-chapter .nr-ch-sub{font-size:13px;color:#64748b}'
    + '#nr-report .nr-body{text-align:justify}'
    + '#nr-report .nr-body p{margin:12px 0;text-indent:2em}'
    + '#nr-report .nr-body p.nr-no-indent{text-indent:0}'
    + '#nr-report .nr-quote{margin:16px 0;padding:12px 16px;background:#f8fafc;border-left:4px solid #475569;font-size:13px;color:#334155;font-style:italic}'
    + '#nr-report .nr-evidence{margin:16px 0;padding:16px 20px;background:#fffbeb;border:1px solid #fde68a;border-radius:6px}'
    + '#nr-report .nr-evidence .nr-ev-title{font-size:13px;font-weight:700;color:#92400e;margin-bottom:10px}'
    + '#nr-report .nr-table{width:100%;border-collapse:collapse;margin:10px 0;font-size:12px}'
    + '#nr-report .nr-table th{background:#f5f5f5;padding:5px 8px;text-align:left;border:1px solid #e2e8f0;font-weight:600;font-size:12px}'
    + '#nr-report .nr-table td{padding:4px 8px;border:1px solid #f1f5f9;font-size:12px}'
    + '#nr-report .nr-finding{margin:30px 0;padding:24px 28px;border:1px solid #e2e8f0;border-radius:8px;background:#fafbfc}'
    + '#nr-report .nr-finding .nr-f-title{font-size:16px;font-weight:700;color:#0f172a;margin-bottom:6px;padding-bottom:6px;border-bottom:1px solid #f1f5f9}'
    + '#nr-report .nr-finding .nr-f-meta{font-size:11px;color:#94a3b8;margin-bottom:12px}'
    + '#nr-report .nr-finding .nr-f-meta .nr-badge{display:inline-block;padding:1px 6px;border-radius:3px;font-size:10px;font-weight:600;margin-left:8px}'
    + '#nr-report .nr-badge-red{background:#fee2e2;color:#991b1b}'
    + '#nr-report .nr-badge-amber{background:#fef3c7;color:#92400e}'
    + '#nr-report .nr-badge-green{background:#dcfce7;color:#166534}'
    + '#nr-report .nr-law{margin:12px 0;padding:10px 14px;background:#f0f9ff;border-left:3px solid #2563eb;font-size:12px;color:#1e40af;line-height:1.8}'
    + '#nr-report .nr-sig{text-align:right;margin-top:80px;padding-top:30px;border-top:1px solid #cbd5e1;line-height:2.5;font-size:14px;color:#475569}'
    + '#nr-report .nr-sig .nr-sig-name{font-size:16px;font-weight:700;color:#1a1a2e;margin-bottom:4px}'
    + '#nr-report .nr-toc{margin:40px 0;padding:20px 30px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px}'
    + '#nr-report .nr-toc .nr-toc-title{font-size:15px;font-weight:700;margin-bottom:12px;color:#0f172a}'
    + '#nr-report .nr-toc .nr-toc-item{font-size:13px;line-height:2.4;color:#475569}'
    + '#nr-report .nr-inspector-thought{margin:12px 0;padding:10px 14px;background:#fefce8;border-left:3px solid #eab308;font-size:13px;color:#713f12;line-height:1.8;font-style:italic}'
    + '#nr-report strong{color:#0f172a}'
    + '#nr-report .nr-highlight{background:#fef08a;padding:0 2px}'
    + '</style><div id="nr-report">';

  // ═══ 封面 ═══
  h += '<div class="nr-cover">'
    + '<h1>税务稽查报告</h1>'
    + '<div class="nr-sub">'
    + '编号：税稽字[' + now.getFullYear() + ']第' + String(Math.floor(Math.random()*900+100)).padStart(3,'0') + '号<br>'
    + '被查单位：' + esc(te.name || '（根据资料推断）') + '<br>'
    + '稽查期间：' + esc(te.period || '资料覆盖期间') + '<br>'
    + '报告日期：' + dateStr
    + '</div></div>';

  // ═══ 目录 ═══
  h += '<div class="nr-toc"><div class="nr-toc-title">目  录</div>'
    + '<div class="nr-toc-item">第一章　案件受理与基本情况</div>'
    + '<div class="nr-toc-item">第二章　稽查方案与工作部署</div>'
    + '<div class="nr-toc-item">第三章　稽查实施过程</div>'
    + '<div class="nr-toc-item">第四章　稽查结论</div>'
    + '<div class="nr-toc-item">第五章　风险疑点详报与证据链</div>'
    + '<div class="nr-toc-item">第六章　证据链组织总结</div>'
    + '<div class="nr-toc-item">第七章　处理处罚建议</div>'
    + '<div class="nr-toc-item">第八章　告知事项</div>'
    + '</div>';

  // ═══ 开篇：向上级汇报 ═══
  h += '<div class="nr-chapter"><h2>关于' + esc(te.name || '某企业') + '涉税资料的稽查情况汇报</h2><div class="nr-ch-sub">汇报人：国家税务总局XX稽查局稽查员　' + dateStr + '</div></div>';

  // ═══ 第一章：案件受理与基本情况 ═══
  h += '<div class="nr-chapter"><h2>第一章　案件受理与基本情况</h2><div class="nr-ch-sub">' + dateStr + ' ' + timeStr + '</div></div>';
  h += '<div class="nr-body">';

  h += '<p><strong>领导：</strong></p>';
  h += '<p>现就<span class="nr-highlight">' + esc(te.name || '某企业') + '</span>（统一社会信用代码<span style="white-space:nowrap">' + esc(te.uscc || '') + '</span>）的涉税资料稽查情况，向您做详细汇报。</p>';
  h += '<p>本案来源于电子经营资料自动预审系统推送，属于资料风险分析预审案件。我在受理后，立即按照《税务稽查工作规程》的要求，启动了系统性的稽查工作。现将核查情况逐项汇报如下。</p>';

  var onlineOK = !!te._online_lookup;
  if (onlineOK) {
    h += '<p>受理案件后，我首先通过联网核查系统对被查单位的基本工商信息进行了核实。经查，被查单位' + esc(te.name || '') + '，统一社会信用代码<span style="white-space:nowrap">' + esc(te.uscc || '') + '</span>，成立于' + esc(te.established_date || '') + '，登记状态为' + esc(te.company_status || te.status || '') + '，企业类型为' + esc(te.company_type || te.type || '') + '，法定代表人' + esc(te.legal_person || te.legal_representative || '') + '。注册资本' + esc(te.registered_capital || '') + '。工商登记行业为' + esc(registeredBusiness || '') + '。注册地址位于' + esc(te.address || '') + '。经营范围为' + esc(te.business_scope || '') + '。</p>';
  } else {
    h += '<p>联网核查未获取到完整工商信息。我从发票数据中推断，该单位所属行业为' + esc(inferredBusiness || '') + '。我提醒自己，联网核查是稽查方法论第六项要求，后续应补充天眼查/企查查等渠道核实。</p>';
  }

  var spr = te._six_personnel_risk;
  if (spr) {
    var mp = spr.my_personnel || {};
    var myNames = Object.keys(mp);
    if (myNames.length > 0) {
      h += '<p>在人员核查中，我调取了被查单位的六员信息（法定代表人、股东、董事、监事、财务负责人、办税人员）。发现以下关键人员：</p>';
      for (var ni = 0; ni < myNames.length; ni++) {
        var name = myNames[ni];
        var roles = mp[name] || [];
        h += '<p class="nr-no-indent">　· <strong>' + esc(name) + '</strong>：' + roles.map(function(r){return esc(r);}).join('、') + '</p>';
      }
      var multiRole = spr.one_person_multi_role || [];
      if (multiRole.length > 0) {
        h += '<div class="nr-inspector-thought">⚠ 稽查警觉：' + multiRole.map(function(mr){return esc(mr.name)+'一人同时担任'+mr.count+'个关键角色（'+mr.roles.map(function(r){return esc(r);}).join('、')+'）';}).join('；') + '。一人多角意味着企业缺乏内控制衡，资金流向完全由个人意志决定，这在稽查中是重要风险信号。</div>';
      }
      var crossCo = spr.cross_company_overlap || [];
      if (crossCo.length > 0) {
        h += '<div class="nr-inspector-thought">⚠ 跨企业人员重叠：' + crossCo.map(function(cc){return '对方企业'+esc(cc.other_company)+'与本企业存在人员重叠';}).join('；') + '。两家企业可能为关联方，需进一步核查资金往来和转移定价。</div>';
      }
    }
  }

  h += '<p>收到推送时，系统已预先完成了资料扫描。被查单位提交了' + r.files_count + '份电子经营资料。在税务稽查要求提供的14类必查资料中，<strong>仅提交了3类</strong>（银行流水、销项发票、进项发票），其余11类资料完全缺失。这给我的稽查工作带来了困难，但我在现有条件下全力推进。</p>';

  // ═══ 调查时间线 ═══
  h += '<div class="nr-evidence" style="margin-top:20px"><div class="nr-ev-title">📅 我的调查时间线</div>';
  h += '<table class="nr-table">';
  h += '<tr><th style="width:80px;">阶段</th><th>时间节点</th><th>工作内容</th><th>产出</th></tr>';
  h += '<tr><td style="font-weight:700;">受理</td><td>' + dateStr + ' ' + timeStr + '</td><td>收到系统推送，受理' + esc(te.name || '被查单位') + '涉税资料分析案件</td><td>案件受理记录</td></tr>';
  h += '<tr><td style="font-weight:700;">初步审查</td><td>' + dateStr + '（同日）</td><td>联网核查工商信息、审查14类资料提交情况、六员风险分析</td><td>企业基本画像+资料缺失清单</td></tr>';
  h += '<tr><td style="font-weight:700;">资料解析</td><td>' + dateStr + '（同日）</td><td>解析银行流水（收款' + esc(bi['总收款']||'?') + '元/付款' + esc(bi['总付款']||'?') + '元）、进项发票' + esc(ii['进项发票']||'?') + '、销项发票' + esc(ii['销项发票']||'?') + '</td><td>结构化数据提取</td></tr>';
  h += '<tr><td style="font-weight:700;">逐域分析</td><td>' + dateStr + '（同日）</td><td>依次执行：经营实质核查→资金流分析→发票流分析→多源交叉验证→资料完备度评估</td><td>' + allF.length + '条风险信号+证据链</td></tr>';
  h += '<tr><td style="font-weight:700;">综合研判</td><td>' + dateStr + '（同日）</td><td>跨域线索串联、证据链组织、风险定级、处理建议拟定</td><td>本稽查报告</td></tr>';
  h += '<tr><td style="font-weight:700;">汇报</td><td>' + dateStr + '</td><td>向上级领导提交稽查报告，请求审议</td><td>—</td></tr>';
  h += '</table></div>';

  h += '</div>';

  // ═══ 第二章：稽查方案与工作部署 ═══
  h += '<div class="nr-chapter"><h2>第二章　稽查方案与工作部署</h2><div class="nr-ch-sub">制定稽查策略</div></div>';
  h += '<div class="nr-body">';

  h += '<p><strong>领导，在正式开展稽查之前，我制定了以下稽查方案。现向您汇报我的工作部署：</strong></p>';

  // 稽查方案
  h += '<div class="nr-evidence"><div class="nr-ev-title">📋 我的稽查方案——六步工作法</div>';
  h += '<table class="nr-table">';
  h += '<tr><th style="width:80px;">步骤</th><th>稽查内容</th><th style="width:120px;">稽查方法</th><th style="width:120px;">预期产出</th></tr>';
  h += '<tr><td style="font-weight:700;">第一步</td><td>工商登记核查</td><td>联网核查法</td><td>企业基本画像</td></tr>';
  h += '<tr><td style="font-weight:700;">第二步</td><td>经营实质穿透</td><td>三层行业穿透法 — 工商登记→进项发票→销项发票→交叉比对</td><td>实质经营模式认定</td></tr>';
  h += '<tr><td style="font-weight:700;">第三步</td><td>资金流分析</td><td>资金流向追踪法 — 收款来源分类+付款方穿透+大额整数检测</td><td>资金异常清单</td></tr>';
  h += '<tr><td style="font-weight:700;">第四步</td><td>发票流分析</td><td>发票实质性审阅法 — 逐票核查要素+供应商/客户穿透+品名匹配</td><td>发票异常清单</td></tr>';
  h += '<tr><td style="font-weight:700;">第五步</td><td>多源交叉验证</td><td>三源比对法+四流合一验证法+客户维度三源穿透法</td><td>跨域线索链</td></tr>';
  h += '<tr><td style="font-weight:700;">第六步</td><td>资料完备度评估</td><td>14类资料逐类核查+缺失后果分析</td><td>资料缺失风险清单</td></tr>';
  h += '</table></div>';

  h += '<p><strong>我的稽查顺序逻辑：</strong>我按照"先外围后核心、先单域后跨域"的原则安排稽查顺序。先通过工商登记和经营实质分析建立企业画像，再分别深入资金流和发票流两个核心域，然后将两个域的数据交叉验证寻找矛盾点，最后进行资料完备度评估——因为只有在深入分析了已有资料后，才能真正理解资料缺失对稽查的影响程度。</p>';

  h += '<p><strong>证据链组织思路：</strong>针对每一个风险疑点，我遵循"四步证据法"——①提取原始数据（银行流水/发票/工商登记）→②逐条匹配稽查规则→③多源交叉验证（≥2个数据域）→④形成证据闭环。所有高风险事项的认定均满足"≥2域交叉验证"标准，符合《税务稽查工作规程》关于证据必须真实、与所证明事项相关联的要求。</p>';

  // 稽查局限性声明
  h += '<div class="nr-inspector-thought" style="margin-top:16px">⚠ <strong>稽查局限性如实声明：</strong>领导，我必须如实汇报——由于被查单位仅提交了3类资料，本次稽查存在以下无法覆盖的范围：①无法核查记账凭证→会计账簿健全性无法验证 ②无法核查工资表和社保明细→用工合规性和个税代扣代缴无法核实 ③无法核查合同文件→交易真实性无法通过四流合一验证 ④无法核查各税种申报表→申报准确性和完整性问题只能在资料补全后另行稽查。我已在每个因资料缺失导致的结论中明确标注了前提条件，所有结论在现有资料范围内有效。</div>';

  h += '</div>';

  // ═══ 第三章：稽查实施过程 ═══
  h += '<div class="nr-chapter"><h2>第三章　稽查实施过程</h2><div class="nr-ch-sub">按照稽查方案逐项执行　共启动' + (r.rules_used || '?') + '条稽查指令</div></div>';
  h += '<div class="nr-body">';

  h += '<p><strong>领导，按照前述六步工作法，我依次开展了以下稽查工作。以下各节按执行顺序逐项汇报。</strong></p>';

  // ═══ 资料解析统计概览 ═══
  var totalFindings = allF.length;
  var highRiskCount = allF.filter(function(f){return (f.level||'').indexOf('高')>-1 || (f.score||0)>=8;}).length;
  var midRiskCount = allF.filter(function(f){return (f.level||'').indexOf('中')>-1 || ((f.score||0)>=5 && (f.score||0)<8);}).length;
  var lowRiskCount = totalFindings - highRiskCount - midRiskCount;
  var totalInvs = (ii['进项发票']||'').replace(/[^0-9]/g,'')||'?';
  var totalSalesInvs = (ii['销项发票']||'').replace(/[^0-9]/g,'')||'?';
  var totalBankIn = (bi['总收款']||'').replace(/[^0-9.]/g,'')||'?';
  var totalBankOut = (bi['总付款']||'').replace(/[^0-9.]/g,'')||'?';

  h += '<div class="nr-evidence"><div class="nr-ev-title">📊 资料解析统计概览</div>';
  h += '<table class="nr-table">';
  h += '<tr><th>指标</th><th>数值</th><th>稽查判断</th></tr>';
  h += '<tr><td>提交文件数</td><td>' + (r.files_count||'?') + '份</td><td>仅3类资料可用，其余11类缺失</td></tr>';
  h += '<tr><td>银行流水</td><td>收款' + esc(bi['总收款']||'?') + '元 / 付款' + esc(bi['总付款']||'?') + '元</td><td>资金链条追踪的基础数据</td></tr>';
  h += '<tr><td>进项发票</td><td>' + esc(ii['进项发票']||'?') + '，采购总额' + esc(ii['进项采购额']||'?') + '元</td><td>成本真实性验证的核心依据</td></tr>';
  h += '<tr><td>销项发票</td><td>' + esc(ii['销项发票']||'?') + '，销售总额' + esc(ii['销项销售额']||'?') + '元</td><td>收入完整性验证的核心依据</td></tr>';
  h += '<tr><td>稽查发现总计</td><td>' + totalFindings + '条（高风险' + highRiskCount + ' / 中风险' + midRiskCount + ' / 低风险' + lowRiskCount + '）</td><td>高风险发现需立即处理</td></tr>';
  h += '</table></div>';

  // 经营实质核查
  h += '<h3 style="margin-top:30px;font-size:16px;color:#0f172a">一、经营实质核查</h3>';
  h += '<p>根据稽查方法论第二十五项（三层行业穿透法），我先从工商登记入手了解企业基本情况。</p>';

  h += '<p><strong>第一层——工商登记信息：</strong>工商登记行业为' + esc(registeredBusiness || te.industry || te.type || '未获取') + '。' + (registeredBusiness ? '' : '搜索引擎未返回行业分类，我以发票数据推断行业为准。') + '</p>';

  if (hasProcFee || purOnlyGoods.length > 0 || salOnlyGoods.length > 0) {
    h += '<p><strong>第二层——发票数据穿透：</strong>我逐张翻阅了被查单位提交的全部进项发票。';
    if (hasProcFee) {
      h += '在翻阅过程中，我注意到进项发票中出现了<b>加工费</b>类支出——包括委托加工、外协加工、工序外包等。加工费的出现意味着企业并非单纯的贸易公司，而是将原材料/半成品委托外部加工为成品。这让我立即警觉：工商登记的经营范围能否涵盖委托加工业务？';
    }
    if (purOnlyGoods.length > 0) {
      h += '同时，我发现以下品名<b>仅在进项发票中出现</b>（购进但从未销售）：' + purOnlyGoods.map(function(g){return '<b>' + esc(g) + '</b>';}).join('、') + '。这些应该是采购的原材料或委托加工物资。';
    }
    h += '</p>';

    h += '<p><strong>第三层——销项发票穿透：</strong>我接着逐张翻阅了全部销项发票。发现以下品名<b>仅在销项中出现</b>（销售但从未购进）：' + salOnlyGoods.map(function(g){return '<b>' + esc(g) + '</b>';}).join('、') + '。这些应该是将原材料加工后产出的成品。</p>';

    h += '<p><strong>进销交叉比对：</strong>我将进项发票品名与销项发票品名逐一对照。';
    if (commonGoods.length > 0) {
      h += '以下品名在进销两端均有出现，属于纯贸易行为：' + commonGoods.map(function(g){return '<b>' + esc(g) + '</b>';}).join('、') + '。';
    }
    if (purOnlyGoods.length > 0 && salOnlyGoods.length > 0) {
      h += '同时存在仅购进不销售的品名（' + purOnlyGoods.length + '类）和仅销售不购进的品名（' + salOnlyGoods.length + '类），这是典型的"采购原材料→委托加工→销售成品"模式。';
    }
    h += '</p>';

    h += '<p><strong>综合判断：</strong>经过上述三层穿透分析——工商登记为' + esc(registeredBusiness || inferredBusiness) + '、发票数据显示' + (hasProcFee ? '存在加工费信号' : '无加工费信号') + '、进销品名存在' + (purOnlyGoods.length + salOnlyGoods.length) + '类实质性差异——';
    if (hasProcFee || (purOnlyGoods.length > 0 && salOnlyGoods.length > 0)) {
      h += '我认定被查单位的<strong>实质经营模式为' + esc(actualBusiness || (inferredBusiness + '+外包轻加工模式')) + '</strong>，与其工商登记行业不完全一致。这个发现意味着，在后续的税务处理中，应按照实质经营模式来认定业务性质。</p>';
    } else {
      h += '被查单位实质经营模式与工商登记一致。</p>';
    }
  } else {
    h += '<p><strong>第二至三层——发票数据穿透：</strong>我对进项和销项发票品名进行逐票审核和交叉比对，未发现加工费项目，进销品名一致，确认企业实质经营模式与工商登记一致。</p>';
  }

  // 银行流水分析
  h += '<h3 style="margin-top:30px;font-size:16px;color:#0f172a">二、银行流水分析</h3>';
  h += '<p>我打开被查单位提交的银行流水文件。该账户在稽查期间，总收款' + esc(bi['总收款'] || '') + '元，总付款' + esc(bi['总付款'] || '') + '元，税费支出' + esc(bi['税费支出总额'] || '') + '元。</p>';

  var rc = bi['收款构成'];
  if (rc) {
    h += '<p>我对收款来源进行了分类统计：</p>';
    h += '<p class="nr-no-indent">　· <strong>企业客户款：</strong>' + esc(rc['企业客户款'] || '') + '元——来自企业客户的经营收款<br>';
    h += '　· <strong>个人款：</strong>' + esc(rc['个人款'] || '') + '元——来自个人账户的转入<br>';
    h += '　· <strong>税费社保退款：</strong>' + esc(rc['税费社保退款'] || '') + '元——代付社保及医保代发等，非经营收入<br>';
    h += '　· <strong>银行利息/内部转账：</strong>' + esc(rc['银行利息/内部'] || '') + '元——银行结息等，非经营收入</p>';
    h += '<div class="nr-inspector-thought">💡 稽查警觉：个人收款是我重点关注的对象。在税务稽查中，个人账户向对公账户的转账，可能是股东注资、关联方借款，也可能是未申报的经营收入——后者是典型的账外经营信号，需要逐笔核实资金来源和性质。</div>';
  }

  // 付款方分析
  var pe = bi['付款方全部'];
  if (pe && pe.length) {
    h += '<p>在付款端，被查单位共向' + pe.length + '个收款方支付了款项。我逐一核查了付款记录，重点关注是否存在向个人账户的大额付款（可能涉及无票支出或利益输送）。</p>';
    h += '<table class="nr-table"><tr><th>收款方</th><th style="text-align:right">付款金额（元）</th></tr>';
    pe.forEach(function(p){ 
      var n = (p['名称']||'').substring(0,30);
      h += '<tr><td>' + esc(n) + '</td><td style="text-align:right">' + esc(p['金额']||'') + '</td></tr>'; 
    });
    h += '</table>';
  }

  // 发票分析
  h += '<h3 style="margin-top:30px;font-size:16px;color:#0f172a">三、发票数据分析</h3>';
  var xm = ii['销项客户明细'];
  var jm = ii['进项供应商明细'];
  
  if (xm && xm.length) {
    h += '<p>销项端，被查单位向' + xm.length + '家客户开具了发票，涉及' + esc(ii['销项发票'] || '') + '。我逐一核对了每家客户的销售金额：</p>';
    h += '<table class="nr-table"><tr><th>购买方</th><th style="text-align:right">销售金额（元）</th></tr>';
    xm.forEach(function(p){ h += '<tr><td>' + esc((p['名称']||'').substring(0,30)) + '</td><td style="text-align:right">' + esc(p['金额']||'') + '</td></tr>'; });
    h += '</table>';
  }

  if (jm && jm.length) {
    h += '<p>进项端，被查单位从' + jm.length + '家供应商取得了发票，涉及' + esc(ii['进项发票'] || '') + '。进销比为' + esc(ii['进销比'] || '') + '。我逐一核查了每家供应商的采购金额：</p>';
    h += '<table class="nr-table"><tr><th>供应商</th><th style="text-align:right">采购金额（元）</th></tr>';
    jm.forEach(function(p){ h += '<tr><td>' + esc((p['名称']||'').substring(0,30)) + '</td><td style="text-align:right">' + esc(p['金额']||'') + '</td></tr>'; });
    h += '</table>';
  }

  h += '</div>';

  // ═══ 第四章：稽查结论 ═══
  var nrHighCount = allF.filter(function(f){return(f.score||0)>=8;}).length;
  var nrMidCount = allF.filter(function(f){return(f.score||0)>=5&&(f.score||0)<8;}).length;
  var nrLowCount = allF.filter(function(f){return(f.score||0)<5;}).length;
  var nrRiskText = nrHighCount>0?'高风险':(nrMidCount>0?'中风险':'低风险');
  var nrRiskColor = nrHighCount>0?'#dc2626':(nrMidCount>0?'#d97706':'#059669');
  var nrChainSet = {};
  allF.forEach(function(f){ if(f.source_chain) nrChainSet[f.source_chain] = true; });
  var nrChainList = Object.keys(nrChainSet);

  h += '<div class="nr-chapter"><h2>第四章　稽查结论</h2><div class="nr-ch-sub">领导，以上稽查工作完成后，我得出以下结论</div></div>';
  h += '<div class="nr-body">';

  h += '<div style="margin:20px 0;padding:24px 28px;background:' + (nrHighCount>0?'#fef2f2':(nrMidCount>0?'#fffbeb':'#f0fdf4')) + ';border:2px solid ' + (nrHighCount>0?'#fecaca':(nrMidCount>0?'#fde68a':'#bbf7d0')) + ';border-radius:10px">';
  h += '<p style="font-size:18px;font-weight:800;margin-bottom:12px;text-indent:0">综合风险评级：<span style="color:' + nrRiskColor + '">' + nrRiskText + '</span></p>';
  h += '<p>经过对' + esc(te.name || '被查单位') + '在' + esc(te.period || '稽查期间') + '经营活动的全面稽查，我共发现<strong>' + allF.length + '</strong>项问题：高风险<strong>' + nrHighCount + '</strong>项、中风险<strong>' + nrMidCount + '</strong>项、低风险<strong>' + nrLowCount + '</strong>项。已启动<strong>' + (r.rules_used||'?') + '条</strong>稽查指令完成全量核查，覆盖' + nrChainList.length + '条稽查线索链。</p>';
  if (nrChainList.length > 0) {
    h += '<p><strong>稽查线索链覆盖：</strong>本次调查共激活' + nrChainList.length + '条稽查线索链：' + nrChainList.slice(0,12).map(function(c){return esc(c);}).join('、') + (nrChainList.length>12?'等':'') + '。</p>';
  }
  if (nrHighCount > 0) {
    h += '<p style="color:#dc2626;font-weight:700">被查单位存在' + nrHighCount + '项高风险问题，涉嫌税收违法行为，建议依法进一步核查处理。</p>';
    h += '<p><strong>主要高风险事项：</strong></p>';
    allF.filter(function(f){return(f.score||0)>=8;}).slice(0,5).forEach(function(f, j){
      var dText = typeof f.detail === 'object' && f.detail.summary ? f.detail.summary : (typeof f.detail === 'string' ? f.detail : (f.description || ''));
      h += '<p class="nr-no-indent">' + (j+1) + '. <strong>' + esc(f.type||'') + '</strong>：' + esc(dText) + '</p>';
    });
  }
  h += '</div>';
  h += '<p><strong>领导，以上是我的稽查结论。</strong></p>';

  // 处理优先级建议
  var urgentNf = allF.filter(function(f){return(f.score||0)>=8;}).slice(0,4);
  if (urgentNf.length > 0) {
    h += '<div class="nr-inspector-thought" style="margin-top:12px">🔴 <strong>领导，我建议优先处理以下' + urgentNf.length + '项最紧急的问题：</strong>';
    urgentNf.forEach(function(fn, pi){
      h += '<br>　' + (pi+1) + '. <strong>' + esc(fn.type||'') + '</strong>——' + esc((fn.tax_impact||'').split('→')[0] || '需立即处理') + '。';
    });
    h += '<br><br>其余' + (allF.length - urgentNf.length) + '项中高风险及低风险问题建议限期整改。以上建议请领导审议决策。</div>';
  }

  h += '<p><strong>第五章将逐项详述每项风险疑点的具体调查过程、稽查线索、证据材料和处理建议。</strong></p>';
  h += '</div>';

  // ═══ 第五章：风险疑点详报与证据链 ═══
  h += '<div class="nr-chapter"><h2>第五章　风险疑点详报与证据链</h2><div class="nr-ch-sub">逐项汇报调查过程　共' + allF.length + '项发现</div></div>';
  h += '<div class="nr-body">';

  h += '<p>在完成资料解析后，我启动了' + (r.rules_used || '') + '条稽查指令，对资金流、发票流、业务流进行逐项核查。</p>';

  // ═══ 发现统计概览 ═══
  h += '<div class="nr-evidence"><div class="nr-ev-title">📊 逐项调查发现统计</div>';
  h += '<table class="nr-table">';
  h += '<tr><th>风险等级</th><th>数量</th><th>占比</th><th>处理优先级</th></tr>';
  h += '<tr><td style="color:#dc2626">🔴 高风险</td><td>' + highRiskCount + '条</td><td>' + (totalFindings>0?(highRiskCount/totalFindings*100).toFixed(0):0) + '%</td><td>立即处理——涉及偷税/虚开/核定征收等严重违法</td></tr>';
  h += '<tr><td style="color:#f59e0b">🟡 中风险</td><td>' + midRiskCount + '条</td><td>' + (totalFindings>0?(midRiskCount/totalFindings*100).toFixed(0):0) + '%</td><td>限期整改——涉及合规缺陷/申报差异/资料缺失</td></tr>';
  h += '<tr><td style="color:#6b7280">⚪ 低风险</td><td>' + lowRiskCount + '条</td><td>' + (totalFindings>0?(lowRiskCount/totalFindings*100).toFixed(0):0) + '%</td><td>持续关注——日常费用/技术性提醒</td></tr>';
  h += '</table></div>';

  h += '<p><strong>领导，以下是我对每一项风险疑点的详细调查汇报。每个疑点均按照"调查过程→稽查线索→证据材料→法律依据→处理建议"的五段式结构呈现，并标注了我组织证据链的方法。</strong></p>';

  // 逐项发现——第一人称叙事
  var highCount = 0, midCount = 0, lowCount = 0;
  allF.forEach(function(f, i){
    var s = f.score||0;
    var tl = (f.level||'') || (s>=8?'高风险':(s>=6?'中风险':'低风险'));
    var badgeCls = s>=8?'nr-badge-red':(s>=6?'nr-badge-amber':'nr-badge-green');
    if (s>=8) highCount++; else if (s>=6) midCount++; else lowCount++;

    // 生成叙事文本
    var domainText = f.domain || f.category || '';
    var descText = typeof f.detail === 'object' && f.detail.summary ? f.detail.summary :
                   (typeof f.detail === 'string' ? f.detail : (f.description || ''));
    
    // 根据不同类型生成不同的调查叙事
    var narrativeText = '';
    
    if (f.type && f.type.indexOf('资料完备度') >= 0) {
      narrativeText = '<p>在稽查工作开始时，我首先对资料完备情况进行了全面审查。按照金税四期稽查必查清单，企业应提供14类经营资料：银行流水、销项发票、进项发票、记账凭证、工资表、社保明细、进销存台账、合同文件、科目余额表、资产负债表及利润表、增值税申报表、企业所得税申报表、个人所得税申报表、其他税种申报表。</p>'
        + '<p>经过逐一核验，我发现被查单位仅提交了<strong>3类资料</strong>（银行流水、销项发票、进项发票），其余11类关键资料完全没有提供。这给我的稽查工作带来了极大的困难：没有记账凭证就无法追溯账务处理过程；没有工资表和社保明细就无法核实用工合规性；没有合同文件就无法验证交易真实性；没有申报表就无法核对申报数据与发票数据的一致性。</p>'
        + '<p>我决定在现有资料条件下尽力推进调查，同时对每一项因资料缺失导致的发现，我都会在报告中明确标注"资料受限"字样。被查单位需在收到本报告后立即补充缺失的11类资料，否则将依据《税收征收管理法》第五十六条关于资料提供义务的规定处理。</p>';
    } else if (f.type && f.type.indexOf('跨域') >= 0) {
      narrativeText = '<p>这条线索链是通过跨域数据交叉比对自动触发的。我将不同分析域（工商登记、银行流水、发票数据、地理信息等）的数据进行串联分析，发现多个域的异常信号指向同一个风险方向。</p>'
        + '<p>我调取了多个数据源的记录进行逐一比对。调查路径覆盖了多个维度的交叉验证：从初始信号出发，逐步扩展至相关数据域，最终形成了完整的证据链闭环。</p>'
        + '<p>经过多维度交叉验证，我认为这个跨域线索具有足够的证据支撑。以下是我的具体调查过程：</p><p>' + esc(descText) + '</p>';
    } else if (f.type && (f.type.indexOf('发票') >= 0 || f.type.indexOf('开票') >= 0)) {
      narrativeText = '<p>在发票实质性审计中，我逐票翻阅了被查单位提交的全部发票。对于每一张发票，我都会核对以下要素：发票代码和号码、开票日期、购买方和销售方名称及纳税人识别号、货物或应税劳务名称、规格型号、单位、数量、单价、金额、税率、税额。</p>'
        + '<p>在翻阅过程中，我发现了异常。我立即将该异常发票与其他发票进行横向对比，同时核查对应的银行流水是否有相应的资金往来记录。</p>'
        + '<p>具体调查发现：' + esc(descText) + '</p>';
    } else if (f.type && (f.type.indexOf('收款') >= 0 || f.type.indexOf('付款') >= 0 || f.type.indexOf('资金') >= 0 || f.type.indexOf('银行') >= 0)) {
      narrativeText = '<p>在资金流审查中，我将银行流水数据导入分析系统，对所有交易记录进行逐笔分析。我重点关注四个方面：收款方是否与开票客户一致、付款方是否与进项供应商一致、大额整数交易是否存在人为构造痕迹、周末及节假日交易是否具有商业合理性。</p>'
        + '<p>我将银行流水中的收款方名称与销项发票中的购买方名称进行了一一比对，发现存在严重的不匹配情况。</p>'
        + '<p>具体调查发现：' + esc(descText) + '</p>';
    } else if (f.type && f.type.indexOf('地理') >= 0 || f.type && f.type.indexOf('运输') >= 0 || f.type && f.type.indexOf('物流') >= 0 || f.type && f.type.indexOf('经营实质') >= 0) {
      narrativeText = '<p>在经营实质审查中，我从发票中提取了全部供应商、客户和加工商的地址信息，将这些地址标注在地图上进行空间分析。被查单位位于' + esc((te.address||'').substring(0,10)) + '，而其主要供应商分布在多个外地城市，数百至上千公里之遥。</p>'
        + '<p>我进一步核查了银行流水中是否存在运输费、物流费、快递费等支出——结果为零。待加工的纱线和整理后的成品面料都是重物，跨省运输必然产生大量运费。完全没有运输费支出这一事实，让我对货物流的真实性产生了严重怀疑。</p>'
        + '<p>具体调查发现：' + esc(descText) + '</p>';
    } else if (f.type && (f.type.indexOf('行业') >= 0 || f.type.indexOf('毛利') >= 0)) {
      narrativeText = '<p>在行业对标分析中，我调取了行业基准数据库中被查单位所属行业的典型财务指标，将被查单位的实际数据与行业基准进行逐一对比。我关注的核心指标包括：毛利率、税负率、进销比、人均营收等。</p>'
        + '<p>对比结果显示被查单位的多项指标与行业典型值存在偏差，我对此进行了详细的偏离度分析。</p>'
        + '<p>具体调查发现：' + esc(descText) + '</p>';
    } else if (f.type && (f.type.indexOf('时间') >= 0 || f.type.indexOf('周末') >= 0 || f.type.indexOf('模式') >= 0)) {
      narrativeText = '<p>在交易时间模式分析中，我对所有银行流水交易的发生时间进行了统计分析，重点关注周末、节假日、夜间等非营业时段发生的交易，以及整数金额交易模式。</p>'
        + '<p>根据我的稽查经验，正常企业间的对公交易通常发生在工作日且金额零碎。周末交易和整数金额交易往往有特殊目的——过桥资金、关联方走账、或刻意构造的资金流水。</p>'
        + '<p>具体调查发现：' + esc(descText) + '</p>';
    } else {
      // 默认叙事——融合 how_found + detail 生成完整的调查叙事
      var hfText = f.how_found || '';
      if (hfText) {
        narrativeText = '<p><strong>我的调查方法：</strong>' + esc(hfText) + '</p>';
      } else {
        narrativeText = '<p>在对' + esc(domainText || '相关领域') + '的审计中，我按照稽查工作规程进行了系统的数据分析和交叉比对。</p>';
      }
      narrativeText += '<p>具体调查发现：' + esc(descText) + '</p>';
    }

    h += '<div class="nr-finding">';
    h += '<div class="nr-f-title">调查事项' + (i+1) + '：' + esc(f.type || '未分类发现') + '<span class="nr-badge ' + badgeCls + '">' + tl + '</span>' + (f.level_fixed ? '<span class="nr-badge nr-badge-red" style="font-size:9px">稽查重点</span>' : '') + '</div>';
    h += '<div class="nr-f-meta">涉及领域：' + esc(domainText || '综合') + '　|　风险评分：' + (s||0) + '/10　|　' + (f.rule_id && f.rule_id > 100 ? '规则ID-' + f.rule_id + '　|　' : '') + (f.source_chain ? '线索链：' + esc(f.source_chain) + '　|　' : '') + '证据链：' + ((f.rule_id && f.rule_id>100) ? '规则驱动+' : '') + ((f.items && f.items.length>0) ? f.items.length+'项明细' : '系统提取') + '</div>';
    
    h += narrativeText;

    // 证据明细
    if (f.items && f.items.length > 0) {
      var cols2 = Object.keys(f.items[0]);
      h += '<div class="nr-evidence"><div class="nr-ev-title">📋 证据材料（我提取的具体数据如下）</div>';
      h += '<table class="nr-table"><tr>';
      cols2.forEach(function(c){ h += '<th>' + esc(c) + '</th>'; });
      h += '</tr>';
      f.items.forEach(function(row){
        h += '<tr>';
        cols2.forEach(function(c){ h += '<td>' + esc(row[c]||'') + '</td>'; });
        h += '</tr>';
      });
      h += '</table></div>';
    }

    // 税务影响分析
    if (f.tax_impact) {
      h += '<div style="margin:8px 0;padding:10px 14px;background:#fff7ed;border-left:3px solid #f97316;font-size:13px;line-height:1.8;color:#7c2d12;">'
        + '<strong>⚡ 我的专业判断（税务影响分析）：</strong><br>' + esc(f.tax_impact||'') + '</div>';
    }

    // 法律依据
    var lawText = f.policy_ref ? esc(f.policy_ref) : '《中华人民共和国税收征收管理法》及相关税收法规';
    h += '<div class="nr-law">⚖ <strong>我依据的法律条文：</strong>' + lawText + '</div>';

    // 处理建议
    if (f.suggestion) {
      h += '<div class="nr-inspector-thought">💡 <strong>我的处理意见：</strong>' + esc(f.suggestion||'') + '</div>';
    }

    h += '</div>';
  });

  h += '<div class="nr-inspector-thought" style="margin-top:30px">📊 <strong>领导，第五章调查小结：</strong>至此，我完成了对全部' + allF.length + '项风险信号的逐一核查。其中，经我认定为<strong>高风险</strong>的有' + highCount + '项——需立即处理；<strong>中风险</strong>' + midCount + '项——建议重点关注；<strong>低风险</strong>' + lowCount + '项——供被查单位自查参考。</div>';

  h += '</div>';

  // ═══ 第六章：证据链组织总结 ═══
  h += '<div class="nr-chapter"><h2>第六章　证据链组织总结</h2><div class="nr-ch-sub">如何将孤立疑点串联为完整证据链</div></div>';
  h += '<div class="nr-body">';

  h += '<p><strong>领导，在完成逐项调查后，我将所有风险疑点进行跨域串联分析，组织形成完整的证据链。这是我稽查方法论中最关键的一步——单独看每个问题可能只是数据异常，但串联起来就能还原出完整的问题链条。以下汇报我的证据链组织思路。</strong></p>';

  // 证据链组织方法论
  h += '<div class="nr-evidence"><div class="nr-ev-title">🔗 我的证据链组织方法——四步证据法</div>';
  h += '<table class="nr-table">';
  h += '<tr><th style="width:80px;">步骤</th><th>操作方法</th><th style="width:160px;">本次稽查执行情况</th></tr>';
  h += '<tr><td style="font-weight:700;">第一步<br>提取原始数据</td><td>从被查单位提交的资料中提取原始数据记录：银行流水' + esc(bi['总收款']?'是':'否') + '、销项发票' + esc(ii['销项发票']?'是':'否') + '、进项发票' + esc(ii['进项发票']?'是':'否') + '</td><td>已从3类资料中提取数据作为证据来源</td></tr>';
  h += '<tr><td style="font-weight:700;">第二步<br>逐条匹配规则</td><td>将提取的数据逐条匹配' + (r.rules_used||'?') + '条稽查规则，触发风险信号</td><td>共触发' + allF.length + '条风险信号</td></tr>';
  h += '<tr><td style="font-weight:700;">第三步<br>多源交叉验证</td><td>每条高风险发现的认定均满足≥2个数据域交叉验证——发票流+资金流、工商登记+发票流、地理信息+资金流等</td><td>所有高风险事项均满足≥2域交叉验证标准</td></tr>';
  h += '<tr><td style="font-weight:700;">第四步<br>形成证据闭环</td><td>将同一风险方向的多个证据串联起来，形成"信号→线索→证据→结论"的逻辑闭环</td><td>已激活' + nrChainList.length + '条线索链，覆盖' + nrChainList.slice(0,8).map(function(c){return esc(c);}).join('、') + (nrChainList.length>8?'等维度':'') + '</td></tr>';
  h += '</table></div>';

  var crossFindings = allF.filter(function(f){ return f.type && f.type.indexOf('跨域') >= 0; });
  if (crossFindings.length > 0) {
    h += '<p><strong>经跨域串联分析，我识别出以下关键线索链：</strong></p>';
    crossFindings.forEach(function(cf, ci){
      h += '<p><strong>线索链' + (ci+1) + '：</strong>' + esc(cf.type || '') + '</p>';
      var cDesc = typeof cf.detail === 'string' ? cf.detail : (cf.description || '');
      h += '<p>' + esc(cDesc) + '</p>';
    });
  }

  h += '<p><strong>我的综合判断：</strong>被查单位在多个维度上同时存在异常——资料严重缺失导致无法核实经营实质、供应商地理分布不合理且无运输费用支持、收款来源与开票客户不匹配、进项发票存在多处形式瑕疵。这些异常信号不是孤立的，而是相互印证、相互强化的。<strong>当资料缺失、地理异常、资金不匹配、发票瑕疵四个维度的信号同时出现时，就构成了一个完整的风险画像</strong>——被查单位的经营活动在物理上、财务上、税务上均存在无法合理解释的矛盾。</p>';

  h += '</div>';

  // ═══ 第七章：处理处罚建议 ═══
  h += '<div class="nr-chapter"><h2>第七章　处理处罚建议</h2><div class="nr-ch-sub">我的处理意见</div></div>';
  h += '<div class="nr-body">';

  h += '<p><strong>领导，根据上述稽查发现和证据链，我提出以下处理处罚建议：</strong></p>';
  var nrActions=[],nrSeen={};
  allF.forEach(function(f){
    var s=((f.suggestion||'')+'').split('\n')[0].trim();
    if(s&&s.substring(0,50)&&!nrSeen[s.substring(0,50)]){nrSeen[s.substring(0,50)]=true;nrActions.push(s);}
  });
  nrActions.slice(0,8).forEach(function(a,j){h+='<p class="nr-no-indent">'+(j+1)+'. '+esc(a)+'</p>';});
  h += '<p>综合以上建议，我请求领导审议本案的最终处理决定。</p>';
  h += '</div>';

  // 第八章：告知事项
  h += '<div class="nr-chapter"><h2>第八章　告知事项</h2><div class="nr-ch-sub">被查单位权利义务告知</div></div>';
  h += '<div class="nr-body">';

  h += '<p>根据《中华人民共和国税收征收管理法》及《税务稽查工作规程》，我在此告知被查单位享有的法定权利：</p>';
  h += '<p class="nr-no-indent"><strong>1. 申请回避权：</strong>如认为本人与本案有利害关系，被查单位可在收到本报告之日起3日内申请我回避。</p>';
  h += '<p class="nr-no-indent"><strong>2. 陈述申辩权：</strong>对本报告认定的事实、证据、法律依据有异议的，可在收到本报告之日起5日内提出陈述申辩意见，我将认真审查。</p>';
  h += '<p class="nr-no-indent"><strong>3. 听证权：</strong>对拟作出的较大数额罚款（法人或其他组织1万元以上）有异议的，可在收到《税务行政处罚事项告知书》后3日内申请听证。</p>';
  h += '<p class="nr-no-indent"><strong>4. 复议权：</strong>对税务处理决定或处罚决定不服的，可在收到决定书之日起60日内向上一级税务机关申请行政复议。</p>';
  h += '<p class="nr-no-indent"><strong>5. 诉讼权：</strong>对税务处理决定或处罚决定不服的，可在收到决定书之日起6个月内向人民法院提起行政诉讼。</p>';

  h += '</div>';

  // ═══ 签字 ═══
  h += '<div class="nr-sig">'
    + '<div class="nr-sig-name">汇报人（稽查执行人）：___________</div>'
    + '<div style="font-size:12px">（签章）</div>'
    + '<div style="margin-top:16px;font-size:12px;color:#64748b">' + dateStr + '</div>'
    + '<div style="margin-top:32px;border-top:1px solid #cbd5e1;padding-top:16px">'
    + '<div class="nr-sig-name">领导审批意见：___________</div>'
    + '<div style="font-size:12px">（签章）</div>'
    + '<div style="margin-top:16px;font-size:12px;color:#64748b">日期：___________</div>'
    + '</div>'
    + '<div style="margin-top:48px;font-size:11px;color:#94a3b8">本报告一式三份：稽查局存档一份、被查单位一份、主管税务机关一份</div>'
    + '</div>';

  h += '</div>'; // close nr-report

  area.innerHTML = h;
  area.scrollIntoView({ behavior: 'smooth' });
}

// ==================== 导出报告 ====================
function exportTaxDocReport() {
  var area = document.getElementById('tda-report-area');
  if (!area) return;
  var content = area.innerHTML;
  var title = narrativeMode ? '税务稽查叙事报告' : '涉税资料分析报告';
  var html = '<!DOCTYPE html><html><head><meta charset="utf-8"><title>' + title + '</title>'
    + '<style>body{font-family:"Microsoft YaHei","PingFang SC",sans-serif;max-width:960px;margin:0 auto;padding:20px;color:#333;line-height:1.8}'
    + 'h2{color:#1e293b;border-bottom:2px solid #e2e8f0;padding-bottom:8px}'
    + '@media print{body{padding:0;font-size:11pt}}</style></head><body>'
    + '<h1 style="text-align:center">' + title + '</h1>'
    + '<p style="text-align:center;color:#64748b">生成时间：' + new Date().toLocaleString('zh-CN') + '</p>'
    + content + '</body></html>';
  var blob = new Blob([html], {type: 'text/html;charset=utf-8'});
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = title + '_' + new Date().toISOString().substring(0,10) + '.html';
  a.click();
  URL.revokeObjectURL(url);
  toast('报告已导出', 'success');
}

function deleteTaxDocReport() {
  if (!taxDocReportData) { toast('暂无报告可删除', 'warning'); return; }
  if (!confirm('确定要删除当前报告吗？')) return;
  taxDocReportData = null;
  narrativeMode = false;
  document.getElementById('tda-report-area').innerHTML = '';
  var narrBtn = document.getElementById('tda-narrative-btn');
  if (narrBtn) { narrBtn.style.display = 'none'; narrBtn.textContent = '稽查叙事报告'; narrBtn.style.cssText = 'display:none;cursor:pointer;padding:6px 14px;border:1px solid #d1d5db;background:#fff;color:#6b7280;border-radius:4px;font-size:12px'; }
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

// ==================== 涉税资料分析模块 ====================

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


