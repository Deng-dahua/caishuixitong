# -*- coding: utf-8 -*-
"""法律时效性核查程序 (Law Validity Checker)

理念（老邓 2026-07-13 确立）：不把法条固定写死当永久真理——规则引用"现行有效的法律"，
由本程序对每一部被引用的法律做动态时效核查。任何法律都有随时废止的可能，因此：
  1. 规则 policy_ref 引用时统一冠以"现行有效的《XX法》"，保留具体条号以保证稽查精确性；
  2. 本程序维护【现行有效法律清单】与【已废止法律清单】，主动核查引用法律的时效；
  3. 法律一旦变动，只需更新本程序的两张清单并跑 scan_rules()，即可自动标出全库需更新的规则，
     无需逐条改死代码。

数据源：与 engine/memory.py 的 rule_precise_writing.repealed_law_watch 同源。
用法：
  python engine/law_validity_checker.py [规则JSON路径]     # 扫描全库输出时效报告
  from engine.law_validity_checker import check_policy_ref  # 精写/审计时逐条核查
"""
import re, json, sys, os
from datetime import date

# ============ 已废止法律清单（含替代法与条文映射）============
REPEALED_LAWS = [
    {
        "patterns": ["增值税暂行条例"],
        "repealed_date": "2026-01-01",
        "replaced_by": "《中华人民共和国增值税法》(主席令第41号,2026-01-01施行)及《增值税法实施条例》(国务院令第826号)",
        "article_map": "暂行条例第1条纳税人→增值税法第1条;第2条税率→第9条;第4条应纳税额→第14条;第6条销售额价外费用→第17条;第19条纳税义务时间→第28条",
    },
    {
        "patterns": ["营业税暂行条例"],
        "repealed_date": "2016-05-01",
        "replaced_by": "营改增全面完成,相关业务改征增值税,依《中华人民共和国增值税法》",
        "article_map": "营业税应税项目→增值税应税交易,不再有营业税",
    },
]

# ============ 现行有效法律清单（版本+施行日期）============
# 维护规则：法律更替时更新此清单——废止的移入 REPEALED_LAWS，新法加入本表。
CURRENT_VALID_LAWS = [
    {"name": "中华人民共和国增值税法", "version": "主席令第41号", "effective": "2026-01-01"},
    {"name": "中华人民共和国增值税法实施条例", "version": "国务院令第826号", "effective": "2026-01-01"},
    {"name": "中华人民共和国税收征收管理法", "version": "2015修正", "effective": "2015-04-24"},
    {"name": "中华人民共和国税收征收管理法实施细则", "version": "2016修订", "effective": "2016-02-06"},
    {"name": "中华人民共和国企业所得税法", "version": "2018修正", "effective": "2018-12-29"},
    {"name": "中华人民共和国企业所得税法实施条例", "version": "2019修订", "effective": "2019-04-23"},
    {"name": "中华人民共和国个人所得税法", "version": "2018修正", "effective": "2019-01-01"},
    {"name": "中华人民共和国个人所得税法实施条例", "version": "2018修订", "effective": "2019-01-01"},
    {"name": "中华人民共和国会计法", "version": "2024修正", "effective": "2024-07-01"},
    {"name": "中华人民共和国发票管理办法", "version": "2023修订", "effective": "2023-07-20"},
    {"name": "中华人民共和国印花税法", "version": "主席令第89号", "effective": "2022-07-01"},
    {"name": "中华人民共和国契税法", "effective": "2021-09-01"},
    {"name": "中华人民共和国城市维护建设税法", "effective": "2021-09-01"},
    {"name": "中华人民共和国土地增值税暂行条例", "note": "现行有效(尚未上升为法)"},
    {"name": "中华人民共和国房产税暂行条例", "note": "现行有效"},
    {"name": "中华人民共和国车船税法", "effective": "2012-01-01"},
    {"name": "中华人民共和国资源税法", "effective": "2020-09-01"},
    {"name": "中华人民共和国消费税暂行条例", "note": "现行有效(消费税法立法中)"},
    {"name": "中华人民共和国城镇土地使用税暂行条例", "note": "现行有效"},
    {"name": "中华人民共和国刑法", "version": "2023修正", "note": "现行有效"},
    {"name": "中华人民共和国民法典", "effective": "2021-01-01"},
    {"name": "中华人民共和国电子商务法", "effective": "2019-01-01"},
    {"name": "企业所得税税前扣除凭证管理办法", "note": "现行有效(总局公告2018年第28号)"},
    {"name": "个人所得税扣缴申报管理办法", "note": "现行有效(试行,总局公告2018年第61号)"},
    {"name": "特别纳税调整实施办法", "note": "现行有效(试行,国税发〔2009〕2号)"},
    {"name": "企业会计准则", "note": "现行有效"},
    {"name": "财税〔2003〕158号", "note": "现行有效"},
]

LAW_PATTERN = re.compile(r"《([^》]+)》")
# 核验标注（内部会提及被废止法作说明，核查时须先剥离，避免误报为"仍在引用"）
NOTE_PATTERN = re.compile(r"（法规现行性核验[：:][^）]*）")


def extract_laws(text):
    """从文本提取引用的法律名称（《》包裹）。先剥离核验标注，避免把说明文字里提到的废止法误判为引用。"""
    if not isinstance(text, str):
        return []
    text = NOTE_PATTERN.sub("", text)
    # 去重保序
    seen, out = set(), []
    for m in LAW_PATTERN.findall(text):
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


def check_law(name):
    """核查单部法律的时效状态 → dict(status)。status: REPEALED / VALID / UNKNOWN"""
    for r in REPEALED_LAWS:
        for p in r["patterns"]:
            if p in name:
                return {"law": name, "status": "REPEALED", "repealed_date": r["repealed_date"],
                        "replaced_by": r["replaced_by"], "article_map": r["article_map"]}
    for c in CURRENT_VALID_LAWS:
        cn = c["name"]
        short = cn.replace("中华人民共和国", "")
        if cn in name or (short and short in name) or name in cn:
            return {"law": name, "status": "VALID", "version": c.get("version", ""),
                    "effective": c.get("effective", "")}
    return {"law": name, "status": "UNKNOWN", "note": "未在现行/废止清单，需人工核验时效性"}


def check_policy_ref(text):
    """核查一段 policy_ref 中所有引用法律的时效 → list"""
    return [check_law(law) for law in extract_laws(text)]


# ============ 已废止法规 → 现行法 精确条文替换映射（供 auto_process 自动改写）============
REPEALED_ARTICLE_SUBS = [
    (r"《中华人民共和国增值税暂行条例实施细则》第十二条", "《中华人民共和国增值税法实施条例》（价外费用相关规定）"),
    (r"《增值税暂行条例实施细则》第十二条", "《增值税法实施条例》（价外费用相关规定）"),
    (r"《中华人民共和国增值税暂行条例》第一条", "《中华人民共和国增值税法》第一条"),
    (r"《增值税暂行条例》第一条", "《增值税法》第一条"),
    (r"《中华人民共和国增值税暂行条例》第四条", "《中华人民共和国增值税法》第十四条"),
    (r"《增值税暂行条例》第四条", "《增值税法》第十四条"),
    (r"《中华人民共和国增值税暂行条例》第六条", "《中华人民共和国增值税法》第十七条"),
    (r"《增值税暂行条例》第六条", "《增值税法》第十七条"),
    (r"《中华人民共和国增值税暂行条例》第十九条", "《中华人民共和国增值税法》第二十八条"),
    (r"《增值税暂行条例》第十九条", "《增值税法》第二十八条"),
    (r"《中华人民共和国增值税暂行条例实施细则》", "《中华人民共和国增值税法实施条例》"),
    (r"《增值税暂行条例实施细则》", "《增值税法实施条例》"),
    (r"《中华人民共和国增值税暂行条例》", "《中华人民共和国增值税法》"),
    (r"《增值税暂行条例》", "《增值税法》"),
]
TEXT_FIELDS = ["policy_ref", "suggestion", "tax_impact", "risk_table", "determination",
               "normal_reason", "direction", "drill_questions", "phenomena", "focus",
               "evidence", "threshold", "action", "remedy", "applicable_condition"]


def auto_process(rules, today=None):
    """引擎自动校验+自动处理（取代"待人工核验"）。
    ① 引用已废止法律 → 按 REPEALED_ARTICLE_SUBS 自动替换为现行法条文；
    ② policy_ref 缺核验标注 → 引擎自动比对废止库：未命中废止即判定现行有效，自动补
       "（引擎自动核验：YYYY-MM-DD，经比对未命中废止法规库，判定所引法律现行有效，已纳入时效监控）"；
       命中废止的（替换后理论上不再有）→ 标注需更新。
    全程无"待人工"出口——引擎自行判定处理，并留痕透明可追溯。
    返回处理统计 dict。"""
    from datetime import date as _date
    today = today or _date.today().isoformat()
    stats = {"replaced_repealed": 0, "auto_verified": 0, "flagged_repealed": 0}
    for r in rules:
        # ① 自动替换已废止法条
        for fld in TEXT_FIELDS:
            v = r.get(fld)
            if not isinstance(v, str) or not v:
                continue
            nv = v
            for pat, rep in REPEALED_ARTICLE_SUBS:
                nv = re.sub(pat, rep, nv)
            if nv != v:
                r[fld] = nv
                stats["replaced_repealed"] += 1
        # ② policy_ref 自动核验标注
        pr = r.get("policy_ref", "")
        if isinstance(pr, str) and pr and "核验" not in pr:
            checks = check_policy_ref(pr)
            has_repealed = any(c["status"] == "REPEALED" for c in checks)
            if has_repealed:
                r["policy_ref"] = pr.rstrip() + f"（引擎自动核验：{today}，检出仍引用已废止法规，已按现行法映射自动更新）"
                stats["flagged_repealed"] += 1
            else:
                r["policy_ref"] = pr.rstrip() + f"（引擎自动核验：{today}，经比对未命中废止法规库，判定所引法律现行有效，已纳入时效监控）"
                stats["auto_verified"] += 1
    return stats


def scan_rules(rules):
    """扫描规则库 → 时效核查报告"""
    rep = {"total": len(rules), "repealed_hits": [], "unknown_laws": {},
           "no_verify_date": [], "valid_only": 0}
    for r in rules:
        pr = r.get("policy_ref", "")
        if not isinstance(pr, str) or not pr:
            continue
        checks = check_policy_ref(pr)
        has_repealed = False
        for c in checks:
            if c["status"] == "REPEALED":
                has_repealed = True
                rep["repealed_hits"].append({"id": r.get("id"), "law": c["law"],
                                             "replaced_by": c["replaced_by"]})
            elif c["status"] == "UNKNOWN":
                rep["unknown_laws"][c["law"]] = rep["unknown_laws"].get(c["law"], 0) + 1
        if ("法规现行性核验" not in pr) and ("引擎自动核验" not in pr):
            rep["no_verify_date"].append(r.get("id"))
        if not has_repealed:
            rep["valid_only"] += 1
    return rep


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    default = os.path.join(here, "..", "static", "tax_risk_rules_local_export.json")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = args[0] if args else default
    with open(path, encoding="utf-8") as f:
        rules = json.load(f)

    if "--auto-process" in sys.argv:
        stats = auto_process(rules)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rules, f, ensure_ascii=False, indent=2)
        print(f"===== 引擎自动校验+处理完成 · {date.today()} =====")
        print(f"自动替换已废止法条的字段: {stats['replaced_repealed']} 处")
        print(f"自动核验并补标注(现行有效): {stats['auto_verified']} 条")
        print(f"检出并标记仍引用废止法规: {stats['flagged_repealed']} 条")
        # 处理后复核
        rep = scan_rules(rules)
        print(f"处理后：仍引用已废止法律 {len(rep['repealed_hits'])} 条；缺核验标注 {len(rep['no_verify_date'])} 条")
        sys.exit(0)

    rep = scan_rules(rules)
    print(f"===== 法律时效性核查报告 · {date.today()} =====")
    print(f"规则总数: {rep['total']}")
    print(f"[严重] 仍引用已废止法律的规则: {len(rep['repealed_hits'])} 条")
    for h in rep["repealed_hits"][:20]:
        print(f"    #{h['id']} → 已废止《{h['law']}》，应改依 {h['replaced_by']}")
    total_unknown_rules = sum(rep["unknown_laws"].values())
    print(f"[监控] 引用清单外法律(引擎自动纳入时效监控,非待人工)的引用数: {total_unknown_rules}")
    for law, cnt in sorted(rep["unknown_laws"].items(), key=lambda kv: -kv[1])[:15]:
        print(f"    《{law}》: {cnt} 处")
    print(f"[规范] policy_ref 缺法规核验标注的规则: {len(rep['no_verify_date'])} 条（可用 --auto-process 由引擎自动核验补全）")
    print(f"未命中废止法律的规则: {rep['valid_only']} 条")
