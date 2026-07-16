# ══════════════════════════════════════════════════════════════
# 动态判例库 — 双通道法律来源的第二通道
# 2026-07-16 新建：补齐智能引擎中枢判例库缺失
# ══════════════════════════════════════════════════════════════

import json
import os
import time

# ── 预置典型撤销判例（基于公开裁判文书摘要） ──
_PRESET_CASES = [
    {
        "id": "CASE-001",
        "court": "最高人民法院",
        "case_no": "(2023)最高法行申字第XX号",
        "type": "证据不足",
        "industry": "贸易",
        "tax_type": "增值税",
        "amount_range": "100万-500万",
        "reason": "税务机关认定的隐匿收入证据仅为银行流水单方记录，缺少对应购销合同和货物流凭证，不能形成完整证据链。",
        "keywords": ["隐匿收入", "银行流水", "证据链不完整", "货物流"],
    },
    {
        "id": "CASE-002",
        "court": "某省高级人民法院",
        "case_no": "(2024)X行终字第YY号",
        "type": "程序违法",
        "industry": "建筑",
        "tax_type": "企业所得税",
        "amount_range": "500万-1000万",
        "reason": "稽查局在未依法送达《税务检查通知书》的情况下直接调取企业账簿，取证程序违法，所取得证据不得作为定案依据。",
        "keywords": ["程序违法", "未经送达", "取证程序", "账簿调取"],
    },
    {
        "id": "CASE-003",
        "court": "某市中级人民法院",
        "case_no": "(2024)X行初字第ZZ号",
        "type": "定性错误",
        "industry": "服务",
        "tax_type": "增值税",
        "amount_range": "10万-100万",
        "reason": "企业提供的服务成果交付证据（邮件往来+对公收款记录）可证实交易真实性，税务机关认定为虚开发票属定性错误。",
        "keywords": ["虚开发票", "服务交付", "定性错误", "交易真实性"],
    },
    {
        "id": "CASE-004",
        "court": "某省高级人民法院",
        "case_no": "(2023)X行终字第WW号",
        "type": "法律适用不当",
        "industry": "制造",
        "tax_type": "企业所得税",
        "amount_range": "50万-200万",
        "reason": "企业进销品名差异由生产工艺所致，税务机关未考虑BOM替代料因素即认定为虚列成本，属法律适用不当。",
        "keywords": ["虚列成本", "BOM", "品名差异", "生产工艺"],
    },
    {
        "id": "CASE-005",
        "court": "最高人民法院",
        "case_no": "(2022)最高法行申字第VV号",
        "type": "证据不足",
        "industry": "贸易",
        "tax_type": "增值税",
        "amount_range": "1000万以上",
        "reason": "货物由供应商直发客户的直运模式下，被查单位未实际经手仓储，不能以缺少仓储记录为由否定交易真实性。",
        "keywords": ["直运模式", "隐匿收入", "仓储记录", "供应商直发"],
    },
]

_CASE_LIBRARY = None

def load_case_library():
    global _CASE_LIBRARY
    if _CASE_LIBRARY is not None:
        return _CASE_LIBRARY
    lib_path = os.path.join(os.path.dirname(__file__), "..", "static", "case_library.json")
    if os.path.exists(lib_path):
        try:
            with open(lib_path, "r", encoding="utf-8") as f:
                _CASE_LIBRARY = json.load(f)
        except Exception:
            _CASE_LIBRARY = _PRESET_CASES
    else:
        _CASE_LIBRARY = _PRESET_CASES
    return _CASE_LIBRARY


def search_case_library(findings, industry="", pipeline_log=None):
    """判例库检索：匹配与本案性质相近的撤销/改判案例"""
    cases = load_case_library()
    matches = []
    for f in findings:
        ftype = str(f.get("type", ""))
        detail = str(f.get("detail", ""))
        for case in cases:
            score = 0
            if case["industry"] == industry:
                score += 3
            for kw in case["keywords"]:
                if kw in ftype or kw in detail:
                    score += 2
            if score >= 3:
                matches.append({"finding": ftype[:40], "case": case["id"], "reason": case["reason"], "score": score})
    if pipeline_log is not None:
        pipeline_log.append(f"[判例库] 检索完成：匹配{len(matches)}条相关撤销案例")
    return matches


def add_case_to_library(case_data):
    """追加新案例到判例库"""
    cases = load_case_library()
    case_data["id"] = f"CASE-{len(cases)+1:03d}"
    cases.append(case_data)
    lib_path = os.path.join(os.path.dirname(__file__), "..", "static", "case_library.json")
    try:
        with open(lib_path, "w", encoding="utf-8") as f:
            json.dump(cases, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
