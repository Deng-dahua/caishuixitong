# -*- coding: utf-8 -*-
"""税务疑点库深度字段消费引擎 —— 让引擎真正"看懂"精写后的23字段规则。

按老邓"所有内容给引擎消费"理念（2026-07-13确立），把至今零消费的深度字段接入分析管道：
  - threshold 结构化触发指标：取代正则抠数字+关键词猜测
  - direction 推理链 + drill_questions 穿透追问 + evidence 证据清单：注入LLM推理上下文
  - determination 定性路径 + suggestion 稽查处理 + remedy 整改建议：驱动报告生成
"""

import re, json

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 第一步：threshold 结构化解析器
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 从规则 threshold 字段提取的数据目标 → 要检查的数据源
THRESHOLD_DATA_TARGETS = {
    # 发票类
    "发票金额": "invoices", "发票数量": "invoices", "销项发票": "invoices",
    "进项发票": "invoices", "红字发票": "invoices", "作废发票": "invoices",
    # 银行流水类
    "银行流水": "bank_txs", "收款": "bank_txs", "付款": "bank_txs",
    "转账": "bank_txs", "银行": "bank_txs", "流水": "bank_txs",
    "资金": "bank_txs", "贷款": "bank_txs",
    # 工资薪酬类
    "工资": "salaries", "薪酬": "salaries", "个税": "salaries",
    "社保": "social_security", "公积金": "social_security",
    # 资产负债类
    "预收账款": "accounts", "应收账款": "accounts", "存货": "inventory",
    "固定资产": "fixed_assets", "负债": "accounts",
    # 凭证类
    "凭证": "vouchers", "记账": "vouchers", "序时账": "vouchers",
    # 通用
    "收入": "bank_txs", "成本": "all", "毛利": "all",
}


def parse_threshold(threshold_text):
    """解析规则的结构化 threshold 字段 → 可执行的 (数据目标, 条件, 比较符, 阈值)。
    支持："差额>资产总额的0.5%且>5万元"、"账龄>365天 && 金额>10万"、"=是即触发"等。
    返回 [{"target":"invoices","field":"amount","op":">","value":500000,"unit":"元","raw":"..."},...]
    无法解析的返回 None，交旧引擎兜底。
    """
    if not isinstance(threshold_text, str) or not threshold_text.strip():
        return None
    text = threshold_text.strip()
    # 1) "=是即触发" 类二元条件
    if text.startswith("=是") or "即触发" in text[:10]:
        return [{"target": "any", "op": "exists", "value": 1}]
    # 2) 按逻辑连接词拆分子条件
    sub_texts = re.split(r'[且&&+＋&]', text)
    units_map = {"万": 10000, "万元": 10000, "亿": 100000000, "元": 1,
                 "%": None, "天": 1, "个月": 1, "月": 1, "年": 365, "倍": 1}
    conditions = []
    for sub in sub_texts:
        sub = sub.strip()
        if not sub:
            continue
        # 找比较运算符: >=, <=, >, <, ==, =, ≥, ≤
        op_match = re.search(r'(>=|<=|≥|≤|[><=])', sub)
        if not op_match:
            continue
        op = op_match.group(1)
        # 数据目标 = 运算符前面的部分
        target_part = sub[:op_match.start()].strip()
        # 运算符后面的部分: 数字+可选单位
        rest = sub[op_match.end():].strip()
        val_match = re.match(r'(\d+(?:\.\d+)?)\s*(万|万元|亿|元|%|天|个月|月|年|m³|吨|倍)?', rest)
        if not val_match:
            continue
        val = float(val_match.group(1))
        unit = val_match.group(2) or "元"
        multiplier = units_map.get(unit, 1)
        if multiplier is not None:
            val *= multiplier
        else:
            val = val  # 百分比保持原值
        # 从 target_part 匹配数据源
        target = "general"
        kw = ""
        ctx = target_part + op + rest[:30]
        for k, t in sorted(THRESHOLD_DATA_TARGETS.items(), key=lambda x: -len(x[0])):
            if k in ctx:
                target = t
                kw = k
                break
        # 百分比特殊处理
        if unit == "%":
            val = val / 100.0  # 0.5% → 0.005
        conditions.append({
            "target": target,
            "keyword": kw,
            "op": op,
            "value": val,
            "unit": unit,
            "raw": sub.strip()
        })
    return conditions if conditions else None


def verify_with_threshold(rule, bank_txs, invoices, salaries, social_security, vouchers, inventory=None, accounts=None):
    """用规则的结构化 threshold 字段做真正数据验证（替代 _verify_rule_against_data 的抠数字）。
    返回 (触发bool, 原因str, 置信度float, 证据dict) 或 None（降级到旧引擎）。
    """
    th = rule.get("threshold")
    if not th or not isinstance(th, str):
        return None
    conditions = parse_threshold(th)
    if not conditions:
        return None
    item = str(rule.get("item", ""))
    # 处理二元条件 "=是即触发"
    for c in conditions:
        if c.get("op") == "exists":
            # 检查对应数据源是否存在
            target = c.get("target", "any")
            if target == "bank_txs" and bank_txs:
                return (True, f"有{len(bank_txs)}笔银行流水可分析", 0.7, {"银行流水笔数": len(bank_txs)})
            if target == "invoices" and invoices:
                return (True, f"有{len(invoices)}张发票可分析", 0.7, {"发票张数": len(invoices)})
            if target == "salaries" and salaries:
                return (True, f"有{len(salaries)}条工资记录可分析", 0.7, {"工资条数": len(salaries)})
            return (False, "触发条件未满足：对应数据缺失", 0, {})
    # 定量条件
    evidence = {}
    triggered = False
    reasons = []
    for c in conditions:
        t = c.get("target", "general")
        op = c.get("op", ">")
        val = c.get("value", 0)
        kw = c.get("keyword", "")
        # ── 发票类 ──
        if t == "invoices" and invoices:
            hits = []
            for inv in invoices:
                amt = float(inv.get("amount", 0) or 0)
                if op == ">" and amt > val:
                    hits.append(amt)
                elif op == ">=" and amt >= val:
                    hits.append(amt)
                elif op == "<" and amt < val:
                    hits.append(amt)
                elif op == "==" and amt == val:
                    hits.append(amt)
            if hits:
                triggered = True
                evidence["发票"] = f"{len(hits)}张"
                evidence["发票最大值"] = max(hits)
                reasons.append(f"{len(hits)}张发票金额{op}{val}元")
        # ── 银行流水类 ──
        if t == "bank_txs" and bank_txs:
            hits = []
            for tx in bank_txs:
                amt = max(float(tx.get("debit", 0) or 0), float(tx.get("credit", 0) or 0))
                if op == ">" and amt > val:
                    hits.append(amt)
                elif op == ">=" and amt >= val:
                    hits.append(amt)
            if hits:
                triggered = True
                evidence["银行流水"] = f"{len(hits)}笔"
                evidence["流水最大值"] = max(hits)
                reasons.append(f"{len(hits)}笔流水{op}{val}元")
        # ── 工资类 ──
        if t == "salaries" and salaries:
            total = sum(float(s.get("amount", 0) or 0) for s in salaries)
            if op == ">" and total > val:
                triggered = True
                evidence["总工资"] = total
                reasons.append(f"总工资{total:,.2f}{op}{val:,.2f}")
            elif total <= val:
                evidence["总工资"] = total
        # ── 账龄类（预收/应收）──
        if t == "accounts" and accounts:
            aged = [a for a in accounts if float(a.get("balance", 0) or 0) > val]
            if aged:
                triggered = True
                evidence["超期账户"] = len(aged)
                reasons.append(f"{len(aged)}户挂账超{val}天")
    if triggered:
        return (True, "；".join(reasons), 0.85, evidence)
    return (False, "未触发阈值条件", 0, {})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 第二步：direction/drill_questions/evidence 注入 LLM 推理上下文
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_rule_context_for_llm(rule, finding=None):
    """把一条规则的深度字段组装成 LLM 推理上下文。
    在引擎发现异常信号命中某规则后，将以下内容注入 prompt：
      - 推理链 → 告诉 LLM"这个异常为什么是疑点，推到哪一步了"
      - 穿透追问 → 告诉 LLM"稽查人员会问什么，应该往哪个方向深挖"
      - 证据清单 → 告诉 LLM"需要什么证据才能闭环"
    返回 (context_str, token_est) 或 (None, 0)。
    """
    if not rule:
        return (None, 0)
    parts = []
    direction = rule.get("direction", "")
    drill = rule.get("drill_questions", "")
    evidence = rule.get("evidence", "")
    focus = rule.get("focus", "")
    normal = rule.get("normal_reason", "")
    determination = rule.get("determination", "")
    
    if direction:
        parts.append(f"【推理链】{direction[:2000]}")
    if drill:
        parts.append(f"【穿透追问方向】{drill[:2000]}")
    if focus and focus != "待明确重点":
        parts.append(f"【稽查重点预判】{focus[:1000]}")
    if evidence:
        parts.append(f"【需获取证据】{evidence[:1500]}")
    if normal:
        parts.append(f"【可能合理商业解释（需证据排除）】{normal[:1000]}")
    if determination:
        parts.append(f"【定性路径指南】{determination[:1000]}")
    if finding:
        parts.insert(0, f"【信号特征】{str(finding.get('item',''))} | 风险等级：{rule.get('level','')} | 评分：{rule.get('score','')}/10")
        parts.insert(0, f"【命中规则】#{rule.get('id','?')} {rule.get('item','')}")
    if parts:
        context = "\n\n".join(parts)
        return (context, len(context) // 3)  # rough token estimate (1 token ≈ 3 chars for Chinese)
    return (None, 0)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 第三步：determination/suggestion/remedy 驱动报告生成
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_report_context_from_rule(rule, finding_data=None):
    """从规则深度字段提取报告所需的结构化上下文。
    返回 dict：给报告引擎用，按 finding→定性处理→建议的顺序输出。
    """
    if not rule:
        return {}
    ctx = {
        "rule_id": rule.get("id"),
        "item": rule.get("item", ""),
        "level": rule.get("level", ""),
        "score": rule.get("score", 0),
        "category": rule.get("category", ""),
    }
    # 法律依据（带核验标注）
    pr = rule.get("policy_ref", "")
    if pr:
        ctx["legal_basis"] = pr[:2000]
    # 税务影响
    ti = rule.get("tax_impact", "")
    if ti:
        ctx["tax_impact"] = ti
    # 定性路径 → 报告中的"定性结论"
    det = rule.get("determination", "")
    if det:
        ctx["determination_guide"] = det[:2000]
    # 稽查处理（稽查局视角）
    sg = rule.get("suggestion", "")
    if sg:
        ctx["enforcement_guide"] = sg[:2000]
    # 整改建议（企业视角）
    rm = rule.get("remedy", "")
    if rm:
        ctx["remedy_guide"] = rm[:2000] if rm != sg else sg[:2000]
    # 风险表格
    rt = rule.get("risk_table", "")
    if rt:
        # 解析税种:描述行
        ctx["risk_breakdown"] = [l.strip() for l in rt.split("\n") if ":" in l]
    # 触发阈值（用于报告说明"为何触发"）
    th = rule.get("threshold", "")
    if th:
        ctx["trigger_condition"] = th[:500]
    # 稽查动作
    act = rule.get("action", "")
    if act:
        ctx["investigation_steps"] = act[:2000]
    # 发现数据
    if finding_data:
        ctx["finding"] = finding_data
    return ctx


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 第四步：关键词/语义级规则匹配（2026-07-17 新增）
# 精确 item 匹配命中率低（域分析发现的 type 与规则条目名对不上），
# 用中文 bigram 重叠系数做语义级匹配，把命中率提上来。
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _cn_bigrams(text):
    """提取中文/字母数字的字符 bigram 集合（轻量分词替代，全行业适用）"""
    t = re.sub(r'[^\u4e00-\u9fa5A-Za-z0-9]', '', str(text or ""))
    if len(t) < 2:
        return {t} if t else set()
    return {t[i:i + 2] for i in range(len(t) - 1)}


def _overlap_coef(a, b):
    """重叠系数 = 交集 / 较短集合大小。比 Jaccard 更容忍短标题 vs 长描述的长度差。"""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def build_rule_match_index(rules):
    """预计算每条规则的匹配索引（bigram 集合），一次分析建一次。"""
    index = []
    for r in rules:
        item = str(r.get("item", "")).strip()
        if not item:
            continue
        index.append({
            "rule": r,
            "item_bi": _cn_bigrams(item),
            # phenomena 前80字作为辅助语料（规则描述的典型表现）
            "ext_bi": _cn_bigrams(item + str(r.get("phenomena", ""))[:80]),
        })
    return index


def match_rule_semantic(finding, index, threshold=0.55):
    """语义级匹配：为一条发现找最相似的疑点库规则。

    评分 = max(type↔item 重叠, 0.8×(type+detail ↔ item+phenomena) 重叠)
    只取 top1 且分数 ≥ threshold，宁缺勿滥——错配比不配危害更大。
    返回 (rule, score) 或 (None, 0)。
    """
    ftype = str(finding.get("type", "")).strip()
    if not ftype or not index:
        return None, 0.0
    f_type_bi = _cn_bigrams(ftype)
    f_full_bi = _cn_bigrams(ftype + str(finding.get("detail", ""))[:150])
    best, best_score = None, 0.0
    for entry in index:
        s1 = _overlap_coef(f_type_bi, entry["item_bi"])
        s2 = _overlap_coef(f_full_bi, entry["ext_bi"]) * 0.8
        score = max(s1, s2)
        if score > best_score:
            best, best_score = entry["rule"], score
    if best is not None and best_score >= threshold:
        return best, round(best_score, 3)
    return None, 0.0

