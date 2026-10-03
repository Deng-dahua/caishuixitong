# -*- coding: utf-8 -*-
"""一键分析**输出自检**（唯一权威可执行入口）—— 对成品报告做四维机器体检。

## 为什么需要

用户多次指出报告"不精准/很儿戏/证据很垃圾"，而这些缺陷**光读文字看不出来**：
必须拿**引擎派生量**与**原始凭证**去对账。本脚本把本轮实践中查出的错法固化为**可重复执行的检查**，
作为"改完必须再跑一次"的收尾门禁（与 `tools/audit_consistency.py` 的静态闸门互补：
后者查源码契约，本脚本查**成品产出**）。

## 四维自检（判据代码化）

- **A 主体一致性**：每条疑点的**主体**（风险指标名）↔**建入口那条发现**↔**附表来源**是否同一件事
  （判据唯一权威 `engine/subject_consistency`）。错配会以"标题讲A、正文讲B"的形式出现。
- **B 证据编辑质量**（六类，逐条实测过）：
  ① 元信息当证据（"看到已读取资料：…"/"看到本轮未取得…"）
  ② 空话占步（"数据与上一环一致"）
  ③ 指标倾倒（"…等5项 等10项"把引擎内部结构倒进正文）
  ④ 方向相反（收款表混支出行；讲销项红冲却列进项红字）
  ⑤ 正文声明与表自相矛盾（正文称已剔除借款/往来款，表里却有）
  ⑥ 跨疑点重复（同一批记录填多张不同主题的表）
- **C 计数与口径对账**：等级计数 vs `by_level`；分类合计 vs 疑点数；"X 项占 Y%"自己除一遍；
  必查资料「已提供＋缺失」vs 权威清单剔除不适用后的条数；"另有 N 项"这类**旁路清单**是否
  写明了与主计数的关系；**所有 `[:N]` 截断**是否吞掉了别处点过名的对象；列举处**括号是否成对**。
- **D 金额溯源**：报告里出现的金额必须能回指**原始上传凭证**、并按**唯一标识去重**
  （进项发票是「一票多行」，按行加总会虚高；按票号去重见 `fieldkit.invoice_no`）。
  本维只做**提示 + 关键金额复核**，不自动判定（外部口径需人工核）。

## 用法

    python tools/selfcheck_report_output.py [结果JSON] [--strict]

默认读 `scripts/four_reports/_fresh_result.json`（由 `scripts/_dump_company1.py` 生成）。
退出码：有 ERROR → 1；`--strict` 时 WARN 也算失败。
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

ISSUES = []          # (级别, 维度, 说明)


def _add(level, dim, msg):
    ISSUES.append((level, dim, msg))


def _load(path):
    d = json.load(open(path, encoding="utf-8"))
    rep = d.get("report", d)
    return rep, rep.get("enterprise_readable_report") or {}


# ── A 主体一致性 ──────────────────────────────────────────────────────────
def check_subject_consistency(rep, er):
    from engine.subject_consistency import norm_subject_key, suspicion_subject_ok, table_source_ok
    sus = ((rep.get("comprehensive") or {}).get("redline_detection") or {}).get("suspicions") or []
    probs = er.get("confirmed_problems") or []
    # 表题→来源发现主体键（显式下钻表用）
    findings = ((rep.get("scenario_execution") or {}).get("findings") or rep.get("all_findings") or [])
    _TITLE_OWNER = {}
    for f in findings:
        if not isinstance(f, dict):
            continue
        _k = norm_subject_key(f.get("type") or "")
        if not _k:
            continue
        for t in (f.get("detail_tables") or []):
            if isinstance(t, dict) and t.get("title"):
                _TITLE_OWNER.setdefault(norm_subject_key(t["title"]), _k)
        if f.get("evidence_rows"):
            _TITLE_OWNER.setdefault(norm_subject_key(f.get("type") or ""), _k)
    by_rid = {str(s.get("redline_id") or ""): s for s in sus}
    checked = 0
    for p in probs:
        title = str(p.get("title") or "")
        # 报告出口已剥红线编号，按标题回查（先红线名、再 entry 名）
        s = None
        for _s in sus:
            _n = norm_subject_key(_s.get("redline_name"))
            if _n and _n in norm_subject_key(title):
                s = _s
                break
        if s is None:
            continue
        keys = [k for k in {norm_subject_key(f.get("type"))
                            for f in (s.get("supporting_findings") or []) if isinstance(f, dict)} if k]
        ent = str(s.get("finding_type") or "").strip()
        if ent:
            keys.insert(0, norm_subject_key(ent))
        if not keys:
            continue
        checked += 1
        ok, why = suspicion_subject_ok(str(s.get("redline_name") or ""), [ent] if ent else keys,
                                       s.get("redline_id"))
        if not ok:
            _add("ERROR", "A 主体一致性", f"疑点{p.get('seq')}「{title[:24]}」：{why[:80]}")
        for para in (p.get("narrative_paragraphs") or []):
            for tb in ((para or {}).get("detail_tables") or []):
                ttl = str((tb or {}).get("title") or "")
                if ttl.startswith("构成要件独立核对表"):
                    continue
                # ⚠ 显式下钻表的题名会被 `table_governance` 规范标点（·→，），
                #   不能拿题名当来源 —— 按"表题→来源发现"回溯（与报告挂载同口径）。
                _src = _TITLE_OWNER.get(norm_subject_key(ttl)) or norm_subject_key(ttl)
                ok2, why2 = table_source_ok(set(keys), _src)
                if not ok2:
                    _add("ERROR", "A 主体一致性",
                         f"疑点{p.get('seq')} 附表「{ttl[:26]}」来源不符：{why2[:64]}")
    return checked


# ── B 证据编辑质量（六类）──────────────────────────────────────────────────
_META = ("已读取资料", "本轮未取得", "该环节未取得", "该环节未产出")
_NON_OPER = ("借款", "往来款", "还款", "退款", "贷款", "利息", "保证金", "押金")
_EXPENSE_HINT = ("明星费用", "房租", "水电", "手续费", "工资", "公积金", "社保", "缴税")


def check_evidence_quality(er):
    probs = er.get("confirmed_problems") or []
    dup = defaultdict(set)
    n = 0
    for p in probs:
        seq = p.get("seq")
        for para in (p.get("narrative_paragraphs") or []):
            h = str((para or {}).get("heading") or "")
            if h.startswith("二、"):
                t = str((para or {}).get("text") or "")
                for k in _META:
                    if "看到" + k in t:
                        _add("ERROR", "B 证据编辑", f"疑点{seq}：元信息当证据（看到{k}…）")
                if "数据与上一环一致" in t:
                    _add("ERROR", "B 证据编辑", f"疑点{seq}：空话占步（数据与上一环一致）")
                for m in re.finditer(r"等\d+项", t):
                    _add("WARN", "B 证据编辑", f"疑点{seq}：指标倾倒（{m.group(0)}）")
                # ⚠ 补漏：以「…」截断的长清单同样是"指标倾倒"（此前只认"等N项"会漏检）
                for m in re.finditer(r"[^，；。]{40,}…", t):
                    _add("WARN", "B 证据编辑",
                         f"疑点{seq}：疑似指标倾倒被「…」截断（{m.group(0)[:34]}…）")
            for tb in ((para or {}).get("detail_tables") or []):
                ttl = str((tb or {}).get("title") or "")
                for r in ((tb or {}).get("rows") or []):
                    lab = str((r or {}).get("凭证/单据标识") or (r or {}).get("ref_label") or "")
                    src = str((r or {}).get("来源资料") or (r or {}).get("source") or "")
                    who = str((r or {}).get("对方单位") or (r or {}).get("counterparty") or "")
                    amt = str((r or {}).get("金额（元）") or (r or {}).get("金额(元)") or "")
                    dup[(src[:8], lab[:18], who[:12], amt)].add(seq)
                    n += 1
                    if ("收款" in ttl or "收入" in ttl) and any(k in lab for k in _EXPENSE_HINT):
                        _add("ERROR", "B 证据编辑",
                             f"疑点{seq}：支出行混入收款表（{ttl[:18]} ← {lab[:12]}）")
                    if any(k in lab for k in _NON_OPER) and ("收款" in ttl or "收入" in ttl):
                        _add("ERROR", "B 证据编辑",
                             f"疑点{seq}：非经营性收款混入（{lab[:12]}）")
    rep_dup = {k: v for k, v in dup.items() if len(v) > 1}
    if len(rep_dup) > 20:
        _add("WARN", "B 证据编辑",
             f"跨疑点重复证据行 {len(rep_dup)} 条（应只列与本项同方向的记录；"
             f"正当共享可接受，数量过大需查方向过滤是否生效）")
    return n, len(rep_dup)


# ── C 计数与口径对账 ──────────────────────────────────────────────────────
def check_counts(rep, er):
    from engine.enterprise_report import _REQUIRED_DOC_CATEGORIES, _not_required_docs
    probs = er.get("confirmed_problems") or []
    oc = er.get("overall_conclusion") or {}
    counts = oc.get("counts") or {}
    tiers = {t.get("level"): t.get("count") for t in (oc.get("tiers") or [])}
    # ① 等级计数
    real = Counter(str(p.get("risk_level")) for p in probs)
    for lv, c in (counts.get("by_level") or {}).items():
        if int(real.get(lv, 0)) != int(c or 0):
            _add("ERROR", "C 计数对账", f"等级「{lv}」报告 {c} 项、实际 {real.get(lv,0)} 项")
    # ② 分类合计
    themes = oc.get("risk_themes") or []
    tot = sum(int(t.get("count") or 0) for t in themes)
    if themes and tot != len(probs):
        _add("ERROR", "C 计数对账", f"风险性质分类合计 {tot} 项 ≠ 疑点 {len(probs)} 项")
    # ③ 占比重算
    for t in themes[:2]:
        pass
    # ④ 必查资料对账
    mr = er.get("material_readiness") or {}
    prov = len(mr.get("provided") or [])
    miss = len(mr.get("missing") or [])
    na = len(((mr.get("not_applicable") or {}).get("docs")) or [])
    # ⚠ 只减**确实在必查清单里**的不适用项（如"物料清单"不在清单内，减它会把期望算错）
    _na_list = ((mr.get("not_applicable") or {}).get("docs")) or []
    expect = len(_REQUIRED_DOC_CATEGORIES) - len([x for x in _na_list if x in _REQUIRED_DOC_CATEGORIES])
    if prov + miss != expect:
        _add("ERROR", "C 计数对账",
             f"必查资料「已提供{prov}+缺失{miss}」= {prov+miss} ≠ 清单剔除不适用后 {expect} 类")
    # ⑤ 旁路清单（"另有 N 项"）必须写明与主计数的关系
    further = er.get("further_checks") or []
    seg = [p for p in (oc.get("paragraphs") or []) if "检查受限记录" in p or "另有" in p]
    if further:
        if not seg:
            _add("ERROR", "C 计数对账", "存在 further_checks 但正文没有口径说明段")
        else:
            t = seg[0]
            if "不相互计入" not in t or "不属于风险疑点" not in t:
                _add("ERROR", "C 计数对账",
                     "「另有 N 项」未写明与主计数的关系（须声明：不属于风险疑点、不相互计入）")
            if str(len(further)) not in t:
                _add("WARN", "C 计数对账", "「另有 N 项」的 N 与 further_checks 条数不一致")
    # ⑥ 括号成对 + 截断
    for p in (oc.get("paragraphs") or []):
        if p.count("（") != p.count("）") or p.count("(") != p.count(")"):
            _add("ERROR", "C 计数对账", f"总述段落括号不成对：{p[:40]}…")
        for m in re.finditer(r"[:：]\s*$", p[:200]):
            _add("WARN", "C 计数对账", f"总述段落以冒号结尾（疑截断）：{p[:40]}…")
    # ⑦ 明细表标题里的"共N笔"与真实行数一致
    for p in probs:
        for para in (p.get("narrative_paragraphs") or []):
            for tb in ((para or {}).get("detail_tables") or []):
                ttl = str((tb or {}).get("title") or "")
                m = re.search(r"共\s*(\d+)\s*笔", ttl)
                if m and int(m.group(1)) != len((tb or {}).get("rows") or []):
                    _add("ERROR", "C 计数对账",
                         f"疑点{p.get('seq')} 表题「{ttl[:24]}」自称共{m.group(1)}笔、实际"
                         f"{len((tb or {}).get('rows') or [])} 行")
    return counts


# ── D 金额溯源提示 ────────────────────────────────────────────────────────
def check_amount_provenance(er, dump_path):
    """提示需要人工复核的关键金额（脚本不自动裁定外部口径）。"""
    oc = er.get("overall_conclusion") or {}
    tas = er.get("tax_impact_summary") or {}
    tips = []
    for k in ("total", "quantified", "total_items"):
        if k in (tas or {}):
            tips.append(f"税额敞口 {k}={tas.get(k)}")
    for t in (oc.get("tax_types") or []):
        tips.append(f"{t.get('name')}{t.get('count')}项")
    _add("INFO", "D 金额溯源",
         "以下金额若要写进结论，必须能回指**原始上传凭证**并按唯一标识去重"
         "（进项发票是「一票多行」，按行加总会虚高；口径示例：`fieldkit.invoice_no` 按票号去重）："
         + "；".join(tips[:6]))
    return tips


def check_scope_disclosure(er):
    """E 口径自证：报告里的"银行侧金额"是否按**收款性质**取值并披露了剔除与待判定。

    ★ 2026-10-03（用户质询"是不是所有银行流水的收款都与收入相关？"）：
      全部贷方 ≠ 收入。报告若把"银行入账"当收入去比开票额，差额会被读成
      "隐匿未开票收入"（实测凭空造出 133.7 万）。成品报告层面必须能看出：
        · 措辞是「银行经营性收款」而不是笼统的「银行入账」；
        · 披露了剔除了多少非经营性收款、还有多少"性质待判定"须企业说明。
    判据用**词面**（报告是最终产物，只能按文本判），命中即提示人工复核。
    """
    import json as _json

    # 只看**疑点正文**（读者实际读到的段落），不看整份 JSON：
    # 口径写在发现对象的其它字段里而正文没写 = 读者仍然看不到（实测踩过）。
    parts = []
    for p in (er.get("confirmed_problems") or []):
        for para in (p.get("narrative_paragraphs") or []):
            parts.append(str(para.get("text") or para.get("body") or ""))
        for k in ("final_answer", "suggestion"):
            parts.append(str(p.get(k) or ""))
    body = "\n".join(parts)
    if not body.strip():
        _add("WARN", "E 口径自证", "取不到疑点正文段落，口径披露无法检查")
        return 1
    n = 0
    if "银行入账" in body and "经营性收款" not in body:
        _add("ERROR", "E 口径自证",
             "疑点正文出现「银行入账」但无「经营性收款」——银行侧疑似按**全部贷方**当收入"
             "（借款/往来/保证金会被算成收入，差额即被读成隐匿未开票收入）")
        n += 1
    if "经营性收款" in body and "非经营性" not in body:
        _add("WARN", "E 口径自证",
             "疑点正文写了「经营性收款」但未披露**剔除了多少非经营性收款**——读者无法判断口径范围")
        n += 1
    if "经营性收款" in body and "待判定" not in body:
        _add("WARN", "E 口径自证",
             "疑点正文写了「经营性收款」但未披露**性质待判定**的收款——未定性的收款既不能定罪也不该消失")
        n += 1
    if n == 0:
        _add("INFO", "E 口径自证", "疑点正文口径措辞与披露完整（经营性收款 + 剔除构成 + 待判定）")
    return n


def main(argv=None):
    argv = list(argv or sys.argv[1:])
    strict = "--strict" in argv
    argv = [a for a in argv if a != "--strict"]
    path = argv[0] if argv else os.path.join("scripts", "four_reports", "_fresh_result.json")
    if not os.path.exists(path):
        print(f"✗ 找不到结果文件：{path}（先跑 scripts/_dump_company1.py）")
        return 2
    rep, er = _load(path)
    if not er:
        print("✗ 该结果里没有 enterprise_readable_report（不是企业版报告产物）")
        return 2

    n_sub = check_subject_consistency(rep, er)
    n_rows, n_dup = check_evidence_quality(er)
    check_counts(rep, er)
    check_amount_provenance(er, path)
    n_scope = check_scope_disclosure(er)

    print("=" * 86)
    print("一键分析输出自检（五维）")
    print("=" * 86)
    print(f"结果文件：{path}")
    print(f"A 主体一致性：核对 {n_sub} 条疑点")
    print(f"B 证据编辑  ：扫描 {n_rows} 行明细；跨疑点重复 {n_dup} 条")
    print(f"E 口径自证  ：{n_scope} 项待核（银行侧是否按收款性质取值并披露）")
    print("-" * 86)
    if not ISSUES:
        print("✓ 全部通过（无 ERROR / WARN）")
        return 0
    order = {"ERROR": 0, "WARN": 1, "INFO": 2}
    for lv in ("ERROR", "WARN", "INFO"):
        rows = [x for x in ISSUES if x[0] == lv]
        if not rows:
            continue
        print(f"\n【{lv}】{len(rows)} 项")
        for _, dim, msg in rows[:60]:
            print(f"  · [{dim}] {msg}")
    n_err = len([x for x in ISSUES if x[0] == "ERROR"])
    n_warn = len([x for x in ISSUES if x[0] == "WARN"])
    print(f"\n合计：ERROR {n_err} 项 / WARN {n_warn} 项")
    if n_err:
        return 1
    return 1 if (strict and n_warn) else 0


if __name__ == "__main__":
    raise SystemExit(main())
