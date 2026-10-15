# -*- coding: utf-8 -*-
"""反向验证：`check_material_granularity_truthful` 闸门**真的会报错**。

★ 子进程逐轮（闸门读模块缓存，同进程改文件不生效 —— 首版测试方法错，误判"闸门失效"）。

三段注入：
- **A 假条款级**：标 `granularity=provision` 却清空 `provision_ids` ⇒ 应报"假条款级"；
- **B 非法 ID**：注入形状不合法 / 未登记法短码的 ID ⇒ 应报；
- **C 依据不成立**：把某材料的 `matched_provisions` 改成正文里不存在的条号 ⇒ 应报。

用法：`./.venv/Scripts/python.exe scripts/_verify_material_granularity_gate_reverse.py`
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CFG = ROOT / "config" / "legal_materials.json"

_CHILD = (
    "import sys, json; sys.path.insert(0, r'%s')\n"
    "from tools.audit_consistency import check_material_granularity_truthful as C\n"
    "print(json.dumps([[m for m in x] for x in C()], ensure_ascii=False))\n"
) % str(ROOT)


def _gate():
    r = subprocess.run([sys.executable, "-c", _CHILD], capture_output=True, text=True,
                       cwd=str(ROOT), encoding="utf-8", errors="replace")
    line = [ln for ln in (r.stdout or "").splitlines() if ln.strip().startswith("[")]
    if not line:
        raise RuntimeError("闸门无输出：%s / %s" % ((r.stdout or "")[-300:], (r.stderr or "")[-300:]))
    return [tuple(x) for x in json.loads(line[-1])]


def main() -> int:
    orig = CFG.read_text(encoding="utf-8")
    fails = []

    def _write(d):
        CFG.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")

    try:
        d0 = json.loads(orig)
        target = next(m for m in d0["materials"] if m.get("granularity") == "provision")

        # A 假条款级
        d = json.loads(orig)
        for m in d["materials"]:
            if m["material_id"] == target["material_id"]:
                m["provision_ids"] = []
        _write(d)
        iss = _gate()
        hit = any("假条款级" in x[2] for x in iss)
        print(f"[A] 清空 provision_ids 但标 provision ⇒ 报 {len(iss)} 项，命中={hit}")
        if not hit:
            fails.append("A 未报错：假条款级未被识别")

        # B 非法 ID
        d = json.loads(orig)
        for m in d["materials"]:
            if m["material_id"] == target["material_id"]:
                m["provision_ids"] = ["NOPE-9999"]
        _write(d)
        iss = _gate()
        hit = any("法短码" in x[2] and "NOPE" in x[2] for x in iss)
        print(f"[B] 注入未登记法短码 ID `NOPE-9999` ⇒ 报 {len(iss)} 项，命中={hit}")
        if not hit:
            fails.append("B 未报错：非法/未登记法短码未被识别")

        # C 依据不成立（指向**在索引里、但正文中不存在**的条号：
        #   首版注入了索引里也没有的 ID，被 C 段的"未入正文库"分支正确跳过 ⇒ 测法错，非闸门失效）
        d = json.loads(orig)
        for m in d["materials"]:
            if m["material_id"] == target["material_id"]:
                m["matched_provisions"] = [{"law_code": "TAX-ADMIN-LAW", "article": "第一条",
                                            "provision_id": "TAX-ADMIN-LAW-001",
                                            "matched_by": "法名紧邻条号", "in_library": True}]
                m["provision_ids"] = ["TAX-ADMIN-LAW-001"]
        _write(d)
        iss = _gate()
        hit = any("依据不成立" in x[2] for x in iss)
        print(f"[C] 指向在索引但正文无依据的条号 ⇒ 报 {len(iss)} 项，命中={hit}")
        if not hit:
            fails.append("C 未报错：正文无依据的条款级未被识别")

        # C2 两表脱同步（标 in_library=true 却不在索引里）
        d = json.loads(orig)
        for m in d["materials"]:
            if m["material_id"] == target["material_id"]:
                m["matched_provisions"] = [{"law_code": "TAX-ADMIN-LAW", "article": "第九百九十九条",
                                            "provision_id": "TAX-ADMIN-LAW-999",
                                            "matched_by": "法名紧邻条号", "in_library": True}]
                m["provision_ids"] = ["TAX-ADMIN-LAW-999"]
        _write(d)
        iss = _gate()
        hit = any("脱同步" in x[2] for x in iss)
        print(f"[C2] 标 in_library=true 却不在索引 ⇒ 报 {len(iss)} 项，命中={hit}")
        if not hit:
            fails.append("C2 未报错：两表脱同步未被识别")

        # 对照
        CFG.write_text(orig, encoding="utf-8")
        iss0 = _gate()
        print(f"[对照] 恢复原状 ⇒ 报 {len(iss0)} 项（期望 0）")
        if iss0:
            fails.append("对照失败：恢复后仍报 %d 项" % len(iss0))
    finally:
        CFG.write_text(orig, encoding="utf-8")

    print()
    if fails:
        print("反向验证 **FAIL**：")
        for f in fails:
            print("  ✗", f)
        return 1
    print("反向验证 **PASS**：A 假条款级 / B 非法 ID / C 依据不成立 三段均变红，恢复后归零。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
