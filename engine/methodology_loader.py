# ══════════════════════════════════════════════════════════════
# 方法论加载器 — 让前端说明、后台匹配和质量门禁共用同一框架
# ══════════════════════════════════════════════════════════════

import json
import os

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "methodology_config.json")
_FRAMEWORK_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "methodology_framework.json")


def load_methodology_framework():
    """加载只读的方法论权威框架；运行期个性化配置仍由 config 单独管理。"""
    try:
        with open(_FRAMEWORK_PATH, "r", encoding="utf-8") as framework_file:
            framework = json.load(framework_file)
        if isinstance(framework, dict) and framework.get("workflow"):
            return framework
    except (OSError, ValueError, TypeError):
        pass
    return {
        "version": "fallback",
        "workflow": [],
        "business_domains": [],
        "legal_sources": [],
        "positioning": "系统只形成待核线索和复核建议，不替代法定认定。",
    }


def load_methodology_config():
    """加载运行配置；核心流程和边界始终以只读 v4 框架为准。"""
    if os.path.exists(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                configured = json.load(f)
            authoritative = _default_config()
            for key in ("version", "layers", "iron_rules", "six_steps"):
                configured[key] = authoritative[key]
            return configured
        except Exception:
            pass
    return _default_config()


def _default_config():
    """默认全流程执行框架。"""
    return {
        "version": "4.0.0",
        "layers": [
            {"name": "任务与权限", "order": 1, "steps": ["主体、期间、税费种和授权范围确认"], "broadcast": "phase1_triage"},
            {"name": "资料接收保全", "order": 2, "steps": ["原件、来源、哈希、交接和缺口登记"], "broadcast": None},
            {"name": "解析与质量", "order": 3, "steps": ["结构化、口径统一、去重和解析限制"], "broadcast": "phase1_triage"},
            {"name": "画像与适用性", "order": 4, "steps": ["经营实质、行业、业务模式和规则闸门"], "broadcast": "phase2_deep_dive"},
            {"name": "全域扫描", "order": 5, "steps": ["税费种、业务周期、账票表税和时间序列扫描"], "broadcast": "phase2_deep_dive"},
            {"name": "调查线索", "order": 6, "steps": ["待证事实、资料请求、访谈问题和停止条件"], "broadcast": "phase3_cross_validate"},
            {"name": "证据复核", "order": 7, "steps": ["三性、独立性、支持证据、反证和矛盾"], "broadcast": "phase3_cross_validate"},
            {"name": "分析测算", "order": 8, "steps": ["规则要件、竞争解释、因果和可复算底稿"], "broadcast": "phase4_synthesis"},
            {"name": "法律程序权益", "order": 9, "steps": ["效力期间、取证程序、陈述申辩和权限复核"], "broadcast": None},
            {"name": "审理移交", "order": 10, "steps": ["事实、证据、反证、测算、依据和限制成套移交"], "broadcast": None},
            {"name": "受控进化", "order": 11, "steps": ["效果评估、候选变更、审批测试和版本回退"], "broadcast": None}
        ],
        "iron_rules": [
            "经营实质必须由依法取得且可追溯的多源事实支持",
            "规则命中和模型评分只产生待核线索，不是证据或法律结论",
            "同源派生结果不重复计算为独立证据，反向证据同等评价",
            "事实、证据、金额、法律性质和程序条件分别复核",
            "证据不足、冲突未解或权限不明时必须停在待核状态",
        ],
        "report_standards": {
            "chapters": 8,
            "quality_gates": ["文本净化", "底层三性校验", "12项质量标准", "建议增强", "二次净化"],
            "quality_standards": [
                "客观第三人称叙事", "事实-证据-后果三要素", "完整因果链",
                "可操作的紧迫感", "智能法律诊断", "证据明细表",
                "方法在前过程在后", "反模板句", "事实具体化",
                "防跨发现复制", "空占位符检测", "法律条款号",
            ],
        },
        "six_steps": ["范围锚定", "资料保全", "适用性判断", "调查取证", "证据与反证复核", "审理移交"],
    }


def save_methodology_config(config):
    """保存方法论配置（风险检查员在线编辑后持久化）"""
    try:
        os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def get_layer_by_name(name):
    """按名称获取某一层配置"""
    config = load_methodology_config()
    for layer in config.get("layers", []):
        if layer["name"] == name:
            return layer
    return None


def validate_execution(pipeline_log, layer_names=None):
    """验证十一环节执行完整性：检查 pipeline_log 是否覆盖了全部必经环节。"""
    config = load_methodology_config()
    if layer_names is None:
        layer_names = [layer["name"] for layer in config["layers"]]
    executed = []
    for line in pipeline_log:
        for name in layer_names:
            if name in str(line):
                executed.append(name)
    executed = list(set(executed))
    missing = [n for n in layer_names if n not in executed]
    return {"executed": executed, "missing": missing, "complete": len(missing) == 0}


def get_filter_rules():
    """动态加载过滤规则（替代硬编码 HARD_BAN/COND_BAN/模板句/标准分级）

    返回节点：
      hard_ban              — 硬删除关键词列表
      cond_ban              — 有条件过滤字典 {资料类别: [关键词...]}
      boilerplate_prefixes  — 模板句前缀
      boilerplate_suffixes  — 模板句后缀
      standard_overrides    — 12项质量标准分级覆盖 {S01: {score_min, enabled}}
    """
    config = load_methodology_config()
    return config.get("filter_rules", {})


def seed_filter_rules(defaults):
    """首次运行时把代码内置默认规则写入配置文件（幂等：已有节点不覆盖）。

    引擎不再"背"规则而是"读"规则——写入后风险检查员可直接编辑
    static/methodology_config.json 的 filter_rules 节点，修改即生效。
    """
    config = load_methodology_config()
    fr = config.get("filter_rules") or {}
    changed = False
    for key, val in (defaults or {}).items():
        if key not in fr or not fr.get(key):
            fr[key] = val
            changed = True
    if changed:
        config["filter_rules"] = fr
        save_methodology_config(config)
    return fr


def set_filter_rule(rule_type, rule_value, enabled=True):
    """动态添加/更新过滤规则"""
    config = load_methodology_config()
    if "filter_rules" not in config:
        config["filter_rules"] = {}
    if rule_type not in config["filter_rules"]:
        config["filter_rules"][rule_type] = []
    if enabled and rule_value not in config["filter_rules"][rule_type]:
        config["filter_rules"][rule_type].append(rule_value)
    elif not enabled and rule_value in config["filter_rules"][rule_type]:
        config["filter_rules"][rule_type].remove(rule_value)
    return save_methodology_config(config)


# ═══════════ 兼容旧接口（orchestrator.py / pipeline.py / __init__.py 依赖） ═══════════

_FRAMEWORK = load_methodology_framework()

METHODOLOGY_KNOWLEDGE = {
    "version": _FRAMEWORK.get("version", "fallback"),
    "methodologies": [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "category": "全流程作业",
            "description": item.get("objective", ""),
            "gate": item.get("gate", ""),
            "output": item.get("output", ""),
        }
        for item in _FRAMEWORK.get("workflow", [])
    ] + [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "category": "业务域",
            "description": item.get("scope", ""),
            "output": "、".join(item.get("key_outputs", [])),
        }
        for item in _FRAMEWORK.get("business_domains", [])
    ],
    "law_references": _FRAMEWORK.get("legal_sources", []),
    # 兼容旧调用方，但不再维护可能过期的硬编码条款号。
    "laws": _FRAMEWORK.get("legal_sources", []),
}


def _normalise_profile(data_profile):
    """兼容文本、字典和列表输入，统一生成方法论匹配画像。"""
    if isinstance(data_profile, dict):
        profile = dict(data_profile)
        text_parts = [str(profile.get(key, "")) for key in (
            "type", "name", "category", "detail", "description", "tax_type",
            "industry", "business_model",
        )]
        profile["text"] = " ".join(text_parts)
        return profile
    if isinstance(data_profile, (list, tuple, set)):
        return {"text": " ".join(str(item) for item in data_profile)}
    return {"text": str(data_profile or "")}


def match_methodology(data_profile, knowledge=None):
    """根据发现或数据画像匹配流程与业务域；不会因字符串输入而降级失败。"""
    if knowledge is None:
        knowledge = METHODOLOGY_KNOWLEDGE
    profile = _normalise_profile(data_profile)
    text = profile.get("text", "")
    methods = knowledge.get("methodologies", [])
    matched = []
    keyword_groups = {
        "D03": ("账", "凭证", "报表", "申报", "税会差异"),
        "D04": ("收入", "销售", "应收", "预收", "客户"),
        "D05": ("采购", "成本", "应付", "预付", "供应商"),
        "D06": ("发票", "开票", "进项", "销项", "红冲", "数电"),
        "D07": ("资金", "收款", "付款", "银行", "账户", "往来"),
        "D08": ("存货", "库存", "物流", "产能", "能耗", "加工", "BOM"),
        "D09": ("费用", "资产", "折旧", "摊销", "个人消费"),
        "D10": ("工资", "薪酬", "个税", "社保", "人员", "劳务"),
        "D11": ("合同", "履约", "经营实质", "商业目的"),
        "D12": ("关联", "集团", "跨境", "非居民", "转让定价"),
        "D13": ("房产", "土地", "资源", "环保", "车辆", "印花", "项目"),
        "D14": ("证据", "法律", "处罚", "申辩", "听证", "程序", "移送"),
    }
    selected_ids = {
        domain_id for domain_id, keywords in keyword_groups.items()
        if any(keyword in text for keyword in keywords)
    }
    if profile.get("has_invoices"):
        selected_ids.add("D06")
    if profile.get("has_bank"):
        selected_ids.add("D07")
    if profile.get("has_inventory"):
        selected_ids.add("D08")

    # 每个事项始终需要适用性、证据和法律程序三道流程闸门。
    core_ids = {"W04", "W07", "W09"}
    for method in methods:
        if method.get("id") in selected_ids:
            matched.append(method)
    for method in methods:
        if method.get("id") in core_ids:
            matched.append(method)
    return matched or methods[:3]


def get_relevant_laws(data_profile, knowledge=None):
    """按事项匹配官方依据类别；具体条款仍须按期间和事实人工核验。"""
    if knowledge is None:
        knowledge = METHODOLOGY_KNOWLEDGE
    profile = _normalise_profile(data_profile)
    text = profile.get("text", "")
    laws = knowledge.get("law_references", knowledge.get("laws", []))
    selected = []
    for law in laws:
        name = str(law.get("name", ""))
        if "税务风险检查案件办理程序" in name or "行政处罚法" in name:
            selected.append(law)
        elif "增值税" in name and any(word in text for word in ("增值税", "发票", "进项", "销项", "销售")):
            selected.append(law)
        elif "税收征收管理法" in name:
            selected.append(law)
        elif "危害税收征管" in name and any(word in text for word in ("移送", "刑事", "虚开", "骗税", "偷税")):
            selected.append(law)
    return selected
