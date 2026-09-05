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

# ── 术语对照表：专业词 → 大白话 ──────────────────────────────
# 顺序即优先级：长的、具体的在前，短的、宽泛的在后。
TERM_MAP: list[tuple[str, str]] = [
    # 发票与进销项
    ("销项发票", "开出去的发票"),
    ("销项收入", "开票收入"),
    ("销项", "开出去的发票"),
    ("进项发票", "收进来的进货发票"),
    ("进项税额转出", "已抵扣的税要转出补税"),
    ("进项税额", "进货发票上的税额"),
    ("进项税", "进货的税"),
    ("进项", "进货发票"),
    ("进销", "进货和销货"),
    ("进销存", "进货、销售、库存"),
    ("留抵税额", "没用完的进项税"),
    ("留抵", "没用完的进项税"),
    # 核对与流程
    ("勾稽", "互相对账核对"),
    ("票证", "发票和凭证"),
    ("核验", "核实"),
    ("核查", "检查"),
    ("穿透", "顺藤摸瓜追查"),
    ("取数", "取数据"),
    ("责令", "要求"),
    ("限期整改", "限期改正"),
    ("疑点信号", "可疑信号"),
    ("疑点", "可疑的地方"),
    ("红冲", "开红字发票冲销"),
    ("须按", "需要按"),
    ("须补", "需要补"),
    ("须逐", "需要逐"),
    ("已核身份证号", "已核实身份证号"),
    # 资金与人
    ("监管盲区", "税务看不到的死角"),
    ("盲区", "死角"),
    ("私户", "个人银行账户"),
    ("对公账户", "公司银行账户"),
    ("实际控制人", "老板（实际控制人）"),
    ("人均产值", "平均每人创造的收入"),
    ("税基", "计税的工资基数"),
    ("全额扣缴", "足额代扣个税"),
    ("全员全额", "全员足额"),
    # 违规类型
    ("隐匿收入", "隐瞒不报的收入"),
    ("账外经营", "不入账的经营"),
    ("账外", "不入账的"),
    ("虚开发票", "虚开发票"),
    ("虚开", "虚开发票"),
    ("空壳", "空壳公司"),
    ("视同销售", "视同销售（按卖货一样交税）"),
    ("拆分", "拆分"),
    ("规避", "逃避"),
    # 经营与核算
    ("产能", "生产能力"),
    ("能耗", "水电能耗"),
    ("委外加工", "委托外厂加工"),
    ("委外", "委托外厂加工"),
    ("BOM", "物料清单（BOM）"),
    ("税负率", "实际缴税比例"),
    ("毛利率", "毛利率"),
    ("存货", "库存"),
    ("往来款", "往来账"),
    ("补缴", "补交"),
    ("申报表", "纳税申报表"),
    # 五流与证据
    ("货物流", "货物流动"),
    ("资金流", "资金流动"),
    ("发票流", "发票流转"),
    ("合同流", "合同流转"),
    ("三流一致", "发票、资金、货物三样对得上"),
    ("三流合一", "发票、资金、货物三样对得上"),
    ("四流一致", "发票、资金、货物、合同四样对得上"),
    ("五流一致", "发票、资金、货物、合同、物流五样对得上"),
    ("五流合一", "发票、资金、货物、合同、物流五样对得上"),
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


def to_plain(text) -> str:
    """把一段专业表述翻译成大白话（数字与结论原样保留）。"""
    if not text or not isinstance(text, str):
        return text or ""
    # 1. 保护法规引用
    shielded, legal = _shield_legal(text)
    # 2. 术语替换（长词优先已由 TERM_MAP 顺序保证）
    for term, plain in TERM_MAP:
        if term in shielded:
            shielded = shielded.replace(term, plain)
    # 3. 句式优化
    for pattern, repl in SENTENCE_PATTERNS:
        shielded = re.sub(pattern, repl, shielded)
    # 4. 恢复法规引用
    result = _unshield_legal(shielded, legal)
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
