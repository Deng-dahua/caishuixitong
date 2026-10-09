"""进项异常凭证 / 应转出未转出 比对引擎 —— 第四阶 P1 能力。

背景：数电票下"票表比对"只校验"已开票 vs 已申报"，并不能识别：
  1) 异常抵扣凭证（上游走逃失联、非正常户开具的专票，受票方进项税须作转出/不得抵扣）；
  2) 应进项转出未转出（购进用于免税项目、集体福利、个人消费、非正常损失等，
     进项税已抵扣但未作转出）。
这两类风险票表比对自动通过，需逐票核对进项勾选与异常凭证清单才能暴露。

本模块作为独立 capability（与 bank_flow / two_tax_income 同构），
扫描进项发票，量化异常抵扣敞口与应转出未转出额，输出 comprehensive["input_voucher"]。

输入：
  pur_invs       : 进项发票列表（_parse_invoice_sheet 行，含 seller/seller_tax/goods/amount/tax/total/invoice_no/date）
  sal_invs       : 销项发票列表（可选，用于"供应商=客户"自循环检测）
  abnormal_list  : 异常凭证清单（可选，list of 供应商名称或税号，标记为走逃/非正常户）
  cross_enterprise: comprehensive["cross_enterprise"]（可选，用于把系统内关联企业名纳入异常候选）
  company_name   : 企业名称

输出：与 external_verifier / bank_flow 对齐的 dict。
"""

from engine.numparse import to_number  # ★ 2026-09-25 统一数值解析（唯一实现）
import re
import time
from collections import defaultdict

# 不得抵扣用途关键词（出现于货物/项目名，提示进项税应作转出未转出）
_NON_DEDUCTIBLE_KW = (
    "福利", "职工", "个人消费", "免税", "简易计税", "非正常损失", "业务招待",
    "交际应酬", "餐饮", "集体", "个人", "奖品", "礼品", "购物卡", "招待",
)

# 顶额/集中虚开：单一供应商占进项金额比例超此值需关注
_CONCENTRATION_THRESHOLD = 0.70


def _safe(v):
    """数值解析（统一实现）。

    ★ 2026-09-25 收敛：实现已统一到 engine/numparse.py（唯一权威）。
      原私有实现遇 "12,000.00" / "￥1,234.56" 等会静默返回 0，
      导致同一金额在不同模块被算成不同值（报告自相矛盾 / 规则漏触发）。
    """
    from engine.numparse import to_number as _to_number
    return _to_number(v)


def _name(inv):
    return str(inv.get("seller", inv.get("销方名称", inv.get("销售方名称", ""))) or "").strip()


def _taxid(inv):
    return str(inv.get("seller_tax", inv.get("销方税号", inv.get("销售方纳税人识别号", ""))) or "").strip()


def _goods(inv) -> str:
    """字段读取/语义判定（统一实现）。

    ★ 2026-09-25 收敛：实现已统一到 engine/fieldkit.py（唯一权威）。
      原多份私有实现互相不一致，导致同一张发票在不同检测器里结论不同。
    """
    from engine.fieldkit import goods_name as _fk
    return _fk(inv)


def run_input_voucher_check(pur_invs, sal_invs=None, abnormal_list=None,
                             cross_enterprise=None, company_name="",
                             input_vat_deductions=None):
    """扫描进项发票，量化异常抵扣凭证与应转出未转出敞口。返回对齐 dict。

    ★★ 2026-10-06（用户：「**你核实了发票类型没有？**」）：
      「应转出**未转出**」的前提是「**已经抵扣**」，而"是否已抵扣"只写在
      **进项认证抵扣明细**（`勾选状态` / `有效抵扣税额`），取票表里没有。
      旧实现只看取票表的**票面税额**就断言"应转出未转出"，等于把"票上印了多少"当成"已经抵扣了多少"。
      实测（某传媒企业数字传媒）：被判"应转出未转出 3,996.91 元"的 146 张发票
      **全部是「数电发票（普通发票）」**，且**一张都没进抵扣表**（255 张抵扣表记录全部能在取票中
      找到，但方向相反——抵扣表是取票的子集，不包含这 146 张）⇒ **从未抵扣，无转出义务**。
      故本函数现在按三态分流（判据全部来自资料本身，不猜）：
        · **可抵扣票种（专票）且已抵扣** → 计入 `应转出未转出`（金额取**有效抵扣税额**，不取票面税额）
        · **不可抵扣票种（普通发票）或未勾选** → 计入 `无需转出`（有票种/勾选证据，结论明确）
        · **无票种也无抵扣记录** → 计入 `待核`（**不给金额**，只列待核线索）
    """
    input_vat_deductions = input_vat_deductions or []
    _ded_by_no = {}
    for _d in input_vat_deductions:
        if not isinstance(_d, dict):
            continue
        for _k in (_d.get("digital_invoice_no"), _d.get("invoice_no"),
                   _d.get("inv_no"), _d.get("digital_inv_no")):
            _s = re.sub(r"\D", "", str(_k or ""))
            if _s:
                _ded_by_no.setdefault(_s, _d)
    if not pur_invs:
        return {
            "available": False,
            "ok": True,
            "title": "进项异常凭证 / 应转出未转出比对",
            "summary": "本轮未提供进项发票（采购专票）数据。",
            "body": "进项异常凭证（上游走逃失联、非正常户开具）与应进项转出未转出（购进用于免税、"
                    "集体福利、个人消费、非正常损失等）是数电票下票表比对仍会自动放行的风险点，"
                    "需逐票核对进项勾选与异常凭证清单。未提供进项发票则无法量化。",
            "metrics": {},
            "signals": [],
            "verdict": "未提供进项发票",
            "recommendation": "上传进项发票/进项抵扣勾选明细（含销方名称、税号、货物名称、金额、税额），"
                              "并粘贴上游异常凭证清单（走逃失联/非正常户名单）。",
            "note": "进项异常凭证比对结论属「待证线索」：异常凭证清单需来自税局官方公告或进项发票查询平台，"
                    "应转出未转出需结合用途明细账核实，不作为定性依据。",
        }

    # ── 按供应商聚合 ──
    sup = defaultdict(lambda: {"count": 0, "amount": 0.0, "tax": 0.0,
                               "non_ded_tax": 0.0, "non_ded_goods": []})
    input_tax_total = 0.0
    input_amount_total = 0.0
    non_deductible_tax = 0.0        # 应转出未转出（**专票且已抵扣**，取有效抵扣税额）
    no_reversal_tax = 0.0           # 无需转出（普票 / 未勾选，有证据）
    pending_tax = 0.0               # 待核（无票种亦无抵扣记录，**不给结论金额**）
    _hit_kw_rows = defaultdict(int)  # 实际命中的关键词 → 张数
    _no_rev_sup = []                 # 无需转出的供应商（含票种）
    _pending_sup = []                # 待核供应商

    for inv in pur_invs:
        nm = _name(inv)
        amt = _safe(inv.get("amount"))
        tax = _safe(inv.get("tax"))
        input_tax_total += tax
        input_amount_total += amt
        if nm:
            d = sup[nm]
            d["count"] += 1
            d["amount"] += amt
            d["tax"] += tax
        g = _goods(inv)
        _hit = [k for k in _NON_DEDUCTIBLE_KW if k in g]
        if _hit:
            for _k in set(_hit):
                _hit_kw_rows[_k] += 1
            # ★★ 三态分流（判据全部来自资料本身，不猜；详见函数 docstring）
            _no = ""
            for _cand in (inv.get("digital_inv_no"), inv.get("inv_no"),
                          inv.get("digital_invoice_no"), inv.get("invoice_no")):
                _no = re.sub(r"\D", "", str(_cand or ""))
                if _no:
                    break
            _ded = _ded_by_no.get(_no) or {}
            # 票种：取票侧字段 `inv_type`（本轮补上）或抵扣表 `invoice_type`
            _itype = str(inv.get("inv_type") or inv.get("invoice_type")
                         or _ded.get("invoice_type") or "").strip()
            _is_special = "专用发票" in _itype
            _is_general = ("普通发票" in _itype) or ("general" in _itype.lower())
            _dtax = to_number(_ded.get("deductible_tax")) if _ded else 0.0
            _status = str((_ded or {}).get("status") or inv.get("inv_status") or "").strip()
            _deducted = _dtax > 0 or ("已勾选" in _status)
            if _is_special and _deducted:
                # 可抵扣票种 + 已抵扣 ⇒ 确属"应转出"；金额取**有效抵扣税额**
                _amt_out = _dtax if _dtax > 0 else tax
                non_deductible_tax += _amt_out
                if nm:
                    sup[nm]["non_ded_tax"] += _amt_out
                    if len(sup[nm]["non_ded_goods"]) < 6:
                        sup[nm]["non_ded_goods"].append(
                            f"{g[:16]}({'、'.join(sorted(set(_hit)))}；已抵扣{_amt_out:,.2f})")
            elif _is_general or (_is_special and not _deducted):
                # 普通发票（本就不可抵扣）或专票但未勾选 ⇒ **不存在"应转出未转出"**
                no_reversal_tax += tax
                if nm and len(_no_rev_sup) < 8:
                    _no_rev_sup.append("%s（%s，%s，票面税额%s）"
                                       % (nm, _itype or "票种不明", _status or "未勾选", f"{tax:,.2f}"))
            else:
                # 既无票种也无抵扣记录 ⇒ **不得给结论金额**，只作待核
                pending_tax += tax
                if nm and len(_pending_sup) < 8:
                    _pending_sup.append("%s（%s）" % (nm, g[:16]))

    # ── 异常凭证清单 → 异常抵扣 ──
    abnormal_set = set()
    for a in (abnormal_list or []):
        s = str(a or "").strip()
        if s:
            abnormal_set.add(s)
    # 把系统内关联企业名（疑似同一控制）也纳入异常候选（仅作待证，须外部清单确认）
    ce = cross_enterprise or {}
    ce_names = set()
    for rel in (ce.get("relationships") or []):
        for key in ("company_a", "company_b"):
            v = str(rel.get(key, "") or "").strip()
            if v:
                ce_names.add(v)
    for ent in (ce.get("companies") or []):
        v = str(ent.get("name", "") or "").strip()
        if v:
            ce_names.add(v)

    abnormal_deduction_tax = 0.0
    abnormal_suppliers = []
    matched_abnormal = set()
    for nm, d in sup.items():
        is_abn = nm in abnormal_set
        # 关联企业名做子串匹配（如"中山市XX建材有限公司"与"中山市XX建材"）
        if not is_abn and ce_names:
            if any((nm and (nm in cn or cn in nm)) for cn in ce_names if len(cn) >= 4):
                is_abn = True
        if is_abn:
            abnormal_deduction_tax += d["tax"]
            matched_abnormal.add(nm)
            abnormal_suppliers.append(f"{nm}（{d['count']}张，税额{d['tax']:,.2f}元）")

    # ── 供应商高度集中（集中顶额虚开嫌疑）──
    top_name = ""
    top_amount = 0.0
    for nm, d in sup.items():
        if d["amount"] > top_amount:
            top_amount = d["amount"]
            top_name = nm
    concentration_ratio = (top_amount / input_amount_total) if input_amount_total else 0.0

    # ── 供应商=客户 自循环（资金回流/对开嫌疑）──
    sal_buyers = set()
    for i in (sal_invs or []):
        b = str(i.get("buyer", i.get("购方名称", i.get("购买方名称", ""))) or "").strip()
        if b:
            sal_buyers.add(b)
    circular_suppliers = []
    for nm, d in sup.items():
        if nm and nm in sal_buyers:
            circular_suppliers.append(f"{nm}（既是供应商{d['amount']:,.2f}元，又是客户）")
    # 2026-09-14 纠偏：互为供需本身完全正常（委托加工/售后回购/集团内购销/商贸双向贸易/
    # 传媒·广告·IT·咨询业互采服务资源）。只有**同额对开**或**购销品名无关且金额重大**
    # 才构成对开嫌疑，其余仅作名单列示，不得据此判"自循环/对开"并抬高整体结论等级。
    circular_mirror, circular_unrelated = [], []
    try:
        from engine.domain_analysis import classify_cross_direction as _ccd
        _cd_invs = []
        for i in (pur_invs or []):
            _n = str(i.get("seller", i.get("销方名称", "")) or "").strip()
            if _n:
                _cd_invs.append({"direction": "进项", "seller": _n,
                                 "goods": i.get("goods", i.get("货物或应税劳务名称", "")),
                                 "amount": i.get("amount")})
        for i in (sal_invs or []):
            _n = str(i.get("buyer", i.get("购方名称", i.get("购买方名称", ""))) or "").strip()
            if _n:
                _cd_invs.append({"direction": "销项", "buyer": _n,
                                 "goods": i.get("goods", i.get("货物或应税劳务名称", "")),
                                 "amount": i.get("amount")})
        _cd = _ccd(_cd_invs)
        circular_mirror = _cd["mirror"]
        circular_unrelated = _cd["unrelated"]
    except Exception:
        pass

    # ── 信号与结论 ──
    signals = []
    sev_high = False
    sev_mid = False

    if abnormal_deduction_tax > 0:
        sev_high = True
        signals.append({
            "signal": f"存在{len(abnormal_suppliers)}家异常凭证供应商，涉及异常抵扣税额{abnormal_deduction_tax:,.2f}元",
            "hint": "上游走逃失联/非正常户开具的专票，受票方进项税不得抵扣或须作进项转出；"
                    f"需逐票核对异常凭证清单与进项勾选，已抵扣的应作转出并补缴。异常供应商：{'、'.join(abnormal_suppliers[:6])}。",
        })

    if concentration_ratio >= _CONCENTRATION_THRESHOLD and top_name:
        sev_high = True if concentration_ratio >= 0.85 else sev_mid
        signals.append({
            "signal": f"供应商高度集中：{top_name} 占进项金额{concentration_ratio*100:.1f}%（{top_amount:,.2f}元）",
            "hint": "单一供应商占比畸高，存在集中顶额开票/虚接受发票嫌疑；结合该供应商经营规模、"
                    "资金回流（是否回流至本企业）与货物真实入库核实。",
        })

    if non_deductible_tax > 0:
        sev_mid = True
        targets = []
        for nm, d in sup.items():
            if d["non_ded_tax"] > 0 and len(targets) < 6:
                targets.append(f"{nm}：{d['non_ded_tax']:,.2f}元（{'、'.join(d['non_ded_goods'][:3])}）")
        # ★ 依据文字必须写**实际命中的关键词**（旧文案写死"福利/职工/个人消费/免税/业务招待"，
        #   而本例实际命中的是「餐饮」「礼品」⇒ 读者按文案去核，一个都找不到）。
        _kw_txt = "、".join("%s（%d张）" % (k, v)
                           for k, v in sorted(_hit_kw_rows.items(), key=lambda kv: -kv[1])[:6])
        signals.append({
            "signal": f"购进项目含不得抵扣用途，应进项转出未转出税额约{non_deductible_tax:,.2f}元",
            "hint": f"命中不得抵扣用途关键词：{_kw_txt}。**已核实为可抵扣票种且已勾选抵扣**"
                    f"（金额取有效抵扣税额），故应作进项转出；"
                    f"需结合用途明细账核实是否已转出。涉及：{'；'.join(targets)}。",
        })
    if no_reversal_tax > 0:
        # ★ 有票种/勾选证据证明"无需转出" ⇒ 明确写出来（**不列为风险**，但要让读者知道系统核过了）
        signals.append({
            "signal": f"另有{no_reversal_tax:,.2f}元票据项目属不得抵扣用途，但**无需转出**（已核实票种/勾选状态）",
            "hint": "这些票据为**普通发票**（本就不作为抵扣凭证）或**未勾选抵扣**，"
                    "不存在「已抵扣应转出」的情形；如与实际情况不符，请提供抵扣勾选记录核对。"
                    + ("涉及：" + "；".join(_no_rev_sup[:5]) + "。" if _no_rev_sup else ""),
        })
    if pending_tax > 0:
        signals.append({
            "signal": f"另有{pending_tax:,.2f}元票据项目属不得抵扣用途，但**票种与抵扣状态均无法判定**，列为待核",
            "hint": "本轮资料中未见这些发票的票种（专用/普通）与勾选抵扣状态，"
                    "**故不给「应转出」金额、也不作排除**；请补充进项认证抵扣明细（含勾选状态、"
                    "有效抵扣税额）后重新核对。"
                    + ("涉及：" + "；".join(_pending_sup[:5]) + "。" if _pending_sup else ""),
        })

    if circular_mirror:
        sev_high = True
        signals.append({
            "signal": "供应商同时为客户且双向金额高度对称（疑似同额对开）："
                      + "、".join(f"{i['name']}（采购{i['purchase']:,.2f}元/销售{i['sale']:,.2f}元）"
                                 for i in circular_mirror[:4]),
            "hint": "同一主体既向本企业销售又采购，且双向金额接近（小额占大额≥90%），"
                    "疑似资金空转、对开/环开发票；结合合同、交付成果与资金流核实是否闭环回流。"
                    "亦可能为委托加工、售后回购、集团内购销或互换媒体/流量资源，须核实商业实质。",
        })
    if circular_unrelated:
        sev_mid = True
        signals.append({
            "signal": "供应商同时为客户且购销品名无关："
                      + "、".join(f"{i['name']}（采购{'、'.join(i['purchase_cats']) or '—'}"
                                 f"/销售{'、'.join(i['sale_cats']) or '—'}）"
                                 for i in circular_unrelated[:4]),
            "hint": "双向交易但购销品名类别毫无交集且金额均达 5 万元以上，缺乏正常商业链条对应关系，"
                    "须核实是否为以对开方式走票。",
        })
    # 行业常态的双向往来（同类业务互采、金额不成比例、金额极小）→ 只列名单，不抬等级、不定性
    if circular_suppliers and not circular_mirror and not circular_unrelated:
        signals.append({
            "signal": f"{len(circular_suppliers)} 家主体既是供应商又是客户，"
                      f"但双向金额与品名不具备对开特征（{'、'.join(circular_suppliers[:2])}）",
            "hint": "互为供需在委托加工、售后回购、集团内购销、商贸双向贸易，以及传媒·广告·IT·咨询业"
                    "互采服务资源等情形下均属正常，本项仅列示名单，不作为对开嫌疑。",
        })

    if sev_high:
        verdict = "进项侧存在较高虚开/异常抵扣嫌疑，须逐票核实"
    elif sev_mid:
        verdict = "进项侧存在异常线索，需核实用途与供应商真实性"
    elif non_deductible_tax <= 0 and pending_tax <= 0:
        # ★★ 2026-10-06：**"不得抵扣用途"≠"应转出未转出"** —— 若经票种/勾选状态核实
        #   **没有一张是"可抵扣票种且已抵扣"的**，则本项**不存在风险事实**，
        #   必须落"未发现异常"（`_promote_standalone_reports` 据此不立为风险事项），
        #   不得以"票面税额"冒充"应转出额"挤进风险清单。
        verdict = "未发现异常"
    else:
        verdict = "进项侧未触发明显异常（仅代表本轮数据范围）"

    metrics = {
        "input_invoice_count": len(pur_invs),
        "input_amount_total": round(input_amount_total, 2),
        "input_tax_total": round(input_tax_total, 2),
        "abnormal_deduction_tax": round(abnormal_deduction_tax, 2),
        "abnormal_supplier_count": len(abnormal_suppliers),
        "concentration_supplier": top_name,
        "concentration_ratio": round(concentration_ratio, 4),
        "should_transfer_out_tax": round(non_deductible_tax, 2),
        # ★ 2026-10-06：三态分流的另两态（**必须与"应转出"同处可见**，
        #   否则读者以为"没提就是没有"）——"无需转出"有票种/勾选证据；"待核"缺票种与抵扣状态。
        "no_reversal_tax": round(no_reversal_tax, 2),
        "pending_invoice_type_tax": round(pending_tax, 2),
        "circular_supplier_count": len(circular_suppliers),
        # 2026-09-14 新增：双向主体的对开分级计数（供询问提纲与报告按级取用，
        # 避免"只要有双向往来就定对开嫌疑"的误报）
        "circular_mirror_count": len(circular_mirror),
        "circular_unrelated_count": len(circular_unrelated),
    }

    lines = []
    lines.append(f"进项发票：{len(pur_invs)}张，金额合计{input_amount_total:,.2f}元，进项税合计{input_tax_total:,.2f}元")
    if abnormal_suppliers:
        lines.append(f"异常凭证供应商（{len(abnormal_suppliers)}家）异常抵扣税额：{abnormal_deduction_tax:,.2f}元")
        for s in abnormal_suppliers[:6]:
            lines.append(f"  - {s}")
    if top_name:
        lines.append(f"供应商集中度：{top_name} 占{concentration_ratio*100:.1f}%")
    if non_deductible_tax > 0:
        lines.append(f"应进项转出未转出（不得抵扣用途，专票且已抵扣）税额：{non_deductible_tax:,.2f}元")
    if no_reversal_tax > 0:
        lines.append(f"属不得抵扣用途但**无需转出**（普通发票/未勾选）票面税额：{no_reversal_tax:,.2f}元")
    if pending_tax > 0:
        lines.append(f"属不得抵扣用途但**票种与抵扣状态无法判定**（待核，不计金额）：{pending_tax:,.2f}元")
    if circular_suppliers:
        lines.append("供应商=客户（双向往来）名单：")
        for s in circular_suppliers[:4]:
            lines.append(f"  - {s}")
        if circular_mirror:
            lines.append(f"  其中 {len(circular_mirror)} 家双向金额高度对称（疑似同额对开）："
                         + "、".join(i["name"] for i in circular_mirror[:3]))
        if circular_unrelated:
            lines.append(f"  其中 {len(circular_unrelated)} 家购销品名无关："
                         + "、".join(i["name"] for i in circular_unrelated[:3]))
        if not circular_mirror and not circular_unrelated:
            lines.append("  上述主体双向金额与品名不具备对开特征，属互为供需的行业常态，未列为对开嫌疑。")
    body = "\n".join(lines)

    recommendation = ("系统已量化上述进项侧敞口。下一步：①取得上游异常凭证清单逐票核对，"
                      "异常抵扣作进项转出并补税；②复核不得抵扣用途货物是否已转出；"
                      "③核查高度集中供应商真实性及资金是否回流；④供应商=客户情形核实业务闭环。全部需人工取证。")

    return {
        "available": True,
        "ok": True,
        "title": "进项异常凭证 / 应转出未转出比对",
        "company": company_name,
        "verified_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": f"进项发票{len(pur_invs)}张、进项税{input_tax_total:,.2f}元；"
                   + (f"异常抵扣税额{abnormal_deduction_tax:,.2f}元；" if abnormal_deduction_tax > 0 else "")
                   + (f"应转出未转出税额{non_deductible_tax:,.2f}元；" if non_deductible_tax > 0 else "")
                   + (f"供应商集中度{concentration_ratio*100:.1f}%。" if top_name else ""),
        "body": body,
        "metrics": metrics,
        "signals": signals,
        "verdict": verdict,
        "recommendation": recommendation,
        "note": "本比对基于进项发票与（可选）异常凭证清单，属「待证线索」：异常凭证须以税局官方公告或"
                "发票查询平台为准，应转出未转出须结合用途明细账，定性权在风险检查员。",
    }
