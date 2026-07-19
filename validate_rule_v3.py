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

# ═══ ④⑤ 重罪等级下限（刑事犯罪级行为禁止标低于高风险）═══
FELONY_KW = ['骗税', '骗取出口退税', '假报出口', '伪造发票', '伪造增值税', '虚开发票', '虚开增值税',
             '暴力虚开', '两套账', '账外经营', '隐匿销毁账簿', '销毁账簿', '阴阳合同', '骗取退税',
             '骗取留抵', '骗取即征即退', '过票', '变名开票', '洗钱']
_item_txt = str(rule.get('item',''))
# ═══ 铁律0·数据矛盾唯一来源：疑点必须写得出数据矛盾特征 ═══
_contra_txt = _item_txt + str(rule.get("phenomena","") or "") + str(rule.get("threshold","") or "") + str(rule.get("detail","") or "")
check("item", bool(re.search(r"不一致|不匹配|不相符|不符|不等|偏差|偏离|差额|差异|背离|倒挂|矛盾|无|未|缺|没有|不足|超过|超出|高于|低于|大于|小于|异常|突然|激增|骤|回流|闭环|连号|顶额|对比|比对|勾稽|印证|>|<|≥|≤|≠|vs", _contra_txt)),
      "疑点必须是数据矛盾（应该相等的不等/应该有的没有/不应该这样的却这样）——名称与内容均无矛盾特征，写不出X vs Y哪里对不上的条目不是疑点")

# ═══ 疑点vs知识边界：知识型措辞禁止作为疑点 ═══
if re.search(r"(立案标准|的认定|认定与处理|的区分|实质区分|的边界|的界定|规则适用|政策衔接|政策延续|准则下|税务处理$|税收处理$)", _item_txt):
    check('item', False, '知识型条目（定性标准/税务处理/政策适用）禁止入疑点库——应存static/audit_knowledge.json稽查知识库')

# ═══ 全行业适用铁律：通病疑点禁止行业限定 ═══
_disease_kw = ('毛利为负','毛利率','购销倒挂','进销倒挂','缺少银行流水','有进无销','零申报','税负率偏低','税负偏低','隐匿收入','两套账','资料不完备')
_ind_kw = ('饲料','设计服务','广告服务','信息技术服务','现代服务','纺织','服装','商贸','批发','零售','餐饮','住宿','酒店','电商','直播')
if any(d in _item_txt for d in _disease_kw) and any(i in _item_txt for i in _ind_kw):
    check('item', False, '通病疑点禁止行业限定——全行业通病由通用条目覆盖，行业差异写入threshold行业调整')

_hit_felony = [kw for kw in FELONY_KW if kw in _item_txt]
if _hit_felony:
    _lv = str(rule.get('level',''))
    check('level', '极高' in _lv or '高' in _lv,
          f'重罪级疑点({"/".join(_hit_felony)})禁止标为{_lv or "空"}——刑事犯罪级行为最低为高风险(评分锚点8-10分档)')
    try:
        _sc = float(rule.get('score', 0))
    except Exception:
        _sc = 0
    check('score', _sc >= 8, f'重罪级疑点评分{_sc}过低——按锚点主观故意/可移送公安=8-10分')

# ═══ ④⑤ level与score锚点一致性（自动发现规则豁免：level=信息 为待确认状态）═══
_is_auto = rule.get('type') == 'auto_signal' or rule.get('source') == '系统发现' or bool(rule.get('auto_type'))
try:
    _sc2 = float(rule.get('score', 0))
    _lv2 = str(rule.get('level',''))
    if _is_auto:
        pass
    elif _sc2 >= 8:
        check('level', '极高' in _lv2 or '高' in _lv2, f'score={_sc2}属8-10分档(高度疑似/系统性造假)，level不得为{_lv2}')
    elif _sc2 >= 6:
        check('level', '中' in _lv2 or '高' in _lv2, f'score={_sc2}属6-7分档(中等风险)，level不得为{_lv2}')
except Exception:
    pass

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
# 有量化阈值的规则必须写"阈值以下处理"
if re.search(r'\d+万|\d+%|≥|>|\d+天|\d+元', str(rule.get('threshold',''))):
    check('determination', '阈值以下' in det, '有量化阈值但缺少"阈值以下处理"分支')

# ═══ ⑱ risk_table 风险表格 ═══
rt = str(rule.get('risk_table',''))
check('risk_table', '核心' in rt, '缺少"核心"影响标注')
# 附加税费影响程度：必然联动=次要，禁止标间接（执行指引防错#8）
if '附加税' in rt:
    _m_fj = re.search(r'附加税[费]?[^|]{0,40}间接', rt)
    check('risk_table', not _m_fj, '附加税费标注为间接——附加税费随增值税必然联动，必须标次要')
# 证据首层命名贴合（执行指引防错#7）：无实物流转维度的疑点禁套货物流
_no_goods_mon = ('申报流监控', '账表质量与勾稽', '社保与个税交叉', '税务合规与程序')
_ev_head = str(rule.get('evidence',''))[:40]
if str(rule.get('monitor_category','')) in _no_goods_mon and '货物流' in _ev_head:
    check('evidence', False, '证据首层套用货物流——本疑点无实物流转，应按第一层命名指引取贴合名称')
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
