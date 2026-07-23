# -*- coding: utf-8 -*-
"""可执行三链引擎 —— 解析JSON链定义，对解析后的数据执行聚合/比对/查询/判定操作

数据模型：
- bank_txs: [{date, counterparty, account, credit(float), debit(float), amount, summary, balance, ...}]
- sal_invs: [{inv_no, goods, buyer, seller, amount(float), tax(float), total(float), date, ...}]
- pur_invs: [{inv_no, goods, buyer, seller, amount(float), tax(float), total(float), date, ...}]
- vouchers: [{date, account_code, account_name, debit(float), credit(float), summary, ...}]
- salaries: [{name, current_income(float), tax_payable(float), net_salary(float), ...}]
- social_security: [{name, personal_amount(float), company_amount(float), salary_base(float), ...}]
- inventory: [{code, name, in_qty(float), out_qty(float), end_qty(float), total_amount(float), ...}]
"""
import json, os, math
from datetime import datetime
from collections import defaultdict

DATA_SOURCES = {
    "bank_txs": "bank_txs",
    "sal_invs": "sal_invs",
    "pur_invs": "pur_invs",
    "vouchers": "vouchers",
    "salaries": "salaries",
    "social_security": "social_security",
    "inventory": "inventory",
}


def _safe_float(v, default=0.0):
    try:
        return float(v) if v not in (None, "", "None") else default
    except (ValueError, TypeError):
        return default


def _month_key(date_str):
    """'20250115' or '2025-01-15' -> '202501'"""
    d = str(date_str).replace("-", "").replace("/", "").strip()
    return d[:6] if len(d) >= 6 else d


# ════════════════ 操作函数 ════════════════

def _op_aggregate(data, step, ctx):
    """聚合操作：按某个字段分组、计算聚合值"""
    source = step.get("source")
    group_by = step.get("group_by")
    fields = step.get("fields", [])
    filters = step.get("filters", {})
    rows = data.get(source, [])

    # 应用过滤条件
    rows = _apply_filters(rows, filters)

    if group_by:
        groups = defaultdict(lambda: {f.split(" as ")[-1].strip(): 0 for f in fields})
        for r in rows:
            if group_by == "month":
                # 从 date 字段提取月份
                date_val = str(r.get("date", r.get("invoice_date", "")))
                gk = _month_key(date_val)
            else:
                gk = str(r.get(group_by, ""))
            for f_expr in fields:
                # 解析 "sum(field) as alias" or "count(*) as alias"
                parts = f_expr.split(" as ")
                alias = parts[-1].strip() if len(parts) > 1 else f_expr.strip()
                func_part = parts[0].strip() if len(parts) > 1 else f_expr
                if func_part.startswith("sum("):
                    fname = func_part[4:-1].strip()
                    groups[gk][alias] += _safe_float(r.get(fname, 0))
                elif func_part.startswith("count("):
                    groups[gk][alias] += 1
                elif func_part.startswith("avg("):
                    fname = func_part[4:-1].strip()
                    groups[gk][alias + "_sum"] = groups[gk].get(alias + "_sum", 0) + _safe_float(r.get(fname, 0))
                    groups[gk][alias + "_cnt"] = groups[gk].get(alias + "_cnt", 0) + 1
        result = [{"group": k, **v} for k, v in groups.items()]
        # 计算avg
        for r in result:
            for k in list(r.keys()):
                if k.endswith("_sum"):
                    base = k[:-4]
                    cnt_key = base + "_cnt"
                    r[base] = r[k] / max(r.get(cnt_key, 1), 1)
                    del r[k]
                    if cnt_key in r: del r[cnt_key]
    else:
        result = {}
        for f_expr in fields:
            parts = f_expr.split(" as ")
            alias = parts[-1].strip() if len(parts) > 1 else f_expr.strip()
            func_part = parts[0].strip() if len(parts) > 1 else f_expr
            total = 0
            if func_part.startswith("sum("):
                fname = func_part[4:-1].strip()
                total = sum(_safe_float(r.get(fname, 0)) for r in rows)
            elif func_part.startswith("count("):
                total = len(rows)
            result[alias] = total
        result = [result]

    ctx[step["output"]] = result
    return result


def _op_compare(data, step, ctx):
    """比对操作：取两个已计算的结果、用公式比较、标记超阈值"""
    left_key = step.get("left")
    right_key = step.get("right")
    formula = step.get("formula", "")
    threshold = step.get("threshold", {})
    left_data = ctx.get(left_key, [])
    right_data = ctx.get(right_key, [])

    # 按 month 对齐
    left_map = {}
    for d in left_data:
        gk = d.get("group", d.get("month", ""))
        left_map[gk] = d
    right_map = {}
    for d in right_data:
        gk = d.get("group", d.get("month", ""))
        right_map[gk] = d

    results = []
    all_months = set(left_map.keys()) | set(right_map.keys())
    for m in sorted(all_months):
        l = left_map.get(m, {})
        r = right_map.get(m, {})

        # 提取值
        lv = 0
        rv = 0
        for expr_name in ["total_receipts", "total_bank", "reported_sales", "total_sales",
                          "total", "sum_amount", "total_credit"]:
            if expr_name in l:
                lv = _safe_float(l.get(expr_name, 0))
                break
            if "total" in l:
                lv = _safe_float(list(l.values())[-1]) if len(l) > 1 else 0
                break
        for expr_name in ["reported_sales", "total_sales", "total_receipts",
                          "total", "sum_amount", "total_credit"]:
            if expr_name in r:
                rv = _safe_float(r.get(expr_name, 0))
                break
            if "total" in r:
                rv = _safe_float(list(r.values())[-1]) if len(r) > 1 else 0
                break

        gap = lv - rv
        is_anomaly = False
        if threshold:
            gt_val = threshold.get("gt", None)
            if gt_val is not None:
                # 支持表达式如 "reported_sales * 0.1"
                gt_str = str(gt_val)
                if "*" in gt_str:
                    parts = gt_str.split("*")
                    ref_val = _safe_float(r.get(parts[0].strip(), rv)) if parts[0].strip() not in ("rv", "reported_sales") else rv
                    mult = _safe_float(parts[1].strip())
                    thresh = ref_val * mult
                else:
                    thresh = _safe_float(gt_val)
                is_anomaly = gap > thresh

        results.append({
            "month": m,
            "left_value": lv,
            "right_value": rv,
            "gap": gap,
            "is_anomaly": is_anomaly
        })

    ctx[step["output"]] = results
    return results


def _op_query(data, step, ctx):
    """查询操作：从数据源筛选并分组聚合"""
    source = step.get("source")
    filters = step.get("filters", {})
    group_by = step.get("group_by")
    fields = step.get("fields", [])
    rows = data.get(source, [])

    if not rows:
        # 特殊处理：如果source是先前计算的ctx
        rows = ctx.get(source, [])
        if not rows:
            ctx[step["output"]] = []
            return []

    # 特殊过滤：not_in 需要对比集合
    special_filters = {}
    normal_filters = {}
    for k, v in filters.items():
        if isinstance(v, dict) and "not_in" in v:
            special_filters[k] = v
        else:
            normal_filters[k] = v

    rows = _apply_filters(rows, normal_filters)

    # not_in 过滤
    if special_filters:
        for fk, fv in special_filters.items():
            not_in_key = fv["not_in"]
            exclude_set = ctx.get(not_in_key, set())
            if not isinstance(exclude_set, set):
                exclude_set = set()
            rows = [r for r in rows if str(r.get(fk, "")) not in exclude_set]

    if group_by:
        groups = defaultdict(lambda: {f.split(" as ")[-1].strip(): 0 for f in fields})
        for r in rows:
            gk = str(r.get(group_by, ""))
            for f_expr in fields:
                parts = f_expr.split(" as ")
                alias = parts[-1].strip() if len(parts) > 1 else f_expr.strip()
                func_part = parts[0].strip() if len(parts) > 1 else f_expr
                if func_part.startswith("sum("):
                    fname = func_part[4:-1].strip()
                    groups[gk][alias] += _safe_float(r.get(fname, 0))
                elif func_part.startswith("count("):
                    groups[gk][alias] += 1
            # 也存原始行供后续使用
        result = [{"group": k, **v} for k, v in groups.items()]
    else:
        result = list(rows)

    ctx[step["output"]] = result
    return result


def _op_conclude(data, step, ctx):
    """判定操作：根据条件生成发现结论
    支持条件格式：
    - "key.field > value" — 检查ctx[key]列表中是否有item[field] > value
    - "key exists" — 检查ctx[key]是否存在且非空
    - "key.field" — 检查ctx[key]列表中是否有item[field]为True
    """
    conditions = step.get("conditions", [])
    findings = []
    for cond in conditions:
        cond_expr = str(cond.get("if", "")).strip()
        if not cond_expr:
            continue

        triggered = False

        # 格式1: "key exists" — 存在性检查
        if cond_expr.endswith(" exists"):
            ref_key = cond_expr[:-7].strip()
            ref_data = ctx.get(ref_key, [])
            if isinstance(ref_data, list) and len(ref_data) > 0:
                triggered = True
            elif isinstance(ref_data, dict) and ref_data:
                triggered = True

        # 格式2: "key.field > value" 或 "key.field >= value" 
        elif " > " in cond_expr or " >= " in cond_expr or " < " in cond_expr or " = " in cond_expr:
            for op_str in [">=", ">", "<", "="]:
                if f" {op_str} " in cond_expr:
                    left_raw, right_raw = cond_expr.split(f" {op_str} ", 1)
                    break
            else:
                continue
            
            right_raw = right_raw.strip()
            thresh = _safe_float(right_raw) if right_raw.replace('.','',1).isdigit() else 0

            # 解析 left: "key.field" 或 "key"
            if "." in left_raw:
                ref_key, field = left_raw.rsplit(".", 1)
            else:
                ref_key, field = left_raw, "value"
            
            ref_data = ctx.get(ref_key, [])
            if isinstance(ref_data, list):
                for item in ref_data:
                    if isinstance(item, dict):
                        val = _safe_float(item.get(field, 0))
                        if (op_str == ">" and val > thresh) or \
                           (op_str == ">=" and val >= thresh) or \
                           (op_str == "<" and val < thresh) or \
                           (op_str == "=" and abs(val - thresh) < 0.01):
                            triggered = True
                            break
            elif isinstance(ref_data, dict):
                val = _safe_float(ref_data.get(field, 0))
                if (op_str == ">" and val > thresh) or \
                   (op_str == ">=" and val >= thresh):
                    triggered = True

        # 格式3: "key.field" — 布尔检查（如 is_anomaly）
        elif "." in cond_expr:
            ref_key, field = cond_expr.rsplit(".", 1)
            ref_data = ctx.get(ref_key, [])
            if isinstance(ref_data, list):
                for item in ref_data:
                    if isinstance(item, dict) and item.get(field):
                        triggered = True
                        break

        # 格式4: "key" — 简单存在且非空
        else:
            ref_data = ctx.get(cond_expr)
            if ref_data:
                if isinstance(ref_data, list) and len(ref_data) > 0:
                    triggered = True
                elif isinstance(ref_data, dict) and ref_data:
                    triggered = True

        if triggered:
            findings.append({
                "type": cond.get("conclusion", ""),
                "severity": cond.get("severity", "中"),
                "detail": cond.get("detail", ""),
                "law_refs": step.get("law_refs", [])
            })

    output_name = step.get("output", "findings")
    ctx[output_name] = findings
    return findings


OPERATIONS = {
    "aggregate": _op_aggregate,
    "compare": _op_compare,
    "query": _op_query,
    "conclude": _op_conclude,
}


def _apply_filters(rows, filters):
    if not filters:
        return rows
    result = rows
    for fk, fv in filters.items():
        if isinstance(fv, dict):
            # 操作符过滤
            for op, val in fv.items():
                if op == ">":
                    result = [r for r in result if _safe_float(r.get(fk, 0)) > _safe_float(val)]
                elif op == "<":
                    result = [r for r in result if _safe_float(r.get(fk, 0)) < _safe_float(val)]
                elif op == ">=":
                    result = [r for r in result if _safe_float(r.get(fk, 0)) >= _safe_float(val)]
                elif op == "=":
                    result = [r for r in result if str(r.get(fk, "")) == str(val)]
                elif op == "!=":
                    result = [r for r in result if str(r.get(fk, "")) != str(val)]
                elif op == "in":
                    result = [r for r in result if str(r.get(fk, "")) in val]
        else:
            result = [r for r in result if str(r.get(fk, "")) == str(fv)]
    return result


# ════════════════ 链执行入口 ════════════════

def execute_chain(chain_def, data, company_name=""):
    """
    执行一条链（线索链/证据链/分析链均有统一的执行模型）

    Args:
        chain_def: 链定义 dict，含 steps 数组
        data: 解析后的数据 dict，键为 bank_txs/sal_invs/pur_invs 等
        company_name: 公司名称（用于上下文输出）

    Returns:
        dict: {chain_id, findings: [...], execution_log: [...]}
    """
    ctx = {
        "company_name": company_name,
    }
    # 将data也注入ctx，供op_query跨源引用
    for k, v in data.items():
        if isinstance(v, list):
            ctx[k + "_data"] = v

    log = []
    chain_id = chain_def.get("id", chain_def.get("rule_id", "?"))

    steps = chain_def.get("steps", [])
    for step in steps:
        op = step.get("op", "")
        if op not in OPERATIONS:
            log.append(f"未知操作: {op} (step {step.get('step','?')})")
            continue
        try:
            result = OPERATIONS[op](data, step, ctx)
            output_name = step.get("output", "unnamed")
            log.append(f"[{op}] step {step.get('step','?')} -> {output_name}: {len(result) if isinstance(result, list) else 1} items")
        except Exception as e:
            log.append(f"[{op}] step {step.get('step','?')} ERROR: {e}")

    # 收集所有findings
    all_findings = []
    for key in ctx:
        if key.startswith("findings_") or key == "findings":
            f = ctx[key]
            if isinstance(f, list):
                all_findings.extend(f)

    return {
        "chain_id": chain_id,
        "rule_id": chain_def.get("rule_id"),
        "findings": all_findings,
        "execution_log": log,
        "context": {k: v for k, v in ctx.items() if isinstance(v, (int, float, str, bool)) or (isinstance(v, list) and len(str(v)) < 500)}
    }


def run_chains_for_rule(rule_id, clues_data, evidence_data, analysis_data, engine_data):
    """
    对指定规则执行线索链→证据链→分析链

    Returns:
        dict: {clue_result, evidence_result, analysis_result}
    """
    results = {}

    # 线索链
    clue_chain = _find_chain(clues_data, rule_id)
    if clue_chain:
        results["clue"] = execute_chain(clue_chain, engine_data)
    else:
        results["clue"] = None

    # 证据链
    evid_chain = _find_chain(evidence_data, rule_id)
    if evid_chain:
        # 证据链可以引用线索链的上下文
        clues_ctx = results.get("clue", {}).get("context", {}) if isinstance(results.get("clue"), dict) else {}
        merged_data = {**engine_data}
        for k, v in clues_ctx.items():
            if not k.endswith("_data"):
                merged_data[k] = v
        results["evidence"] = execute_chain(evid_chain, merged_data)
    else:
        results["evidence"] = None

    # 分析链
    anal_chain = _find_chain(analysis_data, rule_id)
    if anal_chain:
        # 分析链可以引用线索链和证据链的结果
        merged_data = {**engine_data}
        for result_key in ("clue", "evidence"):
            r = results.get(result_key)
            if r and isinstance(r, dict):
                for k, v in r.get("context", {}).items():
                    if not k.endswith("_data"):
                        merged_data[k] = v
        results["analysis"] = execute_chain(anal_chain, merged_data)
    else:
        results["analysis"] = None

    # ═══ 规则增强：为每条链的发现注入23字段规则数据 ═══
    try:
        from engine.rule_enricher import enrich_finding
        for key in ("clue", "evidence", "analysis"):
            r = results.get(key)
            if r and isinstance(r, dict) and r.get("findings"):
                for f in r["findings"]:
                    enrich_finding(f, rule_id)
    except Exception:
        pass

    return results


def _find_chain(chains_data, rule_id):
    """在链数据中查找匹配 rule_id 的链"""
    items = chains_data if isinstance(chains_data, list) else chains_data.get("evidence_chains", chains_data.get("analysis_chains", []))
    for item in items:
        if isinstance(item, dict) and item.get("rule_id") == rule_id:
            return item
    return None
