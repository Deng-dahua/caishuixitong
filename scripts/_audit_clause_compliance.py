# -*- coding: utf-8 -*-
"""条款符合性核验（只读）—— 对【一键分析集成条款10条】+【专注税务风险检查条款5条】逐条取证。

原则（项目铁律）：
  · 不靠肉眼读代码下结论，**以真实产物为准**（默认读 data/cache/last_analysis_cache.json）。
  · **断言"没有 X"前必须全文本反查语境**：本报告大量出现"不构成违法认定""不是税务处理决定"
    这类**合规否定式**，按裸字符串计数会整片假红 ⇒ 判据一律用**肯定式语境**（`_affirmative`）。
  · 取不到数据时明确写「取不到」，绝不用默认值顶替。

用法：
  ./.venv/Scripts/python.exe scripts/_audit_clause_compliance.py [payload.json]
"""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# ★ 必须把项目根加入 sys.path：脚本模式下 `sys.path[0]` 是 `scripts/`，
#   不设会导致 `import engine` **静默失败**、取数全空（本次实测踩过：
#   B4 术语表 / B5 声明全空，而单独 `python -c` 正常）。
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
DEFAULT = os.path.join(ROOT, "data", "cache", "last_analysis_cache.json")

#: 否定/限制词——出现在关键词附近即视为"合规否定式"，不算违规定性
_NEG = ("不", "非", "未", "无", "勿", "禁", "免", "尚未")


def _affirmative(text: str, kw: str, *, span: int = 16, follow_ok=("",)):
    """返回 kw 的**肯定式**用法上下文（剔除否定式与"法条名"等后缀）。"""
    hits, i = [], 0
    while True:
        j = text.find(kw, i)
        if j < 0:
            break
        i = j + len(kw)
        after = text[j + len(kw): j + len(kw) + 1]
        if after in follow_ok:
            continue
        near = text[max(0, j - span): j + len(kw) + span]
        if any(m in near for m in _NEG):
            continue
        hits.append(text[max(0, j - 42): j + len(kw) + 42].replace("\n", " "))
    return hits


def load_report(path: str) -> dict:
    raw = json.loads(open(path, encoding="utf-8", errors="ignore").read())
    if not isinstance(raw, dict):
        return {}
    if "enterprise_readable_report" in raw:
        return raw
    for v in raw.values():
        if isinstance(v, dict):
            rep = v.get("report")
            if isinstance(rep, dict) and isinstance(rep.get("report"), dict):
                return rep["report"]
            if isinstance(rep, dict) and "enterprise_readable_report" in rep:
                return rep
    return {}


def all_text(node, limit: int = 400000) -> str:
    """迭代 + id() 去环收集全部字符串（禁递归，项目铁律⑤）。"""
    out, seen, stack = [], set(), [node]
    while stack and sum(len(x) for x in out) < limit:
        cur = stack.pop()
        if isinstance(cur, str):
            out.append(cur)
            continue
        if isinstance(cur, (dict, list)):
            if id(cur) in seen:
                continue
            seen.add(id(cur))
            stack.extend(cur.values() if isinstance(cur, dict) else cur)
    return "\n".join(out)


RESULTS: list = []


def rec(no: str, clause: str, verdict: str, evidence: str) -> None:
    RESULTS.append((no, clause, verdict, evidence))


def main(path: str) -> int:
    rep = load_report(path)
    if not rep:
        print("!! 未取到报告结构：%s" % path)
        return 2
    err = rep.get("enterprise_readable_report") or {}
    T = all_text(err)
    T_full = all_text(rep)
    oc = err.get("overall_conclusion") or {}
    cp = err.get("confirmed_problems") or []

    # ══════════════ 一键分析集成条款 ══════════════
    pip = rep.get("_one_click_pipeline") or {}
    rec("A1", "所有流程封装为一键分析后端逻辑", "有" if pip else "无",
        "_one_click_pipeline.stages = %s" % list((pip.get("stages") or {}).keys()))

    probe2 = {
        "资料读取": bool(rep.get("file_results") or rep.get("files_count")),
        "行业识别": bool((rep.get("target_entity") or {}).get("industry")),
        "风险扫描": bool(cp or rep.get("all_findings")),
        "报告生成": bool(err),
        "去重": rep.get("_dedup_rate_after") is not None,
        "唯一事实源": bool(rep.get("_fact_store_stats")),
        "引用替换": bool(re.search(r"〔见(疑点|事实)[^〕]*〕", T_full)),
        "等级与证据分离": bool(rep.get("_risk_evidence")),
        "资料缺失单列": bool(rep.get("_material_gap")),
        "法规校验": bool(rep.get("_legal_versions")),
        "自动自检": bool(rep.get("_pipeline_selfcheck")),
        "输出报告": bool(rep.get("analysis_session") or rep.get("compilation_badge")),
    }
    miss2 = [k for k, v in probe2.items() if not v]
    rec("A2", "点击后自动执行 12 步链", "有" if not miss2 else "部分",
        "命中 %d/12；缺：%s" % (12 - len(miss2), miss2 or "无"))

    gap = rep.get("_material_gap") or {}
    have_what = bool(re.search(r"缺失|缺少|未提供|未获取", T))
    have_impact = bool(re.search(r"影响.{0,14}(检查|核实|判断|方向)|受阻|无法完成|未能完成|影响相应", T))
    have_redo = bool(re.search(r"补充.{0,10}(资料|材料).{0,24}(后|之后).{0,16}(重新|再)|重新分析|重新执行", T))
    blocked = rep.get("formal_workpaper_allowed") is False
    still_defer = bool(re.search(r"待核|不作认定|不作出?任何认定|不予排除", T))
    rec("A3", "资料不足：不编造 + 提示(缺什么/影响什么/需补后重跑)",
        "有" if (have_what and have_impact and have_redo and still_defer) else "部分",
        "缺什么=%s 影响什么=%s 需补后重跑=%s 不作认定=%s 阻断正式稿=%s"
        % (have_what, have_impact, have_redo, still_defer, blocked))

    out4 = {
        "执行摘要": bool(oc.get("paragraphs")),
        "风险总表": bool(rep.get("_risk_evidence") or cp),
        "逐项详情": bool((cp[0].get("narrative_paragraphs") or []) if cp else False),
        "资料缺失汇总": bool(gap or err.get("required_doc_coverage")),
        "复查标准": bool(err.get("recheck")),
        "自检报告": bool(rep.get("_pipeline_selfcheck")),
        "系统规则更新说明": bool(rep.get("_knowledge_learn")),
    }
    miss4 = [k for k, v in out4.items() if not v]
    rec("A4", "输出 7 项交付物", "有" if not miss4 else "部分",
        "命中 %d/7；缺：%s" % (7 - len(miss4), miss4 or "无"))

    dr = rep.get("_duplicate_rate") or {}
    three = all(k in dr for k in ("整体", "章节统计", "事实重复"))
    _ch = (dr.get("章节统计") or {}).get("超阈章节")
    _ft = (dr.get("事实重复") or {}).get("超额出现次数合计")
    rec("A5", "去重三项阈值(整体≤10%/同章节≤5%/同一事实≤1)+未达标不得输出",
        "有" if three else "部分",
        "键=%s；整体=%s 章节超阈=%s 事实超额=%s；阻断=%s"
        % (list(dr.keys()), (dr.get("整体") or {}).get("判定"), _ch, _ft, dr.get("阻断")))

    w = rep.get("_wording_audit")
    forb6 = ("已查明违法", "已认定违法", "构成偷税", "属于偷税", "定性成立", "确认虚开", "确定违法")
    hit6 = [k for k in forb6 if _affirmative(T, k)]
    rec("A6", "结论分级引擎：禁越权表述", "有" if (not hit6 and not w) else "部分",
        "_wording_audit 命中=%s；越权定性词(肯定式)=%s"
        % (len(w) if isinstance(w, list) else w, hit6 or "无"))

    lv = rep.get("_legal_versions") or {}
    rec("A7", "法规版本管理器（现行有效 + 待核清单）", "有" if lv.get("summary") else "部分",
        "summary=%s；blocking=%s" % (lv.get("summary"), lv.get("blocking")))

    ip = rep.get("industry_params") or {}
    rec("A8", "行业规则库（必查资料/基准/风险点/话术）", "有" if ip.get("matched") else "部分",
        "matched=%s industry_id=%s risk_families=%d materiality=%s"
        % (ip.get("matched"), ip.get("industry_id"), len(ip.get("risk_families") or []), bool(ip.get("materiality"))))

    mv = rep.get("_report_editions") or {}
    rec("A9", "不脱敏：内部版与对外版内容一致", "有" if mv.get("实质一致性校验") else "部分",
        "内部=%s 对外=%s 实质一致=%s 脱敏标记=%s"
        % (os.path.basename(str(mv.get("internal"))), os.path.basename(str(mv.get("external"))),
           mv.get("实质一致性校验"), mv.get("脱敏标记反查")))

    kl = rep.get("_knowledge_learn") or {}
    n_cases = 0
    try:
        n_cases = len((json.load(open(os.path.join(ROOT, "config", "experience_cases.json"),
                                     encoding="utf-8")) or {}).get("cases") or [])
    except Exception:
        pass
    _kc = kl.get("case") or {}
    # 入库是**幂等**的：第二次跑同一企业 `added=False`（已入库）——那也说明**确实执行了入库**。
    a10_ok = bool(kl.get("learn")) and (
        bool(_kc.get("added")) or "已入库" in str(_kc.get("reason") or ""))
    rec("A10", "报告存样本库 + 提炼新规则 + 更新知识库（闭环）",
        "有" if a10_ok else "部分",
        "自学习 summary=%s；样本入库=%s（%s）；样本库现有 %d 条"
        % (kl.get("summary"), bool(_kc.get("added")), str(_kc.get("reason") or "")[:40], n_cases))

    # ══════════════ 专注税务风险检查条款 ══════════════
    forbid1 = ("税务处理决定", "行政处罚", "移送决定", "法律意见", "财务顾问")
    hit1 = [k for k in forbid1 if _affirmative(T, k, follow_ok=("法", "决"))]
    rec("B1", "只做税务风险检查（不含处理决定/处罚/移送/法律意见/财务顾问）",
        "有" if not hit1 else "部分",
        "禁区词(肯定式，已剔除否定式与法条名)：%s" % (hit1 or "无"))

    five = {
        "风险识别": bool(cp),
        "证据核对": bool((cp[0].get("detail_table") or {}) if cp else False),
        "资料缺口": bool(gap or err.get("material_readiness")),
        "待核事项": ("待核" in T),
        "复查标准": bool(err.get("recheck")),
    }
    miss5 = [k for k, v in five.items() if not v]
    rec("B2", "章节围绕『风险识别—证据核对—资料缺口—待核事项—复查标准』",
        "有" if not miss5 else "部分",
        "实质承载 %d/5（按章节字段判定，不按词面）：%s" % (5 - len(miss5), miss5 or "无"))

    unrel = [k for k in ("绩效考核", "员工评价", "商业建议", "投资建议", "投融资建议")
             if _affirmative(T, k)]
    rec("B3", "无绩效考核/员工评价/商业建议等无关模块", "有" if not unrel else "部分",
        "无关模块词(肯定式)：%s" % (unrel or "无"))

    terms = []
    try:
        from engine import conclusion_grade as _cg
        terms = list(_cg.conclusion_terms())
    except Exception as _e4:  # noqa: BLE001
        print("  [B4 取数失败] %r" % (_e4,))
    want_terms = ["风险信号", "待核事项", "已认定事实", "违法认定"]
    others = {k: T.count(k) for k in ("涉嫌风险事项", "已列明", "待核实事项", "问题事项") if T.count(k)}
    rec("B4", "结论只用统一术语(风险信号/待核事项/已认定事实/违法认定)",
        "有" if (terms == want_terms and not others) else "部分",
        "术语权威表=%s；报告内非统一结论术语=%s（『风险事项/疑点』是结构对象名，不属结论用语）"
        % (terms, others or "无"))

    decl = ""
    try:
        from engine.enterprise_report import _administrative_boundary_statement as _abs
        decl = "".join(_abs() or [])
    except Exception as _e5:  # noqa: BLE001
        print("  [B5 取数失败] %r" % (_e5,))
    b5 = ("不替代税务机关" in decl and "法定程序" in decl) and ("不替代税务机关" in T)
    rec("B5", "报告声明不替代税务机关法定程序认定", "有" if b5 else "无",
        "权威声明=%s；报告内可见=%s" % (decl[:56] or "（取不到）", "不替代税务机关" in T))

    # ── 输出 ──
    W = 78
    print("\n" + "=" * W)
    print("条款符合性核验（真实产物：%s）" % os.path.relpath(path, ROOT))
    print("=" * W)
    cur = ""
    for no, clause, verdict, ev in RESULTS:
        if no[0] != cur:
            cur = no[0]
            print("\n【%s】" % ("一键分析集成条款" if cur == "A" else "专注税务风险检查条款"))
        print("  %-4s [%s] %s" % (no, verdict, clause))
        print("        └─ %s" % ev)
    n_ok = sum(1 for _, _, v, _ in RESULTS if v == "有")
    n_part = sum(1 for _, _, v, _ in RESULTS if v == "部分")
    n_no = sum(1 for _, _, v, _ in RESULTS if v == "无")
    print("\n" + "-" * W)
    print("合计：符合 %d / 部分 %d / 不符合 %d（共 %d 条）" % (n_ok, n_part, n_no, len(RESULTS)))
    print("-" * W)
    # 供报告生成脚本读取（结构化 JSON；设 CLAUSE_JSON=<path> 启用）
    _out = os.environ.get("CLAUSE_JSON")
    if _out:
        try:
            json.dump({"rows": [{"no": n, "clause": c, "verdict": v, "evidence": e}
                                for n, c, v, e in RESULTS],
                       "summary": {"ok": n_ok, "part": n_part, "no": n_no, "total": len(RESULTS)}},
                      open(_out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        except Exception as _je:  # noqa: BLE001
            print("  [JSON 落盘失败] %r" % (_je,))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT))
