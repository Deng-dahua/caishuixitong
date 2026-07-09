# -*- coding: utf-8 -*-
# 将 tax-pipeline-pages.js 的 81-686 行（旧文件解析函数块）替换为 _fp_block.js
import io

TARGET = 'static/js/tax-pipeline-pages.js'
BLOCK = '_fp_block.js'

with io.open(TARGET, 'r', encoding='utf-8') as f:
    lines = f.readlines()

with io.open(BLOCK, 'r', encoding='utf-8') as f:
    block = f.read()

# 校验边界：第81行应为 renderFileParsingPage 定义（1-based -> index 80）
assert 'function renderFileParsingPage' in lines[80], '边界错误: 第81行不是 renderFileParsingPage: ' + lines[80][:60]
# 第686行应为 renderFileParsingResult 的结束 }（1-based -> index 685）
assert lines[685].rstrip('\n') == '}', '边界错误: 第686行不是单独的 }: ' + repr(lines[685])
# 第688行应为 renderDomainAnalysisPage
assert 'renderDomainAnalysisPage' in lines[687], '边界错误: 第688行不是 renderDomainAnalysisPage: ' + lines[687][:60]

before = lines[:80]          # 1-80 行
after = lines[686:]          # 687 行及之后（保留 687 空行 + 域分析）

new_content = ''.join(before) + block.rstrip('\n') + '\n' + ''.join(after)

with io.open(TARGET, 'w', encoding='utf-8') as f:
    f.write(new_content)

print('替换完成。新文件行数:', new_content.count('\n') + 1)
