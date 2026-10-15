# -*- coding: utf-8 -*-
"""反向验证 driver（**必须在独立子进程中逐轮调用**，脚本自身只做"改→跑→恢复"）。

用法：python /tmp/_rev19.py <case_no>
  1 = 报告表去掉「条款ID」列        → 期望 ③ 变红
  2 = 关联表注入孤儿映射            → 期望 ① 变红
  3 = 材料改成"关键词匹配"          → 期望 ⑥ 变红
  4 = rule_catalog.get 不带条款     → 期望 ④ 变红
  0 = 不注入（基线）                → 期望 0
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ★ 跨 bash / Python 必须用**绝对 Windows 路径**（项目铁律：Git Bash 的 `/c/...`
#   Python 不认）。PY 用 `sys.executable`（本脚本本身就跑在项目 venv 里）。
ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
TMP = Path(tempfile.gettempdir())

TARGETS = {
    1: ROOT / "engine" / "report_service.py",
    2: ROOT / "config" / "legal_mappings.json",
    3: ROOT / "config" / "legal_materials.json",
    4: ROOT / "engine" / "rule_catalog.py",
}


def run_gate() -> str:
    code = (r"""
import sys; sys.path.insert(0,'.'); sys.path.insert(0,'tools')
import audit_consistency as AC
i = AC.check_legal_mapping_wiring()
print('N=%d' % len([x for x in i if x[0]=='ERROR']))
for x in i[:3]:
    print('  -', x[2][:100])
""")
    r = subprocess.run([PY, "-c", code], cwd=str(ROOT), capture_output=True, text=True)
    return (r.stdout or r.stderr).strip()


def main() -> int:
    case = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    if case == 0:
        print("基线：", run_gate())
        return 0
    p = TARGETS[case]
    bak = TMP / ("rev19_%d.bak" % case)
    shutil.copy2(p, bak)
    try:
        if case == 1:
            s = p.read_text(encoding="utf-8")
            s2 = s.replace('"条款ID", ', "")
            assert s2 != s, "未命中「条款ID」列定义"
            p.write_text(s2, encoding="utf-8")
        elif case == 2:
            d = json.loads(p.read_text(encoding="utf-8"))
            d["mappings"].append({"rule_id": "RL-NOT-EXIST-999", "raw_basis": "x",
                                  "law": "x", "law_code": "X", "article": "第一条",
                                  "provision_id": "X-001", "verified": True,
                                  "provision_source": "", "content_sha256": ""})
            p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        elif case == 3:
            d = json.loads(p.read_text(encoding="utf-8"))
            d["materials"][0]["matched_refs"][0]["matched_by"] = "关键词匹配"
            p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        elif case == 4:
            s = p.read_text(encoding="utf-8")
            s2 = s.replace("return _attach_legal(out, with_content=True)", "return out")
            assert s2 != s, "未命中 get() 的 _attach_legal 调用"
            p.write_text(s2, encoding="utf-8")
        out = run_gate()
        print("用例%d 注入后：%s" % (case, out))
    finally:
        shutil.copy2(bak, p)
        bak.unlink()
    print("用例%d 恢复后：" % case, run_gate())
    return 0


if __name__ == "__main__":
    sys.exit(main())
