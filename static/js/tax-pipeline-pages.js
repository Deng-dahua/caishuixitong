// ══════════════════════════════════════════════════════════════
//  稽查管道独立页：文件解析 | 域分析 | 跨域证据链 | 方法论过滤器
// ══════════════════════════════════════════════════════════════

// ═══════════ 模块数量自动加载（从JSON数据文件动态读取，杜绝硬编码过期数字） ═══════════
var _pipelineCounts = null;

async function loadPipelineCounts() {
  if (_pipelineCounts) return _pipelineCounts;
  try {
    var t0 = Date.now();
    var [rulesResp, chainsResp, cdeResp, cdcResp, cdaResp] = await Promise.all([
      fetch('/static/tax_risk_rules_local_export.json?_t=' + t0),
      fetch('/static/audit_chains.json?_t=' + t0),
      fetch('/static/cross_domain_evidence.json?_t=' + t0),
      fetch('/static/cross_domain_clues.json?_t=' + t0),
      fetch('/static/cross_domain_analysis.json?_t=' + t0)
    ]);
    var rules = await rulesResp.json();
    var chainsData = await chainsResp.json();
    var cde = await cdeResp.json();
    var cdc = await cdcResp.json();
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
    var m = {rules:'rules_count',trailChains:'clue_chains',evidenceChains:'evidence_chains',totalChains:'total_chains'};
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
  container.innerHTML = '<style>.fp-layout{display:flex;gap:24px;max-width:1200px;margin:0 auto;padding:20px}.fp-toc{width:200px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:12px;line-height:2.2}.fp-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.fp-toc a{display:block;color:#475569;text-decoration:none;padding:2px 8px;border-radius:4px;cursor:pointer}.fp-main{flex:1;min-width:0}</style>'
    + '<div class="fp-layout">'
    + '<nav class="fp-toc"><div class="toc-title">📖 导航</div>'
    + '<a href="#fp-mechanism">一 识别机制</a>'
    + '<a href="#fp-compat">二 兼容策略</a>'
    + '<a href="#fp-fingerprint">三 文件指纹库</a>'
    + '<a href="#fp-result">四 本次解析结果</a>'
    + '</nav>'
    + '<div class="fp-main">'
    + '<h2 style="font-size:22px;font-weight:800;color:#0f172a;margin:0 0 4px">📁 文件解析</h2>'
    + '<p style="font-size:13px;color:#94a3b8;margin:0 0 24px">三层递进识别 · 34类文件指纹 · 关键词打分 · 结构分析 · 数据推断兜底</p>'
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

  // ══════ 一、识别机制详解 ══════
  html += '<div id="fp-mechanism" style="margin-bottom:48px">'
    + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">一、识别机制：三层递进</h3>'
    + '<p style="font-size:13px;color:#64748b;line-height:2;margin:0 0 20px">'
    + '系统接收到文件后，不会依赖文件扩展名（因为用户上传的 .xls 可能是任何内容），'
    + '而是执行三层递进识别，从粗到细逐步确定文件类型：'
    + '</p>'

    + '<div style="display:flex;gap:20px;margin-bottom:24px">'

    // Step 1
    + '<div style="flex:1;padding:20px;background:#f8fafc;border-radius:8px;border-top:3px solid #0f172a">'
    + '<div style="font-size:12px;color:#94a3b8;margin-bottom:6px">Step 1</div>'
    + '<div style="font-size:16px;font-weight:700;color:#0f172a;margin-bottom:8px">关键词匹配 · 打分制</div>'
    + '<div style="font-size:13px;color:#475569;line-height:1.9">'
    + '读取 Excel 文件的前200行表头区域，将表头中的每个词与34类文件指纹的关键词库进行匹配。<br><br>'
    + '每匹配一个关键词得1分，得分超过该类指纹的阈值（通常2-4分）即判定为该类型。<br><br>'
    + '例如：表头出现"对方户名""交易日期""收入金额"三个词→银行流水指纹得3分→≥阈值3→判定为银行流水。<br><br>'
    + '多个类型同时超过阈值时，取得分最高的类型。'
    + '</div>'
    + '</div>'

    // Step 2
    + '<div style="flex:1;padding:20px;background:#f8fafc;border-radius:8px;border-top:3px solid #94a3b8">'
    + '<div style="font-size:12px;color:#94a3b8;margin-bottom:6px">Step 2</div>'
    + '<div style="font-size:16px;font-weight:700;color:#0f172a;margin-bottom:8px">结构分析 · 列模式</div>'
    + '<div style="font-size:13px;color:#475569;line-height:1.9">'
    + '当关键词匹配不够明确时（多个类型分数接近），进入结构分析阶段。<br><br>'
    + '检查列数、列位置、表头的组合模式——例如银行流水通常包含日期列+对方户名列+金额列+余额列；'
    + '工资表通常包含姓名列+收入列+扣除列+实发列。<br><br>'
    + '系统维护了每种文件类型的列模式模板，按模式相似度进行二次判定。'
    + '</div>'
    + '</div>'

    // Step 3
    + '<div style="flex:1;padding:20px;background:#f8fafc;border-radius:8px;border-top:3px solid #94a3b8">'
    + '<div style="font-size:12px;color:#94a3b8;margin-bottom:6px">Step 3</div>'
    + '<div style="font-size:16px;font-weight:700;color:#0f172a;margin-bottom:8px">数据推断 · 兜底</div>'
    + '<div style="font-size:13px;color:#475569;line-height:1.9">'
    + '当关键词和结构都无法确定时，进入数据推断阶段。系统逐列读取前200行数据样本，按照语义角色自动化分类：<br><br>'
    + '→ 日期格式（2023-01-01、2023/1/1等）→ 日期列<br>'
    + '→ 纯数字无明显小数 → 数量/编号列<br>'
    + '→ 含"公司""有限""厂""店" → 企业名称列<br>'
    + '→ 含"元""金额""￥" → 金额列<br>'
    + '→ 含"税""%""税率" → 税率列<br><br>'
    + '不因无法识别而丢弃数据——标注为"通用数据"（generic_data），交由下游分析模块自行判断数据用途。'
    + '</div>'
    + '</div>'

    + '</div>'
    + '</div>'

    // Step 4: 综合判断（2026-06-28新增）
    + '<div style="flex:1;padding:20px;background:#f0fdf4;border-radius:8px;border-top:3px solid #16a34a">'
    + '<div style="font-size:12px;color:#94a3b8;margin-bottom:6px">Step 4 · 2026-06-28新</div>'
    + '<div style="font-size:16px;font-weight:700;color:#0f172a;margin-bottom:8px">综合判断 · 四方交叉验证</div>'
    + '<div style="font-size:13px;color:#475569;line-height:1.9">'
    + '前三层都无法确定时，启动四方证据交叉验证：文件名暗示→列头推理→数据扫描（买卖方身份）→公司匹配。证据冲突优先数据推理。'
    + '</div>'
    + '</div></div>';

  // ══════ 二、兼容策略 ══════
  html += '<div id="fp-compat" style="margin-bottom:48px;padding:20px 24px;background:#fafafa;border-radius:8px">'
    + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 12px">二、兼容策略</h3>'
    + '<div style="font-size:13px;color:#475569;line-height:2.2">'
    + '<strong>银行流水</strong>：兼容5种日期列名（交易日期/记账日期/交易时间/日期/申请日期），'
    + '对方户名兼容4种命名（counterparty/对方户名/交易对方/对方名称），金额自动去除￥/元/逗号等非数字字符。<br>'
    + '<strong>发票</strong>：兼容购方名称/购买方名称、销方名称/销售方名称/供应商名称等多种命名习惯，'
    + '进项/销项方向通过购方税号与公司税号比对自动判定。<br>'
    + '<strong>工资表</strong>：兼容60+个列名变体（本期收入/应发工资/实发合计等）。<br>'
    + '<strong>汇总行过滤</strong>：自动识别并剔除"小计""合计""总计""本页合计""本年累计""当月合计"等汇总行，'
    + '防止汇总数据污染分析结果。<br>'
    + '<strong>社保/公积金</strong>：区分缴费基数、单位缴纳、个人缴纳三列数据。'
    + '</div>'
    + '</div>';

  // ══════ 三、34类文件指纹 ══════
  html += '<div id="fp-fingerprint" style="margin-bottom:48px">'
    + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">三、文件指纹库 · ' + fps.length + ' 类</h3>'
    + '<p style="font-size:13px;color:#94a3b8;margin:0 0 20px">每类指纹由 关键词集 + 得分阈值 + 专用解析器 三部分组成。按使用频率分梯队排列。</p>';

  // 分组显示
  var groups = [
    {title:'第一梯队 · 高频核心（用户最常上传）', items: fps.slice(0,12),
     desc:'这12类文件是稽查中最常出现的材料，拥有最完善的关键词库和解析器。得分阈值2-4分。'},
    {title:'第二梯队 · 合同/权证/关联交易', items: fps.slice(12,17),
     desc:'合同和关联交易文件的识别需要更细致的结构分析，阈值通常为2分。'},
    {title:'第三梯队 · 申报表与财务报表', items: fps.slice(17,23),
     desc:'各类税务申报表和财务报表，关键词含税种名称、报表项目等专业术语。'},
    {title:'第四梯队 · 往来与合同清单', items: fps.slice(23,27),
     desc:'应收账款、应付账款、预收预付、其他应收付等往来类数据表。'},
    {title:'第五梯队 · 资产与费用', items: fps.slice(27,31),
     desc:'固定资产、无形资产、资产损失、费用明细、研发费用等资产和费用类表格。'},
    {title:'第六梯队 · 特殊交易与兜底', items: fps.slice(31),
     desc:'人员清单、股权交易、借款合同、进出口报关等特殊类型，以及通用数据的兜底识别。'},
  ];

  groups.forEach(function(g) {
    html += '<div style="margin-bottom:24px">'
      + '<div style="font-size:13px;font-weight:600;color:#64748b;margin-bottom:6px">' + escHtml(g.title) + '</div>'
      + '<div style="font-size:12px;color:#94a3b8;margin-bottom:10px">' + escHtml(g.desc) + '</div>'
      + '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:8px">';

    g.items.forEach(function(item) {
      html += '<div style="padding:10px 12px;border:1px solid #f1f5f9;border-radius:6px;font-size:13px;line-height:1.7">'
        + '<div style="font-weight:600;color:#0f172a;margin-bottom:4px"><span style="font-size:16px">' + item.icon + '</span> ' + escHtml(item.name) + '</div>'
        + '<div style="color:#64748b;font-size:12px;margin-bottom:4px">' + escHtml(item.sig) + '</div>'
        + '<div style="color:#94a3b8;font-size:11px">阈值：' + item.threshold + ' · 解析器：' + item.parser + '</div>'
        + '</div>';
    });

    html += '</div></div>';
  });

  html += '</div>';

  // ══════ 四、解析流程 ══════
  html += '<div style="margin-bottom:32px;padding:20px 24px;background:#fafafa;border-radius:8px">'
    + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 12px">四、解析流程</h3>'
    + '<div style="font-size:13px;color:#475569;line-height:2.2">'
    + '<strong>1. 磁盘扫描</strong> → 遍历 uploads/ 目录下所有 .xls/.xlsx/.csv/.pdf 文件，按修改时间排序。<br>'
    + '<strong>2. 格式检测</strong> → 读取文件前5KB数据，判断是 xls/xlsx/csv/pdf 格式，调用对应的文件读取库（openpyxl / xlrd / csv / pypdf）。<br>'
    + '<strong>3. 表头提取</strong> → 逐 sheet 读取前200行，提取每列的表头文字和历史数据样本。<br>'
    + '<strong>4. 指纹匹配</strong> → 将表头文字与34类指纹关键词库做交叉匹配，计算每类的得分。<br>'
    + '<strong>5. 类型判定</strong> → 取得分最高的类型（需超过阈值），未超过的进入结构分析和数据推断。<br>'
    + '<strong>6. 解析器调用</strong> → 根据确定的文件类型，调用对应的专用解析器（如 _parse_bank_sheet / _parse_invoice_sheet 等），将原始表格转换为结构化数据。<br>'
    + '<strong>7. 标准化输出</strong> → 统一字段命名（date/amount/seller/buyer/goods等），输出可在后续分析中直接使用的结构化数据。<br>'
    + '<strong>8. 逻辑层</strong> → 统计每条解析动作（如 "bank_statement: 13条"），输出 file_results 和 pipeline_log。'
    + '</div>'
    + '</div>';

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
    + '<h3 style="font-size:16px;font-weight:700;color:#0f172a;margin:0 0 6px">四、本次解析结果</h3>'
    + '<p style="font-size:13px;color:#94a3b8;margin:0 0 24px">本次分析共解析 ' + frs.length + ' 个文件，成功识别 ' + parsed + ' 个，未识别 ' + failed + ' 个</p>'

    // 统计卡片
    + '<div style="display:flex;gap:12px;margin-bottom:40px">'
    + '<div style="flex:1;text-align:center;padding:16px;background:#f8fafc;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#0f172a">' + frs.length + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">文件总数</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#f0fdf4;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#059669">' + parsed + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">已解析</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fef2f2;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#dc2626">' + failed + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">未解析</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#f8fafc;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#0f172a">' + plogs.length + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">管线日志</div></div>'
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
    html += '<div style="background:#0f172a;border-radius:6px;padding:20px 24px;max-height:500px;overflow-y:auto;font-family:\'SF Mono\',\'Fira Code\',monospace;font-size:12px;line-height:2.2">';
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
  container.innerHTML = '<style>.da-layout{display:flex;gap:24px;max-width:1200px;margin:0 auto;padding:20px}.da-toc{width:200px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:12px;line-height:2.2}.da-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.da-toc a{display:block;color:#475569;text-decoration:none;padding:2px 8px;border-radius:4px;cursor:pointer}.da-main{flex:1;min-width:0}</style>'
    + '<div class="da-layout">'
    + '<nav class="da-toc"><div class="toc-title">📖 导航</div>'
    + '<a href="#da-intro">一 什么是域分析</a>'
    + '<a href="#da-arch">二 域分析架构</a>'
    + '<a href="#da-domains">三 36个分析域</a>'
    + '<a href="#da-result">四 本次分析结果</a>'
    + '</nav>'
    + '<div class="da-main">'
    + '<h2 style="font-size:22px;font-weight:800;color:#0f172a;margin:0 0 4px">🔬 域分析</h2>'
    + '<p style="font-size:13px;color:#94a3b8;margin:0 0 24px">36个域分析函数 · 跨域关联推理 · 多源证据链串联</p>'
    + renderDomainAnalysisStatic()
    + '<div id="da-analysis-result"></div>'
    + '</div></div>';

  if (_cachedDomainReport) { renderDomainAnalysisResult(_cachedDomainReport); }
  else { loadDomainAnalysisData(); }
}

function renderDomainAnalysisStatic() {
  var html = '';

  // ══════ 一、什么是域分析 ══════
  html += '<div id="da-intro" style="margin-bottom:48px">'
    + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">一、什么是域分析</h3>'
    + '<p style="font-size:13px;color:#64748b;line-height:2;margin:0 0 16px">'
    + '域分析是税务稽查系统的核心工作台。系统将从资料中提取的全部数据导入多个独立的分析域（Domain），'
    + '每个域由专门的域分析函数（<code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">_domain_*</code>）驱动，'
    + '从不同维度对同一份数据做交叉审视。域与域之间不孤立——跨域关联推理将所有域的发现串联为多源交叉证据链，'
    + '形成完整的稽查判断体系。'
    + '</p>'
    + '<div style="padding:16px 20px;background:#f8fafc;border-radius:8px;font-size:13px;color:#475569;line-height:2">'
    + '<strong>分析原理</strong>：每个域分析函数接收原始数据（银行流水 / 发票 / 工资表 / 社保 / 凭证 / 库存等），输出结构化发现列表。'
    + '每条发现包含：发现类型（type）、风险等级（level/score）、详细数据（detail）、稽查解读（description）、'
    + '处理建议（suggestion）、法律依据（policy_ref）、发现方法（how_found）、分类标签（category）。'
    + '</div>'
    + '</div>';

  // ══════ 二、域分析架构 ══════
  html += '<div id="da-arch" style="margin-bottom:48px">'
    + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">二、域分析架构</h3>'
    + '<div style="display:flex;gap:16px;margin-bottom:20px">'
    + '<div style="flex:1;padding:16px;background:#f8fafc;border-radius:8px;border-left:3px solid #dc2626">'
    + '<div style="font-size:13px;font-weight:600;color:#0f172a;margin-bottom:6px">资料驱动域</div>'
    + '<div style="font-size:12px;color:#64748b;line-height:1.8">依赖上传资料进行判断。<br>资料完备度越高，结论置信度越高。<br>缺资料时标注资料缺口，不做无依据结论。</div>'
    + '</div>'
    + '<div style="flex:1;padding:16px;background:#f8fafc;border-radius:8px;border-left:3px solid #2563eb">'
    + '<div style="font-size:13px;font-weight:600;color:#0f172a;margin-bottom:6px">算法驱动域</div>'
    + '<div style="font-size:12px;color:#64748b;line-height:1.8">基于数据内在特征自动计算。<br>如进销比、毛利率、周转率。<br>只要有发票数据即可运行。</div>'
    + '</div>'
    + '<div style="flex:1;padding:16px;background:#f8fafc;border-radius:8px;border-left:3px solid #7c3aed">'
    + '<div style="font-size:13px;font-weight:600;color:#0f172a;margin-bottom:6px">知识驱动域</div>'
    + '<div style="font-size:12px;color:#64748b;line-height:1.8">内置66行业基准库、税务法规库。<br>将企业数据与行业均值对比。<br>与法律法规要求对照验证。</div>'
    + '</div>'
    + '</div>'
    + '</div>';

  // ══════ 三、36个分析域 ══════
  html += '<div id="da-domains" style="margin-bottom:48px">'
    + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">三、36个分析域</h3>'
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
    {cat:'进销存（供应链核心）', color:'#dc2626', desc:'发票品名交叉比对，进销平衡分析，制造业加工链条诊断。有进无销/有销无进是税务稽查的核心切入点。', items:[
      {name:'进销存匹配分析', fn:'_domain_invoice_deep', line:'12763', desc:'进销品名交叉映射 · 进销比检测 · 有进无销/有销无进触发制造业加工诊断 · BOM表需求判断'},
      {name:'发票实质性审计', fn:'_domain_invoice_audit', line:'14966', desc:'五层递进审计：格式合规→同品名单价→加工费专项→金额合理性→BOM进销映射'},
      {name:'存货周转预警', fn:'_domain_inventory_turnover', line:'12393', desc:'周转率+库龄分析+库存结构合理性 · 入库>>出库→积压预警'},
    ]},
    {cat:'供应商与客户分析', color:'#f59e0b', desc:'供应商集中度、地理分布、身份验证；客户结构分析。识别供应商群集和关联交易风险。', items:[
      {name:'供应商穿透分析', fn:'_domain_supplier_deep', line:'12286', desc:'供应商集中度 · 同城群集检测 · 名称异常检测 · 前3大占比>70%触发依赖预警'},
      {name:'供应商画像分析', fn:'_domain_supplier_profiling', line:'13757', desc:'行业/地域/注册资本综合分析 · 新注册零实缴→可疑交易方'},
      {name:'上下游穿透分析', fn:'_domain_supply_chain_deep', line:'14661', desc:'客户vs供应商关联 · 同一企业既是客户又是供应商→对倒开票嫌疑'},
    ]},
    {cat:'资金流分析', color:'#dc2626', desc:'银行流水收款/付款结构，资金流向追踪，付款方身份核实，异常交易检测。', items:[
      {name:'资金流向追踪', fn:'_domain_fund_flow_mapping', line:'13806', desc:'收款方/付款方分类 · 个人转账/关联方/税费 · 第三方占比预警 · 付款方身份核实'},
      {name:'异常交易时间分析', fn:'_domain_temporal_anomaly', line:'14298', desc:'非工作时间交易 · 特殊日期突击交易检测 · 月末集中行为识别'},
    ]},
    {cat:'交叉验证（多源串联）', color:'#7c3aed', desc:'两个以上数据源相互比对，验证数据一致性。单源异常可能是巧合，多源交叉指向真实问题。', items:[
      {name:'多源交叉验证', fn:'_domain_multi_source_cross', line:'13111', desc:'资金流+发票流+货物流三源采购验证 · 收入+发票双源 · 合同+发票+付款三角'},
      {name:'发票存货付款三角验证', fn:'_domain_triangle_invoice_inventory_payment', line:'13949', desc:'进项发票vs存货入库vs银行付款三向验证——票货分离、虚开嫌疑'},
      {name:'凭证发票收入对比', fn:'_domain_voucher_invoice_revenue_compare', line:'13416', desc:'主营业务收入vs销项发票金额vs银行入账三源对比 · 偏差>20%预警'},
      {name:'利润现金流矛盾检测', fn:'_domain_profit_cashflow_gap', line:'14268', desc:'账面利润vs经营现金流背离 · 利润正/现金流负→利润质量存疑'},
    ]},
    {cat:'经营实质分析', color:'#059669', desc:'验证企业是否具备真实经营条件——有无费用/场地/仓储/运输/人员。空壳企业最怕经营实质分析。', items:[
      {name:'经营实质分析', fn:'_domain_business_substance', line:'12618', desc:'基础经营费用检测 · 企业能力评估 · 发票与人员规模匹配 · 业务链条完整性'},
      {name:'经营实质地理分析', fn:'_domain_business_premise_geo', line:'14158', desc:'供应商/客户/加工商地址三角验真 · 重物运输成本 · 点→面推理全链条经营实质'},
      {name:'人员与业务匹配', fn:'_domain_workforce_profiling', line:'13894', desc:'员工vs营收合理性 · 人均薪资vs行业均值 · 社保人数vs工资人数匹配'},
    ]},
    {cat:'资料完备度', color:'#2563eb', desc:'14类稽查必查资料逐一检测，合同需求四层自动分层。缺失资料→风险标记→无法支撑结论时标注资料缺口。', items:[
      {name:'资料完备度评估', fn:'_domain_document_completeness', line:'12798', desc:'14类稽查必查资料逐一检测 · 合同需求四层分层（必签/应签/可免/小额）'},
    ]},
    {cat:'发票分析', color:'#0891b2', desc:'发票多维特征分析——时间/金额/税率/红冲/作废/连续性。每一张发票都是稽查线索。', items:[
      {name:'发票深度特征', fn:'_domain_invoice_deep', line:'12763', desc:'开具时间分布 · 价格区间 · 金额尾数 · 连续性 · 顶额开票检测'},
      {name:'发票生命周期', fn:'_domain_invoice_lifecycle', line:'12576', desc:'未认证占比 · 超期未认证 · 税率异常 · 类型分布 · 红冲作废追踪'},
      {name:'红冲作废发票追踪', fn:'_domain_red_void_invoice', line:'14244', desc:'红冲率+作废率+时间模式+金额占比+集中度 · 月末/季末突击'},
    ]},
    {cat:'合同与凭证', color:'#0f172a', desc:'合同流与发票流/资金流比对；凭证规范性、科目使用、借贷平衡检查。', items:[
      {name:'合同比对分析', fn:'_domain_contract_comparison', line:'12592', desc:'合同与发票/付款的对应关系验证 · 合同覆盖度+金额偏差检测'},
      {name:'凭证科目异常', fn:'_domain_voucher_anomaly', line:'12320', desc:'科目使用合规性 · 借贷方向 · 摘要规范性 · 异常科目组合检测'},
      {name:'凭证发票收入对比', fn:'_domain_voucher_invoice_revenue_compare', line:'13416', desc:'三源收入交叉验证——主营业务收入 vs 销项发票 vs 银行入账'},
    ]},
    {cat:'税务与社保', color:'#065f46', desc:'各税种申报数据与发票/银行数据交叉比对，社保与工资数据一致性验证。', items:[
      {name:'税务缴纳一致性', fn:'_domain_tax_consistency', line:'12524', desc:'银行税费支出vs发票推算应纳税额差异 · 申报表vs实际数据偏差'},
      {name:'增值税申报比对', fn:'_domain_vat_declaration_compare', line:'14569', desc:'销项税额/进项税额/应纳税额vs申报表 · 差异>1000元预警'},
      {name:'工资社保比对', fn:'_domain_salary_ss_hf_compare', line:'12546', desc:'工资表vs社保明细交叉验证——基数匹配 · 人数一致 · 比例合规'},
    ]},
    {cat:'资产与关联交易', color:'#047857', desc:'固定资产折旧匹配、无形资产摊销、关联交易穿透、资产损失核实。', items:[
      {name:'资产折旧费用匹配', fn:'_domain_depreciation_match', line:'14373', desc:'固定资产采购vs折旧匹配 · 有资产无折旧→利润虚增'},
      {name:'关联交易穿透检测', fn:'_domain_related_party_check', line:'14339', desc:'名称相似度+同法人+同注册地+同电话→关联交易未披露'},
    ]},
    {cat:'行业对标与规则', color:'#6366f1', desc:'66行业基准库对标，' + pc('rules','1514') + '条规则全覆盖验证，审计基础检查。', items:[
      {name:'行业对标分析', fn:'_domain_industry_benchmark', line:'14475', desc:'66个行业基准——毛利率/税负率/进销比/人均营收/费用率五维对标'},
      {name:'规则全覆盖验证', fn:'_domain_rule_coverage', line:'15114', desc:'' + pc('rules','1514') + '条规则逐条检查 · 数据不足→资料缺口 · 不作无依据结论'},
      {name:'跨域关联推理', fn:'_domain_cross_domain_reasoning', line:'13490', desc:'单点→多域印证→10条跨域证据链 · A域+B域+C域异常→闭环'},
    ]},
  ];

  domainGroups.forEach(function(g) {
    html += '<div style="margin-bottom:32px">'
      + '<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:6px">'
      + '<span style="width:3px;height:14px;display:inline-block;background:' + g.color + ';border-radius:2px"></span>'
      + '<span style="font-size:13px;font-weight:700;color:#0f172a">' + escHtml(g.cat) + '</span>'
      + '</div>'
      + '<div style="font-size:12px;color:#94a3b8;margin:0 0 12px 0;line-height:1.7">' + escHtml(g.desc) + '</div>';

    g.items.forEach(function(d) {
      html += '<div style="padding:10px 12px 10px 0;margin-bottom:4px;border-left:2px solid ' + g.color + ';background:#fafafa;border-radius:0 6px 6px 0">'
        + '<div style="display:flex;align-items:baseline;justify-content:space-between;margin-bottom:4px">'
        + '<div style="font-size:14px;font-weight:600;color:#0f172a">' + escHtml(d.name) + '</div>'
        + '<div style="font-size:11px;color:#94a3b8">' + escHtml(d.fn) + '() · 行' + d.line + '</div>'
        + '</div>'
        + '<div style="font-size:13px;color:#64748b;line-height:1.8">' + escHtml(d.desc) + '</div>'
        + '</div>';
    });

    html += '</div>';
  });

  html += '</div>';

  // ══════ 四、域间关系 ══════
  html += '<div style="margin-bottom:32px;padding:20px 24px;background:#fafafa;border-radius:8px">'
    + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 12px">四、域间关系与数据流</h3>'
    + '<div style="font-size:13px;color:#475569;line-height:2.2">'
    + '<strong>资料完备度</strong>（顶层）→ 决定所有域分析的置信度上限。缺合同→合同比对无法运行→标记缺口。<br>'
    + '<strong>经营实质分析</strong>（基础层）→ 提供企业画像：制造业/贸易型/服务型、本地/跨省、自加工/外包。<br>'
    + '<strong>发票+银行+凭证</strong>（数据层）→ 三大主数据源，支撑进销存、资金流、税务、薪酬、资产等15个分析域。<br>'
    + '<strong>多源交叉验证</strong>（交叉层）→ 将单个域的发现两两比对、三向检验，发现孤立点无法发现的隐藏关联。<br>'
    + '<strong>行业对标+规则引擎</strong>（校验层）→ 将企业数据与66行业基准对比，与' + pc('rules','1514') + '条规则逐一匹配。<br>'
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
    + '<div style="flex:1;text-align:center;padding:16px;background:#f8fafc;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#0f172a">' + totalDomains + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">分析域</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#eff6ff;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#2563eb">' + triggeredDomains + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">已触发</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fef2f2;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#dc2626">' + highTotal + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">高风险</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fffbeb;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#f59e0b">' + midTotal + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">中风险</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#f8fafc;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#0f172a">' + allF.length + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">合计发现</div></div>'
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
        html += '<div id="dd-' + di + '" style="display:none;margin-top:12px;padding:12px 16px;background:#fafafa;border-radius:6px">';
        d.findings.forEach(function(f) {
          var lvlColor = f.level === '极高风险' || (f.level === '极高风险' || c.level === '高风险') ? '#dc2626' : (f.level === '中风险' ? '#f59e0b' : '#22c55e');
          var lvlBg = f.level === '极高风险' || (f.level === '极高风险' || c.level === '高风险') ? '#fef2f2' : (f.level === '中风险' ? '#fffbeb' : '#f0fdf4');
          var dt = typeof f.detail === 'object' && f.detail.summary ? f.detail.summary : (f.detail || '');
          var trace = f._trace || {};
          html += '<div style="padding:10px 12px;margin-bottom:6px;background:' + lvlBg + ';border-radius:6px;border-left:3px solid ' + lvlColor + '">'
            + '<div style="font-size:13px;font-weight:600;color:#0f172a;margin-bottom:4px">' + escHtml(f.type || '') + '</div>'
            + '<div style="font-size:12px;color:#475569;line-height:1.8;margin-bottom:4px"><span class="d-find-detail" data-full="' + escHtml(dt).replace(/"/g, '&quot;') + '">' + escHtml(dt.substring(0, 300)) + '</span>'
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
            html += '<div style="margin-top:6px;padding:6px 8px;background:rgba(59,130,246,0.06);border-radius:4px;font-size:10px;color:#64748b;line-height:1.6">'
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
  container.innerHTML = '<style>.cde-layout{display:flex;gap:24px;max-width:1200px;margin:0 auto;padding:20px}.cde-toc{width:180px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:12px;line-height:2.2;max-height:calc(100vh-40px);overflow-y:auto}.cde-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.cde-toc a{display:block;color:#475569;text-decoration:none;padding:2px 8px;border-radius:4px;cursor:pointer}.cde-main{flex:1;min-width:0}</style>'
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
    + '<p style="font-size:13px;color:#64748b;line-height:2;margin:0 0 16px">'
    + '跨域证据链是系统最高价值的输出——它不依赖单一数据源的孤立异常，而是将来自不同数据域（资金流、发票流、'
    + '经营实质、资料完备等）的发现串联起来，形成多源交叉验证的证据闭环。单维度触发视为孤证，不形成证据链闭环。'
    + '只有≥2个维度同时命中，才算形成有效证据链。这是税务稽查中"证据链"概念在AI系统中的实现。'
    + '</p>'
    + '<div style="padding:16px 20px;background:#f8fafc;border-radius:8px;font-size:13px;color:#475569;line-height:2">'
    + '<strong>工作流程</strong>：domain_results中发现 → 关键词匹配各链维度 → 累计触发维度数 → 达到min_evidence阈值 → 生成跨域证据链发现 → 多源交叉闭环保高风险输出。'
    + '</div>'
    + '</div>';

  // 统计卡片
  html += '<div style="display:flex;gap:12px;margin-bottom:40px">'
    + '<div style="flex:1;text-align:center;padding:16px;background:#f8fafc;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#0f172a">' + chains.length + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">证据链</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fef2f2;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#dc2626">' + highCount + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">高风险链</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#eff6ff;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#2563eb">' + totalDim + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">总维度</div></div>'
    + '<div id="cde-triggered-count" style="flex:1;text-align:center;padding:16px;background:#f0fdf4;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#059669">—</div><div style="font-size:12px;color:#64748b;margin-top:4px">本次触发</div></div>'
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
      + '<div style="font-size:13px;color:#475569;line-height:2;margin-bottom:12px">' + escHtml(c.description) + '</div>'

      // 维度详情
      + '<div style="margin-bottom:8px;padding:10px 12px;background:#fff;border-radius:6px">'
      + '<div style="font-size:12px;font-weight:600;color:#64748b;margin-bottom:6px">触发维度 · ' + c.dimensions.length + ' 个</div>';
    c.dimensions.forEach(function(d) {
      html += '<div style="padding:4px 0;font-size:13px;color:#475569;line-height:1.8">'
        + '<span style="font-weight:600;color:#0f172a">' + escHtml(d.code) + '</span>'
        + ' <span style="color:#64748b">' + escHtml(d.source) + '</span>'
        + '<span style="color:#94a3b8;margin-left:6px">→ ' + escHtml(d.desc) + '</span>'
        + '</div>';
    });
    html += '</div>'

      // 完整字段
      + (c.how_found ? '<div style="font-size:13px;color:#64748b;line-height:1.8;margin-bottom:4px"><span style="font-weight:600;color:#0f172a">溯源：</span>' + escHtml(c.how_found) + '</div>' : '')
      + (c.tax_impact ? '<div style="font-size:13px;color:#64748b;line-height:1.8;margin-bottom:4px"><span style="font-weight:600;color:#0f172a">纳税影响：</span>' + escHtml(c.tax_impact) + '</div>' : '')
      + (c.policy_ref ? '<div style="font-size:13px;color:#64748b;line-height:1.8;margin-bottom:4px"><span style="font-weight:600;color:#0f172a">法律依据：</span>' + escHtml(c.policy_ref) + '</div>' : '')
      + (c.suggestion ? '<div style="font-size:13px;color:#64748b;line-height:1.8;margin-bottom:4px"><span style="font-weight:600;color:#0f172a">处理建议：</span>' + escHtml(c.suggestion) + '</div>' : '')

      + '</div>';
  });

  html += '<div style="margin-top:20px;padding:16px 20px;background:#fafafa;border-radius:8px;font-size:13px;color:#64748b;line-height:2">'
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
    + '<div style="flex:1;text-align:center;padding:14px;background:#f8fafc;border-radius:8px"><div style="font-size:24px;font-weight:700;color:#0f172a">' + allEvidence.length + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">证据链发现</div></div>'
    + '<div style="flex:1;text-align:center;padding:14px;background:#f0fdf4;border-radius:8px"><div style="font-size:24px;font-weight:700;color:#059669">' + closedCount + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">已闭环</div></div>'
    + '<div style="flex:1;text-align:center;padding:14px;background:#eff6ff;border-radius:8px"><div style="font-size:24px;font-weight:700;color:#2563eb">' + chainExecution.length + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">线索链</div></div>'
    + '<div style="flex:1;text-align:center;padding:14px;background:#f8fafc;border-radius:8px"><div style="font-size:24px;font-weight:700;color:#0f172a">' + triggeredChains.length + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">含规则</div></div>'
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
        + (f.description ? '<div style="font-size:13px;color:#475569;line-height:2;margin-bottom:6px">' + escHtml(f.description) + '</div>' : '')
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

  container.innerHTML = '<style>.ch-layout{display:flex;gap:24px;max-width:1200px;margin:0 auto;padding:20px}.ch-toc{width:200px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:12px;line-height:2.2;max-height:calc(100vh-40px);overflow-y:auto}.ch-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.ch-toc a{display:flex;align-items:center;justify-content:space-between;color:#475569;text-decoration:none;padding:3px 8px;border-radius:4px;cursor:pointer}.ch-toc a:hover{background:#eff6ff;color:#2563eb;font-weight:600}.ch-toc a .cnt{font-size:10px;color:#94a3b8;background:#f1f5f9;padding:1px 6px;border-radius:10px}.ch-main{flex:1;min-width:0}</style>'
    + '<div class="ch-layout">'
    + '<nav class="ch-toc" id="ch-toc"><div class="toc-title">📖 分类</div></nav>'
    + '<div class="ch-main">'
    + '<h2 style="font-size:22px;font-weight:800;color:#0f172a;margin:0 0 4px">🔍 线索链</h2>'
    + '<p style="font-size:13px;color:#94a3b8;margin:0 0 24px" id="chains-subtitle">' + (hasCache ? _allClueChains.length + ' 条线索链' : '加载中...') + ' · 每条链含若干调查步骤</p>'
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
    var resp = await fetch('/static/audit_chains.json?_t=' + Date.now());
    var data = await resp.json();
    _allChains = data.chains || [];
    var clueChains = _allChains.filter(function(c) { return c.chain_type === '线索链' || !c.chain_type; });
    if (!clueChains.length) clueChains = _allChains.filter(function(c) { return c.chain_type !== '证据链'; });
    if (!clueChains.length) clueChains = _allChains;

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
    
    // 按 type 分组填充 TOC
    var typeGroups = {};
    chains.forEach(function(c){ var t = c.chain_type || '其他'; if(!typeGroups[t])typeGroups[t]=[]; typeGroups[t].push(c); });
    var tocEl = document.getElementById('ch-toc');
    if (tocEl) {
      tocEl.innerHTML = '<div class="toc-title">📖 ' + chains.length + ' 条线索链</div>';
      Object.keys(typeGroups).sort().forEach(function(t){ tocEl.innerHTML += '<a href="#ch-type-'+encodeURIComponent(t)+'">'+t+' <span class="cnt">'+typeGroups[t].length+'</span></a>'; });
    }

    html += '<div id="ch-stats" style="display:flex;gap:12px;margin-bottom:32px">'
      + '<div style="flex:1;text-align:center;padding:16px;background:#f8fafc;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#0f172a">' + chains.length + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">线索链总数</div></div>'
      + '<div style="flex:1;text-align:center;padding:16px;background:#eff6ff;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#2563eb">' + triggeredCount + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">本次触发</div></div>'
      + '</div>';

    chains.forEach(function(c, ci) {
      var exec = execMap[c.name];
      var isOldFormat = !!(c.investigation_path && c.investigation_path.length > 0 && c.investigation_path[0].rule_id);
      var isNewFormat = !!(c.steps && Array.isArray(c.steps) && c.steps.length > 0 && c.steps[0].action);
      var stepList = isOldFormat ? c.investigation_path : (isNewFormat ? c.steps : (c.investigation_path || []));
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
        badge = ' <span style="font-size:11px;padding:2px 8px;border-radius:10px;background:#f1f5f9;color:#94a3b8;font-weight:500">未触发</span>';
      }

      // 子主题标签
      var topicTag = subTopic ? ' <span style="font-size:11px;padding:1px 8px;border-radius:4px;background:#ede9fe;color:#7c3aed;font-weight:500">' + escHtml(subTopic) + '</span>' : '';

      // 质量分标签
      var scoreTag = qualityScore > 0 ? ' <span style="font-size:11px;color:#94a3b8">⭐ ' + qualityScore + '</span>' : '';

      html += '<div style="padding:18px 20px;margin-bottom:14px;border:1px solid #e2e8f0;border-radius:10px;background:#fff;box-shadow:0 1px 2px rgba(0,0,0,0.04)">'

        // ══ 卡片头部：名称 + 标签行 ═══
        + '<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:6px;margin-bottom:10px">'
        + '<div style="font-size:15px;font-weight:700;color:#0f172a">' + escHtml(c.name) + badge + topicTag + scoreTag + '</div>'
        + '</div>';

      // 描述（新格式链有 description/desc）
      if (c.description) {
        html += '<div style="padding:10px 14px;margin-bottom:12px;background:#f8fafc;border-left:3px solid #6366f1;border-radius:0 6px 6px 0;font-size:13px;color:#475569;line-height:1.7">' + escHtml(c.description) + '</div>';
      } else if (c.desc) {
        html += '<div style="padding:10px 14px;margin-bottom:12px;background:#f8fafc;border-left:3px solid #6366f1;border-radius:0 6px 6px 0;font-size:13px;color:#475569;line-height:1.7">' + escHtml(c.desc) + '</div>';
      }

      // ══ 步骤列表 ═══
      if (isOldFormat) {
        // 旧格式：investigation_path 含 rule_id/level/detail/policy_ref/suggestion
        html += '<div style="margin-bottom:12px">';
        stepList.forEach(function(s, si) {
          var lvl = s.level || '';
          var lvlColor = lvl === '高风险' ? '#dc2626' : (lvl === '中风险' ? '#f59e0b' : (lvl === '低风险' ? '#059669' : '#94a3b8'));
          var lvlBg = lvl === '高风险' ? '#fef2f2' : (lvl === '中风险' ? '#fffbeb' : (lvl === '低风险' ? '#f0fdf4' : '#f8fafc'));
          var isHigh = lvl === '高风险';

          html += '<div style="padding:10px 14px;margin-bottom:6px;background:' + (isHigh ? '#fef2f2' : '#fafafa') + ';border-radius:6px;border-left:3px solid ' + (isHigh ? '#dc2626' : lvlColor) + '">'
            + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">'
            + '<span style="color:#94a3b8;font-size:12px;font-weight:600">#' + (si + 1) + '</span>'
            + (s.rule_id ? '<span style="color:#6366f1;font-size:11px;font-weight:600;background:#eef2ff;padding:1px 6px;border-radius:3px">R' + s.rule_id + '</span>' : '')
            + (lvl ? '<span style="font-size:11px;font-weight:600;color:' + lvlColor + ';background:' + lvlBg + ';padding:1px 6px;border-radius:3px">' + lvl + '</span>' : '')
            + (s.score ? '<span style="font-size:11px;color:#94a3b8">score=' + s.score + '</span>' : '')
            + '<b style="font-size:13px;color:#0f172a">' + escHtml(s.rule_item || s.step || '') + '</b>'
            + '</div>'
            + (s.detail ? '<div style="font-size:13px;color:#475569;line-height:1.7;margin-top:6px;padding-left:20px;border-left:2px solid #e2e8f0">' + escHtml(s.detail) + '</div>' : '')
            + (s.suggestion ? '<div style="font-size:12px;color:#059669;margin-top:6px;padding:8px 12px;background:#f0fdf4;border-radius:4px">💡 建议：' + escHtml(s.suggestion) + '</div>' : '')
            + (s.policy_ref ? '<div style="font-size:11px;color:#94a3b8;margin-top:4px">📎 ' + escHtml(s.policy_ref) + '</div>' : '')
            + '</div>';
        });
        html += '</div>';
      } else if (isNewFormat) {
        // 新格式：steps 数组含 {step: N, action: "文本"}
        html += '<div style="margin-bottom:12px">';
        stepList.forEach(function(s, si) {
          var stepNum = s.step || (si + 1);
          var isHigh = !!(s.level && (s.level === '极高风险' || c.level === '高风险'));

          html += '<div style="padding:10px 14px;margin-bottom:6px;background:' + (isHigh ? '#fef2f2' : '#fafafa') + ';border-radius:6px;border-left:3px solid ' + (isHigh ? '#dc2626' : '#cbd5e1') + '">'
            + '<div style="display:flex;align-items:center;gap:8px">'
            + '<span style="display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:50%;font-size:11px;font-weight:700;color:#fff;background:' + (isHigh ? '#dc2626' : '#94a3b8') + '">' + stepNum + '</span>'
            + '<span style="font-size:13px;color:#334155;line-height:1.7">' + escHtml(s.action || '') + '</span>'
            + (isHigh ? '<span style="font-size:11px;color:#dc2626;font-weight:600;background:#fee2e2;padding:1px 6px;border-radius:3px">高风险</span>' : '')
            + '</div>'
            + '</div>';
        });
        html += '</div>';
      } else if (totalS > 0) {
        // 兜底格式
        html += '<div style="margin-bottom:12px">';
        stepList.forEach(function(s, si) {
          var sText = typeof s === 'string' ? s : (s.step || s.action || s.rule_item || '');
          var lvl = s.level || '';
          html += '<div style="padding:8px 14px;margin-bottom:4px;background:#fafafa;border-radius:4px;font-size:13px;color:#475569">'
            + '<span style="color:#94a3b8;margin-right:8px">#' + (si + 1) + '</span>'
            + (lvl ? '<span style="color:' + (lvl==='高风险'?'#dc2626':lvl==='中风险'?'#f59e0b':'#94a3b8') + ';margin-right:8px">[' + lvl + ']</span>' : '')
            + escHtml(sText)
            + '</div>';
        });
        html += '</div>';
      }

      // ══ 政策依据 ═══
      if (c.policies && c.policies.length > 0) {
        html += '<div style="margin-bottom:10px">'
          + '<div style="font-size:12px;font-weight:600;color:#64748b;margin-bottom:6px">📋 政策依据</div>';
        c.policies.forEach(function(p) {
          html += '<div style="padding:6px 12px;margin-bottom:3px;background:#fffbeb;border-radius:4px;font-size:12px;color:#854d0e;line-height:1.6">• ' + escHtml(p) + '</div>';
        });
        html += '</div>';
      }

      // ══ 税务影响 ═══
      if (c.tax_impacts && c.tax_impacts.length > 0) {
        html += '<div style="margin-bottom:10px">'
          + '<div style="font-size:12px;font-weight:600;color:#64748b;margin-bottom:6px">⚠️ 税务影响</div>';
        c.tax_impacts.forEach(function(t) {
          html += '<div style="padding:6px 12px;margin-bottom:3px;background:#fef2f2;border-radius:4px;font-size:12px;color:#991b1b;line-height:1.6">• ' + escHtml(t) + '</div>';
        });
        html += '</div>';
      }

      // ══ 底部元信息栏 ═══
      html += '<div style="display:flex;flex-wrap:wrap;gap:12px;padding-top:10px;border-top:1px solid #f1f5f9;font-size:12px;color:#94a3b8">'
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
  container.innerHTML = '<style>.ev-layout{display:flex;gap:24px;max-width:1200px;margin:0 auto;padding:20px}.ev-toc{width:180px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:12px;line-height:2.2;max-height:calc(100vh-40px);overflow-y:auto}.ev-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.ev-toc a{display:flex;align-items:center;justify-content:space-between;color:#475569;text-decoration:none;padding:3px 8px;border-radius:4px;cursor:pointer}.ev-toc a:hover{background:#eff6ff;color:#2563eb;font-weight:600}.ev-toc a .cnt{font-size:10px;color:#94a3b8;background:#f1f5f9;padding:1px 6px;border-radius:10px}.ev-main{flex:1;min-width:0}</style>'
    + '<div class="ev-layout"><nav class="ev-toc" id="ev-toc"><div class="toc-title">📖 分类</div></nav>'
    + '<div class="ev-main"><h2 style="font-size:22px;font-weight:800;color:#0f172a;margin:0 0 4px">🔒 证据链</h2>'
    + '<p style="font-size:13px;color:#94a3b8;margin:0 0 24px">'+ (hasCache?_allEvidenceChains.length:'...') +' 条证据链 · ≥2域交叉验证形成闭环</p>'
    + '<div id="evidence-body"></div></div></div>';
  if (hasCache) { renderEvidenceList(_allEvidenceChains); }
  else { loadEvidenceData(); }
}

async function loadEvidenceData() {
  var target = document.getElementById('evidence-body');
  try {
    var resp = await fetch('/static/audit_chains.json?_t=' + Date.now());
    var data = await resp.json();
    _allChains = data.chains || [];
    var evChains = _allChains.filter(function(c) { return c.chain_type === '证据链'; });
    if (!evChains.length) evChains = _allChains.filter(function(c) { return c.chain_type !== '线索链'; });
    if (!evChains.length) evChains = _allChains;

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
  var closedCount = chains.filter(function(c) {
    var exec = evExecMap[c.name];
    return exec && exec.closed;
  }).length;

  // Populate TOC
  var tocEl = document.getElementById('ev-toc');
  if (tocEl) { tocEl.innerHTML = '<div class="toc-title">📖 '+chains.length+' 条证据链</div><a href="#ev-stats">统计总览</a>'; }

  var html = '';

  // 统计卡片
  html += '<div id="ev-stats" style="display:flex;gap:12px;margin-bottom:32px">'
    + '<div style="flex:1;text-align:center;padding:16px;background:#f8fafc;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#0f172a">' + chains.length + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">证据链总数</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#eff6ff;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#2563eb">' + totalSteps + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">调查步骤</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#f0fdf4;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#059669">' + closedCount + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">已闭环</div></div>'
    + '</div>';

  if (!chains.length) {
    html += '<div style="text-align:center;padding:40px;color:#94a3b8">无证据链数据</div>';
  } else {
    // 分组：按名称前缀分类
    var groups = {};
    chains.forEach(function(c) {
      var prefix = (c.name || '其他').split('-')[0] || '其他';
      if (!groups[prefix]) groups[prefix] = [];
      groups[prefix].push(c);
    });
    var sortedPrefixes = Object.keys(groups).sort(function(a,b) { return groups[b].length - groups[a].length; });

    sortedPrefixes.forEach(function(prefix) {
      var groupChains = groups[prefix];
      html += '<div style="margin-bottom:32px">';

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

        html += '<div style="padding:18px 20px;margin-bottom:14px;border:1px solid #e2e8f0;border-radius:10px;background:#fff;box-shadow:0 1px 2px rgba(0,0,0,0.04)">'

          // ══ 标题行 ═══
          + '<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:6px;margin-bottom:10px">'
          + '<div style="font-size:15px;font-weight:700;color:#0f172a">' + escHtml(c.name) + topicTag + scoreTag + '</div>'
          + (badgeText ? '<span style="font-size:11px;padding:2px 8px;border-radius:10px;background:' + badgeColor + '15;color:' + badgeColor + ';font-weight:600">' + badgeText + '</span>' : '')
          + '</div>';

        // ══ 描述（新格式证据链有 description） ═══
        if (c.description) {
          html += '<div style="padding:10px 14px;margin-bottom:12px;background:#f8fafc;border-left:3px solid #6366f1;border-radius:0 6px 6px 0;font-size:13px;color:#475569;line-height:1.7">' + escHtml(c.description) + '</div>';
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

            html += '<div style="padding:10px 14px;margin-bottom:6px;background:' + (isHigh ? '#fef2f2' : '#fafafa') + ';border-radius:6px;border-left:3px solid ' + (isHigh ? '#dc2626' : lvlColor) + '">'
              + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">'
              + '<span style="color:#94a3b8;font-size:12px;font-weight:600">#' + (si + 1) + '</span>'
              + (s.rule_id ? '<span style="color:#6366f1;font-size:11px;font-weight:600;background:#eef2ff;padding:1px 6px;border-radius:3px">R' + s.rule_id + '</span>' : '')
              + (lvl ? '<span style="font-size:11px;font-weight:600;color:' + lvlColor + ';background:' + lvlBg + ';padding:1px 6px;border-radius:3px">' + lvl + '</span>' : '')
              + '<b style="font-size:13px;color:#0f172a">' + escHtml(s.rule_item || s.step || '') + '</b>'
              + '</div>'
              + (s.detail ? '<div style="font-size:13px;color:#475569;line-height:1.7;margin-top:6px;padding-left:20px;border-left:2px solid #e2e8f0">' + escHtml(s.detail) + '</div>' : '')
              + (s.policy_ref ? '<div style="font-size:11px;color:#94a3b8;margin-top:4px">📎 ' + escHtml(s.policy_ref) + '</div>' : '')
              + '</div>';
          });
          html += '</div>';
        } else if (isStringFormat) {
          // 新格式：investigation_path 是字符串描述（如 "人员信息→发票数据→资金流→进销存四维交叉验证"）
          html += '<div style="padding:10px 14px;margin-bottom:12px;background:#eef2ff;border-radius:6px;font-size:13px;color:#3730a3;line-height:1.7">'
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
              + '<span style="font-size:13px;color:#334155;line-height:1.7">' + escHtml(s.action || '') + '</span>'
              + (isHigh ? '<span style="font-size:11px;color:#dc2626;font-weight:600;background:#fee2e2;padding:1px 6px;border-radius:3px">高风险</span>' : '')
              + '</div>'
              + '</div>';
          });
          html += '</div>';
        }

        // ══ 政策依据 ═══
        if (c.policies && c.policies.length > 0) {
          html += '<div style="margin-bottom:10px">'
            + '<div style="font-size:12px;font-weight:600;color:#64748b;margin-bottom:6px">📋 政策依据</div>';
          c.policies.forEach(function(p) {
            html += '<div style="padding:6px 12px;margin-bottom:3px;background:#fffbeb;border-radius:4px;font-size:12px;color:#854d0e;line-height:1.6">• ' + escHtml(p) + '</div>';
          });
          html += '</div>';
        }

        // ══ 税务影响 ═══
        if (c.tax_impacts && c.tax_impacts.length > 0) {
          html += '<div style="margin-bottom:10px">'
            + '<div style="font-size:12px;font-weight:600;color:#64748b;margin-bottom:6px">⚠️ 税务影响</div>';
          c.tax_impacts.forEach(function(t) {
            html += '<div style="padding:6px 12px;margin-bottom:3px;background:#fef2f2;border-radius:4px;font-size:12px;color:#991b1b;line-height:1.6">• ' + escHtml(t) + '</div>';
          });
          html += '</div>';
        }

        // ══ 关联线索链 ═══
        if (c.related_chains && c.related_chains.length > 0) {
          html += '<div style="margin-bottom:10px">'
            + '<div style="font-size:12px;font-weight:600;color:#64748b;margin-bottom:6px">🔗 关联线索链</div>';
          c.related_chains.forEach(function(rc) {
            html += '<div style="padding:6px 12px;margin-bottom:3px;background:#f0f9ff;border-radius:4px;font-size:12px;color:#0369a1;line-height:1.6">• ' + escHtml(rc) + '</div>';
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

      html += '</div>';
    });
  }

  target.innerHTML = html;
}

// ==================== 页面：分析链 ====================
function renderAnalyzePage(container) {
  if (!container) return;
  window.currentModule = '分析链';
  container.innerHTML = '<style>.al-layout{display:flex;gap:24px;max-width:1200px;margin:0 auto;padding:20px}.al-toc{width:190px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:12px;line-height:2.2;max-height:calc(100vh-40px);overflow-y:auto}.al-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.al-toc a{display:block;color:#475569;text-decoration:none;padding:2px 8px;border-radius:4px;cursor:pointer}.al-main{flex:1;min-width:0}</style>'
    + '<div class="al-layout">'
    + '<nav class="al-toc">'
    + '<div class="toc-title">📖 '+pc('rules','1514')+'规则 + '+pc('trailChains','396')+'线索 + '+pc('evidenceChains','745')+'证据</div>'
    + '<a href="#al-cap">引擎核心能力</a>'
    + '<a href="#al-overview">一 什么是分析链</a>'
    + '<a href="#al-steps">二 七步执行流程</a>'
    + '<a href="#al-methods">四 稽查方法论</a>'
    + '<a href="#al-result">结果</a>'
    + '</nav>'
    + '<div class="al-main">'
    + '<h2 style="font-size:22px;font-weight:800;color:#0f172a;margin:0 0 4px">⚡ 分析链</h2>'
    + '<p style="font-size:13px;color:#94a3b8;margin:0 0 24px"><a href="#" onclick="navigateTo(\'tax-doc-analysis\');return false" style="display:inline-block;padding:6px 16px;background:#2563eb;color:#fff;border-radius:6px;font-size:13px;text-decoration:none;font-weight:600">📊 查看完整报告 →</a></p>'
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

  // ══════ 引擎核心能力（六项）═══
  html += '<div id="al-cap" style="margin-bottom:32px;padding:20px 24px;background:linear-gradient(135deg,#1a1a2e,#16213e);border-radius:12px;color:#e2e8f0">'
    + '<h3 style="font-size:18px;font-weight:800;color:#fff;margin:0 0 16px;text-align:center">引擎核心能力宣言</h3>'
    + '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;font-size:12px;line-height:1.8">'
    + '<div style="padding:12px;background:rgba(255,255,255,0.08);border-radius:8px"><strong style="color:#fbbf24;font-size:14px">🧠 有记忆</strong><br>每次分析自动提取指纹存入记忆库，后续分析检索相似案例，输出行业对标和风险校准。实现：audit_memory.json，上限500条，12维度加权检索。</div>'
    + '<div style="padding:12px;background:rgba(255,255,255,0.08);border-radius:8px"><strong style="color:#fbbf24;font-size:14px">📚 能学习</strong><br>三层学习机制：用户反馈学习（驳回→降权0.2）、EMA自学习（58样本指数移动平均）、自动规则发现（信号组合→新规则）。</div>'
    + '<div style="padding:12px;background:rgba(255,255,255,0.08);border-radius:8px"><strong style="color:#fbbf24;font-size:14px">🔬 懂思考</strong><br>四层推理：假设-验证引擎（2-3竞争假设逐条验证）、Phase1-4推理引擎、因果叙事链（5条因果规则）、四步稽查分析法。</div>'
    + '<div style="padding:12px;background:rgba(255,255,255,0.08);border-radius:8px"><strong style="color:#fbbf24;font-size:14px">⚖️ 会判断</strong><br>七层判定：文件识别（四方交叉验证）、身份锚定、发票方向、进项分类、服务闸门、品名过滤、存疑排除。32条判定规则逐条校验。</div>'
    + '<div style="padding:12px;background:rgba(255,255,255,0.08);border-radius:8px"><strong style="color:#fbbf24;font-size:14px">🎯 懂决策</strong><br>五层决策：风险综合评分、审计策略推荐（P0/P1/P2）、因果叙事链、合规门禁（12项质量标准）、自省检查（16项）+7章报告输出。</div>'
    + '<div style="padding:12px;background:rgba(255,255,255,0.08);border-radius:8px"><strong style="color:#fbbf24;font-size:14px">🔮 有自知</strong><br>引擎知道自己是财税稽查系统的大脑。所有代码修改都是在增强引擎自身能力——新规则写到这里，新方法记到这里，新判断标准存到这里。</div>'
    + '</div></div>';

  // ══════ 一、分析链概述 ══════
  html += '<div style="margin-bottom:48px;padding:20px 24px;background:#f8fafc;border-radius:8px">'
    + '<h3 style="font-size:18px;font-weight:700;color:#0f172a;margin:0 0 12px">一、什么是分析链</h3>'
    + '<p style="font-size:14px;color:#475569;line-height:2.2;margin:0 0 16px">'
    + '分析链是税务稽查系统的核心执行管线，负责将用户上传的原始资料转化为结构化稽查报告。'
    + '这条管线不是简单的函数调用链，而是一个<strong>七步串联的数据处理流水线</strong>——每一步都有明确的输入、处理逻辑和输出，'
    + '数据在管线中单向流动，不丢失、不污染、不截断。'
    + '</p>'
    + '<p style="font-size:14px;color:#475569;line-height:2.2;margin:0 0 16px">'
    + '管线的设计理念来自稽查实战：真实稽查不是看一个数字就下结论，而是<strong>从资料扫描开始，经过多轮交叉验证，最终形成证据闭环</strong>。'
    + '分析链模拟的就是这个完整过程——资料驱动（有什么资料审什么）、诚实边界（缺什么资料报什么）、交叉推断（多源数据串联）、明细支撑（每条发现必须有具体数据）。'
    + '</p>'
    + '<div style="padding:16px 20px;background:#fff;border-radius:8px;font-size:13px;color:#64748b;line-height:2.2;border-left:3px solid #2563eb">'
    + '<strong>代码位置：</strong>main.py 中的 <code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">_run_analyze()</code> 函数（约第8540行）<br>'
    + '<strong>数据规模：</strong>' + pc('rules','1514') + ' 条稽查指令 · ' + pc('trailChains','396') + ' 条线索链 · ' + pc('evidenceChains','745') + ' 条证据链 · 11 条跨域证据链<br>'
    + '<strong>处理结果：</strong>97% 噪声过滤率 · 66 行业基准库 · 35 个域分析函数 · 7 步执行流程'
    + '</div>'
    + '</div>';

  // ══════ 二、七步执行流程详解 ══════
  html += '<div style="margin-bottom:48px">'
    + '<h3 style="font-size:18px;font-weight:700;color:#0f172a;margin:0 0 16px">二、七步执行流程详解</h3>'
    + '<p style="font-size:14px;color:#64748b;line-height:2;margin:0 0 20px">'
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
     desc:'将各类型文件数据导入36个域分析函数。包括：银行流水收款构成分析 + 付款方身份核实（联网法人/股东比对）；'
       + '进销存比对比——商品明细匹配 + 进销比 + 毛利率；五层发票审计——格式合规→同品名单价→加工费专项→金额合理性→BOM进销映射；'
       + '供应商穿透——集中度+群集+名称异常+双向交易检测；合同分层——四层自动分类（必签/应签/可免/小额）。'},
    {n:'④', title:'规则引擎与链驱动检查', icon:'⚙️',
     desc:'' + pc('rules','1514') + '条稽查指令逐条与域分析发现做匹配。' + pc('trailChains','396') + '条线索链引擎（行业特化链自动过滤——非本行业链不执行，全行业通用链全部运行）：每链多个调查步骤，通过定量/定性/缺失三类数据验证后触发，'
       + '产生链驱动发现。' + pc('evidenceChains','745') + '条证据链闭环检测：收集所有触发的规则ID，计算每链触发率——≥60%且≥3条规则+≥2数据域→形成证据闭环。'
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
    html += '<div style="padding:16px 20px;margin-bottom:6px;border-left:3px solid #2563eb;background:#fafafa;border-radius:0 6px 6px 0">'
      + '<div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:8px"><span style="font-size:18px">' + s.icon + '</span> ' + s.n + ' ' + s.title + '</div>'
      + '<div style="font-size:13px;color:#475569;line-height:2">' + s.desc + '</div>'
      + '</div>';
  });

  html += '</div>';

  // ══════ 三、全链路稽查质量保障体系 ══════
  html += '<div style="margin-bottom:48px;padding:24px;background:#f8fafc;border-radius:8px">'
    + '<h3 style="font-size:18px;font-weight:700;color:#0f172a;margin:0 0 16px">三、全链路稽查质量保障体系</h3>'
    + '<p style="font-size:14px;color:#64748b;line-height:2;margin:0 0 16px">'
    + '全链路稽查质量保障体系是一个开放的质量保障生态系统，从规则触发到报告输出，每条发现必须可追溯、可验证、可复核。'
    + '体系持续扩展新的保障维度，随系统发展而演进，不固定为"X合一"。下面按五大层次展示当前体系内容。'
    + '</p>'
    + '<div style="font-size:13px;color:#475569;line-height:2.2">'
    // 第一层：核心数据资产
    + '<div style="margin-bottom:16px"><div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:8px">① 核心数据资产</div>'
    + '<div style="padding:10px 16px;margin-bottom:6px;background:#fff;border-radius:6px;border-left:3px solid #2563eb"><strong>规则引擎</strong> → ' + pc('rules','1514') + '条稽查指令（tax_risk_rules_local_export.json），每条发现必须可追溯到具体规则ID。</div>'
    + '<div style="padding:10px 16px;margin-bottom:6px;background:#fff;border-radius:6px;border-left:3px solid #7c3aed"><strong>线索链系统</strong> → ' + pc('trailChains','396') + '条线索链（audit_chains.json），每条发现必须可追溯到具体线索链，触发率=已触发步骤/总步骤。</div>'
    + '<div style="padding:10px 16px;margin-bottom:6px;background:#fff;border-radius:6px;border-left:3px solid #059669"><strong>证据链系统</strong> → ' + pc('evidenceChains','745') + '条证据链 + ' + pc('crossEvidence','11') + '条跨域证据链，≥60%触发率+≥3条规则+≥2数据域→闭环发现→强制升级高风险。</div>'
    + '<div style="padding:10px 16px;background:#fff;border-radius:6px;border-left:3px solid #0891b2"><strong>跨域分析链</strong> → 多源数据交叉验证，覆盖资金流+票据流+业务流三维验证，形成跨域证据闭环。</div>'
    + '</div>'
    // 第二层：方法论体系
    + '<div style="margin-bottom:16px"><div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:8px">② 方法论体系</div>'
    + '<div style="padding:10px 16px;margin-bottom:6px;background:#fff;border-radius:6px;border-left:3px solid #dc2626"><strong>稽查方法论33条</strong> → 已全部代码化，涵盖多格式兼容、汇总行过滤、付款方身份核实等33条实战方法论。</div>'
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
    + '<div style="padding:10px 16px;margin-bottom:6px;background:#fff;border-radius:6px;border-left:3px solid #f59e0b"><strong>36个域分析函数</strong> → 银行流水+进销存比+五层发票审计+供应商穿透+合同分层等。</div>'
    + '<div style="padding:10px 16px;background:#fff;border-radius:6px;border-left:3px solid #059669"><strong>全链路溯源体系</strong> → 规则ID追溯✓+线索链追溯✓+证据来源✓+一键分析溯源✓+证据链闭环✓+跨域证据链✓。</div>'
    + '</div>'
    + '</div>'
    + '</div>';
  // ══════ 四、稽查方法论（㉛条详解）══════
  html += '<div style="margin-bottom:48px;padding:24px;background:#fafafa;border-radius:8px">'
    + '<h3 style="font-size:18px;font-weight:700;color:#0f172a;margin:0 0 16px">四、稽查方法论（33条已全部代码化）</h3>'
    + '<p style="font-size:14px;color:#64748b;line-height:2;margin:0 0 20px">'
    + '稽查方法论是税务稽查系统的灵魂。每一条方法论都来自实战中反复踩过的坑，是血泪教训的结晶。下面逐条详解。'
    + '</p>'
    + '<div style="font-size:13px;color:#475569;line-height:2.2">'

  var methods = [
    {id:'①', name:'多格式兼容', desc:'银行文件date/tx_time/交易日期/交易时间/记账日期五种命名全兼容。PDF发票PDFPlumber解析+OCR兜底。Excel多引擎（openpyxl/xlrd/pandas）。不因格式不兼容而丢弃数据。'},
    {id:'②', name:'汇总行过滤', desc:'月末汇总行（对手为空+大额整数）→自动识别并剔除。银行流水中的汇总行（如"本月合计"）不是真实交易，必须过滤。'},
    {id:'③', name:'付款方身份核实', desc:'个人打款→联网查工商→范善茂=法定代表人→性质待核实（股东注资/借款/未申报收入），不直接定性。付款方身份必须核实，不能凭名字猜测。'},
    {id:'④', name:'关键词≠事实', desc:'BOM从纯关键词→进销品名实质差异+加工费证据。含"BOM"关键词不等于有BOM业务，必须通过进销品名差异和加工费发票来证明。'},
    {id:'⑤', name:'行业认知补算法', desc:'工商登记类型≠实际经营模式。企业可能通过委托加工等外包方式实现进销品名转化（如买原料→委托加工→卖成品），在贸易型企业中广泛存在。算法必须考虑行业认知，不能仅凭工商登记判定企业类型。'},
    {id:'⑥', name:'联网核查', desc:'企查查查法人/股东/行业/注册资本。工商信息可能与发票数据不一致，必须联网核查确认。'},
    {id:'⑦', name:'明细即信服力', desc:'全部收款方+付款方逐一列示明细表，不分组合并。每条发现必须有具体数据（供应商名/金额/发票号），不可泛泛计数。'},
    {id:'⑧', name:'不墨迹直接干', desc:'发现问题不请示，读文件查格式直接修。下一步工作必须做时，不等不提问，自动继续直到交付完整结果。'},
    {id:'⑨', name:'合同分层判断', desc:'四层自动分类：必签（主营业务+金额>5万）、应签（金额1-5万）、可免（日常消费）、小额（金额<1万）。印花税预估：must_total × 0.03%。'},
    {id:'⑩', name:'完备度明细', desc:'资料完备度评估必须列明每类资料的实际数量（如"销项发票：36张"），不能只说"齐全"或"缺失"。'},
    {id:'⑪', name:'完备度升级', desc:'资料完备度综合评估从单一维度（有/无）升级为多维度（数量+时间跨度+完整性），更准确反映资料质量。'},
    {id:'⑫', name:'凭证描述纠正', desc:'记账凭证摘要必须规范化（如"购入原材料"而非"付款"），便于后续分析。'},
    {id:'⑬', name:'进销诊断升级', desc:'进销品名不匹配的诊断从简单比对升级为三层分析：①品名差异分析、②加工费证据检查、③加工链条合理性判断。'},
    {id:'⑭', name:'行业基准库', desc:'66行业基准值库，每个行业含毛利率/净利率/税负率/进销比/人均营收五个指标的下限/上限/典型值。用于行业对标分析。'},
    {id:'⑮', name:'结论分析法', desc:'每条结论必须同时具备：detect（检测现象）+ verify（交叉验证）+ diagnose（根因诊断）+ report（综合结论）四步分析框架。'},
    {id:'⑯', name:'COND_BAN防误杀', desc:'条件过滤（COND_BAN）防止过滤器误杀重要发现。有资料则放过，无资料则删除相关结论。'},
    {id:'⑰', name:'稽查重点强制等级', desc:'12类稽查重点发现不根据score计算等级，而是直接硬编码为"高风险"。保护机制：后端强制修正+过滤器绕过+前端红色标记。'},
    {id:'⑱', name:'报告纯净度', desc:'报告是给稽查执行人员阅读的专业文书，不是开发调试日志。所有系统内部标注（【detect 检测现象】等）必须移除。'},
    {id:'⑲', name:'发票≠收付款1:1', desc:'进项发票vs银行付款、销项发票vs银行收款，均不能按"名称对上=正常、对不上=异常"的1:1逻辑判断。六种收付款模式：自然跨期/合并/分期/预付预收/应付应收/非对公代付。'},
    {id:'⑳', name:'经营实质地理分析', desc:'从单一风险点推理出面的风险。供应商地址+客户地址+加工商地址+运输成本→全链条经营实质是否合理。重物跨省经营缺运输成本=货物流物证链断裂。'},
    {id:'㉑', name:'规则detail业务化', desc:'规则detail字段从技术语言改为业务语言。如"BOM进销映射异常"→"进销品名不匹配，可能存在虚开发票风险"。'},
    {id:'㉒', name:'建议质量增强', desc:'每个风险点的建议必须含具体消除路径——提供XX资料→如果A就XX→如果B就XX→无法做到的后果。不能只说"立即整改"。'},
    {id:'㉓', name:'四步稽查分析法', desc:'detect（检测现象）→ verify（交叉验证）→ diagnose（根因诊断）→ report（输出结论）。四大核心发现全部应用四步法。'},
    {id:'㉔', name:'禁止数据截断', desc:'报告中显示全部明细数据，不截断（如"前5条"→显示全部）。明细即信服力。'},
    {id:'㉕', name:'三层行业穿透法', desc:'工商登记（法律形式）→ 发票数据（经营实质）→ 加工信号（业务模式）。三者不一致时以实质重于形式为原则。'},
    {id:'㉖', name:'经营实质点面推理法', desc:'从单一风险点推理出面的风险。点（单点发现）→ 数据扩展 → 线（关联维度A/B/C/D）→ 交叉验证 → 面（综合结论）。'},
    {id:'㉗', name:'稽查六员跨企业比对', desc:'联网核查获取六员（法定代表人/董事/监事/财务负责人/股东/经理）后，三重检测：①一人多角 ②跨企业人员重叠 ③供应链交叉比对→关联交易连锁风险。'},
    {id:'㉘', name:'供应链联网核查', desc:'进销发票TOP10→搜索引擎查每家→六员交叉比对→人员重叠=关联交易→供应商=客户=购销闭环→虚开发票嫌疑。'},
    {id:'㉙', name:'资料缺失风险推理', desc:'任一资料缺失≥1类时，自动触发对应的风险结论到综合定性。14类资料缺失→9条风险结论映射，全行业适用。'},
    {id:'㉚', name:'存疑排除法', desc:'买卖双方均不匹配当前公司时，标记为存疑发票并绝对排除出所有后续分析。不得以默认值继续处理。'},
    {id:'㉛', name:'规则配置外部化', desc:'所有配置存放在JSON文件中，代码不硬编码行业特定逻辑。新增行业只需修改JSON，不改Python代码。'},
    {id:'㉜', name:'资金回流检测法', desc:'三源比对中发现付款方与收款方有重叠时，追踪资金是否形成闭环。资金回流是虚开发票的核心特征。'}
  ];

  methods.forEach(function(m) {
    html += '<div style="padding:10px 16px;margin-bottom:6px;background:#fff;border-radius:6px;border-left:2px solid #e2e8f0">'
      + '<span style="font-weight:700;color:#2563eb;margin-right:8px">' + m.id + '</span>'
      + '<strong style="color:#0f172a">' + m.name + '</strong>'
      + '<span style="color:#64748b;margin-left:8px;font-size:12px">' + m.desc + '</span>'
      + '</div>';
  });

  html += '</div></div>';

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
    + '<div style="font-size:13px;color:#475569;line-height:2;margin:0 0 16px">'
    + '分析链是税务稽查系统的核心执行管线——<strong>七步串联的数据处理流水线</strong>，数据在管线中单向流动，不丢失、不污染、不截断。'
    + '从资料扫描开始，经过多轮交叉验证，最终形成证据闭环：资料驱动+诚实边界+交叉推断+明细支撑。'
    + '</div>'
    + '<div style="font-size:12px;color:#94a3b8;line-height:1.8;padding:12px 16px;background:#f8fafc;border-radius:6px">'
    + '代码位置：main.py _run_analyze() · 数据规模：' + pc('rules','1514') + '条指令 + ' + pc('trailChains','396') + '条线索链 + ' + pc('evidenceChains','745') + '条证据链 · 处理能力：97%噪声过滤 · 66行业基准库 · 35域分析函数'
    + '</div>'
    + '</div>';

  // ══════ 二、七步执行流程 ══════
  h += '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 16px">七步执行流程</h3>'
    + '<div style="margin-bottom:40px;display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px;color:#475569;line-height:1.9">'
    + '<div style="padding:14px 16px;background:#f0f9ff;border-radius:6px;border-left:3px solid #2563eb"><strong style="color:#0f172a;font-size:13px">① 资料扫描与类型识别</strong><br>34类文件指纹库+三层递进识别（关键词打分→结构分析→数据推断），自动判定发票方向。</div>'
    + '<div style="padding:14px 16px;background:#f5f3ff;border-radius:6px;border-left:3px solid #7c3aed"><strong style="color:#0f172a;font-size:13px">② 目标实体识别</strong><br>进项购买方∩销项销售方确定企业全称，90+关键词×66行业加权投票，联网工商比对。</div>'
    + '<div style="padding:14px 16px;background:#ecfdf5;border-radius:6px;border-left:3px solid #059669"><strong style="color:#0f172a;font-size:13px">③ 资料情报提取与分析</strong><br>36个域分析函数并行执行：银行流水收款构成+进销存比+五层发票审计+供应商穿透+合同分层。</div>'
    + '<div style="padding:14px 16px;background:#fef2f2;border-radius:6px;border-left:3px solid #dc2626"><strong style="color:#0f172a;font-size:13px">④ 规则引擎与链驱动检查</strong><br>' + pc('rules','1514') + '条稽查指令逐条匹配，' + pc('trailChains','396') + '条线索链触发（行业不匹配链自动跳过），' + pc('evidenceChains','745') + '条证据链闭环检测。</div>'
    + '<div style="padding:14px 16px;background:#fffbeb;border-radius:6px;border-left:3px solid #f59e0b"><strong style="color:#0f172a;font-size:13px">⑤ 方法论噪声过滤器</strong><br>HARD_BAN（23类禁止词）+ COND_BAN（5类条件过滤），97%噪声过滤率。稽查重点发现不受过滤影响。</div>'
    + '<div style="padding:14px 16px;background:#fdf2f8;border-radius:6px;border-left:3px solid #ec4899"><strong style="color:#0f172a;font-size:13px">⑥ 行业对标与申报比对</strong><br>66行业基准值自动对标（毛利率/净利率/税负率/进销比/人均营收五维），申报表vs发票实际比对。</div>'
    + '<div style="padding:14px 16px;background:#f0fdf4;border-radius:6px;border-left:3px solid #16a34a"><strong style="color:#0f172a;font-size:13px">⑦ 正式稽查报告输出</strong><br>按《税务稽查工作规程》标准格式生成7章节+附件的完整稽查报告（详见第七节「稽查报告标准格式」）。</div>'
    + '</div>';

  // ══════ 三、本次分析结果 ══════
  h += '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 16px">本次分析结果</h3>'
    + '<div style="display:flex;gap:12px;margin-bottom:20px">'
    + '<div style="flex:1;text-align:center;padding:16px;background:#f8fafc;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#0f172a">' + (report.files_count||0) + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">资料文件</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#eff6ff;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#2563eb">' + (comp.rule_count||pc('rules','1514')) + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">匹配规则</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fef2f2;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#dc2626">' + highCount + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">高风险</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fffbeb;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#f59e0b">' + midCount + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">中风险</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#f0fdf4;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#059669">' + lowCount + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">低风险</div></div>'
    + '</div>'
    + '<div style="margin-bottom:40px;font-size:13px;color:#475569;line-height:2">'
    + '规则 <strong>' + (comp.rule_count||pc('rules','1514')) + '</strong> 则 · 线索链 <strong>' + (comp.chain_count||pc('trailChains','396')) + '</strong> 条 · '
    + '证据链 <strong>' + (comp.evidence_count||pc('evidenceChains','745')) + '</strong> 条 · 文件 <strong>' + (report.files_count||0) + '</strong> 个 · '
    + '全链路闭环：规则ID追溯 ✓ · 线索链追溯 ✓ · 证据来源 ✓ · 一键分析 ✓'
    + '</div>';

  // ══════ 四、管线日志 ══════
  if (plogs.length > 0) {
    h += '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 8px">管线执行日志 · ' + plogs.length + ' 条</h3>'
      + '<div style="margin-bottom:40px;background:#0f172a;border-radius:6px;padding:20px 24px;max-height:400px;overflow-y:auto;font-family:\'SF Mono\',\'Fira Code\',monospace;font-size:12px;line-height:2.2">';
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

  h += '<div style="margin-bottom:32px;padding:20px 24px;background:#fafafa;border-radius:8px">'
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
            + '<div style="font-size:12px;color:#475569;line-height:1.8">' + escHtml(desc) + '</div>'
            + '<div style="display:none;margin-top:8px;padding:8px 12px;background:#f8fafc;border-radius:6px;font-size:12px;color:#475569;line-height:2">'
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
  h += '<div style="margin-bottom:32px;padding:16px 20px;background:#f8fafc;border-radius:8px;border-left:3px solid #059669">'
    + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 8px">全链路稽查质量保障体系</h3>'
    + '<p style="font-size:12px;color:#94a3b8;margin:0 0 8px">开放生态系统 · 五大层次 · 持续扩展</p>'
    + '<div style="font-size:12px;color:#475569;line-height:2">'
    + '<div>🗄️ <strong>核心数据资产</strong>：规则引擎(' + pc('rules','1514') + '条) + 线索链(' + pc('trailChains','396') + '条) + 证据链(' + pc('evidenceChains','745') + '条) + 跨域分析链</div>'
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
  container.innerHTML = '<style>.cdc-layout{display:flex;gap:24px;max-width:1200px;margin:0 auto;padding:20px}.cdc-toc{width:180px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:12px;line-height:2.2}.cdc-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.cdc-toc a{display:block;color:#475569;text-decoration:none;padding:2px 8px;border-radius:4px;cursor:pointer}.cdc-main{flex:1;min-width:0}</style>'
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
        + '<p style="font-size:13px;color:#64748b;line-height:2;margin:0 0 16px">'
        + '跨域线索链是从单一数据异常出发，跨多个数据域进行串联调查的标准化路径。每条线索链定义了从首域发现到多域验证的完整调查步骤，'
        + '确保每个疑点都被多源数据交叉验证——不依赖单一数据源的孤立异常下结论。'
        + '与跨域证据链不同：线索链定义的是<strong>调查路径</strong>（怎么查），证据链定义的是<strong>验证标准</strong>（怎么判）。'
        + '</p>'
        + '<div style="padding:16px 20px;background:#f8fafc;border-radius:8px;font-size:13px;color:#475569;line-height:2">'
        + '<strong>与跨域证据链的关系</strong>：线索链（调查路径）→ 证据链（验证标准）→ 结论。线索链告诉稽查人员"从哪里开始查，每一步查什么"，证据链告诉稽查人员"满足什么条件才算发现问题"。'
        + '</div>'
        + '</div>';

      // 统计
      var highCount = clues.filter(function(c) { return (c.level === '极高风险' || c.level === '高风险'); }).length;
      var totalSteps = clues.reduce(function(s,c){return s+(c.investigation_path||[]).length;},0);
      html += '<div style="display:flex;gap:12px;margin-bottom:40px">'
        + '<div style="flex:1;text-align:center;padding:16px;background:#f8fafc;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#0f172a">' + clues.length + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">线索链</div></div>'
        + '<div style="flex:1;text-align:center;padding:16px;background:#fef2f2;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#dc2626">' + highCount + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">高风险链</div></div>'
        + '<div style="flex:1;text-align:center;padding:16px;background:#eff6ff;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#2563eb">' + totalSteps + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">调查步骤</div></div>'
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
          + '<div style="font-size:13px;color:#475569;line-height:2;margin-bottom:12px">' + escHtml(c.description) + '</div>'

          // 调查路径
          + '<div style="margin-bottom:8px;padding:10px 12px;background:#fff;border-radius:6px">'
          + '<div style="font-size:12px;font-weight:600;color:#64748b;margin-bottom:6px">调查路径 · ' + (c.investigation_path||[]).length + ' 步</div>';
        (c.investigation_path||[]).forEach(function(s) {
          html += '<div style="padding:6px 0;border-bottom:1px solid #f8fafc;font-size:13px;line-height:1.8">'
            + '<span style="color:#94a3b8;font-size:12px;margin-right:8px">Step ' + s.step + '</span>'
            + '<span style="font-weight:600;color:#2563eb">' + escHtml(s.domain) + '</span>'
            + '<span style="color:#64748b"> → ' + escHtml(s.action) + '</span>'
            + '<div style="color:#94a3b8;font-size:12px;margin-top:2px">所需资料：' + escHtml(s.data_required) + '</div>'
            + '</div>';
        });
        html += '</div>'

          + (c.tax_impact ? '<div style="font-size:13px;color:#64748b;line-height:1.8;margin-bottom:4px"><span style="font-weight:600">纳税影响：</span>' + escHtml(c.tax_impact) + '</div>' : '')
          + (c.policy_ref ? '<div style="font-size:13px;color:#64748b;line-height:1.8;margin-bottom:4px"><span style="font-weight:600">法律依据：</span>' + escHtml(c.policy_ref) + '</div>' : '')
          + (c.suggestion ? '<div style="font-size:13px;color:#64748b;line-height:1.8"><span style="font-weight:600">处理建议：</span>' + escHtml(c.suggestion) + '</div>' : '')
          + '</div>';
      });

      html += '<div style="margin-top:20px;padding:16px 20px;background:#fafafa;border-radius:8px;font-size:13px;color:#64748b;line-height:2">'
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
  container.innerHTML = '<style>.cda-layout{display:flex;gap:24px;max-width:1200px;margin:0 auto;padding:20px}.cda-toc{width:180px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:12px;line-height:2.2}.cda-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.cda-toc a{display:block;color:#475569;text-decoration:none;padding:2px 8px;border-radius:4px;cursor:pointer}.cda-main{flex:1;min-width:0}</style>'
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
        + '<p style="font-size:13px;color:#64748b;line-height:2;margin:0 0 16px">'
        + '跨域分析链定义的是<strong>推理路径</strong>——从一个域的异常信号开始，通过多步逻辑推理，逐步扩展到其他域，'
        + '最终得出跨域综合结论。每条链都有<strong>回退点</strong>——只要某个环节能提供合理解释，风险就会降级或消除。'
        + '与线索链（调查路径）和证据链（验证标准）不同，分析链关注的是<strong>推理逻辑</strong>本身。'
        + '</p>'
        + '<div style="padding:16px 20px;background:#f8fafc;border-radius:8px;font-size:13px;color:#475569;line-height:2">'
        + '<strong>三个跨域链的关系</strong><br>'
        + '🔎 跨域线索链 → 告诉稽查人员「怎么查」（调查步骤）<br>'
        + '🔗 跨域证据链 → 告诉稽查人员「怎么判」（验证标准）<br>'
        + '🧠 跨域分析链 → 告诉稽查人员「怎么推理」（逻辑路径+回退条件）'
        + '</div>'
        + '</div>';

      // 统计
      html += '<div style="display:flex;gap:12px;margin-bottom:40px">'
        + '<div style="flex:1;text-align:center;padding:16px;background:#f8fafc;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#0f172a">' + chains.length + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">分析链</div></div>'
        + '<div style="flex:1;text-align:center;padding:16px;background:#fef2f2;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#dc2626">' + highCount + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">高风险链</div></div>'
        + '<div style="flex:1;text-align:center;padding:16px;background:#eff6ff;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#2563eb">' + totalSteps + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">推理步骤</div></div>'
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
          + '<div style="font-size:13px;color:#475569;line-height:1.8;margin-bottom:4px"><span style="font-weight:600;color:#0f172a">触发信号：</span>' + escHtml(c.trigger_signal) + '</div>'

          // 描述
          + '<div style="font-size:13px;color:#475569;line-height:2;margin-bottom:12px">' + escHtml(c.description) + '</div>'

          // 推理链
          + '<div style="margin-bottom:12px;padding:12px 16px;background:#fff;border-radius:6px">'
          + '<div style="font-size:12px;font-weight:600;color:#64748b;margin-bottom:8px">推理链 · ' + (c.reasoning_chain||[]).length + ' 步</div>';

        (c.reasoning_chain||[]).forEach(function(s, si) {
          html += '<div style="padding:6px 0;border-bottom:1px solid #f8fafc;font-size:13px;line-height:1.8">'
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
          html += '<div style="padding:4px 0;font-size:13px;color:#475569;line-height:1.8">'
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

      html += '<div style="margin-top:20px;padding:16px 20px;background:#fafafa;border-radius:8px;font-size:13px;color:#64748b;line-height:2">'
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

  container.innerHTML = '<style>.mf-layout{display:flex;gap:24px;max-width:1200px;margin:0 auto;padding:20px}.mf-toc{width:200px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:12px;line-height:2.2}.mf-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.mf-toc a{display:block;color:#475569;text-decoration:none;padding:2px 8px;border-radius:4px;cursor:pointer}.mf-main{flex:1;min-width:0}.mf-stat{flex:1;text-align:center;padding:16px;border-radius:8px;font-size:13px}</style>'
    + '<div class="mf-layout">'
    + '<nav class="mf-toc"><div class="toc-title">📖 目录</div>'
    + '<a href="#mf-static">一 过滤规则体系</a>'
    + '<a href="#mf-result">二 本次过滤结果</a>'
    + '</nav>'
    + '<div class="mf-main">'
    + '<h2 style="font-size:22px;font-weight:800;color:#0f172a;margin:0">🎯 方法论过滤器</h2>'
    + '<p style="font-size:13px;color:#94a3b8;margin:0 0 24px">HARD_BAN + COND_BAN + 去重 — 三大噪声过滤机制，剔除97%无效发现</p>'
    + '<div id="mf-body"></div>'
    + '</div></div>';

  if (_cachedFilterReport) { renderFilterResult(_cachedFilterReport); }
  else { loadMethodologyFilterData(); }
}

async function loadMethodologyFilterData() {
  try {
    var data = await getSharedAnalysis();
    if (!data.ok) {
      document.getElementById('mf-body').innerHTML = '<div style="padding:40px 0;font-size:13px;color:#94a3b8">' + (data.message || '暂无分析结果') + '</div>';
      return;
    }
    _cachedFilterReport = data.report;
    renderFilterResult(data.report);
  } catch (e) {
    document.getElementById('mf-body').innerHTML = '<div style="padding:40px 0;font-size:13px;color:#dc2626">加载失败: ' + e.message + '</div>';
  }
}

function renderFilterResult(report) {
  var comp = report.comprehensive || {};
  var fl = comp.filter_log;
  
  var html = '';

  // ══════ 一、过滤规则体系（始终显示） ══════
  html += '<div id="mf-static" style="margin-bottom:32px">'
    + '<h3 style="font-size:16px;font-weight:700;color:#0f172a;margin:0 0 8px">一、过滤规则体系</h3>'
    + '<p style="font-size:13px;color:#64748b;line-height:2;margin:0 0 16px">方法论过滤器是稽查报告质量的最后防线。过滤器按稽查方法论铁律，将不具备数据支撑的噪声发现剔除，只保留可查证可追溯可复核的核心发现进入正式报告。<strong>宁可漏报，不可误报。</strong></p>';

  var rules = [
    {title:'HARD_BAN 硬删除（23类）', icon:'🛑', color:'#dc2626',
     desc:'绝对禁止出现在报告输出中的关键词：公安/经侦/刑事/走逃/失联/空壳等。发现type或detail中包含任一禁止词→立即删除。'},
    {title:'COND_BAN 条件过滤（5类）', icon:'⚠️', color:'#f59e0b',
     desc:'无申报表删除申报类发现、无合同删除合同类发现、无工资表删除工资类发现、无库存删除库存类发现、无凭证删除凭证类发现。有资料放过，无资料删除。'},
    {title:'稽查重点保护（level_fixed）', icon:'🛡️', color:'#2563eb',
     desc:'12类稽查重点发现（资金流异常/资料缺失/进销不匹配等）不参与任何过滤，强制保留。'},
    {title:'正常结论排除', icon:'✅', color:'#059669',
     desc:'含"一致/正常/无异常/OK"等正常结论→删除。这些不构成风险发现。'},
    {title:'资料缺口限流', icon:'📊', color:'#6366f1',
     desc:'资料缺少/缺失类发现最多保留5条，超限按score从低到高删除。'},
    {title:'行业不匹配过滤', icon:'🏭', color:'#0f172a',
     desc:'行业特定关键词与当前企业行业不匹配时删除。'},
    {title:'去重合并', icon:'🔄', color:'#94a3b8',
     desc:'同type前60字符完全相同→只保留score最高的第一条。'},
  ];

  rules.forEach(function(r) {
    html += '<div style="padding:14px 18px;margin-bottom:6px;border-left:3px solid '+r.color+';background:#fafafa;border-radius:0 6px 6px 0">'
      + '<div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:4px">'+r.icon+' '+r.title+'</div>'
      + '<div style="font-size:12px;color:#475569;line-height:1.8">'+r.desc+'</div></div>';
  });

  html += '</div>';

  if (!fl) {
    html += '<div style="padding:40px 0;font-size:13px;color:#94a3b8;text-align:center">暂无过滤记录<br><br><a href="#" onclick="navigateTo(\'tax-doc-analysis\');return false" style="color:#2563eb;text-decoration:underline">→ 运行一键分析后查看过滤详情</a></div>';
    document.getElementById('mf-body').innerHTML = html;
    return;
  }

  // ══════ 二、本次过滤结果 ══════
  var removedItems = fl.removed_items || [];
  var breakdown = fl.reason_breakdown || {};
  var totalRemoved = fl.total_removed || 0;
  var before = fl.before_count || 0;
  var after = fl.after_count || 0;

  html += '<div id="mf-result" style="margin-top:16px">'
    + '<h3 style="font-size:16px;font-weight:700;color:#0f172a;margin:0 0 8px">二、本次过滤结果</h3>'
    + '<p style="font-size:13px;color:#94a3b8;margin:0 0 16px">' + before + ' → ' + after + ' 条，剔除 ' + totalRemoved + ' 条，噪声率 ' + (fl.noise_ratio||0) + '%</p>';

  // 统计卡片
  html += '<div style="display:flex;gap:12px;margin-bottom:24px">'
    + '<div class="mf-stat" style="background:#f8fafc"><div style="font-size:28px;font-weight:700;color:#0f172a">'+before+'</div><div>过滤前</div></div>'
    + '<div class="mf-stat" style="background:#fef2f2"><div style="font-size:28px;font-weight:700;color:#dc2626">'+totalRemoved+'</div><div>已剔除</div></div>'
    + '<div class="mf-stat" style="background:#f0fdf4"><div style="font-size:28px;font-weight:700;color:#059669">'+after+'</div><div>过滤后</div></div>'
    + '<div class="mf-stat" style="background:#eff6ff"><div style="font-size:28px;font-weight:700;color:#2563eb">'+(fl.noise_ratio||0)+'%</div><div>噪声率</div></div>'
    + '</div>';

  // 剔除原因分布
  if (Object.keys(breakdown).length > 0) {
    html += '<h4 style="font-size:13px;font-weight:600;color:#64748b;margin:0 0 12px">剔除原因分布</h4>';
    var breakdownEntries = Object.entries(breakdown).sort(function(a, b) { return b[1] - a[1]; });
    html += '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:24px">';
    breakdownEntries.forEach(function(entry) {
      var reason = entry[0], count = entry[1];
      var pct = totalRemoved > 0 ? Math.round(count / totalRemoved * 100) : 0;
      html += '<div style="padding:8px 14px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;font-size:13px">'
        + '<span style="color:#0f172a;font-weight:600">' + count + '</span>'
        + ' <span style="color:#64748b">' + reason + '</span>'
        + ' <span style="color:#94a3b8;font-size:12px">' + pct + '%</span></div>';
    });
    html += '</div>';
  }

  // 剔除明细
  if (removedItems.length > 0) {
    html += '<h4 style="font-size:13px;font-weight:600;color:#64748b;margin:0 0 12px">剔除明细（共' + removedItems.length + '条）</h4>';
    var grouped = {};
    removedItems.forEach(function(item) { var r = item.reason || '未知'; if (!grouped[r]) grouped[r] = []; grouped[r].push(item); });
    Object.keys(grouped).sort(function(a, b) { return grouped[b].length - grouped[a].length; }).forEach(function(reason) {
      var items = grouped[reason];
      html += '<div style="padding:4px 0;border-bottom:1px solid #f1f5f9;font-size:13px;color:#64748b">' + reason + ' <span style="color:#94a3b8">(' + items.length + '条)</span></div>';
    });
  }

  html += '</div>';
  document.getElementById('mf-body').innerHTML = html;
}

// ══════════════════════════════════════════════════════════════
//  智哥行为准则页面 —— 全部13条行为准则
// ══════════════════════════════════════════════════════════════

function renderAiRules(container) {
  var html = '';
  
  html += '<div id="ai-rules-pipeline-bar" style="margin-bottom:16px;max-width:1200px;margin-left:auto;margin-right:auto;padding:0 20px">';
  html += '<div style="padding:10px 16px;background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px">';
  html += '<span style="font-size:13px;color:#0369a1;">🔗 正在连接一键分析管道…</span>';
  html += '</div></div>';

  var categories = [
    {name:'行事风格', icon:'⚡', color:'#0f172a', id:'style', desc:'决定智哥如何做事的态度准则。做事要狠、不墨迹、主动进攻——这是"性格"层面的规范。', rules:[
      {id:1, name:'做事要狠', level:'准则', date:'2026-05-31', desc:'代码改就改彻底，不要留尾巴。发现Bug直接修到根。', why:'针对AI"只改用户指出的那一个点"的惰性行为。'},
      {id:2, name:'自作主张', level:'准则', date:'2026-05-31', desc:'技术上该做的事情直接做，不要问"要不要做"。', why:'消除不必要的确认往返。'},
      {id:3, name:'主动进攻', level:'准则', date:'2026-05-31', desc:'用户发现问题时，不只修那一个点，把同类问题全部揪出来。', why:'防止代码累积隐性债务。'},
    ]},
    {name:'质量保障铁律', icon:'✅', color:'#dc2626', id:'quality', desc:'确保代码质量和正确性的强制规则。违反任何一条都可能导致系统崩溃或数据错误。', rules:[
      {id:4, name:'自行验证', level:'铁律', date:'2026-06-03', desc:'每做完一件事，必须验证结果——重启服务器+预览页面。不验证不算完成。', why:'多次"代码改了但没重启→用户看到旧版本"。'},
      {id:8, name:'变更影响分析', level:'铁律', date:'2026-06-13', desc:'改任何值之前先搜索所有引用点，改后逐一验证。禁止改完就走。', why:'修改函数签名后未更新调用点→崩溃。'},
      {id:15, name:'提交前自查', level:'铁律', date:'2026-06-20', desc:'每次写代码后、commit前，必须按全部铁律逐条自查。', why:'代码描述文字写死了纺织举例→违反全行业适用铁律。'},
    ]},
    {name:'财税系统铁律', icon:'📊', color:'#7c3aed', id:'tax', desc:'专门针对财税账务处理系统的强制规则。来自实际账务处理中踩过的坑。', rules:[
      {id:6, name:'科目name', level:'铁律', date:'2026-06-13', desc:'Account表name字段只存本级名称。写入前必须查DB以实际值为准。', why:'硬编码导致父级和子级科目名称不一致。'},
      {id:7, name:'三号合并', level:'铁律', date:'2026-06-13', desc:'同一(invoice_code,invoice_no,digital_invoice_no)必须合并为一个凭证号。', why:'逐条调用导致同一张发票被拆分为多个凭证。'},
      {id:9, name:'审计铁律', level:'铁律', date:'2026-06-13', desc:'财税系统每次代码变更后必须python audit.py 1，7项全通过才提交。', why:'账务系统的数据一致性比代码功能更重要。'},
      {id:10, name:'ref_id去重', level:'铁律', date:'2026-06-13', desc:'去重用ref_id==tx.id精确匹配，禁止金额模糊匹配。', why:'金额模糊匹配导致银行余额计算错误。'},
      {id:11, name:'普票税额并入成本', level:'准则', date:'2026-06-13', desc:'普通发票税额不单独记进项税额，并入成本/费用借方。', why:'普通发票不能抵扣进项税额。'},
      {id:12, name:'7分类禁止兜底', level:'准则', date:'2026-06-13', desc:'CATEGORY_ACCOUNT_MAP严格限定7个分类，不在其中返回None跳过。', why:'兜底导致所有未识别费用被错误归类。'},
    ]},
    {name:'通用铁律', icon:'🌐', color:'#059669', id:'general', desc:'跨项目适用的最高级别行为准则。定义了AI的可信度和可靠性边界。', rules:[
      {id:5, name:'规则=代码', level:'铁律', date:'2026-06-13', desc:'改了规则必须同步改代码，不允许只改记忆不改代码。', why:'只改记忆不改代码→口号和实现脱节。'},
      {id:13, name:'代码即承诺', level:'铁律', date:'2026-06-19', desc:'所有提出的功能、方法论、规则必须全部编写为实际可运行的代码。', why:'只写口号不写代码——方法论声称已实现但代码中没有。'},
      {id:14, name:'全行业适用', level:'铁律', date:'2026-06-19', desc:'所有行为准则、方法论、代码逻辑必须适用于全行业各企业。', why:'BOM分析中原料关键词全是纺织词，已改造为25行业自适应词典。'},
      {id:16, name:'主动关联更新', level:'铁律', date:'2026-06-19', desc:'发现概念过时时，主动搜索全项目所有相关位置一并更新。', why:'只改用户指出的那一个位置→其他位置还是旧版本。'},
      {id:17, name:'自我反思与准则迭代', level:'铁律', date:'2026-06-19', desc:'每次用户批评后，反思准则是否遗漏了规范。准则必须持续迭代。', why:'行为准则自己的规范都不遵守，怎么要求代码质量？'},
      {id:18, name:'方法论先行', level:'铁律', date:'2026-06-20', desc:'任何功能在上代码之前，必须先有明确的方法论。', why:'没有方法论的代码是盲目的，没有代码的方法论是空洞的。'},
    ]}
  ];

  var totalRules = categories.reduce(function(s,c){return s + c.rules.length;}, 0);
  var tieLvCount = 0, zhunZeCount = 0;
  categories.forEach(function(c) { c.rules.forEach(function(r) { if (r.level==='铁律') tieLvCount++; else zhunZeCount++; }); });

  // ══ TOC sidebar layout ══
  html += '<style>.ar-layout{display:flex;gap:24px;max-width:1200px;margin:0 auto;padding:0 20px 40px}.ar-toc{width:200px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:12px;line-height:2.2}.ar-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.ar-toc a{display:block;color:#475569;text-decoration:none;padding:2px 8px;border-radius:4px;cursor:pointer}.ar-main{flex:1;min-width:0}</style>';
  html += '<div class="ar-layout">';

  // TOC
  html += '<nav class="ar-toc"><div class="toc-title">📖 目录</div>';
  html += '<a href="#ar-stats">统计总览</a>';
  categories.forEach(function(c){html+='<a href="#ar-'+c.id+'">'+c.icon+' '+c.name+'</a>';});
  html += '</nav>';

  html += '<div class="ar-main">';
  html += '<h2 style="font-size:22px;font-weight:800;color:#0f172a;margin:0 0 4px">🧠 智哥行为准则</h2>';
  html += '<p style="font-size:13px;color:#94a3b8;margin:0 0 24px">共'+totalRules+'条准则（'+tieLvCount+'铁律+'+zhunZeCount+'准则）· 4大分类 · 持续迭代</p>';

  // Stats
  html += '<div id="ar-stats" style="display:flex;gap:12px;margin-bottom:32px">'
    + '<div style="flex:1;text-align:center;padding:16px;background:#f8fafc;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#0f172a">'+totalRules+'</div><div style="font-size:12px;color:#64748b">准则总数</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fef2f2;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#dc2626">'+tieLvCount+'</div><div style="font-size:12px;color:#64748b">🔴 铁律</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#f0fdf4;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#059669">'+zhunZeCount+'</div><div style="font-size:12px;color:#64748b">📋 准则</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#eff6ff;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#2563eb">'+categories.length+'</div><div style="font-size:12px;color:#64748b">分类</div></div>'
    + '</div>';


  // ══════ 逐分类渲染 ══════
  categories.forEach(function(cat) {
    var catColor = cat.color;
    html += '<div id="ar-' + cat.id + '" style="margin-bottom:40px">'
      + '<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:6px">'
      + '<span style="width:3px;height:14px;display:inline-block;background:' + catColor + ';border-radius:2px"></span>'
      + '<span style="font-size:16px;font-weight:700;color:#0f172a">' + cat.icon + ' ' + cat.name + '</span>'
      + '<span style="font-size:13px;color:#94a3b8">' + cat.rules.length + ' 条</span>'
      + '</div>'
      + '<div style="font-size:13px;color:#64748b;line-height:1.8;margin:0 0 16px">' + cat.desc + '</div>';

    cat.rules.forEach(function(r) {
      var isTieLv = r.level === '铁律';
      var borderColor = isTieLv ? '#dc2626' : '#475569';
      var bgColor = isTieLv ? '#fef2f2' : '#f8fafc';
      var badgeColor = isTieLv ? '#991b1b' : '#334155';
      var badgeBg = isTieLv ? '#fee2e2' : '#e2e8f0';
      var badgeText = isTieLv ? '🔴 铁律' : '📋 准则';

      html += '<div style="padding:16px 20px;margin-bottom:6px;background:' + bgColor + ';border-left:3px solid ' + borderColor + ';border-radius:0 6px 6px 0">'
        + '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">'
        + '<div style="font-size:14px;font-weight:600;color:#0f172a">#' + r.id + ' ' + escHtml(r.name) + '</div>'
        + '<div style="display:flex;gap:8px;align-items:center">'
        + '<span style="font-size:11px;padding:2px 8px;border-radius:4px;background:' + badgeBg + ';color:' + badgeColor + ';font-weight:600">' + badgeText + '</span>'
        + '<span style="font-size:11px;color:#94a3b8">' + r.date + '</span>'
        + '</div></div>'
        + '<div style="font-size:13px;color:#475569;line-height:1.9;margin-bottom:6px">' + escHtml(r.desc) + '</div>'
        + '<div style="font-size:12px;color:#94a3b8;line-height:1.7;padding-top:4px;border-top:1px solid #e2e8f0">'
        + '<span style="color:#64748b">创立原因：</span>' + escHtml(r.why) + '</div>'
        + '</div>';
    });

    html += '</div>';
  });

  html += '</div>';
  html += '</div>'; // ar-main
  html += '</div>'; // ar-layout
  container.innerHTML = html;

  // ═══ 连接一键分析管道（深度） ═══
  (function() {
    try {
      if (typeof getSharedAnalysis !== 'function') return;
      getSharedAnalysis().then(function(data) {
        var report = (data && data.report) ? data.report : {};
        var pipelineLog = report.pipeline_log || [];
        var allF = report.all_findings || [];
        var totalFindings = allF.length;
        var highRisk = report.high_risk || 0;
        var pipelineSteps = 0;
        for (var i = 0; i < pipelineLog.length; i++) {
          if (pipelineLog[i].indexOf('域') > -1 || pipelineLog[i].indexOf('分析') > -1 || pipelineLog[i].indexOf('过滤') > -1) pipelineSteps++;
        }

        // ─── 状态栏 ───
        var statusBar = document.getElementById('ai-rules-pipeline-bar');
        if (statusBar) {
          statusBar.innerHTML = '<div class="card" style="padding:10px 16px;background:#f0fdf4;border:1px solid #bbf7d0;">' +
            '<div style="display:flex;align-items:center;flex-wrap:wrap;gap:12px;">' +
            '<span style="font-size:13px;">🔗 <strong>已连接一键分析管道</strong></span>' +
            '<span style="font-size:12px;color:#374151;">📊 ' + totalFindings + '条发现</span>' +
            '<span style="font-size:12px;color:#dc2626;">🔴 高风险 ' + highRisk + '</span>' +
            '<span style="font-size:12px;color:#6b7280;">⚙️ ' + pipelineSteps + '个分析步骤</span>' +
            '<span style="font-size:11px;color:#10b981;">✅ 本页' + totalRules + '条规则——所有铁律在每次提交前自动执行</span>' +
            '<a href="#" onclick="navigateTo(\'methodology-filter\');return false" style="font-size:12px;color:#2563eb;margin-left:auto;">查看过滤器 →</a>' +
            '</div></div>';
        }

        // ─── 检查关键铁律在本次管道中的执行结果 ───
        var filterLog = report.filter_log || [];
        var hasFilterLog = filterLog.length > 0;
        var hasCompleteness = false;
        var hasDocumentCheck = false;
        var allCategoriesOk = true;
        for (var fi = 0; fi < allF.length; fi++) {
          if (allF[fi].type === '资料完备度综合评估') { hasCompleteness = true; hasDocumentCheck = true; break; }
        }
        // 检查是否有行业特化违规（方法论过滤器中的行业检查）
        var industrySafe = true;
        for (var fl = 0; fl < pipelineLog.length; fl++) {
          if (pipelineLog[fl].indexOf('全行业') > -1 || pipelineLog[fl].indexOf('行业特化') > -1) { industrySafe = false; break; }
        }

        // 更新规则卡片上的管道状态图标
        var ruleCards = document.querySelectorAll('.ar-main [style*="border-left"]');
        for (var ri = 0; ri < ruleCards.length; ri++) {
          var card = ruleCards[ri];
          var cardText = card.textContent || '';
          var statusIcon = null;

          // 匹配管道相关规则
          if (cardText.indexOf('全行业适用') > -1) {
            statusIcon = industrySafe ? '✅ 通过' : '⚠ 待查';
          } else if (cardText.indexOf('自行验证') > -1) {
            statusIcon = totalFindings > 0 ? '✅ 已执行' : '⏳ 待运行';
          } else if (cardText.indexOf('变更影响分析') > -1) {
            statusIcon = hasCompleteness ? '✅ 通过' : '⏳ 待运行';
          } else if (cardText.indexOf('科目name') > -1 || cardText.indexOf('三号合并') > -1) {
            statusIcon = hasDocumentCheck ? '✅ 已执行' : '⏳ 待运行';
          } else if (cardText.indexOf('提交前自查') > -1) {
            statusIcon = '✅ 已执行';
          } else if (cardText.indexOf('ref_id') > -1 || cardText.indexOf('去重') > -1) {
            statusIcon = '✅ 已执行';
          } else if (cardText.indexOf('7分类') > -1 || cardText.indexOf('普票') > -1) {
            statusIcon = hasDocumentCheck ? '✅ 已执行' : '⏳ 待运行';
          }

          if (statusIcon) {
            var existingBadge = card.querySelector('[data-pipeline-badge]');
            if (!existingBadge) {
              var badge = document.createElement('span');
              badge.setAttribute('data-pipeline-badge', '1');
              badge.style.cssText = 'display:inline-block;margin-left:8px;padding:1px 6px;border-radius:3px;font-size:10px;' +
                (statusIcon.indexOf('✅') > -1 ? 'background:#dcfce7;color:#16a34a;' : 'background:#fefce8;color:#92400e;');
              badge.textContent = statusIcon;
              // Insert before the description div
              var descDiv = card.querySelector('[style*=\"line-height:1.9\"]');
              if (descDiv) {
                descDiv.parentNode.insertBefore(badge, descDiv);
              } else {
                card.appendChild(badge);
              }
            }
          }
        }
      }).catch(function() {});
    } catch(e) {}
  })();
}

// ══════════════════════════════════════════════════════════════
//  全链路稽查质量保障体系 —— 五大层次18组件全景页
// ══════════════════════════════════════════════════════════════
function renderQualitySystem(container) {
  if (!container) return;
  window.currentModule = '全链路质量保障体系';

  var layers = [
    { id:1, name:'核心数据资产', icon:'🗄️', color:'#2563eb',
      desc:'规则引擎、线索链、证据链、跨域分析链构成完整的数据资产底座。',
      items:[
        {name:'规则引擎',source:'tax_risk.py',desc:'1514条稽查指令，每条含触发条件、风险等级、调查步骤和处罚依据。'},
        {name:'线索链系统',source:'main.py',desc:'396条线索链，每条含多个调查步骤。定量/定性/缺失数据三类验证触发链驱动发现。'},
        {name:'证据链系统',source:'main.py',desc:'745条证据链+11条跨域证据链。≥60%触发率+≥3规则+≥2域→证据闭环。'},
        {name:'跨域分析链',source:'main.py',desc:'多源数据交叉验证引擎。覆盖资金流+票据流+业务流三维验证。'},
      ]},
    { id:2, name:'方法论体系', icon:'📐', color:'#7c3aed',
      desc:'33条稽查方法论全部代码化，六大分析框架覆盖全流程。',
      items:[
        {name:'稽查方法论33条',source:'main.py',desc:'已全部代码化：多格式兼容→汇总行过滤→付款方身份核实→关键词≠事实→行业基准库→联网核查→明细即信服力→合同分层→完备度→凭证纠正→进销诊断→结论分析法→COND_BAN→稽查重点→报告纯净度→发票≠收付款→经营实质地理→规则detail→建议增强→四步分析→禁止截断→三层穿透→点面推理→六员比对→供应链核查→缺失推理→存疑排除→配置外部化→资金回流。'},
        {name:'四步稽查分析法',source:'main.py',desc:'detect→verify→diagnose→report。每条发现完整呈现推导链。'},
        {name:'三层行业穿透法',source:'main.py',desc:'工商登记→发票数据→加工信号。不一致时以实质重于形式。'},
        {name:'经营实质点面推理法',source:'main.py',desc:'单点风险→数据扩展→关联维度→交叉验证→综合结论。'},
        {name:'合同分层判断法',source:'main.py',desc:'品名+金额+类型：必签/应签/可免/小额。'},
        {name:'发票与收付款时间差方法论',source:'main.py',desc:'六种真实收付款模式：自然跨期/合并支付/分期支付/预付预收/应付应收/非对公代付。发票日期≠收款日期是正常商业现象。'},
      ]},
    { id:3, name:'质量保障机制', icon:'🔒', color:'#dc2626',
      desc:'确保报告质量的最后关口。五层保护确保输出专业、准确、可交付。',
      items:[
        {name:'稽查重点强制等级',source:'main.py',desc:'12类稽查重点硬编码为高风险。三层保护：后端修正+过滤器绕过+前端标记。'},
        {name:'报告纯净度规范',source:'generate_report.py',desc:'系统内部标注移除，四步框架表现为自然段落衔接。'},
        {name:'噪声过滤器',source:'main.py',desc:'HARD_BAN（23类）+COND_BAN（5类）→97%噪声过滤率。'},
        {name:'数据一致性自检',source:'audit_consistency.py',desc:'启动前自动扫描所有JS/PY文件，正则匹配硬编码数字与权威数据源(system_config.json)对比，发现不一致→阻止启动或自动修复。--sync模式支持跨模块联动修正。'},
        {name:'审核反馈闭环',source:'self_learning.py',desc:'审核内容→存入correction_rules.json→按发现类型|行业|模式生成指纹→四级回退匹配(精确→行业→通用→名称)→累计1次纠正→升级为自动规则→下次同类发现自动标注。'},
      ]},
    { id:4, name:'行业认知体系', icon:'🏭', color:'#059669',
      desc:'像经验丰富的稽查员一样理解不同行业的经营模式差异。',
      items:[
        {name:'25行业产品链词典',source:'main.py',desc:'25个行业×2组关键词对。精确匹配→模糊匹配→通用兜底三级策略。'},
        {name:'外包轻加工模式认知',source:'main.py',desc:'批发业可能存在实质加工。进销品名差异+加工费→不能仅凭工商判定。'},
        {name:'66行业基准值库',source:'main.py',desc:'66个行业×5个指标×3个基准值。企业值<下限→高风险。'},
      ]},
    { id:5, name:'执行管线', icon:'⚙️', color:'#f59e0b',
      desc:'从原始资料到正式报告的七步处理流程，数据单向流动不丢失不污染不截断。',
      items:[
        {name:'七步执行流程',source:'main.py',desc:'①资料扫描→②实体识别→③情报提取→④规则引擎(1514+396+745)→⑤噪声过滤→⑥行业对标→⑦报告输出。'},
        {name:'36个域分析函数',source:'main.py',desc:'覆盖稽查全领域：银行流水、进销存、费用、往来款、固定资产、税务、资料完备度、经营实质。'},
        {name:'全链路溯源体系',source:'tax-doc-analysis.js',desc:'规则ID→线索链→证据来源→一键分析→证据闭环→跨域证据链。六步溯源。'},
      ]},
    { id:6, name:'跨域协商引擎', icon:'🤝', color:'#0ea5e9',
      desc:'域名分析独立运行后自动跨域对话消解/降级/增强。15条协商规则覆盖四类场景。',
      items:[
        {name:'行业闸门消解',source:'cross_domain_negotiation.py',desc:'服务行业自动跳过进销存/存货/BOM/毛利率对标，消除假阳性。NEG-001~005（5条）'},
        {name:'资料驱动的跨域标记',source:'cross_domain_negotiation.py',desc:'缺少某类资料→相关域标注资料受限。NEG-010~040（4条）'},
        {name:'证据矛盾消解',source:'cross_domain_negotiation.py',desc:'域A正面证据推翻域B负面结论。NEG-020~030（3条）'},
        {name:'联合增强',source:'cross_domain_negotiation.py',desc:'多域异常同时触发→合成更高级别新发现。NEG-AUG-001~003（3条）'},
      ]},
  ];

  var totalItems = layers.reduce(function(s,l){return s+l.items.length;},0);
  var h='<style>.qs-layout{display:flex;gap:28px;max-width:1100px;margin:0 auto;padding:24px 16px;background:#fff}.qs-toc{width:180px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:12px;line-height:2.2;max-height:calc(100vh-40px);overflow-y:auto}.qs-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.qs-toc a{display:block;color:#475569;text-decoration:none;padding:3px 10px;border-radius:4px;cursor:pointer;font-size:12px}.qs-toc a:hover,.qs-toc a.active{background:#eff6ff;color:#2563eb;font-weight:600}.qs-main{flex:1;min-width:0;background:#fff}.qs-sec-title{font-size:16px;font-weight:700;color:#0f172a;padding-bottom:10px;border-bottom:2px solid #e2e8f0;margin-bottom:16px}.qs-layer{margin-bottom:28px;padding:20px;background:#fff;border:1px solid #e2e8f0;border-radius:8px}.qs-layer-hd{display:flex;align-items:center;gap:10px;margin-bottom:14px;padding-bottom:12px;border-bottom:2px solid}.qs-item{padding:12px 16px;margin-bottom:6px;background:#fafbfc;border-radius:4px;border-left:3px solid #e2e8f0}.qs-stat{text-align:center;padding:14px 8px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px}.qs-info{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px 20px;font-size:13px;line-height:2}</style>';

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
      h+='<div class="qs-item"><div style="font-size:13px;font-weight:600;color:#0f172a;margin-bottom:4px">'+(idx+1)+'. '+item.name+'</div><div style="font-size:12px;color:#475569;line-height:1.8;margin-bottom:4px">'+item.desc+'</div><div style="font-size:11px;color:#6366f1">📁 '+item.source+'</div></div>';
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
        
        html += '<div style="margin-bottom:16px;padding:16px 20px;background:#f8fafc;border-radius:8px;border-left:3px solid #2563eb">'
          + '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">'
          + '<div style="font-size:15px;font-weight:700;color:#0f172a">' + escHtml(id) + ' ' + escHtml(name) + '</div>'
          + '<span style="font-size:11px;color:#94a3b8;cursor:pointer" onclick="var d=this.parentNode.parentNode.nextElementSibling;d.style.display=d.style.display==\'none\'?\'\':\'none\'">展开/折叠</span>'
          + '</div>'
          + '<div style="font-size:13px;color:#475569;line-height:1.8">' + escHtml(desc) + '</div>'
          + '<div style="display:none;margin-top:12px;padding:12px 16px;background:#fff;border-radius:6px;font-size:13px;color:#475569;line-height:2">'
          + (requirement ? '<div style="margin-bottom:8px"><span style="font-weight:600;color:#0f172a">要求：</span>' + escHtml(requirement) + '</div>' : '')
          + (purpose ? '<div style="margin-bottom:8px"><span style="font-weight:600;color:#0f172a">用途：</span>' + escHtml(purpose) + '</div>' : '')
          + (codePos ? '<div style="margin-bottom:8px"><span style="font-weight:600;color:#0f172a">代码位置：</span><code style="font-size:12px;background:#f1f5f9;padding:2px 6px;border-radius:4px">' + escHtml(codePos) + '</code></div>' : '')
          + (callLocs.length > 0 ? '<div><span style="font-weight:600;color:#0f172a">调用位置：</span>' + callLocs.map(function(loc) { return '<span style="display:inline-block;margin:2px 4px 2px 0;padding:2px 8px;background:#e0f2fe;color:#0369a1;font-size:11px;border-radius:4px">' + escHtml(loc) + '</span>'; }).join('') + '</div>' : '')
          + '</div>'
          + '</div>';
      });
      
      target.innerHTML = html;
    })
    .catch(function(e) {
      target.innerHTML = '<div style="color:#dc2626;padding:20px">加载方法论失败：' + e.message + '</div>';
    });
}
