# -*- coding: utf-8 -*-
"""反向验证：破坏「删账套 ⇒ 派生物一起清」的各个关键点，确认闸门**真的会变红**。

规约：一次报 0 的闸门，先怀疑**变异无效**（打偏 / 没造出缺陷），而不是"闸门覆盖到了"。
两个必须绕开的坑（详见 skill G6 第 4/5 条）：
  ① 变异脚本必须清 `sys.modules` 里的 `main`/`engine`/`tools` 模块缓存；
  ② 变异要**真的造出缺陷**（先在 REPL 里看到缺陷出现，再跑闸门）。

用法：./.venv/Scripts/python.exe scripts/_verify_company_purge_gate_reverse.py
"""
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.stdout.reconfigure(encoding="utf-8")

MAIN = os.path.join(ROOT, "main.py")
ORPHAN = os.path.join(ROOT, "scripts", "four_reports", "company_2_full.json")


def _read(p):
    with io.open(p, encoding="utf-8", newline="") as f:
        return f.read()


def _write(p, t):
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        f.write(t)


def gate_count():
    """清模块缓存后跑本组闸门，返回 (ERROR 条数, 消息)。"""
    for m in [k for k in list(sys.modules)
              if k in ("audit_consistency", "main") or k.startswith("engine")
              or k.startswith("runtime_storage")]:
        sys.modules.pop(m, None)
    import audit_consistency as A                       # noqa: PLC0415
    iss = (A.check_company_artifact_consistency()
           + A.check_delete_exits())                    # 删除出口唯一
    errs = [i for i in iss if i[0] == "ERROR"]
    return len(errs), [i[2] for i in errs]


def mut_m1_delete_company_skips_purge():
    """M1：删账套不再调清理权威（回到旧病根）。

    ⚠ 锚点必须**单行且唯一**（CRLF 坑见 mut_m6 说明；调用现为两行带 confirmed_deleted）。
    ★ 原 M2「改成 include_uploads=False 但保留 confirmed_deleted=True」**造不出独立缺陷**
      （它就是 M1 的等价形态：不上传原件 + 已确认）⇒ 并入 M1，不硬凑用例数
      （skill G6 第 5 条：报 0 时先问"变异真造出缺陷了吗"）。
    """
    t = _read(MAIN)
    old = "out = purge_company_analysis_artifacts(company_id, include_uploads=True,"
    assert t.count(old) == 1, "M1 锚点不唯一（%d 处）" % t.count(old)
    _write(MAIN, t.replace(old, "out = purge_company_analysis_artifacts(company_id, include_uploads=False,", 1))


def mut_m3_create_company_keeps_tombstone():
    """M3：重建账套不撤销墓碑（id 复用 ⇒ 新企业永远出不来报告）。"""
    t = _read(MAIN)
    old = "    _deleted_company_ids.discard(company.id)"
    assert old in t, "M3 锚点未命中"
    _write(MAIN, t.replace(old, "    pass  # mutated: tombstone kept", 1))


def mut_m4_orphan_artifact_reappears():
    """M4：磁盘上重新出现一个库里不存在的企业的产物（回归场景）。"""
    bak = _read(ORPHAN) if os.path.exists(ORPHAN) else None
    with io.open(ORPHAN, "w", encoding="utf-8") as f:
        json.dump({"report": {"note": "reverse-validation orphan"}}, f, ensure_ascii=False)
    return bak


def mut_m5_orphan_tombstone_reappears():
    """M5：墓碑文件里重新出现一个库里不存在的企业的墓碑。"""
    from runtime_storage import (DELETED_DOCS, load_doc_tombstones,    # noqa: PLC0415
                                 atomic_write_json)
    bak = _read(DELETED_DOCS)
    t = load_doc_tombstones()
    t["88888:reverse_validation_probe.pdf"] = {
        "company_id": 88888, "filename": "reverse_validation_probe.pdf",
        "path": "", "reason": "probe", "purged": True,
        "at": "2026-10-06T00:00:00",
    }
    atomic_write_json(DELETED_DOCS, t)
    return bak



def mut_m7_new_delete_endpoint_without_authority():
    """M7：将来有人新增一个删除端点但**不接清理权威** ⇒ 闸门必须当场报错。"""
    t = _read(MAIN)
    probe = ('\n@app.delete("/api/companies/{company_id}/probe")\n'
             'def probe_delete_endpoint(company_id: int):\n'
             '    return {"ok": True}\n')
    _write(MAIN, t + probe)



def mut_m8_adhoc_delete():
    """M8：某处「顺手删一下」（未走声明的删除出口）⇒ 闸门必须报错。"""
    t = _read(MAIN)
    probe = ('\n\ndef _ad_hoc_cleanup(paths):\n'
             '    for p in paths://n'
             '        os.remove(p)\n')
    _write(MAIN, t + probe)


def mut_m6_guard_removed():
    """M6：拆掉清理权威的**安全护栏**（对在库企业也照清）。

    ★ 2026-10-06 实测事故的变异还原：护栏被拆 ⇒ 对在库企业执行清理 ⇒
      `company_1_full.json` 等被清掉且不可恢复。
    ⚠ 锚点必须**单行** —— 跨行锚点会踩 CRLF 坑（skill G6 第 3 条：本文件按
      `newline=""` 原样读写，行尾是 `\r\n`，含 `\n` 的锚点匹配不上）。
    """
    t = _read(MAIN)
    old = "            if _exists:"
    assert old in t, "M6 锚点未命中"
    _write(MAIN, t.replace(old, "            if False and _exists:", 1))


# (名称, 变异函数, 需还原的文件路径列表, 恢复函数)
MUTS = [
    ("M1 删账套不再调清理权威", mut_m1_delete_company_skips_purge, [MAIN], None),
    ("M3 重建账套不撤销墓碑", mut_m3_create_company_keeps_tombstone, [MAIN], None),
    ("M4 磁盘重现孤儿产物", mut_m4_orphan_artifact_reappears, [ORPHAN], "restore_orphan"),
    ("M5 墓碑重现孤儿企业", mut_m5_orphan_tombstone_reappears,
     [os.path.join(ROOT, "data", "deleted_docs.json")], "restore_tombstone"),
    ("M6 拆掉安全护栏", mut_m6_guard_removed, [MAIN], None),
    ("M7 新增删除端点不接权威", mut_m7_new_delete_endpoint_without_authority, [MAIN], None),
    ("M8 顺手删一下(未走出口)", mut_m8_adhoc_delete, [MAIN], None),
]


def main():
    base, _ = gate_count()
    print("基准（未变异）ERROR = %d" % base)
    if base:
        print("基准不为 0，先修好再做反向验证")
        return 1
    ok = True
    for name, fn, files, restore in MUTS:
        bak = {p: _read(p) for p in files if os.path.exists(p)}
        extra = None
        try:
            extra = fn()
            n, msgs = gate_count()
            good = n > 0
            ok = ok and good
            print("\n%s  →  ERROR %d  %s" % (name, n, "✔ 有效" if good else "✘ 无效（闸门有洞）"))
            for m in msgs[:2]:
                print("      · %s" % m[:130])
        finally:
            for p, t in bak.items():
                _write(p, t)
            if restore == "restore_orphan" and extra is None and os.path.exists(ORPHAN):
                os.remove(ORPHAN)          # 变异前本不存在 ⇒ 删掉注入的探针
            if restore == "restore_tombstone" and extra is not None:
                from runtime_storage import atomic_write_json, DELETED_DOCS  # noqa: PLC0415
                atomic_write_json(DELETED_DOCS, json.loads(extra))
    after, _ = gate_count()
    print("\n全部还原后 ERROR = %d %s" % (after, "✔" if after == 0 else "✘ 还原不干净"))
    return 0 if (ok and after == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
