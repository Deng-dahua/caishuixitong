"""Debug: step by step reachability audit"""
import sys, os, re, json
from collections import defaultdict

BASE = os.getcwd()

# 1. JSON
json_files = []
for root, dirs, files in os.walk(os.path.join(BASE, "static")):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for fn in files:
        if fn.endswith(".json"):
            json_files.append(os.path.relpath(os.path.join(root, fn), BASE))
print(f"1. JSON: {len(json_files)}")

# 2. Python
py_content = ""
for root, dirs, files in os.walk(BASE):
    dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", ".workbuddy")]
    for fn in files:
        if fn.endswith(".py") and fn not in ("audit_reachability.py", "audit_debug.py"):
            path = os.path.relpath(os.path.join(root, fn), BASE)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    py_content += f.read() + "\n"
            except Exception as e:
                pass
print(f"2. Python: {len(py_content)} chars")

# 3. JS
js_content = ""
for fn in os.listdir(os.path.join(BASE, "static", "js")):
    if fn.endswith(".js"):
        path = os.path.join("static", "js", fn)
        try:
            with open(path, "r", encoding="utf-8") as f:
                js_content += f.read() + "\n"
        except Exception as e:
            print(f"  SKIP {fn}: {e}")
print(f"3. JS: {len(js_content)} chars")

# 4. APIs
api_endpoints = set()
for m in re.finditer(r'@app\.(?:get|post|put|delete)\("([^"]+)"\)', py_content):
    api_endpoints.add(m.group(1))
print(f"4. APIs: {len(api_endpoints)}")
for a in sorted(api_endpoints)[:5]:
    print(f"   {a}")

# 5. Frontend calls each API
api_callers = {}
for api in sorted(api_endpoints):
    callers = []
    short = api.rsplit("/", 1)[-1]
    for fn in os.listdir(os.path.join(BASE, "static", "js")):
        if fn.endswith(".js"):
            path = os.path.join("static", "js", fn)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    jsc = f.read()
                if api in jsc or short in jsc:
                    callers.append(fn)
            except:
                pass
    if callers:
        api_callers[api] = callers

uncalled = [a for a in api_endpoints if a not in api_callers]
print(f"5. Uncalled APIs: {len(uncalled)}")
for a in sorted(uncalled)[:20]:
    print(f"   {a}")

# 6. Sidebar pages
with open(os.path.join(BASE, "static", "index.html"), "r", encoding="utf-8") as f:
    html = f.read()
sidebar_pages = set()
for m in re.finditer(r'data-page="([^"]+)"', html):
    sidebar_pages.add(m.group(1))
print(f"6. Sidebar pages: {len(sidebar_pages)}")

# 7. navigateTo routes
page_routes = {}
nav_start = js_content.find("switch (page)")
if nav_start > 0:
    for m in re.finditer(r"case '([^']+)':", js_content[nav_start:nav_start+5000]):
        page_routes[m.group(1)] = True

# Also check main.py routes
for m in re.finditer(r"case '([^']+)':", py_content):
    page_routes[m.group(1)] = True

orphan = sidebar_pages - set(page_routes.keys())
missing = set(page_routes.keys()) - sidebar_pages - {"break", "default", "cross-domain-evidence", "cross-domain-clues", "cross-domain-analysis"}
print(f"7. Sidebar pages with NO route: {len(orphan)}")
for p in sorted(orphan):
    print(f"   ORPHAN: {p}")
print(f"8. Routes with NO sidebar entry: {len(missing)}")
for p in sorted(missing):
    print(f"   MISSING: {p}")

# 9. Duplicate page routes
from collections import Counter
page_renders = {}
for m in re.finditer(r"case '([^']+)':\s*(\w+)", js_content):
    page_renders[m.group(1)] = m.group(2)
fn_pages = defaultdict(list)
for p, fn in page_renders.items():
    fn_pages[fn].append(p)
print("9. Duplicate page functions (multiple pages -> same render):")
for fn, pages in fn_pages.items():
    if len(pages) > 1 and fn != "break":
        print(f"   {fn} <- {', '.join(pages)}")

print("\nDONE")
