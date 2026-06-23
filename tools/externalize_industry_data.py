"""
将 main.py 中硬编码的行业字典外部化到 static/industry_data.json
"""
import re, json, sys, os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_PY = os.path.join(BASE, "main.py")
OUT_JSON = os.path.join(BASE, "static", "industry_data.json")

with open(MAIN_PY, "r", encoding="utf-8") as f:
    src = f.read()
    lines = src.split("\n")

# Helper: extract a Python dict block from source text, between start pattern and end marker
def extract_dict_block(text, var_name):
    """Find `var_name = {` or `var_name = (` and return the Python literal block."""
    pattern = rf'{var_name}\s*=\s*[{{\[(]'
    m = re.search(pattern, text)
    if not m:
        print(f"  NOT FOUND: {var_name}")
        return None
    start = m.start()
    # Find the matching closing bracket
    ch = text[m.end()-1]
    close = {"{": "}", "[": "]", "(": ")"}[ch]
    depth = 1
    i = m.end()
    while i < len(text) and depth > 0:
        if text[i] == ch: depth += 1
        elif text[i] == close: depth -= 1
        i += 1
    block = text[m.start():i]
    return block

# Read the blocks we already know
benchmarks_src = extract_dict_block(src, "INDUSTRY_BENCHMARKS")
product_chains_src = extract_dict_block(src, "INDUSTRY_PRODUCT_CHAINS")
heavy_goods_src = extract_dict_block(src, "_heavy_goods_examples")
cluster_map_src = extract_dict_block(src, "_cluster_map")
proc_map_src = extract_dict_block(src, "_proc_map")
industry_map_src = extract_dict_block(src, "industry_map")
service_ind_src = extract_dict_block(src, "service_industries")
prod_ind_src = extract_dict_block(src, "production_industries")
all_ind_src = extract_dict_block(src, "ALL_INDUSTRIES")
chain_prefix_src = extract_dict_block(src, "_INDUSTRY_CHAIN_PREFIXES")

# Convert each block to Python objects by eval (safe - these are simple data structures)
def safe_eval_dict(code):
    """Evaluate a Python dict literal safely."""
    try:
        # Remove the variable assignment prefix
        code = re.sub(r'^\w+\s*=\s*', '', code.strip())
        return eval(code)
    except Exception as e:
        print(f"  EVAL ERROR: {e}")
        return None

data = {}
for name, src_block in [
    ("benchmarks", benchmarks_src),
    ("product_chains", product_chains_src),
    ("heavy_goods_examples", heavy_goods_src),
    ("cluster_map", cluster_map_src),
    ("proc_map", proc_map_src),
    ("industry_map", industry_map_src),
    ("service_industries", service_ind_src),
    ("production_industries", prod_ind_src),
    ("all_industries", all_ind_src),
    ("chain_prefixes", chain_prefix_src),
]:
    if src_block:
        val = safe_eval_dict(src_block)
        if val is not None:
            data[name] = val
            # Print summary
            if isinstance(val, dict):
                print(f"  {name}: {len(val)} entries")
            elif isinstance(val, (list, tuple)):
                print(f"  {name}: {len(val)} items (list/tuple → converted to list)")
                data[name] = list(val)  # Convert tuples to lists for JSON
        else:
            print(f"  {name}: eval FAILED")
    else:
        print(f"  {name}: not found")

# Write JSON
with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

size_kb = os.path.getsize(OUT_JSON) / 1024
print(f"\nWritten: {OUT_JSON} ({size_kb:.1f} KB)")
print("Done!")
