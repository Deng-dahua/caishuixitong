files = [
    ("C:/Users/26726/WorkBuddy/2026-05-31-09-56-37/caishuixitong/static/js/tax-pipeline-pages.js", [
        ("四合一数据闭环体系", "全链路稽查质量保障体系"),
        ("四合一闭环", "全链路闭环"),
    ]),
    ("C:/Users/26726/WorkBuddy/2026-05-31-09-56-37/caishuixitong/static/js/tax-doc-analysis.js", [
        ("四合一闭环：规则ID追溯 ✓ · 线索链追溯 ✓ · 证据来源 ✓ · 一键分析 ✓",
         "全链路闭环：规则ID追溯 ✓ · 线索链追溯 ✓ · 证据来源 ✓ · 一键分析 ✓ · 证据链闭环 ✓ · 跨域证据链 ✓"),
    ]),
    ("C:/Users/26726/WorkBuddy/2026-05-31-09-56-37/caishuixitong/static/js/new_analyze_page.js", [
        ("// 3. 四合一数据闭环体系增加详细解释", "// 3. 全链路稽查质量保障体系增加详细解释"),
    ]),
]

for filepath, replacements in files:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    original_len = len(content)
    for old, new in replacements:
        content = content.replace(old, new)
    new_len = len(content)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print("OK: " + filepath.split("/")[-1] + "  (" + str(original_len) + "->" + str(new_len) + " bytes)")

print("Done.")
