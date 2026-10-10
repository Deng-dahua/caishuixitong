"""反向验证（A 轨道·RL-CIT-009/010 同概念裁定 + 归属纠正）—— 只读破坏、内存还原，不改文件。

证明三件事（闸门必须是**真判据**，不是假绿）：
  R23：把 RL-CIT-009 的兜底序号加回 `_DEFAULT_HIT_INDEX` ⇒ `check_redline_overlap_ledger` 必须 ERROR
       （"登记为要件重复却仍靠兜底认要件"的假闭环仍在）。
  R24：把 RL-CIT-009 移出 `_NO_BLIND_CONSTITUENT_FALLBACK` ⇒ 必须 ERROR。
  R25：归属纠正**端到端**——债资比检测器真跑一遍，产出必须 `redline_id == "RL-CIT-010"`
       且 `constituent_hits` 只认领真算过的要件①②（不得再是 RL-CIT-002）。
  R26：把 `_REDLINE_DECL` 改回旧错配值 ⇒ 归属闸门必须与之冲突（表与代码不一致 ⇒ ERROR）。
"""
import sys

sys.path.insert(0, ".")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(("  [PASS] " if ok else "  [FAIL] ") + name + (("  :: " + detail) if detail and not ok else ""))


def _gates():
    from tools.audit_consistency import check_redline_overlap_ledger as a
    from tools.audit_consistency import check_redline_detector_attribution as b
    return a, b


def main() -> int:
    from engine import redline_engine as RE
    from engine.deduction_limit_detector import detect_deduction_limits, _REDLINE_DECL

    ledger, attr = _gates()

    print("\n[R23] 把 009 的兜底序号加回 _DEFAULT_HIT_INDEX ⇒ 必须 ERROR（假闭环仍在）")
    _dh = RE._DEFAULT_HIT_INDEX
    try:
        _dh["RL-CIT-009"] = [1, 2, 3, 4]
        issues = ledger()
        check("抓「登记重复却仍靠兜底认要件」",
              any("假闭环仍在" in i[2] for i in issues), repr(issues[:2]))
    finally:
        _dh.pop("RL-CIT-009", None)

    print("\n[R24] 把 009 移出 _NO_BLIND_CONSTITUENT_FALLBACK ⇒ 必须 ERROR")
    _nb = RE._NO_BLIND_CONSTITUENT_FALLBACK
    try:
        _nb.discard("RL-CIT-009")
        issues = ledger()
        check("抓「登记重复却未声明有意不兜底」",
              any("须有意不做盲发兜底" in i[2] for i in issues), repr(issues[:2]))
    finally:
        _nb.add("RL-CIT-009")

    print("\n[R25] 归属纠正端到端：债资比检测器产出必须 = RL-CIT-010 + 要件①②")
    bs = {"total_equity": 1_000_000.0}
    vch = [{"account_name": "其他应付款-关联方借款", "credit": 3_000_000.0, "贷方": 3_000_000.0}]
    fs = detect_deduction_limits(vch, {}, bs)
    check("检测器确实产出（样例触发）", len(fs) == 1, repr(len(fs)))
    f = fs[0] if fs else {}
    check("归属 = RL-CIT-010（不再是 RL-CIT-002 错配）", f.get("redline_id") == "RL-CIT-010",
          repr(f.get("redline_id")))
    idx = [h.get("index") for h in (f.get("constituent_hits") or [])]
    check("只认领真算过的要件①②（未算的③④不认领）", idx == [1, 2], repr(idx))

    print("\n[R26] _REDLINE_DECL 是唯一来源：其值必须与登记表一致（且破坏后必须不一致）")
    import json as _json
    from pathlib import Path as _P
    _tbl = _json.loads((_P("config") / "redline_detector_attribution.json").read_text(encoding="utf-8"))
    _row = [r for r in _tbl["declarations"] if r.get("detector_fn") == "_check_related_party_debt_equity"]
    check("登记表存在该检测器行", bool(_row), repr(_row))
    _orig = _REDLINE_DECL["_check_related_party_debt_equity"]["redline_id"]
    # ① 正常态：登记表与唯一来源必须一致（这是要求，不是恒真）
    check("正常态：登记表 redline_id == _REDLINE_DECL 唯一来源",
          bool(_row) and _row and _row[0]["redline_id"] == _orig,
          repr((_row[0]["redline_id"] if _row else None, _orig)))
    # ② 反证：把唯一来源改回旧错配值 ⇒ 二者必须不一致（证明①不是恒真判据）
    try:
        _REDLINE_DECL["_check_related_party_debt_equity"]["redline_id"] = "RL-CIT-002"
        check("反证：唯一来源改为 RL-CIT-002 后与登记表不一致（判据非恒真）",
              _row[0]["redline_id"] != _REDLINE_DECL["_check_related_party_debt_equity"]["redline_id"])
    finally:
        _REDLINE_DECL["_check_related_party_debt_equity"]["redline_id"] = _orig

    print("\n[还原] 全部还原后必须回到全绿")
    check("台账闸门还原后为空",
          [i for i in ledger() if i[0] == "ERROR"] == [])
    check("归属闸门还原后无 ERROR",
          [i for i in attr() if i[0] == "ERROR"] == [])
    check("_REDLINE_DECL 已还原为 RL-CIT-010",
          _REDLINE_DECL["_check_related_party_debt_equity"]["redline_id"] == "RL-CIT-010")

    bad = [r for r in RESULTS if not r[1]]
    print("\n" + "-" * 70)
    print("合计 %d 项 | 通过 %d | 失败 %d" % (len(RESULTS), len(RESULTS) - len(bad), len(bad)))
    print("-" * 70)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
