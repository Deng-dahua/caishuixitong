"""M4/M5 反向验证：
  M4 拆掉 M06 的元发现豁免 ⇒ check_non_tax_law_not_misattributed 必须变红；
  M5 拆掉「待核事实：」前缀 ⇒ 同一闸门必须变红。

用法： ./.venv/Scripts/python.exe scripts/_mutate_m4.py {m4|m5|restore}
"""
import io
import sys

mode = sys.argv[1] if sys.argv[1:] else "m4"
NL_TXT = {}
for p in ("engine/self_learning.py", "engine/argumentation.py"):
    NL_TXT[p] = "\r\n" if ("\r\n" in io.open(p, encoding="utf-8", newline="").read()) else "\n"

if mode == "restore":
    for p in NL_TXT:
        io.open(p, "w", encoding="utf-8", newline="").write(
            io.open("scripts/_bk_" + p.replace("/", "_"), encoding="utf-8", newline="").read())
    print("restored")
    sys.exit(0)

if mode == "m4":
    p = "engine/self_learning.py"
    s = io.open(p, encoding="utf-8", newline="").read()
    NL = NL_TXT[p]
    old = ('    if not isinstance(finding, dict):' + NL +
           '        return ""' + NL)
    new = ('    if True:  # MUTATED(反向验证)' + NL +
           '        return "MUTATED 反向验证：豁免判据被拆掉"' + NL)
    n = s.count(old)
    if n != 1:
        print("MUTATION_FAILED matched=%d" % n)
        sys.exit(2)
    io.open(p, "w", encoding="utf-8", newline="").write(s.replace(old, new, 1))
    print("MUTATED m4")
else:
    p = "engine/argumentation.py"
    s = io.open(p, encoding="utf-8", newline="").read()
    NL = NL_TXT[p]
    old = ('    "需外部数据核验：",' + NL +
           '    "待核事实：",      # 外部数据待核验的账内信号（真实产出里数量最多的一类）')
    if old not in s:
        print("MUTATION_FAILED (prefix line not found)")
        sys.exit(2)
    s2 = s.replace(old, '    "需外部数据核验：",', 1)
    io.open(p, "w", encoding="utf-8", newline="").write(s2)
    print("MUTATED m5")
