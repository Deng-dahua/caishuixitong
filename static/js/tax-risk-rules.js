// ==================== 稽查指令页面 ====================
var taxRiskRulesData = [];

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
};

function renderTaxRiskRules(container) {
  if (!container) return;
  window.currentModule = '稽查指令';

  container.innerHTML = ''
    + '<div class="pipeline-page card card-fill">'
    + '  <div style="margin-bottom:48px">'
    + '    <h2 style="font-size:24px;font-weight:700;color:#0f172a;margin:0 0 6px">稽查指令</h2>'
    + '    <p style="font-size:14px;color:#94a3b8;margin:0" id="risk-rules-count">1505 条稽查指令 · 按分类分组 · 每条含详细稽查标准和法律依据</p>'
    + '  </div>'
    + '  <div id="risk-rules-list"></div>'
    + '  <div id="risk-rules-stats" style="text-align:center;padding:24px;font-size:13px;color:#94a3b8"></div>'
    + '</div>';

  // 每次进入页面都重新加载，不使用缓存
  loadTaxRiskRules();
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
    renderTaxRiskRulesList();
  } catch (e) {
    var el = document.getElementById('risk-rules-list');
    if (el) el.innerHTML = '<div style="text-align:center;padding:40px;color:#dc2626">加载失败: ' + e.message + '</div>';
  }
}

function renderTaxRiskRulesList() {
  var data = taxRiskRulesData;
  var listEl = document.getElementById('risk-rules-list');
  var statsEl = document.getElementById('risk-rules-stats');
  if (!listEl) return;

  // 更新页面标题数量
  var countEl = document.getElementById('risk-rules-count');
  if (countEl) countEl.textContent = data.length + ' 条稽查指令 · 按分类分组 · 每条含详细稽查标准和法律依据';

  if (data.length === 0) {
    listEl.innerHTML = '<div style="padding:40px 0;font-size:13px;color:#94a3b8">暂无稽查指令，请加载数据</div>';
    return;
  }

  // 按分类分组
  var grouped = {};
  data.forEach(function(r) {
    var cat = r.category || '其他';
    if (!grouped[cat]) { grouped[cat] = { icon: r.categoryIcon || '', rules: [] }; }
    grouped[cat].rules.push(r);
  });

  var sortedCats = Object.keys(grouped).sort(function(a, b) {
    return grouped[b].rules.length - grouped[a].rules.length;
  });

  var html = '';

  // 统计概览
  var high = data.filter(function(r) { return r.level === '高风险'; }).length;
  var mid = data.filter(function(r) { return r.level === '中风险'; }).length;
  var low = data.filter(function(r) { return r.level === '低风险' || r.level === '良好'; }).length;

  html += '<div style="display:flex;gap:12px;margin-bottom:40px">'
    + '<div style="flex:1;text-align:center;padding:16px;background:#f8fafc;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#0f172a">' + data.length + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">指令总数</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fef2f2;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#dc2626">' + high + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">高风险</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#fffbeb;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#f59e0b">' + mid + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">中风险</div></div>'
    + '<div style="flex:1;text-align:center;padding:16px;background:#f0fdf4;border-radius:8px"><div style="font-size:28px;font-weight:700;color:#10b981">' + low + '</div><div style="font-size:12px;color:#64748b;margin-top:4px">低/良好</div></div>'
    + '</div>';

  // 按分类详情
  sortedCats.forEach(function(cat) {
    var group = grouped[cat];
    var catDesc = CATEGORY_DESCRIPTIONS[cat] || '';
    var catRules = group.rules;

    html += '<div style="margin-bottom:40px">'
      + '<div style="margin-bottom:16px">'
      + '<div style="font-size:16px;font-weight:700;color:#0f172a;margin-bottom:6px">'
      + (group.icon ? '<span style="font-size:18px">' + group.icon + '</span> ' : '') + escHtml(cat)
      + ' <span style="font-size:13px;font-weight:400;color:#94a3b8">' + catRules.length + ' 条指令</span>'
      + '</div>'
      + (catDesc ? '<div style="font-size:13px;color:#64748b;line-height:1.7">' + escHtml(catDesc) + '</div>' : '')
      + '</div>';

    catRules.forEach(function(rule) {
      var color = RISK_LEVEL_COLORS[rule.level] || '#64748b';
      var icon = RISK_LEVEL_ICONS[rule.level] || '⚪';
      var levelBg = rule.level === '高风险' ? '#fef2f2' : (rule.level === '中风险' ? '#fffbeb' : '#f0fdf4');

      html += '<div data-rule-id="' + (rule.id || '') + '" style="padding:16px 20px;margin-bottom:8px;background:' + levelBg + ';border-left:3px solid ' + color + ';border-radius:0 8px 8px 0">'
        // 标题行
        + '<div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:8px">'
        + '<div style="font-size:15px;font-weight:600;color:#0f172a">' + escHtml(rule.item) + '<span class="rule-trigger-badge" style="display:none;margin-left:8px;font-size:11px;padding:1px 6px;border-radius:3px;background:#fef2f2;color:#dc2626;font-weight:600">本次触发</span></div>'
        + '<div style="display:flex;gap:8px;align-items:center;flex-shrink:0;margin-left:16px">'
        + '<span style="font-size:11px;padding:2px 8px;border-radius:4px;background:' + color + '15;color:' + color + ';font-weight:600">' + icon + ' ' + (rule.level || '') + '</span>'
        + '<span style="font-size:11px;color:#94a3b8">评分 ' + (rule.score !== undefined ? rule.score : '-') + '</span>'
        + (rule.id ? '<span style="font-size:10px;color:#94a3b8">ID:' + rule.id + '</span>' : '')
        + '</div>'
        + '</div>'

        // 详细内容
        + (rule.detail ? '<div style="font-size:13px;color:#475569;line-height:1.9;margin-bottom:8px">' + escHtml(rule.detail) + '</div>' : '')

        // 建议
        + (rule.suggestion ? '<div style="font-size:13px;color:#334155;line-height:1.8;margin-bottom:6px"><span style="font-weight:600;color:#0f172a">稽查建议：</span>' + escHtml(rule.suggestion) + '</div>' : '')

        // 佐证
        + (rule.evidence ? '<div style="font-size:13px;color:#334155;line-height:1.8;margin-bottom:6px"><span style="font-weight:600;color:#0f172a">所需佐证：</span>' + escHtml(rule.evidence) + '</div>' : '')

        // 底栏：税务影响 + 法律依据 + 数据来源
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

  // 标注本次触发的规则（延迟加载，不阻塞页面渲染）
  if (typeof getSharedAnalysis === 'function') {
    getSharedAnalysis().then(function(sa) {
      if (sa && sa.ok && sa.report) {
        var triggeredIds = new Set();
        (sa.report.all_findings || []).forEach(function(f) {
          if (f.rule_id) triggeredIds.add(String(f.rule_id));
        });
        triggeredIds.forEach(function(rid) {
          var el = document.querySelector('[data-rule-id="' + rid + '"]');
          if (el) {
            el.style.borderLeftColor = '#dc2626';
            el.style.borderLeftWidth = '5px';
            var badge = el.querySelector('.rule-trigger-badge');
            if (badge) badge.style.display = 'inline';
          }
        });
        // 更新标题的触发统计
        var cntEl = document.getElementById('risk-rules-count');
        if (cntEl) cntEl.textContent = data.length + ' 条稽查指令（本次触发 ' + triggeredIds.size + ' 条）· 按分类分组 · 每条含详细稽查标准和法律依据';
      }
    }).catch(function(){});
  }
}
