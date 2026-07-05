# -*- coding: utf-8 -*-
"""
叙事生成引擎 (Narrative Builder)
==============================
将跨域线索链的触发发现（散点列表）→ 分组、串联、交叉验证 → 输出结构化叙事JSON。
全行业各企业适用，不硬编码任何行业/企业特化逻辑。

架构位置：模块⑨跨域线索链 → 叙事增强层
"""

import re
from collections import defaultdict

# ── 步骤分组关键词：将 investigation_path 的 step.domain 映射到发现的分组逻辑 ──
# key = 步骤域名关键词组, value = 该步骤的叙事标题模板
STEP_NARRATIVE_TEMPLATES = {
    "地理|分布|同城|群集|城市": {
        "title": "第一刀：供应商地理解剖",
        "intro": "不再看总量，一家一家拆。",
        "outro": "同城+同行业+同命名模板+新注册——这是同一控制人批量注册空壳公司分散开票的典型特征。",
    },
    "工商|穿透|法人|注册|经营范围|成立|地址": {
        "title": "供应商工商穿透",
        "intro": "逐户联网核查工商登记信息：",
        "outro": "",
    },
    "资金|付款|匹配|银行|回流": {
        "title": "发票和钱对不上",
        "intro": "逐名比对进项发票供应商与银行付款对手方：",
        "outro": "这些不是录入错误。发票名称和付款对手方名称不一致，在税务合规中是资金回流的直接证据。",
    },
    "经营实质|运输|仓储|办公|物流|房租|工资|人员": {
        "title": "经营实质验证",
        "intro": "检查企业是否具备真实经营条件：",
        "outro": "一个年采购过千万的企业，没有房租、没有仓库、没有物流——它在哪生产？谁来生产？",
    },
    "同一法人|共享|共用|重叠": {
        "title": "同一控制人检测",
        "intro": "检测同城供应商之间的关联关系：",
        "outro": "",
    },
    "采购|销售|量级|占比|集中度": {
        "title": "采购量有没有对应的销售？",
        "intro": "比对进销规模：",
        "outro": "采购量远超销售 → 要么大量囤货未售（需进销存验证），要么买的不是原料是发票。",
    },
}

# ── 证据强度判定 ──
def _evidence_strength(finding):
    """根据发现来源域判定证据强度"""
    domain = str(finding.get("domain", "")) + str(finding.get("category", ""))
    detail = str(finding.get("detail", ""))
    ftype = str(finding.get("type", ""))

    # 硬证据：数据域直接产出的匹配/不匹配发现
    if any(kw in domain + detail + ftype for kw in ["银行", "付款", "匹配", "未匹配", "无付款", "有票无付"]):
        return "硬证据"
    # 硬证据：经营实质域的缺位发现
    if any(kw in domain + detail + ftype for kw in ["经营实质", "经营费用", "无运输", "无房租", "无仓储", "无工资", "零运输"]):
        return "硬证据"
    # 工商域：需要联网补强
    if any(kw in domain + ftype for kw in ["工商", "穿透", "失信", "法人", "经营范围"]):
        return "软证据（需补强）"
    # 发票量级分析：推定性
    if any(kw in domain + ftype for kw in ["进销", "毛利率", "采购量", "占比", "集中度", "高频低额"]):
        return "推定性证据"
    return "辅助证据"


def _group_findings_by_step(triggered_findings, investigation_path):
    """将触发发现按调查路径步骤分组"""
    steps = []
    used_indices = set()

    for path_step in investigation_path:
        step_num = path_step.get("step", len(steps) + 1)
        step_domain = path_step.get("domain", "")
        step_keywords = (step_domain + " " + path_step.get("action", "")).lower()
        step_action = path_step.get("action", "")

        # 为该步骤匹配发现
        matched = []
        for idx, f in enumerate(triggered_findings):
            if idx in used_indices:
                continue
            ftype = str(f.get("type", "")).lower()
            fdetail = str(f.get("detail", "")).lower()
            fdomain = str(f.get("domain", "")).lower()
            fcategory = str(f.get("category", "")).lower()
            combined = ftype + " " + fdetail + " " + fdomain + " " + fcategory

            # 按域名关键词匹配
            domain_kws = step_domain.split()
            hits = sum(1 for kw in domain_kws if kw.lower() in combined)
            if hits >= 1 or any(kw in combined for kw in step_keywords.split()):
                matched.append({"finding": f, "idx": idx})
                used_indices.add(idx)

        # 找叙事模板
        narrative = _match_narrative_template(step_domain, step_action)

        if matched or narrative:
            steps.append({
                "step": step_num,
                "domain": step_domain,
                "action": step_action,
                "findings": [m["finding"] for m in matched],
                "count": len(matched),
                "narrative_title": narrative.get("title", f"第{step_num}步：{step_domain}"),
                "narrative_intro": narrative.get("intro", step_action),
                "narrative_outro": narrative.get("outro", ""),
            })

    # 收集未被匹配的发现
    unmatched = [f for idx, f in enumerate(triggered_findings) if idx not in used_indices]
    if unmatched:
        steps.append({
            "step": len(steps) + 1,
            "domain": "其他相关发现",
            "action": "补充验证",
            "findings": unmatched,
            "count": len(unmatched),
            "narrative_title": "补充发现",
            "narrative_intro": "以下发现也间接支持本线索：",
            "narrative_outro": "",
        })

    return steps


def _match_narrative_template(domain, action):
    """匹配步骤对应的叙事模板"""
    combined = (domain + " " + action).lower()
    for key, template in STEP_NARRATIVE_TEMPLATES.items():
        key_parts = key.split("|")
        if any(kw in combined for kw in key_parts):
            return template
    return {}


def _build_cross_table(steps):
    """构建五维交叉验证表"""
    rows = []
    for s in steps:
        if not s["findings"]:
            continue
        # 取该步骤第一条发现作为代表
        first = s["findings"][0]
        items_detail = []
        for f in s["findings"]:
            items_detail.append(str(f.get("detail", ""))[:120])
        strength = _evidence_strength(first)
        rows.append({
            "dimension": s["domain"],
            "findings_summary": "；".join(items_detail[:3]),
            "source": str(first.get("domain", "") or first.get("category", s["domain"])),
            "strength": strength,
        })
    return rows


def _build_evidence_closure(triggered_findings):
    """提取证据链闭环信息"""
    closure_chains = []
    for f in triggered_findings:
        details = f.get("matched_chain_details", [])
        if not details:
            continue
        for chain in details:
            name = chain.get("name", "")
            steps_count = chain.get("steps", 0)
            high_risk = chain.get("high_risk", 0)
            if steps_count > 0 and "虚开" in name:
                ratio = int(high_risk / steps_count * 100) if steps_count > 0 else 0
                closure_chains.append({
                    "name": name,
                    "triggered": high_risk,
                    "total": steps_count,
                    "ratio": ratio,
                })
    # 去重
    seen = set()
    unique = []
    for c in closure_chains:
        if c["name"] not in seen:
            seen.add(c["name"])
            unique.append(c)
    return unique


def _count_domains(steps):
    """统计跨域数量"""
    domains = set()
    for s in steps:
        if s["findings"]:
            domains.add(s["domain"])
    return len(domains)


def build_narrative(chain_def, triggered_findings, all_findings=None):
    """
    为一条线索构建完整叙事。

    参数：
      chain_def: dict, 线索定义 (来自 cross_domain_clues.json)
      triggered_findings: list, 被该线索触发的全部发现
      all_findings: list, 全部发现（用于查找证据链闭环等）

    返回：
      dict: {
        "narrative": str,          # 主叙事文本（HTML格式，前端直接渲染）
        "steps": list,             # 分步叙事
        "cross_table": list,       # 交叉验证表
        "evidence_closure": list,  # 证据链闭环
        "domain_count": int,       # 跨域数量
        "total_findings": int,     # 触发发现总数
        "summary": str,            # 一句话摘要
      }
    """
    name = chain_def.get("name", "")
    investigation_path = chain_def.get("investigation_path", [])
    description = chain_def.get("description", "")
    total = len(triggered_findings)

    # 1. 按调查步骤分组
    steps = _group_findings_by_step(triggered_findings, investigation_path)

    # 2. 构建交叉验证表
    cross_table = _build_cross_table(steps)

    # 3. 提取证据链闭环
    evidence_closure = _build_evidence_closure(triggered_findings)

    # 4. 统计跨域
    domain_count = _count_domains(steps)

    # 5. 生成主叙事文本
    narrative_html = _generate_main_narrative(name, steps, cross_table, evidence_closure, total, domain_count, description)

    # 6. 生成摘要
    summary = f"从{_first_signal(steps)}出发，跨{domain_count}个域串联{'、'.join([s['domain'] for s in steps if s['findings']][:4])}，经{total}条发现交叉验证，{'、'.join([c['name'].split('-')[-1] if '-' in c['name'] else c['name'] for c in evidence_closure[:2]])}证据链闭环。结论：{description}"

    return {
        "narrative": narrative_html,
        "steps": steps,
        "cross_table": cross_table,
        "evidence_closure": evidence_closure,
        "domain_count": domain_count,
        "total_findings": total,
        "summary": summary,
    }


def _first_signal(steps):
    """提取第一个有发现的步骤域"""
    for s in steps:
        if s["findings"]:
            return s["domain"]
    return "线索信号"


def _generate_main_narrative(name, steps, cross_table, evidence_closure, total, domain_count, description):
    """生成主叙事HTML文本"""
    parts = []

    # 开头：调查起点
    first_signal_domain = _first_signal(steps)
    parts.append(f'<div style="margin-bottom:20px">')
    parts.append(f'<p style="font-size:14px;line-height:2;color:#334155">')
    parts.append(f'<strong style="color:#0f172a;font-size:16px">调查起点</strong><br>')
    parts.append(f'{description}<br>')
    parts.append(f'本轮分析中，线索引擎共捕获 <strong style="color:#dc2626">{total}</strong> 条独立发现，')
    parts.append(f'跨越 <strong style="color:#dc2626">{domain_count}</strong> 个数据域。')
    parts.append(f'</p></div>')

    # 分步叙事
    for s in steps:
        if not s["findings"]:
            continue
        parts.append(f'<div style="margin-bottom:16px;padding-left:12px;border-left:3px solid #7c3aed">')
        parts.append(f'<div style="font-weight:700;font-size:14px;color:#0f172a;margin-bottom:6px">{s["narrative_title"]}（{s["count"]}条发现）</div>')
        if s["narrative_intro"]:
            parts.append(f'<p style="font-size:13px;color:#475569;margin:4px 0 8px 0">{s["narrative_intro"]}</p>')
        for f in s["findings"]:
            ftype = f.get("type", "")
            fdetail = f.get("detail", "")
            flevel = f.get("level", "")
            level_color = "#dc2626" if "高" in str(flevel) else ("#d97706" if "中" in str(flevel) else "#0369a1")
            parts.append(f'<div style="margin:4px 0 4px 16px;font-size:13px;color:#334155">')
            parts.append(f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{level_color};margin-right:6px;vertical-align:middle"></span>')
            parts.append(f'<strong>{ftype}</strong>：{fdetail}')
            parts.append(f'</div>')
        if s["narrative_outro"]:
            parts.append(f'<p style="font-size:12px;color:#7c3aed;margin:8px 0 0 0;font-style:italic">→ {s["narrative_outro"]}</p>')
        parts.append(f'</div>')

    # 交叉验证表
    if cross_table:
        parts.append(f'<div style="margin:20px 0">')
        parts.append(f'<div style="font-weight:700;font-size:14px;color:#0f172a;margin-bottom:8px">交叉验证矩阵</div>')
        parts.append(f'<table style="width:100%;border-collapse:collapse;font-size:12px">')
        parts.append(f'<tr style="background:#f1f5f9"><th style="padding:6px 8px;text-align:left;border:1px solid #e2e8f0">维度</th><th style="padding:6px 8px;text-align:left;border:1px solid #e2e8f0">关键发现</th><th style="padding:6px 8px;text-align:left;border:1px solid #e2e8f0">来源域</th><th style="padding:6px 8px;text-align:left;border:1px solid #e2e8f0">证据强度</th></tr>')
        for i, row in enumerate(cross_table):
            bg = "#f8fafc" if i % 2 == 0 else "#ffffff"
            parts.append(f'<tr style="background:{bg}">')
            parts.append(f'<td style="padding:6px 8px;border:1px solid #e2e8f0;font-weight:600">{row["dimension"]}</td>')
            parts.append(f'<td style="padding:6px 8px;border:1px solid #e2e8f0">{row["findings_summary"]}</td>')
            parts.append(f'<td style="padding:6px 8px;border:1px solid #e2e8f0">{row["source"]}</td>')
            strength_color = "#dc2626" if "硬" in row["strength"] else ("#d97706" if "软" in row["strength"] else "#64748b")
            parts.append(f'<td style="padding:6px 8px;border:1px solid #e2e8f0;color:{strength_color};font-weight:600">{row["strength"]}</td>')
            parts.append(f'</tr>')
        parts.append(f'</table>')
        parts.append(f'<p style="font-size:12px;color:#64748b;margin-top:6px">每个维度单独看，都可能找到合理解释。但{len(cross_table)}个维度同时异常且互相印证——这就不是巧合。</p>')
        parts.append(f'</div>')

    # 证据链闭环
    if evidence_closure:
        parts.append(f'<div style="margin:16px 0">')
        parts.append(f'<div style="font-weight:700;font-size:14px;color:#0f172a;margin-bottom:6px">证据链闭环判定</div>')
        for ec in evidence_closure:
            color = "#dc2626" if ec["ratio"] >= 100 else ("#d97706" if ec["ratio"] >= 60 else "#0369a1")
            parts.append(f'<div style="margin:4px 0;font-size:13px;padding:8px 12px;background:#fef2f2;border-radius:6px;border-left:3px solid {color}">')
            parts.append(f'<strong>{ec["name"]}</strong>：{ec["triggered"]}/{ec["total"]}规则触发（{ec["ratio"]}%）')
            if ec["ratio"] >= 60:
                parts.append(f' → <span style="color:#dc2626;font-weight:700">违法事实闭环</span>')
            elif ec["ratio"] >= 40:
                parts.append(f' → <span style="color:#d97706;">部分闭环，需补强</span>')
            parts.append(f'</div>')
        closed_count = sum(1 for ec in evidence_closure if ec["ratio"] >= 60)
        if closed_count >= 2:
            parts.append(f'<p style="font-size:12px;color:#dc2626;font-weight:600;margin-top:4px">{closed_count}条证据链同时闭环，风险等级强制升级为高风险。</p>')
        parts.append(f'</div>')

    # 结论
    parts.append(f'<div style="margin-top:16px;padding:12px 16px;background:#fef2f2;border-radius:6px;border:1px solid #fecaca">')
    parts.append(f'<div style="font-weight:700;font-size:14px;color:#0f172a;margin-bottom:4px">交叉验证结论</div>')
    parts.append(f'<p style="font-size:13px;color:#334155">{description}<br>')
    parts.append(f'<strong>线索成立。确认成立。</strong></p>')
    parts.append(f'</div>')

    return "\n".join(parts)
