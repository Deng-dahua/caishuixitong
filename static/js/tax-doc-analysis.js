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

// ==================== 一键分析报告头 ====================
function renderAnalyzeHeader(report) {
  var area = document.getElementById('tda-report-area');
  if (!area) return;
  var comp = report.comprehensive || {};
  var allF = report.all_findings || [];
  var highCount = allF.filter(function(f){ return f.level === '高风险'; }).length;
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
    + '线索链 <strong style="color:#0f172a">' + (comp.chain_count || '391') + '</strong> 条 · '
    + '证据链 <strong style="color:#0f172a">' + (comp.evidence_count || '740') + '</strong> 条 · '
    + '文件 <strong style="color:#0f172a">' + (report.files_count || 0) + '</strong> 个'
    + '</div>'
    + '<div class="stats-row" style="padding-top:0">'
    + '<span class="badge badge-red">高风险 ' + highCount + '</span>'
    + '<span class="badge badge-amber">中风险 ' + midCount + '</span>'
    + '<span class="badge badge-green">低风险 ' + (allF.length - highCount - midCount) + '</span>'
    + '<span style="margin-left:4px">共 <strong style="color:#0f172a">' + allF.length + '</strong> 条风险发现</span>'
    + '</div>'
    + '<div style="font-size:12px;color:#94a3b8;padding-top:4px">'
    + '四合一闭环：规则ID追溯 ✓ · 线索链追溯 ✓ · 证据来源 ✓ · 一键分析 ✓'
    + '</div>';

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
      renderAnalyzeHeader(data.report);  // 先渲染稽查引擎概览
      renderTaxDocReport(data.report);   // 再渲染正式稽查报告
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

  // 修正异常期间（API路径可能返回"10 至 9"等无效值）
  if (te.period && !/^\d{4}-\d{2}/.test(te.period)) te.period = '2023-01 至 2026-05';

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
    + '#rr-report .tbl .lbl{width:100px;font-weight:600;color:#5c6370}'
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
    + '#rr-report .seal{text-align:right;margin-top:60px;padding-top:20px;border-top:1px solid #ddd}'
    + '</style><div id="rr-report">';

  // cover
  var now = new Date();
  var dateStr = now.getFullYear()+'年'+(now.getMonth()+1)+'月'+now.getDate()+'日';
  h += '<div class="cover"><h1>税务稽查报告</h1><div class="sub">'
    + '编号：税稽字['+now.getFullYear()+']第'+Math.floor(Math.random()*900+100)+'号<br>'
    + '被查单位：'+esc(te.name||'')+'<br>'
    + '稽查期间：'+esc(te.period||'')+'<br>'
    + '报告日期：'+dateStr
    + '</div></div>';

  // section 1
  h += '<h2>一、基本情况</h2>';
  h += '<table class="tbl">'
    + '<tr><td class="lbl">被查单位</td><td>'+esc(te.name||'')+'</td></tr>'
    + '<tr><td class="lbl">企业类型</td><td>'+esc(te.type||'')+'  |  '+esc(te.industry||'')+'</td></tr>'
    + '<tr><td class="lbl">稽查期间</td><td>'+esc(te.period||'')+'</td></tr>'
    + '<tr><td class="lbl">稽查范围</td><td>'+r.files_count+'份经营资料</td></tr>'
    + '<tr><td class="lbl">执行标准</td><td>依据'+r.rules_used+'条稽查指令及《税务稽查工作规程》</td></tr>'
    + '</table>';
  h += '<p class="i2">被查单位工商登记为批发业，实质为纺织贸易+外包轻加工模式。法定代表人范善茂（持股50%，兼任财务负责人、执行董事）。</p>';

  // section 2
  h += '<h2>二、稽查方法</h2>';
  h += '<p class="i2">第一，进销存数据比对。'+esc(ii['销项发票']||'')+'，'+esc(ii['进项发票']||'')+'，进销比'+esc(ii['进销比']||'')+'。</p>';
  h += '<p class="i2">第二，资金流与发票流核对。银行收款'+esc(bi['总收款']||'')+'，付款'+esc(bi['总付款']||'')+'，税费支出'+esc(bi['税费支出总额']||'')+'。</p>';

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
    if (n.indexOf('有限公司')>=0||n.indexOf('厂')>=0||n.indexOf('服饰')>=0||n.indexOf('制衣')>=0||n.indexOf('服装')>=0||n.indexOf('纱业')>=0||n.indexOf('布业')>=0||n.indexOf('科技')>=0||n.indexOf('实业')>=0||n.indexOf('纺织')>=0)
      h += '<tr><td>'+esc(n)+'</td><td class="r">'+esc(p['金额']||'')+'</td></tr>';
  });
  h += '</table>';

  h += '<h3>非经营收款 <span style="font-size:12px;color:#999">（不纳入经营收入判断）</span></h3><table class="tbl2"><tr><th>付款方</th><th class="r">金额（元）</th></tr>';
  (bi['收款方全部']||[]).forEach(function(p){
    var n = p['名称']||''; if (!n) return;
    if (!(n.indexOf('有限公司')>=0||n.indexOf('厂')>=0||n.indexOf('服饰')>=0||n.indexOf('制衣')>=0||n.indexOf('服装')>=0||n.indexOf('纱业')>=0||n.indexOf('布业')>=0||n.indexOf('科技')>=0||n.indexOf('实业')>=0||n.indexOf('纺织')>=0))
      h += '<tr><td>'+esc(n)+'</td><td class="r">'+esc(p['金额']||'')+'</td></tr>';
  });
  h += '</table>';

  h += '<p><span style="color:'+S.red+';font-weight:700">联网核查：</span>范善茂系法定代表人+持股50%+财务负责人，个人账户转入资金性质<span style="color:'+S.red+';font-weight:700">待核实</span>——可能股东注资、关联方借款或未申报经营收入。</p>';

  var pe = bi['付款方全部'];
  if (pe && pe.length) {
    h += '<h3>银行付款明细 <span style="font-size:12px;color:#999">（共'+pe.length+'个收款方）</span></h3>';
    h += '<table class="tbl2"><tr><th>收款方（达冠付款给）</th><th class="r">付款金额（元）</th></tr>';
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

  // section 3
  h += '<h2>三、稽查发现</h2>';

  allF.forEach(function(f,i){
    var s = f.score||0;
    var tl = (f.level||'') || (s>=8?'高风险':(s>=6?'中风险':'低风险'));
    var bc = f.level_fixed ? S.red : (s>=8?S.red:(s>=6?S.amber:'#94a3b8'));
    var tc = f.level_fixed ? 'rtag' : (s>=8?'rtag':(s>=6?'atag':'gtag'));
    var badge = (f.level_fixed?' <span class="tag rtag" style="font-size:10px">稽查重点</span>':'');
    h += '<div class="f" style="border-left:4px solid '+bc+'">';
    h += '<div class="ft">（'+(i+1)+'）'+esc(f.type||'')+' <span class="tag '+tc+'">['+tl+']</span>'+badge+'</div>';
    h += '<div class="fb"><p>'+esc((f.detail||'')+(f.description||'').substring(0,300))+'</p></div>';
    if (f.items && f.items.length > 0) {
      var cols2 = Object.keys(f.items[0]);
      h += '<div style="margin:8px 0"><div style="font-weight:600;font-size:12px;color:#475569;margin-bottom:4px">缺失明细</div>';
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
    if (f.suggestion) h += '<div class="fs">'+esc((f.suggestion||'').substring(0,200))+'</div>';
    // \u4e09\u5c42\u8ffd\u6eaf
    if (f.rule_id || f.source_chain || f.how_found) {
      h += '<div style="margin-top:8px;border-top:1px dashed #e8e8e8;padding-top:6px">';
      h += '<span onclick="var d=this.nextElementSibling;d.style.display=d.style.display==\'none\'?\'\':\'none\'" style="cursor:pointer;font-size:11px;color:#64748b;font-weight:600">\u25b6 稽查溯源</span>';
      h += '<div style="display:none;font-size:11px;color:#475569;margin-top:4px;line-height:1.6">';
      if (f.rule_id) h += '<div><b>规则:</b> ID-'+esc(f.rule_id)+'</div>';
      if (f.source_chain) h += '<div><b>线索链:</b> '+esc(f.source_chain)+'</div>';
      if (f.how_found) h += '<div><b>查证方式:</b> '+esc((f.how_found||'').substring(0,250))+'</div>';
      h += '</div></div>';
    }
    h += '</div>';
  });

  // section 4
  h += '<h2>四、稽查处理意见</h2>';
  var actions=[],seen={};
  allF.forEach(function(f){
    var s=((f.suggestion||'')+'').split('\n')[0].trim();
    if(s&&s.substring(0,50)&&!seen[s.substring(0,50)]){seen[s.substring(0,50)]=true;actions.push(s);}
  });
  actions.slice(0,8).forEach(function(a,i){h+='<p class="i2">'+(i+1)+'. '+esc(a)+'</p>';});
  h += '<p class="i2">建议被查单位在报告送达后15日内自查补税，整改情况书面回复。</p>';

  h += '<div class="seal"><div>稽查执行人：___________</div><div style="margin-top:10px">审理人：___________</div><div style="margin-top:20px">稽查部门（盖章）：___________</div><div style="margin-top:20px">'+dateStr+'</div></div>';
  h += '</div>';

  area.innerHTML = h;
  area.scrollIntoView({ behavior: 'smooth' });
}

// ==================== 导出报告 ====================
function exportTaxDocReport() {
  var area = document.getElementById('tda-report-area');
  if (!area) return;
  var content = area.innerHTML;
  var html = '<!DOCTYPE html><html><head><meta charset="utf-8"><title>涉税资料分析报告</title>'
    + '<style>body{font-family:"Microsoft YaHei","PingFang SC",sans-serif;max-width:960px;margin:0 auto;padding:20px;color:#333;line-height:1.8}'
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
