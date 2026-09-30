"""小微税种/费义务探测器（2026-09-30）

补齐一键分析中**尚无红线覆盖**的税种/费义务（覆盖度审计外的新缺口）：
    文化事业建设费 / 车辆购置税 / 耕地占用税 / 烟叶税 / 船舶吨税 / 增值税留抵退税真实性。

这些义务中 6 类（文建费/车购税/耕地占用税/烟叶税/船舶吨税/留抵退税）已在 tax_redlines.py 登记红线
（findings 带 redline_id、运行期 declared 归位）；其余费类义务（残保金/水利基金/工会经费）仅作报告级「待核线索」。
识别口径表驱动，新增同类义务只需在 SPECS 加一行。

核心原则（严守系统铁律）：
1. 发现≠确认：只产出「待核疑点」，绝不下定性结论。
2. 有线索 → 产出待核；同时列出需补资料。命中对应税种申报/缴款记录则抑制（不误报）。
3. finding 必须带 `_scenario_governed=True`（否则被 seal_governed_findings 静默丢弃）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from engine.gap_risk_detectors import _dump, _hit

SPECS: List[Dict[str, Any]] = [
    {
        "topic": "文化事业建设费未申报（待核）", "tax_type": "文化事业建设费", "redline_id": "RL-SPT-017",
        "signals": ["广告服务", "广告发布", "娱乐服务", "文化服务", "广告代理"],
        "decl_keywords": ["文化事业建设费"],
        "needs": ["广告服务/娱乐服务收入台账", "增值税申报表", "文化事业建设费申报表"],
        "method": "检索发票品名/经营范围涉广告、娱乐服务 → 无对应文化事业建设费申报/缴款记录 → 命中即置疑",
        "policy_ref": "财税〔2016〕25号、财税〔2016〕60号（广告服务、娱乐业按3%征收）",
    },
    {
        "topic": "车辆购置税未申报（待核）", "tax_type": "车辆购置税", "redline_id": "RL-SPT-018",
        "signals": ["车辆购置", "购置车辆", "新增车辆", "购车款"],
        "decl_keywords": ["车辆购置税"],
        "needs": ["固定资产明细（车辆）", "机动车销售统一发票", "车辆购置税完税证明"],
        "method": "检索固定资产新增车辆/购车支出 → 无车辆购置税完税记录 → 命中即置疑",
        "policy_ref": "《车辆购置税法》第一条、第四条（10%比例税率）",
    },
    {
        "topic": "耕地占用税未申报（待核）", "tax_type": "耕地占用税", "redline_id": "RL-SPT-014",
        "signals": ["耕地占用", "占用耕地", "农用地转用", "建设用地审批"],
        "decl_keywords": ["耕地占用税"],
        "needs": ["农用地转用批准文件", "占用耕地面积资料", "耕地占用税申报表"],
        "method": "检索占用耕地/农用地转用线索 → 无耕地占用税申报记录 → 命中即置疑",
        "policy_ref": "《耕地占用税法》第一条、第三条、第四条",
    },
    {
        "topic": "烟叶税未申报（待核）", "tax_type": "烟叶税", "redline_id": "RL-SPT-015",
        "signals": ["烟叶", "收购烟叶", "烤烟"],
        "decl_keywords": ["烟叶税"],
        "needs": ["烟叶收购凭证与台账", "收购金额资料", "烟叶税申报表"],
        "method": "检索烟叶收购线索 → 无烟叶税申报/缴款记录 → 命中即置疑",
        "policy_ref": "《烟叶税法》第一条、第三条（收购金额20%）",
    },
    {
        "topic": "船舶吨税未申报（待核）", "tax_type": "船舶吨税", "redline_id": "RL-SPT-016",
        "signals": ["船舶", "吨税", "船籍", "进出境船舶"],
        "decl_keywords": ["船舶吨税"],
        "needs": ["船舶登记与船籍资料", "船舶进出境记录", "船舶吨税完税凭证"],
        "method": "检索自有/使用船舶线索 → 无船舶吨税缴款记录 → 命中即置疑",
        "policy_ref": "《船舶吨税法》第一条、第三条、第五条",
    },
    {
        "topic": "增值税留抵退税真实性存疑（待核）", "tax_type": "增值税", "redline_id": "RL-VAT-013",
        "signals": ["留抵退税", "增量留抵", "存量留抵", "留抵税额退还"],
        "decl_keywords": [],
        "needs": ["增值税纳税申报表（含留抵税额）", "进项发票全量明细", "留抵退税申请与税务机关核准资料", "进销存与银行流水"],
        "method": "检索留抵退税/增量留抵线索 → 结合进项发票真实性与虚开风险 → 命中即置疑骗取留抵退税",
        "policy_ref": "财政部 税务总局公告2022年第14号、21号",
    },
    {
        "topic": "残疾人就业保障金未申报（待核）", "tax_type": "残疾人就业保障金",
        "signals": ["残疾人就业保障金", "残保金", "安排残疾人就业", "残疾人就业"],
        "decl_keywords": ["残疾人就业保障金", "残保金"],
        "needs": ["在职职工人数与工资总额", "残疾人就业证明或减免证明", "残保金申报表"],
        "method": "检索工资总额/在职人数线索 → 未申报残保金且无减免证明 → 命中即置疑",
        "policy_ref": "《残疾人就业条例》、财税〔2015〕72号",
    },
    {
        "topic": "水利建设基金未申报（待核）", "tax_type": "水利建设基金",
        "signals": ["水利建设基金", "水利基金", "水利建设专项资金"],
        "decl_keywords": ["水利建设基金", "水利基金"],
        "needs": ["销售收入或增值税计税依据", "水利建设基金申报表"],
        "method": "检索销售收入/计税依据线索 → 未申报水利建设基金 → 命中即置疑",
        "policy_ref": "财税〔2011〕2号",
    },
    {
        "topic": "工会经费未足额拨缴（待核）", "tax_type": "工会经费",
        "signals": ["工会经费", "拨缴工会经费", "工会筹备金"],
        "decl_keywords": ["工会经费", "工会筹备金"],
        "needs": ["工资总额", "工会经费拨缴凭证", "工会组织证明"],
        "method": "检索工资总额线索 → 未按工资总额2%拨缴工会经费 → 命中即置疑",
        "policy_ref": "《中华人民共和国工会法》第四十三条",
    },
    {
        "topic": "营业账簿印花税未申报（待核）", "tax_type": "印花税", "redline_id": "RL-OTH-007",
        "signals": ["实收资本", "资本公积", "资金账簿"],
        "decl_keywords": ["资金账簿", "营业账簿"],
        "needs": ["财务报表（资产负债表）", "印花税申报表"],
        "method": "检索科目余额表/资产负债表实收资本＋资本公积>0 → 无印花税申报表资金账簿税目申报/缴款记录 → 命中即置疑",
        "policy_ref": "《印花税法》第二条、第五条（营业账簿税目万分之五，小微企业减半）",
    },
]


def _obligation_finding(spec: Dict, hits: Sequence[str]) -> Dict:
    topic = spec["topic"]
    return {
        "type": topic,
        "detail": (f"在账簿/申报/发票资料中检测到涉及「{topic.rstrip('（待核）')}」的线索"
                   f"（命中：{'、'.join(hits[:4])}）。本项为待核线索：请补充下列资料后复核，"
                   "以确认是否属于法定免征或已申报情形。"),
        "level": "低风险",
        "score": 3,
        "tax_type": spec["tax_type"],
        "domain": spec["tax_type"],
        "policy_ref": spec.get("policy_ref", ""),
        "suggestion": "请补充下列资料后复核：" + "、".join(spec["needs"]),
        "items": [{"name": m, "status": "待补充"} for m in spec["needs"]],
        "evidence": list(hits[:4]),
        "needs_material": list(spec["needs"]),
        "_scenario_governed": True,   # ★ 必须打标，否则被输出封印丢弃
        "_gap_obligation": spec["tax_type"],
        "_detection_method": spec.get("method", ""),
        "_unconfirmed": True,
    }


def run_gap_tax_obligation_detection(engine_data: Dict, pipeline_log: List[str] = None) -> List[Dict]:
    """执行小微税种/费义务探测器，返回待核发现列表（无红线归属，仅报告级线索）。"""
    data = engine_data if isinstance(engine_data, dict) else {}
    decl = _dump(data.get("tax_declarations"))
    text = "\n".join([
        _dump(data.get("vouchers")), _dump(data.get("balances")),
        _dump(data.get("sal_invs")), _dump(data.get("pur_invs")),
        _dump(data.get("bank_txs")), _dump(data.get("fixed_assets")),
        _dump(data.get("contracts")), decl,
    ])

    results: List[Dict] = []
    for spec in SPECS:
        try:
            hits = _hit(text, spec["signals"])
            if not hits:
                continue
            dl = spec.get("decl_keywords") or []
            if dl and any(k in decl for k in dl):
                continue  # 已见对应税种申报/缴款 → 不置疑
            f = _obligation_finding(spec, hits)
            rid = spec.get("redline_id")
            if rid:
                f["redline_id"] = rid
                f["_gap_detector"] = rid
                f["constituent_hits"] = [{"index": 1, "evidence":
                    "命中线索：「" + "、".join(str(e) for e in hits[:3])
                    + "」（要件观察事实；是否构成该要件之情形须人工复核）"}]
            results.append(f)
        except Exception as exc:
            if pipeline_log is not None:
                pipeline_log.append(f"[税费义务探测器] {spec.get('tax_type')} 执行异常: {exc}")

    if pipeline_log is not None and results:
        pipeline_log.append(f"[税费义务探测器] 命中小微税种/费义务待核 {len(results)} 条")
    return results
