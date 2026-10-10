# -*- coding: utf-8 -*-
"""反向验证：故意破坏「业态剔除单一权威」的各个关键点，确认闸门**真的会变红**。

判据（本项目的规约）：一次报 0 项的闸门，先怀疑**变异无效**，而不是"闸门覆盖到了"。
所以每个变异都要：
  ① 明确打在**参与判定**的代码/数据上；
  ② 报出闸门新增的 ERROR 条数（必须 > 0）；
  ③ 还原后必须回到 0。

用法：./.venv/Scripts/python.exe scripts/_verify_na_gate_reverse.py
"""
import io
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.stdout.reconfigure(encoding="utf-8")


def _read(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


def _write(p, t):
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        f.write(t)


def gate_count():
    """重载闸门模块与**全部 engine 模块**后跑本组检查，返回 (ERROR 条数, 消息)。

    ⚠ 必须连 `engine.*` 一起从 `sys.modules` 清掉 —— 否则变异只写在磁盘上，
      已被导入的模块仍是旧字节码 ⇒ **变异无效**，闸门"报 0"是假象
      （第一版工装就踩了这个坑：M1/M2/M4 全部"未被检出"）。
    """
    for m in [k for k in list(sys.modules)
              if k == "audit_consistency" or k.startswith("engine")]:
        sys.modules.pop(m, None)
    import audit_consistency as A                     # noqa: PLC0415
    iss = (A.check_industry_exclusion_single_source()
           + A.check_metric_key_localized())
    errs = [i for i in iss if i[0] == "ERROR"]
    return len(errs), [i[2] for i in errs]


EC = os.path.join(ROOT, "engine", "evidence_chain.py")
ER = os.path.join(ROOT, "engine", "enterprise_report.py")
AC = os.path.join(ROOT, "tools", "audit_consistency.py")


def mut_m1_char_replace():
    """M1：把引擎层改回**字符级 replace**（本轮修掉的真实病根）。"""
    t = _read(EC)
    old = ('        if role != "反证" and _xna is not None:\n'
           '            # ★ 反证不剔：它是正当理由（不是企业要交的材料），剔空会把反证整条吃掉。\n'
           '            _nm_eff = _xna(name, _na_docs)\n')
    assert old in t, "M1 锚点未命中（源码已变）"
    new = ('        if role != "反证" and _na_docs:\n'
           '            _nm_eff = name\n'
           '            for _mm in _na_docs:\n'
           '                if _mm and _mm in _nm_eff:\n'
           '                    _nm_eff = _nm_eff.replace(_mm, "")\n'
           '            _nm_eff = _nm_eff.strip("、，,；; /（ ）()")\n')
    _write(EC, t.replace(old, new, 1))


def mut_m2_strip_selfimpl():
    """M2：报告层不再薄转发，改回自持一套切段表。"""
    t = _read(ER)
    old = ('    from engine.industry_resolver import exclude_not_required_material as _authority\n'
           '    return _authority(name, not_required)')
    assert old in t, "M2 锚点未命中"
    new = ('    _segs = [x for x in re.split(r"[、/｜|]+", str(name or "")) if x]\n'
           '    _keep = [x for x in _segs if x not in (not_required or [])]\n'
           '    return "".join(_keep)')
    _write(ER, t.replace(old, new, 1))


def mut_m3_dup_sep_table():
    """M3：在另一个模块里又放一份「并列分隔符」正则。"""
    p = os.path.join(ROOT, "engine", "plain_language.py")
    t = _read(p)
    _write(p, t + '\n_NA_SEG_DUP = re.compile(r"[、/]+|与|及|和")\n')


def mut_m4_silent_drop():
    """M4：整项不适用时**静默丢弃**（不记 industry_excluded）。"""
    t = _read(EC)
    old = '                _excluded.append({"role": role, "name": name,'
    assert old in t, "M4 锚点未命中"
    _write(EC, t.replace(old, '                _excluded.append({"role": "", "name": "",', 1))


def mut_m5_raw_key_dump():
    """M5：把唯一实现**整体改回修复前的实现**（裸拼引擎原始英文键、无汉化、无守卫）。

    ⚠ 第一版变异只把 `_translate_key(k)` 换成 `str(k)` —— **变异无效**：
      "未汉化则整条不写"的守卫仍在，英文照样进不了正文，闸门报 0 是**正确**的。
      ⇒ 忠实还原修复前的实现（整块替换）才算有效用例。
    """
    t = _read(ER)
    old = ('        zh = _translate_key(k)\n'
           '        if not zh or re.search(r"[A-Za-z]", str(zh)):\n'
           '            continue                      # 键未汉化 ⇒ 宁可不写，也不让英文变量名入文\n')
    assert old in t, "M5 锚点未命中"
    _write(ER, t.replace(old, '        zh = str(k)\n', 1))


def mut_m6_fallback_to_english():
    """M6：未汉化的键**回落成英文**（而不是整条不写）。"""
    t = _read(ER)
    old = ('        if not zh or re.search(r"[A-Za-z]", str(zh)):\n'
           '            continue                      # 键未汉化 ⇒ 宁可不写，也不让英文变量名入文\n')
    assert old in t, "M6 锚点未命中"
    _write(ER, t.replace(old, "        if not zh:\n            zh = str(k)\n", 1))


def mut_m7_two_impls_again():
    """M7：让两处拼接中的一处不再走唯一实现（恢复"一个概念两份实现"）。"""
    t = _read(ER)
    old = ("                _kv = _metric_kv_text(_met)\n"
           "                if _kv:\n"
           "                    _basis.append(\"量化结果：\" + _kv)\n")
    assert old in t, "M7 锚点未命中"
    _write(ER, t.replace(old,
                         "                _basis.append(\"量化结果：\" + \";\".join(\n"
                         "                    \"%s=%s\" % (k, v) for k, v in list(_met.items())[:8]\n"
                         "                    if isinstance(v, (int, float, str, bool))))\n", 1))


def mut_m8_bool_and_enum_raw():
    """M8：值不再汉化（布尔写 True/False、枚举码原样）。"""
    t = _read(ER)
    old = ('        if isinstance(v, bool):\n'
           '            val = "是" if v else "否"\n'
           '        elif isinstance(v, str) and re.match(r"^[a-z][a-z0-9_]*$", v):\n'
           '            # ★ 枚举码（b2b_or_unknown…）同样是英文 ⇒ 必须译出，译不出就不写这一对\n'
           '            _vz = _translate_key(v)\n'
           '            if re.search(r"[A-Za-z]", str(_vz)):\n'
           '                continue\n'
           '            val = _vz\n'
           '        else:\n'
           '            val = v\n')
    assert old in t, "M8 锚点未命中"
    _write(ER, t.replace(old, '        val = v\n', 1))


def mut_m9_enum_not_registered():
    """M9：**摘掉一条"载重"的指标键登记**（模拟"新增指标但没补汉化数据行"）。

    ⚠ 第一版 M9 是"摘掉枚举码 `b2b_or_unknown`" —— **变异无效**：
      "值译不出就整对不写"的守卫仍在 ⇒ 不会漏英文，闸门报 0 是**正确的**。
      ⇒ 改用**会被产物普查抓到**的变异：摘掉一个"没有它就一定译不出"的键登记
        （`analysis_base_date`；实测摘掉后 `_translate_key` 原样返回英文键）。
    """
    t = _read(ER)
    old = '    "analysis_base_date": "分析基准日",\n'
    assert old in t, "M9 锚点未命中"
    _write(ER, t.replace(old, "", 1))


MUTS = [
    ("M1 引擎层改回字符级 replace", mut_m1_char_replace, [EC]),
    ("M2 报告层不再薄转发", mut_m2_strip_selfimpl, [ER]),
    ("M3 别处又加一份分隔符表", mut_m3_dup_sep_table,
     [os.path.join(ROOT, "engine", "plain_language.py")]),
    ("M4 整项不适用时静默丢弃", mut_m4_silent_drop, [EC]),
    ("M5 量化结果裸拼英文键", mut_m5_raw_key_dump, [ER]),
    ("M6 未汉化键回落成英文", mut_m6_fallback_to_english, [ER]),
    ("M7 两处拼接恢复双实现", mut_m7_two_impls_again, [ER]),
    ("M8 值不汉化(True/False·枚举码)", mut_m8_bool_and_enum_raw, [ER]),
    ("M9 枚举码未登记", mut_m9_enum_not_registered, [ER]),
]


def main():
    base, _ = gate_count()
    print("基准（未变异）ERROR = %d" % base)
    if base:
        print("基准不为 0，先修好再来做反向验证")
        return 1
    ok = True
    for name, fn, files in MUTS:
        bak = {}
        for p in files:
            bak[p] = _read(p)
        try:
            fn()
            n, msgs = gate_count()
            flag = "✔ 有效" if n > 0 else "�’ 无效（变异没被覆盖 ⇒ 闸门有洞）"
            if n == 0:
                ok = False
            print("\n%s  →  ERROR %d  %s" % (name, n, flag))
            for m in msgs[:3]:
                print("      · %s" % m[:120])
        finally:
            for p, t in bak.items():
                _write(p, t)
    after, _ = gate_count()
    print("\n全部还原后 ERROR = %d %s" % (after, "✔" if after == 0 else "✘ 还原不干净"))
    return 0 if (ok and after == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
