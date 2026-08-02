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
import json, os, math, re
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

CHAIN_TYPE_KEYS = {
    "clue": "clue",
    "evidence": "evid",
    "analysis": "alc",
}

DECISION_LANGUAGE = (
    "定性成立", "认定为", "构成偷税", "构成虚开", "依法定性", "应予处罚",
    "处以罚款", "建议追缴", "移送公安", "刑事追诉", "铁证", "即可定案",
    "直接定案", "违法成立", "犯罪成立",
)


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
    ctx.setdefault("_output_meta", {})[step["output"]] = {
        "kind": "aggregate",
        "source": source,
        "sources": [source] if source and rows else [],
        "filters": filters,
        "source_rows": len(rows),
    }
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
    ctx.setdefault("_output_meta", {})[step["output"]] = {
        "kind": "compare",
        "anomaly_count": sum(1 for item in results if item.get("is_anomaly")),
        "sources": sorted(set(
            ctx.get("_output_meta", {}).get(left_key, {}).get("sources", [])
            + ctx.get("_output_meta", {}).get(right_key, {}).get("sources", [])
        )),
    }
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
            ctx.setdefault("_output_meta", {})[step["output"]] = {
                "kind": "query",
                "source": source,
                "sources": [],
                "filters": filters,
                "source_rows": 0,
                "filtered_query": bool(filters),
            }
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
    ctx.setdefault("_output_meta", {})[step["output"]] = {
        "kind": "query",
        "source": source,
        "sources": [source] if source and rows else [],
        "filters": filters,
        "source_rows": len(rows),
        "filtered_query": bool(filters),
    }
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
        condition_refs = []

        # 格式1: "key exists" — 存在性检查
        if cond_expr.endswith(" exists"):
            ref_key = cond_expr[:-7].strip()
            condition_refs.append(ref_key)
            ref_data = ctx.get(ref_key, [])
            meta = ctx.get("_output_meta", {}).get(ref_key, {})
            # “有数据”不等于“有异常”。只有明确的异常比对结果，或带筛选
            # 条件的查询命中，才允许 exists 触发待核事项。
            if meta.get("kind") == "compare":
                triggered = meta.get("anomaly_count", 0) > 0
            elif meta.get("kind") == "query" and meta.get("filtered_query"):
                triggered = bool(ref_data)
            elif cond.get("allow_plain_exists") is True:
                triggered = bool(ref_data)

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
            elif len(left_raw.split()) == 2:
                ref_key, field = left_raw.split(None, 1)
            else:
                ref_key, field = left_raw, "value"
            condition_refs.append(ref_key)
            
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
            condition_refs.append(ref_key)
            ref_data = ctx.get(ref_key, [])
            if isinstance(ref_data, list):
                for item in ref_data:
                    if isinstance(item, dict) and item.get(field):
                        triggered = True
                        break

        # 格式4: "key" — 简单存在且非空
        else:
            ref_data = ctx.get(cond_expr)
            condition_refs.append(cond_expr)
            if ref_data:
                if isinstance(ref_data, list) and len(ref_data) > 0:
                    triggered = True
                elif isinstance(ref_data, dict) and ref_data:
                    triggered = True

        if triggered:
            for supporting_ref in cond.get("supporting_refs", []):
                if _has_material_value(ctx.get(supporting_ref)):
                    condition_refs.append(supporting_ref)
            supporting_sources = set()
            for ref_key in condition_refs:
                supporting_sources.update(
                    ctx.get("_output_meta", {}).get(ref_key, {}).get("sources", [])
                )
                if ref_key in DATA_SOURCES and _has_material_value(data.get(ref_key)):
                    supporting_sources.add(ref_key)
            findings.append({
                "type": cond.get("conclusion", ""),
                "severity": cond.get("severity", "中"),
                "detail": cond.get("detail", ""),
                "law_refs": step.get("law_refs", []),
                "_supporting_sources": sorted(supporting_sources),
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

def _normalise_rule_id(rule_id):
    try:
        return int(rule_id)
    except (TypeError, ValueError):
        return str(rule_id or "").strip()


def _has_material_value(value):
    if value is None:
        return False
    if isinstance(value, (list, tuple, set, dict, str)):
        return len(value) > 0
    return True


def _strip_decision_language(text):
    """保留可复核的事实描述，移除模板中的自动定性、处罚和移送语句。"""
    text = str(text or "").strip()
    if not text:
        return ""
    parts = re.split(r"(?<=[。；;\n])", text)
    kept = [part.strip() for part in parts if part.strip() and not any(token in part for token in DECISION_LANGUAGE)]
    return "".join(kept).strip()


def _neutralise_finding(finding, chain_type, evidence_state):
    """把链模板输出限定为待核事项，避免算法越过调查、审理和裁量。"""
    original_type = str(finding.get("type", "") or "未命名事项")
    safe_type = original_type
    for token in ("定性成立", "违法成立", "犯罪成立", "即可定案", "直接定案"):
        safe_type = safe_type.replace(token, "待核")
    if any(token in safe_type for token in ("认定", "处罚", "追缴", "移送")):
        safe_type = "待核事项"
    if not safe_type.startswith("待核") and chain_type in ("evidence", "analysis"):
        safe_type = f"待核事项：{safe_type}"

    detail = _strip_decision_language(finding.get("detail", ""))
    if not detail:
        detail = "链路条件已触发，须回到原始资料核验适用前提、款项或交易性质、反向证据和合理解释。"

    return {
        **finding,
        "type": safe_type,
        "detail": detail,
        "finding_status": evidence_state,
        "conclusion_scope": "screening_and_review_only",
        "required_human_review": True,
        "decision_boundary": "不得由规则命中、模型评分或预设证据数量自动作出行政认定、处理处罚或刑事判断。",
    }


def execute_chain(chain_def, data, company_name="", prior_context=None, chain_type="clue"):
    """
    执行一条链（线索链/证据链/分析链均有统一的执行模型）

    Args:
        chain_def: 链定义 dict，含 steps 数组
        data: 解析后的数据 dict，键为 bank_txs/sal_invs/pur_invs 等
        company_name: 公司名称（用于上下文输出）

    Returns:
        dict: {chain_id, findings: [...], execution_log: [...]}
    """
    ctx = {"company_name": company_name}
    if isinstance(prior_context, dict):
        ctx.update(prior_context)
    input_keys = set(ctx)
    # 同时保留原始键和兼容的 *_data 键，供跨链步骤引用。
    for k, v in data.items():
        ctx[k] = v
        input_keys.add(k)
        if isinstance(v, (list, tuple, set, dict)):
            ctx[k + "_data"] = v
            input_keys.add(k + "_data")
    # 每条链单独维护输出谱系，不把上游“存在性”当作本链证据。
    ctx["_output_meta"] = {}

    log = []
    errors = []
    queried_sources = set()
    chain_id = chain_def.get("id", chain_def.get("rule_id", "?"))

    steps = chain_def.get("steps", [])
    for step in steps:
        op = step.get("op", "")
        if op not in OPERATIONS:
            message = f"未知操作: {op} (step {step.get('step','?')})"
            log.append(message)
            errors.append(message)
            continue
        try:
            result = OPERATIONS[op](data, step, ctx)
            source = step.get("source")
            if source and _has_material_value(data.get(source, ctx.get(source))):
                queried_sources.add(source)
            output_name = step.get("output", "unnamed")
            log.append(f"[{op}] step {step.get('step','?')} -> {output_name}: {len(result) if isinstance(result, list) else 1} items")
        except Exception as e:
            message = f"[{op}] step {step.get('step','?')} ERROR: {e}"
            log.append(message)
            errors.append(message)

    # 收集所有findings
    all_findings = []
    for key in ctx:
        if key.startswith("findings_") or key == "findings":
            f = ctx[key]
            if isinstance(f, list):
                all_findings.extend(f)

    min_evidence_dimensions = max(int(chain_def.get("min_evidence", 2) or 2), 1)
    min_independent_sources = max(int(chain_def.get("min_independent_sources", 2) or 2), 1)
    supporting_sources = set()
    for finding in all_findings:
        if isinstance(finding, dict):
            supporting_sources.update(finding.pop("_supporting_sources", []))
    if errors:
        state = "execution_incomplete"
    elif chain_type == "clue":
        state = "formed_pending_investigation" if all_findings else "not_triggered"
    elif chain_type == "evidence":
        if not all_findings:
            state = "not_supported"
        elif (
            len(all_findings) < min_evidence_dimensions
            or len(supporting_sources) < min_independent_sources
        ):
            state = "single_source_or_insufficient"
        else:
            state = "partially_supported_pending_human_review"
    else:
        state = "ready_for_human_review" if all_findings else "hypothesis_not_supported"

    all_findings = [
        _neutralise_finding(finding, chain_type, state)
        for finding in all_findings if isinstance(finding, dict)
    ]
    output_context = {
        key: value for key, value in ctx.items()
        if key not in input_keys and key != "company_name" and not key.startswith("findings")
    }
    return {
        "chain_id": chain_id,
        "rule_id": chain_def.get("rule_id"),
        "chain_type": chain_type,
        "status": state,
        "complete": not errors,
        "ready_for_analysis": chain_type == "evidence" and state == "partially_supported_pending_human_review",
        "queried_sources": sorted(queried_sources),
        "independent_sources": sorted(supporting_sources),
        "independent_source_count": len(supporting_sources),
        "evidence_dimension_count": len(all_findings) if chain_type == "evidence" else None,
        "minimum_evidence_dimensions": min_evidence_dimensions if chain_type == "evidence" else None,
        "minimum_independent_sources": min_independent_sources if chain_type == "evidence" else None,
        "findings": all_findings,
        "execution_log": log,
        "errors": errors,
        "context": output_context,
    }


def run_chains_for_rule(rule_id, clues_data, evidence_data, analysis_data, engine_data):
    """
    对指定规则执行线索链→证据链→分析链

    Returns:
        dict: {clue_result, evidence_result, analysis_result}
    """
    results = {}

    # 线索链
    clue_chain = _find_chain(clues_data, rule_id, "clue")
    if clue_chain:
        results["clue"] = execute_chain(clue_chain, engine_data, chain_type="clue")
    else:
        results["clue"] = None

    # 证据链
    evid_chain = _find_chain(evidence_data, rule_id, "evidence")
    if evid_chain:
        clues_ctx = results.get("clue", {}).get("context", {}) if isinstance(results.get("clue"), dict) else {}
        results["evidence"] = execute_chain(
            evid_chain,
            engine_data,
            prior_context=clues_ctx,
            chain_type="evidence",
        )
    else:
        results["evidence"] = None

    # 分析链
    anal_chain = _find_chain(analysis_data, rule_id, "analysis")
    evidence_result = results.get("evidence")
    if anal_chain and isinstance(evidence_result, dict) and evidence_result.get("ready_for_analysis"):
        prior_context = {}
        for result_key in ("clue", "evidence"):
            result = results.get(result_key)
            if isinstance(result, dict):
                prior_context.update(result.get("context", {}))
        results["analysis"] = execute_chain(
            anal_chain,
            engine_data,
            prior_context=prior_context,
            chain_type="analysis",
        )
    elif anal_chain:
        results["analysis"] = {
            "chain_id": anal_chain.get("id"),
            "rule_id": anal_chain.get("rule_id"),
            "chain_type": "analysis",
            "status": "blocked_by_evidence",
            "complete": True,
            "ready_for_analysis": False,
            "findings": [],
            "execution_log": ["证据来源未达到独立性和数量要求，分析链停在补证环节。"],
            "errors": [],
            "context": {},
        }
    else:
        results["analysis"] = None

    # ═══ 规则增强：为每条链的发现注入23字段规则数据 ═══
    try:
        from engine.rule_enricher import enrich_finding
        from engine.methodology_guardrails import review_finding
        for key in ("clue", "evidence", "analysis"):
            r = results.get(key)
            if r and isinstance(r, dict) and r.get("findings"):
                for f in r["findings"]:
                    enrich_finding(f, rule_id)
                    review_finding(f)
    except Exception:
        pass

    return results


# ═══ 全局链索引缓存 (rule_id→chain) — 避免每次分析O(n)扫描1720条链 ═══
_chain_index = {}  # key: (clue|evid|alc), value: {rule_id: chain}

def _build_chain_index(clues_data, evidence_data, analysis_data):
    """一次性将所有链数据按 rule_id 建立索引"""
    global _chain_index
    _chain_index = {}
    for key, data in [("clue", clues_data), ("evid", evidence_data), ("alc", analysis_data)]:
        idx = {}
        if isinstance(data, list):
            for item in data:
                rid = _normalise_rule_id(item.get("rule_id"))
                if rid is not None: idx[rid] = item
        elif isinstance(data, dict):
            items = data.get("evidence_chains", data.get("analysis_chains", []))
            for item in items:
                rid = _normalise_rule_id(item.get("rule_id"))
                if rid is not None: idx[rid] = item
        _chain_index[key] = idx

def _find_chain(chains_data, rule_id, chain_type=None):
    """只在指定链类型中查找，防止证据链或分析链误取线索链。"""
    normalised_id = _normalise_rule_id(rule_id)
    index_key = CHAIN_TYPE_KEYS.get(chain_type or "")
    if index_key:
        item = _chain_index.get(index_key, {}).get(normalised_id)
        if item is not None:
            return item
    # 降级: 线性扫描
    items = chains_data if isinstance(chains_data, list) else chains_data.get("evidence_chains", chains_data.get("analysis_chains", []))
    for item in items:
        if isinstance(item, dict) and _normalise_rule_id(item.get("rule_id")) == normalised_id:
            return item
    return None
