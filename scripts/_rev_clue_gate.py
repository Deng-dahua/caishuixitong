# -*- coding: utf-8 -*-
"""反向验证：故意破坏 clue_chain 的**四条行为**，确认闸门真的变红；逐项还原后归零。

（首版用的两个变异是"无效变异"——构造的用例交集=0，任何阈值都不变 ⇒ 白过。
  现改为"真能破坏"的变异，其中 M-a/M-d 分别复现 D6 病根与 D7 误配。）
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NL = chr(10)
CC = os.path.join(ROOT, "engine", "clue_chain.py")

RUN = (
    "import sys; sys.path.insert(0, %r);"
    "from tools.audit_consistency import check_report_consistency as f;"
    "iss=[i for i in f() if 'clue_chain.py' in i[1]];"
    "print(len(iss));"
    "[print('   ', i[0], i[2][:70]) for i in iss]"
) % ROOT

# 各变异：(名称, 旧串, 新串)
MUTS = [
    ("M-a 复现 D6：取不到对题读数时回落全文数字（拿别的环节的数顶替）",
     "            # 取不到对题读数：如实标注缺的是\"资料\"还是\"程序\"，**不拿别的环节的数顶替**\n"
     "            _reason = _gap_reason(tpl.get(\"source\", \"\"))",
     "            # 取不到对题读数：如实标注缺的是\"资料\"还是\"程序\"，**不拿别的环节的数顶替**\n"
     "            if numbers:\n"
     "                nodes.append({\"step\": step_no, \"source\": tpl.get(\"source\", \"\"),\n"
     "                              \"action\": tpl.get(\"action\", \"\"),\n"
     "                              \"output\": tpl.get(\"output\", \"\"),\n"
     "                              \"observed\": \"计算得到：\" + \"、\".join(numbers[:3]),\n"
     "                              \"trace_ref\": \"x\", \"has_data\": True})\n"
     "                continue\n"
     "            _reason = _gap_reason(tpl.get(\"source\", \"\"))"),
    ("M-b 复现 D5：资料匹配退回\"整片原文精确比 15 类名\"（不经 categories_of 归一）",
     "        cats = _mn.categories_of(piece) or []",
     "        cats = ([piece] if piece in _prov else [])"),
    ("M-c 空清单早退：把\"缺资料\"说成\"程序待完善\"",
     "    _prov = set()",
     "    if not _prov_raw:\n        return False, []\n    _prov = set()"),
    ("M-d 复现 D7：对题阈值降到 3（误配不相干要件）",
     "_ON_TOPIC_MIN_BIGRAMS = 4",
     "_ON_TOPIC_MIN_BIGRAMS = 3"),
]


def read():
    return io.open(CC, "r", encoding="utf-8", newline="").read()


def write(s):
    io.open(CC, "w", encoding="utf-8", newline="").write(s)


def run_gate():
    r = subprocess.run([sys.executable, "-c", RUN], capture_output=True, text=True,
                       cwd=ROOT, encoding="utf-8", errors="replace")
    return (r.stdout or "") + (r.stderr or "")


base = read()
print("=== 基线（未破坏）===")
print(run_gate().strip()[:200])

for name, old, new in MUTS:
    cur = read()
    s = cur.replace("\r\n", NL)
    if s.count(old) != 1:
        print("\n!! %s anchor 命中 %d 次 —— 未生效，不算通过" % (name, s.count(old)))
        continue
    s = s.replace(old, new, 1)
    write(s.replace(NL, "\r\n") if "\r\n" in cur else s)
    out = run_gate().strip()
    n = out.splitlines()[0] if out else "?"
    print("\n=== %s ⇒ 闸门报 %s 项 ===" % (name, n))
    for ln in out.splitlines()[1:4]:
        print(ln)
    write(base)

print("\n=== 全部还原后 ===")
print(run_gate().strip()[:200])
print("还原逐字节一致:", read() == base)
