# -*- coding: utf-8 -*-
"""备份与恢复（S-10 / D-02）守护测试。

覆盖四类判据：
  ① **备份真能还原**：改坏数据 → 恢复 → 行数与内容回到备份时点（不是"看起来成功"）；
  ② **坏备份不许覆盖生产库**：篡改备份文件 ⇒ 校验必然失败 ⇒ 恢复被拒绝；
  ③ **在线一致快照**：WAL 里未 checkpoint 的数据也必须进备份（用 VACUUM INTO，
     文件级 copy 会漏）；
  ④ **轮转走回收站**：过期备份进 trash（可恢复），不得物理删除。

★ 全部用临时目录 + monkeypatch，**不碰真实 data/**。
"""
from __future__ import annotations

import json
import pathlib
import sqlite3
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import backup as B   # noqa: E402


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """隔离环境：临时 data 目录 + 两个小库 + 一个状态文件。"""
    data = tmp_path / "data"
    data.mkdir()
    acc = data / "accounting.db"
    sec = data / "security.db"
    for p in (acc, sec):
        con = sqlite3.connect(str(p))
        con.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        con.executemany("INSERT INTO t (v) VALUES (?)", [("a",), ("b",), ("c",)])
        con.commit()
        con.close()
    (data / "user_corrections.json").write_text('{"k": 1}', encoding="utf-8")

    monkeypatch.setattr(B, "DATA_DIR", data)
    monkeypatch.setattr(B, "BACKUP_DIR", data / "backups")
    monkeypatch.setattr(B, "DATABASES", (acc, sec))
    monkeypatch.setattr(B, "STATE_FILES", ("user_corrections.json",))
    return {"data": data, "acc": acc, "sec": sec}


def _rows(db: pathlib.Path) -> int:
    con = sqlite3.connect(str(db))
    try:
        return int(con.execute("SELECT COUNT(*) FROM t").fetchone()[0])
    finally:
        con.close()


def test_backup_creates_manifest_with_sha256(env) -> None:
    m = B.create_backup("manual", note="t")
    folder = B.BACKUP_DIR / m["folder"]
    assert (folder / "manifest.json").is_file()
    names = {f["name"] for f in m["files"]}
    assert {"accounting.db", "security.db", "user_corrections.json"} <= names
    for f in m["files"]:
        assert len(f["sha256"]) == 64, "缺 sha256"
        assert (folder / f["name"]).stat().st_size == f["bytes"]
    assert m["integrity"]["accounting.db"] == "ok"
    assert m["uploads"]["count"] is None or isinstance(m["uploads"]["count"], int)
    # 版本如实（无 VERSION 文件时是 unknown，不许编造）
    assert m["app_version"], "版本字段为空"


def test_verify_passes_on_intact_backup(env) -> None:
    m = B.create_backup("manual")
    v = B.verify_backup(m["folder"])
    assert v["ok"] is True, v["problems"]


def test_verify_detects_tampering(env) -> None:
    """反向验证：篡改备份文件 ⇒ 校验必须失败（否则「校验通过」是假的）。"""
    m = B.create_backup("manual")
    target = B.BACKUP_DIR / m["folder"] / "accounting.db"
    raw = bytearray(target.read_bytes())
    raw[-40:] = b"\x00" * 40                       # 破坏尾部页面
    target.write_bytes(bytes(raw))
    v = B.verify_backup(m["folder"])
    assert v["ok"] is False, "篡改后仍判为通过 ⇒ 校验形同虚设"
    assert any("sha256" in p or "完整性" in p for p in v["problems"])


def test_restore_refuses_damaged_backup(env) -> None:
    """坏备份**绝不能**覆盖生产库 —— 这是恢复路径上最危险的一步。"""
    m = B.create_backup("manual")
    (B.BACKUP_DIR / m["folder"] / "accounting.db").write_bytes(b"not a database")
    # 破坏生产库内容，确认它没被坏备份盖掉
    con = sqlite3.connect(str(env["acc"]))
    con.execute("INSERT INTO t (v) VALUES ('keep-me')")
    con.commit()
    con.close()
    before = _rows(env["acc"])
    res = B.restore_backup(m["folder"], force=True)
    assert res["ok"] is False and res["stage"] == "verify"
    assert _rows(env["acc"]) == before, "★ 恢复被拒绝却仍改动了生产库"


def test_restore_actually_restores_data(env) -> None:
    """★ 核心判据：删掉数据 → 恢复 → 数据回来（结果级验收）。"""
    m = B.create_backup("manual")
    assert _rows(env["acc"]) == 3
    con = sqlite3.connect(str(env["acc"]))
    con.execute("DELETE FROM t")
    con.commit()
    con.close()
    assert _rows(env["acc"]) == 0, "前置失效：没删掉"

    res = B.restore_backup(m["folder"], force=True)
    assert res["ok"] is True, res
    assert _rows(env["acc"]) == 3, "恢复后行数没回来"
    assert res["safety_backup"], "恢复前未生成 pre-restore 后悔药"


def test_restore_snapshot_captures_wal_data(env) -> None:
    """在线一致快照：**WAL 中未 checkpoint 的数据**也要进备份。

    这是"为什么必须 VACUUM INTO 而不是文件 copy"的直接证明：
    写一行但不 checkpoint、且不让 SQLite 自动 checkpoint，
    文件级 copy 会漏掉这一行，VACUUM INTO 不会。
    """
    con = sqlite3.connect(str(env["acc"]))
    con.execute("PRAGMA wal_autocheckpoint=0")
    con.execute("INSERT INTO t (v) VALUES ('wal-only')")
    con.commit()
    assert _rows(env["acc"]) == 4
    try:
        m = B.create_backup("manual")
        snap = B.BACKUP_DIR / m["folder"] / "accounting.db"
        assert _rows(snap) == 4, "备份漏掉了 WAL 中的未落盘数据（应改用 VACUUM INTO）"
    finally:
        con.close()


def test_rotation_moves_old_backups_to_trash(env, monkeypatch) -> None:
    """轮转：只保留最近 N 份，旧的**移入回收站**而不是物理删除。"""
    made = []
    for i in range(4):
        m = B.create_backup("manual", note="r%d" % i)
        made.append(m["folder"])
    trashed = []
    real_purge = B.purge_file

    def spy(p):
        trashed.append(str(p))
        return real_purge(p)

    monkeypatch.setattr(B, "purge_file", spy)
    B._rotate(keep=2)
    left = [m["folder"] for m in B.list_backups()]
    assert len(left) == 2, "保留份数不是 2：%s" % left
    assert trashed, "过期备份未走回收站出口（可能用了 os.remove）"
    assert set(made[:2]).issubset(set(made) - set(left)), "删错了份数"


def test_rotation_never_deletes_pre_restore(env) -> None:
    """`pre-restore` 快照永不轮转（恢复失败的后悔药）。"""
    pre = B.create_backup("pre-restore")
    for i in range(3):
        B.create_backup("manual")
    B._rotate(keep=1)
    names = {m["folder"] for m in B.list_backups()}
    assert pre["folder"] in names, "pre-restore 被轮转删掉了"


def test_due_logic(env) -> None:
    assert B.is_due() is True, "无备份时应当判定为需要备份"
    B.create_backup("daily")
    assert B.backup_age_hours() is not None
    assert B.is_due() is False, "刚备份完仍判为需要备份 ⇒ 会重复备份"


def test_ensure_daily_backup_runs_once(env) -> None:
    first = B.ensure_daily_backup()
    assert first["ran"] is True and first["folder"]
    second = B.ensure_daily_backup()
    assert second["ran"] is False, "间隔内重复备份"


def test_summary_reports_dir_follows_data_dir(env) -> None:
    B.create_backup("manual")
    s = B.summary()
    assert str(B.DATA_DIR) in s["dir"], "备份目录未跟随 APP_DATA_DIR"
    assert s["count"] == 1 and s["total_bytes"] > 0
    assert isinstance(s["note"], str) and s["note"]


# ── 事故回归（2026-10-17）────────────────────────────────────────────────────
# ★ 背景：`restore_backup` 首版用模块级常量 `SECURITY_DB.parent` 拼恢复目标，
#   该常量在 import 时已固化为**真实 data/**，于是 monkeypatch `DATA_DIR` 不生效
#   ⇒ 跑一次测试就把生产 accounting.db（6.3 MB）覆盖成 12 KB 测试库。
#   下面两条判据专门锁死这个路径：**恢复只能写进 DATA_DIR**。


def test_assert_inside_rejects_paths_outside_data_dir(env) -> None:
    """硬护栏：DATA_DIR 之外的写入目标必须**在写之前**抛错。"""
    ok = B._assert_inside(env["data"] / "sub" / "x.db")
    assert ok == (env["data"] / "sub" / "x.db").resolve()
    with pytest.raises(RuntimeError):
        B._assert_inside(ROOT / "data" / "accounting.db")
    with pytest.raises(RuntimeError):
        B._assert_inside(env["data"].parent / "elsewhere.db")


def test_restore_never_touches_files_outside_data_dir(env) -> None:
    """★ 事故判据：跑完恢复，**仓库真实 data/ 下的库文件必须字节与 mtime 不变**。

    这条如果当时存在，就不会发生「测试把生产库覆盖」的事故。
    """
    repo_data = ROOT / "data"

    def snap() -> dict:
        out = {}
        if repo_data.is_dir():
            for p in repo_data.glob("*.db*"):
                try:
                    st = p.stat()
                    out[p.name] = (st.st_size, st.st_mtime_ns)
                except OSError:
                    continue
        return out

    before = snap()
    m = B.create_backup("manual")
    # 破坏隔离库，确保恢复动作真的执行到"写文件"这一步
    con = sqlite3.connect(str(env["acc"]))
    con.execute("DELETE FROM t")
    con.commit()
    con.close()
    res = B.restore_backup(m["folder"], force=True)
    assert res["stage"] == "restored", res
    after = snap()
    assert before == after, (
        "★ 恢复动作改动了 DATA_DIR 之外的真实库文件：\n before=%s\n after=%s\n"
        "（2026-10-17 事故：恢复目标必须由 DATA_DIR 派生）" % (before, after))
