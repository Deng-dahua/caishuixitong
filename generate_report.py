"""
生成稽查报告 HTML — 全面运用分析链㉔条标准
"""
import json, os
from datetime import datetime

with open(os.path.join(os.path.dirname(__file__), 'report_data.json'), 'r', encoding='utf-8') as f:
    data = json.load(f)

high_list = data['high_list']
mid_list = data['mid_list']
low_list = data['low_list']

def esc(s):
    if not s: return ''
    return str(s).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

def render_items(items):
    """渲染明细表格——全部数据，不截断"""
    if not items or not isinstance(items, list) or len(items) == 0:
        return ''
    h = '<div style="margin:8px 0"><div style="font-weight:600;font-size:12px;color:#475569;margin-bottom:4px">明细数据</div>'
    h += '<table class="tbl2"><thead><tr>'
    for k in items[0].keys():
        h += f'<th>{esc(k)}</th>'
    h += '</tr></thead><tbody>'
    for item in items:
        h += '<tr>'
        for v in item.values():
            h += f'<td>{esc(str(v))}</td>'
        h += '</tr>'
    h += '</tbody></table></div>'
    return h

def render_finding(f, level, is_high=False):
    """渲染单条发现"""
    ftype = f.get('type', '')
    detail = f.get('detail', '')
    desc = f.get('description', '')
    tax_impact = f.get('tax_impact', '')
    policy = f.get('policy_ref', '')
    suggestion = f.get('suggestion', '')
    items = f.get('items', [])
    score = f.get('score', 0)
    rule_id = f.get('rule_id', '')
    
    if level == '高风险':
        cls = ''; tag_cls = 'tag-r'; tag_text = f'高风险 {score}分'
    elif level == '中风险':
        cls = 'amber'; tag_cls = 'tag-a'; tag_text = '中风险'
    else:
        cls = 'green'; tag_cls = 'tag-g'; tag_text = '低风险'
    
    # 稽查重点标记
    audit_priority = f.get('level_fixed', False)
    
    h = f'<div class="finding {cls}"><div class="ft">'
    h += f'<span class="tag {tag_cls}">{tag_text}</span> '
    if audit_priority:
        h += '<span class="tag tag-r" style="font-size:10px">稽查重点</span> '
    h += f'{esc(ftype)}'
    if rule_id:
        h += f' <span style="font-size:11px;color:#94a3b8">[规则ID:{rule_id}]</span>'
    h += '</div>'
    
    if detail:
        h += f'<p style="font-weight:600;color:#0f172a">{esc(detail)}</p>'
    
    if desc:
        for para in desc.split('\n'):
            para = para.strip()
            if para:
                h += f'<div class="fb">{esc(para)}</div>'
    
    if tax_impact:
        h += f'<div class="fb"><strong>纳税影响：</strong>{esc(tax_impact)}</div>'
    
    if policy:
        h += f'<div class="fs"><strong>法律依据：</strong>{esc(policy)}</div>'
    
    if suggestion:
        h += f'<div class="fs"><strong>稽查建议：</strong>{esc(suggestion)}</div>'
    
    # 明细表格——全部数据，不截断
    h += render_items(items)
    
    h += '</div>'
    return h

# ═══════ 构建报告 ═══════

html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>税务稽查报告 — 达冠纺织</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"PingFang SC","Microsoft YaHei",serif;font-size:15px;line-height:2;color:#1a1a2e;background:#f8f9fa}
.report{max-width:860px;margin:0 auto;padding:60px 50px;background:#fff}
.cover{text-align:center;padding:60px 0 40px;border-bottom:3px double #1a1a2e;margin-bottom:40px}
.cover h1{font-size:28px;font-weight:900;letter-spacing:6px;margin-bottom:16px}
.cover .sub{font-size:14px;color:#555;line-height:2.5}
h2{font-size:20px;font-weight:700;margin:40px 0 20px;padding:10px 16px;background:#f0f4f8;border-left:4px solid #c92a2a;letter-spacing:2px}
h3{font-size:16px;font-weight:600;margin:24px 0 12px;color:#c92a2a}
p{margin:10px 0;text-align:justify}
p.i2{text-indent:2em}
.tbl{width:100%;border-collapse:collapse;margin:16px 0;font-size:13px}
.tbl td{padding:8px 12px;border-bottom:1px solid #e8e8e8}
.tbl .lbl{width:120px;font-weight:600;color:#5c6370;background:#fafafa}
.tbl2{width:100%;border-collapse:collapse;margin:12px 0;font-size:13px}
.tbl2 th{background:#f0f4f8;padding:8px 12px;text-align:left;font-weight:600;border-bottom:2px solid #c92a2a}
.tbl2 td{padding:8px 12px;border-bottom:1px solid #eee}
.tbl2 .r{text-align:right}
.tag{display:inline-block;padding:2px 10px;border-radius:4px;font-size:12px;font-weight:600;margin-right:4px}
.tag-r{background:#fee2e2;color:#991b1b}
.tag-a{background:#fef3c7;color:#92400e}
.tag-g{background:#dcfce7;color:#166534}
.finding{margin:16px 0;padding:16px 20px;border:1px solid #e0e0e0;border-left:4px solid #c92a2a;border-radius:6px;background:#fff}
.finding .ft{font-weight:700;font-size:15px;margin-bottom:8px}
.finding .fb{font-size:13px;color:#334155;line-height:1.8}
.finding .fs{font-size:12px;color:#64748b;margin-top:8px;padding-top:8px;border-top:1px dashed #e8e8e8}
.finding.amber{border-left-color:#e67700}
.finding.green{border-left-color:#2b8a3e}
.stat-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:20px 0}
.stat-card{text-align:center;padding:20px 16px;background:#f8f9fa;border-radius:8px}
.stat-card .num{font-size:32px;font-weight:700;color:#c92a2a}
.stat-card .lbl{font-size:13px;color:#64748b;margin-top:4px}
.seal{text-align:right;margin-top:60px;padding-top:30px;border-top:2px solid #1a1a2e}
.warn{background:#fff8e1;border-left:4px solid #e67700;padding:12px 16px;margin:12px 0;font-size:13px;line-height:1.8}
.info{background:#e8f5e9;border-left:4px solid #2b8a3e;padding:12px 16px;margin:12px 0;font-size:13px}
.meth-item{padding:8px 0;border-bottom:1px solid #f1f5f9;font-size:12px;color:#64748b}
.meth-item .mnum{display:inline-block;width:22px;height:22px;line-height:22px;text-align:center;border-radius:50%;background:#c92a2a;color:#fff;font-size:11px;margin-right:6px;vertical-align:middle}
</style>
</head>
<body>
<div class="report">
<div class="cover">
<h1>税 务 稽 查 报 告</h1>
<div class="sub">
编号：税稽字[2026]第''' + str(data['total_risks']) + '''号<br>
被查单位：中山市达冠纺织有限公司<br>
稽查期间：2023年6月 — 2026年9月<br>
报告日期：''' + datetime.now().strftime('%Y年%m月%d日') + '''<br>
资料数量：银行流水13份 + 进项发票5份 + 销项发票5份 = 共''' + str(data['files_count']) + '''份
</div>
</div>

<h2>稽查引擎执行标准</h2>
<p style="font-size:13px;color:#64748b;line-height:2">
本报告依托分析链㉔条稽查方法论，全量规则引擎+线索链+证据链+跨域推理+方法论过滤+建议增强。
</p>
<div style="padding:12px 16px;background:#fafafa;border-radius:6px;font-size:12px;line-height:2">
<div class="meth-item"><span class="mnum">①</span>多格式兼容 <span style="margin:0 8px">②</span>汇总行过滤 <span style="margin:0 8px">③</span>付款方身份核实 <span style="margin:0 8px">④</span>关键词≠事实 <span style="margin:0 8px">⑤</span>行业认知补算法</div>
<div class="meth-item"><span class="mnum">⑥</span>联网核查 ✅ <span style="margin:0 8px">⑦</span>明细即信服力 <span style="margin:0 8px">⑧</span>不墨迹直接干 <span style="margin:0 8px">⑨</span>合同分层判断 <span style="margin:0 8px">⑩</span>完备度明细</div>
<div class="meth-item"><span class="mnum">⑪</span>完备度升级 <span style="margin:0 8px">⑫</span>凭证描述纠正 <span style="margin:0 8px">⑬</span>进销诊断升级 <span style="margin:0 8px">⑭</span>行业基准库 <span style="margin:0 8px">⑮</span>结论分析法</div>
<div class="meth-item"><span class="mnum">⑯</span>COND_BAN防误杀 <span style="margin:0 8px">⑰</span>稽查重点强制等级 <span style="margin:0 8px">⑱</span>报告纯净度 <span style="margin:0 8px">⑲</span>发票≠收付款1:1 <span style="margin:0 8px">⑳</span>经营实质地理分析</div>
<div class="meth-item"><span class="mnum">㉑</span>规则detail业务化 <span style="margin:0 8px">㉒</span>建议质量增强 <span style="margin:0 8px">㉓</span>四步稽查分析法 <span style="margin:0 8px">㉔</span>禁止数据截断</div>
<div class="meth-item"><span class="mnum">㉕</span>三层行业穿透法 <span style="margin:0 8px;color:#c92a2a">NEW</span></div>
<div class="meth-item"><span class="mnum">㉖</span>经营实质点面推理法 <span style="margin:0 8px;color:#c92a2a">NEW</span></div>
</div>

'''

# ═══════ 企业工商信息（联网核查） ═══════
entity = data.get('target_entity', {})
online_lookup = entity.get('_online_lookup', False)
legal_rep = entity.get('legal_representative', '')
reg_capital = entity.get('registered_capital', '')
est_date = entity.get('established_date', '')
address_ = entity.get('address', '')
biz_scope = entity.get('business_scope', '')
company_type = entity.get('company_type', '')
company_status = entity.get('company_status', '')
lookup_source = entity.get('lookup_source', '')
shareholders = entity.get('shareholders', [])

if legal_rep or reg_capital:
    html += '''
<h2>企业工商信息（联网核查）</h2>
<p style="font-size:13px;color:#64748b;margin-bottom:12px">
数据来源：''' + esc(lookup_source or '联网查询') + ''' | 核查时间：''' + datetime.now().strftime('%Y-%m-%d %H:%M') + '''
</p>
<table class="tbl">
<tr><td class="lbl">企业名称</td><td>''' + esc(entity.get('name', '')) + '''</td></tr>
<tr><td class="lbl">法定代表人</td><td style="font-weight:600">''' + esc(legal_rep) + '''</td></tr>
<tr><td class="lbl">注册资本</td><td>''' + esc(reg_capital) + '''</td></tr>
<tr><td class="lbl">成立日期</td><td>''' + esc(est_date) + '''</td></tr>
<tr><td class="lbl">企业类型</td><td>''' + esc(company_type) + '''</td></tr>
<tr><td class="lbl">经营状态</td><td>''' + esc(company_status) + '''</td></tr>
<tr><td class="lbl">注册地址</td><td>''' + esc(address_) + '''</td></tr>
<tr><td class="lbl">经营范围</td><td style="font-size:12px">''' + esc(biz_scope) + '''</td></tr>
<tr><td class="lbl">统一社会信用代码</td><td>''' + esc(entity.get('uscc', '')) + '''</td></tr>
<tr><td class="lbl">行业分类</td><td style="font-weight:600">发票推断：''' + esc(entity.get('industry', '')) + ''' | 联网核查：''' + esc(entity.get('industry_online', '')) + '''</td></tr>'''
    if shareholders:
        html += '<tr><td class="lbl">股东信息</td><td>'
        for i, sh in enumerate(shareholders):
            if i > 0:
                html += '；'
            html += esc(sh.get('name', '')) + '(' + esc(str(sh.get('ratio', ''))) + ')'
        html += '</td></tr>'
    html += '''
</table>
'''

html += '''
<h2>一、稽查概况</h2>

<div class="stat-grid">
<div class="stat-card"><div class="num">''' + str(data['total_risks']) + '''</div><div class="lbl">风险发现总数</div></div>
<div class="stat-card"><div class="num" style="color:#991b1b">''' + str(data['high_risk']) + '''</div><div class="lbl">高风险</div></div>
<div class="stat-card"><div class="num" style="color:#92400e">''' + str(data['mid_risk']) + '''</div><div class="lbl">中风险</div></div>
<div class="stat-card"><div class="num" style="color:#166534">''' + str(data['low_risk']) + '''</div><div class="lbl">低风险</div></div>
</div>

<div class="warn">
<strong>⚠️ 资料完备度严重不足：</strong>本次稽查共收到''' + str(data['files_count']) + '''份资料（银行流水13份、进项发票5份、销项发票5份），覆盖银行流水、进项发票、销项发票3类。缺失记账凭证、工资表、社保明细、进销存台账、合同文件、科目余额表、财务报表、各类申报表等11类稽查必查资料。
</div>

<h2>二、高风险发现（''' + str(data['high_risk']) + '''项）</h2>
'''

for f in high_list:
    html += render_finding(f, '高风险', is_high=True)

html += '<h2>三、中风险发现（' + str(data['mid_risk']) + '项）</h2>'
for f in mid_list:
    html += render_finding(f, '中风险')

html += '<h2>四、低风险发现（' + str(data['low_risk']) + '项）</h2>'
for f in low_list:
    html += render_finding(f, '低风险')

html += '''
<h2>五、综合结论与稽查建议</h2>

<p class="i2">经对被查单位「中山市达冠纺织有限公司」2023年6月至2026年9月期间的''' + str(data['files_count']) + '''份资料进行系统性稽查分析，形成结论如下：</p>

<h3>（一）已查实问题</h3>

<p class="i2">1. <strong>资料完备度极低</strong>——仅提交3类资料，缺失11类稽查必查资料。根据《税收征收管理法》第五十四条、第五十六条，税务机关有权要求纳税人提供完整的涉税资料。</p>

<p class="i2">2. <strong>进项发票与银行付款记录存在未匹配</strong>——部分进项发票供应商在银行付款记录中找不到对应付款。但需注意：发票与付款天然不是一一对应关系——存在自然跨期、合并付款、分期付款、预付账款、应付账款、非对公/代付等六种正常商业场景，未匹配不等于虚开。</p>

<p class="i2">3. <strong>收款来源与开票客户不匹配</strong>——银行收款方中含有非开票客户的资金流入，需逐笔核实资金来源性质。</p>

<p class="i2">4. <strong>进销品名存在显著差异</strong>——进项以棉纱/涤纶布等原材料为主，销项以针织布/梭织布等成品为主，表明存在实质加工环节。</p>

<h3>（二）需进一步核实事项</h3>

<p class="i2">1. 要求被查单位补充提供：记账凭证、工资表、社保明细、进销存台账、合同文件、科目余额表、财务报表、各类申报表等11类资料。</p>

<p class="i2">2. 对进项发票与银行付款未匹配的供应商，逐笔核实属于六种付款模式中的哪一种，并提供对应佐证材料。</p>

<p class="i2">3. 对银行收款中非开票客户的资金来源，逐笔标注性质并提供合同或凭证。</p>

<p class="i2">4. 核实加工链条真实性和加工费发票合规性。</p>

<h3>（三）稽查建议</h3>

<p class="i2">鉴于达冠纺织仅提供了3类核心资料且已暴露多项高风险发现，建议：</p>

<p class="i2"><strong>1. 限期整改（15个工作日）：</strong>补充全部缺失的11类资料，逐笔说明进项发票付款和银行收款的匹配情况。</p>

<p class="i2"><strong>2. 重点核查：</strong>（1）银行收款中个人账户的资金性质——法定代表人/股东打款可能为注资或关联方往来；（2）进项发票供应商与银行付款方的匹配度——重点关注无付款记录的大额供应商。</p>

<p class="i2"><strong>3. 风险提示：</strong>如在限期内未能提供完整资料或对异常事项做出合理解释，将面临核定征收、虚开发票专项核查、纳税信用等级降级等后果。</p>

<div class="seal">
<p>稽查员（签名）：_______________</p>
<p>日期：''' + datetime.now().strftime('%Y年%m月%d日') + '''</p>
</div>

</div>
</body>
</html>
'''

output_path = os.path.join(os.path.dirname(__file__), '稽查报告_达冠纺织_20260619.html')
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(html)

print(f"报告已生成: {output_path}")
print(f"长度: {len(html):,} 字符")
print(f"高风险 {len(high_list)} 项, 中风险 {len(mid_list)} 项, 低风险 {len(low_list)} 项")
