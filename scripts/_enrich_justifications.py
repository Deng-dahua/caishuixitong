# -*- coding: utf-8 -*-
"""为 68 条红线的 justifications（正当理由/反证，论证链 rebuttals 维度）做「对称扩充」。

背景：上一轮只为 constituents 追加了 70 个"新涉嫌场景"（insert 到末项出罪要件之前），
但 justifications（出证反证清单）未动，仍 228 条——新场景没有对应的"企业可逐条自证"的反证。
本脚本按 rid 为本次新增的每个涉嫌场景补一条对应反证，使论证链 rebuttals 与 constituents 平行。

硬约束（务必守住）：
  - 新反证只 APPEND 到各红线 justifications 列表末尾（不破坏原有顺序/不删原有条目）；
  - 新反证是"若此嫌疑系合理情形、企业已留存 X 证据则不触红"的保守表述，不弱化红线；
  - 幂等：已存在的反证不重复追加，可安全重跑；
  - 基线锁：扩充后每条红线 justifications 条数 = 原基线(ORIG_J) + 本线新增数；全局 298 条。
验证：写回后重新导入 REDLINES，断言条数、新文本落地、全局总数、无空项。
"""
import importlib.util
import os
import re
import tempfile
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "engine", "tax_redlines.py")

# 原 justifications 条数基线（扩充前实测，重导入校验用；与 _enrich_constituents.EXTRA 一一对应）
ORIG_J = {"RL-VAT-001": 4, "RL-VAT-002": 4, "RL-VAT-003": 3, "RL-VAT-004": 3,
          "RL-VAT-005": 3, "RL-VAT-006": 3, "RL-VAT-007": 3, "RL-INC-001": 4,
          "RL-INC-002": 3, "RL-INC-003": 3, "RL-INC-004": 3, "RL-COST-001": 3,
          "RL-COST-002": 3, "RL-COST-003": 3, "RL-COST-004": 4, "RL-COST-005": 3,
          "RL-FUND-001": 3, "RL-FUND-002": 3, "RL-FUND-003": 3, "RL-FUND-004": 2,
          "RL-FUND-005": 3, "RL-FUND-006": 3, "RL-INV-001": 3, "RL-INV-002": 3,
          "RL-INV-003": 3, "RL-PAY-001": 5, "RL-PAY-002": 3, "RL-PAY-003": 3,
          "RL-PAY-004": 3, "RL-CIT-001": 3, "RL-CIT-002": 3, "RL-CIT-003": 3,
          "RL-CIT-004": 3, "RL-PTY-001": 5, "RL-PTY-002": 7, "RL-PTY-003": 3,
          "RL-PTY-004": 3, "RL-PTY-005": 3, "RL-AST-001": 3, "RL-AST-002": 3,
          "RL-AST-003": 3, "RL-OTH-001": 3, "RL-OTH-002": 3, "RL-OTH-003": 2,
          "RL-SPT-001": 4, "RL-SPT-002": 4, "RL-SPT-003": 4, "RL-SPT-004": 4,
          "RL-SPT-005": 4, "RL-SPT-006": 5, "RL-SPT-007": 5, "RL-SPT-008": 4,
          "RL-SPT-009": 5, "RL-SPT-010": 4, "RL-SPT-011": 4, "RL-CIT-005": 3,
          "RL-CIT-006": 3, "RL-PAY-005": 3, "RL-PAY-006": 3, "RL-OTH-004": 3,
          "RL-OTH-005": 3, "RL-VAT-008": 3, "RL-VAT-009": 3, "RL-COST-006": 3,
          "RL-CIT-007": 3, "RL-VAT-010": 3, "RL-VAT-011": 3, "RL-OTH-006": 3}
EXPECTED_TOTAL = 298  # 228 + 70

# rid -> 新增反证（与 _enrich_constituents.EXTRA 顺序一一对应）
JUSTIFY_EXTRA = {
    "RL-VAT-001": [
        "进项偏低系采购对象以一般纳税人为主、取得专票充分，或经营品类本身低进项特性，已提供同行业税负率可比口径及进销项结构说明，不构成虚开",
        "已提供该供应商实地经营佐证（经营场所、人员、社保、银行流水）及真实交易合同、付款与物流记录，证实交易真实、开票方非空壳",
    ],
    "RL-VAT-002": [
        "已说明留抵形成的经营性原因（如大额设备采购、周期性备货），并提供对应进项发票、付款与资产验收记录，留抵真实合理",
        "作废或红冲系真实交易撤销（退货、折让）并已同步冲减存货与成本，提供退货单、红字信息表与出入库记录可证",
    ],
    "RL-VAT-003": [
        "已说明进销税率差异的业务实质（深加工增值、农产品进项核定扣除等），并提供投入产出与成本核算佐证，符合税法规定",
    ],
    "RL-VAT-004": [
        "整数或临界金额系行业交易习惯或合同定价（如按件、按吨计价），提供合同与流水可证非为规避发票限额人为拆分",
    ],
    "RL-VAT-005": [
        "已提供能耗、运费与产值的勾稽测算及同行业可比口径，差异系工艺节能、自有物流或产品结构差异所致，非产能虚胖或开票虚高",
    ],
    "RL-VAT-006": [
        "已说明该部分资产移送的用途与税务处理，属不征增值税范围或已按规定视同销售申报，提供内部审批与账务记录可证",
    ],
    "RL-VAT-007": [
        "作废后重开系开票信息录入错误更正，且前后发票对应同一真实交易，提供原票、重开票及交易凭证可证非调节税额或隐瞒交易",
    ],
    "RL-VAT-008": [
        "已说明该自产货物移送用途，并按规定视同销售计提销项或属不征税项目，提供在建工程领用单与税务处理说明可证",
    ],
    "RL-VAT-009": [
        "价外费用已如实核算，混入往来科目系暂挂待结算，提供合同价外条款与最终确认收入凭证可证未隐瞒收入",
    ],
    "RL-VAT-010": [
        "已说明申报波动的经营原因（季节性、项目制、大额偶发业务），提供各期业务明细与核算依据可证非人为调节纳税义务",
    ],
    "RL-VAT-011": [
        "已按财税规定对免税与应税项目进项税额分别核算或按比例分摊，并提供划分依据与计算表可证",
    ],
    "RL-INC-001": [
        "个人账户代收系临时周转，款项已全额转入公司对公账户并确认收入申报纳税，提供流水与入账凭证可证非账外回流",
    ],
    "RL-INC-002": [
        "个人支付宝、微信收款已全额纳入公司账务并申报纳税，提供收款台账与申报记录可证非隐瞒收入",
    ],
    "RL-INC-003": [
        "已说明未达到收入确认条件的依据（合同风险报酬未转移），或已达到条件并已结转收入，提供交房或交付验收记录可证",
    ],
    "RL-INC-004": [
        "借款系真实资金往来，提供借款合同、利息计提与还款计划，或个人确为股东借款并已按规定处理，可证非隐匿销售收入",
    ],
    "RL-COST-001": [
        "暂估成本已提供采购合同、收货单与付款凭证，供应商失联系经营异常非虚构交易，并按规定取得合法凭证或作纳税调整",
    ],
    "RL-COST-002": [
        "已提供咨询服务内容、成果交付与独立交易价格佐证（如市场比价、同期资料），关联交易定价公允可证",
    ],
    "RL-COST-003": [
        "自制凭证仅作内部流转记录，成本费用最终以合规发票入账，提供对应发票可证未以白条列支",
    ],
    "RL-COST-004": [
        "已说明负毛利或零毛利成因（行业周期、清仓折价、战略亏损），并提供收入成本明细勾稽可证非虚增成本或隐瞒收入",
    ],
    "RL-COST-005": [
        "年末费用真实发生，次年红冲或退回系真实退费并已作跨期调整，提供原发票、退费凭证与调整分录可证",
    ],
    "RL-COST-006": [
        "工资或劳务费对应真实用工与考勤、个税扣缴与银行代发记录，提供用工合同与支付流水可证非虚列套取",
    ],
    "RL-FUND-001": [
        "公转私系真实薪酬、报销或分红，已依法扣缴个税并留存审批与发放明细，提供银行流水与凭证可证非拆分规避监管",
    ],
    "RL-FUND-002": [
        "资金闭环系真实业务链（如委托收款、票据贴现周转），提供各方协议与业务背景可证非虚构循环回流",
    ],
    "RL-FUND-003": [
        "股东借款已按税法规定在年度终了视作分红扣缴个税，或已签订还款计划并实际归还，提供处理记录可证",
    ],
    "RL-FUND-004": [
        "现金交易系行业惯例（如农产品收购、小额零售），已按规定开具收据并入账，提供现金日报表与存货可证非规避留痕",
    ],
    "RL-FUND-005": [
        "多账户互转系真实资金调度（如母子户、项目专户），提供账户清单与调度审批可证非掩饰资金来源与去向",
    ],
    "RL-FUND-006": [
        "红字或负数冲抵系正常差错更正或退货冲账，提供原凭证与更正依据可证非异常操纵",
    ],
    "RL-INV-001": [
        "存货盘亏已按规定报批并作进项转出或损失税前扣除，提供盘点表、审批与税务处理可证",
    ],
    "RL-INV-002": [
        "已提供可变现净值测算与跌价准备计提依据，计提充分符合准则可证",
    ],
    "RL-INV-003": [
        "已说明投入产出与废料、副产品归集口径，提供副产品销售台账与申报记录可证非隐瞒副产品销售",
    ],
    "RL-PAY-001": [
        "已核实工资发放名单与在职状态，离职人员工资系代发尾薪或误列已更正，提供社保减员与发放记录可证非虚列",
    ],
    "RL-PAY-002": [
        "发放拆分系依法选择计税方式（如单独计税），已合并计入综合所得或按规定申报，提供个税计算可证非降低计税基数",
    ],
    "RL-PAY-003": [
        "已核实人员真实身份与用工记录，身份证异常系录入差错已更正，提供考勤、合同与银行代发可证非冒用身份虚列",
    ],
    "RL-PAY-004": [
        "高管已签订劳动合同并全额按工资薪金申报个税，咨询费或劳务费对应独立业务与成果，提供合同与申报可证非规避工资薪金个税",
    ],
    "RL-PAY-005": [
        "已按规定代扣个税并取得税务机关代开发票或留存扣缴记录，提供代开或扣缴凭证可证",
    ],
    "RL-PAY-006": [
        "已提示个人在汇算清缴时合并综合所得，或企业已就多处所得履行扣缴义务，提供申报记录可证",
    ],
    "RL-CIT-001": [
        "已补备同期资料与转让定价文档，或关联交易未达准备门槛，提供文档与测算可证",
    ],
    "RL-CIT-002": [
        "已按独立交易原则作视同销售或纳税调整，提供定价依据与调整分录可证",
    ],
    "RL-CIT-003": [
        "已提供研发人员工时分配与项目立项，仅将实际从事研发人员工资计入，提供考勤与分配表可证非虚增加计扣除",
    ],
    "RL-CIT-004": [
        "已说明亏损成因（市场培育、投产初期）与扩产商业合理性，提供可行性研究与投资记录可证非收入或成本不实",
    ],
    "RL-CIT-005": [
        "亏损额系真实经营亏损并经审计，提供纳税申报与鉴证可证非虚构亏损额抵减",
    ],
    "RL-CIT-006": [
        "资产损失已按规定认定并报备，与经营亏损分别核算，提供损失证据与报备可证非包装为资产损失",
    ],
    "RL-CIT-007": [
        "已按税法限额作纳税调增，科目混用已重分类，提供调整表与凭证可证",
    ],
    "RL-PTY-001": [
        "已说明该供应链安排的公允商业目的（如集团内分工），提供独立交易价格与货物流可证非自买自卖虚增",
    ],
    "RL-PTY-002": [
        "已提供供应商实地经营佐证（经营场所、人员、社保、实地核查记录），证实真实经营、非空壳供货",
    ],
    "RL-PTY-003": [
        "已说明三方委托加工关系与发票开具主体，提供委托加工合同与加工方确认可证票货一致",
    ],
    "RL-PTY-004": [
        "已提供投料产出与废料、在产品归集口径及损耗率测算，提供生产台账可证非隐瞒产出售",
    ],
    "RL-PTY-005": [
        "已说明购方信息差异原因（如总分公司、代理采购），提供真实交易合同与物流可证非替票或代开",
    ],
    "RL-AST-001": [
        "已说明未转固原因（验收结算未完成）并已按暂估转固计提折旧，提供工程进度与折旧分录可证",
    ],
    "RL-AST-002": [
        "已将不征税收入对应支出单独核算并作纳税调增，提供科目设置与调整可证",
    ],
    "RL-AST-003": [
        "整数尾数系合同定价（按件、按吨或含税额取整）所致，提供合同与流水可证非人为构造",
    ],
    "RL-OTH-001": [
        "已梳理电子订单与框架协议并按规定申报印花税，提供应税凭证清单与申报可证",
    ],
    "RL-OTH-002": [
        "已按税法将地价、装修等并入房产原值，提供入账依据与计税调整可证",
    ],
    "RL-OTH-003": [
        "已按现行规定将免抵增值税额计入城市维护建设税计税依据并补缴，提供申报调整可证",
    ],
    "RL-OTH-004": [
        "已提供免税土地批文或权属证明，或已据实申报，提供文件可证",
    ],
    "RL-OTH-005": [
        "已办理车辆税源信息变更或注销并停申报，提供过户与报废凭证可证",
    ],
    "RL-OTH-006": [
        "已按税法将返利冲减收入并作进项转出（如适用），提供返利协议与处理可证",
    ],
    "RL-SPT-001": [
        "已提供开发成本合同、付款与竣工决算，成本真实可证非虚增建安或前期费用",
    ],
    "RL-SPT-002": [
        "已按视同销售缴纳消费税，提供移送用途与完税凭证可证",
    ],
    "RL-SPT-003": [
        "已按应税产品实际税率申报并补缴，提供产品认定与申报调整可证",
    ],
    "RL-SPT-004": [
        "已采用合规监测数据并按实际排放量申报，提供监测报告与申报可证",
    ],
    "RL-SPT-005": [
        "已按海关估价规定将相关费用并入完税价格并补税，提供合同与报关调整可证",
    ],
    "RL-SPT-006": [
        "已按规定代扣预提所得税并申报，提供扣缴凭证可证",
    ],
    "RL-SPT-007": [
        "已按承受权属申报契税，提供抵债或作价协议与完税可证",
    ],
    "RL-SPT-008": [
        "已说明金额差异原因（如佣金、运保费列示口径）并如实申报，提供合同与报关单可证非高报出口骗税",
    ],
    "RL-SPT-009": [
        "已按真实转让价格申报纳税，提供真实合同与付款凭证可证非低报避税",
    ],
    "RL-SPT-010": [
        "已按实际工资基数补缴社保，提供工资台账与补缴记录可证",
    ],
    "RL-SPT-011": [
        "已按规定设置账簿并取得合规凭证，或核定征收系税务机关依法核定，提供账簿与凭证可证",
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


def _find_list_block(lines, start, key):
    """在 lines[start:] 找 `"key": [ ... ]` 块，返回 [起行, 止行(含])]。"""
    j = None
    for k in range(start, min(start + 400, len(lines))):
        if ('"%s"' % key) in lines[k] and "[" in lines[k]:
            j = k
            break
    assert j is not None, "未找到 %s 起始" % key
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
    assert close >= 0, "%s 括号不匹配" % key
    head = buf[:close + 1]
    end_line = j + head.count("\n")
    return j, end_line


def main():
    # 仅保留有新增反证的红线条目（其余 rid 在 JUSTIFY_EXTRA 中以 [] 占位，跳过）
    todo = {rid: v for rid, v in JUSTIFY_EXTRA.items() if v}
    assert set(todo) == set(ORIG_J), "JUSTIFY_EXTRA 与 ORIG_J 的 rid 集合不一致"

    with open(SRC, encoding="utf-8") as f:
        text = f.read()
    before = _load(text)
    by_id = {r["id"]: r for r in before.REDLINES}

    lines = text.split("\n")
    changed = 0
    # 逐 redline 处理（重新定位起点，避免位置错位）
    for rid, extras in todo.items():
        # 定位红线起点
        start = None
        for i, ln in enumerate(lines):
            if re.search(r'"id"\s*:\s*"%s"' % re.escape(rid), ln):
                start = i
                break
        assert start is not None, "%s 未定位" % rid
        j, end_line = _find_list_block(lines, start, "justifications")
        base_indent = re.match(r"\s*", lines[j]).group(0)
        item_indent = base_indent + "    "
        # 现有条目（去空白引号）用于幂等判定
        exist = set()
        for ln in lines[j + 1:end_line]:
            s = ln.strip().strip(",").strip()
            if s.startswith('"') and s.endswith('"'):
                exist.add(s[1:-1])
        new_entries = []
        for e in extras:
            if e in exist:
                continue  # 幂等：已存在不重复追加
            new_entries.append('%s"%s",' % (item_indent, e))
        if new_entries:
            # 保证前一条（最后一个旧条目）以逗号结尾，否则新条目会与其黏合成一条字符串字面量
            prev = lines[end_line - 1]
            if prev.strip().startswith('"') and not prev.rstrip().endswith(','):
                lines[end_line - 1] = prev.rstrip() + ','
            # 插入到闭合 ] 之前
            lines[end_line:end_line] = new_entries
            changed += 1

    new_text = "\n".join(lines)

    # 重新导入验证
    after = _load(new_text)
    new_by_id = {r["id"]: r for r in after.REDLINES}
    assert len(after.REDLINES) == len(before.REDLINES)
    total = 0
    for rid, extras in todo.items():
        jl = new_by_id[rid].get("justifications") or []
        total += len(jl)
        exp = ORIG_J[rid] + len(extras)
        assert len(jl) == exp, "%s justifications 期望 %d，实际 %d" % (rid, exp, len(jl))
        for e in extras:
            assert e in jl, "新增反证未落地：%s" % e[:30]
    # 全量非空校验
    for r in after.REDLINES:
        assert (r.get("justifications") or []), "%s justifications 为空" % r["id"]
    assert total == EXPECTED_TOTAL, "全局 justifications 期望 %d，实际 %d" % (EXPECTED_TOTAL, total)

    with open(SRC, "w", encoding="utf-8") as f:
        f.write(new_text)

    added = sum(len(v) for v in todo.values())
    print("OK: 为 %d 条红线追加 %d 条新场景反证（幂等，已落地的不重复）" % (changed, added))
    print("OK: justifications 总数 228 -> %d（预期 %d）" % (total, EXPECTED_TOTAL))


if __name__ == "__main__":
    main()
