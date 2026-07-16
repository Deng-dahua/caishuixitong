# ══════════════════════════════════════════════════════════════
# 方法论加载器 — 让引擎动态读取稽查秘笈
# 2026-07-17 新建：稽查方法论和报告编制总纲从前端静态文档
# 转为引擎可读取的活配置
# ══════════════════════════════════════════════════════════════

import json
import os

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "methodology_config.json")


def load_methodology_config():
    """加载七层执行框架配置"""
    if os.path.exists(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return _default_config()


def _default_config():
    """默认七层执行框架（与前端稽查方法论页面同步）"""
    return {
        "version": "2026-07-17",
        "layers": [
            {
                "name": "启动",
                "order": 1,
                "steps": ["锁定身份", "三层穿透定行业", "三相符·四流合一立标尺"],
                "broadcast": "phase1_triage",
            },
            {
                "name": "扫描",
                "order": 2,
                "steps": ["34类文件指纹识别", "数据打元标签提取", "三大突破口分析", "结构对比时间序列"],
                "broadcast": "phase2_deep_dive",
            },
            {
                "name": "布网",
                "order": 3,
                "steps": ["规则引擎+线索链+证据链+分析链四阶段递进", "六大战法", "分税种杀手锏", "10类行业专属检测包"],
                "broadcast": "phase3_cross_validate",
            },
            {
                "name": "过滤",
                "order": 4,
                "steps": ["行业豁免", "数据缺失豁免", "重复合并", "低置信度切除", "金额阈值", "矛盾消解", "白名单排除"],
                "broadcast": None,
            },
            {
                "name": "定案",
                "order": 5,
                "steps": ["证据三性与闭环", "税款测算", "定性分寸(偷税/少缴/虚开)", "对抗性自检(反向假设/对手交叉/政策复查)"],
                "broadcast": "phase4_synthesis",
            },
            {
                "name": "出鞘",
                "order": 6,
                "steps": ["报告生成与净化", "六要素叙事框架", "合规度五维热力图评估"],
                "broadcast": None,
            },
            {
                "name": "进化",
                "order": 7,
                "steps": ["规则置信度自校准", "新模式自动发现", "政策同步更新"],
                "broadcast": None,
            },
        ],
        "iron_rules": [
            "实质重于形式（登记不算、干的才算）",
            "孤证不立（单源数据不定案）",
            "疑点非结论（起点是疑点、落点是铁证）",
            "宁存疑不错杀（说不清的标存疑、有铁证的才下定论）",
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
        "six_steps": [
            "数据锚定", "文件识别与方向判定", "行业锚定与域闸门",
            "全维度扫描", "跨域协商自洽", "结论生成与分级",
        ],
    }


def save_methodology_config(config):
    """保存方法论配置（稽查员在线编辑后持久化）"""
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
    """验证七层执行完整性：检查 pipeline_log 是否覆盖了所有层"""
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

    引擎不再"背"规则而是"读"规则——写入后稽查员可直接编辑
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

METHODOLOGY_KNOWLEDGE = {
    "methodologies": [
        {"name": "四步税务合规分析法", "category": "核心方法论", "description": "收入核查→成本核查→费用核查→资产核查"},
        {"name": "三相符·四流合一", "category": "标尺", "description": "账载/票载/申报三相符 + 合同/货物/资金/发票四流合一"},
        {"name": "三层穿透定行业", "category": "启动层", "description": "工商登记→发票数据→加工信号三层穿透判定实质经营行业"},
        {"name": "证据三性校验", "category": "定案层", "description": "真实性(可追溯)、关联性(直接相关)、合法性(程序合规)"},
        {"name": "红队证伪", "category": "定案层", "description": "生成无罪假设→证据逐一攻击→程序合规审查"},
        {"name": "六要素叙事框架", "category": "出鞘层", "description": "性质→事实→证据→来源→法律→建议"},
        {"name": "跨域协商", "category": "过滤层", "description": "消解/调整/标记/增强四种协商结果"},
        {"name": "规则置信度自校准", "category": "进化层", "description": "验证通过置信度上升，连续10次误报降级或暂停"},
    ],
    "laws": [
        {"name": "增值税法", "articles": ["第十七条(进项税额)", "第二十条(销项税额)"]},
        {"name": "企业所得税法", "articles": ["第八条(成本扣除)", "第二十八条(税率优惠)"]},
        {"name": "税收征收管理法", "articles": ["第三十五条(核定征收)", "第六十三条(偷税)", "第六十四条(少缴)"]},
    ],
}


def match_methodology(data_profile, knowledge=None):
    """根据数据画像匹配适用的方法论"""
    if knowledge is None:
        knowledge = METHODOLOGY_KNOWLEDGE
    methods = knowledge.get("methodologies", [])
    # 简单匹配：数据画像中包含的领域激活对应方法论
    matched = []
    if data_profile.get("has_invoices"):
        matched.extend([m for m in methods if m["category"] in ("核心方法论", "标尺")])
    if data_profile.get("has_bank"):
        matched.extend([m for m in methods if "资金" in m.get("description", "") or "三相符" in m.get("name", "")])
    return matched if matched else methods[:3]


def get_relevant_laws(data_profile, knowledge=None):
    """根据数据画像匹配相关法律条款"""
    if knowledge is None:
        knowledge = METHODOLOGY_KNOWLEDGE
    return knowledge.get("laws", [])
