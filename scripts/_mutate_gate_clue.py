# -*- coding: utf-8 -*-
"""升级既有「线索链三态」闸门为**行为级**断言（疑点1 D5/D6/D7 收口配套）。

旧版只查两处**旧文案**（"不计入资料缺失" / observed 恰等于"本轮未取得该项资料"），
既挡不住"资料未提供却给出读数"（D5/D6 的真正病根），也会因为文案改进而误报。
新版断言的是**行为**：
  a) 资料已提供但本环节无对题读数 ⇒ 必须写"未产出对题读数"且**不得混入数字**，reason=engine_gap；
  b) 资料确未提供 ⇒ 必须**点名缺哪份资料**、has_data=False、reason=material_missing；
  c) 带括号说明的资料名（"销项发票（含红字标识）"）必须能归一到类别，不得误判未提供；
  d) 有对题命中证据 ⇒ 必须**原样采用**该证据（唯一权威=要件命中证据）；
  e) 对题阈值必须挡得住不相干要件（否则 D7「拿不适用资料冒充已核对」复发）。
"""
import io
import os
import sys

NL = chr(10)
P = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "tools", "audit_consistency.py")

OLD = '''    # ① 线索链三态：资料已提供的环节不得写"本轮未取得该项资料"
    try:
        from engine.clue_chain import build_clue_chain
        _rl = {"id": "RL-T", "name": "测试红线",
               "clue_chain": [{"step": 1, "source": "工资表", "action": "a", "output": "o"}]}
        _f = {"type": "t", "detail": "金额5万元，需核实"}
        _c1 = build_clue_chain(_f, _rl, {}, provided_materials=["工资表"])
        if "不计入资料缺失" not in str((_c1.get("nodes") or [{}])[0].get("observed", "")):
            issues.append(("ERROR", "engine/clue_chain.py",
                           "资料已提供但环节无数据时，仍写「本轮未取得该项资料」（与已提供清单矛盾）"))
        if not _c1.get("data_gaps") or _c1["data_gaps"][0].get("reason") != "engine_gap":
            issues.append(("ERROR", "engine/clue_chain.py",
                           "engine_gap 三态标记缺失"))
        _c2 = build_clue_chain(_f, _rl, {}, provided_materials=[])
        if str((_c2.get("nodes") or [{}])[0].get("observed", "")) != "本轮未取得该项资料":
            issues.append(("ERROR", "engine/clue_chain.py",
                           "资料确未提供时应保留「本轮未取得该项资料」"))
        if not _c2.get("data_gaps") or _c2["data_gaps"][0].get("reason") != "material_missing":
            issues.append(("ERROR", "engine/clue_chain.py",
                           "material_missing 三态标记缺失"))
    except Exception as exc:
        issues.append(("ERROR", "engine/clue_chain.py", f"线索链三态断言执行失败: {exc}"))
'''

NEW = '''    # ① 线索链环节：**资料有无**与**读数有无**必须同源（2026-10-04 疑点1 D5/D6/D7 收口）
    #    ★ 本检查由"只查旧文案"升级为**行为级**断言（旧版只认「不计入资料缺失」这句措辞，
    #      挡不住真正病根——"资料未提供却给出读数"、"读数与本环节不对题"）。
    try:
        from engine.clue_chain import build_clue_chain
        import re as _re_clue
        _rl = {"id": "RL-T", "name": "测试红线",
               "clue_chain": [{"step": 1, "source": "工资表", "action": "a", "output": "o"}]}
        _f = {"type": "t", "detail": "金额5万元，需核实"}

        # a) 资料已提供但本环节无对题读数 ⇒ 如实标注，且**不得混入数字**
        _c1 = build_clue_chain(_f, _rl, {}, provided_materials=["工资表"])
        _n1 = (_c1.get("nodes") or [{}])[0]
        if "未产出对题读数" not in str(_n1.get("observed", "")) or _n1.get("has_data"):
            issues.append(("ERROR", "engine/clue_chain.py",
                           "资料已提供但本环节无对题读数时，未如实标注「未产出对题读数」"))
        if _re_clue.search(r"\\d", str(_n1.get("observed", ""))):
            issues.append(("ERROR", "engine/clue_chain.py",
                           "本环节无读数却仍给出数字（拿别的环节的数顶替）"))
        if not _c1.get("data_gaps") or _c1["data_gaps"][0].get("reason") != "engine_gap":
            issues.append(("ERROR", "engine/clue_chain.py", "engine_gap 三态标记缺失"))

        # b) 资料确未提供 ⇒ 必须**点名缺哪份**（面向企业说具体材料名），且不得给读数
        _c2 = build_clue_chain(_f, _rl, {}, provided_materials=[])
        _n2 = (_c2.get("nodes") or [{}])[0]
        if "因缺少资料" not in str(_n2.get("observed", "")) or "工资表" not in str(_n2.get("observed", "")):
            issues.append(("ERROR", "engine/clue_chain.py",
                           "资料未提供时未点名缺失的具体资料名"))
        if _n2.get("has_data"):
            issues.append(("ERROR", "engine/clue_chain.py", "资料未提供却判为有数据"))
        if not _c2.get("data_gaps") or _c2["data_gaps"][0].get("reason") != "material_missing":
            issues.append(("ERROR", "engine/clue_chain.py", "material_missing 三态标记缺失"))

        # c) 带括号说明的资料名必须能归一到类别（旧实现整片精确匹配 ⇒ 永远匹配不上）
        _rl_c = {"id": "RL-T", "name": "n",
                 "clue_chain": [{"step": 1, "source": "销项发票（含红字标识）",
                                 "action": "a", "output": "o"}]}
        _n_c = (build_clue_chain(_f, _rl_c, {}, provided_materials=["销项发票"]).get("nodes") or [{}])[0]
        if "因缺少资料" in str(_n_c.get("observed", "")):
            issues.append(("ERROR", "engine/clue_chain.py",
                           "带括号说明的资料名未归一到类别，被判「未提供」"))

        # d) 有对题命中证据 ⇒ 必须**原样采用**（环节读数唯一权威 = 要件命中证据）
        _rl_d = {"id": "RL-T", "name": "n", "constituents": ["存在红字发票或作废发票（红冲行为）"],
                 "clue_chain": [{"step": 1, "source": "销项发票",
                                 "action": "统计红字与作废发票金额、占比",
                                 "output": "红冲率与时间分布特征"}]}
        _ev = "销项红字/作废 1,015,900.00 元，占同期销项蓝字开票额 12.6%"
        _f_d = {"type": "t", "detail": "共13张涉及红冲",
                "constituent_hits": [{"index": 1, "evidence": _ev}]}
        _n_d = (build_clue_chain(_f_d, _rl_d, {}, provided_materials=["销项发票"]).get("nodes") or [{}])[0]
        if str(_n_d.get("observed", "")) != _ev or not _n_d.get("has_data"):
            issues.append(("ERROR", "engine/clue_chain.py",
                           "有对题命中证据时未原样采用（环节读数须以要件命中证据为唯一权威）"))

        # e) 对题阈值必须挡得住不相干要件（否则"拿不适用资料冒充已核对"复发）
        _rl_e = {"id": "RL-T", "name": "n", "constituents": ["与被冲减蓝字发票不配平"],
                 "clue_chain": [{"step": 1, "source": "银行流水",
                                 "action": "核对红冲是否对应退款", "output": "红冲真实性判断"}]}
        _f_e = {"type": "t", "detail": "x",
                "constituent_hits": [{"index": 1,
                                      "evidence": "红字发票备注/状态中未见退货、折让等合法事由"}]}
        _n_e = (build_clue_chain(_f_e, _rl_e, {}, provided_materials=["银行流水"]).get("nodes") or [{}])[0]
        if _n_e.get("has_data"):
            issues.append(("ERROR", "engine/clue_chain.py",
                           "对题阈值失效：不相干的要件命中证据被当成该环节读数"))
    except Exception as exc:
        issues.append(("ERROR", "engine/clue_chain.py", f"线索链环节一致性断言执行失败: {exc}"))
'''

s = io.open(P, "r", encoding="utf-8", newline="").read()
crlf = "\r\n" in s
s = s.replace("\r\n", NL)
if s.count(OLD) != 1:
    print("!! anchor 命中 %d 次" % s.count(OLD))
    sys.exit(2)
s = s.replace(OLD, NEW, 1)
if crlf:
    s = s.replace(NL, "\r\n")
io.open(P, "w", encoding="utf-8", newline="").write(s)
print("OK 闸门已升级为行为级断言（含对题阈值反向保护）")
