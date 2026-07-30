// ================================================================
// 智能引擎中枢 · 闭环治理版
// 知识 → 约束 → 推理 → 运行 → 质控 → 追踪 → 学习
// ================================================================

var ENGINE_HUB_SECTIONS = [
  {
    id:'overview',
    label:'🧭 闭环总览',
    title:'闭环总览',
    desc:'统一定义引擎的职责边界、五个并行认知环路和七段治理闭环。'
  },
  {
    id:'knowledge',
    label:'🧠 知识与记忆',
    title:'知识与记忆',
    desc:'把稽查知识、行业基准、经验记忆、发现规则、映射和历史反馈统一为可检索的知识底座。'
  },
  {
    id:'rules',
    label:'🛡️ 决策边界',
    title:'决策边界与行为准则',
    desc:'规定引擎能判断什么、必须保留什么不确定性、何时必须降级或交由人工复核。'
  },
  {
    id:'agi',
    label:'🧬 推理核心',
    title:'税务 AGI 推理核心',
    desc:'集中呈现因果推理、反事实检验、红队证伪、调度协同和自我进化架构。'
  },
  {
    id:'dashboard',
    label:'🖥️ 运行全景',
    title:'运行全景与诊断',
    desc:'一次展开管道调度、学习反馈、AGI运行态、实时质量、方法对账和引擎详情。'
  },
  {
    id:'quality',
    label:'✅ 质量门禁',
    title:'质量门禁与交付治理',
    desc:'围绕输入、规则、证据、推理、报告和运行一致性设置六道检查，决定分析结果能否进入交付环节。'
  },
  {
    id:'logs',
    label:'📜 全程追踪',
    title:'执行日志与全程追踪',
    desc:'按发生顺序保留每次分析的阶段切换、规则触发、异常、耗时和输出结果。'
  },
  {
    id:'corrections',
    label:'🔧 学习纠正',
    title:'学习、纠正与进化',
    desc:'把编辑、审核和追问反馈转化为可核验、可暂停、可恢复、可追溯的学习规则。'
  }
];

var ENGINE_HUB_BRIDGES = {
  knowledge: [
    '知识与记忆层汇聚政策依据、行业基准、历史经验、发现规则、字段映射和审计记录，为分析提供统一、可检索、可核验的认知底座。',
    '记忆推送采用三级优先级：P0 为已验证模式骨架，P1 为同行业经验，P2 为通用指标偏离。每次推送都必须记录后续验证结果，连续误报的模式自动降权。',
    '知识资产按类别连续呈现，支持按需折叠和快速检索；每条内容均保留来源、适用范围、版本与验证状态。'
  ],
  rules: [
    '决策边界约束税务分析引擎的判断范围与行为方式，围绕证据充分性、法律适用、不确定性、数据安全、人工复核和可追溯性设置刚性要求。',
    '硬边界优先于模型意见：单一来源不得定案，证据不足不得补造事实，法条状态不明不得给出确定性结论，跨账套数据不得混用。',
    '规则冲突时按“法律与安全边界 → 证据强度 → 行业适用性 → 模型置信度”的顺序裁决。'
  ],
  agi: [
    '推理核心负责解释“引擎为什么形成这一判断”。感知层持续广播，记忆层主动推送，推理层同步验证；三者通过事件总线并行协同。',
    '证据闭环是唯一正式判定点：先做真实性、关联性、合法性三性校验，再要求至少两个独立来源，最后排除反向证据。不能闭环的发现必须降格为存疑。',
    '红队证伪是强制关卡：生成合法商业解释、逐条攻击现有证据、复核程序与现行法依据。无法击破反向解释时，不得升级结论。'
  ],
  dashboard: [
    '运行全景集中呈现引擎当前状态、阶段进度、质量水平和异常诊断，使分析过程可观察、可定位、可复核。',
    '六类运行信息一次展开：管道调度看阶段进度，学习反馈看本次规则触发，AGI运行态看调度与成长，实时质量看本次分析可靠性，方法对账看文档与代码一致性，引擎详情看实际数据和推理组件输出。',
    '没有一键分析数据时，对应区域明确显示“暂无数据”，不会用演示数字伪装成实时结果。'
  ],
  quality: [
    '质量门禁围绕输入完整性、规则适用性、证据充分性、推理一致性、报告准确性和运行稳定性执行六道检查。',
    '任何一道硬门禁失败，正式结论必须暂停放行；可降级项则标明限制条件、缺失材料和复核建议。',
    '自省环路独立运行：随机证据盲测、不同参数复跑、法条与数据一致性检查的结果会回写自愈与纠正规则。'
  ],
  logs: [
    '日志是审计轨迹，不是报告正文。它保留引擎实际做过什么、何时做、是否成功以及耗时多少，供故障定位和复核使用。',
    '日志不直接改变风险结论；任何由日志暴露的问题，必须经过纠正规则或质量门禁后才能影响下一次分析。'
  ],
  corrections: [
    '学习纠正环节承接编辑、审核和追问反馈：先完成结构化记录，再匹配同类场景，经过置信度与适用范围核验后进入后续分析。',
    '学习规则必须保留来源、适用行业、经营模式、证据条件、置信度、应用次数和启停状态；禁止把一次个案意见直接扩散为全行业规则。',
    '验证成功的模式逐步升级，误报模式自动降权；任何自动应用规则都可以暂停、恢复和回溯。'
  ]
};

function _engineHubOverviewHtml() {
  var loops = [
    ['感知', '资料进入即触发', '识别文件、提取情报、广播阶段事件；只提供信号和证据素材，不独立定案。', '#2563eb'],
    ['记忆', '持续监听并推送', '匹配政策、行业画像、历史模式和纠正经验；跟踪每次推送是否被后续证据验证。', '#7c3aed'],
    ['推理', '随感知并行启动', '汇聚多域信号、构建竞争性假设、完成证据闭环并执行红队证伪。', '#dc2626'],
    ['学习', '报告与反馈后触发', '抽取可迁移的资金、关系和发票拓扑骨架；验证后才提升规则置信度。', '#059669'],
    ['自省', '独立定时运行', '做证据盲测、参数复跑、幻觉检测和一致性检查，把缺陷转化为自愈要求。', '#d97706']
  ];
  var h = '<div class="engine-overview">';
  h += '<div class="engine-loop-grid">';
  loops.forEach(function(loop, index) {
    h += '<article class="engine-loop-card" style="border-top-color:' + loop[3] + '">';
    h += '<div class="engine-loop-index">0' + (index + 1) + '</div>';
    h += '<h3>' + loop[0] + '环路</h3><strong>' + loop[1] + '</strong><p>' + loop[2] + '</p></article>';
  });
  h += '</div>';
  h += '<div class="engine-flow-line">';
  [
    ['知识', '提供可验证背景'],
    ['约束', '划定判断边界'],
    ['推理', '形成竞争性假设'],
    ['运行', '执行并记录状态'],
    ['质控', '决定是否放行'],
    ['追踪', '保留完整轨迹'],
    ['学习', '验证后更新能力']
  ].forEach(function(item, index, all) {
    h += '<div class="engine-flow-node"><b>' + item[0] + '</b><span>' + item[1] + '</span></div>';
    if (index < all.length - 1) h += '<div class="engine-flow-arrow">→</div>';
  });
  h += '</div>';
  h += '<div class="engine-principles">';
  h += '<h3>统一判定原则</h3><div class="engine-principle-grid">';
  [
    ['证据先于结论', '至少两个独立来源且通过真实性、关联性、合法性校验，才能进入正式判断。'],
    ['反证先于升级', '每个高风险发现必须生成合法解释并逐条证伪；无法排除时降格为存疑。'],
    ['实质先于标签', '工商登记、发票、资金和人员结论不一致时，展示穿透过程，不以单一标签覆盖事实。'],
    ['限制必须可见', '缺资料、低置信度、法条待核验和行业不适用必须直接显示，禁止静默补全。'],
    ['人工保留终审权', '模型负责发现、组织和建议；行政认定、处罚及司法判断必须由有权人员完成。'],
    ['全程可追溯', '结论能够回到规则、链路、证据来源、原始数据和人工纠正记录。']
  ].forEach(function(item) {
    h += '<div><b>' + item[0] + '</b><p>' + item[1] + '</p></div>';
  });
  h += '</div></div></div>';
  return h;
}

function _renderEngineHubOverview(container) {
  if (container) container.innerHTML = _engineHubOverviewHtml();
}

function _engineHubBridgeHtml(sectionId) {
  var items = ENGINE_HUB_BRIDGES[sectionId] || [];
  if (!items.length) return '';
  var h = '<div class="engine-section-bridge">';
  items.forEach(function(item) { h += '<p>' + item + '</p>'; });
  return h + '</div>';
}

function _engineHubMount(sectionId, rendererName) {
  var mount = document.getElementById('engine-mount-' + sectionId);
  if (!mount) return;
  var renderer = window[rendererName];
  if (typeof renderer !== 'function') {
    mount.innerHTML = '<div class="engine-load-error">该能力尚未载入，请刷新页面后重试。</div>';
    return;
  }
  try {
    var result = renderer(mount);
    if (result && typeof result.catch === 'function') {
      result.catch(function(error) {
        mount.innerHTML = '<div class="engine-load-error">载入失败：'
          + ((error && error.message) || '未知错误') + '</div>';
      });
    }
  } catch (error) {
    mount.innerHTML = '<div class="engine-load-error">载入失败：'
      + ((error && error.message) || '未知错误') + '</div>';
  }
}

function renderEngineHub(container) {
  if (!container) return;
  window.currentModule = '智能引擎中枢';
  var shouldScrollToSelected = Boolean(window._engineHubSection);
  var selected = window._engineHubSection || 'overview';
  window._engineHubSection = null;

  var toc = ENGINE_HUB_SECTIONS.map(function(section, index) {
    return '<a href="#engine-section-' + section.id + '" data-engine-section="' + section.id
      + '" onclick="selectEngineHubSection(\'' + section.id + '\');return false;">'
      + '<span class="engine-toc-index">' + String(index + 1).padStart(2, '0') + '</span>'
      + '<span class="engine-toc-label">' + section.label + '</span></a>';
  }).join('');

  var sections = ENGINE_HUB_SECTIONS.map(function(section, index) {
    var body = section.id === 'overview'
      ? _engineHubOverviewHtml()
      : _engineHubBridgeHtml(section.id)
        + '<div id="engine-mount-' + section.id + '" class="engine-section-body">'
        + '<div class="engine-loading"><span class="spinner"></span> 正在载入完整内容...</div></div>';
    return '<section id="engine-section-' + section.id + '" class="engine-unified-section">'
      + '<header class="engine-section-head"><span class="engine-section-no">'
      + String(index + 1).padStart(2, '0') + '</span><div class="engine-section-title">'
      + '<span class="engine-section-kicker">治理章节 · '
      + String(index + 1).padStart(2, '0') + ' / '
      + String(ENGINE_HUB_SECTIONS.length).padStart(2, '0') + '</span><h2>' + section.title
      + '</h2><p>' + section.desc + '</p></div></header>' + body + '</section>';
  }).join('');

  container.innerHTML = `
    <style>
      .engine-unified{
        --engine-ink:#14243a;
        --engine-text:#3d4f65;
        --engine-muted:#68788d;
        --engine-line:#dce4ee;
        --engine-soft:#f4f7fb;
        --engine-blue:#1f5f99;
        --engine-blue-dark:#123454;
        max-width:1500px;
        margin:0 auto;
        padding:36px clamp(24px,3.2vw,52px) 56px;
        box-sizing:border-box;
        color:var(--engine-text);
        background:var(--engine-soft);
        font-family:"Microsoft YaHei UI","Microsoft YaHei","PingFang SC","Noto Sans SC",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
        font-size:15px;
        line-height:1.78;
        letter-spacing:.01em;
        text-rendering:optimizeLegibility
      }
      .engine-unified *{box-sizing:border-box}
      .engine-unified-hero{
        position:relative;
        overflow:hidden;
        margin-bottom:30px;
        padding:46px 52px 42px;
        border:1px solid rgba(255,255,255,.12);
        border-radius:18px;
        color:#fff;
        background:linear-gradient(135deg,#102b47 0%,#194b76 62%,#246693 100%);
        box-shadow:0 16px 36px rgba(15,39,66,.16)
      }
      .engine-unified-hero:after{
        content:"";
        position:absolute;
        right:-70px;
        bottom:-110px;
        width:330px;
        height:330px;
        border:1px solid rgba(255,255,255,.1);
        border-radius:50%;
        box-shadow:0 0 0 52px rgba(255,255,255,.035),0 0 0 104px rgba(255,255,255,.025)
      }
      .engine-unified-badge{
        position:relative;
        z-index:1;
        display:inline-flex;
        align-items:center;
        margin-bottom:16px;
        padding:6px 12px;
        border:1px solid rgba(255,255,255,.2);
        border-radius:5px;
        color:#dbeafe;
        background:rgba(255,255,255,.08);
        font-size:12px;
        font-weight:700;
        letter-spacing:.08em
      }
      .engine-unified-hero h1{
        position:relative;
        z-index:1;
        margin:0 0 14px;
        color:#fff;
        font-size:34px;
        line-height:1.3;
        font-weight:750;
        letter-spacing:.02em
      }
      .engine-unified-hero p{
        position:relative;
        z-index:1;
        max-width:1040px;
        margin:0;
        color:#dce8f4;
        font-size:15px;
        line-height:2;
        text-align:justify
      }
      .engine-unified-shell{
        display:grid;
        grid-template-columns:224px minmax(0,1fr);
        gap:30px;
        align-items:start
      }
      .engine-unified-toc{
        position:sticky;
        top:18px;
        z-index:20;
        display:block;
        padding:18px 14px 16px;
        border:1px solid var(--engine-line);
        border-radius:13px;
        background:rgba(255,255,255,.97);
        box-shadow:0 8px 24px rgba(20,36,58,.06)
      }
      .engine-toc-title{
        margin:0 8px 12px;
        padding-bottom:11px;
        border-bottom:1px solid #e8edf3;
        color:var(--engine-ink);
        font-size:13px;
        font-weight:750;
        letter-spacing:.08em
      }
      .engine-toc-note{
        display:block;
        margin:10px 8px 2px;
        color:#93a0b1;
        font-size:11px;
        line-height:1.65
      }
      .engine-unified-toc a{
        display:grid;
        grid-template-columns:28px minmax(0,1fr);
        gap:9px;
        align-items:center;
        margin:3px 0;
        padding:9px 9px;
        border:1px solid transparent;
        border-radius:7px;
        color:#53657a;
        text-decoration:none;
        font-size:13px;
        font-weight:600;
        line-height:1.45;
        transition:background .16s ease,border-color .16s ease,color .16s ease
      }
      .engine-unified-toc a:hover{
        border-color:#dbe7f2;
        color:var(--engine-blue);
        background:#f5f9fd
      }
      .engine-unified-toc a.active{
        border-color:#cbddeb;
        color:#174d78;
        background:#eaf3fa;
        box-shadow:inset 3px 0 0 var(--engine-blue)
      }
      .engine-toc-index{
        display:inline-flex;
        align-items:center;
        justify-content:center;
        width:26px;
        height:26px;
        border-radius:6px;
        color:#718197;
        background:#edf2f7;
        font-size:10px;
        font-weight:800;
        letter-spacing:0
      }
      .engine-unified-toc a.active .engine-toc-index{
        color:#fff;
        background:var(--engine-blue)
      }
      .engine-unified-content{min-width:0}
      .engine-unified-section{
        scroll-margin-top:24px;
        margin:0 0 28px;
        padding:34px clamp(28px,3vw,40px) 38px;
        border:1px solid var(--engine-line);
        border-radius:15px;
        background:#fff;
        box-shadow:0 8px 24px rgba(20,36,58,.045)
      }
      .engine-section-head{
        display:flex;
        gap:17px;
        align-items:flex-start;
        margin-bottom:26px;
        padding-bottom:21px;
        border-bottom:1px solid #e5ebf2
      }
      .engine-section-no{
        display:inline-flex;
        align-items:center;
        justify-content:center;
        width:42px;
        height:42px;
        flex:0 0 42px;
        margin-top:2px;
        border-radius:8px;
        color:#fff;
        background:var(--engine-blue-dark);
        font-size:12px;
        font-weight:800;
        letter-spacing:.04em;
        box-shadow:0 5px 12px rgba(18,52,84,.16)
      }
      .engine-section-title{min-width:0}
      .engine-section-kicker{
        display:block;
        margin-bottom:4px;
        color:#77879a;
        font-size:10px;
        font-weight:750;
        letter-spacing:.12em
      }
      .engine-section-head h2{
        margin:0 0 7px;
        color:var(--engine-ink);
        font-size:23px;
        line-height:1.4;
        font-weight:750;
        letter-spacing:.015em
      }
      .engine-section-head p{
        max-width:900px;
        margin:0;
        color:var(--engine-muted);
        font-size:14px;
        line-height:1.85
      }
      .engine-section-bridge{
        margin:0 0 25px;
        padding:20px 24px 20px 26px;
        border:1px solid #d7e3ee;
        border-left:4px solid var(--engine-blue);
        border-radius:9px;
        background:#f6f9fc
      }
      .engine-section-bridge p{
        margin:0 0 13px;
        color:#46596f;
        font-size:14px;
        line-height:1.9;
        text-align:justify
      }
      .engine-section-bridge p:last-child{margin-bottom:0}
      .engine-section-body{
        min-height:100px;
        color:var(--engine-text);
        font-size:14px;
        line-height:1.82
      }
      .engine-section-body>p,.engine-section-body li{line-height:1.85}
      .engine-section-body>.kh-wrap,
      .engine-section-body>.crh-layout,
      .engine-section-body>.qs-layout{
        max-width:none!important;
        margin:0!important;
        padding:0!important
      }
      .engine-section-body .agi-layout{
        display:block!important;
        max-width:none!important;
        margin:0!important;
        padding:0!important
      }
      .engine-section-body .agi-toc{display:none!important}
      .engine-section-body [style*="font-size:10px"]{font-size:13px!important}
      .engine-section-body [style*="font-size:11px"]{font-size:13px!important}
      .engine-section-body [style*="font-size:12px"]{font-size:13px!important}
      .engine-section-body [style*="line-height:20px"]{line-height:1.82!important}
      .engine-section-body table{width:100%;font-size:13px!important;line-height:1.7}
      .engine-section-body table th{padding:11px 13px!important;line-height:1.55}
      .engine-section-body table td{padding:10px 13px!important;line-height:1.7;vertical-align:top}
      .engine-section-body input,.engine-section-body select,.engine-section-body textarea{
        min-height:38px;
        font-family:inherit;
        font-size:14px!important
      }
      .engine-section-body button{font-family:inherit;font-size:13px!important}
      .engine-loading,.engine-load-error{
        padding:40px;
        border:1px solid #e4eaf1;
        border-radius:9px;
        color:#718096;
        background:#f8fafc;
        text-align:center;
        font-size:14px
      }
      .engine-load-error{border-color:#fecaca;color:#b91c1c;background:#fef2f2}
      .engine-loop-grid{
        display:grid;
        grid-template-columns:repeat(auto-fit,minmax(205px,1fr));
        gap:15px
      }
      .engine-loop-card{
        position:relative;
        min-height:182px;
        padding:22px 20px 21px;
        border:1px solid #dde5ee;
        border-top:4px solid;
        border-radius:10px;
        background:#fff;
        box-shadow:0 4px 13px rgba(20,36,58,.035)
      }
      .engine-loop-card h3{
        margin:0 0 7px;
        color:var(--engine-ink);
        font-size:16px;
        line-height:1.45
      }
      .engine-loop-card strong{
        display:block;
        margin-bottom:10px;
        color:#53657a;
        font-size:12px;
        line-height:1.6
      }
      .engine-loop-card p{
        margin:0;
        color:#68788d;
        font-size:13px;
        line-height:1.82;
        text-align:justify
      }
      .engine-loop-index{
        position:absolute;
        right:15px;
        top:12px;
        color:#c5d0dc;
        font-size:19px;
        font-weight:800
      }
      .engine-flow-line{
        display:flex;
        align-items:stretch;
        gap:8px;
        margin:22px 0;
        padding:18px;
        overflow-x:auto;
        border:1px solid #e2e8f0;
        border-radius:11px;
        background:#f7f9fc
      }
      .engine-flow-node{
        flex:1 0 104px;
        min-width:104px;
        padding:13px 10px;
        border:1px solid #dce5ee;
        border-radius:8px;
        background:#fff;
        text-align:center
      }
      .engine-flow-node b{display:block;color:var(--engine-ink);font-size:13px}
      .engine-flow-node span{
        display:block;
        margin-top:5px;
        color:#738398;
        font-size:11px;
        line-height:1.55
      }
      .engine-flow-arrow{display:flex;align-items:center;color:#93a3b6;font-weight:800}
      .engine-principles{
        padding:24px;
        border:1px solid #d9e3ed;
        border-radius:11px;
        background:#f8fafc
      }
      .engine-principles>h3{
        margin:0 0 16px;
        color:var(--engine-ink);
        font-size:17px;
        line-height:1.45
      }
      .engine-principle-grid{
        display:grid;
        grid-template-columns:repeat(2,minmax(0,1fr));
        gap:13px
      }
      .engine-principle-grid>div{
        padding:17px 18px;
        border:1px solid #e0e7ef;
        border-radius:8px;
        background:#fff
      }
      .engine-principle-grid b{color:#22364e;font-size:14px}
      .engine-principle-grid p{
        margin:7px 0 0;
        color:#66778b;
        font-size:13px;
        line-height:1.82;
        text-align:justify
      }
      .engine-unified .kh-integrated-wrap{font-size:14px!important;line-height:1.82!important;color:var(--engine-text)!important}
      .engine-unified .kh-integrated-tools{margin-bottom:18px!important;padding:14px!important;border-color:#d9e4ee!important;background:#f7fafd!important}
      .engine-unified .kh-integrated-search{padding:10px 12px!important;font-size:14px!important}
      .engine-unified .kh-integrated-btn{padding:9px 12px!important;font-size:12px!important}
      .engine-unified .kh-integrated-group{margin-bottom:13px!important;border-color:#dce4ed!important}
      .engine-unified .kh-integrated-group>summary{padding:17px 19px!important;background:#f7f9fc!important}
      .engine-unified .kh-integrated-group summary b{font-size:14px!important;color:#214b73!important}
      .engine-unified .kh-integrated-group summary small{margin-top:4px!important;font-size:12px!important;line-height:1.65!important}
      .engine-unified .kh-summary-state{font-size:11px!important}
      .engine-unified .kh-integrated-body{padding:18px!important;color:var(--engine-text)!important}
      .engine-unified .kh-card{margin-bottom:11px!important;padding:15px 17px!important;background:#f5f9fd!important}
      .engine-unified .kh-card h4{font-size:14px!important}
      .engine-unified .kh-meta,.engine-unified .kh-detail{font-size:13px!important;line-height:1.8!important}
      .engine-unified .kh-table{font-size:13px!important;color:var(--engine-text)!important}
      .engine-unified .engine-rules{font-size:14px!important;line-height:1.82}
      .engine-unified .engine-rules-toc,.engine-unified .engine-live-toc{gap:8px!important;margin-bottom:18px!important}
      .engine-unified .engine-rules-toc a,.engine-unified .engine-live-toc a{padding:7px 11px!important;font-size:12px!important}
      .engine-unified .engine-rule-section{margin-bottom:18px!important;padding:20px!important;border-color:#dce4ed!important}
      .engine-unified .engine-rule-section>header{margin-bottom:15px!important;padding-bottom:14px!important}
      .engine-unified .engine-rule-section h3{font-size:16px!important}
      .engine-unified .engine-rule-section header p{font-size:13px!important;line-height:1.75!important}
      .engine-unified .engine-rule-grid{gap:13px!important}
      .engine-unified .engine-rule-card{padding:16px 17px!important}
      .engine-unified .engine-rule-name{font-size:14px!important}
      .engine-unified .engine-rule-card p{margin-top:8px!important;font-size:13px!important;line-height:1.82!important}
      .engine-unified .agi-main{font-size:14px;line-height:1.82}
      .engine-unified .agi-hero{margin-bottom:30px!important;padding:24px 26px!important;border-color:#dce4ed!important;background:#f8fafc!important}
      .engine-unified .agi-main h2.hb-section-title{margin-bottom:19px!important;padding-bottom:13px!important;font-size:18px!important;line-height:1.5!important}
      .engine-unified .agi-main .hb-section-lead{margin-bottom:17px!important;font-size:14px!important;line-height:1.85!important}
      .engine-unified .agi-main section{margin-bottom:42px!important}
      .engine-unified .agi-main .hb-card-grid,.engine-unified .agi-main .agi-card-grid{gap:15px!important}
      .engine-unified .engine-live{font-size:14px;line-height:1.82}
      .engine-unified .engine-live-panel{margin-bottom:18px!important;border-color:#dce4ed!important;border-radius:9px!important}
      .engine-unified .engine-live-panel>header{padding:17px 19px!important;background:#f7f9fc!important}
      .engine-unified .engine-live-panel h3{font-size:16px!important}
      .engine-unified .engine-live-panel header p{font-size:13px!important;line-height:1.75!important}
      .engine-unified .engine-live-body{padding:20px!important}
      .engine-unified .qs-main{font-size:14px!important;line-height:1.82!important}
      .engine-unified .qs-sec-title{margin-bottom:17px!important;padding-bottom:13px!important;font-size:17px!important}
      .engine-unified .qs-layer{margin-bottom:17px!important;padding:21px!important;line-height:1.82!important}
      .engine-unified .qs-item{margin-bottom:12px!important;padding:14px 16px!important;line-height:1.82!important}
      .engine-unified .qs-info{padding:18px 21px!important;font-size:13px!important;line-height:1.82!important}
      .engine-unified .crh-h2{font-size:19px!important}
      .engine-unified .crh-sub{margin-bottom:26px!important;color:#64748b!important;font-size:14px!important;line-height:1.9!important}
      .engine-unified .crh-stats{gap:14px!important;margin-bottom:28px!important}
      .engine-unified .crh-stat{padding:18px 13px!important;border-color:#dce4ed!important}
      .engine-unified .crh-stat-label{font-size:12px!important}
      .engine-unified .crh-filter{gap:9px!important;margin-bottom:19px!important}
      .engine-unified .crh-filter-btn{padding:8px 15px!important;font-size:12px!important}
      .engine-unified .crh-card{margin-bottom:13px!important;padding:18px 20px!important;border-color:#dce4ed!important}
      .engine-unified .crh-meta,.engine-unified .crh-chain{font-size:12px!important;line-height:1.7}
      .engine-unified .crh-reason{margin-top:11px!important;padding:11px 13px!important;font-size:13px!important;line-height:1.82!important}
      #engine-mount-logs>div{font-size:12.5px!important;line-height:1.85!important;padding:17px 19px!important}
      #engine-mount-logs [style*="font-size:10px"]{font-size:12.5px!important;line-height:1.85!important}
      @media(max-width:1180px){
        .engine-unified{padding:28px 24px 46px}
        .engine-unified-shell{display:block}
        .engine-unified-section{scroll-margin-top:82px}
        .engine-unified-toc{
          position:sticky;
          top:0;
          display:flex;
          gap:7px;
          margin-bottom:20px;
          padding:11px;
          overflow-x:auto;
          border-radius:10px
        }
        .engine-toc-title,.engine-toc-note{display:none}
        .engine-unified-toc a{flex:0 0 auto;margin:0;padding:8px 10px}
        .engine-unified-toc a.active{box-shadow:inset 0 -3px 0 var(--engine-blue)}
      }
      @media(max-width:820px){
        .engine-unified-hero{padding:36px 34px}
        .engine-unified-hero h1{font-size:29px}
        .engine-unified-section{padding:28px 25px 31px}
        .engine-loop-grid,.engine-principle-grid{grid-template-columns:1fr 1fr}
        .engine-rule-grid{grid-template-columns:1fr!important}
      }
      @media(max-width:680px){
        .engine-unified{padding:14px 12px 34px;font-size:14px}
        .engine-unified-hero{margin-bottom:18px;padding:28px 22px;border-radius:13px}
        .engine-unified-hero h1{font-size:25px}
        .engine-unified-hero p{font-size:14px;line-height:1.85;text-align:left}
        .engine-unified-section{margin-bottom:18px;padding:23px 18px 26px;border-radius:11px}
        .engine-section-head{gap:12px;margin-bottom:20px;padding-bottom:17px}
        .engine-section-no{width:36px;height:36px;flex-basis:36px}
        .engine-section-head h2{font-size:20px}
        .engine-section-head p{font-size:13px}
        .engine-section-bridge{padding:17px 17px 17px 19px}
        .engine-section-bridge p{text-align:left}
        .engine-loop-grid,.engine-principle-grid{grid-template-columns:1fr}
        .engine-loop-card{min-height:0}
        .engine-flow-line{padding:13px}
        .engine-unified .crh-stats{grid-template-columns:repeat(2,minmax(0,1fr))!important}
        .engine-unified .agi-main .hb-card-grid,.engine-unified .agi-main .agi-card-grid{grid-template-columns:1fr!important}
        .engine-section-body{overflow-x:auto}
      }
    </style>
    <div class="engine-unified" data-engine-layout="executive">
      <header class="engine-unified-hero">
        <span class="engine-unified-badge">知识驱动 · 受控推理 · 持续进化</span>
        <h1>🧠 智能引擎中枢</h1>
        <p>智能引擎中枢汇聚税务知识、行业基准、分析规则与历史经验，协调感知、记忆、推理、质控和学习能力，为每一次分析提供可验证的依据、可解释的推理路径、可追溯的运行记录和受控的改进机制。所有结论均经过证据校验、反向验证与质量门禁；资料不足、规则冲突或置信度不足时，系统主动降级并提交人工复核。</p>
      </header>
      <div class="engine-unified-shell">
        <nav class="engine-unified-toc" aria-label="智能引擎中枢单页目录">
          <div class="engine-toc-title">页面目录</div>
          ${toc}
          <small class="engine-toc-note">内容按治理闭环连续展开，目录仅用于定位，不隐藏任何章节。</small>
        </nav>
        <main class="engine-unified-content">${sections}</main>
      </div>
    </div>`;

  _engineHubMount('knowledge', 'renderKnowledgeHubIntegrated');
  _engineHubMount('rules', 'renderAiRules');
  window._agiSection = null;
  _engineHubMount('agi', 'renderAgiDashboard');
  _engineHubMount('dashboard', 'renderEngineDashboardIntegrated');
  window._qsLayer = null;
  _engineHubMount('quality', 'renderQualitySystem');
  _engineHubMount('logs', 'renderAnalyzeLogs');
  _engineHubMount('corrections', 'renderCorrectionRulesHub');

  setTimeout(function() {
    if (shouldScrollToSelected) {
      selectEngineHubSection(selected, true);
      return;
    }
    var initialLinks = document.querySelectorAll('[data-engine-section]');
    for (var i = 0; i < initialLinks.length; i++) {
      initialLinks[i].classList.toggle(
        'active',
        initialLinks[i].getAttribute('data-engine-section') === selected
      );
    }
  }, 80);
}

function selectEngineHubSection(sectionId, skipSmooth) {
  var section = ENGINE_HUB_SECTIONS.filter(function(item) {
    return item.id === sectionId;
  })[0] || ENGINE_HUB_SECTIONS[0];
  var links = document.querySelectorAll('[data-engine-section]');
  for (var i = 0; i < links.length; i++) {
    links[i].classList.toggle(
      'active',
      links[i].getAttribute('data-engine-section') === section.id
    );
  }
  var target = document.getElementById('engine-section-' + section.id);
  if (target) {
    target.scrollIntoView({
      behavior: skipSmooth ? 'auto' : 'smooth',
      block: 'start'
    });
  }
  window.currentModule = '智能引擎中枢';
}
