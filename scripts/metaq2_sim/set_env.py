# -*- coding: utf-8 -*-
"""META-QUALITY 阶段2：搭建**隔离**场景模拟环境（不触碰生产 data/）。

产出：
  `_scenario_sim/data`（独立 APP_DATA_DIR）—— 复制 security.db / accounting.db / uploads，
  播种 5 个角色账号 + 1 个合成测试企业（测试数据，不用真实纳税人数据）。

用法：`python scripts/_set_metaq2_env.py`
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIM = Path(r"C:\Users\Administrator\WorkBuddy\2026-08-04-21-37-33\_scenario_sim")
DATA = SIM / "data"

PW = "MetaQ2-Sim-2026!"
USERS = [
    # (用户名, 角色码, users.role, 中文名)
    ("sim_finance", "enterprise_finance", "user", "模拟·企业财务"),
    ("sim_advisor", "tax_advisor", "user", "模拟·税务师"),
    ("sim_expert", "review_expert", "user", "模拟·复核专家"),
    ("sim_admin", "system_admin", "admin", "模拟·系统管理员"),
    ("sim_auditor", "auditor", "user", "模拟·审计员"),
]
TEST_COMPANY = {
    "name": "元质量模拟测试有限公司",
    "uscc": "91440300MA5SIMQ2X1",   # 合成，非真实主体
}


def _copy_db(src: Path, dst: Path) -> None:
    """用 sqlite backup API 复制（含 WAL 已提交内容，避免半写快照）。"""
    if dst.exists():
        dst.unlink()
    src_c = sqlite3.connect(str(src))
    dst_c = sqlite3.connect(str(dst))
    with dst_c:
        src_c.backup(dst_c)
    dst_c.close()
    src_c.close()


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    for name in ("security.db", "accounting.db"):
        _copy_db(ROOT / "data" / name, DATA / name)
        print(f"[copy] {name} -> {DATA}")
    up_src, up_dst = ROOT / "data" / "uploads", DATA / "uploads"
    if up_src.exists():
        if up_dst.exists():
            shutil.rmtree(up_dst)
        shutil.copytree(up_src, up_dst)
        print(f"[copy] uploads/ -> {up_dst}")

    os.environ["APP_DATA_DIR"] = str(DATA)
    sys.path.insert(0, str(ROOT))
    from security import create_user, init_security_db, set_user_companies   # noqa: E402
    from engine import rbac as _rbac                                        # noqa: E402

    init_security_db()
    _rbac.ensure_rbac_schema()

    # ── 合成测试企业（直接落库：setup 阶段，随后由 API 场景再验证真实新建路径）──
    acc = sqlite3.connect(str(DATA / "accounting.db"))
    _COLS = ("name", "uscc", "registered_capital", "established_date", "legal_representative",
             "address", "business_scope", "created_at")
    row = acc.execute("select id from companies where uscc=?", (TEST_COMPANY["uscc"],)).fetchone()
    if row:
        company_id = int(row[0])
        print(f"[reuse] 测试企业 id={company_id}")
    else:
        acc.execute(
            f"insert into companies ({','.join(_COLS)}) values ({','.join('?' * len(_COLS))})",
            [TEST_COMPANY["name"], TEST_COMPANY["uscc"], 100, "2024-01-10", "测试法人",
             "广东省深圳市南山区科技园测试路 1 号", "技术服务;软件开发;信息咨询",
             "2026-10-16 08:40:00.000000"],
        )
        acc.commit()
        company_id = int(acc.execute("select last_insert_rowid()").fetchone()[0])
        print(f"[new] 测试企业 id={company_id} {TEST_COMPANY['name']}")
    acc.close()

    # ── 5 个角色账号 ──
    ids = {}
    for username, role_code, urole, cname in USERS:
        try:
            uid = create_user(username, PW, role=urole, company_ids=[company_id],
                              display_name=cname, phone="13900000099")
            print(f"[user+] {username} id={uid} role={role_code}")
        except Exception as exc:                                        # noqa: BLE001
            uid = int(sqlite3.connect(str(DATA / "security.db")).execute(
                "select id from users where username=?", (username,)).fetchone()[0])
            print(f"[user=] {username} 已存在 id={uid}（{exc}）")
        ids[username] = uid
        _rbac.assign_user_roles(uid, [role_code])
        if role_code != "system_admin":
            set_user_companies(uid, [company_id])

    # 审计用：给 admin 也绑定测试企业，便于核对
    meta = {"company_id": company_id, "company": TEST_COMPANY, "password": PW, "users": ids}
    (SIM / "env.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n[环境] ", SIM / "env.json")
    print(json.dumps(meta, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
