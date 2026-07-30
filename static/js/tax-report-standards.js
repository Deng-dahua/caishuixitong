// ==================== 报告编制要求（统一融合版） ====================

function renderReportStandards(container) {
  if (!container) return;
  window.currentModule = '报告编制要求';

  var sections = [
    {
      id: 'rpt-1',
      title: '一、报告定位与法律边界',
      summary: '先明确报告是什么、能说到什么程度，再确定全部编制用语和披露边界。',
      body: `
        <p>报告的终极目的，是使未接触原始数据的审核人员在完整阅读后，能够独立判断是否达到立案标准、是否需要追缴税款、是否需要移送司法机关。报告必须同时建立在<strong>事实、证据、逻辑、法律</strong>四个支柱上：事实须明确日期、主体、金额和数量；证据须定位到发票号、账页、文件行号或合同条款；逻辑须说明异常、合法情形排除过程及税务后果；法律须列明现行法条名称和条款号。</p>
        <p>报告处于<strong>事实发现和专业判断阶段</strong>，不是行政处罚决定或刑事裁判。全篇使用“涉嫌、存疑、可能存在、建议核实、需进一步确认、与申报数据存在差异、未能提供相关证据”等审慎表述；禁止使用“违法、认定、确定、必定、显然、绝对、非法、犯罪”等终局裁判性用语。</p>
        <div class="rpt-duo">
          <div class="rpt-card ok"><b>规范表达</b><span>经查、该企业、被查单位、数据显示、综合分析判断、潜在风险、建议进一步核实。</span></div>
          <div class="rpt-card bad"><b>禁止表达</b><span>我、你、我们，以及未经法定程序直接作出的违法认定、犯罪定性或绝对化结论。</span></div>
        </div>
        <p><strong>机密边界：</strong>系统执行流程、内部配置参数、代码位置、系统日志、内部方法论名称和模型推理过程不得直接写入报告。对应内容应分别转换为“系统自动分析发现、行业通用标准、经系统验证、分析记录显示、多维度交叉分析、综合分析判断”等对外专业表述。</p>
      `
    },
    {
      id: 'rpt-2',
      title: '二、编制前提与判定可靠性',
      summary: '报告表述规范之前，必须先保证分析对象、数据方向和适用分析域均正确。',
      body: `
        <ol class="rpt-steps">
          <li><b>身份锚定：</b>锁定公司名称、统一社会信用代码、分析期间和数据来源。身份锚定错误时，全部分析结果作废。</li>
          <li><b>文件识别与方向判定：</b>通过文件名、列头、数据内容和公司身份四方交叉验证文件类型；进项、销项方向不得颠倒，存疑发票单独列示。</li>
          <li><b>行业锚定与域闸门：</b>依次核对工商登记、发票数据和加工信号。服务行业不得套用制造业实物商品分析域，混合行业应下沉到品名级区分。</li>
          <li><b>有效数据守卫：</b>只读取有效明细，排除空白行、小计、合计和汇总行；买卖双方均不含本公司名称的发票必须排除。</li>
          <li><b>全维度扫描与跨域协商：</b>各分析域独立运行后，对结论执行证据矛盾检测、资料完备度调整和多维联合增强。</li>
          <li><b>综合结论与分级：</b>根据证据强度、影响金额、规则来源和合法解释排除结果确定风险等级及处理建议。</li>
        </ol>
        <p><strong>七项可靠性底线：</strong>公司身份准确、发票方向有依据、文件类型经综合判断、只读有效信息、存疑数据已排除、行业闸门正确、混合业务达到品名级精度。任何一项未满足，相关发现不得进入正式结论。</p>
      `
    },
    {
      id: 'rpt-3',
      title: '三、事实、证据与逻辑链',
      summary: '每条发现用同一套六要素框架组织，并经过多源、时间和金额三类验证。',
      body: `
        <div class="rpt-flow"><span>事实 What</span><i>→</i><span>方法 How</span><i>→</i><span>证据 Evidence</span><i>→</i><span>法律 Why</span><i>→</i><span>影响 Impact</span><i>→</i><span>建议 Action</span></div>
        <p><strong>六要素要求：</strong>说明发现了什么事实、通过什么方法发现、有哪些可定位证据、涉及什么法律条款、可能产生多大税务影响以及建议如何处理。每条发现至少包含一个具体数值和一个时间锚点；证据须精确到发票号、账簿页码、合同条款、来源文件或原始行号。</p>
        <p><strong>三类事实验证：</strong>数据交叉验证要求发票、账簿、银行和申报数据中至少两个独立来源相互印证；时间轴验证要求交易、开票、收付款和履约时点符合业务逻辑；金额验证要求借贷平衡及发票、账簿、合同和资金口径能够勾稽。</p>
        <p><strong>递进逻辑：</strong>禁止从“现象”直接跳到“结论”，必须完整呈现“信号→推论→验证→合法解释排除→结论”。证据还须通过真实性、关联性和合法性三性校验；任一项不通过，只能列为待核实线索，不得写成正式结论。</p>
        <p><strong>全链路溯源：</strong>每条结论均应能够反向追踪至触发规则、调查线索、证据来源、原始文件和原始数据行，保证可复核、可审计、可对质。</p>
      `
    },
    {
      id: 'rpt-4',
      title: '四、报告结构与章节要求',
      summary: '统一采用“封面＋七章正文＋附件清单”，每部分都有固定职责。',
      body: `
        <div class="rpt-list">
          <div><b>封面</b><span>报告名称、被查单位、分析期间、报告编号和报告日期；编号采用“税稽字〔YYYY〕第XXX号”等统一格式。</span></div>
          <div><b>第一章·案件来源及基本情况</b><span>以表格列示案件来源、单位名称、信用代码、法定代表人、企业类型、实质行业、分析期间和分析范围。</span></div>
          <div><b>第二章·实施情况</b><span>按资料获取、身份行业判断、数据处理、分析方法、核查范围、质量控制和限制事项组织七个执行段落，整体不少于2000字；需要展开的方法段落原则上不少于400字。</span></div>
          <div><b>第三章·发现问题及事实认定</b><span>按六要素格式编写，高风险优先；同类风险合并但子项、证据和影响金额保持独立可追溯。</span></div>
          <div><b>第四章·综合结论</b><span>汇总风险分布、证据强度、总体影响和反向证据排除情况，避免重复抄写第三章。</span></div>
          <div><b>第五章·处理处罚建议</b><span>按P0立即处理、P1限期整改、P2持续关注分级，分别对应5、15、30个工作日的建议处理时限。</span></div>
          <div><b>第六章·告知权利义务</b><span>独立列示陈述申辩、申请回避、行政复议、行政诉讼及其他法定权利义务。</span></div>
          <div><b>第七章·人员签字</b><span>列示编制、复核、审批人员及日期，保留责任链。</span></div>
          <div><b>附件清单</b><span>至少包含销项发票、进项发票、主营成本发票、重大费用发票、银行流水汇总、资料文件清单和质量自检结果；生成证据关联关系图谱时作为第八项附件。</span></div>
        </div>
      `
    },
    {
      id: 'rpt-5',
      title: '五、风险归并、排序与处置分级',
      summary: '同类问题合并呈现，但不牺牲任何子项证据、金额或可追溯信息。',
      body: `
        <ol class="rpt-steps">
          <li><b>统一分组：</b>按规范化后的风险类型归组，去除内部前缀和无意义差异。</li>
          <li><b>等级取高：</b>合并后采用组内最高风险等级，不得因合并降低风险标记。</li>
          <li><b>标题标识：</b>明确显示同类风险数量和合并范围。</li>
          <li><b>子项独立：</b>每个子项保留事实、金额、税务影响和处理建议。</li>
          <li><b>证据归集：</b>合并全部证据明细、数据行、规则来源和链路信息。</li>
          <li><b>去重不丢失：</b>删除重复句和重复证据引用，但保留不同期间、主体和金额差异。</li>
          <li><b>统一结论：</b>父项形成综合法律分析和优先级，子项仍可单独复核。</li>
        </ol>
        <p>知识图谱、发票合规和资料缺失等容易产生大量同类发现的场景优先适用归并规则。处置建议统一分为：<strong>P0立即处理</strong>（原则上5个工作日）、<strong>P1限期整改</strong>（原则上15个工作日）和<strong>P2持续关注</strong>（原则上30个工作日或纳入后续监控）。</p>
      `
    },
    {
      id: 'rpt-6',
      title: '六、叙事、段落与格式规范',
      summary: '一段只表达一个主题，先写数据事实，再写分析方法，最后写专业判断。',
      body: `
        <p><strong>统一叙事句式：</strong>采用XX分析方法→核查XX数据→发现XX异常情况→分析可能产生的XX税务后果→提出XX查证或处理建议。第一、二章已经说明背景和实施过程，第三章直接从具体发现切入，避免重复铺陈。</p>
        <div class="rpt-list compact">
          <div><b>禁止一逗到底</b><span>多个完整逻辑句必须拆分，一段只表达一个中心意思。</span></div>
          <div><b>禁止多逻辑挤在同段</b><span>不同分析域、税种、主体或期间的内容分别成段。</span></div>
          <div><b>禁止括号堆叠</b><span>括号只用于简短补充，不能承载完整判定链。</span></div>
          <div><b>子项独立成段</b><span>合并风险下的每个子项均使用独立段落，便于复核。</span></div>
          <div><b>数据与解释分层</b><span>先陈述客观数据，再说明分析过程，最后给出结论和建议。</span></div>
        </div>
        <p><strong>段落自检：</strong>每段能否用一句话概括主旨？是否混入两个以上无关主题？超过200字后是否应拆分？全篇是否保持客观第三人称、时间口径统一、金额单位统一和编号连续？</p>
      `
    },
    {
      id: 'rpt-7',
      title: '七、质量控制与审核闭环',
      summary: '先验证分析成立，再检查报告表达；两类质量控制不能互相替代。',
      body: `
        <div class="rpt-flow"><span>文本净化</span><i>→</i><span>可靠性校验</span><i>→</i><span>12项质量检查</span><i>→</i><span>建议增强</span><i>→</i><span>二次净化</span></div>
        <p><strong>文本净化：</strong>清除模板句、重复句、空描述、空占位符和内部技术表述。<strong>可靠性校验：</strong>检查身份、方向、行业、有效数据、存疑排除和证据三性；分析不成立时，表述再规范也不得进入正式报告。</p>
        <div class="rpt-grid">
          <span><b>1 模板句清除</b>不得使用无事实支撑的泛化模板句</span>
          <span><b>2 重复句合并</b>相似内容统一表达</span>
          <span><b>3 空描述删除</b>不得保留“无、暂无、—”占位结论</span>
          <span><b>4 专业可读</b>内部技术参数转为外部专业语言</span>
          <span><b>5 六要素完整</b>事实、方法、证据、法律、影响、建议齐全</span>
          <span><b>6 法律引用准确</b>法条现行有效并含条款号</span>
          <span><b>7 具体数值</b>每条发现至少包含一个有效数值</span>
          <span><b>8 因果链完整</b>不存在“现象→结论”跳跃</span>
          <span><b>9 建议可执行</b>包含查证路径、责任动作和时间要求</span>
          <span><b>10 条款号完整</b>规程和法律引用可核对</span>
          <span><b>11 防跨企业复制</b>主体、期间和数据均来自当前账套</span>
          <span><b>12 占位符清零</b>正式交付内容不残留模板变量</span>
        </div>
        <p><strong>建议增强：</strong>对证据充分但处置路径不清的发现，补充查证步骤、时限、金额参照、法律依据及正常/异常分支处理。增强后再次净化，防止产生新的模板句或内部标记。</p>
      `
    },
    {
      id: 'rpt-8',
      title: '八、跨域协同与一致性约束',
      summary: '所有分析结果必须在同一企业、同一期间和同一证据体系内保持自洽。',
      body: `
        <p>跨域协商按固定顺序执行：<strong>行业闸门判定→资料完备度驱动→证据矛盾检测→多维度联合增强</strong>。协商结果分为四类：⛔消解（推翻不适用发现）、🔄调整（降低或修正等级）、ℹ️标记（补充资料受限说明）、🔴增强（多域同向证据叠加升级）。全过程保留审计记录。</p>
        <p><strong>系统铁律与报告质量映射：</strong>科目名称准确、凭证编号合并一致、审计结论可溯源、引用编号去重、普通发票税额按适用规则计入成本、分类不得随意兜底、规则与代码同步、代码实现与对外承诺一致、行业适用边界明确、关联修改同步更新、方法论先行。违反任一铁律，都可能形成致命质量缺陷。</p>
      `
    },
    {
      id: 'rpt-9',
      title: '九、交付、一致性与持续改进',
      summary: '交付前完成同步、验证和分级放行；退修结果继续反哺编制规则。',
      body: `
        <p><strong>一致性保障：</strong>系统在手动同步、服务启动、版本提交和分析管线启动等节点执行一致性检查。运行模式包括纯审计（只报告差异）、同步修复（自动更新可安全修复项）和基准校正（权威数据源变化后重新统计）。</p>
        <div class="rpt-duo three">
          <div class="rpt-card ok"><b>绿色交付</b><span>同步完成、全部检查通过，可正式交付。</span></div>
          <div class="rpt-card warn"><b>黄色交付</b><span>存在已知但不阻断的差异，必须在限制事项中披露。</span></div>
          <div class="rpt-card bad"><b>红色阻断</b><span>身份、方向、证据或数据一致性存在严重问题，禁止交付。</span></div>
        </div>
        <p><strong>审核反馈闭环：</strong>所有退修记录按证据不足、程序不合规、定性错误、法律适用不当、表述不规范和计算错误分类。系统对退修类型进行聚类，更新案例库、质量规则和编制提示，防止同类问题再次出现。</p>
      `
    },
    {
      id: 'rpt-10',
      title: '十、语音播报与阅读体验',
      summary: '播报是报告交付的一部分，不能改变原文含义，也不能掩盖段落结构问题。',
      body: `
        <p>报告支持全文播报和点击段落播报，并提供暂停、继续、停止、语速调节、当前段落高亮和自动滚动。优先采用中文男声；不可用时依次降级为其他中文男声或中文语音，确保可访问性。</p>
        <p><strong>六类语调：</strong>章节标题使用较慢、较低音调；小节标题略快；高风险内容保持严肃低沉；法律条文放慢并清晰断句；处理建议使用明确稳定语调；普通叙述保持自然速度。播报前须完成段落拆分和标点检查，禁止用语音停顿弥补文字结构缺陷。</p>
      `
    }
  ];

  var toc = sections.map(function(section) {
    return '<a href="#' + section.id + '">' + section.title.replace(/^[一二三四五六七八九十]+、/, '') + '</a>';
  }).join('');

  var content = sections.map(function(section) {
    return '<section id="' + section.id + '" class="rpt-section">'
      + '<h2>' + section.title + '</h2>'
      + '<p class="rpt-summary">' + section.summary + '</p>'
      + section.body
      + '</section>';
  }).join('');

  container.innerHTML = `
    <style>
      .rpt-unified{max-width:1180px;margin:0 auto;padding:34px 42px 56px;background:#fff;color:#3f4a5a;font:14px/1.9 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif}
      .rpt-unified *{box-sizing:border-box}
      .rpt-title{margin:0 0 8px;color:#14213a;font-size:26px;line-height:1.35;font-weight:800}
      .rpt-lead{margin:0 0 30px;color:#64748b;font-size:14px}
      .rpt-layout{display:flex;gap:40px;align-items:flex-start}
      .rpt-toc{position:sticky;top:18px;width:180px;flex:0 0 180px;max-height:calc(100vh - 36px);overflow:auto;padding:10px 0;border-right:1px solid #e7edf4}
      .rpt-toc b{display:block;margin:0 0 8px;padding-left:12px;color:#94a3b8;font-size:12px;letter-spacing:.14em}
      .rpt-toc a{display:block;padding:6px 14px;color:#64748b;text-decoration:none;border-left:3px solid transparent;line-height:1.5}
      .rpt-toc a:hover{color:#0e7490;border-left-color:#0e7490;background:#f7fbfc}
      .rpt-content{min-width:0;flex:1}
      .rpt-section{margin:0 0 42px;scroll-margin-top:18px}
      .rpt-section h2{margin:0 0 7px;color:#16233a;font-size:19px;line-height:1.45}
      .rpt-summary{margin:0 0 16px;padding:0 0 12px;color:#64748b;border-bottom:1px solid #e9eef4}
      .rpt-section p{margin:0 0 13px;text-align:justify}
      .rpt-section strong,.rpt-section b{color:#25364b}
      .rpt-duo{display:flex;gap:12px;margin:14px 0 18px}
      .rpt-duo.three .rpt-card{flex-basis:0}
      .rpt-card{flex:1;padding:13px 15px;border:1px solid #dbe5ef;border-radius:9px;background:#fbfdff}
      .rpt-card b{display:block;margin-bottom:5px}
      .rpt-card span{display:block;color:#64748b}
      .rpt-card.ok{border-color:#bbf7d0;background:#f6fef9}.rpt-card.ok b{color:#087f5b}
      .rpt-card.warn{border-color:#fde68a;background:#fffdf3}.rpt-card.warn b{color:#a16207}
      .rpt-card.bad{border-color:#fecaca;background:#fff8f8}.rpt-card.bad b{color:#c92a2a}
      .rpt-steps{margin:10px 0 18px;padding:0;list-style:none;counter-reset:rpt-step}
      .rpt-steps li{position:relative;margin:0 0 10px;padding-left:34px;counter-increment:rpt-step}
      .rpt-steps li:before{content:counter(rpt-step);position:absolute;left:0;top:3px;width:22px;height:22px;border-radius:50%;background:#e8f5f7;color:#0e7490;font-size:12px;font-weight:700;text-align:center;line-height:22px}
      .rpt-flow{display:flex;flex-wrap:wrap;align-items:center;gap:7px;margin:12px 0 18px}
      .rpt-flow span{padding:6px 11px;border-radius:15px;background:#edf8fa;color:#0e7490;font-weight:700}
      .rpt-flow i{color:#b7c4d1;font-style:normal}
      .rpt-list{margin:10px 0 18px}
      .rpt-list>div{display:grid;grid-template-columns:210px 1fr;gap:12px;padding:9px 0;border-bottom:1px dashed #e5ebf1}
      .rpt-list.compact>div{grid-template-columns:180px 1fr}
      .rpt-list span{color:#5e6b7b}
      .rpt-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 16px;margin:14px 0 18px}
      .rpt-grid span{padding:10px 12px;border:1px solid #e4eaf1;border-radius:8px;background:#fafcfe;color:#5e6b7b}
      .rpt-grid b{display:block;margin-bottom:3px}
      @media(max-width:800px){.rpt-unified{padding:24px 20px}.rpt-layout{display:block}.rpt-toc{position:static;width:auto;max-height:none;border-right:0;border-bottom:1px solid #e7edf4;margin-bottom:26px}.rpt-toc a{display:inline-block}.rpt-duo{display:block}.rpt-card{margin-bottom:9px}.rpt-list>div,.rpt-list.compact>div{grid-template-columns:1fr;gap:2px}.rpt-grid{grid-template-columns:1fr}}
    </style>
    <div class="rpt-unified">
      <h1 class="rpt-title">报告编制要求</h1>
      <p class="rpt-lead">本页是一套统一的报告编制体系。原“编制要求”和“报告规范”中的重复内容已合并，独有要求已按编制流程重新归位，不再保留两套章节或拼接式结构。</p>
      <div class="rpt-layout">
        <nav class="rpt-toc"><b>编制目录</b>${toc}</nav>
        <main class="rpt-content">${content}</main>
      </div>
    </div>
  `;

  if (window._reportSection) {
    var aliases = {
      'rs-1': 'rpt-4',
      'rs-2': 'rpt-1',
      'rs-3': 'rpt-3',
      'rs-4': 'rpt-5',
      'rs-5': 'rpt-7',
      'rs-6': 'rpt-2',
      'rs-7': 'rpt-6',
      'rs-8': 'rpt-10',
      'rs-9': 'rpt-9'
    };
    var targetId = aliases[window._reportSection] || window._reportSection;
    window._reportSection = null;
    var target = document.getElementById(targetId);
    if (target) target.scrollIntoView({block: 'start'});
  }
}
