# -*- coding: utf-8 -*-
"""反向验证（直调 D1 判据，毫秒级）：① 改坏数字 ⇒ 必报；② 撤 R1 豁免 ⇒ 必报；恢复后必绿。"""
import json
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from engine import doc_consistency_core as c  # noqa: E402

doc = Path("docs/第01批_触发条件与认定要件分离/05_回归测试报告.md")
cfg = Path("config/doc_consistency.json")
orig_doc = doc.read_text(encoding="utf-8")
orig_cfg = cfg.read_text(encoding="utf-8")


def d1_error_lines():
    c.reload_config()
    iss = c.check_numbers()
    return sorted({i["where"] for i in iss if i["level"] == "ERROR"})


# 基线
base = d1_error_lines()
print("基线 D1 ERROR 处数:", len(base), base[:5])

# 反验① 改坏数字
doc.write_text(orig_doc.replace("| passed | **1569** |", "| passed | **1553** |"), encoding="utf-8")
e1 = d1_error_lines()
doc.write_text(orig_doc, encoding="utf-8")
ok1 = any("05_回归测试报告.md:19" in w for w in e1)
print("反验① 改坏 ⇒ ERROR 处数=%d，命中 05:19=%s → %s" % (len(e1), ok1, "PASS" if ok1 else "FAIL"))

# 反验② 撤 R1 豁免
spec = json.loads(orig_cfg)
spec["quote_files"] = [f for f in spec["quote_files"] if f != "R1_Skill修订记录.md"]
cfg.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
e2 = d1_error_lines()
cfg.write_text(orig_cfg, encoding="utf-8")
ok2 = any("R1_Skill修订记录.md:148" in w for w in e2)
print("反验② 撤豁免 ⇒ ERROR 处数=%d，命中 R1:148=%s → %s" % (len(e2), ok2, "PASS" if ok2 else "FAIL"))

# 恢复复验
e3 = d1_error_lines()
print("恢复后 D1 ERROR 处数=%d → %s" % (len(e3), "PASS" if len(e3) == 0 else "FAIL"))

assert doc.read_text(encoding="utf-8") == orig_doc, "05 未还原"
assert cfg.read_text(encoding="utf-8") == orig_cfg, "config 未还原"
print("文件字节级还原 ✔")
