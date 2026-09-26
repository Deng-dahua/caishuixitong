"""体检四项修复复核（2026-09-14）：直接读 RERUN4 生成的真实报告 JSON。
对照 4 个修复点：
  ① 公司3 VR055 工资均额/拆分疑点：误报消除（条数=0）+ 无重复
  ② 公司1 VR060 主营成本资金证据链：重复两条 → 合并为 1 条
  ③ 公司1 VR056 公私混同发薪：金额口径（公户>=账面 不再称"重大背离"）
  ④ 公司3 有进无销风险：高风险误判 → 中风险（加工链条解释）
输出 _verify.txt。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FR = os.path.join(HERE, "four_reports")


def load(cid):
    with open(os.path.join(FR, "company_%d_full.json" % cid), "r", encoding="utf-8") as f:
        return json.load(f)


def get_scenario_findings(rep):
    comp = rep.get("comprehensive") or {}
    se = comp.get("scenario_execution") or {}
    return se.get("findings") or []


def find_by_type(findings, kw):
    return [f for f in findings if kw in (f.get("type") or "")]


lines = []
def log(s):
    lines.append(s)


# ---------- ① 公司3 VR055 ----------
rep3 = load(3)
f3 = get_scenario_findings(rep3)
vr055 = find_by_type(f3, "工资薪酬均额") or find_by_type(f3, "VR055") or [f for f in f3 if "VR055" in str(f.get("rule_id") or "")]
log("① 公司3 VR055「工资薪酬均额/拆分疑点」")
log("   VR055 条数=%d  %s" % (len(vr055), "PASS消除" if len(vr055) == 0 else "FAIL仍触发"))
for f in vr055:
    log("   - %s | %s | %s" % (f.get("type"), f.get("level"), str(f.get("detail"))[:160]))

# ---------- ④ 公司3 有进无销 ----------
log("")
log("④ 公司3「有进无销风险」")
buy_no_sell = find_by_type(f3, "有进无销")
log("   有进无销 条数=%d" % len(buy_no_sell))
ok4 = True
for f in buy_no_sell:
    lvl = f.get("level")
    resolved = f.get("_phase3_conflict_resolved")
    log("   - level=%s resolved=%s" % (lvl, resolved))
    if lvl != "中风险":
        ok4 = False
log("   %s" % ("PASS中风险" if (len(buy_no_sell) == 1 and ok4) else "FAIL"))

# ---------- ③ 公司1 VR056 ----------
rep1 = load(1)
f1 = get_scenario_findings(rep1)
vr056 = find_by_type(f1, "公私混同") or [f for f in f1 if "VR056" in str(f.get("rule_id") or "")]
log("")
log("③ 公司1 VR056「公私混同发薪」")
log("   VR056 条数=%d" % len(vr056))
ok3 = True
for f in vr056:
    det = str(f.get("detail") or "")
    has_div = "重大背离" in det
    has_cov = ("已覆盖并超过" in det) or ("覆盖并超过" in det)
    log("   - level=%s | 含'重大背离'=%s | 含'已覆盖并超过'=%s" % (f.get("level"), has_div, has_cov))
    if has_div:
        ok3 = False
log("   %s" % ("PASS口径正确" if (len(vr056) >= 1 and ok3) else "FAIL仍称重大背离"))

# ---------- ② 公司1 VR060 ----------
log("")
log("② 公司1 VR060「主营业务成本资金与负债证据链核验」")
vr060 = find_by_type(f1, "主营业务成本资金") or [f for f in f1 if "VR060" in str(f.get("rule_id") or "")]
log("   VR060 条数=%d" % len(vr060))
if len(vr060) == 1:
    m = vr060[0].get("_merged_from")
    log("   merged_from=%s  %s" % (m, "PASS已合并" if m and m >= 2 else "PASS单条(无需合并)"))
else:
    log("   FAIL 仍为%d条（未合并）" % len(vr060))
ok2 = (len(vr060) == 1)

log("")
log("===== 复核汇总 =====")
log("① VR055消除: %s" % ("PASS" if len(vr055) == 0 else "FAIL"))
log("② VR060合并: %s" % ("PASS" if ok2 else "FAIL"))
log("③ VR056口径: %s" % ("PASS" if (len(vr056) >= 1 and ok3) else "FAIL"))
log("④ 有进无销降级: %s" % ("PASS" if (len(buy_no_sell) == 1 and ok4) else "FAIL"))

out = os.path.join(HERE, "_verify.txt")
with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print("\n".join(lines))
print("\n[written] %s" % out)
