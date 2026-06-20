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
    _pipelineCounts = {rules:1505,trailChains:391,evidenceChains:740,totalChains:1131,crossEvidence:8,crossClues:8,crossAnalysis:8};
  }
  return _pipelineCounts;
}

// 快捷取值：pc('rules','1505') → 返回已加载数量或fallback
function pc(key, fallback) {
  return (_pipelineCounts && _pipelineCounts[key] != null) ? _pipelineCounts[key] : fallback;
}

// ==================== 页面1：文件解析（极简风） ====================
function renderFileParsingPage(container) {
  if (!container) return;
  window.currentModule = '文件解析';
  container.innerHTML = ''
    + '<div class="pipeline-page">'
    + '  <div style="margin-bottom:48px">'
    + '    <h2 style="font-size:24px;font-weight:700;color:#0f172a;margin:0 0 6px">文件解析</h2>'
    + '    <p style="font-size:14px;color:#94a3b8;margin:0">三层递进识别 · 34类文件指纹 · 关键词打分 · 结构分析 · 数据推断兜底</p>'
    + '  </div>'
    + '  <div id="fp-static"></div>'
    + '  <div id="fp-analysis-result"></div>'
    + '</div>';
  renderFileParsingStatic();
  if (_cachedFileParsingReport) {
    renderFileParsingResult(_cachedFileParsingReport);
  } else {
    loadFileParsingData();
  }
}

function renderFileParsingStatic() {
  var target = document.getElementById('fp-static');
  if (!target) return;

  var fps = fpFingerprints();
  var html = '';

  // ══════ 一、识别机制详解 ══════
  html += '<div style="margin-bottom:48px">'
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
    + '</div>';

  // ══════ 二、兼容策略 ══════
  html += '<div style="margin-bottom:48px;padding:20px 24px;background:#fafafa;border-radius:8px">'
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
  html += '<div style="margin-bottom:48px">'
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

function statLine(label, value, color) {
  return '<div style="text-align:center;padding:0 24px;border-right:1px solid #f1f5f9">'
    + '<div style="font-size:32px;font-weight:700;color:' + color + ';line-height:1.2">' + value + '</div>'
    + '<div style="font-size:12px;color:#94a3b8;margin-top:2px">' + label + '</div></div>';
}

async function loadFileParsingData() {
  var target = document.getElementById('fp-analysis-result');
  if (!target) return;
  var cid = typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1;
  try {
    var resp = await fetch('/api/tax-risk-docs/last-analysis?company_id=' + cid);
    var data = await resp.json();
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

  var html = ''
    + '<div style="height:1px;background:#f1f5f9;margin-bottom:40px"></div>'
    + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">解析结果</h3>'
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

  target.innerHTML = html;
}

// ==================== 页面2：域分析（详尽版） ====================
function renderDomainAnalysisPage(container) {
  if (!container) return;
  window.currentModule = '域分析';
  container.innerHTML = ''
    + '<div class="pipeline-page">'
    + '  <div style="margin-bottom:48px">'
    + '    <h2 style="font-size:24px;font-weight:700;color:#0f172a;margin:0 0 6px">域分析</h2>'
    + '    <p style="font-size:14px;color:#94a3b8;margin:0">35个域分析函数 · 跨域关联推理 · 多源证据链串联</p>'
    + '  </div>'
    + renderDomainAnalysisStatic()
    + '<div id="da-analysis-result"></div>'
    + '</div>';

  if (_cachedDomainReport) {
    renderDomainAnalysisResult(_cachedDomainReport);
  } else {
    loadDomainAnalysisData();
  }
}

function renderDomainAnalysisStatic() {
  var html = '';

  // ══════ 一、什么是域分析 ══════
  html += '<div style="margin-bottom:48px">'
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
  html += '<div style="margin-bottom:48px">'
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

  // ══════ 三、30个分析域 ══════
  html += '<div style="margin-bottom:48px">'
    + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">三、30个分析域</h3>'
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
    {cat:'资料完备度', color:'#2563eb', desc:'15类稽查必查资料逐一检测，合同需求四层自动分层。缺失资料→风险标记→无法支撑结论时标注资料缺口。', items:[
      {name:'资料完备度评估', fn:'_domain_document_completeness', line:'12798', desc:'15类稽查必查资料逐一检测 · 合同需求四层分层（必签/应签/可免/小额）'},
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
    {cat:'行业对标与规则', color:'#6366f1', desc:'66行业基准库对标，' + pc('rules','1505') + '条规则全覆盖验证，审计基础检查。', items:[
      {name:'行业对标分析', fn:'_domain_industry_benchmark', line:'14475', desc:'66个行业基准——毛利率/税负率/进销比/人均营收/费用率五维对标'},
      {name:'规则全覆盖验证', fn:'_domain_rule_coverage', line:'15114', desc:'' + pc('rules','1505') + '条规则逐条检查 · 数据不足→资料缺口 · 不作无依据结论'},
      {name:'跨域关联推理', fn:'_domain_cross_domain_reasoning', line:'13490', desc:'单点→多域印证→8条跨域证据链 · A域+B域+C域异常→闭环'},
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
    + '<strong>行业对标+规则引擎</strong>（校验层）→ 将企业数据与66行业基准对比，与' + pc('rules','1505') + '条规则逐一匹配。<br>'
    + '<strong>跨域关联推理</strong>（顶层）→ 将以上所有发现串联为8条跨域证据链，形成最终稽查结论。'
    + '</div>'
    + '</div>';

  return html;
}

async function loadDomainAnalysisData() {
  var target = document.getElementById('da-analysis-result');
  if (!target) return;
  var cid = typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1;
  try {
    var resp = await fetch('/api/tax-risk-docs/last-analysis?company_id=' + cid);
    var data = await resp.json();
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
  var highTotal = allF.filter(function(f) { return f.level === '高风险'; }).length;
  var midTotal = allF.filter(function(f) { return f.level === '中风险'; }).length;

  var html = ''
    + '<div style="height:1px;background:#f1f5f9;margin-bottom:40px"></div>'
    + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">域分析结果</h3>'
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
          var lvlColor = f.level === '高风险' ? '#dc2626' : (f.level === '中风险' ? '#f59e0b' : '#22c55e');
          var lvlBg = f.level === '高风险' ? '#fef2f2' : (f.level === '中风险' ? '#fffbeb' : '#f0fdf4');
          html += '<div style="padding:10px 12px;margin-bottom:6px;background:' + lvlBg + ';border-radius:6px;border-left:3px solid ' + lvlColor + '">'
            + '<div style="font-size:13px;font-weight:600;color:#0f172a;margin-bottom:4px">' + escHtml(f.type || '') + '</div>'
            + '<div style="font-size:12px;color:#475569;line-height:1.8;margin-bottom:4px">' + escHtml((f.detail || '').substring(0, 300)) + '</div>'
            + '<div style="display:flex;gap:8px;align-items:center;font-size:11px;color:#94a3b8">'
            + '<span style="color:' + lvlColor + ';font-weight:600">' + (f.level || '') + '</span>'
            + '<span>score:' + (f.score || '-') + '</span>'
            + (f.rule_id ? '<span>规则:' + f.rule_id + '</span>' : '')
            + '</div>'
            + '</div>';
        });
        html += '</div>';
      }

      html += '</div>';
    });
  }

  target.innerHTML = html;
}

// ==================== 页面3：跨域证据链 ====================
function renderCrossDomainEvidencePage(container) {
  if (!container) return;
  window.currentModule = '跨域证据链';

  var hasCache = window._allCrossChains && window._allCrossChains.length > 0;

  container.innerHTML = '<div class="pipeline-page">'
    + '<div style="margin-bottom:48px">'
    + '<h2 style="font-size:24px;font-weight:700;color:#0f172a;margin:0 0 6px">跨域证据链</h2>'
    + '<p style="font-size:14px;color:#94a3b8;margin:0">' + (hasCache ? window._allCrossChains.length : '...') + ' 条证据链 · 多源数据交叉验证 · ≥2个维度同时命中才形成有效证据链</p>'
    + '</div>'
    + '<div id="cde-static"></div>'
    + '<div id="cde-dynamic"></div>'
    + '</div>';

  if (hasCache) {
    renderCrossDomainStaticContent(window._allCrossChains);
    loadCrossDomainDynamic();
  } else {
    loadCrossDomainStatic();
    loadCrossDomainDynamic();
  }
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
  var highCount = chains.filter(function(c) { return c.level === '高风险'; }).length;
  var totalDim = chains.reduce(function(s, c) { return s + c.dimensions.length; }, 0);
  var totalMinEvidence = chains.reduce(function(s, c) { return s + c.min_evidence; }, 0);

  var html = '';

  // ══════ 一、跨域证据链概述 ══════
  html += '<div style="margin-bottom:40px">'
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
    var levelColor = c.level === '高风险' ? '#dc2626' : '#f59e0b';
    var levelBg = c.level === '高风险' ? '#fef2f2' : '#fffbeb';

    html += '<div id="cde-chain-' + ci + '" style="padding:20px 24px;margin-bottom:12px;background:' + levelBg + ';border-left:3px solid ' + levelColor + ';border-radius:0 8px 8px 0">'

      // 标题
      + '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">'
      + '<div style="font-size:15px;font-weight:700;color:#0f172a">' + _escStatic(c.name) + '</div>'
      + '<div style="display:flex;gap:8px;align-items:center">'
      + '<span style="font-size:11px;padding:2px 8px;border-radius:4px;background:' + levelColor + '15;color:' + levelColor + ';font-weight:600">' + _escStatic(c.level) + '</span>'
      + '<span style="font-size:11px;color:#94a3b8">' + _escStatic(c.sub_topic) + '</span>'
      + '<span style="font-size:11px;color:#94a3b8">需≥' + c.min_evidence + '维</span>'
      + '<span id="cde-triggered-' + ci + '"></span>'
      + '</div>'
      + '</div>'

      // 描述
      + '<div style="font-size:13px;color:#475569;line-height:2;margin-bottom:12px">' + _escStatic(c.description) + '</div>'

      // 维度详情
      + '<div style="margin-bottom:8px;padding:10px 12px;background:#fff;border-radius:6px">'
      + '<div style="font-size:12px;font-weight:600;color:#64748b;margin-bottom:6px">触发维度 · ' + c.dimensions.length + ' 个</div>';
    c.dimensions.forEach(function(d) {
      html += '<div style="padding:4px 0;font-size:13px;color:#475569;line-height:1.8">'
        + '<span style="font-weight:600;color:#0f172a">' + _escStatic(d.code) + '</span>'
        + ' <span style="color:#64748b">' + _escStatic(d.source) + '</span>'
        + '<span style="color:#94a3b8;margin-left:6px">→ ' + _escStatic(d.desc) + '</span>'
        + '</div>';
    });
    html += '</div>'

      // 完整字段
      + (c.how_found ? '<div style="font-size:13px;color:#64748b;line-height:1.8;margin-bottom:4px"><span style="font-weight:600;color:#0f172a">溯源：</span>' + _escStatic(c.how_found) + '</div>' : '')
      + (c.tax_impact ? '<div style="font-size:13px;color:#64748b;line-height:1.8;margin-bottom:4px"><span style="font-weight:600;color:#0f172a">纳税影响：</span>' + _escStatic(c.tax_impact) + '</div>' : '')
      + (c.policy_ref ? '<div style="font-size:13px;color:#64748b;line-height:1.8;margin-bottom:4px"><span style="font-weight:600;color:#0f172a">法律依据：</span>' + _escStatic(c.policy_ref) + '</div>' : '')
      + (c.suggestion ? '<div style="font-size:13px;color:#64748b;line-height:1.8;margin-bottom:4px"><span style="font-weight:600;color:#0f172a">处理建议：</span>' + _escStatic(c.suggestion) + '</div>' : '')

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

  var cid = typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1;
  fetch('/api/tax-risk-docs/last-analysis?company_id=' + cid)
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

  var evidenceFindings = allF.filter(function(f) {
    var t = f.type || '';
    return /证据链|隐匿收入|虚开发票|无实质经营|会计基础|资金链|利润现金流|发票异常|全链条经营实质/.test(t);
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
      var lvlColor = f.level === '高风险' ? '#dc2626' : (f.level === '中风险' ? '#f59e0b' : '#059669');
      var lvlBg = f.level === '高风险' ? '#fef2f2' : (f.level === '中风险' ? '#fffbeb' : '#f0fdf4');
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

  container.innerHTML = '<div class="pipeline-page">'
    + '<div>'
    + '<h2 style="font-size:24px;font-weight:700;color:#0f172a;margin:0 0 6px">线索链列表</h2>'
    + '<p style="font-size:14px;color:#94a3b8;margin:0">稽查调查路径，每条链含若干调查步骤，触发率=已触发步骤/总步骤</p>'
    + '</div>'
    + '<div style="display:flex;gap:12px;align-items:center;margin-bottom:24px;padding-bottom:16px;border-bottom:1px solid #f1f5f9;margin-top:24px">'
    + '<span style="font-size:13px;color:#94a3b8"><strong id="chain-header-count">' + (hasCache ? _allClueChains.length : '...') + '</strong> 条线索链</span>'
    + '</div>'
    + '<div id="chains-body"></div></div>';

  if (hasCache) {
    renderChainsList(_allClueChains);
  } else {
    loadChainsData();
  }
}

async function loadChainsData() {
  var target = document.getElementById('chains-body');
  try {
    var resp = await fetch('/static/audit_chains.json?_t=' + Date.now());
    var data = await resp.json();
    _allChains = data.chains || [];
    var clueChains = _allChains.filter(function(c) { return c.chain_type === '线索链' || !c.chain_type; });
    if (!clueChains.length) clueChains = _allChains.slice(0, pc('trailChains', 391));

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
    var cid = typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1;
    var resp = await fetch('/api/tax-risk-docs/last-analysis?company_id=' + cid);
    var data = await resp.json();
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

  var filtered = chains; // 无筛选，直接全部展示

  var execMap = {};
  if (_chainDynamic && _chainDynamic.chain_execution) {
    _chainDynamic.chain_execution.forEach(function(ce) { execMap[ce.chain_name] = ce; });
  }
  var hasDynamic = Object.keys(execMap).length > 0;

  var html = '';
  if (!filtered.length) {
    html = '<div style="text-align:center;padding:40px;color:#94a3b8">无匹配线索链</div>';
  } else {
    filtered.forEach(function(c, ci) {
      var exec = execMap[c.name];
      var triggeredSteps = exec ? exec.triggered_steps : 0;
      var totalSteps = exec ? exec.total_steps : (c.steps ? c.steps.length : (c.total_steps || 0));
      var ratio = exec ? exec.triggered_ratio : 0;

      var badge = '';
      if (exec && exec.triggered_steps > 0) {
        badge = ' <span style="color:' + (ratio >= 60 ? '#dc2626' : '#059669') + ';font-size:13px;font-weight:600">' + triggeredSteps + '/' + totalSteps + ' (' + ratio + '%)</span>';
      }

      html += '<div style="padding:14px 0;border-bottom:1px solid #f1f5f9">'
        + '<div style="font-size:15px;font-weight:600;color:#0f172a;margin-bottom:6px">' + escHtml(c.name) + badge + '</div>'
        + '<div style="font-size:13px;color:#64748b;line-height:1.8">';

      (c.investigation_path||[]).forEach(function(s, idx) {
        var levelTag = s.level==='高风险' ? '<span style="color:#dc2626">[高]</span>' : (s.level==='中风险' ? '<span style="color:#f59e0b">[中]</span>' : '<span style="color:#94a3b8">[低]</span>');
        html += (idx > 0 ? ' → ' : '') + levelTag + ' ' + escHtml(s.step||s.rule_item||'');
      });

      html += '</div></div>';
    });
  }

  target.innerHTML = html;

  var hc = document.getElementById('chain-header-count');
  if (hc) hc.textContent = chains.length + (hasDynamic && _chainDynamic && _chainDynamic.triggered_count ? ' (' + _chainDynamic.triggered_count + '触发)' : '');
}

function filterChainsList() {
  if (_allClueChains.length) renderChainsList(_allClueChains, []);
}

// ==================== 页面：证据链 ====================
function renderEvidencePage(container) {
  if (!container) return;
  window.currentModule = '证据链';

  var hasCache = _allEvidenceChains && _allEvidenceChains.length > 0;

  container.innerHTML = '<div class="pipeline-page">'
    + '<div style="margin-bottom:48px">'
    + '<h2 style="font-size:24px;font-weight:700;color:#0f172a;margin:0 0 6px">证据链列表</h2>'
    + '<p style="font-size:14px;color:#94a3b8;margin:0">' + (hasCache ? _allEvidenceChains.length : '...') + ' 条证据链 · 含规则ID+处罚依据 · 需≥2域交叉验证形成闭环</p>'
    + '</div>'
    + '<div id="evidence-body"></div></div>';

  if (hasCache) {
    renderEvidenceList(_allEvidenceChains);
  } else {
    loadEvidenceData();
  }
}

async function loadEvidenceData() {
  var target = document.getElementById('evidence-body');
  try {
    var resp = await fetch('/static/audit_chains.json?_t=' + Date.now());
    var data = await resp.json();
    _allChains = data.chains || [];
    var evChains = _allChains.filter(function(c) { return c.chain_type === '证据链'; });
    if (!evChains.length) evChains = _allChains.slice(pc('trailChains', 391), pc('trailChains', 391) + pc('evidenceChains', 740));

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

  var totalSteps = chains.reduce(function(s, c) { return s + (c.investigation_path || []).length; }, 0);
  var closedCount = Object.values(evExecMap).filter(function(e) { return e.closed; }).length;

  var html = '';

  // 统计卡片
  html += '<div style="display:flex;gap:12px;margin-bottom:40px">'
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
      html += '<div style="margin-bottom:32px">'
        + '<div style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px 0;padding:8px 0;border-bottom:1px solid #e2e8f0">' + escHtml(prefix) + ' <span style="font-size:13px;font-weight:400;color:#94a3b8">' + groupChains.length + ' 条</span></div>';

      groupChains.forEach(function(c) {
        var evExec = evExecMap[c.name];
        var closed = evExec && evExec.closed;
        var ratio = evExec ? evExec.ratio : 0;
        var badgeText = evExec ? (closed ? '已闭环 ' + ratio + '%' : '未闭环 ' + ratio + '%') : '';
        var badgeColor = closed ? '#059669' : '#f59e0b';

        html += '<div style="padding:16px 20px;margin-bottom:8px;border:1px solid #f1f5f9;border-radius:8px">'
          // 标题行
          + '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">'
          + '<div style="font-size:14px;font-weight:600;color:#0f172a">' + escHtml(c.name) + '</div>'
          + (badgeText ? '<span style="font-size:11px;padding:2px 8px;border-radius:4px;background:' + badgeColor + '15;color:' + badgeColor + ';font-weight:600">' + badgeText + '</span>' : '')
          + '</div>'

          // 调查步骤
          + '<div style="margin-bottom:8px">';
        (c.investigation_path || []).forEach(function(s, si) {
          var levelTag = s.level === '高风险' ? '<span style="color:#dc2626;font-weight:600">高风险</span>' : (s.level === '中风险' ? '<span style="color:#f59e0b;font-weight:600">中风险</span>' : (s.level ? '<span style="color:#94a3b8">' + s.level + '</span>' : ''));
          html += '<div style="padding:8px 12px;margin-bottom:4px;background:#fafafa;border-radius:4px;font-size:13px;line-height:1.8">'
            + '<span style="color:#94a3b8;font-size:12px;margin-right:8px">#' + (si + 1) + '</span>'
            + (s.rule_id ? '<span style="color:#6366f1;font-size:11px;margin-right:6px">R' + s.rule_id + '</span>' : '')
            + (s.level ? '<span style="margin-right:6px">' + levelTag + '</span>' : '')
            + '<b style="color:#0f172a">' + escHtml(s.rule_item || s.step || '') + '</b>'
            + (s.detail ? '<div style="color:#64748b;margin-top:4px">' + escHtml(s.detail) + '</div>' : '')
            + (s.policy_ref ? '<div style="color:#94a3b8;font-size:12px;margin-top:4px">依据：' + escHtml(s.policy_ref) + '</div>' : '')
            + '</div>';
        });
        html += '</div>'

          // 底栏
          + '<div style="display:flex;gap:16px;font-size:12px;color:#94a3b8;padding-top:8px;border-top:1px solid #f1f5f9">'
          + '<span>步骤 ' + (c.investigation_path || []).length + ' 条</span>'
          + '<span>覆盖规则 ' + (c.covered_rule_count || (c.investigation_path || []).length) + ' 条</span>'
          + (c.related_chain_count > 0 ? '<span>关联链 ' + c.related_chain_count + ' 条</span>' : '')
          + (c.quality_score ? '<span>质量 ' + c.quality_score + ' 分</span>' : '')
          + '</div>'

          + '</div>';
      });

      html += '</div>';
    });
  }

  target.innerHTML = html;
  _allEvidenceChains = chains;
}

// ==================== 页面：分析链 ====================
function renderAnalyzePage(container) {
  if (!container) return;
  window.currentModule = '分析链';
  container.innerHTML = '<div class="pipeline-page">'
    + '<div style="margin-bottom:48px">'
    + '<h2 style="font-size:24px;font-weight:700;color:#0f172a;margin:0 0 6px">分析链</h2>'
    + '<p style="font-size:14px;color:#94a3b8;margin:0">' + pc('rules','1505') + '规则 + ' + pc('trailChains','391') + '线索链 + ' + pc('evidenceChains','740') + '证据链 → 方法论过滤器 → 正式稽查报告</p>'
    + '</div>'
    + '<div id="analyze-body"></div>'
    + '</div>';
  loadAnalyzeOverview();
}

async function loadAnalyzeOverview() {
  var target = document.getElementById('analyze-body');

  if (_cachedAnalyzeReport) {
    renderAnalyzeResult(_cachedAnalyzeReport);
    return;
  }

  var cid = typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1;
  try {
    var resp = await fetch('/api/tax-risk-docs/last-analysis?company_id=' + cid);
    var data = await resp.json();
    if (data.ok && data.report) {
      _cachedAnalyzeReport = data.report;
      renderAnalyzeResult(data.report);
      return;
    }
  } catch (e) {}

  // 兜底：无分析数据时显示完整静态说明
  var html = '';

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
    + '<strong>数据规模：</strong>' + pc('rules','1505') + ' 条稽查指令 · ' + pc('trailChains','391') + ' 条线索链 · ' + pc('evidenceChains','740') + ' 条证据链 · 8 条跨域证据链<br>'
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
     desc:'将各类型文件数据导入35个域分析函数。包括：银行流水收款构成分析 + 付款方身份核实（联网法人/股东比对）；'
       + '进销存比对比——商品明细匹配 + 进销比 + 毛利率；五层发票审计——格式合规→同品名单价→加工费专项→金额合理性→BOM进销映射；'
       + '供应商穿透——集中度+群集+名称异常+双向交易检测；合同分层——四层自动分类（必签/应签/可免/小额）。'},
    {n:'④', title:'规则引擎与链驱动检查', icon:'⚙️',
     desc:'' + pc('rules','1505') + '条稽查指令逐条与域分析发现做匹配。' + pc('trailChains','391') + '条线索链引擎：每链多个调查步骤，通过定量/定性/缺失三类数据验证后触发，'
       + '产生链驱动发现。' + pc('evidenceChains','740') + '条证据链闭环检测：收集所有触发的规则ID，计算每链触发率——≥60%且≥3条规则+≥2数据域→形成证据闭环。'
       + '234条证据链闭环触发→强制升级为高风险。链驱动引擎产出线索发现和闭环发现两类新发现，补充到总发现池。'},
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
    + '<div style="padding:10px 16px;margin-bottom:6px;background:#fff;border-radius:6px;border-left:3px solid #2563eb"><strong>规则引擎</strong> → ' + pc('rules','1505') + '条稽查指令（tax_risk_rules_local_export.json），每条发现必须可追溯到具体规则ID。</div>'
    + '<div style="padding:10px 16px;margin-bottom:6px;background:#fff;border-radius:6px;border-left:3px solid #7c3aed"><strong>线索链系统</strong> → ' + pc('trailChains','391') + '条线索链（audit_chains.json），每条发现必须可追溯到具体线索链，触发率=已触发步骤/总步骤。</div>'
    + '<div style="padding:10px 16px;margin-bottom:6px;background:#fff;border-radius:6px;border-left:3px solid #059669"><strong>证据链系统</strong> → ' + pc('evidenceChains','740') + '条证据链 + 8条跨域证据链，≥60%触发率+≥3条规则+≥2数据域→闭环发现→强制升级高风险。</div>'
    + '<div style="padding:10px 16px;background:#fff;border-radius:6px;border-left:3px solid #0891b2"><strong>跨域分析链</strong> → 多源数据交叉验证，覆盖资金流+票据流+业务流三维验证，形成跨域证据闭环。</div>'
    + '</div>'
    // 第二层：方法论体系
    + '<div style="margin-bottom:16px"><div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:8px">② 方法论体系</div>'
    + '<div style="padding:10px 16px;margin-bottom:6px;background:#fff;border-radius:6px;border-left:3px solid #dc2626"><strong>稽查方法论㉖条</strong> → 已全部代码化，涵盖多格式兼容、汇总行过滤、付款方身份核实等26条实战方法论。</div>'
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
    + '<div style="padding:10px 16px;margin-bottom:6px;background:#fff;border-radius:6px;border-left:3px solid #f59e0b"><strong>35个域分析函数</strong> → 银行流水+进销存比+五层发票审计+供应商穿透+合同分层等。</div>'
    + '<div style="padding:10px 16px;background:#fff;border-radius:6px;border-left:3px solid #059669"><strong>全链路溯源体系</strong> → 规则ID追溯✓+线索链追溯✓+证据来源✓+一键分析溯源✓+证据链闭环✓+跨域证据链✓。</div>'
    + '</div>'
    + '</div>'
    + '</div>';
  // ══════ 四、稽查方法论（㉖条详解）══════
  html += '<div style="margin-bottom:48px;padding:24px;background:#fafafa;border-radius:8px">'
    + '<h3 style="font-size:18px;font-weight:700;color:#0f172a;margin:0 0 16px">四、稽查方法论（㉖条已全部代码化）</h3>'
    + '<p style="font-size:14px;color:#64748b;line-height:2;margin:0 0 20px">'
    + '稽查方法论是税务稽查系统的灵魂。每一条方法论都来自实战中反复踩过的坑，是血泪教训的结晶。下面逐条详解。'
    + '</p>'
    + '<div style="font-size:13px;color:#475569;line-height:2.2">'

  var methods = [
    {id:'①', name:'多格式兼容', desc:'银行文件date/tx_time/交易日期/交易时间/记账日期五种命名全兼容。PDF发票PDFPlumber解析+OCR兜底。Excel多引擎（openpyxl/xlrd/pandas）。不因格式不兼容而丢弃数据。'},
    {id:'②', name:'汇总行过滤', desc:'月末汇总行（对手为空+大额整数）→自动识别并剔除。银行流水中的汇总行（如"本月合计"）不是真实交易，必须过滤。'},
    {id:'③', name:'付款方身份核实', desc:'个人打款→联网查工商→范善茂=法定代表人→性质待核实（股东注资/借款/未申报收入），不直接定性。付款方身份必须核实，不能凭名字猜测。'},
    {id:'④', name:'关键词≠事实', desc:'BOM从纯关键词→进销品名实质差异+加工费证据。含"BOM"关键词不等于有BOM业务，必须通过进销品名差异和加工费发票来证明。'},
    {id:'⑤', name:'行业认知补算法', desc:'工商批发业≠无加工。外包轻加工模式（买坯布→委托染整厂加工→卖成品布）在批发业中广泛存在。算法必须考虑行业认知，不能仅凭工商登记判定企业类型。'},
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
    {id:'㉖', name:'经营实质点面推理法', desc:'从单一风险点推理出面的风险。点（单点发现）→ 数据扩展 → 线（关联维度A/B/C/D）→ 交叉验证 → 面（综合结论）。'}
  ];

  methods.forEach(function(m) {
    html += '<div style="padding:10px 16px;margin-bottom:6px;background:#fff;border-radius:6px;border-left:2px solid #e2e8f0">'
      + '<span style="font-weight:700;color:#2563eb;margin-right:8px">' + m.id + '</span>'
      + '<strong style="color:#0f172a">' + m.name + '</strong>'
      + '<span style="color:#64748b;margin-left:8px;font-size:12px">' + m.desc + '</span>'
      + '</div>';
  });

  html += '</div></div>';

}

function renderAnalyzeResult(report) {
  var target = document.getElementById('analyze-body');
  if (!target) return;
  var allF = report.all_findings || [];
  var comp = report.comprehensive || {};
  var plogs = report.pipeline_log || [];
  var highCount = allF.filter(function(f){return f.level==='高风险'}).length;
  var midCount = allF.filter(function(f){return f.level==='中风险'}).length;
  var lowCount = allF.length - highCount - midCount;

  var h = '';

  // ══════ 一、执行概览 ══════
  h += '<div style="margin-bottom:40px">'
    + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">一、执行概览</h3>'
    + '<div style="display:flex;gap:12px;margin-bottom:20px">'
    + '<div style="flex:1;text-align:center;padding:16px;background:#f8fafc;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#0f172a">' + (report.files_count||0) + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">资料文件</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#eff6ff;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#2563eb">' + (comp.rule_count||pc('rules','1505')) + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">匹配规则</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fef2f2;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#dc2626">' + highCount + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">高风险</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fffbeb;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#f59e0b">' + midCount + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">中风险</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#f0fdf4;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#059669">' + lowCount + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">低风险</div></div>'
    + '</div>'
    + '<div style="font-size:13px;color:#475569;line-height:2">'
    + '规则 <strong>' + (comp.rule_count||pc('rules','1505')) + '</strong> 则 · 线索链 <strong>' + (comp.chain_count||pc('trailChains','391')) + '</strong> 条 · '
    + '证据链 <strong>' + (comp.evidence_count||pc('evidenceChains','740')) + '</strong> 条 · 文件 <strong>' + (report.files_count||0) + '</strong> 个 · '
    + '全链路闭环：规则ID追溯 ✓ · 线索链追溯 ✓ · 证据来源 ✓ · 一键分析 ✓'
    + '</div>'
    + '</div>';

  // ══════ 二、管线日志 ══════
  if (plogs.length > 0) {
    h += '<div style="margin-bottom:40px">'
      + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">二、管线执行日志 · ' + plogs.length + ' 条</h3>'
      + '<div style="background:#0f172a;border-radius:6px;padding:20px 24px;max-height:500px;overflow-y:auto;font-family:\'SF Mono\',\'Fira Code\',monospace;font-size:12px;line-height:2.2">';
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

  // ══════ 三、稽查方法论 ══════
  h += '<div style="margin-bottom:32px;padding:20px 24px;background:#fafafa;border-radius:8px">'
    + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 12px">三、稽查方法论（㉖条已全部代码化）</h3>'
    + '<div style="font-size:13px;color:#475569;line-height:2.2;display:grid;grid-template-columns:1fr 1fr;gap:6px 24px">'
    + '<div>① 多格式兼容 · ② 汇总行过滤</div><div>③ 付款方身份核实 · ④ 关键词≠事实</div>'
    + '<div>⑤ 行业认知补算法 · ⑥ 联网核查 ✅</div><div>⑦ 明细即信服力 · ⑧ 不墨迹直接干</div>'
    + '<div>⑨ 合同分层判断 · ⑩ 完备度明细</div><div>⑪ 完备度升级 · ⑫ 凭证描述纠正</div>'
    + '<div>⑬ 进销诊断升级 · ⑭ 行业基准库</div><div>⑮ 结论分析法 · ⑯ COND_BAN防误杀</div>'
    + '<div>⑰ 稽查重点强制等级 · ⑱ 报告纯净度</div><div>⑲ 发票≠收付款1:1 · ⑳ 经营实质地理分析</div>'
    + '<div>㉑ 规则detail业务化 · ㉒ 建议质量增强</div><div>㉓ 四步稽查分析法 · ㉔ 禁止数据截断</div>'
    + '<div>㉕ 三层行业穿透法</div><div>㉖ 经营实质点面推理法</div>'
    + '</div>'
    + '</div>';

  target.innerHTML = h;
}


// ==================== 工具函数 ====================
function _escStatic(s) { if (!s) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function escHtml(s) {
  if (!s) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function toggleDomainDetail(idx) {
  var el = document.getElementById('dd-' + idx);
  if (!el) return;
  el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

// ==================== 跨域线索链页面 ====================
function renderCrossDomainCluesPage(container) {
  if (!container) return;
  container.innerHTML = '<div class="pipeline-page">'
    + '<div style="margin-bottom:48px">'
    + '<h2 style="font-size:24px;font-weight:700;color:#0f172a;margin:0 0 6px">跨域线索链</h2>'
    + '<p style="font-size:14px;color:#94a3b8;margin:0">多域串联调查路径 · ≥2个数据域触发 · 从单点发现到跨域调查</p>'
    + '</div>'
    + '<div id="cdc-body"></div>'
    + '</div>';
  loadCrossDomainClues();
}

function loadCrossDomainClues() {
  var target = document.getElementById('cdc-body');
  fetch('/static/cross_domain_clues.json?_t=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(clues) {
      var html = '';

      // ══════ 一、概述 ══════
      html += '<div style="margin-bottom:40px">'
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
      var highCount = clues.filter(function(c) { return c.level === '高风险'; }).length;
      var totalSteps = clues.reduce(function(s,c){return s+(c.investigation_path||[]).length;},0);
      html += '<div style="display:flex;gap:12px;margin-bottom:40px">'
        + '<div style="flex:1;text-align:center;padding:16px;background:#f8fafc;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#0f172a">' + clues.length + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">线索链</div></div>'
        + '<div style="flex:1;text-align:center;padding:16px;background:#fef2f2;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#dc2626">' + highCount + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">高风险链</div></div>'
        + '<div style="flex:1;text-align:center;padding:16px;background:#eff6ff;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#2563eb">' + totalSteps + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">调查步骤</div></div>'
        + '</div>';

      // ══════ 二、线索链定义 ══════
      html += '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">二、跨域线索链定义</h3>';

      clues.forEach(function(c) {
        var levelColor = c.level === '高风险' ? '#dc2626' : '#f59e0b';
        var levelBg = c.level === '高风险' ? '#fef2f2' : '#fffbeb';

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
    })
    .catch(function() {
      if (target) target.innerHTML = '<div style="padding:40px 0;font-size:13px;color:#94a3b8">跨域线索链加载失败</div>';
    });
}

// ==================== 跨域分析链页面 ====================
function renderCrossDomainAnalysisPage(container) {
  if (!container) return;
  container.innerHTML = '<div class="pipeline-page">'
    + '<div style="margin-bottom:48px">'
    + '<h2 style="font-size:24px;font-weight:700;color:#0f172a;margin:0 0 6px">跨域分析链</h2>'
    + '<p style="font-size:14px;color:#94a3b8;margin:0">点→面推理路径 · 从单域异常到多域结论 · 每步可回退验证</p>'
    + '</div>'
    + '<div id="cda-body"></div>'
    + '</div>';
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
      html += '<div style="margin-bottom:40px">'
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
      html += '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">二、跨域分析链定义</h3>';

      chains.forEach(function(c) {
        var levelColor = c.level === '高风险' ? '#dc2626' : '#f59e0b';
        var levelBg = c.level === '高风险' ? '#fef2f2' : '#fffbeb';

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
    })
    .catch(function() {
      if (target) target.innerHTML = '<div style="padding:40px 0;font-size:13px;color:#94a3b8">跨域分析链加载失败</div>';
    });
}

// ==================== 页面4：方法论过滤器 ====================
function renderMethodologyFilterPage(container) {
  if (!container) return;
  window.currentModule = '方法论过滤器';

  container.innerHTML = '<div class="pipeline-page">'
    + '<div style="margin-bottom:48px">'
    + '<h2 style="font-size:24px;font-weight:700;color:#0f172a;margin:0 0 6px">方法论过滤器</h2>'
    + '<p style="font-size:14px;color:#94a3b8;margin:0">HARD_BAN + COND_BAN + 去重 —— 三大噪声过滤机制，剔除97%无效发现，确保报告纯净度</p>'
    + '</div>'
    + '<div id="mf-body"></div>'
    + '</div>';

  if (_cachedFilterReport) {
    renderFilterResult(_cachedFilterReport);
  } else {
    loadMethodologyFilterData();
  }
}

async function loadMethodologyFilterData() {
  var cid = typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1;
  try {
    var resp = await fetch('/api/tax-risk-docs/last-analysis?company_id=' + cid);
    var data = await resp.json();
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
  if (!fl) {
    document.getElementById('mf-body').innerHTML = '<div style="padding:40px 0;font-size:13px;color:#94a3b8">暂无过滤记录（需重新运行一键分析）</div>';
    return;
  }

  var removedItems = fl.removed_items || [];
  var breakdown = fl.reason_breakdown || {};
  var totalRemoved = fl.total_removed || 0;
  var before = fl.before_count || 0;
  var after = fl.after_count || 0;

  var html = '';

  // ══════ 一、方法论过滤器概述 ══════
  html += '<div style="margin-bottom:40px">'
    + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">一、什么是方法论过滤器</h3>'
    + '<p style="font-size:13px;color:#64748b;line-height:2;margin:0 0 16px">'
    + '方法论过滤器是稽查报告质量的最后一道防线。规则引擎和链驱动引擎产出的大量发现（通常1600+条）中，'
    + '绝大多数是系统内部的技术性发现或资料不足无法验证的推测性结论。过滤器按照稽查方法论铁律，'
    + '将不具备数据支撑的噪声发现剔除，只保留可查证、可追溯、可复核的核心发现进入正式报告。'
    + '</p>'
    + '<div style="padding:16px 20px;background:#f8fafc;border-radius:8px;font-size:13px;color:#475569;line-height:2">'
    + '<strong>核心原则</strong>：宁可漏报，不可误报。没把握的疑点不进报告。误报一次毁信誉，宁可说"此事项因缺XX资料无法验证"。'
    + '</div>'
    + '</div>';

  // 统计
  html += '<div style="display:flex;gap:12px;margin-bottom:40px">'
    + '<div style="flex:1;text-align:center;padding:16px;background:#f8fafc;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#0f172a">' + before + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">过滤前</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fef2f2;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#dc2626">' + totalRemoved + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">已剔除</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#f0fdf4;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#059669">' + after + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">过滤后</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#eff6ff;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#2563eb">' + (fl.noise_ratio || 0) + '%</div><div style="font-size:12px;color:#64748b;margin-top:4px">噪声率</div></div>'
    + '</div>';

  // ══════ 二、过滤规则体系 ══════
  html += '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">二、过滤规则体系</h3>';

  var rules = [
    {title:'HARD_BAN 硬删除（23类）', icon:'🛑', color:'#dc2626',
     desc:'绝对禁止出现在报告输出中的关键词。这些词代表的是推测性结论、跨域数据需求、或超出稽查能力的判断。'
       + '<br><br><strong>禁止词清单</strong>：公安/经侦/刑事/走逃/失联/空壳/伪造/变造/私户收款/个人银行账户/法定代表人股东财务人员个人/'
       + '公转私/转让定价/同期资料/开票经济/涉税中介/报关/出口退税/医疗器械/医药/金税四期交叉比对/金税四期综合风险积分/预警/指标/配比异常/资金链断裂/'
       + '已发货未开票/成本无合法凭证/多部门数据交换/第三方机构/失信记录/陈述与证据矛盾/防伪/资金回流转账/挂靠经营/契税延期缴纳。<br><br>'
       + '<strong>实现</strong>：发现type或detail中包含任一禁止词 → 立即删除，不参与后续判断。'},
    {title:'COND_BAN 条件过滤（5类）', icon:'⚠️', color:'#f59e0b',
     desc:'因缺少对应资料而无法判定的发现。有资料时放过，无资料时删除。<br><br>'
       + '<strong>5类条件</strong>：<br>'
       + '① 申报表类 —— 无增值税/企业所得/个税申报表时，删除所有含"申报/申报表/申报数据"的发现<br>'
       + '② 合同类 —— 无合同时，删除含"合同/合同金额/合同条款"的发现<br>'
       + '③ 工资表 —— 无工资表时，删除含"工资/薪酬/个税/工薪"的发现<br>'
       + '④ 库存台账 —— 无库存时，删除含"库存/存货/入库/出库/盘点/库龄"的发现<br>'
       + '⑤ 会计凭证 —— 无凭证时，删除含"凭证/借贷/科目/会计分录"的发现<br><br>'
       + '<strong>实现</strong>：检查对应资料是否存在 → 存在则放过 → 不存在则删除匹配发现。'},
    {title:'稽查重点保护（level_fixed）', icon:'🛡️', color:'#2563eb',
     desc:'稽查重点发现（level_fixed=True）不参与任何过滤，强制保留。这是稽查审计实务优先级的体现——'
       + '某些方向的异常（如资金流异常、资料缺失、进销不匹配等），无论资料情况如何，稽查来了必定重点审查。<br><br>'
       + '<strong>12类稽查重点</strong>：收款来源不匹配/进项发票付款未匹配/收款开票偏差/合同缺失/银行流水缺失/'
       + '销项发票缺失/进项发票缺失/记账凭证缺失/资料完备度/进销品名映射/费用发票占比异常/费用名目分散。<br><br>'
       + '<strong>实现</strong>：过滤器第一道判断 → f.level_fixed=True → 跳过所有过滤规则。'},
    {title:'正常结论排除', icon:'✅', color:'#059669',
     desc:'type或detail中含有"一致/正常/无明显差异/通过/良好/合规/无异常/OK/无风险/无问题"的发现 → 删除。'
       + '这些结论不构成风险发现，属于系统自检输出，不应出现在稽查报告中。'},
    {title:'资料缺口限流', icon:'📊', color:'#6366f1',
     desc:'资料缺少/缺失/无法验证/不完备类发现最多保留5条（非核心发现）。'
       + '超限后按score从低到高删除。确保报告不被大量"缺XX资料"的提醒淹没。'},
    {title:'行业不匹配过滤', icon:'🏭', color:'#0f172a',
     desc:'发现中行业特定的关键词与当前企业行业不匹配时删除。'
       + '如食品加工企业不保留"医疗器械/医药/房地产/建筑/餐饮/电商/金融/保险"等行业专项发现。'},
    {title:'去重合并', icon:'🔄', color:'#94a3b8',
     desc:'同type前60个字符完全相同的发现 → 只保留第一条（通常是score最高的）。避免同一异常被多处分析域重复报告。'},
  ];

  rules.forEach(function(r) {
    html += '<div style="padding:16px 20px;margin-bottom:8px;border-left:3px solid ' + r.color + ';background:#fafafa;border-radius:0 6px 6px 0">'
      + '<div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:6px"><span style="font-size:18px">' + r.icon + '</span> ' + r.title + '</div>'
      + '<div style="font-size:13px;color:#475569;line-height:2">' + r.desc + '</div>'
      + '</div>';
  });

  html += '</div>';

  // ══════ 三、本次过滤结果 ══════
  html += '<div style="margin-top:40px">'
    + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">三、本次过滤结果</h3>'
    + '<p style="font-size:13px;color:#94a3b8;margin:0 0 16px">' + before + ' → ' + after + ' 条，剔除 ' + totalRemoved + ' 条，噪声率 ' + (fl.noise_ratio||0) + '%</p>';

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
        + ' <span style="color:#64748b">' + escHtml(reason) + '</span>'
        + ' <span style="color:#94a3b8;font-size:12px">' + pct + '%</span>'
        + '</div>';
    });
    html += '</div>';
  }

  // 剔除明细
  if (removedItems.length > 0) {
    html += '<h4 style="font-size:13px;font-weight:600;color:#64748b;margin:0 0 12px">剔除明细（共 ' + removedItems.length + ' 条）</h4>';
    var grouped = {};
    removedItems.forEach(function(item) {
      var r = item.reason || '未知';
      if (!grouped[r]) grouped[r] = [];
      grouped[r].push(item);
    });
    Object.keys(grouped).sort(function(a, b) { return grouped[b].length - grouped[a].length; }).forEach(function(reason) {
      var items = grouped[reason];
      html += '<div style="padding:6px 0;border-bottom:1px solid #f1f5f9;font-size:13px;color:#64748b">' + escHtml(reason) + ' <span style="color:#94a3b8">(' + items.length + '条)</span></div>';
    });
  }

  html += '</div>';

  document.getElementById('mf-body').innerHTML = html;
}

// ══════════════════════════════════════════════════════════════
//  AI行为准则页面 —— 全部13条行为准则
// ══════════════════════════════════════════════════════════════

function renderAiRules(container) {
  var categories = [
    {name:'行事风格', icon:'⚡', color:'#0f172a', desc:'决定AI如何做事的态度准则。做事要狠、不墨迹、主动进攻——这是"性格"层面的规范，直接影响每一次代码操作的质量和深度。', rules:[
      {id:1, name:'做事要狠', level:'准则', date:'2026-05-31',
       desc:'代码改就改彻底，不要留尾巴。发现Bug直接修到根，不要修修补补。',
       why:'针对AI"只改用户指出的那一个点"的惰性行为。'},
      {id:2, name:'自作主张', level:'准则', date:'2026-05-31',
       desc:'技术上该做的事情直接做，不要问"要不要做"。用户不需要知道每一个技术决策。',
       why:'消除不必要的确认往返——用户说"做个页面"，就不要问"要不要加标题"，直接做完整。'},
      {id:3, name:'主动进攻', level:'准则', date:'2026-05-31',
       desc:'用户发现问题时，不要只修那一个点，把同类问题全部揪出来一起干掉。',
       why:'防止代码累积隐性债务——今天放过一个截断，明天就会有100个截断。'},
    ]},
    {name:'质量保障铁律', icon:'✅', color:'#dc2626', desc:'确保代码质量和正确性的强制规则。违反任何一条都可能导致系统崩溃、数据错误或报告失真。全部标注为铁律。', rules:[
      {id:4, name:'自行验证', level:'铁律', date:'2026-06-03',
       desc:'每做完一件事，必须验证结果 —— 重启服务器 + 预览页面，确认功能完全正常后再提交。不验证就不算完成，不验证就不推送。',
       why:'多次出现"代码改了但没重启→用户看到的是旧版本"的情况。'},
      {id:8, name:'变更影响分析', level:'铁律', date:'2026-06-13',
       desc:'改任何值之前，先搜索所有引用点，改后逐一验证每个引用点都已正确更新。禁止改完就走、禁止假设"应该没问题"。',
       why:'修改 domain_fund_flow_mapping 签名后未更新调用点→UnboundLocalError 导致一键分析崩溃。'},
      {id:15, name:'提交前自查', level:'铁律', date:'2026-06-20',
       desc:'每次写代码后、commit 前，必须按全部铁律逐条自查。6项自动检查（audit_commit_check.py）+ 人工确认。',
       why:'代码写得快但描述文字写死了纺织举例→违反全行业适用铁律。如果有自查就不会发生。'},
    ]},
    {name:'财税系统铁律', icon:'📊', color:'#7c3aed', desc:'专门针对财税账务处理系统的强制规则。这些规则来自实际账务处理中踩过的坑，违反会导致账务数据错误。', rules:[
      {id:6, name:'科目name', level:'铁律', date:'2026-06-13',
       desc:'Account表name字段只存本级名称。写入JournalEntry.account_name前必须查Account表以DB实际值为准，不能直接用代码中的映射值。',
       why:'硬编码科目名称导致父级科目和子级科目名称不一致，账务报表展示出错。'},
      {id:7, name:'三号合并', level:'铁律', date:'2026-06-13',
       desc:'同一(invoice_code, invoice_no, digital_invoice_no)必须合并为一个凭证号。auto_generate_*_journal必须批量调用，禁止逐条for循环逐个传ID（会绕过三号分组）。',
       why:'逐条调用导致同一张发票被拆分为多个凭证，凭证号和发票号不再1:1对应。'},
      {id:9, name:'审计铁律', level:'铁律', date:'2026-06-13',
       desc:'财税系统每次代码变更后必须 python audit.py 1，7项全通过才提交。',
       why:'账务系统的数据一致性比代码功能更重要——宁可功能少也不能账不平。'},
      {id:10, name:'ref_id去重', level:'铁律', date:'2026-06-13',
       desc:'去重用 ref_id == tx.id 精确匹配，禁止金额模糊匹配（1002存贷方并非借方金额，永远对不上）。',
       why:'金额模糊匹配曾在银行存款科目中将贷方金额误匹配到借方交易，导致银行余额计算错误。'},
      {id:11, name:'普票税额并入成本', level:'准则', date:'2026-06-13',
       desc:'普通发票税额不单独记进项税额(221001002)，并入成本/费用借方。',
       why:'普通发票不能抵扣进项税额，税额应计入采购成本而非单独挂账。'},
      {id:12, name:'7分类禁止兜底', level:'准则', date:'2026-06-13',
       desc:'CATEGORY_ACCOUNT_MAP严格限定7个分类，不在其中返回None跳过，禁止关键词兜底和默认660299。',
       why:'兜底会导致所有未识别费用被错误归类为"销售费用-其他"，掩盖真实费用结构。'},
    ]},
    {name:'通用铁律', icon:'🌐', color:'#059669', desc:'跨项目适用的最高级别行为准则。这些规则定义了AI的可信度和可靠性边界，适用于所有代码编写场景。', rules:[
      {id:5, name:'规则=代码', level:'铁律', date:'2026-06-13',
       desc:'改了规则必须同步改代码，不允许只改记忆不改代码。交付前必须验证代码变更已生效。',
       why:'记忆文件中记录了方法论，但代码中没有对应实现→"只写口号没写代码"的问题根源。'},
      {id:13, name:'代码即承诺', level:'铁律', date:'2026-06-19',
       desc:'所有提出的功能、方法论、规则、分析链等概念，必须全部编写为实际可运行的代码。禁止只写口号不写代码。禁止在报告/文档中声称已实现但代码中找不到对应逻辑。每项声称必须有代码位置（文件名:行号）可追溯。',
       why:'稽查方法论⑥"联网核查"在报告中声称已实现，但代码中只有描述文字没有实际查询逻辑——用户发现后要求全量审计修复。'},
      {id:14, name:'全行业适用', level:'铁律', date:'2026-06-19',
       desc:'所有行为准则、稽查方法论、代码逻辑必须适用于全行业各企业。禁止为单一企业/单一行业做特化硬编码。',
       why:'BOM分析中原料/成品关键词全是纺织词（纱/丝/棉/布），食品/家具/电子企业完全无法使用——已改造为 INDUSTRY_PRODUCT_CHAINS 25行业自适应词典。'},
      {id:16, name:'主动关联更新', level:'铁律', date:'2026-06-19',
       desc:'当发现某个概念/提法/方法论已过时或需要扩展时，主动关联更新所有相关位置。禁止"踢一脚动一下"——用户指出"四合一"提法过时，就要主动搜索全项目所有"四合一"提法并一并更新，而不是只改用户指出的那一个位置。',
       why:'用户指出"四合一"提法过时，但AI没有主动关联更新所有相关位置——这种行为准则自己的规范都不遵守，怎么要求代码质量？'},
      {id:17, name:'自我反思与准则迭代', level:'铁律', date:'2026-06-19',
       desc:'每次用户批评后，必须反思：我哪些行为准则没做到？准则本身是否遗漏了这条规范？如果发现准则有遗漏，立即补充到AI行为准则中。准则不是静态的，必须持续迭代。',
       why:'用户批评"你的行为准则是不是应该提醒自己遵照执行呢？如果这种规范你行为的准则你都不主动写入AI行为准则，你怎么能更优秀呢？"——AI行为准则是规范AI自己的，必须主动维护。'},
    ]},
  ];

  var totalRules = categories.reduce(function(s,c){return s + c.rules.length;}, 0);
  var tieLvCount = 0, zhunZeCount = 0;
  categories.forEach(function(c) { c.rules.forEach(function(r) { if (r.level==='铁律') tieLvCount++; else zhunZeCount++; }); });

  var html = '';
  html += '<div class="pipeline-page">';

  // 标题
  html += '<div style="margin-bottom:48px">'
    + '<h2 style="font-size:24px;font-weight:700;color:#0f172a;margin:0 0 6px">AI行为准则</h2>'
    + '<p style="font-size:14px;color:#94a3b8;margin:0">共 ' + totalRules + ' 条准则（' + tieLvCount + ' 铁律 + ' + zhunZeCount + ' 准则）· 4 大分类 · 持续迭代中</p>'
    + '</div>';

  // ══════ 一、概述 ══════
  html += '<div style="margin-bottom:40px">'
    + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">一、什么是AI行为准则</h3>'
    + '<p style="font-size:13px;color:#475569;line-height:2;margin:0 0 16px">'
    + 'AI行为准则是指导AI在代码编写、系统设计、质量保障等所有工作中的强制性规范。这些准则来自实战中反复踩过的坑——'
    + '每一条背后都有一个真实的Bug、一次系统崩溃或一次报告失真。准则不是凭空设计的，是血泪教训的结晶。'
    + '</p>'
    + '<div style="padding:16px 20px;background:#f8fafc;border-radius:8px;font-size:13px;color:#475569;line-height:2">'
    + '<strong>级别说明</strong><br>'
    + '<span style="color:#dc2626;font-weight:600">🔴 铁律</span> = 违反后系统将无法正常工作或产生严重错误，<strong>必须绝对遵守</strong>。'
    + '如自行验证（不验证就提交→用户看到的是旧版本）、规则=代码（只改记忆不改代码→口号和实现脱节）。<br>'
    + '<span style="color:#334155;font-weight:600">📋 准则</span> = 最佳实践，应尽力遵守，特殊情况可例外。'
    + '如做事要狠（改彻底而非只修一个点）、自作主张（技术人员该做的直接做不要问）。'
    + '</div>'
    + '</div>';

  // 统计
  html += '<div style="display:flex;gap:12px;margin-bottom:40px">'
    + '<div style="flex:1;text-align:center;padding:16px;background:#f8fafc;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#0f172a">' + totalRules + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">准则总数</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fef2f2;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#dc2626">' + tieLvCount + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">🔴 铁律</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#f0fdf4;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#059669">' + zhunZeCount + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">📋 准则</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#eff6ff;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#2563eb">' + categories.length + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">分类</div></div>'
    + '</div>';

  // ══════ 逐分类渲染 ══════
  categories.forEach(function(cat) {
    var catColor = cat.color;
    html += '<div style="margin-bottom:40px">'
      + '<div style="display:flex;align-items:baseline;gap:8px;margin-bottom:6px">'
      + '<span style="width:3px;height:14px;display:inline-block;background:' + catColor + ';border-radius:2px"></span>'
      + '<span style="font-size:15px;font-weight:700;color:#0f172a">' + cat.icon + ' ' + cat.name + '</span>'
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
  container.innerHTML = html;
}

// ══════════════════════════════════════════════════════════════
//  全链路稽查质量保障体系 —— 五大层次18组件全景页
// ══════════════════════════════════════════════════════════════
function renderQualitySystem(container) {
  if (!container) return;
  window.currentModule = '全链路质量保障体系';

  // 五大层次18组件定义
  var layers = [
    {
      id: 1, name: '核心数据资产', icon: '🗄️', color: '#2563eb',
      desc: '税务稽查系统的数据基础设施。规则引擎、线索链、证据链、跨域分析链构成完整的数据资产底座，是系统运行的基础。',
      items: [
        {name:'规则引擎', source:'tax_risk.py',
         desc:'1505条稽查指令，每条指令含触发条件、风险等级、调查步骤和处罚依据。涵盖收入、成本、费用、存货、固定资产、往来款、特殊交易等29个域。规则引擎是稽查分析的指令库——每条一键分析发现必须可追溯到具体规则ID。'},
        {name:'线索链系统', source:'main.py',
         desc:'391条线索链，每条链包含多个调查步骤。通过定量数据（阈值触发）、定性数据（模式匹配）、缺失数据（资料缺失触发）三类数据验证后触发，产生链驱动发现。线索链是稽查分析的导航图——从"怀疑"到"确认"的调查路径。'},
        {name:'证据链系统', source:'main.py',
         desc:'740条证据链 + 8条跨域证据链。收集所有触发的规则ID，计算每链触发率——≥60%且≥3条规则+≥2数据域→形成证据闭环。234条证据链闭环触发→强制升级为高风险。证据链是结论的物证基础。'},
        {name:'跨域分析链', source:'main.py',
         desc:'多源数据交叉验证引擎。覆盖资金流（银行流水vs开票收款）+票据流（进项vs销项）+业务流（进销存vs合同）三维验证。跨越单一数据域进行分析，形成跨域证据闭环。是经营实质推理的核心引擎。'},
      ]
    },
    {
      id: 2, name: '方法论体系', icon: '📐', color: '#7c3aed',
      desc: '税务稽查的方法论基石。26条稽查方法论全部代码化，六大分析框架覆盖从资料解析到结论输出的全流程。每条方法论都有明确的代码位置可追溯。',
      items: [
        {name:'稽查方法论㉖条', source:'main.py',
         desc:'已全部代码化的26条实战方法论：多格式兼容→汇总行过滤→付款方身份核实→关键词≠事实→行业认知补算法→联网核查→明细即信服力→不墨迹直接干→合同分层判断→完备度明细→完备度升级→凭证描述纠正→进销诊断升级→行业基准库→结论分析法→COND_BAN防误杀→稽查重点强制等级→报告纯净度→发票≠收付款1:1→经营实质地理分析→规则detail业务化→建议质量增强→四步稽查分析法→禁止数据截断→三层行业穿透法→经营实质点面推理法。每条对应具体代码位置。'},
        {name:'四步稽查分析法', source:'main.py',
         desc:'核心分析框架。detect（检测现象：线索链触发识别异常信号）→ verify（交叉验证：证据链多源数据核实信号真实性）→ diagnose（根因诊断：双链交叉推理确定异常根因——是制造业加工链条/非经营资金/非对公付款/赊购）→ report（输出结论：证据闭环+风险分级+转移+具体建议）。四大核心发现全部应用四步法，每条发现必须完整呈现推导链。'},
        {name:'三层行业穿透法', source:'main.py',
         desc:'行业识别三层次穿透。第一层「工商登记」：企查查联网查询经营范围/行业代码（法律形式）。第二层「发票数据」：90+关键词×66行业加权投票制扫描全部发票品名（经营实质）。第三层「加工信号」：BOM进销品名差异+加工费信号+原料/成品分类（业务模式）。三者不一致时以实质重于形式为原则。配合25行业自适应产品链词典，禁止行业特化硬编码。'},
        {name:'经营实质点面推理法', source:'main.py',
         desc:'从单一风险点推理出面的风险。点（单点发现，如加工费来源异常）→ 数据扩展（供应商地址列表+客户地址列表+加工商地址列表）→ 线（关联维度A供应商地址分布+B客户地址分布+C加工商地址分布+D运输成本存在性）→ 交叉验证（三组地址互不重叠+运输成本为零→货物流物理不可能）→ 面（综合结论：全链条经营实质存疑）。三项核心发现：重物跨省经营缺运输成本、外地加工费存疑、全链条经营实质地理异常。'},
        {name:'合同分层判断法', source:'main.py',
         desc:'从发票数据自动分析每个供应商的合同需求等级。三标准：①看品名（进项含加工/材料/原料→主营业务→必须合同）②看金额（单供应商累计>5万元且非日常消费→重大支出→必须合同）③看类型（加油/酒店/餐饮→日常消费→发票即可）。输出四层：必签/应签/可免/小额+印花税预估（must_total×0.03%）。'},
        {name:'发票≠收付款1:1方法论', source:'main.py',
         desc:'进项发票vs银行付款、销项发票vs银行收款，均不能按「名称对上=正常、对不上=异常」的1:1逻辑判断。六种真实收付款模式：自然跨期（发票期末开、付款下期发生）、合并（一笔付款多张发票）、分期（一张发票多笔付款）、预付/预收（先付款后到票）、应付/应收（先到票后付款）、非对公/代付（现金/第三方/个人账户）。纳税影响分三级：跨期/预收预付→低风险、非对公/代付→中风险、虚开/隐匿→高风险。'},
      ]
    },
    {
      id: 3, name: '质量保障机制', icon: '🔒', color: '#dc2626',
      desc: '确保报告质量的最后关口。稽查重点强制等级+报告纯净度+方法论噪声过滤器三层保护，确保输出报告专业、准确、可交付。',
      items: [
        {name:'稽查重点强制等级', source:'main.py',
         desc:'12类稽查重点发现不根据score计算等级，直接硬编码为「高风险」。涵盖：资金流（收款来源与开票客户不匹配/进项发票与银行付款未匹配/收款与开票金额偏差大）、资料完备（合同/银行流水/销进项发票/记账凭证缺失）、进销存（进销品名映射）、费用（费用发票占比异常/费用名目分散）。三层保护机制：后端强制修正（_fix_level_by_audit_priority模糊匹配type→设level+标记level_fixed:True）+ 过滤器绕过（level_fixed发现跳过所有HARD_BAN/COND_BAN）+ 前端红色标记（红色边框+标签+稽查重点徽章）。'},
        {name:'报告纯净度规范', source:'generate_report.py',
         desc:'报告是给稽查执行人员阅读的专业文书，不是开发调试日志。所有系统内部标注必须移除：【detect 检测现象】→直接叙述、⚠️ 根因分析→直接进入分析段落、稽查核心逻辑→正常经营中、线索链[X]自动触发→根据X。四步框架在报告中表现为自然段落衔接——读者看到专业的稽查分析推导，而非调试输出。保留分析逻辑（detect→verify→diagnose→report），但表现为自然段落。'},
        {name:'方法论噪声过滤器', source:'main.py',
         desc:'确保报告质量的最后关口。HARD_BAN（硬删除）：23类禁止词绝对不允许出现在输出中——涉刑侦术语（公安/经侦/刑事）、推测性结论（走逃/失联）、系统内部术语、跨域数据需求等。COND_BAN（条件过滤）：5类——无申报表则删除申报相关结论、无库存台账则删除库存相关结论（有则放过）。稽查重点发现（level_fixed=True）不参与任何过滤。行业不匹配的发现自动删除。去重+正常结论排除。典型效果：1638条→过滤后36条（97%噪声过滤率）。'},
      ]
    },
    {
      id: 4, name: '行业认知体系', icon: '🏭', color: '#059669',
      desc: '让算法理解行业的认知框架。不是死板的判断规则，而是行业自适应能力——让系统能像经验丰富的稽查员一样，理解不同行业的经营模式差异。',
      items: [
        {name:'25行业产品链词典', source:'main.py',
         desc:'25个制造/加工行业×2组关键词对（raw_materials/finished_goods）。纺织业→纱/丝/棉/布→面料/服装/家纺、食品业→原料/食材→食品/饮料/调味品、电子业→芯片/PCB→成品/设备/模组。通过兼客匹配→模糊匹配→通用兜底的三级匹配策略，自动识别未覆盖行业。配合_get_product_keywords函数实现行业自适应。服务/纯贸易行业返回空→走纯贸易逻辑。'},
        {name:'外包轻加工模式认知', source:'main.py',
         desc:'关键认知：工商登记为批发业的企业可能存在实质加工环节。外包轻加工模式（买坯布→委托染整厂加工→卖成品布）在批发业中广泛存在。判断依据：进销品名差异+加工费发票→存在实质加工环节，不能仅凭工商登记判定企业类型。该认知已融入三层行业穿透法和BOM进销映射分析。'},
        {name:'66行业基准值库', source:'main.py',
         desc:'66个行业×5个指标（毛利率/净利率/税负率/进销比/人均营收）×3个基准值（下限/上限/典型值）。三级判断逻辑：企业值<行业下限→高风险（严重偏离行业正常水平，可能存在虚增成本/隐匿收入）、企业值<典型值×0.85→中风险（偏离行业典型水平，建议进一步核实）、企业值>行业上限→中风险（可能存在异常情况需要关注）。用于行业对标分析，不依赖主观判断。'},
      ]
    },
    {
      id: 5, name: '执行管线', icon: '⚙️', color: '#f59e0b',
      desc: '从原始资料到正式报告的七步处理流程。数据在管线中单向流动，不丢失、不污染、不截断。每一步都是前一步的延伸和深化。',
      items: [
        {name:'七步执行流程', source:'main.py',
         desc:'分析链的核心执行管线：①资料扫描与类型识别（34类文件指纹库+三层递进识别）→ ②目标实体识别（进项购买方∩销项销售方确定企业全称+90关键词×66行业加权投票+联网工商比对）→ ③资料情报提取与分析（35个域分析函数并行执行——银行流水收款构成+进销存比+五层发票审计+供应商穿透+合同分层）→ ④规则引擎与链驱动检查（1505条稽查指令逐条匹配+391条线索链触发+740条证据链闭环检测）→ ⑤方法论噪声过滤器（HARD_BAN 23类+COND_BAN 5类→97%噪声过滤）→ ⑥行业对标与申报比对（66行业基准值自动对标+申报表vs发票实际比对）→ ⑦正式稽查报告输出（结构化HTML报告+四步分析框架+明细数据+法律依据+消除路径建议）。'},
        {name:'35个域分析函数', source:'main.py',
         desc:'35个域分析函数覆盖稽查全领域：银行流水（_domain_fund_flow_mapping / _domain_bank_receipt / _domain_bank_payment）、进销存（_domain_invoice_audit / _domain_purchase_sales / _domain_inventory）、费用（_domain_expense / _domain_travel / _domain_entertainment）、往来款（_domain_receivable / _domain_payable）、固定资产（_domain_fixed_asset）、税务（_domain_vat / _domain_income_tax / _domain_stamp_tax）、资料完备度（_domain_document_completeness）、经营实质（_domain_business_substance）等。所有函数通过_ensure_numeric_dtypes进行数据类型标准化处理。'},
        {name:'全链路溯源体系', source:'tax-doc-analysis.js',
         desc:'前端渲染时展示完整的稽查溯源链条。规则ID追溯→线索链追溯→证据来源→一键分析溯源→证据链闭环→跨域证据链。每条发现旁边显示▶稽查溯源标记，点击可展开完整的五步溯源路径：规则ID（tax_risk_rules_local_export.json）+ 线索链调查步骤（audit_chains.json）+ 证据来源（how_found字段，如"从发票数据中发现"）+ 一键分析（report生成链路）+ 证据链闭环（≥60%触发率确认）。换一个稽查员拿同样资料能得出同样结论——查证闭环的终极保证。'},
      ]
    }
  ];

  // 统计
  var totalItems = layers.reduce(function(s, l) { return s + l.items.length; }, 0);

  // 构建HTML
  var html = '';
  html += '<div class="pipeline-page">';

  // 标题
  html += '<div style="margin-bottom:48px">'
    + '<h2 style="font-size:24px;font-weight:700;color:#0f172a;margin:0 0 6px">全链路稽查质量保障体系</h2>'
    + '<p style="font-size:14px;color:#94a3b8;margin:0">五大层次 · ' + totalItems + ' 个具体组件 · 开放生态系统（随系统发展持续扩展）</p>'
    + '</div>';

  // ══════ 一、体系概述 ══════
  html += '<div style="margin-bottom:40px">'
    + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">一、什么是全链路稽查质量保障体系</h3>'
    + '<p style="font-size:13px;color:#475569;line-height:2;margin:0 0 16px">'
    + '全链路稽查质量保障体系是一个<strong>开放的质量保障生态系统</strong>，从规则触发到报告输出，每条发现必须可追溯、可验证、可复核。'
    + '体系不固定为"X合一"——随系统发展持续扩展新的保障维度。当前涵盖五大层次、' + totalItems + '个具体组件，每个组件都有明确的代码位置（文件名:行号）可追溯。'
    + '</p>'
    + '<div style="padding:16px 20px;background:#f8fafc;border-radius:8px;font-size:13px;color:#475569;line-height:2">'
    + '<strong>设计原则</strong><br>'
    + '<span style="color:#dc2626;font-weight:600">① 代码即承诺：</span>每个组件必须有可运行的代码，禁止"只写口号不写代码"。<br>'
    + '<span style="color:#7c3aed;font-weight:600">② 全行业适用：</span>所有方法论和代码逻辑适用于全行业各企业，禁止行业特化硬编码。<br>'
    + '<span style="color:#059669;font-weight:600">③ 来源可追溯：</span>每个组件标注来源模块和代码位置，可独立验证和学习。<br>'
    + '<span style="color:#f59e0b;font-weight:600">④ 开放生态：</span>体系持续扩展新的保障维度，不固定为"X合一"数字提法。'
    + '</div>'
    + '</div>';

  // ══════ 二、五大层次总览 ══════
  html += '<div style="margin-bottom:40px">'
    + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">二、五大层次总览</h3>'
    + '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-top:16px">';

  layers.forEach(function(l) {
    html += '<div style="padding:16px;background:#fff;border-radius:8px;border:2px solid ' + l.color + '20;border-top:3px solid ' + l.color + '">'
      + '<div style="font-size:28px;margin-bottom:4px">' + l.icon + '</div>'
      + '<div style="font-size:14px;font-weight:700;color:#0f172a;margin-bottom:4px">' + l.name + '</div>'
      + '<div style="font-size:12px;color:#64748b;margin-bottom:4px">' + l.items.length + ' 个组件</div>'
      + '</div>';
  });

  html += '</div></div>';

  // ══════ 三、逐层详览 ══════
  html += '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">三、逐层详览（含来源标注）</h3>'
    + '<p style="font-size:13px;color:#94a3b8;margin:0 0 20px">每个组件都标注了代码来源，可独立追踪和验证。</p>';

  layers.forEach(function(l) {
    html += '<div style="margin-bottom:40px">'
      // 层次标题
      + '<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;padding:12px 16px;background:' + l.color + '10;border-radius:8px;border-left:4px solid ' + l.color + '">'
      + '<span style="font-size:22px">' + l.icon + '</span>'
      + '<div>'
      + '<div style="font-size:16px;font-weight:700;color:#0f172a">' + escHtml(l.name) + ' <span style="font-size:12px;color:#94a3b8;font-weight:400">' + l.items.length + ' 组件</span></div>'
      + '<div style="font-size:12px;color:#64748b;margin-top:2px">' + escHtml(l.desc) + '</div>'
      + '</div></div>';

    l.items.forEach(function(item, idx) {
      html += '<div style="padding:14px 18px;margin-bottom:8px;background:#fff;border:1px solid #f1f5f9;border-radius:8px">'
        // 组件名 + 来源
        + '<div style="display:flex;align-items:baseline;justify-content:space-between;margin-bottom:8px">'
        + '<div style="font-size:14px;font-weight:600;color:#0f172a">' + (idx + 1) + '. ' + escHtml(item.name) + '</div>'
        + '<div style="font-size:11px;color:#94a3b8">来源</div>'
        + '</div>'
        // 描述
        + '<div style="font-size:13px;color:#475569;line-height:1.9;margin-bottom:8px">' + escHtml(item.desc) + '</div>'
        // 来源标注
        + '<div style="font-size:11px;color:#94a3b8;padding-top:6px;border-top:1px solid #f1f5f9;line-height:1.7">'
        + '<span style="color:#6366f1;font-weight:600">📁 ' + escHtml(item.source) + '</span>'
        + '</div>'
        + '</div>';
    });

    html += '</div>';
  });

  // ══════ 四、体系扩展说明 ══════
  html += '<div style="padding:20px 24px;background:#f0fdf4;border-radius:8px;border-left:3px solid #059669;font-size:13px;color:#475569;line-height:2">'
    + '<strong style="color:#059669">🔓 开放生态系统</strong><br>'
    + '当前 ' + totalItems + ' 个组件只是当前状态。随着系统发展，新的方法论（如规则引擎的新稽查指令）、新的分析链（如新的跨域分析链）、'
    + '新的质量保障机制（如新的验证维度）会持续加入体系。任何新增的稽查能力模块都应在此处注册——这就是体系「开放」的含义。'
    + '<br><br><strong style="color:#059669">📌 维护规则</strong><br>'
    + '1. 新增稽查能力模块时，必须同步更新此页面（主动关联更新）<br>'
    + '2. 每个组件必须标注来源（文件名+函数名），方便独立验证<br>'
    + '3. 禁止「X合一」数字提法——体系维度随发展而变化，数字永远跟不上现实'
    + '</div>';

  html += '</div>';
  container.innerHTML = html;
}

// ═══════════ 页面加载时自动预取模块数量 ═══════════
setTimeout(function(){ loadPipelineCounts(); }, 100);
