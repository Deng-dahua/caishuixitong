#!/usr/bin/env python3
"""
系统数据一致性自检引擎
功能：
1. 启动时自动扫描所有 JS/PY 文件，对比 system_config.json 权威数据
2. 发现硬编码数字不一致 → 生成报告 → 可选自动修复
3. 支持 --fix 参数自动替换不一致的数字
"""
import json, re, os, sys
from pathlib import Path

ROOT = Path(__file__).parent
CONFIG_FILE = ROOT / "static" / "system_config.json"

def load_authority():
    """加载权威配置"""
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def scan_files(authority):
    """扫描所有JS/PY文件中的硬编码数字"""
    issues = []
    
    # 定义检查映射: (文件名模式, 正则模式, 权威键名, 描述)
    checks = [
        # JS文件
        (r"static/js/.*\.js$", r"(?<!\w)(15\d{2,3})(?=\s*条|规则|指令)", "rules_count", "规则数"),
        (r"static/js/.*\.js$", r"(?<!\w)(39[0-9]|40[0-5])(?=\s*条.*线索)", "clue_chains", "线索链数"),
        (r"static/js/.*\.js$", r"(?<!\w)(74[0-5]|75[0-4])(?=\s*条.*证据)", "evidence_chains", "证据链数"),
        (r"static/js/.*\.js$", r"(?<!\w)(2[8-9]|3[0-3])(?=\s*条.*方法论|条稽查方法论)", "methodology_count", "方法论数"),
        (r"static/js/.*\.js$", r"(?<!\w)(117[0-4])(?=\s*条.*链|总链)", "total_chains", "总链数"),
        (r"static/js/.*\.js$", r"(?<!\w)(3[5-6])(?=\s*个.*域分析|域分析函数)", "domain_functions", "域分析函数数"),
        # PY文件
        (r"(?:engine/|^)main\.py$", r"(?<!\w)(15\d{2,3})(?=\s*条|规则)", "rules_count", "规则数(PY)"),
        (r"engine/memory\.py$", r"(?<!\w)(15\d{2,3})", "rules_count", "规则数(memory)"),
        (r"engine/.*\.py$", r"(?<!\w)(39[0-9]|40[0-5])(?=.*线索)", "clue_chains", "线索链(PY)"),
        (r"engine/.*\.py$", r"(?<!\w)(74[0-5]|75[0-4])(?=.*证据)", "evidence_chains", "证据链(PY)"),
    ]
    
    for file_pattern, num_pattern, key, desc in checks:
        authority_value = authority.get(key)
        if authority_value is None:
            continue
        
        import glob as g
        for fp in ROOT.glob(file_pattern):
            if fp.name.startswith("_") or fp.suffix == ".bak":
                continue
            with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            
            for i, line in enumerate(lines, 1):
                # 跳过注释中的配置引用、动态获取行
                if "system_config" in line or "getConfig" in line or "_pipelineCounts" in line:
                    continue
                matches = re.finditer(num_pattern, line)
                for m in matches:
                    found = int(m.group(1))
                    if found != authority_value:
                        issues.append({
                            "file": str(fp.relative_to(ROOT)),
                            "line": i,
                            "found": found,
                            "expected": authority_value,
                            "key": key,
                            "desc": desc,
                            "text": line.strip()[:120]
                        })
    
    return issues

def fix_issues(issues, authority):
    """自动修复不一致"""
    fixed = 0
    files_touched = set()
    
    for issue in issues:
        fp = ROOT / issue["file"]
        with open(fp, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        
        old_val = str(issue["found"])
        new_val = str(issue["expected"])
        
        # 精确替换（行内替换，避免全局误替换）
        lines = content.split("\n")
        line_idx = issue["line"] - 1
        if line_idx < len(lines):
            line = lines[line_idx]
            # 只替换行内第一个匹配
            line = re.sub(r'(?<!\w)' + re.escape(old_val) + r'(?!\w)', new_val, line, count=1)
            lines[line_idx] = line
            files_touched.add(issue["file"])
            fixed += 1
        
        content = "\n".join(lines)
        with open(fp, "w", encoding="utf-8") as f:
            f.write(content)
    
    return fixed, files_touched

def print_report(issues, authority):
    """打印审计报告"""
    if not issues:
        print("\n✅ 系统数据一致性审计：全部通过！")
        return True
    
    print(f"\n❌ 发现 {len(issues)} 处数据不一致：")
    print("=" * 80)
    
    by_key = {}
    for iss in issues:
        k = iss["key"]
        if k not in by_key:
            by_key[k] = []
        by_key[k].append(iss)
    
    for key, items in sorted(by_key.items()):
        auth = authority.get(key, "?")
        print(f"\n📊 {key}（权威值={auth}）：{len(items)} 处不一致")
        for it in items[:5]:
            print(f"  {it['file']}:{it['line']}  {it['found']}→{it['expected']}  [{it['desc']}]")
        if len(items) > 5:
            print(f"  ... 还有 {len(items)-5} 处")
    
    print("\n" + "=" * 80)
    return False

def calibrate(authority):
    """闭环校准——将当前数据写入配置，并检查是否需要更新引用"""
    # 重新统计权威数据
    rules_file = ROOT / "static" / "tax_risk_rules_local_export.json"
    chains_file = ROOT / "static" / "audit_chains.json"
    
    if rules_file.exists():
        with open(rules_file) as f:
            authority["rules_count"] = len(json.load(f))
    
    if chains_file.exists():
        with open(chains_file) as f:
            chains = json.load(f)
        authority["clue_chains"] = sum(1 for c in chains["chains"] if c.get("chain_type") == "线索链")
        authority["evidence_chains"] = sum(1 for c in chains["chains"] if c.get("chain_type") == "证据链")
        authority["methodology_count"] = sum(1 for c in chains["chains"] if c.get("chain_type") == "方法论")
        authority["total_chains"] = len(chains["chains"])
    
    da_file = ROOT / "engine" / "domain_analysis.py"
    if da_file.exists():
        with open(da_file) as f:
            authority["domain_functions"] = len(re.findall(r"def _domain_", f.read()))
    
    authority["_calibrated"] = "2026-06-29-auto"
    
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(authority, f, ensure_ascii=False, indent=2)
    
    print("📐 校准完成：数据已从数据源重新统计并写入 system_config.json")

def sync_all(authority):
    """联动同步模式：扫描所有模块，修正全部不一致"""
    from glob import glob
    changes = []
    
    # 数值映射：过时值→正确值
    value_map = {
        "33条方法论": "33条方法论",
        "33条方法": "33条方法",
        "33条实战方法论": "33条实战方法论",
        "1514条": "1514条",
        "1514条": "1514条",
        "396条线索": "396条线索",
        "745条证据": "745条证据",
        "1174条": "1174条",
        "36个分析域": "36个分析域",
        "36个域分析": "36个域分析",
        "25维度": "25维度",
    }
    
    for fp in glob("static/js/*.js") + glob("engine/*.py") + glob("*.py"):
        with open(fp, "r", encoding="utf-8") as f:
            content = f.read()
        original = content
        for old, new in value_map.items():
            if old in content:
                content = content.replace(old, new)
                changes.append((fp, old, new))
        if content != original:
            with open(fp, "w", encoding="utf-8") as f:
                f.write(content)
    
    if changes:
        print(f"\n🔗 联动同步完成：{len(changes)}处修改")
        for ch in changes:
            print(f"  {ch[0]}: {ch[1]} → {ch[2]}")
    else:
        print("\n✅ 全部模块已一致，无需同步")
    return changes


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    authority = load_authority()
    
    if "--calibrate" in sys.argv:
        calibrate(authority)
        sys.exit(0)
    
    if "--sync" in sys.argv:
        sync_all(authority)
        sys.exit(0)
    
    print("🔍 审计启动：扫描系统数据一致性...")
    print(f"   权威配置：rules={authority['rules_count']} clues={authority['clue_chains']} "
          f"evidence={authority['evidence_chains']} method={authority['methodology_count']} "
          f"total={authority['total_chains']} domains={authority['domain_functions']}")
    
    issues = scan_files(authority)
    
    if "--fix" in sys.argv:
        if issues:
            fixed, files = fix_issues(issues, authority)
            print(f"\n✅ 自动修复完成：{fixed} 处不一致已修复，涉及 {len(files)} 个文件")
        else:
            print("\n✅ 无需修复，全部一致")
    else:
        ok = print_report(issues, authority)
        if issues:
            print("\n💡 提示：运行 python audit_consistency.py --fix 可自动修复所有不一致")
