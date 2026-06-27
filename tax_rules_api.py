"""
涉税风险规则管理模块 - 从 main.py 自动拆分
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
import os, io, json, re as _re_module

from database import get_db

router = APIRouter(tags=["规则管理"])

@router.post("/api/tax-risk-rules/audit")
async def tax_risk_rules_audit(request: Request):
    """接收当前规则 JSON，返回 8 层质量审计报告"""
    try:
        data = await request.json()
    except Exception:
        return {"ok": False, "error": "无效的 JSON 数据"}

    from difflib import SequenceMatcher as _SeqMatcher
    from collections import Counter as _Counter
    import re as _re

    report = {"ok": True, "total": len(data), "layers": [], "summary": {}}
    issues_found = []

    # --- 第1层: ID和名称精确去重 ---
    ids = [r["id"] for r in data]
    dup_ids = [i for i in ids if ids.count(i) > 1]
    items = [r["item"] for r in data]
    dup_names = {k: v for k, v in _Counter(items).items() if v > 1}
    layer1 = {"name": "ID/名称精确去重", "pass": not dup_ids and not dup_names}
    if dup_ids:
        layer1["detail"] = f"重复ID: {list(set(dup_ids))}"
    if dup_names:
        layer1["detail"] = f"重复名称: {dup_names}"
    report["layers"].append(layer1)
    if not layer1["pass"]:
        issues_found.append("ID/名称去重")

    # --- 第2层: 名称相似度 (>=85%) ---
    sim_names = []
    for i in range(len(data)):
        for j in range(i + 1, len(data)):
            ratio = _SeqMatcher(None, data[i]["item"], data[j]["item"]).ratio()
            if ratio >= 0.85:
                sim_names.append({
                    "ratio": round(ratio, 2),
                    "a": data[i]["item"], "a_cat": data[i]["category"],
                    "b": data[j]["item"], "b_cat": data[j]["category"]
                })
    layer2 = {"name": "名称相似度检查 (≥85%)", "pass": len(sim_names) == 0}
    if sim_names:
        layer2["detail"] = sim_names
        issues_found.append("名称相似度")
    report["layers"].append(layer2)

    # --- 第3层: detail 相似度 (>=80%) ---
    by_cat = {}
    for r in data:
        by_cat.setdefault(r["category"], []).append(r)
    sim_detail = []
    # 同分类
    for cat, rules in by_cat.items():
        for i in range(len(rules)):
            for j in range(i + 1, len(rules)):
                ratio = _SeqMatcher(None, rules[i]["detail"], rules[j]["detail"]).ratio()
                if ratio >= 0.80:
                    sim_detail.append({
                        "type": "同分类", "cat": cat, "ratio": round(ratio, 2),
                        "a": rules[i]["item"], "b": rules[j]["item"]
                    })
    # 跨分类
    for i in range(len(data)):
        for j in range(i + 1, len(data)):
            if data[i]["category"] != data[j]["category"]:
                ratio = _SeqMatcher(None, data[i]["detail"], data[j]["detail"]).ratio()
                if ratio >= 0.80:
                    sim_detail.append({
                        "type": "跨分类", "ratio": round(ratio, 2),
                        "a": f"{data[i]['item']}({data[i]['category']})",
                        "b": f"{data[j]['item']}({data[j]['category']})"
                    })
    layer3 = {"name": "detail 相似度检查 (≥80%)", "pass": len(sim_detail) == 0}
    if sim_detail:
        layer3["detail"] = sim_detail
        issues_found.append("detail相似度")
    report["layers"].append(layer3)

    # --- 第4层: 语义同类跨分类扫描 ---
    keyword_groups = {
        "零申报/零税额": ["零申报", "零税额"],
        "留抵退税/留抵": ["留抵退税", "留抵", "进项留抵"],
        "红冲/作废": ["红冲", "作废"],
        "开票限额/顶额": ["顶额", "开票限额"],
        "进项转出": ["进项转出", "进项税额转出"],
        "发票跨期": ["跨期", "跨年"],
        "税负率": ["税负率"],
        "咨询费/服务费": ["咨询", "服务费"],
        "资金回流": ["资金回流"],
    }
    sem_overlaps = []
    for group_name, keywords in keyword_groups.items():
        matches = []
        seen = set()
        for kw in keywords:
            for r in data:
                combined = r["item"] + r["detail"]
                if kw in combined and r["item"] not in seen:
                    seen.add(r["item"])
                    matches.append({"item": r["item"], "category": r["category"]})
        cats = set(m["category"] for m in matches)
        if len(matches) > 1 and len(cats) > 1:
            sem_overlaps.append({"group": group_name, "categories": list(cats), "count": len(matches), "items": matches})
    layer4 = {"name": "语义同类跨分类扫描", "pass": True}
    if sem_overlaps:
        layer4["detail"] = sem_overlaps
    report["layers"].append(layer4)

    # --- 第5层: 碎片分类 (<2条) ---
    cats = _Counter(r["category"] for r in data)
    fragments = {cat: cnt for cat, cnt in cats.items() if cnt < 2}
    layer5 = {"name": "碎片分类检测 (<2条)", "pass": len(fragments) == 0}
    if fragments:
        frag_list = []
        for cat, cnt in fragments.items():
            citems = [r["item"] for r in data if r["category"] == cat]
            frag_list.append({"category": cat, "count": cnt, "items": citems})
        layer5["detail"] = frag_list
        issues_found.append("碎片分类")
    report["layers"].append(layer5)

    # --- 第6层: 归类不当 ---
    # tax_map: 税种关键词 → 允许的分类列表
    # 判断逻辑：如果规则detail/suggestion中出现某税种关键词，但分类不在允许列表中 → 标记为归类不当
    # 以下已根据实际业务关系做了合理豁免：
    #   - 城建税必然关联增值税；资金往来/隐匿虚增必然关联个税；
    #   - 税负水平关联所有税种；征管风险常涉及进项税额；
    #   - 发票深度分析影响多个税种；经营实质涉及增值税认定；
    #   - 企业所得税分类中未分配利润规则涉及规避股东个税。
    tax_map = {
        "增值税": ["增值税专项", "申报比对", "发票合规", "发票异常", "发票深度", "税负水平", "城建税", "经营实质"],
        "进项税额": ["增值税专项", "申报比对", "发票合规", "发票异常", "发票深度", "交易特征", "征管风险"],
        "销项税额": ["增值税专项", "申报比对", "发票合规", "发票异常", "发票深度"],
        "企业所得税": ["企业所得税", "纳税调整", "成本结构", "财务健康", "税负水平", "发票深度"],
        "汇算清缴": ["企业所得税", "纳税调整", "个人所得税"],
        "纳税调增": ["企业所得税", "纳税调整", "成本结构"],
        "个人所得税": ["个人所得税", "企业所得税"],
        "个税": ["个人所得税", "薪酬福利", "资金往来", "隐匿虚增", "发票深度", "企业所得税"],
        "代扣代缴": ["个人所得税"],
    }
    mismatches = []
    for r in data:
        detail = r["detail"] + r.get("suggestion", "")
        for tax_kw, allowed_cats in tax_map.items():
            if tax_kw in detail and r["category"] not in allowed_cats:
                mismatches.append({"item": r["item"], "category": r["category"], "keyword": tax_kw})
                break
    layer6 = {"name": "归类不当检测", "pass": len(mismatches) == 0}
    if mismatches:
        layer6["detail"] = mismatches
        issues_found.append("归类不当")
    report["layers"].append(layer6)

    # --- 第7层: level 一致性 ---
    valid_levels = {"高风险", "中风险", "低风险", "良好"}
    bad_levels = []
    for r in data:
        lv = r.get("level", "")
        if lv not in valid_levels:
            bad_levels.append({"item": r["item"], "level": lv})
    layer7 = {"name": "level 字段一致性", "pass": len(bad_levels) == 0}
    if bad_levels:
        layer7["detail"] = bad_levels
        issues_found.append("level不一致")
    report["layers"].append(layer7)

    # --- 第8层: 评分跨度 ---
    by_cat2 = {}
    for r in data:
        by_cat2.setdefault(r["category"], []).append(r.get("score", 0))
    wide_cats = []
    for cat, scores in sorted(by_cat2.items()):
        if len(scores) > 1 and max(scores) - min(scores) >= 5:
            wide_cats.append({"category": cat, "min": min(scores), "max": max(scores), "spread": max(scores) - min(scores)})
    layer8 = {"name": "同分类评分跨度检查 (≥5分)", "pass": len(wide_cats) == 0}
    if wide_cats:
        layer8["detail"] = wide_cats
    report["layers"].append(layer8)

    # --- 第9层(P0): 同item不同ID重复检测 ---
    by_item = {}
    for r in data:
        by_item.setdefault(r["item"], []).append(r["id"])
    p0_dups = {k: v for k, v in by_item.items() if len(v) > 1}
    layer9 = {"name": "P0-同item重复检测", "pass": len(p0_dups) == 0}
    if p0_dups:
        layer9["detail"] = [{"item": k, "ids": v} for k, v in p0_dups.items()]
        issues_found.append("P0同item重复")
    report["layers"].append(layer9)

    # --- 第10层(P1): urgency非法值检测 ---
    valid_urgencies = {"紧急", "一般", "提醒"}
    bad_urgency = [(r["id"], r.get("urgency", "")) for r in data if r.get("urgency", "") not in valid_urgencies]
    layer10 = {"name": "P1-urgency合法性", "pass": len(bad_urgency) == 0}
    if bad_urgency:
        layer10["detail"] = [{"id": id, "urgency": u} for id, u in bad_urgency]
        issues_found.append("P1urgency非法值")
    report["layers"].append(layer10)

    # --- 第11层(P2): 碎片分类检测（≤2条的） ---
    cats_all = _Counter(r["category"] for r in data)
    frag_cats = {k: v for k, v in cats_all.items() if v <= 2}
    layer11 = {"name": "P2-碎片分类(≤2条)", "pass": len(frag_cats) == 0}
    if frag_cats:
        layer11["detail"] = dict(frag_cats)
        issues_found.append("P2碎片分类")
    report["layers"].append(layer11)

    # --- 第12层(P3): detectable字段缺失检测 ---
    missing_detectable = [(r["id"], r["item"]) for r in data if "detectable" not in r]
    layer12 = {"name": "P3-detectable字段", "pass": len(missing_detectable) == 0}
    if missing_detectable:
        layer12["detail"] = [{"id": id, "item": item} for id, item in missing_detectable]
        issues_found.append("P3缺少detectable")
    report["layers"].append(layer12)

    # --- 汇总 ---
    levels_all = _Counter(r.get("level", "未设置") for r in data)
    scores_all = [r.get("score", 0) for r in data]
    report["summary"] = {
        "total_rules": len(data),
        "total_categories": len(cats_all),
        "level_distribution": dict(levels_all),
        "score_range": f"{min(scores_all)}~{max(scores_all)}",
        "avg_score": round(sum(scores_all) / len(scores_all), 1),
        "category_distribution": dict(cats_all.most_common()),
        "issues_found": issues_found,
        "all_clear": len(issues_found) == 0
    }
    return report

# ==================== 涉税风险规则自动修复 API ====================
@router.post("/api/tax-risk-rules/fix")
async def tax_risk_rules_fix(request: Request):
    """接收当前规则 JSON，自动修复可修复的问题，返回修复后规则"""
    try:
        data = await request.json()
    except Exception:
        return {"ok": False, "error": "无效的 JSON 数据"}

    from difflib import SequenceMatcher as _SeqMatcher
    from collections import Counter as _Counter
    import copy as _copy

    rules = _copy.deepcopy(data)
    fixes = []
    skipped = []

    # ========== 修复1: 碎片分类 → 合并到语义最相关的分类 ==========
    cat_counts = _Counter(r["category"] for r in rules)
    fragments = {cat: cnt for cat, cnt in cat_counts.items() if cnt < 2}

    # 碎片合并映射表：碎片分类 → 最相关的目标分类
    fragment_merge_map = {
        "印花税": "税负水平",
        "行业专项": "经营实质",
        "城建税": "税负水平",
        "房产税": "税负水平",
        "客户穿透": "交易特征",
        "供应商穿透": "交易特征",
        "政策执行": "征管风险",
    }

    if fragments:
        for frag_cat in fragments:
            target = None
            if frag_cat in fragment_merge_map:
                target = fragment_merge_map[frag_cat]
            else:
                # 默认：按名称相似度找最匹配的非碎片分类
                best = (0, None)
                for cat in cat_counts:
                    if cat != frag_cat and cat_counts[cat] >= 2:
                        ratio = _SeqMatcher(None, frag_cat, cat).ratio()
                        if ratio > best[0]:
                            best = (ratio, cat)
                if best[1]:
                    target = best[1]

            if target:
                cnt = 0
                for r in rules:
                    if r["category"] == frag_cat:
                        r["category"] = target
                        cnt += 1
                fixes.append(f"碎片合并: {frag_cat}({cnt}条) → {target}")

    # ========== 修复2: 归类不当 → 重新分配 ==========
    tax_map = {
        "增值税": ["增值税专项", "申报比对", "发票合规", "发票异常", "发票深度", "税负水平", "城建税", "经营实质"],
        "进项税额": ["增值税专项", "申报比对", "发票合规", "发票异常", "发票深度", "交易特征", "征管风险"],
        "销项税额": ["增值税专项", "申报比对", "发票合规", "发票异常", "发票深度"],
        "企业所得税": ["企业所得税", "纳税调整", "成本结构", "财务健康", "税负水平", "发票深度"],
        "汇算清缴": ["企业所得税", "纳税调整", "个人所得税"],
        "纳税调增": ["企业所得税", "纳税调整", "成本结构"],
        "个人所得税": ["个人所得税", "企业所得税"],
        "个税": ["个人所得税", "薪酬福利", "资金往来", "隐匿虚增", "发票深度", "企业所得税"],
        "代扣代缴": ["个人所得税"],
    }

    # 关键词→首选分类映射（当多个允许时选第一个）
    keyword_preferred = {
        "增值税": "增值税专项",
        "进项税额": "增值税专项",
        "销项税额": "增值税专项",
        "企业所得税": "企业所得税",
        "汇算清缴": "纳税调整",
        "纳税调增": "纳税调整",
        "个人所得税": "个人所得税",
        "个税": "个人所得税",
        "代扣代缴": "个人所得税",
    }

    for r in rules:
        detail = r["detail"] + r.get("suggestion", "")
        for tax_kw, allowed_cats in tax_map.items():
            if tax_kw in detail and r["category"] not in allowed_cats:
                # 找到关键词 → 选首选分类
                preferred = keyword_preferred.get(tax_kw, allowed_cats[0])
                old_cat = r["category"]
                r["category"] = preferred
                fixes.append(f"归类纠正: '{r['item'][:30]}' {old_cat} → {preferred} (关键词: {tax_kw})")
                break  # 只修第一个触发的

    # ========== 修复3: level 标准化 ==========
    level_map = {
        "高": "高风险", "中": "中风险", "低": "低风险",
        "较高": "高风险", "较低": "低风险", "中等风险": "中风险",
        "高危": "高风险",
    }
    for r in rules:
        if r["level"] in level_map:
            old = r["level"]
            r["level"] = level_map[old]
            fixes.append(f"级别标准化: '{r['item'][:30]}' {old} → {r['level']}")

    # ========== P0修复: 同item不同ID去重 ==========
    by_item_p0 = {}
    for r in rules:
        by_item_p0.setdefault(r["item"], []).append(r)
    for item, group in by_item_p0.items():
        if len(group) > 1:
            group.sort(key=lambda x: x.get("score", 0), reverse=True)
            for dup in group[1:]:
                rules.remove(dup)
                fixes.append(f"P0去重: 移除{item}(ID={dup['id']}，保留ID={group[0]['id']})")

    # ========== P1修复: urgency非法值规范化 ==========
    urgency_fix_map = {"建议": "提醒", "高": "紧急", "警示": "一般", "重要": "一般"}
    for r in rules:
        u = r.get("urgency", "")
        if u in urgency_fix_map:
            old_u = u
            r["urgency"] = urgency_fix_map[u]
            fixes.append(f"P1: urgency '{old_u}'→'{r['urgency']}' (ID={r['id']})")

    # ========== P3修复: 补充detectable字段 ==========
    auto_detectable = {"账务数据","发票合规","发票深度","成本结构","申报比对","隐匿虚增","税负水平","个人所得税","纳税调整","政策执行","资金往来","薪酬合规","财务健康","增值税专项","经营实质","合同风险","供应商穿透","交易特征","企业所得税","薪酬福利","平台经济","征管风险","多源交叉","经营穿透","经营分析","时间线调查","供应商画像","资金流向","人员画像","三角验证","现金流分析","时间模式","关联交易","资产匹配","行业对标","发票生命周期"}
    for r in rules:
        if "detectable" not in r:
            r["detectable"] = r["category"] in auto_detectable
            fixes.append(f"P3: 补充detectable={r['detectable']} (ID={r['id']})")

    # ========== 重新生成审计报告 ==========
    # 轻量审计（仅检查是否还有问题）
    cat_counts2 = _Counter(r["category"] for r in rules)
    fragments2 = {cat: cnt for cat, cnt in cat_counts2.items() if cnt < 2}
    mismatches2 = []
    for r in rules:
        detail = r["detail"] + r.get("suggestion", "")
        for tax_kw, allowed_cats in tax_map.items():
            if tax_kw in detail and r["category"] not in allowed_cats:
                mismatches2.append(r["item"])
                break

    remaining = []
    if fragments2:
        remaining.append(f"还有 {len(fragments2)} 个碎片分类需手动处理")
        skipped.extend([f"{cat}({cnt}条)" for cat, cnt in fragments2.items()])
    if mismatches2:
        remaining.append(f"还有 {len(mismatches2)} 项归类不当需手动处理")
        skipped.extend(mismatches2)

    all_fixed = len(fragments2) == 0 and len(mismatches2) == 0

    return {
        "ok": True,
        "fixed_rules": rules,
        "fixes_applied": fixes,
        "fixes_count": len(fixes),
        "remaining_issues": remaining,
        "skipped_items": skipped,
        "all_fixed": all_fixed,
        "summary": {
            "total": len(rules),
            "categories": len(cat_counts2),
            "category_distribution": dict(cat_counts2.most_common()),
        }
    }


