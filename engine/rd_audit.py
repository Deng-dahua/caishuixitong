# -*- coding: utf-8 -*-
"""研发费用加计扣除风险检查审计引擎

实现 CAN-12-R03 / CAN-17-R01~R03 要求的研发费用合规审计：
1. 研发辅助账解析 — A107012表结构识别与费用分类
2. 研发活动真实性验证 — 项目×人员×成果三重交叉
3. 费用归集合规检查 — 非研发活动混入/人员分摊异常/材料消耗异常
4. 委托/合作研发合规 — 合同备案、费用比例、关联交易
5. 研发支出资本化检查 — 资本化时点、摊销合理性

核心原则（CAN-12 report_boundary）：
研发失败不当然否定研发活动；只产生核验问题，不自行做违法定性。
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict


# ═══════════════════════════════════════════════════
# 基准数据
# ═══════════════════════════════════════════════════

# 可加计扣除的研发费用类别（国家税务总局公告2017年第40号）
RD_EXPENSE_CATEGORIES = {
    "人员人工费用": {
        "code": "A01",
        "description": "直接从事研发活动人员的工资薪金、五险一金、外聘研发人员劳务费",
        "allowable": True,
        "max_ratio": None,  # 无上限但要与人员工时匹配
    },
    "直接投入费用": {
        "code": "A02", 
        "description": "研发活动直接消耗的材料、燃料、动力费用；模具、样品等",
        "allowable": True,
        "max_ratio": 0.4,  # 直接投入通常不超过研发总费用的40%
    },
    "折旧费用": {
        "code": "A03",
        "description": "用于研发活动的仪器、设备、房屋等固定资产的折旧费",
        "allowable": True,
        "max_ratio": None,
    },
    "无形资产摊销": {
        "code": "A04",
        "description": "用于研发活动的软件、专利权、非专利技术的摊销费用",
        "allowable": True,
        "max_ratio": None,
    },
    "设计费": {
        "code": "A05",
        "description": "新产品设计费、新工艺规程制定费",
        "allowable": True,
        "max_ratio": None,
    },
    "装备调试费": {
        "code": "A06",
        "description": "工装准备过程中研究开发活动所发生的费用",
        "allowable": True,
        "max_ratio": None,
    },
    "委托研发费": {
        "code": "A07",
        "description": "委托境内/境外机构或个人进行研发所支付的费用",
        "allowable": True,
        "max_ratio": None,  # 境内80%/境外80%但不超过境内2/3
    },
    "合作研发费": {
        "code": "A08",
        "description": "与境内外机构合作研发按约定比例归集的费用",
        "allowable": True,
        "max_ratio": None,
    },
    "其他相关费用": {
        "code": "A09",
        "description": "技术图书资料费、资料翻译费、专家咨询费、高新科技研发保险费等",
        "allowable": True,
        "max_ratio": 0.10,  # 不超过可加计扣除总额的10%
    },
}

# 不得加计扣除的活动（财税〔2015〕119号）
NON_RD_ACTIVITIES = [
    ("常规升级", "企业产品（服务）的常规性升级"),
    ("直接应用", "对某项科研成果的直接应用（如直接采用公开的新工艺、材料等）"),
    ("商品化支持", "商品化后为顾客提供的技术支持活动"),
    ("重复简单", "对现存产品、服务、技术、材料或工艺流程进行的重复或简单改变"),
    ("市场调研", "市场调查研究、效率调查或管理研究"),
    ("质量控制", "作为工业（服务）流程环节或常规的质量控制、测试分析、维修维护"),
    ("社科艺术", "社会科学、艺术或人文学方面的研究"),
]

# 常见"日常生产混入研发"的红线信号
PRODUCTION_MIXED_SIGNALS = {
    "生产人员": "生产车间人员工资计入研发人工",
    "通用材料": "可用于生产和研发的通用材料全额计入研发（未按用量分摊）",
    "共用设备": "生产与研发共用设备折旧全额计入研发",
    "水电动力": "全厂水电费按比例分摊进研发，无独立计量",
    "批量异常": "研发领料量远超研发试制合理用量（>正常批量的3倍）",
}


def audit_rd_deduction(
    rd_data: Optional[Dict] = None,
    invoices: Optional[List] = None,
    salaries: Optional[List] = None,
    target_entity: Optional[Dict] = None,
    pipeline_log: Optional[List] = None,
) -> List[Dict]:
    """研发费用加计扣除风险检查审计主入口
    
    Args:
        rd_data: 解析后的研发辅助账数据（来自_parse_rd_aux_ledger）
        invoices: 所有发票列表（含进项/销项）
        salaries: 工资数据
        target_entity: 被查单位信息
        pipeline_log: 流水日志
    
    Returns:
        结构化发现列表，每条含 type/level/score/detail/description/suggestion
    """
    findings = []
    
    if pipeline_log is None:
        pipeline_log = []
    
    # ═══ 无研发辅助账 → 无法审计 ═══
    if not rd_data or not rd_data.get("projects"):
        findings.append({
            "type": "研发费用加计扣除-无辅助账数据",
            "level": "待补资料", "score": 0,
            "detail": "未上传研发费用辅助账（A107012表或等效数据），无法执行的研发费用审计。",
            "description": "企业可能享受了研发加计扣除但未提供辅助账数据。建议上传研发费用辅助账或A107012表以进行合规审计。",
            "suggestion": "上传研发辅助账（含项目名称、费用类别、金额、人员等信息）。",
            "category": "研发费加计扣除",
        })
        return findings
    
    projects = rd_data.get("projects", [])
    total_rd = rd_data.get("total_rd_expense", 0)
    
    # ═══ 1. 研发概况 ═══
    findings.append({
        "type": "研发费用加计扣除-概况",
        "level": "信息", "score": 2,
        "detail": f"识别到{len(projects)}个研发项目，研发费用合计{total_rd:,.0f}元。",
        "description": f"被查单位申报了{len(projects)}个研发项目（{'、'.join(p.get('name','')[:15] for p in projects[:5])}），研发费用总计{total_rd:,.0f}元。以下逐项审计合规性。",
        "category": "研发费加计扣除",
    })
    
    # ═══ 2. 费用类别合理性检查 ═══
    _check_expense_categories(findings, rd_data)
    
    # ═══ 3. 逐一项目审计 ═══
    for proj in projects:
        _audit_single_project(findings, proj, invoices, salaries, target_entity)
    
    # ═══ 4. 人员费用交叉验证 ═══
    if salaries and any(p.get("personnel") for p in projects):
        _cross_verify_personnel(findings, projects, salaries)
    
    # ═══ 5. 委托研发检查 ═══
    _check_outsourced_rd(findings, rd_data, invoices)
    
    # ═══ 6. 资本化检查 ═══
    _check_capitalization(findings, rd_data)
    
    # ═══ 7. 加计扣除金额复算 ═══
    _recalculate_deduction(findings, rd_data)
    
    pipeline_log.append(f"[研发审计] {len(findings)}条发现")
    return findings


def _check_expense_categories(findings, rd_data):
    """费用类别分布合理性检查"""
    projects = rd_data.get("projects", [])
    
    # 汇总全部项目的费用分类
    cat_totals = defaultdict(float)
    for proj in projects:
        for cat, amount in (proj.get("categories", {})).items():
            cat_totals[cat] += amount
    
    total = sum(cat_totals.values())
    if total == 0:
        return
    
    # 其他相关费用不超过10%检查
    other = cat_totals.get("其他相关费用", 0)
    if other > 0:
        other_pct = other / total
        if other_pct > 0.10:
            findings.append({
                "type": "研发费加计扣除-其他费用超标",
                "level": "中风险", "score": 6,
                "detail": f"其他相关费用{other:,.0f}元，占研发总额{other_pct*100:.1f}%，超出10%上限。",
                "description": f"根据财税〔2015〕119号，其他相关费用不得超过可加计扣除研发费用总额的10%。超出的{(other - total * 0.10):,.0f}元不得加计扣除。",
                "tax_impact": f"超出部分不得加计扣除，需调增应纳税所得额约{(other - total * 0.10):,.0f}元。",
                "suggestion": "将超出10%部分的费用剔除出加计扣除范围，或重新核实费用分类。",
                "policy_ref": "财税〔2015〕119号",
                "category": "研发费加计扣除",
            })
    
    # 直接投入费用占比异常（>40%触发）
    direct_input = cat_totals.get("直接投入费用", 0)
    if direct_input > 0 and direct_input / total > 0.40:
        findings.append({
            "type": "研发费加计扣除-直接投入占比过高",
            "level": "中风险", "score": 5,
            "detail": f"直接投入费用{direct_input:,.0f}元，占研发总额{direct_input/total*100:.1f}%，可能混合了生产领料。",
            "description": f"研发直接投入占比{direct_input/total*100:.1f}%偏高（正常不超过40%）。需核实是否存在生产领料混入研发费用或研发试制材料用量异常。",
            "suggestion": "逐项核验直接投入的领料单、材料用途和实际消耗量，剔除生产性领用。",
            "category": "研发费加计扣除",
        })
    
    # 人员人工费用占比异常（<30%触发——软企应该高，制造可能低但不应太低）
    personnel = cat_totals.get("人员人工费用", 0)
    if personnel > 0 and personnel / total < 0.20:
        findings.append({
            "type": "研发费加计扣除-人员费用占比过低",
            "level": "中风险", "score": 5,
            "detail": f"人员人工费用{personnel:,.0f}元，仅占研发总额{personnel/total*100:.1f}%，研发活动缺乏人力支撑。",
            "description": f"真实研发活动以人力投入为核心。人员费用占比过低({personnel/total*100:.1f}%)可能意味着：①大量生产/运维人员被计入制造费用而非研发人工；②研发活动主要为外包采购（实质为委托研发）；③研发费用归集不当。",
            "suggestion": "核实研发人员名单、工时分配和工资归集，确保全部直接研发人员的人工费用已正确归入研发。",
            "category": "研发费加计扣除",
        })


def _audit_single_project(findings, proj, invoices, salaries, target_entity):
    """单个研发项目的完整审计"""
    proj_name = proj.get("name", "未命名项目")
    proj_categories = proj.get("categories", {})
    proj_total = sum(proj_categories.values())
    proj_personnel = proj.get("personnel", [])
    proj_outputs = proj.get("outputs", [])
    
    if proj_total == 0:
        return
    
    # ═══ 项目产出检查 ═══
    if not proj_outputs:
        findings.append({
            "type": "研发费加计扣除-项目无产出",
            "level": "中风险", "score": 5,
            "detail": f"研发项目'{proj_name}'投入{proj_total:,.0f}元但无任何产出记录（专利/软著/新产品/新工艺等）。",
            "description": f"项目'{proj_name}'研发费用{proj_total:,.0f}元，但没有对应的专利、软著、新产品、新工艺等研发产出。研发失败本身不否定研发活动，但需保留研发过程记录（实验记录、测试报告、失败分析等）作为证据。",
            "suggestion": f"提供'{proj_name}'的研发过程记录（立项书/实验记录/测试报告/阶段性成果），即使项目失败也应保留完整档案。",
            "policy_ref": "财税〔2015〕119号；研发失败项目仍可享受加计扣除",
            "category": "研发费加计扣除",
        })
    
    # ═══ 项目人员检查 ═══
    if proj_total > 500000 and not proj_personnel:
        findings.append({
            "type": "研发费加计扣除-项目无人员",
            "level": "高风险", "score": 8,
            "detail": f"研发项目'{proj_name}'总费用{proj_total:,.0f}元但没有列出任何研发人员——谁在做研发？",
            "description": f"项目'{proj_name}'投入超50万元却无对应研发人员。一项真实的研发活动必然有人员投入。无人员记录可能意味着：①费用归集错误（非研发费用归入了研发）；②人员记录不全；③虚假研发项目。",
            "tax_impact": "虚假研发项目→不得享受加计扣除→补税+滞纳金+罚款。",
            "suggestion": f"立即补充'{proj_name}'的研发人员名单及工时记录。",
            "category": "研发费加计扣除",
        })
    
    # ═══ 生产混入研发检查 ═══
    for signal_name, signal_desc in PRODUCTION_MIXED_SIGNALS.items():
        if signal_name in str(proj.get("notes", "")) or signal_name in str(proj.get("categories", {})):
            findings.append({
                "type": "研发费加计扣除-生产混入研发",
                "level": "高风险", "score": 9,
                "detail": f"项目'{proj_name}'存在{signal_desc}风险。",
                "description": f"检测到项目'{proj_name}'可能存在{signal_desc}。这是最常见的研发加计扣除造假手段——将日常生产和运营费用包装成研发费用以骗取加计扣除。",
                "tax_impact": "非研发活动的费用不得加计扣除→补税+滞纳金+50%-5倍罚款。",
                "suggestion": "重新核定研发费用范围，剔除不属于研发活动的费用。建立独立的研发领料、设备使用和人员工时记录。",
                "category": "研发费加计扣除",
            })
            break  # 每个项目最多报一个混入信号


def _cross_verify_personnel(findings, projects, salaries):
    """研发人员工资与全员工资交叉验证"""
    # 汇总所有研发项目中的人员
    all_rd_personnel = set()
    for proj in projects:
        for p in proj.get("personnel", []):
            if isinstance(p, dict):
                name = p.get("name", "")
            else:
                name = str(p)
            if name:
                all_rd_personnel.add(name)
    
    if not all_rd_personnel:
        return
    
    # 从工资表中提取所有员工
    all_employees = set()
    for s in salaries:
        name = s.get("name", s.get("姓名", ""))
        if name:
            all_employees.add(str(name).strip())
    
    # 研发人员不在工资表中
    missing_from_payroll = all_rd_personnel - all_employees
    if missing_from_payroll:
        findings.append({
            "type": "研发费加计扣除-研发人员无工资记录",
            "level": "中风险", "score": 6,
            "detail": f"{len(missing_from_payroll)}名研发人员不在工资表中：{'、'.join(list(missing_from_payroll)[:5])}。",
            "description": f"研发项目中列出的{len(missing_from_payroll)}人未在工资表中找到。可能原因：①外聘研发人员未在常规工资表中；②研发人员工资单独发放未合并；③虚构研发人员。",
            "suggestion": "核实研发人员身份：内部员工应出现在工资表中，外部人员应有劳务合同和个税代扣记录。",
            "category": "研发费加计扣除",
        })
    
    # 工资表人数与研发人员比例
    if all_employees:
        rd_ratio = len(all_rd_personnel & all_employees) / max(len(all_employees), 1)
        if rd_ratio > 0.6:
            findings.append({
                "type": "研发费加计扣除-研发人员占比畸高",
                "level": "中风险", "score": 5,
                "detail": f"研发人员占全员{rd_ratio*100:.1f}%，超出正常水平。",
                "description": f"研发人员占全部员工{rd_ratio*100:.1f}%（超过60%）。即使是纯研发型企业，也需要行政、人事、财务、销售等支持人员。过高比例可能意味着非研发人员也被计入了研发费用。",
                "suggestion": "逐人核实研发人员的工作内容和工时记录，确保只有直接从事研发活动的人员才归入研发人工。",
                "category": "研发费加计扣除",
            })


def _check_outsourced_rd(findings, rd_data, invoices):
    """委托研发和合作研发合规检查"""
    projects = rd_data.get("projects", [])
    
    for proj in projects:
        outsourced = proj.get("outsourced_rd", [])
        if not outsourced:
            continue
        
        for item in outsourced:
            if isinstance(item, dict):
                partner = item.get("partner", "未指明")
                amount = item.get("amount", 0)
                contract = item.get("contract", "")
                is_related = item.get("is_related_party", False)
            else:
                continue
            
            # 境内委托扣除比例检查
            if amount > 0:
                allowable = amount * 0.80
                findings.append({
                    "type": "研发费加计扣除-委托研发扣除限制",
                    "level": "信息", "score": 3,
                    "detail": f"项目'{proj.get('name','')}'委托{partner}研发{amount:,.0f}元，按80%计算可加计{allowable:,.0f}元。",
                    "description": f"根据财税〔2015〕119号，企业委托境内机构或个人进行研发活动所发生的费用，按照费用实际发生额的80%计入委托方研发费用并加计扣除。",
                    "suggestion": "确认委托研发合同已在科技部门登记备案。",
                    "category": "研发费加计扣除",
                })
            
            # 关联方委托
            if is_related:
                findings.append({
                    "type": "研发费加计扣除-关联方委托研发",
                    "level": "中风险", "score": 6,
                    "detail": f"项目'{proj.get('name','')}'委托关联方{partner}研发{amount:,.0f}元，需核验定价是否公允。",
                    "description": f"委托关联方进行研发活动，必须提供研发项目费用支出明细，并保证交易价格符合独立交易原则。否则可能被认定为利润转移。",
                    "suggestion": "提供关联方委托研发的费用明细和独立交易定价依据。",
                    "policy_ref": "国家税务总局公告2017年第40号",
                    "category": "研发费加计扣除",
                })


def _check_capitalization(findings, rd_data):
    """研发支出资本化检查"""
    projects = rd_data.get("projects", [])
    
    for proj in projects:
        capitalized = proj.get("capitalized_amount", 0)
        if not capitalized:
            continue
        
        cap_date = proj.get("cap_date", "")
        proj_name = proj.get("name", "")
        
        findings.append({
            "type": "研发费加计扣除-资本化处理",
            "level": "信息", "score": 3,
            "detail": f"项目'{proj_name}'已将{capitalized:,.0f}元研发支出资本化（{cap_date}），形成无形资产。",
            "description": f"研发支出资本化后形成无形资产，按无形资产成本的200%在税前摊销（制造业/科技型中小企业为220%）。注意：资本化时点的判断（研究阶段→开发阶段）是常见争议点。",
            "tax_impact": "资本化时点判断错误→可能提前摊销→少缴当期所得税。",
            "suggestion": f"确认'{proj_name}'满足资本化五项条件（技术可行性/完成意图/产生经济利益/资源支持/可靠计量），保留资本化判断依据。",
            "category": "研发费加计扣除",
        })


def _recalculate_deduction(findings, rd_data):
    """加计扣除金额复算"""
    projects = rd_data.get("projects", [])
    declared_deduction = rd_data.get("declared_deduction", 0)
    industry = rd_data.get("industry", "")
    
    # 计算实际可加计金额
    total_allowable = 0
    for proj in projects:
        cats = proj.get("categories", {})
        proj_total = sum(cats.values())
        
        # 扣除其他费用超10%部分
        other = cats.get("其他相关费用", 0)
        if other > 0:
            # 其他费用限额 = (总额 - 其他费用) * 10% / 90%
            non_other = proj_total - other
            other_limit = non_other * 0.10 / 0.90
            if other > other_limit:
                proj_total -= (other - other_limit)
        
        # 委托研发按80%计
        for item in proj.get("outsourced_rd", []):
            amt = item.get("amount", 0) if isinstance(item, dict) else 0
            if amt > 0:
                proj_total = proj_total - amt + amt * 0.80
        
        total_allowable += proj_total
    
    # 加计比例
    is_manufacturing = any(k in (industry or "").upper() for k in ["C", "制造"])
    is_sme_tech = any(k in (industry or "") for k in ["科技", "软件", "信息技术"])
    deduction_rate = 1.0  # 一般企业100%
    if is_manufacturing or is_sme_tech:
        deduction_rate = 1.0  # 实际也是100%（政策调整后）
    
    calculated_deduction = total_allowable * deduction_rate
    
    if declared_deduction > 0 and total_allowable > 0:
        diff = abs(declared_deduction - calculated_deduction)
        diff_pct = diff / max(calculated_deduction, 1)
        
        if diff_pct > 0.05:
            findings.append({
                "type": "研发费加计扣除-申报金额偏差",
                "level": "中风险" if diff_pct < 0.15 else "高风险",
                "score": 6 if diff_pct < 0.15 else 9,
                "detail": f"申报加计扣除{declared_deduction:,.0f}元，系统复算{calculated_deduction:,.0f}元，偏差{diff_pct*100:.1f}%。",
                "description": f"基于研发辅助账数据复算的加计扣除金额与申报金额偏差{diff_pct*100:.1f}%。需逐项核对差异原因。",
                "tax_impact": "超申报部分不得加计扣除，少申报部分可在汇算清缴期前调整。",
                "suggestion": "逐项核对辅助账与申报表（A107012表），定位差异来源。",
                "category": "研发费加计扣除",
            })
    
    findings.append({
        "type": "研发费加计扣除-复算结果",
        "level": "信息", "score": 2,
        "detail": f"可加计扣除研发费用合计{total_allowable:,.0f}元，加计扣除{calculated_deduction:,.0f}元。",
        "category": "研发费加计扣除",
    })
