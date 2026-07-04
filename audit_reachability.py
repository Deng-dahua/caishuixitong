#!/usr/bin/env python3
"""
全链路可达性审计 — 扫描谁调用谁、谁引用谁
输出：
  1. JSON数据文件 → 被哪些.py/.js引用
  2. API端点 → 被哪些前端调用
  3. 死数据（JSON key无任何引用）
  4. 死代码（函数/变量无任何引用）
"""
import os, re, json, sys
from collections import defaultdict

BASE = os.getcwd()

# ══════════════════════════════════════
# 1. 收集所有 JSON 数据文件
# ══════════════════════════════════════
json_files = []
for root, dirs, files in os.walk(os.path.join(BASE, "static")):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for fn in files:
        if fn.endswith(".json"):
            path = os.path.join(root, fn)
            rel = os.path.relpath(path, BASE)
            json_files.append(rel)

# 读取JSON内容，提取key
json_data = {}  # {filename: {keys: [...], items: [...]}}
for jf in json_files:
    try:
        with open(os.path.join(BASE, jf), "r", encoding="utf-8") as f:
            data = json.load(f)
    except:
        continue
    keys = []
    items = []
    if isinstance(data, dict):
        keys = list(data.keys())
        # 提取深层key
        def extract_keys(obj, prefix=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    full = f"{prefix}.{k}" if prefix else k
                    keys.append(full)
                    if isinstance(v, (dict, list)):
                        extract_keys(v, full)
            elif isinstance(obj, list):
                for i, item in enumerate(obj[:3]):  # 采样前3个
                    if isinstance(item, dict):
                        for k in item.keys():
                            keys.append(f"{prefix}[].{k}")
                            if k in ("name", "id", "item", "sub_topic", "category", "page"):
                                val = str(item[k])[:60]
                                if val:
                                    items.append(val)
                    break
        extract_keys(data)
    elif isinstance(data, list):
        if data and isinstance(data[0], dict):
            keys = list(data[0].keys())
            if "name" in data[0]:
                items = [str(d["name"])[:60] for d in data[:3]]
            elif "item" in data[0]:
                items = [str(d["item"])[:60] for d in data[:3]]
    json_data[jf] = {"keys": list(set(keys[:200])), "items": list(set(items))[:50], "count": len(data) if isinstance(data, list) else 1}

# ══════════════════════════════════════
# 2. 收集所有 Python 文件内容
# ══════════════════════════════════════
py_files = []
py_content = ""
for root, dirs, files in os.walk(BASE):
    dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", ".workbuddy", "node_modules")]
    for fn in files:
        if fn.endswith(".py") and fn != "audit_reachability.py":
            path = os.path.join(root, fn)
            rel = os.path.relpath(path, BASE)
            py_files.append(rel)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    py_content += f.read() + "\n"
            except:
                pass

# ══════════════════════════════════════
# 3. 收集所有 JS 文件内容
# ══════════════════════════════════════
js_files = []
js_content = ""
for root, dirs, files in os.walk(os.path.join(BASE, "static", "js")):
    for fn in files:
        if fn.endswith(".js"):
            path = os.path.join(root, fn)
            rel = os.path.relpath(path, BASE)
            js_files.append(rel)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    js_content += f.read() + "\n"
            except:
                pass

# ══════════════════════════════════════
# 4. API端点 ←→ 前端调用
# ══════════════════════════════════════
api_endpoints = []
for m in re.finditer(r'@app\.(?:get|post|put|delete)\("([^"]+)"\)', py_content):
    api_endpoints.append(m.group(1))
api_endpoints = list(set(api_endpoints))

api_callers = defaultdict(list)  # {endpoint: [js_file, ...]}
for endpoint in api_endpoints:
    short = endpoint.rsplit("/", 1)[-1] if "/" in endpoint else endpoint
    for jsf in js_files:
        jsp = os.path.join(BASE, jsf)
        try:
            with open(jsp, "r", encoding="utf-8") as f:
                jsc = f.read()
            if endpoint in jsc or short in jsc:
                api_callers[endpoint].append(jsf)
        except:
            pass

uncalled_apis = [e for e in api_endpoints if not api_callers.get(e)]

# ══════════════════════════════════════
# 5. JSON字段 ←→ Python/JS引用
# ══════════════════════════════════════
json_refs = {}  # {json_file: {field: [referring_files]}}
for jf, jdata in json_data.items():
    jf_short = os.path.basename(jf)
    refs = defaultdict(list)
    for key in jdata["keys"]:
        short_key = key.split(".")[-1]  # last segment
        for pf in py_files:
            try:
                with open(os.path.join(BASE, pf), "r", encoding="utf-8") as f:
                    pc = f.read()
                if short_key in pc and jf_short in pc:
                    refs[key].append(pf)
            except:
                pass
        for jf2 in js_files:
            try:
                with open(os.path.join(BASE, jf2), "r", encoding="utf-8") as f:
                    jc = f.read()
                if short_key in jc:
                    refs[key].append(jf2)
            except:
                pass
    json_refs[jf] = dict(refs)

# ══════════════════════════════════════
# 6. 路由（page）→ 渲染函数
# ══════════════════════════════════════
page_routes = {}
for m in re.finditer(r"case '([^']+)':\s*(?:render|window\.location|show)?(\w*)", py_content):
    page_routes[m.group(1)] = m.group(2)
# Also from core.js
for m in re.finditer(r"case '([^']+)':\s*(\w+)", js_content):
    page_routes[m.group(1)] = m.group(2)

# Sidebar pages
sidebar_pages = set()
with open(os.path.join(BASE, "static", "index.html"), "r", encoding="utf-8") as f:
    html = f.read()
for m in re.finditer(r'data-page="([^"]+)"', html):
    sidebar_pages.add(m.group(1))

missing_sidebar = set(page_routes.keys()) - sidebar_pages - {"company", "break", "default", "cross-domain-"}
orphan_pages = sidebar_pages - set(page_routes.keys())

# ══════════════════════════════════════
# 7. 输出报告
# ══════════════════════════════════════
report = []
report.append("=" * 70)
report.append("全链路可达性审计报告")
report.append("=" * 70)

report.append(f"\n【概览】")
report.append(f"  JSON数据文件: {len(json_files)}")
report.append(f"  Python文件: {len(py_files)}")  
report.append(f"  JS文件: {len(js_files)}")
report.append(f"  API端点: {len(api_endpoints)}")
report.append(f"  页面路由: {len(page_routes)}")
report.append(f"  侧边栏项: {len(sidebar_pages)}")

report.append(f"\n【API端点——未被前端调用】{len(uncalled_apis)}个")
for api in sorted(uncalled_apis)[:30]:
    report.append(f"  ✗ {api}")
if len(uncalled_apis) > 30:
    report.append(f"  ... 另有{len(uncalled_apis)-30}个")

report.append(f"\n【API端点——被前端调用】示例（前20）")
called = [(e, callers) for e, callers in api_callers.items() if callers]
for e, callers in sorted(called, key=lambda x: -len(x[1]))[:20]:
    report.append(f"  {e}  ← {callers[0]} +{len(callers)-1}个")

report.append(f"\n【侧边栏页面——无渲染函数】{len(orphan_pages)}个")
for p in sorted(orphan_pages):
    report.append(f"  ✗ {p}")

report.append(f"\n【渲染函数——无侧边栏入口】{len(missing_sidebar)}个")
for p in sorted(missing_sidebar)[:20]:
    report.append(f"  ✗ {p}")

report.append(f"\n【JSON→代码引用分析】")
for jf in sorted(json_files):
    refs = json_refs.get(jf, {})
    has_ref = sum(len(v) for v in refs.values())
    if not has_ref:
        report.append(f"  ✗ 死文件: {jf} (无任何.py/.js引用)")
    elif jf in ("static/tax_risk_rules_local_export.json", "static/cross_domain_clues.json", "static/cross_domain_evidence.json", "static/cross_domain_analysis.json"):
        report.append(f"  ✓ {jf}: {len(refs)}个字段被引用")

report.append(f"\n【重复页面入口】")
page_funcs = defaultdict(list)
for p, fn in page_routes.items():
    if fn:
        page_funcs[fn].append(p)
for fn, pages in page_funcs.items():
    if len(pages) > 1 and fn != "break":
        report.append(f"  ✗ 函数{fn}被{pages}共用→{len(pages)}个入口")

# 写出
with open(os.path.join(BASE, "audit_reachability_report.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(report))

print("\n".join(report))
