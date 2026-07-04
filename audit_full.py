"""Full reachability audit: who calls whom, who references what"""
import sys, os, re, json
from collections import Counter, defaultdict

BASE = os.getcwd()
report = []

def add(msg):
    report.append(msg)
    print(msg)

# ====== 1. Collect all code content ======
add("=" * 60)
add("全链路可达性审计 v1.0")
add("=" * 60)

py_content = ""
py_files = []
for root, dirs, files in os.walk(BASE):
    dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", ".workbuddy")]
    for fn in files:
        if fn.endswith(".py") and fn not in ("audit_reachability.py", "audit_debug.py", "audit_full.py"):
            path = os.path.relpath(os.path.join(root, fn), BASE)
            py_files.append(path)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    py_content += f.read() + "\n"
            except: pass

js_content = ""
js_files = []
for fn in os.listdir(os.path.join(BASE, "static", "js")):
    if fn.endswith(".js"):
        path = os.path.join("static", "js", fn)
        js_files.append(path)
        try:
            with open(path, "r", encoding="utf-8") as f:
                js_content += f.read() + "\n"
        except: pass

all_code = py_content + js_content

add(f"\n[概览] {len(py_files)}个.py, {len(js_files)}个.js, {len(py_content)+len(js_content):,}字符")

# ====== 2. API endpoints -> frontend callers ======
add(f"\n{'='*40}\n[1] API端点 → 前端调用")
api_endpoints = set()
for m in re.finditer(r'@app\.(?:get|post|put|delete)\("([^"]+)"\)', py_content):
    api_endpoints.add(m.group(1))

uncalled = []
called_list = []
for api in sorted(api_endpoints):
    callers = []
    short = api.rsplit("/", 1)[-1]
    for jf in js_files:
        try:
            with open(jf, "r", encoding="utf-8") as f:
                jsc = f.read()
            if api in jsc or short in jsc:
                callers.append(os.path.basename(jf))
        except: pass
    if callers:
        called_list.append((api, callers))
    else:
        uncalled.append(api)

add(f"  API总数: {len(api_endpoints)}  被调用: {len(called_list)}  未被调用: {len(uncalled)}")
if uncalled:
    add(f"\n  【未被前端调用的API】{len(uncalled)}个(可能是后端内部/AGI/管理类):")
    for api in uncalled:
        # Categorize
        if "/agi/" in api: tag = "[AGI]"
        elif "/api-key" in api or "/apikey" in api: tag = "[KEY]"
        elif "/company" in api: tag = "[COMPANY]"
        elif "/account" in api: tag = "[ACCOUNT]"
        elif "/journal" in api: tag = "[JOURNAL]"
        else: tag = "[OTHER]"
        if tag != "[AGI]":  # AGI ones may be called differently
            add(f"    {tag} {api}")

# ====== 3. Page routes <-> sidebar ======
add(f"\n{'='*40}\n[2] 页面路由 → 侧边栏入口")
with open(os.path.join(BASE, "static", "index.html"), "r", encoding="utf-8") as f:
    html = f.read()
sidebar_pages = set()
for m in re.finditer(r'data-page="([^"]+)"', html):
    sidebar_pages.add(m.group(1))

# Find all page routes from JS navigateTo
page_routes_js = {}
for m in re.finditer(r"case '([^']+)':\s*(\w+)", js_content):
    page_routes_js[m.group(1)] = m.group(2)

# Find from main.py too
for m in re.finditer(r"case '([^']+)':\s*(\w+)", py_content):
    page_routes_js[m.group(1)] = m.group(2)

orphan_sidebar = sidebar_pages - set(page_routes_js.keys()) - {"cross-domain-evidence", "cross-domain-clues", "cross-domain-analysis"}
missing_sidebar = set(page_routes_js.keys()) - sidebar_pages - {"break", "default"}

add(f"  侧边栏项: {len(sidebar_pages)}  路由: {len(page_routes_js)}")
add(f"  侧边栏无路由: {len(orphan_sidebar)}  路由无侧边栏: {len(missing_sidebar)}")

# Duplicate render functions
fn_pages = defaultdict(list)
for p, fn in page_routes_js.items():
    if fn and fn != "break":
        fn_pages[fn].append(p)
dupes = {fn: pages for fn, pages in fn_pages.items() if len(pages) > 1}
if dupes:
    add(f"\n  【多入口共用渲染函数】{len(dupes)}处:")
    for fn, pages in sorted(dupes.items()):
        add(f"    {fn} ← {', '.join(pages)}")

# ====== 4. Rule categories referenced in code ======
add(f"\n{'='*40}\n[3] 规则分类 → 代码引用")

with open("static/tax_risk_rules_local_export.json", "r", encoding="utf-8") as f:
    rules = json.load(f)
rule_cats = Counter(r.get("category", "") for r in rules)

# Check if each category name appears in Python or JS code
cat_in_code = {}
for cat in rule_cats:
    in_py = cat in py_content
    in_js = cat in js_content
    cat_in_code[cat] = {"py": in_py, "js": in_js, "count": rule_cats[cat]}

dead_cats = [c for c, v in cat_in_code.items() if not v["py"] and not v["js"]]
add(f"  规则分类: {len(rule_cats)}  代码中引用: {len(rule_cats)-len(dead_cats)}  死分类(无代码引用): {len(dead_cats)}")
if dead_cats:
    for c in dead_cats:
        add(f"    DEAD: {c} ({rule_cats[c]}条规则)")

# ====== 5. JSON data files -> code references ======
add(f"\n{'='*40}\n[4] JSON数据文件 → 代码引用")

# Key JSON files to check
key_jsons = [
    "static/tax_risk_rules_local_export.json",
    "static/cross_domain_clues.json",
    "static/cross_domain_evidence.json",
    "static/cross_domain_analysis.json",
    "static/methodology_items.json",
    "static/audit_rules.json",
    "static/legal_refs.json",
    "static/system_config.json",
    "static/shared_content_map.json",
]

for jf in key_jsons:
    jf_short = os.path.basename(jf)
    path = os.path.join(BASE, jf)
    if not os.path.exists(path):
        add(f"  MISSING: {jf}")
        continue
    
    # Count references in code
    refs = []
    for pf in py_files:
        try:
            with open(pf, "r", encoding="utf-8") as f:
                pc = f.read()
            if jf_short in pc:
                refs.append(os.path.basename(pf))
        except: pass
    for jf2 in js_files:
        try:
            with open(jf2, "r", encoding="utf-8") as f:
                jc = f.read()
            if jf_short in jc:
                refs.append(os.path.basename(jf2))
        except: pass
    
    status = "OK" if refs else "DEAD"
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list): size = f"{len(data)}条"
        elif isinstance(data, dict): size = f"{len(data)}键"
        else: size = "1"
    except: size = "?"
    
    add(f"  [{status}] {jf_short} ({size}) ← {refs[:3]}{'...' if len(refs)>3 else ''}")

# ====== 6. Category DESCRIPTION check ======
add(f"\n{'='*40}\n[5] CATEGORY_DESCRIPTIONS vs 实际规则分类")

with open("static/js/tax-risk-rules.js", "r", encoding="utf-8") as f:
    rules_js = f.read()

# Extract CATEGORY_DESCRIPTIONS keys
desc_keys = set()
for m in re.finditer(r"'([^']+)'\s*:\s*'", rules_js[:rules_js.find("var CATEGORY_DESCRIPTIONS")+5000]):
    key = m.group(1)
    if len(key) >= 2 and len(key) <= 10:
        desc_keys.add(key)

# Filter to only Chinese keys
desc_keys = {k for k in desc_keys if any('\u4e00' <= c <= '\u9fff' for c in k)}

# Compare
actual_cats = set(rule_cats.keys())
only_in_desc = desc_keys - actual_cats
only_in_data = actual_cats - desc_keys - {""}
common = desc_keys & actual_cats

add(f"  CATEGORY_DESCRIPTIONS: {len(desc_keys)}个")
add(f"  实际数据分类: {len(actual_cats)}个")
add(f"  交集: {len(common)}  仅在DESC: {len(only_in_desc)}  仅在数据: {len(only_in_data)}")
if only_in_desc:
    add(f"  仅在CATEGORY_DESCRIPTIONS中存在(前端会显示但数据中没有):")
    for c in sorted(only_in_desc):
        add(f"    {c}")
if only_in_data:
    add(f"  仅在数据中存在(前端DESCRIPTION缺失):")
    for c in sorted(only_in_data):
        add(f"    {c} ({rule_cats[c]}条)")

# ====== 7. Methods methodology check ======
add(f"\n{'='*40}\n[6] 33条方法论文档 vs 代码")

with open("static/methodology_items.json", "r", encoding="utf-8") as f:
    methods = json.load(f)

methods_in_code = []
methods_not_found = []
for m in methods:
    name = m["name"]
    short = name[:4]
    found = name in py_content or short in py_content or name in js_content or short in js_content
    if found:
        methods_in_code.append(name)
    else:
        methods_not_found.append(name)

add(f"  方法论总数: {len(methods)}")
add(f"  代码中有对应实现: {len(methods_in_code)}")
add(f"  代码中未找到: {len(methods_not_found)}")
for m in methods_not_found:
    add(f"    {m}")

# ====== 8. Output ======
add(f"\n{'='*40}\n[总结]")
add(f"  API死端点: {len(uncalled)}个需要清理或确认")
add(f"  重复渲染函数: {len(dupes)}处")
add(f"  规则分类不一致: {len(only_in_desc)+len(only_in_data)}处")
add(f"  方法论未实现: {len(methods_not_found)}条")
add(f"  侧边栏无路由: {len(orphan_sidebar)}个")
add(f"  路由无侧边栏: {len(missing_sidebar)}个")

with open("audit_full_report.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(report))
