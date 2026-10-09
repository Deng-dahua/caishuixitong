# -*- coding: utf-8 -*-
"""报告编排 —— **专项比对 → 疑点** 的归属映射（唯一权威）。

## 为什么要有这张表（用户 2026-10-05 追问）

> 「这些内容是什么意思？你认为这些内容就不能融入到第二章吗？」
> 「这个内容是什么意思？就不能融入相关的板块中去？」

报告里 `bank_flow_report`（银行流水比对）、`revenue_authenticity_report`
（收入真实性三维度）、`two_tax_report`（两税收入差异）、`fund_loop_report`
（跨企业资金回流）、`cross_enterprise_report`（跨企业关联图谱）、
`false_invoice_report`（虚开风险网络）、`cost_recon_detail`（成本两口径勾稽）
**原本全部平铺在报告末尾的"专项能力比对"一节** —— 但它们各自讲的就是
**某一个疑点**的深度分析：

  · 疑点3「银行收款大于申报收入」的论证依据 = 银行流水比对 + 收入真实性三维度；
  · 疑点25「表间勾稽不一致」的依据 = 两税收入差异比对；
  · 疑点18「资金回流」的依据 = 跨企业资金回流闭环比对；
  · 疑点19「关联交易异常」的依据 = 跨企业关联图谱 + 虚开风险网络；
  · 疑点15「成本列支证据不足」的依据 = 主营业务成本两口径勾稽。

⇒ 应**融入对应疑点**（读者在一个地方看到"结论 + 全部论证"），
  而不是让读者在末尾一节里自己去对应"哪段是给哪个疑点的"。

## 使用纪律
- 新增同类专项报告只在本表加一行（`报告键: 目标疑点标题关键词`）。
- 映射**按标题关键词**匹配，不按顺序、不按下标 —— 顺序会随数据变。
- 匹配不到目标的报告（如 `external_verify_report` 外部核实通道、
  `capability_boundary` 能力边界）**保持独立**，它们讲的不是某个疑点。
"""

from typing import Dict, List, Tuple

# ── 专项报告键 → 目标疑点标题关键词（唯一权威）──────────────────────
# ⚠ 关键词取疑点标题里的**独有词**，避免误挂（详见每条注释）
SPECIAL_TO_PROBLEM: Dict[str, str] = {
    # 银行流水比对 + 收入真实性 → 疑点3「银行收款大于申报收入：存在账外收入嫌疑」
    "bank_flow_report": "银行收款大于申报收入",
    "revenue_authenticity_report": "银行收款大于申报收入",
    # 两税收入差异 → 疑点25「表间勾稽四方比对不一致」
    "two_tax_report": "表间勾稽四方比对",
    # 跨企业资金回流闭环 → 疑点18「待核线索：资金回流与公私混同检测」
    "fund_loop_report": "资金回流与公私混同",
    # 跨企业关联图谱 + 虚开网络 → 疑点19「关联交易异常：购销闭环与六员重叠」
    "cross_enterprise_report": "关联交易异常",
    "false_invoice_report": "关联交易异常",
    # 成本两口径勾稽 → 疑点15「成本列支的资金与负债证据不足」
    "cost_recon_detail": "成本列支的资金与负债证据不足",
    # ★ 2026-10-06 更正旧注释：`input_voucher_report`（进项异常凭证/应转出未转出）
    #   自 2026-10-05 起已由 `STANDALONE_RISK_REPORTS` 立为**独立风险事项**
    #   「进项异常凭证：不得抵扣用途未作进项转出」⇒ 它不再是"无对应疑点的专题"，
    #   而是**本身就是风险事项**，故仍**不**进本表（本表是"底稿并入疑点"的映射）。
    #   它对应的**询问主题**归属见 `QUESTION_THEME_TO_PROBLEM`。
}

# ── 保持独立的报告/区块（它们讲的不是某一个疑点）────────────────────
STANDALONE_KEYS: Tuple[str, ...] = (
    "external_verify_report",   # 外部核实通道（工商/舆情）—— 讲"系统能查到什么"
    "capability_boundary",      # 系统能力边界 —— 讲"系统查不到什么"
    "inspection_questions_report",  # 询问清单 —— 讲"要企业答复什么"（跨全部疑点）
    "industry_benchmark_report",    # 行业对标 —— 讲"与行业比处于什么位置"（跨全部）
    "related_party_report",         # 关联方穿透 —— 已在 cross_enterprise_report 覆盖
)


# ── **内部工作底稿块**：不呈现给企业 ⇒ 不适用"面向企业正文"的措辞口径 ────────
#   ★ 2026-10-06：产物级"禁用模糊词"扫描原先**全量**扫描 `enterprise_readable_report`，
#     于是把内部底稿里的「待核」用语也判成 ERROR（实测 225 处里 12 处来自这里）。
#     `inspector_reasoning` 是**系统推理底稿**，在 `static/js/**` 与
#     `scripts/_render_report_html.py` 中**零引用**（grep 可证）—— 它不是给企业看的。
#   ⚠ 纪律：**一旦给某个块加了渲染器，必须同时把它从本表移除**（否则措辞口径失守）。
#   ⚠ 本表**不是**"不想改的挡箭牌"：只收"确定不呈现"的块，且每条注明理由。
INTERNAL_BLOCKS: Tuple[str, ...] = (
    "inspector_reasoning",   # 内部推理底稿（inspector_reasoning 结构）：无渲染器引用
)


# ── 专项报告的显示标题（报告层缺 title 时的兜底，唯一权威）────────────
#   ⚠ 实测 `cost_recon_detail` **没有 title 键**（它的结构是按品名分类的明细），
#     直接取 `rep["title"]` 会得到空标题 ⇒ 读着像"本项专项比对："后面没内容。
SPECIAL_TITLES: Dict[str, str] = {
    "cost_recon_detail": "主营业务成本两口径勾稽（发票口径 ↔ 账面口径）",
    "bank_flow_report": "银行流水（资金流）比对",
    "revenue_authenticity_report": "收入真实性（账外收入嫌疑）三维度验证",
    "two_tax_report": "增值税收入 与 企业所得税收入差异比对",
    "fund_loop_report": "跨企业资金回流闭环比对",
    "cross_enterprise_report": "跨企业关联交易闭环比对",
    "false_invoice_report": "虚开风险网络比对",
}


def report_title(kind: str, rep: Dict) -> str:
    """取专项报告的显示标题：报告自带 title 优先，缺则用本表兜底。"""
    t = str((rep or {}).get("title") or "").strip()
    return t or SPECIAL_TITLES.get(str(kind or ""), "")


def has_content(rep) -> bool:
    """专项报告是否**有可呈现内容**。

    ★ 2026-10-05：判据演进（两轮都踩了坑，故判据要覆盖三种形态）：
      · 不能用 `available` —— 实测 `cross_enterprise_report` **无该键**（None）
        ⇒ 「跨企业关联交易闭环」被整段漏挂（该挂到疑点19 的没挂上）；
      · 也不能只看 title/summary/body —— 实测 `cost_recon_detail` **三者都没有**
        （它的结构是按品名分类的明细：`invoice_total`/`by_goods`/`invoice_rows`…）
        ⇒ 疑点15 的专项比对又掉了。
      最终判据：三种典型形态**任一有实料**即算有内容：
        ① 有文本（title/summary/body）；
        ② 有信号/指标（signals/metrics/risk_links）；
        ③ 有明细数据（by_goods/invoice_rows/rows 等，按"存在且非空"判）。
    """
    if not isinstance(rep, dict):
        return False
    for _k in ("title", "summary", "body"):
        if str(rep.get(_k) or "").strip():
            return True
    for _k in ("signals", "metrics", "risk_links", "by_goods", "invoice_rows",
               "rows", "dimensions", "categories"):
        _v = rep.get(_k)
        if _v:
            return True
    return False


def match_problem(problem_title: str, kind: str) -> str:
    """判断某项专项报告是否归入某疑点。返回 `""` 表示不归入。

    判据：`SPECIAL_TO_PROBLEM[kind]` 的关键词出现在疑点标题里。
    """
    kw = SPECIAL_TO_PROBLEM.get(str(kind or ""))
    if not kw:
        return ""
    return kw if kw in str(problem_title or "") else ""


def mapped_kinds() -> List[str]:
    """已映射的报告键清单（供自检/闸门使用）。"""
    return list(SPECIAL_TO_PROBLEM.keys())


# ══════════════════════════════════════════════════════════════════════
# 资料缺口 ↔ 疑点 的归属（用户追问「这些内容就不能融入到第二章吗？」）
# ══════════════════════════════════════════════════════════════════════
# ## 为什么用"独立数据源"作判据，而不是关键词全文匹配
#   实测：疑点2 正文含「劳动**合同**」，若按"合同文件"全文搜，它会被误挂 ——
#   但疑点2 的**独立数据源**是「工资表、社保明细、劳务派遣协议」，本不依赖购销合同。
#   而疑点17（股权转让）的数据源含「股权转让协议…」，才是真依赖合同类的项。
#   ⇒ **唯一可靠依据 = 疑点自己声明的「独立数据源」**（结构化、不误命中）。
#
# ## 用法
#   `material_gap_targets(problem)` 从疑点正文抽取其声明的数据源，
#   `gap_category_hit(sources, category)` 判断某资料类别是否在其中。

# 资料类别 → 可用于识别的同义写法（类别名与"独立数据源"里材料的写法差异）
#   例：类别「合同文件」在疑点里写作「合同台账」「购销合同」「合同」…
# ⚠ 别名必须用**完整词**，不能用单字「合同」「协议」——
#   实测单字会误命中：「折让协议」（疑点1）、「劳动合同」「劳务派遣协议」（疑点2）——
#   它们都是**劳动/民事关系文件**，不是必查的**交易合同**。
#   判据经"先量化再收窄"：打印每疑点命中的词，再据实收白名单。
GAP_CATEGORY_ALIASES: Dict[str, Tuple[str, ...]] = {
    "合同文件": ("合同文件", "合同台账", "购销合同", "采购合同", "销售合同",
                 "服务合同", "交易合同", "业务合同", "租赁合同", "借款合同",
                 "贷款合同", "保险合同", "加工合同", "委托合同", "框架合同"),
    # ⚠ 别名**不能**含"报表"二字：实测「增值税**申**报表」里恰好含"报表"
    #   ⇒ 把"增值税申报表"误判成"资产负债表"（疑点3/10/14 全被误挂）。
    #   判据经"先量化再收窄"：打印命中词后才定位到这条。
    "资产负债表": ("资产负债表", "科目余额表"),
    "利润表": ("利润表", "损益表", "利润总额"),
    "企业所得税申报表": ("企业所得税申报表", "所得税申报表", "汇算清缴"),
    "个税申报表": ("个人所得税申报表", "个税申报表", "扣缴申报"),
    "其他税种申报表": ("其他税种申报表", "印花税申报表", "房产税", "土地使用税"),
    "增值税申报表": ("增值税申报表", "申报表"),
    "银行流水": ("银行流水", "流水"),
    "销项发票": ("销项发票", "开票"),
    "进项发票": ("进项发票", "进项"),
    "工资表": ("工资表", "工资总额"),
    "社保明细": ("社保明细", "社保"),
    "记账凭证": ("记账凭证", "序时账", "凭证"),
}


def extract_sources(problem: Dict) -> Tuple[str, ...]:
    """从疑点正文抽取其声明的**独立数据源**（结构化，非全文匹配）。

    数据源写在证据条目文本里，形如「独立数据源：销项发票、进项发票」。
    """
    import re as _re
    out: List[str] = []
    for par in (problem or {}).get("narrative_paragraphs") or []:
        if not isinstance(par, dict):
            continue
        texts = [str(par.get("text") or "")]
        texts += [str(b) for b in (par.get("bullets") or [])]
        for t in texts:
            for m in _re.findall(r"独立数据源：([^｜）;；。]{2,90})", t):
                for x in _re.split(r"[、,，]", m):
                    x = x.strip()
                    if x and x not in out:
                        out.append(x)
    return tuple(out)


# 不属于该资料类别的写法（排除词）—— 防"劳动合同"被当成"合同文件"
GAP_CATEGORY_EXCLUDE: Dict[str, Tuple[str, ...]] = {
    "合同文件": ("劳动合同", "劳务派遣", "劳务协议", "折让协议", "退货单",
                 "拒收证明", "用工名册"),
}


def gap_category_hit(sources, category: str) -> bool:
    """该疑点的数据源里是否含此资料类别（按别名表判，唯一权威）。

    规则：命中任一**完整别名** ⇒ 命中；但若该数据源含**排除词** ⇒ 该条不算。
    （排除词用于区分"交易合同"与"劳动合同/折让协议"这类**同字不同物**的写法。）
    """
    alias = GAP_CATEGORY_ALIASES.get(str(category or ""))
    if not alias:
        return False
    excl = GAP_CATEGORY_EXCLUDE.get(str(category or ""), ())
    for s in sources or ():
        s = str(s)
        if any(e in s for e in excl):
            continue
        for a in alias:
            if a in s:
                return True
    return False


# ══════════════════════════════════════════════════════════════════════
# 询问主题 ↔ 疑点 的归属（用户追问三次「这些内容就不能融入到第二章吗？」）
# ══════════════════════════════════════════════════════════════════════
# 依据：询问清单的 `theme` 是**按主题板块**命名的（"资金，私户收款性质"），
#   而疑点标题是该事项的**正式名**。二者无共同字段，故必须用**显式归属表**
#   （业务判断，已逐条核实），**不可用全文关键词匹配** ——
#   实测"资金，关联闭环"若按全文搜会命中疑点3（只因疑点3正文也出现"关联"）。
#
# ⚠ 无对应疑点的主题（如"进项，应转出未转出"）**不挂** ——
#   疑点15 正文完全不含"进项转出/不得抵扣"，硬挂即张冠李戴；
#   这类主题保留在报告末尾，不强行塞进某个疑点。
QUESTION_THEME_TO_PROBLEM: Dict[str, str] = {
    "资金，私户收款性质": "公私混同发薪",          # → 疑点20 私户支付薪酬
    "资金，未开票敞口": "银行收款大于申报收入",      # → 疑点3
    "资金，关联闭环": "资金回流与公私混同检测",      # → 疑点18
    "进项，双向往来主体": "关联交易异常",          # → 疑点19
    "虚开，同额凑数": "关联交易异常",             # → 疑点19
    "虚开，双向往来主体": "关联交易异常",          # → 疑点19
    # ★ 2026-10-06（用户：「这些内容为什么存在？又为什么会呈现在这里？难道不应该在分析出的疑点
    #   中呈现吗？」）：本条一度被登记为"无对应疑点"，理由是"疑点15 正文不含『进项转出』"。
    #   但 2026-10-05 起 `input_voucher_report` 已由 `STANDALONE_RISK_REPORTS` 立为**独立风险事项**
    #   「进项异常凭证：不得抵扣用途未作进项转出」（同一税额 3,996.91 元、同一 7 段结构）。
    #   ⇒ 对应关系**已经存在**，只是归属表没跟着更新，于是这条询问被丢进报告末尾的
    #   「待企业澄清事项（其余事项）」——**同一风险在报告里出现两次**。
    #   ⇒ 更新归属表（一行数据）；并加闸门保证"落到残余章"必报错，杜绝再次漂移。
    "进项，应转出未转出": "进项异常凭证",          # → 独立风险事项（进项异常凭证）
    # ⚠ 资料类主题（"资料，申报表缺失/存货与余额表缺失/其他缺失"）**不再进入询问清单**：
    #   它们是**资料缺口**，唯一权威是 `material_readiness`（含"缺失资料 / 将影响的风险检查方面 /
    #   补救要求"三列），见 `inspection_questions` 中的说明。此处不登记，也不该出现在残余章。
}


def _norm_theme(theme) -> str:
    """询问主题**标点归一化**（唯一权威）。

    ★★ 2026-10-05 实测根因：`_build_inspection_questions_report` 返回的主题是
      `资金·私户收款性质`（**间隔号 ·**），而报告落盘前 `normalize_cjk_punct`
      会把它规范成 `资金，私户收款性质`（**逗号**）——
      故**同一主题在挂载时与产物里长得不一样**，按字面匹配必然失败
      （我第一次就踩了：映射表写成逗号版 ⇒ 10 条全部落到"无归属"）。
    通用修法：把常见分隔符（·・,，、空白）统一为 `，` 后再匹配，
      **不在表里堆两种写法**（新增主题也只写一种）。
    """
    import re as _re
    s = str(theme or "").strip()
    # ② 去掉括注：实测主题常带补充说明，如「进项，双向往来主体**（未发现对开特征）**」，
    #    而映射表按**短名**登记 ⇒ 不去括注就匹配不上（我第一次踩的就是这个）。
    s = _re.sub(r"[（(][^）)]*[）)]", "", s)
    # ① 分隔符归一：`·`（挂载时）与 `，`（落盘标点规范化后）视为同一分隔
    return _re.sub(r"[·・,，、\s]+", "，", s).strip()


def question_theme_target(theme: str) -> str:
    """询问主题 → 目标疑点标题关键词（`""` = 无对应疑点，不挂）。"""
    _key = _norm_theme(theme)
    for _k, _v in QUESTION_THEME_TO_PROBLEM.items():
        if _norm_theme(_k) == _key:
            return _v
    return ""


def _problem_match_text(p: Dict) -> str:
    """疑点**可匹配文本** = 本项标题 ∪ **同族别名**（被并入本项的成员标题）。

    ★★ 2026-10-06 事故：同族合并（`finding_families`）把归属表指向的那条疑点
      **并入了族主事项**，族主标题与原成员标题不同 ⇒ 归属表里的关键词匹配不上
      ⇒ 询问主题**全部退回残余章**，与风险事项重复呈现
      （实测 5 条：资金·私户收款性质 / 资金·关联闭环 / 进项·双向往来主体 /
        虚开·同额凑数 / 虚开·双向往来主体）。
    ⇒ 匹配文本必须包含**同族别名**（由 `finding_families` 在合并时登记），
      这样归属表一行不改、也不必为"合并后标题长什么样"写特例。
    """
    _t = str((p or {}).get("title") or "")
    _al = (p or {}).get("_family_aliases") or []
    if isinstance(_al, (list, tuple, set)):
        _t += " " + " ".join(str(x) for x in _al)
    _fam = str((p or {}).get("_family") or "")
    if _fam:
        _t += " " + _fam
    return _t


def attach_question_themes(themes, problems):
    """把**指向具体疑点**的询问主题整条挂到该疑点（原地改 `problems`）。

    :return: `(attached_count, unattached_themes)`

    ★ 2026-10-06 抽为函数（原本内联在 `enterprise_report` 里），原因有二：
      ① **原实现有静默丢失**：命中归属表却找不到匹配疑点时，循环走完既不挂载、
         也不落 `unattached` ⇒ 这条询问**凭空消失**（报告里再也找不到）。
         现改为：**挂不上就退回 unattached**，绝不静默吞掉。
      ② 抽成函数才能被闸门/测试**直接喂假数据断言**（见
         `tools/audit_consistency.py::check_question_theme_attachment`）——
         "代码看起来接了"不等于"运行期真的挂了"。
    归属表唯一权威：本模块 `QUESTION_THEME_TO_PROBLEM`。
    """
    unattached = []
    attached = 0
    for th in themes or []:
        if not isinstance(th, dict):
            continue
        kw = question_theme_target(th.get("theme"))
        if not kw:
            unattached.append(th)          # 无对应疑点 → 留在报告末尾
            continue
        hit = None
        for p in problems or []:
            if isinstance(p, dict) and kw in _problem_match_text(p):
                hit = p
                break
        if hit is None:
            # ★ 归属表写了目标、本轮却不存在该疑点（如风险未触发）⇒ 退回未挂载，
            #   不得静默丢弃（否则这条询问在报告任何地方都看不到）。
            unattached.append(th)
            continue
        hit.setdefault("questions", []).append(th)
        attached += 1
    return attached, unattached


# ══════════════════════════════════════════════════════════════════════
# 无对应疑点、但**本身是真风险**的底稿 ⇒ 立为独立风险事项
# ══════════════════════════════════════════════════════════════════════
# ★★★ 2026-10-05（用户：「这真让人想死…你是怎么认为这些内容的？」）：
#   事故：`input_voucher_report`（进项异常凭证/应转出未转出 **3,996.91 元**）
#   因为**没有对应红线疑点**，被我判定"保持独立"，结果被降格成一节**技术比对**，
#   和"系统能力边界""外部数据源核验"（都是系统自述/日志）挤在同一章里。
#   **"没有对应疑点" ≠ "它不是风险"** —— 它明明是实打实的风险事项
#   （不得抵扣的进项税未转出），应当与其它风险**同等呈现**（同样的 7 段结构）。
#   判据：底稿自身带 `metrics`/`signals`/`verdict` 且结论非"未发现异常" ⇒ 它是风险事项。
STANDALONE_RISK_REPORTS: Dict[str, str] = {
    "input_voucher_report": "进项异常凭证：不得抵扣用途未作进项转出",
}
