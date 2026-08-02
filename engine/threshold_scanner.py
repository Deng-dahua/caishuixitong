# -*- coding: utf-8 -*-
"""阈值扫描器 —— 解析规则threshold字段中的量化条件，对数据执行硬性检查触发规则

精写编制标准要求阈值含: 量化阈值 + 行业差异调整 + 四维前置条件 + 三色预警等级
示例: "差额>资产总额0.5%且绝对额>5万元，连续2期以上触发预警"

本模块从规则JSON的threshold字段提取数值条件，对引擎已解析的数据做检查。
"""
import re, json, os
from collections import defaultdict


def _safe_float(v, default=0.0):
    try:
        return float(v) if v not in (None, "", "None") else default
    except (ValueError, TypeError):
        return default


def _month_key(date_str):
    d = str(date_str).replace("-", "").replace("/", "").strip()
    return d[:6] if len(d) >= 6 else d


def scan_balance_equation(vouchers, trial_balance_data):
    """
    扫描资产负债表平衡 (对应规则#1)
    从trial_balance检查资产类借方总和 vs 负债权益类贷方总和
    如果vouchers和trial_balance都没数据，返回None(不触发)
    """
    if not trial_balance_data:
        return []

    total_assets = 0.0
    total_liab_equity = 0.0
    for row in trial_balance_data:
        code = str(row.get("code", ""))
        close_debit = _safe_float(row.get("close_debit", row.get("close", 0)) or 0)
        close_credit = _safe_float(row.get("close_credit", 0)) or 0
        if code.startswith("1"):
            total_assets += close_debit
            total_liab_equity += close_credit
        elif code.startswith("2") or code.startswith("4"):
            total_liab_equity += close_credit
            total_assets += close_debit
        else:
            total_assets += close_debit
            total_liab_equity += close_credit

    diff = abs(total_assets - total_liab_equity)
    if total_assets > 0:
        diff_pct = diff / total_assets
    else:
        diff_pct = 0

    findings = []
    # 阈值: >资产总额0.5%且绝对额>5万元
    if diff_pct > 0.005 and diff > 50000:
        findings.append({
            "type": "资产负债表不平·会计恒等式断裂",
            "rule_id": 1,
            "severity": "高风险",
            "detail": f"资产总额{total_assets:.0f}元 vs 负债+权益{total_liab_equity:.0f}元，差额{diff:.0f}元(差异率{diff_pct*100:.2f}%)，超过阈值0.5%且>5万元",
            "score": 9,
            "threshold_met": True
        })

    return findings


def scan_bank_vs_revenue(bank_txs, sal_invs):
    """
    扫描银行收款vs申报收入差异 (对应规则#21)
    """
    if not bank_txs:
        return []

    monthly_bank = defaultdict(float)
    for tx in bank_txs:
        credit = _safe_float(tx.get("credit", 0))
        if credit > 0:
            mk = _month_key(tx.get("date", ""))
            monthly_bank[mk] += credit

    monthly_sales = defaultdict(float)
    if sal_invs:
        for inv in sal_invs:
            total = _safe_float(inv.get("total", 0))
            if total > 0:
                mk = _month_key(inv.get("date", ""))
                monthly_sales[mk] += total

    all_months = set(monthly_bank.keys()) | set(monthly_sales.keys())
    anomaly_months = 0
    total_gap = 0
    for m in sorted(all_months):
        bank = monthly_bank.get(m, 0)
        sales = monthly_sales.get(m, 0)
        if sales > 0 and bank > sales * 1.1:
            anomaly_months += 1
            total_gap += (bank - sales)

    findings = []
    if anomaly_months >= 2 and total_gap > 50000:
        findings.append({
            "type": "银行收款与申报收入不匹配",
            "rule_id": 21,
            "severity": "高风险",
            "detail": f"{anomaly_months}个月银行收款>申报销售额10%以上，累计差额{total_gap:.0f}元",
            "score": 9,
            "threshold_met": True
        })

    return findings


def scan_voucher_volume_anomaly(vouchers):
    """
    扫描凭证量异常 (对应规则#2)
    月凭证量 > 行业基准2倍(简化: 月均>200张)且无对应人员/资产增长
    """
    if not vouchers:
        return []

    monthly = defaultdict(int)
    for v in vouchers:
        mk = _month_key(v.get("date", ""))
        monthly[mk] += 1

    if not monthly:
        return []

    stats = list(monthly.values())
    avg = sum(stats) / len(stats)
    # 简化阈值: 月均>200张
    if avg > 200:
        return [{
            "type": "月凭证量异常偏高",
            "rule_id": 2,
            "severity": "中风险",
            "detail": f"月均凭证量{avg:.0f}张，超过200张基准线",
            "score": 7,
            "threshold_met": True
        }]
    return []


# 旧扫描函数保留用于历史结果解释，但其数据口径不足以支持生产触发：
# 规则#1缺少资产负债表两侧字段，#2使用未经验证的固定行业基准，#21把开票
# 金额误写成申报收入。生产可执行规则已迁移至 verified_rule_engine。
SCANNERS = {}


def scan_all(engine_data):
    """
    对所有已注册的阈值规则执行扫描。

    Args:
        engine_data: dict, 含 bank_txs/sal_invs/pur_invs/vouchers/trial_balance等

    Returns:
        list of findings
    """
    all_findings = []
    for rule_id, scanner_fn in SCANNERS.items():
        try:
            results = scanner_fn(
                vouchers=engine_data.get("vouchers", []),
                trial_balance_data=engine_data.get("trial_balance", []),
                bank_txs=engine_data.get("bank_txs", []),
                sal_invs=engine_data.get("sal_invs", [])
            )
            if results:
                all_findings.extend(results)
        except Exception:
            pass
    return all_findings
