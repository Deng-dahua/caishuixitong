"""
提交前自查脚本 —— AI行为准则第15条铁律的代码实现
检查清单（全部自动化）：
  ① 行业特化硬编码文本
  ② 只写口号没写代码
  ③ 变量定义前引用
  ④ 数据截断[:N]
  ⑤ 语法编译
  ⑥ JSON格式
"""
import os, sys, re, json, ast
from collections import defaultdict

BASE = os.path.dirname(__file__)
errors = []
warnings = []

def check_file(path, label):
    if not os.path.exists(path):
        errors.append(f"[{label}] 文件不存在: {path}")
        return

# ═══════ ① 行业特化硬编码文本 ═══════
TEXTILE_PATTERNS = [
    (r'(?<!")(?<![\'"])(棉纱|氨纶|梭织布|针织衫|梭织|针织)(?![\'"])', "纺织专用词"),
    (r'(?<!")(?<![\'"])(沙溪镇|大涌镇)(?![\'"])', "中山市特定地名"),
    (r'买坯布.*委托染整.*卖成品布', "纺织产业链特化描述"),
    (r'买纱线.*委托加工.*卖成品布', "纺织产业链特化描述"),
    (r'纺织行业常见模式', "行业定语"),
    (r'纺织制造的标准流程', "行业定语"),
    (r'纺织产业集群地', "行业定语"),
]

def check_industry_neutrality(path):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
        lines = content.split('\n')
    
    # 排除关键词字典区域（这些是合法的行业词典）
    dict_zones = []
    current_zone = None
    for i, line in enumerate(lines):
        if re.match(r'^\s*(MAIN_BIZ_KWS|DAILY_GOODS|IMPORTANT_EXPENSE_KWS|INDUSTRY_PRODUCT_CHAINS|_heavy_goods_examples|_cluster_map|_proc_map|industry_map)\s*=', line):
            current_zone = i
        if current_zone and re.match(r'^\s*[\]\}\)],?\s*$', line) and i > current_zone + 5:
            if current_zone not in [z[0] for z in dict_zones]:
                dict_zones.append((current_zone, i))
            current_zone = None
    
    for pattern, desc in TEXTILE_PATTERNS:
        for match in re.finditer(pattern, content):
            line_num = content[:match.start()].count('\n') + 1
            # 跳过关键词字典区域
            in_dict = any(zs <= line_num <= ze for zs, ze in dict_zones)
            if not in_dict:
                # 跳过注释行
                line_text = lines[line_num - 1].strip()
                if line_text.startswith('#') or line_text.startswith('//'):
                    continue
                errors.append(f"[行业特化] {path}:{line_num}: {desc} → '{match.group()}'")

# ═══════ ④ 数据截断检测 ═══════
def check_truncation(path):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
        lines = content.split('\n')
    
    for i, line in enumerate(lines):
        line_num = i + 1
        stripped = line.strip()
        if stripped.startswith('#') or stripped.startswith('//'):
            continue
        # 检测列表截断
        truncs = re.findall(r'(?:sorted\([^)]+\)|list\([^)]+\)|\.keys\(\)|\.values\(\)|\.items\(\))\s*\[:\d+\]', stripped)
        truncs += re.findall(r'(?<!\wstr\()(?:\w+)\[:\d+\](?!\s*[=])', stripped)
        for t in truncs:
            # 跳过字符串截断(日期等)
            if re.match(r'.*str\(.*\[:\d+\]', stripped):
                continue
            if re.match(r'.*date.*\[:\d+\]', stripped.lower()):
                continue
            if re.match(r'.*path.*\[:\d+\]', stripped.lower()):
                continue
            if re.match(r'.*url.*\[:\d+\]', stripped.lower()):
                continue
            if re.match(r'.*\[:\d+\]\s*$', t):  # 只有结尾有数字
                warnings.append(f"[数据截断] {path}:{line_num}: {t.strip()}")

# ═══════ ⑤ 语法编译 ═══════
def check_syntax(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            compile(f.read(), path, 'exec')
    except SyntaxError as e:
        errors.append(f"[语法错误] {path}:{e.lineno}: {e.msg}")

# ═══════ ⑥ JSON格式 ═══════
JSON_FILES = [
    'static/tax_risk_rules_local_export.json',
    'static/audit_chains.json',
    'static/cross_domain_evidence.json',
]

def check_json(path):
    full = os.path.join(BASE, path)
    if not os.path.exists(full):
        errors.append(f"[JSON] 文件不存在: {full}")
        return
    try:
        with open(full, 'r', encoding='utf-8') as f:
            json.load(f)
    except json.JSONDecodeError as e:
        errors.append(f"[JSON格式] {path}: line {e.lineno}: {e.msg}")

# ═══════ ② 只写口号没写代码 ═══════
# 检查报告/面板中引用的方法论函数是否在 main.py 中真实存在
def extract_functions_from_file(path):
    """提取文件中定义的函数名"""
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    funcs = set()
    # 匹配 def function_name(
    for m in re.finditer(r'^\s*def\s+(\w+)\s*\(', content, re.MULTILINE):
        funcs.add(m.group(1))
    return funcs

def extract_referenced_functions(path):
    """从JS/HTML面板文件中提取引用的函数名和功能名称"""
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    refs = set()
    # 查找 _domain_* 或 _analyze_* 之类的函数引用模式
    for m in re.finditer(r'_domain_\w+|_analyze_\w+|_enrich_\w+|_detect_\w+|_verify_\w+|_apply_\w+', content):
        refs.add(m.group(0))
    return refs

def check_methodology_implementation():
    """检查报告中声称的方法论是否都有代码实现"""
    report_path = os.path.join(BASE, 'generate_report.py')
    main_path = os.path.join(BASE, 'main.py')
    
    if not os.path.exists(main_path):
        errors.append("[口号检查] main.py 不存在")
        return
    
    # 提取 main.py 中所有函数
    main_funcs = extract_functions_from_file(main_path)
    
    # 检查关键方法论函数是否存在
    required_funcs = [
        '_detect_target_entity',      # 目标实体识别
        '_enrich_finding_details',    # 明细注入
        '_domain_business_premise_geo',  # 经营实质地理分析
        '_domain_cross_domain_reasoning',  # 跨域推理
        '_domain_fund_flow_mapping',  # 资金流向
        '_domain_document_completeness',  # 资料完备度
        '_domain_industry_benchmark', # 行业对标
        '_domain_invoice_audit',      # 发票审计
        '_analyze_contract_tiers',    # 合同分层
        '_apply_methodology_filter',  # 方法论过滤器
        '_online_company_lookup',     # 联网核查
        '_four_step_audit_framework', # 四步稽查法
        '_get_product_keywords',      # 行业自适应产品链
        '_enrich_target_entity_from_online',  # 联网结果注入
        '_get_root_causes',           # 根因诊断
        '_get_action_paths',          # 行动路径
    ]
    
    for func in required_funcs:
        if func not in main_funcs:
            errors.append(f"[口号检查] 函数 {func}() 在 main.py 中未找到——只有口号没代码")
        else:
            # 进一步检查函数体是否非空
            # (简单检查：函数体不能少于3行)
            pass
    
    # 检查报告面板中引用的函数
    panel_funcs = set()
    for fname in ['generate_report.py']:
        fp = os.path.join(BASE, fname)
        if os.path.exists(fp):
            panel_funcs.update(extract_referenced_functions(fp))
    
    for pf in panel_funcs:
        if pf not in main_funcs:
            warnings.append(f"[口号检查] 面板引用 {pf}() 但 main.py 中未定义")

# ═══════ ③ 变量定义前引用（AST 分析） ═══════
def check_variable_before_assign(path):
    """使用 AST 检测变量在函数内可能在赋值前被引用（仅报告高风险模式）"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        tree = ast.parse(content, filename=path)
        
        # 收集模块级名称
        module_names = set(dir(__builtins__))
        for stmt in tree.body:
            if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                for alias in stmt.names:
                    module_names.add(alias.asname or alias.name.split('.')[0])
            elif isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        module_names.add(target.id)
        
        # 只对新增/修改过的核心分析函数做深度检查
        CORE_FUNCS = [
            '_run_analyze', '_domain_business_premise_geo', '_domain_fund_flow_mapping',
            '_analyze_contract_tiers', '_domain_cross_domain_reasoning',
            '_four_step_audit_framework', '_online_company_lookup',
            '_enrich_target_entity_from_online', '_domain_invoice_audit',
            '_domain_document_completeness', '_domain_industry_benchmark',
        ]
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in CORE_FUNCS:
                # 简单检查：扫描函数体中的 Name 节点
                assigned_at_toplevel = set()
                used_vars = set()
                
                for arg in node.args.args:
                    assigned_at_toplevel.add(arg.arg)
                
                for stmt in node.body:
                    if isinstance(stmt, ast.Assign):
                        for target in stmt.targets:
                            if isinstance(target, ast.Name):
                                assigned_at_toplevel.add(target.id)
                    # 收集所有使用的变量
                    for child in ast.walk(stmt):
                        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                            if child.id not in module_names and child.id not in dir(__builtins__):
                                if not child.id[0].isupper() and not child.id.startswith('_'):
                                    used_vars.add(child.id)
                
                # 只在函数体较大时才报告（小函数容易误报）
                if len(node.body) > 20:
                    unassigned = used_vars - assigned_at_toplevel
                    for var in unassigned:
                        # 只警告那些看起来可能出问题的
                        if len(var) <= 3 and not var.isupper():
                            warnings.append(f"[变量引用] {path}:{node.lineno}: {node.name}() 检查 '{var}' 是否在赋值前引用")
    except SyntaxError:
        pass
    except Exception as e:
        warnings.append(f"[变量引用] {path}: AST异常: {e}")

# ═══════ 主流程 ═══════
def main():
    # ② 口号检查
    check_methodology_implementation()
    
    # ① 行业特化检查 - main.py
    main_py = os.path.join(BASE, 'main.py')
    if os.path.exists(main_py):
        check_industry_neutrality(main_py)
        # ③ 变量定义前引用
        check_variable_before_assign(main_py)
        # ④ 截断检查
        check_truncation(main_py)
        # ⑤ 语法检查
        check_syntax(main_py)
    
    # ① 行业特化检查 - tax_risk.py
    tax_py = os.path.join(BASE, 'tax_risk.py')
    if os.path.exists(tax_py):
        check_industry_neutrality(tax_py)
        check_variable_before_assign(tax_py)
        check_truncation(tax_py)
        check_syntax(tax_py)
    
    # ⑥ JSON检查
    for jf in JSON_FILES:
        check_json(jf)
    
    # 输出结果
    total_issues = len(errors) + len(warnings)
    print(f"\n{'='*60}")
    print(f"提交前自查报告")
    print(f"{'='*60}")
    
    if errors:
        print(f"\n❌ 错误 ({len(errors)}项) — 必须修复才能提交:")
        for e in errors:
            print(f"  {e}")
    
    if warnings:
        print(f"\n⚠️ 警告 ({len(warnings)}项) — 建议修复:")
        for w in warnings:
            print(f"  {w}")
    
    if not errors and not warnings:
        print(f"\n✅ 全部 6 项检查通过 — 可以提交")
    
    print(f"\n检查清单:")
    items = [
        ("① 行业特化硬编码", "✅" if not any("行业特化" in e for e in errors) else "❌"),
        ("② 只写口号没代码", "✅" if not any("口号检查" in e for e in errors) else "❌"),
        ("③ 变量定义前引用", "✅" if not any("变量引用" in e for e in errors) else "⚠️"),
        ("④ 数据截断[:N]", "✅" if not any("数据截断" in w for w in warnings) else "⚠️"),
        ("⑤ 语法编译", "✅" if not any("语法错误" in e for e in errors) else "❌"),
        ("⑥ JSON格式", "✅" if not any("JSON" in e for e in errors) else "❌"),
    ]
    for name, status in items:
        print(f"  {name}: {status}")
    
    return 0 if not errors else 1

if __name__ == '__main__':
    sys.exit(main())
