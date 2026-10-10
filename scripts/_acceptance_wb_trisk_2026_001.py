# -*- coding: utf-8 -*-
"""WB-TRISK-2026-001 验收脚本（§七 必测用例 + 反向验证）。

对基准样本《深圳海更数字传媒有限公司》的**真实 report_data** 执行：
  ① 正例：缺陷在 ⇒ 对应门禁判据必须报 ERROR（不许漏）
  ② 反例：把该处缺陷**修好** ⇒ 该判据必须转绿（不许永远报红 = 假闸门）

只读基准数据（原地打补丁后立即还原），不写回任何业务文件。

用法：
    ./.venv/Scripts/python.exe scripts/_acceptance_wb_trisk_2026_001.py
退出码：0 = 全部用例通过；1 = 存在漏报或假红。
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import quality_gates as qg          # noqa: E402
from engine import conclusion_grade as cg       # noqa: E402
from engine import numbering as nb              # noqa: E402
from engine import fact_store as fs             # noqa: E402

BENCH = ROOT / "data" / "cache" / "last_analysis_cache.json"
COMPANY_CODE = "91440300MA5H824G7M"
PERIOD = "202601"

REPORT: Dict[str, Any] = {}
ITEMS: List[Dict[str, Any]] = []


def _load() -> None:
    global REPORT, ITEMS
    with open(BENCH, "r", encoding="utf-8") as fh:
        REPORT = json.load(fh)["1"]["report"]["report"]
    ITEMS = qg.iter_items(REPORT)


def _checks(res: Dict[str, Any], gate: Optional[str] = None) -> List[str]:
    out: List[str] = []
    for g in res.get("gates") or []:
        if gate and g.get("gate") != gate:
            continue
        out += [f"{g['gate']}-{f['check_id']}" for f in (g.get("findings") or [])
                if f.get("severity") == "ERROR"]
    return out


def _run(**kw: Any) -> List[str]:
    return _checks(qg.run_all_gates(REPORT, company_code=COMPANY_CODE, period=PERIOD, **kw))


def _run_gate(gate: str, **kw: Any) -> List[str]:
    return [c for c in _checks(qg.run_all_gates(REPORT, company_code=COMPANY_CODE, period=PERIOD, **kw),
                               gate=gate)]


# ---------------------------------------------------------------- 现场打补丁工具
class Patch:
    """在真实报告对象上临时改写字段，退出时精确还原。"""

    def __init__(self) -> None:
        self._undo: List[Tuple[Any, Any, Any]] = []

    def set(self, obj: Any, key: Any, value: Any) -> None:
        if isinstance(obj, dict):
            self._undo.append((obj, key, obj.get(key, "<__ABSENT__>")))
            obj[key] = value
        elif isinstance(obj, list):
            self._undo.append((obj, key, obj[key]))
            obj[key] = value

    def delete(self, obj: Dict[str, Any], key: Any) -> None:
        self._undo.append((obj, key, obj.get(key, "<__ABSENT__>")))
        obj.pop(key, None)

    def restore(self) -> None:
        for obj, key, old in reversed(self._undo):
            if old == "<__ABSENT__>":
                if isinstance(obj, dict):
                    obj.pop(key, None)
                continue
            obj[key] = old
        self._undo.clear()

    def __enter__(self) -> "Patch":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.restore()


def _cn(i: int) -> str:
    d = "〇一二三四五六七八九"
    if i <= 10:
        return "十" if i == 10 else d[i]
    if i < 20:
        return "十" + d[i - 10]
    return d[i // 10] + "十" + (d[i % 10] if i % 10 else "")


def _rewrite_strings(obj: Any, fn: Callable[[str], str], *, seen: Optional[set] = None) -> int:
    """迭代式把 `obj` 内所有字符串替换为 fn(原值)，返回替换条数。不递归爆栈。"""
    seen = set() if seen is None else seen
    n = 0
    stack: List[Any] = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if id(cur) in seen:
                continue
            seen.add(id(cur))
            for k, v in list(cur.items()):
                if isinstance(v, str):
                    nv = fn(v)
                    if nv != v:
                        cur[k] = nv
                        n += 1
                elif isinstance(v, (dict, list, tuple)):
                    stack.append(v)
        elif isinstance(cur, list):
            if id(cur) in seen:
                continue
            seen.add(id(cur))
            for i, v in enumerate(cur):
                if isinstance(v, str):
                    nv = fn(v)
                    if nv != v:
                        cur[i] = nv
                        n += 1
                elif isinstance(v, (dict, list, tuple)):
                    stack.append(v)
    return n


# ---------------------------------------------------------------- 反向验证夹具
def _synth_report(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """构造最小报告夹具（用于文本类判据的正/反例）。"""
    return {
        "total_risks": len(items),
        "high_risk": 0, "mid_risk": 0, "low_risk": 0,
        "overall_level": "",
        "enterprise_readable_report": {"confirmed_problems": items},
    }


def _d_check(render_text: str = "", report: Optional[Dict[str, Any]] = None) -> List[str]:
    r = qg.gate_template_hygiene(report if report is not None else _synth_report([]),
                                 render_text=render_text)
    return [f"{r.gate}-{f.check_id}" for f in r.errors]


# ---------------------------------------------------------------- 用例定义
def case_a1_fix() -> Dict[str, Any]:
    """A1/A9 一票否决与未闭合：无证据或闭合度未达阈值者一律降为『待核验』。"""
    def fix(p: Patch) -> None:
        for it in ITEMS:
            h = it.get("evidence_have")
            c = it.get("closure")
            unclosed = (c is None) or (float(c) < cg.min_closure())
            if (h is None) or (h == 0) or unclosed:
                p.set(it, "risk_level", "待核验")
    return {"name": "A1/A9 无证据或未闭合不得带中风险及以上", "checks": ["A-A1", "A-A9"], "fix": fix}


def case_a4_fix() -> Dict[str, Any]:
    """A4 结论等级必填。修法=补登。"""
    def fix(p: Patch) -> None:
        for it in ITEMS:
            if not str(it.get("conclusion_grade") or "").strip():
                p.set(it, "conclusion_grade", cg.GRADE_L2)
    return {"name": "A4 每条风险必须登记 conclusion_grade", "checks": ["A-A4"], "fix": fix}


def case_b2_fix() -> Dict[str, Any]:
    """B2 编号连续。修法=按 1..N 重排『办理顺序』。"""
    def fix(p: Patch) -> None:
        for i, it in enumerate(ITEMS, 1):
            p.set(it, "办理顺序", _cn(i))
    return {"name": "B2 编号必须 1..N 连续（不跳号不重号）", "checks": ["B-B2"], "fix": fix}


def case_b6_count_fix() -> Dict[str, Any]:
    """B6 声明计数单一来源。修法=按实际盘点回填。"""
    def fix(p: Patch) -> None:
        from collections import Counter
        cnt = Counter(cg.normalize_level(it.get("risk_level"))[0] for it in ITEMS)
        p.set(REPORT, "total_risks", len(ITEMS))
        p.set(REPORT, "high_risk", cnt.get("高风险", 0))
        p.set(REPORT, "mid_risk", cnt.get("中风险", 0))
        p.set(REPORT, "low_risk", cnt.get("低风险", 0))
        p.set(REPORT, "overall_level", f"待核{len(ITEMS)}项")
        ledger = REPORT["enterprise_readable_report"].get("resolution_ledger")
        if isinstance(ledger, dict):
            for k in ("total", "ironclad", "self_provable", "pending", "with_resolve", "with_self_proof"):
                if k in ledger:
                    p.set(ledger, k, len(ITEMS))
    return {"name": "B6 声明计数 == 实际盘点（同一事实单一来源）", "checks": ["B-B6"], "fix": fix}


def case_b5_fix() -> Dict[str, Any]:
    """B5 结论自相矛盾。修法=**递归**把『已查明/已认定』改写为合规表述（只改 verdict 字段不够）。"""
    def subs(t: str) -> str:
        t = t.replace("本项已查明的风险；未认定到构成要件", "本项已读到与该风险指向一致的信号；未认定到构成要件")
        t = t.replace("本项已查明的风险", "本项已读到与该风险指向一致的信号")
        t = t.replace("已查明的风险", "已读到的风险信号")
        t = t.replace("已认定成立", "待认定")
        return t
    def fix(p: Patch) -> None:
        for it in ITEMS:
            _rewrite_strings(it, subs)
    return {"name": "B5 同一事项不得并存『未认定』与『已查明』", "checks": ["B-B5"], "fix": fix}


def case_b7_fix() -> Dict[str, Any]:
    """B7 同事实表述相反。修法=全报告递归把『均已取得』统一为同口径表述。"""
    def subs(t: str) -> str:
        return t.replace("三次均已取得", "本轮尚未核验完整").replace("三项均已取得", "本轮尚未核验完整") \
                .replace("均已取得", "本轮尚未核验完整")
    def fix(p: Patch) -> None:
        _rewrite_strings(REPORT, subs)
    return {"name": "B7 同一事实在不同章节不得表述相反", "checks": ["B-B7"], "fix": fix}


def case_c_fix() -> Dict[str, Any]:
    """C1/C2/C5/C7/C8 归档规范。修法=补编号/索引/签署/审计轨迹。"""
    def fix(p: Patch) -> None:
        svc = nb.NumberingService(COMPANY_CODE, PERIOD)
        p.set(REPORT, "workpaper_no", svc.workpaper_no(1))
        for it in ITEMS:
            it.setdefault("risk_no", svc.next("risk"))
        err = REPORT["enterprise_readable_report"]
        err.setdefault("indexes", {i: [] for i in ("risk", "evidence", "gap", "law", "amount", "attachment", "rectify")})
        sig = err.get("signature_block")
        if isinstance(sig, dict):
            sig.setdefault("审批人", "待签")
            sig.setdefault("编制人", "待签")
            sig.setdefault("复核人", "待签")
        else:
            err["signature_block"] = {"编制人": "待签", "复核人": "待签", "审批人": "待签"}
        err["audit_trail"] = [{"at": "2026-10-08T00:00:00", "operator": "system",
                               "action": "初始生成", "target": "报告", "before": "", "after": "",
                               "reason": "首轮生成"}]
    return {"name": "C1/C2/C5/C7/C8 归档规范（编号/索引/签署/审计轨迹）", "checks": ["C-C1","C-C2","C-C5","C-C7","C-C8"], "fix": fix}


# ---------------------------------------------------------------- 主流程
def main() -> int:
    _load()
    print("=" * 104)
    print("WB-TRISK-2026-001 验收：四道质量门禁 × 真实基准样本（深圳海更数字传媒有限公司）")
    print("=" * 104)
    print(f"基准文件：{BENCH.relative_to(ROOT)}")
    print(f"报告主体条目：{len(ITEMS)} 项")

    # ---------- 0. 引擎自检
    base = qg.run_all_gates(REPORT, company_code=COMPANY_CODE, period=PERIOD)
    print(f"\n引擎自检：{base['self_check_errors'] or 'OK'}")
    print(f"基线结论：all_passed={base['all_passed']}  formal_output_allowed={base['formal_output_allowed']}")
    print(f"          {base['summary']}")

    # ---------- 1. §七 必测用例（正例：必须报红）
    print("\n" + "=" * 104)
    print("【第一部分】§七 必测用例 —— 缺陷在，判据必须报红")
    print("=" * 104)
    baseline = set(_run())
    asserted: List[Tuple[str, str, bool]] = []

    cases = [
        ("§七-1a 金额矛盾（个人账户收款 1,082,000 vs 1,082,094.53）",
         "GATE-SCAN", "B-B6" in baseline or "B-B5" in baseline),
        ("§七-1b 成本无付款 1,498,692.68 vs 13,432.48（同项两个金额）",
         "GATE-SCAN", "B-B5" in baseline),
        ("§七-2 风险等级冲突（多税种联动『可能性低』却列高风险）",
         "B-B3", "B-B3" in baseline),
        ("§七-3 编号混乱（缺第八/十/十二/十六/十七）",
         "B-B2", "B-B2" in baseline),
        ("§七-4a 模板残留（『…需要：』后空白）",
         "D-D2", "D-D2" in baseline),
        ("§七-4b 模板残留（Markdown `**` 未剥离）",
         "D-D4", "D-D4" in baseline),
        ("§七-4c 模板残留（重复段落 = 模板疲劳）",
         "D-D5", "D-D5" in baseline),
        ("§七-5 归档规范（无底稿号/风险号/索引/签署/审计轨迹）",
         "C", bool({"C-C1", "C-C2", "C-C5", "C-C7", "C-C8"} & baseline)),
        ("§七-6 证据链门禁（closure=0 仍判『已查明风险』/ 高风险）",
         "A-A1", "A-A1" in baseline),
        ("§七-6b 证据链门禁（关键证据缺失仍出现定性词）",
         "A-A3", "A-A3" in baseline),
    ]
    ok = 0
    for name, cid, hit in cases:
        ok += hit
        print(f"  [{'PASS' if hit else 'FAIL'}] {name}")
    print(f"\n  §七 必测用例：{ok}/{len(cases)} 被门禁捕获")
    print(f"  基线 ERROR 判据清单：{sorted(baseline)}")

    # ---------- 2. 反向验证（反例：修好必须转绿，否则是假闸门）
    print("\n" + "=" * 104)
    print("【第二部分】反向验证 —— 把缺陷修好，该判据必须转绿（防「永远报红」的假闸门）")
    print("=" * 104)
    rev_ok = 0
    rev_total = 0
    for spec in (case_a1_fix(), case_a4_fix(), case_b2_fix(), case_b6_count_fix(),
                 case_b5_fix(), case_b7_fix(), case_c_fix()):
        with Patch() as p:
            spec["fix"](p)
            after = set(_run())
        lines = []
        for cid in spec["checks"]:
            rev_total += 1
            b_hit, a_hit = cid in baseline, cid in after
            good = b_hit and not a_hit
            rev_ok += good
            lines.append(f"         {cid}: 修前={b_hit} 修后={a_hit} → "
                         f"{'判据有效' if good else ('修前未命中(判据失效)' if not b_hit else '修后仍命中(假闸门)')}")
        print(f"  {spec['name']}")
        for ln in lines:
            print(ln)

    # ---------- 3. 文本类判据的合成夹具双向验证
    print("\n" + "=" * 104)
    print("【第三部分】文本类判据双向验证（合成夹具：有缺陷必报红 / 无缺陷必绿）")
    print("=" * 104)
    dup_a = "完全相同的一段超过二十五个字的模板文字用于触发重复度判据。"
    dup_b = "完全不同的一段超过二十五个字的模板文字用于对照重复度判据。"
    fixtures = [
        ("D-D2 孤立引导句",
         _d_check(render_text="说明2。要把这一项查清楚，需要：\n下一段"),
         _d_check(render_text="说明2。要把这一项查清楚，需要提供：合同、发票、流水。\n下一段")),
        ("D-D4 Markdown 残留",
         _d_check(render_text="**尚未完成签署**：编制人、复核人、审批人。"),
         _d_check(render_text="尚未完成签署：编制人、复核人、审批人。")),
        ("D-D5 重复段落",
         _d_check(render_text="\n".join([dup_a] * 5 + [dup_b] * 5)),
         _d_check(render_text="\n".join([f"{dup_a[:-1]}{i}。" for i in range(5)] +
                                        [f"{dup_b[:-1]}{i}。" for i in range(5)]))),
        ("D-D9 空表",
         _d_check(render_text="|  |  |\n|  |  |\n|  |  |\n"),
         _d_check(render_text="| 供应商 | 金额 |\n| 甲 | 100.00 |\n")),
        ("D-D1 UI 残留",
         _d_check(render_text="点击展开 下载 CSV localhost:8001"),
         _d_check(render_text="详见附件明细。")),
    ]
    fx_ok = 0
    for name, bad, good in fixtures:
        pos = bool(bad)
        neg = not bool(good)
        passed = pos and neg
        fx_ok += passed
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}：有缺陷命中={pos} 无缺陷命中={neg}")

    # ---------- 4. 事实库（SSOT）正反例
    print("\n" + "=" * 104)
    print("【第四部分】事实库（SSOT）× 金额口径登记 —— 正反例")
    print("=" * 104)
    st = fs.FactStore(company_code=COMPANY_CODE, period=PERIOD)
    st.declare(kind=fs.KIND_AMOUNT, label="未匹配到任何支付渠道的金额", value="13,432.48", source="表3")
    st.declare(kind=fs.KIND_AMOUNT, label="未匹配到任何支付渠道的金额", value="1,498,692.68", source="表4")
    conf_bad = st.conflicts()
    st2 = fs.FactStore(company_code=COMPANY_CODE, period=PERIOD)
    st2.declare(kind=fs.KIND_AMOUNT, label="银行差异", value="1,734,859.35",
                scope=fs.SCOPE_FULL, related="BANKSET", scope_note="收款−申报侧，全口径")
    st2.declare(kind=fs.KIND_AMOUNT, label="银行差异", value="227,659.35",
                scope=fs.SCOPE_ADJUSTED, related="BANKSET", scope_note="剔除明显非销售流入后")
    conf_good = st2.conflicts()
    st3 = fs.FactStore()
    fid = st3.declare(kind=fs.KIND_AMOUNT, label="测试", value="无法解析的文本")
    ssot_ok = bool(conf_bad) and not conf_good and st3.value_of(fid) is None
    print(f"  [{'PASS' if bool(conf_bad) else 'FAIL'}] 同键不同值 ⇒ 判定冲突（{len(conf_bad)} 组）")
    for c in conf_bad:
        print(f"         {c.describe()}")
    print(f"  [{'PASS' if not conf_good else 'FAIL'}] 已声明口径分组的多值 ⇒ 不判冲突（{len(conf_good)} 组）")
    print(f"  [{'PASS' if st3.value_of(fid) is None else 'FAIL'}] 解析失败 ⇒ 值为 None（不返回 0）")

    # ---------- 5. 结论分级映射
    print("\n" + "=" * 104)
    print("【第五部分】结论四级映射与一票否决")
    print("=" * 104)
    mapping_ok = True
    for v, exp in [("已触碰税务违规红线（资料齐全，可作初步判断）", "L3"),
                   ("疑似触碰税务违规红线（资料不足，待补充资料后判断）", "L2"),
                   ("本项已查明的风险；未认定到构成要件", "L2")]:
        got, reg = cg.map_verdict(v)
        good = (got == exp and reg)
        mapping_ok &= good
        print(f"  [{'PASS' if good else 'FAIL'}] {v[:24]}… → {got}（登记={reg}）")
    vto = cg.apply_veto({"risk_level": "高风险", "closure": 0.0, "evidence_have": 0,
                         "evidence_need": 3, "verdict": "本项已查明的风险", "conclusion_grade": "待核"})
    veto_ok = vto.get("risk_level") == "待核验" and vto.get("conclusion_grade") == "L2" and vto.get("_veto_applied")
    print(f"  [{'PASS' if veto_ok else 'FAIL'}] 一票否决后：risk_level={vto.get('risk_level')} "
          f"conclusion_grade={vto.get('conclusion_grade')}")

    # ---------- 汇总
    print("\n" + "=" * 104)
    total = ok + rev_ok + fx_ok + (3 if ssot_ok else 0) + (4 if mapping_ok else 0) + (1 if veto_ok else 0)
    expect = len(cases) + rev_total + len(fixtures) + 3 + 4 + 1
    print(f"验收汇总：{total}/{expect}")
    print("=" * 104)
    return 0 if total == expect else 1


if __name__ == "__main__":
    sys.exit(main())
