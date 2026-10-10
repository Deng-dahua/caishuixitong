# -*- coding: utf-8 -*-
"""反向验证：证明「资料异名漂移闸门」不是假闸门。

方法论硬要求：每一个闸门/修复都必须做反向验证——故意破坏输入，闸门必须变红；
否则「ERROR 0」只说明闸门没在工作，不说明数据是对的。

本脚本**不改任何产品文件**（进程内破坏 + 用完即还原），规避 safe-delete 守护。

六组验证：
  A. 基线：当前数据下 check_material_alias_drift 必须为空（现在是真的 0）。
  B. 破坏「登记名漂移」（复现 2026-10-01 事故本身）：把 RL-VAT-013 的 required_materials
     加回旧文案「增值税纳税申报表（含留抵税额）」→ 闸门必须报 ERROR。
     ★ 不能靠往 _SUPP_ENTRIES 尾插异名条目来造漂移：闸门模拟的文件名是「需求名+.xlsx」，
       被命中的关键词必须是需求名的子串，且要**严格长于**当前最长命中词；
       「增值税申报表」只有 5 字，塞不进更长的子串 → 这条造不出来（B2 组另做）。
  B2. 破坏「关键词等长打平」：给 sup_transfer_financial 加回旧关键词「转让时点」(4字)，
      它会与 sup_appraisal_report 的「评估报告」(4字) 在同一文件名上等长打平
      → 闸门必须报 ERROR（漂移判据抓的是「打平后赢家名≠需求名」）。
  C. 顺序脆弱性自曝（闸门真盲区）：把 B2 的打平条目**挪到 sup_appraisal_report 之后**，
      此时赢家恰好是正确登记项 → 闸门**不报**（Δ 与 B2 只差一行声明顺序）。
      这证明「等长打平」不是被闸门兜住的，而是靠声明顺序侥幸 → 必须人工留长度差。
  D. 破坏「关键词共用撞车」：插一条与既有条目共用同一关键词字符串的登记项
     → 闸门必须报 ERROR。
  E. 破坏「超类键不得是具体类别名」：往 _MATERIAL_SUPERCLASS 塞一个具体类别名作键
     → check_coverage_source_wiring 必须报 bad_keys。
  F. 破坏「红线需求名必须可登记」：临时塞一条含幽灵资料名的红线
     → check_coverage_source_wiring 必须报 drift。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.audit_consistency import (  # noqa: E402
    check_material_alias_drift,
    check_coverage_source_wiring,
)
import engine.material_recognition as mr  # noqa: E402
import engine.analysis_coverage as ac  # noqa: E402
import engine.tax_redlines as tx  # noqa: E402

_ok = "\033[32m✓\033[0m"
_bad = "\033[31m✗\033[0m"
_pn = os.path.basename(__file__)


def _codes():
    return {i[0] for i in check_material_alias_drift()}


def _cov_codes():
    return {i[0] for i in check_coverage_source_wiring()}


def main():
    fails = []

    # A. 基线
    base = check_material_alias_drift()
    print("A 基线 check_material_alias_drift: %d 条 %s %s"
          % (len(base), _ok if not base else _bad, [b[2][:40] for b in base][:3]))
    if base:
        fails.append("A 基线就非空，先查当前数据")

    # B. 破坏「登记名漂移」：复现 2026-10-01 事故本身（红线文案 ↔ 登记名不同名）
    _orig_rl = tx.all_redlines

    def _sabotaged_redlines():
        out = []
        for _r in _orig_rl():
            if _r.get("id") == "RL-VAT-013":
                _r = dict(_r)
                _r["required_materials"] = (list(_r.get("required_materials") or [])
                                            + ["增值税纳税申报表（含留抵税额）"])
            out.append(_r)
        return out

    tx.all_redlines = _sabotaged_redlines
    try:
        hit = [x for x in check_material_alias_drift() if "增值税纳税申报表" in x[2]]
        print("B 红线文案回退成旧名「增值税纳税申报表（含留抵税额）」→ 闸门 %s %d 条（相关 %d）"
              % (_ok if hit else _bad, len(hit), len(hit)))
        if not hit:
            fails.append("B 闸门未检出登记名漂移 → 闸门是假的")
    finally:
        tx.all_redlines = _orig_rl

    # B2. 破坏「关键词等长打平」（转增时点案）：加回旧关键词「转让时点」
    _tie_kw = "转让时点"
    _saved_lt = None
    for _i, (_n, _dt, _kws, _e) in enumerate(mr._SUPP_ENTRIES):
        if _dt == "sup_transfer_financial":
            _saved_lt = (_i, list(_kws))
            mr._SUPP_ENTRIES[_i] = (_n, _dt, [_tie_kw] + list(_kws), _e)
            break
    try:
        hit = [x for x in check_material_alias_drift() if "转让时点" in x[2]]
        print("B2 给 sup_transfer_financial 加回等长关键词「%s」→ 闸门 %s %d 条（相关 %d）"
              % (_tie_kw, _ok if hit else _bad, len(hit), len(hit)))
        if not hit:
            fails.append("B2 闸门未检出等长打平漂移 → 闸门是假的")
    finally:
        if _saved_lt is not None:
            _i, _kws = _saved_lt
            mr._SUPP_ENTRIES[_i] = (mr._SUPP_ENTRIES[_i][0], mr._SUPP_ENTRIES[_i][1],
                                    _kws, mr._SUPP_ENTRIES[_i][3])

    # C. 顺序脆弱性自曝（闸门真盲区）：打平条目挪到 sup_appraisal_report 之后 → 闸门不报
    _mock_fn = "转让时点财务报表或评估报告.xlsx"
    _mock_m = "转让时点财务报表或评估报告"
    if _saved_lt is not None:
        _i, _kws = _saved_lt
        _entry = (mr._SUPP_ENTRIES[_i][0], mr._SUPP_ENTRIES[_i][1], _kws,
                  mr._SUPP_ENTRIES[_i][3])
        _old = mr._SUPP_ENTRIES[_i]
        mr._SUPP_ENTRIES[_i] = ("<占位>", "sup_evil_placeholder", [], [])
        # 把打平条目塞到注册表末尾（此时「评估报告」声明在先，赢家恰好正确）
        mr._SUPP_ENTRIES.append(_entry)
        try:
            _res = mr._recognize_supplementary(_mock_fn)
            _cat = (mr.supplementary_doc_type_to_category(_res)[0] if _res else None)
            _cnt = len(check_material_alias_drift())
            _flip = "顺序翻转(末尾声明)" if _cat == _mock_m else "顺序保持(靠登记顺序侥幸)"
            print("C 同文件打平但赢家恰好正确 → 识别结果「%s」/ 闸门 %s %d 条 | %s"
                  % (_cat, _ok if not _cnt else _bad, _cnt, _flip))
            if _cnt:
                fails.append("C 与预期不符：打平赢家正确时闸门也报了，边界假设需重写")
        finally:
            mr._SUPP_ENTRIES.remove(_entry)
            mr._SUPP_ENTRIES[_i] = _old

    # D. 破坏「关键词撞车」
    mr._SUPP_ENTRIES.append(("过磅单", "sup_evil_slip", ["过磅单"], []))
    try:
        c = _codes()
        hit = [x for x in check_material_alias_drift() if "过磅单" in x[2]]
        print("D 两条登记项共用关键词「过磅单」→ 闸门 %s %d 条（含过磅单相关：%d）"
              % (_ok if c else _bad, len(c), len(hit)))
        if not hit:
            fails.append("D 闸门未检出关键词撞车 → 闸门是假的")
    finally:
        mr._SUPP_ENTRIES.pop()

    # E. 破坏「超类键不得是具体类别名」
    ac._MATERIAL_SUPERCLASS["增值税申报表"] = ("其他税种申报表",)
    try:
        c = _cov_codes()
        hit = [x for x in check_coverage_source_wiring()
               if "增值税申报表" in x[2] or "具体类别名" in x[2]]
        print("E 往 _MATERIAL_SUPERCLASS 塞具体类别名作键 → 闸门 %s %d 条（bad_keys 相关：%d）"
              % (_ok if c else _bad, len(c), len(hit)))
        if not hit:
            fails.append("E 闸门未检出超类键污染 → 闸门是假的")
    finally:
        del ac._MATERIAL_SUPERCLASS["增值税申报表"]

    # F. 破坏「红线需求名必须可登记」
    _orig = tx.all_redlines
    tx.all_redlines = lambda: list(_orig()) + [{"id": "RL-SANDBOX-999",
                                                "required_materials": ["幽灵资料X"]}]
    try:
        c = _cov_codes()
        hit = [x for x in check_coverage_source_wiring() if "幽灵资料X" in x[2]]
        print("F 红线声明未登记的幽灵资料名 → 闸门 %s %d 条（含幽灵资料名：%d）"
              % (_ok if c else _bad, len(c), len(hit)))
        if not hit:
            fails.append("F 闸门未检出未登记需求名 → 闸门是假的")
    finally:
        tx.all_redlines = _orig

    # G. 验证「跨登记项等长打平」新判据独立有效（旧判据此时应当不响）
    #    构造：把长名登记项 sup_weight_receipt 挪到最前（保证赢家=需求名自身，
    #    漂移判据不响），同时给另一登记项 sup_weight_slip 塞一条 9 字关键词
    #    「过磅单与入库验收」（是需求名的真子串，等长）→ 打平成立、赢家仍正确。
    _need_g = "不动产权证或土地使用证"
    _bak = list(mr._SUPP_ENTRIES)      # 可改的工作副本
    _snap = list(mr._SUPP_ENTRIES)     # 还原用快照（含破坏前的干净 kws）
    try:
        _ia = next(i for i, e in enumerate(_bak) if e[1] == "sup_property_cert")
        _ib = next(i for i, e in enumerate(_bak) if e[1] == "sup_appraisal_report")
        # 保证 A 先声明 → 等长命中的赢家仍是 A（即需求名自身）
        assert _ib > _ia, "构造前提不成立（A 需在 B 之前声明）"
        # 「权证或土地」(5字) 是需求名的真子串，且与 A 的「不动产权证」(5字) 等长 → 打平成立
        _e_b = _bak[_ib]
        _bak[_ib] = (_e_b[0], _e_b[1], list(_e_b[2]) + ["权证或土地"], _e_b[3])
        mr._SUPP_ENTRIES[:] = _bak
        _dt_g = mr._recognize_supplementary(_need_g + ".xlsx")
        _cat_g = mr.supplementary_doc_type_to_category(_dt_g)[0]
        _all_g = check_material_alias_drift()
        _tie = [x for x in _all_g if "不同登记项" in x[2]]
        _drift_g = [x for x in _all_g
                    if "不同登记项" not in x[2] and _need_g in x[2]]
        print("G 跨登记项等长打平（赢家「%s」= 需求名自身、旧判据不响）→ 新判据 %s %d 条；"
              "漂移判据 %s %d 条（应为 0，才可证新判据独立）"
              % (_cat_g, _ok if _tie else _bad, len(_tie),
                 _ok if not _drift_g else _bad, len(_drift_g)))
        if _cat_g != _need_g:
            fails.append("G 构造前提失效（赢家不是需求名自身，漂移判据本就该响）")
        if not _tie:
            fails.append("G 新判据未检出跨登记项等长打平 → 新判据是假的")
        if _drift_g:
            fails.append("G 漂移判据同时响了两枪，无法证明新判据独立有效（需重构造场景）")
    finally:
        mr._SUPP_ENTRIES[:] = _snap

    # 还原后复跑：必须回到空
    after = check_material_alias_drift()
    print("还原后复跑 check_material_alias_drift: %d 条 %s"
          % (len(after), _ok if not after else _bad))
    if after:
        fails.append("还原后仍非空，破坏没清干净")

    print("\n【%s】%s" % (_pn, "反向验证全部通过（6/6 闸门都会变红）" if not fails
                          else "存在失败项：" + "；".join(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
