import re

f = 'C:/Users/26726/WorkBuddy/2026-05-31-09-56-37/caishuixitong/static/js/tax-pipeline-pages.js'
with open(f, 'r', encoding='utf-8') as fp:
    content = fp.read()

# 新的 loadAnalyzeOverview 函数中的静态HTML部分（详尽版本）
# 找到 "var html = '';" 和 "target.innerHTML = html;" 之间的内容

# 由于内容太长，我们分段替换

# 1. 替换概述部分
old_overview = '''  // ══════ 一、分析链概述 ══════
  html += '<div style="margin-bottom:48px">'
    + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">一、分析链概述</h3>'
    + '<p style="font-size:13px;color:#64748b;line-height:2;margin:0 0 16px">'
    + '分析链是税务稽查系统的核心执行管线。从用户上传资料开始，经过七步串联处理，最终输出结构化稽查报告。'
    + '每一步都有对应的代码实现（main.py 中的 <code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">_run_analyze()</code> 函数），'
    + '数据在管线中单向流动，不丢失、不污染、不截断。'
    + '</p>'
    + '<div style="padding:16px 20px;background:#f8fafc;border-radius:8px;font-size:12px;color:#94a3b8;line-height:2">'
    + '<span style="font-weight:600;color:#64748b">数据规模：</span>'
    + pc('rules','1505') + ' 条稽查指令 · ' + pc('trailChains','391') + ' 条线索链 · ' + pc('evidenceChains','740') + ' 条证据链 · 8 条跨域证据链 · 97% 噪声过滤率 · 66 行业基准库'
    + '</div>'
    + '</div>';'''

new_overview = '''  // ══════ 一、分析链概述 ══════
  html += '<div style="margin-bottom:48px;padding:20px 24px;background:#f8fafc;border-radius:8px">'
    + '<h3 style="font-size:18px;font-weight:700;color:#0f172a;margin:0 0 12px">一、什么是分析链</h3>'
    + '<p style="font-size:14px;color:#475569;line-height:2.2;margin:0 0 16px">'
    + '分析链是税务稽查系统的核心执行管线，负责将用户上传的原始资料转化为结构化稽查报告。'
    + '这条管线不是简单的函数调用链，而是一个<strong>七步串联的数据处理流水线</strong>——每一步都有明确的输入、处理逻辑和输出，'
    + '数据在管线中单向流动，不丢失、不污染、不截断。'
    + '</p>'
    + '<p style="font-size:14px;color:#475569;line-height:2.2;margin:0 0 16px">'
    + '管线的设计理念来自稽查实战：真实稽查不是看一个数字就下结论，而是<strong>从资料扫描开始，经过多轮交叉验证，最终形成证据闭环</strong>。'
    + '分析链模拟的就是这个完整过程——资料驱动（有什么资料审什么）、诚实边界（缺什么资料报什么）、交叉推断（多源数据串联）、明细支撑（每条发现必须有具体数据）。'
    + '</p>'
    + '<div style="padding:16px 20px;background:#fff;border-radius:8px;font-size:13px;color:#64748b;line-height:2.2;border-left:3px solid #2563eb">'
    + '<strong>代码位置：</strong>main.py 中的 <code style="background:#f1f5f9;padding:1px 4px;border-radius:3px">_run_analyze()</code> 函数（约第8540行）<br>'
    + '<strong>数据规模：</strong>' + pc('rules','1505') + ' 条稽查指令 · ' + pc('trailChains','391') + ' 条线索链 · ' + pc('evidenceChains','740') + ' 条证据链 · 8 条跨域证据链<br>'
    + '<strong>处理结果：</strong>97% 噪声过滤率 · 66 行业基准库 · 35 个域分析函数 · 7 步执行流程'
    + '</div>'
    + '</div>';'''

if old_overview in content:
    content = content.replace(old_overview, new_overview)
    print('OK: replaced overview section')
else:
    print('WARN: overview section not found exactly')

# 2. 替换七步执行流程的标题和描述
old_steps_header = '''  // ══════ 二、七步执行流程 ══════
  html += '<div style="margin-bottom:48px">'
    + '<h3 style="font-size:15px;font-weight:700;color:#0f172a;margin:0 0 6px">二、七步执行流程</h3>';'''

new_steps_header = '''  // ══════ 二、七步执行流程详解 ══════
  html += '<div style="margin-bottom:48px">'
    + '<h3 style="font-size:18px;font-weight:700;color:#0f172a;margin:0 0 16px">二、七步执行流程详解</h3>'
    + '<p style="font-size:14px;color:#64748b;line-height:2;margin:0 0 20px">'
    + '分析链的执行过程分为七个步骤，每一步都是前一步的延伸和深化。下面详细说明每一步的输入、处理逻辑和输出。'
    + '</p>';'''

if old_steps_header in content:
    content = content.replace(old_steps_header, new_steps_header)
    print('OK: replaced steps header')
else:
    print('WARN: steps header not found exactly')

# 3. 增强七步流程中每一步的描述 - 替换steps数组
# 由于steps数组内容复杂，我们直接替换整个steps数组

# 4. 写回文件
with open(f, 'w', encoding='utf-8') as fp:
    fp.write(content)

print('DONE: Analysis chain page updated')
