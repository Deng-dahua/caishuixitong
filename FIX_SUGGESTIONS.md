# 12模块问题修复建议

> 基于2026-06-20全盘诊断结果

---

## P0 — 立即修复（本周必须完成）

### 1. 消除硬编码企业信息

**问题**：`tax-doc-analysis.js:395` 硬编码"被查单位工商登记为批发业，实质为纺织贸易+外包轻加工模式"。

**修复**：
```javascript
// 旧：硬编码
h += '<p class="i2">被查单位工商登记为批发业...</p>';

// 新：从target_entity动态生成
var te = report.target_entity || {};
var industryDesc = te.registered_industry || '';
var actualBiz = te.inferred_industry || te.registered_industry || '';
var director = (te.legal_person || '') + (te.legal_person_role ? '（' + te.legal_person_role + '）' : '');
h += '<p class="i2">' + escHtml(
  (industryDesc ? '工商登记' + industryDesc : '企业') +
  (actualBiz !== industryDesc ? '，实质为' + actualBiz : '') +
  (director ? '。法定代表人' + director : '') +
  '。</p>';
```

同步修复 `tax-doc-analysis.js:344` 稽查期间回退值、`tax-doc-analysis.js:413` 收款方关键词。

---

### 2. 统一escHtml转义函数

**问题**：4套转义逻辑共存，单引号遗漏有XSS风险。

**修复**：在 `core.js` 中定义唯一版本，删除其他3个：
```javascript
// core.js — 唯一正确的版本
function escHtml(s) {
  if (!s) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
```

删除：
- `tax-risk-rules.js:169` 的 DOM版本
- `tax-pipeline-pages.js:1392` 的 `_escStatic`
- `tax-pipeline-pages.js:1394` 的 `escHtml`
- `core.js:17` 的 `escapeHtml` 统一用 `escHtml`

---

### 3. 修复后端重复定义

**问题**：`main.py:13634-13652` `_BUILTIN_CROSS_DOMAIN_CHAINS` 定义两次。

**修复**：删除第二次定义（行13644-13652），保留第一次即可。

---

### 4. 修复证据链闭环率虚高

**问题**：`tax-pipeline-pages.js:1050` 只统计已触发的链，未触发链不计入"未闭环"。

**修复**：
```javascript
// 旧：只统计evidence_closures中的链
var closedCount = Object.values(evExecMap).filter(function(e) { return e.closed; }).length;

// 新：total = 证据链总数，closed = 已闭环数
var totalChains = chains.length;
var closedCount = chains.filter(function(c) {
  var exec = evExecMap[c.name];
  return exec && exec.closed;
}).length;
// 闭环率 = closedCount / totalChains （而非 closedCount / evExecMap长度）
```

---

## P1 — 本周修复（核心架构问题）

### 5. 建立API共享缓存，消除5模块重复请求

**问题**：文件解析/域分析/线索链/证据链/过滤器各自请求同一API。

**修复**：在 `tax-pipeline-pages.js` 顶部建单例：
```javascript
var _analysisCache = null;
var _analysisPromise = null;

function getAnalysisCache() {
  if (_analysisCache) return Promise.resolve(_analysisCache);
  if (_analysisPromise) return _analysisPromise;
  var cid = typeof currentCompanyId !== 'undefined' ? currentCompanyId : 1;
  _analysisPromise = fetch('/api/tax-risk-docs/last-analysis?company_id=' + cid)
    .then(function(r) { return r.json(); })
    .then(function(data) {
      _analysisCache = data;
      _analysisPromise = null;
      return data;
    })
    .catch(function(e) {
      _analysisPromise = null;
      throw e;
    });
  return _analysisPromise;
}
```

各模块改为调用 `getAnalysisCache()` 而非各自 fetch。5个模块减少到1次请求。

---

### 6. 跨域分析链和跨域线索链接入API动态数据

**问题**：模块8和10完全不消费API数据。

**修复**：
```javascript
// loadCrossDomainAnalysis() 在渲染静态JSON后，追加动态触发状态
async function loadCrossDomainAnalysis() {
  // ... 现有静态渲染 ...
  
  // 新增：加载动态触发状态
  var cache = await getAnalysisCache();
  if (cache.ok && cache.report) {
    var comp = cache.report.comprehensive || {};
    var triggered = comp.triggered_chains || [];
    // 标注每条分析链的触发状态
    document.querySelectorAll('.cda-chain-item').forEach(function(el, i) {
      var chainName = el.getAttribute('data-chain-name');
      var isTriggered = triggered.some(function(t) {
        return (typeof t === 'string' ? t : t.name || t.chain_id || '') === chainName;
      });
      if (isTriggered) {
        el.style.borderLeftColor = '#dc2626';
        el.querySelector('.cda-status').textContent = '● 已触发';
        el.querySelector('.cda-status').style.color = '#dc2626';
      }
    });
  }
}
```

模块10同理。

---

### 7. 域分析→稽查指令建立联动

**问题**：1505条规则不知道哪些在本次分析中触发。

**修复**：稽查指令页面加载时查询API，标注触发状态：
```javascript
// renderTaxRiskRulesList 中追加
async function annotateRuleTriggers() {
  var cache = await getAnalysisCache();
  if (!cache || !cache.ok) return;
  var triggeredRuleIds = new Set();
  (cache.report.all_findings || []).forEach(function(f) {
    if (f.rule_id) triggeredRuleIds.add(f.rule_id);
  });
  // 给每条规则标注状态
  triggeredRuleIds.forEach(function(rid) {
    var el = document.querySelector('[data-rule-id="' + rid + '"]');
    if (el) {
      var badge = document.createElement('span');
      badge.className = 'trigger-badge';
      badge.textContent = '本次触发';
      badge.style.cssText = 'background:#fef2f2;color:#dc2626;font-size:11px;padding:2px 6px;border-radius:4px;margin-left:8px';
      el.querySelector('.rule-header').appendChild(badge);
    }
  });
}
```

---

## P2 — 本月修复（代码质量清理）

### 8. 删除死代码

| 死代码 | 位置 |
|--------|------|
| `statLine()` 函数（全局零调用） | tax-pipeline-pages.js:246-250 |
| `filterChainsList()` 伪实现 | tax-pipeline-pages.js:997-999 |
| `_escStatic()` 多余函数 | tax-pipeline-pages.js:1392 |
| `_allEvidenceChains` 重复赋值 | tax-pipeline-pages.js:1123 |
| `RISK_LEVEL_COLORS/ICONS` 重复定义 | tax-risk-rules.js:4-9 |

### 9. 消除跨模块重复内容

| 重复内容 | 重复次数 | 统一方案 |
|---------|---------|---------|
| 稽查方法论㉖条 | 4处 | 提取为独立函数 `renderMethodologyBrief()` |
| 七步执行流程 | 2处 | 提取为独立函数 `renderSevenSteps()` |
| 三链关系说明 | 3处 | 提取为独立函数 `renderCrossChainRelation()` |

---

### 10. 证据链/线索链接入稽查指令

**问题**：链页面无法跳转到对应的规则详情。

**修复**：链的每个调查步骤如果含 `rule_id`，渲染为可点击链接：
```javascript
if (s.rule_id) {
  html += '<span class="rule-link" onclick="navigateToRule(\'' + s.rule_id + '\')" ' +
    'style="color:#6366f1;cursor:pointer;text-decoration:underline;font-size:11px">查看规则 R' + s.rule_id + '</span>';
}
```

---

## P3 — 下月优化（体验提升）

### 11. 全链路质量保障体系接入动态数据

调用 `loadPipelineCounts()` 替换硬编码数字，调用 `getAnalysisCache()` 获取实际触发状态。

### 12. 分析进度条

在 `analyzeTaxDocs()` 中添加轮询进度（后端在分析过程中写状态到内存/Redis）。

### 13. 域分析展开/收起全部 + 发现展开全文

添加全局控制按钮和 `detail.substring(0,300) + '...展开'` 交互。

---

## 架构建议（中期）

### 建议1：三层缓存架构

```
L1: 数据层缓存
  _analysisCache     ← /api/tax-risk-docs/last-analysis (共享)
  _rulesCache        ← /static/tax_risk_rules_local_export.json (共享)
  _chainsCache       ← /static/audit_chains.json (共享)

L2: 视图层状态
  _activeRuleIds     ← 当前触发规则ID集合
  _activeChainNames  ← 当前触发线索链名称集合
  _domainFindings    ← 域分析发现（按域分组）

L3: UI渲染层
  各模块只做渲染，不直接fetch
```

### 建议2：模块间导航矩阵

| 从 | 到 | 导航方式 |
|----|----|---------|
| 分析链 | 资料风险分析报告 | "查看完整报告"按钮 |
| 资料风险分析报告 | 分析链 | "查看分析过程"按钮 |
| 质量保障体系 | 稽查指令/线索链/证据链 | 每个组件附"查看详情"链接 |
| 域分析 | 稽查指令 | 每个域附"查看相关规则"链接 |
| 稽查指令 | 域分析 | 每条规则附"查看触发发现"链接 |
| 线索链 | 证据链 | "关联证据链"链接 |

### 建议3：统一报告渲染管道

当前 `renderAnalyzeResult`(分析链)、`renderTaxDocReport`(报告)、`renderFilterResult`(过滤器) 各自渲染发现列表。建议提取统一组件：
```javascript
function renderFindingsList(findings, options) {
  // options: { showSource, showSteps, showEvidence, collapsible }
}
```

---

## 修复工作量评估

| 优先级 | 修复项数 | 预估工时 | 影响模块 |
|--------|---------|---------|---------|
| P0 | 4项 | 2-3小时 | 全系统 |
| P1 | 3项 | 4-6小时 | API层+模块8/10/4 |
| P2 | 3项 | 2-3小时 | 代码清理 |
| P3 | 3项 | 3-4小时 | UI体验 |
| 架构 | 3项 | 8-12小时 | 全系统重构 |
| **合计** | **16项** | **19-28小时** | — |
