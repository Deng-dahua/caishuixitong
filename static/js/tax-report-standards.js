// ==================== 报告编制总纲 ====================

function renderReportStandards(container) {
  if (!container) return;
  window.currentModule = '报告编制总纲';

  var h = '<style>'
    + '.rpt{max-width:1140px;margin:0 auto;padding:40px 46px;background:#fff;color:#3a4048;font-size:10px;line-height:20px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif}'
    + '.rpt h2{font-size:10px;font-weight:700;color:#16233a;margin:0 0 10px;line-height:1.35}'
    + '.rpt>h2:first-child{font-size:10px;font-weight:800;color:#16233a;margin:0 0 10px;letter-spacing:-.02em;line-height:1.3}'
    + '.rpt .tag{display:inline-block;font-size:10px;color:#9a1f2b;border:1px solid #f4c2c7;background:#fef8f8;border-radius:20px;padding:4px 14px;margin:0 0 30px}'
    + '.rpt p{margin:0 0 10px;text-align:justify}'
    + '.rpt p b,.rpt p strong,.rpt strong{color:#1f2d3d;font-weight:600}'
    + '.rpt p em,.rpt em{font-style:normal;color:#9a1f2b;font-weight:600}'
    + '.rpt-chapter{margin:10px 0 10px;padding:0}'
    + '.rpt-chapter h2{font-size:10px;font-weight:800;color:#16233a;margin:0 0 10px;line-height:1.35;border:none;padding:0}'
    + '.rpt-rule{margin:4px 0;padding:0;font-size:10px;line-height:20px;color:#3a4048}'
    + '.rpt-rule .rn{color:#9a1f2b;font-weight:700;margin-right:6px}'
    + '.rpt-rule .rc{color:#3a4048}'
    + '.rpt-rule.fatal{margin:6px 0}'
    + '.rpt-rule.high{margin:6px 0}'
    + '.rpt-table{font-size:10px;border-collapse:collapse;width:100%;margin:0 0 10px}'
    + '.rpt-table th,.rpt-table td{font-size:10px;text-align:left;padding:4px 8px;line-height:1.8}'
    + '.rpt-table th{font-weight:700;color:#16233a;background:#f8fafc}'
    + '.rpt-table th:nth-child(3){min-width:96px;white-space:nowrap}'
    + '.rpt-table td:nth-child(3){white-space:nowrap}'
    + '</style>'
    + '<div class="rpt">';
  h += '<h2>报告编制总纲</h2>';

  h += '<div class="rpt-chapter"><h2>一、报告本质</h2>';
  h += '<p>报告的终极目的在于：使任何未接触原始数据的审核人员，在完整阅读报告后，能够独立判断案件是否符合立案标准、是否需要追缴税款、是否应当移送司法机关。</p>';
  h += '<p><b>四大支柱：</b>事实（日期/主体/金额/数量）→ 证据（精确到发票号/行号/合同条款）→ 逻辑（异常→排除合法情形→剩余原因→税务后果）→ 法律（具体法条+条款号）。四项要素缺一不可。</p>';
  h += '<p><b>语言立场：</b>报告的语言立场为事实发现者，非最终裁判者。规范用语包括"涉嫌""存疑""经查""可能存在"，禁止使用"违法认定""已查明""构成XX罪"等裁判性表述。</p>';
  h += '</div>';

  h += '<div class="rpt-chapter"><h2>二、发现生成规程（六步核查流程）</h2>';
  h += '<p>① 数据锚定：锁定公司身份+信用代码+分析期间+数据来源。身份锚定错误将导致全部分析结果作废。</p>';
  h += '<p>② 文件识别与方向判定：四方交叉验证判定文件类型。进销方向错误将导致收入与成本数据完全颠倒，属于基础性错误。</p>';
  h += '<p>③ 行业锚定与域闸门：三层穿透（工商登记→发票数据→加工信号）。服务行业不适用制造业域分析，须通过行业闸门进行拦截。</p>';
  h += '<p>④ 全维度扫描：29域独立运行。每个域分析结论须有明确的程序逻辑支撑。</p>';
  h += '<p>⑤ 跨域协商自洽：消解/调整/标记/联合增强。确保所有发现在同一逻辑体系内保持一致性和协调性。</p>';
  h += '<p>⑥ 结论生成与分级：综合评分→风险分级→处理建议。每条分析结论须完整追溯至触发规则、线索调查链、证据闭环链及原始数据来源。</p>';
  h += '</div>';

  h += '<div class="rpt-chapter"><h2>三、报告叙事</h2>';
  h += '<p><b>人称规范：</b>全篇"经查/该企业/被查单位"客观第三人称。禁止"我/你/我们"。</p>';
  h += '<p><b>叙事结构：</b>采用XX分析方法→核查XX数据→发现XX异常情况→分析可能导致XX税务后果→建议进行XX处理。</p>';
  h += '<p><b>数据颗粒度：</b>每条发现至少含1个具体数值+1个时间锚点。</p>';
  h += '<p><b>六要素格式：</b>性质→事实→证据→来源（规则ID可追溯）→法律（法条+条款号）→建议（具体路径）。</p>';
  h += '<p><b>五条禁令：</b>①禁止通篇单一逗号分隔 ②禁止多个逻辑论点集中于同一段落 ③禁止括号堆叠使用 ④子项内容须独立成段 ⑤数据陈述与原因解释须分层表述。</p>';
  h += '</div>';

  h += '<div class="rpt-chapter"><h2>四、质量防线</h2>';
  h += '<p><b>闸门一·文本净化：</b>自动清除模板句/空描述/重复句/空占位符。大部分格式问题可通过自动净化程序修复。</p>';
  h += '<p><b>基础防线：</b>证据三性校验（真实性/关联性/合法性）。三性不通过→不入正式结论。</p>';
  h += '<p><b>闸门二·12项质量标准：</b>客观第三人称/事实-证据-后果三要素/完整因果链/可操作建议/智能法律诊断/证据明细表/方法在前/反模板句/事实具体化/防跨发现复制/空占位符检测/法律条款号。</p>';
  h += '<p><b>闸门三·建议增强：</b>补充查证路径+时间要求+金额参照+法律依据+正常/异常分支处理。</p>';
  h += '<p><b>闸门四·二次净化：</b>清除增强过程产生的新模板句。</p>';
  h += '</div>';

  h += '<div class="rpt-chapter"><h2>五、报告结构（七章一附件）</h2>';
  h += '<p>封面→第一章·案件来源及基本情况（8项基本情况统计表格）→第二章·税务合规实施情况（7段落，每段落不少于400字）→第三章·发现问题及事实认定（六要素+同类风险合并）→第四章·税务合规结论（5段落，附反向证据排除声明）→第五章·处理处罚建议（P0立即处理/P1限期整改/P2持续关注）→第六章·告知权利义务（5项法定权利，各以独立卡片形式呈现）→第七章·签字→附件·证据清单（8个附件，包含证据关联关系图谱）。</p>';
  h += '</div>';

  h += '<div class="rpt-chapter"><h2>六、协同自洽</h2>';
  h += '<p>系统完成39个域分析函数的独立运行后，启动跨域协商程序（执行顺序不可调整：行业闸门判定→资料完备度驱动→证据矛盾检测→多维度联合增强），经级联消解处理后形成统一结论，全过程记录审计日志。</p>';
  h += '<p>四种协商结果：⛔消解（推翻）/🔄调整（降级）/ℹ️标记（加注）/🔴增强（多域叠加升级）。</p>';
  h += '</div>';

  h += '<div class="rpt-chapter"><h2>七、系统铁律与报告质量映射</h2>';
  h += '<p>以下12条系统铁律各自对应报告的一个关键质量维度：科目name准确性/三号合并/审计铁律/ref_id去重/普票税额并入成本/7分类禁止兜底/规则代码同步/代码即承诺/全行业适用/主动关联更新/方法论先行。违反任一铁律将导致报告存在致命质量缺陷。</p>';
  h += '</div>';

  h += '<div class="rpt-chapter"><h2>八、机密边界与交付</h2>';
  h += '<p><b>禁止入报告：</b>系统内部执行流程说明、规则数量统计信息、内部闭环状态标记、系统自诊断信息、内部技术标签。报告正文仅呈现分析结论和处理依据。</p>';
  h += '<p><b>审核→反馈→迭代：</b>退修记录自动纳入案例库。退修类型标注：证据不足、程序违法、定性错误、法律适用不当、表述不合规、计算错误。系统按退修类型进行聚类分析，驱动定向改进。</p>';
  h += '</div>';

  h += '</div>'; // end rpt
  container.innerHTML = h;

  // 侧边栏子模块入口
  if (window._reportSection) {
    var sec = window._reportSection;
    window._reportSection = null;
    var style = document.createElement('style');
    style.textContent = '.rpt > .rpt-chapter{display:none}';
    container.appendChild(style);
    setTimeout(function() {
      var el = container.querySelector('[id="' + sec + '"]');
      if (el) el.closest('.rpt-chapter').style.display = 'block';
    }, 100);
  }
}
