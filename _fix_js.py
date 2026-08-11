with open('static/js/tax-doc-analysis.js', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Header disclaimer  
old1 = "h += '<h1>'"
new1 = "  h += '<div style=\"background:#fef3c7;border:1px solid #eab308;border-radius:4px;padding:6px 12px;margin:8px 0;font-size:11px;color:#92400e\">本报告为系统辅助分析结果。所有发现均为待核线索，不得直接作为税务稽查结论、补税金额或违法定性使用。正式结论须经有权人员复核签署。</div>';\n  h += '<h1>'"
content = content.replace(old1, new1)

# 2. Footer disclaimer
old2 = "h += '</body></html>'"
new2 = "  h += '<hr style=\"margin:20px 0;border-color:#e2e8f0\">';\n  h += '<p style=\"font-size:10px;color:#94a3b8;text-align:center\">系统生成·仅供辅助参考·不得直接用于处罚或正式定性·所有结论须经有权人员复核</p>';\n  h += '</body></html>'"
content = content.replace(old2, new2)

with open('static/js/tax-doc-analysis.js', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')
