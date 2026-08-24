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


    + '<div style="font-size:13px;color:#64748b;margin-top:6px">一键分析将按稽查任务、资料接收、程序执行、逐项检查、证据底稿、过程意见和复查安排生成工作过程报告。</div>'


    + '</div>'


    // ── 资料上传区 ──


    + '<div id="tda-upload-section" style="background:#f8fafc;border:2px dashed #cbd5e1;border-radius:10px;padding:20px 24px;margin-bottom:20px">'


    + '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">'


    + '<div>'


    + '<span style="font-weight:600;font-size:16px">上传经营资料 <span id="tda-file-count" style="color:var(--gray-400);font-weight:400;font-size:14px">(0 份)</span></span>'


    + '<span style="font-size:12px;color:var(--gray-400);margin-left:12px">支持 Excel / PDF / Word / 图片 / XML / OFD / ZIP，可多文件同时上传；压缩包会逐成员安全解析</span>'


    + '</div>'


    + '<div style="display:flex;gap:10px">'


    + '<input type="file" id="tda-file-input" multiple accept=".xlsx,.xls,.csv,.pdf,.txt,.docx,.doc,.jpg,.jpeg,.png,.bmp,.tiff,.xml,.ofd,.zip" style="display:none" onchange="uploadTaxDocs()">'


    + '<button class="btn-toolbar" onclick="document.getElementById(\'tda-file-input\').click()" style="cursor:pointer">上传资料</button>'


    + '<button class="btn-toolbar" onclick="batchDelTdaDocs()">删除选中资料</button>'


    + '<button class="btn-toolbar" onclick="analyzeTaxDocs()" id="tda-analyze-btn">一键分析并生成过程报告</button>'


    + '<button class="btn-toolbar" id="tda-export-btn" onclick="exportTaxDocReport()">导出内部草稿</button>'


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


  } else {


    restoreTaxDocReportFromServer();


  }


}


async function restoreTaxDocReportFromServer() {


  var cid = _tdaCid();


  if (!cid || taxDocAnalyzing) return;


  try {


    var response = await fetch('/api/tax-risk-docs/last-analysis?company_id=' + encodeURIComponent(cid));


    if (!response.ok) return;


    var data = await response.json();


    if (!data || !data.ok || !data.report) return;


    if (!taxDocPageActive || taxDocAnalyzing || !document.getElementById('tda-report-area')) return;


    taxDocReportData = data.report;


    renderTaxDocReport(taxDocReportData);


    var btn = document.getElementById('tda-export-btn');


    if (btn) btn.style.display = '';


  } catch (error) {


    console.warn('[tax-doc] 最近一次分析报告恢复失败', error);


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

      // 补件进入系统后自动重跑全部规则和场景，不让企业重复点击或遗漏复查。
      if (data.uploaded && data.uploaded.length) {
        toast('补件已登记，正在自动发起新一轮全量复查', 'success');
        input.value = '';
        await refreshTaxDocList();
        if (btn) { btn.disabled = false; btn.textContent = '一键分析并生成过程报告'; }
        return analyzeTaxDocs();
      }


    } else {


      toast(data.message || '上传失败', 'error');


    }


    input.value = '';


    refreshTaxDocList();


  } catch (e) {


    toast('上传失败: ' + e.message, 'error');


    if (listEl) listEl.innerHTML = '<div style="color:#dc2626;padding:10px">上传出错: ' + esc(String(e.message || e)) + '</div>';


  } finally {


    if (btn) { btn.disabled = false; btn.textContent = '一键分析并生成过程报告'; }


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


  h += '<details style="margin-bottom:12px"><summary style="cursor:pointer;font-size:14px;font-weight:700;color:#0f172a;padding:6px 0;border-bottom:1px solid #e2e8f0">⚙️ 税务合规引擎全链路执行流程（52步·23模块协同）</summary><div style="padding:8px 0">';


  var steps = [


    { title: '第一阶段：文件解析与身份识别', desc: '① {{file_fingerprints}}类文件指纹扫描 → ② 四方交叉验证判定类型 → ③ 公司身份锚定（名+统一社会信用代码双向比对） → ④ 发票方向判定（购买方=公司→进项/销售方=公司→销项/双方不匹配→存疑排除） → ⑤ 只读有效数据（过滤空白行/小计行）' },


    { title: '第二阶段：Phase1 初查——企业画像与财务快照', desc: '⑥ 目标实体识别（频次统计） → ⑦ 财务快照（销项/进项/银行/工资汇总） → ⑧ 主营业务成本识别（core/major/minor三层分类） → ⑨ 企业画像（行业推断+经营模式判定） → ⑩ 服务行业闸门（销项金税编码检测→跳过进销存/BOM） → ⑪ 历史记忆检索（具体条款待从官方有效文本核验相似案例） → ⑫ 资料缺失检测（14类必查资料逐项扫描）' },


    { title: '第三阶段：Phase2 定向深挖——信号驱动+行业自适应', desc: '⑬ 信号→域映射（16个初查信号驱动5域深挖） → ⑭ 发票实质性审计（五层：合规/同品单价/加工费/金额合理性/BOM） → ⑮ 经营实质分析（工商登记↔发票数据↔加工信号三层穿透） → ⑯ 资金流向追踪（付款→供应商比对/收款→客户比对） → ⑰ 个人交易风险检测 → ⑱ 关联交易穿透检测 → ⑲ 税收优惠分析 → ⑳ 行业自适应知识库注入（8行业画像+{{industries}}行业基准值）' },


    { title: '第四阶段：Phase3 交叉验证——冲突消解与证据闭环', desc: '㉑ 冲突消解引擎（信号互斥检测→自动降级/升级） → ㉒ 规则引擎（具体条款待从官方有效文本核验逐条匹配） → ㉓ 线索链驱动（具体条款待从官方有效文本核验链驱动发现） → ㉔ 证据链匹配（具体条款待从官方有效文本核验跨域证据闭环） → ㉕ 轻量跨结论串联 → ㉖ 证伪检查（30+规则覆盖） → ㉗ 联网核查（DB缓存→API→搜索引擎三层降级） → ㉘ 经营实质五步核查法 → ㉙ 知识图谱（49实体/5异常关系检测）' },


    { title: '第五阶段：方法论过滤——噪声剔除97%', desc: '㉚ 禁止词硬删除（40+） → ㉛ 无资料条件过滤 → ㉜ 行业不匹配过滤 → ㉝ 服务行业进销存过滤（三层闸门） → ㉞ 重复发现去重 → ㉟ 正常结论排除 → ㊱ 具体条款待从官方有效文本核验→具体条款待从官方有效文本核验，剔除具体条款待从官方有效文本核验噪声' },


    { title: '第六阶段：Phase4 综合定性——AI推理与因果叙事', desc: '㊲ 风险综合评分 → ㊳ 因果叙事链（具体条款待从官方有效文本核验因果规则推理） → ㊴ 缺失后果自动触发（14类资料缺失→具体条款待从官方有效文本核验风险结论） → ㊵ 贝叶斯因果推理 → ㊶ 矛盾检测（具体条款待从官方有效文本核验逻辑冲突） → ㊷ 回溯引擎定位根因 → ㊸ 四步税务审查法（detect→verify→diagnose→report）' },


    { title: '第七阶段：质量保障——三层门禁', desc: '㊹ 文本净化（剔除模板句/重复句/空描述） → ㊺ 建议质量增强（具体条款待从官方有效文本核验补充操作路径） → ㊻ 12项质量标准检测（5/32项通过·15.62%） → ㊼ 合规门禁（178项检测+自动修复+质量标记） → ㊽ Provenance溯源链注入（具体条款待从官方有效文本核验） → ㊾ Benford数字检验 → ㊿ EMA自学习（58样本）' },


    { title: '第八阶段：持续学习——智能体反思与记忆积累', desc: '⓫ AGI法律推理 → ⓬ AGI跨企业关联 → ⓭ AGI趋势追踪 → ⓮ 自动规则发现（具体条款待从官方有效文本核验新信号） → ⓯ 审计策略推荐（具体条款待从官方有效文本核验·P0×2） → ⓰ 分析记忆保存（具体条款待从官方有效文本核验积累） → ⓱ 行业基准更新 → ⓲ 智能体反思与学习闭环' },


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


    + '全链路闭环：规则ID追溯 ✓ · 线索链追溯 ✓ · 数据来源 ✓ · 一键分析 ✓ · 证据链闭环 ✓ · 跨域证据链 ✓'


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


      + '<span style="font-size:18px;font-weight:700;color:#1e293b">推理引擎综合税务合规结论</span>'


      + '<span style="display:inline-block;padding:4px 16px;background:' + riskColor + ';color:#fff;border-radius:6px;font-size:14px;font-weight:700">' + (synthFinding.level || '?') + '</span>'


      + '<span style="font-size:13px;color:var(--gray-500)">评分 ' + (synthFinding.score || '?') + '/100</span>'


      + '</div>'


      + '<div style="font-size:14px;color:var(--gray-700);line-height:1.8;white-space:pre-wrap">' + (synthFinding.description || '').replace(/</g,'&lt;').replace(/>/g,'&gt;') + '</div>'


      + '</div>';


  }


  h += '</div>';

  // 跨企业信息比对
  var ce = comp.cross_enterprise;
  if (ce && ce.total_companies) {
    h += '<div style="margin:16px 0;padding:16px 20px;background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;font-size:13px;line-height:2">';
    h += '<div style="font-weight:700;color:#c2410c;margin-bottom:8px">🔗 跨企业信息比对</div>';
    h += '<div style="color:#431407;font-size:12px">' + esc(ce.summary || '') + '</div>';
    var rels = ce.relationships || [];
    if (rels.length > 0) {
      h += '<table style="width:100%;margin-top:10px;font-size:12px;border-collapse:collapse">';
      h += '<tr style="border-bottom:1px solid #fed7aa"><td style="padding:4px 8px;font-weight:600">公司A</td><td style="padding:4px 8px;font-weight:600">公司B</td><td style="padding:4px 8px;font-weight:600">关联类型</td><td style="padding:4px 8px;font-weight:600">风险</td></tr>';
      for (var ri = 0; ri < rels.length; ri++) {
        var r = rels[ri];
        var rc = r.risk_level === 'high' ? '#dc2626' : r.risk_level === 'medium' ? '#f59e0b' : '#94a3b8';
        h += '<tr><td style="padding:4px 8px">' + esc(r.company_a) + '</td><td style="padding:4px 8px">' + esc(r.company_b) + '</td>';
        h += '<td style="padding:4px 8px">' + esc(r.type || '') + '</td>';
        h += '<td style="padding:4px 8px;color:' + rc + '">' + (r.risk_level === 'high' ? '高风险' : r.risk_level === 'medium' ? '中风险' : '低风险') + '</td></tr>';
      }
      h += '</table>';
    }
    h += '</div>';
  }

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


function _amountNumber(v) {
  if (typeof v === 'number') return isFinite(v) ? v : 0;
  var cleaned = String(v === undefined || v === null ? '' : v)
    .replace(/,/g, '').replace(/，/g, '').replace(/￥/g, '').replace(/¥/g, '').replace(/元/g, '').trim();
  var parsed = parseFloat(cleaned);
  return isNaN(parsed) ? 0 : parsed;
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


  h += '<table class="tbl2"><tr><th>缺失资料</th><th>风险等级</th><th>推定后果</th><th>涉及法规</th><th>处理行动</th></tr>';


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


  h += '<div style="font-weight:700;color:#166534;margin-bottom:8px">🔗 税务合规线索链激活统计</div>';


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


// ── 9. 跨企业信息比对（comprehensive.cross_enterprise）──

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


  h += '<div class="atitle">附件二：税务合规报告质量标准自检（12项硬指标）</div>';


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



// 安全JSON解析：处理服务器返回HTML错误页的情况
async function _safeJson(response, context) {
  var text = await response.text();
  try {
    var data = JSON.parse(text);
    if (data._raw) data._raw = text.substring(0, 500);
    return data;
  } catch (e) {
    // 非JSON响应 → 提取有用信息
    var preview = text.substring(0, 200).replace(/<[^>]+>/g, '').trim();
    return { ok: false, message: (context || '服务器') + '返回异常: ' + (preview || text.substring(0, 100)), _raw: text.substring(0, 500) };
  }
}


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


    var startData = await _safeJson(startResp, "启动分析");


    if (!startData.ok) { throw new Error(startData.message); }


    var taskId = startData.task_id;

    // ═══ 设置全局task_id，管道调度页面可检测到正在运行的分析 ═══
    window._currentAnalysisTaskId = taskId;

    


    // 2. 轮询进度


    var maxPolls = 1800; // 最多等30分钟（1秒一次，具体条款待从官方有效文本核验链需更长时间）


    var pollCount = 0;


    while (pollCount < maxPolls) {


      await new Promise(function(r) { setTimeout(r, 1000); });


      pollCount++;


      


      var statusResp = await fetch('/api/tax-risk-docs/analyze-status/' + taskId);


      var statusData = await _safeJson(statusResp, "分析状态");


      if (!statusData.ok) { throw new Error(statusData.message); }


      


      var pct = statusData.progress || 0;


      var msg = statusData.message || '';


      btn.textContent = '⏳ ' + pct + '% ' + msg.substring(0, 20);


      


      if (statusData.status === 'done') {
        window._currentAnalysisTaskId = null; // 清除全局task_id
        btn.textContent = '✅ 分析完成，正在加载报告...';
        break;


      }


      if (statusData.status === 'error') {


        window._currentAnalysisTaskId = null; // 清除全局task_id
        throw new Error(statusData.error || statusData.message || '分析服务异常');


      }


    }


    


    if (pollCount >= maxPolls) {


      throw new Error('分析超时，请稍后重试');


    }


    


    // 3. 获取结果


    var resultResp = await fetch('/api/tax-risk-docs/analyze-result/' + taskId);


    var resultData = await _safeJson(resultResp, "分析结果");


    if (!resultData.ok) { throw new Error(resultData.message); }


    


    // 4. 渲染报告


    var data = resultData;


    if (!taxDocPageActive) return;


    taxDocReportData = data.report;


    // 系统内部信息不再渲染到报告区域，保护引擎机密


    // renderAnalyzeHeader(data.report);


    


    // ── 统一走 renderTaxDocReport（含按钮注入+7章结构+交互面板）──


    renderTaxDocReport(data.report);


    


        var exportBtn = document.getElementById('tda-export-btn');
    if (exportBtn) {
      var ma = (data.report||{})._methodology_applied || {};
      if (ma.methodology_gate_enforced) {
        exportBtn.style.display = 'inline-block';
        exportBtn.title = '方法论验收未通过，导出已禁用。请修复失败场景后重新分析。';
        exportBtn.style.opacity = '0.5';
        exportBtn.style.cursor = 'not-allowed';
      } else {
        exportBtn.style.display = 'inline-block';
      }
    }


    if (exportBtn) exportBtn.style.display = 'inline-block';


    var closeInfo = (data.report||{}).coverage_closure || {};
    toast(
      '分析完成：' + data.report.total_risks + '项待核事项，' +
      (closeInfo.total_items||0) + '项规则/场景已记账，未决' +
      (closeInfo.unresolved_items||0) + '项',
      'success'
    );


    


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


    btn.disabled = false; btn.textContent = '一键分析并生成过程报告';


  }


}


// ==================== 报告渲染 ====================


// 智能判断税务合规涉及税种（根据主营业务+实际数据分析）


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


  // ✏️由_initAllEditIcons统一注入，这里不再内联


  var html = ctx.html;
  var enterpriseMode = !!(r.enterprise_readable_report && ['税务稽查文书式报告', '内部税务稽查员报告', '企业易读检查结果'].indexOf(r.enterprise_readable_report.compilation_style) >= 0);

  // 持续合规轮次与系统角色必须在报告首屏固定展示，防止内部分析
  // 被误认为税务机关行政处理、处罚或案件定性结论。
  var cr = r.compliance_round || {};
  var identity = r.report_identity || {};
  var mode = (identity.mode || cr.mode || r.operating_mode_profile || {});
  var disclosure = mode.disclaimer || identity.required_display_statement || r.release_boundary || '本报告为企业内部风险分析，不属于税务机关行政处理、处罚或案件定性结论。';
  var complianceBanner = '<div style="border:1px solid #bfdbfe;background:#eff6ff;border-radius:8px;padding:12px 14px;margin:0 0 14px;font-size:12px;line-height:1.8;color:#1e3a8a">' +
    '<div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap"><b>🧭 ' + escHtml(mode.name || '企业自查模式') + '</b>' +
    '<span>持续合规第' + escHtml(cr.round_no || r.analysis_round || 1) + '轮 · ' + escHtml(cr.status || r.release_status || '草稿_待人工复核') + '</span></div>' +
    '<div>' + escHtml(disclosure) + '</div>' +
    (cr.immutable_hash ? '<div style="font-size:10px;color:#64748b">案件快照指纹：' + escHtml(cr.immutable_hash) + '</div>' : '') +
    '</div>';
  if (!enterpriseMode) html = complianceBanner + html;

  var oneClickClosure = r.one_click_closure || {};
  if (!enterpriseMode && (oneClickClosure.modules||[]).length) {
    var closureStrip = '<div style="border:1px solid #cbd5e1;background:#fff;border-radius:8px;padding:12px 14px;margin:0 0 14px;font-size:12px;line-height:1.8">' +
      '<div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap"><b>一键分析四模块闭环</b><span>静默跳过 ' + (oneClickClosure.silent_skip_count||0) + ' · 未决 ' + (oneClickClosure.unresolved_items||0) + '</span></div>' +
      '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:6px">';
    (oneClickClosure.modules||[]).forEach(function(mod){
      closureStrip += '<span style="background:#f1f5f9;border-radius:4px;padding:3px 7px">' + escHtml(mod.module||'') + '：' + escHtml(mod.status||'') + '（' + (mod.items||0) + '项）</span>';
    });
    closureStrip += '</div><div style="color:#475569">下一步：' + escHtml(oneClickClosure.next_action||'') + '</div></div>';
    html = closureStrip + html;
  }

  var taskClosure = cr.task_closure || {};
  if (!enterpriseMode && taskClosure.open_issue_count != null) {
    var taskStrip = '<div style="border:1px solid #fed7aa;background:#fff7ed;border-radius:8px;padding:12px 14px;margin:0 0 14px;font-size:12px;line-height:1.8;color:#9a3412">' +
      '<div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap"><b>补件—整改—复查任务已生成</b><span>开放事项 ' + (taskClosure.open_issue_count||0) + '</span></div>' +
      '<div>补件任务 ' + (taskClosure.material_request_count||0) + ' 项 · 专项资料门 ' + (taskClosure.source_gate_request_count||0) + ' 项 · 风险整改任务 ' + (taskClosure.risk_rectification_count||0) + ' 项 · 本轮新增 ' + (taskClosure.created||0) + ' 项 · 跨轮承接 ' + (taskClosure.carried_forward||0) + ' 项</div>' +
      '<button class="btn-toolbar" style="margin-top:6px" onclick="navigateTo(\'compliance-workbench\')">进入持续合规工作台处理</button></div>';
    html = taskStrip + html;
  }

  var roundComparison = cr.comparison || {};
  if (!enterpriseMode && !roundComparison.baseline && roundComparison.counts) {
    var rcnt = roundComparison.counts || {};
    var comparisonStrip = '<div style="border:1px solid #a7f3d0;background:#ecfdf5;border-radius:8px;padding:12px 14px;margin:0 0 14px;font-size:12px;line-height:1.8;color:#065f46">' +
      '<b>本轮与上一轮闭环比较</b>' +
      '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:6px">' +
      '<span>新增风险 ' + (rcnt.new_risks||0) + '</span><span>持续风险 ' + (rcnt.continuing_risks||0) + '</span>' +
      '<span>未再复现 ' + (rcnt.not_reproduced_risks||0) + '</span><span>状态变化 ' + (rcnt.risk_status_changes||0) + '</span>' +
      '<span>重新出现 ' + (rcnt.reopened_risks||0) + '</span>' +
      '<span>已补资料 ' + (rcnt.closed_material_gaps||0) + '</span><span>持续缺口 ' + (rcnt.continuing_material_gaps||0) + '</span></div>' +
      '<div>未再复现不等于自动关闭，须进入持续合规工作台完成独立关闭复核。</div></div>';
    html = comparisonStrip + html;
  }


  area.innerHTML = html;


  area.scrollIntoView({ behavior: 'smooth' });


  


  // ── 统一✏️图标：章节/封面/表格行/发现——一键全入口 ──


  setTimeout(function() { _initAllEditIcons(); }, 200);


  


  // ── 语音播报条初始化 ──


  setTimeout(function() { _initReportTTS(); }, 300);

  // 企业易读版已经包含完整结论、处理方法和补件清单，不再插入内部评分、
  // 技术状态码或未经本轮证据门槛筛选的智能分析卡片。
  if (enterpriseMode) {
    _initReportChatPanel();
    return;
  }


  


  // ── 报告智能增强：异步加载风险叙事+税负模拟+资料缺口影响链 ──


  setTimeout(function(){


    var cid = window.currentCompanyId || 1;


    fetch('/api/tax-risk-docs/report-smart?company_id=' + cid)


      .then(function(resp){ return resp.json(); })


      .then(function(smart){


        if (!smart.ok) return;


        var smartHtml = '';


        


        // ① 风险叙事


        if (smart.narrative) {


          smartHtml += '<div class="edt-block" style="display:flex;align-items:flex-start;gap:0;margin:4px 0">';


          smartHtml += '<span style="flex:1;min-width:0"><p class="i2" style="margin:0"><strong>🧠 引擎智能分析总览：</strong>' + (smart.narrative||'') + '</p></span>';


          smartHtml += '';


          smartHtml += '</div>';


        }


        


        // ② 税负模拟


        if (smart.tax_burden && smart.tax_burden.length > 0) {


          smartHtml += '<div class="edt-block" style="margin:12px 0">';


          smartHtml += '<div style="display:flex;align-items:flex-start;gap:0;margin-bottom:8px">';


          smartHtml += '<span style="flex:1;min-width:0"><p class="i2" style="margin:0"><strong>💰 税负模拟</strong></p></span>';


          smartHtml += '';


          smartHtml += '</div>';


          smartHtml += '<table class="tbl2" style="margin:8px 0"><thead><tr><th>风险类型</th><th>等级</th><th>发票数</th><th>涉税金额</th><th>增值税（实际税额）</th><th>企业所得税（最高' + (smart.tax_burden[0] ? smart.tax_burden[0].income_tax_rate : '25%') + '）</th></tr></thead><tbody>';


          smart.tax_burden.forEach(function(tb){


            var vatShow = tb.vat_actual > 0 ? '¥' + (tb.vat_actual||0).toLocaleString('zh-CN',{minimumFractionDigits:0,maximumFractionDigits:0}) : '<span style="color:#94a3b8">0（普票）</span>';


            smartHtml += '<tr><td>' + (tb.type||'') + '</td><td style="color:' + (tb.level==='高风险'?'#dc2626':tb.level==='中风险'?'#d97706':'#16a34a') + '">' + tb.level + '</td><td class="r">' + (tb.invoice_count||0) + '张</td><td class="r">¥' + (tb.amount||0).toLocaleString('zh-CN',{minimumFractionDigits:0,maximumFractionDigits:0}) + '</td><td class="r">' + vatShow + '</td><td class="r">¥' + (tb.income_tax_est||0).toLocaleString('zh-CN',{minimumFractionDigits:0,maximumFractionDigits:0}) + '</td></tr>';


          });


          smartHtml += '<tr style="font-weight:700;background:#f8fafc"><td colspan="3">合计</td><td class="r">¥' + (smart.tax_total||0).toLocaleString('zh-CN',{minimumFractionDigits:0,maximumFractionDigits:0}) + '</td><td class="r">¥' + (smart.vat_total||0).toLocaleString('zh-CN',{minimumFractionDigits:0,maximumFractionDigits:0}) + '</td><td class="r">¥' + (smart.income_tax_total||0).toLocaleString('zh-CN',{minimumFractionDigits:0,maximumFractionDigits:0}) + '</td></tr>';


          smartHtml += '</tbody></table>';


          smartHtml += '<p class="i1" style="font-size:12px;color:#64748b">以上仅为基于现有资料的税负测算线索，不构成确定税额。应逐项核验事实期间、计税口径、抵扣条件、优惠条件、已缴税款和有效政策，并形成可复算金额底稿后由有权人员审签。</p>';


          smartHtml += '</div>';


        }


        


        // ③ 资料缺口影响链


        if (smart.gap_chain && smart.gap_chain.length > 0) {


          smartHtml += '<div class="edt-block" style="margin:12px 0">';


          smartHtml += '<div style="display:flex;align-items:flex-start;gap:0;margin-bottom:8px">';


          smartHtml += '<span style="flex:1;min-width:0"><p class="i2" style="margin:0"><strong>🔗 资料缺口影响链</strong></p></span>';


          smartHtml += '';


          smartHtml += '</div>';


          smartHtml += '<p class="i1" style="font-size:12px;color:#64748b;margin-bottom:6px">以下为缺失资料对税务合规判断的影响链——缺少一份资料会影响多个分析域的判定：</p>';


          smartHtml += '<table class="tbl2" style="margin:8px 0"><thead><tr><th>缺失资料</th><th>风险</th><th>影响链</th></tr></thead><tbody>';


          smart.gap_chain.forEach(function(gap){


            smartHtml += '<tr><td><strong>' + (gap.material||'') + '</strong></td><td style="color:#dc2626">⚠ ' + (gap.risk||'') + '</td><td style="color:#475569">' + (gap.chain||'') + '</td></tr>';


          });


          smartHtml += '</tbody></table>';


          smartHtml += '</div>';


        }


        


        // ④ 智能报告质量自审评分


        if (smart.agi_enhanced && smart.agi_enhanced.meta_audit) {


          var audit = smart.agi_enhanced.meta_audit;


                    var auditSummary = '综合等级' + (audit.grade||'?') + '级，总分' + (audit.overall_score||0) + '，严重' + (audit.critical_count||0) + '项、警告' + (audit.warning_count||0) + '项';
          var dims = audit.dimensions || {};
          var dimParts = [];
          for (var dk in dims) { if (dims.hasOwnProperty(dk)) { var ds = dims[dk]; dimParts.push(dk + ' ' + Math.round((ds.score||0)*100) + '%'); } }
          var dimNote = dimParts.length > 0 ? '（评分构成：' + dimParts.join('，') + '）' : '';


          smartHtml += '<div class="edt-block agi-quality-audit" style="display:block;width:100%;max-width:none;margin:12px 0">';


          smartHtml += '<div style="display:block;width:100%;min-width:0"><p class="i2" style="margin:0"><strong>🔍 智能报告质量自审：</strong>' + auditSummary + '</p>' + (dimNote ? '<p class="i2" style="margin:4px 0 0 0;font-size:11px;color:#64748b">' + dimNote + '</p>' : '') + '<p class="i2" style="margin:2px 0 0 0;font-size:10px;color:#94a3b8">本评分为内部质量自审，不得直接用于处罚或正式定性</p></div>';


          smartHtml += '';


          var dims = audit.dimensions || {};


          var dimLines = [];


          Object.keys(dims).forEach(function(d){ dimLines.push(d + ' ' + (dims[d].status||'') + '(' + (dims[d].score||0) + '%)'); });


          if (dimLines.length) smartHtml += '<p class="i2">六维度评分：' + dimLines.join('、') + '。</p>';


          if (audit.critical_issues && audit.critical_issues.length > 0) {


            smartHtml += '<p class="i2"><strong>严重问题：</strong>' + audit.critical_issues.slice(0,3).map(function(i){return i.issue;}).join('；') + '。</p>';


          }


          if (audit.per_finding_audits && audit.per_finding_audits.length > 0) {


            var lines = audit.per_finding_audits.map(function(pfa){ return '发现' + pfa.index + ' ' + (pfa.verdict||'?') + '(' + (pfa.score||0) + '分)'; });


            smartHtml += '<p class="i2">第三章逐条审核：' + lines.join('、') + '。成立' + (audit.valid_findings||0) + '条，存疑' + (audit.questionable_findings||0) + '条。</p>';


          }
          smartHtml += '</div>';


        }


        


        if (smartHtml) {


          var rr = document.getElementById('rr-report');


          if (rr) {


            var smartDiv = document.createElement('div');


            smartDiv.innerHTML = smartHtml;


            smartDiv.style.cssText = 'margin:0;padding:0;border:none;background:transparent;font-family:inherit;font-size:inherit;line-height:inherit;color:inherit';


            rr.insertBefore(smartDiv, rr.firstChild);


            // 重新扫描新增的表格，加上✏️


            _initAllEditIcons();


          }


        }


      })


      .catch(function(){});


  }, 500);


  // 追加对话式交互面板（发现审查的升级版）


  _initReportChatPanel();


}


// ═══════════════════════════════════════════════════════════


// 对话式税务合规报告交互引擎（前端）


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


    '<div><span style="font-size:16px">🧬</span> <b>税务合规对话引擎</b><span id="chat-finding-label" style="font-size:11px;color:#94a3b8;margin-left:8px">（可追问任何发现）</span></div>' +


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


// ═══════════════════════════════════════════════════════════


// 报告正文内嵌操作：编辑/审核/追问/删除


// ═══════════════════════════════════════════════════════════


window._sendAskChat = function() {


  var input = document.getElementById('ask-chat-input');


  var policyText = document.getElementById('ask-policy-text');


  var question = (input ? input.value.trim() : '');


  var policy = (policyText ? policyText.value.trim() : '');


  if (!question && !policy) return;


  


  var body = document.getElementById('ask-chat-body');


  if (!body) return;


  


  var userHtml = '<div style="margin-bottom:12px"><div style="background:#7c3aed;color:#fff;padding:8px 12px;border-radius:12px 12px 4px 12px;display:inline-block;max-width:90%;font-size:12px">';


  userHtml += '<b>You:</b> ' + (question || '(pasted policy text)');


  if (policy) userHtml += '<br><span style="font-size:11px;opacity:0.8">policy (' + policy.length + ' chars)</span>';


  userHtml += '</div></div>';


  body.innerHTML += userHtml;


  body.innerHTML += '<div id="ask-thinking" style="color:#94a3b8;font-size:12px;margin-bottom:12px">Thinking...</div>';


  body.scrollTop = body.scrollHeight;


  


  // Track conversation per popup session


  if (!window._askChatHistory) window._askChatHistory = [];


  if (!window._conversationId) window._conversationId = '';


  


  window._askChatHistory.push({role:'user', text: question || '', policy: policy || '', intent: '', finding_idx: window._chatFindingIdx});


  if (input) input.value = '';


  


  var companyId = window.currentCompanyId || 1;


  fetch('/api/tax-risk-docs/ask?company_id=' + companyId, {


    method: 'POST',


    headers: {'Content-Type': 'application/json'},


    body: JSON.stringify({


      finding_index: window._chatFindingIdx || 0,


      question: question || '',


      policy_doc: policy || '',


      history: window._askChatHistory || [],


      conversation_id: window._conversationId || ''


    })


  }).then(function(r){ return r.json(); }).then(function(data){


    var t = document.getElementById('ask-thinking');


    if (t) t.remove();


    


    if (!data.ok) {


      body.innerHTML += '<div style="color:#dc2626;font-size:12px">Error: ' + (data.message || 'unknown') + '</div>';


      return;


    }


    


    var html = '<div style="margin-bottom:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden">';


    html += '<div style="background:#f1f5f9;padding:8px 12px;font-size:11px;color:#475569"><b>Engine (' + (data.engine_mode||'analyze') + ')</b></div>';


    if (data.analysis) {


      data.analysis.forEach(function(block){


        html += '<div style="padding:10px 12px;border-bottom:1px solid #f1f5f9">';


        html += '<div style="font-size:12px;font-weight:600;color:#0f172a;margin-bottom:6px">' + (block.title||'') + '</div>';


        html += '<div style="font-size:12px;color:#475569;line-height:1.8;white-space:pre-wrap">' + (block.content||'') + '</div>';


        html += '</div>';


      });


    }


    html += '</div>';


    // 引擎回应记入对话历史


    window._askChatHistory.push({role:'engine', text: JSON.stringify(data.analysis||[]), mode: data.engine_mode||'', intent: data.intent||''});


    if (data.conversation_id) window._conversationId = data.conversation_id;


    // compare/correct模式→保存纠正按钮


    if (data.engine_mode === 'compare' || data.engine_mode === 'correct') {


      html += '<div style="margin-top:6px"><button onclick="window._saveAskAsCorrection(' + JSON.stringify(data.finding_index) + ',\'' + (data.engine_mode||'') + '\')" style="background:#059669;color:#fff;border:none;padding:4px 12px;border-radius:4px;font-size:11px;cursor:pointer;font-weight:600">Save to Correction Rules</button></div>';


    }


    // 多轮对话后出现"自动总结"按钮（>=2轮）


    if (window._askChatHistory.length >= 4) {


      html += '<div style="margin-top:8px;padding-top:8px;border-top:1px dashed #e2e8f0">' +


        '<button onclick="window._summarizeAskChat()" style="background:#0ea5e9;color:#fff;border:none;padding:4px 12px;border-radius:4px;font-size:11px;cursor:pointer;font-weight:600">Auto-Summarize & Save as Correction</button>' +


        '<span style="font-size:10px;color:#94a3b8;margin-left:6px">' + window._askChatHistory.length + ' turns</span></div>';


    }


    body.innerHTML += html;


    body.scrollTop = body.scrollHeight;


  }).catch(function(e){


    var t = document.getElementById('ask-thinking');


    if (t) t.remove();


    body.innerHTML += '<div style="color:#dc2626">Network error: ' + e.message + '</div>';


  });


};


window._askQuickFromPopup = function(q) {


  var inp = document.getElementById('ask-chat-input');


  if (inp) { inp.value = q || ''; window._sendAskChat(); }


};


window._clearAskChat = function() {


  var body = document.getElementById('ask-chat-body');


  if (body) body.innerHTML = '<div style="color:#94a3b8;text-align:center;padding:30px">Chat cleared</div>';


  window._askChatHistory = [];


  window._conversationId = '';


};


// ═══════════ 统一✏反馈系统 ═══════════


window._editScope = {};


window._initAllEditIcons = function() { return; /* 2026-07-25 老邓要求删除全部 */


  var area = document.getElementById('tda-report-area');


  if (!area) return;


  // 1. 每章<h2>加✏️


  area.querySelectorAll('h2[id]').forEach(function(h2) {


    if (h2.id === 'appendix') return;
    if (h2.querySelector('.edt-icon')) return;


    var btn = _makeEditIcon('该章内容');


    btn.onclick = function(e){ e.stopPropagation();


      var chHtml = ''; var nextSib = h2.nextElementSibling; while (nextSib && nextSib.tagName !== 'H2') { var tmp=nextSib.cloneNode(true); var eis=tmp.querySelectorAll('.edt-icon,.edt-icon-inline,.edt-block-icon'); for(var ei=0;ei<eis.length;ei++)eis[ei].remove(); chHtml += tmp.outerHTML; nextSib = nextSib.nextElementSibling; }
window._editScope = {level:'chapter', id:h2.id, title:h2.textContent.replace('','').trim(), content: chHtml, isHtml: true};


      window._unifiedEditPopup();


    };


    h2.appendChild(btn);


  });


  // 2. 每节<h3>加✏️


  area.querySelectorAll('h3').forEach(function(h3, hi) {


    if (h3.closest('.appendix')) return;
    if (h3.querySelector('.edt-icon')) return;


    var btn = _makeEditIcon('该小节标题');


    (function(idx, txt, el){


      btn.onclick = function(e){ e.stopPropagation();


        var subHtml=''; var ns=el.nextElementSibling; while(ns&&ns.tagName!=='H2'&&ns.tagName!=='H3'){var tmp=ns.cloneNode(true);var eis=tmp.querySelectorAll('.edt-icon,.edt-icon-inline,.edt-block-icon');for(var ei=0;ei<eis.length;ei++)eis[ei].remove();subHtml+=tmp.outerHTML;ns=ns.nextElementSibling;}
        window._editScope = {level:'paragraph', id:'h3-'+idx, title:'节标题·'+txt.slice(0,40), content: subHtml||txt, isHtml: !!subHtml};


        window._unifiedEditPopup();


      };


    })(hi, h3.textContent.trim(), h3);


    h3.appendChild(btn);


  });


  // 2b. 每个四级标题<h4>加✏️
  area.querySelectorAll('h4').forEach(function(h4, hi) {
    if (h4.closest('.appendix')) return;
    if (h4.querySelector('.edt-icon')) return;
    var btn = _makeEditIcon('该小节内容');
    (function(idx, txt, el){
      btn.onclick = function(e){ e.stopPropagation();
        var subHtml=''; var ns=el.nextElementSibling; while(ns&&ns.tagName!=='H2'&&ns.tagName!=='H3'&&ns.tagName!=='H4'){var tmp=ns.cloneNode(true);var eis=tmp.querySelectorAll('.edt-icon,.edt-icon-inline,.edt-block-icon');for(var ei=0;ei<eis.length;ei++)eis[ei].remove();subHtml+=tmp.outerHTML;ns=ns.nextElementSibling;}
        window._editScope = {level:'sub-section', id:'h4-'+idx, title:'小节·'+txt.slice(0,40), content: subHtml||txt, isHtml: !!subHtml};
        window._unifiedEditPopup();
      };
    })(hi, h4.textContent.trim(), h4);
    h4.appendChild(btn);
  });

  // 3. 每段<p>加✏️


  area.querySelectorAll('p').forEach(function(p, pi) {


    if (p.closest('.appendix') || p.querySelector('.edt-icon') || p.querySelector('.edt-icon-inline') || p.closest('#tts-bar') || p.closest('#edt-popup') || p.closest('.edt-block')) return;


    if (p.style.display === 'flex' || p.style.display === 'inline-flex') return;  // 已是flex容器（如发现标题）


    var txt = p.textContent.trim();


    if (!txt) return;  // 空段跳过


    // 把p改为flex容器，原文在左，✏️在右


    if (!p.classList.contains('edt-p-flex')) {


      p.classList.add('edt-p-flex');


      p.style.display = 'flex';


      p.style.alignItems = 'flex-start';


      p.style.gap = '0';


      var inner = document.createElement('span');


      inner.style.flex = '1';


      inner.style.minWidth = '0';


      while (p.firstChild) inner.appendChild(p.firstChild);


      p.appendChild(inner);


    }


    var btn = _makeEditIcon();


    (function(idx, ct){


      btn.onclick = function(e){ e.stopPropagation();


        window._editScope = {level:'paragraph', id:'p-'+idx, title:'报告段落', content:ct};


        window._unifiedEditPopup();


      };


    })(pi, txt);


    p.appendChild(btn);


  });


  // 4. 表格行加✏️


  area.querySelectorAll('table.tbl, table.tbl2').forEach(function(table, ti) {


    if (table.closest('.appendix') || table.closest('.edt-block')) return;  // 附件表格不开编辑，块级已有


    if (table.querySelector('.edt-tbl-col')) return;


    var theadRow = table.querySelector('thead tr') || table.querySelector('tr');


    if (theadRow && !theadRow.querySelector('.edt-tbl-col')) {


      var th = document.createElement('th'); th.textContent = ''; th.className = 'edt-tbl-col'; th.style.cssText = 'width:28px'; theadRow.appendChild(th);


    }


    var bodyRows = table.querySelectorAll('tbody tr');


    if (!bodyRows.length) bodyRows = table.querySelectorAll('tr');


    var ri = 0;


    bodyRows.forEach(function(row) {


      if (row === theadRow || (row.querySelector('th') && !row.closest('tbody'))) return;


      ri++; if (row.querySelector('.edt-cell')) return;


      var td = document.createElement('td'); td.className = 'edt-cell'; td.style.cssText = 'text-align:center;padding:1px';


      var cells = []; row.querySelectorAll('td:not(.edt-cell)').forEach(function(c){ cells.push(c.textContent.trim()); });


      var rowData = cells.join(' | ');


      var btn = _makeEditIcon('此行数据');


      (function(rd, rn){


        btn.onclick = function(e){ e.stopPropagation();


          window._editScope = {level:'table_row', id:'row'+rn, title:'附件表格·第'+rn+'行', content:rd};


          window._unifiedEditPopup(rd);


        };


      })(rowData, ri);


      td.appendChild(btn); row.appendChild(td);


    });


  });


};


window._makeEditIcon = function(tip) {


  var btn = document.createElement('span');


  btn.className = 'edt-icon';


  btn.innerHTML = ''; /*  removed */


  btn.title = '编辑 / 审核 / 追问 / 重置';


  btn.style.cssText = 'font-size:14px;cursor:pointer;opacity:0.35;transition:opacity 0.2s;margin-left:4px';


  btn.onmouseenter = function(){ this.style.opacity = '1'; };


  btn.onmouseleave = function(){ this.style.opacity = '0.35'; };


  return btn;


};


// ═══ 统一弹窗（Tab切换：编辑/审核/追问） ═══


window._unifiedEditPopup = function(rowData) { return; /* 编辑弹窗已禁用 */ 
};


// ═══ Tab切换 ═══


window._edtSwitchTab = function(tab) {


  var popup = document.getElementById("edt-popup");


  if (!popup) return;


  popup.querySelectorAll(".edt-tab").forEach(function(t){


    var isActive = t.getAttribute("data-tab") === tab;


    t.style.color = isActive ? "#6366f1" : "#94a3b8";


    t.style.fontWeight = isActive ? "600" : "500";


    t.style.borderBottomColor = isActive ? "#6366f1" : "transparent";


  });


  popup.querySelectorAll(".edt-panel").forEach(function(p){ p.style.display = "none"; });


  var panel = document.getElementById("edt-panel-" + tab);


  if (panel) panel.style.display = "block";


};


// ═══ 编辑提交 ═══


window._edtSubmitEdit = function() {


  var input = document.getElementById("edt-edit-input");


  var content = (input||{}).value || "";


  if (!content.trim()) { alert("请输入编辑内容"); return; }


  var scope = window._editScope;


  fetch("/api/agi/content-feedback", {


    method: "POST", headers: {"Content-Type": "application/json"},


    body: JSON.stringify({ chapter: scope.title||"", wrong_content: ((scope.content||"").replace(/<[^>]*>/g,'').slice(0,2000)), correct_content: content })


  }).then(function(r){ return r.json(); }).then(function(d){


    var el = document.getElementById("edt-edit-result");


    if (d.ok) {
      el.textContent = "✅ 已记录，已更新规则库"; el.style.color = "#16a34a";
      // 触发规则传播到五链
      fetch("/api/agi/propagate-to-chains", {method:"POST"}).catch(function(){});
      // 触发人类学习引擎
      fetch("/api/human-learning/learn", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({correction:content, source:"编辑", context:{error_detail:scope.title||""}})}).catch(function(){});
    }


    else { el.textContent = d.message || "失败"; el.style.color = "#dc2626"; }


  });


};


// ═══ 审核提交 ═══


window._edtSubmitAudit = function() {


  var note = (document.getElementById("edt-audit-note")||{}).value || "";


  var scope = window._editScope;


  fetch("/api/agi/content-feedback", {


    method: "POST", headers: {"Content-Type": "application/json"},


    body: JSON.stringify({ chapter: scope.title||"", wrong_content: "", correct_content: "[审核通过] " + note, audit: true })


  }).then(function(r){ return r.json(); }).then(function(d){


    var el = document.getElementById("edt-audit-result");


    if (d.ok) {
      el.textContent = "✅ 审核已记录，已更新规则库"; el.style.color = "#16a34a";
      fetch("/api/agi/propagate-to-chains", {method:"POST"}).catch(function(){});
      // 审核确认=认可引擎判断，增强相关规则置信度
      fetch("/api/human-learning/learn", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({correction:note||"审核确认", source:"审核", context:{action:"confirm"}})}).catch(function(){});
    }


    else { el.textContent = d.message || "失败"; el.style.color = "#dc2626"; }


  });


};


// ═══ 追问 ═══


window._edtSendAsk = function() {


  var input = document.getElementById("edt-ask-input");


  var q = (input||{}).value || "";


  if (!q.trim()) return;


  var hist = document.getElementById("edt-ask-history");


  hist.innerHTML += "<div style=\"margin:3px 0\"><b>你：</b>" + q + "</div>";


  input.value = "";


  var cid = window.currentCompanyId || 1;


  var scope = window._editScope;


  fetch("/api/tax-risk-docs/ask?company_id=" + cid, {


    method: "POST", headers: {"Content-Type": "application/json"},


    body: JSON.stringify({ finding_index: -1, question: q, paragraph_text: ((scope.content||"").replace(/<[^>]*>/g,'').slice(0,2000)) })


  }).then(function(r){ return r.json(); }).then(function(d){


    var txt = d.ok && d.analysis ? d.analysis.map(function(b){ return "<b>"+(b.title||"")+"</b><br>"+(b.content||""); }).join("<br><br>") : (d.message||"无回答");


    hist.innerHTML += "<div style=\"margin:3px 0;background:#f0f4ff;border-radius:4px;padding:6px 10px\"><b>引擎：</b>" + txt + "</div>";


    hist.scrollTop = hist.scrollHeight;


  }).catch(function(){ hist.innerHTML += "<div style=\"color:#dc2626\">网络错误</div>"; });


};


window._edtSubmitAskResult = function() {
  var scope = window._editScope; if (scope && scope.title) { fetch("/api/agi/content-feedback", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({chapter:scope.title||"", wrong_content:"", correct_content:"[追问] 对话已记录"})}).catch(function(){}); fetch("/api/agi/propagate-to-chains", {method:"POST"}).catch(function(){}); fetch("/api/human-learning/learn", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({correction:JSON.stringify(window._askHistory||[]), source:"追问", context:{error_detail:scope.title||""}})}).catch(function(){}); }


  var el = document.getElementById("edt-ask-result");


  el.textContent = "✅ 对话已记录，已更新规则库"; el.style.color = "#16a34a";


};


// ═══════════ 语音输入 ═══════════


window._voiceRecognition = null;


window._startVoiceInput = function() {


  var btn = document.getElementById('voice-btn');


  var inp = document.getElementById('ask-chat-input');


  if (!btn || !inp) return;


  


  var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;


  if (!SpeechRecognition) {


    alert('您的浏览器不支持语音识别，请使用Chrome浏览器。');


    return;


  }


  


  if (window._voiceRecognition) {


    window._voiceRecognition.stop();


    return;


  }


  


  var recognition = new SpeechRecognition();


  recognition.lang = 'zh-CN';


  recognition.interimResults = false;


  recognition.maxAlternatives = 1;


  


  recognition.onstart = function() {


    btn.style.background = '#dc2626';


    btn.textContent = '⏺';


    inp.placeholder = '正在聆听...';


  };


  


  recognition.onresult = function(event) {


    var text = event.results[0][0].transcript;


    inp.value = text;


    inp.focus();


  };


  


  recognition.onerror = function(event) {


    window._voiceRecognition = null;


    btn.style.background = '#f59e0b';


    btn.textContent = '🎤';


    inp.placeholder = '输入问题...';


  };


  


  recognition.onend = function() {


    window._voiceRecognition = null;


    btn.style.background = '#f59e0b';


    btn.textContent = '🎤';


    if (inp.value && inp.value.length > 1) {


      window._sendAskChat();


    }


  };


  


  window._voiceRecognition = recognition;


  recognition.start();


};


// 自动总结多轮对话并保存为纠正规则


window._summarizeAskChat = function() {


  var history = window._askChatHistory || [];


  if (history.length < 2) { alert('需要更多对话才能总结。'); return; }


  


  // 提取核心内容


  var userMessages = history.filter(function(h){return h.role==='user';}).map(function(h){return h.text;});


  var engineModes = history.filter(function(h){return h.role==='engine';}).map(function(h){return h.mode;});


  


  var summary = 'Multi-turn conversation (' + history.length + ' turns). ';


  summary += 'User asked: ' + userMessages.slice(0,2).join('; ') + '. ';


  summary += 'Engine responded in modes: ' + engineModes.join(', ') + '. ';


  


  var fi = window._chatFindingIdx || 0;


  var rpt = window._reportData || {};


  var te = rpt.target_entity || {};


  


  // 收集用户所有输入，拼接为完整纠正内容


  var allUserInput = userMessages.join('\n');


  


  var payload = {


    company_id: window.currentCompanyId || 1,


    industry: te.industry || '',


    biz_model: te.company_type || '',


    finding_type: ((window._allFindings||[])[fi]||{}).type || '',


    original_level: ((window._allFindings||[])[fi]||{}).level || '',


    corrected_risk: '已纠正（多轮对话总结）',


    reason: '[Auto-summarized from ' + history.length + '-turn conversation]\n\n' + allUserInput,


    detail: ((window._allFindings||[])[fi]||{}).detail || '',


    action: 'ask_summary',


    timestamp: new Date().toISOString(),


    conversation_summary: summary


  };


  


  fetch('/api/feedback', {


    method: 'POST',


    headers: {'Content-Type': 'application/json'},


    body: JSON.stringify(payload)


  }).then(function(r){return r.json();}).then(function(data){


    if(data.ok){


      var body = document.getElementById('ask-chat-body');


      if(body) body.innerHTML += '<div style="color:#059669;font-size:12px;margin-top:8px;font-weight:600">Auto-summary saved to correction rules. ' + (data.auto_rule?'Auto-applied to '+data.count+' findings.':'') + '</div>';


      window._askChatHistory = [];


    }


  }).catch(function(){});


};


// 追问对话中保存纠正到规则库


window._saveAskAsCorrection = function(fi, mode) {


  var inp = document.getElementById('ask-chat-input');


  var reason = inp ? inp.value.trim() : '';


  if (!reason) { reason = prompt('Enter the correct answer:'); if (!reason) return; }


  var payload = {


    company_id: window.currentCompanyId || 1,


    industry: ((window._reportData||{}).target_entity||{}).industry || '',


    biz_model: ((window._reportData||{}).target_entity||{}).company_type || '',


    finding_type: ((window._allFindings||[])[fi]||{}).type || '',


    original_level: ((window._allFindings||[])[fi]||{}).level || '',


    corrected_risk: '已纠正（经追问确认）',


    reason: reason,


    detail: ((window._allFindings||[])[fi]||{}).detail || '',


    action: 'ask_correction',


    timestamp: new Date().toISOString()


  };


  fetch('/api/feedback', {


    method: 'POST',


    headers: {'Content-Type': 'application/json'},


    body: JSON.stringify(payload)


  }).then(function(r){return r.json();}).then(function(data){


    if(data.ok){


      alert(data.auto_rule ? '已自动应用到'+data.count+'条发现。' : 'Saved to correction rules engine.');


    }


  }).catch(function(){});


};


function _prValue(value, fallback) {
  if (value === undefined || value === null || value === '') return fallback || '';
  if (Array.isArray(value)) return value.map(function(item){ return _prValue(item, ''); }).filter(Boolean).join('；');
  if (typeof value === 'object') {
    var preferred = value.label || value.name || value.source || value.file || value.description || value.explanation || value.status || value.reference;
    if (preferred) return _prValue(preferred, fallback);
    return Object.keys(value).map(function(key){
      var text = _prValue(value[key], '');
      return text ? key + '：' + text : '';
    }).filter(Boolean).join('；');
  }
  return String(value);
}


function _prList(values, emptyText) {
  var rows = Array.isArray(values) ? values : (values ? [values] : []);
  rows = rows.map(function(item){ return _prValue(item, ''); }).filter(Boolean);
  if (!rows.length) return '<span style="color:#64748b">' + esc(emptyText || '本轮未形成记录') + '</span>';
  return '<ol style="margin:4px 0 4px 20px;padding:0">' + rows.map(function(item){return '<li style="margin:3px 0">' + esc(item) + '</li>';}).join('') + '</ol>';
}


function _prStatus(status) {
  var raw = String(status || '待记录');
  var ok = raw === 'completed' || raw === 'completed_no_candidate' || raw === '已人工确认' || raw === '已关闭';
  var bad = raw === 'blocked' || raw === 'failed' || raw.indexOf('阻断') >= 0;
  var labelMap = {
    completed: '已执行', completed_no_candidate: '已执行/无候选', completed_with_open_items: '已执行/有未决',
    insufficient_data: '资料不足', blocked: '已阻断', failed: '执行失败',
    usable: '解析可用', partial: '部分解析', unknown: '待核验', pending: '待处理',
    human_review_required: '待人工复核', manual_review_required: '待人工复核'
  };
  var color = ok ? '#166534' : (bad ? '#991b1b' : '#9a3412');
  var bg = ok ? '#dcfce7' : (bad ? '#fee2e2' : '#ffedd5');
  return '<span style="display:inline-block;padding:2px 7px;border-radius:4px;background:' + bg + ';color:' + color + ';font-size:11px;font-weight:700">' + esc(labelMap[raw] || raw) + '</span>';
}


function _prFileName(value) {
  if (typeof value === 'string') return value;
  return _prValue(value, '待回查源资料');
}


function _renderProcessInvoiceAppendix(r) {
  var tables = r.invoice_tables || {};
  var groups = [
    {key:'sales', title:'销项发票逐票清册', party:'购买方'},
    {key:'purchases', title:'进项发票逐票清册', party:'销售方'}
  ];
  var html = '';
  groups.forEach(function(group){
    var rows = tables[group.key] || [];
    if (!rows.length) return;
    html += '<h3>' + esc(group.title) + '（' + rows.length + '张）</h3><div style="overflow-x:auto"><table class="tbl"><thead><tr>' +
      '<th>序号</th><th>' + esc(group.party) + '</th><th>发票号码</th><th>开票日期</th><th>品名</th><th>金额</th><th>税额</th><th>价税合计</th><th>票种/状态</th></tr></thead><tbody>';
    rows.forEach(function(inv, index){
      html += '<tr><td>' + (index + 1) + '</td><td>' + esc(inv.counterparty || '') + '</td><td class="mono">' + esc(inv.inv_no || inv.invoice_no || '') + '</td>' +
        '<td>' + esc(inv.date || '') + '</td><td>' + esc(inv.goods || '') + '</td><td class="r">' + esc(_prValue(inv.amount, '0')) + '</td>' +
        '<td class="r">' + esc(_prValue(inv.tax, '0')) + '</td><td class="r">' + esc(_prValue(inv.total, '0')) + '</td><td>' + esc(_prValue(inv.inv_type || inv.status, '待核')) + '</td></tr>';
    });
    html += '</tbody></table></div>';
  });
  return html;
}


function _renderDetailTable(table) {
  if (!table || !Array.isArray(table.rows) || !table.rows.length) return '';
  var cols = Array.isArray(table.columns) ? table.columns : [];
  var head = '<tr>' + cols.map(function(c){ return '<th>' + esc(String(c)) + '</th>'; }).join('') + '</tr>';
  var body = table.rows.map(function(r){
    var tds = cols.map(function(c){
      var v = r[c];
      if (v === undefined || v === null) v = '';
      if (typeof v === 'object') v = JSON.stringify(v);
      return '<td>' + esc(String(v)) + '</td>';
    });
    return '<tr>' + tds.join('') + '</tr>';
  }).join('');
  return '<table class="fact-detail-table"><thead>' + head + '</thead><tbody>' + body + '</tbody></table>';
}

function _renderNarrativeParagraphs(rows, emptyText) {
  rows = Array.isArray(rows) ? rows : [];
  if (!rows.length) return '<p class="i2">' + esc(emptyText || '本轮未形成可展示的段落内容。') + '</p>';
  return rows.map(function(row){
    var heading = row && row.heading ? '<strong>' + esc(row.heading) + '。</strong>' : '';
    var table = row && row.detail_table ? _renderDetailTable(row.detail_table) : '';
    return '<p class="i2" style="margin:10px 0;text-align:justify;line-height:2">' + heading + esc((row && row.text) || '') + '</p>' + table;
  }).join('');
}


function _narrativeSequence(values, emptyText) {
  var rows = Array.isArray(values) ? values : (values ? [values] : []);
  rows = rows.map(function(item){ return _prValue(item, ''); }).filter(Boolean);
  if (!rows.length) return emptyText || '';
  var nums = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十'];
  return rows.map(function(item, index){
    return '第' + (nums[index] || String(index + 1)) + '，' + String(item).replace(/[。；]+$/, '');
  }).join('；') + '。';
}


function _reportChineseNumber(value) {
  var number = Number(value || 0);
  var nums = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十'];
  if (number >= 0 && number <= 10) return nums[number];
  if (number > 10 && number < 20) return '十' + nums[number - 10];
  if (number >= 20 && number < 100) return nums[Math.floor(number / 10)] + '十' + (number % 10 ? nums[number % 10] : '');
  return String(value || '');
}


function _enterpriseMaterialName(item) {
  var raw = String((item && (item.display_name || item.document_type)) || '财税资料');
  return raw.replace(/^资料(?:第)?[一二三四五六七八九十百零0-9]+[：:]\s*/, '') || '财税资料';
}


function _enterpriseMaterialNarrative(item, displayName) {
  if (item && item.narrative) return item.narrative;
  return '本轮收到的第' + _reportChineseNumber(item.seq) + '份资料为' + displayName + '。' +
    '该资料通过' + (item.read_method || '资料读取') + '方式处理，读取结果为' + (item.read_result || '已接收') +
    '。本轮使用范围为：' + (item.use_boundary || '仅使用已经成功读取的内容。');
}


function _enterpriseProblemParagraphs(item) {
  if (Array.isArray(item.narrative_paragraphs) && item.narrative_paragraphs.length) return item.narrative_paragraphs;
  var evidence = item.evidence_summary || {};
  return [
    {heading:'查明的主要事实', text:'经查，' + (item.what_found || '') + '上述数字来自本轮已读取资料的全量筛查，不是抽样估计。'},
    {heading:'检查范围、方法和资料依据', text:'本项使用的资料范围为' + (evidence.source_scope || _prValue(item.source_references, '本轮已上传并成功读取的相关资料')) + '。' + (item.how_confirmed || '稽查人员按照统一口径整理本项资料并重新计算。') + (evidence.workpaper_note || '')},
    {heading:'这件事对企业意味着什么', text:(item.inspection_opinion || '') + (item.possible_effect || '') + (item.amount_conclusion || '')},
    {heading:'应当同时核对的正常业务原因', text:'出现上述情况不当然等于发生税务违法。企业应结合真实业务核对：' + _narrativeSequence(evidence.normal_explanations, '正常业务原因和对企业有利的原始资料。')},
    {heading:'企业应当怎样处理', text:'企业应依据真实业务办理，不得倒签、补造或者作无事实依据的调整。具体处理顺序为：' + _narrativeSequence(item.what_to_do, '按真实业务和原始资料查明原因并作真实处理。')},
    {heading:'怎样才算处理完成', text:'本项只有达到下列条件后才可申请关闭：' + _narrativeSequence(item.completion_standard, '问题能够定位、处理过程能够回查，重新检查不再出现同一差异。')}
  ];
}


function _enterpriseFollowUpParagraphs(item) {
  if (Array.isArray(item.narrative_paragraphs) && item.narrative_paragraphs.length) return item.narrative_paragraphs;
  return [
    {heading:'本轮检查结论', text:'经检查，' + (item.reason || '本轮没有取得完成该项检查所需的完整资料。') + (item.current_conclusion || '本轮不作问题认定') + '。这表示相应检查尚未完成，不表示企业已经发生违法或者少缴税款。'},
    {heading:'被阻断的检查和风险影响', text:'本轮无法完成以下检查：' + _narrativeSequence(item.blocked_checks, '相关业务事实、会计处理和纳税申报检查。') + '目前仍无法排除以下风险方向：' + _narrativeSequence(item.risks_not_excluded, '相关风险需要在取得资料后判断。') + (item.conclusion_effect || '相关检查不得显示为无异常或已经合规。')},
    {heading:'补充资料要求', text:'企业应补充：' + _narrativeSequence(item.required_materials, '能够证明相关业务事实的原始资料。') + '如原资料客观上无法取得，可以提供以下能够证明同一事实的替代资料：' + _narrativeSequence(item.alternative_materials, '能够真实证明同一事项的其他原始资料。')},
    {heading:'下一轮复查程序', text:'资料补齐后，稽查人员将重新执行：' + _narrativeSequence(item.next_checks, item.next_check || '重新运行受影响的全部检查项目。') + '本项完成标准为：' + (item.completion_standard || '资料完整、能够回查，并已完成受影响项目的重新检查。')}
  ];
}


function _buildEnterpriseReadableBody(r, dateStr) {
  var report = r.enterprise_readable_report || {};
  var identity = report.identity || {};
  var summary = report.summary || {};
  var keyPoints = summary.key_points || [];
  var inspector = report.inspector_perspective || {};
  var procedures = report.inspection_procedures || [];
  var materials = report.materials || [];
  var problems = report.confirmed_problems || [];
  var completed = report.completed_checks || [];
  var plans = report.action_plan || [];
  var further = report.further_checks || [];
  var recheck = report.recheck || {};
  var statements = (report.report_statement || []).map(function(item){
    var value = String(item || '');
    if (value.indexOf('本报告以企业内部税务稽查人员视角编制') >= 0) {
      return '本报告采用税务稽查文书式结构和稽查人员陈述口径编制，所列检查事实、处理意见和复查要求用于企业合规整改。';
    }
    return value;
  });
  var displayedAddressee = '被检查企业及其负责人';
  var openingText = String(inspector.opening || '');
  if (!openingText || openingText.indexOf('本报告以内部税务稽查人员的工作口径') >= 0 || openingText.indexOf('稽查人员对被检查企业提交') >= 0) {
    openingText = '根据本轮税务稽查工作安排，现对被检查企业提交并成功读取的财税资料实施检查，并将检查范围、实施程序、查明事实、税务影响、处理意见及后续复查要求报告如下。';
  }
  var headlineText = String(summary.headline || '').replace(/本次内部税务稽查/g, '本次税务稽查');
  var administrativeBoundary = String(inspector.administrative_boundary || '');
  if (!administrativeBoundary || administrativeBoundary.indexOf('企业内部自查文书') >= 0) {
    administrativeBoundary = '本报告由企业使用的财税风险防控系统依据已提交资料生成，用于模拟税务稽查程序并开展合规整改，不具有税务机关行政执法文书效力；税务机关实际检查结论应以依法送达的正式文书为准。';
  }
  var html = '';

  html += '<div class="cover"><h1>涉 税 稽 查 工 作 报 告</h1><div class="sub">' +
    '报告送达对象：' + esc(displayedAddressee) + '<br>' +
    '被检查企业：' + esc(identity.subject_name || '未填写企业名称') + '<br>' +
    '统一社会信用代码：' + esc(identity.taxpayer_id || '未填写') + '<br>' +
    '检查期间：' + esc(identity.period || '以本轮资料记载期间为准') + '<br>' +
    '检查轮次：第' + esc(identity.analysis_round || 1) + '轮<br>' +
    '报告日期：' + esc(report.generated_date || dateStr) +
    '</div></div>';

  html += '<div style="padding:16px 18px;border:2px solid #1e3a8a;background:#eff6ff;margin:0 0 24px;line-height:1.9">' +
    esc(openingText) + '<br>检查范围、总体结论和给企业负责人的整改要求，详见本报告第一章。' +
    '</div>';

  html += '<div class="toc"><a href="#company-conclusion">一、稽查任务和给企业负责人的总体结论</a><br>' +
    '<a href="#company-materials">二、本轮接收和使用的资料</a><br>' +
    '<a href="#company-procedures">三、稽查员实际执行的检查程序</a><br>' +
    '<a href="#company-problems">四、本轮稽查确认的具体问题</a><br>' +
    '<a href="#company-completed">五、已经执行且本轮未发现达到条件异常的检查</a><br>' +
    '<a href="#company-actions">六、稽查处理意见和整改验收标准</a><br>' +
    '<a href="#company-further">七、因资料缺失或不完整而无法完成的检查</a><br>' +
    '<a href="#company-recheck">八、下一轮复查安排</a><br>' +
    '<a href="#company-statement">九、报告性质和使用说明</a></div>';

  html += '<h2 id="company-conclusion">一、稽查任务和给企业负责人的总体结论</h2>' +
    '<p class="i2"><strong>稽查工作原则：</strong>' + esc(inspector.work_principle || '') + '</p>' +
    '<p class="i2"><strong>问题确认标准：</strong>' + esc(inspector.conclusion_rule || '') + '</p>' +
    '<p class="i2">' + esc(headlineText) + '</p>' +
    '<p class="i2">' + esc(summary.owner_message || '') + '</p>' +
    '<p class="i2">本轮共收到<strong>' + (summary.received_material_count || 0) + '个文件</strong>，归并为<strong>' + (summary.material_category_count || materials.length || 0) + '类资料</strong>。其中，已有资料能够证明的具体问题<strong>' + (summary.confirmed_problem_count || 0) + '项</strong>；已经执行且本轮未发现达到条件异常的检查<strong>' + (summary.completed_check_count || 0) + '项</strong>；因资料缺失、资料不完整或者影响范围尚未查清，需要补充资料后再检查的事项<strong>' + (summary.further_check_count || 0) + '项</strong>。</p>';
  if (keyPoints.length) {
    html += '<h3>本轮最需要负责人关注的内容</h3>' + keyPoints.map(function(item){
      return '<p class="i2" style="line-height:2">' + esc(item) + '</p>';
    }).join('');
  }

  // 本轮全部发现一览：让负责人不展开各章就能看到全貌
  var overview = report.discovery_overview || [];
  if (overview.length) {
    html += '<h3>本轮全部发现一览</h3>' +
      '<p class="i2">下表汇总本轮确认问题、已执行检查与受阻检查的全部条目；点击目录可跳转至对应章节查看逐笔明细。</p>' +
      '<table class="fact-detail-table discovery-overview"><thead><tr>' +
      '<th>序号</th><th>类别</th><th>项目</th><th>结论等级</th><th>一句话结论</th>' +
      '</tr></thead><tbody>';
    overview.forEach(function(row){
      var gradeCls = '';
      if (row.grade === '已核定') gradeCls = ' grade-verified';
      else if (row.grade === '待核' || row.grade === '待补资料') gradeCls = ' grade-pending';
      html += '<tr class="' + (gradeCls || '') + '">' +
        '<td>' + esc(row.no || '') + '</td>' +
        '<td>' + esc(row.category || '') + '</td>' +
        '<td>' + esc(row.type || '') + '</td>' +
        '<td>' + esc(row.grade || '') + '</td>' +
        '<td>' + esc(row.summary || '') + '</td>' +
        '</tr>';
    });
    html += '</tbody></table>';
  }

  html += '<h2 id="company-materials">二、本轮接收和使用的资料</h2>' +
    '<p class="i2">为便于企业负责人阅读，本报告不逐个罗列月份文件和英文文件名，而是按中文资料类别归并说明文件数量、读取记录数、读取质量和本轮使用范围；逐文件清单及指纹保留在内部资料底稿中。</p>';
  materials.forEach(function(item){
    var displayName = _enterpriseMaterialName(item);
    html += '<h3>资料' + esc(_reportChineseNumber(item.seq)) + '：' + esc(displayName) + '</h3>' +
      '<p class="i2">' + esc(_enterpriseMaterialNarrative(item, displayName)) + '</p>';
  });
  if (!materials.length) html += '<p class="i2">本轮没有可列示的已读取资料。</p>';

  html += '<h2 id="company-procedures">三、稽查员实际执行的检查程序</h2>' +
    '<p class="i2">以下内容记录本轮实际完成的稽查工作。资料条件不满足的程序会明确写出停止位置和后续要求，不以空结果表示检查已经完成。</p>';
  procedures.forEach(function(item){
    html += '<section class="fact-sec"><div class="ftitle">程序' + esc(item.seq || '') + '：' + esc(item.name || '稽查程序') + '</div>' +
      '<p class="i2" style="line-height:2">' + esc(item.narrative || ('稽查人员执行的工作是：' + (item.work || '') + '本轮程序结果为：' + (item.result || ''))) + '</p></section>';
  });
  if (!procedures.length) html += '<p class="i2">本轮没有形成可向企业负责人展示的稽查程序记录。</p>';

  html += '<h2 id="company-problems">四、本轮稽查确认的具体问题</h2>' +
    '<p class="i2">本部分只写本轮资料能够直接证明的具体问题。没有达到这一标准的事项，不在这里写成企业已经存在的问题。</p>';
  if (!problems.length) {
    html += '<p class="i2">本轮没有发现能够由现有资料直接证明的具体问题。请继续处理第七部分列明的资料缺口事项。</p>';
  }
  problems.forEach(function(item){
    html += '<section class="fact-sec"><div class="ftitle">问题' + esc(item.seq || '') + '：' + esc(item.title || '具体资料问题') + '</div>' +
      _renderNarrativeParagraphs(_enterpriseProblemParagraphs(item), '本项尚未形成完整的段落式检查记录。') +
      '</section>';
  });

  html += '<h2 id="company-completed">五、已经执行且本轮未发现达到条件异常的检查</h2>' +
    '<p class="i2">本部分只列示资料条件满足且规则已经实际执行的项目。“本轮未发现达到条件的异常”不等于企业在其他资料、期间或事项上完全没有风险。</p>';
  if (!completed.length) html += '<p class="i2">本轮没有可单独列示为已经完成且未发现达到检查条件异常的项目。</p>';
  completed.forEach(function(item){
    html += '<section class="fact-sec"><div class="ftitle">检查' + esc(item.seq || '') + '：' + esc(item.title || '') + '</div>' +
      '<p class="i2" style="line-height:2">' + esc(item.narrative || ((item.method || '') + (item.result || '') + (item.boundary || ''))) + '</p></section>';
  });

  html += '<h2 id="company-actions">六、稽查处理意见和整改验收标准</h2>' +
    '<p class="i2">请按照下列顺序办理。所有处理必须建立在真实业务和原始资料基础上，不要为了让系统不再提示而作没有事实依据的调账或申报。</p>';
  if (!plans.length) html += '<p class="i2">本轮没有需要立即处理的已证实具体问题，企业应先按第七部分补充资料。</p>';
  plans.forEach(function(item){
    html += '<h3>' + esc(item.seq || '') + '、先处理“' + esc(item.problem || '') + '”</h3>' +
      '<p class="i2" style="line-height:2">' + esc(item.narrative || ('稽查人员提出的第一项处理动作是：' + (item.first_action || '') + '责任安排为：' + (item.responsibility || '') + '本项整改不能以口头说明作为完成依据，必须达到以下验收条件：' + _narrativeSequence(item.completion_standard, '完成后能够用原始资料重新核对。'))) + '</p>';
  });

  html += '<h2 id="company-further">七、因资料缺失或不完整而无法完成的检查</h2>' +
    '<p class="i2">本部分不是问题认定。系统逐项说明缺少什么、阻断了什么检查、哪些风险目前无法排除、可以提供什么替代资料，以及补齐后下一轮具体重新检查什么。</p>';
  if (!further.length) html += '<p class="i2">本轮没有单独列明的补充资料事项。</p>';
  further.forEach(function(item){
    html += '<section class="fact-sec"><div class="ftitle">事项' + esc(item.seq || '') + '：' + esc(item.title || '') + '</div>' +
      _renderNarrativeParagraphs(_enterpriseFollowUpParagraphs(item), '本项资料缺口尚未形成完整的段落式说明。') + '</section>';
  });

  html += '<h2 id="company-recheck">八、下一轮复查安排</h2>' +
    '<p class="i2"><strong>什么时候重新检查：</strong>' + esc(recheck.trigger || '') + '</p>' +
    '<p class="i2"><strong>重新检查什么：</strong>' + esc(recheck.work || '') + '</p>' +
    '<p class="i2"><strong>怎样判断企业正在趋于合规：</strong>' + esc(recheck.convergence || '') + '</p>';

  html += '<h2 id="company-statement">九、报告性质和使用说明</h2>' +
    '<p class="i2"><strong>文书性质说明。</strong>' + esc(administrativeBoundary) + '</p>';
  statements.forEach(function(item, index){ html += '<p class="i2"><strong>说明' + (index + 1) + '。</strong>' + esc(item || '') + '</p>'; });

  // ═══ 第十章：疑点派生树（洋葱式逐层展开） ═══
  var dtree = report.derivation_tree_report || {};
  if (dtree && dtree.title) {
    html += '<h2 id="company-derivation-tree">十、疑点派生树（稽查思维导图 · 洋葱式逐层展开）</h2>' +
      '<p class="i2">' + esc(dtree.summary || '') + '</p>';
    if (dtree.principle) html += '<p class="i2" style="color:#64748b">' + esc(dtree.principle) + '</p>';
    if (dtree.body) html += '<div class="i2" style="line-height:2;white-space:pre-wrap">' + esc(dtree.body) + '</div>';
  }

  // ═══ 第十一章：跨企业关联交易闭环（供应链网状违法图谱） ═══
  var ceSec = report.cross_enterprise_report || {};
  if (ceSec && ceSec.title) {
    html += '<h2 id="company-cross-enterprise">十一、跨企业关联交易闭环（供应链网状违法图谱）</h2>' +
      '<p class="i2">' + esc(ceSec.summary || '') + '</p>';
    if (ceSec.body) html += '<div class="i2" style="line-height:2;white-space:pre-wrap">' + esc(ceSec.body) + '</div>';
    // 高风险关联单独提示
    if (ceSec.high_risk_count) {
      html += '<p class="i2" style="color:#b91c1c"><strong>高风险关联交易 ' + esc(ceSec.high_risk_count) + ' 条：</strong>上述关联指向同一实际控制人、关联交易或资金往来独立性存疑，须逐笔核实。</p>';
    }
    if (ceSec.note) html += '<p class="i2" style="color:#64748b">' + esc(ceSec.note) + '</p>';
  }

  // ═══ 第十二章：能力边界与彻底稽查路线 ═══
  var capb = report.capability_boundary || {};
  if (capb && capb.title) {
    html += '<h2 id="company-capability-boundary">十二、能力边界与彻底稽查路线</h2>' +
      '<p class="i2">' + esc(capb.opening || '') + '</p>';
    var cov = capb.covered_in_scope || [];
    if (cov.length) {
      html += '<h3>系统已能在数据可触达范围内近乎彻底覆盖</h3><ul class="i2">';
      cov.forEach(function(it){ html += '<li>' + esc(it) + '</li>'; });
      html += '</ul>';
      if (capb.coverage_note) html += '<p class="i2" style="color:#64748b">' + esc(capb.coverage_note) + '</p>';
    }
    var ext = capb.must_rely_on_external || [];
    if (ext.length) {
      html += '<h3>必须依赖外部数据源与人工下户才能查实</h3><table class="tbl"><thead><tr><th>缺口</th><th>为何系统够不着</th><th>所需证据</th></tr></thead><tbody>';
      ext.forEach(function(it){
        html += '<tr><td>' + esc(it.gap || '') + '</td><td>' + esc(it.why || '') + '</td><td>' + esc(it.need || '') + '</td></tr>';
      });
      html += '</tbody></table>';
    }
    var road = capb.roadmap || [];
    if (road.length) {
      html += '<h3>继续向上推进的路线</h3><ol class="i2">';
      road.forEach(function(it){ html += '<li>' + esc(it) + '</li>'; });
      html += '</ol>';
    }
    if (capb.bottom_line) html += '<p class="i2"><strong>底线：</strong>' + esc(capb.bottom_line) + '</p>';
  }

  html += '<div class="seal"><p>稽查报告编制人：_______________　日期：_______________</p>' +
    '<p>被检查企业负责人签收：_______________　日期：_______________</p>' +
    '<p>整改负责人：_______________　复核人员：_______________</p></div>';
  return html;
}


function _buildInspectionProcessBody(r, allF, dateStr) {
  var process = r.inspection_process_report || {};
  var identity = process.identity || {};
  var assignment = process.work_assignment || {};
  var intake = process.material_intake || {};
  var execution = process.procedure_execution || {};
  var workItems = process.item_work_records || [];
  var evidence = process.evidence_and_workpapers || {};
  var disposition = process.interim_disposition || {};
  var recheck = process.recheck_and_follow_up || {};
  var release = process.release_and_signoff || {};
  var processCheck = process.process_compilation_check || {};
  var html = '';

  html += '<div class="cover"><h1>企 业 内 部 涉 税 稽 查 工 作 过 程 报 告</h1><div class="sub">' +
    '文书性质：一键分析形成的内部过程报告草稿<br>' +
    '被检查主体：' + esc(identity.subject_name || '未指定') + '<br>' +
    '检查轮次：第' + esc(identity.analysis_round || 1) + '轮<br>' +
    '资料批次/快照：' + esc(identity.snapshot_id || '待生成') + '<br>' +
    '编制日期：' + esc(dateStr) + '<br>' +
    '当前状态：' + esc(release.release_status || r.release_status || '过程报告草稿_待人工复核') +
    '</div></div>';

  html += '<div style="padding:12px 14px;border:2px solid #1e3a8a;background:#eff6ff;margin:0 0 24px;line-height:1.8">' +
    '<strong>报告定位：</strong>' + esc(process.report_subtitle || '记录本轮检查程序、证据形成过程和未决事项。') +
    '<br><strong>效力边界：</strong>本报告记录企业内部涉税稽查辅助工作的实际过程，不是税务机关检查报告、审理报告、税务处理决定或行政处罚文书。' +
    '</div>';

  html += '<div class="toc"><a href="#ch1">第一章　本轮稽查工作任务与边界</a><br>' +
    '<a href="#ch2">第二章　资料接收、解析与取证准备过程</a><br>' +
    '<a href="#ch3">第三章　稽查程序与模块执行记录</a><br>' +
    '<a href="#ch4">第四章　逐项检查工作记录</a><br>' +
    '<a href="#ch5">第五章　证据、反证、资料缺口与金额底稿</a><br>' +
    '<a href="#ch6">第六章　本轮过程性意见与处理指引</a><br>' +
    '<a href="#ch7">第七章　未决事项、复查安排与报告状态</a><br>' +
    '<a href="#appendix">附件　工作日志与逐票清册</a></div>';

  html += '<h2 id="ch1">第一章 本轮稽查工作任务与边界</h2>' +
    '<table class="tbl2"><tr><th style="width:20%">项目</th><th>本轮工作记录</th></tr>' +
    '<tr><td>任务来源</td><td>' + esc(assignment.source || '') + '</td></tr>' +
    '<tr><td>工作目标</td><td>' + esc(assignment.objective || '') + '</td></tr>' +
    '<tr><td>被检查主体</td><td>' + esc(identity.subject_name || '') + '；统一标识：' + esc(identity.taxpayer_id || '待核验') + '；行业：' + esc(identity.industry || '待核验') + '</td></tr>' +
    '<tr><td>检查期间</td><td>' + esc(identity.period || '以源资料记录期间为准') + '</td></tr>' +
    '<tr><td>检查范围</td><td>' + esc(assignment.scope || r.scope || '') + '</td></tr>' +
    '<tr><td>局限与停止边界</td><td>' + esc(assignment.limitations || r.limitations || '') + '</td></tr>' +
    '<tr><td>行政效力</td><td>无。报告中的风险等级用于安排内部检查顺序，不是违法程度、补税金额或处罚幅度。</td></tr></table>';

  html += '<h2 id="ch2">第二章 资料接收、解析与取证准备过程</h2>' +
    '<p class="i2">' + esc(intake.work_rule || '') + '</p>' +
    '<p class="i2"><strong>接收情况：</strong>共接收' + (intake.received_count || 0) + '份；可用解析' + (intake.usable_count || 0) + '份；部分解析' + (intake.partial_count || 0) + '份；解析阻断' + (intake.blocked_count || 0) + '份；可进入自动计算候选' + (intake.calculation_candidate_count || 0) + '份。</p>' +
    '<div style="overflow-x:auto"><table class="tbl"><thead><tr><th>序号</th><th>资料</th><th>类型</th><th>解析方法</th><th>质量/定位</th><th>逐票或字段复核</th><th>本轮处理</th></tr></thead><tbody>';
  (intake.files || []).forEach(function(file){
    var subjectText = file.invoice_unit_count ? ('逐票核验' + (file.invoice_verified_unit_count || 0) + '/' + file.invoice_unit_count + '，阻断' + (file.invoice_blocked_unit_count || 0)) : '非发票资料/不适用逐票主体核验';
    var fieldText = file.field_review_required ? ('字段复核套用' + (file.field_review_applied || 0) + '/' + file.field_review_required) : '无待套用字段复核';
    html += '<tr><td>' + (file.seq || '') + '</td><td>' + esc(file.source_name || '') + (file.receipt_hash ? '<br><small>回执 ' + esc(String(file.receipt_hash).slice(0,16)) + '…</small>' : '') + '</td>' +
      '<td>' + esc(file.document_type || '') + '</td><td>' + esc(file.extraction_method || '') + '</td><td>' + _prStatus(file.quality_status) + '<br>源位置覆盖 ' + (file.source_locator_coverage || 0) + '%</td>' +
      '<td>' + esc(subjectText) + '<br>' + esc(fieldText) + '</td><td>' + esc(file.work_status || '') + (file.blockers && file.blockers.length ? '<br><strong>阻断：</strong>' + esc(_prValue(file.blockers, '')) : '') + '</td></tr>';
  });
  if (!(intake.files || []).length) html += '<tr><td colspan="7">本轮没有形成可核验的资料接收记录，检查程序停留在资料准备阶段。</td></tr>';
  html += '</tbody></table></div>';

  html += '<h2 id="ch3">第三章 稽查程序与模块执行记录</h2><p class="i2">' + esc(execution.sequence_rule || '') + '</p>' +
    '<table class="tbl"><thead><tr><th>顺序</th><th>工作阶段</th><th>检查目的</th><th>执行状态</th><th>本轮结果</th><th>未决/停止条件</th></tr></thead><tbody>';
  (execution.stages || []).forEach(function(stage){
    html += '<tr><td>' + esc(stage.seq || '') + '</td><td><strong>' + esc(stage.name || '') + '</strong><br><small>' + esc(stage.stage_code || '') + '</small></td>' +
      '<td>' + esc(stage.purpose || '') + '</td><td>' + _prStatus(stage.status) + '</td><td>' + esc(stage.result || '') + '</td>' +
      '<td>' + _prList(stage.open_items || [], '本阶段无单独未决事项') + '<div style="margin-top:5px;color:#64748b"><strong>停止条件：</strong>' + esc(stage.stop_condition || '') + '</div></td></tr>';
  });
  html += '</tbody></table>';

  html += '<h2 id="ch4">第四章 逐项检查工作记录</h2>';
  if (!workItems.length) html += '<p class="i2">本轮未形成具体待核风险事项；这只表示已上传资料未触发可记录事项，不表示企业全部事项无风险。资料缺口和未执行场景仍见第二、三章。</p>';
  workItems.forEach(function(item){
    html += '<section class="fact-sec" id="risk-' + esc(item.risk_id || item.seq) + '"><div class="ftitle">' + (item.seq || '') + '. ' + esc(item.title || '待核事项') + '　' + _prStatus(item.work_status) + '</div>' +
      '<table class="tbl2"><tr><th style="width:20%">工作项目</th><th>过程记录</th></tr>' +
      '<tr><td>事项编号与检查范围</td><td>' + esc(item.risk_id || '') + '；' + esc(_prValue(item.inspection_scope, '待按业务主键定位')) + '</td></tr>' +
      '<tr><td>观察事实</td><td>' + _prList(item.observed_facts, '尚无可定位观察事实') + '</td></tr>' +
      '<tr><td>待证事实</td><td>' + esc(item.target_fact || '') + '</td></tr>' +
      '<tr><td>已执行/拟执行检查程序</td><td>' + _prList(item.procedures_performed, '待制定逐项检查步骤') + '</td></tr>' +
      '<tr><td>支持证据</td><td>' + _prList(item.supporting_evidence, '尚未取得充分支持证据') + '</td></tr>' +
      '<tr><td>反向证据与正常解释</td><td>' + _prList((item.opposing_evidence || []).concat(item.competing_explanations || []), '尚未取得足够反向证据或正常解释') + '</td></tr>' +
      '<tr><td>资料缺口</td><td>' + _prList(item.missing_information, '本项暂无明确资料缺口，仍须复核完整性') + '</td></tr>' +
      '<tr><td>政策核验</td><td>' + esc(_prValue(item.policy_review, '待按事实期间核验官方依据')) + '</td></tr>' +
      '<tr><td>金额底稿</td><td>' + esc(_prValue(item.amount_workpaper, '尚未形成确定金额或可复算底稿')) + '</td></tr>' +
      '<tr><td>本轮过程性意见</td><td>' + esc(item.process_opinion || '') + '</td></tr>' +
      '<tr><td>停止条件</td><td>' + esc(item.stop_condition || '') + '</td></tr>' +
      '<tr><td>定性边界</td><td><strong>' + esc(item.determination_boundary || '') + '</strong></td></tr></table></section>';
  });

  html += '<h2 id="ch5">第五章 证据、反证、资料缺口与金额底稿</h2>' +
    '<p class="i2">' + esc(evidence.boundary || '') + '</p>' +
    '<h3>一、证据溯源索引</h3><table class="tbl"><thead><tr><th>事项编号</th><th>资料来源</th><th>溯源编号</th><th>状态</th><th>证据边界</th></tr></thead><tbody>';
  (evidence.evidence_index || []).forEach(function(row){
    html += '<tr><td>' + esc(row.risk_id || '') + '</td><td>' + esc(_prFileName(row.source)) + '</td><td>' + esc(row.trace_id || '待建立') + '</td><td>' + esc(row.status || '') + '</td><td>' + esc(row.evidence_boundary || '') + '</td></tr>';
  });
  if (!(evidence.evidence_index || []).length) html += '<tr><td colspan="5">本轮尚未形成完整证据索引；相关事项保持未决并禁止正式发布。</td></tr>';
  html += '</tbody></table><h3>二、补充资料工作单</h3><table class="tbl"><thead><tr><th>事项编号</th><th>应补资料</th><th>证明目的</th><th>边界</th></tr></thead><tbody>';
  (evidence.missing_information_requests || []).forEach(function(request){
    html += '<tr><td>' + esc(request.risk_id || '') + '</td><td>' + esc(_prValue(request.items, '')) + '</td><td>' + esc(request.purpose || '') + '</td><td>' + esc(request.boundary || '') + '</td></tr>';
  });
  if (!(evidence.missing_information_requests || []).length) html += '<tr><td colspan="4">本轮没有形成明确补件工作单。</td></tr>';
  html += '</tbody></table><p class="i2"><strong>金额底稿状态：</strong>已形成可识别金额底稿' + (evidence.amount_workpaper_count || 0) + '项；未形成底稿的事项不得写成确定补税、退税、罚款或其他金额结论。</p>';

  html += '<h2 id="ch6">第六章 本轮过程性意见与处理指引</h2><p class="i2">' + esc(disposition.decision_boundary || '') + '</p>';
  (disposition.items || []).forEach(function(item, index){
    html += '<h3>' + (index + 1) + '. ' + esc(item.title || '') + '（' + esc(item.risk_id || '') + '）</h3>' +
      '<p class="i2"><strong>当前状态：</strong>' + esc(item.current_status || '') + '</p>' +
      '<p class="i2"><strong>过程性意见：</strong>' + esc(item.process_opinion || '') + '</p>' +
      '<p class="i2"><strong>处理步骤：</strong></p>' + _prList(item.handling_guidance, '待责任部门依据真实事实制定') +
      '<p class="i2"><strong>完成标准：</strong></p>' + _prList(item.completion_criteria, '待建立可验证完成标准') +
      '<p class="i2"><strong>禁止事项：</strong></p>' + _prList(item.forbidden_actions, '禁止倒签、补造、删改或无事实依据调整');
  });

  html += '<h2 id="ch7">第七章 未决事项、复查安排与报告状态</h2>' +
    '<p class="i2"><strong>本轮未决：</strong>' + (disposition.open_item_count || 0) + '项逐项检查记录仍需补资料、复算或人工审理。</p>' +
    '<p class="i2"><strong>下一轮触发：</strong>' + esc(recheck.trigger || '') + '</p>' +
    '<p class="i2"><strong>下一轮：</strong>第' + esc(recheck.next_round || ((identity.analysis_round || 1) + 1)) + '轮；必须重跑：' + esc(_prValue(recheck.must_rerun, '全部适用场景')) + '。</p>' +
    '<p class="i2"><strong>轮次比较：</strong>' + esc(_prValue(recheck.comparison_dimensions, '风险、资料、金额、政策及复核状态')) + '。</p>' +
    '<p class="i2"><strong>趋于合规规则：</strong>' + esc(recheck.convergence_rule || '') + '</p>' +
    '<p class="i2"><strong>停止规则：</strong>' + esc(recheck.stop_rule || '') + '</p>' +
    '<h3>一、报告编制检查</h3><p class="i2">过程报告检查通过' + (processCheck.passed || 0) + '/' + (processCheck.total || 0) + '项；失败' + (processCheck.failed || 0) + '项。</p>' +
    '<table class="tbl"><thead><tr><th>编号</th><th>检查项目</th><th>状态</th></tr></thead><tbody>';
  (processCheck.details || []).forEach(function(check){
    html += '<tr><td>' + esc(check.id || '') + '</td><td>' + esc(check.label || '') + '</td><td>' + _prStatus(check.passed ? 'completed' : 'blocked') + '</td></tr>';
  });
  html += '</tbody></table><h3>二、发布与审签边界</h3>' +
    '<p class="i2"><strong>报告状态：</strong>' + esc(release.release_status || '') + '</p>' +
    '<p class="i2"><strong>发布边界：</strong>' + esc(release.release_boundary || r.release_boundary || '') + '</p>' +
    '<p class="i2"><strong>正式发布：</strong>当前不具备自动正式发布资格。只要还有待审、资料不足、政策待核、金额待复算或角色不独立，报告必须保持内部过程草稿。</p>' +
    '<div class="seal"><p>检查工作记录编制人：_______________　日期：_______________</p>' +
    '<p>证据复核人：_______________　政策与金额复核人：_______________</p>' +
    '<p>独立报告批准人：_______________　日期：_______________</p></div>';

  html += '<h2 id="appendix">附件 工作日志与逐票清册</h2><h3>附件一：一键分析工作日志</h3>' +
    '<table class="tbl"><thead><tr><th>序号</th><th>系统工作记录</th></tr></thead><tbody>';
  (execution.execution_log || []).forEach(function(log, index){
    html += '<tr><td>' + (index + 1) + '</td><td>' + esc(_prValue(log, '')) + '</td></tr>';
  });
  if (!(execution.execution_log || []).length) html += '<tr><td colspan="2">本轮未返回可展示的过程日志。</td></tr>';
  html += '</tbody></table><h3>附件二：资料与回执索引</h3>' +
    '<table class="tbl"><thead><tr><th>序号</th><th>资料</th><th>质量</th><th>回执</th><th>自动计算边界</th></tr></thead><tbody>';
  (intake.files || []).forEach(function(file){
    html += '<tr><td>' + file.seq + '</td><td>' + esc(file.source_name || '') + '</td><td>' + esc(file.quality_status || '') + '</td><td>' + esc(file.receipt_hash || '待生成') + '</td><td>' + (file.safe_for_automatic_calculation ? '可进入候选，仍须业务审理' : '不得直接用于金额定稿') + '</td></tr>';
  });
  html += '</tbody></table>' + _renderProcessInvoiceAppendix(r);
  return html;
}


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


    // 全局容器——所有报告内容统一在此


    + '#tda-report-area{font-family:"PingFang SC","Microsoft YaHei","SimSun",serif;font-size:14px;line-height:1.85;color:#1a1a2e;max-width:none;margin:0;padding:16px 0;background:#fff}'


    + '#tda-report-area *{margin:0;padding:0;box-sizing:border-box}'


    + '#tda-report-area p,#tda-report-area div,#tda-report-area span,#tda-report-area li{font-family:inherit;font-size:inherit;line-height:inherit;color:inherit}'


    + '#tda-report-area h2{font-size:17px;font-weight:700;margin:32px 0 16px;padding-bottom:8px;border-bottom:2px solid #1a1a2e;text-align:left;letter-spacing:2px;display:flex;align-items:center;justify-content:space-between;color:#1a1a2e}'


    + '#tda-report-area h2 .edt-icon{flex-shrink:0;margin-left:8px}'


    + '#tda-report-area h3{font-size:14px;font-weight:600;margin:18px 0 10px;color:#1a1a2e;display:flex;align-items:center;justify-content:space-between}'
    + '#tda-report-area h3 .edt-icon{flex-shrink:0;margin-left:8px}'
    + '#tda-report-area h4{font-size:13px;font-weight:600;margin:12px 0 8px;color:#1a1a2e;display:flex;align-items:center;justify-content:space-between}'
    + '#tda-report-area h4 .edt-icon{flex-shrink:0;margin-left:8px}'


    + '#tda-report-area p{margin:8px 0;text-align:justify;line-height:1.85;color:#1a1a2e}'


    + '#tda-report-area p.i2,#tda-report-area p[class*=\"i2\"]{text-indent:2em}'


    + '#tda-report-area p.edt-p-flex{display:flex !important;align-items:flex-start;gap:0}'


    + '#tda-report-area p.edt-p-flex > span:first-child{flex:1;min-width:0;text-align:justify}'


    + '#tda-report-area p.edt-p-flex.i2 > span:first-child,#tda-report-area p.edt-p-flex[class*=\"i2\"] > span:first-child{text-indent:2em}'


    + '#tda-report-area p.edt-p-flex .edt-icon{flex-shrink:0;margin-left:4px;align-self:flex-start;line-height:1.85}'


    + '#tda-report-area .agi-quality-audit{display:block!important;width:100%!important;max-width:none!important;min-width:0}'


    + '#tda-report-area .agi-quality-audit > p,#tda-report-area .agi-quality-audit > div{display:block;width:100%;max-width:none;overflow-wrap:anywhere}'


    // 表格


    + '#tda-report-area table.tbl,#tda-report-area table.tbl2{width:100%;border-collapse:collapse;margin:16px 0;font-size:12px}'


    + '#tda-report-area table.tbl th,#tda-report-area table.tbl2 th{background:#f1f5f9;padding:8px 12px;text-align:left;border:1px solid #cbd5e1;font-weight:600;font-size:12px;color:#334155;white-space:nowrap}'


    + '#tda-report-area table.tbl td,#tda-report-area table.tbl2 td{padding:7px 12px;border:1px solid #e2e8f0;white-space:normal;line-height:1.7;vertical-align:top;font-size:12px;color:#334155}'

    + '#tda-report-area table.fact-detail-table{width:100%;border-collapse:collapse;margin:10px 0 14px;font-size:12px;background:#fff}'
    + '#tda-report-area table.fact-detail-table th{background:#1e3a8a;color:#fff;padding:7px 10px;text-align:left;border:1px solid #1e3a8a;font-weight:600;white-space:nowrap}'
    + '#tda-report-area table.fact-detail-table td{padding:6px 10px;border:1px solid #dbeafe;white-space:normal;line-height:1.6;vertical-align:top;color:#1a1a2e}'
    + '#tda-report-area table.fact-detail-table tbody tr:nth-child(even){background:#f5f8ff}'
    + '#tda-report-area table.fact-detail-table.discovery-overview td{font-size:12px}'
    + '#tda-report-area table.fact-detail-table tbody tr.grade-verified{background:#ecfdf5}'
    + '#tda-report-area table.fact-detail-table tbody tr.grade-verified td:first-child{color:#047857;font-weight:600}'
    + '#tda-report-area table.fact-detail-table tbody tr.grade-pending{background:#fffbeb}'
    + '#tda-report-area table.fact-detail-table tbody tr.grade-pending td:first-child{color:#b45309;font-weight:600}'


    + '#tda-report-area .r{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}'


    + '#tda-report-area tbody tr:hover{background:#f8fafc}'


    // 封面


    + '#tda-report-area .cover{text-align:center;padding:50px 0 40px;border-bottom:3px double #1a1a2e;margin-bottom:32px}'


    + '#tda-report-area .cover h1{font-size:24px;font-weight:900;letter-spacing:8px;margin-bottom:16px;color:#1a1a2e}'


    + '#tda-report-area .cover .sub{font-size:14px;color:#555;line-height:2.4}'


    // 所有盒子/卡片/权利段/附件/intel/aar智能卡——全裸奔


    + '#tda-report-area .fact-sec,#tda-report-area .rights-sec,#tda-report-area .appendix,#tda-report-area .conclusion-box,#tda-report-area .law-ref,#tda-report-area .smart-card,#tda-report-area div[id^=\"rpt-smart\"]{margin:14px 0;padding:0;border:none;border-radius:0;background:transparent;box-shadow:none;font-size:14px;line-height:1.85;color:#1a1a2e}'


    + '#tda-report-area .fact-sec .ftitle,#tda-report-area .rights-sec .rtitle,#tda-report-area .appendix .atitle{font-size:14px;font-weight:700;margin-bottom:8px}'


    + '#tda-report-area .fact-sec .frow,#tda-report-area .rights-sec .ritem,#tda-report-area .appendix .aitem{margin:5px 0;font-size:14px;line-height:1.85;padding:0;border:none;background:transparent;border-radius:0}'


    + '#tda-report-area .rights-sec div,#tda-report-area .rights-sec .ritem div,#tda-report-area .rights-sec div[style]{padding:0;margin:5px 0;background:transparent;border:none;border-left:none;border-radius:0;font-size:14px;color:#1a1a2e;line-height:1.85}'


    + '#tda-report-area .conclusion-box.red{color:#dc2626}'


    + '#tda-report-area .conclusion-box.amber{color:#d97706}'


    + '#tda-report-area .conclusion-box.green{color:#16a34a}'


    // 标签


    + '#tda-report-area .tag{display:inline-block;padding:1px 8px;border-radius:3px;font-size:11px;font-weight:500}'


    + '#tda-report-area .rtag{color:#c92a2a;font-weight:700}'


    + '#tda-report-area .atag{color:#e67700;font-weight:600}'


    + '#tda-report-area .gtag{color:#2b8a3e}'


    // 目录/签章


    + '#tda-report-area .toc{margin:28px 0;padding:0 40px}'


    + '#tda-report-area .toc a{color:#1a1a2e;text-decoration:none;font-size:14px;line-height:2.4}'


    + '#tda-report-area .seal{text-align:right;margin-top:50px;padding-top:18px;border-top:1px solid #ddd;line-height:2.2;font-size:13px}'


    // @media


    + '@media(max-width:768px){#tda-report-area{padding:16px 12px}}'


    + '</style><div id="rr-report">';


  // 企业版是主文书；专业过程底稿继续保留在后台，供内部复查和历史轮次追溯。
  if (r.enterprise_readable_report && ['税务稽查文书式报告', '内部税务稽查员报告', '企业易读检查结果'].indexOf(r.enterprise_readable_report.compilation_style) >= 0) {
    h += _buildEnterpriseReadableBody(r, dateStr);
    h += '</div>';
    return {
      html: h,
      renderedModules: ['稽查任务与总体结论','中文资料清单','稽查程序','稽查确认问题','处理意见与验收','受阻检查','下一轮复查','报告说明'],
      skippedModules: []
    };
  }

  // 旧缓存没有企业版时展示原过程报告，保证历史轮次可回看。
  if (r.inspection_process_report && r.inspection_process_report.compilation_style === 'inspection_work_process') {
    h += _buildInspectionProcessBody(r, allF, dateStr);
    h += '</div>';
    return {
      html: h,
      renderedModules: ['process-cover','process-assignment','process-material-intake','process-procedure-ledger','process-item-work-records','process-evidence-workpapers','process-guidance','process-recheck-release','process-appendix'],
      skippedModules: []
    };
  }


  // fallback 使用7章标准结构渲染


  h += '<div class="cover"><h1>企 业 内 部 税 务 合 规 风 险 分 析 报 告</h1><div class="sub">'


    + '报告编号：未配置（交付前由有权人员按适用制度填写）<br>'


    + '被审查企业：' + (te.name || te.company_name || '未指定') + '<br>'


    + '报告日期：'+dateStr+'<br>'


    + '资料数量：' + (r.files_count || allF.length) + '份'


    + '</div></div>';


  // ═══ 目录 ═══


  h += '<div class="toc">';


  h += '<a href="#ch1"><span class="num">一、</span>公司和基本情况</a><br>';


  h += '<a href="#ch2"><span class="num">二、</span>审查过程</a><br>';


  h += '<a href="#ch3"><span class="num">三、</span>发现的问题</a><br>';


  h += '<a href="#ch4"><span class="num">四、</span>总体结论</a><br>';


  h += '<a href="#ch5"><span class="num">五、</span>整改建议</a><br>';


  h += '<a href="#ch6"><span class="num">六、</span>您的权利</a><br>';


  h += '<a href="#ch7"><span class="num">七、</span>签字页</a><br>';


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


  


  // ═══ 第一章：公司和基本情况 ═══


  h += '<h2 id="ch1">第一章 公司和基本情况</h2>';


  h += '<p class="i2">本系统根据企业上传的' + (r.files_count || 0) + '份经营资料执行涉税风险辅助分析。观察信号只用于形成待核事项和补充资料清单，不构成税务机关立案、检查、审理、处罚或执行决定。以下列示主体情况和本次分析范围。</p>';


  h += '<table class="tbl">';


  h += '<tr><td class="lbl">被审查企业</td><td>' + (te.name || te.company_name || '-') + '</td></tr>';


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


  h += '<tr><td class="lbl">审查期间</td><td>' + (te.period || '全量数据分析期间') + '</td></tr>';


  h += '<tr><td class="lbl">审查范围</td><td>' + _detectTaxScope(r, te).join('、') + '</td></tr>';


  h += '<tr><td class="lbl">执行标准</td><td>系统方法论场景合同、报告18项质量门禁及业务期间现行有效税收法律规范；正式稽查程序以有权机关依法启动和送达的文书为准</td></tr>';


  h += '</table>';


  // ═══ 第二章：审查过程情况 ═══


  h += '<h2 id="ch2">第二章 审查过程</h2>';

  var totalRecords = 0;
  var fileResults = r.file_results || [];
  var ftypeCounts = {};
  var allFileNames = [];
  for (var tri = 0; tri < fileResults.length; tri++) {
    var fr3 = fileResults[tri];
    if (!fr3) continue;
    var ft = fr3.type || 'other';
    var acts = fr3.actions || [];
    for (var ai = 0; ai < acts.length; ai++) {
      var m = acts[ai].match(/(\d+)条/);
      if (m) totalRecords += parseInt(m[1]) || 0;
    }
    ftypeCounts[ft] = (ftypeCounts[ft] || 0) + 1;
    if (fr3.file && fr3.file.original_name) allFileNames.push(fr3.file.original_name);
  }
  
  var mi = (r.comprehensive || {}).material_intel || {};
  var ic = r.invoice_counts || {};
  var ds = r.domain_summary || [];
  
  h += '<p class="i2"><strong>收到资料。</strong>本次共接收' + (r.files_count || fileResults.length) + '份电子资料，识别出';
  var typeParts = [];
  if (ftypeCounts.salary) typeParts.push('工资表' + ftypeCounts.salary + '份');
  if (ftypeCounts.social_security) typeParts.push('社保' + ftypeCounts.social_security + '份');
  if (ftypeCounts.housing_fund) typeParts.push('公积金' + ftypeCounts.housing_fund + '份');
  if (ftypeCounts.sales_invoice) typeParts.push('销项发票' + ftypeCounts.sales_invoice + '份');
  if (ftypeCounts.purchase_invoice) typeParts.push('进项发票' + ftypeCounts.purchase_invoice + '份');
  if (ftypeCounts.invoice_mixed) typeParts.push('逐票核验混合购销发票' + ftypeCounts.invoice_mixed + '份');
  if (ftypeCounts.input_vat_deduction) typeParts.push('进项抵扣' + ftypeCounts.input_vat_deduction + '份');
  if (ftypeCounts.bank || ftypeCounts.bank_statement) typeParts.push('银行流水' + (ftypeCounts.bank || ftypeCounts.bank_statement) + '份');
  if (typeParts.length > 0) h += typeParts.join('、') + '，共' + typeParts.length + '类资料';
  h += '，提取有效数据' + (totalRecords || '若干') + '条。</p>';

  var parseSummary = r.parse_quality_summary || {};
  if (parseSummary.total) {
    var parseTone = parseSummary.release_blocked ? '#b45309' : '#166534';
    h += '<p class="i2"><strong>解析质量。</strong><span style="color:' + parseTone + '">可用解析' + (parseSummary.usable || 0) + '份、部分解析' + (parseSummary.partial || 0) + '份、解析阻断' + (parseSummary.blocked || 0) + '份，其中' + (parseSummary.calculation_ready || 0) + '份可进入自动计算候选。</span>' +
      (parseSummary.release_blocked ? ' 部分解析或阻断资料已转为补件/重解析缺口，本报告只能作为内部草稿，不能正式发布。' : ' 解析质量门已通过，但资料真实性、合法性和税务结论仍须人工审理。') + '</p>';
    if (parseSummary.invoice_subject_blocker_count) {
      h += '<p class="i2" style="color:#b91c1c"><strong>发票主体归属门禁。</strong>本轮仍有' + parseSummary.invoice_subject_blocker_count + '张/组发票存在账套主体、购销方向或关键字段冲突，已停止进入进销项金额计算并阻断正式发布：' + (parseSummary.invoice_subject_blockers || []).map(function(item){return (item.source_name || '未命名发票') + '/' + (item.unit_ref || '整份文件') + (item.invoice_no ? '/票号' + item.invoice_no : '') + '（' + (item.state_label || item.state || '待核验') + '：' + (item.basis || '') + '）';}).join('；') + '。</p>';
    }
  }

  var ocrReceipts = fileResults.map(function(item){return item && item.parse_receipt || {};}).filter(function(receipt){return receipt.extraction_method === 'ocr';});
  if (ocrReceipts.length) {
    var ocrRuntime = ocrReceipts[0].ocr_runtime_status || {};
    var ocrCandidates = ocrReceipts.reduce(function(total, receipt){return total + ((receipt.field_review_candidates || []).length || 0);},0);
    var ocrApplied = ocrReceipts.reduce(function(total, receipt){return total + (((receipt.field_review_summary || {}).approved_applied) || 0);},0);
    h += '<p class="i2"><strong>扫描件识别。</strong>' + (ocrRuntime.ready ? ('离线OCR引擎已就绪（' + ((ocrRuntime.engines || []).join('、') || '本机引擎') + '）') : ('OCR引擎未就绪：' + (ocrRuntime.blocking_reason || '原因待核验'))) + '；本轮生成关键字段候选' + ocrCandidates + '项，已在本轮按原文件指纹和定位套用独立复核结果' + ocrApplied + '项。未完成逐字段确认、不同人员复核和下一轮全量复查前，不得作为确定金额或正式发布依据。</p>';
  }

  var documentEvidence = r.document_evidence_index || [];
  if (documentEvidence.length) {
    var locatedDocuments = documentEvidence.filter(function(item){return (item.source_locator_coverage || 0) === 100;}).length;
    var mappedDocuments = documentEvidence.filter(function(item){return item.field_mapping_status === 'complete';}).length;
    h += '<p class="i2"><strong>证据定位。</strong>已为' + documentEvidence.length + '份资料建立文档级索引，其中' + locatedDocuments + '份达到解析行100%定位覆盖，' + mappedDocuments + '份完成财税字段映射。定位和字段映射只用于回查与复核，不替代原件真实性、合法性和关联性审查。</p>';
  }
  
  h += '<p class="i2"><strong>数据概览。</strong>';
  var ov = [];
  var bk = mi['银行流水'] || {};
  if (bk.exists && bk['笔数']) ov.push('银行流水共' + bk['笔数'] + '笔，总收款' + (bk['总收款']||'?') + '，总付款' + (bk['总付款']||'?'));
  var inv = mi['发票'] || {};
  if (inv.exists) ov.push('销项' + (ic.sales||0) + '张、进项' + (ic.purchases||0) + '张');
  var sl = mi['工资'] || {};
  if (sl.exists) ov.push('工资' + (sl['员工人数']||'?') + '人，人均' + (sl['人均工资']||'?'));
  var ss = mi['社保'] || {};
  if (ss.exists) ov.push('社保' + (ss['记录条数']||'?') + '条，缴费' + (ss['总缴费金额']||'?'));
  h += ov.join('。') + '。</p>';
  
  var activeDomains = [];
  for (var di = 0; di < ds.length; di++) {
    if (ds[di] && ds[di].count > 0) activeDomains.push(ds[di].name || ds[di].domain || '');
  }
  h += '<p class="i2"><strong>分析方法。</strong>基于以上资料，系统自动执行了' + activeDomains.length + '个维度的交叉核查：' + (activeDomains.length > 0 ? activeDomains.join('、') : '多维度比对') + '。其中产生关注事项的分析域详见第三章，其余未产生信号的域自动跳过，不占用报告篇幅。</p>';

h += '<h2 id="ch3">第三章 发现的问题</h2>';


  


  var risks = allF.filter(function(f){ return f.level === '高风险' || f.level === '极高风险'; });


  var mids = allF.filter(function(f){ return f.level === '中风险'; });


  var lows = allF.filter(function(f){ return f.level !== '高风险' && f.level !== '极高风险' && f.level !== '中风险'; });


  var allSorted = risks.concat(mids).concat(lows);


  


  var reportCards = r.risk_register || ((r._report_package||{}).risk_register) || [];
  var reportTasks = r.rectification_tasks || ((r._report_package||{}).rectification_tasks) || [];
  var reportRecheck = r.recheck_plan || ((r._report_package||{}).recheck_plan) || {};
  var coverageClosure = r.coverage_closure || ((r.scenario_execution||{}).coverage_closure) || {};
  var closureCounts = coverageClosure.counts || {};
  if (coverageClosure.total_items) {
    h += '<h3>一键分析闭环台账</h3>';
    h += '<p class="i2">本轮应查项目共<strong>' + coverageClosure.total_items + '</strong>项，全部已生成唯一处置状态和原因；静默跳过<strong>' + (coverageClosure.silent_skip_count||0) + '</strong>项。未见阈值异常不等同于企业完全合规，资料不足、执行失败和待人工复核事项必须进入下一轮。</p>';
    h += '<table class="tbl"><thead><tr><th>已发现</th><th>未见阈值异常</th><th>资料不足</th><th>不适用</th><th>执行失败</th><th>待人工复核</th></tr></thead><tbody><tr>' +
      '<td>' + (closureCounts.finding||0) + '</td>' +
      '<td>' + (closureCounts.no_exception_observed||0) + '</td>' +
      '<td>' + (closureCounts.insufficient_data||0) + '</td>' +
      '<td>' + (closureCounts.not_applicable||0) + '</td>' +
      '<td>' + (closureCounts.execution_failed||0) + '</td>' +
      '<td>' + (closureCounts.human_review_required||0) + '</td></tr></tbody></table>';
    h += '<details style="margin:10px 0 18px"><summary style="cursor:pointer;font-weight:600;color:#1e3a8a">展开全部规则与场景执行明细</summary>';
    h += '<table class="tbl"><thead><tr><th>编号</th><th>类型</th><th>项目</th><th>状态</th><th>原因/下一步</th></tr></thead><tbody>';
    (coverageClosure.items||[]).forEach(function(item){
      h += '<tr><td>' + escHtml(item.item_id||'') + '</td><td>' + escHtml(item.item_type==='atomic_rule'?'通用规则':(item.item_type==='industry_scene'?'行业场景':'治理门禁')) + '</td><td>' + escHtml(item.name||'') + '</td><td>' + escHtml(item.status_label||item.status||'') + '</td><td>' + escHtml(item.reason||'') + '</td></tr>';
    });
    h += '</tbody></table></details>';
  }
  h += '<p class="i2">经分析，共形成<strong>' + allF.length + '</strong>项待核事项。风险等级和分数仅用于安排核验顺序，不代表违法定性、确定税额、处罚或移送结论。</p>';


  


  if (reportCards.length > 0) {
    for (var rci = 0; rci < reportCards.length; rci++) {
      var card = reportCards[rci] || {};
      var ce = card.evidence || {};
      var cim = card.investigation_method || {};
      var cp = card.policy || {};
      var csteps = cim.steps || [];
      h += '<div style="border:1px solid #cbd5e1;border-radius:8px;padding:14px;margin:12px 0;background:#fff">';
      h += '<p class="i2" style="margin:0 0 8px"><strong>【风险卡' + (rci+1) + '】' + (card.title||'待核涉税事项') + '</strong></p>';
      h += '<p class="i2"><strong>编号：</strong>' + (card.risk_id||'') + '　<strong>核验优先级：</strong>' + (card.priority_level||'待核验') + '　<strong>当前状态：</strong>' + (card.conclusion_state||'待人工复核') + '</p>';
      h += '<p class="i2"><strong>完整表述：</strong>' + (card.statement||'') + '</p>';
      h += '<p class="i2"><strong>待证事实：</strong>' + (card.target_fact||'') + '</p>';
      h += '<p class="i2"><strong>仍缺资料：</strong>' + ((card.missing_information||[]).join('、')||'暂无明确缺口，仍须复核完整性') + '</p>';
      h += '<p class="i2"><strong>竞争解释：</strong>' + ((card.competing_explanations||[]).join('、')||'尚待核验') + '</p>';
      h += '<p class="i2"><strong>调查起点：</strong>' + (cim.start||'先确定主体、事项、期间和业务主键') + '</p>';
      if (csteps.length) {
        h += '<ol style="margin:6px 0 8px 32px">';
        for (var csi=0; csi<csteps.length; csi++) h += '<li>' + (typeof csteps[csi]==='string' ? csteps[csi] : (csteps[csi].action||'')) + '</li>';
        h += '</ol>';
      }
      h += '<p class="i2"><strong>停止条件：</strong>' + (cim.stop_condition||'资料不足或主要反向解释未核验时停止外推') + '</p>';
      h += '<p class="i2"><strong>政策状态：</strong>' + (cp.validity||'待按事实期间核验官方有效依据') + '</p>';
      h += '<p class="i2"><strong>证据边界：</strong>支持材料' + ((ce.supporting||[]).length) + '项、反向材料' + ((ce.opposing||[]).length) + '项；系统索引不替代原件核验、法定取证和人工审签。</p>';
      h += '</div>';
    }
  } else {
  for (var fi = 0; fi < allSorted.length; fi++) {


    var f = allSorted[fi];


    if (f._deleted) continue;


    var lv = f.level || '中风险';


    var finType = (f.type || '未命名发现').replace(/^Synthesis:\s*/,'').replace(/^Causal:\s*/,'').replace(/^[\w]+:\s*/,'');


    var safeFinType = finType.replace(/\\/g, '\\\\').replace(/'/g, "\\'");


    var mergeCount = f._mergeCount || 0;


    


    // ── 发现标题（含发现级编辑/审核/追问按钮）──


    var realIdx = f._idx !== undefined ? f._idx : fi;


    h += '<p style="text-indent:2em;margin:8px 0;text-align:justify;display:flex;align-items:center;gap:0">' +


      '<span style="flex:1;min-width:0"><strong>【发现' + (fi+1) + '】' + finType + '</strong> —— 风险等级：' + lv;


    // ── AGI增强徽章 ──


    if (f._agi_enhanced) {


      var agi = f._agi_enhanced;


      var cf = agi.confidence || {};


      var bw = agi.boundary || {};


      if (cf.confidence !== undefined) {


        var sc = cf.confidence;


        var cfColor = sc >= 0.7 ? '#16a34a' : (sc >= 0.4 ? '#d97706' : '#dc2626');


        h += ' <span style="font-size:10px;color:' + cfColor + ';border:1px solid ' + cfColor + ';border-radius:3px;padding:0 4px">置信度' + Math.round(sc*100) + '%</span>';


      }


      if (bw.level) {


        h += ' <span style="font-size:10px;color:#6366f1;border:1px solid #6366f1;border-radius:3px;padding:0 4px">' + bw.level + '</span>';


      }


      if (agi.penetration) {


        h += ' <span style="font-size:10px;color:#f59e0b;border:1px solid #f59e0b;border-radius:3px;padding:0 4px">已穿透</span>';


      }


      // 审核结论


      if (agi.audit_verdict) {


        var av = agi.audit_verdict;


        var avc = av.verdict_color || '#16a34a';


        h += ' <span style="font-size:10px;color:' + avc + ';border:1px solid ' + avc + ';border-radius:3px;padding:0 4px">审核:' + (av.verdict||'成立') + '</span>';


      }


    }


    if (mergeCount > 1) h += '（' + mergeCount + '项同类风险合并）';


    h += '</span>' +


      '' +


      '</p>';


    


    // ── 跨域协商标记（无按钮）──


    if (f._negotiated_drop) {


      h += '<p style="text-indent:2em;margin:8px 0;text-align:justify">⛔ 跨域协商已消解：' + (f._drop_reason || f._negotiation_reason || '') + '</p>';


    } else if (f._negotiated) {


      h += '<p style="text-indent:2em;margin:8px 0;text-align:justify">🔄 跨域协商已调整：' + (f._negotiation_reason || '') + '</p>';


    } else if (f._tags && f._tags.length > 0) {


      var tagLabels = f._tags.join(' · ');


      h += '<p style="text-indent:2em;margin:8px 0;text-align:justify">🏷️ 跨域协商标记：' + tagLabels + '</p>';


    } else if (f._dismissed) {


      h += '<p style="text-indent:2em;margin:8px 0;text-align:justify">✅ 已审核：' + (f._correction_reason || '用户反馈已记录') + '</p>';


    }


    


    // ── 合并子项（无按钮）──


    if (f._mergedItems && f._mergedItems.length > 1) {


      h += '<p style="text-indent:2em;margin:8px 0;text-align:justify">该类风险共发现' + f._mergedItems.length + '项具体问题，逐一列示如下：</p>';


      f._mergedItems.forEach(function(sub, si) {


        h += '<p style="text-indent:2em;margin:8px 0;text-align:justify"><strong>子项' + (si+1) + '：' + (sub.title || '') + '</strong> [' + (sub.level || '') + '] —— ' + (sub.detail || '') + '</p>';


        if (sub.tax_impact && sub.tax_impact.length > 10) {


          h += '<p style="text-indent:2em;margin:8px 0;text-align:justify">⚠ 纳税影响：' + sub.tax_impact + '</p>';


        }


        if (sub.suggestion && sub.suggestion.length > 10) {


          h += '<p style="text-indent:2em;margin:8px 0;text-align:justify">→ 建议：' + sub.suggestion + '</p>';


        }


      });


    }


    


    // ── 纠正标记（自动应用/人工审核）──
    if (f._dismissed || f._auto_corrected || f.correctedBy) {
      h += '<div style="background:#f0fdf4;border:1px solid #22c55e;border-radius:6px;padding:8px 14px;margin:8px 0;font-size:13px">';
      h += '<span style="color:#166534;font-weight:600">✅ 已纠正</span>';
      h += '<span style="color:#64748b;margin-left:8px;font-size:12px">' + (f.correctedBy || '系统自学习') + '</span>';
      if (f.correctionReason) h += '<div style="color:#475569;font-size:12px;margin-top:4px">理由：' + f.correctionReason + '</div>';
      h += '</div>';
    }

    // ── 六要素（无按钮，用内联样式保持缩进）──


    var provenance = f.provenance || {};


    h += '<p style="text-indent:2em;margin:8px 0;text-align:justify"><strong>① 问题说明：</strong>' + finType + '</p>';


    h += '<p style="text-indent:2em;margin:8px 0;text-align:justify"><strong>② 具体情况：</strong>' + (f.description || f.detail || '') + '</p>';


    


    // ③ 相关数据（表格无按钮）


    h += '<p style="text-indent:2em;margin:8px 0;text-align:justify"><strong>③ 相关数据：</strong></p>';


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


      h += '<p style="text-indent:2em;margin:8px 0;text-align:justify">参见税务合规事实部分</p>';


    }


    


    h += '<p style="text-indent:2em;margin:8px 0;text-align:justify"><strong>④ 数据来源：</strong>' + (f.how_found || f.source_chain || (provenance.sources||[]).join('+') || '系统分析引擎自动识别') + '</p>';
    // 证据追溯号
    var evr = f._evidence_ref || {};
    if (evr.trace_id) {
      h += '<p style="text-indent:2em;margin:4px 0;font-size:10px;color:#94a3b8">证据编号: ' + evr.trace_id + ' | 快照: ' + (evr.snapshot_id||'') + '</p>';
    }


    h += '<p style="text-indent:2em;margin:8px 0;text-align:justify"><strong>⑤ 待核依据：</strong>' + (f.policy_ref || '须按事实期间、地区、纳税人身份、交易性质和程序阶段取得官方有效依据并完成人工复核') + '</p>';


    if (f.suggestion && f.suggestion.length > 5) {


      h += '<p style="text-indent:2em;margin:8px 0;text-align:justify"><strong>⑥ 建议：</strong>' + f.suggestion + '</p>';


    } else {


      h += '<p style="text-indent:2em;margin:8px 0;text-align:justify"><strong>⑥ 建议：</strong>建议进一步核实相关资料。</p>';


    }


    


    // 发现间分隔线


    if (fi < allSorted.length - 1) {


      h += '<hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0">';


    }


  }
  }


  // ═══ 第四章：税务合规结论 ═══


  h += '<h2 id="ch4">第四章 总体结论</h2>';


  


  // ── 推理引擎综合结论卡片 ──

  if (reportCards.length > 0) {
    var qgateSummary = r._quality_gate || {};
    var methodSummary = r._methodology_applied || {};
    h += '<div style="margin:0 0 18px;padding:18px;background:#eff6ff;border:1px solid #93c5fd;border-radius:10px">';
    h += '<p class="i2" style="margin:0 0 8px"><strong>报告状态：</strong>' + (r.release_status||'草稿_待人工复核') + '</p>';
    h += '<p class="i2"><strong>本轮结论：</strong>系统在已上传资料范围内形成' + reportCards.length + '项待核风险卡。优先级只用于安排核验顺序；资料缺失、模型评分和行业对标不得单独作为违法事实。</p>';
    h += '<p class="i2"><strong>方法论门禁：</strong>' + (methodSummary.portfolio_acceptance_status||'待核验') + '；失败场景' + (methodSummary.portfolio_failed_scenes||0) + '个。<strong>内部草稿门禁：</strong>' + (qgateSummary.draft_gate_passed?'通过':'未通过') + '。<strong>正式发布：</strong>' + (qgateSummary.formal_release_eligible?'可发布':'不可发布/待独立复核') + '。</p>';
    if ((qgateSummary.formal_release_blockers||[]).length) {
      h += '<p class="i2" style="color:#b91c1c"><strong>正式发布待办：</strong>' + (qgateSummary.formal_release_blockers||[]).map(function(item){return item.message||item.code||'';}).join('；') + '</p>';
    }
    h += '<p class="i2"><strong>下一步：</strong>按第五章任务补充真实资料、完成差异复算和反证核验后，发起第' + (reportRecheck.next_round||'下一') + '轮全量合规核验。本轮指引不承诺风险必然消除。</p>';
    h += '</div>';
  } else {

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


    h += '<span style="font-size:18px;font-weight:700;color:#1e293b">综合税务合规结论</span>';


    h += '<span style="display:inline-block;padding:4px 16px;background:' + riskColor + ';color:#fff;border-radius:6px;font-size:14px;font-weight:700">' + (synthFinding.level || '?') + '</span>';


    h += '<span style="font-size:13px;color:#64748b">综合评分 ' + (synthFinding.score || '?') + '/100</span>';


    h += '</div>';


    h += '<div style="font-size:14px;color:#334155;line-height:2">' + (synthFinding.description || '').replace(/</g,'&lt;').replace(/>/g,'&gt;') + '</div>';


    h += '</div>';


  }


  


  // 风险等级


  var synth = r.comprehensive || {};


  var overall = synth.overall_risk || (allF.length > 0 && risks.length > (mids.length + lows.length) ? '高风险' : '中风险');


  // conclusion-box wrapper removed


  h += '<p class="i2"><strong>风险等级：</strong><span class="' + (overall==='高风险'||overall==='极高风险'?'rtag':'atag') + '" style="font-size:18px">' + overall + '</span></p>';


  


  // 风险分布


  h += '<p class="i2">经对被审查企业「' + (te.name || te.company_name || '') + '」（信用代码：' + (te.uscc || '') + '）提交的' + (r.files_count || 0) + '份经营资料进行全面税务审查，共发现<strong>' + allF.length + '</strong>项涉税风险事项，按风险等级分布如下：</p>';


  h += '<table class="tbl" style="margin:12px 0"><thead><tr><th>风险等级</th><th>数量</th><th>占比</th><th>代表事项</th></tr></thead><tbody>';


  h += '<tr><td style="color:#dc2626;font-weight:700">极高风险</td><td>' + (allF.filter(function(f){return f.level==='极高风险';}).length) + '项</td><td>' + (allF.length>0 ? (allF.filter(function(f){return f.level==='极高风险';}).length/allF.length*100).toFixed(1) : 0) + '%</td><td>涉及虚开信号、隐匿收入等红线问题</td></tr>';


  h += '<tr><td style="color:#dc2626;font-weight:600">高风险</td><td>' + risks.length + '项</td><td>' + (allF.length>0 ? (risks.length/allF.length*100).toFixed(1) : 0) + '%</td><td>' + (risks.map(function(f){return (f.type||'');}).join('、') || '资料完备度、资金偏差等') + '</td></tr>';


  h += '<tr><td style="color:#e67700;font-weight:600">中风险</td><td>' + mids.length + '项</td><td>' + (allF.length>0 ? (mids.length/allF.length*100).toFixed(1) : 0) + '%</td><td>发票合规、社保基数偏差、供应商集中等</td></tr>';


  h += '<tr><td style="color:#16a34a;font-weight:600">低风险</td><td>' + lows.length + '项</td><td>' + (allF.length>0 ? (lows.length/allF.length*100).toFixed(1) : 0) + '%</td><td>税收优惠提醒、资料规范建议等</td></tr>';


  h += '</tbody></table>';


  


  // 证据链完整性


  h += '<p class="i2"><strong>证据链状态：</strong>本轮仅在已上传且可解析的资料范围内形成待核事实和资料缺口。证据编号用于内部溯源，不代表真实性、合法性、关联性或来源独立性已经完成复核；单一来源、资料缺失和反向解释均须在后续任务中逐项处理。</p>';


  


  // 税务合规局限性声明


  h += '<p class="i2"><strong>税务合规局限性声明：</strong>本次分析基于被审查企业提交的' + (r.files_count || 0) + '份资料。根据14类税务合规必查资料清单，尚有部分资料未提交（如记账凭证、合同文件、申报表等）。对于资料缺失的分析域，本次税务合规已在对应发现中标注资料缺口，并说明缺失资料对税务合规判断的影响。被审查企业补充提交相关资料后，税务合规结论可能需要相应调整。</p>';


  


  // 总体结论


  h += '<p class="i2"><strong>总体结论：</strong>';


  if (overall === '高风险' || overall === '极高风险') {


    h += '本轮存在需要优先核验的观察差异。应按每项风险卡锁定主体、事项、期间和业务主键，补充真实资料并同时检验正常商业解释；在证据、政策、金额底稿和人工复核完成前，不得写成违法定性或确定税额。';


  } else if (overall === '中风险') {


    h += '本轮形成若干待核事项，须结合真实业务、原始资料和业务期间有效政策逐项复核。风险数量和等级仅用于排序，不自动影响纳税信用，也不代表违法事实。';


  } else {


    h += '本轮已上传资料中未形成高优先级观察信号，但不能据此证明全部期间和全部事项完全合规；仍应核对资料覆盖范围、未上传资料及政策适用条件。';


  }


  h += '</p>';
  }


  // ═══ 第五章：处理处罚建议 ═══


    var qg = r._quality_gate || {};

  h += '<h2 id="ch4b">附：内部草稿质量自检与正式发布边界</h2>';
  h += '<div class="wide-table"><table><thead><tr><th>验收项</th><th>评价口径</th><th>当前</th><th>状态</th></tr></thead><tbody>';
  var metricDetails = qg.metric_details || [];
  if (metricDetails.length) {
    metricDetails.forEach(function(metric){
      var current = metric.rate === null || typeof metric.rate === 'undefined' ? '不适用' : metric.rate + '% (' + (metric.numerator||0) + '/' + (metric.denominator||0) + ')';
      var label = metric.status === 'passed' ? '<span style="color:#166534">通过</span>' : (metric.status === 'not_applicable' ? '<span style="color:#64748b">不适用</span>' : '<span style="color:#dc2626">待完成</span>');
      h += '<tr><td>' + (metric.label||metric.code||'') + '</td><td>' + (metric.reason||'逐项核验') + '</td><td>' + current + '</td><td>' + label + '</td></tr>';
    });
  } else {
    h += '<tr><td colspan="4">尚未生成可核验的质量指标；不得显示为100%通过。</td></tr>';
  }
  h += '</tbody></table></div>';
  h += '<p class="i2" style="background:#fef2f2;padding:10px;border-radius:6px;font-size:13px"><strong>发布边界：</strong>本表仅评价内部草稿质量。正式发布状态：' + (qg.formal_release_eligible?'可发布':'不可发布') + '。在证据、法规时效、金额底稿、人员分离和受控发布全部完成前，不得作为正式对外结论、补税金额或违法定性使用。</p>';
h += '<h2 id="ch5">第五章 合规改进与复查任务</h2>';


  h += '<p class="i2">以下内容是查清事实、修正真实差错和改进内部控制的操作指引，不保证执行后风险必然消除，也不得用于倒签、补造、删除或覆盖历史资料。</p>';

  if (reportTasks.length > 0) {
    for (var rti=0; rti<reportTasks.length; rti++) {
      var task = reportTasks[rti] || {};
      h += '<div style="border-left:4px solid #2563eb;background:#f8fafc;padding:12px 14px;margin:10px 0">';
      h += '<p class="i2" style="margin:0 0 6px"><strong>【任务' + (rti+1) + '】' + (task.task_id||'') + ' / 风险卡 ' + (task.risk_id||'') + '</strong></p>';
      h += '<p class="i2"><strong>目标：</strong>' + (task.objective||'') + '</p>';
      h += '<p class="i2"><strong>执行步骤：</strong></p><ol style="margin:4px 0 8px 32px">';
      (task.actions||[]).forEach(function(item){ h += '<li>' + item + '</li>'; });
      h += '</ol>';
      h += '<p class="i2"><strong>应补资料：</strong>' + ((task.required_documents||[]).join('、')||'按风险卡逐项确认') + '</p>';
      h += '<p class="i2"><strong>完成标准：</strong>' + ((task.completion_criteria||[]).join('；')||'待人工确定') + '</p>';
      h += '<p class="i2"><strong>回传证据：</strong>' + ((task.evidence_to_return||[]).join('、')||'待确定') + '</p>';
      h += '<p class="i2" style="color:#b91c1c"><strong>禁止：</strong>' + ((task.forbidden_actions||[]).join('；')||'禁止倒签补造和无依据调账') + '</p>';
      h += '<p class="i2"><strong>责任人与期限：</strong>' + (task.owner||'待指定') + '；' + (task.due_date||'待结合实际期限确定') + '</p>';
      h += '</div>';
    }
    h += '<h3>下一轮复查</h3>';
    h += '<p class="i2">本轮为第' + (reportRecheck.current_round||1) + '轮，补充资料并完成真实整改后发起第' + (reportRecheck.next_round||2) + '轮全量合规核验。必须重跑：' + ((reportRecheck.must_rerun||[]).join('、')||'全部适用场景') + '。</p>';
    h += '<p class="i2"><strong>趋于合规判断：</strong>' + (reportRecheck.convergence_rule||'以风险状态、资料缺口和控制缺陷持续减少且证据质量提高为准，不以分数下降单独判定。') + '</p>';
  } else {


  


  // P0：立即处理


  h += '<h3>一、P0 —— 立即处理（涉及逃税、虚开等红线问题）</h3>';


  var p0Count = 0;


  for (var fi = 0; fi < allSorted.length; fi++) {


    var sf = allSorted[fi];


    if ((sf.level === '极高风险' || sf.level === '高风险') && sf.suggestion && sf.suggestion.length > 10) {


      p0Count++;


      h += '<p class=\"i2\">' + p0Count + '. ' + sf.suggestion + '</p>';


      if (p0Count >= 5) break;


    }


  }


  if (p0Count === 0) h += '<p class="i2">暂无需要立即处理的P0级事项。</p>';


  


  // P1：限期整改


  h += '<h3>二、P1 —— 限期整改（发票合规、账务调整等问题）</h3>';


  var p1Count = 0;


  for (var fi = 0; fi < allSorted.length; fi++) {


    var sf = allSorted[fi];


    if (sf.level === '中风险' && sf.suggestion && sf.suggestion.length > 10) {


      p1Count++;


      h += '<p class=\"i2\">' + p1Count + '. ' + sf.suggestion + '</p>';


      if (p1Count >= 5) break;


    }


  }


  if (p1Count === 0) h += '<p class="i2">暂无需要限期整改的P1级事项。</p>';


  


  // P2：持续关注


  h += '<h3>三、P2 —— 持续关注（资料完善、合规提醒、优惠政策享受建议）</h3>';


  var p2Count = 0;


  for (var fi = 0; fi < allSorted.length; fi++) {


    var sf = allSorted[fi];


    if ((sf.level === '低风险' || sf.level === '优惠机会') && sf.suggestion && sf.suggestion.length > 10) {


      p2Count++;


      h += '<p class=\"i2\">' + p2Count + '. ' + sf.suggestion + '</p>';


      if (p2Count >= 5) break;


    }


  }


  if (p2Count === 0) h += '<p class="i2">暂无需要持续关注的P2级事项。</p>';


  


  // 整改期限


  h += '<h3>四、整改期限</h3>';


  h += '<p class="i2">1. <strong>高优先级事项：</strong>企业应结合申报期限、法定程序期限和事项重要性确定内部完成时间；资料未补齐时保留为未决事项，系统不得依据现有数据直接作出处理决定。</p>';


  h += '<p class="i2">2. <strong>一般待核事项：</strong>按事实和有效依据决定是否更正账务、申报或内部流程；无事实依据时不得为了降低系统分数而调整。</p>';


  h += '<p class="i2">3. <strong>持续改进事项：</strong>完成资料、底稿和内部控制改进后上传完成证据，发起新一轮全量分析并保留轮次比较。</p>';


  h += '<p class="i2">4. 被审查企业如对以上发现的事实有异议，可依据第六章规定的陈述申辩权和听证权，在法定期限内提出。</p>';
  }


  // ═══ 第六章：告知权利义务 ═══


  h += '<h2 id="ch6">第六章 您的权利</h2>';


  h += '<p class="i2">被分析企业「' + (te.name || te.company_name || '') + '」依法享有知情、保密、陈述申辩、申请回避、救济等权利。具体权利、条件和期限应以现行法律规范及有权机关依法送达的文书为准；本系统仅提供线索核验辅助：</p>';

  h += '<h3>一、知情权</h3>';
  h += '<p class="i2">有权了解审查的法律依据、审查范围、审查期间以及审查人员的身份信息。</p>';
  h += '<p class="i1" style="font-size:12px;color:#64748b">涉及法规：《税收征收管理法》第八条、《纳税人权利与义务公告》</p>';

  h += '<h3>二、保密权</h3>';
  h += '<p class="i2">审查中知悉的商业秘密和个人隐私受法律保护。</p>';
  h += '<p class="i1" style="font-size:12px;color:#64748b">涉及法规：《税收征收管理法》第八条</p>';

  h += '<h3>三、委托代理权</h3>';
  h += '<p class="i2">有权委托税务师、律师或其他代理人代为办理涉税事宜。</p>';
  h += '<p class="i1" style="font-size:12px;color:#64748b">涉及法规：《税收征收管理法》第五十七条</p>';



  


  h += '<h3>四、申请回避权</h3>';


  h += '<p class="i2">被审查企业认为税务合规人员与本案有利害关系或其他关系可能影响公正执法的，有权申请该税务合规人员回避。申请回避应当在税务合规人员送达《税务检查通知书》后<strong>3日内</strong>，以书面形式向税务合规部门提出，说明申请回避的理由。税务合规部门应当在收到申请后3日内作出决定并告知申请人。</p>';


  h += '<p class="i1" style="font-size:12px;color:#64748b">涉及法规：《税收征收管理法》第十二条</p>';


  


  h += '<h3>五、陈述申辩权</h3>';


  h += '<p class="i2">企业有权对系统风险卡中的事实、依据、数据口径和指引提出说明并上传反向证据。涉及正式行政程序时，陈述申辩方式和期限以有权机关依法送达的文书及现行规定为准，系统不得自行设定法定期限。</p>';


  h += '<p class="i1" style="font-size:12px;color:#64748b">涉及法规：《中华人民共和国行政处罚法》第三十二条</p>';


  


  h += '<h3>六、要求听证权</h3>';


  h += '<p class="i2">本系统不作行政处罚或听证决定。如企业收到有权机关送达的行政处罚告知文书，应按该文书和现行法律核验是否享有听证权、申请方式和期限，并及时交由有权人员处理。</p>';


  h += '<p class="i1" style="font-size:12px;color:#64748b">具体适用依据、标准和期限须按实际送达文书及当时有效规定核验。</p>';


  


  h += '<h3>七、申请行政复议权</h3>';


  h += '<p class="i2">本系统报告不是税务处理决定。企业如收到正式税务文书，应按文书载明的权利、期限和受理机关，结合现行法律判断是否申请行政复议，并及时取得专业意见。</p>';


  h += '<p class="i1" style="font-size:12px;color:#64748b">行政复议规则须结合文书类型、前置条件和最新有效法律逐案核验。</p>';


  


  h += '<h3>八、提起行政诉讼权</h3>';


  h += '<p class="i2">本系统不判断行政诉讼条件或期限。企业如收到税务处理、处罚或复议文书，应以实际文书和现行法律为准核验起诉条件、期限及管辖。</p>';


  h += '<p class="i1" style="font-size:12px;color:#64748b">建议对正式文书单独进行程序与救济期限核验。</p>';


  


  // ═══ 第七章：税务合规人员签字 ═══


  h += '<h2 id="ch7">第七章 签字页</h2>';
  h += '<p class="i2" style="background:#fef3c7;padding:10px;border-radius:6px;font-size:12px"><strong>角色分离提醒：</strong>本系统为企业内部辅助分析工具。风险卡编制、税务复核和报告批准应由不同授权角色完成；系统分析不得冒充税务机关检查、审理或执行。</p>';


  h += '<div class="seal" style="margin-top:40px;padding:24px 0;line-height:3">';


  h += '<p>内部报告编制人：_______________　　日期：_______________</p>';


  h += '<p>税 务 复 核 人：_______________　　日期：_______________</p>';


  h += '<p>企业内部批准人/授权标识（如适用）：_______________</p>';


  h += '<p style="margin-top:20px">报告日期：' + dateStr + '</p>';


  h += '<p style="margin-top:12px;font-size:12px;color:#94a3b8">本报告为企业风险防控系统生成的内部辅助分析草稿。是否形成正式文书、份数、送达和归档方式，由有权主体依适用制度另行确定。</p>';


  h += '</div>';


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


  h += '<div class="aitem">· 银行流水' + ((r.bank_stats && r.bank_stats.count) || bi['笔数'] || 0) + '条</div>';


  h += '<div class="aitem">· 累计收款' + (_amountNumber(bi['总收款'])/10000).toFixed(2) + '万元 · 累计付款' + (_amountNumber(bi['总付款'])/10000).toFixed(2) + '万元</div>';


  h += '</div>';


  


  h += '<div class="appendix"><div class="atitle">附件六：其他经营资料</div>';


  if (r.file_results && r.file_results.length) {


    r.file_results.forEach(function(fr, fi) {


      var receipt = fr.parse_receipt || {};
      var qualityText = {usable:'可用解析',partial:'部分解析',blocked:'解析阻断'}[receipt.quality_status] || '待核验';
      var fileName = typeof fr.file === 'string' ? fr.file : ((fr.file || {}).original_name || '');
      var subject = receipt.invoice_subject_assessment || {};
      h += '<div class="aitem">' + (fi+1) + '. ' + fileName + ' (' + (fr.type || '未知') + ') · ' + qualityText +
        (receipt.confidence == null ? '' : ' · 置信度' + receipt.confidence + '%') +
        (receipt.receipt_hash ? ' · 回执' + receipt.receipt_hash.slice(0,12) + '…' : '') +
        (receipt.safe_for_automatic_calculation ? ' · 可进入自动计算候选' : ' · 不得直接用于金额定稿') +
        (receipt.extraction_method === 'ocr' ? ' · 字段候选' + ((receipt.field_review_candidates || []).length || 0) + '项/已复核套用' + (((receipt.field_review_summary || {}).approved_applied) || 0) + '项' : '') +
        (subject.state ? '<br>发票主体：' + (subject.state_label || subject.state) + ' · 方向' + (subject.direction || '存疑') + ' · 逐票' + (subject.verified_unit_count || 0) + '/' + (subject.unit_count || 0) + '通过' + (subject.blocked_unit_count ? '、阻断' + subject.blocked_unit_count + '张/组' : '') + ' · ' + (subject.basis || '') + ((subject.units || []).length ? '<br>' + subject.units.map(function(unit){return (unit.unit_ref || unit.unit_id || '发票单元') + (unit.invoice_no ? '/票号' + unit.invoice_no : '') + '：' + (unit.state_label || unit.state || '待核验') + '，方向' + (unit.direction || '存疑');}).join('；') : '') : '') + '</div>';


    });


  }


  h += '</div>';

  if (r.document_evidence_index && r.document_evidence_index.length) {
    h += '<div class="appendix"><div class="atitle">附件七：文档证据定位与字段映射索引</div>';
    r.document_evidence_index.forEach(function(item, index) {
      var mapped = Object.keys(item.mapped_fields || {});
      var suggested = (item.suggested_document_types || []).map(function(row){return (row.label || row.type || '待确认') + (row.confidence == null ? '' : '(' + row.confidence + '%)');});
      var subject = item.invoice_subject_assessment || {};
      h += '<div class="aitem">' + (index + 1) + '. ' + (item.source_name || '') + ' · ' + (item.quality_status || '待核验') + ' · 定位覆盖' + (item.source_locator_coverage || 0) + '% · ' + ((item.locator_kinds || []).join('、') || '无精确定位') + '<br>映射字段：' + (mapped.join('、') || '无') + (suggested.length ? ' · 资料类型建议：' + suggested.join('；') + '（待人工确认）' : '') + (subject.state ? '<br>主体归属：' + (subject.state_label || subject.state) + ' · 方向' + (subject.direction || '存疑') + ' · 逐票' + (subject.verified_unit_count || 0) + '/' + (subject.unit_count || 0) + '通过 · ' + (subject.basis || '') : '') + ' · 回执' + ((item.receipt_hash || '').slice(0,12) || '-') + '…</div>';
    });
    h += '<div class="aitem">边界：资料类型建议不得自动替代主体方向、业务性质、政策适用和证据三性审查。</div></div>';
  }


  


  if (r.quality_check) {


    h += '<div class="appendix"><div class="atitle">附件八：质量标准自检</div>';


    var qc = r.quality_check;


    h += '<div class="aitem">通过：' + (qc.passed || 0) + '/' + (qc.total || 12) + '项 (' + (qc.pass_rate || 0) + '%)</div>';


    h += '</div>';


  }


  h += '</div>';


  return { html: h, renderedModules: ['cover','ch1-entity','ch2-methods','ch3-findings','ch4-funds','ch5-synthesis','ch6-conclusion','ch7-appendix'], skippedModules: [] };


}


// ═══════════════════════════════════════════════════════════


// 报告正文段落右侧注入编辑/审核/交互/重置按钮


// ═══════════════════════════════════════════════════════════


// 覆盖第一章至第七章全部正文段落（<p class="i2">标签）


// 段落级操作函数 — 连接到纠正规则引擎


// 弹窗样式对齐纠正规则库的编辑弹窗（_editFindingInReport）


window._submitParaEdit = function(i) {


  var text = document.getElementById('finding-edit-text');


  var content = (text ? text.value.trim() : '');


  if (!content) { toast('请填写内容', 'warning'); return; }


  


  var p = document.getElementById('finding-edit-popup');


  if (p) p.remove();


  


  var paraContent = _getParagraphContent(i) || '';


  var rpt = window._reportData || {};


  var te = rpt.target_entity || {};


  


  fetch('/api/feedback', {


    method: 'POST',


    headers: {'Content-Type': 'application/json'},


    body: JSON.stringify({


      company_id: window.currentCompanyId || 1,


      industry: te.industry || '',


      biz_model: te.company_type || '',


      finding_type: 'Paragraph#' + i,


      original_level: '',


      corrected_risk: '低风险（用户纠正）',


      reason: content,


      detail: paraContent.slice(0, 500),


      action: 'edit_paragraph',


      timestamp: new Date().toISOString()


    })


  }).then(function(r){ return r.json(); }).then(function(data){


    if (data.ok) {


      toast(data.auto_rule ? '已记录；该规则已通过受控同步' : '已保存为候选规则，待重复验证和人工批准', 'success');


    } else {


      toast('提交失败: ' + (data.error || '未知错误'), 'error');


    }


  }).catch(function(e){


    toast('网络错误，请稍后重试', 'error');


  });


};


window._sendParaChat = function(i) {


  var inp = document.getElementById('ask-chat-input-para');


  var q = inp ? inp.value.trim() : '';


  if (!q) return;


  


  var body = document.getElementById('ask-chat-body-para');


  if (!body) return;


  


  body.innerHTML += '<div style="margin-bottom:8px"><span style="background:#7c3aed;color:#fff;padding:4px 10px;border-radius:8px;font-size:11px">You: ' + q + '</span></div>';


  body.innerHTML += '<div style="font-size:12px;color:#94a3b8">Thinking...</div>';


  body.scrollTop = body.scrollHeight;


  


  if (inp) inp.value = '';


  


  var companyId = window.currentCompanyId || 1;


  var paraContent = _getParagraphContent(i) || '';


  fetch('/api/tax-risk-docs/ask?company_id=' + companyId, {


    method: 'POST',


    headers: {'Content-Type': 'application/json'},


    body: JSON.stringify({finding_index:-1, paragraph_text: paraContent, question: q, policy_doc:'', history:[]})


  }).then(function(r){return r.json();}).then(function(data){


    var html = '<div style="margin-top:8px;font-size:12px;color:#475569">';


    if (data.ok && data.analysis) {


      data.analysis.forEach(function(b){ html += '<div style="margin:4px 0;font-weight:600">' + (b.title||'') + '</div><div style="font-size:11px">' + (b.content||'').slice(0,300) + '</div>'; });


    } else {


      html += '错误: ' + (data.message||'');


    }


    html += '</div>';


    body.innerHTML += html;


    body.scrollTop = body.scrollHeight;


  }).catch(function(e){


    body.innerHTML += '<div style="color:#dc2626;font-size:12px">错误: ' + e.message + '</div>';


  });


};


function _getParagraphContent(i) {


  // btn → .rpt-btn-bar → flex wrapper → firstChild(内容div) → p.i2


  var btn = document.querySelector('button[data-pi="' + i + '"]');


  if (!btn) return '';


  var bar = btn.closest('.rpt-btn-bar');


  if (!bar) return '';


  var wrapper = bar.parentElement;


  if (!wrapper) return '';


  var para = wrapper.querySelector('p.i2');


  if (!para) return '';


  var clone = para.cloneNode(true);


  var btns = clone.querySelectorAll('.rpt-btn-bar');


  btns.forEach(function(b) { b.remove(); });


  return clone.textContent || clone.innerText || '';


}


function _getParagraphHTML(i) {


  var btn = document.querySelector('button[data-pi="' + i + '"]');


  if (!btn) return '';


  var bar = btn.closest('.rpt-btn-bar');


  if (!bar) return '';


  var wrapper = bar.parentElement;


  if (!wrapper) return '';


  var para = wrapper.querySelector('p.i2');


  if (!para) return '';


  var clone = para.cloneNode(true);


  var btns = clone.querySelectorAll('.rpt-btn-bar');


  btns.forEach(function(b) { b.remove(); });


  return clone.innerHTML;


}


// ==================== 导出报告 ====================


async function exportTaxDocReport() {

  var report = window._reportData || taxDocReportData || {};
  var round = report.compliance_round || {};
  var roundId = round.round_id || '';
  if (!roundId) {
    toast('当前报告尚未形成受控分析轮次，请重新执行一键分析', 'warning');
    return;
  }
  try {
    var cid = _tdaCid();
    var detailResp = await fetch('/api/compliance/rounds/' + encodeURIComponent(roundId) + '?company_id=' + encodeURIComponent(cid));
    var detail = await _safeJson(detailResp, '报告发布状态');
    if (!detailResp.ok || !detail.ok) throw new Error(detail.detail || detail.message || '无法读取报告发布状态');
    var isOfficial = (detail.round || {}).status === 'published';
    var recipient = '', purpose = '';
    if (isOfficial) {
      recipient = prompt('请输入正式报告接收对象（企业、部门或人员）：', (report.target_entity || {}).name || '本企业管理层');
      if (recipient === null || !String(recipient).trim()) return;
      purpose = prompt('请输入本次正式交付用途：', '企业内部税务合规决策');
      if (purpose === null || !String(purpose).trim()) return;
    }
    var response = await fetch('/api/compliance/rounds/' + encodeURIComponent(roundId) + '/deliver?company_id=' + encodeURIComponent(cid), {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        delivery_type: isOfficial ? 'official' : 'draft',
        format: 'html',
        recipient: recipient,
        purpose: purpose
      })
    });
    if (!response.ok) {
      var error = await response.json().catch(function(){return {detail:'报告交付失败'};});
      throw new Error(error.detail || error.message || '报告交付失败');
    }
    var blob = await response.blob();
    var disposition = response.headers.get('Content-Disposition') || '';
    var match = disposition.match(/filename="?([^";]+)"?/i);
    var filename = match ? match[1] : (isOfficial ? 'tax-compliance-official.html' : 'tax-compliance-draft.html');
    var downloadUrl = URL.createObjectURL(blob);
    var link = document.createElement('a');
    link.href = downloadUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(function(){ URL.revokeObjectURL(downloadUrl); }, 1000);
    var exportBtn = document.getElementById('tda-export-btn');
    if (exportBtn) exportBtn.textContent = isOfficial ? '下载正式报告' : '导出内部草稿';
    toast(isOfficial ? '正式报告已交付，并记录接收对象和文件指纹' : '带水印内部草稿已导出', 'success');
    return;
  } catch (error) {
    toast(error.message || '报告交付失败', 'error');
  }
}


function deleteTaxDocReport() {
  if (!confirm('确定要删除当前报告吗？此操作会同时清除后端缓存。')) return;
  var area = document.getElementById('tda-report-area');
  taxDocReportData = null;
  if (area) area.innerHTML = '';
  fetch('/api/tax-risk-docs/report?company_id=' + _tdaCid(), { method: 'DELETE' })
    .then(function(r){ return r.json(); })
    .then(function(d){ toast(d && d.message ? d.message : '报告已删除', 'success'); })
    .catch(function(){ toast('报告已删除', 'success'); });
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


  var area = document.getElementById('tda-report-area');


  if (!area) return;


  


  var oldBar = document.getElementById('tts-bar');


  if (oldBar) oldBar.remove();


  


  var bar = document.createElement('div');


  bar.id = 'tts-bar';


  bar.innerHTML = 


    '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">' +


    '<span style="font-size:13px;font-weight:700;color:#1a1a2e">🔊 税务合规报告语音播报</span>' +


    '<button id="tts-play-all" style="padding:6px 16px;background:#2563eb;color:#fff;border:none;border-radius:6px;font-size:13px;cursor:pointer;font-weight:600">▶ 全文播报</button>' +


    '<button id="tts-pause" style="padding:6px 16px;background:#fff;border:1px solid #d1d5db;border-radius:6px;font-size:13px;cursor:pointer;display:none">⏸ 暂停</button>' +


    '<button id="tts-stop" style="padding:6px 16px;background:#fff;border:1px solid #dc2626;color:#dc2626;border-radius:6px;font-size:13px;cursor:pointer;display:none">⏹ 停止</button>' +


    '<select id="tts-speed" style="padding:6px 10px;border:1px solid #d1d5db;border-radius:6px;font-size:13px;background:#fff;cursor:pointer">' +


    '<option value="0.85">0.85x 新闻联播</option><option value="1.0" selected>1.0x 标准</option><option value="1.15">1.15x 略快</option><option value="1.3">1.3x 快速</option>' +


    '</select>' +


    '<span id="tts-progress" style="font-size:12px;color:#94a3b8"></span>' +


    '</div>' +


    '<div style="font-size:11px;color:#94a3b8;margin-top:4px">💡 点击报告任意段落可从此处开始播报至报告结束 · 播音标准：新闻联播级专业播报 · 橙色底纹=正在播报的段落</div>';


  bar.style.cssText = 'position:fixed;bottom:20px;right:20px;z-index:9999;min-width:380px;max-width:920px;padding:12px 18px;background:rgba(255,255,255,0.96);border:1px solid #cbd5e1;border-radius:12px;box-shadow:0 4px 24px rgba(0,0,0,0.15);backdrop-filter:blur(10px);cursor:grab';


  bar.setAttribute('data-draggable', 'true');


  document.body.appendChild(bar);


  


  // ── 拖拽移动 ──


  var dragHandle = bar.querySelector('div:first-child');


  if (dragHandle) dragHandle.style.cursor = 'grab';


  var dragging = false, dragX = 0, dragY = 0, startLeft = 0, startTop = 0;


  


  bar.addEventListener('mousedown', function(e) {


    if (e.target.tagName === 'BUTTON' || e.target.tagName === 'SELECT' || e.target.tagName === 'OPTION') return;


    dragging = true;


    bar.style.cursor = 'grabbing';


    bar.style.transition = 'none';


    dragX = e.clientX; dragY = e.clientY;


    var rect = bar.getBoundingClientRect();


    startLeft = rect.left; startTop = rect.top;


    e.preventDefault();


  });


  


  document.addEventListener('mousemove', function(e) {


    if (!dragging) return;


    var dx = e.clientX - dragX, dy = e.clientY - dragY;


    bar.style.left = (startLeft + dx) + 'px';


    bar.style.top = (startTop + dy) + 'px';


    bar.style.right = 'auto'; bar.style.bottom = 'auto';


    bar.style.transform = 'none';


  });


  


  document.addEventListener('mouseup', function() {


    if (dragging) { dragging = false; bar.style.cursor = 'grab'; }


  });


  


  // 触摸支持


  bar.addEventListener('touchstart', function(e) {


    if (e.target.tagName === 'BUTTON' || e.target.tagName === 'SELECT' || e.target.tagName === 'OPTION') return;


    if (e.touches.length !== 1) return;


    dragging = true; bar.style.cursor = 'grabbing'; bar.style.transition = 'none';


    dragX = e.touches[0].clientX; dragY = e.touches[0].clientY;


    var rect = bar.getBoundingClientRect();


    startLeft = rect.left; startTop = rect.top;


  }, {passive: false});


  


  document.addEventListener('touchmove', function(e) {


    if (!dragging) return;


    var dx = e.touches[0].clientX - dragX, dy = e.touches[0].clientY - dragY;


    bar.style.left = (startLeft + dx) + 'px';


    bar.style.top = (startTop + dy) + 'px';


    bar.style.right = 'auto'; bar.style.bottom = 'auto';


    bar.style.transform = 'none';


    e.preventDefault();


  }, {passive: false});


  


  document.addEventListener('touchend', function() {


    if (dragging) { dragging = false; bar.style.cursor = 'grab'; }


  });


  


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


  var els = container.querySelectorAll('p, h1, h2, h3, h4, td, th, li, .ftitle, .frow, .flabel, .ritem, .atitle, .aitem, .seal p, .fact-sec, .conclusion-box, .i2, .cover h1, .cover .sub, .tag, .law-ref, .std-label, .rpt-title');


  els.forEach(function(el) {


    if (el.closest('#tts-bar') || el.closest('#review-panel') || el.closest('details') || el.closest('style') || el.closest('.rpt-btn-bar')) return;


    // 克隆元素去除按钮栏，取纯文本


    var clone = el.cloneNode(true);


    var btns = clone.querySelectorAll('.rpt-btn-bar');


    btns.forEach(function(b) { b.remove(); });


    var t = _ttsCleanText((clone.textContent || ''));


    if (t.length > 5) _ttsChunks.push({el: el, text: t});


  });


}


// 文本清洗：去标点符号、修正多音字（全报告覆盖·财税税务合规语境）


function _ttsCleanText(text) {


  var t = text.replace(/\s+/g, ' ').trim();


  // 去除播报不需要的标点符号


  t = t.replace(/[_→●◆■★☆✓✕⚠📌📡🔬📋💡🔗🎯⚖️🧠📚🔊🎙️📝💻📄📁📐📜🛡️⚙️🔍📊🔒⚡📋🔴🟡🟢❌✅]/g, '');


  t = t.replace(/[`*~#>\-\[\](){}|]/g, '');


  t = t.replace(/\s{2,}/g, ' ');


  


  // ═══ 多音字全面修正（财税税务合规语境·词级替换）═══


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


    if (e.target.closest('#tts-bar') || e.target.closest('#review-panel') || e.target.closest('.rpt-btn-bar')) return;


    


    // 找到被点击的文本容器元素


    var el = e.target;


    while (el && el !== container) {


      if (el.tagName === 'P' || el.tagName === 'H1' || el.tagName === 'H2' || el.tagName === 'H3' || el.tagName === 'TD' || el.tagName === 'TH' || el.tagName === 'LI' || el.tagName === 'DIV') {


        // 克隆并去除按钮栏，取纯文本用于匹配


        var clickClone = el.cloneNode(true);


        var clickBtns = clickClone.querySelectorAll('.rpt-btn-bar');


        clickBtns.forEach(function(b) { b.remove(); });


        var text = (clickClone.textContent || '').trim();


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


  var isFinding = text.indexOf('税务合规性质') >= 0 || text.indexOf('发现要点') >= 0;


  var isLaw = text.indexOf('《') >= 0 && text.indexOf('》') >= 0 && text.indexOf('第') >= 0 && text.indexOf('条') >= 0;


  var isSuggestion = text.indexOf('建议') >= 0 || text.indexOf('整改') >= 0;


  


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


    _ttsState.currentChunk.el.style.padding = '';


    _ttsState.currentChunk.el.style.borderRadius = '';


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


  // 清除高亮——包括padding/borderRadius，恢复原样


  if (_ttsState.currentChunk && _ttsState.currentChunk.el) {


    _ttsState.currentChunk.el.style.background = '';


    _ttsState.currentChunk.el.style.transition = '';


    _ttsState.currentChunk.el.style.padding = '';


    _ttsState.currentChunk.el.style.borderRadius = '';


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


// ═══ 纠正规则引擎接口：统一构建完整反馈数据 ═══
