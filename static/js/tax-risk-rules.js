// ==================== 稽查指令页面 ====================
var taxRiskRulesData = [];
var _triggeredRuleFindings = {};  // rule_id → [finding, ...] 触发溯源

var RISK_LEVEL_COLORS = {
  '高风险': '#dc2626', '中风险': '#f59e0b', '低风险': '#3b82f6', '良好': '#10b981'
};
var RISK_LEVEL_ICONS = {
  '高风险': '🔴', '中风险': '🟡', '低风险': '🔵', '良好': '🟢'
};

// 分类描述
var CATEGORY_DESCRIPTIONS = {
  '资金流': '资金流向追踪、收款来源分析、付款方身份核实、异常交易检测。银行流水是稽查的第一切入资料。',
  '进销存': '进销品名交叉映射、进销比分析、有进无销/有销无进诊断、BOM加工链条验证、存货周转预警。',
  '发票流': '发票合规检查、税率异常、红冲作废追踪、发票生命周期监控、进销发票深度特征分析。',
  '经营实质': '企业是否具备真实经营条件——经营费用/仓储/物流/人员/产能。全链条经营实质地理分析。',
  '资料完备': '14类稽查必查资料逐项检测，合同需求四层自动分层，缺失资料标注风险等级。',
  '税务合规': '增值税/企业所得税/个税/印花税/城建税等各税种申报与实际数据比对验证。',
  '财务数据': '科目余额、凭证完整性、报表勾稽、利润质量、资产负债结构等基础财务质量评估。',
  '薪酬社保': '工资表vs社保明细vs公积金三方交叉验证——基数匹配、人数一致、比例合规。',
  '关联交易': '名称相似度检测、同法人/同注册地/同电话识别、客户供应商重叠对倒检测。',
  '行业对标': '66行业基准库五维对标——毛利率/净利率/税负率/进销比/人均营收。',
  '跨域推理': '跨域证据链串联——多源数据交叉验证形成闭环证据链。系统最高价值输出层。',
  '发票匹配': '发票号码/代码/日期/金额与申报数据的匹配验证，进销发票数量与金额的一致性检查。',
  '申报合规': '各税种申报表的填写规范性和数据准确性检查，申报期限和报送要求验证。',
  '行业专项': '针对特定行业的专属稽查规则——制造业/建筑业/服务业/贸易等行业的特殊检查标准。',
  '个税': '个人所得税代扣代缴、专项附加扣除、工资薪金与劳务报酬的合规检查。',
  '资产负债': '资产和负债科目的真实性验证——存货/应收账款/固定资产/负债的计价和存在性。',
  '企业所得': '企业所得税的收入确认、成本扣除、税收优惠、纳税调整等申报合规检查。',
  '成本费用': '成本和费用的真实性、合理性与配比性检查——虚列成本、费用资本化等。',
  '发票合规': '发票开具、取得、保管的全流程合规检查——虚开、代开、非法取得等。',
  '增值税': '增值税销项税额、进项税额、应纳税额的计算准确性和申报及时性。',
  '自动发现': '系统自动发现的行业校准规则——当某个信号在同行业多家企业中普遍出现(>60%)时，系统判定该信号为该行业常态，自动降低风险权重，避免误报。这是AGI自学习机制的Layer C输出。',
};

function renderTaxRiskRules(container) {
  if (!container) return;
  window.currentModule = '稽查指令';

  container.innerHTML = '<style>'
    + '.rr-layout{display:flex;gap:24px;max-width:1300px;margin:0 auto;padding:20px;background:#fff}'
    + '.rr-toc{width:190px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:12px;line-height:2.0;max-height:calc(100vh-40px);overflow-y:auto}'
    + '.rr-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}'
    + '.rr-toc a{display:flex;align-items:center;justify-content:space-between;color:#475569;text-decoration:none;padding:3px 8px;border-radius:4px;cursor:pointer}'
    + '.rr-toc a:hover,.rr-toc a.active{background:#eff6ff;color:#2563eb;font-weight:600}'
    + '.rr-toc a .cnt{font-size:10px;color:#94a3b8;background:#f1f5f9;padding:1px 6px;border-radius:10px}'
    + '.rr-main{flex:1;min-width:0;background:#fff}'
    + '.rr-main h3{font-size:16px!important;font-weight:700!important;color:#0f172a!important;padding-bottom:8px!important;border-bottom:2px solid #e2e8f0!important;margin:0 0 12px!important}'
    + '.rr-main .rr-rule-card{transition:box-shadow 0.15s}'
    + '.rr-main .rr-rule-card:hover{box-shadow:0 2px 8px rgba(0,0,0,.06)}'
    + '</style>'
    + '<div class="rr-layout">'
    + '<nav class="rr-toc" id="rr-toc"><div class="toc-title">📖 分类</div></nav>'
    + '<div class="rr-main">'
    + '<h2 style="font-size:22px;font-weight:800;color:#0f172a;margin:0 0 4px">📋 稽查指令</h2>'
    + '<p style="font-size:13px;color:#94a3b8;margin:0 0 16px" id="risk-rules-count">加载中...</p>'
    // Hero
    + '<div style="background:#fff;border:1px solid #e2e8f0;padding:20px 24px;border-radius:8px;margin-bottom:24px">'
    + '<p style="font-size:13px;color:#475569;line-height:2.0;margin:0">'
    + '稽查指令是系统的规则知识库——1514条结构化税务稽查规则，覆盖资金流、进销存、发票流、经营实质、'
    + '税务合规、薪酬社保、关联交易等20个分类。每条指令包含稽查标准、风险等级、评分、详细检查方法、'
    + '处理建议和法律依据。运行一键分析后，系统自动将域分析发现与规则库交叉匹配，触发对应指令——'
    + '被触发的规则高亮显示并展示触发溯源（是哪个域分析的哪项发现触发了该规则），形成"发现→规则→结论"的完整证据链。'
    + '</p>'
    + '</div>'
    // 使用说明
    + '<details style="margin-bottom:24px;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden">'
    + '<summary style="padding:12px 16px;background:#fff;cursor:pointer;font-size:14px;font-weight:600;color:#0f172a;user-select:none;border-bottom:1px solid #f1f5f9">📖 使用说明</summary>'
    + '<div style="padding:14px 16px;font-size:13px;color:#475569;line-height:2.0;background:#fff">'
    + '<p style="margin:0 0 8px"><strong>1. 浏览规则：</strong>左侧目录按分类组织，点击可快速定位。右侧统计卡片展示规则总数和高/中/低风险分布。</p>'
    + '<p style="margin:0 0 8px"><strong>2. 搜索筛选：</strong>输入关键词搜索指令名称、规则ID、分类名称、法律条文或详细内容。下拉框按风险等级筛选。点击"仅看触发"过滤只显示本次分析匹配到的规则。</p>'
    + '<p style="margin:0 0 8px"><strong>3. 查看触发：</strong>运行一键分析后，被触发的规则会以红色左边线+红色徽章"✅ 本次触发(N)"高亮显示。'
    + '展开规则可见红色溯源卡片，列出每一项触发了该规则的域分析发现——包含发现类型、数据详情和风险等级，支持从规则反向追溯到原始发现。</p>'
    + '<p style="margin:0 0 8px"><strong>4. 规则结构：</strong>每条指令包含11个标准字段——指令名称(item)、风险等级(level)、评分(score)、详细标准(detail)、'
    + '稽查建议(suggestion)、所需佐证(evidence)、税务影响(tax_impact)、法律依据(policy_ref)、数据来源(dataSource)、可检测性(detectable)、分类(category)。</p>'
    + '<p style="margin:0"><strong>5. 学习闭环：</strong>用户通过报告审核功能对发现的准确性进行反馈，纠正规则存入correction_rules.json。'
    + '同类纠正累计≥1次后自动升级为系统规则——下次一键分析自动应用四级回退匹配，无需人工干预。形成"分析→审核→纠正→自动应用"的完整学习闭环。</p>'
    + '</div>'
    + '</details>'
    // 搜索栏
    + '<div style="display:flex;gap:8px;margin-bottom:24px;flex-wrap:wrap">'
    + '<input id="rr-search" type="text" placeholder="🔍 搜索指令（关键词/规则ID/分类/法条）..." oninput="filterRules()" style="flex:1;min-width:200px;padding:8px 14px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;color:#0f172a;background:#fff;outline:none" onfocus="this.style.borderColor=\'#2563eb\'" onblur="this.style.borderColor=\'#e2e8f0\'">'
    + '<select id="rr-level-filter" onchange="filterRules()" style="padding:8px 12px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;color:#0f172a;background:#fff;cursor:pointer">'
    + '<option value="">全部等级</option><option value="高风险">🔴 高风险</option><option value="中风险">🟡 中风险</option><option value="低风险">🔵 低风险</option><option value="良好">🟢 良好</option>'
    + '</select>'
    + '<button onclick="toggleTriggeredOnly()" id="rr-trigger-btn" style="padding:8px 14px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;color:#0f172a;background:#fff;cursor:pointer;white-space:nowrap">🔗 仅看触发</button>'
    + '<span id="rr-filter-count" style="font-size:12px;color:#94a3b8;padding:8px 0"></span>'
    + '</div>'
    + '<div id="risk-rules-list"></div>'
    + '<div id="risk-rules-stats" style="text-align:center;padding:24px;font-size:13px;color:#94a3b8"></div>'
    + '</div></div>';

  loadTaxRiskRules();
}

var _showTriggeredOnly = false;

function toggleTriggeredOnly() {
  _showTriggeredOnly = !_showTriggeredOnly;
  var btn = document.getElementById('rr-trigger-btn');
  if (btn) {
    btn.style.background = _showTriggeredOnly ? '#eff6ff' : '#fff';
    btn.style.borderColor = _showTriggeredOnly ? '#2563eb' : '#e2e8f0';
    btn.style.color = _showTriggeredOnly ? '#2563eb' : '#0f172a';
  }
  filterRules();
}

function filterRules() {
  var search = (document.getElementById('rr-search')?.value || '').toLowerCase();
  var level = document.getElementById('rr-level-filter')?.value || '';
  
  var listEl = document.getElementById('risk-rules-list');
  if (!listEl) return;
  
  var allCards = listEl.querySelectorAll('[data-rule-id]');
  var visible = 0;
  
  allCards.forEach(function(card) {
    var text = (card.textContent || '').toLowerCase();
    var ruleLevel = card.getAttribute('data-level') || '';
    var triggered = card.getAttribute('data-triggered') === '1';
    
    var matches = true;
    if (search && text.indexOf(search) < 0) matches = false;
    if (level && ruleLevel !== level) matches = false;
    if (_showTriggeredOnly && !triggered) matches = false;
    
    card.style.display = matches ? '' : 'none';
    if (matches) visible++;
    
    // Also show/hide parent category header
    var header = card.closest('[id^="rr-cat-"]');
    if (header) {
      var anyVisible = header.querySelectorAll('[data-rule-id]:not([style*="display: none"])').length > 0;
      header.style.display = anyVisible ? '' : 'none';
    }
  });
  
  var cntEl = document.getElementById('rr-filter-count');
  if (cntEl) cntEl.textContent = '显示 ' + visible + ' 条';
}

async function loadTaxRiskRules() {
  await loadDefaultTaxRiskRules();
}

async function loadDefaultTaxRiskRules() {
  try {
    var resp = await fetch('/static/tax_risk_rules_local_export.json?_t=' + Date.now());
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    var rules = await resp.json();
    if (!Array.isArray(rules) || rules.length === 0) throw new Error('数据为空');
    taxRiskRulesData = rules;
    try { localStorage.setItem('taxRiskRulesData', JSON.stringify(rules)); } catch(e) {}
    
    // 先加载触发溯源数据，再渲染
    await loadTriggeredRules();
    renderTaxRiskRulesList();
  } catch (e) {
    var el = document.getElementById('risk-rules-list');
    if (el) el.innerHTML = '<div style="text-align:center;padding:40px;color:#dc2626">加载失败: ' + e.message + '</div>';
  }
}

async function loadTriggeredRules() {
  _triggeredRuleFindings = {};
  try {
    if (typeof getSharedAnalysis === 'function') {
      var sa = await getSharedAnalysis();
      if (sa && sa.ok && sa.report) {
        (sa.report.all_findings || []).forEach(function(f) {
          var rid = String(f.rule_id || '').trim();
          if (!rid) return;
          if (!_triggeredRuleFindings[rid]) _triggeredRuleFindings[rid] = [];
          _triggeredRuleFindings[rid].push({
            type: f.type || f.domain || '',
            domain: f.domain || '',
            detail: f.detail || '',
            level: f.level || '',
            score: f.score || 0
          });
        });
      }
    }
  } catch(e) {}
}

function renderTaxRiskRulesList() {
  var data = taxRiskRulesData;
  var listEl = document.getElementById('risk-rules-list');
  var statsEl = document.getElementById('risk-rules-stats');
  if (!listEl) return;

  var triggeredCount = Object.keys(_triggeredRuleFindings).length;
  var countEl = document.getElementById('risk-rules-count');
  var triggerText = triggeredCount > 0 ? '（本次触发 <span style="color:#dc2626;font-weight:600">' + triggeredCount + '</span> 条）' : '（暂无触发）';
  if (countEl) countEl.innerHTML = data.length + ' 条稽查指令 ' + triggerText + ' · 按分类分组 · 支持搜索筛选';

  if (data.length === 0) {
    listEl.innerHTML = '<div style="padding:40px 0;font-size:13px;color:#94a3b8">暂无稽查指令，请加载数据</div>';
    return;
  }

  // 按分类分组
  var grouped = {};
  data.forEach(function(r) {
    var cat = r.category || r.rule_category || '其他';
    if (!grouped[cat]) { grouped[cat] = { icon: r.categoryIcon || '', rules: [] }; }
    grouped[cat].rules.push(r);
  });

  var sortedCats = Object.keys(grouped).sort(function(a, b) {
    return grouped[b].rules.length - grouped[a].rules.length;
  });

  // 统计
  var high = data.filter(function(r) { return (r.level === '极高风险' || r.level === '高风险'); }).length;
  var mid = data.filter(function(r) { return r.level === '中风险'; }).length;
  var low = data.filter(function(r) { return r.level === '低风险' || r.level === '良好'; }).length;

  // 左侧目录
  var tocEl = document.getElementById('rr-toc');
  if (tocEl) {
    tocEl.innerHTML = '<div class="toc-title">📖 ' + data.length + ' 条指令</div>'
      + '<a href="#rr-stats">📊 统计总览</a>';
    sortedCats.forEach(function(cat) {
      tocEl.innerHTML += '<a href="#rr-cat-' + encodeURIComponent(cat) + '">' + (grouped[cat].icon||'📋') + ' ' + cat + ' <span class="cnt">' + grouped[cat].rules.length + '</span></a>';
    });
  }

  var html = '';

  // 统计概览
  html += '<div id="rr-stats" style="display:flex;gap:12px;margin-bottom:32px">'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#0f172a">' + data.length + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">指令总数</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#dc2626">' + high + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">高风险</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#f59e0b">' + mid + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">中风险</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:1px solid #e2e8f0;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#10b981">' + low + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">低/良好</div></div>'
    + (triggeredCount > 0 ? '<div style="flex:1;text-align:center;padding:16px;background:#fff;border:2px solid #dc2626;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#dc2626">' + triggeredCount + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">本次触发</div></div>' : '')
    + '</div>';

  // 按分类详情
  sortedCats.forEach(function(cat) {
    var group = grouped[cat];
    var catDesc = CATEGORY_DESCRIPTIONS[cat] || '';
    var catRules = group.rules;

    html += '<div id="rr-cat-' + encodeURIComponent(cat) + '" style="margin-bottom:40px">'
      + '<div style="margin-bottom:16px">'
      + '<div style="font-size:16px;font-weight:700;color:#0f172a;margin-bottom:6px">'
      + (group.icon ? '<span style="font-size:18px">' + group.icon + '</span> ' : '') + escHtml(cat)
      + ' <span style="font-size:13px;font-weight:400;color:#94a3b8">' + catRules.length + ' 条指令' + (catDesc ? ' · ' + catDesc : '') + '</span>'
      + '</div>'
      + '</div>';

    catRules.forEach(function(rule) {
      // 自动发现规则的字段映射
      var isAutoRule = rule.type === 'auto_signal';
      var itemName = rule.item || rule.signal || '';
      var levelName = rule.level || rule.severity || '';
      var scoreVal = rule.score !== undefined ? rule.score : (rule.confidence !== undefined ? Math.round(rule.confidence * 10) : '-');
      var detailText = rule.detail || '';
      var suggestText = rule.suggestion || rule.action || '';
      var evidenceText = rule.evidence || '';
      var impactText = rule.tax_impact || '';
      var policyText = rule.policy_ref || '';
      
      // 自动发现规则用蓝色标识
      var color = isAutoRule ? '#2563eb' : (RISK_LEVEL_COLORS[levelName] || '#64748b');
      var icon = isAutoRule ? '🤖' : (RISK_LEVEL_ICONS[levelName] || '⚪');
      var rid = String(rule.id || '').trim();
      var triggered = _triggeredRuleFindings[rid] || [];
      var isTriggered = triggered.length > 0;
      var borderColor = isTriggered ? '#dc2626' : color;
      var borderWidth = isTriggered ? '4px' : '3px';

      html += '<div data-rule-id="' + rid + '" data-level="' + (levelName || '') + '" data-triggered="' + (isTriggered ? '1' : '0') + '"'
        + ' style="padding:16px 20px;margin-bottom:8px;background:#fff;border:1px solid #e2e8f0;border-left:' + borderWidth + ' solid ' + borderColor + ';border-radius:6px" class="rr-rule-card">'
        
        // 标题行
        + '<div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:8px">'
        + '<div style="font-size:15px;font-weight:600;color:#0f172a">'
        + (isAutoRule ? '🤖 ' : '') + escHtml(itemName)
        + (isAutoRule ? '<span style="margin-left:6px;font-size:11px;font-weight:400;color:#64748b">[' + escHtml(rule.industry || '') + ']</span>' : '')
        + (isTriggered ? '<span style="margin-left:8px;font-size:11px;padding:2px 8px;border-radius:4px;background:#fef2f2;color:#dc2626;font-weight:600">✅ 本次触发(' + triggered.length + ')</span>' : '')
        + '</div>'
        + '<div style="display:flex;gap:8px;align-items:center;flex-shrink:0;margin-left:16px">'
        + (isAutoRule 
            ? '<span style="font-size:11px;padding:2px 8px;border-radius:4px;background:#eff6ff;color:#2563eb;font-weight:600">🤖 自动发现</span>'
            : '<span style="font-size:11px;padding:2px 8px;border-radius:4px;background:' + color + '15;color:' + color + ';font-weight:600">' + icon + ' ' + (levelName || '') + '</span>')
        + (isAutoRule 
            ? '<span style="font-size:11px;color:#94a3b8">置信度 ' + (rule.confidence !== undefined ? Math.round(rule.confidence * 100) + '%' : '-') + '</span>'
            : '<span style="font-size:11px;color:#94a3b8">评分 ' + scoreVal + '</span>')
        + (rid ? '<span style="font-size:10px;color:#94a3b8">ID:' + rid + '</span>' : '')
        + '</div>'
        + '</div>'

        // 触发溯源
        + (isTriggered ? '<div style="margin-bottom:8px;padding:8px 12px;background:#fef2f2;border-radius:4px;font-size:12px;line-height:2.0">'
        + '<div style="font-weight:600;color:#991b1b;margin-bottom:4px">🔗 触发溯源：</div>'
        + triggered.map(function(t) {
            return '<div style="color:#7f1d1d">→ <strong>' + escHtml(t.domain || t.type || '') + '</strong>' + (t.detail ? ': ' + escHtml(t.detail.substring(0, 150)) : '') + (t.level ? ' [' + t.level + ']' : '') + '</div>';
          }).join('')
        + '</div>' : '')

        // 详细内容
        + (detailText ? '<div style="font-size:13px;color:#475569;line-height:2.0;margin-bottom:8px">' + escHtml(detailText) + '</div>' : '')

        // 建议 + 佐证
        + (suggestText ? '<div style="font-size:13px;color:#334155;line-height:2.0;margin-bottom:4px"><span style="font-weight:600;color:#0f172a">' + (isAutoRule ? '系统建议：' : '稽查建议：') + '</span>' + escHtml(suggestText) + '</div>' : '')
        + (evidenceText ? '<div style="font-size:13px;color:#334155;line-height:2.0;margin-bottom:4px"><span style="font-weight:600;color:#0f172a">' + (isAutoRule ? '发现依据：' : '所需佐证：') + '</span>' + escHtml(evidenceText) + '</div>' : '')
        
        // 自动发现额外信息
        + (isAutoRule ? '<div style="font-size:13px;color:#334155;line-height:2.0;margin-bottom:4px"><span style="font-weight:600;color:#0f172a">信号出现率：</span>' + escHtml(rule.prevalence || '') + '</div>' : '')
        + (isAutoRule && rule.auto_discovered_at ? '<div style="font-size:13px;color:#334155;line-height:2.0;margin-bottom:4px"><span style="font-weight:600;color:#0f172a">自动发现时间：</span>' + escHtml(rule.auto_discovered_at.substring(0, 19)) + '</div>' : '')

        // 底栏
        + '<div style="display:flex;gap:16px;flex-wrap:wrap;margin-top:8px;padding-top:8px;border-top:1px solid #e2e8f0;font-size:12px;color:#94a3b8">'
        + (impactText ? '<span><span style="color:#64748b">税务影响：</span>' + escHtml(impactText.substring(0, 120)) + (impactText.length > 120 ? '...' : '') + '</span>' : '')
        + (policyText ? '<span><span style="color:#64748b">法条：</span>' + escHtml(policyText.substring(0, 100)) + (policyText.length > 100 ? '...' : '') + '</span>' : '')
        + (rule.dataSource ? '<span><span style="color:#64748b">数据源：</span>' + escHtml(rule.dataSource) + '</span>' : '')
        + (rule.detectable !== undefined ? '<span>' + (rule.detectable ? '✅ 可自动检测' : '⚠️ 需人工') + '</span>' : '')
        + '</div>'
        + '</div>';

        // 底栏
        + '<div style="display:flex;gap:16px;flex-wrap:wrap;margin-top:8px;padding-top:8px;border-top:1px solid #e2e8f0;font-size:12px;color:#94a3b8">'
        + (rule.tax_impact ? '<span><span style="color:#64748b">税务影响：</span>' + escHtml(rule.tax_impact.substring(0, 120)) + (rule.tax_impact.length > 120 ? '...' : '') + '</span>' : '')
        + (rule.policy_ref ? '<span><span style="color:#64748b">法条：</span>' + escHtml(rule.policy_ref.substring(0, 100)) + (rule.policy_ref.length > 100 ? '...' : '') + '</span>' : '')
        + (rule.dataSource ? '<span><span style="color:#64748b">数据源：</span>' + escHtml(rule.dataSource) + '</span>' : '')
        + (rule.detectable !== undefined ? '<span>' + (rule.detectable ? '✅ 可自动检测' : '⚠️ 需人工') + '</span>' : '')
        + '</div>'
        + '</div>';
    });

    html += '</div>';
  });

  listEl.innerHTML = html;

  if (statsEl) {
    statsEl.innerHTML = '共 ' + data.length + ' 条稽查指令 · '
      + '<span style="color:#dc2626">高 ' + high + '</span> · '
      + '<span style="color:#f59e0b">中 ' + mid + '</span> · '
      + '<span style="color:#10b981">低/良 ' + low + '</span> · '
      + sortedCats.length + ' 个分类';
  }
  
  // 初始化筛选计数
  var cntEl = document.getElementById('rr-filter-count');
  if (cntEl) cntEl.textContent = '显示 ' + data.length + ' 条';
}
