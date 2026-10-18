# -*- coding: utf-8 -*-
"""GAP-13 反向验证：故意把域隔离改坏，`tests/test_field_domain_isolation.py` 必须变红。

五个注入点：
  ① `counterparty.aliases_from` 回退成 `BANK_TX_TEXT_KEYS`（品名/摘要重新进来）
  ② 已知域白名单放开（invoice 允许跨域）⇒ 流水金额又能记成发票不含税金额
  ③ `cross_domain_hits` 忽略"独有别名"约束（共用别名也可命中）
  ④ `_registered_names` 的必填只按本域 → 回退成"全部必填"
  ⑤ 重新引入无上界跨域实现 `_other_domain_hits`

每个注入点**独立子进程**跑（避免 `sys.modules` 缓存造成假绿），跑完必定还原。
用法：python scripts/_reverse_verify_field_isolation.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
CONFIG = os.path.join(ROOT, "config", "standard_fields.json")
SF = os.path.join(ROOT, "engine", "standard_fields.py")
ES = os.path.join(ROOT, "engine", "extract_service.py")
TEST = "tests/test_field_domain_isolation.py"


def _run_test() -> tuple:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    p = subprocess.run([PY, "-m", "pytest", TEST, "-q", "--no-header", "-p", "no:cacheprovider"],
                       cwd=ROOT, capture_output=True, text=True, env=env, timeout=600)
    tail = (p.stdout or "") + (p.stderr or "")
    return p.returncode, tail


def _bump(path: str) -> None:
    """把 mtime 推到未来，防 `.pyc` 假绿。"""
    st = os.stat(path)
    os.utime(path, (st.st_atime + 120, st.st_mtime + 120))


def inject_alias_source() -> None:
    shutil.copy2(CONFIG, CONFIG + ".bak")
    txt = open(CONFIG, encoding="utf-8").read()
    txt = txt.replace('"aliases_from": "COUNTERPARTY_KEYS"',
                      '"aliases_from": "BANK_TX_TEXT_KEYS"')
    open(CONFIG, "w", encoding="utf-8", newline="").write(txt)


def inject_allowlist() -> None:
    shutil.copy2(CONFIG, CONFIG + ".bak")
    txt = open(CONFIG, encoding="utf-8").read()
    txt = txt.replace('"cross_domain_allow": {\n      "_desc"',
                      '"cross_domain_allow": {\n      "invoice": ["invoice_amount", "counterparty"],\n'
                      '      "bank": ["invoice_amount"],\n      "_desc"', 1)
    open(CONFIG, "w", encoding="utf-8", newline="").write(txt)


def inject_shared_alias() -> None:
    shutil.copy2(SF, SF + ".bak")
    txt = open(SF, encoding="utf-8").read()
    txt = txt.replace("        for a in exclusive_aliases(n):",
                      "        for a in aliases_of(n):", 1)
    open(SF, "w", encoding="utf-8", newline="").write(txt)
    _bump(SF)


def inject_required_all() -> None:
    shutil.copy2(ES, ES + ".bak")
    txt = open(ES, encoding="utf-8").read()
    txt = txt.replace("    req = set(_req(dom) if dom else _req())",
                      "    req = set(_req())", 1)
    txt = txt.replace("    req_local = [n for n in _req(dom) if n] if dom else "
                      "[str(x.get(\"name\")) for x in _required_all()]",
                      "    req_local = [str(x.get(\"name\")) for x in _required_all()]", 1)
    open(ES, "w", encoding="utf-8", newline="").write(txt)
    _bump(ES)


def inject_second_impl() -> None:
    shutil.copy2(ES, ES + ".bak")
    txt = open(ES, encoding="utf-8").read()
    txt += ("\n\ndef _other_domain_hits(rows, exclude):\n"
            "    return []\n")
    open(ES, "w", encoding="utf-8", newline="").write(txt)
    _bump(ES)


CASES = [
    ("① 回退 counterparty 别名源", inject_alias_source, CONFIG),
    ("② 放开已知域白名单", inject_allowlist, CONFIG),
    ("③ 忽略「独有别名」约束", inject_shared_alias, SF),
    ("④ 必填改回「全部域」", inject_required_all, ES),
    ("⑤ 重引无上界跨域实现", inject_second_impl, ES),
]


def main() -> int:
    base_rc, base_out = _run_test()
    print("基线：rc=%d %s" % (base_rc, base_out.strip().splitlines()[-1] if base_out.strip() else ""))
    if base_rc != 0:
        print("✗ 基线未绿，反向验证无意义：")
        print(base_out)
        return 2
    results = []
    for name, fn, target in CASES:
        bak = target + ".bak"
        try:
            fn()
            rc, out = _run_test()
            red = rc != 0
            detail = ""
            for line in reversed(out.strip().splitlines()):
                if "failed" in line or "passed" in line:
                    detail = line.strip()
                    break
            results.append({"case": name, "turned_red": red, "detail": detail})
            print("%s %s → %s" % ("✓" if red else "✗", name, detail or out.strip()[-120:]))
        finally:
            if os.path.exists(bak):
                shutil.move(bak, target)
                if target.endswith(".py"):
                    _bump(target)
    after_rc, after_out = _run_test()
    print("还原后：rc=%d %s" % (after_rc, after_out.strip().splitlines()[-1] if after_out.strip() else ""))
    ok = all(r["turned_red"] for r in results) and after_rc == 0
    print("\n===== 结论 =====")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print("反向验证 %d/%d 触发红灯；还原后 %s"
          % (sum(1 for r in results if r["turned_red"]), len(results),
             "绿" if after_rc == 0 else "仍红（异常）"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
