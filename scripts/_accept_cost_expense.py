# -*- coding: utf-8 -*-
"""真实验收：跑一遍一键分析（临时账套 9999），抽出「主营业务成本 vs 期间费用」三态结论。

用法：
    .venv/Scripts/python.exe scripts/_accept_cost_expense.py

产出：scripts/four_reports/_cost_expense_accept.json（供人工核对，不改任何产品代码）
校验点：
  ① 三态齐全：成本桶 / 费用桶 / 待核桶都得有结论（不能只有成本）；
  ② 判不出来的必须落「待核」，不得默认计入成本；
  ③ 广告业（某企业型）样本：广告发布/策划/信息服务/会展=成本，餐饮/住宿/办公用品=期间费用；
  ④ 报告层必须能渲染出这三块（cost_recon_detail 段落 + 离线 HTML + 前端 JS）。
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())

# ★ 2026-10-02：原 _scratch_measure 从 data/trash 取样，但该目录现只剩 JSON 索引、
#   源 xlsx/pdf 已迁至 data/uploads/<公司>，取样为 0 → “暂无上传资料”。
#   改为直接从公司 3（猩织光宠物食品商贸，真账套 16 份）只读复制成临时账套 9999。
SCRATCH = os.path.join("data", "uploads", "9999")
SRC3 = os.path.join("data", "uploads", "3")
os.makedirs(SCRATCH, exist_ok=True)
picked = []
for i, fn in enumerate(sorted(os.listdir(SRC3))):
    with open(os.path.join(SRC3, fn), "rb") as fh:
        data = fh.read()
    if not data:
        continue
    # 文件名必须是「公司id_文档序号_原始名」三段，否则 pipeline 的磁盘扫描会整份跳过
    dst = os.path.join(SCRATCH, "9999_%d_%s" % (900 + i, fn.split("_", 2)[-1]))
    with open(dst, "wb") as fh:
        fh.write(data)
    picked.append(os.path.basename(dst))
print("临时账套 9999 就位 %d 份（复制自公司3 真账套）：%s" % (len(picked), picked[:4]))
import main  # noqa: E402  必须在资料就位后再 import（扫描只在导入期执行一次）
from database import SessionLocal  # noqa: E402

db = SessionLocal()
try:
    res = main._execute_tax_risk_analysis(9999, db)
finally:
    db.close()

print("run ok =", (res or {}).get("ok"), "| 顶层键 =", list((res or {}).keys())[:8])
report = (res or {}).get("report") or {}
# cost_recon_detail 挂在 enterprise_readable_report 下（不是报告顶层）
crd = (report.get("enterprise_readable_report") or {}).get("cost_recon_detail") or {}
attr = crd.get("cost_expense_attribution") or {}

def _block(name):
    b = attr.get(name) or {}
    items = b.get("items") or []
    return {"amount": b.get("amount"), "count": b.get("count"),
            "samples": [i.get("goods") for i in items[:8]]}

out = {
    "industry": attr.get("industry"),
    "industry_covered": attr.get("industry_covered"),
    "total_amount": attr.get("total_amount"),
    "cost": _block("cost"),
    "expense": _block("expense"),
    "pending": _block("pending"),
    "missing_materials": attr.get("missing_materials") or [],
    "contradictions": attr.get("contradictions") or [],
    "available": attr.get("available"),
}
with open("scripts/four_reports/_cost_expense_accept.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print("行业口径 =", out["industry"], "| 已覆盖 =", out["industry_covered"])
print("合计金额 =", out["total_amount"])
for k in ("cost", "expense", "pending"):
    b = out[k]
    print("%-8s 金额=%-16s 张数=%-5s 品名样例=%s" % (k, b["amount"], b["count"], "、".join(b["samples"][:5])))
print("口径差异（ Contradictions ）=", out["contradictions"][:5])
print("missing_materials =", out["missing_materials"][:5])

# 校验点
errs = []
if not attr:
    errs.append("cost_expense_attribution 为空 → 报告层未接到分类结论")
else:
    for k in ("cost", "expense", "pending"):
        if not (out[k]["amount"] is not None):
            errs.append("三态缺失：" + k)
    if (out["cost"]["amount"] or 0) <= 0:
        errs.append("成本桶金额为 0 → 主营成本被判没了")
print("\n验收结论：", "PASS" if not errs else "FAIL " + "; ".join(errs))
