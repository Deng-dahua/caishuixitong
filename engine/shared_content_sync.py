# ==================== 共享内容同步引擎 ====================
# 
# 跨模块内容一致性标准 —— 引擎铁律第七条
# 
# 规则：同一内容在多个模块中出现时，必须保持完全一致。
# 每个共享内容块有且仅有一个权威源，其他模块为依赖副本。
# 权威源变更后，--sync 自动将依赖副本更新为与权威源一致。
#
# 使用方式：
#   1. 定义共享块：static/shared_content_map.json
#   2. 运行同步：python audit_consistency.py --sync
#   3. 每次start.bat启动时自动执行
#   4. git pre-commit hook 自动执行
#
# 代码位置：audit_consistency.py → sync_shared_content()
# 数据位置：static/shared_content_map.json

import json
import re
import hashlib
import os
from pathlib import Path
from typing import Dict, List, Tuple


ROOT = Path(__file__).parent.parent  # engine/ 的父目录 = 项目根目录
MAP_FILE = ROOT / "static" / "shared_content_map.json"


def load_text_sync_blocks() -> List[Dict]:
    """加载text_sync类共享块（逐字同步）"""
    if not MAP_FILE.exists():
        return []
    with open(MAP_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("text_sync_blocks", data.get("shared_blocks", []))


def load_concept_links() -> List[Dict]:
    """加载concept_link类共享概念（验证关联存在）"""
    if not MAP_FILE.exists():
        return []
    with open(MAP_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("concept_links", [])


def compute_hash(text: str) -> str:
    """计算文本的MD5哈希"""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def extract_handbook_chapter_body(file_content: str, label: str) -> Tuple[str, str, str, str]:
    """从手册文件中提取指定章节的标签/标题/正文"""
    # 手册格式: ['封面','编号格式+报告日期','正文...']
    escaped = re.escape(label)
    pattern = r"\['?" + escaped + r"'?,\s*'([^']*)',\s*'([^']*)'\]"
    match = re.search(pattern, file_content)
    if not match:
        return None, None, None, None
    return label, match.group(1), match.group(2), match.group(0)


def extract_standards_chapter_body(file_content: str, label: str) -> Tuple[str, str, str, str]:
    """从报告编制要求文件中提取指定章节的标签/标题/正文"""
    # 格式: {label:'封面',title:'编号格式+报告日期',body:'正文...'}
    escaped = re.escape(label)
    pattern = (
        r"\{label:'" + escaped + r"',\s*title:'([^']*)',\s*body:'([^']*)'\}"
    )
    match = re.search(pattern, file_content)
    if not match:
        return None, None, None, None
    return label, match.group(1), match.group(2), match.group(0)


def extract_chapter(file_content: str, label: str, file_path: str) -> Tuple[str, str, str, str]:
    """根据文件类型提取章节内容"""
    if "tax-auditor-handbook" in file_path:
        return extract_handbook_chapter_body(file_content, label)
    elif "tax-report-standards" in file_path:
        return extract_standards_chapter_body(file_content, label)
    return None, None, None, None


def sync_shared_content() -> List[str]:
    """
    同步共享内容块：
    1. 读取shared_content_map.json
    2. 从权威源提取内容
    3. 对比依赖模块的内容
    4. 不一致则自动更新依赖模块
    返回同步日志列表
    """
    blocks = load_text_sync_blocks()
    if not blocks:
        return ["无逐字同步块定义"]

    log = []
    synced_count = 0

    for block in blocks:
        bid = block["id"]
        source_file = ROOT / block["source_file"]

        if not source_file.exists():
            log.append(f"⚠ {bid}: 权威源文件不存在 {source_file}")
            continue

        # 读取权威源
        with open(source_file, "r", encoding="utf-8") as f:
            source_content = f.read()

        src_label, src_title, src_body, src_full = extract_chapter(
            source_content, block["label"], str(source_file)
        )

        if not src_body:
            log.append(f"⚠ {bid}: 无法从权威源提取 [{block['label']}]")
            continue

        src_hash = compute_hash(src_body)

        # 对比每个依赖模块
        for dep_path in block.get("dependent_files", []):
            dep_file = ROOT / dep_path

            if not dep_file.exists():
                log.append(f"⚠ {bid}: 依赖文件不存在 {dep_path}")
                continue

            with open(dep_file, "r", encoding="utf-8") as f:
                dep_content = f.read()

            dep_label, dep_title, dep_body, dep_full = extract_chapter(
                dep_content, block["label"], str(dep_file)
            )

            if not dep_body:
                log.append(f"⚠ {bid}: 无法从依赖模块提取 [{block['label']}] ({dep_path})")
                continue

            dep_hash = compute_hash(dep_body)

            if src_hash == dep_hash:
                log.append(f"✅ {bid}: {block['label']} 一致 ({len(src_body)}字)")
                continue

            # 不一致——需要同步
            log.append(f"🔄 {bid}: {block['label']} 不一致，正在同步... ({len(dep_body)}→{len(src_body)}字)")

            # 替换依赖文件中的正文
            # 手册格式需重建完整数组项
            if "tax-auditor-handbook" in dep_path:
                new_full = f"['{src_label}','{src_title}','{src_body}']"
            else:
                new_full = f"{{label:'{src_label}',title:'{src_title}',body:'{src_body}'}}"

            dep_content = dep_content.replace(dep_full, new_full, 1)
            with open(dep_file, "w", encoding="utf-8") as f:
                f.write(dep_content)

            synced_count += 1

    if synced_count > 0:
        log.append(f"\n✅ 共享内容同步完成: {synced_count}个块已更新")
    else:
        log.append("\n✅ 所有共享内容块一致，无需同步")

    return log


def rebuild_shared_map() -> List[str]:
    """
    重新扫描两个文件，自动生成共享内容映射表。
    当新增共享内容时调用此函数重建映射。
    """
    log = []
    rs_file = ROOT / "static" / "js" / "tax-report-standards.js"
    hb_file = ROOT / "static" / "js" / "tax-auditor-handbook.js"

    for f in [rs_file, hb_file]:
        if not f.exists():
            log.append(f"❌ 文件不存在: {f}")
            return log

    with open(str(rs_file), "r", encoding="utf-8") as f:
        rs_content = f.read()
    with open(str(hb_file), "r", encoding="utf-8") as f:
        hb_content = f.read()

    # 提取章节
    hb_start = hb_content.find('id="hb-s5"')
    hb_end = hb_content.find('id="hb-s6"', hb_start)
    if hb_end < 0:
        return ["❌ 无法找到手册第5章边界"]

    hb_chaps = re.findall(
        r"\['([^']+)','([^']+)','([^']+)'\]",
        hb_content[hb_start:hb_end]
    )
    rs_chaps = re.findall(
        r"\{label:'([^']+)',\s*title:'([^']+)',\s*body:'([^']+)'\}",
        rs_content
    )

    shared_blocks = []
    for hc, rc in zip(hb_chaps, rs_chaps):
        shared_blocks.append({
            "id": f"report_chapter_{hc[0]}",
            "label": hc[0],
            "title": hc[1],
            "source_file": "static/js/tax-report-standards.js",
            "dependent_files": ["static/js/tax-auditor-handbook.js"],
            "content_hash": compute_hash(rc[2]),
            "content_length": len(rc[2])
        })

    config = {
        "version": "2.0",
        "description": "跨模块共享内容映射——text_sync_blocks逐字同步，concept_links关联验证。",
        "text_sync_blocks": shared_blocks,
        "concept_links": load_concept_links()  # 保留已有概念链接
    }

    with open(str(MAP_FILE), "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    log.append(f"✅ 重建共享内容映射: {len(shared_blocks)}个共享块")
    for sb in shared_blocks:
        log.append(f"  {sb['id']}: {sb['source_file']} → {sb['dependent_files']}")

    return log


def verify_shared_content() -> Tuple[bool, List[str]]:
    """
    静默验证共享内容一致性（不修改文件）。
    检查两类：text_sync（逐字哈希） + concept_link（关键词存在）。
    返回(全部一致, 日志列表)
    """
    log = []
    all_ok = True

    # ═══ 第一类：text_sync 逐字验证 ═══
    blocks = load_text_sync_blocks()

    for block in blocks:
        bid = block["id"]
        source_file = ROOT / block["source_file"]
        if not source_file.exists():
            continue

        with open(source_file, "r", encoding="utf-8") as f:
            source_content = f.read()

        _, _, src_body, _ = extract_chapter(source_content, block["label"], str(source_file))
        if not src_body:
            continue

        src_hash = compute_hash(src_body)

        for dep_path in block.get("dependent_files", []):
            dep_file = ROOT / dep_path
            if not dep_file.exists():
                continue

            with open(dep_file, "r", encoding="utf-8") as f:
                dep_content = f.read()

            _, _, dep_body, _ = extract_chapter(dep_content, block["label"], str(dep_file))
            if not dep_body:
                continue

            dep_hash = compute_hash(dep_body)

            if src_hash != dep_hash:
                log.append(
                    f"❌ [{block['label']}] text_sync不一致: "
                    f"{block['source_file']}({len(src_body)}字) ≠ {dep_path}({len(dep_body)}字)"
                )
                all_ok = False

    # ═══ 第二类：concept_link 存在性验证 ═══
    links = load_concept_links()

    for link in links:
        lid = link["id"]
        lname = link["name"]
        source = link.get("source_module", "")

        # 检查源模块是否存在
        source_path = extract_file_from_module_ref(source)
        if source_path and not os.path.exists(source_path):
            log.append(f"⚠ [{lname}] 权威源文件不存在: {source}")
            all_ok = False

        # 检查每个关联模块
        for mod_ref in link.get("linked_modules", []):
            mod_path = extract_file_from_module_ref(mod_ref)
            if mod_path and not os.path.exists(mod_path):
                log.append(f"⚠ [{lname}] 关联模块文件不存在: {mod_ref}")

    # 添加摘要
    text_count = len(blocks)
    concept_count = len(links)
    log.insert(0, f"📋 共享内容审计: {text_count}个text_sync块 + {concept_count}个concept_link")

    return all_ok, log


def extract_file_from_module_ref(ref: str) -> str:
    """从模块引用中提取文件路径，如 '手册§3' → 'static/js/tax-auditor-handbook.js'"""
    
    # 已经是文件路径的
    if ref.endswith('.py') or ref.endswith('.js') or ref.endswith('.json'):
        path = ref.split('#')[0].split(' ')[0]
        full = os.path.join(str(ROOT), path)
        return full if os.path.exists(full) else ""
    
    # Module name references
    name_map = {
        '手册': 'static/js/tax-auditor-handbook.js',
        '编制要求': 'static/js/tax-report-standards.js',
        '全链路质量保障': 'static/js/tax-pipeline-pages.js',
        '分析链': 'static/js/tax-pipeline-pages.js',
        '方法论过滤器': 'static/js/tax-pipeline-pages.js',
        'AI行为准则': 'static/js/tax-pipeline-pages.js',
        '引擎仪表盘': 'static/js/tax-engine-dashboard.js',
        '审核模板': 'static/js/tax-feedback-template.js',
        '引擎记忆': 'engine/memory.py',
        '域分析引擎': 'engine/domain_analysis.py',
        '管线引擎': 'engine/pipeline.py',
        '系统配置': 'static/system_config.json',
    }
    
    for name, path in name_map.items():
        if name in ref:
            return os.path.join(str(ROOT), path)
    
    return ""
