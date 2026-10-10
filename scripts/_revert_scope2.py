# -*- coding: utf-8 -*-
"""按行区间移除 `_SCOPE_QUALIFIERS`（表定义 + 使用循环），不依赖精确文本匹配。"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, "engine", "evidence_chain.py")
NL = chr(10)
CRLF = chr(13) + chr(10)

raw = io.open(P, "r", encoding="utf-8", newline="").read()
has_crlf = CRLF in raw
lines = raw.replace(CRLF, NL).split(NL)

# 1) 找 "for _q in _SCOPE_QUALIFIERS:" 所在行，连同其下 2 行一起删（从后往前删，避免索引位移）
i_loop = next(i for i, ln in enumerate(lines) if "_SCOPE_QUALIFIERS:" in ln and ln.strip().startswith("for "))
assert lines[i_loop + 1].strip() == "if _q in _extra:", lines[i_loop + 1]
assert lines[i_loop + 2].strip() == "return _q", lines[i_loop + 2]
del lines[i_loop:i_loop + 3]
print("删除使用循环 3 行 @", i_loop)

# 2) 找表定义行，向上吃掉紧邻的注释块与空行，向下吃掉到以 ')' 结尾的行
i_def = next(i for i, ln in enumerate(lines) if ln.startswith("_SCOPE_QUALIFIERS: tuple = ("))
i_end = i_def
while not lines[i_end].rstrip().endswith(")"):
    i_end += 1
i_start = i_def
while i_start > 0 and (lines[i_start - 1].startswith("#") or lines[i_start - 1].strip() == ""):
    i_start -= 1
# 保留一个空行分隔（不吞掉前一段的收尾空行）
if i_start > 0 and lines[i_start].strip() == "":
    i_start += 1
del lines[i_start:i_end + 1]
print("删除表定义区 [%d, %d) 共 %d 行" % (i_start, i_end + 1, i_end + 1 - i_start))

out = NL.join(lines)
io.open(P, "w", encoding="utf-8", newline="").write(out.replace(NL, CRLF) if has_crlf else out)
print("剩余 _SCOPE_QUALIFIERS 出现次数 =", out.count("_SCOPE_QUALIFIERS"))
print("保留 _SUBSTANTIVE_QUALIFIERS 出现次数 =", out.count("_SUBSTANTIVE_QUALIFIERS"))
