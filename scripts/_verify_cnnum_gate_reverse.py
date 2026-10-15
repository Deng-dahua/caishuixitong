# -*- coding: utf-8 -*-
"""反向验证：`check_cnnum_single_source` 闸门**真的会报错**（防"假闸门"）。

判据：
- **A 新增私有一份** ⇒ 在 `engine/` 下写一个含中文数字表的临时模块，闸门必须报 ERROR；
- **B 权威被改坏** ⇒ 把 `engine/cnnum.py` 的「百」位处理破坏一次，行为断言必须失败。

用法：`./.venv/Scripts/python.exe scripts/_verify_cnnum_gate_reverse.py`

★ 必须**子进程逐轮**：闸门读的是**运行期已导入**的 `engine.cnnum`，
  同进程内改文件后仍命中 Python 模块缓存（首版反向验证因此误判"闸门失效"，
  实为测试方法错）。每段破坏后起新进程 ⇒ 加载的是改后的文件。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CN = ROOT / "engine" / "cnnum.py"
PLANT = ROOT / "engine" / "_tmp_cnnum_plant.py"

_CHILD = (
    "import sys, json; sys.path.insert(0, r'%s')\n"
    "from tools.audit_consistency import check_cnnum_single_source as C\n"
    "print(json.dumps([[m for m in x] for x in C()], ensure_ascii=False))\n"
) % str(ROOT)


def _gate():
    """**新进程**跑闸门（避开模块缓存），返回 [(level, file, msg)]。"""
    r = subprocess.run([sys.executable, "-c", _CHILD], capture_output=True, text=True,
                       cwd=str(ROOT), encoding="utf-8", errors="replace")
    line = [ln for ln in (r.stdout or "").splitlines() if ln.strip().startswith("[")]
    if not line:
        raise RuntimeError("闸门子进程无输出：%s / %s" % ((r.stdout or "")[-200:], (r.stderr or "")[-200:]))
    return [tuple(x) for x in json.loads(line[-1])]


def main() -> int:
    orig = CN.read_text(encoding="utf-8")
    fails = []
    try:
        # ── A 注入第 N 份私有实现 ──
        PLANT.write_text(
            "# -*- coding: utf-8 -*-\n"
            "_CN = {\"零\": 0, \"一\": 1, \"二\": 2, \"十\": 10}\n\n\n"
            "def my_cn(s):\n    return _CN.get(s)\n",
            encoding="utf-8")
        iss = _gate()
        hit = any("_tmp_cnnum_plant.py" in f for _l, f, _m in iss)
        print(f"[A] 注入私有中文数字表 ⇒ 报 {len(iss)} 项，命中判据={hit}")
        if not hit:
            fails.append("A 未报错：engine/ 下新增私有中文数字表，闸门未识别")
        PLANT.unlink(missing_ok=True)

        # ── B 破坏权威（把"百"当 10 处理）──
        CN.write_text(orig.replace('"百": 100', '"百": 10'), encoding="utf-8")
        iss = _gate()
        hit_b = any("行为断言失败" in m for _l, _f, m in iss)
        print(f"[B] 破坏「百」位 ⇒ 报 {len(iss)} 项，命中判据={hit_b}")
        if not hit_b:
            fails.append("B 未报错：权威实现的「百」位被改坏，行为断言未变红")
        # ── B2 破坏排序键（模拟旧事故：不乘 100）──
        CN.write_text(orig.replace("return num * 100 + (sub or 0)",
                                   "return num"), encoding="utf-8")
        iss = _gate()
        hit_b2 = any("非严格递增" in m for _l, _f, m in iss)
        print(f"[B2] 模拟旧排序键事故（不乘100）⇒ 报 {len(iss)} 项，命中判据={hit_b2}")
        if not hit_b2:
            fails.append("B2 未报错：排序键退回旧事故写法，闸门未识别")

        # ── 对照 ──
        CN.write_text(orig, encoding="utf-8")
        iss0 = _gate()
        print(f"[对照] 恢复原状 ⇒ 报 {len(iss0)} 项（期望 0）")
        if iss0:
            fails.append("对照失败：恢复后仍报 %d 项" % len(iss0))
    finally:
        CN.write_text(orig, encoding="utf-8")
        PLANT.unlink(missing_ok=True)

    print()
    if fails:
        print("反向验证 **FAIL**：")
        for f in fails:
            print("  ✗", f)
        return 1
    print("反向验证 **PASS**：A 新增私有实现 / B 破坏位数 / B2 排序键退回旧事故 三段均变红，恢复后归零。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
