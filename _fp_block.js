// ═══════════ 页面1：文件解析（清新段落式） ═══════════
function renderFileParsingPage(container) {
  if (!container) return;
  window.currentModule = '文件解析';
  var fps = fpFingerprints();
  container.innerHTML = '<style>'
    + '.fp2{max-width:1060px;margin:0 auto;padding:38px 46px;background:#fff;color:#4b5563;'
    + 'font-size:12px;line-height:1.9;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif}'
    + '.fp2-wrap{display:flex;gap:54px;align-items:flex-start}'
    + '.fp2-toc{width:128px;flex-shrink:0;position:sticky;top:24px;font-size:11.5px}'
    + '.fp2-toc .tt{font-size:10.5px;font-weight:700;color:#b0b8c4;letter-spacing:.12em;margin:0 0 12px 12px}'
    + '.fp2-toc a{display:block;color:#64748b;text-decoration:none;padding:6px 0 6px 12px;border-left:2px solid #eef2f6;transition:.15s;line-height:1.5}'
    + '.fp2-toc a:hover{color:#0e7490;border-left-color:#0e7490}'
    + '.fp2-body{flex:1;min-width:0;max-width:788px}'
    + '.fp2 h1{font-size:20px;font-weight:700;color:#0f172a;margin:0 0 6px;letter-spacing:-.01em}'
    + '.fp2 .lead{font-size:11.5px;color:#a5adba;margin:0 0 24px;font-weight:500}'
    + '.fp2 .intro{font-size:12.5px;color:#4b5563;line-height:2.05;margin:0 0 10px}'
    + '.fp2 section{margin:0 0 54px;scroll-margin-top:24px}'
    + '.fp2 h2{font-size:15.5px;font-weight:700;color:#0f172a;margin:0 0 4px;display:flex;align-items:baseline;gap:9px}'
    + '.fp2 h2 .idx{color:#0e7490;font-size:12px;font-weight:700;letter-spacing:.02em}'
    + '.fp2 .sub{font-size:12px;color:#94a3b8;margin:0 0 20px;padding-bottom:15px;border-bottom:1px solid #eef2f6;line-height:2.0}'
    + '.fp2 p{margin:0 0 13px}'
    + '.fp2 strong{color:#334155;font-weight:600}'
    + '.fp2 .layer{padding:2px 0 2px 20px;border-left:2px solid #e0f2f7;margin:0 0 24px}'
    + '.fp2 .layer .lh{font-size:13px;font-weight:700;color:#0f172a;margin:0 0 9px}'
    + '.fp2 .layer .lh .n{color:#0e7490;margin-right:9px}'
    + '.fp2 .layer .lh em{font-style:normal;font-size:11px;font-weight:500;color:#a5adba;margin-left:10px}'
    + '.fp2 .layer p{margin:0 0 9px;line-height:2.0}'
    + '.fp2 details{border-bottom:1px solid #eef2f6}'
    + '.fp2 summary{padding:12px 2px;cursor:pointer;font-size:12.5px;font-weight:600;color:#334155;list-style:none;user-select:none;display:flex;align-items:center;gap:8px}'
    + '.fp2 summary::-webkit-details-marker{display:none}'
    + '.fp2 summary::after{content:"+";margin-left:auto;color:#cbd5e1;font-size:16px;font-weight:400}'
    + '.fp2 details[open] summary::after{content:"\\2212"}'
    + '.fp2 details .dc{padding:0 2px 16px;color:#64748b;line-height:2.05}'
    + '.fp2 .fmt{margin:0 0 20px}'
    + '.fp2 .fmt .ft{font-size:13px;font-weight:700;color:#0f172a;margin:0 0 5px}'
    + '.fp2 .fmt p{margin:0;line-height:2.0;color:#64748b}'
    + '.fp2 .fq{margin:0 0 22px}'
    + '.fp2 .fq .qt{font-size:12.5px;font-weight:700;color:#0f172a;margin:0 0 2px}'
    + '.fp2 .fq .qd{font-size:11.5px;color:#a5adba;margin:0 0 11px;line-height:1.9}'
    + '.fp2 .fp-row{display:flex;gap:12px;padding:8px 0;border-bottom:1px solid #f4f7fa}'
    + '.fp2 .fp-row .nm{flex-shrink:0;width:104px;font-weight:600;color:#334155;font-size:12px}'
    + '.fp2 .fp-row .sg{flex:1;color:#9ca3af;line-height:1.75;font-size:11.5px}'
    + '.fp2 .fp-row .th{flex-shrink:0;color:#0e7490;font-weight:600;font-size:11.5px;white-space:nowrap}'
    + '.fp2 .step{display:flex;gap:15px;margin:0 0 17px}'
    + '.fp2 .step .sn{flex-shrink:0;width:25px;height:25px;border-radius:50%;background:#f0f9fb;color:#0e7490;font-size:12px;font-weight:700;display:flex;align-items:center;justify-content:center;margin-top:1px}'
    + '.fp2 .step .st{font-size:13px;font-weight:700;color:#0f172a;margin:0 0 3px}'
    + '.fp2 .step .sd{color:#64748b;line-height:2.0}'
    + '.fp2 .rstat{display:flex;gap:36px;margin:0 0 34px}'
    + '.fp2 .rstat .rc .rn{font-size:26px;font-weight:700;color:#0f172a;line-height:1.1}'
    + '.fp2 .rstat .rc .rl{font-size:11.5px;color:#a5adba;margin-top:5px}'
    + '.fp2 .tag{display:inline-block;margin:0 7px 7px 0;padding:5px 11px;background:#f8fafc;border:1px solid #eef2f6;border-radius:14px;font-size:11.5px;color:#64748b}'
    + '.fp2 .tag b{color:#0e7490;font-weight:700;margin-left:3px}'
    + '.fp2 table.rt{width:100%;border-collapse:collapse;font-size:12px}'
    + '.fp2 table.rt th{text-align:left;padding:9px 12px 9px 0;font-weight:600;color:#94a3b8;font-size:11px;border-bottom:1px solid #e5eaf0}'
    + '.fp2 table.rt td{padding:9px 12px 9px 0;border-bottom:1px solid #f4f7fa;color:#475569}'
    + '.fp2 .rh{font-size:11px;font-weight:700;color:#b0b8c4;letter-spacing:.08em;margin:0 0 14px}'
    + '.fp2 .plog{background:#f8fafc;border:1px solid #eef2f6;border-radius:8px;padding:16px 18px;max-height:420px;overflow-y:auto;font-family:"SF Mono","Fira Code",Consolas,monospace;font-size:11px;line-height:1.95}'
    + '.fp2 .empty{color:#b0b8c4;font-size:12px;padding:28px 0}'
    + '</style>'
    + '<div class="fp2"><div class="fp2-wrap">'
    + '<nav class="fp2-toc"><div class="tt">目录</div>'
    + '<a href="#fp-mechanism">识别机制</a>'
    + '<a href="#fp-compat">兼容策略</a>'
    + '<a href="#fp-formats">格式扩展</a>'
    + '<a href="#fp-fingerprint">文件指纹库</a>'
    + '<a href="#fp-flow">解析流程</a>'
    + '<a href="#fp-result">本次解析结果</a>'
    + '</nav>'
    + '<div class="fp2-body">'
    + '<h1>文件解析</h1>'
    + '<p class="lead">工作第一步 · ' + fps.length + ' 类文件指纹 · 四层递进识别 · 四方交叉验证 · 8 种格式全兼容</p>'
    + '<p class="intro">文件解析引擎是税务合规分析的起点。企业上传各种格式的原始资料后，引擎不依赖文件扩展名，而是通过 ' + fps.length + ' 类文件指纹、四层递进识别与四方交叉验证，自动判定每个文件的真实类型，并提取为标准化的结构化数据，供下游的域分析与风险稽查使用。</p>'
    + '<p class="intro">它支持 xls、xlsx、csv、pdf、docx、jpg、png、tiff 共 8 种格式，兼容 82+ 种列名变体，采用自适应表头检测（不预设表头在第几行）与汇总行自动过滤，最大限度保证数据质量——核心原则是不因无法识别而丢弃任何一行数据。</p>'
    + '<div id="fp-static"></div>'
    + '<div id="fp-analysis-result"></div>'
    + '</div></div></div>';
  renderFileParsingStatic();
  if (_cachedFileParsingReport) { renderFileParsingResult(_cachedFileParsingReport); }
  else { loadFileParsingData(); }
}

function renderFileParsingStatic() {
  var target = document.getElementById('fp-static');
  if (!target) return;
  var fps = fpFingerprints();
  var html = '';

  // 一、识别机制
  html += '<section id="fp-mechanism">'
    + '<h2><span class="idx">一</span> 识别机制</h2>'
    + '<p class="sub">四层递进 + 四方交叉验证 —— 从粗糙到精细、从单一证据到多方印证，逐步锁定文件真实类型</p>'
    + '<p>系统接收到文件后，不依赖文件扩展名判断（用户上传的 .xls 可能是任何内容），而是模拟人类专家的判断逻辑：先看表头关键词，再看列结构，再看数据样本，最后综合文件名、列头、数据、公司身份四方证据做最终裁决。</p>'
    + '<div class="layer">'
    + '<div class="lh"><span class="n">1</span>关键词匹配 · 打分制<em>最高优先级 · 识别率 ~80%</em></div>'
    + '<p><strong>执行逻辑：</strong>读取 Excel 文件的前 200 行表头区域（不只是第 1 行），将表头中的每一个词与 ' + fps.length + ' 类文件指纹的关键词库做交叉匹配。每命中一个关键词得 1 分，得分超过该类型指纹的评分阈值（通常 2–4 分）即判定为该类型；多类型同时超过阈值时，取得分最高者作为主判定。</p>'
    + '<p><strong>实际例子：</strong>表头出现"对方户名""交易日期""收入金额"三个词 → 银行流水指纹得 3 分 ≥ 阈值 3 → 判定为银行流水；表头出现"发票号码""开票日期""金额""税额"四个词 → 通用发票指纹得 4 分 ≥ 阈值 4 → 判定为通用发票。</p>'
    + '<p><strong>边缘情况：</strong>当多个类型得分非常接近（相差 ≤1 分）时标记为"存疑"，进入结构分析做二次判定。关键词库持续迭代——每发现一种新的列名变体即自动补充。目前银行流水关键词 23 个、工资表 60+ 个、通用发票 20 个。</p>'
    + '</div>'
    + '<div class="layer">'
    + '<div class="lh"><span class="n">2</span>结构分析 · 列模式匹配<em>第二优先级 · 多类型接近时激活</em></div>'
    + '<p><strong>激活条件：</strong>关键词匹配阶段前两名得分差距 ≤1 分，或最高分类型得分恰好等于阈值（临界状态）。此时不简单地"取最高分"，而是进入更深层次的结构分析。</p>'
    + '<p><strong>分析方法：</strong>系统为每种文件类型维护一套列模式模板——包括列数范围、关键列位置、排列顺序。例如银行流水模板：日期列（前 3 列）+ 对方户名列（前 3–5 列）+ 金额列（第 4–8 列）+ 余额列（最后 1–2 列）；工资表模板：姓名列（第 1 列）+ 收入列（第 2–5 列）+ 扣除列（第 6–8 列）+ 实发列（倒数 1–2 列）。</p>'
    + '<p><strong>容错设计：</strong>列位置允许 ±3 列偏移，关键列必须存在但位置可浮动。相似度 = 命中列数 / 模板总列数 ≥ 60% 即匹配。例如模板要求 8 列，实际命中 5 列（5/8 = 62.5% ≥ 60%）→ 匹配成功。</p>'
    + '</div>'
    + '<div class="layer">'
    + '<div class="lh"><span class="n">3</span>数据推断 · 逐列语义分类<em>兜底机制 · 绝不丢弃数据</em></div>'
    + '<p><strong>触发场景：</strong>关键词匹配和结构分析都无法确定类型时（如企业自制的非标准表格），系统不拒绝解析或丢弃数据，而是逐列读取前 200 行数据样本，按每个单元格的语义角色自动分类。</p>'
    + '<p><strong>语义分类（5 类）：</strong>日期格式（2023-01-01、2023/1/1、2023年1月1日等）→ 日期列；纯数字无小数位（整数、序号）→ 数量/编号列；含"公司""有限""厂""店""集团"等标识词 → 企业名称列；含"元""金额""￥""合计"或含 2 位小数 → 金额列；含"税""%""税率" → 税率列。</p>'
    + '<p><strong>兜底输出：</strong>无法确定具体类型时标注为"通用数据"（generic_data），保留完整原始行列结构，交由下游域分析引擎与规则匹配引擎自行判断用途。核心原则：不因无法识别而丢弃任何一行数据。</p>'
    + '</div>'
    + '<div class="layer">'
    + '<div class="lh"><span class="n">4</span>四方交叉验证 · 最终裁决<em>证据冲突时数据优先</em></div>'
    + '<p><strong>设计目的：</strong>前三层都是"文件内部"的推理，有时会产生歧义（如一份银行流水被改了列名，看起来像费用明细）。四方交叉验证引入"外部证据"——文件名暗示、公司身份锚定、买卖方关系匹配，从多角度验证前三层的结论。</p>'
    + '<p><strong>四方证据：</strong>① 文件名暗示——含"开票""销项"倾向销项发票，含"取票""进项""抵扣"倾向进项发票，仅作参考权重；② 列头推理——前三层结果带置信度；③ 数据扫描——读取数据中的企业名称与公司身份双向比对，购方 = 当前公司 → 进项、销方 = 当前公司 → 销项，双方都不匹配 → 存疑排除；④ 公司匹配——通过企业名称与统一社会信用代码双向锚定当前账套身份。</p>'
    + '<p><strong>冲突裁决：</strong>数据扫描（买卖方匹配）> 列头推理（关键词得分）> 文件名暗示。因为数据不会说谎——只要数据中购方名称 = 当前公司，无论文件名写什么、表头怎么命名，这份文件就是进项发票。文件名可能错标、表头可能不规范，但数据本身的身份关系是铁证。</p>'
    + '</div>'
    + '</section>';

  // 二、兼容策略
  html += '<section id="fp-compat">'
    + '<h2><span class="idx">二</span> 兼容策略</h2>'
    + '<p class="sub">列名映射表（82+ 变体）+ 智能自适应机制 —— 兼容不同 ERP、财务软件、银行导出的命名习惯差异</p>'
    + '<p>企业上传的资料格式千差万别。文件解析模块通过列名映射与汇总行过滤，把各类非标准表格归一化为标准字段。以下按资料类型展开各自的兼容细节：</p>';

  var compatItems = [
    {title:'\u{1f3e7} 银行流水', detail:
      '<strong>日期列：</strong>交易日期、记账日期、交易时间、日期、申请日期、起息日 共 6 种。<br>' +
      '<strong>对方户名：</strong>对方户名、交易对方、对方名称、counterparty、对方单位、收款人名称 共 6 种。<br>' +
      '<strong>金额：</strong>收入金额、支出金额、贷方金额、借方金额、交易金额、发生额 共 6 种，自动去除 ￥/元/逗号/空格 等非数字字符，符号按借贷方向或交易关键词自动判断。<br>' +
      '<strong>余额：</strong>本次余额、交易余额、账户余额 共 3 种。<br>' +
      '<strong>汇总行过滤：</strong>自动剔除含"小计""合计""总计""本页合计""本年累计""当月合计"的行。'},
    {title:'\u{1f9fe} 发票', detail:
      '<strong>方向自动判定：</strong>购方名称/税号 = 当前公司 → 进项；销方名称/税号 = 当前公司 → 销项；双方都不匹配 → 存疑排除。<br>' +
      '<strong>购买方列名：</strong>购方名称、购买方名称、购方、买方、客户名称、付款方 共 6 种。<br>' +
      '<strong>销售方列名：</strong>销方名称、销售方名称、销方、卖方、供应商名称、供方名称、收款方 共 7 种。<br>' +
      '<strong>发票号码：</strong>发票号码、发票号、数电发票号码、票据号码 共 4 种。<br>' +
      '<strong>金额：</strong>金额、不含税金额、含税金额、价税合计、小写金额——自动识别含税/不含税并补齐缺失字段。'},
    {title:'\u{1f4b0} 工资表', detail:
      '<strong>60+ 列名变体：</strong>本期收入 / 应发工资 / 实发工资 / 应发合计 / 实发合计 / 代扣个税 / 基本养老保险 / 基本医疗保险 / 住房公积金 / 专项扣除 / 子女教育 / 赡养老人 / 基本工资 / 绩效工资 / 岗位工资 / 加班工资 / 各类补贴 / 奖金 / 年终奖 / 提成 等。<br>' +
      '<strong>个税申报格式：</strong>累计收入 / 累计减除费用 / 累计专项扣除 / 累计应纳税额 / 已预缴税额 / 应补退税额——与工资表按关键词自动区分，走不同解析器。<br>' +
      '<strong>合计行过滤：</strong>自动剔除"合计""总计""小计"行，防止重复统计。'},
    {title:'\u{1f3e5} 社保 / 公积金', detail:
      '<strong>社保三列自动区分：</strong>缴费基数（工资基数/社保基数）、单位缴纳（单位缴费/公司缴纳）、个人缴纳（个人缴费/个人承担）。<br>' +
      '<strong>五险自动识别：</strong>养老 / 医疗 / 失业 / 工伤 / 生育——各险种可能独立 Sheet 或合并列出现。<br>' +
      '<strong>公积金：</strong>公积金/住房公积金/住房储金、缴存基数、缴存比例（自动识别单位+个人两部分）、月缴存额。'},
    {title:'\u{1f4cb} 申报表', detail:
      '<strong>增值税申报表：</strong>销售额 / 销项税额 / 进项税额 / 应纳税额 / 期末留抵——兼容一般纳税人与小规模两种表式。<br>' +
      '<strong>企业所得税申报表：</strong>营业收入 / 营业成本 / 利润总额 / 纳税调整增减 / 应纳税所得额 / 税率——兼容查账征收与核定征收。<br>' +
      '<strong>个税申报表：</strong>通过"累计预扣预缴""应补退税额""所得项目"等专属词与工资表区分。<br>' +
      '<strong>印花税 / 完税证明：</strong>按税种名称和缴款日期格式自动识别。'},
    {title:'\u{1f4ca} 财务报表', detail:
      '<strong>科目余额表：</strong>科目编码 / 科目名称 / 期初余额 / 本期借方 / 本期贷方 / 期末余额——兼容借贷方向与余额方向两种格式。<br>' +
      '<strong>资产负债表 / 利润表：</strong>按报表项目名称（流动资产、营业收入、营业成本等）自动区分。<br>' +
      '<strong>进销存台账：</strong>期初库存 / 本期入库 / 本期出库 / 期末库存 / 存货编码 / 产品名称——兼容数量与金额两类台账。'},
    {title:'\u{1f4c4} 合同 / 往来 / 资产', detail:
      '<strong>合同台账：</strong>合同编号 / 名称 / 甲方 / 乙方 / 金额 / 已付 / 未付 / 签订 / 生效 / 到期——14 字段全覆盖。<br>' +
      '<strong>应收 / 应付账款：</strong>客户/供应商名称、欠款/应付金额、账龄、账期、逾期标志。<br>' +
      '<strong>固定资产：</strong>资产名称 / 原值 / 累计折旧 / 净值 / 入账日期 / 折旧年限 / 残值率。<br>' +
      '<strong>无形资产 / 资产损失 / 费用明细 / 研发费用：</strong>各有专属关键词集与解析器，按列名自动路由。'},
    {title:'\u{1f50d} 特殊类型', detail:
      '<strong>人员清单：</strong>姓名 / 身份证号 / 入职 / 离职 / 岗位 / 部门——通过无金额列与工资表区分。<br>' +
      '<strong>股权交易：</strong>出让方 / 受让方 / 转让比例 / 转让价格 / 审批日期。<br>' +
      '<strong>借款合同：</strong>借款人 / 出借人 / 借款金额 / 利率 / 期限 / 担保方式。<br>' +
      '<strong>进出口报关：</strong>报关单号 / 进出口类型 / 商品名称 / 金额 / 币种 / 口岸。<br>' +
      '<strong>关联交易：</strong>关联方名称 / 交易类型 / 关联关系 / 交易金额 / 定价政策。<br>' +
      '<strong>通用数据（兜底）：</strong>以上均不匹配时标注 generic_data，保留原始结构原样输出供下游判断。'}
  ];
  compatItems.forEach(function(ci) {
    html += '<details><summary>' + ci.title + '</summary><div class="dc">' + ci.detail + '</div></details>';
  });
  html += '</section>';

  // 三、格式扩展
  html += '<section id="fp-formats">'
    + '<h2><span class="idx">三</span> 格式扩展</h2>'
    + '<p class="sub">多格式全兼容 —— 除传统 Excel 外，已扩展到 PDF / Word / CSV / OCR 图片的自动解析</p>'
    + '<div class="fmt"><div class="ft">\u{1f4c4} PDF 文档</div><p>双引擎架构：pdfplumber 表格提取（优先）+ pypdf 文本解析（兜底）。自适应策略——逐页提取所有表格 → 取最大表格 → 表头走 ' + fps.length + ' 类指纹匹配 → 成功则按类型路由，失败则回退旧解析器。不再硬编码特定银行格式，任何银行 / 税务 PDF 均可识别。支持 .pdf。</p></div>'
    + '<div class="fmt"><div class="ft">\u{1f4dd} Word 文档</div><p>python-docx 遍历所有表格 → 合并多表格 → 表头指纹匹配；无表格时提取段落文本标注为 document_text 类型。适用于合同、申报说明、审计报告等 Word 资料。支持 .docx。</p></div>'
    + '<div class="fmt"><div class="ft">\u{1f4ca} CSV 文本</div><p>管道原生支持：csv.reader 读取 → CsvSheet 模拟 Sheet 接口 → 指纹匹配。编码自动检测（UTF-8-BOM 优先），自动处理逗号分隔与引号转义。适用于银行系统、ERP 导出的 CSV 数据。支持 .csv。</p></div>'
    + '<div class="fmt"><div class="ft">\u{1f4f7} OCR 图片识别</div><p>双引擎 OCR：EasyOCR（中文优先，文字块坐标提取）+ Tesseract（系统兜底）。表格重建——Y 坐标聚类（&lt;15px 视为同行）→ X 排序 → 构建行×列矩阵 → 指纹匹配；无表格结构时用正则提取发票号 / 代码 / 日期 / 金额等字段。首次使用需联网下载 EasyOCR 模型（约 200MB，一次性）。支持 .jpg .jpeg .png .bmp .tiff。</p></div>'
    + '</section>';

  // 四、文件指纹库
  html += '<section id="fp-fingerprint">'
    + '<h2><span class="idx">四</span> 文件指纹库 · ' + fps.length + ' 类</h2>'
    + '<p class="sub">每类指纹 = 关键词集 + 得分阈值 + 专用解析器 —— 关键词决定"怎么看"，阈值决定"多确定才算"，解析器决定"识别后怎么提取"</p>'
    + '<p>指纹库按使用频率分为六个梯队，第一梯队是税务合规中最常见的高频类型。下表列出每类的识别特征与判定阈值：</p>';

  var groups = [
    {title:'第一梯队 · 高频核心', items: fps.slice(0,12),
     desc:'税务合规中最常出现的材料——银行流水、发票、工资表、社保公积金等，拥有最完善的关键词库（20–60+ 个）和最成熟的解析器，识别率 >95%。'},
    {title:'第二梯队 · 合同 / 关联交易', items: fps.slice(12,14),
     desc:'关键词数量较少（9–12 个），依赖更细致的结构分析——这类文件的列结构比关键词更有特征性。'},
    {title:'第三梯队 · 申报表与财务报表', items: fps.slice(14,20),
     desc:'含税种名称、报表项目、会计科目等专业术语，阈值 3 分，因列名专业性强、不易与其他类型混淆。'},
    {title:'第四梯队 · 往来与合同清单', items: fps.slice(20,24),
     desc:'应收应付、预收预付等往来类数据，通常含对方单位名称 + 金额 + 账龄三要素。'},
    {title:'第五梯队 · 资产与费用', items: fps.slice(24,29),
     desc:'固定资产、无形资产、资产损失、费用明细、研发费用等，各有关键词特征，阈值 2 分。'},
    {title:'第六梯队 · 特殊交易与兜底', items: fps.slice(29),
     desc:'人员清单、股权交易、借款合同、进出口报关等特殊类型；最后由通用数据（generic_data）兜底，阈值仅 1 分，确保任何有结构的表格都不会被丢弃。'}
  ];
  groups.forEach(function(g) {
    html += '<div class="fq"><div class="qt">' + escHtml(g.title) + '</div><div class="qd">' + escHtml(g.desc) + '</div>';
    g.items.forEach(function(item) {
      html += '<div class="fp-row"><div class="nm">' + item.icon + ' ' + escHtml(item.name) + '</div>'
        + '<div class="sg">' + escHtml(item.sig) + '</div>'
        + '<div class="th">' + item.threshold + '</div></div>';
    });
    html += '</div>';
  });
  html += '</section>';

  // 五、解析流程
  html += '<section id="fp-flow">'
    + '<h2><span class="idx">五</span> 解析流程</h2>'
    + '<p class="sub">8 步全链路 —— 从磁盘上的原始文件到结构化的分析数据，每步有明确的输入、处理与输出</p>';

  var steps = [
    {num:'1', title:'磁盘扫描', detail:'遍历 uploads/ 目录下所有支持格式的文件，按修改时间排序，跳过系统临时文件（~$ 开头、.tmp 结尾）。同一文件 MD5 去重——内容相同只解析一次，避免重复工作。'},
    {num:'2', title:'格式检测', detail:'读取文件前 5KB，通过二进制签名（magic bytes）判断真实格式而非扩展名：xls/xlsx 看 OLE2/ZIP 签名、CSV 看纯文本逗号、PDF 看 %PDF 头、DOCX 看 ZIP+[Content_Types].xml、图片看 JPEG/PNG/BMP/TIFF 头，据此调用 openpyxl / xlrd / csv / pdfplumber / python-docx / PIL。'},
    {num:'3', title:'表头提取', detail:'逐 Sheet 读取前 200 行（非硬编码"第 1 行"，而是自适应扫描直到找到列名行）。对每列提取列名文本 + 前 200 个数据样本，构建"表头特征向量"，自动跳过空行、纯数字行与明显的合计行。'},
    {num:'4', title:'指纹匹配', detail:'将表头特征向量与 ' + fps.length + ' 类指纹关键词库交叉匹配：遍历每种类型的关键词集，命中 1 词得 1 分，记录各类型总得分；同时检查"关键识别词"——某些词的出现足以直接判定类型。'},
    {num:'5', title:'类型判定', detail:'取得分最高者：最高分 ≥ 阈值 → 直接判定；最高分 < 阈值且前两名差距 ≤1 分 → 进入结构分析；所有类型均 < 阈值且无接近候选 → 进入数据推断。四方交叉验证在判定存疑时介入做最终裁决。'},
    {num:'6', title:'解析器调用', detail:'根据最终类型调用对应专用解析器（银行流水 → _parse_bank_sheet、发票 → _parse_invoice_sheet、工资 → _parse_salary_sheet、合同 → _parse_contract_sheet 等），完成列名映射归一化（82+ 变体 → 标准字段）、数据类型转换（字符串 → float/date）、无效行过滤。'},
    {num:'7', title:'标准化输出', detail:'统一字段命名（date / amount / counterparty / seller / buyer / goods / quantity / tax_rate / tax_amount / total），金额统一为 float（去千分位与货币符号）、日期统一为 YYYY-MM-DD，输出为可直接使用的结构化 JSON。'},
    {num:'8', title:'日志与路由', detail:'将每个文件的解析结果写入 file_results 数组与 pipeline_log 日志，按类型路由到对应数据列表（银行流水 → bank_txs、发票 → invoice_data、工资 → salary_data 等）；解析失败标注 error 原因供诊断回溯，所有日志持久化到分析缓存。'}
  ];
  steps.forEach(function(st) {
    html += '<div class="step"><div class="sn">' + st.num + '</div>'
      + '<div><div class="st">' + st.title + '</div><div class="sd">' + st.detail + '</div></div></div>';
  });
  html += '</section>';

  target.innerHTML = html;
}

// 文件指纹数据（详尽版）
function fpFingerprints() {
  return [
    {icon:'🏧', name:'银行流水', sig:'对方户名 | 交易日期 | 收入金额 | 支出金额 | 借贷标志 | 余额（23 个关键词）', threshold:'≥3', parser:'_parse_bank_sheet'},
    {icon:'💰', name:'工资表', sig:'本期收入 | 应发工资 | 代扣个税 | 社保 | 公积金 | 实发合计（60+ 关键词）', threshold:'≥2', parser:'_parse_salary_sheet'},
    {icon:'🧾', name:'销项发票', sig:'购方名称 | 购方税号 | 购买方纳税人识别号（10 个关键词）', threshold:'≥2', parser:'_parse_invoice_sheet(销项)'},
    {icon:'📥', name:'进项发票', sig:'销方名称 | 销方税号 | 销售方名称 | 供应商名称（11 个关键词）', threshold:'≥2', parser:'_parse_invoice_sheet(进项)'},
    {icon:'📋', name:'通用发票', sig:'发票号码 | 发票代码 | 开票日期 | 金额 | 税额 | 价税合计 | 税率（20 个关键词）', threshold:'≥4', parser:'_parse_invoice_sheet(进项)'},
    {icon:'📝', name:'记账凭证', sig:'凭证号 | 科目名称 | 摘要 | 借方金额 | 贷方金额（8 个主关键词）', threshold:'≥2', parser:'_parse_voucher_sheet'},
    {icon:'🛡️', name:'社保明细', sig:'缴费基数 | 单位缴纳 | 个人缴纳 | 养老保险 | 医疗保险 | 工伤保险（15 个关键词）', threshold:'≥2', parser:'_parse_social_sheet'},
    {icon:'🏡', name:'公积金', sig:'公积金 | 缴存基数 | 缴存比例 | 单位缴存 | 个人缴存 | 月缴存额（17 个关键词）', threshold:'≥2', parser:'_parse_housing_fund_sheet'},
    {icon:'📑', name:'进项抵扣勾选', sig:'勾选状态 | 有效抵扣税额 | 数电发票号码 | 发票风险等级（5 个关键词）', threshold:'≥2', parser:'_parse_input_vat_sheet'},
    {icon:'📦', name:'进销存台账', sig:'期初库存 | 本期入库 | 本期出库 | 期末库存 | 存货编码 | 产品名称（16 个关键词）', threshold:'≥2', parser:'_parse_inventory_sheet'},
    {icon:'📊', name:'科目余额表', sig:'科目编码 | 科目名称 | 期初余额 | 本期发生额 | 期末余额（8 个关键词）', threshold:'≥2', parser:'_parse_trial_balance_sheet'},
    {icon:'📄', name:'合同文件', sig:'合同编号 | 签约方 | 合同金额 | 签订日期 | 履约期限（9 个关键词）', threshold:'≥2', parser:'_parse_contract_sheet'},
    {icon:'🔗', name:'关联交易', sig:'关联方名称 | 交易类型 | 关联关系 | 交易金额 | 定价方式（12 个关键词）', threshold:'≥2', parser:'_parse_related_party'},
    {icon:'📄', name:'合同清单', sig:'合同名称 | 对方名称 | 合同金额 | 已付金额 | 未付金额（16 个关键词）', threshold:'≥2', parser:'_parse_contract_list'},
    {icon:'💰', name:'财务报表', sig:'营业收入 | 营业成本 | 利润总额 | 资产合计 | 负债合计 | 期末余额（18 个关键词）', threshold:'≥3', parser:'_parse_financial_sheet'},
    {icon:'🏦', name:'增值税申报表', sig:'销售额 | 销项税额 | 进项税额 | 应纳税额 | 期末留抵（19 个关键词）', threshold:'≥3', parser:'_parse_vat_declaration'},
    {icon:'📈', name:'企业所得税申报表', sig:'营业收入 | 营业成本 | 利润总额 | 应纳税所得额 | 税率（11 个关键词）', threshold:'≥3', parser:'_parse_cit_declaration'},
    {icon:'👤', name:'个税申报表', sig:'纳税人姓名 | 收入 | 应纳税所得额 | 已缴税额 | 应补退税额（16 个关键词）', threshold:'≥2', parser:'_parse_individual_tax'},
    {icon:'📜', name:'印花税', sig:'税目 | 计税金额 | 税率 | 应纳税额 | 减免税额（12 个关键词）', threshold:'≥2', parser:'_parse_stamp_duty'},
    {icon:'📋', name:'完税证明', sig:'税种 | 所属期 | 计税金额 | 实缴金额 | 缴款日期（14 个关键词）', threshold:'≥2', parser:'_parse_tax_payment'},
    {icon:'🤝', name:'应收账款', sig:'客户名称 | 欠款金额 | 账龄 | 账期 | 是否逾期（10 个关键词）', threshold:'≥2', parser:'_parse_accounts_receivable'},
    {icon:'🏗️', name:'应付账款', sig:'供应商名称 | 应付金额 | 账龄 | 付款条件（10 个关键词）', threshold:'≥2', parser:'_parse_accounts_payable'},
    {icon:'💳', name:'预收预付', sig:'客户/供应商名称 | 预收金额 | 预付金额 | 结算状态（10 个关键词）', threshold:'≥2', parser:'_parse_prepaid_advance'},
    {icon:'🧾', name:'其他应收付', sig:'对方名称 | 应收/应付 | 金额 | 账龄 | 坏账准备（7 个关键词）', threshold:'≥2', parser:'_parse_other_receivables'},
    {icon:'🏭', name:'固定资产', sig:'资产名称 | 原值 | 累计折旧 | 净值 | 入账日期 | 折旧年限（14 个关键词）', threshold:'≥2', parser:'_parse_fixed_assets'},
    {icon:'📜', name:'无形资产', sig:'资产名称 | 原值 | 累计摊销 | 净值 | 摊销年限（9 个关键词）', threshold:'≥2', parser:'_parse_intangible_assets'},
    {icon:'📊', name:'资产损失', sig:'资产名称 | 损失金额 | 损失原因 | 审批日期（8 个关键词）', threshold:'≥2', parser:'_parse_asset_impairment'},
    {icon:'📋', name:'费用明细', sig:'费用类型 | 金额 | 报销人 | 所属部门 | 发生日期（20 个关键词）', threshold:'≥2', parser:'_parse_expense_detail'},
    {icon:'🔬', name:'研发费用', sig:'研发项目 | 费用类型 | 金额 | 研发阶段 | 资本化/费用化（12 个关键词）', threshold:'≥2', parser:'_parse_rd_expense'},
    {icon:'👥', name:'人员清单', sig:'姓名 | 身份证号 | 入职日期 | 离职日期 | 岗位 | 部门（14 个关键词）', threshold:'≥2', parser:'_parse_employee_list'},
    {icon:'📄', name:'股权交易', sig:'出让方 | 受让方 | 转让比例 | 转让价格 | 审批日期（9 个关键词）', threshold:'≥2', parser:'_parse_equity_transaction'},
    {icon:'💰', name:'借款合同', sig:'借款人 | 出借人 | 借款金额 | 利率 | 期限 | 担保方式（14 个关键词）', threshold:'≥2', parser:'_parse_loan_borrowing'},
    {icon:'🚢', name:'进出口报关', sig:'报关单号 | 进出口类型 | 商品名称 | 金额 | 币种 | 口岸（15 个关键词）', threshold:'≥2', parser:'_parse_import_export'},
    {icon:'📋', name:'通用数据', sig:'纯数值表（9 个关键词，兜底）', threshold:'≥1', parser:'_parse_generic'}
  ];
}

async function loadFileParsingData() {
  var target = document.getElementById('fp-analysis-result');
  if (!target) return;
  try {
    var data = await getSharedAnalysis();
    if (!data.ok) {
      target.innerHTML = '<section id="fp-result"><h2><span class="idx">六</span> 本次解析结果</h2><p class="sub">动态数据 —— 展示本次分析实际解析的文件结果</p><div class="empty">暂无分析结果，请先运行一键分析</div></section>';
      return;
    }
    _cachedFileParsingReport = data.report;
    renderFileParsingResult(data.report);
  } catch (e) {
    target.innerHTML = '<section id="fp-result"><h2><span class="idx">六</span> 本次解析结果</h2><div class="empty">加载失败</div></section>';
  }
}

function renderFileParsingResult(report) {
  var target = document.getElementById('fp-analysis-result');
  if (!target) return;
  var frs = report.file_results || [];
  var plogs = report.pipeline_log || [];
  var parsed = frs.filter(function(f) { return f.type !== 'unknown' && !f.error; }).length;
  var failed = frs.filter(function(f) { return f.error; }).length;

  var html = '<section id="fp-result">'
    + '<h2><span class="idx">六</span> 本次解析结果</h2>'
    + '<p class="sub">动态数据 —— 本次分析共解析 ' + frs.length + ' 个文件，成功识别 ' + parsed + ' 个，未识别 ' + failed + ' 个</p>'
    + '<div class="rstat">'
    + '<div class="rc"><div class="rn">' + frs.length + '</div><div class="rl">文件总数</div></div>'
    + '<div class="rc"><div class="rn" style="color:#0e9f6e">' + parsed + '</div><div class="rl">已解析</div></div>'
    + '<div class="rc"><div class="rn" style="color:#e02424">' + failed + '</div><div class="rl">未解析</div></div>'
    + '<div class="rc"><div class="rn" style="color:#0e7490">' + plogs.length + '</div><div class="rl">管线日志</div></div>'
    + '</div>';

  var typeCount = {};
  frs.forEach(function(fr) { var t = fr.type || 'unknown'; typeCount[t] = (typeCount[t] || 0) + 1; });
  var types = Object.keys(typeCount).sort(function(a,b) { return typeCount[b] - typeCount[a]; });
  if (types.length > 0) {
    html += '<div class="rh">类型分布</div><div style="margin:0 0 34px">';
    types.forEach(function(t) {
      html += '<span class="tag">' + escHtml(t) + '<b>' + typeCount[t] + '</b></span>';
    });
    html += '</div>';
  }

  html += '<div class="rh">解析明细</div>';
  if (frs.length === 0) {
    html += '<div class="empty">无文件数据</div>';
  } else {
    html += '<table class="rt"><thead><tr>'
      + '<th style="width:32px">#</th><th>文件名</th><th>识别类型</th><th style="text-align:right">数据条数</th><th>解析动作</th>'
      + '</tr></thead><tbody>';
    frs.forEach(function(fr, i) {
      var typeLabel = fr.type || '未知';
      var status = fr.error ? 'fail' : (fr.type === 'unknown' ? 'warn' : 'ok');
      var rowCount = '—';
      var actions = '';
      if (fr.actions && fr.actions.length) {
        var m = (fr.actions.join(' ')).match(/(\d+)条/);
        if (m) rowCount = m[1];
        actions = fr.actions.join(' · ');
      }
      var statusIcon = status === 'fail' ? '✗' : (status === 'warn' ? '△' : '✓');
      var statusColor = status === 'fail' ? '#e02424' : (status === 'warn' ? '#c27803' : '#0e9f6e');
      html += '<tr>'
        + '<td style="color:#b0b8c4">' + (i + 1) + '</td>'
        + '<td style="color:#0f172a;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + escHtml(fr.file) + '"><span style="color:' + statusColor + ';margin-right:6px">' + statusIcon + '</span>' + escHtml(fr.file) + '</td>'
        + '<td style="color:#64748b">' + escHtml(typeLabel) + '</td>'
        + '<td style="text-align:right;color:#334155;font-weight:600">' + rowCount + '</td>'
        + '<td style="color:#a5adba;font-size:11px;max-width:260px">' + escHtml(actions) + '</td>'
        + '</tr>';
    });
    html += '</tbody></table>';
  }

  if (plogs.length > 0) {
    html += '<div class="rh" style="margin-top:36px">管线日志 · 共 ' + plogs.length + ' 条</div>';
    html += '<div class="plog">';
    plogs.forEach(function(log, i) {
      var color = '#94a3b8';
      if (/异常|失败|错误/.test(log)) color = '#e02424';
      else if (/完成|成功|通过/.test(log)) color = '#0e9f6e';
      else if (/发现|触发|命中/.test(log)) color = '#c27803';
      else if (/Phase|Step|阶段/.test(log)) color = '#0e7490';
      html += '<div style="color:' + color + '">[' + (i + 1).toString().padStart(3, ' ') + '] ' + escHtml(log) + '</div>';
    });
    html += '</div>';
  }

  html += '</section>';
  target.innerHTML = html;
}
