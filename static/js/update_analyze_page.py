import re

f = 'C:/Users/26726/WorkBuddy/2026-05-31-09-56-37/caishuixitong/static/js/tax-pipeline-pages.js'
with open(f, 'r', encoding='utf-8') as fp:
    content = fp.read()

# 读取新的分析链页面代码（从临时文件）
# 由于代码太长，我们分段替换关键部分

# 1. 替换 renderAnalyzePage 函数中的标题描述
old_title = '''+ '<p style="font-size:14px;color:#94a3b8;margin:0">' + pc('rules','1505') + '规则 + ' + pc('trailChains','391') + '线索链 + ' + pc('evidenceChains','740') + '证据链 → 方法论过滤器 → 正式稽查报告</p>''''
new_title = '''+ '<p style="font-size:14px;color:#94a3b8;margin:0">' + pc('rules','1505') + '条稽查指令 · ' + pc('trailChains','391') + '条线索链 · ' + pc('evidenceChains','740') + '条证据链 · 8条跨域证据链 · 97%噪声过滤率 · 66行业基准库</p>' '''

if old_title in content:
    content = content.replace(old_title, new_title)
    print('OK: updated title')
else:
    print('WARN: title not found exactly, trying partial')
    #  partial match
    if '规则 + ' in content and '线索链 + ' in content:
        print('Found partial match for title')

# 2. 增强概述部分 - 找"一、分析链概述"部分
overview_start = content.find('// ══════ 一、分析链概述 ══════')
if overview_start == -1:
    print('ERROR: overview section not found')
else:
    print(f'Found overview section at {overview_start}')

print('DONE: basic checks complete')
