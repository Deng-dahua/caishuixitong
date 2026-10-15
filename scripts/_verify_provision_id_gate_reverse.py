# -*- coding: utf-8 -*-
"""`check_provision_id_unique` 的**反向验证** —— 防"假闸门"。

做法（项目铁律：反向验证**必须子进程逐轮**，否则模块缓存会让改动不生效）：
对 `config/legal_provisions.json` 逐项注入**已知缺陷**，
每次都在**新子进程**里跑闸门，断言"必须变红"；最后恢复并断言"必须归零"。

四段注入（对应闸门判据 A/B/C/D）：
  A 撞号        —— 把某条的 `provision_id` 改成与另一条相同；
  B 前缀不符    —— 把某条的 `law_code` 改掉（ID 前缀与它不一致）；
  C 短码多法名  —— 造一条法名不同、短码相同的条目（同一条文会存两份）；
  D 真缺口      —— 把有条号条目的 `provision_id` 清空。

用法：`./.venv/Scripts/python.exe scripts/_verify_provision_id_gate_reverse.py`
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "config" / "legal_provisions.json"

_CHILD = (
    "import sys; sys.path.insert(0, r'%s')\n"
    "from tools.audit_consistency import check_provision_id_unique as C\n"
    "r = C()\n"
    "print('ISSUES %%d' %% len(r))\n"
    "for _l, _f, _m in r:\n"
    "    print(' -', _m[:120])\n"
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
        # A 撞号
        def _dup(d):
            ps = [p for p in d["provisions"] if p.get("provision_id")]
            ps[1]["provision_id"] = ps[0]["provision_id"]
        run("A 注入撞号 ⇒ 必须报`撞号`", _dup, "撞号")

        # B 前缀与 law_code 不符
        def _pref(d):
            p = next(x for x in d["provisions"] if x.get("provision_id"))
            p["law_code"] = "WRONG-CODE"
        run("B 注入短码不符 ⇒ 必须报`前缀`", _pref, "前缀")

        # C 同一短码两个法名
        def _multi(d):
            p = next(x for x in d["provisions"] if x.get("provision_id"))
            q = copy.deepcopy(p)
            q["law"] = p["law"] + "（另一个法名）"
            d["provisions"].append(q)
        run("C 注入同码两名 ⇒ 必须报`多个法名`", _multi, "多个法名")

        # D 真缺口
        def _gap(d):
            p = next(x for x in d["provisions"]
                     if x.get("provision_id") and "第" in str(x.get("article") or ""))
            p["provision_id"] = None
        run("D 注入真缺口 ⇒ 必须报`拿不到`", _gap, "拿不到")
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
    print("反向验证 **PASS**：四类注入全部变红、恢复后归零（判据非空转）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
