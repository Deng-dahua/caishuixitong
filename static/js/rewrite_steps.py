import re

f = 'C:/Users/26726/WorkBuddy/2026-05-31-09-56-37/caishuixitong/static/js/tax-pipeline-pages.js'
with open(f, 'r', encoding='utf-8') as fp:
    content = fp.read()

# 新的steps数组（详尽版本）
new_steps = [
    {'n':'①', 'title':'资料扫描与类型识别', 'icon':'📄',
     'desc':'系统遍历 uploads/ 目录，读取全部 Excel/CSV/PDF 文件。使用<strong>34类文件指纹库</strong>执行三层递进识别：'
        + '第一层：关键词打分——表头文字与34类指纹关键词库交叉匹配，每匹配一词得1分，超阈值即判定；'
        + '第二层：结构分析——列数+位置+表头组合模式确认，银行流水=日期+对方+金额+余额模式；'
        + '第三层：数据推断兜底——读前200行按语义角色判定。不因无法识别而丢弃数据——标注为通用数据交由下游模块自行判断。'},
    {'n':'②', 'title':'目标实体识别', 'icon':'🎯',
     'desc':'从发票数据中自动推断<strong>被查单位的名称和行业</strong>。企业名称识别：进项购买方 ∩ 销项销售方 → 交叉取交集确定企业全称。'
        + '行业识别：90+关键词×66行业加权投票制。联网核查：同时联网查询工商登记信息，与发票推断结果做双源比对。'},
    {'n':'③', 'title':'资料情报提取与数据分析', 'icon':'🔍',
     'desc':'将各类型文件数据导入<strong>35个域分析函数</strong>。包括：银行流水收款构成分析 + 付款方身份核实（联网法人/股东比对）；'
        + '进销存比对比——商品明细匹配 + 进销比 + 毛利率；五层发票审计——格式合规→同品名单价→加工费专项→金额合理性→BOM进销映射；'
        + '供应商穿透——集中度+群集+名称异常+双向交易检测；合同分层——四层自动分类（必签/应签/可免/小额）。'},
    {'n':'④', 'title':'规则引擎与链驱动检查', 'icon':'⚙️',
     'desc':'' + '1505' + '条稽查指令逐条与域分析发现做匹配。' + '391' + '条线索链引擎：每链多个调查步骤，通过定量/定性/缺失三类数据验证后触发，'
        + '产生链驱动发现。' + '740' + '条证据链闭环检测：收集所有触发的规则ID，计算每链触发率——≥60%且≥3条规则+≥2数据域→形成证据闭环。'
        + '234条证据链闭环触发→强制升级为高风险。'},
    {'n':'⑤', 'title':'方法论噪声过滤器', 'icon':'🎯',
     'desc':'方法论过滤器是确保报告质量的最后关口。HARD_BAN（硬删除）：23类禁止词绝对不允许出现在输出中——'
        + '涉刑侦术语（公安/经侦/刑事）、推测性结论（走逃/失联）、系统内部术语、跨域数据需求等。'
        + 'COND_BAN（条件过滤）：5类——无申报表则删除申报相关结论，无库存台账则删除库存相关结论（有则放过）。'
        + '稽查重点发现（level_fixed=True）不参与任何过滤。典型效果：1638条→过滤后36条。'},
    {'n':'⑥', 'title':'行业对标与申报比对', 'icon':'📊',
     'desc':'66行业基准值自动对标（每个行业含：毛利率下限/上限/典型值、净利率下限/上限/典型值、税负率下限/上限/典型值、'
        + '进销比下限/上限/典型值、人均营收下限/上限/典型值）。三级判断：低于下限→高风险、低于典型值85%→中风险、高于上限→中风险。'
        + '增值税申报表 vs 发票实际销项税额/进项税额比对，差异>1000元预警。'},
    {'n':'⑦', 'title':'正式稽查报告输出', 'icon':'📝',
     'desc':'综合所有域分析发现、链驱动发现、证据闭环发现，经过方法论过滤器和建议增强后，生成结构化稽查报告。'
        + '报告含：稽查概况、企业工商信息（联网核查）、高风险/中风险/低风险发现（按优先级排序）、'
        + '每条发现含四步分析框架（detect→verify→diagnose→report）、明细数据（供应商/金额/发票号）、'
        + '法律依据引用、具体消除路径建议。报告为独立HTML文件，可直接交付。'},
]

# 由于直接替换steps数组太复杂，我们采用另一种方法：
# 直接替换 loadAnalyzeOverview 函数中的 steps 数组定义部分

# 找到 steps 数组的开始位置
steps_start = content.find("  var steps = [", content.find("function loadAnalyzeOverview"))
if steps_start == -1:
    print("ERROR: steps array not found")
else:
    print(f"Found steps array at position {steps_start}")
    # 找到 steps 数组的结束位置（下一个 "  ];"）
    steps_end = content.find("  ];", steps_start)
    if steps_end == -1:
        print("ERROR: steps array end not found")
    else:
        steps_end += 4  # 包括 "  ];"
        print(f"Steps array ends at position {steps_end}")
        print(f"Steps array length: {steps_end - steps_start}")
        
        # 生成新的steps数组字符串
        new_steps_str = "  var steps = [\n"
        for s in new_steps:
            new_steps_str += "    {" + f'n:\'{s["n"]}\', title:\'{s["title"]}\', icon:\'{s["icon"]}\',\n'
            new_steps_str += "     desc:'" + s["desc"] + "'},\n"
        new_steps_str += "  ];"
        
        print(f"New steps array length: {len(new_steps_str)}")
        
        # 替换
        content = content[:steps_start] + new_steps_str + content[steps_end:]
        
        with open(f, 'w', encoding='utf-8') as fp:
            fp.write(content)
        
        print("SUCCESS: Steps array replaced")

print("DONE")
