"""
将 main.py 中硬编码行业字典替换为 JSON 加载调用
"""
import re, os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_PY = os.path.join(BASE, "main.py")

with open(MAIN_PY, "r", encoding="utf-8") as f:
    src = f.read()

# ── 替换规则：变量名 → JSON key ──
replacements = {
    "INDUSTRY_BENCHMARKS": "benchmarks",
    "INDUSTRY_PRODUCT_CHAINS": "product_chains",
    "_heavy_goods_examples": "heavy_goods_examples",
    "_cluster_map": "cluster_map",
    "_proc_map": "proc_map",
    "industry_map": "industry_map",
    "service_industries": "service_industries",
    "production_industries": "production_industries",
    "ALL_INDUSTRIES": "all_industries",
    "_INDUSTRY_CHAIN_PREFIXES": "chain_prefixes",
}

# Step 1: Delete each hardcoded dict definition block
for var_name in replacements:
    pattern = rf'\n# .*\n{re.escape(var_name)}\s*=\s*[{{\[(].*?(?=\n\ndef |\n# ={10,}|\n\Z)'
    # More aggressive: find the block start and block end
    block_pattern = rf'{re.escape(var_name)}\s*=\s*[{{\[(]'
    m = re.search(block_pattern, src)
    if not m:
        print(f"  SKIP (not found): {var_name}")
        continue
    
    start = m.start()
    # Find the end of this block (next top-level definition or comment marker)
    # Find matching bracket
    ch = src[m.end()-1]
    close = {"{": "}", "[": "]", "(": ")"}[ch]
    depth = 1
    i = m.end()
    while i < len(src) and depth > 0:
        if src[i] == ch: depth += 1
        elif src[i] == close: depth -= 1
        i += 1
    
    # Also consume trailing comma and any blank lines
    while i < len(src) and src[i] in ",\n\r ":
        i += 1
    
    block = src[start:i]
    # Count lines removed
    lines_removed = block.count("\n")
    
    # Replace with comment
    src = src[:start] + f"# [外部化] {var_name} → 从 industry_data.json 加载，见 static/industry_data.json" + src[i:]
    print(f"  DELETED: {var_name} ({lines_removed} lines)")

# Step 2: Add model_to_key to the loader (was inline in _load_industry_profile)
# Find the model_to_key block and replace with JSON-loaded version
model_to_key_pattern = r"model_to_key\s*=\s*\{[^}]+\}"
model_replacement = "model_to_key = _load_industry_data().get(\"model_to_key\", {\"制造业\": \"制造业\", \"贸易\": \"贸易批发\", \"服务/劳务\": \"服务业\"})"
src, n = re.subn(model_to_key_pattern, model_replacement, src)
print(f"  REPLACED model_to_key: {n} occurrence(s)")

# Step 3: Replace all variable references with JSON-loaded calls
# Pattern: VAR_NAME.get(...) or VAR_NAME[...] or VAR_NAME in ...
for var_name, json_key in replacements.items():
    count = 0
    # Replace VAR_NAME.get( → _load_industry_data().get("json_key", {}).get(
    old = f"{var_name}.get("
    new = f'_load_industry_data().get("{json_key}", {{}}).get('
    while old in src:
        src = src.replace(old, new, 1)
        count += 1
    
    # Replace VAR_NAME[ → _load_industry_data()["json_key"][
    old = f"{var_name}["
    new = f'_load_industry_data()["{json_key}"]['
    while old in src:
        src = src.replace(old, new, 1)
        count += 1
    
    # Replace `if VAR_NAME:` or `in VAR_NAME` patterns
    old = f"if {var_name}:"
    if old in src:
        new = f"if _load_industry_data().get(\"{json_key}\"):"
        src = src.replace(old, new, 1)
        count += 1
    
    if count > 0:
        print(f"  REPLACED {var_name} references: {count}")

# Add model_to_key to the JSON (will need to also update the JSON)
# For now, patch the loader to provide a default
# Find _load_industry_data function and add model_to_key default
loader_patch = '_INDUSTRY_DATA_CACHE.setdefault("model_to_key", {"制造业": "制造业", "贸易": "贸易批发", "服务/劳务": "服务业"})'
# Insert after the try/except block in _load_industry_data
if '_INDUSTRY_DATA_CACHE' in src and 'model_to_key' not in src:
    # Add the default after json.load or after the except
    patch_target = '_INDUSTRY_DATA_CACHE = json.load(f)'
    if patch_target in src:
        src = src.replace(patch_target, 
                         f'{patch_target}\n        {loader_patch}')
        print("  PATCHED: model_to_key default in loader")

with open(MAIN_PY, "w", encoding="utf-8") as f:
    f.write(src)

print(f"\nDone! File: {MAIN_PY} ({len(src)} chars)")
