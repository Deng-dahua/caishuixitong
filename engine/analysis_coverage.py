# -*- coding: utf-8 -*-
"""分析覆盖清单 —— 让"该查什么 / 这轮查了没 / 为什么没查"永远可见（2026-09-25）

═══════════════════════════════════════════════════════════════════════════════
为什么需要（根因）
═══════════════════════════════════════════════════════════════════════════════
一键分析要当"税务稽查人员的替身"，就必须能回答一个问题：
**金税四期该查的点，这一轮到底查了多少？没查的是为什么？**

此前它答不出来，于是出现三类危险情况（都是真实事故）：

  ① **登记了但从不执行**：`TAX_AUDIT_INDICATORS` 14 项里 7 项只在目录里登记、
     全项目零消费点 —— 系统"看着有这项指标"，实际从不计算。
  ② **静默跳过**：损益类科目取数为 0 → `if not income: return` →
     "财务报表分析"域十余项检查一次都不执行，报告里既无结论也无原因。
  ③ **少报被当成没问题**：24 个文件读不到内容 → 发现数从 13 静默降到 7，
     使用者会把"资料不全导致的少报"当成"这家企业没问题"。

**结论：必须把"覆盖情况"本身作为报告的一等输出。**
本模块是这件事的唯一实现：按**每项检查自己声明的资料依赖**（`required_sources`）
判定"可执行 / 缺资料不可执行"，并逐项列出缺什么。

设计原则
--------------------------------------------------
C1 **禁止自造依赖**：一项检查能不能跑，只看它自己声明的 `required_sources`，
   不在本模块另写一套"我认为需要什么"。
C2 **缺资料 ≠ 无风险**：不可执行必须显式列出，并说明对应风险方向无法检查。
C3 **只读**：不参与任何结论计算，不改变 findings。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# `required_sources` 的键 → 中文资料名（用于报告展示；**不是**新的依赖定义）
_SOURCE_ZH = {
    "sal_invs": "销项发票",
    "pur_invs": "进项发票",
    "bank_txs": "银行流水",
    "vouchers": "记账凭证/序时账",
    "tax_declarations": "纳税申报表",
    "declaration": "纳税申报表",
    "inventory_ledger": "进销存台账",
    "inventory": "进销存台账",
    "salaries": "工资表",
    "social_security": "社保明细",
    "company_profile": "企业基本信息",
    "target_entity": "企业基本信息",
    "trial_balance": "科目余额表",
    "fixed_assets": "固定资产清单",
    "transport_contracts": "运输合同",
    "bom": "BOM/物料清单",
    "contracts": "合同文件",
}

# 本轮**已取得数据**的判据：每个 source 键给一个"有没有数据"的探针。
# ⚠ 探针只看"数据是否真的读到了"，不看文件是否在清单里 —— 这正是本轮修的静默缺口。
def _has(engine_data: Dict, key: str) -> bool:
    ed = engine_data or {}
    def _n(v):
        try:
            return len(v or [])
        except TypeError:
            return 1 if v else 0
    if key in ("sal_invs", "pur_invs"):
        # 发票在 engine_data 中以 invoices+方向 或 sal_invs/pur_invs 出现
        if _n(ed.get(key)):
            return True
        invs = ed.get("invoices") or []
        want = "销项" if key == "sal_invs" else "进项"
        return any(str(i.get("direction") or "") == want for i in invs if isinstance(i, dict))
    if key in ("tax_declarations", "declaration"):
        return _n(ed.get("tax_declarations")) > 0
    if key in ("inventory_ledger", "inventory"):
        return _n(ed.get("inventory_ledger") or ed.get("inventory")) > 0
    if key in ("company_profile", "target_entity"):
        return bool(ed.get("target_entity") or ed.get("company_profile"))
    return _n(ed.get(key)) > 0


# 所需资料的**超类关系**（2026-09-26）：红线（或检查项）声明的所需资料常写**泛化名**
# （如「纳税申报表」），而系统按实际提供的是**具体类别名**（如「增值税申报表」）记账。
# 二者不对齐时，声明泛化名的项会被**永久误判为"缺资料"** —— 哪怕用户已经上传并解析了
# 相关申报表（实测：一批声明泛化名的红线因此永远显示缺纳税申报表）。
# 这与既有 P0「`_DOC_TYPE_TO_CATEGORY` 键错配谎报缺申报表」同族：
# **已取得的数据源被判为不存在**。
#
# ★ 规则形态：key = 需求里可能出现的泛化名，value = 能够满足它的具体类别名集合。
#   **新增同类只需在此加一行数据**，不得在判定逻辑里写 `if need == "纳税申报表"` 这类特例。
# ⚠ 安全边界：本模块铁律 C3 **只读**（不参与任何结论计算、不改变 findings），
#   故此处的判定放宽**只影响"覆盖清单"的可判定性表述**，不会像历史 P0 那样
#   把证据误判为「已有」而抬升闭合度/误升级 confirmed。
_MATERIAL_SUPERCLASS: Dict[str, tuple] = {
    "纳税申报表": ("增值税申报表", "企业所得税申报表", "个税申报表", "其他税种申报表"),
    # 以下三条红线的写法与系统类别名不同，但所指是同一事物：
    "个税代扣代缴申报表": ("个税申报表",),
    "个税代扣代缴明细申报表": ("个税申报表",),
    "个税申报明细": ("个税申报表",),
    "交易合同": ("合同文件",),
    # ⚠ 「BOM物料清单」不在系统的 15 类必查资料类别内（尽管 `bom_data` 会被解析），
    #    `present` 由 15 类类别构成，故无法在此登记 —— 属已知能力边界，勿加无效成员。
    #
    # ★ 2026-09-27（P3 收口）：红线库声明的 `required_materials` 里，与系统类别
    #   **同名异写**的需求名在此登记超类映射，使其能被正确识别为"已提供/缺失"，
    #   而不是被永久判为「缺资料」。
    #   ⚠ 只登记**同一事物、不同写法**（或明确由该类资料承载）的映射：
    #     ① 成员必须是系统真实类别（闸门强制，否则 ERROR）；
    #     ② **不是**"系统没有的资料"——那些（如 排污许可证/采矿许可证/完税凭证/
    #        出口报关单/评估报告/成果交付文件…）属**真实能力边界**，必须保留漂移，
    #        绝不硬凑映射冒充"已提供"。
    # —— 申报表类（各税种申报表 → 其他税种申报表；所得税附表 → 企业所得税申报表）
    # ★ 2026-10-01：「土地增值税申报表」已于 material_recognition 登记为具体资料类别
    #   （关键词 8 字压过「增值税申报表」5 字），故本表不再保留该超类键：
    #   ① 超类键必须是泛化需求名（闸门 check_coverage_source_wiring 强制）；
    #   ② 「任一税种申报表」并不等于「土地增值税申报表」，留着映射等于拿泛化资料冒充已提供。
    # ★ 2026-10-02 #461：「印花税申报表」已于 material_recognition 登记为具体资料类别
    #   （解 RL-OTH-001/007/008/009/010/011 六条印花税红线「永远缺资料」的永久缺口），
    #   与上文「土地增值税申报表」同一范式：登记名一旦成为真实系统类别，超类键即删除。
    "城镇土地使用税申报表": ("其他税种申报表",),
    "房产税申报表": ("其他税种申报表",),
    "契税申报表": ("其他税种申报表",),
    "消费税申报表": ("其他税种申报表",),
    "资源税申报表": ("其他税种申报表",),
    "环境保护税申报表": ("其他税种申报表",),
    "附加税费申报表": ("其他税种申报表",),
    "A105090申报表": ("企业所得税申报表",),
    "A106000弥补亏损明细表": ("企业所得税申报表",),
    "历年企业所得税年度纳税申报表": ("企业所得税申报表",),
    "扣缴企业所得税报告表": ("企业所得税申报表",),
    "核定征收申报表": ("企业所得税申报表",),
    "进项转出凭证或申报表": ("增值税申报表",),
    # —— 合同/协议类 → 合同文件
    "劳务合同": ("合同文件",), "劳务派遣协议": ("合同文件",),
    "服务合同": ("合同文件",), "采购合同": ("合同文件",),
    "销售合同": ("合同文件",), "费用合同": ("合同文件",),
    "借款合同": ("合同文件",), "合同台账": ("合同文件",),
    "合同或协议": ("合同文件",), "合同折扣条款": ("合同文件",),
    "合同价外费用条款": ("合同文件",), "委托加工协议": ("合同文件",),
    "委托加工合同": ("合同文件",), "权属转移合同": ("合同文件",),
    # ★ 2026-10-01：「土地出让合同」「股权转让协议及补充协议」已登记为具体资料类别
    #   （各自有独立 doc_type 与最长关键词），不再是"同名异写"→ 移除超类键，
    #   避免一份泛化的《合同文件》被当成土地出让/股权转让协议已提供。
    "资金拆借协议": ("合同文件",), "特许权使用费协议": ("合同文件",),
    "进口合同": ("合同文件",), "仓储合同": ("合同文件",), "租赁合同": ("合同文件",),
    # —— 账簿/序时/原始凭证类 → 记账凭证（系统由凭证与序时账承载）
    "序时账": ("记账凭证",), "现金日记账": ("记账凭证",),
    "会计账簿与凭证": ("记账凭证",), "原始单据": ("记账凭证",),
    "费用明细账": ("记账凭证",), "成本明细账": ("记账凭证",),
    "成本费用明细账": ("记账凭证",), "固定资产明细账": ("记账凭证",),
    "固定资产明细": ("记账凭证",), "研发费用辅助账": ("记账凭证",),
    "开发成本明细账": ("记账凭证",), "费用明细账与凭证": ("记账凭证",),
    # —— 往来/余额类明细 → 科目余额表
    "其他应收款明细": ("科目余额表",), "应付账款明细": ("科目余额表",),
    "往来明细": ("科目余额表",), "往来科目明细": ("科目余额表",),
    # —— 存货/进销存单据类 → 进销存台账
    "存货台账": ("进销存台账",), "入库单": ("进销存台账",),
    "出库单": ("进销存台账",), "出入库单": ("进销存台账",),
    "完工入库单": ("进销存台账",), "出库单与领用单": ("进销存台账",),
    "领料单": ("进销存台账",), "投料单": ("进销存台账",),
    "盘点表": ("进销存台账",), "订单台账": ("进销存台账",),
    "产成品明细账": ("进销存台账",), "存货明细账": ("进销存台账",),
    # —— 资金/结算类 → 银行流水
    "收款凭证与银行流水": ("银行流水",), "收款记录": ("银行流水",),
    "银行对账单": ("银行流水",), "银行余额调节表": ("银行流水",),
    "银行流水与付款凭证": ("银行流水",), "银行流水（含个人账户）": ("银行流水",),
    "收银或平台结算单": ("银行流水",),
    # —— 发票/报表类 → 对应真实类别
    "出口发票": ("销项发票",), "建安发票": ("进项发票",),
    "进项发票与认证记录": ("进项发票",),
    "财务报表": ("资产负债表", "利润表"),
    # —— 人社类
    "社保参保明细": ("社保明细",), "社保缴纳记录": ("社保明细",),
    "社保缴费明细": ("社保明细",),
    "建筑服务合同": ("合同文件",),
    # ★ 2026-10-01：「过磅单与入库验收单」已登记为具体资料类别（长关键词压过「过磅单」），
    #   移除超类键 —— 泛化的<进销存台账>不等于过磅单与入库验收单。
    "银行付款记录": ("银行流水",),
    "工资表与奖金发放记录": ("工资表",),
    # —— 第二批（2026-09-27 复核补遗）：同样是"同名异写"，非能力边界
    "入库验收单": ("进销存台账",), "完工验收单": ("进销存台账",),
    "验收单": ("进销存台账",), "退货单": ("进销存台账",),
    "折让协议": ("合同文件",), "合同": ("合同文件",),
    "采购合同与进项发票": ("合同文件", "进项发票"),
    "销售发票与台账": ("销项发票",),
    "开票系统导出文件": ("销项发票", "进项发票"),
    "年度汇算清缴记录": ("企业所得税申报表",),
    "劳务费支付凭证": ("银行流水",), "收汇水单": ("银行流水",),
    "销项税额计提凭证": ("记账凭证",),
}


def _material_satisfied(need: str, present) -> bool:
    """所需资料 `need` 是否被已提供资料 `present` 满足：精确名，或超类任一成员已提供。"""
    if need in present:
        return True
    members = _MATERIAL_SUPERCLASS.get(need) or ()
    return any(m in present for m in members)


# ── 金税四期量化指标的数据依赖（**唯一权威**）────────────────────────────────
# ★ 2026-10-06：原为 `build_coverage` 内的局部变量 `_IND_SRC`，
#   导致任何外部审计脚本无法引用同一张表（只能自己再抄一份 = 同一概念两处实现）。
#   提到模块级：既是本模块的依赖声明，也是 `scripts/_audit_executed_items.py` 的取数依据。
_IND_SRC: Dict[str, list] = {
    "revenue_declaration_ratio": ["sal_invs", "tax_declarations"],
    "unbilled_revenue_ratio": ["sal_invs", "tax_declarations"],
    "cost_income_ratio": ["trial_balance"],
    "purchase_invoice_match": ["pur_invs", "trial_balance"],
    "expense_revenue_ratio": ["trial_balance"],
    "travel_entertainment_ratio": ["trial_balance", "vouchers"],
    "receivable_turnover": ["trial_balance", "sal_invs"],
    "inventory_turnover": ["trial_balance"],
    "asset_liability_ratio": ["trial_balance"],
    "operating_cashflow_quality": ["bank_txs", "trial_balance"],
    "cash_sales_match": ["bank_txs", "trial_balance"],
    "owner_equity_change": ["trial_balance"],
    "revenue_growth_surge": ["__cross_period__"],
    "cost_surge_detect": ["__cross_period__"],
}


def build_coverage(engine_data: Optional[Dict] = None,
                   executions: Optional[List[Dict]] = None) -> Dict:
    """生成本轮**分析覆盖清单**。

    :param engine_data: 与本轮分析同源的输入数据（各 source 键）
    :param executions: `run_verified_rules()` 返回的 `executions`（**执行回执**）。
        ★ 2026-10-06：不传则不臆断"已执行"，只标 `executed_basis="资料齐备（无执行回执）"`。

    返回：
        {
          "total": 应检查项总数,
          "executed": **真的执行了**的项数（原子规则以执行回执为准）,
          "blocked": 因缺资料不可执行的项数,
          "not_executed": 资料齐备、引擎却没执行的项数（★ 应为 0；非 0 即系统缺陷，非企业问题）,
          "executed_ratio": 0~1,
          "blocked_items": [ {name, kind, missing: [中文资料名], effect} ],
          "not_executed_items": [ {…, run_status, executed_basis} ],
          "missing_sources": {中文资料名: 阻碍的检查项数},
          "summary_text": "一句话结论",
        }

    铁律（C2）：`blocked_items` 必须逐项列出、不得为空缺省；
    宁可说"这项没查、因为缺 X"，也绝不静默略过。
    ★ 铁律（C4，2026-10-06）：**"资料齐备" ≠ "已执行"**。
      `executed` 只能由**执行回执**证明；查不到回执就必须如实降级为"未执行"，
      绝不用"数据在"冒充"跑过了"——那正是覆盖率虚报的根因。
    """
    from engine.verified_rule_engine import VERIFIED_RULE_CATALOG, _spec_applies_to_entity
    from engine.tax_redlines import all_redlines

    ed = engine_data or {}
    items: List[Dict] = []

    # ★★★ 2026-10-05（用户要求「一键分析必须执行100%覆盖率；能查的全查完」）：
    #   **业态剔除必须在下标构建之前算出来，且三段（原子规则/税务指标/税务红线）全用**。
    #   原实现只在**税务红线段**用了 `_na_docs`，原子规则段与税务指标段没用 ⇒
    #   服务型企业被算了「进销存台账」（8 项）、「入库单」（5 项）、「存货台账」（5 项）
    #   等**本业态天然不适用**的检查项进分母，覆盖率被虚低到 46%，
    #   且企业永远补不齐（它本来就没有实物货物流转）。
    #   判据唯一权威：`industry_resolver.not_required_materials`（业态 skip_domains 驱动）。
    _na_docs: set = set()
    try:
        from engine.industry_resolver import not_required_materials as _nrm
        _te = ed.get("target_entity") or {}
        _ind = str((_te or {}).get("industry_resolved") or (_te or {}).get("industry") or "") \
            or str((ed.get("company_profile") or {}).get("industry") or "")
        if _ind:
            _na_docs = {str(x) for x in (_nrm(_ind)[0] or ())}
    except Exception:
        _na_docs = set()

    def _na(s: str) -> bool:
        """该资料在本业态**不适用**（不进分母、也不算缺口）。"""
        return _SOURCE_ZH.get(s, s) in _na_docs

    # ══════════════════════════════════════════════════════════════════════════
    # ★★★ 2026-10-06 执行回执：「资料齐备」**不等于**「已经跑过」
    #   用户原话：「一键分析按钮必须执行100%覆盖率」「能查的全查完即可」。
    #   而 `executed` 原定义为 `len(items) - len(blocked)`，其中
    #   `blocked := missing 非空`、`missing := 声明的 required_sources 里 engine_data 没数据`——
    #   它证明的只是「声明所需资料本轮齐备」，**不能**证明该项被引擎执行过。
    #   二者之间还隔着执行器的口径差（见下方 ①）与运行期异常。
    #   修法：判定"缺什么 / 跑没跑"一律以**执行回执**为准（与执行器同一权威）。
    #   回执形如 `[{"rule_id": "VR001", "status": "triggered"|"completed_not_triggered"
    #                |"not_run_missing_data"|"skipped_industry"|"execution_error", ...}]`
    # ══════════════════════════════════════════════════════════════════════════
    _RAN = ("triggered", "completed_not_triggered")
    _BASIS = {
        "not_run_missing_data": "引擎未执行：缺执行器认定的必需数据源",
        "skipped_industry": "引擎未执行：本业态不适用（行业门槛跳过）",
        "execution_error": "引擎执行异常（见 executions[].message）",
    }
    _rcpt = {str((e or {}).get("rule_id") or ""): (e or {}) for e in (executions or [])}
    _has_receipt = executions is not None

    # ① 已验原子规则（73 条）：按其声明的 required_sources 判定
    catalog = VERIFIED_RULE_CATALOG
    catalog = catalog if isinstance(catalog, list) else list(catalog.values())
    _te = ed.get("target_entity") or {}
    for r in catalog:
        if not isinstance(r, dict):
            continue
        # ★★ 2026-10-06（用户：「能查的全查完即可」）：**适用性判定必须与执行器同源**。
        #   执行器 `run_verified_rules` 在 `_spec_applies_to_entity(spec, target_entity)`
        #   为假时记 `skipped_industry`（该规则对本企业不适用，本就不该跑）。
        #   本模块原实现**不做这道闸**，于是服务业企业被算了
        #   「生产用能源消耗」（VR014，industries 仅 A/B/C/D）、
        #   「进销物耗投入产出比」（VR023）等**本业态规则级不适用**的项进分母，
        #   且因资料"看得到"（进项发票）反被判为 `executed` ⇒ **覆盖率虚报**。
        #   判据唯一权威：`verified_rule_engine._spec_applies_to_entity`（与执行器同一函数）。
        if not _spec_applies_to_entity(r, _te):
            continue
        srcs = [str(s) for s in (r.get("required_sources") or []) if s]
        if not srcs:
            continue
        # ★ 2026-10-05：**先剔除本业态不适用的源**；若该检查项全部源都不适用，
        #   说明"这项检查本业态天然没有" ⇒ **不进分母**（不是"没查"，也不是"缺资料"），
        #   否则服务型企业会永远挂着一批它不可能提供的资料，覆盖率被永久虚低。
        srcs = [s for s in srcs if not _na(s)]
        if not srcs:
            continue
        # ── ★★ 2026-10-06 判缺口径必须与执行器一致 ──────────────────────────────
        #   执行器 `run_verified_rules` 按 `required_sources` 的**原始声明**判缺
        #   （不剔业态不适用源）。若本模块用"剔过 `_na` 之后"的清单判缺，两套口径必然分叉：
        #   实测 VR044「库存积压与收入背离」声明 `[inventory_ledger, declaration, sal_invs]`，
        #   服务业企业 `inventory_ledger` 不适用被剔 ⇒ 本模块判 `missing=[]` 计"已执行"，
        #   执行器却因缺 `inventory_ledger` 记 `not_run_missing_data` ⇒ **声称查了、其实没跑**。
        #   现以**执行回执**为准（同一权威）；无回执时才退回本模块探针。
        #   规则：执行器缺的源若**全是本业态不适用资料** ⇒ 该检查对本业态不成立 ⇒ 不进分母。
        _rec = _rcpt.get(str(r.get("id") or "")) if _rcpt else None
        if _rec is not None and str(_rec.get("status") or "") == "not_run_missing_data":
            _m_raw = [str(x) for x in (_rec.get("missing_sources") or [])]
            if not [s for s in _m_raw if not _na(s)]:
                continue          # 缺的全是业态不适用 ⇒ 本项对本业态不成立
        missing = [s for s in srcs if not _has(ed, s)]
        items.append({
            "kind": "原子规则",
            "name": str(r.get("name") or r.get("id") or ""),
            "id": str(r.get("id") or ""),
            "missing": [_SOURCE_ZH.get(s, s) for s in missing],
            "effect": str(r.get("limitation") or "")[:160],
        })

    # ② 金税四期量化指标（14 项）：逐项声明其数据依赖
    from engine.financial_analyzer import TAX_AUDIT_INDICATORS
    for key, meta in (TAX_AUDIT_INDICATORS or {}).items():
        need = _IND_SRC.get(key) or ["trial_balance"]
        if "__cross_period__" in need:
            items.append({
                "kind": "税务指标", "name": str(meta.get("name") or key), "id": key,
                "missing": ["上期（跨期）报表"],
                "effect": "单期资料无法计算同比增幅，需提供上期报表后方可判定。",
            })
            continue
        # ★ 2026-10-05：同 ①，本业态不适用的源要剔除；全不适用则不进分母。
        need = [s for s in need if not _na(s)]
        if not need:
            continue
        missing = [s for s in need if not _has(ed, s)]
        items.append({
            "kind": "税务指标", "name": str(meta.get("name") or key), "id": key,
            "missing": [_SOURCE_ZH.get(s, s) for s in missing],
            "effect": str(meta.get("tax_impact") or "")[:160],
        })

    # ★★ 2026-10-03（用户："服务类采购本无物流"）：**资料要求必须跟随业态**——
    #   服务型企业天然无实物货物流转，"物流单据/入库验收单/出库单"对其**不适用**；
    #   若仍列为"缺失"，受限清单会永远挂着一项企业根本不可能提供的资料，
    #   让"资料齐全"永远达不到、也让"该红线检查受限"变成无根据的指责。
    #   判据唯一权威：`industry_resolver.not_required_materials`（业态 skip_domains 驱动）。
    #   （`_na_docs` 已在函数开头算出，此处不再重复计算 —— 见上方 ★★★ 2026-10-05 说明。）

    # ③ 税务红线（68 条）：红线是"命中"概念，但可按其 required_materials 判定
    #    "本轮是否具备判定条件"——不具备则不可能是"排除"，只能说"未能检查"。
    for rl in all_redlines():
        mats = [str(m) for m in (rl.get("required_materials") or []) if m]
        if not mats:
            continue
        # ★ 2026-10-05（用户：「能查的全查完即可」）：**本业态不适用 ⇒ 该红线不进分母**。
        #   原实现只把不适用资料从 `missing` 里剔掉，检查项**本身仍进 items** ⇒
        #   服务型企业被算了「运输费与产销规模背离」「库存积压与收入背离」这类
        #   只依赖"运输合同/进销存台账"（本业态天然没有）的检查项，
        #   missing 剔完为空 ⇒ 反被算成"已执行"，既不准也掩盖了真实覆盖情况。
        mats = [m for m in mats if m not in _na_docs]
        if not mats:
            continue
        _present = ed.get("_available_materials") or []
        # ★ 必须用超类判定，不能用裸 `m not in _present`：泛化名会永远判缺
        #  ★ 剔除本业态不适用资料（如服务型企业的货物流类）——不构成缺失
        missing = [m for m in mats
                   if m not in _na_docs and not _material_satisfied(m, _present)]
        items.append({
            "kind": "税务红线",
            "name": str(rl.get("name") or ""),
            "id": str(rl.get("id") or ""),
            "missing": missing,
            "effect": "所需资料不齐时，该红线既不能认定、也不能排除，属检查受限。",
        })

    # ══════════════════════════════════════════════════════════════════════════
    # 逐项打「执行回执」标记（判据统一在此，勿在各段各写一份）
    # ══════════════════════════════════════════════════════════════════════════
    for it in items:
        if it.get("kind") != "原子规则":
            # 指标/红线暂无独立回执通道：如实标注口径，不冒充"引擎已执行"。
            it["executed_basis"] = "资料齐备（非回执口径）"
            continue
        rec = _rcpt.get(it.get("id") or "")
        if rec is None:
            it["run_status"] = ""
            it["executed_basis"] = ("资料齐备（未取得执行回执）" if _has_receipt
                                    else "资料齐备（无执行回执通道）")
            continue
        st = str(rec.get("status") or "")
        it["run_status"] = st
        it["executed_basis"] = ("引擎已执行（%s）" % st) if st in _RAN else _BASIS.get(
            st, "引擎未执行：" + (st or "状态缺失"))

    def _really_executed(it: Dict) -> bool:
        """该项是否**真的跑了**。

        · 原子规则：仅当执行回执为 `triggered`/`completed_not_triggered`。
          ★ 未传回执时（`_has_receipt=False`）退回"资料齐备"口径并保留如实标注，
            绝不把"没回执"当成"已执行"再对外声称。
        · 指标/红线：无回执通道，按资料齐备计（口径写在 `executed_basis`）。
        """
        if it.get("kind") != "原子规则":
            return True
        if not _has_receipt:
            return True
        return str(it.get("executed_basis") or "").startswith("引擎已执行")

    blocked = [it for it in items if it["missing"]]
    _blocked_ids = {id(it) for it in blocked}
    # 未执行 = 资料齐备、且不在缺资料桶里，但执行回执证明没跑（或压根没回执）
    not_executed = [it for it in items
                    if id(it) not in _blocked_ids and not _really_executed(it)]
    executed_items = [it for it in items
                      if id(it) not in _blocked_ids and _really_executed(it)]
    executed = len(executed_items)
    miss_stat: Dict[str, int] = {}
    for it in blocked:
        for m in it["missing"]:
            miss_stat[m] = miss_stat.get(m, 0) + 1
    top_miss = sorted(miss_stat.items(), key=lambda kv: -kv[1])[:6]

    ratio = round(executed / len(items), 4) if items else 0.0
    if not items:
        summary = ""
    elif not blocked and not not_executed:
        summary = f"本轮应检查 {len(items)} 项，现有资料已支撑全部检查项执行。"
    else:
        # ★ 2026-09-25 语义纠正（用户宗旨）：
        #   原文案"因缺资料**未能执行**"暗示"系统在等资料齐全"，与宗旨相悖。
        #   正确表述是：现有资料能查的**已经查尽**；其余不是"没查"，
        #   而是"需要交叉比对、必须等企业补充资料后才能判定"——
        #   它是**待补自证事项**，不是未执行事项，更不是违规线索。
        summary = (
            f"本轮按「上传了什么资料就查什么资料」执行：应检查 {len(items)} 项，"
            f"其中现有资料已足以判定 {executed} 项（已全部执行），"
            f"另有 {len(blocked)} 项需与企业补充资料交叉比对后方可判定（已全部列为待补自证事项）。"
            + ("须补充的资料主要为：" + "、".join(f"{k}（涉及 {v} 项）" for k, v in top_miss) + "。"
               if top_miss else "")
            + "上述待补事项在资料补齐前一律不作违规认定；补齐后重新分析即可得到完整结论。"
        )
        if not_executed:
            # ★ 这类不是企业的问题，是**系统自身**的问题，必须独立点名、不得混进"待补资料"。
            summary += (f"⚠ 另有 {len(not_executed)} 项资料齐备却未取得执行回执，"
                        f"属系统执行缺口，须逐项核因（不得对外表述为已检查）。")

    return {
        "total": len(items),
        "executed": executed,
        "blocked": len(blocked),
        "not_executed": len(not_executed),
        "executed_ratio": ratio,
        "awaiting_self_proof": len(blocked),
        "items": items,
        "executed_items": executed_items,
        "blocked_items": blocked,
        "not_executed_items": not_executed,
        "missing_sources": dict(top_miss),
        "summary_text": summary,
    }
