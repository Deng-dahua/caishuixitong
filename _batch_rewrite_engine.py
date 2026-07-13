# -*- coding: utf-8 -*-
"""税务疑点库批量精写引擎
驱动智能更新按钮（DeepSeek LLM），按23字段精写标准逐条重写全库。
特性：动态读engine.memory标准 / 断点续传 / 引擎自动校验 / 质量统计 / 实时输出
用法：python _batch_rewrite_engine.py [--resume] [--max N] [--dry]
"""
import json, os, sys, time, re
import httpx

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
RULES_PATH = os.path.join(THIS_DIR, "static", "tax_risk_rules_local_export.json")
BACKUP_PATH = RULES_PATH.replace(".json", f".bak_batch_{int(time.time())}.json")

# ━━ 动态读取精写标准（不维护独立副本）━━
from engine.memory import TAX_BURDEN_RULES
RPW = TAX_BURDEN_RULES["rule_precise_writing"]
IRON = " ".join(RPW["iron_rules"])
EC = RPW["exhaustion_criteria"]
EXHAUST = EC["principle"]
EXHAUST_DRILL = EC.get("drill_questions_done", {}).get("最终判定", "")
EXHAUST_DIR = EC.get("direction_done", {}).get("结束条件", "")
EXHAUST_NR = EC.get("normal_reason_done", {}).get("五个自问", "")
RLW = RPW["repealed_law_watch"]
REPEALED_ITEMS = []
for r in RLW["repealed"]:
    n = r.get("废止法规") or r.get("更新法规", "?")
    p = r.get("替代法规") or r.get("现行版本", "?")
    REPEALED_ITEMS.append(f"{n}→{p}")
REPEALED = "；".join(REPEALED_ITEMS)
BASELINE = RLW["current_valid_baseline"]

# ━━ LLM配置 ━━
from main import get_api_config
CFG = get_api_config()
API_KEY = CFG.get("key", "")
BASE_URL = CFG.get("base_url", "https://api.deepseek.com/v1").rstrip("/")
MODEL = CFG.get("model", "deepseek-chat")

# ━━ 精写Prompt模板（JSON字段模板强制英文字段名）━━
PROMPT_HEADER = (
    "你是50年税务稽查局长。逐条按23字段精写标准做深度重写。以下标准从引擎权威源 engine/memory.py 动态注入。\n\n"
    "【铁律】" + IRON + "\n"
    "【穷举判定·追问】" + EXHAUST + " " + EXHAUST_DRILL + "\n"
    "【穷举判定·推理链】" + EXHAUST_DIR + "\n"
    "【穷举判定·正常解释】" + EXHAUST_NR + "\n"
    "【法规红线·严禁引用废止法】" + REPEALED + "\n"
    "【现行有效基线】" + BASELINE + "\n\n"
    "【输出格式铁律】每条规则输出严格以下JSON格式，键名必须精确英文（不得用中文编号名！）。不设上限字数，应写尽写：\n\n"
    '{\n'
    '  "id": 原编号,\n'
    '  "item": "异常名称",\n'
    '  "category": "所属类别",\n'
    '  "level": "极高/高风险/中风险/低风险",\n'
    '  "score": 1-10,\n'
    '  "check_frequency": "高频/中频/低频",\n'
    '  "policy_ref": "现行有效的《XX法》(版本)第X条:条文内容（法规现行性核验:2026-07-13）",\n'
    '  "tax_impact": "税种(影响描述)",\n'
    '  "applicable_condition": "行业限制+纳税人资质+规模门槛+时间条件+金额门槛",\n'
    '  "source": "LLM智能更新",\n'
    '  "auto_type": "",\n'
    '  "direction": "【推理第N层:XX法则】依赖证据:XX→结论:XX。层与层因果递进,每层标注依赖证据。",\n'
    '  "drill_questions": "第一组【事实层】:\\nQ1:问题→潜台词:稽查意图。A:应对话术。追问三维覆盖度决定数量。",\n'
    '  "phenomena": "异常定义+典型表现(至少5种)+兜底条款+排除条件",\n'
    '  "focus": "①舞弊手法:操作方式→识别要点。②③④⑤逐条标注。",\n'
    '  "normal_reason": "①情形——需提供(具体证据文件)。穷举全部真实合法情形。",\n'
    '  "determination": "路径一(无法证明→线索)…路径二(部分证明→强证据)…路径三(完整证明→铁证)…。",\n'
    '  "risk_table": "税种:具体风险描述。影响几个写几个,区分核心/次要/间接。",\n'
    '  "evidence": "四层框架(货物流+合同资金流+业务合理性+排雷)+优先级标注",\n'
    '  "threshold": "量化阈值+行业差异调整+前置条件四维度+触发方式",\n'
    '  "action": "至少3步含1项现场核查,每步=动作类型+具体操作+预期产出",\n'
    '  "suggestion": "稽查局视角:定性→补税→滞纳金→罚款(征管法条款)→移送标准",\n'
    '  "remedy": "企业视角:自查阶段→应对阶段(含话术策略)→制度阶段"\n'
    '}\n\n'
    "【追问格式铁律】必须严格: Q{N}:{问题}→潜台词:{稽查意图}。A:{应对话术}。三组递进。\n"
    "【推理格式铁律】必须:【推理第N层:法则名称】依赖证据:XX→结论:XX\n"
    "【禁止】禁止凑数凑字、禁止固定数量、禁止引用废止法规、禁止用中文编号如⑩⑬作为JSON键名。\n"
    "【输出】只返回JSON数组，不做任何解释。"
)

def build_batch_prompt(target_rules):
    """为一批规则构建精写输入"""
    inputs = []
    for r in target_rules:
        inputs.append({
            "id": r["id"],
            "item": r.get("item", ""),
            "category": r.get("category", ""),
            "level": r.get("level", ""),
            "score": r.get("score", 5),
            "existing_direction": str(r.get("direction", ""))[:300],
            "existing_detail": str(r.get("detail", ""))[:200]
        })
    return PROMPT_HEADER + f"\n\n【待精写规则】\n{json.dumps(inputs, ensure_ascii=False, indent=2)}"

def call_llm(prompt, max_retries=2):
    """调用DeepSeek LLM，失败自动重试"""
    for attempt in range(max_retries + 1):
        try:
            resp = httpx.post(
                f"{BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                json={"model": MODEL, "messages": [{"role": "user", "content": prompt}],
                      "temperature": 0.3, "max_tokens": 12000},
                timeout=180
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            if resp.status_code == 429:  # rate limit
                wait = min((attempt + 1) * 10, 60)
                print(f"  限流,等待{wait}s..."); time.sleep(wait)
                continue
            print(f"  LLM错误 HTTP{resp.status_code}: {resp.text[:200]}")
            if attempt < max_retries: time.sleep(5)
        except Exception as e:
            print(f"  调用异常: {e}")
            if attempt < max_retries: time.sleep(10)
    return None

def validate_batch(rewritten):
    """引擎自动校验：有效期核查 + 字段完整性"""
    from engine.law_validity_checker import auto_process
    auto_process(rewritten)
    REQUIRED = ["id","item","category","level","score","direction","drill_questions",
                "normal_reason","determination","risk_table","evidence","threshold",
                "action","suggestion","remedy","policy_ref","tax_impact","phenomena","focus"]
    for rw in rewritten:
        missing = [k for k in REQUIRED if not rw.get(k)]
        if missing:
            rw["_validation_errors"] = missing
    return rewritten

def quality_stats(rules_batch):
    """批量质量统计"""
    for rw in rules_batch:
        dr = str(rw.get("direction", ""))
        dq = str(rw.get("drill_questions", ""))
        nr = str(rw.get("normal_reason", ""))
        layers = dr.count("推理第") + dr.count("【推理第")
        questions = dq.count("→潜台词")
        reasons = max(nr.count("需提供证据"), nr.count("需提供"))
        verified = "核验" in str(rw.get("policy_ref", ""))
        english_keys = all(not k.startswith("⑩") and not k.startswith("⑬") for k in rw.keys() if k != "_validation_errors")
        yield {"id": rw["id"], "layers": layers, "questions": questions,
               "reasons": reasons, "verified": verified, "english_keys": english_keys,
               "errors": rw.get("_validation_errors", [])}

def save_rules(rules):
    """写回JSON + 自动备份"""
    if not os.path.exists(BACKUP_PATH):
        import shutil; shutil.copy2(RULES_PATH, BACKUP_PATH)
        print(f"  已备份: {BACKUP_PATH}")
    with open(RULES_PATH, "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)

def main():
    dry = "--dry" in sys.argv
    resume = "--resume" in sys.argv
    max_batches = int(next((a.replace("--max=","") for a in sys.argv if a.startswith("--max=")), 0))
    
    with open(RULES_PATH, encoding="utf-8") as f:
        rules = json.load(f)
    
    # 确定优先级：极高 > 高 > 中 > 低
    level_order = {"极高风险": 0, "极高": 0, "高风险": 1, "高": 1, "中风险": 2, "低风险": 3, "信息": 4}
    pending = sorted(
        [r for r in rules if (len(str(r.get("direction",""))) < 300 or "→潜台词" not in str(r.get("drill_questions","")))],
        key=lambda r: (level_order.get(r.get("level",""), 9), r.get("id", 9999))
    )
    
    print(f"===== 批量精写引擎 =====")
    print(f"总规则: {len(rules)} | 待精写: {len(pending)}条 | 每批3条 | dry={'是' if dry else '否'}")
    print(f"已备份: {BACKUP_PATH}")
    
    if dry:
        print("DRY模式——预览前3批:")
        for b in range(min(3, len(pending) // 3 + 1)):
            batch = pending[b*3:(b+1)*3]
            print(f"  第{b+1}批: {[r['id'] for r in batch]} - {[r.get('item','')[:20] for r in batch]}")
        return
    
    batch_num = 0
    total_done = 0
    for bi in range(0, len(pending), 3):
        batch = pending[bi:bi+3]
        if not batch:
            break
        batch_num += 1
        ids = [r["id"] for r in batch]
        items = "、".join(r.get("item","")[:15] for r in batch)
        print(f"\n第{batch_num}批 [{ids[0]}-{ids[-1]}]: {items}")
        
        # 构建prompt并调用LLM
        prompt = build_batch_prompt(batch)
        print("  调LLM...", end="", flush=True)
        ai_text = call_llm(prompt)
        if not ai_text:
            print("失败(跳过)")
            if batch_num > 1: save_rules(rules)  # 失败也保存已完成进度
            continue
        
        # 解析
        jm = re.search(r'\[[\s\S]*\]', ai_text)
        if not jm:
            print("JSON解析失败,重试...")
            ai_text = call_llm(prompt + "\n\n【上一次你返回了非JSON内容,请修正。严格返回JSON数组!】")
            jm = re.search(r'\[[\s\S]*\]', ai_text or "")
            if not jm:
                print("重试仍失败,跳过此批")
                continue
        
        try:
            rewritten = json.loads(jm.group())
        except Exception as e:
            print(f"JSON解析异常: {e}")
            continue
        
        print(f"返回{len(rewritten)}条", end="")
        
        # 引擎校验
        rewritten = validate_batch(rewritten)
        
        # 写入
        for rw in rewritten:
            rid = str(rw.get("id"))
            for i, r in enumerate(rules):
                if str(r.get("id")) == rid:
                    rules[i] = rw
                    break
        save_rules(rules)
        total_done += len(rewritten)
        
        # 质量报告
        has_bad = False
        for s in quality_stats(rewritten):
            flag = ""
            if not s["english_keys"]: flag += " ⚠中文键名"; has_bad = True
            if s["layers"] < 2: flag += f" ⚠推理{s['layers']}层(不足)"
            if s["questions"] < 3: flag += f" ⚠追问{s['questions']}条(少)"
            if s["errors"]: flag += f" ⚠缺{s['errors']}"; has_bad = True
            status = "❌" if has_bad else "✅"
            print(f"\n  #{s['id']}: 推理{s['layers']}层 追问{s['questions']}条 正常解释{s['reasons']}种 核验:{'✓' if s['verified'] else '✗'}{flag}")
        
        print(f"  进度: {total_done}/{len(pending)} ({total_done*100//max(len(pending),1)}%)")
        sys.stdout.flush()
        
        if max_batches and batch_num >= max_batches:
            print(f"\n已达批次上限({max_batches})，暂停。下次可用 --resume 继续")
            break
    
    print(f"\n===== 完成: {total_done}条 =====")
    # 最终审计
    from engine.law_validity_checker import auto_process as ap2
    rules2 = json.load(open(RULES_PATH, encoding="utf-8"))
    st2 = ap2(rules2)
    json.dump(rules2, open(RULES_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"最终审计: 废止法替换{st2['replaced_repealed']}处, 核验{st2['auto_verified']}条")

if __name__ == "__main__":
    if not API_KEY:
        print("⛔ 未配置LLM API Key，请先在系统主页左上角配置。")
        sys.exit(1)
    main()
