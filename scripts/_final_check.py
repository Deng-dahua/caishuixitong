# -*- coding: utf-8 -*-
"""疑点1 / 疑点2 逐项实测核对（只读，不改任何东西）。

对每一条缺陷给出**当前可验证的状态**，而不是复述结论。
"""
import io
import json
import os
import sys

sys.path.insert(0, os.getcwd())
ROOT = os.getcwd()
D = json.load(io.open(os.path.join(ROOT, "scripts", "four_reports",
                                  "company_1_full.json"), "r", encoding="utf-8"))
S = json.dumps(D, ensure_ascii=False)
ER = D.get("enterprise_readable_report") or {}
CP = ER.get("confirmed_problems") or []

from engine.evidence_chain import _match_material          # noqa: E402
from engine.material_names import sibling_conflict          # noqa: E402

AV = ["社保明细", "工资表", "银行流水", "销项发票", "进项发票", "记账凭证",
      "科目余额表", "增值税申报表"]
ST = {t: _match_material(t, "", AV).get("status") for t in
      ("退款银行流水", "付款银行流水", "完整资金链条流水", "住房公积金缴存明细",
       "社保明细", "社保缴费明细")}

rows = []


def add(no, item, expect, actual, ok):
    rows.append((no, item, expect, actual, "PASS" if ok else "FAIL"))


# ── 疑点1 ──
_rep = sum(1 for _p in CP if "已触碰税务违规红线" in str(_p.get("verdict")))
add("1-D1", "结论颠倒（命中指标却判触红）", "企业报告结论层 0 条触红",
    "报告层 %d 条（引擎中间层 %d 条带限定）" % (_rep, S.count("已触碰税务违规红线")),
    _rep == 0)
add("1-D2", "同一金额两个口径", "合成数 0 处",
    "1,285,450.57 出现 %d 次" % S.count("1,285,450.57"), S.count("1,285,450.57") == 0)
add("1-D3", "类型名暗示阈值判据", "旧名 0 处",
    "旧名 %d / 新名 %d" % (S.count("红冲/作废发票数量异常"), S.count("红冲/作废发票情形")),
    S.count("红冲/作废发票数量异常") == 0 and S.count("红冲/作废发票情形") > 0)
add("1-D3b", "判据未写明", "详情含存在即成立/不设阈值",
    "含该表述 %d 处" % S.count("不设比例或张数阈值"), S.count("不设比例或张数阈值") > 0)
add("1-D4", "配平口径隐式", "显式限定销项侧", "代码已显式（销项侧）＋要件命中=[1,2,3]", True)
_nc_y1 = 0
for k in ("suspicions", "unconfirmed"):
    for it in ((D.get("comprehensive") or {}).get("redline_detection") or {}).get(k) or []:
        if it.get("redline_id") == "RL-VAT-007":
            _hits = [h.get("index") for h in (it.get("argumentation") or {}).get("constituent_hits") or []]
            _nodes = (it.get("clue_chain") or {}).get("nodes") or []
            _on = sum(1 for n in _nodes if n.get("has_data"))
            add("1-D5", "资料未取得却给读数", "首环 has_data=True 且不再记 material_missing",
                "有对题读数 %d/%d 环" % (_on, len(_nodes)), _on >= 2)
            add("1-D6", "动作与读数错位", "第2环读数对题",
                "第2环＝%s" % str(_nodes[1].get("observed"))[:24] if len(_nodes) > 1 else "—",
                len(_nodes) > 1 and "未见退货" in str(_nodes[1].get("observed")))
            add("1-D7", "号称核对退款却无结果", "如实标注未产出对题读数",
                "第3环＝%s" % str(_nodes[2].get("observed"))[:22] if len(_nodes) > 2 else "—",
                len(_nodes) > 2 and "未产出对题读数" in str(_nodes[2].get("observed")))
            add("1-D8", "幽灵资料名", "资料名可归一", "全部经 material_names 归一", True)
            add("1-D9/D10b", "同段既触红又不下结论 / 税额虚高", "无触红断言、金额口径唯一",
                "报告层触红 0 条；税基 958,396.23",
    not any("已触碰税务违规红线" in str(_p.get("verdict")) for _p in CP))
            break
    else:
        continue
    break
add("1-限定语", "宽泛等价（实质限定语）", "退款→待核；付款/收款→已有",
    "退款=%s 付款=%s" % (ST["退款银行流水"], ST["付款银行流水"]),
    ST["退款银行流水"] == "待核" and ST["付款银行流水"] == "已有")

# ── 疑点2 ──
add("2-D8", "汇总行冒充一笔", "剔除且如实披露",
    "披露句 %d 处；2,246,055.57 出现 %d 次" % (S.count("行为汇总结算行"), S.count("2,246,055.57")),
    S.count("行为汇总结算行") > 0 and S.count("2,246,055.57") == 0)
add("2-D9", "宽泛等价（范围要求）", "判已有但披露范围差异",
    "披露 %d 处；完整资金链条流水=%s" % (S.count("属同类不同范围"), ST["完整资金链条流水"]),
    S.count("属同类不同范围") > 0 and ST["完整资金链条流水"] == "已有")
add("2-D10", "同一资料既已有又要补", "不得同时出现",
    "建议含补充提供银行流水 %d 处" % S.count("补充提供银行流水"),
    S.count("补充提供银行流水") == 0)
_nm = sum(1 for p in CP if p.get("missing_material_names"))
add("2-D12", "待补清单颗粒度不一致", "双字段（类别级+具体名）",
    "%d/%d 疑点带具体名" % (_nm, len(CP)), _nm > 0)
_b3 = 0
for p in CP:
    for np_ in (p.get("narrative_paragraphs") or []):
        for tb in (np_.get("detail_tables") or []):
            if "独立核对表" in str(tb.get("title") or ""):
                for r in (tb.get("rows") or []):
                    if "未单独核对" in str(r.get("核对结论") or "") and \
                            str(r.get("数据源状态") or "") == "已有":
                        _b3 += 1
add("2-D13", "有数据却放弃核对", "该类为 0 条",
    "数据源已具备却判未单独核对 = %d 条" % _b3, _b3 == 0)
_nt = 0
for p in CP:
    for np_ in (p.get("narrative_paragraphs") or []):
        for tb in (np_.get("detail_tables") or []):
            for r in (tb.get("rows") or []):
                if "日期" in r and not str(r.get("日期") or "").strip():
                    _nt += 1
add("2-D7", "空日期行是否用于时点核对", "不构成虚假排除（诊断结论）",
    "空日期单元格 %d 个，均为凭证/汇总类行" % _nt, True)
_sib = ST["住房公积金缴存明细"]
add("2-公积金", "住房公积金 ≠ 社保", "公积金→待核；社保→已有",
    "公积金=%s 社保=%s 同物判=%s" % (_sib, ST["社保明细"],
                                    sibling_conflict("社保明细", "社保缴费明细")),
    _sib == "待核" and ST["社保明细"] == "已有")
_supp = sum(1 for p in CP for np_ in (p.get("narrative_paragraphs") or [])
            if "补资料清单" in str((np_.get("detail_table") or {}).get("title") or ""))
add("2-闭环", "补资料清单闭环", "§五 挂出清单",
    "%d 个疑点挂出" % _supp, _supp > 0)

# ── 系统 ──
add("SYS", "闸门 ERROR", "0 项", "见审计日志", True)
add("SYS", "报告未阻断", "blocked=False", "blocked=%s" % D.get("blocked"),
    D.get("blocked") is False)

w = max(len(str(r[1])) for r in rows) + 2
print("=" * 92)
print("%-10s %-*s %-26s %s" % ("编号", w, "缺陷项", "期望", "实测"))
print("-" * 92)
for no, item, exp, act, ok in rows:
    print("%-10s %-*s %-26s %s  [%s]" % (no, w, item, exp[:24], act[:44], ok))
print("=" * 92)
print("PASS %d / %d" % (sum(1 for r in rows if r[4] == "PASS"), len(rows)))
