#!/usr/bin/env python3
"""
系统数据一致性自检引擎
功能：
1. 启动时自动扫描所有 JS/PY 文件，对比 system_config.json 权威数据
2. 发现硬编码数字不一致 → 生成报告 → 可选自动修复
3. 支持 --fix 参数自动替换不一致的数字
4. 支持 --sync 联动同步（代码层+文档层+共享内容层）
5. 跨模块内容一致性标准 —— 同一内容在多模块出现时必须一致
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
        (r"static/js/.*\.js$", r"(?<!\w)(2[8-9]|3[0-3])(?=\s*条.*方法论|条税务合规方法论)", "methodology_count", "方法论数"),
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
    clues_file = ROOT / "static" / "cross_domain_clues.json"
    evidence_file = ROOT / "static" / "cross_domain_evidence.json"
    analysis_file = ROOT / "static" / "cross_domain_analysis.json"
    
    if rules_file.exists():
        with open(rules_file, encoding='utf-8') as f:
            authority["rules_count"] = len(json.load(f))
    
    # 线索链：从 cross_domain_clues.json 统计
    if clues_file.exists():
        with open(clues_file, encoding='utf-8') as f:
            clues = json.load(f)
        authority["clue_chains"] = len(clues)  # 总线索链数=1215
        authority["executable_clues"] = sum(1 for c in clues if c.get("executable", True))
        authority["legacy_clues"] = sum(1 for c in clues if c.get("legacy", False))
    
    # 证据链：从 cross_domain_evidence.json 统计
    if evidence_file.exists():
        with open(evidence_file, encoding='utf-8') as f:
            evidence = json.load(f)
        authority["evidence_chains"] = len(evidence)
        authority["executable_evidence"] = sum(1 for e in evidence if e.get("executable", True))
        authority["legacy_evidence"] = sum(1 for e in evidence if e.get("legacy", False))
    
    # 分析链：从 cross_domain_analysis.json 统计
    if analysis_file.exists():
        with open(analysis_file, encoding='utf-8') as f:
            analysis = json.load(f)
        authority["analysis_chains"] = len(analysis)
    
    # 总链数（线索+证据+分析）
    authority["total_chains"] = authority.get("clue_chains", 0) + \
                                 authority.get("evidence_chains", 0) + \
                                 authority.get("analysis_chains", 0)
    authority["methodology_count"] = authority.get("legacy_clues", 0)  # 旧方法链=legacy数
    
    da_file = ROOT / "engine" / "domain_analysis.py"
    if da_file.exists():
        with open(da_file, encoding='utf-8') as f:
            authority["domain_functions"] = len(re.findall(r"def _domain_", f.read()))
    
    authority["_calibrated"] = "2026-06-30-merged"
    
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(authority, f, ensure_ascii=False, indent=2)
    
    print("📐 校准完成：数据已从数据源重新统计并写入 system_config.json")

def sync_all(authority):
    """联动同步模式：扫描所有模块，修正全部不一致"""
    from glob import glob
    changes = []
    
    rc = authority.get("rules_count", 1608)
    cc = authority.get("clue_chains", 1215)
    ec = authority.get("evidence_chains", 22)
    ac = authority.get("analysis_chains", 13)
    mc = authority.get("methodology_count", 1174)
    tc = authority.get("total_chains", 1250)
    dc = authority.get("domain_functions", 39)
    
    # 数值映射：可能在文件中出现的旧值→正确的权威值
    value_map = {
        # 规则数：多种旧写法都映射到当前权威值
        "1610条": f"{rc}条",
        # 线索链
        "437条线索(全部可执行)": "437条线索(全部可执行)",
        "437条": f"{cc}条",
        # 证据链
        "22条跨域证据": "22条跨域证据",
        # 方法论
        "1266条方法链(legacy)": "1266条方法链(legacy)",
        "1266条方法链": "1266条方法链",
        "1266条方法链": "1266条方法链",
        # 总链
        "1266条": f"{tc}条",
        # 域分析
        "39个分析域": f"{dc}个分析域",
        "39个域分析": f"{dc}个域分析",
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
    
    # 同步引擎记忆文档层
    mem_changes = sync_memory_docstring(authority)
    changes.extend(mem_changes)
    
    if changes:
        print(f"\n🔗 联动同步完成：{len(changes)}处修改")
        for ch in changes:
            print(f"  {ch[0]}: {ch[1]} → {ch[2]}")
    else:
        print("\n✅ 全部模块已一致，无需同步")
    return changes


def sync_memory_docstring(authority):
    """同步引擎记忆文档层——将 system_config.json 的数据写入 engine/memory.py 的 docstring"""
    memory_file = ROOT / "engine" / "memory.py"
    if not memory_file.exists():
        return []
    
    with open(memory_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    original = content
    changes = []
    
    # 获取权威数据
    rc = authority.get("rules_count", 1608)
    cc = authority.get("clue_chains", 1215)
    ec = authority.get("evidence_chains", 22)
    mc = authority.get("methodology_count", 1174)
    tc = authority.get("total_chains", 1250)
    dc = authority.get("domain_functions", 39)
    
    # 获取额外的动态数据
    ff = authority.get("file_fingerprints", 34)
    qs = authority.get("quality_standards", 12)
    
    # 统计 user_corrections.json 中的规则数
    cr_count = 0
    cr_file = ROOT / "static" / "user_corrections.json"
    if cr_file.exists():
        with open(cr_file, "r", encoding="utf-8") as f:
            cr = json.load(f)
            cr_count = len(cr)
    
    # 统计 industry_data.json 中的收款分类规则数
    rc_rules = 12  # 固定12条，数据结构为多级嵌套，不便自动统计
    
    # 定义替换映射：旧值模式 → 新值（支持正则）
    replacements = [
        # 核心数据
        (r"(?<!\w)1514(?!\d)", str(rc), "规则数"),
        (r"(?<!\w)396(?!\d)(?=.*线索)", str(cc), "线索链数"),
        (r"(?<!\w)745(?!\d)(?=.*证据)", str(ec), "证据链数"),
        (r"(?<!\w)33(?!\d)(?=.*方法论|条税务合规方法论|条方法)", str(mc), "方法论数"),
        (r"(?<!\w)1174(?!\d)", str(tc), "总链数"),
        (r"(?<!\w)36(?!\d)(?=.*域分析|域函数|个域)", str(dc), "域分析函数数"),
        (r"(?<!\w)34(?!\d)(?=.*文件指纹|类指纹)", str(ff), "文件指纹数"),
        (r"(?<!\w)12(?!\d)(?=.*质量标准|质量保障标准)", str(qs), "质量标准数"),
        
        # 收款分类
        (r"(?<!\w)12条(?=.*收款.*分类|分类规则)", str(rc_rules) + "条", "收款分类规则数"),
        
        # 引擎铁律章节
        (r"23类.*HARD_BAN|HARD_BAN.*23类", "23类", "HARD_BAN数"),
        
        # 知识库
        (r"(?<!\w)500条(?=.*记忆)", "500条", "知识库上限"),
        
        # 调度中枢
        (r"(?<!\w)16(?!\d)(?=.*功能模块|个模块)", "16", "功能模块数"),
        (r"(?<!\w)7(?!\d)(?=.*数据域|个域)", "7", "数据域数"),
        
        # 仪表盘
        (r"(?<!\w)6(?!\d)(?=.*标签页|个标签)", "6", "标签页数"),
        
        # 前端页面
        (r"(?<!\w)17(?!\d)(?=.*页面|个页面)", "17", "前端页面数"),
    ]
    
    # 只更新docstring内的内容（在首尾"""之间）
    # docstring从第一行"""开始，到下一个单独的"""结束
    ds_start = content.find('"""\n', 0)  # opening """
    if ds_start < 0:
        ds_start = content.find('"""')
    ds_end = content.find('\n"""', ds_start + 3)  # closing """
    if ds_end < 0:
        ds_end = content.find('"""', ds_start + 3)
    
    if ds_start < 0 or ds_end < 0:
        return []
    
    before = content[:ds_start + 3]
    docstring = content[ds_start + 3:ds_end]
    after = content[ds_end:]
    
    for pattern, new_val, desc in replacements:
        matches = list(re.finditer(pattern, docstring))
        for m in matches:
            old_val = m.group(0)
            if old_val != new_val:
                docstring = docstring.replace(old_val, new_val, 1)
                changes.append(("engine/memory.py [docstring]", old_val, new_val))
    
    # 更新权威数据区块
    auth_block_pattern = r"(rules_count=\d+.*?noise_filter_rate=\d+)"
    auth_match = re.search(auth_block_pattern, docstring)
    if auth_match:
        old_auth = auth_match.group(1)
        new_auth = (f"rules_count={rc} | clue_chains={cc} | evidence_chains={ec} | "
                   f"methodology_count={mc} | total_chains={tc} | domain_functions={dc}")
        if old_auth != new_auth:
            docstring = docstring.replace(old_auth, new_auth)
            changes.append(("engine/memory.py [权威数据]", "过时数据", "已更新"))
    
    if changes:
        content = before + docstring + after
        with open(memory_file, "w", encoding="utf-8") as f:
            f.write(content)
    
    return changes


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    authority = load_authority()
    
    if "--calibrate" in sys.argv:
        calibrate(authority)
        sys.exit(0)

    if "--rebuild-shared-map" in sys.argv:
        from engine.shared_content_sync import rebuild_shared_map
        log = rebuild_shared_map()
        for l in log:
            print(l)
        sys.exit(0)
    
    if "--sync" in sys.argv:
        sync_all(authority)
        # 同步共享内容（跨模块文本一致性）
        from engine.shared_content_sync import sync_shared_content
        shared_log = sync_shared_content()
        print("\n📋 共享内容同步：")
        for l in shared_log:
            print(f"  {l}")
        sys.exit(0)
    
    print("🔍 审计启动：扫描系统数据一致性...")
    print(f"   权威配置：rules={authority['rules_count']} clues={authority['clue_chains']} "
          f"evidence={authority['evidence_chains']} analysis={authority.get('analysis_chains', 0)} "
          f"legacy={authority.get('legacy_clues', 0)} total={authority['total_chains']} domains={authority['domain_functions']}")
    
    issues = scan_files(authority)
    
    # 验证共享内容一致性
    from engine.shared_content_sync import verify_shared_content
    shared_ok, shared_log = verify_shared_content()
    if not shared_ok:
        print("\n📋 共享内容一致性检查（发现问题）：")
        for l in shared_log:
            print(f"  {l}")
    else:
        # Print first line of shared_log (the summary line)
        if shared_log:
            print(f"  {shared_log[0]}")
    
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
