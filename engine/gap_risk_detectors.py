"""缺口风险探测器（2026-09-12）

为 audit_coverage.RISK_DOMAIN_PANORAMA 中原本 6 个「待实现」盲区补上
**具体可执行的识别方法**，让这些风险域不只是知识库条目，而是真正能被一键分析检出。

对应红线：
    RL-CIT-005 亏损弥补年限            RL-CIT-006 资产损失税前扣除
    RL-PAY-005 劳务报酬 vs 工资        RL-PAY-006 多处取得/年终奖
    RL-OTH-004 城镇土地使用税          RL-OTH-005 车船税

核心原则（严守系统铁律，绝不越权定性）：
1. 发现≠确认。本模块只产出「待核疑点」或「置疑清单（要求补资料）」，绝不下定性结论。
2. 有数据 → 交叉验证，产出可量化的待核疑点；
   无数据 → 降级为置疑清单，列明需要企业补充的资料，待补齐后再复核。
3. 每个域的识别方法固化在 METHODS 中，报告与审计可追溯「凭什么认为这里有风险」。

数据契约（engine_data，键均可缺省）：
    vouchers         序时账/凭证（含科目、摘要、金额）
    salaries         工资表（含姓名、身份证、项目）
    bank_txs         银行流水
    tax_declarations 纳税申报表（增值税/企业所得税/个税/印花等）
    sal_invs/pur_invs 销项/进项发票
    inventory        库存台账
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Sequence

# ── 识别方法说明（对外可展示，回答"凭什么识别"）────────────────────────────
METHODS: Dict[str, str] = {
    "RL-CIT-005": "检索申报表与序时账中的亏损弥补记录 → 计算弥补年度与亏损发生年度之差 → "
                  "比对法定结转年限（一般5年/高新与科技型中小10年）→ 缺台账则置疑要求补A106000",
    "RL-CIT-006": "检索序时账营业外支出/资产减值损失/固定资产清理等科目 → 汇总账载资产损失 → "
                  "与申报表A105090申报扣除额比对 → 差额或缺失专项申报资料则置疑",
    "RL-PAY-005": "提取工资发放名单与劳务费支付名单 → 按姓名/身份证匹配重复人员 → "
                  "核查劳务报酬个税代扣代缴与合同 → 重名则疑点、无合同无扣缴则置疑",
    "RL-PAY-006": "按身份证号与纳税年度聚合奖金记录 → 统计全年一次性奖金单独计税次数 → "
                  "同一年度超过一次即疑点（政策只允许一次）；缺明细申报则置疑要求补年度汇算记录",
    "RL-OTH-004": "检索序时账土地使用权/房屋建筑物等持有线索 → 检索申报表城镇土地使用税记录 → "
                  "有持有无申报则置疑要求补权证与面积；有申报再比对面积",
    "RL-OTH-005": "检索固定资产运输设备与车辆保险/加油/维修/过路费等用车支出 → "
                  "检索车船税申报或交强险代收记录 → 有车无税则置疑要求补车辆台账与保单",
}


# ── 通用工具 ──────────────────────────────────────────────────────────

def _as_list(value: Any) -> List[Any]:
    """把任意输入统一成列表（None → 空列表）。"""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _dump(records: Any) -> str:
    """把记录集合压成可检索文本（不依赖具体字段名）。"""
    parts: List[str] = []
    for rec in _as_list(records):
        if isinstance(rec, (dict, list)):
            try:
                parts.append(json.dumps(rec, ensure_ascii=False, default=str))
            except Exception:
                parts.append(str(rec))
        else:
            parts.append(str(rec))
    return "\n".join(parts)


def _get_field(rec: Dict, candidates: Sequence[str]) -> str:
    """按候选键名取值（容错不同来源的字段命名差异）。"""
    if not isinstance(rec, dict):
        return ""
    for key in candidates:
        v = rec.get(key)
        if v not in (None, ""):
            return str(v)
    return ""


def _hit(text: str, keywords: Sequence[str]) -> List[str]:
    """返回在文本中命中的关键词列表。"""
    return [k for k in keywords if k and k in text]


def _finding(
    redline_id: str,
    topic: str,
    tax_type: str,
    detail: str,
    level: str,
    score: int,
    needs_material: List[str] = None,
    unconfirmed: bool = False,
    policy_ref: str = "",
    evidence: List[str] = None,
) -> Dict:
    """构造一条待核发现。

    措辞一律为待核/置疑口径，绝不使用定性表述（严守"绝不自动定罪"铁律）。
    """
    return {
        "type": topic,
        "detail": detail,
        "level": level,
        "score": score,
        "tax_type": tax_type,
        "domain": tax_type,
        "policy_ref": policy_ref,
        "suggestion": ("请补充下列资料后复核：" + "、".join(needs_material or []))
        if needs_material else "请就该事项提供说明与佐证资料，以便复核确认。",
        "items": [{"name": m, "status": "待补充"} for m in (needs_material or [])],
        "evidence": evidence or [],
        "needs_material": needs_material or [],
        "_scenario_governed": True,   # ★ 必须打标，否则会被 seal_governed_findings 丢弃（输出封印）
        "redline_id": redline_id,
        "_gap_detector": redline_id,
        "_detection_method": METHODS.get(redline_id, ""),
        "_unconfirmed": unconfirmed,
    }


# ── 六个探测器 ────────────────────────────────────────────────────────

def detect_loss_carryforward(data: Dict) -> List[Dict]:
    """RL-CIT-005 亏损弥补：超期弥补 / 无历年亏损台账。"""
    redline_id = "RL-CIT-005"
    decl_text = _dump(data.get("tax_declarations"))
    vch_text = _dump(data.get("vouchers"))
    all_text = decl_text + "\n" + vch_text

    trigger = _hit(all_text, ["弥补亏损", "亏损弥补", "以前年度亏损", "可弥补亏损", "A106000"])
    if not trigger:
        return []

    # 台账/明细证据
    ledger = _hit(all_text, ["A106000", "弥补亏损明细", "亏损台账", "可弥补亏损额", "结转余额"])
    findings: List[Dict] = []

    if not ledger:
        findings.append(_finding(
            redline_id, "弥补亏损无历年台账支撑（待核）", "企业所得税",
            f"申报或账簿中存在亏损弥补记录（命中：{'、'.join(trigger[:3])}），"
            "但未提供历年汇算清缴亏损台账（A106000）证明可弥补亏损额及所属年度，"
            "无法判断是否存在超期弥补。需补充资料后复核。",
            "低风险", 3,
            needs_material=["历年企业所得税年度纳税申报表", "A106000弥补亏损明细表",
                            "高新技术企业证书（若主张10年结转）"],
            unconfirmed=True, policy_ref="《企业所得税法》第十八条",
            evidence=trigger[:3],
        ))
        return findings

    # 有台账：尝试按年度判断是否超期（5年/10年）
    years = sorted({int(y) for y in re.findall(r"(20\d{2})", all_text)})
    if len(years) >= 2:
        span = years[-1] - years[0]
        limit = 10 if _hit(all_text, ["高新技术", "科技型中小"]) else 5
        if span > limit:
            findings.append(_finding(
                redline_id, "弥补亏损可能超过法定结转年限（待核）", "企业所得税",
                f"资料涉及年度区间为 {years[0]}—{years[-1]}（跨度{span}年），"
                f"超出法定结转年限（当前判定适用{limit}年）。请核实各笔弥补亏损的发生年度"
                "及企业是否具备延长结转年限资格。",
                "中风险", 6,
                needs_material=["历年企业所得税年度纳税申报表", "A106000弥补亏损明细表",
                                "高新技术企业证书或科技型中小企业入库证明"],
                policy_ref="《企业所得税法》第十八条",
                evidence=[f"年度区间 {years[0]}—{years[-1]}", f"适用年限 {limit} 年"],
            ))
    return findings


def detect_asset_loss(data: Dict) -> List[Dict]:
    """RL-CIT-006 资产损失：账载损失未见专项申报。"""
    redline_id = "RL-CIT-006"
    vch_text = _dump(data.get("vouchers"))
    decl_text = _dump(data.get("tax_declarations"))

    loss_kw = ["营业外支出", "资产减值损失", "固定资产清理", "盘亏", "毁损",
               "非常损失", "坏账损失", "存货损失"]
    trigger = _hit(vch_text, loss_kw)
    if not trigger:
        return []

    declared = _hit(decl_text, ["资产损失", "A105090", "专项申报", "清单申报"])
    if declared:
        return []

    return [_finding(
        redline_id, "账载资产损失未见专项申报资料（待核）", "企业所得税",
        f"序时账中存在资产损失类科目记录（命中：{'、'.join(trigger[:4])}），"
        "但纳税申报表中未见资产损失税前扣除（A105090）申报或专项申报资料。"
        "请核实该损失是否已按规定申报，未申报的不得税前扣除。",
        "中风险", 5,
        needs_material=["资产损失专项申报资料", "资产损失鉴证报告（达到标准时）",
                        "盘点表与毁损鉴定报告", "A105090申报表"],
        unconfirmed=True, policy_ref="国家税务总局公告2011年第25号第四条、第五条",
        evidence=trigger[:4],
    )]


def detect_labor_vs_salary(data: Dict) -> List[Dict]:
    """RL-PAY-005 劳务报酬 vs 工资：重名拆分 / 未代扣代缴。"""
    redline_id = "RL-PAY-005"
    salaries = _as_list(data.get("salaries"))
    vch_text = _dump(data.get("vouchers"))
    bank_text = _dump(data.get("bank_txs"))

    labor_kw = ["劳务费", "劳务报酬", "佣金", "提成", "兼职"]
    labor_hit = _hit(vch_text + "\n" + bank_text, labor_kw)
    if not labor_hit:
        return []

    # 工资名单（按姓名/身份证）
    names = set()
    for rec in salaries:
        n = _get_field(rec, ["姓名", "name", "员工姓名", "employee_name", "person_name"])
        if n:
            names.add(n.strip())
        idn = _get_field(rec, ["身份证", "身份证号", "id_card", "id_number", "证件号码"])
        if idn:
            names.add(idn.strip())

    # 在劳务费相关文本中查找是否出现工资名单中的人
    overlap = sorted({n for n in names if n and len(n) >= 2 and n in vch_text})

    if overlap:
        return [_finding(
            redline_id, "同一自然人同时列支工资与劳务报酬（待核）", "个人所得税",
            f"账簿或流水中存在劳务费类支出（命中：{'、'.join(labor_hit[:3])}），"
            f"且工资表人员 {('、'.join(overlap[:5]))} 等同时出现在劳务报酬支付记录中。"
            "请核实所得性质划分是否真实，是否存在拆分收入规避累进税率或社保缴纳义务的情形。",
            "中风险", 6,
            needs_material=["劳务合同", "人员身份证与身份信息", "个税代扣代缴申报表（劳务报酬项目）"],
            policy_ref="《个人所得税法》第二条、第六条",
            evidence=labor_hit[:3] + [f"重叠人员 {len(overlap)} 人"],
        )]

    # 无重名：有劳务费但未见合同/扣缴 → 置疑
    has_contract_or_iit = _hit(_dump(data.get("tax_declarations")) + "\n" + vch_text,
                               ["劳务合同", "劳务报酬所得", "代扣代缴"])
    if not has_contract_or_iit:
        return [_finding(
            redline_id, "劳务报酬支出缺合同与代扣代缴佐证（待核）", "个人所得税",
            f"存在劳务费类支出（命中：{'、'.join(labor_hit[:3])}），"
            "但未见劳务合同与个人所得税代扣代缴佐证。请核实支付对象、所得性质及扣缴义务履行情况。",
            "低风险", 4,
            needs_material=["劳务合同", "人员身份证与身份信息", "个税代扣代缴申报表", "劳务费支付凭证"],
            unconfirmed=True, policy_ref="《个人所得税法》第二条、第六条",
            evidence=labor_hit[:3],
        )]
    return []


def detect_multi_income_bonus(data: Dict) -> List[Dict]:
    """RL-PAY-006 全年一次性奖金单独计税重复使用 / 多处任职。"""
    redline_id = "RL-PAY-006"
    salaries = _as_list(data.get("salaries"))
    decl_text = _dump(data.get("tax_declarations"))
    pay_text = _dump(salaries) + "\n" + decl_text

    bonus_kw = ["全年一次性奖金", "一次性奖金", "年终奖", "年终奖金", "第十三个月工资"]
    bonus_hit = _hit(pay_text, bonus_kw)
    if not bonus_hit:
        return []

    # 统计"单独计税"出现次数（同一纳税年度只允许一次）
    times = len(re.findall(r"单独计税", pay_text)) or 1
    if times > 1:
        return [_finding(
            redline_id, "全年一次性奖金单独计税疑似重复使用（待核）", "个人所得税",
            f"资料中出现全年一次性奖金记录（命中：{'、'.join(bonus_hit[:3])}），"
            f"且'单独计税'标识出现 {times} 次。按政策一个纳税年度内对同一纳税人"
            "只允许采用一次单独计税方式，请核实并重新计算应纳税额。",
            "中风险", 6,
            needs_material=["个税代扣代缴明细申报表", "工资表与奖金发放记录",
                            "综合所得年度汇算清缴记录"],
            policy_ref="财税〔2018〕164号第一条",
            evidence=bonus_hit[:3] + [f"单独计税出现 {times} 次"],
        )]

    # 有奖金但缺个税明细/汇算 → 置疑
    has_iit = _hit(decl_text, ["个人所得税", "个税", "代扣代缴", "综合所得", "年度汇算"])
    if not has_iit:
        return [_finding(
            redline_id, "奖金发放缺个税明细与年度汇算佐证（待核）", "个人所得税",
            f"存在全年一次性奖金类发放记录（命中：{'、'.join(bonus_hit[:3])}），"
            "但未见个人所得税明细申报或年度汇算记录。请补充以核实计税方式与多处任职所得是否已合并。",
            "低风险", 4,
            needs_material=["个税代扣代缴明细申报表", "工资表与奖金发放记录",
                            "年度汇算清缴记录", "人员身份证信息"],
            unconfirmed=True, policy_ref="财税〔2018〕164号第一条",
            evidence=bonus_hit[:3],
        )]
    return []


def detect_land_use_tax(data: Dict) -> List[Dict]:
    """RL-OTH-004 城镇土地使用税：有土地/房产持有线索但无申报。"""
    redline_id = "RL-OTH-004"
    vch_text = _dump(data.get("vouchers"))
    decl_text = _dump(data.get("tax_declarations"))

    hold_kw = ["土地使用权", "无形资产—土地", "无形资产-土地", "房屋建筑物",
               "不动产", "土地出让金", "厂房", "自建厂房"]
    hold_hit = _hit(vch_text, hold_kw)
    if not hold_hit:
        return []

    declared = _hit(decl_text, ["城镇土地使用税", "土地使用税"])
    if declared:
        return []

    return [_finding(
        redline_id, "持有土地或房产但未见城镇土地使用税申报（待核）", "城镇土地使用税",
        f"序时账中存在土地或房产持有线索（命中：{'、'.join(hold_hit[:3])}），"
        "但纳税申报资料中未见城镇土地使用税申报记录。请核实实际占用土地面积与申报情况，"
        "并确认是否存在法定免税情形。",
        "中风险", 5,
        needs_material=["不动产权证或土地使用证", "土地出让合同",
                        "城镇土地使用税申报表", "房产税申报表"],
        unconfirmed=True, policy_ref="《城镇土地使用税暂行条例》第二条、第三条、第四条",
        evidence=hold_hit[:3],
    )]


def detect_vehicle_tax(data: Dict) -> List[Dict]:
    """RL-OTH-005 车船税：有车辆持有/使用线索但无申报或代收。"""
    redline_id = "RL-OTH-005"
    vch_text = _dump(data.get("vouchers"))
    decl_text = _dump(data.get("tax_declarations"))
    bank_text = _dump(data.get("bank_txs"))
    use_text = vch_text + "\n" + bank_text

    veh_kw = ["运输设备", "车辆", "汽车", "加油费", "过路过桥", "过路费",
              "车辆保险", "交强险", "维修费", "洗车"]
    veh_hit = _hit(use_text, veh_kw)
    if not veh_hit:
        return []

    declared = _hit(decl_text + "\n" + vch_text, ["车船税", "代收车船税"])
    if declared:
        return []

    return [_finding(
        redline_id, "存在车辆使用线索但未见车船税缴纳记录（待核）", "车船税",
        f"账簿或流水中存在车辆持有或使用线索（命中：{'、'.join(veh_hit[:3])}），"
        "但未见车船税申报或交强险保单中的代收车船税记录。请核实车辆台账与已缴情况，"
        "并确认是否存在新能源车船免税等法定情形。",
        "中风险", 5,
        needs_material=["车辆登记证与行驶证", "车辆台账", "交强险保单", "车船税完税凭证"],
        unconfirmed=True, policy_ref="《车船税法》第一条、第六条",
        evidence=veh_hit[:3],
    )]


# ── 统一入口 ──────────────────────────────────────────────────────────

DETECTORS = [
    ("RL-CIT-005", detect_loss_carryforward),
    ("RL-CIT-006", detect_asset_loss),
    ("RL-PAY-005", detect_labor_vs_salary),
    ("RL-PAY-006", detect_multi_income_bonus),
    ("RL-OTH-004", detect_land_use_tax),
    ("RL-OTH-005", detect_vehicle_tax),
]


def run_gap_risk_detection(engine_data: Dict, pipeline_log: List[str] = None) -> List[Dict]:
    """执行全部缺口风险探测器。

    返回待核发现列表（只含疑点或置疑请求，绝不含定性结论）。
    任何单个探测器异常都不影响其余探测器执行。
    """
    data = engine_data if isinstance(engine_data, dict) else {}
    results: List[Dict] = []
    for rule_id, func in DETECTORS:
        try:
            found = func(data) or []
        except Exception as exc:  # 单域异常不阻断整体
            if pipeline_log is not None:
                pipeline_log.append(f"[缺口探测器] {rule_id} 执行异常: {exc}")
            found = []
        for item in found:
            item.setdefault("_gap_detector", rule_id)
            item.setdefault("_detection_method", METHODS.get(rule_id, ""))
        results.extend(found)
    if pipeline_log is not None and results:
        pipeline_log.append(
            f"[缺口探测器] 补齐风险域检出 {len(results)} 条待核事项"
            f"（置疑待补资料 {sum(1 for r in results if r.get('_unconfirmed'))} 条）"
        )
    return results
