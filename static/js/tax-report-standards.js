// ==================== 报告编制要求（编审一体单页版） ====================

var REPORT_SECTION_ALIASES = {
  requirements: 'rpt-1',
  review: 'rpt-8',
  'feedback-template': 'rpt-8',
  'report-spec': 'rpt-7',
  'rs-1': 'rpt-7',
  'rs-2': 'rpt-1',
  'rs-3': 'rpt-3',
  'rs-4': 'rpt-7',
  'rs-5': 'rpt-10',
  'rs-6': 'rpt-2',
  'rs-7': 'rpt-7',
  'rs-8': 'rpt-10',
  'rs-9': 'rpt-10'
};

function _reportTargetSection() {
  var requested = window._reportSection || window._reportStandardsSection || '';
  window._reportSection = null;
  window._reportStandardsSection = null;
  return REPORT_SECTION_ALIASES[requested] || requested;
}

function renderReportStandards(container) {
  if (!container) return;
  window.currentModule = '报告编制要求';

  var sections = [
    {
      id: 'rpt-1',
      kicker: '01',
      title: '职责、文种与法律边界',
      summary: '先确认“由谁、为谁、基于什么权限、形成哪一种文件”，再决定措辞和必备内容。',
      body: `
        <div class="rpt-callout critical"><b>边界先行</b><span>系统可以整理事实、证据、分析路径、测算结果和待核事项，但不能代替有权机关作出立案、违法认定、行政处理处罚、移送司法或司法裁判。未经法定程序，不得把风险信号写成终局结论。</span></div>
        <div class="rpt-grid three">
          <div class="rpt-card"><b>风险分析报告</b><span>用于内部筛查和安排核验任务。可以写“异常、差异、待核”，不得写成已经认定的违法事实。</span></div>
          <div class="rpt-card"><b>检查工作底稿或检查报告</b><span>按实际授权、程序和单位制度编制，区分已查明事实、专业判断、当事人意见和未解决事项。</span></div>
          <div class="rpt-card"><b>法定执法文书</b><span>只能由有权主体依现行程序制作。文号、章节、告知、签章和送达要求以适用的法定文书规范为准。</span></div>
        </div>
        <p><strong>四项开篇声明：</strong>报告目的与使用人、对象与期间、资料和方法范围、限制事项与责任边界。文种不明、授权不明或读者范围不明时，页面只能形成内部草稿。</p>
        <p><strong>用语分层：</strong>客观事实使用“资料显示、经核对”；分析判断使用“存在差异、与正常逻辑不一致、尚需核实”；建议使用“建议补充、建议复核”。只有在适用文种、权限、程序和证据均允许时，才使用具有法定含义的定性词。模型推理过程、密钥、内部参数、代码位置和系统日志不得进入对外交付文本。</p>
      `
    },
    {
      id: 'rpt-2',
      kicker: '02',
      title: '编制启动与输入门禁',
      summary: '报告不是从写第一段开始，而是从锁定主体、期间、口径、资料和责任人开始。',
      body: `
        <ol class="rpt-steps">
          <li><b>任务卡：</b>记录任务来源、授权范围、文种、使用目的、读者、保密等级、版本和计划完成日期。</li>
          <li><b>主体卡：</b>核对名称、统一社会信用代码、纳税人身份、所属行业、经营模式、关联主体和适用地域。</li>
          <li><b>期间卡：</b>区分业务发生期、会计期间、纳税所属期、资料覆盖期和政策有效期，禁止用一个日期代替全部期间。</li>
          <li><b>资料卡：</b>建立原始文件目录，记录来源、取得方式、哈希或版本、页码/行号、解析状态及资料缺口。</li>
          <li><b>口径卡：</b>明确含税或不含税、权责发生或收付实现、币种、单位、舍入、抽样范围和合并抵销规则。</li>
          <li><b>责任卡：</b>明确编制、业务复核、证据复核、法律复核、金额复核和最终批准人员；不相容职责按实际制度分离。</li>
        </ol>
        <div class="rpt-callout stop"><b>启动停点</b><span>主体或期间无法锁定、资料来源不可定位、关键口径冲突、适用身份不明或授权不足时，不生成正式报告；只输出缺口清单、影响说明和补充路径。</span></div>
      `
    },
    {
      id: 'rpt-3',
      kicker: '03',
      title: '单项发现的七联单',
      summary: '每条发现都是一个可独立复核的最小单元，正文、底稿、证据和计算之间使用同一编号。',
      body: `
        <div class="rpt-flow"><span>状态</span><i>→</i><span>事实</span><i>→</i><span>证据</span><i>→</i><span>分析</span><i>→</i><span>依据</span><i>→</i><span>影响</span><i>→</i><span>行动</span></div>
        <div class="rpt-list">
          <div><b>1 状态与结论层级</b><span>标记为线索、待核事实、专业判断或已确认事项，并写明证据成熟度和未决条件。</span></div>
          <div><b>2 客观事实</b><span>回答谁、何时、做了什么、涉及何种业务；能量化的写金额、数量和占比，不能量化的说明性质及影响范围。</span></div>
          <div><b>3 支持与反向证据</b><span>同时列示支持材料、相反材料、缺失材料和精确定位信息，不选择性忽略合理解释。</span></div>
          <div><b>4 分析与排除过程</b><span>呈现“信号→核验→竞争性解释→排除或保留→判断”，禁止从阈值命中直接跳到结论。</span></div>
          <div><b>5 法律与规则依据</b><span>注明规范全称、文号、条款、效力和适用期间；内部规则只能解释筛查方法，不能充当执法依据。</span></div>
          <div><b>6 金额或影响</b><span>区分已核金额、估算金额和无法量化影响，列示公式、参数、税率来源、调整项及不确定区间。</span></div>
          <div><b>7 行动与责任</b><span>写明补什么资料、由谁复核、判断分支、完成条件和下一决策点；时限由法定要求、案件计划或单位制度确定。</span></div>
        </div>
        <p><strong>去重规则：</strong>同一事实、同一期间、同一法理的发现归并为父项；不同主体、期间、税费种、证据状态或计算口径保留为独立子项。正文去重，附件保留完整明细和原始编号。</p>
      `
    },
    {
      id: 'rpt-4',
      kicker: '04',
      title: '证据组织与全链路溯源',
      summary: '证据数量不是机械门槛；证明力取决于真实性、关联性、合法性以及对待证事实的覆盖程度。',
      body: `
        <div class="rpt-grid">
          <div class="rpt-card"><b>真实性</b><span>核验来源主体、形成时间、原始载体、完整性、签章或电子校验信息，区分原件、复制件、导出数据和模型提取值。</span></div>
          <div class="rpt-card"><b>关联性</b><span>说明该材料证明哪个待证事实、覆盖哪一期间和金额，避免“附件很多但与结论无对应关系”。</span></div>
          <div class="rpt-card"><b>合法性</b><span>记录取得主体、权限、方式和程序；依法不得作为认定依据的材料不得通过技术加工“洗白”。</span></div>
          <div class="rpt-card"><b>充分性</b><span>按事项重要性和证据风险决定是否需要多源印证。单一材料能够充分证明时说明理由；来源受限时降级并披露限制。</span></div>
        </div>
        <p><strong>双向索引：</strong>发现编号→待证事实→证据编号→原文件页码/行号；证据编号也能反查其支持或反驳的全部发现。截图、摘录和结构化字段不得脱离原始材料单独保存。</p>
        <p><strong>证据冲突：</strong>不通过简单“多数表决”消解。比较形成时间、来源独立性、取得程序、业务链位置和可验证性；不能消解的冲突写入限制事项并交由人工复核。</p>
      `
    },
    {
      id: 'rpt-5',
      kicker: '05',
      title: '法律适用与时效核验',
      summary: '法条字段不是装饰；每次交付都要重新核验效力、期间、地域、主体和程序。',
      body: `
        <div class="rpt-table-wrap"><table class="rpt-table">
          <thead><tr><th>核验维度</th><th>必须记录</th><th>常见错误</th></tr></thead>
          <tbody>
            <tr><td>规范身份</td><td>发布机关、全称、文号、条款及权威来源</td><td>只写简称、转载标题或系统内部规则号</td></tr>
            <tr><td>效力与期间</td><td>施行、修改、废止、过渡条款及行为发生时点</td><td>用当前规则评价历史期间，或把征求意见稿当现行依据</td></tr>
            <tr><td>主体与地域</td><td>纳税人身份、业务类型、属地和特别适用条件</td><td>把区域裁量基准、行业口径或优惠条件跨范围套用</td></tr>
            <tr><td>规则层级</td><td>区分法律法规、规章、规范性文件、裁量基准和办税口径</td><td>以裁量基准替代上位法依据，或把办税指引当定性依据</td></tr>
            <tr><td>实体与程序</td><td>分别说明实体义务、取证程序、告知听证和救济要求</td><td>只论税额和责任，不核对程序权利</td></tr>
          </tbody>
        </table></div>
        <p><strong>引用规则：</strong>正文写与本事项直接相关的依据和适用理由，完整条文或检索记录放入附件。法律状态不确定时标记“待法律复核”，不得由模型补全条款。高影响事项至少由具备相应职责的人员复核权威来源、适用期间和具体条款。</p>
      `
    },
    {
      id: 'rpt-6',
      kicker: '06',
      title: '金额测算、时间轴与勾稽',
      summary: '测算表必须让未参与编制的人能够独立复算，并能看见差异来自数据、口径还是法律判断。',
      body: `
        <div class="rpt-list compact">
          <div><b>基础数据层</b><span>原始金额、币种、含税状态、所属期、来源编号和纳入/排除理由。</span></div>
          <div><b>参数层</b><span>税率或征收率、扣除比例、计税方法、汇率、舍入和参数的权威来源及有效期。</span></div>
          <div><b>公式层</b><span>计算步骤、调整项、抵减项、已申报已缴金额、差异金额和可复算表达式。</span></div>
          <div><b>结论层</b><span>区分账面差异、申报差异、估算影响、拟调整额和经有权程序确认的金额。</span></div>
        </div>
        <p><strong>四条时间线：</strong>合同履行、货物或服务交付、开票、收付款与会计税务处理分别排列，再解释错期、预收预付、退款红冲、分期结算和期后调整。日期差异本身只触发核验。</p>
        <p><strong>勾稽顺序：</strong>先统一主体、期间、币种和含税口径，再核对账簿—发票—财务报表—申报—资金。差异表应包含双方口径、差额、原因、证据、处理状态和责任人。重大测算实行独立复算或交叉复核。</p>
      `
    },
    {
      id: 'rpt-7',
      kicker: '07',
      title: '成稿结构、叙事与呈现',
      summary: '结构按文种和任务配置，以功能完整为标准，不把固定章数、字数、编号或时限写成普遍规则。',
      body: `
        <div class="rpt-grid">
          <div class="rpt-card"><b>元信息与摘要</b><span>标题、对象、期间、文种、版本、密级、编制日期；摘要只呈现范围、主要事项、总体影响和关键限制。</span></div>
          <div class="rpt-card"><b>任务范围与方法</b><span>说明授权、资料、抽样、分析方法、完成程序和未实施程序，让读者知道报告覆盖什么、没有覆盖什么。</span></div>
          <div class="rpt-card"><b>发现与综合分析</b><span>按重要性、税费种或业务链组织七联单；综合部分解释关联关系和总体影响，不重复抄写单项事实。</span></div>
          <div class="rpt-card"><b>行动、权利与附件</b><span>行动建议、责任与完成条件；法定权利义务仅在文种和程序要求适用时列示。附件含证据、计算、差异和限制清单。</span></div>
        </div>
        <p><strong>段落公式：</strong>主题句→关键事实→证据定位→分析和反向解释→影响→下一行动。一段只解决一个问题；数据先于判断，事实与意见分栏或分段，简称首次出现时给出全称。</p>
        <p><strong>格式统一：</strong>标题层级、编号、金额单位、日期、币种、百分比、小数位、表格表头、图例、脚注和附件引用全篇一致。不得残留占位符、模型提示、内部评分、技术报错、无事实模板句或跨账套内容。</p>
        <p><strong>可访问性：</strong>报告应支持打印、导出、键盘浏览和清晰朗读。播报或摘要只能忠实转换已批准文本，不得省略限制事项、反向证据或不确定性。</p>
      `
    },
    {
      id: 'rpt-8',
      kicker: '08',
      title: '审核嵌入编制，而不是另设模板页',
      summary: '原“审核模板”的有效要求已经分布到每条发现和每个放行门；本节只定义统一复核记录。',
      body: `
        <div class="rpt-flow"><span>编制自检</span><i>→</i><span>事实证据复核</span><i>→</i><span>法律与金额复核</span><i>→</i><span>对抗性复核</span><i>→</i><span>批准放行</span></div>
        <div class="rpt-table-wrap"><table class="rpt-table">
          <thead><tr><th>复核字段</th><th>填写要求</th><th>允许状态</th></tr></thead>
          <tbody>
            <tr><td>复核处置</td><td>对本条发现给出明确处理结果，不用“基本同意”等模糊词</td><td>通过 / 修改后通过 / 退回 / 待补证 / 不适用</td></tr>
            <tr><td>具体缺陷</td><td>指出错误落在哪个事实、证据、推理、法条、金额、程序或表述位置</td><td>必须定位到发现编号和字段</td></tr>
            <tr><td>正确逻辑</td><td>写明应采用的判断步骤、适用条件、退出条件及影响范围</td><td>不得只给结论</td></tr>
            <tr><td>待补证据</td><td>列明材料名称、证明目的、来源、期间和取得责任人</td><td>补证前保持待核状态</td></tr>
            <tr><td>依据与口径</td><td>核验法律效力、计算参数、数据范围和正常解释</td><td>不确定项单独升级复核</td></tr>
            <tr><td>修改与责任链</td><td>保留修改前后文本、修改人、复核人、时间、理由和版本</td><td>可追溯、可撤销、可比较</td></tr>
          </tbody>
        </table></div>
        <div class="rpt-callout"><b>审核意见示例骨架</b><span>【处置】待补证；【缺陷】现有资料只能证明收款与开票存在差额，尚不能证明差额性质；【正确逻辑】先按对手方和摘要区分经营款、借款、注资、退款与往来，再与合同、账簿和申报勾稽；【待补证据】差额明细、合同、记账凭证及资金性质说明；【依据/口径】补证后重新核验适用期间规则和测算口径。</span></div>
      `
    },
    {
      id: 'rpt-9',
      kicker: '09',
      title: '常见误判的归因与复核矩阵',
      summary: '原20个场景按误判根因归并，不把个案答案、行业经验或静态法条固化成通用结论。',
      body: `
        <div class="rpt-table-wrap"><table class="rpt-table">
          <thead><tr><th>误判根因</th><th>覆盖的典型现象</th><th>进入报告前必须复核</th></tr></thead>
          <tbody>
            <tr><td>对象、身份或行业错配</td><td>一般/小规模身份错用；服务业套用进销存；行业阈值直接照搬</td><td>登记与申报身份、实质业务、品名结构、合同履行及适用分析域</td></tr>
            <tr><td>数据范围或分类错误</td><td>全部银行收入等同销售；个人往来、注资、借款、补贴和代垫未分类；资料缺失被当成否定事实</td><td>逐笔资金性质、数据去重、完整性、来源覆盖和未提交资料的影响</td></tr>
            <tr><td>时间与经营节奏未解释</td><td>预付/赊购票款错期；项目制收入波动；季节性集中开票；大型客户账期较长</td><td>合同节点、履约、开票、收付、历史同期、行业周期和期后结算</td></tr>
            <tr><td>交易实质与正常解释遗漏</td><td>客户供应商重叠、供应商集中、红冲、关联人员往来、咨询服务被直接定性</td><td>双向业务内容、商业目的、交付物、定价、重开对应、资金闭环和独立第三方信息</td></tr>
            <tr><td>税务口径或法定例外错用</td><td>差额计税、非日常收入、扣缴义务、社保人员范围、税前扣除条件被一刀切</td><td>纳税人和交易身份、适用期间政策、属地要求、例外条件、申报资料及权威法律来源</td></tr>
          </tbody>
        </table></div>
        <p><strong>统一处理：</strong>场景库只提供“需要问什么、需要取什么证据”的反例索引，不提供自动免责或自动定性答案。任何相似案例都必须重新验证主体、期间、行业、业务实质、证据和现行法律。</p>
      `
    },
    {
      id: 'rpt-10',
      kicker: '10',
      title: '质量放行、版本交付与受控反馈',
      summary: '把内容质量、程序权利、版本责任和系统学习统一收口，形成可回退的交付闭环。',
      body: `
        <div class="rpt-checks">
          <span>主体、期间、文种与授权一致</span><span>事实、意见与法定认定已分层</span>
          <span>资料来源和证据链可双向定位</span><span>支持证据、反向证据与缺口均披露</span>
          <span>法律名称、文号、条款、效力和期间已核验</span><span>金额公式、参数和调整项可独立复算</span>
          <span>跨章节数字、名称、编号和等级一致</span><span>重大事项完成人工及对抗性复核</span>
          <span>程序权利和限制事项未被摘要省略</span><span>附件齐全且与正文逐项引用</span>
          <span>无占位符、内部信息、跨账套内容和绝对化措辞</span><span>版本、修改记录、签批和交付对象完整</span>
        </div>
        <div class="rpt-grid three release">
          <div class="rpt-card ok"><b>绿色放行</b><span>所有阻断项关闭，复核签批和交付包完整，可按批准范围交付。</span></div>
          <div class="rpt-card warn"><b>黄色受限</b><span>非关键缺口不会改变主要判断，已在醒目位置披露影响、责任人和补正计划。</span></div>
          <div class="rpt-card bad"><b>红色阻断</b><span>主体、证据、法律、金额、程序、高影响人工复核或数据隔离任一关键项未通过。</span></div>
        </div>
        <p><strong>交付包：</strong>批准版报告、证据索引、计算底稿、差异表、资料与限制清单、复核记录、版本变更单和必要的机器可读导出。交付后修改必须产生新版本，旧版只读留存，不得覆盖责任链。</p>
        <p><strong>受控反馈：</strong>单次审核意见先进入候选池，限定到原账套、发现类型、行业、经营模式和适用期间。只有完成复核、重复验证、冲突检查和版本审批后，才可扩大适用范围；自动应用只能增加审核标记或建议，不得删除原始事实、覆盖原风险等级或替代最终批准。错误规则必须能够停用、回退并追踪受影响报告。</p>
      `
    }
  ];

  var toc = sections.map(function(section) {
    return '<a href="#' + section.id + '"><span>' + section.kicker + '</span>' + section.title + '</a>';
  }).join('');

  var content = sections.map(function(section) {
    return '<section id="' + section.id + '" class="rpt-section">'
      + '<div class="rpt-section-kicker">' + section.kicker + '</div>'
      + '<h2>' + section.title + '</h2>'
      + '<p class="rpt-summary">' + section.summary + '</p>'
      + section.body
      + '</section>';
  }).join('');

  container.innerHTML = `
    <style>
      .rpt-unified{max-width:1380px;margin:0 auto;padding:24px;color:#344256;font:14px/1.88 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif}
      .rpt-unified *{box-sizing:border-box}
      .rpt-hero{position:relative;overflow:hidden;margin:0 0 14px;padding:30px 34px;border:1px solid #d8e7ea;border-radius:16px;background:linear-gradient(135deg,#f3fbfc 0%,#f8fafc 58%,#f3f7ff 100%)}
      .rpt-hero:after{content:"";position:absolute;right:-65px;top:-80px;width:240px;height:240px;border-radius:50%;background:rgba(14,116,144,.07)}
      .rpt-eyebrow{margin:0 0 8px;color:#0e7490;font-size:12px;font-weight:800;letter-spacing:.12em}
      .rpt-title{position:relative;z-index:1;margin:0 0 9px;color:#12213a;font-size:28px;line-height:1.35;font-weight:850}
      .rpt-lead{position:relative;z-index:1;max-width:980px;margin:0;color:#5d6b7c;font-size:14px;line-height:1.85}
      .rpt-stages{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin:0 0 18px}
      .rpt-stage{padding:10px 12px;border:1px solid #e2eaf0;border-radius:10px;background:#fff;color:#526174;font-size:12px;text-align:center}
      .rpt-stage b{display:block;color:#0e7490;font-size:13px}
      .rpt-layout{display:grid;grid-template-columns:228px minmax(0,1fr);gap:34px;align-items:start}
      .rpt-toc{position:sticky;top:18px;max-height:calc(100vh - 36px);overflow:auto;padding:12px 0;border:1px solid #e3eaf0;border-radius:12px;background:#fff}
      .rpt-toc-title{display:block;margin:0 14px 7px;padding:0 0 9px;border-bottom:1px solid #edf1f5;color:#94a3b8;font-size:11px;font-weight:800;letter-spacing:.14em}
      .rpt-toc a{display:flex;gap:8px;align-items:flex-start;padding:7px 14px;color:#5f6d7d;text-decoration:none;line-height:1.45;border-left:3px solid transparent}
      .rpt-toc a span{min-width:20px;color:#9aabba;font-size:10px;font-weight:800}
      .rpt-toc a:hover{color:#0e7490;border-left-color:#0e7490;background:#f4fafb}
      .rpt-content{min-width:0;padding:2px 0}
      .rpt-section{position:relative;margin:0 0 18px;padding:26px 30px;border:1px solid #e3e9ef;border-radius:14px;background:#fff;scroll-margin-top:18px}
      .rpt-section-kicker{position:absolute;right:24px;top:20px;color:#e2eaef;font-size:34px;font-weight:900;line-height:1}
      .rpt-section h2{position:relative;margin:0 0 7px;padding-right:45px;color:#17253b;font-size:20px;line-height:1.45}
      .rpt-summary{margin:0 0 18px;padding:0 48px 13px 0;color:#667588;border-bottom:1px solid #edf1f5}
      .rpt-section p{margin:0 0 13px;text-align:justify}
      .rpt-section strong,.rpt-section b{color:#263a50}
      .rpt-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:11px;margin:13px 0 18px}
      .rpt-grid.three{grid-template-columns:repeat(3,minmax(0,1fr))}
      .rpt-card{padding:14px 16px;border:1px solid #dfe7ee;border-radius:10px;background:#fafcfd}
      .rpt-card b{display:block;margin-bottom:5px;color:#21445a}
      .rpt-card span{display:block;color:#627183}
      .rpt-card.ok{border-color:#bbebd4;background:#f4fcf7}.rpt-card.ok b{color:#087f5b}
      .rpt-card.warn{border-color:#f5df99;background:#fffaf0}.rpt-card.warn b{color:#a16207}
      .rpt-card.bad{border-color:#f1c7c7;background:#fff7f7}.rpt-card.bad b{color:#b42318}
      .rpt-callout{display:flex;gap:12px;margin:13px 0 18px;padding:13px 16px;border-left:4px solid #0e7490;border-radius:7px;background:#f1fafb}
      .rpt-callout b{flex:0 0 106px;color:#0e7490}
      .rpt-callout span{color:#546577}
      .rpt-callout.critical{border-left-color:#b42318;background:#fff7f7}.rpt-callout.critical b{color:#b42318}
      .rpt-callout.stop{border-left-color:#a16207;background:#fffaf0}.rpt-callout.stop b{color:#a16207}
      .rpt-steps{margin:10px 0 18px;padding:0;list-style:none;counter-reset:rpt-step}
      .rpt-steps li{position:relative;margin:0 0 10px;padding:3px 0 3px 36px;counter-increment:rpt-step}
      .rpt-steps li:before{content:counter(rpt-step);position:absolute;left:0;top:3px;width:24px;height:24px;border-radius:50%;background:#e8f5f7;color:#0e7490;font-size:12px;font-weight:800;text-align:center;line-height:24px}
      .rpt-flow{display:flex;flex-wrap:wrap;align-items:center;gap:7px;margin:12px 0 19px}
      .rpt-flow span{padding:6px 11px;border-radius:16px;background:#eaf6f8;color:#0e7490;font-weight:750}
      .rpt-flow i{color:#afbdc9;font-style:normal}
      .rpt-list{margin:10px 0 18px}
      .rpt-list>div{display:grid;grid-template-columns:188px 1fr;gap:13px;padding:9px 0;border-bottom:1px dashed #e1e8ee}
      .rpt-list.compact>div{grid-template-columns:150px 1fr}
      .rpt-list span{color:#5b6a7b}
      .rpt-table-wrap{margin:13px 0 18px;overflow:auto;border:1px solid #e1e8ee;border-radius:10px}
      .rpt-table{width:100%;min-width:680px;border-collapse:collapse;background:#fff;font-size:13px}
      .rpt-table th{padding:10px 12px;background:#f2f7f9;color:#28465a;text-align:left;font-weight:750}
      .rpt-table td{padding:10px 12px;border-top:1px solid #e8edf2;vertical-align:top;color:#5a6878}
      .rpt-table td:first-child{color:#2b3d51;font-weight:650}
      .rpt-checks{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 16px;margin:13px 0 18px}
      .rpt-checks span{position:relative;padding:8px 12px 8px 32px;border:1px solid #e3e9ef;border-radius:8px;background:#fbfcfd;color:#59697a}
      .rpt-checks span:before{content:"✓";position:absolute;left:11px;color:#0e7490;font-weight:900}
      @media(max-width:1000px){.rpt-stages{grid-template-columns:repeat(2,minmax(0,1fr))}.rpt-layout{grid-template-columns:1fr}.rpt-toc{position:static;max-height:none;display:flex;flex-wrap:wrap;gap:3px;padding:10px}.rpt-toc-title{width:100%}.rpt-toc a{width:calc(50% - 2px);border-left:0}.rpt-grid.three{grid-template-columns:1fr}.rpt-grid.three.release{grid-template-columns:repeat(3,minmax(0,1fr))}}
      @media(max-width:720px){.rpt-unified{padding:14px}.rpt-hero{padding:23px 20px}.rpt-title{font-size:24px}.rpt-stages{grid-template-columns:1fr 1fr}.rpt-section{padding:22px 18px}.rpt-toc a{width:100%}.rpt-grid,.rpt-grid.three,.rpt-grid.three.release,.rpt-checks{grid-template-columns:1fr}.rpt-list>div,.rpt-list.compact>div{grid-template-columns:1fr;gap:2px}.rpt-callout{display:block}.rpt-callout b{display:block;margin-bottom:5px}.rpt-summary{padding-right:32px}}
    </style>
    <div class="rpt-unified" data-report-single-page="true">
      <header class="rpt-hero">
        <p class="rpt-eyebrow">单页融合 · 编审一体 · 证据驱动</p>
        <h1 class="rpt-title">📖 报告编制要求</h1>
        <p class="rpt-lead">本页把原“编制要求、报告规范、审核模板和典型误判场景”按报告生命周期真正融合为一套连续标准。审核不是末端挑错，而是嵌入事实、证据、法律、金额、成稿和交付的每一道门。</p>
      </header>
      <div class="rpt-stages" aria-label="报告编制闭环">
        <div class="rpt-stage"><b>1 启动</b>边界与输入</div>
        <div class="rpt-stage"><b>2 形成</b>事实与证据</div>
        <div class="rpt-stage"><b>3 论证</b>法律与金额</div>
        <div class="rpt-stage"><b>4 编审</b>成稿与复核</div>
        <div class="rpt-stage"><b>5 交付</b>放行与版本</div>
      </div>
      <div class="rpt-layout">
        <nav class="rpt-toc" aria-label="报告编制要求单页目录">
          <b class="rpt-toc-title">编制—审核—交付目录</b>${toc}
        </nav>
        <main class="rpt-content">${content}</main>
      </div>
    </div>
  `;

  var targetId = _reportTargetSection();
  if (targetId) {
    window.setTimeout(function() {
      var target = document.getElementById(targetId);
      if (target) target.scrollIntoView({block: 'start'});
    }, 0);
  }
}
