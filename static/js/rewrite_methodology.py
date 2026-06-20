import re

f = 'C:/Users/26726/WorkBuddy/2026-05-31-09-56-37/caishuixitong/static/js/tax-pipeline-pages.js'
with open(f, 'r', encoding='utf-8') as fp:
    content = fp.read()

# 新的稽查方法论部分（详尽版本）
new_methodology = '''  // ══════ 四、稽查方法论（㉖条详解）══════
  html += '<div style="margin-bottom:48px;padding:24px;background:#fafafa;border-radius:8px">'
    + '<h3 style="font-size:18px;font-weight:700;color:#0f172a;margin:0 0 16px">四、稽查方法论（㉖条已全部代码化）</h3>'
    + '<p style="font-size:14px;color:#64748b;line-height:2;margin:0 0 20px">'
    + '稽查方法论是税务稽查系统的灵魂。每一条方法论都来自实战中反复踩过的坑，是血泪教训的结晶。下面逐条详解。'
    + '</p>'
    + '<div style="font-size:13px;color:#475569;line-height:2.2">'

  var methods = [
    {id:'①', name:'多格式兼容', desc:'银行文件date/tx_time/交易日期/交易时间/记账日期五种命名全兼容。PDF发票PDFPlumber解析+OCR兜底。Excel多引擎（openpyxl/xlrd/pandas）。不因格式不兼容而丢弃数据。'},
    {id:'②', name:'汇总行过滤', desc:'月末汇总行（对手为空+大额整数）→自动识别并剔除。银行流水中的汇总行（如"本月合计"）不是真实交易，必须过滤。'},
    {id:'③', name:'付款方身份核实', desc:'个人打款→联网查工商→范善茂=法定代表人→性质待核实（股东注资/借款/未申报收入），不直接定性。付款方身份必须核实，不能凭名字猜测。'},
    {id:'④', name:'关键词≠事实', desc:'BOM从纯关键词→进销品名实质差异+加工费证据。含"BOM"关键词不等于有BOM业务，必须通过进销品名差异和加工费发票来证明。'},
    {id:'⑤', name:'行业认知补算法', desc:'工商批发业≠无加工。外包轻加工模式（买坯布→委托染整厂加工→卖成品布）在批发业中广泛存在。算法必须考虑行业认知，不能仅凭工商登记判定企业类型。'},
    {id:'⑥', name:'联网核查', desc:'企查查查法人/股东/行业/注册资本。工商信息可能与发票数据不一致，必须联网核查确认。'},
    {id:'⑦', name:'明细即信服力', desc:'全部收款方+付款方逐一列示明细表，不分组合并。每条发现必须有具体数据（供应商名/金额/发票号），不可泛泛计数。'},
    {id:'⑧', name:'不墨迹直接干', desc:'发现问题不请示，读文件查格式直接修。下一步工作必须做时，不等不提问，自动继续直到交付完整结果。'},
    {id:'⑨', name:'合同分层判断', desc:'四层自动分类：必签（主营业务+金额>5万）、应签（金额1-5万）、可免（日常消费）、小额（金额<1万）。印花税预估：must_total × 0.03%。'},
    {id:'⑩', name:'完备度明细', desc:'资料完备度评估必须列明每类资料的实际数量（如"销项发票：36张"），不能只说"齐全"或"缺失"。'},
    {id:'⑪', name:'完备度升级', desc:'资料完备度综合评估从单一维度（有/无）升级为多维度（数量+时间跨度+完整性），更准确反映资料质量。'},
    {id:'⑫', name:'凭证描述纠正', desc:'记账凭证摘要必须规范化（如"购入原材料"而非"付款"），便于后续分析。'},
    {id:'⑬', name:'进销诊断升级', desc:'进销品名不匹配的诊断从简单比对升级为三层分析：①品名差异分析、②加工费证据检查、③加工链条合理性判断。'},
    {id:'⑭', name:'行业基准库', desc:'66行业基准值库，每个行业含毛利率/净利率/税负率/进销比/人均营收五个指标的下限/上限/典型值。用于行业对标分析。'},
    {id:'⑮', name:'结论分析法', desc:'每条结论必须同时具备：detect（检测现象）+ verify（交叉验证）+ diagnose（根因诊断）+ report（综合结论）四步分析框架。'},
    {id:'⑯', name:'COND_BAN防误杀', desc:'条件过滤（COND_BAN）防止过滤器误杀重要发现。有资料则放过，无资料则删除相关结论。'},
    {id:'⑰', name:'稽查重点强制等级', desc:'12类稽查重点发现不根据score计算等级，而是直接硬编码为"高风险"。保护机制：后端强制修正+过滤器绕过+前端红色标记。'},
    {id:'⑱', name:'报告纯净度', desc:'报告是给稽查执行人员阅读的专业文书，不是开发调试日志。所有系统内部标注（【detect 检测现象】等）必须移除。'},
    {id:'⑲', name:'发票≠收付款1:1', desc:'进项发票vs银行付款、销项发票vs银行收款，均不能按"名称对上=正常、对不上=异常"的1:1逻辑判断。六种收付款模式：自然跨期/合并/分期/预付预收/应付应收/非对公代付。'},
    {id:'⑳', name:'经营实质地理分析', desc:'从单一风险点推理出面的风险。供应商地址+客户地址+加工商地址+运输成本→全链条经营实质是否合理。重物跨省经营缺运输成本=货物流物证链断裂。'},
    {id:'㉑', name:'规则detail业务化', desc:'规则detail字段从技术语言改为业务语言。如"BOM进销映射异常"→"进销品名不匹配，可能存在虚开发票风险"。'},
    {id:'㉒', name:'建议质量增强', desc:'每个风险点的建议必须含具体消除路径——提供XX资料→如果A就XX→如果B就XX→无法做到的后果。不能只说"立即整改"。'},
    {id:'㉓', name:'四步稽查分析法', desc:'detect（检测现象）→ verify（交叉验证）→ diagnose（根因诊断）→ report（输出结论）。四大核心发现全部应用四步法。'},
    {id:'㉔', name:'禁止数据截断', desc:'报告中显示全部明细数据，不截断（如"前5条"→显示全部）。明细即信服力。'},
    {id:'㉕', name:'三层行业穿透法', desc:'工商登记（法律形式）→ 发票数据（经营实质）→ 加工信号（业务模式）。三者不一致时以实质重于形式为原则。'},
    {id:'㉖', name:'经营实质点面推理法', desc:'从单一风险点推理出面的风险。点（单点发现）→ 数据扩展 → 线（关联维度A/B/C/D）→ 交叉验证 → 面（综合结论）。'}
  ];

  methods.forEach(function(m) {
    html += '<div style="padding:10px 16px;margin-bottom:6px;background:#fff;border-radius:6px;border-left:2px solid #e2e8f0">'
      + '<span style="font-weight:700;color:#2563eb;margin-right:8px">' + m.id + '</span>'
      + '<strong style="color:#0f172a">' + m.name + '</strong>'
      + '<span style="color:#64748b;margin-left:8px;font-size:12px\">' + m.desc + '</span>'
      + '</div>';
  });

  html += '</div></div>';'''

# 找到旧的稽查方法论部分
old_methodology_start = content.find("  // ══════ 四、稽查方法论")
if old_methodology_start == -1:
    print("ERROR: methodology section not found")
else:
    print(f"Found methodology section at {old_methodology_start}")
    # 找到结束位置（target.innerHTML = html;）
    methodology_end = content.find("  target.innerHTML = html;", old_methodology_start)
    if methodology_end == -1:
        print("ERROR: methodology section end not found")
    else:
        methodology_end += len("  target.innerHTML = html;")
        print(f"Methodology section ends at {methodology_end}")
        
        # 替换
        content = content[:old_methodology_start] + new_methodology + '\n' + content[methodology_end:]
        
        with open(f, 'w', encoding='utf-8') as fp:
            fp.write(content)
        
        print("SUCCESS: Methodology section replaced")

print("DONE")
