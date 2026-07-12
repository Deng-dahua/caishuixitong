# -*- coding: utf-8 -*-
"""
enterprise_profile.py —— 案情画像与分析策略 (P0)

在感知层启动后、29域扫描前调用。聚合现有散落的四块逻辑：
  _detect_target_entity() → identity
  行业检测(三层穿透)    → industry  
  规模判定                → scale
  记忆层行业画像          → risk_profile + strategy

不替代现有逻辑——只聚合产出为统一入口。
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Identity:
    """企业身份"""
    name: str = ""
    credit_code: str = ""
    legal_person: str = ""
    taxpayer_type: str = ""           # 一般纳税人/小规模纳税人
    established_date: str = ""        # 成立日期
    registered_capital: str = ""      # 注册资本
    business_scope: str = ""          # 经营范围


@dataclass
class IndustryProfile:
    """行业画像（三层穿透）"""
    registered: str = ""              # 工商登记行业
    inferred: str = ""                # 发票编码推断行业
    real: str = ""                    # 综合判断实质行业
    penetration_note: str = ""        # 穿透说明
    service_gate_active: bool = False # 服务行业闸门是否激活
    mixed_industry: bool = False      # 是否混合行业（服务+货物）


@dataclass
class ScaleProfile:
    """规模判定"""
    revenue_range: str = ""           # 营收区间: 500-1000万
    employee_count: int = 0           # 从业人数
    asset_range: str = ""             # 资产区间
    annual_revenue: float = 0.0       # 年营收预估
    annual_purchases: float = 0.0     # 年采购额预估
    is_small_micro: bool = False      # 是否小微企业


@dataclass 
class RiskProfile:
    """风险初评"""
    vulnerabilities: List[str] = field(default_factory=list)   # TOP5脆弱点
    common_issues: List[str] = field(default_factory=list)     # 常见问题
    benchmark_deviations: Dict[str, float] = field(default_factory=dict)  # 偏离行业基准
    prior_violations: List[str] = field(default_factory=list)  # 历史违规记录
    overall_risk_score: float = 0.0   # 综合风险评分(0-10)


@dataclass
class Strategy:
    """分析策略"""
    priority_attack: str = ""               # 优先攻哪个点: 银行流水/发票/往来款
    priority_domains: List[str] = field(default_factory=list) # 优先扫描的域
    skip_domains: List[str] = field(default_factory=list)     # 跳过的域（服务行业跳过制造业域）
    threshold_adjustments: Dict[str, Any] = field(default_factory=dict)  # 阈值行业调整
    domain_weights: Dict[str, float] = field(default_factory=dict)       # 域扫描权重分配
    expected_analysis_depth: str = ""      # 预期分析深度: 全面/标准/快速


@dataclass
class EnterpriseProfile:
    """完整的案情画像"""
    company_id: str = ""
    identity: Identity = field(default_factory=Identity)
    industry: IndustryProfile = field(default_factory=IndustryProfile)
    scale: ScaleProfile = field(default_factory=ScaleProfile)
    risk_profile: RiskProfile = field(default_factory=RiskProfile)
    strategy: Strategy = field(default_factory=Strategy)
    
    def to_dict(self) -> Dict[str, Any]:
        """转为可序列化字典（供前端消费）"""
        return {
            "company_id": self.company_id,
            "identity": {
                "name": self.identity.name,
                "credit_code": self.identity.credit_code,
                "legal_person": self.identity.legal_person,
                "taxpayer_type": self.identity.taxpayer_type,
            },
            "industry": {
                "registered": self.industry.registered,
                "inferred": self.industry.inferred,
                "real": self.industry.real,
                "penetration_note": self.industry.penetration_note,
            },
            "scale": {
                "revenue_range": self.scale.revenue_range,
                "employee_count": self.scale.employee_count,
                "asset_range": self.scale.asset_range,
            },
            "risk_profile": {
                "vulnerabilities": self.risk_profile.vulnerabilities,
                "common_issues": self.risk_profile.common_issues,
                "benchmark_deviations": self.risk_profile.benchmark_deviations,
                "overall_risk_score": self.risk_profile.overall_risk_score,
            },
            "strategy": {
                "priority_attack": self.strategy.priority_attack,
                "priority_domains": self.strategy.priority_domains,
                "skip_domains": self.strategy.skip_domains,
                "threshold_adjustments": self.strategy.threshold_adjustments,
            }
        }


# ================================================================
# 主入口
# ================================================================

def _profile_enterprise(company_id: str, ctx=None, pipeline_log: List[str] = None,
                        db=None, bank_txs=None, invoices=None, docs=None,
                        business_license_text: str = "", company_profile: Dict = None,
                        industry_data: Dict = None) -> EnterpriseProfile:
    """
    在感知层启动后、29域扫描前调用。
    聚合现有四块逻辑，输出统一案情画像。
    
    Args:
        company_id: 账套ID
        ctx: 流水线上下文（可选，含已计算的中间结果）
        pipeline_log: 日志列表
        db: 数据库连接
        bank_txs: 银行交易记录
        invoices: 发票列表
        docs: 上传资料元信息
        business_license_text: 营业执照文本
        company_profile: 已提取的公司信息
        industry_data: 行业基准数据
    """
    if pipeline_log is None:
        pipeline_log = []
    
    profile = EnterpriseProfile(company_id=company_id)
    
    # Step 1: 身份锁定
    profile.identity = _build_identity(company_id, db, company_profile, business_license_text, pipeline_log)
    
    # Step 2: 行业穿透
    profile.industry = _build_industry(invoices, bank_txs, business_license_text, 
                                        industry_data, pipeline_log)
    
    # Step 3: 规模判定
    profile.scale = _build_scale(invoices, bank_txs, db, company_id, pipeline_log)
    
    # Step 4: 风险初评
    profile.risk_profile = _build_risk_profile(profile.industry, profile.scale, 
                                                db, company_id, pipeline_log)
    
    # Step 5: 生成策略
    profile.strategy = _build_strategy(profile.industry, profile.scale, 
                                        profile.risk_profile, pipeline_log)
    
    pipeline_log.append(f"[PROFILE] 案情画像完成: {profile.identity.name} | "
                        f"行业={profile.industry.real} | "
                        f"规模={profile.scale.revenue_range} | "
                        f"策略={profile.strategy.priority_attack}")
    
    return profile


# ================================================================
# Step 1: 身份锁定
# ================================================================

def _build_identity(company_id: str, db, company_profile: Dict = None,
                    business_license_text: str = "", pipeline_log: List[str] = None) -> Identity:
    """从数据库/缓存/营业执照构建企业身份"""
    identity = Identity()
    
    # 从数据库获取
    if db:
        try:
            row = db.execute(
                "SELECT name, credit_code, legal_person, taxpayer_type, "
                "established_date, registered_capital, business_scope "
                "FROM companies WHERE id=?", (company_id,)
            ).fetchone()
            if row:
                identity.name = row[0] or ""
                identity.credit_code = row[1] or ""
                identity.legal_person = row[2] or ""
                identity.taxpayer_type = row[3] or ""
                identity.established_date = row[4] or ""
                identity.registered_capital = row[5] or ""
                identity.business_scope = row[6] or ""
        except Exception as e:
            if pipeline_log is not None:
                pipeline_log.append(f"[PROFILE] 数据库查询身份失败: {e}")
    
    # 数据库无数据时用 company_profile 补充
    if company_profile and not identity.name:
        identity.name = company_profile.get("name", "")
        identity.credit_code = company_profile.get("credit_code", "")
        identity.legal_person = company_profile.get("legal_person", "")
        identity.taxpayer_type = company_profile.get("taxpayer_type", "一般纳税人")
    
    # 营业执照文本兜底
    if business_license_text and not identity.name:
        identity.name = _extract_field(business_license_text, ["名称", "企业名称"])
        identity.credit_code = _extract_field(business_license_text, ["统一社会信用代码", "信用代码"])
        identity.legal_person = _extract_field(business_license_text, ["法定代表人", "法人代表", "负责人"])
    
    return identity


# ================================================================
# Step 2: 行业穿透
# ================================================================

def _build_industry(invoices, bank_txs, business_license_text: str = "",
                    industry_data: Dict = None, pipeline_log: List[str] = None) -> IndustryProfile:
    """三层穿透：工商登记 → 发票推断 → 综合判断"""
    ind = IndustryProfile()
    
    # 第一层：工商登记行业
    ind.registered = _extract_industry_from_license(business_license_text)
    
    # 第二层：发票编码推断行业
    ind.inferred = _extract_industry_from_invoices(invoices, industry_data)
    
    # 第三层：综合判断
    if ind.inferred and ind.inferred != ind.registered:
        # 发票推断与工商登记不一致 → 以发票推断为准（实质重于形式）
        ind.real = ind.inferred
        ind.penetration_note = f"工商登记={ind.registered}，但发票编码推断={ind.inferred}，以发票数据为准判定实质行业"
    elif ind.inferred:
        ind.real = ind.inferred
    elif ind.registered:
        ind.real = ind.registered
    else:
        ind.real = "未识别"
    
    # 服务行业闸门判断
    SERVICE_CODES = {"信息技术服务", "广告服务", "设计服务", "咨询服务", "软件服务",
                     "会议展览服务", "文化创意服务", "物流辅助服务", "鉴证咨询服务",
                     "广播影视服务", "商务辅助服务", "其他现代服务", "教育医疗服务",
                     "旅游娱乐服务", "餐饮住宿服务", "居民日常服务", "其他生活服务",
                     "金融服务", "保险服务"}
    if ind.real in SERVICE_CODES or any(svc in ind.real for svc in ["服务", "金融", "保险"]):
        ind.service_gate_active = True
        if pipeline_log is not None:
            pipeline_log.append(f"[GATE] 服务行业闸门激活: {ind.real} → 关闭制造业实物域分析")
    
    # 混合行业判断
    goods_keywords = ["制造", "生产", "加工", "组装", "批发", "零售", "贸易", "建材", "食品", "纺织", "服装"]
    service_keywords = ["服务", "咨询", "设计", "广告", "运输", "物流", "代理"]
    has_goods = any(kw in (ind.real or "") for kw in goods_keywords)
    has_service = any(kw in (ind.real or "") for kw in service_keywords)
    ind.mixed_industry = has_goods and has_service
    
    return ind


def _extract_industry_from_license(text: str) -> str:
    """从营业执照提取行业"""
    if not text:
        return ""
    for line in text.split("\n"):
        line = line.strip()
        if "行业" in line:
            parts = line.split("行业")
            if len(parts) > 1:
                return parts[1].strip().rstrip("。，,；;")
    return ""


def _extract_industry_from_invoices(invoices, industry_data: Dict = None) -> str:
    """从发票品名关键词推断行业（加权投票制）"""
    if not invoices:
        return ""
    
    # 收集所有品名
    goods_names = []
    for inv in invoices:
        goods = str(inv.get("goods", inv.get("货物或应税劳务名称", "")))
        if goods and goods.lower() != "nan":
            goods_names.append(goods)
    
    if not goods_names:
        return ""
    
    goods_text = " ".join(goods_names)
    
    # 如果传入了行业数据，使用匹配逻辑
    candidates = []
    if industry_data:
        benchmarks = industry_data.get("benchmarks", {})
        for kw in benchmarks:
            if kw == "_default":
                continue
            if kw in goods_text:
                candidates.append((kw, len(kw)))
            else:
                # 反向匹配
                for word in set(goods_text.replace(",", " ").replace("，", " ").split()):
                    word = word.strip("*").strip()
                    if len(word) >= 2 and word in kw:
                        candidates.append((kw, len(word)))
                        break
    
    if candidates:
        candidates.sort(key=lambda x: -x[1])
        return candidates[0][0]
    
    # 无行业数据时使用内置关键词匹配
    INDUSTRY_KEYWORDS = {
        "广告服务": ["广告", "推广", "营销", "策划"],
        "信息技术服务": ["软件", "开发", "系统", "技术", "IT", "信息"],
        "设计服务": ["设计", "创意", "美术"],
        "咨询服务": ["咨询", "顾问", "培训", "辅导"],
        "餐饮住宿服务": ["餐饮", "食品", "外卖", "餐", "酒"],
        "批发零售": ["批发", "零售", "销售", "贸易"],
        "制造业": ["制造", "生产", "加工", "建材", "纺织", "服装", "电子", "机械", "设备"],
        "交通运输": ["运输", "物流", "快递", "货运", "配送"],
        "建筑": ["建筑", "工程", "施工", "装修", "建材"],
    }
    
    goods_lower = goods_text.lower()
    for industry, keywords in INDUSTRY_KEYWORDS.items():
        if any(kw in goods_lower for kw in keywords):
            return industry
    
    return ""


# ================================================================
# Step 3: 规模判定
# ================================================================

def _build_scale(invoices, bank_txs, db, company_id: str,
                 pipeline_log: List[str] = None) -> ScaleProfile:
    """从发票+银行流水判定企业规模"""
    sp = ScaleProfile()
    
    # 从发票计算年营收
    total_amount = 0.0
    total_tax = 0.0
    if invoices:
        for inv in invoices:
            try:
                total_amount += float(inv.get("amount", 0) or 0)
                total_tax += float(inv.get("tax_amount", 0) or 0)
            except (ValueError, TypeError):
                pass
    
    sp.annual_revenue = total_amount + total_tax  # 含税营收
    
    # 从银行流水计算采购额（贷方=支出）
    if bank_txs:
        for tx in bank_txs:
            try:
                credit = float(tx.get("credit", 0) or 0)
                sp.annual_purchases += abs(credit)
            except (ValueError, TypeError):
                pass
    
    # 分级
    if sp.annual_revenue > 10_000_000:
        sp.revenue_range = "1000万以上"
    elif sp.annual_revenue > 5_000_000:
        sp.revenue_range = "500-1000万"
    elif sp.annual_revenue > 1_000_000:
        sp.revenue_range = "100-500万"
    elif sp.annual_revenue > 0:
        sp.revenue_range = "100万以下"
    else:
        sp.revenue_range = "未知"
    
    # 从数据库获取员工数
    if db:
        try:
            row = db.execute(
                "SELECT COUNT(DISTINCT name) FROM salary_data WHERE company_id=?",
                (company_id,)
            ).fetchone()
            if row:
                sp.employee_count = row[0] or 0
        except Exception:
            pass
    
    # 小微企业判断
    sp.is_small_micro = (sp.employee_count <= 100 and sp.annual_revenue <= 30_000_000)
    
    return sp


# ================================================================
# Step 4: 风险初评
# ================================================================

def _build_risk_profile(industry: IndustryProfile, scale: ScaleProfile, 
                         db, company_id: str, pipeline_log: List[str] = None) -> RiskProfile:
    """行业脆弱点+历史违规+基准偏离"""
    rp = RiskProfile()
    
    # 行业典型脆弱点（从记忆层抽取）
    INDUSTRY_VULNERABILITIES = {
        "广告服务": ["私户收款隐匿收入", "虚列咨询费/服务费", "关联交易转移利润", "无票收入不入账"],
        "信息技术服务": ["虚列研发费用", "软件销售收入确认时点不当", "关联交易转移利润", "私户收款"],
        "设计服务": ["私户收款隐匿收入", "虚列外包费用", "个人劳务报酬未代扣个税"],
        "咨询服务": ["虚列咨询费", "关联交易转移利润", "无票收入不入账"],
        "批发零售": ["账外经营", "虚开/接受虚开发票", "存货账实不符", "私户收款"],
        "制造业": ["账外经营(不开票销售)", "虚增成本(多列材料消耗)", "关联交易定价不当", "废料收入不入账"],
        "建筑": ["预收账款不转收入", "甲供材处理不当", "跨区域预缴不足", "劳务分包虚列"],
        "交通运输": ["无票收入(现金收款)", "燃油费虚增", "车辆挂靠税务处理不当"],
        "餐饮住宿": ["现金收入不入账", "食材采购无票入账", "会员储值卡收入确认不当"],
        "房地产": ["预售收入确认时点不当", "成本分摊不当", "关联交易定价", "土地增值税清算滞后"],
    }
    
    rp.vulnerabilities = INDUSTRY_VULNERABILITIES.get(
        industry.real, 
        ["隐匿收入", "虚列成本", "关联交易", "发票违规"]
    )
    
    # 历史违规查询
    if db:
        try:
            rows = db.execute(
                "SELECT violation_type, COUNT(*) as cnt FROM audit_history "
                "WHERE company_id=? GROUP BY violation_type ORDER BY cnt DESC LIMIT 5",
                (company_id,)
            ).fetchall()
            if rows:
                rp.prior_violations = [f"{r[0]}({r[1]}次)" for r in rows]
        except Exception:
            pass
    
    # 综合风险评分
    if rp.prior_violations:
        rp.overall_risk_score = min(9.0, 3.0 + len(rp.prior_violations) * 1.5)
    else:
        rp.overall_risk_score = 3.0
    
    return rp


# ================================================================
# Step 5: 生成策略
# ================================================================

def _build_strategy(industry: IndustryProfile, scale: ScaleProfile,
                    risk_profile: RiskProfile, pipeline_log: List[str] = None) -> Strategy:
    """据行业和规模生成分析策略"""
    s = Strategy()
    
    # ---- 优先攻击方向 ----
    INDUSTRY_ATTACK_PRIORITY = {
        "广告服务": "银行流水",       # 服务业先攻资金流，看私户收款
        "信息技术服务": "银行流水",    # 同上
        "设计服务": "银行流水",
        "咨询服务": "银行流水",
        "批发零售": "发票进销比对",    # 商贸业先攻进销匹配
        "制造业": "进销存匹配",       # 制造业先攻BOM+进销存
        "建筑": "预收账款+银行流水",
        "交通运输": "燃油费+银行流水",
        "餐饮住宿": "银行流水",
        "房地产": "预售收入+成本分摊",
    }
    s.priority_attack = INDUSTRY_ATTACK_PRIORITY.get(industry.real, "银行流水")
    
    # ---- 优先域 ----
    COMMON_PRIORITY_DOMAINS = [
        "资金全链路追踪", "资金流向追踪", "进销毛利率分析",
        "多源交叉验证", "经营实质分析", "供应商穿透分析"
    ]
    s.priority_domains = COMMON_PRIORITY_DOMAINS.copy()
    
    # ---- 跳过域（服务行业闸门）----
    if industry.service_gate_active:
        s.skip_domains = [
            "进销存匹配分析", "存货周转预警", "发票存货付款三角验证",
            "制造业毛利率对标", "BOM分析"
        ]
        if pipeline_log is not None:
            pipeline_log.append(f"[PROFILE] 服务行业闸门: 跳过 {len(s.skip_domains)} 个制造业域")
    
    # 混合行业特殊处理
    if industry.mixed_industry:
        s.skip_domains = [d for d in s.skip_domains if "制造业" not in d]
        s.priority_domains.append("混合行业品名级区分")
    
    # ---- 阈值行业调整 ----
    s.threshold_adjustments = _get_threshold_adjustments(industry.real)
    
    # ---- 域权重分配 ----
    s.domain_weights = {
        "资金全链路追踪": 1.5,
        "进销毛利率分析": 1.3,
        "经营实质分析": 1.4,
    }
    
    # ---- 分析深度 ----
    if risk_profile.overall_risk_score >= 7:
        s.expected_analysis_depth = "全面"
    elif risk_profile.overall_risk_score >= 4:
        s.expected_analysis_depth = "标准"
    else:
        s.expected_analysis_depth = "快速"
    
    return s


def _get_threshold_adjustments(industry: str) -> Dict[str, Any]:
    """获取行业阈值调整"""
    base = {
        "预收账款账龄": {"通用": 365, "建筑": 730, "商贸": 90, "服务": 180},
        "大额支付阈值": {"通用": 100000, "建筑": 500000, "商贸": 50000, "服务": 50000},
        "单笔发票金额": {"通用": 50000, "建筑": 200000, "商贸": 30000, "服务": 30000},
    }
    
    result = {}
    for key, values in base.items():
        industry_type = "服务" if "服务" in industry else ("建筑" if "建筑" in industry else ("商贸" if any(k in industry for k in ["批发","零售","贸易"]) else "通用"))
        result[key] = values.get(industry_type, values["通用"])
    
    return result


# ================================================================
# 工具函数
# ================================================================

def _extract_field(text: str, keywords: List[str]) -> str:
    """从文本中按关键词提取字段值"""
    for line in text.split("\n"):
        line = line.strip()
        for kw in keywords:
            if kw in line:
                val = line.split(kw)[-1].strip().lstrip("：:").strip()
                if val:
                    return val
    return ""


def _load_industry_data():
    """加载行业基准数据"""
    import json, os
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)) or ".", "static", "industry_data.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"benchmarks": {"_default": {}}}
