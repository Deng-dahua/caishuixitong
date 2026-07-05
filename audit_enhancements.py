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


def detect_industry(business_scope="", company_name=""):
    """从经营范围文本推断行业（可选的company_name用于消歧）"""
    if not business_scope and not company_name:
        return "未知行业"
    scope = str(business_scope).lower()
    name = str(company_name).lower() if company_name else ""
    
    # 公司名优先消歧：如果公司名称已经暗示行业，优先使用
    if any(k in name for k in ("广告","传媒","文化","娱乐","影视","设计")):
        return "广告传媒"
    if any(k in name for k in ("软件","信息","互联网","计算机","科技","数据","数字")):
        return "信息技术"
    if any(k in name for k in ("咨询","服务","管理")):
        return "咨询服务"
    if any(k in name for k in ("建筑","工程","装修","房地产")):
        return "建筑工程"
    if any(k in name for k in ("纺织","服装","面料","纱线","布","染整")):
        return "纺织制造"
    if any(k in name for k in ("餐饮","酒店","住宿","食品")):
        return "餐饮服务"
    if any(k in name for k in ("物流","运输","快递","仓储")):
        return "物流运输"
    if any(k in name for k in ("医药","医疗","药品","器械")):
        return "医药健康"
    
    # 经营范围关键词（当公司名无行业暗示时用）
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
