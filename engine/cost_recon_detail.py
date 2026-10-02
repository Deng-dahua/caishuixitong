# -*- coding: utf-8 -*-
"""主营业务成本「两口径勾稽明细」（2026-09-27 用户指令）。

背景（用户驳回）：
  第一章此前只有一句「主营业务成本三方勾稽：发票类目口径 X；账面口径 Y；差异 Z」，
  **没有单独的详细分析**——差异超阈值时 VR060 才会多出一条台账事项（标题级），
  差异在阈值内则连事项都没有；且无论哪种情况都**看不到两口径的构成明细**。

本模块补齐：无论是否超阈值，都产出一份**可核对**的明细——
  ① 发票类目口径构成（按品名/类目逐类小计；并列供应商维度）；
  ② 账面口径构成（序时账 6401 本期借方发生额，按凭证号归集；并列科目余额表 6401 交叉核对）；
  ③ 差异 = ① − ②，逐项归因（暂估/不开票/费用混入/跨期/已收未入账），每项标金额线索与可核资料；
  ④ 阈值内也照出（合规留痕）。

设计纪律：
  · **只读** report_data，不修改任何结论；不判定违法性质（发现≠确认）。
  · **单一权威**：发票类目构成取自 `engine_status.biz_cost_classification`
    （由 pipeline 在 core_cost_invs 处一次算清），本模块**不重跑** classify；
    阈值常量复用 `verified_rule_engine` 的 _COST_BASIS_GAP_RATIO/_ABS，不另立一套。
  · 取不到的数据一律明说「未取得」，**绝不用默认值顶替**后照常出结论。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine.numparse import to_number_checked

# 与 VR060 双口径勾稽同一阈值（单一出处）
try:
    from engine.verified_rule_engine import (
        _COST_BASIS_GAP_RATIO, _COST_BASIS_GAP_ABS,
    )
except Exception:  # pragma: no cover - 极端情况下退回同值常量
    _COST_BASIS_GAP_RATIO, _COST_BASIS_GAP_ABS = 0.10, 10000.0


def _num_or_none(v: Any) -> Optional[float]:
    """区分「未取得」与「0」——`to_number(None)` 会静默返 0.0，此处必须显式区分。"""
    if v is None or v == "":
        return None
    val, ok = to_number_checked(v)
    return val if ok else None


def _row_amount(row: Dict[str, Any]) -> float:
    """序时账行金额：主营业务成本在借方；取借方发生额（贷方为期末结转，不计）。"""
    v = _num_or_none((row or {}).get("debit"))
    return float(v) if v is not None else 0.0


def _collect_book(rd: Dict[str, Any]) -> Dict[str, Any]:
    """② 账面口径构成：序时账 6401（主营业务成本）本期借方发生额，按凭证号归集。"""
    out: Dict[str, Any] = {
        "total": None, "source": "", "row_count": 0,
        "by_voucher": [], "by_month": [], "trial_balance_check": None,
    }
    # ── 序时账 ──
    for fr in (rd.get("file_results") or []):
        if not isinstance(fr, dict) or str(fr.get("type") or "") != "voucher":
            continue
        rows = fr.get("_rows") or []
        cost_rows = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            acct = str(r.get("account") or "")
            name = str(r.get("account_name") or "")
            if acct.startswith("6401") or "主营业务成本" in name:
                cost_rows.append(r)
        if not cost_rows:
            continue
        total = round(sum(_row_amount(r) for r in cost_rows), 2)
        # 按凭证号归集
        vmap: Dict[str, Dict[str, Any]] = {}
        mmap: Dict[str, float] = {}
        for r in cost_rows:
            amt = _row_amount(r)
            if not amt:
                continue
            vno = str(r.get("voucher_no") or "（未标凭证号）")
            b = vmap.setdefault(vno, {"voucher_no": vno, "summary": str(r.get("summary") or ""),
                                      "month": str(r.get("month_no") or ""), "amount": 0.0, "count": 0})
            b["amount"] += amt
            b["count"] += 1
            m = str(r.get("month_no") or "（未标月份）")
            mmap[m] = mmap.get(m, 0.0) + amt
        out["total"] = total
        out["source"] = "序时账·主营业务成本(6401)本期借方发生额"
        out["row_count"] = len([r for r in cost_rows if _row_amount(r)])
        out["by_voucher"] = sorted(
            [{"voucher_no": v["voucher_no"], "summary": v["summary"], "month": v["month"],
              "count": v["count"], "amount": round(v["amount"], 2)} for v in vmap.values()],
            key=lambda x: -x["amount"])
        out["by_month"] = [{"month": k, "amount": round(v, 2)}
                           for k, v in sorted(mmap.items(), key=lambda kv: str(kv[0]))]
        # ★ 逐笔清单（供导出附件）：明细到每一笔 6401 借方发生额
        _itemized = []
        for r in cost_rows:
            _amt = _row_amount(r)
            if not _amt:
                continue
            _itemized.append({
                "month": str(r.get("month_no") or ""),
                "voucher_no": str(r.get("voucher_no") or ""),
                "summary": str(r.get("summary") or ""),
                "amount": round(_amt, 2),
            })
        _itemized.sort(key=lambda x: (str(x["month"]), str(x["voucher_no"])))
        out["rows"] = _itemized
        break

    # ── 科目余额表 6401 本期借方发生额（交叉核对，非主口径）──
    for fr in (rd.get("file_results") or []):
        if not isinstance(fr, dict) or str(fr.get("type") or "") != "trial_balance":
            continue
        for r in (fr.get("_rows") or []):
            if not isinstance(r, dict):
                continue
            code = str(r.get("code") or r.get("科目编码") or "")
            name = str(r.get("name") or r.get("科目名称") or "")
            if code.startswith("6401") or "主营业务成本" in name:
                v = _num_or_none(r.get("current_debit"))
                if v is None:
                    v = _num_or_none(r.get("本期借方发生额"))
                if v is not None:
                    out["trial_balance_check"] = round(float(v), 2)
                break
        break
    return out


def _collect_invoice(rd: Dict[str, Any]) -> Dict[str, Any]:
    """① 发票类目口径构成：取 pipeline 已算好的 core_cost 汇总与逐类拆分（单一权威）。"""
    bcc = ((rd.get("engine_status") or {}).get("biz_cost_classification")) or {}
    total = _num_or_none(bcc.get("core_cost_amount"))
    cnt = _num_or_none(bcc.get("core_cost_count"))
    _pend = _num_or_none(bcc.get("pending_cost_count"))
    return {
        "total": round(float(total), 2) if total is not None else None,
        "count": int(cnt) if cnt is not None else 0,
        "by_goods": bcc.get("core_goods_breakdown") or [],
        "by_supplier": bcc.get("core_cost_supplier_breakdown") or [],
        "rows": bcc.get("core_cost_invoices") or [],
        "field_fill": bcc.get("core_cost_invoices_field_fill") or {},
        "pending_count": int(_pend) if _pend is not None else 0,
        "industry_basis": str(bcc.get("industry_basis") or ""),
    }


def _attribution(diff: Optional[float], inv_total: Optional[float], book_total: Optional[float]) -> List[Dict[str, str]]:
    """③ 差异逐项归因：给出可能成因 + 可核资料（不判定违法）。"""
    causes = [
        ("暂估入账（货到票未到）", "账面已计入成本但当期无对应进项发票",
         "核对存货入库单、暂估台账、次月红字冲回凭证"),
        ("不开票采购（小额零星/个体户）", "有账面成本而无进项发票",
         "核对采购合同、付款流水、入库单、收据"),
        ("人工与制造费用不在进项发票", "成本含人工/折旧/制造费用，本无发票可抵",
         "核对工资表、固定资产折旧表、制造费用明细账"),
        ("费用混入成本（发票按品名误归）", "费用类发票被归入成本，抬高发票口径",
         "按品名逐张核对发票用途与费用归属"),
        ("跨期（上期票本期入/成本与票跨期）", "发票与成本确认期间不一致",
         "核对发票开票日期与入账期间、成本结转期间"),
        ("发票已收但当期未入账", "有发票无账面成本",
         "核对进项发票台账与记账凭证"),
    ]
    out: List[Dict[str, str]] = []
    if diff is None or (inv_total is not None and book_total is not None and diff == 0):
        return out
    if diff > 0:
        likely = ["费用混入成本（发票按品名误归）", "发票已收但当期未入账", "跨期（上期票本期入/成本与票跨期）"]
    else:
        likely = ["暂估入账（货到票未到）", "不开票采购（小额零星/个体户）",
                  "人工与制造费用不在进项发票", "跨期（上期票本期入/成本与票跨期）"]
    for name, hint, ev in causes:
        out.append({
            "cause": name, "hint": hint, "evidence": ev,
            "likelihood": "较可能" if name in likely else "亦需排除",
        })
    return out


def _build_cost_expense_attribution(rd: Dict[str, Any]) -> Dict[str, Any]:
    """★ 2026-10-02：主营业务成本 **vs** 期间费用的**三态归属**（成本构成 / 期间费用 / 待核）。

    为什么必须有这一层（用户诉求原话）：「一键分析按钮要把主营业务成本和期间费用**准确区分**」。
    此前报告只有「核心成本发票张数」，费用侧与待核侧**只报个数不报构成**——
    读者只能看到"有多少钱是成本"，看不到"哪些是费用、哪些还没判出来"。

    判据全部来自唯一权威 `engine.account_classifier`（本模块不重写任何词表、不重跑分类逻辑）：
      · 成本构成   = 权威判定为「主营业务成本」的品名（含行业核心投入命中）
      · 期间费用   = 权威判定为「期间费用」的品名（管理/销售/财务费用分项）
      · 待核       = 权威判定「待核」的品名（需项目/合同上下文才能定性）
      · 补证资料   = 待核项索要的具体资料（取自权威层给的 missing_material）

    ★ 铁律复述：判不出来的**只报待核**，绝不默认计入成本（默认判成本=虚增成本、压低毛利）。
    """
    bcs = ((rd.get("engine_status") or {}).get("biz_cost_classification")) or {}
    industry = str(bcs.get("industry_basis") or "")
    core_rows = [r for r in (bcs.get("core_goods_breakdown") or []) if isinstance(r, dict)]
    exp_rows = [r for r in (bcs.get("expense_goods_breakdown") or []) if isinstance(r, dict)]
    pend_rows = [r for r in (bcs.get("pending_goods_breakdown") or []) if isinstance(r, dict)]
    if not (core_rows or exp_rows or pend_rows):
        return {"available": False, "industry": industry, "industry_covered": False,
                "total_amount": 0.0, "cost": None, "expense": None, "pending": None,
                "missing_materials": [], "contradictions": []}

    try:
        from engine import account_classifier as _ac
    except Exception:  # pragma: no cover
        return {"available": False, "industry": industry, "industry_covered": False,
                "total_amount": 0.0, "cost": None, "expense": None, "pending": None,
                "missing_materials": [], "contradictions": []}

    # ① 三桶合并为待分类明细（同一品名在核心桶与费用桶同时出现时，**取权威层口径**）
    lines: List[Dict[str, Any]] = []
    seen: Dict[str, Dict[str, Any]] = {}
    for rows in (core_rows, exp_rows, pend_rows):
        for r in rows:
            g = str(r.get("goods") or "").strip()
            if not g:
                continue
            # ★ 2026-10-02：把发票结构性证据（税收编码/计量单位/业务类型）一并交给权威层，
            #   否则「第一刀」（有无实物存货）无数据可用，只能退回关键词猜。
            item = {"goods": g, "amount": float(r.get("amount") or 0),
                    "count": int(r.get("count") or 0),
                    "tax_code": str(r.get("tax_code") or ""),
                    "unit": str(r.get("unit") or ""),
                    "biz_type": str(r.get("biz_type") or "")}
            if g in seen:
                seen[g]["count"] += item["count"]
                seen[g]["amount"] += item["amount"]
            else:
                seen[g] = item
                lines.append(item)
    for ln in lines:
        ln["amount"] = round(ln["amount"], 2)

    summary = _ac.classify_lines(lines, industry=industry)
    by_cls = summary.get("by_class") or {}

    def _block(cls) -> Optional[Dict[str, Any]]:
        blk = by_cls.get(cls) or {}
        items = [{"goods": it["goods"], "amount": it["amount"], "count": 0,
                  "evidence": it["evidence"], "matched_kw": it.get("matched_kw", ""),
                  "matched_layer": it.get("matched_layer", ""),
                  "expense_sub": it.get("expense_sub", "")}
                 for it in (blk.get("lines") or [])]
        return {"amount": blk.get("amount", 0), "count": blk.get("count", 0), "items": items}

    # ② 口径差异：管道「核心成本桶」里的品名，权威层判为费用/资本化 —— 必须显式披露，
    #    不能让两套口径在报告里各自沉默（这正是本轮修复的 4 处词表打架的可视化）。
    contradictions: List[Dict[str, Any]] = []
    for r in core_rows:
        g = str(r.get("goods") or "").strip()
        if not g:
            continue
        cls = _ac.classify_line(g, industry=industry).get("account_class")
        if cls and cls != _ac.CLASS_COST:
            contradictions.append({"goods": g, "amount": float(r.get("amount") or 0),
                                   "authority_class": cls,
                                   "reason": _ac.classify_line(g, industry=industry).get("reason", "")})
    contradictions.sort(key=lambda x: abs(x.get("amount") or 0), reverse=True)

    return {
        "available": True,
        "industry": summary.get("industry") or industry or "未取得",
        "industry_covered": bool(summary.get("industry_covered")),
        "total_amount": summary.get("total_amount", 0),
        "cost": _block(_ac.CLASS_COST),
        "expense": _block(_ac.CLASS_EXPENSE),
        "pending": _block(_ac.CLASS_UNDETERMINED),
        "missing_materials": summary.get("missing_materials") or [],
        "contradictions": contradictions,
    }


def build_cost_recon_detail(report_data: Any) -> Dict[str, Any]:
    """生成「主营业务成本两口径勾稽明细」。无论是否超阈值都产出（合规留痕）。"""
    rd = report_data if isinstance(report_data, dict) else {}
    inv = _collect_invoice(rd)
    book = _collect_book(rd)

    it, bt = inv.get("total"), book.get("total")
    diff = None
    diff_pct = None
    status = "未取得"
    if it is not None and bt is not None:
        diff = round(float(it) - float(bt), 2)
        diff_pct = round(diff / float(bt) * 100, 2) if bt else None
        if bt and abs(diff) > _COST_BASIS_GAP_ABS and abs(diff / float(bt)) > _COST_BASIS_GAP_RATIO:
            status = "差异超阈值（待核）"
        else:
            status = "两口径基本吻合"
    elif it is not None:
        status = "账面口径未取得"
    elif bt is not None:
        status = "发票口径未取得"

    attribution = _attribution(diff, it, bt)
    available = (it is not None) or (bt is not None)

    # ── 概述句（与第一章「三方勾稽」同口径，措辞更细）──
    paragraphs: List[str] = []
    if available:
        _inv_txt = ("%s 元（%d 张）" % (format(it, ",.2f"), inv["count"])) if it is not None else "未取得"
        _bk_txt = ("%s 元（%s）" % (format(bt, ",.2f"), book["source"] or "未标注来源")) if bt is not None else "未取得"
        seg = "主营业务成本两口径勾稽明细：发票类目口径 %s；账面口径 %s。" % (_inv_txt, _bk_txt)
        if diff is not None:
            seg += "差异 %s 元（%s），%s。" % (format(diff, ",.2f"),
                                              ("%s%%" % diff_pct) if diff_pct is not None else "—", status)
        else:
            seg += "%s。" % status
        seg += "本明细仅陈述两口径构成与差异，不作定性；差异成因须逐项核对账证后确认。"
        paragraphs.append(seg)

        if book.get("trial_balance_check") is not None and bt is not None:
            _tb = book["trial_balance_check"]
            _same = "一致" if abs(_tb - bt) < 0.01 else "不一致（相差 %.2f 元）" % abs(_tb - bt)
            paragraphs.append(
                "交叉核对：科目余额表「主营业务成本(6401)」本期借方发生额 %s 元，"
                "与序时账 6401 借方合计 %s 元%s。" % (format(_tb, ",.2f"), format(bt, ",.2f"), _same))

        if attribution:
            _c = "；".join("%s（%s）：%s，可核资料——%s" % (a["cause"], a["likelihood"], a["hint"], a["evidence"])
                           for a in attribution)
            paragraphs.append("差异归因（按可能性排序，均须逐项核对后确认）：" + _c + "。")

        if inv.get("industry_basis"):
            paragraphs.append("发票类目口径的分类依据：按「%s」行业核心投入认定主营业务成本类发票。" % inv["industry_basis"])

        # ★ 2026-09-29（点评整改 P0-9a）：**空列必须被解释**，不得留白让人猜。
        #   真实事故：导出的「发票逐张清单」是一张 95 行全空表——读者无法判断
        #   是"企业本无此信息"还是"系统没解析出来"。此处按下游真实填充率如实披露。
        _ff = inv.get("field_fill") or {}
        _n = int(_ff.get("rows") or 0)
        if _n:
            _lack = []
            for _k, _zh in (("inv_no", "发票号码"), ("date", "开票日期"), ("seller", "销售方")):
                _got = int(_ff.get(_k) or 0)
                if _got < _n:
                    _lack.append("%s（%d/%d 张已有）" % (_zh, _got, _n))
            if _lack:
                paragraphs.append(
                    "逐张清单字段说明：%s 未能从原始文件中解析取得（原始文件未含该列或列名未识别），"
                    "相应单元格留空**不表示该发票无此项信息**，须回到原始发票文件核对；"
                    "金额与税额口径取自解析结果，可作为逐张核对起点。" % "、".join(_lack))
            if _ff.get("blank_rows_dropped"):
                paragraphs.append("另有 %d 条发票记录因全部字段为空（未解析出任何可展示信息）未列入清单，"
                                  "相应张数已计入上方发票张数，差异属解析未识别而非数据缺失。"
                                  % int(_ff["blank_rows_dropped"]))

        if inv.get("pending_count"):
            paragraphs.append("尚有 %d 张进项发票按行业口径无法判定归属（待核），未计入上表成本类；"
                              "其归属确认后会改变发票类目口径。" % inv["pending_count"])

        # ★ 2026-10-02：主营业务成本 vs 期间费用的三态归属（口径来自唯一权威 account_classifier）
        cea = _build_cost_expense_attribution(rd)
        assert cea is not None, "成本费用归属不得为 None（关键产出）"
        if cea.get("available"):
            _fmt = lambda _x: "0" if _x is None else format(float(_x), ",.2f")  # noqa: E731
            _c, _e, _p = cea.get("cost") or {}, cea.get("expense") or {}, cea.get("pending") or {}
            _seg = ("主营业务成本与期间费用的区分：按「%s」行业口径判定，"
                    "计入主营业务成本 %s 元（%d 类），计入期间费用 %s 元（%d 类，其中管理费用 %s 元、"
                    "销售费用 %d 元），尚待项目/合同上下文才能定性 %s 元（%d 类）。"
                    % (cea.get("industry") or "未取得", _fmt(_c.get("amount")), _c.get("count", 0),
                       _fmt(_e.get("amount")), _e.get("count", 0),
                       _fmt(sum(i.get("amount", 0) for i in (_e.get("items") or [])
                                if i.get("expense_sub") == "管理费用")),
                       sum(1 for i in (_e.get("items") or []) if i.get("expense_sub") == "销售费用"),
                       _fmt(_p.get("amount")), _p.get("count", 0)))
            paragraphs.append(_seg + "判不出来的只列入待核，未默认计入成本。")
            if not cea.get("industry_covered"):
                paragraphs.append(
                    "需说明：本轮未取到该行业的核心投入登记（系统内置行业库中无对应行业口径），"
                    "上述划分因此采用**业态兜底**口径（购销/生产业态下未落入费用或资本化口径的进项"
                    "计入存货），而非按行业核心投入逐项认定；若要精确到「哪些属于该行业的外购成本」，"
                    "须补充登记该行业的核心投入品名。")
            if cea.get("contradictions"):
                _top = "；".join("「%s」%s 元" % (str(x["goods"])[:24], _fmt(x.get("amount")))
                                for x in (cea["contradictions"] or [])[:3])
                # ★ 2026-10-02：此处必须写明是**哪个口径的成本**。
                #   本列表按定义来自「发票类目口径」认定为成本类的品名（`core_rows`），
                #   旧文案写「已计入成本桶的品名中…」——读者会把它理解成上一段的
                #   「主营业务成本」桶（三态归属的 cost 桶），于是同一品名看起来
                #   「既在成本桶、又说应作待核」，成了新的自相矛盾（用户一眼就会问）。
                #   两个「成本」本是不同口径：发票类目（按品名归类）vs 三态归属（按权威层）。
                paragraphs.append(
                    "口径差异提示：本次「发票类目口径」认定为成本类的品名中，有 %d 类经"
                    "「成本/费用/待核」区分后不属于主营业务成本（%s，其中金额最大一项应作「%s」"
                    "处理）；两套口径的差异须核对合同用途后确认。"
                    % (len(cea["contradictions"]),
                       _top, (cea["contradictions"][0].get("authority_class") or "")))

    # ★ 2026-10-02（用户拍板）：**成本明细只列最终判为主营业务成本的部分**。
    #   此前「按供应商」「逐张清单」直接沿用**发票类目口径**，把已判为费用/待核的支出
    #   也挂在"主营业务成本"名下 —— 实测 59 家供应商里 47.5% 的金额并非成本
    #   （机票/住宿/咨询/体育文化…），读者看到的是"表名说成本、内容混着差旅和咨询"。
    #   做法：对每条明细用**唯一权威** `account_classifier` 复核归属，只保留 CLASS_COST；
    #   被剔除的金额不消失 —— 它们在三态归属表里各有归属（费用/待核），两表口径一致。
    _cea_final = _build_cost_expense_attribution(rd)
    _cost_goods = {str(_i.get("goods") or "")
                   for _i in (((_cea_final or {}).get("cost") or {}).get("items") or [])}
    _base_rows = inv.get("rows") or []
    # 二次过滤是**幂等**的保险：pipeline 已按同一口径过滤过（`filter_cost_invoices`），
    # 这里再按三态归属复核一次，确保任何入口（含离线重建）拿到的都是同一口径。
    _keep_rows = [_r for _r in _base_rows if str(_r.get("goods") or "") in _cost_goods]
    _sup: Dict[str, Dict[str, Any]] = {}
    for _r in _keep_rows:
        _s = str(_r.get("seller") or "")
        _b = _sup.setdefault(_s, {"seller": _s, "count": 0, "amount": 0.0})
        _b["count"] += 1
        _b["amount"] += float(_r.get("amount") or 0)
    _by_supplier = sorted(
        [{"seller": k, "count": v["count"], "amount": round(v["amount"], 2)} for k, v in _sup.items()],
        key=lambda x: -x["amount"])

    _by_goods = [_g for _g in (inv.get("by_goods") or [])
                 if str(_g.get("goods") or "") in _cost_goods]

    return {
        "available": available,
        # ⚠ `invoice_total/count` 是**发票类目口径全量**（含已判为费用/待核的部分），
        #   用于与账面口径做勾稽（概述句引用）；下方三张成本明细表则只列归属为成本的
        #   部分，故另有 `cost_detail_total/count` 作为这三张表的合计（两者口径不同，
        #   前端必须各用各的，否则"表内明细加总 ≠ 合计行"）。
        "invoice_total": it, "invoice_count": int(inv.get("count") or 0),
        "cost_detail_total": round(sum(float(_r.get("amount") or 0) for _r in _keep_rows), 2),
        "cost_detail_count": len(_keep_rows),
        "by_goods": _by_goods,
        # ⚠ 下表只含**归属为主营业务成本**的发票；发票类目口径的全量合计见 invoice_total，
        #   两者差额即已判为期间费用/待核的部分（见 cost_expense_attribution）。
        "by_supplier": _by_supplier,
        "invoice_rows": _keep_rows,
        "cost_detail_scope": ("本明细只列经「成本/费用/待核」区分后归属主营业务成本、"
                              "且能定位到具体发票的支出；已判为期间费用或待核的部分不计入本表"
                              "（另见三态归属），无逐张发票可列的成本类支出亦不在本表。"),
        "cost_detail_dropped_amount": round(
            sum(float(_r.get("amount") or 0) for _r in _base_rows
                if str(_r.get("goods") or "") not in _cost_goods), 2),
        "invoice_field_fill": inv.get("field_fill") or {},
        "book_total": bt, "book_source": book.get("source") or "",
        "book_row_count": book.get("row_count") or 0,
        "by_voucher": book.get("by_voucher") or [],
        "by_month": book.get("by_month") or [],
        "book_rows": book.get("rows") or [],
        "trial_balance_check": book.get("trial_balance_check"),
        "diff": diff, "diff_pct": diff_pct, "status": status,
        "attribution": attribution,
        # ★ 2026-10-02：主营业务成本 vs 期间费用三态归属（唯一权威 account_classifier 产出）
        "cost_expense_attribution": _build_cost_expense_attribution(rd),
        "paragraphs": paragraphs,
    }
