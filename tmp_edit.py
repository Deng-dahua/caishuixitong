import re

with open('static/js/tax-doc-analysis.js', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Score decomposition in AGI block
old = "var auditSummary = '综合等级' + (audit.grade||'?') + '级，总分' + (audit.overall_score||0) + '，严重问题' + (audit.critical_count||0) + '个，警告' + (audit.warning_count||0) + '个';"
new = "          var auditSummary = '综合等级' + (audit.grade||'?') + '级，总分' + (audit.overall_score||0) + '，严重' + (audit.critical_count||0) + '项、警告' + (audit.warning_count||0) + '项';\n          var dims = audit.dimensions || {};\n          var dimParts = [];\n          for (var dk in dims) { if (dims.hasOwnProperty(dk)) { var ds = dims[dk]; dimParts.push(dk + ' ' + Math.round((ds.score||0)*100) + '%'); } }\n          var dimNote = dimParts.length > 0 ? '（评分构成：' + dimParts.join('，') + '）' : '';"
content = content.replace(old, new)

# Update the display line  
old2 = "smartHtml += '<span style=\"flex:1;min-width:0\"><p class=\"i2\" style=\"margin:0\"><strong>🔍 AGI自审报告：</strong>' + auditSummary + '</p></span>';"
new2 = "smartHtml += '<span style=\"flex:1;min-width:0\"><p class=\"i2\" style=\"margin:0\"><strong>🔍 AGI报告质量自审：</strong>' + auditSummary + '</p>' + (dimNote ? '<p class=\"i2\" style=\"margin:4px 0 0 0;font-size:11px;color:#64748b\">' + dimNote + '</p>' : '') + '<p class=\"i2\" style=\"margin:2px 0 0 0;font-size:10px;color:#94a3b8\">本评分为内部质量自审，不得直接用于处罚或正式定性</p></span>';"
content = content.replace(old2, new2)

# 2. Rights chapter - add 知情权/保密权/代理权 before 申请回避权
old3 = "在本次税务合规过程中依法享有以下权利：</p>';"
new3 = "在本次审查中依法享有以下权利。系统仅提供线索核验辅助，不得直接用于正式稽查结论：</p>';\n\n  h += '<h3>一、知情权</h3>';\n  h += '<p class=\"i2\">有权了解审查的法律依据、审查范围、审查期间以及审查人员的身份信息。</p>';\n  h += '<p class=\"i1\" style=\"font-size:12px;color:#64748b\">涉及法规：《税收征收管理法》第八条、《纳税人权利与义务公告》</p>';\n\n  h += '<h3>二、保密权</h3>';\n  h += '<p class=\"i2\">审查中知悉的商业秘密和个人隐私受法律保护。</p>';\n  h += '<p class=\"i1\" style=\"font-size:12px;color:#64748b\">涉及法规：《税收征收管理法》第八条</p>';\n\n  h += '<h3>三、委托代理权</h3>';\n  h += '<p class=\"i2\">有权委托税务师、律师或其他代理人代为办理涉税事宜。</p>';\n  h += '<p class=\"i1\" style=\"font-size:12px;color:#64748b\">涉及法规：《税收征收管理法》第五十七条</p>';\n"
content = content.replace(old3, new3)

# Renumber original rights: 一→四, 二→五, etc.
content = content.replace("<h3>一、申请回避权</h3>", "<h3>四、申请回避权</h3>")
content = content.replace("<h3>二、陈述申辩权</h3>", "<h3>五、陈述申辩权</h3>")
content = content.replace("<h3>三、要求听证权</h3>", "<h3>六、要求听证权</h3>")
content = content.replace("<h3>四、申请行政复议权</h3>", "<h3>七、申请行政复议权</h3>")
content = content.replace("<h3>五、提起行政诉讼权</h3>", "<h3>八、提起行政诉讼权</h3>")

with open('static/js/tax-doc-analysis.js', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')
