# -*- coding: utf-8 -*-
"""P0-8 新增闸门 `check_rbac_single_source` 的**反向验证**（子进程逐轮）。

★ 为什么必须**子进程逐轮**：本闸门会 `import engine.audit_trail` 读动作表。
  同一进程内 `sys.modules` 有缓存 ⇒ 注入缺陷后再跑闸门仍拿到**旧模块** ⇒
  **假绿**（实测：G5 在同进程下报 0 ERROR）。项目既有教训同款
  （`check_clause_compliance` 的反向验证也必须子进程逐轮）。

判据：注入已知缺陷 ⇒ 闸门必须报 ERROR；恢复后必须与原文逐字节一致。
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")

_CHILD = r'''
import sys, pathlib
ROOT = pathlib.Path.cwd()
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
import audit_consistency as AC
errs = [i for i in AC.check_rbac_single_source() if i[0] == "ERROR"]
print("ERRS=%d" % len(errs))
for e in errs[:3]:
    print("MSG=" + e[2][:110])
'''

SCENARIOS = [
    dict(name="G0 基线（无注入 ⇒ 必须 0 ERROR）", path=None, old=None, new=None),
    dict(name="G1 判定多头（第二个 rbac_allows 定义）",
         path="engine/rbac.py",
         old="def redaction_role_of_code(role_code: str) -> str:",
         new="def rbac_allows(session, permission):  # DUP-INJECT\n"
             "    return True\n\n\n"
             "def redaction_role_of_code(role_code: str) -> str:"),
    dict(name="G2 角色-权限写入分叉（别处也 INSERT）",
         path="rbac_api.py",
         old='router = APIRouter(prefix="/api/v1", tags=["权限与审计（P0-8）"])',
         new='router = APIRouter(prefix="/api/v1", tags=["权限与审计（P0-8）"])\n'
             '# DUP-INJECT\n'
             '_FORK = "INSERT INTO role_permissions (role_code, perm_code) VALUES (1, 2)"'),
    dict(name="G3 users.role 两值 CHECK 被改",
         path="security.py",
         old="                role TEXT NOT NULL CHECK(role IN ('admin', 'user')),",
         new="                role TEXT NOT NULL,"),
    dict(name="G4 去掉接线（页面不可达）",
         path="main.py",
         old="app.include_router(rbac_router); app.include_router(rbac_page_router)",
         new="app.include_router(rbac_router)"),
    dict(name="G5 审计动作缺中文名",
         path="engine/audit_trail.py",
         old='    "auth.denied": "越权访问被拒",',
         new='    "auth.denied": "",'),
    dict(name="G6 权限判定放行（rbac_allows 恒真，行为判据）",
         path="engine/rbac.py",
         old="    return p in session_permission_codes(session)",
         new="    return True  # INJECT"),
]


def _sha(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()[:16]


def _run_gate() -> tuple:
    cp = subprocess.run([PY, "-c", _CHILD], cwd=str(ROOT), capture_output=True,
                        text=True, encoding="utf-8", errors="replace", timeout=300)
    out = (cp.stdout or "") + (cp.stderr or "")
    n = 0
    msg = ""
    for line in out.splitlines():
        if line.startswith("ERRS="):
            n = int(line.split("=", 1)[1])
        elif line.startswith("MSG=") and not msg:
            msg = line[4:]
    if cp.returncode != 0 and not n:
        msg = "子进程异常：" + out.strip()[-160:]
    return n, msg


def main() -> int:
    bad = []
    for sc in SCENARIOS:
        if sc["path"] is None:
            n, msg = _run_gate()
            good = (n == 0)
            if not good:
                bad.append(sc["name"])
            print("%s%-42s 基线 ERROR=%d" % ("OK  " if good else "BAD ", sc["name"], n))
            continue
        p = ROOT / sc["path"]
        original = p.read_text(encoding="utf-8")
        hits = original.count(sc["old"])
        if hits != 1:
            print("SKIP %-42s 命中 %d 次（期望 1）" % (sc["name"], hits))
            bad.append(sc["name"])
            continue
        p.write_text(original.replace(sc["old"], sc["new"]), encoding="utf-8")
        try:
            n, msg = _run_gate()
        finally:
            p.write_text(original, encoding="utf-8")
            same = _sha(p.read_text(encoding="utf-8")) == _sha(original)
        ok = (n > 0) and same
        if not ok:
            bad.append(sc["name"])
        print("%s%-42s 注入后 ERROR=%d ｜ 恢复%s ｜ %s"
              % ("OK  " if ok else "BAD ", sc["name"], n,
                 "一致" if same else "**不一致**", msg))
    print("\n闸门反向验证：%d/%d 通过" % (len(SCENARIOS) - len(bad), len(SCENARIOS)))
    for b in bad:
        print("  - " + b)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
