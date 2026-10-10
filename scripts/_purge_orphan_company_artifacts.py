# -*- coding: utf-8 -*-
"""孤儿产物修复：磁盘上**按公司 id** 存在、但库里已无该企业的派生物 ⇒ 全部清掉。

## 为什么必须有它（用户 2026-10-06 原话）
> 「若是在系统上进行了删除处理的，你能不能设置成与之相应的文件都删除和修改相应的信息。
>   例如4个产物就必须改为1个产物，公司2/3/4的缓存或相应的资料和信息都应该删除。
>   待重新建立时再新建文件。就是这些常规的思考和动作，能不能都做到位，不要踢一脚动一下！！！」

机制上已做两件事：
  ① 删除账套端点现在走唯一权威 `main.purge_company_analysis_artifacts(include_uploads=True)`，
     以后**在系统里删**就会连派生物一起清；
  ② 本脚本处理**已经残留**的历史孤儿（库被重置过，账套是直接从库里消失的，没走删除端点）。

判据（与闸门 `check_company_artifact_consistency` 完全一致）：
  · `scripts/four_reports/**/company_{id}_*`
  · `data/uploads/{id}/`、`data/uploads/checkpoints/{id}.json`、`data/uploads/transfer/{id}_*`
  · `data/cache/last_analysis_cache.json` 的键
  · `data/deleted_docs.json` 里 `company_id == id` 的墓碑
  凡 id 不在 `companies` 表 ⇒ 属孤儿，逐项清掉（走 `purge_file` ⇒ 进项目回收站，可恢复）。

用法：
    ./.venv/Scripts/python.exe scripts/_purge_orphan_company_artifacts.py           # 只列出
    ./.venv/Scripts/python.exe scripts/_purge_orphan_company_artifacts.py --apply   # 真清
"""
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")

REP_ROOT = os.path.join(ROOT, "scripts", "four_reports")


def _db_company_ids():
    from database import Company                                        # noqa: PLC0415
    from database import SessionLocal                                   # noqa: PLC0415
    db = SessionLocal()
    try:
        return {int(r) for (r,) in db.query(Company.id).all()}
    finally:
        db.close()


def _scan(db_ids):
    """返回 {orphan_id: [描述, ...]}。判据与闸门一致。"""
    from runtime_storage import load_doc_tombstones, read_json          # noqa: PLC0415
    from shared_state import _last_analysis_cache                       # noqa: PLC0415
    out = {}

    def add(cid, desc):
        out.setdefault(int(cid), []).append(desc)

    # ① 离线产物（递归：four_reports/ 与 four_reports/readable/）
    if os.path.isdir(REP_ROOT):
        for _root, _dirs, _files in os.walk(REP_ROOT):
            for fn in _files:
                if fn.startswith("company_") and "_" in fn:
                    try:
                        cid = int(fn.split("_")[1])
                    except (ValueError, IndexError):
                        continue
                    if cid not in db_ids:
                        add(cid, "离线产物 " + os.path.relpath(os.path.join(_root, fn), REP_ROOT))
    # ② 上传原件目录
    up = os.path.join(ROOT, "data", "uploads")
    if os.path.isdir(up):
        for name in os.listdir(up):
            if not name.isdigit():
                continue
            cid = int(name)
            if cid not in db_ids and os.path.isdir(os.path.join(up, name)):
                add(cid, "上传原件目录 data/uploads/%d/" % cid)
    # ③ 检查点
    ck = os.path.join(up, "checkpoints")
    if os.path.isdir(ck):
        for fn in os.listdir(ck):
            if fn.endswith(".json") and fn[:-5].isdigit():
                cid = int(fn[:-5])
                if cid not in db_ids:
                    add(cid, "检查点 data/uploads/checkpoints/%s" % fn)
    # ④ 中转站解析缓存
    tr = os.path.join(up, "transfer")
    if os.path.isdir(tr):
        for fn in os.listdir(tr):
            head = fn.split("_")[0]
            if head.isdigit():
                cid = int(head)
                if cid not in db_ids:
                    add(cid, "中转站缓存 data/uploads/transfer/%s" % fn)
    # ⑤ 磁盘分析缓存
    try:
        disk = read_json(os.path.join(ROOT, "data", "cache", "last_analysis_cache.json"), {})
        if isinstance(disk, dict):
            for k in disk:
                if str(k).isdigit() and int(k) not in db_ids:
                    add(int(k), "磁盘分析缓存 last_analysis_cache[%s]" % k)
    except Exception:
        pass
    # ⑥ 内存分析缓存（本进程内可见才清得掉；脚本进程里通常为空，如实列出）
    try:
        for k in list(_last_analysis_cache.keys()):
            if int(k) not in db_ids:
                add(int(k), "内存分析缓存[%s]" % k)
    except Exception:
        pass
    # ⑦ 资料删除墓碑
    try:
        for v in load_doc_tombstones().values():
            cid = int((v or {}).get("company_id") or 0)
            if cid and cid not in db_ids:
                add(cid, "资料删除墓碑（company_id=%d）" % cid)
    except Exception:
        pass
    return out


def main():
    db_ids = _db_company_ids()
    print("数据库在库企业 id：%r" % sorted(db_ids))
    orphans = _scan(db_ids)
    if not orphans:
        print("✓ 无孤儿派生物（磁盘/缓存与数据库一致）")
        return 0
    total = sum(len(v) for v in orphans.values())
    print("发现孤儿派生物：企业 id %r，共 %d 项"
          % (sorted(orphans), total))
    for cid in sorted(orphans):
        for desc in orphans[cid]:
            print("   - [%d] %s" % (cid, desc))
    if "--apply" not in sys.argv:
        print("\n（只列出，未清理。加 --apply 执行清理；清理走 purge_file ⇒ 移入 data/trash，可恢复）")
        return 1
    from main import purge_company_analysis_artifacts                   # noqa: PLC0415
    print("\n开始清理……")
    for cid in sorted(orphans):
        out = purge_company_analysis_artifacts(cid, include_uploads=True)
        print("  企业 %d：清理 %d 处（%s）%s"
              % (cid, len(out["cleared"]), "、".join(out["cleared"]),
                 ("；残留：" + "、".join(out["leftovers"])) if out["leftovers"] else ""))
    # 复扫确认
    left = _scan(_db_company_ids())
    if left:
        print("\n✘ 仍有残留：%r" % {k: v[:3] for k, v in left.items()})
        return 2
    print("\n✓ 复扫通过：磁盘/缓存与数据库已一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
