// ==================== 存勤法税智能体 v2.0 ====================
// 三栏专业布局: 左侧快捷导航 | 中间主聊区 | 右侧知识参考
let chatSessionId = null;
let chatMessages = [];
let chatLoading = false;
let _chatUnread = 0;

window.openRiskQuestion = function(context) {
  var payload = context && typeof context === 'object' ? context : {question:String(context || '')};
  payload.opened_at = new Date().toISOString();
  try { sessionStorage.setItem('taxRiskQuestionContext', JSON.stringify(payload)); } catch (error) {}
  if (typeof navigateTo === 'function') navigateTo('chat');
};

function _consumeRiskQuestionContext() {
  try {
    var raw = sessionStorage.getItem('taxRiskQuestionContext');
    if (!raw) return null;
    sessionStorage.removeItem('taxRiskQuestionContext');
    var parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch (error) {
    return null;
  }
}

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
  {icon:'⚖️',name:'法律合规',topics:['虚开发票认定','偷税与漏税区别','税务风险检查程序','滞纳金计算']},
  {icon:'⚠️',name:'风险提示',topics:['进项发票合规','四流一致要求','关联交易风险','发票作废红冲规范']},
  {icon:'💰',name:'财务管理',topics:['毛利率分析','费用率控制','存货管理','现金流规划']},
];

async function renderChat(container) {
  _chatInit();
  const el = container || document.getElementById('page-' + currentPage) || document.getElementById('content-area');

  const css = `
    <style>
      .cq-page{
        display:flex;
        flex-direction:column;
        height:calc(100vh - 72px);
        min-height:0;
        box-sizing:border-box;
        padding:16px
      }
      .cq-wrap{
        display:grid;
        grid-template-columns:240px minmax(0,1fr) 280px;
        gap:16px;
        flex:1;
        min-height:0;
        height:auto;
        margin:0;
        padding:0;
        overflow:hidden;
        color:#405166;
        background:#edf1f5;
        font-family:"Microsoft YaHei UI","Microsoft YaHei","PingFang SC",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif
      }
      .cq-left,.cq-main,.cq-right{
        min-height:0;
        border:1px solid #dce4ed;
        border-radius:14px;
        background:#fff;
        box-shadow:0 8px 24px rgba(20,34,52,.055);
        overflow:hidden
      }
      .cq-left{display:flex;flex-direction:column}
      .cq-left-header{padding:24px 20px 19px;border-bottom:1px solid #e6ebf1;background:#f8fafc;text-align:left}
      .cq-left-header h3{margin:0;color:#17273c;font-size:15px;line-height:1.5;font-weight:750}
      .cq-left-header .cq-sub{margin-top:6px;color:#718095;font-size:12px;line-height:1.65}
      .cq-cat-list{flex:1;overflow-y:auto;padding:12px}
      .cq-cat-group{margin-bottom:7px}
      .cq-cat-group-header{display:flex;align-items:center;gap:7px;padding:10px 13px 7px;color:#263a50;font-size:13px;line-height:1.5;font-weight:700;cursor:pointer}
      .cq-cat-title{padding:11px 13px 7px;color:#718095;font-size:11px;font-weight:750;letter-spacing:.06em}
      .cq-cat-item{margin-bottom:3px;padding:9px 13px;border-radius:7px;color:#52647a;font-size:13px;line-height:1.55;cursor:pointer;transition:.16s}
      .cq-cat-item:hover,.cq-cat-item.active{color:#174d7c;background:#eef5fb;font-weight:650}
      .cq-cat-item .cq-ci{margin-right:6px;color:#1f6b9b;font-size:11px;font-weight:750}

      .cq-main{display:flex;flex-direction:column;min-width:0;background:#f7f9fc}
      .cq-main-header{
        padding:20px 24px;
        border-bottom:1px solid rgba(255,255,255,.12);
        color:#fff;
        background:linear-gradient(135deg,#17273c 0%,#27435e 72%,#31536d 100%);
        display:flex;
        align-items:center;
        gap:14px
      }
      .cq-main-header .cq-avatar{width:42px;height:42px;border:1px solid rgba(255,255,255,.24);border-radius:11px;background:rgba(255,255,255,.1);display:flex;align-items:center;justify-content:center;color:#fff;font-size:18px;flex-shrink:0}
      .cq-main-header .cq-title{color:#fff;font-size:17px;line-height:1.45;font-weight:750}
      .cq-main-header .cq-status{margin-top:3px;color:#c9eadc;font-size:11px;line-height:1.5;display:flex;align-items:center;gap:6px}
      .cq-main-header .cq-status-dot{width:7px;height:7px;border-radius:50%;background:#59c79a;box-shadow:0 0 0 4px rgba(89,199,154,.12);animation:cqPulse 2s infinite}
      @keyframes cqPulse{0%,100%{opacity:1}50%{opacity:.4}}

      .cq-body{flex:1;overflow-y:auto;padding:26px 28px;display:flex;flex-direction:column;gap:16px;scroll-behavior:smooth}
      .cq-msg{max-width:82%;padding:14px 18px;border-radius:12px;font-size:14px;line-height:1.85;letter-spacing:.01em;animation:cqFade .25s ease;word-break:break-word}
      .cq-msg.user{align-self:flex-end;color:#fff;background:#245f88;border-bottom-right-radius:4px;box-shadow:0 5px 14px rgba(36,95,136,.16)}
      .cq-msg.ai{align-self:flex-start;color:#405166;background:#fff;border:1px solid #dfe6ee;border-bottom-left-radius:4px;box-shadow:0 4px 14px rgba(20,34,52,.045)}
      .cq-msg.ai strong{color:#173f63;font-weight:700}
      .cq-msg.ai em{color:#657589}
      .cq-msg.ai p{margin:0 0 11px}
      .cq-msg.ai p:last-child{margin-bottom:0}
      .cq-msg.ai ul,.cq-msg.ai ol{margin:10px 0;padding-left:22px}
      .cq-msg.ai li{margin-bottom:7px}
      .cq-msg.ai code{padding:2px 6px;border-radius:4px;color:#334155;background:#eef2f6;font-size:12px}
      .cq-msg.ai pre{margin:12px 0;padding:14px 16px;border-radius:8px;color:#e2e8f0;background:#17273c;overflow-x:auto;font-size:12px;line-height:1.7}
      .cq-risk-context{margin:0 0 12px;padding:12px 14px;border:1px solid #bfdbfe;border-left:4px solid #2563eb;border-radius:8px;color:#1e3a5f;background:#eff6ff;font-size:12px;line-height:1.7}
      .cq-risk-context b{color:#1d4ed8}
      @keyframes cqFade{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
      .cq-msg-typing{align-self:flex-start;padding:10px 16px;color:#718095;font-size:12px;display:flex;align-items:center;gap:7px}
      .cq-msg-typing .cq-dot{width:5px;height:5px;border-radius:50%;background:#94a3b8;animation:cqBounce .6s infinite alternate}
      .cq-msg-typing .cq-dot:nth-child(2){animation-delay:.2s}
      .cq-msg-typing .cq-dot:nth-child(3){animation-delay:.4s}
      @keyframes cqBounce{to{transform:translateY(-6px);opacity:.4}}

      .cq-input-wrap{display:flex;gap:10px;padding:16px 20px;background:#fff;border-top:1px solid #dfe6ee}
      .cq-input-wrap input{flex:1;min-width:0;padding:12px 17px;border:1px solid #cfd9e5;border-radius:8px;color:#33465c;background:#f8fafc;font-size:14px;outline:none;transition:.16s}
      .cq-input-wrap input:focus{border-color:#376f98;background:#fff;box-shadow:0 0 0 3px rgba(55,111,152,.1)}
      .cq-input-wrap .cq-btn{padding:11px 18px;border-radius:8px;font-size:13px;font-weight:700;cursor:pointer;transition:.16s;display:flex;align-items:center;justify-content:center;gap:5px}
      .cq-input-wrap .cq-btn-send{border:1px solid #234f70;color:#fff;background:#234f70}
      .cq-input-wrap .cq-btn-send:hover{background:#173f63;box-shadow:0 4px 12px rgba(23,63,99,.16)}
      .cq-input-wrap .cq-btn-send:disabled{opacity:.4;cursor:not-allowed;box-shadow:none}
      .cq-input-wrap .cq-btn-upload{border:1px solid #cfd9e5;color:#52647a;background:#fff}
      .cq-input-wrap .cq-btn-upload:hover{border-color:#376f98;color:#245f88;background:#f5f9fc}

      .cq-right{display:flex;flex-direction:column;overflow-y:auto}
      .cq-right-section{padding:21px 19px;border-bottom:1px solid #e8edf3}
      .cq-right-section h4{margin:0 0 12px;color:#607289;font-size:12px;font-weight:750;letter-spacing:.06em}
      .cq-right-topic{margin-bottom:5px;padding:9px 11px;border-radius:7px;color:#52647a;font-size:13px;line-height:1.55;cursor:pointer;transition:.16s}
      .cq-right-topic:hover{color:#174d7c;background:#eef5fb;font-weight:650}
      .cq-right-topic .cq-hot{margin-left:6px;padding:2px 6px;border-radius:8px;color:#9f3037;background:#fbebec;font-size:9px}
      .cq-right-stat{display:flex;justify-content:space-between;align-items:center;padding:7px 0;color:#657589;font-size:12px}
      .cq-right-stat .cq-stv{font-weight:700;color:#1e293b}
      .cq-kb-link{display:block;margin-bottom:4px;padding:9px 10px;border-radius:6px;color:#245f88;font-size:13px;line-height:1.5;text-decoration:none;transition:.16s}
      .cq-kb-link:hover{color:#173f63;background:#eef5fb;font-weight:650}
      .cq-footer{padding:14px 18px!important;color:#8794a5!important;background:#fafbfd;font-size:11px!important;line-height:1.7;text-align:center}
      .cq-footer span{font-size:10px!important}
      @media(max-width:1180px){
        .cq-wrap{grid-template-columns:220px minmax(0,1fr)}
        .cq-right{display:none}
      }
      @media(max-width:820px){
        .cq-wrap{grid-template-columns:minmax(0,1fr);gap:0;padding:0}
        .cq-left{display:none}
        .cq-body{padding:20px 16px}
        .cq-msg{max-width:92%;font-size:13px}
      }
      @media(max-width:560px){
        .cq-page{height:calc(100vh - 64px);padding:8px}
        .cq-wrap{padding:0}
        .cq-main-header{padding:16px}
        .cq-input-wrap{padding:11px;gap:7px}
        .cq-input-wrap .cq-btn{padding:10px 12px}
      }
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
            <div class="cq-cat-group-header" onclick="var items=this.nextElementSibling;items.style.display=items.style.display==='none'?'block':'none'">
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
        <div class="cq-right-topic" onclick="_cqSendTopic('税务风险检查常见风险点')">税务风险检查常见风险点</div>
        <div class="cq-right-topic" onclick="_cqSendTopic('固定资产折旧年限表')">固定资产折旧年限</div>
        <div class="cq-right-topic" onclick="_cqSendTopic('印花税最新税目税率')">印花税最新税目</div>
      </div>
      <div class="cq-right-section">
        <h4>🔗 知识库快捷入口</h4>
        <a class="cq-kb-link" href="javascript:navigateTo('knowledge-hub')">🧠 引擎知识中枢</a>
        <a class="cq-kb-link" href="javascript:navigateTo('methodology')">📖 风险检查方法论</a>
        <a class="cq-kb-link" href="javascript:navigateTo('auditor-handbook')">⚖️ 风险检查员手册</a>
        <a class="cq-kb-link" href="javascript:navigateTo('tax-risk-rules-list')">📋 规则与调查目录</a>
        <a class="cq-kb-link" href="javascript:navigateTo('report-standards')">📐 报告编制要求</a>
      </div>
      <div class="cq-right-section cq-footer">
        存勤法税 v2.0 · AI智能体<br>
        <span style="font-size:9px">${new Date().getFullYear()} 广东存勤法税</span>
      </div>
    </div>
  `;

  el.innerHTML = css
    + '<div class="cq-page">'
    + '<header class="risk-report-header"><h2>智能问答</h2></header>'
    + `<div class="cq-wrap">${leftPanel}${mainPanel}${rightPanel}</div>`
    + '</div>';
  const pendingRisk = _consumeRiskQuestionContext();
  if (pendingRisk) {
    const input = document.getElementById('chat-input');
    const body = document.getElementById('chat-body');
    if (input) input.value = String(pendingRisk.question || '');
    if (body) {
      body.insertAdjacentHTML('afterbegin', '<div class="cq-risk-context"><b>已带入风险卡上下文：</b>'
        + escapeHtml(pendingRisk.title || pendingRisk.risk_id || '待核风险')
        + ' · 轮次 ' + escapeHtml(pendingRisk.round_id || '待核验')
        + '<br>请检查问题内容后发送。回答必须区分已证实事实、资料缺口、正常解释和待人工判断，并附可核验官方来源。</div>');
    }
    if (input) input.focus();
  }
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
    const resp = await fetch('/api/tax-risk-docs/ask?company_id=' + (window.currentCompanyId || 1), {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        question: q,
        session_id: chatSessionId
      })
    });
    const data = await resp.json();
    hideTyping();
    
    if (data.ok && data.answer) {
      const sourceNotice = data.citation_status === 'missing_official_source'
        ? '\n\n**依据状态：未取得可核验的官方来源，本回答不得写入正式报告或自动进入规则学习。**'
        : '\n\n**依据状态：' + ((data.citations || []).length ? '已附可核验来源，请逐项核对适用期间。' : '待核验。') + '**';
      appendMessage('ai', data.answer + sourceNotice + '\n\n---\n*⚠ 本回答为AI辅助生成，仅供参考。具体税务处理应以现行法律法规及主管税务机关正式意见为准。如涉及重大税务事项，请咨询专业税务顾问。*');
    } else if (data.ok && data.reply) {
      const sourceNotice = data.citation_status === 'missing_official_source'
        ? '\n\n**依据状态：未取得可核验的官方来源，本回答不得写入正式报告或自动进入规则学习。**'
        : '';
      appendMessage('ai', data.reply + sourceNotice + '\n\n---\n*⚠ 本回答为AI辅助生成，仅供参考。具体税务处理应以现行法律法规及主管税务机关正式意见为准。*');
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
  formData.append('session_id', chatSessionId);
  
  appendMessage('user', '📎 上传文件：' + file.name);
  chatLoading = true;
  showTyping();
  
  try {
    const resp = await fetch('/api/tax-risk-docs/ask?company_id=' + (window.currentCompanyId || 1), {
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
