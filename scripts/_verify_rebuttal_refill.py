# -*- coding: utf-8 -*-
"""C2 反证回填实测（2026-09-29）。

验证「企业提交反证 → rebuttal_ratio↑ → 置信度下调」机制确实生效：
  ① build_evidence_chain：finding 提供 reasonable_explanations 命中反证材料名时，
     该反证元素 status 由「待企业提交」翻转为「已提交」；
  ② build_argumentation：rebuttal_ratio 随已提交反证比例上升，confidence 同步下调；
  ③ run_redline_detection 端到端：同一红线，提交反证后 suspicion.confidence 更低。
用法：PYTHONPATH=. python scripts/_verify_rebuttal_refill.py
"""
from engine.tax_redlines import get_redline
from engine.evidence_chain import build_evidence_chain
from engine.argumentation import build_argumentation
from engine.redline_engine import run_redline_detection


def _clue():
    return {"terminal_signal": "检测到相关事实", "nodes": [{"has_data": True}]}


def _evidence_with(rid, submit_text):
    rl = get_redline(rid)
    finding = {"redline_id": rid}
    if submit_text:
        finding["reasonable_explanations"] = [submit_text]
    # 已提供部分资料，使非反证证据项有「已有」以构造可比基线
    mats = rl.get("required_materials") or []
    return build_evidence_chain(finding, rl, available_materials=mats[:2])


def main():
    rid = "RL-VAT-001"
    rl = get_redline(rid)
    errs = []

    # ① 反证状态翻转
    ev_no = _evidence_with(rid, None)
    ev_yes = _evidence_with(rid, "委托加工协议")
    rebut_no = [e for e in ev_no["elements"] if e["role"] == "反证"]
    rebut_yes = [e for e in ev_yes["elements"] if e["role"] == "反证"]
    if not rebut_no or not rebut_yes:
        errs.append("RL-VAT-001 反证元素缺失"); 
        print("[ERROR]", errs); return 1
    n_sub_no = sum(1 for e in rebut_no if e["status"] == "已提交")
    n_sub_yes = sum(1 for e in rebut_yes if e["status"] == "已提交")
    print(f"[反证状态] 未提交反证: 已提交 {n_sub_no}/{len(rebut_no)}；"
          f"提交『委托加工协议』: 已提交 {n_sub_yes}/{len(rebut_yes)}")
    if not (n_sub_no == 0 and n_sub_yes >= 1):
        errs.append("反证状态未随企业提交翻转")

    # ② confidence 随反证提交下调（已提交反证使 ratio 上升；被排除情形不再被 0.60 地板掩盖）
    clue = _clue()
    arg_no = build_argumentation({"level": "中风险"}, rl, clue, ev_no)
    arg_yes = build_argumentation({"level": "中风险"}, rl, clue, ev_yes)
    c_no, c_yes = arg_no["confidence"], arg_yes["confidence"]
    v_no, v_yes = arg_no.get("verdict"), arg_yes.get("verdict")
    print(f"[置信度] 未提交反证: conf={c_no} verdict={v_no}；"
          f"提交反证: conf={c_yes} verdict={v_yes}")
    if not (c_yes < c_no):
        errs.append("置信度未随反证提交下调")
    # 提交反证使 ratio≥0.5 且闭合度不足 → 应判为排除（_VERDICT_EXCLUDED）
    if not (v_yes and v_yes == "经核查未触碰违规红线（已有合理解释）"):
        errs.append("提交反证后未将红线判为排除（rebuttal 机制未闭环）")

    # ③ 端到端 run_redline_detection
    f_no = {"type": rl["name"], "level": "中风险",
            "detail": "检测到有销无进相关事实。", "redline_id": rid}
    f_yes = dict(f_no, reasonable_explanations=["委托加工协议"])
    mats = rl.get("required_materials") or []
    r_no = run_redline_detection([f_no], engine_data={},
                                 material_readiness={"provided": mats})
    r_yes = run_redline_detection([f_yes], engine_data={},
                                  material_readiness={"provided": mats})
    s_no = next((s for s in r_no["suspicions"] if s["redline_id"] == rid), None)
    s_yes = next((s for s in r_yes["suspicions"] if s["redline_id"] == rid), None)
    if not s_no or not s_yes:
        errs.append("端到端未产出 RL-VAT-001 suspicion"); 
        print("[ERROR]", errs); return 1
    print(f"[端到端] 未提交反证 conf={s_no['confidence']}；"
          f"提交反证 conf={s_yes['confidence']}")
    if not (s_yes["confidence"] < s_no["confidence"]):
        errs.append("端到端置信度未随反证提交下调")

    if errs:
        print("[ERROR] C2 反证回填实测未通过：")
        for e in errs:
            print("  -", e)
        return 1
    print("[OK] C2 反证回填机制生效：企业提交反证 → rebuttal_ratio 上升 → 置信度下调（端到端一致）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
