# -*- coding: utf-8 -*-
"""把三份"修正记录"里记录的**用户指令交付物清单**抽出来，与实际文件名逐个对照。"""
import pathlib, re
D = pathlib.Path('.')
actual = sorted(p.name for p in D.glob('*.md'))
print('实际文件名（%d）：' % len(actual))
for f in actual: print('   ', f)
print()
for f in ('第1批修正记录.md', '第1批最终修正记录.md', '第1批终极修正记录.md'):
    t = (D / f).read_text(encoding='utf-8')
    names = re.findall(r'`([^`\n]{2,60}\.md)`', t) + re.findall(r'《([^》\n]{2,60}\.md)》', t)
    names = sorted({n for n in names if '/' not in n and '\\' not in n})
    print('=== %s 里出现过的**.md 名字**（%d 个）===' % (f, len(names)))
    miss = [n for n in names if n not in actual]
    for n in names:
        print('   %s %s' % ('✅' if n in actual else '❌ 目录里没有', n))
    print()
