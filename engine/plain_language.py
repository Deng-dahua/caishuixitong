"""大白话翻译层——把稽查报告的专业术语转成通俗表达。

设计原则（2026-09-05，用户要求「报告编辑内容通俗易懂，用大白话来叙述」）：
1. 只做「翻译」，不改「事实」——数字、结论、风险定性原样保留；
2. 术语首次出现用「大白话（专业词）」或直接替换，让非财税专业的人也能读懂；
3. 替换顺序长词优先，避免子串冲突（如「销项发票」须先于「销项」替换）；
4. 不碰法规名称（《增值税暂行条例》等法律引用保持原文准确）；
5. 报告渲染层调用，规则引擎内部逻辑仍用原始文案（不影响匹配与裁决）。

用法：
    from engine.plain_language import to_plain
    text = to_plain(finding.get("detail", ""))
"""

from __future__ import annotations

import re

# ── 术语对照表：**只改「非行业」的词** ──────────────────────────
# ★★ 用户口径（2026-09-27）：**行业专有名词一律保持原样、直接用** ——
#    虚开 / 增值税 / 企业所得税 / 主营业务成本 / 销项发票 / 进项发票 / 勾稽 /
#    红字冲销 / 序时账 / 科目余额表 / 进项税额转出 … 行业读者本就看得懂，
#    改成大白话反而显得不专业。**加新词前先自问：这是"行业术语/专有名词"吗？是 → 不要加。**
#    本表**只**改「系统/报告语言」与「通用公文/口语词」（这些才是非财税读者看不懂的）。
TERM_MAP: list[tuple[str, str]] = [
    # 报告 / 系统用语
    ("监管盲区", "看不到的死角"),
    ("盲区", "死角"),
    ("疑点信号", "可疑信号"),
    # ★ 2026-09-27 移除 ("疑点", "可疑的地方")：**"疑点"是稽查术语、也是报告里的条目名**
    #   （用户称"疑点1/疑点2"），按「行业专有名词不改」应保留。保留它会产生
    #   "涉嫌**可疑的地方**的构成要件"这类被改坏的措辞。
    ("穿透", "顺藤摸瓜追查"),
    ("取数", "取出所需要的数据"),
    ("责令", "要求"),
    ("限期整改", "限期改正"),
    ("核验", "核实"),
    ("核查", "检查"),
    ("须按", "需要按"),
    ("须补", "需要补"),
    ("须逐", "需要逐"),
    ("已核身份证号", "已核实身份证号"),
    # 通用公文 / 口语词
    ("规避", "逃避"),
    ("空壳", "没有实际经营的公司"),
    ("补证", "补充资料"),
]

# ── 句式优化：固定模式 → 口语化 ──────────────────────────────
# （正则，从左到右应用；捕获组用 \\1 引用）
SENTENCE_PATTERNS: list[tuple[str, str]] = [
    (r"须(?P<verb>要求|核验|核实|核查|检查|提供|提交|补充|查明)(?P<rest>[^。；，]{1,40})",
     r"需要\g<verb>\g<rest>"),
    (r"不得仅凭(?P<rest>[^。；，]{1,40})",
     r"不能只凭\g<rest>"),
    (r"异常偏低", "明显偏低，不正常"),
    (r"异常偏高", "明显偏高，不正常"),
    (r"显著偏低", "明显偏低"),
    (r"显著偏高", "明显偏高"),
    (r"显著低于", "明显低于"),
    (r"显著高于", "明显高于"),
    (r"本项不列为税务风险", "这项不算税务风险"),
    (r"本项为(?P<rest>[^。；，]{1,30})", r"这项属于\g<rest>"),
    (r"未被核验", "没有被核实"),
    (r"无法核验", "没法核实"),
    (r"已核验", "已核实"),
    (r"待核验", "待核实"),
    (r"待核(?!验|实)", "待核实"),
]

# 法规引用保护：这些词段不做句式改写（保证法条引用准确）
_LEGAL_SHIELDS = ("《", "》", "国家税务总局公告", "财税", "财会", "中华人民共和国")


def _shield_legal(text: str) -> tuple[str, list[str]]:
    """把法规名称（《…》及公告文号）临时替换成占位符，防止误改。"""
    placeholders: list[str] = []
    def _rep(m: "re.Match[str]") -> str:
        placeholders.append(m.group(0))
        return f"\x00LEGAL{len(placeholders) - 1}\x00"
    shielded = re.sub(r"《[^》]{1,60}》|(?:财税|财会|国家税务总局公告)[〔\[（(]?\d{4}[〕\[)）]\d{1,4}号?", _rep, text)
    return shielded, placeholders


def _unshield_legal(text: str, placeholders: list[str]) -> str:
    for i, ph in enumerate(placeholders):
        text = text.replace(f"\x00LEGAL{i}\x00", ph)
    return text


# 文件名护罩：报告里出现的是**用户实际上传文件的名称**，是"可自证来源"的标识，
# 一旦翻译成大白话就与实际文件对不上（用户按名字找不到文件）→ 必须原样保留。
# 只护罩"以常见扩展名结尾的整段 token"，其前后的说明文字仍照常白话化。
_FILE_RE = re.compile(
    r"[\w\u4e00-\u9fff][^\s。；，、：:！？（）()【】\[\]《》\"'<>|]{0,90}?"
    r"\.(?:xlsx|xlsm|xls|csv|tsv|pdf|docx?|pptx?|txt|json|xml|zip|rar|7z|png|jpe?g|gif|bmp|ofd)",
    re.I,
)


def _shield_files(text: str) -> tuple[str, list[str]]:
    placeholders: list[str] = []
    def _rep(m: "re.Match[str]") -> str:
        placeholders.append(m.group(0))
        return f"\x00FILE{len(placeholders) - 1}\x00"
    return _FILE_RE.sub(_rep, text), placeholders


def _unshield_files(text: str, placeholders: list[str]) -> str:
    for i, ph in enumerate(placeholders):
        text = text.replace(f"\x00FILE{i}\x00", ph)
    return text


# ★ 长词优先（运行时强制，稳定排序）：保证「具体术语」先于其「短超串」命中。
#   例：两口径勾稽(5) 先于 勾稽(2)；账外收款(4) 先于 账外(2)；进项税额转出 先于 进项。
#   这样新增具体条目即便追加在表尾，也能真正生效，不会成为"死条目"。
_TERMS_SORTED = tuple(sorted(TERM_MAP, key=lambda kv: len(kv[0]), reverse=True))


def to_plain(text) -> str:
    """把一段专业表述翻译成大白话（数字与结论原样保留）。"""
    if not text or not isinstance(text, str):
        return text or ""
    # 1. 保护法规引用 与 文件名（真实来源标识不得翻译）
    shielded, legal = _shield_legal(text)
    shielded, files = _shield_files(shielded)
    # 2. 术语替换（长词优先：由 _TERMS_SORTED 强制，不依赖手写顺序）
    for term, plain in _TERMS_SORTED:
        if term in shielded:
            shielded = shielded.replace(term, plain)
    # 3. 句式优化
    for pattern, repl in SENTENCE_PATTERNS:
        shielded = re.sub(pattern, repl, shielded)
    # 4. 恢复文件名 与 法规引用
    result = _unshield_files(shielded, files)
    result = _unshield_legal(result, legal)
    # 5. 收尾清理：多余空格、重复标点、英文 or
    result = re.sub(r"\s+or\s+", " 或 ", result)
    result = re.sub(r"\s+", " ", result).strip()
    result = re.sub(r"([。；，])\1+", r"\1", result)
    return result


def to_plain_list(items) -> list[str]:
    """列表逐条翻译（用于 key_points / narrative_paragraphs）。"""
    if not items:
        return []
    out = []
    for it in items:
        if isinstance(it, str):
            out.append(to_plain(it))
        elif isinstance(it, dict) and "text" in it:
            out.append({**it, "text": to_plain(it.get("text", ""))})
        else:
            out.append(it)
    return out


# ── 递归「说人话」：用于报告最终出口对整份 report_data 统一生效 ──────────────────
# 键黑名单：这些键的值是前端依赖的枚举/标签（level / verdict / evidence_tier /
# terminal_state 等），禁止做术语替换，避免破坏前端渲染与既有测试。
_PLAIN_SKIP_KEYS = {
    "level", "terminal_state", "conclusion_grade", "evidence_tier",
    "verdict", "redline_id", "fact_id", "category", "evidence_status",
    "grade", "status", "type", "kind", "edition", "compilation_style",
}


def _plain_skip_key(k) -> bool:
    if not isinstance(k, str):
        return False
    if k in _PLAIN_SKIP_KEYS:
        return True
    for _suf in ("_tier", "_id", "_grade", "_level", "_verdict", "_status",
                "_category", "_type", "_kind"):
        if k.endswith(_suf):
            return True
    return False


def to_plain_obj(o, _key=None):
    """对字符串值做说人话替换（键黑名单保护前端枚举/标签）。非字符串原样返回。

    注：这是**单值**接口。对整份报告做"迭代 + 去环"的原地遍历请用
    `walk_strings_inplace`（见下），后者不会因循环引用/深层嵌套递归爆栈。
    """
    if isinstance(o, str):
        if _plain_skip_key(_key):
            return o
        return to_plain(o)
    return o


def walk_strings_inplace(root, fn):
    """迭代 + 去环地**原地**遍历 dict/list，对每个字符串值/元素应用 `fn(value, key_ctx)->str`。

    为什么不用递归：报告对象可能含**循环引用**与深层嵌套，递归遍历会抛
    `maximum recursion depth exceeded`，若被上层 try/except 静默吞掉，则整份报告的
    文本加工（标点规范化 / 说人话替换）**从未真正生效**（本项目实际踩过此坑）。
    本函数用显式栈 + id() 去环：覆盖全部可达文本、不重复处理共享子树、不陷入环。

    key_ctx：dict 子节点的键名；list 元素沿用其所属容器的键名（供键黑名单判断）。
    返回 root（同一对象，原地修改）。
    """
    seen = set()
    stack = [(root, None)]
    while stack:
        obj, key_ctx = stack.pop()
        if isinstance(obj, dict):
            if id(obj) in seen:
                continue
            seen.add(id(obj))
            for k, v in list(obj.items()):
                if isinstance(v, str):
                    obj[k] = fn(v, k)
                elif isinstance(v, (dict, list)):
                    stack.append((v, k))
        elif isinstance(obj, list):
            if id(obj) in seen:
                continue
            seen.add(id(obj))
            for i, v in enumerate(list(obj)):
                if isinstance(v, str):
                    obj[i] = fn(v, key_ctx)
                elif isinstance(v, (dict, list)):
                    stack.append((v, key_ctx))
    return root


def validate_plain_map():
    """不变量自检（写错映射表时 import 即报错）：

    ① 每条「大白话」不得再包含**原触发词**（否则自触发、破坏幂等）；
    ② 每条「大白话」不得包含**任何其它触发词**（否则会在输出里残留专业术语，
       或按排序被二次替换 —— 实测踩过：`红冲→开红字冲销` 输出里残留"红字冲销"）。
    """
    triggers = [j for j, _ in TERM_MAP if j]
    bad = []
    for jargon, plain in TERM_MAP:
        for t in triggers:
            if t and t in plain:
                bad.append((jargon, plain, t))
    if bad:
        raise AssertionError(
            "plain_language 映射表违规（大白话含触发词，会残留/二次替换）: %r" % bad[:20])
    return True


if __debug__:
    validate_plain_map()
