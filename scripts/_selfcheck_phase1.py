# -*- coding: utf-8 -*-
"""阶段1 判据反向验证：每条判据都必须『有缺陷时报红、无缺陷时不报』。

用法：
    ./.venv/Scripts/python.exe scripts/_selfcheck_phase1.py

目的（项目铁律）：不经验证的判据＝假判据。此前已实测抓到 P8『摘要』误命中表格列名、
P3-b 正则过严导致真缺陷漏报 —— 故每条判据都必须双向验证。

判据清单与阶段1 脚本一一对应，不在本文件另立规则。
"""
from __future__ import annotations

import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("p1", os.path.join(ROOT, "scripts", "_phase1_diagnose.py"))
p1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p1)

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(("  [PASS] " if cond else "  [FAIL] ") + name + (f"  {detail}" if detail else ""))


def run(lines: list[str]) -> tuple[list[dict], list[dict], list[dict]]:
    blocks = p1.build_blocks(lines)
    findings, fact_rep = p1.classify(blocks)
    rates = p1.compute_rates(blocks, findings, fact_rep) if hasattr(p1, "compute_rates") else {
        "整体": {"重复率": 0.0, "阈值": 0.10, "判定": "PASS",
                 "冗余字数": 0, "总字数": 1, "冗余块数": 0, "总块数": len(blocks)}
    }
    problems = p1.diagnose_problems(blocks, lines, rates)
    return findings, fact_rep, problems


def prob(problems: list[dict], pid: str) -> dict | None:
    return next((p for p in problems if p["id"] == pid), None)


def prob_hit(problems: list[dict], pid: str, name_kw: str = "") -> bool:
    """命中判定；name_kw 用于同一 id 下有多条规则时精确定位（P3 下有两条）。"""
    p = prob(problems, pid) if not name_kw else next(
        (x for x in problems if x["id"] == pid and name_kw in x["name"]), None)
    if p is None:
        return False
    st = p.get("status", "")
    return p.get("count", 0) > 0 or st in ("检出", "FAIL", "未检出（即缺）")


# ============================================================ 用例
def t_p2():
    bad = ["疑点1：甲办理顺序：第一项", "内容甲。", "疑点2：乙办理顺序：第三项", "内容乙。"]
    good = ["疑点1：甲办理顺序：第一项", "内容甲。", "疑点2：乙办理顺序：第二项", "内容乙。"]
    _, _, pb = run(bad)
    _, _, pg = run(good)
    check("P2 办理顺序断裂-缺陷报红", prob_hit(pb, "P2-b"))
    check("P2 办理顺序正常-不报", not prob_hit(pg, "P2-b"))


def t_p3():
    bad = ["本企业本项已查明的风险；未认定到构成要件的可能性中等。"]
    good = ["本企业本项经核对未认定到任何一条构成要件，属 L2 待核线索。"]
    _, _, pb = run(bad)
    _, _, pg = run(good)
    check("P3 『已查明的风险』破句-缺陷报红", prob_hit(pb, "P3", "破句"))
    check("P3 正常结论句-不报", not prob_hit(pg, "P3", "破句"))


def t_p3b():
    bad = ["本项已查明相关信号；但未认定到任何一条构成要件成立，不作认定。"]
    good = ["本项已从账内检出信号，未认定到构成要件成立，属 L2 待核线索。"]
    _, _, pb = run(bad)
    _, _, pg = run(good)
    check("P3-b 『已查明』与『未认定』同段-缺陷报红", prob_hit(pb, "P3", "同段并存"))
    check("P3-b 单一结论口径-不报", not prob_hit(pg, "P3", "同段并存"))


def t_p4b():
    bad = ["疑点1：甲", "［弱］直接证据：劳动合同　现状：缺失", "风险等级 高风险", "本项结论。"]
    good = ["疑点1：甲", "［弱］直接证据：劳动合同　现状：缺失", "风险等级 待核验", "本项结论。"]
    _, _, pb = run(bad)
    _, _, pg = run(good)
    check("P4-b 关键证据缺失仍给高风险-缺陷报红", prob_hit(pb, "P4-b"))
    check("P4-b 缺失时降为待核验-不报", not prob_hit(pg, "P4-b"))


def t_p5():
    bad = ["本项等级：极高风险。", "另项等级：较高风险。"]
    good = ["本项等级：高风险。", "另项等级：中风险。"]
    _, _, pb = run(bad)
    _, _, pg = run(good)
    check("P5 等级词不在法定词表-缺陷报红", prob_hit(pb, "P5"))
    check("P5 法定等级词-不报", not prob_hit(pg, "P5"))


def t_p6():
    bad = ["法定依据：《某法》第十条（版本未登记，须核对现行有效文本）。"]
    good = ["法定依据：《某法》第十条（2018年修正；主席令第二十三号，现行有效）。"]
    _, _, pb = run(bad)
    _, _, pg = run(good)
    check("P6 法条版本未登记-缺陷报红", prob_hit(pb, "P6"))
    check("P6 法条已核版本-不报", not prob_hit(pg, "P6"))


def t_p7():
    bad = ["本项结论：待核（须项目上下文）。"]
    good = ["本项结论：待核验（须项目上下文）。"]
    _, _, pb = run(bad)
    _, _, pg = run(good)
    check("P7 『待核』非法定词-缺陷报红", prob_hit(pb, "P7"))
    check("P7 统一为『待核验』-不报", not prob_hit(pg, "P7"))


def t_p8():
    bad = ["一、检查情况总述", "本轮共 16 项风险事项。"]
    good = ["一、决策摘要", "本轮共 16 项风险事项，建议 7 日内补齐资料。"]
    _, _, pb = run(bad)
    _, _, pg = run(good)
    check("P8 缺决策摘要-缺陷报红", prob_hit(pb, "P8"))
    check("P8 有决策摘要-不报", not prob_hit(pg, "P8"))


def t_p9():
    bad = ["|  |  |  |", "分述"]
    good = ["| 要件 | 结论 | 说明 |", "本项无适用行"]
    _, _, pb = run(bad)
    _, _, pg = run(good)
    check("P9 空表行/空小标题-缺陷报红", prob_hit(pb, "P9"))
    check("P9 正常表与正常表述-不报", not prob_hit(pg, "P9"))


def t_p6b():
    bad = ["业务招待费411,111.53元，占主营业务收入6,636,800.57元的6.19%，超过收入5%的法定扣除标准。"]
    good = ["业务招待费411,111.53元，占主营业务收入6,636,800.57元的6.19%，超过收入5‰的法定扣除标准。"]
    _, _, pb = run(bad)
    _, _, pg = run(good)
    b = prob(pb, "P6-b")
    g = prob(pg, "P6-b")
    check("P6-b 招待费限额写成5%-缺陷报红", bool(b) and b.get("count", 0) > 0)
    check("P6-b 招待费限额为5‰-不报", bool(g) and g.get("count", 0) == 0)


def t_exact_dup():
    bad = ["这是一段需要在报告中重复出现的完整陈述内容。"] * 4
    good = ["甲事项的事实陈述。", "乙事项的事实陈述。", "丙事项的事实陈述。"]
    fb, _, _ = run(bad)
    fg, _, _ = run(good)
    hb = [f for f in fb if f["type"] == "完全重复"]
    hg = [f for f in fg if f["type"] == "完全重复"]
    check("完全重复-4次相同段报红", len(hb) > 0)
    check("完全重复-3段各不相同不报", len(hg) == 0)


def t_boiler():
    bp = p1.RULES["boilerplate"]["exact"][0]
    bad = [bp] * 3
    good = ["甲事项的核对要点说明。", "乙事项的核对要点说明。"]
    fb, _, _ = run(bad)
    fg, _, _ = run(good)
    check("套话重复-3次通用句报红", any(f["type"] == "套话重复" for f in fb))
    check("套话重复-无通用句不报", not any(f["type"] == "套话重复" for f in fg))


def t_skeleton():
    t = p1.RULES["structure_skeleton"]["titles"][0]
    bad = ["疑点1：甲", t, "内容甲。", "疑点2：乙", t, "内容乙。"]
    good = ["疑点1：甲", t, "内容甲。"]
    fb, _, _ = run(bad)
    fg, _, _ = run(good)
    check("结构重复-骨架出现2次报红", any(f["type"] == "结构重复" for f in fb))
    check("结构重复-骨架出现1次不报", not any(f["type"] == "结构重复" for f in fg))


def t_near_dup():
    a = "本项在账内检出信号，业务招待费占主营业务收入的比例超过法定扣除标准，需纳税调增。"
    b = "本项在账内检出信号，业务招待费占主营业务收入的比例超过法定扣除标准，应当纳税调增。"
    bad = [a, b]
    good = ["甲事项：银行收款与申报收入存在差异，需核实。", "乙事项：工资表人数与社保参保人数不符，需核实劳动合同。"]
    fb, _, _ = run(bad)
    fg, _, _ = run(good)
    check("近似重复-高度相似两段报红", any(f["type"] == "近似重复" for f in fb))
    check("近似重复-不同主题两段不报", not any(f["type"] == "近似重复" for f in fg))


def t_fact_rep():
    """判据口径：『同一事实完整出现』= 同一数值所在的**高度相似句子**重复。
    上下文不同的表述（即便含同一数值）不算重复完整陈述 —— 这是修正后的口径，
    不能用『含该数值的段落数』（那会把正常引用全部误判）。"""
    bad = ["本项业务招待费 6,636,800.57 元，已超过收入 5‰ 的法定扣除标准，需纳税调增。",
           "本项业务招待费 6,636,800.57 元，已超过收入 5‰ 的法定扣除标准，应作纳税调增。"]
    ctx = ["本项业务招待费 6,636,800.57 元，占收入比例超限。",
           "另项银行收款 5,280,000.00 元，与申报收入存在差异。"]
    _, rb, _ = run(bad)
    _, rg, _ = run(ctx)
    check("事实重复-同一数值所在相似句重复报红", any(x["occurrences"] >= 2 for x in rb))
    check("事实重复-上下文不同（含同一数值但表述不同）不报", not any(x["occurrences"] >= 2 for x in rg))


def t_render_residue():
    bad = ["|  |  |", "分述", "总述"]
    good = ["| 要件 | 结论 |", "本项结论及理由"]
    fb, _, _ = run(bad)
    fg, _, _ = run(good)
    check("渲染残留-空表行与空标题报红", any(f["type"] == "渲染残留" for f in fb))
    check("渲染残留-无残留不报", not any(f["type"] == "渲染残留" for f in fg))


def main() -> int:
    print("=== 阶段1 判据反向验证（每条：缺陷报红 + 正常不报）===")
    for fn in (t_p2, t_p3, t_p3b, t_p4b, t_p5, t_p6, t_p7, t_p8, t_p9, t_p6b,
               t_exact_dup, t_boiler, t_skeleton, t_near_dup, t_fact_rep, t_render_residue):
        fn()
    print(f"\n结果：PASS {len(PASS)} / FAIL {len(FAIL)}  (合计 {len(PASS)+len(FAIL)})")
    if FAIL:
        print("失败项：")
        for f in FAIL:
            print("  - " + f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
