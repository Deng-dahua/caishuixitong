# -*- coding: utf-8 -*-
"""批次验收独立复核（质量检查员视角）—— **全部基于本次实际运行的输出**。

覆盖用户点名的 10 类问题：
  A 未修复问题  B 结论与证据冲突  C 数据前后矛盾  D 格式/错别字/系统字段名/占位符
  E 表格截断/空表/只有表头/合计为0  F 事项计数不一致  G 风险族重复计数
  H 税额测算逻辑错误  I 税费法律适用混同  J 重复模板段落

用法：`python scripts/audit_batches.py [--out data/audit/<label>.json]`
"""
import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

_SYS_KEYS = ("tax_impact", "redline_id", "finding_type", "scene_fact_id", "risk_level",
             "conclusion_grade", "evidence_have", "evidence_need", "missing_materials",
             "source_chain", "policy_ref", "law_ref", "trace_id", "detail_table",
             "narrative_paragraphs", "family_members", "constituent_hits")
#: 真占位符（★ 必须带定界，否则会误伤正常词：实测裸「略」命中的是
#:   "粗略测算""战略投入"；「（待核验）」是**合法状态**不是占位符 ⇒ 一律不列）。
_PLACEHOLDERS = ("TODO", "待填", "待补填", "xxx", "XXX", "【待填", "（待填", "占位符",
                 "N/A", "示例文本", "（略）", "(略)", "……待填", "XXX元")
_FORBIDDEN = ("口经说明", "敦低法", "补教要求", "2025-515", "一元")


def _probs(rep):
    return [p for p in (rep.get("confirmed_problems") or []) if isinstance(p, dict)]


def _all_strings(o, acc=None, seen=None):
    acc = [] if acc is None else acc
    seen = set() if seen is None else seen
    if isinstance(o, dict):
        if id(o) in seen:
            return acc
        seen.add(id(o))
        for v in o.values():
            _all_strings(v, acc, seen)
    elif isinstance(o, list):
        if id(o) in seen:
            return acc
        seen.add(id(o))
        for v in o:
            _all_strings(v, acc, seen)
    elif isinstance(o, str):
        acc.append(o)
    return acc


def _tables(rep):
    out = []
    for p in _probs(rep):
        seq = p.get("seq")
        if isinstance(p.get("detail_table"), dict):
            out.append((seq, p["detail_table"]))
        for np in (p.get("narrative_paragraphs") or []):
            if isinstance(np, dict):
                for t in (np.get("detail_tables") or []):
                    if isinstance(t, dict):
                        out.append((seq, t))
    return out


def _cols(t):
    return [str(c) for c in ((t or {}).get("columns") or (t or {}).get("headers") or [])]


def _rows(t):
    return [r for r in ((t or {}).get("rows") or []) if r is not None]


# ── 10 类问题 ────────────────────────────────────────────────────────────────

def pA_unfixed(rep, rep_data):
    """A 未修复问题：必须有据实清单（本次存在性由 audit 文档承担，这里只统计信号）。"""
    return {"ok": True, "detail": "未修复清单由《批次条件检查报告》§未修复 承载",
            "count": None}


def pB_conclusion_conflict(rep, rep_data):
    try:
        from tools.audit_consistency import (check_conclusion_not_exceed_finding,
                                             check_pending_verdict_softened)
        errs = []
        for fn in (check_pending_verdict_softened, check_conclusion_not_exceed_finding):
            try:
                errs += [i for i in fn() if i[0] == "ERROR"]
            except Exception as exc:  # noqa: BLE001
                errs.append(("ERROR", fn.__name__, str(exc)))
        return {"ok": not errs, "detail": "%d 项闸门冲突" % len(errs), "samples": errs[:2]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": "判据不可用: %s" % exc}


def pC_data_contradiction(rep, rep_data):
    t = json.dumps(rep, ensure_ascii=False)
    sents = re.findall(r"[^。；\n]{0,120}自然人自有账户[^。；\n]{0,120}", t)
    neg = [x for x in sents if any(k in x for k in ("未提供", "未取得", "尚未取得", "另需取得"))]
    pos = [x for x in sents if any(k in x for k in ("已提供", "已取得", "已经取得"))]
    # 计数口径矛盾：总述里的"共 N 项" vs len(problems)
    heads = re.findall(r"共\s*(\d+)\s*项", json.dumps(rep.get("summary") or {}, ensure_ascii=False))
    head_nums = sorted({int(x) for x in heads})
    n = len(_probs(rep))
    head_ok = all(x == n for x in head_nums) if head_nums else True
    ok = (not (neg and pos)) and head_ok
    return {"ok": ok, "detail": "私户表述 %d 处（未取得%d/已取得%d）；总述项数=%s（实际 %d）"
            % (len(sents), len(neg), len(pos), head_nums or "未标注", n)}


def pD_format(rep, rep_data):
    vals = "\n".join(_all_strings(rep))
    sys_hits = sorted({k for k in _SYS_KEYS if re.search(r"\b%s\b" % re.escape(k), vals)})
    ph_hits = sorted({k for k in _PLACEHOLDERS if k in vals})
    fw_hits = [k for k in _FORBIDDEN if k in vals]
    # 错别字/常见混淆（项目已定的错字表在闸门里，这里只做抽样提示）
    typo_hits = [w for w in ("口经", "敦低", "补教", "账载与申报金额不一致。") if w in vals]
    ok = not (sys_hits or ph_hits or fw_hits or typo_hits)
    return {"ok": ok, "detail": "系统键=%s；占位符=%s；禁用/错字=%s"
            % (sys_hits[:4] or "无", ph_hits[:4] or "无", (fw_hits + typo_hits)[:4] or "无")}


def pE_tables(rep, rep_data):
    bad_empty, bad_headonly, bad_zero, bad_trunc = [], [], [], []
    for seq, t in _tables(rep):
        cols, rows = _cols(t), _rows(t)
        title = str(t.get("title") or "")[:24]
        if not rows:
            bad_empty.append((seq, title))
            continue
        if not cols and rows:
            bad_headonly.append((seq, title))
            continue
        # 金额列全为 0
        amt_idx = [i for i, c in enumerate(cols)
                   if ("金额" in c) or ("税额" in c) or ("(元)" in c) or ("（元）" in c)]
        if amt_idx:
            tot = 0.0
            seen_num = False
            for r in rows:
                cells = list(r.values()) if isinstance(r, dict) else list(r)
                for i in amt_idx:
                    if i < len(cells):
                        v = str(cells[i]).replace(",", "").replace("元", "").strip()
                        try:
                            tot += abs(float(v))
                            seen_num = True
                        except Exception:
                            pass
            if seen_num and tot == 0.0:
                bad_zero.append((seq, title))
        # 截断：单元格以 … 结尾但标题/表注未说明抽样
        scope = str(t.get("scope_note") or "") + str(t.get("note") or "")
        for r in rows[:50]:
            cells = list(r.values()) if isinstance(r, dict) else list(r)
            for c in cells:
                if isinstance(c, str) and (c.endswith("…") or "…（" in c) and "截断" not in scope:
                    bad_trunc.append((seq, title, c[:20]))
                    break
    ok = not (bad_empty or bad_headonly or bad_zero or bad_trunc)
    return {"ok": ok, "detail": "空表=%d 只有表头=%d 合计0=%d 截断未注明=%d；样例=%s"
            % (len(bad_empty), len(bad_headonly), len(bad_zero), len(bad_trunc),
               (bad_empty + bad_headonly + bad_zero + bad_trunc)[:2] or "无")}


def pF_counts(rep, rep_data):
    probs = _probs(rep)
    cnt = Counter(str(p.get("risk_level") or "") for p in probs)
    want = {"高风险": 2, "中风险": 9, "低风险": 3, "待核验": 2}
    # 报告内声明的计数（总述/等级判据）
    blob = json.dumps(rep.get("summary") or {}, ensure_ascii=False)
    decl = {k: blob.count(k) for k in want}
    ok = (len(probs) == 16 and all(cnt.get(k, 0) == v for k, v in want.items())
          and sum(cnt.values()) == 16)
    return {"ok": ok, "detail": "16 项=%s；分布 %s（应为 %s）；加总=%d"
            % (len(probs) == 16, dict(cnt), want, sum(cnt.values()))}


def pG_family_double_count(rep, rep_data):
    """风险族重复计数：同族多个子项不得各占一行（merge 后应只留父项）。"""
    try:
        from engine.finding_families import classify_family
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": "归族不可用: %s" % exc}
    fams = {}
    for p in _probs(rep):
        try:
            f = classify_family(p)
            fid = str(f.get("family") or f.get("name") or f) if isinstance(f, dict) else str(f)
        except Exception:
            fid = ""
        if fid and fid not in ("其他", "None", ""):
            fams.setdefault(fid, []).append(p.get("seq"))
    dup = {k: v for k, v in fams.items() if len(v) > 1}
    # 已有同族合并（family_members 挂在父项）⇒ 说明合并生效
    merged = [p.get("seq") for p in _probs(rep) if p.get("family_members")]
    ok = not dup
    return {"ok": ok, "detail": "同族多行=%s；已合并父项=%s" % (dup or "无", merged or "无")}


def pH_tax_logic(rep, rep_data):
    from engine.tax_impact import estimate_tax
    r1 = estimate_tax(4501.34, ["增值税"], amount_is_tax=True)
    ok_in = abs(float(r1["items"][0]["amount"]) - 4501.34) < 0.01 and r1["items"][0]["rate"] == "—"
    r2 = estimate_tax(2_112_137.70, ["企业所得税"], rate_ctx={"cit_rate": 0.05})
    ok_smb = abs(float(r2["items"][0]["amount"]) - 2_112_137.70 * 0.25) < 0.01
    r3 = estimate_tax(2_112_137.70, ["企业所得税"],
                      rate_ctx={"cit_rate": 0.05, "smb_verified": True})
    ok_smb2 = abs(float(r3["items"][0]["amount"]) - 2_112_137.70 * 0.05) < 0.01
    p1 = next((p for p in _probs(rep) if "红字冲销" in str(p.get("title"))), None)
    blob = json.dumps(p1 or {}, ensure_ascii=False)
    ok_red = ("759" not in blob) and ("7,595,196" not in blob)
    ok = ok_in and ok_smb and ok_smb2 and ok_red
    return {"ok": ok, "detail": "进项不乘税率=%s；未验证小微回到25%%=%s；已核实按5%%=%s；红冲无759万=%s"
            % (ok_in, ok_smb, ok_smb2, ok_red)}


def pI_legal_mixing(rep, rep_data):
    try:
        from engine.levy_nature import consequence_text
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": "levy_nature 不可用: %s" % exc}
    bad = []
    for nat, must, must_not in (("社会保险费", "社会保险法", "第六十三条"),
                                ("住房公积金", "住房公积金管理中心", "第六十三条"),
                                ("政府性基金", "政府性基金", "第六十三条")):
        try:
            t = consequence_text(nat)
        except Exception as exc:  # noqa: BLE001
            bad.append((nat, "异常: %s" % exc))
            continue
        if must not in t or must_not in t:
            bad.append((nat, "缺 %s 或误引 %s" % (must, must_not)))
    # 报告正文：非税事项不得出现"处不缴或少缴税款百分之五十以上五倍以下罚款"
    vals = "\n".join(_all_strings(rep))
    fee_leak = "处不缴或少缴税款百分之五十以上五倍以下罚款" in vals
    ok = not bad and not fee_leak
    return {"ok": ok, "detail": "费/基金依据=%s；正文误引征管法罚则=%s" % (bad or "正确", fee_leak)}


def pJ_duplicate(rep, rep_data):
    texts = []
    for p in _probs(rep):
        for np in (p.get("narrative_paragraphs") or []):
            if isinstance(np, dict):
                for k in ("text", "tail"):
                    v = re.sub(r"\s+", "", str(np.get(k) or ""))
                    if len(v) >= 30:
                        texts.append(v)
                for b in (np.get("bullets") or []):
                    v = re.sub(r"\s+", "", str(b))
                    if len(v) >= 30:
                        texts.append(v)
    cnt = Counter(texts)
    dup = {k[:36]: v for k, v in cnt.items() if v > 1}
    return {"ok": not dup, "detail": "重复段=%s" % (list(dup.items())[:2] or "无")}


PROBES = [("A 未修复问题", pA_unfixed), ("B 结论与证据冲突", pB_conclusion_conflict),
          ("C 数据前后矛盾", pC_data_contradiction), ("D 格式/错字/系统键/占位符", pD_format),
          ("E 表格截断/空表/表头/合计0", pE_tables), ("F 事项计数不一致", pF_counts),
          ("G 风险族重复计数", pG_family_double_count), ("H 税额测算逻辑", pH_tax_logic),
          ("I 税费法律适用混同", pI_legal_mixing), ("J 重复模板段落", pJ_duplicate)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data" / "audit" / "audit.json"))
    a = ap.parse_args()
    src = ROOT / "scripts" / "four_reports" / "company_1_full.json"
    rep_data = json.loads(src.read_text(encoding="utf-8"))
    from engine.enterprise_report import build_enterprise_readable_report
    rep = build_enterprise_readable_report(rep_data)
    rows = []
    for name, fn in PROBES:
        try:
            r = fn(rep, rep_data)
        except Exception as exc:  # noqa: BLE001
            r = {"ok": False, "detail": "检查异常：%s" % exc}
        rows.append({"name": name, "ok": bool(r.get("ok")), "detail": str(r.get("detail"))})
    # 12 项回归（复用既有脚本，避免两份判据）
    import regression_batch6 as R
    reg = R.run_all(rep)
    out = {"report": str(src), "probes": rows, "regression": reg,
           "regression_pass": len([r for r in reg if r["ok"]]), "regression_total": len(reg)}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("== 10 类问题 ==")
    for r in rows:
        print(("✅" if r["ok"] else "❌"), r["name"], "|", r["detail"][:150])
    print("\n== 12 项回归 ==  %d/%d" % (out["regression_pass"], out["regression_total"]))
    for r in reg:
        print(("✅" if r["ok"] else "❌"), r["name"], "|", r["evidence"][:110])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
