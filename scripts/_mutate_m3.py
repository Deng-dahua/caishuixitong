"""M3 反向验证：把 ⑲ 的 not_concluded 改回旧的 checked_miss，闸门必须变红。

用法： ./.venv/Scripts/python.exe scripts/_mutate_m3.py   （加 restore 参数则还原）
"""
import io
import sys

path = "engine/constituent_checkpoint.py"
s = io.open(path, encoding="utf-8", newline="").read()
NL = "\r\n" if "\r\n" in s else "\n"

OLD = (
    '            # ★⑲：资料已取得 = 有得查；**没有针对该要件的核对证据 = 没查过**，'
    + NL +
    '            #   不得写成"未发现符合"。如实标「未形成核对结论」。'
    + NL +
    '            conclusion = "not_concluded"'
)
NEW = (
    '            # MUTATED(反向验证)：回退到旧行为'
    + NL +
    '            conclusion = "checked_miss"'
)

if sys.argv[1:] and sys.argv[1] == "restore":
    io.open(path, "w", encoding="utf-8", newline="").write(
        io.open("scripts/_bk_constituent_checkpoint.py", encoding="utf-8", newline="").read())
    print("restored")
    sys.exit(0)

n = s.count(OLD)
if n != 1:
    print("MUTATION_FAILED matched=%d" % n)
    sys.exit(2)
io.open(path, "w", encoding="utf-8", newline="").write(s.replace(OLD, NEW, 1))
print("MUTATED ok")
