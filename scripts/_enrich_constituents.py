# -*- coding: utf-8 -*-
"""为 68 条红线 constituents 追加"更多风险场景"（用户确认：不固定数量尽量补全 + 新场景纳入逐条判定兜底）。

硬约束（务必守住）：
  - 新场景只 APPEND 到末项「不属于…正当情形」出罪要件之前（出罪要件始终压轴）；
  - 不改原有序号、不触动出罪要件 -> _DEFAULT_HIT_INDEX 旧序号零漂移；
  - 新场景不含「不属于/豁免」等出罪关键词；
  - _DEFAULT_HIT_INDEX 仅扩展原 18 条兜底红线（命中时新场景一并呈现）；
    其余 50 条为显式检测器红线，新场景仅在 (A) 抽象清单呈现，(B) 由检测器实际命中决定，不强制标注（防误判）。
验证：插入后重新导入 REDLINES，断言每条被改红线 constituents 条数+新增数、末项仍含「不属于」、
  新文本已落地；再跑 check_default_hit_index_valid 复验新序号在界内且不出罪。
"""
import importlib.util
import os
import re
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "engine", "tax_redlines.py")
ENG = os.path.join(ROOT, "engine", "redline_engine.py")

# rid -> 新增风险场景（实质性要件，均不含"不属于/豁免"；按顺序追加到出罪要件之前）
EXTRA = {
    "RL-VAT-001": [
        "进项税额明显低于同行业税负率水平，进项结构异常偏轻（疑似取得进项不足或虚开）",
        "接受开票的供应商为短期内成立、无实际经营地址的空壳企业，开票方真实性存疑",
    ],
    "RL-VAT-002": [
        "进项税额长期大于销项形成大额留抵且无合理经营理由（疑似虚增进项）",
        "取得进项发票后短期内作废或红冲，对应存货无入库与领用轨迹",
    ],
    "RL-VAT-003": [
        "购进品名与销项品名适用税率档次差异巨大（如购进低税率农产品、销售高税率货物）",
    ],
    "RL-VAT-004": [
        "开票金额呈规律性整数或临界值聚集，疑似规避发票限额或起征点",
    ],
    "RL-VAT-005": [
        "单位产值对应的能耗、运费显著低于同行业可比水平（产能虚胖或开票虚高）",
    ],
    "RL-VAT-006": [
        "存在未开具发票的视同销售行为（无偿赠送、用于集体福利或个人消费）未确认收入",
    ],
    "RL-VAT-007": [
        "频繁作废发票后重新开具以调节税额或隐瞒真实交易",
    ],
    "RL-VAT-008": [
        "将自产货物用于在建工程、固定资产等非增值税应税项目未作视同销售处理",
    ],
    "RL-VAT-009": [
        "向购买方收取的价外费用混入往来科目（其他应付款等）隐瞒、未确认收入",
    ],
    "RL-VAT-010": [
        "各期申报数据大起大落、税负率忽高忽低，疑似人为调节纳税义务",
    ],
    "RL-VAT-011": [
        "兼营免税与应税项目但未按销售额比例划分、全额抵扣进项税额",
    ],
    "RL-INC-001": [
        "个人账户代收经营款项后转入公司账户但未确认收入，形成账外回流",
    ],
    "RL-INC-002": [
        "通过关联方或员工个人支付宝、微信收取货款未申报纳税",
    ],
    "RL-INC-003": [
        "预收房款、货款已达到交房或交付条件仍挂账不转收入",
    ],
    "RL-INC-004": [
        "以借款名义长期挂账实为隐匿销售收入，后续无还款、无利息支出",
    ],
    "RL-COST-001": [
        "暂估成本对应的供应商后续失联或注销，支出真实性存疑",
    ],
    "RL-COST-002": [
        "咨询服务费开票方为同一控制人关联企业，缺乏独立交易价格佐证",
    ],
    "RL-COST-003": [
        "以内部审批单、出库单等自制凭证代替发票列支成本费用",
    ],
    "RL-COST-004": [
        "毛利率长期为负或接近零（收入成本倒挂），疑似虚增成本或隐瞒收入",
    ],
    "RL-COST-005": [
        "年末大额费用入账后次年集中红冲或退回，跨期调节利润",
    ],
    "RL-COST-006": [
        "以员工或关联方名义虚列工资、劳务费等套取资金、虚构列支",
    ],
    "RL-FUND-001": [
        "频繁小额公转私拆分转账，疑似规避大额交易报告与监管",
    ],
    "RL-FUND-002": [
        "资金经多个个人账户闭环流转后回流，形成资金循环",
    ],
    "RL-FUND-003": [
        "股东借款跨年度滚续、长期挂其他应收款不清理",
    ],
    "RL-FUND-004": [
        "现金收支占比异常偏高，规避银行流水留痕",
    ],
    "RL-FUND-005": [
        "多账户间资金互转掩饰资金来源与去向",
    ],
    "RL-FUND-006": [
        "记账凭证借贷方含大量红字或负数冲抵，分录异常",
    ],
    "RL-INV-001": [
        "存货盘亏长期挂待处理财产损溢未报批、未转出对应进项税额",
    ],
    "RL-INV-002": [
        "存货账面值远高于可变现净值，跌价准备计提不足",
    ],
    "RL-INV-003": [
        "投入原材料与产出废料、副产品数量关系异常，疑似隐瞒副产品销售",
    ],
    "RL-PAY-001": [
        "工资表含已离职人员仍列支，疑似虚列工资",
    ],
    "RL-PAY-002": [
        "年终奖与日常工资拆分多处发放以降低计税基数",
    ],
    "RL-PAY-003": [
        "工资表人员身份证号为虚假或重复，疑似冒用身份虚列",
    ],
    "RL-PAY-004": [
        "高管薪酬以咨询费、劳务费名义支付，规避工资薪金个税",
    ],
    "RL-PAY-005": [
        "向无资质个人支付大额劳务费未扣缴个税且未取得发票",
    ],
    "RL-PAY-006": [
        "同一人在多家关联企业同时领薪未合并综合所得申报",
    ],
    "RL-CIT-001": [
        "关联交易未准备同期资料、未做转让定价文档",
    ],
    "RL-CIT-002": [
        "关联方无偿使用资产（厂房、设备、商标）未作视同销售或纳税调整",
    ],
    "RL-CIT-003": [
        "将普通生产人员工资全额计入研发人员，虚增加计扣除",
    ],
    "RL-CIT-004": [
        "连续亏损但仍持续新增投资、扩大产能，收入或成本不实信号明显",
    ],
    "RL-CIT-005": [
        "用未实际发生的亏损额抵减当期应纳税所得额",
    ],
    "RL-CIT-006": [
        "将经营亏损包装为资产损失税前扣除",
    ],
    "RL-CIT-007": [
        "业务招待费、广告费和业务宣传费超限额部分未纳税调增且混用科目",
    ],
    "RL-PTY-001": [
        "成本对应的供应商与销售客户为同一控制方，形成自买自卖闭环",
    ],
    "RL-PTY-002": [
        "主要供应商注册地与实际经营地不符、无实地经营，疑似空壳供货",
    ],
    "RL-PTY-003": [
        "委托加工费开票方与受托加工方不一致，票货分离",
    ],
    "RL-PTY-004": [
        "投料量远大于产出量且无废料、在产品合理解释，疑似隐瞒产出售",
    ],
    "RL-PTY-005": [
        "发票购方信息与企业实际客户不符，疑似替票或代开",
    ],
    "RL-AST-001": [
        "已完工在建工程长期不转固，推迟计提折旧",
    ],
    "RL-AST-002": [
        "不征税收入对应支出与应税支出混同核算",
    ],
    "RL-AST-003": [
        "金额尾数高度集中于 .00、.50 等整数，疑似人为构造",
    ],
    "RL-OTH-001": [
        "以电子订单、框架协议隐瞒应税凭证未申报印花税",
    ],
    "RL-OTH-002": [
        "房产原值未包含地价或装修等，计税依据偏低",
    ],
    "RL-OTH-003": [
        "免抵增值税额未作为城市维护建设税计税依据，依据错误",
    ],
    "RL-OTH-004": [
        "免税土地范围主张无批文支撑",
    ],
    "RL-OTH-005": [
        "已过户或报废车辆仍继续申报、或未停申报，税基不实",
    ],
    "RL-OTH-006": [
        "以折扣折让名义冲减收入实为返利，未依规处理",
    ],
    "RL-SPT-001": [
        "虚增开发成本（虚列建安、前期费用）降低增值额",
    ],
    "RL-SPT-002": [
        "自产应税消费品用于在建工程、职工福利未缴纳消费税",
    ],
    "RL-SPT-003": [
        "原矿销售按选矿税率申报，适用税率错误",
    ],
    "RL-SPT-004": [
        "应税污染物排放量按虚假监测数据申报",
    ],
    "RL-SPT-005": [
        "特许权使用费、协助费用未计入进口完税价格",
    ],
    "RL-SPT-006": [
        "向境外支付特许权使用费未扣缴预提所得税",
    ],
    "RL-SPT-007": [
        "以抵债、作价出资方式承受权属未申报契税",
    ],
    "RL-SPT-008": [
        "出口发票金额与报关单不一致，疑似高报出口骗税",
    ],
    "RL-SPT-009": [
        "以阴阳合同低报转让价格避税",
    ],
    "RL-SPT-010": [
        "按最低缴费基数而非实际工资缴存，缴存基数不实",
    ],
    "RL-SPT-011": [
        "为维持核定征收故意不取得合规凭证、不设置账簿",
    ],
}


def _load(text_src):
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".py",
                                     delete=False, dir=os.path.dirname(SRC)) as tf:
        tf.write(text_src)
        tmp = tf.name
    try:
        spec = importlib.util.spec_from_file_location("rl_load", tmp)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        os.unlink(tmp)


def _find_constituents_block(lines, start):
    """在 lines[start:] 中找到该 redline 的 "constituents": [ ... ] 块的 [起行, 止行(含])]。"""
    j = None
    for k in range(start, min(start + 400, len(lines))):
        if '"constituents"' in lines[k] and "[" in lines[k]:
            j = k
            break
    assert j is not None, "未找到 constituents 起始"
    buf = "\n".join(lines[j:])
    depth = 0
    in_str = False
    esc = False
    close = -1
    for off, ch in enumerate(buf):
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                close = off
                break
    assert close >= 0, "constituents 括号不匹配"
    head = buf[:close + 1]
    end_line = j + head.count("\n")
    return j, end_line


def main():
    with open(SRC, encoding="utf-8") as f:
        text = f.read()

    before = _load(text)
    by_id = {r["id"]: r for r in before.REDLINES}

    # 构造新 constituents（内存）
    new_cons_map = {}
    for rid, extras in EXTRA.items():
        cons = list(by_id[rid].get("constituents") or [])
        assert ("不属于" in cons[-1]) or ("豁免" in cons[-1]), "%s 末项非出罪要件" % rid
        for e in extras:
            assert ("不属于" not in e) and ("豁免" not in e), "%s 新场景含出罪关键词" % rid
        insert_at = len(cons) - 1
        cons[insert_at:insert_at] = list(extras)
        new_cons_map[rid] = cons

    # 逐 redline 重扫当前 lines 插入（避免位置错位）
    lines = text.split("\n")
    changed = 0
    for rid, new_cons in new_cons_map.items():
        start = None
        for i, ln in enumerate(lines):
            if re.search(r'"id"\s*:\s*"%s"' % re.escape(rid), ln):
                start = i
                break
        assert start is not None, "%s 未定位" % rid
        j, end_line = _find_constituents_block(lines, start)
        indent = re.match(r"\s*", lines[j]).group(0)
        inner = indent + "    "
        cons_lines = [indent + '"constituents": [']
        for c in new_cons:
            cons_lines.append('%s"%s",' % (inner, c))
        cons_lines.append(indent + "],")
        lines[j:end_line + 1] = cons_lines
        changed += 1

    new_text = "\n".join(lines)

    # 重新导入验证
    after = _load(new_text)
    new_by_id = {r["id"]: r for r in after.REDLINES}
    assert len(after.REDLINES) == len(before.REDLINES)
    flat = " ".join(" ".join(r.get("constituents") or []) for r in after.REDLINES)
    for rid, extras in EXTRA.items():
        cons = new_by_id[rid].get("constituents") or []
        assert ("不属于" in cons[-1]) or ("豁免" in cons[-1]), "%s 末项出罪要件丢失" % rid
        assert len(cons) == len(by_id[rid].get("constituents") or []) + len(extras), \
            "%s 条数不一致" % rid
        for e in extras:
            assert e in flat, "新场景未落地：%s…" % e[:20]

    # 合并新场景序号进 _DEFAULT_HIT_INDEX（仅原 18 条兜底红线）
    eng_text = open(ENG, encoding="utf-8").read()
    m = re.search(r"_DEFAULT_HIT_INDEX\s*=\s*\{(.*?)\n\}", eng_text, re.S)
    assert m, "未找到 _DEFAULT_HIT_INDEX"
    block = m.group(1)
    existing = {}
    for km in re.finditer(r'"(RL-\w+)"\s*:\s*\[([^\]]*)\]', block):
        existing[km.group(1)] = [int(x) for x in re.findall(r"\d+", km.group(2))]

    merged = {}
    for rid in existing:
        s = set(existing[rid])
        if rid in EXTRA:
            orig_len = len(by_id[rid].get("constituents") or [])
            s |= set(range(orig_len, orig_len + len(EXTRA[rid])))
        merged[rid] = sorted(s)

    order = ["RL-PTY-002", "RL-FUND-001", "RL-CIT-001", "RL-PTY-004", "RL-SPT-008",
             "RL-SPT-011", "RL-PAY-005", "RL-PTY-003", "RL-INC-002", "RL-AST-003",
             "RL-PAY-002", "RL-PAY-003", "RL-AST-001", "RL-FUND-002", "RL-OTH-003",
             "RL-VAT-002", "RL-VAT-006", "RL-COST-003"]
    parts = ["_DEFAULT_HIT_INDEX = {"]
    parts.append("    # —— 原兜底（外部核验待办 + 关键字匹配型红线），序号对应 constituents 顺序 ——")
    for rid in order:
        if rid in merged:
            parts.append('    "%s": %s,' % (rid, merged[rid]))
    parts.append("    # —— 本轮新增场景追加（逐条判定兜底，序号由 enrich 脚本按 constituents 顺序计算）——")
    for rid in sorted(merged):
        if rid not in order:
            parts.append('    "%s": %s,' % (rid, merged[rid]))
    parts.append("}")
    new_block = "\n".join(parts)
    eng_text = eng_text[:m.start()] + new_block + eng_text[m.end():]

    # 写回
    with open(SRC, "w", encoding="utf-8") as f:
        f.write(new_text)
    with open(ENG, "w", encoding="utf-8") as f:
        f.write(eng_text)

    print("OK: 为 %d 条红线追加 %d 个新风险场景（出罪要件保持最后，序号零漂移）"
          % (changed, sum(len(v) for v in EXTRA.values())))
    print("OK: _DEFAULT_HIT_INDEX 已为 %d 条兜底红线合并新场景序号" % len(merged))


if __name__ == "__main__":
    main()
