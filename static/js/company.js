// ==================== 多公司支持 ====================
// 全局变量 currentCompanyId/currentCompanyName/allCompanies 已在 core.js 声明

// ==================== 启动 ====================

async function loadCompanies() {
  try {
    allCompanies = await fetch('/api/companies').then(r => r.json());
    window._companiesForPick = allCompanies || [];
    const display = document.getElementById('company-name-display');
    if (allCompanies.length > 0) {
      const cur = allCompanies.find(c => c.id === currentCompanyId) || allCompanies[0];
      currentCompanyName = cur.name;
      if (display) display.textContent = currentCompanyName;
    }
  } catch (e) {
    console.error('加载公司列表失败', e);
  }
}

async function switchCompany() {
  // 确保公司列表已加载
  if (!window._companiesForPick || window._companiesForPick.length === 0) {
    try {
      window._companiesForPick = await fetch('/api/companies').then(r => r.json());
    } catch(e) {
      window._companiesForPick = [];
    }
  }
  
  // 显示账套切换下拉菜单
  const selector = document.getElementById('company-selector-popup');
  if (!selector) {
    // 动态创建下拉菜单
    const popup = document.createElement('div');
    popup.id = 'company-selector-popup';
    popup.style.cssText = 'position:absolute;top:100%;left:0;background:#fff;border:1px solid #e2e8f0;border-radius:8px;box-shadow:0 10px 30px rgba(0,0,0,0.12);z-index:9999;min-width:280px;max-height:360px;overflow-y:auto;padding:8px 0';
    document.querySelector('.company-selector').style.position = 'relative';
    document.querySelector('.company-selector').appendChild(popup);
  }
  
  const popup = document.getElementById('company-selector-popup');
  if (popup.style.display === 'block') {
    popup.style.display = 'none';
    return;
  }
  
  // 渲染公司列表
  const companies = window._companiesForPick || allCompanies || [];
  if (companies.length === 0) {
    popup.innerHTML = '<div style="padding:20px;text-align:center;color:#94a3b8">暂无其他账套</div>';
    popup.style.display = 'block';
    return;
  }
  
  popup.innerHTML = companies.map(c => {
    let activeMark = c.id === currentCompanyId ? ' ✅' : '';
    return '<div style="display:flex;align-items:center;padding:10px 16px;cursor:pointer;transition:background 0.15s"'
      + ' onmouseover="this.style.background=\\'#f1f5f9\\'" onmouseout="this.style.background=\\'transparent\\'"'
      + ' onclick="event.stopPropagation();switchToCompany(' + c.id + ',\\'' + c.name.replace(/'/g, "\\'") + '\\')">'
      + '<span style="flex:1;font-size:14px;font-weight:500;color:#1e293b">' + c.name + activeMark + '</span>'
      + '<button style="border:none;background:transparent;font-size:16px;cursor:pointer;padding:4px 8px;border-radius:4px;color:#94a3b8"'
      + ' onmouseover="this.style.background=\\'#fef2f2\\';this.style.color=\\'#ef4444\\'" onmouseout="this.style.background=\\'transparent\\';this.style.color=\\'#94a3b8\\'"'
      + ' onclick="event.stopPropagation();deleteCompanyFromPick(' + c.id + ',\\'' + c.name.replace(/'/g, "\\'") + '\\');document.getElementById(\\'company-selector-popup\\').style.display=\\'none\\'"'
      + ' title="删除此账套">🗑</button>'
      + '</div>';
  }).join('');
  
  popup.style.display = 'block';
  
  // 点击其他地方关闭
  setTimeout(function() {
    document.addEventListener('click', function closePopup(e) {
      if (!popup.contains(e.target) && e.target !== document.querySelector('.company-selector')) {
        popup.style.display = 'none';
        document.removeEventListener('click', closePopup);
      }
    });
  }, 10);
}

function switchToCompany(companyId, companyName) {
  currentCompanyId = companyId;
  currentCompanyName = companyName;
  localStorage.setItem('lastCompanyId', companyId);
  localStorage.setItem('lastCompanyName', companyName);
  document.getElementById('company-name-display').textContent = companyName;
  document.getElementById('company-selector-popup').style.display = 'none';
  loadCurrentPeriod();
  navigateTo('dashboard');
  toast('已切换到「' + companyName + '」', 'success');
}

// ==================== 公司信息 ====================
async function showCompanyManager(container) {
  let el = container || document.getElementById('page-' + currentPage) || document.getElementById('content-area');
  try {
    const c = await fetch('/api/company?company_id=' + currentCompanyId).then(r => r.json());
    if (!c || !c.company_name) { el.innerHTML = '<div class="empty-state">暂无公司信息</div>'; return; }

    let html = '<div class="card card-fill">';
    html += '<div class="page-header">';
    html += '<h1>🏢 公司管理</h1>';
    html += '<p>查看和编辑公司基本信息 · 税务登记信息 · 工商注册信息</p>';
    html += '</div>';
    html += '<div style="display:flex;justify-content:flex-start;margin-bottom:12px">';
    html += '<button class="btn btn-primary" onclick="showCompanyEditForm()">编辑公司信息</button>';
    html += '</div>';

    html += '<div class="detail-grid">';
    html += _detailRow('ID', c.id);
    html += _detailRow('公司全称', c.company_name);
    html += _detailRow('统一社会信用代码', c.uscc || '--');
    html += _detailRow('注册资本', c.registered_capital ? '¥' + c.registered_capital.toLocaleString() : '--');
    html += _detailRow('成立日期', c.established_date || '--');
    html += _detailRow('法定代表人', c.legal_representative || '--');
    html += _detailRow('法定代表人身份证', c.legal_representative_id || '--');
    html += _detailRow('注册地址', c.address || '--');
    html += _detailRow('经营范围', c.business_scope || '--');
    html += _detailRow('公司类型', c.company_type || '--');
    html += '</div>';

    html += '<div class="card-title" style="margin-top:24px">股东信息</div>';
    if (c.shareholders && c.shareholders.length) {
      html += '<div class="table-wrap"><table><thead><tr><th>姓名/公司名称</th><th>身份证号/统一社会信用代码</th><th>持股比例(%)</th><th>认缴出资额</th></tr></thead><tbody>';
      for (const s of c.shareholders) {
        html += '<tr><td>' + esc(s.name) + '</td><td>' + esc(s.id_number || '--') + '</td><td>' + esc(s.ratio || '--') + '</td><td>' + (s.contribution_amount ? '¥' + s.contribution_amount.toLocaleString() : '--') + '</td></tr>';
      }
      html += '</tbody></table></div>';
    } else {
      html += '<div class="empty-state" style="padding:12px">暂无股东信息</div>';
    }

    html += '<div class="card-title" style="margin-top:24px">董事信息</div>';
    if (c.directors && c.directors.length) {
      html += '<div class="table-wrap"><table><thead><tr><th>姓名</th><th>身份证号</th></tr></thead><tbody>';
      for (const d of c.directors) {
        html += '<tr><td>' + esc(d.name) + '</td><td>' + esc(d.id_number || '--') + '</td></tr>';
      }
      html += '</tbody></table></div>';
    } else {
      html += '<div class="empty-state" style="padding:12px">暂无董事信息</div>';
    }

    html += '<div class="card-title" style="margin-top:24px">监事信息</div>';
    if (c.supervisors && c.supervisors.length) {
      html += '<div class="table-wrap"><table><thead><tr><th>姓名</th><th>身份证号</th></tr></thead><tbody>';
      for (const s of c.supervisors) {
        html += '<tr><td>' + s.name + '</td><td>' + (s.id_number || '--') + '</td></tr>';
      }
      html += '</tbody></table></div>';
    } else {
      html += '<div class="empty-state" style="padding:12px">暂无监事信息</div>';
    }

    html += '<div class="card-title" style="margin-top:24px">财务负责人信息</div>';
    if (c.finance_contacts && c.finance_contacts.length) {
      html += '<div class="table-wrap"><table><thead><tr><th>姓名</th><th>身份证号</th></tr></thead><tbody>';
      for (const f of c.finance_contacts) {
        html += '<tr><td>' + esc(f.name) + '</td><td>' + esc(f.id_number || '--') + '</td></tr>';
      }
      html += '</tbody></table></div>';
    } else {
      html += '<div class="empty-state" style="padding:12px">暂无财务负责人信息</div>';
    }
    html += '</div>';  // close card-fill

    el.innerHTML = html;
  } catch (e) {
    toast(e.message, 'error');
  }
}

function _detailRow(label, value) {
  return '<div class="detail-row"><span class="detail-label">' + label + '</span><span class="detail-value">' + value + '</span></div>';
}

// ==================== 公司编辑弹窗 ====================
async function showCompanyEditForm() {
  let c = {};
  try { c = await fetch('/api/company?company_id=' + currentCompanyId).then(r => r.json()); } catch(e) {}

  let html = '<div class="modal-title">编辑公司信息</div>';
  html += '<form id="company-edit-form" class="form-grid">';
  html += '<div class="form-group"><label>公司全称 *</label><input type="text" class="form-control" name="company_name" value="' + (c.company_name || '') + '" required></div>';
  html += '<div class="form-group"><label>统一社会信用代码</label><input type="text" class="form-control" name="uscc" value="' + (c.uscc || '') + '"></div>';
  html += '<div class="form-group"><label>注册资本</label><input type="number" step="0.01" class="form-control" name="registered_capital" value="' + (c.registered_capital || '') + '"></div>';
  html += '<div class="form-group"><label>成立日期</label><input type="date" class="form-control" name="established_date" value="' + (c.established_date || '') + '"></div>';
  html += '<div class="form-group"><label>法定代表人</label><input type="text" class="form-control" name="legal_representative" value="' + (c.legal_representative || '') + '"></div>';
  html += '<div class="form-group"><label>法定代表人身份证</label><input type="text" class="form-control" name="legal_representative_id" value="' + (c.legal_representative_id || '') + '"></div>';
  html += '<div class="form-group"><label>注册地址</label><input type="text" class="form-control" name="address" value="' + (c.address || '') + '"></div>';
    html += '<div class="form-group" style="grid-column:1/-1"><label>经营范围</label><textarea class="form-control" name="business_scope" rows="2">' + (c.business_scope || '') + '</textarea></div>';
    html += '<div class="form-group"><label>公司类型</label><select class="form-control" name="company_type"><option value="">请选择</option><option value="有限责任公司"' + (c.company_type==='有限责任公司'?' selected':'') + '>有限责任公司</option><option value="股份有限公司"' + (c.company_type==='股份有限公司'?' selected':'') + '>股份有限公司</option><option value="个人独资企业"' + (c.company_type==='个人独资企业'?' selected':'') + '>个人独资企业</option><option value="合伙企业"' + (c.company_type==='合伙企业'?' selected':'') + '>合伙企业</option><option value="外商投资企业"' + (c.company_type==='外商投资企业'?' selected':'') + '>外商投资企业</option><option value="其他"' + (c.company_type==='其他'?' selected':'') + '>其他</option></select></div>';
    html += '</form>';

  html += _buildPersonSection('shareholders', '股东信息', c.shareholders || [], ['姓名/公司名称', '身份证号/统一社会信用代码', '持股比例(%)', '认缴出资额']);
  html += _buildPersonSection('directors', '董事信息', c.directors || [], ['姓名', '身份证号']);
  html += _buildPersonSection('supervisors', '监事信息', c.supervisors || [], ['姓名', '身份证号']);
  html += _buildPersonSection('finance_contacts', '财务负责人', c.finance_contacts || [], ['姓名', '身份证号']);

  html += '<div class="modal-footer">' +
    '<button class="btn btn-secondary" onclick="closeModal()">取消</button>' +
    '<button class="btn btn-primary" onclick="saveCompanyDetail()">保存</button>' +
    '</div>';
  showModal(html);
}

function _buildPersonSection(key, title, items, headers) {
  let h = '<div style="margin-top:16px"><strong>' + title + '</strong>';
  h += '<table style="width:100%;margin-top:8px;border-collapse:collapse" id="tbl-' + key + '"><thead><tr>';
  for (const th of headers) { h += '<th style="text-align:left;padding:4px 8px;border-bottom:1px solid #e5e7eb;font-size:13px">' + th + '</th>'; }
  h += '<th style="width:50px"></th></tr></thead><tbody></tbody></table>';
  h += '<button type="button" class="btn btn-sm btn-secondary" style="margin-top:8px" onclick="addPersonRow(\'' + key + '\', ' + JSON.stringify(headers) + ')">＋ 添加</button>';
  h += '</div>';
  setTimeout(function() {
    for (const item of items) { addPersonRow(key, headers, item); }
  }, 10);
  return h;
}

function addPersonRow(key, headers, data) {
  data = data || {};
  const tbody = document.querySelector('#tbl-' + key + ' tbody');
  if (!tbody) return;
  const tr = document.createElement('tr');
  let h = '';
  for (const th of headers) {
    const fk = th === '持股比例(%)' ? 'ratio' : th === '认缴出资额' ? 'contribution_amount' : th === '联系电话' ? 'phone' : (th === '身份证号' || th === '身份证号/统一社会信用代码') ? 'id_number' : 'name';
    h += '<td style="padding:4px 8px"><input class="form-control" value="' + (data[fk] || '') + '" style="font-size:13px"></td>';
  }
  h += '<td><button class="btn btn-sm btn-danger" onclick="this.closest(\'tr\').remove()" style="padding:2px 8px">×</button></td>';
  tr.innerHTML = h;
  tbody.appendChild(tr);
}

function _collectPersonData(key, headers) {
  const tbody = document.querySelector('#tbl-' + key + ' tbody');
  if (!tbody) return [];
  const items = [];
  tbody.querySelectorAll('tr').forEach(function(tr) {
    const item = {};
    const inputs = tr.querySelectorAll('input');
    headers.forEach(function(th, i) {
      const fk = th === '持股比例(%)' ? 'ratio' : th === '认缴出资额' ? 'contribution_amount' : th === '联系电话' ? 'phone' : (th === '身份证号' || th === '身份证号/统一社会信用代码') ? 'id_number' : 'name';
      let val = inputs[i] ? inputs[i].value.trim() : '';
      if (fk === 'ratio' || fk === 'contribution_amount') val = parseFloat(val) || null;
      item[fk] = val || null;
    });
    if (item.name) items.push(item);
  });
  return items;
}

async function saveCompanyDetail() {
  const form = document.getElementById('company-edit-form');
  const body = {};
  new FormData(form).forEach(function(v, k) { if (v) body[k] = v; });
  if (body.registered_capital) body.registered_capital = parseFloat(body.registered_capital);

  body.shareholders = _collectPersonData('shareholders', ['姓名/公司名称', '身份证号/统一社会信用代码', '持股比例(%)', '认缴出资额']);
  body.directors = _collectPersonData('directors', ['姓名', '身份证号']);
  body.supervisors = _collectPersonData('supervisors', ['姓名', '身份证号']);
  body.finance_contacts = _collectPersonData('finance_contacts', ['姓名', '身份证号']);

  try {
    await fetch('/api/company?company_id=' + currentCompanyId, {
      method: 'PUT', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body)
    });
    closeModal();
    toast('保存成功', 'success');
    showCompanyManager();
  } catch(e) { toast(e.message, 'error'); }
}
async function deleteCompany(id) {
  if (!confirm('\u786e\u8ba4\u5220\u9664\u8be5\u516c\u53f8\u8d26\u5957\uff1f\u6b64\u64cd\u4f5c\u4e0d\u53ef\u6062\u590d\uff01')) return;
  try {
    await fetch('/api/companies/' + id, { method: 'DELETE' });
    toast('\u5220\u9664\u6210\u529f', 'success');
    // 如果删除的是当前账套，退出到公司选择页
    if (id === currentCompanyId) {
      localStorage.removeItem('lastCompanyId');
      localStorage.removeItem('lastCompanyName');
      localStorage.removeItem('lastPage');
      currentCompanyId = 1;
      currentCompanyName = '';
      const companies = await loadCompaniesRaw();
      window._companiesForPick = companies || [];
      showCompanyPick(companies);
      return;
    }
    await loadCompanies();
    showCompanyManager();
  } catch (e) {
    toast(e.message, 'error');
  }
}



// ── 标准科目模板导入 ──
var STANDARD_ACCOUNTS_TEMPLATE = {
  '小企业会计准则': [
    {code:'1001',name:'库存现金',category:'资产类'},
    {code:'1002',name:'银行存款',category:'资产类'},
    {code:'1122',name:'应收账款',category:'资产类'},
    {code:'1123',name:'预付账款',category:'资产类'},
    {code:'1221',name:'其他应收款',category:'资产类'},
    {code:'1405',name:'库存商品',category:'资产类'},
    {code:'1403',name:'原材料',category:'资产类'},
    {code:'1601',name:'固定资产',category:'资产类'},
    {code:'1602',name:'累计折旧',category:'资产类'},
    {code:'2001',name:'短期借款',category:'负债类'},
    {code:'2202',name:'应付账款',category:'负债类'},
    {code:'2203',name:'预收账款',category:'负债类'},
    {code:'2211',name:'应付职工薪酬',category:'负债类'},
    {code:'2221',name:'应交税费',category:'负债类'},
    {code:'4001',name:'实收资本',category:'权益类'},
    {code:'4101',name:'盈余公积',category:'权益类'},
    {code:'4104',name:'利润分配',category:'权益类'},
    {code:'5001',name:'主营业务收入',category:'损益类'},
    {code:'5401',name:'主营业务成本',category:'损益类'},
    {code:'5501',name:'销售费用',category:'损益类'},
    {code:'5502',name:'管理费用',category:'损益类'},
    {code:'5503',name:'财务费用',category:'损益类'},
  ]
};

async function importStandardAccounts(companyId) {
  if (!confirm('确认导入小企业会计准则标准科目？将新增约22个科目。')) return;
  
  var template = STANDARD_ACCOUNTS_TEMPLATE['小企业会计准则'];
  var count = 0;
  
  for (var i = 0; i < template.length; i++) {
    try {
      var resp = await fetch('/api/accounts?company_id='+companyId, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          code: template[i].code,
          name: template[i].name,
          category: template[i].category,
          company_id: companyId
        })
      });
      if (resp.ok) count++;
    } catch(e) {}
  }
  
  alert('成功导入'+count+'/'+template.length+'个标准科目');
  location.reload();
}
