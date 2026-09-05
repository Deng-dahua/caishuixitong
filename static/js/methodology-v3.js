/* 2026-09-04 重构：风险检查方法论改为段落式呈现。
 * 核心策略：保留数据形态与可折叠交互（场景库/能力账本是结构化数据不可强行段落化）；
 * 移除"碎片卡片堆砌"——所有章节开头改写为连贯叙述，场景详情内 7~8 个 article 整合
 * 为 4~5 段连贯散文，metric 块改为段落中的嵌入式引用，让方法论页可像专业白皮书一样阅读。
 * 不动后端 API、不动 JSON 数据源、保留所有 CSS 兼容兜底。
 */
(function () {
  'use strict';

  // 加载成功标记——core.js 据此判定现行渲染器是否就绪，禁止回退到旧版渲染器。
  window.__METHODOLOGY_V3_LOADED__ = true;

  function esc(value) {
    if (typeof window.escHtml === 'function') return window.escHtml(String(value == null ? '' : value));
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  // 段落元素的工厂函数。
  function p(html) {
    return '<p>' + html + '</p>';
  }

  function h4(text) {
    return '<h4>' + esc(text) + '</h4>';
  }

  function quoteBox(label, html) {
    return '<aside class="m3-quote"><b>' + esc(label) + '</b><div>' + html + '</div></aside>';
  }

  // 段落中的"嵌入式列表"——与一般 ul 不同：不出现独立卡片化效果，仅在段落中作为补充条目。
  function inlineList(items, className) {
    var values = (items || []).filter(function (item) { return item != null && String(item).trim(); });
    if (!values.length) return '';
    return '<ul class="' + (className || 'm3-inline-list') + '">' + values.map(function (item) {
      return '<li>' + esc(typeof item === 'string' ? item : JSON.stringify(item)) + '</li>';
    }).join('') + '</ul>';
  }

  // 嵌入式 metric——只在段落中以括号引用形式呈现，避免把数据指标孤立成卡片。
  function inlineMetric(value, label) {
    return '<span class="m3-ref"><b>' + esc(value) + '</b>' + esc(label) + '</span>';
  }

  // 账本一致性说明——保留为段尾引用，不孤立成卡片。
  function ledgerConsistencyNote(ledger) {
    var items = (ledger && ledger.items) || [];
    var count = (ledger && ledger.methodology_item_count) || 0;
    if (!items.length && !count) return '暂无登记明细';
    return items.length === count ? '行数一致且无静默状态' : '与明细行数不符（' + items.length + '行），须人工核查';
  }

  // ------------------------------------------------------------------
  // 章节级段落化渲染函数
  // ------------------------------------------------------------------

  // 能力账本——必须保留为表格（242 项结构化数据），但表格放在段落流中，前后用段落串联。
  function capabilityLedgerProse(ledger) {
    ledger = ledger || {};
    var items = ledger.items || [];
    var boundary = ledger.boundary || '能力数量不作为自动风险检查能力的等价物。';
    var counts = ledger.design_status_counts || {};

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

    var intro = p('本账本是方法论对外公开的自我盘点。它逐项声明每一种能力' +
      inlineMetric(ledger.methodology_item_count || 0, '项') +
      '在系统中由人工撰写、由系统执行、由独立案例验证以及是否已正式发布的当前状态。' +
      '账本与详细描述的目的在于明确边界：') +
      p('系统不会用资产数量冒充自动风险检查能力；任何能力在被独立案例验证通过之前，只能被用于产生「待核事实」，不能直接作为「认定结论」使用。' +
        '这一点对所有调用本系统的用户、稽查人员、审理人员均有效，并构成第一道质量门禁。') +
      p('账本当前累计登记 <b>' + esc(ledger.methodology_item_count || 0) + '</b> 项方法，其中' +
        '<b>' + esc(ledger.verified_atomic_rule_count || 0) + '</b> 项已形成「已验证原子规则」、' +
        '<b>' + esc(counts.partial_atomic_support || 0) + '</b> 项具备「部分自动执行支撑」、' +
        '<b>' + esc(ledger.independently_validated_method_count || 0) + '</b> 项已完成独立验证。' +
        '账本说明与明细行数的内部一致性为：' + esc(ledgerConsistencyNote(ledger)) + '。');

    var table = '<details class="m3-fold"><summary><span><b>' + esc(String(ledger.methodology_item_count || 0)) +
      '</b> 项能力逐项查看真实状态</span><em>能力、自动化、验证与发布四个状态独立计数</em></summary>' +
      '<div class="m3-fold-body"><div class="m3-table-wrap"><table>' +
      '<thead><tr><th>编号</th><th>方法或场景</th><th>行业</th><th>类型</th><th>自动化状态</th>' +
      '<th>关联原子规则</th><th>独立验证</th><th>下一步建设</th></tr></thead><tbody>' + rows + '</tbody></table></div>' +
      '<p class="m3-coda">' + esc(boundary) + '</p></div></details>';

    return intro + table;
  }

  // 统一财税数据模型——前段叙述，后附模型清单（结构性元素不可段落化）。
  function canonicalModelProse(model) {
    model = model || {};
    var entities = model.entities || {};
    var formats = Object.keys(model.supported_formats || {}).map(function (ext) {
      return ext.replace('.', '').toUpperCase() + '（' + esc(model.supported_formats[ext]) + '）';
    });
    var entries = Object.keys(entities).map(function (code) {
      var item = entities[code] || {};
      return '<p class="m3-entity-prose"><b class="m3-entity-code">' + esc(code) + '</b>' +
        '<b class="m3-entity-name">' + esc(item.name || '') + '</b>' +
        '核心字段：' + esc((item.required_core_fields || []).join('、') || '按资料内容确认') + '；' +
        '来源类型：' + esc((item.source_types || []).join('、')) + '。</p>';
    }).join('');

    return p('不同银行流水、财务软件导出、税务平台导出、非标准 Excel 与非结构化扫描件，对外来资料而言是异构的；' +
      '对税务稽查而言，它们必须被映射到同一组稳定的财税对象上——身份、期间、交易、往来、资金、发票、税会、文档位置——' +
      '并保留原始来源定位，以便调查核验、复算复盘、外部取证均可回溯到具体文件、具体行、具体字段。') +
      p('本模型现登记 <b>' + esc(Object.keys(entities).length) + '</b> 类核心对象，覆盖' +
        '主体（' + (entities.company ? '已登记' : '未登记') + '）、往来（' + (entities.party ? '已登记' : '未登记') +
        '）、交易（' + (entities.transaction ? '已登记' : '未登记') + '）、税务记录（' + (entities.tax_record ? '已登记' : '未登记') +
        '）等关键域。已支持资料格式共 ' + esc(formats.length) + ' 类，包括' + formats.join('、') + '。') +
      p('统一模型的边界条件：') +
      inlineList(['不依赖任何一家财务软件或一家银行的内部表结构', '保留源文件位置与字段映射，不替用户决定「哪份资料作废」',
        '不支持的资料类型必须显式标记为「解析阻断」，禁止假装无异常']) +
      '<div class="m3-domain-grid">' + entries + '</div>';
  }

  // 独立验证体系——段落化强调"什么样的样本才算数"。
  function validationBlueprintProse(validation) {
    validation = validation || {};
    var stateNames = { supported: '事实支持', rebutted: '反证成立', partial: '部分支持',
      contradictory: '证据矛盾', insufficient: '资料不足' };
    var first = (validation.scene_requirements || [])[0] || {};

    return p('任何一项核查方法、任何一个行业场景、任何一条原子规则，在正式发布之前都必须经过独立案例验证。' +
      '本系统将验证区分为四层：场景层（适用与不适用边界）、格式层（资料能被解析且字段完整）、组合层（多资料场景下链路完整）、' +
      '原子层（单条规则在真实资料上得到正确结果）。只有四层全部独立验证通过，才允许被登记到能力账本中。') +
      p('当前累计登记 <b>' + esc(validation.industry_contract_count || 0) + '</b> 类行业与叠加模式、' +
        '<b>' + esc(validation.scene_count || 0) + '</b> 个必须独立验证的场景、' +
        '<b>' + esc(validation.required_validation_cells || 0) + '</b> 个分层必验单元。每一个场景至少要有' +
        esc(first.minimum_independent_cases || 10) + ' 例独立案例，' +
        '并覆盖「' + ((first.required_evidence_states || []).map(function (x) { return stateNames[x] || x; }).join('、')) +
        '」五类证据状态中的每一类。') +
      p('什么样的样本才算数。') +
      inlineList(['样本必须使用真实企业资料，禁止用文字样例替代实测',
        '每个场景至少 3 例风险正样本 + 3 例正常负样本，正反比例必须可比',
        '单资料、双资料、多资料部分链、完整链、关键资料缺失、资料冲突、无可用资料均须独立验证',
        '样例验收必须区分「文字描述能跑」与「独立资料能跑」，不可合并解释为「通过」']) +
      '<p class="m3-coda">' + esc(validation.boundary || '') + '</p>';
  }

  // 行业场景合同内的"场景"——7~8 个 article 整合为 4~5 段连贯叙述。这是本次重构最大改动。
  function scenarioProse(scene) {
    if (!scene) return '';
    var doubt = scene.doubt || {};
    var clue = scene.clue_chain || {};
    var evidence = scene.evidence_chain || {};
    var analysis = scene.analysis_chain || {};
    var domains = scene.domain_collaboration || {};
    var report = scene.report_contract || {};
    var policy = scene.policy_applicability || {};
    var steps = (clue.steps || []);
    var alts = (analysis.alternatives || doubt.must_exclude || doubt.reasonable_explanations || []);
    var acceptanceItems = (scene.acceptance_cases || []).map(function (item) {
      return '<tr><td>' + esc(item.case || '') + '</td><td>' + esc(item.facts || '') +
        '</td><td>' + esc(item.expected || '') + '</td></tr>';
    }).join('');

    var applicability = scene.applicability || {};
    var partners = (domains.partners || []).map(function (partner) {
      return partner.domain + '（' + partner.responsibility + '；交付：' + partner.handoff + '）';
    });
    var reportMust = (report.must_state || []);
    var reportForbidden = (report.forbidden || []);

    // 段一：场景定位——一句话说清"这是在查什么"。
    var para1 = p(
      h4('场景定位') +
      '本场景针对的是「' + esc(doubt.target_fact || scene.name || '') + '」。' +
      '系统把企业资料里的相关信号拆解为待证事实，下一步的工作是把待证事实拆解为可核验的调查线索、可取得的证据材料、可论证的法律要件。' +
      '适用条件是：' + ((applicability.apply_when || []).join('；') || '按实际经营活动认定') + '；' +
      '不应被使用或应停止核验的情况是：' + ((applicability.do_not_apply_when || []).join('；') || '资料明显不属于该场景对应的事实范围') + '。');

    // 段二：调查与证据——这是核心操作层。
    var stepsHtml = steps.length
      ? steps.map(function (s) { return esc(s.step) + '：' + esc(s.action) + '（交付：' + esc(s.deliverable || '—') + '）'; }).join('；')
      : '未登记调查步骤，须在执行前补全';
    var para2 = p(
      h4('调查步骤与证据要求') +
      '调查沿以下链路推进：' + stepsHtml + '。线索链的终点状态是：' + esc(clue.terminal || '资料就位') + '。') +
      p('支持证据通常来源于：' + ((evidence.supporting_sources || []).join('；') || '按资料取得') +
        '；反向证据与可能推翻本假设的合理解释则需要：' + ((evidence.opposing_sources || []).join('；') || '资料中可见的反向陈述') +
        '。下列情况应停止核验（避免证据不足被误判）：' + ((evidence.insufficient_when || []).join('；') || '资料缺失或与场景无关') +
        '；证据质量须复核：' + ((evidence.quality_checks || []).join('；') || '三性、来源独立性、完整性') + '。');

    // 段三：分析与政策——这是论证层。
    var para3 = p(
      h4('分析论证与政策期间') +
      '核心命题是：' + esc(analysis.proposition || '待证据取得后给出') + '。' +
      '论证按以下顺序展开：' + ((analysis.reasoning || []).join('；') || '事实复算—>会计处理—>税法要件—>程序核验') + '。' +
      '税法边界：' + esc(analysis.tax_boundary || '按最新法规与本系统登记的政策期间判断') + '。') +
      p('政策期间核验须先确认：' + ((policy.required_dimensions || []).join('；') || '政策文号、适用范围、生效与废止日期') +
        '。下列情况应停止使用该政策依据：' + ((policy.stop_if || []).join('；') || '已废止、不适用本案、要件不全') +
        '。本场景的「政策使用边界」表述为：' + esc(policy.output_boundary || '依证据闭合度判定') + '。');

    // 段四：业务域协同与报告移交——这是协作层。
    var para4 = p(
      h4('业务域协同与报告移交') +
      '本场景由「' + esc(domains.lead || '主调查业务域') + '」牵头，下列业务域协同参与：' +
      (partners.join('；') || '未登记协同业务域') + '。' +
      '多域结论冲突时回到原始资料与实际履行，不以多数表决或系统评分裁决。冲突规则：' +
      esc(domains.conflict_rule || '回到原始资料与原始证据') + '。') +
      p('报告移交必须写明：' + (reportMust.join('；') || '事实、证据、依据、限制') +
        '；禁止的写法是：' + (reportForbidden.join('；') || '口径不清、把待证事实描述为认定结论') + '。');

    // 可选：边界验证样本（结构化表格保留）。
    var acceptanceTable = acceptanceItems
      ? '<details class="m3-fold"><summary><span>查看五类证据状态验收' +
        '（共 ' + esc(String((scene.acceptance_cases || []).length)) + ' 例）</span>' +
        '<em>证据状态/事实/输出上限</em></summary>' +
        '<div class="m3-fold-body"><div class="m3-table-wrap"><table>' +
        '<thead><tr><th>证据状态</th><th>场景化事实</th><th>输出上限</th></tr></thead><tbody>' +
        acceptanceItems + '</tbody></table></div></div></details>'
      : '';

    return para1 + para2 + para3 + para4 + acceptanceTable;
  }

  // 行业场景合同——保留折叠（场景库必须可查），但场景内已段落化。
  function contractProse(contract) {
    contract = contract || {};
    var scenes = contract.scenarios || [];
    var clueDepths = [];
    var caseDepths = [];
    scenes.forEach(function (scene) {
      var cd = ((scene.clue_chain || {}).steps || []).length;
      if (clueDepths.indexOf(cd) < 0) clueDepths.push(cd);
      var vd = (scene.validation_cases || []).length;
      if (caseDepths.indexOf(vd) < 0) caseDepths.push(vd);
    });
    clueDepths.sort(function (a, b) { return a - b; });
    caseDepths.sort(function (a, b) { return a - b; });

    return '<details class="m3-fold"><summary><span><b>' + esc(contract.code) + '</b> ' +
      esc(contract.name || '') + '</span><em>' + scenes.length + ' 个场景 · 调查步骤深度 ' +
      esc(clueDepths.join('、') || '未登记') + ' · 边界样本深度 ' + esc(caseDepths.join('、') || '未登记') +
      '</em></summary><div class="m3-fold-body">' +
      p('<b>本合同的总体定位。</b>' + esc(contract.positioning || '')) +
      scenes.map(function (s) {
        return '<section class="m3-scene"><h5 class="m3-scene-title"><b>' + esc(s.id) + '</b>' +
          '<span>' + esc(s.name || '') + '</span></h5>' + scenarioProse(s) + '</section>';
      }).join('') +
      '</div></details>';
  }

  // 跨行业共同事实模块——段落+折叠场景保留。
  function canonicalModuleProse(module) {
    module = module || {};
    var rules = module.rules || [];

    return p(esc(module.purpose || '')) +
      '<details class="m3-fold m3-canonical"><summary><span><b>' + esc(module.id) + '</b> ' +
      esc(module.name || '') + '</span><em>' + esc(rules.length) + ' 项事实规则 · ' +
      esc((module.clue_paths || []).length) + ' 类调查路径</em></summary>' +
      '<div class="m3-fold-body">' +
      p('<b>启动门槛。</b>' + inlineList(module.activation_gate || [])) +
      p('<b>可证伪事实规则。</b>每条规则都有一个清晰的"如果在该条件下观察到该事实，则触发核查"的假设结构。' +
        '规则不在被满足时说明资料不真实，而在被违反时说明场景需要展开：' +
        inlineList(rules.map(function (rule) { return rule.id + '｜' + rule.fact_hypothesis; }))) +
      p('<b>分析检验与报告边界。</b>' + inlineList(module.analysis_tests || []) +
        '。报告边界：' + esc(module.report_boundary || '须待证据闭合后形成结论')) +
      '</div></details>';
  }

  // 当前账套执行成果——把 8 个孤独 metric 改写为段落叙述+关键观测表。
  function latestResultProse(data) {
    if (!data || data.ok === false) {
      return '<aside class="m3-empty"><b>当前账套尚无可复核的执行快照</b>' +
        '<p>没有执行记录、资料不足、规则未激活和执行后未发现异常是不同状态，' +
        '不能合并解释为「无风险」。请先完成资料上传与一键分析，再回到本页复核。</p></aside>';
    }
    var report = data.report && typeof data.report === 'object' ? data.report : data;
    var findings = report.all_findings || report.findings || [];
    var scenario = report.scenario_methodology || {};
    var ledger = report.capability_ledger || {};
    var canonical = report.canonical_tax_data || {};
    var adaptation = report.document_combination_adaptation || canonical.document_combination_adaptation || {};
    var validation = report.universal_validation || {};
    var currentValidation = validation.current_scope || {};

    var metrics = [
      [findings.length, '待复核事项（不等于违法事实）'],
      [scenario.scene_count || 0, '已选择场景（' + (scenario.industry_name || '按实际经营匹配') + '）'],
      [scenario.ready_for_human_review || 0, '资料就绪（仍须人工核验）'],
      [scenario.pending_more_sources || 0, '待补资料（缺失不推定违法）'],
      [ledger.methodology_item_count || 0, '账本已登记（' + ledgerConsistencyNote(ledger) + '）'],
      [canonical.canonical_record_count || 0, '标准财税记录（来自本轮全部已解析资料）'],
      [adaptation.unresolved_document_count || 0, '资料适配待处理（逐份说明原因与下一步）'],
      [validation.qualified_independent_case_count || 0, '合格独立验证样本（' +
        (currentValidation.release_ready ? '当前范围验证通过' : '当前范围不得正式发布') + '）']
    ];
    var metricList = metrics.map(function (m) {
      return '<li><b>' + esc(m[0]) + '</b><span>' + esc(m[1]) + '</span></li>';
    }).join('');

    var opening = p('最近一次一键分析的结果回到方法论门禁中复核。本页不是「结论页」，' +
      '而是「可核验状态页」——每一个数字都对应一类口径，必须区分「没有执行」「正在执行」「执行后未发现」「资料不足」等不同状态。');
    var meta = '<ul class="m3-obs">' + metricList + '</ul>';
    var closing = p('独立验证门禁当前状态：' +
      (currentValidation.blockers || []).length
        ? inlineList(currentValidation.blockers)
        : '当前范围内没有阻断项，但「没有阻断」不等于「可发布」，需结合独立验证通过率共同判断。');
    return opening + meta + closing;
  }

  // ------------------------------------------------------------------
  // 章节级段落化组装：12 个章节统一为 "段落叙述 + 嵌入元素" 风格
  // ------------------------------------------------------------------

  function renderPage(container, coverage, portfolio, catalog, framework, ledger, canonicalModel, validationBlueprint, latest) {
    var inventory = coverage.inventory || {};
    var acceptance = coverage.acceptance || {};
    var contracts = portfolio.contracts || [];
    var industries = contracts.filter(function (item) { return /^[A-T]$/.test(item.code || ''); });
    var overlays = contracts.filter(function (item) { return String(item.code || '').indexOf('OVERLAY-') === 0; });

    var taxRows = (framework.tax_coverage || []).map(function (group) {
      return '<tr><td>' + esc(group.group || '') + '</td><td>' + esc((group.items || []).join('、')) +
        '</td><td>' + esc(group.focus || '') + '</td></tr>';
    }).join('');
    var industryRows = contracts.map(function (item) {
      var scenes = item.scenarios || [];
      var clueDepths = [];
      var caseDepths = [];
      scenes.forEach(function (scene) {
        var cd = ((scene.clue_chain || {}).steps || []).length;
        if (clueDepths.indexOf(cd) < 0) clueDepths.push(cd);
        var vd = (scene.validation_cases || []).length;
        if (caseDepths.indexOf(vd) < 0) caseDepths.push(vd);
      });
      return '<tr><td>' + esc(item.code) + '</td><td>' + esc(item.name || '') + '</td>' +
        '<td>' + scenes.length + '</td>' +
        '<td>' + esc(clueDepths.sort(function (a, b) { return a - b; }).join('、') || '未登记') + '</td>' +
        '<td>' + esc(caseDepths.sort(function (a, b) { return a - b; }).join('、') || '未登记') + '</td></tr>';
    }).join('');

    var html = '<style>' + methodologyCss() + '</style>' +
      '<aside class="m3-nav">' +
      '<b>风险检查方法论</b>' +
      [['m3-overview', '前言'], ['m3-coverage', '覆盖体系'], ['m3-ledger', '能力账本'],
       ['m3-data-model', '数据模型'], ['m3-validation', '独立验证'],
       ['m3-common', '共同事实'], ['m3-industries', '行业场景'],
       ['m3-workflow', '作业规程'], ['m3-domains', '业务域协同'],
       ['m3-chains', '链路与证据'], ['m3-report', '报告移交'],
       ['m3-results', '执行成果'], ['m3-quality', '质量与进化']
      ].map(function (item) {
        return '<a href="#' + item[0] + '">' + item[1] + '</a>';
      }).join('') +
      '</aside>' +
      '<article class="m3-prose">' +
        // 前言
        '<section id="m3-overview">' +
          p('<b>本方法的来源与适用边界。</b>' + esc(portfolio.positioning ||
            '本系统的方法论源自税务稽查一线工作经验与公开稽查规范，结合金融、税法与会计领域的方法论汇编而成。' +
            '它不替代有权人员的法定职责，而是为有权人员提供可复核的待核事实、调查路径与证据组织结构。')) +
          p('从资料进入到报告移交，本系统的工作沿固定链路展开：<b>资料准入 → 经营画像 → 事实规则 → 调查核验 → ' +
            '证据组织 → 分析论证 → 人工审理 → 报告移交</b>。每一个阶段都设有启动门槛、停止条件与可审计交付物；' +
            '任何一阶段未达门槛即停止并补件，不可跨越。') +
          p('<small>现行方法论版本 ' + esc(portfolio.version || '') + '。' +
            '本页内容由系统从权威方法论目录、行业场景合同、统一数据模型、独立验证蓝图、能力账本与执行结果汇总生成，' +
            '并随方法论变更而自动更新。</small>') +
        '</section>' +

        // 01 覆盖体系
        '<section id="m3-coverage">' +
          p('<b>覆盖的范围与边界。</b>覆盖体系由三层组成：' +
            '跨行业共同事实（用于一切企业的通用底座）、行业场景合同（按实际经营活动选择）、' +
            '叠加业务层（平台、跨境、集团关联等特殊情形）。' +
            '数量不是越多越好，而是必须按真实业务需要决定——任何一项方法在被独立案例验证之前都不进入正式覆盖。') +
          p('当前登记：跨行业共同事实 <b>' + esc(inventory.canonical_rules || 0) + '</b> 项、' +
            '完整行业场景 <b>' + esc(inventory.industry_scenarios || 0) + '</b> 个、' +
            '行业门类 <b>' + esc(industries.length) + '</b> 个、' +
            '叠加业务层 <b>' + esc(overlays.length) + '</b> 个、' +
            '调查路径 <b>' + esc(inventory.clue_paths || 0) + '</b> 类、' +
            '证据方案 <b>' + esc(inventory.evidence_plans || 0) + '</b> 类、' +
            '证据状态验收 <b>' + esc(acceptance.acceptance_case_count || 0) + '</b> 例。') +
          p('数量原则是：' + esc(portfolio.count_policy || '') + '。') +
          '<h4>税费事项覆盖</h4>' +
          '<div class="m3-table-wrap"><table>' +
          '<thead><tr><th>税费组</th><th>覆盖事项</th><th>核验重点</th></tr></thead><tbody>' + taxRows + '</tbody></table></div>' +
          '<h4>行业与叠加业务覆盖</h4>' +
          '<div class="m3-table-wrap"><table>' +
          '<thead><tr><th>代码</th><th>合同</th><th>场景</th><th>调查深度</th><th>边界样本深度</th></tr></thead><tbody>' +
          industryRows + '</tbody></table></div>' +
        '</section>' +

        // 02 能力账本
        '<section id="m3-ledger">' + capabilityLedgerProse(ledger) + '</section>' +

        // 03 数据模型
        '<section id="m3-data-model">' + canonicalModelProse(canonicalModel) + '</section>' +

        // 04 独立验证
        '<section id="m3-validation">' + validationBlueprintProse(validationBlueprint) + '</section>' +

        // 05 共同事实
        '<section id="m3-common">' +
          p('<b>为什么先做共同事实。</b>本系统处理的稽查工作，首先不是「找出风险」，而是先把一切企业都会涉及的身份、期间、' +
            '资料、交易、资金、发票、税会与程序性问题解决掉，再叠加行业经营事实。' +
            '这样做的好处是：把绝大多数通用异常在第一阶段识别，企业特定场景只在剩余空间内展开。') +
          (catalog.modules || []).map(canonicalModuleProse).join('') +
        '</section>' +

        // 06 行业场景（标识符保留为「全行业完整场景合同」以便前后端契约对齐）
        '<section id="m3-industries">' +
          p('<b>本节（标识符：全行业完整场景合同）说明行业场景的展开原则。</b>' +
            '每个行业的真实业务都有自身的常态（季节、人员、产能、客户类型）。' +
            '本节提供的是「场景合同」——一组按场景拆解的调查与证据要求，而不是按企业拆解的固定清单。' +
            '在执行时按企业实际经营活动匹配场景、按匹配场景展开调查路径。' +
            '下列合同涵盖 <b>' + esc(industries.length) + '</b> 个行业门类与 <b>' + esc(overlays.length) + '</b> 个叠加业务层，' +
            '每个场景在本节完整呈现适用边界、调查路径、支持与反向证据、分析论证、政策期间、业务域协同和报告要求。') +
          contracts.map(contractProse).join('') +
        '</section>' +

        // 07 作业规程
        '<section id="m3-workflow">' +
          p('<b>作业规程的启动与放行。</b>全流程沿资料准入 → 经营画像 → 事实规则 → 调查核验 → ' +
            '证据组织 → 分析论证 → 人工审理 → 报告移交这八步推进，每一步都设有启动条件、停止条件与可审计交付。' +
            '系统不允许跨越资料、证据和程序门槛——任何一步未达交付标准，下一步不能启动。') +
          p((framework.workflow || []).map(function (step) {
            return '<b>' + esc(step.id) + ' ' + esc(step.name || '') + '。</b>' +
              '目标：' + esc(step.objective || '') +
              '。启动门槛：' + esc(step.gate || '') +
              '。交付：' + esc(step.output || '') + '。';
          }).join('　')) +
        '</section>' +

        // 08 业务域协同
        '<section id="m3-domains">' +
          p('<b>多业务域协同的工作模型。</b>不同业务域围绕同一「待证事实」协同，' +
            '而不是各管一摊、独立出报告。当多域结论出现冲突时，回到原始资料与实际履行进行比对，' +
            '不以多数表决、不以系统评分裁决、不以先入为主的口径压制相反意见。') +
          p((framework.business_domains || []).map(function (domain) {
            return '<b>' + esc(domain.id) + ' ' + esc(domain.name || '') + '。</b>' +
              esc(domain.scope || '') +
              '主要输出：' + ((domain.key_outputs || []).join('；') || '按场景需要列出');
          }).join('　')) +
        '</section>' +

        // 09 链路与证据
        '<section id="m3-chains">' +
          p('<b>调查链、证据链与分析链是一体化结构。</b>它们不是相互独立的清单，' +
            '而是同一「待证事实」从发现、核验、证明到论证的连续记录。调查链只决定「怎样查」，' +
            '证据链只说明「事实能否被证明」，分析链只论证「事实意味着什么」。') +
          p('调查链须给出：' + inlineList(((framework.chain_contracts || {}).clue || {}).required_fields) +
            '。证据链须给出：' + inlineList(((framework.chain_contracts || {}).evidence || {}).required_fields) +
            '。分析链须给出：' + inlineList(((framework.chain_contracts || {}).analysis || {}).required_fields) + '。') +
          p('<b>证据原则。</b>' + inlineList((framework.evidence_model || {}).rules)) +
        '</section>' +

        // 10 报告移交
        '<section id="m3-report">' +
          p('<b>报告移交接口的边界。</b>方法论只向报告编制移交通过门禁的事实、证据、测算、依据、限制和人工复核记录。' +
            '不能移交的：评分（不应作为结论）、未经独立验证的假设、口径不清的口径选择、未经核验的"经验"。') +
          p('<b>事实包</b>交给报告时，须写明主体、事项、期间、业务主键、原始来源、事实时间线、差异复算与未取得资料；' +
            '<b>证据包</b>须写明证明对象、支持与反向证据、取得方式、证据三性、来源谱系、矛盾处理与证据成熟度；' +
            '<b>专业复核包</b>须写明会计处理、税费要件、金额底稿、竞争解释、政策期间、程序状态与结论边界。') +
        '</section>' +

        // 11 执行成果
        '<section id="m3-results">' + latestResultProse(latest) + '</section>' +

        // 12 质量与进化
        '<section id="m3-quality">' +
          p('<b>放行控制。</b>反馈用于发现缺口与提出变更；' +
            '没有经过来源核验、正反样本覆盖、审批流程、回归测试与可回退发布的变更，不进入正式方法论。' +
            '本系统对放行有下列硬性约束：' +
            inlineList(coverage.quality_controls || []) + '。') +
          p('<b>持续验证与已知缺口。</b>' + inlineList((coverage.known_gaps || []).map(function (item) {
            return item.priority + '｜' + item.gap + '（控制：' + item.control + '）';
          }))) +
          p('当前验收状态汇总：' +
            '通过结构验收场景 <b>' + esc(acceptance.passed_scene_count || 0) + '</b> / ' + esc(acceptance.scene_count || 0) + '、' +
            '未通过场景 <b>' + esc(acceptance.failed_scene_count || 0) + '</b>（必须为 0 才允许发布）、' +
            '已执行边界样本 <b>' + esc(acceptance.acceptance_case_count || 0) + '</b> 例、' +
            '组合验收状态 <b>' + esc(acceptance.status || '待执行') + '</b>——' +
            esc(acceptance.decision_boundary || '') + '。') +
          ((framework.quality_metrics || []).length
            ? p('<b>持续观测指标。</b>' + ((framework.quality_metrics || []).map(function (item) {
                return esc(item.name) + '（目标：' + esc(item.target || '持续观测') +
                  '；公式：' + esc(item.formula || '—') + '）';
              }).join('；')))
            : '') +
        '</section>' +
      '</article>';

    container.innerHTML = html;

    var requested = window._methodologySection || '';
    window._methodologySection = null;
    var map = { overview: 'm3-overview', coverage: 'm3-coverage', ledger: 'm3-ledger',
      model: 'm3-data-model', validation: 'm3-validation', guide: 'm3-workflow',
      files: 'm3-workflow', rules: 'm3-common', domains: 'm3-domains',
      results: 'm3-results', chains: 'm3-chains', handbook: 'm3-quality' };
    var targetId = map[requested] || requested;
    if (targetId) setTimeout(function () {
      var node = document.getElementById(targetId);
      if (node) node.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 40);
  }

  // ------------------------------------------------------------------
  // 段落式 CSS——衬线字体、专业白皮书风格。
  // ------------------------------------------------------------------

  function methodologyCss() {
    return [
      // ── 页面整体：米白底、居中阅读栏、大方留白 ──
      '.m3-shell{--ink:#1f2430;--muted:#5c6675;--line:#e3e7ee;--soft:#f6f7f9;--brand:#8b2332;--accent:#b98a5a;display:flex;align-items:flex-start;gap:40px;width:calc(100% - 28px);max-width:1440px;margin:0 auto;padding:30px 14px 56px;color:var(--ink);background:#faf9f6;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;font-size:15px;line-height:1.6}',
      // ── 侧边导航：清爽、字大一级 ──
      '.m3-nav{position:sticky;top:24px;width:188px;flex:none;padding:24px 0;border-right:1px solid var(--line)}',
      '.m3-nav>b{display:block;margin:0 20px 16px;color:var(--brand);font-size:15px;font-weight:800;letter-spacing:.08em}',
      '.m3-nav a{display:block;padding:9px 20px;border-left:3px solid transparent;color:#5c6675;text-decoration:none;font-size:15px;font-weight:500;transition:all .15s}',
      '.m3-nav a:hover{border-left-color:var(--brand);color:var(--brand);background:#fdf5f6}',
      // ── 正文阅读区：白底居中、宽松内边距 ──
      '.m3-prose{min-width:0;flex:1;max-width:1200px;margin:0 auto;background:#fff;padding:36px 48px 48px;border:1px solid var(--line);border-radius:16px;box-shadow:0 8px 32px rgba(7,31,74,.05)}',
      '.m3-prose section{margin:0 0 44px;padding-bottom:26px;border-bottom:1px solid var(--line)}',
      '.m3-prose section:last-child{border-bottom:0;margin-bottom:0}',
      // ── 章节大标题：层级第一级 ──
      '.m3-prose h2{font-size:15px;font-weight:800;color:var(--ink);margin:0 0 18px;padding-bottom:10px;border-bottom:2px solid var(--brand);letter-spacing:.02em}',
      '.m3-prose h2 small{display:block;margin-top:5px;font-size:15px;font-weight:500;color:var(--muted);letter-spacing:0}',
      // ── 小节标题：层级第二级 ──
      '.m3-prose h4{margin:22px 0 12px;padding-left:14px;border-left:3px solid var(--brand);font-size:15px;font-weight:700;color:var(--brand)}',
      '.m3-prose h5.m3-scene-title{margin:0 0 12px;padding:0 0 8px;border-bottom:1px solid var(--line);font-size:15px;font-weight:700;color:var(--ink);display:flex;align-items:baseline;gap:12px;text-indent:0}',
      '.m3-prose h5.m3-scene-title b{padding:2px 8px;border-radius:4px;background:#fdf5f6;color:var(--brand);font-size:15px;font-weight:800;letter-spacing:.05em}',
      '.m3-prose h5.m3-scene-title span{flex:1;line-height:1.6}',
      // ── 正文段落：首行缩进、两端对齐 ──
      '.m3-prose p{margin:0 0 10px;font-size:15px;line-height:1.6;color:#242b3a;text-align:justify;text-justify:inter-ideograph;text-indent:2em}',
      '.m3-prose p:first-child{text-indent:0}',
      '.m3-prose p b{color:#8b2332;font-weight:700}',
      // ── 段落式实体（原实体卡改段落）：编号+名称+描述连续成段 ──
      '.m3-prose p.m3-entity-prose{margin:0 0 10px;padding:0 0 12px;border-bottom:1px dashed var(--line);font-size:15px;line-height:1.6;text-indent:0}',
      '.m3-prose .m3-entity-code{display:inline-block;min-width:80px;margin-right:8px;padding:2px 8px;border-radius:4px;background:var(--soft);color:var(--brand);font-size:15px;font-weight:800;text-align:center}',
      '.m3-prose .m3-entity-name{margin-right:8px;font-size:15px;color:var(--ink)}',
      // ── 嵌入式引用指标 ──
      '.m3-prose .m3-ref{display:inline-block;margin:0 3px;padding:1px 9px;border:1px solid var(--line);border-radius:14px;background:var(--soft);font-size:15px;line-height:1.6;color:#3a4561}',
      '.m3-prose .m3-ref>b{margin-right:5px;color:var(--brand);font-weight:800;font-size:15px}',
      // ── 嵌入式列表：段落内要点 ──
      '.m3-prose .m3-inline-list{margin:8px 0 16px 24px;padding:0;text-indent:0}',
      '.m3-prose .m3-inline-list li{position:relative;margin:6px 0;font-size:15px;line-height:1.6;color:#39404f;list-style:none}',
      '.m3-prose .m3-inline-list li:before{content:"·";position:absolute;left:-16px;color:var(--brand);font-weight:800}',
      // ── 引用盒：原则/边界陈述 ──
      '.m3-prose .m3-quote,.m3-prose .m3-coda{margin:16px 0 20px;padding:12px 20px;border-left:3px solid var(--brand);background:#fdf5f6;border-radius:0 8px 8px 0;font-size:15px;line-height:1.6;color:#3d4659;text-indent:0}',
      '.m3-prose .m3-quote>b{display:block;margin-bottom:6px;color:var(--brand);font-size:15px;font-weight:800;letter-spacing:.06em}',
      // ── 表格：自适应宽度、字号适中 ──
      '.m3-prose .m3-table-wrap{max-width:100%;overflow:auto;margin:16px 0 24px;border:1px solid var(--line);border-radius:12px;text-indent:0}',
      '.m3-prose .m3-table-wrap table{width:100%;border-collapse:collapse;font-size:15px}',
      '.m3-prose .m3-table-wrap th{padding:10px 14px;background:var(--soft);color:#475569;text-align:left;font-weight:700;font-size:15px;letter-spacing:.03em}',
      '.m3-prose .m3-table-wrap td{padding:10px 14px;border-top:1px solid #eef1f5;vertical-align:top;font-size:15px;line-height:1.6}',
      '.m3-prose .m3-table-wrap tr:hover td{background:#fafbfc}',
      // ── 折叠容器：素净可查（场景库/能力账本） ──
      '.m3-prose .m3-fold{margin:22px 0;border:1px solid var(--line);border-radius:12px;background:#fbfaf7;text-indent:0}',
      '.m3-prose .m3-fold>summary{display:flex;justify-content:space-between;gap:14px;align-items:center;padding:12px 20px;cursor:pointer;list-style:none;font-size:15px;font-weight:600;color:var(--ink)}',
      '.m3-prose .m3-fold>summary::-webkit-details-marker{display:none}',
      '.m3-prose .m3-fold>summary b{display:inline-block;min-width:60px;margin-right:10px;padding:2px 8px;border-radius:4px;background:#fdf5f6;color:var(--brand);font-size:15px;font-weight:800;letter-spacing:.05em;text-align:center}',
      '.m3-prose .m3-fold>summary em{color:var(--muted);font-size:15px;font-style:normal;text-align:right}',
      '.m3-prose .m3-fold[open]>summary{background:#fff;border-bottom:1px solid var(--line)}',
      '.m3-prose .m3-fold-body{padding:16px 22px}',
      // ── 场景：纯段落流（无边框无卡片感） ──
      '.m3-prose .m3-scene{margin:0 0 22px;padding:0;text-indent:0}',
      '.m3-prose .m3-scene p{margin:0 0 10px;font-size:15px;line-height:1.6;text-align:justify}',
      '.m3-prose .m3-scene p:first-child{text-indent:0}',
      // ── 数据模型容器：单列段落流 ──
      '.m3-prose .m3-domain-grid{display:block;margin:14px 0}',
      // ── 执行成果观测：段落式列表（去边框背景） ──
      '.m3-prose .m3-obs{margin:16px 0 26px;padding:0;list-style:none;text-indent:0}',
      '.m3-prose .m3-obs li{display:flex;align-items:baseline;gap:12px;padding:9px 0;border-bottom:1px dashed var(--line);font-size:15px;color:#39404f}',
      '.m3-prose .m3-obs li:last-child{border-bottom:0}',
      '.m3-prose .m3-obs li>b{flex:none;color:var(--brand);font-size:15px;font-weight:800;min-width:64px;text-align:right}',
      '.m3-prose .m3-obs li>span{flex:1;line-height:1.6}',
      // ── 空状态 ──
      '.m3-prose .m3-empty{margin:20px 0;padding:36px;border:1px dashed #bdc6d1;border-radius:12px;background:#fbfaf7;text-align:center;text-indent:0}',
      '.m3-prose .m3-empty p{margin:8px 0 0;color:var(--muted);font-size:15px;text-align:center;text-indent:0}',
      // ── 响应式 ──
      '@media(max-width:1100px){.m3-nav{display:none}.m3-prose{padding:28px 30px}}',
      '@media(max-width:720px){.m3-prose{padding:22px 18px;font-size:15px}.m3-prose section{margin-bottom:36px;padding-bottom:22px}.m3-prose p{font-size:15px;text-indent:0}.m3-prose .m3-fold>summary{display:block}.m3-prose .m3-fold>summary em{display:block;margin-top:8px;text-align:left}}'
    ].join('');
  }

  // 暴露关键函数用于 Node 端单元测试（浏览器侧无副作用）。
  // 不接受运行时不存在的环境，保持浏览器侧与 Node 侧行为一致。
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      p: p, h4: h4, quoteBox: quoteBox, esc: esc, inlineList: inlineList,
      capabilityLedgerProse: capabilityLedgerProse, canonicalModelProse: canonicalModelProse,
      validationBlueprintProse: validationBlueprintProse, scenarioProse: scenarioProse,
      contractProse: contractProse, canonicalModuleProse: canonicalModuleProse,
      latestResultProse: latestResultProse
    };
  }

  window.renderMethodologyPage = function (container) {
    if (!container) return;
    window.currentModule = '风险检查方法论';
    container.innerHTML = '<div style="padding:50px;text-align:center;color:#637083">正在装载现行风险检查方法论...</div>';
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
      renderPage(container, values[0] || {}, values[1] || {}, values[2] || {},
        values[3] || {}, values[4] || {}, values[5] || {}, values[6] || {}, values[7]);
    }).catch(function (error) {
      container.innerHTML = '<div style="max-width:900px;margin:40px auto;padding:24px;border:1px solid #fecaca;border-radius:10px;background:#fff7f7;color:#991b1b">风险检查方法论读取失败：' + esc(error.message || error) + '</div>';
    });
  };
}());
