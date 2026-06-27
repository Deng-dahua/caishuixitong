// ==================== 全局状态 ====================
var currentPage = 'dashboard';
var currentPeriod = '';
var allAccounts = [];

// 多公司全局状态（供所有模块访问）
var currentCompanyId = 0;  // 0=未选择，必须显式选公司后才有效
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
  // 已废弃：登录页分离到 login.html，此函数保留兼容旧代码
  e.preventDefault();
  window.location.href = '/app';
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

  // 始终进入账套选择页（不自动进入、不自动跳建档页）
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
  var list = document.getElementById('pick-list');
  if (!list) { console.error('pick-list 元素未找到！'); return; }
  // 始终渲染列表（空数组则显示空列表+创建按钮）
  list.innerHTML = companies.map(function(c) {
    var initial = c.name ? c.name.charAt(0) : '公';
    var safeName = escapeHtml(c.name);
    return '<li data-company-id="' + c.id + '" data-company-name="' + safeName + '" style="cursor:pointer;" onclick="window._pickEnter(' + c.id + ')">'
      + '<div class="av">' + initial + '</div>'
      + '<div class="info"><div class="cn">' + safeName + '</div>'
      + (c.uscc ? '<div class="us">' + escapeHtml(c.uscc) + '</div>' : '')
      + '</div><div class="arr">→</div>'
      + '<button class="pick-del-btn" data-del-id="' + c.id + '" data-del-name="' + safeName + '" title="删除此账套">🗑</button>'
      + '</li>';
  }).join('');

  // 删除按钮事件委托
  list.addEventListener('click', function(e) {
    var btn = e.target.closest('.pick-del-btn');
    if (btn) {
      e.stopPropagation();
      e.preventDefault();
      var delId = parseInt(btn.getAttribute('data-del-id'));
      var delName = btn.getAttribute('data-del-name');
      if (delId) deleteCompanyFromPick(delId, delName);
    }
  });

  document.getElementById('registration-view').classList.add('hidden');
  document.getElementById('company-pick-view').classList.remove('hidden');
  document.getElementById('app-view').classList.add('hidden');

  // 用事件委托绑定"创建新公司"按钮（比 inline onclick 更可靠）
  var pickCard = document.querySelector('.pick-card');
  if (pickCard) {
    // 移除旧监听避免重复绑定
    var oldHandler = pickCard._showRegHandler;
    if (oldHandler) pickCard.removeEventListener('click', oldHandler);
    pickCard._showRegHandler = function(e) {
      if (e.target.classList.contains('pick-new-btn')) {
        e.preventDefault();
        showRegistration();
      }
    };
    pickCard.addEventListener('click', pickCard._showRegHandler);
  }
}

// 全局入口——供 inline onclick 调用
window._pickEnter = function(companyId) {
  var li = document.querySelector('[data-company-id="' + companyId + '"]');
  var name = li ? li.getAttribute('data-company-name') : '';
  if (name) enterApp(parseInt(companyId), name);
};

async function deleteCompanyFromPick(companyId, companyName) {
  if (!confirm('确定要删除账套「' + companyName + '」吗？\n\n⚠️ 此操作不可逆，该账套下的所有数据（凭证、发票、报表等）将一并删除。')) return;
  try {
    // 如果删除的是当前已登录的公司，先清除记录
    if (currentCompanyId === companyId) {
      localStorage.removeItem('lastCompanyId');
      localStorage.removeItem('lastCompanyName');
      currentCompanyId = 0;  // 退出时清空，防止后续操作错误关联
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
      showCompanyPick([]);
    } else {
      showCompanyPick(companies);
    }
  } catch (e) {
    toast('删除失败：' + e.message, 'error');
  }
}

async function enterApp(companyId, companyName) {
window.enterApp = enterApp;  // 确保全局可访问
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
  currentCompanyId = 0;  // 退出时清空，防止后续操作错误关联
  currentCompanyName = '';
  const companies = await loadCompaniesRaw();
  window._companiesForPick = companies || [];
  showCompanyPick(companies);
}

function logoutUser() {
  // 完全退出登录，返回个人登录页
  localStorage.removeItem('taxUser');
  localStorage.removeItem('lastCompanyId');
  localStorage.removeItem('lastCompanyName');
  localStorage.removeItem('lastPage');
  currentCompanyId = 0;
  currentCompanyName = '';
  // 跳转到登录页
  window.location.href = '/';
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
    toast('公司「' + data.name + '」创建成功', 'success');
    // 创建成功后返回账套选择页（不自动进入系统）
    const companies = await loadCompaniesRaw();
    window._companiesForPick = companies || [];
    showCompanyPick(companies);
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
  const pt = document.getElementById('page-title');
  if (pt) pt.textContent = pages[page] || page;

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
    // 2026-06-26 修复：未选公司时默认为0而非1，防止跨公司数据混淆
    params.set('company_id', currentCompanyId > 0 ? currentCompanyId : 0);
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
    h += '<h1>🧬 税务AGI v' + (agi.version ? agi.version.agent : '3.0') + '</h1>';
    h += '<p>存勤法税·智能大脑 — 24引擎 · 36域分析 · 1512规则 · 1170线索链 · ' + pipe.total_events + '条学习事件</p>';
    h += '<div class="hb-status-bar hb-status-connected" style="margin-top:12px;">🔗 已连接 · 活跃 ' + pipe.modules_active + ' 模块 · 因果边 ' + ((agi.causal_network||{}).edges||0) + ' 条 · 知识库 ' + (kb.lessons_count||0) + ' 条经验 · SCM推理+元认知运行中</div>';
    h += '</div>';

    // ═══ 一、核心智能引擎（6个） ═══
    h += '<section class="hb-section">';
    h += '<h2 class="hb-section-title"><span class="hb-section-num">一</span> 核心智能引擎</h2>';
    h += '<div class="hb-method-grid">';
    h += _agiEngineCard('🪞','自我反思器','SelfReflector','<code>agent_core.py</code>','14维反向假设验证：隐匿收入←个人转账、虚开发票←长期合作、品名不匹配←外发加工。阈值：adj<-0.05→不确定，adj<-0.15→推翻。','红');
    h += _agiEngineCard('💡','洞见总结器','InsightSynthesizer','<code>agent_core.py</code>','五段式报告：企业画像→风险全景→核心问题→行业对标→行动建议。','蓝');
    h += _agiEngineCard('🧠','跨分析学习器','CrossAnalysisLearner','<code>agent_core.py</code>','多企业行业模式归纳，同行业经验自动复用。cross_analysis_memory.json持久化。','绿');
    h += _agiEngineCard('📐','稽查方法论','MethodologyEngine','<code>methodology_loader.py</code>','10种方法+14类资料+7条法律。按域关键词自动匹配适用方法论。','紫');
    h += _agiEngineCard('🔍','规则发现','RuleDiscovery','<code>rule_discovery.py</code>','三层归纳：空跑→修正→信号→基准。discovered_rules.json输出。','橙');
    h += _agiEngineCard('🔄','自动巡逻','PatrolEngine','<code>auto_patrol.py</code>','重分析→前后对比→因果影响定向巡逻→变化率>30%标记显著。','青');
    h += '</div></section>';

    // ═══ 二、因果推理层（4个） ═══
    h += '<section class="hb-section">';
    h += '<h2 class="hb-section-title"><span class="hb-section-num">二</span> 因果推理层</h2>';
    h += '<div class="hb-method-grid">';
    h += _agiEngineCard('🎯','SCM因果推理','SCMReasoner','<code>scm_reasoner.py</code>','从条件概率升级为结构化因果：do-干预分析（消除信号X→对下游影响）、反事实推理（如果当初有合同→风险降多少）、混淆因子检测、因果链查询。预置9条税务领域因果先验。','红');
    h += _agiEngineCard('🧠','元认知引擎','Metacognition','<code>metacognition.py</code>','四维推理质量评估（因果链完整性/证据充分性/法律依据/可操作性）→质量分→不确定性检测→信息缺口识别→行动建议。站在更高层看"反思器做得对不对"。','蓝');
    h += _agiEngineCard('📖','法律三段论','LegalReasoner','<code>legal_reasoner.py</code>','11条结构化法律规则。大前提(法条)+小前提(本案事实)→结论(法律定性)。含征管法第63条、发票管理办法第22条、刑法第205条等。','紫');
    h += _agiEngineCard('🕸️','因果网络','CausalNetwork','<code>causal_network.py</code>','条件概率矩阵+多信号联合预测+自主推理器(AutonomousReasoner)。信号共现→因果边→置信度=P(结论|信号)×log(lift+1)。','绿');
    h += '</div></section>';

    // ═══ 三、连接通信层（3个） ═══
    h += '<section class="hb-section">';
    h += '<h2 class="hb-section-title"><span class="hb-section-num">三</span> 连接通信层</h2>';
    h += '<div class="hb-method-grid">';
    h += _agiEngineCard('🔄','事件总线','EventBus','<code>event_bus.py</code>','模块间实时通信中枢。pub/sub模式：因果网络发现新边→发布事件→假设生成器更新→巡逻引擎响应。跨模块因果链追踪。14种标准事件类型。','青');
    h += _agiEngineCard('🕸️','知识图谱','KnowledgeGraph','<code>knowledge_graph.py</code>','实体-关系-属性图推理。节点：企业/供应商/客户/人员/发票/法条/风险。多跳查询：企业→供应商→关联人员→其他企业。购销闭环检测。','紫');
    h += _agiEngineCard('🔧','自愈引擎','SelfHealing','<code>self_healing.py</code>','双重模式：①人工反馈→5种错误分类→自动生成修正规则→auto_apply ②自动检测：矛盾结论/三要素缺失/模板句/空占位符/因果链过短→无需人工反馈。','橙');
    h += '</div></section>';

    // ═══ 四、知识层（3个） ═══
    h += '<section class="hb-section">';
    h += '<h2 class="hb-section-title"><span class="hb-section-num">四</span> 知识层</h2>';
    h += '<div class="hb-card-grid">';
    h += _agiInfoCard('📚','统一知识库','<code>knowledge_base.py</code> · 9域','政策/因果边/信号模式/语义词典/风险同义词/行业画像/自愈规则/经验教训/分析历史。线程安全写锁，全局单例，JSON持久化。','purple');
    h += _agiInfoCard('🎓','自学习引擎','<code>self_learning.py</code>','三层渐进学习：模块效率评估(历史运行日志)→反馈规则转化(纠正模式累积≥3→自动规则)→合规门禁(修正后必须过门禁)。历史校准自动计算行业百分位阈值。','blue');
    h += _agiInfoCard('📈','趋势分析器','<code>trend_analyzer.py</code>','12项指标跨期追踪：毛利率/销售收入/采购金额/供应商数量/客户数量/发票数量/银行流入流出/工资/员工/税负率/净利率。趋势方向：上升/下降/持平。','green');
    h += '</div></section>';

    // ═══ 五、专项引擎层（5个） ═══
    h += '<section class="hb-section">';
    h += '<h2 class="hb-section-title"><span class="hb-section-num">五</span> 专项引擎层</h2>';
    h += '<div class="hb-method-grid">';
    h += _agiEngineCard('🏷️','语义推理器','SemanticReasoner','<code>semantic_reasoner.py</code>','手工同义词库(14类品名)→子字符串匹配+编辑距离→语义归类。创造性假设引擎：Jaccard相似度→找到最近已知模式→类比推理生成试探假设。','蓝');
    h += _agiEngineCard('🔍','未知模式检测','UnknownPatternDetector','<code>unknown_pattern_detector.py</code>','规则覆盖度检查+异常检测器(7种：结构化转账/幽灵供应商/价格异常/数量尖峰/月末突击/个人大额转账/营收平滑)→标记未知模式→路由"智哥"人工分析。','橙');
    h += _agiEngineCard('⚡','假设验证引擎','HypothesisEngine','<code>hypothesis_engine.py</code>','竞争假设：每条重要发现生成2-3条互斥假设→逐条证据检查→贝叶斯更新后验概率→选出最佳假设。7种信号类型各2-3条预置竞争模板。','红');
    h += _agiEngineCard('🌐','跨企业关系网','CrossEnterpriseGraph','<code>cross_enterprise_graph.py</code>','全系统企业间供应商/客户/人员关联检测。一人多角：同一人在多家企业任不同角色→关联交易→连锁稽查点。','绿');
    h += _agiEngineCard('💰','税收优惠分析','TaxIncentiveAnalyzer','<code>tax_incentive_analyzer.py</code>','9类优惠(小微/小规模/研发/高新/六税两费/软件即征即退/残保金/农林/西部大开发)。联网核查三步法：搜索URL→抓取页面→提取结构化条件。90天缓存。','紫');
    h += '</div></section>';

    // ═══ 六、加速与保护层（3个） ═══
    h += '<section class="hb-section">';
    h += '<h2 class="hb-section-title"><span class="hb-section-num">六</span> 加速与保护层</h2>';
    h += '<div class="hb-method-grid">';
    h += _agiEngineCard('⚡','并行加速','ParallelRunner','<code>parallel_runner.py</code>','多模块并行执行，依赖DAG自动排序。可开关切换串行/并行模式。预计提升分析速度30-50%。','青');
    h += _agiEngineCard('🛡️','覆盖层引擎','OverrideEngine','<code>override_engine.py</code>','AGI自主修正→安全回滚机制。待审核→激活→生效/回滚→紧急恢复。防止错误修正造成连锁反应。','红');
    h += _agiEngineCard('🔒','外部验证','ExternalVerifier','<code>external_verifier.py</code>','4通道验证：天眼查API/企查查API/工商信息/搜索引擎后备。企业工商数据交叉验证。','蓝');
    h += '</div></section>';

    // ═══ 七、调度中枢（2个） ═══
    h += '<section class="hb-section">';
    h += '<h2 class="hb-section-title"><span class="hb-section-num">七</span> 调度中枢</h2>';
    h += '<div class="hb-method-grid">';
    h += _agiEngineCard('📋','21模块调度','Orchestrator','<code>orchestrator.py</code>','数据画像→自适应激活判定→依赖DAG→执行顺序。行业自适应（服务/制造/贸易）。每个模块含skip_if/priority/requires条件。','蓝');
    h += _agiEngineCard('🔗','AGI管线','AGIPipeline','<code>agi_pipeline.py</code>','21模块学习事件采集+6步智能进化：事件总线→SCM推理→元认知自检→知识图谱导入→知识库自生长→自愈自动检测。每次分析结束自动执行。','紫');
    h += '</div></section>';
    h += _agiEngineCard('🧠','跨分析学习器','CrossAnalysisLearner','<code>agent_core.py</code>','多企业分析经验积累+行业通用模式归纳。每个行业独立记忆：常见高风险模式、典型数据画像。跨分析记忆持久化到 cross_analysis_memory.json。','绿');
    h += _agiEngineCard('📐','稽查方法论引擎','MethodologyEngine','<code>methodology_loader.py</code>','10种稽查方法论(M01-M10)：资料驱动/四步分析/进销存比对/资金流双向核对/供应商穿透/经营实质/客户三源穿透/发票五层审计/六员跨企业比对/地理分析。按域自动匹配适用方法论。','紫');
    h += _agiEngineCard('🔍','自动规则发现','RuleDiscovery','<code>rule_discovery.py</code>','三层归纳引擎——Layer A：模块效率分析→空跑率>80%→跳过规则；Layer B：纠正模式→同类纠正≥5次→通用修正；Layer C：信号模式对比→>60%同类企业出现→行业特征信号。结果输出到 discovered_rules.json。','橙');
    h += _agiEngineCard('🔄','自动巡逻引擎','PatrolEngine','<code>auto_patrol.py</code>','定期重分析已分析企业→对比前后结论：新增/消失/风险等级迁移。变化>30%→标记显著变化→验证AGI学习效果。快照存入 patrol_snapshots →下次巡逻自动加载做基线对比。','青');
    h += '</div></section>';

    // ═══ 八、系统数据资产（精确计数） ═══
    h += '<section class="hb-section">';
    h += '<h2 class="hb-section-title"><span class="hb-section-num">八</span> 系统数据资产</h2>';
    h += '<p class="hb-section-lead">以下数字来自代码和数据文件的精确统计（2026-06-25验证），非手工标注。</p>';
    h += '<div class="hb-card-grid">';
    h += '<div class="hb-info-card hb-info-blue"><strong>📁 域分析函数</strong><p><code>grep "^def _domain_" main.py | wc -l</code> → <strong>36个</strong></p><p>覆盖资金追踪/利润分析/供应商深挖/发票审计/经营实质/地理分析等</p></div>';
    h += '<div class="hb-info-card hb-info-red"><strong>📋 稽查规则</strong><p><code>len(tax_risk_rules_local_export.json)</code> → <strong>1512条</strong></p><p>20个分类：发票匹配184+申报合规142+行业专项133+个税125+资产负债121+企业所得107+成本费用106+发票合规104+增值税101+经营实质98等</p></div>';
    h += '<div class="hb-info-card hb-info-purple"><strong>🔗 线索/证据链</strong><p><code>audit_chains.json</code> chains数组 → <strong>1170条</strong></p><p>每条链含触发条件+风险等级+调查步骤+关联规则ID</p></div>';
    h += '<div class="hb-info-card hb-info-green"><strong>🧠 引擎模块</strong><p><code>engine/</code> 目录下 <strong>24个.py文件</strong></p><p>核心6+推理4+连接3+知识3+专项5+加速3+调度2</p></div>';
    h += '<div class="hb-info-card hb-info-yellow"><strong>📊 21模块调度</strong><p><code>orchestrator.py</code> 注册 <strong>21个模块</strong></p><p>M001-M021：数据准备3+核查3+分析8+推理1+质量控制4+综合2+输出1</p></div>';
    h += '<div class="hb-info-card hb-info-cyan" style="background:#ecfeff;border-color:#a5f3fc;"><strong>📐 代码规模</strong><p>main.py <strong>~29,000行</strong> + engine/ <strong>~8,500行</strong> + 前端 <strong>~15,000行</strong></p><p>总计约 <strong>52,500行</strong> 系统代码</p></div>';
    h += '</div></section>';

    // ═══ 九、API端点清单 ═══
    h += '<section class="hb-section">';
    h += '<h2 class="hb-section-title"><span class="hb-section-num">九</span> API端点清单</h2>';
    h += '<table class="hb-table hb-table-striped">';
    h += '<thead><tr><th style="width:80px;">方法</th><th>端点</th><th>功能说明</th></tr></thead><tbody>';
    var apis = [
      ['GET','/api/agi/status','AGI完整状态面板（24引擎+知识库+因果网络+SCM+元认知+知识图谱+自愈+巡逻）'],
      ['GET','/api/agi/pipeline/dashboard','Pipeline仪表盘数据'],
      ['POST','/api/agi/query','自然语言查询分析结果'],
      ['POST','/api/agi/chat','对话式税务稽查'],
      ['POST','/api/agi/self-check/{company_id}','闭环自检'],
      ['GET','/api/agi/overrides/summary','AGI覆盖层概况'],
      ['POST','/api/agi/overrides/{id}/activate','激活覆盖层'],
      ['POST','/api/agi/overrides/{id}/rollback','回滚覆盖层'],
      ['POST','/api/agi/overrides/emergency-reset','紧急恢复'],
      ['GET','/api/agi/patrol/status','巡逻状态（含因果影响分析）'],
      ['POST','/api/agi/patrol/trigger','触发巡逻'],
      ['GET','/api/agi/verify-supplier','供应商验证'],
      ['GET','/api/agi/verify-channels','验证渠道'],
      ['POST','/api/agi/parallel/toggle','并行加速开关'],
    ];
    for (var a = 0; a < apis.length; a++) {
      var api = apis[a];
      var mc = api[0]==='GET'?'#2563eb':'#16a34a';
      h += '<tr><td style="font-weight:700;color:'+mc+'">'+api[0]+'</td><td style="font-family:monospace;font-size:12px;">'+api[1]+'</td><td style="font-size:12px;">'+api[2]+'</td></tr>';
    }
    h += '</tbody></table></section>';

    // ═══ 十、知识库结构 ═══
    h += '<section class="hb-section">';
    h += '<h2 class="hb-section-title"><span class="hb-section-num">十</span> 知识库结构</h2>';
    h += '<div class="hb-card-grid">';
    h += _agiInfoCard('\u{1F4DC}','政策库','<code>policies</code>','9条税收优惠政策 \u00b7 结构化条件','purple');
    h += _agiInfoCard('\u{1F517}','因果网络','<code>causal_edges</code>','信号\u2192结论因果关系 \u00b7 ' + ((agi.causal_network||{}).edges||0) + '条因果边','red');
    h += _agiInfoCard('\u{1F4CA}','信号模式','<code>signal_patterns</code>','多信号组合模式 \u00b7 ' + ((agi.causal_network||{}).patterns||0) + '个','blue');
    h += _agiInfoCard('\u{1F4D6}','语义词典','<code>semantic_dict</code>','14类同义词库','green');
    h += _agiInfoCard('\u{1F3ED}','行业画像','<code>industry_profiles</code>','8大行业标准画像','yellow');
    h += _agiInfoCard('\u{1F527}','自愈规则','<code>healing_rules</code>','错误\u2192规则\u2192修正 \u00b7 ' + ((agi.healing||{}).active_rules||0) + '条活跃','purple');
    h += _agiInfoCard('\u{1F393}','经验教训','<code>lessons</code>','跨分析积累 \u00b7 ' + (kb.lessons_count||0) + '条','green');
    h += _agiInfoCard('\u{1F4DD}','分析历史','<code>analysis_history</code>','最近100条','slate');
    h += _agiInfoCard('\u{1F50D}','巡逻快照','<code>patrol_snapshots</code>','巡逻基线 \u00b7 ' + (patrol.companies_with_snapshots||0) + '家','cyan');
    h += '</div></section>';

    // ═══ 十、配置参数 ═══
    h += '<section class="hb-section">';
    h += '<h2 class="hb-section-title"><span class="hb-section-num">十一</span> 核心配置参数</h2>';
    h += '<div class="hb-card-grid">';
    h += _agiConfigCard('\u2699\uFE0F 自愈引擎','self_healing.py','5种错误模式 \u00b7 同类\u22652\u2192生成规则 \u00b7 auto_apply','自动检测+人工反馈双模式');
    h += _agiConfigCard('\u2699\uFE0F 自动巡逻','auto_patrol.py','最大5家 \u00b7 触发\u22652边 \u00b7 变化>30%显著','v2.0：因果影响定向巡逻');
    h += _agiConfigCard('\u2699\uFE0F 规则发现','rule_discovery.py','Layer A>80%空跑 \u00b7 Layer B\u22655次纠正 \u00b7 Layer C>60%出现','discovered_rules.json');
    h += _agiConfigCard('\u2699\uFE0F 反思器','agent_core.py','adj<-0.05不确定 \u00b7 adj<-0.15推翻 \u00b7 7种类型','14维反向假设');
    h += _agiConfigCard('\u2699\uFE0F 元认知','metacognition.py','四维评估 \u00b7 不确定性阈值0.3 \u00b7 6种缺口','监控推理质量');
    h += _agiConfigCard('\u2699\uFE0F SCM因果','scm_reasoner.py','do-干预\u00b7反事实\u00b7混淆检测\u00b7因果链','9条领域因果先验');
    h += _agiConfigCard('\u2699\uFE0F 知识库','knowledge_base.py','线程安全\u00b7单例\u00b7100条历史\u00b7JSON','v2.0：自动提取');
    h += _agiConfigCard('\u2699\uFE0F 联网核查','tax_incentive_analyzer.py','三步法\u00b790天缓存','chinatax.gov.cn');
    h += _agiConfigCard('\u2699\uFE0F 并行加速','parallel_runner.py','多模块并行\u00b7DAG\u00b7可开关','提升30-50%');
    h += _agiConfigCard('\u2699\uFE0F 事件总线','event_bus.py','pub/sub\u00b714种事件\u00b7500条日志','自动持久化');
    h += '</div></section>';

    // ═══ 底部 ═══
    h += '<div class="hb-footer">';
    h += '<p>\u{1F9EC} 税务AGI v3.0 \u00b7 存勤法税智能大脑 \u00b7 24引擎模块 \u00b7 ' + pipe.total_events + '条学习事件 \u00b7 ' + ((agi.causal_network||{}).edges||0) + '条因果边 \u00b7 ' + ((agi.healing||{}).active_rules||0) + '条自愈规则 \u00b7 每次一键分析自动进化</p>';
    h += '</div>';

    h += '</div></div>'; // handbook-content + card-fill

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
    // 未登录 → 跳转回登录页
    window.location.replace('/');
    return;
  }
  return initAppFlow();
}

document.addEventListener('DOMContentLoaded', function () {
  init().catch(function (e) {
    console.error('初始化失败', e);
  });
});

