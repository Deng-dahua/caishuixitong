# -*- coding: utf-8 -*-
"""`check_law_code_unique` 的**反向验证** —— 防"假闸门"。

对 `config/legal_law_codes.json` 逐项注入**已知缺陷**，每次都在**新子进程**里
跑闸门（项目铁律：子进程逐轮，避免模块缓存假通过），断言"必须变红"；
最后恢复并断言"必须归零"。

三段注入（对应闸门判据 A/B/C）：
  A 同一部法两个短码 —— 复制一行、改 `code`、保留同一 `name`；
  B `code` 重复     —— 复制一行、改 `name`、保留同一 `code`；
  C 前缀不符        —— 把某行 `provision_id_prefix` 改掉。

用法：`./.venv/Scripts/python.exe scripts/_verify_law_code_gate_reverse.py`
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config" / "legal_law_codes.json"

_CHILD = (
    "import sys; sys.path.insert(0, r'%s')\n"
    "from tools.audit_consistency import check_law_code_unique as C\n"
    "r = C()\n"
    "print('ISSUES %%d' %% len(r))\n"
    "for _l, _f, _m in r:\n"
    "    print(' -', _m[:130])\n"
) % str(ROOT)


def _gate() -> str:
    r = subprocess.run([sys.executable, "-c", _CHILD], capture_output=True, text=True,
                       cwd=str(ROOT), encoding="utf-8", errors="replace")
    return (r.stdout or "") + (r.stderr or "")


def main() -> int:
    orig = CFG.read_text(encoding="utf-8")
    base = json.loads(orig)
    fails = []

    def run(name: str, mutate, expect: str) -> None:
        d = copy.deepcopy(base)
        mutate(d)
        CFG.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        out = _gate()
        hit = ("ISSUES 0" not in out) and (expect in out)
        print("[%s] %s" % ("变红" if hit else "未变红", name))
        if not hit:
            print("     输出：%s" % out.strip()[:220])
            fails.append(name)

    try:
        def _same_law_two_codes(d):
            src = next(x for x in d["laws"] if x.get("name"))
            q = copy.deepcopy(src)
            q["code"] = "ZZ-DUP-TEST"
            q["provision_id_prefix"] = "ZZ-DUP-TEST-"
            d["laws"].append(q)
        run("A 同一部法两个短码 ⇒ 必须报`多个短码`", _same_law_two_codes, "多个短码")

        def _dup_code(d):
            src = next(x for x in d["laws"] if x.get("name"))
            q = copy.deepcopy(src)
            q["name"] = str(src["name"]) + "（测试副本）"
            q["aliases"] = []
            d["laws"].append(q)
        run("B code 重复 ⇒ 必须报`重复`", _dup_code, "重复")

        def _bad_prefix(d):
            d["laws"][0]["provision_id_prefix"] = "WRONG-"
        run("C 前缀与短码不符 ⇒ 必须报`前缀`", _bad_prefix, "前缀")
    finally:
        CFG.write_text(orig, encoding="utf-8")

    out = _gate()
    ok = "ISSUES 0" in out
    print("[%s] 恢复后必须归零" % ("归零" if ok else "仍报错"))
    if not ok:
        fails.append("恢复后仍报错")

    print()
    if fails:
        print("反向验证 **FAIL** —— 以下注入未被抓出：%s" % "、".join(fails))
        return 1
    print("反向验证 **PASS**：三类注入全部变红、恢复后归零（判据非空转）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
