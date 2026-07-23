// ==================== 税务疑点库页面 ====================
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
  '资金流': '资金流向追踪、收款来源分析、付款方身份核实、异常交易检测。银行流水是税务合规的第一切入资料。',
  '发票进销匹配': '进销品名交叉映射、进销比分析、有进无销/有销无进诊断、BOM加工链条验证、存货周转预警、发票合规检查、税率异常、红冲作废追踪。',
  '经营实质': '企业是否具备真实经营条件——经营费用/仓储/物流/人员/产能。全链条经营实质地理分析。',
  '资料完备': '14类税务合规必查资料逐项检测，合同需求四层自动分层，缺失资料标注风险等级。',
  '税务合规': '增值税/企业所得税/个税/印花税/城建税等各税种申报与实际数据比对验证。',
  '财务数据': '科目余额、凭证完整性、报表勾稽、利润质量、资产负债结构等基础财务质量评估。',
  '薪酬社保': '工资表vs社保明细vs公积金三方交叉验证——基数匹配、人数一致、比例合规。',
  '关联交易': '名称相似度检测、同法人/同注册地/同电话识别、客户供应商重叠对倒检测。',
  '申报合规': '各税种申报表的填写规范性和数据准确性检查，申报期限和报送要求验证。',
  '行业专项': '针对特定行业的专属税务合规规则——制造业/建筑业/服务业/贸易等行业的特殊检查标准。',
  '个税': '个人所得税代扣代缴、专项附加扣除、工资薪金与劳务报酬的合规检查。',
  '资产负债': '资产和负债科目的真实性验证——存货/应收账款/固定资产/负债的计价和存在性。',
  '资产负债往来': '资产负债往来对应关系检查——借贷不平衡/应付账款占比/应收账款账龄/预收账款挂账等。',
  '企业所得税': '企业所得税的收入确认、成本扣除、税收优惠、纳税调整等申报合规检查。',
  '成本费用': '成本和费用的真实性、合理性与配比性检查——虚列成本、费用资本化等。',
  '成本费用配比': '毛利率/净利率/期间费用/业务招待费/资产损失等多项财务指标的综合配比分析。',
  '收入合规': '收入确认的真实性、完整性与及时性——预收账款转收入/其他应收款/存货周转/应付账款等。',
  '增值税税负': '增值税税负率偏高/偏低分析、文化事业建设费、长期零申报、免税收入进项转出等。',
  '增值税': '增值税销项税额、进项税额、应纳税额的计算准确性和申报及时性。',
  '个人所得税': '个人所得税代扣代缴、劳务报酬、经营所得、财产转让等个人所得税的申报与缴纳合规检查。',
  '虚开风险': '虚开发票风险检测——三流不一致/空壳供应商/资金回流/品名不匹配等虚开发票的典型特征识别与证据链构建。',
  '经营穿透': '经营实质深度穿透——从发票/合同/物流/资金多维度核查企业经营真实性，识别空壳/虚假交易。',
  '财产行为税': '房产税、契税、土地增值税、印花税、车船税等财产行为税种的申报缴纳合规检查。',
  '外部数据比对': '通过工商/海关/外汇/社保/电力等外部数据与税务申报数据的交叉比对，发现不一致和隐匿信息。',
  '合同风险': '合同签订与执行的税务风险——阴阳合同/时间倒挂/付款不符/金额不一致等合同异常检测。',
  '关联风险': '关联方穿透识别——同一法人/同址/同电话/交叉任职/利益输送等关联风险排查。',
  '出口退税': '出口退税合规检查——出口收入真实性/退税率/收汇/产能/货源穿透等出口退税全链条核查。',
};

// ═══ 详情内容生成（23字段完整展示，列表页与详情页共用数据源）═══
// 元信息标识（人工/自动、等级、评分、分类、频率）已移至列表标题行显示，详情页不再重复
window._rrDetailHtml = function(rl) {
  var card = '<div class="rr-rule">'
    + '<div class="rh">#' + (rl.id || '') + ' ' + escHtml(rl.item || '未命名') + '</div>';

  // 7段式新格式：phenomena → direction → focus → risk_table → normal_reason → determination → drill_questions
  if (rl.phenomena) {
    card += '<div style="font-size:10px;font-weight:600;color:#16233a;margin:8px 0 4px;border-bottom:1px solid #e2e8f0;padding-bottom:4px">一、异常现象描述</div>';
    card += '<div style="font-size:10px;color:#3a4048;line-height:20px;margin:4px 0 10px;white-space:pre-wrap">' + escHtml(rl.phenomena) + '</div>';
  }
  if (rl.direction) {
    card += '<div style="font-size:10px;font-weight:600;color:#16233a;margin:8px 0 4px;border-bottom:1px solid #e2e8f0;padding-bottom:4px">' + (rl.phenomena ? '二' : '一') + '、异常逻辑分析（为何成为疑点）</div>';
    card += '<div style="font-size:10px;color:#64748b;line-height:20px;padding-left:10px;border-left:2px solid #9a1f2b;margin:4px 0 10px;white-space:pre-wrap">' + escHtml(rl.direction) + '</div>';
  }
  if (rl.focus && rl.focus !== '待明确重点') {
    card += '<div style="font-size:10px;font-weight:600;color:#16233a;margin:8px 0 4px;border-bottom:1px solid #e2e8f0;padding-bottom:4px">稽查重点指向</div>';
    card += '<div style="font-size:10px;color:#dc2626;line-height:20px;padding-left:10px;border-left:2px solid #dc2626;margin:4px 0 10px;white-space:pre-wrap">' + escHtml(rl.focus) + '</div>';
  }
  
  // 风险表格
  if (rl.risk_table) {
    card += '<div style="font-size:10px;font-weight:600;color:#16233a;margin:8px 0 4px;border-bottom:1px solid #e2e8f0;padding-bottom:4px">触发的稽查风险点</div>';
    card += '<table style="width:100%;border-collapse:collapse;font-size:10px;margin:4px 0 10px"><tr style="background:#fef2f2"><td style="padding:3px 6px;border:1px solid #fcc;font-weight:600;width:80px">风险维度</td><td style="padding:3px 6px;border:1px solid #fcc">风险点描述</td></tr>';
    var rows = typeof rl.risk_table === 'string' ? rl.risk_table.split('\n') :
  (Array.isArray(rl.risk_table) ? rl.risk_table.map(function(rr){
    var tax = rr.税种 || rr.tax || rr.name || '';
    var desc = rr.具体风险描述 || rr.风险描述 || rr.desc || rr.描述 || '';
    return tax + ':' + desc;
  }) : []);
    for (var ri = 0; ri < rows.length; ri++) {
      var parts = rows[ri].split(':');
      if (parts.length >= 2) {
        card += '<tr><td style="padding:3px 6px;border:1px solid #e2e8f0;font-weight:600">' + escHtml(parts[0]) + '</td><td style="padding:3px 6px;border:1px solid #e2e8f0">' + escHtml(parts.slice(1).join(':')) + '</td></tr>';
      }
    }
    card += '</table>';
  }
  
  // 正常业务解释
  if (rl.normal_reason) {
    card += '<div style="font-size:10px;font-weight:600;color:#16233a;margin:8px 0 4px;border-bottom:1px solid #e2e8f0;padding-bottom:4px">可能的业务解释（正常情形）</div>';
    card += '<div style="font-size:10px;color:#059669;line-height:20px;margin:4px 0 10px;padding:8px 12px;background:#f0fdf4;white-space:pre-wrap">' + escHtml(rl.normal_reason) + '</div>';
  }
  
  // 定性路径
  if (rl.determination) {
    card += '<div style="font-size:10px;font-weight:600;color:#16233a;margin:8px 0 4px;border-bottom:1px solid #e2e8f0;padding-bottom:4px">稽查定性路径</div>';
    card += '<div style="font-size:10px;color:#3a4048;line-height:20px;margin:4px 0 10px;white-space:pre-wrap">' + escHtml(rl.determination) + '</div>';
  }
  
  // 穿透式追问（整段完整展示，忠实原文换行，不做正则截取）
  if (rl.drill_questions) {
    card += '<div style="font-size:10px;font-weight:600;color:#16233a;margin:8px 0 4px;border-bottom:1px solid #e2e8f0;padding-bottom:4px">稽查常见穿透式追问与应对</div>';
    var dq = typeof rl.drill_questions === 'string' ? rl.drill_questions : (Array.isArray(rl.drill_questions) ? rl.drill_questions.join('\n') : '');
    card += '<div style="font-size:10px;color:#3a4048;line-height:20px;margin:4px 0 10px;padding:8px 12px;background:#fef8f8;border-left:3px solid #9a1f2b;white-space:pre-wrap">' + escHtml(dq) + '</div>';
  }
  
  // 传统字段（兼容未升级的规则）
  card += (rl.detail ? '<div style="font-size:10px;color:#3a4048;margin:2px 0 4px;white-space:pre-wrap">📄 详细标准：' + escHtml(rl.detail) + '</div>' : '')
    + (rl.action ? '<div style="font-size:10px;color:#3a4048;margin:2px 0 4px;white-space:pre-wrap">🔍 核查动作：' + escHtml(rl.action) + '</div>' : '')
    + (rl.threshold && !rl.threshold.startsWith('评分阈值') ? '<div style="font-size:10px;color:#94a3b8;margin:2px 0;white-space:pre-wrap">📏 触发指标：' + escHtml(rl.threshold) + '</div>' : '')
    + (rl.evidence ? '<div style="font-size:10px;color:#94a3b8;margin:2px 0;white-space:pre-wrap">📎 证据清单：' + escHtml(rl.evidence) + '</div>' : '')
    + (rl.policy_ref ? '<div class="ra" style="white-space:pre-wrap">📜 法律依据：' + escHtml(rl.policy_ref) + '</div>' : '')
    + (rl.suggestion ? '<div class="ra" style="white-space:pre-wrap">⚖ 稽查处理：' + escHtml(rl.suggestion) + '</div>' : '')
    + (rl.tax_impact ? '<div class="ra" style="white-space:pre-wrap">💰 税务影响：' + escHtml(rl.tax_impact) + '</div>' : '')
    + (rl.remedy && rl.remedy !== rl.suggestion ? '<div class="ra" style="white-space:pre-wrap">🔧 整改建议：' + escHtml(rl.remedy) + '</div>' : '')
    + (rl.applicable_condition ? '<div class="ra" style="white-space:pre-wrap">📋 适用条件：' + escHtml(rl.applicable_condition) + '</div>' : '');
  card += '</div>';
  return card;
};

// ═══ 表格行生成（列表=表格，每字段一列，点击行进详情）═══
window._rrTitleRow = function(rl) {
  var rid = String(rl.id || '').trim();
  var isAuto = rl.type === 'auto_signal' || rl.source === '系统发现' || !!rl.auto_type;
  var trigN = (typeof _triggeredRuleFindings !== 'undefined' && _triggeredRuleFindings[rid] || []).length;
  var rn = parseInt(rid) || 0;
  var padId = function(n) { return n < 10 ? '00' + n : n < 100 ? '0' + n : '' + n; };
  var chainInfo = (typeof _rrChainInfo !== 'undefined' && _rrChainInfo[rid]) || null;
  var cue = chainInfo && chainInfo.c_steps ? 'clue-' + padId(rn) : '-';
  var evd = chainInfo && chainInfo.e_dims ? 'evid-' + padId(rn) : '-';
  var alc = chainInfo && chainInfo.a_steps ? 'alc-' + padId(rn) : '-';
  return '<tr class="rr-row" data-rule-id="' + rid + '" data-level="' + (rl.level || '') + '" data-category="' + (rl.category || '') + '" data-monitor="' + (rl.monitor_category || '') + '" data-type="' + (isAuto ? 'auto' : 'manual') + '" data-triggered="' + (trigN > 0 ? '1' : '0') + '" onclick="_rrShowDetail(\'' + rid + '\')">'
    + '<td style="white-space:nowrap;color:#94a3b8">#' + rid + '</td>'
    + '<td class="rr-name" style="word-break:break-all">' + escHtml(rl.item || rl.signal || '未命名') + '</td>'
    + '<td>' + escHtml(rl.monitor_category || '-') + '</td>'
    + '<td style="white-space:nowrap"><span style="color:#7c3aed">✍ 人工规则</span></td>'
    + '<td style="text-align:center;font-size:9px;white-space:nowrap;color:#64748b">' + cue + '</td>'
    + '<td style="text-align:center;font-size:9px;white-space:nowrap;color:#64748b">' + evd + '</td>'
    + '<td style="text-align:center;font-size:9px;white-space:nowrap;color:#64748b">' + alc + '</td>'
    + '<td style="white-space:nowrap;text-align:center;color:#64748b">' + escHtml(String(rl.updated_at || rl.created_at || '').substring(0, 10) || '-') + '</td>'
    + '<td style="white-space:nowrap;text-align:center">' + (trigN > 0 ? '<span style="color:#dc2626;font-weight:700">✓</span>' : '') + '</td>'
    + '</tr>';
};

// ═══ 表格骨架（表头+行，两条渲染路径共用）═══
window._rrTable = function(rules) {
  var h = '<table class="rr-table">'
    + '<colgroup><col style="width:56px"><col><col style="width:118px"><col style="width:92px"><col style="width:68px"><col style="width:68px"><col style="width:68px"><col style="width:92px"><col style="width:82px"></colgroup>'
    + '<thead><tr>'
    + '<th>编号</th><th>疑点名称</th><th>监控维度</th><th>来源</th><th style="text-align:center">线索链</th><th style="text-align:center">证据链</th><th style="text-align:center">分析链</th><th style="text-align:center">更新时间</th><th style="text-align:center">本次触发</th>'
    + '</tr></thead><tbody>';
  rules.forEach(function(rl) { h += window._rrTitleRow(rl); });
  h += '</tbody></table>';
  return h;
};

// ═══ 详情视图：点击标题进入，返回按钮回列表 ═══
window._rrShowDetail = function(rid) {
  rid = String(rid || '').trim();
  var all = (window._rrData && window._rrData.length ? window._rrData : (typeof taxRiskRulesData !== 'undefined' ? taxRiskRulesData : [])) || [];
  var rl = all.find(function(r) { return String(r.id || '').trim() === rid; });
  if (!rl) return;
  var lv = document.getElementById('rr-list-view');
  var dv = document.getElementById('rr-detail-view');
  if (!lv || !dv) return;

  var isAuto = rl.type === 'auto_signal' || rl.source === '系统发现' || !!rl.auto_type;
  var triggered = (typeof _triggeredRuleFindings !== 'undefined' && _triggeredRuleFindings[rid]) || [];

  var h = '<div data-rule-id="' + rid + '">';
  // 顶栏：返回 + 操作
  h += '<div style="display:flex;align-items:center;gap:10px;margin:0 0 10px">'
    + '<button onclick="_rrBackToList()" style="font-size:10px;padding:5px 14px;border:1px solid #e2e8f0;background:#fff;color:#0f172a;cursor:pointer;font-weight:600">← 返回列表</button>'
    + '</div>';

  // 触发溯源
  if (triggered.length > 0) {
    h += '<div style="margin:0 0 10px;padding:8px 12px;background:#fef2f2;font-size:10px;line-height:20px">'
      + '<div style="font-weight:600;color:#991b1b;margin-bottom:4px">✅ 本次分析触发 ' + triggered.length + ' 次 · 触发溯源：</div>'
      + triggered.map(function(t) {
          return '<div style="color:#7f1d1d">→ <strong>' + escHtml(t.domain || t.type || '') + '</strong>' + (t.detail ? ': ' + escHtml(String(t.detail).substring(0, 200)) : '') + (t.level ? ' [' + t.level + ']' : '') + '</div>';
        }).join('')
      + '</div>';
  }

  // 23字段完整内容
  h += window._rrDetailHtml(rl);
  h += '</div>';

  dv.innerHTML = h;
  lv.style.display = 'none';
  dv.style.display = 'block';
  window.scrollTo(0, 0);
  var panel = document.querySelector('.rr');
  if (panel) panel.scrollTop = 0;
};

window._rrBackToList = function() {
  var lv = document.getElementById('rr-list-view');
  var dv = document.getElementById('rr-detail-view');
  if (dv) { dv.style.display = 'none'; dv.innerHTML = ''; }
  if (lv) lv.style.display = 'block';
};

// ═══ 点击线索/证据/分析链编号 → 弹窗查看链内容 ═══
window._rrShowChainDetail = function(chainId) {
  var prefix = chainId.substring(0, 4); // clue / evid / alc
  var fileMap = { 'clue': 'cross_domain_clues.json', 'evid': 'cross_domain_evidence.json', 'alc': 'cross_domain_analysis.json' };
  var fname = fileMap[prefix];
  if (!fname) return;

  // 显示加载状态
  var overlay = document.createElement('div');
  overlay.id = 'rr-chain-overlay';
  overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.4);z-index:9999;display:flex;align-items:center;justify-content:center';
  overlay.innerHTML = '<div id="rr-chain-popup" style="background:#fff;width:720px;max-height:85vh;overflow-y:auto;border-radius:8px;padding:20px;font-family:-apple-system,Microsoft YaHei,sans-serif;font-size:10px;line-height:20px;color:#3a4048;box-shadow:0 8px 32px rgba(0,0,0,0.15)"><div style="text-align:center;padding:40px;color:#94a3b8">加载中...</div></div>';
  document.body.appendChild(overlay);
  overlay.onclick = function(e) { if (e.target === overlay) { overlay.remove(); } };

  fetch('/static/' + fname + '?_t=' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var items = Array.isArray(data) ? data : (data[prefix + '_chains'] || data.evidence_chains || data.analysis_chains || []);
      var item = items.find(function(it) { return it && it.id === chainId; });
      var popup = document.getElementById('rr-chain-popup');
      if (!item) {
        popup.innerHTML = '<div style="text-align:center;padding:40px;color:#dc2626">未找到: ' + chainId + '</div>';
        return;
      }
      var h = '<div style="font-weight:700;font-size:12px;color:#16233a;margin-bottom:12px">🔗 ' + escHtml(item.id || '') + ' ' + escHtml(item.name || '') + '</div>';
      h += '<div style="color:#64748b;margin-bottom:12px">' + escHtml(item.description || '') + '</div>';

      // 线索链：调查步骤
      if (item.investigation_path) {
        h += '<div style="font-weight:600;color:#16233a;margin:8px 0 6px">调查路径 (' + item.investigation_path.length + '步)</div>';
        item.investigation_path.forEach(function(s) {
          h += '<div style="margin:4px 0;padding:6px 10px;background:#f8fafc;border-left:2px solid #2563eb">'
            + '<span style="font-weight:600;color:#2563eb">步骤' + (s.step || '?') + '</span> '
            + '<span style="color:#3a4048">' + escHtml(s.action || '') + '</span>'
            + (s.evidence ? '<div style="color:#94a3b8;margin-top:2px">📄 ' + escHtml(s.evidence) + '</div>' : '')
            + '</div>';
        });
      }

      // 证据链：验证维度
      if (item.dimensions) {
        h += '<div style="font-weight:600;color:#16233a;margin:8px 0 6px">验证维度 (' + item.dimensions.length + '维) ｜ 最少满足: ' + (item.min_evidence || '?') + '</div>';
        item.dimensions.forEach(function(d) {
          var wc = d.weight === '必备维度' ? '#dc2626' : d.weight === '核心维度' ? '#f59e0b' : '#64748b';
          h += '<div style="margin:4px 0;padding:6px 10px;background:#f8fafc;border-left:2px solid #f59e0b">'
            + '<span style="font-weight:600;color:#16233a">' + escHtml(d.dimension || '') + '</span>'
            + (d.weight ? ' <span style="font-size:9px;color:' + wc + '">[' + d.weight + ']</span>' : '')
            + '<div style="color:#3a4048;margin-top:2px">检验: ' + escHtml(d.check || '') + '</div>'
            + '<div style="color:#94a3b8;font-size:9px">条件: ' + escHtml(d.pass_condition || '') + '</div>'
            + '</div>';
        });
      }

      // 分析链：推理路径
      if (item.reasoning_path) {
        h += '<div style="font-weight:600;color:#16233a;margin:8px 0 6px">推理路径 (' + item.reasoning_path.length + '步)</div>';
        item.reasoning_path.forEach(function(s) {
          h += '<div style="margin:4px 0;padding:6px 10px;background:#f8fafc;border-left:2px solid #7c3aed">'
            + '<span style="font-weight:600;color:#7c3aed">步骤' + (s.step || '?') + '</span>'
            + (s.cross ? ' <span style="color:#94a3b8">[' + escHtml(s.cross) + ']</span>' : '')
            + '<div style="color:#3a4048;margin-top:2px">' + escHtml(s.action || '') + '</div>'
            + (s.conclusion ? '<div style="color:#059669;margin-top:2px">→ ' + escHtml(s.conclusion) + '</div>' : '')
            + (s.evidence_required ? '<div style="color:#94a3b8;font-size:9px;margin-top:2px">📄 ' + escHtml(s.evidence_required) + '</div>' : '')
            + '</div>';
        });
      }

      // suggestion
      if (item.suggestion) {
        h += '<div style="margin:12px 0 0;padding:8px 12px;background:#fef2f2;border-left:2px solid #dc2626;color:#991b1b">'
          + '<span style="font-weight:600">💡 判定建议: </span>' + escHtml(item.suggestion) + '</div>';
      }

      h += '<div style="text-align:center;margin-top:16px"><button onclick="document.getElementById(\'rr-chain-overlay\').remove()" style="font-size:10px;padding:5px 20px;border:1px solid #e2e8f0;background:#fff;color:#0f172a;cursor:pointer">关闭</button></div>';
      popup.innerHTML = h;
    })
    .catch(function(e) {
      var popup = document.getElementById('rr-chain-popup');
      if (popup) popup.innerHTML = '<div style="text-align:center;padding:40px;color:#dc2626">加载失败: ' + escHtml(e.message) + '</div>';
    });
};

function renderTaxRiskRules(container) {
  if (!container) return;
  var h = '';
  h += '<style>'
    + '.rr{max-width:960px;margin:0 auto;padding:10px;font-family:-apple-system,"Microsoft YaHei",sans-serif;color:#3a4048;font-size:10px;line-height:20px}'
    + '.rr-pre{font-size:10px;color:#5b6675;line-height:20px;margin:0 0 10px;padding:0}'
    + '.rr-pre em{font-style:normal;color:#9a1f2b;font-weight:600}'
    + '.rr-tax{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:10px;margin:0 0 10px}'
    + '.rr-tax .rt{padding:10px;font-size:10px}'
    + '.rr-tax .rt b{color:#16233a}'
    + '.rr-tax .rt span{font-size:10px;color:#94a3b8;float:right}'
    + '.rr-search{display:flex;gap:10px;margin-bottom:10px;flex-wrap:wrap;align-items:center}'
    + '.rr-search input{flex:1;min-width:180px;padding:6px 10px;border:none;border-bottom:1px solid #e2e8f0;font-size:10px;color:#475569;outline:none;background:transparent}'
    + '.rr-search input:focus{border-bottom-color:#9a1f2b}'
    + '.rr-search select{padding:6px 8px;border:none;border-bottom:1px solid #e2e8f0;font-size:10px;color:#475569;background:transparent;outline:none;cursor:pointer}'
    + '.rr-rule{padding:0 0 10px;margin-bottom:10px}'
    + '.rr-rule:hover{box-shadow:none}'
    + '.rr-rule .rh{font-size:10px;font-weight:600;color:#16233a;margin:0 0 10px}'
    + '.rr-rule .rl{display:inline-block;padding:1px 8px;border-radius:4px;font-size:10px;font-weight:600;margin-right:10px}'
    + '.rr-rule .rb{font-size:10px;color:#64748b;line-height:20px;margin:10px 0}'
    + '.rr-rule .ra{font-size:10px;color:#94a3b8}'
    + '.rr p{margin:0 0 10px;line-height:20px}'
    + '.rr-table{width:100%;table-layout:fixed;border-collapse:collapse;font-size:10px;margin:0 0 10px}'
    + '.rr-table th{padding:8px 8px;border:none;border-bottom:2px solid #16233a;color:#16233a;font-weight:700;text-align:left;line-height:20px;white-space:nowrap;overflow:hidden;background:transparent}'
    + '.rr-table td{padding:6px 8px;border:none;border-bottom:1px solid #eef2f6;line-height:20px;color:#3a4048;overflow:hidden;text-overflow:ellipsis}'
    + '.rr-row{cursor:pointer}'
    + '.rr-row:hover{background:transparent}'
    + '.rr-row:hover .rr-name{color:#9a1f2b;text-decoration:underline}'
    + '</style>';
  h += '<div id="rr-list-view">';
  h += '<div class="rr-pre">本规则库来源于多年稽查实务经验——每一条指令，均为<em>稽查判例、被查企业真实手法、行政复议和法院判决</em>提炼出的量化标尺。规则库不是"猜疑清单"，而是<em>将稽查经验转化为可复核的判定条件</em>——什么数据特征构成疑点、该疑点严重程度如何、下一步应查什么、法律依据在哪。系统依据这些规则对数据进行扫描、生成信号、提供溯源。以下为当前已加载的全部规则指令。</div>';

  h += '<div class="rr-search">'
    + '<input id="rr-search-input" type="text" placeholder="搜索规则..." oninput="window._rrFilter()" style="max-width:220px">'
    + '<select id="rr-cat-filter" onchange="window._rrFilter()">'
    + '<option value="">全部分类</option>'
    + '<option>资金流监控</option><option>发票流监控</option><option>申报流监控</option>'
    + '<option>社保与个税交叉</option><option>经营实质穿透</option><option>关联交易与利益输送</option>'
    + '<option>虚开发票专项</option><option>财产行为税监控</option><option>出口退税监控</option>'
    + '<option>行业专项监控</option><option>外部数据比对</option><option>账表质量与勾稽</option>'
    + '<option>税务合规与程序</option>'
    + '</select>'
    + '<select id="rr-source-filter" onchange="window._rrFilter()"><option value="">全部来源</option><option value="manual">人工规则</option><option value="auto">自动发现规则</option></select>'
    + '<select id="rr-sort-by" onchange="window._rrFilter()" style="padding:6px 8px;border:none;border-bottom:1px solid #e2e8f0;font-size:10px;color:#475569;background:transparent;cursor:pointer"><option value="id">编号排序</option><option value="updated">更新时间排序</option></select>'
    + '</div>';

  h += '<details id="rr-standard" style="margin-bottom:10px;background:transparent;border:none;border-top:1px solid #e2e8f0;border-bottom:1px solid #e2e8f0;padding:10px 0;font-size:10px;line-height:20px;color:#334155"><summary style="font-weight:700;color:#16233a;cursor:pointer;font-size:10px">📐 精写编制标准（23字段完整版 · v6六类攻击角度）</summary>'
    + '<div style="margin-top:10px">'
    + '<p><b>疑点编制规则·税务疑点仅来源于数据矛盾</b>——疑点不是法律条文，不是会计知识，不是处理标准，而是数据之间的结构性矛盾。"该企业可能存在偷税风险"属于主观推测，无法直接核查；"银行账户全年收款5000万元但申报收入仅3000万元"属于客观数据矛盾，可立即启动核查——后者方为有效疑点。编制疑点的首要步骤：明确掌握哪些数据、这些数据之间应呈何种关系，关系不成立即构成疑点。</p>'
    + '<p><b>三种基本矛盾类型</b>——①应当相等但不等：资产负债表左右不平、增值税与所得税申报收入不一致、工资薪金与社保个税三源数据不一致（勾稽断裂类）。②应当存在但缺失：有销售收入无运输费用记录、持有房产无房产税申报记录、有在职员工无社保参保记录（数据缺失类）。③不应出现但出现：购进钢材却开具咨询服务发票、新设企业三个月内开票5000万元、凌晨时段集中开票（模式异常类——"应当"的基准来源于行业统计与行为规律分析，基准本身亦为数据，故本质上仍属数据矛盾）。所有疑点均为上述三种矛盾的组合表现。</p>'
    + '<p><b>编制三步法</b>——第一步·界定数据矛盾点：以一句话明确两组数据的对比关系（"银行账户收款总额与增值税申报收入"为正确示例，"成本费用不合规"为错误示例），无法用一句话界定矛盾关系的疑点不成立。第二步·穷举合法解释：每种合法情形须明确可排除该解释的具体证据要求，企业无法提供相应证据时矛盾方可升级为风险。第三步·构建定性路径：铁证级→认定处理 / 强证据级→涉嫌，继续调查 / 线索级→存疑，不纳入正式结论。</p>'
    + '<p><b>三问检查标准</b>——完成每条规则编制后须逐项自检：①能否被系统自动识别（系统无法自动扫描的规则不具备可操作性）；②是否具备明确的核查路径（触发后可确定应调取何种凭证、查阅何种资金流水、询问相关人员）；③是否存在合法的排除途径（企业能否提供证据消除疑点，防止误判合规企业）。</p>'
    + '<p><b>编制顺序</b>——首先编制四流矛盾（资金流=银行流水，发票流=发票数据，账载流=纳税申报表，实物流=经营数据），其次编制税种间矛盾，再次编制财务数据与实物数据矛盾，最后编制行业特有矛盾。疑点库是数据矛盾关系网络，不是法规汇编，不是会计教材——立案标准、偷税与少缴的区分等属于查实后的定性知识，存放于稽查知识库，不纳入疑点库。</p>'
    + '<p><b>铁律0·数据矛盾唯一来源</b>——疑点仅来源于数据矛盾：应当相等但不等、应当存在但缺失、不应出现但出现。无法表述为"X与Y对不上"的条目不构成疑点。</p>'
    + '<p><b>铁律1·字段齐全</b>——23项字段缺一不可。基础字段9项为系统自动填充，深度字段12项须人工精写。</p>'
    + '<p><b>铁律2·穷举至稽查终点</b>——穿透追问须穷举至稽查终点：问题间因果递进、环环相扣，直至证实违法行为存在或排除违法行为存在为止。推理链须推导至定性落地或排除风险为止。追问数量和推理层数由因果链条的自然长度决定。</p>'
    + '<p><b>铁律3·定级映射</b>——定性路径三条路径必须对应证据链三档定级标准：无法证明→线索级 / 部分证明→强证据级 / 完整证明→铁证级。</p>'
    + '<p><b>铁律4·角色分明</b>——稽查重点属于策略层（舞弊手法预判）；穿透追问属于执行层（讯问问题清单）。现象描述属于现象层；风险表格属于影响层。稽查处理为稽查部门视角；整改建议为企业视角。</p>'
    + '<p><b>铁律5·证据可校验</b>——推理链每层须标注依赖证据类型；证据清单须标注优先级（必须获取/应当获取/可以获取）；触发指标须包含行业差异阈值。</p>'
    + '<p><b>一、基础字段（9项·每项必填）</b></p>'
    + '<p><b>① id（异常编号）</b>——{类型前缀}-{三位序号}，类型划分: AN=隐匿收入/VC=虚列成本/VI=虚开发票/ST=少缴税款/OT=其他。系统执行：作为发现溯源锚点，稽查分析中通过 finding._rule_id 关联规则与发现；跨域线索链、证据链、分析链通过 rule_refs 串联规则；规则删除或修改时同步更新全部关联引用，防止无效引用。</p>'
    + '<p><b>② item（异常名称）</b>——采用受控词表统一命名，禁止同义异名。系统执行：作为规则匹配主键，稽查分析执行三级匹配策略——①发现类型与名称精确匹配后注入深度字段；②精确匹配失败后通过语义相似度进行二次匹配（阈值0.55，优先保证准确率）；③主动扫描时按名称防止重复生成。受身份锁保护，任何自动化流程不得修改名称。</p>'
    + '<p><b>③ category（所属类别）</b>——五类之一: 隐匿收入/虚列成本/虚开发票/少缴税款/其他违规。系统执行：作为定性分类载体，报告按类别汇总违规性质。受身份锁保护。</p>'
    + '<p><b>④ level（风险等级）</b>——极高/高/中/低/良好。与合规度评分对应: 极高<40分/高40-60/中60-80/低80-90/良好>90。系统执行：作为发现风险等级来源，扫描触发型发现依据疑点非结论原则统一标注为中风险待人工核实；校验程序强制重罪条目不低于高风险、评分与等级锚点保持一致。</p>'
    + '<p><b>⑤ score（风险评分）</b>——1-10分。评分锚定: 10=系统性造假/金额重大/主观故意; 5=中等风险/需补充证据; 1=低风险/小金额/偶发性。系统执行：作为发现评分与排序依据，报告按分值降序排列；主动扫描注入的发现评分上限为5分（金额维度已验证、业务属性待核实）；8分以上纳入高风险清单。</p>'
    + '<p><b>⑥ check_frequency（核查频率）</b>——高频=每户必查; 中频=匹配行业时查; 低频=特定条件触发时查。系统执行：高频及中频规则参与常规扫描（触发置信度阈值0.85）；低频规则仅在结构化条件强力触发（置信度不低于0.95）时生成发现，防止低频规则全量扫描导致误报。</p>'
    + '<p><b>⑦ policy_ref（法律依据）</b>——引用现行有效法律法规，统一标注"现行有效的《XX法》（XX年版）第X条"，保留条款编号确保稽查引用精确性。法律条文不作为永久性固定内容：每条引用须经法律时效性核查程序验证，末尾强制附加核验日期。法律法规修订时，核查程序自动识别废止法规并替换为现行有效法条，无需人工维护对照表。系统执行：作为发现的法律依据，直接注入发现数据与报告。</p>'
    + '<p><b>⑧ tax_impact（税务影响）</b>——区分最低影响与典型影响: 税种（最低补税X万元，典型补税Y万元）。系统执行：作为报告税负测算与处置建议段落的数据来源，随发现注入。</p>'
    + '<p><b>⑨ applicable_condition（适用条件）</b>——五维度结构化: 行业限制+纳税人资质+规模门槛+时间条件+金额门槛，非全部必填。系统执行：作为触发前置闸门，扫描前解析五维度中当前可判定的维度——行业限制与企业识别行业比对，限定行业不符直接拦截，防止跨行业误报；资质、规模、时间、金额维度随对应数据源接入逐步启用硬校验。</p>'
    + '<p><b>二、来源标记（2项）</b></p>'
    + '<p><b>⑩ source（来源）</b>——空=人工精写 / 系统发现 / 智能生成。系统执行：来源标记与身份锁保护对象。系统自动发现规则须经人工确认转正；报告区分人工精写、系统发现、智能生成三类来源的可信度。</p>'
    + '<p><b>⑪ auto_type（自动发现类型）</b>——行业基准校准/购销倒挂/毛利为负/缺失数据/综合异常/未知模式。系统执行：自动发现分类标记。</p>'
    + '<p><b>三、深度字段（12项·精写核心）</b></p>'
    + '<p><b>一、推理链（direction）</b>——推理至稽查终点。根据攻击角度选择推理深度：A类（商业逻辑）→2-3层，因矛盾本身已接近自证；B类（物理事实）→加物理验证层，用测量替代推理；C类（数据穿透）→至少4层，含追溯断裂时点+科目穿透定位。所有类型必须包含追溯首次异常时点层。最后一层落地到具体法条编号。层间因果递进，每层格式：【推理第N层: XX法则】依赖证据: XX → 结论: XX。三种结束条件: 定性落地/证据尽头/逻辑闭环。标杆参照: #1717(5层到§63)、#1(4层到§63/§64)。</p>'
    + '<p><b>二、穿透追问（drill_questions）</b>——穷举至稽查终点。三组递进（事实→证据→逻辑），每组穷举至无新有效追问。必须包含至少1条物理常识类追问——用不可辩驳的物理事实堵死辩解空间（如\"仓库能不能装下\"\"仓储费为什么没增加\"）。格式: Q{N}:{问题}→潜台词:{稽查真实意图}。A:{应对话术}。追问末尾必须包含穷举完成判定——\"事实六要素全覆盖/证据四流全追问/逻辑所有解释全排除→三问全答是→穷举完成\"。标杆: #1716(14问含5条物理追问)、#1717(15问含仓库容积+仓储费双验证)。</p>'
    + '<p><b>三、现象描述（phenomena）</b>——矛盾一句话说清：用\"X vs Y——哪里对不上\"格式。一句话说不清=疑点不成立。每种表现须含具体数据特征（%和绝对值），使系统可据此扫描。含排除条件明确边界。标杆: #1717\"已收款+未申报\"五个字钉死。#1716\"有销售+有收款+无运费=物理上不可能\"。</p>'
    + '<p><b>四、稽查重点（focus）</b>——策略层：舞弊手法预判，不直接用于提问。格式: 舞弊手法名称: 具体操作方式 → 识别要点，以①②③④逐条标注。与穿透追问的分工: focus为策略层预判，drill_questions为将预判转化为讯问问题的执行层。系统执行：策略层预判，命中后注入报告舞弊手法提示段落。</p>'
    + '<p><b>五、正常业务解释（normal_reason）</b>——穷举全部合法情形。禁止笼统，须具体到文件类型。必须标注最常见解释作为优先核验素材。穷举完毕标注\"穷举说明：已穷举全部合法情形\"。五问自检全答否=穷举完成。标杆: #2写了5种已穷举、#1717从4种吸收到5种。</p>'
    + '<p><b>六、定性路径（determination）</b>——平铺文本，严禁JSON。三路径各有进入条件：无法证明→线索级(单源)→存疑不入结论；部分证明→强证据级(2源)→涉嫌标注部分闭环；完整证明→铁证级(≥3源)→认定可作处罚依据。终极目标：要么铁证如山要么自证清白——存疑是中途站不是终点站。有量化阈值须加阈值以下处理分支。末尾附应对总原则。</p>'
    + '<p><b>七、风险表格（risk_table）</b>——覆盖实际涉及税种或维度，不设数量下限。跨税种≥2个逐税种列明，仅单一税种不强制跨税种。每行: 税种:具体风险描述 | 影响程度:核心/次要/间接。</p>'
    + '<p><b>八、证据清单（evidence）</b>——四层框架+AB场景+金额分级+优先级标注。首层命名必须贴合疑点类型（禁止全用货物流）：实物→货物流/账务→账实核对层/申报→申报数据层/费用→费用真实性层/关联→关联关系与定价层。排雷层与正常解释联动。标杆: #2费用真实性层(凭证量)、#1716货物流与财务流核对层。</p>'
    + '<p><b>九、触发指标（threshold）</b>——量化阈值+四维前置条件+三色预警必含。阈值含行业调整值（如建筑730天/商贸90天/服务180天/制造540天）。预警按严重度升档：黄→橙→红。标杆: #1717黄(365-540天)→橙(540-730天)→红(>730天)含四个行业调整值。</p>'
    + '<p><b>十、稽查动作（action）</b>——物理验证优先于纸面比对。≥3步含1项现场核查。B类(物理事实)至少2步物理验证。每步: 动作类型+具体操作+预期产出。标杆: #1716含装卸能力实测+物流公司走访(5步)；#1717吸收后到7步含仓库容积实测+仓储费穿透。</p>'
    + '<p><b>十一、稽查处理（suggestion）</b>——稽查部门视角。固定格式: 定性→补税（分税种+金额）→滞纳金（日万分之五+起止日期）→罚款（征管法条款+幅度）→移送标准（金额/情节门槛）。与定性路径结论保持一致。系统执行：稽查处置建议，直接进入发现与报告处置段落。</p>'
    + '<p><b>十二、整改建议（remedy）</b>——企业视角。三阶段含时间维度: 自查阶段（收到稽查通知前·主动补报可减轻处罚）→应对阶段（稽查进行中·含配合策略:如何配合、提供何种材料、如何说明）→制度阶段（稽查结束后长期建设·内控制度、发票管理、合同规范）。与稽查处理的分工: suggestion为稽查部门视角，remedy为企业视角。系统执行：整改建议，进入报告企业视角段落，与suggestion分视角呈现。</p>'
    + '<p><b>四、穷举完成判定标准（数量由业务复杂程度决定，非模板规定）</b></p>'
    + '<p><b>核心原则：</b>决定数量的不是模板，是业务本身的复杂程度。复杂疑点追问可达数十条、推理链可达五层；简单疑点追问数条、推理两层即可到达终点。数量是编制完成后的自然结果，不是编制前的硬性规定——按实际需要编制，不虚增、不凑数。</p>'
    + '<p><b>1. 追问穷举——不设固定数量上限，以问无可问为准：</b>数量由三维覆盖度决定。事实层：交易六要素全覆盖（主体、客体、时间、地点、方式、参与人），任一要素空白即仍有追问空间。证据层：四流（合同流、货物流、资金流、发票流）每环节全追问（证据类型、来源真实性、四流一致性比对），任一流关键证据缺失即仍有追问空间。逻辑层：所有合理商业解释全部排除（合同特殊条款、行业惯例、交易对手特殊情况、关联方关系），无法提出新解释即为完成。最终判定标准：对"是否还有未覆盖的交易要素""四流是否还有未追问的证据环节""对方是否还可能提出未涉及的解释"三个问题全部回答"否"，即穷举完成。追问数量为3条或13条均属正确答案。</p>'
    + '<p><b>2. 推理链层数——不设固定层数上限，以推无可推为准：</b>由因果链条的自然长度决定。满足任一结束条件即停止：①定性落地（指向偷税、少缴、虚开或不违规，无法再追问后续推理）；②证据尽头（下一层证据无法获取，标注"证据断点"）；③逻辑闭环（回到第一层前提）。复杂异常自然需4-5层，中等异常3-4层，简单异常2-3层，超出因果链条自然长度的增层为无效推导。</p>'
    + '<p><b>3. 正常业务解释——不设固定数量上限，以穷举完毕为准：</b>"异常"本身意味着不符合正常商业逻辑，合法解释过多则其本身即不构成异常。五个自问全部回答"否"即为完成（合同条款、行业惯例、交易对手特殊情况、税收政策特殊规定、不可抗力）。仅有0-3种时注明"已穷举全部合法情形"；超过5种时须重新审视该项是否确实构成异常。</p>'
    + '<p><b>4. 风险表格——不设固定税种下限，以实际涉及为准：</b>影响多少个税种列明多少个，不设下限。跨税种不少于2个的逐税种列明并区分核心、次要、间接影响；仅涉及单一税种的注明"仅影响XX税，不涉及其他"，不得为凑数虚构跨税种影响。</p>'
    + '<p><b>字段数量决定表：</b>⑫推理链——因果链条的自然长度，下限2层（简单情形如实编制），无上限（推导至定性落地为止）。⑬穿透追问——交易要素+四流+解释覆盖度，不设下限（穷举完毕即停止），以问无可问为准。⑯正常业务解释——实际合法情形数量，下限0（确实无合法情形则如实注明），穷举完毕为准。⑱风险表格——实际涉及税种数量，下限1（单税种即列明单税种），全部涉及则全部列明。⑲证据清单——四流各环节证据数量，每层不少于1项必须获取证据，穷举完毕为准。㉑稽查动作——纸质比对至现场核查步骤数量，不少于3步且含1项现场核查，穷举完毕为准。</p>'
    + '<p>穿透追问须穷举至稽查终点（证实违法或排除违法），问题间因果递进、环环相扣。数量为因果链条的自然长度，非预设指标。按实际需要编制，不虚增、不凑数。</p>'
    + '<p style="margin-top:20px;padding-top:10px;border-top:2px solid #e2e8f0"><b>⚔️ 顶级精写方法论——六条攻击角度</b></p>'
    + '<p><b>A类·商业逻辑不可辩驳</b>——矛盾本身违反正常市场主体的经济理性，企业无法用行业惯例解释。开案成本最低，两证即可定案。标志：大额资金无偿存放、长期挂账不处理。代表规则：#1717（预收挂账）、#9（银行收款vs申报）、#1715（平台收款vs申报）。</p>'
    + '<p><b>B类·物理事实不可辩驳</b>——矛盾违反物理常识。不需要推理，只需要测量。追问用物理堵死辩解空间。标志：重量/体积与实际不符、能耗与产量不一致。代表规则：#1716（运输费缺失）、#20（存货周转率vs仓库容积）、#4（无形资产摊销为零）。</p>'
    + '<p><b>C类·数据异常需穿透</b>——矛盾是数据偏差而非必然违规，需逐层排除合法解释后定性。数量最多，涵盖面最广。代表规则：#1（资产负债表不平）、#5（四流不匹配）、#11（品名背离）、#15（费用增速vs收入增速）。</p>'
    + '<p><b>D类·关系网络不可辩驳</b>——矛盾不在一对数值之间，而在多个节点之间的环形关系。单节点视角一切正常，构建交易网络图谱后环形闭环暴露。标志：六员重叠、地址电话重叠、资金闭环回流。代表规则：#1718（进销交易闭环+资金回流）。</p>'
    + '<p><b>E类·法律义务真空</b>——矛盾不是两个数对不上，而是应该有的根本不存在。A的存在触发B的法定义务，但B=0。不是偏差，是法律义务的完全缺失。标志：有A无B、应有未有、零值异常。代表规则：#1719（代发工资vs社保人数缺口）。</p>'
    + '<p><b>F类·时序节奏异常</b>——矛盾不在数值本身，而在数值发生的时间节奏。数值比对看不出问题，时间分布统计暴露人为操纵。标志：月末突击、集中度指数偏高、红冲关联、进销时间差。代表规则：#1720（月末集中开票时间分布异常）。</p>'
    + '<p style="margin-top:20px;padding-top:10px;border-top:2px solid #e2e8f0"><b>✅ 十三条自检清单——十三勾全满即顶级精写</b></p>'
    + '<p>GS-1·矛盾一句话：数据矛盾点必须能用X vs Y——一句话说清。GS-2·推理至法条：每层标注依赖证据，最后一层落地到法条编号。GS-3·追问堵死物理极限：必须包含物理常识类追问。GS-4·三路径各有进入条件：单源/2源/≥3源不得笼统写。GS-5·证据四层命名贴合：首层必须贴合疑点类型，禁止全用货物流。GS-6·税负能算出具体数字：必须给出补税计算公式和金额区间。GS-7·触发含三色预警：黄/橙/红按严重度分档。GS-8·正常解释有最常见标注：合法解释中必须标注最常见解释。GS-9·核查动作含现场核查：≥3步含1项现场核查，物理验证优于纸面比对。GS-10·适用条件五维度：行业+资质+规模+时间+金额全覆盖。</p>'
    + '<p>GS-11·关联网络图谱化：涉及多主体交易的疑点必须构建节点-边关系图，查六员重叠+地址电话重叠+资金闭环+购销闭环。单节点视角无法发现环形矛盾。</p>'
    + '<p>GS-12·缺失因果链验证：缺失型疑点必须写明A存在→触发B义务→B=0的因果链。穷举合法免履行义务情形，逐人逐项提供证据。必须双线并查。</p>'
    + '<p>GS-13·时序集中度量化：时序异常型必须计算集中度指数=目标时段/全周期×100%。三重交叉验证：客户下单时间+红冲关联+物流收款时间差。</p>'
    + '<p style="margin-top:20px;padding-top:10px;border-top:2px solid #e2e8f0"><b>📝 逐字段编制法——原则 + 标杆案例 + 禁止写法</b></p>'
    + '<p><b>phenomena（现象描述）：</b>原则——矛盾一句话说清，用"X vs Y——哪里对不上"格式。一句话说不清=疑点不成立。标杆：#1717"已收款+未申报"（五个字钉死）、#1716"有销售+有收款+无运费=物理上不可能"。禁止：写"该企业可能存在偷税风险"——主观推测不可查。</p>'
    + '<p><b>direction（推理链）：</b>原则——每层标注依赖证据，最后一层落地到法条编号。加入"追溯首次异常时点"层——定位异常起点。标杆：#1第四层"资金流交叉验证→账外循环→偷税(§63)"；#1717第五层到§63。禁止：不到法条就结束、各层无因果递进。</p>'
    + '<p><b>drill_questions（穿透追问）：</b>原则——三组递进（事实→证据→逻辑），必须含物理常识类追问。追问末尾必须有"三问全答是→穷举完成"判定。标杆：#1716 Q3"工厂有没有能吊装这个吨位设备的行车"——装车能力是物理事实，没有就是没有。禁止：追问缺乏攻击性、没有物理验证。</p>'
    + '<p><b>determination（定性路径）：</b>原则——三条路径各有进入条件（单源/2源/≥3源），禁止笼统写"根据证据分别处理"。有量化阈值必须加阈值以下处理分支。标杆：#1717路径一仅账龄→存疑、路径二账龄+收款→涉嫌、路径三账龄+收款+外调→认定。禁止：使用JSON dict格式。</p>'
    + '<p><b>evidence（证据清单）：</b>原则——四层框架，首层命名贴合疑点类型。实物交易→货物流、账务断裂→账实核对层、纯申报→申报数据层、成本费用→费用真实性层、关联交易→关联关系与定价层。标杆：#2"费用真实性层"（凭证量异常）、#1716"货物流与财务流核对层"。禁止：全部套用"货物流"。</p>'
    + '<p><b>threshold（触发指标）：</b>原则——量化阈值+行业差异+四维前置+三色预警。标杆：#1717"账龄≥365天+单笔≥5万+总额≥10万，行业调整：建筑730天/商贸90天/服务180天/制造540天，预警：黄(365-540天)→橙(540-730天)→红(>730天)"。禁止：笼统写"超过一定期限"不给具体数值。</p>'
    + '<p><b>tax_impact / suggestion（税负与处理）：</b>原则——必须给出具体补税计算公式和金额区间，稽查人员拿规则即可测算。标杆：#1717"增值税=挂账余额÷(1+税率)×税率；企业所得税=挂账余额×应税利润率×25%"、tax_impact"最低约3万，典型65-390万"。禁止：笼统写"补缴相关税款"不给金额。</p>'
    + '<p><b>normal_reason（正常解释）：</b>原则——穷举全部合法情形，每种格式"{情形}——需提供:{具体文件类型}"。必须标注"最常见解释"。穷举完毕标注"穷举说明：已穷举全部合法情形"。标杆：#2写了5种已穷举。禁止：写"提供相关证明"笼统表述、不标最常见解释。</p>'
    + '<p><b>action（稽查动作）：</b>原则——物理验证优先于纸面比对。≥3步含1项现场核查。B类(物理事实)至少2步物理验证类。标杆：#1716含"装卸能力实测"和"物流公司走访"共5步；#1717吸收后到7步含仓库容积实测+仓储费用穿透。禁止：只有纸面比对没有现场核查、写"现场核查"不写具体操作。</p>'
    + '<p style="margin-top:20px;padding-top:10px;border-top:2px solid #e2e8f0"><b>🔄 互相学习矩阵——编制任何规则时可向标杆借技术</b></p>'
    + '<p><b>从 #1717 借：</b>矛盾短句钉死技术、税负公式具体化、三色预警等级设计、行业调整值精细化。</p>'
    + '<p><b>从 #1716 借：</b>物理常识类追问攻击、物理验证类核查动作、追问结束条件结构化验证。</p>'
    + '<p><b>从 #1 借：</b>推理链追溯断裂时点、科目穿透定位技术、舞弊手法预判详细度。</p>'
    + '<p><b>从 #2 借：</b>证据四层命名贴合度、正常解释穷举充分性、话术策略对主观故意的测试。</p>'
    + '<p><b>从 #1718 借：</b>网络图谱构建技术、六员交叉比对、资金闭环路径追踪、隐性关联分层穿透、交易实质验证方法论。</p>'
    + '<p><b>从 #1719 借：</b>缺失因果链表述、合法免履行义务穷举、双线并查技术（人数+基数）、逐人归因证据清单、违法后果定量算账。</p>'
    + '<p><b>从 #1720 借：</b>时间分布统计技术、集中度指数量化、红冲关联检测、三重交叉验证（下单+红冲+物流）、进销时间差分析。</p>'
    + '<p style="margin-top:20px;padding-top:10px;border-top:2px solid #e2e8f0"><b>📊 1条深度精写规则全景索引</b></p>'
    + '<p>A类(5条)：#1717预收挂账(15问)、#9银行收款vs申报(8问)、#10关联版(6问)、#1711银行vs应税(7问)、#1715平台收款(8问)</p>'
    + '<p>B类(4条)：#1716运输费缺失(14问)、#20存货周转率(9问)、#4无形资产摊销(8问)、#19其他应收款(9问)</p>'
    + '<p>C类(18条)：#1资产负债表(15问)、#2凭证量异常(10问)、#3固定资产折旧(8问)、#5四流不匹配(15问)、#6红冲退款(8问)、#7票面规范(8问)、#8税号缺失(9问)、#11品名背离(13问)、#12三流不一致(9问)、#13毛利率偏离(9问)、#14申报毛利率(8问)、#15费用增速(10问)、#16招待费限额(8问)、#17三表不一致(8问)、#18收入成本增速(8问)、#1712外币汇率(8问)、#1713银行偏差10万(6问)、#1714平台保证金(7问)</p>'
    + '<p>D类(1条)：#1718资金闭环回流(14问三组：关系穿透→资金追踪→交易实质)</p>'
    + '<p>E类(1条)：#1719社保人数缺口(14问三组：基数确认→缺口归因→后果算账)</p>'
    + '<p>F类(1条)：#1720月末集中开票(14问三组：时间确认→原因追问→后果算账)</p>'
    + '<p style="margin-top:20px;padding-top:10px;border-top:2px solid #e2e8f0"><b>🔧 标准升级判定规则（发现标准 v1.0 · 双层自举系统）</b></p>'
    + '<p style="font-weight:700;color:#8B0000;font-size:10px;margin:4px 0 10px">发现标准=元标准。精写编制标准告诉你怎么写疑点；发现标准告诉你在写疑点时怎么判断精写编制标准是否需要升级。发现标准自身也随精写编制标准一起升级，升级后能识别更多缺口类型。</p>'
    + '<p style="font-weight:700;color:#8B0000"><b>核心原理 · 双层自举：</b></p>'
    + '<p style="font-weight:700;color:#8B0000">第1层（标准升级层）：精写每条疑点→逐维判定缺口→触发精写编制标准升级</p>'
    + '<p style="font-weight:700;color:#8B0000">第2层（自举层）：精写编制标准升级后→审查发现标准是否有新盲区→发现标准自身升级</p>'
    + '<p style="font-weight:700;color:#8B0000;margin-top:10px"><b>七维判定（DIM-1~7）：</b></p>'
    + '<p style="font-weight:700;color:#8B0000;font-size:10px;line-height:1.9">①攻击角度覆盖(能否归入A-F marker) ②GS自查项覆盖(每项是否有效检查) ③字段格式指导(是否足以指导编制) ④特殊类型编制技术(新技术是否已收录) ⑤跨类型适配(混合类型有无衔接指导) ⑥边界定义(判定模糊处) ⑦发现标准自身盲区(是否需新增维度)</p>'
    + '<p style="font-weight:700;color:#8B0000;margin-top:10px"><b>六步判定流程：</b></p>'
    + '<p style="font-weight:700;color:#8B0000;font-size:10px;line-height:1.9">①规则精写完成→②逐维过审(每条独立逐DIM-1~7判定)→③捕捉缺口(记录规则ID+字段+缺口描述)→④聚合归类(两层聚合：层1批内交叉比较+层2跨批去重比较)→⑤触发升级(共性缺口≥1则升级；已有缺口不重复升级)→⑥事后审查(DIM-7自检)</p>'
    + '<p style="font-weight:700;color:#8B0000;margin-top:10px"><b>跨批去重规则（核心原则：不缺不重）：</b></p>'
    + '<p style="font-weight:700;color:#8B0000;font-size:10px;line-height:1.9"><b>层1·批内交叉比较</b>——同一DIM下多条规则触发同一类缺口→合并为一个；不同类缺口→各自独立；不同DIM→永不合并</p>'
    + '<p style="font-weight:700;color:#8B0000;font-size:10px;line-height:1.9"><b>层2·跨批去重比较</b>——当前批次缺口vs历史批次已检出缺口：①同一缺口跨批匹配→已有缺口，不重复升级，追加触发记录 ②首次出现的新缺口→计入升级计数 ③只被一条规则触发且所有批次仅此一次→个案·待观察</p>'
    + '<p style="font-weight:700;color:#8B0000;font-size:10px;line-height:1.9"><b>举例</b>——#1~#5已检出DIM-1法律事实缺口（#4触发）。#6~#10中#8又触发同一DIM-1法律事实→已有缺口不重复升级。但#7触发DIM-2的GS-5新问题（#1~#5中DIM-2只捕获GS-3）→新缺口。若批内仅#7一条触发→计为个案·待观察，后续批次再次出现→自动升级为共性缺口</p>'
    + '<p style="font-weight:700;color:#8B0000;margin-top:10px"><b>四条自举规则（SU-1~4）：</b></p>'
    + '<p style="font-weight:700;color:#8B0000;font-size:10px;line-height:1.9">SU-1新维度追加(缺口无法归入DIM-1~7→新增DIM-N) | SU-2现有维度细化(不够精确→修订) | SU-3流程参数调整(效率不理想→调N值) | SU-4版本跟踪(任何修改→更新版本号和历史)</p>'
    + '<p style="font-weight:700;color:#8B0000;margin-top:10px"><b>实战验证 · 精写#1~#5后的缺口检出：</b></p>'
    + '<p style="font-weight:700;color:#8B0000;font-size:10px;line-height:1.9">DIM-1触发(B类marker需扩展法律事实子类型·#4) | DIM-2触发(GS-3需增加非物理类例外条款·#1#4#5) | DIM-3触发(threshold维度替换指导+追溯时点层无GS检查·#2#3#4#5) | DIM-4触发(人力产能验证技术未分类·#2) | DIM-5触发(C含B类的编制优先级·#3) | DIM-6未触发(0种正常解释边界暂未暴露) | DIM-7未触发(DIM-1~6已全覆盖)→5项缺口全部捕获，发现标准v1.0暂不升级</p>'
    + '<p style="font-weight:700;color:#8B0000;font-size:10px;margin-top:10px">当前精写编制标准为v6（六类攻击角度+十三项自查），发现标准为v1.0。完整内容见 engine/memory.py → standard_upgrade_criteria。</p>'
    + '<p style="color:#64748b;font-size:10px">完整详细内容见 engine/memory.py → gold_standard_decoded → rule_index。每条规则的完整精写见 static/tax_risk_rules_local_export.json。</p>'
    + '</div>'
    + '</details>';

  h += '<div id="rr-list"></div>';
  h += '</div>';  // rr-list-view 结束
  h += '<div id="rr-detail-view" style="display:none"></div>';

  container.innerHTML = h;

  // 加载数据
  loadTaxRiskRules();

  var dataUrl = '/static/tax_risk_rules_local_export.json';

  // 加载数据
  fetch(dataUrl + '?' + Date.now())
    .then(function(r) { return r.json(); })
    .then(function(rules) {
      window._rrData = rules;
      // 更新自动发现规则计数（自动面板数据已分离到独立文件，计数始终准确）
      var autoCount = rules.filter(function(rl){ return rl.type === 'auto_signal' || rl.source === '系统发现' || !!rl.auto_type; }).length;
      var acEl = document.getElementById('au-auto-count'); if (acEl) acEl.textContent = autoCount;
      var cats = {};
      var total = 0, high = 0, mid = 0, low = 0, good = 0;
      rules.forEach(function(rl) {
        total++; 
        var lv = rl.level || rl.level || '';
        if (lv.indexOf('极高') >= 0 || lv.indexOf('高') >= 0) high++;
        else if (lv.indexOf('中') >= 0) mid++;
        else if (lv.indexOf('低') >= 0) low++;
        else good++;
        var cat = rl.category || rl.分类 || '其他';
        cats[cat] = (cats[cat] || 0) + 1;
      });

      // 分类筛选下拉已改为固定13监控维度选项（不再从旧category动态填充）

      // 加载三链信息（可执行链的步数/维度）
      Promise.all([
        fetch('/static/cross_domain_clues.json?_t=' + Date.now()).then(function(r){return r.json();}).catch(function(){return[];}),
        fetch('/static/cross_domain_evidence.json?_t=' + Date.now()).then(function(r){return r.json();}).catch(function(){return{};}),
        fetch('/static/cross_domain_analysis.json?_t=' + Date.now()).then(function(r){return r.json();}).catch(function(){return{};})
      ]).then(function(datas){
        var clueData = datas[0];
        var evidRaw = datas[1]; var evidData = Array.isArray(evidRaw) ? evidRaw : (evidRaw.evidence_chains || []);
        var analRaw = datas[2]; var analData = Array.isArray(analRaw) ? analRaw : (analRaw.analysis_chains || []);
        window._rrChainInfo = {};
        clueData.forEach(function(c){
          var rid = String(c.rule_id || '');
          if (rid) { window._rrChainInfo[rid] = window._rrChainInfo[rid] || {}; window._rrChainInfo[rid].c_steps = (c.steps || []).length; }
        });
        evidData.forEach(function(e){
          var rid = String(e.rule_id || '');
          if (rid) { window._rrChainInfo[rid] = window._rrChainInfo[rid] || {}; window._rrChainInfo[rid].e_dims = (e.steps || []).length; }
        });
        analData.forEach(function(a){
          var rid = String(a.rule_id || '');
          if (rid) { window._rrChainInfo[rid] = window._rrChainInfo[rid] || {}; window._rrChainInfo[rid].a_steps = (a.steps || []).length; }
        });
        window._rrFilter();
      });

      var rrSortBy = 'id';
window._rrSort = function(rules, sortBy) {
  if (sortBy === 'updated') {
    return rules.slice().sort(function(a,b){return (b.updated_at||'').localeCompare(a.updated_at||'');});
  }
  return rules.slice().sort(function(a,b){return (a.id||0)-(b.id||0);});
};
window._rrFilter = function() {
        var kw = (document.getElementById('rr-search-input') && document.getElementById('rr-search-input').value || '').toLowerCase();
        var ct = document.getElementById('rr-cat-filter') && document.getElementById('rr-cat-filter').value || '';
        var sc = document.getElementById('rr-source-filter') && document.getElementById('rr-source-filter').value || '';
        var list = document.getElementById('rr-list');
        if (!list) return;
        var sb = document.getElementById('rr-sort-by'); var sortBy = sb ? sb.value : 'id';
        var filtered = window._rrSort(rules, sortBy).filter(function(rl) {
          var txt = (rl.item || '') + ' ' + (rl.direction || '') + ' ' + (rl.focus || '') + ' ' + (rl.action || '') + ' ' + (rl.policy_ref || '') + ' ' + (rl.id || '');
          if (kw && txt.toLowerCase().indexOf(kw) < 0) return false;
          if (ct && (rl.monitor_category || '') !== ct) return false;
          if (sc) {
            var isAuto = rl.source === '系统发现' || rl.type === 'auto_signal';
            if (sc === 'auto' && !isAuto) return false;
            if (sc === 'manual' && isAuto) return false;
          }
          return true;
        });
        if (filtered.length === 0) {
          list.innerHTML = '<div style="text-align:center;padding:24px;color:#94a3b8">未找到匹配的规则</div>';
          return;
        }
        list.innerHTML = window._rrTable(filtered);
      };
    })
    .catch(function(e) {
      var list = document.getElementById('rr-list');
      if (list) list.innerHTML = '<div style="text-align:center;padding:24px;color:#dc2626">规则库加载失败：' + escHtml(e.message) + '</div>';
    });
}

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

var _currentSort = 'time';  // 当前排序模式

function sortAndRenderRules() {
  var sel = document.getElementById('rr-sort-filter');
  _currentSort = sel?.value || 'time';
  renderTaxRiskRulesList();
  filterRules();
}

async function promoteAutoRule(ruleId, btn) {
  if (!confirm('确定将这条自动发现规则升级为正式规则？')) return;
  btn.disabled = true;
  btn.textContent = '...';
  try {
    var r = await fetch('/api/tax-risk-rules/promote-auto-rule?rule_id=' + ruleId, { method: 'POST' });
    var d = await r.json();
    if (d.ok) {
      btn.textContent = '✓ 已确认';
      btn.style.background = '#059669';
      btn.style.color = '#fff';
      // 2秒后刷新规则列表
      setTimeout(function(){ loadTaxRiskRules(); }, 1500);
    } else {
      alert(d.message || '操作失败');
      btn.disabled = false;
      btn.textContent = '✗ 重试';
    }
  } catch(e) {
    btn.disabled = false;
    btn.textContent = '✗ 重试';
  }
}

// ═══ 规则编辑面板 ═══
function toggleRuleEdit(ruleId, btn) {
  var card = btn.closest('[data-rule-id]');
  if (!card) return;
  var existing = card.querySelector('.rr-edit-panel');
  if (existing) { existing.remove(); return; }  // 关闭
  // 读取当前值
  var rule = (taxRiskRulesData || []).find(function(r){ return String(r.id||'') === ruleId; });
  if (!rule) return;
  var fields = [
    {k:'item',label:'指令名称',v:rule.item||''},
    {k:'level',label:'风险等级',v:rule.level||'',type:'select',opts:['高风险','中风险','低风险','良好']},
    {k:'score',label:'评分',v:rule.score||''},
    {k:'detail',label:'详细标准',v:rule.detail||'',ta:true},
    {k:'suggestion',label:'税务合规建议',v:rule.suggestion||'',ta:true},
    {k:'evidence',label:'所需佐证',v:rule.evidence||'',ta:true},
    {k:'tax_impact',label:'税务影响',v:rule.tax_impact||'',ta:true},
    {k:'policy_ref',label:'法律依据',v:rule.policy_ref||'',ta:true},
    {k:'category',label:'分类',v:rule.category||''},
    {k:'dataSource',label:'数据来源',v:rule.dataSource||''},
    {k:'detectable',label:'可检测性',v:rule.detectable||''},
  ];
  var h = '<div class="rr-edit-panel" style="margin:12px 0;padding:16px;background:#f8fafc;border:1px solid #e2e8f0;">';
  h += '<div style="font-size:10px;font-weight:600;color:#1e293b;margin-bottom:12px">✏️ 编辑规则 ' + ruleId + '</div>';
  fields.forEach(function(f){
    h += '<div style="margin-bottom:8px"><span style="font-size:10px;color:#94a3b8">' + f.label + '</span>';
    if (f.type === 'select') {
      h += '<select id="rr-edit-' + f.k + '" style="width:100%;font-size:10px;padding:4px 8px;border:1px solid #e2e8f0;border-radius:4px;margin-top:2px">';
      (f.opts||[]).forEach(function(o){ h += '<option ' + (o===f.v?'selected':'') + '>' + o + '</option>'; });
      h += '</select>';
    } else if (f.ta) {
      h += '<textarea id="rr-edit-' + f.k + '" rows="2" style="width:100%;font-size:10px;padding:4px 8px;border:1px solid #e2e8f0;border-radius:4px;margin-top:2px;resize:vertical">' + escHtml(String(f.v)) + '</textarea>';
    } else {
      h += '<input id="rr-edit-' + f.k + '" value="' + escHtml(String(f.v)) + '" style="width:100%;font-size:10px;padding:4px 8px;border:1px solid #e2e8f0;border-radius:4px;margin-top:2px">';
    }
    h += '</div>';
  });
  h += '<div style="display:flex;gap:8px;margin-top:12px">';
  h += '<button onclick="saveRuleEdit(\'' + ruleId + '\',this)" style="font-size:10px;padding:5px 16px;border:none;border-radius:4px;background:#2563eb;color:#fff;cursor:pointer;font-weight:600">保存</button>';
  h += '<button onclick="toggleRuleEdit(\'' + ruleId + '\',this)" style="font-size:10px;padding:5px 16px;border:1px solid #e2e8f0;border-radius:4px;background:#fff;color:#64748b;cursor:pointer">取消</button>';
  h += '</div></div>';
  card.insertAdjacentHTML('beforeend', h);
}

async function saveRuleEdit(ruleId, btn) {
  var card = btn.closest('[data-rule-id]');
  if (!card) return;
  var fields = ['item','level','score','detail','suggestion','evidence','tax_impact','policy_ref','category','dataSource','detectable'];
  var body = {rule_id: ruleId};
  fields.forEach(function(k){
    var el = card.querySelector('#rr-edit-'+k);
    if (el) body[k] = el.value || '';
  });
  btn.disabled = true;
  btn.textContent = '保存中...';
  try {
    var r = await fetch('/api/tax-risk-rules/update-rule', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    var d = await r.json();
    if (d.ok) {
      var panel = card.querySelector('.rr-edit-panel');
      if (panel) panel.innerHTML = '<div style="color:#059669;font-weight:600;font-size:10px;padding:8px">✓ 已保存（' + d.changed.length + '字段）· 1.5秒后刷新</div>';
      setTimeout(function(){ loadTaxRiskRules(); }, 1500);
    } else { alert(d.message); btn.disabled = false; btn.textContent = '保存'; }
  } catch(e) { btn.disabled = false; btn.textContent = '重试'; }
}

async function batchRefreshRules(btn) {
  if (!confirm('统一刷新全部人工规则的时效标记？此操作会备份原文件。')) return;
  btn.disabled = true;
  btn.textContent = '刷新中...';
  try {
    var r = await fetch('/api/tax-risk-rules/batch-refresh', {method:'POST'});
    var d = await r.json();
    if (d.ok) { alert(d.message); loadTaxRiskRules(); }
    else { alert(d.message); btn.disabled = false; btn.textContent = '🔄 统一刷新政策法律'; }
  } catch(e) { btn.disabled = false; btn.textContent = '重试'; }
}

function filterRules() {
  var search = (document.getElementById('rr-search')?.value || '').toLowerCase();
  var cat = document.getElementById('rr-cat-filter')?.value || '';
  var rtype = document.getElementById('rr-type-filter')?.value || '';
  
  var listEl = document.getElementById('rr-list');
  if (!listEl) return;
  
  var allCards = listEl.querySelectorAll('[data-rule-id]');
  var visible = 0;
  
  allCards.forEach(function(card) {
    var text = (card.textContent || '').toLowerCase();
    var ruleCat = card.getAttribute('data-monitor') || '';
    var ruleType = card.getAttribute('data-type') || '';
    var triggered = card.getAttribute('data-triggered') === '1';
    
    var matches = true;
    if (search && text.indexOf(search) < 0) matches = false;
    if (cat && ruleCat !== cat) matches = false;
    if (rtype && ruleType !== rtype) matches = false;
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
    var resp = await fetch('/api/tax-risk-rules/data');
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    var rules = await resp.json();
    if (!Array.isArray(rules) || rules.length === 0) throw new Error('数据为空');
    taxRiskRulesData = rules;
    try { localStorage.setItem('taxRiskRulesData', JSON.stringify(rules)); } catch(e) {}
    // 记录数据更新时间（从HTTP响应头取Last-Modified）
    try {
      var lm = resp.headers.get('Last-Modified');
      if (lm) { window._rulesUpdateTime = lm; }
    } catch(e) {}
    
    // 先加载触发溯源数据，再渲染
    await loadTriggeredRules();
    renderTaxRiskRulesList();
  } catch (e) {
    var el = document.getElementById('rr-list');
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
  var listEl = document.getElementById('rr-list');
  var statsEl = document.getElementById('risk-rules-stats');
  if (!listEl) return;

  var triggeredCount = Object.keys(_triggeredRuleFindings).length;
  var countEl = document.getElementById('risk-rules-count');
  var triggerText = triggeredCount > 0 ? '（本次触发 <span style="color:#dc2626;font-weight:600">' + triggeredCount + '</span> 条）' : '（暂无触发）';
  var sortNames = {time:'按时间排序', high:'高风险优先', low:'低风险优先', trigger:'触发优先'};
  var sortName = sortNames[_currentSort] || '按时间排序';
  var timeStr = window._rulesUpdateTime ? ' · 数据更新于 ' + window._rulesUpdateTime : '';
  if (countEl) countEl.innerHTML = data.length + ' 条税务疑点 ' + triggerText + ' · ' + sortName + ' · 支持搜索筛选' + timeStr;

  if (data.length === 0) {
    listEl.innerHTML = '<div style="padding:40px 0;font-size:10px;color:#94a3b8">暂无税务疑点，请加载数据</div>';
    return;
  }

  // 排序
  var sortedData = data.slice();
  if (_currentSort === 'high') {
    var lv={'极高风险':0,'高风险':1,'中风险':2,'低风险':3,'良好':4};
    sortedData.sort(function(a,b){return (lv[a.level||'']||9)-(lv[b.level||'']||9);});
  } else if (_currentSort === 'low') {
    var lv2={'极高风险':4,'高风险':3,'中风险':2,'低风险':1,'良好':0};
    sortedData.sort(function(a,b){return (lv2[a.level||'']||9)-(lv2[b.level||'']||9);});
  } else if (_currentSort === 'trigger') {
    sortedData.sort(function(a,b){
      var ta=(_triggeredRuleFindings[String(a.id||'').trim()]||[]).length;
      var tb=(_triggeredRuleFindings[String(b.id||'').trim()]||[]).length;
      return tb-ta || ((b.id||0)-(a.id||0));
    });
  } else {
    // 按生成时间（ID越大越新）
    sortedData.sort(function(a, b) { return (b.id || 0) - (a.id || 0); });
  }

  // 统计 — 填充顶部卡片
  var high = data.filter(function(r) { return (r.level === '极高风险' || r.level === '高风险'); }).length;
  var mid = data.filter(function(r) { return r.level === '中风险'; }).length;
  var low = data.filter(function(r) { return r.level === '低风险' || r.level === '良好'; }).length;
  _fillEl('tr-total', data.length);
  _fillEl('tr-high', high);
  _fillEl('tr-mid', mid);
  _fillEl('tr-low', low);
  _fillEl('tr-trigger', triggeredCount);

  // 表格形式渲染所有指令
  listEl.innerHTML = window._rrTable(sortedData);

  if (statsEl) {
    statsEl.innerHTML = '共 ' + data.length + ' 条税务疑点 · '
      + '<span style="color:#dc2626">高 ' + high + '</span> · '
      + '<span style="color:#f59e0b">中 ' + mid + '</span> · '
      + '<span style="color:#10b981">低/良 ' + low + '</span> · '
      + '按ID排序';
  }
  
  // 初始化筛选计数
  var cntEl = document.getElementById('rr-filter-count');
  if (cntEl) cntEl.textContent = '显示 ' + data.length + ' 条';
}

function _fillEl(id, val) {
  var el = document.getElementById(id);
  if (el) el.textContent = val;
}


