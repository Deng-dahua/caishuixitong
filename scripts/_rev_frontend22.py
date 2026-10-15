# -*- coding: utf-8 -*-
"""反向验证 driver（**必须子进程逐轮**，脚本自身只做"改→跑→恢复"）。

用法：python scripts/_rev_frontend22.py <case_no>
  1 = 删专题页侧边栏入口        → 期望 B 变红
  2 = 把 /legal-topics/stats 挪到 {topic_id} 之后 → 期望 C 变红
  3 = 前端写死专题编号          → 期望 E1 变红
  4 = 专题读层另写正文读取      → 期望 D 变红（真读盘判据）
  5 = 材料层去掉 granularity 说明 → 期望 G 变红（专题材料缺口无 reason 路径）
  0 = 基线                      → 期望 0
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
TMP = Path(tempfile.gettempdir())


def run_gate() -> str:
    code = ("import sys; sys.path.insert(0,'.'); sys.path.insert(0,'tools')\n"
            "import audit_consistency as AC\n"
            "i = AC.check_legal_frontend_wiring()\n"
            "print('N=%d' % len([x for x in i if x[0]=='ERROR']))\n"
            "for x in i[:2]: print('  -', x[2][:96])\n")
    r = subprocess.run([PY, "-c", code], cwd=str(ROOT), capture_output=True, text=True)
    return (r.stdout or r.stderr).strip()


TARGETS = {
    1: ROOT / "static" / "index.html",
    2: ROOT / "legal_api.py",
    3: ROOT / "static" / "js" / "legal_topics.js",
    4: ROOT / "engine" / "legal_topics.py",
    5: ROOT / "engine" / "legal_topics.py",
}


def main() -> int:
    case = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    if case == 0:
        print("基线：", run_gate())
        return 0
    p = TARGETS[case]
    bak = TMP / ("rev22_%d.bak" % case)
    shutil.copy2(p, bak)
    try:
        s = p.read_text(encoding="utf-8")
        if case == 1:
            s2 = s.replace("location.href='/legal-topics'", "location.href='/legal-library'")
            assert s2 != s, "未命中侧边栏入口"
            p.write_text(s2, encoding="utf-8")
        elif case == 2:
            # 把 stats 路由块挪到 {topic_id} **之后**（用 {topic_id}/documents 作锚 ⇒ 确实在其后）
            m = re.search(r'@router\.get\("/legal-topics/stats".*?\n\n\n', s, re.S)
            assert m, "未命中 stats 路由块"
            block = m.group(0)
            s2 = s.replace(block, "")
            anchor = '@router.get("/legal-topics/{topic_id}/documents"'
            assert anchor in s2, "未命中锚点"
            s2 = s2.replace(anchor, block + anchor, 1)
            # 自检：注入后 stats 必须**真的**排在 {topic_id} 之后
            assert s2.find('"/legal-topics/stats"') > s2.find('"/legal-topics/{topic_id}"'), \
                "注入未生效（顺序未反转）"
            p.write_text(s2, encoding="utf-8")
        elif case == 3:
            s2 = s + "\nvar HARD = ['TOPIC-001','TOPIC-002'];\n"
            p.write_text(s2, encoding="utf-8")
        elif case == 4:
            s2 = s.replace('got = LM.content_of(pid)',
                           'got = json.loads((Path(__file__).resolve().parent.parent / "static" / "legal_library.json").read_text(encoding="utf-8"))')
            assert s2 != s, "未命中 content_of 调用"
            p.write_text(s2, encoding="utf-8")
        elif case == 5:
            # 去掉专题材料缺口的 reason 分支（模拟"静默空"回归）
            s2 = s.replace('"reason": ("本专题**暂无已核实条款** ⇒ 无法按法定位相关材料"',
                           '"zzz": ("本专题**暂无已核实条款** ⇒ 无法按法定位相关材料"')
            assert s2 != s, "未命中 reason 分支"
            p.write_text(s2, encoding="utf-8")
        print("用例%d 注入后：%s" % (case, run_gate()))
    finally:
        shutil.copy2(bak, p)
        bak.unlink()
    print("用例%d 恢复后：" % case, run_gate())
    return 0


if __name__ == "__main__":
    sys.exit(main())
