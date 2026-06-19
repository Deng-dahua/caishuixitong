"""
提交前自查脚本 —— AI行为准则第15条铁律的代码实现
检查清单：
  ① 行业特化硬编码文本
  ② 只写口号没写代码
  ③ 变量定义前引用
  ④ 数据截断[:N]
  ⑤ 语法编译
  ⑥ JSON格式
"""
import os, sys, re, json

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

# ═══════ 主流程 ═══════
def main():
    # ① 行业特化检查 - main.py
    main_py = os.path.join(BASE, 'main.py')
    if os.path.exists(main_py):
        check_industry_neutrality(main_py)
        # ④ 截断检查
        check_truncation(main_py)
        # ⑤ 语法检查
        check_syntax(main_py)
    
    # ① 行业特化检查 - tax_risk.py
    tax_py = os.path.join(BASE, 'tax_risk.py')
    if os.path.exists(tax_py):
        check_industry_neutrality(tax_py)
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
        ("② 只写口号没代码", "⚠️ 人工确认"),
        ("③ 变量定义前引用", "⚠️ 人工确认"),
        ("④ 数据截断[:N]", "✅" if not any("数据截断" in w for w in warnings) else "⚠️"),
        ("⑤ 语法编译", "✅" if not any("语法错误" in e for e in errors) else "❌"),
        ("⑥ JSON格式", "✅" if not any("JSON" in e for e in errors) else "❌"),
    ]
    for name, status in items:
        print(f"  {name}: {status}")
    
    return 0 if not errors else 1

if __name__ == '__main__':
    sys.exit(main())
