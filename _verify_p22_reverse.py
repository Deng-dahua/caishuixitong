# -*- coding: utf-8 -*-
"""P2-2 反向验证：注入已知缺陷 ⇒ 必须变红；恢复后**逐字节一致**。

★ 备份 / 注入 / 恢复**一律走 bytes**；注入锚点**一律单行**。

场景：
  S1 industry_api.py 把参数化段 `{industry}` 挪到 `generic` **之前** ⇒ 闸门报"路由顺序"
  S2 engine/industry_indicators.py 代码里写死**口径警示语字面量** ⇒ 闸门报"第二份声明"
  S3 engine/industry_indicators.py 代码里**硬编码行业 id** ⇒ 闸门报"硬编码行业 id"
  S4 main.py 去掉 `app.include_router(industry_router)` ⇒ 闸门报"缺接线"
  S5 读层**编造指标**（追加一个不在 indicator_keys 里的键） ⇒ 区间薄转发判据变红
  S6 未登记行业**返回兜底**（不再 404） ⇒ 未登记判据变红
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
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


T = "tests/test_industry_indicators_p22.py"

inj = Inject()
try:
    # ── S1 路由顺序 ──────────────────────────────────────────────
    inj.patch("industry_api.py",
              '@router.get("/industry-indicators/meta"',
              '@router.get("/industry-indicators/{industry}")\n'
              'def _moved_placeholder(industry: str):\n'
              '    return {}\n\n\n'
              '@router.get("/industry-indicators/meta"')
    errs = gate_errors("check_industry_indicators_wiring")
    ok("S1 路由顺序被破坏 ⇒ 闸门报 ERROR", bool(errs),
       (errs[0][2][:76] if errs else "闸门未报（判据是假的）"))
    inj.restore_all()

    # ── S2 口径警示第二份声明 ─────────────────────────────────────
    inj.patch("engine/industry_indicators.py",
              "def metadata() -> Dict[str, Any]:",
              'CAUTION = "系统内置行业统计通用参考值，非税务机关官方口径"   # 注入：第二份声明\n\n\n'
              "def metadata() -> Dict[str, Any]:")
    errs = gate_errors("check_industry_indicators_wiring")
    ok("S2 口径警示字面量 ⇒ 闸门报 ERROR", bool(errs),
       (errs[0][2][:76] if errs else "闸门未报（判据是假的）"))
    inj.restore_all()

    # ── S3 硬编码行业 id ────────────────────────────────────────
    inj.patch("engine/industry_indicators.py",
              "def _indicators_of(",
              'HARDCODED_IND = "manufacturing"   # 注入：硬编码行业 id\n\n\n'
              "def _indicators_of(")
    errs = gate_errors("check_industry_indicators_wiring")
    ok("S3 硬编码行业 id ⇒ 闸门报 ERROR", bool(errs),
       (errs[0][2][:76] if errs else "闸门未报（判据是假的）"))
    inj.restore_all()

    # ── S4 接线缺失 ─────────────────────────────────────────────
    inj.patch("main.py", "app.include_router(industry_router)", "pass  # 注入：去掉接线")
    errs = gate_errors("check_industry_indicators_wiring")
    ok("S4 去掉 include_router ⇒ 闸门报 ERROR", bool(errs),
       (errs[0][2][:76] if errs else "闸门未报（判据是假的）"))
    inj.restore_all()

    # ── S5 读层编造指标 ⇒ 区间薄转发判据必须变红 ────────────────────
    inj.patch("engine/industry_indicators.py",
              '    return {"matched": matched, "source": source, "indicators": rows}',
              '    rows.append({"key": "fabricated_metric", "label": "编造指标",\n'
              '                 "unit": "", "low": 0.0, "high": 1.0})   # 注入：编造指标\n'
              '    return {"matched": matched, "source": source, "indicators": rows}')
    red = not run_pytest(T + "::IndustryIndicatorsUnitTests"
                         "::test_ranges_are_thin_forward_of_authority")
    ok("S5 读层编造指标 ⇒ 薄转发判据变红", red,
       "判据正确地失败了" if red else "判据仍绿（同义反复 ⇒ 假判据）")
    inj.restore_all()

    # ── S6 未登记行业返回兜底 ⇒ 未登记判据必须变红 ──────────────────
    #   ★ 必须**同时**去掉 `return None`：只加 `raw = {}` 而保留 return 则行为不变
    #     ⇒ 判据仍绿，被误读成"假判据"（实测踩过）。
    inj.patch("engine/industry_indicators.py",
              "        return None",
              "        raw = {}   # 注入：不再 404，改用兜底包装")
    red = not run_pytest(T + "::IndustryIndicatorsCaliberTests"
                         "::test_unregistered_industry_is_404_not_generic")
    ok("S6 未登记行业返回兜底 ⇒ 未登记判据变红", red,
       "判据正确地失败了" if red else "判据仍绿（同义反复 ⇒ 假判据）")
    inj.restore_all()

    bad = inj.verify_restored()
    ok("恢复后全部文件逐字节一致", not bad, bad)
finally:
    inj.restore_all()

print("\nP2-2 反向验证：%d 通过 / %d 失败" % (len(_pass), len(_fail)))
if _fail:
    print("失败项：", _fail)
    raise SystemExit(1)
print("ALL PASS")
