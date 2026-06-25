// ==================== 全局状态 ====================
var currentPage = 'dashboard';
var currentPeriod = '';
var allAccounts = [];

// 多公司全局状态（供所有模块访问）
var currentCompanyId = 1;
var currentCompanyName = '';
var allCompanies = [];

// 文件导入全局状态
var _importFile = null;
var _importModule = '';
var _importBankConfigId = null;

// ==================== 全局工具函数 ====================
function escapeHtml(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
var esc = escapeHtml;      // 全局统一转义函数（简写）
var escHtml = escapeHtml;  // 全局统一转义函数（全名，供 tax-pipeline-pages / tax-risk-rules 等模块使用）

const pages = {
  'chat': '财税问答',
  'dashboard': '数据看板',
  'company': '公司信息',
  'departments': '部门档案',
  'employees': '人员档案',
  'customers': '客户档案',
  'suppliers': '供应商档案',
  'general-ledger': '总账',
  'detail-ledger': '科目明细账',
  'employee-ledger': '人员明细账',
  'customer-ledger': '客户明细账',
  'supplier-ledger': '供应商明细账',
  'journal': '序时账',
  'profit-loss': '利润表',
  'balance-sheet': '资产负债表',
  'cash-flow': '现金流量表',
  'equity-changes': '所有者权益变动表',
  'account-balance': '科目余额表',
  'accounts': '会计科目',
  'periods': '期间管理',
  'fixed-assets': '固定资产',
  'intangible-assets': '无形资产',
  'inventory': '库存管理',
  'contracts': '合同管理',
  'payments': '付款管理',
  'sales-invoices': '开具发票',
  'purchase-invoices': '取得发票',
  'input-vat-deductions': '进项认证',
  'bank-transactions': '银行流水',
  'vat-declaration': '增值税',
  'salary': '工资薪金',
  'social-security': '社会保险费',
  'housing-fund': '住房公积金',
  'bookkeeping-invoices': '记账发票',
  'tax-risk-report': '账务风险分析报告',
  'tax-risk-rules': '涉税风险稽查指令',
  'tax-doc-analysis': '资料风险分析报告',
  'file-parsing': '文件解析',
  'domain-analysis': '域分析',
  'methodology-filter': '方法论过滤器',
  'pipeline-rules': '稽查指令',
  'chains-page': '线索链',
  'evidence-page': '证据链',
  'analyze-page': '分析链',
  'quality-system': '全链路质量保障体系',
  'cross-domain-evidence': '跨域证据链',
  'cross-domain-clues': '跨域线索链',
  'cross-domain-analysis': '跨域分析链',
  'system-logs': '系统日志',
  'ai-rules': '智哥行为准则',
  'auditor-handbook': '税务稽查员手册',
  'report-standards': '报告编制要求',
  'tax-agi': '税务AGI'
};

// ==================== 用户登录 ====================
function getCurrentUser() {
  try {
    var data = JSON.parse(localStorage.getItem('taxUser') || 'null');
    return data || null;
  } catch(e) { return null; }
}

// 全局 fetch 拦截：所有请求自动附加用户信息
(function() {
  var _origFetch = window.fetch;
  window.fetch = function(url, options) {
    options = options || {};
    options.headers = options.headers || {};
    var user = getCurrentUser();
    if (user) {
      options.headers['X-User-Name'] = encodeURIComponent(user.name);
      options.headers['X-User-Phone'] = encodeURIComponent(user.phone);
    }
    return _origFetch(url, options);
  };
})();

function handleUserLogin(e) {
  e.preventDefault();
  var name = document.getElementById('user-login-name').value.trim();
  var phone = document.getElementById('user-login-phone').value.trim();
  if (!name || !phone) { toast('请填写姓名和手机号', 'warning'); return; }
  if (!/^1[3-9]\d{9}$/.test(phone)) { toast('手机号格式不正确', 'warning'); return; }
  
  var user = { name: name, phone: phone, loginAt: new Date().toISOString() };
  localStorage.setItem('taxUser', JSON.stringify(user));
  document.getElementById('user-register-overlay').style.display = 'none';
  // 继续正常初始化流程
  initAppFlow();
}

// 分离出应用入口，登录后再调用
async function initAppFlow() {
  const companies = await loadCompaniesRaw();
  window._companiesForPick = companies || [];

  // 如果刷新前在建档页，保持建档页
  if (sessionStorage.getItem('onRegistrationPage') === '1') {
    showRegistration();
    return;
  }

  if (!companies || companies.length === 0) {
    showRegistration();
    return;
  }
  // 记住上次选择的公司，刷新直接进入
  const lastCompanyId = localStorage.getItem('lastCompanyId');
  const lastCompanyName = localStorage.getItem('lastCompanyName');
  if (lastCompanyId && lastCompanyName) {
    const exists = companies.some(c => String(c.id) === String(lastCompanyId));
    if (exists) {
      await enterApp(parseInt(lastCompanyId), lastCompanyName);
      return;
    }
  }
  showCompanyPick(companies);
}

async function loadCompaniesRaw() {
  try {
    return await fetch('/api/companies').then(r => r.json());
  } catch (e) {
    return [];
  }
}

function showRegistration() {
  document.getElementById('registration-view').classList.remove('hidden');
  document.getElementById('company-pick-view').classList.add('hidden');
  document.getElementById('app-view').classList.add('hidden');
  // 标记用户在建档页，刷新时保留
  sessionStorage.setItem('onRegistrationPage', '1');
  // 如果有已有公司，显示"返回选择"链接
  const hasExisting = (window._companiesForPick && window._companiesForPick.length > 0);
  document.getElementById('reg-back-hint').style.display = hasExisting ? '' : 'none';
}

function showCompanyPick(companies) {
  sessionStorage.removeItem('onRegistrationPage');
  // 没有公司时直接跳建档页
  if (!companies || companies.length === 0) {
    showRegistration();
    return;
  }
  const list = document.getElementById('pick-list');
  list.innerHTML = companies.map(c => {
    const initial = c.name ? c.name.charAt(0) : '公';
    return '<li onclick="enterApp(' + c.id + ', \'' + escapeHtml(c.name) + '\')">'
      + '<div class="av">' + initial + '</div>'
      + '<div class="info"><div class="cn">' + escapeHtml(c.name) + '</div>'
      + (c.uscc ? '<div class="us">' + escapeHtml(c.uscc) + '</div>' : '')
      + '</div><div class="arr">→</div>'
      + '<button class="pick-del-btn" onclick="event.stopPropagation();deleteCompanyFromPick(' + c.id + ',\'' + escapeHtml(c.name) + '\')" title="删除此账套">🗑</button>'
      + '</li>';
  }).join('');
  document.getElementById('registration-view').classList.add('hidden');
  document.getElementById('company-pick-view').classList.remove('hidden');
  document.getElementById('app-view').classList.add('hidden');
}

async function deleteCompanyFromPick(companyId, companyName) {
  if (!confirm('确定要删除账套「' + companyName + '」吗？\n\n⚠️ 此操作不可逆，该账套下的所有数据（凭证、发票、报表等）将一并删除。')) return;
  try {
    // 如果删除的是当前已登录的公司，先清除记录
    if (currentCompanyId === companyId) {
      localStorage.removeItem('lastCompanyId');
      localStorage.removeItem('lastCompanyName');
      currentCompanyId = 1;
      currentCompanyName = '';
    }
    await fetch('/api/companies/' + companyId, { method: 'DELETE' });
    toast('账套「' + companyName + '」已删除', 'success');
    // 刷新选择列表
    const companies = await loadCompaniesRaw();
    window._companiesForPick = companies || [];
    if (!companies || companies.length === 0) {
      localStorage.removeItem('lastCompanyId');
      localStorage.removeItem('lastCompanyName');
      showRegistration();
    } else {
      showCompanyPick(companies);
    }
  } catch (e) {
    toast('删除失败：' + e.message, 'error');
  }
}

async function enterApp(companyId, companyName) {
  sessionStorage.removeItem('onRegistrationPage');
  currentCompanyId = companyId;
  currentCompanyName = companyName;
  localStorage.setItem('lastCompanyId', companyId);
  localStorage.setItem('lastCompanyName', companyName);
  document.getElementById('registration-view').classList.add('hidden');
  document.getElementById('company-pick-view').classList.add('hidden');
  document.getElementById('app-view').classList.remove('hidden');
  // 显示当前用户
  var user = getCurrentUser();
  var userEl = document.getElementById('sidebar-user-name');
  if (userEl && user) userEl.textContent = user.name + ' (' + user.phone + ')';
  await loadCompanies();
  await loadCurrentPeriod();
  await loadAllAccounts();
  const lastPage = localStorage.getItem('lastPage') || 'dashboard';
  navigateTo(lastPage);
}

async function exitCompany() {
  // 清除记录的账套信息，返回公司选择页
  localStorage.removeItem('lastCompanyId');
  localStorage.removeItem('lastCompanyName');
  localStorage.removeItem('lastPage');
  currentCompanyId = 1;
  currentCompanyName = '';
  const companies = await loadCompaniesRaw();
  window._companiesForPick = companies || [];
  showCompanyPick(companies);
}

// ==================== 全局 AI 自动处理 ====================
async function globalAIAutoProcess() {
  const btn = document.querySelector('.btn-ai-auto');
  if (!currentCompanyId) { toast('请先选择账套', 'warning'); return; }
  if (!window.currentModule) { toast('请先进入一个功能模块', 'warning'); return; }

  const module = window.currentModule;
  const moduleFuncMap = {
    '文化事业建设费': 'ccfAIAutoFill',
    '增值税': 'vatAIAutoFill',
    '工资薪金': 'salaryAIAutoFill',
    '社会保险费': 'ssAIAutoFill',
    '住房公积金': 'hfAIAutoFill',
    '销项发票': 'siAIAutoFill',
    '进项发票': 'piAIAutoFill',
    '银行流水': 'bankAIAutoFill',
  };

  const funcName = moduleFuncMap[module];
  if (!funcName) {
    toast('当前模块【' + module + '】暂不支持 AI 自动处理', 'info');
    return;
  }

  if (!window[funcName]) {
    toast('当前模块【' + module + '】的 AI 处理函数尚未实现', 'info');
    return;
  }

  // 禁用按钮，防止重复点击
  if (btn) { btn.disabled = true; btn.textContent = '🤖 AI 处理中...'; }

  try {
    toast('正在对【' + module + '】执行 AI 自动处理...', 'info');
    await window[funcName]();
  } catch (err) {
    console.error('AI 自动处理失败:', err);
    toast('AI 自动处理失败：' + (err.message || err), 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '🤖 AI 自动处理'; }
  }
}

async function handleCompanyRegister(e) {
  e.preventDefault();
  const btn = document.getElementById('reg-submit-btn');
  btn.disabled = true;
  btn.textContent = '⏳ 正在创建...';

  const name = document.getElementById('reg-name').value.trim();
  if (!name) { toast('请输入公司全称', 'error'); btn.disabled = false; btn.textContent = '✅ 创建账套，进入系统'; return; }

  const body = {
    name: name,
    uscc: document.getElementById('reg-uscc').value.trim() || null
  };

  try {
    const data = await fetch('/api/companies', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(r => { if (!r.ok) return r.json().then(err => { throw new Error(err.detail || '创建失败'); }); return r.json(); });
    toast('公司「' + data.name + '」创建成功，正在进入系统...', 'success');
    setTimeout(() => enterApp(data.id, data.name), 600);
  } catch (err) {
    toast('创建失败：' + err.message, 'error');
    btn.disabled = false;
    btn.textContent = '✅ 创建账套，进入系统';
  }
}


async function loadCurrentPeriod() {
  const yearSel = document.getElementById('period-year');
  if (!yearSel) return;
  let ops = '<option value="">年</option>';
  let now = new Date();
  let curY = now.getFullYear();
  for (let y = curY - 5; y <= curY + 5; y++) ops += `<option value="${y}">${y}年</option>`;
  yearSel.innerHTML = ops;

  const saved = localStorage.getItem('currentPeriod');
  if (saved && /^\d{4}-\d{2}$/.test(saved)) {
    const [y, m] = saved.split('-');
    yearSel.value = y;
    const monthSel = document.getElementById('period-month');
    if (monthSel) monthSel.value = m;
    currentPeriod = saved;
  }
}

function periodToDateRange(period) {
  if (!period || !/^\d{4}-\d{2}$/.test(period)) return { from: '', to: '' };
  const [y, m] = period.split('-').map(Number);
  const lastDay = new Date(y, m, 0).getDate();
  return { from: period + '-01', to: period + '-' + String(lastDay).padStart(2, '0') };
}

function onPeriodSelectChange() {
  const y = document.getElementById('period-year')?.value;
  const m = document.getElementById('period-month')?.value;
  if (!y || !m) return;
  const newPeriod = y + '-' + m;
  if (newPeriod === currentPeriod) return;
  currentPeriod = newPeriod;
  localStorage.setItem('currentPeriod', currentPeriod);
  // 同步所有已渲染页面的期间筛选框到新期间
  ['gl-from','gl-to','dl-from','dl-to','pl-from','pl-to','bs-from','bs-to','cf-from','cf-to','ec-from','tb-from','tb-to','je-from','je-to'].forEach(function(prefix) {
    let ey = document.getElementById(prefix + '-y');
    let em = document.getElementById(prefix + '-m');
    if (ey) ey.value = y;
    if (em) em.value = m;
  });
  // 同步工资薪金
  try { currentSalaryPeriod = newPeriod; } catch(e) {}
  let sy = document.getElementById('salary-y');
  let sm = document.getElementById('salary-m');
  if (sy) sy.value = y;
  if (sm) sm.value = m;
  // 同步往来明细账（人员/客户/供应商）
  ['employee','customer','supplier'].forEach(function(type) {
    ['from','to'].forEach(function(side) {
      let ey = document.getElementById(type + '-' + side + '-y');
      let em = document.getElementById(type + '-' + side + '-m');
      if (ey) ey.value = y;
      if (em) em.value = m;
    });
  });
  // 同步文化事业建设费
  try { ccfFilterPeriod = newPeriod; ccfCurrentData = null; } catch(e) {}
  let ccfY = document.getElementById('ccf-detail-year');
  let ccfM = document.getElementById('ccf-detail-month');
  if (ccfY) ccfY.value = y;
  if (ccfM) ccfM.value = m;
  try { siFilter.dateFrom = ''; siFilter.dateTo = ''; } catch(e) {}
  try { piFilter.dateFrom = ''; piFilter.dateTo = ''; } catch(e) {}
  try { ivdFilter.dateFrom = ''; ivdFilter.dateTo = ''; } catch(e) {}
  navigateTo(currentPage);
}

// 全局期间确认：所有模块时间栏同步到顶格栏期间，并刷新当前页面数据
function globalPeriodConfirm() {
  const y = document.getElementById('period-year')?.value;
  const m = document.getElementById('period-month')?.value;
  if (!y || !m) { toast('请先在顶格栏选择年份和月份', 'warning'); return; }
  const newPeriod = y + '-' + m;
  currentPeriod = newPeriod;
  localStorage.setItem('currentPeriod', currentPeriod);

  // ===== 状态变量（影响 re-render/下次渲染时的默认值）必须在 navigateTo 之前设置 =====
  try { currentSalaryPeriod = newPeriod; } catch(e) {}
  try { vatFilterPeriod = newPeriod; vatSelectedId = null; vatCurrentData = null; } catch(e) {}
  try { ssFilterPeriod = newPeriod; } catch(e) {}
  try { ccfFilterPeriod = newPeriod; ccfCurrentData = null; } catch(e) {}

  // ===== DOM 直接同步（已渲染但当前未激活的页面，下次切换过去时生效） =====
  // 1. 序时账/总账/明细账/报表 (from-to)
  ['gl','dl','pl','bs','cf','ec','tb','je'].forEach(function(prefix) {
    ['from','to'].forEach(function(side) {
      let ey = document.getElementById(prefix + '-' + side + '-y');
      let em = document.getElementById(prefix + '-' + side + '-m');
      if (ey) ey.value = y;
      if (em) em.value = m;
    });
  });

  // 2. 往来明细账（人员/客户/供应商）
  ['employee','customer','supplier'].forEach(function(type) {
    ['from','to'].forEach(function(side) {
      let ey = document.getElementById(type + '-' + side + '-y');
      let em = document.getElementById(type + '-' + side + '-m');
      if (ey) ey.value = y;
      if (em) em.value = m;
    });
  });

  // 3. 工资薪金 DOM
  let sy = document.getElementById('salary-y');
  let sm = document.getElementById('salary-m');
  if (sy) sy.value = y;
  if (sm) sm.value = m;

  // 4. 住房公积金 DOM
  let hy = document.getElementById('hf-year');
  let hm = document.getElementById('hf-month');
  if (hy) hy.value = y;
  if (hm) hm.value = m;

  // 5. 社会保险费 DOM
  let ssPeriod = document.getElementById('ss-filter-period');
  if (ssPeriod) ssPeriod.value = newPeriod;

  // 6. 文化事业建设费 DOM
  let ccfY = document.getElementById('ccf-detail-year');
  let ccfM = document.getElementById('ccf-detail-month');
  if (ccfY) ccfY.value = y;
  if (ccfM) ccfM.value = m;

  // 7. 发票/抵扣筛选器
  try { siFilter.dateFrom = ''; siFilter.dateTo = ''; } catch(e) {}
  try { piFilter.dateFrom = ''; piFilter.dateTo = ''; } catch(e) {}
  try { ivdFilter.dateFrom = ''; ivdFilter.dateTo = ''; } catch(e) {}

  // ===== 刷新当前页面（re-render 会读状态变量决定默认期间） =====
  navigateTo(currentPage);
  toast('已同步所有模块到 ' + newPeriod, 'success');
}

function stepPeriodYear(delta) {
  const sel = document.getElementById('period-year');
  if (!sel || !sel.value) return;
  sel.value = parseInt(sel.value) + delta;
}

function stepPeriodMonth(delta) {
  const sel = document.getElementById('period-month');
  if (!sel || !sel.value) return;
  let m = parseInt(sel.value) + delta;
  if (m > 12) { m = 1; stepPeriodYear(1); }
  else if (m < 1) { m = 12; stepPeriodYear(-1); }
  sel.value = String(m).padStart(2, '0');
}

async function loadAllAccounts() {
  try {
    allAccounts = await api('/api/accounts');
  } catch (e) {}
}

// ==================== 路由 ====================
// 每页独立容器，切换只 show/hide，不清空 DOM
const _pageContainers = {};
function _ensureContainer(page) {
  if (_pageContainers[page]) return _pageContainers[page];
  let el = document.getElementById('page-' + page);
  if (!el) {
    el = document.createElement('div');
    el.id = 'page-' + page;
    el.style.display = 'none';
    document.getElementById('content-area').appendChild(el);
  }
  _pageContainers[page] = el;
  return el;
}

function navigateTo(page) {
  currentPage = page;
  // 离开资料分析页时标记为非活跃
  if (typeof taxDocPageActive !== 'undefined') taxDocPageActive = false;
  if (typeof taxDocAnalyzing !== 'undefined' && taxDocAnalyzing) {
    // 有正在进行中的分析，标记为非活跃但不禁用（分析继续在后台运行）
  }
  console.log('[navigateTo] 切换到：' + page);
  localStorage.setItem('lastPage', page);
  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.page === page);
  });
  document.getElementById('page-title').textContent = pages[page] || page;

  // 隐藏所有页面容器，只显示当前页
  document.querySelectorAll('#content-area > [id^="page-"]').forEach(el => el.style.display = 'none');
  const container = _ensureContainer(page);
  container.style.display = '';

  // 每次切换都自动刷新页面
  switch (page) {
    case 'dashboard': renderDashboard(container); break;
    case 'journal': renderJournal(container); break;
    case 'general-ledger': renderGeneralLedger(container); break;
    case 'detail-ledger': renderDetailLedger(container); break;
    case 'employee-ledger': renderEmployeeLedger(container); break;
    case 'customer-ledger': renderCustomerLedger(container); break;
    case 'supplier-ledger': renderSupplierLedger(container); break;
    case 'profit-loss': renderProfitLoss(container); break;
    case 'balance-sheet': renderBalanceSheet(container); break;
    case 'cash-flow': renderCashFlow(container); break;
    case 'equity-changes': renderEquityChanges(container); break;
    case 'account-balance': renderAccountBalance(container); break;
    case 'accounts': renderAccounts(container); break;
    case 'periods': renderPeriods(container); break;
    case 'company': showCompanyManager(container); break;
    case 'departments': renderDepartments(container); break;
    case 'employees': renderEmployees(container); break;
    case 'customers': renderCustomers(container); break;
    case 'suppliers': renderSuppliers(container); break;
    case 'fixed-assets': renderFixedAssets(container); break;
    case 'intangible-assets': renderIntangibleAssets(container); break;
    case 'inventory': renderInventory(container); break;
    case 'contracts': renderContracts(container); break;
    case 'payments': renderPayments(container); break;
    case 'sales-invoices': renderSalesInvoices(container); break;
    case 'purchase-invoices': renderPurchaseInvoices(container); break;
    case 'bookkeeping-invoices': renderBookkeepingInvoices(container); break;
    case '未记账发票': renderUnbookkeptInvoices(container); break;
    case 'input-vat-deductions': renderInputVATDeductions(container); break;
    case 'bank-transactions': renderBankTransactions(container); break;
    case 'vat-declaration': renderVATDeclaration(container); break;
    case 'salary': showSalaryPage(container); break;
    case 'social-security': renderSocialSecurity(container); break;
    case 'housing-fund': renderHousingFund(container); break;
    case '文化事业建设费': renderCulturalConstructionFee(container); break;
    case 'tax-risk-report': renderTaxRiskReport(container); break;
    case 'tax-risk-rules': renderTaxRiskRules(container); break;
    case 'tax-doc-analysis': renderTaxDocAnalysis(container); break;
    case 'file-parsing': renderFileParsingPage(container); break;
    case 'domain-analysis': renderDomainAnalysisPage(container); break;
    case 'methodology-filter': renderMethodologyFilterPage(container); break;
    case 'pipeline-rules': renderTaxRiskRules(container); break;
    case 'chains-page': renderChainsPage(container); break;
    case 'evidence-page': renderEvidencePage(container); break;
    case 'analyze-page': renderAnalyzePage(container); break;
    case 'quality-system': renderQualitySystem(container); break;
    case 'cross-domain-evidence': renderCrossDomainEvidencePage(container); break;
    case 'cross-domain-clues': renderCrossDomainCluesPage(container); break;
    case 'cross-domain-analysis': renderCrossDomainAnalysisPage(container); break;
    case 'system-logs': renderSystemLogs(container); break;
    case 'ai-rules': renderAiRules(container); break;
    case 'auditor-handbook': renderAuditorHandbook(container); break;
    case 'report-standards': renderReportStandards(container); break;
    case 'engine-dashboard': renderEngineDashboardPage(container); break;
    case 'engine-dimensions': renderEngineDimensions(container); break;
    case 'tax-agi': renderAgiDashboard(container); break;
  }
  var ca = document.getElementById('content-area');
  if (ca) ca.scrollTop = 0;
}

document.querySelectorAll('.nav-item').forEach(el => {
  el.addEventListener('click', () => navigateTo(el.dataset.page));
});

// ==================== API 工具（多公司版本） ====================
async function api(method, url, body) {
  // 支持三种调用方式：api(url) / api(url, options) / api(method, url, body)
  var extraHeaders = {};  // 旧式调用传递的自定义 headers
  var extraQuery = {};    // 旧式调用传递的 URL 查询参数（skip/limit 等）
  if (arguments.length === 1) {
    // api(url) → GET 请求
    body = undefined;
    url = method;
    method = 'GET';
  } else if (arguments.length === 2 && typeof method === 'string' && !['GET','POST','PUT','DELETE','PATCH'].includes(method.toUpperCase())) {
    // 旧式调用 api(url, options) — 提取 method/body/headers，其余视为查询参数
    let options = url;
    url = method;
    method = (options && options.method) || 'GET';
    body = (options && options.body) || undefined;
    if (options && options.headers) extraHeaders = options.headers;
    // 其余非 method/headers/body 的属性 → URL 查询参数
    if (options) {
      for (var k in options) {
        if (options.hasOwnProperty(k) && k !== 'method' && k !== 'headers' && k !== 'body') {
          extraQuery[k] = options[k];
        }
      }
    }
  }
  // 强制附加 company_id 参数（/api/companies 自身除外）
  if (url.includes('/api/') && !url.startsWith('/api/companies')) {
    const [base, query] = url.split('?');
    const params = new URLSearchParams(query || '');
    // 合并旧式调用的查询参数
    for (var k in extraQuery) {
      if (extraQuery.hasOwnProperty(k)) params.set(k, extraQuery[k]);
    }
    params.set('company_id', currentCompanyId || 1);
    url = base + '?' + params.toString();
  }
  const isFormData = body instanceof FormData;
  const fetchOptions = {
    method: method,
  };
  if (body !== undefined && body !== null) {
    if (isFormData) {
      fetchOptions.body = body;
      // 不设置 Content-Type，让浏览器自动设置（含 boundary）
    } else if (typeof body === 'object') {
      fetchOptions.headers = Object.assign({}, extraHeaders, { 'Content-Type': 'application/json' });
      fetchOptions.body = JSON.stringify(body);
    } else {
      fetchOptions.body = body;
      // 字符串 body（通常已是 JSON.stringify 结果）：设置 Content-Type
      fetchOptions.headers = Object.assign({}, extraHeaders, { 'Content-Type': 'application/json' });
    }
  }
  const res = await fetch(url, fetchOptions);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: '请求失败' }));
    throw new Error(err.detail || '请求失败');
  }
  return res.json();
}

function toast(msg, type = 'default') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

// ==================== 分页工具 ====================
var _paginationState = {};

function setPageState(key, skip, limit) {
  _paginationState[key] = { skip: skip || 0, limit: limit || 50 };
}

function getPageState(key) {
  return _paginationState[key] || { skip: 0, limit: 50 };
}

// ═══════════════════ 税务AGI 仪表盘 ═══════════════════
async function renderAgiDashboard(container) {
  container.innerHTML = '<div style="text-align:center;padding:60px;color:#64748b;"><div class="spinner"></div><p>加载税务AGI状态...</p></div>';
  try {
    var d1 = await fetch('/api/agi/pipeline/dashboard').then(function(r){return r.json();}).catch(function(){return {};});
    var d2 = await fetch('/api/agi/status').then(function(r){return r.json();}).catch(function(){return {};});

    var pipe = d1.ok ? d1 : {stats:{modules_connected:0,events_collected:0},total_events:0,modules_active:0,health:'idle',module_breakdown:[],knowledge_base:{},cross_memory:{analyses:0}};
    var agi = d2.ok ? d2 : {knowledge_base:{},healing:{},causal_network:{},cross_analysis:{},version:{features:[]},methodology:{},rule_discovery:{},patrol:{},legal_reasoning:{},trend_analysis:{},overrides:{},external_verify:{}};
    var kb = agi.knowledge_base || {};
    var cm = pipe.cross_memory || {};
    var stats = pipe.stats || {};
    var meth = agi.methodology || {};
    var rules = agi.rule_discovery || {};
    var patrol = agi.patrol || {};

    var h = '';
    h += '<div class="card card-fill"><div class="handbook-content" style="max-width:960px;">';
    
    // ═══ Hero ═══
    h += '<div class="hb-hero">';
    h += '<h1>🧬 税务AGI v' + (agi.version ? agi.version.agent : '2.1') + '</h1>';
    h += '<p>存勤法税·智能大脑 — 6大智能引擎 · 19模块知识管线 · 13项交互能力 · ' + pipe.total_events + '条学习事件 · ' + kb.analyses_count + '次历史分析</p>';
    h += '<div class="hb-status-bar hb-status-connected" style="margin-top:12px;">🔗 已连接 · 活跃模块 ' + pipe.modules_active + ' 个 · 因果边 ' + ((agi.causal_network||{}).edges||0) + ' 条 · 知识库 ' + (kb.lessons_count||0) + ' 条经验</div>';
    h += '</div>';

    // ═══ 一、6大智能引擎 ═══
    h += '<section class="hb-section">';
    h += '<h2 class="hb-section-title"><span class="hb-section-num">一</span> 6大智能引擎</h2>';
    h += '<p class="hb-section-lead">每个引擎在推理管线的不同阶段独立运行，协同工作形成完整的 AGI 能力。</p>';
    h += '<div class="hb-method-grid">';
    h += _agiEngineCard('🪞','自我反思器','SelfReflector','<code>agent_core.py</code>','对每条高风险结论生成反向假设并尝试证伪。14个维度：隐匿收入←可能只是个人转账、虚开发票←可能是长期合作、品名不匹配←可能因为外发加工。阈值：adj<-0.05→不确定，adj<-0.15→推翻。','红');
    h += _agiEngineCard('💡','洞见总结器','InsightSynthesizer','<code>agent_core.py</code>','五段式综合报告：①企业画像 ②风险全景 ③核心问题提炼 ④行业对标 ⑤优先行动建议。自动生成1054字级洞见总结。','蓝');
    h += _agiEngineCard('🧠','跨分析学习器','CrossAnalysisLearner','<code>agent_core.py</code>','多企业分析经验积累+行业通用模式归纳。每个行业独立记忆：常见高风险模式、典型数据画像。跨分析记忆持久化到 cross_analysis_memory.json。','绿');
    h += _agiEngineCard('📐','稽查方法论引擎','MethodologyEngine','<code>methodology_loader.py</code>','10种稽查方法论(M01-M10)：资料驱动/四步分析/进销存比对/资金流双向核对/供应商穿透/经营实质/客户三源穿透/发票五层审计/六员跨企业比对/地理分析。按域自动匹配适用方法论。','紫');
    h += _agiEngineCard('🔍','自动规则发现','RuleDiscovery','<code>rule_discovery.py</code>','三层归纳引擎——Layer A：模块效率分析→空跑率>80%→跳过规则；Layer B：纠正模式→同类纠正≥5次→通用修正；Layer C：信号模式对比→>60%同类企业出现→行业特征信号。结果输出到 discovered_rules.json。','橙');
    h += _agiEngineCard('🔄','自动巡逻引擎','PatrolEngine','<code>auto_patrol.py</code>','定期重分析已分析企业→对比前后结论：新增/消失/风险等级迁移。变化>30%→标记显著变化→验证AGI学习效果。快照存入 patrol_snapshots →下次巡逻自动加载做基线对比。','青');
    h += '</div></section>';

    // ═══ 二、19模块知识管线 ═══
    h += '<section class="hb-section">';
    h += '<h2 class="hb-section-title"><span class="hb-section-num">二</span> 19模块知识管线</h2>';
    h += '<p class="hb-section-lead">调度中枢(orchestrator.py)注册21个模块(M001-M021)，通过数据画像+依赖DAG自适应激活。当前 ' + pipe.modules_active + ' 个模块活跃，累计 ' + pipe.total_events + ' 条学习事件。</p>';
    h += '<table class="hb-table hb-table-striped">';
    h += '<thead><tr><th>领域</th><th>模块</th><th>功能</th><th style="width:70px;">状态</th></tr></thead><tbody>';
    var modules = [
      ['数据准备','M001 文件扫描','文件类型识别(34类指纹)·关键词打分·结构分析·数据推断兜底'],
      ['数据准备','M002 数据标准化','统一日期格式/金额单位/品名规范化/税号校验'],
      ['数据准备','M003 实体识别','企业名称→统一社会信用代码映射·六员信息提取'],
      ['核查','M004 联网核查','搜索引擎KG提取→公告抓取→结构化条件提取·三步法'],
      ['核查','M005 供应链核查','进销发票TOP10供应商/客户联网查·六员交叉比对·闭环检测'],
      ['核查','M019 政策有效期核实','90天缓存机制·chinatax.gov.cn/mof.gov.cn原文抓取·结构化验证'],
      ['分析','M006 Phase1信号检测','财务全景+企业画像+初查信号·信号→域映射12种'],
      ['分析','M007 Phase2定向深挖','基于Phase1信号定向深挖·盲跑域自动替换·深挖域优先展示'],
      ['分析','M008 18域分析','35域分析函数·跨域关联推理·多源证据链串联'],
      ['分析','M009 规则引擎','1505条稽查指令·34类风险规则·行业自适应'],
      ['分析','M010 链驱动引擎','405线索链+750证据链+38分析链·触发率评估'],
      ['分析','M017 财务报表稽查','资产负债表/利润表/现金流量表合规性核查'],
      ['分析','M018 税收优惠分析','9大类优惠智能分析·联网核查·结构化条件比对'],
      ['推理','M011 假设验证','HypothesisGenerator 10条假设模板·主动生成调查假设'],
      ['质量控制','M012 方法论过滤器','CAP(强制保留)/COND_BAN(禁止)/DEDUP(去重)三层·97%噪声过滤'],
      ['质量控制','M013 Phase3交叉验证','跨结论串联·矛盾检测·因果叙事链·置信度评分'],
      ['质量控制','M020 自动规则发现','三层归纳引擎：空跑检测→模式归纳→信号提取'],
      ['质量控制','M021 合规门禁','结论自洽性检查·法律依据完备性·事实可追溯性'],
      ['综合','M014 Phase4综合定性','风险分级+转移+具体建议·缺失触发+矛盾检测+因果链'],
      ['综合','M015 12维增强管线','资料缺失→后果触发·结论矛盾→报警·跨域因果→叙事'],
      ['输出','M016 报告渲染','多版本报告(详细/简报/底稿)·证据固化·关联图谱·整改跟踪'],
    ];
    for (var i = 0; i < modules.length; i++) {
      var m = modules[i];
      var pipeMod = (pipe.module_breakdown||[]).find(function(pm){return pm.module.indexOf(m[1].split(' ')[0])===0;});
      var active = pipeMod ? '🟢 运行中' : '⚪ 待启动';
      h += '<tr><td class="hb-td-label">' + m[0] + '</td><td><strong>' + m[1] + '</strong></td><td style="font-size:12px;color:#475569;">' + m[2] + '</td><td style="font-size:11px;text-align:center;">' + active + '</td></tr>';
    }
    h += '</tbody></table></section>';

    // ═══ 三、13项交互能力 ═══
    h += '<section class="hb-section">';
    h += '<h2 class="hb-section-title"><span class="hb-section-num">三</span> 13项交互能力</h2>';
    h += '<p class="hb-section-lead">所有交互能力集中在"资料风险分析报告"页面，一键分析完成后自动激活。</p>';
    h += '<div class="hb-method-grid" style="grid-template-columns:repeat(auto-fill,minmax(280px,1fr));">';
    var caps = [
      ['📋','多版本报告','详细版/简报版/稽查底稿版三种视图，一键切换','全面'],
      ['🔗','关联网络图谱','SVG拓扑图：客户/供应商/关联人绕心排列，购销闭环红色标注','拓扑'],
      ['🔒','电子证据固化','SHA256哈希链存证，每文件可追溯，完整性校验','存证'],
      ['🎯','智能抽样引擎','风险分层抽样：score×10+金额/10000综合评分，P0-P2分级','抽样'],
      ['📝','整改跟踪闭环','5状态流转：待整改→整改中→已完成→已核验→已关闭','闭环'],
      ['📈','多期趋势分析','进销比/资金流匹配率/毛利率/风险密度跨期对比，方向判断','趋势'],
      ['💬','对话式稽查','自然语言查询+5快捷问题+Web Speech API语音输入','对话'],
      ['🔄','自动巡检','定时/手动触发→前后结论对比→发现变化→AGI学习验证','巡逻'],
      ['🔮','风险预测模型','加权因子模型：进销比+资金流+风险密度+行业基准','预测'],
      ['⚖️','法规变更预警','9类优惠政策到期监测+影响评估+联网核查更新','预警'],
      ['📊','多企业集团分析','横向对比+共同风险类型+雷达图维度','对比'],
      ['📱','移动端驾驶舱','CSS媒体查询响应式，手机/平板自适应','响应'],
      ['🎤','语音提问','Web Speech API中文识别，支持口语化自然提问','语音'],
    ];
    for (var c = 0; c < caps.length; c++) {
      var cap = caps[c];
      h += '<div class="hb-method-card"><div class="hb-method-icon hb-m-icon-blue">' + cap[0] + '</div><h3>' + cap[1] + '</h3><p class="hb-method-principle">' + cap[2] + '</p><span style="font-size:11px;color:#94a3b8;background:#f1f5f9;padding:2px 8px;border-radius:4px;">' + cap[3] + '</span></div>';
    }
    h += '</div></section>';

    // ═══ 四、API端点清单 ═══
    h += '<section class="hb-section">';
    h += '<h2 class="hb-section-title"><span class="hb-section-num">四</span> API端点清单</h2>';
    h += '<p class="hb-section-lead">税务AGI注册的全部REST API端点，供前端和外部系统调用。</p>';
    h += '<table class="hb-table hb-table-striped">';
    h += '<thead><tr><th style="width:80px;">方法</th><th>端点</th><th>功能说明</th></tr></thead><tbody>';
    var apis = [
      ['GET','/api/agi/status','AGI完整状态面板（知识库+因果网络+方法论+规则+巡逻+法律推理+趋势）'],
      ['GET','/api/agi/pipeline/dashboard','19模块管道仪表盘数据（模块统计+事件计数+活跃状态）'],
      ['POST','/api/agi/query','自然语言查询分析结果（中文关键词匹配+知识库+因果网络）'],
      ['POST','/api/agi/chat','对话式税务稽查（查询+快捷问+统计+建议四合一）'],
      ['POST','/api/agi/self-check/{company_id}','闭环自检——高风险结论法律依据/事实/建议完备性检查'],
      ['GET','/api/agi/overrides/summary','AGI覆盖层概况（自主修正→安全回滚机制）'],
      ['GET','/api/agi/overrides/pending','待审核覆盖层列表'],
      ['POST','/api/agi/overrides/{id}/activate','激活覆盖层——AGI自主修正生效'],
      ['POST','/api/agi/overrides/{id}/rollback','回滚覆盖层——安全恢复'],
      ['POST','/api/agi/overrides/emergency-reset','紧急恢复——全部覆盖层回滚'],
      ['GET','/api/agi/patrol/status','自动巡逻状态查询（知识库概况+巡逻配置+快照统计）'],
      ['POST','/api/agi/patrol/trigger','手动触发巡逻——重分析+前后结论对比'],
      ['GET','/api/agi/verify-supplier','供应商工商验证（搜索引擎后备方案）'],
      ['GET','/api/agi/verify-channels','可用验证渠道查询（天眼查/企查查/工商/搜索引擎）'],
      ['POST','/api/agi/parallel/toggle','并行加速引擎开关'],
    ];
    for (var a = 0; a < apis.length; a++) {
      var api = apis[a];
      var methodColor = api[0]==='GET'?'#2563eb':api[0]==='POST'?'#16a34a':'#7c3aed';
      h += '<tr><td style="font-weight:700;color:'+methodColor+'">'+api[0]+'</td><td style="font-family:monospace;font-size:12px;">'+api[1]+'</td><td style="font-size:12px;color:#475569;">'+api[2]+'</td></tr>';
    }
    h += '</tbody></table></section>';

    // ═══ 五、知识库结构 ═══
    h += '<section class="hb-section">';
    h += '<h2 class="hb-section-title"><span class="hb-section-num">五</span> 知识库结构</h2>';
    h += '<p class="hb-section-lead">统一知识库(tax_agi_knowledge.json)存储全部学习成果，线程安全写锁保护。</p>';
    h += '<div class="hb-card-grid">';
    h += _agiInfoCard('📜','政策库','<code>policies</code>','9条税收优惠政策 · 结构化条件 · 有效期管理 · 联网核查更新','purple');
    h += _agiInfoCard('🔗','因果网络','<code>causal_edges</code>','信号→结论因果关系 · 置信度评分 · ' + ((agi.causal_network||{}).edges||0) + '条因果边','red');
    h += _agiInfoCard('📊','信号模式','<code>signal_patterns</code>','多信号组合模式 · 联合预测 · ' + ((agi.causal_network||{}).patterns||0) + '个模式','blue');
    h += _agiInfoCard('📖','语义词典','<code>semantic_dict</code>','14类语义同义词库 · 全行业品名/摘要/法规语义理解','green');
    h += _agiInfoCard('🏭','行业画像','<code>industry_profiles</code>','8大行业标准画像 · 财务指标基准 · 风险特征描述','yellow');
    h += _agiInfoCard('🔧','自愈规则','<code>healing_rules</code>','错误反馈→规则生成→自动修正 · ' + ((agi.healing||{}).active_rules||0) + '条活跃规则','purple');
    h += _agiInfoCard('🎓','经验教训','<code>lessons</code>','跨分析经验积累 · 行业通用模式 · ' + (kb.lessons_count||0) + '条经验','green');
    h += _agiInfoCard('📝','分析历史','<code>analysis_history</code>','保留最近100条分析记录 · 时间倒序 · 按企业分组','slate');
    h += _agiInfoCard('🔍','巡逻快照','<code>patrol_snapshots</code>','每次巡逻保存结论快照 · 前后对比基线 · ' + (patrol.companies_with_snapshots||0) + '家企业','cyan');
    h += '</div></section>';

    // ═══ 六、配置参数 ═══
    h += '<section class="hb-section">';
    h += '<h2 class="hb-section-title"><span class="hb-section-num">六</span> 配置参数</h2>';
    h += '<p class="hb-section-lead">所有可配置参数及其默认值。</p>';
    h += '<div class="hb-card-grid">';
    h += _agiConfigCard('自愈引擎','self_healing.py','5种错误模式：policy_expired/false_positive/false_negative/rate_wrong/condition_missing','同类错误≥2→自动生成修正规则');
    h += _agiConfigCard('自动巡逻','auto_patrol.py','最大企业数：5 · 触发阈值：因果边/模式增加≥2 · 变化阈值：>30%标记显著 · 间隔：1小时','巡逻快照持久化到 patrol_snapshots');
    h += _agiConfigCard('规则发现','rule_discovery.py','Layer A：空跑率>80%触发 · Layer B：同类型纠正≥5次 · Layer C：>60%同类企业出现','输出到 discovered_rules.json');
    h += _agiConfigCard('因果网络','causal_network.py','条件概率网络 · 信号共现→因果边 · 置信度计算 · 联合预测','从历史分析数据自主学习');
    h += _agiConfigCard('反思器','agent_core.py','阈值：adj<-0.05→不确定 · adj<-0.15→推翻 · 覆盖7种发现类型','14维度反向假设验证');
    h += _agiConfigCard('知识库','knowledge_base.py','线程安全写锁 · 全局单例 · 最大分析历史100条 · 持久化JSON','内存操作+异步磁盘写入');
    h += _agiConfigCard('联网核查','tax_incentive_analyzer.py','三步法：搜索URL→抓取页面→提取条件 · 90天缓存 · 双编码检测','chinatax.gov.cn/mof.gov.cn');
    h += _agiConfigCard('并行加速','parallel_runner.py','多模块并行执行 · 可开关 · 自动依赖DAG排序','提升分析速度30-50%');
    h += '</div></section>';

    // ═══ 七、法律推理+趋势+跨企业 ═══
    h += '<section class="hb-section">';
    h += '<h2 class="hb-section-title"><span class="hb-section-num">七</span> 三大专项引擎</h2>';
    h += '<div class="hb-method-grid">';
    h += _agiEngineCard('⚖️','法律推理引擎','LegalReasoner','<code>legal_reasoner.py</code>','三段论推理：大前提(法律条文)→小前提(企业事实)→结论(违法定性)。' + ((agi.legal_reasoning||{}).rules_loaded||0) + '条规则已加载。支持'+((agi.legal_reasoning||{}).domains||[]).join('+')+'等域。','红');
    h += _agiEngineCard('📈','趋势分析引擎','TrendAnalyzer','<code>trend_analyzer.py</code>','12项指标跨期追踪：毛利率/销售收入/采购金额/供应商数量/客户数量/发票数量/银行流入流出/工资总额/员工数量/税负率/净利率。趋势方向：上升/下降/持平。','绿');
    h += _agiEngineCard('🔗','跨企业关系网','CrossEnterpriseGraph','<code>cross_enterprise_graph.py</code>','自动发现系统内企业间的供应商/客户/人员关联关系。一人多角检测+跨企业人员重叠→关联交易→连锁稽查点。','蓝');
    h += '</div></section>';

    // ═══ 八、方法论索引 ═══
    h += '<section class="hb-section">';
    h += '<h2 class="hb-section-title"><span class="hb-section-num">八</span> 稽查方法论索引</h2>';
    h += '<p class="hb-section-lead">' + (meth.total_methods||10) + '种稽查方法 · ' + (meth.total_documents||14) + '类必查资料 · ' + (meth.total_laws||7) + '条法律条文</p>';
    if (meth.methods && meth.methods.length) {
      h += '<div class="hb-card-grid">';
      for (var mi = 0; mi < meth.methods.length; mi++) {
        h += '<div class="hb-law-card"><strong>M' + String(mi+1).padStart(2,'0') + '</strong><span class="hb-law-tag">方法论</span><p>' + meth.methods[mi] + '</p></div>';
      }
      h += '</div>';
    }
    h += '<div class="hb-callout hb-callout-green">🔗 详见"税务稽查员手册"页面——完整方法论详解+法律条文引用+工作流程对照。</div>';
    h += '</section>';

    // ═══ 底部 ═══
    h += '<div class="hb-footer">';
    h += '<p>🧬 税务AGI v' + (agi.version ? agi.version.agent : '2.1') + ' · 存勤法税智能大脑 · ' + pipe.total_events + '条学习事件 · ' + (agi.causal_network||{}).edges + '条因果边 · ' + ((agi.healing||{}).active_rules||0) + '条自愈规则 · 每次一键分析自动进化</p>';
    h += '</div>';

    h += '</div></div>'; // handbook-content + card-fill
    container.innerHTML = h;
  } catch(e) {
    _renderAgiFallback(container, e.message);
  }
}

function _agiEngineCard(icon, name, engName, codeRef, desc, color) {
  var colors = {红:'hb-m-icon-red',蓝:'hb-m-icon-blue',绿:'hb-m-icon-green',紫:'hb-m-icon-purple',橙:'hb-m-icon-yellow',青:'hb-m-icon-cyan'};
  return '<div class="hb-method-card"><div class="hb-method-icon '+colors[color]+'">'+icon+'</div><h3>'+name+' <span style="font-size:11px;font-weight:400;color:#94a3b8;">'+engName+'</span></h3><p class="hb-method-principle" style="font-size:11px;color:#64748b;margin:0 0 8px;">'+codeRef+'</p><div class="hb-method-items"><div class="hb-mi">'+desc+'</div></div></div>';
}

function _agiInfoCard(icon, name, code, desc, color) {
  var colors = {purple:'hb-info-purple',red:'hb-info-red',blue:'hb-info-blue',green:'hb-info-green',yellow:'hb-info-yellow',slate:'',cyan:''};
  var cls = colors[color] || '';
  var bg = color==='slate'?'background:#f1f5f9;':'';
  var bd = color==='cyan'?'background:#ecfeff;border-color:#a5f3fc;':'';
  return '<div class="hb-info-card '+cls+'" style="'+bg+bd+'"><strong>'+icon+' '+name+'</strong><p style="font-size:11px;color:#64748b;margin-top:4px;">'+code+'</p><p>'+desc+'</p></div>';
}

function _agiConfigCard(name, file, params, note) {
  return '<div class="hb-law-card"><strong>⚙️ '+name+'</strong><span class="hb-law-tag">'+file+'</span><p style="font-size:12px;color:#475569;line-height:1.5;">'+params+'</p><p style="font-size:11px;color:#64748b;">💡 '+note+'</p></div>';
}

function _agiCardMini(bg, color, value, label) {
  return '<div style="text-align:center;padding:16px 12px;background:'+bg+';border-radius:10px;"><div style="font-size:28px;font-weight:700;color:'+color+'">'+(value||0)+'</div><div style="font-size:12px;color:#6b7280;margin-top:4px">'+label+'</div></div>';
}

function _renderAgiFallback(container, errMsg) {
  container.innerHTML = '<div class="card card-fill"><div style="max-width:1100px;margin:0 auto;padding:20px;">' +
    '<div style="display:flex;align-items:center;gap:16px;margin-bottom:24px;padding:20px;background:linear-gradient(135deg,#0ea5e9,#8b5cf6);border-radius:12px;color:#fff;">' +
      '<div style="font-size:42px;">🧬</div>' +
      '<div><h2 style="margin:0 0 4px;font-size:22px;">税务AGI v2.0</h2>' +
      '<p style="margin:0;opacity:0.85;font-size:13px;">三大升级引擎 · 法律推理 · 跨企业关系 · 趋势学习</p></div>' +
    '</div>' +
    '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:20px;">' +
      '<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:10px;padding:16px;text-align:center;">' +
        '<div style="font-size:28px;margin-bottom:6px;">⚖️</div><div style="font-size:14px;font-weight:700;color:#991b1b;">法律逻辑推理</div>' +
        '<div style="font-size:11px;color:#7f1d1d;margin-top:4px;">10条条文·三段论推理</div></div>' +
      '<div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;padding:16px;text-align:center;">' +
        '<div style="font-size:28px;margin-bottom:6px;">🔗</div><div style="font-size:14px;font-weight:700;color:#1e40af;">跨企业关系网</div>' +
        '<div style="font-size:11px;color:#1e3a5f;margin-top:4px;">全系统企业关联检测</div></div>' +
      '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;padding:16px;text-align:center;">' +
        '<div style="font-size:28px;margin-bottom:6px;">📈</div><div style="font-size:14px;font-weight:700;color:#14532d;">时序趋势学习</div>' +
        '<div style="font-size:11px;color:#14532d;margin-top:4px;">12项指标跨期追踪</div></div>' +
    '</div>' +
    '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:16px;">' +
      _agiCard('📚','知识库','—','政策/因果边/信号模式') +
      _agiCard('🔬','语义引擎','—','全行业同义词库') +
      _agiCard('🛡️','自愈系统','—','错误→规则自动生成') +
      _agiCard('🧠','学习记忆','—','跨企业经验积累') +
    '</div>' +
    '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:20px;">' +
      _agiCard('🗣️','对话稽查','—','中文税务问答') +
      _agiCard('🔗','外部验证','—','天眼查/企查查/工商') +
      _agiCard('🔁','闭环自检','—','AGI自主修正覆盖层') +
      _agiCard('⚡','并行加速','—','多域并发分析') +
    '</div>' +
    '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:24px;margin-bottom:20px;">' +
      '<h3 style="margin:0 0 16px;font-size:16px;">🎯 10大核心能力</h3>' +
      '<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px;">' +
        ['感知引擎—多源文件解析与标准化','推理引擎—四步稽查分析法','学习引擎—自愈规则自动生成',
         '表达引擎—结构化报告生成','记忆引擎—跨企业知识积累','语义理解—税法同义匹配',
         '对话稽查—自然语言交互','外部验证—四通道联网核查','自我纠错—三层安全覆盖',
         '并行加速—ThreadPoolExecutor并发'].map(function(t,i){
          var icons=['🔍','📡','💡','🧬','🌐','🔗','❓','🗣️','🔁','⚡'];
          return '<div style="padding:10px 14px;background:#f8fafc;border-radius:8px;border-left:3px solid #0ea5e9;font-size:13px;">' +
            '<span>'+icons[i]+'</span> <strong>'+t.split('—')[0]+'</strong><br><span style="font-size:11px;color:#64748b;">'+(t.split('—')[1]||'')+'</span></div>';
        }).join('') +
      '</div></div>' +
    (errMsg ? '<div style="text-align:center;padding:12px;background:#fef2f2;border:1px solid #fecaca;border-radius:8px;color:#dc2626;font-size:13px;margin-bottom:20px;">⚠️ 连接异常：'+escapeHtml(errMsg)+' · 请刷新页面重试</div>' : '') +
    '<div style="text-align:center;padding:16px;color:#94a3b8;font-size:12px;">' +
      '税务AGI引擎嵌入在每次一键分析中自动运行 · 运行一键分析后数据将在此展示</div>' +
    '</div></div>';
}

function _agiCard(icon, title, value, subtitle) {
  return '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:16px 20px;text-align:center;">' +
    '<div style="font-size:28px;margin-bottom:4px;">'+icon+'</div>' +
    '<div style="font-size:20px;font-weight:700;color:#1e293b;">'+value+'</div>' +
    '<div style="font-size:13px;color:#0ea5e9;margin-top:2px;">'+title+'</div>' +
    '<div style="font-size:11px;color:#94a3b8;margin-top:4px;">'+subtitle+'</div></div>';
}

function renderPagination(container, total, key, onPageChange) {
  const state = getPageState(key);
  const currentPage = Math.floor(state.skip / state.limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / state.limit));
  if (totalPages <= 1) return;

  const html = `
    <div class="pagination">
      <button class="pag-btn" ${currentPage <= 1 ? 'disabled' : ''} onclick="event.stopPropagation();this.onclick=function(){${onPageChange}(0)}">
        « 首页
      </button>
      <button class="pag-btn" ${currentPage <= 1 ? 'disabled' : ''} onclick="event.stopPropagation();this.onclick=function(){${onPageChange}(${(currentPage-2)*state.limit})}">
        ‹ 上一页
      </button>
      <span class="pag-info">第 ${currentPage} / ${totalPages} 页</span>
      <button class="pag-btn" ${currentPage >= totalPages ? 'disabled' : ''} onclick="event.stopPropagation();this.onclick=function(){${onPageChange}(${currentPage*state.limit})}">
        下一页 ›
      </button>
      <button class="pag-btn" ${currentPage >= totalPages ? 'disabled' : ''} onclick="event.stopPropagation();this.onclick=function(){${onPageChange}(${(totalPages-1)*state.limit})}">
        末页 »
      </button>
    </div>`;
  container.insertAdjacentHTML('beforeend', html);
}

// 统一的 Modal 关闭函数：无参时移除 #modal-overlay（兼容 chat.js），有参时移除指定 id 元素（salary.js）
function closeModal(id) {
    if (id) { const el = document.getElementById(id); if (el) el.remove(); return; }
    document.getElementById('modal-overlay')?.remove();
}

function fmt(n) {
  if (n === null || n === undefined) return '-';
  return Number(n).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// ==================== 统一错误处理 ====================
function handleError(err, context) {
  const msg = context ? (context + '失败：' + err.message) : err.message;
  console.error('[' + (context || 'error') + ']', err);
  toast(msg, 'error');
}

function showError(el, err, context) {
  const msg = context ? (context + '失败：' + err.message) : err.message;
  console.error('[' + (context || 'error') + ']', err);
  el.innerHTML = '<div class="empty-state"><p style="color:var(--danger)">' + msg + '</p></div>';
}

// ==================== 凭证详情弹窗（通用）====================
// 点击凭证号时调用，voucherFull 格式："记-1"
function showVoucherDetail(voucherFull) {
    const idx = voucherFull.lastIndexOf('-');
    if (idx === -1) { alert('凭证号格式错误：' + voucherFull); return; }
    const voucher_word = voucherFull.substring(0, idx);
    const voucher_no = parseInt(voucherFull.substring(idx + 1));
    if (isNaN(voucher_no)) { alert('凭证号格式错误：' + voucherFull); return; }

    // 移除已有 modal
    const old = document.getElementById('voucher-detail-modal');
    if (old) old.remove();

    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.id = 'voucher-detail-modal';
    modal.innerHTML = `
        <div class="modal" style="max-width:900px;max-height:90vh;overflow-y:auto">
            <div class="modal-header">
                <h3>凭证详情 - ${escapeHtml(voucherFull)}</h3>
                <button class="modal-close" onclick="closeModal('voucher-detail-modal')">&times;</button>
            </div>
            <div class="modal-body" id="voucher-detail-body">
                <div style="text-align:center;padding:40px;color:#999;">加载中...</div>
            </div>
        </div>`;
    document.body.appendChild(modal);

    const url = `/api/journal-entries/by-voucher?voucher_word=${encodeURIComponent(voucher_word)}&voucher_no=${voucher_no}&company_id=${currentCompanyId}`;
    api(url).then(data => {
        const body = document.getElementById('voucher-detail-body');
        if (!body) return;
        let html = `
            <div style="margin-bottom:16px;font-size:13px;color:#666;">
                <span style="margin-right:24px;">期间：<b>${data.period || '-'}</b></span>
                <span style="margin-right:24px;">日期：<b>${data.entry_date || '-'}</b></span>
                <span>来源：<b>${escapeHtml(data.source || '-')}</b></span>
            </div>
            <table class="data-table" style="font-size:13px;">
                <thead><tr>
                    <th style="width:30%;">摘要</th>
                    <th style="width:15%;">科目编码</th>
                    <th style="width:25%;">科目名称</th>
                    <th style="width:15%;text-align:right;">借方金额</th>
                    <th style="width:15%;text-align:right;">贷方金额</th>
                </tr></thead>
                <tbody>`;
        (data.entries || []).forEach(e => {
            html += `<tr>
                <td>${escapeHtml(e.summary || '-')}</td>
                <td>${escapeHtml(e.account_code || '-')}</td>
                <td>${escapeHtml(e.account_name || '-')}</td>
                <td style="text-align:right;">${e.debit_amount ? Number(e.debit_amount).toLocaleString() : ''}</td>
                <td style="text-align:right;">${e.credit_amount ? Number(e.credit_amount).toLocaleString() : ''}</td>
            </tr>`;
        });
        html += `</tbody></table>
            <div style="margin-top:12px;font-size:13px;color:#666;text-align:right;">
                借方合计：<b style="color:#16a34a;">${Number(data.total_debit || 0).toLocaleString()}</b>
                &nbsp;&nbsp;
                贷方合计：<b style="color:#dc2626;">${Number(data.total_credit || 0).toLocaleString()}</b>
                &nbsp;&nbsp;
                平衡：<b style="color:${data.is_balanced ? '#16a34a' : '#dc2626'};">${data.is_balanced ? '是' : '否'}</b>
            </div>`;
        body.innerHTML = html;
    }).catch(err => {
        const body = document.getElementById('voucher-detail-body');
        if (body) body.innerHTML = `<div style="padding:40px;color:#f44;">加载失败：${escapeHtml(err.message || String(err))}</div>`;
    });
}

// ==================== 共享期间选择器组件 ====================

/**
 * 生成与"文化事业建设费"一致样式的期间选择器HTML
 * @param {string} prefix - DOM id前缀，如 "si", "pi", "ivd", "bt"
 * @param {string} year   - 默认年份，如 "2025"
 * @param {string} month  - 默认月份，如 "06"
 * @param {string} onQueryFn - 查询按钮调用的全局函数名，如 "onSIPeriodQuery"
 */
function buildPeriodSelectorHtml(prefix, year, month, onQueryFn) {
  var cy = new Date().getFullYear();
  var yearOpts = '';
  for (var y = cy - 5; y <= cy + 3; y++) {
    yearOpts += '<option value="' + y + '" ' + (String(y) === String(year) ? 'selected>' : '>') + y + '年</option>';
  }
  var monthOpts = '';
  for (var m = 1; m <= 12; m++) {
    var mv = String(m).padStart(2, '0');
    monthOpts += '<option value="' + mv + '" ' + (mv === String(month) ? 'selected>' : '>') + mv + '月</option>';
  }
  return '<div class="period-selector-bar">'
    + '<div class="period-stepper">'
    + '<select id="' + prefix + '-year" class="period-selector-year">' + yearOpts + '</select>'
    + '<div class="stepper-arrows">'
    + '<button class="stepper-btn stepper-up" onclick="stepModulePeriod(\'' + prefix + '\',\'year\',1)" title="下一年">▲</button>'
    + '<button class="stepper-btn stepper-down" onclick="stepModulePeriod(\'' + prefix + '\',\'year\',-1)" title="上一年">▼</button>'
    + '</div></div>'
    + '<div class="period-stepper">'
    + '<select id="' + prefix + '-month" class="period-selector-month">' + monthOpts + '</select>'
    + '<div class="stepper-arrows">'
    + '<button class="stepper-btn stepper-up" onclick="stepModulePeriod(\'' + prefix + '\',\'month\',1)" title="下一月">▲</button>'
    + '<button class="stepper-btn stepper-down" onclick="stepModulePeriod(\'' + prefix + '\',\'month\',-1)" title="上一月">▼</button>'
    + '</div></div></div>'
    + '<button class="btn-toolbar" onclick="' + onQueryFn + '()" title="按所选期间查询">查询</button>'
    + '<button class="btn-toolbar" onclick="' + onQueryFn + '(true)" title="清除筛选条件">清除</button>';
}

function stepModulePeriod(prefix, type, delta) {
  var ySel = document.getElementById(prefix + '-year');
  var mSel = document.getElementById(prefix + '-month');
  if (!ySel || !mSel) return;
  var y = parseInt(ySel.value);
  var m = parseInt(mSel.value);
  if (isNaN(y) || isNaN(m)) return;
  if (type === 'year') { y += delta; } else {
    m += delta;
    if (m > 12) { m = 1; y++; }
    if (m < 1)  { m = 12; y--; }
  }
  // 检查年份是否在可选范围内
  var found = false;
  ySel.querySelectorAll('option').forEach(function(o) { if (parseInt(o.value) === y) found = true; });
  if (!found) return;
  ySel.value = String(y);
  mSel.value = String(m).padStart(2, '0');
}

function getModulePeriod(prefix) {
  var y = document.getElementById(prefix + '-year')?.value;
  var m = document.getElementById(prefix + '-month')?.value;
  if (!y || !m) return '';
  return y + '-' + m;
}

// ==================== 启动 ====================
async function init() {
  var user = getCurrentUser();
  if (!user) {
    document.getElementById('user-register-overlay').style.display = 'flex';
    return;
  }
  document.getElementById('user-register-overlay').style.display = 'none';
  return initAppFlow();
}

document.addEventListener('DOMContentLoaded', function () {
  init().catch(function (e) {
    console.error('初始化失败', e);
  });
});

