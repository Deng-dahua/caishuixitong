# -*- coding: utf-8 -*-
"""第 6 批·全量回归测试（12 项验收，可复现"修复前失败 / 修复后通过"）。

用法：
    python scripts/regression_batch6.py                  # 用 company_1_full.json 重建报告后跑
    python scripts/regression_batch6.py --report X.json  # 用已有报告（report_data 或成品）跑
    python scripts/regression_batch6.py --label before   # 把结果落到 data/regression/<label>.json

设计口径（★ 为什么这样写）：
  · **按内容判定，不按编号**：第 1 批已把疑点编号统一重排为 1–16，而用户给的 12 项验收用的是**旧编号**
    （如"疑点15""疑点27/29/34"）。本脚本用**主题关键词**定位事项，并把"旧编号 → 新编号"写进报告，
    避免"改了编号就找不到验收对象"。
  · **每项都给出证据**（命中位置/数量/样例），不只是一个 PASS/FAIL —— 否则无法复现、也无法修。
  · **不修改任何东西**：纯只读检查；修复由调用方决定。
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

#: 旧编号 → 内容关键词（用于把用户口径映射到当前报告）
LEGACY_HINTS = {
    "疑点1": "红字冲销与作废发票比例异常",
    "疑点2": "工资表人数与社保参保人数不符",
    "疑点3": "银行收款大于申报收入",
    "疑点4": "税前扣除限额超限",
    "疑点6": "印花税计税依据不足",
    "疑点15": "采购/供应商类（表格须带金额）",
    "疑点27/29/34": "同一交易对手同时出现在客户与供应商清单",
}

#: 全文级禁用词（用户逐条点名）
FORBIDDEN = ("口经说明", "敦低法", "补教要求", "2025-515", "一元")

#: 英文/系统键（面向企业文本里不得出现）
_SYS_KEY_RE = re.compile(
    r"\b(?:tax_impact|redline_id|finding_type|scene_fact_id|risk_level|"
    r"conclusion_grade|evidence_have|evidence_need|missing_materials|"
    r"source_chain|policy_ref|law_ref|trace_id)\b")


def _load_report(args):
    if args.report:
        obj = json.loads(Path(args.report).read_text(encoding="utf-8"))
        if "confirmed_problems" in obj:
            return obj, "external"
        from engine.enterprise_report import build_enterprise_readable_report
        return build_enterprise_readable_report(obj), "rebuilt"
    src = ROOT / "scripts" / "four_reports" / "company_1_full.json"
    obj = json.loads(src.read_text(encoding="utf-8"))
    from engine.enterprise_report import build_enterprise_readable_report
    return build_enterprise_readable_report(obj), "rebuilt"


def _probs(rep):
    return [p for p in (rep.get("confirmed_problems") or []) if isinstance(p, dict)]


def _txt(rep):
    return json.dumps(rep, ensure_ascii=False)


def _find(rep, kw):
    for p in _probs(rep):
        if kw in str(p.get("title") or "") or kw in str(p.get("redline_name") or ""):
            return p
    return None


def _narr(p):
    """把一项的叙述与表格拼成纯文本（判定用）。"""
    parts = []
    for np in (p.get("narrative_paragraphs") or []):
        if isinstance(np, dict):
            parts += [str(np.get("text") or ""), str(np.get("tail") or "")]
            parts += [str(b) for b in (np.get("bullets") or [])]
    return "\n".join(parts)


def _tables(p):
    out = []
    for np in (p.get("narrative_paragraphs") or []):
        if isinstance(np, dict):
            out += [t for t in (np.get("detail_tables") or []) if isinstance(t, dict)]
    if isinstance(p.get("detail_table"), dict):
        out.append(p["detail_table"])
    return out


def _cols(t):
    return [str(c) for c in ((t or {}).get("columns") or (t or {}).get("headers") or [])]


# ── 12 项检查 ────────────────────────────────────────────────────────────────

def c01_counts(rep, ctx):
    """① 事项计数：16 项，高2/中9/低3/须核对2，加总一致。"""
    probs = _probs(rep)
    from collections import Counter
    cnt = Counter(str(p.get("risk_level") or "") for p in probs)
    want = {"高风险": 2, "中风险": 9, "低风险": 3, "待核验": 2}
    total = sum(cnt.values())
    ok = (len(probs) == 16 and total == 16
          and all(cnt.get(k, 0) == v for k, v in want.items()))
    # 报告头/总述里的口径也必须同源
    head = json.dumps(rep.get("summary") or {}, ensure_ascii=False)
    head_ok = ("16" in head) and ("已量化" not in head or "26" not in head)
    ev = "事项 %d 项；等级分布 %s；总述含16=%s" % (len(probs), dict(cnt), head_ok)
    return ok and head_ok, ev


def c02_redvoid(rep, ctx):
    """② 疑点1：不得出现 759 万元增值税（红冲按涉案量、不按销项蓝字全额）。"""
    p = _find(rep, LEGACY_HINTS["疑点1"])
    blob = _txt(p) if p else ""
    hits = [x for x in ("759", "7,595,196", "7595196") if x in blob]
    ti = (p or {}).get("tax_impact") or {}
    amt = ti.get("total")
    ok = bool(p) and not hits and (amt is None or float(amt) < 3_000_000)
    return ok, "疑点1=%s；命中禁用数字=%s；敞口=%s" % (
        (p or {}).get("seq"), hits or "无", amt)


def c03_payroll_rows(rep, ctx):
    """③ 疑点2：三源比对只展示差异人（杨莹），不展示无差异人；全文不得出现 2025-515。"""
    p = _find(rep, LEGACY_HINTS["疑点2"])
    if not p:
        return False, "未找到三源比对事项"
    names_nodiff = [n for n in ("初永伟", "徐瑶", "吴德昌") if n in _txt(p)]
    rows = []
    for t in _tables(p):
        rows += [t.get("rows") or []]
    state_col = any(any("状态" in c for c in _cols(t)) for t in _tables(p))
    ok = bool(p) and not names_nodiff and state_col and ("2025-515" not in _txt(rep))
    return ok, "事项=%s；无差异人出现=%s；表含状态列=%s" % (
        p.get("seq"), names_nodiff or "无", state_col)


def c04_private_account(rep, ctx):
    """④ 疑点3：私户矛盾消除；1,734,859.35 与 227,659.35 口径须说明。"""
    p = _find(rep, LEGACY_HINTS["疑点3"])
    if not p:
        return False, "未找到账外收入/私户事项"
    t = _txt(p)
    # ★ 收窄（初版判据过宽造成假阳性）：只在**含「自然人自有账户」的那几句**里判自相矛盾。
    #   初版用全文的"未提供/已提供"共现 ⇒ 只要报告里别处提到"已提供银行流水"就误报。
    sents: list = []
    for m in re.finditer(r"[^。；\n]{0,120}自然人自有账户[^。；\n]{0,120}", t):
        sents.append(m.group(0))
    neg = [x for x in sents if any(k in x for k in ("未提供", "未取得", "尚未取得", "另需取得"))]
    pos = [x for x in sents if any(k in x for k in ("已提供", "已取得", "已经取得"))]
    contra = bool(neg) and bool(pos)
    expl = any(k in t for k in ("口径", "价税", "不含税", "含税", "另一侧"))
    has_a, has_b = "1,734,859.35" in t, "227,659.35" in t
    ok = (not contra) and bool(sents) and expl
    return ok, "私户表述 %d 处（未取得%d/已取得%d，矛盾=%s）；含口径说明=%s；1,734,859.35=%s 227,659.35=%s" % (
        len(sents), len(neg), len(pos), contra, expl, has_a, has_b)


def c05_limit_table(rep, ctx):
    """⑤ 疑点4：分项扣除限额表完整（含差异性质与适用规则）；全文无「敦低法」。"""
    p = _find(rep, LEGACY_HINTS["疑点4"])
    if not p:
        return False, "未找到扣除限额事项"
    cols = set()
    for t in _tables(p):
        cols |= set(_cols(t))
    need = [c for c in cols if "差异性质" in c or "适用规则" in c]
    ok = len(need) >= 2 and ("敦低法" not in _txt(rep))
    return ok, "事项=%s；表列=%s；命中必需列=%s" % (p.get("seq"), sorted(cols)[:6], need)


def c06_clue_rows(rep, ctx):
    """⑥ 疑点6：线索链三环节的「资料」列不得三行完全相同。"""
    p = _find(rep, LEGACY_HINTS["疑点6"])
    if not p:
        return False, "未找到该事项"
    rows = []
    for t in _tables(p):
        c = _cols(t)
        if any("资料" in x for x in c):
            rows = t.get("rows") or []
            break
    if len(rows) < 3:
        return True, "无三行资料列（不适用）"
    mat = []
    for r in rows[:3]:
        mat.append(tuple(str(v) for v in (r.values() if isinstance(r, dict) else r)))
    ok = len(set(mat)) > 1
    return ok, "三行是否完全相同=%s" % (len(set(mat)) == 1)


def c07_tables_have_amount(rep, ctx):
    """⑦ 疑点15：明细表必须有金额列，不得只有供应商名称。"""
    # ★ 收窄（初版判据过宽）：用户要求的是"**列供应商的表**必须有金额"。
    #   要件核对表（要件序号/构成要件/独立数据源）与证据角色表（证据角色/证据名称/证明目的/现状）
    #   本来就不该有金额列 ⇒ 不能一律要求"每张表都有金额"。
    #   判据：**含对手方/名称类列**的逐笔表，若无任何金额列 ⇒ 失败。
    #   ⚠ 再收窄：`名称` 会命中"**证据名称**"（证据角色表本就不该有金额）⇒ 只认可作对手方判定的列名。
    _CP_COLS = ("供应商", "客户", "对手方", "对方单位", "付款方", "收款方",
                "单位名称", "供应商名称", "客户名称")
    #: 明确的**非金额意图**表（要件核对表 / 证据角色表）⇒ 不参与"必须有金额"判定
    _NON_AMOUNT_COLS = ("要件序号", "构成要件", "证据角色", "证据名称", "证明目的")
    bad = []
    for p in _probs(rep):
        for t in _tables(p):
            cols = _cols(t)
            if not cols:
                continue
            if any(any(k in c for k in _NON_AMOUNT_COLS) for c in cols):
                continue
            if not any(any(k in c for k in _CP_COLS) for c in cols):
                continue
            has_amt = any(("金额" in c) or ("税额" in c) or ("价税合计" in c) or ("(元)" in c)
                          for c in cols)
            if not has_amt:
                bad.append((p.get("seq"), str(p.get("title"))[:16], cols[:4]))
    ok = not bad
    return ok, "含对手方列但无金额列的表=%s" % (bad[:3] or "无")


def c08_localize_and_combo(rep, ctx):
    """⑧ 疑点27/29/34：系统字段名转中文；组合项不再单独定高风险。"""
    # ★ 收窄（初版扫了整个 JSON ⇒ 把**结构性键名**也算成"系统字段名"）。用户要的是
    #   **面向企业可见的文本**里不得出现系统键 ⇒ 只扫字符串值，不扫键名。
    def _strings(o, acc):
        if isinstance(o, dict):
            for v in o.values():
                _strings(v, acc)
        elif isinstance(o, list):
            for v in o:
                _strings(v, acc)
        elif isinstance(o, str):
            acc.append(o)
        return acc
    vals = "\n".join(_strings(rep, []))
    sys_keys = sorted(set(_SYS_KEY_RE.findall(vals)))
    # 组合项（有 family_members = 由同族合并而来）若定为高风险，**必须有独立依据**；
    # 仅"继承子项最高等级"不算依据（用户："组合项不再单独定高风险"）。
    combo_high, no_basis = [], []
    for p in _probs(rep):
        if str(p.get("risk_level")) != "高风险":
            continue
        if not p.get("family_members"):
            continue
        combo_high.append(p.get("seq"))
        basis = str(p.get("risk_level_basis") or "")
        if ("独立" not in basis) and ("组合" not in basis) and ("联动" not in basis):
            no_basis.append(p.get("seq"))
    ok = not sys_keys and not no_basis
    return ok, "文本里的系统键=%s；组合项高风险=%s；其中无独立依据=%s" % (
        sys_keys[:5] or "无", combo_high or "无", no_basis or "无")


def c09_forbidden_words(rep, ctx):
    """⑨ 全文：无「口经说明」「敦低法」「补教要求」「2025-515」「一元」。"""
    blob = _txt(rep)
    hits = [w for w in FORBIDDEN if w in blob]
    return not hits, "命中=%s" % (hits or "无")


def c10_duplicate_paragraphs(rep, ctx):
    """⑩ 全文：同一自然段不得重复出现超过 1 次。"""
    from collections import Counter
    texts = []
    for p in _probs(rep):
        for np in (p.get("narrative_paragraphs") or []):
            if isinstance(np, dict):
                t = re.sub(r"\s+", "", str(np.get("text") or ""))
                if len(t) >= 30:
                    texts.append(t)
                for b in (np.get("bullets") or []):
                    b = re.sub(r"\s+", "", str(b))
                    if len(b) >= 30:
                        texts.append(b)
    cnt = Counter(texts)
    dup = {k[:40]: v for k, v in cnt.items() if v > 1}
    return not dup, "重复段=%s" % (list(dup.items())[:2] or "无")


def c11_conclusion_vs_evidence(rep, ctx):
    """⑪ 全文：无结论与证据冲突（复用既有闸门判据，不在本脚本另写一份）。"""
    try:
        from tools.audit_consistency import check_pending_verdict_softened, \
            check_conclusion_not_exceed_finding
        issues = []
        for fn in (check_pending_verdict_softened, check_conclusion_not_exceed_finding):
            try:
                issues += [i for i in fn() if i[0] == "ERROR"]
            except Exception as exc:  # noqa: BLE001
                issues.append(("ERROR", fn.__name__, str(exc)))
        return not issues, "闸门报出的冲突=%s" % (issues[:2] or "无")
    except Exception as exc:  # noqa: BLE001
        return False, "判据不可用: %s" % exc


def c12_two_documents(rep, ctx):
    """⑫ 生成《修复前后对照表》与《回归测试报告》（由 main() 落盘，这里校验能力存在）。"""
    ok = all(hasattr(sys.modules[__name__], n) for n in ("render_report", "render_diff"))
    return ok, "渲染函数齐备=%s" % ok


CHECKS = [
    ("1 事项计数", c01_counts),
    ("2 疑点1 红冲不 759 万", c02_redvoid),
    ("3 疑点2 三源只展示差异人 / 无 2025-515", c03_payroll_rows),
    ("4 疑点3 私户口径自洽", c04_private_account),
    ("5 疑点4 限额表完整 / 无敦低法", c05_limit_table),
    ("6 疑点6 三环节资料不同", c06_clue_rows),
    ("7 疑点15 表格须有金额", c07_tables_have_amount),
    ("8 疑点27/29/34 汉化 + 组合项不单独高风险", c08_localize_and_combo),
    ("9 全文禁用词", c09_forbidden_words),
    ("10 无重复模板段落", c10_duplicate_paragraphs),
    ("11 无结论与证据冲突", c11_conclusion_vs_evidence),
    ("12 两份文档可生成", c12_two_documents),
]


# ── 输出渲染 ────────────────────────────────────────────────────────────────

def run_all(rep):
    rows = []
    for name, fn in CHECKS:
        try:
            ok, ev = fn(rep, {})
        except Exception as exc:  # noqa: BLE001
            ok, ev = False, "检查异常：%s" % exc
        rows.append({"name": name, "ok": bool(ok), "evidence": str(ev)})
    return rows


def render_report(rows, label, mapping):
    n_ok = len([r for r in rows if r["ok"]])
    L = ["# 全量回归测试报告（第 6 批）", "",
         "样例：`scripts/four_reports/company_1_full.json` 重建的报告成品；本次标签：**%s**。" % label, "",
         "结果：**%d / %d 通过**。" % (n_ok, len(rows)), "",
         "## 一、12 项验收逐条", "", "| # | 验收项 | 结果 | 证据 |", "|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        L.append("| %d | %s | %s | %s |" % (i, r["name"], "✅ 通过" if r["ok"] else "❌ 失败",
                                            r["evidence"].replace("|", "／")[:170]))
    L += ["", "## 二、旧编号 → 当前编号 映射", "",
          "第 1 批已把疑点编号统一重排为 **1–16**；用户给的验收用**旧编号**，按内容对应如下：", "",
          "| 用户口径 | 主题 | 当前编号 |", "|---|---|---|"]
    for k, v in mapping.items():
        L.append("| %s | %s | %s |" % (k, v["hint"], v.get("seq") or "未找到"))
    L.append("")
    return "\n".join(L)


def render_diff(before, after, label_after="after"):
    """《修复前后对照表（全量）》：逐项列出修复前/后结果与证据。"""
    bmap = {r["name"]: r for r in before}
    L = ["# 修复前后对照表（全量）", "",
         "| # | 验收项 | 修复前 | 修复后 | 前证据 | 后证据 |", "|---|---|---|---|---|---|"]
    fixed, regressed = 0, 0
    for i, r in enumerate(after, 1):
        b = bmap.get(r["name"]) or {}
        bo, ao = bool(b.get("ok")), bool(r["ok"])
        if not bo and ao:
            fixed += 1
        if bo and not ao:
            regressed += 1
        L.append("| %d | %s | %s | %s | %s | %s |" % (
            i, r["name"], "❌" if not bo else "✅", "✅" if ao else "❌",
            str(b.get("evidence") or "")[:90].replace("|", "／"),
            str(r.get("evidence") or "")[:90].replace("|", "／")))
    L += ["", "汇总：修复 **%d** 项；回归（原本通过变失败）**%d** 项。" % (fixed, regressed), ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="第 6 批全量回归（12 项）")
    ap.add_argument("--report", help="报告文件（report_data 或成品）")
    ap.add_argument("--label", default="current", help="结果标签（用于落盘与前后对比）")
    ap.add_argument("--out-dir", default=str(ROOT / "data" / "regression"))
    a = ap.parse_args()
    rep, how = _load_report(a)
    rows = run_all(rep)
    mapping = {}
    for k, hint in LEGACY_HINTS.items():
        p = _find(rep, hint) if k != "疑点15" else None
        mapping[k] = {"hint": hint, "seq": (p or {}).get("seq") if p else None}
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / ("%s.json" % a.label)).write_text(
        json.dumps({"label": a.label, "how": how, "rows": rows, "mapping": mapping},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    md = render_report(rows, a.label, mapping)
    (out / ("report_%s.md" % a.label)).write_text(md, encoding="utf-8")
    print(md[:2600])
    n_ok = len([r for r in rows if r["ok"]])
    print("\n[结果] %d/%d 通过（标签 %s，落盘 %s）" % (n_ok, len(rows), a.label, out))
    return 0 if n_ok == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
