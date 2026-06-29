// ==================== 驳回内容填写模板 ====================
function renderFeedbackTemplate(container) {
  if (!container) return;
  window.currentModule = '驳回内容模板';

  var html = '';
  html += '<style>.fb-layout{display:flex;gap:24px;max-width:1100px;margin:0 auto;padding:20px}.fb-toc{width:190px;flex-shrink:0;position:sticky;top:20px;align-self:flex-start;background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:12px;line-height:2.2}.fb-toc .toc-title{font-weight:700;color:#0f172a;font-size:13px;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}.fb-toc a{display:block;color:#475569;text-decoration:none;padding:2px 8px;border-radius:4px;cursor:pointer}.fb-main{flex:1;min-width:0}</style>';
  html += '<div class="fb-layout">';

  // TOC
  html += '<nav class="fb-toc"><div class="toc-title">📖 导航</div>';
  html += '<a href="#fb-struct">模板结构</a>';
  html += '<a href="#fb-compare">对比方法</a>';
  html += '<a href="#fb-industry">行业不适用</a>';
  html += '<a href="#fb-missing">缺资料误判</a>';
  html += '<a href="#fb-threshold">阈值过严</a>';
  html += '<a href="#fb-datasource">数据源问题</a>';
  html += '<a href="#fb-effect">系统怎么用</a>';
  html += '</nav>';

  html += '<div class="fb-main">';
  html += '<h2 style="font-size:22px;font-weight:800;color:#0f172a;margin:0 0 4px">📋 驳回内容填写模板</h2>';
  html += '<p style="font-size:13px;color:#94a3b8;margin:0 0 24px">照着填，系统就能在下一次分析时自动识别并纠正同类发现。</p>';

  // ── 模板结构 ──
  html += '<div id="fb-struct" style="margin-bottom:32px">';
  html += '<h3 style="font-size:16px;font-weight:700;color:#0f172a;margin:0 0 8px">模板结构</h3>';
  html += '<div style="padding:16px 20px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;font-size:13px;line-height:2.2;white-space:pre-wrap">【判断结论】[正确 / 需纠正 / 不适用]
【具体问题】[一句话指出系统哪里判断错了]
【正确逻辑】[说明正确的判断方法是什么]
【需要证据】[要什么资料才能做出正确判断]
【法律依据】[可选：引用的法条或法规]</div>';
  html += '</div>';

  // ── 场景1 ──
  html += '<div id="fb-compare" style="margin-bottom:32px">';
  html += '<h3 style="font-size:16px;font-weight:700;color:#0f172a;margin:0 0 4px">场景1：对比方法错误</h3>';
  html += '<p style="font-size:12px;color:#94a3b8;margin:0 0 12px">全量比对→按客户逐名匹配。适用：收款vs开票、付款vs进项、银行vs凭证</p>';
  html += '<div style="padding:16px 20px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;font-size:13px;line-height:2.2;white-space:pre-wrap">【判断结论】需纠正
【具体问题】系统将全部银行贷方金额与全部销项开票金额直接比对，这种全量比对包含了股东注资、借款、往来款等非经营性资金，夸大了偏差程度。52000元偏差里可能有30000元是关联方资金往来，根本不是销售收入。
【正确逻辑】以销项发票的购买方名称为锚，去银行流水收款中匹配对应的付款方名称。只比对"同一客户→已开票+已收款"的那部分金额。开票大于收款=应收账款（正常商业信用），收款大于开票=预收款或未开票收入（重点核查）。
【需要证据】销项发票+银行流水（含对方户名），按客户逐名匹配后的对比表。
【法律依据】《增值税暂行条例》第十九条（纳税义务发生时间）</div>';
  html += '</div>';

  // ── 场景2 ──
  html += '<div id="fb-industry" style="margin-bottom:32px">';
  html += '<h3 style="font-size:16px;font-weight:700;color:#0f172a;margin:0 0 4px">场景2：行业不适用</h3>';
  html += '<p style="font-size:12px;color:#94a3b8;margin:0 0 12px">服务行业触发了制造业专属分析域。适用：进销存/存货/BOM/毛利率/进销比</p>';
  html += '<div style="padding:16px 20px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;font-size:13px;line-height:2.2;white-space:pre-wrap">【判断结论】不适用
【具体问题】被查单位销项品名100%属于广告服务/咨询服务/技术服务，是典型的服务型企业，根本不存在实物商品的进销存。但系统仍然报了"进销存匹配异常"高风险。服务行业的核心生产要素是人力和知识，不是原材料和产成品。
【正确逻辑】服务行业应自动跳过进销存、存货周转、BOM表、进销比行业对标、毛利率行业对标共5个分析域。这些域对服务行业无分析意义，报出任何结论都是假的。
【需要证据】销项发票品名即可判断——含"广告/咨询/设计/服务/策划/代理/推广"等关键词即为服务行业。
【法律依据】-</div>';
  html += '</div>';

  // ── 场景3 ──
  html += '<div id="fb-missing" style="margin-bottom:32px">';
  html += '<h3 style="font-size:16px;font-weight:700;color:#0f172a;margin:0 0 4px">场景3：缺少资料导致高风险</h3>';
  html += '<p style="font-size:12px;color:#94a3b8;margin:0 0 12px">缺资料≠高风险。适用：合同比对、关联交易、申报比对等依赖缺失资料的域</p>';
  html += '<div style="padding:16px 20px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;font-size:13px;line-height:2.2;white-space:pre-wrap">【判断结论】需纠正
【具体问题】系统因为缺少合同资料，将"长期大额客户无正式合同"判定为高风险。但企业确实有长期合作的客户，只是没有上传合同文件。没有文件不意味着没有合同——这是两回事。
【正确逻辑】缺少某类资料时，涉及该资料的发现应降为低风险并标注"资料未提交，待补充后重新评估"。不应在无证据的情况下直接判定高风险。
【需要证据】补充提交正式业务合同/框架协议/订单确认单后重新分析。
【法律依据】《税务稽查工作规程》第二十四条（证据规则）</div>';
  html += '</div>';

  // ── 场景4 ──
  html += '<div id="fb-threshold" style="margin-bottom:32px">';
  html += '<h3 style="font-size:16px;font-weight:700;color:#0f172a;margin:0 0 4px">场景4：算法阈值过严</h3>';
  html += '<p style="font-size:12px;color:#94a3b8;margin:0 0 12px">偏差百分比/比率超过阈值但业务合理的。适用：人均产值、毛利率、进销比</p>';
  html += '<div style="padding:16px 20px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;font-size:13px;line-height:2.2;white-space:pre-wrap">【判断结论】需纠正
【具体问题】系统以"人均产值超过50万元"判定人均效能异常。但广告传媒行业的人均产值通常较高，尤其是头部企业或承接大型项目的企业。50万的阈值对服务行业来说偏低。
【正确逻辑】人均产值的阈值应分行业设定。制造业50万合理，但广告/咨询/软件/设计等服务行业应提高到80-100万，金融/投资行业更高。不能一刀切。
【需要证据】行业人均产值基准数据（可从66行业基准库中查询或联网获取）。
【法律依据】-</div>';
  html += '</div>';

  // ── 场景5 ──
  html += '<div id="fb-datasource" style="margin-bottom:32px">';
  html += '<h3 style="font-size:16px;font-weight:700;color:#0f172a;margin:0 0 4px">场景5：数据本身有问题</h3>';
  html += '<p style="font-size:12px;color:#94a3b8;margin:0 0 12px">系统逻辑正确，但数据源存在分类错误。适用：银行流水分类错误、发票归类错误</p>';
  html += '<div style="padding:16px 20px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;font-size:13px;line-height:2.2;white-space:pre-wrap">【判断结论】正确（数据源有问题）
【具体问题】系统判断"收款与开票金额偏差大"本身是正确的分析逻辑。但问题出在数据源——银行流水中有一笔50000元是股东个人账户打进来的注资款，被错误地归入了"企业客户款"类别，导致收款端多出50000元。
【正确逻辑】系统分析逻辑正确。应修正收款分类规则——将付款方为个人姓名的收款归入"个人待分析"而不是"企业客户款"。"有限公司"关键字匹配不应覆盖不含公司后缀的个人姓名。
【需要证据】银行流水+付款方身份证明（如股东身份证/出资协议/银行凭证）。
【法律依据】-</div>';
  html += '</div>';

  // ── 系统怎么用 ──
  html += '<div id="fb-effect" style="padding:16px 24px;background:#f0f4ff;border-radius:8px;font-size:13px;line-height:2.2">';
  html += '<strong style="font-size:14px">系统怎么用这个内容</strong><br>';
  html += '<b>存入</b>：驳回内容存入 <code style="background:#e2e8f0;padding:1px 4px;border-radius:3px">static/correction_rules.json</code>，按"发现类型|行业|经营模式"生成指纹。<br>';
  html += '<b>匹配</b>：下次分析时，<code style="background:#e2e8f0;padding:1px 4px;border-radius:3px">apply_correction_rules()</code> 四级回退匹配（精确→行业→通用→名称）。<br>';
  html += '<b>生效</b>：匹配成功后，给发现打标签（_dismissed/_negotiated），不影响原始等级但标注已驳回。<br>';
  html += '<b>查看</b>：推理引擎仪表盘 → 智能大脑 → 纠正规则库。<br>';
  html += '<b>代码位置</b>：<code style="background:#e2e8f0;padding:1px 4px;border-radius:3px">engine/self_learning.py</code>（record_correction + apply_correction_rules）';
  html += '</div>';

  html += '</div></div>';
  container.innerHTML = html;
}