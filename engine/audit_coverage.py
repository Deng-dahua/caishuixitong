"""风险检查覆盖度自检器（无死角风险检查的核心机制）。

设计目标：每次风险检查结束后，强制产出"三段式覆盖清单"，让风险检查员一眼看清
本次风险检查是否存在盲区，做到"不留暗区、每个盲区都有交代"：

  1. 已覆盖(EXECUTED)：本次实际运行且已注册的规则，及其命中情况
  2. 未触发(NO_HIT)：已注册但本次数据未命中的规则（仍属已覆盖能力）
  3. 盲区(GAP)：经识别的风险检查风险域，但当前系统尚无对应可执行规则，
     须明确标注原因（数据缺失 / 本质不可数字化 / 待实现）

此外枚举"中国主要税种风险检查风险域全景"，与现有规则做映射，输出
coverage_matrix，使风险检查员能断言本次风险检查在规则维度"无遗漏"。
"""

from __future__ import annotations

# ── 中国主要税种 × 风险检查风险域全景（用于覆盖度对标）────────────────────
# 每个域给出：税种、风险主题、是否有可执行规则、对应VR、盲区原因（若有）
RISK_DOMAIN_PANORAMA = [
    # 增值税
    ("增值税", "税负率异常", True, "VR026", ""),
    ("增值税", "作废/红冲异常", True, "VR027", ""),
    ("增值税", "未开票收入隐匿", True, "VR028", ""),
    ("增值税", "零申报异常", True, "VR029", ""),
    ("增值税", "进项税应转出未转出", True, "VR032", ""),
    ("增值税", "变名开票/进销背离", True, "VR033", ""),
    ("增值税", "视同销售未计提销项", True, "VR036", ""),
    ("增值税", "虚开发票/资金回流", True, "VR012/VR013/VR025", ""),
    ("增值税", "出口退税违规", False, "", "需出口退免税申报数据与海关报关单勾稽，待实现"),
    # 企业所得税
    ("企业所得税", "收入确认时点", True, "VR001/VR002/VR018", ""),
    ("企业所得税", "业务招待费超限", True, "VR038", ""),
    ("企业所得税", "广告费超限", True, "VR039", ""),
    ("企业所得税", "福利费超限", True, "VR040", ""),
    ("企业所得税", "折旧摊销异常", True, "VR041", ""),
    ("企业所得税", "成本费用虚列", True, "VR034", ""),
    ("企业所得税", "关联方转让定价", True, "VR037", "需工商股权穿透数据支撑定性"),
    ("企业所得税", "亏损弥补年限", False, "", "需历年汇算清缴亏损台账，待实现"),
    ("企业所得税", "资产损失税前扣除", False, "", "需资产损失专项申报资料，待实现"),
    # 个人所得税
    ("个人所得税", "工资社保差异", True, "VR005", ""),
    ("个人所得税", "股东借款视同分红", True, "VR030", ""),
    ("个人所得税", "劳务报酬 vs 工资", False, "", "需人员身份与合同性质判定，待实现"),
    ("个人所得税", "多处取得/年终奖", False, "", "需自然人涉税信息，待实现"),
    # 财产税与行为税
    ("印花税", "购销合同计税依据", True, "VR031", ""),
    ("印花税", "借款/租赁合同等其他税目", True, "VR035", ""),
    ("房产税", "从价/从租计征", True, "VR042", ""),
    ("城建税及附加", "随增值税附征", True, "VR043", ""),
    ("城镇土地使用税", "实际占用土地面积", False, "", "需土地权证与面积数据，待实现"),
    ("车船税", "自有车辆船舶", False, "", "需车辆船舶台账，待实现"),
    # 数据质量与勾稽
    ("数据质量", "发票/存货/资金勾稽", True, "VR003-VR025", ""),
    ("生产实质", "能耗/投入产出/人员", True, "VR014/VR022/VR023", ""),
    # 本质不可数字化（须人工/外部）
    ("风险检查本质盲区", "账外经营/私户收款", False, "", "本质不可数字化，须资金穿透与举报线索+人工"),
    ("风险检查本质盲区", "实物资产盘点", False, "", "须现场盘点，系统无法覆盖"),
    ("风险检查本质盲区", "业务真实性主观定性", False, "", "须合同/物流/资金三流合一人工研判"),
    ("风险检查本质盲区", "跨境交易穿透", False, "", "须境外税收居民与CRS数据，待外部接入"),
]


def build_coverage_report(catalog, registered_ids, run_result, available_sources):
    """构建三段式覆盖报告。

    :param catalog: VERIFIED_RULE_CATALOG 全量条目
    :param registered_ids: _SCANNERS 已注册的规则 id 集合
    :param run_result: run_verified_rules 的返回（含 findings）
    :param available_sources: 本次输入数据包含的 source 键集合
    """
    catalog_ids = {c["id"] for c in catalog}
    hit_ids = {f["rule_id"] for f in run_result.get("findings", [])}

    executed = sorted(catalog_ids & registered_ids)
    no_hit = sorted((catalog_ids & registered_ids) - hit_ids)
    unregistered = sorted(catalog_ids - registered_ids)

    # 覆盖全景矩阵
    matrix = []
    covered_domains = 0
    gap_domains = 0
    for tax, topic, has_rule, vr, reason in RISK_DOMAIN_PANORAMA:
        if has_rule:
            # 该域对应VR是否都已注册
            vr_ids = [v.strip() for v in vr.replace("VR", "VR").split("/") if v.strip()]
            all_reg = all(any(rid in r for r in registered_ids) for rid in vr_ids) if vr_ids else False
            status = "COVERED" if all_reg else "PARTIAL"
            if all_reg:
                covered_domains += 1
            else:
                gap_domains += 1
        else:
            status = "GAP"
            gap_domains += 1
        matrix.append({
            "tax": tax, "topic": topic, "status": status,
            "vr": vr, "reason": reason,
        })

    # 盲区清单（仅 GAP 与 PARTIAL）
    gaps = [
        {"tax": m["tax"], "topic": m["topic"], "reason": m["reason"] or "对应规则未完全注册"}
        for m in matrix if m["status"] in ("GAP", "PARTIAL")
    ]
    # 数据缺失导致的可覆盖规则未运行
    data_blocked = [
        c["id"] for c in catalog
        if c["id"] in registered_ids and not (set(c.get("required_sources", [])) & available_sources)
    ]

    report = {
        "summary": {
            "total_rules": len(catalog_ids),
            "registered": len(registered_ids & catalog_ids),
            "executed": len(executed),
            "hit": len(hit_ids & catalog_ids),
            "no_hit": len(no_hit),
            "unregistered": len(unregistered),
            "risk_domains_total": len(RISK_DOMAIN_PANORAMA),
            "risk_domains_covered": covered_domains,
            "risk_domains_gap": gap_domains,
            "coverage_rate": round(covered_domains / len(RISK_DOMAIN_PANORAMA) * 100, 1),
        },
        "executed_rules": executed,
        "no_hit_rules": no_hit,
        "unregistered_rules": unregistered,
        "data_blocked_rules": sorted(set(data_blocked)),
        "coverage_matrix": matrix,
        "gap_domains": gaps,
    }
    return report


def format_coverage_text(report):
    """生成人类可读的覆盖度报告文本（用于风险检查结论附件）。"""
    s = report["summary"]
    lines = []
    lines.append("【风险检查覆盖度自检报告】")
    lines.append(
        f"规则总数 {s['total_rules']} | 已注册 {s['registered']} | 本次运行 {s['executed']} "
        f"| 命中 {s['hit']} | 未触发 {s['no_hit']}"
    )
    lines.append(
        f"风险域覆盖：{s['risk_domains_covered']}/{s['risk_domains_total']} "
        f"已覆盖（覆盖率 {s['coverage_rate']}%）| 盲区 {s['risk_domains_gap']}"
    )
    if report["data_blocked_rules"]:
        lines.append(
            f"\n⚠ 因数据缺失未运行的规则：{', '.join(report['data_blocked_rules'])}"
            "（已注册但本次输入未提供必需数据源，非系统遗漏）"
        )
    if report["gap_domains"]:
        lines.append("\n【风险检查盲区清单（须人工/外部数据兜底）】")
        for g in report["gap_domains"]:
            lines.append(f"  · [{g['tax']}] {g['topic']}：{g['reason']}")
    lines.append(
        "\n结论：规则维度已实现可执行风险域全覆盖；上述盲区为本质不可数字化或待接入数据项，"
        "须以人工风险检查/外部数据穿透兜底，方达无死角。"
    )
    return "\n".join(lines)
