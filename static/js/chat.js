// ==================== 存勤法税智能体 v2.0 ====================
// 三栏专业布局: 左侧快捷导航 | 中间主聊区 | 右侧知识参考
let chatSessionId = null;
let chatMessages = [];
let chatLoading = false;
let _chatUnread = 0;

function _chatInit() {
  if (!chatSessionId) {
    chatSessionId = 'sess_' + Date.now();
    chatMessages = [{
      role: 'ai',
      text: '👋 你好！我是**存勤法税智能体**，专注中小企业财税与法律问答。\n\n直接输入问题开始咨询，或点击右侧推荐话题。'
    }];
  }
}

const CHAT_CATEGORIES = [
  {icon:'📋',name:'税务政策',topics:['增值税税率','企业所得税计算','小规模纳税人优惠','印花税税目','个税专项附加扣除']},
  {icon:'📝',name:'账务处理',topics:['采购材料分录','固定资产折旧','收入确认时点','成本费用归集']},
  {icon:'⚖️',name:'法律合规',topics:['虚开发票认定','偷税与漏税区别','税务稽查程序','滞纳金计算']},
  {icon:'⚠️',name:'风险提示',topics:['进项发票合规','四流一致要求','关联交易风险','发票作废红冲规范']},
  {icon:'💰',name:'财务管理',topics:['毛利率分析','费用率控制','存货管理','现金流规划']},
];

async function renderChat(container) {
  _chatInit();
  const el = container || document.getElementById('page-' + currentPage) || document.getElementById('content-area');

  const css = `
    <style>
      .cq-wrap{display:flex;height:calc(100vh - 56px);background:#f4f6f9;overflow:hidden;margin:-20px}
      .cq-left{width:220px;background:#fff;border-right:1px solid #e8ecf1;display:flex;flex-direction:column;flex-shrink:0}
      .cq-left-header{padding:20px 16px 12px;border-bottom:1px solid #f0f2f5;text-align:center}
      .cq-left-header h3{font-size:13px;font-weight:700;color:#1e293b;margin:0}
      .cq-left-header .cq-sub{font-size:10px;color:#94a3b8;margin-top:4px}
      .cq-cat-list{flex:1;overflow-y:auto;padding:8px}
      .cq-cat-group{margin-bottom:4px}
      .cq-cat-title{padding:10px 14px 6px;font-size:10px;font-weight:700;color:#94a3b8;letter-spacing:.05em;text-transform:uppercase}
      .cq-cat-item{padding:7px 14px;font-size:11px;color:#475569;cursor:pointer;border-radius:6px;transition:.12s;margin-bottom:1px;line-height:1.5}
      .cq-cat-item:hover,.cq-cat-item.active{background:#eff6ff;color:#2563eb;font-weight:600}
      .cq-cat-item .cq-ci{font-size:10px;color:#2563eb;font-weight:700;margin-right:6px}

      .cq-main{flex:1;display:flex;flex-direction:column;min-width:0;background:#f8fafc}
      .cq-main-header{padding:14px 20px;background:#fff;border-bottom:2px solid #e8ecf1;display:flex;align-items:center;gap:12px}
      .cq-main-header .cq-avatar{width:36px;height:36px;border-radius:10px;background:linear-gradient(135deg,#2563eb,#7c3aed);display:flex;align-items:center;justify-content:center;color:#fff;font-size:16px;flex-shrink:0}
      .cq-main-header .cq-title{font-size:14px;font-weight:700;color:#1e293b}
      .cq-main-header .cq-status{font-size:10px;color:#16a34a;display:flex;align-items:center;gap:4px}
      .cq-main-header .cq-status-dot{width:6px;height:6px;border-radius:50%;background:#16a34a;animation:cqPulse 2s infinite}
      @keyframes cqPulse{0%,100%{opacity:1}50%{opacity:.4}}

      .cq-body{flex:1;overflow-y:auto;padding:16px 20px;display:flex;flex-direction:column;gap:10px}
      .cq-msg{max-width:72%;padding:10px 15px;border-radius:12px;font-size:12px;line-height:1.75;animation:cqFade .25s ease;word-break:break-word}
      .cq-msg.user{align-self:flex-end;background:linear-gradient(135deg,#2563eb,#3b82f6);color:#fff;border-bottom-right-radius:3px;box-shadow:0 1px 4px rgba(37,99,235,.15)}
      .cq-msg.ai{align-self:flex-start;background:#fff;border:1px solid #e8ecf1;border-bottom-left-radius:3px;box-shadow:0 1px 3px rgba(0,0,0,.04)}
      .cq-msg.ai strong{color:#2563eb;font-weight:600}
      .cq-msg.ai em{color:#64748b}
      .cq-msg.ai p{margin:0 0 6px}
      .cq-msg.ai p:last-child{margin-bottom:0}
      .cq-msg.ai ul,.cq-msg.ai ol{margin:6px 0;padding-left:20px}
      .cq-msg.ai li{margin-bottom:3px}
      .cq-msg.ai code{background:#f1f5f9;padding:1px 5px;border-radius:3px;font-size:11px;color:#334155}
      .cq-msg.ai pre{background:#1e293b;color:#e2e8f0;padding:10px 14px;border-radius:8px;overflow-x:auto;font-size:11px;line-height:1.6;margin:8px 0}
      @keyframes cqFade{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
      .cq-msg-typing{align-self:flex-start;padding:8px 16px;font-size:11px;color:#94a3b8;display:flex;align-items:center;gap:6px}
      .cq-msg-typing .cq-dot{width:5px;height:5px;border-radius:50%;background:#94a3b8;animation:cqBounce .6s infinite alternate}
      .cq-msg-typing .cq-dot:nth-child(2){animation-delay:.2s}
      .cq-msg-typing .cq-dot:nth-child(3){animation-delay:.4s}
      @keyframes cqBounce{to{transform:translateY(-6px);opacity:.4}}

      .cq-input-wrap{display:flex;gap:8px;padding:12px 20px;background:#fff;border-top:1px solid #e8ecf1}
      .cq-input-wrap input{flex:1;padding:10px 16px;border:1px solid #e2e8f0;border-radius:20px;font-size:12px;outline:none;transition:border .15s;background:#f8fafc}
      .cq-input-wrap input:focus{border-color:#2563eb;background:#fff}
      .cq-input-wrap .cq-btn{padding:10px 18px;border:none;border-radius:20px;font-size:12px;font-weight:600;cursor:pointer;transition:.15s;display:flex;align-items:center;gap:4px}
      .cq-input-wrap .cq-btn-send{background:linear-gradient(135deg,#2563eb,#3b82f6);color:#fff}
      .cq-input-wrap .cq-btn-send:hover{opacity:.9;box-shadow:0 2px 8px rgba(37,99,235,.25)}
      .cq-input-wrap .cq-btn-send:disabled{opacity:.4;cursor:not-allowed;box-shadow:none}
      .cq-input-wrap .cq-btn-upload{background:#fff;color:#64748b;border:1px solid #e2e8f0}
      .cq-input-wrap .cq-btn-upload:hover{background:#f8fafc;border-color:#2563eb;color:#2563eb}

      .cq-right{width:260px;background:#fff;border-left:1px solid #e8ecf1;display:flex;flex-direction:column;flex-shrink:0;overflow-y:auto}
      .cq-right-section{padding:16px;border-bottom:1px solid #f0f2f5}
      .cq-right-section h4{font-size:11px;font-weight:700;color:#94a3b8;letter-spacing:.05em;margin:0 0 8px}
      .cq-right-topic{padding:7px 10px;font-size:11px;color:#475569;cursor:pointer;border-radius:6px;margin-bottom:3px;transition:.12s;line-height:1.5}
      .cq-right-topic:hover{background:#eff6ff;color:#2563eb;font-weight:500}
      .cq-right-topic .cq-hot{font-size:9px;background:#fef2f2;color:#dc2626;padding:1px 5px;border-radius:8px;margin-left:6px}
      .cq-right-stat{display:flex;justify-content:space-between;align-items:center;padding:6px 0;font-size:11px;color:#64748b}
      .cq-right-stat .cq-stv{font-weight:700;color:#1e293b}
      .cq-kb-link{padding:6px 10px;font-size:10px;color:#2563eb;cursor:pointer;border-radius:4px;display:block;transition:.12s;text-decoration:none}
      .cq-kb-link:hover{background:#eff6ff;font-weight:600}
    </style>
  `;

  const leftPanel = `
    <div class="cq-left">
      <div class="cq-left-header">
        <h3>📚 知识导航</h3>
        <div class="cq-sub">点击分类展开话题</div>
      </div>
      <div class="cq-cat-list">
        ${CHAT_CATEGORIES.map((c,i) => `
          <div class="cq-cat-group">
            <div class="cq-cat-group-header" onclick="var items=this.nextElementSibling;items.style.display=items.style.display==='none'?'block':'none'" style="cursor:pointer;padding:8px 14px 4px;display:flex;align-items:center;gap:6px;font-size:11px;font-weight:600;color:#1e293b">
              <span>${c.icon}</span> ${c.name}
              <span style="margin-left:auto;font-size:9px;color:#94a3b8">▼</span>
            </div>
            <div class="cq-cat-items" style="display:${i===0?'block':'none'}">
              ${c.topics.map(t => `<div class="cq-cat-item" onclick="_cqSendTopic('${t}')">${t}</div>`).join('')}
            </div>
          </div>
        `).join('')}
      </div>
    </div>
  `;

  const mainPanel = `
    <div class="cq-main">
      <div class="cq-main-header">
        <div class="cq-avatar">🤖</div>
        <div style="flex:1">
          <div class="cq-title">存勤法税智能体</div>
          <div class="cq-status"><span class="cq-status-dot"></span>在线 · AI大模型驱动</div>
        </div>
      </div>
      <div class="cq-body" id="chat-body">
        ${_renderCqMessages()}
      </div>
      <div class="cq-input-wrap">
        <button class="cq-btn cq-btn-upload" onclick="document.getElementById('chat-file-input').click()" title="上传文件分析">📎</button>
        <input type="file" id="chat-file-input" accept=".xlsx,.xls,.csv,.pdf,.txt,.md,.log" style="display:none" onchange="handleFileUpload(this)">
        <input id="chat-input" type="text" placeholder="输入财税问题..." 
               onkeypress="if(event.key==='Enter') sendChat()" autofocus>
        <button class="cq-btn cq-btn-send" onclick="sendChat()" id="chat-send-btn">
          <span>➤</span> 发送
        </button>
      </div>
    </div>
  `;

  const rightPanel = `
    <div class="cq-right" id="cq-right-panel">
      <div class="cq-right-section">
        <h4>🔥 热门话题</h4>
        <div class="cq-right-topic" onclick="_cqSendTopic('增值税税率是多少')">增值税税率 <span class="cq-hot">HOT</span></div>
        <div class="cq-right-topic" onclick="_cqSendTopic('企业所得税怎么计算')">企业所得税计算</div>
        <div class="cq-right-topic" onclick="_cqSendTopic('小规模纳税人优惠政策')">小规模纳税人优惠</div>
        <div class="cq-right-topic" onclick="_cqSendTopic('进项发票抵扣规范')">进项发票抵扣规范</div>
        <div class="cq-right-topic" onclick="_cqSendTopic('税务稽查常见风险点')">税务稽查常见风险点</div>
        <div class="cq-right-topic" onclick="_cqSendTopic('固定资产折旧年限表')">固定资产折旧年限</div>
        <div class="cq-right-topic" onclick="_cqSendTopic('印花税最新税目税率')">印花税最新税目</div>
      </div>
      <div class="cq-right-section">
        <h4>🔗 知识库快捷入口</h4>
        <a class="cq-kb-link" href="javascript:navigateTo('knowledge-hub')">🧠 引擎知识中枢</a>
        <a class="cq-kb-link" href="javascript:navigateTo('methodology')">📖 稽查方法论</a>
        <a class="cq-kb-link" href="javascript:navigateTo('auditor-handbook')">⚖️ 稽查员手册</a>
        <a class="cq-kb-link" href="javascript:navigateTo('tax-risk-rules-list')">📋 疑点库（1720条）</a>
        <a class="cq-kb-link" href="javascript:navigateTo('report-standards')">📐 报告编制总纲</a>
      </div>
      <div class="cq-right-section" style="font-size:10px;color:#94a3b8;text-align:center;padding:12px">
        存勤法税 v2.0 · AI智能体<br>
        <span style="font-size:9px">${new Date().getFullYear()} 广东存勤法税</span>
      </div>
    </div>
  `;

  el.innerHTML = css + `<div class="cq-wrap">${leftPanel}${mainPanel}${rightPanel}</div>`;
}

window._cqSendTopic = function(topic) {
  const input = document.getElementById('chat-input');
  if (!input) return;
  input.value = topic;
  sendChat();
};

function _renderCqMessages() {
  let h = '';
  chatMessages.slice(-50).forEach(m => {
    const cls = 'cq-msg ' + m.role;
    const content = m.role === 'ai' ? _formatCqMarkdown(m.text) : '<span>' + _cqEsc(m.text) + '</span>';
    h += '<div class="' + cls + '">' + content + '</div>';
  });
  if (chatLoading) h += '<div class="cq-msg-typing"><span class="cq-dot"></span><span class="cq-dot"></span><span class="cq-dot"></span> 思考中...</div>';
  return h || '<div style="text-align:center;color:#94a3b8;padding:40px;font-size:12px">输入问题开始咨询</div>';
}

function _formatCqMarkdown(text) {
  let t = _cqEsc(text);
  t = t.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  t = t.replace(/\*(.+?)\*/g, '<em>$1</em>');
  t = t.replace(/`(.+?)`/g, '<code>$1</code>');
  t = t.replace(/^### (.+)$/gm, '<p style="font-weight:700;color:#1e293b;font-size:13px;margin-top:10px">$1</p>');
  t = t.replace(/^## (.+)$/gm, '<p style="font-weight:700;color:#2563eb;font-size:14px;margin-top:12px">$1</p>');
  t = t.replace(/^# (.+)$/gm, '<p style="font-weight:800;color:#2563eb;font-size:15px;margin-top:14px">$1</p>');
  // Lists
  t = t.replace(/^- (.+)$/gm, '<li>$1</li>');
  t = t.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>');
  // Numbered
  t = t.replace(/^\d+\.\s(.+)$/gm, '<li>$1</li>');
  // Line breaks
  t = t.replace(/\n\n/g, '</p><p>');
  t = t.replace(/\n/g, '<br>');
  if (!t.startsWith('<p>')) t = '<p>' + t;
  if (!t.endsWith('</p>') && !t.endsWith('</ul>') && !t.endsWith('</ol>')) t += '</p>';
  return t;
}

function _cqEsc(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function appendMessage(role, text) {
  const body = document.getElementById('chat-body');
  if (!body) return;
  chatMessages.push({role, text});
  // Remove old typing indicator and old messages if too many
  const typing = body.querySelector('.cq-msg-typing');
  if (typing) typing.remove();
  
  const cls = 'cq-msg ' + role;
  const content = role === 'ai' ? _formatCqMarkdown(text) : '<span>' + _cqEsc(text) + '</span>';
  const div = document.createElement('div');
  div.className = cls;
  div.innerHTML = content;
  body.appendChild(div);
  body.scrollTop = body.scrollHeight;
  return div;
}

function showTyping() {
  const body = document.getElementById('chat-body');
  if (!body) return;
  const div = document.createElement('div');
  div.className = 'cq-msg-typing';
  div.innerHTML = '<span class="cq-dot"></span><span class="cq-dot"></span><span class="cq-dot"></span> 思考中...';
  body.appendChild(div);
  body.scrollTop = body.scrollHeight;
}

function hideTyping() {
  const body = document.getElementById('chat-body');
  if (!body) return;
  const t = body.querySelector('.cq-msg-typing');
  if (t) t.remove();
}

async function sendChat() {
  const input = document.getElementById('chat-input');
  const btn = document.getElementById('chat-send-btn');
  if (!input || chatLoading) return;
  const q = input.value.trim();
  if (!q) return;
  input.value = '';
  input.disabled = true;
  if (btn) btn.disabled = true;
  chatLoading = true;

  appendMessage('user', q);
  showTyping();

  try {
    const resp = await fetch('/api/tax-risk-docs/ask', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        question: q,
        company_id: window.currentCompanyId || 1,
        session_id: chatSessionId
      })
    });
    const data = await resp.json();
    hideTyping();
    
    if (data.ok && data.answer) {
      appendMessage('ai', data.answer);
    } else if (data.ok && data.reply) {
      appendMessage('ai', data.reply);
    } else {
      appendMessage('ai', '⚠️ ' + (data.message || '服务暂不可用，请稍后重试'));
    }
  } catch(e) {
    hideTyping();
    appendMessage('ai', '⚠️ 网络异常，请检查服务是否正常运行');
  }
  
  chatLoading = false;
  input.disabled = false;
  if (btn) btn.disabled = false;
  input.focus();
}

async function handleFileUpload(input) {
  const file = input.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append('file', file);
  formData.append('company_id', window.currentCompanyId || 1);
  formData.append('session_id', chatSessionId);
  
  appendMessage('user', '📎 上传文件：' + file.name);
  chatLoading = true;
  showTyping();
  
  try {
    const resp = await fetch('/api/tax-risk-docs/ask', {
      method: 'POST',
      body: formData
    });
    const data = await resp.json();
    hideTyping();
    if (data.ok && (data.answer || data.reply)) {
      appendMessage('ai', data.answer || data.reply);
    } else {
      appendMessage('ai', '⚠️ 文件分析失败：' + (data.message || '未知错误'));
    }
  } catch(e) {
    hideTyping();
    appendMessage('ai', '⚠️ 网络异常，请检查服务是否正常运行');
  }
  chatLoading = false;
  input.value = '';
}
