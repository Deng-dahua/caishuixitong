"""M2 反向验证注入脚本：颠倒 _infer_law_ref 中「非税表 / 税表」的判定顺序。

用法：  ./.venv/Scripts/python.exe scripts/_mutate_m2.py

注入后 `check_non_tax_law_not_misattributed()` 必须变红（否则闸门本身是假的）。
用完 `cp scripts/_bk_self_learning.py engine/self_learning.py` 还原。
"""
import io
import sys

NL = "\r\n" if ("\r\n" in io.open("engine/self_learning.py", encoding="utf-8", newline="").read()) else "\n"

OLD = (
    "        for keyword in _NON_TAX_LAW_KEYWORDS:" + NL +
    "            if keyword in ftype:" + NL +
    "                return _NON_TAX_LAW_MAP[keyword]" + NL +
    "        for keyword, law in _TAX_LAW_MAP.items():" + NL +
    "            if keyword in ftype:" + NL +
    "                return law" + NL
)
NEW = (
    "        for keyword, law in _TAX_LAW_MAP.items():" + NL +
    "            if keyword in ftype:" + NL +
    "                return law" + NL +
    "        for keyword in _NON_TAX_LAW_KEYWORDS:" + NL +
    "            if keyword in ftype:" + NL +
    "                return _NON_TAX_LAW_MAP[keyword]" + NL
)

path = "engine/self_learning.py"
s = io.open(path, encoding="utf-8", newline="").read()
n = s.count(OLD)
if sys.argv[1:] and sys.argv[1] == "restore":
    io.open(path, "w", encoding="utf-8", newline="").write(io.open("scripts/_bk_self_learning.py", encoding="utf-8", newline="").read())
    print("restored")
    sys.exit(0)
if n != 1:
    print("MUTATION_FAILED matched=%d" % n)
    sys.exit(2)
io.open(path, "w", encoding="utf-8", newline="").write(s.replace(OLD, NEW, 1))
print("MUTATED ok NL=%r" % NL)
