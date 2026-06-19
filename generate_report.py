"""
生成稽查报告 HTML — 以稽查员身份出具
"""
import json, os

with open(os.path.join(os.path.dirname(__file__), 'report_data.json'), 'r', encoding='utf-8') as f:
    data = json.load(f)

high_list = data['high_list']
mid_list = data['mid_list']
low_list = data['low_list']

def esc(s):
    if not s: return ''
    return str(s).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

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
报告日期：2026年6月19日<br>
资料数量：银行流水13份 + 进项发票5份 + 销项发票5份 = 共23份
</div>
</div>

<h2>一、稽查概况</h2>

<div class="stat-grid">
<div class="stat-card"><div class="num">''' + str(data['total_risks']) + '''</div><div class="lbl">风险发现总数</div></div>
<div class="stat-card"><div class="num" style="color:#991b1b">''' + str(data['high_risk']) + '''</div><div class="lbl">高风险</div></div>
<div class="stat-card"><div class="num" style="color:#92400e">''' + str(data['mid_risk']) + '''</div><div class="lbl">中风险</div></div>
<div class="stat-card"><div class="num" style="color:#166534">''' + str(data['low_risk']) + '''</div><div class="lbl">低风险</div></div>
</div>

<div class="warn">
<strong>⚠️ 资料完备度严重不足：</strong>本次稽查共收到23份资料（银行流水13份、进项发票5份、销项发票5份），覆盖银行流水、进项发票、销项发票3类。缺失记账凭证、工资表、社保明细、进销存台账、合同文件、科目余额表、财务报表、各类申报表等11类稽查必查资料。核查结论仅基于已提供资料推断，不排除因资料缺失存在更多未暴露风险。
</div>

<h2>二、高风险发现（''' + str(data['high_risk']) + '''项）</h2>
'''

for i, f in enumerate(high_list):
    ftype = f.get('type', '')
    detail = f.get('detail', '')
    desc = f.get('description', '')
    tax_impact = f.get('tax_impact', '')
    policy = f.get('policy_ref', '')
    suggestion = f.get('suggestion', '')
    items = f.get('items', [])
    score = f.get('score', 0)
    
    html += f'<div class="finding"><div class="ft"><span class="tag tag-r">高风险 {score}分</span> {esc(ftype)}</div>'
    
    if detail:
        html += f'<p style="font-weight:600;color:#0f172a">{esc(detail)}</p>'
    
    if desc:
        # 保留换行
        for para in desc.split('\n'):
            para = para.strip()
            if para:
                html += f'<div class="fb">{esc(para)}</div>'
    
    if tax_impact:
        html += f'<div class="fb"><strong>纳税影响：</strong>{esc(tax_impact)}</div>'
    
    if policy:
        html += f'<div class="fs"><strong>法律依据：</strong>{esc(policy)}</div>'
    
    if suggestion:
        html += f'<div class="fs"><strong>稽查建议：</strong>{esc(suggestion)}</div>'
    
    if items and isinstance(items, list) and len(items) > 0:
        html += '<table class="tbl2" style="margin-top:8px"><tr>'
        for k in items[0].keys():
            html += f'<th>{esc(k)}</th>'
        html += '</tr>'
        for item in items:
            html += '<tr>'
            for v in item.values():
                html += f'<td>{esc(str(v))}</td>'
            html += '</tr>'
        html += '</table>'
    
    html += '</div>'

html += '<h2>三、中风险发现（' + str(data['mid_risk']) + '项）</h2>'

for i, f in enumerate(mid_list):
    ftype = f.get('type', '')
    detail = f.get('detail', '')
    desc = f.get('description', '')
    suggestion = f.get('suggestion', '')
    
    html += f'<div class="finding amber"><div class="ft"><span class="tag tag-a">中风险</span> {esc(ftype)}</div>'
    if detail:
        html += f'<p style="font-weight:600">{esc(detail)}</p>'
    if desc:
        for para in desc.split('\n'):
            para = para.strip()
            if para:
                html += f'<div class="fb">{esc(para)}</div>'
    if suggestion:
        html += f'<div class="fs"><strong>建议：</strong>{esc(suggestion)}</div>'
    html += '</div>'

html += '<h2>四、低风险发现（' + str(data['low_risk']) + '项）</h2>'
for f in low_list:
    html += f'<div class="finding green"><div class="ft"><span class="tag tag-g">低风险</span> {esc(f.get("type", ""))}</div>'
    if f.get('detail'): html += f'<p>{esc(f["detail"])}</p>'
    html += '</div>'

html += '''
<h2>五、综合结论与稽查建议</h2>

<p class="i2">经对被查单位「中山市达冠纺织有限公司」2023年6月至2026年9月期间的23份资料（银行流水13份、进项发票5份、销项发票5份）进行系统性稽查分析，形成结论如下：</p>

<h3>（一）已查实问题</h3>

<p class="i2">1. <strong>资料完备度极低</strong>——仅提交3类资料，缺失11类稽查必查资料。根据《税收征收管理法》第五十四条、第五十六条，税务机关有权要求纳税人提供完整的涉税资料。缺失资料将使企业面临罚款（单位最高5万元）及核定征收风险。</p>

<p class="i2">2. <strong>进项发票与银行付款记录存在大量未匹配</strong>——大量进项发票供应商在银行付款记录中找不到对应付款，涉及金额巨大。根据《发票管理办法》第二十二条及《刑法》第二百零五条，需要逐笔核实是否存在虚开发票情形。但需注意：发票与付款天然不是一一对应关系，未匹配不等于虚开——存在自然跨期、合并付款、分期付款、预付账款、应付账款、非对公/代付等六种正常商业场景。</p>

<p class="i2">3. <strong>收款来源与开票客户不匹配</strong>——银行收款方中含有非开票客户的资金流入，需要逐笔核实资金来源性质（经营收款/借款/注资/往来款），无法说明来源的按隐匿收入处理。</p>

<p class="i2">4. <strong>进销品名存在显著差异</strong>——进项以棉纱、涤纶布等原材料为主，销项以针织布、梭织布等成品为主，表明存在实质加工环节。需要核实加工链条的真实性和加工费发票的合规性。</p>

<h3>（二）需进一步核实事项</h3>

<p class="i2">1. 要求被查单位补充提供：记账凭证（完整序时账）、工资表、社保明细、进销存台账、合同文件、科目余额表、资产负债表+利润表、增值税申报表、企业所得税申报表、个人所得税申报表、其他税种申报表等11类资料。</p>

<p class="i2">2. 对进项发票与银行付款未匹配的供应商，逐笔核实属于六种付款模式中的哪一种，并提供对应的佐证材料。</p>

<p class="i2">3. 对银行收款中非开票客户的资金来源，逐笔标注性质（经营/借款/注资/关联方往来），并提供对应的合同或凭证。</p>

<p class="i2">4. 核实加工费真实性和加工链条完整性，确认是否存在虚开加工费发票或利用加工费转移利润的情形。</p>

<h3>（三）稽查建议</h3>

<p class="i2">鉴于达冠纺织仅提供了3类核心资料且已暴露多项高风险发现，建议：</p>

<p class="i2"><strong>1. 限期整改（15个工作日）：</strong>补充全部缺失的11类资料，逐笔说明进项发票付款和银行收款的匹配情况。</p>

<p class="i2"><strong>2. 重点核查：</strong>（1）银行收款中范善茂等个人账户的资金性质——根据工商登记查询，范善茂为法定代表人，其个人打款可能为股东注资或关联方往来；（2）进项发票中供应商名称与银行付款方名称的匹配度——重点关注无任何付款记录的大额供应商。</p>

<p class="i2"><strong>3. 风险提示：</strong>如在限期内未能提供完整资料或对异常事项做出合理解释，将面临：（1）核定征收——税务机关根据银行流水等已有数据倒推核定应纳税额；（2）虚开发票专项核查——移送稽查部门；（3）纳税信用等级降级——影响发票领用、出口退税等。</p>

<div class="seal">
<p>稽查员（签名）：_______________</p>
<p>日期：2026年6月19日</p>
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
