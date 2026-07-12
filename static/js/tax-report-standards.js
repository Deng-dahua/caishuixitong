// ==================== 报告编制总纲 —— 50年稽查经验凝结 ====================

function renderReportStandards(container) {
  if (!container) return;
  window.currentModule = '报告编制总纲';

  var h = '<style>'
    + '.rpt-layout{max-width:960px;margin:0 auto;padding:28px 20px 60px;font-family:"PingFang SC","Microsoft YaHei",sans-serif}'
    + '.rpt-h1{font-size:24px;font-weight:900;color:#0f172a;margin:0 0 4px;letter-spacing:1px}'
    + '.rpt-sub{font-size:13px;color:#94a3b8;margin:0 0 32px}'
    + '.rpt-chapter{margin-bottom:48px}'
    + '.rpt-ch-title{font-size:18px;font-weight:800;color:#1e293b;padding-bottom:12px;border-bottom:3px solid #1e293b;margin-bottom:20px;display:flex;align-items:center;gap:10px}'
    + '.rpt-ch-title .cn{display:inline-flex;align-items:center;justify-content:center;min-width:32px;height:32px;background:#1e293b;color:#fff;border-radius:6px;font-size:16px;font-weight:800}'
    + '.rpt-block{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:22px 26px;margin-bottom:16px;font-size:13px;line-height:2;color:#334155}'
    + '.rpt-block h4{font-size:14px;font-weight:700;color:#0f172a;margin:18px 0 8px}'
    + '.rpt-block h4:first-child{margin-top:0}'
    + '.rpt-em{background:#fef3c7;padding:2px 6px;border-radius:3px;font-weight:600;color:#92400e}'
    + '.rpt-bad{display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;margin-right:4px;vertical-align:2px}'
    + '.rpt-bad-r{background:#fee2e2;color:#dc2626}'
    + '.rpt-bad-b{background:#dbeafe;color:#2563eb}'
    + '.rpt-bad-g{background:#dcfce7;color:#16a34a}'
    + '.rpt-bad-y{background:#fef3c7;color:#d97706}'
    + '.rpt-flow{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:12px 0;font-size:12px}'
    + '.rpt-flow span{display:inline-block;padding:6px 14px;background:#f1f5f9;border-radius:6px;font-weight:600;color:#475569}'
    + '.rpt-flow span.act{background:#1e293b;color:#fff}'
    + '.rpt-flow .arr{color:#94a3b8;font-size:16px;margin:0 2px}'
    + '.rpt-table{width:100%;border-collapse:collapse;font-size:12px;margin:10px 0}'
    + '.rpt-table td{padding:8px 12px;border-bottom:1px solid #f1f5f9;vertical-align:top}'
    + '.rpt-table th{padding:8px 12px;background:#f8fafc;text-align:left;font-weight:600;color:#64748b;font-size:11px;border-bottom:2px solid #e2e8f0}'
    + '.rpt-rule{display:flex;gap:10px;align-items:flex-start;margin:6px 0;padding:10px 14px;background:#f8fafc;border-radius:6px;border-left:3px solid #e2e8f0}'
    + '.rpt-rule .rn{font-size:12px;font-weight:800;color:#1e293b;min-width:20px}'
    + '.rpt-rule .rc{font-size:12px;color:#475569;line-height:1.9}'
    + '.rpt-rule.fatal{border-left-color:#dc2626;background:#fef2f2}'
    + '.rpt-rule.high{border-left-color:#f59e0b;background:#fffbeb}'
    + '</style>';

  h += '<div class="rpt-layout">';
  h += '<h1 class="rpt-h1">报告编制总纲</h1>';
  h += '<p class="rpt-sub">五十载稽查生涯所悟——报告不是产品，是证据。以下内容为稽查局长毕生经验，已全部注入系统引擎。</p>';

  // ════════════════════════════════════════
  // 第一章：报告的本质
  // ════════════════════════════════════════
  h += '<div class="rpt-chapter">';
  h += '<div class="rpt-ch-title"><span class="cn">一</span>报告的本质：从数据异常到法律证据</div>';
  
  h += '<div class="rpt-block">';
  h += '<h4>报告不是产品，是证据链</h4>';
  h += '干了五十年稽查，我见过太多报告——有用没用的信息堆在一起，有结论没证据，有数据没分析，有引用没条款。这种报告送到审理环节，第一眼就被退回来。报告的终极目的只有一个：<span class="rpt-em">让一个没看过原始数据的人，读完报告后能独立判断这个案子要不要立、税要不要补、人要不要移送</span>。能做到这一点，报告就及格了。';
  h += '</div>';

  h += '<div class="rpt-block">';
  h += '<h4>报告的四大支柱</h4>';
  h += '任何一份合格的税务稽查报告，拆开来看就是四根柱子：<br>';
  h += '<b>第一柱·事实</b> —— 什么时候、谁、做了什么、涉及多少钱。没有具体数值的事实不叫事实，叫印象。每条发现必须含：日期或期间、主体名称（企业/个人全称）、具体金额、涉及数量。<br>';
  h += '<b>第二柱·证据</b> —— 这话谁说的？哪张票？哪条银行流水？哪个合同的第几条款？证据必须精确到可被第三方独立验证的程度。<br>';
  h += '<b>第三柱·逻辑</b> —— 从A到B到C的推导过程。不能跳步——"毛利率偏低→因此存在隐匿收入"中间少了至少两步。完整的逻辑链必须展示：异常现象→反推可能原因→逐一排除合法情形→剩余最可能原因→税务后果。<br>';
  h += '<b>第四柱·法律</b> —— 违反了哪个法的第几条？是行政处罚还是刑事责任？补税多少？罚款区间多少？移送标准是否达标？没有法律依据的结论只是个人意见，不是稽查结论。<br>';
  h += '四柱缺一不可。缺事实→报告空洞。缺证据→报告不可信。缺逻辑→报告武断。缺法律→报告无约束力。稽查局里带徒弟几十年，第一课永远是这四根柱子。';
  h += '</div>';

  h += '<div class="rpt-block">';
  h += '<h4>报告的语言立场：发现者，不是审判者</h4>';
  h += '稽查报告处于发现阶段——尚未经过被查单位陈述申辩、尚未经过审理部门复核、尚未进入法律裁决程序。因此报告用语必须体现"发现"而非"定性"：<br>';
  h += '<span class="rpt-bad rpt-bad-g">正确</span> 涉嫌 / 存疑 / 税务合规发现 / 可能存在 / 提示风险 / 经查<br>';
  h += '<span class="rpt-bad rpt-bad-r">禁止</span> 违法认定 / 确定 / 已查明 / 经核实确认 / 构成XX罪<br>';
  h += '原因很简单：预判法律结论属于程序违法。稽查阶段你只有发现的权力，没有定性的权力。定性是审理部门和法院的事。这条规矩我做了五十年从没破过——破了就是退回重写。';
  h += '</div>';
  h += '</div>';

  // ════════════════════════════════════════
  // 第二章：从数据到发现——六步铁律
  // ════════════════════════════════════════
  h += '<div class="rpt-chapter">';
  h += '<div class="rpt-ch-title"><span class="cn">二</span>发现生成：从数据异常到可定性的六步铁律</div>';

  h += '<div class="rpt-block">';
  h += '<h4>为什么六步——一步都不能少</h4>';
  h += '二十年带徒弟总结的教训：新手最常犯的错误是"跳步"——看到数据异常直接跳结论。毛利率偏低？隐匿收入！没有运输费？无货虚开！这种跳跃式思维在稽查中是致命的。每一步之间必须有证据桥接，中间断了就等于推理链断了。以下六步是稽查局内部培训标准，已全部注入系统引擎。';
  h += '</div>';

  h += '<div class="rpt-block">';
  h += '<h4>第一步·数据锚定</h4>';
  h += '做什么：确定分析对象——这家企业是谁（全称+信用代码）、分析期间是什么（起止年月）、数据来源是什么（上传文件清单）。<br>';
  h += '铁律：<span class="rpt-em">公司身份必须在报告第一段锚定</span>。锚定错了→后面所有分析全部作废→致命事故。<br>';
  h += '格式范例：被查单位"XX有限公司"（统一社会信用代码91440101XXXXXXXXXX），税务合规期间2024年1月至2024年12月。';

  h += '<h4>第二步·文件识别与方向判定</h4>';
  h += '做什么：识别上传文件的性质——哪份是销项、哪份是进项、哪份是银行流水——通过文件名+表头+内容+身份匹配四方交叉验证。<br>';
  h += '铁律：<span class="rpt-em">不得仅凭文件名判定文件类型</span>。四方冲突时以数据扫描结果为准，并说明判定依据。<br>';
  h += '进销方向判定：购买方=被查公司→进项；销售方=被查公司→销项。方向错→收入/成本全部颠倒→致命事故。存疑发票（买卖双方都不含公司）必须排除并记录原因。';

  h += '<h4>第三步·行业锚定与域闸门</h4>';
  h += '做什么：判定企业实质经营行业——工商登记行业≠发票推断行业≠实质经营行业——须三层穿透后综合判断。<br>';
  h += '铁律：<span class="rpt-em">服务行业（金税编码25类）不得出现进销存/制造业毛利率对标等实物域分析</span>。如果行业闸门已激活，必须在报告中声明跳过原因。<br>';
  h += '混合行业（服务+货物）必须品名级区分——混为一谈视为误判。';

  h += '<h4>第四步·全维度扫描</h4>';
  h += '做什么：29个域分析函数独立运行（各域之间暂不通信）——进销匹配、毛利率、费用率、资金流水比对、供应商客户重叠、发票合规、税负率、折旧摊销……<br>';
  h += '铁律：<span class="rpt-em">每个域的结论必须有代码支撑</span>。报告声称"已分析XX域"但代码中找不到对应函数→违规。';

  h += '<h4>第五步·跨域协商自洽</h4>';
  h += '做什么：29个域各自独立产出发现后，协商引擎统一消解矛盾。域A说"收款偏差52%→高风险"，域B说"行业=服务"→协商引擎消解域A的进销存异常。原则：一个结论。报告中的所有发现必须在同一个逻辑体系内自洽。<br>';
  h += '四种协商结果：⛔消解（推翻）→🔄调整（降级）→ℹ️标记（加注）→🔴联合增强（多域信号叠加升级）。';

  h += '<h4>第六步·结论生成与分级</h4>';
  h += '做什么：综合评分→风险分级（极高/高/中/低）→处理建议分级（P0立即处理/P1限期整改/P2持续关注）。<br>';
  h += '铁律：<span class="rpt-em">结论必须有方法论支撑</span>。每一个结论都能追溯到：发现←规则ID←线索链←证据链←原始数据行。不能追溯的结论不叫结论，叫猜测。';
  h += '</div>';

  h += '<div class="rpt-block">';
  h += '<h4>全链路执行顺序（不可调换）</h4>';
  h += '<div class="rpt-flow">'
    + '<span class="act">数据锚定</span><span class="arr">→</span>'
    + '<span>文件识别</span><span class="arr">→</span>'
    + '<span>行业判定</span><span class="arr">→</span>'
    + '<span>29域扫描</span><span class="arr">→</span>'
    + '<span class="act">跨域协商</span><span class="arr">→</span>'
    + '<span>方法过滤</span><span class="arr">→</span>'
    + '<span>综合评分</span><span class="arr">→</span>'
    + '<span class="act">报告生成</span>'
    + '</div>';
  h += '顺序不可调——先协商才能避免矛盾发现进入后续步骤；先过滤才能确保评分建立在已经净化后的发现体系上。';
  h += '</div>';
  h += '</div>';

  // ════════════════════════════════════════
  // 第三章：报告叙事——每一句话都要经得起追问
  // ════════════════════════════════════════
  h += '<div class="rpt-chapter">';
  h += '<div class="rpt-ch-title"><span class="cn">三</span>报告叙事：每一句话都要经得起追问</div>';

  h += '<div class="rpt-block">';
  h += '<h4>叙事铁律：第三人称 + 方法在前 + 数据具体</h4>';
  h += '<b>人称规范：</b>全篇使用"经查""该企业""被查单位"等客观第三人称。绝对禁止"我""你""我们""你们"。稽查报告是国家公文，不是聊天记录。<br>';
  h += '<b>叙事结构：</b>通过XX方法→核查了XX数据→发现XX异常→导致XX后果→建议从XX方面处理。不是"发现XX问题建议XX"，而是展示完整的核查过程。读者应该能从报告中复原你的每一步操作。<br>';
  h += '<b>数据颗粒度：</b>每条发现至少含1个具体数值（金额/百分比/数量）+1个时间锚点（期间/日期）。"存在较大偏差"不生硬——必须写"偏差52%""涉及金额423,605.31元""涉及32笔交易"。定性词必须有紧随其后的数值支撑。';
  h += '</div>';

  h += '<div class="rpt-block">';
  h += '<h4>发现的六要素统一格式</h4>';
  h += '每条发现按以下六要素组织，缺一不可。这不是模板，是最低标准——不够可以加，但不能少：<br>';
  h += '<span class="rpt-em">要素① 性质</span> —— 发现类型标题。一句话说清这是什么问题。<br>';
  h += '<span class="rpt-em">要素② 事实</span> —— 具体事实描述+明细数据。必须含供应商/客户名称、金额、发票号、品名、数量、日期。不允许"存在XX问题"这种无具体信息的表述。<br>';
  h += '<span class="rpt-em">要素③ 证据</span> —— 逐笔列示证据明细。发票对应的附件清单、银行流水的对应行号。items数组不截断、不缺斤短两。涉及多个实体的发现必须附带明细表。<br>';
  h += '<span class="rpt-em">要素④ 来源</span> —— 这条发现是谁发现的？规则ID（可点击溯源）+线索链编号+查证方式。每项发现的源头必须可追溯。<br>';
  h += '<span class="rpt-em">要素⑤ 法律</span> —— 完整法条名称+具体条款号。不得笼统写"相关税收法规"。格式：《XX法》第X条第X款。<br>';
  h += '<span class="rpt-em">要素⑥ 建议</span> —— 具体处理路径。格式："提供XX资料→如果A则做XX→如果B则做XX→无法做到的后果是XX"。禁止"请提供相关资料""请核实"等笼统表述。';
  h += '</div>';

  h += '<div class="rpt-block">';
  h += '<h4>段落格式：五条禁令</h4>';
  h += '<div class="rpt-rule"><span class="rn">①</span><span class="rc">禁止一逗到底——多个完整逻辑句子各自独立成段，不得用逗号/分号串联为一个整块段落。</span></div>';
  h += '<div class="rpt-rule"><span class="rn">②</span><span class="rc">禁止多逻辑挤一段——同段不得混杂2个以上不相关的分析维度。</span></div>';
  h += '<div class="rpt-rule"><span class="rn">③</span><span class="rc">禁止括号堆叠——不得用括号内堆砌多段判定逻辑链。</span></div>';
  h += '<div class="rpt-rule"><span class="rn">④</span><span class="rc">子项独立成段——"①②③④"引导的子项内容各自独立为一段。</span></div>';
  h += '<div class="rpt-rule"><span class="rn">⑤</span><span class="rc">数据与解释分层——先陈述数据事实（独立段）→再解释分析方法（独立段）→最后给出结论（独立段）。</span></div>';
  h += '拆分自检：每写完一段自问——这段只有一个主题吗？能用一句话概括主旨吗？超过200字了吗（超了就拆）。换主题=换段，换视角=换段，换分析对象=换段。';
  h += '</div>';
  h += '</div>';

  // ════════════════════════════════════════
  // 第四章：质量防线——四道闸门
  // ════════════════════════════════════════
  h += '<div class="rpt-chapter">';
  h += '<div class="rpt-ch-title"><span class="cn">四</span>质量防线：四道闸门确保报告铁板一块</div>';
  
  h += '<div class="rpt-block">';
  h += '<h4>闸门总览</h4>';
  h += '稽查报告在生成后经过四道闸门层层过滤。我们的系统不是"生成完就交付"——每份报告都走完这四道闸门才能发出。这四道闸门是我几十年审理报告总结出来的——哪里的报告最容易出问题，闸门就设在哪里。';
  h += '<div class="rpt-flow">'
    + '<span class="act">闸门一</span><span class="arr">→</span>'
    + '<span>文本净化</span><span class="arr">→</span>'
    + '<span class="act" style="background:#fef2f2;color:#dc2626">底层防线</span><span class="arr">→</span>'
    + '<span class="act">闸门二</span><span class="arr">→</span>'
    + '<span>质量标准检查</span><span class="arr">→</span>'
    + '<span class="act">闸门三</span><span class="arr">→</span>'
    + '<span>建议质量增强</span><span class="arr">→</span>'
    + '<span class="act">闸门四</span><span class="arr">→</span>'
    + '<span>二次净化</span>'
    + '</div>';
  h += '<span class="rpt-em">执行顺序不可逆：</span>底层防线是闸门二的前置条件——先过底层防线（分析不成立的发现直接打回重新分析），再过闸门二（表述检查）。如果底层防线未通过却进入闸门二，会出现"表述合格但分析不成立"的发现流入后续环节。</div>';

  h += '<div class="rpt-block">';
  h += '<h4>闸门一：文本净化</h4>';
  h += '自动清除四类垃圾内容：<br>';
  h += '① 模板句——识别并移除"是税务合规重点方向""需逐笔核实""请核实并提供相关佐证材料""申报不合规是税务行政处罚的常见案由"等8类预定义模板句。<br>';
  h += '② 空描述——type字段为空或detail不足10字符的发现标记无效。<br>';
  h += '③ 重复句——同一finding内出现≥2次完全相同的句子（长度>30字符），只保留首次。<br>';
  h += '④ 空占位符——清理自动填充失效残留如"如：()""()；()；()"等。<br>';
  h += '净化后约70%的格式问题自动修复。';
  h += '</div>';

  h += '<div class="rpt-block">';
  h += '<h4>底层防线：分析可靠性要求（闸门二前置条件，不可跳过）</h4>';
  h += '质量标准检测的是"表述是否正确"，可靠性要求检测的是"<span class="rpt-em">分析本身是否成立</span>"。底层防线是闸门二的前置条件——分析不成立的发现直接打回重新分析，不得流入闸门二。顺序不可逆。';
  h += '<h4>证据三性校验（报告生成时落地执行）</h4>';
  h += '每条发现入报告前须通过三性校验：<br>';
  h += '<b>真实性</b> — 数据来源是否可追溯至原始上传文件的具体行号？不可追溯的证据标记为"待核实"，不入正式结论。<br>';
  h += '<b>关联性</b> — 每一项证据是否直接服务于当前发现的认定？旁证、间接证据、可作多种解释的证据，需标注关联强度（直接/间接/参考）。<br>';
  h += '<b>合法性</b> — 取证路径是否合规？数据是否仅为用户授权上传、未跨企业比对？违规取证路径的数据不得作为证据使用。<br>';
  h += '三性校验不通过的证据，在发现底部标注"⚠ 三性未通过：原因"，该发现降级至"线索"等级。';
  h += '<h4>致命级和高风险级可靠性要求</h4>';
  h += '<div class="rpt-rule fatal"><span class="rn">致命</span><span class="rc"><b>公司身份锚定</b>——报告开头必须声明公司名称+信用代码。锚定错误→全部分析作废。</span></div>';
  h += '<div class="rpt-rule fatal"><span class="rn">致命</span><span class="rc"><b>发票方向判定</b>——进项/销项分类须有判定依据。方向错→收入成本颠倒。</span></div>';
  h += '<div class="rpt-rule fatal"><span class="rn">致命</span><span class="rc"><b>综合判断</b>——文件类型须经四方交叉验证，不得仅凭文件名判定。</span></div>';
  h += '<div class="rpt-rule high"><span class="rn">高风险</span><span class="rc"><b>只读有效信息</b>——所有统计基于有效行，排除空白行/小计行/合计行。Excel行数≠有效数据量。</span></div>';
  h += '<div class="rpt-rule high"><span class="rn">高风险</span><span class="rc"><b>存疑排除</b>——买卖双方都不含公司的发票必须排除出所有计算。A公司数据污染B公司=跨账套污染。</span></div>';
  h += '<div class="rpt-rule high"><span class="rn">高风险</span><span class="rc"><b>服务行业闸门</b>——服务行业不得出现制造业域的分析。混合行业须品名级区分。</span></div>';
  h += '</div>';

  h += '<div class="rpt-block">';
  h += '<h4>闸门二：质量标准检查</h4>';
  h += '12项硬性标准逐条执行。每项含：检查方法（正则匹配+语义检测）+正确范例+错误范例。不通过的在发现底部标注<span class="rpt-em">⚠ 标准N：问题摘要</span>——标记模式（不影响报告主体，仅供审理参考）。';

  h += '<table class="rpt-table">';
  h += '<tr><th>#</th><th>标准</th><th>等级</th><th>核心要求</th></tr>';
  h += '<tr><td>1</td><td>客观第三人称叙事</td><td><span class="rpt-bad rpt-bad-r">强制</span></td><td>全文使用"经查""该企业""被查单位"，禁止"我""你"</td></tr>';
  h += '<tr><td>2</td><td>事实-证据-后果三要素</td><td><span class="rpt-bad rpt-bad-r">强制</span></td><td>每条发现须含①具体事实（含数值）②证据来源③后果推导（→导致XX）</td></tr>';
  h += '<tr><td>3</td><td>完整因果链A→B→C</td><td><span class="rpt-bad rpt-bad-y">重要</span></td><td>tax_impact中至少含一个"→"，完整呈现从异常到后果的推导</td></tr>';
  h += '<tr><td>4</td><td>可操作的紧迫感</td><td><span class="rpt-bad rpt-bad-r">强制</span></td><td>suggestion必须具体到可执行步骤，禁止笼统表述</td></tr>';
  h += '<tr><td>5</td><td>智能法律诊断</td><td><span class="rpt-bad rpt-bad-r">强制</span></td><td>policy_ref含具体条款号，同时自动检索并提示相同违法事实下的从轻/减轻/免于处罚情节（如主动补缴税款和滞纳金的，引用征管法相应条款建议从轻）。禁止兜底模板。</td></tr>';
  h += '<tr><td>6</td><td>证据明细表</td><td><span class="rpt-bad rpt-bad-y">重要</span></td><td>涉及多实体的发现须附items数组</td></tr>';
  h += '<tr><td>7</td><td>方法在前→过程在后</td><td><span class="rpt-bad rpt-bad-g">建议</span></td><td>先声明分析方法，再展示具体发现</td></tr>';
  h += '<tr><td>8</td><td>反模板句</td><td><span class="rpt-bad rpt-bad-r">强制</span></td><td>禁止8类预定义模板文本</td></tr>';
  h += '<tr><td>9</td><td>事实具体化</td><td><span class="rpt-bad rpt-bad-r">强制</span></td><td>含具体数值：日期/金额/数量/百分比</td></tr>';
  h += '<tr><td>10</td><td>防跨发现复制</td><td><span class="rpt-bad rpt-bad-y">重要</span></td><td>同类风险合并之后执行。不同发现的tax_impact不得完全相同。</td></tr>';
  h += '<tr><td>11</td><td>空占位符检测</td><td><span class="rpt-bad rpt-bad-y">重要</span></td><td>suggestion不得含"( )""如：( )"等空占位残留</td></tr>';
  h += '<tr><td>12</td><td>法律条款号</td><td><span class="rpt-bad rpt-bad-r">强制</span></td><td>必须含"第X条"或"第X款"，不能笼统引用</td></tr>';
  h += '</table>';
  h += '</div>';

  h += '<div class="rpt-block">';
  h += '<h4>闸门三：建议质量增强</h4>';
  h += '11条增强规则：补充具体查证路径（"在天眼查确认供应商工商状态"而非"请核实供应商"）→添加时间要求（"5个工作日内"）→添加金额参照→补充法律依据→区分正常/异常分支处理路径。增强后每条建议含完整操作链：查什么→怎么查→正常怎么办→异常怎么办→无法做到的后果。';
  h += '</div>';

  h += '<div class="rpt-block">';
  h += '<h4>闸门四：二次净化</h4>';
  h += '再次执行文本净化，清除建议增强过程中可能产生的新模板句或格式残留。经过四道闸门后——文本纯净度>95%，标准通过率>90%。';
  h += '</div>';

  h += '</div>';
  h += '</div>';

  // ════════════════════════════════════════
  // 第五章：报告结构 —— 七章一附件
  // ════════════════════════════════════════
  h += '<div class="rpt-chapter">';
  h += '<div class="rpt-ch-title"><span class="cn">五</span>报告结构：七章一附件</div>';
  
  h += '<div class="rpt-block">';
  h += '<h4>封面</h4>';
  h += '标题居中"税 务 稽 查 报 告"，字体加粗加大。编号格式：税稽字[YYYY]第XXX号（年份4位+3位流水号），右上角。报告日期精确到日，右下角。封面不编页码。';

  h += '<h4>第一章 · 案件来源及基本情况</h4>';
  h += '8项基本信息以表格呈现：案件来源 / 被查单位全称 / 统一社会信用代码 / 法定代表人 / 企业类型 / 行业分类（三层穿透结论："工商登记X/发票推断Y/实质经营Z→综合判断"）/ 税务合规期间 / 税务合规范围。行业分类须注明推断依据和数据来源。缺失工商数据标注"待联网核查补充"。';

  h += '<h4>第二章 · 税务合规实施情况</h4>';
  h += '7个执行段落，每段200-400字，整体2000字以上。以税务合规过程叙事展开：资料审阅与类型识别→身份锚定与发票方向判定→行业判定与闸门验证→资金流借方/贷方双向核对→穿透分析与知识图谱→行业对标→综合分析与结论形成。所有数据从report对象实时提取，使用客观第三人称叙事。';

  h += '<h4>第三章 · 发现问题及事实认定</h4>';
  h += '每条发现按六要素格式独立呈现，高风险优先排列。已审核的发现展示绿色审核横幅。跨域协商结果以彩色横幅（⛔消解/🔄调整/ℹ️标记）展示在发现标题下方。<br>';
  h += '<span class="rpt-em">同类风险合并规则：</span>同一风险类型（type字段相同）的多条发现必须合并为一条——不得逐条罗列导致报告冗长。合并步骤：按type分组→取最高等级→展示"N项同类风险合并"标签→列出所有子项→合并证据明细。<br>';
  h += '<span class="rpt-em">执行顺序（不可逆）：</span>先在第三章执行同类风险合并，再在闸门二执行标准#10防跨发现复制检查。如果合并逻辑完美，标准#10应极少触发；反之，频繁触发则说明合并逻辑有漏。';

  h += '<h4>第四章 · 税务合规结论</h4>';
  h += '5个结论段落：综合评分+风险等级+结论叙述→风险分布表（四级等级/数量/占比/代表性事项举例）→证据链完整性声明（跨域覆盖范围+核心证据闭环+追溯能力）→局限性声明（缺什么资料报什么局限）→定调性总体结论（高风险→"建议启动立案程序"；中→"建议限期自查整改"；低→"建议持续规范完善"）。结论须定调性而非定论性。<br>';
  h += '<span class="rpt-em">反证排除声明（强制附加）</span> — 在总体结论后，必须附加一段反证排除声明：<br>';
  h += '"本结论排除了以下合理可能：①企业能提供合理解释证明交易真实性；②第三方证据（如运输单据、对方确认函）可证实货物/服务已交付；③金额差异由计算口径或时间性差异导致且企业已提供说明。"<br>';
  h += '这个声明不是在示弱——是在主动告诉审理部门和法院：<em>结案前，我们已经把所有能推翻结论的理由都想过并排除了</em>。这是铁案的最后一道自我安检。';

  h += '<h4>第五章 · 处理处罚建议</h4>';
  h += '按紧急程度分三级，红黄绿三色区分：<span class="rpt-bad rpt-bad-r">P0立即处理</span>极高/高风险发现，标注"5个工作日内书面回复"——<span class="rpt-bad rpt-bad-y">P1限期整改</span>中风险发现，标注"15个工作日内完成整改"——<span class="rpt-bad rpt-bad-g">P2持续关注</span>低风险/优惠机会，标注"30个工作日内完善"。最后附《自查整改期限总说明》含时限/逾期后果/异议处理。';

  h += '<h4>第六章 · 告知权利义务</h4>';
  h += '五项法定权利各独立卡片：回避权（3日内申请）→陈述申辩权（7日内）→听证权（5日内申请）→行政复议权（60日内）→行政诉讼权（15日内）。每项权利含四要素：权利名称+行使条件+法定期限+法律依据。';

  h += '<h4>第七章 · 税务合规人员签字</h4>';
  h += '执行人亲笔签名+执法证件号 / 审理人亲笔签名+执法证件号 / 税务机关公章 / 报告日期（系统自动获取）。存档说明："本报告一式三份：税务合规部门留存一份，被查单位一份，报送上一级税务机关备案一份"。系统预留签名栏位，正式文书人工手签盖章。';

  h += '<h4>附件 · 证据清单</h4>';
  h += '附件一：销项发票全量明细（11列） / 附件二：进项发票全量明细（11列） / 附件三：主营业务成本发票明细 / 附件四：重大费用发票明细 / 附件五：银行流水汇总 / 附件六：各资料文件清单 / 附件七：质量标准自检结果。发票明细上限200条，超出部分以电子附件形式另行提供，不截断。<br>';
  h += '<span class="rpt-em">附件八：证据关联图（强制要求）</span> — 每条P0级发现必须在附件中附带一张证据关联图。该图以时间为横轴，将合同、资金流水、发票、货物流凭证、账载记录等证据节点串联——直观展示证据如何形成闭环。图中标注每项证据的来源文件、具体行号、金额、日期。文字论证配以可视化证据链，这是报告呈堂时最有说服力的部分。';
  h += '</div>';
  h += '</div>';

  // ════════════════════════════════════════
  // 第六章：协同自洽
  // ════════════════════════════════════════
  h += '<div class="rpt-chapter">';
  h += '<div class="rpt-ch-title"><span class="cn">六</span>协同自洽：29域结论必须是一个整体</div>';
  
  h += '<div class="rpt-block">';
  h += '<h4>为什么需要协商</h4>';
  h += '29个域各自独立运行——域A说"收款偏差52%→高风险"，域B说"行业=服务行业"——两个结论各自正确但存在矛盾。没有协商引擎的报告=29个域各自为政，结论相互矛盾读者不知道信谁。协商引擎的作用：把29个独立的分析结论融合为一个自洽的整体判断。';
  h += '</div>';

  h += '<div class="rpt-block">';
  h += '<h4>协商四步骤</h4>';
  h += '<b>步骤1·域分析独立运行：</b>29个域各产发现，域间暂时不通信。各域在各自范围内是正确的。<br>';
  h += '<b>步骤2·协商引擎启动：</b>先行业闸门消解（NEG-001~005）→再资料驱动标记（NEG-010~040）→再证据矛盾消解（NEG-020~030）→最后联合增强（NEG-AUG-001~003）。顺序不可调——先消解才能避免矛盾发现被增强引擎误用来合成错误的"增强发现"。<br>';
  h += '<b>步骤3·级联消解：</b>一条消解可能触发三级联动。域15判服务行业→消解域1进销存异常→域14不再因"缺进销存台账"报高风险→域17不用制造业基准值。<br>';
  h += '<b>步骤4·日志审计：</b>每条记录协商前后状态变化——原始等级→协商后等级/是否被消解/协商规则编号。协商过程全程可审计。';
  h += '</div>';

  h += '<div class="rpt-block">';
  h += '<h4>四种协商结果</h4>';
  h += '<span class="rpt-bad rpt-bad-r">⛔ 消解</span> 域A直接推翻域B结论。如"服务行业→进销存风险不适用"。在报告中发现保留但仅作参考。<br>';
  h += '<span class="rpt-bad rpt-bad-y">🔄 调整</span> 域A削弱域B结论。展示原等级→新等级和原因。<br>';
  h += '<span class="rpt-bad rpt-bad-b">ℹ️ 标记</span> 域A给域B加标签不加等级。如"资料受限结论""含非经营收款"。<br>';
  h += '<span class="rpt-bad rpt-bad-r">🔴 增强</span> 多域信号同时触发→合成更高级别新发现。如空壳企业预警、隐匿收入预警、对倒开票预警。';
  h += '</div>';
  h += '</div>';

  // ════════════════════════════════════════
  // 第七章：引擎铁律 → 报告质量映射
  // ════════════════════════════════════════
  h += '<div class="rpt-chapter">';
  h += '<div class="rpt-ch-title"><span class="cn">七</span>引擎铁律与报告质量的因果关系</div>';

  h += '<div class="rpt-block">';
  h += '<h4>每条铁律守护报告的一个质量维度——违反一条，报告就有一条致命缺陷</h4>';
  h += '<table class="rpt-table">';
  h += '<tr><th width="140">铁律</th><th>守护的质量维度</th><th>违反后果</th></tr>';
  h += '<tr><td>科目name：只存本级名称</td><td>报告第三章证据材料中科目名称准确性</td><td>科目名称与实际账务不符→证据链断裂</td></tr>';
  h += '<tr><td>三号合并：同票唯一凭证号</td><td>报告附件中凭证清单不重复不遗漏</td><td>银行余额与实际不符→资金流分析失真</td></tr>';
  h += '<tr><td>审计铁律：交付前必过审计</td><td>报告数据借贷平衡</td><td>带错数据进入审理→直接退回</td></tr>';
  h += '<tr><td>ref_id去重：精确匹配</td><td>证据清单每条唯一不重复</td><td>金额模糊匹配导致错误合并</td></tr>';
  h += '<tr><td>普票税额：并入成本</td><td>报告第五章补税金额计算的正确性</td><td>建议补税额与实际应补税额不符</td></tr>';
  h += '<tr><td>7分类禁止兜底</td><td>报告第三章成本分析真实反映费用构成</td><td>未识别费用全归"其他"→数据失真</td></tr>';
  h += '<tr><td>规则=代码：同步变更</td><td>报告中规则描述与系统行为一致</td><td>报告"声称"的规则和实际逻辑对不上</td></tr>';
  h += '<tr><td>代码即承诺：可追溯实现</td><td>报告声称的每一项分析能力有代码支撑</td><td>报告说"已分析XX域"但代码中无对应函数</td></tr>';
  h += '<tr><td>全行业适用：禁止特化</td><td>行业对标数据与企业实际行业匹配</td><td>不同行业企业看到同一套对标→误判</td></tr>';
  h += '<tr><td>主动关联更新</td><td>报告中多处出现的同一数据一致</td><td>概述52%/详情48%/附件50%——自相矛盾</td></tr>';
  h += '<tr><td>方法论先行：每步可查</td><td>每个结论有方法论支撑→追到代码</td><td>结论变成"系统判的"无法解释</td></tr>';
  h += '</table>';
  h += '</div>';
  h += '</div>';

  // ════════════════════════════════════════
  // 第八章：机密边界与交付
  // ════════════════════════════════════════
  h += '<div class="rpt-chapter">';
  h += '<div class="rpt-ch-title"><span class="cn">八</span>机密边界与交付闭环</div>';

  h += '<div class="rpt-block">';
  h += '<h4>报告中的机密红线——系统内部信息不得入报告</h4>';
  h += '以下内容<span class="rpt-em">绝对禁止</span>出现在正式报告中：引擎执行流程（管线结构/模块名称）→规则/线索链/证据链数量统计→内部闭环状态清单→系统自诊与自我修正→审核审查面板→方法论演进文字→内部技术标签（Synthesis:/Causal:/[AGI]等前缀）。原则：报告给被查单位和税务机关看，只呈现结论和依据，不暴露系统实现细节。凡是标注"⚠仅供分析参考，不入正式报告"的信息，生成时一律移除。';
  h += '</div>';

  h += '<div class="rpt-block">';
  h += '<h4>审核→反馈→迭代闭环</h4>';
  h += '审核反馈驱动报告持续进化：审理部门提出修改意见→系统记录本次审核经验→注入AGI知识库→下次同类问题识别更精准。累计审核次数越多，系统对同类问题的判断越准确。<br>';
  h += '<span class="rpt-em">退修记录入案例库（学习引擎输入）</span> — 每一份被退回修改的报告，其完整修改记录（原结论、退回原因、修改后结论、采用的新证据）必须自动存入案例库。引擎不仅要从新案子学，更要从自己被退回来的"败笔"中学——原结论为什么被退？缺了什么证据？法律引用哪里有问题？每一条退回原因都转化为学习层的一条纠错训练样本。这比正确案例的学习价值更大。<br>';  
  h += '四触发机制（手动/启动/提交/分析）确保全模块数据统一——任何一个触发点启动的数据同步都会传导到其他模块。';  
  h += '</div>';

  h += '<div class="rpt-block">';
  h += '<h4>语音播报</h4>';
  h += '全文播报控制条固定于报告顶部。中文男声(zh-CN male)低沉严肃声线。6档语调：章节标题0.65音调/0.7x语速庄严缓慢有力→高风险管理内容0.68/0.75x严肃凝重→法律条文0.70/0.72x清晰郑重→处理建议0.80/0.85x清晰有力→普通叙述0.78/0.88x新闻联播标准。当前播报段落橙色底纹高亮，自动滚动至视野中央。';
  h += '</div>';
  h += '</div>';

  h += '</div>'; // end rpt-layout
  container.innerHTML = h;

  // 侧边栏子模块入口
  if (window._reportSection) {
    var sec = window._reportSection;
    window._reportSection = null;
    var style = document.createElement('style');
    style.textContent = '.rpt-layout > .rpt-chapter{display:none}';
    container.appendChild(style);
    setTimeout(function() {
      var el = container.querySelector('[id="' + sec + '"]');
      if (el) el.closest('.rpt-chapter').style.display = 'block';
    }, 100);
  }
}
