(function () {
  'use strict';

  function esc(value) {
    if (typeof window.escHtml === 'function') return window.escHtml(String(value == null ? '' : value));
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function list(items, className) {
    var values = (items || []).filter(function (item) { return item != null && String(item).trim(); });
    if (!values.length) return '<p class="m3-muted">本场景不设置无依据的固定项目。</p>';
    return '<ul class="' + (className || 'm3-list') + '">' + values.map(function (item) {
      return '<li>' + esc(typeof item === 'string' ? item : JSON.stringify(item)) + '</li>';
    }).join('') + '</ul>';
  }

  function metric(value, label, note) {
    return '<div class="m3-metric"><strong>' + esc(value) + '</strong><span>' + esc(label) + '</span>'
      + (note ? '<small>' + esc(note) + '</small>' : '') + '</div>';
  }

  function capabilityLedgerHtml(ledger) {
    ledger = ledger || {};
    var items = ledger.items || [];
    var rows = items.map(function (item) {
      var typeLabel = item.method_type === 'industry_fact_review_contract' ? '行业场景合同' : '跨行业复核合同';
      var automation = item.automatic_fact_scope === 'partial' ? '部分原子筛查支持' : '尚无确定性执行器';
      var validation = item.independent_validation_status === 'passed' ? '独立验证通过' : '尚未独立验证';
      return '<tr><td>' + esc(item.capability_id || '') + '</td><td>' + esc(item.name || '')
        + '</td><td>' + esc(item.industry_code === 'ALL' ? '全行业' : item.industry_code || '')
        + '</td><td>' + esc(typeLabel) + '</td><td>' + esc(automation)
        + '</td><td>' + esc((item.candidate_atomic_rule_ids || []).join('、') || '无')
        + '</td><td>' + esc(validation) + '</td><td>' + esc(item.next_build_action || '') + '</td></tr>';
    }).join('');
    return '<div class="m3-metrics">'
      + metric(ledger.methodology_item_count || 0, '逐项能力账本', '每项都有真实状态和下一步')
      + metric(ledger.verified_atomic_rule_count || 0, '已验证原子规则', '只能形成部分客观筛查事实')
      + metric((ledger.design_status_counts || {}).partial_atomic_support || 0, '有部分自动支持的方法', '不等于完整自动执行')
      + metric(ledger.independently_validated_method_count || 0, '独立验证通过的方法', '未验证不得作为正式能力')
      + '</div><div class="m3-principle"><b>能力数量边界</b><p>' + esc(ledger.boundary || '') + '</p></div>'
      + '<details class="m3-contract"><summary><span><b>242</b>逐项查看真实能力</span><em>方法、自动筛查、验证和发布分别计数</em></summary>'
      + '<div class="m3-contract-body"><div class="m3-table-wrap"><table><thead><tr><th>编号</th><th>方法或场景</th><th>行业</th><th>类型</th><th>自动化状态</th><th>关联原子规则</th><th>独立验证</th><th>下一步建设</th></tr></thead><tbody>'
      + rows + '</tbody></table></div></div></details>';
  }

  function canonicalModelHtml(model) {
    model = model || {};
    var entities = model.entities || {};
    var cards = Object.keys(entities).map(function (code) {
      var item = entities[code] || {};
      return '<article class="m3-domain"><b>' + esc(code) + '</b><h5>' + esc(item.name || '')
        + '</h5><p>核心字段：' + esc((item.required_core_fields || []).join('、') || '按资料内容确认')
        + '</p><small>来源类型：' + esc((item.source_types || []).join('、')) + '</small></article>';
    }).join('');
    var formats = Object.keys(model.supported_formats || {}).map(function (ext) {
      return ext.replace('.', '').toUpperCase() + '（' + model.supported_formats[ext] + '）';
    });
    return '<div class="m3-principle"><b>统一模型边界</b><p>' + esc(model.boundary || '') + '</p></div>'
      + '<p><b>已登记资料格式：</b>' + esc(formats.join('、')) + '</p>'
      + '<div class="m3-domain-grid">' + cards + '</div>';
  }

  function validationBlueprintHtml(validation) {
    validation = validation || {};
    var stateNames = {supported:'事实支持',rebutted:'反证成立',partial:'部分支持',contradictory:'证据矛盾',insufficient:'资料不足'};
    var first = (validation.scene_requirements || [])[0] || {};
    return '<div class="m3-metrics">'
      + metric(validation.industry_contract_count || 0, '行业与叠加模式', '20个行业门类＋3个叠加模式')
      + metric(validation.scene_count || 0, '必须独立验证的场景', '每场景不得只用文字样例验收')
      + metric(validation.required_validation_cells || 0, '分层必验单元', '场景、格式、组合和原子规则')
      + metric(validation.minimum_independent_case_count || 0, '最低独立案例数', '每场景至少' + esc(first.minimum_independent_cases || 10) + '例')
      + '</div><div class="m3-grid-2"><article><h4>每个场景必须覆盖</h4>'
      + list((first.required_evidence_states || []).map(function (item) { return stateNames[item] || item; }))
      + '<p class="m3-boundary">每场景至少3个风险正样本、3个正常负样本，同时达到准确率和召回率门槛。</p></article>'
      + '<article><h4>每种资料格式必须覆盖</h4>'
      + list(['可用解析','部分解析','解析阻断','源文件定位','字段映射变化','错误模板不得假装无异常'])
      + '<p class="m3-boundary">单资料、双资料、多资料部分链、完整链、关键资料缺失、资料冲突和无可用资料均须独立验证。</p></article></div>'
      + '<div class="m3-principle"><b>什么样的样本才算数</b><p>' + esc(validation.boundary || '') + '</p></div>';
  }

  function scenarioHtml(scene) {
    var doubt = scene.doubt || {};
    var clue = scene.clue_chain || {};
    var evidence = scene.evidence_chain || {};
    var analysis = scene.analysis_chain || {};
    var domains = scene.domain_collaboration || {};
    var report = scene.report_contract || {};
    var policy = scene.policy_applicability || {};
    var steps = (clue.steps || []).map(function (step) {
      return '<li><b>' + esc(step.step || '') + '</b><span>' + esc(step.action || '') + '</span>'
        + (step.deliverable ? '<small>交付：' + esc(step.deliverable) + '</small>' : '') + '</li>';
    }).join('');
    var partners = (domains.partners || []).map(function (partner) {
      return '<tr><td>' + esc(partner.domain || '') + '</td><td>' + esc(partner.responsibility || '')
        + '</td><td>' + esc(partner.handoff || '') + '</td></tr>';
    }).join('');
    var cases = (scene.validation_cases || []).map(function (item) {
      return '<tr><td>' + esc(item.case || '') + '</td><td>' + esc(item.facts || '')
        + '</td><td>' + esc(item.expected || '') + '</td></tr>';
    }).join('');
    var acceptanceCases = (scene.acceptance_cases || []).map(function (item) {
      return '<tr><td>' + esc(item.case || '') + '</td><td>' + esc(item.facts || '')
        + '</td><td>' + esc(item.expected || '') + '</td></tr>';
    }).join('');
    return '<details class="m3-scene"><summary><span><b>' + esc(scene.id) + '</b>' + esc(scene.name || '')
      + '</span><em>' + esc((clue.steps || []).length) + '步调查 · '
      + esc((evidence.supporting_sources || []).length) + '类支持资料 · '
      + esc((scene.validation_cases || []).length) + '组边界样本</em></summary>'
      + '<div class="m3-scene-body">'
      + '<div class="m3-target"><b>待证事实</b><p>' + esc(doubt.target_fact || '') + '</p></div>'
      + '<div class="m3-grid-2"><article><h5>适用与停止条件</h5>'
      + '<p class="m3-label">适用</p>' + list((scene.applicability || {}).apply_when)
      + '<p class="m3-label">不适用或停止</p>' + list((scene.applicability || {}).do_not_apply_when)
      + '</article><article><h5>需要先排除的正常解释</h5>'
      + list(analysis.alternatives || doubt.must_exclude || doubt.reasonable_explanations)
      + '</article></div>'
      + '<article><h5>调查线索路径</h5><ol class="m3-steps">' + steps + '</ol><p class="m3-boundary">'
      + esc(clue.terminal || '') + '</p></article>'
      + '<div class="m3-grid-2"><article><h5>支持证据及来源</h5>' + list(evidence.supporting_sources)
      + '</article><article><h5>反向证据及合理解释材料</h5>' + list(evidence.opposing_sources) + '</article></div>'
      + '<div class="m3-grid-2"><article><h5>证据不足时停止</h5>' + list(evidence.insufficient_when)
      + '</article><article><h5>证据质量复核</h5>' + list(evidence.quality_checks) + '</article></div>'
      + '<article><h5>分析论证路径</h5><p><b>核心命题：</b>' + esc(analysis.proposition || '') + '</p>'
      + list(analysis.reasoning) + '<p class="m3-boundary"><b>税法边界：</b>' + esc(analysis.tax_boundary || '') + '</p></article>'
      + '<article><h5>政策期间与效力核验</h5><div class="m3-grid-2"><div><p class="m3-label">必须核对</p>'
      + list(policy.required_dimensions) + '</div><div><p class="m3-label">停止使用依据</p>' + list(policy.stop_if)
      + '</div></div><p class="m3-boundary">' + esc(policy.output_boundary || '') + '</p></article>'
      + '<article><h5>业务域协同</h5><p><b>牵头业务域：</b>' + esc(domains.lead || '') + '</p>'
      + '<div class="m3-table-wrap"><table><thead><tr><th>协同业务域</th><th>职责</th><th>交付</th></tr></thead><tbody>'
      + partners + '</tbody></table></div><p class="m3-boundary">' + esc(domains.conflict_rule || '') + '</p></article>'
      + '<article><h5>报告移交合同</h5><div class="m3-grid-2"><div><p class="m3-label">必须写明</p>'
      + list(report.must_state) + '</div><div><p class="m3-label">禁止写法</p>' + list(report.forbidden) + '</div></div></article>'
      + (cases ? '<article><h5>正向、反向与边界验证</h5><div class="m3-table-wrap"><table><thead><tr><th>样本</th><th>事实</th><th>预期状态</th></tr></thead><tbody>' + cases + '</tbody></table></div></article>' : '')
      + (acceptanceCases ? '<article><h5>五类证据状态验收</h5><div class="m3-table-wrap"><table><thead><tr><th>证据状态</th><th>场景化事实</th><th>输出上限</th></tr></thead><tbody>' + acceptanceCases + '</tbody></table></div></article>' : '')
      + '</div></details>';
  }

  function contractHtml(contract) {
    var scenes = contract.scenarios || [];
    var clueDepths = [];
    var caseDepths = [];
    scenes.forEach(function (scene) {
      var clue = (scene.clue_chain || {}).steps || [];
      if (clueDepths.indexOf(clue.length) < 0) clueDepths.push(clue.length);
      var cases = (scene.validation_cases || []).length;
      if (caseDepths.indexOf(cases) < 0) caseDepths.push(cases);
    });
    clueDepths.sort(function (a, b) { return a - b; });
    caseDepths.sort(function (a, b) { return a - b; });
    return '<details class="m3-contract"><summary><span><b>' + esc(contract.code) + '</b>' + esc(contract.name || '')
      + '</span><em>' + scenes.length + '个场景 · 调查深度' + esc(clueDepths.join('、'))
      + ' · 样本深度' + esc(caseDepths.join('、')) + '</em></summary><div class="m3-contract-body">'
      + '<p class="m3-contract-note">' + esc(contract.positioning || '') + '</p>'
      + scenes.map(scenarioHtml).join('') + '</div></details>';
  }

  function canonicalModuleHtml(module) {
    return '<details class="m3-canonical"><summary><span><b>' + esc(module.id) + '</b>' + esc(module.name || '')
      + '</span><em>' + esc((module.rules || []).length) + '项事实规则 · '
      + esc((module.clue_paths || []).length) + '类调查路径</em></summary><div class="m3-canonical-body">'
      + '<p>' + esc(module.purpose || '') + '</p><div class="m3-grid-2"><article><h5>启动门槛</h5>' + list(module.activation_gate)
      + '</article><article><h5>可证伪事实规则</h5>'
      + list((module.rules || []).map(function (rule) { return rule.id + '｜' + rule.fact_hypothesis; }))
      + '</article></div><div class="m3-grid-2"><article><h5>分析检验</h5>' + list(module.analysis_tests)
      + '</article><article><h5>报告边界</h5><p>' + esc(module.report_boundary || '') + '</p></article></div></div></details>';
  }

  function workflowHtml(framework) {
    return (framework.workflow || []).map(function (step) {
      return '<article class="m3-work"><b>' + esc(step.id) + '</b><div><h5>' + esc(step.name || '') + '</h5><p>'
        + esc(step.objective || '') + '</p><small>放行门槛：' + esc(step.gate || '') + '</small><em>交付：'
        + esc(step.output || '') + '</em></div></article>';
    }).join('');
  }

  function domainHtml(framework) {
    return (framework.business_domains || []).map(function (domain) {
      return '<article class="m3-domain"><b>' + esc(domain.id) + '</b><h5>' + esc(domain.name || '')
        + '</h5><p>' + esc(domain.scope || '') + '</p>' + list(domain.key_outputs) + '</article>';
    }).join('');
  }

  function latestResultHtml(data) {
    if (!data || data.ok === false) {
      return '<div class="m3-empty"><b>当前账套尚无可复核的执行快照</b><p>没有执行记录、资料不足、规则未激活和执行后未发现异常是不同状态，不能合并解释为“无风险”。</p></div>';
    }
    var report = data.report && typeof data.report === 'object' ? data.report : data;
    var findings = report.all_findings || report.findings || [];
    var scenario = report.scenario_methodology || {};
    var ledger = report.capability_ledger || {};
    var canonical = report.canonical_tax_data || {};
    var adaptation = report.document_combination_adaptation || canonical.document_combination_adaptation || {};
    var validation = report.universal_validation || {};
    var currentValidation = validation.current_scope || {};
    return '<div class="m3-live-grid">'
      + metric(findings.length, '待复核事项', '不等于违法事实')
      + metric(scenario.scene_count || 0, '已选择场景', scenario.industry_name || '按实际经营匹配')
      + metric(scenario.ready_for_human_review || 0, '资料就绪', '仍须人工核验')
      + metric(scenario.pending_more_sources || 0, '待补资料', '缺失不推定违法')
      + metric(ledger.methodology_item_count || 0, '账本已登记', '必须为242且无静默状态')
      + metric(canonical.canonical_record_count || 0, '标准财税记录', '来自本轮全部已解析资料')
      + metric(adaptation.unresolved_document_count || 0, '资料适配待处理', '逐份说明原因和下一步')
      + metric(validation.qualified_independent_case_count || 0, '合格独立验证样本', currentValidation.release_ready ? '当前范围验证通过' : '当前范围不得正式发布')
      + '</div>'
      + ((currentValidation.blockers || []).length ? '<div class="m3-principle"><b>当前独立验证门禁</b>' + list(currentValidation.blockers) + '</div>' : '');
  }

  function renderPage(container, coverage, portfolio, catalog, framework, ledger, canonicalModel, validationBlueprint, latest) {
    var inventory = coverage.inventory || {};
    var acceptance = coverage.acceptance || {};
    var contracts = portfolio.contracts || [];
    var industries = contracts.filter(function (item) { return /^[A-T]$/.test(item.code || ''); });
    var overlays = contracts.filter(function (item) { return String(item.code || '').indexOf('OVERLAY-') === 0; });
    var taxRows = (framework.tax_coverage || []).map(function (group) {
      return '<tr><td>' + esc(group.group || '') + '</td><td>' + esc((group.items || []).join('、'))
        + '</td><td>' + esc(group.focus || '') + '</td></tr>';
    }).join('');
    var industryRows = contracts.map(function (item) {
      var scenes = item.scenarios || [];
      var clueDepths = [];
      var caseDepths = [];
      scenes.forEach(function (scene) {
        var cd = ((scene.clue_chain || {}).steps || []).length;
        var vd = (scene.validation_cases || []).length;
        if (clueDepths.indexOf(cd) < 0) clueDepths.push(cd);
        if (caseDepths.indexOf(vd) < 0) caseDepths.push(vd);
      });
      return '<tr><td>' + esc(item.code) + '</td><td>' + esc(item.name || '') + '</td><td>' + scenes.length
        + '</td><td>' + esc(clueDepths.sort(function (a,b){return a-b;}).join('、')) + '</td><td>'
        + esc(caseDepths.sort(function (a,b){return a-b;}).join('、')) + '</td></tr>';
    }).join('');
    var html = '<style>' + methodologyCss() + '</style><div class="m3-shell">'
      + '<aside class="m3-nav"><b>稽查方法论</b>'
      + [['m3-overview','职责与主流程'],['m3-coverage','覆盖体系'],['m3-ledger','真实能力账本'],['m3-data-model','统一数据模型'],['m3-validation','独立验证体系'],['m3-common','共同事实底座'],['m3-industries','全行业场景'],['m3-workflow','作业规程'],['m3-domains','业务域协同'],['m3-chains','链路与证据'],['m3-report','报告移交'],['m3-results','执行成果'],['m3-quality','质量与进化']].map(function (item) {
        return '<a href="#' + item[0] + '">' + item[1] + '</a>';
      }).join('') + '</aside><main class="m3-main">'
      + '<header class="m3-hero" id="m3-overview"><span>税务稽查方法论 · 现行版本 ' + esc(portfolio.version || '') + '</span>'
      + '<h1>从资料进入到报告移交的完整专业作业体系</h1><p>' + esc(portfolio.positioning || '')
      + ' 系统负责形成待核事实、调查任务、证据矩阵、分析底稿和报告移交包；有权人员依法完成事实认定、税额确认、处理处罚及其他法定决定。</p>'
      + '<div class="m3-flow"><b>资料准入</b><i>→</i><b>经营画像</b><i>→</i><b>事实规则</b><i>→</i><b>调查核验</b><i>→</i><b>证据组织</b><i>→</i><b>分析论证</b><i>→</i><b>人工审理</b><i>→</i><b>报告移交</b></div></header>'
      + '<section class="m3-section" id="m3-coverage"><div class="m3-heading"><span>01</span><div><h2>覆盖体系</h2><p>共同事实、行业合同和叠加业务分层组合，数量由真实业务需要决定。</p></div></div>'
      + '<div class="m3-metrics">'
      + metric(inventory.canonical_rules || 0, '跨行业共同事实', '统一资料与程序底座')
      + metric(inventory.industry_scenarios || 0, '完整行业场景', '每场景含调查、证据与分析')
      + metric(industries.length, '行业门类', '按实际经营活动选择')
      + metric(overlays.length, '叠加业务层', '平台、跨境与集团关联')
      + metric(inventory.clue_paths || 0, '调查路径', '共同路径与行业路径合计')
      + metric(inventory.evidence_plans || 0, '证据方案', '同时处理支持与反向材料')
      + metric(acceptance.acceptance_case_count || 0, '证据状态验收', '五类状态逐场景校准')
      + '</div><div class="m3-principle"><b>数量原则</b><p>' + esc(portfolio.count_policy || '') + '</p></div>'
      + '<h3>税费事项覆盖</h3><div class="m3-table-wrap"><table><thead><tr><th>税费组</th><th>覆盖事项</th><th>核验重点</th></tr></thead><tbody>' + taxRows + '</tbody></table></div>'
      + '<h3>行业和叠加业务覆盖</h3><div class="m3-table-wrap"><table><thead><tr><th>代码</th><th>合同</th><th>场景</th><th>调查深度</th><th>边界样本深度</th></tr></thead><tbody>' + industryRows + '</tbody></table></div></section>'
      + '<section class="m3-section" id="m3-ledger"><div class="m3-heading"><span>02</span><div><h2>242项真实能力账本</h2><p>逐项公开方法论、自动执行、独立验证和正式发布状态，禁止用资产数量冒充自动稽查能力。</p></div></div>'
      + capabilityLedgerHtml(ledger) + '</section>'
      + '<section class="m3-section" id="m3-data-model"><div class="m3-heading"><span>03</span><div><h2>统一财税数据模型</h2><p>不同银行、财务软件、税务导出、非标准表格和非结构化文档统一映射到稳定财税对象，并保留源文件定位。</p></div></div>'
      + canonicalModelHtml(canonicalModel) + '</section>'
      + '<section class="m3-section" id="m3-validation"><div class="m3-heading"><span>04</span><div><h2>全行业独立验证体系</h2><p>固定回归样本、方法论自带文字样例和独立验证案例严格分开计数。</p></div></div>'
      + validationBlueprintHtml(validationBlueprint) + '</section>'
      + '<section class="m3-section" id="m3-common"><div class="m3-heading"><span>05</span><div><h2>跨行业共同事实底座</h2><p>先解决身份、期间、资料、交易、资金、发票、税会和程序问题，再叠加行业经营事实。</p></div></div>'
      + (catalog.modules || []).map(canonicalModuleHtml).join('') + '</section>'
      + '<section class="m3-section" id="m3-industries"><div class="m3-heading"><span>06</span><div><h2>全行业完整场景合同</h2><p>每个场景在本页完整呈现适用边界、调查路径、支持与反向证据、分析论证、域协同和报告要求。</p></div></div>'
      + contracts.map(contractHtml).join('') + '</section>'
      + '<section class="m3-section" id="m3-workflow"><div class="m3-heading"><span>07</span><div><h2>全流程作业规程</h2><p>每一步都有启动条件、停止条件和可审计交付，不允许跨越资料、证据和程序门槛。</p></div></div><div class="m3-workflow">'
      + workflowHtml(framework) + '</div></section>'
      + '<section class="m3-section" id="m3-domains"><div class="m3-heading"><span>08</span><div><h2>业务域协同</h2><p>不同业务域围绕同一待证事实协同，冲突时回到原始资料和实际履行，不以多数表决或分数裁决。</p></div></div><div class="m3-domain-grid">'
      + domainHtml(framework) + '</div></section>'
      + '<section class="m3-section" id="m3-chains"><div class="m3-heading"><span>09</span><div><h2>调查、证据与分析一体化</h2><p>链路不是相互独立的清单，而是同一待证事实从发现、核验、证明到论证的连续记录。</p></div></div>'
      + '<div class="m3-grid-3"><article><h4>调查链</h4><p>把信号拆成待证事实、资料请求、访谈问题、外部核验、分支条件和停止条件；只决定怎样查。</p>'
      + list((((framework.chain_contracts || {}).clue || {}).required_fields)) + '</article>'
      + '<article><h4>证据链</h4><p>围绕证明对象评价真实性、关联性、合法性、来源独立性、完整性和反向证据；只说明事实能否被证明。</p>'
      + list((((framework.chain_contracts || {}).evidence || {}).required_fields)) + '</article>'
      + '<article><h4>分析链</h4><p>把事实、竞争解释、会计处理、税法要件、金额复算和程序状态分别论证；不把评分写成结论。</p>'
      + list((((framework.chain_contracts || {}).analysis || {}).required_fields)) + '</article></div>'
      + '<div class="m3-principle"><b>证据原则</b>' + list(((framework.evidence_model || {}).rules)) + '</div></section>'
      + '<section class="m3-section" id="m3-report"><div class="m3-heading"><span>10</span><div><h2>报告移交接口</h2><p>方法论只向报告编制模块移交通过门禁的事实、证据、测算、依据、限制和人工复核记录。</p></div></div>'
      + '<div class="m3-grid-3"><article><h4>事实包</h4><p>主体、事项、期间、业务主键、原始来源、事实时间线、差异复算及未取得资料。</p></article>'
      + '<article><h4>证据包</h4><p>证明对象、支持与反向证据、取得方式、证据三性、来源谱系、矛盾处理和成熟度。</p></article>'
      + '<article><h4>专业复核包</h4><p>会计处理、税费要件、金额底稿、竞争解释、政策期间、程序状态和结论边界。</p></article></div></section>'
      + '<section class="m3-section" id="m3-results"><div class="m3-heading"><span>11</span><div><h2>当前账套执行成果</h2><p>最近一次一键分析结果回到方法论门禁中复核，结果数量不等于违法数量。</p></div></div>'
      + latestResultHtml(latest) + '</section>'
      + '<section class="m3-section" id="m3-quality"><div class="m3-heading"><span>12</span><div><h2>质量门禁与受控进化</h2><p>反馈用于发现缺口和提出变更，未经来源核验、正反样本、审批、回归测试和可回退发布，不改变正式方法论。</p></div></div>'
      + '<div class="m3-grid-2"><article><h4>放行控制</h4>' + list(coverage.quality_controls)
      + '</article><article><h4>持续验证</h4>' + list((coverage.known_gaps || []).map(function (item) { return item.priority + '｜' + item.gap + '：' + item.control; }))
      + '</article></div><div class="m3-metrics m3-quality-metrics">'
      + metric(acceptance.passed_scene_count || 0, '已通过结构验收场景', '共' + esc(acceptance.scene_count || 0) + '个')
      + metric(acceptance.failed_scene_count || 0, '未通过场景', '必须为0才允许发布')
      + metric(acceptance.acceptance_case_count || 0, '已执行边界样本', '充分支持、正常解释、限定范围、矛盾、资料不足')
      + metric(acceptance.status || '待执行', '组合验收状态', acceptance.decision_boundary || '')
      + (framework.quality_metrics || []).map(function (item) { return metric(item.target || '持续观测', item.name, item.formula); }).join('')
      + '</div></section></main></div>';
    container.innerHTML = html;

    var requested = window._methodologySection || '';
    window._methodologySection = null;
    var map = {overview:'m3-overview',coverage:'m3-coverage',ledger:'m3-ledger',model:'m3-data-model',validation:'m3-validation',guide:'m3-workflow',files:'m3-workflow',rules:'m3-common',domains:'m3-domains',results:'m3-results',chains:'m3-chains',handbook:'m3-quality'};
    var targetId = map[requested] || requested;
    if (targetId) setTimeout(function () { var node = document.getElementById(targetId); if (node) node.scrollIntoView({behavior:'smooth',block:'start'}); }, 40);
  }

  function methodologyCss() {
    return [
      '.m3-shell{--ink:#1a1a2e;--muted:#5b6b82;--line:#e2e6ed;--soft:#f7f8fa;--brand:#8b2332;--accent:#d4a574;display:flex;align-items:flex-start;gap:28px;width:calc(100% - 28px);max-width:1480px;margin:0 auto;padding:28px 14px 80px;color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;font-size:16px;line-height:1.9}',
      '.m3-nav{position:sticky;top:20px;width:176px;flex:none;padding:22px 0;border-right:1px solid var(--line)}.m3-nav>b{display:block;margin:0 18px 16px;color:var(--brand);font-size:14px;font-weight:800;letter-spacing:.06em}.m3-nav a{display:block;padding:9px 18px;border-left:2px solid transparent;color:#5b6b82;text-decoration:none;font-size:13px;font-weight:500;transition:all .15s}.m3-nav a:hover{border-left-color:var(--brand);color:var(--brand);background:#fdf5f6}',
      '.m3-main{min-width:0;flex:1}.m3-hero{padding:48px 52px 42px;border:1px solid #174b8f;border-radius:16px;background:linear-gradient(135deg,#071f4a 0%,#0b3470 58%,#164b8f 100%);color:#fff;box-shadow:0 16px 36px rgba(7,31,74,.22)}.m3-hero>span{display:block;margin-bottom:8px;color:#bfdbfe;font-size:13px;font-weight:600;letter-spacing:.1em;text-transform:uppercase}.m3-hero h1{max-width:900px;margin:0 0 16px;color:#fff;font-size:34px;line-height:1.35;letter-spacing:-.03em;font-weight:800}.m3-hero p{max-width:1100px;margin:0;color:#dbeafe;font-size:16px;line-height:2.1}.m3-flow{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-top:28px}.m3-flow b{padding:7px 12px;border:1px solid rgba(255,255,255,.24);border-radius:6px;background:rgba(255,255,255,.11);font-size:12px;font-weight:600}.m3-flow i{color:#93c5fd;font-size:14px;font-style:normal;font-weight:700}',
      '.m3-section{scroll-margin-top:22px;margin-top:22px;padding:36px 40px 40px;border:1px solid var(--line);border-radius:14px;background:#fff}.m3-heading{display:flex;align-items:flex-start;gap:16px;margin-bottom:28px;padding-bottom:20px;border-bottom:1px solid var(--line)}.m3-heading>span{display:inline-grid;place-items:center;min-width:36px;height:36px;border-radius:8px;background:#f9eef0;color:var(--brand);font-size:14px;font-weight:800}.m3-heading h2{margin:0;color:var(--ink);font-size:23px;font-weight:700;letter-spacing:-.01em}.m3-heading p{margin:4px 0 0;color:var(--muted);font-size:14px;line-height:1.8}.m3-section h3{margin:30px 0 14px;font-size:18px;font-weight:700}.m3-section h4{margin:0 0 10px;font-size:16px;font-weight:700}.m3-section h5{margin:0 0 8px;font-size:14px;font-weight:700;color:var(--brand)}.m3-section p{margin:6px 0 14px;font-size:16px;line-height:2}',
      '.m3-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:22px}.m3-metric{min-width:0;padding:18px 16px;border:1px solid var(--line);border-radius:10px;background:var(--soft)}.m3-metric strong{display:block;color:var(--brand);font-size:26px;line-height:1.3;font-weight:800}.m3-metric span{display:block;margin-top:6px;font-size:13px;font-weight:700;color:var(--ink)}.m3-metric small{display:block;margin-top:6px;color:var(--muted);font-size:11px;line-height:1.6}.m3-principle{margin:20px 0;padding:18px 20px;border-left:4px solid var(--brand);background:#fdf5f6;border-radius:0 8px 8px 0}.m3-principle>b{display:block;margin-bottom:6px;color:var(--brand);font-size:15px}.m3-principle p{font-size:15px;margin:4px 0;line-height:1.9}',
      '.m3-table-wrap{max-width:100%;overflow:auto;margin:14px 0;border:1px solid var(--line);border-radius:10px}.m3-table-wrap table{width:100%;min-width:720px;border-collapse:collapse;font-size:13px}.m3-table-wrap th{padding:12px 14px;background:var(--soft);color:#475569;text-align:left;white-space:nowrap;font-weight:700;font-size:12px;letter-spacing:.03em}.m3-table-wrap td{padding:12px 14px;border-top:1px solid #eef1f5;vertical-align:top;font-size:13px;line-height:1.8}.m3-table-wrap tr:hover td{background:#fafbfc}',
      '.m3-list{margin:8px 0 16px;padding-left:22px}.m3-list li{margin:6px 0;color:#475569;font-size:15px;line-height:1.9}.m3-muted{color:var(--muted);font-size:14px}.m3-label{margin:12px 0 4px!important;color:var(--brand);font-size:12px;font-weight:800;letter-spacing:.05em;text-transform:uppercase}.m3-boundary{padding:12px 14px;border-radius:6px;background:#f0f4f8;color:#566477;font-size:13px;line-height:1.8}',
      '.m3-canonical,.m3-contract,.m3-scene{margin:12px 0;border:1px solid var(--line);border-radius:10px;background:#fff;transition:box-shadow .15s}.m3-canonical:hover,.m3-contract:hover,.m3-scene:hover{box-shadow:0 2px 8px rgba(0,0,0,.04)}.m3-canonical>summary,.m3-contract>summary,.m3-scene>summary{display:flex;justify-content:space-between;gap:16px;align-items:center;padding:16px 20px;cursor:pointer;list-style:none;font-size:15px}.m3-canonical>summary::-webkit-details-marker,.m3-contract>summary::-webkit-details-marker,.m3-scene>summary::-webkit-details-marker{display:none}.m3-canonical>summary span,.m3-contract>summary span,.m3-scene>summary span{font-weight:700;font-size:15px}.m3-canonical>summary b,.m3-contract>summary b,.m3-scene>summary b{display:inline-block;min-width:72px;margin-right:10px;padding:3px 8px;border-radius:4px;background:#fdf5f6;color:var(--brand);font-size:12px;font-weight:800;letter-spacing:.04em}.m3-canonical>summary em,.m3-contract>summary em,.m3-scene>summary em{color:var(--muted);font-size:12px;font-style:normal;text-align:right}.m3-canonical[open]>summary,.m3-contract[open]>summary,.m3-scene[open]>summary{background:var(--soft);border-bottom:1px solid var(--line)}.m3-canonical-body,.m3-contract-body,.m3-scene-body{padding:24px 22px}.m3-contract{margin:16px 0}.m3-contract>summary{padding:18px 22px;font-size:16px}.m3-contract>summary span{font-size:16px}.m3-contract-note{margin:0 0 18px!important;color:var(--muted);font-size:14px;line-height:1.9}.m3-scene{margin:10px 0}.m3-scene-body>article,.m3-grid-2>article,.m3-grid-3>article{padding:18px 20px;border:1px solid #e8ecf1;border-radius:10px;background:#fff}.m3-target{margin-bottom:16px;padding:16px 20px;border-left:4px solid #2c3a50;background:#f7f8fa;border-radius:0 8px 8px 0}.m3-target b{display:block;margin-bottom:6px;color:var(--brand);font-size:14px}.m3-target p{margin:0;font-size:15px;line-height:1.95;color:var(--ink)}',
      '.m3-grid-2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin:14px 0}.m3-grid-3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.m3-steps{margin:10px 0;padding:0;list-style:none}.m3-steps li{display:grid;grid-template-columns:32px 1fr;gap:4px 10px;padding:11px 0;border-bottom:1px solid #eef1f5}.m3-steps li:last-child{border-bottom:0}.m3-steps li>b{grid-row:1/3;display:grid;place-items:center;width:28px;height:28px;border-radius:50%;background:#f1e4e6;color:var(--brand);font-size:11px;font-weight:800}.m3-steps li>span{color:#334155;font-size:14px;line-height:1.8}.m3-steps li>small{color:var(--muted);font-size:11px;line-height:1.6}',
      '.m3-workflow{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.m3-work{display:flex;gap:14px;padding:18px;border:1px solid var(--line);border-radius:10px}.m3-work>b{flex:none;padding:4px 8px;border-radius:4px;background:#fdf5f6;color:var(--brand);font-size:11px;font-weight:800;letter-spacing:.04em}.m3-work p{color:#475569;font-size:14px;line-height:1.8}.m3-work small,.m3-work em{display:block;color:var(--muted);font-size:11px;font-style:normal;line-height:1.6}.m3-work em{margin-top:6px;color:#43556c;font-weight:600}.m3-domain-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.m3-domain{padding:18px;border:1px solid var(--line);border-radius:10px}.m3-domain>b{padding:3px 8px;border-radius:4px;background:#fdf5f6;color:var(--brand);font-size:10px;font-weight:800;letter-spacing:.04em}.m3-domain p{color:var(--muted);font-size:13px;line-height:1.8}.m3-domain .m3-list{font-size:12px}',
      '.m3-live-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.m3-empty{padding:32px;border:1px dashed #bdc6d1;border-radius:10px;background:var(--soft);text-align:center}.m3-empty p{margin-top:8px;color:var(--muted);font-size:14px}.m3-quality-metrics{grid-template-columns:repeat(4,minmax(0,1fr));margin-top:18px}',
      '@media(max-width:1100px){.m3-metrics{grid-template-columns:repeat(3,minmax(0,1fr))}.m3-domain-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.m3-nav{display:none}.m3-shell{width:calc(100% - 16px);padding:16px 8px 60px;font-size:15px}}',
      '@media(max-width:720px){.m3-hero{padding:30px 22px}.m3-hero h1{font-size:24px}.m3-section{padding:24px 18px}.m3-grid-2,.m3-grid-3,.m3-workflow,.m3-domain-grid,.m3-live-grid{grid-template-columns:1fr}.m3-metrics,.m3-quality-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.m3-canonical>summary,.m3-contract>summary,.m3-scene>summary{display:block}.m3-canonical>summary em,.m3-contract>summary em,.m3-scene>summary em{display:block;margin-top:6px;text-align:left}.m3-shell{font-size:14px}}'
    ].join('');
  }

  window.renderMethodologyPage = function (container) {
    if (!container) return;
    window.currentModule = '稽查方法论';
    container.innerHTML = '<div style="padding:50px;text-align:center;color:#637083">正在装载现行稽查方法论...</div>';
    Promise.all([
      fetch('/api/methodology/coverage?_t=' + Date.now()).then(function (r) { if (!r.ok) throw new Error('覆盖矩阵读取失败'); return r.json(); }),
      fetch('/api/methodology/assets/portfolio?_t=' + Date.now()).then(function (r) { if (!r.ok) throw new Error('行业场景读取失败'); return r.json(); }),
      fetch('/api/methodology/assets/canonical_catalog?_t=' + Date.now()).then(function (r) { if (!r.ok) throw new Error('共同事实目录读取失败'); return r.json(); }),
      fetch('/api/methodology/assets/framework?_t=' + Date.now()).then(function (r) { if (!r.ok) throw new Error('作业框架读取失败'); return r.json(); }),
      fetch('/api/methodology/assets/capability_ledger?_t=' + Date.now()).then(function (r) { if (!r.ok) throw new Error('能力账本读取失败'); return r.json(); }),
      fetch('/api/methodology/assets/canonical_tax_model?_t=' + Date.now()).then(function (r) { if (!r.ok) throw new Error('统一数据模型读取失败'); return r.json(); }),
      fetch('/api/methodology/assets/validation_blueprint?_t=' + Date.now()).then(function (r) { if (!r.ok) throw new Error('独立验证蓝图读取失败'); return r.json(); }),
      (typeof window.getSharedAnalysis === 'function' ? window.getSharedAnalysis().catch(function () { return null; }) : Promise.resolve(null))
    ]).then(function (values) {
      if (!document.body.contains(container)) return;
      renderPage(container, values[0] || {}, values[1] || {}, values[2] || {}, values[3] || {}, values[4] || {}, values[5] || {}, values[6] || {}, values[7]);
    }).catch(function (error) {
      container.innerHTML = '<div style="max-width:900px;margin:40px auto;padding:24px;border:1px solid #fecaca;border-radius:10px;background:#fff7f7;color:#991b1b">稽查方法论读取失败：' + esc(error.message || error) + '</div>';
    });
  };
}());
