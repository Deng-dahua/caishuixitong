"""
稽查引擎记忆系统 — 历史分析经验积累与检索

设计理念：
  每次分析完成后，提取"指纹"（行业+模式+关键信号+风险评分），
  存入记忆库。后续分析时检索相似案例，为当前分析提供参考。
  
  这是引擎从"每次都从零开始"到"越用越聪明"的关键一步。

═════ 行业推断铁律（写入引擎记忆中，随记忆系统永续生效）═════
  行业推断唯一依据 = 销项发票品名
  不参考进项发票品名
  WHY: 销项=企业实际经营产出（卖什么就是什么行业）
       进项=采购投入/成本结构（买什么不代表行业）
  代码位置: engine/phase1_triage.py _infer_industry_from_goods()
            main.py _extract_material_intel() 第5步

═════ 系统稽查判定规则（2026-06-28 老邓亲授，写入引擎记忆）═════

【规则一：公司身份锚定】
  所有分析以当前账套公司为锚点（侧边栏公司名+信用代码）
  销项发票的销售方只有一个=账套公司
  进项发票的购买方只有一个=账套公司
  代码: engine/pipeline.py 综合判断层

【规则二：发票方向自动判定】
  上传发票→逐行扫描购买方/销售方名称+税号→与公司身份比对
  公司名/USCC在购买方→进项 | 在销售方→销项 | 双方都不含公司→存疑
  存疑发票排除出分析，不参与记账和风险计算
  代码: engine/pipeline.py 发票方向判定

【规则三：综合判断·四方交叉验证】
  文件名暗示→列头推理→数据扫描（买卖方身份）→公司匹配
  证据一致→高置信度 | 冲突→优先数据推理 | 全不匹配→存疑
  代码: engine/pipeline.py 综合判断层

【规则四：进项发票再分类】
  进项+含"有效抵扣税额/勾选状态/勾选时间"→进项抵扣认证（抵税用）
  进项+无上述列→进项发票（记账用）
  两种用途不可混淆
  代码: engine/pipeline.py 列头推理

【规则五：服务行业闸门】
  销项品名金税分类编码∈服务行业（广告/IT/咨询/金融等25类）
  →跳过进销存台账/BOM表/进销比/毛利率行业对标
  三层闸门：管道层→域分析层→引擎输出层
  配置: static/industry_data.json service_industries

【规则六：品名级精准过滤】
  公司既有服务又有实物品名→服务跳过进销存，实物正常检查
  按品名金税编码逐项判定，不搞公司级别一刀切
  代码: engine/pipeline.py _is_service_goods()

【规则七：配置外部化】
  服务行业编码→static/industry_data.json
  文件名映射→static/filename_type_map.json
  列结构锚点→static/type_anchors.json
  新增行业/类型只改JSON，不改Python代码

═══ 缺失的关键规则（2026-06-28 补充写入） ═══

【规则八：只读有效信息，空白全部忽略】
  解析Excel/文件时，跳过所有空白行、小计行、合计行、重复表头行
  只统计有实际数据的有效记录
  140行Excel→可能只有7条有效，不能把空行计入分析
  代码: main.py _is_summary_row() / engine/pipeline.py 有效行过滤

【规则九：文件类型识别体系（13类）】
  引擎必须通过四步推理识别文件类型，不得仅靠文件名或单一关键词：
  bank_statement / sales_invoice / purchase_invoice / input_vat_deduction /
  salary / salary_tax / social_security / housing_fund / voucher /
  contract / inventory / trial_balance / tax_declaration
  代码: engine/pipeline.py 综合判断层 / static/filename_type_map.json

【规则十：存疑发票绝对排除】
  买卖双方都有名称+税号但都不含当前公司→此发票不属于本账套
  标记"存疑"后必须排除出所有后续分析（记账/风险计算/税务推断）
  不得以任何默认值（如默认进项）继续处理
  代码: engine/pipeline.py 存疑标记+排除逻辑

【规则十一：账套数据物理隔离】
  所有分析数据按company_id隔离，文件存储在{company_id}/子目录
  删除账套=32张数据表级联删除+文件目录全部清除
  不同账套的分析结果互不影响
  代码: engine/pipeline.py _get_company_upload_dir() / archives.py delete_company()

═══ 引擎自省能力 ═══
  每次分析完成后，引擎必须自问：
  1. 公司身份是否已锚定？（规则一）
  2. 发票方向是否已比对判定？（规则二）
  3. 存疑发票是否已排除？（规则十）
  4. 空白行是否已跳过？（规则八）
  5. 服务行业是否已跳过进销存？（规则五）
  6. 品名是否精准过滤？（规则六）
  上述6项全部通过，本次分析才算可靠。

═════ 假设-验证推理引擎（引擎"思考"能力）═════
  每条重要发现 → 生成2-3个竞争假设 → 逐条证据验证 → 加权判决
  代码位置: engine/hypothesis_engine.py run_hypothesis_verification()
  调用位置: main.py ~22383行（方法论过滤后、明细注入前）
══════════════════════════════════════════════════════════════
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
    检索相似案例 v2 — 加权关键词匹配（准向量检索，无需embedding依赖）
    
    匹配维度（加权）：
      - 同行业（精确匹配）: 权重 3
      - 行业关键词重叠: 权重 2  
      - 同经营模式: 权重 2
      - 收入规模相近: 权重 1
    
    返回结构同v1，增加 similarity_scores 和 calibrated_thresholds
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
            "insight": "暂无历史分析记录。",
            "calibrated_thresholds": {},
        }
    
    cp = ctx.company_profile
    industry = cp.get("industry", "")
    biz_model = cp.get("biz_model", "")
    current_sales = ctx.financial_snapshot.get("total_sales", 0)
    
    # ── 加权相似度评分 ──
    scored_cases = []
    for m in memory:
        score = 0
        m_industry = m.get("industry", "")
        m_model = m.get("biz_model", "")
        m_sales = (m.get("snapshot", {}) or {}).get("sales", 0)
        
        # 同行业精确匹配
        if industry and m_industry == industry:
            score += 3
        
        # 行业关键词重叠（模糊匹配）
        if industry and m_industry:
            ind_words = set(industry)
            m_words = set(m_industry)
            overlap = len(ind_words & m_words) / max(len(ind_words | m_words), 1)
            score += overlap * 2
        
        # 同经营模式
        if biz_model and m_model == biz_model:
            score += 2
        
        # 收入规模相近（同数量级）
        if current_sales > 0 and m_sales > 0:
            ratio = max(current_sales, m_sales) / max(min(current_sales, m_sales), 1)
            if ratio < 3:  # 3倍以内视为相近
                score += 1
        
        if score > 0:
            scored_cases.append((score, m))
    
    scored_cases.sort(key=lambda x: -x[0])
    
    # 取相似度>=2 的案例
    similar = [m for s, m in scored_cases if s >= 2]
    exact_match = [m for s, m in scored_cases if s >= 4]
    same_industry = [m for m in memory if m.get("industry") == industry and industry]
    same_model = [m for m in memory if m.get("biz_model") == biz_model and biz_model]
    
    # 统计常见信号
    from collections import Counter
    red_counter = Counter()
    for m in similar[:50]:
        for flag in m.get("red_flags", []):
            red_counter[flag] += 1
    common_red = red_counter.most_common(5)
    
    scores = [m.get("risk_score", 0) for m in similar if m.get("risk_score")]
    avg_score = sum(scores) / len(scores) if scores else 0
    
    insight = _generate_insight(ctx, similar, common_red, avg_score)
    
    # ── 历史数据校准阈值 ──
    calibrated = _calibrate_thresholds_from_history(memory, industry, biz_model)
    
    return {
        "total_records": len(memory),
        "similar_count": len(similar),
        "exact_match_count": len(exact_match),
        "same_industry": same_industry,
        "same_model": same_model,
        "avg_risk_score": round(avg_score, 1),
        "common_red_flags": common_red,
        "insight": insight,
        "calibrated_thresholds": calibrated,
    }


def _calibrate_thresholds_from_history(memory, industry, biz_model):
    """从历史数据中自动校准行业阈值。
    
    对同行业企业的毛利率、购销比、供应商/客户集中度等指标
    进行统计分析，产出动态阈值替代硬编码。
    """
    if not memory:
        return {}
    
    # 筛选同行业案例
    industry_cases = [m for m in memory if m.get("industry") == industry and industry]
    if len(industry_cases) < 3:
        industry_cases = [m for m in memory if m.get("biz_model") == biz_model and biz_model]
    if len(industry_cases) < 3:
        industry_cases = memory[-50:]  # 兜底用最近50条
    
    # 提取财务快照
    snapshots = [(m.get("snapshot") or {}) for m in industry_cases]
    
    gross_margins = [s.get("gross_margin_pct", 0) for s in snapshots if s.get("gross_margin_pct", 0) != 0]
    supplier_concs = [m.get("supplier_concentration", 0) for m in industry_cases if m.get("supplier_concentration")]
    customer_concs = [m.get("customer_concentration", 0) for m in industry_cases if m.get("customer_concentration")]
    data_scores = [m.get("data_quality_score", 0) for m in industry_cases if m.get("data_quality_score")]
    
    def _percentile(data, p):
        if not data: return 0
        s = sorted(data)
        idx = int(len(s) * p / 100)
        return s[min(idx, len(s)-1)]
    
    calibrated = {}
    
    if len(gross_margins) >= 3:
        calibrated["gross_margin_low"] = _percentile(gross_margins, 10)  # P10 = 异常低
        calibrated["gross_margin_high"] = _percentile(gross_margins, 90)  # P90 = 异常高
        calibrated["gross_margin_median"] = _percentile(gross_margins, 50)
        calibrated["gross_margin_sample_size"] = len(gross_margins)
    
    if len(supplier_concs) >= 3:
        calibrated["supplier_concentration_warn"] = _percentile(supplier_concs, 75)  # P75 = 预警
        calibrated["supplier_concentration_sample_size"] = len(supplier_concs)
    
    if len(customer_concs) >= 3:
        calibrated["customer_concentration_warn"] = _percentile(customer_concs, 75)
        calibrated["customer_concentration_sample_size"] = len(customer_concs)
    
    if len(data_scores) >= 3:
        calibrated["data_quality_avg"] = sum(data_scores) / len(data_scores)
    
    return calibrated


def record_user_feedback(feedback):
    """记录用户反馈 — 对分析结论的确认/修正/补充。
    
    feedback 结构:
      {
        "finding_type": "购销严重倒挂",  # 被反馈的发现类型
        "action": "confirm" | "dismiss" | "adjust",  # 确认/驳回/调整
        "adjusted_score": 8,            # 调整后的评分(可选)
        "note": "确实是关联交易问题",    # 备注
        "timestamp": "2024-01-15T10:00"
      }
    
    反馈数据用于：
      1. 信号权重自适应调整
      2. 虚假信号降权
      3. 漏报信号追偿
    """
    feedback_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'audit_feedback.json')
    
    try:
        if os.path.exists(feedback_path):
            with open(feedback_path, 'r', encoding='utf-8') as f:
                feedbacks = json.load(f)
        else:
            feedbacks = []
    except Exception:
        feedbacks = []
    
    feedback["timestamp"] = feedback.get("timestamp") or datetime.now().isoformat()
    feedbacks.append(feedback)
    
    # 限制1000条
    if len(feedbacks) > 1000:
        feedbacks = feedbacks[-1000:]
    
    try:
        os.makedirs(os.path.dirname(feedback_path), exist_ok=True)
        with open(feedback_path, 'w', encoding='utf-8') as f:
            json.dump(feedbacks, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    
    # ── 根据反馈调整信号权重 ──
    adjusted = _adjust_signal_weights_from_feedback(feedbacks)
    
    return {
        "ok": True,
        "total_feedbacks": len(feedbacks),
        "adjusted_weights": adjusted,
    }


def _adjust_signal_weights_from_feedback(feedbacks):
    """根据用户反馈调整信号权重。
    
    - confirm → 信号权重 +0.1（确认有效）
    - dismiss → 信号权重 -0.2（驳回=误报）
    - adjust → 按调整幅度微调
    """
    from collections import defaultdict
    
    weight_deltas = defaultdict(float)
    
    for fb in feedbacks[-50:]:  # 只看最近50条反馈
        ftype = fb.get("finding_type", "")
        action = fb.get("action", "")
        
        if action == "confirm":
            weight_deltas[ftype] += 0.1
        elif action == "dismiss":
            weight_deltas[ftype] -= 0.2
        elif action == "adjust" and fb.get("adjusted_score"):
            orig = fb.get("original_score", 5)
            adj = fb.get("adjusted_score", 5)
            weight_deltas[ftype] += (adj - orig) * 0.05
    
    # 钳制在 0.3 ~ 2.0 范围
    clamped = {}
    for k, v in weight_deltas.items():
        clamped[k] = round(max(0.3, min(2.0, 1.0 + v)), 2)
    
    return clamped


def get_adaptive_signal_weights(ctx, base_weights=None):
    """获取自适应信号权重 — 融合行业配置 + 历史反馈调整。
    
    优先级：用户反馈调整 > 行业配置 > 默认值1.0
    """
    # 行业配置权重
    ip = ctx.industry_profile or {}
    industry_weights = ip.get("signal_weights", {})
    
    # 用户反馈权重
    feedback_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'audit_feedback.json')
    adjusted_weights = {}
    try:
        if os.path.exists(feedback_path):
            with open(feedback_path, 'r', encoding='utf-8') as f:
                feedbacks = json.load(f)
            adjusted_weights = _adjust_signal_weights_from_feedback(feedbacks)
    except Exception:
        pass
    
    # 合并：基础默认1.0 → 行业配置覆盖 → 反馈调整覆盖
    merged = {}
    all_signal_names = set(list(industry_weights.keys()) + list(adjusted_weights.keys()))
    if base_weights:
        all_signal_names.update(base_weights.keys())
    
    for name in all_signal_names:
        w = base_weights.get(name, 1.0) if base_weights else 1.0
        w = industry_weights.get(name, w)
        w = adjusted_weights.get(name, w)
        merged[name] = round(w, 2)
    
    return merged


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
