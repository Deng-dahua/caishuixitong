"""Complete cross-reference map: who calls whom, who references what."""
import os, re, json
from collections import defaultdict

BASE = os.getcwd()
out = []

def w(s):
    out.append(s)

# ====== Collect all content ======
py_content = ""
py_files = []
for root, dirs, files in os.walk(BASE):
    dirs[:] = [d for d in dirs if d not in ("__pycache__",".git",".workbuddy","node_modules")]
    for fn in files:
        if fn.endswith(".py"):
            path = os.path.relpath(os.path.join(root, fn), BASE)
            py_files.append(path)
            try:
                with open(path,"r",encoding="utf-8") as f:
                    py_content += f.read() + "\n"
            except: pass

js_content = ""
js_files = []
js_dir = os.path.join(BASE, "static", "js")
for fn in os.listdir(js_dir) if os.path.exists(js_dir) else []:
    if fn.endswith(".js"):
        path = os.path.join("static","js",fn)
        js_files.append(path)
        try:
            with open(path,"r",encoding="utf-8") as f:
                js_content += f.read() + "\n"
        except: pass

# ====== 1. Page -> Render Function -> JS File ======
w("="*60)
w("1. 页面(侧边栏) → 渲染函数 → JS文件")
w("="*60)

# Find render functions in JS
js_funcs = {}
for jf in js_files:
    try:
        with open(jf,"r",encoding="utf-8") as f:
            jsc = f.read()
        for m in re.finditer(r"function\s+(\w+)", jsc):
            js_funcs[m.group(1)] = os.path.basename(jf)
    except: pass

# Find navigateTo routes
page_routes = {}
for m in re.finditer(r"case '([^']+)':\s*(\w+)", js_content):
    page = m.group(1)
    fn = m.group(2)
    page_routes[page] = fn

# Also from main.py
for m in re.finditer(r"case '([^']+)':\s*(\w+)", py_content):
    page_routes[m.group(1)] = m.group(2)

# Sidebar pages
with open(os.path.join(BASE,"static","index.html"),"r",encoding="utf-8") as f:
    html = f.read()

for m in re.finditer(r'data-page="([^"]+)"', html):
    page = m.group(1)
    fn = page_routes.get(page, "?")
    jf = js_funcs.get(fn, "")
    # Find group title
    idx = html.find(f'data-page="{page}"')
    prev = html[:idx].rfind("nav-group-title")
    group = ""
    if prev > 0:
        gm = re.search(r'>([^<]+)<', html[prev:prev+80])
        if gm: group = gm.group(1)
    w(f"  [{group}] {page} -> {fn}() -> {jf}")

# ====== 2. Render function -> API endpoints ======
w("")
w("="*60)
w("2. 渲染函数 → 调用的API端点")
w("="*60)

for jf in js_files:
    try:
        with open(jf,"r",encoding="utf-8") as f:
            jsc = f.read()
    except: continue
    apis = set()
    for m in re.finditer(r"fetch\(['\"]([^'\"]+)['\"]", jsc):
        url = m.group(1)
        if url.startswith("/api/") or url.startswith("/static/"):
            apis.add(url)
    if apis:
        w(f"  {os.path.basename(jf)}:")
        for api in sorted(apis):
            w(f"    -> {api}")

# ====== 3. API -> Python function ======
w("")
w("="*60)
w("3. API端点 → Python后端处理函数")
w("="*60)

for m in re.finditer(r'@app\.(get|post|put|delete)\("([^"]+)"\)\s*\n\s*def\s+(\w+)', py_content):
    method = m.group(1).upper()
    path = m.group(2)
    func = m.group(3)
    w(f"  {method} {path} -> {func}()")

# ====== 4. Python -> JSON data files ======
w("")
w("="*60)
w("4. Python函数 → 读取的JSON数据文件")
w("="*60)

json_refs = defaultdict(set)
for pf in py_files:
    try:
        with open(pf,"r",encoding="utf-8") as f:
            pc = f.read()
    except: continue
    for m in re.finditer(r'["\']([\w\-_/]+\.json)["\']', pc):
        jname = m.group(1)
        if "static" in jname or jname.endswith(".json"):
            json_refs[jname].add(os.path.basename(pf))

for jname, files in sorted(json_refs.items()):
    w(f"  {jname} <- {', '.join(sorted(files)[:3])}")

# ====== 5. Python function -> Engine modules ======
w("")
w("="*60)
w("5. main.py 函数调用 -> engine/ 模块")
w("="*60)

# Find imports in main.py
with open(os.path.join(BASE,"main.py"),"r",encoding="utf-8") as f:
    main_py = f.read()

imports = []
for m in re.finditer(r"from engine\.(\w+)\s+import", main_py):
    imports.append(m.group(1))
imports = sorted(set(imports))
w(f"  main.py imports: {', '.join(imports)}")

# ====== 6. JS -> JS inter-file calls ======
w("")
w("="*60)
w("6. 前端JS文件 → 引用的渲染函数(跨文件调用)")
w("="*60)

for jf in js_files:
    try:
        with open(jf,"r",encoding="utf-8") as f:
            jsc = f.read()
    except: continue
    called = set()
    for m in re.finditer(r"(\w+)\(container\)", jsc):
        fn = m.group(1)
        if fn.startswith("render") and fn != "render":
            # Find which file defines this function
            for jf2 in js_files:
                if jf2 != jf:
                    try:
                        with open(jf2,"r",encoding="utf-8") as f2:
                            jsc2 = f2.read()
                        if f"function {fn}(" in jsc2:
                            called.add(f"{fn}() in {os.path.basename(jf2)}")
                    except: pass
    if called:
        w(f"  {os.path.basename(jf)}:")
        for c in sorted(called):
            w(f"    calls -> {c}")

# ====== 7. Summary ======
w("")
w("="*60)
w("7. 统计")
w("="*60)
w(f"  侧边栏页面: {sum(1 for _ in re.finditer(r'data-page=', html))}")
w(f"  路由映射: {len(page_routes)}")
w(f"  渲染函数: {len(js_funcs)}")
w(f"  API端点: {sum(1 for _ in re.finditer(r'@app\.', py_content))}")
w(f"  JSON引用: {len(json_refs)}")
w(f"  跨文件JS调用: 见第6部分")

with open("crossref_full.txt","w",encoding="utf-8") as f:
    f.write("\n".join(out))

print(f"\nWritten {len(out)} lines to crossref_full.txt")
print("Hint: open crossref_full.txt in VSCode for full view with search")
