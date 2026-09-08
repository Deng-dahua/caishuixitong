# -*- coding: utf-8 -*-
"""
_associate_findings.py —— 多疑点关联推理 (P1)

在 Phase4 跨域协商完成之后调用。
输入：本轮分析触发的所有疑点（每条带 ⑫推理链+⑰定性路径结论）
输出：关联分析矩阵 — clusters / isolated / systemic_score / upgrades
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class FindingRef:
    """疑点引用"""
    finding_id: str
    item: str = ""              # ⑵异常名称
    category: str = ""           # ③所属类别
    level: str = ""              # ④风险等级
    direction: str = ""          # ⑫推理链
    determination: str = ""      # ⑰定性路径结论
    risk_table: str = ""         # ⑱风险表格
    evidence: str = ""           # ⑲证据清单
    applicable_condition: str = ""  # ⑨适用条件
    score: float = 0.0           # ⑤评分


@dataclass
class FindingCluster:
    """疑点群集"""
    cluster_id: str = ""
    label: str = ""
    findings: List[str] = field(default_factory=list)
    anchor_finding: str = ""         # 核心疑点
    relation: str = ""               # 因果链/证据共享/同一交易
    description: str = ""
    combined_score: float = 0.0


@dataclass
class AssociationResult:
    """关联分析结果"""
    clusters: List[Dict[str, Any]] = field(default_factory=list)
    isolated: List[Dict[str, Any]] = field(default_factory=list)
    systemic_score: float = 0.0
    systemic_factors: List[str] = field(default_factory=list)
    upgrades: List[Dict[str, Any]] = field(default_factory=list)


# ================================================================
# 主入口
# ================================================================

def _associate_findings(triggered_findings: List[Dict[str, Any]],
                         pipeline_log: List[str] = None) -> AssociationResult:
    """
    多疑点关联推理主函数。
    
    Args:
        triggered_findings: 本轮分析触发的所有疑点
            每条至少含: id, item, category, level, direction, determination,
                       risk_table, evidence, applicable_condition, score
        pipeline_log: 日志列表
    
    Returns:
        AssociationResult: 含 clusters, isolated, systemic_score, upgrades
    """
    if pipeline_log is None:
        pipeline_log = []
    
    if not triggered_findings:
        return AssociationResult()
    
    # 转换为内部数据结构
    findings = [_to_finding_ref(f) for f in triggered_findings]
    
    if len(findings) <= 1:
        pipeline_log.append("[ASSOC] 仅触发2条疑点，无关联分析需求")
        return AssociationResult()
    
    # Step 1-4: 构建四个关联矩阵
    condition_matrix = _build_condition_matrix(findings)
    evidence_matrix = _build_evidence_overlap(findings)
    causality = _build_causality(findings)
    tax_matrix = _build_tax_overlap(findings)
    
    # Step 5: 聚类
    clusters, isolated = _cluster_findings(
        findings, condition_matrix, evidence_matrix, causality, tax_matrix
    )
    
    # Step 6: 系统性造假评分
    systemic_score, systemic_factors = _calc_systemic_score(
        clusters, findings, condition_matrix, evidence_matrix
    )
    
    # Step 7: 联合增强升级
    upgrades = _apply_joint_enhancement(clusters, findings)
    
    result = AssociationResult(
        clusters=clusters,
        isolated=isolated,
        systemic_score=systemic_score,
        systemic_factors=systemic_factors,
        upgrades=upgrades
    )
    
    pipeline_log.append(
        f"[ASSOC] 多疑点关联完成: {len(clusters)}个集群, "
        f"{sum(len(c.get('findings',[])) for c in clusters)}条关联疑点, "
        f"{len(isolated)}条独立疑点, "
        f"系统性风险={systemic_score:.2f}"
    )
    
    return result


# ================================================================
# Step 1: 适用条件交集
# ================================================================

def _build_condition_matrix(findings: List[FindingRef]) -> Dict[Tuple[int, int], float]:
    """按⑨applicable_condition计算疑点间的适用条件相似度"""
    matrix = {}
    
    for i, f1 in enumerate(findings):
        for j, f2 in enumerate(findings):
            if i >= j:
                continue
            
            c1 = _parse_conditions(f1.applicable_condition)
            c2 = _parse_conditions(f2.applicable_condition)
            
            # 五维度交集（行业/资质/规模/时间/金额）
            dims = ["industry", "taxpayer_type", "scale", "time", "amount"]
            hits = sum(1 for d in dims if c1.get(d) and c2.get(d) and c1[d] == c2[d])
            total = sum(1 for d in dims if c1.get(d) or c2.get(d))
            
            score = hits / max(total, 1)
            matrix[(i, j)] = score
    
    return matrix


def _parse_conditions(cond_text: str) -> Dict[str, str]:
    """解析适用条件文本"""
    result = {}
    if not cond_text:
        return result
    
    # 简单解析: 行业=X; 资质=Y; ...
    parts = cond_text.replace("\n", ";").split(";")
    for part in parts:
        part = part.strip()
        if "=" in part or "：" in part or ":" in part:
            for sep in ["=", "：", ":"]:
                if sep in part:
                    k, v = part.split(sep, 1)
                    result[k.strip()] = v.strip().rstrip("，,。;；")
                    break
    
    return result


# ================================================================
# Step 2: 证据源重叠
# ================================================================

def _build_evidence_overlap(findings: List[FindingRef]) -> Dict[Tuple[int, int], float]:
    """按⑲evidence四层框架计算证据源重叠率"""
    matrix = {}
    
    for i, f1 in enumerate(findings):
        for j, f2 in enumerate(findings):
            if i >= j:
                continue
            
            e1 = _extract_evidence_sources(f1.evidence)
            e2 = _extract_evidence_sources(f2.evidence)
            
            if not e1 or not e2:
                matrix[(i, j)] = 0.0
                continue
            
            overlap = len(e1 & e2)
            union = len(e1 | e2)
            matrix[(i, j)] = overlap / max(union, 1)
    
    return matrix


def _extract_evidence_sources(evidence_text: str) -> set:
    """从证据文本提取证据源关键词"""
    if not evidence_text:
        return set()
    
    EVIDENCE_KEYWORDS = {
        "银行流水", "银行对账单", "付款凭证", "收款记录", "对公账户",
        "发票", "销项发票", "进项发票", "增值税发票", "普通发票",
        "合同", "采购合同", "销售合同", "协议", "订单",
        "运输单", "物流记录", "快递单", "送货单", "装箱单",
        "入库单", "出库单", "验收单", "质检报告", "盘点表",
        "询证函", "对方确认函", "对账记录", "往来邮件",
        "工商信息", "企业信用报告", "关联方清单", "股东名册",
        "申报表", "纳税申报表", "完税证明", "缴款书",
    }
    
    return {kw for kw in EVIDENCE_KEYWORDS if kw in evidence_text}


# ================================================================
# Step 3: 因果关联
# ================================================================

def _build_causality(findings: List[FindingRef]) -> Dict[Tuple[int, int], float]:
    """按⑫direction推理链判断因果关联"""
    matrix = {}
    
    for i, f1 in enumerate(findings):
        for j, f2 in enumerate(findings):
            if i >= j:
                continue
            
            score = _check_causality(f1, f2)
            matrix[(i, j)] = score
            matrix[(j, i)] = score
    
    return matrix


def _check_causality(f1: FindingRef, f2: FindingRef) -> float:
    """检查两个疑点是否存在因果关系"""
    score = 0.0
    
    # 规则1: 同类别高度相关
    if f1.category and f1.category == f2.category:
        score += 0.3
    
    # 规则2: 隐匿收入 → 少缴税款（因果链）
    CAUSAL_CHAINS = [
        (["隐匿收入"], ["少缴税款", "虚开发票"]),
        (["虚列成本"], ["少缴税款"]),
        (["私户收款"], ["隐匿收入", "少缴税款"]),
        (["关联交易"], ["转移利润", "少缴税款"]),
    ]
    for causes, effects in CAUSAL_CHAINS:
        if any(c in (f1.category or "") for c in causes) and any(e in (f2.category or "") for e in effects):
            score += 0.4
            break
    
    # 规则3: 推理链中有相互引用
    if f1.item and f1.item in (f2.direction or ""):
        score += 0.2
    if f2.item and f2.item in (f1.direction or ""):
        score += 0.2
    
    return min(score, 1.0)


# ================================================================
# Step 4: 跨税种关联
# ================================================================

def _build_tax_overlap(findings: List[FindingRef]) -> Dict[Tuple[int, int], float]:
    """按⑱risk_table计算跨税种重叠"""
    matrix = {}
    
    TAX_KEYWORDS = [
        "增值税", "企业所得税", "个人所得税", "印花税", 
        "房产税", "土地使用税", "城建税", "教育附加",
        "土地增值税", "契税", "消费税", "资源税"
    ]
    
    for i, f1 in enumerate(findings):
        for j, f2 in enumerate(findings):
            if i >= j:
                continue
            
            t1 = {kw for kw in TAX_KEYWORDS if kw in (f1.risk_table or "")}
            t2 = {kw for kw in TAX_KEYWORDS if kw in (f2.risk_table or "")}
            
            if not t1 and not t2:
                matrix[(i, j)] = 0.0
                continue
            
            overlap = len(t1 & t2)
            union = len(t1 | t2)
            matrix[(i, j)] = overlap / max(union, 1)
    
    return matrix


# ================================================================
# Step 5: 聚类
# ================================================================

def _cluster_findings(findings: List[FindingRef],
                      condition_matrix: Dict, evidence_matrix: Dict,
                      causality: Dict, tax_matrix: Dict
                      ) -> Tuple[List[Dict], List[Dict]]:
    """四维加权聚类"""
    WEIGHTS = {
        "condition": 0.15,
        "evidence": 0.35,
        "causality": 0.35,
        "tax": 0.15,
    }
    
    # 所有疑点对之间的综合关联度
    pair_scores: Dict[Tuple, float] = {}
    for i in range(len(findings)):
        for j in range(i + 1, len(findings)):
            score = (
                condition_matrix.get((i, j), 0) * WEIGHTS["condition"] +
                evidence_matrix.get((i, j), 0) * WEIGHTS["evidence"] +
                causality.get((i, j), 0) * WEIGHTS["causality"] +
                tax_matrix.get((i, j), 0) * WEIGHTS["tax"]
            )
            pair_scores[(i, j)] = score
    
    # Union-Find 聚类
    parent = list(range(len(findings)))
    
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    
    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py
    
    # 阈值0.6以上合并为同一集群
    for (i, j), score in pair_scores.items():
        if score >= 0.6:
            union(i, j)
    
    # 按根节点分组
    groups: Dict[int, List[int]] = {}
    for i in range(len(findings)):
        root = find(i)
        groups.setdefault(root, []).append(i)
    
    clusters = []
    isolated = []
    
    for root, indices in groups.items():
        if len(indices) == 1:
            idx = indices[0]
            isolated.append({
                "finding_id": findings[idx].finding_id,
                "item": findings[idx].item,
                "description": f"{findings[idx].item}——与其他疑点无显著证据交集，可能为独立违规事件"
            })
        else:
            # 找核心疑点（锚点）——风险等级最高+评分最高
            anchor_idx = max(indices, key=lambda x: (
                {"极高": 4, "高": 3, "中": 2, "低": 1}.get(findings[x].level, 0),
                findings[x].score
            ))
            
            # 判断关系类型
            avg_evidence = sum(evidence_matrix.get((i, j), 0) for i in indices for j in indices if i < j) / max(len(indices), 1)
            avg_causality = sum(causality.get((i, j), 0) for i in indices for j in indices if i < j) / max(len(indices), 1)
            
            if avg_causality > avg_evidence:
                relation = "因果链"
            elif avg_evidence > 0.5:
                relation = "证据共享"
            else:
                relation = "同一交易的不同维度"
            
            cluster_findings_ids = [findings[idx].finding_id for idx in indices]
            combined_score = sum(findings[idx].score for idx in indices) / len(indices)
            
            clusters.append({
                "cluster_id": f"CL-{len(clusters)+1:03d}",
                "label": f"{findings[anchor_idx].item}等{len(indices)}条疑点",
                "findings": cluster_findings_ids,
                "anchor_finding": findings[anchor_idx].finding_id,
                "relation": relation,
                "description": _build_cluster_description([findings[idx] for idx in indices], relation),
                "combined_score": round(combined_score, 1)
            })
    
    return clusters, isolated


def _build_cluster_description(cluster_findings: List[FindingRef], relation: str) -> str:
    """生成群集描述"""
    names = [f.item or f.finding_id for f in cluster_findings[:3]]
    if len(cluster_findings) > 3:
        names.append(f"等{len(cluster_findings)}条疑点")
    
    if relation == "因果链":
        return f"{'、'.join(names)}——存在因果关系，指向同一违法事实"
    elif relation == "证据共享":
        return f"{'、'.join(names)}——共享相同证据源，可能为同一交易的不同表现"
    else:
        return f"{'、'.join(names)}——同一起事实的多个分析维度"


# ================================================================
# Step 6: 系统性造假评分
# ================================================================

def _calc_systemic_score(clusters: List[Dict], findings: List[FindingRef],
                          condition_matrix: Dict, evidence_matrix: Dict
                          ) -> Tuple[float, List[str]]:
    """计算系统性造假概率(0-1)"""
    factors = []
    score = 0.0
    
    # 因子1: 群集数量（多个群集→不同维度的异常同时存在）
    if len(clusters) > 0:
        max_cluster_size = max(len(c.get("findings", [])) for c in clusters)
        # 最大群集≥3→高度可疑
        if max_cluster_size >= 3:
            score += 0.35
            factors.append(f"存在跨维度异常群集(max={max_cluster_size})")
        elif max_cluster_size >= 2:
            score += 0.2
            factors.append(f"存在疑点对(max={max_cluster_size})")
    
    # 因子2: 高风险疑点比例
    high_count = sum(1 for f in findings if f.level in ("极高", "高"))
    if high_count >= 3:
        score += 0.25
        factors.append(f"高/极高风险疑点≥3条(共{high_count}条)")
    elif high_count >= 1:
        score += 0.1
    
    # 因子3: 跨税种影响
    all_taxes = set()
    for f in findings:
        for tax in ["增值税", "企业所得税", "个人所得税", "印花税"]:
            if tax in (f.risk_table or ""):
                all_taxes.add(tax)
    if len(all_taxes) >= 3:
        score += 0.25
        factors.append(f"涉及{len(all_taxes)}个税种({','.join(all_taxes)})")
    elif len(all_taxes) >= 2:
        score += 0.15
    
    # 因子4: 多重证据共享
    total_pairs = sum(1 for i in range(len(findings)) for j in range(i+1, len(findings)))
    if total_pairs > 0:
        high_evidence_pairs = sum(1 for (i, j), v in evidence_matrix.items() if v > 0.5)
        if high_evidence_pairs / total_pairs > 0.3:
            score += 0.15
            factors.append(f"证据源高度重叠({high_evidence_pairs}/{total_pairs}对)")
    
    return round(min(score, 1.0), 2), factors


# ================================================================
# Step 7: 联合增强升级
# ================================================================

def _apply_joint_enhancement(clusters: List[Dict], findings: List[FindingRef]) -> List[Dict]:
    """群集中的疑点联合增强升级"""
    upgrades = []
    LEVEL_ORDER = {"良好": 0, "低": 1, "中": 2, "高": 3, "极高": 4}
    
    for cluster in clusters:
        if len(cluster["findings"]) < 2:
            continue
        
        # 群集中的每条疑点检查升级
        for fid in cluster["findings"]:
            cluster_findings = [f for f in findings if f.finding_id == fid]
            if not cluster_findings:
                continue
            f = cluster_findings[0]
            current_level_idx = LEVEL_ORDER.get(f.level, 2)
            
            # 群集大小≥3且全为"高"→升级为"极高"
            cluster_levels = [LEVEL_ORDER.get(ff.level, 0) for ff in findings 
                             if ff.finding_id in cluster["findings"]]
            if len(cluster["findings"]) >= 3 and all(l >= 3 for l in cluster_levels):
                if current_level_idx < 4:
                    upgrades.append({
                        "finding_id": fid,
                        "from_level": f.level,
                        "to_level": "极高",
                        "reason": f"与{len(cluster['findings'])-1}条同群集疑点联合增强升级（群集={cluster['cluster_id']}）"
                    })
            # 群集大小≥2且全为"中"→升级为"高"
            elif len(cluster["findings"]) >= 2 and current_level_idx <= 2:
                if all(l >= 2 for l in cluster_levels) and any(l >= 3 for l in cluster_levels):
                    upgrades.append({
                        "finding_id": fid,
                        "from_level": f.level,
                        "to_level": "高",
                        "reason": f"与群集中高风险疑点联合增强升级（群集={cluster['cluster_id']}）"
                    })
    
    return upgrades


# ================================================================
# 工具函数
# ================================================================

def _to_finding_ref(f: Dict[str, Any]) -> FindingRef:
    """将字典转换为FindingRef"""
    return FindingRef(
        finding_id=str(f.get("id", f.get("finding_id", "UNKNOWN"))),
        item=str(f.get("item", "")),
        category=str(f.get("category", "")),
        level=str(f.get("level", "中")),
        direction=str(f.get("direction", "")),
        determination=str(f.get("determination", "")),
        risk_table=str(f.get("risk_table", "")),
        evidence=str(f.get("evidence", "")),
        applicable_condition=str(f.get("applicable_condition", "")),
        score=float(f.get("score", 0) or 0),
    )
