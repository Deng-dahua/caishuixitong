"""
稽查增强模块 - 补充材料缺口报告/数据质量评估/行业检测等功能
"""
from database import SessionLocal


def assess_data_quality(db, company_id, period_start, period_end):
    """评估上传数据的质量"""
    return {
        "total_tables": 0, "tables_with_data": 0,
        "completeness_score": 0, "quality_issues": []
    }


def check_analysis_data_availability(db, company_id, period_start, period_end):
    """检查各分析域所需数据是否可用 - 返回受限分析列表"""
    return []


def detect_industry(business_scope=""):
    """从经营范围文本推断行业"""
    if not business_scope:
        return "未知行业"
    scope = str(business_scope).lower()
    if any(k in scope for k in ("纺织","服装","面料","纱线")): return "纺织制造"
    if any(k in scope for k in ("建筑","工程","装修","房地产")): return "建筑工程"
    if any(k in scope for k in ("软件","信息","互联网","计算机")): return "信息技术"
    if any(k in scope for k in ("餐饮","酒店","住宿","食品")): return "餐饮服务"
    if any(k in scope for k in ("物流","运输","快递","仓储")): return "物流运输"
    if any(k in scope for k in ("广告","传媒","文化","娱乐")): return "广告传媒"
    if any(k in scope for k in ("咨询","服务","管理")): return "咨询服务"
    if any(k in scope for k in ("医药","医疗","药品","器械")): return "医药健康"
    return "商贸"


def get_industry_benchmark(industry):
    """获取行业基准值 - 返回格式需匹配tax_risk.py的用法"""
    benchmarks = {
        "纺织制造": {
            "name": "纺织制造", "vat_burden_min": 1.5, "vat_burden_max": 5.0,
            "gross_margin_min": 8, "gross_margin_max": 25, "net_margin_min": 2, "net_margin_max": 10,
            "per_person_rev_low": 20, "per_person_rev_high": 80, "io_ratio_low": 0.5, "io_ratio_high": 1.0
        },
        "信息技术": {
            "name": "信息技术", "vat_burden_min": 2.0, "vat_burden_max": 8.0,
            "gross_margin_min": 40, "gross_margin_max": 80, "net_margin_min": 10, "net_margin_max": 35,
            "per_person_rev_low": 30, "per_person_rev_high": 150, "io_ratio_low": 0.1, "io_ratio_high": 0.5
        },
        "建筑工程": {
            "name": "建筑工程", "vat_burden_min": 2.0, "vat_burden_max": 6.0,
            "gross_margin_min": 5, "gross_margin_max": 20, "net_margin_min": 2, "net_margin_max": 8,
            "per_person_rev_low": 40, "per_person_rev_high": 150, "io_ratio_low": 0.6, "io_ratio_high": 0.92
        },
        "餐饮服务": {
            "name": "餐饮服务", "vat_burden_min": 2.0, "vat_burden_max": 6.0,
            "gross_margin_min": 45, "gross_margin_max": 70, "net_margin_min": 5, "net_margin_max": 20,
            "per_person_rev_low": 8, "per_person_rev_high": 25, "io_ratio_low": 0.2, "io_ratio_high": 0.55
        },
        "物流运输": {
            "name": "物流运输", "vat_burden_min": 1.5, "vat_burden_max": 5.0,
            "gross_margin_min": 10, "gross_margin_max": 30, "net_margin_min": 3, "net_margin_max": 12,
            "per_person_rev_low": 20, "per_person_rev_high": 80, "io_ratio_low": 0.3, "io_ratio_high": 0.7
        },
        "广告传媒": {
            "name": "广告传媒", "vat_burden_min": 1.5, "vat_burden_max": 5.0,
            "gross_margin_min": 30, "gross_margin_max": 65, "net_margin_min": 5, "net_margin_max": 25,
            "per_person_rev_low": 15, "per_person_rev_high": 60, "io_ratio_low": 0.1, "io_ratio_high": 0.5
        },
        "咨询服务": {
            "name": "咨询服务", "vat_burden_min": 2.0, "vat_burden_max": 8.0,
            "gross_margin_min": 50, "gross_margin_max": 90, "net_margin_min": 15, "net_margin_max": 45,
            "per_person_rev_low": 20, "per_person_rev_high": 80, "io_ratio_low": 0.05, "io_ratio_high": 0.3
        },
        "医药健康": {
            "name": "医药健康", "vat_burden_min": 3.0, "vat_burden_max": 9.0,
            "gross_margin_min": 30, "gross_margin_max": 70, "net_margin_min": 8, "net_margin_max": 30,
            "per_person_rev_low": 25, "per_person_rev_high": 100, "io_ratio_low": 0.2, "io_ratio_high": 0.6
        },
    }
    return benchmarks.get(industry, {
        "name": industry or "未知", "vat_burden_min": 0.5, "vat_burden_max": 8.0,
        "gross_margin_min": 5, "gross_margin_max": 60, "net_margin_min": 1, "net_margin_max": 30,
        "per_person_rev_low": 15, "per_person_rev_high": 200, "io_ratio_low": 0.2, "io_ratio_high": 0.95
    })


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
    """生成稽查工作底稿HTML"""
    return f"<html><body><h1>{company_name} — 稽查工作底稿</h1><p>期间: {period_start}~{period_end}</p><p>分析项: {len(results)}项</p></body></html>"


def detect_submitted_materials(db, company_id):
    """检测已提交的材料"""
    return {}
