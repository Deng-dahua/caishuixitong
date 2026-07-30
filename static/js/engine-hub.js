// ================================================================
// 智能引擎中枢 · 单页融合版
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
    desc:'只承担输入、规则、证据、推理、报告和运行一致性检查，不再重复方法论与知识资产。'
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
    '本区是全部推理活动的共同输入层。知识不再按“一个页签一个仓库”分散展示，而是按知识、基准、记忆、规则、映射、审计六类用途统一组织。',
    '记忆推送采用三级优先级：P0 为已验证模式骨架，P1 为同行业经验，P2 为通用指标偏离。每次推送都必须记录后续验证结果，连续误报的模式自动降权。',
    '所有知识分类均在本页加载；折叠只改变阅读密度，不改变内容是否存在。'
  ],
  rules: [
    '本区约束的是税务分析引擎，不再展示与业务判断无关的代码维护口号。所有规则围绕证据、法律、不确定性、数据安全、人工复核和可追溯性展开。',
    '硬边界优先于模型意见：单一来源不得定案，证据不足不得补造事实，法条状态不明不得给出确定性结论，跨账套数据不得混用。',
    '规则冲突时按“法律与安全边界 → 证据强度 → 行业适用性 → 模型置信度”的顺序裁决。'
  ],
  agi: [
    '本区说明“引擎为什么这样判断”。感知层持续广播，记忆层主动推送，推理层同步验证；三者不是先后排队，而是通过事件总线并行协同。',
    '证据闭环是唯一正式判定点：先做真实性、关联性、合法性三性校验，再要求至少两个独立来源，最后排除反向证据。不能闭环的发现必须降格为存疑。',
    '红队证伪是强制关卡：生成合法商业解释、逐条攻击现有证据、复核程序与现行法依据。无法击破反向解释时，不得升级结论。'
  ],
  dashboard: [
    '本区说明“引擎现在运行得怎样”。它只展示实时状态和诊断结果，不再重复介绍静态架构。',
    '六类运行信息一次展开：管道调度看阶段进度，学习反馈看本次规则触发，AGI运行态看调度与成长，实时质量看本次分析可靠性，方法对账看文档与代码一致性，引擎详情看实际数据和推理组件输出。',
    '没有一键分析数据时，对应区域明确显示“暂无数据”，不会用演示数字伪装成实时结果。'
  ],
  quality: [
    '本区回答“什么结果可以放行”。质量保障不再重复讲知识库数量、方法论章节或AGI架构，只保留六道可执行门禁。',
    '任何一道硬门禁失败，正式结论必须暂停放行；可降级项则标明限制条件、缺失材料和复核建议。',
    '自省环路独立运行：随机证据盲测、不同参数复跑、法条与数据一致性检查的结果会回写自愈与纠正规则。'
  ],
  logs: [
    '日志是审计轨迹，不是报告正文。它保留引擎实际做过什么、何时做、是否成功以及耗时多少，供故障定位和复核使用。',
    '日志不直接改变风险结论；任何由日志暴露的问题，必须经过纠正规则或质量门禁后才能影响下一次分析。'
  ],
  corrections: [
    '本区完成闭环的最后一步：人工反馈先结构化，再匹配同类场景，经过置信度和适用范围核验后进入下一次分析。',
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
  var selected = window._engineHubSection || 'overview';
  window._engineHubSection = null;

  var toc = ENGINE_HUB_SECTIONS.map(function(section) {
    return '<a href="#engine-section-' + section.id + '" data-engine-section="' + section.id
      + '" onclick="selectEngineHubSection(\'' + section.id + '\');return false;">'
      + section.label + '</a>';
  }).join('');

  var sections = ENGINE_HUB_SECTIONS.map(function(section, index) {
    var body = section.id === 'overview'
      ? _engineHubOverviewHtml()
      : _engineHubBridgeHtml(section.id)
        + '<div id="engine-mount-' + section.id + '" class="engine-section-body">'
        + '<div class="engine-loading"><span class="spinner"></span> 正在载入完整内容...</div></div>';
    return '<section id="engine-section-' + section.id + '" class="engine-unified-section">'
      + '<header class="engine-section-head"><span class="engine-section-no">'
      + String(index + 1).padStart(2, '0') + '</span><div><h2>' + section.title
      + '</h2><p>' + section.desc + '</p></div></header>' + body + '</section>';
  }).join('');

  container.innerHTML = `
    <style>
      .engine-unified{max-width:1380px;margin:0 auto;padding:24px;color:#334155}
      .engine-unified-hero{padding:28px 30px;border:1px solid #dce5ef;border-radius:16px;background:linear-gradient(135deg,#f8fbff 0%,#faf7ff 55%,#f8fafc 100%)}
      .engine-unified-hero h1{margin:0 0 10px;color:#0f172a;font-size:27px}
      .engine-unified-hero p{margin:0;max-width:1060px;color:#526174;font-size:14px;line-height:1.9}
      .engine-unified-badge{display:inline-flex;margin-bottom:12px;padding:5px 12px;border-radius:999px;background:#ede9fe;color:#6d28d9;font-size:12px;font-weight:700}
      .engine-unified-toc{position:sticky;top:0;z-index:20;display:flex;gap:7px;flex-wrap:wrap;margin:14px 0 20px;padding:11px;border:1px solid #e2e8f0;border-radius:12px;background:rgba(255,255,255,.96);box-shadow:0 4px 18px rgba(15,23,42,.05)}
      .engine-unified-toc a{padding:7px 11px;border-radius:999px;color:#475569;text-decoration:none;font-size:12px;font-weight:650}
      .engine-unified-toc a:hover,.engine-unified-toc a.active{background:#6d28d9;color:#fff}
      .engine-unified-section{scroll-margin-top:72px;margin:0 0 22px;padding:24px;border:1px solid #e2e8f0;border-radius:15px;background:#fff;box-shadow:0 5px 18px rgba(15,23,42,.035)}
      .engine-section-head{display:flex;gap:14px;align-items:flex-start;margin-bottom:16px;padding-bottom:14px;border-bottom:1px solid #e8edf3}
      .engine-section-no{display:inline-flex;align-items:center;justify-content:center;width:36px;height:36px;flex:0 0 36px;border-radius:10px;background:#0f172a;color:#fff;font-size:12px;font-weight:800}
      .engine-section-head h2{margin:0 0 5px;color:#0f172a;font-size:21px}
      .engine-section-head p{margin:0;color:#64748b;font-size:13px;line-height:1.75}
      .engine-section-bridge{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:0 0 18px}
      .engine-section-bridge p{margin:0;padding:12px 14px;border-left:3px solid #7c3aed;border-radius:7px;background:#faf7ff;color:#536173;font-size:12px;line-height:1.75}
      .engine-section-body{min-height:100px}
      .engine-section-body>.kh-wrap,.engine-section-body>.crh-layout,.engine-section-body>.qs-layout{max-width:none;margin:0;padding:0}
      .engine-section-body .qs-layout{max-width:none}
      .engine-section-body .agi-layout{max-width:none}
      .engine-loading,.engine-load-error{padding:34px;text-align:center;color:#64748b;background:#f8fafc;border-radius:9px}
      .engine-load-error{color:#b91c1c;background:#fef2f2}
      .engine-loop-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}
      .engine-loop-card{position:relative;padding:16px 14px;border:1px solid #e2e8f0;border-top:4px solid;border-radius:10px;background:#fff}
      .engine-loop-card h3{margin:0 0 5px;color:#0f172a;font-size:14px}
      .engine-loop-card strong{display:block;margin-bottom:7px;color:#475569;font-size:11px}
      .engine-loop-card p{margin:0;color:#64748b;font-size:11px;line-height:1.75}
      .engine-loop-index{position:absolute;right:10px;top:8px;color:#cbd5e1;font-size:18px;font-weight:800}
      .engine-flow-line{display:flex;align-items:stretch;gap:7px;margin:16px 0;padding:14px;border-radius:11px;background:#f8fafc}
      .engine-flow-node{flex:1;min-width:0;padding:10px;text-align:center;border:1px solid #e2e8f0;border-radius:8px;background:#fff}
      .engine-flow-node b{display:block;color:#0f172a;font-size:12px}
      .engine-flow-node span{display:block;margin-top:3px;color:#64748b;font-size:10px;line-height:1.45}
      .engine-flow-arrow{display:flex;align-items:center;color:#94a3b8;font-weight:800}
      .engine-principles{padding:17px;border:1px solid #dbe4ee;border-radius:11px;background:linear-gradient(135deg,#f8fafc,#fff)}
      .engine-principles>h3{margin:0 0 12px;color:#0f172a;font-size:15px}
      .engine-principle-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
      .engine-principle-grid>div{padding:12px;border-radius:8px;background:#fff;border:1px solid #e2e8f0}
      .engine-principle-grid b{color:#1e293b;font-size:12px}
      .engine-principle-grid p{margin:5px 0 0;color:#64748b;font-size:11px;line-height:1.7}
      @media(max-width:1000px){.engine-loop-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.engine-section-bridge,.engine-principle-grid{grid-template-columns:1fr 1fr}.engine-flow-line{flex-wrap:wrap}.engine-flow-node{min-width:120px}.engine-flow-arrow{display:none}}
      @media(max-width:680px){.engine-unified{padding:12px}.engine-unified-hero,.engine-unified-section{padding:18px}.engine-section-bridge,.engine-principle-grid,.engine-loop-grid{grid-template-columns:1fr}.engine-unified-toc{position:static}.engine-section-head h2{font-size:18px}}
    </style>
    <div class="engine-unified">
      <header class="engine-unified-hero">
        <span class="engine-unified-badge">单页融合 · 全量能力 · 闭环治理</span>
        <h1>🧠 智能引擎中枢</h1>
        <p>本页不再保留“知识中枢、运行仪表盘、质量保障、行为准则、税务AGI、执行日志、纠正规则”等相互割裂的子页面。全部内容按照“知识提供依据—约束划定边界—推理形成假设—运行执行分析—质量决定放行—日志保留轨迹—反馈驱动进化”的闭环重新组织；重复的架构说明只保留一次，实时状态与静态规范明确分工。</p>
      </header>
      <nav class="engine-unified-toc" aria-label="智能引擎中枢单页目录">${toc}</nav>
      ${sections}
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

  setTimeout(function() { selectEngineHubSection(selected, true); }, 80);
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
