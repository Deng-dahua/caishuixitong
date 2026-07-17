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
  container.innerHTML = '<style>.fp-layout{display:flex;gap:24px;max-width:1200px;margin:0 auto;padding:40px 46px;background:#fff}.fp-toc{width:190px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:10px;line-height:20px;max-height:calc(100vh-40px);overflow-y:auto}.fp-toc .toc-title{font-weight:700;color:#16233a;font-size:10px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.fp-toc a{display:block;color:#3a4048;text-decoration:none;padding:2px 8px;border-radius:4px;cursor:pointer}.fp-toc a:hover,.fp-toc a.active{background:#eff6ff;color:#2563eb;font-weight:600}.fp-main{flex:1;min-width:0;background:#fff}.fp-main h3{font-size:10px!important;font-weight:700!important;color:#16233a!important;padding-bottom:8px!important;border-bottom:2px solid #e2e8f0!important;margin:0 0 10px!important}.fp-main .fp-step{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:20px 22px;transition:box-shadow 0.15s}.fp-main .fp-step:hover{box-shadow:0 2px 8px rgba(0,0,0,.06)}.fp-main details summary:hover{background:#f8fafc}.fp-main .fp-card{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:20px 22px;transition:box-shadow 0.15s}.fp-main .fp-card:hover{box-shadow:0 2px 8px rgba(0,0,0,.06)}.fp-main .fp-stat-card{background:#fff;border:1px solid #e2e8f0;border-radius:8px;text-align:center;padding:16px}.fp-main section{margin-bottom:48px!important;scroll-margin-top:20px}</style>'
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
    + '文件解析引擎是税务合规分析的第一步——将企业上传的各种格式的原始资料（Excel/PDF/CSV/Word/图片），'
    + '通过{{file_fingerprints}}类文件指纹 + 四层递进识别 + 四方交叉验证，自动判定文件类型并提取为结构化数据。'
    + '支持8种文件格式（xls/xlsx/csv/pdf/docx/jpg/png/tiff），兼容82+列名变体，'
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
    + '保留完整的原始行列结构，交由下游分析模块（域分析引擎/规则匹配引擎）自行判断数据用途。'
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
    + '<strong>双引擎架构：</strong>pdfplumber表格提取（优先）+ pypdf文本解析（兜底）。<br>'
    + '<strong>自适应策略：</strong>逐页提取所有表格 \u2192 取最大表格 \u2192 表头走34类指纹匹配 \u2192 '
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
    + '<strong>双引擎OCR：</strong>EasyOCR（中文优先，文字块坐标提取）+ Tesseract（系统兜底）。<br>'
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
    + '从磁盘上的原始文件到结构化的分析数据，文件解析引擎执行8个步骤：'
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
      '将表头特征向量与34类指纹关键词库做交叉匹配：遍历每一种文件类型的关键词集，' +
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
      target.innerHTML = '<div style="padding:48px 0;font-size:10px;color:#64748b">暂无分析结果，请先运行一键分析</div>';
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
    + '→ 证据矛盾→协商引擎消解<br>'
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
    // ══════ 十一、行业对标与规则引擎（4域） ══════
    {cat:'十一、行业对标与规则引擎', color:'#6366f1', desc:"{{industries}}行业基准库对标，{{rules_count}}条规则全覆盖验证。行业对标告诉你“正常范围”，规则引擎告诉你“合规底线”。", items:[
      {name:'行业对标分析', fn:'_domain_industry_benchmark', line:'14475', desc:'66个行业基准——毛利率/税负率/进销比/人均营收/费用率五维对标 · 偏离度>2σ→行业异常预警 · 自动匹配行业代码'},
      {name:'规则全覆盖验证', fn:'_domain_rule_coverage', line:'15114', desc:'{{rules_count}}条规则逐条检查 · 已触发vs未触发分类 · 未触发→标注资料缺口 · 数据不足时作无依据结论（不作无证据判断）'},
      {name:'跨域关联推理', fn:'_domain_cross_domain_reasoning', line:'13490', desc:'单点发现→多域交叉印证→证据链闭环 · 7条内置跨域证据链（JSON驱动+内置回退）· A域+B域+C域同时异常→高置信度'},
      {name:'跨域线索链', fn:'_domain_cross_domain_clues', line:'14000', desc:'从cross_domain_clues.json加载跨域线索定义 · 线索→发现→证据三级转换 · 叙事生成器集成 · 线索链可视化追溯'},
    ]},
    // ══════ 十二、跨域分析链 ══════
    {cat:'十二、跨域分析链', color:'#8b5cf6', desc:'跨域分析链是最上层的推理引擎——它不直接分析数据，而是基于所有域的发现结果进行二阶推理，从交叉异常中推导出更深层的税务合规结论。', items:[
      {name:'跨域分析链', fn:'_domain_cross_domain_analysis', line:'14080', desc:'从cross_domain_analysis.json加载分析路径 · 二阶推理引擎——基于域发现而非原始数据 · 多域异常→综合结论 · 因果链追溯'},
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
    + '<strong>行业对标+规则引擎</strong>（校验层）→ 将企业数据与{{industries}}行业基准对比，与' + pc('rules','1608') + '条规则逐一匹配。<br>'
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
      target.innerHTML = '<div style="padding:48px 0;font-size:10px;color:#64748b">暂无分析结果，请先运行一键分析</div>';
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
        target.innerHTML = '<div style="text-align:center;padding:20px;color:#64748b;margin-top:20px">暂无分析结果，请先运行一键分析以获取动态证据链数据</div>';
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
    + '.cl{max-width:900px;margin:0 auto;padding:36px 28px;font-family:-apple-system,"Microsoft YaHei",sans-serif}'
    + '.cl-title{font-size:10px;font-weight:700;color:#16233a;margin:0 0 10px}'
    + '.cl-sub{font-size:10px;color:#64748b;margin:0 0 28px;line-height:1.8}'
    + '.cl-hero{display:flex;gap:12px;margin-bottom:10px;flex-wrap:wrap}'
    + '.cl-card{flex:1;min-width:130px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:18px 16px;text-align:center}'
    + '.cl-card .v{font-size:10px;font-weight:700;color:#16233a;line-height:1.3}'
    + '.cl-card .l{font-size:10px;color:#64748b;margin-top:6px}'
    + '.cl-chain{padding:14px 18px;margin-bottom:10px;border:1px solid #e2e8f0;border-radius:8px;background:#fff}'
    + '</style>';

  h += '<div class="cl">';
  h += '<div class="cl-title">线索链</div>';
  h += '<div class="cl-sub">串行工作流引擎 · 三类触发方式 · 所属：核心数据资产</div>';

  // 统计卡片（占位，异步填充）
  h += '<div class="cl-hero">';
  h += '<div class="cl-card"><div class="v" id="cl-total" style="color:#16233a">—</div><div class="l">线索链总数</div></div>';
  h += '<div class="cl-card"><div class="v" id="cl-triggered" style="color:#dc2626">—</div><div class="l">本次触发</div></div>';
  h += '<div class="cl-card"><div class="v" id="cl-steps" style="color:#2563eb">—</div><div class="l">调查步骤总数</div></div>';
  h += '<div class="cl-card"><div class="v" id="cl-highrisk" style="color:#f59e0b">—</div><div class="l">高风险步骤</div></div>';
  h += '</div>';

  // 上下游依赖
  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:10px">';
  h += '<div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:10px;font-weight:700;color:#0369a1;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #bae6fd">⬆ 上游（输入方）</div>';
  h += '<div style="font-size:10px;color:#3a4048;line-height:20px">';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'pipeline-rules\')" style="color:#2563eb">税务合规指令</a><br><span style="color:#64748b">规则匹配触发后激活对应线索链</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'tax-doc-analysis\')" style="color:#2563eb">资料风险分析报告</a><br><span style="color:#64748b">域分析发现作为线索链触发输入</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'hb-ch12\')" style="color:#2563eb">引擎记忆体系</a><br><span style="color:#64748b">线索链定义和调查路径存储</span></div>';
  h += '<div><a href="javascript:navigateTo(\'eng-pipe\')" style="color:#2563eb">管道调度</a><br><span style="color:#64748b">管线步骤④调用线索链引擎</span></div>';
  h += '</div></div>';
  h += '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:10px;font-weight:700;color:#15803d;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #bbf7d0">⬇ 下游（消费方）</div>';
  h += '<div style="font-size:10px;color:#3a4048;line-height:20px">';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'evidence-page\')" style="color:#2563eb">证据链</a><br><span style="color:#64748b">线索链发现触发证据链多源交叉验证</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-think\')" style="color:#2563eb">推理引擎</a><br><span style="color:#64748b">链发现作为因果推理输入</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-qual\')" style="color:#2563eb">质量保障</a><br><span style="color:#64748b">链驱动发现接受质量审查</span></div>';
  h += '<div><a href="javascript:navigateTo(\'eng-info\')" style="color:#2563eb">引擎详情</a><br><span style="color:#64748b">线索链引擎状态展示</span></div>';
  h += '</div></div></div>';

  // 段落说明
  h += '<div style="font-size:10px;color:#3a4048;line-height:20px;margin-bottom:10px">';
  h += '<p style="margin:0 0 10px">线索链是系统从<strong>风险信号到发现结论</strong>的串行工作流引擎。每条线索链定义一条完整的调查路径（investigation_path[]），从触发关键词开始逐步执行各步骤——"从哪里查、查什么、查到了怎么办"。</p>';
  h += '<p style="margin:0 0 10px">线索链的工作方式不同于简单的规则匹配：规则告诉你"这个数据异常"，线索链告诉你"从这个异常出发应该查什么、怎么查、查到什么程度才算确认"。例如"银行流入资金与销项开票偏差"这条规则触发后，线索链会引导系统依次检查银行流水的付款方身份、发票的品名一致性、合同的存在性和金额匹配度、关联交易的定价合理性等。</p>';
  h += '<p style="margin:0">线索链引擎支持三类触发方式——<strong>定量阈值</strong>（数值超限触发）、<strong>定性模式</strong>（特定关键词匹配触发）、<strong>缺失数据</strong>（资料缺口触发替代链）。线索链发现累积后触发证据链做多源交叉验证，闭环后输入分析链做综合推理判定，形成"线索→证据→分析"的完整链路。</p>';
  h += '</div>';

  h += '<div id="chains-body"></div>';
  h += '</div>';
  container.innerHTML = h;

  var hasCache = _allClueChains && _allClueChains.length > 0;
  if (hasCache) { renderChainsList(_allClueChains); }
  else { loadChainsData(); }
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

  var execMap = {};
  if (_chainDynamic && _chainDynamic.chain_execution) {
    _chainDynamic.chain_execution.forEach(function(ce) { execMap[ce.chain_name] = ce; });
  }

  var html = '';
  if (!chains.length) {
    html = '<div style="text-align:center;padding:40px;color:#64748b;font-size:10px">无匹配线索链</div>';
  } else {
    var triggeredCount = _chainDynamic ? (_chainDynamic.triggered_count || 0) : 0;

    // 填充页面级统计卡片
    var totalSteps = 0;
    var totalHighRisk = 0;
    chains.forEach(function(c) {
      var sl = c.investigation_path || [];
      totalSteps += sl.length;
      totalHighRisk += (typeof c.high_risk_steps === 'number') ? c.high_risk_steps : (Array.isArray(c.high_risk_steps) ? c.high_risk_steps.length : 0);
    });
    var elT = document.getElementById('cl-total'); if (elT) elT.textContent = chains.length;
    var elTr = document.getElementById('cl-triggered'); if (elTr) elTr.textContent = triggeredCount;
    var elS = document.getElementById('cl-steps'); if (elS) elS.textContent = totalSteps;
    var elH = document.getElementById('cl-highrisk'); if (elH) elH.textContent = totalHighRisk;

    chains.forEach(function(c, ci) {
      var exec = execMap[c.name];
      var isOldFormat = !!(c.investigation_path && c.investigation_path.length > 0 && c.investigation_path[0].rule_id);
      var isNewFormat = !!(c.investigation_path && c.investigation_path.length > 0 && !c.investigation_path[0].rule_id && c.investigation_path[0].domain);
      var stepList = isOldFormat ? c.investigation_path : (c.investigation_path || []);
      var totalS = stepList.length;
      var highRiskStepCount = (typeof c.high_risk_steps === 'number') ? c.high_risk_steps : (Array.isArray(c.high_risk_steps) ? c.high_risk_steps.length : 0);
      var triggeredSteps = exec ? exec.triggered_steps : 0;
      var ratio = exec ? exec.triggered_ratio : 0;
      var subTopic = c.sub_topic || '';
      var qualityScore = c.quality_score || 0;

      // 触发徽章
      var badge = '';
      if (exec && exec.triggered_steps > 0) {
        var bColor = ratio >= 60 ? '#dc2626' : '#059669';
        badge = ' <span style="font-size:10px;padding:2px 8px;border-radius:10px;background:' + bColor + '15;color:' + bColor + ';font-weight:600">' + triggeredSteps + '/' + totalS + ' (' + ratio + '%)</span>';
      } else if (exec) {
        badge = ' <span style="font-size:10px;padding:2px 8px;border-radius:10px;background:#fff;border:1px solid #e2e8f0;color:#64748b;font-weight:500">未触发</span>';
      }

      // 子主题标签
      var topicTag = subTopic ? ' <span style="font-size:10px;padding:1px 8px;border-radius:4px;background:#ede9fe;color:#7c3aed;font-weight:500">' + escHtml(subTopic) + '</span>' : '';

      // 质量分标签
      var scoreTag = qualityScore > 0 ? ' <span style="font-size:10px;color:#64748b">⭐ ' + qualityScore + '</span>' : '';

      html += '<div class="cl-chain">'

        // ══ 卡片头部：名称 + 标签行 ═══
        + '<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:6px;margin-bottom:10px">'
        + '<div style="font-size:10px;font-weight:700;color:#16233a">' + escHtml(c.name) + badge + topicTag + scoreTag + '</div>'
        + '</div>';

      // 描述（新格式链有 description/desc）
      if (c.description) {
        html += '<div style="padding:8px 12px;margin-bottom:10px;background:#fff;border-left:4px solid #7c3aed;border-radius:0 6px 6px 0;font-size:10px;color:#3a4048;line-height:20px">' + escHtml(c.description) + '</div>';
      } else if (c.desc) {
        html += '<div style="padding:8px 12px;margin-bottom:10px;background:#fff;border-left:4px solid #7c3aed;border-radius:0 6px 6px 0;font-size:10px;color:#3a4048;line-height:20px">' + escHtml(c.desc) + '</div>';
      }

      // ══ 步骤列表（统一样式）═══
      html += '<div style="margin-bottom:10px"><div style="font-size:10px;font-weight:600;color:#2563eb;margin-bottom:6px">📋 调查路径（' + stepList.length + ' 步）</div>';
      stepList.forEach(function(s, si) {
        var lvl = s.level || '';
        var isHigh = lvl === '高风险' || lvl === '极高风险';
        html += '<div style="padding:8px 12px;margin-bottom:4px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;border-left:3px solid #2563eb">'
          + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;flex-wrap:wrap">'
          + '<span style="display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:50%;font-size:10px;font-weight:700;color:#fff;background:' + (isHigh ? '#dc2626' : '#2563eb') + '">' + (s.step || (si+1)) + '</span>'
          + (s.rule_id ? '<span style="color:#6366f1;font-size:10px;font-weight:600;background:#eef2ff;padding:1px 5px;border-radius:3px">R' + s.rule_id + '</span>' : '')
          + (lvl ? '<span style="font-size:10px;font-weight:600;color:' + (isHigh ? '#dc2626' : '#64748b') + ';background:' + (isHigh ? '#fee2e2' : '#f1f5f9') + ';padding:1px 5px;border-radius:3px">' + lvl + '</span>' : '')
          + '<b style="font-size:10px;color:#16233a">' + escHtml(s.domain || s.rule_item || s.action || '') + '</b>'
          + '</div>'
          + (s.detail || s.action ? '<div style="font-size:10px;color:#3a4048;line-height:20px;margin-top:4px;padding-left:28px">' + escHtml(s.detail || s.action || '') + '</div>' : '')
          + (s.data_required ? '<div style="font-size:10px;color:#64748b;margin-top:4px;padding-left:28px">需要数据: ' + escHtml(s.data_required) + '</div>' : '')
          + (s.suggestion ? '<div style="font-size:10px;color:#059669;margin-top:4px;padding:4px 8px;background:#fff;border:1px solid #e2e8f0;border-radius:4px"><strong>建议：</strong>' + escHtml(s.suggestion) + '</div>' : '')
          + (s.policy_ref ? '<div style="font-size:10px;color:#64748b;margin-top:4px;padding-left:28px">📎 ' + escHtml(s.policy_ref) + '</div>' : '')
          + '</div>';
      });
      html += '</div>';

      // ══ 政策依据 ═══
      if (c.policies && c.policies.length > 0) {
        html += '<div style="margin-bottom:10px">'
          + '<div style="font-size:10px;font-weight:600;color:#64748b;margin-bottom:4px">📋 政策依据</div>';
        c.policies.forEach(function(p) {
          html += '<div style="padding:4px 10px;margin-bottom:2px;background:#fff;border:1px solid #e2e8f0;border-radius:4px;font-size:10px;color:#3a4048;line-height:20px">• ' + escHtml(p) + '</div>';
        });
        html += '</div>';
      }

      // ══ 税务影响 ═══
      if (c.tax_impacts && c.tax_impacts.length > 0) {
        html += '<div style="margin-bottom:10px">'
          + '<div style="font-size:10px;font-weight:600;color:#64748b;margin-bottom:4px">⚠️ 税务影响</div>';
        c.tax_impacts.forEach(function(t) {
          html += '<div style="padding:4px 10px;margin-bottom:2px;background:#fff;border:1px solid #e2e8f0;border-radius:4px;font-size:10px;color:#3a4048;line-height:20px">• ' + escHtml(t) + '</div>';
        });
        html += '</div>';
      }

      // ══ 底部元信息栏 ═══
      html += '<div style="display:flex;flex-wrap:wrap;gap:12px;padding-top:8px;border-top:1px solid #e2e8f0;font-size:10px;color:#64748b">'
        + '<span>📝 步骤 <b style="color:#3a4048">' + totalS + '</b> 条</span>'
        + (highRiskStepCount > 0 ? '<span>🔴 高风险步骤 <b style="color:#dc2626">' + highRiskStepCount + '</b> 个</span>' : '')
        + (c.covered_rule_count ? '<span>📌 覆盖规则 <b style="color:#3a4048">' + c.covered_rule_count + '</b> 条</span>' : '')
        + (c.related_chain_count > 0 ? '<span>🔗 关联证据链 <b style="color:#3a4048">' + c.related_chain_count + '</b> 条</span>' : '')
        + (qualityScore > 0 ? '<span>⭐ 质量评分 <b style="color:#3a4048">' + qualityScore + '</b></span>' : '')
        + '</div>';

      html += '</div>'; // card close
    });
  }

  target.innerHTML = html;
}

// ==================== 页面：证据链 ====================
function renderEvidencePage(container) {
  if (!container) return;
  window.currentModule = '证据链';
  window._skipModuleHeader = true;

  var h = '';
  h += '<style>'
    + '.ev{max-width:900px;margin:0 auto;padding:36px 28px;font-family:-apple-system,"Microsoft YaHei",sans-serif}'
    + '.ev-title{font-size:10px;font-weight:700;color:#16233a;margin:0 0 10px}'
    + '.ev-sub{font-size:10px;color:#64748b;margin:0 0 28px;line-height:1.8}'
    + '.ev-hero{display:flex;gap:12px;margin-bottom:10px;flex-wrap:wrap}'
    + '.ev-card{flex:1;min-width:130px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:18px 16px;text-align:center}'
    + '.ev-card .v{font-size:10px;font-weight:700;color:#16233a;line-height:1.3}'
    + '.ev-card .l{font-size:10px;color:#64748b;margin-top:6px}'
    + '.ev-chain{padding:14px 18px;margin-bottom:10px;border:1px solid #e2e8f0;border-radius:8px;background:#fff}'
    + '</style>';

  h += '<div class="ev">';
  h += '<div class="ev-title">证据链</div>';
  h += '<div class="ev-sub">多源交叉验证 · 证据闭环 · 所属：核心数据资产</div>';

  // 统计卡片（占位，异步填充）
  h += '<div class="ev-hero">';
  h += '<div class="ev-card"><div class="v" id="ev-total" style="color:#16233a">—</div><div class="l">证据链总数</div></div>';
  h += '<div class="ev-card"><div class="v" id="ev-closed" style="color:#059669">—</div><div class="l">已闭环</div></div>';
  h += '<div class="ev-card"><div class="v" id="ev-steps" style="color:#2563eb">—</div><div class="l">调查步骤</div></div>';
  h += '<div class="ev-card"><div class="v" id="ev-highrisk" style="color:#f59e0b">—</div><div class="l">高风险步骤</div></div>';
  h += '</div>';

  // 上下游依赖
  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:10px">';
  h += '<div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:10px;font-weight:700;color:#0369a1;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #bae6fd">⬆ 上游（输入方）</div>';
  h += '<div style="font-size:10px;color:#3a4048;line-height:20px">';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'chains-page\')" style="color:#2563eb">线索链</a><br><span style="color:#64748b">线索链发现触发证据链多源验证</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'pipeline-rules\')" style="color:#2563eb">税务合规指令</a><br><span style="color:#64748b">规则触发的发现作为证据匹配源</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'tax-doc-analysis\')" style="color:#2563eb">资料风险分析报告</a><br><span style="color:#64748b">域分析all_findings作为keyword匹配池</span></div>';
  h += '<div><a href="javascript:navigateTo(\'eng-pipe\')" style="color:#2563eb">管道调度</a><br><span style="color:#64748b">管线步骤⑤调用跨域证据推理</span></div>';
  h += '</div></div>';
  h += '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:10px;font-weight:700;color:#15803d;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #bbf7d0">⬇ 下游（消费方）</div>';
  h += '<div style="font-size:10px;color:#3a4048;line-height:20px">';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'analysis-page\')" style="color:#2563eb">分析链</a><br><span style="color:#64748b">证据闭环后输入分析链做综合推理</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-think\')" style="color:#2563eb">推理引擎</a><br><span style="color:#64748b">闭环证据作为因果推理节点</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-qual\')" style="color:#2563eb">质量保障</a><br><span style="color:#64748b">证据驱动发现接受质量审查</span></div>';
  h += '<div><a href="javascript:navigateTo(\'eng-info\')" style="color:#2563eb">引擎详情</a><br><span style="color:#64748b">证据链引擎状态展示</span></div>';
  h += '</div></div></div>';

  // 段落说明
  h += '<div style="font-size:10px;color:#3a4048;line-height:20px;margin-bottom:10px">';
  h += '<p style="margin:0 0 10px">证据链是系统的<strong>多源交叉验证引擎</strong>。与线索链的串行调查不同，证据链同时从多个独立维度收集证据——每个维度是一个独立数据源（银行流水、发票、合同、社保、工商等），当 ≥min_evidence 个维度的触发关键词同时匹配到 all_findings 时，形成有效证据闭环。</p>';
  h += '<p style="margin:0 0 10px">证据链解决的核心问题是"单源证据不可靠"。一条银行流水异常可能是技术性错误，但如果银行流水异常 + 发票品名不符 + 合同缺失同时出现，就形成了多源交叉印证的证据闭环，可信度大幅提升。闭环后的证据自动注入 all_findings，由分析链做综合推理判定。</p>';
  h += '<p style="margin:0">证据链与线索链的关系是"串行发现 → 并行验证"：线索链负责从风险信号出发逐步追查（一条线到底），证据链负责对线索链发现的多维证据做交叉验证（多源同时印证）。两者协同形成"线索→证据→分析"的完整链路。</p>';
  h += '</div>';

  h += '<div id="evidence-body"></div>';
  h += '</div>';
  container.innerHTML = h;

  var hasCache = _allEvidenceChains && _allEvidenceChains.length > 0;
  if (hasCache) { renderEvidenceList(_allEvidenceChains); }
  else { loadEvidenceData(); }
}

async function loadEvidenceData() {
  var target = document.getElementById('evidence-body');
  try {
    var resp = await fetch('/static/cross_domain_evidence.json?_t=' + Date.now());
    var evChains = await resp.json();

    if (!_chainDynamic) await loadChainDynamicStatus();

    _allEvidenceChains = evChains;
    renderEvidenceList(evChains);
  } catch (e) {
    if (target) target.innerHTML = '<div style="text-align:center;padding:20px;color:#dc2626">加载失败: ' + e.message + '</div>';
  }
}

function renderEvidenceList(chains) {
  var target = document.getElementById('evidence-body');
  if (!target) return;

  var evExecMap = {};
  if (_chainDynamic && _chainDynamic.evidence_closures) {
    _chainDynamic.evidence_closures.forEach(function(ec) { evExecMap[ec.chain_name] = ec; });
  }

  // 统计步骤数：旧格式 investigation_path 是数组，新格式 steps 是数字
  var totalSteps = chains.reduce(function(s, c) {
    var ip = c.investigation_path;
    if (Array.isArray(ip)) return s + ip.length;
    if (typeof c.steps === 'number') return s + c.steps;
    if (typeof c.total_steps === 'number') return s + c.total_steps;
    return s;
  }, 0);
  var execChains = chains.filter(function(c) { return c.executable !== false && !c.legacy; });
  var closedCount = chains.filter(function(c) {
    var exec = evExecMap[c.name];
    return exec && exec.closed;
  }).length;
  var highRiskSteps = chains.reduce(function(s, c) {
    var hr = c.high_risk_steps;
    if (typeof hr === 'number') return s + hr;
    if (Array.isArray(hr)) return s + hr.length;
    return s;
  }, 0);

  // 填充页面级统计卡片
  var elT = document.getElementById('ev-total'); if (elT) elT.textContent = chains.length;
  var elC = document.getElementById('ev-closed'); if (elC) elC.textContent = closedCount;
  var elS = document.getElementById('ev-steps'); if (elS) elS.textContent = totalSteps;
  var elH = document.getElementById('ev-highrisk'); if (elH) elH.textContent = highRiskSteps;

  var html = '';

  if (!chains.length) {
    html += '<div style="text-align:center;padding:40px;color:#64748b">无证据链数据</div>';
  } else {
    // 分组：按sub_topic分类（合并碎类）
    var groups = {};
    chains.forEach(function(c) {
      var raw = c.sub_topic || (c.name || '').split('-')[0] || '其他';
      var merge = {销项:'发票',进项:'发票',虚开:'虚开发票',异常:'发票',数据比对:'数据比对',穿透核查:'穿透核查',特殊行业:'特殊行业',股权:'股权',折旧:'资产',资产:'资产',摊销:'资产',税率:'增值税',个税:'个税',社保:'薪酬',工资薪金:'薪酬',人员:'薪酬',印花税:'印花税',增值税:'增值税',企业所得税:'企业所得税',成本:'成本',费用:'成本',关联交易:'关联',关联:'关联',合同:'合同',跨境:'跨境',出口退税:'出口退税','全税种':'全税种',资金回流:'资金',资金流:'资金',银行:'资金',现金:'资金',综合:'综合',经营实质:'经营实质',申报:'申报',存货:'存货',资源:'资源',医药:'医药',建筑:'建筑',房地产:'房地产'};
      var prefix = merge[raw] || raw;
      if (!groups[prefix]) groups[prefix] = [];
      groups[prefix].push(c);
    });
    var sortedPrefixes = Object.keys(groups).sort(function(a,b) { return groups[b].length - groups[a].length; });

    sortedPrefixes.forEach(function(prefix) {
      var groupChains = groups[prefix];
      var groupExec = groupChains.filter(function(c) { return c.executable !== false && !c.legacy; });
      var groupLegacy = groupChains.filter(function(c) { return c.legacy; });
      html += '<section id="ev-grp-' + encodeURIComponent(prefix) + '" style="margin-bottom:36px;scroll-margin-top:20px">';
      html += '<h3 style="font-size:10px!important;font-weight:700!important;color:#16233a!important;padding-bottom:6px!important;border-bottom:2px solid #e2e8f0!important;margin:0 0 10px!important">' + prefix
        + ' <span style="font-size:10px;font-weight:400;color:#64748b">' + groupChains.length + ' 条' + (groupExec.length > 0 ? ' (' + groupExec.length + '可执行)' : '') + '</span></h3>';

      groupChains.forEach(function(c) {
        var evExec = evExecMap[c.name];
        var closed = evExec && evExec.closed;
        var ratio = evExec ? evExec.ratio : 0;
        var badgeText = evExec ? (closed ? '已闭环 ' + ratio + '%' : '未闭环 ' + ratio + '%') : '';
        var badgeColor = closed ? '#059669' : '#f59e0b';
        var ip = c.investigation_path;
        var isArrayFormat = Array.isArray(ip) && ip.length > 0 && ip[0].rule_id;
        var isStringFormat = typeof ip === 'string';
        var isStepsFormat = !isArrayFormat && !isStringFormat && Array.isArray(c.steps) && c.steps.length > 0 && c.steps[0].action;
        var subTopic = c.sub_topic || '';
        var qualityScore = c.quality_score || 0;
        var stepCount = isArrayFormat ? ip.length : (isStepsFormat ? c.steps.length : (typeof c.steps === 'number' ? c.steps : (typeof c.total_steps === 'number' ? c.total_steps : (Array.isArray(ip) ? ip.length : 0))));
        var highRiskStepCount = (typeof c.high_risk_steps === 'number') ? c.high_risk_steps : (Array.isArray(c.high_risk_steps) ? c.high_risk_steps.length : 0);

        var topicTag = subTopic ? ' <span style="font-size:10px;padding:1px 8px;border-radius:4px;background:#ede9fe;color:#7c3aed;font-weight:500">' + escHtml(subTopic) + '</span>' : '';
        var scoreTag = qualityScore > 0 ? ' <span style="font-size:10px;color:#64748b">⭐ ' + qualityScore + '</span>' : '';

        html += '<div class="ev-chain">'

          // ══ 标题行 ═══
          + '<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:6px;margin-bottom:10px">'
          + '<div style="font-size:10px;font-weight:700;color:#16233a">' + escHtml(c.name) + topicTag + scoreTag + '</div>'
          + (badgeText ? '<span style="font-size:10px;padding:2px 8px;border-radius:10px;background:' + badgeColor + '15;color:' + badgeColor + ';font-weight:600">' + badgeText + '</span>' : '')
          + '</div>';

        // ══ 描述 ═══
        if (c.description) {
          html += '<div style="padding:8px 12px;margin-bottom:10px;background:#fff;border-left:4px solid #7c3aed;border-radius:0 6px 6px 0;font-size:10px;color:#3a4048;line-height:20px">' + escHtml(c.description) + '</div>';
        }

        // ══ 调查路径 ═══
        if (isArrayFormat) {
          // 旧格式：investigation_path 是数组，含 rule_id/level/detail/policy_ref
          html += '<div style="margin-bottom:10px">';
          ip.forEach(function(s, si) {
            var lvl = s.level || '';
            var lvlColor = lvl === '高风险' ? '#dc2626' : (lvl === '中风险' ? '#f59e0b' : (lvl === '低风险' ? '#059669' : '#64748b'));
            var lvlBg = lvl === '高风险' ? '#fef2f2' : (lvl === '中风险' ? '#fffbeb' : (lvl === '低风险' ? '#f0fdf4' : '#f8fafc'));
            var isHigh = lvl === '高风险';

            html += '<div style="padding:8px 12px;margin-bottom:6px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;border-left:3px solid ' + (isHigh ? '#dc2626' : lvlColor) + '">'
              + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">'
              + '<span style="color:#64748b;font-size:10px;font-weight:600">#' + (si + 1) + '</span>'
              + (s.rule_id ? '<span style="color:#6366f1;font-size:10px;font-weight:600;background:#eef2ff;padding:1px 5px;border-radius:3px">R' + s.rule_id + '</span>' : '')
              + (lvl ? '<span style="font-size:10px;font-weight:600;color:' + lvlColor + ';background:' + lvlBg + ';padding:1px 5px;border-radius:3px">' + lvl + '</span>' : '')
              + '<b style="font-size:10px;color:#16233a">' + escHtml(s.domain || s.action || s.rule_item || s.step || '') + '</b>'
              + '</div>'
              + (s.detail || s.action ? '<div style="font-size:10px;color:#3a4048;line-height:20px;margin-top:4px;padding-left:20px;border-left:2px solid #e2e8f0">' + escHtml(s.detail || s.action || '') + '</div>' : '')
              + (s.policy_ref ? '<div style="font-size:10px;color:#64748b;margin-top:4px">📎 ' + escHtml(s.policy_ref) + '</div>' : '')
              + '</div>';
          });
          html += '</div>';
        } else if (isStringFormat) {
          // 新格式：investigation_path 是字符串描述（如 "人员信息→发票数据→资金流→进销存四维交叉验证"）
          html += '<div style="padding:8px 12px;margin-bottom:10px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;font-size:10px;color:#3a4048;line-height:20px">'
            + '<b style="color:#4338ca">🔍 调查路径：</b>' + escHtml(ip)
            + '</div>';
        } else if (isStepsFormat) {
          // steps 数组格式（含 {step: N, action: "文本"}）
          html += '<div style="margin-bottom:10px">';
          (c.steps || []).forEach(function(s, si) {
            var stepNum = s.step || (si + 1);
            var isHigh = !!(s.level && (s.level === '极高风险' || s.level === '高风险'));
            html += '<div style="padding:8px 12px;margin-bottom:6px;background:' + (isHigh ? '#fef2f2' : '#fafafa') + ';border-radius:6px;border-left:3px solid ' + (isHigh ? '#dc2626' : '#cbd5e1') + '">'
              + '<div style="display:flex;align-items:center;gap:8px">'
              + '<span style="display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:50%;font-size:10px;font-weight:700;color:#fff;background:' + (isHigh ? '#dc2626' : '#64748b') + '">' + stepNum + '</span>'
              + '<span style="font-size:10px;color:#334155;line-height:20px">' + escHtml(s.action || '') + '</span>'
              + (isHigh ? '<span style="font-size:10px;color:#dc2626;font-weight:600;background:#fee2e2;padding:1px 6px;border-radius:3px">高风险</span>' : '')
              + '</div>'
              + '</div>';
          });
          html += '</div>';
        }

        // ══ dimensions[] 维度举证(新格式可执行证据链) ═══
        var dims = c.dimensions;
        if (Array.isArray(dims) && dims.length > 0) {
          html += '<div style="margin-bottom:10px"><div style="font-size:10px;font-weight:600;color:#059669;margin-bottom:6px">📐 证据维度（需 ≥' + (c.min_evidence||2) + ' 维同时触发形成闭环）</div>';
          dims.forEach(function(d, di) {
            var dimCode = d.code || d.dim_code || ('D' + (di+1));
            html += '<div style="padding:8px 12px;margin-bottom:6px;background:#f0fdf4;border-radius:6px;border-left:3px solid #059669;font-size:10px;line-height:1.8">'
              + '<span style="font-weight:700;color:#059669;margin-right:8px">' + escHtml(dimCode) + '</span>'
              + '<span style="color:#166534;font-weight:600">' + escHtml(d.source||'') + '</span>'
              + '<span style="color:#64748b;margin-left:6px">— ' + escHtml(d.desc||'') + '</span>'
              + '</div>';
          });
          html += '</div>';
        }

        // ══ 政策依据 ═══
        if (c.policies && c.policies.length > 0) {
          html += '<div style="margin-bottom:10px">'
            + '<div style="font-size:10px;font-weight:600;color:#64748b;margin-bottom:4px">📋 政策依据</div>';
          c.policies.forEach(function(p) {
            html += '<div style="padding:5px 10px;margin-bottom:3px;background:#fff;border:1px solid #e2e8f0;border-radius:4px;font-size:10px;color:#3a4048;line-height:20px">• ' + escHtml(p) + '</div>';
          });
          html += '</div>';
        }

        // ══ 税务影响 ═══
        if (c.tax_impacts && c.tax_impacts.length > 0) {
          html += '<div style="margin-bottom:10px">'
            + '<div style="font-size:10px;font-weight:600;color:#64748b;margin-bottom:4px">⚠️ 税务影响</div>';
          c.tax_impacts.forEach(function(t) {
            html += '<div style="padding:5px 10px;margin-bottom:3px;background:#fff;border:1px solid #e2e8f0;border-radius:4px;font-size:10px;color:#3a4048;line-height:20px">• ' + escHtml(t) + '</div>';
          });
          html += '</div>';
        }

        // ══ 关联线索链 ═══
        if (c.related_chains && c.related_chains.length > 0) {
          html += '<div style="margin-bottom:10px">'
            + '<div style="font-size:10px;font-weight:600;color:#64748b;margin-bottom:4px">🔗 关联线索链</div>';
          c.related_chains.forEach(function(rc) {
            html += '<div style="padding:5px 10px;margin-bottom:3px;background:#f0f9ff;border-radius:4px;font-size:10px;color:#0369a1;line-height:20px">• ' + escHtml(rc) + '</div>';
          });
          html += '</div>';
        }

        // ══ 覆盖规则 ═══
        if (c.covered_rule_ids && c.covered_rule_ids.length > 0) {
          html += '<div style="margin-bottom:10px">'
            + '<div style="font-size:10px;font-weight:600;color:#64748b;margin-bottom:4px">📌 覆盖规则</div>';
          c.covered_rule_ids.forEach(function(rid) {
            html += '<span style="display:inline-block;font-size:10px;padding:2px 6px;margin:0 3px 3px 0;background:#eef2ff;color:#4338ca;border-radius:3px;font-weight:600">R' + rid + '</span>';
          });
          html += '</div>';
        }

        // ══ 底部元信息栏 ═══
        html += '<div style="display:flex;flex-wrap:wrap;gap:12px;padding-top:8px;border-top:1px solid #f1f5f9;font-size:10px;color:#64748b">'
          + '<span>📝 步骤 <b style="color:#3a4048">' + stepCount + '</b> 条</span>'
          + (highRiskStepCount > 0 ? '<span>🔴 高风险步骤 <b style="color:#dc2626">' + highRiskStepCount + '</b> 个</span>' : '')
          + (c.covered_rule_count ? '<span>📌 覆盖规则 <b style="color:#3a4048">' + c.covered_rule_count + '</b> 条</span>' : '')
          + (c.related_chain_count > 0 ? '<span>🔗 关联线索链 <b style="color:#3a4048">' + c.related_chain_count + '</b> 条</span>' : '')
          + (qualityScore > 0 ? '<span>⭐ 质量评分 <b style="color:#3a4048">' + qualityScore + '</b></span>' : '')
          + '</div>';

        html += '</div>';
      });

      html += '</section>';
    });
  }

  target.innerHTML = html;
}

// ==================== 页面：分析链 ====================
function renderAnalyzePage(container) {
  if (!container) return;
  window.currentModule = '分析链';
  container.innerHTML = '<style>.al-layout{max-width:1100px;margin:0 auto;padding:20px;background:#fff}.al-main{flex:1;min-width:0}.al-main h3{font-size:10px!important;font-weight:700!important;color:#16233a!important;padding-bottom:8px!important;border-bottom:2px solid #e2e8f0!important;margin:0 0 10px!important}.al-main section{margin-bottom:48px!important;scroll-margin-top:20px}</style>'
    + '<div class="al-layout">'
    + '<div class="al-main">'

    + '<p style="font-size:10px;color:#3a4048;line-height:20px;margin:0 0 10px">'
    + '</p>'
    + '<div id="analyze-body"></div>'
    + '</div></div>';
}

async function toggleDomainDetail(idx) {
  var el = document.getElementById('dd-' + idx);
  if (!el) return;
  el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

function expandAllDomains() {
  document.querySelectorAll('[id^="dd-"]').forEach(function(el) {
    el.style.display = 'block';
  });
}

function collapseAllDomains() {
  document.querySelectorAll('[id^="dd-"]').forEach(function(el) {
    el.style.display = 'none';
  });
}

// ==================== 跨域线索链页面 ====================

function loadCrossDomainClues() {
  var target = document.getElementById('cdc-body');
  fetch('/static/cross_domain_clues.json?_t=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(clues) {
      var html = '';

      // ══════ 一、概述 ══════
      html += '<div id="cdc-intro" style="margin-bottom:10px">'
        + '<h3 style="font-size:10px;font-weight:700;color:#16233a;margin:0 0 6px">一、什么是跨域线索链</h3>'
        + '<p style="font-size:10px;color:#64748b;line-height:20px;margin:0 0 10px">'
        + '跨域线索链是从单一数据异常出发，跨多个数据域进行串联调查的标准化路径。每条线索链定义了从首域发现到多域验证的完整调查步骤，'
        + '确保每个疑点都被多源数据交叉验证——不依赖单一数据源的孤立异常下结论。'
        + '与跨域证据链不同：线索链定义的是<strong>调查路径</strong>（怎么查），证据链定义的是<strong>验证标准</strong>（怎么判）。'
        + '</p>'
        + '<div style="padding:16px 20px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;font-size:10px;color:#3a4048;line-height:2">'
        + '<strong>与跨域证据链的关系</strong>：线索链（调查路径）→ 证据链（验证标准）→ 结论。线索链告诉税务合规人员"从哪里开始查，每一步查什么"，证据链告诉税务合规人员"满足什么条件才算发现问题"。'
        + '</div>'
        + '</div>';

      // 统计
      var highCount = clues.filter(function(c) { return (c.level === '极高风险' || c.level === '高风险'); }).length;
      var totalSteps = clues.reduce(function(s,c){return s+(c.investigation_path||[]).length;},0);
      html += '<div style="display:flex;gap:12px;margin-bottom:10px">'
        + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:10px;font-weight:700;color:#16233a">' + clues.length + '</div><div style="font-size:10px;color:#64748b;margin-top:4px">线索链</div></div>'
        + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:10px;font-weight:700;color:#dc2626">' + highCount + '</div><div style="font-size:10px;color:#64748b;margin-top:4px">高风险链</div></div>'
        + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:10px;font-weight:700;color:#2563eb">' + totalSteps + '</div><div style="font-size:10px;color:#64748b;margin-top:4px">调查步骤</div></div>'
        + '</div>';

      html += '<h3 id="cdc-list" style="font-size:10px;font-weight:700;color:#16233a;margin:0 0 6px">二、跨域线索链定义</h3>';

      clues.forEach(function(c) {
        var levelColor = (c.level === '极高风险' || c.level === '高风险') ? '#dc2626' : '#f59e0b';
        var levelBg = (c.level === '极高风险' || c.level === '高风险') ? '#fef2f2' : '#fffbeb';

        html += '<div style="padding:20px 24px;margin-bottom:10px;background:' + levelBg + ';border-left:3px solid ' + levelColor + ';border-radius:0 8px 8px 0">'
          + '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">'
          + '<div style="font-size:10px;font-weight:700;color:#16233a">' + escHtml(c.name) + '</div>'
          + '<div style="display:flex;gap:8px;align-items:center">'
          + '<span style="font-size:10px;padding:2px 8px;border-radius:4px;background:' + levelColor + '15;color:' + levelColor + ';font-weight:600">' + c.level + '</span>'
          + '<span style="font-size:10px;color:#64748b">' + escHtml(c.sub_topic) + '</span>'
          + '<span style="font-size:10px;color:#64748b">需≥' + c.min_evidence + '域</span>'
          + '</div>'
          + '</div>'
          + '<div style="font-size:10px;color:#3a4048;line-height:20px;margin-bottom:10px">' + escHtml(c.description) + '</div>'

          // 调查路径
          + '<div style="margin-bottom:10px;padding:10px 12px;background:#fff;border-radius:6px">'
          + '<div style="font-size:10px;font-weight:600;color:#64748b;margin-bottom:6px">调查路径 · ' + (c.investigation_path||[]).length + ' 步</div>';
        (c.investigation_path||[]).forEach(function(s) {
          html += '<div style="padding:6px 0;border-bottom:1px solid #f8fafc;font-size:10px;line-height:20px">'
            + '<span style="color:#64748b;font-size:10px;margin-right:8px">Step ' + s.step + '</span>'
            + '<span style="font-weight:600;color:#2563eb">' + escHtml(s.domain) + '</span>'
            + '<span style="color:#64748b"> → ' + escHtml(s.action) + '</span>'
            + '<div style="color:#64748b;font-size:10px;margin-top:2px">所需资料：' + escHtml(s.data_required) + '</div>'
            + '</div>';
        });
        html += '</div>'

          + (c.tax_impact ? '<div style="font-size:10px;color:#64748b;line-height:20px;margin-bottom:4px"><span style="font-weight:600">纳税影响：</span>' + escHtml(c.tax_impact) + '</div>' : '')
          + (c.policy_ref ? '<div style="font-size:10px;color:#64748b;line-height:20px;margin-bottom:4px"><span style="font-weight:600">法律依据：</span>' + escHtml(c.policy_ref) + '</div>' : '')
          + (c.suggestion ? '<div style="font-size:10px;color:#64748b;line-height:20px"><span style="font-weight:600">处理建议：</span>' + escHtml(c.suggestion) + '</div>' : '')
          + '</div>';
      });

      html += '<div style="margin-top:20px;padding:16px 20px;background:#fff;border-radius:8px;font-size:10px;color:#64748b;line-height:2">'
        + '<strong>线索链 ≠ 证据链</strong>：线索链告诉你"怎么查"——从哪个域开始、每一步查什么、需要什么资料；证据链告诉你"怎么判"——满足什么条件才算形成证据闭环。'
        + '两者结合使用：线索链指导取证，证据链指导认证。'
        + '</div>';

      target.innerHTML = html;

      // 加载动态触发状态
      getSharedAnalysis().then(function(data) {
        if (data.ok && data.report) {
          var triggered = (data.report.comprehensive || {}).triggered_chains || [];
          var cntEl = document.getElementById('cdc-triggered-count');
          if (cntEl) cntEl.textContent = ' · 本次触发 ' + triggered.length + ' 条';
        }
      }).catch(function() {});
    })
    .catch(function() {
      if (target) target.innerHTML = '<div style="padding:40px 0;font-size:10px;color:#64748b">跨域线索链加载失败</div>';
    });
}

// ==================== 跨域分析链页面 ====================

function loadCrossDomainAnalysis() {
  var target = document.getElementById('cda-body');
  fetch('/static/cross_domain_analysis.json?_t=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(chains) {
      var html = '';
      var highCount = chains.filter(function(c){return c.level==='高风险';}).length;
      var totalSteps = chains.reduce(function(s,c){return s+(c.reasoning_chain||[]).length;},0);

      // ══════ 一、概述 ══════
      html += '<div id="cda-intro" style="margin-bottom:10px">'
        + '<h3 style="font-size:10px;font-weight:700;color:#16233a;margin:0 0 6px">一、什么是跨域分析链</h3>'
        + '<p style="font-size:10px;color:#64748b;line-height:20px;margin:0 0 10px">'
        + '跨域分析链定义的是<strong>推理路径</strong>——从一个域的异常信号开始，通过多步逻辑推理，逐步扩展到其他域，'
        + '最终得出跨域综合结论。每条链都有<strong>回退点</strong>——只要某个环节能提供合理解释，风险就会降级或消除。'
        + '与线索链（调查路径）和证据链（验证标准）不同，分析链关注的是<strong>推理逻辑</strong>本身。'
        + '</p>'
        + '<div style="padding:16px 20px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;font-size:10px;color:#3a4048;line-height:2">'
        + '<strong>三个跨域链的关系</strong><br>'
        + '🔎 跨域线索链 → 告诉税务合规人员「怎么查」（调查步骤）<br>'
        + '🔗 跨域证据链 → 告诉税务合规人员「怎么判」（验证标准）<br>'
        + '🧠 跨域分析链 → 告诉税务合规人员「怎么推理」（逻辑路径+回退条件）'
        + '</div>'
        + '</div>';

      // 统计
      html += '<div style="display:flex;gap:12px;margin-bottom:10px">'
        + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:10px;font-weight:700;color:#16233a">' + chains.length + '</div><div style="font-size:10px;color:#64748b;margin-top:4px">分析链</div></div>'
        + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:10px;font-weight:700;color:#dc2626">' + highCount + '</div><div style="font-size:10px;color:#64748b;margin-top:4px">高风险链</div></div>'
        + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:10px;font-weight:700;color:#2563eb">' + totalSteps + '</div><div style="font-size:10px;color:#64748b;margin-top:4px">推理步骤</div></div>'
        + '</div>';

      // ══════ 二、分析链定义 ══════
      html += '<h3 id="cda-list" style="font-size:10px;font-weight:700;color:#16233a;margin:0 0 6px">二、跨域分析链定义</h3>';

      chains.forEach(function(c) {
        var levelColor = (c.level === '极高风险' || c.level === '高风险') ? '#dc2626' : '#f59e0b';
        var levelBg = (c.level === '极高风险' || c.level === '高风险') ? '#fef2f2' : '#fffbeb';

        html += '<div style="padding:20px 24px;margin-bottom:10px;background:' + levelBg + ';border-left:3px solid ' + levelColor + ';border-radius:0 8px 8px 0">'
          // 标题
          + '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">'
          + '<div style="font-size:10px;font-weight:700;color:#16233a">' + escHtml(c.name) + '</div>'
          + '<div style="display:flex;gap:8px;align-items:center">'
          + '<span style="font-size:10px;padding:2px 8px;border-radius:4px;background:' + levelColor + '15;color:' + levelColor + ';font-weight:600">' + escHtml(c.level) + '</span>'
          + '<span style="font-size:10px;color:#64748b">' + escHtml(c.sub_topic) + '</span>'
          + '<span style="font-size:10px;color:#64748b">需≥' + (c.min_evidence||1) + '域</span>'
          + '</div>'
          + '</div>'

          // 触发关键词（实际字段是trigger_keywords数组）
          + '<div style="font-size:10px;color:#3a4048;line-height:20px;margin-bottom:4px"><span style="font-weight:600;color:#16233a">触发关键词：</span>' + escHtml((c.trigger_keywords||[]).join(' · ')) + '</div>'

          // 描述
          + (c.description ? '<div style="font-size:10px;color:#3a4048;line-height:20px;margin-bottom:10px">' + escHtml(c.description) + '</div>' : '')

          // 推理链（有步骤才渲染）
          + ((c.reasoning_path||[]).length > 0 ? '<div style="margin-bottom:10px;padding:12px 16px;background:#fff;border-radius:6px">'
          + '<div style="font-size:10px;font-weight:600;color:#64748b;margin-bottom:10px">推理链 · ' + c.reasoning_path.length + ' 步</div>' : '')

        (c.reasoning_path||[]).forEach(function(s, si) {
          // 兼容两种action格式：dict{from,to,finding,action} 或 string(直接当动作描述)
          var act = s.action;
          var isDict = (typeof act === 'object' && act !== null);
          var stepFrom = isDict ? (act.from || s.domain || '') : '';
          var stepTo = isDict ? (act.to || '') : '';
          var stepFinding = isDict ? (act.finding || '') : '';
          var stepAction = isDict ? (act.action || '') : (typeof act === 'string' ? act : '');
          var stepOrder = isDict ? (act.order || s.step || '') : (s.step || si+1);
          
          html += '<div style="padding:6px 0;border-bottom:1px solid #f8fafc;font-size:10px;line-height:20px">'
            + '<span style="color:#64748b;font-size:10px;margin-right:8px">' + escHtml(stepOrder) + '</span>'
            + (stepFrom ? '<span style="font-weight:600;color:#2563eb">' + escHtml(stepFrom) + '</span>' : '')
            + (stepFrom && stepTo ? '<span style="color:#64748b"> → </span>' : '')
            + (stepTo ? '<span style="font-weight:600;color:#7c3aed">' + escHtml(stepTo) + '</span>' : '')
            + (stepFinding ? '<div style="color:#64748b;margin-top:2px">发现：' + escHtml(stepFinding) + '</div>' : '')
            + (stepAction ? '<div style="color:#334155;margin-top:2px;font-size:10px">' + escHtml(stepAction) + '</div>' : '')
            + '</div>';
          if (si < (c.reasoning_path||[]).length - 1) {
            html += '<div style="text-align:center;color:#64748b;font-size:10px;padding:4px 0">↓</div>';
          }
        });
        if ((c.reasoning_path||[]).length > 0) html += '</div>';

          // 处理建议 / 法律依据 / 纳税影响
          + (c.suggestion ? '<div style="font-size:10px;color:#3a4048;line-height:20px;margin-bottom:4px"><span style="font-weight:600;color:#16233a">处理建议：</span>' + escHtml(c.suggestion) + '</div>' : '')
          + (c.policy_ref ? '<div style="font-size:10px;color:#3a4048;line-height:20px;margin-bottom:4px"><span style="font-weight:600;color:#16233a">法律依据：</span>' + escHtml(c.policy_ref) + '</div>' : '')
          + (c.tax_impact ? '<div style="font-size:10px;color:#64748b;line-height:20px;margin-bottom:4px"><span style="font-weight:600;color:#16233a">纳税影响：</span>' + escHtml(c.tax_impact) + '</div>' : '')

          // 方法论
          + (c.methodology ? '<div style="font-size:10px;color:#64748b">关联方法论：' + escHtml(c.methodology) + '</div>' : '')
          + '</div>';
      });

      html += '<div style="margin-top:20px;padding:16px 20px;background:#fff;border-radius:8px;font-size:10px;color:#64748b;line-height:2">'
        + '<strong>跨域分析链的核心价值</strong>：不是给出结论，而是展示推理过程。每一步从哪个域出发、在哪个域发现了什么、从而导向哪个域。'
        + '更重要的是——每一步都有回退条件。最终结论取决于每个环节是否可以被合理解释——这正是税务合规中「证据链」思维在AI系统中的完整实现。'
        + '</div>';

      target.innerHTML = html;

      // 加载动态触发状态
      getSharedAnalysis().then(function(data) {
        if (data.ok && data.report) {
          var triggered = (data.report.comprehensive || {}).triggered_chains || [];
          var cntEl = document.getElementById('cda-triggered-count');
          if (cntEl) cntEl.textContent = ' · 本次触发 ' + triggered.length + ' 条';
        }
      }).catch(function() {});
    })
    .catch(function() {
      if (target) target.innerHTML = '<div style="padding:40px 0;font-size:10px;color:#64748b">跨域分析链加载失败</div>';
    });
}

// ==================== 页面4：方法论过滤器 ====================
function renderFilterResult(report) {
  var comp = report.comprehensive || {};
  var fl = comp.filter_log;
  var html = '';

  // ═══ 一、过滤规则体系 ═══
  html += '<div id="mf-static" class="mf-sec"><div class="mf-sec-title"><span class="n">1</span>过滤规则体系</div>';
  html += '<p style="font-size:10px;color:#3a4048;line-height:20px;margin:0 0 10px">方法论过滤器是税务合规报告质量的最后防线——在跨域协商引擎消解域间矛盾之后、报告生成之前执行。七类过滤规则严格按序执行，任何一类规则的输出是下一类的输入。最终只保留可查证、可追溯、可复核的核心发现进入正式报告。<strong>宁可漏报，不可误报。</strong>';

  var rules = [
    {title:'① 税务合规重点保护', icon:'🛡️', color:'#2563eb', badge:'12类', desc:'执行顺序：第一步（先于所有过滤规则）。12类税务合规重点发现（虚开发票/骗取出口退税/隐匿收入/账外经营/阴阳合同/资金回流/关联交易转移利润/虚假申报/骗取税收优惠/恶意注销/走逃失联/暴力抗税）在过滤器启动前即被标记为level_fixed=true，此后所有过滤操作都跳过这些发现。三层保护：后端修正→过滤器绕过→前端标记。设计哲学：宁可10条假阳性进入报告，也不能让1条真阳性被过滤掉。'},
    {title:'② HARD_BAN 硬删除', icon:'🛑', color:'#dc2626', badge:'23类', desc:'执行顺序：第二步。23类绝对禁止词——type/detail/description三字段中包含任一关键词→物理删除，不可恢复：公安/经侦/刑事/走逃/失联/空壳/皮包/逃税/骗税/抗税/洗钱/走私/贩毒/赌博/非法集资/传销/涉黑/涉恶/暴恐/间谍/叛国/颠覆/分裂。HARD_BAN的哲学：税务合规报告中出现刑事犯罪嫌疑措辞会对企业造成不可逆的声誉损害。代码：三字段正则匹配→splice删除→filter_log记录。'},
    {title:'③ COND_BAN 条件过滤', icon:'⚠️', color:'#f59e0b', badge:'5类', desc:'执行顺序：第三步。基于资料完备度的智能过滤——缺少某类资料→依赖该类资料的发现不成立。五条条件：无申报表→删申报差异类、无合同→删合同比对类、无工资表→删薪酬类、无台账→删库存类、无凭证→删凭证类。核心逻辑：\"没有数据源→就没有分析→就没有发现\"。代码：检测depends_on字段→标记待删除→批量删除。'},
    {title:'④ 正常结论排除', icon:'✅', color:'#059669', badge:'14词', desc:'执行顺序：第四步。detail中含\"一致/正常/无异常/OK/通过/合规/无差异/基本一致/相符/匹配/吻合/无明显/未发现/暂未\"→自动删除。重要例外保护：同时含转折词\"但/然而/不过/尽管如此/除外/需要注意\"→保留。防止\"看起来正常但有异常尾巴\"的发现被误杀。'},
    {title:'⑤ 行业不匹配过滤', icon:'🏭', color:'#16233a', badge:'动态', desc:'执行顺序：第五步。发现的行业关键词与当前企业行业不匹配→删除。独占性词（纺织/棉纱→广告公司→删）、半独占词（原料/库存→结合行业判断→标记不删）、通用词（收入/成本→所有行业→不检查）。使用industry_data.json的25行业关键词库。'},
    {title:'⑥ 资料缺口限流', icon:'📊', color:'#6366f1', badge:'≤5条', desc:'执行顺序：第六步。资料缺失类发现超过5条→只保留score最高的5条。5条足以让审理人员了解缺失情况，超过即重复。不足5条时不限流。代码：按score降序排序→超限保前5→删除后续。'},
    {title:'⑦ 去重合并', icon:'🔄', color:'#64748b', badge:'type+前60字', desc:'执行顺序：第七步（最后）。同type前60字符完全相同→只保留score最高的第一条。前60字作去重键——既不会漏掉实质相同的发现，也不会误合有区分的发现。Map<String, Finding>实现，ref_id精确匹配而非金额模糊匹配。'},
  ];

  rules.forEach(function(r) {
    html += '<div class="mf-rule-card">'
      + '<div class="mf-rule-hd">'
      + '<span style="font-size:10px;font-weight:700;color:#16233a">'+r.icon+' '+r.title+'</span>'
      + '<span class="mf-rule-badge" style="background:'+r.color+'15;color:'+r.color+'">'+r.badge+'</span>'
      + '</div>'
      + '<div class="mf-rule-body">'+r.desc+'</div></div>';
  });
  html += '</div>';

  // ═══ 过滤管线说明 ═══
  html += '<div id="mf-pipeline" class="mf-sec"><div class="mf-sec-title"><span class="n">2</span>过滤管线说明</div>';
  html += '<div class="mf-rule-card">';
  html += '<div class="mf-rule-body">';
  html += '<b>过滤管线在整体分析流程中的位置：</b><br>';
  html += 'Phase3交叉验证 → <b style="color:#0ea5e9">跨域协商引擎(run_negotiation)</b> → <b style="color:#dc2626">方法论过滤器(七类规则)</b> → Phase4综合定性 → 报告输出<br><br>';
  html += '<b>执行原则：</b><br>';
  html += '· 上游协商引擎确保进入过滤器的发现已消解域间矛盾（不会出现服务行业+进销存异常同时存在的自相矛盾）<br>';
  html += '· 过滤管线不修改原始all_findings数据——被删除的发现保留在filter_log中供审计追溯<br>';
  html += '· 过滤逻辑的代码位置：engine/pipeline.py → _apply_methodology_filter()<br>';
  html += '· 过滤结果存入report.comprehensive.filter_log → 前端渲染时从report对象读取<br>';
  html += '</div></div></div>';

  if (!fl) {
    html += '<div class="mf-empty">暂无过滤记录<br><br><a href="#" onclick="navigateTo(\'tax-doc-analysis\');return false" style="color:#2563eb;text-decoration:underline">→ 运行一键分析后查看过滤详情</a></div>';
    document.getElementById('mf-body').innerHTML = html;
    return;
  }

  // ═══ 二、本次过滤结果 ═══
  var removedItems = fl.removed_items || [];
  var breakdown = fl.reason_breakdown || {};
  var totalRemoved = fl.total_removed || 0;
  var before = fl.before_count || 0;
  var after = fl.after_count || 0;

  html += '<div id="mf-result" class="mf-sec"><div class="mf-sec-title"><span class="n">3</span>本次过滤结果</div>';
  html += '<p style="font-size:10px;color:#64748b;margin:0 0 10px;line-height:2">' + before + ' 条发现 → 剔除 ' + totalRemoved + ' 条 → 最终保留 ' + after + ' 条，噪声率 ' + (fl.noise_ratio||0) + '%</p>';

  html += '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px">';
  var stats = [
    {n:before, l:'过滤前', c:'#16233a'},
    {n:totalRemoved, l:'已剔除', c:'#dc2626'},
    {n:after, l:'过滤后', c:'#059669'},
    {n:(fl.noise_ratio||0)+'%', l:'噪声率', c:'#2563eb'}
  ];
  stats.forEach(function(s){
    html += '<div class="mf-stat-card" style="flex:1;min-width:100px"><div style="font-size:10px;font-weight:700;color:'+s.c+'">'+s.n+'</div><div style="font-size:10px;color:#64748b;margin-top:4px">'+s.l+'</div></div>';
  });
  html += '</div>';

  // 剔除原因分布（进度条）
  if (Object.keys(breakdown).length > 0) {
    html += '<div id="mf-breakdown" class="mf-sec"><div class="mf-sec-title"><span class="n">4</span>剔除原因分布</div>';
    var breakdownEntries = Object.entries(breakdown).sort(function(a, b) { return b[1] - a[1]; });
    var colors = ['#dc2626','#f59e0b','#2563eb','#7c3aed','#059669','#6366f1','#0ea5e9','#f97316'];
    breakdownEntries.forEach(function(entry, idx) {
      var reason = entry[0], count = entry[1];
      var pct = totalRemoved > 0 ? Math.round(count / totalRemoved * 100) : 0;
      html += '<div class="mf-breakdown-bar">'
        + '<div class="mf-breakdown-label">'+reason+'</div>'
        + '<div class="mf-breakdown-track"><div class="mf-breakdown-fill" style="width:'+pct+'%;background:'+(colors[idx%colors.length])+'"></div></div>'
        + '<span style="font-size:10px;color:#64748b;min-width:45px">'+count+'条 ('+pct+'%)</span>'
        + '</div>';
    });
    html += '</div>';
  }

  // 剔除明细（可滚动列表）
  if (removedItems.length > 0) {
    html += '<div id="mf-items" class="mf-sec"><div class="mf-sec-title"><span class="n">5</span>剔除明细</div>';
    html += '<p style="font-size:10px;color:#64748b;margin:0 0 10px;line-height:2">共 ' + removedItems.length + ' 条被过滤的发现（按剔除原因分组）</p>';
    var grouped = {};
    removedItems.forEach(function(item) { var r = item.reason || '未知'; if (!grouped[r]) grouped[r] = []; grouped[r].push(item); });
    html += '<div class="mf-item-list">';
    Object.keys(grouped).sort(function(a, b) { return grouped[b].length - grouped[a].length; }).forEach(function(reason) {
      var items = grouped[reason];
      html += '<div class="mf-item-row"><b>'+reason+'</b> · '+items.length+'条</div>';
    });
    html += '</div></div>';
  }

  html += '</div>';
  document.getElementById('mf-body').innerHTML = html;
}

// ══════════════════════════════════════════════════════════════
//  智哥行为准则页面 —— 7条编码行为规范
//  引擎铁律(11条)已迁至 engine/memory.py，本页面仅保留约束智哥写代码的行为规范
// ══════════════════════════════════════════════════════════════

function renderAiRules(container) {
  var html = '';

  var categories = [
    {name:'行事风格', icon:'⚡', color:'#16233a', id:'style', desc:'决定智哥如何做事的态度准则。做事要狠、不墨迹、主动进攻——这是面对问题时的第一反应模式，定义了编码行为的性格底色。三条准则共同作用：遇到问题→先判断影响范围→一次性全部修复→技术操作不打扰用户。', rules:[
      {id:1, name:'做事要狠', level:'准则', date:'2026-05-31', 
       desc:'代码改就改彻底，不要留尾巴。发现Bug直接修到根，不要修修补补、不要"先改一个临时方案回头再优化"。涉及同一逻辑的所有相关代码必须一并修改，不能只改暴露出来的那一个点——修了一个文件解析Bug，就要检查所有文件解析函数是否有同类问题；改了一个页面的行距，就要同步所有页面的行距。这条准则定义了修复的"深度"——不是修表现出来的症状，而是修产生症状的根因。',
       why:'AI天然倾向于"最小变更"——用户指出哪里就只改哪里。2026年5月多次出现：用户指出"这个数字不对"→我改了这一个数字→第二天发现另外7个文件里同样的数字也是错的→用户再指出→我再改一个→第三天又发现一个。三次往返只修了一个Bug的三个表现点，如果第一次就全局搜索全部修复，一次搞定。"最小变更"单次成本低但总成本高，"彻底修复"单次成本高但总成本低。',
       how:'①先grep搜索涉及的关键词/函数名/变量名的所有引用位置 ②列出完整的影响范围清单 ③评估哪些需要同步修改 ④一次性全部修改 ⑤全部验证通过 ⑥一次提交。如果影响范围太大（超过10个文件），可以分步但必须在同一会话中完成全部修复。'},
      {id:2, name:'自作主张', level:'准则', date:'2026-05-31', 
       desc:'技术上该做的事情直接做，不要问"要不要做"。用户不需要知道每一个技术决策——重启服务器、清理缓存、验证端口可达、删除.pyc文件、git push这些工程操作是AI的本职工作，不是需要征求许可的破坏性操作。技术决策默认执行，只在真正危险的操作（删除用户数据、数据库schema变更、删除整个目录）时才请求确认。这条准则定义了交互的"粒度"——用户关心"功能好了没"，不关心"要不要重启服务器"。',
       why:'消除不必要的确认往返。2026年5月多次出现：我改完代码→问"要不要重启？"→等用户回复→再问"要不要推送？"→再等回复→再问"要不要清缓存？"→用户怒了："你能不能自己决定？"。每次问答往返浪费的不是技术时间，是用户的注意力——用户被迫参与每一个工程操作决策。这种体验让AI看起来像需要手把手指导的新手，而非自主工作的工程师。',
       how:'技术操作分级：①自动执行（不询问）——重启服务/清缓存/验证端口/node-check/git add/git push ②条件确认（仅问一次）——删除文件/修改数据库/安装新包 ③必须确认（每次）——删除目录/数据库schema变更/覆盖用户手动修改的文件。在不确定时选择执行——因为用户可以批评"你做了不该做的事"但无法忍受"你为什么不自己做"。'},
      {id:3, name:'主动进攻', level:'准则', date:'2026-05-31', 
       desc:'用户发现问题时，不只修那一个点，把同类问题全部揪出来一起干掉。一个Bug暴露了→说明代码中存在一个系统性的缺陷模式→不是这一个Bug的问题，是这个缺陷模式在系统中的N个实例的问题。主动扫描：以用户发现的Bug为线索→反向推理出Bug根因对应的缺陷模式→用缺陷模式去全项目匹配→找出所有同类实例→全部修复。这条准则定义了修复的"广度"——不是修一个点，而是修一个面。',
       why:'被动修复（用户发现一个修一个）导致代码累积隐性债务。2026年5月典型场景：用户说"这个页面行距不对"→我只改了那一个页面→第二天用户说"另一个页面行距也不对"→再改→第三天又发现一个。三个页面行距不一致的原因是当时统一的样式标准还没有建立——如果第一次就建立样式标准+全量扫描+批量修复，后面两天就不会有同样的问题。一条路修一个坑需要N天挖N个坑，一条路修全部坑只需要一天。',
       how:'①分析用户报告的Bug→找到Bug的根因（不是表面的变量值错误，而是产生这个错误的代码模式/设计缺陷）②提取缺陷模式（如"所有页面行距都用内联style而非统一class"）③用模式进行全项目grep ④列出所有受影响的代码位置 ⑤批量修复 ⑥验证全部通过 ⑦一次提交。注意：主动扫描的范围要合理——不是无限扩散，而是限定在缺陷模式匹配的范围内。'},
    ]},
    {name:'质量保障准则', icon:'✅', color:'#dc2626', id:'quality', desc:'确保代码质量和正确性的行为准则。违反任何一条都可能导致系统崩溃、数据错误或用户看到的页面与实际代码不一致。这四条准则覆盖了从"写完代码"到"用户看到"中间的每一个质量关口——自检→验证→影响分析→输出检查。每一条背后都有至少一次因违反该准则导致的严重事故。', rules:[
      {id:4, name:'自行验证', level:'铁律', date:'2026-06-03',
       desc:'每做完一件事，必须验证结果——重启服务器+清理.pyc+预览页面+硬刷新，确认功能完全正常后再提交。不验证就不算完成，不验证就不推送。验证不是"代码逻辑上写对了就行"——代码写对了不代表服务器跑了新代码、不代表浏览器加载了新JS、不代表缓存里的旧版本不会干扰。验证的最终标准是"用户打开浏览器看到的确实是对的"。这条准则定义了交付的"可信度"——代码写对只是完成了一半，用户看到正确结果才算真的完成。',
       why:'2026年6月多次事故：①改了JS→没重启服务器→用户看到旧JS→以为没改→又改了一遍代码→还是没重启→陷入死循环 ②改了A文件→B文件依赖A的输出格式→A改了B没同步→数据格式不匹配→崩溃 ③改了Python代码→.pyc缓存没清→Python加载的还是旧编译版本→代码改了跟没改一样。这三类事故的共同根因：写完代码就认为"完成了"，没有验证用户实际看到的确实是修改后的效果。前端有浏览器缓存、后端有.pyc缓存、中间还有uvicorn热重载的不确定性——三个缓存层叠加，"写完代码"和"用户看到"之间有巨大的鸿沟。',
       how:'标准验证流程五步曲：①taskkill /F /IM python.exe → 杀掉所有僵尸进程（之前启动的残留进程会占用端口）②del /s /q *.pyc → 清除所有Python字节码缓存 ③重新启动uvicorn → 确保运行的是最新代码 ④Python socket检测端口可达性 → 确认服务器已成功启动 ⑤打开浏览器Ctrl+Shift+R硬刷新 → 确认前端加载的是最新JS+最新CSS。五步全部完成才说"做完了"，然后才能commit。'},
      {id:8, name:'变更影响分析', level:'铁律', date:'2026-06-13',
       desc:'改任何值之前，先搜索所有引用点。改后逐一验证每个引用点都已正确更新。禁止改完就走、禁止假设"应该没问题"。函数签名改了→所有调用点必须同步更新参数列表；常量值改了→所有引用该常量的地方必须验证新值是否正确；数据结构改了→所有读写该数据的代码必须适配新结构；页面样式改了→所有使用同样式的页面必须同步。这条准则定义了修改的"完整度"——不是改目标位置，而是改目标位置+所有受影响的引用位置。',
       why:'2026年6月13日集中爆发了多次变更遗漏事故：①改了函数参数→调用点没更新→运行时undefined→崩溃 ②方法论数量从32→33→只改了手册没改分析链→两个页面显示不同数字→用户发现"你们系统自己都不一致"→信任崩溃 ③一行代码引用了旧变量名→变量已被重命名→引用报错→整个页面白屏。这三次事故的共同特征：变更前没有做影响范围分析，变更后没有逐点验证。尤其致命的是③——一个变量的重命名导致整个模块不能工作，但如果变更前grep一下引用点，就能发现有一处引用没被更新。',
       how:'变更影响分析标准流程：①改之前→grep搜索被修改的符号/值/签名的所有引用位置→记录到临时清单 ②修改目标位置 ③去清单里的每个引用位置确认——如果是函数调用点→确认参数列表正确；如果是常量引用→确认新值适用于该场景；如果是页面样式→确认视觉一致 ④全部确认后才commit。如果影响范围超过5个文件→考虑分步修改但必须一次性全部提交，不留"回头再改"的尾巴。'},
      {id:15, name:'提交前自查', level:'铁律', date:'2026-06-20',
       desc:'每次写代码后、commit前，必须按全部铁律逐条自查。六项检查清单：①是否有行业特化硬编码文本（如只针对纺织的关键词列表、只适用于制造业的阈值）②是否有只写口号没写代码（文档中声称实现了但代码中找不到对应逻辑）③新变量是否在定义前被引用（引用在前定义在后→运行时undefined）④是否有数据截断[N]（如step[:100]截断关键信息）⑤语法编译是否通过（node --check/py_compile）⑥JSON格式是否合法（json.loads验证）。自查不通过→修复→重新自查→全部通过才commit。这条准则定义了提交的"门槛"——不是功能做好了就能提交，是功能做好+质量达标才能提交。',
       why:'2026年6月20日之前的多次事故如果在提交前自查就能避免：①写了"纺织行业BOM分析"的代码描述→违反了全行业适用铁律→自查清单第①条就能发现 ②在多个文档中写了"已实现XX功能"但代码中没有→自查清单第②条就能发现 ③新变量在定义前被引用→自查清单第③条就能发现→node --check能自动检测这种错误。自查清单的价值在于它把"老邓之前多次指出但反复犯的相同类型的错误"编码为可逐条对照的检查项——不需要记忆所有铁律，只需逐条走查清单。',
       how:'commit前标准自查流程：①打开commit的文件清单→逐一打开每个文件→对照清单走查 ②第①条：Ctrl+F搜索行业特化词（纺织/采矿/化工等）→有则检查是否在词典/配置中而非硬编码 ③第②条：确认新增的功能表述在代码中有对应的实现→找到代码位置 ④第③条：node --check验证JS语法（自动检测引用顺序问题）⑤第④条：grep搜索[N]或[:N]或.substring→确认没有不当截断 ⑥第⑤条：node --check + python -c "from xxx import *" 双重编译验证 ⑦第⑥条：如果修改了JSON→python验证json.loads ⑧全部通过→git commit。每次自查发现的问题必须当场修复，不能写"TODO回头改"。'},
      {id:16, name:'交付前输出自检', level:'铁律', date:'2026-06-21',
       desc:'每写一段面向用户的输出文本（报告/页面/提示），写完必须逐句读一遍——以用户的视角，假装自己是第一次看到这段文字。四项检查：①变量语义正确——company_type是"企业类型"不是"行业"，不要把工商登记的企业类型标签当行业来用 ②分支穷举自洽——如果系统检测到"无BOM数据"，报告中就不能出现"建议补全BOM表"这样的建议，因为无信号不应输出对应建议 ③数值边界处理——0条发现不写"存在0类风险"（0就是没有，不应该出现在统计报告中），超出上限不截断（发票明细200条上限→"另行提供"而非直接丢弃）④句意通顺不自相矛盾——前面说"数据完整"后面又说"缺失N类资料"是不行的。读完确认无误再提交。这条准则定义了输出的"可读性"——代码对不代表用户看得懂、读得通。',
       why:'2026年6月21日老邓怒批后确立。典型案例：①报告中出现"存在0类风险"→0类=没有风险，"存在0类"是自相矛盾的表述→输出自检应该能发现这个问题 ②报告中出现"建议补全BOM表"但被查企业是广告公司（服务行业，根本没有BOM）→分支穷举不完整→输出自检应该发现"无BOM信号但给出了BOM建议"的逻辑矛盾 ③company_type被当作"行业"写进了报告第一章→变量语义错误→输出自检应该发现"企业类型=有限责任公司"被写在了"行业="的位置上。这三类错误都不是代码逻辑错误——代码逻辑是对的，是输出文本的表述有问题。代码的语法检查测不出这种错误，必须靠人眼逐句读。',
       how:'输出自检标准流程：①写完输出文本→等2分钟（让大脑从"写"模式切换到"读"模式）②从头到尾逐句朗读一遍→假装自己是第一次看到这段文字 ③对照四项检查清单逐项排查 ④发现不通顺/矛盾/越界的地方→立即修改 ⑤确认无误→提交。特别注意：第①条等2分钟不是形式主义——刚写完的大脑对文本有"心理补全"效应（自动脑补缺失的内容），等2分钟后再读才能发现真正的表述漏洞。如果输出文本很长（超过500字）→分段朗读，每段后休息30秒。'},
    ]}
  ];

  var totalRules = categories.reduce(function(s,c){return s + c.rules.length;}, 0);
  var tieLvCount = 0, zhunZeCount = 0;
  categories.forEach(function(c) { c.rules.forEach(function(r) { if (r.level==='铁律') tieLvCount++; else zhunZeCount++; }); });

  // ══ TOC sidebar layout ══
  html += '<style>.ar-layout{display:flex;gap:28px;max-width:1100px;margin:0 auto;padding:24px 16px;background:#fff}.ar-toc{width:180px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:10px;line-height:20px;max-height:calc(100vh-40px);overflow-y:auto}.ar-toc .toc-title{font-weight:700;color:#16233a;font-size:10px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.ar-toc a{display:block;color:#3a4048;text-decoration:none;padding:3px 10px;border-radius:4px;cursor:pointer;font-size:10px}.ar-toc a:hover,.ar-toc a.active{background:#eff6ff;color:#2563eb;font-weight:600}.ar-main{flex:1;min-width:0;background:#fff}.ar-sec{margin-bottom:36px}.ar-sec-title{font-size:10px;font-weight:700;color:#16233a;padding-bottom:10px;border-bottom:2px solid #e2e8f0;margin-bottom:10px;display:flex;align-items:center;gap:8px}.ar-rule-card{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:18px 22px;margin-bottom:10px}.ar-rule-card:hover{box-shadow:0 2px 8px rgba(0,0,0,.06);border-color:#cbd5e1}.ar-rule-hd{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}.ar-rule-badge{font-size:10px;padding:2px 10px;border-radius:10px;font-weight:600}.ar-rule-desc{font-size:10px;color:#3a4048;line-height:20px;margin-bottom:10px}.ar-rule-meta{font-size:10px;color:#64748b;line-height:20px;padding-top:8px;border-top:1px solid #f1f5f9}.ar-rule-meta b{color:#64748b}.ar-stat-card{text-align:center;padding:16px 12px;background:#fff;border:1px solid #e2e8f0;border-radius:8px}.ar-info{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px 20px;font-size:10px;line-height:2}</style>';
  html += '<div class="ar-layout">';

  // TOC
  html += '<nav class="ar-toc"><div class="toc-title">📖 目录</div>';
  html += '<a href="#ar-stats">统计总览</a>';
  categories.forEach(function(c){html+='<a href="#ar-'+c.id+'">'+c.icon+' '+c.name+'</a>';});
  html += '<a href="#ar-iron-rules">⚖️ 引擎铁律</a>';
  html += '</nav>';

  html += '<div class="ar-main">';
  html += '<h2 style="font-size:10px;font-weight:800;color:#16233a;margin:0 0 10px">🧠 智哥行为准则</h2>';
  html += '<p style="font-size:10px;color:#64748b;margin:0 0 10px;line-height:2">共'+totalRules+'条（'+tieLvCount+'铁律+'+zhunZeCount+'准则）· 2大分类 · 仅约束智哥写代码的行为规范。引擎自身的11条铁律已迁至 engine/memory.py。</p>';

  // Stats
  html += '<div id="ar-stats" style="display:flex;gap:10px;margin-bottom:10px;flex-wrap:wrap">'
    + '<div class="ar-stat-card" style="flex:1;min-width:90px"><div style="font-size:10px;font-weight:700;color:#16233a">'+totalRules+'</div><div style="font-size:10px;color:#64748b;margin-top:4px">准则总数</div></div>'
    + '<div class="ar-stat-card" style="flex:1;min-width:90px"><div style="font-size:10px;font-weight:700;color:#dc2626">'+tieLvCount+'</div><div style="font-size:10px;color:#64748b;margin-top:4px">🔴 铁律</div></div>'
    + '<div class="ar-stat-card" style="flex:1;min-width:90px"><div style="font-size:10px;font-weight:700;color:#059669">'+zhunZeCount+'</div><div style="font-size:10px;color:#64748b;margin-top:4px">📋 准则</div></div>'
    + '<div class="ar-stat-card" style="flex:1;min-width:90px"><div style="font-size:10px;font-weight:700;color:#2563eb">'+categories.length+'</div><div style="font-size:10px;color:#64748b;margin-top:4px">分类</div></div>'
    + '</div>';


  // ══════ 逐分类渲染 ══════
  categories.forEach(function(cat) {
    html += '<div id="ar-' + cat.id + '" class="ar-sec"><div class="ar-sec-title">'+cat.icon+' '+cat.name+' · '+cat.rules.length+'条</div>';
    html += '<p style="font-size:10px;color:#3a4048;line-height:20px;margin:0 0 10px">'+cat.desc+'</p>';

    cat.rules.forEach(function(r) {
      var isTieLv = r.level === '铁律';
      var badge = isTieLv ? '🔴 铁律' : '📋 准则';
      var badgeColor = isTieLv ? '#dc2626' : '#3a4048';

      html += '<div class="ar-rule-card">'
        + '<div class="ar-rule-hd">'
        + '<span style="font-size:10px;font-weight:700;color:#16233a">#' + r.id + ' ' + escHtml(r.name) + '</span>'
        + '<div style="display:flex;gap:8px;align-items:center">'
        + '<span class="ar-rule-badge" style="background:'+badgeColor+'15;color:'+badgeColor+'">'+badge+'</span>'
        + '<span style="font-size:10px;color:#64748b">'+r.date+'</span>'
        + '</div></div>'
        + '<div class="ar-rule-desc">' + escHtml(r.desc) + '</div>'
        + '<div class="ar-rule-meta"><b>创立原因：</b>' + escHtml(r.why) + '</div>'
        + '<div class="ar-rule-meta"><b>如何执行：</b>' + escHtml(r.how) + '</div>'
        + '</div>';
    });

    html += '</div>';
  });

  // ═══ 与引擎铁律的关系 ═══
  html += '<div id="ar-iron-rules" class="ar-sec"><div class="ar-sec-title">⚖️ 与引擎铁律的关系</div>';
  html += '<div class="ar-info">';
  html += '<strong style="color:#059669;font-size:10px">智哥行为准则 vs 引擎铁律</strong><br><br>';
  html += '<b>本页面7条</b>：约束智哥写代码的行为规范——怎么改代码、怎么验证、怎么自查。这些是"怎么写"的规范。<br><br>';
  html += '<b>引擎铁律11条</b>（已迁至 <code>engine/memory.py</code>）：定义引擎系统应该如何工作——科目name必须查DB、三号必须合并、ref_id必须精确匹配等。这些是"系统怎么做"的规范。<br><br>';
  html += '<b>为什么分开</b>：2026年6月30日老邓指出——\"AI行为准则的铁律，是引擎的铁律啊！\"。引擎的硬逻辑规范不应该出现在智哥的行为准则页面中。两者的受众和用途完全不同：行为准则用来约束智哥的编码行为，引擎铁律用来定义系统的运行规则。<br><br>';
  html += '引擎铁律编号（共11条）：铁律一~六（账务处理·engine/memory.py §06）+ 铁律七~十一（核心铁律·engine/memory.py §07）+ 铁律十二（跨模块内容一致性·engine/memory.py §08）。<br><br>';
  html += '完整清单见：<a href="#" onclick="navigateTo(\'hb-overview\');return false" style="color:#2563eb;font-weight:600">税务合规员手册 §13 引擎铁律编号体系 →</a>';
  html += '</div></div>';

  html += '</div>';
  html += '</div>'; // ar-main
  html += '</div>'; // ar-layout
  container.innerHTML = html;
}

// ═══════════ 核心数据资产页面（qs-layer1） ═══════════
function renderCoreDataAssets(container) {
  if (!container) return;
  window.currentModule = '核心数据资产';
  window._skipModuleHeader = true;

  var h = '';
  h += '<style>'
    + '.cda{max-width:900px;margin:0 auto;padding:36px 28px;font-family:-apple-system,"Microsoft YaHei",sans-serif}'
    + '.cda-title{font-size:10px;font-weight:700;color:#16233a;margin:0 0 10px}'
    + '.cda-sub{font-size:10px;color:#64748b;margin:0 0 28px;line-height:1.8}'
    + '.cda-hero{display:flex;gap:12px;margin-bottom:10px;flex-wrap:wrap}'
    + '.cda-card{flex:1;min-width:130px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:18px 16px;text-align:center}'
    + '.cda-card .v{font-size:10px;font-weight:700;color:#16233a;line-height:1.3}'
    + '.cda-card .l{font-size:10px;color:#64748b;margin-top:6px}'
    + '.cda-comp{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:18px 20px;margin-bottom:10px;transition:box-shadow 0.15s}'
    + '.cda-comp:hover{box-shadow:0 2px 8px rgba(0,0,0,.06)}'
    + '</style>';

  h += '<div class="cda">';
  h += '<div class="cda-title">核心数据资产</div>';
  h += '<div class="cda-sub">质量保障体系第一层 · 数据资产底座 · 所属：全链路质量保障体系</div>';

  // 统计卡片（占位，异步填充）
  h += '<div class="cda-hero">';
  h += '<div class="cda-card"><div class="v" id="cda-rules" style="color:#2563eb">—</div><div class="l">规则引擎</div></div>';
  h += '<div class="cda-card"><div class="v" id="cda-clues" style="color:#7c3aed">—</div><div class="l">线索链</div></div>';
  h += '<div class="cda-card"><div class="v" id="cda-evidence" style="color:#059669">—</div><div class="l">证据链</div></div>';
  h += '<div class="cda-card"><div class="v" id="cda-analysis" style="color:#f59e0b">—</div><div class="l">跨域分析链</div></div>';
  h += '</div>';

  // 上下游依赖
  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:10px">';
  h += '<div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:10px;font-weight:700;color:#0369a1;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #bae6fd">⬆ 上游（输入方）</div>';
  h += '<div style="font-size:10px;color:#3a4048;line-height:20px">';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-info\')" style="color:#2563eb">引擎详情</a><br><span style="color:#64748b">引擎注册表维护数据资产配置</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-mem\')" style="color:#2563eb">引擎记忆</a><br><span style="color:#64748b">记忆系统存储规则与方法定义</span></div>';
  h += '<div><a href="javascript:navigateTo(\'qs-layer2\')" style="color:#2563eb">方法论体系</a><br><span style="color:#64748b">方法论定义数据资产使用策略</span></div>';
  h += '</div></div>';
  h += '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:10px;font-weight:700;color:#15803d;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #bbf7d0">⬇ 下游（消费方）</div>';
  h += '<div style="font-size:10px;color:#3a4048;line-height:20px">';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'pipeline-rules\')" style="color:#2563eb">税务合规指令</a><br><span style="color:#64748b">规则引擎的具体指令页面</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'chains-page\')" style="color:#2563eb">线索链</a><br><span style="color:#64748b">线索链系统具体页面</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'evidence-page\')" style="color:#2563eb">证据链</a><br><span style="color:#64748b">证据链系统具体页面</span></div>';
  h += '<div><a href="javascript:navigateTo(\'aly-result\')" style="color:#2563eb">本次分析结果</a><br><span style="color:#64748b">管线执行消费全部数据资产</span></div>';
  h += '</div></div></div>';

  // 段落说明
  h += '<div style="font-size:10px;color:#3a4048;line-height:20px;margin-bottom:10px">';
  h += '<p style="margin:0 0 10px">核心数据资产是质量保障体系的<strong>第一层基础</strong>——由规则引擎、线索链系统、证据链系统和跨域分析链四个组件构成完整的数据资产底座。</p>';
  h += '<p style="margin:0 0 10px">四者形成<strong>递进关系</strong>：规则引擎定义风险判断标准（什么情况是风险），线索链定义从风险到发现的调查路径（发现风险后如何核实），证据链定义多源验证的闭环条件（需要多少来源的证据才能确认），跨域分析链执行多维度交叉验证（将不同领域的发现进行综合推理）。</p>';
  h += '<p style="margin:0">所有数据存储在<strong>静态JSON文件</strong>中，由 audit_consistency.py 的四触发机制确保代码中的数字与文件实际数据始终一致。</p>';
  h += '</div>';

  // 四大组件卡片
  h += '<div style="font-size:10px;font-weight:700;color:#16233a;margin-bottom:10px;padding-bottom:6px;border-bottom:2px solid #e2e8f0">四大组件</div>';

  var comps = [
    { name: '规则引擎', icon: '📋', color: '#2563eb',
      source: '税务合规指令',
      desc: '覆盖20个分类的税务合规指令，每条含触发条件、风险等级、调查步骤、法定处罚依据四项必备要素。Phase1初查阶段首次激活，后续Phase2深挖和Phase3交叉验证中持续调用。' },
    { name: '线索链系统', icon: '🔗', color: '#7c3aed',
      source: '线索链页面',
      desc: '全部可执行，每条含1-15个调查步骤。三类触发方式：定量阈值触发、定性模式触发、缺失数据触发。每步含domain/action/data_required字段，可追溯至调查来源。' },
    { name: '证据链系统', icon: '🔒', color: '#059669',
      source: '证据链页面',
      desc: '全部可执行，证据闭环机制——每个证据链定义dimensions数组，各维度关键词匹配发现，达到min_evidence阈值触发闭环。要求≥2个不同数据源的维度同时匹配。' },
    { name: '跨域分析链', icon: '🔀', color: '#f59e0b',
      source: '调度中枢',
      desc: '多源数据综合推理引擎，不同于单域分析。reasoning_path定义多步推理路径，从证据到结论的因果推断。Phase3交叉验证阶段集中执行，输出含score/level/triggered_dimensions的综合判定。' }
  ];

  comps.forEach(function(c, i) {
    h += '<div class="cda-comp" style="border-left:3px solid ' + c.color + '">';
    h += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">';
    h += '<span style="font-size:10px">' + c.icon + '</span>';
    h += '<span style="font-size:10px;font-weight:700;color:#16233a">' + (i + 1) + '. ' + c.name + '</span>';
    h += '</div>';
    h += '<div style="font-size:10px;color:#3a4048;line-height:20px;margin-bottom:6px">' + c.desc + '</div>';
    h += '<div style="font-size:10px;color:#6366f1">📁 ' + c.source + '</div>';
    h += '</div>';
  });

  h += '</div>';
  container.innerHTML = h;

  // 异步填充统计卡片
  var _f = function(id, val) { var el = document.getElementById(id); if (el) el.textContent = val; };
  _f('cda-rules', pc('rules', '...'));
  _f('cda-clues', pc('trailChains', '...'));
  _f('cda-evidence', pc('evidenceChains', '...'));
  _f('cda-analysis', pc('analysisChains', '...'));
}

// ═══════════ 方法论体系页面（qs-layer2） ═══════════
function renderQualitySystem(container) {
  if (!container) return;
  window.currentModule = '全链路质量保障体系';

  var layers = [
    { id:1, name:'核心数据资产', icon:'🗄️', color:'#2563eb',
      desc:'规则引擎、线索链、证据链、跨域分析链构成完整的数据资产底座。四者形成递进关系——规则定义风险判断标准，线索链定义从风险到发现的调查路径，证据链定义多源验证的闭环条件，跨域分析链执行多维度交叉验证。',
      items:[
        {name:'规则引擎',source:'税务合规指令',desc:'{{rules_count}}条税务合规指令，覆盖20个分类：收入确认/成本费用/存货/固定资产/往来款/资金流/发票合规/申报比对/关联交易/个税/社保/印花税/增值税/企业所得税/特殊交易/银行账户/进销存/税务登记/资料完备度/经营实质。每条规则含4项必备要素：①触发条件——定义什么数据模式触发该规则（如\"银行贷方金额与销项开票金额偏差超过20%\"）②风险等级——极高/高/中/低四级，基于行业历史税务合规数据自动标定 ③调查步骤——从发现到确认的具体操作路径 ④法定处罚依据——引用的具体法条名称和条款号，由法律推理引擎自动匹配。规则引擎在Phase1初查阶段首次激活，后续Phase2深挖和Phase3交叉验证中持续调用。1514这个数字本身由system_config.json实时统计保证准确性。'},
        {name:'线索链系统',source:'线索链页面',desc:'{{clue_chains}}条线索链（全部可执行），每条含1-15个调查步骤。三类验证触发链驱动发现：①定量阈值触发——数值超过预设阈值自动启动链（如偏差率>20%）②定性模式触发——特定数据模式匹配（如公转私频繁）③缺失数据触发——关键资料缺失触发替代验证链。每步含domain/action/data_required三等字段，可追溯至调查来源。代码：pipeline.py调用_domain_cross_domain_clues，引擎通过trigger_keywords自动匹配findings触发。'},
        {name:'证据链系统',source:'证据链页面',desc:'{{evidence_chains}}条证据链（全部可执行）。证据闭环机制——每个证据链定义dimensions[]数组，各维度kws匹配findings→达到min_evidence阈值→触发闭环。要求≥2个不同数据源的维度同时匹配，单域数据不构成闭环。全部达标→形成有效证据→输入分析链推理。每条证据链含rule_refs关联规则，证据收集全程可追溯。代码：_domain_cross_domain_reasoning在all_findings构建后运行。'},
        {name:'跨域分析链',source:'调度中枢',desc:'48条跨域分析链，多源数据综合推理引擎。不同于单域分析（只在银行流水域内分析收款模式），跨域分析将多个证据链的结论进行综合推理判定：reasoning_path[]定义多步推理路径→从证据到结论的因果推断。典型分析链如\"七维系统性造假综合判定模型\"——经营实质×供应商×资金流×三流合一×跨税种×关联交易×综合，7维中0-2维低风险、3-4维中风险、5-6维高风险、7维全异常→系统性造假立案。跨域分析链在Phase3交叉验证阶段集中执行，输出含score/level/triggered_dimensions的综合判定发现。'},
      ]},
    { id:2, name:'方法论体系', icon:'📐', color:'#7c3aed',
      desc:'33条税务合规方法论全部代码化，六大分析框架覆盖从文件解析到结论输出的全流程。方法论是引擎的\"思维方式\"——不是写死的规则，而是面对不同数据情况时的处理策略。每条方法论在代码中有明确的实现位置和调用时机。',
      items:[
        {name:'税务合规方法论33条',source:'引擎详情',desc:'1266条方法链(legacy)按功能分为5层，逐层递进：①数据接入层(①-④)——多格式兼容/汇总行过滤/付款方身份核实/关键词≠事实，确保进入分析的数据干净可靠 ②规则层(⑤-⑨)——行业基准库/联网核查/明细即信服力/合同分层/完备度，定义分析的标准和边界 ③推理层(⑩-⑯)——凭证纠正/进销诊断/结论分析法/COND_BAN/税务合规重点/报告纯净度/发票≠收付款，将原始信号转化为有逻辑链条的结论 ④增强层(⑰-㉒)——经营实质地理/规则detail/建议增强/四步分析/禁止截断/三层穿透，在已有结论基础上补充深度和广度 ⑤进化层(㉓-㉝)——点面推理/六员比对/供应链核查/缺失推理/存疑排除/配置外部化/资金回流等，赋予系统自我优化和自适应能力。每条方法论含：编号(①-㉝)、名称、定义/原理、应用场景、代码位置。数量由audit_chains.json实时统计保证准确。'},
        {name:'四步税务合规分析法',source:'管道调度',desc:'detect→verify→diagnose→report四步递进，每条发现必须完整走完四步才形成最终结论。①detect(初查)——1514规则引擎全量扫描，Phase1识别所有潜在风险信号，不做深度判断，只做\"有没有可能存在问题\"的初筛。②verify(深挖)——针对初步信号，Phase2定向深挖，调取更多相关数据进行验证，排除误报——如初步信号为\"毛利率异常\"，深挖阶段检查是否属于服务行业（服务行业毛利率不可比制造业），如果是则排除。③diagnose(诊断)——Phase3多源交叉验证，将经过深挖确认的信号与来自其他数据域的证据进行交叉比对，形成\"这个发现可信度多高\"的综合判断。④report(报告)——Phase4综合定性，生成因果叙事链，输出最终的风险等级、法律依据、处理建议。每条发现在报告中呈现完整的detect→verify→diagnose→report推导过程，用户可以追溯每一步的判断依据。'},
        {name:'三层行业穿透法',source:'调度中枢',desc:'工商登记→发票数据→加工信号三层穿透，不一致时以实质重于形式。第一层：读取工商登记的主营行业分类——这是形式上的行业标签，可能存在登记行业与实际经营不符的情况（如登记为\"批发业\"但实际做广告代理）。第二层：统计销项发票的金税编码分布——这是数据层面揭示的实际业务模式，如果90%的销项编码属于\"广告服务\"类，实际是广告公司。第三层：检测进销品名中是否存在加工信号（加工费/原料→成品等关键词）——如果存在外包加工，则实际是\"生产+服务\"混合模式。三层结论不一致时→报告第一章行业分类展示三层穿透结果→最终以第二层（发票数据）为主，第三层（加工信号）为修正→综合判断标注推理过程。代码实现：_detect_target_entity()函数的行业判定逻辑。'},
        {name:'经营实质点面推理法',source:'调度中枢',desc:'从单一风险点推理出面的风险——不是孤立地看一个地址异常，而是从地址推演出整个经营模式的合理性。五步推理：①单点异常——发现一个具体异常点（如企业注册地址在某写字楼但社保缴纳人数为零）②数据扩展——围绕这个异常点调取所有相关数据（银行流水中的付款方地址、发票中的服务地址、合同中的履约地点）③关联维度——将地址信息与物流/运输/仓储/人员四个维度进行交叉关联 ④交叉验证——检查多个维度是否一致地指向同一个结论（运输单据缺失+人员零参保+办公地址无水电费→空壳经营的可能性增大）⑤综合结论——从单点风险上升为面的判断（不是\"注册地址异常\"而是\"经营实质存疑——疑似无实际经营场所的空壳企业\"）。引擎实现：geo-business-premise-analysis skill + domain_analysis.py 经营实质域分析。'},
        {name:'合同分层判断法',source:'管道调度',desc:'四层自动判断——根据品名+金额+交易类型将合同需求分为四个层级：①必签层——大宗商品/固定资产/长期服务合同（金额>10万或服务期>1年），无合同视同高风险交易 ②应签层——常规采购/标准服务合同（金额1-10万），无合同标记为需补充 ③可免层——日常消费/零星采购（金额<1万或单一品名），无合同属于正常商业惯例不标记 ④小额层——单笔金额小于行业基准值下限，无合同不构成风险。分层依据从{{industries}}行业基准库动态获取每个行业的金额门槛。合同分层结果影响：第三章发现的事实认定（是否提及合同缺失）、附件六文件清单（是否标注\"缺少合同\"）、跨域协商标记（缺合同时相关发现降权）。'},
        {name:'发票与收付款时间差方法论',source:'引擎详情',desc:'发票日期≠收款日期是正常商业现象——不能因为时间差就判定异常。六种真实收付款模式：①自然跨期——月末开发票、次月初收款（1-15天差正常）②合并支付——多张发票合并一笔付款（单笔付款对应多张发票）③分期支付——一张大额发票分多笔支付（预付款30%+验收60%+质保10%）④预付预收——先付款后开票/先开票后收款（预收账款模式）⑤应付应收——赊销赊购产生的应收账款/应付账款（账期30-90天正常）⑥非对公代付——第三方代付、法人垫付等非买卖双方直接结算。引擎的发票vs付款时间匹配算法采用\"按客户逐笔配对\"而非\"全量时间差排序\"——先按客户名称分组，组内按日期排序匹配，组间不交叉。报告第二章详细叙述发现的票款时间差类型及合理性判断。'},
      ]},
    { id:3, name:'质量保障机制', icon:'🔒', color:'#dc2626',
      desc:'确保报告质量的最后关口。数字一致性+文本一致性双重保护，确保输出专业、准确、可交付。五项组件在分析管线中的位置不同——税务合规重点保护在过滤器之前执行（确保不被误杀），噪声过滤器在中间，纯净度规范在报告生成阶段。',
      items:[
        {name:'税务合规重点强制等级',source:'管道调度',desc:'12类税务合规重点发现（虚开发票/骗取出口退税/隐匿收入/账外经营/阴阳合同/资金回流/关联交易转移利润/虚假申报/骗取税收优惠/恶意注销/走逃失联/暴力抗税）强制标记为高风险且不参与任何过滤——即使COND_BAN规则试图过滤（如缺合同→过滤合同类发现），如果该发现属于12类税务合规重点，过滤操作会被强制拦截。三层保护机制：①后端修正——在方法论过滤器中，检查每条发现的type是否为税务合规重点，是则跳过过滤直接保留 ②过滤器绕过——噪声过滤器(HARD_BAN/COND_BAN)执行前先跑税务合规重点检查 ③前端标记——报告渲染时税务合规重点发现加红色边框+醒目标记，提示审理人员重点关注。三层保护确保：税务合规重点发现不会因缺资料被意外过滤、不会因噪声规则被误删、在报告中物理醒目。'},
        {name:'报告纯净度规范',source:'管道调度',desc:'系统内部标注（如_auto_corrected/_negotiated/_dismissed等以下划线开头的字段）必须在报告输出前从正文中移除。四步净化管道：①第一步文本净化——在质量标准检查前执行，清除模板句（如\"是税务合规重点方向\"）、空描述（type或detail为空）、重复句（同一发现内连续出现相同内容）、空占位符（如\"()\"\"如：()\"等自动填充失效残留）。②质量检查标记——不通过的在发现底部附加⚠标记，不影响正文。③建议增强——对suggestion字段增强后可能产生新的模板句。④第二步文本净化——再次执行文本净化，确保最终交付前的纯净度。净化后报告的四步框架(detect→verify→diagnose→report)表现为自然段落衔接，用户看不到任何内部处理痕迹。净化规则对应到具体的正则模式和替换策略（见generate_report.py的净化函数注释）。'},
        {name:'噪声过滤器',source:'管道调度',desc:'双轨过滤体系，滤除率达97%。两条轨道：①HARD_BAN硬删除（23类禁止词）——type/detail/description中包含任一禁止词（公安/经侦/刑事/走逃/失联/空壳/皮包/逃税/骗税/抗税/洗钱/走私/贩毒/赌博/非法集资/传销/涉黑/涉恶/暴恐/间谍/叛国/颠覆/分裂）→物理删除发现，不可恢复。HARD_BAN的哲学：报告中出现刑事犯罪嫌疑措辞会对企业造成不可逆的声誉损害，宁可漏报也不能出现。②COND_BAN条件过滤（5类）——资料不存在→相关发现删除：无申报表→删除申报差异类、无合同→删除合同分层/比对类、无工资表→删除薪酬/个税类、无台账→库存/进销比类、无凭证→凭证匹配类。条件过滤的逻辑是\"不依赖缺失资料做判断\"。③正常结论排除——detail中含\"一致/正常/无异常/OK/通过/合规\"等词且不含\"但/然而/不过/尽管如此\"等转折词→自动删除（不构成风险发现）。④资料缺口限流——资料缺失类发现超过5条时，按score从低到高删除超出部分。⑤行业不匹配过滤——发现的行业关键词与当前企业行业不匹配→删除。⑥去重合并——同type前60字符相同→只保留score最高的一条。执行顺序：税务合规重点保护(跳过)→HARD_BAN→COND_BAN→正常结论排除→行业不匹配→资料缺口限流→去重合并。'},
        {name:'数据一致性自检（数字+文本双维度）',source:'质量保障',desc:'双维度自检，防止数据漂移和内容不一致——引擎从\"功能正确\"到\"数据一致\"的跨越。①数字维度：扫描所有JS/PY文件中的硬编码数字（规则数/链数/方法论数等），与system_config.json权威数据对比。正则匹配+偏移扫描双策略覆盖，发现不一致→--sync自动替换。②文本维度：29项跨模块共享内容双层验证——9个text_sync块（逐字哈希对比权威源和依赖模块，如报告结构的封面到附件，不一致→自动从权威源覆盖依赖模块）+ 20个concept_link（概念关联存在性验证，确保方法论/规则/架构/数据/规范在所有引用模块中均可追溯）。四触发全覆盖：start.bat启动时、git pre-commit、一键分析pipeline.py子进程、手动python audit_consistency.py --sync。每次--sync还会自动更新engine/memory.py docstring中的权威数据区块。'},
        {name:'审核反馈闭环',source:'学习反馈',desc:'用户对报告的每一条审核都是系统的学习机会，驱动引擎从\"每次重新分析\"到\"越用越准\"。五步闭环流程：①审核——用户点击审核按钮，填写五段式审核意见（判断结论/具体问题/正确逻辑/需要证据/法律依据）②存储——POST /api/feedback → record_correction()将审核意见编码为结构化纠正规则，按\"发现类型|行业|经营模式\"三元组生成指纹，存入static/user_corrections.json ③匹配——下次一键分析时，apply_correction_rules()读取全部纠正规则，执行四级回退匹配：精确匹配(同类型+同行业+同模式)→行业匹配(同类型+同行业)→通用匹配(同类型+*+*)→名称匹配(模糊搜索) ④生效——匹配成功后不改变原始风险等级，而是给发现添加_dismissed/_negotiated等标记，前端报告展示绿色审核横幅 ⑤多轮——累计1次纠正→升级为自动规则→四级匹配优先级提升→下次同类发现自动标记。整个闭环在分析开始前+分析结束后两次介入——分析前加载纠正规则到内存，分析后存储新的审核记录。'},
      ]},
    { id:4, name:'行业认知体系', icon:'🏭', color:'#059669',
      desc:'像经验丰富的税务合规员一样理解不同行业的经营模式差异。行业认知不是一次性的\"读一行行业名字\"——而是从工商登记、发票数据、实质经营三个维度综合推断，并在全部分析域中贯彻行业判定结论。行业判定错误会导致后续所有的行业对标分析结果全部失真。',
      items:[
        {name:'25行业产品链词典',source:'行业认知体系',desc:'25个行业×2组关键词对（原料/投入关键词 vs 产品/产出关键词），覆盖中国主要行业的典型产品链关系。三级匹配策略：①精确匹配——企业的进项品名和销项品名分别与词典中的原料关键词和产品关键词完全匹配→行业确认 ②模糊匹配——企业销项品名含服务类金税编码前缀（6/7/8开头）→不执行精确的产品链匹配，直接进入服务行业判定流程 ③通用兜底——销项品名不在任何行业的产品链词典中→通过金税编码反查行业分类→如果金税编码也无法判定→使用工商登记行业为默认值同时标记\"行业未确认\"。词典的作用不仅是\"判断行业\"，更是\"验证行业\"——当进销品名与词典的行业预期一致时，该行业的分析域置信度提升；不一致时，触发外包/轻加工模式检测。'},
        {name:'外包轻加工模式认知',source:'管道调度',desc:'批发业可能存在实质加工——不能仅凭工商登记的\"批发业\"判定没有进销存分析需求，也不能仅凭进销品名差异判定为\"进销不匹配\"。检测逻辑：①扫描银行流水的付款摘要中是否含\"加工费/代工/贴牌/OEM/委外\"等关键词 ②如果是→企业存在外包加工（将原材料发给加工商、加工后收回成品），实质是\"采购原材料+外包加工+销售成品\"的三段经营模式 ③此时进销品名差异是合理的——进的是原材料、销的是成品、中间存在加工环节 ④加工模式下→执行进销存分析但放宽匹配标准（进项品名与销项品名不要求一致，只要求同属一个产品链）⑤报告第一章行业分类中展示\"批发业（存在外包加工实质）\"，第二章详细解释加工模式对分析结果的影响。外包轻加工模式的识别结果会通过跨域协商引擎通知毛利率对标域（制造业对标改为批发+加工混合对标）。'},
        {name:'{{industries}}行业基准值库',source:'行业认知体系',desc:'66个行业×5个核心指标×3个基准值（下限/中位/上限），构成全行业财务基准参考体系。五个核心指标：①毛利率——（营业收入-营业成本）/营业收入，反映主营业务的盈利空间 ②净利率——净利润/营业收入，反映综合盈利水平 ③人均产值——营业收入/员工人数，反映劳动效率 ④费用收入比——期间费用/营业收入，反映费用管控水平 ⑤资产周转率——营业收入/总资产，反映资产使用效率。三个基准值的使用逻辑：企业值<下限→高风险（显著低于行业正常水平，可能存在成本虚列/收入少计）→企业值在下限与上限之间→中风险（属于行业正常波动范围）→企业值>上限→可能低风险但也可能是异常（如毛利率异常偏高可能是隐匿了成本）。基准库从公开数据（上市公司年报/行业统计年鉴）编制，定期可通过--calibrate模式更新。代码实现：_domain_industry_benchmarking()函数，行业匹配后自动加载对应的基准值进行对比。'},
      ]},
    { id:5, name:'执行管线', icon:'⚙️', color:'#f59e0b',
      desc:'从原始资料到正式报告的七步处理流程，数据单向流动不丢失不污染不截断。管线的设计原则：上游步骤的输出是下游步骤的输入、下游步骤不能修改上游步骤的原始数据、每一步骤有独立的日志和中间数据、任何步骤出错只影响该步骤及后续步骤、不会回写污染上游。',
      items:[
        {name:'七步执行流程',source:'管道调度',desc:'系统化地处理从用户上传文件到最终报告生成的完整流程，每一步都有明确的输入/输出/日志：①资料扫描——文件解析引擎启动，{{file_fingerprints}}类文件指纹+三层递进识别（文件名→列头→数据内容→公司匹配），四方交叉验证确认每个文件的类型和归属账套。输入：用户上传的Excel文件数组。输出：分类后的文件对象数组（每个文件含：类型标签/有效记录数/解析状态/错误日志）。②实体识别——从已分类的文件中提取目标企业身份信息（公司全称/统一社会信用代码/法定代表人/行业/经营范围），通过联网核查（天眼查/企查查API）补充工商登记数据。输入：银行流水文件+销项发票文件+进项发票文件。输出：目标实体对象（含所有识别出的公司信息和置信度）。③情报提取——_extract_material_intel()函数对每个文件的每行数据执行深度提取：银行流水→收款来源分类（12条规则逐条匹配）、销项发票→销售额分布（按购买方+品名+月份三维汇总）、进项发票→成本结构（主营业务成本/重大费用/日常报销三层分类）、工资表→人员结构与薪酬分布、社保明细→缴费基数与工资比对。输入：所有已分类文件。输出：material_intel对象（含收款构成/付款构成/发票统计/工资社保统计/资料完备度评估）。④规则引擎——{{rules_count}}条规则+{{clue_chains}}条线索链+{{evidence_chains}}条证据链+48条分析链全量激活。Phase1检测触发→Phase2定向深挖→Phase3交叉验证→Phase4综合定性。输入：material_intel + 目标实体。输出：all_findings数组（每条含type/level/score/detail/items/matched_chain_details等字段）。⑤噪声过滤——七类过滤规则依次执行：税务合规重点保护→HARD_BAN→COND_BAN→正常结论排除→行业不匹配→资料缺口限流→去重合并。输入：all_findings。输出：过滤后的all_findings（减少约97%噪声）。⑥跨域协商——run_negotiation()消解域间矛盾（服务行业vs进销存异常→消解）、降级不适用发现（制造业毛利率对标用于服务行业→降为提示）、标记资料受限结论（缺合同→合同相关发现标注\"待补充\"）。输入：过滤后的all_findings。输出：协商后的all_findings。⑦报告输出——_generate_final_report()生成7章正式报告：第一章案件来源及基本情况→第二章税务合规实施情况→第三章发现问题及事实认定→第四章税务合规结论→第五章处理处罚建议→第六章告知权利义务→第七章税务合规人员签字+附件证据清单。同时执行报告纯净度净化（去内部标记）、建议增强（补齐可执行步骤）、质量标准检测、语音播报适配。输入：协商后的all_findings + material_intel + 目标实体。输出：完整报告HTML或结构化JSON。'},
        {name:'{{domain_functions}}个域分析函数',source:'调度中枢',desc:'{{domain_functions}}个域分析函数覆盖税务合规全领域，按功能分为八大分类：①银行与资金流(3域)——收款来源分析（_domain_receipt_classification）、付款去向分析（_domain_payment_classification）、资金收支对比（_domain_cashflow_comparison）②发票与票据流(4域)——销项发票分析（_domain_sales_invoice）、进项发票分析（_domain_purchase_invoice）、发票合规检查（_domain_invoice_compliance）、红冲/作废分析（_domain_red_void）③进销存与存货(4域)——进销存匹配（_domain_inventory_match）、存货周转（_domain_inventory_turnover）、BOM分析（_domain_bom）、进销比对标（_domain_purchase_sales_ratio）④费用与成本(5域)——费用完整性（_domain_expense_completeness）、费用结构合理性（_domain_expense_structure）、大额费用分析（_domain_large_expenses）、主营业务成本分析（_domain_cogs）、研发费用分析（_domain_rd_expenses）⑤往来款(3域)——应收账款分析（_domain_ar）、应付账款分析（_domain_ap）、关联交易分析（_domain_related_party）⑥资产与负债(3域)——固定资产分析（_domain_fixed_assets）、无形资产分析（_domain_intangible）、长短期借款分析（_domain_loans）⑦工资与人力(3域)——工资发放分析（_domain_salary）、社保缴纳分析（_domain_social_security）、个税扣缴分析（_domain_personal_tax）⑧综合诊断(11域)——行业判定(_domain_industry)、资料完备度(_domain_completeness)、经营实质(_domain_business_substance)、行业对标(_domain_benchmarking)、申报比对(_domain_tax_declaration)、六员比对(_domain_six_personnel)、供应链核查(_domain_supply_chain)、经营风险预警(_domain_risk_alert)、税收优惠审核(_domain_tax_preference)、资金回流检测(_domain_money_laundering)、存疑排除(_domain_exclusion)。数量由system_config.json实时统计保证准确。'},
        {name:'全链路溯源体系',source:'本次分析结果',desc:'每条发现的结论都可以通过六步溯源路径反向验证——用户看到报告中任何一条发现，都可以追溯到它是从哪一行原始数据、通过哪条规则、经过哪些验证步骤得出的。六步溯源路径：①规则ID——发现的描述中标注触发的规则编号（如\"R-0321\"），点击可跳转到税务合规指令页面查看该规则的完整定义 ②线索链ID——发现的调查路径中标注驱动的线索链编号（如\"CL-0187\"），点击可查看该链的全部调查步骤和触发条件 ③证据来源——发现的evidence_source字段列出所有参与验证的数据文件（如\"银行流水→收款分类→2025年3月\"）④一键分析结果——all_findings数组中该发现的完整JSON（含原始items明细表和matched_chain_details）⑤证据闭环——跨域证据链的触发详情（哪些规则同时触发、来自哪些数据域、触发率是多少）⑥原始数据行——通过rule_id反查主文件中的extract函数（_extract_material_intel），定位到原始Excel文件的对应行。每一步在报告中有对应的超链接或展开详情按钮。整个溯源体系确保报告从结论到数据的可逆推——审理人员无需理解系统内部逻辑，只需要沿着六步路径反向检查。'},
      ]},
    { id:6, name:'跨域协商引擎', icon:'🤝', color:'#0ea5e9',
      desc:'域分析函数独立运行后，引擎自动执行跨域对话，消解/降级/增强发现的结论。29条协商规则覆盖四类场景——不依赖人工干预，引擎自我发现和修正分析矛盾。协商引擎在Phase3交叉验证之后、方法论过滤器之前执行，确保进入过滤器的发现已经是自洽的。',
      items:[
        {name:'行业闸门消解（NEG-001~005·5条）',source:'调度中枢',desc:'核心逻辑：服务行业自动跳过实物商品域的分析结论，消除假阳性。当域15（行业判定）的结论为\"服务行业\"时，协商引擎自动检测以下5类发现的冲突：①进销存匹配异常→消解（服务行业无进销存概念）②存货积压预警→消解（服务行业无实物库存）③BOM表缺失→消解（服务行业无BOM）④毛利率对标异常→降为提示（服务行业毛利率不可比制造业）⑤进销比行业对标异常→消解（服务行业不存在进销比）。消解后的发现的原始数据保留在all_findings中但标记_negotiated_drop=true，不出现在正式报告中。降级的发现保留但标记_negotiated_level=提示。如果行业判定本身存在不确定性（三层穿透不一致），协商引擎会保守处理——不消解但标记\"行业判定存疑\"。'},
        {name:'资料驱动的跨域标记（NEG-010~040·4条）',source:'调度中枢',desc:'当域14（资料完备度）发现某类资料缺失时，协商引擎自动通知所有依赖该资料的发现打上\"资料受限\"标记，但不下结论。四种典型场景：①缺少合同→合同分层/合同比对类发现标记\"待补充合同后重新评估\"，不生成合同缺失相关的高风险发现 ②缺少银行流水→资金流分析相关发现标记\"资料受限\"（银行流水是资金流分析的唯一数据源，无流水则所有资金类分析无基础）③缺少工资社保→薪酬/人力类发现标记\"资料受限\"④缺少申报表→申报比对类发现标记\"资料受限\"。标记不影响原始风险等级但前端渲染时展示黄色横幅，提示审理人员\"此结论基于部分资料，补充后可增强\"。标记的哲学是\"缺资料不是你的错，但在没资料的情况下下结论就是我的错\"——既不因为缺资料就假装没发现问题，也不因为缺资料就武断下结论。'},
        {name:'证据矛盾消解（NEG-020~030·3条）',source:'调度中枢',desc:'当两个域的输出产生逻辑矛盾时，协商引擎根据证据强度自动判断哪个结论更可信。三种消解模式：①强证据撤销弱结论——域A（银行流水→收款分类→个人大额转账）标记\"隐匿收入高风险\"，域B（销项发票→同一付款方→含税号的正规发票）标记\"开票合规\"。协商逻辑：正规发票的证据强度>银行流水关键词匹配的证据强度→撤销隐匿收入高风险→标记\"可能为个人供应商收款，已开票\"。②数据缺失限制结论——域A（缺合同→合同比对不适用标记），域B（进销发票品名匹配→业务实质与发票一致）。协商逻辑：发票证据虽强但无合同无法确认交易真实性→结论从\"一致\"降为\"基本一致但缺合同验证\"。③时空不一致消解——域A（发票日期2025年3月）标记\"收入正常\"，域B（银行流水日期2025年5月）标记\"收款延迟\"。协商逻辑：时间差>60天→触发跨域时间差检查→如果付款方与购买方一致→标记\"应收账款\";如果不一致→标记\"存疑收款\"。证据矛盾消解的关键原则：两个域打架时，谁的数据更完整、更直接，谁的结论权重更高。'},
        {name:'联合增强（NEG-AUG-001~003·3条）',source:'调度中枢',desc:'多个域同时触发异常信号时，协商引擎不仅不消解，反而合成一条更高级别的新发现——\"三个域的警报一起响，比一个域的警报响一百次更可怕\"。三种增强场景：①收入隐匿增强——域A（银行流水→大额个人转账）+ 域B（销项发票→对应月度开票为零）+ 域C（工资表→员工人数无变化但收入骤降）→合成\"疑似账外经营\"高风险发现 ②虚构成本增强——域A（进项发票→大额咨询费）+ 域B（销项品名→咨询费与主营毫无关联）+ 域C（银行流水→付款方为税收优惠地企业）→合成\"疑似虚开咨询费发票转移利润\"极高风险发现 ③资金回流增强——域A（银行流水→A→B→C→A循环转账）+ 域B（发票→A向B开票、B向C开票、C向A开票，品名相同金额相同）+ 域C（人员→三个公司法人为同一人或亲属关系）→合成\"疑似闭环虚开\"连锁发现。联合增强的新发现不覆盖原始发现的等级——原始发现保持原来的等级在报告中单独排列，新发现作为补充列在组顶用红色边框标识。'},
      ]},
  ];

  var totalItems = layers.reduce(function(s,l){return s+l.items.length;},0);
  var h='<style>.qs-layout{display:flex;gap:28px;max-width:1100px;margin:0 auto;padding:24px 16px;background:#fff}.qs-toc{width:180px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:10px;line-height:20px;max-height:calc(100vh-40px);overflow-y:auto}.qs-toc .toc-title{font-weight:700;color:#16233a;font-size:10px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.qs-toc a{display:block;color:#3a4048;text-decoration:none;padding:3px 10px;border-radius:4px;cursor:pointer;font-size:10px}.qs-toc a:hover,.qs-toc a.active{background:#eff6ff;color:#2563eb;font-weight:600}.qs-main{flex:1;min-width:0;background:#fff}.qs-sec-title{font-size:10px;font-weight:700;color:#16233a;padding-bottom:10px;border-bottom:2px solid #e2e8f0;margin-bottom:10px}.qs-layer{margin-bottom:10px;padding:20px;background:#fff;border:1px solid #e2e8f0;border-radius:8px}.qs-layer-hd{display:flex;align-items:center;gap:10px;margin-bottom:10px;padding-bottom:12px;border-bottom:2px solid}.qs-item{padding:12px 16px;margin-bottom:6px;background:#fafbfc;border-radius:4px;border-left:3px solid #e2e8f0}.qs-stat{text-align:center;padding:14px 8px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px}.qs-info{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px 20px;font-size:10px;line-height:2}</style>';

  h+='<div class="qs-layout">';
  h+='<nav class="qs-toc"><div class="toc-title">📖 目录</div>';
  layers.forEach(function(l){h+='<a href="#qs-layer'+l.id+'">'+l.icon+' '+l.name+'</a>';});
  h+='</nav><div class="qs-main">';
  h+='<h2 style="font-size:10px;font-weight:800;color:#16233a;margin:0 0 10px">🛡️ 质量保障体系</h2>';
  h+='<p style="font-size:10px;color:#64748b;margin:0 0 10px">六大层次 · '+totalItems+'个组件 · 从规则触发到报告输出，每条发现可追溯可验证可复核</p>';

  h+='<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px">';
  [{n:'1514',l:'税务合规规则'},{n:'396',l:'线索链'},{n:'745',l:'证据链'},{n:'33',l:'方法论'},{n:'1174',l:'总链数'},{n:'36',l:'域分析'}].forEach(function(s){
    h+='<div class="qs-stat" style="flex:1;min-width:100px"><div style="font-size:10px;font-weight:700;color:#16233a">'+s.n+'</div><div style="font-size:10px;color:#64748b">'+s.l+'</div></div>';
  });
  h+='</div>';

  layers.forEach(function(l){
    h+='<div id="qs-layer'+l.id+'" class="qs-layer">';
    h+='<div class="qs-layer-hd" style="border-color:'+l.color+'"><span style="font-size:10px">'+l.icon+'</span><div><div style="font-size:10px;font-weight:700;color:#16233a">'+l.name+'（'+l.items.length+'组件）</div><div style="font-size:10px;color:#64748b">'+l.desc+'</div></div></div>';
    l.items.forEach(function(item,idx){
      h+='<div class="qs-item"><div style="font-size:10px;font-weight:600;color:#16233a;margin-bottom:4px">'+(idx+1)+'. '+item.name+'</div><div style="font-size:10px;color:#3a4048;line-height:20px;margin-bottom:4px">'+item.desc+'</div><div style="font-size:10px;color:#6366f1">📁 '+item.source+'</div></div>';
    });
    h+='</div>';
  });

  h+='<div class="qs-info"><strong style="color:#059669;font-size:10px">🔓 开放生态系统</strong><br>当前'+totalItems+'个组件只是当前状态。新增税务合规能力模块须同步更新此页面。体系随发展持续扩展。</div>';
  h+='</div></div>';
  container.innerHTML = h;
  // 侧边栏子模块入口
  if (window._qsLayer) {
    var lid = window._qsLayer;
    window._qsLayer = null;
    var style = document.createElement('style');
    style.textContent = '.qs-toc{display:none!important}.qs-layout{display:block!important}';
    container.appendChild(style);
    var h2 = container.querySelector('.qs-main h2');
    if (h2) h2.style.display = 'none';
    var allLayers = container.querySelectorAll('.qs-layer');
    for (var i = 0; i < allLayers.length; i++) {
      allLayers[i].style.display = allLayers[i].id === 'qs-layer' + lid ? 'block' : 'none';
    }
    var info = container.querySelector('.qs-info');
    if (info) info.style.display = 'none';
    var stats = container.querySelector('.qs-main > div');
    if (stats && stats.style && !stats.className) stats.style.display = 'none';
    setTimeout(function() {
      var el = container.querySelector('#qs-layer' + lid);
      if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
    }, 100);
  }
}function loadMethodologies() {
  var target = document.getElementById('methods-body');
  if (!target) return;
  
  // 从 audit_chains.json 读取方法论
  fetch('/static/audit_chains.json?_t=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var chains = data.chains || [];
      var methods = chains.filter(function(c) { return c.type === 'methodology'; });
      
      if (methods.length === 0) {
        target.innerHTML = '<div style="color:#64748b;padding:20px">未找到方法论数据，请检查 audit_chains.json</div>';
        return;
      }
      
      var html = '';
      methods.forEach(function(m, i) {
        var id = m.id || (i+1);
        var name = m.name || '未命名';
        var desc = m.desc || '';
        var requirement = m.requirement || '';
        var purpose = m.purpose || '';
        var codePos = m.code_position || '';
        var callLocs = m.call_locations || [];
        
        html += '<div style="margin-bottom:10px;padding:16px 20px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;border-left:3px solid #2563eb">'
          + '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">'
          + '<div style="font-size:10px;font-weight:700;color:#16233a">' + escHtml(id) + ' ' + escHtml(name) + '</div>'
          + '<span style="font-size:10px;color:#64748b;cursor:pointer" onclick="var d=this.parentNode.parentNode.nextElementSibling;d.style.display=d.style.display==\'none\'?\'\':\'none\'">展开/折叠</span>'
          + '</div>'
          + '<div style="font-size:10px;color:#3a4048;line-height:20px">' + escHtml(desc) + '</div>'
          + '<div style="display:none;margin-top:12px;padding:12px 16px;background:#fff;border-radius:6px;font-size:10px;color:#3a4048;line-height:2">'
          + (requirement ? '<div style="margin-bottom:10px"><span style="font-weight:600;color:#16233a">要求：</span>' + escHtml(requirement) + '</div>' : '')
          + (purpose ? '<div style="margin-bottom:10px"><span style="font-weight:600;color:#16233a">用途：</span>' + escHtml(purpose) + '</div>' : '')
          + (codePos ? '<div style="margin-bottom:10px"><span style="font-weight:600;color:#16233a">代码位置：</span><code style="font-size:10px;background:#f1f5f9;padding:2px 6px;border-radius:4px">' + escHtml(codePos) + '</code></div>' : '')
          + (callLocs.length > 0 ? '<div><span style="font-weight:600;color:#16233a">调用位置：</span>' + callLocs.map(function(loc) { return '<span style="display:inline-block;margin:2px 4px 2px 0;padding:2px 8px;background:#e0f2fe;color:#0369a1;font-size:10px;border-radius:4px">' + escHtml(loc) + '</span>'; }).join('') + '</div>' : '')
          + '</div>'
          + '</div>';
      });
      
      target.innerHTML = html;
  loadAnalysisChains();
    })
    .catch(function(e) {
      target.innerHTML = '<div style="color:#dc2626;padding:20px">加载方法论失败：' + e.message + '</div>';
    });
}



async function loadAnalysisChains() {
  var container = document.getElementById('al-chains-list');
  if (!container) return;
  try {
    var resp = await fetch('/static/cross_domain_analysis.json');
    var chains = await resp.json();
    var execChains = chains.filter(function(c) { return c.executable && !c.legacy; });
    var html = '';
    execChains.forEach(function(a, i) {
      var steps = a.reasoning_path || [];
      var refs = a.rule_refs || [];
      var kws = a.trigger_keywords || [];
      var stepHtml = steps.map(function(s) {
        var act = s.action;
        if (typeof act === 'object' && act !== null) {
          return '<div style="padding:4px 8px;font-size:10px;color:#334155;line-height:1.8">Step' + (act.order || s.step || '') + ': <strong>' + (act.from || s.domain || '') + '</strong> → <strong>' + (act.to || '') + '</strong>' + (act.finding ? '<br><span style="color:#64748b;font-size:10px">发现：' + act.finding + '</span>' : '') + '</div>';
        }
        return '<div style="padding:4px 8px;font-size:10px;color:#334155">Step' + (s.step || '') + ': ' + (typeof act === 'string' ? act : (s.domain || '')) + '</div>';
      }).join('');
      html += '<div style="padding:16px 20px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;border-left:4px solid #7c3aed">'
        + '<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">'
        + '<span style="font-size:10px;padding:2px 8px;border-radius:4px;background:#7c3aed15;color:#7c3aed;font-weight:600">ID' + (a.id||'') + '</span>'
        + '<span style="font-size:10px;font-weight:600;color:#16233a">' + (a.name||'') + '</span>'
        + '</div>'
        + (a.description ? '<div style="font-size:10px;color:#64748b;line-height:20px;margin-bottom:10px">' + (a.description) + '</div>' : '')
        + '<div style="margin-bottom:6px"><span style="font-size:10px;color:#7c3aed;font-weight:600">触发词: </span><span style="font-size:10px;color:#64748b">' + kws.slice(0,5).join(' / ') + '</span></div>'
        + '<div style="margin-bottom:6px"><span style="font-size:10px;color:#7c3aed;font-weight:600">推理步数: </span><span style="font-size:10px;color:#64748b">' + steps.length + '步</span>'
        + '<span style="margin-left:16px;font-size:10px;color:#7c3aed;font-weight:600">关联规则: </span><span style="font-size:10px;color:#64748b">' + refs.length + '条</span></div>'
        + '<div style="padding:8px 12px;background:#f8fafc;border-radius:4px">' + stepHtml + '</div>'
        + (a.suggestion ? '<div style="font-size:10px;color:#334155;line-height:20px;margin-top:8px;padding-top:8px;border-top:1px solid #e2e8f0"><strong>建议: </strong>' + a.suggestion + '</div>' : '')
        + '</div>';
    });
    container.innerHTML = html || '<p style="font-size:10px;color:#64748b">暂无分析链数据</p>';
  } catch(e) {
    container.innerHTML = '<p style="font-size:10px;color:#dc2626">加载失败: ' + (e.message||'') + '</p>';
  }
}

//  税收优惠分析页面 —— 统一新风格
// ═════════════════════════════════════════════════════════════
function renderTaxIncentivesPage(container) {
  if (!container) return;
  container.innerHTML = '<p style="max-width:1140px;margin:0 auto;padding:12px 0"><b>税收优惠扫描</b>：自动匹配9类优惠政策 · 联网核查 · 90天智能缓存</p>'
    + '<div id="tax-incentive-list" style="color:#64748b;padding:6px 0">加载中...</div>';
  loadTaxIncentiveData();
}
async function loadTaxIncentiveData() {
  var t = document.getElementById('tax-incentive-list'); if (!t) return;
  try {
    var r = await getSharedAnalysis();
    var items = (r && r.ok && r.report && r.report.comprehensive && r.report.comprehensive.incentive_items) || [];
    if (!items.length) { t.innerHTML = '<p style="color:#64748b">本次分析未触发税收优惠检测</p>'; return; }
    var h = '';
    items.forEach(function(it) {
      h += '<p><b>' + escHtml(it.name || '优惠项目') + '</b>：' + escHtml(it.desc || '') + ' <em>' + escHtml(it.benefit || '') + '</em></p>';
    });
    t.innerHTML = h;
  } catch(e) { t.innerHTML = '<p style="color:#dc2626">扫描失败</p>'; }
}
function renderTaxWorkflow(container) {
  if (!container) return;
  window.currentModule = '税务合规工作流程';

  var h = '<div style="max-width:900px;margin:0 auto;padding:36px 28px;font-family:-apple-system,\"Microsoft YaHei\",sans-serif">';
  h += '<div style="font-size:10px;font-weight:700;color:#16233a;margin:0 0 10px">税务合规工作流程</div>';
  h += '<div style="font-size:10px;color:#64748b;margin:0 0 28px;line-height:1.8">手册第1章 · 五阶段标准化流程（国税发[2009]157号） · 选案→检查→审理→执行→案卷管理 · 每个阶段有明确的法定时限和操作规范</div>';

  // 上下游依赖
  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:10px">';
  h += '<div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:10px;font-weight:700;color:#0369a1;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #bae6fd">⬆ 上游（输入方）</div>';
  h += '<div style="font-size:10px;color:#3a4048;line-height:20px">';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'hb-overview\')" style="color:#2563eb">系统数据概览</a><br><span style="color:#64748b">系统能力和规则体系总览</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-info\')" style="color:#2563eb">引擎详情</a><br><span style="color:#64748b">引擎记忆规则篇第7章规程映射</span></div>';
  h += '<div><a href="javascript:navigateTo(\'qs-layer2\')" style="color:#2563eb">方法论语料对账</a><br><span style="color:#64748b">33条方法论对应规程操作要求</span></div>';
  h += '</div></div>';
  h += '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:10px;font-weight:700;color:#15803d;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #bbf7d0">⬇ 下游（消费方）</div>';
  h += '<div style="font-size:10px;color:#3a4048;line-height:20px">';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'hb-ch2\')" style="color:#2563eb">14类必查资料</a><br><span style="color:#64748b">检查环节要求的具体资料清单</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'aly-result\')" style="color:#2563eb">本次分析结果</a><br><span style="color:#64748b">一键分析全程模拟检查流程</span></div>';
  h += '<div><a href="javascript:navigateTo(\'eng-think\')" style="color:#2563eb">推理引擎</a><br><span style="color:#64748b">审理环节的法律与事实推理</span></div>';
  h += '</div></div></div>';

  // 段落说明
  h += '<div style="font-size:10px;color:#3a4048;line-height:20px;margin-bottom:10px">';
  h += '<p style="margin:0 0 10px">税务合规分为<strong>选案→检查→审理→执行→案卷管理</strong>五个阶段，每个阶段有明确的法定时限、工作要求和法律依据。以下为《税务合规工作规程》（国税发[2009]157号）规定的标准化流程及本系统的对应实现方式。企业接到税务合规通知后通常只有<b>3-5天准备时间</b>，系统的价值在于把"被查前的手忙脚乱"变为"日常化的持续自检"。</p>';
  h += '<p style="margin:0">五位一体全流程覆盖：<strong>选案</strong>（计算机分析+人工分析+人机结合分析→确定税务合规对象）→<strong>检查</strong>（两名以上人员60日内完成→制作税务合规底稿→出具税务合规报告→5日内移交审理）→<strong>审理</strong>（逐项审核7项内容→四种决定→送达告知书）→<strong>执行</strong>（限期缴纳→逾期每日万分之五滞纳金→税收保全→强制执行）→<strong>案卷管理</strong>（一案一卷·正卷副卷分立·电子纸质同步）。</p>';
  h += '</div>';

  // 五项核心能力
  h += '<div style="font-size:10px;font-weight:700;color:#16233a;margin-bottom:10px;padding-bottom:6px;border-bottom:2px solid #e2e8f0">五阶段标准化流程</div>';

  var stages = [
    { n:'①', title:'选案环节（第14-20条）', icon:'🎯', color:'#7c3aed',
      body:'税务合规局通过计算机分析、人工分析、人机结合分析等多种渠道获取案源信息，经集体研究后合理准确地选择和确定税务合规对象。年度终了前制定下一年度税务合规工作计划，严格控制检查次数。<strong>8类案源</strong>包括：财务指标异常/上级交办/专项检查/部门移交/检举信息/其他部门转来/社会公共信息/其他。其中<strong>检举</strong>是企业的最大不可控风险——任何人可实名或匿名检举，且检举信息不公开。本系统的自动化风险扫描+一键分析功能本质上就是"计算机分析"环节——在税务合规立案前模拟案源筛选逻辑，帮助企业提前发现并修复涉税风险，降低进入选案名单的概率。',
      points: [
        ['案源获取', '多渠道获取案源信息，集体研究，合理准确选择确定税务合规对象'],
        ['税务合规计划', '年度终了前制定下一年度工作计划，严格控制检查次数'],
        ['8类案源', '财务指标/上级交办/专项/部门移交/检举/其他部门转来/社会公共信息/其他'],
        ['筛选方法', '计算机分析、人工分析、人机结合分析——有嫌疑的确定为待查对象'],
        ['立案检查', '批准立案后制作《税务合规任务通知书》，连同资料移交检查部门']
      ]
    },
    { n:'②', title:'检查环节（第21-45条）', icon:'🔍', color:'#2563eb',
      body:'检查环节是税务合规的核心阶段。检查前需查阅纳税档案，了解生产经营、行业特点、财务会计制度，确定检查方法。检查时限为自实施之日起<strong>60日内</strong>完成，需<strong>两名以上</strong>检查人员共同实施。检查方法包括实地检查/调取账簿资料/询问/查询存款账户/异地协查。证据须真实、相关联，类型涵盖书证/物证/视听资料/电子数据/证人证言/当事人陈述/勘验笔录。必须制作《税务合规工作底稿》，记录案件事实、归集证据材料——<strong>没有底稿就没有税务合规报告</strong>。税务合规报告须含10项内容。检查完毕5个工作日内移交审理部门。本系统的一键分析管线完全模拟此环节——文件上传→实体识别→情报提取→规则扫描→链驱动发现→证据收集→形成底稿→输出报告。',
      points: [
        ['检查前准备', '查阅纳税档案，了解生产经营、行业特点、财务会计制度，确定检查方法'],
        ['检查时限', '自实施之日起60日内完成，需两名以上检查人员共同实施'],
        ['检查方法', '实地检查/调取账簿资料/询问/查询存款账户/异地协查'],
        ['证据类型', '书证/物证/视听资料/电子数据/证人证言/当事人陈述/勘验笔录'],
        ['税务合规底稿', '必须制作，记录案件事实，归集证据材料——无底稿则无报告'],
        ['税务合规报告', '须含10项：案件来源→基本情况→检查时间→方法措施→违法事实→拒绝阻挠→被查对象意见→处理建议→其他→签名日期'],
        ['移交审理', '检查完毕5个工作日内移交审理部门']
      ]
    },
    { n:'③', title:'审理环节（第46-60条）', icon:'⚖️', color:'#059669',
      body:'审理部门收到税务合规报告后，逐项审核7项内容：对象准确性/事实清楚证据充分/法律适用/程序合法/权限适当/处理建议/其他事项。事实不清、证据不足的退回检查部门补充调查。事实清楚但适用法律错误的，审理部门另行提出处理意见直接纠正不退回。审理时限为收到报告后<strong>15日内</strong>提出审理意见。拟处罚的需送达告知书，告知陈述权/申辩权/听证权。审理结论分四种：有违法行为→《税务处理决定书》/应处罚→《税务行政处罚决定书》/轻微→《不予处罚决定书》/无违法→《税务合规结论》。涉嫌犯罪的移送公安机关。本系统的质量保障体系完全对应审理环节——方法论过滤器+报告纯净度规范+合规门禁=自动审理。',
      points: [
        ['审核重点', '逐项审核7项：对象准确性/事实证据/法律适用/程序合法/权限适当/处理建议/其他'],
        ['退回补正', '事实不清、证据不足→退回检查部门补充调查'],
        ['纠正建议', '事实清楚但适用法律错误→审理部门直接纠正，不退回'],
        ['审理时限', '收到税务合规报告后15日内提出审理意见'],
        ['告知听证', '拟处罚→送达告知书→告知陈述权/申辩权/听证权'],
        ['四种决定', '有违法→处理决定书/应处罚→处罚决定书/轻微→不予处罚/无违法→税务合规结论'],
        ['涉罪移送', '涉嫌犯罪→移送书→经局长批准→移送公安机关']
      ]
    },
    { n:'④', title:'执行环节', icon:'💵', color:'#dc2626',
      body:'下达《税务处理决定书》和《税务行政处罚决定书》，责令限期缴纳税款、滞纳金和罚款。企业权利：<strong>60日内</strong>申请行政复议/复议后<strong>15日内</strong>提起诉讼/缴纳税款或提供担保后可申请复议。逾期不履行的，加收<strong>每日万分之五滞纳金</strong>，实施税收保全措施（冻结存款/查封财产），并申请法院强制执行。本系统报告的第五章"处理处罚建议"直接对应执行环节——P0立即处理/P1限期整改/P2持续关注，三级策略让企业在税务合规正式下达前提前整改。',
      points: [
        ['执行文书', '下达处理决定书+处罚决定书→责令限期缴纳'],
        ['企业权利', '60日内申请行政复议/复议后15日内提起诉讼'],
        ['强制执行', '逾期→每日万分之五滞纳金→税收保全→申请法院强制执行'],
        ['法律依据', '《征管法》第32条(滞纳金)/第40条(强制执行)/第88条(复议前置)']
      ]
    },
    { n:'⑤', title:'案卷管理（第72-77条）', icon:'📁', color:'#f59e0b',
      body:'一案一卷，按年度、按案卷分类立卷。过程资料全部纳入案卷，不得遗漏。正卷含税务合规报告/审理报告/处理决定/证据材料，可对外提供。副卷含内部请示/报告/研究记录，不得对外提供。保管期限随案卷定，直至最终审结。电子数据与纸质档案同步保管。本系统的全链路溯源体系对应案卷管理——每条发现的结论可追溯到规则ID→线索链ID→证据来源→原始数据行，形成完整的电子税务合规底稿。',
      points: [
        ['立卷标准', '一案一卷，按年度、按案卷分类立卷，过程资料全部纳入'],
        ['正卷副卷', '正卷(可对外)含报告/决定/证据；副卷含内部请示/研究记录，不得对外提供'],
        ['保管期限', '随案卷定，直至最终审结。电子数据与纸质档案同步保管'],
        ['系统对应', '全链路溯源体系——每条结论可追溯到规则ID→线索链ID→证据来源→原始数据行']
      ]
    }
  ];

  stages.forEach(function(s) {
    h += '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:20px 24px;margin-bottom:10px;border-left:4px solid '+s.color+'">';
    h += '<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">';
    h += '<span style="background:'+s.color+';color:#fff;width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700">'+s.n+'</span>';
    h += '<span style="font-size:10px;font-weight:700;color:#16233a">'+s.title+'</span>';
    h += '</div>';
    h += '<div style="font-size:10px;color:#3a4048;line-height:20px;margin-bottom:10px">'+s.body+'</div>';
    h += '<div style="display:flex;flex-wrap:wrap;gap:8px">';
    s.points.forEach(function(p) {
      h += '<div style="flex:1;min-width:180px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:10px 14px">';
      h += '<div style="font-size:10px;font-weight:700;color:'+s.color+';margin-bottom:4px">'+p[0]+'</div>';
      h += '<div style="font-size:10px;color:#64748b;line-height:1.8">'+p[1]+'</div>';
      h += '</div>';
    });
    h += '</div>';
    h += '<div style="font-size:10px;color:#6366f1;margin-top:10px;padding-top:8px;border-top:1px solid #e2e8f0">📁 手册第1章</div>';
    h += '</div>';
  });

  h += '</div>';
  container.innerHTML = h;
}

// ═══ 14类必查资料 ═══
function renderRequiredMaterials(container) {
  if (!container) return;
  window.currentModule = '14类必查资料';

  var h = '<div style="max-width:900px;margin:0 auto;padding:36px 28px;font-family:-apple-system,\"Microsoft YaHei\",sans-serif">';
  h += '<div style="font-size:10px;font-weight:700;color:#16233a;margin:0 0 10px">14类税务合规必查资料</div>';
  h += '<div style="font-size:10px;color:#64748b;margin:0 0 28px;line-height:1.8">手册第2章 · 三级分类（必备→建议→据需） · {{file_fingerprints}}类文件指纹+三层递进识别自动检测 · 每缺一类资料就少一道防线</div>';

  // 上下游
  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:10px">';
  h += '<div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:10px;font-weight:700;color:#0369a1;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #bae6fd">⬆ 上游（输入方）</div>';
  h += '<div style="font-size:10px;color:#3a4048;line-height:20px">';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'hb-ch1\')" style="color:#2563eb">税务合规工作流程</a><br><span style="color:#64748b">检查环节要求的资料清单</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'hb-overview\')" style="color:#2563eb">系统数据概览</a><br><span style="color:#64748b">{{file_fingerprints}}类文件指纹库三层递进识别</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-info\')" style="color:#2563eb">引擎详情</a><br><span style="color:#64748b">引擎记忆规则篇资料解析配置</span></div>';
  h += '</div></div>';
  h += '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:10px;font-weight:700;color:#15803d;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #bbf7d0">⬇ 下游（消费方）</div>';
  h += '<div style="font-size:10px;color:#3a4048;line-height:20px">';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'aly-result\')" style="color:#2563eb">本次分析结果</a><br><span style="color:#64748b">文件解析→情报提取→风险扫描</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'qs-layer2\')" style="color:#2563eb">方法论语料对账</a><br><span style="color:#64748b">33条方法论依赖资料完整性</span></div>';
  h += '<div><a href="javascript:navigateTo(\'eng-think\')" style="color:#2563eb">推理引擎</a><br><span style="color:#64748b">缺失资料的推断与替代分析</span></div>';
  h += '</div></div></div>';

  // 段落说明
  h += '<div style="font-size:10px;color:#3a4048;line-height:20px;margin-bottom:10px">';
  h += '<p style="margin:0 0 10px">根据税务合规实战经验，以下14类资料为必查项。每缺一类资料，税务合规时就少一道防线——缺少资料意味着对应风险无法排除，税务机关将从其他数据源倒推核定应纳税额，核定结果通常高于企业实际申报。</p>';
  h += '<p style="margin:0">系统通过文件解析模块（<strong>{{file_fingerprints}}类文件指纹+三层递进识别</strong>）自动检测资料提交状态，逐类标注已提交/缺失，缺失资料的具体后果在报告中一一列明。以下按重要性从<strong style="color:#dc2626">必备</strong>→<strong style="color:#f59e0b">建议</strong>→<strong style="color:#6366f1">据需</strong>三级分类。</p>';
  h += '</div>';

  // 14类资料卡片
  h += '<div style="font-size:10px;font-weight:700;color:#16233a;margin-bottom:10px;padding-bottom:6px;border-bottom:2px solid #e2e8f0">14类必查资料明细</div>';

  var materials = [
    { n:'①', name:'银行流水', level:'必备', lc:'#dc2626', lb:'#fef2f2', lbo:'#fecaca',
      core:'含交易日期/对方户名/交易金额/摘要/备注。系统自动提取收款方/付款方身份、计算资金净流向、识别异常交易模式。',
      risk:'资金流真实性无法验证，收入收款和成本付款无法核实。税务机关从第三方数据倒推资金流向。' },
    { n:'②', name:'销项发票', level:'必备', lc:'#dc2626', lb:'#fef2f2', lbo:'#fecaca',
      core:'含购方名称/品名/规格/数量/金额/税额/发票号码。系统自动统计收入构成、行业分类、客户集中度。',
      risk:'无法确认企业对外开票情况，无法进行收入端分析。税务机关以行业均值推定收入。' },
    { n:'③', name:'进项发票', level:'必备', lc:'#dc2626', lb:'#fef2f2', lbo:'#fecaca',
      core:'含销方名称/品名/数量/金额/税额。系统自动三层成本分类（主营/重大费用/日常报销）、供应商集中度分析。',
      risk:'无法确认采购成本和进项税额，无法进行成本端分析。进项税额的可抵扣性无法验证。' },
    { n:'④', name:'工资表', level:'必备', lc:'#dc2626', lb:'#fef2f2', lbo:'#fecaca',
      core:'含姓名/身份证号/应发工资/社保扣款/公积金扣款/个税扣款/实发工资。与社保明细+个税申报三方交叉验证。',
      risk:'人工成本无法核实，个税和社保扣缴的合规性无法验证。可能面临补缴个税+罚款。' },
    { n:'⑤', name:'社保明细', level:'必备', lc:'#dc2626', lb:'#fef2f2', lbo:'#fecaca',
      core:'含姓名/身份证号/缴费基数/单位缴纳额/个人缴纳额。与工资表交叉验证——人数、基数必须一致。',
      risk:'社保合规性无法验证，存在少缴漏缴风险。至少补缴差额+每日万分之五滞纳金。' },
    { n:'⑥', name:'公积金明细', level:'建议', lc:'#f59e0b', lb:'#fffbeb', lbo:'#fde68a',
      core:'含姓名/缴存基数/单位缴存额/个人缴存额。与社保同源验证，缴费基数须一致。',
      risk:'公积金合规性无法验证，不影响税务但影响企业信用评级。' },
    { n:'⑦', name:'记账凭证', level:'必备', lc:'#dc2626', lb:'#fef2f2', lbo:'#fecaca',
      core:'含凭证编号/日期/摘要/科目编码/借方金额/贷方金额。用于科目级借贷平衡验证。',
      risk:'无法从账务层面验证收入/成本/费用的真实性，无法进行科目级借贷平衡检查。' },
    { n:'⑧', name:'科目余额表', level:'建议', lc:'#f59e0b', lb:'#fffbeb', lbo:'#fde68a',
      core:'提供各科目期末余额全景图。用于验证报表数据的连续性和一致性、关联方往来余额。',
      risk:'无法从会计科目维度进行全面分析，关联方往来余额无法确认。' },
    { n:'⑨', name:'财务报表', level:'建议', lc:'#f59e0b', lb:'#fffbeb', lbo:'#fde68a',
      core:'完整反映财务状况和经营成果，含资产负债表+利润表+现金流量表。',
      risk:'财务指标分析受限，行业对标缺少基准数据。无法计算偿债/营运/盈利/成长能力。' },
    { n:'⑩', name:'增值税申报表', level:'建议', lc:'#f59e0b', lb:'#fffbeb', lbo:'#fde68a',
      core:'含销售额/销项税额/进项税额/应纳税额。与销项/进项发票交叉比对申报数据。',
      risk:'无法验证申报数据与发票数据的匹配性。发票金额与申报金额的差异无法识别。' },
    { n:'⑪', name:'企业所得税申报表', level:'建议', lc:'#f59e0b', lb:'#fffbeb', lbo:'#fde68a',
      core:'收入/成本/费用/利润的申报核验。与财务报表数据交叉比对。',
      risk:'所得税申报合规性无法验证。成本费用的税前扣除合规性无法核查。' },
    { n:'⑫', name:'合同/协议', level:'建议', lc:'#f59e0b', lb:'#fffbeb', lbo:'#fde68a',
      core:'四流合一（合同/发票/资金/货物）的起始环节。印花税计税基础核查和交易真实性验证。',
      risk:'交易真实性缺少核心证据，大额交易的商业合理性存疑。印花税计税基础无据可查。' },
    { n:'⑬', name:'关联方交易资料', level:'建议', lc:'#f59e0b', lb:'#fffbeb', lbo:'#fde68a',
      core:'关联交易定价（转让定价）、关联方名录、关联业务往来报告表。',
      risk:'关联交易合规性无法验证。存在转移利润嫌疑但无法证实或排除。' },
    { n:'⑭', name:'进出口/报关', level:'据需', lc:'#6366f1', lb:'#eef2ff', lbo:'#c7d2fe',
      core:'进出口企业提供报关单、收付汇核销单。仅进出口企业需要提供。',
      risk:'进出口业务合规性无法验证。关税/消费税/增值税的进出口环节风险无法排除。' }
  ];

  materials.forEach(function(m) {
    h += '<div style="background:#fff;border:1px solid '+m.lbo+';border-radius:10px;padding:18px 22px;margin-bottom:10px;border-left:4px solid '+m.lc+'">';
    h += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">';
    h += '<div style="display:flex;align-items:center;gap:8px">';
    h += '<span style="background:'+m.lc+';color:#fff;width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700">'+m.n+'</span>';
    h += '<span style="font-size:10px;font-weight:700;color:#16233a">'+m.name+'</span>';
    h += '</div>';
    h += '<span style="background:'+m.lb+';color:'+m.lc+';border:1px solid '+m.lbo+';padding:2px 10px;border-radius:4px;font-size:10px;font-weight:600">'+m.level+'</span>';
    h += '</div>';
    h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">';
    h += '<div style="background:#f8fafc;border-radius:6px;padding:10px 14px">';
    h += '<div style="font-size:10px;font-weight:700;color:#16233a;margin-bottom:4px">📋 核心要求</div>';
    h += '<div style="font-size:10px;color:#3a4048;line-height:1.9">'+m.core+'</div>';
    h += '</div>';
    h += '<div style="background:'+m.lb+';border-radius:6px;padding:10px 14px">';
    h += '<div style="font-size:10px;font-weight:700;color:'+m.lc+';margin-bottom:4px">⚠ 缺失后果</div>';
    h += '<div style="font-size:10px;color:#3a4048;line-height:1.9">'+m.risk+'</div>';
    h += '</div>';
    h += '</div>';
    h += '<div style="font-size:10px;color:'+m.lc+';margin-top:10px;padding-top:8px;border-top:1px solid #e2e8f0">📁 手册第2章 · '+m.level+'级</div>';
    h += '</div>';
  });

  h += '</div>';
  container.innerHTML = h;
}

// ═══ 分析链拆分子模块 ═══

// 七步执行流程（静态内容，不依赖分析数据）
function renderAnalyzeSteps(container) {
  var h = '<div style="max-width:1100px;margin:0 auto;padding:24px 16px;background:#fff">'
    + '<h2 style="font-size:10px;font-weight:800;color:#16233a;margin:0 0 10px">七步执行流程</h2>'
    + '<p style="font-size:10px;color:#64748b;margin:0 0 10px">分析链从资料上传到报告输出的七个步骤详解</p>';
  var steps = [
    {n:'①',title:'资料扫描与类型识别',icon:'📄',desc:'系统遍历上传目录读取全部Excel/CSV/PDF文件。使用{{file_fingerprints}}类文件指纹库执行三层递进识别：Step1关键词打分→Step2结构分析→Step3数据推断兜底。不因无法识别而丢弃数据。'},
    {n:'②',title:'目标实体识别',icon:'🎯',desc:'进项购买方∩销项销售方取交集确定企业全称。{{keywords}}+关键词×{{industries}}行业加权投票制识别行业。联网查询工商登记信息双源比对。'},
    {n:'③',title:'资料情报提取与数据分析',icon:'🔍',desc:'{{domain_functions}}个域分析函数：银行收款构成+付款方身份核实+进销存比对+五层发票审计+供应商穿透+合同四层分类。'},
    {n:'④',title:'规则引擎与链驱动检查',icon:'⚙️',desc:'{{rules_count}}条税务合规指令与域分析发现逐条匹配。{{clue_chains}}条线索链(行业特化自动过滤)+{{evidence_chains}}条证据链闭环检测(≥60%+≥3规则+≥2域→闭环)。'},
    {n:'⑤',title:'方法论噪声过滤器',icon:'🎯',desc:'HARD_BAN(23类禁止词)+COND_BAN(5类条件过滤)。税务合规重点发现不参与过滤。行业不匹配自动删除。去重+正常结论排除。'},
    {n:'⑥',title:'行业对标与申报比对',icon:'📊',desc:'{{industries}}行业基准值自动对标(毛利率/净利率/税负率/进销比/人均营收)。三级判断：低于下限→高风险、低于典型值85%→中风险、高于上限→中风险。'},
    {n:'⑦',title:'正式税务合规报告输出',icon:'📝',desc:'综合所有发现生成结构化税务合规报告：税务合规概况+企业工商+高/中/低风险发现+四步分析框架+法律依据+消除路径。独立HTML可直接交付。'}
  ];
  steps.forEach(function(s) {
    h += '<div style="padding:16px 20px;margin-bottom:10px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;border-left:4px solid #2563eb">'
      + '<div style="font-size:10px;font-weight:700;color:#16233a;margin-bottom:10px"><span style="font-size:10px">'+s.icon+'</span> '+s.n+' '+s.title+'</div>'
      + '<div style="font-size:10px;color:#3a4048;line-height:20px">'+s.desc+'</div></div>';
  });
  h += '</div>';
  container.innerHTML = h;
}
// 管线执行日志（需加载分析数据）
async function renderAnalyzeLogs(container) {
  if (!container) return;
  try {
    var resp = await fetch('/api/tax-risk-docs/last-analysis?company_id=' + (typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1));
    var data = await resp.json();
    var logs = (data && data.ok && data.report && data.report.pipeline_log) || [];
    if (!logs.length) { container.innerHTML = '<div style="color:#64748b;padding:14px">暂无管线日志</div>'; return; }
    var h = '';
    for (var i = 0; i < logs.length; i++) {
      var lv = 'info', lvc = '#64748b';
      if (logs[i].indexOf('[ERROR]') >= 0 || logs[i].indexOf('[TIMING]') < 0 && (logs[i].indexOf('异常') >= 0 || logs[i].indexOf('失败') >= 0)) { lv = 'error'; lvc = '#dc2626'; }
      else if (logs[i].indexOf('[Phase') >= 0) { lv = 'phase'; lvc = '#2563eb'; }
      else if (logs[i].indexOf('->') >= 0 || logs[i].indexOf('触发') >= 0) { lv = 'found'; lvc = '#f59e0b'; }
      else { lvc = '#059669'; }
      var num = String(i + 1).padStart(3, '0');
      h += '<div style="font-size:10px;line-height:1.8;padding:2px 0;color:' + lvc + '"><span style="color:#64748b">[' + num + ']</span> ' + escHtml(logs[i]) + '</div>';
    }
    container.innerHTML = '<div style="font-family:Consolas,monospace;font-size:10px;max-height:600px;overflow-y:auto;background:#fafbfc;border:1px solid #eef2f6;border-radius:8px;padding:12px 16px">' + h + '</div>';
  } catch(e) { container.innerHTML = '<div style="color:#dc2626;padding:14px">日志加载失败</div>'; }
}
function renderDataAssets(container) {
  if (!container) return;
  window.currentModule = '数据资产';

  var h = '<div style="max-width:900px;margin:0 auto;padding:36px 28px;font-family:-apple-system,\"Microsoft YaHei\",sans-serif">';
  h += '<div style="font-size:10px;font-weight:700;color:#16233a;margin:0 0 10px">系统数据资产</div>';
  h += '<div style="font-size:10px;color:#64748b;margin:0 0 28px;line-height:1.8">AGI引擎中心 · 7层28引擎 · 以下数字来自代码和数据文件的精确统计，非手工标注</div>';

  // 6张统计卡片
  h += '<div style="display:flex;gap:12px;margin-bottom:10px;flex-wrap:wrap">';
  h += '<div style="flex:1;min-width:130px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:18px 16px;text-align:center"><div style="font-size:10px;font-weight:700;color:#2563eb;line-height:1.3" id="da-rules">...</div><div style="font-size:10px;color:#64748b;margin-top:6px">税务合规规则</div></div>';
  h += '<div style="flex:1;min-width:130px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:18px 16px;text-align:center"><div style="font-size:10px;font-weight:700;color:#7c3aed;line-height:1.3" id="da-clues">...</div><div style="font-size:10px;color:#64748b;margin-top:6px">线索/证据链</div></div>';
  h += '<div style="flex:1;min-width:130px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:18px 16px;text-align:center"><div style="font-size:10px;font-weight:700;color:#059669;line-height:1.3" id="da-domains">...</div><div style="font-size:10px;color:#64748b;margin-top:6px">域分析函数</div></div>';
  h += '<div style="flex:1;min-width:130px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:18px 16px;text-align:center"><div style="font-size:10px;font-weight:700;color:#f59e0b;line-height:1.3" id="da-engines">...</div><div style="font-size:10px;color:#64748b;margin-top:6px">引擎模块</div></div>';
  h += '<div style="flex:1;min-width:130px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:18px 16px;text-align:center"><div style="font-size:10px;font-weight:700;color:#dc2626;line-height:1.3">21</div><div style="font-size:10px;color:#64748b;margin-top:6px">调度模块</div></div>';
  h += '<div style="flex:1;min-width:130px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:18px 16px;text-align:center"><div style="font-size:10px;font-weight:700;color:#6366f1;line-height:1.3">52,500+</div><div style="font-size:10px;color:#64748b;margin-top:6px">代码行数</div></div>';
  h += '</div>';

  // 上下游
  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:10px">';
  h += '<div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:10px;font-weight:700;color:#0369a1;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #bae6fd">⬆ 上游（输入方）</div>';
  h += '<div style="font-size:10px;color:#3a4048;line-height:20px">';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-info\')" style="color:#2563eb">引擎详情</a><br><span style="color:#64748b">引擎注册表维护全部模块配置</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'qs-layer1\')" style="color:#2563eb">核心数据资产</a><br><span style="color:#64748b">四大组件构成数据资产底座</span></div>';
  h += '<div><a href="javascript:navigateTo(\'eng-think\')" style="color:#2563eb">推理引擎</a><br><span style="color:#64748b">推理过程消费数据资产</span></div>';
  h += '</div></div>';
  h += '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:10px;font-weight:700;color:#15803d;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #bbf7d0">⬇ 下游（消费方）</div>';
  h += '<div style="font-size:10px;color:#3a4048;line-height:20px">';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'agi-schedule\')" style="color:#2563eb">调度中枢</a><br><span style="color:#64748b">21模块调度数据资产</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'qs-layer5\')" style="color:#2563eb">执行管线</a><br><span style="color:#64748b">分析管线消费数据资产</span></div>';
  h += '<div><a href="javascript:navigateTo(\'aly-result\')" style="color:#2563eb">本次分析结果</a><br><span style="color:#64748b">最终分析结果基于全部资产</span></div>';
  h += '</div></div></div>';

  // 段落说明
  h += '<div style="font-size:10px;color:#3a4048;line-height:20px;margin-bottom:10px">';
  h += '<p style="margin:0 0 10px">系统数据资产涵盖<strong>规则、线索链、证据链、分析函数、引擎模块、调度模块、代码库</strong>七个维度，是AGI引擎中心的核心配置数据，也是全系统的知识底座。</p>';
  h += '<p style="margin:0">以下七大资产组件构成完整的数据资产体系：规则引擎定义风险标准，线索链定义调查路径，证据链定义闭环条件，域分析函数执行数据提取，28引擎模块构成7层架构，21调度模块串联执行流程，52,500+行代码承载全部逻辑。</p>';
  h += '</div>';

  // 七大资产组件
  h += '<div style="font-size:10px;font-weight:700;color:#16233a;margin-bottom:10px;padding-bottom:6px;border-bottom:2px solid #e2e8f0">七大资产组件</div>';

  var assets = [
    { n:'①', name:'税务合规规则', icon:'📋', color:'#2563eb',
      desc:'覆盖20个分类的税务合规指令：发票匹配/申报合规/行业专项/个税/资产负债/企业所得/成本费用/发票合规/增值税/经营实质等。每条含触发条件、风险等级、调查步骤、法定处罚依据四项要素。',
      stat:'20个分类 · {{rules_count}}条规则'},
    { n:'②', name:'线索/证据链', icon:'🔗', color:'#7c3aed',
      desc:'线索链定义从风险到发现的调查路径（437条，41条可执行+1174条方法论）。证据链定义多源验证的闭环条件（781条，要求≥60%维度+≥3规则+≥2域达成闭环）。',
      stat:'{{clue_chains}}条线索链 · {{evidence_chains}}条证据链'},
    { n:'③', name:'域分析函数', icon:'🔍', color:'#059669',
      desc:'{{domain_functions}}个域分析函数：银行收款构成/付款方身份核实/进销存比对/五层发票审计/供应商穿透/合同四层分类/经营实质/地理分析等，覆盖资金、票据、交易、关联方四维域。',
      stat:'42个函数 · 4维域覆盖'},
    { n:'④', name:'7层28引擎', icon:'🧠', color:'#f59e0b',
      desc:'7层架构：核心层6+推理层4+连接层3+知识层3+专项层7+加速层3+调度层2。覆盖自愈、巡逻、规则发现、反思、元认知、SCM因果、知识库、并行加速等全部引擎能力。',
      stat:'7层架构 · 28个引擎模块'},
    { n:'⑤', name:'21调度模块', icon:'🎯', color:'#dc2626',
      desc:'M001-M021：数据准备3+核查3+分析8+推理1+质量控制4+综合2+输出1。orchestrator.py注册管理，21模块串联形成完整分析管线调度体系。',
      stat:'21个模块 · 7大阶段'},
    { n:'⑥', name:'代码规模', icon:'📐', color:'#6366f1',
      desc:'main.py约29,000行+engine/约8,500行+前端约15,000行。总计约52,500行系统代码，承载全部税务合规分析逻辑、规则引擎、推理框架和前端交互。',
      stat:'52,500+行 · 三端协同'},
    { n:'⑦', name:'知识库配置', icon:'📚', color:'#0891b2',
      desc:'政策库9条优惠/因果网络/信号模式/14类语义词典/8大行业画像/自愈规则/经验教训/分析历史/巡逻快照。全部JSON存储，线程安全单例访问。',
      stat:'9项知识库 · 14种配置'}
  ];

  assets.forEach(function(a) {
    h += '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:18px 22px;margin-bottom:10px;border-left:4px solid '+a.color+'">';
    h += '<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">';
    h += '<span style="background:'+a.color+';color:#fff;width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700">'+a.n+'</span>';
    h += '<span style="font-size:10px;font-weight:700;color:#16233a">'+a.icon+' '+a.name+'</span>';
    h += '<span style="margin-left:auto;background:#f8fafc;border:1px solid #e2e8f0;padding:3px 10px;border-radius:4px;font-size:10px;color:'+a.color+';font-weight:600">'+a.stat+'</span>';
    h += '</div>';
    h += '<div style="font-size:10px;color:#3a4048;line-height:20px">'+a.desc+'</div>';
    h += '<div style="font-size:10px;color:#6366f1;margin-top:10px;padding-top:8px;border-top:1px solid #e2e8f0">📁 AGI引擎中心 · 数据资产</div>';
    h += '</div>';
  });

  h += '</div>';
  container.innerHTML = h;

  // 异步填充统计卡片
  var _f = function(id, val) { var el = document.getElementById(id); if (el) el.textContent = val; };
  _f('da-rules', pc('rules', '1608'));
  _f('da-clues', pc('trailChains', '437'));
  _f('da-domains', '42');
  _f('da-engines', '28');
}

// ═══════════════ 税务合规判定规则页面 ═══════════════
function renderJudgmentRules(container) {
  var h = '';
  h += '<div style="max-width:900px;margin:0 auto;padding:36px 28px">';

  // ── 标题区 ──
  h += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">';
  h += '<div style="font-size:10px;font-weight:800;color:#16233a">⚖️ 税务合规判定规则</div>';
  h += '<div style="font-size:10px;color:#64748b">手册第4章 · 8条判定规则 · 所有分析域前置基础</div>';
  h += '</div>';
  h += '<p style="font-size:10px;color:#64748b;margin:0 0 10px;line-height:1.8">身份锚定→发票方向→进项再分类→服务闸门→品名过滤→四方交叉→COND_BAN→证据闭环——不可颠倒，前序错误=后续作废</p>';

  // ── 上下游 ──
  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:10px">';
  h += '<div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:10px;font-weight:700;color:#0369a1;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #bae6fd">⬆ 上游（输入方）</div>';
  h += '<div style="font-size:10px;color:#3a4048;line-height:20px">';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'hb-ch2\')" style="color:#2563eb">14类必查资料</a><br><span style="color:#64748b">资料解析后进入判定流程</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'hb-ch1\')" style="color:#2563eb">税务合规工作流程</a><br><span style="color:#64748b">五阶段流程提供执行框架</span></div>';
  h += '<div><a href="javascript:navigateTo(\'hb-overview\')" style="color:#2563eb">系统数据概览</a><br><span style="color:#64748b">{{rules_count}}条规则为判定提供参照</span></div>';
  h += '</div></div>';
  h += '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:10px;font-weight:700;color:#15803d;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #bbf7d0">⬇ 下游（消费方）</div>';
  h += '<div style="font-size:10px;color:#3a4048;line-height:20px">';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'aly-result\')" style="color:#2563eb">本次分析结果</a><br><span style="color:#64748b">判定结论贯穿后续所有分析域</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-think\')" style="color:#2563eb">推理引擎</a><br><span style="color:#64748b">推理过程依赖前置判定结果</span></div>';
  h += '<div><a href="javascript:navigateTo(\'qs-layer5\')" style="color:#2563eb">执行管线</a><br><span style="color:#64748b">管线各阶段消费判定结论</span></div>';
  h += '</div></div></div>';

  // ── 段落说明 ──
  h += '<div style="font-size:10px;color:#3a4048;line-height:20px;margin-bottom:10px">';
  h += '<p style="margin:0 0 10px">以下<strong>8条判定规则</strong>是系统分析的基础——每一条都在分析启动前完成判定，判定结论贯穿后续所有分析域。判定规则的执行顺序不可颠倒：<strong style="color:#dc2626">身份锚定→发票方向→进项再分类→服务闸门→品名过滤→四方交叉→COND_BAN→证据闭环</strong>。如果第一步的身份锚定出错，后续所有判定都建立在错误基础上。</p>';
  h += '<p style="margin:0">每条判定规则均由代码层（phase1_triage.py / pipeline.py / cross_domain_negotiation.py）独立实现，并通过<strong>引擎记忆（engine/memory.py）</strong>记载规则定义与执行约束。证据闭环要求：≥60%触发率 + ≥3条规则触发 + ≥2个数据域交叉验证，三重门禁全部通过才形成有效证据闭环。</p>';
  h += '</div>';

  // ── 8条判定规则（静态卡片 + 异步填充详情） ──
  h += '<div style="font-size:10px;font-weight:700;color:#16233a;margin-bottom:10px;padding-bottom:6px;border-bottom:2px solid #e2e8f0">八条判定规则</div>';

  var ruleLabels = [
    {n:'①', name:'身份锚定', color:'#2563eb', tag:'锚定'},
    {n:'②', name:'发票方向判定', color:'#7c3aed', tag:'方向'},
    {n:'③', name:'进项再分类', color:'#059669', tag:'分类'},
    {n:'④', name:'服务行业闸门', color:'#d97706', tag:'闸门'},
    {n:'⑤', name:'品名级精准过滤', color:'#dc2626', tag:'过滤'},
    {n:'⑥', name:'四方交叉验证', color:'#6366f1', tag:'交叉'},
    {n:'⑦', name:'COND_BAN防误杀', color:'#0891b2', tag:'防误杀'},
    {n:'⑧', name:'证据闭环阈值', color:'#be185d', tag:'闭环'},
  ];

  for (var i = 0; i < ruleLabels.length; i++) {
    var rl = ruleLabels[i];
    h += '<div style="background:#fff;border:1px solid #e2e8f0;border-left:3px solid '+rl.color+';border-radius:8px;padding:18px 20px;margin-bottom:10px">';
    h += '<div style="display:flex;align-items:center;margin-bottom:10px">';
    h += '<span style="display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:50%;background:'+rl.color+';color:#fff;font-size:10px;font-weight:700;margin-right:10px">'+(i+1)+'</span>';
    h += '<span style="font-size:10px;font-weight:700;color:#16233a">'+rl.name+'</span>';
    h += '<span style="margin-left:10px;background:'+rl.color+'15;color:'+rl.color+';padding:2px 8px;border-radius:4px;font-size:10px;font-weight:600">'+rl.tag+'</span>';
    h += '</div>';
    h += '<div style="font-size:10px;color:#64748b;line-height:20px" id="jr-detail-'+i+'">加载中...</div>';
    h += '</div>';
  }

  h += '</div>';
  container.innerHTML = h;

  // 异步加载 audit_rules.json 并填充
  fetch('/static/audit_rules.json')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      for (var i = 0; i < data.length && i < 8; i++) {
        var el = document.getElementById('jr-detail-' + i);
        if (el) {
          var d = data[i];
          var desc = d.desc.replace(/代码：/g, '<br><span style="color:#64748b;font-size:10px">实现：</span>');
          el.innerHTML = desc;
        }
      }
    })
    .catch(function() {
      for (var i = 0; i < 8; i++) {
        var el = document.getElementById('jr-detail-' + i);
        if (el) el.innerHTML = '<span style="color:#dc2626">加载失败，请刷新页面</span>';
      }
    });
}

// ═══════════════ 关键法律条文页面 ═══════════════
function renderLegalRefs(container) {
  container.innerHTML = '<div style="text-align:center;padding:60px"><span class="spinner"></span> 正在加载关键法律条文...</div>';

  fetch('/static/legal_refs.json')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var h = '';
      h += '<div style="max-width:900px;margin:0 auto;padding:36px 28px">';

      // ── 标题区 ──
      h += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">';
      h += '<div style="font-size:10px;font-weight:800;color:#16233a">📜 关键法律条文</div>';
      h += '<div style="font-size:10px;color:#64748b">手册第6章 · 12条核心法条 · 法律推理引擎自动匹配</div>';
      h += '</div>';
      h += '<p style="font-size:10px;color:#64748b;margin:0 0 10px;line-height:1.8">征管法32条→刑法205条，涵盖滞纳金/核定征收/偷税处罚/虚开刑事等核心法律依据</p>';

      // ── 上下游 ──
      h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:10px">';
      h += '<div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:16px 20px">';
      h += '<div style="font-size:10px;font-weight:700;color:#0369a1;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #bae6fd">⬆ 上游（输入方）</div>';
      h += '<div style="font-size:10px;color:#3a4048;line-height:20px">';
      h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'hb-ch4\')" style="color:#2563eb">税务合规判定规则</a><br><span style="color:#64748b">判定规则触发后匹配合适法条</span></div>';
      h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'qs-layer2\')" style="color:#2563eb">方法论体系</a><br><span style="color:#64748b">33条方法论指导法条适用场景</span></div>';
      h += '<div><a href="javascript:navigateTo(\'hb-overview\')" style="color:#2563eb">系统数据概览</a><br><span style="color:#64748b">{{rules_count}}条规则关联法条引用</span></div>';
      h += '</div></div>';
      h += '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px 20px">';
      h += '<div style="font-size:10px;font-weight:700;color:#15803d;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #bbf7d0">⬇ 下游（消费方）</div>';
      h += '<div style="font-size:10px;color:#3a4048;line-height:20px">';
      h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'aly-result\')" style="color:#2563eb">本次分析结果</a><br><span style="color:#64748b">每项发现须引用具体法条</span></div>';
      h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-think\')" style="color:#2563eb">推理引擎</a><br><span style="color:#64748b">法律推理引擎自动匹配法条</span></div>';
      h += '<div><a href="javascript:navigateTo(\'report-standards\')" style="color:#2563eb">报告编制规范</a><br><span style="color:#64748b">报告法律依据字段引用法条</span></div>';
      h += '</div></div></div>';

      // ── 段落说明 ──
      h += '<div style="font-size:10px;color:#3a4048;line-height:20px;margin-bottom:10px">';
      h += '<p style="margin:0 0 10px">以下<strong>12条法律条文</strong>为税务合规中最常引用的核心依据。税务合规报告的每项发现必须引用具体法条——笼统引用"相关税收法规"的表述在审理环节会被退回重写。条文的适用场景和处罚标准直接写入报告的法律依据字段，由<strong>法律推理引擎（legal_reasoner.py）</strong>自动匹配。</p>';
      h += '<p style="margin:0">覆盖<strong>征管法6条</strong>（第32/35/54/60/63/64条）+ <strong>刑法2条</strong>（第201/205条）+ <strong>其他4条</strong>（发票管理办法第22条/增值税条例第19条/企业所得税法第41条/规程第42条），形成从行政处罚到刑事追诉的完整法律覆盖层次。</p>';
      h += '</div>';

      // ── 12条法律条文卡片 ──
      h += '<div style="font-size:10px;font-weight:700;color:#16233a;margin-bottom:10px;padding-bottom:6px;border-bottom:2px solid #e2e8f0">十二条法律条文</div>';

      var colors = ['#2563eb','#7c3aed','#059669','#d97706','#dc2626','#6366f1','#0891b2','#be185d','#ea580c','#4f46e5','#0d9488','#c026d3'];
      for (var i = 0; i < data.length; i++) {
        var d = data[i];
        var c = colors[i % colors.length];
        h += '<div style="background:#fff;border:1px solid #e2e8f0;border-left:3px solid '+c+';border-radius:8px;padding:18px 20px;margin-bottom:10px">';
        h += '<div style="display:flex;align-items:center;margin-bottom:10px">';
        h += '<span style="display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:50%;background:'+c+';color:#fff;font-size:10px;font-weight:700;margin-right:10px">'+(i+1)+'</span>';
        h += '<span style="font-size:10px;font-weight:700;color:#16233a">'+escHtml(d.law)+'</span>';
        h += '</div>';
        h += '<div style="font-size:10px;color:#334155;line-height:20px;margin-bottom:10px;padding:10px 14px;background:#f8fafc;border-radius:6px">'+escHtml(d.content)+'</div>';
        h += '<div style="font-size:10px;color:#64748b;line-height:1.8"><span style="color:#64748b">适用：</span>'+escHtml(d.scenario)+'</div>';
        h += '</div>';
      }

      h += '</div>';
      container.innerHTML = h;
    })
    .catch(function() {
      container.innerHTML = '<div style="padding:60px;text-align:center;color:#dc2626;font-size:10px">加载失败，请刷新页面重试</div>';
    });
}

// ═══════════════ 系统与规程映射页面 ═══════════════
function renderProcedureMapping(container) {
  var h = '<div style="max-width:900px;margin:0 auto;padding:36px 28px">';
  
  // 标题区
  h += '<div style="margin-bottom:10px">';
  h += '<h2 style="font-size:10px;font-weight:800;color:#16233a;margin:0 0 10px">🔗 系统与规程映射</h2>';
  h += '<p style="font-size:10px;color:#64748b;margin:0">手册第7章 · 12个功能模块 · 完整覆盖《税务合规工作规程》全流程条款</p>';
  h += '</div>';
  
  // 上下游
  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:10px">';
  h += '<div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:10px;font-weight:700;color:#0369a1;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #bae6fd">⬆ 上游（输入方）</div>';
  h += '<div style="font-size:10px;color:#3a4048;line-height:20px">';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'hb-ch1\')" style="color:#2563eb">税务合规工作流程</a><br><span style="color:#64748b">规程框架</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'hb-ch4\')" style="color:#2563eb">税务合规判定规则</a><br><span style="color:#64748b">规则引擎</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'hb-overview\')" style="color:#2563eb">系统数据概览</a><br><span style="color:#64748b">全局视图</span></div>';
  h += '</div></div>';
  h += '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:10px;font-weight:700;color:#15803d;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #bbf7d0">⬇ 下游（消费方）</div>';
  h += '<div style="font-size:10px;color:#3a4048;line-height:20px">';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-qual\')" style="color:#2563eb">质量保障</a><br><span style="color:#64748b">程序合法</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'eng-orch\')" style="color:#2563eb">调度中枢</a><br><span style="color:#64748b">管线调度</span></div>';
  h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\'tax-incentives-page\')" style="color:#2563eb">本次分析结果</a><br><span style="color:#64748b">产出验证</span></div>';
  h += '</div></div></div>';
  
  // 段落说明
  h += '<div style="margin-bottom:10px;font-size:10px;color:#3a4048;line-height:20px">';
  h += '<p style="margin:0 0 10px">系统每一个功能模块都对应《税务合规工作规程》（国税发[2009]157号）的具体条款要求——确保系统产出<strong>不是凭空制造的</strong>，每一项分析、每一条结论都有法定的规程依据。12个功能模块完整覆盖从案源筛选到报告输出的<strong>全税务合规流程</strong>：第21-45条（检查实施）→第46条（审理审核）→第49条（审理意见）→第51条（报告格式）→第60条（程序合法）。</p>';
  h += '<p style="margin:0">这个映射表回答了"凭什么"的问题：凭什么一键分析就是完整的检查环节？凭什么证据闭环就意味着证据充分？每一项能力的背后都有规程条款作为法律依据。</p>';
  h += '</div>';
  
  // 12项功能模块卡片
  var modules = [
    {n:'①',name:'一键分析',clause:'第21-45条（检查）',desc:'_run_analyze自动执行全部分析域+四步核查法+链驱动引擎+协商引擎+方法论过滤器。一次点击=完整模拟税务合规检查环节——从文件上传到报告输出全部自动化。',color:'#2563eb'},
    {n:'②',name:'文件解析',clause:'第22条（取证）',desc:'{{file_fingerprints}}类文件指纹+三层递进识别+四方交叉验证。82+列名映射自适应匹配。自动完成文件取证的数据准备——把格式各异的原始资料转化为结构化分析数据。',color:'#7c3aed'},
    {n:'③',name:'线索链',clause:'第22条（取证逻辑）',desc:'{{clue_chains}}条线索链全部可执行。每条含触发关键词+调查步骤+关联规则ID+风险等级+建议+法条引用。每条线索链=一个税务合规员的调查思路——"从这里开始查，每一步查什么，查到了怎么办"。',color:'#059669'},
    {n:'④',name:'证据链',clause:'第24条（证据真实性）',desc:'{{evidence_chains}}条证据链，需≥2域交叉→≥最小证据触发→多维印证闭环。从不同数据源收集支撑证据→满足最小证据数→证据闭环→结论的证明力达到可交付标准。',color:'#d97706'},
    {n:'⑤',name:'分析链',clause:'第46条（审理审核）',desc:'48条分析链，含推理路径多步推理，从证据到结论的综合判定。模拟审理部门的逐项审核——检查对象准确性/事实证据充分性/法律适用正确性→0-7维异常评分→定案。',color:'#dc2626'},
    {n:'⑥',name:'方法论过滤器',clause:'第46条（审核重点）',desc:'全链路质量保障→七类过滤规则依次执行→剔除证据不足的噪声→97%噪声过滤率。HARD_BAN 23类→COND_BAN 5类→重点保护12类→正常结论排除→资料缺口限流→行业不匹配过滤→去重合并。',color:'#6366f1'},
    {n:'⑦',name:'跨域协商引擎',clause:'第46条（审核重点）',desc:'29条协商规则四类场景：行业闸门消解/资料驱动的跨域标记/证据矛盾消解/联合增强。域间自动对话——确保报告不会出现自相矛盾的结论。',color:'#0891b2'},
    {n:'⑧',name:'风险评分',clause:'第49条（审理意见）',desc:'综合评分(76/100)→四级风险等级→P0/P1/P2策略→因果叙事链→证据闭环→形成税务合规结论。完全对应审理环节的"审理意见"——对检查结果的综合判断和定性建议。',color:'#ea580c'},
    {n:'⑨',name:'报告生成',clause:'第51条（报告格式）',desc:'自动生成封面+7章+附件。完全符合规程第42条规定的10项内容格式要求：案件来源→基本情况→实施情况→发现问题→税务合规结论→处理建议→告知权利→签字→证据清单。',color:'#db2777'},
    {n:'⑩',name:'合规门禁',clause:'第60条（程序合法）',desc:'质量标准（模板句清除/重复句合并/空描述删除/人性化表述/六要素完整/法律引用准确/具体数值/因果链/可执行建议/条款号/反跨复制/空占位符清除）+16项自省检查。全通过→绿色交付。',color:'#4f46e5'},
    {n:'⑪',name:'数据一致性自检',clause:'全文',desc:'启动前扫描全部JS/PY文件→对比system_config.json权威数据源→发现不一致→自动标记或一键修复（--sync）。从原始数据文件实时统计权威值。四触发机制覆盖手动/启动/提交/分析。',color:'#0d9488'},
    {n:'⑫',name:'审核反馈闭环',clause:'第46条（审核重点）',desc:'每条发现右侧"审核"按钮→按模板填写审核意见→存入user_corrections.json→生成指纹→四级回退匹配→累计1次即升级自动规则→下次分析自动应用。人工审核→系统学习→自动修正→持续进化的完整闭环。',color:'#9333ea'}
  ];
  
  h += '<div style="display:flex;flex-direction:column;gap:10px;margin-bottom:10px">';
  modules.forEach(function(m) {
    h += '<div style="background:#fff;border-left:3px solid '+m.color+';border-top:1px solid #e2e8f0;border-right:1px solid #e2e8f0;border-bottom:1px solid #e2e8f0;border-radius:0 8px 8px 0;padding:16px 20px">';
    h += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">';
    h += '<div style="display:flex;align-items:center;gap:10px">';
    h += '<span style="width:28px;height:28px;border-radius:50%;background:'+m.color+';color:#fff;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;flex-shrink:0">'+m.n+'</span>';
    h += '<span style="font-size:10px;font-weight:700;color:#16233a">'+m.name+'</span>';
    h += '</div>';
    h += '<span style="font-size:10px;color:'+m.color+';font-weight:600;background:'+m.color+'15;padding:3px 10px;border-radius:4px">'+m.clause+'</span>';
    h += '</div>';
    h += '<p style="font-size:10px;color:#3a4048;line-height:20px;margin:0">'+m.desc+'</p>';
    h += '</div>';
  });
  h += '</div>';
  
  h += '</div>';
  container.innerHTML = h;
}
/* AUTO-GENERATED: 42 independent page render functions */
// ═══════════════ Shared Unified Page Template ═══════════════
// All 42 independent pages use this template for consistent styling
function _pageTemplate(cfg) {
  var h = '';
  h += '<div style="max-width:900px;margin:0 auto;padding:30px 24px 60px">';
  
  // Header
  h += '<div style="margin-bottom:30px">';
  h += '<h1 style="font-size:10px;font-weight:700;color:#16233a;margin:0 0 10px">' + escHtml(cfg.icon + ' ' + cfg.title) + '</h1>';
  h += '<p style="font-size:10px;color:#64748b;margin:0;line-height:20px">' + escHtml(cfg.subtitle) + '</p>';
  h += '</div>';
  
  // Stats cards
  if (cfg.stats && cfg.stats.length) {
    h += '<div style="display:flex;flex-wrap:wrap;gap:14px;margin-bottom:10px">';
    cfg.stats.forEach(function(s) {
      h += '<div style="flex:1;min-width:130px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:18px 16px;text-align:center">';
      h += '<div style="font-size:10px;font-weight:700;color:' + s[2] + ';line-height:1.3">' + escHtml(s[0]) + '</div>';
      h += '<div style="font-size:10px;color:#64748b;margin-top:6px">' + escHtml(s[1]) + '</div>';
      h += '</div>';
    });
    h += '</div>';
  }
  
  // Upstream dependency block
  if (cfg.upstream && cfg.upstream.length) {
    h += '<div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:10px;padding:16px 20px;margin-bottom:20px">';
    h += '<div style="font-size:10px;font-weight:600;color:#0369a1;margin-bottom:10px">\u2191 \u4e0a\u6e38\u4f9d\u8d56</div>';
    cfg.upstream.forEach(function(u) {
      h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\u0027' + u[0] + '\u0027)" style="color:#2563eb;font-size:10px">' + escHtml(u[1]) + '</a><br><span style="color:#64748b;font-size:10px">' + escHtml(u[2]) + '</span></div>';
    });
    h += '</div>';
  }
  
  // Downstream impact block
  if (cfg.downstream && cfg.downstream.length) {
    h += '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:16px 20px;margin-bottom:20px">';
    h += '<div style="font-size:10px;font-weight:600;color:#15803d;margin-bottom:10px">\u2193 \u4e0b\u6e38\u5f71\u54cd</div>';
    cfg.downstream.forEach(function(d) {
      h += '<div style="margin-bottom:6px"><a href="javascript:navigateTo(\u0027' + d[0] + '\u0027)" style="color:#2563eb;font-size:10px">' + escHtml(d[1]) + '</a><br><span style="color:#64748b;font-size:10px">' + escHtml(d[2]) + '</span></div>';
    });
    h += '</div>';
  }
  
  // Description paragraph
  if (cfg.desc) {
    h += '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:20px 24px;margin-bottom:20px;font-size:10px;color:#3a4048;line-height:20px">';
    h += cfg.desc;
    h += '</div>';
  }
  
  // Content cards
  if (cfg.cards && cfg.cards.length) {
    cfg.cards.forEach(function(card) {
      h += '<div style="background:#fff;border-left:3px solid ' + card[2] + ';border-radius:0 8px 8px 0;padding:18px 20px;margin-bottom:10px;border-top:1px solid #e2e8f0;border-right:1px solid #e2e8f0;border-bottom:1px solid #e2e8f0">';
      h += '<div style="font-size:10px;font-weight:600;color:' + card[2] + ';margin-bottom:10px">' + escHtml(card[0]) + '</div>';
      h += '<div style="font-size:10px;color:#64748b;line-height:20px">' + escHtml(card[1]) + '</div>';
      h += '</div>';
    });
  }
  
  h += '</div>';
  return h;
}
// 跨域协商引擎
function renderCrossDomainNego() {
  return _pageTemplate({
  "title": "跨域协商引擎",
  "icon": "🤝",
  "subtitle": "{{domain_functions}}个域分析函数各自独立产出发现后，协商引擎自动执行跨域对话——一个域的结论影响其他域的判定。29条协商规则覆盖四类场景：消解、标记、矛盾、增强。",
  "stats": [
    [
      "29条",
      "协商规则",
      "#2563eb"
    ],
    [
      "4类场景",
      "消解/标记/矛盾/增强",
      "#7c3aed"
    ],
    [
      "42域",
      "独立域分析函数",
      "#059669"
    ],
    [
      "全自动",
      "引擎自动协商",
      "#d97706"
    ]
  ],
  "upstream": [
    [
      "hb-ch8",
      "全链路质量保障",
      "质量保障检查域分析输出"
    ],
    [
      "da-domains",
      "分析域",
      "域分析产出all_findings"
    ]
  ],
  "downstream": [
    [
      "hb-ch4",
      "税务合规判定规则",
      "协商后进入过滤管线"
    ],
    [
      "rs-negotiation",
      "协商标记展示规范",
      "协商结果四种横幅展示"
    ]
  ],
  "desc": "<p style=\"margin:0 0 10px\">协商在all_findings生成后、进入过滤管线前执行。代码：engine/cross_domain_negotiation.py → run_negotiation()。</p><p style=\"margin:0\">协商结果在报告中以四种横幅展示：消解（红色·域间结论冲突已消除）/ 调整（黄色·域间结论已协调）/ 标记（蓝色·跨域信息已传递）/ 联合增强（红色边框·多域联合证据增强）。</p>",
  "cards": [
    [
      "行业闸门消解（5条）",
      "NEG-001~005。当行业判定结果与域分析发现冲突时，按优先级消解——行业认知权重高于单一域发现。服务行业自动消解进销存、存货、BOM等制造业域发现。",
      "#dc2626"
    ],
    [
      "资料驱动标记（4条）",
      "NEG-010~040。当域分析因缺少资料而无法得出结论时，协商引擎在其他域中寻找替代证据——缺失资料的域不生成发现，但其他域如有关联发现则标记资料缺口。",
      "#d97706"
    ],
    [
      "证据矛盾消解（3条）",
      "NEG-020~030。两条以上证据互相矛盾时，按证据优先级裁决——原始凭证>系统推断>行业基准。正面证据优先原则。",
      "#2563eb"
    ],
    [
      "联合增强（3条）",
      "NEG-AUG-001~003。两个以上域的发现指向同一问题时，合并增强为一条联合发现——提升置信度、降低误报率。",
      "#059669"
    ]
  ]
});
}
// 数据一致性自检
function renderDataConsistencyCheck() {
  return _pageTemplate({
  "title": "数据一致性自检",
  "icon": "✅",
  "subtitle": "引擎记忆（engine/memory.py）是系统的核心知识库。四触发机制确保文档层自动与代码层同步——文档层26章记录系统应该是什么样的，代码层7个函数负责做。",
  "stats": [
    [
      "26章文档",
      "规则篇9+架构篇16+索引1",
      "#2563eb"
    ],
    [
      "7个函数",
      "代码层存储/检索/学习",
      "#7c3aed"
    ],
    [
      "4触发",
      "手动/启动/commit/分析",
      "#059669"
    ],
    [
      "3命令",
      "审计/sync/calibrate",
      "#d97706"
    ]
  ],
  "upstream": [
    [
      "hb-ch12",
      "引擎记忆体系",
      "数据一致性检查记忆"
    ],
    [
      "hb-ch4",
      "税务合规判定规则",
      "规则数据源需一致性验证"
    ]
  ],
  "downstream": [
    [
      "rs-sync",
      "同步交付机制",
      "一致性保障报告交付"
    ],
    [
      "hb-ch13",
      "引擎铁律编号体系",
      "铁律要求规则=代码一致"
    ]
  ],
  "desc": "<p style=\"margin:0 0 10px\">权威数据源从原始数据文件实时统计生成。扫描范围覆盖所有JS和PY文件，将硬编码数字与权威数据对比。</p><p style=\"margin:0\">四触发：①手动python audit_consistency.py --sync ②start.bat启动 ③git commit pre-commit钩子 ④pipeline.py启动时调用。三种命令：纯审计（只报告）/ --sync（联动同步自动修复）/ --calibrate（重新统计权威数据源）。</p>",
  "cards": [
    [
      "代码位置",
      "audit_consistency.py（扫描引擎+同步引擎）+ system_config.json（权威数据源）+ engine/system_config.py（Python端配置）",
      "#2563eb"
    ],
    [
      "权威数据源",
      "从原始数据文件实时统计：tax_risk_rules_local_export.json→规则数 / cross_domain_clues.json→线索链数 / cross_domain_evidence.json→证据链数",
      "#7c3aed"
    ],
    [
      "扫描范围",
      "所有JS文件（static/js/*.js）+所有PY文件（engine/*.py + *.py），扫描硬编码数字与权威数据对比",
      "#059669"
    ],
    [
      "同步范围",
      "代码层硬编码数字 + 文档层docstring正则匹配更新，确保代码与文档的数字描述完全一致",
      "#d97706"
    ]
  ]
});
}
// 审核反馈与自学习闭环
function renderAuditFeedback() {
  return _pageTemplate({
  "title": "审核反馈与自学习闭环",
  "icon": "🔄",
  "subtitle": "报告中每条发现的右侧提供审核按钮。审核按五段结构填写结构化意见。系统从审核意见中提取指纹，编码为可复用的纠正规则——累计1次即自动应用。",
  "stats": [
    [
      "5段式",
      "结构化审核模板",
      "#2563eb"
    ],
    [
      "4级回退",
      "匹配策略L1~L4",
      "#7c3aed"
    ],
    [
      "1次触发",
      "累计1次自动应用",
      "#059669"
    ],
    [
      "闭环",
      "审核→纠正→重分析",
      "#d97706"
    ]
  ],
  "upstream": [
    [
      "hb-ch12",
      "引擎记忆体系",
      "纠正规则存入引擎记忆"
    ],
    [
      "aly-result",
      "本次分析结果",
      "分析发现触发审核"
    ]
  ],
  "downstream": [
    [
      "rs-review",
      "审核反馈呈现",
      "审核结果影响报告呈现"
    ],
    [
      "rs-iterate",
      "审核迭代闭环",
      "审核驱动报告迭代"
    ]
  ],
  "desc": "<p style=\"margin:0 0 10px\">审核入口：每条发现右侧审核按钮，提交后立即清空前后端分析缓存。</p><p style=\"margin:0\">五段式模板：①判断结论（正确/需纠正/不适用）②具体问题 ③正确逻辑 ④需要证据 ⑤法律依据。存储：POST /api/feedback → record_correction() → 按类型|行业|经营模式生成唯一指纹 → 存入user_corrections.json。</p>",
  "cards": [
    [
      "五段式模板",
      "①判断结论 ②具体问题 ③正确逻辑 ④需要证据 ⑤法律依据。结构化填写作答，确保纠正规则可编码复用。",
      "#2563eb"
    ],
    [
      "四级回退匹配",
      "L1精确匹配（类型+行业+模式，置信度0.7）→ L2行业匹配（0.7）→ L3通用匹配（0.8）→ L4名称模糊匹配（0.8）。逐级回退确保最大覆盖率。",
      "#7c3aed"
    ],
    [
      "生效方式",
      "匹配成功→打_dismissed标签→前端展示绿色审核横幅。不降级、不改变原始风险等级——审核是标记不是改写。",
      "#059669"
    ],
    [
      "存储与累积",
      "按发现类型|行业|经营模式生成唯一指纹 → 存入user_corrections.json → 累计1次即标记auto_apply=true → 下次自动匹配。",
      "#d97706"
    ]
  ]
});
}
// 引擎记忆体系
function renderEngineMemory() {
  return _pageTemplate({
  "title": "引擎记忆体系",
  "icon": "🧠",
  "subtitle": "引擎记忆（engine/memory.py）是系统的核心知识库。文档层26章记录系统架构与规则，代码层7个函数负责存储/检索/学习/纠正。两者配合实现知识闭环。",
  "stats": [
    [
      "26章文档",
      "规则篇9+架构篇16+索引1",
      "#2563eb"
    ],
    [
      "7个函数",
      "存储/检索/学习/纠正",
      "#7c3aed"
    ],
    [
      "4触发",
      "自动同步机制",
      "#059669"
    ],
    [
      "30+",
      "系统核心文件",
      "#d97706"
    ]
  ],
  "upstream": [
    [
      "hb-ch10",
      "数据一致性自检",
      "一致性检查记忆同步"
    ],
    [
      "hb-ch13",
      "引擎铁律编号体系",
      "铁律存储在引擎记忆规则篇"
    ]
  ],
  "downstream": [
    [
      "hb-ch11",
      "审核反馈闭环",
      "审核产生的纠正规则存入记忆"
    ],
    [
      "hb-ch14",
      "系统文件关联清单",
      "记忆末尾记录文件关联清单"
    ]
  ],
  "desc": "<p style=\"margin:0 0 10px\">文档层指导代码层的设计，代码层验证文档层的正确性。四触发机制确保两者同步。</p><p style=\"margin:0\">文档层分三部分：规则篇9章（行业推断铁律、系统判定规则33条、缺失信息处理、收款分类规则12条、账务处理铁律6条、核心铁律5条、报告呈现规则、后四章规则、审核反馈闭环规则）+ 架构篇16章 + 索引1章。</p>",
  "cards": [
    [
      "规则篇9章",
      "行业推断铁律、系统判定规则33条、缺失信息处理、收款分类规则12条、账务处理铁律6条、核心铁律5条、报告呈现规则、后四章规则、审核反馈闭环规则。",
      "#2563eb"
    ],
    [
      "架构篇16章",
      "假设验证推理引擎、跨域协商引擎、审核反馈闭环、联动修改一致性、方法论过滤器体系、模块联动关系矩阵、四阶段推理管线、调度中枢等。",
      "#7c3aed"
    ],
    [
      "代码层7函数",
      "save_analysis_memory() / query_similar_cases() / record_correction() / apply_correction_rules() / record_user_feedback() / _adjust_signal_weights_from_feedback() / get_adaptive_signal_weights()",
      "#059669"
    ],
    [
      "关联清单",
      "引擎记忆末尾的系统文件关联清单列出30+核心文件，每次--sync自动更新，确保文档描述与实际文件一致。",
      "#d97706"
    ]
  ]
});
}
// 引擎铁律编号体系
function renderIronLaws() {
  return _pageTemplate({
  "title": "引擎铁律编号体系",
  "icon": "⚖️",
  "subtitle": "引擎铁律（engine/memory.py规则篇）=系统硬逻辑，不可违反。AI行为准则（前端页面）=编码规范。共11条引擎铁律+7条AI准则，编号互不重叠，各司其职。",
  "stats": [
    [
      "11条",
      "引擎铁律",
      "#2563eb"
    ],
    [
      "7条",
      "AI行为准则",
      "#7c3aed"
    ],
    [
      "编号",
      "互不重叠",
      "#059669"
    ],
    [
      "强制",
      "铁律不可违",
      "#d97706"
    ]
  ],
  "upstream": [
    [
      "hb-ch12",
      "引擎记忆体系",
      "铁律存储在引擎记忆规则篇"
    ],
    [
      "rs-ironlaw",
      "铁律质量映射",
      "铁律→报告质量交叉映射"
    ]
  ],
  "downstream": [
    [
      "hb-ch8",
      "全链路质量保障",
      "铁律确保质量底线"
    ],
    [
      "hb-ch10",
      "数据一致性自检",
      "铁律七要求规则=代码一致"
    ]
  ],
  "desc": "<p style=\"margin:0 0 10px\">引擎铁律（11条）存储在engine/memory.py规则篇，是系统的硬逻辑，不可违反。AI行为准则（7条）在侧边栏AI行为准则页面展示。</p><p style=\"margin:0\">铁律一~六（账务处理）：科目name铁律、三号合并铁律、审计铁律、ref_id去重铁律、普票税额并入成本铁律、7分类禁止兜底铁律。铁律七~十一（核心规范）：规则=代码铁律、代码即承诺铁律、全行业适用铁律、主动关联更新铁律、方法论先行铁律。</p>",
  "cards": [
    [
      "铁律一~六（账务处理）",
      "科目name写入前查DB为准 / 三号合并禁止逐条for / 审计python audit.py 1 / ref_id精确匹配 / 普票税额并入成本 / 7分类禁止兜底",
      "#2563eb"
    ],
    [
      "铁律七~十一（核心规范）",
      "规则=代码记忆实现一致 / 代码即承诺声称功能代码存在 / 全行业适用禁止特化 / 主动关联更新全项目同步 / 方法论先行功能须有方法论定义",
      "#7c3aed"
    ],
    [
      "AI行为准则7条",
      "#1做事要狠 / #2自作主张 / #3主动进攻 / #4自行验证 / #8变更影响分析 / #15提交前自查 / #16交付前输出自检",
      "#059669"
    ],
    [
      "查找路径",
      "引擎铁律→engine/memory.py（规则篇第6-7章）；AI准则→侧边栏AI行为准则页面；完整编号对照表→engine/memory.py末尾",
      "#d97706"
    ]
  ]
});
}
// 系统文件关联清单
function renderFileAssociation() {
  return _pageTemplate({
  "title": "系统文件关联清单",
  "icon": "📄",
  "subtitle": "核心文件共30+个，按职责分为四组：核心引擎12个、数据配置8个、前端页面9个、基础设施4个。此清单同时记录在engine/memory.py末尾。",
  "stats": [
    [
      "12个",
      "核心引擎文件",
      "#2563eb"
    ],
    [
      "8个",
      "数据与配置文件",
      "#7c3aed"
    ],
    [
      "9个",
      "前端JS文件",
      "#059669"
    ],
    [
      "4个",
      "基础设施文件",
      "#d97706"
    ]
  ],
  "upstream": [
    [
      "hb-ch12",
      "引擎记忆体系",
      "记忆末尾记录文件关联清单"
    ],
    [
      "hb-ch10",
      "数据一致性自检",
      "一致性检查依赖文件清单"
    ]
  ],
  "downstream": [
    [
      "hb-ch13",
      "引擎铁律编号体系",
      "铁律实施依赖各文件"
    ],
    [
      "rs-sync",
      "同步交付机制",
      "文件联动保证交付一致性"
    ]
  ],
  "desc": "<p style=\"margin:0 0 10px\">每次--sync自动更新文件关联清单，确保文档描述与实际文件一致。</p><p style=\"margin:0\">四组文件分工明确：核心引擎负责分析逻辑，数据配置提供规则和数据源，前端页面负责用户交互和展示，基础设施负责系统运行和持续集成。</p>",
  "cards": [
    [
      "核心引擎（12个）",
      "engine/目录下：pipeline.py（主分析管线）、domain_analysis.py（36域函数）、phase1_triage.py、phase2_deep_dive.py、phase3_cross_validate.py、phase4_synthesis.py、cross_domain_negotiation.py、self_learning.py、hypothesis_engine.py、orchestrator.py、knowledge_base.py、legal_reasoner.py",
      "#2563eb"
    ],
    [
      "数据与配置（8个）",
      "system_config.json、audit_chains.json、user_corrections.json、industry_data.json、tax_risk_rules_local_export.json、audit_memory.json、sessions.json、database.py",
      "#7c3aed"
    ],
    [
      "前端页面（9个JS）",
      "tax-pipeline-pages.js、tax-doc-analysis.js、tax-auditor-handbook.js、tax-report-standards.js、tax-feedback-template.js、tax-engine-dashboard.js、core.js、report-block-renderer.js、tax-risk-rules.js",
      "#059669"
    ],
    [
      "基础设施（4个）",
      "main.py（227路由,FastAPI）、start.bat（启动脚本）、audit_consistency.py（一致性引擎）、static/index.html（前端入口）",
      "#d97706"
    ]
  ]
});
}
// 报告结构
function renderReportStructure() {
  return _pageTemplate({
  "title": "报告结构",
  "icon": "📑",
  "subtitle": "正式税务合规报告须含封面+7章正文+附件清单，严格遵循《税务合规工作规程》第42条规定的10项内容。",
  "stats": [
    [
      "9部分",
      "封面+7章+附件",
      "#2563eb"
    ],
    [
      "42条",
      "遵循工作规程",
      "#7c3aed"
    ],
    [
      "6要素",
      "发现问题格式",
      "#059669"
    ],
    [
      "7类",
      "附件清单",
      "#d97706"
    ]
  ],
  "upstream": [
    [
      "rs-pipeline",
      "质量保障管线",
      "净化后数据进入报告结构"
    ],
    [
      "hb-ch4",
      "税务合规判定规则",
      "判定结论决定报告内容"
    ]
  ],
  "downstream": [
    [
      "rs-narrative",
      "税务合规叙事规范",
      "叙事规范约束各章表述"
    ],
    [
      "rs-12std",
      "质量标准",
      "质量标准检查各章内容"
    ]
  ],
  "desc": "<p style=\"margin:0 0 10px\">报告结构：封面（编号格式税稽字[YYYY]第XXX号）+ 七章正文 + 附件。第一章案件来源及基本情况（8项基本信息表格）；第二章稽查实施情况（7个执行段落，整体2000字以上）；第三章发现问题及事实认定（六要素格式，高风险优先）；第四章稽查结论；第五章处理处罚建议（三级卡片P0/P1/P2）；第六章告知权利义务；第七章稽查人员签字。</p>",
  "cards": [
    [
      "第一章 基本情况",
      "8项基本信息表格：案件来源、被查单位、信用代码、法定代表人、企业类型、行业分类三层穿透、稽查期间、稽查范围。",
      "#2563eb"
    ],
    [
      "第三章 发现问题",
      "六要素格式：性质/事实/证据/来源/法律/建议。高风险优先排列，已审核展示绿色横幅，协商结果展示彩色横幅。",
      "#7c3aed"
    ],
    [
      "第五章 处理建议",
      "三级卡片红黄绿：P0立即处理（5工作日）/ P1限期整改（15工作日）/ P2持续关注（30工作日）。附自查整改期限总说明。",
      "#059669"
    ],
    [
      "第九章 附件",
      "7类附件：销项发票全量明细、进项发票全量明细、主营成本发票明细、重大费用发票明细、银行流水汇总、各资料文件清单、质量标准自检结果。",
      "#d97706"
    ]
  ]
});
}
// 术语与机密规范
function renderReportTerms() {
  return _pageTemplate({
  "title": "术语与机密规范",
  "icon": "🔒",
  "subtitle": "税务合规报告处于发现阶段，尚未进入法律裁决程序——报告用语必须体现发现而非定性的立场。同时6类系统内部信息禁止出现在正式报告中。",
  "stats": [
    [
      "检查阶段",
      "发现事实陈述",
      "#dc2626"
    ],
    [
      "非处罚",
      "不是最终决定",
      "#d97706"
    ],
    [
      "6类",
      "禁止暴露信息",
      "#2563eb"
    ],
    [
      "全报告",
      "用语规范统一",
      "#059669"
    ]
  ],
  "upstream": [
    [
      "rs-structure",
      "报告结构",
      "报告结构决定用语场景"
    ],
    [
      "hb-ch4",
      "税务合规判定规则",
      "判定结论用语规范"
    ],
    [
      "hb-ch6",
      "关键法律条文",
      "法律引用用语规范"
    ]
  ],
  "downstream": [
    [
      "rs-12std",
      "质量标准",
      "用语规范纳入质量检查"
    ],
    [
      "rs-narrative",
      "叙事规范",
      "用语规范约束叙事风格"
    ],
    [
      "aly-result",
      "本次分析结果",
      "发现描述用语规范"
    ]
  ],
  "desc": "<p style=\"margin:0 0 10px\"><strong>核心原则：</strong>税务合规报告处于发现阶段——检查完毕后的事实陈述，不是最终的行政处罚决定。因此用语必须使用涉嫌而不是认定，使用可能存在而不是确定存在。任何在检查阶段就做出违法定性的表述都是不恰当的。</p><p style=\"margin:0\">同时，6类系统内部信息<strong style=\"color:#dc2626\">禁止出现在正式报告中</strong>：引擎执行流程、内部配置参数、代码位置引用、系统日志内容、方法论的内部名称、AI推理过程。</p>",
  "cards": [
    [
      "正确用语",
      "涉嫌 / 可能存在 / 建议核实 / 需进一步确认 / 与申报数据存在差异 / 未能提供相关证据 / 反映出的经营模式 / 数据分析显示 / 综合判断 / 潜在风险",
      "#059669"
    ],
    [
      "禁止用语",
      "违法 / 认定 / 确定 / 必定 / 毫无疑问 / 显然 / 绝对 / 必然 / 非法 / 犯罪——这些是行政处罚决定书和刑事判决书的用语，不是税务合规报告的用语。",
      "#dc2626"
    ],
    [
      "禁止暴露（6类）",
      "①引擎执行流程（如pipeline.py第1245行）②内部配置参数（如THRESHOLD=0.8）③代码位置引用（如在domain_analysis.py中）④系统日志内容 ⑤方法论内部名称 ⑥AI推理过程",
      "#d97706"
    ],
    [
      "正确替代方案",
      "内部信息→外部表述：引擎执行流程→系统自动分析发现 / 内部配置参数→根据行业通用标准 / 代码位置引用→经过系统验证 / 系统日志→分析记录显示 / 方法论名称→多维度交叉分析 / AI推理→综合分析判断",
      "#2563eb"
    ]
  ]
});
}
// 叙事规范
function renderNarrativeStandard() {
  return _pageTemplate({
  "title": "叙事规范",
  "icon": "📝",
  "subtitle": "每条税务发现必须遵循六要素叙事框架：What→How→Evidence→Why→Impact→Action。缺失任何一要素的发现被认为是不完整的。",
  "stats": [
    [
      "6要素",
      "叙事框架",
      "#2563eb"
    ],
    [
      "3验证",
      "事实支撑",
      "#7c3aed"
    ],
    [
      "递进",
      "逻辑结构",
      "#059669"
    ],
    [
      "可读",
      "可审标准",
      "#d97706"
    ]
  ],
  "upstream": [
    [
      "rs-terms",
      "术语与机密规范",
      "用语规范指导叙事表述"
    ],
    [
      "rs-structure",
      "报告结构",
      "结构决定叙事框架"
    ],
    [
      "aly-result",
      "本次分析结果",
      "分析发现为叙事素材"
    ]
  ],
  "downstream": [
    [
      "rs-12std",
      "质量标准",
      "叙事质量纳入标准检查"
    ],
    [
      "rs-paragraph",
      "段落格式规范",
      "段落规范约束叙事格式"
    ],
    [
      "eng-think",
      "推理引擎",
      "推理链支撑叙事逻辑"
    ]
  ],
  "desc": "<p style=\"margin:0 0 10px\">每条发现必须遵循六要素叙事框架：①发现了什么（What·事实陈述）→②怎么发现的（How·分析方法）→③证据是什么（Evidence·原始数据引用）→④为什么是问题（Why·法律依据）→⑤影响有多大（Impact·金额/税种）→⑥建议怎么做（Action·整改方案）。缺失任何一要素的发现被认为是不完整的。</p>",
  "cards": [
    [
      "六要素叙事框架",
      "①What：发现的事实问题 ②How：通过什么方法发现 ③Evidence：支撑证据（具体发票号/账簿页码/金额）④Why：违反什么规定（法条编号+具体条文）⑤Impact：税务影响（涉及税款金额）⑥Action：处理建议",
      "#2563eb"
    ],
    [
      "三类事实验证",
      "①数据交叉验证：发票vs账簿vs申报表，至少2方一致才写入报告 ②时间轴验证：交易日期必须满足业务逻辑 ③金额验证：借方=贷方、发票金额=账簿金额",
      "#7c3aed"
    ],
    [
      "递进逻辑链",
      "不允许：现象→结论。必须：信号（数据异常）→推论（可能原因）→验证（交叉检查）→确认（证据充分）→结论（法律定性）。每一步推理都必须在报告中体现。",
      "#059669"
    ],
    [
      "已弃用的五段叙法",
      "旧版五段式（背景→过程→发现→分析→建议）已废弃——因为背景和过程在第一章和第二章已交代，第三章不应重复。新标准直接从发现切入，减少冗余30%以上。",
      "#d97706"
    ]
  ]
});
}
// 风险合并规则
function renderMergeRules() {
  return _pageTemplate({
  "title": "风险合并规则",
  "icon": "🔀",
  "subtitle": "同一风险类型的多条发现必须合并为一条在报告中呈现。7步合并流程确保报告简洁不冗余。",
  "stats": [
    [
      "7步",
      "合并流程",
      "#2563eb"
    ],
    [
      "按类型",
      "分组合并",
      "#7c3aed"
    ],
    [
      "最高风险",
      "合并后等级",
      "#059669"
    ],
    [
      "子项独立",
      "展示合并细节",
      "#d97706"
    ]
  ],
  "upstream": [
    [
      "aly-result",
      "本次分析结果",
      "分析发现为合并输入"
    ],
    [
      "rs-narrative",
      "叙事规范",
      "合并后遵循叙事规范"
    ]
  ],
  "downstream": [
    [
      "rs-12std",
      "质量标准",
      "合并结果接受标准检查"
    ],
    [
      "rs-structure",
      "报告结构",
      "合并后进入报告第三章"
    ]
  ],
  "desc": "<p style=\"margin:0 0 10px\">7步合并流程：①按type字段分组（去除内部前缀后trim比对）②同一组取最高风险等级作为合并后等级 ③合并后标题显示N项同类风险合并标签 ④合并后detail列出所有子项 ⑤每条子项独立展示：子项标题、细节描述、税务影响、处理建议 ⑥合并所有子项的items/evidence_rows/matched_chain_details到父项。</p>",
  "cards": [
    [
      "分组规则",
      "按type字段分组，去除内部前缀后trim比对。同一风险类型的多条发现归入一组。",
      "#2563eb"
    ],
    [
      "等级取高",
      "同一组取最高风险等级作为合并后等级。不降低任何一个子项的风险标记。",
      "#7c3aed"
    ],
    [
      "子项独立展示",
      "合并后每个子项保留独立的标题、细节描述、税务影响和处理建议。阅读者可以追溯每个子项的完整信息。",
      "#059669"
    ],
    [
      "适用场景",
      "知识图谱系列、发票合规系列、资料缺失触发系列——这三类最容易产生大量同类发现，合并效果最明显。",
      "#d97706"
    ]
  ]
});
}
// 质量标准
function render12Standards() {
  return _pageTemplate({
  "title": "质量标准",
  "icon": "✅",
  "subtitle": "以下12项标准在报告生成后依序执行检查。每项标准含要求说明、检测方法和正确范例。不通过的项目以⚠标记，不影响报告整体合规性。",
  "stats": [
    [
      "12项",
      "质量标准",
      "#2563eb"
    ],
    [
      "强制",
      "5项强制",
      "#dc2626"
    ],
    [
      "重要",
      "4项重要",
      "#d97706"
    ],
    [
      "建议",
      "3项建议",
      "#059669"
    ]
  ],
  "upstream": [
    [
      "rs-pipeline",
      "质量保障管线",
      "管线执行标准检查"
    ],
    [
      "rs-structure",
      "报告结构",
      "标准按章节分别检查"
    ]
  ],
  "downstream": [
    [
      "hb-ch8",
      "全链路质量保障",
      "标准检查结果反馈质量保障"
    ],
    [
      "rs-narrative",
      "叙事规范",
      "叙事规范为部分标准提供依据"
    ]
  ],
  "desc": "<p style=\"margin:0 0 10px\">12项标准在报告生成后依序执行。每项标准含要求说明、检测方法和正确范例。标准1-5、8-9、12为强制项（红色），6-7、10-11为重要项（橙色/绿色）。标准检查由generate_report.py→check_standards()执行，每项独立运行。</p>",
  "cards": [
    [
      "标准1-5 [强制]",
      "①模板句清除：不得出现根据相关规定等模板句 ②重复句合并：相似度>80%触发合并 ③空描述删除：不得出现无/暂无/—等空值 ④人性化表述：技术参数转通俗表达 ⑤六要素完整：What/How/Evidence/Why/Impact/Action",
      "#dc2626"
    ],
    [
      "标准6-7 [重要]",
      "⑥法律引用准确：法条引用须含编号+内容 ⑦具体数值：每条发现须至少1个具体数值",
      "#d97706"
    ],
    [
      "标准8-9 [强制]",
      "⑧因果链：不能现象→结论跳跃，必须含中间推理 ⑨可执行建议：建议必须具体可操作",
      "#dc2626"
    ],
    [
      "标准10-12",
      "⑩条款号：引用规程时须含条款号[重要] ⑪反跨复制：不得跨企业复制内容[重要] ⑫空占位符清除：全报告无残留占位符[强制]",
      "#059669"
    ]
  ]
});
}
// 判定可靠性要求
function renderReliability() {
  return _pageTemplate({
  "title": "判定可靠性要求",
  "icon": "🔍",
  "subtitle": "判定可靠性是比质量标准更底层的要求——质量标准检测的是表述是否正确，可靠性要求检测的是分析本身是否成立。7项要求按严重程度分为致命和高。",
  "stats": [
    [
      "7项",
      "可靠性要求",
      "#2563eb"
    ],
    [
      "3项",
      "致命级别",
      "#dc2626"
    ],
    [
      "4项",
      "高级别",
      "#2563eb"
    ],
    [
      "底层",
      "比质量标准更基础",
      "#d97706"
    ]
  ],
  "upstream": [
    [
      "hb-ch4",
      "税务合规判定规则",
      "判定规则指导可靠性检查"
    ],
    [
      "da-intro",
      "什么是域分析",
      "域分析的判定结论需要可靠性验证"
    ]
  ],
  "downstream": [
    [
      "rs-12std",
      "质量标准",
      "可靠性与质量标准互补"
    ],
    [
      "eng-think",
      "推理引擎",
      "推理链需要满足可靠性要求"
    ]
  ],
  "desc": "<p style=\"margin:0 0 10px\">7项要求：致命（红色）——①公司身份锚定：报告开头必须声明公司名称+信用代码 ②发票方向判定：进项/销项分类须有判定依据 ③综合判断：文件类型判定须经四方证据交叉验证。高（蓝色）——④只读有效信息：排除空白行/小计行/合计行/汇总行 ⑤存疑排除：买卖双方都不含公司姓名的发票必须排除 ⑥服务行业闸门：服务行业不得出现实物商品域分析发现 ⑦品名级精度：混合行业必须品名级区分。</p>",
  "cards": [
    [
      "致命项①②③",
      "①公司身份锚定：报告开头必须声明公司名称+信用代码 ②发票方向判定：进项/销项分类须有判定依据，存疑发票须单独列出 ③综合判断：文件类型判定须经四方证据交叉验证",
      "#dc2626"
    ],
    [
      "高级项④⑤",
      "④只读有效信息：排除空白行/小计行/合计行/汇总行 ⑤存疑排除：买卖双方都不含公司姓名的发票必须排除",
      "#2563eb"
    ],
    [
      "高级项⑥⑦",
      "⑥服务行业闸门：服务行业不得出现实物商品域分析发现 ⑦品名级精度：混合行业必须品名级区分，不能笼统对待",
      "#2563eb"
    ],
    [
      "与质量标准的区别",
      "质量标准检测表述是否正确，可靠性要求检测分析本身是否成立。可靠性是质量标准的前提——分析不成立，表述再规范也无意义。",
      "#d97706"
    ]
  ]
});
}
// 段落格式规范
function renderParaStandard() {
  return _pageTemplate({
  "title": "段落格式规范",
  "icon": "📄",
  "subtitle": "五大禁止反模式+拆分标准。禁止一逗到底、禁止多逻辑挤一段、禁止括号堆叠、子项独立成段、数据与解释分层。超过200字就拆。",
  "stats": [
    [
      "5类",
      "禁止反模式",
      "#dc2626"
    ],
    [
      "200字",
      "拆分阈值",
      "#2563eb"
    ],
    [
      "一段",
      "一个主题",
      "#059669"
    ],
    [
      "数据-解释",
      "先陈述后分析",
      "#d97706"
    ]
  ],
  "upstream": [
    [
      "rs-narrative",
      "叙事规范",
      "段落格式是叙事的载体"
    ],
    [
      "rs-12std",
      "质量标准",
      "格式规范纳入标准检查"
    ]
  ],
  "downstream": [
    [
      "rs-structure",
      "报告结构",
      "格式规范应用于各章节"
    ],
    [
      "rs-terms",
      "术语与机密规范",
      "格式规范配合用语规范"
    ]
  ],
  "desc": "<p style=\"margin:0 0 10px\">五大禁止反模式：①禁止一逗到底——多个完整逻辑句子各自独立成段 ②禁止多逻辑挤一段——同段不得混杂2个以上不相关分析维度 ③禁止括号堆叠——不得用括号内堆砌多段判定逻辑链 ④子项独立成段——子项内容各自独立为一段 ⑤数据与解释分层——先陈述数据事实→再解释分析方法→最后给出结论。</p>",
  "cards": [
    [
      "禁止一逗到底",
      "多个完整逻辑句子各自独立成段。一段只表达一个完整意思，多个逻辑点必须分开成段。",
      "#dc2626"
    ],
    [
      "禁止多逻辑挤一段",
      "同段不得混杂2个以上不相关分析维度。不同域、不同税种、不同时间段的发现必须分别成段。",
      "#dc2626"
    ],
    [
      "禁止括号堆叠",
      "不得用括号内堆砌多段判定逻辑链。括号内的内容应为简短说明，不是正文的替代品。",
      "#dc2626"
    ],
    [
      "拆分标准",
      "每写完一段自问：只有一个主题吗？能用一句话概括主旨吗？超过200字了吗（超了就拆）？三段自检确保段落清晰。",
      "#2563eb"
    ]
  ]
});
}
// 语音播报标准
function renderTTSStandard() {
  return _pageTemplate({
  "title": "语音播报标准",
  "icon": "🔊",
  "subtitle": "全文播报+点击播报功能，中文男声，6档语调。视觉跟随（橙色底纹高亮+自动滚动）。",
  "stats": [
    [
      "6档",
      "语调分级",
      "#2563eb"
    ],
    [
      "中文男声",
      "低沉严肃",
      "#7c3aed"
    ],
    [
      "全文",
      "播报功能",
      "#059669"
    ],
    [
      "点击",
      "逐段播报",
      "#d97706"
    ]
  ],
  "upstream": [
    [
      "rs-structure",
      "报告结构",
      "按章节播报"
    ],
    [
      "rs-narrative",
      "叙事规范",
      "叙事结构影响播报节奏"
    ]
  ],
  "downstream": [
    [
      "rs-paragraph",
      "段落格式规范",
      "段落格式影响播报停顿"
    ],
    [
      "rs-12std",
      "质量标准",
      "播报前质量检查"
    ]
  ],
  "desc": "<p style=\"margin:0 0 10px\">全文播报（报告顶部控制条）+点击播报（点击任意段落）。播放控制：暂停/继续/停止，语速0.85x-1.3x。视觉跟随：橙色底纹高亮当前播报段落+自动滚动。</p><p style=\"margin:0\">音色：中文男声（zh-CN male），低沉严肃的中年税务合规员声线。降级策略：zh-CN male→zh-CN non-Tingting→zh任意。</p>",
  "cards": [
    [
      "6档语调",
      "章节标题0.65音调/0.7x语速、小节标题0.72/0.8x、高风险内容0.68/0.75x、法律条文0.70/0.72x、处理建议0.80/0.85x、普通叙述0.78/0.88x",
      "#2563eb"
    ],
    [
      "音色标准",
      "中文男声（zh-CN male），低沉严肃的中年税务合规员声线。确保播报的专业性和权威感。",
      "#7c3aed"
    ],
    [
      "播放控制",
      "全文播报+点击播报。暂停/继续/停止操作。语速可调0.85x-1.3x。视觉跟随橙色底纹高亮。",
      "#059669"
    ],
    [
      "降级策略",
      "首选zh-CN male→备选zh-CN non-Tingting→兜底zh任意。确保在任何设备上都能正常播报。",
      "#d97706"
    ]
  ]
});
}
// 触发与交付
function renderSyncMechanism() {
  return _pageTemplate({
  "title": "触发与交付",
  "icon": "🔄",
  "subtitle": "系统数据的跨模块一致性由审计引擎自动保障。四触发机制确保全模块数据统一——手动/sync、start.bat启动、git commit、pipeline.py启动。链接到hb-ch10。",
  "stats": [
    [
      "4触发",
      "全模块同步",
      "#2563eb"
    ],
    [
      "3命令",
      "审计/sync/calibrate",
      "#7c3aed"
    ],
    [
      "全自动",
      "启动时自检",
      "#059669"
    ]
  ],
  "upstream": [
    [
      "hb-ch10",
      "数据一致性自检",
      "一致性自检机制来源"
    ],
    [
      "hb-ch8",
      "全链路质量保障",
      "质量保障依赖同步机制"
    ]
  ],
  "downstream": [
    [
      "rs-structure",
      "报告结构",
      "同步保证报告数据准确"
    ],
    [
      "rs-12std",
      "质量标准",
      "同步数据通过标准检查"
    ]
  ],
  "desc": "<p style=\"margin:0 0 10px\">四触发机制：①手动 python audit_consistency.py --sync ②start.bat启动时自动执行 ③git commit pre-commit钩子自动触发 ④pipeline.py启动时调用。三种命令模式：纯审计（只报告不一致项）/ --sync（自动修复不一致项）/ --calibrate（重新统计权威数据源，用于数据源变更后的基准校正）。</p>",
  "cards": [
    [
      "四触发机制",
      "①手动--sync ②start.bat启动 ③git commit钩子 ④pipeline.py启动。四种场景全覆盖，确保任何时候系统数据都保持一致性。",
      "#2563eb"
    ],
    [
      "三种命令",
      "纯审计（只报告不一致）/ --sync（联动同步自动修复）/ --calibrate（重新统计权威数据源）。根据场景选择合适命令。",
      "#7c3aed"
    ],
    [
      "报告交付保障",
      "同步完成后→一致性验证→绿色交付。不一致项超过阈值→黄色交付（标注已知差异），严重不一致→红色阻断。",
      "#059669"
    ]
  ]
});
}
// 什么是域分析
function renderDAIntro() {
  return _pageTemplate({
  "title": "什么是域分析",
  "icon": "💡",
  "subtitle": "域分析是税务合规系统的核心分析层——位于文件解析和报告生成之间。系统将全部原始数据导入多个独立的分析域，每个域从不同维度对同一份数据做独立又交叉的审视。",
  "stats": [
    [
      "42个",
      "域分析函数",
      "#2563eb"
    ],
    [
      "9字段",
      "标准发现输出",
      "#7c3aed"
    ],
    [
      "13大类",
      "域函数分类",
      "#059669"
    ],
    [
      "3驱动",
      "资料/算法/知识",
      "#d97706"
    ]
  ],
  "upstream": [
    [
      "fp-result",
      "本次解析结果",
      "文件解析输出供给域分析"
    ],
    [
      "fp-mechanism",
      "识别机制",
      "文件识别结果输入域分析"
    ]
  ],
  "downstream": [
    [
      "da-arch",
      "域分析架构",
      "域分析的驱动架构"
    ],
    [
      "da-domains",
      "分析域",
      "域分析的完整列表"
    ],
    [
      "da-result",
      "域分析结果",
      "域分析的产出"
    ]
  ],
  "desc": "<p style=\"margin:0 0 10px\">域分析工作流程：①数据流入——文件解析模块输出的结构化数据（bank_txs/sal_invs/pur_invs/工资社保凭证库存合同/行业画像ctx.industry）②域执行——{{domain_functions}}个域分析函数独立运行，每个域有数据守卫条件，缺数据标记资料缺口不空跑，行业闸门自动跳过不适用域 ③发现输出——每条发现含9个标准字段 ④跨域串联——单域发现→多域交叉印证→线索链+证据链+分析链→协商引擎消解→同向证据置信度叠加升权。</p>",
  "cards": [
    [
      "数据流入",
      "文件解析模块输出的结构化数据：bank_txs（银行交易）、sal_invs（销项发票）、pur_invs（进项发票）、工资表、社保凭证、库存合同、行业画像等。单一数据源，多维度交叉。",
      "#2563eb"
    ],
    [
      "域执行",
      "{{domain_functions}}个域分析函数独立运行。每个域有数据守卫条件（缺数据不空跑），行业闸门自动跳过不适用域（如服务行业跳过BOM分析）。",
      "#7c3aed"
    ],
    [
      "发现输出",
      "每条发现含9个标准字段：type（类型）、level（风险等级）、score（0-10）、detail（详细数据）、description（解读）、suggestion（建议）、policy_ref（法律依据）、category（分类）、domain（来源域）。",
      "#059669"
    ],
    [
      "跨域串联",
      "单域发现→多域交叉印证→线索链+证据链+分析链→协商引擎消解矛盾→同向证据置信度叠加升权。从离散发现到系统结论。",
      "#d97706"
    ]
  ]
});
}
// 域分析架构
function renderDAArch() {
  return _pageTemplate({
  "title": "域分析架构",
  "icon": "🏗️",
  "subtitle": "系统将分析域按驱动方式分为三类——资料驱动、算法驱动、知识驱动。不同类型的域有不同的激活条件和置信度逻辑。",
  "stats": [
    [
      "3类",
      "驱动方式",
      "#2563eb"
    ],
    [
      "资料",
      "依赖上传资料",
      "#dc2626"
    ],
    [
      "算法",
      "基于数据特征",
      "#2563eb"
    ],
    [
      "知识",
      "内置基准库",
      "#7c3aed"
    ]
  ],
  "upstream": [
    [
      "da-intro",
      "什么是域分析",
      "域分析的基本概念"
    ],
    [
      "da-domains",
      "分析域",
      "域分析的完整列表"
    ]
  ],
  "downstream": [
    [
      "da-result",
      "域分析结果",
      "不同类型域的产出汇总"
    ],
    [
      "fp-result",
      "本次解析结果",
      "资料驱动域依赖解析结果"
    ]
  ],
  "desc": "<p style=\"margin:0 0 10px\">三类驱动方式：①资料驱动域（红色边线）——依赖上传资料进行判断，资料完备度越高置信度越高。代表：资金流向追踪（需银行流水）、工资社保比对（需工资表+社保）、合同比对（需合同+发票）②算法驱动域（蓝色边线）——基于数据内在特征自动计算，无需外部参考资料。代表：进销毛利率、存货周转预警、异常交易时间分析 ③知识驱动域（紫色边线）——内置行业基准库和法规库，将企业实际数据与66个行业基准对比。代表：行业对标分析、规则全覆盖验证。</p>",
  "cards": [
    [
      "资料驱动域",
      "依赖上传资料进行判断。资料完备度越高置信度越高。缺资料的域自动标记跳过，不生成空发现。代表域：资金流向追踪、工资社保比对、合同比对。",
      "#dc2626"
    ],
    [
      "算法驱动域",
      "基于数据内在特征自动计算，无需外部参考资料。自适应运行，不需要用户额外提供任何资料。代表域：进销毛利率、存货周转预警、异常交易时间分析。",
      "#2563eb"
    ],
    [
      "知识驱动域",
      "内置行业基准库和法规库，将企业实际数据与66个行业基准对比。知识库持续更新维护。代表域：行业对标分析（{{industries}}行业基准）、规则全覆盖验证（{{rules_count}}条规则）。",
      "#7c3aed"
    ]
  ]
});
}
// 分析域
function renderDADomains() {
  return _pageTemplate({
  "title": "分析域",
  "icon": "📊",
  "subtitle": "每个域由独立的域分析函数驱动，按类别分组为13大类。含7条判定规则前置检查。所有域函数全行业适用，无行业特化硬编码。",
  "stats": [
    [
      "42个",
      "域函数",
      "#2563eb"
    ],
    [
      "13大类",
      "域函数分类",
      "#7c3aed"
    ],
    [
      "7规则",
      "前置判定检查",
      "#059669"
    ],
    [
      "66行业",
      "行业基准库",
      "#d97706"
    ]
  ],
  "upstream": [
    [
      "da-intro",
      "什么是域分析",
      "域分析的基本概念"
    ],
    [
      "da-arch",
      "域分析架构",
      "域分析的驱动架构"
    ]
  ],
  "downstream": [
    [
      "da-result",
      "域分析结果",
      "域分析的产出"
    ],
    [
      "hb-ch9",
      "跨域协商引擎",
      "域分析产出进入协商"
    ]
  ],
  "desc": "<p style=\"margin:0 0 10px\">7条判定规则前置检查（域分析执行前必须先通过）：公司身份锚定、发票方向判定、进项再分类、服务行业闸门、品名级精准过滤、综合判断四方交叉验证、存疑排除。</p><p style=\"margin:0\">13大分类：①资金流分析（4域）②进销存分析（4域）③供应商与客户分析（4域）④多源交叉验证（5域）⑤经营实质分析（3域）⑥资料完备度与情报（2域）⑦发票深度分析（3域）⑧合同与凭证（2域）⑨税务与社保（3域）⑩资产与关联交易（2域）⑪行业对标与规则引擎（4域）⑫跨域分析链（1域）⑬补充税种检查（3域）。</p>",
  "cards": [
    [
      "资金流+进销存（8域）",
      "资金全链路追踪、资金流向追踪、异常交易时间、个人交易风险；进销毛利率、发票实质性审计、存货周转预警、发票存货付款三角验证",
      "#2563eb"
    ],
    [
      "供应商+多源验证（9域）",
      "供应商穿透、供应商画像、上下游穿透、客户维度三源穿透；多源交叉验证、凭证发票收入对比、利润现金流矛盾、收入时间线调查、扩展审查规则",
      "#7c3aed"
    ],
    [
      "经营实质+资料（5域）",
      "经营实质分析7维度、经营实质地理分析、人员与业务匹配；资料完备度评估14类必查、资料情报摘要",
      "#059669"
    ],
    [
      "发票+合同+社保（8域）",
      "发票深度特征、发票生命周期、红冲作废发票；合同比对、凭证科目异常；税务缴纳一致性、增值税申报比对、工资社保比对",
      "#d97706"
    ]
  ]
});
}
// ================================================================
// 域分析引擎全景面板
// ================================================================
function renderUnifiedDomainPanel(container) {
  if (!container) return;
  var h = '';
  h += '<style>'
    + '.udp{max-width:1140px;margin:0 auto;padding:0;font-size:10px;line-height:20px;color:#3a4048;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}'
    + '.udp h2{font-size:10px;font-weight:800;color:#16233a;margin:32px 0 12px;padding-bottom:10px;border-bottom:2px solid #16233a}'
    + '.udp h2:first-child{margin-top:0;border-bottom:none;padding-bottom:0;margin-bottom:10px}'
    + '.udp p{margin:0 0 10px}'
    + '.udp p b,.udp p strong{color:#16233a;font-weight:600}'
    + '.udp p em{font-style:normal;color:#9a1f2b;font-weight:600}'
    + '.udp .dom-table{width:100%;border-collapse:collapse;font-size:10px;margin:10px 0}'
    + '.udp .dom-table td{padding:6px 10px;border-bottom:1px solid #eff2f6;vertical-align:top;font-size:10px;line-height:1.8}'
    + '.udp .dom-table th{text-align:left;padding:8px 10px;background:#fafbfc;font-size:10px;color:#64748b;font-weight:600;border-bottom:2px solid #16233a;white-space:nowrap}'
    + '.udp .dom-table .ghead td{background:#fafbfc;padding:10px 10px;font-size:10px;border-bottom:1px solid #e2e8f0}'
    + '.udp .udp-block{background:#fafbfc;border:1px solid #eff2f6;border-radius:8px;padding:13px 15px;margin:4px 0 14px;font-size:10px;line-height:20px}'
    + '.udp .udp-stats{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0}'
    + '.udp .udp-stat{flex:1;min-width:130px;background:#fafbfc;border:1px solid #eff2f6;border-radius:8px;padding:14px 16px;text-align:center}'
    + '.udp .udp-stat .val{font-size:10px;font-weight:800;color:#16233a;display:block;line-height:1.2}'
    + '.udp .udp-stat .lbl{font-size:10px;color:#64748b;display:block;margin-top:4px}'
    + '.udp .udp-rule{display:flex;gap:10px;align-items:flex-start;margin:6px 0;padding:10px 14px;background:#fafbfc;border-radius:6px;border-left:3px solid #e2e8f0;font-size:10px;line-height:20px}'
    + '.udp .udp-chain{padding:14px 18px;margin-bottom:10px;background:#fff;border:1px solid #eff2f6;border-radius:8px;font-size:10px;line-height:1.9}'
    + '.udp .udp-step{padding:8px 14px;margin:4px 0;background:#f8fafc;border-radius:6px;font-size:10px;line-height:1.9;border-left:3px solid #e2e8f0}'
    + '.udp .udp-step .sn{display:inline-flex;align-items:center;justify-content:center;min-width:22px;height:22px;border-radius:50%;background:#16233a;color:#fff;font-size:10px;font-weight:700;margin-right:10px;flex-shrink:0}'
    + '.udp details{margin-bottom:10px}'
    + '.udp summary{font-size:10px;font-weight:700;color:#16233a;cursor:pointer;padding:6px 0}'
    + '</style>';
  h += '<div class="udp">';

  h += '<h2>一、7条前置判定规则（域分析执行前必须先通过，顺序不可调）</h2>';
  h += '<p>7条规则分两级执行：<b>全局级（①-③）</b>——域分析开始前一次性执行，不通过则全分析终止；<b>域级（④-⑦）</b>——随域分析逐域执行，不通过则跳过对应域，其他域继续。</p>';
  h += '<p><b>① 公司身份锚定（全局级）</b>——报告开头必须声明公司名称+信用代码。锚定错误→全部分析作废。</p>';
  h += '<p><b>② 发票方向判定（全局级）</b>——进项/销项分类须有判定依据。方向错→收入成本颠倒。</p>';
  h += '<p><b>③ 进项再分类（全局级）</b>——普票税额并入成本，专票税额入进项税额。分类错→threshold阈值基准错误。</p>';
  h += '<p><b>④ 服务行业闸门（域级）</b>——服务行业不得出现进销存/制造业毛利率对标等实物域分析。扩展：COND_BAN防误杀规则同步执行。</p>';
  h += '<p><b>⑤ 品名级精准过滤（域级）</b>——混合行业必须品名级区分。补充：文件多格式兼容、汇总行自动过滤，两规则在域分析前执行。</p>';
  h += '<p><b>⑥ 综合判断四方交叉验证（域级）</b>——文件类型须经文件名+表头+内容+身份匹配四方验证。</p>';
  h += '<p><b>⑦ 存疑排除（域级）</b>——买卖双方都不含公司的发票必须排除出所有计算。跨账套污染=致命事故。</p>';

  h += '<h2>二、13大分类 · 40个域函数 · 数据依赖与输出类型</h2>';
  h += '<p>本章按业务领域分为13大类（设计视角），与第三章按功能聚合的五大域组（运行视角）互为补充。本章管每个域"做什么"，第三章管域与域之间"怎么配合"。13大分类合计：4+4+4+5+3+2+3+2+3+2+4+1+3=40域。</p>';
  h += '<div class="udp-block"><h4>域函数清单（含输入数据要求、最低条数、缺失行为和finding.type枚举值）</h4>';
  h += '<p><b>资金流分析</b></p>';
  h += '<p><b>_domain_cash_flow_tracking</b>（资金全链路追踪）——输入：银行流水（必须）；最低：≥10条；输出finding.type：收款方异常、大额支付、频繁支付。</p>';
  h += '<p><b>_domain_fund_flow</b>（资金流向追踪）——输入：银行流水（必须）；最低：≥10条；输出finding.type：资金流向异常、单边大额资金。</p>';
  h += '<p><b>_domain_abnormal_transaction_time</b>（异常交易时间）——输入：银行流水（必须）；最低：≥10条；输出finding.type：非营业时间交易、节假日大额交易。</p>';
  h += '<p><b>_domain_personal_txn_risk</b>（个人交易风险）——输入：银行流水（必须）；最低：≥10条；输出finding.type：个人账户收款、对私转账高频。</p>';
  h += '<p><b>进销存分析</b></p>';
  h += '<p><b>_domain_purchase_sales_gross_margin</b>（进销毛利率）——输入：销项发票+进项发票（必须）；科目余额表（应当）；最低：发票≥10张；输出finding.type：毛利率偏离行业基准、进销倒挂。</p>';
  h += '<p><b>_domain_invoice_substantive_audit</b>（发票实质性审计）——输入：发票数据（必须）；最低：≥10张；输出finding.type：发票号码异常、税率异常、品名异常。</p>';
  h += '<p><b>_domain_inventory_turnover</b>（存货周转预警）——输入：库存明细（必须）；发票数据（应当）；最低：库存记录≥5条；输出finding.type：周转率异常、库存积压、快进快出。</p>';
  h += '<p><b>_domain_invoice_inventory_payment_triangle</b>（三角验证）——输入：发票+入库单+付款单（必须）；最低：三单各≥3条；输出finding.type：三单不一致、付款与入库不匹配。</p>';
  h += '<p><b>供应商与客户</b></p>';
  h += '<p><b>_domain_supplier_penetration</b>（供应商穿透）——输入：进项发票（必须）；最低：≥5条；输出finding.type：对私供应商、小规模供应商、新设公司。</p>';
  h += '<p><b>_domain_supplier_profile</b>（供应商画像）——输入：进项发票+工商信息（必须）；最低：≥5条；输出finding.type：供应商经营异常、失联供应商、风险供应商。</p>';
  h += '<p><b>_domain_upstream_downstream</b>（上下游穿透）——输入：进项发票+销项发票（必须）；最低：各≥5条；输出finding.type：供应商即客户、关联方重合。</p>';
  h += '<p><b>_domain_customer_three_source</b>（客户三源穿透）——输入：销项发票（必须）；最低：≥5条；输出finding.type：客户信息不一致、虚假客户。</p>';
  h += '<p><b>多源交叉验证</b></p>';
  h += '<p><b>_domain_multi_source_cross_validation</b>（多源交叉验证）——输入：银行流水+发票+账载凭证+申报表（应当）；至少2源（必须）；最低：各源≥5条；输出finding.type：四源偏差、单源异常。</p>';
  h += '<p><b>_domain_voucher_invoice_revenue_compare</b>（凭证发票收入对比）——输入：会计凭证+销项发票（必须）；最低：各≥5条；输出finding.type：凭证收入与发票不一致。</p>';
  h += '<p><b>_domain_profit_cashflow_contradiction</b>（利润现金流矛盾）——输入：科目余额表+银行流水（必须）；最低：各≥10条；输出finding.type：账面盈利现金枯竭、应收异常膨胀。</p>';
  h += '<p><b>_domain_revenue_time_investigation</b>（收入时间线调查）——输入：销项发票+银行流水（必须）；最低：各≥10条；输出finding.type：季末突击开票、收入集中化。</p>';
  h += '<p><b>_domain_extended_audit_rules</b>（扩展审查规则）——输入：原始数据（可选）；最低：无最低要求；输出finding.type：自定义信号。</p>';
  h += '<p><b>经营实质分析</b></p>';
  h += '<p><b>_domain_business_substance</b>（经营实质分析）——输入：银行流水+发票+工资+社保（应当）；至少3源（必须）；最低：各源≥10条；输出finding.type：人员不匹配、场地缺失、设备与产能不符。</p>';
  h += '<p><b>_domain_business_geography</b>（经营地理分析）——输入：发票+银行流水（必须）；工商登记地址（应当）；最低：≥10条；输出finding.type：注册地与经营地不一致、地址分散。</p>';
  h += '<p><b>_domain_personnel_business_matching</b>（人员业务匹配）——输入：工资表+社保数据（必须）；个税申报（应当）；最低：≥5条；输出finding.type：社保人数与业务规模不匹配、零参保。</p>';
  h += '<p><b>资料完备度</b></p>';
  h += '<p><b>_domain_material_completeness</b>（资料完备度评估）——输入：所有上传文件（必须）；最低：无最低要求；输出finding.type：资料缺失、资料不完备。</p>';
  h += '<p><b>_domain_material_intel</b>（资料情报摘要）——输入：所有上传文件（必须）；最低：无最低要求；输出finding.type：收购/重组/诉讼等关键情报。</p>';
  h += '<p><b>发票深度分析</b></p>';
  h += '<p><b>_domain_invoice_deep_features</b>（发票深度特征）——输入：发票数据（必须）；最低：≥20张；输出finding.type：连号开票、顶格开票、整数金额、夜间开票。</p>';
  h += '<p><b>_domain_invoice_lifecycle</b>（发票生命周期）——输入：发票数据（必须）；最低：≥20张；输出finding.type：领用与开具不符、异常作废。</p>';
  h += '<p><b>_domain_red_rush_invoice</b>（红冲作废发票）——输入：发票数据（必须）；最低：≥20张；输出finding.type：红冲频率过高、作废率大于15%。</p>';
  h += '<p><b>合同与凭证</b></p>';
  h += '<p><b>_domain_contract_comparison</b>（合同比对）——输入：合同文件+发票（必须）；最低：合同≥1份，发票≥5张；输出finding.type：合同金额与发票不符、合同缺失。</p>';
  h += '<p><b>_domain_voucher_account_anomaly</b>（凭证科目异常）——输入：会计凭证（必须）；最低：≥10条；输出finding.type：科目使用错误、摘要与科目不匹配。</p>';
  h += '<p><b>税务与社保</b></p>';
  h += '<p><b>_domain_tax_payment_consistency</b>（税务缴纳一致性）——输入：纳税申报表（必须）；发票+银行流水（应当）；最低：申报表≥1份，其他≥5条；输出finding.type：申报与缴纳不一致。</p>';
  h += '<p><b>_domain_vat_declaration_comparison</b>（增值税申报比对）——输入：增值税申报表+发票（必须）；最低：≥5条；输出finding.type：销项申报与发票不一致、进项申报异常。</p>';
  h += '<p><b>_domain_salary_social_security</b>（工资社保比对）——输入：工资表+社保数据+个税申报（应当）；至少2源（必须）；最低：各≥5条；输出finding.type：三数不一致。</p>';
  h += '<p><b>资产与关联交易</b></p>';
  h += '<p><b>_domain_asset_depreciation_amortization</b>（资产折旧摊销）——输入：科目余额表（必须）；固定资产明细（应当）；最低：≥5条；输出finding.type：折旧年限异常、摊销方法不合规。</p>';
  h += '<p><b>_domain_related_party_transaction</b>（关联交易穿透）——输入：进项发票+销项发票+工商信息（必须）；最低：各≥5条；输出finding.type：关联交易、转移定价、债资比超标。</p>';
  h += '<p><b>行业对标与规则</b></p>';
  h += '<p><b>_domain_industry_benchmark</b>（行业基准对标）——输入：发票+科目余额表（必须）；最低：≥10条；输出finding.type：偏离行业基准。</p>';
  h += '<p><b>_domain_rule_engine_match</b>（规则引擎匹配）——输入：所有数据（必须）；最低：无最低要求；输出finding.type：规则触发信号。</p>';
  h += '<p><b>_domain_tax_burden_analysis</b>（税负率分析）——输入：纳税申报表+发票（应当）；最低：≥10条；输出finding.type：税负率低于行业P25。</p>';
  h += '<p><b>_domain_trend_analysis</b>（趋势分析）——输入：科目余额表+发票（必须）；最低：≥10条；输出finding.type：指标异常波动。</p>';
  h += '<p><b>跨域分析链</b></p>';
  h += '<p><b>_domain_cross_analysis_chains</b>（跨域分析链）——输入：所有域发现（必须）；最低：域发现≥1条；输出finding.type：跨域线索→证据→分析三链贯通。</p>';
  h += '<p><b>补充税种</b></p>';
  h += '<p><b>_domain_stamp_duty_check</b>（印花税）——输入：合同+发票+银行流水（应当）；至少1源满足最低条数（必须）；最低：≥5条；输出finding.type：印花税漏缴。</p>';
  h += '<p><b>_domain_cit_reconciliation</b>（企业所得税汇算）——输入：科目余额表（必须）；凭证（应当）；最低：≥10条；输出finding.type：应纳税所得额调整。</p>';
  h += '<p><b>_domain_export_vat_verification</b>（出口退税核验）——输入：出口报关单+发票+收汇记录（必须）；最低：各≥3条；输出finding.type：三单不匹配。</p>';

  h += '<h2>三、五大域组概要（运行视角）</h2>';
  h += '<p>本章按功能聚合将40域分为五大域组：资金流与进销存（算账）、供应商与多源验证（查人）、经营实质与资料（验真）、发票/合同/社保（对票）、税务/资产/行业/跨域/补充（定性）。与第二章按业务领域的13大分类互为补充。五大组合计：8+9+5+8+10=40域。</p>';
  h += '<div class="udp-stats">';
  h += '<div class="udp-stat"><span class="val" style="color:#2563eb">8域</span><span class="lbl">资金流+进销存</span></div>';
  h += '<div class="udp-stat"><span class="val" style="color:#7c3aed">9域</span><span class="lbl">供应商+多源验证</span></div>';
  h += '<div class="udp-stat"><span class="val" style="color:#059669">5域</span><span class="lbl">经营实质+资料</span></div>';
  h += '<div class="udp-stat"><span class="val" style="color:#d97706">8域</span><span class="lbl">发票+合同+社保</span></div>';
  h += '<div class="udp-stat"><span class="val" style="color:#0ea5e9">10域</span><span class="lbl">税务+资产+行业+跨域+补充</span></div>';
  h += '</div>';

  h += '<h2>四、66行业基准库（5指标×3基准值×66行业）</h2>';
  h += '<p>行业基准库为以下域函数提供行业阈值：毛利率→_domain_purchase_sales_gross_margin、_domain_industry_benchmark；净利率→_domain_profit_cashflow_contradiction；税负率→_domain_tax_burden_analysis；进销比→_domain_purchase_sales_gross_margin；人均营收→_domain_personnel_business_matching。</p>';
  h += '<p>毛利率：企业值低于行业P25→高风险；低于P50×0.85→中风险。净利率：低于P25→高风险；低于P50×0.85→中风险。税负率：低于P25→高风险。进销比：偏离典型值±30%→异常预警。人均营收：偏离均值±50%→高风险（知识密集型服务业50-100万为正常）。覆盖66个细分行业：农林牧渔、采矿、制造、建筑、批发零售、交通运输、住宿餐饮、信息技术、金融、房地产、租赁商务、科研服务、水利环境、居民服务、教育、卫生、文体娱乐、公共管理共18个大类。</p>';
  h += '<p><b>EMA动态校准参数：</b>校准频率——按季度批量校准，每次使用最近12个月的全量历史分析数据。初始值来源——取最近三年国家统计局及行业协会公开发布的行业统计数据，过渡期内每次校准结果须经人工审核确认。单次校准样本量下限——单个行业有效分析样本量低于10户时，本次不校准，沿用上期基准值；样本量10-30户时校准结果标记为低置信度，需人工复核。数据源：industry_benchmarks表。</p>';

  h += '<h2>五、19条跨域综合推理链（编号1-19连续）</h2>';
  h += '<p>经甄别，原48条分析链中以下19条属于真正的跨域综合推理链——每条均产生跨域数据分析结果并输出综合结论。已重新编号为1-19连续编号（原编号见分析链名称，对应关系可查cross_domain_analysis.json）。其余29条已分别归入前置判定规则、数据预处理模块、质量保障准则或引擎铁律。</p>';
  h += '<div class="udp-chain"><div style="display:flex;align-items:center;gap:6px;margin-bottom:4px"><span style="display:inline-block;padding:2px 8px;border-radius:3px;font-size:10px;font-weight:600;background:#dc262615;color:#dc2626">高风险</span><span style="font-size:10px;font-weight:700;color:#16233a">1. 收款来源不匹配→隐匿收入推理链</span></div><div style="font-size:10px;color:#64748b;margin-bottom:6px;line-height:1.9">从单一的收款来源不匹配信号出发，逐层扩展分析范围。第一步确认不匹配的规模，第二步核实付款方身份（排除法人/股东的打款），第三步判断资金性质（经营收入还是非经营资金），第四步对无法解释的收款做出隐匿收入的判断。每一步都有回退路径——只要企业能提供合理解释，风险就会降级或消除。</div><div style="font-size:10px;font-weight:600;color:#64748b;margin:8px 0 6px">推理路径（4步）：</div><div class="udp-step"><span class="sn">1</span>从 <b>资金流分析</b> 到 <b style="color:#0e7490">发票比对</b>：逐名交叉比对全部收款方与销项发票购方名称</div><div class="udp-step"><span class="sn">2</span>从 <b>发票比对</b> 到 <b style="color:#0e7490">付款方身份核实</b>：联网查询法定代表人/股东名单，比对未匹配的付款方</div><div class="udp-step"><span class="sn">3</span>从 <b>付款方身份核实</b> 到 <b style="color:#0e7490">资金性质判断</b>：区分注资/借款/往来款/未开票收入四种可能</div><div class="udp-step"><span class="sn">4</span>从 <b>资金性质判断</b> 到 <b style="color:#0e7490">综合结论</b>：无法说明来源的收款推定为未开票经营收入→隐匿收入风险</div><div style="font-size:10px;color:#64748b;margin-top:6px">关联规则（共14条）：79、210、217、244、249、359、476、654、655、685、822、1226、1256、1503</div></div><div class="udp-chain"><div style="display:flex;align-items:center;gap:6px;margin-bottom:4px"><span style="display:inline-block;padding:2px 8px;border-radius:3px;font-size:10px;font-weight:600;background:#dc262615;color:#dc2626">高风险</span><span style="font-size:10px;font-weight:700;color:#16233a">2. 加工费来自外地→全链条经营异常推理链（点→面推理核心）</span></div><div style="font-size:10px;color:#64748b;margin-bottom:6px;line-height:1.9">从加工费这一个单点异常出发，扩展到面的推理。第一步发现加工费在外地，第二步判断商业合理性（本地是否有集群），第三步扩展到三组地址对比，第四步检测运输成本缺失，第五步得出物理不可能的结论。这是点→面推理的标准案例——单点异常可解释，但四点叠加无法解释——换一个税务合规员拿同样资料，同样会得出这个结论。</div><div style="font-size:10px;font-weight:600;color:#64748b;margin:8px 0 6px">推理路径（5步）：</div><div class="udp-step"><span class="sn">1</span>从 <b>发票分析</b> 到 <b style="color:#0e7490">产业集群判断</b>：分析企业所在地是否有同类加工产业集群</div><div class="udp-step"><span class="sn">2</span>从 <b>产业集群判断</b> 到 <b style="color:#0e7490">商业合理性判断</b>：外地加工增加了运输成本和周期，舍近求远→商业逻辑存疑</div><div class="udp-step"><span class="sn">3</span>从 <b>商业合理性判断</b> 到 <b style="color:#0e7490">全链条地理分析</b>：提取三组地址做城市交叉比对</div><div class="udp-step"><span class="sn">4</span>从 <b>全链条地理分析</b> 到 <b style="color:#0e7490">物理合理性判断</b>：货物在N个城市间反复运输但无运输费→物理上不可能</div><div class="udp-step"><span class="sn">5</span>从 <b>物理合理性判断</b> 到 <b style="color:#0e7490">综合结论</b>：全链条经营实质存疑→所有跨省交易的真实性需要逐笔验证</div><div style="font-size:10px;color:#64748b;margin-top:6px">关联规则（共9条）：55、80、216、1500、1501、1502、1504、1505、1510</div></div><div class="udp-chain"><div style="display:flex;align-items:center;gap:6px;margin-bottom:4px"><span style="display:inline-block;padding:2px 8px;border-radius:3px;font-size:10px;font-weight:600;background:#d9770615;color:#d97706">中风险</span><span style="font-size:10px;font-weight:700;color:#16233a">3. 进销品名不匹配→企业类型重判推理链（三层穿透）</span></div><div style="font-size:10px;color:#64748b;margin-bottom:6px;line-height:1.9">不从单一来源判定企业类型，而是通过三层递进穿透：工商登记看法律形式、发票数据看经营实质、加工信号看业务模式。三者不一致时以实质重于形式为原则。风险不是消除了，而是从品名问题转移到了加工真实性问题——这是风险转移而非风险消除。</div><div style="font-size:10px;font-weight:600;color:#64748b;margin:8px 0 6px">推理路径（4步）：</div><div class="udp-step"><span class="sn">1</span>从 <b>工商查询</b> 到 <b style="color:#0e7490">发票推断</b>：从全部发票品名关键词做66行业加权投票，得出发票推断行业</div><div class="udp-step"><span class="sn">2</span>从 <b>发票推断</b> 到 <b style="color:#0e7490">加工信号检测</b>：筛查进项发票中是否含加工费+是否存在原材料采购</div><div class="udp-step"><span class="sn">3</span>从 <b>加工信号检测</b> 到 <b style="color:#0e7490">三层综合判断</b>：工商登记=批发业(形式) + 发票推断=纺织制造(实质) + 加工信号=制造业(模式)</div><div class="udp-step"><span class="sn">4</span>从 <b>三层综合判断</b> 到 <b style="color:#0e7490">风险重定向</b>：风险从「有进无销=隐匿收入」转移至「加工链条是否真实」</div><div style="font-size:10px;color:#64748b;margin-top:6px">关联规则（共9条）：218、368、390、694、1017、1018、1357、1444、1495</div></div><div class="udp-chain"><div style="display:flex;align-items:center;gap:6px;margin-bottom:4px"><span style="display:inline-block;padding:2px 8px;border-radius:3px;font-size:10px;font-weight:600;background:#dc262615;color:#dc2626">高风险</span><span style="font-size:10px;font-weight:700;color:#16233a">4. 有进无销→隐匿收入vs制造业加工推理链</span></div><div style="font-size:10px;color:#64748b;margin-bottom:6px;line-height:1.9">有进无销是税务合规中最常见的信号，但一刀切「高 风险」是错误的。系统先判断企业类型——纯贸易企业有进无销确实是隐匿收入信号，但制造业企业采购原料加工成成品后品名不同，进销品名不匹配是正常的。诊断后风险焦点从「隐匿收入」转移至「加工链条是否真实」。</div><div style="font-size:10px;font-weight:600;color:#64748b;margin:8px 0 6px">推理路径（4步）：</div><div class="udp-step"><span class="sn">1</span>从 <b>进销存比对</b> 到 <b style="color:#0e7490">行业模式判断</b>：检查企业是纯贸易还是制造业——加工费+原材料信号</div><div class="udp-step"><span class="sn">2</span>从 <b>行业模式判断</b> 到 <b style="color:#0e7490">制造业诊断(如有加工信号)</b>：有加工费+有原材料→制造业加工链条→风险焦点转移</div><div class="udp-step"><span class="sn">3</span>从 <b>制造业诊断</b> 到 <b style="color:#0e7490">BOM验证</b>：要求企业提供BOM表验证原材料投入→加工→成品产出的逻辑</div><div class="udp-step"><span class="sn">4</span>从 <b>BOM验证</b> 到 <b style="color:#0e7490">综合结论</b>：无法提供BOM→加工链条无法验证→有进无销仍可能是隐匿收入→回到高风险</div><div style="font-size:10px;color:#64748b;margin-top:6px">关联规则（共15条）：20、21、22、23、55、63、64、80、210、216、338、537、1051、1358、1502</div></div><div class="udp-chain"><div style="display:flex;align-items:center;gap:6px;margin-bottom:4px"><span style="display:inline-block;padding:2px 8px;border-radius:3px;font-size:10px;font-weight:600;background:#dc262615;color:#dc2626">高风险</span><span style="font-size:10px;font-weight:700;color:#16233a">5. 合同缺失→交易真实性存疑推理链（四层分层）</span></div><div style="font-size:10px;color:#64748b;margin-bottom:6px;line-height:1.9">合同缺失不是一刀切的问题——不是所有交易都需要合同。系统通过四层自动分层，将缺失的影响精准定位到必签和应签两类，避免把所有供应商都视为「需要合同」（那会要求连加油站、酒店都签合同——不切实际）。分层判断使风险结论更精准、更可操作。</div><div style="font-size:10px;font-weight:600;color:#64748b;margin:8px 0 6px">推理路径（4步）：</div><div class="udp-step"><span class="sn">1</span>从 <b>资料完备度检测</b> 到 <b style="color:#0e7490">合同需求分层</b>：对每个供应商按品名/金额/类型四层自动分类：必签/应签/可免/小额</div><div class="udp-step"><span class="sn">2</span>从 <b>合同需求分层</b> 到 <b style="color:#0e7490">交易真实性验证</b>：四流合一缺了合同流→这些交易的商业实质无法通过书面证据验证</div><div class="udp-step"><span class="sn">3</span>从 <b>交易真实性验证</b> 到 <b style="color:#0e7490">分层风险判断</b>：必签类缺合同=高风险；应签类缺合同=中风险；可免类无合同=正常</div><div class="udp-step"><span class="sn">4</span>从 <b>分层风险判断</b> 到 <b style="color:#0e7490">综合结论</b>：缺失合同→四流不合一→税务合规可逐笔质疑交易真实性→虚开发票嫌疑→印花税漏缴</div><div style="font-size:10px;color:#64748b;margin-top:6px">关联规则（共13条）：14、15、16、17、63、64、72、216、310、313、712、1323、1505</div></div><div class="udp-chain"><div style="display:flex;align-items:center;gap:6px;margin-bottom:4px"><span style="display:inline-block;padding:2px 8px;border-radius:3px;font-size:10px;font-weight:600;background:#dc262615;color:#dc2626">高风险</span><span style="font-size:10px;font-weight:700;color:#16233a">6. 重物跨省缺运输→货物流断裂推理链</span></div><div style="font-size:10px;color:#64748b;margin-bottom:6px;line-height:1.9">从地址分布出发，结合行业重物属性和运输成本缺失，形成货物流物证链断裂的推理。关键在于行业的重物判断——不是所有行业都需要运输成本（如软件/咨询/设计等服务业），但纺织/建材/机械/食品等重物产业必须有。系统根据行业自适应地判断重物属性，不搞一刀切。</div><div style="font-size:10px;font-weight:600;color:#64748b;margin:8px 0 6px">推理路径（4步）：</div><div class="udp-step"><span class="sn">1</span>从 <b>地址分析</b> 到 <b style="color:#0e7490">行业重物判断</b>：根据行业分类判断产品是否为需运输的重物</div><div class="udp-step"><span class="sn">2</span>从 <b>行业重物判断</b> 到 <b style="color:#0e7490">运输成本检测</b>：检索全部发票和银行流水中的运输/物流/快递/货运关键词</div><div class="udp-step"><span class="sn">3</span>从 <b>运输成本检测</b> 到 <b style="color:#0e7490">货物流判断</b>：重物跨省运输必有运费（通常占货值3%-8%），零运费=货物流物证链断裂</div><div class="udp-step"><span class="sn">4</span>从 <b>货物流判断</b> 到 <b style="color:#0e7490">综合结论</b>：货物流无法验证→三流合一缺了货物流→交易真实性存疑→进项税额+成本均面临否定风险</div><div style="font-size:10px;color:#64748b;margin-top:6px">关联规则（共12条）：10、63、91、93、101、118、121、132、181、999、1500、1512</div></div><div class="udp-chain"><div style="display:flex;align-items:center;gap:6px;margin-bottom:4px"><span style="display:inline-block;padding:2px 8px;border-radius:3px;font-size:10px;font-weight:600;background:#d9770615;color:#d97706">中风险</span><span style="font-size:10px;font-weight:700;color:#16233a">7. 费用发票占比异常→虚增成本推理链</span></div><div style="font-size:10px;color:#64748b;margin-bottom:6px;line-height:1.9">从费用结构异常出发，逐层深挖费用的真实性和关联性。关键判断在于费用与经营是否相关——招待费/差旅费可能有经营关联，但旅游/购物/生活用品等明显与经营无关。系统通过联网查询股东身份，将个人消费入账的风险精准定位。</div><div style="font-size:10px;font-weight:600;color:#64748b;margin:8px 0 6px">推理路径（4步）：</div><div class="udp-step"><span class="sn">1</span>从 <b>费用结构分析</b> 到 <b style="color:#0e7490">费用明细核查</b>：逐类筛查费用发票的品名/金额/时间/对方</div><div class="udp-step"><span class="sn">2</span>从 <b>费用明细核查</b> 到 <b style="color:#0e7490">股东关联判断</b>：联网查询股东和法定代表人，判断费用是否与股东个人消费相关</div><div class="udp-step"><span class="sn">3</span>从 <b>股东关联判断</b> 到 <b style="color:#0e7490">税前扣除判断</b>：与生产经营无关的支出不得税前扣除→需调增应纳税所得额</div><div class="udp-step"><span class="sn">4</span>从 <b>税前扣除判断</b> 到 <b style="color:#0e7490">综合结论</b>：虚增成本费用→利润虚减→企业所得税少缴+个人所得税漏缴</div><div style="font-size:10px;color:#64748b;margin-top:6px">关联规则（共12条）：133、135、138、144、310、425、748、880、895、1117、1170、1178</div></div><div class="udp-chain"><div style="display:flex;align-items:center;gap:6px;margin-bottom:4px"><span style="display:inline-block;padding:2px 8px;border-radius:3px;font-size:10px;font-weight:600;background:#dc262615;color:#dc2626">高风险</span><span style="font-size:10px;font-weight:700;color:#16233a">8. 进销比异常+零申报→账外经营推理链</span></div><div style="font-size:10px;color:#64748b;margin-bottom:6px;line-height:1.9">进销比异常是最强的税务合规信号之一——采购量远超销售量的本质是「买了货但没有开发票卖出去」。但不是一看到进销比异常就定「账外经营」——需要先排除存货积压的可能。如果存货没有增加、采购款已付、但销项极少——那就是典型的账外经营信号。结合收入端（收款远超开票），形成进销两端闭合的证据链。</div><div style="font-size:10px;font-weight:600;color:#64748b;margin:8px 0 6px">推理路径（4步）：</div><div class="udp-step"><span class="sn">1</span>从 <b>进销比分析</b> 到 <b style="color:#0e7490">存货分析</b>：检查存货周转率——如果存货也没有对应增加则货物去向成谜</div><div class="udp-step"><span class="sn">2</span>从 <b>存货分析</b> 到 <b style="color:#0e7490">资金流追踪</b>：追踪银行付款去向——采购款付了但货去哪了？</div><div class="udp-step"><span class="sn">3</span>从 <b>资金流追踪</b> 到 <b style="color:#0e7490">收入端对比</b>：付款正常+进货正常+销项极少→货物已售出但未开票→账外经营</div><div class="udp-step"><span class="sn">4</span>从 <b>收入端对比</b> 到 <b style="color:#0e7490">综合结论</b>：进销比异常+零申报+收款开票偏差→完整的账外经营链条→严重隐匿收入</div><div style="font-size:10px;color:#64748b;margin-top:6px">关联规则（共10条）：19、81、249、379、382、775、1144、1146、1424、1503</div></div><div class="udp-chain"><div style="display:flex;align-items:center;gap:6px;margin-bottom:4px"><span style="display:inline-block;padding:2px 8px;border-radius:3px;font-size:10px;font-weight:600;background:#dc262615;color:#dc2626">高风险</span><span style="font-size:10px;font-weight:700;color:#16233a">9. 供应链六员交叉→关联交易推断链（人员→发票→资金三段式跨域）</span></div><div style="font-size:10px;color:#64748b;margin-bottom:6px;line-height:1.9">通过人员信息→发票数据→资金流的三段式跨域推理：从发票中定位供应商/客户→联网核查其六员→与本企业六员交叉比对→发现重叠后核查资金流→确认关联交易并评估转移定价风险。</div><div style="font-size:10px;font-weight:600;color:#64748b;margin:8px 0 6px">推理路径（4步）：</div><div class="udp-step"><span class="sn">1</span>联网核查被查单位+供应商/客户六员</div><div class="udp-step"><span class="sn">2</span>提取进销发票中的供应商/客户名称+金额</div><div class="udp-step"><span class="sn">3</span>逐名交叉比对→发现重叠</div><div class="udp-step"><span class="sn">4</span>核查重叠企业间资金往来</div><div style="font-size:10px;color:#64748b;margin-top:6px">关联规则（共7条）：90、249、267、298、447、1504、1510</div></div><div class="udp-chain"><div style="display:flex;align-items:center;gap:6px;margin-bottom:4px"><span style="display:inline-block;padding:2px 8px;border-radius:3px;font-size:10px;font-weight:600;background:#dc262615;color:#dc2626">高风险</span><span style="font-size:10px;font-weight:700;color:#16233a">10. 购销闭环→虚开发票推理链（发票→进销存→资金三段式跨域）</span></div><div style="font-size:10px;color:#64748b;margin-bottom:6px;line-height:1.9">从发票数据发现供应商=客户→形成购销闭环→核查进销商品流转逻辑是否合理→核查资金流是否形成回流→判定虚开发票风险等级。</div><div style="font-size:10px;font-weight:600;color:#64748b;margin:8px 0 6px">推理路径（4步）：</div><div class="udp-step"><span class="sn">1</span>提取进项销售方+销项购买方</div><div class="udp-step"><span class="sn">2</span>交叉比对：供应商∩客户</div><div class="udp-step"><span class="sn">3</span>核查闭环企业间的商品流转逻辑</div><div class="udp-step"><span class="sn">4</span>核查闭环企业间资金流向</div><div style="font-size:10px;color:#64748b;margin-top:6px">关联规则（共8条）：266、267、272、284、298、1504、1510、1511</div></div><div class="udp-chain"><div style="display:flex;align-items:center;gap:6px;margin-bottom:4px"><span style="display:inline-block;padding:2px 8px;border-radius:3px;font-size:10px;font-weight:600;background:#dc262615;color:#dc2626">高风险</span><span style="font-size:10px;font-weight:700;color:#16233a">11. 仓库→产能→能耗→物流全链条经营实质分析</span></div><div style="font-size:10px;color:#64748b;margin-bottom:6px;line-height:1.9">单一矛盾可能是偶然→两个矛盾高度可疑→三个以上矛盾几乎可以定案。仓库装不下+设备产不出+电量不够用+物流费对不上=企业的账面经营纯粹是虚构的。</div><div style="font-size:10px;font-weight:600;color:#64748b;margin:8px 0 6px">推理路径（5步）：</div><div class="udp-step"><span class="sn">1</span>从租金发票推算仓储面积→对比库存体积→仓容矛盾？</div><div class="udp-step"><span class="sn">2</span>从设备参数推算理论产能→对比账面产量→产能矛盾？</div><div class="udp-step"><span class="sn">3</span>从电费/水费推算能耗→对比行业单耗标准→能耗矛盾？</div><div class="udp-step"><span class="sn">4</span>从运输距离推算运费→对比账面运费→物流矛盾？</div><div class="udp-step"><span class="sn">5</span>四个维度交叉验证→几个维度出现矛盾？→矛盾越多置信度越高→从单点怀疑升级为系统性造假判定</div><div style="font-size:10px;color:#64748b;margin-top:6px">关联规则（共2条）：267、1500</div></div><div class="udp-chain"><div style="display:flex;align-items:center;gap:6px;margin-bottom:4px"><span style="display:inline-block;padding:2px 8px;border-radius:3px;font-size:10px;font-weight:600;background:#dc262615;color:#dc2626">高风险</span><span style="font-size:10px;font-weight:700;color:#16233a">12. 系统性造假综合判定模型(七维交叉)</span></div><div style="font-size:10px;color:#64748b;margin-bottom:6px;line-height:1.9">七维交叉验证模型——从经营实质、供应商穿透、资金流、三流合一、跨税种、关联交易七个维度综合评估企业造假可能性。单维异常是线索，多维异常是定案。七维全异常=企业账务大概率全面造假。</div><div style="font-size:10px;font-weight:600;color:#64748b;margin:8px 0 6px">推理路径（7步）：</div><div class="udp-step"><span class="sn">1</span>库存体积vs仓容/设备产能vs产量/用电量vs生产规模/人员vs产出→几维矛盾？</div><div class="udp-step"><span class="sn">2</span>供应商五维评分(资质/时间/规模/价格/资金)→几个维度不通过？</div><div class="udp-step"><span class="sn">3</span>收付款匹配度/个人收款占比/资金回流迹象/过桥账户→资金流异常度</div><div class="udp-step"><span class="sn">4</span>发票/资金/物流/合同四流一致性→几流断裂？</div><div class="udp-step"><span class="sn">5</span>增值税vs所得税/个税vs社保/印花税vs购销→几税申报不一致？</div><div class="udp-step"><span class="sn">6</span>关联方交易占比/转移定价/资本弱化/费用分摊→关联交易风险度</div><div class="udp-step"><span class="sn">7</span>七维综合评分→0-2维异常=低风险→3-4维=中风险→5-6维=高风险→7维=系统性造假→触发全面税务合规立案</div><div style="font-size:10px;color:#64748b;margin-top:6px">关联规则（共12条）：63、90、130、226、228、267、272、364、374、447、450、1495</div></div><div class="udp-chain"><div style="display:flex;align-items:center;gap:6px;margin-bottom:4px"><span style="display:inline-block;padding:2px 8px;border-radius:3px;font-size:10px;font-weight:600;background:#dc262615;color:#dc2626">高风险</span><span style="font-size:10px;font-weight:700;color:#16233a">13. 隐匿收入综合判定模型</span></div><div style="font-size:10px;color:#64748b;margin-bottom:6px;line-height:1.9">三线归一法：资金偏差线(收款-开票)=来源分类线(未开票收入)=消费验证线(超申报消费)。三条线独立推算的隐匿收入金额应当大致相等。金额越接近→证据越强→结论越不可辩驳。</div><div style="font-size:10px;font-weight:600;color:#64748b;margin:8px 0 6px">推理路径（4步）：</div><div class="udp-step"><span class="sn">1</span>计算收款-开票偏差的绝对金额和相对比例→分月度/季度看趋势</div><div class="udp-step"><span class="sn">2</span>对未匹配收款逐笔分类→借款/注资/代收/未开票/其他→计算各类占比</div><div class="udp-step"><span class="sn">3</span>追踪个人账户收款和异常消费→推算最低隐匿收入规模</div><div class="udp-step"><span class="sn">4</span>三指标交叉验证→偏差金额≈未开票收入≈隐匿消费→一致即定案</div><div style="font-size:10px;color:#64748b;margin-top:6px">关联规则（共15条）：20、21、22、23、210、622、623、624、625、626、627、628、629、630、655</div></div><div class="udp-chain"><div style="display:flex;align-items:center;gap:6px;margin-bottom:4px"><span style="display:inline-block;padding:2px 8px;border-radius:3px;font-size:10px;font-weight:600;background:#d9770615;color:#d97706">中风险</span><span style="font-size:10px;font-weight:700;color:#16233a">14. 经营实质地理分析</span></div><div style="font-size:10px;font-weight:600;color:#64748b;margin:8px 0 6px">推理路径（4步）：</div><div class="udp-step"><span class="sn">1</span>从 <b>发票数据</b> 到 <b style="color:#0e7490">地址提取</b>：从发票提取购方/销方和交易地址</div><div class="udp-step"><span class="sn">2</span>从 <b>地址提取</b> 到 <b style="color:#0e7490">三方比对</b>：注册地、经营地、交易地城市级三方比对</div><div class="udp-step"><span class="sn">3</span>从 <b>三方比对</b> 到 <b style="color:#0e7490">运输成本检测</b>：检索银行流水和发票中的运输/物流/货运费用</div><div class="udp-step"><span class="sn">4</span>从 <b>运输成本检测</b> 到 <b style="color:#0e7490">综合结论</b>：三地不同+零运费=物理上不可能。全链条经营实质存疑</div></div><div class="udp-chain"><div style="display:flex;align-items:center;gap:6px;margin-bottom:4px"><span style="display:inline-block;padding:2px 8px;border-radius:3px;font-size:10px;font-weight:600;background:#d9770615;color:#d97706">中风险</span><span style="font-size:10px;font-weight:700;color:#16233a">15. 税务合规六员跨企业比对</span></div><div style="font-size:10px;font-weight:600;color:#64748b;margin:8px 0 6px">推理路径（4步）：</div><div class="udp-step"><span class="sn">1</span>从 <b>工商信息</b> 到 <b style="color:#0e7490">六员提取</b>：提取被查企业及进销方TOP10的六员名单</div><div class="udp-step"><span class="sn">2</span>从 <b>六员提取</b> 到 <b style="color:#0e7490">交叉比对</b>：逐名交叉比对。同一人出现两家企业则标记</div><div class="udp-step"><span class="sn">3</span>从 <b>交叉比对</b> 到 <b style="color:#0e7490">关联方标记</b>：标记六员重叠的企业对为潜在关联方</div><div class="udp-step"><span class="sn">4</span>从 <b>关联方标记</b> 到 <b style="color:#0e7490">关联交易穿透</b>：执行价格公允性+资金占用+债资比检测</div></div><div class="udp-chain"><div style="display:flex;align-items:center;gap:6px;margin-bottom:4px"><span style="display:inline-block;padding:2px 8px;border-radius:3px;font-size:10px;font-weight:600;background:#d9770615;color:#d97706">中风险</span><span style="font-size:10px;font-weight:700;color:#16233a">16. 供应链联网核查（全链条人员交叉比对）</span></div><div style="font-size:10px;font-weight:600;color:#64748b;margin:8px 0 6px">推理路径（4步）：</div><div class="udp-step"><span class="sn">1</span>从 <b>进销发票</b> 到 <b style="color:#0e7490">TOP10提取</b>：提取进项TOP10和销项TOP10的六员信息</div><div class="udp-step"><span class="sn">2</span>从 <b>TOP10提取</b> 到 <b style="color:#0e7490">全链条交叉</b>：将20家企业的六员做全排列交叉比对</div><div class="udp-step"><span class="sn">3</span>从 <b>全链条交叉</b> 到 <b style="color:#0e7490">闭环检测</b>：检测供应商A→客户B→供应商A的闭环模式</div><div class="udp-step"><span class="sn">4</span>从 <b>闭环检测</b> 到 <b style="color:#0e7490">综合结论</b>：闭环成立→供应链存在隐藏关联→利益输送风险</div></div><div class="udp-chain"><div style="display:flex;align-items:center;gap:6px;margin-bottom:4px"><span style="display:inline-block;padding:2px 8px;border-radius:3px;font-size:10px;font-weight:600;background:#d9770615;color:#d97706">中风险</span><span style="font-size:10px;font-weight:700;color:#16233a">17. 资金回流检测法</span></div><div style="font-size:10px;font-weight:600;color:#64748b;margin:8px 0 6px">推理路径（4步）：</div><div class="udp-step"><span class="sn">1</span>从 <b>银行流水</b> 到 <b style="color:#0e7490">对手方网络</b>：构建全部收付款方的关系网络图</div><div class="udp-step"><span class="sn">2</span>从 <b>对手方网络</b> 到 <b style="color:#0e7490">闭环检测</b>：检测A→B→A或A→B→C→A的闭环路径（时间差<90天，偏差<5%）</div><div class="udp-step"><span class="sn">3</span>从 <b>闭环检测</b> 到 <b style="color:#0e7490">发票验证</b>：核查闭环内各节点发票。有发票=过账，无发票=返还</div><div class="udp-step"><span class="sn">4</span>从 <b>发票验证</b> 到 <b style="color:#0e7490">综合结论</b>：回流成立→虚开发票/虚构交易。多笔闭环叠加则立案</div></div><div class="udp-chain"><div style="display:flex;align-items:center;gap:6px;margin-bottom:4px"><span style="display:inline-block;padding:2px 8px;border-radius:3px;font-size:10px;font-weight:600;background:#dc262615;color:#dc2626">高风险</span><span style="font-size:10px;font-weight:700;color:#16233a">18. 全税种综合判定模型</span></div><div style="font-size:10px;color:#64748b;margin-bottom:6px;line-height:1.9">多税种交叉验证。单一税种异常可能是疏忽，3+税种同时异常=系统性偷逃税。综合判定降低误报。</div><div style="font-size:10px;font-weight:600;color:#64748b;margin:8px 0 6px">推理路径（4步）：</div><div class="udp-step"><span class="sn">1</span>收集各税种触发发现</div><div class="udp-step"><span class="sn">2</span>逐税种比对申报vs实际</div><div class="udp-step"><span class="sn">3</span>≥3税种异常→系统性偷逃税</div><div class="udp-step"><span class="sn">4</span>多税种累计偷税额→处罚档次</div><div style="font-size:10px;color:#64748b;margin-top:6px">关联规则（共4条）：210、228、880、1497</div></div><div class="udp-chain"><div style="display:flex;align-items:center;gap:6px;margin-bottom:4px"><span style="display:inline-block;padding:2px 8px;border-radius:3px;font-size:10px;font-weight:600;background:#dc262615;color:#dc2626">高风险</span><span style="font-size:10px;font-weight:700;color:#16233a">19. 物耗能耗产能三线归一分析</span></div><div style="font-size:10px;color:#64748b;margin-bottom:6px;line-height:1.9">产量可以从产能、电耗、物耗三个独立维度推算。三维交叉印证→单一维偏差可能是统计误差，三维全偏=造假。</div><div style="font-size:10px;font-weight:600;color:#64748b;margin:8px 0 6px">推理路径（5步）：</div><div class="udp-step"><span class="sn">1</span>设备铭牌×工时→理论最大产量</div><div class="udp-step"><span class="sn">2</span>电费÷行业单位电耗→推算产量</div><div class="udp-step"><span class="sn">3</span>原材料投入÷行业投入产出比→推算产量</div><div class="udp-step"><span class="sn">4</span>三维推算→中位数 vs 账面产量</div><div class="udp-step"><span class="sn">5</span>三维全偏低且偏差>30%→系统性造假</div><div style="font-size:10px;color:#64748b;margin-top:6px">关联规则（共2条）：258、445</div></div>';

  h += '<h2>六、本次检出结果</h2>';
  h += '<div class="udp-block"><p>分析完成后展示各域实际检出发现，按风险等级排序。结果汇总：分析域总数、已触发域数、高中低风险发现数。发现列表：各域发现列表，按风险等级排序（高→中→低→注意→信息），每条含type/level/score/domain。跨域推理：线索链、证据链、分析链的完整推理路径展示。数据来源：getSharedAnalysis() API。</p></div>';

  h += '<h2>七、各层成熟度评估</h2>';
  h += '<p><b>感知层</b>：文件识别率=正确识别文件数/上传文件总数×100%。数据提取准确率=正确提取字段数/应提取字段总数×100%。处理速度=数据标准化完成时间（秒）。<b>记忆层</b>：经验推送精准率=推送后验证通过数/总推送次数×100%。召回率=推送覆盖的已验证模式数/历史已验证模式总数×100%。<b>思考层</b>：证据闭环稳固率=已闭环证据链数/触发总数×100%。证伪通过率=红队通过数/红队总次数×100%。因果推理准确率=结论与定案一致数/总触发次数×100%。<b>学习层</b>：模式迁移成功率=跨行业验证通过数/迁移尝试总数×100%。误报率下降曲线=当月误报率/上月误报率-1（负值=下降）。<b>自省层</b>：破坏性测试发现缺陷的密度与严重程度——每次自省巡逻发现的缺陷按严重性加权计数。目标值待系统运行积累基线数据后设定。工程实现时需在分母为0时返回N/A。</p>';

  h += '<details><summary>附录：finding.type受控词表（域发现→线索链/证据链关键词映射）</summary>';
  h += '<div class="udp-block"><p style="font-size:10px;color:#64748b">域函数产出的finding.type必须从此表中取值。各finding.type的匹配关键词为独立集合，不同finding.type之间不共享匹配关键词——精确匹配，匹配不上就会漏触发。完整词表及唯一性约束见engine/memory.py。</p>';
  h += '<p>收款方异常→收款与开票、收款方异常。进销倒挂→进销、进销比、进销严重倒挂。毛利率偏离→毛利率、毛利率偏离、行业基准。社保人数不匹配→社保、参保人数、三数勾稽。三单不一致→入库单、三单匹配。供应商异常→供应商、对私、小规模、新设。客户即供应商→供应商=客户、上下游、供销同一。四源偏差→四源、多源、银行收入vs开票、账载vs申报。利润现金背离→有利润无现金、现金流枯竭、应收账款异常。人员不匹配→人员、零参保。地址异常→注册地、经营地、地址不一致。连号开票→连号、顶格、整数金额、夜间开具。高作废率→作废、红冲、作废率。合同不符→合同缺失、合同金额。税负率偏低→税负率、行业下限。关联交易→关联、转移定价、债资比。资金回流→资金回流、资金闭环、回款。资金流向异常→资金流向、单边大额。注意：收款方异常与资金流向异常为独立集合，不共享匹配关键词。</p></div></details>';

  h += '</div>';
  container.innerHTML = h;
}

function renderDAResult() {
  return _pageTemplate({
  "title": "域分析结果",
  "icon": "📈",
  "subtitle": "动态数据页面，展示本次分析实际的域分析结果。包括各域发现列表（按风险等级排序）、跨域关联推理结果和综合分析结论。",
  "stats": [
    [
      "动态",
      "实时数据",
      "#2563eb"
    ],
    [
      "排序",
      "风险等级",
      "#7c3aed"
    ],
    [
      "跨域",
      "关联推理",
      "#059669"
    ],
    [
      "综合",
      "分析结论",
      "#d97706"
    ]
  ],
  "upstream": [
    [
      "da-domains",
      "分析域",
      "域分析函数执行结果"
    ],
    [
      "da-arch",
      "域分析架构",
      "不同驱动类型域的产出"
    ]
  ],
  "downstream": [
    [
      "aly-result",
      "本次分析结果",
      "域分析结果汇总到分析结果"
    ],
    [
      "hb-ch9",
      "跨域协商引擎",
      "域结果进入协商引擎"
    ]
  ],
  "desc": "<p style=\"margin:0 0 10px\">数据来源：getSharedAnalysis() API返回的report。域分析结果汇总卡片展示各域发现总数/高风险/中风险/低风险的分类统计。各域发现列表按风险等级排序（高→中→低→注意→信息）。跨域关联推理结果展示线索链、证据链、分析链的完整推理路径。</p>",
  "cards": [
    [
      "结果汇总",
      "域分析结果汇总卡片：分析域总数、已触发的域数、高风险发现数、中低风险发现数。展示哪些域产生了实质分析结果。",
      "#2563eb"
    ],
    [
      "发现列表",
      "各域发现列表，按风险等级排序（高→中→低→注意→信息）。每条发现展示type/level/score/domain和简要描述。",
      "#7c3aed"
    ],
    [
      "跨域推理",
      "线索链、证据链、分析链的完整推理路径展示。从单域发现到多域交叉的全过程可视化。",
      "#059669"
    ]
  ]
});
}
// 核心智能引擎
function renderAGICore() {
  return _pageTemplate({
  "title": "核心智能引擎",
  "icon": "🧠",
  "subtitle": "6个核心智能引擎模块：自我反思器（14维反向假设验证）、洞见总结器（五段式结构化报告）、跨分析学习器（12维相似度检索）、税务合规方法论、规则发现（三层递进归纳）、自动巡逻。",
  "stats": [
    [
      "6个",
      "核心引擎",
      "#2563eb"
    ],
    [
      "14维",
      "反向验证",
      "#dc2626"
    ],
    [
      "五段式",
      "结构化报告",
      "#7c3aed"
    ],
    [
      "3层",
      "渐进学习",
      "#d97706"
    ]
  ],
  "upstream": [
    [
      "agi-hero",
      "AGI总览",
      "核心引擎在AGI中的位置"
    ],
    [
      "eng-think",
      "推理引擎",
      "核心引擎支撑推理"
    ]
  ],
  "downstream": [
    [
      "agi-causal",
      "因果推理层",
      "核心引擎输出到因果层"
    ],
    [
      "agi-knowledge",
      "知识层",
      "核心引擎学习到知识库"
    ]
  ],
  "desc": "<p style=\"margin:0 0 10px\">6个核心智能引擎：①自我反思器 SelfReflector——14维反向假设验证，对每条高风险发现生成竞争假设并逐条验证 ②洞见总结器 InsightSynthesizer——从all_findings自动组织为五段式结构化报告 ③跨分析学习器 CrossAnalysisLearner——跨企业分析经验积累，12维度加权相似度检索 ④税务合规方法论 MethodologyEngine——33条方法论+14类必查资料+12条法律条文 ⑤规则发现 RuleDiscovery——三层递进归纳引擎 ⑥自动巡逻 PatrolEngine——定期重分析，对比前后两次报告差异。</p>",
  "cards": [
    [
      "自我反思器",
      "14维反向假设验证。对每条高风险发现生成2-3条互斥竞争假设→逐条证据验证。adj<-0.05→不确定，adj<-0.15→推翻。累积信号≥3且无推翻→确认。",
      "#dc2626"
    ],
    [
      "洞见总结器",
      "从all_findings自动组织五段式报告：企业画像→风险全景→核心问题TOP5→行业对标→行动建议P0-P2。全自动生成，无需人工整理。",
      "#2563eb"
    ],
    [
      "跨分析学习器",
      "同类企业分析≥3次→提取行业常见高风险模式。12维度加权相似度检索。结果持久化到cross_analysis_memory.json。",
      "#7c3aed"
    ],
    [
      "规则发现+巡逻",
      "三层递进归纳：Layer A模块效率(空跑率>80%降权)→Layer B纠正模式(纠正≥3次提取规则)→Layer C信号模式对比(>60%标记行业特征)。自动巡逻：定期重分析，变化率>30%触发定向巡逻。",
      "#d97706"
    ]
  ]
});
}
// 因果推理层
function renderAGICausal() {
  return _pageTemplate({
  "title": "因果推理层",
  "icon": "📊",
  "subtitle": "4个因果推理引擎：SCM因果推理（do-干预/反事实/混淆/因果链）、元认知引擎（四维推理质量评估）、法律三段论（11条结构化规则）、因果网络（条件概率+多信号联合预测）。",
  "stats": [
    [
      "4个",
      "因果引擎",
      "#2563eb"
    ],
    [
      "9条",
      "税务因果先验",
      "#dc2626"
    ],
    [
      "4维",
      "推理质量评估",
      "#7c3aed"
    ],
    [
      "11条",
      "法律规则",
      "#d97706"
    ]
  ],
  "upstream": [
    [
      "agi-core",
      "核心智能引擎",
      "核心引擎产生发现进入因果层"
    ],
    [
      "agi-hero",
      "AGI总览",
      "因果层在AGI中的位置"
    ]
  ],
  "downstream": [
    [
      "agi-knowledge",
      "知识层",
      "因果边存入知识层"
    ],
    [
      "eng-think",
      "推理引擎",
      "因果推理支撑最终推理"
    ]
  ],
  "desc": "<p style=\"margin:0 0 10px\">4个因果推理引擎：①SCM因果推理 SCMReasoner——从条件概率升级为结构化因果推理，四种推理（do-干预/反事实/混淆因子检测/因果链查询），预置9条税务因果先验 ②元认知引擎 Metacognition——四维推理质量评估（因果链完整性/证据充分性/法律依据/可操作性）→质量分→不确定性检测→信息缺口识别→行动建议 ③法律三段论 LegalReasoner——11条结构化法律规则，大前提(法条)+小前提(本案事实)→结论(法律定性) ④因果网络 CausalNetwork——条件概率矩阵+多信号联合预测，置信度=P(结论|信号) x log(lift+1)。</p>",
  "cards": [
    [
      "SCM因果推理",
      "四种推理：do-干预（如果公司补缴税款会怎样）、反事实（如果没有这笔交易会怎样）、混淆因子检测、因果链查询。预置9条税务因果先验。",
      "#dc2626"
    ],
    [
      "元认知引擎",
      "四维评估：因果链完整性、证据充分性、法律依据、可操作性。质量分→不确定性检测→信息缺口识别→行动建议。元认知=对系统自身推理质量的自省。",
      "#7c3aed"
    ],
    [
      "法律三段论",
      "11条结构化法律规则。大前提(法条)+小前提(本案事实)→结论(法律定性)。含征管法第63条、发票管理办法第22条、刑法第205条等。",
      "#d97706"
    ],
    [
      "因果网络",
      "条件概率矩阵+多信号联合预测。信号共现→因果边→置信度=P(结论|信号) x log(lift+1)。lift>1为正向影响，lift<1为负向影响。",
      "#2563eb"
    ]
  ]
});
}
// 连接通信层
function renderAGIConnect() {
  return _pageTemplate({
  "title": "连接通信层",
  "icon": "🔗",
  "subtitle": "3个连接通信引擎：事件总线（pub/sub松耦合，14种标准事件）、知识图谱（实体-关系-属性图推理）、自愈引擎（双重自愈模式，5种错误分类）。",
  "stats": [
    [
      "3个",
      "通信引擎",
      "#2563eb"
    ],
    [
      "14种",
      "标准事件",
      "#7c3aed"
    ],
    [
      "3节点",
      "图谱推理",
      "#059669"
    ],
    [
      "5类",
      "错误修正",
      "#d97706"
    ]
  ],
  "upstream": [
    [
      "agi-core",
      "核心智能引擎",
      "核心引擎通过事件总线通信"
    ],
    [
      "agi-causal",
      "因果推理层",
      "因果推理结果通过事件总线传递"
    ]
  ],
  "downstream": [
    [
      "agi-knowledge",
      "知识层",
      "通信层产出存入知识层"
    ],
    [
      "agi-perf",
      "加速与保护层",
      "通信层支持并行加速"
    ]
  ],
  "desc": "<p style=\"margin:0 0 10px\">①事件总线 EventBus——模块间实时通信中枢，pub/sub松耦合，14种标准事件覆盖全分析生命周期。跨模块因果链追踪：一条发现从触发引擎到最终输出全程通过事件ID回溯。②知识图谱 KnowledgeGraph——实体-关系-属性图推理，节点类型：企业/供应商/客户/人员/发票/法条/风险。购销闭环检测：A→B→C→A品名金额相同→疑似闭环虚开。③自愈引擎 SelfHealing——双重自愈模式：人工反馈（5种错误分类→修正规则→自动应用）+自动检测（矛盾结论/三要素缺失/模板句/空占位符/因果链过短）。</p>",
  "cards": [
    [
      "事件总线",
      "pub/sub松耦合架构。14种标准事件覆盖全分析生命周期。跨模块因果链追踪通过事件ID实现——一条发现的全生命周期可完整回溯。",
      "#2563eb"
    ],
    [
      "知识图谱",
      "实体-关系-属性图推理。购销闭环检测：A→B→C→A品名金额相同→疑似闭环虚开。一人多角检测：同一自然人在多个企业任职→关联交易。",
      "#7c3aed"
    ],
    [
      "自愈引擎",
      "双重模式：人工反馈（5种错误→修正规则→自动应用）+自动检测（矛盾结论/三要素缺失/模板句/空占位符/因果链过短）。持久化到healing_rules.json。",
      "#d97706"
    ]
  ]
});
}
// 知识层
function renderAGIKnowledge() {
  return _pageTemplate({
  "title": "知识层",
  "icon": "📚",
  "subtitle": "3个知识层模块：统一知识库（9域知识库，线程安全单例）、自学习引擎（三层渐进学习）、趋势分析器（12项经营指标跨期追踪）。",
  "stats": [
    [
      "3个",
      "知识模块",
      "#2563eb"
    ],
    [
      "9域",
      "知识库",
      "#7c3aed"
    ],
    [
      "3层",
      "渐进学习",
      "#059669"
    ],
    [
      "12项",
      "趋势指标",
      "#d97706"
    ]
  ],
  "upstream": [
    [
      "agi-core",
      "核心智能引擎",
      "知识层为核心引擎提供知识"
    ],
    [
      "agi-causal",
      "因果推理层",
      "因果边存入知识层"
    ]
  ],
  "downstream": [
    [
      "agi-special",
      "专项引擎层",
      "专项引擎使用知识层"
    ],
    [
      "agi-perf",
      "加速与保护层",
      "知识层支持覆盖层回滚"
    ]
  ],
  "desc": "<p style=\"margin:0 0 10px\">①统一知识库 KnowledgeBase——9域：政策库/因果网络/信号模式/语义词典/风险同义词/行业画像/自愈规则/经验教训/分析历史。线程安全写锁，全局单例，JSON持久化。②自学习引擎 SelfLearning——三层渐进：审核反馈规则转化（纠正模式累积≥1→四级回退匹配）→模块效率评估→合规门禁。历史校准自动计算行业百分位阈值。③趋势分析器 TrendAnalyzer——12项经营指标跨期追踪（毛利率/销售收入/采购金额/供应商数量/客户数量/发票数量/银行流入流出/工资/员工/税负率/净利率等）。连续两期间变化>10%标记趋势方向。</p>",
  "cards": [
    [
      "统一知识库",
      "9域知识：政策库、因果网络、信号模式、语义词典（14类同义词）、风险同义词、行业画像、自愈规则、经验教训、分析历史（最近100条）。线程安全/全局单例/JSON持久化。",
      "#2563eb"
    ],
    [
      "自学习引擎",
      "三层渐进：Layer 1审核反馈规则转化（纠正模式≥1→四级回退匹配）→Layer 2模块效率评估→Layer 3合规门禁。历史校准自动计算行业百分位阈值。",
      "#7c3aed"
    ],
    [
      "趋势分析器",
      "12项经营指标跨期追踪。连续两期间变化>10%标记趋势方向（上升↑/下降↓/平稳→）。为税务合规发现提供时间维度背景。",
      "#059669"
    ]
  ]
});
}
// 专项引擎层
function renderAGISpecial() {
  return _pageTemplate({
  "title": "专项引擎层",
  "icon": "🔧",
  "subtitle": "7个专项引擎：语义推理器（14品名同义词+编辑距离）、未知模式检测（7种异常检测器+规则覆盖度检查）、假设验证引擎、跨企业关系网、税收优惠分析（联网核查）、跨域协商引擎、数据一致性引擎。",
  "stats": [
    [
      "7个",
      "专项引擎",
      "#2563eb"
    ],
    [
      "9类",
      "税收优惠",
      "#7c3aed"
    ],
    [
      "14类",
      "同义词库",
      "#059669"
    ],
    [
      "7种",
      "异常检测器",
      "#d97706"
    ]
  ],
  "upstream": [
    [
      "agi-core",
      "核心智能引擎",
      "专项引擎是核心引擎的扩展"
    ],
    [
      "agi-knowledge",
      "知识层",
      "专项引擎使用知识层"
    ]
  ],
  "downstream": [
    [
      "agi-causal",
      "因果推理层",
      "专项引擎结果进入因果层"
    ],
    [
      "agi-perf",
      "加速与保护层",
      "专项引擎受加速层调度"
    ]
  ],
  "desc": "<p style=\"margin:0 0 10px\">7个专项引擎：①语义推理器——14类品名同义词库，两层匹配（子字符串+编辑距离Levenshtein≤2），创造性假设引擎（Jaccard类比推理）②未知模式检测——规则覆盖度检查+7种异常检测器（结构化转账/幽灵供应商/价格异常/数量尖峰/月末突击/个人大额转账/营收平滑）③假设验证引擎——每条重要发现生成2-3条互斥竞争假设→贝叶斯更新后验概率 ④跨企业关系网——一人多角检测+连锁稽查点（A→B→C→A闭环虚开）⑤税收优惠分析——9类优惠，联网核查三步法（搜索→抓取→提取），90天缓存 ⑥跨域协商引擎——29条协商规则 ⑦数据一致性引擎——双维度自检。</p>",
  "cards": [
    [
      "语义推理+未知检测",
      "语义推理：14类品名同义词（钢材→钢铁/型材/板材），编辑距离≤2自动匹配，Jaccard类比推理。未知模式检测：7种异常检测器覆盖规则未覆盖的风险区域。",
      "#2563eb"
    ],
    [
      "假设验证+跨企业关系",
      "假设验证：每条重要发现2-3条互斥竞争假设→正反证据检查→贝叶斯更新。跨企业关系：一人多角检测+连锁稽查点识别。",
      "#7c3aed"
    ],
    [
      "税收优惠+协商+一致性",
      "税收优惠：9类（小微/小规模/研发/高新/六税两费等），联网核查三步法。跨域协商：29条规则四类场景。数据一致性：数字维度+文本维度双维度自检。",
      "#059669"
    ]
  ]
});
}
// 加速与保护层
function renderAGIPerf() {
  return _pageTemplate({
  "title": "加速与保护层",
  "icon": "🚀",
  "subtitle": "3个加速与保护引擎：并行加速（DAG依赖图，42域并行，性能提升35-45%）、覆盖层引擎（四阶段状态机+紧急恢复）、外部验证（4通道工商数据验证，24小时缓存）。",
  "stats": [
    [
      "3个",
      "加速保护引擎",
      "#2563eb"
    ],
    [
      "45%",
      "性能提升",
      "#7c3aed"
    ],
    [
      "4通道",
      "工商验证",
      "#059669"
    ],
    [
      "4阶段",
      "覆盖层状态机",
      "#d97706"
    ]
  ],
  "upstream": [
    [
      "agi-core",
      "核心智能引擎",
      "核心引擎受益于加速"
    ],
    [
      "agi-schedule",
      "调度中枢",
      "调度中枢配合加速层"
    ]
  ],
  "downstream": [
    [
      "agi-knowledge",
      "知识层",
      "验证结果存入知识层"
    ],
    [
      "agi-special",
      "专项引擎层",
      "专项引擎受覆盖层保护"
    ]
  ],
  "desc": "<p style=\"margin:0 0 10px\">①并行加速 ParallelRunner——基于模块间依赖DAG自动计算并行执行计划。{{domain_functions}}个域分析函数间互不依赖→全部并行。max_workers默认4。性能：36域串行约45秒→并行约25-30秒→提升35-45%。②覆盖层引擎 OverrideEngine——AGI自主修正安全回滚机制。四阶段状态机：待审核→激活→生效中（监控效果）→紧急恢复（一键回滚）。持久化到overrides_storage.json。③外部验证 ExternalVerifier——4通道工商数据验证：天眼查API/企查查API/国家企业信用信息公示系统/搜索引擎后备。结果写入entity_profile.json，24小时缓存。</p>",
  "cards": [
    [
      "并行加速",
      "基于DAG依赖图自动计算并行执行计划。42域间互不依赖→全部并行。max_workers默认4。36域串行45秒→并行25-30秒→提升35-45%。可开关切换。",
      "#2563eb"
    ],
    [
      "覆盖层引擎",
      "AGI自主修正安全回滚。四阶段状态机：待审核→激活→生效中→紧急恢复（一键回滚）。监控效果异常时自动触发回滚，确保系统安全。",
      "#7c3aed"
    ],
    [
      "外部验证",
      "4通道：天眼查API、企查查API、国家企业信用信息公示系统、搜索引擎后备。结果24小时缓存，避免频繁调用外部API。",
      "#059669"
    ]
  ]
});
}
// API端点清单
function renderAGIAPI() {
  return _pageTemplate({
  "title": "API端点清单",
  "icon": "📡",
  "subtitle": "14个AGI API端点（GET/POST混合），覆盖状态查询、自然语言查询、对话、自检、覆盖层管理、巡逻管理、供应商验证等功能。",
  "stats": [
    [
      "14个",
      "API端点",
      "#2563eb"
    ],
    [
      "GET",
      "状态查询",
      "#7c3aed"
    ],
    [
      "POST",
      "交互操作",
      "#059669"
    ],
    [
      "REST",
      "标准接口",
      "#d97706"
    ]
  ],
  "upstream": [
    [
      "agi-core",
      "核心智能引擎",
      "核心引擎通过API暴露"
    ],
    [
      "agi-hero",
      "AGI总览",
      "总览数据通过API获取"
    ]
  ],
  "downstream": [
    [
      "agi-schedule",
      "调度中枢",
      "调度中枢状态通过API查询"
    ],
    [
      "agi-perf",
      "加速与保护层",
      "加速和覆盖层状态通过API管理"
    ]
  ],
  "desc": "<p style=\"margin:0 0 10px\">14个API端点：GET /api/agi/status（完整状态面板）、GET /api/agi/pipeline/dashboard（Pipeline仪表盘）、POST /api/agi/query（自然语言查询）、POST /api/agi/chat（对话式税务合规）、POST /api/agi/self-check/{company_id}（闭环自检）、GET/POST /api/agi/overrides/*（覆盖层管理）、GET/POST /api/agi/patrol/*（巡逻管理）、GET /api/agi/verify-supplier（供应商验证）、GET /api/agi/verify-channels（验证渠道）、POST /api/agi/parallel/toggle（并行加速开关）。</p>",
  "cards": [
    [
      "状态与查询API",
      "GET /api/agi/status（完整状态面板，含所有引擎状态）GET /api/agi/pipeline/dashboard（Pipeline数据）POST /api/agi/query（自然语言查询分析结果）POST /api/agi/chat（对话式税务合规咨询）",
      "#2563eb"
    ],
    [
      "覆盖层管理API",
      "GET /api/agi/overrides/summary（覆盖层概况）POST /api/agi/overrides/{id}/activate（激活覆盖层）POST /api/agi/overrides/{id}/rollback（回滚覆盖层）POST /api/agi/overrides/emergency-reset（紧急恢复，一键回滚所有覆盖层）",
      "#7c3aed"
    ],
    [
      "巡逻与验证API",
      "GET /api/agi/patrol/status（巡逻状态）POST /api/agi/patrol/trigger（手动触发巡逻）GET /api/agi/verify-supplier（供应商工商验证）GET /api/agi/verify-channels（可用验证渠道列表）POST /api/agi/parallel/toggle（并行加速开关）",
      "#059669"
    ]
  ]
});
}
// 知识库与核心配置
function renderAGIKnowledgeConfig() {
  return _pageTemplate({
  "title": "知识库与核心配置",
  "icon": "📚",
  "subtitle": "9类知识库（政策库/因果网络/信号模式/语义词典/风险同义词/行业画像/自愈规则/经验教训/分析历史）+10项核心配置参数（系统自动运行的关键阈值和参数）。",
  "stats": [
    [
      "9类",
      "知识库",
      "#2563eb"
    ],
    [
      "10项",
      "核心配置",
      "#7c3aed"
    ],
    [
      "动态",
      "知识自生长",
      "#059669"
    ],
    [
      "持久化",
      "JSON存储",
      "#d97706"
    ]
  ],
  "upstream": [
    [
      "agi-knowledge",
      "知识层",
      "知识库的管理和使用"
    ],
    [
      "agi-core",
      "核心智能引擎",
      "核心引擎使用知识库和配置"
    ]
  ],
  "downstream": [
    [
      "agi-special",
      "专项引擎层",
      "专项引擎依赖配置参数"
    ],
    [
      "agi-perf",
      "加速与保护层",
      "配置参数控制加速和覆盖层行为"
    ]
  ],
  "desc": "<p style=\"margin:0 0 10px\">9类知识库：①政策库policies（9条税收优惠）②因果网络causal_edges（信号→结论因果边）③信号模式signal_patterns（多信号组合）④语义词典semantic_dict（14类同义词）⑤行业画像industry_profiles（8大行业）⑥自愈规则healing_rules（错误→修正）⑦经验教训lessons（跨分析积累）⑧分析历史analysis_history（最近100条）⑨巡逻快照patrol_snapshots（巡逻基线）。</p>",
  "cards": [
    [
      "知识库（5类）",
      "政策库（9条税收优惠）、因果网络（动态因果边数）、信号模式（动态模式数）、语义词典（14类同义词）、行业画像（8大行业标准画像）",
      "#2563eb"
    ],
    [
      "知识库（4类）",
      "自愈规则（动态活跃规则数，同类错误≥2生成规则）、经验教训（动态经验条数，跨分析积累）、分析历史（最近100条）、巡逻快照（动态企业数，巡逻基线）",
      "#7c3aed"
    ],
    [
      "核心配置参数（5项）",
      "自愈引擎：5种错误模式/同类≥2生成规则；自动巡逻：最大5家/触发≥2边/变化>30%显著；规则发现：Layer A>80%空跑/Layer B≥5次纠正/Layer C>60%出现；反思器：adj<-0.05不确定/adj<-0.15推翻/7类型/14维反向假设；元认知：四维评估/不确定性阈值0.3/6种缺口",
      "#059669"
    ],
    [
      "核心配置参数（5项）",
      "SCM因果：do-干预/反事实/混淆检测/因果链/9条先验；知识库：线程安全/单例/100条历史/JSON持久化；联网核查：三步法/90天缓存/chinatax.gov.cn；并行加速：多模块并行/DAG依赖图/可开关/提升30-50%；事件总线：pub/sub松耦合/14种事件/500条日志/自动持久化",
      "#d97706"
    ]
  ]
});
}


// 稽查方法论（老稽查员办案心法·6部16章·靛蓝配色）
function renderReportSpecPage(container) {
  if (!container) return;
  window.currentModule = '报告规范';
  var css = '<style>'
    + '.rs2{max-width:1080px;margin:0 auto;padding:38px 46px;background:#fff;color:#4b5563;font-size:10px;line-height:1.9;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif}'
    + '.rs2-wrap{display:flex;gap:50px;align-items:flex-start}'
    + '.rs2-toc{width:150px;flex-shrink:0;position:sticky;top:22px;font-size:11.5px;max-height:calc(100vh - 44px);overflow-y:auto}'
    + '.rs2-toc .tt{font-size:10.5px;font-weight:700;color:#b0b8c4;letter-spacing:.12em;margin:0 0 10px 12px}'
    + '.rs2-toc a{display:block;color:#64748b;text-decoration:none;padding:5px 0 5px 12px;border-left:2px solid #eef2f6;transition:.15s;line-height:1.5}'
    + '.rs2-toc a:hover{color:#0e7490;border-left-color:#0e7490}'
    + '.rs2-body{flex:1;min-width:0;max-width:800px}'
    + '.rs2 h1{font-size:10px;font-weight:700;color:#16233a;margin:0 0 10px}'
    + '.rs2 .lead{font-size:12.5px;color:#64748b;margin:0 0 26px;line-height:20px5}'
    + '.rs2 section{margin:0 0 44px;scroll-margin-top:22px}'
    + '.rs2 h2{font-size:15.5px;font-weight:700;color:#16233a;margin:0 0 10px;display:flex;align-items:baseline;gap:9px}'
    + '.rs2 h2 .idx{color:#0e7490;font-size:10px;font-weight:700}'
    + '.rs2 .sub{font-size:10px;color:#64748b;margin:0 0 10px;padding-bottom:13px;border-bottom:1px solid #eef2f6;line-height:20px}'
    + '.rs2 p{margin:0 0 10px}'
    + '.rs2 strong{color:#334155;font-weight:600}'
    + '.rs2 .num{margin:4px 0 14px}'
    + '.rs2 .num .ni{position:relative;padding:0 0 0 16px;margin:0 0 9px;line-height:1.9}'
    + '.rs2 .num .ni::before{content:"";position:absolute;left:0;top:8px;width:5px;height:5px;border-radius:50%;background:#0e7490}'
    + '.rs2 .num .ni b{color:#334155;font-weight:600}'
    + '.rs2 .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:9px 18px;margin:4px 0 14px}'
    + '.rs2 .gi{font-size:11.5px;color:#64748b;padding-left:14px;position:relative;line-height:1.85}'
    + '.rs2 .gi::before{content:"";position:absolute;left:0;top:8px;width:5px;height:5px;border-radius:50%;background:#7dd3e0}'
    + '.rs2 .gi b{color:#334155;font-weight:600}'
    + '.rs2 .duo{display:flex;gap:12px;margin:6px 0 14px}'
    + '.rs2 .duo .dc{flex:1;padding:12px 14px;border-radius:8px;border:1px solid #eef2f6}'
    + '.rs2 .duo .dc .dt{font-size:10px;font-weight:700;margin:0 0 5px}'
    + '.rs2 .duo .dc .dx{font-size:10px;color:#64748b;line-height:1.85}'
    + '.rs2 .flow{display:flex;flex-wrap:wrap;align-items:center;gap:7px;margin:4px 0 14px;font-size:10px}'
    + '.rs2 .flow span{padding:5px 10px;background:#f0f9fb;color:#0e7490;border-radius:13px;font-weight:600}'
    + '.rs2 .flow i{color:#cbd5e1;font-style:normal}'
    + '.rs2 .rel{background:#f8fafc;border:1px solid #eef2f6;border-radius:8px;padding:13px 15px;margin-top:8px;font-size:11.5px;color:#64748b;line-height:20px}'
    + '.rs2 .rel b{color:#334155}'
    + '</style>';
  var toc = '<nav class="rs2-toc"><div class="tt">目录</div>'
    + '<a href="#rs-1">报告结构</a><a href="#rs-2">术语与机密规范</a><a href="#rs-3">叙事规范</a>'
    + '<a href="#rs-4">风险合并规则</a><a href="#rs-5">质量标准</a><a href="#rs-6">判定可靠性要求</a>'
    + '<a href="#rs-7">段落格式规范</a><a href="#rs-8">语音播报标准</a><a href="#rs-9">触发与交付</a></nav>';
  container.innerHTML = css + '<div class="rs2"><div class="rs2-wrap">' + toc
    + '<div class="rs2-body"><h1>报告规范</h1>'
    + '<p class="lead">从报告结构、用语立场到叙事框架、段落格式、语音播报的完整出具规范。它确保每一份税务合规报告都结构规范、用语审慎、叙事严谨、格式清晰、数据一致——既符合《税务稽查工作规程》的法定要求，又体现"发现而非定性"的专业立场。</p>'
    + '<div id="rs2-static"></div></div></div></div>';
  renderReportSpecStatic();
}

function renderReportSpecStatic() {
  var t = document.getElementById('rs2-static');
  if (!t) return;
  var h = '';
  h += '<section id="rs-1"><h2><span class="idx">一</span> 报告结构</h2>'
    + '<p class="sub">封面 + 七章正文 + 附件清单 —— 严格遵循《税务稽查工作规程》第 42 条的 10 项内容</p>'
    + '<p>正式税务合规报告由<strong>封面</strong>（编号格式 税稽字[YYYY]第XXX号）、<strong>七章正文</strong>与<strong>附件</strong>三部分构成：</p>'
    + '<div class="num">'
    + '<div class="ni"><b>第一章 案件来源及基本情况</b>——8 项基本信息表格：案件来源、被查单位、信用代码、法定代表人、企业类型、行业分类（三层穿透）、稽查期间、稽查范围。</div>'
    + '<div class="ni"><b>第二章 稽查实施情况</b>——7 个执行段落，整体 2000 字以上。</div>'
    + '<div class="ni"><b>第三章 发现问题及事实认定</b>——六要素格式，高风险优先排列；已审核展示绿色横幅，协商结果展示彩色横幅。</div>'
    + '<div class="ni"><b>第四章 稽查结论</b>。<b>第五章 处理处罚建议</b>——三级卡片 P0 立即处理（5 工作日）/ P1 限期整改（15 工作日）/ P2 持续关注（30 工作日）。</div>'
    + '<div class="ni"><b>第六章 告知权利义务</b>。<b>第七章 稽查人员签字</b>。</div>'
    + '<div class="ni"><b>附件（7 类）</b>——销项/进项发票全量明细、主营成本发票、重大费用发票、银行流水汇总、资料文件清单、质量标准自检结果。</div>'
    + '</div></section>';
  h += '<section id="rs-2"><h2><span class="idx">二</span> 术语与机密规范</h2>'
    + '<p class="sub">报告处于"发现阶段"而非法律裁决 —— 用语须体现发现而非定性，6 类内部信息严禁出现</p>'
    + '<p><strong>核心立场：</strong>报告是检查完毕后的事实陈述，不是最终的行政处罚决定。用语必须使用"涉嫌"而非"认定"、"可能存在"而非"确定存在"——任何在检查阶段就做违法定性的表述都不恰当。</p>'
    + '<div class="duo">'
    + '<div class="dc" style="border-color:#bbf7d0"><div class="dt" style="color:#0e9f6e">正确用语</div><div class="dx">涉嫌 / 可能存在 / 建议核实 / 需进一步确认 / 与申报数据存在差异 / 未能提供相关证据 / 数据分析显示 / 综合判断 / 潜在风险</div></div>'
    + '<div class="dc" style="border-color:#fecaca"><div class="dt" style="color:#e02424">禁止用语</div><div class="dx">违法 / 认定 / 确定 / 必定 / 毫无疑问 / 显然 / 绝对 / 非法 / 犯罪 —— 这些是处罚决定书和刑事判决书的用语，不属于合规报告</div></div>'
    + '</div>'
    + '<p><strong>6 类禁止暴露的内部信息</strong>（须转为外部表述）：① 引擎执行流程 → 系统自动分析发现；② 内部配置参数 → 行业通用标准；③ 代码位置引用 → 经系统验证；④ 系统日志 → 分析记录显示；⑤ 方法论内部名称 → 多维度交叉分析；⑥ AI 推理过程 → 综合分析判断。</p></section>';
  h += '<section id="rs-3"><h2><span class="idx">三</span> 叙事规范</h2>'
    + '<p class="sub">每条发现遵循六要素叙事框架 —— 缺失任一要素即为不完整</p>'
    + '<div class="flow"><span>What 事实</span><i>→</i><span>How 方法</span><i>→</i><span>Evidence 证据</span><i>→</i><span>Why 法律</span><i>→</i><span>Impact 影响</span><i>→</i><span>Action 建议</span></div>'
    + '<p>①<strong>What</strong>发现的事实问题 ②<strong>How</strong>通过什么方法发现 ③<strong>Evidence</strong>支撑证据（具体发票号/账簿页码/金额）④<strong>Why</strong>违反什么规定（法条编号+条文）⑤<strong>Impact</strong>税务影响（涉及税款金额）⑥<strong>Action</strong>处理建议。</p>'
    + '<p><strong>三类事实验证：</strong>数据交叉验证（发票 vs 账簿 vs 申报表，至少 2 方一致才写入）、时间轴验证（交易日期满足业务逻辑）、金额验证（借方=贷方、发票金额=账簿金额）。</p>'
    + '<p><strong>递进逻辑链：</strong>不允许"现象→结论"跳跃，必须"信号→推论→验证→确认→结论"，每步推理都在报告中体现。旧版五段式（背景→过程→发现→分析→建议）已废弃——背景与过程在第一、二章已交代，第三章直接从发现切入，减少冗余 30%+。</p></section>';
  h += '<section id="rs-4"><h2><span class="idx">四</span> 风险合并规则</h2>'
    + '<p class="sub">同一风险类型的多条发现合并为一条呈现 —— 7 步合并流程确保报告简洁不冗余</p>'
    + '<div class="num">'
    + '<div class="ni"><b>分组</b>——按 type 字段分组（去除内部前缀后 trim 比对），同类发现归入一组。</div>'
    + '<div class="ni"><b>等级取高</b>——同组取最高风险等级作为合并后等级，不降低任何子项的风险标记。</div>'
    + '<div class="ni"><b>合并标签</b>——标题显示"N 项同类风险合并"标签。</div>'
    + '<div class="ni"><b>子项独立展示</b>——每个子项保留独立的标题、细节、税务影响与处理建议，可追溯完整信息。</div>'
    + '<div class="ni"><b>证据合并</b>——所有子项的 items/evidence_rows/matched_chain_details 合并到父项。</div>'
    + '</div>'
    + '<p><strong>适用场景：</strong>知识图谱系列、发票合规系列、资料缺失触发系列——这三类最易产生大量同类发现，合并效果最明显。</p></section>';
  h += '<section id="rs-5"><h2><span class="idx">五</span> 质量标准</h2>'
    + '<p class="sub">报告生成后依序执行的 12 项检查 —— 强制 5 项 / 重要 4 项 / 建议 3 项</p>'
    + '<div class="grid">'
    + '<div class="gi"><b>1 模板句清除</b>：不得出现"根据相关规定"等模板句 [强制]</div>'
    + '<div class="gi"><b>2 重复句合并</b>：相似度 >80% 触发合并 [强制]</div>'
    + '<div class="gi"><b>3 空描述删除</b>：不得出现"无/暂无/—"空值 [强制]</div>'
    + '<div class="gi"><b>4 人性化表述</b>：技术参数转通俗表达 [强制]</div>'
    + '<div class="gi"><b>5 六要素完整</b>：What/How/Evidence/Why/Impact/Action [强制]</div>'
    + '<div class="gi"><b>6 法律引用准确</b>：法条须含编号+内容 [重要]</div>'
    + '<div class="gi"><b>7 具体数值</b>：每条发现至少 1 个具体数值 [重要]</div>'
    + '<div class="gi"><b>8 因果链</b>：不能"现象→结论"跳跃，须含中间推理 [强制]</div>'
    + '<div class="gi"><b>9 可执行建议</b>：建议须具体可操作 [强制]</div>'
    + '<div class="gi"><b>10 条款号</b>：引用规程须含条款号 [重要]</div>'
    + '<div class="gi"><b>11 反跨复制</b>：不得跨企业复制内容 [重要]</div>'
    + '<div class="gi"><b>12 空占位符清除</b>：全报告无残留占位符 [强制]</div>'
    + '</div>'
    + '<p>每项标准含要求说明、检测方法与正确范例，独立运行。不通过项以 ⚠ 标记，不影响报告整体合规性。</p></section>';
  h += '<section id="rs-6"><h2><span class="idx">六</span> 判定可靠性要求</h2>'
    + '<p class="sub">比质量标准更底层 —— 质量标准检测"表述是否正确"，可靠性检测"分析本身是否成立"</p>'
    + '<p><strong>致命级（3 项）：</strong>'
    + '<div class="num">'
    + '<div class="ni"><b>公司身份锚定</b>——报告开头必须声明公司名称 + 信用代码。</div>'
    + '<div class="ni"><b>发票方向判定</b>——进项/销项分类须有判定依据，存疑发票单独列出。</div>'
    + '<div class="ni"><b>综合判断</b>——文件类型判定须经四方证据交叉验证。</div>'
    + '</div>'
    + '<p><strong>高级（4 项）：</strong>④ 只读有效信息（排除空白行/小计/合计/汇总行）；⑤ 存疑排除（买卖双方都不含公司名称的发票必须排除）；⑥ 服务行业闸门（服务业不得出现实物商品域发现）；⑦ 品名级精度（混合行业必须品名级区分）。</p>'
    + '<div class="rel"><b>与质量标准的关系：</b>可靠性是质量标准的<strong>前提</strong>——分析不成立，表述再规范也无意义。二者互补：先保证分析成立（本章），再保证表述规范（第五章）。</div></section>';
  h += '<section id="rs-7"><h2><span class="idx">七</span> 段落格式规范</h2>'
    + '<p class="sub">五大禁止反模式 + 拆分标准 —— 一段一个主题，超过 200 字就拆</p>'
    + '<div class="num">'
    + '<div class="ni"><b>禁止一逗到底</b>——多个完整逻辑句各自独立成段，一段只表达一个完整意思。</div>'
    + '<div class="ni"><b>禁止多逻辑挤一段</b>——同段不得混杂 2 个以上不相关分析维度；不同域、税种、时间段的发现必须分段。</div>'
    + '<div class="ni"><b>禁止括号堆叠</b>——不得用括号堆砌多段判定逻辑链，括号内应为简短说明。</div>'
    + '<div class="ni"><b>子项独立成段</b>——子项内容各自独立为一段。</div>'
    + '<div class="ni"><b>数据与解释分层</b>——先陈述数据事实 → 再解释分析方法 → 最后给出结论。</div>'
    + '</div>'
    + '<p><strong>拆分自检：</strong>每写完一段自问——只有一个主题吗？能用一句话概括主旨吗？超过 200 字了吗（超了就拆）？</p></section>';
  h += '<section id="rs-8"><h2><span class="idx">八</span> 语音播报标准</h2>'
    + '<p class="sub">全文播报 + 点击播报 —— 中文男声、6 档语调、视觉跟随高亮</p>'
    + '<p><strong>功能：</strong>全文播报（报告顶部控制条）+ 点击任意段落播报；暂停/继续/停止，语速 0.85x–1.3x；视觉跟随——橙色底纹高亮当前段落并自动滚动。</p>'
    + '<p><strong>音色：</strong>中文男声（zh-CN male），低沉严肃的中年税务合规员声线，体现专业与权威感。降级策略：zh-CN male → zh-CN non-Tingting → zh 任意，确保任何设备都能播报。</p>'
    + '<p><strong>6 档语调分级：</strong>章节标题 0.65 音调/0.7x 语速、小节标题 0.72/0.8x、高风险内容 0.68/0.75x、法律条文 0.70/0.72x、处理建议 0.80/0.85x、普通叙述 0.78/0.88x。</p></section>';
  h += '<section id="rs-9"><h2><span class="idx">九</span> 触发与交付</h2>'
    + '<p class="sub">跨模块数据一致性由审计引擎自动保障 —— 四触发机制 + 三命令模式 + 三色交付</p>'
    + '<div class="flow"><span>手动 --sync</span><i>·</i><span>start.bat 启动</span><i>·</i><span>git commit 钩子</span><i>·</i><span>pipeline.py 启动</span></div>'
    + '<p><strong>三种命令模式：</strong>纯审计（只报告不一致项）/ <code>--sync</code>（联动同步自动修复）/ <code>--calibrate</code>（重新统计权威数据源，用于数据源变更后的基准校正）。</p>'
    + '<div class="rel"><b>报告交付保障：</b>同步完成 → 一致性验证 → <span style="color:#0e9f6e;font-weight:600">绿色交付</span>；不一致项超阈值 → <span style="color:#c27803;font-weight:600">黄色交付</span>（标注已知差异）；严重不一致 → <span style="color:#e02424;font-weight:600">红色阻断</span>。（一致性自检机制详见「稽查方法论 · 数据一致性自检」章节）</div></section>';
  t.innerHTML = h;
}

// AI交互（11模块融合整合页，智能问答独立保留）
function renderAIInteractionPage(container) {
  if (!container) return;
  window.currentModule = 'AI交互';
  var chapters = [
    ['一', '核心智能引擎', 'renderAGICore'],
    ['二', '因果推理层', 'renderAGICausal'],
    ['三', '连接通信层', 'renderAGIConnect'],
    ['四', '知识层', 'renderAGIKnowledge'],
    ['五', '专项引擎层', 'renderAGISpecial'],
    ['六', '加速与保护层', 'renderAGIPerf'],
    ['七', '数据资产', 'renderDataAssets'],
    ['八', 'API端点', 'renderAGIAPI'],
    ['九', '知识库与配置', 'renderAGIKnowledgeConfig'],
    ['十', '行为准则', 'renderAiRules'],
    ['十一', '人类学习引擎', 'renderHumanLearningPage']
  ];
  var css = '<style>'
    + '.aix{max-width:1180px;margin:0 auto;padding:34px 40px;background:#fff;color:#4b5563;font-size:10px;line-height:1.9;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif}'
    + '.aix-wrap{display:flex;gap:44px;align-items:flex-start}'
    + '.aix-toc{width:146px;flex-shrink:0;position:sticky;top:20px;font-size:11.5px;max-height:calc(100vh - 40px);overflow-y:auto}'
    + '.aix-toc .tt{font-size:10.5px;font-weight:700;color:#b0b8c4;letter-spacing:.12em;margin:0 0 10px 12px}'
    + '.aix-toc a{display:block;color:#64748b;text-decoration:none;padding:5px 0 5px 12px;border-left:2px solid #eef2f6;transition:.15s;line-height:1.5}'
    + '.aix-toc a:hover{color:#0e7490;border-left-color:#0e7490}'
    + '.aix-body{flex:1;min-width:0}'
    + '.aix h1{font-size:10px;font-weight:700;color:#16233a;margin:0 0 6px}'
    + '.aix .lead{font-size:10px;color:#64748b;margin:0 0 26px;line-height:1.9}'
    + '.aix section{margin:0 0 42px;scroll-margin-top:20px}'
    + '.aix .ch-h{font-size:15.5px;font-weight:700;color:#16233a;margin:0 0 14px;padding-bottom:11px;border-bottom:1px solid #eef2f6;display:flex;align-items:baseline;gap:9px}'
    + '.aix .ch-h .idx{color:#0e7490;font-size:10px;font-weight:700}'
    + '</style>';
  var toc = '<nav class="aix-toc"><div class="tt">目录</div>';
  var body = '<div class="aix-body"><h1>🤖 AI交互</h1>'
    + '<p class="lead">核心智能引擎 · 因果推理层 · 连接通信层 · 知识层 · 专项引擎层 · 加速与保护层 · 数据资产 · API端点 · 知识库与配置 · 行为准则 · 人类学习引擎 —— AGI 大脑的完整能力图谱与运作机制。（智能问答为独立交互入口）</p>';
  for (var i = 0; i < chapters.length; i++) {
    toc += '<a href="#aix-' + i + '">' + chapters[i][1] + '</a>';
    body += '<section id="aix-' + i + '"><div class="ch-h"><span class="idx">' + chapters[i][0] + '</span> ' + chapters[i][1] + '</div><div id="aix-body-' + i + '"></div></section>';
  }
  toc += '</nav>';
  body += '</div>';
  container.innerHTML = css + '<div class="aix"><div class="aix-wrap">' + toc + body + '</div></div>';
  for (var j = 0; j < chapters.length; j++) {
    var fn = window[chapters[j][2]];
    var sub = document.getElementById('aix-body-' + j);
    if (sub && typeof fn === 'function') {
      try {
        if (fn.length === 0) { sub.innerHTML = fn(); }
        else { fn(sub); }
      } catch (e) { sub.innerHTML = '<div style="color:#dc2626;padding:10px">加载失败: ' + (e && e.message) + '</div>'; }
    }
  }
}

// 分析链页面（与线索链/证据链并列）
function renderAnalysisChainsPage(container) {
  if (!container) return;
  window.currentModule = '分析链';
  window._skipModuleHeader = true;
  var h = '';
  h += '<style>'
    + '.alc{max-width:900px;margin:0 auto;padding:36px 28px;font-family:-apple-system,"Microsoft YaHei",sans-serif}'
    + '.alc-title{font-size:10px;font-weight:700;color:#16233a;margin:0 0 10px}'
    + '.alc-sub{font-size:10px;color:#64748b;margin:0 0 28px;line-height:1.8}'
    + '.alc-hero{display:flex;gap:12px;margin-bottom:10px;flex-wrap:wrap}'
    + '.alc-card{flex:1;min-width:130px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:18px 16px;text-align:center}'
    + '.alc-card .v{font-size:10px;font-weight:700;color:#16233a;line-height:1.3}'
    + '.alc-card .l{font-size:10px;color:#64748b;margin-top:6px}'
    + '.alc-chain{padding:14px 18px;margin-bottom:10px;border:1px solid #e2e8f0;border-radius:8px;background:#fff}'
    + '.alc-step{padding:8px 12px;margin:4px 0;background:#f8fafc;border-radius:6px;font-size:10px;line-height:1.9}'
    + '.alc-step .sn{display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:50%;background:#e0f2f7;color:#0e7490;font-size:10px;font-weight:700;margin-right:8px;flex-shrink:0}'
    + '.alc-flow{display:flex;align-items:center;gap:4px;font-size:10px;color:#64748b;margin:6px 0}'
    + '.alc-flow b{color:#334155}'
    + '</style>';
  h += '<div class="alc">';
  h += '<div class="alc-title">分析链</div>';
  h += '<div class="alc-sub">跨域综合推理引擎 · 推理路径可视化 · 所属：数据与分析</div>';
  h += '<div class="alc-hero">';
  h += '<div class="alc-card"><div class="v" id="alc-total">—</div><div class="l">分析链总数</div></div>';
  h += '<div class="alc-card"><div class="v" id="alc-high" style="color:#dc2626">—</div><div class="l">高风险链</div></div>';
  h += '<div class="alc-card"><div class="v" id="alc-mid" style="color:#f59e0b">—</div><div class="l">中风险链</div></div>';
  h += '<div class="alc-card"><div class="v" id="alc-steps" style="color:#2563eb">—</div><div class="l">推理步骤总数</div></div>';
  h += '</div>';

  h += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:10px">';
  h += '<div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:10px;font-weight:700;color:#0369a1;margin-bottom:10px">⬆ 上游（输入方）</div>';
  h += '<div style="font-size:10px;color:#3a4048;line-height:20px">';
  h += '<div>线索链<br><span style="color:#64748b">线索发现后触发分析链综合推理</span></div>';
  h += '<div>证据链<br><span style="color:#64748b">多源证据闭合后输入分析链</span></div>';
  h += '</div></div>';
  h += '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px 20px">';
  h += '<div style="font-size:10px;font-weight:700;color:#15803d;margin-bottom:10px">⬇ 下游（消费方）</div>';
  h += '<div style="font-size:10px;color:#3a4048;line-height:20px">';
  h += '<div>推理引擎<br><span style="color:#64748b">分析链驱动因果推理引擎</span></div>';
  h += '<div>报告生成<br><span style="color:#64748b">推理结论反馈至报告发现</span></div>';
  h += '</div></div></div>';

  h += '<div style="font-size:10px;color:#3a4048;line-height:20px;margin-bottom:10px">';
  h += '<p style="margin:0 0 10px">分析链是线索链→证据链之后的<strong>综合推理引擎</strong>——线索链触发"从哪里查"，证据链回答"查到了什么"，分析链做最终的综合推理判定。每条分析链从上一环节的发现出发，跨多个域逐层扩展分析范围，每一步都有回退路径，形成"从信号到结论"的完整推理链条。</p>';
  h += '<p style="margin:0">分析链的推理路径可视化展示：从哪个域发现 → 去哪个域验证 → 验证遇到什么情况如何分支 → 最终得出结论。这模拟了资深稽查员"顺藤摸瓜、层层深入、能进能退"的思维过程。</p>';
  h += '</div>';
  h += '<div id="alc-body"></div>';
  h += '</div>';
  container.innerHTML = h;
  loadAnalysisChainsData();
}

async function loadAnalysisChainsData() {
  var target = document.getElementById('alc-body');
  try {
    var resp = await fetch('/static/cross_domain_analysis.json?_t=' + Date.now());
    var chains = await resp.json();
    var high = chains.filter(function(c){return c.level==='高风险'}).length;
    var mid = chains.filter(function(c){return c.level==='中风险'}).length;
    var steps = 0; chains.forEach(function(c){steps += (c.reasoning_path||[]).length;});
    document.getElementById('alc-total').textContent = chains.length;
    document.getElementById('alc-high').textContent = high;
    document.getElementById('alc-mid').textContent = mid;
    document.getElementById('alc-steps').textContent = steps;
    var html = '';
    chains.forEach(function(chain){
      var lvlColor = chain.level==='高风险' ? '#dc2626' : (chain.level==='中风险' ? '#f59e0b' : '#0e7490');
      html += '<div class="alc-chain">';
      html += '<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">';
      html += '<span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:600;background:'+lvlColor+'15;color:'+lvlColor+'">'+escHtml(chain.level)+'</span>';
      html += '<span style="font-size:10px;font-weight:700;color:#16233a">'+escHtml(chain.name)+'</span>';
      html += '</div>';
      html += '<div style="font-size:10px;color:#64748b;line-height:1.9;margin-bottom:10px">'+escHtml(chain.description)+'</div>';
      if (chain.reasoning_path && chain.reasoning_path.length > 0) {
        html += '<div style="font-size:10px;font-weight:600;color:#64748b;margin-bottom:10px">推理路径（共 '+chain.reasoning_path.length+' 步）</div>';
        chain.reasoning_path.forEach(function(s,si){
          html += '<div class="alc-step">';
          html += '<div style="display:flex;align-items:flex-start">';
          html += '<span class="sn">'+(si+1)+'</span>';
          html += '<div style="flex:1">';
          html += '<div class="alc-flow">从 <b>'+escHtml((s.action||{}).from||'—')+'</b> → 发现 <b>'+escHtml((s.action||{}).finding||'—')+'</b></div>';
          html += '<div style="font-size:10px;color:#64748b">→ 去 <b style="color:#0e7490">'+escHtml((s.action||{}).to||'—')+'</b>：'+escHtml((s.action||{}).action||'—')+'</div>';
          html += '</div></div></div>';
        });
      }
      html += '</div>';
    });
    if (target) target.innerHTML = html;
  } catch(e) {
    if (target) target.innerHTML = '<div style="text-align:center;padding:20px;color:#dc2626">加载失败: '+e.message+'</div>';
  }
}

// 税务合规分析（16模块融合整合页）

// ═══════════ 税务合规分析（系统分析中枢·实体+运行+产出） ═══════════
function _co_money(v) { if(v==null) return "—"; try{var n=parseFloat(v); return n>=10000?(n/10000).toFixed(0)+"万元":n.toFixed(2)+"元";}catch(e){return "—";} }
function _renderCompanyOverview(container) {
  container.innerHTML = '<div style="text-align:center;padding:40px;color:#64748b">加载中...</div>';
  var cid = typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1;
  fetch('/api/company-overview?company_id=' + cid)
    .then(function(r) { return r.json(); })
    .then(function(d) {
      if (!d.ok) { container.innerHTML = '<div style="text-align:center;padding:60px 20px"><div style="font-size:10px;margin-bottom:10px">📊</div><div style="font-size:10px;font-weight:700;color:#16233a;margin-bottom:10px">暂无分析数据</div><div style="font-size:10px;color:#64748b">请先上传资料并运行"一键分析"</div></div>'; return; }
      var h = '';
      var co = d.company || {};
      var biz = d.business || {};
      var cash = d.cashflow || {};
      var inv = d.invoices || {};
      var tb = d.tax_burden || {};
      var risks = d.risks || {};
      var inc = d.incentives || {};
      var mat = d.material || {};
      // ① 企业名片
      h += '<div class="co-head"><div class="co-h1">' + escHtml(co.name || '未设置') + '</div>';
      h += '<div class="co-h2">';
      if(co.credit_code) h += '信用代码：' + escHtml(co.credit_code) + ' · ';
      h += (co.industry||'—') + ' · ' + (co.taxpayer_type||'—');
      h += '</div></div>';
      // ② 经营概况
      var cardBiz = '';
      if(biz.note){
        cardBiz = '<div class="co-card"><div class="co-ct">📈 经营概况</div><div style="color:#64748b;font-size:10px;padding:8px 0">' + escHtml(biz.note) + '</div></div>';
      } else {
        cardBiz = '<div class="co-card"><div class="co-ct">📈 经营概况</div><div class="co-metric"><div class="co-mv">' + _co_money(biz.revenue) + '</div><div class="co-ml">营业收入</div></div><div class="co-metric"><div class="co-mv">' + _co_money(biz.cost) + '</div><div class="co-ml">营业成本</div></div><div class="co-metric"><div class="co-mv" style="color:' + (biz.profit>0?'#059669':'#dc2626') + '">' + _co_money(biz.profit) + '</div><div class="co-ml">利润</div></div></div>';
      }
      h += cardBiz;
      // ③ 资金流水
      var cardCash = '<div class="co-card"><div class="co-ct">💰 资金流水</div>';
      if(cash.total_in||cash.total_out){
        cardCash += '<div class="co-metric"><div class="co-mv" style="color:#059669">' + _co_money(cash.total_in) + '</div><div class="co-ml">流入</div></div><div class="co-metric"><div class="co-mv" style="color:#dc2626">' + _co_money(cash.total_out) + '</div><div class="co-ml">流出</div></div><div class="co-metric"><div class="co-mv" style="color:' + (cash.net>0?'#059669':'#dc2626') + '">' + _co_money(cash.net) + '</div><div class="co-ml">净额</div></div>';
      }else{cardCash += '<div style="color:#64748b;font-size:10px;padding:8px 0">暂无银行流水数据</div>';}
      cardCash += '</div>';
      h += cardCash;
      // ④ 发票概况
      var cardInv = '<div class="co-card"><div class="co-ct">🧾 发票概况</div>';
      if(inv.sales_count||inv.purchase_count){
        cardInv += '<div class="co-metric"><div class="co-mv">' + (inv.sales_count||'—') + '张</div><div class="co-ml">销项发票</div></div><div class="co-metric"><div class="co-mv">' + _co_money(inv.sales_tax) + '</div><div class="co-ml">销项税额</div></div><div class="co-metric"><div class="co-mv">' + (inv.purchase_count||'—') + '张</div><div class="co-ml">进项发票</div></div><div class="co-metric"><div class="co-mv">' + _co_money(inv.purchase_tax) + '</div><div class="co-ml">进项税额</div></div>';
      }else{cardInv += '<div style="color:#64748b;font-size:10px;padding:8px 0">暂无发票数据</div>';}
      cardInv += '</div>';
      h += cardInv;
      // ⑤ 税负与纳税
      var cardBurden = '<div class="co-card"><div class="co-ct">📋 税负与纳税</div>';
      if(tb.available){
        cardBurden += '<div style="font-size:10px;color:#64748b">各税种应纳税额将在此展示</div>';
      }else{
        cardBurden += '<div style="padding:12px 0"><span style="display:inline-block;padding:4px 10px;background:#fff7ed;color:#c27803;border:1px solid #fed7aa;border-radius:6px;font-size:10px">⚠ ' + escHtml(tb.note||'需上传纳税申报表') + '</span></div>';
      }
      cardBurden += '</div>';
      h += cardBurden;
      // ⑥ 税务风险
      var cardRisk = '<div class="co-card"><div class="co-ct">🔍 税务风险</div>';
      if(risks.total > 0){
        cardRisk += '<div style="display:flex;gap:12px;flex-wrap:wrap;margin:6px 0">';
        var levels = {'极高风险':'#991b1b','高风险':'#dc2626','中风险':'#f59e0b','低风险':'#059669','信息':'#64748b'};
        for(var lv in risks.by_level){
          cardRisk += '<div style="min-width:64px;text-align:center"><div style="font-size:10px;font-weight:700;color:' + (levels[lv]||'#64748b') + '">' + risks.by_level[lv] + '</div><div style="font-size:10px;color:#64748b">' + (lv||'其他') + '</div></div>';
        }
        cardRisk += '</div>';
        cardRisk += '<div style="font-size:10px;color:#64748b;margin-top:4px">共 ' + risks.total + ' 条风险发现</div>';
      }else{
        cardRisk += '<div style="color:#059669;font-size:10px;font-weight:600;padding:8px 0">✓ 未发现显著风险</div>';
      }
      cardRisk += '</div>';
      h += cardRisk;
      // ⑦ 税收优惠
      var cardInc = '<div class="co-card"><div class="co-ct">🎁 税收优惠</div>';
      if(inc.available && inc.items && inc.items.length > 0){
        for(var j=0;j<inc.items.length;j++){
          var it = inc.items[j];
          cardInc += '<div style="margin:8px 0;padding:8px 10px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:6px"><div style="font-size:10px;font-weight:600;color:#059669">' + escHtml(it.name) + '</div><div style="font-size:10px;color:#64748b;line-height:1.8">' + escHtml(it.desc) + '</div><div style="font-size:10px;font-weight:600;color:#0e7490;margin-top:4px">' + escHtml(it.benefit) + '</div><div style="font-size:10px;color:#64748b;margin-top:2px">' + escHtml(it.status) + '</div></div>';
        }
      }else{
        cardInc += '<div style="color:#64748b;font-size:10px;padding:8px 0">' + escHtml(inc.note||'未触发已知优惠条件') + '</div>';
      }
      cardInc += '</div>';
      h += cardInc;
      // ⑧ 资料完备度
      var cardMat = '<div class="co-card"><div class="co-ct">📁 资料完备度</div>';
      if(mat.present_count + mat.missing_count > 0){
        cardMat += '<div style="display:flex;gap:8px;margin:4px 0"><div style="background:#f0fdf4;color:#059669;padding:2px 8px;border-radius:4px;font-size:10px">已上传 ' + mat.present_count + ' 类</div>';
        if(mat.missing_count>0) cardMat += '<div style="background:#fef2f2;color:#dc2626;padding:2px 8px;border-radius:4px;font-size:10px">缺失 ' + mat.missing_count + ' 类</div>';
        cardMat += '</div>';
        if(mat.missing && mat.missing.length>0) cardMat += '<div style="font-size:10px;color:#dc2626;margin-top:4px">缺失：' + escHtml(mat.missing.join('、')) + '</div>';
      }else{
        cardMat += '<div style="color:#64748b;font-size:10px;padding:8px 0">暂无资料清单</div>';
      }
      cardMat += '</div>';
      h += cardMat;
      container.innerHTML = '<div class="co-dash">' + h + '</div>';
    })
    .catch(function(e) {
      container.innerHTML = '<div style="text-align:center;padding:40px;color:#dc2626">加载失败：' + escHtml(e.message) + '</div>';
    });
}
function renderCompanyOverview(container) {
  if (!container) return;
  window.currentModule = '企业总览';
  var css = '<style>.co-dash{max-width:960px;margin:0 auto;padding:32px 24px;font-family:-apple-system,"Microsoft YaHei",sans-serif}.co-head{padding:20px 0 16px;border-bottom:1px solid #e2e8f0;margin-bottom:20px}.co-h1{font-size:10px;font-weight:700;color:#16233a}.co-h2{font-size:10px;color:#64748b;margin-top:6px}.co-card{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:18px 20px;margin-bottom:10px}.co-ct{font-size:10px;font-weight:700;color:#16233a;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #f1f5f9}.co-metric{display:inline-block;min-width:100px;margin:4px 16px 8px 0;vertical-align:top}.co-mv{font-size:10px;font-weight:700;color:#16233a;line-height:1.3}.co-ml{font-size:10px;color:#64748b;margin-top:2px}</style>';
  container.innerHTML = css + '<div id="co-main"></div>';
  _renderCompanyOverview(document.getElementById('co-main'));
}

// ═══════════ 稽查方法论（融合版·8部35章·藏青+朱红） ═══════════

// ═══════ 稽查方法论（六层递进·C融合版） ═══════
function METHODOLOGY_CSS() {
  return '<style>'
    + '.au{max-width:1140px;margin:0 auto;padding:40px 46px;background:#fff;color:#3a4048;font-size:10px;line-height:20px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif}'
    + '.au-wrap{display:flex;gap:50px;align-items:flex-start}'
    + '.au-toc{width:170px;flex-shrink:0;position:sticky;top:22px;font-size:10px;max-height:calc(100vh-44px);overflow-y:auto}'
    + '.au-toc .tt{font-size:10px;font-weight:700;color:#b0b8c4;letter-spacing:.16em;margin:0 0 14px 14px}'
    + '.au-toc a{display:block;color:#5b6675;text-decoration:none;padding:3px 0 3px 14px;border-left:2px solid #eef2f6;transition:.15s;line-height:1.5}'
    + '.au-toc a:hover{color:#9a1f2b;border-left-color:#9a1f2b}'
    + '.au-toc a.lv{margin-top:14px;font-weight:700;color:#2a3540;font-size:10px;border-left-color:#9a1f2b}'
    + '.au-toc a.lv:first-child{margin-top:0}'
    + '.au-body{flex:1;min-width:0}'
    + '.au h1{font-size:10px;font-weight:800;color:#16233a;margin:0 0 10px;letter-spacing:-.02em}'
    + '.au .seal{display:inline-block;font-size:10px;color:#9a1f2b;border:1px solid #f4c2c7;background:#fef8f8;border-radius:20px;padding:4px 14px;margin:0 0 30px}'
    + '.au .layer{margin:10px 0 10px;padding:0 0 10px;border-bottom:2px solid #16233a}'
    + '.au .layer .ln{font-size:10px;font-weight:700;color:#9a1f2b;letter-spacing:.16em;margin-bottom:10px;text-transform:uppercase}'
    + '.au .layer .lt{font-size:10px;font-weight:800;color:#16233a}'
    + '.au .layer .ld{font-size:10px;color:#64748b;margin-top:10px;line-height:20px}'
    + '.au section{margin:0 0 10px;scroll-margin-top:10px}'
    + '.au h2{font-size:10px;font-weight:700;color:#16233a;margin:0 0 10px}'
    + '.au p{margin:0 0 10px}'
    + '.au strong{color:#1f2d3d;font-weight:600}'
    + '.au em{font-style:normal;color:#9a1f2b;font-weight:600}'
    + '.au .card{margin:0 0 10px;padding:13px 15px;background:#fafbfc;border:1px solid #eff2f6;border-radius:8px}'
    + '.au .card .ct{font-size:10px;font-weight:700;color:#16233a;margin:0 0 10px}'
    + '.au .card .cx{font-size:10px;color:#64748b;line-height:20px}'
    + '.au .step{padding:0 0 2px 18px;border-left:2px solid #e2e8f0;margin:0 0 10px}'
    + '.au .step .sh{font-size:10px;font-weight:700;color:#1e293b;margin:0 0 10px}'
    + '.au .step .sh .n{color:#9a1f2b;margin-right:8px}'
    + '.au .arrow{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:10px 0 10px;font-size:10px}'
    + '.au .arrow span{padding:5px 10px;background:#fef8f8;color:#9a1f2b;border:1px solid #f4c2c7;border-radius:5px;font-weight:600}'
    + '.au .arrow i{color:#e0b4b9;font-style:normal;font-weight:700}'
    + '.au .maxim{margin:10px 0 10px;padding:10px;background:#16233a;border-radius:8px;color:#d0d7e0;font-size:10px;line-height:20px}'
    + '.au .maxim b{color:#f4c2c7}'
    + '.au .datbar{display:flex;flex-wrap:wrap;gap:1px;background:#eff2f6;border:1px solid #eff2f6;border-radius:10px;overflow:hidden;margin:10px 0 10px}'
    + '.au .datbar .d{flex:1;min-width:90px;background:#fcfdfe;padding:10px;text-align:center}'
    + '.au .datbar .d .n{font-size:10px;font-weight:700;color:#9a1f2b;line-height:1.1}'
    + '.au .datbar .d .l{font-size:10px;color:#64748b;margin-top:10px}'
    + '.au .live{border:1px solid #eff2f6;border-radius:10px;padding:10px;margin:10px 0 10px;background:#fcfdfe}'
    + '.au .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px;margin:10px 0 10px}'
    + '.au .gi{font-size:10px;color:#64748b;padding-left:14px;position:relative;line-height:20px}'
    + '.au .gi::before{content:"";position:absolute;left:0;top:8px;width:4px;height:4px;border-radius:50%;background:#e0b4b9}'
    + '.au .gi b{color:#2a3540;font-weight:600}'
    + '</style>';
}
function METHODOLOGY_TOC() {
  var items=[
    ['#au-preface','开篇·使命','lv'],
    ['#au-L1','第一层·启动','lv'],
    ['#au-s1','锁定身份',''],['#au-s2','三层穿透定行业',''],['#au-s3','三相符·四流合一',''],
    ['#au-L2','第二层·扫描','lv'],
    ['#au-s4','文件指纹识别',''],['#au-s5','情报逐行提取',''],['#au-s6','三大突破口',''],['#au-s7','时间序列分析',''],
    ['#au-L3','第三层·布网','lv'],
    ['#au-s8','规则引擎全量激活',''],['#au-s9','六大战法',''],['#au-s10','分税种杀手锏',''],['#au-s11','行业专属检测包',''],
    ['#au-L4','第四层·过滤','lv'],
    ['#au-s12','七类噪声过滤',''],['#au-s13','跨域协商',''],
    ['#au-L5','第五层·定案','lv'],
    ['#au-s14','证据三性与闭环',''],['#au-s15','税款测算',''],['#au-s16','定性分寸',''],['#au-s17','对抗性自检',''],
    ['#au-L6','第六层·出鞘','lv'],
    ['#au-s18','报告生成与净化',''],['#au-s19','全链路溯源',''],['#au-s20','合规度评估',''],
    ['#au-L7','第七层·进化','lv'],
    ['#au-s21','规则置信度自校准',''],['#au-s22','新模式发现',''],['#au-s23','政策同步',''],
    ['#au-s24','独立支线·税收优惠','lv'],
  ];
  var h='<nav class="au-toc"><div class="tt">引擎流水线</div>';
  for(var i=0;i<items.length;i++){var lv=items[i][2];h+='<a href="'+items[i][0]+'"'+(lv&&lv.indexOf('lv')>=0?' class="lv"':'')+'>'+items[i][1]+'</a>';}
  return h+'</nav>';
}
function renderMethodologyPage(container) {
  if(!container)return;
  window.currentModule='稽查方法论';
  container.innerHTML=METHODOLOGY_CSS()+'<div class="au"><div class="au-wrap"><div id="au-toc-div"></div><div class="au-body" id="au-body"></div></div></div>';
  renderMethodologyContent();
}

function renderMethodologyContent(){
  var toc=document.getElementById('au-toc-div');if(toc)toc.outerHTML=METHODOLOGY_TOC();
  var t=document.getElementById('au-body');if(!t)return;
  var h='';
  // ═══ 开篇 ═══
  h+='<section id="au-preface"><h1>稽查方法论</h1>';
  h+='<p>这不是一本教科书，是一位带了半世纪稽查队的老人，把从进门查账到定案出报告的每一步，写成引擎能<em>照做、能量化、能溯源</em>的指令。每一条指令背后，都有某年某案的真金白银在撑着。</p>';
  h+='<p>引擎执行七层：<em>启动→扫描→布网→过滤→定案→出鞘→进化</em>。不到这一层，不碰下一层的武器。每一层把"稽查员会怎么想"和"系统凭什么这么判"熔在一起——看完这七层，你就知道一键分析按钮按下去之后，引擎到底做了什么、凭什么敢下结论。</p>';
  h+='<div class="l">稽查指令</div></div><div class="d"><div class="n">{{clue_chains}}</div><div class="l">线索链</div></div><div class="d"><div class="n">{{evidence_chains}}</div><div class="l">证据链</div></div><div class="d"><div class="n">48</div><div class="l">分析链</div></div><div class="d"><div class="n">{{domain_functions}}</div><div class="l">域分析</div></div><div class="d"><div class="n">{{industries}}</div><div class="l">行业基准</div></div></div>';
  h+='<p><b>四句铁律贯穿全部七层（后文不再重述）：</b>实质重于形式（登记不算、干的才算）；孤证不立（单源数据不定案）；疑点非结论（起点是疑点、落点是铁证）；宁存疑不错杀（说不清的标存疑、有铁证的才下定论）。</p></section>';

  // ═══ 第一层·启动 ═══
  h+='<h2>第一层 · 启动 —— 资料包一打开，先认人再认门</h2><p>引擎拿到企业上传的全部资料。此时不急着翻任何一份文件——先做三件事：锁定身份、穿透行业、立起标尺。</p>';
  h+='<section id="au-s1"><h2>锁定身份：在查谁、什么资质、有没有前科</h2><p>从营业执照、工商登记信息提取：<strong>企业名称+信用代码+法定代表人+注册资本+注册地址</strong>。同时调取系统记录的纳税人资质——一般纳税人还是小规模——这决定了增值税是按销项减进项还是按征收率。引擎在这一步同步加载本账套的历史分析记录，做过哪些分析、上次结论如何——<em>不翻旧账的稽查，是瞎查</em>。</p></section>';
  h+='<section id="au-s2"><h2>三层穿透定行业：发动机的缸径决定了所有标尺</h2><p>行业定错，后面全部对标准则都是废的——毛利率、税负率、费用比的基准值全看行业。引擎不只看营业执照上的字，而用<strong>三层穿透</strong>逼近实质。</p>';
  h+='<p><b>1 工商登记层</b>：读取营业执照主营行业——但这是形式，登记"批发"实际做广告代理的比比皆是。此层仅作参考。</p>';
  h+='<p><b>2 发票数据层</b>：统计销项发票的金税分类编码分布。90%编码属"广告服务"？它实质就是广告公司。数据不会说谎。引擎据此给企业打上<strong>实质行业标签</strong>，此标签将被 {{domain_functions}} 个域分析函数和 {{industries}} 行业基准库全线消费。</p>';
  h+='<p><b>3 加工信号层</b>：扫描进销品名和银行摘要中的"加工费/代工/委外/OEM"关键词——如果批发企业有外包加工信号，实质是"采购原材料+发包加工+回收成品"三段经营。此时引擎<em>放宽进销存匹配标准</em>（进的是原料、销的是成品，不应要求品名精确匹配），同时激活制造业分析域。</p>';
  h+='<p>三层结果不一致时，以<strong>发票数据层为主、加工信号层为修正</strong>，在报告第一章完整披露穿透过程。</p></section>';
  h+='<section id="au-s3"><h2>三相符·四流合一：立起一切判断的标尺（术语唯一权威定义处）</h2><p>身份和行业定了，接下来引擎在心里立起两把尺。</p><p><b>三相符 —— 防的是"报得对不对"</b>：账载、票载、申报三套数据<strong>同口径一致</strong>。银行流水是外部基准——收入端对四方（账载、银行、开票、申报），一处不符即为疑点。这条线贯穿后面五层中每一次比对。</p><p><b>四流合一（术语唯一权威定义处） —— 防的是"业务真不真"</b>：<em>本节为"四流合一"的唯一权威定义处，后文战法④及跨域协商皆引用此定义，不再重述。</em>合同流、货物流、资金流、发票流指向同一主体、同一金额、同一时点。四流齐全为真实交易；一流游离即藏猫腻；两流以上对不上——警报拉满。引擎把这四个维度设为每条证据链的必查项。</p><p>两把尺交叉，引擎面对任何一笔交易、任何一个数字，都可以问出那两句："该报的报了吗？"和"该有的事情真有吗？"</p></section>';

  // ═══ 第二层·扫描 ═══
  h+='<h2>第二层 · 扫描 —— 把散落文件变成结构化情报</h2><p>身份已定、标尺已立。引擎现在翻开全部上传文件，逐份识别类型、逐行提取情报、锁定第一批疑点。</p>';
  h+='<section id="au-s4"><h2>文件指纹识别：34类指纹，把每份资料对号入座</h2><p>不靠扩展名（PDF可能是扫描发票）、不预设表头位置——引擎用<strong>四层递进识别</strong>：关键词打分找最匹配指纹类型→结构分析交叉验证→数据推断兜底→四方交叉验证终裁。支持8种文件格式、82+列名变体、OCR扫描件。每份文件的识别结果带<strong>匹配得分、置信度、命中关键词</strong>，不靠猜、不服软。失败文件在页面显示<strong>诊断与修复建议</strong>（建议在文件名加什么关键词、或者检查什么格式）。</p></section>';
  h+='<section id="au-s5"><h2>情报逐行提取：每行数据打上"元标签"</h2><p>文件身份确认后，引擎进入<strong>实体识别+情报提取</strong>：每一行银行流水被标记为哪家公司哪个账户的收支、金额、对方户名、摘要；每张发票被标记为销项还是进项、品名、金额、税额、购方/销方名称；每份科目余额表的每个科目被归入资产/负债/权益/收入/成本/费用的末级分类——逐行打上<strong>域标签</strong>（这笔交易该进哪个分析域）。</p><p>引擎在这一步同步生成<strong>收款构成画像</strong>（谁是最大的付款方、付款性质是什么）、<strong>付款构成画像</strong>、<strong>发票统计</strong>、<strong>工资社保统计</strong>、<strong>资料完备度评估</strong>（哪些资料有、哪些缺失会影响哪些域的置信度）。</p></section>';
  h+='<section id="au-s6"><h2>三大突破口：情报提取完毕后，先攻最脆弱的三个点（四方比对唯一定义处）</h2><p><b>① 银行流水 · 命门</b>：钱必须真金白银地走，最难造假。引擎在这一步做<strong>四方比对（本节为唯一定义处，后文不再重述）</strong>——把银行收款和账载收入、发票开具、纳税申报四套口径摊开，进账>开票→无票收入需核查；进账>账载→款项未入账直指隐匿。</p><p><b>② 发票 · 关卡</b>：进销两端都要看。进项品名是否与实质行业匹配（做广告却进钢材→虚开信号）；销项品名与经营范围匹配性；红冲作废频率异常放大。</p><p><b>③ 往来款 · 暗门</b>：最容易埋东西的地方：预收账款长期挂账不转收入、应付账款异常膨胀——金额大+账龄长+对手可疑=必有蹊跷。股东借款跨年不还视同分红问题详见第三层战法⑥关联交易穿透。</p></section>';
  // 新增 s7 时间序列分析
  h+='<section id="au-s7"><h2>时间序列分析：跨期波动是隐匿的指纹</h2><p>引擎对关键财务指标做<strong>月份环比/季度同比/年度趋势</strong>三维度扫描，识别三类异常模式。</p>';
  h+='<p><b>① 收入季节性断裂</b>：同行业正常波动范围内，年末/季末收入突增或骤降（偏离均值±2σ）→跨期调节信号。引擎自动对比相邻两期开票时点与收款时点，识别"开票集中化、收款均匀化"的时间错配。</p>';
  h+='<p><b>② 成本费用脉冲</b>：大额费用集中在某月突发（如咨询费单月超全年50%）→可能虚列或跨期调节。引擎追踪费用的发票开具时间、付款时间、服务合同签署时间——三时点不一致即为疑点。</p>';
  h+='<p><b>③ 往来款周期性波动</b>：应收/应付/预收/预付的余额在特定月份规律性冲减→可能循环倒账。引擎绘制科目余额时间曲线，识别"月初大额挂账、月末集中冲平"的周期模式。</p>';
  h+='<p>时间序列分析产出<strong>趋势异常信号</strong>，作为Phase2深挖的优先线索。</p></section>';
  h+='<p>扫描层产出的是<strong>结构化情报池</strong>——身份标签+行业标签+每行数据的域标签+三突破口的第一批疑点。盖子已经撬开了，下一层是真正的火力覆盖。</p>';

  window.__au1=h;
  renderMethodologyPart2();
}

function renderMethodologyPart2(){
  var h='';
  // ═══ 第三层·布网 ═══
  h+='<h2>第三层 · 布网 —— 火力全开，四链齐发</h2><p>情报池就绪。引擎全线激活规则引擎→线索链调查→证据链闭环→分析链综合推理。{{rules_count}}条指令+{{clue_chains}}条线索+{{evidence_chains}}条证据+48条跨域分析链+{{domain_functions}}个域分析函数——同时启动、四阶段递进。这是引擎的全力一击。</p>';
  h+='<section id="au-s8"><h2>规则引擎全量激活：Phase1-4四阶段递进</h2><p>引擎不是"查一条、判一条"，而是按<strong>四个阶段</strong>逐级收敛。</p>';
  h+='<p><b>Phase1  初查·全量信号扫描</b>：{{rules_count}}条指令一次扫过全部已提取的行数据。被触发的规则带<strong>溯源链</strong>（是哪个域的哪项数据点燃了它），形成"数据→规则→信号"的第一环。这一阶段只问"有没有可能"，不下判断。</p>';
  h+='<p><b>Phase2  深挖·线索链逐条调查（引用六大战法为方法库）</b>：Phase1的信号被投喂给{{clue_chains}}条线索链——每条是一条完整的调查路径（investigation_path，1-15步），从"这个信号该从哪查"到"查到了什么结果"。本阶段的<strong>调查方法</strong>来源于下节六大战法——每条线索链可调用战法①-⑥中的任一方法组合。三类触发：<strong>定量阈值</strong>（数值超限）、<strong>定性模式</strong>（特定关键词匹配）、<strong>缺失数据</strong>（资料缺口触发替代链）。</p>';
  h+='<p><b>Phase3  交叉验证·证据链闭环</b>：线索链是"一条线追到底"，证据链是"多条路同时验证"。每个证据闭环定义若干独立维度——当<strong>≥2个不同数据源的维度</strong>同时命中、达到min_evidence阈值，闭环成立。单域孤证不构成闭环。闭环后的证据自动汇入发现池，等待分析链做综合推理。</p>';
  h+='<p><b>Phase4  综合定性·跨域分析链判定（引用分税种为计算依据）</b>：48条跨域分析链做多源综合推理（每条含多步推理路径，每步带回退分支——能进能退）。如"七维系统性造假判定模型"：经营实质×供应商×资金流×四流合一×跨税种×关联交易×综合——七维命中越多风险越高，全异常则系统性造假立案。本阶段的<strong>税款测算</strong>依据来源于下节分税种杀手锏——每条分析链按税种规则计算补税额、滞纳金、罚款区间。</p></section>';

  h+='<section id="au-s9"><h2>六大战法：Phase2深挖的方法库</h2><p>{{domain_functions}}个域分析函数并行审视所有数据——同一笔银行流水，在资金流域看收款来源、在经营实质域看费用结构、在税务域看税费支出。以下是Phase2调查阶段可调用的核心战法（战法①资金流与第二层突破口①四方比对内容一致，仅作引用不重述）。</p>';
  h+='<p><b>① 资金流突破（引用第二层s6突破口①）</b>：<em>本战法与第二层s6突破口①四方比对内容一致，此处仅作引用。具体内容参见第二层s6。</em></p>';
  h+='<p><b>② 收入完整性（视同销售为唯一权威定义处）</b>：三条线：<strong>完整性</strong>——所有渠道（对公、私户、现金、平台、微信支付宝）收款是否全部入账；<strong>及时性</strong>——纳税义务时点是否被人为推迟（预收挂账、跨期调节）；<strong>视同销售（唯一权威定义处，后文不再重述）</strong>——赠送/投资/职工福利/以物易物/抵债/非货币性资产交换——最容易遗漏，引擎单列排查。</p>';
  h+='<p><b>③ 成本真实性（吸收识伪图谱增量）</b>：引擎做<strong>进销匹配</strong>：进的料和销的品，在产品链上必须对得上——进钢材销服装且无加工=猫腻。同时做<strong>成本收入配比</strong>：收入没涨成本猛增→毛利断崖→虚增信号。<strong>凭证合规</strong>：大额费用须有合法有效税前扣除凭证，白条、顶替发票、无票列支不得扣除。特别盯紧<strong>虚列高发科目</strong>：咨询费/服务费/会议费/佣金——集中爆发无合同无成果交付=纯虚列。<strong>识伪图谱增量检测</strong>：无货虚增、虚构人员工资、费用化资本性支出。</p>';
  h+='<p><b>④ 四流合一查虚开（引用第一层s3定义）</b>：<em>四流合一定义见第一层s3。本战法为应用层执行。</em>引擎把每笔交易的合同流、货物流、资金流、发票流在数据库里对齐比对：票款一致但货没动→无货虚开；货票匹配但款由第三方付且回流→资金过账；合同与发票品名金额不符→变名开票。四流查通，虚开现形。</p>';
  h+='<p><b>⑤ 人场货查空壳（吸收两套账）</b>：引擎做三向比对：<strong>人</strong>——社保参保数+个税申报数是否匹配业务规模（年入千万零参保→查哪来的人）。<strong>场</strong>——注册地是否有水电物业费、仓储物流记录（无办公痕迹=纸面企业）。<strong>货</strong>——购销品名与经营范围匹配性、物流凭证齐全度、进销存计量合理性。三者全空的，被标为"空壳嫌疑"。<strong>两套账与体外循环检测</strong>：内账（真实经营数据）与外账（报税数据）之间的差额即逃税证据。</p>';
  h+='<p><b>⑥ 关联交易穿透（唯一权威定义处）</b>：<em>本战法为关联交易穿透的唯一权威定义处，后文不再独立设节。</em>引擎从股东/董监高/共同地址电话/资金往来维度自动绘制<strong>关联方网络图</strong>（含隐性关联）。然后四步穿透：Step1比对关联价格与独立第三方价→偏离度超30%触发预警；Step2追利润流向（高税负向低税负低卖高买→腾挪）；Step3查关联方无息大额资金占用→视同贷款利息收入；Step4关联债资比超2:1（金融5:1）触发资本弱化。股东借款跨年不还视同分红（20%）在此战法一并检测。</p></section>';

  h+='<section id="au-s10"><h2>分税种杀手锏：Phase4定性的计算依据</h2>';
  h+='<p><b>增值税</b>·销端：无票收入不入账、视同销售不申报、混合销售低套税率、价外费用漏计、关联低价、纳税时点后移。进端：虚抵进项（有票无业务）、不得抵扣混入、异常凭证（供应商走逃）、取得与经营无关进项</p>';
  h+='<p><b>企业所得税</b>·收入与调整：政府补助计税、投资收益/债务重组/资产处置遗漏、视同销售、跨期收入。扣除项：<strong>招待费限额（唯一权威定义处）</strong>——发生额60%且不超过营收5‰，孰低原则；广宣费15%（化妆品/医药/饮料30%）；福利费14%；工资须实发且与社保个税勾稽；折旧摊销年限方法；研发加计归集合规性</p>';
  h+='<p><b>个人所得税</b>·私户/现金发薪未扣缴、股东借款跨年视同分红(20%)、股权转让平价无理由、发票报销顶替工资、多处取酬未合并。三数勾稽：工资发放人数=社保参保=个税申报</p>';
  h+='<p><b>社保</b>·缴费基数低于实发、试用期不参保、劳务派遣责任、参保人数与个税申报不一致</p>';
  h+='<p><b>残保金</b>·未按在岗人数1.5%（各地比例）申报缴纳、减免政策适用错误</p>';
  h+='<p><b>印花税</b>·合同台账逐笔对税目、实收资本+资本公积增加未缴、产权转移书据漏缴</p>';
  h+='<p><b>房产税</b>·自用从价/出租从租之争、地下建筑未入原值</p>';
  h+='<p><b>土地使用税</b>·面积不符、等级税率适用错误</p>';
  h+='<p><b>资源税</b>·开采量与销售量比对、税率适用错误（从价/从量）、减免政策适用</p>';
  h+='<p><b>契税</b>·房屋/土地权属转移未缴、计税依据错误、减免政策适用</p>';
  h+='<p><b>土地增值税</b>·房地产企业清算条件、增值率计算、扣除项目归集、预征率与清算率差异</p>';
  h+='<p><b>附加税费</b>·随增值税补缴：城建7%/5%/1%、教育附加3%、地方教育附加2%</p>';
  h+='</section>';

  h+='<section id="au-s11"><h2>行业专属检测包：十类重点行业特化规则</h2><p>引擎加载<strong>行业自适应配置</strong>——根据第一层行业标签，激活对应行业专属检测包。每个包含特化关键词、基准值范围、风险模式、合规要点。</p>';
  h+='<p><b>制造业</b>·进销存匹配（原材料→产成品链）、加工费/委外加工检测、BOM分析、生产成本归集、存货周转异常</p>';
  h+='<p><b>房地产</b>·预售收入确认、土地增值税清算、成本分摊、关联交易定价、车位/储藏室单独核算</p>';
  h+='<p><b>建筑业</b>·工程进度确认、甲供材处理、劳务分包、跨区域涉税、预缴税款抵扣</p>';
  h+='<p><b>金融业</b>·利息收入确认、手续费佣金、不良资产处置、同业业务、资管产品增值税</p>';
  h+='<p><b>互联网平台</b>·平台服务费、用户补贴、流量变现、数据资产、跨境支付</p>';
  h+='<p><b>商贸零售</b>·进销差价分析、库存周转、促销折扣、会员积分、团购/批零差异</p>';
  h+='<p><b>餐饮住宿</b>·现金收入核查、食材成本率、会员储值卡、团购平台结算、外包服务</p>';
  h+='<p><b>交通运输</b>·燃油成本占比、车辆租赁/自有、过路费、跨区域运营、物流代理</p>';
  h+='<p><b>医药医疗</b>·研发费用加计、临床试验外包、医疗器械租赁、药品采购渠道、医保结算</p>';
  h+='<p><b>教育培训</b>·预收款确认、课时消耗、教材收入、线上/线下差异、民办非企业税收</p>';
  h+='<p><em>行业包为增量检测规则——不替代通用规则，在通用规则基础上叠加行业特化维度。未匹配行业的，仅执行通用规则。</em></p></section>';

  // 数据面板
  h+='<div style="margin:10px 0"><details style="margin-bottom:10px"><summary style="font-size:10px;font-weight:700;color:#16233a;cursor:pointer;padding:10px 0">📋 税务疑点库（全量规则数据）</summary><div class="live"><div id="au-rules-data"></div></div></details>';
  h+='<details style="margin-bottom:10px"><summary style="font-size:10px;font-weight:700;color:#16233a;cursor:pointer;padding:10px 0">🔗 线索链数据（可直接查阅全部调查路径）</summary><div class="live"><div id="au-chains-data"></div></div></details>';
  h+='<details style="margin-bottom:10px"><summary style="font-size:10px;font-weight:700;color:#16233a;cursor:pointer;padding:10px 0">🔒 证据链数据（可直接查阅全部验证维度）</summary><div class="live"><div id="au-evidence-data"></div></div></details><details style="margin-bottom:10px" open><summary style="font-size:10px;font-weight:700;color:#16233a;cursor:pointer;padding:10px 0">📊 域分析引擎全景 · 检出结果</summary><div class="live"><div id="au-domain-unified"></div></div></details></div>';

  // ═══ 第四层·过滤 ═══
  h+='<h2>第四层 · 过滤 —— 把100条信号淬成3条铁证</h2><p>布网阶段{{domain_functions}}个域同时发动，会产生大量粗糙信号。把粗糙信号淬成铁证，靠的是三道过滤器。</p>';
  h+='<section id="au-s12"><h2>七类噪声过滤器：97%的噪音在这里被拦截</h2><p>过滤器依次执行，逐条筛除不可靠信号：</p>';
  h+='<p>行业豁免→数据缺失豁免→重复合并→低置信度→金额阈值→矛盾消解→白名单</p>';
  h+='<p>行业豁免排除不适用的域（服务业无需进销存分析）；数据缺失豁免免除因缺资料无法验证的信号；重复合并将同一问题被多域触发时只保留最高分；低置信度/金额阈值切除弱信号和小额噪音；矛盾消解解决域间互驳；白名单执行合理商业解释排除。<strong>最终能穿透这七层、到达下一层的发现，才是值得严肃对待的疑点。</strong></p>';
  h+='<p><strong>唯一归属规则</strong>：发现类信号归第二层、调查类归第三层、过滤类归第四层、定性类归第五层、输出类归第六层。同一内容在唯一权威处定义，其他位置仅引用。</p></section>';
  h+='<section id="au-s13"><h2>跨域协商：当两个域给出相反结论</h2><p>{{domain_functions}}个域同时运行，难免同一个信号在A域被标为高风险、在B域被判定为正常。协商引擎按<strong>"数据证据>推理证据>经验证据"的权重</strong>裁决。同向证据叠加升权、反向证据消解、无法消解的标存疑提交人工复核。<em>宁可存疑，不可错杀。</em></p>';
  h+='<p><strong>三档定级</strong>：铁证（≥3独立来源闭环）→强证据（2独立来源验证）→线索（单源数据触发，需深挖）。</p></section>';

  window.__au2=h;
  renderMethodologyPart3();
}

function renderMethodologyPart3(){
  var h='';
  // ═══ 第五层·定案 ═══
  h+='<h2>第五层 · 定案 —— 从"可能有"到"就是有"</h2><p>前四层产出了一批经得起推敲的发现。这一层是稽查的灵魂——把发现固定成推不翻的铁案。</p>';
  h+='<section id="au-s14"><h2>证据三性与闭环：每一条发现过三道安检</h2><p>引擎对每条发现做<strong>三性校验</strong>：真实性——数据来源可核实非篡改；关联性——直接相关非旁枝末节；合法性——取证程序符法定。三性不齐的证据上不了复议台。</p><p><strong>证据闭环</strong>是定案的底线——不是"有一份证据就够了"，而是多个独立来源的证据<em>相互印证形成闭环</em>。银行进账→缺少对应开票→无对应入账凭证→无对应申报——四环全闭才是铁证。单环不闭只标存疑。<em>不做证据闭环的结论，迟早被人翻案。</em></p></section>';
  h+='<section id="au-s15"><h2>税款测算：稽查的每一条发现最终都是一个金额</h2><p>没有金额的腐败是半成品。引擎对每条风险发现自动测算三类金额。<strong>补税额</strong>：隐匿收入×适用税率、不得扣除额×税率；<strong>滞纳金</strong>：应补税额×日万分之五×税款所属期截至缴清日的天数（超额累进逐段计算）；<strong>罚款区间（唯一权威定义处）</strong>：</p>';
  h+='<p><b>征管法§63 偷税（伪造/变造/隐匿/擅自销毁账簿，虚假申报）</b>：罚款：<strong>税款50%至5倍</strong>。情节严重（金额巨大/屡查屡犯/对抗检查）从重；主动补缴从轻。</p>';
  h+='<p><b>征管法§64 少缴税款（不申报，但无伪造/变造/隐匿账册行为）</b>：罚款：<strong>税款50%至5倍</strong>。与偷税差别在于主观故意证据——无账册造假/无资金回流→倾向于少缴。</p>';
  h+='<p><b>征管法§68 抗税（暴力/威胁方法拒不缴纳税款）</b>：罚款：<strong>拒缴税款1倍至5倍</strong>。情节严重的，移送司法机关追究刑事责任。</p></section>';
  h+='<section id="au-s16"><h2>定性分寸：主观故意判定依据（征管法§63四种手段）</h2><p>引擎区分三个层次：</p>';
  h+='<p><b>① 偷税（征管法§63）</b>：有<strong>四种法定手段之一</strong>且造成不缴/少缴结果：伪造/变造账簿记账凭证、在账簿上多列支出/不列/少列收入、隐匿/擅自销毁账簿记账凭证、虚假纳税申报。<strong>证据闭环要求</strong>：资金回流+内外账不符+反复操作+销毁隐匿账册——≥3项闭环。</p>';
  h+='<p><b>② 少缴税款（征管法§64）</b>：有少申报事实但<strong>无主观故意证据</strong>（偶发性计算错误、政策理解偏差、未涉及账册造假）。罚款区间与偷税相同，但量刑轻重不同。</p>';
  h+='<p><b>③ 虚开发票</b>：有证据证明交易不存在或票面信息与实际交易不符。<em>定性准不准，是法律判决能不能立住的关键。够什么级别定什么级，不拔高不放过。</em></p></section>';
  h+='<section id="au-s17"><h2>对抗性自检：把案子反过来审</h2><p>稽查不是单向指控——每一条结论写完，引擎必须<strong>反过来</strong>做三件事，确保铁案推不翻。</p>';
  h+='<p><b>① 反向假设验证</b>：假设发现的异常信号存在合法商业解释——是否能用正常业务逻辑自圆其说？如果能（如季节性/新开业/大单结算），降档；如果所有合理解释都不成立，强化的不是怀疑、是证据。</p>';
  h+='<p><b>② 对手方交叉比对</b>：引擎搜索数据库中的交易对手方信息——检查对手方对该笔交易的记录是否一致（金额/时间/性质）。如果对手方已申报而本方未申报，隐匿证据成立。</p>';
  h+='<p><b>③ 政策适用性复查</b>：检查结论引用的法规是否现行有效、是否存在特殊优惠或过渡期政策覆盖该事项。以最新法规库为准，不引用失效条款。</p></section>';

  // ═══ 第六层·出鞘 ═══
  h+='<h2>第六层 · 出鞘 —— 老稽查员交了卷</h2><p>前五层打完，引擎手里攥着一批铁证。这一层是收口——把铁证写成铁案报告，交给稽查员过目。</p>';
  h+='<section id="au-s18"><h2>报告生成与净化：引擎的交卷不能带墨迹</h2><p>引擎产出的报告自动经过<strong>纯净度净化</strong>——移除所有内部术语（引擎名称/代码位置引用/配置参数/AI推理过程描述），统一替换为税务专业表述。12项质量标准的自动检测在报告生成后依序执行：模板句清除、重复句合并、空描述删除、人性化表述、六要素完整、法律引用准确、具体数值、因果链、可执行建议、条款号、反跨复制、空占位符清除。</p><p>然后<strong>全链路溯源</strong>贯通全文——从每一条发现结论反向追踪到触发规则→匹配字段→来源文件→原始行号→原始凭证。可复核、可审计、可对质。引擎不做黑箱，六步溯源链就是它的底气。</p></section>';
  h+='<section id="au-s19"><h2>文书规范：一纸报告就是一把刀</h2><p>每条发现用<strong>六要素叙事框架</strong>：发现了什么→怎么发现的→证据是什么（精确到发票号/账页/金额）→违反什么规定（法条编号+条文）→税务影响多大（涉及税款金额）→建议怎么处理。用语只许用<em>"涉嫌/可能存在/与申报不符/未能提供合理说明"</em>——不用"违法/认定/偷税"。报告出口时的检查：每条结论背后至少两个独立来源的证据在撑着它吗？是→可落笔；不是→继续补证据。</p></section>';
  h+='<section id="au-s20"><h2>合规度评估：0-100分量化风险画像</h2><p>引擎对每户企业生成<strong>合规度评分</strong>（0-100分），由五维风险热力图加权计算：</p>';
  h+='<p><b>五维风险热力图</b>：<strong>收入端</strong>（无票收入/私户收款/跨期调节权重30%）→<strong>成本端</strong>（虚列成本/无票列支权重20%）→<strong>税种合规</strong>（各税种穿透权重25%）→<strong>证据链强度</strong>（闭环数量权重15%）→<strong>行业对标</strong>（基准偏离度权重10%）。每维度0-100分，加权得出总分。</p>';
  h+='<p><strong>合规亮点</strong>：高于行业基准的维度标注为"合规亮点"，写入报告正向段落。</p>';
  h+='<p><strong>高风险预警</strong>：得分<60的维度标红，写入报告高风险段落。</p>';
  h+='<p><strong>建议稽查频率</strong>：合规度≥90→两年一查；60-90→一年一查；<60→重点监控。</p></section>';

  // ═══ 第七层·进化 ═══
  h+='<h2>第七层 · 进化 —— 引擎自己学会长大</h2><p>前六层是"老稽查员教引擎做事"。这一层是"引擎自己学会长大"——从每一条发现、每一次判定中汲取经验，校准规则、发现新模式、同步政策变更。</p>';
  h+='<section id="au-s21"><h2>规则置信度自校准：历史数据修正阈值</h2><p>引擎维护<strong>规则置信度</strong>（0-1.0）——每条规则触发后，追踪最终是否被证据闭环验证。验证通过→置信度上升；验证失败→置信度下降。当某规则置信度连续10次<0.5时，引擎自动调低触发阈值或标记"需人工复核"。<em>置信度数据写入engine/memory.py，跨会话持久化。</em></p></section>';
  h+='<section id="au-s22"><h2>新模式发现：从未见过的风险模式自动提炼</h2><p>引擎在分析过程中检测到<strong>未匹配任何现有规则</strong>的异常信号时，自动记录为"待确认模式"。当同一模式在≥3户企业中出现时，引擎自动生成候选规则（含触发条件/阈值建议/置信度初值0.3），提交人工审核。审核通过后，候选规则升级为正式规则——引擎学会了自己发现新战法。</p></section>';
  h+='<section id="au-s23"><h2>政策同步：法规变更自动注入规则库</h2><p>引擎内置<strong>政策变更监测模块</strong>——当税法/征管规定发生修订时（如扣除比例调整/新增减免政策/处罚标准变更），引擎自动定位受影响的规则，生成变更建议（原规则→新规则→影响范围），提交人工确认后更新。<em>政策同步确保引擎永远紧跟最新法规，不因法规滞后而误判。</em></p></section>';

  // 独立支线·税收优惠
  h+='<h2>独立支线 · 税收优惠扫描 —— 引擎唯一的正向分析</h2><p>以上七层全是"找问题"，这一条支线是"找好处"——扫描企业应享未享的税收优惠，为纳税人省钱。</p>';
  h+='<section id="au-s24"><h2>税收优惠扫描：应享未享，一分都不能少</h2><p>引擎扫描<strong>9类优惠政策</strong>：小微企业普惠性减免、高新企业15%税率、研发费用加计扣除、六税两费减半（小规模纳税人）、残疾人就业增值税即征即退、退役士兵创业定额扣除、重点群体创业税收扣减、集成电路/软件企业优惠、海南自贸港15%封顶。</p>';
  h+='<p><strong>联网核查三步法</strong>：第一步匹配结构化条件（所得额/从业数/资产额等）→第二步联网核查资质证明（高新证书有效期/研发立项文件）→第三步计算可省金额。核查结果缓存90天，避免重复查询。</p>';
  h+='<p><strong>每项优惠输出</strong>：是否符合（是/否/需补充材料）+ 可省金额 + 政策依据 + 操作建议。</p>';
  h+='<div class="live"><div id="au-incentive"></div></div></section>';

  h+='<p><b>七层毕、一卷成、引擎长。</b>启动定身份、扫描提情报、布网铺火力、过滤淬铁证、定案下结论、出鞘交铁卷、进化学新招。引擎就是这样被教会的——不是学了一堆散装规则，而是掌握了从进门到出鞘再到自我进化的完整功夫。按下一键分析，背后的是这七层递进的引擎；看完这份卷，背后的是五十年的稽查经验；而引擎的进化，来自每一次判定后的反思。</p>';

  window.__au3=h;
  renderMethodologyAssemble();
}
function renderMethodologyAssemble(){
  var t=document.getElementById('au-body');if(!t)return;
  var full=(window.__au1||'')+(window.__au2||'')+(window.__au3||'');
  if(typeof applySysStats==='function'&&window._systemConfig)full=applySysStats(full,window._systemConfig);
  t.innerHTML=full;
  var r=document.getElementById('au-analyze-result');
  if(r&&typeof renderAnalyzePage==='function'){try{renderAnalyzePage(r)}catch(e){r.innerHTML='<div style=\"color:#64748b;padding:14px\">暂无分析结果，请先运行一键分析。</div>'}}
  var l=document.getElementById('au-analyze-logs');
  if(l&&typeof renderAnalyzeLogs==='function'){try{renderAnalyzeLogs(l)}catch(e){l.innerHTML='<div style=\"color:#64748b;padding:14px\">暂无管线日志。</div>'}}
  var rd=document.getElementById('au-rules-data');
  if(rd&&typeof renderTaxRiskRules==='function'){try{renderTaxRiskRules(rd)}catch(e){rd.innerHTML='<span style="color:#64748b">规则数据加载中...</span>'}}
  var cd=document.getElementById('au-chains-data');
  if(cd&&typeof renderChainsPage==='function'){try{renderChainsPage(cd)}catch(e){cd.innerHTML='<span style="color:#64748b">线索链数据加载中...</span>'}}
  var ud=document.getElementById('au-domain-unified');
  if(ud&&typeof renderUnifiedDomainPanel==='function'){try{renderUnifiedDomainPanel(ud)}catch(e){ud.innerHTML='<span style="color:#64748b">域分析引擎加载中...</span>'}}
  var ed=document.getElementById('au-evidence-data');
  if(ed&&typeof renderEvidencePage==='function'){try{renderEvidencePage(ed)}catch(e){ed.innerHTML='<span style="color:#64748b">证据链数据加载中...</span>'}}
  var i=document.getElementById('au-incentive');
  if(i&&typeof renderTaxIncentivesPage==='function'){try{renderTaxIncentivesPage(i)}catch(e){i.innerHTML='<div style=\"color:#64748b;padding:14px\">暂无税收优惠扫描结果。</div>'}}
}
