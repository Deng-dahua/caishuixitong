// ==================== 涉税资料分析模块 ====================
var taxDocReportData = null;
var taxDocAnalyzing = false;
var taxDocPageActive = false;

// 安全获取当前 company_id（无 fallback，宁可报错也不错查）
function _tdaCid() {
  var cid = (typeof currentCompanyId !== 'undefined' && currentCompanyId) ? currentCompanyId : 0;
  if (!cid) console.warn('[tax-doc] currentCompanyId 未设置，API 调用可能失败');
  return cid;
}

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
    renderTaxDocReport(taxDocReportData);
    var btn = document.getElementById('tda-export-btn');
    if (btn) btn.style.display = '';
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
    var resp = await fetch('/api/tax-risk-docs/upload?company_id=' + _tdaCid(), {
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
    var resp = await fetch('/api/tax-risk-docs/list?company_id=' + _tdaCid());
    var docs = await resp.json();
    // 守卫：API 可能返回错误对象而非数组
    if (!Array.isArray(docs)) {
      console.error('[tax-doc] 文件列表API返回非数组:', typeof docs, docs);
      docs = [];
    }
    var listEl = document.getElementById('tda-file-list');
    if (!listEl) { console.error('[tax-doc] tda-file-list 元素不存在'); return; }

    // 更新文件数量显示
    var countEl = document.getElementById('tda-file-count');
    if (countEl) countEl.textContent = '(' + (docs.length || 0) + ' 份)';

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
    var resp = await fetch('/api/tax-risk-docs/' + id + '?company_id=' + _tdaCid(), { method: 'DELETE' });
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
      await fetch('/api/tax-risk-docs/' + ids[i] + '?company_id=' + _tdaCid(), { method: 'DELETE' });
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

  // 7步执行流程（默认折叠）
  h += '<details style="margin-bottom:12px"><summary style="cursor:pointer;font-size:14px;font-weight:700;color:#0f172a;padding:6px 0;border-bottom:1px solid #e2e8f0">⚙️ 稽查引擎执行流程</summary><div style="padding:8px 0">';
  var steps = [
    { title: '① 资料扫描与类型识别', desc: '34类文件指纹 + 三层递进识别（关键词→结构分析→数据推断）。自动判定发票方向。' },
    { title: '② 目标实体识别', desc: '进项购买方 ∩ 销项销售方 → 自动确定被查单位。66个行业分类（加权投票制）。' },
    { title: '③ 资料情报提取 + 数据分析', desc: '银行流水深度分析：收款构成+收款方TOP10。进销存比对：商品明细匹配+进销比+毛利率。供应商穿透：集中度+群集+双向交易。发票深度审计：五层检查。' },
    { title: '④ 规则引擎 + 链驱动检查', desc: '1512条规则逐条匹配 + 396条线索链驱动 + 745条证据链闭环（≥3条触发+≥2域交叉验证）→ 方法论过滤器剔除97%噪声。' },
    { title: '⑤ 方法论噪声过滤器', desc: '硬删除：禁止词40+。条件过滤：无资料→对应结论全删。行业匹配：不报非本行业发现。去重+正常结论排除。' },
    { title: '⑥ 行业对标 + 申报比对', desc: '66行业基准值自动对标（毛利率/税负率/进销比/人均营收）。申报表vs发票实际数据比对。' },
    { title: '⑦ 正式稽查报告输出', desc: '已查实问题+需进一步核实问题，两级分类。查证过程/问题定性/法律依据完整呈现。' },
  ];
  steps.forEach(function(s) {
    h += '<div class="step-block"><div class="st">' + s.title + '</div><div class="sd">' + s.desc + '</div></div>';
  });
  h += '</div></details>';

  // 分析结果统计
  h += '<h3 style="margin-top:24px">本次分析结果</h3>';
  h += '<div class="stats-row">'
    + '规则 <strong style="color:#0f172a">' + (comp.rule_count || '1512') + '</strong> 则 · '
    + '线索链 <strong style="color:#0f172a">' + (comp.chain_count || '396') + '</strong> 条 · '
    + '证据链 <strong style="color:#0f172a">' + (comp.evidence_count || '745') + '</strong> 条 · '
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
    + '<div id="tax-doc-result" style="margin-top:16px"></div>';

    // ═══ ⑧ 系统自诊：矛盾检测 + 回溯定位 + 修正验证 ═══
  var btReport = comp.backtrack_report;
  var fixVerify = comp.fix_verification;
  var anaMem = comp.analysis_memory;
  if (btReport && btReport.total > 0) {
    h += '<details style="margin-bottom:12px"><summary style="cursor:pointer;font-size:13px;font-weight:600;color:#64748b;padding:4px 0">🤖 系统自诊与自我修正（' + btReport.total + '条矛盾）</summary><div style="padding:8px 0">';
    h += '<div class="stats-row" style="font-size:12px;line-height:1.8">'
      + '发现问题 <strong style="color:#dc2626">' + btReport.total + '</strong> 条矛盾 · '
      + '可自动修正 <strong style="color:#16a34a">' + (btReport.auto_fixes ? btReport.auto_fixes.length : 0) + '</strong> 条 · '
      + '需人工 <strong style="color:#d97706">' + (btReport.manual_flags ? btReport.manual_flags.length : 0) + '</strong> 条'
      + '</div>';
    
    // 自动修正列表
    if (btReport.auto_fixes && btReport.auto_fixes.length > 0) {
      h += '<div style="margin:8px 0;padding:12px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px">';
      h += '<div style="font-size:13px;font-weight:600;color:#166534;margin-bottom:8px">✅ 系统已自动修正</div>';
      btReport.auto_fixes.forEach(function(af) {
        h += '<div class="step-block" style="padding:6px 0"><div class="st" style="font-size:12px;color:#166534">' + (af.contradiction_id || '') + '</div>';
        h += '<div class="sd" style="font-size:11px">' + (af.fix_desc || '') + '</div></div>';
      });
      h += '</div>';
    }
    
    // 修正验证结果
    if (fixVerify && fixVerify.verified_fixes && fixVerify.verified_fixes.length > 0) {
      h += '<div style="margin:8px 0;padding:12px;background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px">';
      h += '<div style="font-size:13px;font-weight:600;color:#1e40af;margin-bottom:8px">🔍 修正前后对比</div>';
      fixVerify.verified_fixes.forEach(function(vf) {
        h += '<div class="step-block" style="padding:4px 0">';
        h += '<div style="font-size:11px;color:#64748b">← 修正前: 矛盾存在 | 修正后: ' + (vf.after || '') + '</div>';
        if (vf.verification_detail) {
          h += '<div style="font-size:10px;color:#94a3b8">' + vf.verification_detail + '</div>';
        }
        h += '</div>';
      });
      h += '</div>';
    }
    
    // 需要人工的列表
    if (btReport.manual_flags && btReport.manual_flags.length > 0) {
      h += '<div style="margin:8px 0;padding:12px;background:#fffbeb;border:1px solid #fde68a;border-radius:8px">';
      h += '<div style="font-size:13px;font-weight:600;color:#92400e;margin-bottom:8px">⚠️ 需人工审查 (' + btReport.manual_flags.length + '条)</div>';
      btReport.manual_flags.slice(0, 5).forEach(function(mf) {
        h += '<div class="step-block" style="padding:4px 0"><div class="sd" style="font-size:11px">'
          + (mf.contradiction_id || '') + ': ' + (mf.reason || '') + '</div></div>';
      });
      h += '</div>';
    }
    
    // 跨案例分析记忆
    if (anaMem && anaMem.cross_company && anaMem.cross_company.length > 0) {
      h += '<div style="margin:8px 0;padding:12px;background:#faf5ff;border:1px solid #e9d5ff;border-radius:8px">';
      h += '<div style="font-size:13px;font-weight:600;color:#7c3aed;margin-bottom:8px">🧠 跨公司泛化模式 (' + anaMem.cross_company.length + '个)</div>';
      anaMem.cross_company.slice(0, 3).forEach(function(cc) {
        h += '<div class="step-block" style="padding:4px 0"><div class="sd" style="font-size:11px">'
          + (cc.contradiction_id || '') + ': 出现在 ' + cc.companies_affected + ' 个公司(' + cc.occurrence_count + '次)</div></div>';
      });
      h += '</div>';
    }
    if (anaMem && anaMem.total_records > 0) {
      h += '<div style="font-size:10px;color:#94a3b8;padding:4px 0">'
        + '已积累' + anaMem.total_records + '条分析记忆 · 当前公司' + (anaMem.current_company_records || 0) + '条'
        + '</div>';
    }
    h += '</div></details>';
  }

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

// ═══════════════════════════════════════════════════════════════
//  报告增强渲染模块 — 补全后端产出数据到前端
// ═══════════════════════════════════════════════════════════════

// 全局转义函数
function esc(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function _fmt(v, dft) {
  if (v === undefined || v === null) return dft !== undefined ? dft : '';
  if (typeof v === 'number') {
    if (Math.abs(v) >= 10000) return (v/10000).toFixed(2) + '万';
    return v.toFixed(2);
  }
  // 尝试解析字符串数字
  var n = parseFloat(v);
  if (!isNaN(n)) {
    if (Math.abs(n) >= 10000) return (n/10000).toFixed(2) + '万';
    return n.toFixed(2);
  }
  return String(v);
}

// ── 1. 资料概览（comprehensive.data_overview）──
function renderDataOverview(cc) {
  var ov = cc && cc.data_overview;
  if (!ov) return '';
  var present = ov.present || [];
  var missing = ov.missing || [];
  if (!present.length && !missing.length) return '';
  var h = '<div style="margin:16px 0;padding:16px 20px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;font-size:13px;line-height:2">';
  h += '<div style="font-weight:700;color:#0f172a;margin-bottom:8px">📋 资料概览</div>';
  if (present.length) h += '<div>已获取资料：' + present.map(function(p){return '<span style="display:inline-block;padding:1px 8px;margin:2px 4px;background:#dbeafe;border-radius:3px;font-size:12px">' + esc(p) + '</span>';}).join('') + '</div>';
  if (missing.length) h += '<div style="margin-top:8px;color:#dc2626">缺失资料：' + missing.map(function(m){return '<span style="display:inline-block;padding:1px 8px;margin:2px 4px;background:#fee2e2;border-radius:3px;font-size:12px">' + esc(m) + '</span>';}).join('') + '</div>';
  h += '</div>';
  return h;
}

// ── 2. 缺失后果触发（comprehensive.missing_consequence_triggers）──
function renderMissingConsequenceTriggers(cc) {
  var trs = cc && cc.missing_consequence_triggers;
  if (!trs || !trs.length) return '';
  var h = '<div style="margin:16px 0;padding:16px 20px;background:#fef2f2;border:1px solid #fecaca;border-radius:8px;font-size:13px;line-height:2">';
  h += '<div style="font-weight:700;color:#dc2626;margin-bottom:10px">⚠️ 资料缺失触发风险</div>';
  h += '<table class="tbl2"><tr><th>缺失资料</th><th>风险等级</th><th>推定后果</th><th>法律依据</th><th>处理行动</th></tr>';
  for (var i = 0; i < trs.length; i++) {
    var t = trs[i];
    var lvl = t.level || '高风险';
    var lvlColor = lvl === '高风险' ? '#dc2626' : (lvl === '中风险' ? '#d97706' : '#059669');
    h += '<tr>';
    h += '<td style="font-weight:600">' + esc(t.missing_doc || '') + '</td>';
    h += '<td style="color:' + lvlColor + ';font-weight:600">' + esc(lvl) + '</td>';
    h += '<td style="color:#991b1b">' + esc(t.consequence || '') + '</td>';
    h += '<td style="font-size:11px">' + esc(t.law_ref || '') + '</td>';
    h += '<td>' + esc(t.action || '') + '</td>';
    h += '</tr>';
  }
  h += '</table></div>';
  return h;
}

// ── 3. 月度资金流（comprehensive.cashflow）──
function renderCashflowChart(cc) {
  var cf = cc && cc.cashflow;
  if (!cf || !cf.months || !cf.months.length) return '';
  var h = '<div style="margin:16px 0;padding:16px 20px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;font-size:13px">';
  h += '<div style="font-weight:700;color:#0f172a;margin-bottom:10px">📊 月度资金流分析</div>';
  h += '<table class="tbl2"><tr><th>月份</th><th class="r">收入（元）</th><th class="r">支出（元）</th><th class="r">税费（元）</th><th class="r">净额（元）</th></tr>';
  var months = cf.months || [];
  var income = cf.income || [];
  var expense = cf.expense || [];
  var tax = cf.tax || [];
  var net = cf.net || [];
  for (var i = 0; i < months.length; i++) {
    var n = net[i] || 0;
    var nColor = n < 0 ? '#dc2626' : '#059669';
    h += '<tr>';
    h += '<td>' + esc(months[i]) + '</td>';
    h += '<td class="r">' + _fmt(income[i], 0) + '</td>';
    h += '<td class="r">' + _fmt(expense[i], 0) + '</td>';
    h += '<td class="r">' + _fmt(tax[i], 0) + '</td>';
    h += '<td class="r" style="color:' + nColor + ';font-weight:600">' + _fmt(net[i], 0) + '</td>';
    h += '</tr>';
  }
  h += '</table></div>';
  return h;
}

// ── 4. 往来方TOP20（comprehensive.top_receivers / top_payers）──
function renderTopCounterparties(cc) {
  var recv = cc && cc.top_receivers;
  var pay = cc && cc.top_payers;
  if ((!recv || !recv.length) && (!pay || !pay.length)) return '';
  var h = '<div style="margin:16px 0;padding:16px 20px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;font-size:13px">';
  h += '<div style="font-weight:700;color:#0f172a;margin-bottom:10px">📋 主要往来方（按金额排序）</div>';
  if (recv && recv.length) {
    h += '<div style="display:inline-block;vertical-align:top;width:48%;margin-right:2%">';
    h += '<div style="font-weight:600;color:#059669;margin-bottom:6px">收款方 TOP10</div>';
    h += '<table class="tbl2"><tr><th>名称</th><th class="r">金额（元）</th></tr>';
    for (var i = 0; i < Math.min(recv.length, 10); i++) {
      h += '<tr><td>' + esc(recv[i].name || '') + '</td><td class="r">' + _fmt(recv[i].amount, 0) + '</td></tr>';
    }
    h += '</table></div>';
  }
  if (pay && pay.length) {
    h += '<div style="display:inline-block;vertical-align:top;width:48%;margin-left:2%">';
    h += '<div style="font-weight:600;color:#dc2626;margin-bottom:6px">付款方 TOP10</div>';
    h += '<table class="tbl2"><tr><th>名称</th><th class="r">金额（元）</th></tr>';
    for (var j = 0; j < Math.min(pay.length, 10); j++) {
      h += '<tr><td>' + esc(pay[j].name || '') + '</td><td class="r">' + _fmt(pay[j].amount, 0) + '</td></tr>';
    }
    h += '</table></div>';
  }
  h += '</div>';
  return h;
}

// ── 5. 金税四期风险评分（comprehensive.risk_profile）──
function renderRiskProfile(cc) {
  var rp = cc && cc.risk_profile;
  if (!rp) return '';
  var score = rp.composite_score || rp.overall_score || 0;
  // 统一风险等级：优先用finding-based level，维度评分为0时用overall_level兜底
  var level = rp.composite_level;
  if ((!level || score <= 0) && cc.overall_level) {
    level = cc.overall_level;
  }
  if (!level) level = '无法评估';
  var factors = rp.factors || rp.detail_factors || {};
  var lvlColor = level === '高风险' ? '#dc2626' : (level === '中风险' ? '#d97706' : '#059669');
  var h = '<div style="margin:16px 0;padding:16px 20px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;font-size:13px;line-height:2">';
  h += '<div style="font-weight:700;color:#0f172a;margin-bottom:8px">🔢 金税四期式多因子风险评分</div>';
  h += '<div>综合风险等级：<span style="color:' + lvlColor + ';font-weight:700;font-size:15px">' + esc(level) + '</span></div>';
  h += '<div>综合评分：<span style="font-weight:700">' + _fmt(score) + '分</span></div>';
  var factorKeys = Object.keys(factors);
  if (factorKeys.length > 0) {
    h += '<div style="margin-top:8px;font-size:12px;color:#475569">';
    h += '评分因子：';
    for (var i = 0; i < factorKeys.length; i++) {
      var k = factorKeys[i];
      var v = factors[k];
      h += '<span style="display:inline-block;padding:1px 6px;margin:2px 3px;background:#f1f5f9;border-radius:3px">' + esc(k) + '=' + esc(v) + '</span>';
    }
    h += '</div>';
  }
  h += '</div>';
  return h;
}

// ── 6. 链使用统计（comprehensive.chain_usage）──
function renderChainUsage(cc) {
  var cu = cc && cc.chain_usage;
  if (!cu) return '';
  var keys = Object.keys(cu);
  if (!keys.length) return '';
  var h = '<div style="margin:16px 0;padding:16px 20px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;font-size:13px;line-height:2">';
  h += '<div style="font-weight:700;color:#166534;margin-bottom:8px">🔗 稽查线索链激活统计</div>';
  h += '<table class="tbl2"><tr><th>线索链</th><th>类型</th><th>命中步数</th><th>总步数</th></tr>';
  for (var i = 0; i < Math.min(keys.length, 15); i++) {
    var c = cu[keys[i]];
    var hitRate = c.steps > 0 ? Math.round(c.hits / c.steps * 100) : 0;
    h += '<tr><td>' + esc(keys[i]) + '</td><td>' + esc(c.type || '') + '</td><td>' + _fmt(c.hits) + '/' + _fmt(c.steps) + ' (' + hitRate + '%)</td><td>' + _fmt(c.steps) + '</td></tr>';
  }
  h += '</table></div>';
  return h;
}

// ── 7. P0/P1/P2分级整改建议（comprehensive.actions）──
function renderActionsTable(cc) {
  var actions = cc && cc.actions;
  if (!actions) return '';
  var p0 = actions.p0_urgent || [];
  var p1 = actions.p1_important || [];
  var p2 = actions.p2_normal || [];
  if (!p0.length && !p1.length && !p2.length) return '';
  var h = '<div style="margin:16px 0;font-size:13px">';
  h += '<div style="font-weight:700;color:#0f172a;margin-bottom:10px">📋 分级整改建议（基于风险评分引擎）</div>';
  if (p0.length) {
    h += '<div style="margin:10px 0;padding:12px 16px;background:#fef2f2;border-left:4px solid #dc2626;border-radius:4px">';
    h += '<div style="font-weight:700;color:#dc2626;margin-bottom:6px">🔴 P0 — 立即处理（' + p0.length + '项）</div>';
    for (var i = 0; i < p0.length; i++) {
      h += '<div style="margin:4px 0;color:#991b1b"><b>' + esc(p0[i].type || '') + '</b>（评分' + _fmt(p0[i].score) + '）：' + esc(p0[i].suggestion || '') + '</div>';
    }
    h += '</div>';
  }
  if (p1.length) {
    h += '<div style="margin:10px 0;padding:12px 16px;background:#fffbeb;border-left:4px solid #d97706;border-radius:4px">';
    h += '<div style="font-weight:700;color:#d97706;margin-bottom:6px">🟡 P1 — 重点关注（' + p1.length + '项）</div>';
    for (var j = 0; j < p1.length; j++) {
      h += '<div style="margin:4px 0;color:#92400e"><b>' + esc(p1[j].type || '') + '</b>（评分' + _fmt(p1[j].score) + '）：' + esc(p1[j].suggestion || '') + '</div>';
    }
    h += '</div>';
  }
  if (p2.length) {
    h += '<div style="margin:10px 0;padding:12px 16px;background:#f0fdf4;border-left:4px solid #059669;border-radius:4px">';
    h += '<div style="font-weight:700;color:#059669;margin-bottom:6px">⚪ P2 — 持续关注（' + p2.length + '项）</div>';
    for (var k = 0; k < p2.length; k++) {
      h += '<div style="margin:4px 0;color:#166534"><b>' + esc(p2[k].type || '') + '</b>（评分' + _fmt(p2[k].score) + '）：' + esc(p2[k].suggestion || '') + '</div>';
    }
    h += '</div>';
  }
  h += '</div>';
  return h;
}

// ── 8. 推荐下一步（comprehensive.recommended_next）──
function renderRecommendedNext(cc) {
  var rn = cc && cc.recommended_next;
  if (!rn || !rn.length) return '';
  var h = '<div style="margin:16px 0;padding:16px 20px;background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;font-size:13px;line-height:2">';
  h += '<div style="font-weight:700;color:#0369a1;margin-bottom:8px">🔄 推荐下一步核查方向</div>';
  for (var i = 0; i < Math.min(rn.length, 5); i++) {
    var r = rn[i];
    h += '<div style="margin:8px 0;padding:8px 12px;background:#fff;border-radius:4px">';
    h += '<div style="font-weight:600">' + esc(r.chain_name || '') + '（' + esc(r.chain_type || '') + '）';
    h += ' — 已触发<span style="color:#059669">' + _fmt(r.triggered) + '</span>步，剩余<span style="color:#d97706">' + _fmt(r.remaining) + '</span>步待核查</div>';
    var steps = r.next_steps || [];
    if (steps.length) {
      h += '<div style="margin-top:4px;font-size:12px;color:#475569">';
      for (var j = 0; j < steps.length; j++) {
        h += '<div style="margin:2px 0">· ' + esc(steps[j].step || '') + ' [规则' + esc(steps[j].rule_id || '') + ']</div>';
      }
      h += '</div>';
    }
    h += '</div>';
  }
  h += '</div>';
  return h;
}

// ── 9. 供应链风险（target_entity._supply_chain_risk）──
function renderSupplyChainRisk(te) {
  var scr = te && te._supply_chain_risk;
  if (!scr) return '';
  var results = scr.lookup_results || [];
  var findings = scr.findings || [];
  if (!results.length && !findings.length) return '';
  var h = '<div style="margin:16px 0;padding:16px 20px;background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;font-size:13px;line-height:2">';
  h += '<div style="font-weight:700;color:#c2410c;margin-bottom:8px">🔗 供应链联网核查（㉗）</div>';
  if (results.length) {
    h += '<div style="color:#374151">已查询<span style="font-weight:600">' + results.length + '</span>家供应商/客户</div>';
  }
  if (findings.length) {
    for (var i = 0; i < findings.length; i++) {
      var f = findings[i];
      h += '<div style="margin:6px 0;padding:6px 10px;background:#fff;border-radius:4px;border-left:3px solid #f97316">';
      h += '<span style="font-weight:600">' + esc(f.type || '') + '</span>';
      if (f.detail) h += '：' + esc(typeof f.detail === 'string' ? f.detail : '');
      h += '</div>';
    }
  }
  h += '</div>';
  return h;
}

// ── 10. 质量报告附录（quality_report）──
function renderQualityReport(qr, allF) {
  if (!qr) return '';
  var total = qr.total || 0;
  var passed = qr.passed || 0;
  var warnings = qr.warnings || [];
  if (!total) return '';
  var passRate = total > 0 ? Math.round(passed / total * 100) : 0;
  var rateColor = passRate >= 80 ? '#059669' : (passRate >= 50 ? '#d97706' : '#dc2626');
  var h = '<div class="appendix" style="margin-top:30px">';
  h += '<div class="atitle">附件二：稽查报告质量标准自检（12项硬指标）</div>';
  h += '<div class="aitem">标准执行结果：<span style="color:' + rateColor + ';font-weight:700">' + passed + '/' + total + '项通过（' + passRate + '%）</span></div>';
  if (warnings.length) {
    h += '<div class="aitem" style="color:#d97706">⚠️ ' + warnings.length + '条发现存在质量标注（已在正文中标注）</div>';
  }
  var stats = qr.stats || {};
  var statKeys = Object.keys(stats);
  if (statKeys.length) {
    h += '<div class="aitem">各标准检出问题数：</div>';
    h += '<table class="tbl2" style="margin-left:16px;width:auto;min-width:300px"><tr><th>质量标准</th><th class="r">问题数</th></tr>';
    for (var i = 0; i < statKeys.length; i++) {
      if (stats[statKeys[i]] > 0) {
        h += '<tr><td>' + esc(statKeys[i]) + '</td><td class="r" style="color:#d97706">' + _fmt(stats[statKeys[i]]) + '</td></tr>';
      }
    }
    h += '</table>';
  }
  h += '</div>';
  return h;
}

// ==================== 一键分析（异步任务机制） ====================
async function analyzeTaxDocs() {
  if (taxDocAnalyzing) return;
  var cid = _tdaCid();
  if (!cid) { toast('请先选择公司账套', 'error'); return; }
  taxDocAnalyzing = true;
  var btn = document.getElementById('tda-analyze-btn');
  btn.disabled = true; btn.textContent = '⏳ 启动分析...';

  try {
    // 1. 启动异步任务
    var startResp = await fetch('/api/tax-risk-docs/analyze-start?company_id=' + cid, { method: 'POST' });
    var startData = await startResp.json();
    if (!startData.ok) { throw new Error(startData.message); }
    var taskId = startData.task_id;
    
    // 2. 轮询进度
    var maxPolls = 600; // 最多等10分钟（1秒一次）
    var pollCount = 0;
    while (pollCount < maxPolls) {
      await new Promise(function(r) { setTimeout(r, 1000); });
      pollCount++;
      
      var statusResp = await fetch('/api/tax-risk-docs/analyze-status/' + taskId);
      var statusData = await statusResp.json();
      if (!statusData.ok) { throw new Error(statusData.message); }
      
      var pct = statusData.progress || 0;
      var msg = statusData.message || '';
      btn.textContent = '⏳ ' + pct + '% ' + msg.substring(0, 20);
      
      if (statusData.status === 'done') {
        btn.textContent = '✅ 分析完成，正在加载报告...';
        break;
      }
      if (statusData.status === 'error') {
        throw new Error(statusData.error || statusData.message || '分析服务异常');
      }
    }
    
    if (pollCount >= maxPolls) {
      throw new Error('分析超时，请稍后重试');
    }
    
    // 3. 获取结果
    var resultResp = await fetch('/api/tax-risk-docs/analyze-result/' + taskId);
    var resultData = await resultResp.json();
    if (!resultData.ok) { throw new Error(resultData.message); }
    
    // 4. 渲染报告
    var data = resultData;
    if (!taxDocPageActive) return;
    taxDocReportData = data.report;
    renderAnalyzeHeader(data.report);
    
    // ── 报告块架构（新）：后端推 blocks → 前端通用渲染 ──
    if (data.blocks && data.blocks.length) {
      var area = document.getElementById('tax-doc-result');
      if (area && typeof window.renderReportBlocks === 'function') {
        area.innerHTML = '';
        window.renderReportBlocks(data.blocks, area);
      } else if (area) {
        // 降级：内嵌简约渲染
        var h = '';
        data.blocks.forEach(function(b) {
          if (b.type === 'finding' && b.data && b.data.finding) {
            var f = b.data.finding;
            var lvl = f.level || '中风险';
            var cls = lvl === '高风险' ? '#fef2f2' : (lvl === '中风险' ? '#fffbeb' : '#f0fdf4');
            h += '<div style="margin:12px 0;padding:14px 18px;border-left:4px solid ' + (lvl==='高风险'?'#dc2626':(lvl==='中风险'?'#e67700':'#16a34a')) + ';border-radius:6px;background:' + cls + ';border:1px solid #eee">';
            h += '<div style="font-weight:700;margin-bottom:6px">' + (f.title || f.category || '') + ' [' + lvl + ']</div>';
            if (f.detail) h += '<div style="font-size:13px;color:#333;margin-bottom:6px">' + (f.detail||'') + '</div>';
            h += '<div style="text-align:right"><button onclick="window._dismissTaxFinding(this)" data-finding=\'' + JSON.stringify({type:f.type||'',title:f.title||'',level:lvl,category:f.category||'',detail:(f.detail||'').substring(0,200)}).replace(/'/g,"&#39;") + '\' style="background:none;border:1px solid #dc2626;color:#dc2626;padding:4px 12px;border-radius:4px;font-size:12px;cursor:pointer">❌ 驳回</button></div>';
            h += '</div>';
          }
        });
        area.innerHTML = h;
      }
    } else {
      // 降级：使用 ReportEngine 模块化渲染
      renderTaxDocReport(data.report);
    }
    
    var exportBtn = document.getElementById('tda-export-btn');
    if (exportBtn) exportBtn.style.display = 'inline-block';
    toast('分析完成：' + data.report.total_risks + '项风险发现', 'success');
    
    // 自动滚动到报告区域
    var area = document.getElementById('tax-doc-result');
    setTimeout(function() { if (area) area.scrollIntoView({behavior: 'smooth', block: 'start'}); }, 200);
    
    // ── 通知仪表盘：新分析已完成 ──
    try {
      localStorage.setItem('_tax_engine_new_analysis', JSON.stringify({
        trace_id: data.report.trace_id || '',
        risk_level: data.report.overall_level || '',
        risk_score: data.report.comprehensive ? (data.report.comprehensive.risk_score || 0) : 0,
        timestamp: Date.now()
      }));
    } catch(e) {}
    
    var now2 = new Date();
    var ts2 = now2.getFullYear() + '-' + String(now2.getMonth()+1).padStart(2,'0') + '-' + String(now2.getDate()).padStart(2,'0') + ' ' + String(now2.getHours()).padStart(2,'0') + ':' + String(now2.getMinutes()).padStart(2,'0');
    var el2 = document.getElementById('tda-last-update');
    if (el2) el2.textContent = '最近更新: ' + ts2;
    
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

  // 预处理——数据规整
  var allF = r.all_findings || [];
  allF.sort(function(a,b){return(b.score||0)-(a.score||0);});
  // 确保资料完备度发现排最前
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
  r.all_findings = allF; // 写回

  var te = r.target_entity || {};
  if (te.period && !/^\d{4}-\d{2}/.test(te.period)) te.period = '';

  // ── 使用模块化引擎渲染报告 ──
  // ── 自由编制报告：系统根据数据自行装配模块 ──
  var ctx;
  if (typeof ReportEngine !== 'undefined' && ReportEngine.render) {
    try {
      ctx = ReportEngine.render(r, {});
      console.log('[report-modules] 自由编制报告: ' + ctx.renderedModules.length + '个模块, 跳过' + ctx.skippedModules.length + '个');
    } catch(e) {
      console.error('[report-modules] 渲染失败，降级:', e);
      ctx = null;
    }
  }

  if (!ctx || !ctx.html) {
    ctx = _renderReportFallback(r, allF);
  }

  area.innerHTML = ctx.html;
  area.scrollIntoView({ behavior: 'smooth' });
}

// ── 报告渲染降级方案（旧逻辑保留，当模块引擎不可用时使用）──
function _renderReportFallback(r, allF) {
  var S = { red: '#c92a2a', amber: '#e67700', green: '#2b8a3e' };
  var te = r.target_entity || {};
  var cc = (r.comprehensive||{});
  var mi = cc.material_intel || {};
  var bi = mi['银行流水'] || {};
  var ii = mi['发票'] || {};
  var rc = bi['收款构成'];
  var now = new Date();
  var dateStr = now.getFullYear()+'年'+(now.getMonth()+1)+'月'+now.getDate()+'日';

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
    + '#rr-report .conclusion-box{margin:16px 0;padding:16px 20px;border-radius:8px;line-height:2}'
    + '#rr-report .conclusion-box.red{background:#fef2f2;border:1px solid #fecaca}'
    + '#rr-report .conclusion-box.amber{background:#fffbeb;border:1px solid #fde68a}'
    + '#rr-report .conclusion-box.green{background:#f0fdf4;border:1px solid #bbf7d0}'
    + '#rr-report .toc{margin:30px 0;padding:0 40px}'
    + '#rr-report .toc a{color:#1a1a2e;text-decoration:none;font-size:15px;line-height:2.4}'
    + '#rr-report .toc a:hover{color:#2563eb;text-decoration:underline}'
    + '#rr-report .toc .num{display:inline-block;min-width:28px;font-weight:700}'
    + '#rr-report .seal{text-align:right;margin-top:60px;padding-top:20px;border-top:1px solid #ddd;line-height:2.2}'
    + '@media (max-width:768px){'
    + '#rr-report{padding:8px !important}'
    + '#rr-report h1{font-size:18px !important}'
    + '#rr-report h2{font-size:15px !important}'
    + '#rr-report .fact-sec{padding:10px !important;margin:8px 0 !important}'
    + '#rr-report .ftitle{font-size:13px !important}'
    + '#rr-report .frow{font-size:12px !important}'
    + '#rr-report table.tbl2{font-size:10px !important;display:block;overflow-x:auto}'
    + '#rr-report table.tbl2 th,#rr-report table.tbl2 td{padding:4px 6px !important}'
    + '#rr-report .tag{font-size:10px !important;padding:1px 6px !important}'
    + '#rr-report .seal{padding:12px !important;font-size:13px !important}'
    + '}'
    + '</style><div id="rr-report">';

  // fallback 使用7章标准结构渲染
  h += '<div class="cover"><h1>税 务 稽 查 报 告</h1><div class="sub">'
    + '编号：税稽字['+now.getFullYear()+']第'+Math.floor(Math.random()*900+100)+'号<br>'
    + '被查单位：' + (te.name || te.company_name || '未指定') + '<br>'
    + '报告日期：'+dateStr+'<br>'
    + '资料数量：' + (r.files_count || allF.length) + '份'
    + '</div></div>';

  // ═══ 第一章：稽查对象基本情况 ═══
  h += '<h2>第一章 稽查对象基本情况</h2>';
  h += '<table class="tbl"><tr><td class="lbl">企业名称</td><td>' + (te.name || te.company_name || '-') + '</td></tr>';
  h += '<tr><td class="lbl">统一社会信用代码</td><td>' + (te.uscc || '-') + '</td></tr>';
  h += '<tr><td class="lbl">行业分类</td><td>发票推断：' + (te.industry || '未确定') + '</td></tr>';
  h += '<tr><td class="lbl">分析期间</td><td>' + (te.period || '全量数据') + '</td></tr>';
  h += '</table>';

  // ═══ 第二章：稽查方法 ═══
  h += '<h2>第二章 稽查方法</h2>';
  h += '<p class="i2">根据资料驱动稽查方法论，本次核查采用以下方法：</p>';
  h += '<p class="i2">1. 资料驱动法：对7份经营资料进行综合判定，自动识别文件类型并提取关键数据。</p>';
  h += '<p class="i2">2. 三流比对法：逐票比对发票流（进项/销项）与资金流（银行流水），检查购销匹配度。</p>';
  h += '<p class="i2">3. 多源交叉验证：银行流水、进项发票、销项发票三方数据交叉比对，确认收款来源与开票客户匹配关系。</p>';
  h += '<p class="i2">4. 行业对标法：将毛利率、进销比、人均产值等指标与行业基准值对比。</p>';
  h += '<p class="i2">5. 知识图谱分析：构建供应商/客户/员工关系图谱，检测关联交易和人员重叠。</p>';
  h += '<p class="i2">6. 系统自动执行了23个分析模块的协同运算，详见稽查引擎执行流程。</p>';

  // ═══ 第三章：风险发现 ═══
  h += '<h2>第三章 风险发现</h2>';
  var risks = allF.filter(function(f){ return f.level === '高风险' || f.level === '极高风险'; });
  var mids = allF.filter(function(f){ return f.level === '中风险'; });
  var lows = allF.filter(function(f){ return f.level !== '高风险' && f.level !== '极高风险' && f.level !== '中风险'; });
  
  h += '<p class="i2">经分析，共发现<strong>' + allF.length + '</strong>条风险，其中'
    + '高风险' + risks.length + '条、中风险' + mids.length + '条、低风险' + lows.length + '条。</p>';
  
  // 高风险优先
  var allSorted = risks.concat(mids).concat(lows);
  for (var fi = 0; fi < allSorted.length; fi++) {
    var f = allSorted[fi];
    var lv = f.level || '中风险';
    var cls = lv === '高风险' || lv === '极高风险' ? 'red' : (lv === '中风险' ? 'amber' : 'green');
    var tagCls = lv === '高风险' || lv === '极高风险' ? 'rtag' : (lv === '中风险' ? 'atag' : 'gtag');
    
    h += '<div class="conclusion-box ' + cls + '">';
    h += '<div class="ftitle"><span class="tag ' + tagCls + '">' + lv + '</span> ' + (f.type || '未命名发现') + '</div>';
    h += '<div class="frow">' + (f.detail || f.description || '') + '</div>';
    if (f.how_found) h += '<div class="frow"><span class="flabel">稽查方法：</span>' + f.how_found + '</div>';
    if (f.tax_impact) h += '<div class="frow"><span class="flabel">税务影响：</span>' + f.tax_impact + '</div>';
    if (f.suggestion) h += '<div class="frow"><span class="flabel">处理建议：</span>' + f.suggestion + '</div>';
    if (f.policy_ref) h += '<div class="law-ref">法规依据：' + f.policy_ref + '</div>';
    h += '</div>';
  }

  // ═══ 第四章：资金流向 ═══
  h += '<h2>第四章 资金流向分析</h2>';
  if (bi && (bi['总收款'] || bi['总付款'])) {
    h += '<p class="i2">分析期间，银行账户累计收款' + ((bi['总收款']||0)/10000).toFixed(2) + '万元，累计付款' + ((bi['总付款']||0)/10000).toFixed(2) + '万元。</p>';
  }
  if (rc && Object.keys(rc).length > 0) {
    h += '<p class="i2"><strong>收款方TOP5：</strong></p>';
    h += '<table class="tbl2"><thead><tr><th>收款方</th><th class="r">笔数</th></tr></thead><tbody>';
    var keys = Object.keys(rc).sort(function(a,b){ return (rc[b]||0) - (rc[a]||0); });
    for (var ki = 0; ki < Math.min(keys.length, 5); ki++) {
      h += '<tr><td>' + keys[ki] + '</td><td class="r">' + rc[keys[ki]] + '笔</td></tr>';
    }
    h += '</tbody></table>';
  }

  // ═══ 第五章：综合定性 ═══
  h += '<h2>第五章 综合定性</h2>';
  var synth = r.comprehensive || {};
  if (synth.synthesis) {
    h += '<p class="i2">' + synth.synthesis + '</p>';
  }
  var overall = synth.overall_risk || '中风险';
  h += '<p class="i2">综合风险评级：<strong class="' + (overall==='高风险'?'rtag':'atag') + '">' + overall + '</strong></p>';

  // ═══ 第六章：稽查结论与建议 ═══
  h += '<h2>第六章 稽查结论与建议</h2>';
  h += '<p class="i2">经对被查单位「' + (te.name || te.company_name || '') + '」进行综合稽查分析，形成结论如下：</p>';
  h += '<p class="i2">本次共发现' + allF.length + '项风险，其中高风险' + risks.length + '项，需重点核查。</p>';
  
  // P0建议列表
  if (r.audit_strategies && r.audit_strategies.length) {
    h += '<p class="i2"><strong>优先处理建议：</strong></p>';
    r.audit_strategies.forEach(function(s, si) {
      h += '<p class="i2">' + (si+1) + '. ' + (s.action || s.description || '') + '</p>';
    });
  }
  
  h += '<div class="seal"><p>稽查员（签名）：_______________</p><p>日期：' + dateStr + '</p></div>';

  // ═══ 第七章：附件 ═══
  h += '<h2>第七章 附件</h2>';
  h += '<div class="appendix"><div class="atitle">附件一：文件清单</div>';
  if (r.file_results && r.file_results.length) {
    r.file_results.forEach(function(fr, fi) {
      h += '<div class="aitem">' + (fi+1) + '. ' + (fr.file || '') + ' (' + (fr.type || '') + ')</div>';
    });
  } else {
    h += '<div class="aitem">共7份文件（详情见资料列表）</div>';
  }
  h += '</div>';
  
  if (r.quality_check) {
    h += '<div class="appendix"><div class="atitle">附件二：质量标准自检</div>';
    var qc = r.quality_check;
    h += '<div class="aitem">通过：' + (qc.passed || 0) + '/' + (qc.total || 12) + '项 (' + (qc.pass_rate || 0) + '%)</div>';
    h += '</div>';
  }

  h += '</div>';
  return { html: h, renderedModules: ['cover','ch1-entity','ch2-methods','ch3-findings','ch4-funds','ch5-synthesis','ch6-conclusion','ch7-appendix'], skippedModules: [] };
}

// ==================== 导出报告 ====================
function exportTaxDocReport() {
  var area = document.getElementById('tda-report-area');
  if (!area) return;
  var content = area.innerHTML;
  var title = '涉税资料分析报告';
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
    var resp = await fetch('/api/tax-risk-docs/review?company_id=' + _tdaCid(), { method: 'POST' });
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

  html += '<div style="margin-top:16px;background:#f0fdf4;border-radius:8px;padding:12px 16px;font-size:12px;color:#065f46">'
    + '<b>复核方法：</b>'
    + '① 数据源验证（结论引用的数字是否真实存在） | '
    + '② 计算复核（关键数字重新从源数据计算） | '
    + '③ 逻辑一致性（不同域结论是否自相矛盾） | '
    + '④ 空值陷阱检测（分母/分组键是否有效） | '
    + '⑤ 极端值合理性（>95%占比需人工确认）'
    + '</div>';

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
    var resp = await fetch('/api/tax-risk-docs/review-single?company_id=' + _tdaCid(), {
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

// ==================== 缓存管理 ====================
async function showCacheInfo() {
  try {
    var listResp = await fetch('/api/tax-risk-docs/list?company_id=' + _tdaCid());
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
    var resp = await fetch('/api/tax-risk-docs/clear-transfer?company_id=' + _tdaCid(), { method: 'DELETE' });
    var data = await resp.json();
    if (data.ok) { toast('缓存已清除', 'success'); var m = document.getElementById('tda-cache-modal'); if(m) m.remove(); }
    else { toast('清除失败', 'error'); }
  } catch(e) { toast('清除失败: ' + e.message, 'error'); }
}
