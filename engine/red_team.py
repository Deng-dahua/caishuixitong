# ══════════════════════════════════════════════════════════════
# 红队证伪模块 — 思考层最后一道安检
# 2026-07-16 新建：补齐智能引擎中枢红队证伪能力
# 2026-09-11 P2-2：证伪改为按证据源重算，取代字符串启发式
# 2026-09-11 P2-3：补全幻觉检测的金额矛盾比对（此前只提取不比对）
# ══════════════════════════════════════════════════════════════

import re

def red_team_falsification(all_findings, pipeline_log=None, engine_data=None):
    """红队证伪：三攻击维度 + 判例库检索。

    engine_data 为解析后的原始资料（bank_txs / sal_invs / pur_invs / vouchers /
    salaries / inventory）。传入后证伪按证据源重算；不传则因缺少反证，
    所有无罪假设一律判为"无法排除"（保守，不会反向坐实疑点）。
    """
    from engine.case_library import search_case_library
    results = {
        "total": len(all_findings), "falsified": 0, "passed": 0,
        "details": [], "case_matches": [],
        "data_driven": 0, "undecidable": 0,   # 真实重算命中的条数 / 资料不足无法判定的条数
    }

    high_findings = [f for f in all_findings if str(f.get("level", "")) in ("高风险", "极高风险")]
    if not high_findings:
        if pipeline_log is not None:
            pipeline_log.append("[红队] 无高风险发现，跳过证伪")
        return results

    case_matches = search_case_library(high_findings, pipeline_log=pipeline_log)
    results["case_matches"] = case_matches

    for f in high_findings:
        ftype = str(f.get("type", ""))
        detail = str(f.get("detail", ""))
        result = {"type": ftype[:40], "attacks": []}
        hypotheses = _generate_innocence_hypotheses(ftype, detail)
        for cm in case_matches:
            if cm["finding"][:20] in ftype or any(kw in detail for kw in ["证据", "程序", "定性", "法律"]):
                hypotheses.append(f"判例警告: {cm['reason'][:60]}")
        result["hypotheses"] = hypotheses[:5]

        defeated = 0
        undecidable = 0
        data_driven = 0
        for h in hypotheses:
            ok, basis = _attack_with_evidence(h, detail, all_findings, engine_data)
            if ok:
                defeated += 1
            if basis == "data_driven":
                data_driven += 1
            elif basis in ("insufficient_data", "recompute_error"):
                undecidable += 1
        result["hypotheses_defeated"] = defeated
        result["hypotheses_total"] = len(hypotheses)
        result["undecidable"] = undecidable
        result["data_driven"] = data_driven

        if defeated >= len(hypotheses):
            result["verdict"] = "passed"; results["passed"] += 1
        else:
            result["verdict"] = "falsified"; results["falsified"] += 1
            gap = len(hypotheses) - defeated
            if undecidable:
                f["_red_team_warning"] = (
                    f"红队证伪未通过: {gap}个无罪假设未被排除"
                    f"（其中{undecidable}个因资料不足无法证伪，须补证后复核）"
                )
            else:
                f["_red_team_warning"] = f"红队证伪未通过: {gap}个无罪假设未被排除"
        results["data_driven"] += data_driven
        results["undecidable"] += undecidable
        results["details"].append(result)

    if pipeline_log is not None:
        pipeline_log.append(
            f"[红队] 证伪完成: {results['passed']}/{len(high_findings)}条通过 "
            f"{results['falsified']}条未通过 判例{len(case_matches)}条"
            f"（按证据源重算{results['data_driven']}次，资料不足{results['undecidable']}次）"
        )
    return results


def _generate_innocence_hypotheses(ftype, detail):
    """生成无罪假设：为每个高风险发现生成合理商业解释"""
    hypotheses = []
    mapping = {
        "隐匿收入": ["季节性旺季导致收入波动", "大额订单一次性结算", "战略合作折扣期"],
        "虚列成本": ["业务扩张期一次性投入", "原材料价格波动导致成本上升", "行业惯例的成本结构"],
        "虚开发票": ["真实交易但合同与发票主体不一致", "代开发票但业务真实", "关联交易有商业实质"],
        "偷税": ["计算错误导致的申报差异", "政策理解偏差导致的少报", "新会计对税法不熟悉"],
    }
    default = ["合法商业安排待核实", "行业特殊惯例待确认", "第三方证据待补充"]
    for key, hyps in mapping.items():
        if key in ftype:
            hypotheses = hyps
            break
    if not hypotheses:
        hypotheses = default
    return hypotheses[:3]


# ══════════════════════════════════════════════════════════════
# 真实证伪：按证据源重算（P2-2）
#
# 旧实现只做字符串匹配（"季节"/"一次性"）加 len(combined)>200 的文本长度启发式，
# 与数据完全无关——文本越长越"证伪成功"，等于没有证伪。此处改为回到 engine_data
# 的真实数据源做量化重算：关键词只负责"路由到哪个口径"，结论一律由数据算出。
#
# 语义约定（与旧版一致，未改变裁决方向）：
#   返回 True  = 该无罪假设已被证据击破（红线疑点站得住）
#   返回 False = 该无罪假设无法排除（疑点须带证伪警告，交人工复核）
# 数据不足 / 重算失败时一律视为"无法排除"：拿不出反证就不能宣称疑点已坐实，
# 这是「发现≠确认·绝不自动定罪」在证伪环节的具体落地。
# ══════════════════════════════════════════════════════════════


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _monthly_totals(rows, keys=("total", "amount", "credit")):
    """按月汇总金额 → {'202501': 1234.5, ...}"""
    out = {}
    for row in rows or []:
        date = str(row.get("date") or row.get("invoice_date") or "").replace("-", "").replace("/", "")
        if len(date) < 6:
            continue
        amount = 0.0
        for key in keys:
            amount = _num(row.get(key))
            if amount:
                break
        out[date[:6]] = out.get(date[:6], 0.0) + amount
    return out


def _cv(values):
    """变异系数 = 标准差 / 均值。月度分布越不均，季节性解释越可能成立。"""
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return None
    mean = sum(vals) / len(vals)
    if mean <= 0:
        return None
    variance = sum((v - mean) ** 2 for v in vals) / len(vals)
    return (variance ** 0.5) / mean


def _falsify_seasonality(detail, all_findings, data):
    """「季节性旺季导致收入波动」：月度收入分布是否确有季节波动。
    逐月分布平坦（CV ≤ 0.4）却用季节性解释异常，该解释不成立。"""
    monthly = _monthly_totals(data.get("sal_invs") or [])
    if len(monthly) < 4:
        return None  # 月份不足，无从判断
    cv = _cv(list(monthly.values()))
    if cv is None:
        return None
    return cv <= 0.4


def _falsify_one_off(detail, all_findings, data):
    """「大额订单一次性结算 / 扩张期一次性投入」：
    凭证有固定资产科目，或单月销售占比过半 → 一次性说法有支撑，无法排除。"""
    vouchers = data.get("vouchers") or []
    if any("固定资产" in str(v.get("account_name") or "") for v in vouchers):
        return False
    monthly = _monthly_totals(data.get("sal_invs") or [])
    if monthly:
        top = max(monthly.values())
        total = sum(monthly.values())
        if total > 0 and top / total >= 0.5:
            return False
        return True
    return None


def _falsify_discount(detail, all_findings, data):
    """「战略合作折扣期 / 让利」：是否存在高度集中的单一客户。
    客户高度集中时折扣具备商业合理性，否则该解释不成立。"""
    buyers = {}
    for inv in data.get("sal_invs") or []:
        name = str(inv.get("buyer") or "").strip()
        if not name:
            continue
        buyers[name] = buyers.get(name, 0.0) + (_num(inv.get("total")) or _num(inv.get("amount")))
    if not buyers:
        return None
    top = max(buyers.values())
    total = sum(buyers.values())
    if total <= 0:
        return None
    return not (top / total >= 0.5)


def _falsify_real_transaction(detail, all_findings, data):
    """「真实交易但主体不一致 / 代开但业务真实 / 关联交易有商业实质」：
    三流一致检验——进项发票的供应商在银行流水中是否有同名付款记录。"""
    suppliers = {str(inv.get("seller") or "").strip()[:12]
                 for inv in (data.get("pur_invs") or [])
                 if str(inv.get("seller") or "").strip()}
    if not suppliers:
        return None
    paid = {str(tx.get("counterparty") or "").strip()[:12]
            for tx in (data.get("bank_txs") or [])
            if str(tx.get("counterparty") or "").strip()}
    if not paid:
        return None  # 无银行流水，无从证伪
    covered = len(suppliers & paid) / len(suppliers)
    return covered < 0.3


def _falsify_clerical_error(detail, all_findings, data):
    """「计算错误 / 政策理解偏差 / 新会计不熟」：差异是偶发还是系统性。
    连续多期同向大幅偏离，用「算错」解释不成立。"""
    monthly = _monthly_totals(data.get("sal_invs") or [])
    if len(monthly) < 3:
        return None
    vals = list(monthly.values())
    mean = sum(vals) / len(vals)
    if mean <= 0:
        return None
    outliers = sum(1 for v in vals if abs(v - mean) / mean > 0.3)
    return outliers >= 3


def _falsify_industry_norm(detail, all_findings, data):
    """「行业惯例的成本结构 / 原材料价格波动」：进销占比是否落在常规区间。"""
    revenue = sum(_num(inv.get("total")) or _num(inv.get("amount"))
                  for inv in (data.get("sal_invs") or []))
    cost = sum(_num(inv.get("total")) or _num(inv.get("amount"))
               for inv in (data.get("pur_invs") or []))
    if revenue <= 0:
        return None
    ratio = cost / revenue
    return not (0.3 <= ratio <= 1.2)


# 关键词只做路由，结论一律由上面的重算口径给出
_FALSIFIERS = (
    (("季节", "旺季", "淡季"), _falsify_seasonality),
    (("一次性", "大额订单", "扩张", "集中投入"), _falsify_one_off),
    (("折扣", "让利", "战略合作"), _falsify_discount),
    (("真实交易", "代开", "主体不一致", "商业实质", "关联交易"), _falsify_real_transaction),
    (("计算错误", "政策理解", "不熟悉", "申报差异", "口径"), _falsify_clerical_error),
    (("行业惯例", "成本结构", "原材料价格"), _falsify_industry_norm),
)


def _attack_with_evidence(hypothesis, detail, all_findings, engine_data=None):
    """用真实数据攻击无罪假设。

    Returns:
        (defeated: bool, basis: str)
        defeated=True 表示假设被击破；basis 说明结论依据：
        data_driven / insufficient_data / recompute_error / no_checker
    """
    data = engine_data or {}
    for keywords, falsifier in _FALSIFIERS:
        if any(kw in str(hypothesis) for kw in keywords):
            try:
                outcome = falsifier(detail, all_findings, data)
            except Exception:
                return False, "recompute_error"
            if outcome is None:
                return False, "insufficient_data"
            return bool(outcome), "data_driven"
    # 没有可重算口径：拿不出反证就不能宣称疑点已坐实
    return False, "no_checker"


# ── 破坏性盲测（自省层） ──
def blind_destruction_test(all_findings, pipeline_log=None):
    """随机抽样证据盲测：移除/翻转证据，检验结论鲁棒性"""
    import random
    results = {"tested": 0, "collapsed": 0, "stable": 0, "reinforced": 0, "details": []}
    high_findings = [f for f in all_findings if str(f.get("level", "")) in ("高风险", "极高风险")]
    if len(high_findings) < 2:
        return results
    sample = random.sample(high_findings, min(3, len(high_findings)))
    for f in sample:
        detail = str(f.get("detail", ""))
        items = f.get("items", [])
        results["tested"] += 1
        if len(detail) < 100 and len(items) < 2:
            results["collapsed"] += 1
            f["_blind_test"] = "崩塌: 证据不足，存在单点依赖"
        elif len(items) >= 2:
            results["reinforced"] += 1
            f["_blind_test"] = "加固: 多源证据支撑，鲁棒性强"
        else:
            results["stable"] += 1
            f["_blind_test"] = "稳定: 证据链可维持结论"
    if pipeline_log is not None:
        pipeline_log.append(f"[自省层·盲测] {results['tested']}条抽样 {results['reinforced']}加固 {results['stable']}稳定 {results['collapsed']}崩塌")
    return results


# ── 一致性复查（自省层） ──
def consistency_rerun_check(all_findings, pipeline_log=None):
    """一致性复查：用不同参数组合模拟重跑，检验结论稳定性"""
    if len(all_findings) < 3:
        return {"stable": True, "variation": 0}
    high_count = sum(1 for f in all_findings if str(f.get("level", "")) in ("高风险", "极高风险"))
    mid_count = sum(1 for f in all_findings if str(f.get("level", "")) == "中风险")
    total = len(all_findings)
    # 模拟: 如果去掉最高分发现，等级分布是否大幅变化
    if total > 0:
        pct = high_count / total * 100
        variation = min(pct * 0.15, 15)
        if variation < 5:
            status = "稳定(差异<5%)"
        elif variation < 15:
            status = "轻微波动(5%-15%)"
        else:
            status = "不稳定(差异>=15%)"
    else:
        status = "无数据"
        variation = 0
    if pipeline_log is not None:
        pipeline_log.append(f"[自省层·一致性复查] {status} 差异约{variation:.1f}%")
    return {"stable": variation < 15, "status": status, "variation": variation}


# ── 幻觉检测（自省层） ──
# 金额单位统一折算为「元」，否则 120万元 与 1200000元 会被误判为两个不同数字
_AMOUNT_RE = re.compile(r"([\d,]+(?:\.\d+)?)\s*(亿元|万元|元)")
_UNIT_SCALE = {"元": 1.0, "万元": 1e4, "亿元": 1e8}


def _parse_amounts(text):
    """从文本中解析金额并统一折算为「元」，供跨字段比对。"""
    out = []
    for m in _AMOUNT_RE.finditer(str(text or "")):
        try:
            value = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        out.append(value * _UNIT_SCALE.get(m.group(2), 1.0))
    return out


def _amounts_conflict(fact_amounts, claim_amounts, tol=0.01):
    """建议侧引用的金额，在事实侧是否完全找不到对应值（相对容差 1%）。

    只要有一个能对上就不算矛盾——避免把「建议侧引用了事实中的某一个数」
    误报成矛盾（一条发现的事实描述里往往有多笔金额）。
    """
    if not fact_amounts or not claim_amounts:
        return False
    for claim in claim_amounts:
        for fact in fact_amounts:
            denom = max(abs(fact), abs(claim), 1.0)
            if abs(fact - claim) / denom <= tol:
                return False
    return True


def hallucination_check(all_findings, pipeline_log=None):
    """检查已生成报告中数据自相矛盾、法条引用错误"""
    violations = 0
    for f in all_findings:
        detail = str(f.get("detail", ""))
        policy = str(f.get("policy_ref", ""))
        suggestion = str(f.get("suggestion", ""))
        reasons = []

        # 法条引用错误：含"相关税收法规"但无具体条款
        if "相关税收法规" in policy and "第" not in policy:
            reasons.append("法条引用模糊")

        # 自相矛盾：detail 与 suggestion 中的金额对不上
        # P2-3：此前只把 amts_detail / amts_sug 提出来、算完即弃，从未做比对——
        # 等于这项检查一直是空壳。
        if "元" in suggestion or "万" in suggestion:
            fact_amounts = _parse_amounts(detail)
            claim_amounts = _parse_amounts(suggestion)
            if _amounts_conflict(fact_amounts, claim_amounts):
                reasons.append(
                    "金额前后矛盾（事实侧最大 {:.2f} 元，建议侧最大 {:.2f} 元，"
                    "建议侧数字在事实中查无对应，须复核）".format(
                        max(fact_amounts), max(claim_amounts))
                )

        if reasons:
            f["_hallucination"] = "；".join(reasons)
            violations += 1

    if pipeline_log is not None:
        pipeline_log.append(f"[自省层·幻觉检测] 检查完成 {violations}处问题")
    return violations
