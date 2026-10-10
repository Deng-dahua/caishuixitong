# -*- coding: utf-8 -*-
"""扫描「关键词等长打平」残留风险点（check_material_alias_drift 扫不到的那一半）。

背景（2026-10-01 实测，见 scripts/_reverse_verify_alias.py 的 C 组）：
  `check_material_alias_drift` 判据只覆盖两类：
   ① 两条登记项共用**完全相同**的关键词字符串 → 被撞车判据抓住；
   ② 同一文件名上，打平后**赢家门 ≠ 需求名** → 被漂移判据抓住。
  但还有第三种：两条登记项关键词**不同字符串、长度相同**，同时命中同一文件名，
  而赢家恰好是需求名自己（或需求名根本不在这个集合里）→ 闸门**一声不响**。
  此时判定是「靠 _SUPP_ENTRIES 声明顺序侥幸成立」——挪一行顺序就翻车，
  与 PYTHONHASHSEED 那类可复现性坑同族，属静默但迟早爆的缺陷。

本脚本照运行时真语义（`_recognize_supplementary` 的最长命中、等长则声明顺序优先）
枚举所有会打平的文件名，把「已打平」和「危险边缘（只差没同时命中）」都列出来。

用法：python scripts/_scan_kw_ties.py
"""  # noqa: E501
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.material_recognition import (  # noqa: E402
    _SUPP_ENTRIES,
    _recognize_supplementary,
    supplementary_doc_type_to_category,
)
from engine.tax_redlines import all_redlines  # noqa: E402

# 需要被模拟的文件名：红线声明的每一类需求名（就是闸门模拟的那批）
_NEEDS = []
for _r in all_redlines():
    for _m in (_r.get("required_materials") or []):
        _m = str(_m)
        if _m not in _NEEDS:
            _NEEDS.append(_m)
# 连同登记名自身一起扫（登记名也是用户可能上传的叫法）
for _n, _dt, _kws, _e in _SUPP_ENTRIES:
    if _n not in _NEEDS:
        _NEEDS.append(str(_n))


def _hits(filename, _supp=None):
    """返回 [(关键词, 登记名, 注册序)] —— 运行时判定命中的所有关键词（可能多条等长）。"""
    out = []
    for _i, (_name, _dt, _kws, _extra) in enumerate(_supp if _supp is not None
                                                    else _SUPP_ENTRIES):
        for _k in (_kws or []):
            if str(_k) and str(_k) in filename:
                out.append((str(_k), str(_name), _i))
    return out


def _recognize_all(names, supp):
    """用**指定的** _SUPP_ENTRIES 副本跑一遍识别，返回 {需求名: (doc_type, 中文名)}。"""
    out = {}
    for _n in names:
        _dt = _recognize_supplementary(_n + ".xlsx")
        out[_n] = (_dt, (supplementary_doc_type_to_category(_dt)[0] if _dt else None))
    return out


def main():
    # ── 反向验证 + 识别回归 ────────────────────────────────────────────────
    # 把 12 条「登记名全称」长词从内存里的 _SUPP_ENTRIES 剔掉：
    #   ① 打平数必须**回升**到 12（证明本扫描器对打平是敏感的，不是摆设）；
    #   ② 对 224 个文件名的识别结果必须与含长词时**完全一致**（证明加长词不改变判定）。
    import engine.material_recognition as _mr

    def _count_ties(_supp):
        _n = 0
        for _need in _NEEDS:
            _hs = _hits(_need + ".xlsx", _supp)
            if not _hs:
                continue
            # 打平 = 最长命中**有多条**（同登记项内多叫法、或跨登记项撞车都算）
            _b = max(len(x[0]) for x in _hs)
            if len([x for x in _hs if len(x[0]) == _b]) > 1:
                _n += 1
        return _n

    _base = list(_mr._SUPP_ENTRIES)
    _long = [n for n, _d, ks, _x in _base if n in [str(k) for k in (ks or [])]]
    _cut = [(n, d, [k for k in (ks or []) if k != n], x)
            for (n, d, ks, x) in _base]
    _with = _recognize_all(_NEEDS, _base)
    _mr._SUPP_ENTRIES[:] = _cut
    _without = _recognize_all(_NEEDS, _cut)
    _ties_before = _count_ties(_base)
    _ties_after = _count_ties(_cut)
    _mr._SUPP_ENTRIES[:] = _base
    _diff = sorted(k for k in _with if _with[k] != _without.get(k))

    print("=" * 78)
    print("【反向验证 / 识别回归】本脚本口径：剔除 %d 条追加的「登记名全称」长词后复核"
          % len(_long))
    print("  长词清单（前 3）：%s" % "、".join(_long[:3]) + ("…" if len(_long) > 3 else ""))
    print("  ① 打平数：含长词 %d → 剔除长词 %d  %s"
          % (_ties_before, _ties_after,
             "✓ 扫描器敏感" if _ties_after > _ties_before else "✗ 剔除后没回升，扫描器可能失灵"))
    print("  ② 识别结果差异：%s"
          % ("0 处（完全不变）" if not _diff else "！！！%s" % _diff[:5]))
    _ok = (not _diff) and _ties_after > _ties_before
    print("  %s" % ("✓ 反向验证与回归通过" if _ok else "✗ 反向验证或回归未通过"))
    if not _ok:
        print("  （下方打平清单仍按**含长词**的正式配置输出）")
    print("=" * 78)

    flat, risky = [], []
    for need in _NEEDS:
        fn = need + ".xlsx"
        hits = _hits(fn)
        if not hits:
            continue
        best_len = max(len(k) for k, _n, _i in hits)
        winners = [(k, n) for k, n, _i in hits if len(k) == best_len]
        if len(winners) < 2:
            continue          # 唯一最长命中，无打平
        owners = sorted({n for _k, n in winners})
        kw_strs = {k for k, _n in winners}
        flat.append((need, best_len, sorted(kw_strs), owners))
        dt = _recognize_supplementary(fn)
        cat = (supplementary_doc_type_to_category(dt)[0] if dt else None)
        if cat != need:
            risky.append((need, cat))     # 真错（该被闸门抓，列出便于核对）
        else:
            risky.append((need, "靠声明顺序侥幸命中自身", sorted(kw_strs)))

    intra, cross = [], []
    for need, ln, kws, owners in flat:
        if len(owners) > 1:
            cross.append((need, ln, kws, owners))
        else:
            intra.append((need, ln, kws, owners))

    print("=" * 78)
    print("关键词等长打平扫描：共模拟 %d 个文件名，命中打平的有 %d 个"
          % (len(_NEEDS), len(flat)))
    print("  ① 同登记项内多叫法打平（无害，赢家恒为该登记项自身）：%d 个" % len(intra))
    for need, ln, kws, owners in intra:
        print("     《%s.xlsx》 %d字打平：%s" % (need, ln, " | ".join("「%s」" % k for k in kws)))
    print("  ② 跨登记项等长打平（真风险，赢家由声明顺序决定）：%d 个" % len(cross))
    for need, ln, kws, owners in cross:
        print("     《%s.xlsx》 %d字打平：%s → %s"
              % (need, ln, " | ".join("「%s」" % k for k in kws), "、".join(owners)))
    print("\n" + "=" * 78)
    _wrong = [r for r in risky if isinstance(r[1], str)
              and r[1] != "靠声明顺序侥幸命中自身"]
    print("真错（赢家门≠需求名，check_material_alias_drift 会抓）：%d 个 %s"
          % (len(_wrong), _wrong[:3]))
    print("跨登记项打平（check_material_alias_drift 新增判据后会抓）：%d 个" % len(cross))
    if not cross:
        print("结论：当前跨登记项等长打平 = 0，闸门加判据后不会误报；"
              "同登记项打平属刻意容错（一个资料多个叫法），无需消除。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
