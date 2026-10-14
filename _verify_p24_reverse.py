# -*- coding: utf-8 -*-
"""P2-4 反向验证：注入已知缺陷 ⇒ 必须变红；恢复后**逐字节一致**。

★ 备份 / 注入 / 恢复**一律走 bytes**；注入锚点**一律单行**。

场景：
  S1 config 里把某模型的 `impl` 改成不存在的模块 ⇒ 闸门报"实现不可溯源"
  S2 engine/tax_deep_models.py 代码里**硬编码税种名** ⇒ 闸门报"硬编码税种名"
  S3 去掉税率表薄转发 `tax_rate_table(` ⇒ 闸门报"未薄转发"
  S4 tax_models_api.py 把参数化段挪到 `coverage` 之前 ⇒ 闸门报"路由顺序"
  S5 main.py 去掉 `app.include_router(tax_models_router)` ⇒ 闸门报"缺接线"
  S6 把"待建"模型**假装已实现**（implemented 强制 True） ⇒ 「不假装」判据变红
  S7 把**覆盖缺口掩盖**（taxes_without_models 置空） ⇒ 覆盖如实判据变红
"""
from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
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
    def __init__(self):
        self._bak: dict = {}

    def patch(self, rel: str, old: str, new: str) -> None:
        p = ROOT / rel
        self._bak.setdefault(rel, p.read_bytes())
        raw = p.read_bytes()
        ob, nb = old.encode("utf-8"), new.encode("utf-8")
        if raw.count(ob) < 1:
            raise AssertionError("锚点未命中 %s: %s" % (rel, old[:70]))
        p.write_bytes(raw.replace(ob, nb))

    def restore_all(self) -> None:
        for rel, data in self._bak.items():
            (ROOT / rel).write_bytes(data)

    def verify_restored(self) -> list:
        return [rel for rel, data in self._bak.items() if (ROOT / rel).read_bytes() != data]


def gate_errors(fn_name: str) -> list:
    return [x for x in getattr(GATE, fn_name)() if x[0] == "ERROR"]


def run_pytest(node: str) -> bool:
    cp = subprocess.run([sys.executable, "-m", "pytest", node, "-q"],
                        cwd=str(ROOT), capture_output=True, text=True, timeout=900)
    return cp.returncode == 0


T = "tests/test_tax_deep_models_p24.py"
inj = Inject()
try:
    # ── S1 实现不可溯源 ──────────────────────────────────────────
    inj.patch("config/tax_deep_models.json",
              '"impl": "vat_reversal", "severity": "medium"',
              '"impl": "no_such_engine_module_xyz", "severity": "medium"')
    errs = gate_errors("check_tax_models_wiring")
    ok("S1 impl 指向不存在的模块 ⇒ 闸门报 ERROR", bool(errs),
       (errs[0][2][:76] if errs else "闸门未报（判据是假的）"))
    inj.restore_all()

    # ── S2 硬编码税种名 ─────────────────────────────────────────
    inj.patch("engine/tax_deep_models.py",
              "def _load() -> Dict[str, Any]:",
              'HARDCODED = "增值税"   # 注入：硬编码税种名\n\n\n'
              "def _load() -> Dict[str, Any]:")
    errs = gate_errors("check_tax_models_wiring")
    ok("S2 硬编码税种名 ⇒ 闸门报 ERROR", bool(errs),
       (errs[0][2][:76] if errs else "闸门未报（判据是假的）"))
    inj.restore_all()

    # ── S3 未薄转发税率表 ────────────────────────────────────────
    inj.patch("engine/tax_deep_models.py", "    rate_tbl = TI.tax_rate_table()",
              "    rate_tbl = {}   # 注入：不再薄转发")
    errs = gate_errors("check_tax_models_wiring")
    ok("S3 去掉税率表薄转发 ⇒ 闸门报 ERROR", bool(errs),
       (errs[0][2][:76] if errs else "闸门未报（判据是假的）"))
    inj.restore_all()

    # ── S4 路由顺序 ─────────────────────────────────────────────
    inj.patch("tax_models_api.py", '@router.get("/tax-models/meta"',
              '@router.get("/tax-models/{tax}")\n'
              'def _moved_placeholder(tax: str):\n'
              '    return {}\n\n\n'
              '@router.get("/tax-models/meta"')
    errs = gate_errors("check_tax_models_wiring")
    ok("S4 路由顺序被破坏 ⇒ 闸门报 ERROR", bool(errs),
       (errs[0][2][:76] if errs else "闸门未报（判据是假的）"))
    inj.restore_all()

    # ── S5 接线缺失 ─────────────────────────────────────────────
    inj.patch("main.py", "app.include_router(tax_models_router)", "pass  # 注入：去掉接线")
    errs = gate_errors("check_tax_models_wiring")
    ok("S5 去掉 include_router ⇒ 闸门报 ERROR", bool(errs),
       (errs[0][2][:76] if errs else "闸门未报（判据是假的）"))
    inj.restore_all()

    # ── S6 假装已实现 ⇒ 「不假装」判据必须变红 ──────────────────────
    inj.patch("engine/tax_deep_models.py",
              '        "implemented": _impl_exists(impl),',
              '        "implemented": True,   # 注入：假装已实现')
    red = not run_pytest(T + "::TaxDeepModelsUnitTests"
                         "::test_implemented_flag_matches_module_existence")
    ok("S6 假装已实现 ⇒ 「不假装」判据变红", red,
       "判据正确地失败了" if red else "判据仍绿（同义反复 ⇒ 假判据）")
    inj.restore_all()

    # ── S7 掩盖覆盖缺口 ⇒ 覆盖如实判据必须变红 ──────────────────────
    inj.patch("engine/tax_deep_models.py",
              '        "taxes_without_models": missing,',
              '        "taxes_without_models": [],   # 注入：掩盖缺口')
    red = not run_pytest(T + "::TaxDeepModelsCaliberTests"
                         "::test_coverage_reports_gaps_honestly")
    ok("S7 掩盖覆盖缺口 ⇒ 覆盖判据变红", red,
       "判据正确地失败了" if red else "判据仍绿（同义反复 ⇒ 假判据）")
    inj.restore_all()

    bad = inj.verify_restored()
    ok("恢复后全部文件逐字节一致", not bad, bad)
finally:
    inj.restore_all()

print("\nP2-4 反向验证：%d 通过 / %d 失败" % (len(_pass), len(_fail)))
if _fail:
    print("失败项：", _fail)
    raise SystemExit(1)
print("ALL PASS")
