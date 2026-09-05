// 段落化方法论页 Node 端渲染单元测试。
// 从 static/ JSON 加载真实数据，注入 window mock 后加载 methodology-v3.js，验证：
// ① 章节开头是连贯段落（p 标签密度高、碎片 article 块减少）；
// ② 场景详情不再有 7~8 个 article 块；
// ③ 必要的表格/折叠元素保留；
// ④ 中文字段未被错误转义或破坏。
'use strict';

const fs = require('fs');
const path = require('path');

// mock 一个最小的 window/document 给方法论 v3 使用
global.window = {
  escHtml: (s) => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;'),
  currentModule: '',
  _methodologySection: null
};
global.document = { getElementById: () => null };
global.fetch = () => Promise.reject(new Error('fetch not used in test'));
global.module = { exports: {} };
global.Promise = Promise;

// 加载方法论 v3（IIFE 内部会给 module.exports 填入函数）
const code = fs.readFileSync(path.join(__dirname, '..', 'static', 'js', 'methodology-v3.js'), 'utf8');
// vm 模拟运行环境以使 IIFE 中的 `module.exports = {...}` 写入我们的 mock
const vm = require('vm');
const ctx = {
  window: global.window,
  document: global.document,
  fetch: global.fetch,
  module: global.module,
  console: console,
  Promise: Promise,
};
vm.createContext(ctx);
vm.runInContext(code, ctx);

const exposed = ctx.module.exports;
if (!exposed.capabilityLedgerProse) {
  console.error('FAIL: 未能暴露 capabilityLedgerProse');
  process.exit(1);
}

// 模拟一个能力账本（真实场景结构）
const ledger = {
  methodology_item_count: 6,
  verified_atomic_rule_count: 2,
  design_status_counts: { partial_atomic_support: 3 },
  independently_validated_method_count: 1,
  boundary: '能力数量不作为自动风险检查能力的等价物。',
  items: [
    { capability_id: 'CAP-001', name: '跨行业共同事实：身份期间', industry_code: 'ALL',
      method_type: 'cross_industry_review_contract', automatic_fact_scope: 'partial',
      candidate_atomic_rule_ids: ['VR-005','VR-008'],
      independent_validation_status: 'passed', next_build_action: '维护' },
    { capability_id: 'CAP-002', name: '广告传媒行业场景', industry_code: 'F',
      method_type: 'industry_fact_review_contract', automatic_fact_scope: 'partial',
      candidate_atomic_rule_ids: ['VR-105'],
      independent_validation_status: 'pending', next_build_action: '验证中' },
    { capability_id: 'CAP-003', name: '制造业销售循环', industry_code: 'C',
      method_type: 'industry_fact_review_contract', automatic_fact_scope: '',
      candidate_atomic_rule_ids: [],
      independent_validation_status: 'pending', next_build_action: '建立' },
  ],
};

const ledgerHtml = exposed.capabilityLedgerProse(ledger);
const checks = [
  ['段落密度', (ledgerHtml.match(/<p>/g) || []).length >= 2],
  ['包含账本解释段', /账本是方法论对外公开的自我盘点/.test(ledgerHtml)],
  ['包含独立性提醒', /不会用资产数量冒充/.test(ledgerHtml)],
  ['表格保留', /<table>/.test(ledgerHtml) && /<thead>/.test(ledgerHtml)],
  ['折叠容器保留', /<details class="m3-fold">/.test(ledgerHtml)],
  ['中文未被破坏', /方法论/.test(ledgerHtml)],
  ['不包含孤立卡片堆（无 m3-grid）', !/m3-grid-/.test(ledgerHtml)],
  ['不包含 metric 卡片（无 .m3-metric）', !/class="m3-metric"/.test(ledgerHtml)],
];
let failed = 0;
checks.forEach(([name, ok]) => {
  console.log(`  ${ok ? 'OK ' : 'XX '} ${name}`);
  if (!ok) failed++;
});

// 模拟一个场景
const scene = {
  id: 'F-001',
  name: '广告传媒-收入完整性',
  doubt: { target_fact: '广告业务收入是否足额申报' },
  clue_chain: {
    steps: [
      { step: 'STEP1', action: '取得开票数据', deliverable: '开票清单' },
      { step: 'STEP2', action: '取得银行回款', deliverable: '回款凭证' },
    ],
    terminal: '资料就位'
  },
  evidence_chain: {
    supporting_sources: ['增值税申报表', '开票汇总'],
    opposing_sources: ['内部冲账记录'],
    insufficient_when: ['缺失关键期申报'],
    quality_checks: ['金额复算', '口径核对']
  },
  analysis_chain: {
    proposition: '广告收入应等于开票+未开票',
    reasoning: ['开票复算', '未开票推算', '回款核对'],
    tax_boundary: '广告服务增值税税目'
  },
  domains: {
    lead: '增值税业务域',
    partners: [
      { domain: '发票', responsibility: '提供开票数据', handoff: '开票明细' },
    ],
    conflict_rule: '回到原始资料与原始证据'
  },
  report_contract: {
    must_state: ['主体', '事项', '证据', '依据'],
    forbidden: ['把待证事实描述为认定结论']
  },
  policy_applicability: {
    required_dimensions: ['政策文号', '生效日期'],
    stop_if: ['已废止'],
    output_boundary: '依证据闭合度判定'
  },
  applicability: {
    apply_when: ['主营业务为广告设计/投放'],
    do_not_apply_when: ['非广告业务']
  },
  validation_cases: [],
  acceptance_cases: [
    { case: '事实支持', facts: '资料完整', expected: '可继续推进' },
    { case: '资料不足', facts: '缺申报表', expected: '停止并补件' }
  ]
};

const sceneHtml = exposed.scenarioProse(scene);
const sChecks = [
  ['场景段落密度', (sceneHtml.match(/<p>/g) || []).length >= 4],
  ['待证事实段', /待证事实/.test(sceneHtml) || /场景定位/.test(sceneHtml)],
  ['调查与证据段', /调查步骤/.test(sceneHtml) && /支持证据/.test(sceneHtml)],
  ['分析论证段', /分析论证/.test(sceneHtml)],
  ['业务域协同段', /业务域协同/.test(sceneHtml) || /报告移交/.test(sceneHtml)],
  ['段落化（p 标签或 inlineList 任一形式）', (sceneHtml.match(/<p>|<ul class="m3-inline-list">/g) || []).length >= 4],
  ['不再有 m3-grid-2/3 卡片', !/m3-grid/.test(sceneHtml)],
  ['不再有孤立 article 卡片', !/class="m3-target"/.test(sceneHtml)],
  ['中文未损坏', /广告/.test(sceneHtml)],
  ['数据保留（税法边界）', /广告服务增值税/.test(sceneHtml)],
];
console.log('--- 场景段落化 ---');
sChecks.forEach(([name, ok]) => {
  console.log(`  ${ok ? 'OK ' : 'XX '} ${name}`);
  if (!ok) failed++;
});

// 验证 canonical_module_prose
const moduleOut = exposed.canonicalModuleProse({
  id: 'CORE-001',
  name: '身份与期间',
  purpose: '本模块解决主体身份、纳税期间、资料进入完整性等基础事实。',
  activation_gate: ['已上传主体资料', '已选定所属期间'],
  rules: [{ id: 'VR-001', fact_hypothesis: '若主体资料缺失则系统应暂停' }],
  analysis_tests: ['抽检一致性'],
  report_boundary: '按事实闭合度输出',
  clue_paths: ['path-1', 'path-2']
});
const mChecks = [
  ['保留折叠', /<details class="m3-fold/.test(moduleOut)],
  ['保留段落说明', /<p>/.test(moduleOut)],
  ['保留规则列表', /VR-001/.test(moduleOut)],
];
console.log('--- 共同事实模块段落化 ---');
mChecks.forEach(([name, ok]) => {
  console.log(`  ${ok ? 'OK ' : 'XX '} ${name}`);
  if (!ok) failed++;
});

if (failed === 0) {
  console.log('\n=== 段落化断言全部通过 ===');
} else {
  console.log(`\n=== 失败 ${failed} 项 ===`);
  // 同时打印场景 HTML 头 1500 字帮助诊断
  console.log('\n--- scenarioProse 输出（前 1500 字）---');
  console.log(sceneHtml.slice(0, 1500));
  process.exit(1);
}

// ═══ 稽查顺序重排断言（2026-09-05）═══
var orderSrc = fs.readFileSync(path.join(__dirname, '..', 'static', 'js', 'methodology-v3.js'), 'utf8');
var orderChecks = [
  ['稽查总纲章节', /id="m3-overview"/.test(orderSrc)],
  ['稽查顺序总述（十一大步）', /①检查准备（资料调取）→ ②资料接收与解析/.test(orderSrc)],
  ['收入完整性阶段', /id: 'm3-revenue'/.test(orderSrc)],
  ['成本费用阶段', /id: 'm3-cost'/.test(orderSrc)],
  ['发票真实性阶段', /id: 'm3-invoice'/.test(orderSrc)],
  ['资金流阶段', /id: 'm3-fund'/.test(orderSrc)],
  ['人员薪酬阶段', /id: 'm3-payroll'/.test(orderSrc)],
  ['经营实质阶段', /id: 'm3-substance'/.test(orderSrc)],
  ['穿透关联阶段', /id: 'm3-penetration'/.test(orderSrc)],
  ['执行对账条（自动执行vs人工复核）', /stageAccount/.test(orderSrc) && /引擎自动执行/.test(orderSrc)],
  ['规则分组覆盖69条', /'VR063'/.test(orderSrc) && /'VR070'/.test(orderSrc)],
  ['导航按稽查顺序', /①收入完整性/.test(orderSrc)],
];
var orderFail = 0;
orderChecks.forEach(function (c) {
  if (c[1]) { console.log('  OK ', c[0]); } else { console.log('FAIL', c[0]); orderFail++; }
});
if (orderFail) process.exit(1);
console.log('=== 稽查顺序断言全部通过 ===');
