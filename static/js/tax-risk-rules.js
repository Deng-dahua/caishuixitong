// ==================== 税务异常库页面 ====================
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

function renderTaxRiskRules(container, isAuto) {
  if (!container) return;
  var autoOnly = isAuto === true || container.id === 'au-auto-rules';  // 自动发现规则面板
  var h = '';
  h += '<style>'
    + '.rr{max-width:960px;margin:0 auto;padding:32px 20px;font-family:-apple-system,"Microsoft YaHei",sans-serif;color:#3a4048;font-size:12px;line-height:1.95}'
    + '.rr-pre{font-size:12.5px;color:#5b6675;line-height:2.1;margin:0 0 20px;padding:12px 16px;background:#fef8f8;border-left:3px solid #9a1f2b;border-radius:0 6px 6px 0}'
    + '.rr-pre em{font-style:normal;color:#9a1f2b;font-weight:600}'
    + '.rr-hero{display:flex;gap:12px;margin-bottom:24px;flex-wrap:wrap}'
    + '.rr-stat{flex:1;min-width:120px;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px 14px;text-align:center}'
    + '.rr-stat .v{font-size:20px;font-weight:700;color:#16233a;line-height:1.3}'
    + '.rr-stat .l{font-size:10px;color:#94a3b8;margin-top:4px}'
    + '.rr-tax{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:8px;margin:0 0 20px}'
    + '.rr-tax .rt{padding:8px 10px;background:#fafbfc;border:1px solid #eff2f6;border-radius:6px;font-size:11px}'
    + '.rr-tax .rt b{color:#16233a}'
    + '.rr-tax .rt span{font-size:10px;color:#94a3b8;float:right}'
    + '.rr-search{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}'
    + '.rr-search input{flex:1;min-width:180px;padding:6px 10px;border:1px solid #e2e8f0;border-radius:6px;font-size:11px;color:#475569;outline:none}'
    + '.rr-search input:focus{border-color:#9a1f2b}'
    + '.rr-search select{padding:6px 8px;border:1px solid #e2e8f0;border-radius:6px;font-size:11px;color:#475569;background:#fff}'
    + '.rr-rule{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px;margin-bottom:8px;transition:box-shadow .12s}'
    + '.rr-rule:hover{box-shadow:0 2px 6px rgba(0,0,0,.04)}'
    + '.rr-rule .rh{font-size:13px;font-weight:600;color:#16233a;margin:0 0 4px}'
    + '.rr-rule .rl{display:inline-block;padding:1px 8px;border-radius:4px;font-size:10px;font-weight:600;margin-right:6px}'
    + '.rr-rule .rb{font-size:11px;color:#64748b;line-height:1.8;margin:4px 0}'
    + '.rr-rule .ra{font-size:10.5px;color:#94a3b8}'
    + '</style>';

  h += '<div class="rr-pre">此库非凭空而来——每一条指令，都是<em>五十年稽查判例、被查企业真实手法、行政复议和法院判决</em>提炼出的量化标尺。规则库不是"猜疑清单"，而是<em>把经验变成可复核的判定条件</em>——什么数据特征构成疑点、这个疑点有多严重、接下来该查什么、法律依据在哪。引擎对照这些指令扫数据、出信号、给溯源。以下为引擎已加载的全部指令。</div>';

  h += '<div class="rr-search">'
    + '<input id="rr-search-input" type="text" placeholder="搜索规则..." oninput="window._rrFilter()" style="max-width:220px">'
    + '<select id="rr-level-filter" onchange="window._rrFilter()">'
    + '<option value="">全部等级</option>'
    + '<option value="极高风险">极高风险</option>'
    + '<option value="高风险">高风险</option>'
    + '<option value="中风险">中风险</option>'
    + '<option value="低风险">低风险</option>'
    + '<option value="良好">良好/正常</option>'
    + '</select>'
    + '<select id="rr-cat-filter" onchange="window._rrFilter()"><option value="">全部分类</option></select>'
    + '<button id="rr-update-btn" onclick="window._smartUpdate()" style="padding:6px 14px;background:#9a1f2b;color:#fff;border:none;border-radius:6px;font-size:11px;font-weight:600;cursor:pointer;white-space:nowrap">🤖 智能更新</button>'
    + '<span id="rr-update-time" style="font-size:10px;color:#94a3b8;white-space:nowrap"></span>'
    + '<span id="rr-update-status" style="font-size:10px;color:#94a3b8"></span>'
    + '</div>';

  h += '<div class="rr-hero" id="rr-hero"></div>';
  h += '<details id="rr-standard" style="margin-bottom:16px;background:#fafbfc;border:1px solid #eef2f6;border-radius:8px;padding:12px 16px;font-size:11px;line-height:2;color:#5b6675"><summary style="font-weight:700;color:#16233a;cursor:pointer;font-size:12px">📐 精写编制标准（共23字段）</summary>'
    + '<b>基础字段（9项·每条必填）:</b><br>'
    + '① id — 异常编号 ② item — 异常名称 ③ category — 所属类别 ④ level — 风险等级（极高/高/中/低/良好） ⑤ score — 风险评分（1-10）<br>'
    + '⑥ check_frequency — 稽查频率（高频/中频/低频） ⑦ policy_ref — 法律依据（具体法条编号和条文） ⑧ tax_impact — 税务影响（涉及税种+补税区间） ⑨ applicable_condition — 适用条件（什么类型/规模/行业触发）<br>'
    + '<b>来源标记（2项）:</b>⑩ source — 来源（空=人工精写/系统发现） ⑪ auto_type — 自动发现类型<br>'
    + '<b>一、推理链：</b>direction字段必须展示从现象到定性的递进推理。格式为【推理第一层：XX法则】→【推理第二层：XX】→...每层50-80字，至少4层，最后一层必须落地到定性。<br>'
    + '<b>二、穿透追问：</b>drill_questions字段至少8条分3组，每组标注组名。每条格式为"Q{N}:{问题}→潜台词:{稽查真实意图}。A:{应对话术}"<br>'
    + '<b>三、正常业务解释：</b>normal_reason字段至少6种情形。每种格式为"{情形}——需提供{具体证据}"。证据必须可核验。<br>'
    + '<b>四、证据清单：</b>evidence字段按四层框架组织：货物流+合同资金流+业务合理性+排雷。大额业务区分AB场景（自提vs直运）。<br>'
    + '<b>五、整改建议：</b>remedy字段按三阶段组织：自查(稽查前)→应对(稽查中)→制度(长期)。应对部分含话术策略。<br>'
    + '<b>六、定性路径：</b>determination字段分三条推理路径：无法证明→定性+后果；部分证明→分类处理；完整证明→排除风险。结尾附应对总原则。<br>'
    + '<b>七、风险表格：</b>risk_table字段至少覆盖5个税种/维度，每行格式为"税种:具体风险描述"。<br>'
    + '<b>八、现象描述：</b>phenomena字段包含异常定义+5种常见表现形式（用①②③④⑤列举），加适用范围的兜底条款。<br>'
    + '<b>九、触发指标：</b>threshold字段必须有量化阈值 + 前置条件（如销售额门槛）。<br>'
    + '<b>十、稽查动作：</b>action字段含具体的核查步骤（至少5步），其中必须包含现场核查手段（实地查看/调取记录/外调走访），不能全是纸面比对。<br>'
    + '<b>十一、稽查重点：</b>focus字段列明该异常最常见的舞弊手法，用①②③④逐条标注。<br>'
    + '<b>十二、稽查处理：</b>suggestion字段明确查实后的处置方式（补税/罚款/移送）。<br>'
    + '</details>';
  h += '<div id="rr-list"></div>';
  h += '<div id="rr-compare" style="display:none;margin:0 0 20px;padding:16px;background:#fef8f8;border:1px solid #f4c2c7;border-radius:8px"></div>';

  container.innerHTML = h;

  var dataUrl = autoOnly ? '/static/auto_discovered_rules.json' : '/static/tax_risk_rules_local_export.json';
  // 显示规则文件最后修改时间
  fetch(dataUrl, {method:'HEAD'}).then(function(r){
    var lm = r.headers.get('Last-Modified');
    if (lm) {
      var d = new Date(lm);
      var ds = (d.getMonth()+1)+'/'+d.getDate()+' '+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0');
      var tu = document.getElementById('rr-update-time'); if (tu) tu.textContent = '最后更新 ' + ds;
    }
  }).catch(function(){});

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

      // 统计面板
      var hero = document.getElementById('rr-hero');
      if (hero) hero.innerHTML = 
        '<div class="rr-stat"><div class="v" style="color:#16233a">' + total + '</div><div class="l">指令总数</div></div>'
        + '<div class="rr-stat"><div class="v" style="color:#dc2626">' + high + '</div><div class="l">极高/高风险</div></div>'
        + '<div class="rr-stat"><div class="v" style="color:#f59e0b">' + mid + '</div><div class="l">中风险</div></div>'
        + '<div class="rr-stat"><div class="v" style="color:#059669">' + (low + good) + '</div><div class="l">低风险/良好</div></div>';

      // 分类标签
      var catFilter = document.getElementById('rr-cat-filter');
      if (catFilter) {
        Object.keys(cats).sort(function(a, b) { return cats[b] - cats[a]; }).forEach(function(c) {
          var o = document.createElement('option');
          o.value = c; o.textContent = c + ' (' + cats[c] + ')';
          catFilter.appendChild(o);
        });
      }

      window._rrFilter = function() {
        var kw = (document.getElementById('rr-search-input') && document.getElementById('rr-search-input').value || '').toLowerCase();
        var lv = document.getElementById('rr-level-filter') && document.getElementById('rr-level-filter').value || '';
        var ct = document.getElementById('rr-cat-filter') && document.getElementById('rr-cat-filter').value || '';
        var list = document.getElementById('rr-list');
        if (!list) return;
        var filtered = rules.filter(function(rl) {
          var txt = (rl.item || '') + ' ' + (rl.direction || '') + ' ' + (rl.focus || '') + ' ' + (rl.action || '') + ' ' + (rl.policy_ref || '') + ' ' + (rl.id || '');
          if (kw && txt.toLowerCase().indexOf(kw) < 0) return false;
          if (lv && (rl.level || rl.level || '').indexOf(lv) < 0) return false;
          if (ct && (rl.category || '') !== ct) return false;
          return true;
        });
        if (filtered.length === 0) {
          list.innerHTML = '<div style="text-align:center;padding:24px;color:#94a3b8">未找到匹配的规则</div>';
          return;
        }
        var html = '';
        filtered.forEach(function(rl) {
          var lv = rl.level || rl.level || '信息';
          var lc = '#64748b';
          if (lv.indexOf('极高') >= 0) lc = '#991b1b';
          else if (lv.indexOf('高') >= 0) lc = '#dc2626';
          else if (lv.indexOf('中') >= 0) lc = '#f59e0b';
          else if (lv.indexOf('低') >= 0) lc = '#059669';
          var card = '<div class="rr-rule">'
            + '<div class="rh">#' + (rl.id || '') + ' ' + escHtml(rl.item || '未命名') + '</div>'
            + (rl.type === 'auto_signal' || rl.source === '系统发现' || rl.auto_type ? '<span style="font-size:9px;background:#eff6ff;color:#2563eb;padding:2px 6px;border-radius:4px;font-weight:600;margin-right:4px">🤖 自动发现</span>' : '')
            + '<span class="rl" style="background:' + lc + '15;color:' + lc + ';border:1px solid ' + lc + '30">' + lv + '</span>'
            + (rl.score ? '<span style="font-size:9px;color:#94a3b8;margin-left:4px">评分' + rl.score + '/10</span>' : '')
            + (rl.category ? '<span style="font-size:10px;color:#94a3b8;margin-left:6px">' + rl.category + '</span>' : '')
            + (rl.check_frequency ? '<span style="font-size:9px;color:#94a3b8;margin-left:6px;border:1px solid #e2e8f0;border-radius:4px;padding:0 4px">' + rl.check_frequency + '</span>' : '');

          // 7段式新格式：phenomena → direction → focus → risk_table → normal_reason → determination → drill_questions
          if (rl.phenomena) {
            card += '<div style="font-size:12px;font-weight:600;color:#16233a;margin:8px 0 4px;border-bottom:1px solid #e2e8f0;padding-bottom:4px">一、异常现象描述</div>';
            card += '<div style="font-size:11px;color:#3a4048;line-height:2;margin:4px 0 10px">' + escHtml(rl.phenomena).replace(/①/g,'<br>①').replace(/②/g,'<br>②').replace(/③/g,'<br>③').replace(/④/g,'<br>④').replace(/⑤/g,'<br>⑤') + '</div>';
          }
          if (rl.direction) {
            card += '<div style="font-size:12px;font-weight:600;color:#16233a;margin:8px 0 4px;border-bottom:1px solid #e2e8f0;padding-bottom:4px">' + (rl.phenomena ? '二' : '一') + '、异常逻辑分析（为何成为疑点）</div>';
            card += '<div style="font-size:11px;color:#64748b;line-height:2;padding-left:10px;border-left:2px solid #9a1f2b;margin:4px 0 10px">' + escHtml(rl.direction) + '</div>';
          }
          if (rl.focus && rl.focus !== '待明确重点') {
            card += '<div style="font-size:12px;font-weight:600;color:#16233a;margin:8px 0 4px;border-bottom:1px solid #e2e8f0;padding-bottom:4px">稽查重点指向</div>';
            card += '<div style="font-size:11px;color:#dc2626;line-height:2;padding-left:10px;border-left:2px solid #dc2626;margin:4px 0 10px">' + escHtml(rl.focus) + '</div>';
          }
          
          // 风险表格
          if (rl.risk_table) {
            card += '<div style="font-size:12px;font-weight:600;color:#16233a;margin:8px 0 4px;border-bottom:1px solid #e2e8f0;padding-bottom:4px">触发的稽查风险点</div>';
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
            card += '<div style="font-size:12px;font-weight:600;color:#16233a;margin:8px 0 4px;border-bottom:1px solid #e2e8f0;padding-bottom:4px">可能的业务解释（正常情形）</div>';
            card += '<div style="font-size:11px;color:#059669;line-height:2;margin:4px 0 10px;padding:8px 12px;background:#f0fdf4;border-radius:6px">' + escHtml(rl.normal_reason).replace(/①/g,'<br>①').replace(/②/g,'<br>②').replace(/③/g,'<br>③').replace(/④/g,'<br>④') + '</div>';
          }
          
          // 定性路径
          if (rl.determination) {
            card += '<div style="font-size:12px;font-weight:600;color:#16233a;margin:8px 0 4px;border-bottom:1px solid #e2e8f0;padding-bottom:4px">稽查定性路径</div>';
            card += '<div style="font-size:11px;color:#3a4048;line-height:2;margin:4px 0 10px">' + escHtml(rl.determination).replace(/核查方向/g,'<br><b>核查方向</b>').replace(/定性结论/g,'<br><b>定性结论</b>').replace(/法律后果/g,'<br><b>法律后果</b>') + '</div>';
          }
          
          // 穿透式追问
          if (rl.drill_questions) {
            card += '<div style="font-size:12px;font-weight:600;color:#16233a;margin:8px 0 4px;border-bottom:1px solid #e2e8f0;padding-bottom:4px">稽查常见穿透式追问与应对</div>';
            var qas = typeof rl.drill_questions === 'string' ? rl.drill_questions.split('\n') : (Array.isArray(rl.drill_questions) ? rl.drill_questions : []);
            for (var qi = 0; qi < qas.length; qi++) {
              var qm = qas[qi].match(/^(Q\d+):(.+?)→A:(.+)$/);
              if (qm) {
                card += '<div style="margin:4px 0;padding:6px 10px;background:#fef8f8;border-left:3px solid #9a1f2b;border-radius:0 4px 4px 0;font-size:10px"><b style="color:#9a1f2b">' + escHtml(qm[1]) + '</b> ' + escHtml(qm[2]) + '<br><span style="color:#059669">▶ ' + escHtml(qm[3]) + '</span></div>';
              }
            }
          }
          
          // 传统字段（兼容未升级的规则）
          card += (rl.action ? '<div style="font-size:11px;color:#3a4048;margin:2px 0 4px">🔍 核查动作：' + escHtml(rl.action) + '</div>' : '')
            + (rl.threshold && !rl.threshold.startsWith('评分阈值') ? '<div style="font-size:10px;color:#94a3b8;margin:2px 0">📏 触发指标：' + escHtml(rl.threshold) + '</div>' : '')
            + (rl.evidence ? '<div style="font-size:10px;color:#94a3b8;margin:2px 0">📎 证据清单：' + escHtml(rl.evidence) + '</div>' : '')
            + (rl.policy_ref ? '<div class="ra">📜 法律依据：' + escHtml(rl.policy_ref) + '</div>' : '')
            + (rl.suggestion ? '<div class="ra">⚖ 稽查处理：' + escHtml(rl.suggestion) + '</div>' : '')
            + (rl.tax_impact ? '<div class="ra">💰 税务影响：' + escHtml(rl.tax_impact) + '</div>' : '')
            + (rl.remedy && rl.remedy !== rl.suggestion ? '<div class="ra">🔧 整改建议：' + escHtml(rl.remedy) + '</div>' : '')
            + (rl.applicable_condition ? '<div class="ra">📋 适用条件：' + escHtml(rl.applicable_condition) + '</div>' : '');
          card += '</div>';
          html += card;
        });
        list.innerHTML = html;
      };
      window._rrFilter();
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
  var h = '<div class="rr-edit-panel" style="margin:12px 0;padding:16px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px">';
  h += '<div style="font-size:12px;font-weight:600;color:#1e293b;margin-bottom:12px">✏️ 编辑规则 ' + ruleId + '</div>';
  fields.forEach(function(f){
    h += '<div style="margin-bottom:8px"><span style="font-size:10px;color:#94a3b8">' + f.label + '</span>';
    if (f.type === 'select') {
      h += '<select id="rr-edit-' + f.k + '" style="width:100%;font-size:11px;padding:4px 8px;border:1px solid #e2e8f0;border-radius:4px;margin-top:2px">';
      (f.opts||[]).forEach(function(o){ h += '<option ' + (o===f.v?'selected':'') + '>' + o + '</option>'; });
      h += '</select>';
    } else if (f.ta) {
      h += '<textarea id="rr-edit-' + f.k + '" rows="2" style="width:100%;font-size:11px;padding:4px 8px;border:1px solid #e2e8f0;border-radius:4px;margin-top:2px;resize:vertical">' + escHtml(String(f.v)) + '</textarea>';
    } else {
      h += '<input id="rr-edit-' + f.k + '" value="' + escHtml(String(f.v)) + '" style="width:100%;font-size:11px;padding:4px 8px;border:1px solid #e2e8f0;border-radius:4px;margin-top:2px">';
    }
    h += '</div>';
  });
  h += '<div style="display:flex;gap:8px;margin-top:12px">';
  h += '<button onclick="saveRuleEdit(\'' + ruleId + '\',this)" style="font-size:11px;padding:5px 16px;border:none;border-radius:4px;background:#2563eb;color:#fff;cursor:pointer;font-weight:600">保存</button>';
  h += '<button onclick="toggleRuleEdit(\'' + ruleId + '\',this)" style="font-size:11px;padding:5px 16px;border:1px solid #e2e8f0;border-radius:4px;background:#fff;color:#64748b;cursor:pointer">取消</button>';
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
      if (panel) panel.innerHTML = '<div style="color:#059669;font-weight:600;font-size:12px;padding:8px">✓ 已保存（' + d.changed.length + '字段）· 1.5秒后刷新</div>';
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
  var level = document.getElementById('rr-level-filter')?.value || '';
  var cat = document.getElementById('rr-cat-filter')?.value || '';
  var rtype = document.getElementById('rr-type-filter')?.value || '';
  
  var listEl = document.getElementById('risk-rules-list');
  if (!listEl) return;
  
  var allCards = listEl.querySelectorAll('[data-rule-id]');
  var visible = 0;
  
  allCards.forEach(function(card) {
    var text = (card.textContent || '').toLowerCase();
    var ruleLevel = card.getAttribute('data-level') || '';
    var ruleCat = card.getAttribute('data-category') || '';
    var ruleType = card.getAttribute('data-type') || '';
    var triggered = card.getAttribute('data-triggered') === '1';
    
    var matches = true;
    if (search && text.indexOf(search) < 0) matches = false;
    if (level && ruleLevel !== level) matches = false;
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
    var resp = await fetch('/static/tax_risk_rules_local_export.json?_t=' + Date.now());
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
  var sortNames = {time:'按时间排序', high:'高风险优先', low:'低风险优先', trigger:'触发优先'};
  var sortName = sortNames[_currentSort] || '按时间排序';
  var timeStr = window._rulesUpdateTime ? ' · 数据更新于 ' + window._rulesUpdateTime : '';
  if (countEl) countEl.innerHTML = data.length + ' 条税务异常 ' + triggerText + ' · ' + sortName + ' · 支持搜索筛选' + timeStr;

  if (data.length === 0) {
    listEl.innerHTML = '<div style="padding:40px 0;font-size:12px;color:#94a3b8">暂无税务异常，请加载数据</div>';
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

  var html = '';

  // 按生成时间渲染所有指令
  sortedData.forEach(function(rule) {
      // 自动发现规则的字段映射
      var isAutoRule = rule.type === 'auto_signal' || rule.source === '系统发现' || !!rule.auto_type;
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

      html += '<div data-rule-id="' + rid + '" data-level="' + (levelName || '') + '" data-triggered="' + (isTriggered ? '1' : '0') + '" data-category="' + (rule.category || '') + '" data-type="' + (isAutoRule ? 'auto' : 'manual') + '"'
        + ' style="padding:14px 18px;margin-bottom:8px;background:#fff;border:1px solid #e2e8f0;border-left:' + borderWidth + ' solid ' + borderColor + ';border-radius:6px" class="tr-rule-card">'
        
        // 标题行
        + '<div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:6px">'
        + '<div style="font-size:13px;font-weight:600;color:#0f172a">'
        + (isAutoRule ? '🤖 ' : '') + escHtml(itemName)
        + (isAutoRule ? '<span style="margin-left:6px;font-size:11px;font-weight:400;color:#64748b">[' + escHtml(rule.industry || '') + ']</span>' : '')
        + (isTriggered ? '<span style="margin-left:8px;font-size:11px;padding:2px 8px;border-radius:4px;background:#fef2f2;color:#dc2626;font-weight:600">✅ 本次触发(' + triggered.length + ')</span>' : '')
        + '</div>'
        + '<div style="display:flex;gap:8px;align-items:center;flex-shrink:0;margin-left:16px">'
        + (isAutoRule 
            ? '<span style="font-size:11px;padding:2px 8px;border-radius:4px;background:#eff6ff;color:#2563eb;font-weight:600">🤖 自动发现</span>'
            : '<span style="font-size:11px;padding:2px 8px;border-radius:4px;background:' + color + '15;color:' + color + ';font-weight:600">' + icon + ' ' + (levelName || '') + '</span>')
        + (!isAutoRule ? '<button onclick="toggleRuleEdit(\'' + rid + '\',this)" style="font-size:10px;padding:2px 8px;border:1px solid #cbd5e1;border-radius:4px;background:#fff;color:#64748b;cursor:pointer">✏️</button>' : '')
        + (isAutoRule 
            ? '<span style="font-size:11px;color:#94a3b8">置信度 ' + (rule.confidence !== undefined ? Math.round(rule.confidence * 100) + '%' : '-') + '</span>'
            + '<button onclick="promoteAutoRule(\'' + rid + '\',this)" style="font-size:10px;padding:3px 10px;border:1px solid #059669;border-radius:4px;background:#ecfdf5;color:#059669;cursor:pointer;font-weight:600">✓ 确认为正式规则</button>'
            : '<span style="font-size:11px;color:#94a3b8">评分 ' + scoreVal + '</span>')
        + (rid ? '<span style="font-size:10px;color:#94a3b8">ID:' + rid + '</span>' : '')
        + '</div>'
        + '</div>'

        // 触发溯源
        + (isTriggered ? '<div style="margin-bottom:6px;padding:8px 12px;background:#fef2f2;border-radius:4px;font-size:11px;line-height:2.0">'
        + '<div style="font-weight:600;color:#991b1b;margin-bottom:4px">🔗 触发溯源：</div>'
        + triggered.map(function(t) {
            return '<div style="color:#7f1d1d">→ <strong>' + escHtml(t.domain || t.type || '') + '</strong>' + (t.detail ? ': ' + escHtml(t.detail.substring(0, 150)) : '') + (t.level ? ' [' + t.level + ']' : '') + '</div>';
          }).join('')
        + '</div>' : '')

        // 详细内容 —— 自动发现规则也展示7段式字段
        + (rule.phenomena ? '<div style="font-size:11px;color:#475569;line-height:2.0;margin-bottom:4px"><b>现象：</b>' + escHtml(rule.phenomena) + '</div>' : '')
        + (rule.direction ? '<div style="font-size:11px;color:#475569;line-height:2.0;margin-bottom:4px"><b>逻辑：</b>' + escHtml(rule.direction) + '</div>' : '')
        + (rule.focus && rule.focus !== '待明确重点' ? '<div style="font-size:11px;color:#dc2626;line-height:2.0;margin-bottom:4px"><b>重点：</b>' + escHtml(rule.focus) + '</div>' : '')
        + (rule.drill_questions ? '<div style="font-size:11px;color:#475569;line-height:2.0;margin-bottom:4px"><b>追问：</b>' + escHtml(rule.drill_questions.replace(/\n/g,'<br>')) + '</div>' : '')
        + (detailText ? '<div style="font-size:12px;color:#475569;line-height:2.0;margin-bottom:6px">' + escHtml(detailText) + '</div>' : '')
        + (rule.normal_reason && rule.normal_reason.length > 20 ? '<div style="font-size:11px;color:#059669;line-height:2.0;margin-bottom:4px"><b>正常解释：</b>' + escHtml(rule.normal_reason) + '</div>' : '')
        + (rule.risk_table ? '<div style="font-size:11px;color:#dc2626;line-height:2.0;margin-bottom:4px"><b>风险：</b>' + escHtml(rule.risk_table).replace(/\n/g,'<br>') + '</div>' : '')

        // 建议 + 佐证
        + (suggestText ? '<div style="font-size:12px;color:#334155;line-height:2.0;margin-bottom:4px"><span style="font-weight:600;color:#0f172a">' + (isAutoRule ? '系统建议：' : '税务合规建议：') + '</span>' + escHtml(suggestText) + '</div>' : '')
        + (evidenceText ? '<div style="font-size:12px;color:#334155;line-height:2.0;margin-bottom:4px"><span style="font-weight:600;color:#0f172a">' + (isAutoRule ? '发现依据：' : '所需佐证：') + '</span>' + escHtml(evidenceText) + '</div>' : '')

        // 自动发现额外信息
        + (isAutoRule ? '<div style="font-size:12px;color:#334155;line-height:2.0;margin-bottom:4px"><span style="font-weight:600;color:#0f172a">信号出现率：</span>' + escHtml(rule.prevalence || '') + '</div>' : '')
        + (isAutoRule && rule.auto_discovered_at ? '<div style="font-size:12px;color:#334155;line-height:2.0;margin-bottom:4px"><span style="font-weight:600;color:#0f172a">自动发现时间：</span>' + escHtml(rule.auto_discovered_at.substring(0, 19)) + '</div>' : '')

        // 底栏
        + '<div style="display:flex;gap:16px;flex-wrap:wrap;margin-top:6px;padding-top:6px;border-top:1px solid #e2e8f0;font-size:11px;color:#94a3b8">'
        + (impactText ? '<span><span style="color:#64748b">税务影响：</span>' + escHtml(impactText.substring(0, 120)) + (impactText.length > 120 ? '...' : '') + '</span>' : '')
        + (policyText ? '<span><span style="color:#64748b">法条：</span>' + escHtml(policyText.substring(0, 100)) + (policyText.length > 100 ? '...' : '') + '</span>' : '')
        + (rule.dataSource ? '<span><span style="color:#64748b">数据源：</span>' + escHtml(rule.dataSource) + '</span>' : '')
        + (rule.detectable !== undefined ? '<span>' + (rule.detectable ? '✅ 可自动检测' : '⚠️ 需人工') + '</span>' : '')
        + '</div>'
        + '</div>';
    });

  listEl.innerHTML = html;

  if (statsEl) {
    statsEl.innerHTML = '共 ' + data.length + ' 条税务异常 · '
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

window._smartUpdate = function() {
  
  
  var st = document.getElementById('rr-update-status');
  var btn = document.getElementById('rr-update-btn');
  if (st) st.textContent = '分析中...';
  if (btn) { btn.disabled = true; btn.textContent = '分析中...'; }
  fetch('/api/tax-risk-rules/smart-update', {method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})
    .then(function(r){return r.json();})
    .then(function(d){
      var now = new Date().toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});
      var tu = document.getElementById('rr-update-time'); if (tu) tu.textContent = '最后更新 ' + now;
      if (st) st.textContent = d.ok ? '完成' : '失败';
      if (btn) { btn.disabled = false; btn.textContent = d.ok ? '🤖 再次更新' : '🤖 重试'; }
      if (!d.ok) { alert('更新失败: ' + (d.message||'')); return; }
      var c = d.compare || {};
      var total = (c.new_count||0) + (c.modify_count||0) + (c.delete_count||0);
      var cp = document.getElementById('rr-compare');
      if (!cp) return;
      if (total === 0) {
        cp.innerHTML = '<div style="font-size:14px;font-weight:700;color:#059669;margin:0 0 8px">✅ 本次分析无更新建议</div><div style="font-size:12px;color:#5b6675">依据9个维度全面扫描，当前规则库已覆盖完善，无需新增、修改或删除。规则库状态：' + (c.before_total||0) + '条。</div>';
        cp.style.display = 'block';
        return;
      }
      var h = '<div style="font-size:14px;font-weight:700;color:#9a1f2b;margin:0 0 12px">📊 智能更新对比报告</div>';
      h += '<div style="font-size:12px;color:#5b6675;margin:0 0 12px">' + escHtml(c.summary||'') + '</div>';
      h += '<div style="display:flex;gap:16px;margin:0 0 12px;flex-wrap:wrap"><div style="flex:1;min-width:80px;text-align:center;padding:10px;background:#f0fdf4;border-radius:6px"><div style="font-size:18px;font-weight:700;color:#059669">' + (c.new_count||0) + '</div><div style="font-size:10px;color:#64748b">建议新增</div></div><div style="flex:1;min-width:80px;text-align:center;padding:10px;background:#fff7ed;border-radius:6px"><div style="font-size:18px;font-weight:700;color:#f59e0b">' + (c.modify_count||0) + '</div><div style="font-size:10px;color:#64748b">建议修改</div></div><div style="flex:1;min-width:80px;text-align:center;padding:10px;background:#fef2f2;border-radius:6px"><div style="font-size:18px;font-weight:700;color:#dc2626">' + (c.delete_count||0) + '</div><div style="font-size:10px;color:#64748b">建议删除</div></div></div>';
      h += '<div style="font-size:11px;color:#64748b">更新前: ' + (c.before_total||0) + '条 → 更新后: ' + (c.after_total||0) + '条</div>';
      if (c.new_rules && c.new_rules.length) {
        h += '<div style="margin:12px 0"><div style="font-size:12px;font-weight:600;color:#059669;margin:8px 0">新增规则</div>' + c.new_rules.map(function(r){return '<div style="margin:6px 0;padding:8px 10px;background:#f0fdf4;border-radius:6px;font-size:11px"><b>'+escHtml(r.item||'')+'</b> ['+escHtml(r.category||'')+'/'+escHtml(r.level||'')+']<div style="color:#64748b;margin:2px 0">'+escHtml((r.detail||'').substring(0,120))+'</div></div>';}).join('') + '</div>';
      }
      if (c.modify && c.modify.length) {
        h += '<div style="margin:12px 0"><div style="font-size:12px;font-weight:600;color:#f59e0b;margin:8px 0">修改建议</div><table style="width:100%;border-collapse:collapse;font-size:11px"><tr style="background:#fff7ed"><td>ID</td><td>原名称</td><td>建议改为</td><td>原因</td></tr>' + c.modify.map(function(r){return '<tr><td style="padding:4px 8px;border:1px solid #e2e8f0">'+(r.id||'')+'</td><td style="padding:4px 8px;border:1px solid #e2e8f0">'+escHtml(r.old_item||'')+'</td><td style="padding:4px 8px;border:1px solid #e2e8f0;color:#059669">'+escHtml(r.new_item||'')+'</td><td style="padding:4px 8px;border:1px solid #e2e8f0">'+escHtml(r.reason||'')+'</td></tr>';}).join('') + '</table></div>';
      }
      if (c.delete && c.delete.length) {
        h += '<div style="margin:12px 0"><div style="font-size:12px;font-weight:600;color:#dc2626;margin:8px 0">删除建议</div>' + c.delete.map(function(r){return '<div style="margin:4px 0;font-size:11px;color:#dc2626">ID['+escHtml(r.id||'')+'] '+escHtml(r.item||'')+' — '+escHtml(r.reason||'')+'</div>';}).join('') + '</div>';
      }
      h += '<div style="margin:12px 0 0;font-size:10px;color:#94a3b8">以上为LLM建议，请人工审核确认后再执行更新操作。</div>';
      cp.innerHTML = h;
      cp.style.display = 'block';
    })
    .catch(function(e){
      if (st) st.textContent = '异常';
      if (btn) { btn.disabled = false; btn.textContent = '🤖 重试'; }
      alert('请求异常: ' + e.message);
    });
};

// —— 自动发现规则面板（独立渲染，不与主面板共享任何逻辑）——
function renderAutoRules(container) {
  if (!container) { console.error('renderAutoRules: no container'); return; }
  container.innerHTML = '<div style=\"text-align:center;padding:24px;color:#94a3b8\">加载中...</div>';
  fetch('/static/auto_discovered_rules.json?' + Date.now())
    .then(function(r){ if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); })
    .then(function(rules){
      var h = '<div style=\"font-size:11px;color:#64748b;margin-bottom:8px\">共 ' + rules.length + ' 条自动发现规则</div>';
      for (var i = 0; i < rules.length; i++) {
        var r = rules[i];
        h += '<div style=\"padding:10px 14px;margin:4px 0;background:#fff;border:1px solid #e2e8f0;border-left:3px solid #2563eb;border-radius:4px;font-size:12px\">';
        h += '<b>#' + r.id + '</b> 🤖 ' + escapeHtml(r.item || '') + ' <span style=\"color:#94a3b8;font-size:10px\">' + (r.category || '') + '</span>';
        if (r.phenomena) h += '<div style=\"margin:4px 0;color:#475569;font-size:11px\">' + escapeHtml(r.phenomena).substring(0,200) + '</div>';
        if (r.direction) h += '<div style=\"margin:2px 0;color:#64748b;font-size:11px\">' + escapeHtml(r.direction).substring(0,150) + '</div>';
        h += '</div>';
      }
      container.innerHTML = h;
    })
    .catch(function(e){
      container.innerHTML = '<div style=\"color:#dc2626;padding:14px\">加载失败: ' + e.message + '</div>';
    });
}
