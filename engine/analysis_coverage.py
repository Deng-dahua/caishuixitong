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
    "印花税申报表": ("其他税种申报表",),
    "土地增值税申报表": ("其他税种申报表",),
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
    "土地出让合同": ("合同文件",), "资金拆借协议": ("合同文件",),
    "股权转让协议及补充协议": ("合同文件",), "特许权使用费协议": ("合同文件",),
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


def build_coverage(engine_data: Optional[Dict] = None) -> Dict:
    """生成本轮**分析覆盖清单**。

    返回：
        {
          "total": 应检查项总数,
          "executed": 资料齐备、可执行的项数,
          "blocked": 因缺资料不可执行的项数,
          "executed_ratio": 0~1,
          "blocked_items": [ {name, kind, missing: [中文资料名], effect} ],
          "missing_sources": {中文资料名: 阻碍的检查项数},
          "summary_text": "一句话结论（含"结论基于不完整资料"提示）",
        }

    铁律（C2）：`blocked_items` 必须逐项列出、不得为空缺省；
    宁可说"这项没查、因为缺 X"，也绝不静默略过。
    """
    from engine.verified_rule_engine import VERIFIED_RULE_CATALOG
    from engine.tax_redlines import all_redlines

    ed = engine_data or {}
    items: List[Dict] = []

    # ① 已验原子规则（73 条）：按其声明的 required_sources 判定
    catalog = VERIFIED_RULE_CATALOG
    catalog = catalog if isinstance(catalog, list) else list(catalog.values())
    for r in catalog:
        if not isinstance(r, dict):
            continue
        srcs = [str(s) for s in (r.get("required_sources") or []) if s]
        if not srcs:
            continue
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
    _IND_SRC = {
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
    for key, meta in (TAX_AUDIT_INDICATORS or {}).items():
        need = _IND_SRC.get(key) or ["trial_balance"]
        if "__cross_period__" in need:
            items.append({
                "kind": "税务指标", "name": str(meta.get("name") or key), "id": key,
                "missing": ["上期（跨期）报表"],
                "effect": "单期资料无法计算同比增幅，需提供上期报表后方可判定。",
            })
            continue
        missing = [s for s in need if not _has(ed, s)]
        items.append({
            "kind": "税务指标", "name": str(meta.get("name") or key), "id": key,
            "missing": [_SOURCE_ZH.get(s, s) for s in missing],
            "effect": str(meta.get("tax_impact") or "")[:160],
        })

    # ③ 税务红线（68 条）：红线是"命中"概念，但可按其 required_materials 判定
    #    "本轮是否具备判定条件"——不具备则不可能是"排除"，只能说"未能检查"。
    for rl in all_redlines():
        mats = [str(m) for m in (rl.get("required_materials") or []) if m]
        if not mats:
            continue
        _present = ed.get("_available_materials") or []
        # ★ 必须用超类判定，不能用裸 `m not in _present`：泛化名会永远判缺
        missing = [m for m in mats if not _material_satisfied(m, _present)]
        items.append({
            "kind": "税务红线",
            "name": str(rl.get("name") or ""),
            "id": str(rl.get("id") or ""),
            "missing": missing,
            "effect": "所需资料不齐时，该红线既不能认定、也不能排除，属检查受限。",
        })

    blocked = [it for it in items if it["missing"]]
    executed = len(items) - len(blocked)
    miss_stat: Dict[str, int] = {}
    for it in blocked:
        for m in it["missing"]:
            miss_stat[m] = miss_stat.get(m, 0) + 1
    top_miss = sorted(miss_stat.items(), key=lambda kv: -kv[1])[:6]

    ratio = round(executed / len(items), 4) if items else 0.0
    if not items:
        summary = ""
    elif not blocked:
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

    return {
        "total": len(items),
        "executed": executed,
        "blocked": len(blocked),
        "executed_ratio": ratio,
        "awaiting_self_proof": len(blocked),
        "blocked_items": blocked,
        "missing_sources": dict(top_miss),
        "summary_text": summary,
    }
