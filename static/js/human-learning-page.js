/**
 * 人类学习引擎 — 前端展示页
 * 显示12项认知能力的实时状态
 * API: /api/human-learning/status
 */
function renderHumanLearningPage(container) {
  if (!container) return;
  window.currentModule = '人类学习引擎';

  container.innerHTML =
    '<style>' +
    '.hl-wrap{max-width:1100px;margin:0 auto;padding:24px}' +
    '.hl-title{font-size:22px;font-weight:800;color:#0f172a;margin:0 0 4px}' +
    '.hl-sub{font-size:13px;color:#94a3b8;margin:0 0 24px}' +
    '.hl-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:24px}' +
    '.hl-stat{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:14px 16px;text-align:center}' +
    '.hl-stat-num{font-size:24px;font-weight:700}' +
    '.hl-stat-label{font-size:11px;color:#94a3b8;margin-top:2px}' +
    '.hl-section{margin-bottom:24px}' +
    '.hl-sectitle{font-size:15px;font-weight:700;color:#0f172a;margin:0 0 10px;padding-bottom:8px;border-bottom:2px solid #e2e8f0}' +
    '.hl-card{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:14px 18px;margin-bottom:8px}' +
    '.hl-card:hover{box-shadow:0 2px 8px rgba(0,0,0,.04)}' +
    '.hl-card-h{display:flex;justify-content:space-between;align-items:center}' +
    '.hl-card-title{font-weight:600;font-size:13px;color:#0f172a}' +
    '.hl-card-meta{font-size:11px;color:#94a3b8;margin-top:4px}' +
    '.hl-card-body{font-size:12px;color:#475569;margin-top:6px;line-height:1.7}' +
    '.hl-badge{padding:2px 8px;border-radius:8px;font-size:10px;font-weight:600}' +
    '.hl-badge-green{background:#dcfce7;color:#16a34a}' +
    '.hl-badge-red{background:#fee2e2;color:#dc2626}' +
    '.hl-badge-yellow{background:#fef3c7;color:#d97706}' +
    '.hl-badge-blue{background:#dbeafe;color:#2563eb}' +
    '.hl-badge-purple{background:#ede9fe;color:#7c3aed}' +
    '.hl-loading{text-align:center;padding:80px;color:#94a3b8}' +
    '.hl-empty{text-align:center;padding:60px;color:#94a3b8;font-size:14px}' +
    '.hl-error{text-align:center;padding:40px;color:#dc2626}' +
    '.hl-btn{padding:4px 12px;border:1px solid #e2e8f0;border-radius:4px;font-size:11px;cursor:pointer;background:#fff;color:#475569}' +
    '.hl-btn:hover{background:#f1f5f9}' +
    '@media(max-width:800px){.hl-grid{grid-template-columns:1fr}}' +
    '</style>' +
    '<div class="hl-wrap">' +
    '<h2 class="hl-title">人类学习引擎</h2>' +
    '<p class="hl-sub">引擎模拟人的12项认知能力，从编辑/审核/追问中持续学习进化</p>' +
    '<div id="hl-content" class="hl-loading">加载引擎状态...</div>' +
    '</div>';

  loadHumanLearningState();
}

async function loadHumanLearningState() {
  var el = document.getElementById('hl-content');
  try {
    var resp = await fetch('/api/human-learning/status');
    var data = await resp.json();
    if (!data.ok) {
      el.innerHTML = '<div class="hl-error">加载失败: ' + (data.message || '未知') + '</div>';
      return;
    }
    renderHLState(data.status);
  } catch(e) {
    el.innerHTML = '<div class="hl-error">连接失败: ' + e.message + '</div>';
  }
}

function renderHLState(st) {
  var el = document.getElementById('hl-content');
  if (!el) return;

  // 顶部统计卡片
  var html =
    '<div class="hl-grid">' +
    statBox('记忆记录', st['记忆'] || 0, '#2563eb') +
    statBox('活跃规则', st['活跃规则'] || 0, '#16a34a') +
    statBox('已归档规则', st['已归档规则'] || 0, '#94a3b8') +
    statBox('待验证纠正', st['待验证纠正'] || 0, '#d97706') +
    statBox('待解决问题', st['待回答问题'] || 0, '#dc2626') +
    statBox('规则关联', st['规则关联'] || 0, '#7c3aed') +
    '</div>';

  // 12项能力状态表
  html += '<div class="hl-section"><div class="hl-sectitle">12项认知能力状态</div>';

  var abilities = [
    {id:1, name:'记忆', desc:'记住每次决策的原因和结果', key:'记忆', color:'#2563eb'},
    {id:2, name:'遗忘', desc:'30天降权/180天归档无效规则', key:'已归档规则', color:'#94a3b8'},
    {id:3, name:'举一反三', desc:'规则跨行业自动迁移', key:'活跃规则', color:'#7c3aed'},
    {id:4, name:'质疑自己', desc:'新旧冲突标记不盲目覆盖', key:'待解决冲突', color:'#dc2626'},
    {id:5, name:'抽象归纳', desc:'多条纠正提炼通用规则', key:'已归纳聚类', color:'#7c3aed'},
    {id:6, name:'因果推理', desc:'分析引擎为什么之前错了', key:'根因分析', color:'#2563eb'},
    {id:7, name:'容错机制', desc:'3次确认后才采纳纠正', key:'待验证纠正', color:'#d97706'},
    {id:8, name:'主动提问', desc:'模糊时反问用户确认', key:'待回答问题', color:'#dc2626'},
    {id:9, name:'自我评估', desc:'规则置信度自动评分', key:'活跃规则', color:'#16a34a'},
    {id:10, name:'渐进调整', desc:'每次+-5%逐步调权', key:'活跃规则', color:'#2563eb'},
    {id:11, name:'回测验证', desc:'新规则跑旧数据验证', key:'回测记录', color:'#7c3aed'},
    {id:12, name:'关系发现', desc:'构建规则关联网络', key:'规则关联', color:'#dc2626'},
  ];

  abilities.forEach(function(a){
    var val = st[a.key] || 0;
    var badgeStyle = val > 0 ? 'hl-badge-green' : 'hl-badge-blue';
    if (a.key === '待验证纠正' && val > 0) badgeStyle = 'hl-badge-yellow';
    if (a.key === '待回答问题' && val > 0) badgeStyle = 'hl-badge-red';
    if (a.key === '待解决冲突' && val > 0) badgeStyle = 'hl-badge-red';
    html += '<div class="hl-card">' +
      '<div class="hl-card-h">' +
      '<div class="hl-card-title">' + a.id + '. ' + a.name + '</div>' +
      '<span class="hl-badge ' + badgeStyle + '">' + (val > 0 ? val + '条' : '就绪') + '</span>' +
      '</div>' +
      '<div class="hl-card-body">' + a.desc + '</div>' +
      '</div>';
  });

  html += '</div>';

  // 操作按钮
  html += '<div style="display:flex;gap:8px;margin-top:16px">' +
    '<button class="hl-btn" onclick="callHLAction(\'decay\')">触发遗忘衰减</button>' +
    '<button class="hl-btn" onclick="callHLAction(\'relationships\')">触发关系发现</button>' +
    '<button class="hl-btn" style="background:#eff6ff;color:#2563eb;border-color:#bfdbfe" onclick="loadHumanLearningState()">刷新状态</button>' +
    '</div>';

  el.innerHTML = html;
}

function statBox(label, num, color) {
  return '<div class="hl-stat">' +
    '<div class="hl-stat-num" style="color:' + color + '">' + num + '</div>' +
    '<div class="hl-stat-label">' + label + '</div>' +
    '</div>';
}

async function callHLAction(action) {
  try {
    var resp = await fetch('/api/human-learning/' + action, {method:'POST'});
    var data = await resp.json();
    if (data.ok) {
      loadHumanLearningState();
    } else {
      alert('操作失败: ' + (data.message || ''));
    }
  } catch(e) {
    alert('请求失败: ' + e.message);
  }
}
