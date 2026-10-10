# -*- coding: utf-8 -*-
"""check_no_lock_reentrancy 闸门的**干净反向验证**（2026-10-01）。

反向验证只有一条判据：把现场代码**故意改坏**，闸门必须**按判据**变红；且红色必须来自
`ERROR` + 消息含「自死锁」，**不能**来自「语法错误/读取失败」——后者说明坏副本自己就
写坏了，闸门变红是白捡的，等于没验证。为此每道坏副本先过 `ast.parse` 门。

事故本体（用户报「一键分析卡在 99%，生成不了报告」）：
  锁块 → `_write_analysis_checkpoint` → `_is_result_deleted` → `with _analysis_lock:`
  （threading.Lock 不可重入 → 同一线程自己等自己 → CPU 0%、跑 80 分钟不动、状态恒
  running、前端停在 99%、报告其实早已落盘却永远取不到）

跑法（必须用托管 venv，tools/audit_consistency.py 需要 fastapi 所在环境）：
  C:/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python.exe \
      scripts/_reverse_verify_lock_gate.py
"""
import ast
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
_MAIN = os.path.join(_ROOT, "main.py")
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "tools"))

from tools.audit_consistency import check_no_lock_reentrancy  # noqa: E402

_ORIG = open(_MAIN, "r", encoding="utf-8").read()
_TMP_NAMES = []


def _mk(text, name):
    """写临时副本，并检查语法（语法坏的副本不能用于反向验证）。"""
    p = os.path.join(_ROOT, name)
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    _TMP_NAMES.append(p)
    try:
        ast.parse(open(p, encoding="utf-8").read())
    except SyntaxError as e:
        print("  ✗ %s 语法错误（第 %s 行 %s）→ 坏副本不可用，本轮不成立" % (name, e.lineno, e.msg))
        return None
    return p


def _scenario(label, issues, must_be_red):
    if must_be_red:
        if not issues:
            print("  ✗ %s → 闸门没响（预期按判据报 ERROR）" % label)
            return False
        msg = issues[0][2]
        if "解析失败" in msg or "语法错误" in msg:
            print("  ✗ %s → 闸门响，但原因是「%s」= 坏副本语法已坏，本轮验证不成立！" % (label, msg[:40]))
            return False
        if "自死锁" not in msg:
            print("  ✗ %s → 闸门响，但消息不含判据特征「自死锁」：%s" % (label, msg[:80]))
            return False
        print("  ✓ %s → 按判据报 ERROR（%d 条）：%s…" % (label, len(issues), msg[:44]))
        return True
    if issues:
        print("  ✗ %s → 闸门误报 %d 条：%s" % (label, len(issues), issues[0][2][:70]))
        return False
    print("  ✓ %s → 保持绿（不误报）" % label)
    return True


def main():
    print("=" * 78)
    print("【_reverse_verify_lock_gate.py】check_no_lock_reentrancy 干净反向验证")
    print("=" * 78)
    r = []

    r.append(_scenario("0 真实 main.py 基线", check_no_lock_reentrancy(_MAIN), False))

    # —— A：只把取锁侧改回事故态（_is_result_deleted 重新加锁）——————————————
    #    `_run_analysis_thread` 的 except 分支**仍在 `with _analysis_lock:` 内**调用
    #    `_write_analysis_checkpoint`；`_is_result_deleted` 一旦重新加锁，这条链立刻
    #    自死锁 → 闸门必须**按判据**报红。这正是本闸门的主要防护面：
    #   「谁给写回守卫（_is_result_deleted / _write_analysis_checkpoint）加回锁」。
    a_old = ('        for _task_del in list(_analysis_tasks.values()):\n'
             '            if (\n'
             '                _task_del.get("company_id") == company_id\n'
             '                and _task_del.get("status") == "deleted"\n'
             '            ):\n'
             '                return True\n')
    a_new = ('        with _analysis_lock:\n'
             '            for _task_del in list(_analysis_tasks.values()):\n'
             '                if (\n'
             '                    _task_del.get("company_id") == company_id\n'
             '                    and _task_del.get("status") == "deleted"\n'
             '                ):\n'
             '                    return True\n')
    if a_old not in _ORIG:
        print("  ✗ A 构造失败：找不到 _is_result_deleted 的无锁遍历文本（main.py 结构已变）")
        r.append(False)
    else:
        p = _mk(_ORIG.replace(a_old, a_new, 1), "_bad_lockA.py")
        r.append(_scenario("A 取锁侧回退（_is_result_deleted 重新加锁）",
                           check_no_lock_reentrancy(p) if p else [None], True)
                 if p else False)

    # —— B：调用成功检查点塞回 `with _analysis_lock:` 块体内（事故发生时的写法）——
    b_anchor = '                        _analysis_tasks[task_id]["patrol_enrolled"] = True\n'
    b_add = (b_anchor
             + '                        # ★ 恶意插入\n'
             + '                        _write_analysis_checkpoint(\n'
             + '                            company_id,\n'
             + '                            "done",\n'
             + '                            "ok",\n'
             + '                        )\n')
    if b_anchor not in _ORIG:
        print("  ✗ B 构造失败：找不到 patrol_enrolled 锚点")
        r.append(False)
    else:
        p = _mk(_ORIG.replace(b_anchor, b_add, 1), "_bad_lockB.py")
        if p:
            # B 单调取锁侧（无锁）时运行期无害 → 绿；但 B+A 才复现事故 → 红。
            r.append(_scenario("B 仅调用侧回退（_is_result_deleted 仍无锁）",
                               check_no_lock_reentrancy(p), False))
            ab = _mk(_ORIG.replace(a_old, a_new, 1).replace(b_anchor, b_add, 1)
                     if a_old in _ORIG else "", "_bad_lockAB.py")
            r.append(_scenario("A+B 完整复现事故（取锁侧＋调用侧同时回退）",
                               check_no_lock_reentrancy(ab) if ab else [None], True)
                     if ab else False)

    # —— D：写回守卫重新加锁（最可能被回归成的一种形态）————————————————————
    #    `_write_analysis_checkpoint` 被 `_run_analysis_thread` 的锁块直接调用，
    #    它一旦自己 `with _analysis_lock:` 就立刻自死锁。
    d_old = '        payload = {\n'
    d_new = '        with _analysis_lock:\n            payload = {\n'
    if d_old not in _ORIG:
        print("  ✗ D 构造失败：找不到 _write_analysis_checkpoint 的 payload 锚点")
        r.append(False)
    else:
        p = _mk(_ORIG.replace(d_old, d_new, 1), "_bad_lockD.py")
        r.append(_scenario("D 写回守卫 _write_analysis_checkpoint 重新加锁",
                           check_no_lock_reentrancy(p) if p else [None], True)
                 if p else False)

    # —— C：无关改动（对照组）—————————————————————————————————————————————
    c_old = '    user_context_token = set_current_user_id(user_id)\n'
    c_new = '    # ★ 无关注释对照（不动锁语义）\n    user_context_token = set_current_user_id(user_id)\n'
    if c_old not in _ORIG:
        print("  ✗ C 构造失败：找不到 user_context_token 锚点")
        r.append(False)
    else:
        p = _mk(_ORIG.replace(c_old, c_new, 1), "_bad_lockC.py")
        r.append(_scenario("C 无关改动（对照）", check_no_lock_reentrancy(p) if p else [None], False)
                 if p else False)

    for _p in _TMP_NAMES:
        try:
            os.remove(_p)
        except Exception:
            pass

    end = check_no_lock_reentrancy(_MAIN)
    r.append(_scenario("还原后复跑真实 main.py", end, False))

    print("-" * 78)
    if all(r):
        print("【_reverse_verify_lock_gate.py】反向验证全部通过（%d/%d）：" % (len(r), len(r)))
        print("  0 基线绿 / A 按判据红 / B 绿(取锁侧已无锁,运行期无害) / "
              "A+B 按判据红 / D 按判据红 / C 绿 / 还原后绿")
        return 0
    print("【_reverse_verify_lock_gate.py】反向验证未全部通过：%d/%d" % (sum(1 for x in r if x), len(r)))
    return 1


if __name__ == "__main__":
    sys.exit(main())
