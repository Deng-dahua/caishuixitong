// ==================== 报告编制总纲 —— 50年稽查经验凝结 ====================

function renderReportStandards(container) {
  if (!container) return;
  window.currentModule = '报告编制总纲';

  var h = '<style>'
    + '.rpt{max-width:1140px;margin:0 auto;padding:20px;background:#fff;color:#3a4048;font-size:10px;line-height:20px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif}'
    + '.rpt h2{font-size:10px;font-weight:700;color:#16233a;margin:0 0 20px;line-height:20px}'
    + '.rpt>h2:first-child{font-size:10px;font-weight:800;color:#16233a;margin:0 0 20px;letter-spacing:-.02em;line-height:20px}'
    + '.rpt .tag{display:inline-block;font-size:10px;color:#9a1f2b;border:1px solid #f4c2c7;background:#fef8f8;border-radius:20px;padding:4px 14px;margin:0 0 20px}'
    + '.rpt p{margin:0 0 20px;text-align:justify;line-height:20px}'
    + '.rpt p b,.rpt p strong,.rpt strong{color:#1f2d3d;font-weight:600}'
    + '.rpt p em,.rpt em{font-style:normal;color:#9a1f2b;font-weight:600}'
    + '.rpt-chapter{margin:20px 0 20px;padding:0}'
    + '.rpt-chapter h2{font-size:10px;font-weight:800;color:#16233a;margin:0;line-height:20px;border:none;padding:0}'
    + '.rpt-rule{margin:20px 0;padding:0;font-size:10px;line-height:20px;color:#3a4048}'
    + '.rpt-rule .rn{color:#9a1f2b;font-weight:700;margin-right:6px}'
    + '.rpt-rule .rc{color:#3a4048}'
    + '.rpt-rule.fatal{margin:20px 0}'
    + '.rpt-rule.high{margin:20px 0}'
    + '.rpt-table{font-size:10px;border-collapse:collapse;width:100%;margin:0 0 20px}'
    + '.rpt-table th,.rpt-table td{font-size:10px;text-align:left;padding:4px 8px;line-height:20px}'
    + '.rpt-table th{font-weight:700;color:#16233a;background:#f8fafc}'
    + '.rpt-table th:nth-child(3){min-width:96px;white-space:nowrap}'
    + '.rpt-table td:nth-child(3){white-space:nowrap}'
    + '</style>'
    + '<div class="rpt">';
  h += '<h2>报告编制总纲</h2>';

  h += '<div class="rpt-chapter"><h2>一、报告本质</h2>';
  h += '<p>报告终极目的：让一个没看过原始数据的人，读完报告后能独立判断案子要不要立、税要不要补、人要不要移送。</p>';
  h += '<p><b>四大支柱：</b>事实（日期/主体/金额/数量）→ 证据（精确到发票号/行号/合同条款）→ 逻辑（异常→排除合法情形→剩余原因→税务后果）→ 法律（具体法条+条款号）。四柱缺一不可。</p>';
  h += '<p><b>语言立场：</b>发现者，不是审判者。用"涉嫌/存疑/经查/可能存在"，禁止"违法认定/已查明/构成XX罪"。</p>';
  h += '</div>';

  h += '<div class="rpt-chapter"><h2>二、发现生成（六步铁律）</h2>';
  h += '<p>① 数据锚定：锁定公司身份+信用代码+分析期间+数据来源。锚定错→全部分析作废。</p>';
  h += '<p>② 文件识别与方向判定：四方交叉验证判定文件类型。进销方向错→收入成本颠倒→致命。</p>';
  h += '<p>③ 行业锚定与域闸门：三层穿透（工商登记→发票数据→加工信号）。服务行业禁止制造业域分析。</p>';
  h += '<p>④ 全维度扫描：29域独立运行。每个域结论必须有代码支撑。</p>';
  h += '<p>⑤ 跨域协商自洽：消解/调整/标记/联合增强。一个结论，所有发现在同一逻辑体系内自洽。</p>';
  h += '<p>⑥ 结论生成与分级：综合评分→风险分级→处理建议。每条结论可追溯至规则ID→线索链→证据链→原始数据。</p>';
  h += '</div>';

  h += '<div class="rpt-chapter"><h2>三、报告叙事</h2>';
  h += '<p><b>人称规范：</b>全篇"经查/该企业/被查单位"客观第三人称。禁止"我/你/我们"。</p>';
  h += '<p><b>叙事结构：</b>通过XX方法→核查XX数据→发现XX异常→导致XX后果→建议XX处理。</p>';
  h += '<p><b>数据颗粒度：</b>每条发现至少含1个具体数值+1个时间锚点。</p>';
  h += '<p><b>六要素格式：</b>性质→事实→证据→来源（规则ID可追溯）→法律（法条+条款号）→建议（具体路径）。</p>';
  h += '<p><b>五条禁令：</b>①禁止一逗到底 ②禁止多逻辑挤一段 ③禁止括号堆叠 ④子项独立成段 ⑤数据与解释分层。</p>';
  h += '</div>';

  h += '<div class="rpt-chapter"><h2>四、质量防线</h2>';
  h += '<p><b>闸门一·文本净化：</b>自动清除模板句/空描述/重复句/空占位符。约70%格式问题自动修复。</p>';
  h += '<p><b>底层防线：</b>证据三性校验（真实性/关联性/合法性）。三性不通过→不入正式结论。</p>';
  h += '<p><b>闸门二·12项质量标准：</b>客观第三人称/事实-证据-后果三要素/完整因果链/可操作建议/智能法律诊断/证据明细表/方法在前/反模板句/事实具体化/防跨发现复制/空占位符检测/法律条款号。</p>';
  h += '<p><b>闸门三·建议增强：</b>补充查证路径+时间要求+金额参照+法律依据+正常/异常分支处理。</p>';
  h += '<p><b>闸门四·二次净化：</b>清除增强过程产生的新模板句。</p>';
  h += '</div>';

  h += '<div class="rpt-chapter"><h2>五、报告结构（七章一附件）</h2>';
  h += '<p>封面→第一章·案件来源及基本情况（8项基本表格）→第二章·税务合规实施情况（7段落2000字以上）→第三章·发现问题及事实认定（六要素+同类风险合并）→第四章·税务合规结论（5段落+反证排除声明）→第五章·处理处罚建议（P0立即处理/P1限期整改/P2持续关注）→第六章·告知权利义务（5项权利各独立卡片）→第七章·签字→附件·证据清单（8个附件含证据关联图）。</p>';
  h += '</div>';

  h += '<div class="rpt-chapter"><h2>六、协同自洽</h2>';
  h += '<p>29域独立运行→协商引擎启动（行业闸门→资料驱动→证据矛盾→联合增强，顺序不可调）→级联消解→日志审计。</p>';
  h += '<p>四种协商结果：⛔消解（推翻）/🔄调整（降级）/ℹ️标记（加注）/🔴增强（多域叠加升级）。</p>';
  h += '</div>';

  h += '<div class="rpt-chapter"><h2>七、引擎铁律与报告质量映射</h2>';
  h += '<p>11条铁律各自守护报告的一个质量维度：科目name准确性/三号合并/审计铁律/ref_id去重/普票税额并入成本/7分类禁止兜底/规则代码同步/代码即承诺/全行业适用/主动关联更新/方法论先行。违反任一条→报告有致命缺陷。</p>';
  h += '</div>';

  h += '<div class="rpt-chapter"><h2>八、机密边界与交付</h2>';
  h += '<p><b>禁止入报告：</b>引擎执行流程/规则数量统计/内部闭环状态/系统自诊/内部技术标签。报告只呈现结论和依据。</p>';
  h += '<p><b>审核→反馈→迭代：</b>退修记录自动入案例库。退修类型标签：证据不足/程序违法/定性错误/法律适用不当/表述不合规/计算错误。学习引擎按类型聚类消费，驱动定向增强。</p>';
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
