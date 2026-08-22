// ==================== 全局状态 ====================
var currentPage = 'dashboard';
var currentPeriod = '';
var allAccounts = [];

// ═══ 安全派发：运行时动态取函数，不存在就降级 — 永无人为补存根 ═══
var _LOADING_HTML = '<div style="padding:60px;text-align:center;color:#94a3b8">模块加载中，请稍候...</div>';
function _sR(container, fnName) {
  var fn = window[fnName];
  if (typeof fn === 'function') { fn(container); return true; }
  // 可能来自 defer 脚本尚未加载 → 显示加载提示 + 轮询等待（最多 5 秒）
  container.innerHTML = _LOADING_HTML;
  var retried = 0, maxRetry = 25;
  var timer = setInterval(function() {
    fn = window[fnName];
    if (typeof fn === 'function') {
      clearInterval(timer);
      fn(container);
      return;
    }
    retried++;
    if (retried >= maxRetry) {
      clearInterval(timer);
      container.innerHTML = '<div style="padding:60px;text-align:center;color:#dc2626">模块 ' + fnName + ' 加载超时，请刷新页面重试</div>';
      console.error('[安全派发] 函数 ' + fnName + ' 5秒内未就绪');
    }
  }, 200);
  return false;
}
function _sRX(container, fnName, xarg) {
  var fn = window[fnName];
  if (typeof fn === 'function') { fn(container, xarg); return true; }
  container.innerHTML = _LOADING_HTML;
  console.warn('[安全派发] 函数 ' + fnName + ' 未就绪');
  return false;
}

// 多公司全局状态（供所有模块访问）
var currentCompanyId = 0;  // 0=未选择，必须显式选公司后才有效
var currentCompanyName = '';
var allCompanies = [];
var currentAuthContext = null;

// ══════ 系统配置中心（数据驱动——消除硬编码） ══════
var _systemConfig = null;
var _systemConfigCallbacks = [];

function getSystemConfig(callback) {
  if (_systemConfig) { callback(_systemConfig); return; }
  _systemConfigCallbacks.push(callback);
  if (_systemConfigCallbacks.length === 1) {
    fetch('/api/knowledge/assets/system_config.json?_t=' + Date.now()).then(function(r){return r.json();}).then(function(cfg){
      _systemConfig = cfg;
      var cbs = _systemConfigCallbacks; _systemConfigCallbacks = [];
      cbs.forEach(function(cb){cb(cfg);});
    }).catch(function(){ _systemConfig = {}; });
  }
}

// 全局统一数量获取（消除各个页面/组件的硬编码）
function SYS(key) { return _systemConfig ? (_systemConfig[key] || '...') : '...'; }
// 同步获取（需确保已加载，适用于已在callback中的场景）
window._sys = function(k) { return _systemConfig ? _systemConfig[k] : null; };

// 文件导入全局状态
var _importFile = null;
var _importModule = '';
var _importBankConfigId = null;

// ==================== 全局工具函数 ====================
function getUserPath() {
  try {
    var u = JSON.parse(localStorage.getItem('taxUser') || 'null');
    return (u && u.pinyin) ? '/' + u.pinyin : '';
  } catch(e) { return ''; }
}
function normalizeDisplayValue(value) {
  if (value === undefined || value === null) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') return String(value);
  if (value instanceof Date) return value.toISOString();
  if (Array.isArray(value)) return value.map(normalizeDisplayValue).filter(Boolean).join('、');
  if (typeof value === 'object') {
    try {
      var seen = typeof WeakSet === 'function' ? new WeakSet() : null;
      var json = JSON.stringify(value, function(key, item) {
        if (item && typeof item === 'object' && seen) {
          if (seen.has(item)) return '[循环引用]';
          seen.add(item);
        }
        return item;
      });
      if (!json || json === '{}') return '结构化数据（无可展示字段）';
      return json.length > 2000 ? json.slice(0, 2000) + '…' : json;
    } catch (error) {
      return '结构化数据（请展开详情查看）';
    }
  }
  return String(value);
}

function escapeHtml(s) {
    var text = normalizeDisplayValue(s);
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
var esc = escapeHtml;      // 全局统一转义函数（简写）
var escHtml = escapeHtml;  // 全局统一转义函数（全名，供 tax-pipeline-pages / tax-risk-rules 等模块使用）

var _visibleTextObserver = null;
function _cleanVisibleTextValue(value) {
  var text = String(value == null ? '' : value).replace(/\[object Object\]/g, '结构化数据（请展开详情查看）');
  text = text.replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, '');
  var trimmed = text.trim();
  var looksLikeCss = trimmed.length > 80
    && /(?:^|\s)(?:[.#][a-z_-][\w-]*|:root|@media|@keyframes)\s*[^\n{]*\{[^}]*:[^}]*\}/i.test(trimmed)
    && (trimmed.match(/[{}]/g) || []).length >= 4;
  return looksLikeCss ? '' : text;
}

function sanitizeVisibleTextLayer(root) {
  if (!root || !document.createTreeWalker) return {object_tokens:0, css_nodes:0};
  var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  var nodes = [], objectTokens = 0, cssNodes = 0;
  while (walker.nextNode()) nodes.push(walker.currentNode);
  nodes.forEach(function(node) {
    var parent = node.parentElement;
    if (!parent || parent.closest('style,script,pre,code,textarea,[data-allow-raw-text="true"]')) return;
    var before = node.nodeValue || '';
    var objectCount = (before.match(/\[object Object\]/g) || []).length;
    var after = _cleanVisibleTextValue(before);
    if (objectCount) objectTokens += objectCount;
    if (before.trim() && !after.trim()) cssNodes += 1;
    if (after !== before) node.nodeValue = after;
  });
  return {object_tokens:objectTokens, css_nodes:cssNodes};
}

function _ensureVisibleTextSanitizer(root) {
  var target = document.getElementById('content-area') || root;
  if (!target) return;
  sanitizeVisibleTextLayer(target);
  if (_visibleTextObserver || typeof MutationObserver !== 'function') return;
  _visibleTextObserver = new MutationObserver(function(mutations) {
    mutations.forEach(function(mutation) {
      if (mutation.type === 'characterData') {
        sanitizeVisibleTextLayer(mutation.target.parentElement);
        return;
      }
      Array.prototype.forEach.call(mutation.addedNodes || [], function(node) {
        if (node.nodeType === 3) sanitizeVisibleTextLayer(node.parentElement);
        else if (node.nodeType === 1) sanitizeVisibleTextLayer(node);
      });
    });
  });
  _visibleTextObserver.observe(target, {subtree:true, childList:true, characterData:true});
}

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
  'tax-doc-analysis': '资料风险分析报告',
  'system-logs': '系统日志',
  'ai-interaction': 'AI交互',
  'feedback-template': '审核内容模板',
  'brain': '智能大脑（已迁移至智能分析系统中枢）',
  'engine-hub': '智能分析系统中枢',
  'methodology': '稽查方法论',
  'rs-pipeline': '质量保障管线',
  'report-standards': '报告编制要求',
  'rs-negotiation': '跨域协商标记展示规范',
  'rs-review': '审核反馈在报告中的呈现',
  'rs-ironlaw': '系统铁律与报告质量映射',
  'rs-iterate': '审核反馈→报告迭代闭环',
  'rs-negoflow': '跨域协商详细工作流程',
  'file-parsing': '文件解析',
  'agi-schedule': '调度中枢',
  'analysis-page': '分析链',
  'chains-page': '线索链',
  'evidence-page': '证据链',
  // 以下6个缺标题的页面（2026-07-23 补齐）
  'company-overview': '企业概览',
  'compliance-workbench': '企业持续合规工作台',
  '未记账发票': '未记账发票',
  '文化事业建设费': '文化事业建设费',
  'correction-rules': '纠正规则中心',
  'report-spec': '报告编制要求',
  'auditor-handbook': '稽查员手册',
  // 以下6个新独立路由（2026-07-23 补齐）
  'engine-dashboard': '引擎仪表盘',
  'quality-system': '质量保障体系',
  'ai-rules': 'AI行为准则',
  'tax-agi': '税务AGI仪表盘',
  'tax-risk-rules-list': '税务疑点库',
  'pipeline-analyze': '一键分析结果',
  'analyze-logs': '管线执行日志',
  'domain-panel': '域分析面板',
  'tax-incentives': '税收优惠扫描',
  'compact-clues': '线索链紧凑视图',
  'knowledge-hub': '引擎知识中枢',
};

// ==================== 用户登录 ====================
function getCurrentUser() {
  try {
    if (currentAuthContext && currentAuthContext.username) {
      return {name: currentAuthContext.username, phone: ''};
    }
    // 优先从 localStorage 读取
    var data = JSON.parse(localStorage.getItem('taxUser') || 'null');
    if (data) return data;
    // 从 cookie 读取 user_name
    var cookie = document.cookie.split('; ').find(function(c){ return c.startsWith('user_name='); });
    if (cookie) {
      var name = decodeURIComponent(cookie.split('=')[1]);
      return {name: name, phone: ''};
    }
    return null;
  } catch(e) { return null; }
}

async function loadAuthContext(force) {
  if (!force && currentAuthContext) return currentAuthContext;
  try {
    var response = await fetch('/api/auth/me', {cache: 'no-store'});
    if (!response.ok) return null;
    var data = await response.json();
    if (!data || !data.ok || !data.username) return null;
    currentAuthContext = data;
    localStorage.removeItem('taxUser');
    return data;
  } catch (e) {
    return null;
  }
}

// 全局 fetch 拦截：所有请求自动附加用户信息
(function() {
  var _origFetch = window.fetch;
  window.fetch = function(url, options) {
    options = options || {};
    options.headers = options.headers || {};
    var requestMethod = String(options.method || 'GET').toUpperCase();
    if (!['GET', 'HEAD', 'OPTIONS'].includes(requestMethod)) {
      var csrfCookie = document.cookie.split('; ').find(function(c) {
        return c.startsWith('csrf_token=');
      });
      if (csrfCookie) {
        var csrfToken = decodeURIComponent(csrfCookie.split('=').slice(1).join('='));
        if (options.headers instanceof Headers) {
          options.headers.set('X-CSRF-Token', csrfToken);
        } else {
          options.headers['X-CSRF-Token'] = csrfToken;
        }
      }
    }
    var user = getCurrentUser();
    if (user) {
      // Identity is derived from the server-side session, never client headers.
    }
    return _origFetch(url, options);
  };
})();

function handleUserLogin(e) {
  // 已废弃：登录页分离到 login.html，此函数保留兼容旧代码
  e.preventDefault();
  window.location.href = getUserPath() + '/xuanzezhangtao/';
}

// 分离出应用入口，登录后再调用
async function initAppFlow() {
  const auth = await loadAuthContext();
  const companies = await loadCompaniesRaw();
  window._companiesForPick = companies || [];

  if (!companies || companies.length === 0) {
    // 没有账套 → 创建页（保留新建能力）
    showRegistration();
    return;
  }

  // HttpOnly 账套 Cookie 不暴露给脚本；以服务端会话为准。
  var selectedCompanyId = auth && auth.selected_company_id;
  var lastId = localStorage.getItem('lastCompanyId');
  var target = null;
  if (selectedCompanyId) {
    target = companies.find(function(c) { return String(c.id) === String(selectedCompanyId); });
  }
  if (!target && lastId) {
    target = companies.find(function(c) { return String(c.id) === String(lastId); });
  }
  if (!target) target = companies[0];

  await enterApp(target.id, target.name);
}

async function loadCompaniesRaw() {
  // 优先用服务端预注入的数据，避免依赖 AJAX fetch
  if (window.__PRELOAD_COMPANIES__ && window.__PRELOAD_COMPANIES__.length > 0) {
    return window.__PRELOAD_COMPANIES__;
  }
  try {
    return await fetch('/api/companies').then(r => r.json());
  } catch (e) {
    return [];
  }
}

function showRegistration() {
  // 无账套时自动创建默认账套
  var cname = '默认公司';
  fetch('/api/companies', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name: cname, uscc: ''})
  }).then(function(r) { return r.json(); }).then(function(c) {
    enterApp(c.id, cname);
  }).catch(function() {
    alert('无法创建账套，请检查服务器');
  });
}

function showCompanyPick(companies) {
  sessionStorage.removeItem('onRegistrationPage');
  if (!companies || companies.length === 0) {
    showRegistration();
    return;
  }
  var list = document.getElementById('pick-list');
  if (!list) { console.error('pick-list 元素未找到'); return; }
  // 从 URL 提取拼音前缀
  var py = '';
  var pp = window.location.pathname.split('/').filter(Boolean);
  if (pp[0] && pp[0] !== 'xuanzezhangtao' && pp[0] !== 'xinjianzhangtao') py = pp[0];
  else { try { py = JSON.parse(localStorage.getItem('taxUser')||'{}').pinyin || ''; } catch(e) {} }
  list.innerHTML = companies.map(function(c) {
    var sn = escapeHtml(c.name);
    var si = parseInt(c.id);
    return '<li data-company-id="' + si + '" data-company-name="' + sn + '" style="cursor:pointer;display:flex;align-items:center;gap:12px;padding:12px;border-radius:10px;margin-bottom:8px;background:rgba(255,255,255,0.85);border:1px solid rgba(0,0,0,0.06)">'
      + '<div class="av">' + (c.name?escapeHtml(c.name.charAt(0)):'公') + '</div>'
      + '<div style="flex:1"><div class="cn" style="font-weight:600;color:#1e293b">' + sn + '</div>' + (c.uscc?'<div class="us" style="font-size:12px;color:#94a3b8">'+escapeHtml(c.uscc)+'</div>':'') + '</div>'
      + '<button class="pick-del-btn" data-del-id="' + si + '" data-del-name="' + sn + '" style="opacity:1;background:none;border:none;font-size:16px;cursor:pointer" title="删除此账套">🗑</button>'
      + '</li>';
  }).join('');
  // 事件委托：点击 li 进入系统，点击 .pick-del-btn 删除
  if (list._pickHandler) list.removeEventListener('click', list._pickHandler);
  list._pickHandler = function(e) {
    // 删除按钮
    var delBtn = e.target.closest('.pick-del-btn');
    if (delBtn) {
      e.stopPropagation();
      var dId = parseInt(delBtn.getAttribute('data-del-id'));
      var dName = delBtn.getAttribute('data-del-name');
      if (dId && dName) window.deleteCompanyFromPick(dId, dName);
      return;
    }
    // 点击 li 进入系统（直接调用 enterApp，不跳转）
    var li = e.target.closest('li[data-company-id]');
    if (li) {
      var id = parseInt(li.getAttribute('data-company-id'));
      var name = li.getAttribute('data-company-name');
      if (id && name) {
        enterApp(id, name);
      }
    }
  };
  list.addEventListener('click', list._pickHandler);
  document.getElementById('registration-view').classList.add('hidden');
  document.getElementById('company-pick-view').classList.remove('hidden');
  document.getElementById('app-view').classList.add('hidden');
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
    // 强制走API刷新（不能用预注入旧数据）
    window.__PRELOAD_COMPANIES__ = null;
    const companies = await fetch('/api/companies').then(r => r.json()).catch(() => []);
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
window.deleteCompanyFromPick = deleteCompanyFromPick;

async function enterApp(companyId, companyName) {
window.enterApp = enterApp;  // 确保全局可访问
  sessionStorage.removeItem('onRegistrationPage');
  currentCompanyId = companyId;
  currentCompanyName = companyName;
  localStorage.setItem('lastCompanyId', companyId);
  localStorage.setItem('lastCompanyName', companyName);
  var registrationView = document.getElementById('registration-view');
  var companyPickView = document.getElementById('company-pick-view');
  var appView = document.getElementById('app-view');
  if (registrationView) registrationView.classList.add('hidden');
  if (companyPickView) companyPickView.classList.add('hidden');
  if (appView) appView.classList.remove('hidden');
  // 显示当前用户
  var user = getCurrentUser();
  var userEl = document.getElementById('sidebar-user-name');
  if (userEl && user) userEl.textContent = user.name;
  // 检查API Key状态
  checkApiKeyStatus();
  // 显示当前账套信息
  var coNameEl = document.getElementById('sidebar-company-name');
  var coUsccEl = document.getElementById('sidebar-company-uscc');
  if (coNameEl) coNameEl.textContent = companyName || '';
  // 从公司列表中获取USCC
  var coList = window._companiesForPick || [];
  var co = coList.find(function(c){ return String(c.id) === String(companyId); });
  if (coUsccEl && co) coUsccEl.textContent = co.uscc || '';
  await loadCompanies();
  await loadCurrentPeriod();
  await loadAllAccounts();
  const lastPage = localStorage.getItem('lastPage') || 'dashboard';
  navigateTo(lastPage);
}

// ═══ API Key状态检查 ═══
function checkApiKeyStatus() {
  // 状态已由服务器在HTML中直接注入，无需异步请求
  // 此处保留空函数以防调用报错
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
  let now = new Date();
  let curY = now.getFullYear();
  const fallback = curY + '-' + String(now.getMonth() + 1).padStart(2, '0');
  const saved = localStorage.getItem('currentPeriod');
  currentPeriod = (saved && /^\d{4}-\d{2}$/.test(saved)) ? saved : fallback;
  if (currentPeriod !== saved) localStorage.setItem('currentPeriod', currentPeriod);

  const yearSel = document.getElementById('period-year');
  if (!yearSel) return;
  let ops = '<option value="">年</option>';
  for (let y = curY - 5; y <= curY + 5; y++) ops += `<option value="${y}">${y}年</option>`;
  yearSel.innerHTML = ops;

  const [y, m] = currentPeriod.split('-');
  yearSel.value = y;
  const monthSel = document.getElementById('period-month');
  if (monthSel) monthSel.value = m;
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

function _applySystemStatsWithoutRebuilding(root) {
  if (!root || typeof applySysStats !== 'function' || !window._systemConfig) return;
  var textWalker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  var textNodes = [];
  while (textWalker.nextNode()) textNodes.push(textWalker.currentNode);
  textNodes.forEach(function(node) {
    if (node.nodeValue && node.nodeValue.indexOf('{{') !== -1) {
      node.nodeValue = applySysStats(node.nodeValue, window._systemConfig);
    }
  });
  root.querySelectorAll('*').forEach(function(element) {
    Array.from(element.attributes || []).forEach(function(attribute) {
      if (attribute.value && attribute.value.indexOf('{{') !== -1) {
        element.setAttribute(
          attribute.name,
          applySysStats(attribute.value, window._systemConfig)
        );
      }
    });
  });
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
  _ensureVisibleTextSanitizer(container);

  // ═══ 安全派发：所有页面渲染走 _sR/_sRX，函数未就绪时降级不抛异常 ═══
  switch (page) {
    case 'dashboard':            _sR(container, 'renderDashboard'); break;
    case 'company-overview':    _sR(container, 'renderCompanyOverview'); break;
    case 'compliance-workbench': _sR(container, 'renderComplianceWorkbench'); break;
    case 'journal':                _sR(container, 'renderJournal'); break;
    case 'general-ledger':         _sR(container, 'renderGeneralLedger'); break;
    case 'detail-ledger':          _sR(container, 'renderDetailLedger'); break;
    case 'employee-ledger':        _sR(container, 'renderEmployeeLedger'); break;
    case 'customer-ledger':        _sR(container, 'renderCustomerLedger'); break;
    case 'supplier-ledger':        _sR(container, 'renderSupplierLedger'); break;
    case 'profit-loss':            _sR(container, 'renderProfitLoss'); break;
    case 'balance-sheet':          _sR(container, 'renderBalanceSheet'); break;
    case 'cash-flow':              _sR(container, 'renderCashFlow'); break;
    case 'equity-changes':         _sR(container, 'renderEquityChanges'); break;
    case 'account-balance':        _sR(container, 'renderAccountBalance'); break;
    case 'accounts':               _sR(container, 'renderAccounts'); break;
    case 'periods':                _sR(container, 'renderPeriods'); break;
    case 'company':                window.location.href = '/select-company'; break;
    case 'departments':            _sR(container, 'renderDepartments'); break;
    case 'employees':              _sR(container, 'renderEmployees'); break;
    case 'customers':              _sR(container, 'renderCustomers'); break;
    case 'suppliers':              _sR(container, 'renderSuppliers'); break;
    case 'fixed-assets':           _sR(container, 'renderFixedAssets'); break;
    case 'intangible-assets':      _sR(container, 'renderIntangibleAssets'); break;
    case 'inventory':              _sR(container, 'renderInventory'); break;
    case 'contracts':              _sR(container, 'renderContracts'); break;
    case 'payments':               _sR(container, 'renderPayments'); break;
    case 'sales-invoices':         _sR(container, 'renderSalesInvoices'); break;
    case 'purchase-invoices':      _sR(container, 'renderPurchaseInvoices'); break;
    case 'bookkeeping-invoices':   _sR(container, 'renderBookkeepingInvoices'); break;
    case '未记账发票':              _sR(container, 'renderUnbookkeptInvoices'); break;
    case 'input-vat-deductions':   _sR(container, 'renderInputVATDeductions'); break;
    case 'bank-transactions':      _sR(container, 'renderBankTransactions'); break;
    case 'vat-declaration':        _sR(container, 'renderVATDeclaration'); break;
    case 'salary':                 _sR(container, 'showSalaryPage'); break;
    case 'social-security':        _sR(container, 'renderSocialSecurity'); break;
    case 'housing-fund':           _sR(container, 'renderHousingFund'); break;
    case '文化事业建设费':          _sR(container, 'renderCulturalConstructionFee'); break;
    case 'tax-risk-report':        _sR(container, 'renderTaxRiskReport'); break;
    case 'tax-doc-analysis':       _sR(container, 'renderTaxDocAnalysis'); break;
    case 'system-logs':            _sR(container, 'renderSystemLogs'); break;
    case 'ai-interaction':
    case 'brain':
      // 旧入口已融合至智能引擎中枢单页
      window._engineHubSection = 'agi';
      navigateTo('engine-hub');
      return;
    case 'engine-hub':            _sR(container, 'renderEngineHub'); break;
    case 'chat':                   _sR(container, 'renderChat'); break;
    case 'feedback-template':
      window._reportSection = 'rpt-8';
      navigateTo('report-standards');
      return;
    case 'correction-rules':
      window._engineHubSection = 'corrections';
      navigateTo('engine-hub');
      return;
    case 'methodology':
      if (typeof renderMethodologyPage === 'function') { renderMethodologyPage(container); }
      else { container.innerHTML = _LOADING_HTML; }
      break;
    case 'rs-pipeline':
      window._engineHubSection = 'quality';
      navigateTo('engine-hub');
      return;
    case 'report-spec':
      window._reportSection = 'rpt-7';
      navigateTo('report-standards');
      return;
    case 'report-standards': _sR(container, 'renderReportStandards'); break;
    case 'rs-negotiation':
      window._reportSection = 'rpt-4';
      navigateTo('report-standards');
      return;
    case 'rs-review':
      window._reportSection = 'rpt-8';
      navigateTo('report-standards');
      return;
    case 'rs-ironlaw':
      window._reportSection = 'rpt-10';
      navigateTo('report-standards');
      return;
    case 'rs-iterate':
      window._reportSection = 'rpt-10';
      navigateTo('report-standards');
      return;
    case 'chains-page':
      window._methodologySection = 'chains';
      window._methodologyChainView = 'clues';
      navigateTo('methodology');
      return;
    case 'evidence-page':
      window._methodologySection = 'chains';
      window._methodologyChainView = 'evidence';
      navigateTo('methodology');
      return;
    case 'analysis-page':
      window._methodologySection = 'chains';
      window._methodologyChainView = 'analysis';
      navigateTo('methodology');
      return;
    case 'rs-negoflow':    _sR(container, 'renderCrossDomainNego'); break;
    case 'file-parsing':
      window._methodologySection = 'files';
      navigateTo('methodology');
      return;
    case 'agi-schedule':
      window._engineHubSection = 'agi';
      navigateTo('engine-hub');
      return;
    case 'auditor-handbook':
      window._methodologySection = 'handbook';
      navigateTo('methodology');
      return;
    case 'engine-dashboard':
      window._engineHubSection = 'dashboard';
      navigateTo('engine-hub');
      return;
    case 'quality-system':
      window._engineHubSection = 'quality';
      navigateTo('engine-hub');
      return;
    case 'ai-rules':
      window._engineHubSection = 'rules';
      navigateTo('engine-hub');
      return;
    case 'tax-agi':
      window._engineHubSection = 'agi';
      navigateTo('engine-hub');
      return;
    case 'analyze-logs':
      window._engineHubSection = 'logs';
      navigateTo('engine-hub');
      return;
    case 'knowledge-hub':
      window._engineHubSection = 'knowledge';
      navigateTo('engine-hub');
      return;
    case 'tax-risk-rules-list':
      window._methodologySection = 'rules';
      navigateTo('methodology');
      return;
    case 'pipeline-analyze':
      window._methodologySection = 'results';
      navigateTo('methodology');
      return;
    case 'domain-panel':
      window._methodologySection = 'domains';
      navigateTo('methodology');
      return;
    case 'compact-clues':
      window._methodologySection = 'chains';
      window._methodologyChainView = 'compact';
      navigateTo('methodology');
      return;
    case 'tax-incentives':
      navigateTo('taxpayer-rights');
      return;
    case 'taxpayer-rights':     _sR(container, 'renderTaxpayerRightsHub'); break;
  }
  var ca = document.getElementById('content-area');
  if (ca) ca.scrollTop = 0;
  // 标准模块头部注入（已设跳过标记则不注入）
  if (typeof injectModuleHeader === 'function' && !window._skipModuleHeader) {
    injectModuleHeader(page);
    // 异步页面二次尝试
    setTimeout(function(){ injectModuleHeader(page); }, 500);
  }
  // 全局模板替换不能重建页面，否则异步加载函数会继续写入已脱离 DOM 的旧节点。
  var pageDiv = document.getElementById('page-' + page);
  _applySystemStatsWithoutRebuilding(pageDiv);
  setTimeout(function() {
    _applySystemStatsWithoutRebuilding(pageDiv);
  }, 750);
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
    var agi = d2.ok ? d2 : {knowledge_base:{},healing:{},causal_network:{},cross_analysis:{},version:{agent:'3.0',features:[]},methodology:{},rule_discovery:{},patrol:{},legal_reasoning:{},trend_analysis:{},overrides:{},external_verify:{},corrections:{}};
    var kb = agi.knowledge_base || {};
    var cm = pipe.cross_memory || {};
    var stats = pipe.stats || {};
    var meth = agi.methodology || {};
    var rules = agi.rule_discovery || {};
    var patrol = agi.patrol || {};
    var agiVersion = (agi.version && agi.version.agent) || '3.0';
    var correctionTotal = Number((agi.corrections || {}).total || (agi.corrections || {}).total_rules || 0);

    var h = '';
    h += '<style>.agi-layout{display:flex;gap:28px;max-width:1100px;margin:0 auto;padding:24px 16px;background:#fff}.agi-toc{width:180px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:12px;line-height:2.0;max-height:calc(100vh-40px);overflow-y:auto}.agi-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.agi-toc a{display:block;color:#475569;text-decoration:none;padding:3px 10px;border-radius:4px;cursor:pointer;font-size:12px}.agi-toc a:hover,.agi-toc a.active{background:#eff6ff;color:#2563eb;font-weight:600}.agi-main{flex:1;min-width:0;background:#fff}.agi-main h2.hb-section-title{font-size:16px!important;font-weight:700!important;color:#0f172a!important;padding-bottom:10px!important;border-bottom:2px solid #e2e8f0!important;margin-bottom:16px!important;background:none!important}.agi-main .hb-section-num{display:inline-flex!important;align-items:center!important;justify-content:center!important;min-width:24px!important;height:24px!important;background:#1e293b!important;color:#fff!important;border-radius:4px!important;font-size:12px!important;font-weight:700!important;margin-right:8px!important}.agi-main section{margin-bottom:36px!important}.agi-hero{background:#fff;border:1px solid #e2e8f0;padding:20px 24px;border-radius:8px;margin-bottom:28px}.agi-hero h2{font-size:20px!important;margin:0 0 4px!important}.agi-hero p{font-size:13px;color:#475569;line-height:2.0;margin:0 0 8px}.agi-hero .hb-status-bar{font-size:12px;color:#64748b;line-height:2.0}.agi-main .hb-section-lead{font-size:13px;color:#64748b;line-height:2.0;margin:0 0 12px}.agi-main .hb-card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px}.agi-main .agi-card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}.agi-main .hb-table{width:100%;border-collapse:collapse;font-size:13px;line-height:2.0}.agi-main .hb-table th{padding:10px 14px;text-align:left;font-weight:600;background:#f8fafc;color:#0f172a;border-bottom:2px solid #e2e8f0}.agi-main .hb-table td{padding:10px 14px;border-bottom:1px solid #f1f5f9}.agi-main .hb-table-striped tr:nth-child(even){background:#fafbfc}.agi-main .hb-status-connected{color:#059669;font-weight:600}</style>';
    h += '<div class="agi-layout">';
    
    // TOC
    h += '<nav class="agi-toc"><div class="toc-title">📖 导航</div>';
    h += '<a href="#agi-hero">总览</a>';
    h += '<a href="#agi-core">一 核心分析引擎</a>';
    h += '<a href="#agi-causal">二 因果推理层</a>';
    h += '<a href="#agi-connect">三 连接通信层</a>';
    h += '<a href="#agi-knowledge">四 知识层</a>';
    h += '<a href="#agi-special">五 专项分析层</a>';
    h += '<a href="#agi-perf">六 加速与保护层</a>';
    h += '<a href="#agi-schedule">七 调度中枢</a>';
    h += '<a href="#agi-assets">八 数据资产</a>';
    h += '<a href="#agi-api">九 API端点</a>';
    h += '<a href="#agi-knowledge-config">十 知识库与配置</a>';
    h += '</nav>';
    
    h += '<div class="agi-main">';
    
    // ═══ Hero ═══
    h += '<div id="agi-hero" class="agi-hero">';
    h += '<h2 style="font-size:20px;font-weight:800;color:#0f172a">🧬 税务AGI v' + agiVersion + '</h2>';
    h += '<p style="font-size:13px;color:#94a3b8;margin:0 0 16px">存勤法税·智能大脑 — 多域协同分析 · 方法论驱动 · 证据链闭环 · 红队证伪 · ' + pipe.total_events + ' 条学习事件</p>';
    h += '<div class="hb-status-bar hb-status-connected" style="margin-top:8px">🔗 已连接 · 活跃 ' + pipe.modules_active + ' 个模块 · 因果边 ' + ((agi.causal_network||{}).edges||0) + ' 条 · 知识经验 ' + (kb.lessons_count||0) + ' 条 · 纠正规则 ' + correctionTotal + ' 条</div>';
    h += '</div>';

    // ═══ 一、核心分析引擎 ═══
    h += '<section id="agi-core">';
    h += '<h2 class="hb-section-title"><span class="hb-section-num">一</span> 核心分析引擎</h2>';
    h += '<div class="agi-card-grid">';
    h += _agiEngineCard('🪞','自我反思器','SelfReflector','<code>agent_core.py</code>','14维反向假设验证——对每条高风险发现生成竞争假设并逐条证据验证：隐匿收入←个人大额转账且无对应开票、虚开发票←长期合作供应商突然新增大量交易、品名不匹配←外发加工模式。调整规则：adj<-0.05→不确定（证据不足但存疑）、adj<-0.15→推翻（足够反证据）、累积信号≥3且无推翻→确认（升级为因果边输入SCM）。每次分析后更新记录用于下次先验校准。','红');
    h += _agiEngineCard('💡','洞见总结器','InsightSynthesizer','<code>agent_core.py</code>','从all_findings自动组织为五段式结构化报告：①企业画像——行业+模式+规模+关键财务指标 ②风险全景——四级分布（极高/高/中/低各数量+占比+典型发现类型）③核心问题——TOP5高风险发现的详细因果推演 ④行业对标——66行业基准库五维指标偏离度 ⑤行动建议——P0/P1/P2三级分级建议+具体执行路径。每段从report对象动态提取，不使用预置模板文本。','蓝');
    h += _agiEngineCard('🧠','跨分析学习器','CrossAnalysisLearner','<code>agent_core.py</code>','跨企业分析经验积累——不是每次从零开始。功能：①行业通用模式——同类企业分析≥3次后提取该行业常见高风险模式 ②典型数据画像——记录每个行业的合理收入/毛利率/费用率/人均产值基准 ③经验自动复用——分析新企业时先检索同行业已分析企业作为参考基线 ④持久化到cross_analysis_memory.json，12维度加权相似度检索。','绿');
    h += _agiEngineCard('📐','税务合规方法论','MethodologyEngine','<code>methodology_loader.py</code>','把检查方法、必查资料和法律依据结构化加载。引擎按分析域的domain_key匹配适用方法——收款分析域加载资金与收入核验方法，进销存域加载购销、库存和成本核验方法；根据实际数据特征动态组合，不使用写死的检查清单。','紫');
    h += _agiEngineCard('🔍','规则发现','RuleDiscovery','<code>rule_discovery.py</code>','三层递进归纳引擎——Layer A：模块效率分析只提出调度建议；Layer B：同账套同场景的纠正达到重复验证门槛后进入人工批准，批准规则按精确范围增加审核标记；Layer C：信号模式只形成待验证行业假设，不直接改变当前结论。全部变更保留版本和回退记录。','橙');
    h += _agiEngineCard('🔄','自动巡逻','PatrolEngine','<code>auto_patrol.py</code>','定期重分析已分析企业→对比前后两次报告的差异：①新增风险——上次无本次有 ②消失风险——上次有本次无（AGI修正消解的假阳性）③风险等级迁移——升级或降级 ④变化率>30%→标记显著→触发因果影响定向巡逻→分析引擎改动导致的变化方向→正确保留、错误回滚。快照存入patrol_snapshots做基线对比。','青');
    h += '</div></section>';

    // ═══ 二、因果推理层（4个） ═══
    h += '<section id="agi-causal" class="hb-section">';
    h += '<h2 class="hb-section-title"><span class="hb-section-num">二</span> 因果推理层</h2>';
    h += '<div class="agi-card-grid">';
    h += _agiEngineCard('🎯','SCM因果推理','SCMReasoner','<code>scm_reasoner.py</code>','从条件概率升级为结构化因果推理——不是「X和Y相关」而是检验「X是否导致Y」。四种推理：①do-干预——假设消除信号X，计算对下游结论的影响 ②反事实——补齐合同、申报表或台账后，风险是否降级 ③混淆因子——检测信号X和Y是否由共同因素Z驱动 ④因果链查询——沿上下游因果边构建完整推演。','红');
    h += _agiEngineCard('🧠','元认知引擎','Metacognition','<code>metacognition.py</code>','四维推理质量评估（因果链完整性/证据充分性/法律依据/可操作性）→质量分→不确定性检测→信息缺口识别→行动建议。站在更高层看"反思器做得对不对"。','蓝');
    h += _agiEngineCard('📖','法律三段论','LegalReasoner','<code>legal_reasoner.py</code>','以现行有效的法律依据作为大前提，以本案已核实事实作为小前提，再形成专业判断。条款名称、条号、适用期间和效力状态必须核验；无法确认时标记“法律依据待复核”，不得生成确定性定性。','紫');
    h += _agiEngineCard('🕸️','因果网络','CausalNetwork','<code>causal_network.py</code>','条件概率矩阵+多信号联合预测+自主推理器(AutonomousReasoner)。信号共现→因果边→置信度=P(结论|信号)×log(lift+1)。','绿');
    h += '</div></section>';

    // ═══ 三、连接通信层（3个） ═══
    h += '<section id="agi-connect" class="hb-section">';
    h += '<h2 class="hb-section-title"><span class="hb-section-num">三</span> 连接通信层</h2>';
    h += '<div class="agi-card-grid">';
    h += _agiEngineCard('🔄','事件总线','EventBus','<code>event_bus.py</code>','模块间实时通信中枢——pub/sub松耦合协作。14种标准事件覆盖全分析生命周期。事件路由：因果网络发现新边→发布causal_edge_found→假设生成器订阅并更新规则→巡逻引擎订阅并标记重查。跨模块因果链追踪：一条发现从触发引擎→经过哪些引擎→最终哪个引擎输出→全程通过事件ID回溯。','青');
    h += _agiEngineCard('🕸️','知识图谱','KnowledgeGraph','<code>knowledge_graph.py</code>','实体-关系-属性图推理——将税务合规实体建模为知识图谱。节点类型：企业/供应商/客户/人员/发票/法条/风险。多跳查询示例：企业A→供应商B→关联人员C（B的法人=C）→其他企业D（C也是D的法人）→A/B/D是否闭环交易？购销闭环检测：A→B→C→A品名金额相同→疑似闭环虚开。图谱持久化到knowledge_graph.json。','紫');
    h += _agiEngineCard('🔧','自愈引擎','SelfHealing','<code>self_healing.py</code>','双重自愈模式——人工反馈形成候选修正规则；自动检测识别矛盾结论、金额/偏差/基准缺失、模板空话、空占位符以及信号来源单一或因果链过短。修正结果必须重新经过证据和质量门禁，验证后才能应用。','橙');
    h += '</div></section>';

    // ═══ 四、知识层（3个） ═══
    h += '<section id="agi-knowledge" class="hb-section">';
    h += '<h2 class="hb-section-title"><span class="hb-section-num">四</span> 知识层</h2>';
    h += '<div class="hb-card-grid">';
    h += _agiInfoCard('📚','统一知识库','<code>knowledge_base.py</code> · 9域','政策/因果边/信号模式/语义词典/风险同义词/行业画像/自愈规则/经验教训/分析历史。线程安全写锁，全局单例，JSON持久化。','purple');
    h += _agiInfoCard('🎓','自学习引擎','<code>self_learning.py</code>','三层渐进学习：审核反馈先形成限定账套和场景的候选规则→重复验证与人工同步批准→已批准规则按精确范围增加审核标记。历史数据只用于提出校准建议，不能替代当前证据和合规门禁。','blue');
    h += _agiInfoCard('📈','趋势分析器','<code>trend_analyzer.py</code>','12项经营指标跨期追踪——对比本次vs上次或本次vs行业平均。追踪：毛利率/销售收入/采购金额/供应商数量/客户数量/发票数量/银行流入流出/工资/员工/税负率/净利率。连续两期间变化>10%→标记趋势方向。毛利率下降→成本上升或售价下降，收入增长→市场份额扩大，采购金额与收入对比→购销比合理性。','green');
    h += '</div></section>';

    // ═══ 五、专项分析层（7个） ═══
    h += '<section id="agi-special" class="hb-section">';
    h += '<h2 class="hb-section-title"><span class="hb-section-num">五</span> 专项分析层</h2>';
    h += '<div class="agi-card-grid">';
    h += _agiEngineCard('🏷️','语义推理器','SemanticReasoner','<code>semantic_reasoner.py</code>','手工维护14类品名同义词库——如「棉纱/棉线/纱线」→同一语义组。两层匹配：①子字符串匹配→最长匹配原则归类 ②编辑距离→短品名≤4字无法子串归类→Levenshtein距离≤2→同一组。创造性假设引擎：无归类品名→Jaccard相似度→找最近已知模式→类比推理生成试探假设→标记「语义存疑待确认」。','蓝');
    h += _agiEngineCard('🔍','未知模式检测','UnknownPatternDetector','<code>unknown_pattern_detector.py</code>','规则覆盖度检查+异常检测器(7种：结构化转账/幽灵供应商/价格异常/数量尖峰/月末突击/个人大额转账/营收平滑)→标记未知模式→路由"智哥"人工分析。','橙');
    h += _agiEngineCard('⚡','假设验证引擎','HypothesisEngine','<code>hypothesis_engine.py</code>','每条重要发现至少生成两个互斥的竞争性假设，逐条检查支持证据和反向证据，再更新置信度。系统可推荐证据更强的解释，但必须保留其他假设、限制条件和人工判断入口；验证结果进入历史记录，用于后续先验校准。','红');
    h += _agiEngineCard('🌐','跨企业关系网','CrossEnterpriseGraph','<code>cross_enterprise_graph.py</code>','跨企业关系图谱——检测全系统企业的供应商/客户/人员交叉关联。一人多角检测：同一自然人在企业A是法人/B是股东/C是财务负责人→A↔B↔C交易是否构成关联交易。连锁税务合规点：A→B→C→A品名金额相同→疑似闭环虚开。图持久化到cross_enterprise_graph.json→O(N²)交叉扫描通过图索引优化。','绿');
    h += _agiEngineCard('💰','税收优惠分析','TaxIncentiveAnalyzer','<code>tax_incentive_analyzer.py</code>','9类优惠(小微/小规模/研发/高新/六税两费/软件即征即退/残保金/农林/西部大开发)。联网核查三步法：搜索URL→抓取页面→提取结构化条件。90天缓存。','紫');
    h += _agiEngineCard('🤝','跨域协商引擎','CrossDomainNegotiation','<code>cross_domain_negotiation.py</code>','把不同分析域的结论统一送入协商层，按四类动作处理：消解不适用发现、降低证据不足的风险等级、标记资料限制、联合增强相互印证的跨域信号。所有调整都保留原结论、触发条件和协商理由。','蓝');
    h += _agiEngineCard('🔐','数据一致性引擎','ConsistencyEngine','<code>audit_consistency.py + shared_content_sync.py</code>','双维度自检：数字维度(硬编码vs权威源自动修复)+文本维度(29项跨模块共享内容逐字哈希+概念关联验证)。四触发全覆盖：start.bat/git pre-commit/一键分析/手动--sync。','绿');
    h += '</div></section>';

    // ═══ 六、加速与保护层（3个） ═══
    h += '<section id="agi-perf" class="hb-section">';
    h += '<h2 class="hb-section-title"><span class="hb-section-num">六</span> 加速与保护层</h2>';
    h += '<div class="agi-card-grid">';
    h += _agiEngineCard('⚡','并行加速','ParallelRunner','<code>parallel_runner.py</code>','多模块并行执行——基于模块间依赖DAG自动计算并行执行计划。有依赖→串行，无依赖→并行（39个域分析函数间互不依赖→全部并行）。max_workers默认4，可配置调整。串行/并行可开关切换——调试用串行追踪错误，生产用并行加速。性能：36域串行约45秒→并行约25-30秒→提升35-45%。','青');
    h += _agiEngineCard('🛡️','覆盖层引擎','OverrideEngine','<code>override_engine.py</code>','AGI自主修正安全回滚机制——防止自学习过度修正。四阶段状态机：①待审核→覆盖建议等待确认 ②激活→人工确认后生效 ③生效中→监控效果→假阴性触发回滚 ④紧急恢复→一键回滚所有激活覆盖→清零AGI修正。完整审计日志记录每次激活/回滚，持久化到overrides_storage.json。','红');
    h += _agiEngineCard('🔒','外部验证','ExternalVerifier','<code>external_verifier.py</code>','4通道工商数据验证——任一通道成功即更新企业信息。①天眼查API（需配置Key）②企查查API（备用）③国家企业信用信息公示系统（免费）④搜索引擎后备（仅供参考标注「待核实」）。结果写入entity_profile.json→24小时缓存有效期。','蓝');
    h += '</div></section>';

    // ═══ 七、调度中枢（2个） ═══
    h += '<section id="agi-schedule" class="hb-section">';
    h += '<h2 class="hb-section-title"><span class="hb-section-num">七</span> 调度中枢</h2>';
    h += '<div class="agi-card-grid">';
    h += _agiEngineCard('📋','21模块调度','Orchestrator','<code>orchestrator.py</code>','21模块调度中枢——根据数据画像自适应激活判定。模块注册结构含skip_if/priority/requires/max_workers四字段。行业自适应：服务行业→跳过进销存/BOM/毛利率对标等5个制造域；贸易企业→跳过加工费检测；制造企业→全部激活。调度决策日志写入orchestration_log.json。','蓝');
    h += _agiEngineCard('🔗','AGI管线','AGIPipeline','<code>agi_pipeline.py</code>','21模块事件采集+6步进化流程：①事件总线汇总 ②SCM因果推理提取新因果 ③元认知自检评估推理质量 ④知识图谱导入新节点 ⑤知识库自生长写入新经验 ⑥自愈自动检测生成覆盖建议。全部在分析后自动执行，无需人工触发。','紫');
    h += '</div></section>';

    // ═══ 八、系统能力资产 ═══
    h += '<section id="agi-assets" class="hb-section">';
    h += '<h2 class="hb-section-title"><span class="hb-section-num">八</span> 系统能力资产</h2>';
    h += '<p class="hb-section-lead">按运行职责展示分析域、规则、链路、引擎和调度资产。实时数量以本页状态接口为准，不再使用容易失真的手工统计。</p>';
    h += '<div class="hb-card-grid">';
    h += '<div class="hb-info-card hb-info-blue"><strong>📁 分析域</strong><p><strong>多域并行、按资料自适应激活</strong></p><p>覆盖资金、利润、供应商、发票、经营实质、人员、地域和跨域关系等调查方向。</p></div>';
    h += '<div class="hb-info-card hb-info-red"><strong>📋 税务合规规则</strong><p><strong>运行时按分类加载</strong></p><p>覆盖发票、申报、行业专项、个人所得税、资产负债、企业所得税、成本费用、增值税和经营实质等。</p></div>';
    h += '<div class="hb-info-card hb-info-purple"><strong>🔗 调查链路</strong><p><strong>线索链 → 证据链 → 分析链</strong></p><p>每条正式发现必须能够回到触发信号、原始证据、推理步骤、反证检查和适用方法。</p></div>';
    h += '<div class="hb-info-card hb-info-green"><strong>🧠 引擎层</strong><p><strong>核心、推理、通信、知识、专项、保护、调度</strong></p><p>各层通过事件和状态接口协同，避免重复判断和相互覆盖。</p></div>';
    h += '<div class="hb-info-card hb-info-yellow"><strong>📊 调度资产</strong><p><code>orchestrator.py</code> 统一管理模块</p><p>依据资料类型、行业特征、前置依赖和质量状态决定激活、跳过、重试或降级。</p></div>';
    h += '<div class="hb-info-card hb-info-cyan" style="background:#ecfeff;border-color:#a5f3fc;"><strong>📐 可追溯资产</strong><p><strong>规则、方法、接口和日志相互映射</strong></p><p>版本、来源、运行状态和人工纠正共同形成可复核的系统资产。</p></div>';
    h += '</div></section>';

    // ═══ 九、API端点清单 ═══
    h += '<section id="agi-api" class="hb-section">';
    h += '<h2 class="hb-section-title"><span class="hb-section-num">九</span> API端点清单</h2>';
    h += '<table class="hb-table hb-table-striped">';
    h += '<thead><tr><th style="width:80px;">方法</th><th>端点</th><th>功能说明</th></tr></thead><tbody>';
    var apis = [
      ['GET','/api/agi/status','AGI完整状态面板（分析引擎+知识库+因果网络+SCM+元认知+知识图谱+自愈+巡逻）'],
      ['GET','/api/agi/pipeline/dashboard','Pipeline仪表盘数据'],
      ['POST','/api/agi/query','自然语言查询分析结果'],
      ['POST','/api/agi/chat','对话式税务合规'],
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

    // ═══ 十、知识库与核心配置 ═══
    h += '<section id="agi-knowledge-config" class="hb-section">';
    h += '<h2 class="hb-section-title"><span class="hb-section-num">十</span> 知识库与核心配置</h2>';
    h += '<div class="hb-card-grid">';
    h += _agiInfoCard('\u{1F4DC}','政策库','<code>policies</code>',(kb.policies_count||0) + '项结构化政策知识','purple');
    h += _agiInfoCard('\u{1F517}','因果网络','<code>causal_edges</code>','信号\u2192结论因果关系 \u00b7 ' + ((agi.causal_network||{}).edges||0) + '条因果边','red');
    h += _agiInfoCard('\u{1F4CA}','信号模式','<code>signal_patterns</code>','多信号组合模式 \u00b7 ' + ((agi.causal_network||{}).patterns||0) + '个','blue');
    h += _agiInfoCard('\u{1F4D6}','语义词典','<code>semantic_dict</code>',(kb.semantic_categories||0) + '类语义映射','green');
    h += _agiInfoCard('\u{1F3ED}','行业画像','<code>industry_profiles</code>',(kb.industries_tracked||0) + '个已学习行业画像','yellow');
    h += _agiInfoCard('\u{1F527}','自愈规则','<code>healing_rules</code>','错误\u2192规则\u2192修正 \u00b7 ' + ((agi.healing||{}).active_rules||0) + '条活跃','purple');
    h += _agiInfoCard('\u{1F393}','经验教训','<code>lessons</code>','跨分析积累 \u00b7 ' + (kb.lessons_count||0) + '条','green');
    h += _agiInfoCard('\u{1F4DD}','分析历史','<code>analysis_history</code>',(kb.analyses_tracked||0) + '次已记录分析','slate');
    h += _agiInfoCard('\u{1F50D}','巡逻快照','<code>patrol_snapshots</code>','巡逻基线 \u00b7 ' + (patrol.companies_with_snapshots||0) + '家','cyan');
    h += '</div>';
    h += '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:28px 0 12px;padding-bottom:6px;border-bottom:1px solid #e2e8f0">⚙️ 核心配置参数</h3>';
    h += '<div class="hb-card-grid">';
    h += _agiConfigCard('\u2699\uFE0F 自愈引擎','self_healing.py','5种错误模式 \u00b7 同类\u22652\u2192生成规则 \u00b7 auto_apply','自动检测+人工反馈双模式');
    h += _agiConfigCard('\u2699\uFE0F 自动巡逻','auto_patrol.py','最大5家 \u00b7 触发\u22652边 \u00b7 变化>30%显著','v2.0：因果影响定向巡逻');
    h += _agiConfigCard('\u2699\uFE0F 规则发现','rule_discovery.py','模块效率 \u00b7 纠正模式 \u00b7 跨样本信号','验证后进入规则库');
    h += _agiConfigCard('\u2699\uFE0F 反思器','agent_core.py','adj<-0.05不确定 \u00b7 adj<-0.15推翻 \u00b7 7种类型','14维反向假设');
    h += _agiConfigCard('\u2699\uFE0F 元认知','metacognition.py','四维评估 \u00b7 不确定性阈值0.3 \u00b7 6种缺口','监控推理质量');
    h += _agiConfigCard('\u2699\uFE0F SCM因果','scm_reasoner.py','do-干预\u00b7反事实\u00b7混淆检测\u00b7因果链','领域先验+运行验证');
    h += _agiConfigCard('\u2699\uFE0F 知识库','knowledge_base.py','线程安全\u00b7单例\u00b7受控历史\u00b7私有存储','自动提取并持续校验');
    h += _agiConfigCard('\u2699\uFE0F 联网核查','tax_incentive_analyzer.py','三步法\u00b790天缓存','chinatax.gov.cn');
    h += _agiConfigCard('\u2699\uFE0F 并行加速','parallel_runner.py','多模块并行\u00b7DAG\u00b7可开关','提升30-50%');
    h += _agiConfigCard('\u2699\uFE0F 事件总线','event_bus.py','pub/sub\u00b7标准事件\u00b7受控日志','自动持久化');
    h += '</div></section>';

    // ═══ 底部 ═══
    h += '<div class="hb-footer">';
    h += '<p>\u{1F9EC} 税务AGI v3.0 \u00b7 存勤法税智能大脑 \u00b7 分析引擎模块 \u00b7 ' + pipe.total_events + '条学习事件 \u00b7 ' + ((agi.causal_network||{}).edges||0) + '条因果边 \u00b7 ' + ((agi.healing||{}).active_rules||0) + '条自愈规则 \u00b7 每次一键分析自动进化</p>';
    h += '</div>';

    h += '</div></div>'; // agi-main + agi-layout
    container.innerHTML = h;
    // 侧边栏子模块入口
    if (window._agiSection) {
      var asec = window._agiSection;
      window._agiSection = null;
      var as = document.createElement('style');
      as.textContent = '.agi-toc{display:none!important}.agi-layout{display:block!important}.agi-hero,.hb-footer{display:none!important}#agi-core,#agi-causal,#agi-connect,#agi-knowledge,#agi-special,#agi-perf,#agi-schedule,#agi-assets,#agi-api,#agi-knowledge-config{display:none!important}#'+asec+'{display:block!important}';
      container.appendChild(as);
    }
  } catch(e) {
    _renderAgiFallback(container, e.message);
  }
}
function agiSliceToSection(sectionId) {
  var toc = document.querySelector('.agi-toc');
  if (toc) toc.style.display = 'none';
  var layout = document.querySelector('.agi-layout');
  if (layout) layout.style.display = 'block';
  var hero = document.querySelector('.agi-main > .agi-hero');
  if (hero) hero.style.display = 'none';
  var allSecs = document.querySelectorAll('#agi-core,#agi-causal,#agi-connect,#agi-knowledge,#agi-special,#agi-perf,#agi-schedule,#agi-assets,#agi-api,#agi-knowledge-config');
  for (var i = 0; i < allSecs.length; i++) {
    allSecs[i].style.display = allSecs[i].id === sectionId ? 'block' : 'none';
  }
  setTimeout(function() {
    var el = document.getElementById(sectionId);
    if (el) el.scrollIntoView({behavior: 'smooth', block: 'start'});
  }, 200);
}

function _agiEngineCard(icon, name, engName, codeRef, desc, color) {
  var colorMap = {红:'#fee2e2',蓝:'#dbeafe',绿:'#dcfce7',紫:'#f3e8ff',橙:'#ffedd5',青:'#cffafe'};
  var bg = colorMap[color] || '#f1f5f9';
  return '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px 18px;transition:box-shadow 0.15s" onmouseover="this.style.boxShadow=\'0 2px 8px rgba(0,0,0,.06)\'" onmouseout="this.style.boxShadow=\'none\'">'
    + '<div style="display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px;border-radius:6px;background:'+bg+';font-size:16px;margin-bottom:8px">'+icon+'</div>'
    + '<h3 style="font-size:14px;font-weight:700;color:#0f172a;margin:0 0 2px">'+name+' <span style="font-size:11px;font-weight:400;color:#94a3b8">'+engName+'</span></h3>'
    + '<div style="font-size:11px;color:#94a3b8;margin:0 0 6px">'+codeRef+'</div>'
    + '<div style="font-size:12px;color:#475569;line-height:2">'+desc+'</div></div>';
}

function _agiInfoCard(icon, name, code, desc, color) {
  var colors = {purple:'#f3e8ff',red:'#fee2e2',blue:'#dbeafe',green:'#dcfce7',yellow:'#ffedd5',slate:'#f1f5f9',cyan:'#cffafe'};
  var bg = colors[color] || '#f8fafc';
  return '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:14px 16px">'
    + '<strong style="display:block;font-size:13px;color:#0f172a;margin-bottom:4px">'+icon+' '+name+'</strong>'
    + '<div style="font-size:11px;color:#64748b;margin-bottom:6px">'+code+'</div>'
    + '<div style="font-size:12px;color:#475569;line-height:2.0">'+desc+'</div></div>';
}

function _agiConfigCard(name, file, params, note) {
  return '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:14px 16px;margin-bottom:8px">'
    + '<strong style="display:block;font-size:13px;color:#0f172a;margin-bottom:4px">⚙️ '+name+'</strong>'
    + '<span style="font-size:11px;color:#2563eb;background:#eff6ff;padding:2px 8px;border-radius:10px;margin-bottom:6px;display:inline-block">'+file+'</span>'
    + '<div style="font-size:12px;color:#475569;line-height:2.0;margin-top:6px">'+params+'</div>'
    + '<div style="font-size:11px;color:#64748b;margin-top:4px">💡 '+note+'</div></div>';
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
        '<div style="font-size:11px;color:#7f1d1d;margin-top:4px;">具体条款待从官方有效文本核验条文·三段论推理</div></div>' +
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
      _agiCard('🗣️','对话税务合规','—','中文税务问答') +
      _agiCard('🔗','外部验证','—','天眼查/企查查/工商') +
      _agiCard('🔁','闭环自检','—','AGI自主修正覆盖层') +
      _agiCard('⚡','并行加速','—','多域并发分析') +
    '</div>' +
    '<div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:24px;margin-bottom:20px;">' +
      '<h3 style="margin:0 0 16px;font-size:16px;">🎯 10大核心能力</h3>' +
      '<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px;">' +
        ['感知引擎—多源文件解析与标准化','推理引擎—四步税务合规分析法','学习引擎—自愈规则自动生成',
         '表达引擎—结构化报告生成','记忆引擎—跨企业知识积累','语义理解—税法同义匹配',
         '对话税务合规—自然语言交互','外部验证—四通道联网核查','自我纠错—三层安全覆盖',
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
  // 身份只从服务端会话读取，避免使用本地伪造的用户信息。
  await loadAuthContext(true);
  // 预加载系统统计 → 设置 window._systemConfig 供所有页面的 pc() 函数动态引用
  try {
    var r = await fetch('/api/system/stats');
    var stats = await r.json();
    if (stats && stats.ok) {
      window._systemConfig = {
        rules_count: stats.rules_count,
        clue_chains: stats.clue_chains,
        evidence_chains: stats.evidence_chains,
        analysis_chains: stats.analysis_chains || 48,
        domain_functions: stats.domain_functions,
        industries: stats.industries,
        keywords: stats.keywords,
        file_fingerprints: stats.file_fingerprints,
        hard_ban_categories: stats.hard_ban_categories,
        cond_ban_categories: stats.cond_ban_categories,
        total_chains: (stats.clue_chains||0) + (stats.evidence_chains||0) + (stats.analysis_chains||48)
      };
      // 注入模板替换函数到全局，供所有页面使用
      window.applyTemplates = function(html) {
        if (!html || typeof html !== 'string') return html || '';
        var cfg = window._systemConfig || {};
        return html.replace(/\{\{(\w+)\}\}/g, function(m, key) {
          return cfg[key] != null ? cfg[key] : m;
        });
      };
      // 为所有页面提供便捷取值函数（兼容 tax-pipeline-pages.js 的 pc()）
      if (!window.pc) {
        window.pc = function(key, fallback) {
          var cfg = window._systemConfig || {};
          return cfg[key] != null ? cfg[key] : (fallback != null ? fallback : '—');
        };
      }
    }
  } catch(e) {}
  // 页面加载后替换DOM中所有遗留的 {{...}} 模板
  document.addEventListener('DOMContentLoaded', function() {
    if (window.applyTemplates && document.body) {
      var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
      var node;
      while ((node = walker.nextNode())) {
        var txt = node.textContent || '';
        if (txt.indexOf('{{') !== -1) {
          node.textContent = window.applyTemplates(txt);
        }
      }
    }
  });
  // MutationObserver 自动替换动态注入HTML中的 {{...}} 模板
  if (typeof MutationObserver !== 'undefined') {
    var tplObserver = new MutationObserver(function(mutations) {
      mutations.forEach(function(mutation) {
        if (!window.applyTemplates) return;
        mutation.addedNodes.forEach(function(node) {
          if (node.nodeType === Node.TEXT_NODE) {
            var txt = node.textContent || '';
            if (txt.indexOf('{{') !== -1) {
              node.textContent = window.applyTemplates(txt);
            }
          } else if (node.nodeType === Node.ELEMENT_NODE && node.querySelectorAll) {
            var textNodes = node.querySelectorAll('*');
            for (var i = 0; i < textNodes.length; i++) {
              var childNodes = textNodes[i].childNodes;
              for (var j = 0; j < childNodes.length; j++) {
                var cn = childNodes[j];
                if (cn.nodeType === Node.TEXT_NODE) {
                  var t = cn.textContent || '';
                  if (t.indexOf('{{') !== -1) {
                    cn.textContent = window.applyTemplates(t);
                  }
                }
              }
            }
          }
        });
      });
    });
    tplObserver.observe(document.documentElement, { childList: true, subtree: true });
  }
  return initAppFlow();
}

document.addEventListener('DOMContentLoaded', function () {
  _startApp();
});

// 兜底：脚本加载时 DOM 已经完全载入（如 BFCache 恢复、动态注入），直接启动
// 注意：不用 'interactive'——此时 defer 脚本未执行，会导致 _sR 降级
if (document.readyState === 'complete') {
  setTimeout(_startApp, 0);
}

function _startApp() {
  init().catch(function (e) {
    console.error('初始化失败', e);
  });
}

function _bindPickPageButtons() {
  // 退出登录链接（兜底，HTML已有inline onclick，此处不重复绑定）
  // 创建新账套按钮已在HTML中使用 inline onclick，无需此处绑定
}
