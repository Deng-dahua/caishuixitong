"""反向验证（A 轨道·为 RL-VAT-012 净增量建真检测器）—— 破坏后必须变红，证明判据不是假绿。

证明四件事：
  R27：篡改覆盖率权威产物（把**只靠"有检测器"豁免**的 `RL-VAT-008` 从 `has_detector` 移除）
       ⇒ `check_redline_overlap_ledger` 必须 ERROR（"登记为要件重复、又无检测器、
       却未声明有意不兜底"）—— 证明「有真检测器 ⇒ 豁免」这条**分支仍然是活的**。
       ★ 前提必须与判据分支对齐（2026-10-10 实测修正）：该闸门对 `constituent_duplicate`
       成员有**两条**豁免——①`has_detector` ②`_NO_BLIND_CONSTITUENT_FALLBACK`。`RL-VAT-012`
       **两条都占**（有检测器 **且** 有意不兜底），故只抽掉①而不动②，闸门**正确地**不报；
       那不是假绿，而是反向验证的前提写错了。R27c 专门覆盖"两豁免全摘 ⇒ 012 也必红"。
  R27c：去掉 012 的检测器 **且** 在进程内摘掉它的 `_NO_BLIND` 豁免 ⇒ 台账闸门必须 ERROR，
       证明 012 也在同一判据约束之下（不是判据够不着的死角）。篡改后逐字节还原。
  R28：篡改归属登记表（把 012 行的 `detector_file` 指向不存在/非生产代码）⇒
       `check_redline_detector_attribution` 必须 ERROR。
  R29：端到端行为 —— VR036 通道3 正例必须 `redline_id=RL-VAT-012` + 要件[2,3]；
       两类负例（已计提销项 / 正常销售成本结转）必须**不报**（防假阳性）。
  R30：008/012 的**合并评审**必须已记录（防"建完检测器却不回到冗余裁定"）。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

RESULTS = []
_COV = Path("scripts") / "_redline_coverage.json"
_TBL = Path("config") / "redline_detector_attribution.json"


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(("  [PASS] " if ok else "  [FAIL] ") + name + (("  :: " + detail) if detail and not ok else ""))


def main() -> int:
    from tools.audit_consistency import (check_redline_overlap_ledger as ledger,
                                        check_redline_detector_attribution as attr)
    from engine import verified_rule_engine as vre

    spec = {s["id"]: s for s in vre.VERIFIED_RULE_CATALOG}["VR036"]

    # ── R27 覆盖率产物被篡改 ⇒ 台账闸门必须 ERROR（证明豁免分支是活的）──────
    #   ★ 用**只靠"有检测器"豁免**的 RL-VAT-008（has_detector=True / _NB=False / _DH=False）。
    #     抽掉它的检测器后，两条豁免都不占 ⇒ 闸门必然变红。（012 两条豁免都占，只抽①不动②
    #     时闸门**正确**不报，见 R27c 的反向触发。）
    print("\n[R27] 篡改 _redline_coverage.json（去掉 008 的检测器）⇒ 台账闸门必须 ERROR")
    _orig_cov = _COV.read_bytes()
    try:
        _d = json.loads(_orig_cov.decode("utf-8"))
        _d["has_detector"] = [r for r in _d.get("has_detector") or [] if r != "RL-VAT-008"]
        _d["has_detector_static"] = [r for r in _d.get("has_detector_static") or [] if r != "RL-VAT-008"]
        _COV.write_text(json.dumps(_d, ensure_ascii=False, indent=2), encoding="utf-8")
        issues = ledger()
        check("抓「无真检测器却未声明有意不兜底」(008)",
              any(i[0] == "ERROR" and "RL-VAT-008" in i[2] for i in issues), repr(issues[:3]))
    finally:
        _COV.write_bytes(_orig_cov)

    print("\n[R27b] 还原后台账闸门必须回到无 ERROR")
    check("还原后 ERROR 为空（判据非恒真）", [i for i in ledger() if i[0] == "ERROR"] == [])

    # ── R27c 012 亦受同一判据约束：两豁免全摘 ⇒ 必须 ERROR ───────────────
    print("\n[R27c] 去掉 012 的检测器 **且** 摘掉其 _NO_BLIND 豁免 ⇒ 台账闸门必须 ERROR")
    import engine.redline_engine as _re_mod
    _orig_cov2 = _COV.read_bytes()
    _orig_nb = list(_re_mod._NO_BLIND_CONSTITUENT_FALLBACK)
    try:
        _d = json.loads(_orig_cov2.decode("utf-8"))
        _d["has_detector"] = [r for r in _d.get("has_detector") or [] if r != "RL-VAT-012"]
        _d["has_detector_static"] = [r for r in _d.get("has_detector_static") or [] if r != "RL-VAT-012"]
        _COV.write_text(json.dumps(_d, ensure_ascii=False, indent=2), encoding="utf-8")
        _re_mod._NO_BLIND_CONSTITUENT_FALLBACK = [x for x in _orig_nb if x != "RL-VAT-012"]
        issues = ledger()
        check("抓「012 无检测器且无 _NO_BLIND 豁免」",
              any(i[0] == "ERROR" and "RL-VAT-012" in i[2] for i in issues), repr(issues[:3]))
    finally:
        _COV.write_bytes(_orig_cov2)
        _re_mod._NO_BLIND_CONSTITUENT_FALLBACK = _orig_nb

    print("\n[R27d] 还原后台账闸门必须回到无 ERROR")
    check("还原后 ERROR 为空（非恒真）", [i for i in ledger() if i[0] == "ERROR"] == [])

    # ── R28 归属登记表被篡改 ⇒ 归属闸门必须 ERROR ────────────────────────
    print("\n[R28] 篡改归属登记表（012 行 detector_file 指向非生产代码）⇒ 归属闸门必须 ERROR")
    _orig_tbl = _TBL.read_bytes()
    try:
        _t = json.loads(_orig_tbl.decode("utf-8"))
        _hit = False
        for _row in _t["declarations"]:
            if _row.get("redline_id") == "RL-VAT-012":
                _row["detector_file"] = "scripts/_audit_redline_coverage.py"
                _hit = True
        check("登记表存在 RL-VAT-012 行", _hit)
        _TBL.write_text(json.dumps(_t, ensure_ascii=False, indent=2), encoding="utf-8")
        issues = attr()
        check("抓「detector_file 不是生产代码」",
              any(i[0] == "ERROR" and "不是生产代码" in i[2] for i in issues), repr(issues[:3]))
    finally:
        _TBL.write_bytes(_orig_tbl)

    print("\n[R28b] 还原后归属闸门必须无 ERROR")
    check("还原后 ERROR 为空", [i for i in attr() if i[0] == "ERROR"] == [])

    # ── R29 端到端行为：正例 / 两个负例 ─────────────────────────────────
    print("\n[R29] 端到端：VR036 通道3 正例必须归 RL-VAT-012 + 要件[2,3]；负例必须不报")
    invest = [
        {"month_no": "3", "voucher_no": "记-8", "summary": "以存货对外投资",
         "account_name": "长期股权投资/某公司", "account": "1511", "debit": 120000.0, "credit": 0.0},
        {"month_no": "3", "voucher_no": "记-8", "summary": "以存货对外投资",
         "account_name": "库存商品/A产品", "account": "1405", "debit": 0.0, "credit": 120000.0},
    ]
    fs = vre._SCANNERS["VR036"]({"vouchers": invest}, spec)
    dl = [f for f in fs if f.get("redline_id") == "RL-VAT-012"]
    check("正例产出且归属 RL-VAT-012", len(dl) == 1, repr([f.get("redline_id") for f in fs]))
    check("只认领真算过的要件②③（未算的①④不认领）",
          [h.get("index") for h in (dl[0].get("constituent_hits") or [])] == [2, 3] if dl else False)
    check("成本口径金额取自存货贷方转出", float((dl[0].get("observed_metrics") or {}).get(
        "invest_distribute_total") or 0) == 120000.0 if dl else False)

    ok_v = invest + [{"month_no": "3", "voucher_no": "记-8", "summary": "以存货对外投资",
                      "account_name": "应交税费/应交增值税/销项税额", "account": "22210105",
                      "debit": 0.0, "credit": 15600.0}]
    fs2 = vre._SCANNERS["VR036"]({"vouchers": ok_v}, spec)
    check("负例①已计提销项税额 ⇒ 不得报未计提销项",
          all(f.get("redline_id") != "RL-VAT-012" for f in fs2))

    sales_v = [
        {"month_no": "5", "voucher_no": "记-9", "summary": "结转销售成本",
         "account_name": "主营业务成本/商品成本", "account": "6401", "debit": 80000.0, "credit": 0.0},
        {"month_no": "5", "voucher_no": "记-9", "summary": "结转销售成本",
         "account_name": "库存商品/C", "account": "1405", "debit": 0.0, "credit": 80000.0},
    ]
    fs3 = vre._SCANNERS["VR036"]({"vouchers": sales_v}, spec)
    check("负例②正常销售成本结转 ⇒ 不得误判为对外投资/分配",
          all(f.get("redline_id") != "RL-VAT-012" for f in fs3))

    # ── R30 合并评审已记录（防"建完不回到冗余裁定"）────────────────────
    print("\n[R30] 008/012 的建后合并评审必须已记录在台账里")
    _lg = json.loads((Path("config") / "redline_overlap_ledger.json").read_text(encoding="utf-8"))
    _pair = [p for p in _lg.get("pairs") or []
             if set(p.get("members") or []) == {"RL-VAT-008", "RL-VAT-012"}]
    check("台账存在 008/012 对", bool(_pair))
    if _pair:
        mr = _pair[0].get("merge_review") or {}
        check("合并评审结论 = keep_both（两条各有独立净增量）", mr.get("verdict") == "keep_both", repr(mr))
        check("已记录『已建真检测器』", bool(_pair[0].get("detector_built_at")), repr(_pair[0].keys()))

    bad = [r for r in RESULTS if not r[1]]
    print("\n" + "-" * 70)
    print("合计 %d 项 | 通过 %d | 失败 %d" % (len(RESULTS), len(RESULTS) - len(bad), len(bad)))
    print("-" * 70)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
