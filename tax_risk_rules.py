"""涉税规则加载与校验 — 从 tax_risk.py 提取"""
import json, os, sys
from typing import Dict, Any

CONFLICT_ANSWERS_FILE = os.path.join(os.path.dirname(__file__), 'tax_risk_conflict_answers.json')

def _load_saved_rules():
    """加载现行权威事实核验规则。"""
    try:
        from engine.methodology_catalog import load_flat_rules
        rules = load_flat_rules()
        if isinstance(rules, list) and len(rules) > 0:
            return rules
        return None
    except Exception:
        return None


# ── 规则校验标准（启动时自动审计·2026-07-18 对齐23字段现行体系）──
# 旧schema(urgency/remark/dataSource必填、score0-100、无极高风险)已废——那是23字段体系之前的老格式，
# 兼容旧调用方的最低字段校验；权威目录的完整结构由专门测试负责。
VALID_LEVELS = {'极高风险', '高风险', '中风险', '低风险', '良好', '信息'}
RULE_REQUIRED_FIELDS = ['id', 'item', 'category', 'score', 'level', 'suggestion']

def _validate_rules_on_load(rules: list):
    """启动时校验规则文件完整性，不合格打印警告到stdout"""
    issues = []
    seen_items = {}
    for r in rules:
        if not isinstance(r, dict):
            issues.append(f"[规则] 非法条目类型: {type(r).__name__} -> {str(r)[:50]}")
            continue
        rid = r.get('id', '?')
        ritem = str(r.get('item', '') or '').strip()

        # 必填字段
        for f in RULE_REQUIRED_FIELDS:
            val = r.get(f)
            if val is None or (isinstance(val, str) and val.strip() == ''):
                issues.append(f"[规则] ID={rid} 缺失字段: {f}")

        # score范围（现行1-10分制，auto规则允许0）
        score = r.get('score', -1)
        if not isinstance(score, (int, float)) or score < 0 or score > 10:
            issues.append(f"[规则] ID={rid} score={score} 无效(0-10)")

        # level
        if r.get('level', '') not in VALID_LEVELS:
            issues.append(f"[规则] ID={rid} level='{r.get('level','')}' 无效")

        # item唯一性
        if ritem:
            if ritem in seen_items:
                issues.append(f"[规则] ID={rid} item='{ritem}' 与 ID={seen_items[ritem]} 重复!")
            else:
                seen_items[ritem] = rid

        # suggestion长度
        if len(str(r.get('suggestion', '') or '')) < 5:
            issues.append(f"[规则] ID={rid} suggestion过短")
    
    if issues:
        print(f"\n规则文件校验发现 {len(issues)} 个问题，详见日志", file=sys.stderr)
        _ = [print(f"  {i}", file=sys.stderr) for i in issues]
        if len(issues) > 5:
            print(f"  ... 共{len(issues)}个", file=sys.stderr)
    return issues


# ── 冲突场景答案存储（用户确认风险冲突后保存）──
CONFLICT_ANSWERS_FILE = os.path.join(os.path.dirname(__file__), "tax_risk_conflict_answers.json")

def _load_conflict_answers(company_id: int) -> Dict[str, Any]:
    """加载某公司的冲突答案 {risk_item: {conflict_id: answer_dict}}"""
    try:
        if os.path.exists(CONFLICT_ANSWERS_FILE):
            with open(CONFLICT_ANSWERS_FILE, "r", encoding="utf-8") as f:
                all_answers = json.load(f)
            return all_answers.get(str(company_id), {})
    except Exception:
        pass
    return {}

def _save_conflict_answers(company_id: int, answers: Dict[str, Any]):
    """保存某公司的冲突答案"""
    all_answers = {}
    try:
        if os.path.exists(CONFLICT_ANSWERS_FILE):
            with open(CONFLICT_ANSWERS_FILE, "r", encoding="utf-8") as f:
                all_answers = json.load(f)
    except Exception:
        pass
    all_answers[str(company_id)] = answers
    with open(CONFLICT_ANSWERS_FILE, "w", encoding="utf-8") as f:
        json.dump(all_answers, f, ensure_ascii=False, indent=2)

def _apply_conflict_answers(results, company_id):
    """将用户已确认的冲突答案应用到结果中，调整风险等级和内容"""
    answers = _load_conflict_answers(company_id)
    if not answers:
        return
    for r in results:
        item = r.get("item", "")
        if item not in answers:
            continue
        item_answers = answers[item]
        scenarios = r.get("conflict_scenarios", [])
        if not scenarios:
            continue
        for sc in scenarios:
            sc_id = sc.get("id", "")
            if sc_id in item_answers:
                user_ans = item_answers[sc_id]
                if user_ans.get("confirmed"):
                    if_confirmed = sc.get("if_confirmed", {})
                    if if_confirmed.get("new_level"):
                        r["risk_level"] = if_confirmed["new_level"]
                    if if_confirmed.get("new_score") is not None:
                        r["risk_score"] = if_confirmed["new_score"]
                    if if_confirmed.get("override_detail"):
                        r["detail"] = if_confirmed["override_detail"]
                    if if_confirmed.get("override_suggestion"):
                        r["suggestion"] = if_confirmed["override_suggestion"]
                    r["risk_color"] = _risk_color(r["risk_score"])
                    r["_conflict_resolved"] = True
                    r["_conflict_answer"] = user_ans
                    break
        r["_saved_answers"] = {k: v for k, v in item_answers.items()}

