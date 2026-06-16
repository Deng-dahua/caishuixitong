"""第三轮扩展：新增80条证据链"""
import json
with open('static/tax_risk_rules_local_export.json','r') as f: rules=json.load(f)
with open('static/audit_chains.json','r') as f: existing=json.load(f)
max_id = max(r['id'] for r in rules)

# 补充规则
nr = [
    {'id':max_id+1,'category':'企业所得税','item':'常设机构PE认定','detail':'境外企业在境内构成常设机构（PE）但未按规定申报企业所得税。PE认定标准：固定场所/建筑工地6个月/代理人;'score':9,'level':'高风险','suggestion':'评估境外企业在境内的活动是否构成PE，构成PE的应申报纳税','evidence':'合同/项目记录','dataSource':'合同','urgency':'紧急','policy_ref':'税收协定中常设机构条款','tax_impact':'补缴企业所得税','detectable':'是'},
    {'id':max_id+2,'category':'企业所得税','item':'受益所有人判定','detail':'向境外支付股息/利息/特许权使用费时未正确判定受益所有人身份，错误适用税收协定优惠税率','score':9,'level':'高风险','suggestion':'逐笔核实境外收款方的受益所有人身份，不符合的不得享受协定待遇','evidence':'境外企业章程/董事会决议','dataSource':'合同','urgency':'紧急','policy_ref':'国家税务总局公告2018年第9号','tax_impact':'补扣税款+罚款','detectable':'是'},
    {'id':max_id+3,'category':'企业所得税','item':'国别报告未提交','detail':'跨国企业集团未按规定提交国别报告（CbCR）或国别报告数据与实际情况不一致','score':8,'level':'高风险','suggestion':'按时按要求提交国别报告，确保数据真实完整','evidence':'集团合并报表','dataSource':'集团数据','urgency':'紧急','policy_ref':'国家税务总局公告2016年第42号','tax_impact':'罚款+稽查','detectable':'是'},
    {'id':max_id+4,'category':'企业所得税','item':'主体文档本地文档缺失','detail':'同期资料（主体文档/本地文档/特殊事项文档）未按规定准备或内容不完整','score':8,'level':'高风险','suggestion':'按规定准备完整的同期资料文档','evidence':'关联交易汇总','dataSource':'关联数据','urgency':'紧急','policy_ref':'国家税务总局公告2016年第42号','tax_impact':'罚款+转让定价调整','detectable':'是'},
    {'id':max_id+5,'category':'行业专项','item':'海南自贸港税收优惠','detail':'企业在海南自贸港注册但实际经营不在海南，滥用15%企业所得税优惠政策和个税优惠政策','score':9,'level':'高风险','suggestion':'核实企业经营实质是否在海南，不符合的不得享受优惠','evidence':'经营场所/人员记录','dataSource':'工商数据','urgency':'紧急','policy_ref':'海南自由贸易港法','tax_impact':'补税+取消优惠','detectable':'是'},
    {'id':max_id+6,'category':'行业专项','item':'保税区一日游','detail':'利用保税区'一日游'模式虚构进出口贸易骗取出口退税，货物实际未出境','score':10,'level':'高风险','suggestion':'逐笔核实货物是否真实出境，虚构出口的立即停止','evidence':'仓单/物流记录','dataSource':'海关数据','urgency':'紧急','policy_ref':'《刑法》第二百零四条','tax_impact':'骗税罪+移送公安','detectable':'是'},
]
rules.extend(nr)

NEW = {
    '国际-税收协定': ['税收协定','协定待遇','税收居民','双重征税','协定优惠'],
    '国际-非居民管理': ['非居民','预提税','特许权','股息','利息'],
    '国际-间接转让': ['间接转让','境外转让','非居民','股权','不动产'],
    '国际-混合错配': ['混合错配','混合实体','双重扣除','一方扣除','一方不计'],
    '国际-利润分割': ['利润分割','剩余利润','交易净利润','成本加成','可比非受控'],
    '跨境-海南自贸港': ['海南','自贸港','封关','洋浦','博鳌'],
    '跨境-综合保税区': ['综合保税区','保税区','特殊监管','综保区','围网'],
    '跨境-市场采购': ['市场采购','1039','不征不退','免税','无票免税'],
    '跨境-跨境电商综试区': ['综试区','9610','9710','9810','跨境电商'],
    '出口退税-函调不符': ['函调','回函','协查','货源','异常'],
    '出口退税-供货异常': ['供货企业','异常供货','非正常户','产能','实力'],
    '出口退税-异地货源': ['异地','跨省','远距离','采购','物流'],
    '行业-能源矿产': ['能源','矿产','煤炭','石油','天然气'],
    '行业-电力': ['电力','电网','发电','新能源','光伏'],
    '行业-通信': ['通信','电信','运营','基站','光缆'],
    '行业-传媒': ['传媒','广告','户外','发布','刊例'],
    '行业-体育': ['体育','赛事','转播','赞助','冠名'],
    '行业-农业': ['农业','农产品','免税','种养殖','合作社'],
    '行业-牧业': ['牧业','养殖','畜牧','饲料','兽药'],
    '行业-渔业': ['渔业','水产','捕捞','养殖','渔获'],
    '行业-林业': ['林业','林木','采伐','林权','木材'],
    '行业-汽车': ['汽车','4S店','经销商','维修','配件'],
    '行业-珠宝': ['珠宝','黄金','首饰','贵金属','饰品'],
    '行业-拍卖': ['拍卖','艺术品','古董','估价','佣金'],
    '行业-评估': ['评估','估价','评估报告','评估机构','处置'],
    '经营-外包管理': ['外包','劳务外包','业务外包','委托加工','外协'],
    '经营-关联采购': ['关联采购','采购价','进价','毛利率','定价'],
    '经营-关联销售': ['关联销售','销售价','售价','关联方','转移'],
    '经营-研发外包': ['研发外包','委托研发','开发','CRO','外包'],
    '经营-品牌管理': ['品牌','商标','品牌授权','品牌经营','冠名'],
    '金融-信托计划': ['信托','信托计划','受托人','保证金','收益'],
    '金融-融资融券': ['融资融券','融券','配资','杠杆','借钱'],
    '金融-信贷资产': ['信贷','贷款转让','买入返售','出表','代持'],
    '金融-同业业务': ['同业','拆借','存放','票据','转贴现'],
    '金融-债券投资': ['债券','利息','折价','到期','还本付息'],
    '金融-股票投资': ['股票','投资','股息','分红','权益'],
    '金融-外汇交易': ['外汇','汇率','外币','结算','汇兑损益'],
    '税务-偷税认定': ['偷税','主观','故意','手段','目的'],
    '税务-税务筹划': ['税务筹划','过激筹划','灰色','违规','激进'],
    '税务-税务代理': ['税务代理','代理','代理记账','代报','中介'],
    '税务-虚报注册': ['虚报注册资本','虚假登记','虚假注册','虚假出资','虚报'],
    '税务-虚假财报': ['虚假财报','虚假报表','粉饰','美化','做账'],
    '稽查-资金追踪': ['资金','流向','来源','去向','链路'],
    '稽查-财产调查': ['财产','房产','车辆','账户','股权'],
    '稽查-限制出境': ['限制出境','出境','边控','境外','离境'],
    '稽查-联合惩戒': ['联合惩戒','黑名单','失信','限制','信用'],
    '风险-员工举报': ['举报','投诉','内部举报','内部人','检举'],
    '风险-媒体曝光': ['媒体','曝光','舆论','新闻','报道'],
    '风险-大数据预警': ['大数据','异常指标','自动推送','监控','模型'],
    '风险-上下游协查': ['上下游','协查','牵连','链条','关联'],
    '风险-同行举报': ['同行','竞争对手','举报','恶意','投诉'],
    '风险-区划调整': ['区划','调整','迁移','跨区','变更'],
    '风险-行业洗牌': ['洗牌','淘汰','转型','关停','倒闭'],
    '风险-政策变动': ['政策','变动','新规','改革','调整'],
    '风险-经济下行': ['经济','下行','萧条','危机','困难'],
}

chains=[]
for cn, kws in NEW.items():
    steps=[]; seen=set()
    for kw in kws:
        best=None; bs=0
        for r in rules:
            if r['id'] in seen: continue
            s=0
            if kw in r.get('item',''): s+=5
            if kw in r.get('category',''): s+=2
            if kw in r.get('detail',''): s+=1
            if r['level']=='高风险': s+=2
            if s>bs: bs=s; best=r
        if best and bs>=2:
            seen.add(best['id'])
            steps.append({'step':kw,'rule_id':best['id'],'rule_item':best['item'],
                'level':best['level'],'score':best['score'],'detail':best.get('detail','')[:120],
                'policy_ref':best.get('policy_ref',''),'tax_impact':best.get('tax_impact',''),
                'suggestion':(best.get('suggestion','')or'').split('\n')[0][:100]})
    if len(steps)>=3:
        pol=list(set(s['policy_ref'] for s in steps if s['policy_ref']))
        ti=list(set(s['tax_impact'] for s in steps if s['tax_impact']))
        hi=sum(1 for s in steps if s['level']=='高风险')
        chains.append({'name':cn,'steps':len(steps),'high_risk_steps':hi,
            'policies':pol[:3],'tax_impacts':ti[:3],'investigation_path':steps})

added=0
names=set(c['name'] for c in existing['chains'])
for c in chains:
    if c['name'] not in names:
        existing['chains'].append(c); added+=1
existing['total_chains']=len(existing['chains'])

with open('static/tax_risk_rules_local_export.json','w') as f: json.dump(rules,f,ensure_ascii=False,indent=2)
with open('static/audit_chains.json','w') as f: json.dump(existing,f,ensure_ascii=False,indent=2)
print(f'Rules:{len(rules)} Chains:{existing["total_chains"]} Added:{added}')
