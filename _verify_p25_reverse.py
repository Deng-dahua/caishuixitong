# -*- coding: utf-8 -*-
"""P2-5 反向验证：注入已知缺陷 ⇒ 必须变红；恢复后**逐字节一致**。

★ 备份 / 注入 / 恢复**一律走 bytes**；注入锚点**一律单行**。

场景：
  S1 engine/dashboard.py 不再薄转发某 Service ⇒ 闸门报"自建取数"
  S2 engine/dashboard.py 出现 SQL 关键字（SELECT） ⇒ 闸门报"零 SQL 被破坏"
  S3 dashboard_api.py 路径加参数段 `{...}` ⇒ 闸门报"路径含参数段"
  S4 main.py 去掉 `app.include_router(dashboard_router)` ⇒ 闸门报"缺接线"
  S5 把 `payload_unavailable` 与 0 风险混同（改 note / 强制置 0） ⇒ 口径判据变红
  S6 大屏**无视可见范围**（overview 改用无权限过滤的项目列表） ⇒ 范围判据变红
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


T = "tests/test_dashboard_p25.py"
inj = Inject()
try:
    # ── S1 不再薄转发 Service ────────────────────────────────────
    inj.patch("engine/dashboard.py", "    from engine import risk_service as RISK                        # noqa: PLC0415",
              "    pass  # 注入：不再薄转发风险 Service")
    errs = gate_errors("check_dashboard_wiring")
    ok("S1 去掉 Service 薄转发 ⇒ 闸门报 ERROR", bool(errs),
       (errs[0][2][:74] if errs else "闸门未报（判据是假的）"))
    inj.restore_all()

    # ── S2 出现 SQL ────────────────────────────────────────────
    inj.patch("engine/dashboard.py", "def overview(session: Any) -> Dict[str, Any]:",
              'SQL_STUB = "SELECT * FROM projects"   # 注入：出现 SQL\n\n\n'
              "def overview(session: Any) -> Dict[str, Any]:")
    errs = gate_errors("check_dashboard_wiring")
    ok("S2 出现 SQL 关键字 ⇒ 闸门报 ERROR", bool(errs),
       (errs[0][2][:74] if errs else "闸门未报（判据是假的）"))
    inj.restore_all()

    # ── S3 路径含参数段 ─────────────────────────────────────────
    inj.patch("dashboard_api.py", '@router.get("/dashboard/meta"',
              '@router.get("/dashboard/{scope}")\n'
              'def _moved_placeholder(scope: str):\n'
              '    return {}\n\n\n'
              '@router.get("/dashboard/meta"')
    errs = gate_errors("check_dashboard_wiring")
    ok("S3 路径含参数段 ⇒ 闸门报 ERROR", bool(errs),
       (errs[0][2][:74] if errs else "闸门未报（判据是假的）"))
    inj.restore_all()

    # ── S4 接线缺失 ─────────────────────────────────────────────
    inj.patch("main.py", "app.include_router(dashboard_router)", "pass  # 注入：去掉接线")
    errs = gate_errors("check_dashboard_wiring")
    ok("S4 去掉 include_router ⇒ 闸门报 ERROR", bool(errs),
       (errs[0][2][:74] if errs else "闸门未报（判据是假的）"))
    inj.restore_all()

    # ── S5 口径混同：把"载荷不可得"说成 0 条风险 ⇒ 判据必须变红 ────────
    #   锚点 = note 里那句"不是 0 条风险"的说明
    inj.patch("engine/dashboard.py",
              '                 "尚未产出风险载荷（一键分析未跑或产物缺失）——**这不是 0 条风险**，两者不可混。"',
              '                 "尚未产出风险载荷（一键分析未跑或产物缺失）。"')
    red = not run_pytest(T + "::DashboardCaliberTests"
                         "::test_payload_unavailable_not_confused_with_zero")
    ok("S5 口径混同 ⇒ 「不混口径」判据变红", red,
       "判据正确地失败了" if red else "判据仍绿（同义反复 ⇒ 假判据）")
    inj.restore_all()

    # ── S6 无视可见范围 ⇒ 范围判据必须变红 ──────────────────────────
    #   注入：让项目扫描"不漏掉任何项目"（模拟绕过 Service 的可见性过滤）
    inj.patch("engine/dashboard.py",
              "    got = PROJ.list_projects(session, page=1, page_size=min(PROJECT_CAP, 200))",
              "    _adm = session\n"
              "    try:\n"
              "        from security import SessionContext as _SC\n"
              "        _adm = _SC(user_id=session.user_id, username=session.username,\n"
              "                   role='admin', allowed_company_ids=frozenset(),\n"
              "                   selected_company_id=None, csrf_hash='', expires_at=0)\n"
              "    except Exception:\n"
              "        pass\n"
              "    got = PROJ.list_projects(_adm, page=1, page_size=min(PROJECT_CAP, 200))")
    red = not run_pytest(T + "::DashboardScopeTests::test_visible_scope_same_as_service")
    ok("S6 无视可见范围 ⇒ 范围判据变红", red,
       "判据正确地失败了" if red else "判据仍绿（同义反复 ⇒ 假判据）")
    inj.restore_all()

    bad = inj.verify_restored()
    ok("恢复后全部文件逐字节一致", not bad, bad)
finally:
    inj.restore_all()

print("\nP2-5 反向验证：%d 通过 / %d 失败" % (len(_pass), len(_fail)))
if _fail:
    print("失败项：", _fail)
    raise SystemExit(1)
print("ALL PASS")
