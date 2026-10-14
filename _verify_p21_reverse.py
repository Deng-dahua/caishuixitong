# -*- coding: utf-8 -*-
"""P2-1 反向验证：注入已知缺陷 ⇒ 必须变红；恢复后**逐字节一致**。

为什么必须做：判据本身可能是"同义反复"（问了必然为真）或判据挂错对象 ⇒ 给出假绿。
本脚本对每个判据都注入一个**已知会让它出错**的缺陷，若判据没红 ⇒ 判据是假的。

★ 备份 / 注入 / 恢复**一律走 bytes**（`Path.write_text` 在 Windows 会把 LF 变 CRLF，
  恢复后 md5 不一致 ⇒ 假红）。注入锚点**一律单行**（跨行锚点在 CRLF 下不命中）。

场景：
  S1 legal_api.py 把参数化段 `{law}` 挪到字面量段**之前** ⇒ 闸门报"路由顺序"
  S2 engine/legal_library.py 代码里出现数据文件字面量 ⇒ 闸门报"读盘第二处"
  S3 main.py 去掉 `app.include_router(legal_router)` ⇒ 闸门报"缺接线"
  S4 config/rbac.json 去掉权限点 `legal.view` ⇒ 闸门报"缺权限点"
  S5 读层**编造条文**（给 content 追加标记） ⇒ 「不硬编码条文」判据必须变红
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def _load_gate():
    spec = importlib.util.spec_from_file_location("ac", str(ROOT / "tools" / "audit_consistency.py"))
    m = importlib.util.module_from_spec(spec)
    sys.modules["ac"] = m
    spec.loader.exec_module(m)
    return m


GATE = _load_gate()
_pass, _fail = [], []


def ok(name: str, cond: bool, detail: str = "") -> None:
    (_pass if cond else _fail).append(name)
    print("%s %s%s" % ("PASS" if cond else "FAIL", name, ("  | " + str(detail)) if detail else ""))


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


class Inject:
    """按 bytes 注入 / 恢复（恢复后断言字节一致）。"""

    def __init__(self):
        self._bak: dict = {}

    def patch(self, rel: str, old: str, new: str, *, regex: bool = False) -> str:
        p = ROOT / rel
        before = _md5(p)
        self._bak.setdefault(rel, p.read_bytes())
        raw = p.read_bytes()
        if regex:
            text = raw.decode("utf-8")
            if not re.search(old, text):
                raise AssertionError("正则未命中 %s: %s" % (rel, old[:60]))
            text = re.sub(old, new, text)
            p.write_bytes(text.encode("utf-8"))
        else:
            ob, nb = old.encode("utf-8"), new.encode("utf-8")
            if raw.count(ob) < 1:
                raise AssertionError("锚点未命中 %s: %s" % (rel, old[:60]))
            p.write_bytes(raw.replace(ob, nb))
        return before

    def restore_all(self) -> None:
        for rel, data in self._bak.items():
            (ROOT / rel).write_bytes(data)
        for rel in self._bak:
            assert _md5(ROOT / rel) is not None
        return

    def verify_restored(self) -> list:
        bad = []
        for rel, data in self._bak.items():
            if (ROOT / rel).read_bytes() != data:
                bad.append(rel)
        return bad


def gate_errors(fn_name: str) -> list:
    iss = getattr(GATE, fn_name)()
    return [x for x in iss if x[0] == "ERROR"]


def run_pytest(node: str) -> bool:
    """跑单个测试节点，返回是否通过。"""
    cp = subprocess.run([sys.executable, "-m", "pytest", node, "-q"],
                        cwd=str(ROOT), capture_output=True, text=True, timeout=900)
    return cp.returncode == 0


inj = Inject()
try:
    # ── S1 路由顺序（把参数化段插到**字面量段之前**）────────────────
    inj.patch("legal_api.py",
              '@router.get("/legal-library/meta"',
              '@router.get("/legal-library/{law}")\n'
              'def _moved_placeholder(law: str):\n'
              '    return {}\n\n\n'
              '@router.get("/legal-library/meta"',
              )
    errs = gate_errors("check_legal_library_wiring")
    ok("S1 路由顺序被破坏 ⇒ 闸门报 ERROR", bool(errs),
       (errs[0][2][:70] if errs else "闸门未报（判据是假的）"))
    inj.restore_all()

    # ── S2 读盘第二处（**代码**里出现数据文件字面量）──────────────
    inj.patch("engine/legal_library.py",
              "def _norm(s: Any) -> str:",
              'LIB_FILE = "legal_library.json"   # 注入：代码里出现数据文件字面量\n\n\ndef _norm(s: Any) -> str:')
    errs = gate_errors("check_legal_library_wiring")
    ok("S2 读盘第二处 ⇒ 闸门报 ERROR", bool(errs),
       (errs[0][2][:70] if errs else "闸门未报（判据是假的）"))
    inj.restore_all()

    # ── S3 接线缺失 ─────────────────────────────────────────────
    inj.patch("main.py", "app.include_router(legal_router)", "pass  # 注入：去掉接线")
    errs = gate_errors("check_legal_library_wiring")
    ok("S3 去掉 include_router ⇒ 闸门报 ERROR", bool(errs),
       (errs[0][2][:70] if errs else "闸门未报（判据是假的）"))
    inj.restore_all()

    # ── S4 权限点缺失 ───────────────────────────────────────────
    rb = json.loads((ROOT / "config/rbac.json").read_text(encoding="utf-8"))
    before_app = rb["role_permissions"].get("auditor", [])[:]
    inj.patch("config/rbac.json", '"code": "legal.view"', '"code": "legal.view__injected"')
    errs = gate_errors("check_legal_library_wiring")
    ok("S4 缺权限点 legal.view ⇒ 闸门报 ERROR", bool(errs),
       (errs[0][2][:70] if errs else "闸门未报（判据是假的）"))
    inj.restore_all()

    # ── S5 读层编造条文 ⇒ 「不硬编码条文」判据必须变红 ──────────────
    inj.patch("engine/legal_library.py",
              '        "content": row.get("content") or "",',
              '        "content": (row.get("content") or "") + "【编造】",')
    red = not run_pytest("tests/test_legal_library_p21.py::LegalLibraryNoHardcodeTests"
                         "::test_every_returned_article_exists_in_data_file")
    ok("S5 读层编造条文 ⇒ 「不硬编码」判据变红", red,
       "判据正确地失败了" if red else "判据仍绿（同义反复 ⇒ 假判据）")
    inj.restore_all()

    # ── 恢复一致性 ─────────────────────────────────────────────
    bad = inj.verify_restored()
    ok("恢复后全部文件逐字节一致", not bad, bad)
finally:
    inj.restore_all()

print("\nP2-1 反向验证：%d 通过 / %d 失败" % (len(_pass), len(_fail)))
if _fail:
    print("失败项：", _fail)
    raise SystemExit(1)
print("ALL PASS")
