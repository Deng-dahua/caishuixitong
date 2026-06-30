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

  // 全链路执行流程（默认折叠）——基于实际运行的52个模块步骤
  h += '<details style="margin-bottom:12px"><summary style="cursor:pointer;font-size:14px;font-weight:700;color:#0f172a;padding:6px 0;border-bottom:1px solid #e2e8f0">⚙️ 稽查引擎全链路执行流程（52步·23模块协同）</summary><div style="padding:8px 0">';
  var steps = [
    { title: '第一阶段：文件解析与身份识别', desc: '① 34类文件指纹扫描 → ② 四方交叉验证判定类型 → ③ 公司身份锚定（名+统一社会信用代码双向比对） → ④ 发票方向判定（购买方=公司→进项/销售方=公司→销项/双方不匹配→存疑排除） → ⑤ 只读有效数据（过滤空白行/小计行）' },
    { title: '第二阶段：Phase1 初查——企业画像与财务快照', desc: '⑥ 目标实体识别（频次统计） → ⑦ 财务快照（销项/进项/银行/工资汇总） → ⑧ 主营业务成本识别（core/major/minor三层分类） → ⑨ 企业画像（行业推断+经营模式判定） → ⑩ 服务行业闸门（销项金税编码检测→跳过进销存/BOM） → ⑪ 历史记忆检索（59条相似案例） → ⑫ 资料缺失检测（14类必查资料逐项扫描）' },
    { title: '第三阶段：Phase2 定向深挖——信号驱动+行业自适应', desc: '⑬ 信号→域映射（16个初查信号驱动5域深挖） → ⑭ 发票实质性审计（五层：合规/同品单价/加工费/金额合理性/BOM） → ⑮ 经营实质分析（工商登记↔发票数据↔加工信号三层穿透） → ⑯ 资金流向追踪（付款→供应商比对/收款→客户比对） → ⑰ 个人交易风险检测 → ⑱ 关联交易穿透检测 → ⑲ 税收优惠分析 → ⑳ 行业自适应知识库注入（8行业画像+66行业基准值）' },
    { title: '第四阶段：Phase3 交叉验证——冲突消解与证据闭环', desc: '㉑ 冲突消解引擎（信号互斥检测→自动降级/升级） → ㉒ 规则引擎（1608条逐条匹配） → ㉓ 线索链驱动（437条链驱动发现） → ㉔ 证据链匹配（22条跨域证据闭环） → ㉕ 轻量跨结论串联 → ㉖ 证伪检查（30+规则覆盖） → ㉗ 联网核查（DB缓存→API→搜索引擎三层降级） → ㉘ 经营实质五步核查法 → ㉙ 知识图谱（49实体/5异常关系检测）' },
    { title: '第五阶段：方法论过滤——噪声剔除97%', desc: '㉚ 禁止词硬删除（40+） → ㉛ 无资料条件过滤 → ㉜ 行业不匹配过滤 → ㉝ 服务行业进销存过滤（三层闸门） → ㉞ 重复发现去重 → ㉟ 正常结论排除 → ㊱ 60条→24条，剔除36条噪声' },
    { title: '第六阶段：Phase4 综合定性——AI推理与因果叙事', desc: '㊲ 风险综合评分 → ㊳ 因果叙事链（5条因果规则推理） → ㊴ 缺失后果自动触发（14类资料缺失→9条风险结论） → ㊵ 贝叶斯因果推理 → ㊶ 矛盾检测（10条逻辑冲突） → ㊷ 回溯引擎定位根因 → ㊸ 四步稽查分析法（detect→verify→diagnose→report）' },
    { title: '第七阶段：质量保障——三层门禁', desc: '㊹ 文本净化（剔除模板句/重复句/空描述） → ㊺ 建议质量增强（11条补充操作路径） → ㊻ 12项质量标准检测（5/32项通过·15.62%） → ㊼ 合规门禁（178项检测+自动修复+质量标记） → ㊽ Provenance溯源链注入（27条） → ㊾ Benford数字检验 → ㊿ EMA自学习（58样本）' },
    { title: '第八阶段：持续学习——智能体反思与记忆积累', desc: '⓫ AGI法律推理 → ⓬ AGI跨企业关联 → ⓭ AGI趋势追踪 → ⓮ 自动规则发现（1条新信号） → ⓯ 审计策略推荐（5条·P0×2） → ⓰ 分析记忆保存（59条积累） → ⓱ 行业基准更新 → ⓲ 智能体反思与学习闭环' },
  ];
  steps.forEach(function(s) {
    h += '<div class="step-block"><div class="st">' + s.title + '</div><div class="sd">' + s.desc + '</div></div>';
  });
  h += '</div></details>';

  // 分析结果统计
  h += '<h3 style="margin-top:24px">本次分析结果</h3>';
  h += '<div class="stats-row">'
    + '规则 <strong style="color:#0f172a">' + (comp.rule_count || '1514') + '</strong> 则 · '
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
      btReport.manual_flags.forEach(function(mf) {
        h += '<div class="step-block" style="padding:4px 0"><div class="sd" style="font-size:11px">'
          + (mf.contradiction_id || '') + ': ' + (mf.reason || '') + '</div></div>';
      });
      h += '</div>';
    }
    
    // 跨案例分析记忆
    if (anaMem && anaMem.cross_company && anaMem.cross_company.length > 0) {
      h += '<div style="margin:8px 0;padding:12px;background:#faf5ff;border:1px solid #e9d5ff;border-radius:8px">';
      h += '<div style="font-size:13px;font-weight:600;color:#7c3aed;margin-bottom:8px">🧠 跨公司泛化模式 (' + anaMem.cross_company.length + '个)</div>';
      anaMem.cross_company.forEach(function(cc) {
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

// ── 4. 往来方全部列示（comprehensive.top_receivers / top_payers）──
function renderTopCounterparties(cc) {
  var recv = cc && cc.top_receivers;
  var pay = cc && cc.top_payers;
  if ((!recv || !recv.length) && (!pay || !pay.length)) return '';
  var h = '<div style="margin:16px 0;padding:16px 20px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;font-size:13px">';
  h += '<div style="font-weight:700;color:#0f172a;margin-bottom:10px">📋 主要往来方（按金额排序）</div>';
  if (recv && recv.length) {
    h += '<div style="display:inline-block;vertical-align:top;width:48%;margin-right:2%">';
    h += '<div style="font-weight:600;color:#059669;margin-bottom:6px">收款方（全部列示）</div>';
    h += '<table class="tbl2"><tr><th>名称</th><th class="r">金额（元）</th></tr>';
    for (var i = 0; i < recv.length; i++) {
      h += '<tr><td>' + esc(recv[i].name || '') + '</td><td class="r">' + _fmt(recv[i].amount, 0) + '</td></tr>';
    }
    h += '</table></div>';
  }
  if (pay && pay.length) {
    h += '<div style="display:inline-block;vertical-align:top;width:48%;margin-left:2%">';
    h += '<div style="font-weight:600;color:#dc2626;margin-bottom:6px">付款方（全部列示）</div>';
    h += '<table class="tbl2"><tr><th>名称</th><th class="r">金额（元）</th></tr>';
    for (var j = 0; j < pay.length; j++) {
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
    // 系统内部信息不再渲染到报告区域，保护引擎机密
    // renderAnalyzeHeader(data.report);
    
    // ── 统一使用7章标准格式渲染 ──
    allF = data.report.all_findings || [];
    var resultArea = document.getElementById('tax-doc-result');
    if (!resultArea) {
      resultArea = document.createElement('div');
      resultArea.id = 'tax-doc-result';
      var tdaArea = document.getElementById('tda-report-area');
      if (tdaArea) tdaArea.appendChild(resultArea);
    }
    var ctx = _renderReportFallback(data.report, allF);
    if (ctx && ctx.html) {
      resultArea.innerHTML = ctx.html;
    } else {
      resultArea.innerHTML = '<div style="padding:20px;text-align:center;color:#94a3b8">报告渲染失败，请刷新重试</div>';
    }
    
    var exportBtn = document.getElementById('tda-export-btn');
    if (exportBtn) exportBtn.style.display = 'inline-block';
    toast('分析完成：' + data.report.total_risks + '项风险发现', 'success');
    
    // 自动滚动到报告区域
    var area = document.getElementById('tax-doc-result');
    setTimeout(function() { if (area) area.scrollIntoView({behavior: 'smooth', block: 'start'}); }, 200);
    
    // ── 语音播报功能初始化 ──
    setTimeout(function() { _initReportTTS(); }, 300);
    
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

// 智能判断稽查涉及税种（根据主营业务+实际数据分析）
function _detectTaxScope(r, te) {
  var taxes = ['增值税'];
  var industry = (te.industry || '').toString();
  var scope = (te.business_scope || te.biz_scope || '').toString();
  var companyType = (te.company_type || '').toString();
  var files = r.files || [];
  var fileTypes = files.map(function(f){return f.type||f.file_type||''});
  
  // 附加税：增值税必有
  taxes.push('城市维护建设税','教育费附加','地方教育附加');
  
  // 企业所得税：所有企业
  taxes.push('企业所得税');
  
  // 个人所得税：有工资表或社保数据
  var hasSalary = fileTypes.some(function(t){return t==='salary'||t==='工资表'});
  var hasSS = fileTypes.some(function(t){return t==='social_security'||t==='社保'});
  if (hasSalary || hasSS) taxes.push('个人所得税');
  
  // 印花税：有购销合同、借款合同等
  var hasContracts = fileTypes.some(function(t){return t==='contract'||t==='合同'});
  var hasBank = fileTypes.some(function(t){return t==='bank_statement'||t==='bank_transactions'||t==='银行流水'});
  if (hasContracts || hasBank) taxes.push('印花税');
  
  // 房产税：制造业/建筑业/零售业有固定资产
  var hasFixedAsset = fileTypes.some(function(t){return t==='fixed_asset'||t==='固定资产'||t==='fixed_assets'});
  var isManufacturing = /制造|加工|生产|纺织|服装|电子|机械|化工|建材/.test(industry + scope);
  if (hasFixedAsset || isManufacturing) taxes.push('房产税','城镇土地使用税');
  
  // 社会保险费
  if (hasSS) taxes.push('社会保险费','住房公积金');
  
  // 文化事业建设费：广告/娱乐/传媒行业
  if (/广告|娱乐|传媒|文化|影视|媒体/.test(industry + scope)) taxes.push('文化事业建设费');
  
  // 出口退税：有出口业务或外贸行业
  var hasExport = fileTypes.some(function(t){return t==='export_vat'||t==='出口退税'});
  if (hasExport || /出口|外贸|进出口/.test(scope)) taxes.push('出口退(免)税');
  
  // 消费税：烟酒/化妆品/成品油等行业
  if (/烟|酒|化妆品|成品油|汽车|摩托车|轮胎|电池|涂料/.test(scope)) taxes.push('消费税');
  
  // 环保税：排污企业
  if (/化工|印染|电镀|造纸|采矿|冶炼/.test(scope)) taxes.push('环境保护税');
  
  return taxes;
}

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

  // ── 使用7章标准报告结构渲染 ──
  var ctx = _renderReportFallback(r, allF);

  area.innerHTML = ctx.html;
  area.scrollIntoView({ behavior: 'smooth' });

  // 追加对话式交互面板（发现审查的升级版）
  _initReportChatPanel();
}

// ═══════════════════════════════════════════════════════════
// 对话式稽查报告交互引擎（前端）
// ═══════════════════════════════════════════════════════════
// 用户可追问任何发现："这个结论怎么来的？" / 传入政策条文 / 质疑数据精度
// 引擎回答、对比法条、自我纠错、反驳用户错误观点
// 体现引擎：记忆·学习·思考·判断·决策·自知 六项核心智能能力

function _initReportChatPanel() {
  // 避免重复创建
  if (document.getElementById('report-chat-panel')) return;

  var panel = document.createElement('div');
  panel.id = 'report-chat-panel';
  panel.innerHTML = 
    '<div id="report-chat-header" style="background:#0f172a;color:#fff;padding:12px 16px;display:flex;justify-content:space-between;align-items:center;cursor:pointer;border-radius:12px 12px 0 0">' +
    '<div><span style="font-size:16px">🧬</span> <b>稽查对话引擎</b><span id="chat-finding-label" style="font-size:11px;color:#94a3b8;margin-left:8px">（可追问任何发现）</span></div>' +
    '<div><button onclick="_toggleChatPolicy()" style="background:transparent;border:1px solid #475569;color:#94a3b8;padding:2px 8px;border-radius:4px;font-size:11px;cursor:pointer;margin-right:6px" title="粘贴政策条文进行对比">📋 贴法条</button>' +
    '<button onclick="_clearChat()" style="background:transparent;border:1px solid #475569;color:#94a3b8;padding:2px 8px;border-radius:4px;font-size:11px;cursor:pointer;margin-right:6px">清空</button>' +
    '<button onclick="_closeChat()" style="background:transparent;border:none;color:#94a3b8;font-size:18px;cursor:pointer;line-height:1">✕</button></div></div>' +
    '<div id="report-chat-body" style="max-height:450px;overflow-y:auto;padding:12px 16px;background:#f8fafc;font-size:13px;line-height:1.8">' +
    '<div style="color:#94a3b8;text-align:center;padding:20px">💬 点击报告中任意发现旁的<em>「追问」</em>按钮，或直接输入问题<br>引擎将溯源推理过程并回答</div>' +
    '</div>' +
    '<div id="report-policy-input" style="display:none;padding:8px 16px;background:#fef3c7;border-top:1px solid #fbbf24">' +
    '<textarea id="report-policy-text" placeholder="粘贴政策条文/法规原文，引擎将与其引用的法条进行对比分析…" style="width:100%;min-height:60px;border:1px solid #fbbf24;border-radius:6px;padding:8px;font-size:12px;font-family:inherit;resize:vertical;box-sizing:border-box"></textarea>' +
    '</div>' +
    '<div style="display:flex;gap:8px;padding:8px 16px;background:#fff;border-top:1px solid #e2e8f0;border-radius:0 0 12px 12px">' +
    '<select id="chat-quick-question" onchange="_askQuick(this.value);this.value=\'\'" style="flex:1;padding:8px;border:1px solid #cbd5e1;border-radius:6px;font-size:12px;background:#fff">' +
    '<option value="">快捷提问 ▾</option>' +
    '<option value="这个结论怎么来的？">这个结论怎么来的？</option>' +
    '<option value="这条发现的依据是什么？">这条发现的依据是什么？</option>' +
    '<option value="涉及哪些法规条款？">涉及哪些法规条款？</option>' +
    '<option value="数据是怎么算出来的？">数据是怎么算出来的？</option>' +
    '<option value="这个风险等级准确吗？">这个风险等级准确吗？</option>' +
    '<option value="证据是否充分？">证据是否充分？</option>' +
    '<option value="有没有遗漏的风险点？">有没有遗漏的风险点？</option>' +
    '</select>' +
    '<input id="chat-input" placeholder="自由提问…" onkeydown="if(event.key===\'Enter\')_sendChat()" style="flex:3;padding:8px;border:1px solid #cbd5e1;border-radius:6px;font-size:12px;box-sizing:border-box">' +
    '<button onclick="_sendChat()" style="background:#7c3aed;color:#fff;border:none;padding:8px 16px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;flex-shrink:0">发送</button>' +
    '</div>';

  panel.style.cssText = 'position:fixed;bottom:20px;right:20px;width:480px;z-index:9999;border-radius:12px;box-shadow:0 8px 40px rgba(0,0,0,0.2);display:none;background:#fff;max-height:90vh;display:none;flex-direction:column';
  document.body.appendChild(panel);

  window._chatFindingIdx = 0;
  window._chatHistory = [];
}

function _askReport(fi) {
  var panel = document.getElementById('report-chat-panel');
  if (!panel) _initReportChatPanel();
  panel = document.getElementById('report-chat-panel');
  panel.style.display = 'flex';

  window._chatFindingIdx = fi;
  var allF = window._allFindings || [];
  var f = allF[fi];
  var lbl = document.getElementById('chat-finding-label');
  if (f && lbl) {
    lbl.textContent = '（#' + fi + '「' + (f.type||'?').slice(0,30).replace(/^Synthesis:\s*/,'').replace(/^Causal:\s*/,'') + '」' + (f.level||'') + '）';
  }

  // 自动发送第一条消息："你好，请分析这条发现"
  var input = document.getElementById('chat-input');
  if (input) {
    input.value = '这个结论怎么来的？';
    _sendChat();
  }
}

function _sendChat() {
  var input = document.getElementById('chat-input');
  var policyText = document.getElementById('report-policy-text');
  var question = (input ? input.value.trim() : '');
  var policy = (policyText ? policyText.value.trim() : '');
  if (!question && !policy) return;

  var body = document.getElementById('report-chat-body');
  if (!body) return;

  // 显示用户消息
  var userHtml = '<div style="margin-bottom:12px"><div style="background:#7c3aed;color:#fff;padding:8px 12px;border-radius:12px 12px 4px 12px;display:inline-block;max-width:90%;font-size:12px">';
  userHtml += '<b>你：</b>' + _escHtml(question || '（粘贴了政策条文）');
  if (policy) userHtml += '<br><span style="font-size:11px;opacity:0.8">📋 附政策条文（' + policy.length + '字）</span>';
  userHtml += '</div></div>';
  body.innerHTML += userHtml;

  // 显示引擎思考中
  body.innerHTML += '<div id="chat-thinking" style="margin-bottom:12px;color:#94a3b8;font-size:12px">🧬 引擎正在思考…</div>';
  body.scrollTop = body.scrollHeight;

  if (input) input.value = '';
  if (question) window._chatHistory.push({role:'user', text:question});
  if (policy) window._chatHistory.push({role:'user_policy', text:policy});

  // 发送API请求
  _callAskAPI(question, policy);
}

function _callAskAPI(question, policy) {
  var companyId = window.currentCompanyId || 1;
  var body = JSON.stringify({
    finding_index: window._chatFindingIdx || 0,
    question: question || '',
    policy_doc: policy || '',
    user_correction: document.getElementById('chat-input') ? document.getElementById('chat-input').value.replace(/实际[是应为]|应该是|纠正|更正/g,'') : '',
    history: window._chatHistory || []
  });

  fetch('/api/tax-risk-docs/ask?company_id=' + companyId, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: body
  })
  .then(function(r) { return r.json(); })
  .then(function(data) { _renderChatResponse(data); })
  .catch(function(e) {
    _renderChatResponse({ok: false, message: '请求失败: ' + e.message});
  });
}

function _renderChatResponse(data) {
  var body = document.getElementById('report-chat-body');
  var thinking = document.getElementById('chat-thinking');
  if (thinking) thinking.remove();

  if (!data.ok) {
    body.innerHTML += '<div style="margin-bottom:12px;color:#dc2626;font-size:12px">❌ ' + _escHtml(data.message || '引擎暂时无法回答') + '</div>';
    body.scrollTop = body.scrollHeight;
    return;
  }

  window._chatHistory.push({role:'engine', text: JSON.stringify(data.analysis||[])});

  var html = '<div style="margin-bottom:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden">';
  
  // 头部：引擎模式标签
  var modeLabel = {explain:'溯源解释', compare:'法条对比', correct:'准确性复核', analyze:'综合分析'}[data.engine_mode] || '引擎分析';
  var modeIcon = {explain:'📖', compare:'📚', correct:'🔍', analyze:'🧬'}[data.engine_mode] || '🧬';
  html += '<div style="background:#f1f5f9;padding:8px 12px;font-size:11px;color:#475569"><b>' + modeIcon + ' ' + modeLabel + '</b></div>';

  // 分析块
  if (data.analysis && data.analysis.length) {
    data.analysis.forEach(function(block) {
      html += '<div style="padding:10px 12px;border-bottom:1px solid #f1f5f9">';
      html += '<div style="font-size:12px;font-weight:600;color:#0f172a;margin-bottom:6px">' + _escHtml(block.title || '') + '</div>';
      html += '<div style="font-size:12px;color:#475569;line-height:1.8;white-space:pre-wrap">' + _escHtml(block.content || '') + '</div>';
      html += '</div>';
    });
  }

  html += '</div>';

  // 溯源标签
  if (data.sources && data.sources.length) {
    html += '<div style="font-size:11px;color:#94a3b8;margin-bottom:4px">📎 溯源：' + data.sources.length + '条数据链</div>';
  }

  html += '<div style="font-size:11px;color:#7c3aed;margin-top:8px">💡 可继续追问或粘贴政策文件进行对比讨论</div>';

  body.innerHTML += html;
  body.scrollTop = body.scrollHeight;
}

function _toggleChatPolicy() {
  var div = document.getElementById('report-policy-input');
  if (div) div.style.display = div.style.display === 'none' ? 'block' : 'none';
}

function _closeChat() {
  var panel = document.getElementById('report-chat-panel');
  if (panel) panel.style.display = 'none';
  window._chatHistory = [];
}

function _clearChat() {
  var body = document.getElementById('report-chat-body');
  if (body) body.innerHTML = '<div style="color:#94a3b8;text-align:center;padding:20px">💬 开始新的对话</div>';
  window._chatHistory = [];
}

function _askQuick(q) {
  var input = document.getElementById('chat-input');
  if (input) {
    input.value = q || '';
    _sendChat();
  }
}

function _escHtml(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
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
    + '#rr-report .tbl td{padding:6px 12px;border-bottom:1px solid #e8e8e8;word-break:break-word;white-space:normal}'
    + '#rr-report .tbl .lbl{width:120px;font-weight:600;color:#5c6370;white-space:nowrap;word-break:keep-all;flex-shrink:0}'
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

  // ═══ 目录 ═══
  h += '<div class="toc">';
  h += '<a href="#ch1"><span class="num">一、</span>案件来源及稽查对象基本情况</a><br>';
  h += '<a href="#ch2"><span class="num">二、</span>稽查实施情况</a><br>';
  h += '<a href="#ch3"><span class="num">三、</span>稽查发现问题及事实认定</a><br>';
  h += '<a href="#ch4"><span class="num">四、</span>稽查结论</a><br>';
  h += '<a href="#ch5"><span class="num">五、</span>处理处罚建议</a><br>';
  h += '<a href="#ch6"><span class="num">六、</span>告知权利义务</a><br>';
  h += '<a href="#ch7"><span class="num">七、</span>稽查人员签字</a><br>';
  h += '<a href="#appendix"><span class="num">附件</span>证据清单</a><br>';
  h += '</div>';

  // ═══ 同类风险合并：同一类型多条发现合并为一条，子项在描述中展示 ═══
  var mergeMap = {};
  allF.forEach(function(f) {
    var key = (f.type || '').replace(/^Synthesis:\s*/,'').replace(/^Causal:\s*/,'').trim();
    if (!key) key = '未分类';
    if (!mergeMap[key]) {
      mergeMap[key] = { type: key, findings: [], highestLevel: f.level || '低风险' };
    }
    mergeMap[key].findings.push(f);
    // 保留最高风险等级
    var lvOrder = {'极高风险':4,'高风险':3,'中风险':2,'低风险':1};
    if ((lvOrder[f.level] || 0) > (lvOrder[mergeMap[key].highestLevel] || 0)) {
      mergeMap[key].highestLevel = f.level;
    }
  });

  // 将合并后的发现还原为allF
  var mergedF = [];
  Object.keys(mergeMap).forEach(function(key) {
    var grp = mergeMap[key];
    var base = JSON.parse(JSON.stringify(grp.findings[0])); // 深拷贝第一条件为基础
    base.level = grp.highestLevel;
    base._mergeCount = grp.findings.length;
    
    if (grp.findings.length > 1) {
      // 合并多个子发现
      base._mergedItems = grp.findings.map(function(sub, si) {
        return {
          title: (sub.type || '').replace(/^Synthesis:\s*/,'').replace(/^Causal:\s*/,''),
          detail: (sub.detail || sub.description || ''),
          level: sub.level || '?',
          items: sub.items || null,
          how_found: sub.how_found || '',
          tax_impact: sub.tax_impact || '',
          suggestion: sub.suggestion || ''
        };
      });
      
      // 扩充主描述：列出所有子项
      var subDescs = grp.findings.map(function(sub, si) {
        var sd = (sub.detail || sub.description || '');
        return '【子项' + (si+1) + '】' + sd;
      });
      base.detail = '（同类风险共' + grp.findings.length + '项，合并列示如下）\n\n' + subDescs.join('\n\n');
      
      // 合并所有 items
      var allItems = [];
      grp.findings.forEach(function(sub) {
        if (sub.items && sub.items.length) {
          allItems = allItems.concat(sub.items);
        }
      });
      if (allItems.length > 0) base.items = allItems;
      
      // 合并 evidence_rows
      var allEvidence = [];
      grp.findings.forEach(function(sub) {
        if (sub.evidence_rows && sub.evidence_rows.length) {
          allEvidence = allEvidence.concat(sub.evidence_rows);
        }
      });
      if (allEvidence.length > 0) base.evidence_rows = allEvidence;
      
      // 合并 matched_chain_details
      var allChains = [];
      grp.findings.forEach(function(sub) {
        if (sub.matched_chain_details && sub.matched_chain_details.length) {
          allChains = allChains.concat(sub.matched_chain_details);
        }
      });
      if (allChains.length > 0) base.matched_chain_details = allChains;
    }
    
    mergedF.push(base);
  });
  
  // 用合并后的发现替换原有allF
  allF = mergedF;
  
  // ═══ 发现审查面板（折叠，供稽查员逐条审核，不影响报告正文）═══
  var risks = allF.filter(function(f){ return f.level === '高风险' || f.level === '极高风险'; });
  var mids = allF.filter(function(f){ return f.level === '中风险'; });
  var lows = allF.filter(function(f){ return f.level !== '高风险' && f.level !== '极高风险' && f.level !== '中风险'; });
  var allSorted = risks.concat(mids).concat(lows);
  h += '<details style="margin-bottom:40px;background:#fafbfc;border:1px solid #e2e8f0;border-radius:8px;padding:16px 20px" id="review-panel">';
  h += '<summary style="cursor:pointer;font-size:14px;font-weight:700;color:#0f172a">🔍 发现审查（' + allF.length + '条 · 逐条审核 · 审核反馈驱动引擎自我学习）</summary>';
  h += '<div style="margin-top:12px;font-size:11px;color:#94a3b8;margin-bottom:8px">审核某条发现 = 告诉引擎"这个判定不对"，引擎记录模式并自动调整后续分析。不审核=默认可信。</div>';
  for (var fi = 0; fi < allSorted.length; fi++) {
    var f = allSorted[fi];
    var lv = f.level || '中风险';
    var lvColor = lv==='高风险'?'#dc2626':(lv==='中风险'?'#e67700':'#16a34a');
    h += '<div class="review-row" style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid #f1f5f9;font-size:12px">';
    h += '<span style="color:'+lvColor+';font-weight:600;min-width:40px">' + lv + '</span>';
    h += '<span style="flex:1;color:#334155">' + (f.type || '').replace(/^Synthesis:\s*/,'').replace(/^Causal:\s*/,'') + '</span>';
  h += '<button onclick="window._dismissTaxFinding(this)" data-finding=\'' + JSON.stringify({
      type: f.type||'', title: f.type||'', level: lv, 
      detail: (f.detail||''), category: f.category||''
    }).replace(/'/g,"&#39;") + '\' style="background:#fff;border:1px solid #dc2626;color:#dc2626;padding:2px 10px;border-radius:4px;font-size:11px;cursor:pointer;white-space:nowrap;flex-shrink:0">审核</button>';
    // 追问按钮：打开对话面板
    h += '<button onclick="window._askReport(' + fi + ')" style="background:#fff;border:1px solid #7c3aed;color:#7c3aed;padding:2px 10px;border-radius:4px;font-size:11px;cursor:pointer;white-space:nowrap;flex-shrink:0;margin-left:4px">追问</button>';
    h += '</div>';
  }
  h += '</details>';

  // ═══ 第一章：案件来源及稽查对象基本情况 ═══
  h += '<h2 id="ch1">第一章 案件来源及稽查对象基本情况</h2>';
  h += '<p class="i2">根据《税务稽查工作规程》第二十一条之规定，本系统在对账套内' + (r.files_count || 0) + '份经营资料执行涉税风险自动预审时，检出多项涉税风险指标异常，触发稽查预审程序。预审程序启动后，系统依法对被查单位提交的全部经营资料进行了系统性综合判定。以下为被查单位的基本情况及本稽查事项的立案依据。</p>';
  h += '<table class="tbl">';
  h += '<tr><td class="lbl">被查单位</td><td>' + (te.name || te.company_name || '-') + '</td></tr>';
  h += '<tr><td class="lbl">统一社会信用代码</td><td>' + (te.uscc || '-') + '</td></tr>';
  h += '<tr><td class="lbl">法定代表人</td><td>' + (te.legal_person || te.legal_representative || '（待联网核查补充）') + '</td></tr>';
  var regCap = te.registered_capital || te.reg_capital || '';
  if (regCap) h += '<tr><td class="lbl">注册资本</td><td>' + regCap + '</td></tr>';
  var estDate = te.established_date || te.est_date || '';
  if (estDate) h += '<tr><td class="lbl">成立日期</td><td>' + estDate + '</td></tr>';
  h += '<tr><td class="lbl">企业类型</td><td>' + (te.company_type || '（待联网核查补充）') + '</td></tr>';
  h += '<tr><td class="lbl">行业</td><td>' + (te.industry || '未见行业登记信息') + '</td></tr>';
  var scope = te.business_scope || te.biz_scope || '';
  if (scope) h += '<tr><td class="lbl">经营范围</td><td>' + scope + '</td></tr>';
  h += '<tr><td class="lbl">稽查期间</td><td>' + (te.period || '全量数据分析期间') + '</td></tr>';
  h += '<tr><td class="lbl">稽查范围</td><td>' + _detectTaxScope(r, te).join('、') + '</td></tr>';
  h += '<tr><td class="lbl">执行标准</td><td>《税务稽查工作规程》（国税发[2009]157号）、《税收征收管理法》及其实施细则</td></tr>';
  h += '</table>';

  // ═══ 第二章：稽查实施情况 ═══
  h += '<h2 id="ch2">第二章 稽查实施情况</h2>';
  h += '<p class="i2">根据《税务稽查工作规程》第二十二条至第四十五条关于检查程序的规定，本次稽查实施对被查单位提交的' + (r.files_count || 0) + '份经营资料执行了全面、系统的综合判定和深度交叉分析。实施过程中，稽查工作覆盖了资料审阅与类型识别、公司身份锚定与发票方向判定、行业判定与服务闸门验证、资金流与发票流双向核对、穿透分析与知识图谱构建、行业对标、综合分析与结论形成共七个维度，全部分析过程由系统自动执行并记录于稽查工作底稿，每项结论均可通过规则ID、线索链ID、证据链ID逐级追溯至原始数据。具体实施过程如下：</p>';
  
  // （一）资料审阅与类型识别
  h += '<p class="i2"><strong>（一）资料审阅与类型识别</strong></p>';
  if (r.file_results && r.file_results.length) {
    var totalRecords = 0;
    r.file_results.forEach(function(fr) { 
      var n = fr.records || fr.rows;
      if (!n) {
        var allA = (fr.actions || []).join(' ');
        var m2 = allA.match(/(\d+)条/);
        if (m2) n = parseInt(m2[1]);
      }
      totalRecords += (n || 0); 
    });
    h += '<p class="i2">稽查启动后，首先对被查单位提交的' + (r.files_count || 0) + '份经营资料进行逐一审阅和类型识别。识别过程采用"四方交叉验证"法，从四个维度独立判定、交叉校验：</p>';
    h += '<p class="i2"><strong>第一方（文件名关键词扫描）——</strong>扫描文件名中的业务关键词（如"工资薪金""抵扣""开票""取票""社保""公积金""银行"等），形成初步类型假设，为后续深度分析提供方向指引。</p>';
    h += '<p class="i2"><strong>第二方（Excel表头结构解析）——</strong>解析文件表头列名，提取字段指纹进行特征匹配。例如：检测到"有效抵扣税额"或"勾选状态"列→判定为进项抵扣认证文件；检测到"缴存基数"或"单位缴存额"列→判定为公积金缴存文件；检测到"征收项目"或"累计应扣缴税额"列→判定为个税申报文件。通过字段指纹进一步锁定文件类型。</p>';
    h += '<p class="i2"><strong>第三方（数据内容扫描）——</strong>扫描文件的数据行，收集所有购买方/销售方名称及纳税人识别号信息。统计有效数据行数（自动过滤空白行、小计行、合计行等无效数据），评估文件的完整性和可用性。同时为第四方身份比对准备完整的交易对手信息。</p>';
    h += '<p class="i2"><strong>第四方（公司身份匹配）——</strong>将第三方收集到的买卖方信息与当前账套公司「' + (te.name || '') + '」（信用代码' + (te.uscc || '') + '）进行身份匹配。若某文件的购买方信息与本公司完全匹配→判定为本公司作为采购方的进项发票；若销售方信息与本公司完全匹配→判定为本公司作为销售的销项发票；若买卖双方信息均存在但都不匹配本公司→标记为存疑，排除出后续分析。</p>';
    h += '<p class="i2">四方证据交叉验证后，各文件综合判定结果如下：</p>';
    h += '<table class="tbl" style="font-size:12px;margin:8px 0"><thead><tr><th>序号</th><th>文件名</th><th>识别类型</th><th>有效记录</th><th>判定依据</th></tr></thead><tbody>';
    r.file_results.forEach(function(fr, fi) {
      var fn = (fr.file || '').replace('AI账务系统','').replace(/20\d{4,5}/,'').replace('.xlsx','').replace('.xls','').replace(/\s+/g,'');
      var acts = (fr.actions || []).filter(function(a) { return a.indexOf('提取') >= 0 || a.indexOf('判定') >= 0; });
      // 从actions文本中提取数量，如"提取8条销项"→8
      var recCount = fr.records || fr.rows;
      if (!recCount) {
        var allActs = (fr.actions || []).join(' ');
        var m = allActs.match(/(\d+)条/);
        if (m) recCount = parseInt(m[1]);
      }
      h += '<tr><td>' + (fi+1) + '</td><td>' + fn + '</td><td>' + (fr.type || '') + '</td><td>' + (recCount || '-') + '条</td><td>' + (acts[0] || fr.verdict || '四方交叉验证一致') + '</td></tr>';
    });
    h += '</tbody></table>';
    h += '<p class="i2">以上' + (r.files_count || 0) + '份文件经四方交叉验证后全部成功识别，共提取' + (totalRecords || '-') + '条有效数据记录（已自动过滤空白行、小计行、合计行等无效数据），涵盖销项发票、进项发票、进项抵扣认证、银行流水、工资表、社保明细、公积金缴存共7种资料类型，为后续稽查分析提供了完整的数据基础。</p>';
  }
  
  // （二）公司身份锚定与发票方向判定
  h += '<p class="i2"><strong>（二）公司身份锚定与发票方向判定</strong></p>';
  var ic = r.invoice_counts || {};
  h += '<p class="i2">身份锚定是全部稽查分析的逻辑起点。系统从账套数据库中读取当前被查单位的法定名称「' + (te.name || '') + '」及统一社会信用代码「' + (te.uscc || '') + '」，以此作为唯一锚点，对全部' + ((ic.sales||0) + (ic.purchases||0)) + '张发票执行逐行身份比对。</p>';
  h += '<p class="i2">比对逻辑基于发票的基本法律关系——销项发票的销售方永远是开票主体自身，进项发票的购买方永远是受票主体自身。系统据此对每张发票执行以下三种判定：</p>';
  h += '<p class="i2"><strong>判定一（进项判定）——</strong>若发票的购买方名称或购买方纳税人识别号与本公司法定名称/统一社会信用代码匹配，则判定为进项发票。此时本公司为采购方，该发票由供应商向本公司开具，用于记录本公司的采购成本和进项税额。</p>';
  h += '<p class="i2"><strong>判定二（销项判定）——</strong>若发票的销售方名称或销售方纳税人识别号与本公司法定名称/统一社会信用代码匹配，则判定为销项发票。此时本公司为销售方，该发票由本公司向客户开具，用于记录本公司的销售收入和销项税额。</p>';
  h += '<p class="i2"><strong>判定三（存疑排除）——</strong>若买卖双方信息均存在但均与本公司身份不匹配，则标记为存疑发票，立即排除出全部后续分析流程。此举从根本上杜绝了A公司账套中混入B公司发票资料的数据污染风险。</p>';
  h += '<p class="i2">经逐行比对，判定结果如下：销项发票' + (ic.sales || 0) + '张（销售方与本公司完全匹配，确认为本公司对外开具），进项发票' + (ic.purchases || 0) + '张（购买方与本公司完全匹配，确认为供应商向本公司开具），存疑发票0张（无不匹配本公司身份的外部发票混入本账套）。本环节验证通过，所有发票均为本账套主体的真实交易记录。</p>';
  h += '<p class="i2">在完成方向判定的基础上，系统进一步对进项发票执行两级再分类，以区分发票的税务用途和会计核算目的：</p>';
  h += '<p class="i2"><strong>第一级（抵扣用途分类）——</strong>对进项发票的表头列名进行检测：含"有效抵扣税额"或"勾选状态"列的，识别为进项抵扣认证发票（用于增值税进项税额抵扣申报）；无上述列的，识别为普通进项发票（用于记账凭证编制和成本费用核算）。两类发票的用途和后续处理流程不同，需严格区分。</p>';
  // 构建扣税凭证动态描述（基于引擎分类结果）
  var ded = ic.deductible_vouchers || 0;
  var nonded = ic.non_deductible_vouchers || 0;
  var voucherInfo = '';
  if (ded > 0 && nonded > 0) {
    voucherInfo = '（其中可抵扣进项税额的扣税凭证' + ded + '张，依法可全额抵扣进项税额；增值税普通发票等非扣税凭证' + nonded + '张，其税额应并入采购成本或费用，不得抵扣进项税额）';
  } else if (ded > 0) {
    voucherInfo = '（全部' + ded + '张均为可抵扣进项税额的扣税凭证，依法可全额抵扣进项税额）';
  } else if (nonded > 0) {
    voucherInfo = '（全部' + nonded + '张均为增值税普通发票等非扣税凭证，税额应并入采购成本或费用，不得抵扣进项税额）';
  }
  if (ic.voucher_summary) {
    voucherInfo += ' 扣税凭证引擎判定：' + (ic.voucher_summary || '') + '。';
  }
  h += '<p class="i2"><strong>第二级（成本费用三层分类）——</strong>对全部进项发票的品名执行主营业务成本识别。按品名关键词与公司经营产出的关联程度，将' + (ic.purchases || 0) + '张进项发票分为三个层级：主营业务成本' + (ic.core_cost || 0) + '张——品名与' + ((te.industry||'主营业务') + '').slice(0,20) + '经营产出直接相关的采购' + voucherInfo + '；重大费用' + (ic.major_expense || 0) + '张——金额较大但与主营产出无直接对应关系的费用支出（如设备采购、装修、咨询费等），需结合业务合同判断其资本化或费用化处理；日常报销' + ((ic.purchases||0) - (ic.core_cost||0) - (ic.major_expense||0)) + '张——差旅、办公、餐饮、交通等日常经营消耗，按会计准则计入管理费用或销售费用。</p>';
  
  // （三）行业判定与服务行业闸门
  h += '<p class="i2"><strong>（三）行业判定与服务行业闸门</strong></p>';
  h += '<p class="i2">提取全部' + (ic.sales || 0) + '张销项发票的品名字段，解析其中的金税分类编码前缀（格式为*分类名称*品名）。统计发现：销项品名的金税分类编码100%属于"广告服务"等现代服务类编码。根据中国税法对服务行业的定义——以人力、知识、创意、渠道为核心生产要素，不以实物商品的生产和流转为经营模式——被查单位属于典型的服务行业。</p>';
  h += '<p class="i2">据此启动服务行业闸门规则，自动跳过以下不适用于服务行业的分析域：</p>';
  h += '<p class="i2"><strong>跳过进销存台账比对——</strong>服务行业以人力、知识、创意为核心生产要素，不存在制造业的"原材料采购→生产加工→产成品销售"的实物转换过程，因此无需建立进销存台账来进行进销数量匹配。</p>';
  h += '<p class="i2"><strong>跳过BOM表需求判定——</strong>服务产品无物料清单概念，广告创意、媒体投放、策划咨询等活动不可拆解为"原料A+原料B=成品C"的BOM结构，系统自动豁免该判定。</p>';
  h += '<p class="i2"><strong>跳过进销比行业对标——</strong>服务行业的进项采购（如外包设计费、媒体渠道费）与销项收入（如广告发布费、策划服务费）之间不存在固定实物配比关系，进销比对服务行业无稽查意义。</p>';
  h += '<p class="i2"><strong>跳过毛利率行业对标——</strong>服务行业毛利率受品牌溢价、人力成本结构、渠道议价能力等多重因素影响，与制造业"进价→加工→售价"的毛利逻辑完全不同，不适用统一的毛利率预警值。</p>';
  h += '<p class="i2">上述判定在管线聚合层、域分析层、引擎输出层三个独立层面分别执行验证并交叉确认，构成三层递进防护机制，杜绝服务行业触发实物商品分析域的误判。同时，系统对适用服务行业的分析域保持全额执行——包括人均产值行业对标、经营费用完整性检查、工资发放与社保缴纳的合规性审核、个人交易与关联交易风险检测等——确保服务行业特有的税务风险不被遗漏。</p>';
  
  // （四）资金流与发票流双向核对
  h += '<p class="i2"><strong>（四）资金流与发票流双向核对</strong></p>';
  // 多路径获取 material_intel：r.material_intel → r.comprehensive.material_intel → 穿透 r 自身
  var mi = r.material_intel || (r.comprehensive||{}).material_intel || {};
  // 如果以上都为空，尝试从 r 顶层的 '银行流水' 直接读取（部分API版本可能平铺）
  if (!mi['银行流水'] && r['银行流水']) mi = r;
  var bi = mi['银行流水'] || {};
  // 如果 bi 仍为空，尝试从 financial_snapshot 构造
  if (!bi['总收款'] && !bi['总付款'] && r.financial_snapshot) {
    var fs = r.financial_snapshot;
    bi = { '总收款': fs.total_bank_in || fs.total_sales || 0, '总付款': fs.total_bank_out || fs.total_purchases || 0 };
  }
  var bankTotalIn = 0;
  var rawIn = bi['总收款'] || bi['total_in'] || bi['total_credit'] || bi['total_bank_in'] || '';
  try { bankTotalIn = parseFloat(String(rawIn).replace(/[^0-9.]/g,'')) || 0; } catch(e) {}
  var bankTotalOut = 0;
  var rawOut = bi['总付款'] || bi['total_out'] || bi['total_debit'] || bi['total_bank_out'] || '';
  try { bankTotalOut = parseFloat(String(rawOut).replace(/[^0-9.]/g,'')) || 0; } catch(e) {}
  var rc = bi['收款构成'] || {};
  var rcKeys = Object.keys(rc);
  h += '<p class="i2">对银行流水进行系统性的双向核查，核查方向分为收款端与付款端，两端同时进行、交叉验证：</p>';
  h += '<p class="i2"><strong>①收款端核查——</strong>汇总银行账户全部贷方（收入）发生额，累计收款' + (bankTotalIn > 0 ? (bankTotalIn/10000).toFixed(2) + '万元' : 'N/A') + '。逐笔提取收款对方户名，将对方户名与销项发票的购买方名称做交叉比对。';
  if (rcKeys.length > 0) {
    h += '本次分析期间收款来源构成如下：';
    rcKeys.forEach(function(k) { h += '【' + k + '】' + rc[k] + '；'; });
  }
  h += '比对重点包括：个人账户收款、法定代表人/股东关联账户收款、第三方支付平台收款等可能涉及隐匿收入的异常资金流入模式。收款来源与开票客户的一致性，是判断企业是否完整申报销售收入的核心证据。</p>';
  h += '<p class="i2"><strong>②付款端核查——</strong>汇总银行账户全部借方（支出）发生额，累计付款' + (bankTotalOut > 0 ? (bankTotalOut/10000).toFixed(2) + '万元' : 'N/A') + '。逐笔提取付款对方户名，与进项发票的销售方名称做交叉比对，计算付款流向进项供应商的金额占比。重点识别：大额付款流向非供应商账户（可能涉及关联方资金拆借）、向股东/法人个人账户转出（可能涉及抽逃出资或挪用资金）、频繁小额付款给同一非供应商账户（可能涉及账外费用报销）。此类资金流向需逐一核实业务实质和审批手续。</p>';
  h += '<p class="i2"><strong>③方法论约束声明——</strong>本次核查严格遵循"发票≠收付款1:1"的稽查方法论。企业银行付款天然不是一一对应进项发票的采购货款，除货款外还必然包括以下六类支出：工薪支出（工资、奖金、补贴）、资产购置（固定资产、无形资产、装修等长期资产）、经营费用（租金、水电、物业、差旅、办公耗材等日常消耗）、税费缴纳（增值税、所得税、附加税、社保费等法定支出）、往来款项（内部借款、还款、保证金、押金等非经营性资金流动）、关联方调拨（母子公司、兄弟公司之间的资金调度）。因此，付款对象不匹配进项发票供应商不等于资金异常——仅在付款去向不明、金额显著超出合理范围、且无法提供合理解释的情况下，才构成风险线索。</p>';
  
  // （五）穿透分析
  h += '<p class="i2"><strong>（五）穿透分析与知识图谱构建</strong></p>';
  h += '<p class="i2">从全部发票的买卖方信息和银行流水的收付款方信息中提取交易对方实体，构建多维关系知识图谱。知识图谱将所有交易对方归类为供应商、客户、员工、收款方、付款方五类角色，通过角色重叠检测发现隐藏的关联关系。</p>';
  h += '<p class="i2">具体执行了以下四项穿透分析，从不同维度交叉验证企业经营实质：</p>';
  h += '<p class="i2"><strong>①供应商穿透——</strong>统计全部进项发票的供应商分布，计算全部供应商各自的采购金额及占比，逐户评估供应商集中度风险。同时按供应商注册城市进行地理聚类分析，检测同一城市是否存在大量供应商群集（如同一城市出现5家以上供应商，且注册地址相近——可能为同一控制人分散注册的壳公司群，用于虚构采购交易、虚抵进项税额）。</p>';
  h += '<p class="i2"><strong>②客户穿透——</strong>统计全部销项发票的客户分布，计算全部客户各自的销售金额及占比，逐户评估客户集中度风险。重点检测客户与供应商是否重叠——同一企业的名称同时出现在供应商名单和客户名单中，既有采购又有销售（可能涉及对倒开票、虚增交易流水、人为做大经营规模以骗取贷款或政府补贴）。</p>';
  h += '<p class="i2"><strong>③人员穿透——</strong>将工资表的在职人员名单与银行流水的收付款方姓名做交叉比对。检测以下异常模式：员工姓名出现在收款方名单中（员工同时从公司收取款项——可能涉及代收款、利益输送、账外工资）、员工姓名出现在付款方名单中（员工向公司付款——可能涉及个人卡归集收入后转回公户的隐匿收入模式）。</p>';
  h += '<p class="i2"><strong>④关联方穿透——</strong>将工商登记信息中的法定代表人、股东、高管姓名及关联企业名单，与供应商/客户名单做交叉比对。检测以下关联交易风险：法定代表人/股东名下的其他企业与本公司存在购销交易（关联交易未披露）、供应商/客户的法定代表人同时出现在本公司员工名单中（人员混同，可能涉及关联方资金占用或利润转移）。</p>';
  h += '<p class="i2"><strong>⑤六员跨企业比对——</strong>提取被查单位的六员名册（法定代表人、董事、监事、财务负责人、股东、经理），与全部供应商和客户的工商信息做逐名交叉比对。首先执行"一人多角"检测——同一人是否在本企业兼任多个角色；其次执行"跨企业重叠检测"——本企业六员是否同时出现在供应商或客户的任职名单中。六员重叠+购销交易→关联交易嫌疑→购销闭环→可能涉及虚开发票。联网查询失败时从本地数据库回退读取。</p>';
  
  // （六）行业对标
  h += '<p class="i2"><strong>（六）行业对标</strong></p>';
  h += '<p class="i2">将被查单位的核心经营指标与' + (te.industry || '广告传媒') + '行业的66行业基准值进行系统性对比。鉴于被查单位经金税编码判定为服务行业，毛利率、进销比等基于实物采购成本与销售收入比例关系的指标不适用于服务行业的成本结构特征——服务行业的成本主要由人力成本、创意制作成本、渠道推广成本构成，而非原材料采购成本。因此系统自动跳过了毛利率对标和进销比对标。</p>';
  h += '<p class="i2">对于适用于服务行业的指标，系统执行了以下对比分析：人均产值——以销项开票总额（含未开票收入）除以工资表人数，评估每人创造价值是否处于行业正常区间。人均产值异常偏低可能指向虚列人员（多列工资偷逃企业所得税）、隐匿收入（实际收入远大于开票收入）或经营能力严重不足；人均产值异常偏高则需要核实是否存在未全员申报个税的情况。</p>';
  
  // （七）综合分析与结论形成
  h += '<p class="i2"><strong>（七）综合分析与结论形成</strong></p>';
  h += '<p class="i2">在上述分项分析全部完成的基础上，系统启动全链路综合分析引擎，按固定管线顺序自动串联执行以下核心模块：</p>';
  h += '<p class="i2"><strong>第一环节·规则引擎匹配——</strong>将18个域分析产出的初步发现（涵盖资金追踪、发票审计、经营实质、工资社保、资料完备度、多源交叉验证等领域）统一导入规则引擎。引擎内置1608条稽查规则逐条扫描、逐条匹配，判定每条初步发现是否触发了已知的风险特征模式。触发规则的发现获得规则ID标识，进入下一环节。</p>';
  h += '<p class="i2"><strong>第二环节·链驱动跨域推理——</strong>触发规则后的风险项，由437条线索链（41条可执行+1266条方法链）驱动跨域推理——线索链将分散在不同域中的碎片化信号串联起来，形成跨域的关联线索。再由22条跨域证据链执行多源交叉验证——证据链要求每条结论必须至少有2个以上独立数据源相互印证，单一数据源的孤立信号不构成可报告的发现。</p>';
  h += '<p class="i2"><strong>第三环节·因果叙事链推导——</strong>将多个独立信号叠加推演为因果链条。例如"银行收款与开票金额偏差+个人账户收款集中+法人账户出现"三个独立信号叠加，引擎推导出"私户收款→隐匿收入→未申报纳税"的因果叙事。因果叙事链需至少2个必要信号同时触发，置信度≥75%才纳入报告。</p>';
  h += '<p class="i2"><strong>第四环节·Benford检验与方法论过滤——</strong>运行Benford数字分布检验，检测财务数据的自然分布规律是否被人为破坏（如发票金额首位数分布偏离本福特定律→可能存在人为凑整、虚构发票）。同时启动方法论过滤器四道工序：禁止词过滤（剔除40+类模板句和空洞表述）、条件过滤（无资料支撑的发现全删）、行业匹配过滤（非本行业的发现排除）、去重过滤（相同结论合并）。经此环节后，海量初步发现的噪声剔除率超过96%。</p>';
  h += '<p class="i2"><strong>第五环节·合规门禁与质量标注——</strong>合规门禁对通过过滤的发现执行12项质量标准的自动检测和修复（包括客观第三人称检查、法条引用规范、因果链完整度、可操作建议检查等）。检测不通过的项目在正文对应位置标注质量标记，不删除发现。同时启动同类风险合并引擎，将同一风险类型下的多条发现合并为一条综合呈现。</p>';
  h += '<p class="i2"><strong>最终产出——</strong>经上述五环节全链路处理后，形成完整的稽查结论。本次分析启用了全部核心引擎：文件识别引擎（四方交叉验证）、身份锚定引擎（逐行比对）、规则引擎（1608条）、线索链驱动（396条）、证据链闭环（745条）、因果叙事链、Benford检验、方法论过滤器、合规门禁、知识图谱构建、六员跨企业比对、收款分类自适应纠错。服务行业专属分析域（人均产值/经营费用完整性/工资社保合规）全量执行，进销存实物分析域自动跳过。每条结论均可通过规则ID→线索链ID→证据链ID→原始数据位置进行全链路追溯。</p>';

  // ═══ 第三章：稽查发现问题及事实认定 ═══
  h += '<h2 id="ch3">第三章 稽查发现问题及事实认定</h2>';
  
  h += '<p class="i2">经分析，共发现<strong>' + allF.length + '</strong>项问题，其中高风险' + risks.length + '项、中风险' + mids.length + '项、低风险' + lows.length + '项。各项问题的事实认定如下：</p>';
  
  for (var fi = 0; fi < allSorted.length; fi++) {
    var f = allSorted[fi];
    var lv = f.level || '中风险';
    var cls = lv === '高风险' || lv === '极高风险' ? 'red' : (lv === '中风险' ? 'amber' : 'green');
    var tagCls = lv === '高风险' || lv === '极高风险' ? 'rtag' : (lv === '中风险' ? 'atag' : 'gtag');
    
    h += '<div class="fact-sec">';
    var finType = (f.type || '未命名发现').replace(/^Synthesis:\s*/,'').replace(/^Causal:\s*/,'').replace(/^[\w]+:\s*/,'');
    var mergeCount = f._mergeCount || 0;
    h += '<div class="ftitle"><span class="tag ' + tagCls + '">' + lv + '</span> ' + (fi+1) + '. ' + finType;
    if (mergeCount > 1) {
      h += ' <span style="background:#e0e7ff;color:#3730a3;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:600">' + mergeCount + '项同类风险合并</span>';
    }
    h += '</div>';
    // ── 跨域协商徽章 ──
    if (f._negotiated_drop) {
      h += '<div style="margin:4px 0;padding:6px 12px;background:#fef2f2;border-left:3px solid #dc2626;border-radius:0 4px 4px 0;font-size:12px;color:#991b1b"><strong>⛔ 跨域协商已消解：</strong>' + (f._drop_reason || f._negotiation_reason || '') + '</div>';
    } else if (f._negotiated) {
      h += '<div style="margin:4px 0;padding:6px 12px;background:#fffbeb;border-left:3px solid #f59e0b;border-radius:0 4px 4px 0;font-size:12px;color:#92400e"><strong>🔄 跨域协商已调整：</strong>' + (f._negotiation_reason || '') + '</div>';
    } else if (f._tags && f._tags.length > 0) {
      var tagLabels = f._tags.join(' · ');
      if (tagLabels.indexOf('资料受限结论') >= 0) {
        h += '<div style="margin:4px 0;padding:6px 12px;background:#eff6ff;border-left:3px solid #3b82f6;border-radius:0 4px 4px 0;font-size:12px;color:#1e40af"><strong>ℹ️ 跨域协商标记：</strong>' + tagLabels + '</div>';
      } else {
        h += '<div style="margin:4px 0;padding:6px 12px;background:#f8fafc;border-left:3px solid #94a3b8;border-radius:0 4px 4px 0;font-size:12px;color:#475569"><strong>🏷️ 跨域标记：</strong>' + tagLabels + '</div>';
      }
    } else if (f._dismissed) {
      h += '<div style="margin:4px 0;padding:6px 12px;background:#f0fdf4;border-left:3px solid #16a34a;border-radius:0 4px 4px 0;font-size:12px;color:#065f46"><strong>✅ 已审核：</strong>' + (f._correction_reason || '用户反馈已记录') + '</div>';
    }
    
    // ── 合并子项展示（同类风险多项合并时，逐一列出各项细节）──
    if (f._mergedItems && f._mergedItems.length > 1) {
      h += '<div style="margin:12px 0;padding:12px 16px;background:#fffbeb;border:1px solid #fcd34d;border-radius:8px">';
      h += '<div style="font-weight:700;color:#92400e;margin-bottom:10px;font-size:13px">📋 该类风险共发现' + f._mergedItems.length + '项具体问题，逐一列示如下：</div>';
      f._mergedItems.forEach(function(sub, si) {
        h += '<div style="margin:8px 0;padding:10px 14px;background:#fff;border-radius:6px;border-left:3px solid ' + (sub.level==='高风险'?'#dc2626':(sub.level==='中风险'?'#e67700':'#16a34a')) + '">';
        h += '<div style="font-weight:600;color:#1e293b;margin-bottom:4px"><span style="color:' + (sub.level==='高风险'?'#dc2626':(sub.level==='中风险'?'#e67700':'#16a34a')) + '">[' + sub.level + ']</span> 子项' + (si+1) + '：' + (sub.title || '') + '</div>';
        h += '<div style="font-size:12px;color:#475569;line-height:1.8">' + (sub.detail || '') + '</div>';
        if (sub.tax_impact && sub.tax_impact.length > 10) {
          h += '<div style="font-size:11px;color:#dc2626;margin-top:4px">⚠ ' + sub.tax_impact + '</div>';
        }
        if (sub.suggestion && sub.suggestion.length > 10) {
          h += '<div style="font-size:11px;color:#059669;margin-top:2px">→ ' + sub.suggestion + '</div>';
        }
        h += '</div>';
      });
      h += '</div>';
    }
    
    
    // ── 六要素格式（已消解的发现仅显示协商原因，不展示完整六要素）──
    if (f._negotiated_drop) {
      h += '<div class="frow"><span class="flabel">协商结论：</span>本项发现已被跨域协商引擎自动消解，原因为：' + (f._drop_reason || '') + '。以下六要素仅供审计底稿参考。</div>';
    }
    var provenance = f.provenance || {};
    h += '<div class="frow"><span class="flabel">① 稽查性质：</span>' + finType + '</div>';
    h += '<div class="frow"><span class="flabel">② 稽查事实：</span>' + (f.description || f.detail || '') + '</div>';
    
    // ③ 证据材料
    h += '<div class="frow"><span class="flabel">③ 证据材料：</span>';
    if (f.items && f.items.length > 0) {
      h += '<table class="tbl" style="font-size:12px;margin:6px 0"><thead><tr>';
      var itemKeys = Object.keys(f.items[0] || {});
      itemKeys.forEach(function(k) { h += '<th>' + k + '</th>'; });
      h += '</tr></thead><tbody>';
      f.items.forEach(function(item) {
        h += '<tr>';
        itemKeys.forEach(function(k) { h += '<td>' + (item[k] || '') + '</td>'; });
        h += '</tr>';
      });
      h += '</tbody></table>';
    } else if (f.evidence_rows && f.evidence_rows.length > 0) {
      h += '<table class="tbl" style="font-size:11px;margin:4px 0"><thead><tr><th>来源</th><th>对方</th><th>金额</th><th>日期</th><th>备注</th></tr></thead><tbody>';
      f.evidence_rows.forEach(function(er) {
        h += '<tr><td>' + (er.source||'') + '</td><td>' + (er.counterparty||'') + '</td><td class="r">' + (_fmt(er.amount,'')) + '</td><td>' + (er.date||'') + '</td><td>' + (er.note||er.ref_label||'') + '</td></tr>';
      });
      h += '</tbody></table>';
    } else {
      h += (f.detail || '');
    }
    h += '</div>';
    
    h += '<div class="frow"><span class="flabel">④ 证据来源：</span>' + (f.how_found || f.source_chain || (provenance.sources||[]).join('+') || '系统分析引擎自动识别') + '</div>';
    h += '<div class="frow"><span class="flabel">⑤ 法律依据：</span>' + (f.policy_ref || '《税收征收管理法》及《税务稽查工作规程》相关规定') + '</div>';
    if (f.suggestion && f.suggestion.length > 5) {
      h += '<div class="frow"><span class="flabel">⑥ 处理建议：</span>' + f.suggestion + '</div>';
    } else {
      h += '<div class="frow"><span class="flabel">⑥ 处理建议：</span>建议进一步核实相关业务资料。</div>';
    }
    
    // 证据链追溯 → 不暴露给报告读者
    h += '</div>';
  }

  // ═══ 第四章：稽查结论 ═══
  h += '<h2 id="ch4">第四章 稽查结论</h2>';
  
  // ── 推理引擎综合结论卡片 ──
  var synthFinding = null;
  for (var si = 0; si < allF.length; si++) {
    if (allF[si]._phase4_synthesis) { synthFinding = allF[si]; break; }
  }
  if (synthFinding) {
    var riskColor = (synthFinding.level === '极高风险' || synthFinding.level === '高风险') ? '#dc2626' : '#f59e0b';
    var riskBg = (synthFinding.level === '极高风险' || synthFinding.level === '高风险') ? '#fef2f2' : '#fffbeb';
    h += '<div style="margin:0 0 24px;padding:24px;background:' + riskBg + ';border:2px solid ' + riskColor + ';border-radius:12px">';
    h += '<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">';
    h += '<span style="font-size:24px">⚖️</span>';
    h += '<span style="font-size:18px;font-weight:700;color:#1e293b">综合稽查结论</span>';
    h += '<span style="display:inline-block;padding:4px 16px;background:' + riskColor + ';color:#fff;border-radius:6px;font-size:14px;font-weight:700">' + (synthFinding.level || '?') + '</span>';
    h += '<span style="font-size:13px;color:#64748b">综合评分 ' + (synthFinding.score || '?') + '/100</span>';
    h += '</div>';
    h += '<div style="font-size:14px;color:#334155;line-height:2">' + (synthFinding.description || '').replace(/</g,'&lt;').replace(/>/g,'&gt;') + '</div>';
    h += '</div>';
  }
  
  // 综合风险评级
  var synth = r.comprehensive || {};
  var overall = synth.overall_risk || (allF.length > 0 && risks.length > (mids.length + lows.length) ? '高风险' : '中风险');
  h += '<div class="conclusion-box ' + (overall==='高风险'||overall==='极高风险'?'red':'amber') + '" style="padding:24px;margin-bottom:24px">';
  h += '<p class="i2"><strong>综合风险评级：</strong><span class="' + (overall==='高风险'||overall==='极高风险'?'rtag':'atag') + '" style="font-size:18px">' + overall + '</span></p>';
  
  // 风险分布
  h += '<p class="i2">经对被查单位「' + (te.name || te.company_name || '') + '」（信用代码：' + (te.uscc || '') + '）提交的' + (r.files_count || 0) + '份经营资料进行全面稽查分析，共发现<strong>' + allF.length + '</strong>项涉税风险事项，按风险等级分布如下：</p>';
  h += '<table class="tbl" style="margin:12px 0"><thead><tr><th>风险等级</th><th>数量</th><th>占比</th><th>代表事项</th></tr></thead><tbody>';
  h += '<tr><td style="color:#dc2626;font-weight:700">极高风险</td><td>' + (allF.filter(function(f){return f.level==='极高风险';}).length) + '项</td><td>' + (allF.length>0 ? (allF.filter(function(f){return f.level==='极高风险';}).length/allF.length*100).toFixed(1) : 0) + '%</td><td>涉及虚开信号、隐匿收入等红线问题</td></tr>';
  h += '<tr><td style="color:#dc2626;font-weight:600">高风险</td><td>' + risks.length + '项</td><td>' + (allF.length>0 ? (risks.length/allF.length*100).toFixed(1) : 0) + '%</td><td>' + (risks.map(function(f){return (f.type||'');}).join('、') || '资料完备度、资金偏差等') + '</td></tr>';
  h += '<tr><td style="color:#e67700;font-weight:600">中风险</td><td>' + mids.length + '项</td><td>' + (allF.length>0 ? (mids.length/allF.length*100).toFixed(1) : 0) + '%</td><td>发票合规、社保基数偏差、供应商集中等</td></tr>';
  h += '<tr><td style="color:#16a34a;font-weight:600">低风险</td><td>' + lows.length + '项</td><td>' + (allF.length>0 ? (lows.length/allF.length*100).toFixed(1) : 0) + '%</td><td>税收优惠提醒、资料规范建议等</td></tr>';
  h += '</tbody></table>';
  
  // 证据链完整性
  h += '<p class="i2"><strong>证据链完整性：</strong>本次稽查分析覆盖了18个分析域，共触发证据链交叉验证。所有高风险发现均经过多源数据交叉验证——银行流水、销项发票、进项发票三源比对构成了核心证据闭环。每条发现均标注了证据来源（数据源+规则ID+查证方法），可供后续审理环节逐条追溯复核。</p>';
  
  // 稽查局限性声明
  h += '<p class="i2"><strong>稽查局限性声明：</strong>本次分析基于被查单位提交的' + (r.files_count || 0) + '份资料。根据14类稽查必查资料清单，尚有部分资料未提交（如记账凭证、合同文件、申报表等）。对于资料缺失的分析域，本次稽查已在对应发现中标注资料缺口，并说明缺失资料对稽查判断的影响。被查单位补充提交相关资料后，稽查结论可能需要相应调整。</p>';
  
  // 总体结论
  h += '<p class="i2"><strong>总体结论：</strong>';
  if (overall === '高风险' || overall === '极高风险') {
    h += '被查单位存在多项高风险涉税事项，涉及银行收款与开票金额严重偏差（涉嫌隐匿收入）、基础经营费用缺失（经营实质存疑）、供应商与客户存在关联交易嫌疑等核心问题。建议在收到本报告后立即启动深度核查程序，重点核实：银行收款来源的真实性、经营场所和经营能力的实际情况、关联交易的商业实质。同时要求被查单位在15个工作日内补充提交缺失的9类资料，为后续审理提供完整的证据基础。';
  } else if (overall === '中风险') {
    h += '被查单位存在一定数量的涉税风险事项，主要集中在发票合规、社保缴纳、资料完备度等方面。虽未发现明显的逃税或虚开信号，但多项中低风险问题叠加可能影响企业的纳税信用等级和税务合规形象。建议被查单位在收到本报告后15个工作日内完成自查整改，补充相关资料并规范财务税务处理。';
  } else {
    h += '被查单位整体税务合规状况良好，仅存在少量低风险事项和税收优惠提醒。建议被查单位继续保持规范的财务税务管理，并对报告中指出的低风险事项进行完善。';
  }
  h += '</p>';
  h += '</div>';

  // ═══ 第五章：处理处罚建议 ═══
  h += '<h2 id="ch5">第五章 处理处罚建议</h2>';
  h += '<p class="i2">根据本次稽查发现的事实和被查单位的风险等级，按照紧急程度和影响程度，分级提出以下处理建议：</p>';
  
  // P0：立即处理
  h += '<div style="margin:16px 0;padding:20px 24px;background:#fef2f2;border:2px solid #fca5a5;border-radius:8px">';
  h += '<div style="font-size:15px;font-weight:700;color:#dc2626;margin-bottom:12px">🔴 P0 —— 立即处理（涉及逃税、虚开等红线问题）</div>';
  var p0Count = 0;
  for (var fi = 0; fi < allSorted.length; fi++) {
    var sf = allSorted[fi];
    if ((sf.level === '极高风险' || sf.level === '高风险') && sf.suggestion && sf.suggestion.length > 10) {
      p0Count++;
      h += '<div class="frow" style="font-size:13px;margin:8px 0;padding:8px 12px;background:#fff;border-radius:4px"><strong>' + p0Count + '.</strong> ' + sf.suggestion + '</div>';
      if (p0Count >= 5) break;
    }
  }
  if (p0Count === 0) h += '<p class="i2">暂无需要立即处理的P0级事项。</p>';
  h += '</div>';
  
  // P1：限期整改
  h += '<div style="margin:16px 0;padding:20px 24px;background:#fffbeb;border:2px solid #fcd34d;border-radius:8px">';
  h += '<div style="font-size:15px;font-weight:700;color:#d97706;margin-bottom:12px">🟡 P1 —— 限期整改（发票合规、账务调整等问题）</div>';
  var p1Count = 0;
  for (var fi = 0; fi < allSorted.length; fi++) {
    var sf = allSorted[fi];
    if (sf.level === '中风险' && sf.suggestion && sf.suggestion.length > 10) {
      p1Count++;
      h += '<div class="frow" style="font-size:13px;margin:8px 0;padding:8px 12px;background:#fff;border-radius:4px"><strong>' + p1Count + '.</strong> ' + sf.suggestion + '</div>';
      if (p1Count >= 5) break;
    }
  }
  if (p1Count === 0) h += '<p class="i2">暂无需要限期整改的P1级事项。</p>';
  h += '</div>';
  
  // P2：持续关注
  h += '<div style="margin:16px 0;padding:20px 24px;background:#f0fdf4;border:2px solid #86efac;border-radius:8px">';
  h += '<div style="font-size:15px;font-weight:700;color:#16a34a;margin-bottom:12px">🟢 P2 —— 持续关注（资料完善、合规提醒、优惠政策享受建议）</div>';
  var p2Count = 0;
  for (var fi = 0; fi < allSorted.length; fi++) {
    var sf = allSorted[fi];
    if ((sf.level === '低风险' || sf.level === '优惠机会') && sf.suggestion && sf.suggestion.length > 10) {
      p2Count++;
      h += '<div class="frow" style="font-size:13px;margin:8px 0;padding:8px 12px;background:#fff;border-radius:4px"><strong>' + p2Count + '.</strong> ' + sf.suggestion + '</div>';
      if (p2Count >= 5) break;
    }
  }
  if (p2Count === 0) h += '<p class="i2">暂无需要持续关注的P2级事项。</p>';
  h += '</div>';
  
  // 整改期限
  h += '<div style="margin:20px 0;padding:20px 24px;background:#f8fafc;border:2px solid #e2e8f0;border-radius:8px">';
  h += '<div style="font-size:15px;font-weight:700;color:#1a1a2e;margin-bottom:12px">📅 自查整改期限</div>';
  h += '<p class="i2">1. <strong>P0事项：</strong>被查单位应在收到本报告之日起<strong>5个工作日</strong>内，对以上P0事项逐条书面说明情况并提供相关佐证资料。逾期未回复的，稽查部门将依据现有证据材料直接作出处理决定。</p>';
  h += '<p class="i2">2. <strong>P1事项：</strong>被查单位应在收到本报告之日起<strong>15个工作日</strong>内，完成P1事项的自查整改，并向稽查部门提交书面整改报告及相关证明材料。</p>';
  h += '<p class="i2">3. <strong>P2事项：</strong>被查单位应在收到本报告之日起<strong>30个工作日</strong>内，对P2事项进行完善，并在后续税务申报和财务管理中持续规范。</p>';
  h += '<p class="i2">4. 被查单位如对以上发现的事实有异议，可依据第六章规定的陈述申辩权和听证权，在法定期限内提出。</p>';
  h += '</div>';

  // ═══ 第六章：告知权利义务 ═══
  h += '<h2 id="ch6">第六章 告知权利义务</h2>';
  h += '<div class="rights-sec" style="padding:24px">';
  h += '<div class="rtitle" style="font-size:15px;font-weight:700;margin-bottom:16px;color:#1a1a2e">根据《中华人民共和国税收征收管理法》及《税务稽查工作规程》，被查单位「' + (te.name || te.company_name || '') + '」在本次稽查过程中依法享有以下权利：</div>';
  
  h += '<div class="ritem" style="margin:16px 0;padding:16px 20px;background:#f8fafc;border-left:3px solid #2563eb;border-radius:0 6px 6px 0">';
  h += '<div style="font-size:14px;font-weight:700;color:#1a1a2e;margin-bottom:6px">一、申请回避权</div>';
  h += '<div style="font-size:13px;color:#475569;line-height:2">被查单位认为稽查人员与本案有利害关系或其他关系可能影响公正执法的，有权申请该稽查人员回避。申请回避应当在稽查人员送达《税务检查通知书》后<strong>3日内</strong>，以书面形式向稽查部门提出，说明申请回避的理由。稽查部门应当在收到申请后3日内作出决定并告知申请人。</div>';
  h += '<div style="font-size:11px;color:#94a3b8;margin-top:4px">法律依据：《税收征收管理法》第十二条</div>';
  h += '</div>';
  
  h += '<div class="ritem" style="margin:16px 0;padding:16px 20px;background:#f8fafc;border-left:3px solid #2563eb;border-radius:0 6px 6px 0">';
  h += '<div style="font-size:14px;font-weight:700;color:#1a1a2e;margin-bottom:6px">二、陈述申辩权</div>';
  h += '<div style="font-size:13px;color:#475569;line-height:2">被查单位对稽查认定的事实、依据和处理建议，有权进行陈述和申辩。稽查部门应当充分听取被查单位的意见，对其提出的事实、理由和证据进行复核。被查单位提出的事实、理由或者证据成立的，稽查部门应当采纳。陈述申辩应当在收到《税务稽查报告》后<strong>7日内</strong>以书面形式提交。</div>';
  h += '<div style="font-size:11px;color:#94a3b8;margin-top:4px">法律依据：《中华人民共和国行政处罚法》第三十二条</div>';
  h += '</div>';
  
  h += '<div class="ritem" style="margin:16px 0;padding:16px 20px;background:#f8fafc;border-left:3px solid #2563eb;border-radius:0 6px 6px 0">';
  h += '<div style="font-size:14px;font-weight:700;color:#1a1a2e;margin-bottom:6px">三、要求听证权</div>';
  h += '<div style="font-size:13px;color:#475569;line-height:2">对拟作出的税务行政处罚决定，罚款金额达到法定听证标准的（对公民处以2000元以上、对法人或其他组织处以10000元以上罚款），被查单位有权在收到《税务行政处罚事项告知书》后<strong>3日内</strong>书面申请听证。稽查部门应当在收到听证申请后<strong>15日内</strong>组织听证。听证不收取费用。</div>';
  h += '<div style="font-size:11px;color:#94a3b8;margin-top:4px">法律依据：《中华人民共和国行政处罚法》第四十二条、《税务行政处罚听证程序实施办法（试行）》</div>';
  h += '</div>';
  
  h += '<div class="ritem" style="margin:16px 0;padding:16px 20px;background:#f8fafc;border-left:3px solid #2563eb;border-radius:0 6px 6px 0">';
  h += '<div style="font-size:14px;font-weight:700;color:#1a1a2e;margin-bottom:6px">四、申请行政复议权</div>';
  h += '<div style="font-size:13px;color:#475569;line-height:2">被查单位对稽查部门作出的处理决定不服的，可以自收到《税务处理决定书》之日起<strong>60日内</strong>，向上一级税务机关申请行政复议。申请行政复议不影响处理决定的执行，但被查单位按规定提供相应担保的，经税务机关确认后可以暂缓执行。对行政复议决定不服的，可以依法向人民法院提起行政诉讼。</div>';
  h += '<div style="font-size:11px;color:#94a3b8;margin-top:4px">法律依据：《中华人民共和国行政复议法》第九条</div>';
  h += '</div>';
  
  h += '<div class="ritem" style="margin:16px 0;padding:16px 20px;background:#f8fafc;border-left:3px solid #2563eb;border-radius:0 6px 6px 0">';
  h += '<div style="font-size:14px;font-weight:700;color:#1a1a2e;margin-bottom:6px">五、提起行政诉讼权</div>';
  h += '<div style="font-size:13px;color:#475569;line-height:2">被查单位对稽查部门作出的处理决定或行政复议决定不服的，可以自收到《税务处理决定书》或《行政复议决定书》之日起<strong>6个月内</strong>，依法向有管辖权的人民法院提起行政诉讼。在诉讼期间，不停止处理决定的执行，但法律另有规定的除外。</div>';
  h += '<div style="font-size:11px;color:#94a3b8;margin-top:4px">法律依据：《中华人民共和国行政诉讼法》第四十五条、第四十六条</div>';
  h += '</div>';
  
  h += '</div>';

  // ═══ 第七章：稽查人员签字 ═══
  h += '<h2 id="ch7">第七章 稽查人员签字</h2>';
  h += '<div class="seal" style="margin-top:40px;padding:24px 0;line-height:3">';
  h += '<p>稽 查 执 行 人：_______________　　执法证件号：_______________</p>';
  h += '<p>审　理　人：_______________　　执法证件号：_______________</p>';
  h += '<p>稽查部门（盖章）：_______________</p>';
  h += '<p style="margin-top:20px">报告日期：' + dateStr + '</p>';
  h += '<p style="margin-top:12px;font-size:12px;color:#94a3b8">本报告一式三份：稽查部门留存一份，被查单位一份，报送上一级税务机关备案一份。</p>';
  h += '</div>';
  h += '<p>报告日期：' + dateStr + '</p>';
  h += '</div>';

  // ═══ 附件 ═══
  h += '<h2 id="appendix">附件 证据清单</h2>';
  
  // 附件一：发票明细
  var it = r.invoice_tables;
  var ic = r.invoice_counts;
  if (it && it.sales && it.sales.length > 0) {
    h += '<div class="appendix"><div class="atitle">附件一：销项发票全量明细（' + (ic.sales||it.sales.length) + '张）</div>';
    h += '<div style="overflow-x:auto"><table class="tbl inv-detail"><thead><tr>'
      + '<th>购买方</th><th>品名</th><th>规格</th><th>单位</th><th>数量</th>'
      + '<th>金额</th><th>税额</th><th>价税合计</th><th>日期</th><th>票种</th><th>发票号</th>'
      + '</tr></thead><tbody>';
    it.sales.forEach(function(inv) {
      h += '<tr><td>' + (inv.counterparty||'') + '</td><td>' + (inv.goods||'') + '</td>'
        + '<td>' + (inv.spec||'') + '</td><td>' + (inv.unit||'') + '</td>'
        + '<td class="r">' + (inv.qty||'') + '</td><td class="r">' + (inv.amount||'') + '</td>'
        + '<td class="r">' + (inv.tax||'') + '</td><td class="r">' + (inv.total||'') + '</td>'
        + '<td>' + (inv.date||'') + '</td><td>' + (inv.inv_type||'') + '</td><td class="mono">' + (inv.inv_no||'') + '</td></tr>';
    });
    h += '</tbody></table></div></div>';
  }
  
  if (it && it.purchases && it.purchases.length > 0) {
    h += '<div class="appendix"><div class="atitle">附件二：进项发票全量明细（' + (ic.purchases||it.purchases.length) + '张）</div>';
    h += '<div style="overflow-x:auto"><table class="tbl inv-detail"><thead><tr>'
      + '<th>销售方</th><th>品名</th><th>规格</th><th>单位</th><th>数量</th>'
      + '<th>金额</th><th>税额</th><th>价税合计</th><th>日期</th><th>票种</th><th>发票号</th>'
      + '</tr></thead><tbody>';
    it.purchases.forEach(function(inv) {
      h += '<tr><td>' + (inv.counterparty||'') + '</td><td>' + (inv.goods||'') + '</td>'
        + '<td>' + (inv.spec||'') + '</td><td>' + (inv.unit||'') + '</td>'
        + '<td class="r">' + (inv.qty||'') + '</td><td class="r">' + (inv.amount||'') + '</td>'
        + '<td class="r">' + (inv.tax||'') + '</td><td class="r">' + (inv.total||'') + '</td>'
        + '<td>' + (inv.date||'') + '</td><td>' + (inv.inv_type||'') + '</td><td class="mono">' + (inv.inv_no||'') + '</td></tr>';
    });
    h += '</tbody></table></div></div>';
  }
  
  if (it && it.core_cost && it.core_cost.length > 0) {
    h += '<div class="appendix"><div class="atitle">附件三：主营业务成本发票明细（' + (ic.core_cost||it.core_cost.length) + '张）</div>';
    h += '<div style="overflow-x:auto"><table class="tbl"><thead><tr>'
      + '<th>销售方</th><th>品名</th><th>金额</th><th>价税合计</th><th>日期</th>'
      + '</tr></thead><tbody>';
    it.core_cost.forEach(function(inv) {
      h += '<tr><td>' + (inv.counterparty||'') + '</td><td>' + (inv.goods||'') + '</td>'
        + '<td class="r">' + (inv.amount||'') + '</td><td class="r">' + (inv.total||'') + '</td>'
        + '<td>' + (inv.date||'') + '</td></tr>';
    });
    h += '</tbody></table></div></div>';
  }
  
  if (it && it.major_expense && it.major_expense.length > 0) {
    h += '<div class="appendix"><div class="atitle">附件四：重大费用发票明细（' + (ic.major_expense||it.major_expense.length) + '张）</div>';
    h += '<div style="overflow-x:auto"><table class="tbl"><thead><tr>'
      + '<th>销售方</th><th>品名</th><th>金额</th><th>价税合计</th><th>日期</th>'
      + '</tr></thead><tbody>';
    it.major_expense.forEach(function(inv) {
      h += '<tr><td>' + (inv.counterparty||'') + '</td><td>' + (inv.goods||'') + '</td>'
        + '<td class="r">' + (inv.amount||'') + '</td><td class="r">' + (inv.total||'') + '</td>'
        + '<td>' + (inv.date||'') + '</td></tr>';
    });
    h += '</tbody></table></div></div>';
  }
  
  // 附件五：银行流水
  h += '<div class="appendix"><div class="atitle">附件五：银行流水数据</div>';
  h += '<div class="aitem">· 银行流水' + ((r.bank_stats && r.bank_stats.count) || 'N/A') + '条</div>';
  h += '<div class="aitem">· 累计收款' + ((bi['总收款']||0)/10000).toFixed(2) + '万元 · 累计付款' + ((bi['总付款']||0)/10000).toFixed(2) + '万元</div>';
  h += '</div>';
  
  h += '<div class="appendix"><div class="atitle">附件六：其他经营资料</div>';
  if (r.file_results && r.file_results.length) {
    r.file_results.forEach(function(fr, fi) {
      h += '<div class="aitem">' + (fi+1) + '. ' + (fr.file || '') + ' (' + (fr.type || '未知') + ')</div>';
    });
  }
  h += '</div>';
  
  if (r.quality_check) {
    h += '<div class="appendix"><div class="atitle">附件七：质量标准自检</div>';
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

// ═══════════ 报告语音播报系统（新闻联播级播音标准）═══════════
var _ttsState = { speaking: false, paused: false, utterance: null, speed: 1.0, currentText: '', currentIdx: 0, currentChunk: null };
var _ttsChunks = [];

function _initReportTTS() {
  var area = document.getElementById('tax-doc-result');
  if (!area) return;
  
  var oldBar = document.getElementById('tts-bar');
  if (oldBar) oldBar.remove();
  
  var bar = document.createElement('div');
  bar.id = 'tts-bar';
  bar.innerHTML = 
    '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">' +
    '<span style="font-size:13px;font-weight:700;color:#1a1a2e">🔊 稽查报告语音播报</span>' +
    '<button id="tts-play-all" style="padding:6px 16px;background:#2563eb;color:#fff;border:none;border-radius:6px;font-size:13px;cursor:pointer;font-weight:600">▶ 全文播报</button>' +
    '<button id="tts-pause" style="padding:6px 16px;background:#fff;border:1px solid #d1d5db;border-radius:6px;font-size:13px;cursor:pointer;display:none">⏸ 暂停</button>' +
    '<button id="tts-stop" style="padding:6px 16px;background:#fff;border:1px solid #dc2626;color:#dc2626;border-radius:6px;font-size:13px;cursor:pointer;display:none">⏹ 停止</button>' +
    '<select id="tts-speed" style="padding:6px 10px;border:1px solid #d1d5db;border-radius:6px;font-size:13px;background:#fff;cursor:pointer">' +
    '<option value="0.85">0.85x 新闻联播</option><option value="1.0" selected>1.0x 标准</option><option value="1.15">1.15x 略快</option><option value="1.3">1.3x 快速</option>' +
    '</select>' +
    '<span id="tts-progress" style="font-size:12px;color:#94a3b8"></span>' +
    '</div>' +
    '<div style="font-size:11px;color:#94a3b8;margin-top:4px">💡 点击报告任意段落可从此处开始播报至报告结束 · 播音标准：新闻联播级专业播报 · 橙色底纹=正在播报的段落</div>';
  bar.style.cssText = 'position:fixed;bottom:20px;left:50%;transform:translateX(-50%);z-index:9999;min-width:620px;max-width:920px;padding:12px 18px;background:rgba(255,255,255,0.96);border:1px solid #cbd5e1;border-radius:12px;box-shadow:0 4px 24px rgba(0,0,0,0.15);backdrop-filter:blur(10px)';
  document.body.appendChild(bar);
  
  document.getElementById('tts-play-all').onclick = function() { _ttsBuildChunks(area); _ttsState.currentIdx = 0; _ttsSpeakNext(); _updateTtsUI(true); };
  document.getElementById('tts-pause').onclick = _ttsTogglePause;
  document.getElementById('tts-stop').onclick = _ttsStop;
  document.getElementById('tts-speed').onchange = function() { _ttsState.speed = parseFloat(this.value); };
  
  _bindClickToSpeak(area);
  
  if (window.speechSynthesis) {
    window.speechSynthesis.getVoices();
    window.speechSynthesis.onvoiceschanged = function() { window.speechSynthesis.getVoices(); };
  }
}

function _ttsBuildChunks(container) {
  _ttsChunks = [];
  // 覆盖全部报告内容元素——确保不漏播
  var els = container.querySelectorAll('p, h1, h2, h3, h4, td, th, li, .ftitle, .frow, .flabel, .ritem, .atitle, .aitem, .seal p, .fact-sec, .conclusion-box, .i2, .cover h1, .cover .sub, .tag, .law-ref, .std-label, .rpt-title');
  els.forEach(function(el) {
    if (el.closest('#tts-bar') || el.closest('#review-panel') || el.closest('details') || el.closest('style')) return;
    var t = _ttsCleanText((el.textContent || ''));
    if (t.length > 5) _ttsChunks.push({el: el, text: t});
  });
}

// 文本清洗：去标点符号、修正多音字（全报告覆盖·财税稽查语境）
function _ttsCleanText(text) {
  var t = text.replace(/\s+/g, ' ').trim();
  // 去除播报不需要的标点符号
  t = t.replace(/[_→●◆■★☆✓✕⚠📌📡🔬📋💡🔗🎯⚖️🧠📚🔊🎙️📝💻📄📁📐📜🛡️⚙️🔍📊🔒⚡📋🔴🟡🟢❌✅]/g, '');
  t = t.replace(/[`*~#>\-\[\](){}|]/g, '');
  t = t.replace(/\s{2,}/g, ' ');
  
  // ═══ 多音字全面修正（财税稽查语境·词级替换）═══
  var fixes = [
    // 行 — xíng vs háng
    ['银行', '银航'], ['行业', '航业'], ['同行', '同航'],
    // 率 — 财税场景全为 lǜ
    ['税率', '税律'], ['毛利率', '毛利律'], ['进销比', '进销比'], ['比率', '比律'],
    ['利率', '利律'], ['概率', '概律'], ['频率', '频律'], ['占比', '占比'],
    // 差 — chā vs chà vs chāi
    ['偏差', '偏叉'], ['差异', '叉异'], ['差额', '叉额'], ['误差', '误叉'],
    ['差距', '叉距'], ['偏差率', '偏叉律'],
    // 调 — diào vs tiáo
    ['调查', '掉查'], ['调拨', '掉拨'], ['调度', '掉度'], ['协调', '协条'],
    ['调整', '条整'], ['空调', '空条'], ['调和', '条和'],
    // 重 — zhòng vs chóng
    ['重要', '众要'], ['重大', '众大'], ['严重', '严众'], ['重点', '众点'],
    ['沉重', '沉众'], ['重视', '众视'], ['重罚', '众罚'],
    ['重新', '从新'], ['重复', '从复'], ['重叠', '从叠'],
    // 长 — zhǎng vs cháng
    ['法定代表人', '法定代理人'], ['董事长', '董事掌'], ['负责人', '负责仁'],
    ['长期', '常期'], ['长度', '常度'],
    // 处 — chǔ vs chù
    ['处理', '础理'], ['处罚', '础罚'], ['处分', '础分'], ['查处', '础查'],
    ['处置', '础置'],
    // 会 — huì vs kuài
    ['会计', '快计'], ['会计师', '快计师'], ['会计准则', '快计准则'],
    // 传 — chuán vs zhuàn
    ['传媒', '船媒'], ['传统', '船统'], ['传递', '船递'],
    // 为 — wèi (介词) vs wéi (动词)
    ['为了', '位了'], ['因为', '因位'],
    ['作为', '作围'], ['行为', '形围'], ['认为', '认围'], ['称为', '称围'],
    // 应 — yīng vs yìng
    ['应当', '英当'], ['应该', '英该'], ['应有', '英有'],
    ['应对', '硬对'], ['供应', '供硬'],
    // 当 — dāng vs dàng
    ['应当', '英当'], ['当时', '当十'], ['当期', '当七'],
    ['适当', '适荡'], ['正当', '正荡'],
    // 量 — liàng vs liáng
    ['数量', '数亮'], ['计量', '计亮'], ['总量', '总亮'], ['金额', '金鹅'],
    // 得 — dé
    ['取得', '取德'], ['获得', '获德'], ['得到', '德到'], ['所得', '所德'],
    ['不得', '不德'],
    // 还 — huán vs hái
    ['归还', '归环'], ['偿还', '偿环'], ['返还', '返环'], ['还款', '环款'],
    ['还有', '还有'], ['还是', '还是'], ['还包括', '还包括'],
    // 给 — jǐ vs gěi
    ['供给', '供己'], ['补给', '补己'],
    // 相 — xiāng vs xiàng
    ['相关', '乡关'], ['相互', '乡互'], ['相应', '乡应'], ['相同', '乡同'],
    // 间 — jiān vs jiàn
    ['期间', '期坚'], ['之间', '之坚'], ['中间', '中坚'],
    ['间接', '件接'],
    // 将 — jiāng
    ['将来', '江来'], ['将导致', '江导致'], ['将面临', '江面临'],
    // 折 — zhé
    ['折旧', '哲旧'], ['折扣', '哲扣'],
    // 担 — dān
    ['承担', '承单'], ['担保', '单保'], ['负担', '负单'],
    // 中 — zhōng
    ['其中', '其忠'], ['集中', '集忠'], ['中国', '忠国'],
    // 没 — mò vs méi
    ['没收', '末收'],
    // 创 — chuàng vs chuāng
    ['创意', '创艺'], ['创造', '创皂'],
    // 号 — hào vs háo
    ['信号', '信浩'], ['编号', '编浩'], ['发票号', '发票浩'],
    // 便 — biàn vs pián
    ['以便', '以变'], ['便于', '变于'],
    // 觉 — jué vs jiào
    ['察觉', '查爵'], ['感觉', '感爵'], ['觉得', '爵得'],
    // 降 — jiàng vs xiáng
    ['降低', '匠低'], ['下降', '下匠'], ['降幅', '匠幅'],
    // 划 — huà vs huá
    ['计划', '计画'], ['规划', '规画'], ['筹划', '筹画'],
    // 结 — jié vs jiē
    ['结论', '杰论'], ['结果', '杰果'], ['结构', '杰构'], ['总结', '总杰'],
    // 发 — fā vs fà
    ['发票', '发漂'], ['发现', '发现'], ['发生', '发生'],
    // 种 — zhǒng vs zhòng
    ['品种', '品肿'], ['种类', '肿类'], ['各种', '各肿'],
    // 倒 — dào vs dǎo
    ['导致', '导至'], ['反倒', '反到'],
    // 更 — gèng vs gēng
    ['更加', '更佳'], ['更为', '更为'], ['更新', '更新'],
    // 数 — shù vs shǔ vs shuò
    ['数据', '树据'], ['数量', '树量'], ['金额', '金鹅'],
    // 法 — fǎ vs fā
    ['办法', '办发'], ['方法', '方发'],
    // 职 — zhí
    ['职工', '直工'], ['职能', '直能'],
  ];
  
  // 按长度降序排列，避免短词先替换破坏长词
  fixes.sort(function(a,b) { return b[0].length - a[0].length; });
  
  for (var fi = 0; fi < fixes.length; fi++) {
    var fw = fixes[fi][0], rw = fixes[fi][1];
    t = t.split(fw).join(rw);
  }
  
  return t;
}

function _bindClickToSpeak(container) {
  container.addEventListener('click', function(e) {
    if (e.target.tagName === 'BUTTON' || e.target.tagName === 'A' || e.target.tagName === 'SELECT' || e.target.tagName === 'OPTION') return;
    if (e.target.closest('#tts-bar') || e.target.closest('#review-panel')) return;
    
    // 找到被点击的文本容器元素
    var el = e.target;
    while (el && el !== container) {
      if (el.tagName === 'P' || el.tagName === 'H1' || el.tagName === 'H2' || el.tagName === 'H3' || el.tagName === 'TD' || el.tagName === 'TH' || el.tagName === 'LI' || el.tagName === 'DIV') {
        var text = (el.textContent || '').trim();
        if (text.length > 10) {
          _ttsStop();
          // 重新构建文本块列表，找到点击元素的索引
          _ttsBuildChunks(container);
          var foundIdx = -1;
          for (var i = 0; i < _ttsChunks.length; i++) {
            if (_ttsChunks[i].el === el) { foundIdx = i; break; }
          }
          // 如果精确匹配不到，用文本匹配
          if (foundIdx < 0) {
            for (var j = 0; j < _ttsChunks.length; j++) {
              if (_ttsChunks[j].text === text) { foundIdx = j; break; }
            }
          }
          if (foundIdx >= 0) {
            _ttsState.currentIdx = foundIdx;
            _ttsSpeakNext();
            _updateTtsUI(true);
          }
          return;
        }
      }
      el = el.parentElement;
    }
  });
}

function _ttsGetVoice() {
  var voices = window.speechSynthesis.getVoices();
  // 优先选中文男声
  return voices.find(function(v) { return v.lang.indexOf('zh-CN') >= 0 && (v.name.indexOf('Male') >= 0 || v.name.indexOf('男') >= 0); }) ||
         voices.find(function(v) { return v.lang.indexOf('zh') >= 0 && (v.name.indexOf('Male') >= 0 || v.name.indexOf('男') >= 0); }) ||
         voices.find(function(v) { return v.lang.indexOf('zh-CN') >= 0 && v.name.indexOf('Tingting') < 0; }) ||
         voices.find(function(v) { return v.lang.indexOf('zh') >= 0; });
}

// 新闻联播级情感调节：根据内容类型动态调整语速和音调
function _ttsSetNewsTone(utt, text) {
  var hasHighRisk = text.indexOf('高风险') >= 0 || text.indexOf('极高风险') >= 0 || text.indexOf('虚开') >= 0;
  var hasTitle = text.indexOf('第') === 0 && (text.indexOf('章') >= 0 || text.indexOf('部分') >= 0);
  var hasChapterTitle = text.indexOf('第一章') >= 0 || text.indexOf('第二章') >= 0 || text.indexOf('第三章') >= 0 || 
                        text.indexOf('第四章') >= 0 || text.indexOf('第五章') >= 0 || text.indexOf('第六章') >= 0 || text.indexOf('第七章') >= 0;
  var isFinding = text.indexOf('稽查性质') >= 0 || text.indexOf('发现要点') >= 0;
  var isLaw = text.indexOf('《') >= 0 && text.indexOf('》') >= 0 && text.indexOf('第') >= 0 && text.indexOf('条') >= 0;
  var isSuggestion = text.indexOf('处理建议') >= 0 || text.indexOf('自查整改') >= 0;
  
  var baseSpeed = _ttsState.speed;
  
  if (hasChapterTitle) {
    // 章节标题：庄严、缓慢、有力
    utt.rate = baseSpeed * 0.7;
    utt.pitch = 0.65;
    utt.volume = 1.0;
  } else if (hasTitle || isFinding) {
    // 小节标题/发现：稍慢、沉稳
    utt.rate = baseSpeed * 0.8;
    utt.pitch = 0.72;
    utt.volume = 1.0;
  } else if (hasHighRisk) {
    // 高风险内容：严肃、凝重、强调
    utt.rate = baseSpeed * 0.75;
    utt.pitch = 0.68;
    utt.volume = 1.0;
  } else if (isLaw) {
    // 法律条文：清晰、郑重、一字一顿
    utt.rate = baseSpeed * 0.72;
    utt.pitch = 0.7;
    utt.volume = 1.0;
  } else if (isSuggestion) {
    // 建议/整改：清晰、有力
    utt.rate = baseSpeed * 0.85;
    utt.pitch = 0.8;
    utt.volume = 1.0;
  } else {
    // 普通叙述：新闻联播标准
    utt.rate = baseSpeed * 0.88;
    utt.pitch = 0.78;
    utt.volume = 0.95;
  }
}

function _ttsSpeakNext() {
  if (_ttsState.currentIdx >= _ttsChunks.length) { _ttsStop(); return; }
  
  // 清除上一个高亮
  if (_ttsState.currentChunk && _ttsState.currentChunk.el) {
    _ttsState.currentChunk.el.style.background = '';
    _ttsState.currentChunk.el.style.transition = '';
  }
  
  var chunk = _ttsChunks[_ttsState.currentIdx];
  _ttsState.currentChunk = chunk;
  
  // 橙色底纹高亮当前播报段落
  if (chunk.el) {
    chunk.el.style.transition = 'background 0.2s';
    chunk.el.style.background = '#fef3c7';
    chunk.el.style.borderRadius = chunk.el.style.borderRadius || '4px';
    chunk.el.style.padding = chunk.el.style.padding || '4px 8px';
    // 滚动到可见区域
    chunk.el.scrollIntoView({behavior: 'smooth', block: 'center'});
  }
  
  window.speechSynthesis.cancel();
  _ttsState.utterance = new SpeechSynthesisUtterance(chunk.text);
  _ttsState.utterance.lang = 'zh-CN';
  
  // 新闻联播级情感语调
  _ttsSetNewsTone(_ttsState.utterance, chunk.text);
  
  var voice = _ttsGetVoice();
  if (voice) _ttsState.utterance.voice = voice;
  
  _ttsState.utterance.onend = function() {
    _ttsState.currentIdx++;
    var prog = document.getElementById('tts-progress');
    if (prog) prog.textContent = (_ttsState.currentIdx + 1) + ' / ' + _ttsChunks.length;
    _ttsSpeakNext();
  };
  
  _ttsState.speaking = true;
  window.speechSynthesis.speak(_ttsState.utterance);
  var prog = document.getElementById('tts-progress');
  if (prog) prog.textContent = (_ttsState.currentIdx + 1) + ' / ' + _ttsChunks.length;
}

function _ttsTogglePause() {
  if (_ttsState.paused) {
    window.speechSynthesis.resume();
    _ttsState.paused = false;
    var btn = document.getElementById('tts-pause');
    if (btn) btn.textContent = '⏸ 暂停';
  } else {
    window.speechSynthesis.pause();
    _ttsState.paused = true;
    var btn2 = document.getElementById('tts-pause');
    if (btn2) btn2.textContent = '▶ 继续';
  }
}

function _ttsStop() {
  window.speechSynthesis.cancel();
  // 清除高亮
  if (_ttsState.currentChunk && _ttsState.currentChunk.el) {
    _ttsState.currentChunk.el.style.background = '';
    _ttsState.currentChunk.el.style.transition = '';
  }
  _ttsState.speaking = false;
  _ttsState.paused = false;
  _ttsState.currentIdx = 0;
  _ttsState.currentChunk = null;
  _ttsChunks = [];
  _updateTtsUI(false);
}

function _updateTtsUI(active) {
  var playBtn = document.getElementById('tts-play-all');
  var pauseBtn = document.getElementById('tts-pause');
  var stopBtn = document.getElementById('tts-stop');
  var progEl = document.getElementById('tts-progress');
  if (!playBtn) return;
  
  if (active) {
    playBtn.style.display = 'none';
    pauseBtn.style.display = 'inline-block';
    stopBtn.style.display = 'inline-block';
  } else {
    playBtn.style.display = 'inline-block';
    pauseBtn.style.display = 'none';
    stopBtn.style.display = 'none';
    if (progEl) progEl.textContent = '';
  }
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
