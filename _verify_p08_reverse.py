# -*- coding: utf-8 -*-
"""P0-8 判据**反向验证**：注入已知缺陷 ⇒ 对应测试必须变红；随后原样恢复。

判据（与项目既有约定同口径）：
  · 每处替换必须**命中恰好 1 次**（命中数不对 ⇒ 直接判"补丁没打上"，不算通过）；
  · 打完补丁跑**指定测试节点**，必须 **FAILED**；
  · 恢复后必须与原文**逐字节一致**（hash 比对），否则判"恢复失败"。
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
TEST = "tests/test_rbac_api.py"

SCENARIOS = [
    dict(
        name="R1 权限判定放行（rbac_allows 恒真）",
        path="engine/rbac.py",
        old="    return p in session_permission_codes(session)",
        new="    return True  # REVERSE-INJECT",
        node="%s::RbacUnitTests::test_permission_matrix_and_deny_semantics" % TEST,
    ),
    dict(
        name="R2 丢掉租户过滤（用户列表查全量）",
        path="engine/access_service.py",
        old="    rows = _sec.list_users_detailed(tenant_id=tid,",
        new="    rows = _sec.list_users_detailed(tenant_id=None,  # REVERSE-INJECT",
        node="%s::TenantIsolationTests::test_tenant_scope" % TEST,
    ),
    dict(
        name="R3 脱敏空转（_mask 直接返回原对象）",
        path="engine/access_service.py",
        old="    r = _rbac()\n    if not fields:\n        return r.mask_for_session(session, obj, counter)",
        new="    return obj  # REVERSE-INJECT\n    r = _rbac()\n    if not fields:\n        return r.mask_for_session(session, obj, counter)",
        node="%s::RedactionTests::test_masking_by_role" % TEST,
    ),
    dict(
        name="R4 越权不留痕（删掉 auth.denied 登记）",
        path="security_web.py",
        old='            _audit_auth("auth.denied", target=path, detail="CSRF 校验失败",\n'
            '                        user_id=session.user_id, user_name=session.username)\n',
        new="",
        node="%s::AuditCompletenessTests::test_all_actions_recorded" % TEST,
    ),
]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def main() -> int:
    failures = []
    for sc in SCENARIOS:
        p = ROOT / sc["path"]
        original = p.read_text(encoding="utf-8")
        hits = original.count(sc["old"])
        if hits != 1:
            print("SKIP %-46s 命中 %d 次（期望 1）" % (sc["name"], hits))
            failures.append("%s：替换点命中 %d 次" % (sc["name"], hits))
            continue
        p.write_text(original.replace(sc["old"], sc["new"]), encoding="utf-8")
        try:
            r = subprocess.run([PY, "-m", "pytest", sc["node"], "-q", "--no-header"],
                               cwd=ROOT, capture_output=True, text=True, timeout=600)
            red = (r.returncode != 0) and ("failed" in r.stdout.lower())
        finally:
            p.write_text(original, encoding="utf-8")
            restored = p.read_text(encoding="utf-8")
        same = _sha(restored) == _sha(original)
        verdict = "OK  " if (red and same) else "BAD "
        if not (red and same):
            failures.append(sc["name"])
        print("%s%-46s 注入后%s ｜ 恢复%s"
              % (verdict, sc["name"], "变红" if red else "**仍绿**",
                 "一致" if same else "**不一致**"))
    print("\n反向验证：%d/%d 通过" % (len(SCENARIOS) - len(failures), len(SCENARIOS)))
    for f in failures:
        print("  - " + f)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
