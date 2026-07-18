# ===== v3标准自检脚本 — 精写规则提交前必跑 =====
# 用法：python validate_rule_v3.py N
# 检查规则 #N 是否达到 v3 精写编制标准 + 精写编制说明要求
import json, sys, re

rules = json.load(open('static/tax_risk_rules_local_export.json', encoding='utf-8'))
rid = sys.argv[1] if len(sys.argv) > 1 else '1'
rule = [r for r in rules if str(r.get('id')) == rid]
if not rule:
    print(f'规则 #{rid} 不存在'); sys.exit(1)
rule = rule[0]

errors = []

def check(field, condition, message):
    if not condition:
        errors.append(f'❌ [{field}] {message}')
    else:
        print(f'  ✅ [{field}] 通过')

# ═══ 基础字段 ①-⑨ ═══
for f in ['id','item','category','level','score','check_frequency','policy_ref','tax_impact','applicable_condition']:
    check(f, bool(str(rule.get(f,'')).strip()), f'字段不能为空')

# ═══ ⑫ direction 推理链 ═══
d = str(rule.get('direction',''))
check('direction', '推理第' in d or '推理第一层' in d, '缺少推理层标注格式')
check('direction', '依赖证据' in d, '每层缺少"依赖证据"标注')
check('direction', '复杂度' in d, '缺少"复杂度：复杂/中等/简单"标记')

# ═══ ⑬ drill_questions 穿透追问 ═══
dq = str(rule.get('drill_questions',''))
# 验证分组顺序
facts_pos = dq.find('事实层')
evid_pos = dq.find('证据层')
logic_pos = dq.find('逻辑层')
if facts_pos >= 0 and evid_pos >= 0 and logic_pos >= 0:
    order_ok = facts_pos < evid_pos < logic_pos
    check('drill_questions', order_ok, '分组顺序必须是 事实→证据→逻辑')
else:
    check('drill_questions', False, '缺少三组递进标题（事实层/证据层/逻辑层）')
# Q&A格式
q_count = len(re.findall(r'Q\d+[：:]', dq))
check('drill_questions', q_count >= 3, f'追问至少3条（当前{q_count}条）')
check('drill_questions', '→潜台词' in dq or '→潜台词:' in dq, '缺少"→潜台词"格式')
check('drill_questions', 'A：' in dq or 'A:' in dq, '缺少"A：应对话术"格式')

# ═══ ⑮ focus 稽查重点 ═══
focus = str(rule.get('focus',''))
check('focus', '①' in focus, '稽查重点须用①②③④逐条标注')

# ═══ ⑯ normal_reason ═══
nr = str(rule.get('normal_reason',''))
reason_count = len(re.findall(r'——需提供', nr))
check('normal_reason', reason_count >= 4, f'至少4种正常解释（当前{reason_count}种）')
check('normal_reason', '最常见解释' in nr or '穷举' in nr, '缺少"最常见解释"标注或"穷举说明"')

# ═══ ⑰ determination 定性路径 ═══
det = str(rule.get('determination',''))
check('determination', '线索' in det, '缺少路径一（线索等级）')
check('determination', '强证据' in det, '缺少路径二（强证据）')
check('determination', '铁证' in det, '缺少路径三（铁证）')
check('determination', '应对总原则' in det, '缺少"应对总原则"')

# ═══ ⑱ risk_table 风险表格 ═══
rt = str(rule.get('risk_table',''))
check('risk_table', '核心' in rt, '缺少"核心"影响标注')
check('risk_table', '次要' in rt or '核心' in rt, '缺少影响程度标注')

# ═══ ⑲ evidence 证据清单 ═══
ev = str(rule.get('evidence',''))
check('evidence', '必须' in ev, '缺少"必须获取"优先级')
check('evidence', '应当' in ev, '缺少"应当获取"优先级')
check('evidence', '可以' in ev, '缺少"可以获取"优先级')
check('evidence', '金额分级' in ev or '大额' in ev or '>10万' in ev, '缺少金额分级标准')

# ═══ ㉑ threshold 触发指标 ═══
th = str(rule.get('threshold',''))
check('threshold', '行业' in th, '缺少行业差异阈值')
check('threshold', '前置条件' in th, '缺少前置条件四维度')
check('threshold', '触发' in th, '缺少触发方式说明')

# ═══ ㉒ suggestion 稽查处理 ═══
sg = str(rule.get('suggestion',''))
check('suggestion', '定性' in sg, '缺少"定性"')
check('suggestion', '补税' in sg, '缺少"补税"')

# ═══ ㉓ remedy 整改建议 ═══
rm = str(rule.get('remedy',''))
check('remedy', '自查' in rm or '应对' in rm or '制度' in rm, '缺少三阶段（自查/应对/制度）')

print(f'\n===== 结果: {len(errors)} 个问题 =====')
if errors:
    for e in errors: print(' ', e)
    sys.exit(1)
else:
    print('  全部通过 ✅')
