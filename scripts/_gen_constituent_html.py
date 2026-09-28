# -*- coding: utf-8 -*-
"""由 engine/tax_redlines.REDLINES 程序化生成「红线构成要件明细清单.html」。

展示两条对称的维度：
  - constituents（涉嫌要件/风险场景）：含本轮新增场景标记「新增」；
  - justifications（正当理由/反证，论证链 rebuttals 维度）：含本轮新增反证标记「新增反证」。
两者同源：justifications 末项豁免清单由 constituents 末项出罪要件抽离；本轮 constituents 追加 70 个新场景，
justifications 同步追加 70 条对应出证反证（总数 228 -> 298）。
"""
import html
import os

import engine.tax_redlines as T

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "红线构成要件明细清单.html")

# 本轮各红线新增场景数（与 enrich 脚本一致），用于标记 constituents「新增」
EXTRA_N = {
    "RL-VAT-001": 2, "RL-VAT-002": 2, "RL-VAT-003": 1, "RL-VAT-004": 1,
    "RL-VAT-005": 1, "RL-VAT-006": 1, "RL-VAT-007": 1, "RL-VAT-008": 1,
    "RL-VAT-009": 1, "RL-VAT-010": 1, "RL-VAT-011": 1, "RL-INC-001": 1,
    "RL-INC-002": 1, "RL-INC-003": 1, "RL-INC-004": 1, "RL-COST-001": 1,
    "RL-COST-002": 1, "RL-COST-003": 1, "RL-COST-004": 1, "RL-COST-005": 1,
    "RL-COST-006": 1, "RL-FUND-001": 1, "RL-FUND-002": 1, "RL-FUND-003": 1,
    "RL-FUND-004": 1, "RL-FUND-005": 1, "RL-FUND-006": 1, "RL-INV-001": 1,
    "RL-INV-002": 1, "RL-INV-003": 1, "RL-PAY-001": 1, "RL-PAY-002": 1,
    "RL-PAY-003": 1, "RL-PAY-004": 1, "RL-PAY-005": 1, "RL-PAY-006": 1,
    "RL-CIT-001": 1, "RL-CIT-002": 1, "RL-CIT-003": 1, "RL-CIT-004": 1,
    "RL-CIT-005": 1, "RL-CIT-006": 1, "RL-CIT-007": 1, "RL-PTY-001": 1,
    "RL-PTY-002": 1, "RL-PTY-003": 1, "RL-PTY-004": 1, "RL-PTY-005": 1,
    "RL-AST-001": 1, "RL-AST-002": 1, "RL-AST-003": 1, "RL-OTH-001": 1,
    "RL-OTH-002": 1, "RL-OTH-003": 1, "RL-OTH-004": 1, "RL-OTH-005": 1,
    "RL-OTH-006": 1, "RL-SPT-001": 1, "RL-SPT-002": 1, "RL-SPT-003": 1,
    "RL-SPT-004": 1, "RL-SPT-005": 1, "RL-SPT-006": 1, "RL-SPT-007": 1,
    "RL-SPT-008": 1, "RL-SPT-009": 1, "RL-SPT-010": 1, "RL-SPT-011": 1,
}
# justifications 基线（enrich 前每条红线条数），用于标记「新增反证」
ORIG_J = {"RL-VAT-001": 4, "RL-VAT-002": 4, "RL-VAT-003": 3, "RL-VAT-004": 3,
          "RL-VAT-005": 3, "RL-VAT-006": 3, "RL-VAT-007": 3, "RL-INC-001": 4,
          "RL-INC-002": 3, "RL-INC-003": 3, "RL-INC-004": 3, "RL-COST-001": 3,
          "RL-COST-002": 3, "RL-COST-003": 3, "RL-COST-004": 4, "RL-COST-005": 3,
          "RL-FUND-001": 3, "RL-FUND-002": 3, "RL-FUND-003": 3, "RL-FUND-004": 2,
          "RL-FUND-005": 3, "RL-FUND-006": 3, "RL-INV-001": 3, "RL-INV-002": 3,
          "RL-INV-003": 3, "RL-PAY-001": 5, "RL-PAY-002": 3, "RL-PAY-003": 3,
          "RL-PAY-004": 3, "RL-CIT-001": 3, "RL-CIT-002": 3, "RL-CIT-003": 3,
          "RL-CIT-004": 3, "RL-PTY-001": 5, "RL-PTY-002": 7, "RL-PTY-003": 3,
          "RL-PTY-004": 3, "RL-PTY-005": 3, "RL-AST-001": 3, "RL-AST-002": 3,
          "RL-AST-003": 3, "RL-OTH-001": 3, "RL-OTH-002": 3, "RL-OTH-003": 2,
          "RL-SPT-001": 4, "RL-SPT-002": 4, "RL-SPT-003": 4, "RL-SPT-004": 4,
          "RL-SPT-005": 4, "RL-SPT-006": 5, "RL-SPT-007": 5, "RL-SPT-008": 4,
          "RL-SPT-009": 5, "RL-SPT-010": 4, "RL-SPT-011": 4, "RL-CIT-005": 3,
          "RL-CIT-006": 3, "RL-PAY-005": 3, "RL-PAY-006": 3, "RL-OTH-004": 3,
          "RL-OTH-005": 3, "RL-VAT-008": 3, "RL-VAT-009": 3, "RL-COST-006": 3,
          "RL-CIT-007": 3, "RL-VAT-010": 3, "RL-VAT-011": 3, "RL-OTH-006": 3}


def main():
    total_cons = 0
    total_new = 0
    total_j = 0
    total_j_new = 0
    items = []
    for rl in T.REDLINES:
        rid = rl["id"]
        name = rl["name"]
        taxes = "、".join(rl.get("taxes") or [])
        cons = rl.get("constituents") or []
        jus = rl.get("justifications") or []
        n_new = EXTRA_N.get(rid, 0)
        n_j_new = max(0, len(jus) - ORIG_J.get(rid, 0))
        total_cons += len(cons)
        total_new += n_new
        total_j += len(jus)
        total_j_new += n_j_new

        # constituents 列表
        clis = []
        for i, c in enumerate(cons, 1):
            is_exempt = ("不属于" in c) or ("豁免" in c)
            is_new = (i > len(cons) - n_new) and not is_exempt
            cls = "exempt" if is_exempt else ("new" if is_new else "normal")
            badge = '<span class="badge-new">新增</span>' if is_new else ""
            clis.append('<li class="%s"><b>[%d]</b> %s %s</li>' % (
                cls, i, html.escape(c), badge))

        # justifications 列表（反证/正当理由）
        jlis = []
        for i, j in enumerate(jus, 1):
            is_new_j = i > ORIG_J.get(rid, 0)
            cls = "rebut-new" if is_new_j else "rebut"
            badge = '<span class="badge-newj">新增反证</span>' if is_new_j else ""
            jlis.append('<li class="%s"><b>[%d]</b> %s %s</li>' % (
                cls, i, html.escape(j), badge))

        items.append(
            '<details class="rl"><summary><span class="rid">%s</span> %s '
            '<span class="tax">[%s]</span></summary>'
            '<div class="sec-h">① 构成要件 / 涉嫌场景（%d 项）</div>'
            '<ul class="cons">%s</ul>'
            '<div class="sec-h rebut-h">② 正当理由 / 反证（%d 条，论证链 rebuttals）</div>'
            '<ul class="rebuts">%s</ul>'
            '</details>' % (
                html.escape(rid), html.escape(name), html.escape(taxes),
                len(cons), "".join(clis), len(jus), "".join(jlis))
        )

    doc = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>税务红线构成要件与反证明细清单</title>
<style>
body{font-family:"Microsoft YaHei",-apple-system,sans-serif;margin:24px;color:#1f2329;background:#fafbfc}
h1{font-size:22px;border-bottom:3px solid #2b6cb0;padding-bottom:8px}
.meta{color:#666;font-size:13px;margin:6px 0 18px}
.rl{border:1px solid #e3e8ef;border-radius:8px;margin:6px 0;background:#fff;overflow:hidden}
summary{cursor:pointer;padding:10px 14px;font-weight:600;background:#f3f7fc}
summary:hover{background:#e8f0fa}
.rid{display:inline-block;min-width:96px;color:#2b6cb0;font-family:monospace}
.tax{color:#888;font-size:12px;font-weight:400;margin-left:6px}
.sec-h{margin:10px 0 4px 30px;font-size:13px;font-weight:700;color:#444}
.rebut-h{color:#b0591a}
.cons,.rebuts{margin:4px 0 6px 0;padding-left:30px}
.cons li,.rebuts li{margin:5px 0;line-height:1.6}
.exempt{color:#1a5fb4;background:#eef5ff;padding:2px 6px;border-radius:4px}
.new{background:#eafaf0;padding:2px 6px;border-radius:4px;border-left:3px solid #2f9e44}
.normal{}
.rebut{background:#fff7ed;padding:2px 6px;border-radius:4px;border-left:3px solid #f59f00}
.rebut-new{background:#fff1e6;padding:2px 6px;border-radius:4px;border-left:3px solid #e8590c}
.badge-new{display:inline-block;background:#2f9e44;color:#fff;font-size:11px;border-radius:3px;padding:0 5px;margin-left:6px;vertical-align:middle}
.badge-newj{display:inline-block;background:#e8590c;color:#fff;font-size:11px;border-radius:3px;padding:0 5px;margin-left:6px;vertical-align:middle}
.legend{font-size:12px;color:#666;margin-top:10px}
.legend b{color:#1a5fb4}
</style></head><body>
<h1>税务红线构成要件与反证明细清单</h1>
<div class="meta">共 %d 条红线 · 构成要件 %d 项（本轮新增 %d 项风险场景）· 正当理由/反证 %d 条（本轮新增 %d 条出证反证）。
① 浅蓝=出罪要件（豁免/正当情形）；绿底「新增」=本轮追加涉嫌场景。② 橙底=反证（出证口）；深橙「新增反证」=本轮为新增场景补的对应反证。</div>
%s
<div class="legend">图例：<b>浅蓝</b>=出罪要件（豁免/正当情形）&nbsp;|&nbsp;<b>绿底</b>=本轮新增风险场景&nbsp;|&nbsp;<b>橙底</b>=正当理由/反证（出证口）&nbsp;|&nbsp;<b>深橙</b>=本轮新增反证</div>
</body></html>""" % (len(T.REDLINES), total_cons, total_new, total_j, total_j_new, "\n".join(items))

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(doc)
    print("OK: 生成 %s（%d 红线 / 要件 %d(新%d) / 反证 %d(新%d)）"
          % (OUT, len(T.REDLINES), total_cons, total_new, total_j, total_j_new))


if __name__ == "__main__":
    main()
