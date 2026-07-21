// ══════════════════════════════════════════════════════════════
//  税务合规管道独立页：文件解析 | 域分析 | 跨域证据链 | 方法论过滤器
// ══════════════════════════════════════════════════════════════

// ═══════════ 模块数量自动加载（从JSON数据文件动态读取，杜绝硬编码过期数字） ═══════════
var _pipelineCounts = null;

async function loadPipelineCounts() {
  if (_pipelineCounts) return _pipelineCounts;
  try {
    var t0 = Date.now();
    var [rulesResp, cdcResp, cdeResp, cdaResp] = await Promise.all([
      fetch('/static/tax_risk_rules_local_export.json?_t=' + t0),
      fetch('/static/cross_domain_clues.json?_t=' + t0),
      fetch('/static/cross_domain_evidence.json?_t=' + t0),
      fetch('/static/cross_domain_analysis.json?_t=' + t0)
    ]);
    var rules = await rulesResp.json();
    var cdc = await cdcResp.json();
    var cde = await cdeResp.json();
    var cda = await cdaResp.json();
    _pipelineCounts = {
      rules: rules.length,
      trailChains: cdc.length,
      evidenceChains: cde.length,
      analysisChains: cda.length,
      totalChains: cdc.length + cde.length + cda.length,
      crossEvidence: cde.length,
      crossClues: cdc.length,
      crossAnalysis: cda.length
    };
    console.log('[pipeline counts] loaded:', _pipelineCounts);
  } catch(e) {
    console.error('[pipeline counts] failed:', e);
    // 从 system_config.json 读取权威值
  }
  // 如果 system_config 已加载，用它覆盖（权威数据源）
  if (window._systemConfig) {
    _pipelineCounts.rules = window._systemConfig.rules_count || _pipelineCounts.rules;
    _pipelineCounts.trailChains = window._systemConfig.clue_chains || _pipelineCounts.trailChains;
    _pipelineCounts.evidenceChains = window._systemConfig.evidence_chains || _pipelineCounts.evidenceChains;
    _pipelineCounts.analysisChains = window._systemConfig.analysis_chains || _pipelineCounts.analysisChains;
    _pipelineCounts.totalChains = window._systemConfig.total_chains || _pipelineCounts.totalChains;
  }
  return _pipelineCounts;
}

// 快捷取值：优先从 _pipelineCounts，回退到 system_config
function pc(key, fallback) {
  if (_pipelineCounts && _pipelineCounts[key] != null) return _pipelineCounts[key];
  if (window._systemConfig) {
    var m = {rules:'rules_count',trailChains:'clue_chains',evidenceChains:'evidence_chains',analysisChains:'analysis_chains',totalChains:'total_chains'};
    if (m[key] && window._systemConfig[m[key]]) return window._systemConfig[m[key]];
  }
  return fallback || '...';
}

// ═══════════ API共享缓存（消除6模块重复请求同一API） ═══════════
var _analysisCacheData = null;
var _analysisCachePromise = null;

function getSharedAnalysis() {
  if (_analysisCacheData) return Promise.resolve(_analysisCacheData);
  if (_analysisCachePromise) return _analysisCachePromise;
  var cid = typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1;
  _analysisCachePromise = fetch('/api/tax-risk-docs/last-analysis?company_id=' + cid)
    .then(function(r) { return r.json(); })
    .then(function(data) {
      _analysisCacheData = data;
      _analysisCachePromise = null;
      return data;
    })
    .catch(function(e) {
      _analysisCachePromise = null;
      throw e;
    });
  return _analysisCachePromise;
}

// ═══════════ 页面1：文件解析（极简风） ═══════════
function renderFileParsingPage(container) {
  if (!container) return;
  window.currentModule = '文件解析';
  container.innerHTML = '<style>.fp-layout{display:flex;gap:24px;max-width:1200px;margin:0 auto;padding:40px 46px;background:#fff}.fp-toc{width:190px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:10px;line-height:20px;max-height:calc(100vh-40px);overflow-y:auto}.fp-toc .toc-title{font-weight:700;color:#16233a;font-size:10px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.fp-toc a{display:block;color:#3a4048;text-decoration:none;padding:2px 8px;border-radius:4px;cursor:pointer}.fp-toc a:hover,.fp-toc a.active{background:#eff6ff;color:#2563eb;font-weight:600}.fp-main{flex:1;min-width:0;background:#fff;line-height:1.6}.fp-main p,.fp-main div,.fp-main li{margin-bottom:10px}.fp-main h3{font-size:10px!important;font-weight:700!important;color:#16233a!important;padding-bottom:8px!important;border-bottom:2px solid #e2e8f0!important;margin:0 0 10px!important}.fp-main .fp-step{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:20px 22px;transition:box-shadow 0.15s}.fp-main .fp-step:hover{box-shadow:0 2px 8px rgba(0,0,0,.06)}.fp-main details summary:hover{background:#f8fafc}.fp-main .fp-card{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:20px 22px;transition:box-shadow 0.15s}.fp-main .fp-card:hover{box-shadow:0 2px 8px rgba(0,0,0,.06)}.fp-main .fp-stat-card{background:#fff;border:1px solid #e2e8f0;border-radius:8px;text-align:center;padding:16px}.fp-main section{margin-bottom:10px!important;scroll-margin-top:20px}</style>'
    + '<div class="fp-layout">'
    + '<nav class="fp-toc"><div class="toc-title">📖 导航</div>'
    + '<a href="#fp-mechanism">一 识别机制</a>'
    + '<a href="#fp-compat">二 兼容策略</a>'
    + '<a href="#fp-formats">三 格式扩展</a>'
    + '<a href="#fp-fingerprint">四 文件指纹库</a>'
    + '<a href="#fp-flow">五 解析流程</a>'
    + '<a href="#fp-result">六 本次解析结果</a>'
    + '</nav>'
    + '<div class="fp-main">'
    + '<h2 style="font-size:10px;font-weight:800;color:#16233a;margin:0 0 10px">📁 文件解析</h2>'
    + '<p style="font-size:10px;color:#64748b;margin:0 0 10px">{{file_fingerprints}}类文件指纹 · 三层递进识别 · 四方交叉验证 · 8种格式全兼容 · OCR扫描件解析 · 关键词打分 · 结构分析 · 数据推断兜底</p>'
        + '<div style="background:#fff;border:1px solid #e2e8f0;padding:20px 24px;border-radius:8px;margin-bottom:10px">'
    + '<p style="font-size:10px;color:#3a4048;line-height:20px;margin:0">'
    + '文件解析系统是税务合规分析的第一步——将企业上传的各种格式的原始资料（Excel/PDF/CSV/Word/图片），'
    + '通过{{file_fingerprints}}类文件指纹 + 四层递进识别 + 四方交叉验证，自动判定文件类型并提取为结构化数据。'
    + '支持多种文件格式（xls/xlsx/csv/pdf/docx/jpg/png/tiff），兼容各类列名变体，'
    + '采用自适应表头检测（不预设表头在第几行）和汇总行自动过滤，确保数据质量。'
    + '</p>'
    + '</div>'

+ '<div id="fp-static"></div>'
    + '<div id="fp-analysis-result"></div>'
    + '</div></div>';
  renderFileParsingStatic();
  if (_cachedFileParsingReport) { renderFileParsingResult(_cachedFileParsingReport); }
  else { loadFileParsingData(); }
  // 侧边栏子模块入口
  if (window._fpSection) {
    var sec = window._fpSection;
    window._fpSection = null;
    if (sec === 'fp-result') { window._pendingFpSlice = 'fp-result'; }
    else {
      // CSS注入隐藏无关内容
      var s = document.createElement('style');
      s.textContent = '.fp-toc{display:none!important}.fp-layout{display:block!important}.fp-main h2,.fp-main>p,.fp-main>div:first-child{display:none!important}#fp-mechanism,#fp-compat,#fp-formats,#fp-fingerprint,#fp-flow,#fp-result{display:none!important}#'+sec+'{display:block!important}';
      container.appendChild(s);
    }
  }
}

function fpSliceToSection(sectionId) {
  var toc = document.querySelector('.fp-toc');
  if (toc) toc.style.display = 'none';
  var layout = document.querySelector('.fp-layout');
  if (layout) layout.style.display = 'block';
  var h2 = document.querySelector('.fp-main h2');
  if (h2) h2.style.display = 'none';
  var p = document.querySelector('.fp-main > p');
  if (p) p.style.display = 'none';
  var overview = document.querySelector('.fp-main > div');
  if (overview && !overview.id) overview.style.display = 'none';
  // Hide/Show target section
  var allSecs = document.querySelectorAll('#fp-mechanism,#fp-compat,#fp-formats,#fp-fingerprint,#fp-flow,#fp-result');
  for (var i = 0; i < allSecs.length; i++) {
    allSecs[i].style.display = allSecs[i].id === sectionId ? 'block' : 'none';
  }
  setTimeout(function() {
    var el = document.getElementById(sectionId);
    if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
  }, 200);
}

function renderFileParsingStatic() {
  var target = document.getElementById('fp-static');
  if (!target) return;

  var fps = fpFingerprints();
  var html = '';

  // ═══════════════════════════════════════════════
  // 一、识别机制：四层递进 + 四方交叉验证
  // ═══════════════════════════════════════════════
  html += '<div id="fp-mechanism" style="margin-bottom:48px">'
    + '<h3>一、识别机制：四层递进 + 四方交叉验证</h3>'
    + '<p style="font-size:10px;color:#3a4048;line-height:20px;margin:0 0 10px">'
    + '系统接收到文件后，不依赖文件扩展名判断（用户上传的 .xls 可能是任何内容），'
    + '而是执行四层递进识别——从粗糙到精细、从单一证据到多方交叉验证，逐步锁定文件真实类型。'
    + '整个过程模拟人类专家的判断逻辑：先看表头关键词 → 再看列结构 → '
    + '再看数据样本 → 最后综合文件名/列头/数据/公司身份四方证据做最终裁决。'
    + '</p>'

    // Step 1
    + '<div class="fp-step" style="margin-bottom:10px;border-left:4px solid #16233a">'
    + '<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">'
    + '<span style="display:inline-flex;align-items:center;justify-content:center;'
    + 'width:28px;height:28px;border-radius:6px;background:#16233a;color:#fff;font-size:10px;font-weight:700">1</span>'
    + '<span style="font-size:10px;font-weight:700;color:#16233a">关键词匹配 \u00b7 打分制</span>'
    + '<span style="font-size:10px;color:#64748b">最高优先级 \u00b7 识别率 ~80%</span>'
    + '</div>'
    + '<div style="font-size:10px;color:#3a4048;line-height:20px">'
    + '<p style="margin:0 0 10px"><strong>执行逻辑：</strong>'
    + '读取 Excel 文件的前200行表头区域（不只是第1行），将表头中的每一个词与{{file_fingerprints}}类文件指纹的关键词库做交叉匹配。'
    + '每命中一个关键词得1分，得分超过该类型指纹的评分阈值（通常2-4分）即判定为该类型。'
    + '多类型同时超过阈值时，取得分最高的类型作为主判定。'
    + '</p>'
    + '<p style="margin:0 0 10px"><strong>实际例子：</strong>'
    + '表头出现 \u201c对方户名\u201d\u201c交易日期\u201d\u201c收入金额\u201d三个词'
    + '\u2192 银行流水指纹得3分 \u2192 \u2265阈值3 \u2192 判定为银行流水。'
    + '表头出现 \u201c发票号码\u201d\u201c开票日期\u201d\u201c金额\u201d\u201c税额\u201d四个词'
    + '\u2192 通用发票指纹得4分 \u2192 \u2265阈值4 \u2192 判定为通用发票。'
    + '</p>'
    + '<p style="margin:0"><strong>边缘情况：</strong>'
    + '当多个类型得分非常接近（相差\u22641分）时，标记为\u201c存疑\u201d，进入结构分析做二次判定。'
    + '关键词库持续迭代——每发现一种新的列名变体，自动补充到对应类型的关键词集中。'
    + '目前银行流水关键词23个、工资表关键词60+个、通用发票关键词20个。'
    + '</p>'
    + '</div>'
    + '</div>'

    // Step 2
    + '<div class="fp-step" style="margin-bottom:10px;border-left:4px solid #64748b">'
    + '<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">'
    + '<span style="display:inline-flex;align-items:center;justify-content:center;'
    + 'width:28px;height:28px;border-radius:6px;background:#64748b;color:#fff;font-size:10px;font-weight:700">2</span>'
    + '<span style="font-size:10px;font-weight:700;color:#16233a">结构分析 \u00b7 列模式匹配</span>'
    + '<span style="font-size:10px;color:#64748b">第二优先级 \u00b7 多类型接近时激活</span>'
    + '</div>'
    + '<div style="font-size:10px;color:#3a4048;line-height:20px">'
    + '<p style="margin:0 0 10px"><strong>激活条件：</strong>'
    + '关键词匹配阶段，前两名得分差距\u22641分，或最高分类型得分恰好等于阈值（临界状态）。'
    + '此时不是简单地\u201c取最高分\u201d，而是进入更深层次的结构分析。'
    + '</p>'
    + '<p style="margin:0 0 10px"><strong>分析方法：</strong>'
    + '系统为每种文件类型维护了一套列模式模板——包括列数范围、关键列的位置、列的排列顺序。'
    + '例如银行流水的列模式模板：日期列(前3列) + 对方户名列(前3-5列) + 金额列(第4-8列) + 余额列(最后1-2列)。'
    + '工资表的列模式模板：姓名列(第1列) + 收入列(第2-5列) + 扣除列(第6-8列) + 实发列(倒数1-2列)。'
    + '</p>'
    + '<p style="margin:0"><strong>容错设计：</strong>'
    + '列位置允许\u00b13列的偏移（不同企业/不同财务软件导出的表头顺序可能不同），'
    + '关键列必须存在但位置可以浮动。模式相似度计算公式：命中列数/模板总列数 \u2265 60% 即匹配。'
    + '例如银行流水模板要求8列关键列，实际命中5列（5/8=62.5%\u226560%）\u2192 匹配成功。'
    + '</p>'
    + '</div>'
    + '</div>'

    // Step 3
    + '<div class="fp-step" style="margin-bottom:10px;border-left:4px solid #64748b">'
    + '<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">'
    + '<span style="display:inline-flex;align-items:center;justify-content:center;'
    + 'width:28px;height:28px;border-radius:6px;background:#64748b;color:#fff;font-size:10px;font-weight:700">3</span>'
    + '<span style="font-size:10px;font-weight:700;color:#16233a">数据推断 \u00b7 逐列语义分类</span>'
    + '<span style="font-size:10px;color:#64748b">兜底机制 \u00b7 绝不丢弃数据</span>'
    + '</div>'
    + '<div style="font-size:10px;color:#3a4048;line-height:20px">'
    + '<p style="margin:0 0 10px"><strong>触发场景：</strong>'
    + '关键词匹配和结构分析都无法确定文件类型时（例如企业自制的非标准表格、极少见的资料类型），'
    + '系统不会拒绝解析或丢弃数据，而是进入数据推断阶段——逐列读取前200行数据样本，'
    + '按每一个单元格的语义角色自动分类。'
    + '</p>'
    + '<p style="margin:0 0 10px"><strong>语义分类规则（5类）：</strong><br>'
    + '\u2192 日期格式（2023-01-01、2023/1/1、2023年1月1日、20230101等）\u2192 日期列<br>'
    + '\u2192 纯数字无明显小数位（整数、序号）\u2192 数量/编号列<br>'
    + '\u2192 含\u201c公司\u201d\u201c有限\u201d\u201c厂\u201d\u201c店\u201d\u201c集团\u201d等企业标识词 \u2192 企业名称列<br>'
    + '\u2192 含\u201c元\u201d\u201c金额\u201d\u201c￥\u201d\u201c¥\u201d\u201c合计\u201d或纯数字含2位小数 \u2192 金额列<br>'
    + '\u2192 含\u201c税\u201d\u201c%\u201d\u201c税率\u201d \u2192 税率列'
    + '</p>'
    + '<p style="margin:0"><strong>兜底输出：</strong>'
    + '数据推断无法确定具体类型时，标注为\u201c通用数据\u201d（generic_data），'
    + '保留完整的原始行列结构，交由下游分析模块（域分析系统/规则匹配系统）自行判断数据用途。'
    + '核心原则：不因无法识别而丢弃任何一行数据。'
    + '</p>'
    + '</div>'
    + '</div>'

    // Step 4
    + '<div class="fp-step" style="margin-bottom:10px;border-left:4px solid #16a34a">'
    + '<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">'
    + '<span style="display:inline-flex;align-items:center;justify-content:center;'
    + 'width:28px;height:28px;border-radius:6px;background:#16a34a;color:#fff;font-size:10px;font-weight:700">4</span>'
    + '<span style="font-size:10px;font-weight:700;color:#16233a">四方交叉验证 \u00b7 最终裁决</span>'
    + '<span style="font-size:10px;color:#64748b">2026-06-28新增 \u00b7 证据冲突时数据优先</span>'
    + '</div>'
    + '<div style="font-size:10px;color:#3a4048;line-height:20px">'
    + '<p style="margin:0 0 10px"><strong>设计目的：</strong>'
    + '前三层都是\u201c文件内部\u201d的推理——仅依据表头和数据本身判断。但有时文件内部的线索可能产生歧义'
    + '（例如一份银行流水表头被改了列名，看起来像费用明细）。四方交叉验证引入\u201c外部证据\u201d——'
    + '包括文件名暗示、公司身份锚定、买卖方关系匹配——从多角度验证前三层的结论。'
    + '</p>'
    + '<p style="margin:0 0 10px"><strong>四方证据：</strong><br>'
    + '\u2460 <strong>文件名暗示</strong>：文件名含\u201c开票\u201d\u201c销项\u201d\u2192倾向销项发票；含\u201c取票\u201d\u201c进项\u201d\u201c抵扣\u201d\u2192倾向进项发票。'
    + '但仅作为参考权重，不直接决定类型——因为文件名可能错误标注。<br>'
    + '\u2461 <strong>列头推理</strong>：前三层的结果，带置信度。不同类型的关键词得分和列模式相似度作为主证据。<br>'
    + '\u2462 <strong>数据扫描（买卖方身份）</strong>：读取数据样本中的企业名称字段，与公司身份做双向比对。'
    + '购方名称=当前公司\u2192进项发票；销方名称=当前公司\u2192销项发票。'
    + '双方都不匹配\u2192存疑排除（可能是其他公司的文件误上传）。<br>'
    + '\u2463 <strong>公司匹配</strong>：通过企业名称和统一社会信用代码双向锚定当前账套的企业身份，'
    + '确保发票方向判定的正确性。'
    + '</p>'
    + '<p style="margin:0"><strong>冲突裁决规则：</strong>'
    + '当四方证据出现矛盾时，优先级：数据扫描（买卖方匹配）> 列头推理（关键词得分）> '
    + '文件名暗示。因为数据不会说谎——如果数据中购方名称=当前公司，那么无论文件名写什么、'
    + '表头怎么命名，这份文件就是进项发票。文件名可能错误标注，表头可能不规范，但数据本身的身份关系是铁证。'
    + '</p>'
    + '</div>'
    + '</div>'
    + '</div>';

  // ═══════════════════════════════════════════════
  // 二、兼容策略（全部34类 + 跨格式）
  // ═══════════════════════════════════════════════
  html += '<div id="fp-compat" style="margin-bottom:48px">'
    + '<h3>二、兼容策略</h3>'
    + '<p style="font-size:10px;color:#3a4048;line-height:20px;margin:0 0 10px">'
    + '企业上传的资料格式千差万别——不同ERP系统、不同财务软件、不同银行导出的表格结构各不相同。'
    + '文件解析模块通过列名映射表（82+变体）和智能自适应机制，兼容主要的命名习惯差异。'
    + '</p>';

  // 各类型兼容详情
  var compatItems = [
    {title:'银行流水', icon:'\u{1f3e7}', detail:'' +
      '<strong>日期列兼容：</strong>交易日期、记账日期、交易时间、日期、申请日期、起息日 共6种。<br>' +
      '<strong>对方户名兼容：</strong>对方户名、交易对方、对方名称、counterparty、对方单位、收款人名称 共6种。<br>' +
      '<strong>金额兼容：</strong>收入金额、支出金额、贷方金额、借方金额、交易金额、发生额 共6种——' +
      '自动去除\u00a5/\u5143/\u9017\u53f7/\u7a7a\u683c等非数字字符。金额符号按借贷方向或交易关键词自动判断。<br>' +
      '<strong>余额兼容：</strong>本次余额、交易余额、账户余额 共3种。<br>' +
      '<strong>汇总行过滤：</strong>自动识别并剔除所有含\u201c小计\u201d\u201c合计\u201d\u201c总计\u201d\u201c本页合计\u201d\u201c本年累计\u201d\u201c当月合计\u201d的行。'},
    {title:'发票', icon:'\u{1f9fe}', detail:'' +
      '<strong>方向自动判定：</strong>购方名称/税号=当前公司\u2192进项发票；销方名称/税号=当前公司\u2192销项发票；双方都不匹配\u2192存疑排除。<br>' +
      '<strong>购买方列名兼容：</strong>购方名称、购买方名称、购方、买方、客户名称、付款方 共6种。<br>' +
      '<strong>销售方列名兼容：</strong>销方名称、销售方名称、销方、卖方、供应商名称、供方名称、收款方 共7种。<br>' +
      '<strong>发票号码兼容：</strong>发票号码、发票号、数电发票号码、票据号码 共4种。<br>' +
      '<strong>税收分类：</strong>货物或应税劳务名称、\u203b品名、商品名称、服务名称、项目名称 共5种——自动按最长子串匹配归类。<br>' +
      '<strong>金额兼容：</strong>金额、不含税金额、含税金额、价税合计、小写金额——自动识别含税/不含税并补齐缺失字段。'},
    {title:'工资表', icon:'\u{1f4b0}', detail:'' +
      '<strong>60+列名变体：</strong>本期收入/应发工资/实发工资/应发合计/实发合计/代扣个税/'
      + '基本养老保险/基本医疗保险/住房公积金/专项扣除/子女教育/赡养老人/基本工资/绩效工资/'
      + '岗位工资/加班工资/交通补贴/通讯补贴/餐补/高温补贴/奖金/年终奖/提成工资等。<br>' +
      '<strong>个税申报格式兼容：</strong>累计收入/累计减除费用/累计专项扣除/累计应纳税额/已预缴税额/应补退税额——'
      + '与工资表自动区分，按关键词集不同走不同解析器。<br>' +
      '<strong>合计行过滤：</strong>自动剔除\u201c合计\u201d\u201c总计\u201d\u201c小计\u201d行，防止重复统计。'},
    {title:'社保/公积金', icon:'\u{1f3e5}', detail:'' +
      '<strong>社保三列数据自动区分：</strong>缴费基数（工资基数/社保基数）、'
      + '单位缴纳（单位缴费/公司缴纳）、个人缴纳（个人缴费/个人承担）。<br>' +
      '<strong>五险自动识别：</strong>养老保险/医疗保险/失业保险/工伤保险/生育保险——各险种可能独立Sheet或以合并列出现。<br>' +
      '<strong>公积金兼容：</strong>公积金/住房公积金/住房储金、缴存基数/公积金基数、'
      + '缴存比例（自动识别单位+个人两部分）、月缴存额。'},
    {title:'申报表', icon:'\u{1f4cb}', detail:'' +
      '<strong>增值税申报表：</strong>销售额/销项税额/进项税额/应纳税额/期末留抵税额/即征即退——'
      + '兼容一般纳税人和小规模纳税人两种表格式。<br>' +
      '<strong>企业所得税申报表：</strong>营业收入/营业成本/利润总额/纳税调整增加额/纳税调整减少额/'
      + '应纳税所得额/税率/应纳所得税额——兼容查账征收和核定征收。<br>' +
      '<strong>个税申报表：</strong>与工资表通过关键词区分（含\u201c累计预扣预缴\u201d\u201c应补退税额\u201d\u201c所得项目\u201d等个税专属词）。<br>' +
      '<strong>印花税/完税证明：</strong>按税种名称和缴款日期格式自动识别。'},
    {title:'财务报表', icon:'\u{1f4ca}', detail:'' +
      '<strong>科目余额表：</strong>科目编码/科目名称/期初余额/本期借方/本期贷方/期末余额——兼容借贷方向和余额方向两种格式。<br>' +
      '<strong>财务报表（资产负债表/利润表）：</strong>按报表项目名称（流动资产、非流动资产、营业收入、营业成本等）自动区分。<br>' +
      '<strong>进销存台账：</strong>期初库存/本期入库/本期出库/期末库存/存货编码/产品名称——兼容数量和金额两类台账。'},
    {title:'合同/往来/资产', icon:'\u{1f4c4}', detail:'' +
      '<strong>合同台账：</strong>合同编号/合同名称/甲方/乙方/合同金额/已付金额/未付金额/签订日期/生效日期/到期日期——14字段全覆盖。<br>' +
      '<strong>应收/应付账款：</strong>客户/供应商名称、欠款金额/应付金额、账龄、账期、逾期标志。<br>' +
      '<strong>固定资产：</strong>资产名称/原值/累计折旧/净值/入账日期/折旧年限/残值率。<br>' +
      '<strong>无形资产/资产损失/费用明细/研发费用：</strong>各有专属关键词集和解析器，按列名自动路由。'},
    {title:'特殊类型', icon:'\u{1f50d}', detail:'' +
      '<strong>人员清单：</strong>姓名/身份证号/入职/离职/岗位/部门——与工资表通过关键词区分（无金额列）。<br>' +
      '<strong>股权交易：</strong>出让方/受让方/转让比例/转让价格/审批日期。<br>' +
      '<strong>借款合同：</strong>借款人/出借人/借款金额/利率/期限/担保方式。<br>' +
      '<strong>进出口报关：</strong>报关单号/进出口类型/商品名称/金额/币种/口岸。<br>' +
      '<strong>关联交易：</strong>关联方名称/交易类型/关联关系/交易金额/定价政策。<br>' +
      '<strong>通用数据（兜底）：</strong>以上所有类型均不匹配时，标注为generic_data——保留原始结构不变，将数据原样输出供下游模块自行判断。'}
  ];

  compatItems.forEach(function(ci) {
    html += '<details style="margin-bottom:10px;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden">'
      + '<summary style="padding:12px 16px;background:#fff;border-bottom:1px solid #f1f5f9;cursor:pointer;font-size:10px;font-weight:600;color:#16233a;user-select:none">'
      + ci.icon + ' ' + ci.title + '</summary>'
      + '<div style="padding:14px 16px;font-size:10px;color:#3a4048;line-height:20px;background:#fff">'
      + ci.detail + '</div>'
      + '</details>';
  });

  html += '</div>';

  // ═══════════════════════════════════════════════
  // 三、格式扩展（PDF/DOCX/CSV/OCR图片）
  // ═══════════════════════════════════════════════
  html += '<div id="fp-formats" style="margin-bottom:48px">'
    + '<h3>三、格式扩展：多格式全兼容</h3>'
    + '<p style="font-size:10px;color:#3a4048;line-height:20px;margin:0 0 10px">'
    + '除了传统的 Excel 格式（.xls/.xlsx），文件解析模块已扩展到支持以下格式的自动解析：'
    + '</p>'

    + '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:12px">'

    // PDF
    + '<div class="fp-step">'
    + '<div style="font-size:10px;font-weight:700;color:#16233a;margin-bottom:10px">\u{1f4c4} PDF文档</div>'
    + '<div style="font-size:10px;color:#3a4048;line-height:20px">'
    + '<strong>双系统架构：</strong>pdfplumber表格提取（优先）+ pypdf文本解析（兜底）。<br>'
    + '<strong>自适应策略：</strong>逐页提取所有表格 \u2192 取最大表格 \u2192 表头走多维指纹匹配 \u2192 '
    + '成功则按类型路由，失败则回退旧格式解析器。<br>'
    + '<strong>优势：</strong>不再硬编码特定银行格式（旧版仅支持招商银行大兴支行），任何银行/税务PDF均可识别。<br>'
    + '<strong>格式：</strong>支持 .pdf'
    + '</div>'
    + '</div>'

    // DOCX
    + '<div class="fp-step">'
    + '<div style="font-size:10px;font-weight:700;color:#16233a;margin-bottom:10px">\u{1f4dd} Word文档</div>'
    + '<div style="font-size:10px;color:#3a4048;line-height:20px">'
    + '<strong>表格提取：</strong>python-docx遍历所有表格 \u2192 合并多表格 \u2192 表头指纹匹配。<br>'
    + '<strong>文本兜底：</strong>无表格时提取段落文本，标注为 document_text 类型。<br>'
    + '<strong>应用场景：</strong>合同文件、申报说明、审计报告等Word格式资料。<br>'
    + '<strong>格式：</strong>支持 .docx'
    + '</div>'
    + '</div>'

    // CSV
    + '<div class="fp-step">'
    + '<div style="font-size:10px;font-weight:700;color:#16233a;margin-bottom:10px">\u{1f4ca} CSV文本</div>'
    + '<div style="font-size:10px;color:#3a4048;line-height:20px">'
    + '<strong>管道原生支持：</strong>csv.reader读取 \u2192 CsvSheet模拟Sheet接口 \u2192 指纹匹配。<br>'
    + '<strong>编码自动检测：</strong>UTF-8-BOM优先，自动处理逗号分隔和引号转义。<br>'
    + '<strong>应用场景：</strong>银行系统导出的流水、ERP导出的数据表等CSV格式。<br>'
    + '<strong>格式：</strong>支持 .csv'
    + '</div>'
    + '</div>'

    // OCR images
    + '<div class="fp-step">'
    + '<div style="font-size:10px;font-weight:700;color:#16233a;margin-bottom:10px">\u{1f4f7} OCR图片识别</div>'
    + '<div style="font-size:10px;color:#3a4048;line-height:20px">'
    + '<strong>双系统OCR：</strong>EasyOCR（中文优先，文字块坐标提取）+ Tesseract（系统兜底）。<br>'
    + '<strong>表格重建：</strong>Y坐标聚类（<15px=同行）\u2192 X排序 \u2192 构建行\u00d7列矩阵 \u2192 指纹匹配。<br>'
    + '<strong>字段提取：</strong>无表格结构时，正则提取发票号/代码/日期/金额等关键字段。<br>'
    + '<strong>首次使用：</strong>需联网下载EasyOCR模型（~200MB，一次性），之后本地缓存。<br>'
    + '<strong>格式：</strong>支持 .jpg .jpeg .png .bmp .tiff'
    + '</div>'
    + '</div>'

    + '</div>'
    + '</div>';

  // ═══════════════════════════════════════════════
  // 四、{{file_fingerprints}}类文件指纹库
  // ═══════════════════════════════════════════════
  html += '<div id="fp-fingerprint" style="margin-bottom:48px">'
    + '<h3>四、文件指纹库 \u00b7 ' + fps.length + ' 类</h3>'
    + '<p style="font-size:10px;color:#3a4048;line-height:20px;margin:0 0 10px">'
    + '每类指纹由 <strong>关键词集</strong> + <strong>得分阈值</strong> + <strong>专用解析器</strong> 三部分组成。'
    + '关键词决定了\u201c怎么看\u201d，阈值决定了\u201c多确定才能算\u201d，解析器决定了\u201c识别后怎么提取\u201d。'
    + '按使用频率分六梯队排列，第一梯队是税务合规中最常见的高频类型。'
    + '</p>';

  var groups = [
    {title:'第一梯队 \u00b7 高频核心（用户最常上传）', items: fps.slice(0,12),
     desc:'这12类文件是税务合规中最常出现的材料——银行流水、发票、工资表、社保公积金等。拥有最完善的关键词库（20-60+个关键词）和最成熟的解析器。得分阈值2-4分，识别率>95%。'},
    {title:'第二梯队 \u00b7 合同/权证/关联交易', items: fps.slice(12,17),
     desc:'合同和关联交易文件的识别依赖更细致的结构分析——关键词数量较少（9-12个），阈值通常为2分。这类文件的列结构比关键词更有特征性。'},
    {title:'第三梯队 \u00b7 申报表与财务报表', items: fps.slice(17,23),
     desc:'各类税务申报表和财务报表——关键词含税种名称、报表项目、会计科目等专业术语。阈值3分，因为申报表的列名专业性强、不易与其他类型混淆。'},
    {title:'第四梯队 \u00b7 往来与合同清单', items: fps.slice(23,27),
     desc:'应收账款、应付账款、预收预付等往来类数据表。特征：通常含对方单位名称+金额+账龄三要素。'},
    {title:'第五梯队 \u00b7 资产与费用', items: fps.slice(27,31),
     desc:'固定资产、无形资产、资产损失、费用明细、研发费用等资产和费用类表格。各有关键词特征，阈值2分。'},
    {title:'第六梯队 \u00b7 特殊交易与兜底', items: fps.slice(31),
     desc:'人员清单、股权交易、借款合同、进出口报关等特殊类型。最后是通用数据（generic_data）作为兜底——关键词阈值仅1分，确保任何有结构的表格都不会被丢弃。'},
  ];

  groups.forEach(function(g) {
    html += '<div style="margin-bottom:10px">'
      + '<div style="font-size:10px;font-weight:700;color:#16233a;margin-bottom:4px">' + escHtml(g.title) + '</div>'
      + '<div style="font-size:10px;color:#64748b;margin-bottom:10px;line-height:20px">' + escHtml(g.desc) + '</div>'
      + '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:8px">';

    g.items.forEach(function(item) {
      html += '<div style="padding:10px 12px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;font-size:10px;line-height:20px">'
        + '<div style="font-weight:600;color:#16233a;margin-bottom:4px"><span style="font-size:10px">' + item.icon + '</span> ' + escHtml(item.name) + '</div>'
        + '<div style="color:#64748b;font-size:10px;margin-bottom:4px">' + escHtml(item.sig) + '</div>'
        + '<div style="color:#64748b;font-size:10px">阈值：' + item.threshold + ' \u00b7 ' + item.parser + '</div>'
        + '</div>';
    });

    html += '</div></div>';
  });

  html += '</div>';

  // ═══════════════════════════════════════════════
  // 五、解析流程（8步详解）
  // ═══════════════════════════════════════════════
  html += '<div id="fp-flow" style="margin-bottom:48px">'
    + '<h3>五、解析流程：8步全链路</h3>'
    + '<p style="font-size:10px;color:#3a4048;line-height:20px;margin:0 0 10px">'
    + '从磁盘上的原始文件到结构化的分析数据，文件解析系统执行8个步骤：'
    + '</p>';

  var steps = [
    {num:'1', title:'磁盘扫描', detail:'' +
      '遍历 uploads/ 目录下所有支持格式的文件（.xls .xlsx .csv .pdf .docx .jpg .png 等），按文件修改时间排序。' +
      '跳过系统临时文件（~$开头、.tmp结尾）。同一文件MD5去重——内容相同的文件只解析一次，避免重复工作。'},
    {num:'2', title:'格式检测', detail:'' +
      '读取文件前5KB数据，通过二进制签名（magic bytes）判断真实格式——不是依赖扩展名。' +
      'xls/xlsx: OLE2/ZIP签名；CSV: 纯文本逗号分隔；PDF: %PDF-头部；DOCX: ZIP+[Content_Types].xml；' +
      '图片: JPEG/PNG/BMP/TIFF头部签名。调用对应的文件读取库：openpyxl / xlrd / csv / pdfplumber / python-docx / PIL。'},
    {num:'3', title:'表头提取', detail:'' +
      '逐Sheet读取前200行（非硬编码\u201c第1行\u201d——自适应扫描直到找到列名行）。' +
      '对每一列：提取列名文本 + 前200个数据样本，构建\u201c表头特征向量\u201d。' +
      '自动跳过空行、纯数字行（不太可能是表头）、以及明显的合计行。'},
    {num:'4', title:'指纹匹配', detail:'' +
      '将表头特征向量与多维指纹关键词库做交叉匹配：遍历每一种文件类型的关键词集，' +
      '对表头中出现的每个词检查是否命中，每命中1词得1分。记录每种类型的总得分。' +
      '同时检查\u201c关键识别词\u201d——某些词的出现足以直接判定类型（如\u201c发票号码\u201d+3个其他词\u2192通用发票）。'},
    {num:'5', title:'类型判定', detail:'' +
      '取得分最高的类型：①最高分\u2265阈值 \u2192 直接判定为该类型；' +
      '②最高分<阈值 且 前两名差距\u22641分 \u2192 进入结构分析做二次判定；' +
      '③所有类型得分均<阈值且无接近候选人 \u2192 进入数据推断（第3层）。' +
      '四方交叉验证在判定存疑时介入——综合文件名/列头/数据/公司匹配做最终裁决。'},
    {num:'6', title:'解析器调用', detail:'' +
      '根据最终确定的文件类型，调用对应的专用解析器函数。' +
      '每个解析器负责将原始表格转换为字段标准化的结构化数据：' +
      '银行流水\u2192_parse_bank_sheet、发票\u2192_parse_invoice_sheet、' +
      '工资\u2192_parse_salary_sheet、合同\u2192_parse_contract_sheet等。' +
      '解析器内部完成：列名映射归一化（82+变体\u2192标准字段名）、数据类型转换（字符串\u2192float/date）、无效行过滤。'},
    {num:'7', title:'标准化输出', detail:'' +
      '统一字段命名规范：date（日期）、amount（金额）、counterparty（对方）、' +
      'seller（销售方）、buyer（购买方）、goods（品名）、quantity（数量）、' +
      'tax_rate（税率）、tax_amount（税额）、total（价税合计）。' +
      '所有金额统一为float（去除千分位逗号/货币符号）、日期统一为YYYY-MM-DD格式。' +
      '输出为可在后续分析中直接使用的结构化JSON数据。'},
    {num:'8', title:'日志与路由', detail:'' +
      '将每个文件的解析结果写入 file_results 数组和 pipeline_log 日志。' +
      '按文件类型自动路由到对应的数据列表：银行流水\u2192bank_txs、发票\u2192invoice_data、' +
      '工资\u2192salary_data、合同\u2192contract_data等。' +
      '解析失败的标注error原因，供诊断面板回溯。所有日志持久化到分析缓存中。'}
  ];

  steps.forEach(function(st) {
    html += '<div class="fp-step" style="margin-bottom:10px">'
      + '<div style="display:flex;gap:12px">'
      + '<span style="display:inline-flex;align-items:center;justify-content:center;'
      + 'flex-shrink:0;width:28px;height:28px;border-radius:50%;background:#f1f5f9;'
      + 'color:#64748b;font-size:10px;font-weight:700">' + st.num + '</span>'
      + '<div>'
      + '<div style="font-size:10px;font-weight:700;color:#16233a;margin-bottom:4px">' + st.title + '</div>'
      + '<div style="font-size:10px;color:#3a4048;line-height:20px">' + st.detail + '</div>'
      + '</div></div>'
      + '</div>';
  });

  html += '</div>';

  target.innerHTML = html;
}

// {{file_fingerprints}}类文件指纹数据（详尽版）
function fpFingerprints() {
  return [
    // 第一梯队
    {icon:'🏧', name:'银行流水', sig:'对方户名 | 交易日期 | 收入金额 | 支出金额 | 借贷标志 | 余额 (23个关键词 阈值3分)', threshold:'≥3', parser:'_parse_bank_sheet'},
    {icon:'💰', name:'工资表', sig:'本期收入 | 应发工资 | 代扣个税 | 社保 | 公积金 | 实发合计 (60+关键词 阈值2分)', threshold:'≥2', parser:'_parse_salary_sheet'},
    {icon:'🧾', name:'销项发票', sig:'购方名称 | 购方税号 | 购买方纳税人识别号 (10个关键词 阈值2分)', threshold:'≥2', parser:'_parse_invoice_sheet(销项)'},
    {icon:'📥', name:'进项发票', sig:'销方名称 | 销方税号 | 销售方名称 | 供应商名称 (11个关键词 阈值2分)', threshold:'≥2', parser:'_parse_invoice_sheet(进项)'},
    {icon:'📋', name:'通用发票', sig:'发票号码 | 发票代码 | 开票日期 | 金额 | 税额 | 价税合计 | 税率 (20个关键词 阈值4分)', threshold:'≥4', parser:'_parse_invoice_sheet(进项)'},
    {icon:'📝', name:'记账凭证', sig:'凭证号 | 科目名称 | 摘要 | 借方金额 | 贷方金额 (8个主关键词 阈值2分)', threshold:'≥2', parser:'_parse_voucher_sheet'},
    {icon:'🛡️', name:'社保明细', sig:'缴费基数 | 单位缴纳 | 个人缴纳 | 养老保险 | 医疗保险 | 工伤保险 (15个关键词 阈值2分)', threshold:'≥2', parser:'_parse_social_sheet'},
    {icon:'🏡', name:'公积金', sig:'公积金 | 缴存基数 | 缴存比例 | 单位缴存 | 个人缴存 | 月缴存额 (17个关键词 阈值2分)', threshold:'≥2', parser:'_parse_housing_fund_sheet'},
    {icon:'📑', name:'进项抵扣勾选', sig:'勾选状态 | 有效抵扣税额 | 数电发票号码 | 发票风险等级 (5个关键词 阈值2分)', threshold:'≥2', parser:'_parse_input_vat_sheet'},
    {icon:'📦', name:'进销存台账', sig:'期初库存 | 本期入库 | 本期出库 | 期末库存 | 存货编码 | 产品名称 (16个关键词 阈值2分)', threshold:'≥2', parser:'_parse_inventory_sheet'},
    {icon:'📊', name:'科目余额表', sig:'科目编码 | 科目名称 | 期初余额 | 本期发生额 | 期末余额 (8个关键词 阈值2分)', threshold:'≥2', parser:'_parse_trial_balance_sheet'},
    // 第二梯队
    {icon:'📄', name:'合同文件', sig:'合同编号 | 签约方 | 合同金额 | 签订日期 | 履约期限 (9个关键词 阈值2分)', threshold:'≥2', parser:'_parse_contract_sheet'},
    {icon:'🔗', name:'关联交易', sig:'关联方名称 | 交易类型 | 关联关系 | 交易金额 | 定价方式 (12个关键词 阈值2分)', threshold:'≥2', parser:'_parse_related_party'},
    // 第三梯队
    {icon:'💰', name:'财务报表', sig:'营业收入 | 营业成本 | 利润总额 | 资产合计 | 负债合计 | 期末余额 (18个关键词 阈值3分)', threshold:'≥3', parser:'_parse_financial_sheet'},
    {icon:'🏦', name:'增值税申报表', sig:'销售额 | 销项税额 | 进项税额 | 应纳税额 | 期末留抵 (19个关键词 阈值3分)', threshold:'≥3', parser:'_parse_vat_declaration'},
    {icon:'📈', name:'企业所得税申报表', sig:'营业收入 | 营业成本 | 利润总额 | 应纳税所得额 | 税率 (11个关键词 阈值3分)', threshold:'≥3', parser:'_parse_cit_declaration'},
    {icon:'👤', name:'个税申报表', sig:'纳税人姓名 | 收入 | 应纳税所得额 | 已缴税额 | 应补退税额 (16个关键词 阈值2分)', threshold:'≥2', parser:'_parse_individual_tax'},
    {icon:'📜', name:'印花税', sig:'税目 | 计税金额 | 税率 | 应纳税额 | 减免税额 (12个关键词 阈值2分)', threshold:'≥2', parser:'_parse_stamp_duty'},
    {icon:'📋', name:'完税证明', sig:'税种 | 所属期 | 计税金额 | 实缴金额 | 缴款日期 (14个关键词 阈值2分)', threshold:'≥2', parser:'_parse_tax_payment'},
    // 第四梯队
    {icon:'📄', name:'合同清单', sig:'合同名称 | 对方名称 | 合同金额 | 已付金额 | 未付金额 (16个关键词 阈值2分)', threshold:'≥2', parser:'_parse_contract_list'},
    {icon:'🤝', name:'应收账款', sig:'客户名称 | 欠款金额 | 账龄 | 账期 | 是否逾期 (10个关键词 阈值2分)', threshold:'≥2', parser:'_parse_accounts_receivable'},
    {icon:'🏗️', name:'应付账款', sig:'供应商名称 | 应付金额 | 账龄 | 付款条件 (10个关键词 阈值2分)', threshold:'≥2', parser:'_parse_accounts_payable'},
    {icon:'💳', name:'预收预付', sig:'客户/供应商名称 | 预收金额 | 预付金额 | 结算状态 (10个关键词 阈值2分)', threshold:'≥2', parser:'_parse_prepaid_advance'},
    {icon:'🧾', name:'其他应收付', sig:'对方名称 | 应收/应付 | 金额 | 账龄 | 坏账准备 (7个关键词 阈值2分)', threshold:'≥2', parser:'_parse_other_receivables'},
    // 第五梯队
    {icon:'🏭', name:'固定资产', sig:'资产名称 | 原值 | 累计折旧 | 净值 | 入账日期 | 折旧年限 (14个关键词 阈值2分)', threshold:'≥2', parser:'_parse_fixed_assets'},
    {icon:'📜', name:'无形资产', sig:'资产名称 | 原值 | 累计摊销 | 净值 | 摊销年限 (9个关键词 阈值2分)', threshold:'≥2', parser:'_parse_intangible_assets'},
    {icon:'📊', name:'资产损失', sig:'资产名称 | 损失金额 | 损失原因 | 审批日期 (8个关键词 阈值2分)', threshold:'≥2', parser:'_parse_asset_impairment'},
    {icon:'📋', name:'费用明细', sig:'费用类型 | 金额 | 报销人 | 所属部门 | 发生日期 (20个关键词 阈值2分)', threshold:'≥2', parser:'_parse_expense_detail'},
    {icon:'🔬', name:'研发费用', sig:'研发项目 | 费用类型 | 金额 | 研发阶段 | 资本化/费用化 (12个关键词 阈值2分)', threshold:'≥2', parser:'_parse_rd_expense'},
    // 第六梯队
    {icon:'👥', name:'人员清单', sig:'姓名 | 身份证号 | 入职日期 | 离职日期 | 岗位 | 部门 (14个关键词 阈值2分)', threshold:'≥2', parser:'_parse_employee_list'},
    {icon:'📄', name:'股权交易', sig:'出让方 | 受让方 | 转让比例 | 转让价格 | 审批日期 (9个关键词 阈值2分)', threshold:'≥2', parser:'_parse_equity_transaction'},
    {icon:'💰', name:'借款合同', sig:'借款人 | 出借人 | 借款金额 | 利率 | 期限 | 担保方式 (14个关键词 阈值2分)', threshold:'≥2', parser:'_parse_loan_borrowing'},
    {icon:'🚢', name:'进出口报关', sig:'报关单号 | 进出口类型 | 商品名称 | 金额 | 币种 | 口岸 (15个关键词 阈值2分)', threshold:'≥2', parser:'_parse_import_export'},
    {icon:'📋', name:'通用数据', sig:'纯数值表 (9个关键词 兜底阈值1分)', threshold:'≥1', parser:'_parse_generic'},
  ];
}

async function loadFileParsingData() {
  var target = document.getElementById('fp-analysis-result');
  if (!target) return;
  try {
    var data = await getSharedAnalysis();
    if (!data.ok) {
      target.innerHTML = '<div style="padding:48px 0;font-size:10px;color:#64748b">暂无分析结果，请先运行一键稽查</div>';
      return;
    }
    _cachedFileParsingReport = data.report;
    renderFileParsingResult(data.report);
  } catch (e) {
    target.innerHTML = '<div style="padding:48px 0;font-size:10px;color:#64748b">加载失败</div>';
  }
}

function renderFileParsingResult(report) {
  var target = document.getElementById('fp-analysis-result');
  if (!target) return;
  var frs = report.file_results || [];
  var plogs = report.pipeline_log || [];

  var parsed = frs.filter(function(f) { return f.type !== 'unknown' && !f.error; }).length;
  var failed = frs.filter(function(f) { return f.error; }).length;

  var html = '<div id="fp-result">'
    + '<h3 style="font-size:10px;font-weight:700;color:#16233a;margin:0 0 6px">六、本次解析结果</h3>'
    + '<p style="font-size:10px;color:#64748b;margin:0 0 10px">本次分析共解析 ' + frs.length + ' 个文件，成功识别 ' + parsed + ' 个，未识别 ' + failed + ' 个</p>'

    // 统计卡片
    + '<div style="display:flex;gap:12px;margin-bottom:10px">'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:10px;font-weight:700;color:#16233a">' + frs.length + '</div><div style="font-size:10px;color:#64748b;margin-top:4px">文件总数</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:10px;font-weight:700;color:#059669">' + parsed + '</div><div style="font-size:10px;color:#64748b;margin-top:4px">已解析</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:10px;font-weight:700;color:#dc2626">' + failed + '</div><div style="font-size:10px;color:#64748b;margin-top:4px">未解析</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:10px;font-weight:700;color:#16233a">' + plogs.length + '</div><div style="font-size:10px;color:#64748b;margin-top:4px">管线日志</div></div>'
    + '</div>'

    // 类型分布
    + '<h4 style="font-size:10px;font-weight:600;color:#64748b;margin:0 0 10px">类型分布</h4>';
  var typeCount = {};
  frs.forEach(function(fr) { var t = fr.type || 'unknown'; typeCount[t] = (typeCount[t] || 0) + 1; });
  var types = Object.keys(typeCount).sort(function(a,b) { return typeCount[b] - typeCount[a]; });
  if (types.length > 0) {
    html += '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px">';
    types.forEach(function(t) {
      html += '<div style="padding:6px 12px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;font-size:10px;color:#3a4048">'
        + escHtml(t) + ' <span style="font-weight:600;color:#16233a">x' + typeCount[t] + '</span></div>';
    });
    html += '</div>';
  }

  // 解析明细表
  html += '<h4 style="font-size:10px;font-weight:600;color:#64748b;margin:0 0 10px">解析明细</h4>';

  if (frs.length === 0) {
    html += '<div style="color:#64748b;font-size:10px;padding:24px 0">无文件数据</div>';
  } else {
    html += '<table style="width:100%;border-collapse:collapse;font-size:10px">'
      + '<thead><tr style="border-bottom:2px solid #16233a;text-align:left">'
      + '<th style="padding:8px 12px 8px 0;font-weight:600;color:#16233a;width:36px">#</th>'
      + '<th style="padding:8px 12px;font-weight:600;color:#16233a">文件名</th>'
      + '<th style="padding:8px 12px;font-weight:600;color:#16233a">识别类型</th>'
      + '<th style="padding:8px 12px;font-weight:600;color:#16233a">数据条数</th>'
      + '<th style="padding:8px 12px;font-weight:600;color:#16233a">解析动作</th>'
      + '<th style="padding:8px 12px;font-weight:600;color:#16233a;min-width:100px">识别依据</th>'
      + '</tr></thead><tbody>';

    frs.forEach(function(fr, i) {
      var typeLabel = fr.type || '未知';
      var status = fr.error ? 'fail' : (fr.type === 'unknown' ? 'warn' : 'ok');
      var rowCount = '—';
      var actions = '';
      if (fr.actions && fr.actions.length) {
        var m = (fr.actions.join(' ')).match(/(\d+)条/);
        if (m) rowCount = m[1];
        actions = fr.actions.join(' · ');
      }
      var statusIcon = status === 'fail' ? '✗' : (status === 'warn' ? '△' : '✓');
      var statusColor = status === 'fail' ? '#dc2626' : (status === 'warn' ? '#f59e0b' : '#22c55e');
      var rowBg = status === 'fail' ? '#fef2f2' : (i % 2 === 0 ? '#fafafa' : 'transparent');

      html += '<tr style="border-bottom:1px solid #f1f5f9;background:' + rowBg + '">'
        + '<td style="padding:10px 12px 10px 0;color:#64748b">' + (i + 1) + '</td>'
        + '<td style="padding:10px 12px;color:#16233a;max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + escHtml(fr.file) + '">' + escHtml(fr.file) + '</td>'
        + '<td style="padding:10px 12px;color:#64748b">' + escHtml(typeLabel) + '</td>'
        + '<td style="padding:10px 12px;color:#3a4048;font-weight:600">' + rowCount + '</td>'
        + '<td style="padding:10px 12px;color:#64748b;font-size:10px;max-width:280px">' + escHtml(actions) + '</td>'
        + '<td style="padding:10px 12px;color:#64748b;font-size:10px">' + (function(){
          var diag = [];
          var tr = fr._trace || {};
          var kw = tr.kw_phase || {};
          var st = tr.st_phase || {};
          if (kw.best) diag.push('得分' + kw.best.score + '/' + (kw.best.threshold || '?'));
          if (st.best && st.best.confidence != null) diag.push('置信度' + Math.round(st.best.confidence*100) + '%');
          if (fr.match_score != null) diag.push('匹配' + fr.match_score + '/' + (fr.match_threshold || '?'));
          if (fr.st_confidence != null) diag.push('结构' + Math.round(fr.st_confidence*100) + '%');
          if (status === 'fail' || status === 'warn') diag.push('<span style=\'color:#e02424;font-weight:600\'>需复核</span>');
          return diag.join(' · ') || '—';
        })() + '</td>'
        + '</tr>';
    });

    html += '</tbody></table>';
  }

  // 诊断建议（失败/未识别文件的修复建议）
  var diagFiles = frs.filter(function(fr){
    return fr.error || fr.type === 'unknown' || (fr._trace && fr._trace.suggestions && fr._trace.suggestions.length > 0);
  });
  if (diagFiles.length > 0) {
    html += '<h4 style="font-size:10px;font-weight:600;color:#64748b;margin:28px 0 12px">诊断与修复建议 — 共 ' + diagFiles.length + ' 个文件</h4>';
    diagFiles.forEach(function(df){
      var sug = (df._trace && df._trace.suggestions) || [];
      html += '<div style="margin-bottom:10px;border:1px solid #fecaca;border-radius:6px;overflow:hidden">'
        + '<div style="padding:10px 14px;background:#fef2f2;font-size:10px;font-weight:600;color:#dc2626">' + escHtml(df.file) + '（' + escHtml(df.type || '未知') + '）</div>';
      if (sug.length > 0) {
        html += '<div style="padding:12px 14px;background:#fff">';
        sug.forEach(function(s){
          html += '<div style="margin-bottom:10px;padding-left:12px;border-left:3px solid #f59e0b">'
            + '<div style="font-size:10px;font-weight:600;color:#92400e;margin-bottom:3px">问题：' + escHtml(s.issue) + '</div>'
            + (s.detail ? '<div style="font-size:10px;color:#64748b;margin-bottom:3px;line-height:1.8">' + escHtml(s.detail) + '</div>' : '')
            + (s.fix ? '<div style="font-size:10px;color:#0e7490;line-height:1.8">修复建议：' + escHtml(s.fix) + '</div>' : '')
            + '</div>';
        });
        html += '</div>';
      } else {
        html += '<div style="padding:12px 14px;font-size:10px;color:#64748b">暂无详细诊断信息，建议检查文件格式与内容是否完整。</div>';
      }
      html += '</div>';
    });
  }

  // 管线日志（详尽版）
  if (plogs.length > 0) {
    html += '<h4 style="font-size:10px;font-weight:600;color:#64748b;margin:40px 0 12px">管线日志 — 共 ' + plogs.length + ' 条</h4>';
    html += '<div style="background:#16233a;border-radius:6px;padding:20px 24px;max-height:500px;overflow-y:auto;font-family:\'SF Mono\',\'Fira Code\',monospace;font-size:10px;line-height:20px">';
    plogs.forEach(function(log, i) {
      var color = '#64748b';
      if (/异常|失败|错误/.test(log)) color = '#fca5a5';
      else if (/完成|成功|通过/.test(log)) color = '#86efac';
      else if (/发现|触发|命中/.test(log)) color = '#fde68a';
      else if (/Phase|Step|阶段/.test(log)) color = '#93c5fd';
      html += '<div style="color:' + color + '">[' + (i + 1).toString().padStart(3, ' ') + '] ' + escHtml(log) + '</div>';
    });
    html += '</div>';
  }

  html += '</div>'; // fp-result
  target.innerHTML = html;
  if (window._pendingFpSlice) { var s = window._pendingFpSlice; window._pendingFpSlice = null; fpSliceToSection(s); }
}

// ==================== 页面2：域分析（详尽版） ====================
function renderDomainAnalysisPage(container) {
  if (!container) return;
  window.currentModule = '域分析';
  container.innerHTML = '<style>.da-layout{display:flex;gap:24px;max-width:1200px;margin:0 auto;padding:20px;background:#fff}.da-toc{width:190px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:10px;line-height:20px;max-height:calc(100vh-40px);overflow-y:auto}.da-toc .toc-title{font-weight:700;color:#16233a;font-size:10px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.da-toc a{display:block;color:#3a4048;text-decoration:none;padding:2px 8px;border-radius:4px;cursor:pointer}.da-toc a:hover,.da-toc a.active{background:#eff6ff;color:#2563eb;font-weight:600}.da-main{flex:1;min-width:0;background:#fff}.da-main h3{font-size:10px!important;font-weight:700!important;color:#16233a!important;padding-bottom:8px!important;border-bottom:2px solid #e2e8f0!important;margin:0 0 10px!important}.da-main section{margin-bottom:48px!important;scroll-margin-top:20px}</style>'
    + '<div class="da-layout">'
    + '<nav class="da-toc"><div class="toc-title">📖 导航</div>'
    + '<a href="#da-intro">一 什么是域分析</a>'
    + '<a href="#da-arch">二 域分析架构</a>'
    + '<a href="#da-domains">三 分析域</a>'
    + '<a href="#da-result">四 本次分析结果</a>'
    + '</nav>'
    + '<div class="da-main">'
    + '<h2 style="font-size:10px;font-weight:800;color:#16233a;margin:0 0 10px">🔬 域分析</h2>'
    + '<p style="font-size:10px;color:#64748b;margin:0 0 10px">{{domain_functions}}个域分析函数 · 12大分类 · 跨域关联推理 · 多源证据链串联 · 资料情报自适应分类</p>'
    + renderDomainAnalysisStatic()
    + '<div id="da-analysis-result"></div>'
    + '</div></div>';

  if (_cachedDomainReport) { renderDomainAnalysisResult(_cachedDomainReport); }
  else { loadDomainAnalysisData(); }
  // 侧边栏子模块入口
  if (window._daSection) {
    var dsec = window._daSection;
    window._daSection = null;
    if (dsec === 'da-result') { window._pendingDaSlice = 'da-result'; }
    else {
      var ds = document.createElement('style');
      ds.textContent = '.da-toc{display:none!important}.da-layout{display:block!important}.da-main h2,.da-main>p{display:none!important}#da-intro,#da-arch,#da-domains,#da-result{display:none!important}#'+dsec+'{display:block!important}';
      container.appendChild(ds);
    }
  }
}

function daSliceToSection(sectionId) {
  var toc = document.querySelector('.da-toc');
  if (toc) toc.style.display = 'none';
  var layout = document.querySelector('.da-layout');
  if (layout) layout.style.display = 'block';
  var h2 = document.querySelector('.da-main h2');
  if (h2) h2.style.display = 'none';
  var p = document.querySelector('.da-main > p');
  if (p) p.style.display = 'none';
  var allSecs = document.querySelectorAll('#da-intro,#da-arch,#da-domains,#da-result');
  for (var i = 0; i < allSecs.length; i++) {
    allSecs[i].style.display = allSecs[i].id === sectionId ? 'block' : 'none';
  }
  setTimeout(function() {
    var el = document.getElementById(sectionId);
    if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
  }, 200);
}

function renderDomainAnalysisStatic() {
  var html = '';

  // ══════ Hero摘要 ══════
  html += '<div style="background:#fff;border:1px solid #e2e8f0;padding:20px 24px;border-radius:8px;margin-bottom:10px">'
    + '<p style="font-size:10px;color:#3a4048;line-height:20px;margin:0">'
    + '域分析是税务合规分析的核心层——分析域从资金流、进销存、供应商、交叉验证、经营实质、'
    + '资料完备度、发票、合同凭证、税务社保、资产关联、行业对标、跨域推理、补充税种共13个维度，'
    + '对同一份企业数据进行全方位、多角度、交叉印证的分析。每个域由独立的域分析函数驱动，'
    + '输出结构化的发现列表，域与域之间通过跨域关联推理形成多源证据链，最终汇集成完整的税务合规报告。'
    + '</p>'
    + '</div>'

  // ══════ 一、什么是域分析 ══════
  html += '<div id="da-intro" style="margin-bottom:48px">'
    + '<h3 style="font-size:10px;font-weight:700;color:#16233a;margin:0 0 6px">一、什么是域分析</h3>'
    + '<p style="font-size:10px;color:#3a4048;line-height:20px;margin:0 0 10px">'
    + '域分析（Domain Analysis）是税务合规系统的核心分析层——位于文件解析和报告生成之间。'
    + '系统将从资料中提取的全部原始数据（银行流水、发票、工资表、社保、凭证、库存、合同等）'
    + '导入多个独立的分析域，每个域由专门的域分析函数（<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">_domain_*</code>）驱动，'
    + '从不同维度对同一份数据做独立又交叉的审视。'
    + '</p>'
    + '<p style="font-size:10px;color:#3a4048;line-height:20px;margin:0 0 10px">'
    + '<strong>核心设计理念：单一数据源，多维度交叉。</strong>一份银行流水，在资金流分析域看收款来源，'
    + '在经营实质域看费用结构，在税务域看税费支出。同一个数据点在不同域中扮演不同角色，'
    + '多个域的发现相互印证或矛盾——这正是税务合规判断的实质。'
    + '</p>'
    + '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px;margin-bottom:10px">'
    
    + '<div style="padding:14px 16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px">'
    + '<div style="font-size:10px;font-weight:700;color:#16233a;margin-bottom:6px">\u{1f4e5} 数据流入</div>'
    + '<div style="font-size:10px;color:#64748b;line-height:20px">'
    + '文件解析模块输出的结构化数据<br>'
    + '→ 银行交易列表（bank_txs）<br>'
    + '→ 销/进项发票列表（sal_invs/pur_invs）<br>'
    + '→ 工资表/社保/公积金/凭证/库存/合同<br>'
    + '→ 行业画像（ctx.industry）'
    + '</div>'
    + '</div>'
    
    + '<div style="padding:14px 16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px">'
    + '<div style="font-size:10px;font-weight:700;color:#16233a;margin-bottom:6px">\u{2699}\u{fe0f} 域执行</div>'
    + '<div style="font-size:10px;color:#64748b;line-height:20px">'
    + '{{domain_functions}}个域分析函数独立运行<br>'
    + '→ 每个域有数据守卫条件<br>'
    + '→ 缺数据→标记资料缺口不空跑<br>'
    + '→ 有数据→输出发现列表<br>'
    + '→ 行业闸门自动跳过不适用的域'
    + '</div>'
    + '</div>'
    
    + '<div style="padding:14px 16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px">'
    + '<div style="font-size:10px;font-weight:700;color:#16233a;margin-bottom:6px">\u{1f4e4} 发现输出</div>'
    + '<div style="font-size:10px;color:#64748b;line-height:20px">'
    + '每条发现含9个标准字段<br>'
    + '→ type: 发现类型名称<br>'
    + '→ level/score: 风险等级+评分<br>'
    + '→ detail: 详细数据+计算过程<br>'
    + '→ description/suggestion: 解读+建议<br>'
    + '→ policy_ref/category: 法律+归类'
    + '</div>'
    + '</div>'
    
    + '<div style="padding:14px 16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px">'
    + '<div style="font-size:10px;font-weight:700;color:#16233a;margin-bottom:6px">\u{1f517} 跨域串联</div>'
    + '<div style="font-size:10px;color:#64748b;line-height:20px">'
    + '单域发现→多域交叉印证<br>'
    + '→ 跨域关联推理自动串联<br>'
    + '→ 线索链+证据链+分析链<br>'
    + '→ 证据矛盾→协商系统消解<br>'
    + '→ 同向证据→置信度叠加升权'
    + '</div>'
    + '</div>'
    
    + '</div>'
    + '<div style="padding:14px 18px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;font-size:10px;color:#3a4048;line-height:20px">'
    + '<strong>\u{1f4cb} 发现字段详解：</strong><br>'
    + '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">type</code> 发现类型名称，如"资金流向 — 收款方异常"<br>'
    + '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">level</code> 风险等级：高风险/中风险/低风险/注意/信息<br>'
    + '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">score</code> 量化评分（0-10），≥8=极高，6-7=高，4-5=中，1-3=低<br>'
    + '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">detail</code> 详细数据——含计算过程、对比数据、触发阈值<br>'
    + '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">description</code> 税务合规解读——为什么这是风险，如何理解<br>'
    + '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">suggestion</code> 处理建议——具体可执行的核查步骤<br>'
    + '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">policy_ref</code> 法律依据——引用的法条和文件号<br>'
    + '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">category</code> 分类标签——用于报告中的风险归类和合并<br>'
    + '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">domain</code> 来源域——用于追溯发现的出处和回溯分析路径'
    + '</div>'
    + '</div>';

  // ══════ 二、域分析架构 ══════
  html += '<div id="da-arch" style="margin-bottom:48px">'
    + '<h3 style="font-size:10px;font-weight:700;color:#16233a;margin:0 0 6px">二、域分析架构</h3>'
    + '<p style="font-size:10px;color:#3a4048;line-height:20px;margin:0 0 10px">'
    + '系统将分析域按驱动方式分为三类——资料驱动、算法驱动、知识驱动。'
    + '不同类型的域有不同的激活条件和置信度逻辑。'
    + '</p>'
    + '<div style="display:flex;gap:16px;margin-bottom:20px">'
    
    + '<div style="flex:1;padding:20px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;border-left:4px solid #dc2626">'
    + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">'
    + '<span style="font-size:10px">\u{1f4c4}</span>'
    + '<span style="font-size:10px;font-weight:700;color:#16233a">资料驱动域</span>'
    + '</div>'
    + '<div style="font-size:10px;color:#64748b;line-height:20px">'
    + '<strong>依赖上传资料进行判断。</strong>必须有对应的原始数据才能执行分析。'
    + '资料完备度越高，发现结论的置信度越高。缺资料时标注资料缺口，'
    + '不做无依据结论——这是税务合规工作的基本原则。'
    + '</div>'
    + '<div style="margin-top:12px;padding:10px;background:#fef2f2;border-radius:6px;font-size:10px;color:#991b1b;line-height:20px">'
    + '<strong>代表域：</strong>资金流向追踪（需银行流水）、'
    + '工资社保比对（需工资表+社保明细）、'
    + '合同比对（需合同台账+发票）'
    + '</div>'
    + '</div>'
    
    + '<div style="flex:1;padding:20px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;border-left:4px solid #2563eb">'
    + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">'
    + '<span style="font-size:10px">\u{1f4ca}</span>'
    + '<span style="font-size:10px;font-weight:700;color:#16233a">算法驱动域</span>'
    + '</div>'
    + '<div style="font-size:10px;color:#64748b;line-height:20px">'
    + '<strong>基于数据内在特征自动计算。</strong>只要有对应的基础数据即可运行，'
    + '无需外部参考资料。结果基于数学和统计学方法，客观性强。'
    + '</div>'
    + '<div style="margin-top:12px;padding:10px;background:#eff6ff;border-radius:6px;font-size:10px;color:#1e40af;line-height:20px">'
    + '<strong>代表域：</strong>进销毛利率（需进销发票）、'
    + '存货周转预警（需进销存台账）、'
    + '异常交易时间分析（需银行流水）'
    + '</div>'
    + '</div>'
    
    + '<div style="flex:1;padding:20px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;border-left:4px solid #7c3aed">'
    + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">'
    + '<span style="font-size:10px">\u{1f4da}</span>'
    + '<span style="font-size:10px;font-weight:700;color:#16233a">知识驱动域</span>'
    + '</div>'
    + '<div style="font-size:10px;color:#64748b;line-height:20px">'
    + '<strong>内置行业基准库和法规库。</strong>将企业实际数据与66个行业的统计基准值对比，'
    + '与税收法律法规的要求对照验证。偏差超出正常范围时触发预警。'
    + '</div>'
    + '<div style="margin-top:12px;padding:10px;background:#f5f3ff;border-radius:6px;font-size:10px;color:#5b21b6;line-height:20px">'
    + '<strong>代表域：</strong>行业对标分析（需{{industries}}行业基准库）、'
    + '规则全覆盖验证（需{{rules_count}}条规则库）、'
    + 'CIT汇算清缴（需企业所得税法+实施条例）'
    + '</div>'
    + '</div>'
    
    + '</div>'
    + '</div>';

  // ══════ 三、分析域 ══════
  html += '<div id="da-domains" style="margin-bottom:48px">'
    + '<h3 style="font-size:10px;font-weight:700;color:#16233a;margin:0 0 6px">三、分析域</h3>'
    + '<div style="margin:0 0 10px;padding:14px 18px;background:linear-gradient(135deg,#eff6ff,#f0f9ff);border-radius:8px;border-left:3px solid #2563eb;font-size:10px;color:#3a4048;line-height:2">'
    + '<strong>🔍 判定规则（2026-06-28新增）</strong>——域分析执行前必须先通过以下判定：<br>'
    + '① <strong>公司身份锚定</strong>：以账套公司名+信用代码为锚点，发票买卖方与公司比对→方向判定<br>'
    + '② <strong>发票方向判定</strong>：购买方=公司→进项 | 销售方=公司→销项 | 双方不含→存疑排除<br>'
    + '③ <strong>进项再分类</strong>：含"抵扣税额"列→进项抵扣认证 | 无→进项发票(记账)<br>'
    + '④ <strong>服务行业闸门</strong>：销项金税编码∈25类服务→自动跳过进销存/BOM/进销比/毛利率对标<br>'
    + '⑤ <strong>品名级精准过滤</strong>：服务+货物混合企业→服务品名跳过进销存，实物品名正常检查<br>'
    + '⑥ <strong>综合判断·四方交叉验证</strong>：文件名暗示→列头推理→数据扫描→公司匹配，冲突时以数据为准<br>'
    + '⑦ <strong>存疑排除</strong>：买卖双方都不含公司的发票=非本账套数据=排除出所有计算<br>'
    + '</div>'
    + '<p style="font-size:10px;color:#64748b;margin:0 0 10px">每个域由独立的域分析函数驱动，按类别分组。右侧数字为该域的分析函数在 main.py 中的行号。</p>';

  var domainGroups = [
    // ══════ 一、资金流分析（4域） ══════
    {cat:'一、资金流分析', color:'#dc2626', desc:'银行流水收款来源分类、付款方身份核实、大额转账追踪、个人交易检测。资金流是税务合规的血液——每一笔资金流动都可能隐藏着未申报收入或虚开发票。', items:[
      {name:'资金全链路追踪', fn:'_domain_bank_tracking', line:'12137', desc:'收款来源自适应分类 · 第三方平台收款占比 · 付款方身份（企业/个人/税务/银行）· 税费支付自动识别'},
      {name:'资金流向追踪', fn:'_domain_fund_flow_mapping', line:'13806', desc:'收款方与开票客户匹配 · 付款方与进项供应商匹配 · 法人/股东交叉引用 · 个人大额转账预警'},
      {name:'异常交易时间分析', fn:'_domain_temporal_anomaly', line:'14298', desc:'非工作时间交易（深夜/凌晨/周末）· 节假日突击交易 · 月末集中大额行为识别'},
      {name:'个人交易风险', fn:'_domain_personal_transactions', line:'12251', desc:'个人买家发票占比异常 · 无票个人大额收入 · 个人转账收款未开票 · 个人卡收款规模评估'},
    ]},
    // ══════ 二、进销存分析（4域） ══════
    {cat:'二、进销存分析', color:'#f59e0b', desc:'发票品名交叉映射、进销平衡分析、存货周转率、制造业加工链条诊断。进销不匹配是虚开发票的核心线索。', items:[
      {name:'进销毛利率分析', fn:'_domain_profit_analysis', line:'12203', desc:'进项品名vs销项品名交叉映射 · 进销比自动计算 · 有进无销/有销无进触发制造业加工诊断 · BOM表需求判断'},
      {name:'发票实质性审计', fn:'_domain_invoice_audit', line:'14966', desc:'五层递进审计——①格式合规检查 ②同品名单价波动 ③加工费专项（外发加工真实性）④金额/数量合理性 ⑤进销品名映射+BOM缺失检测'},
      {name:'存货周转预警', fn:'_domain_inventory_turnover', line:'12393', desc:'周转率计算+库龄分析+库存结构合理性 · 入库>>出库→库存积压预警 · 仓储成本vs库存价值验证'},
      {name:'发票存货付款三角验证', fn:'_domain_triangle_invoice_inventory_payment', line:'13949', desc:'进项发票金额 vs 存货入库金额 vs 银行付款金额三向验证——票货分离、虚开嫌疑、付款对象不一致'},
    ]},
    // ══════ 三、供应商与客户分析（4域） ══════
    {cat:'三、供应商与客户分析', color:'#f59e0b', desc:'供应商集中度、地理分布、身份验证、空壳识别；客户结构分析与收入穿透。供应商群集和关联交易是偷逃税的高发区。', items:[
      {name:'供应商穿透分析', fn:'_domain_supplier_deep', line:'12286', desc:'前3大供应商占比 · 同城群集检测 · 名称异常检测（短名/***遮掩）· 占比>70%触发依赖预警'},
      {name:'供应商画像分析', fn:'_domain_supplier_profiling', line:'13757', desc:'行业/地域/注册资本/成立时间综合分析 · 新注册零实缴→可疑交易方 · 高频低额（刷票嫌疑）· 单月突击开票检测'},
      {name:'上下游穿透分析', fn:'_domain_supply_chain_deep', line:'14661', desc:'客户vs供应商关联关系穿透 · 同一企业既是客户又是供应商→对倒开票嫌疑 · 名称相似度群集 · 地域群集 · 进销双向交易循环'},
      {name:'客户维度三源穿透', fn:'_domain_customer_revenue_matching', line:'13317', desc:'按客户匹配开票金额vs收款金额 · 五时点对比法 · 大额无开票收款 · 整数特征可疑 · 付款方名称不一致检测'},
    ]},
    // ══════ 四、交叉验证（5域） ══════
    {cat:'四、多源交叉验证', color:'#7c3aed', desc:'两源以上数据相互比对，验证数据一致性。单源异常可能是巧合，多源交叉同时指向同一问题才是高置信度发现。', items:[
      {name:'多源交叉验证', fn:'_domain_multi_source_cross', line:'13111', desc:'资金流+发票流+货物流三源采购验证 · 收款vs开票偏差 · 薪酬三源（工资表vs银行vs个税）· 税务四源交叉'},
      {name:'凭证发票收入对比', fn:'_domain_voucher_invoice_revenue_compare', line:'13416', desc:'主营业务收入 vs 销项发票金额 vs 银行入账三源对比 · 偏差>20%→收入确认存疑 · 趋势对比（月度/季度）'},
      {name:'利润现金流矛盾检测', fn:'_domain_profit_cashflow_gap', line:'14268', desc:'账面利润 vs 经营现金流背离 · 利润正/现金流负→利润质量存疑 · 应收激增伴随现金枯竭→可能虚增收入'},
      {name:'收入时间线调查', fn:'_domain_revenue_timeline', line:'13500', desc:'收入月度波动异常检测 · 开票vs银行入账月度错配 · 年末突击开票 · 季度末/月末集中确认收入'},
      {name:'扩展审查规则', fn:'_domain_advanced_rules', line:'13392', desc:'大额整数交易 · 周末交易 · 购销品名匹配度 · 发票连号检测 · 人均效能 · 发票备注栏合规 · 供应商名称异常'},
    ]},
    // ══════ 五、经营实质分析（3域） ══════
    {cat:'五、经营实质分析', color:'#059669', desc:'验证企业是否具备真实经营条件——有无费用/场地/仓储/运输/人员。空壳企业最怕经营实质分析——没有经营痕迹却有大量开票。', items:[
      {name:'经营实质分析', fn:'_domain_business_substance', line:'12618', desc:'7维度综合评估——①基础费用6要素（租金/水电/物业/办公/通讯/交通）②购销弹性分析 ③人均产值 ④资金沉淀率 ⑤固定资产折旧缺失 ⑥服务行业适应性闸门 ⑦综合预警评分'},
      {name:'经营实质地理分析', fn:'_domain_business_premise_geo', line:'14158', desc:'供应商/客户/加工商地址三角验真 · 跨省重物运输成本推算 · 无物流发票→运输真实性存疑 · 点→面推理全链条经营实质'},
      {name:'人员与业务匹配', fn:'_domain_workforce_profiling', line:'13894', desc:'人均营收vs行业均值 · 人均薪资合理性 · 工资增长率vs收入增长率 · 社保人数vs工资人数一致性 · 员工规模vs业务量匹配'},
    ]},
    // ══════ 六、资料完备度 ══════
    {cat:'六、资料完备度与情报', color:'#2563eb', desc:'14类税务合规必查资料逐一检测，合同需求四层自动分层。资料情报自动分类并统计收款结构/付款方/发票模式。缺失资料→风险标记→无法支撑结论时标注资料缺口。', items:[
      {name:'资料完备度评估', fn:'_domain_document_completeness', line:'12798', desc:'14类税务合规必查资料逐项检测 · 合同需求四层分层（必签/应签/可免/小额）· 缺失资料后果列明 · 综合资料完备度评分'},
      {name:'资料情报摘要', fn:'_extract_material_intel', line:'16992', desc:'银行收款类型自适应分类 · 付款方企业/个人/税务/银行占比 · 进销发票结构 · 凭证收入成本费用汇总 · 大额交易(>50万)识别'},
    ]},
    // ══════ 七、发票分析（3域） ══════
    {cat:'七、发票深度分析', color:'#0891b2', desc:'发票多维特征分析——时间/金额/税率/红冲/作废/连续性/服务vs货物占比。每一张发票都是税务合规线索，发票异常模式能暴露系统性风险。', items:[
      {name:'发票深度特征', fn:'_domain_invoice_deep', line:'12763', desc:'服务类发票占比（服务行业特征判断）· 普票vs专票占比 · 开具时间分布 · 价格区间集中度 · 金额尾数分析 · 顶额开票检测'},
      {name:'发票生命周期', fn:'_domain_invoice_lifecycle', line:'12576', desc:'未认证占比统计 · 超期未认证预警 · 税率异常检测（同一品名不同税率）· 发票类型分布 · 红冲/作废率趋势'},
      {name:'红冲作废发票追踪', fn:'_domain_red_void_invoice', line:'14244', desc:'红冲率+作废率+时间集中度模式+金额集中度 · 月末/季末突击红冲作废 · 同一对方频繁红冲→异常交易关系'},
    ]},
    // ══════ 八、合同与凭证（2域） ══════
    {cat:'八、合同与凭证', color:'#16233a', desc:'合同流与发票流/资金流比对；凭证规范性、科目使用、借贷平衡检查。凭证是财务数据的原子单元。', items:[
      {name:'合同比对分析', fn:'_domain_contract_comparison', line:'12592', desc:'发票客户vs合同当事方一致性 · 合同金额vs发票金额偏差 · 合同覆盖度评估 · 无合同大额交易风险标注'},
      {name:'凭证科目异常', fn:'_domain_voucher_anomaly', line:'12320', desc:'科目使用合规性检查 · 借贷方向正确性 · 分录借贷平衡 · 异常科目组合检测 · 凭证号连续性验证'},
    ]},
    // ══════ 九、税务与社保（3域） ══════
    {cat:'九、税务与社保', color:'#065f46', desc:'各税种申报数据与发票/银行数据交叉比对，社保与工资数据一致性验证。申报表与基础数据的偏差是偷漏税的直接证据。', items:[
      {name:'税务缴纳一致性', fn:'_domain_tax_consistency', line:'12524', desc:'银行税费支出vs发票推算应纳税额差异 · 申报表vs实际数据偏差 · 税种覆盖完整性检查'},
      {name:'增值税申报比对', fn:'_domain_vat_declaration_compare', line:'14569', desc:'进项发票vs认证抵扣vs申报进项三方比对 · 销项vs申报 · 差异>1000元→预警 · 期末留抵税额验证'},
      {name:'工资社保比对', fn:'_domain_salary_ss_hf_compare', line:'12546', desc:'工资表vs社保明细交叉验证——缴费基数匹配 · 参保人数一致 · 单位/个人缴纳比例合规 · 公积金缴存一致性'},
    ]},
    // ══════ 十、资产与关联交易（2域） ══════
    {cat:'十、资产与关联交易', color:'#047857', desc:'固定资产折旧匹配、关联交易穿透、资产损失核实。关联交易未披露是利润转移和资产掏空的常见手法。', items:[
      {name:'资产折旧费用匹配', fn:'_domain_depreciation_match', line:'14373', desc:'固定资产采购vs累计折旧匹配 · 有资产无折旧→利润虚增 · 折旧年限合理性 · 资产减值与处置核实'},
      {name:'关联交易穿透检测', fn:'_domain_related_party_check', line:'14339', desc:'名称相似度比对 · 同法人代表 · 同注册地 · 同联系电话→关联关系未披露 · 买卖双方重叠（同名对倒）'},
    ]},
    // ══════ 十一、行业对标与规则系统（4域） ══════
    {cat:'十一、行业对标与规则系统', color:'#6366f1', desc:"{{industries}}行业基准库对标，{{rules_count}}条规则全覆盖验证。行业对标告诉你“正常范围”，规则系统告诉你“合规底线”。", items:[
      {name:'行业对标分析', fn:'_domain_industry_benchmark', line:'14475', desc:'行业基准库（持续建设中）——毛利率/税负率/进销比/人均营收/费用率五维对标 · 偏离度>2σ→行业异常预警 · 自动匹配行业代码'},
      {name:'规则全覆盖验证', fn:'_domain_rule_coverage', line:'15114', desc:'{{rules_count}}条规则逐条检查 · 已触发vs未触发分类 · 未触发→标注资料缺口 · 数据不足时作无依据结论（不作无证据判断）'},
      {name:'跨域关联推理', fn:'_domain_cross_domain_reasoning', line:'13490', desc:'单点发现→多域交叉印证→证据链闭环 · 7条内置跨域证据链（JSON驱动+内置回退）· A域+B域+C域同时异常→高置信度'},
      {name:'跨域线索链', fn:'_domain_cross_domain_clues', line:'14000', desc:'从cross_domain_clues.json加载跨域线索定义 · 线索→发现→证据三级转换 · 叙事生成器集成 · 线索链可视化追溯'},
    ]},
    // ══════ 十二、跨域分析链 ══════
    {cat:'十二、跨域分析链', color:'#8b5cf6', desc:'跨域分析链是最上层的推理系统——它不直接分析数据，而是基于所有域的发现结果进行二阶推理，从交叉异常中推导出更深层的税务合规结论。', items:[
      {name:'跨域分析链', fn:'_domain_cross_domain_analysis', line:'14080', desc:'从cross_domain_analysis.json加载分析路径 · 二阶推理系统——基于域发现而非原始数据 · 多域异常→综合结论 · 因果链追溯'},
    ]},
    // ══════ 十三、补充税种检查（3域） ══════
    {cat:'十三、补充税种检查', color:'#f97316', desc:'2026-06-30新增：印花税合规检查、企业所得税汇算清缴基础分析、出口退税验证。补充传统税务审计中常见但前期域分析未覆盖的税种检查。', items:[
      {name:'印花税检查', fn:'_domain_stamp_duty_check', line:'12042', desc:'购销合同印花税推算（发票金额×0.03%）· 营业账簿贴花检查 · 借款合同印花税检测 · 偏差>50%预警'},
      {name:'CIT汇算清缴', fn:'_domain_cit_reconciliation', line:'12130', desc:'收入确认差异（发票vs凭证）· 大额无票采购支出（税前不得扣除）· 业务招待费扣除限额（60%与5‰孰低）· 折旧税会差异'},
      {name:'出口退税验证', fn:'_domain_export_vat_verification', line:'12221', desc:'出口收入自动识别 · 退税额推算（13%）· 银行退税入账匹配 · 偏差>30%预警'},
    ]},

  ];

  domainGroups.forEach(function(g) {
    html += '<div style="margin-bottom:10px">'
      + '<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:6px">'
      + '<span style="width:3px;height:14px;display:inline-block;background:' + g.color + ';border-radius:2px"></span>'
      + '<span style="font-size:10px;font-weight:700;color:#16233a">' + escHtml(g.cat) + '</span>'
      + '</div>'
      + '<div style="font-size:10px;color:#64748b;margin:0 0 10px 0;line-height:20px">' + escHtml(g.desc) + '</div>';

    g.items.forEach(function(d) {
      html += '<div style="padding:10px 12px 10px 0;margin-bottom:4px;border-left:3px solid ' + g.color + ';background:#fff;border:1px solid #e2e8f0;border-left-width:3px;border-radius:6px">'
        + '<div style="display:flex;align-items:baseline;justify-content:space-between;margin-bottom:4px">'
        + '<div style="font-size:10px;font-weight:600;color:#16233a">' + escHtml(d.name) + '</div>'
        + '<div style="font-size:10px;color:#64748b">' + escHtml(d.fn) + '() · 行' + d.line + '</div>'
        + '</div>'
        + '<div style="font-size:10px;color:#64748b;line-height:20px">' + escHtml(d.desc) + '</div>'
        + '</div>';
    });

    html += '</div>';
  });

  html += '</div>';

  // ══════ 四、域间关系 ══════
  html += '<div style="margin-bottom:10px;padding:20px 24px;background:#fff;border-radius:8px">'
    + '<h3 style="font-size:10px;font-weight:700;color:#16233a;margin:0 0 10px">四、域间关系与数据流</h3>'
    + '<div style="font-size:10px;color:#3a4048;line-height:20px">'
    + '<strong>资料完备度</strong>（顶层）→ 决定所有域分析的置信度上限。缺合同→合同比对无法运行→标记缺口。<br>'
    + '<strong>经营实质分析</strong>（基础层）→ 提供企业画像：制造业/贸易型/服务型、本地/跨省、自加工/外包。<br>'
    + '<strong>发票+银行+凭证</strong>（数据层）→ 三大主数据源，支撑进销存、资金流、税务、薪酬、资产等15个分析域。<br>'
    + '<strong>多源交叉验证</strong>（交叉层）→ 将单个域的发现两两比对、三向检验，发现孤立点无法发现的隐藏关联。<br>'
    + '<strong>行业对标+规则系统</strong>（校验层）→ 将企业数据与{{industries}}行业基准对比，与' + pc('rules','1608') + '条规则逐一匹配。<br>'
    + '<strong>跨域关联推理</strong>（顶层）→ 将以上所有发现串联为10条跨域证据链，形成最终税务合规结论。'
    + '</div>'
    + '</div>';

  return html;
}

async function loadDomainAnalysisData() {
  var target = document.getElementById('da-analysis-result');
  if (!target) return;
  try {
    var data = await getSharedAnalysis();
    if (!data.ok) {
      target.innerHTML = '<div style="padding:48px 0;font-size:10px;color:#64748b">暂无分析结果，请先运行一键稽查</div>';
      return;
    }
    _cachedDomainReport = data.report;
    renderDomainAnalysisResult(data.report);
  } catch (e) {
    target.innerHTML = '<div style="padding:48px 0;font-size:10px;color:#64748b">加载失败</div>';
  }
}

function renderDomainAnalysisResult(report) {
  var target = document.getElementById('da-analysis-result');
  if (!target) return;
  var ds = report.domain_summary || [];
  var allF = report.all_findings || [];

  var domainMap = {};
  ds.forEach(function(d) {
    domainMap[d.name] = { count: d.count, high: d.high, mid: d.mid, findings: d.findings || [] };
  });

  var domainNames = Object.keys(domainMap).sort(function(a, b) {
    return (domainMap[b].high * 3 + domainMap[b].mid * 2 + domainMap[b].count) - (domainMap[a].high * 3 + domainMap[a].mid * 2 + domainMap[a].count);
  });

  var totalDomains = domainNames.length;
  var triggeredDomains = domainNames.filter(function(n) { return domainMap[n].count > 0; }).length;
  var highTotal = allF.filter(function(f) { return f.level === '极高风险' || f.level === '高风险'; }).length;
  var midTotal = allF.filter(function(f) { return f.level === '中风险'; }).length;

  var html = '<div id="da-result">'
    + '<h3 style="font-size:10px;font-weight:700;color:#16233a;margin:0 0 6px;display:flex;align-items:center;justify-content:space-between">'
    + '<span>四、本次域分析结果</span>'
    + '<span style="font-size:10px;font-weight:400">'
    + '<a href="#" onclick="expandAllDomains();return false" style="color:#2563eb;margin-right:8px">展开全部</a>'
    + '<a href="#" onclick="collapseAllDomains();return false" style="color:#64748b">收起全部</a>'
    + '</span></h3>'
    + '<p style="font-size:10px;color:#64748b;margin:0 0 10px">共 ' + totalDomains + ' 个分析域执行完毕，' + triggeredDomains + ' 个域产生发现，合计 ' + allF.length + ' 条发现（高风险 ' + highTotal + ' · 中风险 ' + midTotal + '）</p>'

    // 统计卡片
    + '<div style="display:flex;gap:12px;margin-bottom:10px">'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:10px;font-weight:700;color:#16233a">' + totalDomains + '</div><div style="font-size:10px;color:#64748b;margin-top:4px">分析域</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:10px;font-weight:700;color:#2563eb">' + triggeredDomains + '</div><div style="font-size:10px;color:#64748b;margin-top:4px">已触发</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:10px;font-weight:700;color:#dc2626">' + highTotal + '</div><div style="font-size:10px;color:#64748b;margin-top:4px">高风险</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fffbeb;border-radius:8px"><div style="font-size:10px;font-weight:700;color:#f59e0b">' + midTotal + '</div><div style="font-size:10px;color:#64748b;margin-top:4px">中风险</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:10px;font-weight:700;color:#16233a">' + allF.length + '</div><div style="font-size:10px;color:#64748b;margin-top:4px">合计发现</div></div>'
    + '</div>'

    + '<h4 style="font-size:10px;font-weight:600;color:#64748b;margin:0 0 10px">域概览（按风险权重排序）</h4>';

  if (domainNames.length === 0) {
    html += '<div style="color:#64748b;font-size:10px;padding:24px 0">无域分析数据</div>';
  } else {
    domainNames.forEach(function(name, di) {
      var d = domainMap[name];
      var hasFindings = d.count > 0;
      var riskLabel = d.high > 0 ? '高风险' : (d.mid > 0 ? '中风险' : (hasFindings ? '信息' : '未触发'));
      var riskColor = d.high > 0 ? '#dc2626' : (d.mid > 0 ? '#f59e0b' : (hasFindings ? '#22c55e' : '#64748b'));

      html += '<div style="border-bottom:1px solid #f1f5f9;padding:12px 0;cursor:' + (hasFindings ? 'pointer' : 'default') + '" onclick="' + (hasFindings ? 'toggleDomainDetail(' + di + ')' : '') + '">'
        + '<div style="display:flex;align-items:center;justify-content:space-between">'
        + '<div style="display:flex;align-items:center;gap:10px">'
        + '<span style="font-size:10px;font-weight:600;color:#16233a">' + escHtml(name) + '</span>'
        + '<span style="font-size:10px;padding:1px 6px;border-radius:3px;background:' + riskColor + '10;color:' + riskColor + ';font-weight:600">' + riskLabel + '</span>'
        + '</div>'
        + '<div style="display:flex;gap:16px;font-size:10px;color:#64748b">'
        + '<span>发现 <b style="color:#16233a">' + d.count + '</b></span>'
        + (d.high > 0 ? '<span style="color:#dc2626;font-weight:600">高' + d.high + '</span>' : '')
        + (d.mid > 0 ? '<span style="color:#f59e0b;font-weight:600">中' + d.mid + '</span>' : '')
        + (hasFindings ? '<span style="color:#64748b;font-size:10px">▸</span>' : '')
        + '</div>'
        + '</div>';

      // 展开的发现详情
      if (hasFindings) {
        html += '<div id="dd-' + di + '" style="display:none;margin-top:12px;padding:12px 16px;background:#fff;border-radius:6px">';
        d.findings.forEach(function(f) {
          var lvlColor = f.level === '极高风险' || f.level === '高风险' ? '#dc2626' : (f.level === '中风险' ? '#f59e0b' : '#22c55e');
          var lvlBg = f.level === '极高风险' || f.level === '高风险' ? '#fef2f2' : (f.level === '中风险' ? '#fffbeb' : '#f0fdf4');
          var dt = typeof f.detail === 'object' && f.detail.summary ? f.detail.summary : (f.detail || '');
          var trace = f._trace || {};
          html += '<div style="padding:10px 12px;margin-bottom:6px;background:' + lvlBg + ';border-radius:6px;border-left:3px solid ' + lvlColor + '">'
            + '<div style="font-size:10px;font-weight:600;color:#16233a;margin-bottom:4px">' + escHtml(f.type || '') + '</div>'
            + '<div style="font-size:10px;color:#3a4048;line-height:20px;margin-bottom:4px"><span class="d-find-detail" data-full="' + escHtml(dt).replace(/"/g, '&quot;') + '">' + escHtml(dt.substring(0, 300)) + '</span>'
            + (dt.length > 300 ? ' <a href="#" onclick="var s=this.previousElementSibling;s.textContent=s.getAttribute(\'data-full\');this.remove();return false" style="color:#2563eb;font-size:10px">展开全文</a>' : '')
            + '</div>'
            + '<div style="display:flex;gap:8px;align-items:center;font-size:10px;color:#64748b">'
            + '<span style="color:' + lvlColor + ';font-weight:600">' + (f.level || '') + '</span>'
            + '<span>score:' + (f.score || '-') + '</span>'
            + (f.rule_id ? '<span>规则:' + f.rule_id + '</span>' : '')
            + '</div>';
          // 自动内联推理链路——每条结论自带追责
          if (trace && trace.finding_id) {
            var pathText = (trace.detection_path||[]).join(' → ');
            var confColor = trace.confidence === '高' ? '#059669' : '#f59e0b';
            html += '<div style="margin-top:6px;padding:6px 8px;background:rgba(59,130,246,0.06);border-radius:4px;font-size:10px;color:#64748b;line-height:20px">'
              + '<span>📋 ' + escHtml(trace.phase_origin||'') + '</span>'
              + '<span style="margin-left:8px;color:' + confColor + '">可信度:' + escHtml(trace.confidence||'?') + '</span>'
              + '<span style="margin-left:8px">| 来源:' + escHtml((trace.data_sources||[]).slice(0,4).join('、')) + '</span>'
              + '<span style="margin-left:8px">| 规则:<code style="font-size:10px">' + escHtml((trace.rules_hit||[]).slice(0,3).join(',')) + '</code></span>'
              + '<br><span style="color:#64748b">' + escHtml(pathText) + '</span>'
              + '</div>';
          }
          html += '</div>';
        });
        html += '</div>';
      }

      html += '</div>';
    });
  }

  html += '</div>'; // da-result
  target.innerHTML = html;
}

// ==================== 页面3：跨域证据链 ====================

function loadCrossDomainStatic() {
  var target = document.getElementById('cde-static');
  fetch('/static/cross_domain_evidence.json?_t=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(chains) {
      window._allCrossChains = chains;
      renderCrossDomainStaticContent(chains);
    })
    .catch(function() {
      if (target) target.innerHTML = '<div style="padding:40px 0;font-size:10px;color:#64748b">跨域证据链定义加载失败</div>';
    });
}


function loadCrossDomainDynamic() {
  var target = document.getElementById('cde-dynamic');
  if (!target) return;

  getSharedAnalysis()
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (!data.ok) {
        target.innerHTML = '<div style="text-align:center;padding:20px;color:#64748b;margin-top:20px">暂无分析结果，请先运行一键稽查以获取动态证据链数据</div>';
        return;
      }
      renderCrossDomainDynamic(data.report);
    })
    .catch(function(e) {
      target.innerHTML = '<div style="text-align:center;padding:20px;color:#64748b;margin-top:20px">动态数据加载失败</div>';
    });
}



// ==================== 全局变量（供线索链/证据链页面共享） ====================
var _cachedDomainReport = null;
var _cachedFileParsingReport = null;
var _cachedFilterReport = null;
var _cachedAnalyzeReport = null;
var _allChains = [];
var _chainDynamic = null;
var _allClueChains = [];
var _allEvidenceChains = [];
var _allCrossChains = null;

// ==================== 页面：线索链 ====================
function renderChainsPage(container) {
  if (!container) return;
  window.currentModule = '线索链';
  window._skipModuleHeader = true;

  var h = '';
  h += '<style>'
    + '.cl{max-width:900px;margin:0 auto;padding:20px 28px;font-family:-apple-system,"Microsoft YaHei",sans-serif}'
    + '.cl-sub{font-size:10px;color:#64748b;margin:0 0 16px;line-height:1.8}'
    + '.cl-chain{padding:10px 0;margin-bottom:10px;border-bottom:1px solid #eef2f6}'
    + '</style>';

  h += '<div class="cl">';
  h += '<div id="chains-body"></div>';
  h += '</div>';
  container.innerHTML = h;
  _allClueChains = null;
  setTimeout(function(){ loadChainsData(); }, 50);
}

async function loadChainsData() {
  var target = document.getElementById('chains-body');
  try {
    var resp = await fetch('/static/cross_domain_clues.json?_t=' + Date.now());
    var clueChains = await resp.json();

    // 加载动态触发状态
    await loadChainDynamicStatus();

    _allClueChains = clueChains;
    renderChainsList(clueChains);
  } catch (e) {
    if (target) target.innerHTML = '<div style="text-align:center;padding:20px;color:#dc2626">加载失败: ' + e.message + '</div>';
  }
}

async function loadChainDynamicStatus() {
  try {
    var data = await getSharedAnalysis();
    if (data.ok && data.report) {
      var comp = data.report.comprehensive || {};
      _chainDynamic = {
        chain_execution: comp.chain_execution || [],
        evidence_closures: comp.evidence_closures || [],
        closed_count: comp.closed_chain_count || 0,
        triggered_count: comp.chain_triggered_count || 0
      };
    } else {
      _chainDynamic = { chain_execution: [], evidence_closures: [], closed_count: 0, triggered_count: 0 };
    }
  } catch(e) { _chainDynamic = { chain_execution: [], evidence_closures: [], closed_count: 0, triggered_count: 0 }; }
}

function renderChainsList(chains) {
  var target = document.getElementById('chains-body');
  if (!target) return;
  var esc = typeof escHtml === 'function' ? escHtml : function(s){ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;'); };
  var html = '<div style="font-size:10px;line-height:2.2">';
  chains.forEach(function(c,ci){
    var steps = (c.investigation_path||[]).length;
    var cat = c.category||'';
    var cid = 'clue-' + ci;
    html += '<div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid #f1f5f9;cursor:pointer" onclick="var d=document.getElementById(\''+cid+'\');d.style.display=d.style.display===\'none\'?\'\':\'none\'">';
    html += '<span style="color:#94a3b8;min-width:24px">#'+(ci+1)+'</span>';
    html += '<span style="flex:1;color:#0f172a">'+esc(c.name||'')+'</span>';
    html += '<span style="color:#64748b;font-size:9px">'+esc(cat)+'</span>';
    html += '<span style="color:#94a3b8;font-size:9px">'+steps+'步</span>';
    html += '<span style="color:#94a3b8">\u25b8</span>';
    html += '</div>';
    html += '<div id="'+cid+'" style="display:none;padding:10px 0 10px 24px;font-size:10px;line-height:1.8;color:#475569">';
    if(c.description) html += '<div style="margin-bottom:10px;color:#64748b">'+esc(c.description)+'</div>';
    if(c.trigger_keywords) html += '<div style="margin-bottom:6px"><b>触发关键词:</b> '+(c.trigger_keywords||[]).join('、')+'</div>';
    if(c.investigation_path&&c.investigation_path.length){
      html += '<div style="margin-bottom:6px"><b>调查路径 ('+c.investigation_path.length+'步):</b></div>';
      c.investigation_path.forEach(function(s,si){
        var stepName = s.name||s.step||'步骤'+(si+1);
        var stepDesc = s.description||s.desc||s.action||'';
        html += '<div style="padding:4px 0">'+(si+1)+'. '+esc(stepName)+'：'+esc(stepDesc)+'</div>';
      });
    }
    if(c.suggestion) html += '<div style="margin-top:8px;color:#94a3b8">'+esc(c.suggestion)+'</div>';
    html += '</div>';
  });
  html += '</div>';
  target.innerHTML = html;
}function renderEvidenceList(chains) {
  var target = document.getElementById('evidence-body');
  if (!target) return;
  var esc = typeof escHtml === 'function' ? escHtml : function(s){ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;'); };
  var html = '<div style="font-size:10px;line-height:2.2">';
  chains.forEach(function(c,ci){
    var dims = (c.dimensions||[]).length;
    var cat = c.category||'';
    var cid = 'evid-' + ci;
    html += '<div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid #f1f5f9;cursor:pointer" onclick="var d=document.getElementById(\''+cid+'\');d.style.display=d.style.display===\'none\'?\'\':\'none\'">';
    html += '<span style="color:#94a3b8;min-width:24px">#'+(ci+1)+'</span>';
    html += '<span style="flex:1;color:#0f172a">'+esc(c.name||'')+'</span>';
    html += '<span style="color:#64748b;font-size:9px">'+esc(cat)+'</span>';
    html += '<span style="color:#94a3b8;font-size:9px">'+(c.min_evidence||'?')+'源\u00d7'+dims+'维</span>';
    html += '<span style="color:#94a3b8">\u25b8</span>';
    html += '</div>';
    html += '<div id="'+cid+'" style="display:none;padding:10px 0 10px 24px;font-size:10px;line-height:1.8;color:#475569">';
    if(c.description) html += '<div style="margin-bottom:10px;color:#64748b">'+esc(c.description)+'</div>';
    html += '<div style="margin-bottom:6px"><b>要求\u2265</b> '+c.min_evidence+' <b>个独立数据源同时匹配</b> | '+(c.dimensions||[]).length+' <b>个验证维度</b></div>';
    if(c.dimensions&&c.dimensions.length){
      html += '<div style="margin-bottom:6px"><b>验证维度:</b></div>';
      c.dimensions.forEach(function(d){
        html += '<div style="padding:2px 0">\u00b7 '+esc(d)+'</div>';
      });
    }
    if(c.trigger_keywords) html += '<div style="margin-top:6px"><b>触发关键词:</b> '+(c.trigger_keywords||[]).join('、')+'</div>';
    if(c.suggestion) html += '<div style="margin-top:8px;color:#94a3b8">'+esc(c.suggestion)+'</div>';
    html += '</div>';
  });
  html += '</div>';
  target.innerHTML = html;
}    var esc2 = typeof escHtml === 'function' ? escHtml : function(s){ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;'); };
    var html = '<div style="font-size:10px;line-height:2.2">';
    chains.forEach(function(chain,ci){
      var steps = (chain.reasoning_path||[]).length;
      var cat = chain.category||'';
      var cid = 'alc-' + ci;
      html += '<div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid #f1f5f9;cursor:pointer" onclick="var d=document.getElementById(\''+cid+'\');d.style.display=d.style.display===\'none\'?\'\':\'none\'">';
      html += '<span style="color:#94a3b8;min-width:24px">#'+(ci+1)+'</span>';
      html += '<span style="flex:1;color:#0f172a">'+esc(chain.name||'')+'</span>';
      html += '<span style="color:#64748b;font-size:9px">'+esc(cat)+'</span>';
      html += '<span style="color:#94a3b8;font-size:9px">'+steps+'步</span>';
      html += '<span style="color:#94a3b8">\u25b8</span>';
      html += '</div>';
      html += '<div id="'+cid+'" style="display:none;padding:10px 0 10px 24px;font-size:10px;line-height:1.8;color:#475569">';
      if(chain.description) html += '<div style="margin-bottom:10px;color:#64748b">'+esc(chain.description)+'</div>';
      if(chain.reasoning_path&&chain.reasoning_path.length){
        html += '<div style="margin-bottom:6px"><b>推理路径 ('+chain.reasoning_path.length+'步):</b></div>';
        chain.reasoning_path.forEach(function(s,si){
          html += '<div style="padding:4px 0">'+(si+1)+'. <b>'+esc(s.cross||'')+'</b> \u2192 '+esc(s.action||'')+'</div>';
          if(s.evidence_required) html += '<div style="padding-left:16px;color:#94a3b8;font-size:9px">证据: '+esc(s.evidence_required)+'</div>';
        });
      }
      if(chain.suggestion) html += '<div style="margin-top:8px;color:#94a3b8">'+esc(chain.suggestion)+'</div>';
      html += '</div>';
    });
    html += '</div>';
    if(target) target.innerHTML = html;
//  税务合规管道独立页：文件解析 | 域分析 | 跨域证据链 | 方法论过滤器
// ══════════════════════════════════════════════════════════════

// ═══════════ 模块数量自动加载（从JSON数据文件动态读取，杜绝硬编码过期数字） ═══════════
var _pipelineCounts = null;

async function loadPipelineCounts() {
  if (_pipelineCounts) return _pipelineCounts;
  try {
    var t0 = Date.now();
    var [rulesResp, cdcResp, cdeResp, cdaResp] = await Promise.all([
      fetch('/static/tax_risk_rules_local_export.json?_t=' + t0),
      fetch('/static/cross_domain_clues.json?_t=' + t0),
      fetch('/static/cross_domain_evidence.json?_t=' + t0),
      fetch('/static/cross_domain_analysis.json?_t=' + t0)
    ]);
    var rules = await rulesResp.json();
    var cdc = await cdcResp.json();
    var cde = await cdeResp.json();
    var cda = await cdaResp.json();
    _pipelineCounts = {
      rules: rules.length,
      trailChains: cdc.length,
      evidenceChains: cde.length,
      analysisChains: cda.length,
      totalChains: cdc.length + cde.length + cda.length,
      crossEvidence: cde.length,
      crossClues: cdc.length,
      crossAnalysis: cda.length
    };
    console.log('[pipeline counts] loaded:', _pipelineCounts);
  } catch(e) {
    console.error('[pipeline counts] failed:', e);
    // 从 system_config.json 读取权威值
  }
  // 如果 system_config 已加载，用它覆盖（权威数据源）
  if (window._systemConfig) {
    _pipelineCounts.rules = window._systemConfig.rules_count || _pipelineCounts.rules;
    _pipelineCounts.trailChains = window._systemConfig.clue_chains || _pipelineCounts.trailChains;
    _pipelineCounts.evidenceChains = window._systemConfig.evidence_chains || _pipelineCounts.evidenceChains;
    _pipelineCounts.analysisChains = window._systemConfig.analysis_chains || _pipelineCounts.analysisChains;
    _pipelineCounts.totalChains = window._systemConfig.total_chains || _pipelineCounts.totalChains;
  }
  return _pipelineCounts;
}

// 快捷取值：优先从 _pipelineCounts，回退到 system_config
function pc(key, fallback) {
  if (_pipelineCounts && _pipelineCounts[key] != null) return _pipelineCounts[key];
  if (window._systemConfig) {
    var m = {rules:'rules_count',trailChains:'clue_chains',evidenceChains:'evidence_chains',analysisChains:'analysis_chains',totalChains:'total_chains'};
    if (m[key] && window._systemConfig[m[key]]) return window._systemConfig[m[key]];
  }
  return fallback || '...';
}

// ═══════════ API共享缓存（消除6模块重复请求同一API） ═══════════
var _analysisCacheData = null;
var _analysisCachePromise = null;

function getSharedAnalysis() {
  if (_analysisCacheData) return Promise.resolve(_analysisCacheData);
  if (_analysisCachePromise) return _analysisCachePromise;
  var cid = typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1;
  _analysisCachePromise = fetch('/api/tax-risk-docs/last-analysis?company_id=' + cid)
    .then(function(r) { return r.json(); })
    .then(function(data) {
      _analysisCacheData = data;
      _analysisCachePromise = null;
      return data;
    })
    .catch(function(e) {
      _analysisCachePromise = null;
      throw e;
    });
  return _analysisCachePromise;
}

// ═══════════ 页面1：文件解析（极简风） ═══════════
function renderFileParsingPage(container) {
  if (!container) return;
  window.currentModule = '文件解析';
  container.innerHTML = '<style>.fp-layout{display:flex;gap:24px;max-width:1200px;margin:0 auto;padding:40px 46px;background:#fff}.fp-toc{width:190px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:10px;line-height:20px;max-height:calc(100vh-40px);overflow-y:auto}.fp-toc .toc-title{font-weight:700;color:#16233a;font-size:10px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.fp-toc a{display:block;color:#3a4048;text-decoration:none;padding:2px 8px;border-radius:4px;cursor:pointer}.fp-toc a:hover,.fp-toc a.active{background:#eff6ff;color:#2563eb;font-weight:600}.fp-main{flex:1;min-width:0;background:#fff;line-height:1.6}.fp-main p,.fp-main div,.fp-main li{margin-bottom:10px}.fp-main h3{font-size:10px!important;font-weight:700!important;color:#16233a!important;padding-bottom:8px!important;border-bottom:2px solid #e2e8f0!important;margin:0 0 10px!important}.fp-main .fp-step{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:20px 22px;transition:box-shadow 0.15s}.fp-main .fp-step:hover{box-shadow:0 2px 8px rgba(0,0,0,.06)}.fp-main details summary:hover{background:#f8fafc}.fp-main .fp-card{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:20px 22px;transition:box-shadow 0.15s}.fp-main .fp-card:hover{box-shadow:0 2px 8px rgba(0,0,0,.06)}.fp-main .fp-stat-card{background:#fff;border:1px solid #e2e8f0;border-radius:8px;text-align:center;padding:16px}.fp-main section{margin-bottom:10px!important;scroll-margin-top:20px}</style>'
    + '<div class="fp-layout">'
    + '<nav class="fp-toc"><div class="toc-title">📖 导航</div>'
    + '<a href="#fp-mechanism">一 识别机制</a>'
    + '<a href="#fp-compat">二 兼容策略</a>'
    + '<a href="#fp-formats">三 格式扩展</a>'
    + '<a href="#fp-fingerprint">四 文件指纹库</a>'
    + '<a href="#fp-flow">五 解析流程</a>'
    + '<a href="#fp-result">六 本次解析结果</a>'
    + '</nav>'
    + '<div class="fp-main">'
    + '<h2 style="font-size:10px;font-weight:800;color:#16233a;margin:0 0 10px">📁 文件解析</h2>'
    + '<p style="font-size:10px;color:#64748b;margin:0 0 10px">{{file_fingerprints}}类文件指纹 · 三层递进识别 · 四方交叉验证 · 8种格式全兼容 · OCR扫描件解析 · 关键词打分 · 结构分析 · 数据推断兜底</p>'
        + '<div style="background:#fff;border:1px solid #e2e8f0;padding:20px 24px;border-radius:8px;margin-bottom:10px">'
    + '<p style="font-size:10px;color:#3a4048;line-height:20px;margin:0">'
    + '文件解析系统是税务合规分析的第一步——将企业上传的各种格式的原始资料（Excel/PDF/CSV/Word/图片），'
    + '通过{{file_fingerprints}}类文件指纹 + 四层递进识别 + 四方交叉验证，自动判定文件类型并提取为结构化数据。'
    + '支持多种文件格式（xls/xlsx/csv/pdf/docx/jpg/png/tiff），兼容各类列名变体，'
    + '采用自适应表头检测（不预设表头在第几行）和汇总行自动过滤，确保数据质量。'
    + '</p>'
    + '</div>'

+ '<div id="fp-static"></div>'
    + '<div id="fp-analysis-result"></div>'
    + '</div></div>';
  renderFileParsingStatic();
  if (_cachedFileParsingReport) { renderFileParsingResult(_cachedFileParsingReport); }
  else { loadFileParsingData(); }
  // 侧边栏子模块入口
  if (window._fpSection) {
    var sec = window._fpSection;
    window._fpSection = null;
    if (sec === 'fp-result') { window._pendingFpSlice = 'fp-result'; }
    else {
      // CSS注入隐藏无关内容
      var s = document.createElement('style');
      s.textContent = '.fp-toc{display:none!important}.fp-layout{display:block!important}.fp-main h2,.fp-main>p,.fp-main>div:first-child{display:none!important}#fp-mechanism,#fp-compat,#fp-formats,#fp-fingerprint,#fp-flow,#fp-result{display:none!important}#'+sec+'{display:block!important}';
      container.appendChild(s);
    }
  }
}

function fpSliceToSection(sectionId) {
  var toc = document.querySelector('.fp-toc');
  if (toc) toc.style.display = 'none';
  var layout = document.querySelector('.fp-layout');
  if (layout) layout.style.display = 'block';
  var h2 = document.querySelector('.fp-main h2');
  if (h2) h2.style.display = 'none';
  var p = document.querySelector('.fp-main > p');
  if (p) p.style.display = 'none';
  var overview = document.querySelector('.fp-main > div');
  if (overview && !overview.id) overview.style.display = 'none';
  // Hide/Show target section
  var allSecs = document.querySelectorAll('#fp-mechanism,#fp-compat,#fp-formats,#fp-fingerprint,#fp-flow,#fp-result');
  for (var i = 0; i < allSecs.length; i++) {
    allSecs[i].style.display = allSecs[i].id === sectionId ? 'block' : 'none';
  }
  setTimeout(function() {
    var el = document.getElementById(sectionId);
    if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
  }, 200);
}

function renderFileParsingStatic() {
  var target = document.getElementById('fp-static');
  if (!target) return;

  var fps = fpFingerprints();
  var html = '';

  // ═══════════════════════════════════════════════
  // 一、识别机制：四层递进 + 四方交叉验证
  // ═══════════════════════════════════════════════
  html += '<div id="fp-mechanism" style="margin-bottom:48px">'
    + '<h3>一、识别机制：四层递进 + 四方交叉验证</h3>'
    + '<p style="font-size:10px;color:#3a4048;line-height:20px;margin:0 0 10px">'
    + '系统接收到文件后，不依赖文件扩展名判断（用户上传的 .xls 可能是任何内容），'
    + '而是执行四层递进识别——从粗糙到精细、从单一证据到多方交叉验证，逐步锁定文件真实类型。'
    + '整个过程模拟人类专家的判断逻辑：先看表头关键词 → 再看列结构 → '
    + '再看数据样本 → 最后综合文件名/列头/数据/公司身份四方证据做最终裁决。'
    + '</p>'

    // Step 1
    + '<div class="fp-step" style="margin-bottom:10px;border-left:4px solid #16233a">'
    + '<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">'
    + '<span style="display:inline-flex;align-items:center;justify-content:center;'
    + 'width:28px;height:28px;border-radius:6px;background:#16233a;color:#fff;font-size:10px;font-weight:700">1</span>'
    + '<span style="font-size:10px;font-weight:700;color:#16233a">关键词匹配 \u00b7 打分制</span>'
    + '<span style="font-size:10px;color:#64748b">最高优先级 \u00b7 识别率 ~80%</span>'
    + '</div>'
    + '<div style="font-size:10px;color:#3a4048;line-height:20px">'
    + '<p style="margin:0 0 10px"><strong>执行逻辑：</strong>'
    + '读取 Excel 文件的前200行表头区域（不只是第1行），将表头中的每一个词与{{file_fingerprints}}类文件指纹的关键词库做交叉匹配。'
    + '每命中一个关键词得1分，得分超过该类型指纹的评分阈值（通常2-4分）即判定为该类型。'
    + '多类型同时超过阈值时，取得分最高的类型作为主判定。'
    + '</p>'
    + '<p style="margin:0 0 10px"><strong>实际例子：</strong>'
    + '表头出现 \u201c对方户名\u201d\u201c交易日期\u201d\u201c收入金额\u201d三个词'
    + '\u2192 银行流水指纹得3分 \u2192 \u2265阈值3 \u2192 判定为银行流水。'
    + '表头出现 \u201c发票号码\u201d\u201c开票日期\u201d\u201c金额\u201d\u201c税额\u201d四个词'
    + '\u2192 通用发票指纹得4分 \u2192 \u2265阈值4 \u2192 判定为通用发票。'
    + '</p>'
    + '<p style="margin:0"><strong>边缘情况：</strong>'
    + '当多个类型得分非常接近（相差\u22641分）时，标记为\u201c存疑\u201d，进入结构分析做二次判定。'
    + '关键词库持续迭代——每发现一种新的列名变体，自动补充到对应类型的关键词集中。'
    + '目前银行流水关键词23个、工资表关键词60+个、通用发票关键词20个。'
    + '</p>'
    + '</div>'
    + '</div>'

    // Step 2
    + '<div class="fp-step" style="margin-bottom:10px;border-left:4px solid #64748b">'
    + '<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">'
    + '<span style="display:inline-flex;align-items:center;justify-content:center;'
    + 'width:28px;height:28px;border-radius:6px;background:#64748b;color:#fff;font-size:10px;font-weight:700">2</span>'
    + '<span style="font-size:10px;font-weight:700;color:#16233a">结构分析 \u00b7 列模式匹配</span>'
    + '<span style="font-size:10px;color:#64748b">第二优先级 \u00b7 多类型接近时激活</span>'
    + '</div>'
    + '<div style="font-size:10px;color:#3a4048;line-height:20px">'
    + '<p style="margin:0 0 10px"><strong>激活条件：</strong>'
    + '关键词匹配阶段，前两名得分差距\u22641分，或最高分类型得分恰好等于阈值（临界状态）。'
    + '此时不是简单地\u201c取最高分\u201d，而是进入更深层次的结构分析。'
    + '</p>'
    + '<p style="margin:0 0 10px"><strong>分析方法：</strong>'
    + '系统为每种文件类型维护了一套列模式模板——包括列数范围、关键列的位置、列的排列顺序。'
    + '例如银行流水的列模式模板：日期列(前3列) + 对方户名列(前3-5列) + 金额列(第4-8列) + 余额列(最后1-2列)。'
    + '工资表的列模式模板：姓名列(第1列) + 收入列(第2-5列) + 扣除列(第6-8列) + 实发列(倒数1-2列)。'
    + '</p>'
    + '<p style="margin:0"><strong>容错设计：</strong>'
    + '列位置允许\u00b13列的偏移（不同企业/不同财务软件导出的表头顺序可能不同），'
    + '关键列必须存在但位置可以浮动。模式相似度计算公式：命中列数/模板总列数 \u2265 60% 即匹配。'
    + '例如银行流水模板要求8列关键列，实际命中5列（5/8=62.5%\u226560%）\u2192 匹配成功。'
    + '</p>'
    + '</div>'
    + '</div>'

    // Step 3
    + '<div class="fp-step" style="margin-bottom:10px;border-left:4px solid #64748b">'
    + '<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">'
    + '<span style="display:inline-flex;align-items:center;justify-content:center;'
    + 'width:28px;height:28px;border-radius:6px;background:#64748b;color:#fff;font-size:10px;font-weight:700">3</span>'
    + '<span style="font-size:10px;font-weight:700;color:#16233a">数据推断 \u00b7 逐列语义分类</span>'
    + '<span style="font-size:10px;color:#64748b">兜底机制 \u00b7 绝不丢弃数据</span>'
    + '</div>'
    + '<div style="font-size:10px;color:#3a4048;line-height:20px">'
    + '<p style="margin:0 0 10px"><strong>触发场景：</strong>'
    + '关键词匹配和结构分析都无法确定文件类型时（例如企业自制的非标准表格、极少见的资料类型），'
    + '系统不会拒绝解析或丢弃数据，而是进入数据推断阶段——逐列读取前200行数据样本，'
    + '按每一个单元格的语义角色自动分类。'
    + '</p>'
    + '<p style="margin:0 0 10px"><strong>语义分类规则（5类）：</strong><br>'
    + '\u2192 日期格式（2023-01-01、2023/1/1、2023年1月1日、20230101等）\u2192 日期列<br>'
    + '\u2192 纯数字无明显小数位（整数、序号）\u2192 数量/编号列<br>'
    + '\u2192 含\u201c公司\u201d\u201c有限\u201d\u201c厂\u201d\u201c店\u201d\u201c集团\u201d等企业标识词 \u2192 企业名称列<br>'
    + '\u2192 含\u201c元\u201d\u201c金额\u201d\u201c￥\u201d\u201c¥\u201d\u201c合计\u201d或纯数字含2位小数 \u2192 金额列<br>'
    + '\u2192 含\u201c税\u201d\u201c%\u201d\u201c税率\u201d \u2192 税率列'
    + '</p>'
    + '<p style="margin:0"><strong>兜底输出：</strong>'
    + '数据推断无法确定具体类型时，标注为\u201c通用数据\u201d（generic_data），'
    + '保留完整的原始行列结构，交由下游分析模块（域分析系统/规则匹配系统）自行判断数据用途。'
    + '核心原则：不因无法识别而丢弃任何一行数据。'
    + '</p>'
    + '</div>'
    + '</div>'

    // Step 4
    + '<div class="fp-step" style="margin-bottom:10px;border-left:4px solid #16a34a">'
    + '<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">'
    + '<span style="display:inline-flex;align-items:center;justify-content:center;'
    + 'width:28px;height:28px;border-radius:6px;background:#16a34a;color:#fff;font-size:10px;font-weight:700">4</span>'
    + '<span style="font-size:10px;font-weight:700;color:#16233a">四方交叉验证 \u00b7 最终裁决</span>'
    + '<span style="font-size:10px;color:#64748b">2026-06-28新增 \u00b7 证据冲突时数据优先</span>'
    + '</div>'
    + '<div style="font-size:10px;color:#3a4048;line-height:20px">'
    + '<p style="margin:0 0 10px"><strong>设计目的：</strong>'
    + '前三层都是\u201c文件内部\u201d的推理——仅依据表头和数据本身判断。但有时文件内部的线索可能产生歧义'
    + '（例如一份银行流水表头被改了列名，看起来像费用明细）。四方交叉验证引入\u201c外部证据\u201d——'
    + '包括文件名暗示、公司身份锚定、买卖方关系匹配——从多角度验证前三层的结论。'
    + '</p>'
    + '<p style="margin:0 0 10px"><strong>四方证据：</strong><br>'
    + '\u2460 <strong>文件名暗示</strong>：文件名含\u201c开票\u201d\u201c销项\u201d\u2192倾向销项发票；含\u201c取票\u201d\u201c进项\u201d\u201c抵扣\u201d\u2192倾向进项发票。'
    + '但仅作为参考权重，不直接决定类型——因为文件名可能错误标注。<br>'
    + '\u2461 <strong>列头推理</strong>：前三层的结果，带置信度。不同类型的关键词得分和列模式相似度作为主证据。<br>'
    + '\u2462 <strong>数据扫描（买卖方身份）</strong>：读取数据样本中的企业名称字段，与公司身份做双向比对。'
    + '购方名称=当前公司\u2192进项发票；销方名称=当前公司\u2192销项发票。'
    + '双方都不匹配\u2192存疑排除（可能是其他公司的文件误上传）。<br>'
    + '\u2463 <strong>公司匹配</strong>：通过企业名称和统一社会信用代码双向锚定当前账套的企业身份，'
    + '确保发票方向判定的正确性。'
    + '</p>'
    + '<p style="margin:0"><strong>冲突裁决规则：</strong>'
    + '当四方证据出现矛盾时，优先级：数据扫描（买卖方匹配）> 列头推理（关键词得分）> '
    + '文件名暗示。因为数据不会说谎——如果数据中购方名称=当前公司，那么无论文件名写什么、'
    + '表头怎么命名，这份文件就是进项发票。文件名可能错误标注，表头可能不规范，但数据本身的身份关系是铁证。'
    + '</p>'
    + '</div>'
    + '</div>'
    + '</div>';

  // ═══════════════════════════════════════════════
  // 二、兼容策略（全部34类 + 跨格式）
  // ═══════════════════════════════════════════════
  html += '<div id="fp-compat" style="margin-bottom:48px">'
    + '<h3>二、兼容策略</h3>'
    + '<p style="font-size:10px;color:#3a4048;line-height:20px;margin:0 0 10px">'
    + '企业上传的资料格式千差万别——不同ERP系统、不同财务软件、不同银行导出的表格结构各不相同。'
    + '文件解析模块通过列名映射表（82+变体）和智能自适应机制，兼容主要的命名习惯差异。'
    + '</p>';

  // 各类型兼容详情
  var compatItems = [
    {title:'银行流水', icon:'\u{1f3e7}', detail:'' +
      '<strong>日期列兼容：</strong>交易日期、记账日期、交易时间、日期、申请日期、起息日 共6种。<br>' +
      '<strong>对方户名兼容：</strong>对方户名、交易对方、对方名称、counterparty、对方单位、收款人名称 共6种。<br>' +
      '<strong>金额兼容：</strong>收入金额、支出金额、贷方金额、借方金额、交易金额、发生额 共6种——' +
      '自动去除\u00a5/\u5143/\u9017\u53f7/\u7a7a\u683c等非数字字符。金额符号按借贷方向或交易关键词自动判断。<br>' +
      '<strong>余额兼容：</strong>本次余额、交易余额、账户余额 共3种。<br>' +
      '<strong>汇总行过滤：</strong>自动识别并剔除所有含\u201c小计\u201d\u201c合计\u201d\u201c总计\u201d\u201c本页合计\u201d\u201c本年累计\u201d\u201c当月合计\u201d的行。'},
    {title:'发票', icon:'\u{1f9fe}', detail:'' +
      '<strong>方向自动判定：</strong>购方名称/税号=当前公司\u2192进项发票；销方名称/税号=当前公司\u2192销项发票；双方都不匹配\u2192存疑排除。<br>' +
      '<strong>购买方列名兼容：</strong>购方名称、购买方名称、购方、买方、客户名称、付款方 共6种。<br>' +
      '<strong>销售方列名兼容：</strong>销方名称、销售方名称、销方、卖方、供应商名称、供方名称、收款方 共7种。<br>' +
      '<strong>发票号码兼容：</strong>发票号码、发票号、数电发票号码、票据号码 共4种。<br>' +
      '<strong>税收分类：</strong>货物或应税劳务名称、\u203b品名、商品名称、服务名称、项目名称 共5种——自动按最长子串匹配归类。<br>' +
      '<strong>金额兼容：</strong>金额、不含税金额、含税金额、价税合计、小写金额——自动识别含税/不含税并补齐缺失字段。'},
    {title:'工资表', icon:'\u{1f4b0}', detail:'' +
      '<strong>60+列名变体：</strong>本期收入/应发工资/实发工资/应发合计/实发合计/代扣个税/'
      + '基本养老保险/基本医疗保险/住房公积金/专项扣除/子女教育/赡养老人/基本工资/绩效工资/'
      + '岗位工资/加班工资/交通补贴/通讯补贴/餐补/高温补贴/奖金/年终奖/提成工资等。<br>' +
      '<strong>个税申报格式兼容：</strong>累计收入/累计减除费用/累计专项扣除/累计应纳税额/已预缴税额/应补退税额——'
      + '与工资表自动区分，按关键词集不同走不同解析器。<br>' +
      '<strong>合计行过滤：</strong>自动剔除\u201c合计\u201d\u201c总计\u201d\u201c小计\u201d行，防止重复统计。'},
    {title:'社保/公积金', icon:'\u{1f3e5}', detail:'' +
      '<strong>社保三列数据自动区分：</strong>缴费基数（工资基数/社保基数）、'
      + '单位缴纳（单位缴费/公司缴纳）、个人缴纳（个人缴费/个人承担）。<br>' +
      '<strong>五险自动识别：</strong>养老保险/医疗保险/失业保险/工伤保险/生育保险——各险种可能独立Sheet或以合并列出现。<br>' +
      '<strong>公积金兼容：</strong>公积金/住房公积金/住房储金、缴存基数/公积金基数、'
      + '缴存比例（自动识别单位+个人两部分）、月缴存额。'},
    {title:'申报表', icon:'\u{1f4cb}', detail:'' +
      '<strong>增值税申报表：</strong>销售额/销项税额/进项税额/应纳税额/期末留抵税额/即征即退——'
      + '兼容一般纳税人和小规模纳税人两种表格式。<br>' +
      '<strong>企业所得税申报表：</strong>营业收入/营业成本/利润总额/纳税调整增加额/纳税调整减少额/'
      + '应纳税所得额/税率/应纳所得税额——兼容查账征收和核定征收。<br>' +
      '<strong>个税申报表：</strong>与工资表通过关键词区分（含\u201c累计预扣预缴\u201d\u201c应补退税额\u201d\u201c所得项目\u201d等个税专属词）。<br>' +
      '<strong>印花税/完税证明：</strong>按税种名称和缴款日期格式自动识别。'},
    {title:'财务报表', icon:'\u{1f4ca}', detail:'' +
      '<strong>科目余额表：</strong>科目编码/科目名称/期初余额/本期借方/本期贷方/期末余额——兼容借贷方向和余额方向两种格式。<br>' +
      '<strong>财务报表（资产负债表/利润表）：</strong>按报表项目名称（流动资产、非流动资产、营业收入、营业成本等）自动区分。<br>' +
      '<strong>进销存台账：</strong>期初库存/本期入库/本期出库/期末库存/存货编码/产品名称——兼容数量和金额两类台账。'},
    {title:'合同/往来/资产', icon:'\u{1f4c4}', detail:'' +
      '<strong>合同台账：</strong>合同编号/合同名称/甲方/乙方/合同金额/已付金额/未付金额/签订日期/生效日期/到期日期——14字段全覆盖。<br>' +
      '<strong>应收/应付账款：</strong>客户/供应商名称、欠款金额/应付金额、账龄、账期、逾期标志。<br>' +
      '<strong>固定资产：</strong>资产名称/原值/累计折旧/净值/入账日期/折旧年限/残值率。<br>' +
      '<strong>无形资产/资产损失/费用明细/研发费用：</strong>各有专属关键词集和解析器，按列名自动路由。'},
    {title:'特殊类型', icon:'\u{1f50d}', detail:'' +
      '<strong>人员清单：</strong>姓名/身份证号/入职/离职/岗位/部门——与工资表通过关键词区分（无金额列）。<br>' +
      '<strong>股权交易：</strong>出让方/受让方/转让比例/转让价格/审批日期。<br>' +
      '<strong>借款合同：</strong>借款人/出借人/借款金额/利率/期限/担保方式。<br>' +
      '<strong>进出口报关：</strong>报关单号/进出口类型/商品名称/金额/币种/口岸。<br>' +
      '<strong>关联交易：</strong>关联方名称/交易类型/关联关系/交易金额/定价政策。<br>' +
      '<strong>通用数据（兜底）：</strong>以上所有类型均不匹配时，标注为generic_data——保留原始结构不变，将数据原样输出供下游模块自行判断。'}
  ];

  compatItems.forEach(function(ci) {
    html += '<details style="margin-bottom:10px;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden">'
      + '<summary style="padding:12px 16px;background:#fff;border-bottom:1px solid #f1f5f9;cursor:pointer;font-size:10px;font-weight:600;color:#16233a;user-select:none">'
      + ci.icon + ' ' + ci.title + '</summary>'
      + '<div style="padding:14px 16px;font-size:10px;color:#3a4048;line-height:20px;background:#fff">'
      + ci.detail + '</div>'
      + '</details>';
  });

  html += '</div>';

  // ═══════════════════════════════════════════════
  // 三、格式扩展（PDF/DOCX/CSV/OCR图片）
  // ═══════════════════════════════════════════════
  html += '<div id="fp-formats" style="margin-bottom:48px">'
    + '<h3>三、格式扩展：多格式全兼容</h3>'
    + '<p style="font-size:10px;color:#3a4048;line-height:20px;margin:0 0 10px">'
    + '除了传统的 Excel 格式（.xls/.xlsx），文件解析模块已扩展到支持以下格式的自动解析：'
    + '</p>'

    + '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:12px">'

    // PDF
    + '<div class="fp-step">'
    + '<div style="font-size:10px;font-weight:700;color:#16233a;margin-bottom:10px">\u{1f4c4} PDF文档</div>'
    + '<div style="font-size:10px;color:#3a4048;line-height:20px">'
    + '<strong>双系统架构：</strong>pdfplumber表格提取（优先）+ pypdf文本解析（兜底）。<br>'
    + '<strong>自适应策略：</strong>逐页提取所有表格 \u2192 取最大表格 \u2192 表头走多维指纹匹配 \u2192 '
    + '成功则按类型路由，失败则回退旧格式解析器。<br>'
    + '<strong>优势：</strong>不再硬编码特定银行格式（旧版仅支持招商银行大兴支行），任何银行/税务PDF均可识别。<br>'
    + '<strong>格式：</strong>支持 .pdf'
    + '</div>'
    + '</div>'

    // DOCX
    + '<div class="fp-step">'
    + '<div style="font-size:10px;font-weight:700;color:#16233a;margin-bottom:10px">\u{1f4dd} Word文档</div>'
    + '<div style="font-size:10px;color:#3a4048;line-height:20px">'
    + '<strong>表格提取：</strong>python-docx遍历所有表格 \u2192 合并多表格 \u2192 表头指纹匹配。<br>'
    + '<strong>文本兜底：</strong>无表格时提取段落文本，标注为 document_text 类型。<br>'
    + '<strong>应用场景：</strong>合同文件、申报说明、审计报告等Word格式资料。<br>'
    + '<strong>格式：</strong>支持 .docx'
    + '</div>'
    + '</div>'

    // CSV
    + '<div class="fp-step">'
    + '<div style="font-size:10px;font-weight:700;color:#16233a;margin-bottom:10px">\u{1f4ca} CSV文本</div>'
    + '<div style="font-size:10px;color:#3a4048;line-height:20px">'
    + '<strong>管道原生支持：</strong>csv.reader读取 \u2192 CsvSheet模拟Sheet接口 \u2192 指纹匹配。<br>'
    + '<strong>编码自动检测：</strong>UTF-8-BOM优先，自动处理逗号分隔和引号转义。<br>'
    + '<strong>应用场景：</strong>银行系统导出的流水、ERP导出的数据表等CSV格式。<br>'
    + '<strong>格式：</strong>支持 .csv'
    + '</div>'
    + '</div>'

    // OCR images
    + '<div class="fp-step">'
    + '<div style="font-size:10px;font-weight:700;color:#16233a;margin-bottom:10px">\u{1f4f7} OCR图片识别</div>'
    + '<div style="font-size:10px;color:#3a4048;line-height:20px">'
    + '<strong>双系统OCR：</strong>EasyOCR（中文优先，文字块坐标提取）+ Tesseract（系统兜底）。<br>'
    + '<strong>表格重建：</strong>Y坐标聚类（<15px=同行）\u2192 X排序 \u2192 构建行\u00d7列矩阵 \u2192 指纹匹配。<br>'
    + '<strong>字段提取：</strong>无表格结构时，正则提取发票号/代码/日期/金额等关键字段。<br>'
    + '<strong>首次使用：</strong>需联网下载EasyOCR模型（~200MB，一次性），之后本地缓存。<br>'
    + '<strong>格式：</strong>支持 .jpg .jpeg .png .bmp .tiff'
    + '</div>'
    + '</div>'

    + '</div>'
    + '</div>';

  // ═══════════════════════════════════════════════
  // 四、{{file_fingerprints}}类文件指纹库
  // ═══════════════════════════════════════════════
  html += '<div id="fp-fingerprint" style="margin-bottom:48px">'
    + '<h3>四、文件指纹库 \u00b7 ' + fps.length + ' 类</h3>'
    + '<p style="font-size:10px;color:#3a4048;line-height:20px;margin:0 0 10px">'
    + '每类指纹由 <strong>关键词集</strong> + <strong>得分阈值</strong> + <strong>专用解析器</strong> 三部分组成。'
    + '关键词决定了\u201c怎么看\u201d，阈值决定了\u201c多确定才能算\u201d，解析器决定了\u201c识别后怎么提取\u201d。'
    + '按使用频率分六梯队排列，第一梯队是税务合规中最常见的高频类型。'
    + '</p>';

  var groups = [
    {title:'第一梯队 \u00b7 高频核心（用户最常上传）', items: fps.slice(0,12),
     desc:'这12类文件是税务合规中最常出现的材料——银行流水、发票、工资表、社保公积金等。拥有最完善的关键词库（20-60+个关键词）和最成熟的解析器。得分阈值2-4分，识别率>95%。'},
    {title:'第二梯队 \u00b7 合同/权证/关联交易', items: fps.slice(12,17),
     desc:'合同和关联交易文件的识别依赖更细致的结构分析——关键词数量较少（9-12个），阈值通常为2分。这类文件的列结构比关键词更有特征性。'},
    {title:'第三梯队 \u00b7 申报表与财务报表', items: fps.slice(17,23),
     desc:'各类税务申报表和财务报表——关键词含税种名称、报表项目、会计科目等专业术语。阈值3分，因为申报表的列名专业性强、不易与其他类型混淆。'},
    {title:'第四梯队 \u00b7 往来与合同清单', items: fps.slice(23,27),
     desc:'应收账款、应付账款、预收预付等往来类数据表。特征：通常含对方单位名称+金额+账龄三要素。'},
    {title:'第五梯队 \u00b7 资产与费用', items: fps.slice(27,31),
     desc:'固定资产、无形资产、资产损失、费用明细、研发费用等资产和费用类表格。各有关键词特征，阈值2分。'},
    {title:'第六梯队 \u00b7 特殊交易与兜底', items: fps.slice(31),
     desc:'人员清单、股权交易、借款合同、进出口报关等特殊类型。最后是通用数据（generic_data）作为兜底——关键词阈值仅1分，确保任何有结构的表格都不会被丢弃。'},
  ];

  groups.forEach(function(g) {
    html += '<div style="margin-bottom:10px">'
      + '<div style="font-size:10px;font-weight:700;color:#16233a;margin-bottom:4px">' + escHtml(g.title) + '</div>'
      + '<div style="font-size:10px;color:#64748b;margin-bottom:10px;line-height:20px">' + escHtml(g.desc) + '</div>'
      + '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:8px">';

    g.items.forEach(function(item) {
      html += '<div style="padding:10px 12px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;font-size:10px;line-height:20px">'
        + '<div style="font-weight:600;color:#16233a;margin-bottom:4px"><span style="font-size:10px">' + item.icon + '</span> ' + escHtml(item.name) + '</div>'
        + '<div style="color:#64748b;font-size:10px;margin-bottom:4px">' + escHtml(item.sig) + '</div>'
        + '<div style="color:#64748b;font-size:10px">阈值：' + item.threshold + ' \u00b7 ' + item.parser + '</div>'
        + '</div>';
    });

    html += '</div></div>';
  });

  html += '</div>';

  // ═══════════════════════════════════════════════
  // 五、解析流程（8步详解）
  // ═══════════════════════════════════════════════
  html += '<div id="fp-flow" style="margin-bottom:48px">'
    + '<h3>五、解析流程：8步全链路</h3>'
    + '<p style="font-size:10px;color:#3a4048;line-height:20px;margin:0 0 10px">'
    + '从磁盘上的原始文件到结构化的分析数据，文件解析系统执行8个步骤：'
    + '</p>';

  var steps = [
    {num:'1', title:'磁盘扫描', detail:'' +
      '遍历 uploads/ 目录下所有支持格式的文件（.xls .xlsx .csv .pdf .docx .jpg .png 等），按文件修改时间排序。' +
      '跳过系统临时文件（~$开头、.tmp结尾）。同一文件MD5去重——内容相同的文件只解析一次，避免重复工作。'},
    {num:'2', title:'格式检测', detail:'' +
      '读取文件前5KB数据，通过二进制签名（magic bytes）判断真实格式——不是依赖扩展名。' +
      'xls/xlsx: OLE2/ZIP签名；CSV: 纯文本逗号分隔；PDF: %PDF-头部；DOCX: ZIP+[Content_Types].xml；' +
      '图片: JPEG/PNG/BMP/TIFF头部签名。调用对应的文件读取库：openpyxl / xlrd / csv / pdfplumber / python-docx / PIL。'},
    {num:'3', title:'表头提取', detail:'' +
      '逐Sheet读取前200行（非硬编码\u201c第1行\u201d——自适应扫描直到找到列名行）。' +
      '对每一列：提取列名文本 + 前200个数据样本，构建\u201c表头特征向量\u201d。' +
      '自动跳过空行、纯数字行（不太可能是表头）、以及明显的合计行。'},
    {num:'4', title:'指纹匹配', detail:'' +
      '将表头特征向量与多维指纹关键词库做交叉匹配：遍历每一种文件类型的关键词集，' +
      '对表头中出现的每个词检查是否命中，每命中1词得1分。记录每种类型的总得分。' +
      '同时检查\u201c关键识别词\u201d——某些词的出现足以直接判定类型（如\u201c发票号码\u201d+3个其他词\u2192通用发票）。'},
    {num:'5', title:'类型判定', detail:'' +
      '取得分最高的类型：①最高分\u2265阈值 \u2192 直接判定为该类型；' +
      '②最高分<阈值 且 前两名差距\u22641分 \u2192 进入结构分析做二次判定；' +
      '③所有类型得分均<阈值且无接近候选人 \u2192 进入数据推断（第3层）。' +
      '四方交叉验证在判定存疑时介入——综合文件名/列头/数据/公司匹配做最终裁决。'},
    {num:'6', title:'解析器调用', detail:'' +
      '根据最终确定的文件类型，调用对应的专用解析器函数。' +
      '每个解析器负责将原始表格转换为字段标准化的结构化数据：' +
      '银行流水\u2192_parse_bank_sheet、发票\u2192_parse_invoice_sheet、' +
      '工资\u2192_parse_salary_sheet、合同\u2192_parse_contract_sheet等。' +
      '解析器内部完成：列名映射归一化（82+变体\u2192标准字段名）、数据类型转换（字符串\u2192float/date）、无效行过滤。'},
    {num:'7', title:'标准化输出', detail:'' +
      '统一字段命名规范：date（日期）、amount（金额）、counterparty（对方）、' +
      'seller（销售方）、buyer（购买方）、goods（品名）、quantity（数量）、' +
      'tax_rate（税率）、tax_amount（税额）、total（价税合计）。' +
      '所有金额统一为float（去除千分位逗号/货币符号）、日期统一为YYYY-MM-DD格式。' +
      '输出为可在后续分析中直接使用的结构化JSON数据。'},
    {num:'8', title:'日志与路由', detail:'' +
      '将每个文件的解析结果写入 file_results 数组和 pipeline_log 日志。' +
      '按文件类型自动路由到对应的数据列表：银行流水\u2192bank_txs、发票\u2192invoice_data、' +
      '工资\u2192salary_data、合同\u2192contract_data等。' +
      '解析失败的标注error原因，供诊断面板回溯。所有日志持久化到分析缓存中。'}
  ];

  steps.forEach(function(st) {
    html += '<div class="fp-step" style="margin-bottom:10px">'
      + '<div style="display:flex;gap:12px">'
      + '<span style="display:inline-flex;align-items:center;justify-content:center;'
      + 'flex-shrink:0;width:28px;height:28px;border-radius:50%;background:#f1f5f9;'
      + 'color:#64748b;font-size:10px;font-weight:700">' + st.num + '</span>'
      + '<div>'
      + '<div style="font-size:10px;font-weight:700;color:#16233a;margin-bottom:4px">' + st.title + '</div>'
      + '<div style="font-size:10px;color:#3a4048;line-height:20px">' + st.detail + '</div>'
      + '</div></div>'
      + '</div>';
  });

  html += '</div>';

  target.innerHTML = html;
}

// {{file_fingerprints}}类文件指纹数据（详尽版）
function fpFingerprints() {
  return [
    // 第一梯队
    {icon:'🏧', name:'银行流水', sig:'对方户名 | 交易日期 | 收入金额 | 支出金额 | 借贷标志 | 余额 (23个关键词 阈值3分)', threshold:'≥3', parser:'_parse_bank_sheet'},
    {icon:'💰', name:'工资表', sig:'本期收入 | 应发工资 | 代扣个税 | 社保 | 公积金 | 实发合计 (60+关键词 阈值2分)', threshold:'≥2', parser:'_parse_salary_sheet'},
    {icon:'🧾', name:'销项发票', sig:'购方名称 | 购方税号 | 购买方纳税人识别号 (10个关键词 阈值2分)', threshold:'≥2', parser:'_parse_invoice_sheet(销项)'},
    {icon:'📥', name:'进项发票', sig:'销方名称 | 销方税号 | 销售方名称 | 供应商名称 (11个关键词 阈值2分)', threshold:'≥2', parser:'_parse_invoice_sheet(进项)'},
    {icon:'📋', name:'通用发票', sig:'发票号码 | 发票代码 | 开票日期 | 金额 | 税额 | 价税合计 | 税率 (20个关键词 阈值4分)', threshold:'≥4', parser:'_parse_invoice_sheet(进项)'},
    {icon:'📝', name:'记账凭证', sig:'凭证号 | 科目名称 | 摘要 | 借方金额 | 贷方金额 (8个主关键词 阈值2分)', threshold:'≥2', parser:'_parse_voucher_sheet'},
    {icon:'🛡️', name:'社保明细', sig:'缴费基数 | 单位缴纳 | 个人缴纳 | 养老保险 | 医疗保险 | 工伤保险 (15个关键词 阈值2分)', threshold:'≥2', parser:'_parse_social_sheet'},
    {icon:'🏡', name:'公积金', sig:'公积金 | 缴存基数 | 缴存比例 | 单位缴存 | 个人缴存 | 月缴存额 (17个关键词 阈值2分)', threshold:'≥2', parser:'_parse_housing_fund_sheet'},
    {icon:'📑', name:'进项抵扣勾选', sig:'勾选状态 | 有效抵扣税额 | 数电发票号码 | 发票风险等级 (5个关键词 阈值2分)', threshold:'≥2', parser:'_parse_input_vat_sheet'},
    {icon:'📦', name:'进销存台账', sig:'期初库存 | 本期入库 | 本期出库 | 期末库存 | 存货编码 | 产品名称 (16个关键词 阈值2分)', threshold:'≥2', parser:'_parse_inventory_sheet'},
    {icon:'📊', name:'科目余额表', sig:'科目编码 | 科目名称 | 期初余额 | 本期发生额 | 期末余额 (8个关键词 阈值2分)', threshold:'≥2', parser:'_parse_trial_balance_sheet'},
    // 第二梯队
    {icon:'📄', name:'合同文件', sig:'合同编号 | 签约方 | 合同金额 | 签订日期 | 履约期限 (9个关键词 阈值2分)', threshold:'≥2', parser:'_parse_contract_sheet'},
    {icon:'🔗', name:'关联交易', sig:'关联方名称 | 交易类型 | 关联关系 | 交易金额 | 定价方式 (12个关键词 阈值2分)', threshold:'≥2', parser:'_parse_related_party'},
    // 第三梯队
    {icon:'💰', name:'财务报表', sig:'营业收入 | 营业成本 | 利润总额 | 资产合计 | 负债合计 | 期末余额 (18个关键词 阈值3分)', threshold:'≥3', parser:'_parse_financial_sheet'},
    {icon:'🏦', name:'增值税申报表', sig:'销售额 | 销项税额 | 进项税额 | 应纳税额 | 期末留抵 (19个关键词 阈值3分)', threshold:'≥3', parser:'_parse_vat_declaration'},
    {icon:'📈', name:'企业所得税申报表', sig:'营业收入 | 营业成本 | 利润总额 | 应纳税所得额 | 税率 (11个关键词 阈值3分)', threshold:'≥3', parser:'_parse_cit_declaration'},
    {icon:'👤', name:'个税申报表', sig:'纳税人姓名 | 收入 | 应纳税所得额 | 已缴税额 | 应补退税额 (16个关键词 阈值2分)', threshold:'≥2', parser:'_parse_individual_tax'},
    {icon:'📜', name:'印花税', sig:'税目 | 计税金额 | 税率 | 应纳税额 | 减免税额 (12个关键词 阈值2分)', threshold:'≥2', parser:'_parse_stamp_duty'},
    {icon:'📋', name:'完税证明', sig:'税种 | 所属期 | 计税金额 | 实缴金额 | 缴款日期 (14个关键词 阈值2分)', threshold:'≥2', parser:'_parse_tax_payment'},
    // 第四梯队
    {icon:'📄', name:'合同清单', sig:'合同名称 | 对方名称 | 合同金额 | 已付金额 | 未付金额 (16个关键词 阈值2分)', threshold:'≥2', parser:'_parse_contract_list'},
    {icon:'🤝', name:'应收账款', sig:'客户名称 | 欠款金额 | 账龄 | 账期 | 是否逾期 (10个关键词 阈值2分)', threshold:'≥2', parser:'_parse_accounts_receivable'},
    {icon:'🏗️', name:'应付账款', sig:'供应商名称 | 应付金额 | 账龄 | 付款条件 (10个关键词 阈值2分)', threshold:'≥2', parser:'_parse_accounts_payable'},
    {icon:'💳', name:'预收预付', sig:'客户/供应商名称 | 预收金额 | 预付金额 | 结算状态 (10个关键词 阈值2分)', threshold:'≥2', parser:'_parse_prepaid_advance'},
    {icon:'🧾', name:'其他应收付', sig:'对方名称 | 应收/应付 | 金额 | 账龄 | 坏账准备 (7个关键词 阈值2分)', threshold:'≥2', parser:'_parse_other_receivables'},
    // 第五梯队
    {icon:'🏭', name:'固定资产', sig:'资产名称 | 原值 | 累计折旧 | 净值 | 入账日期 | 折旧年限 (14个关键词 阈值2分)', threshold:'≥2', parser:'_parse_fixed_assets'},
    {icon:'📜', name:'无形资产', sig:'资产名称 | 原值 | 累计摊销 | 净值 | 摊销年限 (9个关键词 阈值2分)', threshold:'≥2', parser:'_parse_intangible_assets'},
    {icon:'📊', name:'资产损失', sig:'资产名称 | 损失金额 | 损失原因 | 审批日期 (8个关键词 阈值2分)', threshold:'≥2', parser:'_parse_asset_impairment'},
    {icon:'📋', name:'费用明细', sig:'费用类型 | 金额 | 报销人 | 所属部门 | 发生日期 (20个关键词 阈值2分)', threshold:'≥2', parser:'_parse_expense_detail'},
    {icon:'🔬', name:'研发费用', sig:'研发项目 | 费用类型 | 金额 | 研发阶段 | 资本化/费用化 (12个关键词 阈值2分)', threshold:'≥2', parser:'_parse_rd_expense'},
    // 第六梯队
    {icon:'👥', name:'人员清单', sig:'姓名 | 身份证号 | 入职日期 | 离职日期 | 岗位 | 部门 (14个关键词 阈值2分)', threshold:'≥2', parser:'_parse_employee_list'},
    {icon:'📄', name:'股权交易', sig:'出让方 | 受让方 | 转让比例 | 转让价格 | 审批日期 (9个关键词 阈值2分)', threshold:'≥2', parser:'_parse_equity_transaction'},
    {icon:'💰', name:'借款合同', sig:'借款人 | 出借人 | 借款金额 | 利率 | 期限 | 担保方式 (14个关键词 阈值2分)', threshold:'≥2', parser:'_parse_loan_borrowing'},
    {icon:'🚢', name:'进出口报关', sig:'报关单号 | 进出口类型 | 商品名称 | 金额 | 币种 | 口岸 (15个关键词 阈值2分)', threshold:'≥2', parser:'_parse_import_export'},
    {icon:'📋', name:'通用数据', sig:'纯数值表 (9个关键词 兜底阈值1分)', threshold:'≥1', parser:'_parse_generic'},
  ];
}

async function loadFileParsingData() {
  var target = document.getElementById('fp-analysis-result');
  if (!target) return;
  try {
    var data = await getSharedAnalysis();
    if (!data.ok) {
      target.innerHTML = '<div style="padding:48px 0;font-size:10px;color:#64748b">暂无分析结果，请先运行一键稽查</div>';
      return;
    }
    _cachedFileParsingReport = data.report;
    renderFileParsingResult(data.report);
  } catch (e) {
    target.innerHTML = '<div style="padding:48px 0;font-size:10px;color:#64748b">加载失败</div>';
  }
}

function renderFileParsingResult(report) {
  var target = document.getElementById('fp-analysis-result');
  if (!target) return;
  var frs = report.file_results || [];
  var plogs = report.pipeline_log || [];

  var parsed = frs.filter(function(f) { return f.type !== 'unknown' && !f.error; }).length;
  var failed = frs.filter(function(f) { return f.error; }).length;

  var html = '<div id="fp-result">'
    + '<h3 style="font-size:10px;font-weight:700;color:#16233a;margin:0 0 6px">六、本次解析结果</h3>'
    + '<p style="font-size:10px;color:#64748b;margin:0 0 10px">本次分析共解析 ' + frs.length + ' 个文件，成功识别 ' + parsed + ' 个，未识别 ' + failed + ' 个</p>'

    // 统计卡片
    + '<div style="display:flex;gap:12px;margin-bottom:10px">'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:10px;font-weight:700;color:#16233a">' + frs.length + '</div><div style="font-size:10px;color:#64748b;margin-top:4px">文件总数</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:10px;font-weight:700;color:#059669">' + parsed + '</div><div style="font-size:10px;color:#64748b;margin-top:4px">已解析</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:10px;font-weight:700;color:#dc2626">' + failed + '</div><div style="font-size:10px;color:#64748b;margin-top:4px">未解析</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:10px;font-weight:700;color:#16233a">' + plogs.length + '</div><div style="font-size:10px;color:#64748b;margin-top:4px">管线日志</div></div>'
    + '</div>'

    // 类型分布
    + '<h4 style="font-size:10px;font-weight:600;color:#64748b;margin:0 0 10px">类型分布</h4>';
  var typeCount = {};
  frs.forEach(function(fr) { var t = fr.type || 'unknown'; typeCount[t] = (typeCount[t] || 0) + 1; });
  var types = Object.keys(typeCount).sort(function(a,b) { return typeCount[b] - typeCount[a]; });
  if (types.length > 0) {
    html += '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px">';
    types.forEach(function(t) {
      html += '<div style="padding:6px 12px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;font-size:10px;color:#3a4048">'
        + escHtml(t) + ' <span style="font-weight:600;color:#16233a">x' + typeCount[t] + '</span></div>';
    });
    html += '</div>';
  }

  // 解析明细表
  html += '<h4 style="font-size:10px;font-weight:600;color:#64748b;margin:0 0 10px">解析明细</h4>';

  if (frs.length === 0) {
    html += '<div style="color:#64748b;font-size:10px;padding:24px 0">无文件数据</div>';
  } else {
    html += '<table style="width:100%;border-collapse:collapse;font-size:10px">'
      + '<thead><tr style="border-bottom:2px solid #16233a;text-align:left">'
      + '<th style="padding:8px 12px 8px 0;font-weight:600;color:#16233a;width:36px">#</th>'
      + '<th style="padding:8px 12px;font-weight:600;color:#16233a">文件名</th>'
      + '<th style="padding:8px 12px;font-weight:600;color:#16233a">识别类型</th>'
      + '<th style="padding:8px 12px;font-weight:600;color:#16233a">数据条数</th>'
      + '<th style="padding:8px 12px;font-weight:600;color:#16233a">解析动作</th>'
      + '<th style="padding:8px 12px;font-weight:600;color:#16233a;min-width:100px">识别依据</th>'
      + '</tr></thead><tbody>';

    frs.forEach(function(fr, i) {
      var typeLabel = fr.type || '未知';
      var status = fr.error ? 'fail' : (fr.type === 'unknown' ? 'warn' : 'ok');
      var rowCount = '—';
      var actions = '';
      if (fr.actions && fr.actions.length) {
        var m = (fr.actions.join(' ')).match(/(\d+)条/);
        if (m) rowCount = m[1];
        actions = fr.actions.join(' · ');
      }
      var statusIcon = status === 'fail' ? '✗' : (status === 'warn' ? '△' : '✓');
      var statusColor = status === 'fail' ? '#dc2626' : (status === 'warn' ? '#f59e0b' : '#22c55e');
      var rowBg = status === 'fail' ? '#fef2f2' : (i % 2 === 0 ? '#fafafa' : 'transparent');

      html += '<tr style="border-bottom:1px solid #f1f5f9;background:' + rowBg + '">'
        + '<td style="padding:10px 12px 10px 0;color:#64748b">' + (i + 1) + '</td>'
        + '<td style="padding:10px 12px;color:#16233a;max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + escHtml(fr.file) + '">' + escHtml(fr.file) + '</td>'
        + '<td style="padding:10px 12px;color:#64748b">' + escHtml(typeLabel) + '</td>'
        + '<td style="padding:10px 12px;color:#3a4048;font-weight:600">' + rowCount + '</td>'
        + '<td style="padding:10px 12px;color:#64748b;font-size:10px;max-width:280px">' + escHtml(actions) + '</td>'
        + '<td style="padding:10px 12px;color:#64748b;font-size:10px">' + (function(){
          var diag = [];
          var tr = fr._trace || {};
          var kw = tr.kw_phase || {};
          var st = tr.st_phase || {};
          if (kw.best) diag.push('得分' + kw.best.score + '/' + (kw.best.threshold || '?'));
          if (st.best && st.best.confidence != null) diag.push('置信度' + Math.round(st.best.confidence*100) + '%');
          if (fr.match_score != null) diag.push('匹配' + fr.match_score + '/' + (fr.match_threshold || '?'));
          if (fr.st_confidence != null) diag.push('结构' + Math.round(fr.st_confidence*100) + '%');
          if (status === 'fail' || status === 'warn') diag.push('<span style=\'color:#e02424;font-weight:600\'>需复核</span>');
          return diag.join(' · ') || '—';
        })() + '</td>'
        + '</tr>';
    });

    html += '</tbody></table>';
  }

  // 诊断建议（失败/未识别文件的修复建议）
  var diagFiles = frs.filter(function(fr){
    return fr.error || fr.type === 'unknown' || (fr._trace && fr._trace.suggestions && fr._trace.suggestions.length > 0);
  });
  if (diagFiles.length > 0) {
    html += '<h4 style="font-size:10px;font-weight:600;color:#64748b;margin:28px 0 12px">诊断与修复建议 — 共 ' + diagFiles.length + ' 个文件</h4>';
    diagFiles.forEach(function(df){
      var sug = (df._trace && df._trace.suggestions) || [];
      html += '<div style="margin-bottom:10px;border:1px solid #fecaca;border-radius:6px;overflow:hidden">'
        + '<div style="padding:10px 14px;background:#fef2f2;font-size:10px;font-weight:600;color:#dc2626">' + escHtml(df.file) + '（' + escHtml(df.type || '未知') + '）</div>';
      if (sug.length > 0) {
        html += '<div style="padding:12px 14px;background:#fff">';
        sug.forEach(function(s){
          html += '<div style="margin-bottom:10px;padding-left:12px;border-left:3px solid #f59e0b">'
            + '<div style="font-size:10px;font-weight:600;color:#92400e;margin-bottom:3px">问题：' + escHtml(s.issue) + '</div>'
            + (s.detail ? '<div style="font-size:10px;color:#64748b;margin-bottom:3px;line-height:1.8">' + escHtml(s.detail) + '</div>' : '')
            + (s.fix ? '<div style="font-size:10px;color:#0e7490;line-height:1.8">修复建议：' + escHtml(s.fix) + '</div>' : '')
            + '</div>';
        });
        html += '</div>';
      } else {
        html += '<div style="padding:12px 14px;font-size:10px;color:#64748b">暂无详细诊断信息，建议检查文件格式与内容是否完整。</div>';
      }
      html += '</div>';
    });
  }

  // 管线日志（详尽版）
  if (plogs.length > 0) {
    html += '<h4 style="font-size:10px;font-weight:600;color:#64748b;margin:40px 0 12px">管线日志 — 共 ' + plogs.length + ' 条</h4>';
    html += '<div style="background:#16233a;border-radius:6px;padding:20px 24px;max-height:500px;overflow-y:auto;font-family:\'SF Mono\',\'Fira Code\',monospace;font-size:10px;line-height:20px">';
    plogs.forEach(function(log, i) {
      var color = '#64748b';
      if (/异常|失败|错误/.test(log)) color = '#fca5a5';
      else if (/完成|成功|通过/.test(log)) color = '#86efac';
      else if (/发现|触发|命中/.test(log)) color = '#fde68a';
      else if (/Phase|Step|阶段/.test(log)) color = '#93c5fd';
      html += '<div style="color:' + color + '">[' + (i + 1).toString().padStart(3, ' ') + '] ' + escHtml(log) + '</div>';
    });
    html += '</div>';
  }

  html += '</div>'; // fp-result
  target.innerHTML = html;
  if (window._pendingFpSlice) { var s = window._pendingFpSlice; window._pendingFpSlice = null; fpSliceToSection(s); }
}

// ==================== 页面2：域分析（详尽版） ====================
function renderDomainAnalysisPage(container) {
  if (!container) return;
  window.currentModule = '域分析';
  container.innerHTML = '<style>.da-layout{display:flex;gap:24px;max-width:1200px;margin:0 auto;padding:20px;background:#fff}.da-toc{width:190px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:10px;line-height:20px;max-height:calc(100vh-40px);overflow-y:auto}.da-toc .toc-title{font-weight:700;color:#16233a;font-size:10px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.da-toc a{display:block;color:#3a4048;text-decoration:none;padding:2px 8px;border-radius:4px;cursor:pointer}.da-toc a:hover,.da-toc a.active{background:#eff6ff;color:#2563eb;font-weight:600}.da-main{flex:1;min-width:0;background:#fff}.da-main h3{font-size:10px!important;font-weight:700!important;color:#16233a!important;padding-bottom:8px!important;border-bottom:2px solid #e2e8f0!important;margin:0 0 10px!important}.da-main section{margin-bottom:48px!important;scroll-margin-top:20px}</style>'
    + '<div class="da-layout">'
    + '<nav class="da-toc"><div class="toc-title">📖 导航</div>'
    + '<a href="#da-intro">一 什么是域分析</a>'
    + '<a href="#da-arch">二 域分析架构</a>'
    + '<a href="#da-domains">三 分析域</a>'
    + '<a href="#da-result">四 本次分析结果</a>'
    + '</nav>'
    + '<div class="da-main">'
    + '<h2 style="font-size:10px;font-weight:800;color:#16233a;margin:0 0 10px">🔬 域分析</h2>'
    + '<p style="font-size:10px;color:#64748b;margin:0 0 10px">{{domain_functions}}个域分析函数 · 12大分类 · 跨域关联推理 · 多源证据链串联 · 资料情报自适应分类</p>'
    + renderDomainAnalysisStatic()
    + '<div id="da-analysis-result"></div>'
    + '</div></div>';

  if (_cachedDomainReport) { renderDomainAnalysisResult(_cachedDomainReport); }
  else { loadDomainAnalysisData(); }
  // 侧边栏子模块入口
  if (window._daSection) {
    var dsec = window._daSection;
    window._daSection = null;
    if (dsec === 'da-result') { window._pendingDaSlice = 'da-result'; }
    else {
      var ds = document.createElement('style');
      ds.textContent = '.da-toc{display:none!important}.da-layout{display:block!important}.da-main h2,.da-main>p{display:none!important}#da-intro,#da-arch,#da-domains,#da-result{display:none!important}#'+dsec+'{display:block!important}';
      container.appendChild(ds);
    }
  }
}

function daSliceToSection(sectionId) {
  var toc = document.querySelector('.da-toc');
  if (toc) toc.style.display = 'none';
  var layout = document.querySelector('.da-layout');
  if (layout) layout.style.display = 'block';
  var h2 = document.querySelector('.da-main h2');
  if (h2) h2.style.display = 'none';
  var p = document.querySelector('.da-main > p');
  if (p) p.style.display = 'none';
  var allSecs = document.querySelectorAll('#da-intro,#da-arch,#da-domains,#da-result');
  for (var i = 0; i < allSecs.length; i++) {
    allSecs[i].style.display = allSecs[i].id === sectionId ? 'block' : 'none';
  }
  setTimeout(function() {
    var el = document.getElementById(sectionId);
    if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
  }, 200);
}

function renderDomainAnalysisStatic() {
  var html = '';

  // ══════ Hero摘要 ══════
  html += '<div style="background:#fff;border:1px solid #e2e8f0;padding:20px 24px;border-radius:8px;margin-bottom:10px">'
    + '<p style="font-size:10px;color:#3a4048;line-height:20px;margin:0">'
    + '域分析是税务合规分析的核心层——分析域从资金流、进销存、供应商、交叉验证、经营实质、'
    + '资料完备度、发票、合同凭证、税务社保、资产关联、行业对标、跨域推理、补充税种共13个维度，'
    + '对同一份企业数据进行全方位、多角度、交叉印证的分析。每个域由独立的域分析函数驱动，'
    + '输出结构化的发现列表，域与域之间通过跨域关联推理形成多源证据链，最终汇集成完整的税务合规报告。'
    + '</p>'
    + '</div>'

  // ══════ 一、什么是域分析 ══════
  html += '<div id="da-intro" style="margin-bottom:48px">'
    + '<h3 style="font-size:10px;font-weight:700;color:#16233a;margin:0 0 6px">一、什么是域分析</h3>'
    + '<p style="font-size:10px;color:#3a4048;line-height:20px;margin:0 0 10px">'
    + '域分析（Domain Analysis）是税务合规系统的核心分析层——位于文件解析和报告生成之间。'
    + '系统将从资料中提取的全部原始数据（银行流水、发票、工资表、社保、凭证、库存、合同等）'
    + '导入多个独立的分析域，每个域由专门的域分析函数（<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">_domain_*</code>）驱动，'
    + '从不同维度对同一份数据做独立又交叉的审视。'
    + '</p>'
    + '<p style="font-size:10px;color:#3a4048;line-height:20px;margin:0 0 10px">'
    + '<strong>核心设计理念：单一数据源，多维度交叉。</strong>一份银行流水，在资金流分析域看收款来源，'
    + '在经营实质域看费用结构，在税务域看税费支出。同一个数据点在不同域中扮演不同角色，'
    + '多个域的发现相互印证或矛盾——这正是税务合规判断的实质。'
    + '</p>'
    + '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px;margin-bottom:10px">'
    
    + '<div style="padding:14px 16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px">'
    + '<div style="font-size:10px;font-weight:700;color:#16233a;margin-bottom:6px">\u{1f4e5} 数据流入</div>'
    + '<div style="font-size:10px;color:#64748b;line-height:20px">'
    + '文件解析模块输出的结构化数据<br>'
    + '→ 银行交易列表（bank_txs）<br>'
    + '→ 销/进项发票列表（sal_invs/pur_invs）<br>'
    + '→ 工资表/社保/公积金/凭证/库存/合同<br>'
    + '→ 行业画像（ctx.industry）'
    + '</div>'
    + '</div>'
    
    + '<div style="padding:14px 16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px">'
    + '<div style="font-size:10px;font-weight:700;color:#16233a;margin-bottom:6px">\u{2699}\u{fe0f} 域执行</div>'
    + '<div style="font-size:10px;color:#64748b;line-height:20px">'
    + '{{domain_functions}}个域分析函数独立运行<br>'
    + '→ 每个域有数据守卫条件<br>'
    + '→ 缺数据→标记资料缺口不空跑<br>'
    + '→ 有数据→输出发现列表<br>'
    + '→ 行业闸门自动跳过不适用的域'
    + '</div>'
    + '</div>'
    
    + '<div style="padding:14px 16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px">'
    + '<div style="font-size:10px;font-weight:700;color:#16233a;margin-bottom:6px">\u{1f4e4} 发现输出</div>'
    + '<div style="font-size:10px;color:#64748b;line-height:20px">'
    + '每条发现含9个标准字段<br>'
    + '→ type: 发现类型名称<br>'
    + '→ level/score: 风险等级+评分<br>'
    + '→ detail: 详细数据+计算过程<br>'
    + '→ description/suggestion: 解读+建议<br>'
    + '→ policy_ref/category: 法律+归类'
    + '</div>'
    + '</div>'
    
    + '<div style="padding:14px 16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px">'
    + '<div style="font-size:10px;font-weight:700;color:#16233a;margin-bottom:6px">\u{1f517} 跨域串联</div>'
    + '<div style="font-size:10px;color:#64748b;line-height:20px">'
    + '单域发现→多域交叉印证<br>'
    + '→ 跨域关联推理自动串联<br>'
    + '→ 线索链+证据链+分析链<br>'
    + '→ 证据矛盾→协商系统消解<br>'
    + '→ 同向证据→置信度叠加升权'
    + '</div>'
    + '</div>'
    
    + '</div>'
    + '<div style="padding:14px 18px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;font-size:10px;color:#3a4048;line-height:20px">'
    + '<strong>\u{1f4cb} 发现字段详解：</strong><br>'
    + '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">type</code> 发现类型名称，如"资金流向 — 收款方异常"<br>'
    + '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">level</code> 风险等级：高风险/中风险/低风险/注意/信息<br>'
    + '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">score</code> 量化评分（0-10），≥8=极高，6-7=高，4-5=中，1-3=低<br>'
    + '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">detail</code> 详细数据——含计算过程、对比数据、触发阈值<br>'
    + '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">description</code> 税务合规解读——为什么这是风险，如何理解<br>'
    + '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">suggestion</code> 处理建议——具体可执行的核查步骤<br>'
    + '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">policy_ref</code> 法律依据——引用的法条和文件号<br>'
    + '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">category</code> 分类标签——用于报告中的风险归类和合并<br>'
    + '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">domain</code> 来源域——用于追溯发现的出处和回溯分析路径'
    + '</div>'
    + '</div>';

  // ══════ 二、域分析架构 ══════
  html += '<div id="da-arch" style="margin-bottom:48px">'
    + '<h3 style="font-size:10px;font-weight:700;color:#16233a;margin:0 0 6px">二、域分析架构</h3>'
    + '<p style="font-size:10px;color:#3a4048;line-height:20px;margin:0 0 10px">'
    + '系统将分析域按驱动方式分为三类——资料驱动、算法驱动、知识驱动。'
    + '不同类型的域有不同的激活条件和置信度逻辑。'
    + '</p>'
    + '<div style="display:flex;gap:16px;margin-bottom:20px">'
    
    + '<div style="flex:1;padding:20px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;border-left:4px solid #dc2626">'
    + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">'
    + '<span style="font-size:10px">\u{1f4c4}</span>'
    + '<span style="font-size:10px;font-weight:700;color:#16233a">资料驱动域</span>'
    + '</div>'
    + '<div style="font-size:10px;color:#64748b;line-height:20px">'
    + '<strong>依赖上传资料进行判断。</strong>必须有对应的原始数据才能执行分析。'
    + '资料完备度越高，发现结论的置信度越高。缺资料时标注资料缺口，'
    + '不做无依据结论——这是税务合规工作的基本原则。'
    + '</div>'
    + '<div style="margin-top:12px;padding:10px;background:#fef2f2;border-radius:6px;font-size:10px;color:#991b1b;line-height:20px">'
    + '<strong>代表域：</strong>资金流向追踪（需银行流水）、'
    + '工资社保比对（需工资表+社保明细）、'
    + '合同比对（需合同台账+发票）'
    + '</div>'
    + '</div>'
    
    + '<div style="flex:1;padding:20px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;border-left:4px solid #2563eb">'
    + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">'
    + '<span style="font-size:10px">\u{1f4ca}</span>'
    + '<span style="font-size:10px;font-weight:700;color:#16233a">算法驱动域</span>'
    + '</div>'
    + '<div style="font-size:10px;color:#64748b;line-height:20px">'
    + '<strong>基于数据内在特征自动计算。</strong>只要有对应的基础数据即可运行，'
    + '无需外部参考资料。结果基于数学和统计学方法，客观性强。'
    + '</div>'
    + '<div style="margin-top:12px;padding:10px;background:#eff6ff;border-radius:6px;font-size:10px;color:#1e40af;line-height:20px">'
    + '<strong>代表域：</strong>进销毛利率（需进销发票）、'
    + '存货周转预警（需进销存台账）、'
    + '异常交易时间分析（需银行流水）'
    + '</div>'
    + '</div>'
    
    + '<div style="flex:1;padding:20px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;border-left:4px solid #7c3aed">'
    + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">'
    + '<span style="font-size:10px">\u{1f4da}</span>'
    + '<span style="font-size:10px;font-weight:700;color:#16233a">知识驱动域</span>'
    + '</div>'
    + '<div style="font-size:10px;color:#64748b;line-height:20px">'
    + '<strong>内置行业基准库和法规库。</strong>将企业实际数据与66个行业的统计基准值对比，'
    + '与税收法律法规的要求对照验证。偏差超出正常范围时触发预警。'
    + '</div>'
    + '<div style="margin-top:12px;padding:10px;background:#f5f3ff;border-radius:6px;font-size:10px;color:#5b21b6;line-height:20px">'
    + '<strong>代表域：</strong>行业对标分析（需{{industries}}行业基准库）、'
    + '规则全覆盖验证（需{{rules_count}}条规则库）、'
    + 'CIT汇算清缴（需企业所得税法+实施条例）'
    + '</div>'
    + '</div>'
    
    + '</div>'
    + '</div>';

  // ══════ 三、分析域 ══════
  html += '<div id="da-domains" style="margin-bottom:48px">'
    + '<h3 style="font-size:10px;font-weight:700;color:#16233a;margin:0 0 6px">三、分析域</h3>'
    + '<div style="margin:0 0 10px;padding:14px 18px;background:linear-gradient(135deg,#eff6ff,#f0f9ff);border-radius:8px;border-left:3px solid #2563eb;font-size:10px;color:#3a4048;line-height:2">'
    + '<strong>🔍 判定规则（2026-06-28新增）</strong>——域分析执行前必须先通过以下判定：<br>'
    + '① <strong>公司身份锚定</strong>：以账套公司名+信用代码为锚点，发票买卖方与公司比对→方向判定<br>'
    + '② <strong>发票方向判定</strong>：购买方=公司→进项 | 销售方=公司→销项 | 双方不含→存疑排除<br>'
    + '③ <strong>进项再分类</strong>：含"抵扣税额"列→进项抵扣认证 | 无→进项发票(记账)<br>'
    + '④ <strong>服务行业闸门</strong>：销项金税编码∈25类服务→自动跳过进销存/BOM/进销比/毛利率对标<br>'
    + '⑤ <strong>品名级精准过滤</strong>：服务+货物混合企业→服务品名跳过进销存，实物品名正常检查<br>'
    + '⑥ <strong>综合判断·四方交叉验证</strong>：文件名暗示→列头推理→数据扫描→公司匹配，冲突时以数据为准<br>'
    + '⑦ <strong>存疑排除</strong>：买卖双方都不含公司的发票=非本账套数据=排除出所有计算<br>'
    + '</div>'
    + '<p style="font-size:10px;color:#64748b;margin:0 0 10px">每个域由独立的域分析函数驱动，按类别分组。右侧数字为该域的分析函数在 main.py 中的行号。</p>';

  var domainGroups = [
    // ══════ 一、资金流分析（4域） ══════
    {cat:'一、资金流分析', color:'#dc2626', desc:'银行流水收款来源分类、付款方身份核实、大额转账追踪、个人交易检测。资金流是税务合规的血液——每一笔资金流动都可能隐藏着未申报收入或虚开发票。', items:[
      {name:'资金全链路追踪', fn:'_domain_bank_tracking', line:'12137', desc:'收款来源自适应分类 · 第三方平台收款占比 · 付款方身份（企业/个人/税务/银行）· 税费支付自动识别'},
      {name:'资金流向追踪', fn:'_domain_fund_flow_mapping', line:'13806', desc:'收款方与开票客户匹配 · 付款方与进项供应商匹配 · 法人/股东交叉引用 · 个人大额转账预警'},
      {name:'异常交易时间分析', fn:'_domain_temporal_anomaly', line:'14298', desc:'非工作时间交易（深夜/凌晨/周末）· 节假日突击交易 · 月末集中大额行为识别'},
      {name:'个人交易风险', fn:'_domain_personal_transactions', line:'12251', desc:'个人买家发票占比异常 · 无票个人大额收入 · 个人转账收款未开票 · 个人卡收款规模评估'},
    ]},
    // ══════ 二、进销存分析（4域） ══════
    {cat:'二、进销存分析', color:'#f59e0b', desc:'发票品名交叉映射、进销平衡分析、存货周转率、制造业加工链条诊断。进销不匹配是虚开发票的核心线索。', items:[
      {name:'进销毛利率分析', fn:'_domain_profit_analysis', line:'12203', desc:'进项品名vs销项品名交叉映射 · 进销比自动计算 · 有进无销/有销无进触发制造业加工诊断 · BOM表需求判断'},
      {name:'发票实质性审计', fn:'_domain_invoice_audit', line:'14966', desc:'五层递进审计——①格式合规检查 ②同品名单价波动 ③加工费专项（外发加工真实性）④金额/数量合理性 ⑤进销品名映射+BOM缺失检测'},
      {name:'存货周转预警', fn:'_domain_inventory_turnover', line:'12393', desc:'周转率计算+库龄分析+库存结构合理性 · 入库>>出库→库存积压预警 · 仓储成本vs库存价值验证'},
      {name:'发票存货付款三角验证', fn:'_domain_triangle_invoice_inventory_payment', line:'13949', desc:'进项发票金额 vs 存货入库金额 vs 银行付款金额三向验证——票货分离、虚开嫌疑、付款对象不一致'},
    ]},
    // ══════ 三、供应商与客户分析（4域） ══════
    {cat:'三、供应商与客户分析', color:'#f59e0b', desc:'供应商集中度、地理分布、身份验证、空壳识别；客户结构分析与收入穿透。供应商群集和关联交易是偷逃税的高发区。', items:[
      {name:'供应商穿透分析', fn:'_domain_supplier_deep', line:'12286', desc:'前3大供应商占比 · 同城群集检测 · 名称异常检测（短名/***遮掩）· 占比>70%触发依赖预警'},
      {name:'供应商画像分析', fn:'_domain_supplier_profiling', line:'13757', desc:'行业/地域/注册资本/成立时间综合分析 · 新注册零实缴→可疑交易方 · 高频低额（刷票嫌疑）· 单月突击开票检测'},
      {name:'上下游穿透分析', fn:'_domain_supply_chain_deep', line:'14661', desc:'客户vs供应商关联关系穿透 · 同一企业既是客户又是供应商→对倒开票嫌疑 · 名称相似度群集 · 地域群集 · 进销双向交易循环'},
      {name:'客户维度三源穿透', fn:'_domain_customer_revenue_matching', line:'13317', desc:'按客户匹配开票金额vs收款金额 · 五时点对比法 · 大额无开票收款 · 整数特征可疑 · 付款方名称不一致检测'},
    ]},
    // ══════ 四、交叉验证（5域） ══════
    {cat:'四、多源交叉验证', color:'#7c3aed', desc:'两源以上数据相互比对，验证数据一致性。单源异常可能是巧合，多源交叉同时指向同一问题才是高置信度发现。', items:[
      {name:'多源交叉验证', fn:'_domain_multi_source_cross', line:'13111', desc:'资金流+发票流+货物流三源采购验证 · 收款vs开票偏差 · 薪酬三源（工资表vs银行vs个税）· 税务四源交叉'},
      {name:'凭证发票收入对比', fn:'_domain_voucher_invoice_revenue_compare', line:'13416', desc:'主营业务收入 vs 销项发票金额 vs 银行入账三源对比 · 偏差>20%→收入确认存疑 · 趋势对比（月度/季度）'},
      {name:'利润现金流矛盾检测', fn:'_domain_profit_cashflow_gap', line:'14268', desc:'账面利润 vs 经营现金流背离 · 利润正/现金流负→利润质量存疑 · 应收激增伴随现金枯竭→可能虚增收入'},
      {name:'收入时间线调查', fn:'_domain_revenue_timeline', line:'13500', desc:'收入月度波动异常检测 · 开票vs银行入账月度错配 · 年末突击开票 · 季度末/月末集中确认收入'},
      {name:'扩展审查规则', fn:'_domain_advanced_rules', line:'13392', desc:'大额整数交易 · 周末交易 · 购销品名匹配度 · 发票连号检测 · 人均效能 · 发票备注栏合规 · 供应商名称异常'},
    ]},
    // ══════ 五、经营实质分析（3域） ══════
    {cat:'五、经营实质分析', color:'#059669', desc:'验证企业是否具备真实经营条件——有无费用/场地/仓储/运输/人员。空壳企业最怕经营实质分析——没有经营痕迹却有大量开票。', items:[
      {name:'经营实质分析', fn:'_domain_business_substance', line:'12618', desc:'7维度综合评估——①基础费用6要素（租金/水电/物业/办公/通讯/交通）②购销弹性分析 ③人均产值 ④资金沉淀率 ⑤固定资产折旧缺失 ⑥服务行业适应性闸门 ⑦综合预警评分'},
      {name:'经营实质地理分析', fn:'_domain_business_premise_geo', line:'14158', desc:'供应商/客户/加工商地址三角验真 · 跨省重物运输成本推算 · 无物流发票→运输真实性存疑 · 点→面推理全链条经营实质'},
      {name:'人员与业务匹配', fn:'_domain_workforce_profiling', line:'13894', desc:'人均营收vs行业均值 · 人均薪资合理性 · 工资增长率vs收入增长率 · 社保人数vs工资人数一致性 · 员工规模vs业务量匹配'},
    ]},
    // ══════ 六、资料完备度 ══════
    {cat:'六、资料完备度与情报', color:'#2563eb', desc:'14类税务合规必查资料逐一检测，合同需求四层自动分层。资料情报自动分类并统计收款结构/付款方/发票模式。缺失资料→风险标记→无法支撑结论时标注资料缺口。', items:[
      {name:'资料完备度评估', fn:'_domain_document_completeness', line:'12798', desc:'14类税务合规必查资料逐项检测 · 合同需求四层分层（必签/应签/可免/小额）· 缺失资料后果列明 · 综合资料完备度评分'},
      {name:'资料情报摘要', fn:'_extract_material_intel', line:'16992', desc:'银行收款类型自适应分类 · 付款方企业/个人/税务/银行占比 · 进销发票结构 · 凭证收入成本费用汇总 · 大额交易(>50万)识别'},
    ]},
    // ══════ 七、发票分析（3域） ══════
    {cat:'七、发票深度分析', color:'#0891b2', desc:'发票多维特征分析——时间/金额/税率/红冲/作废/连续性/服务vs货物占比。每一张发票都是税务合规线索，发票异常模式能暴露系统性风险。', items:[
      {name:'发票深度特征', fn:'_domain_invoice_deep', line:'12763', desc:'服务类发票占比（服务行业特征判断）· 普票vs专票占比 · 开具时间分布 · 价格区间集中度 · 金额尾数分析 · 顶额开票检测'},
      {name:'发票生命周期', fn:'_domain_invoice_lifecycle', line:'12576', desc:'未认证占比统计 · 超期未认证预警 · 税率异常检测（同一品名不同税率）· 发票类型分布 · 红冲/作废率趋势'},
      {name:'红冲作废发票追踪', fn:'_domain_red_void_invoice', line:'14244', desc:'红冲率+作废率+时间集中度模式+金额集中度 · 月末/季末突击红冲作废 · 同一对方频繁红冲→异常交易关系'},
    ]},
    // ══════ 八、合同与凭证（2域） ══════
    {cat:'八、合同与凭证', color:'#16233a', desc:'合同流与发票流/资金流比对；凭证规范性、科目使用、借贷平衡检查。凭证是财务数据的原子单元。', items:[
      {name:'合同比对分析', fn:'_domain_contract_comparison', line:'12592', desc:'发票客户vs合同当事方一致性 · 合同金额vs发票金额偏差 · 合同覆盖度评估 · 无合同大额交易风险标注'},
      {name:'凭证科目异常', fn:'_domain_voucher_anomaly', line:'12320', desc:'科目使用合规性检查 · 借贷方向正确性 · 分录借贷平衡 · 异常科目组合检测 · 凭证号连续性验证'},
    ]},
    // ══════ 九、税务与社保（3域） ══════
    {cat:'九、税务与社保', color:'#065f46', desc:'各税种申报数据与发票/银行数据交叉比对，社保与工资数据一致性验证。申报表与基础数据的偏差是偷漏税的直接证据。', items:[
      {name:'税务缴纳一致性', fn:'_domain_tax_consistency', line:'12524', desc:'银行税费支出vs发票推算应纳税额差异 · 申报表vs实际数据偏差 · 税种覆盖完整性检查'},
      {name:'增值税申报比对', fn:'_domain_vat_declaration_compare', line:'14569', desc:'进项发票vs认证抵扣vs申报进项三方比对 · 销项vs申报 · 差异>1000元→预警 · 期末留抵税额验证'},
      {name:'工资社保比对', fn:'_domain_salary_ss_hf_compare', line:'12546', desc:'工资表vs社保明细交叉验证——缴费基数匹配 · 参保人数一致 · 单位/个人缴纳比例合规 · 公积金缴存一致性'},
    ]},
    // ══════ 十、资产与关联交易（2域） ══════
    {cat:'十、资产与关联交易', color:'#047857', desc:'固定资产折旧匹配、关联交易穿透、资产损失核实。关联交易未披露是利润转移和资产掏空的常见手法。', items:[
      {name:'资产折旧费用匹配', fn:'_domain_depreciation_match', line:'14373', desc:'固定资产采购vs累计折旧匹配 · 有资产无折旧→利润虚增 · 折旧年限合理性 · 资产减值与处置核实'},
      {name:'关联交易穿透检测', fn:'_domain_related_party_check', line:'14339', desc:'名称相似度比对 · 同法人代表 · 同注册地 · 同联系电话→关联关系未披露 · 买卖双方重叠（同名对倒）'},
    ]},
    // ══════ 十一、行业对标与规则系统（4域） ══════
    {cat:'十一、行业对标与规则系统', color:'#6366f1', desc:"{{industries}}行业基准库对标，{{rules_count}}条规则全覆盖验证。行业对标告诉你“正常范围”，规则系统告诉你“合规底线”。", items:[
      {name:'行业对标分析', fn:'_domain_industry_benchmark', line:'14475', desc:'行业基准库（持续建设中）——毛利率/税负率/进销比/人均营收/费用率五维对标 · 偏离度>2σ→行业异常预警 · 自动匹配行业代码'},
      {name:'规则全覆盖验证', fn:'_domain_rule_coverage', line:'15114', desc:'{{rules_count}}条规则逐条检查 · 已触发vs未触发分类 · 未触发→标注资料缺口 · 数据不足时作无依据结论（不作无证据判断）'},
      {name:'跨域关联推理', fn:'_domain_cross_domain_reasoning', line:'13490', desc:'单点发现→多域交叉印证→证据链闭环 · 7条内置跨域证据链（JSON驱动+内置回退）· A域+B域+C域同时异常→高置信度'},
      {name:'跨域线索链', fn:'_domain_cross_domain_clues', line:'14000', desc:'从cross_domain_clues.json加载跨域线索定义 · 线索→发现→证据三级转换 · 叙事生成器集成 · 线索链可视化追溯'},
    ]},
    // ══════ 十二、跨域分析链 ══════
    {cat:'十二、跨域分析链', color:'#8b5cf6', desc:'跨域分析链是最上层的推理系统——它不直接分析数据，而是基于所有域的发现结果进行二阶推理，从交叉异常中推导出更深层的税务合规结论。', items:[
      {name:'跨域分析链', fn:'_domain_cross_domain_analysis', line:'14080', desc:'从cross_domain_analysis.json加载分析路径 · 二阶推理系统——基于域发现而非原始数据 · 多域异常→综合结论 · 因果链追溯'},
    ]},
    // ══════ 十三、补充税种检查（3域） ══════
    {cat:'十三、补充税种检查', color:'#f97316', desc:'2026-06-30新增：印花税合规检查、企业所得税汇算清缴基础分析、出口退税验证。补充传统税务审计中常见但前期域分析未覆盖的税种检查。', items:[
      {name:'印花税检查', fn:'_domain_stamp_duty_check', line:'12042', desc:'购销合同印花税推算（发票金额×0.03%）· 营业账簿贴花检查 · 借款合同印花税检测 · 偏差>50%预警'},
      {name:'CIT汇算清缴', fn:'_domain_cit_reconciliation', line:'12130', desc:'收入确认差异（发票vs凭证）· 大额无票采购支出（税前不得扣除）· 业务招待费扣除限额（60%与5‰孰低）· 折旧税会差异'},
      {name:'出口退税验证', fn:'_domain_export_vat_verification', line:'12221', desc:'出口收入自动识别 · 退税额推算（13%）· 银行退税入账匹配 · 偏差>30%预警'},
    ]},

  ];

  domainGroups.forEach(function(g) {
    html += '<div style="margin-bottom:10px">'
      + '<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:6px">'
      + '<span style="width:3px;height:14px;display:inline-block;background:' + g.color + ';border-radius:2px"></span>'
      + '<span style="font-size:10px;font-weight:700;color:#16233a">' + escHtml(g.cat) + '</span>'
      + '</div>'
      + '<div style="font-size:10px;color:#64748b;margin:0 0 10px 0;line-height:20px">' + escHtml(g.desc) + '</div>';

    g.items.forEach(function(d) {
      html += '<div style="padding:10px 12px 10px 0;margin-bottom:4px;border-left:3px solid ' + g.color + ';background:#fff;border:1px solid #e2e8f0;border-left-width:3px;border-radius:6px">'
        + '<div style="display:flex;align-items:baseline;justify-content:space-between;margin-bottom:4px">'
        + '<div style="font-size:10px;font-weight:600;color:#16233a">' + escHtml(d.name) + '</div>'
        + '<div style="font-size:10px;color:#64748b">' + escHtml(d.fn) + '() · 行' + d.line + '</div>'
        + '</div>'
        + '<div style="font-size:10px;color:#64748b;line-height:20px">' + escHtml(d.desc) + '</div>'
        + '</div>';
    });

    html += '</div>';
  });

  html += '</div>';

  // ══════ 四、域间关系 ══════
  html += '<div style="margin-bottom:10px;padding:20px 24px;background:#fff;border-radius:8px">'
    + '<h3 style="font-size:10px;font-weight:700;color:#16233a;margin:0 0 10px">四、域间关系与数据流</h3>'
    + '<div style="font-size:10px;color:#3a4048;line-height:20px">'
    + '<strong>资料完备度</strong>（顶层）→ 决定所有域分析的置信度上限。缺合同→合同比对无法运行→标记缺口。<br>'
    + '<strong>经营实质分析</strong>（基础层）→ 提供企业画像：制造业/贸易型/服务型、本地/跨省、自加工/外包。<br>'
    + '<strong>发票+银行+凭证</strong>（数据层）→ 三大主数据源，支撑进销存、资金流、税务、薪酬、资产等15个分析域。<br>'
    + '<strong>多源交叉验证</strong>（交叉层）→ 将单个域的发现两两比对、三向检验，发现孤立点无法发现的隐藏关联。<br>'
    + '<strong>行业对标+规则系统</strong>（校验层）→ 将企业数据与{{industries}}行业基准对比，与' + pc('rules','1608') + '条规则逐一匹配。<br>'
    + '<strong>跨域关联推理</strong>（顶层）→ 将以上所有发现串联为10条跨域证据链，形成最终税务合规结论。'
    + '</div>'
    + '</div>';

  return html;
}

async function loadDomainAnalysisData() {
  var target = document.getElementById('da-analysis-result');
  if (!target) return;
  try {
    var data = await getSharedAnalysis();
    if (!data.ok) {
      target.innerHTML = '<div style="padding:48px 0;font-size:10px;color:#64748b">暂无分析结果，请先运行一键稽查</div>';
      return;
    }
    _cachedDomainReport = data.report;
    renderDomainAnalysisResult(data.report);
  } catch (e) {
    target.innerHTML = '<div style="padding:48px 0;font-size:10px;color:#64748b">加载失败</div>';
  }
}

function renderDomainAnalysisResult(report) {
  var target = document.getElementById('da-analysis-result');
  if (!target) return;
  var ds = report.domain_summary || [];
  var allF = report.all_findings || [];

  var domainMap = {};
  ds.forEach(function(d) {
    domainMap[d.name] = { count: d.count, high: d.high, mid: d.mid, findings: d.findings || [] };
  });

  var domainNames = Object.keys(domainMap).sort(function(a, b) {
    return (domainMap[b].high * 3 + domainMap[b].mid * 2 + domainMap[b].count) - (domainMap[a].high * 3 + domainMap[a].mid * 2 + domainMap[a].count);
  });

  var totalDomains = domainNames.length;
  var triggeredDomains = domainNames.filter(function(n) { return domainMap[n].count > 0; }).length;
  var highTotal = allF.filter(function(f) { return f.level === '极高风险' || f.level === '高风险'; }).length;
  var midTotal = allF.filter(function(f) { return f.level === '中风险'; }).length;

  var html = '<div id="da-result">'
    + '<h3 style="font-size:10px;font-weight:700;color:#16233a;margin:0 0 6px;display:flex;align-items:center;justify-content:space-between">'
    + '<span>四、本次域分析结果</span>'
    + '<span style="font-size:10px;font-weight:400">'
    + '<a href="#" onclick="expandAllDomains();return false" style="color:#2563eb;margin-right:8px">展开全部</a>'
    + '<a href="#" onclick="collapseAllDomains();return false" style="color:#64748b">收起全部</a>'
    + '</span></h3>'
    + '<p style="font-size:10px;color:#64748b;margin:0 0 10px">共 ' + totalDomains + ' 个分析域执行完毕，' + triggeredDomains + ' 个域产生发现，合计 ' + allF.length + ' 条发现（高风险 ' + highTotal + ' · 中风险 ' + midTotal + '）</p>'

    // 统计卡片
    + '<div style="display:flex;gap:12px;margin-bottom:10px">'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:10px;font-weight:700;color:#16233a">' + totalDomains + '</div><div style="font-size:10px;color:#64748b;margin-top:4px">分析域</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:10px;font-weight:700;color:#2563eb">' + triggeredDomains + '</div><div style="font-size:10px;color:#64748b;margin-top:4px">已触发</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:10px;font-weight:700;color:#dc2626">' + highTotal + '</div><div style="font-size:10px;color:#64748b;margin-top:4px">高风险</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fffbeb;border-radius:8px"><div style="font-size:10px;font-weight:700;color:#f59e0b">' + midTotal + '</div><div style="font-size:10px;color:#64748b;margin-top:4px">中风险</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:10px;font-weight:700;color:#16233a">' + allF.length + '</div><div style="font-size:10px;color:#64748b;margin-top:4px">合计发现</div></div>'
    + '</div>'

    + '<h4 style="font-size:10px;font-weight:600;color:#64748b;margin:0 0 10px">域概览（按风险权重排序）</h4>';

  if (domainNames.length === 0) {
    html += '<div style="color:#64748b;font-size:10px;padding:24px 0">无域分析数据</div>';
  } else {
    domainNames.forEach(function(name, di) {
      var d = domainMap[name];
      var hasFindings = d.count > 0;
      var riskLabel = d.high > 0 ? '高风险' : (d.mid > 0 ? '中风险' : (hasFindings ? '信息' : '未触发'));
      var riskColor = d.high > 0 ? '#dc2626' : (d.mid > 0 ? '#f59e0b' : (hasFindings ? '#22c55e' : '#64748b'));

      html += '<div style="border-bottom:1px solid #f1f5f9;padding:12px 0;cursor:' + (hasFindings ? 'pointer' : 'default') + '" onclick="' + (hasFindings ? 'toggleDomainDetail(' + di + ')' : '') + '">'
        + '<div style="display:flex;align-items:center;justify-content:space-between">'
        + '<div style="display:flex;align-items:center;gap:10px">'
        + '<span style="font-size:10px;font-weight:600;color:#16233a">' + escHtml(name) + '</span>'
        + '<span style="font-size:10px;padding:1px 6px;border-radius:3px;background:' + riskColor + '10;color:' + riskColor + ';font-weight:600">' + riskLabel + '</span>'
        + '</div>'
        + '<div style="display:flex;gap:16px;font-size:10px;color:#64748b">'
        + '<span>发现 <b style="color:#16233a">' + d.count + '</b></span>'
        + (d.high > 0 ? '<span style="color:#dc2626;font-weight:600">高' + d.high + '</span>' : '')
        + (d.mid > 0 ? '<span style="color:#f59e0b;font-weight:600">中' + d.mid + '</span>' : '')
        + (hasFindings ? '<span style="color:#64748b;font-size:10px">▸</span>' : '')
        + '</div>'
        + '</div>';

      // 展开的发现详情
      if (hasFindings) {
        html += '<div id="dd-' + di + '" style="display:none;margin-top:12px;padding:12px 16px;background:#fff;border-radius:6px">';
        d.findings.forEach(function(f) {
          var lvlColor = f.level === '极高风险' || f.level === '高风险' ? '#dc2626' : (f.level === '中风险' ? '#f59e0b' : '#22c55e');
          var lvlBg = f.level === '极高风险' || f.level === '高风险' ? '#fef2f2' : (f.level === '中风险' ? '#fffbeb' : '#f0fdf4');
          var dt = typeof f.detail === 'object' && f.detail.summary ? f.detail.summary : (f.detail || '');
          var trace = f._trace || {};
          html += '<div style="padding:10px 12px;margin-bottom:6px;background:' + lvlBg + ';border-radius:6px;border-left:3px solid ' + lvlColor + '">'
            + '<div style="font-size:10px;font-weight:600;color:#16233a;margin-bottom:4px">' + escHtml(f.type || '') + '</div>'
            + '<div style="font-size:10px;color:#3a4048;line-height:20px;margin-bottom:4px"><span class="d-find-detail" data-full="' + escHtml(dt).replace(/"/g, '&quot;') + '">' + escHtml(dt.substring(0, 300)) + '</span>'
            + (dt.length > 300 ? ' <a href="#" onclick="var s=this.previousElementSibling;s.textContent=s.getAttribute(\'data-full\');this.remove();return false" style="color:#2563eb;font-size:10px">展开全文</a>' : '')
            + '</div>'
            + '<div style="display:flex;gap:8px;align-items:center;font-size:10px;color:#64748b">'
            + '<span style="color:' + lvlColor + ';font-weight:600">' + (f.level || '') + '</span>'
            + '<span>score:' + (f.score || '-') + '</span>'
            + (f.rule_id ? '<span>规则:' + f.rule_id + '</span>' : '')
            + '</div>';
          // 自动内联推理链路——每条结论自带追责
          if (trace && trace.finding_id) {
            var pathText = (trace.detection_path||[]).join(' → ');
            var confColor = trace.confidence === '高' ? '#059669' : '#f59e0b';
            html += '<div style="margin-top:6px;padding:6px 8px;background:rgba(59,130,246,0.06);border-radius:4px;font-size:10px;color:#64748b;line-height:20px">'
              + '<span>📋 ' + escHtml(trace.phase_origin||'') + '</span>'
              + '<span style="margin-left:8px;color:' + confColor + '">可信度:' + escHtml(trace.confidence||'?') + '</span>'
              + '<span style="margin-left:8px">| 来源:' + escHtml((trace.data_sources||[]).slice(0,4).join('、')) + '</span>'
              + '<span style="margin-left:8px">| 规则:<code style="font-size:10px">' + escHtml((trace.rules_hit||[]).slice(0,3).join(',')) + '</code></span>'
              + '<br><span style="color:#64748b">' + escHtml(pathText) + '</span>'
              + '</div>';
          }
          html += '</div>';
        });
        html += '</div>';
      }

      html += '</div>';
    });
  }

  html += '</div>'; // da-result
  target.innerHTML = html;
}

// ==================== 页面3：跨域证据链 ====================

function loadCrossDomainStatic() {
  var target = document.getElementById('cde-static');
  fetch('/static/cross_domain_evidence.json?_t=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(chains) {
      window._allCrossChains = chains;
      renderCrossDomainStaticContent(chains);
    })
    .catch(function() {
      if (target) target.innerHTML = '<div style="padding:40px 0;font-size:10px;color:#64748b">跨域证据链定义加载失败</div>';
    });
}


function loadCrossDomainDynamic() {
  var target = document.getElementById('cde-dynamic');
  if (!target) return;

  getSharedAnalysis()
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (!data.ok) {
        target.innerHTML = '<div style="text-align:center;padding:20px;color:#64748b;margin-top:20px">暂无分析结果，请先运行一键稽查以获取动态证据链数据</div>';
        return;
      }
      renderCrossDomainDynamic(data.report);
    })
    .catch(function(e) {
      target.innerHTML = '<div style="text-align:center;padding:20px;color:#64748b;margin-top:20px">动态数据加载失败</div>';
    });
}



// ==================== 全局变量（供线索链/证据链页面共享） ====================
var _cachedDomainReport = null;
var _cachedFileParsingReport = null;
var _cachedFilterReport = null;
var _cachedAnalyzeReport = null;
var _allChains = [];
var _chainDynamic = null;
var _allClueChains = [];
var _allEvidenceChains = [];
var _allCrossChains = null;

// ==================== 页面：线索链 ====================
function renderChainsPage(container) {
  if (!container) return;
  window.currentModule = '线索链';
  window._skipModuleHeader = true;

  var h = '';
  h += '<style>'
    + '.cl{max-width:900px;margin:0 auto;padding:20px 28px;font-family:-apple-system,"Microsoft YaHei",sans-serif}'
    + '.cl-sub{font-size:10px;color:#64748b;margin:0 0 16px;line-height:1.8}'
    + '.cl-chain{padding:10px 0;margin-bottom:10px;border-bottom:1px solid #eef2f6}'
    + '</style>';

  h += '<div class="cl">';
  h += '<div id="chains-body"></div>';
  h += '</div>';
  container.innerHTML = h;
  _allClueChains = null;
  setTimeout(function(){ loadChainsData(); }, 50);
}

async function loadChainsData() {
  var target = document.getElementById('chains-body');
  try {
    var resp = await fetch('/static/cross_domain_clues.json?_t=' + Date.now());
    var clueChains = await resp.json();

    // 加载动态触发状态
    await loadChainDynamicStatus();

    _allClueChains = clueChains;
    renderChainsList(clueChains);
  } catch (e) {
    if (target) target.innerHTML = '<div style="text-align:center;padding:20px;color:#dc2626">加载失败: ' + e.message + '</div>';
  }
}

async function loadChainDynamicStatus() {
  try {
    var data = await getSharedAnalysis();
    if (data.ok && data.report) {
      var comp = data.report.comprehensive || {};
      _chainDynamic = {
        chain_execution: comp.chain_execution || [],
        evidence_closures: comp.evidence_closures || [],
        closed_count: comp.closed_chain_count || 0,
        triggered_count: comp.chain_triggered_count || 0
      };
    } else {
      _chainDynamic = { chain_execution: [], evidence_closures: [], closed_count: 0, triggered_count: 0 };
    }
  } catch(e) { _chainDynamic = { chain_execution: [], evidence_closures: [], closed_count: 0, triggered_count: 0 }; }
}

function renderChainsList(chains) {
  var target = document.getElementById('chains-body');
  if (!target) return;
  var esc = typeof escHtml === 'function' ? escHtml : function(s){ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;'); };
  var html = '<div style="font-size:10px;line-height:2.2">';
  chains.forEach(function(c,ci){
    var steps = (c.investigation_path||[]).length;
    var cat = c.category||'';
    var cid = 'clue-' + ci;
    html += '<div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid #f1f5f9;cursor:pointer" onclick="var d=document.getElementById(\''+cid+'\');d.style.display=d.style.display===\'none\'?\'\':\'none\'">';
    html += '<span style="color:#94a3b8;min-width:24px">#'+(ci+1)+'</span>';
    html += '<span style="flex:1;color:#0f172a">'+esc(c.name||'')+'</span>';
    html += '<span style="color:#64748b;font-size:9px">'+esc(cat)+'</span>';
    html += '<span style="color:#94a3b8;font-size:9px">'+steps+'步</span>';
    html += '<span style="color:#94a3b8">\u25b8</span>';
    html += '</div>';
    html += '<div id="'+cid+'" style="display:none;padding:10px 0 10px 24px;font-size:10px;line-height:1.8;color:#475569">';
    if(c.description) html += '<div style="margin-bottom:10px;color:#64748b">'+esc(c.description)+'</div>';
    if(c.trigger_keywords) html += '<div style="margin-bottom:6px"><b>触发关键词:</b> '+(c.trigger_keywords||[]).join('、')+'</div>';
    if(c.investigation_path&&c.investigation_path.length){
      html += '<div style="margin-bottom:6px"><b>调查路径 ('+c.investigation_path.length+'步):</b></div>';
      c.investigation_path.forEach(function(s,si){
        var stepName = s.name||s.step||'步骤'+(si+1);
        var stepDesc = s.description||s.desc||s.action||'';
        html += '<div style="padding:4px 0">'+(si+1)+'. '+esc(stepName)+'：'+esc(stepDesc)+'</div>';
      });
    }
    if(c.suggestion) html += '<div style="margin-top:8px;color:#94a3b8">'+esc(c.suggestion)+'</div>';
    html += '</div>';
  });
  html += '</div>';
  target.innerHTML = html;
}function renderEvidenceList(chains) {
  var target = document.getElementById('evidence-body');
  if (!target) return;
  var esc = typeof escHtml === 'function' ? escHtml : function(s){ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;'); };
  var html = '<div style="font-size:10px;line-height:2.2">';
  chains.forEach(function(c,ci){
    var dims = (c.dimensions||[]).length;
    var cat = c.category||'';
    var cid = 'evid-' + ci;
    html += '<div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid #f1f5f9;cursor:pointer" onclick="var d=document.getElementById(\''+cid+'\');d.style.display=d.style.display===\'none\'?\'\':\'none\'">';
    html += '<span style="color:#94a3b8;min-width:24px">#'+(ci+1)+'</span>';
    html += '<span style="flex:1;color:#0f172a">'+esc(c.name||'')+'</span>';
    html += '<span style="color:#64748b;font-size:9px">'+esc(cat)+'</span>';
    html += '<span style="color:#94a3b8;font-size:9px">'+(c.min_evidence||'?')+'源\u00d7'+dims+'维</span>';
    html += '<span style="color:#94a3b8">\u25b8</span>';
    html += '</div>';
    html += '<div id="'+cid+'" style="display:none;padding:10px 0 10px 24px;font-size:10px;line-height:1.8;color:#475569">';
    if(c.description) html += '<div style="margin-bottom:10px;color:#64748b">'+esc(c.description)+'</div>';
    html += '<div style="margin-bottom:6px"><b>要求\u2265</b> '+c.min_evidence+' <b>个独立数据源同时匹配</b> | '+(c.dimensions||[]).length+' <b>个验证维度</b></div>';
    if(c.dimensions&&c.dimensions.length){
      html += '<div style="margin-bottom:6px"><b>验证维度:</b></div>';
      c.dimensions.forEach(function(d){
        html += '<div style="padding:2px 0">\u00b7 '+esc(d)+'</div>';
      });
    }
    if(c.trigger_keywords) html += '<div style="margin-top:6px"><b>触发关键词:</b> '+(c.trigger_keywords||[]).join('、')+'</div>';
    if(c.suggestion) html += '<div style="margin-top:8px;color:#94a3b8">'+esc(c.suggestion)+'</div>';
    html += '</div>';
  });
  html += '</div>';
  target.innerHTML = html;
}
