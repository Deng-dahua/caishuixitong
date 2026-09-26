# -*- coding: utf-8 -*-
"""用真实资料（只读复制）在临时账套跑全量分析，实测「域产出 vs 进报告」的落差。

安全性：
  · 只从 data/trash/ **复制**（不移动、不删除）用户此前上传的真实资料；
  · 写入临时账套 data/uploads/9999/（本公司不存在于 DB，主体闸门自动跳过）；
  · 跑完清理 9999 目录与 9999 的分析缓存，绝不触碰 data/uploads/1。

用法：python scripts/_scratch_measure.py [--keep]
"""
import glob
import json
import os
import re
import shutil
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# ★ 脚本可能以任意 cwd 执行：main.py 用相对目录挂载 static，且 import main 需根目录在 sys.path
os.chdir(ROOT)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
TRASH = os.path.join(ROOT, "data", "trash")
SCRATCH_CID = 9999
SCRATCH_DIR = os.path.join(ROOT, "data", "uploads", str(SCRATCH_CID))

# 目标：覆盖尽量多的分析域（银行/发票/工资/社保/公积金/余额表/凭证/档案/进销存）
WANT = [
    ("银行", 2), ("取票", 2), ("工资薪金所得", 2), ("社保", 2), ("公积金", 2),
    ("科目余额表", 1), ("序时账", 1), ("供应商档案", 1), ("人员档案", 1),
    ("进项发票列表", 1), ("销项发票列表", 1),
]


def compose():
    os.makedirs(SCRATCH_DIR, exist_ok=True)
    picked, seen = [], set()
    files = sorted(os.listdir(TRASH))
    for pat, n in WANT:
        got = 0
        for fn in files:
            if got >= n or pat in seen:
                continue
            if pat not in fn:
                continue
            # 跳过明显的重命名副本（.1. / .2.）
            if re.search(r"\.\d+\.(xlsx|xls|pdf|csv)$", fn, re.I):
                continue
            try:
                data = open(os.path.join(TRASH, fn), "rb").read()
            except OSError:
                continue
            if not data:
                continue
            orig = re.sub(r"^[0-9]+_[0-9]+_", "", fn)
            dst = os.path.join(SCRATCH_DIR, f"{SCRATCH_CID}_{900 + len(picked)}_{orig}")
            with open(dst, "wb") as fh:
                fh.write(data)
            picked.append(orig)
            got += 1
        seen.add(pat)
    return picked


def run_and_measure():
    # 必须在 import main 之前放好文件（扫描只在导入期执行一次）
    import main
    from database import SessionLocal
    db = SessionLocal()
    try:
        return main._execute_tax_risk_analysis(SCRATCH_CID, db)
    finally:
        db.close()


def main():
    keep = "--keep" in sys.argv
    picked = compose()
    print(f"临时账套 {SCRATCH_CID} 已就位 {len(picked)} 份真实资料（只读复制自 data/trash）：")
    for p in picked:
        print("   ·", p)
    try:
        res = run_and_measure()
    except Exception:
        print("分析异常：\n" + traceback.format_exc()[-1500:])
        res = None
    if isinstance(res, dict) and res.get("ok"):
        rep = res.get("report") or {}
        final = [f for f in (rep.get("all_findings") or []) if isinstance(f, dict)]
        ftypes = {str(f.get("type") or "") for f in final}
        print(f"\n报告最终发现 {len(final)} 条（文件 {rep.get('files_count')}）")
        print("=" * 80)
        print("%-24s %5s %5s %5s  %s" % ("域", "产出", "进报告", "被吞", "被吞的发现"))
        print("-" * 80)
        tp = td = 0
        rows = []
        for d in (rep.get("domain_summary") or []):
            if not isinstance(d, dict):
                continue
            fs = [f for f in (d.get("findings") or []) if isinstance(f, dict)]
            if not fs:
                continue
            kept = [f for f in fs if str(f.get("type") or "") in ftypes]
            dropped = [f for f in fs if str(f.get("type") or "") not in ftypes]
            rows.append((len(dropped), str(d.get("domain") or ""), len(fs), len(kept), dropped))
            tp += len(fs)
            td += len(dropped)
        for nd, dn, prod, kept, dropped in sorted(rows, reverse=True):
            flag = "⚠" if nd else "✓"
            print("%s %-22s %5d %5d %5d  %s" % (
                flag, dn[:22], prod, kept, nd,
                "、".join(str(f.get("type"))[:26] for f in dropped[:4])))
        print("-" * 80)
        print(f"合计：域产出 {tp} 条，被吞 {td} 条（{td/max(tp,1):.0%}）")
        # 报告最终层面的等级分布（验证非法等级是否被吞）
        from collections import Counter
        print("\n报告最终发现的等级分布:", dict(Counter(str(f.get("level")) for f in final)))
        print("\n关键日志（场景执行核心 / 隔离 / 原子规则）:")
        for ln in (rep.get("pipeline_log") or []):
            s = str(ln)
            if any(k in s for k in ("场景执行核心", "旧式候选", "可信观察", "隔离",
                                    "原子规则", "域分析", "分析覆盖")):
                print("   ", s[:230])
    else:
        print("! 分析未成功:", json.dumps(res, ensure_ascii=False)[:600] if isinstance(res, dict) else res)

    if not keep:
        shutil.rmtree(SCRATCH_DIR, ignore_errors=True)
        print(f"\n[清理] 已删除临时账套目录 {SCRATCH_DIR}")
        for p in (os.path.join(ROOT, "data", "cache", "last_analysis_cache.json"),
                  os.path.join(ROOT, "data", "cache", "analysis_history.json"),
                  os.path.join(ROOT, "data", "uploads", "checkpoints", f"{SCRATCH_CID}.json")):
            try:
                if os.path.exists(p) and p.endswith(f"{SCRATCH_CID}.json"):
                    os.remove(p)
            except OSError:
                pass
    else:
        print(f"\n[保留] 临时账套目录：{SCRATCH_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
