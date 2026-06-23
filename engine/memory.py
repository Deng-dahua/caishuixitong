"""
稽查引擎记忆系统 — 历史分析经验积累与检索

设计理念：
  每次分析完成后，提取"指纹"（行业+模式+关键信号+风险评分），
  存入记忆库。后续分析时检索相似案例，为当前分析提供参考。
  
  这是引擎从"每次都从零开始"到"越用越聪明"的关键一步。
"""

import json
import os
import time
from datetime import datetime

# 记忆存储路径
_MEMORY_PATH = os.path.join(os.path.dirname(__file__), '..', 'static', 'audit_memory.json')


def save_analysis_memory(ctx, synthesis):
    """
    保存分析记忆 — 提取分析指纹存入记忆库
    
    指纹字段：
      - timestamp: 分析时间
      - industry: 行业
      - biz_model: 经营模式（制造业/贸易/服务）
      - scale: 规模
      - risk_score: 综合风险评分
      - risk_level: 风险等级
      - red_flags: 红灯信号列表
      - yellow_flags: 黄灯信号列表
      - pattern_hits: Phase 3 命中的信号叠加模式
      - total_findings: 总发现数
      - core_issues: 核心问题摘要
      - snapshot: 财务快照
    """
    memory = _load_memory()
    
    fs = ctx.financial_snapshot
    cp = ctx.company_profile
    
    fingerprint = {
        "timestamp": datetime.now().isoformat(),
        "industry": cp.get("industry", ""),
        "biz_model": cp.get("biz_model", ""),
        "scale": cp.get("scale", ""),
        "risk_score": synthesis.get("risk_score", 0) if synthesis else 0,
        "risk_level": synthesis.get("overall_risk", "未知") if synthesis else "未知",
        "red_flags": [f["type"] for f in ctx.red_flags] if ctx.red_flags else [],
        "yellow_flags": [f["type"] for f in ctx.yellow_flags] if ctx.yellow_flags else [],
        "pattern_hits": synthesis.get("cross_validated_patterns", 0) if synthesis else 0,
        "total_findings": synthesis.get("total_findings", 0) if synthesis else 0,
        "has_processing": ctx.has_processing_fee,
        "has_personal_payments": ctx.has_personal_payments,
        "supplier_concentration": ctx.supplier_concentration,
        "customer_concentration": ctx.customer_concentration,
        "data_quality_score": ctx.data_quality_score,
        "snapshot": {
            "sales": fs.get("total_sales", 0),
            "purchases": fs.get("total_purchases", 0),
            "bank_in": fs.get("total_bank_in", 0),
            "bank_out": fs.get("total_bank_out", 0),
            "salary": fs.get("total_salary", 0),
            "gross_margin_pct": fs.get("gross_margin_pct", 0),
        }
    }
    
    memory.append(fingerprint)
    
    # 限制记忆数量（保留最近500条）
    if len(memory) > 500:
        memory = memory[-500:]
    
    _save_memory(memory)
    return len(memory)


def query_similar_cases(ctx):
    """
    检索相似案例 — 根据当前企业画像查找历史上同行业/同模式案例
    
    返回：
      {
        "total_records": 总记忆数,
        "similar_count": 相似案例数,
        "same_industry": 同行业案例,
        "same_model": 同经营模式案例,
        "avg_risk_score": 相似案例平均风险分,
        "common_red_flags": 相似案例常见红灯信号,
        "insight": 基于历史数据的洞察文本
      }
    """
    memory = _load_memory()
    
    if not memory:
        return {
            "total_records": 0,
            "similar_count": 0,
            "same_industry": [],
            "same_model": [],
            "avg_risk_score": 0,
            "common_red_flags": [],
            "insight": "暂无历史分析记录，这是首次分析。"
        }
    
    cp = ctx.company_profile
    industry = cp.get("industry", "")
    biz_model = cp.get("biz_model", "")
    
    # 同行业案例
    same_industry = [m for m in memory if m.get("industry") == industry and industry]
    # 同模式案例
    same_model = [m for m in memory if m.get("biz_model") == biz_model and biz_model]
    # 完全匹配（行业+模式）
    exact_match = [m for m in memory if m.get("industry") == industry and m.get("biz_model") == biz_model and industry and biz_model]
    
    similar = exact_match if exact_match else (same_industry if same_industry else same_model)
    
    # 统计常见信号
    from collections import Counter
    red_counter = Counter()
    for m in similar:
        for flag in m.get("red_flags", []):
            red_counter[flag] += 1
    common_red = red_counter.most_common(5)
    
    # 平均风险评分
    scores = [m.get("risk_score", 0) for m in similar if m.get("risk_score")]
    avg_score = sum(scores) / len(scores) if scores else 0
    
    # 生成洞察
    insight = _generate_insight(ctx, similar, common_red, avg_score)
    
    return {
        "total_records": len(memory),
        "similar_count": len(similar),
        "same_industry": same_industry,
        "same_model": same_model,
        "avg_risk_score": round(avg_score, 1),
        "common_red_flags": common_red,
        "insight": insight,
    }


def _generate_insight(ctx, similar, common_red, avg_score):
    """基于历史数据生成洞察文本"""
    if not similar:
        return "暂无同行业/同模式的历史分析记录。这是首次分析。"
    
    cp = ctx.company_profile
    industry = cp.get("industry", "综合")
    biz_model = cp.get("biz_model", "")
    
    lines = []
    lines.append(f"系统记忆库中有{len(similar)}条{industry}{biz_model}企业的历史分析记录。")
    
    if avg_score > 0:
        avg_level = "极高风险" if avg_score >= 70 else ("高风险" if avg_score >= 50 else "中风险")
        lines.append(f"同类型企业历史平均风险评分{avg_score:.0f}/100（{avg_level}）。")
    
    if common_red:
        lines.append(f"同类型企业常见红灯信号：")
        for flag, count in common_red[:3]:
            lines.append(f"  · {flag}（出现{count}次）")
    
    # 对比当前企业与历史均值
    fs = ctx.financial_snapshot
    current_score = 0  # will be set later
    if avg_score > 60:
        lines.append(f"该行业整体风险偏高，当前企业的异常需要结合行业特征综合判断。")
    elif avg_score < 30:
        lines.append(f"该行业整体风险较低，当前企业的异常信号相比同行更为突出，需要重点关注。")
    
    lines.append(f"随着记忆库积累更多案例，洞察将越来越精准。")
    
    return "\n".join(lines)


def _load_memory():
    """从文件加载记忆"""
    try:
        if os.path.exists(_MEMORY_PATH):
            with open(_MEMORY_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_memory(memory):
    """保存记忆到文件"""
    try:
        os.makedirs(os.path.dirname(_MEMORY_PATH), exist_ok=True)
        with open(_MEMORY_PATH, 'w', encoding='utf-8') as f:
            json.dump(memory, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
