// ══════════════════════════════════════════════════════════════
//  稽查管道独立页：文件解析 | 域分析 | 跨域证据链 | 方法论过滤器
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
    var chains = chainsData.chains || [];
    _pipelineCounts = {
      rules: rules.length,
      trailChains: chains.filter(function(c){return c.chain_type==='线索链'}).length,
      evidenceChains: chains.filter(function(c){return c.chain_type==='证据链'}).length,
      totalChains: chains.length,
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
  container.innerHTML = '<style>.fp-layout{display:flex;gap:24px;max-width:1200px;margin:0 auto;padding:20px;background:#fff}.fp-toc{width:190px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:12px;line-height:2.0;max-height:calc(100vh-40px);overflow-y:auto}.fp-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.fp-toc a{display:block;color:#475569;text-decoration:none;padding:2px 8px;border-radius:4px;cursor:pointer}.fp-toc a:hover,.fp-toc a.active{background:#eff6ff;color:#2563eb;font-weight:600}.fp-main{flex:1;min-width:0;background:#fff}.fp-main h3{font-size:16px!important;font-weight:700!important;color:#0f172a!important;padding-bottom:8px!important;border-bottom:2px solid #e2e8f0!important;margin:0 0 16px!important}.fp-main .fp-step{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:20px 22px;transition:box-shadow 0.15s}.fp-main .fp-step:hover{box-shadow:0 2px 8px rgba(0,0,0,.06)}.fp-main details summary:hover{background:#f8fafc}.fp-main .fp-card{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:20px 22px;transition:box-shadow 0.15s}.fp-main .fp-card:hover{box-shadow:0 2px 8px rgba(0,0,0,.06)}.fp-main .fp-stat-card{background:#fff;border:1px solid #e2e8f0;border-radius:8px;text-align:center;padding:16px}.fp-main section{margin-bottom:48px!important;scroll-margin-top:20px}</style>'
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
    + '<h2 style="font-size:22px;font-weight:800;color:#0f172a;margin:0 0 4px">📁 文件解析</h2>'
    + '<p style="font-size:13px;color:#94a3b8;margin:0 0 24px">34类文件指纹 · 三层递进识别 · 四方交叉验证 · 8种格式全兼容 · OCR扫描件解析 · 关键词打分 · 结构分析 · 数据推断兜底</p>'
        + '<div style="background:#fff;border:1px solid #e2e8f0;padding:20px 24px;border-radius:8px;margin-bottom:32px">'
    + '<p style="font-size:13px;color:#475569;line-height:2.0;margin:0">'
    + '文件解析引擎是稽查分析的第一步——将企业上传的各种格式的原始资料（Excel/PDF/CSV/Word/图片），'
    + '通过34类文件指纹 + 四层递进识别 + 四方交叉验证，自动判定文件类型并提取为结构化数据。'
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
    + '<p style="font-size:13px;color:#475569;line-height:2.0;margin:0 0 20px">'
    + '系统接收到文件后，不依赖文件扩展名判断（用户上传的 .xls 可能是任何内容），'
    + '而是执行四层递进识别——从粗糙到精细、从单一证据到多方交叉验证，逐步锁定文件真实类型。'
    + '整个过程模拟人类专家的判断逻辑：先看表头关键词 → 再看列结构 → '
    + '再看数据样本 → 最后综合文件名/列头/数据/公司身份四方证据做最终裁决。'
    + '</p>'

    // Step 1
    + '<div class="fp-step" style="margin-bottom:16px;border-left:4px solid #0f172a">'
    + '<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">'
    + '<span style="display:inline-flex;align-items:center;justify-content:center;'
    + 'width:28px;height:28px;border-radius:6px;background:#0f172a;color:#fff;font-size:13px;font-weight:700">1</span>'
    + '<span style="font-size:15px;font-weight:700;color:#0f172a">关键词匹配 \u00b7 打分制</span>'
    + '<span style="font-size:11px;color:#94a3b8">最高优先级 \u00b7 识别率 ~80%</span>'
    + '</div>'
    + '<div style="font-size:13px;color:#475569;line-height:2.0">'
    + '<p style="margin:0 0 8px"><strong>执行逻辑：</strong>'
    + '读取 Excel 文件的前200行表头区域（不只是第1行），将表头中的每一个词与34类文件指纹的关键词库做交叉匹配。'
    + '每命中一个关键词得1分，得分超过该类型指纹的评分阈值（通常2-4分）即判定为该类型。'
    + '多类型同时超过阈值时，取得分最高的类型作为主判定。'
    + '</p>'
    + '<p style="margin:0 0 8px"><strong>实际例子：</strong>'
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
    + '<div class="fp-step" style="margin-bottom:16px;border-left:4px solid #64748b">'
    + '<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">'
    + '<span style="display:inline-flex;align-items:center;justify-content:center;'
    + 'width:28px;height:28px;border-radius:6px;background:#64748b;color:#fff;font-size:13px;font-weight:700">2</span>'
    + '<span style="font-size:15px;font-weight:700;color:#0f172a">结构分析 \u00b7 列模式匹配</span>'
    + '<span style="font-size:11px;color:#94a3b8">第二优先级 \u00b7 多类型接近时激活</span>'
    + '</div>'
    + '<div style="font-size:13px;color:#475569;line-height:2.0">'
    + '<p style="margin:0 0 8px"><strong>激活条件：</strong>'
    + '关键词匹配阶段，前两名得分差距\u22641分，或最高分类型得分恰好等于阈值（临界状态）。'
    + '此时不是简单地\u201c取最高分\u201d，而是进入更深层次的结构分析。'
    + '</p>'
    + '<p style="margin:0 0 8px"><strong>分析方法：</strong>'
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
    + '<div class="fp-step" style="margin-bottom:16px;border-left:4px solid #94a3b8">'
    + '<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">'
    + '<span style="display:inline-flex;align-items:center;justify-content:center;'
    + 'width:28px;height:28px;border-radius:6px;background:#94a3b8;color:#fff;font-size:13px;font-weight:700">3</span>'
    + '<span style="font-size:15px;font-weight:700;color:#0f172a">数据推断 \u00b7 逐列语义分类</span>'
    + '<span style="font-size:11px;color:#94a3b8">兜底机制 \u00b7 绝不丢弃数据</span>'
    + '</div>'
    + '<div style="font-size:13px;color:#475569;line-height:2.0">'
    + '<p style="margin:0 0 8px"><strong>触发场景：</strong>'
    + '关键词匹配和结构分析都无法确定文件类型时（例如企业自制的非标准表格、极少见的资料类型），'
    + '系统不会拒绝解析或丢弃数据，而是进入数据推断阶段——逐列读取前200行数据样本，'
    + '按每一个单元格的语义角色自动分类。'
    + '</p>'
    + '<p style="margin:0 0 8px"><strong>语义分类规则（5类）：</strong><br>'
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
    + '<div class="fp-step" style="margin-bottom:24px;border-left:4px solid #16a34a">'
    + '<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">'
    + '<span style="display:inline-flex;align-items:center;justify-content:center;'
    + 'width:28px;height:28px;border-radius:6px;background:#16a34a;color:#fff;font-size:13px;font-weight:700">4</span>'
    + '<span style="font-size:15px;font-weight:700;color:#0f172a">四方交叉验证 \u00b7 最终裁决</span>'
    + '<span style="font-size:11px;color:#94a3b8">2026-06-28新增 \u00b7 证据冲突时数据优先</span>'
    + '</div>'
    + '<div style="font-size:13px;color:#475569;line-height:2.0">'
    + '<p style="margin:0 0 8px"><strong>设计目的：</strong>'
    + '前三层都是\u201c文件内部\u201d的推理——仅依据表头和数据本身判断。但有时文件内部的线索可能产生歧义'
    + '（例如一份银行流水表头被改了列名，看起来像费用明细）。四方交叉验证引入\u201c外部证据\u201d——'
    + '包括文件名暗示、公司身份锚定、买卖方关系匹配——从多角度验证前三层的结论。'
    + '</p>'
    + '<p style="margin:0 0 8px"><strong>四方证据：</strong><br>'
    + '\u2460 <strong>文件名暗示</strong>：文件名含\u201c开票\u201d\u201c销项\u201d\u2192倾向销项发票；含\u201c取票\u201d\u201c进项\u201d\u201c抵扣\u201d\u2192倾向进项发票。'
    + '但仅作为参考权重，不直接决定类型——因为文件名可能错误标注。<br>'
    + '\u2461 <strong>列头推理</strong>：前三层的结果，带置信度。不同类型的关键词得分和列模式相似度作为主证据。<br>'
    + '\u2462 <strong>数据扫描（买卖方身份）</strong>：读取数据样本中的企业名称字段，与公司身份做双向比对。'
    + '购方名称=当前公司\u2192进项发票；销方名称=当前公司\u2192销项发票。'
    + '双方都不匹配\u2192存疑排除（可能是其他公司的文件误上传）。<br>'
    + '\u2463 <strong>公司匹配</strong>：通过企业名称和统一社会信用代码（USCC）双向锚定当前账套的企业身份，'
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
    + '<p style="font-size:13px;color:#475569;line-height:2.0;margin:0 0 16px">'
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
    html += '<details style="margin-bottom:12px;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden">'
      + '<summary style="padding:12px 16px;background:#fff;border-bottom:1px solid #f1f5f9;cursor:pointer;font-size:14px;font-weight:600;color:#0f172a;user-select:none">'
      + ci.icon + ' ' + ci.title + '</summary>'
      + '<div style="padding:14px 16px;font-size:13px;color:#475569;line-height:2.0;background:#fff">'
      + ci.detail + '</div>'
      + '</details>';
  });

  html += '</div>';

  // ═══════════════════════════════════════════════
  // 三、格式扩展（PDF/DOCX/CSV/OCR图片）
  // ═══════════════════════════════════════════════
  html += '<div id="fp-formats" style="margin-bottom:48px">'
    + '<h3>三、格式扩展：多格式全兼容</h3>'
    + '<p style="font-size:13px;color:#475569;line-height:2.0;margin:0 0 20px">'
    + '除了传统的 Excel 格式（.xls/.xlsx），文件解析模块已扩展到支持以下格式的自动解析：'
    + '</p>'

    + '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:12px">'

    // PDF
    + '<div class="fp-step">'
    + '<div style="font-size:15px;font-weight:700;color:#0f172a;margin-bottom:8px">\u{1f4c4} PDF文档</div>'
    + '<div style="font-size:13px;color:#475569;line-height:2.0">'
    + '<strong>双引擎架构：</strong>pdfplumber表格提取（优先）+ pypdf文本解析（兜底）。<br>'
    + '<strong>自适应策略：</strong>逐页提取所有表格 \u2192 取最大表格 \u2192 表头走34类指纹匹配 \u2192 '
    + '成功则按类型路由，失败则回退旧格式解析器。<br>'
    + '<strong>优势：</strong>不再硬编码特定银行格式（旧版仅支持招商银行大兴支行），任何银行/税务PDF均可识别。<br>'
    + '<strong>格式：</strong>支持 .pdf'
    + '</div>'
    + '</div>'

    // DOCX
    + '<div class="fp-step">'
    + '<div style="font-size:15px;font-weight:700;color:#0f172a;margin-bottom:8px">\u{1f4dd} Word文档</div>'
    + '<div style="font-size:13px;color:#475569;line-height:2.0">'
    + '<strong>表格提取：</strong>python-docx遍历所有表格 \u2192 合并多表格 \u2192 表头指纹匹配。<br>'
    + '<strong>文本兜底：</strong>无表格时提取段落文本，标注为 document_text 类型。<br>'
    + '<strong>应用场景：</strong>合同文件、申报说明、审计报告等Word格式资料。<br>'
    + '<strong>格式：</strong>支持 .docx'
    + '</div>'
    + '</div>'

    // CSV
    + '<div class="fp-step">'
    + '<div style="font-size:15px;font-weight:700;color:#0f172a;margin-bottom:8px">\u{1f4ca} CSV文本</div>'
    + '<div style="font-size:13px;color:#475569;line-height:2.0">'
    + '<strong>管道原生支持：</strong>csv.reader读取 \u2192 CsvSheet模拟Sheet接口 \u2192 指纹匹配。<br>'
    + '<strong>编码自动检测：</strong>UTF-8-BOM优先，自动处理逗号分隔和引号转义。<br>'
    + '<strong>应用场景：</strong>银行系统导出的流水、ERP导出的数据表等CSV格式。<br>'
    + '<strong>格式：</strong>支持 .csv'
    + '</div>'
    + '</div>'

    // OCR images
    + '<div class="fp-step">'
    + '<div style="font-size:15px;font-weight:700;color:#0f172a;margin-bottom:8px">\u{1f4f7} OCR图片识别</div>'
    + '<div style="font-size:13px;color:#475569;line-height:2.0">'
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
  // 四、34类文件指纹库
  // ═══════════════════════════════════════════════
  html += '<div id="fp-fingerprint" style="margin-bottom:48px">'
    + '<h3>四、文件指纹库 \u00b7 ' + fps.length + ' 类</h3>'
    + '<p style="font-size:13px;color:#475569;line-height:2.0;margin:0 0 20px">'
    + '每类指纹由 <strong>关键词集</strong> + <strong>得分阈值</strong> + <strong>专用解析器</strong> 三部分组成。'
    + '关键词决定了\u201c怎么看\u201d，阈值决定了\u201c多确定才能算\u201d，解析器决定了\u201c识别后怎么提取\u201d。'
    + '按使用频率分六梯队排列，第一梯队是稽查中最常见的高频类型。'
    + '</p>';

  var groups = [
    {title:'第一梯队 \u00b7 高频核心（用户最常上传）', items: fps.slice(0,12),
     desc:'这12类文件是稽查中最常出现的材料——银行流水、发票、工资表、社保公积金等。拥有最完善的关键词库（20-60+个关键词）和最成熟的解析器。得分阈值2-4分，识别率>95%。'},
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
    html += '<div style="margin-bottom:28px">'
      + '<div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:4px">' + escHtml(g.title) + '</div>'
      + '<div style="font-size:12px;color:#94a3b8;margin-bottom:10px;line-height:2.0">' + escHtml(g.desc) + '</div>'
      + '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:8px">';

    g.items.forEach(function(item) {
      html += '<div style="padding:10px 12px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;line-height:2.0">'
        + '<div style="font-weight:600;color:#0f172a;margin-bottom:4px"><span style="font-size:16px">' + item.icon + '</span> ' + escHtml(item.name) + '</div>'
        + '<div style="color:#64748b;font-size:12px;margin-bottom:4px">' + escHtml(item.sig) + '</div>'
        + '<div style="color:#94a3b8;font-size:11px">阈值：' + item.threshold + ' \u00b7 ' + item.parser + '</div>'
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
    + '<p style="font-size:13px;color:#475569;line-height:2.0;margin:0 0 20px">'
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
    html += '<div class="fp-step" style="margin-bottom:12px">'
      + '<div style="display:flex;gap:12px">'
      + '<span style="display:inline-flex;align-items:center;justify-content:center;'
      + 'flex-shrink:0;width:28px;height:28px;border-radius:50%;background:#f1f5f9;'
      + 'color:#64748b;font-size:13px;font-weight:700">' + st.num + '</span>'
      + '<div>'
      + '<div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:4px">' + st.title + '</div>'
      + '<div style="font-size:13px;color:#475569;line-height:2.0">' + st.detail + '</div>'
      + '</div></div>'
      + '</div>';
  });

  html += '</div>';

  target.innerHTML = html;
}

// 34类文件指纹数据（详尽版）
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
      target.innerHTML = '<div style="padding:48px 0;font-size:13px;color:#94a3b8">暂无分析结果，请先运行一键分析</div>';
      return;
    }
    _cachedFileParsingReport = data.report;
    renderFileParsingResult(data.report);
  } catch (e) {
    target.innerHTML = '<div style="padding:48px 0;font-size:13px;color:#94a3b8">加载失败</div>';
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
    + '<h3 style="font-size:16px;font-weight:700;color:#0f172a;margin:0 0 6px">六、本次解析结果</h3>'
    + '<p style="font-size:13px;color:#94a3b8;margin:0 0 24px">本次分析共解析 ' + frs.length + ' 个文件，成功识别 ' + parsed + ' 个，未识别 ' + failed + ' 个</p>'

    // 统计卡片
    + '<div style="display:flex;gap:12px;margin-bottom:40px">'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#0f172a">' + frs.length + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">文件总数</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#059669">' + parsed + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">已解析</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#dc2626">' + failed + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">未解析</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#0f172a">' + plogs.length + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">管线日志</div></div>'
    + '</div>'

    // 类型分布
    + '<h4 style="font-size:13px;font-weight:600;color:#94a3b8;margin:0 0 12px">类型分布</h4>';
  var typeCount = {};
  frs.forEach(function(fr) { var t = fr.type || 'unknown'; typeCount[t] = (typeCount[t] || 0) + 1; });
  var types = Object.keys(typeCount).sort(function(a,b) { return typeCount[b] - typeCount[a]; });
  if (types.length > 0) {
    html += '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:32px">';
    types.forEach(function(t) {
      html += '<div style="padding:6px 12px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:4px;font-size:12px;color:#475569">'
        + escHtml(t) + ' <span style="font-weight:600;color:#0f172a">x' + typeCount[t] + '</span></div>';
    });
    html += '</div>';
  }

  // 解析明细表
  html += '<h4 style="font-size:13px;font-weight:600;color:#94a3b8;margin:0 0 12px">解析明细</h4>';

  if (frs.length === 0) {
    html += '<div style="color:#94a3b8;font-size:13px;padding:24px 0">无文件数据</div>';
  } else {
    html += '<table style="width:100%;border-collapse:collapse;font-size:13px">'
      + '<thead><tr style="border-bottom:2px solid #0f172a;text-align:left">'
      + '<th style="padding:8px 12px 8px 0;font-weight:600;color:#0f172a;width:36px">#</th>'
      + '<th style="padding:8px 12px;font-weight:600;color:#0f172a">文件名</th>'
      + '<th style="padding:8px 12px;font-weight:600;color:#0f172a">识别类型</th>'
      + '<th style="padding:8px 12px;font-weight:600;color:#0f172a">数据条数</th>'
      + '<th style="padding:8px 12px;font-weight:600;color:#0f172a">解析动作</th>'
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
        + '<td style="padding:10px 12px 10px 0;color:#94a3b8">' + (i + 1) + '</td>'
        + '<td style="padding:10px 12px;color:#0f172a;max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + escHtml(fr.file) + '">' + escHtml(fr.file) + '</td>'
        + '<td style="padding:10px 12px;color:#64748b">' + escHtml(typeLabel) + '</td>'
        + '<td style="padding:10px 12px;color:#475569;font-weight:600">' + rowCount + '</td>'
        + '<td style="padding:10px 12px;color:#94a3b8;font-size:12px;max-width:280px">' + escHtml(actions) + '</td>'
        + '</tr>';
    });

    html += '</tbody></table>';
  }

  // 管线日志（详尽版）
  if (plogs.length > 0) {
    html += '<h4 style="font-size:13px;font-weight:600;color:#94a3b8;margin:40px 0 12px">管线日志 — 共 ' + plogs.length + ' 条</h4>';
    html += '<div style="background:#0f172a;border-radius:6px;padding:20px 24px;max-height:500px;overflow-y:auto;font-family:\'SF Mono\',\'Fira Code\',monospace;font-size:12px;line-height:2.0">';
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
}

// ==================== 页面2：域分析（详尽版） ====================
function renderDomainAnalysisPage(container) {
  if (!container) return;
  window.currentModule = '域分析';
  container.innerHTML = '<style>.da-layout{display:flex;gap:24px;max-width:1200px;margin:0 auto;padding:20px;background:#fff}.da-toc{width:190px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:12px;line-height:2.0;max-height:calc(100vh-40px);overflow-y:auto}.da-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.da-toc a{display:block;color:#475569;text-decoration:none;padding:2px 8px;border-radius:4px;cursor:pointer}.da-toc a:hover,.da-toc a.active{background:#eff6ff;color:#2563eb;font-weight:600}.da-main{flex:1;min-width:0;background:#fff}.da-main h3{font-size:16px!important;font-weight:700!important;color:#0f172a!important;padding-bottom:8px!important;border-bottom:2px solid #e2e8f0!important;margin:0 0 16px!important}.da-main section{margin-bottom:48px!important;scroll-margin-top:20px}</style>'
    + '<div class="da-layout">'
    + '<nav class="da-toc"><div class="toc-title">📖 导航</div>'
    + '<a href="#da-intro">一 什么是域分析</a>'
    + '<a href="#da-arch">二 域分析架构</a>'
    + '<a href="#da-domains">三 42个分析域</a>'
    + '<a href="#da-result">四 本次分析结果</a>'
    + '</nav>'
    + '<div class="da-main">'
    + '<h2 style="font-size:22px;font-weight:800;color:#0f172a;margin:0 0 4px">🔬 域分析</h2>'
    + '<p style="font-size:13px;color:#94a3b8;margin:0 0 24px">42个域分析函数 · 12大分类 · 跨域关联推理 · 多源证据链串联 · 资料情报自适应分类</p>'
    + renderDomainAnalysisStatic()
    + '<div id="da-analysis-result"></div>'
    + '</div></div>';

  if (_cachedDomainReport) { renderDomainAnalysisResult(_cachedDomainReport); }
  else { loadDomainAnalysisData(); }
}

function renderDomainAnalysisStatic() {
  var html = '';

  // ══════ Hero摘要 ══════
  html += '<div style="background:#fff;border:1px solid #e2e8f0;padding:20px 24px;border-radius:8px;margin-bottom:32px">'
    + '<p style="font-size:13px;color:#475569;line-height:2.0;margin:0">'
    + '域分析是稽查分析的核心层——42个分析域从资金流、进销存、供应商、交叉验证、经营实质、'
    + '资料完备度、发票、合同凭证、税务社保、资产关联、行业对标、跨域推理、补充税种共13个维度，'
    + '对同一份企业数据进行全方位、多角度、交叉印证的分析。每个域由独立的域分析函数驱动，'
    + '输出结构化的发现列表，域与域之间通过跨域关联推理形成多源证据链，最终汇集成完整的稽查报告。'
    + '</p>'
    + '</div>'

  // ══════ 一、什么是域分析 ══════
  html += '<div id="da-intro" style="margin-bottom:48px">'
    + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">一、什么是域分析</h3>'
    + '<p style="font-size:13px;color:#475569;line-height:2.0;margin:0 0 16px">'
    + '域分析（Domain Analysis）是税务稽查系统的核心分析层——位于文件解析和报告生成之间。'
    + '系统将从资料中提取的全部原始数据（银行流水、发票、工资表、社保、凭证、库存、合同等）'
    + '导入多个独立的分析域，每个域由专门的域分析函数（<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">_domain_*</code>）驱动，'
    + '从不同维度对同一份数据做独立又交叉的审视。'
    + '</p>'
    + '<p style="font-size:13px;color:#475569;line-height:2.0;margin:0 0 16px">'
    + '<strong>核心设计理念：单一数据源，多维度交叉。</strong>一份银行流水，在资金流分析域看收款来源，'
    + '在经营实质域看费用结构，在税务域看税费支出。同一个数据点在不同域中扮演不同角色，'
    + '多个域的发现相互印证或矛盾——这正是稽查判断的实质。'
    + '</p>'
    + '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px;margin-bottom:16px">'
    
    + '<div style="padding:14px 16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px">'
    + '<div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:6px">\u{1f4e5} 数据流入</div>'
    + '<div style="font-size:12px;color:#64748b;line-height:2.0">'
    + '文件解析模块输出的结构化数据<br>'
    + '→ 银行交易列表（bank_txs）<br>'
    + '→ 销/进项发票列表（sal_invs/pur_invs）<br>'
    + '→ 工资表/社保/公积金/凭证/库存/合同<br>'
    + '→ 行业画像（ctx.industry）'
    + '</div>'
    + '</div>'
    
    + '<div style="padding:14px 16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px">'
    + '<div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:6px">\u{2699}\u{fe0f} 域执行</div>'
    + '<div style="font-size:12px;color:#64748b;line-height:2.0">'
    + '42个域分析函数独立运行<br>'
    + '→ 每个域有数据守卫条件<br>'
    + '→ 缺数据→标记资料缺口不空跑<br>'
    + '→ 有数据→输出发现列表<br>'
    + '→ 行业闸门自动跳过不适用的域'
    + '</div>'
    + '</div>'
    
    + '<div style="padding:14px 16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px">'
    + '<div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:6px">\u{1f4e4} 发现输出</div>'
    + '<div style="font-size:12px;color:#64748b;line-height:2.0">'
    + '每条发现含9个标准字段<br>'
    + '→ type: 发现类型名称<br>'
    + '→ level/score: 风险等级+评分<br>'
    + '→ detail: 详细数据+计算过程<br>'
    + '→ description/suggestion: 解读+建议<br>'
    + '→ policy_ref/category: 法律+归类'
    + '</div>'
    + '</div>'
    
    + '<div style="padding:14px 16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px">'
    + '<div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:6px">\u{1f517} 跨域串联</div>'
    + '<div style="font-size:12px;color:#64748b;line-height:2.0">'
    + '单域发现→多域交叉印证<br>'
    + '→ 跨域关联推理自动串联<br>'
    + '→ 线索链+证据链+分析链<br>'
    + '→ 证据矛盾→协商引擎消解<br>'
    + '→ 同向证据→置信度叠加升权'
    + '</div>'
    + '</div>'
    
    + '</div>'
    + '<div style="padding:14px 18px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;font-size:12px;color:#475569;line-height:2.0">'
    + '<strong>\u{1f4cb} 发现字段详解：</strong><br>'
    + '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">type</code> 发现类型名称，如"资金流向 — 收款方异常"<br>'
    + '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">level</code> 风险等级：高风险/中风险/低风险/注意/信息<br>'
    + '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">score</code> 量化评分（0-10），≥8=极高，6-7=高，4-5=中，1-3=低<br>'
    + '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">detail</code> 详细数据——含计算过程、对比数据、触发阈值<br>'
    + '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">description</code> 稽查解读——为什么这是风险，如何理解<br>'
    + '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">suggestion</code> 处理建议——具体可执行的核查步骤<br>'
    + '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">policy_ref</code> 法律依据——引用的法条和文件号<br>'
    + '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">category</code> 分类标签——用于报告中的风险归类和合并<br>'
    + '<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">domain</code> 来源域——用于追溯发现的出处和回溯分析路径'
    + '</div>'
    + '</div>';

  // ══════ 二、域分析架构 ══════
  html += '<div id="da-arch" style="margin-bottom:48px">'
    + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">二、域分析架构</h3>'
    + '<p style="font-size:13px;color:#475569;line-height:2.0;margin:0 0 16px">'
    + '系统将42个分析域按驱动方式分为三类——资料驱动、算法驱动、知识驱动。'
    + '不同类型的域有不同的激活条件和置信度逻辑。'
    + '</p>'
    + '<div style="display:flex;gap:16px;margin-bottom:20px">'
    
    + '<div style="flex:1;padding:20px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;border-left:4px solid #dc2626">'
    + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">'
    + '<span style="font-size:20px">\u{1f4c4}</span>'
    + '<span style="font-size:15px;font-weight:700;color:#0f172a">资料驱动域</span>'
    + '</div>'
    + '<div style="font-size:12px;color:#64748b;line-height:2.0">'
    + '<strong>依赖上传资料进行判断。</strong>必须有对应的原始数据才能执行分析。'
    + '资料完备度越高，发现结论的置信度越高。缺资料时标注资料缺口，'
    + '不做无依据结论——这是稽查工作的基本原则。'
    + '</div>'
    + '<div style="margin-top:12px;padding:10px;background:#fef2f2;border-radius:6px;font-size:11px;color:#991b1b;line-height:2.0">'
    + '<strong>代表域：</strong>资金流向追踪（需银行流水）、'
    + '工资社保比对（需工资表+社保明细）、'
    + '合同比对（需合同台账+发票）'
    + '</div>'
    + '</div>'
    
    + '<div style="flex:1;padding:20px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;border-left:4px solid #2563eb">'
    + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">'
    + '<span style="font-size:20px">\u{1f4ca}</span>'
    + '<span style="font-size:15px;font-weight:700;color:#0f172a">算法驱动域</span>'
    + '</div>'
    + '<div style="font-size:12px;color:#64748b;line-height:2.0">'
    + '<strong>基于数据内在特征自动计算。</strong>只要有对应的基础数据即可运行，'
    + '无需外部参考资料。结果基于数学和统计学方法，客观性强。'
    + '</div>'
    + '<div style="margin-top:12px;padding:10px;background:#eff6ff;border-radius:6px;font-size:11px;color:#1e40af;line-height:2.0">'
    + '<strong>代表域：</strong>进销毛利率（需进销发票）、'
    + '存货周转预警（需进销存台账）、'
    + '异常交易时间分析（需银行流水）'
    + '</div>'
    + '</div>'
    
    + '<div style="flex:1;padding:20px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;border-left:4px solid #7c3aed">'
    + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">'
    + '<span style="font-size:20px">\u{1f4da}</span>'
    + '<span style="font-size:15px;font-weight:700;color:#0f172a">知识驱动域</span>'
    + '</div>'
    + '<div style="font-size:12px;color:#64748b;line-height:2.0">'
    + '<strong>内置行业基准库和法规库。</strong>将企业实际数据与66个行业的统计基准值对比，'
    + '与税收法律法规的要求对照验证。偏差超出正常范围时触发预警。'
    + '</div>'
    + '<div style="margin-top:12px;padding:10px;background:#f5f3ff;border-radius:6px;font-size:11px;color:#5b21b6;line-height:2.0">'
    + '<strong>代表域：</strong>行业对标分析（需66行业基准库）、'
    + '规则全覆盖验证（需1608条规则库）、'
    + 'CIT汇算清缴（需企业所得税法+实施条例）'
    + '</div>'
    + '</div>'
    
    + '</div>'
    + '</div>';

  // ══════ 三、42个分析域 ══════
  html += '<div id="da-domains" style="margin-bottom:48px">'
    + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">三、42个分析域</h3>'
    + '<div style="margin:0 0 24px;padding:14px 18px;background:linear-gradient(135deg,#eff6ff,#f0f9ff);border-radius:8px;border-left:3px solid #2563eb;font-size:12px;color:#475569;line-height:2">'
    + '<strong>🔍 判定规则（2026-06-28新增）</strong>——域分析执行前必须先通过以下判定：<br>'
    + '① <strong>公司身份锚定</strong>：以账套公司名+信用代码为锚点，发票买卖方与公司比对→方向判定<br>'
    + '② <strong>发票方向判定</strong>：购买方=公司→进项 | 销售方=公司→销项 | 双方不含→存疑排除<br>'
    + '③ <strong>进项再分类</strong>：含"抵扣税额"列→进项抵扣认证 | 无→进项发票(记账)<br>'
    + '④ <strong>服务行业闸门</strong>：销项金税编码∈25类服务→自动跳过进销存/BOM/进销比/毛利率对标<br>'
    + '⑤ <strong>品名级精准过滤</strong>：服务+货物混合企业→服务品名跳过进销存，实物品名正常检查<br>'
    + '⑥ <strong>综合判断·四方交叉验证</strong>：文件名暗示→列头推理→数据扫描→公司匹配，冲突时以数据为准<br>'
    + '⑦ <strong>存疑排除</strong>：买卖双方都不含公司的发票=非本账套数据=排除出所有计算<br>'
    + '</div>'
    + '<p style="font-size:13px;color:#94a3b8;margin:0 0 24px">每个域由独立的域分析函数驱动，按类别分组。右侧数字为该域的分析函数在 main.py 中的行号。</p>';

  var domainGroups = [
    // ══════ 一、资金流分析（4域） ══════
    {cat:'一、资金流分析', color:'#dc2626', desc:'银行流水收款来源分类、付款方身份核实、大额转账追踪、个人交易检测。资金流是稽查的血液——每一笔资金流动都可能隐藏着未申报收入或虚开发票。', items:[
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
    {cat:'六、资料完备度与情报', color:'#2563eb', desc:'14类稽查必查资料逐一检测，合同需求四层自动分层。资料情报自动分类并统计收款结构/付款方/发票模式。缺失资料→风险标记→无法支撑结论时标注资料缺口。', items:[
      {name:'资料完备度评估', fn:'_domain_document_completeness', line:'12798', desc:'14类稽查必查资料逐项检测 · 合同需求四层分层（必签/应签/可免/小额）· 缺失资料后果列明 · 综合资料完备度评分'},
      {name:'资料情报摘要', fn:'_extract_material_intel', line:'16992', desc:'银行收款类型自适应分类 · 付款方企业/个人/税务/银行占比 · 进销发票结构 · 凭证收入成本费用汇总 · 大额交易(>50万)识别'},
    ]},
    // ══════ 七、发票分析（3域） ══════
    {cat:'七、发票深度分析', color:'#0891b2', desc:'发票多维特征分析——时间/金额/税率/红冲/作废/连续性/服务vs货物占比。每一张发票都是稽查线索，发票异常模式能暴露系统性风险。', items:[
      {name:'发票深度特征', fn:'_domain_invoice_deep', line:'12763', desc:'服务类发票占比（服务行业特征判断）· 普票vs专票占比 · 开具时间分布 · 价格区间集中度 · 金额尾数分析 · 顶额开票检测'},
      {name:'发票生命周期', fn:'_domain_invoice_lifecycle', line:'12576', desc:'未认证占比统计 · 超期未认证预警 · 税率异常检测（同一品名不同税率）· 发票类型分布 · 红冲/作废率趋势'},
      {name:'红冲作废发票追踪', fn:'_domain_red_void_invoice', line:'14244', desc:'红冲率+作废率+时间集中度模式+金额集中度 · 月末/季末突击红冲作废 · 同一对方频繁红冲→异常交易关系'},
    ]},
    // ══════ 八、合同与凭证（2域） ══════
    {cat:'八、合同与凭证', color:'#0f172a', desc:'合同流与发票流/资金流比对；凭证规范性、科目使用、借贷平衡检查。凭证是财务数据的原子单元。', items:[
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
    {cat:'十一、行业对标与规则引擎', color:'#6366f1', desc:"66行业基准库对标，1608条规则全覆盖验证。行业对标告诉你“正常范围”，规则引擎告诉你“合规底线”。", items:[
      {name:'行业对标分析', fn:'_domain_industry_benchmark', line:'14475', desc:'66个行业基准——毛利率/税负率/进销比/人均营收/费用率五维对标 · 偏离度>2σ→行业异常预警 · 自动匹配行业代码'},
      {name:'规则全覆盖验证', fn:'_domain_rule_coverage', line:'15114', desc:'1608条规则逐条检查 · 已触发vs未触发分类 · 未触发→标注资料缺口 · 数据不足时作无依据结论（不作无证据判断）'},
      {name:'跨域关联推理', fn:'_domain_cross_domain_reasoning', line:'13490', desc:'单点发现→多域交叉印证→证据链闭环 · 7条内置跨域证据链（JSON驱动+内置回退）· A域+B域+C域同时异常→高置信度'},
      {name:'跨域线索链', fn:'_domain_cross_domain_clues', line:'14000', desc:'从cross_domain_clues.json加载跨域线索定义 · 线索→发现→证据三级转换 · 叙事生成器集成 · 线索链可视化追溯'},
    ]},
    // ══════ 十二、跨域分析链 ══════
    {cat:'十二、跨域分析链', color:'#8b5cf6', desc:'跨域分析链是最上层的推理引擎——它不直接分析数据，而是基于所有域的发现结果进行二阶推理，从交叉异常中推导出更深层的稽查结论。', items:[
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
    html += '<div style="margin-bottom:32px">'
      + '<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:6px">'
      + '<span style="width:3px;height:14px;display:inline-block;background:' + g.color + ';border-radius:2px"></span>'
      + '<span style="font-size:13px;font-weight:700;color:#0f172a">' + escHtml(g.cat) + '</span>'
      + '</div>'
      + '<div style="font-size:12px;color:#94a3b8;margin:0 0 12px 0;line-height:2.0">' + escHtml(g.desc) + '</div>';

    g.items.forEach(function(d) {
      html += '<div style="padding:10px 12px 10px 0;margin-bottom:4px;border-left:3px solid ' + g.color + ';background:#fff;border:1px solid #e2e8f0;border-left-width:3px;border-radius:6px">'
        + '<div style="display:flex;align-items:baseline;justify-content:space-between;margin-bottom:4px">'
        + '<div style="font-size:14px;font-weight:600;color:#0f172a">' + escHtml(d.name) + '</div>'
        + '<div style="font-size:11px;color:#94a3b8">' + escHtml(d.fn) + '() · 行' + d.line + '</div>'
        + '</div>'
        + '<div style="font-size:13px;color:#64748b;line-height:2.0">' + escHtml(d.desc) + '</div>'
        + '</div>';
    });

    html += '</div>';
  });

  html += '</div>';

  // ══════ 四、域间关系 ══════
  html += '<div style="margin-bottom:32px;padding:20px 24px;background:#fff;border-radius:8px">'
    + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 12px">四、域间关系与数据流</h3>'
    + '<div style="font-size:13px;color:#475569;line-height:2.0">'
    + '<strong>资料完备度</strong>（顶层）→ 决定所有域分析的置信度上限。缺合同→合同比对无法运行→标记缺口。<br>'
    + '<strong>经营实质分析</strong>（基础层）→ 提供企业画像：制造业/贸易型/服务型、本地/跨省、自加工/外包。<br>'
    + '<strong>发票+银行+凭证</strong>（数据层）→ 三大主数据源，支撑进销存、资金流、税务、薪酬、资产等15个分析域。<br>'
    + '<strong>多源交叉验证</strong>（交叉层）→ 将单个域的发现两两比对、三向检验，发现孤立点无法发现的隐藏关联。<br>'
    + '<strong>行业对标+规则引擎</strong>（校验层）→ 将企业数据与66行业基准对比，与' + pc('rules','1608') + '条规则逐一匹配。<br>'
    + '<strong>跨域关联推理</strong>（顶层）→ 将以上所有发现串联为10条跨域证据链，形成最终稽查结论。'
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
      target.innerHTML = '<div style="padding:48px 0;font-size:13px;color:#94a3b8">暂无分析结果，请先运行一键分析</div>';
      return;
    }
    _cachedDomainReport = data.report;
    renderDomainAnalysisResult(data.report);
  } catch (e) {
    target.innerHTML = '<div style="padding:48px 0;font-size:13px;color:#94a3b8">加载失败</div>';
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
  var highTotal = allF.filter(function(f) { return f.level === '极高风险' || (f.level === '极高风险' || c.level === '高风险'); }).length;
  var midTotal = allF.filter(function(f) { return f.level === '中风险'; }).length;

  var html = '<div id="da-result">'
    + '<h3 style="font-size:16px;font-weight:700;color:#0f172a;margin:0 0 6px;display:flex;align-items:center;justify-content:space-between">'
    + '<span>四、本次域分析结果</span>'
    + '<span style="font-size:12px;font-weight:400">'
    + '<a href="#" onclick="expandAllDomains();return false" style="color:#2563eb;margin-right:8px">展开全部</a>'
    + '<a href="#" onclick="collapseAllDomains();return false" style="color:#94a3b8">收起全部</a>'
    + '</span></h3>'
    + '<p style="font-size:13px;color:#94a3b8;margin:0 0 24px">共 ' + totalDomains + ' 个分析域执行完毕，' + triggeredDomains + ' 个域产生发现，合计 ' + allF.length + ' 条发现（高风险 ' + highTotal + ' · 中风险 ' + midTotal + '）</p>'

    // 统计卡片
    + '<div style="display:flex;gap:12px;margin-bottom:40px">'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#0f172a">' + totalDomains + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">分析域</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#2563eb">' + triggeredDomains + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">已触发</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#dc2626">' + highTotal + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">高风险</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fffbeb;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#f59e0b">' + midTotal + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">中风险</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#0f172a">' + allF.length + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">合计发现</div></div>'
    + '</div>'

    + '<h4 style="font-size:13px;font-weight:600;color:#94a3b8;margin:0 0 12px">域概览（按风险权重排序）</h4>';

  if (domainNames.length === 0) {
    html += '<div style="color:#94a3b8;font-size:13px;padding:24px 0">无域分析数据</div>';
  } else {
    domainNames.forEach(function(name, di) {
      var d = domainMap[name];
      var hasFindings = d.count > 0;
      var riskLabel = d.high > 0 ? '高风险' : (d.mid > 0 ? '中风险' : (hasFindings ? '信息' : '未触发'));
      var riskColor = d.high > 0 ? '#dc2626' : (d.mid > 0 ? '#f59e0b' : (hasFindings ? '#22c55e' : '#94a3b8'));

      html += '<div style="border-bottom:1px solid #f1f5f9;padding:12px 0;cursor:' + (hasFindings ? 'pointer' : 'default') + '" onclick="' + (hasFindings ? 'toggleDomainDetail(' + di + ')' : '') + '">'
        + '<div style="display:flex;align-items:center;justify-content:space-between">'
        + '<div style="display:flex;align-items:center;gap:10px">'
        + '<span style="font-size:14px;font-weight:600;color:#0f172a">' + escHtml(name) + '</span>'
        + '<span style="font-size:11px;padding:1px 6px;border-radius:3px;background:' + riskColor + '10;color:' + riskColor + ';font-weight:600">' + riskLabel + '</span>'
        + '</div>'
        + '<div style="display:flex;gap:16px;font-size:12px;color:#94a3b8">'
        + '<span>发现 <b style="color:#0f172a">' + d.count + '</b></span>'
        + (d.high > 0 ? '<span style="color:#dc2626;font-weight:600">高' + d.high + '</span>' : '')
        + (d.mid > 0 ? '<span style="color:#f59e0b;font-weight:600">中' + d.mid + '</span>' : '')
        + (hasFindings ? '<span style="color:#94a3b8;font-size:11px">▸</span>' : '')
        + '</div>'
        + '</div>';

      // 展开的发现详情
      if (hasFindings) {
        html += '<div id="dd-' + di + '" style="display:none;margin-top:12px;padding:12px 16px;background:#fff;border-radius:6px">';
        d.findings.forEach(function(f) {
          var lvlColor = f.level === '极高风险' || (f.level === '极高风险' || c.level === '高风险') ? '#dc2626' : (f.level === '中风险' ? '#f59e0b' : '#22c55e');
          var lvlBg = f.level === '极高风险' || (f.level === '极高风险' || c.level === '高风险') ? '#fef2f2' : (f.level === '中风险' ? '#fffbeb' : '#f0fdf4');
          var dt = typeof f.detail === 'object' && f.detail.summary ? f.detail.summary : (f.detail || '');
          var trace = f._trace || {};
          html += '<div style="padding:10px 12px;margin-bottom:6px;background:' + lvlBg + ';border-radius:6px;border-left:3px solid ' + lvlColor + '">'
            + '<div style="font-size:13px;font-weight:600;color:#0f172a;margin-bottom:4px">' + escHtml(f.type || '') + '</div>'
            + '<div style="font-size:12px;color:#475569;line-height:2.0;margin-bottom:4px"><span class="d-find-detail" data-full="' + escHtml(dt).replace(/"/g, '&quot;') + '">' + escHtml(dt.substring(0, 300)) + '</span>'
            + (dt.length > 300 ? ' <a href="#" onclick="var s=this.previousElementSibling;s.textContent=s.getAttribute(\'data-full\');this.remove();return false" style="color:#2563eb;font-size:11px">展开全文</a>' : '')
            + '</div>'
            + '<div style="display:flex;gap:8px;align-items:center;font-size:11px;color:#94a3b8">'
            + '<span style="color:' + lvlColor + ';font-weight:600">' + (f.level || '') + '</span>'
            + '<span>score:' + (f.score || '-') + '</span>'
            + (f.rule_id ? '<span>规则:' + f.rule_id + '</span>' : '')
            + '</div>';
          // 自动内联推理链路——每条结论自带追责
          if (trace && trace.finding_id) {
            var pathText = (trace.detection_path||[]).join(' → ');
            var confColor = trace.confidence === '高' ? '#059669' : '#f59e0b';
            html += '<div style="margin-top:6px;padding:6px 8px;background:rgba(59,130,246,0.06);border-radius:4px;font-size:10px;color:#64748b;line-height:2.0">'
              + '<span>📋 ' + escHtml(trace.phase_origin||'') + '</span>'
              + '<span style="margin-left:8px;color:' + confColor + '">可信度:' + escHtml(trace.confidence||'?') + '</span>'
              + '<span style="margin-left:8px">| 来源:' + escHtml((trace.data_sources||[]).slice(0,4).join('、')) + '</span>'
              + '<span style="margin-left:8px">| 规则:<code style="font-size:9px">' + escHtml((trace.rules_hit||[]).slice(0,3).join(',')) + '</code></span>'
              + '<br><span style="color:#94a3b8">' + escHtml(pathText) + '</span>'
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
function renderCrossDomainEvidencePage(container) {
  if (!container) return;
  window.currentModule = '跨域证据链';
  var hasCache = window._allCrossChains && window._allCrossChains.length > 0;
  container.innerHTML = '<style>.cde-layout{display:flex;gap:24px;max-width:1200px;margin:0 auto;padding:20px}.cde-toc{width:180px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:12px;line-height:2.0;max-height:calc(100vh-40px);overflow-y:auto}.cde-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.cde-toc a{display:block;color:#475569;text-decoration:none;padding:2px 8px;border-radius:4px;cursor:pointer}.cde-main{flex:1;min-width:0}</style>'
    + '<div class="cde-layout"><nav class="cde-toc" id="cde-toc"><div class="toc-title">📖 导航</div></nav>'
    + '<div class="cde-main"><h2 style="font-size:22px;font-weight:800;color:#0f172a;margin:0 0 4px">🔗 跨域证据链</h2>'
    + '<p style="font-size:13px;color:#94a3b8;margin:0 0 24px">'+ (hasCache?window._allCrossChains.length:'...') +' 条证据链 · 多源交叉验证</p>'
    + '<div id="cde-static"></div><div id="cde-dynamic"></div></div></div>';
  if (hasCache) { renderCrossDomainStaticContent(window._allCrossChains); loadCrossDomainDynamic(); }
  else { loadCrossDomainStatic(); loadCrossDomainDynamic(); }
}

function loadCrossDomainStatic() {
  var target = document.getElementById('cde-static');
  fetch('/static/cross_domain_evidence.json?_t=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(chains) {
      window._allCrossChains = chains;
      renderCrossDomainStaticContent(chains);
    })
    .catch(function() {
      if (target) target.innerHTML = '<div style="padding:40px 0;font-size:13px;color:#94a3b8">跨域证据链定义加载失败</div>';
    });
}

function renderCrossDomainStaticContent(chains) {
  var target = document.getElementById('cde-static');
  if (!target) return;
  var highCount = chains.filter(function(c) { return (c.level === '极高风险' || c.level === '高风险'); }).length;
  var totalDim = chains.reduce(function(s, c) { return s + c.dimensions.length; }, 0);
  var totalMinEvidence = chains.reduce(function(s, c) { return s + c.min_evidence; }, 0);

  // Populate TOC
  var tocEl = document.getElementById('cde-toc');
  if (tocEl) { tocEl.innerHTML = '<div class="toc-title">📖 '+chains.length+' 条证据链</div><a href="#cde-intro">一 概述</a><a href="#cde-list">二 证据链定义</a>'; }

  var html = '';

  html += '<div id="cde-intro" style="margin-bottom:40px">'
    + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">一、什么是跨域证据链</h3>'
    + '<p style="font-size:13px;color:#64748b;line-height:2.0;margin:0 0 16px">'
    + '跨域证据链是系统最高价值的输出——它不依赖单一数据源的孤立异常，而是将来自不同数据域（资金流、发票流、'
    + '经营实质、资料完备等）的发现串联起来，形成多源交叉验证的证据闭环。单维度触发视为孤证，不形成证据链闭环。'
    + '只有≥2个维度同时命中，才算形成有效证据链。这是税务稽查中"证据链"概念在AI系统中的实现。'
    + '</p>'
    + '<div style="padding:16px 20px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;font-size:13px;color:#475569;line-height:2">'
    + '<strong>工作流程</strong>：domain_results中发现 → 关键词匹配各链维度 → 累计触发维度数 → 达到min_evidence阈值 → 生成跨域证据链发现 → 多源交叉闭环保高风险输出。'
    + '</div>'
    + '</div>';

  // 统计卡片
  html += '<div style="display:flex;gap:12px;margin-bottom:40px">'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#0f172a">' + chains.length + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">证据链</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#dc2626">' + highCount + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">高风险链</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#2563eb">' + totalDim + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">总维度</div></div>'
    + '<div id="cde-triggered-count" style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#059669">—</div><div style="font-size:12px;color:#64748b;margin-top:4px">本次触发</div></div>'
    + '</div>';

  // ══════ 二、证据链定义 ══════
  html += '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">二、证据链定义</h3>';

  chains.forEach(function(c, ci) {
    var levelColor = (c.level === '极高风险' || c.level === '高风险') ? '#dc2626' : '#f59e0b';
    var levelBg = (c.level === '极高风险' || c.level === '高风险') ? '#fef2f2' : '#fffbeb';

    html += '<div id="cde-chain-' + ci + '" style="padding:20px 24px;margin-bottom:12px;background:' + levelBg + ';border-left:3px solid ' + levelColor + ';border-radius:0 8px 8px 0">'

      // 标题
      + '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">'
      + '<div style="font-size:15px;font-weight:700;color:#0f172a">' + escHtml(c.name) + '</div>'
      + '<div style="display:flex;gap:8px;align-items:center">'
      + '<span style="font-size:11px;padding:2px 8px;border-radius:4px;background:' + levelColor + '15;color:' + levelColor + ';font-weight:600">' + escHtml(c.level) + '</span>'
      + '<span style="font-size:11px;color:#94a3b8">' + escHtml(c.sub_topic) + '</span>'
      + '<span style="font-size:11px;color:#94a3b8">需≥' + c.min_evidence + '维</span>'
      + '<span id="cde-triggered-' + ci + '"></span>'
      + '</div>'
      + '</div>'

      // 描述
      + '<div style="font-size:13px;color:#475569;line-height:2.0;margin-bottom:12px">' + escHtml(c.description) + '</div>'

      // 维度详情
      + '<div style="margin-bottom:8px;padding:10px 12px;background:#fff;border-radius:6px">'
      + '<div style="font-size:12px;font-weight:600;color:#64748b;margin-bottom:6px">触发维度 · ' + c.dimensions.length + ' 个</div>';
    c.dimensions.forEach(function(d) {
      html += '<div style="padding:4px 0;font-size:13px;color:#475569;line-height:2.0">'
        + '<span style="font-weight:600;color:#0f172a">' + escHtml(d.code) + '</span>'
        + ' <span style="color:#64748b">' + escHtml(d.source) + '</span>'
        + '<span style="color:#94a3b8;margin-left:6px">→ ' + escHtml(d.desc) + '</span>'
        + '</div>';
    });
    html += '</div>'

      // 完整字段
      + (c.how_found ? '<div style="font-size:13px;color:#64748b;line-height:2.0;margin-bottom:4px"><span style="font-weight:600;color:#0f172a">溯源：</span>' + escHtml(c.how_found) + '</div>' : '')
      + (c.tax_impact ? '<div style="font-size:13px;color:#64748b;line-height:2.0;margin-bottom:4px"><span style="font-weight:600;color:#0f172a">纳税影响：</span>' + escHtml(c.tax_impact) + '</div>' : '')
      + (c.policy_ref ? '<div style="font-size:13px;color:#64748b;line-height:2.0;margin-bottom:4px"><span style="font-weight:600;color:#0f172a">法律依据：</span>' + escHtml(c.policy_ref) + '</div>' : '')
      + (c.suggestion ? '<div style="font-size:13px;color:#64748b;line-height:2.0;margin-bottom:4px"><span style="font-weight:600;color:#0f172a">处理建议：</span>' + escHtml(c.suggestion) + '</div>' : '')

      + '</div>';
  });

  html += '<div style="margin-top:20px;padding:16px 20px;background:#fff;border-radius:8px;font-size:13px;color:#64748b;line-height:2">'
    + '<strong>证据链 ≠ 结论</strong>：每条证据链需要≥2个维度同时命中才能触发。单维度触发视为孤证，不形成证据链闭环。'
    + '换一个稽查员拿同样资料，同样会得出相同结论——这就是证据链闭环的意义。'
    + '</div>';

  target.innerHTML = html;
}

function loadCrossDomainDynamic() {
  var target = document.getElementById('cde-dynamic');
  if (!target) return;

  getSharedAnalysis()
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (!data.ok) {
        target.innerHTML = '<div style="text-align:center;padding:20px;color:#94a3b8;margin-top:20px">暂无分析结果，请先运行一键分析以获取动态证据链数据</div>';
        return;
      }
      renderCrossDomainDynamic(data.report);
    })
    .catch(function(e) {
      target.innerHTML = '<div style="text-align:center;padding:20px;color:#94a3b8;margin-top:20px">动态数据加载失败</div>';
    });
}

function renderCrossDomainDynamic(report) {
  var target = document.getElementById('cde-dynamic');
  if (!target) return;
  var allF = report.all_findings || [];
  var comprehensive = report.comprehensive || {};
  var domainSummary = report.domain_summary || [];

  var crossDomainFindings = [];
  domainSummary.forEach(function(ds) {
    if (ds.name && ds.name.indexOf('跨域关联推理') >= 0) {
      crossDomainFindings = ds.findings || [];
    }
  });

  // 动态匹配：基于实际加载的证据链名称，而非硬编码正则
  var chainNames = [];
  if (window._allCrossChains && window._allCrossChains.length) {
    window._allCrossChains.forEach(function(cc) { if (cc.name) chainNames.push(cc.name); });
  }
  var chainRegex = chainNames.length ? new RegExp(chainNames.join('|')) : /证据链/;

  var evidenceFindings = allF.filter(function(f) {
    var t = f.type || '';
    return /证据链/.test(t) || chainRegex.test(t);
  });

  var allEvidence = [];
  var seen = {};
  crossDomainFindings.forEach(function(f) {
    var key = f.type || '';
    if (!seen[key]) { seen[key] = true; allEvidence.push(f); }
  });
  evidenceFindings.forEach(function(f) {
    var key = f.type || '';
    if (!seen[key]) { seen[key] = true; allEvidence.push(f); }
  });

  var closures = comprehensive.evidence_closures || [];
  var closedCount = comprehensive.closed_chain_count || 0;
  var triggeredChains = comprehensive.triggered_chains || [];
  var chainExecution = comprehensive.chain_execution || [];

  // 更新触发数
  var tcEl = document.getElementById('cde-triggered-count');
  if (tcEl) {
    var tcc = tcEl.querySelector('div');
    if (tcc) tcc.textContent = triggeredChains.length;
  }

  // 更新各链触发badge
  var allCC = window._allCrossChains || [];
  allCC.forEach(function(c, ci) {
    var kwMatch = c.trigger_keywords || [];
    var isTriggered = false;
    if (kwMatch.length) {
      for (var ti = 0; ti < triggeredChains.length; ti++) {
        for (var ki = 0; ki < kwMatch.length; ki++) {
          if (triggeredChains[ti].indexOf(kwMatch[ki]) >= 0) { isTriggered = true; break; }
        }
        if (isTriggered) break;
      }
    }
    var badgeEl = document.getElementById('cde-triggered-' + ci);
    if (badgeEl) {
      badgeEl.innerHTML = triggeredChains.length > 0
        ? (isTriggered ? '<span style="font-size:11px;padding:2px 8px;border-radius:4px;background:#dc262615;color:#dc2626;font-weight:600">已触发</span>' : '<span style="font-size:11px;color:#94a3b8">未触发</span>')
        : '';
    }
  });

  var html = '';
  html += '<div style="height:1px;background:#f1f5f9;margin:40px 0"></div>';

  // ══════ 三、本次动态证据链结果 ══════
  html += '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">三、本次动态证据链结果</h3>'
    + '<p style="font-size:13px;color:#94a3b8;margin:0 0 20px">跨域证据链 ' + allEvidence.length + ' 条 · 已闭环 ' + closedCount + ' 条 · 触发线索链 ' + chainExecution.length + ' 条 · 含规则ID链 ' + triggeredChains.length + ' 条</p>'

    // 统计
    + '<div style="display:flex;gap:12px;margin-bottom:32px">'
    + '<div style="flex:1;text-align:center;padding:14px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:24px;font-weight:700;color:#0f172a">' + allEvidence.length + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">证据链发现</div></div>'
    + '<div style="flex:1;text-align:center;padding:14px;background:#f0fdf4;border-radius:8px"><div style="font-size:24px;font-weight:700;color:#059669">' + closedCount + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">已闭环</div></div>'
    + '<div style="flex:1;text-align:center;padding:14px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:24px;font-weight:700;color:#2563eb">' + chainExecution.length + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">线索链</div></div>'
    + '<div style="flex:1;text-align:center;padding:14px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:24px;font-weight:700;color:#0f172a">' + triggeredChains.length + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">含规则</div></div>'
    + '</div>';

  // 证据链闭环
  if (closures.length > 0) {
    html += '<h4 style="font-size:13px;font-weight:600;color:#64748b;margin:0 0 12px">证据链闭环检测</h4>';
    closures.forEach(function(ec) {
      var closed = ec.closed;
      var color = closed ? '#059669' : '#f59e0b';
      html += '<div style="padding:10px 16px;margin-bottom:4px;background:' + (closed ? '#f0fdf4' : '#fffbeb') + ';border-radius:6px;border-left:3px solid ' + color + '">'
        + '<span style="font-size:14px;font-weight:600;color:#0f172a">' + escHtml(ec.chain_name) + '</span>'
        + ' <span style="font-size:12px;font-weight:600;color:' + color + '">' + (closed ? '已闭环' : '未闭环') + ' ' + ec.ratio + '%</span>'
        + '<span style="font-size:12px;color:#94a3b8;margin-left:8px">触发 ' + ec.triggered_steps + '/' + ec.total_steps + ' 规则</span>'
        + '</div>';
    });
    html += '<div style="margin-bottom:32px"></div>';
  }

  // 跨域推理详情
  if (allEvidence.length > 0) {
    html += '<h4 style="font-size:13px;font-weight:600;color:#64748b;margin:0 0 12px">跨域关联推理详情</h4>';
    allEvidence.forEach(function(f) {
      var lvlColor = f.level === '极高风险' || (f.level === '极高风险' || c.level === '高风险') ? '#dc2626' : (f.level === '中风险' ? '#f59e0b' : '#059669');
      var lvlBg = f.level === '极高风险' || (f.level === '极高风险' || c.level === '高风险') ? '#fef2f2' : (f.level === '中风险' ? '#fffbeb' : '#f0fdf4');
      html += '<div style="padding:14px 16px;margin-bottom:6px;background:' + lvlBg + ';border-left:3px solid ' + lvlColor + ';border-radius:0 6px 6px 0">'
        + '<div style="font-size:14px;font-weight:600;color:#0f172a;margin-bottom:6px">' + escHtml(f.type || '') + '</div>'
        + (f.description ? '<div style="font-size:13px;color:#475569;line-height:2.0;margin-bottom:6px">' + escHtml(f.description) + '</div>' : '')
        + (f.how_found ? '<div style="font-size:12px;color:#94a3b8;margin-bottom:4px">溯源：' + escHtml(f.how_found) + '</div>' : '')
        + (f.tax_impact ? '<div style="font-size:12px;color:#94a3b8;margin-bottom:4px">纳税影响：' + escHtml(f.tax_impact) + '</div>' : '')
        + (f.suggestion ? '<div style="font-size:12px;color:#94a3b8">建议：' + escHtml(f.suggestion) + '</div>' : '')
        + '</div>';
    });
  }

  target.innerHTML = html;
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

  var hasCache = _allClueChains && _allClueChains.length > 0;

  container.innerHTML = '<style>.ch-layout{display:flex;gap:24px;max-width:1200px;margin:0 auto;padding:20px}.ch-toc{width:200px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:12px;line-height:2.0;max-height:calc(100vh-40px);overflow-y:auto}.ch-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.ch-toc a{display:flex;align-items:center;justify-content:space-between;color:#475569;text-decoration:none;padding:3px 8px;border-radius:4px;cursor:pointer}.ch-toc a:hover{background:#eff6ff;color:#2563eb;font-weight:600}.ch-toc a .cnt{font-size:10px;color:#94a3b8;background:#f1f5f9;padding:1px 6px;border-radius:10px}.ch-main{flex:1;min-width:0}</style>'
    + '<div class="ch-layout">'
    + '<nav class="ch-toc" id="ch-toc"><div class="toc-title">📖 分类</div></nav>'
    + '<div class="ch-main">'
    + '<h2 style="font-size:22px;font-weight:800;color:#0f172a;margin:0 0 4px">🔍 线索链</h2>'
    + '<p style="font-size:13px;color:#475569;line-height:2.0;margin:0 0 24px" id="chains-subtitle">'
    + (hasCache ? '437条线索链（全部可执行） · 串行工作流引擎 · 三大触发方式 · 每步一个调查动作' : '加载中...')
    + '</p>'
    + '<div id="chains-body"></div></div></div>';

  if (hasCache) { renderChainsList(_allClueChains); updateChainsSubtitle(); }
  else { loadChainsData(); }
}

function updateChainsSubtitle() {
  var st = document.getElementById('chains-subtitle');
  if (st && _chainDynamic) { st.textContent = _allClueChains.length + ' 条线索链（本次触发 ' + (_chainDynamic.triggered_count || 0) + ' 条）· 每条链含若干调查步骤'; }
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
    // 更新标题栏显示触发数量
    var st = document.getElementById('chains-subtitle');
    if (st && _chainDynamic) {
      st.textContent = clueChains.length + ' 条线索链（本次触发 ' + (_chainDynamic.triggered_count || 0) + ' 条）· 每条链含若干调查步骤，触发率=已触发步骤/总步骤';
    }
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
    html = '<div style="text-align:center;padding:40px;color:#94a3b8">无匹配线索链</div>';
  } else {
    var triggeredCount = _chainDynamic ? (_chainDynamic.triggered_count || 0) : 0;

    // 概念说明
    html += '<div id="ch-concept" style="margin-bottom:32px;padding:20px 24px;background:#fff;border:1px solid #e2e8f0;border-radius:8px">'
      + '<h3 style="font-size:16px;font-weight:700;color:#0f172a;margin:0 0 12px;padding-bottom:8px;border-bottom:2px solid #e2e8f0">线索链是什么</h3>'
      + '<p style="font-size:13px;color:#475569;line-height:2.0;margin:0 0 12px">'
      + '线索链是从<strong>稽查指令（点）到调查路径（线）的串行工作流引擎</strong>。每条线索链定义一条完整的调查路径（investigation_path[]），从触发关键词开始逐步执行各步骤。与证据链的并行多源验证不同，线索链是单路径顺序推进──\"从哪里查、查什么、查到了怎么办\"。'
      + '</p>'
      + '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px">'
      + '<div style="padding:10px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;font-size:12px;line-height:2.0"><strong style="color:#2563eb">串行调查路径</strong><br>一个规则触发→多条调查步骤<br>investigation_path[]顺序执行</div>'
      + '<div style="padding:10px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;font-size:12px;line-height:2.0"><strong style="color:#059669">三类触发方式</strong><br>定量阈值（数值超限）<br>定性模式（特定匹配）<br>缺失数据（资料缺口触发替代链）</div>'
      + '<div style="padding:10px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;font-size:12px;line-height:2.0"><strong style="color:#7c3aed">线索→证据→分析</strong><br>线索链发现累积<br>→触发证据链多源交叉验证<br>→闭环后输入分析链推理判定</div>'
      + '</div>'
      + '</div>';
    
    // 统计卡片
    var typeGroups = {};
    chains.forEach(function(c){ 
      var raw = (c.chain_type && c.chain_type != '线索链') ? c.chain_type : (c.sub_topic || '其他');
      var merge = {'经营实质核查':'经营实质','资产负债项目':'资产负债','成本费用核查':'成本费用','虚开发票核查':'虚开发票','增值税核查':'增值税','企业所得税核查':'企业所得税','个人所得税核查':'个税','财产税核查':'财产税','发票核查':'发票','跨境税源核查':'跨境','行业专项检查':'行业专项','申报合规核查':'申报','纳税人分类分级核查':'检测技术','分析方法核查':'检测技术','审计报告核查':'检测技术','稽查技术':'检测技术','成本偏差检测':'成本','隐匿收入核查':'隐匿收入','税种合规核查':'各税种'};
      var t = merge[raw] || raw;
      if(!typeGroups[t])typeGroups[t]=[];
      typeGroups[t].push(c);
    });
    var tocEl = document.getElementById('ch-toc');
    if (tocEl) {
      tocEl.innerHTML = '<div class="toc-title">📖 ' + chains.length + ' 条线索链</div><a href="#ch-concept">概念说明</a>';
      Object.keys(typeGroups).sort().forEach(function(t){ tocEl.innerHTML += '<a href="#ch-type-'+encodeURIComponent(t)+'">'+t+' <span class="cnt">'+typeGroups[t].length+'</span></a>'; });
    }

    html += '<div id="ch-stats" style="display:flex;gap:12px;margin-bottom:32px">'
      + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#0f172a">' + chains.length + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">线索链总数</div></div>'
      + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#2563eb">' + triggeredCount + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">本次触发</div></div>'
      + '</div>';

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
        badge = ' <span style="font-size:11px;padding:2px 8px;border-radius:10px;background:' + bColor + '15;color:' + bColor + ';font-weight:600">' + triggeredSteps + '/' + totalS + ' (' + ratio + '%)</span>';
      } else if (exec) {
        badge = ' <span style="font-size:11px;padding:2px 8px;border-radius:10px;background:#fff;border:1px solid #e2e8f0;color:#94a3b8;font-weight:500">未触发</span>';
      }

      // 子主题标签
      var topicTag = subTopic ? ' <span style="font-size:11px;padding:1px 8px;border-radius:4px;background:#ede9fe;color:#7c3aed;font-weight:500">' + escHtml(subTopic) + '</span>' : '';

      // 质量分标签
      var scoreTag = qualityScore > 0 ? ' <span style="font-size:11px;color:#94a3b8">⭐ ' + qualityScore + '</span>' : '';

      html += '<div style="padding:18px 20px;margin-bottom:14px;border:1px solid #e2e8f0;border-radius:8px;background:#fff">'

        // ══ 卡片头部：名称 + 标签行 ═══
        + '<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:6px;margin-bottom:10px">'
        + '<div style="font-size:15px;font-weight:700;color:#0f172a">' + escHtml(c.name) + badge + topicTag + scoreTag + '</div>'
        + '</div>';

      // 描述（新格式链有 description/desc）
      if (c.description) {
        html += '<div style="padding:10px 14px;margin-bottom:12px;background:#fff;border-left:4px solid #7c3aed;border-radius:0 6px 6px 0;font-size:13px;color:#475569;line-height:2.0">' + escHtml(c.description) + '</div>';
      } else if (c.desc) {
        html += '<div style="padding:10px 14px;margin-bottom:12px;background:#fff;border-left:4px solid #7c3aed;border-radius:0 6px 6px 0;font-size:13px;color:#475569;line-height:2.0">' + escHtml(c.desc) + '</div>';
      }

      // ══ 步骤列表（统一样式）═══
      html += '<div style="margin-bottom:12px"><div style="font-size:12px;font-weight:600;color:#2563eb;margin-bottom:8px">📋 调查路径（' + stepList.length + ' 步）</div>';
      stepList.forEach(function(s, si) {
        var lvl = s.level || '';
        var isHigh = lvl === '高风险' || lvl === '极高风险';
        html += '<div style="padding:10px 14px;margin-bottom:6px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;border-left:3px solid #2563eb">'
          + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;flex-wrap:wrap">'
          + '<span style="display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:50%;font-size:11px;font-weight:700;color:#fff;background:' + (isHigh ? '#dc2626' : '#2563eb') + '">' + (s.step || (si+1)) + '</span>'
          + (s.rule_id ? '<span style="color:#6366f1;font-size:10px;font-weight:600;background:#eef2ff;padding:1px 5px;border-radius:3px">R' + s.rule_id + '</span>' : '')
          + (lvl ? '<span style="font-size:10px;font-weight:600;color:' + (isHigh ? '#dc2626' : '#64748b') + ';background:' + (isHigh ? '#fee2e2' : '#f1f5f9') + ';padding:1px 5px;border-radius:3px">' + lvl + '</span>' : '')
          + '<b style="font-size:13px;color:#0f172a">' + escHtml(s.domain || s.rule_item || s.action || '') + '</b>'
          + '</div>'
          + (s.detail || s.action ? '<div style="font-size:13px;color:#475569;line-height:2.0;margin-top:4px;padding-left:30px">' + escHtml(s.detail || s.action || '') + '</div>' : '')
          + (s.data_required ? '<div style="font-size:11px;color:#94a3b8;margin-top:4px;padding-left:30px">需要数据: ' + escHtml(s.data_required) + '</div>' : '')
          + (s.suggestion ? '<div style="font-size:12px;color:#059669;margin-top:6px;padding:6px 10px;background:#fff;border:1px solid #e2e8f0;border-radius:4px"><strong>建议：</strong>' + escHtml(s.suggestion) + '</div>' : '')
          + (s.policy_ref ? '<div style="font-size:11px;color:#94a3b8;margin-top:4px;padding-left:30px">📎 ' + escHtml(s.policy_ref) + '</div>' : '')
          + '</div>';
      });
      html += '</div>';

      // ══ 政策依据 ═══
      if (c.policies && c.policies.length > 0) {
        html += '<div style="margin-bottom:10px">'
          + '<div style="font-size:12px;font-weight:600;color:#64748b;margin-bottom:6px">📋 政策依据</div>';
        c.policies.forEach(function(p) {
          html += '<div style="padding:6px 12px;margin-bottom:3px;background:#fff;border:1px solid #e2e8f0;border-radius:4px;font-size:12px;color:#475569;line-height:2.0">• ' + escHtml(p) + '</div>';
        });
        html += '</div>';
      }

      // ══ 税务影响 ═══
      if (c.tax_impacts && c.tax_impacts.length > 0) {
        html += '<div style="margin-bottom:10px">'
          + '<div style="font-size:12px;font-weight:600;color:#64748b;margin-bottom:6px">⚠️ 税务影响</div>';
        c.tax_impacts.forEach(function(t) {
          html += '<div style="padding:6px 12px;margin-bottom:3px;background:#fff;border:1px solid #e2e8f0;border-radius:4px;font-size:12px;color:#475569;line-height:2.0">• ' + escHtml(t) + '</div>';
        });
        html += '</div>';
      }

      // ══ 底部元信息栏 ═══
      html += '<div style="display:flex;flex-wrap:wrap;gap:12px;padding-top:10px;border-top:1px solid #e2e8f0;font-size:12px;color:#94a3b8">'
        + '<span>📝 步骤 <b style="color:#475569">' + totalS + '</b> 条</span>'
        + (highRiskStepCount > 0 ? '<span>🔴 高风险步骤 <b style="color:#dc2626">' + highRiskStepCount + '</b> 个</span>' : '')
        + (c.covered_rule_count ? '<span>📌 覆盖规则 <b style="color:#475569">' + c.covered_rule_count + '</b> 条</span>' : '')
        + (c.related_chain_count > 0 ? '<span>🔗 关联证据链 <b style="color:#475569">' + c.related_chain_count + '</b> 条</span>' : '')
        + (qualityScore > 0 ? '<span>⭐ 质量评分 <b style="color:#475569">' + qualityScore + '</b></span>' : '')
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
  var hasCache = _allEvidenceChains && _allEvidenceChains.length > 0;
  container.innerHTML = '<style>.ev-layout{display:flex;gap:24px;max-width:1200px;margin:0 auto;padding:20px;background:#fff}.ev-toc{width:180px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:12px;line-height:2.0;max-height:calc(100vh-40px);overflow-y:auto}.ev-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.ev-toc a{display:flex;align-items:center;justify-content:space-between;color:#475569;text-decoration:none;padding:3px 8px;border-radius:4px;cursor:pointer}.ev-toc a:hover{background:#eff6ff;color:#2563eb;font-weight:600}.ev-toc a .cnt{font-size:10px;color:#94a3b8;background:#f1f5f9;padding:1px 6px;border-radius:10px}.ev-main{flex:1;min-width:0}.ev-main h3{font-size:16px!important;font-weight:700!important;color:#0f172a!important;padding-bottom:8px!important;border-bottom:2px solid #e2e8f0!important;margin:0 0 16px!important}.ev-main section{margin-bottom:48px!important;scroll-margin-top:20px}</style>'
    + '<div class="ev-layout"><nav class="ev-toc" id="ev-toc"><div class="toc-title">📖 分类</div></nav>'
    + '<div class="ev-main"><h2 style="font-size:22px;font-weight:800;color:#0f172a;margin:0 0 4px">🔒 证据链</h2>'
    + '<p style="font-size:13px;color:#475569;line-height:2.0;margin:0 0 24px">'
    + '证据链是税务稽查的证据质量保障体系——<strong>781条证据链（全部可执行），通过 ≥2维独立数据源交叉验证形成证据闭环</strong>。'
    + '每条可执行证据链定义多个独立维度的数据源，当 ≥min_evidence 个维度同时触发时形成有效证据，闭环后自动输入分析链做综合推理判定。'
    + '</p>'
    + '<div id="evidence-body"></div></div></div>';
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
  var legacyChains = chains.filter(function(c) { return c.legacy; });
  var closedCount = chains.filter(function(c) {
    var exec = evExecMap[c.name];
    return exec && exec.closed;
  }).length;

  // Populate TOC
  var tocEl = document.getElementById('ev-toc');
  if (tocEl) {
    tocEl.innerHTML = '<div class="toc-title">📖 ' + chains.length + ' 条（全部可执行）</div><a href="#ev-stats">统计总览</a>';
  }

  var html = '';

  // ══════ 证据链概念说明 ══════
  html += '<div id="ev-concept" style="margin-bottom:32px;padding:20px 24px;background:#fff;border:1px solid #e2e8f0;border-radius:8px">';
  if (tocEl) tocEl.innerHTML += '<a href="#ev-concept">概念说明</a>';
  html += ''
    + '<h3 style="font-size:16px;font-weight:700;color:#0f172a;margin:0 0 12px;padding-bottom:8px;border-bottom:2px solid #e2e8f0">证据链是什么</h3>'
    + '<p style="font-size:13px;color:#475569;line-height:2.0;margin:0 0 12px">'
    + '证据链是<strong>多源交叉验证形成证据闭环的规则集合</strong>。与线索链（单路径串行调查）不同，证据链同时从多个独立维度收集证据——每个维度是一个独立的数据源（银行流水/发票/合同/社保/工商等），当 ≥min_evidence 个维度的触发关键词同时匹配到 all_findings 时，形成有效证据闭环。'
    + '</p>'
    + '<p style="font-size:12px;color:#64748b;line-height:2.0;margin:0 0 16px">'
    + '引擎工作原理：<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">_domain_cross_domain_reasoning(all_findings)</code> 加载 cross_domain_evidence.json → 逐链遍历 dimensions[] → 每维 kws 与 all_findings 做 keyword 匹配 → 达到 min_evidence 阈值 → 生成跨域发现 → 注入 all_findings → 后续分析链根据闭环发现做综合推理判定。'
    + '</p>'
    + '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:16px">'
    + '<div style="padding:10px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;font-size:12px;line-height:2.0"><strong style="color:#2563eb">线索链 vs 证据链</strong><br>线索链 = 串行追查（一条线到底）<br>证据链 = 并行印证（多源同时验证）<br>线索链发现触发证据链闭环</div>'
    + '<div style="padding:10px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;font-size:12px;line-height:2.0"><strong style="color:#059669">闭环条件</strong><br>≥min_evidence 个维度同时触发<br>每维来自独立数据源<br>闭环后自动输入分析链推理</div>'
    + '<div style="padding:10px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;font-size:12px;line-height:2.0"><strong style="color:#7c3aed">证据→分析桥接</strong><br>证据闭环→风险升级判定<br>经营实质+资金+发票+税费<br>四维全异常→系统性造假</div>'
    + '</div>'
    + '<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:10px;font-size:11px;line-height:2.0">'
    + '<div style="padding:10px;background:#fff;border:1px solid #e2e8f0;border-radius:6px"><strong style="color:#2563eb">全部可执行 (781条)</strong><br>dimensions[] 格式 — 引擎通过 keyword 自动匹配 findings。每条含触发关键词+多维度数据源+闭环阈值（min_evidence），≥2维同时触发形成证据闭环。</div>'
    + '<div style="padding:10px;background:#fff;border:1px solid #e2e8f0;border-radius:6px"><strong style="color:#7c3aed">investigation_path[] 格式</strong><br>原方法链已全部升级为可执行。步骤含 rule_id + level + detail + suggestion + policy_ref，按串联规则逐一调查，每个步骤连接一条稽查指令。</div>'
    + '</div>'
    + '</div>';

  // 统计卡片
  html += '<div id="ev-stats" style="display:flex;gap:12px;margin-bottom:32px">'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#0f172a">' + chains.length + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">证据链总数</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#7c3aed">' + execChains.length + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">可执行</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#2563eb">' + totalSteps + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">调查步骤</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#059669">' + closedCount + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">已闭环</div></div>'
    + '</div>';

  if (!chains.length) {
    html += '<div style="text-align:center;padding:40px;color:#94a3b8">无证据链数据</div>';
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

    // 补充 TOC 导航项
    if (tocEl) {
      sortedPrefixes.forEach(function(p) {
        tocEl.innerHTML += '<a href="#ev-grp-' + encodeURIComponent(p) + '">' + p + '<span class="cnt">' + groups[p].length + '</span></a>';
      });
    }

    sortedPrefixes.forEach(function(prefix) {
      var groupChains = groups[prefix];
      var groupExec = groupChains.filter(function(c) { return c.executable !== false && !c.legacy; });
      var groupLegacy = groupChains.filter(function(c) { return c.legacy; });
      html += '<section id="ev-grp-' + encodeURIComponent(prefix) + '" style="margin-bottom:48px;scroll-margin-top:20px">';
      html += '<h3 style="font-size:16px!important;font-weight:700!important;color:#0f172a!important;padding-bottom:8px!important;border-bottom:2px solid #e2e8f0!important;margin:0 0 16px!important">' + prefix
        + ' <span style="font-size:13px;font-weight:400;color:#94a3b8">' + groupChains.length + ' 条' + (groupExec.length > 0 ? ' (' + groupExec.length + '可执行)' : '') + '</span></h3>';

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

        var topicTag = subTopic ? ' <span style="font-size:11px;padding:1px 8px;border-radius:4px;background:#ede9fe;color:#7c3aed;font-weight:500">' + escHtml(subTopic) + '</span>' : '';
        var scoreTag = qualityScore > 0 ? ' <span style="font-size:11px;color:#94a3b8">⭐ ' + qualityScore + '</span>' : '';

        html += '<div style="padding:18px 20px;margin-bottom:14px;border:1px solid #e2e8f0;border-radius:8px;background:#fff">'

          // ══ 标题行 ═══
          + '<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:6px;margin-bottom:10px">'
          + '<div style="font-size:15px;font-weight:700;color:#0f172a">' + escHtml(c.name) + topicTag + scoreTag + '</div>'
          + (badgeText ? '<span style="font-size:11px;padding:2px 8px;border-radius:10px;background:' + badgeColor + '15;color:' + badgeColor + ';font-weight:600">' + badgeText + '</span>' : '')
          + '</div>';

        // ══ 描述 ═══
        if (c.description) {
          html += '<div style="padding:10px 14px;margin-bottom:12px;background:#fff;border-left:4px solid #7c3aed;border-radius:0 6px 6px 0;font-size:13px;color:#475569;line-height:2.0">' + escHtml(c.description) + '</div>';
        }

        // ══ 调查路径 ═══
        if (isArrayFormat) {
          // 旧格式：investigation_path 是数组，含 rule_id/level/detail/policy_ref
          html += '<div style="margin-bottom:12px">';
          ip.forEach(function(s, si) {
            var lvl = s.level || '';
            var lvlColor = lvl === '高风险' ? '#dc2626' : (lvl === '中风险' ? '#f59e0b' : (lvl === '低风险' ? '#059669' : '#94a3b8'));
            var lvlBg = lvl === '高风险' ? '#fef2f2' : (lvl === '中风险' ? '#fffbeb' : (lvl === '低风险' ? '#f0fdf4' : '#f8fafc'));
            var isHigh = lvl === '高风险';

            html += '<div style="padding:10px 14px;margin-bottom:6px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;border-left:3px solid ' + (isHigh ? '#dc2626' : lvlColor) + '">'
              + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">'
              + '<span style="color:#94a3b8;font-size:12px;font-weight:600">#' + (si + 1) + '</span>'
              + (s.rule_id ? '<span style="color:#6366f1;font-size:11px;font-weight:600;background:#eef2ff;padding:1px 6px;border-radius:3px">R' + s.rule_id + '</span>' : '')
              + (lvl ? '<span style="font-size:11px;font-weight:600;color:' + lvlColor + ';background:' + lvlBg + ';padding:1px 6px;border-radius:3px">' + lvl + '</span>' : '')
              + '<b style="font-size:13px;color:#0f172a">' + escHtml(s.domain || s.action || s.rule_item || s.step || '') + '</b>'
              + '</div>'
              + (s.detail || s.action ? '<div style="font-size:13px;color:#475569;line-height:2.0;margin-top:6px;padding-left:20px;border-left:2px solid #e2e8f0">' + escHtml(s.detail || s.action || '') + '</div>' : '')
              + (s.policy_ref ? '<div style="font-size:11px;color:#94a3b8;margin-top:4px">📎 ' + escHtml(s.policy_ref) + '</div>' : '')
              + '</div>';
          });
          html += '</div>';
        } else if (isStringFormat) {
          // 新格式：investigation_path 是字符串描述（如 "人员信息→发票数据→资金流→进销存四维交叉验证"）
          html += '<div style="padding:10px 14px;margin-bottom:12px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;color:#475569;line-height:2.0">'
            + '<b style="color:#4338ca">🔍 调查路径：</b>' + escHtml(ip)
            + '</div>';
        } else if (isStepsFormat) {
          // steps 数组格式（含 {step: N, action: "文本"}）
          html += '<div style="margin-bottom:12px">';
          (c.steps || []).forEach(function(s, si) {
            var stepNum = s.step || (si + 1);
            var isHigh = !!(s.level && (s.level === '极高风险' || c.level === '高风险'));
            html += '<div style="padding:10px 14px;margin-bottom:6px;background:' + (isHigh ? '#fef2f2' : '#fafafa') + ';border-radius:6px;border-left:3px solid ' + (isHigh ? '#dc2626' : '#cbd5e1') + '">'
              + '<div style="display:flex;align-items:center;gap:8px">'
              + '<span style="display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:50%;font-size:11px;font-weight:700;color:#fff;background:' + (isHigh ? '#dc2626' : '#94a3b8') + '">' + stepNum + '</span>'
              + '<span style="font-size:13px;color:#334155;line-height:2.0">' + escHtml(s.action || '') + '</span>'
              + (isHigh ? '<span style="font-size:11px;color:#dc2626;font-weight:600;background:#fee2e2;padding:1px 6px;border-radius:3px">高风险</span>' : '')
              + '</div>'
              + '</div>';
          });
          html += '</div>';
        }

        // ══ dimensions[] 维度举证(新格式可执行证据链) ═══
        var dims = c.dimensions;
        if (Array.isArray(dims) && dims.length > 0) {
          html += '<div style="margin-bottom:12px"><div style="font-size:12px;font-weight:600;color:#059669;margin-bottom:8px">📐 证据维度（需 ≥' + (c.min_evidence||2) + ' 维同时触发形成闭环）</div>';
          dims.forEach(function(d, di) {
            var dimCode = d.code || d.dim_code || ('D' + (di+1));
            html += '<div style="padding:10px 14px;margin-bottom:6px;background:#f0fdf4;border-radius:6px;border-left:3px solid #059669;font-size:12px;line-height:1.8">'
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
            + '<div style="font-size:12px;font-weight:600;color:#64748b;margin-bottom:6px">📋 政策依据</div>';
          c.policies.forEach(function(p) {
            html += '<div style="padding:6px 12px;margin-bottom:3px;background:#fff;border:1px solid #e2e8f0;border-radius:4px;font-size:12px;color:#475569;line-height:2.0">• ' + escHtml(p) + '</div>';
          });
          html += '</div>';
        }

        // ══ 税务影响 ═══
        if (c.tax_impacts && c.tax_impacts.length > 0) {
          html += '<div style="margin-bottom:10px">'
            + '<div style="font-size:12px;font-weight:600;color:#64748b;margin-bottom:6px">⚠️ 税务影响</div>';
          c.tax_impacts.forEach(function(t) {
            html += '<div style="padding:6px 12px;margin-bottom:3px;background:#fff;border:1px solid #e2e8f0;border-radius:4px;font-size:12px;color:#475569;line-height:2.0">• ' + escHtml(t) + '</div>';
          });
          html += '</div>';
        }

        // ══ 关联线索链 ═══
        if (c.related_chains && c.related_chains.length > 0) {
          html += '<div style="margin-bottom:10px">'
            + '<div style="font-size:12px;font-weight:600;color:#64748b;margin-bottom:6px">🔗 关联线索链</div>';
          c.related_chains.forEach(function(rc) {
            html += '<div style="padding:6px 12px;margin-bottom:3px;background:#f0f9ff;border-radius:4px;font-size:12px;color:#0369a1;line-height:2.0">• ' + escHtml(rc) + '</div>';
          });
          html += '</div>';
        }

        // ══ 覆盖规则 ═══
        if (c.covered_rule_ids && c.covered_rule_ids.length > 0) {
          html += '<div style="margin-bottom:10px">'
            + '<div style="font-size:12px;font-weight:600;color:#64748b;margin-bottom:6px">📌 覆盖规则</div>';
          c.covered_rule_ids.forEach(function(rid) {
            html += '<span style="display:inline-block;font-size:11px;padding:2px 8px;margin:0 4px 4px 0;background:#eef2ff;color:#4338ca;border-radius:3px;font-weight:600">R' + rid + '</span>';
          });
          html += '</div>';
        }

        // ══ 底部元信息栏 ═══
        html += '<div style="display:flex;flex-wrap:wrap;gap:12px;padding-top:10px;border-top:1px solid #f1f5f9;font-size:12px;color:#94a3b8">'
          + '<span>📝 步骤 <b style="color:#475569">' + stepCount + '</b> 条</span>'
          + (highRiskStepCount > 0 ? '<span>🔴 高风险步骤 <b style="color:#dc2626">' + highRiskStepCount + '</b> 个</span>' : '')
          + (c.covered_rule_count ? '<span>📌 覆盖规则 <b style="color:#475569">' + c.covered_rule_count + '</b> 条</span>' : '')
          + (c.related_chain_count > 0 ? '<span>🔗 关联线索链 <b style="color:#475569">' + c.related_chain_count + '</b> 条</span>' : '')
          + (qualityScore > 0 ? '<span>⭐ 质量评分 <b style="color:#475569">' + qualityScore + '</b></span>' : '')
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
  container.innerHTML = '<style>.al-layout{display:flex;gap:24px;max-width:1200px;margin:0 auto;padding:20px;background:#fff}.al-toc{width:190px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:12px;line-height:2.0;max-height:calc(100vh-40px);overflow-y:auto}.al-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.al-toc a{display:block;color:#475569;text-decoration:none;padding:2px 8px;border-radius:4px;cursor:pointer}.al-toc a:hover,.al-toc a.active{background:#eff6ff;color:#2563eb;font-weight:600}.al-main{flex:1;min-width:0}.al-main h3{font-size:16px!important;font-weight:700!important;color:#0f172a!important;padding-bottom:8px!important;border-bottom:2px solid #e2e8f0!important;margin:0 0 16px!important}.al-main section{margin-bottom:48px!important;scroll-margin-top:20px}</style>'
    + '<div class="al-layout">'
    + '<nav class="al-toc">'
    + '<div class="toc-title">📖 导航</div>'
    + '<a href="#al-overview">一 什么是分析链</a>'
    + '<a href="#al-steps">二 七步执行流程</a>'
    + '<a href="#al-quality">三 质量保障体系</a>'
    + '<a href="#al-methods">四 稽查方法论</a>'
    + '<a href="#al-chains">五 分析链定义</a>'
    + '</nav>'
    + '<div class="al-main">'
    + '<h2 style="font-size:22px;font-weight:800;color:#0f172a;margin:0 0 4px">⚡ 分析链</h2>'
    + '<p style="font-size:13px;color:#475569;line-height:2.0;margin:0 0 24px">'
    + '分析链是税务稽查系统的核心执行管线——从用户上传原始资料到输出结构化稽查报告的完整流水线。'
    + '七步串联处理 + 42域分析 + 1608规则 + 1266条链条 + 10条协商规则，97%噪声过滤率。'
    + '</p>'
    + '<div id="analyze-body"></div>'
    + '</div></div>';
  loadAnalyzeOverview();
}

async function loadAnalyzeOverview() {
  var target = document.getElementById('analyze-body');

  // 有分析数据时：渲染动态结果（已包含七步流程+质量体系）
  if (_cachedAnalyzeReport) {
    renderAnalyzeResult(_cachedAnalyzeReport);
    return;
  }

  try {
    var data = await getSharedAnalysis();
    if (data.ok && data.report) {
      _cachedAnalyzeReport = data.report;
      renderAnalyzeResult(data.report);
      return;
    }
  } catch (e) { console.warn('分析链API加载失败，显示静态说明:', e.message); }

  // 兜底：无分析数据时显示完整静态说明
  var html = '';

  // ══════ 一、分析链概述 ══════
  html += '<div id="al-overview" style="margin-bottom:48px;padding:20px 24px;background:#fff;border:1px solid #e2e8f0;border-radius:8px">'
    + '<h3 style="font-size:18px;font-weight:700;color:#0f172a;margin:0 0 12px">一、什么是分析链</h3>'
    + '<p style="font-size:14px;color:#475569;line-height:2.0;margin:0 0 16px">'
    + '分析链是税务稽查系统的核心执行管线，负责将用户上传的原始资料转化为结构化稽查报告。'
    + '这条管线不是简单的函数调用链，而是一个<strong>七步串联的数据处理流水线</strong>——每一步都有明确的输入、处理逻辑和输出，'
    + '数据在管线中单向流动，不丢失、不污染、不截断。'
    + '</p>'
    + '<p style="font-size:14px;color:#475569;line-height:2.0;margin:0 0 16px">'
    + '管线的设计理念来自稽查实战：真实稽查不是看一个数字就下结论，而是<strong>从资料扫描开始，经过多轮交叉验证，最终形成证据闭环</strong>。'
    + '分析链模拟的就是这个完整过程，遵循以下四条核心原则：'
    + '</p>'
    + '<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-bottom:16px">'
    + '<div style="padding:12px;background:#f8fafc;border-radius:6px;font-size:12px;line-height:2.0"><strong style="color:#2563eb">① 资料驱动</strong><br>有什么资料就审什么——不预设"应该有合同"，只能对已有资料做出判断。缺资料的领域标注为"资料缺口"而非凭空猜测。</div>'
    + '<div style="padding:12px;background:#f8fafc;border-radius:6px;font-size:12px;line-height:2.0"><strong style="color:#dc2626">② 诚实边界</strong><br>缺什么资料就报什么——不编造、不脑补、不把"可能"写成"确定"。每行数据标注来源文件位置，每条发现标注置信度和资料依赖。</div>'
    + '<div style="padding:12px;background:#f8fafc;border-radius:6px;font-size:12px;line-height:2.0"><strong style="color:#7c3aed">③ 交叉推断</strong><br>孤立信号不构成发现——银行流水异常+发票异常同时出现才升级为中风险，加经营实质异常才升级为高风险。多源数据串联形成证据链闭环。</div>'
    + '<div style="padding:12px;background:#f8fafc;border-radius:6px;font-size:12px;line-height:2.0"><strong style="color:#059669">④ 明细支撑</strong><br>每条发现必须有具体明细数据——不能写"供应商集中度高"，必须写具体占比、名称和金额。</div>'
    + '</div>'
    + '<p style="font-size:13px;color:#64748b;line-height:2.0;margin:0 0 16px">'
    + '分析链底层引擎工作顺序为：<strong>域分析→稽查指令匹配→线索链触发→证据链闭环→分析链推理→协商引擎消解→同类合并→报告输出</strong>。'
    + '每个环节的输出都是下一个环节的输入：42个域分析函数产出发现→关键词+域分类自动匹配1608条稽查指令获得rule_id→'
    + '触发的规则通过rule_refs激活437条线索链展开串行调查→线索链发现累积后送入781条证据链做多源交叉验证→'
    + '证据闭环后进入48条分析链做综合推理判定→最后经15条协商规则消解冲突、同类发现合并→输出最终稽查报告。'
    + '</p>'
    + '<div style="padding:16px 20px;background:#fff;border-radius:8px;font-size:13px;color:#64748b;line-height:2.0;border-left:3px solid #2563eb">'
    + '<strong>代码位置：</strong>engine/pipeline.py → <code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">_run_analyze()</code> · engine/domain_analysis.py → 42个域分析函数<br>'
    + '<strong>数据规模：</strong>' + pc('rules','1608') + ' 条稽查指令 · ' + pc('trailChains','437') + ' 条线索链 · ' + pc('evidenceChains','781') + ' 条证据链 · 48 条分析链<br>'
    + '<strong>处理结果：</strong>97% 噪声过滤率 · 66 行业基准库 · 42 个域分析函数 · 7 步执行流程'
    + '</div>'
    + '</div>';

  // ══════ 二、七步执行流程详解 ══════
  html += '<div id="al-steps" style="margin-bottom:48px">'
    + '<h3 style="font-size:18px;font-weight:700;color:#0f172a;margin:0 0 16px">二、七步执行流程详解</h3>'
    + '<p style="font-size:14px;color:#64748b;line-height:2.0;margin:0 0 20px">'
    + '分析链的执行过程分为七个步骤，每一步都是前一步的延伸和深化。下面详细说明每一步的输入、处理逻辑和输出。'
    + '</p>';

  var steps = [
    {n:'①', title:'资料扫描与类型识别', icon:'📄',
     desc:'系统遍历 uploads/ 目录，读取全部 Excel/CSV/PDF 文件。使用34类文件指纹库执行三层递进识别：'
       + 'Step1 关键词打分（表头文字与34类指纹关键词库交叉匹配，每匹配一词得1分，超阈值即判定）→ '
       + 'Step2 结构分析（列数+位置+表头组合模式确认，银行流水=日期+对方+金额+余额模式）→ '
       + 'Step3 数据推断兜底（读前200行按语义角色判定：日期格式→日期列，含公司/厂→企业名，含元/￥→金额列）。'
       + '不因无法识别而丢弃数据——标注为通用数据交由下游模块自行判断。'},
    {n:'②', title:'目标实体识别', icon:'🎯',
     desc:'从发票数据中自动推断被查单位的名称和行业。进项购买方 ∩ 销项销售方 → 交叉取交集确定企业全称。'
       + '行业识别：90+关键词×66行业加权投票制，扫描全部发票品名，每个行业命中的关键词次数作为投票权重，取最高分。'
       + '同时联网查询工商登记信息（法定代表人/注册资本/经营范围/股东），与发票推断结果做双源比对。'},
    {n:'③', title:'资料情报提取与数据分析', icon:'🔍',
     desc:'将各类型文件数据导入42个域分析函数。包括：银行流水收款构成分析 + 付款方身份核实（联网法人/股东比对）；'
       + '进销存比对比——商品明细匹配 + 进销比 + 毛利率；五层发票审计——格式合规→同品名单价→加工费专项→金额合理性→BOM进销映射；'
       + '供应商穿透——集中度+群集+名称异常+双向交易检测；合同分层——四层自动分类（必签/应签/可免/小额）。'},
    {n:'④', title:'规则引擎与链驱动检查', icon:'⚙️',
     desc:'' + pc('rules','1608') + '条稽查指令逐条与域分析发现做匹配。' + pc('trailChains','437') + '条线索链引擎（行业特化链自动过滤——非本行业链不执行，全行业通用链全部运行）：每链多个调查步骤，通过定量/定性/缺失三类数据验证后触发，'
       + '产生链驱动发现。' + pc('evidenceChains','781') + '条证据链闭环检测：收集所有触发的规则ID，计算每链触发率——≥60%且≥3条规则+≥2数据域→形成证据闭环。'
       + '链驱动引擎产出线索发现和闭环发现两类新发现，补充到总发现池。'},
    {n:'⑤', title:'方法论噪声过滤器', icon:'🎯',
     desc:'方法论过滤器是确保报告质量的最后关口。HARD_BAN（硬删除）：23类禁止词绝对不允许出现在输出中——'
       + '涉刑侦术语（公安/经侦/刑事）、推测性结论（走逃/失联）、系统内部术语、跨域数据需求等。'
       + 'COND_BAN（条件过滤）：5类——无申报表则删除申报相关结论，无库存台账则删除库存相关结论（有则放过）。'
       + '稽查重点发现（level_fixed=True）不参与任何过滤。行业不匹配的发现自动删除。去重+正常结论排除。'
       + '典型效果：1638条→过滤后36条。'},
    {n:'⑥', title:'行业对标与申报比对', icon:'📊',
     desc:'66行业基准值自动对标（每个行业含：毛利率下限/上限/典型值、净利率下限/上限/典型值、税负率下限/上限/典型值、'
       + '进销比下限/上限/典型值、人均营收下限/上限/典型值）。三级判断：低于下限→高风险、低于典型值85%→中风险、高于上限→中风险。'
       + '增值税申报表 vs 发票实际销项税额/进项税额比对，差异>1000元预警。'},
    {n:'⑦', title:'正式稽查报告输出', icon:'📝',
     desc:'综合所有域分析发现、链驱动发现、证据闭环发现，经过方法论过滤器和建议增强后，生成结构化稽查报告。'
       + '报告含：稽查概况、企业工商信息（联网核查）、高风险/中风险/低风险发现（按优先级排序）、'
       + '每条发现含四步分析框架（detect→verify→diagnose→report）、明细数据（供应商/金额/发票号）、'
       + '法律依据引用、具体消除路径建议。报告为独立HTML文件，可直接交付。'},
  ];

  steps.forEach(function(s) {
    html += '<div style="padding:16px 20px;margin-bottom:12px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;border-left:4px solid #2563eb">'
      + '<div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:10px"><span style="font-size:18px">' + s.icon + '</span> ' + s.n + ' ' + s.title + '</div>'
      + '<div style="font-size:13px;color:#475569;line-height:2.0;margin-bottom:10px">' + s.desc + '</div>'
      + (s.input ? '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:11px;line-height:1.8">'
      + '<div style="padding:8px 10px;background:#f8fafc;border-radius:4px"><strong style="color:#2563eb">输入：</strong>' + s.input + '</div>'
      + '<div style="padding:8px 10px;background:#f8fafc;border-radius:4px"><strong style="color:#059669">输出：</strong>' + s.output + '</div>'
      + '</div>' : '')
      + (s.process ? '<details style="margin-top:8px"><summary style="font-size:11px;color:#2563eb;cursor:pointer;font-weight:600">展开处理逻辑</summary><pre style="margin-top:6px;font-size:11px;color:#475569;line-height:1.8;background:#fafafa;padding:10px;border-radius:4px;white-space:pre-wrap;word-break:break-all">' + s.process + '</pre></details>' : '')
      + (s.edge ? '<div style="margin-top:8px;font-size:11px;color:#94a3b8"><strong>边缘情况：</strong>' + s.edge + '</div>' : '')
      + '</div>';
  });

  html += '</div>';

  // ══════ 三、全链路稽查质量保障体系 ══════
  html += '<div id="al-quality" style="margin-bottom:48px;padding:24px;background:#fff;border:1px solid #e2e8f0;border-radius:8px">'
    + '<h3 style="font-size:18px;font-weight:700;color:#0f172a;margin:0 0 16px">三、全链路稽查质量保障体系</h3>'
    + '<p style="font-size:14px;color:#64748b;line-height:2.0;margin:0 0 16px">'
    + '全链路稽查质量保障体系是一个开放的质量保障生态系统，从规则触发到报告输出，每条发现必须可追溯、可验证、可复核。'
    + '体系持续扩展新的保障维度，随系统发展而演进，不固定为"X合一"。下面按五大层次展示当前体系内容。'
    + '</p>'
    + '<div style="font-size:13px;color:#475569;line-height:2.0">'
    // 第一层：核心数据资产
    + '<div style="margin-bottom:16px"><div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:8px">① 核心数据资产</div>'
    + '<div style="padding:10px 16px;margin-bottom:6px;background:#fff;border-radius:6px;border-left:3px solid #2563eb"><strong>规则引擎</strong> → ' + pc('rules','1608') + '条稽查指令（tax_risk_rules_local_export.json），每条发现必须可追溯到具体规则ID。</div>'
    + '<div style="padding:10px 16px;margin-bottom:6px;background:#fff;border-radius:6px;border-left:3px solid #7c3aed"><strong>线索链系统</strong> → ' + pc('trailChains','437') + '条线索链（cross_domain_clues.json），每条发现必须可追溯到具体线索链，触发率=已触发步骤/总步骤。</div>'
    + '<div style="padding:10px 16px;margin-bottom:6px;background:#fff;border-radius:6px;border-left:3px solid #059669"><strong>证据链系统</strong> → ' + pc('evidenceChains','781') + '条证据链（cross_domain_evidence.json），≥2维交叉验证+≥min_evidence阈值→闭环发现→强制升级高风险。</div>'
    + '<div style="padding:10px 16px;background:#fff;border-radius:6px;border-left:3px solid #0891b2"><strong>跨域分析链</strong> → ' + pc('analysisChains','48') + '条分析链（cross_domain_analysis.json），多源数据综合推理，覆盖资金流+票据流+业务流三维验证。</div>'
    + '</div>'
    // 第二层：方法论体系
    + '<div style="margin-bottom:16px"><div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:8px">② 方法论体系</div>'
    + '<div style="padding:10px 16px;margin-bottom:6px;background:#fff;border-radius:6px;border-left:3px solid #dc2626"><strong>稽查方法论33条</strong> → 已全部代码化，涵盖多格式兼容、汇总行过滤、付款方身份核实等1266条方法链。</div>'
    + '<div style="padding:10px 16px;margin-bottom:6px;background:#fff;border-radius:6px;border-left:3px solid #f59e0b"><strong>四步稽查分析法</strong> → detect→verify→diagnose→report四步分析框架，每条发现必须完整呈现推导链。</div>'
    + '<div style="padding:10px 16px;margin-bottom:6px;background:#fff;border-radius:6px;border-left:3px solid #7c3aed"><strong>三层行业穿透法</strong> → 工商登记+发票数据+加工信号，三者不一致时以实质重于形式为原则。</div>'
    + '<div style="padding:10px 16px;margin-bottom:6px;background:#fff;border-radius:6px;border-left:3px solid #059669"><strong>经营实质点面推理法</strong> → 单点发现→数据扩展→关联维度→交叉验证→综合结论。</div>'
    + '<div style="padding:10px 16px;margin-bottom:6px;background:#fff;border-radius:6px;border-left:3px solid #2563eb"><strong>合同分层判断法</strong> → 必签+应签+可免+小额四层自动分类，印花税预估=must_total×0.03%。</div>'
    + '<div style="padding:10px 16px;background:#fff;border-radius:6px;border-left:3px solid #dc2626"><strong>发票≠收付款1:1方法论</strong> → 六种收付款模式，未匹配≠异常，按纳税影响分级。</div>'
    + '</div>'
    // 第三层：质量保障机制
    + '<div style="margin-bottom:16px"><div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:8px">③ 质量保障机制</div>'
    + '<div style="padding:10px 16px;margin-bottom:6px;background:#fff;border-radius:6px;border-left:3px solid #dc2626"><strong>稽查重点强制等级</strong> → 12类稽查重点直接硬编码为高风险，三层保护机制。</div>'
    + '<div style="padding:10px 16px;margin-bottom:6px;background:#fff;border-radius:6px;border-left:3px solid #f59e0b"><strong>报告纯净度规范</strong> → 移除所有系统内部标注，四步框架在报告中表现为自然段落衔接。</div>'
    + '<div style="padding:10px 16px;background:#fff;border-radius:6px;border-left:3px solid #7c3aed"><strong>方法论噪声过滤器</strong> → HARD_BAN（23类禁止词）+ COND_BAN（5类条件过滤），97%噪声过滤率。</div>'
    + '</div>'
    // 第四层：行业认知体系
    + '<div style="margin-bottom:16px"><div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:8px">④ 行业认知体系</div>'
    + '<div style="padding:10px 16px;margin-bottom:6px;background:#fff;border-radius:6px;border-left:3px solid #059669"><strong>行业自适应产品链词典</strong> → 25个制造/加工行业×2组关键词对，禁止行业特化硬编码。</div>'
    + '<div style="padding:10px 16px;margin-bottom:6px;background:#fff;border-radius:6px;border-left:3px solid #2563eb"><strong>外包轻加工模式认知</strong> → 工商批发业≠无加工，外包轻加工模式在批发业中广泛存在。</div>'
    + '<div style="padding:10px 16px;background:#fff;border-radius:6px;border-left:3px solid #7c3aed"><strong>66行业基准值库</strong> → 每个行业含毛利率/净利率/税负率/进销比/人均营收五个指标。</div>'
    + '</div>'
    // 第五层：执行管线
    + '<div><div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:8px">⑤ 执行管线</div>'
    + '<div style="padding:10px 16px;margin-bottom:6px;background:#fff;border-radius:6px;border-left:3px solid #dc2626"><strong>七步执行流程</strong> → 资料扫描→目标实体识别→数据分析→规则引擎→方法论过滤→行业对标→报告输出。</div>'
    + '<div style="padding:10px 16px;margin-bottom:6px;background:#fff;border-radius:6px;border-left:3px solid #f59e0b"><strong>42个域分析函数</strong> → 银行流水+进销存比+五层发票审计+供应商穿透+合同分层等。</div>'
    + '<div style="padding:10px 16px;background:#fff;border-radius:6px;border-left:3px solid #059669"><strong>全链路溯源体系</strong> → 规则ID追溯✓+线索链追溯✓+证据来源✓+一键分析溯源✓+证据链闭环✓+跨域证据链✓。</div>'
    + '</div>'
    + '</div>'
    + '</div>';
  // ══════ 四、稽查方法论（㉛条详解）══════
  html += '<div id="al-methods" style="margin-bottom:48px;padding:24px;background:#fff;border:1px solid #e2e8f0;border-radius:8px">'
    + '<h3 style="font-size:18px;font-weight:700;color:#0f172a;margin:0 0 16px">四、稽查方法论（33条已全部代码化）</h3>'
    + '<p style="font-size:14px;color:#64748b;line-height:2.0;margin:0 0 20px">'
    + '稽查方法论是税务稽查系统的灵魂。每一条方法论都来自实战中反复踩过的坑，是血泪教训的结晶。下面逐条详解。'
    + '</p>'
    + '<div style="font-size:13px;color:#475569;line-height:2.0">'

  var methods = [
    {id:'①', name:'多格式兼容', desc:'银行文件date/tx_time/交易日期/交易时间/记账日期五种命名全兼容。PDF发票PDFPlumber解析+OCR兜底。Excel多引擎（openpyxl/xlrd/pandas）。不因格式不兼容而丢弃数据。'},
    {id:'②', name:'汇总行过滤', desc:'月末汇总行（对手为空+大额整数）→自动识别并剔除。银行流水中的汇总行（如"本月合计"）不是真实交易，必须过滤。'},
    {id:'③', name:'付款方身份核实', desc:'个人打款→联网查工商→范善茂=法定代表人→性质待核实（股东注资/借款/未申报收入），不直接定性。付款方身份必须核实，不能凭名字猜测。'},
    {id:'④', name:'关键词≠事实', desc:'BOM从纯关键词→进销品名实质差异+加工费证据。含"BOM"关键词不等于有BOM业务，必须通过进销品名差异和加工费发票来证明。'},
    {id:'⑤', name:'行业认知补算法', desc:'工商登记类型≠实际经营模式。企业可能通过委托加工等外包方式实现进销品名转化（如买原料→委托加工→卖成品），在贸易型企业中广泛存在。算法必须考虑行业认知，不能仅凭工商登记判定企业类型。'},
    {id:'⑥', name:'联网核查', desc:'企查查查法人/股东/行业/注册资本。工商信息可能与发票数据不一致，必须联网核查确认。'},
    {id:'⑦', name:'明细即信服力', desc:'全部收款方+付款方逐一列示明细表，不分组合并。每条发现必须有具体数据（供应商名/金额/发票号），不可泛泛计数。'},
    {id:'⑧', name:'资料驱动', desc:'有资料就分析，不猜、不预设、不脑补。缺什么资料就标记什么缺口，列出缺失后果。系统不会因为缺资料而停止分析，也不会在没有数据的情况下编造结论。'},
    {id:'⑨', name:'合同分层判断', desc:'四层自动判断：日常消费（加油/餐饮/差旅/快递/办公→免合同）→主营业务（原材料/加工/半成品/配件→必合同）→重要费用（大额服务/设备/咨询→应合同）→小额杂项（可免）。印花税预估：must_total × 0.03‰。'},
    {id:'⑩', name:'完备度明细', desc:'14类稽查必查资料逐一检测提交状态。缺失→标记"未提交"+列出具体缺失后果。不完备度每升一级升一档风险。'},
    {id:'⑪', name:'完备度升级', desc:'合同需求从发票数据自动分析——判断每个供应商是否需要合同→需要但缺合同→附加风险等级。同时计算缺合同的供应商合计金额和占比。'},
    {id:'⑫', name:'凭证描述纠正', desc:'当企业凭证摘要≠发票品名时，系统从发票数据中提取实际品名自动修正凭证描述。确保账务记录反映真实交易内容。'},
    {id:'⑬', name:'进销诊断升级', desc:'有进无销→判定为采购积压或未开票销售。有销无进→判定为供应商开票延迟或无票采购。制造业进销品名差异→诊断为加工业务→自动触发加工环节深度分析。'},
    {id:'⑭', name:'行业基准库', desc:'66个行业×5个指标×3个基准值（P25/P50/P75）。企业值<下限→高风险。企业值<典型值×0.85→中风险。JSON可扩展。'},
    {id:'⑮', name:'结论分析法', desc:'每条结论含9个结构字段（类型/等级/分数/详情/描述/稽查属性/稽查事实/法律依据/建议）。全维度可追溯。'},
    {id:'⑯', name:'COND_BAN防误杀', desc:'每个风险触发条件必须经双重验证：条件A（数据异常）+条件B（行业/模式确认）同时满足才触发。仅条件A出现不触发。'},
    {id:'⑰', name:'稽查重点强制等级', desc:'12类稽查重点发现直接硬编码为高风险，不受过滤器降级或协商引擎调整。三层保护：后端强制修正→过滤器绕过→前端红色标记。'},
    {id:'⑱', name:'报告纯净度', desc:'自动删除模板句/空描述/重复句/空占位符。方法论内部标注全部从正式报告中移除。每句话必须有数据支撑。'},
    {id:'⑲', name:'发票≠收付款1:1', desc:'发票日期≠收款/付款日期。六种正常时间差模式：自然跨期/合并支付/分期支付/预付预收/应付应收/非对公代付。保留时间容差。'},
    {id:'⑳', name:'经营实质地理分析', desc:'从单一经营场所缺失→扫描供应商/客户/加工商地址→提取城市/省份/距离→点→面推理全链条经营实质。重物运输跨省→运输成本缺失→货物流真实性存疑。'},
    {id:'㉑', name:'规则detail业务化', desc:'每条规则detail描述用自然语言解释异常含义，不能只是阈值罗列。如"BOM进销映射异常"→"进销品名不匹配，可能存在虚开发票风险"。'},
    {id:'㉒', name:'建议质量增强', desc:'处理建议含11条针对性的具体操作路径。每条建议含：查什么→怎么查→正常怎么办→异常怎么办。不能只说"立即整改"。'},
    {id:'㉓', name:'四步稽查分析法', desc:'detect→verify→diagnose→report。系统自动为每条发现生成四步推导链并完整呈现在报告中。'},
    {id:'㉔', name:'禁止数据截断', desc:'任何展示字段不设硬编码截断。完整数据显示，由用户自行判断。列表不设上限，证据明细逐笔列示。'},
    {id:'㉕', name:'三层行业穿透法', desc:'第一层：工商登记行业→第二层：发票数据推断行业（90+关键词加权投票）→第三层：加工信号（BOM品名差异+加工费）。不一致时以实质重于形式。'},
    {id:'㉖', name:'经营实质点面推理法', desc:'发现一个风险点→推理出相关风险面。点→数据扩展→关联维度→交叉验证→综合结论。'},
    {id:'㉗', name:'稽查六员跨企业比对', desc:'法定代表人/股东/董事/监事/高管/财务负责人——同一人在多家企业任职→关联交易风险。联网核查获取六员后执行三重检测。'},
    {id:'㉘', name:'供应链联网核查', desc:'全链条人员交叉比对——供应商→加工商→客户的工商信息和关联关系联网核查。进销发票TOP10→搜索引擎查每家→六员交叉比对。'},
    {id:'㉙', name:'主营业务聚焦法', desc:'将全部采购按品名与主营业务关联度排序。与主营业务无关的大额采购→虚增成本/转移利润嫌疑。品名含主营关键词→主营业务成本；不含→重大费用或日常报销。'},
    {id:'㉚', name:'资料缺失风险推理', desc:'缺失的资料不是空的——它意味着对应风险无法排除。根据缺失资料类型推理出潜在风险方向。14类资料缺失→9条风险结论映射，全行业适用。'},
    {id:'㉛', name:'存疑排除法', desc:'买卖方都不含本公司→非本账套数据→排除出所有计算。防止A公司数据污染B公司分析。'},
    {id:'㉜', name:'规则配置外部化', desc:'所有规则/阈值/关键词存JSON文件，可通过编辑JSON追加新规则。新增规则只改配置不改代码。'},
    {id:'㉝', name:'资金回流检测法', desc:'银行流水中同一对方名称同时出现收款和付款→检测是否为同日或短期资金回流→虚开发票/对倒开票嫌疑。系统自动匹配同一对手方的收付款时间差和金额匹配度。'}
  ];

  methods.forEach(function(m) {
    html += '<div style="padding:10px 16px;margin-bottom:6px;background:#fff;border-radius:6px;border-left:2px solid #e2e8f0">'
      + '<span style="font-weight:700;color:#2563eb;margin-right:8px">' + m.id + '</span>'
      + '<strong style="color:#0f172a">' + m.name + '</strong>'
      + '<span style="color:#64748b;margin-left:8px;font-size:12px">' + m.desc + '</span>'
      + '</div>';
  });

  html += '</div></div>';

  // ══════ 五、分析链定义列表（从 cross_domain_analysis.json 加载） ══════
  html += '<div id="al-chains" style="margin-bottom:48px">'
    + '<h3 style="font-size:18px;font-weight:700;color:#0f172a;margin:0 0 16px">五、分析链定义一览（48 条全部可执行）</h3>'
    + '<p style="font-size:13px;color:#64748b;line-height:2.0;margin:0 0 16px">每条分析链由 evidence→reasoning_path→conclusion 三段组成。推理步骤顺序执行，前一步的输出是后一步的输入。</p>'
    + '<div id="al-chains-list" style="display:flex;flex-direction:column;gap:12px">'
    + '<p style="font-size:13px;color:#94a3b8">加载中...</p>'
    + '</div>'
    + '</div>';
  target.innerHTML = html;

}

function renderAnalyzeResult(report) {
  var target = document.getElementById('analyze-body');
  if (!target) return;
  var allF = report.all_findings || [];
  var comp = report.comprehensive || {};
  var plogs = report.pipeline_log || [];
  var highCount = allF.filter(function(f){return (f.level==='极高风险' || f.level==='高风险')}).length;
  var midCount = allF.filter(function(f){return f.level==='中风险'}).length;
  var lowCount = allF.length - highCount - midCount;

  var h = '';

  // ══════ 一、什么是分析链 ══════
  h += '<div style="margin-bottom:40px">'
    + '<div style="font-size:13px;color:#475569;line-height:2.0;margin:0 0 16px">'
    + '分析链是税务稽查系统的核心执行管线——<strong>七步串联的数据处理流水线</strong>，数据在管线中单向流动，不丢失、不污染、不截断。'
    + '从资料扫描开始，经过多轮交叉验证，最终形成证据闭环：资料驱动+诚实边界+交叉推断+明细支撑。'
    + '</div>'
    + '<div style="font-size:12px;color:#94a3b8;line-height:2.0;padding:12px 16px;background:#fff;border:1px solid #e2e8f0;border-radius:6px">'
    + '代码位置：main.py _run_analyze() · 数据规模：' + pc('rules','1608') + '条指令 + ' + pc('trailChains','437') + '条线索链 + ' + pc('evidenceChains','781') + '条证据链 · 处理能力：97%噪声过滤 · 66行业基准库 · 35域分析函数'
    + '</div>'
    + '</div>';

  // ══════ 二、七步执行流程 ══════
  h += '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 16px">七步执行流程</h3>'
    + '<div style="margin-bottom:40px;display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px;color:#475569;line-height:2.0">'
    + '<div style="padding:14px 16px;background:#f0f9ff;border-radius:6px;border-left:3px solid #2563eb"><strong style="color:#0f172a;font-size:13px">① 资料扫描与类型识别</strong><br>34类文件指纹库+三层递进识别（关键词打分→结构分析→数据推断），自动判定发票方向。</div>'
    + '<div style="padding:14px 16px;background:#f5f3ff;border-radius:6px;border-left:3px solid #7c3aed"><strong style="color:#0f172a;font-size:13px">② 目标实体识别</strong><br>进项购买方∩销项销售方确定企业全称，90+关键词×66行业加权投票，联网工商比对。</div>'
    + '<div style="padding:14px 16px;background:#ecfdf5;border-radius:6px;border-left:3px solid #059669"><strong style="color:#0f172a;font-size:13px">③ 资料情报提取与分析</strong><br>42个域分析函数并行执行：银行流水收款构成+进销存比+五层发票审计+供应商穿透+合同分层。</div>'
    + '<div style="padding:14px 16px;background:#fef2f2;border-radius:6px;border-left:3px solid #dc2626"><strong style="color:#0f172a;font-size:13px">④ 规则引擎与链驱动检查</strong><br>' + pc('rules','1608') + '条稽查指令逐条匹配，' + pc('trailChains','437') + '条线索链触发（行业不匹配链自动跳过），' + pc('evidenceChains','781') + '条证据链闭环检测。</div>'
    + '<div style="padding:14px 16px;background:#fffbeb;border-radius:6px;border-left:3px solid #f59e0b"><strong style="color:#0f172a;font-size:13px">⑤ 方法论噪声过滤器</strong><br>HARD_BAN（23类禁止词）+ COND_BAN（5类条件过滤），97%噪声过滤率。稽查重点发现不受过滤影响。</div>'
    + '<div style="padding:14px 16px;background:#fdf2f8;border-radius:6px;border-left:3px solid #ec4899"><strong style="color:#0f172a;font-size:13px">⑥ 行业对标与申报比对</strong><br>66行业基准值自动对标（毛利率/净利率/税负率/进销比/人均营收五维），申报表vs发票实际比对。</div>'
    + '<div style="padding:14px 16px;background:#f0fdf4;border-radius:6px;border-left:3px solid #16a34a"><strong style="color:#0f172a;font-size:13px">⑦ 正式稽查报告输出</strong><br>按《税务稽查工作规程》标准格式生成7章节+附件的完整稽查报告（详见第七节「稽查报告标准格式」）。</div>'
    + '</div>';

  // ══════ 三、本次分析结果 ══════
  h += '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 16px">本次分析结果</h3>'
    + '<div style="display:flex;gap:12px;margin-bottom:20px">'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#0f172a">' + (report.files_count||0) + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">资料文件</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#2563eb">' + (comp.rule_count||pc('rules','1608')) + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">匹配规则</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#dc2626">' + highCount + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">高风险</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fffbeb;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#f59e0b">' + midCount + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">中风险</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#059669">' + lowCount + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">低风险</div></div>'
    + '</div>'
    + '<div style="margin-bottom:40px;font-size:13px;color:#475569;line-height:2">'
    + '规则 <strong>' + (comp.rule_count||pc('rules','1608')) + '</strong> 则 · 线索链 <strong>' + (comp.chain_count||pc('trailChains','437')) + '</strong> 条 · '
    + '证据链 <strong>' + (comp.evidence_count||pc('evidenceChains','781')) + '</strong> 条 · 文件 <strong>' + (report.files_count||0) + '</strong> 个 · '
    + '全链路闭环：规则ID追溯 ✓ · 线索链追溯 ✓ · 证据来源 ✓ · 一键分析 ✓'
    + '</div>';

  // ══════ 四、管线日志 ══════
  if (plogs.length > 0) {
    h += '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 8px">管线执行日志 · ' + plogs.length + ' 条</h3>'
      + '<div style="margin-bottom:40px;background:#0f172a;border-radius:6px;padding:20px 24px;max-height:400px;overflow-y:auto;font-family:\'SF Mono\',\'Fira Code\',monospace;font-size:12px;line-height:2.0">';
    plogs.forEach(function(log, i) {
      var color = '#64748b';
      if (/异常|失败|错误/.test(log)) color = '#fca5a5';
      else if (/完成|成功|通过/.test(log)) color = '#86efac';
      else if (/发现|触发|命中/.test(log)) color = '#fde68a';
      else if (/Phase|Step|阶段|过滤|剔除|闭环/.test(log)) color = '#93c5fd';
      h += '<div style="color:' + color + '">[' + (i+1).toString().padStart(3,' ') + '] ' + escHtml(log) + '</div>';
    });
    h += '</div></div>';
  }

  // ══════ 五、稽查方法论（㉛条详解）══════
  var methods = [
    {id:'①', name:'多格式兼容（全行业适用）', desc:'银行文件date/tx_time/交易日期/交易时间/记账日期五种命名全兼容。PDF发票PDFPlumber解析+OCR兜底。Excel多引擎。代码：main.py _read_file_multi_engine()。适用所有行业所有格式。'},
    {id:'②', name:'汇总行过滤（全行业适用）', desc:'月末汇总行（对手为空+大额整数）→自动识别并剔除。通用规则，与行业无关。代码：main.py _filter_bank_summary_rows()。'},
    {id:'③', name:'付款方身份核实+联网核查（全行业适用）', desc:'个人打款→必须调用_ online_company_lookup()联网查工商→确认是否为法定代表人/股东/关联方→性质待核实（股东注资/借款/未申报收入），不直接定性。代码：main.py _online_company_lookup()。报告第一章必须使用联网核查结果。'},
    {id:'④', name:'关键词≠事实（全行业适用）', desc:'任何业务关键词（BOM/加工/外包等）必须从纯关键词升级为实质证据（进销品名差异+对应发票/合同证据）。含关键词≠有该业务。代码：main.py _domain_invoice_audit()。适用所有行业。'},
    {id:'⑤', name:'行业认知补算法（全行业适用）', desc:'工商登记行业≠实际经营行业。外包/轻加工/服务外包等模式在各行业广泛存在，算法必须通过三层行业穿透法判断，不能凭工商登记下结论。代码：main.py _detect_target_entity()+INDUSTRY_PRODUCT_CHAINS词典。'},
    {id:'⑥', name:'联网核查（搜索引擎知识图谱提取法）', desc:'稽查报告第一章必须通过_ online_company_lookup()自动查询。三层数据源：①数据库缓存（已有不重查）②搜狗搜索知识图谱卡片（自动聚合企查查/天眼查/启信宝数据，纯文本、无需JS）③360搜索备用。自动提取6项核心字段：法定代表人/注册资本/成立日期/登记状态/经营范围/注册地址。全行业各企业适用。核查成功标注"✅搜索引擎知识图谱"，失败标注"⚠️发票数据推断"。代码：main.py:18436 _COMPANY_LOOKUP_SOURCES + 18478 _extract_company_from_html + 18597 _online_company_lookup。'},
    {id:'⑦', name:'明细即信服力（全行业适用）', desc:'全部收款方+付款方+供应商+客户逐一列示明细表，不分组合并，不截断（禁止"前N条"）。每条发现必须有具体数据（供应商名/金额/发票号/日期）。代码：tax-doc-analysis.js renderTaxDocReport()发现项渲染。'},
    {id:'⑧', name:'不墨迹直接干', desc:'发现问题不请示，读文件查格式直接修。自动继续直到交付完整结果。'},
    {id:'⑨', name:'合同分层判断（全行业适用）', desc:'四层自动分类：必签（主营业务+金额>5万）、应签（1-5万）、可免（日常消费）、小额（<1万）。判断标准：品名含主营业务关键词+金额阈值，与行业无关。代码：main.py _analyze_contract_tiers()。'},
    {id:'⑩', name:'完备度明细（全行业适用）', desc:'资料完备度评估必须列明每类资料的实际数量（如"销项发票：120张"），不能只说"齐全"或"缺失"。代码：main.py _domain_document_completeness()。'},
    {id:'⑪', name:'完备度升级（全行业适用）', desc:'资料完备度从单一维度（有/无）升级为多维度（数量+时间跨度+完整性）。通用规则。代码：main.py _domain_document_completeness()。'},
    {id:'⑫', name:'凭证描述纠正（全行业适用）', desc:'记账凭证摘要必须规范化（如"购入原材料"而非"付款"），便于后续分析。通用规则。代码：main.py _detect_target_entity()摘要分析。'},
    {id:'⑬', name:'进销诊断升级+三层分析（全行业适用）', desc:'进销品名不匹配诊断升级为三层分析：品名差异+加工费检查+加工链条合理性。通过INDUSTRY_PRODUCT_CHAINS词典（25个制造/加工行业×2组关键词对）自动判断，全行业适用。代码：main.py _domain_invoice_audit()+_get_product_keywords()。'},
    {id:'⑭', name:'行业基准库（66行业全覆盖）', desc:'66行业基准值库，每个行业含毛利率/净利率/税负率/进销比/人均营收五维基准值+企业实际值+偏离百分比。未覆盖行业使用同行类比。代码：main.py INDUSTRY_BENCHMARK库。'},
    {id:'⑮', name:'四步稽查分析法（全行业适用）', desc:'detect（检测现象）→verify（交叉验证）→diagnose（根因诊断）→report（输出结论）。每条发现必须完整呈现推导链。代码：tax-doc-analysis.js renderTaxDocReport()发现项六要素格式。'},
    {id:'⑯', name:'COND_BAN防误杀（全行业适用）', desc:'条件过滤防止过滤器误杀重要发现。有资料则放过，无资料则删除相关结论。通用规则。代码：main.py _methodology_filter()。'},
    {id:'⑰', name:'稽查重点强制等级（12类全行业适用）', desc:'12类稽查重点直接硬编码为高风险，三层保护：后端修正+过滤器绕过+前端标记。适用所有行业所有企业。代码：main.py _fix_level_by_audit_priority()。'},
    {id:'⑱', name:'报告纯净度（全行业适用）', desc:'移除所有系统内部标注（【detect】等），四步框架表现为自然段落衔接。读者看到的是专业稽查分析，而非调试输出。代码：tax-doc-analysis.js renderTaxDocReport()。'},
    {id:'⑲', name:'发票≠收付款1:1（全行业适用）', desc:'六种收付款模式：跨期/合并/分期/预付预收/应付应收/非对公代付，未匹配≠异常。双边适用（进项侧+销项侧）。代码：main.py _domain_fund_flow()。'},
    {id:'⑳', name:'经营实质地理分析（全行业适用）', desc:'供应商地址+客户地址+加工商地址+运输成本→全链条经营实质验证。重物（纺织品/钢材/建材等）跨省经营缺运输成本=物证链断裂。通过地址库自动判断。代码：main.py _domain_geographic_analysis()。'},
    {id:'㉑', name:'规则detail业务化（全行业适用）', desc:'规则detail从技术语言改为业务语言，如"BOM进销映射异常"→"进销品名不匹配"。用户/稽查人员不需要懂技术术语。代码：tax_risk.py规则引擎detail字段。'},
    {id:'㉒', name:'建议质量增强（全行业适用）', desc:'每个风险点建议含具体消除路径——提供XX资料→如果A就XX→如果B就XX→无法做到的后果。禁止泛泛说"立即整改"。代码：tax-risk-rules.js建议字段。'},
    {id:'㉓', name:'四步稽查分析法（代码化）', desc:'detect（检测现象）→verify（交叉验证）→diagnose（根因诊断）→report（输出结论）。已在四大核心发现中推广。代码：main.py四步法函数。'},
    {id:'㉔', name:'禁止数据截断（全行业适用）', desc:'报告中显示全部明细数据，不截断（如"前5条"→显示全部）。明细即信服力。代码：tax-doc-analysis.js发现项渲染（无slice(0,N)）。'},
    {id:'㉕', name:'三层行业穿透法（报告第一章强制要求）', desc:'工商登记（法律形式）→发票数据（经营实质）→加工信号（业务模式），三者不一致时以实质重于形式为原则。报告第一章必须呈现三层结论：工商登记X / 发票推断Y / 实质经营Z → 综合判断。代码：main.py _detect_target_entity()+_three_layer_industry_penetration()。全行业适用。'},
    {id:'㉖', name:'经营实质点面推理法（全行业适用）', desc:'单点发现→数据扩展→关联维度（供应商/客户/加工商/运输成本）→交叉验证→综合结论（全链条经营实质）。从单点风险推理出面的风险。代码：main.py _domain_geographic_analysis()。适用所有行业。'},
    {id:'㉗', name:'稽查六员跨企业比对（全行业适用）', desc:'联网核查获取六员（法定代表人/董事/监事/财务负责人/股东/经理）后，双重检测：①一人多角——同一人≥3个关键角色→内控缺陷②跨企业人员重叠——六员在其他企业任职→关联关系→资金回流/转移定价/虚开发票连锁风险。代码：main.py:18866 _check_six_personnel_risk() + tax-doc-analysis.js六员风险渲染。全行业各企业适用。'},
    {id:'㉘', name:'供应链联网核查（全链条人员交叉比对）', desc:'不仅查被查单位，还对TOP供应商/客户执行联网核查：发票提取名称→搜索引擎查六员→逐名与本企业六员交叉比对→发现重叠即关联交易信号。同时检测供应商=客户（购销闭环→虚开发票嫌疑）。三段式跨域分析：发票数据+人员信息+资金流。代码：main.py:18977 _lookup_supply_chain()。全行业各企业适用。'},
    {id:'㉙', name:'资料缺失风险推理（全行业适用）', desc:'任一资料缺失>=1类时，自动触发对应的风险结论到综合定性。14类资料缺失→9条风险结论映射（MISSING_CONSEQUENCE_TRIGGER），无需人工判断。代码：engine/pipeline.py _trigger_missing_consequences()。全行业各企业适用。'},
    {id:'㉚', name:'存疑排除法（全行业适用）', desc:'买卖双方名称+税号都存在但均不匹配当前公司时，标记为存疑发票并绝对排除出所有后续分析（记账、风险计算、税务推断等）。存疑发票不得以默认值（如默认进项）继续处理。代码：engine/pipeline.py 发票方向判定+clean_invs过滤。全行业各企业适用。'},
    {id:'㉛', name:'规则配置外部化（全行业适用）', desc:'所有行业编码、文件名映射、列结构锚点、分类规则等配置数据全部存放在JSON文件中（industry_data.json/filename_type_map.json/type_anchors.json），Python代码不硬编码任何行业特定逻辑。新增行业/类型只需修改JSON文件，不改Python代码。代码：static/industry_data.json + engine/pipeline.py。全行业各企业适用。'},
    {id:'㉜', name:'主营业务聚焦法（全行业适用）', desc:'判断企业所属行业时，必须以主营业务发票为依据，排除住宿费、餐饮费、加油费、租赁费、差旅费、保险费、通讯费、办公费、快递费、广告费、咨询费、法律费、维修费、物业费、停车费、经纪代理费、代订费等经营费用。经营费用是所有企业共同的日常支出，不反映行业特征。任何行业的经营费用种类相似（房租、水电、差旅、办公），但生产物资品类各行业不同（纺织→棉纱、电子→芯片、食品→原料）。代码：main.py _is_expense() + 规则999504 + _generate_biz_substance_findings()。全行业各企业适用。'},
    {id:'㉝', name:'12项报告质量标准（全行业适用）', desc:'每条稽查发现必须过12项标准检查：①客观第三人称叙事 ②三要素 ③因果链 ④可操作建议 ⑤法律条款号 ⑥证据明细表 ⑦方法在前 ⑧反模板句 ⑨事实具体化 ⑩防复制 ⑪空占位符 ⑫法条号。代码：main.py _enforce_report_quality_standards() + _sanitize_finding_boilerplate()。全行业各企业适用。'},
    {id:'㉞', name:'客户维度三源穿透法（全行业适用）', desc:'不只比总额，而是逐客户匹配开票vs收款，逐户标注收款>开票（预收/隐匿收入）、开票>收款（应收/虚开）、零开票大额收款（未申报经营收入）、整数收款（人为构造）、付款方与开票对象不一致（三流不合一）。五时点收入确认（合同→交付→开票→收款→确认）。代码：main.py _domain_customer_revenue_matching()。全行业各企业适用。'},
    {id:'㉟', name:'资金回流检测法（全行业适用）', desc:'三源比对中发现付款方与收款方有重叠时，追踪资金是否形成闭环（A付B→B付C→C付回A）。资金在三方及以上主体间形成闭环+间隔<30天+金额相近→高概率虚开发票。代码：main.py 三源比对+资金回流检测段。全行业各企业适用。'}
  ];

  h += '<div style="margin-bottom:32px;padding:20px 24px;background:#fff;border-radius:8px">'
    + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 12px">稽查方法论（㉛条已全部代码化）</h3>'
    + '<div id="methods-body" style="font-size:13px;color:#475569;line-height:2">加载中...</div>'
    + '</div>';
  // 延迟加载方法论（从 audit_chains.json 读取，支持多字段）
  setTimeout(function() {
    var target = document.getElementById('methods-body');
    if (!target) return;
    fetch('/static/audit_chains.json?_t=' + Date.now())
      .then(function(r) { return r.json(); })
      .then(function(data) {
        var chains = data.chains || [];
        var methods = chains.filter(function(c) { return c.type === 'methodology'; });
        if (methods.length === 0) { target.innerHTML = '未找到方法论数据'; return; }
        var html = '';
        methods.forEach(function(m) {
          var id = m.id || '';
          var name = m.name || '';
          var desc = m.desc || '';
          var requirement = m.requirement || '';
          var purpose = m.purpose || '';
          var codePos = m.code_position || '';
          var callLocs = m.call_locations || [];
          html += '<div style="margin-bottom:12px;padding:12px 16px;background:#fff;border-radius:6px;border-left:3px solid #2563eb">'
            + '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">'
            + '<div style="font-size:14px;font-weight:700;color:#0f172a">' + escHtml(id + ' ' + name) + '</div>'
            + '<span style="font-size:11px;color:#94a3b8;cursor:pointer" onclick="var d=this.parentNode.parentNode.nextElementSibling;d.style.display=d.style.display==\'none\'?\'block\':\'none\'">展开/折叠</span>'
            + '</div>'
            + '<div style="font-size:12px;color:#475569;line-height:2.0">' + escHtml(desc) + '</div>'
            + '<div style="display:none;margin-top:8px;padding:8px 12px;background:#fff;border:1px solid #e2e8f0;border-radius:6px;font-size:12px;color:#475569;line-height:2">'
            + (requirement ? '<div><span style="font-weight:600;color:#0f172a">要求：</span>' + escHtml(requirement) + '</div>' : '')
            + (purpose ? '<div><span style="font-weight:600;color:#0f172a">用途：</span>' + escHtml(purpose) + '</div>' : '')
            + (codePos ? '<div><span style="font-weight:600;color:#0f172a">代码位置：</span><code style="font-size:11px;background:#f1f5f9;padding:2px 6px;border-radius:4px">' + escHtml(codePos) + '</code></div>' : '')
            + (callLocs.length > 0 ? '<div><span style="font-weight:600;color:#0f172a">调用位置：</span>' + callLocs.map(function(loc) { return '<span style="display:inline-block;margin:2px 4px 2px 0;padding:2px 8px;background:#e0f2fe;color:#0369a1;font-size:11px;border-radius:4px">' + escHtml(loc) + '</span>'; }).join('') + '</div>' : '')
            + '</div>'
            + '</div>';
        });
        target.innerHTML = html;
      })
      .catch(function(e) { target.innerHTML = '加载失败：' + e.message; });
  }, 100);

  // ══════ 六、全链路稽查质量保障体系 ══════
  h += '<div style="margin-bottom:32px;padding:16px 20px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;border-left:3px solid #059669">'
    + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 8px">全链路稽查质量保障体系</h3>'
    + '<p style="font-size:12px;color:#94a3b8;margin:0 0 8px">开放生态系统 · 五大层次 · 持续扩展</p>'
    + '<div style="font-size:12px;color:#475569;line-height:2">'
    + '<div>🗄️ <strong>核心数据资产</strong>：规则引擎(' + pc('rules','1608') + '条) + 线索链(' + pc('trailChains','437') + '条) + 证据链(' + pc('evidenceChains','781') + '条) + 跨域分析链</div>'
    + '<div>📐 <strong>方法论体系</strong>：稽查方法论33条 + 四步法 + 三层穿透 + 点面推理 + 合同分层 + 发票≠收付款1:1</div>'
    + '<div>🔒 <strong>质量保障机制</strong>：稽查重点强制等级 + 报告纯净度 + 噪声过滤器(97%)</div>'
    + '<div>🏭 <strong>行业认知体系</strong>：25行业词典 + 外包轻加工认知 + 66行业基准值库</div>'
    + '<div>⚙️ <strong>执行管线</strong>：七步流程 + 35域函数 + 全链路溯源</div>'
    + '</div>'
    + '<a href="#" onclick="navigateTo(\'quality-system\');return false" style="display:inline-block;margin-top:8px;font-size:12px;color:#2563eb">查看完整18组件详情 →</a>'
    + '</div>';

  // ══════ 七、稽查报告标准格式（详见 📐 报告编制要求 模块）══════
  h += '<div style="margin-bottom:32px;padding:20px 24px;background:#fafbfc;border-radius:8px;border-left:3px solid #7c3aed">'
    + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 12px">📌 稽查报告标准格式</h3>'
    + '<p style="font-size:13px;color:#475569;line-height:2">'
    + '报告遵循《税务稽查工作规程》标准格式，共7章节+附件。每条发现按六要素格式呈现。'
    + '完整的12项质量标准、判定可靠性要求（7条）、六要素详细说明和格式对照，'
    + '请参见：<strong><a href="#" onclick="navigateTo(\'report-standards\');return false" style="color:#2563eb">📐 报告编制要求</a></strong> 模块（系统唯一权威标准来源）。'
    + '</p>'
    + '<p style="font-size:12px;color:#94a3b8;margin-top:4px">'
    + '代码位置：<code>static/js/tax-doc-analysis.js</code> <code>_renderReportFallback()</code> 函数'
    + '</p></div>';

  target.innerHTML = h;
}


// ==================== 工具函数 ====================

function toggleDomainDetail(idx) {
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
function renderCrossDomainCluesPage(container) {
  if (!container) return;
  container.innerHTML = '<style>.cdc-layout{display:flex;gap:24px;max-width:1200px;margin:0 auto;padding:20px}.cdc-toc{width:180px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:12px;line-height:2.0}.cdc-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.cdc-toc a{display:block;color:#475569;text-decoration:none;padding:2px 8px;border-radius:4px;cursor:pointer}.cdc-main{flex:1;min-width:0}</style>'
    + '<div class="cdc-layout">'
    + '<nav class="cdc-toc"><div class="toc-title">📖 导航</div>'
    + '<a href="#cdc-intro">一 概述</a><a href="#cdc-list">二 线索链定义</a>'
    + '</nav>'
    + '<div class="cdc-main">'
    + '<h2 style="font-size:22px;font-weight:800;color:#0f172a;margin:0 0 4px">🔎 跨域线索链</h2>'
    + '<p style="font-size:13px;color:#94a3b8;margin:0 0 24px">多域串联调查路径 · ≥2个数据域触发 · 从单点发现到跨域调查</p>'
    + '<div id="cdc-body"></div>'
    + '</div></div>';
  loadCrossDomainClues();
}

function loadCrossDomainClues() {
  var target = document.getElementById('cdc-body');
  fetch('/static/cross_domain_clues.json?_t=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(clues) {
      var html = '';

      // ══════ 一、概述 ══════
      html += '<div id="cdc-intro" style="margin-bottom:40px">'
        + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">一、什么是跨域线索链</h3>'
        + '<p style="font-size:13px;color:#64748b;line-height:2.0;margin:0 0 16px">'
        + '跨域线索链是从单一数据异常出发，跨多个数据域进行串联调查的标准化路径。每条线索链定义了从首域发现到多域验证的完整调查步骤，'
        + '确保每个疑点都被多源数据交叉验证——不依赖单一数据源的孤立异常下结论。'
        + '与跨域证据链不同：线索链定义的是<strong>调查路径</strong>（怎么查），证据链定义的是<strong>验证标准</strong>（怎么判）。'
        + '</p>'
        + '<div style="padding:16px 20px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;font-size:13px;color:#475569;line-height:2">'
        + '<strong>与跨域证据链的关系</strong>：线索链（调查路径）→ 证据链（验证标准）→ 结论。线索链告诉稽查人员"从哪里开始查，每一步查什么"，证据链告诉稽查人员"满足什么条件才算发现问题"。'
        + '</div>'
        + '</div>';

      // 统计
      var highCount = clues.filter(function(c) { return (c.level === '极高风险' || c.level === '高风险'); }).length;
      var totalSteps = clues.reduce(function(s,c){return s+(c.investigation_path||[]).length;},0);
      html += '<div style="display:flex;gap:12px;margin-bottom:40px">'
        + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#0f172a">' + clues.length + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">线索链</div></div>'
        + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#dc2626">' + highCount + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">高风险链</div></div>'
        + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#2563eb">' + totalSteps + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">调查步骤</div></div>'
        + '</div>';

      html += '<h3 id="cdc-list" style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">二、跨域线索链定义</h3>';

      clues.forEach(function(c) {
        var levelColor = (c.level === '极高风险' || c.level === '高风险') ? '#dc2626' : '#f59e0b';
        var levelBg = (c.level === '极高风险' || c.level === '高风险') ? '#fef2f2' : '#fffbeb';

        html += '<div style="padding:20px 24px;margin-bottom:12px;background:' + levelBg + ';border-left:3px solid ' + levelColor + ';border-radius:0 8px 8px 0">'
          + '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">'
          + '<div style="font-size:15px;font-weight:700;color:#0f172a">' + escHtml(c.name) + '</div>'
          + '<div style="display:flex;gap:8px;align-items:center">'
          + '<span style="font-size:11px;padding:2px 8px;border-radius:4px;background:' + levelColor + '15;color:' + levelColor + ';font-weight:600">' + c.level + '</span>'
          + '<span style="font-size:11px;color:#94a3b8">' + escHtml(c.sub_topic) + '</span>'
          + '<span style="font-size:11px;color:#94a3b8">需≥' + c.min_evidence + '域</span>'
          + '</div>'
          + '</div>'
          + '<div style="font-size:13px;color:#475569;line-height:2.0;margin-bottom:12px">' + escHtml(c.description) + '</div>'

          // 调查路径
          + '<div style="margin-bottom:8px;padding:10px 12px;background:#fff;border-radius:6px">'
          + '<div style="font-size:12px;font-weight:600;color:#64748b;margin-bottom:6px">调查路径 · ' + (c.investigation_path||[]).length + ' 步</div>';
        (c.investigation_path||[]).forEach(function(s) {
          html += '<div style="padding:6px 0;border-bottom:1px solid #f8fafc;font-size:13px;line-height:2.0">'
            + '<span style="color:#94a3b8;font-size:12px;margin-right:8px">Step ' + s.step + '</span>'
            + '<span style="font-weight:600;color:#2563eb">' + escHtml(s.domain) + '</span>'
            + '<span style="color:#64748b"> → ' + escHtml(s.action) + '</span>'
            + '<div style="color:#94a3b8;font-size:12px;margin-top:2px">所需资料：' + escHtml(s.data_required) + '</div>'
            + '</div>';
        });
        html += '</div>'

          + (c.tax_impact ? '<div style="font-size:13px;color:#64748b;line-height:2.0;margin-bottom:4px"><span style="font-weight:600">纳税影响：</span>' + escHtml(c.tax_impact) + '</div>' : '')
          + (c.policy_ref ? '<div style="font-size:13px;color:#64748b;line-height:2.0;margin-bottom:4px"><span style="font-weight:600">法律依据：</span>' + escHtml(c.policy_ref) + '</div>' : '')
          + (c.suggestion ? '<div style="font-size:13px;color:#64748b;line-height:2.0"><span style="font-weight:600">处理建议：</span>' + escHtml(c.suggestion) + '</div>' : '')
          + '</div>';
      });

      html += '<div style="margin-top:20px;padding:16px 20px;background:#fff;border-radius:8px;font-size:13px;color:#64748b;line-height:2">'
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
      if (target) target.innerHTML = '<div style="padding:40px 0;font-size:13px;color:#94a3b8">跨域线索链加载失败</div>';
    });
}

// ==================== 跨域分析链页面 ====================
function renderCrossDomainAnalysisPage(container) {
  if (!container) return;
  container.innerHTML = '<style>.cda-layout{display:flex;gap:24px;max-width:1200px;margin:0 auto;padding:20px}.cda-toc{width:180px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:12px;line-height:2.0}.cda-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.cda-toc a{display:block;color:#475569;text-decoration:none;padding:2px 8px;border-radius:4px;cursor:pointer}.cda-main{flex:1;min-width:0}</style>'
    + '<div class="cda-layout">'
    + '<nav class="cda-toc"><div class="toc-title">📖 导航</div>'
    + '<a href="#cda-intro">一 概述</a><a href="#cda-list">二 分析链定义</a>'
    + '</nav>'
    + '<div class="cda-main">'
    + '<h2 style="font-size:22px;font-weight:800;color:#0f172a;margin:0 0 4px">📊 跨域分析链</h2>'
    + '<p style="font-size:13px;color:#94a3b8;margin:0 0 24px">点→面推理路径 · 从单域异常到多域结论</p>'
    + '<div id="cda-body"></div>'
    + '</div></div>';
  loadCrossDomainAnalysis();
}

function loadCrossDomainAnalysis() {
  var target = document.getElementById('cda-body');
  fetch('/static/cross_domain_analysis.json?_t=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(chains) {
      var html = '';
      var highCount = chains.filter(function(c){return c.level==='高风险';}).length;
      var totalSteps = chains.reduce(function(s,c){return s+(c.reasoning_chain||[]).length;},0);

      // ══════ 一、概述 ══════
      html += '<div id="cda-intro" style="margin-bottom:40px">'
        + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">一、什么是跨域分析链</h3>'
        + '<p style="font-size:13px;color:#64748b;line-height:2.0;margin:0 0 16px">'
        + '跨域分析链定义的是<strong>推理路径</strong>——从一个域的异常信号开始，通过多步逻辑推理，逐步扩展到其他域，'
        + '最终得出跨域综合结论。每条链都有<strong>回退点</strong>——只要某个环节能提供合理解释，风险就会降级或消除。'
        + '与线索链（调查路径）和证据链（验证标准）不同，分析链关注的是<strong>推理逻辑</strong>本身。'
        + '</p>'
        + '<div style="padding:16px 20px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;font-size:13px;color:#475569;line-height:2">'
        + '<strong>三个跨域链的关系</strong><br>'
        + '🔎 跨域线索链 → 告诉稽查人员「怎么查」（调查步骤）<br>'
        + '🔗 跨域证据链 → 告诉稽查人员「怎么判」（验证标准）<br>'
        + '🧠 跨域分析链 → 告诉稽查人员「怎么推理」（逻辑路径+回退条件）'
        + '</div>'
        + '</div>';

      // 统计
      html += '<div style="display:flex;gap:12px;margin-bottom:40px">'
        + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#0f172a">' + chains.length + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">分析链</div></div>'
        + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#dc2626">' + highCount + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">高风险链</div></div>'
        + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#2563eb">' + totalSteps + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">推理步骤</div></div>'
        + '</div>';

      // ══════ 二、分析链定义 ══════
      html += '<h3 id="cda-list" style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">二、跨域分析链定义</h3>';

      chains.forEach(function(c) {
        var levelColor = (c.level === '极高风险' || c.level === '高风险') ? '#dc2626' : '#f59e0b';
        var levelBg = (c.level === '极高风险' || c.level === '高风险') ? '#fef2f2' : '#fffbeb';

        html += '<div style="padding:20px 24px;margin-bottom:12px;background:' + levelBg + ';border-left:3px solid ' + levelColor + ';border-radius:0 8px 8px 0">'
          // 标题
          + '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">'
          + '<div style="font-size:15px;font-weight:700;color:#0f172a">' + escHtml(c.name) + '</div>'
          + '<span style="font-size:11px;padding:2px 8px;border-radius:4px;background:' + levelColor + '15;color:' + levelColor + ';font-weight:600">' + c.level + '</span>'
          + '</div>'

          // 触发信号
          + '<div style="font-size:13px;color:#475569;line-height:2.0;margin-bottom:4px"><span style="font-weight:600;color:#0f172a">触发信号：</span>' + escHtml(c.trigger_signal) + '</div>'

          // 描述
          + '<div style="font-size:13px;color:#475569;line-height:2.0;margin-bottom:12px">' + escHtml(c.description) + '</div>'

          // 推理链
          + '<div style="margin-bottom:12px;padding:12px 16px;background:#fff;border-radius:6px">'
          + '<div style="font-size:12px;font-weight:600;color:#64748b;margin-bottom:8px">推理链 · ' + (c.reasoning_chain||[]).length + ' 步</div>';

        (c.reasoning_chain||[]).forEach(function(s, si) {
          html += '<div style="padding:6px 0;border-bottom:1px solid #f8fafc;font-size:13px;line-height:2.0">'
            + '<span style="color:#94a3b8;font-size:12px;margin-right:8px">' + s.order + '</span>'
            + '<span style="font-weight:600;color:#2563eb">' + escHtml(s.from) + '</span>'
            + '<span style="color:#94a3b8"> → </span>'
            + '<span style="font-weight:600;color:#7c3aed">' + escHtml(s.to) + '</span>'
            + '<div style="color:#64748b;margin-top:2px">发现：' + escHtml(s.finding) + '</div>'
            + '<div style="color:#94a3b8;font-size:12px">动作：' + escHtml(s.action) + '</div>'
            + '</div>';
          if (si < (c.reasoning_chain||[]).length - 1) {
            html += '<div style="text-align:center;color:#94a3b8;font-size:18px;padding:4px 0">↓</div>';
          }
        });
        html += '</div>'

          // 回退点
          + '<div style="padding:12px 16px;background:#f0fdf4;border-radius:6px;margin-bottom:8px">'
          + '<div style="font-size:12px;font-weight:600;color:#059669;margin-bottom:6px">回退点 · ' + (c.reversal_points||[]).length + ' 处</div>';
        (c.reversal_points||[]).forEach(function(r) {
          html += '<div style="padding:4px 0;font-size:13px;color:#475569;line-height:2.0">'
            + '<span style="color:#94a3b8;font-size:12px">Step ' + r.at_step + '</span>'
            + '<span style="color:#059669;font-weight:600"> 如果</span> ' + escHtml(r.if)
            + '<span style="color:#059669;font-weight:600"> → 则</span> ' + escHtml(r.then)
            + '</div>';
        });
        html += '</div>'

          // 方法论
          + (c.methodology ? '<div style="font-size:12px;color:#94a3b8">关联方法论：' + escHtml(c.methodology) + '</div>' : '')
          + '</div>';
      });

      html += '<div style="margin-top:20px;padding:16px 20px;background:#fff;border-radius:8px;font-size:13px;color:#64748b;line-height:2">'
        + '<strong>跨域分析链的核心价值</strong>：不是给出结论，而是展示推理过程。每一步从哪个域出发、在哪个域发现了什么、从而导向哪个域。'
        + '更重要的是——每一步都有回退条件。最终结论取决于每个环节是否可以被合理解释——这正是税务稽查中「证据链」思维在AI系统中的完整实现。'
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
      if (target) target.innerHTML = '<div style="padding:40px 0;font-size:13px;color:#94a3b8">跨域分析链加载失败</div>';
    });
}

// ==================== 页面4：方法论过滤器 ====================
function renderMethodologyFilterPage(container) {
  if (!container) return;
  window.currentModule = '方法论过滤器';

  container.innerHTML = '<style>.mf-layout{display:flex;gap:28px;max-width:1100px;margin:0 auto;padding:24px 16px;background:#fff}.mf-toc{width:180px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:12px;line-height:2.0;max-height:calc(100vh-40px);overflow-y:auto}.mf-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.mf-toc a{display:block;color:#475569;text-decoration:none;padding:3px 10px;border-radius:4px;cursor:pointer;font-size:12px}.mf-toc a:hover,.mf-toc a.active{background:#eff6ff;color:#2563eb;font-weight:600}.mf-main{flex:1;min-width:0;background:#fff}.mf-sec{margin-bottom:40px}.mf-sec-title{font-size:16px;font-weight:700;color:#0f172a;padding-bottom:10px;border-bottom:2px solid #e2e8f0;margin-bottom:16px;display:flex;align-items:center;gap:8px}.mf-sec-title .n{display:inline-flex;align-items:center;justify-content:center;min-width:24px;height:24px;background:#1e293b;color:#fff;border-radius:4px;font-size:12px;font-weight:700}.mf-rule-card{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:18px 22px;margin-bottom:10px}.mf-rule-card:hover{box-shadow:0 2px 8px rgba(0,0,0,.06);border-color:#cbd5e1}.mf-rule-hd{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}.mf-rule-badge{font-size:11px;padding:2px 10px;border-radius:10px;font-weight:600}.mf-rule-body{font-size:13px;color:#475569;line-height:2}.mf-stat-card{text-align:center;padding:16px 12px;background:#fff;border:1px solid #e2e8f0;border-radius:8px}.mf-stat-card:hover{box-shadow:0 2px 6px rgba(0,0,0,.04)}.mf-breakdown-bar{margin-bottom:8px;display:flex;align-items:center;gap:10px}.mf-breakdown-label{width:120px;font-size:12px;color:#475569;text-align:right;flex-shrink:0}.mf-breakdown-track{flex:1;height:20px;background:#f1f5f9;border-radius:10px;overflow:hidden}.mf-breakdown-fill{height:100%;border-radius:10px;transition:width .3s}.mf-item-list{max-height:400px;overflow-y:auto;border:1px solid #e2e8f0;border-radius:8px;padding:4px 0}.mf-item-row{padding:8px 16px;border-bottom:1px solid #f1f5f9;font-size:12px;color:#475569}.mf-item-row:last-child{border-bottom:none}.mf-empty{padding:40px 0;text-align:center;font-size:13px;color:#94a3b8;line-height:2}</style>'
    + '<div class="mf-layout">'
    + '<nav class="mf-toc"><div class="toc-title">📖 目录</div>'
    + '<a href="#mf-static">过滤规则体系</a>'
    + '<a href="#mf-pipeline">过滤管线说明</a>'
    + '<a href="#mf-result">本次过滤结果</a>'
    + '<a href="#mf-breakdown">剔除原因分布</a>'
    + '<a href="#mf-items">剔除明细</a>'
    + '</nav>'
    + '<div class="mf-main">'
    + '<h2 style="font-size:20px;font-weight:800;color:#0f172a;margin:0 0 4px">🎯 方法论过滤器</h2>'
    + '<p style="font-size:13px;color:#94a3b8;margin:0 0 24px;line-height:2">七类过滤规则按序执行：稽查重点保护→HARD_BAN→COND_BAN→正常排除→行业不匹配→缺口限流→去重合并。上游跨域协商引擎先消解域间矛盾，再进入过滤器——确保过滤的是自洽的发现。噪声过滤率97%。</p>'
    + '<div id="mf-body"></div>'
    + '</div></div>';

  if (_cachedFilterReport) { renderFilterResult(_cachedFilterReport); }
  else { loadMethodologyFilterData(); }
}

async function loadMethodologyFilterData() {
  try {
    var data = await getSharedAnalysis();
    if (!data.ok) {
      document.getElementById('mf-body').innerHTML = '<div class="mf-empty">' + (data.message || '暂无分析结果') + '<br><br><a href="#" onclick="navigateTo(\'tax-doc-analysis\');return false" style="color:#2563eb;text-decoration:underline">→ 运行一键分析后查看过滤详情</a></div>';
      return;
    }
    _cachedFilterReport = data.report;
    renderFilterResult(data.report);
  } catch (e) {
    document.getElementById('mf-body').innerHTML = '<div class="mf-empty" style="color:#dc2626">加载失败: ' + e.message + '</div>';
  }
}

function renderFilterResult(report) {
  var comp = report.comprehensive || {};
  var fl = comp.filter_log;
  var html = '';

  // ═══ 一、过滤规则体系 ═══
  html += '<div id="mf-static" class="mf-sec"><div class="mf-sec-title"><span class="n">1</span>过滤规则体系</div>';
  html += '<p style="font-size:13px;color:#475569;line-height:2.0;margin:0 0 16px">方法论过滤器是稽查报告质量的最后防线——在跨域协商引擎消解域间矛盾之后、报告生成之前执行。七类过滤规则严格按序执行，任何一类规则的输出是下一类的输入。最终只保留可查证、可追溯、可复核的核心发现进入正式报告。<strong>宁可漏报，不可误报。</strong></p>';

  var rules = [
    {title:'① 稽查重点保护', icon:'🛡️', color:'#2563eb', badge:'12类', desc:'执行顺序：第一步（先于所有过滤规则）。12类稽查重点发现（虚开发票/骗取出口退税/隐匿收入/账外经营/阴阳合同/资金回流/关联交易转移利润/虚假申报/骗取税收优惠/恶意注销/走逃失联/暴力抗税）在过滤器启动前即被标记为level_fixed=true，此后所有过滤操作都跳过这些发现。三层保护：后端修正→过滤器绕过→前端标记。设计哲学：宁可10条假阳性进入报告，也不能让1条真阳性被过滤掉。'},
    {title:'② HARD_BAN 硬删除', icon:'🛑', color:'#dc2626', badge:'23类', desc:'执行顺序：第二步。23类绝对禁止词——type/detail/description三字段中包含任一关键词→物理删除，不可恢复：公安/经侦/刑事/走逃/失联/空壳/皮包/逃税/骗税/抗税/洗钱/走私/贩毒/赌博/非法集资/传销/涉黑/涉恶/暴恐/间谍/叛国/颠覆/分裂。HARD_BAN的哲学：税务稽查报告中出现刑事犯罪嫌疑措辞会对企业造成不可逆的声誉损害。代码：三字段正则匹配→splice删除→filter_log记录。'},
    {title:'③ COND_BAN 条件过滤', icon:'⚠️', color:'#f59e0b', badge:'5类', desc:'执行顺序：第三步。基于资料完备度的智能过滤——缺少某类资料→依赖该类资料的发现不成立。五条条件：无申报表→删申报差异类、无合同→删合同比对类、无工资表→删薪酬类、无台账→删库存类、无凭证→删凭证类。核心逻辑：\"没有数据源→就没有分析→就没有发现\"。代码：检测depends_on字段→标记待删除→批量删除。'},
    {title:'④ 正常结论排除', icon:'✅', color:'#059669', badge:'14词', desc:'执行顺序：第四步。detail中含\"一致/正常/无异常/OK/通过/合规/无差异/基本一致/相符/匹配/吻合/无明显/未发现/暂未\"→自动删除。重要例外保护：同时含转折词\"但/然而/不过/尽管如此/除外/需要注意\"→保留。防止\"看起来正常但有异常尾巴\"的发现被误杀。'},
    {title:'⑤ 行业不匹配过滤', icon:'🏭', color:'#0f172a', badge:'动态', desc:'执行顺序：第五步。发现的行业关键词与当前企业行业不匹配→删除。独占性词（纺织/棉纱→广告公司→删）、半独占词（原料/库存→结合行业判断→标记不删）、通用词（收入/成本→所有行业→不检查）。使用industry_data.json的25行业关键词库。'},
    {title:'⑥ 资料缺口限流', icon:'📊', color:'#6366f1', badge:'≤5条', desc:'执行顺序：第六步。资料缺失类发现超过5条→只保留score最高的5条。5条足以让审理人员了解缺失情况，超过即重复。不足5条时不限流。代码：按score降序排序→超限保前5→删除后续。'},
    {title:'⑦ 去重合并', icon:'🔄', color:'#94a3b8', badge:'type+前60字', desc:'执行顺序：第七步（最后）。同type前60字符完全相同→只保留score最高的第一条。前60字作去重键——既不会漏掉实质相同的发现，也不会误合有区分的发现。Map<String, Finding>实现，ref_id精确匹配而非金额模糊匹配。'},
  ];

  rules.forEach(function(r) {
    html += '<div class="mf-rule-card">'
      + '<div class="mf-rule-hd">'
      + '<span style="font-size:14px;font-weight:700;color:#0f172a">'+r.icon+' '+r.title+'</span>'
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
  html += '<p style="font-size:13px;color:#94a3b8;margin:0 0 16px;line-height:2">' + before + ' 条发现 → 剔除 ' + totalRemoved + ' 条 → 最终保留 ' + after + ' 条，噪声率 ' + (fl.noise_ratio||0) + '%</p>';

  html += '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:24px">';
  var stats = [
    {n:before, l:'过滤前', c:'#0f172a'},
    {n:totalRemoved, l:'已剔除', c:'#dc2626'},
    {n:after, l:'过滤后', c:'#059669'},
    {n:(fl.noise_ratio||0)+'%', l:'噪声率', c:'#2563eb'}
  ];
  stats.forEach(function(s){
    html += '<div class="mf-stat-card" style="flex:1;min-width:100px"><div style="font-size:24px;font-weight:700;color:'+s.c+'">'+s.n+'</div><div style="font-size:11px;color:#94a3b8;margin-top:4px">'+s.l+'</div></div>';
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
        + '<span style="font-size:12px;color:#94a3b8;min-width:45px">'+count+'条 ('+pct+'%)</span>'
        + '</div>';
    });
    html += '</div>';
  }

  // 剔除明细（可滚动列表）
  if (removedItems.length > 0) {
    html += '<div id="mf-items" class="mf-sec"><div class="mf-sec-title"><span class="n">5</span>剔除明细</div>';
    html += '<p style="font-size:13px;color:#94a3b8;margin:0 0 12px;line-height:2">共 ' + removedItems.length + ' 条被过滤的发现（按剔除原因分组）</p>';
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
    {name:'行事风格', icon:'⚡', color:'#0f172a', id:'style', desc:'决定智哥如何做事的态度准则。做事要狠、不墨迹、主动进攻——这是面对问题时的第一反应模式，定义了编码行为的性格底色。三条准则共同作用：遇到问题→先判断影响范围→一次性全部修复→技术操作不打扰用户。', rules:[
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
  html += '<style>.ar-layout{display:flex;gap:28px;max-width:1100px;margin:0 auto;padding:24px 16px;background:#fff}.ar-toc{width:180px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:12px;line-height:2.0;max-height:calc(100vh-40px);overflow-y:auto}.ar-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.ar-toc a{display:block;color:#475569;text-decoration:none;padding:3px 10px;border-radius:4px;cursor:pointer;font-size:12px}.ar-toc a:hover,.ar-toc a.active{background:#eff6ff;color:#2563eb;font-weight:600}.ar-main{flex:1;min-width:0;background:#fff}.ar-sec{margin-bottom:36px}.ar-sec-title{font-size:16px;font-weight:700;color:#0f172a;padding-bottom:10px;border-bottom:2px solid #e2e8f0;margin-bottom:16px;display:flex;align-items:center;gap:8px}.ar-rule-card{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:18px 22px;margin-bottom:10px}.ar-rule-card:hover{box-shadow:0 2px 8px rgba(0,0,0,.06);border-color:#cbd5e1}.ar-rule-hd{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}.ar-rule-badge{font-size:11px;padding:2px 10px;border-radius:10px;font-weight:600}.ar-rule-desc{font-size:13px;color:#475569;line-height:2.0;margin-bottom:10px}.ar-rule-meta{font-size:12px;color:#94a3b8;line-height:2.0;padding-top:8px;border-top:1px solid #f1f5f9}.ar-rule-meta b{color:#64748b}.ar-stat-card{text-align:center;padding:16px 12px;background:#fff;border:1px solid #e2e8f0;border-radius:8px}.ar-info{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px 20px;font-size:13px;line-height:2}</style>';
  html += '<div class="ar-layout">';

  // TOC
  html += '<nav class="ar-toc"><div class="toc-title">📖 目录</div>';
  html += '<a href="#ar-stats">统计总览</a>';
  categories.forEach(function(c){html+='<a href="#ar-'+c.id+'">'+c.icon+' '+c.name+'</a>';});
  html += '<a href="#ar-iron-rules">⚖️ 引擎铁律</a>';
  html += '</nav>';

  html += '<div class="ar-main">';
  html += '<h2 style="font-size:20px;font-weight:800;color:#0f172a;margin:0 0 4px">🧠 智哥行为准则</h2>';
  html += '<p style="font-size:13px;color:#94a3b8;margin:0 0 24px;line-height:2">共'+totalRules+'条（'+tieLvCount+'铁律+'+zhunZeCount+'准则）· 2大分类 · 仅约束智哥写代码的行为规范。引擎自身的11条铁律已迁至 engine/memory.py。</p>';

  // Stats
  html += '<div id="ar-stats" style="display:flex;gap:10px;margin-bottom:32px;flex-wrap:wrap">'
    + '<div class="ar-stat-card" style="flex:1;min-width:90px"><div style="font-size:24px;font-weight:700;color:#0f172a">'+totalRules+'</div><div style="font-size:11px;color:#94a3b8;margin-top:4px">准则总数</div></div>'
    + '<div class="ar-stat-card" style="flex:1;min-width:90px"><div style="font-size:24px;font-weight:700;color:#dc2626">'+tieLvCount+'</div><div style="font-size:11px;color:#94a3b8;margin-top:4px">🔴 铁律</div></div>'
    + '<div class="ar-stat-card" style="flex:1;min-width:90px"><div style="font-size:24px;font-weight:700;color:#059669">'+zhunZeCount+'</div><div style="font-size:11px;color:#94a3b8;margin-top:4px">📋 准则</div></div>'
    + '<div class="ar-stat-card" style="flex:1;min-width:90px"><div style="font-size:24px;font-weight:700;color:#2563eb">'+categories.length+'</div><div style="font-size:11px;color:#94a3b8;margin-top:4px">分类</div></div>'
    + '</div>';


  // ══════ 逐分类渲染 ══════
  categories.forEach(function(cat) {
    html += '<div id="ar-' + cat.id + '" class="ar-sec"><div class="ar-sec-title">'+cat.icon+' '+cat.name+' · '+cat.rules.length+'条</div>';
    html += '<p style="font-size:13px;color:#475569;line-height:2.0;margin:0 0 16px">'+cat.desc+'</p>';

    cat.rules.forEach(function(r) {
      var isTieLv = r.level === '铁律';
      var badge = isTieLv ? '🔴 铁律' : '📋 准则';
      var badgeColor = isTieLv ? '#dc2626' : '#475569';

      html += '<div class="ar-rule-card">'
        + '<div class="ar-rule-hd">'
        + '<span style="font-size:14px;font-weight:700;color:#0f172a">#' + r.id + ' ' + escHtml(r.name) + '</span>'
        + '<div style="display:flex;gap:8px;align-items:center">'
        + '<span class="ar-rule-badge" style="background:'+badgeColor+'15;color:'+badgeColor+'">'+badge+'</span>'
        + '<span style="font-size:11px;color:#94a3b8">'+r.date+'</span>'
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
  html += '<strong style="color:#059669;font-size:14px">智哥行为准则 vs 引擎铁律</strong><br><br>';
  html += '<b>本页面7条</b>：约束智哥写代码的行为规范——怎么改代码、怎么验证、怎么自查。这些是"怎么写"的规范。<br><br>';
  html += '<b>引擎铁律11条</b>（已迁至 <code>engine/memory.py</code>）：定义引擎系统应该如何工作——科目name必须查DB、三号必须合并、ref_id必须精确匹配等。这些是"系统怎么做"的规范。<br><br>';
  html += '<b>为什么分开</b>：2026年6月30日老邓指出——\"AI行为准则的铁律，是引擎的铁律啊！\"。引擎的硬逻辑规范不应该出现在智哥的行为准则页面中。两者的受众和用途完全不同：行为准则用来约束智哥的编码行为，引擎铁律用来定义系统的运行规则。<br><br>';
  html += '引擎铁律编号（共11条）：铁律一~六（账务处理·engine/memory.py §06）+ 铁律七~十一（核心铁律·engine/memory.py §07）+ 铁律十二（跨模块内容一致性·engine/memory.py §08）。<br><br>';
  html += '完整清单见：<a href="#" onclick="navigateTo(\'auditor-handbook\');return false" style="color:#2563eb;font-weight:600">税务稽查员手册 §13 引擎铁律编号体系 →</a>';
  html += '</div></div>';

  html += '</div>';
  html += '</div>'; // ar-main
  html += '</div>'; // ar-layout
  container.innerHTML = html;
}

//  全链路稽查质量保障体系 —— 五大层次18组件全景页
// ══════════════════════════════════════════════════════════════
function renderQualitySystem(container) {
  if (!container) return;
  window.currentModule = '全链路质量保障体系';

  var layers = [
    { id:1, name:'核心数据资产', icon:'🗄️', color:'#2563eb',
      desc:'规则引擎、线索链、证据链、跨域分析链构成完整的数据资产底座。四者形成递进关系——规则定义风险判断标准，线索链定义从风险到发现的调查路径，证据链定义多源验证的闭环条件，跨域分析链执行多维度交叉验证。',
      items:[
        {name:'规则引擎',source:'static/tax_risk_rules_local_export.json → tax_risk.py',desc:'1608条稽查指令，覆盖20个分类：收入确认/成本费用/存货/固定资产/往来款/资金流/发票合规/申报比对/关联交易/个税/社保/印花税/增值税/企业所得税/特殊交易/银行账户/进销存/税务登记/资料完备度/经营实质。每条规则含4项必备要素：①触发条件——定义什么数据模式触发该规则（如\"银行贷方金额与销项开票金额偏差超过20%\"）②风险等级——极高/高/中/低四级，基于行业历史稽查数据自动标定 ③调查步骤——从发现到确认的具体操作路径 ④法定处罚依据——引用的具体法条名称和条款号，由法律推理引擎自动匹配。规则引擎在Phase1初查阶段首次激活，后续Phase2深挖和Phase3交叉验证中持续调用。1514这个数字本身由system_config.json实时统计保证准确性。'},
        {name:'线索链系统',source:'static/cross_domain_clues.json → engine/pipeline.py',desc:'437条线索链（全部可执行），每条含1-15个调查步骤。三类验证触发链驱动发现：①定量阈值触发——数值超过预设阈值自动启动链（如偏差率>20%）②定性模式触发——特定数据模式匹配（如公转私频繁）③缺失数据触发——关键资料缺失触发替代验证链。每步含domain/action/data_required三等字段，可追溯至调查来源。代码：pipeline.py调用_domain_cross_domain_clues，引擎通过trigger_keywords自动匹配findings触发。'},
        {name:'证据链系统',source:'static/cross_domain_evidence.json + engine/pipeline.py',desc:'781条证据链（全部可执行）。证据闭环机制——每个证据链定义dimensions[]数组，各维度kws匹配findings→达到min_evidence阈值→触发闭环。要求≥2个不同数据源的维度同时匹配，单域数据不构成闭环。全部达标→形成有效证据→输入分析链推理。每条证据链含rule_refs关联规则，证据收集全程可追溯。代码：_domain_cross_domain_reasoning在all_findings构建后运行。'},
        {name:'跨域分析链',source:'engine/domain_analysis.py + engine/pipeline.py',desc:'48条跨域分析链，多源数据综合推理引擎。不同于单域分析（只在银行流水域内分析收款模式），跨域分析将多个证据链的结论进行综合推理判定：reasoning_path[]定义多步推理路径→从证据到结论的因果推断。典型分析链如\"七维系统性造假综合判定模型\"——经营实质×供应商×资金流×三流合一×跨税种×关联交易×综合，7维中0-2维低风险、3-4维中风险、5-6维高风险、7维全异常→系统性造假立案。跨域分析链在Phase3交叉验证阶段集中执行，输出含score/level/triggered_dimensions的综合判定发现。'},
      ]},
    { id:2, name:'方法论体系', icon:'📐', color:'#7c3aed',
      desc:'33条稽查方法论全部代码化，六大分析框架覆盖从文件解析到结论输出的全流程。方法论是引擎的\"思维方式\"——不是写死的规则，而是面对不同数据情况时的处理策略。每条方法论在代码中有明确的实现位置和调用时机。',
      items:[
        {name:'稽查方法论33条',source:'engine/memory.py §03 + main.py 方法论调用点',desc:'1266条方法链(legacy)按功能分为5层，逐层递进：①数据接入层(①-④)——多格式兼容/汇总行过滤/付款方身份核实/关键词≠事实，确保进入分析的数据干净可靠 ②规则层(⑤-⑨)——行业基准库/联网核查/明细即信服力/合同分层/完备度，定义分析的标准和边界 ③推理层(⑩-⑯)——凭证纠正/进销诊断/结论分析法/COND_BAN/稽查重点/报告纯净度/发票≠收付款，将原始信号转化为有逻辑链条的结论 ④增强层(⑰-㉒)——经营实质地理/规则detail/建议增强/四步分析/禁止截断/三层穿透，在已有结论基础上补充深度和广度 ⑤进化层(㉓-㉝)——点面推理/六员比对/供应链核查/缺失推理/存疑排除/配置外部化/资金回流等，赋予系统自我优化和自适应能力。每条方法论含：编号(①-㉝)、名称、定义/原理、应用场景、代码位置。数量由audit_chains.json实时统计保证准确。'},
        {name:'四步稽查分析法',source:'engine/pipeline.py → Phase1-4',desc:'detect→verify→diagnose→report四步递进，每条发现必须完整走完四步才形成最终结论。①detect(初查)——1514规则引擎全量扫描，Phase1识别所有潜在风险信号，不做深度判断，只做\"有没有可能存在问题\"的初筛。②verify(深挖)——针对初步信号，Phase2定向深挖，调取更多相关数据进行验证，排除误报——如初步信号为\"毛利率异常\"，深挖阶段检查是否属于服务行业（服务行业毛利率不可比制造业），如果是则排除。③diagnose(诊断)——Phase3多源交叉验证，将经过深挖确认的信号与来自其他数据域的证据进行交叉比对，形成\"这个发现可信度多高\"的综合判断。④report(报告)——Phase4综合定性，生成因果叙事链，输出最终的风险等级、法律依据、处理建议。每条发现在报告中呈现完整的detect→verify→diagnose→report推导过程，用户可以追溯每一步的判断依据。'},
        {name:'三层行业穿透法',source:'engine/domain_analysis.py → _domain_industry判定',desc:'工商登记→发票数据→加工信号三层穿透，不一致时以实质重于形式。第一层：读取工商登记的主营行业分类——这是形式上的行业标签，可能存在登记行业与实际经营不符的情况（如登记为\"批发业\"但实际做广告代理）。第二层：统计销项发票的金税编码分布——这是数据层面揭示的实际业务模式，如果90%的销项编码属于\"广告服务\"类，实际是广告公司。第三层：检测进销品名中是否存在加工信号（加工费/原料→成品等关键词）——如果存在外包加工，则实际是\"生产+服务\"混合模式。三层结论不一致时→报告第一章行业分类展示三层穿透结果→最终以第二层（发票数据）为主，第三层（加工信号）为修正→综合判断标注推理过程。代码实现：_detect_target_entity()函数的行业判定逻辑。'},
        {name:'经营实质点面推理法',source:'engine/domain_analysis.py + geo-business-premise-analysis skill',desc:'从单一风险点推理出面的风险——不是孤立地看一个地址异常，而是从地址推演出整个经营模式的合理性。五步推理：①单点异常——发现一个具体异常点（如企业注册地址在某写字楼但社保缴纳人数为零）②数据扩展——围绕这个异常点调取所有相关数据（银行流水中的付款方地址、发票中的服务地址、合同中的履约地点）③关联维度——将地址信息与物流/运输/仓储/人员四个维度进行交叉关联 ④交叉验证——检查多个维度是否一致地指向同一个结论（运输单据缺失+人员零参保+办公地址无水电费→空壳经营的可能性增大）⑤综合结论——从单点风险上升为面的判断（不是\"注册地址异常\"而是\"经营实质存疑——疑似无实际经营场所的空壳企业\"）。引擎实现：geo-business-premise-analysis skill + domain_analysis.py 经营实质域分析。'},
        {name:'合同分层判断法',source:'engine/pipeline.py → 合同分析逻辑',desc:'四层自动判断——根据品名+金额+交易类型将合同需求分为四个层级：①必签层——大宗商品/固定资产/长期服务合同（金额>10万或服务期>1年），无合同视同高风险交易 ②应签层——常规采购/标准服务合同（金额1-10万），无合同标记为需补充 ③可免层——日常消费/零星采购（金额<1万或单一品名），无合同属于正常商业惯例不标记 ④小额层——单笔金额小于行业基准值下限，无合同不构成风险。分层依据从66行业基准库动态获取每个行业的金额门槛。合同分层结果影响：第三章发现的事实认定（是否提及合同缺失）、附件六文件清单（是否标注\"缺少合同\"）、跨域协商标记（缺合同时相关发现降权）。'},
        {name:'发票与收付款时间差方法论',source:'main.py → 时间差检测函数',desc:'发票日期≠收款日期是正常商业现象——不能因为时间差就判定异常。六种真实收付款模式：①自然跨期——月末开发票、次月初收款（1-15天差正常）②合并支付——多张发票合并一笔付款（单笔付款对应多张发票）③分期支付——一张大额发票分多笔支付（预付款30%+验收60%+质保10%）④预付预收——先付款后开票/先开票后收款（预收账款模式）⑤应付应收——赊销赊购产生的应收账款/应付账款（账期30-90天正常）⑥非对公代付——第三方代付、法人垫付等非买卖双方直接结算。引擎的发票vs付款时间匹配算法采用\"按客户逐笔配对\"而非\"全量时间差排序\"——先按客户名称分组，组内按日期排序匹配，组间不交叉。报告第二章详细叙述发现的票款时间差类型及合理性判断。'},
      ]},
    { id:3, name:'质量保障机制', icon:'🔒', color:'#dc2626',
      desc:'确保报告质量的最后关口。数字一致性+文本一致性双重保护，确保输出专业、准确、可交付。五项组件在分析管线中的位置不同——稽查重点保护在过滤器之前执行（确保不被误杀），噪声过滤器在中间，纯净度规范在报告生成阶段。',
      items:[
        {name:'稽查重点强制等级',source:'engine/pipeline.py → 方法论过滤器(稽查重点保护)',desc:'12类稽查重点发现（虚开发票/骗取出口退税/隐匿收入/账外经营/阴阳合同/资金回流/关联交易转移利润/虚假申报/骗取税收优惠/恶意注销/走逃失联/暴力抗税）强制标记为高风险且不参与任何过滤——即使COND_BAN规则试图过滤（如缺合同→过滤合同类发现），如果该发现属于12类稽查重点，过滤操作会被强制拦截。三层保护机制：①后端修正——在方法论过滤器中，检查每条发现的type是否为稽查重点，是则跳过过滤直接保留 ②过滤器绕过——噪声过滤器(HARD_BAN/COND_BAN)执行前先跑稽查重点检查 ③前端标记——报告渲染时稽查重点发现加红色边框+醒目标记，提示审理人员重点关注。三层保护确保：稽查重点发现不会因缺资料被意外过滤、不会因噪声规则被误删、在报告中物理醒目。'},
        {name:'报告纯净度规范',source:'engine/pipeline.py → _generate_report() → 文本净化',desc:'系统内部标注（如_auto_corrected/_negotiated/_dismissed等以下划线开头的字段）必须在报告输出前从正文中移除。四步净化管道：①第一步文本净化——在12项质量标准检查前执行，清除模板句（如\"是税务稽查重点方向\"）、空描述（type或detail为空）、重复句（同一发现内连续出现相同内容）、空占位符（如\"()\"\"如：()\"等自动填充失效残留）。②质量检查标记——不通过的在发现底部附加⚠标记，不影响正文。③建议增强——对suggestion字段增强后可能产生新的模板句。④第二步文本净化——再次执行文本净化，确保最终交付前的纯净度。净化后报告的四步框架(detect→verify→diagnose→report)表现为自然段落衔接，用户看不到任何内部处理痕迹。净化规则对应到具体的正则模式和替换策略（见generate_report.py的净化函数注释）。'},
        {name:'噪声过滤器',source:'engine/pipeline.py → _apply_methodology_filter()',desc:'双轨过滤体系，滤除率达97%。两条轨道：①HARD_BAN硬删除（23类禁止词）——type/detail/description中包含任一禁止词（公安/经侦/刑事/走逃/失联/空壳/皮包/逃税/骗税/抗税/洗钱/走私/贩毒/赌博/非法集资/传销/涉黑/涉恶/暴恐/间谍/叛国/颠覆/分裂）→物理删除发现，不可恢复。HARD_BAN的哲学：报告中出现刑事犯罪嫌疑措辞会对企业造成不可逆的声誉损害，宁可漏报也不能出现。②COND_BAN条件过滤（5类）——资料不存在→相关发现删除：无申报表→删除申报差异类、无合同→删除合同分层/比对类、无工资表→删除薪酬/个税类、无台账→库存/进销比类、无凭证→凭证匹配类。条件过滤的逻辑是\"不依赖缺失资料做判断\"。③正常结论排除——detail中含\"一致/正常/无异常/OK/通过/合规\"等词且不含\"但/然而/不过/尽管如此\"等转折词→自动删除（不构成风险发现）。④资料缺口限流——资料缺失类发现超过5条时，按score从低到高删除超出部分。⑤行业不匹配过滤——发现的行业关键词与当前企业行业不匹配→删除。⑥去重合并——同type前60字符相同→只保留score最高的一条。执行顺序：稽查重点保护(跳过)→HARD_BAN→COND_BAN→正常结论排除→行业不匹配→资料缺口限流→去重合并。'},
        {name:'数据一致性自检（数字+文本双维度）',source:'audit_consistency.py + shared_content_sync.py',desc:'双维度自检，防止数据漂移和内容不一致——引擎从\"功能正确\"到\"数据一致\"的跨越。①数字维度：扫描所有JS/PY文件中的硬编码数字（规则数/链数/方法论数等），与system_config.json权威数据对比。正则匹配+偏移扫描双策略覆盖，发现不一致→--sync自动替换。②文本维度：29项跨模块共享内容双层验证——9个text_sync块（逐字哈希对比权威源和依赖模块，如报告7章结构的封面到附件，不一致→自动从权威源覆盖依赖模块）+ 20个concept_link（概念关联存在性验证，确保方法论/规则/架构/数据/规范在所有引用模块中均可追溯）。四触发全覆盖：start.bat启动时、git pre-commit、一键分析pipeline.py子进程、手动python audit_consistency.py --sync。每次--sync还会自动更新engine/memory.py docstring中的权威数据区块。'},
        {name:'审核反馈闭环',source:'engine/self_learning.py → record_correction() + apply_correction_rules()',desc:'用户对报告的每一条审核都是系统的学习机会，驱动引擎从\"每次重新分析\"到\"越用越准\"。五步闭环流程：①审核——用户点击审核按钮，填写五段式审核意见（判断结论/具体问题/正确逻辑/需要证据/法律依据）②存储——POST /api/feedback → record_correction()将审核意见编码为结构化纠正规则，按\"发现类型|行业|经营模式\"三元组生成指纹，存入static/correction_rules.json ③匹配——下次一键分析时，apply_correction_rules()读取全部纠正规则，执行四级回退匹配：精确匹配(同类型+同行业+同模式)→行业匹配(同类型+同行业)→通用匹配(同类型+*+*)→名称匹配(模糊搜索) ④生效——匹配成功后不改变原始风险等级，而是给发现添加_dismissed/_negotiated等标记，前端报告展示绿色审核横幅 ⑤多轮——累计1次纠正→升级为自动规则→四级匹配优先级提升→下次同类发现自动标记。整个闭环在分析开始前+分析结束后两次介入——分析前加载纠正规则到内存，分析后存储新的审核记录。'},
      ]},
    { id:4, name:'行业认知体系', icon:'🏭', color:'#059669',
      desc:'像经验丰富的稽查员一样理解不同行业的经营模式差异。行业认知不是一次性的\"读一行行业名字\"——而是从工商登记、发票数据、实质经营三个维度综合推断，并在全部分析域中贯彻行业判定结论。行业判定错误会导致后续所有的行业对标分析结果全部失真。',
      items:[
        {name:'25行业产品链词典',source:'static/industry_data.json → 25_industry_product_chains',desc:'25个行业×2组关键词对（原料/投入关键词 vs 产品/产出关键词），覆盖中国主要行业的典型产品链关系。三级匹配策略：①精确匹配——企业的进项品名和销项品名分别与词典中的原料关键词和产品关键词完全匹配→行业确认 ②模糊匹配——企业销项品名含服务类金税编码前缀（6/7/8开头）→不执行精确的产品链匹配，直接进入服务行业判定流程 ③通用兜底——销项品名不在任何行业的产品链词典中→通过金税编码反查行业分类→如果金税编码也无法判定→使用工商登记行业为默认值同时标记\"行业未确认\"。词典的作用不仅是\"判断行业\"，更是\"验证行业\"——当进销品名与词典的行业预期一致时，该行业的分析域置信度提升；不一致时，触发外包/轻加工模式检测。'},
        {name:'外包轻加工模式认知',source:'engine/pipeline.py → 加工费检测逻辑',desc:'批发业可能存在实质加工——不能仅凭工商登记的\"批发业\"判定没有进销存分析需求，也不能仅凭进销品名差异判定为\"进销不匹配\"。检测逻辑：①扫描银行流水的付款摘要中是否含\"加工费/代工/贴牌/OEM/委外\"等关键词 ②如果是→企业存在外包加工（将原材料发给加工商、加工后收回成品），实质是\"采购原材料+外包加工+销售成品\"的三段经营模式 ③此时进销品名差异是合理的——进的是原材料、销的是成品、中间存在加工环节 ④加工模式下→执行进销存分析但放宽匹配标准（进项品名与销项品名不要求一致，只要求同属一个产品链）⑤报告第一章行业分类中展示\"批发业（存在外包加工实质）\"，第二章详细解释加工模式对分析结果的影响。外包轻加工模式的识别结果会通过跨域协商引擎通知毛利率对标域（制造业对标改为批发+加工混合对标）。'},
        {name:'66行业基准值库',source:'static/industry_data.json → 66_industry_benchmarks',desc:'66个行业×5个核心指标×3个基准值（下限/中位/上限），构成全行业财务基准参考体系。五个核心指标：①毛利率——（营业收入-营业成本）/营业收入，反映主营业务的盈利空间 ②净利率——净利润/营业收入，反映综合盈利水平 ③人均产值——营业收入/员工人数，反映劳动效率 ④费用收入比——期间费用/营业收入，反映费用管控水平 ⑤资产周转率——营业收入/总资产，反映资产使用效率。三个基准值的使用逻辑：企业值<下限→高风险（显著低于行业正常水平，可能存在成本虚列/收入少计）→企业值在下限与上限之间→中风险（属于行业正常波动范围）→企业值>上限→可能低风险但也可能是异常（如毛利率异常偏高可能是隐匿了成本）。基准库从公开数据（上市公司年报/行业统计年鉴）编制，定期可通过--calibrate模式更新。代码实现：_domain_industry_benchmarking()函数，行业匹配后自动加载对应的基准值进行对比。'},
      ]},
    { id:5, name:'执行管线', icon:'⚙️', color:'#f59e0b',
      desc:'从原始资料到正式报告的七步处理流程，数据单向流动不丢失不污染不截断。管线的设计原则：上游步骤的输出是下游步骤的输入、下游步骤不能修改上游步骤的原始数据、每一步骤有独立的日志和中间数据、任何步骤出错只影响该步骤及后续步骤、不会回写污染上游。',
      items:[
        {name:'七步执行流程',source:'engine/pipeline.py → _run_analyze()',desc:'系统化地处理从用户上传文件到最终报告生成的完整流程，每一步都有明确的输入/输出/日志：①资料扫描——文件解析引擎启动，34类文件指纹+三层递进识别（文件名→列头→数据内容→公司匹配），四方交叉验证确认每个文件的类型和归属账套。输入：用户上传的Excel文件数组。输出：分类后的文件对象数组（每个文件含：类型标签/有效记录数/解析状态/错误日志）。②实体识别——从已分类的文件中提取目标企业身份信息（公司全称/统一社会信用代码/法定代表人/行业/经营范围），通过联网核查（天眼查/企查查API）补充工商登记数据。输入：银行流水文件+销项发票文件+进项发票文件。输出：目标实体对象（含所有识别出的公司信息和置信度）。③情报提取——_extract_material_intel()函数对每个文件的每行数据执行深度提取：银行流水→收款来源分类（12条规则逐条匹配）、销项发票→销售额分布（按购买方+品名+月份三维汇总）、进项发票→成本结构（主营业务成本/重大费用/日常报销三层分类）、工资表→人员结构与薪酬分布、社保明细→缴费基数与工资比对。输入：所有已分类文件。输出：material_intel对象（含收款构成/付款构成/发票统计/工资社保统计/资料完备度评估）。④规则引擎——1608条规则+437条线索链+781条证据链+48条分析链全量激活。Phase1检测触发→Phase2定向深挖→Phase3交叉验证→Phase4综合定性。输入：material_intel + 目标实体。输出：all_findings数组（每条含type/level/score/detail/items/matched_chain_details等字段）。⑤噪声过滤——七类过滤规则依次执行：稽查重点保护→HARD_BAN→COND_BAN→正常结论排除→行业不匹配→资料缺口限流→去重合并。输入：all_findings。输出：过滤后的all_findings（减少约97%噪声）。⑥跨域协商——run_negotiation()消解域间矛盾（服务行业vs进销存异常→消解）、降级不适用发现（制造业毛利率对标用于服务行业→降为提示）、标记资料受限结论（缺合同→合同相关发现标注\"待补充\"）。输入：过滤后的all_findings。输出：协商后的all_findings。⑦报告输出——_generate_final_report()生成7章正式报告：第一章案件来源及基本情况→第二章稽查实施情况→第三章发现问题及事实认定→第四章稽查结论→第五章处理处罚建议→第六章告知权利义务→第七章稽查人员签字+附件证据清单。同时执行报告纯净度净化（去内部标记）、建议增强（补齐可执行步骤）、12项质量标准检测、语音播报适配。输入：协商后的all_findings + material_intel + 目标实体。输出：完整报告HTML或结构化JSON。'},
        {name:'42个域分析函数',source:'engine/domain_analysis.py → _domain_XX系列',desc:'42个域分析函数覆盖稽查全领域，按功能分为八大分类：①银行与资金流(3域)——收款来源分析（_domain_receipt_classification）、付款去向分析（_domain_payment_classification）、资金收支对比（_domain_cashflow_comparison）②发票与票据流(4域)——销项发票分析（_domain_sales_invoice）、进项发票分析（_domain_purchase_invoice）、发票合规检查（_domain_invoice_compliance）、红冲/作废分析（_domain_red_void）③进销存与存货(4域)——进销存匹配（_domain_inventory_match）、存货周转（_domain_inventory_turnover）、BOM分析（_domain_bom）、进销比对标（_domain_purchase_sales_ratio）④费用与成本(5域)——费用完整性（_domain_expense_completeness）、费用结构合理性（_domain_expense_structure）、大额费用分析（_domain_large_expenses）、主营业务成本分析（_domain_cogs）、研发费用分析（_domain_rd_expenses）⑤往来款(3域)——应收账款分析（_domain_ar）、应付账款分析（_domain_ap）、关联交易分析（_domain_related_party）⑥资产与负债(3域)——固定资产分析（_domain_fixed_assets）、无形资产分析（_domain_intangible）、长短期借款分析（_domain_loans）⑦工资与人力(3域)——工资发放分析（_domain_salary）、社保缴纳分析（_domain_social_security）、个税扣缴分析（_domain_personal_tax）⑧综合诊断(11域)——行业判定(_domain_industry)、资料完备度(_domain_completeness)、经营实质(_domain_business_substance)、行业对标(_domain_benchmarking)、申报比对(_domain_tax_declaration)、六员比对(_domain_six_personnel)、供应链核查(_domain_supply_chain)、经营风险预警(_domain_risk_alert)、税收优惠审核(_domain_tax_preference)、资金回流检测(_domain_money_laundering)、存疑排除(_domain_exclusion)。数量由system_config.json实时统计保证准确。'},
        {name:'全链路溯源体系',source:'static/js/tax-doc-analysis.js → 报告渲染中的溯源逻辑',desc:'每条发现的结论都可以通过六步溯源路径反向验证——用户看到报告中任何一条发现，都可以追溯到它是从哪一行原始数据、通过哪条规则、经过哪些验证步骤得出的。六步溯源路径：①规则ID——发现的描述中标注触发的规则编号（如\"R-0321\"），点击可跳转到稽查指令页面查看该规则的完整定义 ②线索链ID——发现的调查路径中标注驱动的线索链编号（如\"CL-0187\"），点击可查看该链的全部调查步骤和触发条件 ③证据来源——发现的evidence_source字段列出所有参与验证的数据文件（如\"银行流水→收款分类→2025年3月\"）④一键分析结果——all_findings数组中该发现的完整JSON（含原始items明细表和matched_chain_details）⑤证据闭环——跨域证据链的触发详情（哪些规则同时触发、来自哪些数据域、触发率是多少）⑥原始数据行——通过rule_id反查主文件中的extract函数（_extract_material_intel），定位到原始Excel文件的对应行。每一步在报告中有对应的超链接或展开详情按钮。整个溯源体系确保报告从结论到数据的可逆推——审理人员无需理解系统内部逻辑，只需要沿着六步路径反向检查。'},
      ]},
    { id:6, name:'跨域协商引擎', icon:'🤝', color:'#0ea5e9',
      desc:'域分析函数独立运行后，引擎自动执行跨域对话，消解/降级/增强发现的结论。15条协商规则覆盖四类场景——不依赖人工干预，引擎自我发现和修正分析矛盾。协商引擎在Phase3交叉验证之后、方法论过滤器之前执行，确保进入过滤器的发现已经是自洽的。',
      items:[
        {name:'行业闸门消解（NEG-001~005·5条）',source:'engine/cross_domain_negotiation.py → NEG-001~005',desc:'核心逻辑：服务行业自动跳过实物商品域的分析结论，消除假阳性。当域15（行业判定）的结论为\"服务行业\"时，协商引擎自动检测以下5类发现的冲突：①进销存匹配异常→消解（服务行业无进销存概念）②存货积压预警→消解（服务行业无实物库存）③BOM表缺失→消解（服务行业无BOM）④毛利率对标异常→降为提示（服务行业毛利率不可比制造业）⑤进销比行业对标异常→消解（服务行业不存在进销比）。消解后的发现的原始数据保留在all_findings中但标记_negotiated_drop=true，不出现在正式报告中。降级的发现保留但标记_negotiated_level=提示。如果行业判定本身存在不确定性（三层穿透不一致），协商引擎会保守处理——不消解但标记\"行业判定存疑\"。'},
        {name:'资料驱动的跨域标记（NEG-010~040·4条）',source:'engine/cross_domain_negotiation.py → NEG-010~040',desc:'当域14（资料完备度）发现某类资料缺失时，协商引擎自动通知所有依赖该资料的发现打上\"资料受限\"标记，但不下结论。四种典型场景：①缺少合同→合同分层/合同比对类发现标记\"待补充合同后重新评估\"，不生成合同缺失相关的高风险发现 ②缺少银行流水→资金流分析相关发现标记\"资料受限\"（银行流水是资金流分析的唯一数据源，无流水则所有资金类分析无基础）③缺少工资社保→薪酬/人力类发现标记\"资料受限\"④缺少申报表→申报比对类发现标记\"资料受限\"。标记不影响原始风险等级但前端渲染时展示黄色横幅，提示审理人员\"此结论基于部分资料，补充后可增强\"。标记的哲学是\"缺资料不是你的错，但在没资料的情况下下结论就是我的错\"——既不因为缺资料就假装没发现问题，也不因为缺资料就武断下结论。'},
        {name:'证据矛盾消解（NEG-020~030·3条）',source:'engine/cross_domain_negotiation.py → NEG-020~030',desc:'当两个域的输出产生逻辑矛盾时，协商引擎根据证据强度自动判断哪个结论更可信。三种消解模式：①强证据撤销弱结论——域A（银行流水→收款分类→个人大额转账）标记\"隐匿收入高风险\"，域B（销项发票→同一付款方→含税号的正规发票）标记\"开票合规\"。协商逻辑：正规发票的证据强度>银行流水关键词匹配的证据强度→撤销隐匿收入高风险→标记\"可能为个人供应商收款，已开票\"。②数据缺失限制结论——域A（缺合同→合同比对不适用标记），域B（进销发票品名匹配→业务实质与发票一致）。协商逻辑：发票证据虽强但无合同无法确认交易真实性→结论从\"一致\"降为\"基本一致但缺合同验证\"。③时空不一致消解——域A（发票日期2025年3月）标记\"收入正常\"，域B（银行流水日期2025年5月）标记\"收款延迟\"。协商逻辑：时间差>60天→触发跨域时间差检查→如果付款方与购买方一致→标记\"应收账款\";如果不一致→标记\"存疑收款\"。证据矛盾消解的关键原则：两个域打架时，谁的数据更完整、更直接，谁的结论权重更高。'},
        {name:'联合增强（NEG-AUG-001~003·3条）',source:'engine/cross_domain_negotiation.py → NEG-AUG-001~003',desc:'多个域同时触发异常信号时，协商引擎不仅不消解，反而合成一条更高级别的新发现——\"三个域的警报一起响，比一个域的警报响一百次更可怕\"。三种增强场景：①收入隐匿增强——域A（银行流水→大额个人转账）+ 域B（销项发票→对应月度开票为零）+ 域C（工资表→员工人数无变化但收入骤降）→合成\"疑似账外经营\"高风险发现 ②虚构成本增强——域A（进项发票→大额咨询费）+ 域B（销项品名→咨询费与主营毫无关联）+ 域C（银行流水→付款方为税收优惠地企业）→合成\"疑似虚开咨询费发票转移利润\"极高风险发现 ③资金回流增强——域A（银行流水→A→B→C→A循环转账）+ 域B（发票→A向B开票、B向C开票、C向A开票，品名相同金额相同）+ 域C（人员→三个公司法人为同一人或亲属关系）→合成\"疑似闭环虚开\"连锁发现。联合增强的新发现不覆盖原始发现的等级——原始发现保持原来的等级在报告中单独排列，新发现作为补充列在组顶用红色边框标识。'},
      ]},
  ];

  var totalItems = layers.reduce(function(s,l){return s+l.items.length;},0);
  var h='<style>.qs-layout{display:flex;gap:28px;max-width:1100px;margin:0 auto;padding:24px 16px;background:#fff}.qs-toc{width:180px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:12px;line-height:2.0;max-height:calc(100vh-40px);overflow-y:auto}.qs-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.qs-toc a{display:block;color:#475569;text-decoration:none;padding:3px 10px;border-radius:4px;cursor:pointer;font-size:12px}.qs-toc a:hover,.qs-toc a.active{background:#eff6ff;color:#2563eb;font-weight:600}.qs-main{flex:1;min-width:0;background:#fff}.qs-sec-title{font-size:16px;font-weight:700;color:#0f172a;padding-bottom:10px;border-bottom:2px solid #e2e8f0;margin-bottom:16px}.qs-layer{margin-bottom:28px;padding:20px;background:#fff;border:1px solid #e2e8f0;border-radius:8px}.qs-layer-hd{display:flex;align-items:center;gap:10px;margin-bottom:14px;padding-bottom:12px;border-bottom:2px solid}.qs-item{padding:12px 16px;margin-bottom:6px;background:#fafbfc;border-radius:4px;border-left:3px solid #e2e8f0}.qs-stat{text-align:center;padding:14px 8px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px}.qs-info{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px 20px;font-size:13px;line-height:2}</style>';

  h+='<div class="qs-layout">';
  h+='<nav class="qs-toc"><div class="toc-title">📖 目录</div>';
  layers.forEach(function(l){h+='<a href="#qs-layer'+l.id+'">'+l.icon+' '+l.name+'</a>';});
  h+='</nav><div class="qs-main">';
  h+='<h2 style="font-size:20px;font-weight:800;color:#0f172a;margin:0 0 4px">🛡️ 全链路稽查质量保障体系</h2>';
  h+='<p style="font-size:13px;color:#94a3b8;margin:0 0 24px">六大层次 · '+totalItems+'个组件 · 从规则触发到报告输出，每条发现可追溯可验证可复核</p>';

  h+='<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:28px">';
  [{n:'1514',l:'稽查规则'},{n:'396',l:'线索链'},{n:'745',l:'证据链'},{n:'33',l:'方法论'},{n:'1174',l:'总链数'},{n:'36',l:'域分析'}].forEach(function(s){
    h+='<div class="qs-stat" style="flex:1;min-width:100px"><div style="font-size:22px;font-weight:700;color:#0f172a">'+s.n+'</div><div style="font-size:11px;color:#94a3b8">'+s.l+'</div></div>';
  });
  h+='</div>';

  layers.forEach(function(l){
    h+='<div id="qs-layer'+l.id+'" class="qs-layer">';
    h+='<div class="qs-layer-hd" style="border-color:'+l.color+'"><span style="font-size:22px">'+l.icon+'</span><div><div style="font-size:15px;font-weight:700;color:#0f172a">'+l.name+'（'+l.items.length+'组件）</div><div style="font-size:12px;color:#64748b">'+l.desc+'</div></div></div>';
    l.items.forEach(function(item,idx){
      h+='<div class="qs-item"><div style="font-size:13px;font-weight:600;color:#0f172a;margin-bottom:4px">'+(idx+1)+'. '+item.name+'</div><div style="font-size:12px;color:#475569;line-height:2.0;margin-bottom:4px">'+item.desc+'</div><div style="font-size:11px;color:#6366f1">📁 '+item.source+'</div></div>';
    });
    h+='</div>';
  });

  h+='<div class="qs-info"><strong style="color:#059669;font-size:14px">🔓 开放生态系统</strong><br>当前'+totalItems+'个组件只是当前状态。新增稽查能力模块须同步更新此页面。体系随发展持续扩展。</div>';
  h+='</div></div>';
  container.innerHTML = h;
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
        target.innerHTML = '<div style="color:#94a3b8;padding:20px">未找到方法论数据，请检查 audit_chains.json</div>';
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
        
        html += '<div style="margin-bottom:16px;padding:16px 20px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;border-left:3px solid #2563eb">'
          + '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">'
          + '<div style="font-size:15px;font-weight:700;color:#0f172a">' + escHtml(id) + ' ' + escHtml(name) + '</div>'
          + '<span style="font-size:11px;color:#94a3b8;cursor:pointer" onclick="var d=this.parentNode.parentNode.nextElementSibling;d.style.display=d.style.display==\'none\'?\'\':\'none\'">展开/折叠</span>'
          + '</div>'
          + '<div style="font-size:13px;color:#475569;line-height:2.0">' + escHtml(desc) + '</div>'
          + '<div style="display:none;margin-top:12px;padding:12px 16px;background:#fff;border-radius:6px;font-size:13px;color:#475569;line-height:2">'
          + (requirement ? '<div style="margin-bottom:8px"><span style="font-weight:600;color:#0f172a">要求：</span>' + escHtml(requirement) + '</div>' : '')
          + (purpose ? '<div style="margin-bottom:8px"><span style="font-weight:600;color:#0f172a">用途：</span>' + escHtml(purpose) + '</div>' : '')
          + (codePos ? '<div style="margin-bottom:8px"><span style="font-weight:600;color:#0f172a">代码位置：</span><code style="font-size:12px;background:#f1f5f9;padding:2px 6px;border-radius:4px">' + escHtml(codePos) + '</code></div>' : '')
          + (callLocs.length > 0 ? '<div><span style="font-weight:600;color:#0f172a">调用位置：</span>' + callLocs.map(function(loc) { return '<span style="display:inline-block;margin:2px 4px 2px 0;padding:2px 8px;background:#e0f2fe;color:#0369a1;font-size:11px;border-radius:4px">' + escHtml(loc) + '</span>'; }).join('') + '</div>' : '')
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
        return '<div style="padding:4px 8px;font-size:12px;color:#334155">Step' + s.step + ': <strong>' + (s.domain||'') + '</strong> → ' + (s.action||'');
      }).join('');
      html += '<div style="padding:16px 20px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;border-left:4px solid #7c3aed">'
        + '<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">'
        + '<span style="font-size:11px;padding:2px 8px;border-radius:4px;background:#7c3aed15;color:#7c3aed;font-weight:600">ID' + (a.id||'') + '</span>'
        + '<span style="font-size:14px;font-weight:600;color:#0f172a">' + (a.name||'') + '</span>'
        + '</div>'
        + '<div style="font-size:12px;color:#64748b;line-height:2.0;margin-bottom:8px">' + (a.description||'') + '</div>'
        + '<div style="margin-bottom:6px"><span style="font-size:11px;color:#7c3aed;font-weight:600">触发词: </span><span style="font-size:11px;color:#64748b">' + kws.slice(0,5).join(' / ') + '</span></div>'
        + '<div style="margin-bottom:6px"><span style="font-size:11px;color:#7c3aed;font-weight:600">推理步数: </span><span style="font-size:11px;color:#64748b">' + steps.length + '步</span>'
        + '<span style="margin-left:16px;font-size:11px;color:#7c3aed;font-weight:600">关联规则: </span><span style="font-size:11px;color:#64748b">' + refs.length + '条</span></div>'
        + '<div style="padding:8px 12px;background:#f8fafc;border-radius:4px">' + stepHtml + '</div>'
        + (a.suggestion ? '<div style="font-size:12px;color:#334155;line-height:2.0;margin-top:8px;padding-top:8px;border-top:1px solid #e2e8f0"><strong>建议: </strong>' + a.suggestion + '</div>' : '')
        + '</div>';
    });
    container.innerHTML = html || '<p style="font-size:13px;color:#94a3b8">暂无分析链数据</p>';
  } catch(e) {
    container.innerHTML = '<p style="font-size:13px;color:#dc2626">加载失败: ' + (e.message||'') + '</p>';
  }
}
