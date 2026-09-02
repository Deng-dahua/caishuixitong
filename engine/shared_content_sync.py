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


def extract_handbook_chapter_body_legacy(file_content: str, label: str) -> Tuple[str, str, str, str]:
    """【2026-08-26 审计修复前的旧提取器，内容保留备查】
    旧手册格式: ['封面','编号格式+报告日期','正文...']（三元素数组）。
    现行 tax-auditor-handbook.js 已改为二元数组 ['标题','正文']，本提取器不再匹配，
    由 extract_handbook_chapter_body 取代。"""
    escaped = re.escape(label)
    pattern = r"\['?" + escaped + r"'?,\s*'([^']*)',\s*'([^']*)'\]"
    match = re.search(pattern, file_content)
    if not match:
        return None, None, None, None
    return label, match.group(1), match.group(2), match.group(0)


def extract_standards_chapter_body_legacy(file_content: str, label: str) -> Tuple[str, str, str, str]:
    """【2026-08-26 审计修复前的旧提取器，内容保留备查】
    旧格式: {label:'封面',title:'编号格式+报告日期',body:'正文...'}。
    现行 tax-report-standards.js 已改为 sections 数组（id/kicker/title/summary/body 模板字面量），
    本提取器不再匹配，由 extract_standards_chapter_body 取代。"""
    escaped = re.escape(label)
    pattern = (
        r"\{label:'" + escaped + r"',\s*title:'([^']*)',\s*body:'([^']*)'\}"
    )
    match = re.search(pattern, file_content)
    if not match:
        return None, None, None, None
    return label, match.group(1), match.group(2), match.group(0)


def extract_handbook_chapter_body(file_content: str, label: str) -> Tuple[str, str, str, str]:
    """从手册文件中提取指定章节（2026-08-26 按现行格式重写，P0-5）。
    现行 tax-auditor-handbook.js 格式：chapters 二元数组 ['标题','正文']。
    label 与标题完全相等或为其前缀/子串时命中。"""
    pattern = r"\[\s*'([^']+)'\s*,\s*'((?:[^'\\]|\\.)*)'\s*\]"
    for match in re.finditer(pattern, file_content):
        title, body = match.group(1), match.group(2)
        if title.strip() == label.strip() or title.strip().startswith(label.strip()) or label.strip() in title:
            return label, title, body, match.group(0)
    return None, None, None, None


def extract_standards_chapter_body(file_content: str, label: str) -> Tuple[str, str, str, str]:
    """从报告编制要求文件中提取指定章节（2026-08-26 按现行格式重写，P0-5）。
    现行 tax-report-standards.js 格式：sections 数组
    {id:'rpt-N', kicker:'NN', title:'标题', summary:'...', body:`模板字面量`}。
    label 可按节 id（如 rpt-3）、标题全文或标题子串匹配。"""
    pattern = (
        r"\{\s*id:\s*'([^']+)'\s*,\s*kicker:\s*'([^']*)'\s*,\s*title:\s*'([^']*)'"
        r"[\s\S]*?body:\s*`([\s\S]*?)`\s*,?\s*\}"
    )
    for match in re.finditer(pattern, file_content):
        sec_id, _kicker, title, body = match.groups()
        if label.strip() == sec_id or label.strip() == title.strip() or label.strip() in title:
            return label, title, body, match.group(0)
    return None, None, None, None


def extract_chapter(file_content: str, label: str, file_path: str) -> Tuple[str, str, str, str]:
    """根据文件类型提取章节内容。
    2026-08-26：先按现行格式提取；未命中时回落旧格式提取器（兼容历史结构），
    仍不命中则返回空四元组，由调用方显式记录失败（不得静默跳过）。"""
    if "tax-auditor-handbook" in file_path:
        result = extract_handbook_chapter_body(file_content, label)
        if result[2]:
            return result
        return extract_handbook_chapter_body_legacy(file_content, label)
    elif "tax-report-standards" in file_path:
        result = extract_standards_chapter_body(file_content, label)
        if result[2]:
            return result
        return extract_standards_chapter_body_legacy(file_content, label)
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

    # 2026-08-26 审计修复（P0-5）：原版依赖 id="hb-s5" 死锚点与旧三元素数组/旧
    # {label,title,body} 结构，在现行两文件上必然失败。现按现行结构扫描：
    # 报告编制要求 sections（rpt-N）为权威源候选；手册 chapters（二元数组）为依赖候选。
    hb_chaps = re.findall(r"\[\s*'([^']+)'\s*,\s*'((?:[^'\\]|\\.)*)'\s*\]", hb_content)
    rs_chaps = re.findall(
        r"\{\s*id:\s*'(rpt-\d+)'\s*,\s*kicker:\s*'([^']*)'\s*,\s*title:\s*'([^']*)'"
        r"[\s\S]*?body:\s*`([\s\S]*?)`\s*,?\s*\}",
        rs_content
    )

    shared_blocks = []
    hb_titles = {t.strip(): (t, b) for t, b in hb_chaps}
    for sec_id, _kicker, title, body in rs_chaps:
        # 只有手册中存在同名标题章节时才建立逐字同步关系，否则如实标注无依赖
        matched = hb_titles.get(title.strip())
        shared_blocks.append({
            "id": f"report_section_{sec_id}",
            "label": title,
            "title": title,
            "source_file": "static/js/tax-report-standards.js",
            "dependent_files": ["static/js/tax-auditor-handbook.js"] if matched else [],
            "status": "active" if matched else "no_dependent",
            "content_hash": compute_hash(body),
            "content_length": len(body)
        })

    # 保留既有映射中无法在新结构下建立的块（不删除内容，迁入 legacy 备查）
    legacy_blocks = []
    for block in load_text_sync_blocks():
        if block.get("id") not in {b["id"] for b in shared_blocks}:
            block["status"] = "legacy_unmapped"
            block.setdefault("note", "2026-08-26 重建映射时无法按现行文件结构建立，保留备查")
            legacy_blocks.append(block)

    config = {
        "version": "2.1",
        "description": "跨模块共享内容映射——text_sync_blocks逐字同步，concept_links关联验证。2026-08-26按现行文件结构重建。",
        "text_sync_blocks": shared_blocks,
        "legacy_text_sync_blocks": legacy_blocks,
        "concept_links": load_concept_links()  # 保留已有概念链接
    }

    with open(str(MAP_FILE), "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    log.append(f"✅ 重建共享内容映射: {len(shared_blocks)}个共享块（含无依赖标注），{len(legacy_blocks)}个历史块保留备查")
    for sb in shared_blocks:
        log.append(f"  {sb['id']}: {sb['source_file']} → {sb['dependent_files']} [{sb['status']}]")

    return log


def verify_shared_content() -> Tuple[bool, List[str]]:
    """
    静默验证共享内容一致性（不修改文件）。
    检查两类：text_sync（逐字哈希） + concept_link（关键词存在）。
    返回(全部一致, 日志列表)

    2026-08-26 审计修复（P0-5）：提取失败/文件缺失不再静默 continue——
    活动块（未标记 legacy_unmapped）的任何失败都计入 all_ok=False 并输出 ❌ 日志；
    标记为 legacy_unmapped 的历史遗留块输出显式 ⚠ 说明，不计入通过、也不计入失败。
    """
    log = []
    all_ok = True
    verified_count = 0
    failed_count = 0
    legacy_count = 0

    # ═══ 第一类：text_sync 逐字验证 ═══
    blocks = load_text_sync_blocks()

    for block in blocks:
        bid = block["id"]
        is_legacy = block.get("status") == "legacy_unmapped"
        source_file = ROOT / block["source_file"]
        if not source_file.exists():
            if is_legacy:
                log.append(f"⚠ {bid}: 历史遗留块（{block['label']}），权威源文件不存在 {source_file}")
                legacy_count += 1
            else:
                log.append(f"❌ {bid}: 权威源文件不存在 {source_file}")
                all_ok = False
                failed_count += 1
            continue

        with open(source_file, "r", encoding="utf-8") as f:
            source_content = f.read()

        _, _, src_body, _ = extract_chapter(source_content, block["label"], str(source_file))
        if not src_body:
            if is_legacy:
                log.append(f"⚠ {bid}: 历史遗留块（{block['label']}），现行文件结构中无对应章节，待重新映射")
                legacy_count += 1
            else:
                log.append(f"❌ {bid}: 无法从权威源提取 [{block['label']}]（提取失败不得视为一致）")
                all_ok = False
                failed_count += 1
            continue

        src_hash = compute_hash(src_body)

        if not block.get("dependent_files"):
            # 2026-08-26：无依赖模块的块如实登记，不计入"一致"通过
            log.append(f"⚠ {bid}: [{block['label']}] 无依赖模块（{block.get('status', 'active')}），仅登记权威源 {len(src_body)}字，不发生逐字同步")
            continue

        for dep_path in block.get("dependent_files", []):
            dep_file = ROOT / dep_path
            if not dep_file.exists():
                if is_legacy:
                    log.append(f"⚠ {bid}: 历史遗留块（{block['label']}），依赖文件不存在 {dep_path}")
                    legacy_count += 1
                else:
                    log.append(f"❌ {bid}: 依赖文件不存在 {dep_path}")
                    all_ok = False
                    failed_count += 1
                continue

            with open(dep_file, "r", encoding="utf-8") as f:
                dep_content = f.read()

            _, _, dep_body, _ = extract_chapter(dep_content, block["label"], str(dep_file))
            if not dep_body:
                if is_legacy:
                    log.append(f"⚠ {bid}: 历史遗留块（{block['label']}），依赖模块中无对应章节 ({dep_path})")
                    legacy_count += 1
                else:
                    log.append(f"❌ {bid}: 无法从依赖模块提取 [{block['label']}] ({dep_path})")
                    all_ok = False
                    failed_count += 1
                continue

            dep_hash = compute_hash(dep_body)

            if src_hash != dep_hash:
                log.append(
                    f"❌ [{block['label']}] text_sync不一致: "
                    f"{block['source_file']}({len(src_body)}字) ≠ {dep_path}({len(dep_body)}字)"
                )
                all_ok = False
                failed_count += 1
            else:
                verified_count += 1

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

    # 添加摘要（2026-08-26：如实披露通过/失败/遗留三类计数，不再只报总数）
    text_count = len(blocks)
    concept_count = len(links)
    log.insert(0, f"📋 共享内容审计: {text_count}个text_sync块（一致{verified_count} 失败{failed_count} 历史遗留{legacy_count}） + {concept_count}个concept_link")

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
