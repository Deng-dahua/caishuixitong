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
    ("增值税", "出口退税违规", True, "RL-SPT-008", "需报关单/收汇/产能数据方可定性；缺数据时按置疑清单要求补充"),
    # 企业所得税
    ("企业所得税", "收入确认时点", True, "VR001/VR002/VR018", ""),
    ("企业所得税", "业务招待费超限", True, "VR038", ""),
    ("企业所得税", "广告费超限", True, "VR039", ""),
    ("企业所得税", "福利费超限", True, "VR040", ""),
    ("企业所得税", "折旧摊销异常", True, "VR041", ""),
    ("企业所得税", "成本费用虚列", True, "VR034", ""),
    ("企业所得税", "关联方转让定价", True, "VR037", "需工商股权穿透数据支撑定性"),
    ("企业所得税", "亏损弥补年限", True, "RL-CIT-005", "定性需历年汇算清缴A106000台账；缺台账时降级为置疑清单要求补充"),
    ("企业所得税", "资产损失税前扣除", True, "RL-CIT-006", "定性需A105090与专项申报资料；缺资料时降级为置疑清单要求补充"),
    # 个人所得税
    ("个人所得税", "工资社保差异", True, "VR005", ""),
    ("个人所得税", "股东借款视同分红", True, "VR030", ""),
    ("个人所得税", "劳务报酬 vs 工资", True, "RL-PAY-005", "定性需劳务合同与人员身份信息；缺数据时降级为置疑清单要求补充"),
    ("个人所得税", "多处取得/年终奖", True, "RL-PAY-006", "定性需个税明细申报与年度汇算记录；缺数据时降级为置疑清单要求补充"),
    # 财产税与行为税
    ("印花税", "购销合同计税依据", True, "VR031", ""),
    ("印花税", "借款/租赁合同等其他税目", True, "VR035", ""),
    ("房产税", "从价/从租计征", True, "VR042", ""),
    ("城建税及附加", "随增值税附征", True, "VR043", ""),
    ("城镇土地使用税", "实际占用土地面积", True, "RL-OTH-004", "定性需土地权证与面积数据；缺权证时降级为置疑清单要求补充"),
    ("车船税", "自有车辆船舶", True, "RL-OTH-005", "定性需车辆台账与交强险保单；缺台账时降级为置疑清单要求补充"),
    # ── 特定税种（P1-2 补齐 RL-SPT-001~011 后同步入全景）──
    ("土地增值税", "未清算或扣除项目不实", True, "RL-SPT-001", ""),
    ("消费税", "应税消费品未申报或计税价格偏低", True, "RL-SPT-002", ""),
    ("资源税", "未申报或销售量与产量不符", True, "RL-SPT-003", ""),
    ("环境保护税", "直接排放应税污染物未申报", True, "RL-SPT-004", ""),
    ("关税", "进口货物完税价格申报不实", True, "RL-SPT-005", ""),
    ("非居民企业所得税", "境内所得未履行源泉扣缴", True, "RL-SPT-006", ""),
    ("契税", "承受土地房屋权属未申报", True, "RL-SPT-007", ""),
    ("个人所得税", "股权转让价格明显偏低且无正当理由", True, "RL-SPT-009", ""),
    ("住房公积金", "未开户/未全员缴存/缴存基数不实", True, "RL-SPT-010", ""),
    ("征收管理", "不符合核定征收条件而适用核定征收", True, "RL-SPT-011", ""),
    # ── 2026-09-30 补齐：其余盲区红线（专项/缺口探测器已实装，运行期 declared 归位）──
    ("存货", "账实不符（盘盈亏）", True, "RL-INV-001", "定性需进销存台账与盘点表；缺资料时降级为置疑清单"),
    ("存货", "存货长期不动销", True, "RL-INV-002", "定性需进销存台账与跌价判断；缺资料时降级为置疑清单"),
    ("存货", "投入产出不匹配", True, "RL-INV-003", "定性需BOM/领料/完工单据；缺资料时降级为置疑清单"),
    ("企业所得税", "其他应付款大额长期挂账", True, "RL-INC-004", "定性需其他应付款明细与借款合同；缺资料时降级为置疑清单"),
    ("企业所得税", "暂估成本长期挂账无发票冲回", True, "RL-COST-001", "定性需暂估科目与进项发票；缺资料时降级为置疑清单"),
    ("企业所得税", "关联方无偿/低价资金往来", True, "RL-CIT-002", "定性需资金拆借协议与同期利率；缺资料时降级为置疑清单"),
    ("企业所得税", "研发费用加计扣除归集异常", True, "RL-CIT-003", "定性需研发辅助账与立项工时；缺资料时降级为置疑清单"),
    ("企业所得税", "政府补助与收益确认纳税调整", True, "RL-AST-002", "定性需政府补助文件与不征税收入三条件；缺资料时降级为置疑清单"),
    ("个人所得税", "股东借款年末未归还", True, "RL-FUND-003", "定性需其他应收款明细与借款用途；缺资料时降级为置疑清单"),
    ("个人所得税", "劳务报酬与工资薪金混淆", True, "RL-PAY-004", "定性需劳务合同与人员身份；缺资料时降级为置疑清单"),
    ("增值税", "价外费用未并入销售额", True, "RL-VAT-009", "定性需合同价外条款与收款凭证；缺资料时降级为置疑清单"),
    ("增值税", "大额现金收付", True, "RL-FUND-004", "定性需现金日记账与银行流水印证；缺资料时降级为置疑清单"),
    ("房产税", "持有房产土地未申报房产税/土地使用税", True, "RL-OTH-002", "定性需固定资产明细与房产税申报；缺资料时降级为置疑清单"),
    # ── 2026-09-30 补齐：6 类小微税种/费义务登记红线（运行期 declared 归位）──
    ("文化事业建设费", "广告/娱乐服务未申报文化事业建设费", True, "RL-SPT-017", "定性需广告/娱乐服务收入台账与文建费申报；缺资料时降级为置疑清单"),
    ("车辆购置税", "购置应税车辆未申报车辆购置税", True, "RL-SPT-018", "定性需固定资产车辆明细与完税证明；缺资料时降级为置疑清单"),
    ("耕地占用税", "占用耕地未申报耕地占用税", True, "RL-SPT-014", "定性需农用地转用文件与占地资料；缺资料时降级为置疑清单"),
    ("烟叶税", "收购烟叶未申报烟叶税", True, "RL-SPT-015", "定性需烟叶收购凭证与台账；缺资料时降级为置疑清单"),
    ("船舶吨税", "自有/使用船舶未申报船舶吨税", True, "RL-SPT-016", "定性需船舶登记与进出境记录；缺资料时降级为置疑清单"),
    ("增值税", "留抵退税真实性存疑", True, "RL-VAT-013", "定性需进项全量明细与留抵退税核准资料；缺资料时降级为置疑清单"),
    # 数据质量与勾稽
    ("数据质量", "发票/存货/资金勾稽", True, "VR003-VR025", ""),
    ("生产实质", "能耗/投入产出/人员", True, "VR014/VR022/VR023", ""),
    # 本质不可数字化（须人工/外部）
    ("风险检查本质盲区", "账外经营/私户收款", False, "", "本质不可数字化，须资金穿透与举报线索+人工"),
    ("风险检查本质盲区", "实物资产盘点", False, "", "须现场盘点，系统无法覆盖"),
    ("风险检查本质盲区", "业务真实性主观定性", False, "", "须合同/物流/资金三流合一人工研判"),
    ("风险检查本质盲区", "跨境交易穿透", False, "", "须境外税收居民与CRS数据，待外部接入"),
]


def build_coverage_report(catalog, registered_ids, run_result, available_sources, redline_ids=None):
    """构建三段式覆盖报告。

    :param catalog: VERIFIED_RULE_CATALOG 全量条目
    :param registered_ids: _SCANNERS 已注册的规则 id 集合
    :param run_result: run_verified_rules 的返回（含 findings）
    :param available_sources: 本次输入数据包含的 source 键集合
    :param redline_ids: 税务红线 id 集合（RL-* 前缀的域按红线库判定，缺省自动加载）
    """
    catalog_ids = {c["id"] for c in catalog}
    hit_ids = {f["rule_id"] for f in run_result.get("findings", [])}
    if redline_ids is None:
        try:
            from engine.tax_redlines import REDLINES as _REDLINES
            redline_ids = {str(r.get("id", "")) for r in _REDLINES}
        except Exception:
            redline_ids = set()

    executed = sorted(catalog_ids & registered_ids)
    no_hit = sorted((catalog_ids & registered_ids) - hit_ids)
    unregistered = sorted(catalog_ids - registered_ids)

    # 覆盖全景矩阵
    matrix = []
    covered_domains = 0
    gap_domains = 0
    for tax, topic, has_rule, vr, reason in RISK_DOMAIN_PANORAMA:
        if has_rule:
            # 分流：VR-* 按已注册扫描器判定，RL-* 按税务红线库判定
            ids = [v.strip() for v in vr.split("/") if v.strip()]
            vr_ids = [v for v in ids if v.upper().startswith("VR")]
            rl_ids = [v for v in ids if v.upper().startswith("RL-")]
            if not ids:
                all_reg = False
            else:
                vr_ok = all(any(v in r for r in registered_ids) for v in vr_ids) if vr_ids else True
                rl_ok = all(v in redline_ids for v in rl_ids) if rl_ids else True
                all_reg = vr_ok and rl_ok
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
    # 结论按实际盲区动态表述：区分「待接入/待实现」与「本质不可数字化」，
    # 杜绝无条件下「已实现全覆盖」的过度声明。
    gaps = report.get("gap_domains", []) or []
    inherent = [g for g in gaps if g.get("tax") == "风险检查本质盲区"]
    pending = [g for g in gaps if g.get("tax") != "风险检查本质盲区"]
    if not gaps:
        lines.append("\n结论：规则维度已实现可执行风险域全覆盖，本次无盲区。")
    else:
        lines.append(
            f"\n结论：规则维度覆盖 {s['risk_domains_covered']}/{s['risk_domains_total']}"
            f"（{s['coverage_rate']}%）；尚有 {len(gaps)} 个盲区——"
            f"{len(pending)} 个为待接入外部数据或待实现，{len(inherent)} 个为本质不可数字化。"
        )
        lines.append(
            "「待接入/待实现」项须补数据或补规则方能覆盖；「本质不可数字化」项"
            "须以人工风险检查/外部数据穿透兜底。当前未达无死角，不得对外宣称已覆盖全部税务风险。"
        )
    return "\n".join(lines)
