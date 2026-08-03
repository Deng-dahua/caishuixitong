// Canonical methodology rule, clue, evidence and analysis page.
function renderTaxRiskRules(container) {
  if (!container) return;
  container.innerHTML = '<div style="padding:22px;color:#64748b">正在载入权威方法论目录...</div>';
  return fetch('/api/methodology/assets/canonical_catalog?_t=' + Date.now())
    .then(function(response){
      if (!response.ok) throw new Error('权威方法论目录加载失败');
      return response.json();
    })
    .then(function(payload){
      var modules = payload.modules || [];
      var governance = payload.governance || {};
      var totalRules = modules.reduce(function(sum,item){return sum + (item.rules || []).length;},0);
      var totalClues = modules.reduce(function(sum,item){return sum + (item.clue_paths || []).length;},0);
      function list(items) {
        if (!items || !items.length) return '<p style="color:#94a3b8">无</p>';
        return '<ul class="method-checklist">' + items.map(function(item){
          var text = typeof item === 'string' ? item : (item.fact_hypothesis || item.name || JSON.stringify(item));
          return '<li>' + escHtml(text) + '</li>';
        }).join('') + '</ul>';
      }
      container.innerHTML = '<div class="method-stop"><b>规则底座定位：</b>' + escHtml(payload.positioning || '') + '</div>'
        + '<div class="method-coverage-summary">'
        + '<div><strong>' + escHtml(modules.length) + '</strong><span>权威核验主题</span></div>'
        + '<div><strong>' + escHtml(totalRules) + '</strong><span>可证伪事实规则</span></div>'
        + '<div><strong>' + escHtml(totalClues) + '</strong><span>差异化调查路径</span></div></div>'
        + '<div class="method-source-note"><b>数量原则：</b>' + escHtml(governance.count_policy || '')
        + '<br><b>运行顺序：</b>' + escHtml((governance.activation_order || []).join(' → ')) + '</div>'
        + '<div class="method-framework-stack">' + modules.map(function(module){
          var evidence = module.evidence_plan || {};
          return '<details class="method-framework-card"><summary><b>' + escHtml(module.id + ' · ' + module.name)
            + '</b> · ' + escHtml((module.rules || []).length) + '项事实规则</summary>'
            + '<p>' + escHtml(module.purpose || '') + '</p>'
            + '<div class="method-two-column"><article class="method-framework-card"><h4>适用闸门</h4>' + list(module.activation_gate)
            + '</article><article class="method-framework-card"><h4>报告边界</h4><p>' + escHtml(module.report_boundary || '') + '</p></article></div>'
            + '<h4>疑点规则</h4><table class="method-framework-table"><thead><tr><th style="width:13%">编号</th><th>待证事实</th><th style="width:27%">必需字段</th><th style="width:24%">应先排除</th></tr></thead><tbody>'
            + (module.rules || []).map(function(rule){return '<tr><td>' + escHtml(rule.id) + '</td><td>'
              + escHtml(rule.fact_hypothesis) + '</td><td>' + escHtml((rule.required_fields || []).join('、'))
              + '</td><td>' + escHtml((rule.excludes || []).join('、')) + '</td></tr>';}).join('') + '</tbody></table>'
            + '<h4>调查线索</h4>' + (module.clue_paths || []).map(function(path){return '<p><b>' + escHtml(path.id)
              + '</b>　' + escHtml((path.stages || []).join(' → ')) + '</p>';}).join('')
            + '<div class="method-two-column"><article class="method-framework-card"><h4>支持材料</h4>' + list(evidence.supporting)
            + '<h4>反向材料</h4>' + list(evidence.opposing) + '</article>'
            + '<article class="method-framework-card"><h4>证据不足条件</h4>' + list(evidence.insufficient_when)
            + '<h4>分析检验</h4>' + list(module.analysis_tests) + '</article></div>'
            + '<h4>边界验证样本</h4>' + list(module.validation_cases)
            + '</details>';
        }).join('') + '</div>';
    })
    .catch(function(error){
      container.innerHTML = '<div style="padding:22px;color:#b91c1c">权威方法论目录载入失败：' + escHtml(error.message || '未知错误') + '</div>';
    });
}


