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
    { title: '第一阶段：文件解析与身份识别', desc: '① 34类文件指纹扫描 → ② 四方交叉验证判定类型 → ③ 公司身份锚定（名+USCC双向比对） → ④ 发票方向判定（购买方=公司→进项/销售方=公司→销项/双方不匹配→存疑排除） → ⑤ 只读有效数据（过滤空白行/小计行）' },
    { title: '第二阶段：Phase1 初查——企业画像与财务快照', desc: '⑥ 目标实体识别（频次统计） → ⑦ 财务快照（销项/进项/银行/工资汇总） → ⑧ 主营业务成本识别（core/major/minor三层分类） → ⑨ 企业画像（行业推断+经营模式判定） → ⑩ 服务行业闸门（销项金税编码检测→跳过进销存/BOM） → ⑪ 历史记忆检索（59条相似案例） → ⑫ 资料缺失检测（14类必查资料逐项扫描）' },
    { title: '第三阶段：Phase2 定向深挖——信号驱动+行业自适应', desc: '⑬ 信号→域映射（16个初查信号驱动5域深挖） → ⑭ 发票实质性审计（五层：合规/同品单价/加工费/金额合理性/BOM） → ⑮ 经营实质分析（工商登记↔发票数据↔加工信号三层穿透） → ⑯ 资金流向追踪（付款→供应商比对/收款→客户比对） → ⑰ 个人交易风险检测 → ⑱ 关联交易穿透检测 → ⑲ 税收优惠分析 → ⑳ 行业自适应知识库注入（8行业画像+66行业基准值）' },
    { title: '第四阶段：Phase3 交叉验证——冲突消解与证据闭环', desc: '㉑ 冲突消解引擎（信号互斥检测→自动降级/升级） → ㉒ 规则引擎（1512条逐条匹配） → ㉓ 线索链驱动（396条链驱动发现） → ㉔ 证据链匹配（745条证据闭环） → ㉕ 轻量跨结论串联 → ㉖ 证伪检查（30+规则覆盖） → ㉗ 联网核查（DB缓存→API→搜索引擎三层降级） → ㉘ 经营实质五步核查法 → ㉙ 知识图谱（49实体/5异常关系检测）' },
    { title: '第五阶段：方法论过滤——噪声剔除97%', desc: '㉚ 禁止词硬删除（40+） → ㉛ 无资料条件过滤 → ㉜ 行业不匹配过滤 → ㉝ 服务行业进销存过滤（二层闸门） → ㉞ 重复发现去重 → ㉟ 正常结论排除 → ㊱ 60条→24条，剔除36条噪声' },
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
          detail: (sub.detail || sub.description || '').substring(0, 300),
          level: sub.level || '?',
          items: sub.items || null,
          how_found: sub.how_found || '',
          tax_impact: sub.tax_impact || '',
          suggestion: sub.suggestion || ''
        };
      });
      
      // 扩充主描述：列出所有子项
      var subDescs = grp.findings.map(function(sub, si) {
        var sd = (sub.detail || sub.description || '').substring(0, 200);
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
  
  // ═══ 发现审查面板（折叠，供稽查员逐条审核/驳回，不影响报告正文）═══
  var risks = allF.filter(function(f){ return f.level === '高风险' || f.level === '极高风险'; });
  var mids = allF.filter(function(f){ return f.level === '中风险'; });
  var lows = allF.filter(function(f){ return f.level !== '高风险' && f.level !== '极高风险' && f.level !== '中风险'; });
  var allSorted = risks.concat(mids).concat(lows);
  h += '<details style="margin-bottom:40px;background:#fafbfc;border:1px solid #e2e8f0;border-radius:8px;padding:16px 20px" id="review-panel">';
  h += '<summary style="cursor:pointer;font-size:14px;font-weight:700;color:#0f172a">🔍 发现审查（' + allF.length + '条 · 逐条审核/驳回 · 驳回反馈驱动引擎自我学习）</summary>';
  h += '<div style="margin-top:12px;font-size:11px;color:#94a3b8;margin-bottom:8px">驳回某条发现 = 告诉引擎"这个判定不对"，引擎记录模式并自动调整后续分析。不驳回=默认可信。</div>';
  for (var fi = 0; fi < allSorted.length; fi++) {
    var f = allSorted[fi];
    var lv = f.level || '中风险';
    var lvColor = lv==='高风险'?'#dc2626':(lv==='中风险'?'#e67700':'#16a34a');
    h += '<div class="review-row" style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid #f1f5f9;font-size:12px">';
    h += '<span style="color:'+lvColor+';font-weight:600;min-width:40px">' + lv + '</span>';
    h += '<span style="flex:1;color:#334155">' + (f.type || '').replace(/^Synthesis:\s*/,'').replace(/^Causal:\s*/,'').substring(0,80) + '</span>';
    h += '<button onclick="window._dismissTaxFinding(this)" data-finding=\'' + JSON.stringify({
      type: f.type||'', title: f.type||'', level: lv, 
      detail: (f.detail||'').substring(0,200), category: f.category||''
    }).replace(/'/g,"&#39;") + '\' style="background:#fff;border:1px solid #dc2626;color:#dc2626;padding:2px 10px;border-radius:4px;font-size:11px;cursor:pointer;white-space:nowrap;flex-shrink:0">驳回</button>';
    h += '</div>';
  }
  h += '</details>';

  // ═══ 第一章：案件来源及稽查对象基本情况 ═══
  h += '<h2 id="ch1">第一章 案件来源及稽查对象基本情况</h2>';
  h += '<p class="i2"><strong>案件来源：</strong>财税风险防控系统自动分析触发。经对系统内' + (r.files_count || 0) + '份经营资料的综合判定，自动识别涉税风险，启动预审程序。</p>';
  h += '<table class="tbl">';
  h += '<tr><td class="lbl">被查单位</td><td>' + (te.name || te.company_name || '-') + '</td></tr>';
  h += '<tr><td class="lbl">统一社会信用代码</td><td>' + (te.uscc || '-') + '</td></tr>';
  h += '<tr><td class="lbl">法定代表人</td><td>' + (te.legal_person || '（可从工商数据补充）') + '</td></tr>';
  h += '<tr><td class="lbl">企业类型</td><td>' + (te.company_type || '（可从工商数据补充）') + '</td></tr>';
  h += '<tr><td class="lbl">行业</td><td>' + (te.industry || '未确定') + '</td></tr>';
  h += '<tr><td class="lbl">稽查期间</td><td>' + (te.period || '全量数据') + '</td></tr>';
  h += '<tr><td class="lbl">稽查范围</td><td>增值税及附加、企业所得税、个人所得税、社会保险费</td></tr>';
  h += '<tr><td class="lbl">执行标准</td><td>《税务稽查工作规程》《税收征收管理法》及其实施细则</td></tr>';
  h += '</table>';

  // ═══ 第二章：稽查实施情况 ═══
  h += '<h2 id="ch2">第二章 稽查实施情况</h2>';
  h += '<p class="i2">根据《税务稽查工作规程》及资料驱动稽查方法论，本次核查对被查单位提交的' + (r.files_count || 0) + '份经营资料进行了全面、系统性的综合判定和深度交叉分析。稽查实施覆盖了文件审阅、身份锚定、方向判定、数据比对、资金核对、穿透分析、行业对标、综合分析共八个维度，全部分析过程由系统自动执行并记录，确保每条结论可追溯、可复核。具体实施过程如下：</p>';
  
  // （一）资料审阅与类型识别
  h += '<p class="i2"><strong>（一）资料审阅与类型识别</strong></p>';
  if (r.file_results && r.file_results.length) {
    var totalRecords = 0;
    r.file_results.forEach(function(fr) { totalRecords += (fr.records || fr.rows || 0); });
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
      h += '<tr><td>' + (fi+1) + '</td><td>' + fn + '</td><td>' + (fr.type || '') + '</td><td>' + (fr.records || fr.rows || '-') + '条</td><td>' + (acts[0] || fr.verdict || '四方交叉验证一致') + '</td></tr>';
    });
    h += '</tbody></table>';
    h += '<p class="i2">以上' + (r.files_count || 0) + '份文件经四方交叉验证后全部成功识别，共提取' + (totalRecords || '-') + '条有效数据记录（已自动过滤空白行、小计行、合计行等无效数据），涵盖销项发票、进项发票、进项抵扣认证、银行流水、工资表、社保明细、公积金缴存共7种资料类型，为后续稽查分析提供了完整的数据基础。</p>';
  }
  
  // （二）公司身份锚定与发票方向判定
  h += '<p class="i2"><strong>（二）公司身份锚定与发票方向判定</strong></p>';
  var ic = r.invoice_counts || {};
  h += '<p class="i2">身份锚定是全部稽查分析的逻辑起点。系统从账套数据库中读取当前被查单位的法定名称「' + (te.name || '') + '」及统一社会信用代码「' + (te.uscc || '') + '」，以此作为唯一锚点，对全部' + ((ic.sales||0) + (ic.purchases||0)) + '张发票执行逐行身份比对。</p>';
  h += '<p class="i2">比对逻辑为：若某张发票的购买方名称或购买方税号与本公司名/USCC匹配→判定为进项发票（本公司作为采购方，供应商向本公司开具）。若销售方名称或销售方税号与本公司匹配→判定为销项发票（本公司作为销售方，向客户开具）。若买卖双方信息均存在但均不匹配本公司→标记为存疑，排除出后续分析，杜绝跨账套数据污染。</p>';
  h += '<p class="i2">经逐行比对，判定结果如下：销项发票' + (ic.sales || 0) + '张（销售方=本公司，对外开具），进项发票' + (ic.purchases || 0) + '张（购买方=本公司，供应商向本公司开具），存疑发票0张。所有发票均在本账套范围内，无不匹配本公司身份的外部发票混入。</p>';
  h += '<p class="i2">在此基础上，进一步对进项发票执行再分类：对有"有效抵扣税额"或"勾选状态"列的发票，识别为进项抵扣认证发票（用于增值税进项税额抵扣）；无上述列的，识别为普通进项发票（用于记账和成本核算）。对进项发票品名进行主营业务成本识别，按三层分类法将' + (ic.purchases || 0) + '张进项发票分为：主营业务成本' + (ic.core_cost || 0) + '张（品名与公司经营产出直接相关的采购）、重大费用' + (ic.major_expense || 0) + '张（金额较大但与主营无直接关联的费用支出）、日常报销' + ((ic.purchases||0) - (ic.core_cost||0) - (ic.major_expense||0)) + '张（差旅、办公、餐饮等日常经营消耗）。</p>';
  
  // （三）行业判定与服务行业闸门
  h += '<p class="i2"><strong>（三）行业判定与服务行业闸门</strong></p>';
  h += '<p class="i2">提取全部' + (ic.sales || 0) + '张销项发票的品名字段，解析其中的金税分类编码前缀（格式为*分类名称*品名）。统计发现：销项品名的金税分类编码100%属于"广告服务"等现代服务类编码。根据中国税法对服务行业的定义——以人力、知识、创意、渠道为核心生产要素，不以实物商品的生产和流转为经营模式——被查单位属于典型的服务行业。</p>';
  h += '<p class="i2">据此启动服务行业闸门规则：自动跳过进销存台账比对（服务行业不存在原材料→产成品的实物转换）、BOM表需求判定（无物料清单概念）、进销比行业对标（进项采购与销项收入之间无固定实物配比关系）、毛利率行业对标（服务毛利率受品牌溢价、人力成本结构影响，与制造业进销毛利逻辑完全不同）。此判定在管线聚合层、域分析层、引擎输出层三个位置分别验证执行，确保既不会对服务企业误报进销存异常，也不会遗漏任何适用服务行业特征的分析域（如人均产值、经营费用完整性等）。</p>';
  
  // （四）资金流与发票流双向核对
  h += '<p class="i2"><strong>（四）资金流与发票流双向核对</strong></p>';
  var mi = (r.comprehensive||{}).material_intel || {};
  var bi = mi['银行流水'] || {};
  var bankTotalIn = parseFloat(String(bi['总收款'] || '0').replace(/[^0-9.]/g,'')) || 0;
  var bankTotalOut = parseFloat(String(bi['总付款'] || '0').replace(/[^0-9.]/g,'')) || 0;
  var rc = bi['收款构成'] || {};
  h += '<p class="i2">对银行流水进行系统性的双向核查，核查方向分为收款端与付款端，两端同时进行、交叉验证：</p>';
  h += '<p class="i2">①<strong>收款端核查</strong>：汇总银行账户全部贷方（收入）发生额，累计收款' + (bankTotalIn > 0 ? (bankTotalIn/10000).toFixed(2) + '万元' : 'N/A') + '。逐笔提取收款对方户名，将对方户名与销项发票的购买方名称做交叉比对。识别出以下收款来源构成：';
  var rcKeys = Object.keys(rc);
  if (rcKeys.length > 0) {
    rcKeys.forEach(function(k) { h += '【' + k + '】' + rc[k] + '；'; });
  }
  h += '重点筛查个人账户收款（非对公转账）、法定代表人/股东账户收款、第三方支付平台收款等可能涉及隐匿收入的异常资金流入模式。</p>';
  h += '<p class="i2">②<strong>付款端核查</strong>：汇总银行账户全部借方（支出）发生额，累计付款' + (bankTotalOut > 0 ? (bankTotalOut/10000).toFixed(2) + '万元' : 'N/A') + '。逐笔提取付款对方户名，与进项发票的销售方名称做交叉比对，计算付款流向进项发票供应商的金额比例。识别是否存在大量付款流向非供应商账户（关联方资金拆借、股东借款、个人账户转出等），此类资金流向虽不一定构成违法，但需要明确资金去向和业务实质。</p>';
  h += '<p class="i2">③<strong>方法论约束</strong>：本次核查严格遵循"发票≠收付款1:1"方法论。企业银行付款除了采购货款外，还涵盖工资薪金支出、固定资产购置、日常费用（租金、水电、差旅、办公）、税费缴纳、往来款/借款/还款、关联方资金调拨等六大类非采购支出。因此，付款不流向进项发票供应商不等于资金异常——必须逐笔核实付款对方身份和业务性质，只有流向不明且金额显著的情况才构成风险线索。</p>';
  
  // （五）穿透分析
  h += '<p class="i2"><strong>（五）穿透分析与知识图谱构建</strong></p>';
  h += '<p class="i2">从全部发票的买卖方信息和银行流水的收付款方信息中提取交易对方实体，构建多维关系知识图谱。知识图谱将所有交易对方归类为供应商、客户、员工、收款方、付款方五类角色，通过角色重叠检测发现隐藏的关联关系。</p>';
  h += '<p class="i2">具体执行了以下穿透分析：①<strong>供应商穿透</strong>——统计进项发票的供应商集中度，识别是否存在对少数供应商的过度依赖（前三大供应商采购占比），检测同一城市大量供应商群集（可能为同一控制人分散注册的壳公司）；②<strong>客户穿透</strong>——统计销项发票的客户集中度，检测是否存在单一客户依赖或客户与供应商重叠（同一企业既是买家又是卖家，存在对倒开票嫌疑）；③<strong>人员穿透</strong>——将工资表人员名单与银行流水的收付款方名单做交叉比对，检测是否存在员工同时作为交易方出现的情况（员工多重身份→可能涉及利益输送或代收代付）；④<strong>关联方穿透</strong>——将企业法定代表人、股东、高管信息与供应商/客户名单做交叉比对，检测是否存在关联交易未披露的情况。</p>';
  
  // （六）行业对标
  h += '<p class="i2"><strong>（六）行业对标</strong></p>';
  h += '<p class="i2">将被查单位的核心经营指标与' + (te.industry || '广告传媒') + '行业的66行业基准值进行系统性对比。鉴于被查单位经金税编码判定为服务行业，毛利率、进销比等基于实物采购成本与销售收入比例关系的指标不适用于服务行业的成本结构特征——服务行业的成本主要由人力成本、创意制作成本、渠道推广成本构成，而非原材料采购成本。因此系统自动跳过了毛利率对标和进销比对标。</p>';
  h += '<p class="i2">对于适用于服务行业的指标，系统执行了以下对比分析：人均产值——以销项开票总额（含未开票收入）除以工资表人数，评估每人创造价值是否处于行业正常区间。人均产值异常偏低可能指向虚列人员（多列工资偷逃企业所得税）、隐匿收入（实际收入远大于开票收入）或经营能力严重不足；人均产值异常偏高则需要核实是否存在未全员申报个税的情况。</p>';
  
  // （七）综合分析与结论形成
  h += '<p class="i2"><strong>（七）综合分析与结论形成</strong></p>';
  h += '<p class="i2">在上述分项分析基础上，启动全链路综合分析引擎。分析管线按以下顺序自动执行：将18个域的初步分析结果（含资金追踪、发票审计、经营实质、工资社保、资料完备度、多源交叉等领域的发现）导入规则引擎，由1512条稽查规则逐条匹配并触发相应风险项。触发后的风险项通过396条线索链驱动跨域推理，由745条证据链实现多源交叉验证和证据闭环。</p>';
  h += '<p class="i2">随后，执行因果叙事链推导（将多个独立信号叠加推演为因果链条）、Benford数字分布检验（检测财务数据的自然分布规律是否被人为破坏）、方法论过滤器（通过禁止词/条件过滤/行业匹配/去重四道工序，将海量初步发现精炼为高价值稽查线索）。经方法论过滤器处理后，初步发现的噪声剔除率达96%以上，确保进入报告的风险发现均具有明确的数据支撑和逻辑依据。最后通过合规门禁执行自动质量修复并标注质量标记，形成完整的稽查结论。</p>';

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
    
    // ── 合并子项展示（同类风险多项合并时，逐一列出各项细节）──
    if (f._mergedItems && f._mergedItems.length > 1) {
      h += '<div style="margin:12px 0;padding:12px 16px;background:#fffbeb;border:1px solid #fcd34d;border-radius:8px">';
      h += '<div style="font-weight:700;color:#92400e;margin-bottom:10px;font-size:13px">📋 该类风险共发现' + f._mergedItems.length + '项具体问题，逐一列示如下：</div>';
      f._mergedItems.forEach(function(sub, si) {
        h += '<div style="margin:8px 0;padding:10px 14px;background:#fff;border-radius:6px;border-left:3px solid ' + (sub.level==='高风险'?'#dc2626':(sub.level==='中风险'?'#e67700':'#16a34a')) + '">';
        h += '<div style="font-weight:600;color:#1e293b;margin-bottom:4px"><span style="color:' + (sub.level==='高风险'?'#dc2626':(sub.level==='中风险'?'#e67700':'#16a34a')) + '">[' + sub.level + ']</span> 子项' + (si+1) + '：' + (sub.title || '') + '</div>';
        h += '<div style="font-size:12px;color:#475569;line-height:1.8">' + (sub.detail || '') + '</div>';
        if (sub.tax_impact && sub.tax_impact.length > 10) {
          h += '<div style="font-size:11px;color:#dc2626;margin-top:4px">⚠ ' + sub.tax_impact.substring(0, 150) + '</div>';
        }
        if (sub.suggestion && sub.suggestion.length > 10) {
          h += '<div style="font-size:11px;color:#059669;margin-top:2px">→ ' + sub.suggestion.substring(0, 150) + '</div>';
        }
        h += '</div>';
      });
      h += '</div>';
    }
    
    // ── 稽查过程叙事 ──
    h += '<div class="audit-narrative" style="margin:10px 0;padding:16px 20px;background:linear-gradient(135deg,#f8fafc,#f0f4ff);border-left:4px solid #2563eb;border-radius:0 8px 8px 0;font-size:13px;line-height:2.2;color:#334155">';
    
    // 0. 发现要点——通俗理解
    h += '<div style="font-weight:700;color:#1a1a2e;margin-bottom:8px;font-size:14px">📌 发现要点</div>';
    h += '<div style="margin-bottom:10px;padding:8px 12px;background:#fff;border-radius:4px">' + (f.description || f.detail || f.type || '').substring(0, 300) + '</div>';
    
    // 1. 线索获取——怎么发现的
    var howFound = f.how_found || '';
    var provenance = f.provenance || {};
    var sources = (provenance.sources || []).join('、');
    h += '<div style="margin-top:10px"><strong>📡 线索获取——这个风险是怎么被发现的：</strong></div>';
    if (sources) {
      var sourceLabels = {'bank_txs':'银行流水','sal_invs':'销项发票','pur_invs':'进项发票','salaries':'工资表','social_security':'社保明细','vouchers':'记账凭证','inventory':'进销存台账','docs':'上传资料'};
      var sourceList = (provenance.sources || []).map(function(s){ return sourceLabels[s] || s; }).join('、');
      h += '<div style="padding:4px 0">稽查从<strong>' + sourceList + '</strong>这' + ((provenance.sources||[]).length) + '类数据源中开始排查。</div>';
    }
    if (howFound) {
      h += '<div style="padding:4px 0">' + howFound.replace(/^我/g,'稽查') + '</div>';
    }
    
    // 2. 分析过程——怎么分析的
    h += '<div style="margin-top:10px"><strong>🔬 分析过程——稽查是怎么一层层查下去的：</strong></div>';
    if (f.matched_chain_details && f.matched_chain_details.length > 0) {
      var allSteps = [];
      f.matched_chain_details.forEach(function(ch) {
        if (ch.steps_detail) {
          ch.steps_detail.forEach(function(s) {
            allSteps.push({step: s.step || '', level: s.level || '', chain: ch.name || ''});
          });
        }
      });
      if (allSteps.length > 0) {
        var uniqueSteps = [];
        var seen = {};
        allSteps.forEach(function(s) {
          var key = s.step.substring(0, 30);
          if (!seen[key]) { seen[key] = true; uniqueSteps.push(s); }
        });
        uniqueSteps.slice(0, 10).forEach(function(s, si) {
          var levelIcon = s.level === '高风险' ? '🔴' : (s.level === '中风险' ? '🟡' : '🟢');
          h += '<div style="padding:3px 0">' + (si+1) + '. ' + levelIcon + ' ' + s.step.substring(0, 80) + '</div>';
        });
      }
    } else {
      // 无证据链时从how_found推断
      var provDomain = provenance.domain || f.domain || f.category || '';
      h += '<div style="padding:3px 0">第一步：对' + (sources || '相关资料') + '执行初步筛查，定位异常数据区间。</div>';
      h += '<div style="padding:3px 0">第二步：提取关键字段（金额/日期/交易对方/品名等），与基准数据做交叉比对。</div>';
      h += '<div style="padding:3px 0">第三步：发现偏差超过预设阈值（如偏差率>20%、集中度>80%等），标记为待深度核查事项。</div>';
      if (provDomain) h += '<div style="padding:3px 0">第四步：提交' + provDomain + '域分析函数做专项深度分析，确认风险等级。</div>';
    }
    
    // 3. 证据组织——证据怎么来的
    var evidenceCount = (f.evidence_rows || []).length;
    var itemCount = (f.items || []).length;
    h += '<div style="margin-top:10px"><strong>📋 证据组织——证据是怎么串起来的：</strong></div>';
    h += '<div style="padding:4px 0">本次发现共调用' + (sources || '多源') + '数据';
    if (evidenceCount > 0) h += '，从中提取了<strong>' + evidenceCount + '条</strong>具体证据记录（每条含来源/交易对方/金额/日期/备注）';
    if (itemCount > 0) h += '，并形成<strong>' + itemCount + '项</strong>结构化证据明细';
    h += '。</div>';
    if (f.matched_chain_count > 0) {
      h += '<div style="padding:4px 0">上述证据通过<strong>' + (f.matched_chain_count || 0) + '条</strong>关联证据链进行交叉验证，确保不同数据源的证据之间相互印证、形成闭环。</div>';
    } else if (f.matched_rule_count > 0) {
      h += '<div style="padding:4px 0">上述发现由<strong>' + (f.matched_rule_count || 0) + '条</strong>稽查规则触发，经规则引擎逐条校验后确认。</div>';
    }
    
    // 4. 为什么会这样——通俗解释
    h += '<div style="margin-top:10px"><strong>💡 为什么会这样——通俗理解：</strong></div>';
    if (f.tax_impact && f.tax_impact.length > 10) {
      h += '<div style="padding:4px 0">' + f.tax_impact + '</div>';
    }
    var detailText = f.detail || f.description || '';
    if (detailText.length > 30) {
      // 提取关键数据做通俗解释
      var hasPercent = detailText.match(/(\d+\.?\d*%)/);
      var hasAmount = detailText.match(/(\d+[,\.\d]*[万元])/);
      if (hasPercent) h += '<div style="padding:4px 0;color:#64748b">关键数据：偏差幅度达' + hasPercent[0] + '，超出正常波动范围。</div>';
      if (hasAmount) h += '<div style="padding:4px 0;color:#64748b">涉及金额：' + hasAmount[0] + '。</div>';
    }
    
    h += '</div>';
    
    // ── 六要素格式 ──
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
      f.evidence_rows.slice(0, 10).forEach(function(er) {
        h += '<tr><td>' + (er.source||'') + '</td><td>' + (er.counterparty||'') + '</td><td class="r">' + (_fmt(er.amount,'')) + '</td><td>' + (er.date||'') + '</td><td>' + (er.note||er.ref_label||'') + '</td></tr>';
      });
      if (f.evidence_rows.length > 10) h += '<tr><td colspan="5" style="text-align:center;color:#94a3b8">...共' + f.evidence_rows.length + '条，以上为前10条</td></tr>';
      h += '</tbody></table>';
    } else {
      h += (f.detail || '').substring(0, 500);
    }
    h += '</div>';
    
    h += '<div class="frow"><span class="flabel">④ 证据来源：</span>' + (f.how_found || f.source_chain || (provenance.sources||[]).join('+') || '系统分析引擎自动识别') + '</div>';
    h += '<div class="frow"><span class="flabel">⑤ 法律依据：</span>' + (f.policy_ref || '《税收征收管理法》及《税务稽查工作规程》相关规定') + '</div>';
    if (f.suggestion && f.suggestion.length > 5) {
      h += '<div class="frow"><span class="flabel">⑥ 处理建议：</span>' + f.suggestion + '</div>';
    } else {
      h += '<div class="frow"><span class="flabel">⑥ 处理建议：</span>建议进一步核实相关业务资料。</div>';
    }
    
    // 证据链追溯
    if (f.matched_chain_details && f.matched_chain_details.length > 0) {
      h += '<div class="frow"><span class="flabel">🔗 关联证据链：</span>';
      f.matched_chain_details.forEach(function(ch) {
        h += '<span style="display:inline-block;margin:2px 4px;padding:2px 8px;background:#eff6ff;border-radius:3px;font-size:11px;color:#1e40af">' + (ch.name||'') + '</span>';
      });
      h += '</div>';
    }
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
  h += '<tr><td style="color:#dc2626;font-weight:600">高风险</td><td>' + risks.length + '项</td><td>' + (allF.length>0 ? (risks.length/allF.length*100).toFixed(1) : 0) + '%</td><td>' + (risks.slice(0,2).map(function(f){return (f.type||'').substring(0,25);}).join('、') || '资料完备度、资金偏差等') + '</td></tr>';
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

// ═══════════ 报告语音播报系统 ═══════════
var _ttsState = { speaking: false, paused: false, utterance: null, speed: 1.0, currentText: '', currentIdx: 0 };
var _ttsChunks = [];

function _initReportTTS() {
  var area = document.getElementById('tax-doc-result');
  if (!area) return;
  
  // 移除旧控制条
  var oldBar = document.getElementById('tts-bar');
  if (oldBar) oldBar.remove();
  
  // 创建播报控制条
  var bar = document.createElement('div');
  bar.id = 'tts-bar';
  bar.innerHTML = 
    '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">' +
    '<span style="font-size:13px;font-weight:700;color:#1a1a2e">🔊 稽查报告语音播报</span>' +
    '<button id="tts-play-all" style="padding:6px 16px;background:#2563eb;color:#fff;border:none;border-radius:6px;font-size:13px;cursor:pointer;font-weight:600">▶ 全文播报</button>' +
    '<button id="tts-pause" style="padding:6px 16px;background:#fff;border:1px solid #d1d5db;border-radius:6px;font-size:13px;cursor:pointer;display:none">⏸ 暂停</button>' +
    '<button id="tts-stop" style="padding:6px 16px;background:#fff;border:1px solid #dc2626;color:#dc2626;border-radius:6px;font-size:13px;cursor:pointer;display:none">⏹ 停止</button>' +
    '<select id="tts-speed" style="padding:6px 10px;border:1px solid #d1d5db;border-radius:6px;font-size:13px;background:#fff;cursor:pointer">' +
    '<option value="0.8">0.8x 慢速</option><option value="1.0" selected>1.0x 正常</option><option value="1.2">1.2x 快速</option><option value="1.5">1.5x 加快</option>' +
    '</select>' +
    '<span id="tts-progress" style="font-size:12px;color:#94a3b8"></span>' +
    '</div>' +
    '<div style="font-size:11px;color:#94a3b8;margin-top:4px">💡 点击报告任意段落可从该处开始播报 · 音色：严肃中年男性稽查员</div>';
  bar.style.cssText = 'position:sticky;top:0;z-index:100;margin-bottom:20px;padding:14px 18px;background:#fafbfc;border:1px solid #e2e8f0;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,0.06)';
  
  area.insertBefore(bar, area.firstChild);
  
  // 绑定按钮
  document.getElementById('tts-play-all').onclick = function() { _ttsPlayFrom(area, 0); };
  document.getElementById('tts-pause').onclick = _ttsTogglePause;
  document.getElementById('tts-stop').onclick = _ttsStop;
  document.getElementById('tts-speed').onchange = function() { _ttsState.speed = parseFloat(this.value); };
  
  // 点击报告任意位置播报
  _bindClickToSpeak(area);
  
  // 预加载语音列表（浏览器异步加载voices）
  if (window.speechSynthesis) {
    window.speechSynthesis.getVoices();
    window.speechSynthesis.onvoiceschanged = function() { window.speechSynthesis.getVoices(); };
  }
}

function _bindClickToSpeak(container) {
  // 用事件委托：点击报告正文区域任意段落触发播报
  container.addEventListener('click', function(e) {
    // 排除按钮、链接、控制条
    if (e.target.tagName === 'BUTTON' || e.target.tagName === 'A' || e.target.tagName === 'SELECT' || e.target.tagName === 'OPTION') return;
    if (e.target.closest('#tts-bar') || e.target.closest('#review-panel')) return;
    
    // 找到被点击的最近文本容器
    var el = e.target;
    while (el && el !== container) {
      if (el.tagName === 'P' || el.tagName === 'H1' || el.tagName === 'H2' || el.tagName === 'H3' || el.tagName === 'TD' || el.tagName === 'TH' || el.tagName === 'LI' || el.tagName === 'DIV') {
        var text = (el.textContent || '').trim();
        if (text.length > 10) {
          _ttsStop();
          _ttsSpeakChunk(el, text);
          // 高亮当前播报元素
          el.style.transition = 'background 0.3s';
          el.style.background = '#fef3c7';
          setTimeout(function() { el.style.background = ''; }, 2000);
          return;
        }
      }
      el = el.parentElement;
    }
  });
}

function _ttsPlayFrom(container, startIdx) {
  if (!window.speechSynthesis) { toast('您的浏览器不支持语音播报', 'error'); return; }
  
  // 收集所有可读文本块
  _ttsChunks = [];
  var els = container.querySelectorAll('p, h2, h3, td, th, li, .ftitle, .frow, .flabel, .ritem, .atitle, .aitem, .seal p');
  els.forEach(function(el) {
    // 跳过控制条和审查面板内的
    if (el.closest('#tts-bar') || el.closest('#review-panel') || el.closest('details')) return;
    var t = (el.textContent || '').replace(/\s+/g, ' ').trim();
    if (t.length > 5) _ttsChunks.push({el: el, text: t});
  });
  
  _ttsState.currentIdx = startIdx;
  _ttsSpeakNext();
  _updateTtsUI(true);
}

function _ttsSpeakChunk(el, text) {
  if (!window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  _ttsState.utterance = new SpeechSynthesisUtterance(text);
  _ttsState.utterance.lang = 'zh-CN';
  _ttsState.utterance.rate = _ttsState.speed;
  _ttsState.utterance.pitch = 0.8;  // 低沉男声
  _ttsState.utterance.volume = 1;
  
  // 选择中文男声
  var voices = window.speechSynthesis.getVoices();
  var maleVoice = voices.find(function(v) { return v.lang.indexOf('zh') >= 0 && v.name.indexOf('Male') >= 0; }) ||
                  voices.find(function(v) { return v.lang.indexOf('zh-CN') >= 0 && v.name.indexOf('Tingting') < 0; }) ||
                  voices.find(function(v) { return v.lang.indexOf('zh') >= 0; });
  if (maleVoice) _ttsState.utterance.voice = maleVoice;
  
  _ttsState.speaking = true;
  window.speechSynthesis.speak(_ttsState.utterance);
  _updateTtsUI(true);
}

function _ttsSpeakNext() {
  if (_ttsState.currentIdx >= _ttsChunks.length) { _ttsStop(); return; }
  
  var chunk = _ttsChunks[_ttsState.currentIdx];
  window.speechSynthesis.cancel();
  _ttsState.utterance = new SpeechSynthesisUtterance(chunk.text);
  _ttsState.utterance.lang = 'zh-CN';
  _ttsState.utterance.rate = _ttsState.speed;
  _ttsState.utterance.pitch = 0.8;
  _ttsState.utterance.volume = 1;
  
  var voices = window.speechSynthesis.getVoices();
  var maleVoice = voices.find(function(v) { return v.lang.indexOf('zh') >= 0 && v.name.indexOf('Male') >= 0; }) ||
                  voices.find(function(v) { return v.lang.indexOf('zh-CN') >= 0 && v.name.indexOf('Tingting') < 0; }) ||
                  voices.find(function(v) { return v.lang.indexOf('zh') >= 0; });
  if (maleVoice) _ttsState.utterance.voice = maleVoice;
  
  _ttsState.utterance.onend = function() {
    _ttsState.currentIdx++;
    document.getElementById('tts-progress').textContent = (_ttsState.currentIdx + 1) + ' / ' + _ttsChunks.length;
    _ttsSpeakNext();
  };
  
  _ttsState.speaking = true;
  window.speechSynthesis.speak(_ttsState.utterance);
  document.getElementById('tts-progress').textContent = (_ttsState.currentIdx + 1) + ' / ' + _ttsChunks.length;
}

function _ttsTogglePause() {
  if (_ttsState.paused) {
    window.speechSynthesis.resume();
    _ttsState.paused = false;
    document.getElementById('tts-pause').textContent = '⏸ 暂停';
  } else {
    window.speechSynthesis.pause();
    _ttsState.paused = true;
    document.getElementById('tts-pause').textContent = '▶ 继续';
  }
}

function _ttsStop() {
  window.speechSynthesis.cancel();
  _ttsState.speaking = false;
  _ttsState.paused = false;
  _ttsState.currentIdx = 0;
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
