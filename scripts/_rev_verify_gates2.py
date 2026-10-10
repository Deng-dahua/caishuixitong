# -*- coding: utf-8 -*-
"""反向验证：两道新端到端闸门必须能变红，且恢复后文件 md5 一致。"""
import io, os, hashlib, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
files = ["engine/procurement_authenticity.py", "scripts/four_reports/company_1_full.json"]
bak = {f: io.open(os.path.join(ROOT, f), "rb").read() for f in files}

def restore():
    for f, b in bak.items():
        io.open(os.path.join(ROOT, f), "wb").write(b)

def run(fn):
    code = ("import sys; sys.path.insert(0,'tools'); sys.path.insert(0,'.');"
            "import audit_consistency as A;"
            "r=getattr(A,%r)();"
            "print('RED' if r else 'GREEN');"
            "[print('   ',x[0],str(x[2])[:100]) for x in r[:3]]" % fn)
    p = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (p.stdout or "") + (p.stderr or "")

# ① 把禁用词写回产出文案 → 必须变红
p = os.path.join(ROOT, files[0])
s = io.open(p, encoding="utf-8").read()
s2 = s.replace('"**证实或排除**，而不是靠统计口径推断。"',
               '"**证实或排除**，而不是靠统计指标推断。"', 1)
assert s2 != s
io.open(p, "w", encoding="utf-8", newline="\n").write(s2)
print("[case1 产出文案回填『指标』]"); print(run("check_detector_text_avoids_hard_ban"))
restore()

# ② 在真跑产物里注入一行静默失效留痕 → 必须变红
import json
p2 = os.path.join(ROOT, files[1])
d = json.loads(io.open(p2, encoding="utf-8").read())
rep = d.get("report") if isinstance(d.get("report"), dict) else d
assert isinstance(rep.get("pipeline_log"), list)
rep["pipeline_log"] = list(rep["pipeline_log"]) + ["跨文件逐月勾稽异常: name '_row_period' is not defined"]
io.open(p2, "w", encoding="utf-8", newline="\n").write(json.dumps(d, ensure_ascii=False))
print("[case2 真跑产物注入静默失效留痕]"); print(run("check_last_run_no_silent_domain_crash"))
restore()

for f, b in bak.items():
    a = hashlib.md5(io.open(os.path.join(ROOT, f), "rb").read()).hexdigest()
    assert a == hashlib.md5(b).hexdigest(), "恢复失败: " + f
print("恢复校验通过（md5 一致）")
