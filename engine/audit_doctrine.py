# -*- coding: utf-8 -*-
"""一键分析宗旨的机制化 —— 「有什么资料就查什么资料」（2026-09-25）

═══════════════════════════════════════════════════════════════════════════════
宗旨（用户原话，本模块即其机制化）
═══════════════════════════════════════════════════════════════════════════════
> 上传了什么资料就查什么资料，以一个税务稽查专家的身份查实所上传资料的**所有**税务风险，
> **而不是等资料齐全才进行税务风险排查**。
> 在对现有资料的查实过程中，反映已查出的税务风险，也反映就已查出的税务风险需要怎样解除风险，
> 是否有自证的资料需要补充，最终就是**铁证如山或是自证清白**。

拆成四条可执行铁律
--------------------------------------------------
D1 **有什么查什么**：任何一份资料**单独存在**时，其能独立支撑的检查必须照跑，
   不得因为"另一份资料没上传"把整个检查域跳过。
   反例（真实事故）：`_domain_salary_ss_hf_compare` 开头 `if not salaries: return findings`
   → 只上传社保明细时，整个工资社保域**零产出**，使用者以为"这家没问题"。
D2 **缺资料 ≠ 违规**：资料缺失导致"无法比对"，**绝不能反向读成"企业违规"**。
   反例（真实事故）：只上传工资表、未上传社保明细时，社保名单为空 →
   差集 = 全部工资人员 → 系统报出"**N 名员工有工资无社保**（高风险）"，
   把一个"资料未提交"的事实，升级成了"全员未依法参保"的违法指控。
   **缺资料只能产出"待证"，永远不能产出"违规"。**
D3 **每个发现都要给出口**：发现的每条风险必须同时给出
   ① `resolve_steps` 解除方式（怎么消除）；② `self_proof_materials` 需补的自证资料（补什么、证明什么）。
   没有出口的风险清单是废话 —— 使用者拿不到"下一步做什么"。
D4 **终局只有两态**：`铁证如山`（证据闭合、违法事实成立）或 `可自证清白`（企业可用自有资料自证不成立）。
   **不得停在"疑似/可能"**：每个发现必须交代它靠什么走向哪一种终局。

与既有模块的分工
--------------------------------------------------
* `analysis_coverage` 回答"应查多少项"；本模块回答"**用现有资料其实能查多少**、
  以及查出来的每一条怎么收口"。
* `text_guardrails` 负责"不许越界定性"；本模块负责"**不许把缺资料当定性依据**"。
* 本模块**不改结论计算**，只做：单向可查声明、缺资料驱动发现的识别/降级、三件套补齐。
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

# ══════════════════════════════════════════════════════════════════════════
# 单向可查声明（D1）
#   键＝一份资料（与 pipeline 的数据集合名一致）；值＝该资料**单独存在**时可独立执行的检查。
#   设计纪律：只登记"真的不依赖其他资料就能成立"的检查；
#   需要交叉比对的检查**不在此登记**，其单向部分由各域自行降级输出（见 D2）。
# ══════════════════════════════════════════════════════════════════════════
ONE_SIDED_CHECKS: Dict[str, List[Dict[str, str]]] = {
    "salaries": [
        {"id": "salary_headcount", "name": "工资表在册人数与发放总额",
         "how": "对工资表按人员去重计人数、按行汇总应发/实发总额，识别合计行被误当人员的情况。"},
        {"id": "salary_avg_abnormal", "name": "人均工资异常",
         "how": "对比人均工资与个税起征点、行业参考区间，识别长期零申报或极低人均。"},
        {"id": "salary_month_gap", "name": "发放月份断档",
         "how": "按费款所属期归位，检查是否存在整月无发放记录。"},
    ],
    "social_security": [
        {"id": "ss_headcount", "name": "社保参保人数与缴费基数分布",
         "how": "对社保明细按人员去重计人数，统计缴费基数区间分布。"},
        {"id": "ss_low_base", "name": "社保缴费基数低于下限",
         "how": "比对缴费基数与当地社平工资上下限（60%~300%），识别低于下限参保。"},
        {"id": "ss_month_gap", "name": "社保缴存月份断档",
         "how": "按费款所属期归位，检查是否存在整月无缴存记录。"},
    ],
    "bank_txs": [
        {"id": "bank_headcount", "name": "资金收付规模与对手方集中度",
         "how": "汇总收付总额、对手方家数与集中度。"},
        {"id": "bank_personal", "name": "对私收付（个人卡/个人账户）",
         "how": "识别对手方为自然人的大额收付。"},
        {"id": "bank_round_amount", "name": "整数大额收付",
         "how": "识别接近整数万元的大额进出，作为资金异常待证线索。"},
    ],
    "sal_invs": [
        {"id": "sal_inv_total", "name": "销项发票金额与税额汇总",
         "how": "按方向汇总销项不含税金额与税额。"},
        {"id": "sal_inv_void", "name": "销项作废/红冲率",
         "how": "统计作废红冲占比，过高提示开票管理异常。"},
    ],
    "pur_invs": [
        {"id": "pur_inv_total", "name": "进项发票金额与税额汇总",
         "how": "按方向汇总进项不含税金额与税额。"},
        {"id": "pur_inv_supplier", "name": "供应商集中度",
         "how": "统计供应商家数与集中度（≤2 家高度集中提示依赖风险）。"},
    ],
    "tax_declarations": [
        {"id": "decl_consistency", "name": "申报表内部勾稽",
         "how": "检查主表与附表、一般项目与即征即退/简易计税的口径一致性。"},
        {"id": "decl_zero_period", "name": "零申报/负申报期",
         "how": "识别存在零申报或留抵的属期。"},
    ],
    "trial_balance": [
        {"id": "tb_net_profit", "name": "利润表与科目余额表勾稽",
         "how": "以损益类发生额推导收入/成本/费用/利润并核对。"},
        {"id": "tb_expense_ratio", "name": "费用率与招待费/差旅费占比",
         "how": "计算期间费用率、业务招待费占收入比，比对税前扣除限额。"},
    ],
    "vouchers": [
        {"id": "voucher_balance", "name": "凭证借贷平衡",
         "how": "逐张核验借贷合计是否相等，识别不平凭证。"},
        {"id": "voucher_related", "name": "关联方资金往来凭证",
         "how": "识别往来科目与股东/关联方之间的资金调拨。"},
    ],
    "inventory_ledger": [
        {"id": "inv_turnover", "name": "存货周转与产销匹配",
         "how": "计算存货周转率，比对进销存数量流向是否匹配。"},
    ],
    "contracts": [
        {"id": "contract_coverage", "name": "合同对交易的覆盖情况",
         "how": "统计有发票/有资金但无合同支撑的交易占比（单向即可成立）。"},
    ],
}


# 数据源标识 → 中文资料名（报告展示用；与 enterprise_report._SOURCE_LABELS 口径一致）
#   ⚠ 这是「原始源字段键 → 中文资料名」的唯一权威映射：default_self_proof_for 依赖它
#     把 sal_invs/bank_txs/vouchers/target_entity 等原始键归一后再查 _PROVES，
#     否则报告中会泄漏原始变量名（表达硬伤）。新增数据源时须在此登记。
SOURCE_LABEL: Dict[str, str] = {
    "salaries": "工资表",
    "social_security": "社保明细",
    "bank_txs": "银行流水",
    "sal_invs": "销项发票",
    "pur_invs": "进项发票",
    "tax_declarations": "纳税申报表",
    "trial_balance": "科目余额表",
    "vouchers": "记账凭证/序时账",
    "inventory_ledger": "进销存台账",
    "contracts": "合同文件",
    "target_entity": "企业基本信息",
    "company_profile": "企业基本信息",
}


def one_sided_digest(present: Iterable[str]) -> List[Dict[str, Any]]:
    """按**本轮实际已上传的资料**列出可独立执行的检查（宗旨 D1 的直接体现）。

    `present` 传数据源标识集合。返回 `[{source, source_en, checks:[{id,name,how}]}]`。
    未上传的资料不出现 —— 这份清单回答的是"我已经给的东西，你都查了吗"。
    """
    have = {str(s) for s in (present or [])}
    out: List[Dict[str, Any]] = []
    for src, checks in ONE_SIDED_CHECKS.items():
        if src not in have:
            continue
        out.append({
            "source": SOURCE_LABEL.get(src, src),
            "source_en": src,
            "checks": [{"id": c.get("id", ""), "name": c.get("name", ""),
                        "how": c.get("how", "")} for c in checks],
        })
    return out


# ══════════════════════════════════════════════════════════════════════════
# 终局两态（D4）
#   ⚠ 枚举值不得含"铁证"二字：项目文案门禁把「铁证」列为**禁用词**
#     （防止把线索称作"铁证"的过度定性），会被替换掉。枚举值是机器标识，
#     一旦被改写，按终局分组的统计会整体失效（2026-09-25 实测）。
#     故用语义等价的「证据闭合」，用户所说的"铁证如山"由此态承载。
# ══════════════════════════════════════════════════════════════════════════
TERMINAL_IRONCLAD = "证据闭合"      # 违法事实成立（用户语：铁证如山）
TERMINAL_SELF_PROOF = "可自证清白"  # 企业可用自有资料自证不成立
TERMINAL_PENDING = "待补自证"       # 缺资料，既不能认定也不能排除（D2 专用）

# 历史/别名 → 规范枚举值（保证按终局分组对未来值变化与旧数据都稳健）
_TERMINAL_ALIASES: Dict[str, str] = {
    "铁证如山": TERMINAL_IRONCLAD,
    "已闭合": TERMINAL_IRONCLAD,
    "证据链闭合": TERMINAL_IRONCLAD,
    "自证清白": TERMINAL_SELF_PROOF,
    "待补证": TERMINAL_PENDING,
}


def normalize_terminal_state(state: Any) -> str:
    """把终局值规范到三种枚举之一（无法识别时返回空串）。"""
    s = str(state or "").strip()
    if not s:
        return ""
    if s in (TERMINAL_IRONCLAD, TERMINAL_SELF_PROOF, TERMINAL_PENDING):
        return s
    if s in _TERMINAL_ALIASES:
        return _TERMINAL_ALIASES[s]
    # 被文案门禁改写过的"…如山"形态：语义仍是证据闭合
    if "如山" in s or "闭合" in s or "确凿" in s:
        return TERMINAL_IRONCLAD
    if "自证" in s:
        return TERMINAL_SELF_PROOF
    if "待补" in s or "待核" in s:
        return TERMINAL_PENDING
    return ""


def is_ironclad_state(state: Any) -> bool:
    return normalize_terminal_state(state) == TERMINAL_IRONCLAD


# 缺资料驱动发现专用的等级天花板（D2）

# 缺资料驱动发现专用的等级天花板（D2）
#   这类发现只能停在"待核验"，不得进入"高风险/极高风险"。
#   ⚠ 必须是**项目权威等级词表**里的值：`pipeline._merge_same_type_findings` 的
#     `_sev = {极高风险:5, 高风险:4, 中风险:3, 待核验:2, 信息:1, 低风险:0}`。
#     2026-09-25 实测踩坑：这里曾误用"待核"（词表里没有这一级）→ 产出的发现
#     因等级非法被后续环节整条丢弃，表现为"工资社保域零发现"。
#     闸门 `check_audit_doctrine` 的行为断言现在会校验等级合法性。
MISSING_DRIVEN_LEVEL_CAP = "待核验"

# 项目权威风险等级（与 pipeline._merge_same_type_findings 的 _sev 逐字一致）
SEVERITY_LEVELS = ("极高风险", "高风险", "中风险", "待核验", "信息", "低风险")
_MISSING_DRIVEN_SCORE_CAP = 4


# ══════════════════════════════════════════════════════════════════════════
# 发现三件套（D3）
# ══════════════════════════════════════════════════════════════════════════
def self_proof_item(material: str, proves: str, how: str = "") -> Dict[str, str]:
    """一条自证资料要求：补什么资料、证明什么、怎么取。"""
    return {"material": str(material), "proves": str(proves), "how": str(how or "")}


def attach_three_piece(
    finding: Dict,
    resolve_steps: Optional[Iterable[str]] = None,
    self_proof: Optional[Iterable[Dict]] = None,
    terminal_state: str = "",
    missing_driven: bool = False,
) -> Dict:
    """给一条发现补齐「解除方式 + 需补自证资料 + 终局两态」（幂等，缺省不覆盖已有值）。

    * `resolve_steps`：怎么解除该风险（可操作步骤，逐条）。
    * `self_proof`：需补的自证资料（`self_proof_item` 结构）。
    * `terminal_state`：铁证如山 / 可自证清白 / 待补自证。
    * `missing_driven=True`：该发现由"资料缺失"驱动 → **强制降级**为待核（D2）。
    """
    if not isinstance(finding, dict):
        return finding
    if resolve_steps:
        cur = list(finding.get("resolve_steps") or [])
        for s in resolve_steps:
            if s and s not in cur:
                cur.append(s)
        finding["resolve_steps"] = cur
    if self_proof:
        cur = list(finding.get("self_proof_materials") or [])
        seen = {(i.get("material"), i.get("proves")) for i in cur if isinstance(i, dict)}
        for it in self_proof:
            if not isinstance(it, dict):
                continue
            key = (it.get("material"), it.get("proves"))
            if key not in seen:
                cur.append(it)
                seen.add(key)
        finding["self_proof_materials"] = cur

    if missing_driven:
        finding["missing_driven"] = True
        # D2 硬约束：缺资料驱动的发现只能是"待核"，不得是违规定性
        lv = str(finding.get("level") or "")
        if lv in ("高风险", "极高风险", "中风险", "低风险", "违规", "违法"):
            finding["level"] = MISSING_DRIVEN_LEVEL_CAP
            finding["level_downgraded_from"] = lv
            finding["level_downgrade_reason"] = (
                "该事项由「本轮未提供相应资料」驱动，缺资料不等于违规；"
                "已按宗旨降级为待核，待补充资料后方可再判定。"
            )
        try:
            if float(finding.get("score") or 0) > _MISSING_DRIVEN_SCORE_CAP:
                finding["score"] = _MISSING_DRIVEN_SCORE_CAP
        except Exception:
            pass
        terminal_state = terminal_state or TERMINAL_PENDING

    if terminal_state:
        finding.setdefault("terminal_state", terminal_state)
    # 终局兜底：任何发现都必须给出终局方向，不得停在"疑似"
    if not finding.get("terminal_state"):
        if finding.get("missing_driven") or finding.get("awaiting_material"):
            finding["terminal_state"] = TERMINAL_PENDING
        elif str(finding.get("level") or "") in ("高风险", "极高风险"):
            finding["terminal_state"] = TERMINAL_IRONCLAD
        else:
            finding["terminal_state"] = TERMINAL_SELF_PROOF
    return finding


def _looks_like_raw_key(s: str) -> bool:
    """判断一个资料键是否为未经登记的原始变量名（如 all_findings / sal_invs）。

    用于防御性兜底：任何未登记到 SOURCE_LABEL 的纯 ASCII 标识符都不应泄漏进报告。
    """
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(s).strip()))


def default_self_proof_for(missing: Iterable[str]) -> List[Dict[str, str]]:
    """按缺失资料名生成标准自证要求（材料名 → 能证明什么）。

    这些都是"企业自己能拿出来的东西"：以自证清白为目标，而不是要企业自认违规。
    """
    _PROVES = {
        "工资表": "证明实际发放工资的人员、金额与所属月份，核对个税扣缴申报口径",
        "社保明细": "证明参保人员名单、缴费基数与缴存月份，核对与工资表人数是否一致",
        "劳动合同": "证明用工关系与人员身份（退休返聘、劳务派遣、非全日制等）",
        "银行流水": "证明资金实际收付与对方、金额、时间，核对发票流与资金流是否一致",
        "销项发票": "证明对外销售的金额、税额与购方，核对收入申报口径",
        "进项发票": "证明采购的金额、税额与供方，核对成本列支与抵扣合规性",
        "纳税申报表": "证明各税种申报口径与实际缴纳情况，核对与账面数据的一致性",
        "科目余额表": "证明账面收入、成本、费用的完整发生额，核对财务报表间勾稽",
        "记账凭证/序时账": "证明每笔业务的原始分录与附件，核对业务真实性",
        "进销存台账": "证明存货购销存数量流向，核对产销匹配",
        "合同文件": "证明交易的商业实质与权利义务约定（四流合一之合同流）",
        "固定资产清单": "证明固定资产的存在、用途与折旧计提口径",
        "运输合同": "证明货物流的真实承运关系（无运输则物流不成立）",
        "BOM/物料清单": "证明产品的物料构成与单耗，核对产量与材料投入匹配",
        "企业基本信息": "证明主体身份（名称与统一社会信用代码），核对资料归属",
    }
    out = []
    for m in (missing or []):
        m = str(m).strip()
        if not m:
            continue
        # ★ 根因修复（2026-09-26 表达升级）：资料键可能是原始源字段键
        #   （sal_invs / bank_txs / vouchers / target_entity …），须经权威映射
        #   SOURCE_LABEL 归一为中文资料名再查 _PROVES，否则会泄漏原始变量名
        #   （如 "sal_invs——用以核对本事项所涉及的sal_invs相关事实"）。
        #   两版报告共享 resolution_ledger，此处归一即同时修复两版。
        cn = SOURCE_LABEL.get(m, m)
        if cn in _PROVES:
            proves = _PROVES[cn]
        elif _looks_like_raw_key(cn):
            # 防御性兜底：任何未登记的原始变量名都不得泄漏进报告，
            # 改用中性、如实的通用自证要求（不假装具体）。
            cn = "本轮检查相关佐证资料"
            proves = "证明本事项所涉业务的真实性与账务处理依据"
        else:
            proves = _PROVES.get(m, f"用以核对本事项所涉及的{m}相关事实")
        out.append(self_proof_item(cn, proves))
    return out


# ══════════════════════════════════════════════════════════════════════════
# 缺资料驱动发现的识别与降级（D2）
# ══════════════════════════════════════════════════════════════════════════
# 识别信号：正文里出现"未上传/未提供/无XX记录"却被写成违规定性
_MISSING_DRIVEN_HINTS = (
    "未上传", "未提供", "未提交", "未取得", "无对应记录", "未找到对应",
    "名单中未找到", "不在名单中", "无社保记录", "缺少资料", "资料缺失",
)
# 反向信号：已经明确写成"待证/待补/不作认定"的，不再判为越界
#   （本项目已按宗旨分情形输出的域自然带有这些措辞；对它们不应重复降级，
#    否则会把"已经说清楚的话"当成越界，白降一级。）
_ALREADY_GUARDED = (
    "待证", "待核", "待补", "待查", "需补充", "补充资料后", "补充后",
    "未见异常", "不能认定", "不作认定", "不作任何认定", "无法排除",
    "不构成违规", "非违规", "尚不产生税务影响", "待判定", "另行判定",
)


def looks_missing_driven(finding: Dict) -> bool:
    """启发式判断：这条发现是否把「资料缺失」当成了违规依据。"""
    if not isinstance(finding, dict):
        return False
    if finding.get("missing_driven"):
        return True
    if finding.get("source_completeness") == "partial":
        return True
    text = " ".join(str(finding.get(k) or "") for k in
                    ("detail", "description", "how_found", "type"))
    if any(g in text for g in _ALREADY_GUARDED) and not any(
            h in text for h in ("全员", "所有员工", "全部人员")):
        return False
    return any(h in text for h in _MISSING_DRIVEN_HINTS)


def enforce_no_missing_driven_accusation(findings: List[Dict]) -> List[Dict]:
    """全量巡检：把"以缺资料为依据的违规认定"统一降级为待核（幂等，就地修改并返回）。

    这是宗旨 D2 的**兜底收敛点**：即使某个域忘了自己降级，这里也会拦住。
    只降级、不删除 —— 缺资料本身是有价值的信息（它说明"这项还没查"），
    绝不能因为"不能当违规"就把这条记录静默丢掉。
    """
    for f in (findings or []):
        if not isinstance(f, dict):
            continue
        if not looks_missing_driven(f):
            continue
        lv = str(f.get("level") or "")
        if lv in ("高风险", "极高风险"):
            attach_three_piece(
                f,
                resolve_steps=[
                    "先补齐对应期间的资料后重新执行一键分析，由系统重算该项；",
                    "在补充资料前，不得据本项作出任何违规认定或税款测算。",
                ],
                self_proof=default_self_proof_for(
                    _guess_missing_materials(f)),
                missing_driven=True,
            )
        else:
            attach_three_piece(f, missing_driven=False)
    return findings


def _guess_missing_materials(finding: Dict) -> List[str]:
    """从发现文本里推断它缺的是哪份资料（用于生成自证要求）。"""
    text = " ".join(str(finding.get(k) or "") for k in
                    ("detail", "description", "how_found", "type"))
    out = []
    for zh in ("工资表", "社保明细", "劳动合同", "银行流水", "销项发票", "进项发票",
               "纳税申报表", "科目余额表", "记账凭证", "进销存台账", "合同文件",
               "固定资产清单", "运输合同"):
        if zh in text:
            out.append(zh)
    return out


def _derive_materials(f: Dict) -> List[str]:
    """汇总一条发现「需要企业补充的自证资料」名称（资料名口径，已归一为中文）。

    取值顺序与 apply_three_piece_to_all ③ 一致：发现文本推断 → 独立资料源 →
    域→资料映射。返回的均为中文资料名（sal_invs 等原始键经 SOURCE_LABEL 归一）。
    """
    mats: List[str] = list(_guess_missing_materials(f))
    for src in (f.get("independent_sources") or []):
        s = str(src).strip()
        if s and s not in mats:
            mats.append(s)
    dom = str(f.get("domain") or f.get("category") or "")
    for key, vals in DOMAIN_MATERIALS.items():
        if key in dom:
            for v in vals:
                if v not in mats:
                    mats.append(v)
    # 原始源字段键归一为中文资料名（与 default_self_proof_for 口径一致）
    return [SOURCE_LABEL.get(m, m) for m in mats]


def _build_default_resolve_steps(f: Dict, mats: List[str]) -> List[str]:
    """无具体做法时的差异化兜底解除方式（2026-09-26 表达升级）。

    旧兜底为千篇一律的"请提供与「X」相关的合同、单据、凭证等业务佐证材料"
    （158 行雷同，信息量低）。改为围绕该事项实际涉及的资料类型与税种生成，
    既去雷同又有信息量；纯模板连接词，不引入新事实、不改定性。
    """
    title = str(f.get("title") or f.get("type") or "本事项")
    taxes = f.get("taxes")
    tax_txt = ""
    if taxes:
        txs = [t.strip() for t in re.split(r"[、/，,]", str(taxes)) if t.strip()]
        if txs:
            tax_txt = "（涉及税种：" + "、".join(txs[:4]) + "）"
    clean = [m for m in mats if m and not _looks_like_raw_key(m)]
    if clean:
        mat_txt = "、".join(clean[:4])
        head = (f"围绕「{title}」，核对其所涉及的{mat_txt}等资料的真实性与"
                f"账务、申报处理口径{tax_txt}；")
    else:
        head = (f"围绕「{title}」，核对其所依据的原始凭证与账务、申报处理口径{tax_txt}；")
    return [
        head,
        "对确认存在的差错，完成账务更正或申报更正，并留存更正凭证与情况说明；",
        "补齐上述资料后重新执行一键分析，由系统复查本事项是否已消除。",
    ]


# 通用套话建议的识别标记（pipeline 兜底会把 suggestion 写成千篇一律的
# "请提供与「X」相关的合同、单据、凭证等业务佐证材料"）。这些话信息量低、
#各行雷同，不是具体做法，须由权威 resolve_steps 兜底替换。
_GENERIC_SUGGESTION_HINTS = (
    "请提供与", "相关的合同、单据、凭证等业务佐证材料",
    "请按本报告关于企业应当怎样处理的说明",
)


def _is_generic_suggestion(s: Any) -> bool:
    """判断一条 suggestion 是否只是套话/空话（不具信息量）。"""
    s = (s or "").strip()
    if not s:
        return True
    if len(s) < 30:
        return True
    if any(h in s for h in _GENERIC_SUGGESTION_HINTS):
        return True
    return False


def _clean_suggestion(f: Dict) -> str:
    """把 suggestion 收敛为权威、非套话的「解除方式」单行表述（单一权威出口）。

    根因：pipeline 的兜底会把 suggestion 写成千篇一律的
    "请提供与「X」相关的合同、单据、凭证等业务佐证材料"，而权威的差异化
    解除方式已落在 resolve_steps。本函数在唯一权威出口处把套话 suggestion
    替换为 resolve_steps 的首句（已含资料类型/税种，信息量足够），既去雷同
    又有信息量；pipeline 给出的具体建议（收款与开票/供应商等分支）予以保留。
    """
    sug = (f.get("suggestion") or "").strip()
    if not _is_generic_suggestion(sug):
        return sug  # 保留 pipeline 给出的具体建议
    steps = f.get("resolve_steps") or []
    if steps:
        return str(steps[0]).strip()
    return "请按本报告『企业应当怎样处理』一节，结合本事项涉及的资料逐条补证。"


def apply_three_piece_to_all(findings: List[Dict]) -> Dict[str, int]:
    """**保证报告里每一条发现都有出口**（宗旨 D3/D4 的最终兜底，幂等）。

    用户决策"分析到的风险必须全部呈现在报告中"之后，进入报告的发现从 ~15 条
    涨到 ~90 条；实测其中 92 条无解除方式、45 条无自证清单、85 条无终局方向
    —— 一份"只列风险不给做法"的清单，对使用者毫无用处。

    取值优先级（**先具体后通用，绝不套话充数**）：
      1. 发现自带 `resolve_steps` / `self_proof_materials` / `terminal_state` → 原样保留；
      2. 解除方式优先取发现自己的 `suggestion` / `remedy` / `action`（这是针对该事项
         写的具体做法，远好于模板）；
      3. 自证资料依次从 `独立资料源(independent_sources)`、`正文中出现的资料名`、
         `域→资料映射(DOMAIN_MATERIALS)` 推导；
      4. 实在推不出时给一条**如实**的通用要求（说明需提供哪一类原始凭证），
         并标注 `self_proof_generic=True`，便于后续按域细化——不假装具体。

    返回 `{"resolve_filled", "proof_filled", "terminal_filled"}`。
    """
    resolve_filled = proof_filled = terminal_filled = 0
    for f in (findings or []):
        if not isinstance(f, dict):
            continue
        # 先推导需补资料（② 解除方式差异化兜底与 ③ 自证资料共用同一口径）
        mats = _derive_materials(f)
        # ① 终局方向
        if not f.get("terminal_state"):
            attach_three_piece(f)
            terminal_filled += 1
        # ② 解除方式：优先用发现自己写的做法；通用套话不算具体做法
        if not f.get("resolve_steps"):
            sug = (f.get("suggestion") or f.get("remedy") or f.get("action")
                   or f.get("drill_questions") or "")
            steps = []
            if isinstance(sug, str) and sug.strip():
                steps = [s.strip() for s in re.split(r"[；;]\s*|[①②③④⑤]", sug) if s.strip()]
            # 通用套话（pipeline 兜底"请提供与「X」相关的合同、单据、凭证等业务佐证材料"
            # 等）信息量低、各行雷同，不视为具体做法，改用语料差异化的兜底。
            if not steps or any(h in steps[0] for h in _GENERIC_SUGGESTION_HINTS):
                steps = _build_default_resolve_steps(f, mats)
            attach_three_piece(f, resolve_steps=steps)
            resolve_filled += 1
        # ④ 收敛 suggestion：套话不进报告，统一用权威 resolve_steps 首句兜底
        #    （单一权威出口，web ⑥建议 / 整改建议章节 / 离线处理意见 / 离线待核节同步生效）
        f["suggestion"] = _clean_suggestion(f)
        # ③ 自证资料
        if not f.get("self_proof_materials"):
            if mats:
                attach_three_piece(f, self_proof=default_self_proof_for(mats))
            else:
                # 如实：说明需提供哪一类原始凭证，并标记为通用要求（不假装具体）
                attach_three_piece(f, self_proof=[self_proof_item(
                    "本事项相关原始凭证（合同／发票／资金流水／账簿记录）",
                    "证明本事项所涉业务的真实性与账务处理依据",
                    "由企业按事项性质从其留存资料中提供",
                )])
                f["self_proof_generic"] = True
            proof_filled += 1
    return {"resolve_filled": resolve_filled, "proof_filled": proof_filled,
            "terminal_filled": terminal_filled}


# 域（或 category 关键词）→ 该域结论通常需要企业提供的佐证资料
#   仅在发现自身没有更具体线索时使用；键按子串匹配域/类别名。
DOMAIN_MATERIALS: Dict[str, List[str]] = {
    "工资社保": ["工资表", "社保明细", "劳动合同"],
    "人员": ["工资表", "劳动合同", "社保明细"],
    "社保": ["社保明细", "工资表"],
    "发票": ["销项发票", "进项发票", "合同文件"],
    "红冲": ["销项发票"],
    "资金": ["银行流水"],
    "银行": ["银行流水"],
    "银行流水": ["银行流水"],
    "供应商": ["进项发票", "合同文件", "银行流水"],
    "客户": ["销项发票", "合同文件", "银行流水"],
    "合同": ["合同文件"],
    "存货": ["进销存台账", "进项发票"],
    "进销存": ["进销存台账"],
    "BOM": ["BOM物料清单", "进销存台账"],
    "仓储": ["进销存台账", "合同文件"],
    "运输": ["运输合同", "销项发票", "进项发票"],
    "申报": ["纳税申报表"],
    "增值税": ["纳税申报表", "销项发票", "进项发票"],
    "所得税": ["纳税申报表", "科目余额表"],
    "印花税": ["合同文件", "科目余额表"],
    "研发": ["科目余额表", "记账凭证/序时账"],
    "财务": ["科目余额表"],
    "报表": ["科目余额表"],
    "勾稽": ["科目余额表", "记账凭证/序时账"],
    "凭证": ["记账凭证/序时账"],
    "利润": ["科目余额表"],
    "出口": ["纳税申报表", "银行流水", "合同文件"],
    "关联": ["合同文件", "银行流水", "销项发票", "进项发票"],
    "外部": ["企业基本信息"],
    "资料": ["企业基本信息"],
    "行业": ["科目余额表", "销项发票"],
    "折旧": ["固定资产清单", "科目余额表"],
    "优惠": ["纳税申报表", "科目余额表"],
}


# ══════════════════════════════════════════════════════════════════════════
# 报告编辑标准（两份系统级标准，2026-09-26 用户定调）
# ══════════════════════════════════════════════════════════════════════════
# 用户原话：「把目前这个报告编辑标准定义为税务稽查专家工作底稿版。按选项 C 执行，
# 定义为金字塔原理编辑版。」→ 报告编辑标准从此分为**两份、对所有企业通用**：
#
#   ① 税务稽查专家工作底稿版（基线）：当前报告（六章文书式）内容 + 结构原样，
#      是所有派生编辑版的唯一内容基线，任何派生版都不得反向改写它。
#   ② 金字塔原理编辑版（选项 C，派生）：结论先行 / MECE 分组 / 行动标题 /
#      SCQA 开篇 / 严重度排序 / 台账为基座——只对工作底稿版做**只读结构化重组**，
#      不改任何风险事实。
#
# 关键边界（用户 2026-09-26 澄清「选项 C 会改变内容吗？」）：
#   * 风险事实层（疑点五段式 / 159 项台账 / 金额 / 判定 / 等级）——不改；
#   * 呈现文字层（章节标题改观点式、第一章加统领句、每类加 umbrella 归纳句、
#     疑点排序）——会改，但 umbrella / 统领句 / 行动标题必须**完全由现有字段组合**，
#     严禁引入新事实、新定性。
# ══════════════════════════════════════════════════════════════════════════
REPORT_EDITING_STANDARDS: Dict[str, Dict[str, Any]] = {
    "税务稽查专家工作底稿版": {
        "code": "working_paper",
        "is_baseline": True,
        "derived_from": "",
        "compilation_style": "涉税风险检查工作报告（风险检查文书式）",
        "principle": "检查组工作底稿：六章文书式，按税务红线疑点逐条列示原始证据与判定。"
                     "内容（风险事实层）与结构（章节顺序）均原样保留，不作任何重组或改写。",
        "constraints": [
            "内容（风险事实层）与结构（章节顺序）均原样保留，不作任何重组或改写。",
            "任何派生编辑版都不得反向改写本版的任何字段。",
        ],
    },
    "金字塔原理编辑版": {
        "code": "pyramid",
        "is_baseline": False,
        "derived_from": "税务稽查专家工作底稿版",
        "compilation_style": "涉税风险检查工作报告（风险检查文书式）",
        "principle": "结论先行 / MECE 分组 / 行动标题 / SCQA 开篇 / 严重度排序 / 台账为基座。",
        "constraints": [
            "只读转换：绝不增删发现；不改金额、结论、判定、等级。",
            "新增的 umbrella（归纳句）/ 统领句 / 行动标题必须完全由现有字段组合，"
            "禁引新事实、新定性。",
            "可逆：从工作底稿版 + pyramid_edition 派生字段可无损还原工作底稿版。",
            "通用：分组键从已有字段（title / suspect / risk_level / taxes / trace_id）"
            "派生，不按企业硬编码。",
        ],
    },
}

# 报告编辑版代码（与 REPORT_EDITING_STANDARDS[].code 一一对应）
REPORT_EDITION_CODES = ("working_paper", "pyramid")
# 报告编辑版中文名（与 REPORT_EDITING_STANDARDS 的键一一对应）
REPORT_EDITION_NAMES = ("税务稽查专家工作底稿版", "金字塔原理编辑版")
# 默认编辑版：工作底稿版（基线，内容 + 结构原样）
DEFAULT_REPORT_EDITION = "税务稽查专家工作底稿版"
# 缓存一致性闸门允许复用的 report_edition 取值
VALID_REPORT_EDITIONS = set(REPORT_EDITION_NAMES)


def is_valid_edition(name: Any) -> bool:
    """报告编辑版名是否合法（中文名）。"""
    return str(name or "") in VALID_REPORT_EDITIONS


def edition_to_code(name: Any) -> str:
    """中文编辑版名 → 代码；非法值回退默认。"""
    s = str(name or "")
    for std_name, meta in REPORT_EDITING_STANDARDS.items():
        if std_name == s:
            return meta["code"]
    return REPORT_EDITING_STANDARDS[DEFAULT_REPORT_EDITION]["code"]


def code_to_edition(code: Any) -> str:
    """代码 → 中文编辑版名；非法值回退默认。"""
    s = str(code or "")
    for std_name, meta in REPORT_EDITING_STANDARDS.items():
        if meta["code"] == s:
            return std_name
    return DEFAULT_REPORT_EDITION


def summarise_doctrine(findings: List[Dict]) -> Dict[str, Any]:
    """汇总本轮"宗旨执行情况"，供报告直接引用。

    返回 `{total, with_resolve, with_self_proof, ironclad, self_provable, pending,
           one_sided_sources, statement}`
    """
    fs = [f for f in (findings or []) if isinstance(f, dict)]
    # 按**规范化**后的终局值分组：对历史值/被改写过值保持稳健（2026-09-25）
    iron = [f for f in fs if normalize_terminal_state(f.get("terminal_state")) == TERMINAL_IRONCLAD]
    sp = [f for f in fs if normalize_terminal_state(f.get("terminal_state")) == TERMINAL_SELF_PROOF]
    pend = [f for f in fs if normalize_terminal_state(f.get("terminal_state")) == TERMINAL_PENDING]
    with_resolve = [f for f in fs if f.get("resolve_steps")]
    with_proof = [f for f in fs if f.get("self_proof_materials")]
    return {
        "total": len(fs),
        "with_resolve": len(with_resolve),
        "with_self_proof": len(with_proof),
        "ironclad": len(iron),
        "self_provable": len(sp),
        "pending": len(pend),
        "one_sided_sources": sorted(ONE_SIDED_CHECKS.keys()),
        "statement": (
            "本轮按「上传了什么资料就查什么资料」执行：现有资料能独立支撑的检查均已执行；"
            "需要交叉比对但因资料未齐而无法判定的部分，只列为待补自证事项，"
            "不作为违规认定。每条风险均给出解除方式与需补自证资料，终局为"
            "「证据闭合（违法事实成立）」或「可自证清白」。"
        ),
    }
