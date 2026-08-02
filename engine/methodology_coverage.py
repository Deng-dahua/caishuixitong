# -*- coding: utf-8 -*-
"""稽查方法论覆盖矩阵与规则资产质量审计。"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from engine.candidate_rule_governance import build_candidate_governance
from engine.verified_rule_engine import VERIFIED_RULE_CATALOG


INDUSTRIES = [
    ("A", "农、林、牧、渔业", ("农业", "林业", "畜牧", "渔业", "农产品", "种植", "养殖")),
    ("B", "采矿业", ("采矿", "矿业", "煤炭", "油气", "矿产", "资源开采")),
    ("C", "制造业", ("制造业", "生产企业", "工厂", "BOM", "产能", "委外加工")),
    ("D", "电力、热力、燃气及水生产和供应业", ("电力", "热力", "燃气", "水务", "供水", "能源供应")),
    ("E", "建筑业", ("建筑", "施工", "工程项目", "分包", "甲供", "异地项目")),
    ("F", "批发和零售业", ("批发", "零售", "商贸", "电商", "进销存", "平台销售")),
    ("G", "交通运输、仓储和邮政业", ("运输", "物流", "仓储", "邮政", "货运", "车辆", "船舶")),
    ("H", "住宿和餐饮业", ("住宿", "酒店", "餐饮", "饭店", "客房", "桌台")),
    ("I", "信息传输、软件和信息技术服务业", ("软件", "信息技术", "互联网", "平台", "云服务", "数字服务")),
    ("J", "金融业", ("金融业", "金融机构", "商业银行", "保险业", "证券", "资管")),
    ("K", "房地产业", ("房地产", "开发项目", "预售", "土地增值税", "商品房", "车位")),
    ("L", "租赁和商务服务业", ("租赁", "商务服务", "人力资源", "代理", "居间", "咨询")),
    ("M", "科学研究和技术服务业", ("科研", "研发", "技术服务", "检验检测", "知识产权", "专业服务")),
    ("N", "水利、环境和公共设施管理业", ("水利", "环境", "环保", "公共设施", "污水", "垃圾处理")),
    ("O", "居民服务、修理和其他服务业", ("居民服务", "维修", "修理", "家政", "美容", "生活服务")),
    ("P", "教育", ("教育", "培训", "学校", "学费", "课时", "民办教育")),
    ("Q", "卫生和社会工作", ("医疗", "医院", "医药", "卫生", "社会工作", "医保", "药品")),
    ("R", "文化、体育和娱乐业", ("文化", "体育", "娱乐", "演出", "直播", "票务", "版权")),
    ("S", "公共管理、社会保障和社会组织", ("社会组织", "事业单位", "协会", "基金会", "公共管理", "会费", "捐赠")),
    ("T", "国际组织", ("国际组织", "驻华代表机构", "国际机构")),
]

TAXES = [
    ("VAT", "增值税", ("增值税", "进项", "销项", "发票", "应税交易")),
    ("CIT", "企业所得税", ("企业所得税", "税前扣除", "应纳税所得额", "汇算清缴")),
    ("IIT", "个人所得税", ("个人所得税", "个税", "代扣代缴", "工资薪金")),
    ("CT", "消费税", ("消费税", "应税消费品")),
    ("SUR", "附加税费", ("城市维护建设税", "教育费附加", "地方教育附加", "附加税")),
    ("PROPERTY", "财产行为税", ("房产税", "土地使用税", "印花税", "契税", "土地增值税", "车船税", "车辆购置税", "耕地占用税")),
    ("RESOURCE", "资源环境税", ("资源税", "环境保护税", "环保税", "烟叶税")),
    ("EXPORT", "出口退（免）税", ("出口退税", "退（免）税", "报关", "收汇")),
    ("CROSS", "跨境与非居民", ("跨境", "非居民", "常设机构", "转让定价", "关联申报", "受益所有人")),
    ("BENEFIT", "优惠与退抵税", ("税收优惠", "减免税", "退税", "加计扣除", "高新技术")),
    ("SOCIAL", "社会保险费与非税收入", ("社会保险", "社保", "文化事业建设费", "非税收入")),
]

LIFECYCLES = [
    ("L01", "设立登记与主体资格", ("工商登记", "税务登记", "纳税人资格", "实际控制人", "注销")),
    ("L02", "资本投入与融资", ("资本", "出资", "借款", "融资", "股东投入")),
    ("L03", "采购与取得", ("采购", "供应商", "进项", "取得发票")),
    ("L04", "生产、加工与服务交付", ("生产", "加工", "产能", "服务交付", "履约")),
    ("L05", "存货、物流与资产", ("存货", "库存", "物流", "固定资产", "无形资产")),
    ("L06", "销售与收入确认", ("销售", "收入", "客户", "合同履约")),
    ("L07", "开票、红冲与用途确认", ("开票", "发票", "红冲", "用途确认")),
    ("L08", "收付款与资金结算", ("收款", "付款", "资金", "银行", "账户")),
    ("L09", "用工、薪酬与扣缴", ("工资", "薪酬", "人员", "劳务", "个税", "社保")),
    ("L10", "会计核算与期末结转", ("凭证", "账簿", "科目", "报表", "结转")),
    ("L11", "申报、缴纳与优惠", ("申报", "缴纳", "优惠", "退税", "汇算")),
    ("L12", "重组、关联与跨境", ("重组", "关联", "跨境", "非居民", "转让定价")),
]

DATA_CAPABILITIES = [
    {"source": "主体登记与关联关系", "state": "部分结构化", "use": "主体、资格、股权和期间锚定", "boundary": "实际控制和关联关系仍需文件及人工核验"},
    {"source": "税费申报、缴纳和优惠资料", "state": "部分结构化", "use": "申报口径和税费事项勾稽", "boundary": "不同税费表单和历史期间字段仍需专项契约"},
    {"source": "数电及其他发票资料", "state": "已结构化", "use": "票面、购销、金额税额和时间分析", "boundary": "用途确认、红冲轨迹和业务标签取决于合法导出字段"},
    {"source": "总账、明细账、凭证和科目余额", "state": "已结构化", "use": "税会勾稽、科目穿透和会计质量", "boundary": "会计科目映射和辅助核算需要企业口径"},
    {"source": "银行和资金结算", "state": "已结构化", "use": "收付、余额、对手方和期间勾稽", "boundary": "款项性质不能由资金方向自动判断"},
    {"source": "合同、订单和履约成果", "state": "部分解析", "use": "权利义务、时点、主体和价款条件", "boundary": "非标准文本和附件需要人工确认关键条款"},
    {"source": "存货、出入库和物流", "state": "部分结构化", "use": "数量滚动、账实和进销关系", "boundary": "仓库、单位换算、在途和合理损耗字段需补齐"},
    {"source": "工资、个税和社会保险", "state": "已结构化", "use": "人员范围和支付口径协同", "boundary": "人员身份、属期、异地参保和所得性质需复核"},
    {"source": "固定资产、无形资产和项目台账", "state": "部分结构化", "use": "取得、使用、折旧摊销和处置", "boundary": "资产卡片与会计税务口径的稳定契约尚待完善"},
    {"source": "产量、能耗、设备和BOM", "state": "待行业接入", "use": "制造、采矿和公用事业投入产出", "boundary": "不同工艺不可共用固定行业阈值"},
    {"source": "平台订单、支付、退款和佣金", "state": "待平台接入", "use": "平台经济交易全周期", "boundary": "须确认平台角色、合法授权和字段语义"},
    {"source": "海关、外汇、物流和境外单证", "state": "依法条件接入", "use": "进出口、收汇和跨境履约", "boundary": "无合法来源和权限时不得推断或模拟"},
    {"source": "市场监管、不动产、社保及其他外部资料", "state": "依法条件接入", "use": "主体、资产、人员和权属协同", "boundary": "只在权限、批准、来源和用途明确时使用"},
]


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _normalise(value):
    return re.sub(r"[\W_\d]+", "", str(value or "")).lower()


def _signature(chain):
    return tuple((step.get("op"), step.get("source"), tuple(sorted((step.get("filters") or {}).keys()))) for step in chain.get("steps", []))


def _matrix(rows, dimensions, text_getter):
    matrix = []
    for code, name, keywords in dimensions:
        count = sum(any(keyword in text_getter(row) for keyword in keywords) for row in rows)
        verified_applicable = sum(
            "ALL" in spec.get("industries", []) or code in spec.get("industries", [])
            for spec in VERIFIED_RULE_CATALOG
        ) if dimensions is INDUSTRIES else 0
        verified_specific = sum(
            spec.get("industry_validation") == "industry_specific_verified"
            and code in spec.get("industries", [])
            for spec in VERIFIED_RULE_CATALOG
        ) if dimensions is INDUSTRIES else 0
        generic_verified = sum(
            "ALL" in spec.get("industries", []) for spec in VERIFIED_RULE_CATALOG
        ) if dimensions is INDUSTRIES else 0
        matrix.append({
            "code": code,
            "name": name,
            "candidate_mentions": count,
            "verified_generic_rules": generic_verified,
            "verified_applicable_rules": verified_applicable,
            "verified_specific_rules": verified_specific,
            "state": (
                "已有专项原子规则，仍需行业案例验证" if verified_specific
                else ("存在候选知识，待场景验证" if count else "候选知识空白")
            ),
        })
    return matrix


def build_methodology_coverage(static_root):
    root = Path(static_root)
    industry_profiles_payload = _read(root / "industry_audit_profiles.json")
    industry_packs_payload = _read(root / "industry_methodology_packs.json")
    manufacturing_contracts = _read(root / "manufacturing_scenario_contracts.json")
    construction_contracts = _read(root / "construction_scenario_contracts.json")
    rewritten_contracts = {
        "C": manufacturing_contracts,
        "E": construction_contracts,
    }
    rules = _read(root / "tax_risk_rules_local_export.json")
    clues = _read(root / "cross_domain_clues.json")
    evidence_payload = _read(root / "cross_domain_evidence.json")
    analysis_payload = _read(root / "cross_domain_analysis.json")
    evidence = evidence_payload.get("evidence_chains", evidence_payload)
    analysis = analysis_payload.get("analysis_chains", analysis_payload)

    text_getter = lambda rule: " ".join(str(rule.get(field, "")) for field in (
        "item", "category", "monitor_category", "applicable_condition", "tax_impact",
        "phenomena", "focus", "threshold",
    ))
    industry_text_getter = lambda rule: " ".join(str(rule.get(field, "")) for field in (
        "item", "category", "monitor_category", "applicable_condition",
    ))
    industry_matrix = _matrix(rules, INDUSTRIES, industry_text_getter)
    staged_scenes = Counter()
    for pack in industry_packs_payload.get("packs", []):
        staged_scenes[str(pack.get("industry_code", ""))] += len(pack.get("scenarios", []))
    for row in industry_matrix:
        row["staged_m2_scenarios"] = staged_scenes.get(row["code"], 0)
        row["rewritten_m25_scenarios"] = len(
            rewritten_contracts.get(row["code"], {}).get("scenarios", [])
        )
        if row["staged_m2_scenarios"]:
            row["state"] = "M2专项场景和字段契约已定义，待真实样本与反例验证"
        if row["rewritten_m25_scenarios"]:
            row["state"] = "M2.5五链场景已完成边界测试，待脱敏真实样本验证后升级M3"
    tax_matrix = []
    for code, name, keywords in TAXES:
        count = sum(any(keyword in text_getter(rule) for keyword in keywords) for rule in rules)
        verified = sum(name in spec.get("taxes", []) for spec in VERIFIED_RULE_CATALOG)
        tax_matrix.append({"code": code, "name": name, "candidate_mentions": count, "verified_executable_rules": verified})
    lifecycle_matrix = []
    for code, name, keywords in LIFECYCLES:
        count = sum(any(keyword in text_getter(rule) for keyword in keywords) for rule in rules)
        verified = sum(name in spec.get("lifecycle", []) for spec in VERIFIED_RULE_CATALOG)
        lifecycle_matrix.append({"code": code, "name": name, "candidate_mentions": count, "verified_executable_rules": verified})

    item_counter = Counter(_normalise(rule.get("item")) for rule in rules)
    duplicate_rule_count = sum(count - 1 for key, count in item_counter.items() if key and count > 1)
    clue_signatures = Counter(_signature(chain) for chain in clues)
    evidence_signatures = Counter(_signature(chain) for chain in evidence)
    analysis_signatures = Counter(_signature(chain) for chain in analysis)
    dominant_analysis = analysis_signatures.most_common(1)[0][1] if analysis_signatures else 0
    provenance_missing = sum(not str(rule.get("source", "")).strip() for rule in rules)
    risk_distribution = Counter(str(rule.get("level", "未分级")) for rule in rules)
    candidate_governance = build_candidate_governance(rules)
    pack_summaries = [
        {
            "id": pack.get("id"),
            "industry_code": pack.get("industry_code"),
            "name": pack.get("name"),
            "maturity": pack.get("maturity"),
            "scene_count": len(pack.get("scenarios", [])),
        }
        for pack in industry_packs_payload.get("packs", [])
    ]

    gaps = [
        {"priority": "P0", "gap": "候选规则被误当成熟规则", "control": "1720条统一标记为结构化候选；只有经过数据契约和回归测试的规则进入可执行层。"},
        {"priority": "P0", "gap": "分析链高度模板化", "control": f"最大单一分析链结构覆盖{dominant_analysis}条；未完成事实、反证、因果、金额和法律程序契约前不得升级。"},
        {"priority": "P0", "gap": "来源和验证记录不足", "control": f"{candidate_governance['summary']['candidate_rules'] - candidate_governance['summary']['official_provenance_recorded']}条候选规则尚无完整官方来源记录；其中{provenance_missing}条来源字段为空。需要逐条补官方链接、适用期间、核验人、案例验证和回退版本。"},
        {"priority": "P1", "gap": "行业专项可执行规则不足", "control": "行业矩阵只显示候选知识，不以关键词命中冒充行业验证；按行业包逐批建立样本和原子计算。"},
        {"priority": "P1", "gap": "外部数据权限和字段契约不足", "control": "银行、平台、海关、市场监管等资料只有在合法取得且字段契约明确时才能启用对应规则。"},
        {"priority": "P1", "gap": "风险分级严重偏高", "control": "旧库风险等级不再决定报告结论；运行时改用资料质量、线索、部分支持和待人工复核状态。"},
    ]

    return {
        "version": "1.2.0",
        "positioning": "覆盖矩阵衡量的是已验证能力和已知空白，不把规则数量、关键词命中或模型评分当成真实稽查覆盖。",
        "taxonomy_basis": {
            "name": "国民经济行业分类（GB/T 4754—2017，按第1号修改单修订）",
            "scope": "20个门类、97个大类、473个中类、1382个小类",
            "url": "https://www.stats.gov.cn/xxgk/tjbz/gjtjbz/201710/t20171017_1758922.html",
        },
        "inventory": {
            "candidate_rules": len(rules),
            "verified_executable_rules": len(VERIFIED_RULE_CATALOG),
            "priority_industry_packs": len(pack_summaries),
            "staged_m2_industry_scenarios": sum(item["scene_count"] for item in pack_summaries),
            "rewritten_m25_scenarios": sum(
                len(payload.get("scenarios", [])) for payload in rewritten_contracts.values()
            ),
            "clue_chains": len(clues),
            "evidence_chains": len(evidence),
            "analysis_chains": len(analysis),
            "candidate_rules_missing_provenance": provenance_missing,
            "candidate_rules_without_verified_official_provenance": candidate_governance["summary"]["candidate_rules"] - candidate_governance["summary"]["official_provenance_recorded"],
            "normalised_duplicate_rule_count": duplicate_rule_count,
            "unique_clue_structures": len(clue_signatures),
            "unique_evidence_structures": len(evidence_signatures),
            "unique_analysis_structures": len(analysis_signatures),
            "dominant_analysis_structure_count": dominant_analysis,
            "risk_distribution": dict(risk_distribution),
        },
        "maturity_model": [
            {"id": "M0", "name": "退役或重复", "release": "不进入运行"},
            {"id": "M1", "name": "结构化候选知识", "release": "仅供检索和人工参考"},
            {"id": "M2", "name": "场景已定义", "release": "可生成资料清单和调查计划"},
            {"id": "M2.5", "name": "五链配套并完成边界桌面测试", "release": "可按场景生成受控核验计划，不形成自动结论"},
            {"id": "M3", "name": "数据契约已验证", "release": "可执行原子筛查，只形成待核事实"},
            {"id": "M4", "name": "案例与反例验证完成", "release": "可进入受控生产并持续监测误报漏报"},
        ],
        "verified_rule_catalog": VERIFIED_RULE_CATALOG,
        "candidate_governance": candidate_governance,
        "industry_pack_summary": pack_summaries,
        "industry_matrix": industry_matrix,
        "industry_profiles": industry_profiles_payload.get("profiles", []),
        "industry_profile_boundary": industry_profiles_payload.get("use_boundary", ""),
        "tax_matrix": tax_matrix,
        "lifecycle_matrix": lifecycle_matrix,
        "data_capability_matrix": DATA_CAPABILITIES,
        "gap_register": gaps,
        "release_rule": "新增数量不设目标。只有补齐适用前提、数据字段、计算方法、合理解释、证据谱系、测试样本、维护记录和回退方案后，规则才能升级。",
    }
