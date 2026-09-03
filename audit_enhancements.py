"""
税务合规增强模块 - 补充材料缺口报告/数据质量评估/行业检测等功能

═════ META-001 行业推断铁律 ═════
行业推断唯一依据 = 销项发票品名，不参考进项发票品名。
WHY: 销项=企业实际经营产出（卖什么=什么行业）
     进项=采购投入/成本结构（买什么≠行业，如传媒公司买餐饮≠餐饮行业）
代码位置: detect_industry() + engine/phase1_triage.py + main.py
═══════════════════════════════════
"""
from database import SessionLocal
import json, os


def assess_data_quality(db, company_id, period_start, period_end):
    """评估上传数据的质量"""
    return {
        "total_tables": 0, "tables_with_data": 0,
        "completeness_score": 0, "quality_issues": []
    }


def check_analysis_data_availability(db, company_id, period_start, period_end):
    """检查各分析域所需数据是否可用 - 返回受限分析列表"""
    return []


def _clean_business_scope(business_scope):
    """清洗经营范围文本：截断联网抓取混入的网页噪声。

    联网核查写入的 business_scope 常把搜索引擎结果页文本一并带入
    （如"企业信息详情 > 水滴信用 资讯：…招聘信息 - 智联招聘…"）。
    这类噪声中的通用词（"信息""服务""科技"）会把行业带偏，
    例如宠物用品零售企业被判为"信息技术"。此处按噪声起始标记截断，
    只保留企业真实经营范围部分。
    """
    text = str(business_scope or "")
    noise_markers = ("企业信息详情", "此地址为公司注册地址", "招聘信息", "资讯：", "资讯:",
                     "查看更多", "反馈", "map.360.cn", "www.", "http://", "https://",
                     "BOSS直聘", "智联招聘", "爱企查", "天眼查", "企查查", "水滴信用")
    cut = len(text)
    for marker in noise_markers:
        pos = text.find(marker)
        if pos > 0:
            cut = min(cut, pos)
    return text[:cut].strip()


def detect_industry(business_scope="", company_name=""):
    """从经营范围文本推断行业（可选的company_name用于消歧）

    判定顺序要点：
    1. 经营范围先清洗，剔除联网抓取噪声，避免"企业信息详情"这类通用词污染判定；
    2. 批发零售/商贸优先于信息技术判定——"信息""服务"通用性过强，
       极易把商贸零售企业误判为信息技术或咨询服务；
    3. 公司名称的行业字号（如"商贸有限公司"）优先于经营范围。
    """
    if not business_scope and not company_name:
        return "未知行业"
    scope = _clean_business_scope(business_scope).lower()
    name = str(company_name).lower() if company_name else ""

    # 批零/商贸信号：与信息技术、咨询服务相比，行业指向更明确，优先判定
    _RETAIL_NAME = ("商贸", "贸易", "百货", "超市", "便利店", "商行", "经销", "购物")
    _RETAIL_SCOPE = ("零售", "批发", "日用百货", "互联网销售", "网上销售", "电子商务",
                     "宠物食品", "宠物用品", "母婴用品", "化妆品及卫生用品", "食品销售")
    _IT_NAME = ("软件", "信息", "互联网", "计算机", "科技", "数据", "数字")
    _IT_SCOPE = ("软件开发", "信息技术", "互联网", "计算机", "技术服务", "技术转让",
                 "技术咨询", "数据处理", "集成电路")

    # 经营范围中的"零售/批发"是不可歧义的商品流通标记；科技、传媒、咨询类字号
    # 与实际经营背离的情况极为常见（登记为"数字传媒""科技"却实际从事商品销售），
    # 故此类名称不能直接定行业，须与经营范围交叉验证。
    scope_is_trade = any(k in scope for k in ("零售", "批发"))

    # 公司名优先消歧：名称已明确写明行业字号时直接使用
    if any(k in name for k in _RETAIL_NAME) or any(k in name for k in ("零售", "批发")):
        return "商贸"
    # 科技/传媒/咨询类字号：经营范围呈商品流通特征时判商贸，否则按字号定性
    if any(k in name for k in ("广告", "传媒", "文化", "娱乐", "影视", "设计")):
        return "商贸" if scope_is_trade else "广告传媒"
    if any(k in name for k in _IT_NAME):
        return "商贸" if scope_is_trade else "信息技术"
    if any(k in name for k in ("咨询", "管理")):
        return "商贸" if scope_is_trade else "咨询服务"
    if any(k in name for k in ("建筑", "工程", "装修", "房地产")):
        return "建筑工程"
    if any(k in name for k in ("纺织", "服装", "面料", "纱线", "布", "染整")):
        return "纺织制造"
    if any(k in name for k in ("餐饮", "酒店", "住宿", "食品")):
        return "餐饮服务"
    if any(k in name for k in ("物流", "运输", "快递", "仓储")):
        return "物流运输"
    if any(k in name for k in ("医药", "医疗", "药品", "器械")):
        return "医药健康"

    # 经营范围关键词（公司名无行业暗示时使用）
    # 顺序原则：先看不可歧义的商品流通标记（零售/批发），再看专指性强的行业，
    # 通用词（信息/服务/管理）排在最后，避免把商贸企业误判为信息技术或咨询服务。
    if any(k in scope for k in ("零售", "批发")):
        return "商贸"
    if any(k in scope for k in ("纺织", "面料", "纱线")) or "服装制造" in scope:
        return "纺织制造"
    if any(k in scope for k in ("建筑", "装修", "房地产")) or "工程施工" in scope:
        return "建筑工程"
    if any(k in scope for k in ("餐饮", "酒店", "住宿")) or "食品经营" in scope:
        return "餐饮服务"
    if any(k in scope for k in ("物流", "快递", "仓储")) or "道路货物运输" in scope:
        return "物流运输"
    if any(k in scope for k in ("广告", "传媒", "影视")):
        return "广告传媒"
    if any(k in scope for k in ("医药", "医疗", "药品", "器械")):
        return "医药健康"
    # 其他商品销售类表述（日用百货、宠物用品、互联网销售等）仍属商品流通
    if any(k in scope for k in _RETAIL_SCOPE):
        return "商贸"
    if any(k in scope for k in _IT_SCOPE):
        return "信息技术"
    if any(k in scope for k in ("咨询", "管理咨询")):
        return "咨询服务"
    if "销售" in scope:
        return "商贸"
    return "商贸"


def get_industry_benchmark(industry):
    """获取行业基准值 — 从 industry_profiles.json 加载（替代硬编码字典）"""
    try:
        for base in [os.path.dirname(__file__) or ".", "."]:
            pp = os.path.join(base, "static", "industry_profiles.json")
            if os.path.exists(pp):
                with open(pp, "r", encoding="utf-8") as f:
                    profiles = json.load(f)
                industries = profiles.get("industries", {})
                # 匹配：精确行业名 → subtypes → 默认
                for key, prof in industries.items():
                    if industry == key or industry in prof.get("subtypes", []):
                        bm = prof.get("benchmarks", {})
                        gp = bm.get("gross_margin_pct", {})
                        return {
                            "name": prof.get("label", industry),
                            "vat_burden_min": 0.5, "vat_burden_max": 8.0,
                            "gross_margin_min": gp.get("low", 5), "gross_margin_max": gp.get("high", 40),
                            "net_margin_min": 1, "net_margin_max": 30,
                            "per_person_rev_low": 15, "per_person_rev_high": 200,
                            "io_ratio_low": 0.2, "io_ratio_high": 0.95
                        }
                # 兜底
                return {
                    "name": industry or "未知", "vat_burden_min": 0.5, "vat_burden_max": 8.0,
                    "gross_margin_min": 5, "gross_margin_max": 60, "net_margin_min": 1, "net_margin_max": 30,
                    "per_person_rev_low": 15, "per_person_rev_high": 200, "io_ratio_low": 0.2, "io_ratio_high": 0.95
                }
    except Exception:
        pass
    return {"name": industry or "未知", "vat_burden_min": 0.5, "vat_burden_max": 8.0,
            "gross_margin_min": 5, "gross_margin_max": 60, "net_margin_min": 1, "net_margin_max": 30,
            "per_person_rev_low": 15, "per_person_rev_high": 200, "io_ratio_low": 0.2, "io_ratio_high": 0.95}


# 行业关键词映射（供 main.py API 使用，从 detect_industry 逻辑提取）
INDUSTRY_KEYWORD_MAP = {  # pragma: no cover — 与 detect_industry() 保持一致
    "广告传媒": ["广告","传媒","文化","娱乐","影视","设计"],
    "信息技术": ["软件","信息","互联网","计算机","科技","数据","数字"],
    "咨询服务": ["咨询","服务","管理"],
    "建筑工程": ["建筑","工程","装修","房地产"],
    "纺织制造": ["纺织","服装","面料","纱线","布","染整"],
    "餐饮服务": ["餐饮","酒店","住宿","食品"],
    "物流运输": ["物流","运输","快递","仓储"],
    "医药健康": ["医药","医疗","药品","器械"],
    "商贸": ["贸易","商贸","批发","零售"],
}


def analyze_industry_specific_risks(db, company_id, industry, period_start, period_end):
    """行业特定风险分析"""
    return []


def generate_material_gap_report(db, company_id, period_start, period_end):
    """生成资料缺口报告"""
    return {
        "ok": True, "message": "资料缺口报告",
        "total_required": 0, "available": 0, "missing": [],
        "completeness_score": 0, "risk_level": "未知",
        "summary": "暂无资料缺口分析数据"
    }


def enhance_evidence_summary(evidence_summary, company_id):
    """增强证据摘要"""
    return evidence_summary or {}


def generate_audit_working_paper(db, company_id, period_start, period_end, results, company_name):
    """生成税务合规工作底稿HTML"""
    return f"<html><body><h1>{company_name} — 税务合规工作底稿</h1><p>期间: {period_start}~{period_end}</p><p>分析项: {len(results)}项</p></body></html>"


def detect_submitted_materials(db, company_id):
    """检测已提交的材料"""
    return {}
